/* ==========================================================================
   figure.js -- The figure builder, v2: grab what you see, make it a figure.

   The Figure builder button sits at the top right of Xplorefinder and of
   every ToolKit tool that can make figures. Pressing it grabs every plot on
   the page as it looks now -- its settings, its recording, its channels --
   and opens it as a draft figure. Nothing has to be set up again.

   What a figure is (backend/figkit, backend/figures.py):
     * one recording;
     * panels, each a plot from one tool, redrawn by that tool from its own
       numbers -- never a screenshot -- so a panel can be relabelled, put in
       another unit, cropped or set to a journal's size;
     * a footer that is always there and says where every panel came from;
     * versions. Exporting makes the next one and never changes the last:
       a figure is frozen once it is out.

   How the page is drawn. The server renders the page frame (title, footer,
   where each panel goes) and each panel as a tile of its own, from the same
   geometry the export uses. A word changed redraws one tile, and the old
   tile stays on screen, dimmed, until the new one lands. Tiles come back
   with the boxes of everything on them that can be clicked -- the title,
   each axis, the colour bar, the letter -- and clicking one opens a small
   editor for exactly that thing.

   Units are never typed. An axis offers the units its quantity can be
   shown in, and choosing one rescales the numbers; the words in front of
   the unit are yours.

   Sources. A view or tool says what is on its page with
   `BARRY.figure.source(id, {grab, palette, panelFor, openPanel})`.
   Xplorefinder's is below; each ToolKit tool registers its own.
   ========================================================================== */
'use strict';

BARRY.figure = (function () {
  let cat = null;               // /api/figkit/catalog
  let fig = null;               // the figure record (summary + versions)
  let layout = null;            // the working layout
  let fromV = null;             // the version the working layout came from
  let sel = { uid: null, part: null };
  let frame = null;             // the last frame answer
  const tiles = {};             // uid -> {sig, image, hits, resolved, error}
  const sources = {};
  let shell = null;             // the dialog's node
  let pop = null;               // the open click editor
  let refreshTimer = null;
  let frameSeq = 0;
  let draftTimer = null;
  let draftState = '';          // '', 'saving', 'saved', 'failed'
  let exporting = false;
  let lastExport = null;
  let problems = [];
  let keysOn = false;
  let resizeObs = null;

  const UNDO_MAX = 80;
  let undoStack = [];
  let redoStack = [];

  /* ==================================================================
     Sources: what is on screen, as panels
     ================================================================== */
  function source(id, def) {
    sources[id] = Object.assign({ id }, def || {});
    // A grab button already drawn for this tool can come alive now.
    for (const b of document.querySelectorAll('.fig-grab[data-src="' + id + '"]')) {
      b.disabled = false;
      b.title = grabTitle(id);
    }
  }

  function activeSourceId() {
    const view = (BARRY.state && BARRY.state.view) || '';
    if (view === 'toolkit') {
      const tk = BARRY.views.toolkit;
      const t = tk && typeof tk.tool === 'function' ? tk.tool() : null;
      if (t) return t;
    }
    return view || 'xplore';
  }

  function grabTitle(id) {
    const name = (sources[id] && sources[id].label) || 'this page';
    return 'Make a figure of what ' + name + ' is showing now: every plot, '
      + 'with its settings, as a draft you can finish later.';
  }

  /* The button, for anywhere a page draws plots. Disabled with a reason
     until the page's tool has said what it can draw. */
  function grabButton(opts) {
    const o = opts || {};
    const id = o.source || activeSourceId();
    const ready = !!sources[id];
    return el('button', {
      class: 'btn sm fig-grab' + (o.extra ? ' ' + o.extra : ''),
      'data-src': id, type: 'button',
      text: o.text || 'Figure builder',
      disabled: ready ? null : 'disabled',
      title: ready ? grabTitle(id)
        : 'Figures from ' + (o.name || id) + ' are not built yet.',
      onclick: (e) => { e.stopPropagation(); grab(id); },
    });
  }

  async function grab(id) {
    const sid = id || activeSourceId();
    const src = sources[sid];
    if (!src || typeof src.grab !== 'function') {
      toast('Figures from this page are not built yet.', null, 5000);
      return;
    }
    let got = null;
    try { got = await src.grab(); } catch (e) {
      toast('Could not read what is on screen: ' + e.message, 'err', 8000);
      return;
    }
    if (!got || !(got.panels || []).length) {
      toast(got && got.why ? got.why
        : 'There is nothing on screen to make a figure of yet.', null, 6000);
      return;
    }
    await ensureCatalog();
    const lay = startLayout(got);
    try {
      const res = await apiPost('/api/figures', { layout: lay });
      fig = res.figure;
      layout = res.figure.draft || lay;
      fromV = null;
    } catch (e) {
      toast('Could not start the figure: ' + e.message, 'err', 8000);
      return;
    }
    if (got.note) toast(got.note, null, 7000);
    BARRY.activity.log('figure.grab', {
      figure: fig.id, source: sid, panels: layout.panels.length,
    }, { identity: (layout.recording || {}).identity || {} });
    openBuilder();
  }

  /* A layout for what was grabbed: the profile last used, two columns
     wide, a grid the shape of the panels. */
  function startLayout(got) {
    const profile = BARRY.prefs.get('figure_profile', null)
      || (cat && cat.default_profile) || 'nature';
    const prof = profileOf(profile);
    const width = BARRY.prefs.get('figure_width_' + profile, null)
      || (prof && prof.widths.length ? prof.widths[prof.widths.length - 1].id
                                     : 'double');
    const panels = (got.panels || []).map((p, i) => Object.assign({
      uid: 'p' + (i + 1), row: 0, col: i, rowspan: 1, colspan: 1,
      title: '', axes: {}, link: {}, labels: {},
    }, p));
    const rows = Math.max(1, ...panels.map((p) => p.row + p.rowspan));
    const cols = Math.max(1, ...panels.map((p) => p.col + p.colspan));
    return {
      schema: 'fig/2', profile, width,
      height_mm: null, rows: Math.min(6, rows), cols: Math.min(4, cols),
      gap_mm: 4,
      title: got.title || (got.recording || {}).label || 'Figure',
      subtitle: '', recording: got.recording, panels,
      footer: { notes: '' },
    };
  }

  async function openFigure(fid, v) {
    await ensureCatalog();
    try {
      const res = await api('/api/figures/' + encodeURIComponent(fid));
      fig = res.figure;
    } catch (e) {
      toast('Could not open that figure: ' + e.message, 'err', 8000);
      return;
    }
    const vs = fig.versions || [];
    const pick = v != null ? vs.find((x) => x.v === Number(v)) : null;
    if (pick) {
      layout = JSON.parse(JSON.stringify(pick.layout));
      fromV = pick.v;
    } else {
      layout = JSON.parse(JSON.stringify(fig.draft || (vs.length
        ? vs[vs.length - 1].layout : null)));
      fromV = vs.length ? vs[vs.length - 1].v : null;
    }
    if (!layout) { toast('That figure has nothing in it.', null, 5000); return; }
    delete layout.v;
    openBuilder();
  }

  /* A file in Results, opened: which figure version it is, then that. */
  async function openRun(runId) {
    try {
      const got = await api('/api/figures/for-run/' + encodeURIComponent(runId));
      return openFigure(got.figure_id, got.v);
    } catch (e) {
      toast(e.message, null, 8000);
      return null;
    }
  }

  /* Results › Figures: every figure, drafts first, by recording. */
  let listArchived = false;
  async function paintList(host) {
    host.innerHTML = '';
    const bones = BARRY.skeleton ? BARRY.skeleton.into(host, 'card', 3) : null;
    let got = [];
    try {
      got = (await api('/api/figures' + (listArchived ? '?archived=1' : ''))).figures || [];
    } catch (e) {
      if (bones) bones();
      host.appendChild(el('p', { class: 'hint warn-line', text: e.message }));
      return;
    }
    if (bones) bones();
    host.innerHTML = '';
    host.appendChild(el('div', { class: 'fx-list-bar' }, [
      el('p', { class: 'hint', text: 'Press Figure builder on any page to '
        + 'grab what it shows. It waits here as a draft until you export it.' }),
      el('div', { class: 'spacer' }),
      el('label', { class: 'toggle sm' + (listArchived ? ' on' : '') }, [
        el('input', { type: 'checkbox', checked: listArchived ? 'checked' : null,
          onchange: (e) => { listArchived = e.target.checked; paintList(host); } }),
        el('span', { text: 'Show archived' }),
      ]),
    ]));
    if (!got.length) {
      host.appendChild(el('div', { class: 'tree-empty',
        text: 'No figures yet. Press Figure builder at the top right of '
            + 'Xplorefinder or a ToolKit tool.' }));
      return;
    }
    const groups = new Map();
    for (const f of got) {
      const k = ((f.recording || {}).label) || f.gid || 'Unfiled';
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(f);
    }
    const keys = Array.from(groups.keys()).sort(BARRY.ui.natCompare || undefined);
    for (const k of keys) {
      host.appendChild(el('div', { class: 'section-label', text: k }));
      const rows = groups.get(k).sort((a, b) =>
        String(b.updated || '').localeCompare(String(a.updated || '')));
      for (const f of rows) {
        const last = f.latest;
        host.appendChild(el('div', { class: 'fx-list-row' + (f.archived ? ' archived' : '') }, [
          last && last.files && last.files.png
            ? el('img', { class: 'fx-list-thumb', loading: 'lazy', alt: '',
                          src: '/api/figures/' + encodeURIComponent(f.id) + '/v/'
                             + last.v + '/file/png' })
            : el('div', { class: 'fx-list-thumb none', text: 'draft' }),
          el('div', { class: 'fx-list-what' }, [
            el('strong', { text: f.title || 'Figure' }),
            el('span', { class: 'hint', text: (last ? 'v' + last.v + ' of '
              + f.n_versions : 'a draft, not exported yet')
              + (f.updated ? ' \u00b7 ' + new Date(f.updated).toLocaleString() : '')
              + (f.by ? ' \u00b7 ' + f.by : '') }),
          ]),
          el('div', { class: 'spacer' }),
          el('button', { class: 'btn ghost sm', type: 'button', text: 'Open',
            onclick: () => openFigure(f.id) }),
          last && BARRY.figreplay ? el('button', { class: 'btn ghost sm', type: 'button',
            text: 'Walk through\u2026',
            onclick: () => BARRY.figreplay.start(f.id, last.v) }) : null,
          el('button', { class: 'btn ghost sm', type: 'button',
            text: f.archived ? 'Bring back' : 'Archive',
            title: f.archived ? 'Show it in the list again'
              : 'Hide it from this list. Nothing is deleted.',
            onclick: async () => {
              try {
                await apiPost('/api/figures/' + encodeURIComponent(f.id) + '/archive',
                              { on: !f.archived });
              } catch (e) { toast(e.message, 'err', 6000); }
              paintList(host);
            } }),
        ].filter(Boolean)));
      }
    }
  }

  async function ensureCatalog() {
    if (cat) return cat;
    try {
      cat = await api('/api/figkit/catalog');
    } catch (e) {
      cat = { adapters: [], units: {}, profiles: [], presets: [],
              colormaps: [], default_profile: 'nature' };
      toast('Could not read what figures can hold: ' + e.message, 'err', 8000);
    }
    return cat;
  }

  function profileOf(id) {
    return ((cat && cat.profiles) || []).find((p) => p.id === id) || null;
  }

  function adapterOf(tool) {
    return ((cat && cat.adapters) || []).find((a) => a.tool === tool) || null;
  }

  function plotOf(tool, plot) {
    const a = adapterOf(tool);
    return a ? (a.plots || []).find((p) => p.id === plot) || null : null;
  }

  function plotName(p) {
    const pl = plotOf(p.tool, p.plot);
    return (pl && pl.name) || p.plot;
  }

  /* ==================================================================
     The dialog
     ================================================================== */
  function openBuilder() {
    undoStack = [];
    redoStack = [];
    for (const k of Object.keys(tiles)) delete tiles[k];
    frame = null;
    sel = { uid: (layout.panels[0] || {}).uid || null, part: null };
    problems = [];
    lastExport = null;
    draftState = '';
    shell = el('div', { class: 'fx' }, [
      el('div', { class: 'mh fx-head', id: 'fxHead' }),
      el('div', { class: 'mb fx-body' }, [
        el('div', { class: 'fx-cols' }, [
          el('div', { class: 'fx-col fx-left', id: 'fxLeft' }),
          el('div', { class: 'fx-col fx-mid' }, [
            el('div', { class: 'fx-stage', id: 'fxStage' }, [
              el('div', { class: 'fx-sheet', id: 'fxSheet' }, [
                el('img', { class: 'fx-frame', id: 'fxFrame', alt: '' }),
                el('div', { class: 'fx-wait', id: 'fxWait' }, [
                  el('span', { class: 'spin' }),
                  el('span', { text: 'Drawing the figure…' }),
                ]),
              ]),
            ]),
            el('div', { class: 'chip-row fx-probs', id: 'fxProbs' }),
          ]),
          el('div', { class: 'fx-col fx-right', id: 'fxRight' }),
        ]),
      ]),
      el('div', { class: 'mf fx-foot', id: 'fxFoot' }),
    ]);
    showModal(shell);
    const box = document.getElementById('bigModalBox');
    if (box) box.classList.add('fx-box');
    wireKeys(true);
    watchSize(true);
    paint();
    refresh(0);
  }

  function shut() {
    closePop();
    wireKeys(false);
    watchSize(false);
    flushDraft();
    const box = document.getElementById('bigModalBox');
    if (box) box.classList.remove('fx-box');
    shell = null;
    closeModal();
  }

  function alive() { return !!(shell && shell.isConnected); }

  /* Every part, by its signature: only what changed is rebuilt. */
  function paint() {
    if (!alive()) return;
    const head = $('#fxHead');
    const left = $('#fxLeft');
    const right = $('#fxRight');
    const foot = $('#fxFoot');
    const sp = selPanel();
    BARRY.ui.sections(head, [
      { key: 'head', sig: [layout.title, fig && fig.id, fromV,
                           (fig && fig.versions || []).length,
                           undoStack.length, redoStack.length,
                           (layout.recording || {}).label],
        build: headPart, enter: false },
    ]);
    BARRY.ui.sections(left, [
      { key: 'shapes', sig: [layout.preset, layout.panels.length,
                             cat && cat.presets.length], build: shapesPart },
      { key: 'grid', sig: [layout.rows, layout.cols, sel.uid,
                           layout.panels.map((p) => [p.uid, p.row, p.col,
                             p.rowspan, p.colspan, p.plot, p.title]),
                           frame && frame.letters],
        build: gridPart },
      { key: 'panels', sig: [sel.uid, layout.panels.map((p) => [p.uid,
                             p.plot, p.title, p.row, p.col]),
                             frame && frame.letters],
        build: panelsPart },
      { key: 'palette', sig: [(layout.recording || {}).gid,
                              cat && cat.adapters.length],
        build: palettePart },
    ]);
    BARRY.ui.sections(right, [
      { key: 'page', sig: [layout.profile, layout.width, layout.height_mm,
                           layout.gap_mm, frame && frame.page_in],
        build: pagePart },
      { key: 'words', sig: [layout.title, layout.subtitle,
                            (layout.footer || {}).notes], build: wordsPart },
      { key: 'sel', sig: [sp && JSON.stringify(sp), sp && frame
                          && JSON.stringify(frame.about[sp.uid] || null),
                          frame && frame.letters && sp
                          && frame.letters[sp.uid]],
        build: selectedPart },
    ]);
    BARRY.ui.sections(foot, [
      { key: 'foot', sig: [draftState, exporting, problems,
                           lastExport && lastExport.v, fig && fig.id,
                           (fig && fig.versions || []).length],
        build: footPart, enter: false },
    ]);
  }

  /* ---------- head ---------- */
  function headPart() {
    const rec = layout.recording || {};
    const vs = (fig && fig.versions) || [];
    const kids = [
      el('h3', { text: 'Figure builder' }),
      el('span', { class: 'sub', text: (rec.label || rec.gid || 'a recording')
        + (fromV ? ' · working from v' + fromV : ' · draft') }),
      el('div', { class: 'spacer' }),
    ];
    if (vs.length && BARRY.ui.versionButton) {
      kids.push(BARRY.ui.versionButton({
        versions: vs.map((v) => ({ id: v.id, v: v.v, at: v.at, by: v.by,
                                   note: v.note || ('made on ' + (v.machine || '?')) })),
        value: fromV,
        producer: false,
        heading: 'Every version of this figure',
        sub: 'A version is never changed once it is exported. Opening one '
           + 'puts its layout in front of you; exporting makes the next.',
        lead: { name: 'Draft' },
        onpick: (v) => loadVersion(v.v),
      }));
    }
    kids.push(
      el('button', {
        class: 'btn ghost sm', text: '↶ Undo', type: 'button',
        title: undoStack.length ? 'Undo (Ctrl+Z) — ' + undoStack.length
          + ' step(s) back' : 'Nothing to undo yet',
        disabled: undoStack.length ? null : 'disabled', onclick: undo,
      }),
      el('button', {
        class: 'btn ghost sm', text: '↷', type: 'button',
        title: redoStack.length ? 'Redo (Ctrl+Shift+Z)' : 'Nothing to redo',
        disabled: redoStack.length ? null : 'disabled', onclick: redo,
      }),
      el('button', {
        class: 'close-x', type: 'button', title: 'Close (Esc). The draft is kept.',
        html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
        onclick: shut,
      }));
    return el('div', { class: 'fx-headrow' }, kids);
  }

  function loadVersion(v) {
    const row = ((fig && fig.versions) || []).find((x) => x.v === v);
    if (!row) return;
    change(() => {
      const keep = JSON.parse(JSON.stringify(row.layout));
      delete keep.v;
      for (const k of Object.keys(layout)) delete layout[k];
      Object.assign(layout, keep);
      fromV = v;
    });
    toast('Version ' + v + ' is in front of you. Exporting makes the next '
          + 'version; v' + v + ' stays as it is.', null, 6000);
  }

  /* ---------- left: shapes, grid, panels, palette ---------- */
  function shapesPart() {
    const box = el('div', { class: 'fx-shapes' });
    for (const p of (cat && cat.presets) || []) {
      const mini = el('span', { class: 'fx-shape-mini',
        style: 'grid-template-columns:repeat(' + p.cols + ',1fr);'
             + 'grid-template-rows:repeat(' + p.rows + ',1fr)' },
        p.cells.map((c) => el('i', {
          style: 'grid-row:' + (c[0] + 1) + '/span ' + c[2]
               + ';grid-column:' + (c[1] + 1) + '/span ' + c[3] })));
      box.appendChild(el('button', {
        type: 'button',
        class: 'fx-shape' + (layout.preset === p.id ? ' active' : ''),
        title: p.name + (layout.panels.length > p.cells.length
          ? ' — the ' + (layout.panels.length - p.cells.length)
            + ' panel(s) that do not fit go in rows underneath' : ''),
        onclick: () => change(() => applyPreset(p)),
      }, [mini, el('span', { class: 'fx-shape-n', text: p.name })]));
    }
    return el('div', {}, [
      el('div', { class: 'section-label', text: 'Shape' }),
      box,
    ]);
  }

  /* The same re-slotting figkit/layout.py does, so a click shows at once. */
  function applyPreset(p) {
    const order = layout.panels.slice().sort((a, b) =>
      (a.row - b.row) || (a.col - b.col));
    let rows = p.rows;
    order.forEach((pn, i) => {
      let r, c, rs, cs;
      if (i < p.cells.length) [r, c, rs, cs] = p.cells[i];
      else {
        const j = i - p.cells.length;
        r = p.rows + Math.floor(j / p.cols); c = j % p.cols; rs = 1; cs = 1;
      }
      Object.assign(pn, { row: r, col: c, rowspan: rs, colspan: cs });
      rows = Math.max(rows, r + rs);
    });
    layout.rows = Math.min(6, rows);
    layout.cols = Math.min(4, p.cols);
    layout.panels = order;
    layout.preset = p.id;
  }

  function letterOf(uid) {
    return (frame && frame.letters && frame.letters[uid]) || '';
  }

  function gridPart() {
    const wrap = el('div', { class: 'grid-wrap' });
    const occ = (r, c) => layout.panels.findIndex((p) =>
      r >= p.row && r < p.row + p.rowspan && c >= p.col && c < p.col + p.colspan);
    const heads = el('div', { class: 'grid-heads',
      style: 'grid-template-columns:repeat(' + layout.cols + ',1fr)' });
    for (let c = 0; c < layout.cols; c++) {
      const cc = c;
      heads.appendChild(el('div', { class: 'grid-head' }, [
        el('span', { class: 'gh-n', text: 'column ' + (cc + 1) }),
        layout.cols > 1 ? el('button', {
          class: 'gh-x', text: '×', type: 'button',
          title: 'Remove this column' + (colPanels(cc).length
            ? ' — ' + colPanels(cc).length + ' panel(s) in it go' : ''),
          onclick: (e) => { e.stopPropagation(); change(() => removeCol(cc)); },
        }) : null,
      ].filter(Boolean)));
    }
    wrap.appendChild(heads);

    const map = el('div', { class: 'grid-map',
      style: 'grid-template-columns:repeat(' + layout.cols + ',1fr)' });
    const cells = [];
    const paint = (from, to) => {
      const r0 = Math.min(from[0], to[0]), r1 = Math.max(from[0], to[0]);
      const c0 = Math.min(from[1], to[1]), c1 = Math.max(from[1], to[1]);
      for (const x of cells) {
        x.node.classList.toggle('span-preview',
          x.r >= r0 && x.r <= r1 && x.c >= c0 && x.c <= c1);
      }
    };
    const clear = () => cells.forEach((x) => x.node.classList.remove('span-preview'));

    for (let r = 0; r < layout.rows; r++) {
      for (let c = 0; c < layout.cols; c++) {
        const rr = r, cc = c;
        const at = occ(rr, cc);
        const pn = at >= 0 ? layout.panels[at] : null;
        const node = el('div', {
          class: 'grid-cell' + (pn ? ' filled' : '')
               + (pn && pn.uid === sel.uid ? ' sel' : ''),
          draggable: pn ? 'true' : null,
          title: pn ? (letterOf(pn.uid) + '  ' + (pn.title || plotName(pn))
                       + ' — drag it to move it')
                    : 'Empty — drag a plot here from the list below',
          ondragstart: (e) => {
            if (!pn) return;
            e.dataTransfer.setData('text/plain', 'move:' + pn.uid);
            e.dataTransfer.effectAllowed = 'move';
          },
          ondragover: (e) => { e.preventDefault(); node.classList.add('drop-over'); },
          ondragleave: () => node.classList.remove('drop-over'),
          ondrop: (e) => {
            e.preventDefault();
            node.classList.remove('drop-over');
            const got = e.dataTransfer.getData('text/plain') || '';
            if (got.startsWith('move:')) {
              const p = byUid(got.slice(5));
              if (p) change(() => { p.row = rr; p.col = cc; clamp(p); select(p.uid); });
            } else if (got.startsWith('add:')) {
              const [tool, plot] = got.slice(4).split('|');
              addPanel(tool, plot, rr, cc);
            }
          },
          onclick: () => { if (pn && pn.uid !== sel.uid) { select(pn.uid); paint_(); } },
        }, [
          el('span', { class: 'gc-n', text: pn ? letterOf(pn.uid) || '•' : '' }),
          pn ? el('span', { class: 'gc-ch', text: pn.title || plotName(pn) }) : null,
        ].filter(Boolean));
        node.dataset.r = String(rr);
        node.dataset.c = String(cc);
        if (pn) {
          const right = cc === pn.col + pn.colspan - 1;
          const foot = rr === pn.row + pn.rowspan - 1;
          if (right) node.appendChild(grip(pn, 'e'));
          if (foot) node.appendChild(grip(pn, 's'));
          if (right && foot) node.appendChild(grip(pn, 'se'));
        }
        cells.push({ r: rr, c: cc, node });
        map.appendChild(node);
      }
    }

    function grip(pn, side) {
      return el('div', {
        class: 'gc-grip ' + side,
        title: side === 's' ? 'Drag down to span more rows'
          : side === 'e' ? 'Drag across to span more columns'
            : 'Drag to span rows and columns',
        onpointerdown: (e) => {
          e.preventDefault();
          e.stopPropagation();
          const from = [pn.row, pn.col];
          let to = [pn.row + pn.rowspan - 1, pn.col + pn.colspan - 1];
          const at = (ev) => {
            let best = null, near = Infinity;
            for (const x of cells) {
              const b = x.node.getBoundingClientRect();
              const dx = Math.max(b.left - ev.clientX, 0, ev.clientX - b.right);
              const dy = Math.max(b.top - ev.clientY, 0, ev.clientY - b.bottom);
              if (dx * dx + dy * dy < near) { near = dx * dx + dy * dy; best = [x.r, x.c]; }
            }
            return best;
          };
          const move = (ev) => {
            const got = at(ev);
            if (!got) return;
            to = [side === 'e' ? to[0] : Math.max(from[0], got[0]),
                  side === 's' ? to[1] : Math.max(from[1], got[1])];
            paint(from, to);
          };
          const up = (ev) => {
            window.removeEventListener('pointermove', move);
            window.removeEventListener('pointerup', up);
            move(ev);
            clear();
            change(() => {
              pn.rowspan = Math.abs(to[0] - from[0]) + 1;
              pn.colspan = Math.abs(to[1] - from[1]) + 1;
              clamp(pn);
              select(pn.uid);
            });
          };
          window.addEventListener('pointermove', move);
          window.addEventListener('pointerup', up);
        },
      });
    }
    map.addEventListener('mouseleave', clear);
    wrap.appendChild(map);

    const rowsCol = el('div', { class: 'grid-rows',
      style: 'grid-template-rows:repeat(' + layout.rows + ',1fr)' });
    for (let r = 0; r < layout.rows; r++) {
      const rr = r;
      rowsCol.appendChild(el('div', { class: 'grid-rowh' }, [
        layout.rows > 1 ? el('button', {
          class: 'gh-x', text: '×', type: 'button',
          title: 'Remove this row' + (rowPanels(rr).length
            ? ' — ' + rowPanels(rr).length + ' panel(s) in it go' : ''),
          onclick: (e) => { e.stopPropagation(); change(() => removeRow(rr)); },
        }) : null,
      ].filter(Boolean)));
    }
    wrap.appendChild(rowsCol);
    wrap.appendChild(el('button', {
      class: 'grid-add col', text: '+', title: 'Add a column', type: 'button',
      disabled: layout.cols >= 4 ? 'disabled' : null,
      onclick: () => change(() => { layout.cols = Math.min(4, layout.cols + 1); }),
    }));
    wrap.appendChild(el('button', {
      class: 'grid-add row', text: '+', title: 'Add a row', type: 'button',
      disabled: layout.rows >= 6 ? 'disabled' : null,
      onclick: () => change(() => { layout.rows = Math.min(6, layout.rows + 1); }),
    }));

    const bin = el('div', {
      class: 'grid-bin', text: 'Drag a panel here to take it out',
      ondragover: (e) => { e.preventDefault(); bin.classList.add('over'); },
      ondragleave: () => bin.classList.remove('over'),
      ondrop: (e) => {
        e.preventDefault();
        bin.classList.remove('over');
        const got = e.dataTransfer.getData('text/plain') || '';
        if (got.startsWith('move:')) removePanel(got.slice(5));
      },
    });
    return el('div', {}, [
      el('div', { class: 'section-label', text: 'Grid' }),
      el('p', { class: 'hint', text: 'Drag a panel to move it, or drag its '
        + 'edge to make it span more cells.' }),
      wrap, bin,
    ]);
  }

  function panelsPart() {
    const list = el('div', { class: 'fx-plist' });
    const order = layout.panels.slice().sort((a, b) =>
      (a.row - b.row) || (a.col - b.col));
    for (const p of order) {
      const ab = frame && frame.about ? frame.about[p.uid] : null;
      list.appendChild(el('div', {
        class: 'panel-item' + (p.uid === sel.uid ? ' sel' : ''),
        onclick: () => { select(p.uid); paint_(); },
        oncontextmenu: (e) => { e.preventDefault(); select(p.uid); menuFor(p, e); },
      }, [
        el('div', { class: 'pi-top' }, [
          el('span', { class: 'fx-letter', text: letterOf(p.uid) || '•' }),
          el('span', { class: 'pi-name', text: p.title || plotName(p) }),
          el('button', {
            class: 'badbtn', text: '×', title: 'Take this panel out',
            type: 'button',
            onclick: (e) => { e.stopPropagation(); removePanel(p.uid); },
          }),
        ]),
        el('div', { class: 'pi-sub', text: ((ab && ab.tool_name) || p.tool)
          + ', ' + plotName(p) }),
      ]));
    }
    return el('div', {}, [
      el('div', { class: 'section-label', text: 'Panels' }), list,
    ]);
  }

  function palettePart() {
    const sid = srcIdFor(layout);
    const src = sources[sid];
    const items = src && typeof src.palette === 'function' ? src.palette(layout) : [];
    if (!items.length) {
      return el('div', {}, [
        el('div', { class: 'section-label', text: 'Add a plot' }),
        el('p', { class: 'hint', text: 'Grab from another page to add its '
          + 'plots: they are this recording’s too.' }),
      ]);
    }
    return el('div', {}, [
      el('div', { class: 'section-label', text: 'Add a plot of this recording' }),
      el('div', { class: 'fig-palette' }, items.map((it) => el('div', {
        class: 'fig-chip', draggable: 'true', text: it.name,
        title: it.name + ' — drag it into a cell, or click to put it in '
          + 'the first free one',
        ondragstart: (e) => {
          e.dataTransfer.setData('text/plain', 'add:' + it.tool + '|' + it.plot);
          e.dataTransfer.effectAllowed = 'copy';
        },
        onclick: () => addPanel(it.tool, it.plot),
      }))),
    ]);
  }

  /* ---------- right: page, words, the selected panel ---------- */
  function pagePart() {
    const prof = profileOf(layout.profile);
    const profs = (cat && cat.profiles) || [];
    const seg = (items, on, pick) => el('div', { class: 'seg fx-seg' },
      items.map((it) => el('button', {
        type: 'button', class: it.id === on ? 'active' : null, text: it.name,
        title: it.title || null, onclick: () => pick(it.id),
      })));
    const page = frame && frame.page_in;
    const maxH = prof ? prof.max_height_mm : 600;
    const hNow = layout.height_mm || (page ? Math.round(page[1] * 25.4) : '');
    return el('div', {}, [
      el('div', { class: 'section-label', text: 'Journal' }),
      seg(profs.map((p) => ({ id: p.id, name: p.name })), layout.profile,
          (id) => change(() => {
            const np = profileOf(id);
            layout.profile = id;
            BARRY.prefs.set('figure_profile', id);
            const keep = np && np.widths.find((w) => w.id === layout.width);
            if (!keep && np) {
              layout.width = np.widths[np.widths.length - 1].id;
            }
            layout.height_mm = null;
          })),
      el('div', { class: 'section-label', text: 'Width' }),
      prof ? seg(prof.widths.map((w) => ({ id: w.id,
        name: w.name, title: w.mm + ' mm across' })), layout.width,
                 (id) => change(() => {
                   layout.width = id;
                   BARRY.prefs.set('figure_width_' + layout.profile, id);
                   if (prof.heights && prof.heights[id]) layout.height_mm = null;
                 })) : null,
      el('div', { class: 'fx-pair' }, [
        ui_field('Height (mm)', el('input', {
          type: 'number', min: '30', max: String(maxH), step: '1',
          value: String(hNow), 'data-fk': 'fx-h',
          title: 'Up to ' + maxH + ' mm for ' + (prof ? prof.name : 'this page'),
          onchange: (e) => {
            const v = parseFloat(e.target.value);
            change(() => { layout.height_mm = isFinite(v)
              ? Math.max(30, Math.min(maxH, v)) : null; });
          },
        })),
        ui_field('Gap (mm)', el('input', {
          type: 'number', min: '0', max: '20', step: '0.5',
          value: String(layout.gap_mm != null ? layout.gap_mm : 4),
          'data-fk': 'fx-gap',
          onchange: (e) => {
            const v = parseFloat(e.target.value);
            change(() => { layout.gap_mm = isFinite(v) ? Math.max(0, Math.min(20, v)) : 4; });
          },
        })),
      ]),
      page ? el('p', { class: 'hint', text: Math.round(page[0] * 25.4) + ' × '
        + Math.round(page[1] * 25.4) + ' mm' + (prof ? ', ' + prof.name
        + ' type' : '') }) : null,
    ].filter(Boolean));
  }

  function ui_field(label, control, hint) {
    return BARRY.ui.field ? BARRY.ui.field({ label, control, hint })
      : el('div', { class: 'field' }, [el('label', { text: label }), control]);
  }

  function textBox(value, fk, onset, opts) {
    const o = opts || {};
    const tag = o.area ? 'textarea' : 'input';
    return el(tag, {
      type: o.area ? null : 'text', value: value || '', 'data-fk': fk,
      rows: o.area ? '3' : null, placeholder: o.placeholder || null,
      oninput: debounceInput((e) => change(() => onset(e.target.value),
                                           { coalesce: fk }), 450),
    });
  }

  function wordsPart() {
    return el('div', {}, [
      el('div', { class: 'section-label', text: 'Words' }),
      ui_field('Title', textBox(layout.title, 'fx-title',
                                (v) => { layout.title = v; })),
      ui_field('Subtitle', textBox(layout.subtitle, 'fx-sub',
                                   (v) => { layout.subtitle = v; })),
      ui_field('Note in the footer', textBox((layout.footer || {}).notes,
        'fx-notes', (v) => { layout.footer = Object.assign({}, layout.footer,
                                                           { notes: v }); },
        { area: true, placeholder: 'Printed at the end of the footer' })),
    ]);
  }

  function selectedPart() {
    const p = selPanel();
    if (!p) {
      return el('div', {}, [
        el('div', { class: 'section-label', text: 'Panel' }),
        el('p', { class: 'hint', text: 'Click a panel on the figure to work '
          + 'on it. Click its title, an axis or its colour bar to change '
          + 'just that.' }),
      ]);
    }
    const ab = (frame && frame.about && frame.about[p.uid]) || {};
    const labels = p.labels || {};
    const toggles = [
      ['letter', 'Letter', labels.letter !== false, true],
      ['scalebar', 'Scale bars instead of axes', !!labels.scalebar, ab.scalebar],
      ['anatomy', 'Layer names', !!labels.anatomy, ab.anatomy],
      ['stats', 'Stats marks', !!labels.stats, ab.stats],
    ].filter((t) => t[3]);
    const kids = [
      el('div', { class: 'section-label', text: 'Panel ' + (letterOf(p.uid) || '') }),
      el('p', { class: 'fx-say' }, [
        el('strong', { text: p.title || plotName(p) }),
        el('span', { text: ' — ' + (ab.tool_name || p.tool) + ', '
          + (ab.plot_name || plotName(p)) }),
      ]),
      ab.phrases && ab.phrases.length
        ? el('p', { class: 'hint fx-line', text: ab.phrases.join(' · ') })
        : null,
      ab.error ? el('p', { class: 'hint warn-line', text: ab.error }) : null,
      ui_field('Panel title', textBox(p.title, 'fx-pt-' + p.uid,
                                      (v) => { p.title = v; })),
      el('div', { class: 'fx-toggles' }, toggles.map(([k, name, on]) =>
        el('label', { class: 'toggle sm' + (on ? ' on' : '') }, [
          el('input', { type: 'checkbox', checked: on ? 'checked' : null,
            onchange: (e) => change(() => {
              p.labels = Object.assign({}, p.labels, { [k]: e.target.checked });
            }) }),
          el('span', { text: name }),
        ]))),
      linkRow(p, ab),
      el('div', { class: 'fx-acts' }, [
        el('button', { class: 'btn ghost sm', type: 'button',
          text: 'Open in ' + (ab.tool_name || 'its tool'),
          title: 'Set ' + (ab.tool_name || 'the tool') + ' up the way this '
            + 'panel was grabbed', onclick: () => openInTool(p) }),
        el('button', { class: 'btn ghost sm', type: 'button', text: 'Duplicate',
          onclick: () => duplicate(p.uid) }),
        el('button', { class: 'btn ghost sm', type: 'button',
          text: 'Back to the tool’s labels',
          title: 'Forget this panel’s words, units, ranges and links',
          onclick: () => change(() => { p.axes = {}; p.link = {}; }) }),
      ]),
      moreAbout(ab),
    ];
    return el('div', {}, kids.filter(Boolean));
  }

  function linkRow(p, ab) {
    const axes = Object.entries(ab.axes || {}).filter(([, d]) => d.linkable);
    if (!axes.length) return null;
    const name = { x: 'across', y: 'up', c: 'colour' };
    return el('div', { class: 'fx-links' }, [
      el('span', { class: 'hint', text: 'Shared with matching panels:' }),
      ...axes.map(([k, d]) => {
        const on = !p.link || p.link[k] !== false;
        return el('button', {
          type: 'button', class: 'fx-chain' + (on ? ' on' : ''),
          title: on ? 'This ' + (d.words || k) + ' scale is shared with every '
              + 'panel showing ' + (d.words || k) + '. Click to give this '
              + 'panel its own.'
            : 'This panel keeps its own ' + (d.words || k) + ' scale. Click '
              + 'to share it again.',
          onclick: () => change(() => {
            p.link = Object.assign({}, p.link, { [k]: on ? false : true });
          }),
        }, [el('span', { class: 'fx-chain-i', text: on ? '⛓' : '✂' }),
            el('span', { text: (d.words || k) + ' (' + name[k] + ')' })]);
      }),
    ]);
  }

  function moreAbout(ab) {
    const f = ab.fields || {};
    const rows = Object.entries(f).filter(([k]) => k !== 'params');
    const params = Object.entries(f.params || {})
      .filter(([k]) => k !== 'events');
    if (!rows.length && !params.length) return null;
    const fmt = (v) => (Array.isArray(v) ? (v.length > 12
      ? v.slice(0, 12).join(', ') + ', and ' + (v.length - 12) + ' more'
      : v.join(', ')) : (v && typeof v === 'object' ? JSON.stringify(v) : String(v)));
    return el('details', { class: 'fx-more', 'data-keep': 'fx-more' }, [
      el('summary', { text: 'More about where this panel came from' }),
      el('dl', { class: 'kv' }, rows.concat(params).flatMap(([k, v]) => [
        el('dt', { text: k.replace(/_/g, ' ') }),
        el('dd', { text: v === null || v === undefined ? '—' : fmt(v) }),
      ])),
    ]);
  }

  /* ---------- foot ---------- */
  function footPart() {
    const vs = (fig && fig.versions) || [];
    const next = 1 + Math.max(0, ...vs.map((v) => v.v || 0));
    const say = exporting ? 'Exporting v' + next + '…'
      : draftState === 'saving' ? 'Saving the draft…'
        : draftState === 'saved' ? 'Draft saved'
          : draftState === 'failed' ? 'The draft could not be saved'
            : (fig ? 'A draft until you export it' : '');
    const files = lastExport ? ['png', 'svg', 'pdf'].filter((f) =>
      (lastExport.files || {})[f]).map((f) => el('a', {
      class: 'btn ghost sm', text: f.toUpperCase(),
      href: '/api/figures/' + encodeURIComponent(fig.id) + '/v/'
          + lastExport.v + '/file/' + f + '?download=1',
      title: 'Download version ' + lastExport.v + ' as ' + f.toUpperCase(),
    })) : [];
    return el('div', { class: 'fx-footrow' }, [
      el('span', { class: 'note fx-state', text: say }),
      problems.length ? el('span', { class: 'stat-chip warn',
        text: problems.length + ' panel problem' + (problems.length === 1 ? '' : 's'),
        title: problems.join('\n') }) : null,
      el('div', { class: 'spacer' }),
      lastExport ? el('span', { class: 'hint', text: 'v' + lastExport.v
        + ' filed in Results · download:' }) : null,
      ...files,
      el('button', { class: 'btn ghost', type: 'button', text: 'Close',
                     onclick: shut }),
      el('button', {
        class: 'btn primary', type: 'button', id: 'fxExport',
        text: exporting ? 'Exporting…' : 'Export v' + next,
        disabled: exporting ? 'disabled' : null,
        title: 'PNG, SVG and PDF, filed under Results › Figures. v' + next
          + ' is frozen once it is made (Ctrl+E).',
        onclick: exportIt,
      }),
    ].filter(Boolean));
  }

  /* ==================================================================
     The page: frame + tiles
     ================================================================== */
  function refresh(ms) {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(drawPage, ms == null ? 280 : ms);
  }

  async function drawPage() {
    if (!alive()) return;
    const seq = ++frameSeq;
    const sheet = $('#fxSheet');
    if (sheet) sheet.classList.add('busy');
    let got;
    try {
      got = await apiPost('/api/figkit/frame', { layout, dpi: frameDpi() });
    } catch (e) {
      if (seq !== frameSeq || !alive()) return;
      showPageError(e.message);
      return;
    }
    if (seq !== frameSeq || !alive()) return;
    frame = got;
    problems = got.problems || [];
    fitSheet();
    const img = $('#fxFrame');
    if (img && img.src !== got.image) img.src = got.image;
    const wait = $('#fxWait');
    if (wait) wait.classList.add('hidden');
    placeTiles();
    drawFrameHits();
    paint();
    // Tiles whose picture moved, two at a time.
    const want = layout.panels.filter((p) => !tiles[p.uid]
      || tiles[p.uid].sig !== got.sigs[p.uid]).map((p) => p.uid);
    let next = 0;
    const worker = async () => {
      while (next < want.length) {
        const uid = want[next++];
        await drawTile(uid, got.sigs[uid], seq);
      }
    };
    await Promise.all([worker(), worker()]);
    if (sheet && seq === frameSeq) sheet.classList.remove('busy');
  }

  function frameDpi() {
    const stage = $('#fxStage');
    const w = stage ? stage.clientWidth : 700;
    const page = frame && frame.page_in ? frame.page_in[0] : 7.2;
    // Enough pixels for the sheet as shown, on this screen, and no more.
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    return Math.max(60, Math.min(220, Math.round(w * dpr / page)));
  }

  async function drawTile(uid, sig, seq) {
    const t = tileNode(uid);
    if (t) t.classList.add('stale');
    let got;
    try {
      got = await apiPost('/api/figkit/tile', { layout, uid, dpi: frameDpi() });
    } catch (e) {
      if (t) { t.classList.remove('stale'); t.classList.add('failed'); t.title = e.message; }
      return;
    }
    if (!alive()) return;
    // A newer page may have moved this tile's picture again; a tile is only
    // kept if it is the picture the newest frame asked for.
    if (frame && frame.sigs[uid] !== sig) return;
    const first = !tiles[uid];
    tiles[uid] = { sig, image: got.image, hits: got.hits || {},
                   resolved: got.resolved || {}, error: got.error };
    const node = tileNode(uid);
    if (!node) return;
    node.classList.remove('stale', 'failed');
    const img = node.querySelector('img');
    img.src = got.image;
    drawTileHits(uid);
    if (first && BARRY.motion) BARRY.motion.enter(node, { i: 0 });
  }

  function tileNode(uid) {
    const sheet = $('#fxSheet');
    return sheet ? sheet.querySelector('.fx-tile[data-uid="' + uid + '"]') : null;
  }

  function placeTiles() {
    const sheet = $('#fxSheet');
    if (!sheet || !frame) return;
    const live = new Set(layout.panels.map((p) => p.uid));
    for (const n of sheet.querySelectorAll('.fx-tile')) {
      if (!live.has(n.dataset.uid)) n.remove();
    }
    for (const p of layout.panels) {
      const b = frame.boxes[p.uid];
      if (!b) continue;
      let node = tileNode(p.uid);
      if (!node) {
        node = el('div', {
          class: 'fx-tile', 'data-uid': p.uid,
          oncontextmenu: (e) => { e.preventDefault(); select(p.uid); paint_(); menuFor(p, e); },
        }, [el('img', { alt: '' }), el('div', { class: 'fx-hits' })]);
        sheet.appendChild(node);
      }
      node.style.left = (b[0] * 100) + '%';
      node.style.top = (b[1] * 100) + '%';
      node.style.width = ((b[2] - b[0]) * 100) + '%';
      node.style.height = ((b[3] - b[1]) * 100) + '%';
      node.classList.toggle('sel', p.uid === sel.uid);
      if (tiles[p.uid]) drawTileHits(p.uid);
    }
  }

  const PART_WORDS = {
    title: 'the panel title', letter: 'the letter', x: 'the axis across',
    y: 'the axis up the side', c: 'the colour bar', plot: 'this panel',
  };

  function drawTileHits(uid) {
    const node = tileNode(uid);
    const t = tiles[uid];
    if (!node || !t) return;
    const host = node.querySelector('.fx-hits');
    host.innerHTML = '';
    // The plot first, so the smaller things over it take the click.
    const order = ['plot', 'x', 'y', 'c', 'title', 'letter'];
    for (const part of order) {
      const h = t.hits[part];
      if (!h) continue;
      host.appendChild(el('div', {
        class: 'fx-hit fx-hit-' + part
             + (sel.uid === uid && sel.part === part ? ' on' : ''),
        style: 'left:' + (h[0] * 100) + '%;top:' + (h[1] * 100) + '%;width:'
             + ((h[2] - h[0]) * 100) + '%;height:' + ((h[3] - h[1]) * 100) + '%',
        title: 'Click to change ' + PART_WORDS[part],
        onclick: (e) => {
          e.stopPropagation();
          select(uid, part);
          paint_();
          openPop(uid, part, e);
        },
      }));
    }
  }

  function drawFrameHits() {
    const sheet = $('#fxSheet');
    if (!sheet || !frame) return;
    for (const n of sheet.querySelectorAll(':scope > .fx-hit')) n.remove();
    for (const [part, h] of Object.entries(frame.hits || {})) {
      sheet.appendChild(el('div', {
        class: 'fx-hit fx-hit-' + part,
        style: 'left:' + (h[0] * 100) + '%;top:' + (h[1] * 100) + '%;width:'
             + ((h[2] - h[0]) * 100) + '%;height:' + ((h[3] - h[1]) * 100) + '%',
        title: part === 'fig_title' ? 'Click to change the title'
                                    : 'Click to change the subtitle',
        onclick: (e) => { e.stopPropagation(); openPop(null, part, e); },
      }));
    }
  }

  function fitSheet() {
    const stage = $('#fxStage');
    const sheet = $('#fxSheet');
    if (!stage || !sheet || !frame) return;
    const [w, h] = frame.page_in;
    const maxW = stage.clientWidth - 16;
    const maxH = Math.max(260, window.innerHeight * 0.72);
    const k = Math.max(0.1, Math.min(maxW / w, maxH / h));
    sheet.style.width = Math.round(w * k) + 'px';
    sheet.style.height = Math.round(h * k) + 'px';
  }

  function watchSize(on) {
    if (resizeObs) { resizeObs.disconnect(); resizeObs = null; }
    if (!on || typeof ResizeObserver !== 'function') return;
    const stage = $('#fxStage');
    if (!stage) return;
    resizeObs = new ResizeObserver(() => fitSheet());
    resizeObs.observe(stage);
  }

  function showPageError(msg) {
    const wait = $('#fxWait');
    if (wait) {
      wait.classList.remove('hidden');
      wait.innerHTML = '';
      wait.appendChild(el('div', { class: 'wiz-verdict low', text: msg }));
    }
    const sheet = $('#fxSheet');
    if (sheet) sheet.classList.remove('busy');
  }

  /* ==================================================================
     Click editors
     ================================================================== */
  function closePop() {
    if (pop) { pop.remove(); pop = null; }
    document.removeEventListener('mousedown', popAway, true);
  }

  function popAway(e) {
    if (pop && !pop.contains(e.target)) closePop();
  }

  function openPop(uid, part, ev) {
    closePop();
    const p = uid ? byUid(uid) : null;
    let body;
    if (part === 'fig_title' || part === 'fig_subtitle') {
      const k = part === 'fig_title' ? 'title' : 'subtitle';
      body = [el('div', { class: 'section-label', text: k === 'title'
                          ? 'Title' : 'Subtitle' }),
              textBox(layout[k], 'fxp-' + k, (v) => { layout[k] = v; })];
    } else if (!p) {
      return;
    } else if (part === 'title') {
      body = [el('div', { class: 'section-label', text: 'Panel title' }),
              textBox(p.title, 'fxp-t-' + uid, (v) => { p.title = v; })];
    } else if (part === 'letter') {
      body = [el('div', { class: 'section-label', text: 'Letter ' + letterOf(uid) }),
              el('p', { class: 'hint', text: 'Letters follow reading order and '
                + 'move with the panels.' }),
              el('label', { class: 'toggle sm' + ((p.labels || {}).letter !== false ? ' on' : '') }, [
                el('input', { type: 'checkbox',
                  checked: (p.labels || {}).letter !== false ? 'checked' : null,
                  onchange: (e) => change(() => {
                    p.labels = Object.assign({}, p.labels, { letter: e.target.checked });
                  }) }),
                el('span', { text: 'Print this panel’s letter' }),
              ])];
    } else if (part === 'x' || part === 'y' || part === 'c') {
      body = axisEditor(p, part);
    } else {
      body = panelActions(p);
    }
    pop = el('div', { class: 'fx-pop', role: 'dialog' }, body.filter(Boolean));
    document.body.appendChild(pop);
    const r = pop.getBoundingClientRect();
    /* Beside the pointer, or beside the thing itself when the click came
       from the keyboard (no pointer position). */
    let px = ev.clientX, py = ev.clientY;
    if (!px && !py && ev.target && ev.target.getBoundingClientRect) {
      const t = ev.target.getBoundingClientRect();
      px = t.right; py = t.top;
    }
    const x = Math.min(window.innerWidth - r.width - 12, Math.max(12, px + 10));
    const y = Math.min(window.innerHeight - r.height - 12, Math.max(12, py + 10));
    pop.style.left = x + 'px';
    pop.style.top = y + 'px';
    if (BARRY.motion) BARRY.motion.pop(pop);
    const first = pop.querySelector('input[type=text], textarea');
    if (first) setTimeout(() => { try { first.focus(); } catch (e) { /* gone */ } }, 20);
    setTimeout(() => document.addEventListener('mousedown', popAway, true), 0);
  }

  function factorOf(q, unit) {
    const u = (cat && cat.units && cat.units[q]) || null;
    return u && u.factors ? u.factors[unit] : null;
  }

  /* Words, unit, range, crop, link -- and the colour map for a colour bar.
     The unit is chosen, never typed; the range is said in the unit shown. */
  function axisEditor(p, part) {
    const ab = (frame && frame.about && frame.about[p.uid]) || {};
    const d = (ab.axes || {})[part];
    if (!d) return [el('p', { class: 'hint', text: 'This panel draws no such axis.' })];
    const mine = Object.assign({}, (p.axes || {})[part]);
    const shown = d.units.indexOf(mine.unit) >= 0 ? mine.unit : d.unit;
    const fBase = factorOf(d.quantity, d.unit);
    const fShow = factorOf(d.quantity, shown);
    const k = (fBase && fShow) ? fBase / fShow : 1;
    const res = ((tiles[p.uid] || {}).resolved || {})[part];
    const fmt = (v) => (v == null ? '' : String(+((v * k).toPrecision(6))));
    const save = (patch) => change(() => {
      p.axes = Object.assign({}, p.axes);
      p.axes[part] = Object.assign({}, p.axes[part], patch);
    });
    const say = (words, unit) => (words || d.words || part) + (unit ? ' (' + unit + ')' : '');
    const out = [
      el('div', { class: 'section-label', text: part === 'c' ? 'Colour bar'
        : part === 'x' ? 'Axis across' : 'Axis up the side' }),
      ui_field('Words', textBox(mine.words, 'fxp-w-' + p.uid + part,
        (v) => { p.axes = Object.assign({}, p.axes);
                 p.axes[part] = Object.assign({}, p.axes[part], { words: v }); },
        { placeholder: d.words || '' })),
    ];
    if (d.units.length > 1) {
      out.push(el('div', { class: 'section-label', text: 'Unit' }));
      out.push(el('div', { class: 'seg fx-seg' }, d.units.map((u) => el('button', {
        type: 'button', class: u === shown ? 'active' : null, text: u || '(none)',
        title: 'Show these numbers in ' + u + ' — they are rescaled, '
          + 'not relabelled',
        onclick: () => { save({ unit: u }); closePop(); },
      }))));
    } else if (d.unit) {
      out.push(el('p', { class: 'hint', text: 'Shown in ' + d.unit
        + (d.convertible ? '' : ', which is the only unit this can be in') + '.' }));
    }
    out.push(el('p', { class: 'hint fx-preview-line', text: 'Prints as: '
      + say(mine.words, shown) }));
    if (d.convertible || part === 'c') {
      const lo = el('input', { type: 'number', step: 'any', 'data-fk': 'fxp-lo',
        value: mine.range ? String(mine.range[0]) : fmt(res && res[0]) });
      const hi = el('input', { type: 'number', step: 'any', 'data-fk': 'fxp-hi',
        value: mine.range ? String(mine.range[1]) : fmt(res && res[1]) });
      const setRange = () => {
        const a = parseFloat(lo.value), b = parseFloat(hi.value);
        if (isFinite(a) && isFinite(b) && a !== b) {
          save({ range: [Math.min(a, b), Math.max(a, b)], unit: shown });
        }
      };
      lo.addEventListener('change', setRange);
      hi.addEventListener('change', setRange);
      out.push(el('div', { class: 'fx-pair' }, [
        ui_field('From' + (shown ? ' (' + shown + ')' : ''), lo),
        ui_field('To' + (shown ? ' (' + shown + ')' : ''), hi),
      ]));
      if (part !== 'c') {
        const crop = mine.crop || 'cut';
        out.push(el('div', { class: 'seg fx-seg' }, [
          ['cut', 'Cut to the data', 'Never past where the numbers end'],
          ['extend', 'Extend', 'Exactly the range above, blank where there '
            + 'are no numbers'],
        ].map(([id, name, why]) => el('button', {
          type: 'button', class: crop === id ? 'active' : null, text: name,
          title: why, onclick: () => save({ crop: id }),
        }))));
      }
      if (mine.range) {
        out.push(el('button', { class: 'linkish', type: 'button',
          text: 'Back to the data’s own range',
          onclick: () => { save({ range: null }); closePop(); } }));
      }
    }
    if (d.linkable) {
      const on = !p.link || p.link[part] !== false;
      out.push(el('label', { class: 'toggle sm' + (on ? ' on' : '') }, [
        el('input', { type: 'checkbox', checked: on ? 'checked' : null,
          onchange: (e) => change(() => {
            p.link = Object.assign({}, p.link, { [part]: e.target.checked });
          }) }),
        el('span', { text: 'Share this scale with matching panels' }),
      ]));
    }
    if (part === 'c' && p.params && (cat.colormaps || []).length) {
      out.push(el('div', { class: 'section-label', text: 'Colours' }));
      out.push(el('div', { class: 'cmap-row' }, cat.colormaps.map((c) => el('button', {
        type: 'button',
        class: 'cmap-btn' + (c.id === (p.params.cmap || 'jet') ? ' active' : ''),
        title: c.name + (c.note ? ' — ' + c.note : ''),
        onclick: () => change(() => { p.params = Object.assign({}, p.params, { cmap: c.id }); }),
      }, [el('span', { class: 'grad', style: 'background:linear-gradient(to right,'
            + (c.swatch || ['#888']).join(',') + ')' }),
          el('span', { class: 'nm', text: c.name })]))));
    }
    out.push(el('button', { class: 'linkish', type: 'button',
      text: 'Back to the tool’s own label',
      onclick: () => { change(() => {
        p.axes = Object.assign({}, p.axes); delete p.axes[part];
      }); closePop(); } }));
    return out;
  }

  function panelActions(p) {
    const ab = (frame && frame.about && frame.about[p.uid]) || {};
    return [
      el('div', { class: 'section-label', text: (letterOf(p.uid) || '')
        + '  ' + (p.title || plotName(p)) }),
      el('p', { class: 'hint', text: (ab.phrases || []).join(' · ') }),
      el('div', { class: 'fx-acts' }, actionButtons(p, ab, true)),
    ];
  }

  function actionButtons(p, ab, closing) {
    const done = (fn) => () => { if (closing) closePop(); fn(); };
    return [
      el('button', { class: 'btn ghost sm', type: 'button', text: 'Duplicate',
        onclick: done(() => duplicate(p.uid)) }),
      el('button', { class: 'btn ghost sm', type: 'button',
        text: 'Open in ' + (ab.tool_name || 'its tool'),
        onclick: done(() => openInTool(p)) }),
      el('button', { class: 'btn ghost sm', type: 'button', text: 'Share every scale',
        onclick: done(() => change(() => { p.link = {}; })) }),
      el('button', { class: 'btn ghost sm', type: 'button', text: 'Its own scales',
        onclick: done(() => change(() => { p.link = { x: false, y: false, c: false }; })) }),
      el('button', { class: 'btn ghost sm', type: 'button',
        text: 'Back to the tool’s labels',
        onclick: done(() => change(() => { p.axes = {}; p.labels = {}; p.link = {}; })) }),
      el('button', { class: 'btn ghost sm danger', type: 'button', text: 'Take it out',
        onclick: done(() => removePanel(p.uid)) }),
    ];
  }

  /* The right-click menu: the same acts, where the pointer is. */
  function menuFor(p, e) {
    closePop();
    const ab = (frame && frame.about && frame.about[p.uid]) || {};
    pop = el('div', { class: 'fx-pop fx-menu', role: 'menu' },
             actionButtons(p, ab, true));
    document.body.appendChild(pop);
    const r = pop.getBoundingClientRect();
    pop.style.left = Math.min(window.innerWidth - r.width - 8, e.clientX) + 'px';
    pop.style.top = Math.min(window.innerHeight - r.height - 8, e.clientY) + 'px';
    if (BARRY.motion) BARRY.motion.pop(pop);
    setTimeout(() => document.addEventListener('mousedown', popAway, true), 0);
  }

  /* ==================================================================
     Changing the layout
     ================================================================== */
  let coalesceKey = null;
  let coalesceAt = 0;

  /* Every edit goes through here: one undo step, a repaint of what moved,
     a new page, and the draft kept. Typing in one box is one step, not one
     per letter (`coalesce`). */
  function change(fn, opts) {
    const o = opts || {};
    const now = Date.now();
    const same = o.coalesce && o.coalesce === coalesceKey && now - coalesceAt < 4000;
    if (!same) {
      undoStack.push(JSON.stringify(layout));
      if (undoStack.length > UNDO_MAX) undoStack.shift();
      redoStack = [];
    }
    coalesceKey = o.coalesce || null;
    coalesceAt = now;
    fn();
    if (sel.uid && !byUid(sel.uid)) sel = { uid: (layout.panels[0] || {}).uid || null, part: null };
    paint();
    refresh();
    saveDraftSoon();
  }

  function restore(json) {
    const got = JSON.parse(json);
    for (const k of Object.keys(layout)) delete layout[k];
    Object.assign(layout, got);
    if (sel.uid && !byUid(sel.uid)) sel = { uid: (layout.panels[0] || {}).uid || null, part: null };
    coalesceKey = null;
    paint();
    refresh();
    saveDraftSoon();
  }

  function undo() {
    if (!undoStack.length) { toast('Nothing to undo.', null, 2000); return; }
    redoStack.push(JSON.stringify(layout));
    restore(undoStack.pop());
  }

  function redo() {
    if (!redoStack.length) { toast('Nothing to redo.', null, 2000); return; }
    undoStack.push(JSON.stringify(layout));
    restore(redoStack.pop());
  }

  function paint_() { paint(); placeTiles(); }

  function select(uid, part) {
    sel = { uid, part: part || null };
  }

  function selPanel() { return sel.uid ? byUid(sel.uid) : null; }
  function byUid(uid) { return layout.panels.find((p) => p.uid === uid) || null; }

  function newUid() {
    let n = layout.panels.length + 1;
    while (byUid('p' + n)) n += 1;
    return 'p' + n;
  }

  function firstFreeCell() {
    for (let r = 0; r < layout.rows; r++) {
      for (let c = 0; c < layout.cols; c++) {
        if (!layout.panels.some((p) => r >= p.row && r < p.row + p.rowspan
                                    && c >= p.col && c < p.col + p.colspan)) {
          return [r, c];
        }
      }
    }
    if (layout.rows < 6) { layout.rows += 1; return [layout.rows - 1, 0]; }
    return [0, 0];
  }

  function clamp(p) {
    p.row = Math.max(0, Math.min(p.row, layout.rows - 1));
    p.col = Math.max(0, Math.min(p.col, layout.cols - 1));
    p.rowspan = Math.max(1, Math.min(p.rowspan, layout.rows - p.row));
    p.colspan = Math.max(1, Math.min(p.colspan, layout.cols - p.col));
  }

  function colPanels(c) { return layout.panels.filter((p) => c >= p.col && c < p.col + p.colspan); }
  function rowPanels(r) { return layout.panels.filter((p) => r >= p.row && r < p.row + p.rowspan); }

  function removeCol(c) {
    layout.panels = layout.panels.filter((p) => {
      const inside = c >= p.col && c < p.col + p.colspan;
      if (inside && p.colspan === 1) return false;
      if (inside) p.colspan -= 1;
      if (p.col > c) p.col -= 1;
      return true;
    });
    layout.cols = Math.max(1, layout.cols - 1);
    layout.panels.forEach(clamp);
    layout.preset = null;
  }

  function removeRow(r) {
    layout.panels = layout.panels.filter((p) => {
      const inside = r >= p.row && r < p.row + p.rowspan;
      if (inside && p.rowspan === 1) return false;
      if (inside) p.rowspan -= 1;
      if (p.row > r) p.row -= 1;
      return true;
    });
    layout.rows = Math.max(1, layout.rows - 1);
    layout.panels.forEach(clamp);
    layout.preset = null;
  }

  function removePanel(uid) {
    const p = byUid(uid);
    if (!p) return;
    if (layout.panels.length <= 1) {
      toast('A figure needs one panel. Add another before taking this one out.',
            null, 5000);
      return;
    }
    const name = p.title || plotName(p);
    change(() => { layout.panels = layout.panels.filter((x) => x.uid !== uid); });
    toast('Took out ' + name + '. Ctrl+Z puts it back.', null, 4000);
  }

  function duplicate(uid) {
    const p = byUid(uid);
    if (!p) return;
    change(() => {
      const q = JSON.parse(JSON.stringify(p));
      q.uid = newUid();
      const at = firstFreeCell();
      q.row = at[0]; q.col = at[1]; q.rowspan = 1; q.colspan = 1;
      layout.panels.push(q);
      select(q.uid);
    });
  }

  function srcIdFor(lay) {
    const tools = new Set((lay.panels || []).map((p) => p.tool));
    if (tools.has('xplore') || !tools.size) return 'xplore';
    return Array.from(tools)[0];
  }

  async function addPanel(tool, plot, row, col) {
    const src = sources[tool] || sources[srcIdFor(layout)];
    let spec = null;
    try {
      spec = src && typeof src.panelFor === 'function'
        ? await src.panelFor(tool, plot, layout) : null;
    } catch (e) { spec = null; }
    if (!spec) {
      toast('Could not set that plot up from what is open. Open the '
            + 'recording in its tool and grab from there.', null, 6000);
      return;
    }
    change(() => {
      const at = row != null && col != null ? [row, col] : firstFreeCell();
      const p = Object.assign({ title: '', axes: {}, link: {}, labels: {} }, spec, {
        uid: newUid(), row: at[0], col: at[1], rowspan: 1, colspan: 1,
      });
      layout.panels.push(p);
      select(p.uid);
    });
  }

  async function openInTool(p) {
    const src = sources[p.tool];
    if (!src || typeof src.openPanel !== 'function') {
      toast('Opening this in its tool is not built yet.', null, 5000);
      return;
    }
    try {
      const said = await src.openPanel(p, layout);
      if (said) toast(said, 'ok', 6000);
    } catch (e) {
      toast('Could not open it: ' + e.message, 'err', 8000);
    }
  }

  /* ==================================================================
     Draft and export
     ================================================================== */
  function saveDraftSoon() {
    if (!fig) return;
    clearTimeout(draftTimer);
    draftState = 'saving';
    draftTimer = setTimeout(saveDraft, 1500);
  }

  async function saveDraft() {
    draftTimer = null;
    if (!fig) return;
    try {
      await apiPost('/api/figures/' + encodeURIComponent(fig.id) + '/draft',
                    { layout });
      draftState = 'saved';
    } catch (e) {
      draftState = 'failed';
    }
    if (alive()) paint();
  }

  function flushDraft() {
    if (draftTimer) { clearTimeout(draftTimer); saveDraft(); }
  }

  async function exportIt() {
    if (exporting || !fig) return;
    exporting = true;
    paint();
    try {
      const res = await apiPost('/api/figkit/export', {
        layout, figure_id: fig.id, from_v: fromV,
      });
      lastExport = res.version;
      const full = await api('/api/figures/' + encodeURIComponent(fig.id));
      fig = full.figure;
      fromV = res.version.v;
      problems = res.problems || [];
      toast('Version ' + res.version.v + ' is filed under Results › Figures.',
            'ok', 6000);
      BARRY.activity.log('figure.export', {
        figure: fig.id, v: res.version.v, run_id: res.run_id,
        panels: layout.panels.map((p) => p.tool + ':' + p.plot),
        profile: layout.profile, width: layout.width,
      }, { identity: (layout.recording || {}).identity || {} });
      if (BARRY.refreshSync) BARRY.refreshSync();
    } catch (e) {
      toast('The export did not work: ' + e.message, 'err', 9000);
    } finally {
      exporting = false;
      if (alive()) {
        paint();
        const foot = $('#fxFoot');
        if (lastExport && foot && BARRY.motion) BARRY.motion.land(foot, { sound: true });
      }
    }
  }

  /* ==================================================================
     Keys
     ================================================================== */
  function keys(e) {
    if (!alive()) return;
    if (e.key === 'Escape') {
      e.preventDefault(); e.stopPropagation();
      if (pop) closePop(); else shut();
      return;
    }
    if (isTyping(e)) return;
    const mod = e.ctrlKey || e.metaKey;
    const k = e.key.toLowerCase();
    if (mod && k === 'z') {
      e.preventDefault(); e.stopPropagation();
      if (e.shiftKey) redo(); else undo();
      return;
    }
    if (mod && k === 'e') { e.preventDefault(); e.stopPropagation(); exportIt(); return; }
    const p = selPanel();
    if (!p) return;
    if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault(); e.stopPropagation(); removePanel(p.uid); return;
    }
    const step = { ArrowUp: [-1, 0], ArrowDown: [1, 0],
                   ArrowLeft: [0, -1], ArrowRight: [0, 1] }[e.key];
    if (step) {
      e.preventDefault(); e.stopPropagation();
      change(() => { p.row += step[0]; p.col += step[1]; clamp(p); });
    }
  }

  function wireKeys(on) {
    if (on === keysOn) return;
    keysOn = on;
    if (on) document.addEventListener('keydown', keys, true);
    else document.removeEventListener('keydown', keys, true);
  }

  /* ==================================================================
     Xplorefinder's source
     ================================================================== */
  const XPLORE_PLOTS = ['traces', 'voltage', 'csd', 'theta', 'bandpower',
                        'spectrogram', 'scalogram'];

  function xploreRecording(sess) {
    const id = sess.identity || {};
    const info = sess.info || {};
    return {
      gid: id.gid || null, label: id.label || info.name || sess.path,
      path: sess.path, invert: sess.invert !== false,
      identity: id,
      fs_text: info.fs ? Math.round(info.fs) + ' Hz' : null,
    };
  }

  /* What a pane asks the server for, as a panel's params -- plus the three
     things that live on the recording rather than the pane. */
  function xploreParams(XF, index, sess) {
    const view = BARRY.views.xplore;
    let spec = null;
    try { spec = view.panelSpec(index); } catch (e) { spec = null; }
    const out = Object.assign({}, spec || {});
    delete out.path; delete out.invert; delete out.panel;
    const pane = XF.panes[index] || {};
    if (sess.gain) out.gain = sess.gain;
    const ylim = pane.ylim != null ? pane.ylim : sess.ylim;
    if (ylim != null) out.ylim = ylim;
    if ((sess.events || []).length) {
      out.events = sess.events.map((ev) => (typeof ev === 'number' ? { start: ev }
        : { start: ev.start, end: ev.end }));
      out.events_source = (sess.eventsMeta || {}).name || null;
    }
    return out;
  }

  /* The panes' places on screen, as a grid: their tops are the rows and
     their lefts the columns, whatever shape the pane grid is in. */
  function gridFromScreen(indices) {
    const rects = indices.map((i) => {
      const box = document.querySelector('#paneGrid > [data-pane-at="' + i + '"]');
      return box ? box.getBoundingClientRect() : null;
    });
    if (rects.some((r) => !r || !r.width)) {
      const cols = Math.min(3, indices.length);
      return indices.map((_, k) => ({ row: Math.floor(k / cols), col: k % cols,
                                      rowspan: 1, colspan: 1 }));
    }
    const cut = (vals) => {
      const out = [];
      vals.slice().sort((a, b) => a - b).forEach((v) => {
        if (!out.length || v - out[out.length - 1] > 12) out.push(v);
      });
      return out;
    };
    const tops = cut(rects.map((r) => r.top));
    const lefts = cut(rects.map((r) => r.left));
    const near = (list, v) => list.reduce((best, x, i) =>
      (Math.abs(x - v) < Math.abs(list[best] - v) ? i : best), 0);
    return rects.map((r) => {
      const row = near(tops, r.top);
      const col = near(lefts, r.left);
      const colEnd = lefts.filter((x) => x < r.right - 12).length;
      const rowEnd = tops.filter((x) => x < r.bottom - 12).length;
      return { row, col, rowspan: Math.max(1, rowEnd - row),
               colspan: Math.max(1, colEnd - col) };
    });
  }

  function xploreGrab() {
    const view = BARRY.views.xplore;
    const XF = view && view.state;
    if (!XF) return null;
    const sess = XF.sessions[XF.active] || null;
    if (!sess) return { why: 'Open a recording first, then grab it.' };
    const all = (XF.panes || []).map((p, i) => ({ p, i })).filter(({ p }) =>
      p && XF.sessions[p.sessionId] && p.panel !== 'video' && p.panel !== 'tracking');
    const mine = all.filter(({ p }) => p.sessionId === sess.id);
    const others = all.length - mine.length;
    if (!mine.length) return { why: 'None of the panes is showing this recording.' };

    // A probe laid out across the panes is one panel of the whole probe.
    const probe = mine.length >= 2 && mine.every(({ p }) => p.colTag && p.channels)
      && new Set(mine.map(({ p }) => p.panel || 'traces')).size === 1;
    let panels;
    if (probe) {
      const first = mine[0];
      const params = xploreParams(XF, first.i, sess);
      delete params.channels;
      params.probe = sess.probe || 'h10d';
      params.probe_view = true;
      panels = [{ tool: 'xplore', plot: first.p.panel || 'traces',
                  title: '', params, row: 0, col: 0, rowspan: 1, colspan: 1 }];
    } else {
      const spots = gridFromScreen(mine.map(({ i }) => i));
      panels = mine.map(({ p, i }, k) => Object.assign({
        tool: 'xplore', plot: p.panel || 'traces',
        title: p.colLabel || '', params: xploreParams(XF, i, sess),
      }, spots[k]));
    }
    return {
      recording: xploreRecording(sess),
      title: (sess.identity && sess.identity.label) || (sess.info || {}).name,
      panels,
      note: others ? others + ' pane(s) of another recording were left out: '
        + 'a figure is one recording.' : null,
    };
  }

  function xploreSessionFor(lay) {
    const XF = BARRY.views.xplore && BARRY.views.xplore.state;
    if (!XF) return null;
    const path = (lay.recording || {}).path;
    return Object.values(XF.sessions || {}).find((s) => s.path === path) || null;
  }

  source('xplore', {
    label: 'Xplorefinder',
    grab: xploreGrab,
    palette: () => XPLORE_PLOTS.map((id) => ({
      tool: 'xplore', plot: id, name: (plotOf('xplore', id) || {}).name || id })),
    panelFor: (tool, plot, lay) => {
      if (tool !== 'xplore') return null;
      // Settings from a panel already in the figure, so the new one is of
      // the same seconds and channels; else from the recording on screen.
      const near = lay.panels.find((p) => p.tool === 'xplore');
      const params = near ? JSON.parse(JSON.stringify(near.params || {})) : {};
      const sess = xploreSessionFor(lay);
      if (!near && sess) {
        Object.assign(params, { t0: sess.t0, t1: sess.t0 + sess.span,
          highpass: sess.hp, lowpass: sess.lp, notch: sess.notch,
          channels: Array.from(sess.sel).sort((a, b) => a - b),
          bad_channels: Array.from(sess.bad) });
      }
      delete params.probe_view; delete params.probe_columns;
      if ((plot === 'spectrogram' || plot === 'scalogram') && !params.tf_channels) {
        const first = (params.channels || [])[0];
        params.tf_channels = [first != null ? first : 0];
        params.fmin = params.fmin != null ? params.fmin : 20;
        params.fmax = params.fmax != null ? params.fmax : 1000;
      }
      if (plot === 'bandpower' && params.channel == null) {
        params.channel = (params.channels || [0])[0];
      }
      return { tool: 'xplore', plot, params };
    },
    openPanel: async (p, lay) => {
      const view = BARRY.views.xplore;
      setView('xplore');
      let sess = xploreSessionFor(lay);
      if (!sess) {
        sess = await view.open(lay.recording.path,
                               { invert: lay.recording.invert !== false });
      }
      if (!sess) throw new Error('The recording would not open.');
      const q = p.params || {};
      if (q.t0 != null && q.t1 != null) { sess.t0 = +q.t0; sess.span = Math.max(0.05, q.t1 - q.t0); }
      sess.hp = q.highpass || 0; sess.lp = q.lowpass || 0; sess.notch = q.notch || 0;
      if (Array.isArray(q.channels) && q.channels.length) sess.sel = new Set(q.channels);
      if (q.gain) sess.gain = q.gain;
      view.refreshAll();
      return 'Xplorefinder is showing panel ' + (letterOf(p.uid) || '')
        + ': its seconds, filters and channels.';
    },
  });

  /* ==================================================================
     The old entry points
     ================================================================== */
  // `open(XF, sess)` was the builder seeded from the screen; that is a grab.
  function open() { return grab('xplore'); }

  /* A figure from the old builder, rebuilt: its recipe becomes a v2 layout
     on the server (figkit/legacy.py) and opens as a new draft. */
  async function reopen(xfState, session, recipe, plan) {
    await ensureCatalog();
    try {
      const got = await apiPost('/api/figkit/legacy', {
        recipe, run: (plan || {}).run || {} });
      const lay = got.layout;
      if (session) lay.recording = Object.assign({}, lay.recording, xploreRecording(session));
      const res = await apiPost('/api/figures', { layout: lay });
      fig = res.figure;
      layout = res.figure.draft || lay;
      fromV = null;
      openBuilder();
    } catch (e) {
      toast('Could not rebuild that figure: ' + e.message, 'err', 8000);
    }
  }

  return {
    open, reopen, grab, grabButton, source, openFigure, openRun, paintList,
    layout: () => layout,
    figure: () => fig,
    frame: () => frame,
    redraw: () => { paint(); refresh(0); },
    change: (fn) => change(fn),
    sources: () => Object.keys(sources),
    /* One Xplorefinder pane's params, as a panel would carry them -- what the
       walk-through reads back (figreplay.js). */
    paramsOf: (index) => {
      const XF = BARRY.views.xplore && BARRY.views.xplore.state;
      const pane = XF && XF.panes[index];
      const sess = pane && XF.sessions[pane.sessionId];
      return sess ? xploreParams(XF, index, sess) : null;
    },
    exportNow: exportIt,
    close: () => { if (alive()) shut(); },
  };
})();
