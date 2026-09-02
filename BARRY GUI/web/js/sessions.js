/* ==========================================================================
   sessions.js -- Scan a data root and browse every recording under it.

   Point it at D:\PTEN\PTEN or a netfiles share; the server walks the tree,
   identifies each recording by mouse/session/start-time, and returns them
   grouped by cohort. Clicking one opens it in Xplorefinder.
   ========================================================================== */
'use strict';

BARRY.views.sessions = (function () {
  let sessions = [];
  let tree = [];
  let scanId = null;
  let poll = null;
  let query = '';
  let groupFilter = '';
  const flags = new Set();
  const picked = new Set();   // paths queued for opening
  const health = {};          // path -> report from /api/session/health
  let healthBusy = false;

  const RECENT_KEY = 'barry.roots';
  const LAST_KEY = 'barry.lastSessions';

  /* Remember which recordings were last open, so a restart picks up where you
     left off rather than at an empty Xplorefinder. */
  function rememberOpen(paths) {
    try { localStorage.setItem(LAST_KEY, JSON.stringify(paths.slice(0, 4))); }
    catch (e) { /* private mode */ }
  }

  function lastOpen() {
    try { return JSON.parse(localStorage.getItem(LAST_KEY) || '[]'); }
    catch (e) { return []; }
  }

  /* ---------- recent roots ---------- */
  function recents() {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); }
    catch (e) { return []; }
  }
  function remember(root) {
    try {
      const list = [root].concat(recents().filter((r) => r !== root)).slice(0, 6);
      localStorage.setItem(RECENT_KEY, JSON.stringify(list));
    } catch (e) { /* private mode */ }
    renderRecents();
  }
  function renderRecents() {
    const host = $('#rootRecent');
    host.innerHTML = '';
    for (const r of recents()) {
      host.appendChild(el('button', {
        text: r, title: r,
        onclick: () => { $('#rootPath').value = r; start(r); },
      }));
    }
  }

  /* ---------- scanning ---------- */
  async function start(root) {
    root = (root || $('#rootPath').value || '').trim().replace(/^["']|["']$/g, '');
    if (!root) { toast('Enter or browse to a data root first.', 'err'); return; }

    stopPoll();
    $('#scanStatus').classList.remove('hidden');
    $('#scanStatus').innerHTML = '';
    $('#scanStatus').appendChild(el('span', { class: 'spin' }));
    $('#scanStatus').appendChild(el('span', { text: 'Starting…' }));

    try {
      const res = await apiPost('/api/discover/start', {
        root,
        max_depth: parseInt($('#rootDepth').value, 10) || 6,
        read_headers: $('#rootHeaders').checked,
      });
      scanId = res.job.id;
      remember(root);
      poll = setInterval(tick, 400);
      tick();
    } catch (e) {
      $('#scanStatus').innerHTML = '';
      $('#scanStatus').appendChild(el('span', { class: 'stat-chip warn', text: e.message }));
    }
  }

  function stopPoll() { if (poll) clearInterval(poll); poll = null; }

  async function tick() {
    if (!scanId) return;
    let data;
    try { data = await api('/api/discover/' + scanId); }
    catch (e) { stopPoll(); return; }
    const j = data.job;

    const box = $('#scanStatus');
    box.innerHTML = '';
    if (j.status === 'running') {
      box.appendChild(el('span', { class: 'spin' }));
      box.appendChild(el('span', { text: j.found + ' session(s) · ' + j.scanned + ' folders scanned' }));
      box.appendChild(el('code', { text: j.current || '' }));
      box.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Stop',
        onclick: () => apiPost('/api/discover/' + scanId + '/cancel').catch(() => {}),
      }));
      return;
    }

    stopPoll();
    if (j.status === 'failed') {
      box.appendChild(el('span', { class: 'stat-chip warn', text: j.error || 'Scan failed.' }));
      return;
    }

    sessions = j.sessions || [];
    tree = j.tree || [];
    box.appendChild(el('span', {
      class: 'stat-chip good',
      text: sessions.length + ' session(s) in ' + j.elapsed + 's',
    }));
    box.appendChild(el('code', { text: j.root }));
    box.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Rescan', onclick: () => start(j.root),
    }));

    $('#sessFilters').classList.remove('hidden');
    renderGroupFilter();
    renderTree();
    BARRY.activity.log('sessions.scan',
      { root: j.root, found: sessions.length, elapsed: j.elapsed });
  }

  /* ---------- filtering ---------- */
  function renderGroupFilter() {
    const host = $('#sessGroupFilter');
    host.innerHTML = '';
    host.appendChild(el('button', {
      class: 'pill' + (groupFilter ? '' : ' active'), text: 'All cohorts',
      onclick: () => { groupFilter = ''; renderGroupFilter(); renderTree(); },
    }));
    for (const g of tree) {
      host.appendChild(el('button', {
        class: 'pill' + (groupFilter === g.group ? ' active' : ''),
        text: g.group + ' (' + g.n + ')',
        onclick: () => { groupFilter = g.group; renderGroupFilter(); renderTree(); },
      }));
    }
  }

  function matches(s) {
    if (groupFilter && (s.identity.group || 'Ungrouped') !== groupFilter) return false;
    if (flags.has('video') && !s.has_video) return false;
    if (flags.has('converted') && !s.converted) return false;
    if (flags.has('bad') && !(s.stored && (s.stored.bad_channels || []).length)) return false;
    if (flags.has('good') && qualityOf(s) !== 'good') return false;
    if (flags.has('exclude') && qualityOf(s) === 'exclude') return false;
    if (flags.has('unhealthy')) {
      const h = health[s.path];
      if (!h || h.level === 'ok') return false;
    }
    if (!query) return true;
    const q = query.toLowerCase();
    return (s.identity.label || '').toLowerCase().includes(q)
      || (s.path || '').toLowerCase().includes(q)
      || (s.name || '').toLowerCase().includes(q);
  }

  /* ---------- tree ---------- */
  function renderTree() {
    const host = $('#sessTree');
    host.innerHTML = '';
    const visible = sessions.filter(matches);

    $('#sessSub').textContent = visible.length + ' of ' + sessions.length
      + ' session(s)' + (query ? ' matching "' + query + '"' : '')
      + (picked.size ? '  ·  ' + picked.size + ' selected' : '');
    renderPickBar();

    if (!visible.length) {
      host.appendChild(el('div', { class: 'tree-empty',
        text: sessions.length ? 'Nothing matches those filters.'
                              : 'Scan a data root to list its recordings.' }));
      return;
    }

    const byGroup = new Map();
    for (const s of visible) {
      const g = s.identity.group || 'Ungrouped';
      if (!byGroup.has(g)) byGroup.set(g, new Map());
      const mice = byGroup.get(g);
      const mk = s.identity.mouse != null ? 'm' + s.identity.mouse
        : (s.identity.mouse_folder || 'unknown');
      if (!mice.has(mk)) mice.set(mk, []);
      mice.get(mk).push(s);
    }

    for (const [g, mice] of byGroup) {
      const total = Array.from(mice.values()).reduce((a, b) => a + b.length, 0);
      const grp = el('div', { class: 'grp' }, [
        el('div', { class: 'grp-head' }, [
          el('span', { text: g }),
          el('span', { class: 'count', text: total + ' session(s), ' + mice.size + ' mice' }),
        ]),
      ]);
      const keys = Array.from(mice.keys()).sort((a, b) => {
        const na = parseInt(a.replace(/\D/g, ''), 10);
        const nb = parseInt(b.replace(/\D/g, ''), 10);
        if (isFinite(na) && isFinite(nb)) return na - nb;
        return String(a).localeCompare(String(b));
      });
      for (const mk of keys) {
        const list = mice.get(mk).slice().sort(
          (a, b) => (a.identity.session || 0) - (b.identity.session || 0));
        const row = el('div', { class: 'mouse-row' }, [
          el('div', { class: 'mouse-label' }, [
            el('strong', { text: mk }),
            el('span', { class: 'folder', text: list[0].identity.mouse_folder || '' }),
            el('span', { class: 'folder', text: list.length + ' session(s)' }),
          ]),
        ]);
        const cards = el('div', { class: 'sess-cards' });
        for (const s of list) cards.appendChild(sessionCard(s));
        row.appendChild(cards);
        grp.appendChild(row);
      }
      host.appendChild(grp);
    }
  }

  function sessionCard(s) {
    const i = s.identity;
    const badN = s.stored ? (s.stored.bad_channels || []).length : 0;
    const isPicked = picked.has(s.path);
    return el('div', {
      class: 'sess-card' + (isPicked ? ' picked' : ''), title: s.path,
      onclick: (e) => {
        // Ctrl/Cmd or shift adds to the selection; a plain click opens it.
        if (e.ctrlKey || e.metaKey || e.shiftKey || picked.size) {
          togglePick(s.path);
          return;
        }
        setView('xplore');
        rememberOpen([s.path]);
        BARRY.views.xplore.open(s.path);
      },
    }, [
      el('button', {
        class: 'sc-pick' + (isPicked ? ' on' : ''),
        title: isPicked ? 'Remove from selection' : 'Add to selection',
        text: isPicked ? '\u2713' : '+',
        onclick: (e) => { e.stopPropagation(); togglePick(s.path); },
      }),
      el('div', { class: 'sc-top' }, [
        el('span', { class: 'sc-name', text: 's' + (i.session != null ? i.session : '?') }),
        el('span', { class: 'sc-sub', text: i.start ? i.start.replace('T', ' ') : s.name }),
      ]),
      el('div', { class: 'sc-sub', text:
        (s.channels ? s.channels + ' ch · ' : '')
        + (s.fs ? Math.round(s.fs) + ' Hz · ' : '')
        + (s.duration_s ? fmtTime(s.duration_s) : '') }),
      el('div', { class: 'sc-flags' }, [
        s.converted ? el('span', { class: 'flagchip mat', text: '.mat' }) : null,
        s.has_video ? el('span', { class: 'flagchip video', text: 'video' }) : null,
        s.has_tracking ? el('span', { class: 'flagchip', text: 'tracking' }) : null,
        badN ? el('span', { class: 'flagchip bad', text: badN + ' bad' }) : null,
        i.confidence !== 'high' ? el('span', { class: 'flagchip bad',
          text: 'id: ' + i.confidence }) : null,
        healthPill(s),
        noteChip(s),
      ]),
      flagSet(s),
    ]);
  }

  /* ======================================================================
     Feature 1 -- Health check
     A truncated channel file, a rig that changed sample rate mid-cohort or a
     recording that is 40 seconds long are all things you would rather learn
     here than three stages into the pipeline.
     ====================================================================== */
  function healthPill(s) {
    const h = health[s.path];
    if (!h) return null;
    const label = h.level === 'ok' ? 'healthy'
      : (h.n_bad ? h.n_bad + ' problem' + (h.n_bad > 1 ? 's' : '')
                 : h.n_warn + ' note' + (h.n_warn > 1 ? 's' : ''));
    return el('span', {
      class: 'health-pill ' + h.level, text: label,
      title: 'Click for the full report',
      onclick: (e) => { e.stopPropagation(); showHealth(s); },
    });
  }

  async function checkHealth(paths, deep) {
    if (healthBusy) { toast('Still checking the last batch.', 'err'); return; }
    healthBusy = true;
    const status = $('#scanStatus');
    status.classList.remove('hidden');
    status.textContent = 'Checking ' + paths.length + ' session(s)'
                       + (deep ? ', reading signal from every channel' : '') + '\u2026';
    try {
      // Chunked so one slow network share does not stall the whole sweep,
      // and so partial results appear as they arrive.
      const size = deep ? 4 : 12;
      for (let i = 0; i < paths.length; i += size) {
        const chunk = paths.slice(i, i + size);
        const res = await apiPost('/api/session/health',
                                  { paths: chunk, deep: !!deep });
        for (const rep of (res.reports || [])) health[rep.path] = rep;
        status.textContent = 'Checked ' + Math.min(i + size, paths.length)
                           + ' of ' + paths.length + '\u2026';
        renderTree();
      }
      const bad = paths.filter((x) => (health[x] || {}).level === 'bad').length;
      const warn = paths.filter((x) => (health[x] || {}).level === 'warn').length;
      status.textContent = 'Health: ' + (paths.length - bad - warn) + ' clean, '
                         + warn + ' with notes, ' + bad + ' with problems.';
      toast('Checked ' + paths.length + ' session(s)', bad ? 'err' : 'ok');
    } catch (e) {
      status.textContent = 'Health check failed: ' + e.message;
    }
    healthBusy = false;
    renderTree();
  }

  function showHealth(s) {
    const h = health[s.path] || {};
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Health \u2014 ' + (s.identity.label || s.name) }),
        el('span', { class: 'sub', text: s.path }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [BARRY.checkList(h.checks || [])]),
      el('div', { class: 'mf' }, [
        el('button', {
          class: 'btn ghost sm', text: 'Deep check (reads every channel)',
          onclick: async () => { closeModal(); await checkHealth([s.path], true);
                                 showHealth(s); },
        }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost sm', text: 'Open folder',
          onclick: () => apiPost('/api/reveal', { path: s.path }).catch(() => {}) }),
        el('button', { class: 'btn', text: 'Close', onclick: closeModal }),
      ]),
    ]));
  }

  /* ======================================================================
     Feature 2 -- Quality flags and notes
     Which recordings are in the analysis and which were thrown out is a
     decision that otherwise lives in someone's notebook. Keyed on session
     identity, so it survives a re-mount or a rename like bad channels do.
     ====================================================================== */
  function qualityOf(s) {
    return (s.stored && s.stored.quality) || '';
  }

  function flagSet(s) {
    const cur = qualityOf(s);
    const mk = (key, label, title) => el('button', {
      class: 'flag-btn ' + key + (cur === key ? ' on' : ''),
      text: label, title,
      onclick: async (e) => {
        e.stopPropagation();
        await setQuality(s, cur === key ? '' : key);
      },
    });
    return el('div', { class: 'flag-set' }, [
      mk('good', 'good', 'Include in analysis'),
      mk('review', 'review', 'Needs a second look'),
      mk('exclude', 'exclude', 'Left out of the analysis'),
      el('button', {
        class: 'flag-btn', text: 'note', title: 'Notes on this recording',
        onclick: (e) => { e.stopPropagation(); editNote(s); },
      }),
    ]);
  }

  function noteChip(s) {
    const n = (s.stored && s.stored.notes) || '';
    if (!n) return null;
    return el('span', { class: 'flagchip', text: 'note', title: n });
  }

  async function setQuality(s, quality) {
    try {
      const res = await apiPost('/api/session/note',
                                { identity: s.identity, quality });
      s.stored = res.session || s.stored;
      renderTree();
      toast(quality ? 'Marked ' + (s.identity.label || s.name) + ' "' + quality + '"'
                    : 'Cleared the flag', 'ok', 2400);
    } catch (e) { toast(e.message, 'err'); }
  }

  function editNote(s) {
    const box = el('textarea', {
      style: 'width:100%;height:150px;font-size:12.5px;line-height:1.6',
      placeholder: 'Anything the next person should know \u2014 electrode '
                 + 'position, what the animal was doing, why it was excluded\u2026',
      text: (s.stored && s.stored.notes) || '',
    });
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Notes \u2014 ' + (s.identity.label || s.name) }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [box]),
      el('div', { class: 'mf' }, [
        el('span', { class: 'hint', text: 'Saved against the session ID, so it '
                                        + 'follows the recording.' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        el('button', {
          class: 'btn', text: 'Save',
          onclick: async () => {
            try {
              const res = await apiPost('/api/session/note',
                                        { identity: s.identity, notes: box.value });
              s.stored = res.session || s.stored;
              closeModal();
              renderTree();
              toast('Note saved', 'ok');
            } catch (e) { toast(e.message, 'err'); }
          },
        }),
      ]),
    ]));
  }

  /* ======================================================================
     Feature 3 -- Compare and export a manifest
     The table that goes into a methods section, built from what is already
     on screen instead of retyped.
     ====================================================================== */
  function manifestRows(list) {
    return list.map((s) => ({
      label: s.identity.label || s.name,
      cohort: s.identity.group || '',
      mouse: s.identity.mouse != null ? s.identity.mouse : '',
      session: s.identity.session != null ? s.identity.session : '',
      start: s.identity.start || '',
      channels: s.channels || '',
      fs_hz: s.fs ? Math.round(s.fs) : '',
      duration_s: s.duration_s ? Math.round(s.duration_s) : '',
      quality: qualityOf(s),
      health: (health[s.path] || {}).level || '',
      bad_channels: (s.stored && s.stored.bad_channels) || [],
      video: s.has_video ? 'yes' : 'no',
      tracking: s.has_tracking ? 'yes' : 'no',
      converted: s.converted ? 'yes' : 'no',
      id_confidence: s.identity.confidence || '',
      notes: (s.stored && s.stored.notes) || '',
      path: s.path,
    }));
  }

  function compare() {
    const list = picked.size
      ? sessions.filter((s) => picked.has(s.path))
      : sessions.filter(matches);
    if (!list.length) { toast('Nothing to compare.', 'err'); return; }
    const rows = manifestRows(list.slice(0, 24));
    const keys = Object.keys(rows[0]).filter((k) => k !== 'path');

    const table = el('table', { class: 'cmp-table' }, [
      el('thead', {}, [el('tr', {}, [el('th', { text: '' })].concat(
        rows.map((r) => el('th', { text: r.label }))))]),
      el('tbody', {}, keys.map((k) => {
        const vals = rows.map((r) => String(
          Array.isArray(r[k]) ? r[k].join(' ') : (r[k] === '' ? '\u2014' : r[k])));
        const differ = new Set(vals).size > 1;
        return el('tr', {}, [el('td', { class: 'k', text: k })].concat(
          vals.map((v) => el('td', {
            class: differ ? 'differ' : '', text: v, title: v,
          }))));
      })),
    ]);

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Compare ' + rows.length + ' session(s)' }),
        el('span', { class: 'sub', text: 'differing rows are highlighted' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [el('div', { class: 'cmp-table-wrap' }, [table])]),
      el('div', { class: 'mf' }, [
        el('button', {
          class: 'btn ghost sm', text: 'Export CSV',
          onclick: () => exportManifest(list),
        }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn', text: 'Close', onclick: closeModal }),
      ]),
    ]));
  }

  function exportManifest(list) {
    const rows = manifestRows(list || (picked.size
      ? sessions.filter((s) => picked.has(s.path))
      : sessions.filter(matches)));
    if (!rows.length) { toast('Nothing to export.', 'err'); return; }
    BARRY.download('/api/session/manifest',
                    { rows, name: 'sessions.csv' }, 'sessions.csv');
    BARRY.activity.log('sessions.manifest', { n: rows.length });
  }

  function togglePick(path) {
    if (picked.has(path)) picked.delete(path); else picked.add(path);
    renderTree();
  }

  function renderPickBar() {
    let bar = $('#sessPickBar');
    if (!picked.size) { if (bar) bar.remove(); return; }
    if (!bar) {
      bar = el('div', { class: 'pick-bar', id: 'sessPickBar' });
      $('#sessTree').parentNode.insertBefore(bar, $('#sessTree'));
    }
    bar.innerHTML = '';
    bar.appendChild(el('span', { class: 'stat-chip good',
      text: picked.size + ' selected' }));
    bar.appendChild(el('span', { class: 'hint',
      style: 'font-size:11px;color:var(--text-3)',
      text: 'Ctrl/Cmd-click or use + to add more.' }));
    bar.appendChild(el('div', { style: 'flex:1' }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Clear',
      onclick: () => { picked.clear(); renderTree(); },
    }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Health check',
      onclick: () => checkHealth(Array.from(picked), false),
    }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Compare',
      onclick: compare,
    }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Export CSV',
      onclick: () => exportManifest(),
    }));
    bar.appendChild(el('button', {
      class: 'btn sm',
      text: 'Open ' + picked.size + ' in Xplorefinder',
      onclick: openPicked,
    }));
  }

  async function openPicked() {
    const paths = Array.from(picked);
    if (!paths.length) return;
    picked.clear();
    rememberOpen(paths);
    setView('xplore');

    // Opening in series, not in parallel: each open reads headers and the
    // server keeps one session resident at a time, so a burst of concurrent
    // opens just fights itself.
    let opened = 0;
    for (const p of paths) {
      const sess = await BARRY.views.xplore.open(p);
      if (sess) opened += 1;
    }
    // Give every opened recording a pane if the layout can hold them.
    BARRY.views.xplore.fillPanes();
    renderTree();
    toast('Opened ' + opened + ' of ' + paths.length + ' session(s)',
          opened === paths.length ? 'ok' : 'err');
    BARRY.activity.log('sessions.open_multi', { n: opened, requested: paths.length });
  }

  /* Reopen the previous session(s), announced rather than done silently --
     a window that springs open with old data and no explanation is worse than
     an empty one. */
  async function restoreLast(paths) {
    const names = paths.map((p) => baseName(p));
    toast('Reopening ' + names.join(', '), 'ok', 4000);
    for (const p of paths) {
      const sess = await BARRY.views.xplore.open(p);
      if (!sess) {
        toast('Could not reopen ' + baseName(p) + ' — it may be on a drive '
              + 'that is not mounted.', 'err', 8000);
      }
    }
    if (BARRY.views.xplore.state.order.length > 1) BARRY.views.xplore.fillPanes();
    setView('xplore');
  }

  /* ---------- init ---------- */
  function init() {
    $('#rootGo').addEventListener('click', () => start());
    $('#rootPath').addEventListener('keydown', (e) => { if (e.key === 'Enter') start(); });
    $('#sessScan').addEventListener('click', () => start());
    $('#rootBrowse').addEventListener('click', async () => {
      const p = await pickPath('folder', '');
      if (p) { $('#rootPath').value = p; start(p); }
    });
    $('#sessReveal').addEventListener('click', () => {
      const p = $('#rootPath').value;
      if (p) apiPost('/api/reveal', { path: p }).catch(() => {});
    });
    $('#sessHealth').addEventListener('click', () => {
      const list = picked.size
        ? Array.from(picked)
        : sessions.filter(matches).map((x) => x.path);
      if (!list.length) { toast('Scan a root first.', 'err'); return; }
      checkHealth(list, false);
    });
    $('#sessCompare').addEventListener('click', compare);

    let deb = null;
    $('#sessSearch').addEventListener('input', (e) => {
      query = e.target.value;
      clearTimeout(deb);
      deb = setTimeout(renderTree, 120);
    });

    $$('#sessFilters .filter-row .pill[data-flag]').forEach((b) =>
      b.addEventListener('click', () => {
        const f = b.dataset.flag;
        if (flags.has(f)) flags.delete(f); else flags.add(f);
        b.classList.toggle('active', flags.has(f));
        renderTree();
      }));

    renderRecents();

    // ?root=<path> scans straight away, so a data root can be bookmarked.
    const params = new URLSearchParams(location.search);
    const preset = params.get('root');
    if (preset) { $('#rootPath').value = preset; setTimeout(() => start(preset), 60); }
    else if (recents().length) { $('#rootPath').value = recents()[0]; }

    // Reopen what was last being looked at, unless this window was launched
    // with its own target (a pop-out, or a deep link).
    if (!params.get('csc') && !preset) {
      const last = lastOpen();
      if (last.length) setTimeout(() => restoreLast(last), 250);
    }
  }

  return {
    init,
    picked: () => Array.from(picked),
    onShow: () => { renderRecents(); },
  };
})();
