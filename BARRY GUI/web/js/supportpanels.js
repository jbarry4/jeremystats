/* ==========================================================================
   supportpanels.js -- which support panels each add-on pops up, how each
   one starts, and how they are arranged (2026-10-20, granular 2026-10-21).

   "In the profile have a section called support panel preferences, where
   people can choose what support panels they'd like to have pop up in what
   arrangement for each Xplorefinder add-on."  And then: "super granular...
   select the width/height as percentages... a final mini popout that lets
   you drag things. Allow duplicate modes, e.g. 3 voltage traces. Then for
   each allow to choose default span, gain, channels selected, filter, and
   for the spectrogram/scalogram their presets."

   Every add-on that opens a second window of panels -- Checkup, Spotter,
   Panning, StrataScope, Braid -- asks `plan(mode, defaults, sess)` for what
   to open instead of hard-coding it. With nothing chosen, the add-on's own
   defaults stand, exactly as before. A choice is kept in preferences
   (`support_panels`), per add-on:

     open      whether the window opens at all
     panels    up to eight, in reading order, the same kind more than once
               if wanted; each with its own channels, filter, band, colours
               and (traces) gain, any of them left "as the add-on sets it"
     shape     a named arrangement (xplore.js layoutOf knows each), or
     layout    rows in percent of the window's height, each with its panels'
               widths in percent of the row: drawn in the arrangement editor
     span      seconds the window shows; empty follows the main window

   Span is the window's, not a panel's: every panel in one window reads one
   recording on one clock, so they cannot each show a different stretch.

     overview  the second window's overview strip: shown, hidden, or as
               that kind of window was last left
     main      the same choices for the add-on's MAIN window (2026-10-22:
               "we can modify the details of the support panels, but not the
               details of the main panel"): panels, channels, filter, band,
               gain, span and arrangement. Its first panel is always the
               traces, which every add-on reads its window from.

     plan(mode, defaults, sess)  { specs, shape, layout, span } to open, or
                                 null (turned off). A chosen panel that is
                                 one of `defaults` keeps the add-on's own
                                 settings for whatever was left unchosen.
     opts(plan)                  the popOutPanes options that carry it.
     applyMain(mode, defaults, sess, split, fill)
                                 lay out the main window as chosen (or the
                                 add-on's defaults, exactly as before), and
                                 return the main plan or null.
     restoreMain()               undo what applyMain set, on leaving.
     section()                   the Profile's "Support panel preferences",
                                 with copying someone else's (presets kind
                                 `support_panels`, GUI_logs/presets).
   ========================================================================== */
'use strict';

BARRY.supportPanels = (function () {
  const KEY = 'support_panels';
  const MAX = 8;

  /* The add-ons with a support window, their defaults as the add-ons
     themselves open them, and the shape those defaults had. */
  const ADDONS = [
    { mode: 'curate', name: 'Checkup', panels: ['csd'], shape: null },
    { mode: 'spotter', name: 'Spotter',
      panels: ['csd', 'voltage', 'spectrogram'], shape: 'cols' },
    { mode: 'panning', name: 'Panning',
      panels: ['csd', 'voltage', 'spectrogram'], shape: 'cols' },
    { mode: 'strata', name: 'StrataScope',
      panels: ['csd', 'theta', 'voltage', 'spectrogram'], shape: 'linked' },
    { mode: 'cfc', name: 'Braid', panels: ['bandpower', 'spectrogram'],
      shape: 'cols' },
    { mode: 'braces', name: 'Braces review',
      panels: ['csd', 'theta', 'voltage', 'spectrogram'], shape: 'linked' },
    // Lock's own (2026-10-26: "Panel preferences has been GREAT so far! Can
    // we get it for Lock too?"), starting from Braces' defaults.
    { mode: 'lock', name: 'Lock review',
      panels: ['csd', 'theta', 'voltage', 'spectrogram'], shape: 'linked' },
    // The Arc's review opens no second window: its main window only.
    { mode: 'arcmode', name: 'The Arc\u2019s review', panels: [], shape: null,
      aid: false },
  ];
  // Every main window starts as the add-ons always laid it out: the traces.
  const MAIN_DEFAULT = ['traces'];

  /* The panels a support window can show: Xplorefinder's own list when it
     has loaded, else the ones the add-ons use. */
  const FALLBACK = [
    { id: 'traces', name: 'Voltage traces' },
    { id: 'csd', name: 'CSD' }, { id: 'theta', name: 'Theta' },
    { id: 'voltage', name: 'Voltage raster' },
    { id: 'spectrogram', name: 'Spectrogram' },
    { id: 'scalogram', name: 'Scalogram' },
    { id: 'bandpower', name: 'Band power' },
  ];
  const xf = () => {
    const xp = BARRY.views && BARRY.views.xplore;
    return (xp && xp.state) || {};
  };
  function catalog() {
    const defs = xf().panelDefs || [];
    return defs.length ? defs.map((d) => ({ id: d.id, name: d.name }))
                       : FALLBACK;
  }
  const nameOf = (id) => (catalog().find((p) => p.id === id)
                          || FALLBACK.find((p) => p.id === id) || {}).name || id;
  const isTF = (id) => id === 'spectrogram' || id === 'scalogram';

  /* ---------- the choices a panel has ---------- */

  const CHANNELS = [
    ['default', 'As the add-on sets them'],
    ['all', 'Every channel'],
    ['even', 'Even-numbered'], ['odd', 'Odd-numbered'],
    ['every4', 'Every 4th'], ['every8', 'Every 8th'],
    ['first16', 'First 16'], ['first32', 'First 32'], ['first64', 'First 64'],
    ['custom', 'These channels…'],
  ];
  /* [id, label, hp, lp]: a band-pass in Hz, 0 meaning that edge is open. */
  const FILTERS = [
    ['window', 'The window’s filter'],
    ['raw', 'None (raw)', 0, 0],
    ['lfp', 'LFP 1–300 Hz', 1, 300],
    ['theta', 'Theta 4–12 Hz', 4, 12],
    ['gamma', 'Gamma 30–80 Hz', 30, 80],
    ['ripple', 'Ripple 150–250 Hz', 150, 250],
    ['spikes', 'Spikes 300–6000 Hz', 300, 6000],
    ['custom', 'Custom…'],
  ];
  /* [id, label, fmin, fmax] for a spectrogram or scalogram. */
  const BANDS = [
    ['default', 'As the add-on sets it'],
    ['b1_250', '1–250 Hz', 1, 250],
    ['b1_50', '1–50 Hz (slow)', 1, 50],
    ['b4_100', '4–100 Hz (theta to gamma)', 4, 100],
    ['b100_300', '100–300 Hz (ripples)', 100, 300],
    ['b20_1000', '20–1000 Hz', 20, 1000],
    ['custom', 'Custom…'],
  ];
  const TFMODES = [['default', 'As the add-on sets it'],
                   ['stack', 'Stacked, one per channel'],
                   ['mean', 'Averaged into one']];
  const CMAP_FALLBACK = ['jet', 'viridis', 'magma', 'inferno', 'gray']
    .map((id) => ({ id, name: id }));
  const cmaps = () => {
    const got = xf().colormaps || [];
    return got.length ? got : CMAP_FALLBACK;
  };
  /* The filter presets saved in Xplorefinder (GUI_logs), offered beside the
     built-in ones as `p:<id or name>`. */
  const savedFilters = () => ((xf().presets || {}).filters || [])
    .map((p) => ['p:' + (p.id || p.name), p.name + '  (saved)',
                 +p.highpass || 0, +p.lowpass || 0, +p.notch || 0]);

  /* "1-16, 33, 40-48" -> the channel numbers it names. */
  function parseList(text) {
    const out = new Set();
    for (const part of String(text || '').split(/[\s,;]+/)) {
      const m = /^(\d+)(?:\s*[-–]\s*(\d+))?$/.exec(part);
      if (!m) continue;
      const a = +m[1], b = m[2] != null ? +m[2] : a;
      for (let k = Math.min(a, b); k <= Math.max(a, b) && out.size < 2048; k++) {
        out.add(k);
      }
    }
    return out;
  }

  /* Positions in the recording's channel list, or null for "as it was". */
  function positions(e, chs) {
    const how = e.channels || 'default';
    if (how === 'default' || !chs.length) return null;
    const num = (c, i) => (c && c.number != null ? +c.number : i + 1);
    let idx = chs.map((c, i) => i);
    if (how === 'even') idx = idx.filter((i) => num(chs[i], i) % 2 === 0);
    else if (how === 'odd') idx = idx.filter((i) => num(chs[i], i) % 2 === 1);
    else if (how === 'every4') idx = idx.filter((i) => i % 4 === 0);
    else if (how === 'every8') idx = idx.filter((i) => i % 8 === 0);
    else if (/^first\d+$/.test(how)) idx = idx.slice(0, +how.slice(5));
    else if (how === 'custom') {
      const want = parseList(e.chText);
      idx = idx.filter((i) => want.has(num(chs[i], i)));
    }
    return idx.length ? idx : null;
  }

  function filterOf(e) {
    const how = e.filter || 'window';
    if (how === 'window') return null;
    const notch = e.notch ? 60 : 0;
    if (how === 'custom') {
      return { hp: Math.max(0, +e.hp || 0), lp: Math.max(0, +e.lp || 0), notch };
    }
    const row = FILTERS.concat(savedFilters()).find((f) => f[0] === how);
    if (!row) return null;
    return { hp: row[2] || 0, lp: row[3] || 0,
             notch: notch || (row[4] || 0) };
  }

  function bandOf(e) {
    const how = e.band || 'default';
    if (how === 'default') return null;
    if (how === 'custom') {
      const lo = +e.fmin, hi = +e.fmax;
      return (lo >= 0 && hi > lo) ? [lo, hi] : null;
    }
    const row = BANDS.find((b) => b[0] === how);
    return row && row.length > 2 ? [row[2], row[3]] : null;
  }

  /* ---------- arrangements ---------- */

  /* How n panes can be arranged by name (xplore.js layoutOf knows each). */
  function shapesFor(n) {
    if (n === 2) return [['cols', 'Side by side'], ['rows', 'Stacked']];
    if (n === 3) {
      return [['cols', 'Three across'], ['rows', 'Stacked'],
              ['top1', 'One large on top'], ['top2', 'One large below']];
    }
    if (n === 4) {
      return [['linked', 'Two by two'], ['rows', 'Stacked'],
              ['cols', 'Four across']];
    }
    return [];
  }

  /* Whole percentages that sum to exactly 100. */
  function even100(k) {
    const base = Math.floor(100 / k);
    return Array.from({ length: k }, (x, i) => (i < 100 - base * k ? base + 1 : base));
  }
  function to100(vals) {
    const v = vals.map((x) => Math.max(1, +x || 1));
    const sum = v.reduce((a, b) => a + b, 0);
    const out = v.map((x) => Math.round((x / sum) * 100));
    out[out.length - 1] += 100 - out.reduce((a, b) => a + b, 0);
    return out;
  }
  function gridLayout(n) {
    const per = n <= 1 ? 1 : (n <= 4 ? 2 : Math.ceil(Math.sqrt(n)));
    const rows = [];
    for (let i = 0; i < n; i += per) rows.push(Math.min(per, n - i));
    const hs = even100(rows.length);
    return { rows: rows.map((k, r) => ({ h: hs[r], cols: even100(k) })) };
  }
  /* The named shape, written out as rows, so the editor starts from what
     the window would have opened with. */
  function shapeLayout(shape, n) {
    const row = (k, h) => ({ h, cols: even100(k) });
    if (n <= 1) return { rows: [row(1, 100)] };
    if (shape === 'cols') return { rows: [row(n, 100)] };
    if (shape === 'rows') {
      const hs = even100(n);
      return { rows: hs.map((h) => row(1, h)) };
    }
    if (shape === 'top1' && n === 3) return { rows: [row(1, 50), row(2, 50)] };
    if (shape === 'top2' && n === 3) return { rows: [row(2, 50), row(1, 50)] };
    return gridLayout(n);
  }
  const countOf = (lay) => (lay && Array.isArray(lay.rows))
    ? lay.rows.reduce((k, r) => k + ((r && r.cols) || []).length, 0) : 0;
  function fitLayout(lay, n) {
    if (!lay || countOf(lay) !== n) return null;
    return { rows: lay.rows.map((r) => ({ h: +r.h || 1,
                                          cols: r.cols.map((w) => +w || 1) })) };
  }
  const layoutWords = (lay) => {
    if (!lay) return '';
    const rs = lay.rows;
    return rs.length + (rs.length === 1 ? ' row' : ' rows') + ': '
      + rs.map((r) => r.h + '% high'
               + (r.cols.length > 1 ? ' (' + r.cols.join(' / ') + '% wide)' : ''))
          .join(', ');
  };

  /* Rows of slots, each slot carrying its panel: the one model the editor
     and the list share, so a panel moved between rows takes its settings. */
  function toRows(panels, layout) {
    const lay = layout || gridLayout(panels.length);
    let k = 0;
    return lay.rows.map((r) => ({
      h: r.h, cols: r.cols.map((w) => ({ w, e: panels[k++] })),
    }));
  }
  function fromRows(rows) {
    const live = rows.filter((r) => r.cols.length);
    const hs = to100(live.map((r) => r.h));
    return {
      panels: live.flatMap((r) => r.cols.map((c) => c.e)),
      layout: { rows: live.map((r, i) => ({ h: hs[i],
                                            cols: to100(r.cols.map((c) => c.w)) })) },
    };
  }

  /* ---------- what is kept ---------- */

  function all() {
    try {
      const got = BARRY.prefs.get(KEY, {});
      return (got && typeof got === 'object') ? got : {};
    } catch (e) { return {}; }
  }

  function addon(mode) { return ADDONS.find((a) => a.mode === mode) || null; }

  /* A panel as kept: an old choice was just its id. */
  const entry = (p) => (typeof p === 'string' ? { panel: p }
                        : Object.assign({}, p || {}));

  /* Whether a stored add-on carries a second-window choice (it may hold only
     a main-window one). */
  const AID_KEYS = ['open', 'panels', 'shape', 'layout', 'span', 'overview'];
  const hasAid = (c) => !!c && AID_KEYS.some((k) => c[k] != null);

  /* What this person chose for an add-on, filled in from its defaults. */
  function choice(mode) {
    const a = addon(mode) || { panels: [], shape: null };
    const c = all()[mode] || {};
    const panels = (Array.isArray(c.panels) && c.panels.length
      ? c.panels : a.panels).slice(0, MAX).map(entry)
      .filter((e) => e.panel);
    const shapes = shapesFor(panels.length).map((s) => s[0]);
    return {
      open: c.open !== false,
      panels,
      shape: shapes.includes(c.shape) ? c.shape
        : (shapes.includes(a.shape) ? a.shape : (shapes[0] || null)),
      layout: fitLayout(c.layout, panels.length),
      span: +c.span > 0 ? +c.span : null,
      overview: c.overview === true || c.overview === false ? c.overview : null,
      custom: hasAid(c),
    };
  }

  function save(mode, c) {
    const every = Object.assign({}, all());
    const main = (every[mode] || {}).main;
    if (c === null) {
      // Back to the add-on's own second window; a main-window choice stays.
      if (main) every[mode] = { main }; else delete every[mode];
    } else {
      every[mode] = { open: c.open, panels: c.panels, shape: c.shape,
                      layout: c.layout || null, span: c.span || null,
                      overview: c.overview == null ? null : c.overview };
      if (main) every[mode].main = main;
    }
    try { BARRY.prefs.set(KEY, every); } catch (e) { /* this session only */ }
    publishSoon();
  }

  /* The main window's choice: the same fields, no `open` (it is always
     there) and no overview (its More menu has its own). Its first panel is
     the traces, whatever is stored. */
  function choiceMain(mode) {
    const m = (all()[mode] || {}).main || {};
    let panels = (Array.isArray(m.panels) && m.panels.length ? m.panels
      : MAIN_DEFAULT).slice(0, MAX).map(entry).filter((e) => e.panel);
    if (!panels.length || panels[0].panel !== 'traces') {
      panels = [{ panel: 'traces' }].concat(panels).slice(0, MAX);
    }
    const shapes = shapesFor(panels.length).map((x) => x[0]);
    return {
      open: true,
      panels,
      shape: shapes.includes(m.shape) ? m.shape : (shapes[0] || null),
      layout: fitLayout(m.layout, panels.length),
      span: +m.span > 0 ? +m.span : null,
      custom: Array.isArray(m.panels) && m.panels.length > 0,
    };
  }

  function saveMain(mode, m) {
    const every = Object.assign({}, all());
    const cur = Object.assign({}, every[mode] || {});
    if (m === null) delete cur.main;
    else {
      cur.main = { panels: m.panels, shape: m.shape, layout: m.layout || null,
                   span: m.span || null };
    }
    if (Object.keys(cur).length) every[mode] = cur; else delete every[mode];
    try { BARRY.prefs.set(KEY, every); } catch (e) { /* this session only */ }
    publishSoon();
  }

  /* One panel's spec, as setPanes takes it: the add-on's own spec for that
     kind of panel underneath, then whatever this person chose on top. */
  function specFor(e, base, chs) {
    const sp = JSON.parse(JSON.stringify(base
      || (isTF(e.panel) ? { panel: e.panel, fmin: 1, fmax: 250 }
                        : { panel: e.panel })));
    sp.panel = e.panel;
    const pos = positions(e, chs);
    if (pos) {
      if (isTF(e.panel)) {
        sp.tfChannels = pos.map((i) => (chs[i] && chs[i].index != null
                                         ? chs[i].index : i));
        if (pos.length > 1 && !sp.tfMode) sp.tfMode = 'stack';
      } else {
        sp.channels = pos;
        // The add-on's label named ITS channels, not these.
        delete sp.colLabel; delete sp.colTag; delete sp.colShank;
      }
    }
    const f = filterOf(e);
    if (f) sp.filt = f;
    if (isTF(e.panel)) {
      const b = bandOf(e);
      if (b) { sp.fmin = b[0]; sp.fmax = b[1]; }
      if (e.tfMode && e.tfMode !== 'default') sp.tfMode = e.tfMode;
    }
    if (e.cmap && e.cmap !== 'default' && e.panel !== 'traces') sp.cmap = e.cmap;
    if (e.panel === 'traces' && +e.gain > 0 && +e.gain !== 1) sp.gain = +e.gain;
    return sp;
  }

  function plan(mode, defaults, sess) {
    const c = choice(mode);
    if (!c.open) return null;
    const byId = {};
    for (const d of defaults || []) if (d && !byId[d.panel]) byId[d.panel] = d;
    const chs = (sess && sess.info && sess.info.channels) || [];
    const specs = c.panels.map((e) => specFor(e, byId[e.panel], chs));
    if (!specs.length) return null;
    const layout = c.layout || (specs.length > 4 ? gridLayout(specs.length) : null);
    return { specs, shape: c.shape, layout, span: c.span, overview: c.overview };
  }

  /* The main window's plan, or null when this person has not chosen one --
     so an add-on with nothing chosen lays out exactly as it always has. */
  function mainPlan(mode, defaults, sess) {
    const c = choiceMain(mode);
    if (!c.custom) return null;
    const byId = {};
    for (const d of defaults || []) if (d && !byId[d.panel]) byId[d.panel] = d;
    const chs = (sess && sess.info && sess.info.channels) || [];
    const specs = c.panels.map((e) => specFor(e, byId[e.panel], chs));
    const layout = c.layout || (specs.length > 4 ? gridLayout(specs.length) : null);
    return { specs, shape: c.shape, layout, span: c.span };
  }

  /* What applyMain changed, so leaving can put it back: the drawn layout,
     the shape for that count, the recording's band lock. */
  let mainSnap = null;

  function applyMain(mode, defaults, sess, split, fill) {
    const X = BARRY.views && BARRY.views.xplore;
    if (!X) return null;
    restoreMain(true);
    const p = mainPlan(mode, defaults, sess);
    if (!p) { X.setPanes(defaults, split); return null; }
    if (typeof fill === 'function') fill(p.specs);
    const XF = X.state;
    const n = p.specs.length;
    mainSnap = { n, layout: XF.customLayout || null,
                 hadShape: Object.prototype.hasOwnProperty.call(XF.shape, n),
                 shape: XF.shape[n], sess, flock: sess ? sess.flock : undefined };
    // Set before the panes are, or the first paint uses the old sizes.
    XF.customLayout = p.layout ? Object.assign({ n }, p.layout) : null;
    if (p.shape) XF.shape[n] = p.shape;
    if (sess && p.specs.some((x) => isTF(x.panel) && x.fmin != null)) {
      sess.flock = false;
    }
    /* The caller's split was for its one pane (Braid's is 1/1, which
       would give every pane but the first no room at all). Several panes
       with no drawing share the window evenly. */
    X.setPanes(p.specs, (n > 1 && !p.layout) ? { col: 0.5, row: 0.5 } : split);
    return p;
  }

  /* On leaving: the drawn layout and the shape override go (a later layout
     of the same count would otherwise inherit them and lose its dividers),
     the band lock is put back, and the window returns to its one traces
     pane, as every add-on has always left it. */
  function restoreMain(quiet) {
    if (!mainSnap) return;
    const X = BARRY.views && BARRY.views.xplore;
    const snap = mainSnap;
    mainSnap = null;
    if (!X) return;
    const XF = X.state;
    XF.customLayout = snap.layout;
    let kept = null;
    try { kept = JSON.parse(localStorage.getItem('barry.xfShape') || '{}'); }
    catch (e) { kept = null; }
    if (kept && kept[snap.n]) XF.shape[snap.n] = kept[snap.n];
    else if (snap.hadShape) XF.shape[snap.n] = snap.shape;
    else delete XF.shape[snap.n];
    if (snap.sess && snap.flock !== undefined) snap.sess.flock = snap.flock;
    if (!quiet) X.setPanes([{ panel: 'traces' }], { col: 0.5, row: 0.5 });
  }

  /* The options popOutPanes carries this in (xplore.js paneUrl). The band
     lock comes off when a panel asks for its own band, or the window would
     draw every spectrogram at the recording's one band and ignore it. */
  function opts(p) {
    const o = {};
    if (!p) return o;
    if (p.shape) o.shape = p.shape;
    if (p.layout) o.layout = p.layout;
    if (p.span) o.span = p.span;
    if ((p.specs || []).some((s) => isTF(s.panel) && s.fmin != null)) {
      o.flock = 'off';
    }
    if (p.overview === false) o.overview = 'off';
    else if (p.overview === true) o.overview = 'on';
    return o;
  }

  /* ---------- the arrangement editor: the mini window you drag ---------- */

  /* The window, drawn small: drag the line between two rows to share the
     height between them, the line between two panels to share a row's
     width, or a panel onto another to swap them. Every size is also a
     number you can type. Nothing is kept until Save. */
  function drawEditor(a, c, onSave) {
    let rows = toRows(c.panels, c.layout || shapeLayout(c.shape, c.panels.length));
    const canvas = el('div', { class: 'spl-canvas' });
    const words = el('p', { class: 'hint spl-words' });

    const pctIn = (val, title, onSet, cls) => el('input', {
      type: 'number', class: 'spl-pct ' + cls, min: '5', max: '95', step: '1',
      value: String(val), title,
      onchange: (ev) => onSet(Math.max(5, Math.min(95, +ev.target.value || 0))),
    });

    /* Give one of a group its value, the rest the remainder in their
       existing proportions. */
    function setShare(list, i, v, key) {
      const others = list.filter((x, j) => j !== i);
      const rest = others.reduce((s, x) => s + x[key], 0) || 1;
      const left = 100 - v;
      list[i][key] = v;
      others.forEach((x) => { x[key] = Math.max(5, (x[key] / rest) * left); });
      const fixed = to100(list.map((x) => x[key]));
      list.forEach((x, j) => { x[key] = fixed[j]; });
    }

    function moveRow(r, k, dir) {
      const slot = rows[r].cols.splice(k, 1)[0];
      if (rows[r].cols.length) {
        const ws = to100(rows[r].cols.map((x) => x.w));
        rows[r].cols.forEach((x, j) => { x.w = ws[j]; });
      }
      let to = r + dir;
      if (to < 0) { rows.unshift({ h: 100 / (rows.length + 1), cols: [] }); to = 0; r += 1; }
      else if (to >= rows.length) rows.push({ h: 100 / (rows.length + 1), cols: [] });
      const n = rows[to].cols.length + 1;
      rows[to].cols.forEach((x) => { x.w = x.w * (n - 1) / n; });
      rows[to].cols.push(Object.assign(slot, { w: 100 / n }));
      rows = rows.filter((x) => x.cols.length);
      const hs = to100(rows.map((x) => x.h));
      rows.forEach((x, j) => { x.h = hs[j]; });
      paint();
    }

    /* A divider being dragged: the two neighbours share what they had. */
    function dragBar(ev, list, i, key, axisPx) {
      ev.preventDefault();
      const bar = ev.currentTarget;
      try { bar.setPointerCapture(ev.pointerId); } catch (e) { /* not a live pointer */ }
      const start = axisPx(ev), a0 = list[i][key], b0 = list[i + 1][key];
      const box = canvas.getBoundingClientRect();
      const full = key === 'h' ? box.height : bar.parentNode.getBoundingClientRect().width;
      const move = (m) => {
        const d = ((axisPx(m) - start) / (full || 1)) * 100;
        const av = Math.max(5, Math.min(a0 + b0 - 5, a0 + d));
        list[i][key] = Math.round(av);
        list[i + 1][key] = Math.round(a0 + b0 - av);
        sizeOnly();
      };
      const up = () => {
        bar.removeEventListener('pointermove', move);
        bar.removeEventListener('pointerup', up);
        bar.removeEventListener('pointercancel', up);
        bar.classList.remove('dragging');
        paint();
      };
      bar.classList.add('dragging');
      bar.addEventListener('pointermove', move);
      bar.addEventListener('pointerup', up);
      bar.addEventListener('pointercancel', up);
    }

    /* A panel picked up: dropped on another, the two swap places. */
    function dragSlot(ev, r, k) {
      if (ev.target.closest('input, button')) return;
      const node = ev.currentTarget;
      const x0 = ev.clientX, y0 = ev.clientY;
      let moving = false, over = null;
      try { node.setPointerCapture(ev.pointerId); } catch (e) { /* not a live pointer */ }
      const move = (m) => {
        if (!moving && Math.hypot(m.clientX - x0, m.clientY - y0) < 6) return;
        moving = true;
        node.classList.add('lifted');
        node.style.transform = 'translate(' + (m.clientX - x0) + 'px,'
                             + (m.clientY - y0) + 'px)';
        node.style.pointerEvents = 'none';
        const hit = document.elementFromPoint(m.clientX, m.clientY);
        node.style.pointerEvents = '';
        const t = hit && hit.closest('.spl-slot');
        if (over && over !== t) over.classList.remove('target');
        over = (t && t !== node) ? t : null;
        if (over) over.classList.add('target');
      };
      const up = () => {
        node.removeEventListener('pointermove', move);
        node.removeEventListener('pointerup', up);
        node.removeEventListener('pointercancel', up);
        node.classList.remove('lifted');
        node.style.transform = '';
        if (moving && over) {
          const r2 = +over.dataset.r, k2 = +over.dataset.k;
          const t = rows[r].cols[k].e;
          rows[r].cols[k].e = rows[r2].cols[k2].e;
          rows[r2].cols[k2].e = t;
        }
        paint();
      };
      node.addEventListener('pointermove', move);
      node.addEventListener('pointerup', up);
      node.addEventListener('pointercancel', up);
    }

    /* While a divider moves, only the sizes and their numbers change. */
    function sizeOnly() {
      canvas.querySelectorAll('.spl-row').forEach((rn, r) => {
        rn.style.flexGrow = String(rows[r].h);
        rn.querySelectorAll('.spl-slot').forEach((sn, k) => {
          sn.style.flexGrow = String(rows[r].cols[k].w);
          const w = sn.querySelector('.spl-w'), h = sn.querySelector('.spl-h');
          if (w) w.value = String(Math.round(rows[r].cols[k].w));
          if (h) h.value = String(Math.round(rows[r].h));
        });
      });
      words.textContent = layoutWords(fromRows(rows).layout);
    }

    function paint() {
      canvas.innerHTML = '';
      let n = 0;
      rows.forEach((row, r) => {
        if (r > 0) {
          canvas.appendChild(el('div', {
            class: 'spl-hbar', title: 'Drag to share the height between these rows',
            onpointerdown: (ev) => dragBar(ev, rows, r - 1, 'h', (m) => m.clientY),
          }));
        }
        const rn = el('div', { class: 'spl-row' });
        rn.style.flexGrow = String(row.h);
        row.cols.forEach((slot, k) => {
          if (k > 0) {
            rn.appendChild(el('div', {
              class: 'spl-vbar', title: 'Drag to share the width between these panels',
              onpointerdown: (ev) => dragBar(ev, row.cols, k - 1, 'w', (m) => m.clientX),
            }));
          }
          n += 1;
          const sn = el('div', {
            class: 'spl-slot', 'data-r': String(r), 'data-k': String(k),
            title: 'Drag onto another panel to swap them',
            onpointerdown: (ev) => dragSlot(ev, r, k),
          }, [
            el('strong', { class: 'spl-name', text: n + '. ' + nameOf(slot.e.panel) }),
            el('div', { class: 'spl-sizes' }, [
              el('label', {}, [el('span', { text: 'W' }),
                pctIn(Math.round(slot.w), 'Width, percent of its row', (v) => {
                  setShare(row.cols, k, v, 'w'); paint();
                }, 'spl-w'), el('span', { text: '%' })]),
              el('label', {}, [el('span', { text: 'H' }),
                pctIn(Math.round(row.h), 'Height of its row, percent of the window',
                      (v) => { setShare(rows, r, v, 'h'); paint(); }, 'spl-h'),
                el('span', { text: '%' })]),
            ]),
            el('div', { class: 'spl-moves' }, [
              el('button', { class: 'mini', text: '↑ row', type: 'button',
                title: 'Into the row above (a new row if this is the top one)',
                onclick: () => moveRow(r, k, -1) }),
              el('button', { class: 'mini', text: '↓ row', type: 'button',
                title: 'Into the row below (a new row if this is the bottom one)',
                onclick: () => moveRow(r, k, 1) }),
            ]),
          ]);
          sn.style.flexGrow = String(slot.w);
          rn.appendChild(sn);
        });
        canvas.appendChild(rn);
      });
      words.textContent = layoutWords(fromRows(rows).layout);
    }

    const quick = (label, title, make) => el('button', {
      class: 'mini', type: 'button', text: label, title,
      onclick: () => {
        const panels = fromRows(rows).panels;
        rows = toRows(panels, make(panels.length));
        paint();
      },
    });

    paint();
    showModal(el('div', { class: 'spl' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: a.title || ('Arrange ' + a.name + '’s window') }),
        el('div', { class: 'spacer' }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { class: 'hint', text: 'Drag the line between two rows, or '
          + 'between two panels, to resize them; drag a panel onto another to '
          + 'swap them. Each size is a percentage you can also type: widths '
          + 'of their row, heights of the window.' }),
        el('div', { class: 'spl-quick' }, [
          quick('One row', 'Every panel side by side', (n) => shapeLayout('cols', n)),
          quick('One column', 'Every panel stacked', (n) => shapeLayout('rows', n)),
          quick('Grid', 'As square as the count allows', (n) => gridLayout(n)),
        ]),
        canvas,
        words,
      ]),
      BARRY.ui.modalFoot([
        c.layout ? BARRY.ui.button({ kind: 'ghost', text: 'Use a named arrangement',
          title: 'Forget the drawn sizes; the window opens in the arrangement '
               + 'picked in the list',
          onclick: () => { closeModal(); onSave(null); } }) : null,
      ], [
        BARRY.ui.button({ kind: 'ghost', text: 'Cancel', onclick: () => closeModal() }),
        BARRY.ui.button({ kind: 'primary', text: 'Save the arrangement',
          extra: 'spl-save',
          onclick: () => {
            const got = fromRows(rows);
            /* A main window's first panel is its traces: said here, with
               the drawing still open, rather than after it has gone. */
            if (a.firstFixed && (!got.panels[0] || got.panels[0].panel !== 'traces')) {
              toast('The traces stay the first panel of the main window: put '
                    + 'them back top left, then save.', 'warn', 6000);
              return;
            }
            closeModal();
            onSave(got);
          } }),
      ]),
    ]));
  }

  /* ---------- icons ----------

     2026-10-23: "less words, more icons -- or icons and words, more nicely
     arranged; see all the applicable toolkits, with their icons and colour
     codes." Each add-on wears its ToolKit tool's mark and colour (toolkit.js
     TOOL_ICONS, app.css --tool-<id> through [data-tool]); each panel kind
     and each setting has a small mark of its own, its word in the tooltip. */
  const ADDON_TOOL = { curate: 'curate', spotter: 'spotter', panning: 'panning',
                       strata: 'strata', cfc: 'cfc', braces: 'braces', arcmode: 'spark' };
  const PANEL_ICON = {
    traces: 'M1 4.5h2.2l1.2-2 1.8 4 1.3-2H15M1 8.5h3l1-1.5 1.8 3 1.4-1.5H15M1 12.5h2.2l1.2-2 1.8 4 1.3-2H15',
    csd: 'M2 2.5h12v11H2zM2 6.2h12M2 9.8h12M5.5 2.5v11',
    theta: 'M1 8c1.7-4.5 3.3-4.5 5 0s3.3 4.5 5 0 2.3-3 4-3',
    voltage: 'M2 3h12M2 5.6h12M2 8.2h12M2 10.8h12M2 13.4h12',
    spectrogram: 'M2 1.5v12.5h12.5M5 12V8.5M8 12V4.5M11 12V7',
    scalogram: 'M2 14h12.5M2.5 13c1.8-6 3.6-9 5.5-9s3.7 3 5.5 9',
    bandpower: 'M2 14h12.5M4 14V9.5M7 14V4.5M10 14V7.5M13 14V10.5',
  };
  const SET_ICON = {
    channels: 'M2 3.5h12M2 6.5h12M2 9.5h12M2 12.5h12M4.5 2v13',
    filter: 'M2 3h12l-4.5 5.5V13l-3 1.5V8.5z',
    band: 'M1 9c1.2-3 2.4-3 3.6 0s2.4 3 3.6 0 2.4-3 3.6 0 1.6 2 3.2 2',
    tf: 'M2 4h12M2 8h12M2 12h12',
    colours: 'M8 2a6 6 0 1 0 0 12c1 0 1.5-.6 1.5-1.4 0-1.2-1-1.3-1-2.3 0-.8.7-1.3 1.6-1.3H12a2 2 0 0 0 2-2C14 4.6 11.3 2 8 2zM5 7.2h.01M7.5 4.8h.01M10.5 5.2h.01',
    gain: 'M8 1.5v13M4.5 5L8 1.5 11.5 5M4.5 11L8 14.5 11.5 11',
    span: 'M1.5 8h13M1.5 5v6M14.5 5v6M4 8l-2-2M4 8l-2 2M12 8l2-2M12 8l2 2',
    overview: 'M1.5 10.5h13v3.5h-13zM3 12.2h1.5l1-1.2 1.2 2 1.3-1.5 1 .9H13',
    copy: 'M5.5 5.5h8v8h-8zM2.5 10.5v-8h8',
    up: 'M8 13V3M4 7l4-4 4 4',
    down: 'M8 3v10M4 9l4 4 4-4',
    remove: 'M4 4l8 8M12 4l-8 8',
    share: 'M11 5a2 2 0 1 0 0-.01M5 10a2 2 0 1 0 0-.01M11 15a2 2 0 1 0 0-.01M6.8 9l2.4-2.8M6.8 11l2.4 2.8',
    save: 'M3 2.5h8l2.5 2.5v8.5h-10.5zM5.5 2.5v3.5h5v-3.5M5.5 13.5v-4h5v4',
    main: 'M1.5 3h13v9h-13zM6 14.5h4M8 12v2.5',
    second: 'M1 4h9v7H1zM6 2h9v7h-1.5M4 13h3',
    reset: 'M3 8a5 5 0 1 0 1.5-3.5M3 2.5V5h2.5',
  };
  function svgIcon(d, cls) {
    return el('svg', { class: 'spp-ico' + (cls ? ' ' + cls : ''), viewBox: '0 0 16 16',
                       'aria-hidden': 'true', html: '<path d="' + d + '" />' });
  }
  function toolMark(mode) {
    const tk = BARRY.views && BARRY.views.toolkit;
    const got = tk && tk.toolIcon ? tk.toolIcon(ADDON_TOOL[mode] || mode) : null;
    return got || svgIcon(SET_ICON.main);
  }
  const panelIcon = (id) => svgIcon(PANEL_ICON[id] || SET_ICON.tf, 'spp-pico');
  const iconBtn = (name, title, onclick, extra) => el('button', {
    type: 'button', class: 'spp-ibtn' + (extra ? ' ' + extra : ''), title, 'aria-label': title,
    onclick }, [svgIcon(SET_ICON[name])]);

  /* ---------- someone else's, and mine for them ----------

     "Add an option to copy someone else's preset. Make sure we are able to
     save Rain's presets and copy them over." (2026-10-22)

     Preferences are this computer's, so another person's choice is not in
     them. What travels is a PRESET: a named copy of a person's support
     panel preferences in the shared presets store (`/api/presets/
     support_panels`, GUI_logs/presets, synced like the filter presets),
     carrying whose it is. Everyone's current choice is published by itself
     a moment after they change it ("<name> — current"), so anyone who has
     ever set theirs can be copied from; "Save mine as a preset" keeps a
     named one besides. Copying takes all of a preset's add-ons, or one. */
  const PKIND = 'support_panels';
  let shared = null;                 // the presets, once fetched
  let publishTimer = null;

  const inTest = () => !!BARRY.testNoAutobank;    // a check page's frame
  const slug = (x) => String(x || '').toLowerCase().replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  function me() {
    const p = (BARRY.profile && BARRY.profile.get && BARRY.profile.get()) || {};
    const e = p.effective || {};
    return { name: e.user || p.name || '',
             email: String(e.email || p.email || '').toLowerCase() };
  }
  function ownerOf(p) {
    const sv = p.saved || {};
    return { name: p.owner || sv.user || 'Someone',
             email: String(p.owner_email || sv.email || '').toLowerCase() };
  }
  const isMine = (p) => {
    const m = me(), o = ownerOf(p);
    return (m.email && o.email) ? m.email === o.email : (!!m.name && m.name === o.name);
  };

  async function loadShared() {
    try {
      const d = await api('/api/presets/' + PKIND);
      shared = (d.presets || []).filter((p) => p && p.addons);
    } catch (e) { shared = shared || []; }
    return shared;
  }

  async function publish(label, id, auto) {
    const who = me();
    if (!who.name) throw new Error('Set your name in Profile first, so the '
                                   + 'preset says whose it is.');
    const res = await apiPost('/api/presets/' + PKIND, { preset: {
      id: id || ('sp-' + slug(who.email || who.name) + '-' + slug(label)),
      // The owner in the name, so two people's presets read apart.
      name: who.name + ' — ' + label,
      label, owner: who.name, owner_email: who.email,
      addons: JSON.parse(JSON.stringify(all())),
      at: new Date().toISOString(),
      auto: !!auto,
    } });
    shared = (res.presets || []).filter((p) => p && p.addons);
    return res.preset;
  }

  /* Mine, published by itself a moment after it changes. */
  function publishSoon() {
    if (inTest()) return;
    clearTimeout(publishTimer);
    publishTimer = setTimeout(() => {
      const who = me();
      if (!who.name) return;
      publish('current', 'sp-' + slug(who.email || who.name), true)
        .catch(() => { /* tried again on the next change */ });
    }, 2500);
  }

  async function copyFrom(p, mode) {
    const src = p.addons || {};
    const names = mode ? [mode] : Object.keys(src).filter((k) => addon(k));
    const mine = all();
    const over = names.filter((k) => mine[k]);
    if (over.length && BARRY.confirm) {
      const ok = await BARRY.confirm('Replace your own with '
          + ownerOf(p).name + '’s?',
        'Your choices for ' + over.map((k) => (addon(k) || {}).name || k)
          .join(', ') + ' are replaced by theirs. Theirs stay theirs, and '
          + 'Back to its defaults is there if you change your mind.',
        'Copy theirs');
      if (!ok) return false;
    }
    const every = Object.assign({}, mine);
    for (const k of names) {
      if (src[k]) every[k] = JSON.parse(JSON.stringify(src[k]));
      else delete every[k];
    }
    try {
      BARRY.prefs.set(KEY, every);
      if (BARRY.prefs.flush) await BARRY.prefs.flush();
    } catch (e) { /* this session only */ }
    publishSoon();
    toast('Copied ' + ownerOf(p).name + '’s '
          + (mode ? ((addon(mode) || {}).name || mode) : 'support panels')
          + ' (' + (p.label || p.name) + ').', 'ok', 5000);
    return true;
  }

  /* The sharing bar: quiet, one line on a wide screen. */
  function shareBar(host) {
    const box = el('div', { class: 'spp-share' });
    const paintBar = () => {
      box.innerHTML = '';
      const list = shared || [];
      const theirs = list.filter((p) => !isMine(p));
      const mine = list.filter(isMine);
      // Grouped by person, in name order (natural, so "Lab 2" before "Lab 10").
      const byWho = {};
      for (const p of theirs) {
        const o = ownerOf(p);
        (byWho[o.name] = byWho[o.name] || []).push(p);
      }
      const people = BARRY.ui.natSort(Object.keys(byWho), (x) => x);
      let pick = null;
      const into = el('select', { class: 'spp-sel', title: 'Which add-ons to copy' });
      const fillInto = () => {
        into.innerHTML = '';
        const keys = pick ? Object.keys(pick.addons || {}).filter((k) => addon(k)) : [];
        into.appendChild(el('option', { value: '', text: 'every add-on' }));
        for (const k of keys) {
          into.appendChild(el('option', { value: k, text: 'only ' + addon(k).name }));
        }
        into.disabled = !pick;
      };
      const from = el('select', {
        class: 'spp-sel spp-from', title: 'Someone else’s support panel presets',
        onchange: (e) => {
          pick = list.find((p) => p.id === e.target.value) || null;
          fillInto();
          go.disabled = !pick;
        },
      }, [el('option', { value: '', text: theirs.length
        ? 'Copy someone’s…' : 'Nobody else has shared theirs yet' })]
        .concat(people.map((who) => el('optgroup', { label: who },
          byWho[who].map((p) => el('option', { value: p.id,
            text: (p.label || p.name) + (p.at ? '  ·  '
              + String(p.at).slice(0, 10) : '') }))))));
      from.disabled = !theirs.length;
      const go = el('button', { type: 'button', class: 'btn sm', text: 'Copy',
        disabled: 'disabled',
        onclick: async () => {
          if (!pick) return;
          if (await copyFrom(pick, into.value || null)) paint(host);
        } });
      fillInto();
      const nm = el('input', { type: 'text', class: 'spp-text spp-name',
        placeholder: 'Name mine', title: 'A name for a preset of your own '
          + 'support panel preferences, as they are now' });
      const keep = el('button', { type: 'button', class: 'btn ghost sm spp-keep',
        title: 'Save mine as a preset anyone can copy',
        onclick: async () => {
          const label = nm.value.trim();
          if (!label) { nm.focus(); toast('Give it a name first.', null, 3000); return; }
          // "current" is the one kept up to date by itself.
          if (/^current$/i.test(label)) {
            nm.focus();
            toast('“current” is the one Jarvis keeps up to date for you; '
                  + 'give this one another name.', null, 5000);
            return;
          }
          try {
            await publish(label);
            toast('Saved as “' + label + '”. Anyone can copy it now.', 'ok', 4000);
            paintBar();
          } catch (e) { toast(e.message, 'err', 6000); }
        } }, [svgIcon(SET_ICON.save), el('span', { text: 'Save mine' })]);
      box.appendChild(el('div', { class: 'spp-share-row' }, [
        el('span', { class: 'spp-share-ico', title: 'Someone else’s' }, [svgIcon(SET_ICON.share)]),
        from, into, go,
        el('span', { class: 'spp-share-gap' }),
        nm, keep,
      ].concat(mine.filter((p) => !p.auto && p.label !== 'current').map((p) =>
        el('span', { class: 'spp-mine-chip', title: 'Shared by you' }, [
          el('span', { text: p.label || p.name }),
          el('button', { type: 'button', class: 'mini', text: '×',
            title: 'Stop sharing “' + (p.label || p.name) + '”',
            onclick: async () => {
              try {
                const res = await apiPost('/api/presets/' + PKIND, { id: p.id },
                                          { method: 'DELETE' });
                shared = (res.presets || []).filter((x) => x && x.addons);
              } catch (e) { toast(e.message, 'err', 6000); return; }
              paintBar();
            } }),
        ])))));
    };
    paintBar();
    loadShared().then(paintBar);
    return box;
  }

  /* ---------- the Profile's section ---------- */

  const sel = (opts2, value, title, onPick) => el('select', {
    class: 'spp-sel', title, 'aria-label': title,
    onchange: (ev) => onPick(ev.target.value),
  }, opts2.map(([v, label]) => el('option', {
    value: v, text: label, selected: v === value ? 'selected' : null,
  })));
  const num = (value, title, onSet, o) => el('input', Object.assign({
    type: 'number', class: 'spp-num', value: value == null ? '' : String(value),
    title, 'aria-label': title,
    onchange: (ev) => onSet(ev.target.value === '' ? null : +ev.target.value),
  }, o || {}));
  /* A setting: its mark, its word kept for screen readers and tooltips
     (and for anything that reads the field by name), then its control. */
  const fld = (label, kids, icon) => el('label', { class: 'spp-f', title: label }, [
    el('span', { class: 'spp-fl' }, [icon ? svgIcon(SET_ICON[icon]) : null,
                                     el('span', { class: 'spp-fl-t', text: label })].filter(Boolean)),
  ].concat(kids.filter(Boolean)));

  /* The window drawn small: its rows and panels, each panel's mark in its
     box. Pressing it opens the arrangement editor. */
  function preview(c, onDraw) {
    const lay = c.layout || shapeLayout(c.shape, c.panels.length);
    let k = 0;
    const win = el('button', { type: 'button', class: 'spp-win', title: c.layout
      ? 'Drawn: ' + layoutWords(c.layout) + '. Press to change it.'
      : 'Press to draw it: drag the sizes, type percentages, move panels between rows',
      onclick: onDraw }, lay.rows.map((r) => {
      const row = el('span', { class: 'spp-win-row' });
      row.style.flexGrow = String(r.h);
      for (const w of r.cols) {
        const e = c.panels[k++] || {};
        const cell = el('span', { class: 'spp-win-cell', title: nameOf(e.panel) }, [panelIcon(e.panel)]);
        cell.style.flexGrow = String(w);
        row.appendChild(cell);
      }
      return row;
    }));
    return win;
  }

  /* One window's editor: the add-on's second window ('aid') or its main
     window ('main'). The same pieces either way. */
  function block(a, host, which) {
    const isMain = which === 'main';
    const c = isMain ? choiceMain(a.mode) : choice(a.mode);
    const put = (next) => (isMain ? saveMain(a.mode, next) : save(a.mode, next));
    /* Kept, and the list drawn again (a structural change). */
    const set = (patch) => {
      const next = Object.assign({}, c, patch);
      const shapes = shapesFor(next.panels.length).map((x) => x[0]);
      if (!shapes.includes(next.shape)) next.shape = shapes[0] || null;
      if (next.layout && countOf(next.layout) !== next.panels.length) next.layout = null;
      put(next);
      paint(host);
    };
    /* A field changed: kept, the list left as it is so typing is not lost. */
    const keepField = (i, patch, redraw) => {
      const panels = c.panels.map((e, j) => (j === i ? Object.assign({}, e, patch) : e));
      c.panels = panels;
      put(Object.assign({}, c, { panels }));
      if (redraw) paint(host);
    };
    /* Panels added, copied or removed keep a drawn arrangement in step. */
    const withRows = (fn) => {
      if (!c.layout) return null;
      const rs = toRows(c.panels, c.layout);
      fn(rs);
      return fromRows(rs);
    };
    const addPanel = (id) => {
      const e = { panel: id };
      const r = withRows((rs) => {
        const last = rs[rs.length - 1], n = last.cols.length + 1;
        last.cols.forEach((x) => { x.w = x.w * (n - 1) / n; });
        last.cols.push({ w: 100 / n, e });
      });
      set(r || { panels: c.panels.concat([e]) });
    };
    const copyPanel = (i) => {
      const e = JSON.parse(JSON.stringify(c.panels[i]));
      let k = 0;
      const r = withRows((rs) => {
        for (const rr of rs) {
          for (let j = 0; j < rr.cols.length; j++, k++) {
            if (k === i) {
              const n = rr.cols.length + 1;
              rr.cols.forEach((x) => { x.w = x.w * (n - 1) / n; });
              rr.cols.splice(j + 1, 0, { w: 100 / n, e });
              return;
            }
          }
        }
      });
      const p = c.panels.slice();
      p.splice(i + 1, 0, e);
      set(r || { panels: p });
    };
    const dropPanel = (i) => {
      let k = 0;
      const r = withRows((rs) => {
        for (const rr of rs) {
          for (let j = 0; j < rr.cols.length; j++, k++) {
            if (k === i) { rr.cols.splice(j, 1); return; }
          }
        }
      });
      set(r || { panels: c.panels.filter((x, j) => j !== i) });
    };
    const swap = (i, j) => {
      const p = c.panels.slice();
      [p[i], p[j]] = [p[j], p[i]];
      set({ panels: p });
    };
    // The main window's first panel is its traces, fixed in place.
    const fixed = (i) => isMain && i === 0;
    const draw = () => drawEditor({ name: a.name, firstFixed: isMain,
      title: 'Arrange ' + a.name + (isMain ? '’s main window' : '’s second window') },
      c, (got) => {
        if (got) set({ panels: got.panels, layout: got.layout });
        else set({ layout: null });
      });

    const panelCard = (e, i) => {
      const tf = isTF(e.panel);
      const fil = e.filter || 'window';
      const filters = FILTERS.slice(0, -1).concat(savedFilters(), [FILTERS[FILTERS.length - 1]]);
      return el('div', { class: 'spp-panel' }, [
        el('div', { class: 'spp-ph' }, [
          el('span', { class: 'spp-pmark', title: nameOf(e.panel) }, [panelIcon(e.panel)]),
          fixed(i)
            ? el('span', { class: 'spp-fixed', text: nameOf('traces'),
                title: 'The main window’s first panel is always the traces: '
                     + 'the add-on reads its window, its keys and its marks from it' })
            : sel(catalog().map((p) => [p.id, p.name]), e.panel, 'What this panel shows',
                  (v) => keepField(i, { panel: v }, true)),
          el('span', { class: 'spacer' }),
          c.panels.length < MAX ? iconBtn('copy', 'Another ' + nameOf(e.panel)
            + ' with these settings, right after this one', () => copyPanel(i)) : null,
          i > 0 && !fixed(i - 1) ? iconBtn('up', 'Earlier in the window', () => swap(i, i - 1)) : null,
          i < c.panels.length - 1 && !fixed(i) ? iconBtn('down', 'Later in the window',
            () => swap(i, i + 1)) : null,
          c.panels.length > 1 && !fixed(i) ? iconBtn('remove', 'Take this '
            + nameOf(e.panel) + ' out of the window', () => dropPanel(i), 'danger') : null,
        ].filter(Boolean)),
        el('div', { class: 'spp-pf' }, [
          fld('Channels', [
            sel(CHANNELS, e.channels || 'default', 'Which channels it opens on',
                (v) => keepField(i, { channels: v }, true)),
            e.channels === 'custom' ? el('input', {
              type: 'text', class: 'spp-text', value: e.chText || '',
              placeholder: '1-16, 33', title: 'Channel numbers, ranges allowed',
              onchange: (ev) => keepField(i, { chText: ev.target.value }) }) : null,
          ], 'channels'),
          fld('Filter', [
            sel(filters, fil, isMain
                ? 'The band-pass this panel reads with; the window’s filter is the '
                  + 'one the add-on sets (Spotter and Panning use the IED band)'
                : 'The band-pass this panel reads with; the window’s filter is the '
                  + 'main window’s',
                (v) => keepField(i, { filter: v }, true)),
            fil === 'custom' ? num(e.hp, 'High-pass, Hz (0 = open)',
              (v) => keepField(i, { hp: v }), { min: '0', step: '0.5', placeholder: 'HP' }) : null,
            fil === 'custom' ? num(e.lp, 'Low-pass, Hz (0 = open)',
              (v) => keepField(i, { lp: v }), { min: '0', step: '1', placeholder: 'LP' }) : null,
            fil !== 'window' ? el('span', { class: 'spp-check', title: 'Take out 60 Hz mains' }, [
              el('input', { type: 'checkbox', checked: e.notch ? 'checked' : null,
                onchange: (ev) => keepField(i, { notch: ev.target.checked }) }),
              el('span', { text: '60 Hz' }),
            ]) : null,
          ], 'filter'),
          tf ? fld('Band', [
            sel(BANDS, e.band || 'default', 'The frequencies it computes',
                (v) => keepField(i, { band: v }, true)),
            e.band === 'custom' ? num(e.fmin, 'Lowest frequency, Hz',
              (v) => keepField(i, { fmin: v }), { min: '0', step: '1', placeholder: 'from' }) : null,
            e.band === 'custom' ? num(e.fmax, 'Highest frequency, Hz',
              (v) => keepField(i, { fmax: v }), { min: '1', step: '1', placeholder: 'to' }) : null,
          ], 'band') : null,
          tf ? fld('Several channels', [
            sel(TFMODES, e.tfMode || 'default', 'One picture per channel, or their average',
                (v) => keepField(i, { tfMode: v })),
          ], 'tf') : null,
          e.panel !== 'traces' ? fld('Colours', [
            sel([['default', 'As the add-on sets them']]
                  .concat(cmaps().map((m) => [m.id, m.name])),
                e.cmap || 'default', 'The colour map',
                (v) => keepField(i, { cmap: v })),
          ], 'colours') : null,
          e.panel === 'traces' ? fld('Gain', [
            num(e.gain != null ? e.gain : 1, 'Gain: times the window’s; 1 is the same',
                (v) => keepField(i, { gain: v }), { min: '0.05', step: '0.25' }),
            el('span', { class: 'spp-unit', text: '×' }),
          ], 'gain') : null,
        ].filter(Boolean)),
      ]);
    };

    const n = c.panels.length;
    const shapes = shapesFor(n);
    // The Arc moves its own window to each cue pair, so a span would not hold.
    const spanOk = !(isMain && a.mode === 'arcmode');
    return el('div', { class: 'spp-block ' + which + (c.open ? '' : ' off') }, [
      el('div', { class: 'spp-bhead' }, [
        el('span', { class: 'spp-bname' }, [svgIcon(SET_ICON[isMain ? 'main' : 'second']),
          el('span', { text: isMain ? 'Main window' : 'Second window' })]),
        isMain ? el('span', { class: 'spp-bsay', text: c.custom ? 'as chosen here'
                                                                 : 'as the add-on lays it out' })
          : BARRY.ui.seg([['on', 'Opens'], ['off', 'Off']],
              c.open ? 'on' : 'off', (v) => set({ open: v === 'on' }), { extra: 'sm' }),
        el('span', { class: 'spacer' }),
        c.custom ? el('button', { class: 'linkish spp-reset', type: 'button',
          title: 'Back to the add-on’s own', onclick: () => { put(null); paint(host); } },
          [svgIcon(SET_ICON.reset), el('span', { text: 'Defaults' })]) : null,
      ].filter(Boolean)),
      c.open ? el('div', { class: 'spp-body' }, [
        // Left: the window, drawn small, and its whole-window settings.
        el('div', { class: 'spp-side' }, [
          preview(c, draw),
          el('div', { class: 'spp-arr' }, [
            c.layout
              ? el('span', { class: 'spp-drawn', text: 'Drawn' })
              /* Each named arrangement as a tiny picture of itself, its name
                 on hover: four words wrapped and overlapped in this column
                 (2026-10-23). */
              : (shapes.length > 1 ? el('div', { class: 'spp-shapes', role: 'group',
                  'aria-label': 'Arrangement' }, shapes.map(([id, say]) => {
                  const lay = shapeLayout(id, n);
                  return el('button', { type: 'button', class: 'spp-shape' + (c.shape === id ? ' on' : ''),
                    title: say, 'aria-label': say, 'aria-pressed': String(c.shape === id),
                    onclick: () => { if (c.shape !== id) set({ shape: id, layout: null }); } },
                    lay.rows.map((r) => {
                      const rw = el('span', { class: 'spp-shape-row' });
                      rw.style.flexGrow = String(r.h);
                      for (const w of r.cols) {
                        const cell = el('span', { class: 'spp-shape-cell' });
                        cell.style.flexGrow = String(w);
                        rw.appendChild(cell);
                      }
                      return rw;
                    }));
                })) : null),
            el('button', { class: 'btn ghost sm spp-draw', type: 'button',
              text: c.layout ? 'Edit drawing' : 'Draw it',
              title: 'A small copy of the window: drag the sizes, type percentages, '
                   + 'move panels between rows', onclick: draw }),
          ].filter(Boolean)),
          el('div', { class: 'spp-tools' }, [
            spanOk ? fld('Span', [
              num(c.span, isMain
                  ? 'Span: seconds the main window starts at. Empty: as the add-on '
                    + 'remembers it'
                  : 'Span: seconds the window shows. Empty: it follows the main window',
                  (v) => { c.span = v > 0 ? v : null;
                           put(Object.assign({}, c)); },
                  { min: '0.05', step: '0.5', placeholder: isMain ? 'kept' : 'follows' }),
              el('span', { class: 'spp-unit', text: 's' }),
            ], 'span') : null,
            !isMain ? fld('Overview strip', [
              sel([['default', 'as last left'], ['on', 'shown'], ['off', 'hidden']],
                  c.overview == null ? 'default' : (c.overview ? 'on' : 'off'),
                  'The line through the whole recording, across the bottom of the '
                  + 'window', (v) => {
                    c.overview = v === 'default' ? null : v === 'on';
                    put(Object.assign({}, c));
                  }),
            ], 'overview') : null,
          ].filter(Boolean)),
        ]),
        // Right: the panels, then the marks to add another.
        el('div', { class: 'spp-main' }, [
          el('div', { class: 'spp-panels' }, c.panels.map(panelCard)),
          n < MAX ? el('div', { class: 'spp-addbar', role: 'group',
            'aria-label': 'Add a panel to this window' }, [
            el('span', { class: 'spp-add-t', text: 'Add' }),
          ].concat(catalog().map((p) => el('button', {
            type: 'button', class: 'spp-addp', 'data-add': p.id,
            title: 'Add ' + p.name + ' (the same kind more than once is fine; up to ' + MAX + ')',
            onclick: () => addPanel(p.id) }, [panelIcon(p.id), el('span', { text: p.name })])))) : null,
        ].filter(Boolean)),
      ]) : null,
    ].filter(Boolean));
  }

  /* Which add-on is open in the editor (this computer's convenience). */
  const PICK_KEY = 'barry.spp.pick';
  let picked = null;
  function pickedMode() {
    if (picked && addon(picked)) return picked;
    try { picked = localStorage.getItem(PICK_KEY); } catch (e) { picked = null; }
    if (!picked || !addon(picked)) picked = ADDONS[0].mode;
    return picked;
  }

  /* One add-on's row: its own block per window. All are in the page; only
     the picked one shows. */
  function row(a, host) {
    return el('div', { class: 'spp-row', 'data-mode': a.mode,
                       hidden: a.mode === pickedMode() ? null : 'hidden' }, [
      el('div', { class: 'spp-head' }, [
        el('span', { class: 'spp-tmark', 'data-tool': ADDON_TOOL[a.mode] || a.mode }, [toolMark(a.mode)]),
        el('strong', { text: a.name }),
      ]),
      el('div', { class: 'spp-blocks' }, [
        block(a, host, 'main'),
        a.aid === false ? null : block(a, host, 'aid'),
      ].filter(Boolean)),
    ]);
  }

  /* The add-ons as tiles in their ToolKit colours: the mark, the name, and
     what each window holds, as panel marks. */
  function tiles(host) {
    const box = el('div', { class: 'spp-tiles', role: 'tablist', 'aria-label': 'Add-ons' });
    for (const a of ADDONS) {
      const m = choiceMain(a.mode), s = a.aid === false ? null : choice(a.mode);
      const custom = m.custom || (s && s.custom);
      const on = a.mode === pickedMode();
      const marks = (c) => el('span', { class: 'spp-tile-ps' },
        c.panels.slice(0, 6).map((e) => panelIcon(e.panel))
          .concat(c.panels.length > 6 ? [el('span', { text: '+' + (c.panels.length - 6) })] : []));
      box.appendChild(el('button', {
        type: 'button', role: 'tab', class: 'spp-tile' + (on ? ' on' : '') + (custom ? ' custom' : ''),
        'aria-selected': String(on), 'data-tool': ADDON_TOOL[a.mode] || a.mode, 'data-mode': a.mode,
        title: a.name + (custom ? ' · set up by you' : ' · the add-on’s own'),
        onclick: () => {
          picked = a.mode;
          try { localStorage.setItem(PICK_KEY, a.mode); } catch (e) { /* this view only */ }
          paint(host);
        },
      }, [
        el('span', { class: 'spp-tile-head' }, [el('span', { class: 'spp-tmark' }, [toolMark(a.mode)]),
          el('span', { class: 'spp-tile-name', text: a.name }),
          custom ? el('span', { class: 'spp-tile-dot', title: 'Set up by you' }) : null].filter(Boolean)),
        el('span', { class: 'spp-tile-wins' }, [
          el('span', { class: 'spp-tile-win', title: 'Main window' }, [svgIcon(SET_ICON.main), marks(m)]),
          s ? el('span', { class: 'spp-tile-win' + (s.open ? '' : ' off'), title: s.open
            ? 'Second window' : 'No second window' }, [svgIcon(SET_ICON.second), s.open ? marks(s)
              : el('span', { class: 'spp-tile-off', text: 'off' })]) : null,
        ].filter(Boolean)),
      ]));
    }
    return box;
  }

  function paint(host) {
    host.innerHTML = '';
    host.appendChild(tiles(host));
    for (const a of ADDONS) host.appendChild(row(a, host));
  }

  function section() {
    const list = el('div', { class: 'spp-list' });
    const wrap = el('details', { class: 'spp' }, [
      el('summary', { class: 'section-label', text: 'Support panel preferences' }),
      el('p', { class: 'hint spp-lede', title: 'Up to ' + MAX + ' panels a window, the same kind '
          + 'more than once if you like; each with its channels, filter, band, colours and gain; '
          + 'the span; and the arrangement, to the percent. Saved as you change it, used the next '
          + 'time the add-on opens. Yours are shared as a preset anyone can copy.',
        text: 'What each add-on’s windows open with. Pick an add-on; changes save as you go.' }),
      shareBar(list),
      list,
    ]);
    paint(list);
    return wrap;
  }

  return { plan, opts, choice, choiceMain, mainPlan, applyMain, restoreMain,
           section, ADDONS, copyFrom, loadShared,
           _test: { positions, filterOf, bandOf, parseList, toRows, fromRows,
                    shapeLayout, gridLayout, specFor, publish } };
})();
