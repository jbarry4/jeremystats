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

  /* Availability is a choice, not a switch.

     "Everything BARRY knows" and "only what I can open right now" are two
     different jobs -- one is a catalogue of 473 recordings, the other is a
     work queue of 184 -- and as the ninth checkbox in a row of nine that
     distinction was invisible. */
  let avail = 'all';                      // 'all' | 'open'

  /* What the scan itself is told to do.

     Held here rather than read off two inputs in the toolbar, because the
     inputs are gone: they were the state, and a popover that is rebuilt
     every time it opens cannot be. Defaults are named so the button can say
     when they have been changed -- "why did the scan miss it" is almost
     always Depth. */
  const SCAN_DEFAULTS = { headers: true, depth: 6 };
  const scanOpts = Object.assign({}, SCAN_DEFAULTS);

  /* What each filter is called and where it belongs. One list, so the
     popover, the chips and the count can never disagree about what is on. */
  const FILTERS = [
    { group: 'Recording', id: 'video', name: 'Has video' },
    { group: 'Recording', id: 'converted', name: 'Converted (.mat)',
      note: 'A .mat written by the conversion step' },
    { group: 'Recording', id: 'bad', name: 'Has bad channels' },
    { group: 'Quality', id: 'good', name: 'Marked good',
      note: 'Flagged good for analysis' },
    { group: 'Quality', id: 'exclude', name: 'Hide excluded',
      note: 'Leave out anything flagged exclude' },
    { group: 'Quality', id: 'unhealthy', name: 'Health notes',
      note: 'Only the ones the health check flagged' },
    /* Which recordings still need StrataScope is a question with sixty-odd
       sheets behind it now, and scrolling four hundred cards looking for
       the gaps is not an answer. */
    { group: 'Layers', id: 'layers', name: 'Layers labelled' },
    { group: 'Layers', id: 'nolayers', name: 'Layers still to do' },
  ];
  const picked = new Set();   // paths queued for opening
  const health = {};          // path -> report from /api/session/health
  let healthBusy = false;

  /* Which of the listed recordings this scan actually found.

     The scan page used to hold its results in memory and nothing else, so a
     refresh emptied it -- a strange thing for a page about what is on your
     drives to do. Everything BARRY has ever met is in the registry now, so
     the page opens showing all of it faint and a scan brightens what it
     finds. Refreshing costs you the brightening, not the list. */
  const foundNow = new Set();
  let knownLoaded = false;

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

  /* A registry row, wearing the shape the tree already knows how to draw.

     A translation rather than a second renderer, deliberately: one way of
     drawing a session means the remembered ones and the found ones cannot
     drift apart visually, which is the point of showing them together. */
  function fromRegistry(r) {
    const path = (r.here || [])[0] || (r.paths || [])[0] || '';
    return {
      /* Whether THIS computer has met it: true, false, or null for "the
         server did not say". Carried through because the two modes are two
         different questions and this is what separates them.

         Null matters. The demo project is appended to the payload after the
         walk that marks the rows, so those rows carry no answer at all, and
         `!!undefined` made that indistinguishable from "not seen" -- which
         hid the tour session from the scan view. Absent is not no. */
      _seenHere: r.seen_here === undefined ? null : !!r.seen_here,
      path,
      name: r.label || r.key || r.gid,
      gid: r.gid,
      _remembered: true,
      _reachable: !!r.reachable,
      identity: {
        group: r.project || 'Unfiled',
        mouse: r.mouse,
        session: r.session,
        start: r.start,
        label: r.label,
        mouse_folder: '',
        confidence: 'high',
      },
      channels: r.n_channels || 0,
      fs: r.fs || null,
      duration_s: r.duration_s || 0,
      converted: !!r.converted,
      has_video: !!r.has_video,
      has_tracking: false,
      /* What is attached, and where it can be read from.
         Carried through rather than dropped: the filters ask about both,
         and a translation that quietly loses a field makes a filter that
         matches nothing -- which looks like "none of them qualify" rather
         than like a bug. */
      has: r.has || {},
      here: r.here || [],
      hemisphere: r.hemisphere || null,
      hemisphere_source: r.hemisphere_source || null,
      /* The landmarks a CSD is read against, and what the extraction made
         of them. `extraction_note` is the one that matters: "Missing: No
         CA1 SP channel" changes how the recording should be read, and it
         was only ever visible in a spreadsheet. */
      fissure_channel: r.fissure_channel,
      ripple_channel: r.ripple_channel,
      hilus_channel: r.hilus_channel,
      extraction_note: r.extraction_note || null,
      needs_processing: !!r.needs_processing,
      stored: (r.bad_channels || []).length
        ? { bad_channels: r.bad_channels } : null,
    };
  }

  /* Everything BARRY knows, as the starting list. */
  async function loadKnown(force) {
    if (knownLoaded && !force) return;
    knownLoaded = true;

    /* The registry read takes about five seconds on a full catalogue, and
       this view opened as an empty box for all of it -- which reads as "no
       sessions" rather than "not yet". Only when there is nothing already on
       screen: refreshing a list that is already there should not blank it. */
    const bones = sessions.length
      ? null
      : BARRY.skeleton.into($('#sessTree'), 'card', 6);
    const sub = $('#sessSub');
    if (bones && sub) sub.textContent = 'Reading the catalogue\u2026';

    let reg;
    try {
      reg = await api('/api/registry');
    } catch (e) {
      // An older server: the page still works, but the bones must not stay.
      if (bones) bones();
      if (sub) sub.textContent = '';
      renderTree();
      return;
    }
    if (bones) bones();
    const rows = (reg.tree || []).flatMap(
      (p) => p.mice.flatMap((m) => m.sessions));
    const have = new Set(sessions.map((x) => x.gid).filter(Boolean));
    const seenPath = new Set(sessions.map((x) => x.path).filter(Boolean));
    const extra = rows
      .filter((r) => !have.has(r.gid))
      .map(fromRegistry)
      .filter((x) => !x.path || !seenPath.has(x.path));
    if (!extra.length) { renderTree(); return; }
    sessions = sessions.concat(extra);
    if (!tree.length) {
      // The cohort pills come from the scan; without one, build them from
      // what is known so the filter still works.
      const by = {};
      for (const x of sessions) {
        const g = x.identity.group || 'Ungrouped';
        by[g] = (by[g] || 0) + 1;
      }
      tree = Object.keys(by).sort().map((g) => ({ group: g, n: by[g] }));
      renderGroupFilter();
    }
    const filters = $('#sessFilters');
    if (filters) filters.classList.remove('hidden');
    renderTree();
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
        max_depth: scanOpts.depth || SCAN_DEFAULTS.depth,
        read_headers: !!scanOpts.headers,
      });
      scanId = res.job.id;
      remember(root);
      /* Paced by a chained timeout rather than an interval, so the gap can
         grow. See tick(). */
      scanSeen = { scanned: -1, at: Date.now() };
      scanGap = 400;
      schedule();
      tick();
    } catch (e) {
      $('#scanStatus').innerHTML = '';
      $('#scanStatus').appendChild(el('span', { class: 'stat-chip warn', text: e.message }));
    }
  }

  /* How the scan poll paces itself, and how it notices a stall. */
  let scanSeen = null;      // {scanned, at} the last time the count moved
  let scanGap = 400;

  function schedule() {
    if (poll) clearTimeout(poll);
    poll = setTimeout(tick, scanGap);
  }

  function stopPoll() {
    if (poll) clearTimeout(poll);
    poll = null;
    scanSeen = null;
    scanGap = 400;
  }

  async function tick() {
    if (!scanId) return;
    let data;
    try { data = await api('/api/discover/' + scanId); }
    catch (e) { stopPoll(); return; }
    const j = data.job;

    /* Back off while it runs. Two and a half polls a second for a scan that
       takes minutes is thousands of requests for a number nobody can read
       that fast. */
    if (j.status === 'running') {
      scanGap = Math.min(2000, Math.round(scanGap * 1.25));
      schedule();
    }

    /* Has it actually got anywhere? A network drive that is not reachable
       leaves the walking thread blocked, the job "running" and the counter
       still -- which looks exactly like a slow scan and is not one. */
    let stalledFor = 0;
    if (j.status === 'running') {
      if (!scanSeen || j.scanned !== scanSeen.scanned) {
        scanSeen = { scanned: j.scanned, at: Date.now() };
      } else {
        stalledFor = Math.round((Date.now() - scanSeen.at) / 1000);
      }
    }

    const box = $('#scanStatus');
    box.innerHTML = '';
    if (j.status === 'running') {
      box.appendChild(el('span', { class: 'spin' }));
      box.appendChild(el('span', { text: j.found + ' session(s) \u00b7 '
                                      + j.scanned + ' folders scanned' }));
      box.appendChild(el('code', { text: j.current || '' }));
      if (stalledFor >= 15) {
        /* Say what it is stuck on. On a mapped drive this is almost always
           the drive being unreachable, and it will not resolve by waiting --
           so the useful thing is the path and a way out. */
        box.appendChild(el('span', { class: 'stat-chip warn',
          title: 'The folder count has not moved. If this is a mapped drive, '
               + 'check it is still connected -- Windows leaves a dead mount '
               + 'looking normal until something reads from it.',
          text: 'no progress for ' + stalledFor + 's' }));
      }
      box.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Stop',
        onclick: () => {
          apiPost('/api/discover/' + scanId + '/cancel').catch(() => {});
          stopPoll();
          box.innerHTML = '';
          box.appendChild(el('span', { class: 'stat-chip',
                                       text: 'Scan stopped.' }));
        },
      }));
      return;
    }

    stopPoll();
    if (j.status === 'failed') {
      box.appendChild(el('span', { class: 'stat-chip warn', text: j.error || 'Scan failed.' }));
      return;
    }

    /* Merge rather than replace: what the scan found is now known first
       hand, and what it did not find is still worth listing -- faint -- so
       "the drive I expected it on does not have it" is visible rather than
       silent. */
    const scanned = j.sessions || [];
    for (const x of scanned) { x._remembered = false; }
    foundNow.clear();
    for (const x of scanned) { if (x.gid) foundNow.add(x.gid); }
    const scannedPaths = new Set(scanned.map((x) => x.path));
    const kept = sessions.filter(
      (x) => x._remembered && !(x.gid && foundNow.has(x.gid))
             && !scannedPaths.has(x.path));
    sessions = scanned.concat(kept);
    tree = j.tree || [];
    box.appendChild(el('span', {
      class: 'stat-chip good',
      text: sessions.length + ' session(s) in ' + j.elapsed + 's',
    }));

    /* Folders the scan would not vouch for.

     Kept visible rather than dropped: seven folders on the lab drives are 64
     files of header and nothing else -- an acquisition that was started and
     wrote nothing -- and they had been sitting in the registry looking like
     ordinary recordings. Holding them back is only defensible if it is also
     obvious, and reversible: "this looks wrong" is a judgement about data,
     and whoever made the recording is better placed to make it than a size
     check. */
  function heldChip(held) {
    const chip = el('button', {
      class: 'stat-chip warn',
      title: 'Folders that look like recordings but did not pass the check. '
           + 'Click to see why.',
      text: held.length + ' held back',
      onclick: () => showHeld(held),
    });
    return chip;
  }

  function showHeld(held) {
    const rows = held.map((h) => {
      const q = h.quality || {};
      return el('div', { class: 'held-row' }, [
        el('div', { style: 'min-width:0' }, [
          el('strong', { text: h.label || h.name || h.path }),
          el('code', { class: 'held-path', text: h.path }),
          ...(q.reasons || []).map(
            (r) => el('p', { class: 'hint', text: r })),
        ]),
        el('div', { class: 'held-acts' }, [
          el('span', { class: 'flagchip bad', text: q.verdict || '?' }),
          el('button', {
            class: 'btn sm', text: 'Add anyway',
            title: 'Register it despite the check. Nothing about the '
                 + 'recording changes; BARRY just stops leaving it out.',
            onclick: async (e) => {
              e.target.disabled = true;
              try {
                await apiPost('/api/discover/accept', { path: h.path });
                toast('Registered ' + (h.label || h.name) + '.', 'ok');
                loadKnown(true);
                e.target.textContent = 'Added';
              } catch (err) {
                toast(err.message, 'err', 8000);
                e.target.disabled = false;
              }
            },
          }),
          el('button', {
            class: 'btn ghost sm', text: 'Open the folder',
            onclick: () => apiPost('/api/reveal',
                                   { path: h.path }).catch(() => {}),
          }),
        ]),
      ]);
    });
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: held.length + ' folder(s) held back' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/>'
              + '</svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { class: 'hint',
          text: 'These look like recordings but did not pass the check, so '
              + 'they are not in the registry. Nothing on the drive has been '
              + 'touched \u2014 BARRY does not delete data it did not write.' }),
        el('div', { class: 'held-list' }, rows),
      ]),
    ]));
  }

  /* A scan is the one moment BARRY has the whole picture of a drive, so
       everything it walked past is now registered -- not just the handful
       anyone opens. The server did the writing; this tells the registry view
       which ones were actually laid eyes on, so they stop being merely
       remembered. */
    const reg = j.registered || {};
    if (reg.seen) {
      box.appendChild(el('span', {
        class: 'stat-chip',
        title: 'Every recording found is now in Sessions › Everything '
             + 'BARRY knows, whether or not you open it',
        text: reg.new
          ? reg.new + ' new · ' + reg.seen + ' catalogued'
          : reg.seen + ' catalogued',
      }));
    }
    if (BARRY.views.housekeeping && BARRY.views.housekeeping.confirm) {
      BARRY.views.housekeeping.confirm(Array.from(foundNow), j.root);
    }
    // Anything registered that this scan did not turn up should still be on
    // the page, faint. Forced, because the registry has just grown.
    loadKnown(true);

    box.appendChild(el('code', { text: j.root }));
    box.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Rescan', onclick: () => start(j.root),
    }));
    if ((j.held_back || []).length) box.appendChild(heldChip(j.held_back));

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

  /* Is this recording part of what THIS computer has met?

     Its own function because the filter and the count both need it and they
     had it written out twice, differently -- which is how the view came to
     say "188 of 185": the filter passed a row nobody had answered for and
     the count did not count it. */
  function inLocal(s) {
    return !s._remembered || s._seenHere !== false;
  }

  function matches(s) {
    /* "Scan a drive" is this computer's own view: what it has been exposed
       to, read off the registry on disk with no database involved.
       "Everything BARRY knows" is the shared catalogue -- every recording
       any machine has met, which is what travels through Supabase.

       A recording found by the scan running now counts as met whether or
       not a sighting has been filed yet. */
    if (mode === 'scan' && !inLocal(s)) return false;
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
    /* Layer state, from the registry's own count rather than by asking the
       layers store per card: four hundred cards would be four hundred
       questions, and the registry already knows. */
    const nLayers = ((s.has || {}).layers) || 0;
    if (flags.has('layers') && !nLayers) return false;
    if (flags.has('nolayers') && nLayers) return false;
    /* Can I open this, right now, on this computer.

       Not `here`, which is only whether a folder exists -- a folder can
       outlive its contents. The server answers this one properly: the
       registry asks the loader itself (`can_open`), and a scan already
       counted the CSC and .mat files so it can say `loadable` for free.

       The bug this replaces went the other way from the obvious one. A
       recording a scan had just walked, on this very machine, carried
       neither `here` nor `reachable` -- so the filter read the absence as
       "not on this machine" and hid the only certainly-openable things in
       the list. */
    if (avail === 'open' && !canOpen(s)) return false;
    if (!query) return true;
    const q = query.toLowerCase();
    return (s.identity.label || '').toLowerCase().includes(q)
      || (s.path || '').toLowerCase().includes(q)
      || (s.name || '').toLowerCase().includes(q);
  }

  /* Whether this recording opens on a click.

     Three shapes reach this list and they say it differently: the registry
     sends `can_open` and a `loadable` list, a scan sends `loadable` as a
     boolean, and anything older only has `here`. Taking the first that is
     actually present is the difference between a filter and a guess -- and
     reading a missing field as "no" is what hid every scanned recording. */
  function canOpen(s) {
    if (typeof s.can_open === 'boolean') return s.can_open;
    if (typeof s.loadable === 'boolean') return s.loadable;
    if (Array.isArray(s.loadable)) return s.loadable.length > 0;
    return (s.here || []).length > 0 || !!s._reachable;
  }

  function nActive() {
    return flags.size + (avail === 'all' ? 0 : 1);
  }

  /* One button, the chips for whatever is on, and nothing else. */
  function renderFilterBar() {
    const bar = $('#sessFilterBar');
    if (!bar) return;
    bar.innerHTML = '';
    const n = nActive();

    bar.appendChild(el('button', {
      class: 'btn ghost sm filter-open' + (n ? ' on' : ''),
      onclick: (e) => openPopover(e.currentTarget, filterPop),
    }, [
      el('span', { html: '<svg viewBox="0 0 20 20" class="fb-ico">'
        + '<path d="M3 5h14M6 10h8M9 15h2"/></svg>' }),
      el('span', { text: 'Filter' }),
      n ? el('span', { class: 'fb-count', text: String(n) }) : null,
    ].filter(Boolean)));

    /* A chip per active filter. The point of collapsing nine pills into a
       button is compactness; the point of the chips is that compactness
       must not cost you knowing what is on. */
    if (avail === 'open') {
      bar.appendChild(chip('Only what opens here', () => {
        avail = 'all'; renderFilterBar(); renderTree();
      }, 'open'));
    }
    for (const f of FILTERS) {
      if (!flags.has(f.id)) continue;
      bar.appendChild(chip(f.name, () => {
        flags.delete(f.id); renderFilterBar(); renderTree();
      }, f.id));
    }
    if (n > 1) {
      bar.appendChild(el('button', {
        class: 'linkish fb-clear', text: 'Clear all',
        onclick: () => {
          flags.clear(); avail = 'all'; renderFilterBar(); renderTree();
        },
      }));
    }
  }

  /* The scan's settings: one button, and what is not standard on its face.

     Modelled on the filter button beside it, because it is the same
     problem -- controls that matter occasionally and are in the way
     always. */
  function renderScanOpts() {
    const bar = $('#rootOptsBar');
    if (!bar) return;
    bar.innerHTML = '';
    const odd = [];
    if (!scanOpts.headers) odd.push('no headers');
    if (scanOpts.depth !== SCAN_DEFAULTS.depth) {
      odd.push('depth ' + scanOpts.depth);
    }
    bar.appendChild(el('button', {
      class: 'btn ghost sm filter-open' + (odd.length ? ' on' : ''),
      title: 'How this scan reads the drive',
      onclick: (e) => openPopover(e.currentTarget, scanOptsPop),
    }, [
      el('span', { html: '<svg viewBox="0 0 20 20" class="fb-ico">'
        + '<circle cx="10" cy="10" r="3"/><path d="M10 3v3M10 14v3M3 10h3'
        + 'M14 10h3"/></svg>' }),
      el('span', { text: 'Scan options' }),
      /* Named, not counted. "2" would tell you something is different
         without telling you what, and the whole reason to show it is that
         a changed depth explains a scan that found nothing. */
      odd.length ? el('span', { class: 'fb-count', text: odd.join(', ') })
                 : null,
    ].filter(Boolean)));
  }

  function scanOptsPop() {
    const box = el('div', { class: 'ctl-pop-body' });
    box.appendChild(el('div', { class: 'ctl-pop-group' }, [
      el('div', { class: 'ctl-pop-title', text: 'How to read what it finds' }),
      el('label', { class: 'ctl-pop-opt' + (scanOpts.headers ? ' on' : ''),
                    title: 'Opens the first CSC file of each candidate to '
                         + 'read its real header. Slower, and the only way '
                         + 'to get the exact recording id.' }, [
        el('input', { type: 'checkbox',
          checked: scanOpts.headers ? 'checked' : null,
          onchange: () => { scanOpts.headers = !scanOpts.headers; back(); } }),
        el('span', { text: 'Read headers (exact IDs)' }),
      ]),
      el('p', { class: 'hint', text: scanOpts.headers
        ? 'Every folder is opened far enough to read one header. This is '
          + 'what makes two copies of one recording recognisable as the '
          + 'same recording.'
        : 'Folders are identified by name and shape only, which is faster '
          + 'and cannot tell two copies apart.' }),
    ]));
    box.appendChild(el('div', { class: 'ctl-pop-group' }, [
      el('div', { class: 'ctl-pop-title', text: 'How deep to look' }),
      el('label', { class: 'ctl-pop-opt' }, [
        el('input', {
          type: 'number', value: String(scanOpts.depth), min: '1', max: '12',
          class: 'inp sm',
          oninput: (e) => {
            const v = parseInt(e.target.value, 10);
            scanOpts.depth = (v >= 1 && v <= 12) ? v : SCAN_DEFAULTS.depth;
            renderScanOpts();
          },
        }),
        el('span', { text: 'folders below the root' }),
      ]),
      el('p', { class: 'hint',
        text: 'A recording six folders down from a project root is normal '
            + 'here. Lower is faster; too low and the scan finds nothing '
            + 'and looks broken.' }),
    ]));
    if (scanOpts.headers !== SCAN_DEFAULTS.headers
        || scanOpts.depth !== SCAN_DEFAULTS.depth) {
      box.appendChild(el('button', {
        class: 'linkish fb-clear', text: 'Back to the usual',
        onclick: () => {
          Object.assign(scanOpts, SCAN_DEFAULTS);
          renderScanOpts();
          const open = document.querySelector('.ctl-pop');
          if (open && open.firstChild) {
            open.replaceChild(scanOptsPop(), open.firstChild);
          }
        },
      }));
    }

    function back() {
      renderScanOpts();
      const open = document.querySelector('.ctl-pop');
      if (open && open.firstChild) {
        open.replaceChild(scanOptsPop(), open.firstChild);
      }
    }
    return box;
  }

  function chip(label, off, id) {
    /* `data-flag` so anything driving this page -- a harness, a keyboard
       shortcut later -- can name a control rather than matching its
       wording. Nine pills carried it; collapsing them into a popover
       should not have cost it. */
    return el('span', { class: 'fb-chip', 'data-flag': id || null }, [
      el('span', { text: label }),
      el('button', { class: 'fb-chip-x', text: '\u00d7',
        title: 'Turn this one off', onclick: off }),
    ]);
  }

  function filterPop() {
    const box = el('div', { class: 'ctl-pop-body' });

    /* Availability first, because it is the one that changes what the view
       is FOR rather than which subset of it you see. */
    box.appendChild(el('div', { class: 'ctl-pop-group' }, [
      el('div', { class: 'ctl-pop-title', text: 'Which recordings' }),
      radio('Everything BARRY knows', avail === 'all',
            'Every recording on record, including ones on drives nobody '
            + 'has mounted since.',
            () => { avail = 'all'; refresh(); }, 'all'),
      radio('Only what opens here', avail === 'open',
            'Only the ones this computer can open right now \u2014 the '
            + 'folder is reachable and the CSC or .mat files are in it. '
            + 'This is the work queue.',
            () => { avail = 'open'; refresh(); }, 'open'),
    ]));

    let last = null;
    let group = null;
    for (const f of FILTERS) {
      if (f.group !== last) {
        last = f.group;
        group = el('div', { class: 'ctl-pop-group' }, [
          el('div', { class: 'ctl-pop-title', text: f.group }),
        ]);
        box.appendChild(group);
      }
      group.appendChild(check(f, () => {
        if (flags.has(f.id)) flags.delete(f.id); else flags.add(f.id);
        refresh();
      }));
    }

    function refresh() {
      renderFilterBar();
      renderTree();
      /* Repainted in place rather than closed: turning three filters on
         should be three clicks, not three clicks and two re-opens. */
      const open = document.querySelector('.ctl-pop');
      if (open && open.firstChild) {
        open.replaceChild(filterPop(), open.firstChild);
      }
    }
    return box;
  }

  function radio(label, on, note, pick, id) {
    return el('label', { class: 'ctl-pop-opt' + (on ? ' on' : ''),
                         title: note || '', 'data-avail': id || null }, [
      el('input', { type: 'radio', name: 'sessAvail',
        checked: on ? 'checked' : null, onchange: pick }),
      el('span', { text: label }),
    ]);
  }

  function check(f, toggle) {
    return el('label', {
      class: 'ctl-pop-opt' + (flags.has(f.id) ? ' on' : ''),
      title: f.note || '',
      'data-flag': f.id,
    }, [
      el('input', { type: 'checkbox',
        checked: flags.has(f.id) ? 'checked' : null, onchange: toggle }),
      el('span', { text: f.name }),
    ]);
  }

  /* ---------- tree ---------- */
  function renderTree() {
    const host = $('#sessTree');
    host.innerHTML = '';
    const visible = sessions.filter(matches);

    const nFound = sessions.filter((x) => !x._remembered).length;
    const nKnown = sessions.length - nFound;
    /* The two modes are two questions, and this line is where the view
       says which one it is answering. It used to fight with `setMode` over
       the same element -- prose from one, counts from the other, last
       writer winning -- so it now says both in the space of one line. */
    $('#sessSub').textContent = visible.length + ' of '
      + (mode === 'scan' ? sessions.filter(inLocal).length : sessions.length)
      + (mode === 'scan'
          ? ' on this computer  ·  read from the registry on this disk'
          : ' in the shared catalogue  ·  every machine, kept in step '
            + 'through Supabase')
      /* In the shared view, how the list divides between what this scan
         just found and what was already on record. Left out of the local
         view, where it said "185 of 185 ... 479 remembered" -- the 479
         being the whole catalogue, most of which this view is
         deliberately not showing. */
      + (mode !== 'scan' && nKnown
          ? '  ·  ' + nFound + ' found by this scan, '
            + nKnown + ' remembered'
          : '')
      + (mode === 'scan' && nFound
          ? '  ·  ' + nFound + ' found by this scan' : '')
      + (query ? '  ·  matching "' + query + '"' : '')
      + (avail === 'open' ? '  ·  only what opens here' : '')
      + (picked.size ? '  ·  ' + picked.size + ' selected' : '');
    renderPickBar();

    if (!visible.length) {
      host.appendChild(el('div', { class: 'tree-empty',
        text: sessions.length
          ? 'Nothing matches those filters.'
          : 'Nothing registered yet. Scan a data root and everything under '
            + 'it will be catalogued, whether or not you open it.' }));
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
          /* In a narrow gutter now, so it has to be short. The folder name
             is the long part and it is the part you rarely need, so it moves
             to the tooltip. */
          el('div', {
            class: 'mouse-label',
            title: (list[0].identity.mouse_folder || mk)
                   + '  ·  ' + list.length + ' session(s)',
          }, [
            el('strong', { text: mk }),
            el('span', { class: 'folder', text: list.length + ' sess' }),
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
    const remembered = !!s._remembered;
    return el('div', {
      class: 'sess-card' + (isPicked ? ' picked' : '')
           + (remembered ? ' remembered' : ' found'),
      title: remembered
        ? ((s.path || '(no path on this machine)')
           + '\n\nKnown to BARRY, but this scan has not found it.')
        : s.path,
      onclick: (e) => {
        if (!s.path) {
          toast('None of this recording\u2019s paths are on this machine.',
                'err', 6000);
          return;
        }
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
        el('span', { class: 'sc-sub',
                     text: i.start ? BARRY.when(i.start, 'second') : s.name }),
      ]),
      el('div', { class: 'sc-sub', text:
        (s.channels ? s.channels + ' ch · ' : '')
        + (s.fs ? Math.round(s.fs) + ' Hz · ' : '')
        + (s.duration_s ? fmtTime(s.duration_s) : '') }),
      el('div', { class: 'sc-flags' }, [
        /* Which hippocampus. On the card rather than behind a click,
           because pooling a left and a right recording without noticing is
           the kind of mistake that survives into a figure. */
        /* An extraction that did not go cleanly. Only shown when it did
           not: "Success: Clean extraction" on four hundred cards is noise,
           and the three that say "No CA1 SP channel" are the point. */
        (s.extraction_note && !/^success/i.test(s.extraction_note))
          ? el('span', {
              class: 'flagchip bad',
              title: s.extraction_note,
              text: 'extraction',
            }) : null,
        s.needs_processing ? el('span', {
          class: 'flagchip', title: 'The Toothy workbook has this one down '
                                  + 'as still needing processing',
          text: 'to process',
        }) : null,
        s.fissure_channel != null ? el('span', {
          class: 'flagchip hemi',
          title: 'Reference channels — ripple ' + s.ripple_channel
               + ', fissure ' + s.fissure_channel
               + ', hilus ' + s.hilus_channel,
          text: 'fis ' + s.fissure_channel,
        }) : null,
        s.hemisphere ? el('span', {
          class: 'flagchip hemi',
          title: 'Recorded in the ' + (s.hemisphere === 'L' ? 'left' : 'right')
               + ' hippocampus'
               + (s.hemisphere_source ? '\nfrom ' + s.hemisphere_source : ''),
          text: s.hemisphere === 'L' ? 'left' : 'right',
        }) : null,
        s.converted ? el('span', { class: 'flagchip mat', text: '.mat' }) : null,
        s.has_video ? el('span', { class: 'flagchip video', text: 'video' }) : null,
        s.has_tracking ? el('span', { class: 'flagchip', text: 'tracking' }) : null,
        badN ? el('span', { class: 'flagchip bad', text: badN + ' bad' }) : null,
        i.confidence !== 'high' ? el('span', { class: 'flagchip bad',
          text: 'id: ' + i.confidence }) : null,
        remembered ? el('span', {
          class: 'flagchip', title: 'From the registry, not from this scan',
          text: 'remembered',
        }) : null,
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
    $$('#sessModeSeg button').forEach((b) =>
      b.addEventListener('click', () => setMode(b.dataset.mode)));

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

    renderScanOpts();
    /* The nine pills are gone; the bar builds itself from FILTERS, so
       there is nothing left to wire up one at a time. */
    renderFilterBar();

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

  /* Two views of the same subject: what is on this drive, and what the lab
     has. Kept in one section because "the sessions" is one idea, and a
     twelfth rail entry for the other half of it would not help anyone. */
  let mode = 'scan';

  function setMode(next) {
    mode = next;
    const scan = $('#sessScanPad'), hk = $('#hkBody');
    if (scan) scan.classList.toggle('hidden', mode !== 'scan');
    if (hk) hk.classList.toggle('hidden', mode !== 'housekeeping');
    $$('#sessModeSeg button').forEach(
      (b) => b.classList.toggle('active', b.dataset.mode === mode));
    /* Re-drawn, because the mode is a question about the list and not
       only about the panels under it. This used to toggle two `hidden`
       classes and leave the list exactly as it was, so the local view
       showed the whole catalogue until something else happened to
       re-render.

       The line above the list is written by `renderTree`, which is also
       what counts the cards. */
    if (sessions.length) {
      renderFilterBar();
      renderTree();
    }
    for (const b of $$('#sessHealth, #sessCompare, #sessReveal, #sessScan')) {
      b.classList.toggle('hidden', mode !== 'scan');
    }
    if (mode === 'housekeeping' && BARRY.views.housekeeping) {
      BARRY.views.housekeeping.onShow();
    }
    BARRY.activity.log('sessions.mode', { mode });
  }

  return {
    init,
    picked: () => Array.from(picked),
    setMode,
    /* Forget that the registry has been read, so the next onShow reads it
       again. For web/_dev/motion.html, which checks that the skeleton is on
       screen during that read and gone after it -- and there is no way to
       watch a load that only ever happens once per page. */
    _forget: () => { knownLoaded = false; sessions = []; },
    /* What the scan will actually be told to do. For web/_dev/sessfilter.html:
       the settings moved out of two inputs and into module state, and a
       button that merely looks changed is not the same as a scan that is
       changed -- so the harness reads the state the scan reads. */
    _scanOpts: () => Object.assign({}, scanOpts),
    onShow: () => {
      if (mode === 'housekeeping' && BARRY.views.housekeeping) {
        BARRY.views.housekeeping.onShow();
      } else {
        renderRecents();
        // Open showing what BARRY already knows rather than an empty page.
        loadKnown();
      }
    },
  };
})();
