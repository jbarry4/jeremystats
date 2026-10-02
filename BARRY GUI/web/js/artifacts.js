/* ==========================================================================
   artifacts.js -- Jarvis Artifacts in Results.

   An artifact is a versioned thing a stage made for a later stage to read:
   a Circuit (one recording, one cue type, one kind), which a Drift averages.
   The store is backend/artifacts.py; this is where somebody finds one, reads
   where it came from, picks a version, names it, downloads it, and is told
   why it cannot be deleted.

   The registry is the contract other tools build against:

     BARRY.artifacts.register(kind, { title, icon, summary(record) -> string,
                                      render(host, record, payload, version) })
     BARRY.artifacts.action(kind, { id, label, title, run(record, version) })
     BARRY.artifacts.list(opts) / get(id) / payload(id, v) / open(id, v)

   A kind with no viewer is still readable: its payload is shown as a
   collapsible JSON tree, never as "No preview". Results owns everything
   that is about the artifact rather than its contents -- listing, versions,
   nickname, provenance, citations, download and delete.
   ========================================================================== */
'use strict';

BARRY.artifacts = (function () {
  const viewers = {};          // kind -> { title, icon, summary, render }
  const actions = {};          // kind -> [{ id, label, title, run }]
  const KIND_TITLES = { circuit: 'Circuits', drift: 'Drifts' };

  let host = null;             // the pane Results handed us, while shown
  let rows = null;             // summaries, null until read
  let failed = null;           // the sentence of the last failed read
  let sel = null;              // selected artifact id
  let selV = null;             // selected version id (null = current)
  let query = '';
  const payloads = new Map();  // "<id>:<version id>" -> payload response

  /* ---------------- the registry ---------------- */
  function register(kind, spec) {
    if (!kind || !spec) throw new Error('register(kind, spec)');
    viewers[kind] = Object.assign({}, spec);
    // Registered after the pane was drawn: draw it again with the viewer.
    if (host && host.isConnected) paint(host);
    return viewers[kind];
  }

  function action(kind, spec) {
    if (!kind || !spec || !spec.id || typeof spec.run !== 'function') {
      throw new Error('action(kind, { id, label, run })');
    }
    const list = (actions[kind] = (actions[kind] || [])
      .filter((a) => a.id !== spec.id));
    list.push(Object.assign({}, spec));
    if (host && host.isConnected && sel) paintDetail();
    return spec;
  }

  function unregister(kind) { delete viewers[kind]; }
  function unaction(kind, id) {
    actions[kind] = (actions[kind] || []).filter((a) => a.id !== id);
  }

  /* ---------------- reading ---------------- */
  async function list(opts) {
    const q = new URLSearchParams();
    if (opts && opts.kind) q.set('kind', opts.kind);
    if (opts && opts.gid) q.set('gid', opts.gid);
    const res = await api('/api/artifacts' + (q.toString() ? '?' + q : ''));
    return res.artifacts || [];
  }

  async function getFull(id) {
    return api('/api/artifacts/' + encodeURIComponent(id));
  }

  async function get(id) {
    return (await getFull(id)).artifact;
  }

  async function payload(id, v) {
    const key = id + ':' + (v == null ? '' : v);
    if (v != null && payloads.has(key)) return payloads.get(key);
    const res = await api('/api/artifacts/' + encodeURIComponent(id)
      + '/payload' + (v == null ? '' : '?v=' + encodeURIComponent(v)));
    const out = { payload: res.payload, version: res.version,
                  version_id: res.version_id, digest: res.digest };
    payloads.set(id + ':' + res.version_id, out);
    return out;
  }

  /* Open one in Results' artifact viewer. `v` is a version number or a
     version id; a number two machines both minted is resolved to nothing
     rather than guessed, and the list shows both. */
  function open(id, v) {
    sel = id;
    selV = v == null ? null : String(v);
    // Read again: the one being opened may have been made a moment ago.
    if (!(rows || []).some((r) => r.id === id)) rows = null;
    if (typeof setView === 'function') setView('results');
    const res = BARRY.views && BARRY.views.results;
    if (res && res.mode) res.mode('artifacts');
    else if (host && host.isConnected) paint(host);
    return true;
  }

  /* ---------------- words ---------------- */
  const titleOf = (kind) => (viewers[kind] && viewers[kind].title)
    || KIND_TITLES[kind] || (kind.charAt(0).toUpperCase() + kind.slice(1) + 's');

  const nounOf = (kind) => ({ circuit: 'circuit', drift: 'drift' }[kind] || kind);

  function provLine(ver) {
    if (!ver) return 'no versions';
    const code = [ver.app_version, ver.commit ? '(' + ver.commit + ')' : null]
      .filter(Boolean).join(' ');
    return [ver.by ? 'by ' + ver.by : 'by nobody recorded',
            ver.at ? BARRY.when(ver.at, 'minute') : null,
            ver.machine ? 'on ' + ver.machine : null,
            code || null].filter(Boolean).join('  ·  ');
  }

  function groupOf(r) {
    const s = r.subject || {};
    if (r.kind === 'circuit') {
      return [s.project || 'Unfiled',
              s.mouse != null ? 'r' + s.mouse : null,
              s.session != null ? 's' + s.session : null]
        .filter(Boolean).join(' ') || s.session_label || 'Unfiled';
    }
    return null;
  }

  function hay(r) {
    const s = r.subject || {};
    return [r.name, r.nickname, r.kind, s.project, s.mouse != null ? 'r' + s.mouse : '',
            s.session_label, s.cue_type, s.window_kind, r.id]
      .join(' ').toLowerCase();
  }

  /* ---------------- painting ---------------- */
  async function paint(h) {
    host = h;
    host.innerHTML = '';
    const wrap = el('div', { class: 'art-wrap' });
    const side = el('div', { class: 'art-list' });
    const detail = el('div', { class: 'art-detail', id: 'artDetail' });
    wrap.appendChild(side);
    wrap.appendChild(detail);
    host.appendChild(wrap);

    if (rows === null) {
      const bones = BARRY.skeleton.into(side, 'row', 5);
      detail.appendChild(loader('Reading artifacts', 'Every circuit and drift this computer knows'));
      try {
        rows = await list();
        failed = null;
      } catch (e) {
        failed = e.message;
        reportClientError('artifacts.list', e.message, e.stack);
      } finally {
        bones();
      }
      if (!host || host !== h || !h.isConnected) return;
      detail.innerHTML = '';
    }
    paintList(side);
    paintDetail();
  }

  function reload() {
    rows = null;
    if (host && host.isConnected) paint(host);
  }

  /* New artifacts appear while you look.

     A batch files a circuit every minute or so, and the ask (2026-09-29)
     was that each one be openable in Results as soon as it is filed -- not
     after a reload. `reload()` is the wrong tool for that: it repaints the
     detail pane and puts up a skeleton, which would blink under somebody
     reading an artifact every time another landed. So this asks for the
     list quietly, and redraws ONLY the list, ONLY when something in it
     changed (an id, a version, a nickname), keeping the scroll position.

     Every 10 s, and only while the list is actually on screen and the tab
     is visible -- a timer for a view nobody is looking at is just requests.
     It also skips a tick while somebody is typing in the list, because
     redrawing the search field under the caret loses the focus. */
  const REFRESH_MS = 10000;
  const listKey = (rs) => (rs || []).map((r) => r.id + ':' + (r.version || '')
    + ':' + (r.nickname || '') + ':' + (r.deleted ? 'x' : '')).join('|');
  let refreshing = false;
  async function refreshQuietly() {
    if (refreshing || rows === null || failed) return;
    const side = host && host.querySelector('.art-list');
    if (!side || !side.isConnected || side.offsetParent === null) return;
    if (document.hidden) return;
    if (document.activeElement && side.contains(document.activeElement)
        && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
    refreshing = true;
    try {
      const got = await list();
      if (listKey(got) === listKey(rows)) return;
      const top = side.scrollTop;
      rows = got;
      paintList(side);
      side.scrollTop = top;
    } catch (e) {
      /* A missed refresh costs nothing; the next tick asks again. */
    } finally {
      refreshing = false;
    }
  }
  setInterval(refreshQuietly, REFRESH_MS);
  /* And at once when a stage says it filed something. */
  window.addEventListener('barry:artifact', () => { refreshQuietly(); });

  function paintList(side) {
    side = side || (host && host.querySelector('.art-list'));
    if (!side) return;
    side.innerHTML = '';
    if (failed) {
      side.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'The artifacts could not be read: ' + failed
                        + ' Rescan to try again.' }),
        el('button', { class: 'btn ghost sm', text: 'Read again', onclick: reload }),
      ]));
      return;
    }
    const all = rows || [];
    if (!all.length) {
      side.appendChild(el('div', { class: 'empty-state' }, [
        el('svg', { viewBox: '0 0 24 24',
          html: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="7" r="2.5"/>'
              + '<circle cx="12" cy="18" r="2.5"/><path d="M8 7l7 0M7 8l4 8M17 9l-4 7"/>' }),
        el('p', { text: 'No artifacts yet. Run a Circuit in ToolKit → The Arc '
                        + 'to make one; a Drift is then made from circuits.' }),
      ]));
      return;
    }

    side.appendChild(BARRY.ui.searchField({
      value: query,
      placeholder: 'Type a name, nickname, rat or cue…',
      oninput: (e) => { query = e.target.value; keepFocus(() => paintList()); },
    }));

    const q = query.trim().toLowerCase();
    const shown = all.filter((r) => !q || q.split(/\s+/).every((t) => hay(r).includes(t)));
    side.appendChild(el('p', { class: 'hint art-count',
      text: shown.length + ' of ' + all.length + ' artifact'
            + (all.length === 1 ? '' : 's') }));
    if (!shown.length) {
      side.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'Nothing matches “' + query + '”. Clear the '
                        + 'search to see all ' + all.length + '.' }),
      ]));
      return;
    }

    const kinds = Array.from(new Set(shown.map((r) => r.kind)))
      .sort((a, b) => (a === 'circuit' ? -1 : b === 'circuit' ? 1 : a.localeCompare(b)));
    for (const kind of kinds) {
      const mine = shown.filter((r) => r.kind === kind);
      side.appendChild(el('div', { class: 'section-label art-kind' }, [
        titleOf(kind), el('span', { class: 'art-n', text: String(mine.length) }),
      ]));
      const groups = new Map();
      for (const r of mine) {
        const g = groupOf(r) || '';
        if (!groups.has(g)) groups.set(g, []);
        groups.get(g).push(r);
      }
      const names = Array.from(groups.keys()).sort((a, b) =>
        a.localeCompare(b, undefined, { numeric: true }));
      for (const g of names) {
        if (g) side.appendChild(el('div', { class: 'art-group', text: g }));
        const list = groups.get(g).sort((a, b) =>
          String(a.nickname || a.name).localeCompare(String(b.nickname || b.name),
                                                     undefined, { numeric: true }));
        for (const r of list) side.appendChild(rowOf(r));
      }
    }
  }

  function rowOf(r) {
    const cur = r.current || null;
    let extra = null;
    const v = viewers[r.kind];
    if (v && typeof v.summary === 'function') {
      try { extra = v.summary(r); } catch (e) {
        reportClientError('artifacts.summary:' + r.kind, e.message, e.stack);
      }
    }
    return el('button', {
      class: 'art-row' + (r.id === sel ? ' active' : ''),
      'data-id': r.id,
      title: r.name,
      onclick: () => { sel = r.id; selV = null; paintList(); paintDetail(); },
    }, [
      el('span', { class: 'art-nick', text: r.nickname || r.name }),
      r.nickname ? el('span', { class: 'art-name', text: r.name }) : null,
      el('span', { class: 'art-meta' }, [
        el('span', { class: 'art-vn',
                     text: r.n_versions + ' version' + (r.n_versions === 1 ? '' : 's') }),
        r.cited_active ? el('span', { class: 'art-vn cited',
                                      text: 'cited ' + r.cited_active + '×' }) : null,
        el('span', { class: 'art-prov', text: provLine(cur) }),
        BARRY.syncState ? BARRY.syncState.mark('artifacts', r.id) : null,
      ].filter(Boolean)),
      extra ? el('span', { class: 'art-extra', text: String(extra) }) : null,
    ]);
  }

  /* ---------------- the detail pane ---------------- */
  let paintSeq = 0;

  async function paintDetail() {
    const pane = host && host.querySelector('#artDetail');
    if (!pane) return;
    const seq = ++paintSeq;
    if (!sel) {
      pane.innerHTML = '';
      if ((rows || []).length) {
        pane.appendChild(el('div', { class: 'empty-state' }, [
          el('p', { text: 'Pick an artifact on the left to see its versions, '
                          + 'where each came from, and what cites it.' }),
        ]));
      }
      return;
    }
    pane.innerHTML = '';
    pane.appendChild(loader('Reading the artifact'));
    let full;
    try {
      full = await getFull(sel);
    } catch (e) {
      if (seq !== paintSeq) return;
      pane.innerHTML = '';
      pane.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: e.message }),
      ]));
      reportClientError('artifacts.get', e.message, e.stack);
      return;
    }
    if (seq !== paintSeq) return;
    const rec = full.artifact;
    const cites = full.cited_by || [];
    const vers = (rec.versions || []).slice().sort((a, b) =>
      (b.v - a.v) || String(b.at || '').localeCompare(String(a.at || '')));
    let ver = null;
    if (selV != null) {
      ver = vers.find((x) => x.id === selV)
        || (/^v?\d+$/.test(selV)
            ? (() => {
                const hit = vers.filter((x) => String(x.v) === selV.replace(/^v/, ''));
                return hit.length === 1 ? hit[0] : null;
              })()
            : null);
    }
    ver = ver || rec.current || vers[0] || null;

    pane.innerHTML = '';
    pane.appendChild(headOf(rec));
    pane.appendChild(nicknameField(rec));
    pane.appendChild(versionPicker(rec, vers, ver));
    if (ver) {
      pane.appendChild(el('div', { class: 'section-label', text: 'Where v' + ver.v + ' came from' }));
      pane.appendChild(provOf(ver));
      const params = paramsOf(ver.params);
      if (params) {
        pane.appendChild(el('div', { class: 'section-label', text: 'Settings' }));
        pane.appendChild(params);
      }
      pane.appendChild(el('div', { class: 'section-label', text: 'Made from' }));
      pane.appendChild(inputsOf(ver.inputs));
      pane.appendChild(el('div', { class: 'section-label', text: 'Cited by' }));
      pane.appendChild(citesOf(cites, ver));
    }
    const slot = el('div', { class: 'art-view', 'data-kind': rec.kind });
    pane.appendChild(el('div', { class: 'section-label', text: 'Contents' }));
    pane.appendChild(slot);
    pane.appendChild(actionBar(rec, ver, cites));
    if (ver) fillView(slot, rec, ver, seq);
  }

  function headOf(rec) {
    return el('div', { class: 'art-head' }, [
      el('div', { class: 'art-titles' }, [
        el('h3', { class: 'art-nick', text: rec.nickname || rec.name }),
        rec.nickname ? el('span', { class: 'art-name', text: rec.name }) : null,
      ]),
      el('span', { class: 'art-vn', text: nounOf(rec.kind) }),
    ]);
  }

  function nicknameField(rec) {
    const input = el('input', {
      type: 'text', value: rec.nickname || '', maxlength: '160',
      placeholder: 'Type a name of your own for it…',
      onkeydown: (e) => { if (e.key === 'Enter') save(); },
    });
    const say = el('span', { class: 'hint' });
    async function save() {
      try {
        await apiPost('/api/artifacts/' + encodeURIComponent(rec.id) + '/nickname',
                      { nickname: input.value });
        const r = (rows || []).find((x) => x.id === rec.id);
        if (r) r.nickname = input.value.trim() || null;
        paintList();
        paintDetail();
        toast(input.value.trim() ? 'Nickname saved.' : 'Nickname cleared.', 'ok');
      } catch (e) {
        say.textContent = e.message;
        reportClientError('artifacts.nickname', e.message, e.stack);
      }
    }
    return el('div', { class: 'art-nickfield' }, [
      el('div', { class: 'section-label', text: 'Nickname' }),
      el('div', { class: 'art-inline' }, [
        input,
        el('button', { class: 'btn ghost sm', text: 'Save nickname',
                       title: 'Shown above the automatic name, everywhere. Empty '
                            + 'goes back to the automatic name.',
                       onclick: save }),
      ]),
      say,
    ]);
  }

  function versionPicker(rec, vers, ver) {
    const dupes = {};
    for (const x of vers) dupes[x.v] = (dupes[x.v] || 0) + 1;
    return el('div', {}, [
      el('div', { class: 'section-label', text: 'Versions' }),
      el('div', { class: 'art-versions' }, vers.map((x) => el('button', {
        class: 'pill' + (ver && x.id === ver.id ? ' active' : ''),
        'data-vid': x.id,
        title: provLine(x) + (x.here === false ? '\nIts payload is not on this computer yet.' : '')
             + (dupes[x.v] > 1 ? '\nTwo machines both made a v' + x.v + '; this one is ' + x.id + '.' : ''),
        onclick: () => { selV = x.id; paintDetail(); },
      }, [
        'v' + x.v + (dupes[x.v] > 1 ? ' (' + (x.machine || x.id) + ')' : ''),
        el('span', { class: 'art-vdate', text: x.at ? BARRY.when(x.at, 'stamp') : '' }),
        (x.confirmed || []).length ? el('span', { class: 'art-vdate',
          text: '✓' + x.confirmed.length }) : null,
        x.here === false ? el('span', { class: 'art-vdate', text: 'elsewhere' }) : null,
      ]))),
    ]);
  }

  function provOf(ver) {
    const kv = el('dl', { class: 'kv' });
    const add = (k, v) => {
      if (v === null || v === undefined || v === '') return;
      kv.appendChild(el('dt', { text: k }));
      kv.appendChild(el('dd', { text: String(v) }));
    };
    add('Made by', ver.by || 'nobody recorded');
    add('When', ver.at ? BARRY.when(ver.at, 'second') : null);
    add('On', ver.machine);
    add('Version', [ver.app_version, ver.commit && '(' + ver.commit + ')'].filter(Boolean).join(' '));
    add('Digest', ver.digest);
    add('Version id', ver.id);
    add('Note', ver.note);
    const conf = ver.confirmed || [];
    if (conf.length) {
      const last = conf[conf.length - 1];
      add('Reproduced', conf.length + ' time' + (conf.length === 1 ? '' : 's')
          + ', last ' + [last.by, last.at ? BARRY.when(last.at, 'minute') : null,
                         last.machine ? 'on ' + last.machine : null].filter(Boolean).join(' '));
    }
    const n = ver.n_summary || {};
    const ns = Object.keys(n).filter((k) => n[k] !== null && n[k] !== undefined)
      .map((k) => k.replace(/_/g, ' ') + ' ' + n[k]).join(', ');
    add('Holds', ns);
    return kv;
  }

  function paramsOf(p) {
    const keys = Object.keys(p || {}).sort();
    if (!keys.length) return null;
    return el('table', { class: 'art-params' }, [
      el('tbody', {}, keys.map((k) => el('tr', {}, [
        el('td', { text: k }),
        el('td', { text: Array.isArray(p[k]) ? p[k].join(', ')
                   : (p[k] && typeof p[k] === 'object') ? JSON.stringify(p[k])
                   : String(p[k]) }),
      ]))),
    ]);
  }

  function inputsOf(inputs) {
    const list = inputs || [];
    if (!list.length) {
      return el('p', { class: 'hint', text: 'This version does not say what it '
                                          + 'was made from.' });
    }
    return el('ul', { class: 'art-refs' }, list.map((ref) => {
      if (ref && ref.kind === 'artifact') {
        const known = (rows || []).find((x) => x.id === ref.id);
        return el('li', {}, [
          ref.side ? el('span', { class: 'art-vn', text: ref.side }) : null,
          el('a', { href: '#', class: 'art-link', 'data-ref': ref.id,
                    text: ((known && (known.nickname || known.name)) || ref.name || ref.id)
                          + ' · v' + ref.version,
                    title: 'Open that version' + (ref.digest ? ' (digest ' + ref.digest + ')' : ''),
                    onclick: (e) => { e.preventDefault(); open(ref.id, ref.version_id || ref.version); } }),
        ]);
      }
      if (ref && ref.kind === 'bank') {
        return el('li', { text: 'Event Bank entry ' + ref.entry
                                + (ref.version != null ? ' v' + ref.version : '') });
      }
      return el('li', { text: JSON.stringify(ref) });
    }));
  }

  function citesOf(cites, ver) {
    const mine = cites.filter((c) => c.version_id ? c.version_id === ver.id : c.version === ver.v);
    const others = cites.length - mine.length;
    if (!mine.length) {
      return el('p', { class: 'hint', text: 'Nothing cites v' + ver.v + '.'
        + (others ? ' ' + others + ' citation' + (others === 1 ? '' : 's')
                    + ' of other versions.' : '') });
    }
    return el('ul', { class: 'art-refs' }, mine.map((c) => el('li', {}, [
      el('a', { href: '#', class: 'art-link', 'data-ref': c.by_id,
                text: (c.by_nickname || c.by_name || ('artifact ' + c.by_id
                       + ' (not on this computer yet)')) + ' · v' + c.by_version,
                onclick: (e) => { e.preventDefault(); open(c.by_id, c.by_version); } }),
    ])));
  }

  function actionBar(rec, ver, cites) {
    const reg = actions[rec.kind] || [];
    const bar = el('div', { class: 'art-actions' });
    bar.appendChild(el('button', {
      class: 'btn ghost sm danger', text: 'Delete',
      title: cites.length ? 'Cited by ' + cites.length + ' — it cannot be '
                            + 'deleted until they are' : 'Delete this ' + nounOf(rec.kind),
      onclick: () => del(rec),
    }));
    bar.appendChild(el('div', { class: 'spacer' }));
    const dl = () => el('button', {
      class: reg.length ? 'btn ghost sm' : 'btn sm', text: 'Download as JSON',
      title: 'The payload of v' + (ver ? ver.v : '?') + ', exactly as stored',
      disabled: ver ? null : 'disabled',
      onclick: () => download(rec, ver),
    });
    bar.appendChild(dl());
    /* One primary per surface, and it is the last one: a registered action
       (Drift's "Use in Drift") is the thing this pane is for when there is
       one, so it takes the slot and Download steps back. */
    reg.forEach((a, i) => bar.appendChild(el('button', {
      class: i === reg.length - 1 ? 'btn sm' : 'btn ghost sm',
      text: a.label || a.id, title: a.title || null, 'data-action': a.id,
      onclick: () => {
        try { a.run(rec, ver); } catch (e) {
          reportClientError('artifacts.action:' + a.id, e.message, e.stack);
          toast(e.message, 'err');
        }
      },
    })));
    return bar;
  }

  async function download(rec, ver) {
    try {
      const got = await payload(rec.id, ver.id);
      const blob = new Blob([JSON.stringify(got.payload, null, 1)],
                            { type: 'application/json' });
      const base = String(rec.nickname || rec.name || rec.id)
        .replace(/[^\w .\-]+/g, '_').trim().slice(0, 80) || rec.id;
      const a = el('a', { href: URL.createObjectURL(blob),
                          download: base + ' v' + got.version + ' ' + got.digest + '.json' });
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    } catch (e) {
      toast(e.message, 'err');
      reportClientError('artifacts.download', e.message, e.stack);
    }
  }

  function del(rec) {
    return BARRY.confirm(
      'Delete this ' + nounOf(rec.kind) + '?',
      '“' + (rec.nickname || rec.name) + '” leaves the list. Its '
      + 'versions’ payloads stay on disk. A version a Drift cites cannot '
      + 'be deleted, and if one does you will be told which.',
      'Delete', true,
      async () => {
        await apiPost('/api/artifacts/' + encodeURIComponent(rec.id) + '/delete', {});
        rows = (rows || []).filter((x) => x.id !== rec.id);
        sel = null; selV = null;
        paintList();
        paintDetail();
        toast('Deleted.', 'ok');
      });
  }

  /* ---------------- the viewer slot ---------------- */
  async function fillView(slot, rec, ver, seq) {
    slot.appendChild(loader('Reading v' + ver.v, 'digest ' + ver.digest));
    let got;
    try {
      got = await payload(rec.id, ver.id);
    } catch (e) {
      if (seq !== paintSeq) return;
      slot.innerHTML = '';
      slot.appendChild(el('p', { class: 'hint', text: e.message }));
      return;
    }
    if (seq !== paintSeq || !slot.isConnected) return;
    slot.innerHTML = '';
    const v = viewers[rec.kind];
    if (v && typeof v.render === 'function') {
      try {
        v.render(slot, rec, got.payload, ver);
        slot.setAttribute('data-viewer', 'registered');
        return;
      } catch (e) {
        reportClientError('artifacts.render:' + rec.kind, e.message, e.stack);
        slot.innerHTML = '';
        slot.appendChild(el('p', { class: 'hint',
          text: 'The ' + nounOf(rec.kind) + ' viewer failed (' + e.message
                + '), so here is what it holds, as data.' }));
      }
    }
    slot.setAttribute('data-viewer', 'json');
    slot.appendChild(jsonTree(got.payload));
  }

  /* A readable, collapsible JSON view. Children are built when a node is
     opened, not before: a circuit has a few thousand leaves and nobody reads
     them all. */
  function jsonTree(value) {
    const root = el('div', { class: 'art-json' });
    root.appendChild(node(null, value, 0));
    return root;
  }

  function leaf(v) {
    if (v === null) return el('span', { class: 'j-null', text: 'null' });
    if (typeof v === 'string') return el('span', { class: 'j-str', text: JSON.stringify(v) });
    if (typeof v === 'number') return el('span', { class: 'j-num', text: String(v) });
    if (typeof v === 'boolean') return el('span', { class: 'j-bool', text: String(v) });
    return el('span', { text: String(v) });
  }

  function node(key, v, depth) {
    const isObj = v && typeof v === 'object';
    const label = key === null ? null : el('span', { class: 'j-key', text: key + ': ' });
    if (!isObj) return el('div', { class: 'j-row' }, [label, leaf(v)]);
    const arr = Array.isArray(v);
    const keys = arr ? v.map((_x, i) => i) : Object.keys(v);
    const det = el('details', { class: 'j-node' });
    det.appendChild(el('summary', {}, [
      label,
      el('span', { class: 'j-meta', text: arr ? '[' + keys.length + ']'
                                              : '{' + keys.length + '}' }),
    ]));
    let built = false;
    const build = () => {
      if (built) return;
      built = true;
      const kids = el('div', { class: 'j-kids' });
      for (const k of keys) kids.appendChild(node(String(k), v[k], depth + 1));
      det.appendChild(kids);
    };
    det.addEventListener('toggle', () => { if (det.open) build(); });
    if (depth < 1) { det.open = true; build(); }
    return det;
  }

  return {
    register, action, list, get, payload, open,
    // Results' side of it, and the harness's.
    paint, reload, unregister, unaction,
    viewers: () => Object.keys(viewers),
    actionsFor: (kind) => (actions[kind] || []).map((a) => a.id),
    selected: () => ({ id: sel, version: selV }),
    rows: () => rows,
  };
})();
