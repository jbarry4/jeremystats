/* ==========================================================================
   dspcamany.js -- X-ray Many (2026-11-07).

   What was asked: "everything that went through the PCA analysis should be
   preprocessed in the Many, ready for me to come in and select the border
   for. A grid of the average CSD where for each I can draw the line / click
   one sample, and run one by one or run all ... For each one indicate if
   separation was possible, and how powerful the sinks were, then bank
   that."

   THE SHAPE
   A row of FOLDERS. A folder is the set of recordings a Root Canal workflow
   run kept as verified ("Verified DS 5%", "Verified DS 10%"); the server
   makes those two on the first visit. Under it the folder's global
   parameters, one line for reading what is not read yet, and the grid: one
   tile per recording, its average CSD (the read's shank mean, 5-100 Hz,
   mains out -- the same picture Single drags on).

   On a tile, DRAG for a depth x time box, or CLICK for one time sample
   (keeping the box's depth, or the automatic depth when there is none).
   The box is a shared preference, `dspca_many_boxes`, so a colleague sees
   it. Run fits that one recording on the server and saves the answer as a
   versioned X-ray bundle; Run all does every tile with a read, in turn.

   WHAT IS NOT HERE
   Every number on a tile is the server's: counts, the separation verdict
   and its delta-BIC, the sinks and their unit. Nothing is worked out in the
   browser except the plain-words ratio between two sinks the server sent.

   Mounted by dspca.js when the run bar says Many. The root node is built
   once and put back on every render of the panel, so a refit or a poll
   never rebuilds the grid: tiles change in place.
   ========================================================================== */
'use strict';

BARRY.dspcaMany = (function () {
  const FOLD_KEY = 'dspca_many_folders';
  const BOX_KEY = 'dspca_many_boxes';
  const PAR_KEY = 'dspca_many_params';
  // Which folder is open: this viewer's convenience, not a shared fact.
  const PICK_KEY = 'barry.dspcamany.folder';

  /* The global parameters, Single's defaults. `nclasses` is held at two:
     the question is DS1 against DS2, and Single forces it too. */
  const DEFAULTS = {
    method: 'delta', rule: 'tort', features: 'minmax', notch: true,
    min_sep: 5, gap_weight: 1, nclasses: 2,
  };
  // The labels Single uses, so the two halves say the same words.
  const METHODS = [
    ['delta', 'delta only', 'One number per event, the sink gap, and '
      + 'k-means partitions that line. The boundary is a threshold you can '
      + 'read off the axis.'],
    ['pca_gap', 'PCA + gap', 'The laminar profile, rotated, with the sink '
      + 'gap as one more column.'],
    ['pca', 'PCA, no gap', 'The laminar profile and nothing else.'],
  ];
  const RULES = [
    ['tort', 'tortlab', 'the main sink above the main source; the '
      + 'shallower one is DS1'],
    ['sink', 'Toothy', 'argmin of each class’s mean profile'],
    ['sources', 'source peaks', 'the most prominent source peak'],
    ['anatomy', 'anatomy', 'against the labelled hilus'],
  ];
  const FEATURES = [
    ['minmax', 'min-max (Toothy)', 'Each event scaled 0-1 over the patch.'],
    ['sign', 'sign ±1', 'Source or sink per contact, magnitudes thrown away.'],
    ['sign_dead', 'sign + deadband', 'Sign, with anything within 15% of the '
      + 'patch’s peak counted as neither.'],
  ];
  // Single's class inks (dspca.js colorOf), for the sink ticks.
  const CLS_INK = ['#1a7f37', '#7b3fa0', '#b8620a', '#1f6feb', '#a3155f'];
  const VERDICT = {
    yes: ['separable', 'good'],
    weak: ['weak', 'warn'],
    no: ['not separable', null],
    too_few: ['too few', null],
  };
  const PAD = { l: 26, r: 6, t: 4, b: 14 };
  const TILE_H = 180;

  const S = {
    root: null, nodes: {}, ctx: null,
    folders: null, error: null, loadedAt: 0, loading: null,
    cur: null, showArchived: false,
    job: null, poll: null, jobGen: 0,
    runAll: null,          // {of, done, stop} while Run all is going
    built: null,           // the folder the grid was built for
  };
  const tiles = new Map();     // gid -> tile record, for the open folder
  const rasters = new Map();   // rasterKey -> {got} | {error} | {pending}
  const lastGood = new Map();  // gid -> {read, r}: the last picture drawn
  const versions = new Map();  // artifact id -> [versions] | 'pending'
  const imgs = new Map();      // gid -> {src, img}
  let rasterQ = [];
  let rasterBusy = 0;
  let ro = null;

  const who = () => (BARRY.profile && BARRY.profile.who
                     && BARRY.profile.who()) || '';
  const now = () => new Date().toISOString();
  const prefMap = (k) => {
    const v = BARRY.prefs && BARRY.prefs.get ? BARRY.prefs.get(k, {}) : {};
    return v && typeof v === 'object' && !Array.isArray(v) ? v : {};
  };
  const mergeKey = (k, id, v) => BARRY.prefs.mergeKey(k, id, v);

  /* ==================================================================
     Mounting
     ================================================================== */
  /* Put the panel into `host`. The same root node every time: dspca.js
     empties its host on each render, and appending this node back is what
     keeps the tiles, their canvases and anything half-dragged as they
     were. `ctx.toSingle()` switches the run bar back to one;
     `ctx.fresh` says the run bar has just come to Many, which is when a
     bundle Single saved meanwhile is looked for. Not on every render:
     X-ray re-renders for its own reasons, and a reload each time would
     be a request per render. */
  function mount(host, ctx) {
    if (ctx) S.ctx = ctx;
    if (!S.root) {
      S.root = el('div', { class: 'xm' });
      try {
        if (window.ResizeObserver) {
          ro = new ResizeObserver(() => requestAnimationFrame(drawAll));
          ro.observe(S.root);
        }
      } catch (e) { /* drawn on the next update instead */ }
    }
    if (host && S.root.parentNode !== host) host.appendChild(S.root);
    if (!S.folders && !S.loading) {
      build();
      load();
    } else if (S.folders && ctx && ctx.fresh && !S.loading) {
      // Back from Single, where a bundle may have been saved. Quietly.
      load();
    }
    requestAnimationFrame(drawAll);
    return S.root;
  }

  async function load() {
    const mine = ++S.jobGen;
    S.loading = (async () => {
      let got;
      try {
        got = await api('/api/dspca/many');
      } catch (e) {
        if (mine !== S.jobGen) return;
        S.error = e.message;
        S.loading = null;
        build();
        return;
      }
      // Reset, or a newer load, while this one was out.
      if (mine !== S.jobGen) return;
      S.loading = null;
      S.error = null;
      S.loadedAt = Date.now();
      const first = !S.folders;
      S.folders = got.folders || [];
      // Kept when it is still there to show: a folder just made is named
      // here before it exists in the list.
      if (!S.cur || !visible().some((f) => f.id === S.cur)) S.cur = pickFirst();
      // A different folder from the one on screen is a new grid; the
      // same one is told what changed.
      if (first || !S.nodes.grid || S.built !== S.cur) build();
      else update();
    })();
    return S.loading;
  }

  function pickFirst() {
    let want = null;
    try { want = localStorage.getItem(PICK_KEY); } catch (e) { /* none */ }
    const vis = visible();
    if (want && vis.some((f) => f.id === want)) return want;
    return vis.length ? vis[0].id : null;
  }

  function folderOf(id) {
    return (S.folders || []).find((f) => f.id === id) || null;
  }
  const cur = () => folderOf(S.cur);

  /* Archived as the shared preference says, where this page has written
     it; else as the server sent it. */
  function archivedOf(f) {
    const p = prefMap(FOLD_KEY)[f.id];
    return p && 'archived' in p ? !!p.archived : !!f.archived;
  }
  function visible() {
    return (S.folders || []).filter((f) => S.showArchived || !archivedOf(f));
  }

  function paramsOf(fid) {
    const f = folderOf(fid) || {};
    const p = prefMap(PAR_KEY)[fid];
    return Object.assign({}, DEFAULTS, f.params || {}, p || {}, { nclasses: 2 });
  }

  function boxOf(fid, gid) {
    const all = prefMap(BOX_KEY);
    const k = fid + '|' + gid;
    if (k in all) return all[k] || null;
    const m = memberOf(gid);
    return (m && m.box) || null;
  }

  function memberOf(gid) {
    const f = cur();
    return f ? (f.members || []).find((m) => m.gid === gid) || null : null;
  }
  const readable = (m) => !!(m && m.read && m.read_here);

  /* ==================================================================
     The page
     ================================================================== */
  function build() {
    if (!S.root) return;
    S.root.innerHTML = '';
    S.nodes = {};
    tiles.clear();
    if (S.error && !S.folders) {
      S.root.appendChild(el('div', { class: 'card' }, [
        el('p', { class: 'hint warn-line', text:
          'Could not load the X-ray Many folders: ' + S.error }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Try again',
                          onclick: () => { S.error = null; build(); load(); } }),
      ]));
      return;
    }
    if (!S.folders) {
      S.root.appendChild(el('div', { class: 'card dp-load' }, [
        loader('Opening the folders', 'every recording a Root Canal '
               + 'workflow kept, and what X-ray has done with each'),
      ]));
      return;
    }
    S.nodes.bar = folderBar();
    S.root.appendChild(S.nodes.bar);
    const f = cur();
    if (!f) {
      S.root.appendChild(el('div', { class: 'card' }, [
        el('p', { class: 'hint', text: S.folders.length
          ? 'Every folder is archived. Show archived to put one back.'
          : 'No folders yet. Make one from a Root Canal workflow that has '
            + 'run.' }),
      ]));
      return;
    }
    S.built = f.id;
    S.nodes.params = paramsCard(f);
    S.nodes.job = jobCard(f);
    S.nodes.gridHead = gridHead(f);
    S.nodes.grid = el('div', { class: 'xm-grid' });
    S.root.appendChild(S.nodes.params);
    S.root.appendChild(S.nodes.job);
    S.root.appendChild(el('div', { class: 'card xm-gridcard' }, [
      S.nodes.gridHead, S.nodes.grid,
    ]));
    for (const m of f.members || []) {
      const t = tileOf(m);
      S.nodes.grid.appendChild(t.node);
    }
    requestAnimationFrame(drawAll);
    (f.members || []).forEach((m) => { wantRaster(m); wantVersions(m); });
  }

  /* After a reload: the same tiles, told what changed. A member the
     folder did not have before gets a tile; one it no longer has loses
     its tile. */
  function update() {
    const f = cur();
    if (!f || !S.nodes.grid || S.built !== f.id) { build(); return; }
    put('bar', folderBar());
    put('params', paramsCard(f));
    put('job', jobCard(f));
    put('gridHead', gridHead(f));
    const want = new Set((f.members || []).map((m) => m.gid));
    for (const [gid, t] of Array.from(tiles.entries())) {
      if (!want.has(gid)) { t.node.remove(); tiles.delete(gid); }
    }
    let prev = null;
    for (const m of f.members || []) {
      let t = tiles.get(m.gid);
      if (!t) {
        t = tileOf(m);
        if (prev) prev.node.after(t.node);
        else S.nodes.grid.prepend(t.node);
      } else {
        t.m = m;
        fillTile(t);
      }
      prev = t;
      wantRaster(m);
      wantVersions(m);
    }
    requestAnimationFrame(drawAll);
  }

  function put(name, node) {
    const old = S.nodes[name];
    if (old && old.parentNode) old.replaceWith(node);
    S.nodes[name] = node;
  }

  function switchTo(fid) {
    if (fid === S.cur) return;
    S.cur = fid;
    try { localStorage.setItem(PICK_KEY, fid); } catch (e) { /* fine */ }
    build();
  }

  /* ---------- the folder bar ---------- */
  function stats(f) {
    const ms = f.members || [];
    return {
      n: ms.length,
      read: ms.filter(readable).length,
      run: ms.filter((m) => m.bundle).length,
      sep: ms.filter((m) => m.bundle && verdictOf(m.bundle.separation)
                            === 'yes').length,
    };
  }

  function folderBar() {
    const vis = visible();
    const nArch = (S.folders || []).filter(archivedOf).length;
    return el('div', { class: 'card xm-bar' }, [
      el('div', { class: 'xm-folders' }, vis.map((f) => {
        const s = stats(f);
        const arch = archivedOf(f);
        return el('div', {
          class: 'xm-folder' + (f.id === S.cur ? ' on' : '')
                 + (arch ? ' archived' : ''),
          'data-fid': f.id,
        }, [
          el('button', {
            type: 'button', class: 'xm-folder-pick',
            title: f.source && f.source.nickname
              ? 'From ' + f.source.nickname
                + (f.source.version ? ' v' + f.source.version : '') : null,
            onclick: () => switchTo(f.id),
          }, [
            el('strong', { class: 'xm-folder-name', text: f.name || f.id }),
            el('span', { class: 'xm-folder-n', text:
              s.n + ' recording' + (s.n === 1 ? '' : 's') + ' · ' + s.read
              + ' read · ' + s.run + ' run · ' + s.sep + ' separable' }),
          ]),
          el('button', {
            type: 'button', class: 'mini xm-folder-arch',
            text: arch ? 'Put back' : 'Archive',
            title: arch ? 'Show it with the others again.'
                        : 'Out of the way, for everybody. Nothing in it is '
                          + 'deleted, and Put back brings it back.',
            onclick: () => archive(f, !arch),
          }),
        ]);
      })),
      el('div', { class: 'xm-bar-acts' }, [
        BARRY.ui.button({ kind: 'ghost', size: 'sm',
                          text: 'New folder from a workflow…',
                          onclick: newFolder }),
        nArch ? BARRY.ui.button({
          kind: 'mini', extra: 'xm-show-arch',
          text: (S.showArchived ? 'Hide archived · ' : 'Show archived · ')
                + nArch,
          onclick: () => {
            S.showArchived = !S.showArchived;
            if (!S.showArchived && cur() && archivedOf(cur())) {
              S.cur = pickFirst();
              build();
              return;
            }
            put('bar', folderBar());
          } }) : null,
      ]),
    ]);
  }

  /* Shared, by id: only this folder is sent (BARRY.prefs.mergeKey), so a
     colleague's folders are never written over. The id's whole record is
     what is sent, and the server puts it in place of the one it has; a
     folder the server made after this page loaded its prefs is not in
     this page's copy, so the prefs are read again first rather than the
     record rebuilt from the folder row, which has no `at` or `by`. */
  async function archive(f, on) {
    if (!(f.id in prefMap(FOLD_KEY)) && BARRY.prefs
        && typeof BARRY.prefs.load === 'function') {
      try { await BARRY.prefs.load(true); } catch (e) { /* the row, below */ }
    }
    const was = prefMap(FOLD_KEY)[f.id]
      || { name: f.name, at: f.at || null, by: f.by || null,
           source: f.source || null };
    const rec = Object.assign({}, was);
    if (on) { rec.archived = true; rec.archived_at = now(); }
    else { rec.archived = false; delete rec.archived_at; }
    mergeKey(FOLD_KEY, f.id, rec);
    f.archived = !!on;
    if (on && f.id === S.cur && !S.showArchived) {
      S.cur = pickFirst();
      build();
      return;
    }
    put('bar', folderBar());
  }

  /* A folder from a Root Canal workflow that has run: a verified DS or a
     verified P-spike one. The server reads the run's kept events and makes
     the members; this only says which workflow and what to call it. */
  async function newFolder() {
    let rows;
    try {
      rows = (await api('/api/rootcanal/workflows')).workflows || [];
    } catch (e) {
      toast('Could not list the workflows: ' + e.message, 'err', 8000);
      return;
    }
    const fit = rows.filter((r) => (r.kind === 'ds' || r.kind === 'pspike')
                                   && r.ran);
    let pick = null;
    const name = el('input', { type: 'text', class: 'xm-new-name',
                               placeholder: 'What to call the folder' });
    const go = BARRY.ui.button({ kind: 'primary', text: 'Make the folder',
                                 disabled: true });
    const list = el('div', { class: 'xm-wfs' }, fit.map((r) => el('button', {
      type: 'button', class: 'xm-wf', 'data-wf': r.artifact_id,
      onclick: (e) => {
        pick = r;
        list.querySelectorAll('.xm-wf').forEach((b) =>
          b.classList.toggle('on', b === e.currentTarget));
        if (!name.value.trim() || name.dataset.auto === '1') {
          name.value = r.nickname || r.name || r.artifact_id;
          name.dataset.auto = '1';
        }
        go.disabled = false;
      },
    }, [
      el('strong', { text: r.nickname || r.name || r.artifact_id }),
      el('span', { class: 'hint', text:
        (r.kind === 'ds' ? 'verified dentate spikes' : 'verified P-spikes')
        + ' · run in v' + (r.run_version || r.version)
        + (r.kept != null ? ' · ' + Number(r.kept).toLocaleString()
           + ' kept' + (r.n != null ? ' of ' + Number(r.n).toLocaleString() : '')
           : '')
        + (r.updated ? ' · ' + fmtWhen(r.updated) : '') }),
    ])));
    name.addEventListener('input', () => { name.dataset.auto = '0'; });
    go.onclick = async () => {
      if (!pick) return;
      const nm = name.value.trim() || pick.nickname || pick.name;
      go.disabled = true;
      let got;
      try {
        got = await apiPost('/api/dspca/many/folder', {
          name: nm,
          source: { artifact_id: pick.artifact_id,
                    version: pick.run_version || pick.version },
        });
      } catch (e) {
        go.disabled = false;
        toast(e.message, 'err', 8000);
        return;
      }
      closeModal();
      try { BARRY.activity.log('dspcamany.folder', { id: got.id }); }
      catch (e) { /* the log is not the work */ }
      toast('Folder made: ' + nm + '.', 'ok', 5000);
      S.cur = got.id || S.cur;
      try { localStorage.setItem(PICK_KEY, S.cur); } catch (e) { /* fine */ }
      S.folders = null;
      build();
      load();
    };
    showModal(el('div', { class: 'vpop xm-new' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'New folder from a workflow' }),
        el('div', { class: 'spacer' }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { class: 'hint', text:
          'A folder holds the recordings a Root Canal workflow kept. Pick '
          + 'one that has run; each recording’s events are the ones its '
          + 'run put inside the border.' }),
        fit.length ? list : el('p', { class: 'hint warn-line', text:
          'No verified DS or verified P-spike workflow has run yet.' }),
        el('label', { class: 'xm-new-lab' }, ['Name', name]),
      ]),
      BARRY.ui.modalFoot([], [
        BARRY.ui.button({ kind: 'ghost', text: 'Cancel',
                          onclick: () => closeModal() }),
        go,
      ]),
    ]));
  }

  /* ---------- the global parameters ---------- */
  function paramsCard(f) {
    const p = paramsOf(f.id);
    const set = (k, v) => {
      const was = paramsOf(f.id);
      const next = Object.assign({}, was, { [k]: v });
      mergeKey(PAR_KEY, f.id, next);
      f.params = next;
      put('params', paramsCard(f));
      // The automatic box is the fit's, so it is asked for again; the
      // picture on show stays until the new one lands.
      (f.members || []).forEach(wantRaster);
      tiles.forEach(fillTile);
    };
    const segOf = (items, k) => BARRY.ui.seg(
      items.map(([v, l, t]) => [v, l, t]), p[k], (v) => set(k, v),
      { extra: 'xm-seg xm-seg-' + k });
    return el('div', { class: 'card xm-params' }, [
      el('div', { class: 'section-label', text: 'For every recording in '
                  + 'this folder' }),
      el('div', { class: 'xm-prow' }, [
        el('span', { class: 'xm-plab', text: 'method' }),
        segOf(METHODS, 'method')]),
      el('div', { class: 'xm-prow' }, [
        el('span', { class: 'xm-plab', text: 'which is DS1' }),
        segOf(RULES, 'rule')]),
      p.method === 'delta' ? null : el('div', { class: 'xm-prow' }, [
        el('span', { class: 'xm-plab', text: 'features' }),
        segOf(FEATURES, 'features')]),
      el('div', { class: 'xm-prow' }, [
        el('span', { class: 'xm-plab', text: '60 Hz notch' }),
        BARRY.ui.seg([[true, 'on'], [false, 'off']], !!p.notch,
                     (v) => set('notch', v), { extra: 'xm-seg xm-seg-notch' })]),
      p.method === 'pca' ? null : el('div', { class: 'xm-prow' }, [
        el('span', { class: 'xm-plab', text: 'two sinks at least' }),
        el('input', { type: 'number', class: 'dp-gnum xm-minsep', min: '1',
                      max: '40', value: String(p.min_sep),
                      onchange: (e) => set('min_sep', Math.max(
                        1, parseInt(e.target.value, 10) || 5)) }),
        el('span', { class: 'hint', text: 'contacts apart' })]),
      p.method !== 'pca_gap' ? null : el('div', { class: 'xm-prow' }, [
        el('span', { class: 'xm-plab', text: 'gap column ×' }),
        el('input', { type: 'number', class: 'dp-gnum xm-gapw', min: '0',
                      step: '1', value: String(p.gap_weight),
                      onchange: (e) => set('gap_weight', Math.max(
                        0, parseFloat(e.target.value) || 0)) })]),
      el('p', { class: 'hint', text:
        'Saved with the folder for everybody. A recording keeps the result '
        + 'it was run with until it is run again.' }),
    ]);
  }

  /* ---------- reading what is not read ---------- */
  function jobCard(f) {
    const ms = f.members || [];
    const todo = ms.filter((m) => !readable(m));
    const kids = [el('div', { class: 'section-label', text: 'Reads' })];
    const j = S.job;
    if (j) {
      const mem = j.members || [];
      const of = mem.length || ((j.stages || [])[0] || {}).of || 0;
      const done = mem.filter((m) => m.status === 'done' || m.cached).length;
      const left = j.eta_s != null ? ' · about ' + dur(j.eta_s) + ' left' : '';
      const spent = j.elapsed != null ? ' · ' + dur(j.elapsed) + ' so far' : '';
      kids.push(el('div', { class: 'xm-jobline' }, [
        el('span', { class: 'xm-jobwords', text:
          (j.status === 'running' ? 'Reading ' : 'Read ') + done + ' of '
          + of + ' recording' + (of === 1 ? '' : 's') + spent + left }),
        j.status === 'running' ? BARRY.ui.button({
          kind: 'ghost', size: 'sm', text: 'Stop', extra: 'xm-stop',
          onclick: stopRead }) : null,
      ]));
      kids.push(el('div', { class: 'dp-bar' }, [el('i', { style: 'width:'
        + (of ? (100 * done / of).toFixed(1) : 0) + '%' })]));
      return el('div', { class: 'card xm-job' }, kids);
    }
    const nEv = todo.reduce((a, m) => a + (m.n || 0), 0);
    kids.push(el('div', { class: 'xm-jobline' }, [
      BARRY.ui.button({
        kind: 'ghost', size: 'sm', extra: 'xm-readall',
        text: todo.length ? 'Read all not read yet' : 'Everything here is read',
        disabled: !todo.length,
        onclick: () => startRead(null) }),
      el('span', { class: 'hint', text: todo.length
        ? todo.length + ' recording' + (todo.length === 1 ? '' : 's') + ', '
          + nEv.toLocaleString() + ' events. One job on this computer, one '
          + 'recording after another; seconds each on a local disk and '
          + 'minutes over a share. Cached, so it is paid once.'
        : 'Every recording has a read on this computer.' }),
    ]));
    return el('div', { class: 'card xm-job' }, kids);
  }

  async function startRead(gids) {
    if (S.job) { toast('A read is already running.', 'warn', 5000); return; }
    const f = cur();
    if (!f) return;
    const body = { folder: f.id };
    if (gids) body.gids = gids;
    let got;
    try {
      got = await apiPost('/api/dspca/many/read', body);
    } catch (e) {
      toast(e.message, 'err', 10000);
      return;
    }
    if (!got.job) {
      // Nothing to read: cached already, or the server says why not.
      const sk = got.skipped || [];
      toast(sk.length
        ? 'Nothing to read. ' + sk.map((x) => (x.gid || '?') + ': '
                                        + (x.why || 'skipped')).join('; ') + '.'
        : 'Already read.', sk.length ? 'warn' : 'ok', sk.length ? 10000 : 4000);
      load();
      return;
    }
    S.job = got.job;
    S.job.folder = f.id;
    put('job', jobCard(f));
    tiles.forEach(fillTile);
    watchRead();
  }

  function watchRead() {
    if (S.poll) clearInterval(S.poll);
    S.poll = setInterval(async () => {
      if (!S.job) { clearInterval(S.poll); S.poll = null; return; }
      let got;
      try { got = await api('/api/cfc/job/' + S.job.id); }
      catch (e) { return; }
      const was = S.job;
      const j = Object.assign({}, got.job || was, { folder: was.folder });
      S.job = j;
      let fresh = false;
      (j.members || []).forEach((m) => {
        const before = (was.members || []).find((x) => x.id === m.id) || {};
        const t = tiles.get(m.id);
        if (m.status === 'done' && before.status !== 'done') {
          const mm = memberOf(m.id);
          if (mm && m.read) { mm.read = m.read; mm.read_here = true; wantRaster(mm); }
          else fresh = true;
        }
        if (t && (m.status !== before.status || m.error !== before.error)) {
          fillTile(t);
        }
      });
      const f = cur();
      if (f && f.id === j.folder) put('job', jobCard(f));
      if (j.status === 'running') {
        if (fresh) load();
        return;
      }
      clearInterval(S.poll);
      S.poll = null;
      const n = (j.members || []).filter((m) => m.status === 'done').length;
      const quit = j.status === 'canceled';
      S.job = null;
      toast(quit ? 'Stopped. ' + n + ' read and kept; the rest were not started.'
            : j.status === 'failed' ? 'The read stopped: ' + (j.error || 'failed')
            : 'Read ' + n + '. Nothing was run or saved.',
            quit ? 'warn' : j.status === 'failed' ? 'err' : 'ok', 8000);
      await load();
    }, 900);
  }

  function stopRead() {
    if (!S.job) return;
    apiPost('/api/cfc/job/' + S.job.id + '/cancel', {}).catch(() => {});
  }

  /* ---------- the grid's head: Run all ---------- */
  function gridHead(f) {
    const ms = f.members || [];
    const can = ms.filter(readable);
    const noBox = can.filter((m) => !boxOf(f.id, m.gid)).length;
    const notRead = ms.length - can.length;
    const ra = S.runAll;
    return el('div', { class: 'xm-gridhead' }, [
      el('div', { class: 'section-label', text: 'Average CSD per recording' }),
      el('span', { class: 'hint', text:
        'Drag on a picture for a depth × time box; click once for one time '
        + 'sample.' }),
      el('div', { class: 'spacer' }),
      ra ? el('span', { class: 'xm-runall-words', text:
             'Running ' + Math.min(ra.done + 1, ra.of) + ' of ' + ra.of }) : null,
      ra ? BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Stop',
                             extra: 'xm-runall-stop',
                             onclick: () => { ra.stop = true; } }) : null,
      ra ? null : BARRY.ui.button({
        kind: 'primary', size: 'sm', text: 'Run all', extra: 'xm-runall',
        disabled: !can.length,
        title: 'Every recording with a read here, each with its own box.',
        onclick: runAll }),
      el('span', { class: 'hint xm-runall-sub', text: can.length
        ? can.length + ' with a read' + (noBox ? '; ' + noBox + ' with no box '
          + 'drawn use the automatic box' : '; every one has a box')
          + (notRead ? '; ' + notRead + ' not read yet, left out' : '')
        : 'Nothing is read yet.' }),
      // The workflow behind it could not be listed (the server's words).
      f.error ? el('p', { class: 'hint warn-line xm-ferr', text:
        'Could not list this folder’s recordings: ' + f.error }) : null,
    ]);
  }

  /* ==================================================================
     A tile
     ================================================================== */
  function tileOf(m) {
    const t = { gid: m.gid, m, node: null, cv: null, pic: null, info: null,
                geom: null, drag: null, busy: false, error: null,
                view: null, vbtn: null, note: null, drawn: null };
    t.pic = el('div', { class: 'xm-pic' });
    t.info = el('div', { class: 'xm-info' });
    t.head = el('div', { class: 'xm-head' });
    t.node = el('div', { class: 'xm-tile', 'data-gid': m.gid },
                [t.head, t.pic, t.info]);
    tiles.set(m.gid, t);
    fillTile(t);
    return t;
  }

  /* Everything on a tile but the picture, rebuilt for that tile alone. */
  function fillTile(t) {
    const f = cur();
    if (!f) return;
    const m = t.m;
    t.head.innerHTML = '';
    t.head.appendChild(el('strong', { class: 'xm-label',
                                      text: m.session_label || m.gid }));
    if (m.group) {
      t.head.appendChild(BARRY.ui.chip(m.group, {
        extra: 'xm-group xm-group-' + String(m.group).toLowerCase() }));
    }
    t.head.appendChild(el('span', { class: 'xm-n', text:
      (m.n != null ? Number(m.n).toLocaleString() : '?') + ' events' }));

    // The picture, or why there is none.
    const can = readable(m);
    if (can && !t.cv) {
      t.pic.innerHTML = '';
      t.note = null;
      t.cv = el('canvas', { class: 'xm-cv' });
      t.cv.style.height = TILE_H + 'px';
      t.cv.addEventListener('pointerdown', (e) => onDown(t, e));
      t.cv.addEventListener('pointermove', (e) => onMove(t, e));
      t.cv.addEventListener('pointerup', (e) => onUp(t, e));
      t.cv.addEventListener('pointercancel', () => { t.drag = null; drawTile(t); });
      t.pic.appendChild(t.cv);
    } else if (!can) {
      t.cv = null;
      t.geom = null;
      t.pic.innerHTML = '';
      t.note = null;
      const jm = jobMember(m.gid);
      // The job's member words differ by route: running or reading,
      // waiting or queued, error or failed (cfc Job.member).
      const js = jm ? String(jm.status || '') : '';
      t.pic.appendChild(el('div', { class: 'xm-empty' }, [
        el('span', { text: /^(running|reading)$/.test(js) ? 'reading…'
                     : /^(waiting|queued)$/.test(js) ? 'waiting its turn in the read'
                     : /^(error|failed)$/.test(js) ? 'the read failed'
                       + (jm.error ? ': ' + jm.error : '')
                     : js === 'stopped' ? 'stopped before it was read'
                     : m.read && !m.read_here
                       ? 'read on another computer, not on this one'
                       : 'not read yet' }),
        jm ? null : BARRY.ui.button({
          kind: 'mini', text: 'Read', extra: 'xm-read',
          disabled: !!S.job,
          title: S.job ? 'Another read is running; this waits for it.' : null,
          onclick: () => startRead([m.gid]) }),
      ]));
    }

    t.info.innerHTML = '';
    const bx = boxOf(f.id, m.gid);
    /* THREE PRESSES ON EVERY TILE (2026-11-09: "in addition to the
       automatic box, the center and 1 sample button"). Each keeps the
       depth already chosen -- the drawn one, or the automatic one:
         centre     the time window moved onto the stamp (0 ms), as wide
                    as it was;
         1 sample   the time window made one instant, at its own middle.
       Both together are Toothy's own feature window, one sample at the
       stamp. Shown always; one that would change nothing is greyed. */
    const tw = timeOf(bx, autoBox(m));
    const mid = tw ? Math.round(((tw[0] + tw[1]) / 2) * 10) / 10 : 0;
    const half = tw ? Math.round(((tw[1] - tw[0]) / 2) * 10) / 10 : 0;
    const keepDepth = { sel_lo: bx ? bx.sel_lo : null, sel_hi: bx ? bx.sel_hi : null };
    t.info.appendChild(el('div', { class: 'xm-box' }, [
      el('span', { class: 'xm-boxwords', text: boxWords(bx, autoBox(m)) }),
      el('span', { class: 'xm-box-btns' }, [
        BARRY.ui.button({ kind: 'mini', text: 'automatic box', extra: 'xm-auto',
          disabled: !bx,
          title: bx ? 'Take this box away; the server picks one when it runs.'
                    : 'This tile is on the automatic box already.',
          onclick: () => setBox(t, null) }),
        BARRY.ui.button({ kind: 'mini', text: 'centre', extra: 'xm-centre',
          disabled: !!tw && mid === 0,
          title: 'Move the time window onto the stamp (0 ms), as wide as it '
                 + 'is, keeping the depth.',
          onclick: () => setBox(t, Object.assign({}, keepDepth,
            { t_lo_ms: -half, t_hi_ms: half })) }),
        BARRY.ui.button({ kind: 'mini', text: '1 sample', extra: 'xm-one',
          disabled: !!tw && tw[0] === tw[1],
          title: 'Make the time window one instant, at its middle ('
                 + fmtMs(mid) + ' ms), keeping the depth. With centre, it '
                 + 'is Toothy’s own: one sample at the stamp.',
          onclick: () => setBox(t, Object.assign({}, keepDepth,
            { t_lo_ms: mid, t_hi_ms: mid })) }),
      ]),
    ]));

    const b = shownBundle(t);
    const acts = el('div', { class: 'xm-acts' }, [
      BARRY.ui.button({
        kind: 'ghost', size: 'sm', extra: 'xm-run',
        text: t.busy ? 'Running…' : 'Run',
        disabled: !can || t.busy || !!S.runAll,
        title: can ? 'Fit this recording with its box and save the answer as '
                     + 'the next version of its X-ray bundle.'
                   : 'Read it first.',
        onclick: () => runOne(m.gid) }),
      m.bundle ? BARRY.ui.button({
        kind: 'ghost', size: 'sm', text: 'Open in Single', extra: 'xm-open',
        // A bundle made elsewhere whose payload has not synced here yet.
        disabled: m.bundle.here === false && !t.view,
        title: m.bundle.here === false && !t.view
          ? 'Made on another computer; its numbers have not reached this '
            + 'one yet.' : null,
        onclick: () => openInSingle(t) }) : null,
      m.bundle ? versionBtn(t) : null,
    ]);
    t.info.appendChild(acts);
    if (t.error) {
      t.info.appendChild(el('p', { class: 'hint warn-line xm-err',
                                   text: t.error }));
    }
    if (b) t.info.appendChild(resultBlock(b, t.view));
    drawTile(t);
  }

  function jobMember(gid) {
    if (!S.job || S.job.folder !== S.cur) return null;
    const m = (S.job.members || []).find((x) => x.id === gid);
    return m && m.status !== 'done' && !m.cached ? m : null;
  }

  /* The result on show: an older version somebody picked, else the
     newest. */
  function shownBundle(t) {
    return t.view || (t.m.bundle ? t.m.bundle : null);
  }

  function resultBlock(b, older) {
    const sep = b.separation || {};
    const v = verdictOf(sep);
    const [word, kind] = VERDICT[v] || [sep.verdict || 'no verdict', null];
    const sinks = (b.sinks || []).filter((s) => s && s.value != null);
    return el('div', { class: 'xm-result' + (older ? ' older' : '') }, [
      older ? el('div', { class: 'hint xm-older', text:
        'Showing v' + older.version + ', an older version.' }) : null,
      el('div', { class: 'chip-row' }, [
        BARRY.ui.chip(countWords(b.counts), { extra: 'xm-counts' }),
        el('span', {
          class: 'stat-chip xm-sep xm-sep-' + v + (kind ? ' ' + kind : ''),
          // The server's sentence when the answer carries it.
          title: (sep.why ? sep.why + '\n' : '')
               + 'Two Gaussians against one on the method’s own axis. '
               + 'Separable: ΔBIC at least 10 and the smaller class at least '
               + '10% of the events. Weak: ΔBIC at least 2 and the smaller '
               + 'class at least 10%. Too few: under 20 events.',
        }, [el('strong', { text: word }),
            el('span', { text: ' ' + sepNumbers(sep, v) })]),
      ]),
      sinks.length ? el('div', { class: 'xm-sinks' }, sinks.map((s) =>
        el('div', { class: 'xm-sink' }, [
          el('i', { class: 'xm-dot',
                    style: 'background:' + inkOf(s.cls) }),
          el('span', { text: clsName(s.cls) + ' sink'
            + (s.csc != null ? ' at CSC' + s.csc : '') + ': '
            + num3(s.value) + (s.sem != null ? ' ± ' + num3(s.sem) : '')
            + (s.unit ? ' ' + s.unit : '') }),
        ]))) : null,
      sinkWords(sep, sinks)
        ? el('div', { class: 'xm-sinkwords', text: sinkWords(sep, sinks) })
        : null,
    ]);
  }

  function verdictOf(sep) {
    const v = String((sep && sep.verdict) || '').toLowerCase()
      .replace(/[\s-]+/g, '_');
    if (v === 'separable') return 'yes';
    if (v === 'not_separable') return 'no';
    if (v === 'few') return 'too_few';
    return v;
  }

  function sepNumbers(sep, v) {
    if (v === 'too_few') {
      return sep.n != null ? sep.n + ' events' : '';
    }
    const bits = [];
    if (sep.dbic != null && isFinite(sep.dbic)) {
      bits.push('ΔBIC ' + (Math.round(sep.dbic * 10) / 10).toFixed(1));
    }
    if (sep.min_share != null && isFinite(sep.min_share)) {
      const p = sep.min_share <= 1 ? sep.min_share * 100 : sep.min_share;
      bits.push('smaller class ' + Math.round(p) + '%');
    }
    return bits.join(' · ');
  }

  /* The server's own words when it sent them (a run's answer); else the
     same words made the same way from the sinks it sent, because the
     bundle's summary on a reload carries the sinks and not the words.
     This is xraymany.sink_words, line for line: a class whose "sink" is
     not negative is said to have none; otherwise each sink against the
     weakest. */
  function sinkWords(sep, sinks) {
    if (sep && sep.words) return sep.words;
    const got = sinks.filter((s) => s && s.value != null && isFinite(s.value));
    if (got.length < 2) return null;
    const pos = got.filter((s) => s.value >= 0);
    if (pos.length) {
      return pos.map((s) => clsName(s.cls) + ' has no sink at CSC' + s.csc
        + ' (the CSD there is ' + (s.value === 0 ? 'zero' : 'positive')
        + ', not negative)').join('; ');
    }
    const xs = got.slice().sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
    const weak = xs[xs.length - 1];
    return xs.slice(0, -1).map((s) => clsName(s.cls) + ' sink '
      + (Math.abs(s.value) / Math.abs(weak.value)).toFixed(1) + '× '
      + clsName(weak.cls)).join('; ');
  }

  function countWords(c) {
    const ks = Object.keys(c || {}).sort();
    if (!ks.length) return 'no counts';
    return ks.map((k) => clsName(k) + ' ' + Number(c[k]).toLocaleString())
      .join(' · ');
  }

  function clsName(c) {
    const s = String(c == null ? '?' : c);
    return /^\d+$/.test(s) ? 'DS' + s : s.toUpperCase();
  }
  function inkOf(c) {
    const n = parseInt(String(c).replace(/\D/g, ''), 10) || 1;
    return CLS_INK[(n - 1) % CLS_INK.length];
  }
  function num3(v) {
    const x = Number(v);
    if (!isFinite(x)) return '—';
    if (x === 0) return '0';
    const a = Math.abs(x);
    return a >= 100 ? x.toFixed(0) : a >= 10 ? x.toFixed(1)
         : a >= 0.01 ? x.toFixed(2) : x.toExponential(1);
  }
  function fmtMs(v) {
    const x = Math.round(Number(v) * 10) / 10;
    return (x < 0 ? '−' : x > 0 ? '+' : '') + Math.abs(x).toFixed(1);
  }
  function dur(s) {
    const x = Math.max(0, Math.round(s));
    if (x < 60) return x + ' s';
    const m = Math.floor(x / 60), r = x % 60;
    return m + ' min' + (r ? ' ' + r + ' s' : '');
  }

  /* The box in words. `auto` is what the server picked for the picture
     when nobody has drawn one, if it said. */
  function boxWords(b, auto) {
    const t = (lo, hi) => (lo === hi ? 'one sample at ' + fmtMs(lo) + ' ms'
                           : fmtMs(lo) + ' to ' + fmtMs(hi) + ' ms');
    if (!b) {
      return auto ? 'Automatic box: CSC' + auto.lo + '–' + auto.hi + ', '
                    + t(auto.t_lo_ms, auto.t_hi_ms)
                  : 'Automatic box: the server picks it when it runs.';
    }
    const depth = b.sel_lo == null || b.sel_hi == null ? 'automatic depth'
      : 'CSC' + b.sel_lo + '–' + b.sel_hi;
    const time = b.t_lo_ms == null || b.t_hi_ms == null
      ? 'one sample at the stamp' : t(b.t_lo_ms, b.t_hi_ms);
    return 'Box: ' + depth + ', ' + time;
  }

  /* The time window a tile is on, [lo, hi] in ms: the drawn box's, else
     the automatic one's; null when neither has said yet. */
  function timeOf(b, auto) {
    if (b && b.t_lo_ms != null && b.t_hi_ms != null) return [b.t_lo_ms, b.t_hi_ms];
    if (b) return [0, 0];
    if (auto && auto.t_lo_ms != null && auto.t_hi_ms != null) {
      return [auto.t_lo_ms, auto.t_hi_ms];
    }
    return null;
  }

  /* The band and window the server used for the picture with no box. */
  function autoBox(m) {
    const r = rasterOf(m);
    const ln = r && r.got && r.got.line;
    if (!ln || !ln.band || !ln.window_ms) return null;
    return { lo: ln.band[0], hi: ln.band[1],
             t_lo_ms: Math.round(ln.window_ms[0] * 10) / 10,
             t_hi_ms: Math.round(ln.window_ms[1] * 10) / 10 };
  }

  /* ---------- the bundle's versions ---------- */
  function wantVersions(m) {
    const b = m.bundle;
    if (!b || !b.artifact_id) return;
    const have = versions.get(b.artifact_id);
    if (have === 'pending') return;
    if (Array.isArray(have) && have.some((v) => v.v === b.version)) return;
    versions.set(b.artifact_id, 'pending');
    api('/api/artifacts/' + encodeURIComponent(b.artifact_id))
      .then((got) => {
        const a = got.artifact || {};
        versions.set(b.artifact_id, (a.versions || []).map((v) => ({
          v: v.v, id: v.id, at: v.at, by: v.by, note: v.note,
          n: (v.n_summary || {}).events != null ? v.n_summary.events
             : (v.n_summary || {}).n,
          here: v.here !== false,
        })));
      })
      .catch(() => { versions.set(b.artifact_id, []); })
      .then(() => {
        const t = tiles.get(m.gid);
        if (t && t.m.bundle && t.m.bundle.artifact_id === b.artifact_id) {
          const nb = versionBtn(t);
          if (t.vbtn && t.vbtn.parentNode) t.vbtn.replaceWith(nb);
          t.vbtn = nb;
        }
      });
  }

  function versionBtn(t) {
    const b = t.m.bundle;
    const have = versions.get(b.artifact_id);
    const vs = (Array.isArray(have) && have.length ? have.slice() : []);
    /* The version the tile holds is always among them (2026-11-09): a run
       that has just made it can land before the version list says so, and
       the button then read "Choose a version" over a v it could not show. */
    if (b.version != null && !vs.some((v) => v.v === b.version)) {
      vs.push({ v: b.version, at: b.at, by: b.by, n: b.n });
    }
    const shown = t.view ? t.view.version : b.version;
    t.vbtn = BARRY.ui.versionButton({
      versions: vs, idOf: (v) => v.v, value: shown,
      producer: false, unit: 'events',
      heading: 'Which version of the X-ray bundle for '
               + (t.m.session_label || t.m.gid),
      sub: 'Every run that changed the answer is a version. Picking an older '
           + 'one shows it here; Open in Single opens the one on show.',
      disabled: (v) => (v.here === false
        ? 'Made on another computer; its payload has not reached this one.'
        : null),
      onpick: (v) => { if (v) showVersion(t, v.v); },
    });
    t.vbtn.classList.add('xm-vbtn');
    return t.vbtn;
  }

  async function showVersion(t, v) {
    const b = t.m.bundle;
    if (!b) return;
    if (v === b.version) { t.view = null; fillTile(t); return; }
    let got;
    try {
      got = await api('/api/dspca/bundle/' + encodeURIComponent(b.artifact_id)
                      + '?version=' + encodeURIComponent(v));
    } catch (e) {
      toast(e.message, 'err', 8000);
      return;
    }
    const p = got.payload || {};
    t.view = { version: v, artifact_id: b.artifact_id, counts: p.counts,
               separation: p.separation, sinks: p.sinks, box: p.box };
    fillTile(t);
  }

  /* Single opens the bundle's read, parameters and box and fits it. The
     run bar goes back to One first, so the workbench is what is on show. */
  function openInSingle(t) {
    const b = t.m.bundle;
    if (!b) return;
    const v = t.view ? t.view.version : b.version;
    try { if (S.ctx && S.ctx.toSingle) S.ctx.toSingle(); }
    catch (e) { /* Single still opens below */ }
    if (BARRY.dspca && typeof BARRY.dspca.openBundle === 'function') {
      BARRY.dspca.openBundle(b.artifact_id, v);
    } else {
      toast('Single cannot open a bundle in this build.', 'warn', 6000);
    }
  }

  /* ==================================================================
     Running
     ================================================================== */
  function boxBody(fid, gid) {
    const b = boxOf(fid, gid);
    return b ? { sel_lo: b.sel_lo == null ? null : b.sel_lo,
                 sel_hi: b.sel_hi == null ? null : b.sel_hi,
                 t_lo_ms: b.t_lo_ms == null ? null : b.t_lo_ms,
                 t_hi_ms: b.t_hi_ms == null ? null : b.t_hi_ms } : null;
  }

  async function runOne(gid) {
    const f = cur();
    const t = tiles.get(gid);
    if (!f || !t || t.busy) return false;
    t.busy = true;
    t.error = null;
    fillTile(t);
    let got;
    try {
      got = await apiPost('/api/dspca/many/run', {
        folder: f.id, gids: [gid], params: paramsOf(f.id),
        boxes: { [gid]: boxBody(f.id, gid) },
      });
    } catch (e) {
      t.busy = false;
      t.error = e.message;
      fillTile(t);
      return false;
    }
    t.busy = false;
    const r = (got.results || []).find((x) => x.gid === gid);
    if (!r || !r.ok) {
      t.error = (r && r.error) || 'The run came back with nothing for it.';
      fillTile(t);
      return false;
    }
    t.m.bundle = {
      artifact_id: r.bundle && r.bundle.artifact_id,
      version: r.bundle && r.bundle.version,
      at: now(), by: who(),
      counts: r.counts, separation: r.separation, sinks: r.sinks, box: r.box,
    };
    t.view = null;
    fillTile(t);
    wantVersions(t.m);
    put('bar', folderBar());
    try { BARRY.activity.log('dspcamany.run', { gid, folder: f.id }); }
    catch (e) { /* the log is not the work */ }
    return true;
  }

  /* In turn, so each tile's answer lands as it is made and Stop means
     something. */
  async function runAll() {
    const f = cur();
    if (!f || S.runAll) return;
    const gids = (f.members || []).filter(readable).map((m) => m.gid);
    if (!gids.length) return;
    S.runAll = { of: gids.length, done: 0, stop: false };
    put('gridHead', gridHead(f));
    tiles.forEach(fillTile);
    let good = 0;
    for (const gid of gids) {
      if (S.runAll.stop || S.cur !== f.id) break;
      put('gridHead', gridHead(f));
      const t = tiles.get(gid);
      if (t) { t.busy = false; }
      // eslint-disable-next-line no-await-in-loop
      if (await runOne(gid)) good++;
      S.runAll.done += 1;
    }
    const ra = S.runAll;
    S.runAll = null;
    put('gridHead', gridHead(f));
    tiles.forEach(fillTile);
    toast((ra.stop ? 'Stopped after ' + ra.done + ' of ' + ra.of + '. '
                   : 'Ran ' + ra.of + '. ')
          + good + ' saved as a bundle version.', ra.stop ? 'warn' : 'ok', 7000);
  }

  /* ==================================================================
     The picture
     ================================================================== */
  /* Keyed on everything the server's automatic box depends on: the
     picture is the read's, but the band and window drawn dashed on it
     come from a fit with these parameters. */
  function rasterKey(m) {
    const p = paramsOf(S.cur);
    return [m.gid, m.read, p.notch ? 1 : 0, p.method, p.rule, p.features,
            p.min_sep, p.gap_weight].join('|');
  }
  /* The answer for these parameters, else the last one this recording's
     read had while the new one is coming, so a change of method does not
     blank eighteen pictures. */
  function rasterOf(m) {
    if (!readable(m)) return null;
    const r = rasters.get(rasterKey(m));
    if (r && !r.pending) return r;
    const last = lastGood.get(m.gid);
    return last && last.read === m.read ? last.r : r;
  }

  function wantRaster(m) {
    if (!readable(m)) return;
    const k = rasterKey(m);
    if (rasters.has(k)) return;
    rasters.set(k, { pending: true });
    rasterQ.push({ m, k, p: paramsOf(S.cur) });
    pump();
  }

  /* Four at a time: each one is a fit on the server, for the depth line
     (2026-11-09: two at a time left most of 18 tiles saying "drawing…").
     One queued for parameters that have since changed is dropped, and
     forgotten, so going back to them asks again. */
  function pump() {
    while (rasterBusy < 4 && rasterQ.length) {
      const { m, k, p } = rasterQ.shift();
      if (k !== rasterKey(m)) { rasters.delete(k); continue; }
      rasterBusy++;
      apiPost('/api/dspca/raster', {
        gid: m.gid, read: m.read, what: 'shank', cmap: 'jet',
        nclasses: 2, rule: p.rule, notch: !!p.notch, screen: false,
        flip: false, features: p.features, method: p.method,
        min_sep: p.min_sep, gap_weight: p.gap_weight,
        sel_lo: null, sel_hi: null, t_lo_ms: null, t_hi_ms: null,
      }).then((got) => {
        rasters.set(k, { got });
        if (got && got.ok) lastGood.set(m.gid, { read: m.read, r: { got } });
      })
        .catch((e) => { rasters.set(k, { error: e.message }); })
        .then(() => {
          rasterBusy--;
          const t = tiles.get(m.gid);
          if (t) {
            // The automatic box is in the words, and it has just arrived.
            const w = t.info.querySelector('.xm-boxwords');
            if (w) w.textContent = boxWords(boxOf(S.cur, m.gid), autoBox(t.m));
            drawTile(t);
          }
          pump();
        });
    }
  }

  function ink() {
    const css = getComputedStyle(document.documentElement);
    const v = (n, f) => (css.getPropertyValue(n) || f).trim() || f;
    return { text: v('--text', '#222'), dim: v('--text-3', '#888'),
             line: v('--line', '#ccc'), accent: v('--accent', '#c8a') };
  }

  function drawAll() { tiles.forEach(drawTile); }

  function drawTile(t) {
    const cv = t.cv;
    if (!cv || !cv.isConnected) return;
    const w = cv.clientWidth;
    if (!w) return;
    const h = TILE_H;
    const dpr = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
    }
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const k = ink();
    const x0 = PAD.l, y0 = PAD.t;
    const pw = w - PAD.l - PAD.r, ph = h - PAD.t - PAD.b;
    const r = rasterOf(t.m);
    const d = r && r.got;
    g.font = '10px system-ui, sans-serif';
    t.drawn = null;
    /* Why there is no picture goes under it as text that wraps: a
       server's sentence painted on a canvas is cut off at its edge. */
    picNote(t, r && r.error ? 'Could not draw it: ' + r.error
               : d && !d.ok ? 'Could not draw it: ' + (d.error || 'no reason given')
               : null);
    if (!d || !d.ok) {
      t.geom = null;
      if (!(r && r.error) && !(d && !d.ok)) {
        g.fillStyle = k.dim;
        g.fillText('drawing…', x0 + 4, y0 + ph / 2);
      }
      return;
    }
    const img = imageFor(t, d.image);
    if (img) g.drawImage(img, x0, y0, pw, ph);
    t.drawn = { image: !!img, mark: null, sinks: 0 };
    const geom = { x0, y0, pw, ph, lo: d.lo, hi: d.hi, ext: d.extent };
    t.geom = geom;
    const span = d.hi - d.lo + 1;
    const X = (ms) => x0 + ((ms - d.extent[0]) / (d.extent[1] - d.extent[0])) * pw;
    // Row n is [n - lo, n - lo + 1) of the span: what onUp's toCsc inverts.
    const Ytop = (n) => y0 + ((n - d.lo) / span) * ph;

    // The stamp.
    g.strokeStyle = 'rgba(255,255,255,.55)';
    g.setLineDash([3, 3]);
    g.lineWidth = 1;
    g.beginPath(); g.moveTo(X(0), y0); g.lineTo(X(0), y0 + ph); g.stroke();
    g.setLineDash([]);

    const f = cur();
    const bx = f ? boxOf(f.id, t.gid) : null;
    const auto = bx ? null : autoBox(t.m);
    const draw = bx || (auto && { sel_lo: auto.lo, sel_hi: auto.hi,
                                  t_lo_ms: auto.t_lo_ms, t_hi_ms: auto.t_hi_ms });
    if (draw) {
      const lo = draw.sel_lo == null ? d.lo : draw.sel_lo;
      const hi = draw.sel_hi == null ? d.hi : draw.sel_hi;
      const by0 = Ytop(lo), by1 = Ytop(hi + 1);
      const tl = draw.t_lo_ms == null ? 0 : draw.t_lo_ms;
      const th = draw.t_hi_ms == null ? 0 : draw.t_hi_ms;
      g.setLineDash(bx ? [] : [4, 3]);
      if (tl === th) {
        // One sample: a line, over the depth it is read at.
        g.strokeStyle = '#ffffff';
        g.lineWidth = 2;
        g.beginPath(); g.moveTo(X(tl), by0); g.lineTo(X(tl), by1); g.stroke();
        g.strokeStyle = 'rgba(0,0,0,.6)';
        g.lineWidth = 0.7;
        g.beginPath(); g.moveTo(X(tl) + 1.5, by0); g.lineTo(X(tl) + 1.5, by1);
        g.stroke();
        if (draw.sel_lo != null) {
          g.strokeStyle = '#ffffff';
          g.lineWidth = 1.4;
          [by0, by1].forEach((y) => {
            g.beginPath(); g.moveTo(X(tl) - 5, y); g.lineTo(X(tl) + 5, y);
            g.stroke();
          });
        }
      } else {
        const a = X(tl), b = X(th);
        g.strokeStyle = '#ffffff';
        g.lineWidth = 1.6;
        g.strokeRect(a, by0, Math.max(2, b - a), by1 - by0);
        g.strokeStyle = 'rgba(0,0,0,.55)';
        g.lineWidth = 0.7;
        g.strokeRect(a, by0, Math.max(2, b - a), by1 - by0);
      }
      g.setLineDash([]);
      if (!bx) {
        g.fillStyle = '#ffffff';
        g.fillText('auto', Math.min(X(th) + 4, x0 + pw - 24), by0 + 10);
      }
      // What was drawn, in canvas pixels, for the harness to hold it to.
      t.drawn.mark = { kind: tl === th ? 'line' : 'box', auto: !bx,
                       x0: X(tl), x1: X(th), y0: by0, y1: by1 };
    }

    // Where each class's sink is, from the result on show.
    const res = shownBundle(t);
    (res && res.sinks || []).forEach((s) => {
      if (s.csc == null) return;
      t.drawn.sinks += 1;
      const y = Ytop(s.csc) + (ph / span) / 2;
      g.fillStyle = inkOf(s.cls);
      g.beginPath();
      g.moveTo(x0 + pw, y); g.lineTo(x0 + pw - 7, y - 4);
      g.lineTo(x0 + pw - 7, y + 4); g.closePath(); g.fill();
    });

    // The rubber band, while it is being drawn.
    if (t.drag && t.drag.live) {
      const L = t.drag.live;
      g.strokeStyle = '#ffffff';
      g.setLineDash([4, 3]);
      g.lineWidth = 1.3;
      g.strokeRect(L.x, L.y, L.w, L.h);
      g.setLineDash([]);
    }

    // Axes: the shank's two ends, and the window's.
    g.fillStyle = k.dim;
    g.textBaseline = 'top';
    g.fillText(String(d.lo), 2, y0);
    g.textBaseline = 'bottom';
    g.fillText(String(d.hi), 2, y0 + ph);
    g.textBaseline = 'alphabetic';
    g.fillText(fmtMs(d.extent[0]), x0, h - 2);
    const z = fmtMs(0) + ' ms';
    g.fillText(z, X(0) - g.measureText(z).width / 2, h - 2);
    const e1 = fmtMs(d.extent[1]);
    g.fillText(e1, x0 + pw - g.measureText(e1).width, h - 2);
  }

  function picNote(t, text) {
    if (!text) {
      if (t.note) { t.note.remove(); t.note = null; }
      return;
    }
    if (!t.note) {
      t.note = el('p', { class: 'hint warn-line xm-picnote' });
      t.pic.appendChild(t.note);
    }
    if (t.note.textContent !== text) t.note.textContent = text;
  }

  /* Data URIs decode asynchronously; the tile is redrawn when it has. */
  function imageFor(t, src) {
    if (!src) return null;
    const have = imgs.get(t.gid);
    if (have && have.src === src) return have.img.complete ? have.img : null;
    const img = new Image();
    imgs.set(t.gid, { src, img });
    img.onload = () => {
      const now_ = imgs.get(t.gid);
      if (now_ && now_.src === src) drawTile(t);
    };
    img.src = src;
    return null;
  }

  /* ---------- the gesture ----------

     A drag is a box, a click is one sample. Pixels to milliseconds and
     contacts the way Single's onUp does it, with its three-contact floor. */
  function local(t, e) {
    const r = t.cv.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  function onDown(t, e) {
    const g = t.geom;
    if (!g || e.button !== 0) return;
    const p = local(t, e);
    if (p.x < g.x0 || p.x > g.x0 + g.pw || p.y < g.y0 || p.y > g.y0 + g.ph) return;
    t.drag = { x: p.x, y: p.y, live: null };
    try { t.cv.setPointerCapture(e.pointerId); } catch (err) { /* fine */ }
    e.preventDefault();
  }

  function onMove(t, e) {
    if (!t.drag || !t.geom) return;
    const g = t.geom;
    const p = local(t, e);
    const x = Math.max(g.x0, Math.min(g.x0 + g.pw, p.x));
    const y = Math.max(g.y0, Math.min(g.y0 + g.ph, p.y));
    if (Math.abs(x - t.drag.x) < 3 && Math.abs(y - t.drag.y) < 3
        && !t.drag.live) return;
    t.drag.live = { x: Math.min(t.drag.x, x), y: Math.min(t.drag.y, y),
                    w: Math.abs(x - t.drag.x), h: Math.abs(y - t.drag.y) };
    drawTile(t);
  }

  function onUp(t, e) {
    if (!t.drag) return;
    const g = t.geom;
    const d = t.drag;
    t.drag = null;
    if (!g) return;
    const f = cur();
    if (!f) return;
    const toMs = (px) => g.ext[0] + ((px - g.x0) / g.pw) * (g.ext[1] - g.ext[0]);
    const toCsc = (py) => g.lo + ((py - g.y0) / g.ph) * (g.hi - g.lo + 1) - 0.5;
    const r1 = (v) => Math.round(v * 10) / 10;
    if (!d.live || (d.live.w < 3 && d.live.h < 3)) {
      // A click: one time sample, at the depth already chosen, if any.
      const p = local(t, e);
      const x = Math.max(g.x0, Math.min(g.x0 + g.pw, p.x));
      const ms = r1(toMs(x));
      const was = boxOf(f.id, t.gid);
      setBox(t, { sel_lo: was ? was.sel_lo : null,
                  sel_hi: was ? was.sel_hi : null,
                  t_lo_ms: ms, t_hi_ms: ms });
      return;
    }
    const L = d.live;
    let lo = Math.round(toCsc(L.y));
    let hi = Math.round(toCsc(L.y + L.h));
    // A CSD is a second derivative across depth; three contacts is the
    // floor. Widened rather than refused, as Single does.
    if (hi - lo < 2) hi = lo + 2;
    setBox(t, { sel_lo: Math.max(g.lo, lo), sel_hi: Math.min(g.hi, hi),
                t_lo_ms: r1(toMs(L.x)), t_hi_ms: r1(toMs(L.x + L.w)) });
  }

  /* Shared, by id (`<folder>|<gid>`), so a colleague sees the box. Null
     takes it away and the server's own box is used. */
  function setBox(t, b) {
    const f = cur();
    if (!f) return;
    const k = f.id + '|' + t.gid;
    if (b) {
      const rec = Object.assign({}, b, { at: now(), by: who() });
      mergeKey(BOX_KEY, k, rec);
      t.m.box = rec;
    } else {
      mergeKey(BOX_KEY, k, null);
      t.m.box = null;
    }
    fillTile(t);
    put('gridHead', gridHead(f));
  }

  /* ==================================================================
     For the harness
     ================================================================== */
  function reset() {
    if (S.poll) clearInterval(S.poll);
    if (ro) { try { ro.disconnect(); } catch (e) { /* fine */ } }
    ro = null;
    if (S.root && S.root.parentNode) S.root.remove();
    Object.assign(S, { root: null, nodes: {}, ctx: null, folders: null,
                       error: null, loadedAt: 0, loading: null, cur: null,
                       showArchived: false, job: null, poll: null,
                       runAll: null, built: null });
    S.jobGen += 1;
    tiles.clear(); rasters.clear(); versions.clear(); imgs.clear();
    lastGood.clear();
    rasterQ = []; rasterBusy = 0;
  }

  return {
    mount,
    reload: load,
    _state: () => ({
      cur: S.cur, showArchived: S.showArchived, folders: S.folders,
      job: S.job ? { id: S.job.id, status: S.job.status } : null,
      runAll: S.runAll ? Object.assign({}, S.runAll) : null,
      tiles: Array.from(tiles.keys()),
    }),
    _geom: (gid) => {
      const t = tiles.get(gid);
      if (!t || !t.geom || !t.cv) return null;
      const r = t.cv.getBoundingClientRect();
      return Object.assign({ left: r.left, top: r.top }, t.geom);
    },
    // What the tile last drew: the picture, the box or line, the sinks.
    _drawn: (gid) => {
      const t = tiles.get(gid);
      return t && t.drawn ? JSON.parse(JSON.stringify(t.drawn)) : null;
    },
    _params: (fid) => paramsOf(fid || S.cur),
    _box: (gid, fid) => boxOf(fid || S.cur, gid),
    _boxWords: boxWords,
    _verdict: verdictOf,
    _loading: () => S.loading,
    reset,
  };
})();
