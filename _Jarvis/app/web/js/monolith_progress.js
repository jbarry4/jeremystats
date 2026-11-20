/* ==========================================================================
   monolith_progress.js -- Monolith Progress, on the Monolith's own circuit.

   The Monolith asks one question, Precon4 against Precon1. Its circuit card
   has a button, Monolith Progress (the lab, 2026-10-06), that shows the way
   there: every edge in every Precon session, either as that session's own
   value or as its change from Precon1 -- four circuits side by side, or one
   at a time turning into the next, or both readings at once -- for the view
   the Monolith's own controls set. Over the circuit, any line followed
   across the sessions: a panel a line, each in its own units, stacked so
   several tests read together. Drag an edge (or a node) from any circuit
   onto the panels, or build one from the form. Click a session's point and
   it opens into that session's rats, a rat into its presentations, and a
   presentation into its traces.

   The Cue 2 − Cue 1 tab uses the same circuits for its first two: Cue 2 −
   Cue 1 within Precon1 and within Precon4 (and Precon2 and Precon3 between
   them), beside the tested change.

   Descriptive: nothing here is tested. The only p is the Monolith's own,
   for Precon4 − Precon1, uncorrected, and it is quoted, never recomputed.

   The numbers are backend/monolith.py session_build's files,
   session_<edges|power>_<layer>[__<split>]_<window>.f32, shaped
   (sessions, mean · se · n · chg · chg_se, band, measure, pair) for edges
   and (sessions, ..., band, region) for power. Each rat's own line is the
   /entry the ghost reads. Load order: after monolith.js.
   ========================================================================== */
'use strict';

window.MONO_PROGRESS = (function () {
  const M = () => window.MONO;
  const KEY = 'barry.monolith.progress';
  const NS = 'http://www.w3.org/2000/svg';
  const ALL = ['Precon1', 'Precon2', 'Precon3', 'Precon4'];
  const SQ = { mean: 0, se: 1, n: 2, chg: 3, chg_se: 4 };
  const MODES = [['value', 'Each session’s value', 'Every session as it is: the mean over rats'],
                 ['chg', 'Change from Precon1', 'Every session less Precon1, rat by rat, then the mean over rats'],
                 ['both', 'Both', 'The two readings at once']];
  const MODE_SAY = { value: 'Each session’s value', chg: 'Change from Precon1' };
  const LAYOUTS = [['all', 'All four sessions'], ['step', 'One at a time']];
  // How many lines a circuit draws: every pair at once is a hairball.
  const TOPS = [[10, 'Strongest 10', 'The ten strongest lines of each session (or the ten that changed most)'],
                [25, 'Strongest 25', 'The 25 strongest lines of each session (or the 25 that changed most)'],
                [0, 'Every line', 'Every region pair measured']];
  // Each measure in its own units: a panel's axis says which.
  const UNITS = { coherence: 'coherence (0–1)', icoh: '|imaginary coherency| (0–1)', raw_cc: 'peak r', env_cc: 'envelope peak r',
                  env_cc0: 'envelope r at zero lag', orth_env: 'orthogonalised envelope r', plv: 'PLV (0–1)', ppc: 'PPC',
                  pli: 'PLI (0–1)', wpli: 'wPLI (0–1)', dwpli: 'debiased wPLI²', gc_ab: 'Granger (nats)', gc_ba: 'Granger (nats)',
                  gc_net: 'Granger net (nats)', power: 'power (log10)' };
  const CW = 360, CH = 304, CCX = 180, CCY = 152, CRING = 108;

  const P = { mode: 'value', layout: 'all', step: 0, top: 25, only: false, series: [], drill: null,
              build: null, err: null, playing: null, shown: false, making: false, makeNote: '', makeErr: null };
  const ARR = new Map();       // session files, the last few read
  const SDATA = new Map();     // a series' numbers, by its key

  /* ---------------- small helpers ---------------- */
  const $ = (id) => document.getElementById(id);
  const el = (...a) => M().el(...a);
  function sv(tag, attrs, text) {
    const n = document.createElementNS(NS, tag);
    for (const k in (attrs || {})) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const S = () => M().data.S;
  const sig = (v) => M().sig(v);
  const f3 = (v) => M().f3(v);
  const fp = (v) => M().fp(v);
  const short = (r) => M().short(r);
  const idx = (list, id) => (list || []).findIndex((x) => x.id === id);
  const ratColor = (i, n) => 'hsl(' + Math.round(360 * i / Math.max(1, n)) + ', 55%, 45%)';
  function rgb(c) {
    const s = String(c || '').trim();
    let m = /^#([0-9a-f]{3})$/i.exec(s);
    if (m) return m[1].split('').map((x) => parseInt(x + x, 16));
    m = /^#([0-9a-f]{6})$/i.exec(s);
    if (m) return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16));
    m = /rgba?\(([^)]+)\)/.exec(s);
    if (m) return m[1].split(',').slice(0, 3).map((x) => parseFloat(x));
    return [128, 128, 128];
  }
  const rgbStr = (a) => 'rgb(' + a.map((x) => Math.round(x)).join(',') + ')';
  const lerp = (a, b, t) => a + (b - a) * t;
  const lerp3 = (a, b, t) => [0, 1, 2].map((i) => lerp(a[i], b[i], t));

  function remember() {
    try {
      localStorage.setItem(KEY, JSON.stringify({ mode: P.mode, layout: P.layout, top: P.top, only: P.only, series: P.series }));
    } catch (e) { /* per viewer only */ }
  }
  function recall() {
    try {
      const o = JSON.parse(localStorage.getItem(KEY) || 'null');
      if (!o) return;
      if (MODES.some((x) => x[0] === o.mode)) P.mode = o.mode;
      if (LAYOUTS.some((x) => x[0] === o.layout)) P.layout = o.layout;
      if (TOPS.some((x) => x[0] === o.top)) P.top = o.top;
      P.only = !!o.only;
      if (Array.isArray(o.series)) P.series = o.series.filter(okSeries);
    } catch (e) { /* none */ }
  }
  function okSeries(s) {
    const D = S();
    if (!s || !D || idx(D.windows, s.w) < 0 || idx(D.bands, s.b) < 0) return false;
    if (s.what === 'edges') return s.p >= 0 && s.p < D.pairs.length && idx(D.methods, s.m) >= 0;
    return s.what === 'power' && s.r >= 0 && s.r < D.regions.length;
  }

  /* ---------------- what is in this Monolith ---------------- */
  const sess = () => S().sessions || null;
  const order = () => (sess() || {}).order || [];
  const ran = (day) => order().indexOf(day);
  function splitLabel(g) {
    if (!g || g === 'all') return 'AB and CD pooled';
    const x = ((S().splits || {}).groups || []).find((y) => y.id === g);
    return x ? x.label : g;
  }
  const layerSay = (l) => (l === 'minus_fp' ? 'Minus FP' : 'Raw');
  function bandSay(id) {
    const b = S().bands.find((x) => x.id === id);
    return b ? (b.named ? b.label : b.hz + ' Hz') : id;
  }
  const winSay = (id) => (S().windows.find((w) => w.id === id) || {}).label || id;
  const methodSay = (id) => (S().methods.find((m) => m.id === id) || {}).label || id;
  function fileName(what, layer, split, w) {
    return 'session_' + what + '_' + layer + (split && split !== 'all' ? '__' + split : '') + '_' + w;
  }
  async function sessArr(what, layer, split, w) {
    const name = fileName(what, layer, split, w);
    if (ARR.has(name)) {
      const v = ARR.get(name);
      ARR.delete(name);
      ARR.set(name, v);
      return v;
    }
    const f = ((sess() || {}).files || {})[name + '.f32'];
    if (!f) throw new Error('This Monolith has no ' + name + '.');
    const v = M().getArray(name, f.shape).then((a) => ({ a, shape: f.shape }));
    ARR.set(name, v);
    v.catch(() => ARR.delete(name));
    while (ARR.size > 12) ARR.delete(ARR.keys().next().value);
    return v;
  }
  // One number of a session file: edges (s, q, band, measure, pair);
  // power (s, q, band, region) -- `p` left out.
  function val(v, s, q, b, x, p) {
    if (!v || s < 0) return NaN;
    const sh = v.shape;
    if (sh.length === 5) return v.a[(((s * sh[1] + q) * sh[2] + b) * sh[3] + x) * sh[4] + p];
    return v.a[((s * sh[1] + q) * sh[2] + b) * sh[3] + x];
  }

  /* ---------------- the view: the Monolith's own ---------------- */
  // The window, frequency, measure, layer and cue pairs the Monolith's
  // controls show: Progress sits on the Monolith's circuit and follows them.
  function view() {
    const st = M().state;
    return { w: st.win, b: st.band, m: st.method, layer: st.layer, split: st.split || 'all' };
  }

  /* ---------------- the circuits ----------------
     A group is a set of circuits drawn from one session file: "prog", the
     Monolith Progress circuits on the Monolith's card; "within", Cue 2 −
     Cue 1 within Precon1 and within Precon4; "between", the same within
     Precon2 and Precon3. Each circuit stays and turns into the next: a
     change of mode, session or view morphs the lines it has. */
  const G = {};
  function cellsOf() {
    const both = P.mode === 'both';
    const modes = both ? ['value', 'chg'] : [P.mode];
    if (P.layout === 'all') return modes.map((mode) => ALL.map((day) => ({ mode, day })));
    return [modes.map((mode) => ({ mode, day: ALL[P.step] }))];
  }
  function positions(n) {
    const pos = [];
    for (let i = 0; i < n; i++) {
      const a = -Math.PI / 2 + (i + 0.5) * (2 * Math.PI / n);
      pos.push({ x: CCX + CRING * Math.cos(a), y: CCY + CRING * Math.sin(a), a });
    }
    return pos;
  }
  const edgeSeries = (p) => { const v = view(); return { what: 'edges', p, w: v.w, b: v.b, m: v.m, layer: v.layer, split: v.split }; };
  const nodeSeries = (r) => { const v = view(); return { what: 'power', r, w: v.w, b: v.b, layer: v.layer, split: v.split }; };
  function makeCircuit(cell, g) {
    const D = S();
    const C = { cell, cur: null, g };       // its cell changes under it; the hovers read C's
    const pos = positions(D.regions.length);
    const svg = sv('svg', { viewBox: '0 0 ' + CW + ' ' + CH, class: 'mfig progc', role: 'img' });
    svg.appendChild(sv('circle', { cx: CCX, cy: CCY, r: CRING, fill: 'none', stroke: css('--ring') }));
    // A click: in Progress, follow the line in a panel (and select it); in
    // the contrast's circuits, select it and lift it out on the change.
    const clickEdge = (p) => (g === 'prog' ? () => { addSeries(edgeSeries(p), true); M().pickPair(p, false); }
      : () => M().pickPair(p, true));
    const paths = D.pairs.map(([a, b], p) => {
      const pa = pos[a], pb = pos[b];
      const mx = (pa.x + pb.x) / 2, my = (pa.y + pb.y) / 2;
      const qx = CCX + (mx - CCX) * 0.35, qy = CCY + (my - CCY) * 0.35;
      const path = sv('path', { d: 'M' + pa.x.toFixed(1) + ',' + pa.y.toFixed(1) + ' Q' + qx.toFixed(1) + ',' + qy.toFixed(1) + ' '
        + pb.x.toFixed(1) + ',' + pb.y.toFixed(1), fill: 'none', class: 'pedge', 'data-pair': String(p), 'stroke-linecap': 'round',
        'stroke-width': 0, 'stroke-opacity': 0, tabindex: '0', stroke: css('--ink-3') });
      M().hover(path, () => edgeTip(C, p));
      dragSource(path, () => edgeSeries(p), clickEdge(p));
      svg.appendChild(path);
      return path;
    });
    const nodes = D.regions.map((name, r) => {
      const p = pos[r];
      const c = sv('circle', { cx: p.x, cy: p.y, r: 7, class: 'pnode', 'data-region': String(r), fill: css('--node'),
                               stroke: css('--surface'), 'stroke-width': 2, tabindex: '0' });
      M().hover(c, () => nodeTip(C, r));
      dragSource(c, () => nodeSeries(r));
      svg.appendChild(c);
      const lx = CCX + (CRING + 14) * Math.cos(p.a), ly = CCY + (CRING + 14) * Math.sin(p.a);
      const anchor = Math.abs(Math.cos(p.a)) < 0.2 ? 'middle' : (Math.cos(p.a) > 0 ? 'start' : 'end');
      svg.appendChild(sv('text', { x: lx.toFixed(1), y: (ly + 3.5).toFixed(1), 'text-anchor': anchor, 'font-size': 10.5,
                                   fill: css('--ink-2') }, short(name)));
      return c;
    });
    const none = sv('text', { x: CCX, y: CCY + 4, 'text-anchor': 'middle', 'font-size': 12, fill: css('--ink-3'), class: 'pnone' }, '');
    svg.appendChild(none);
    return Object.assign(C, { svg, paths, nodes, none });
  }
  function edgeTip(C, p) {
    const D = S(), c = (G[C.g] || {}).data, cell = C.cell;
    const [a, b] = D.pairs[p];
    const within = C.g !== 'prog';
    const out = [D.regions[a] + ' – ' + D.regions[b], (within ? 'Within ' + cell.day + ': Cue 2 − Cue 1' : cell.day) + ' · ' + circSay(C.g)];
    if (!c || !c.E) return out.concat(['Reading…']);
    const s = ran(cell.day);
    if (s < 0) return out.concat(['Not run yet: Drift → Monolith → “Run Precon2/3 and the pair window”.']);
    const g = (q) => val(c.E, s, q, c.b, c.m, p);
    if (!isFinite(g(SQ.mean))) return out.concat(['No rat has it in this session.']);
    return out.concat([(within ? 'Cue 2 − Cue 1 ' + f3(g(SQ.mean)) : 'value ' + sig(g(SQ.mean)))
      + (isFinite(g(SQ.se)) ? ' ± ' + sig(g(SQ.se)) + ' SE' : '') + ' over ' + g(SQ.n) + ' rats',
      cell.day === ALL[0] ? (within ? 'Precon1: the change on the right is measured from here' : 'Precon1: where the change is measured from')
        : 'change from Precon1 ' + f3(g(SQ.chg)) + (isFinite(g(SQ.chg_se)) ? ' ± ' + sig(g(SQ.chg_se)) : ''),
      c.pass && !c.pass.has(p) ? 'Precon4 − Precon1 does not pass the Monolith’s slider here' : '',
      within ? 'Click to open it on the change: its rats, trials and signals. Drag it onto the panels above to follow it.'
        : 'Drag it onto the panels above, or click it, to follow it across the sessions.']);
  }
  function nodeTip(C, r) {
    const D = S(), c = (G[C.g] || {}).data, cell = C.cell, v = view();
    const out = [D.regions[r] + ' power', cell.day + ' · ' + winSay(C.g === 'prog' ? v.w : 'c21') + ' · ' + bandSay(v.b) + ' · ' + layerSay(v.layer)];
    if (!c || !c.Pw) return out.concat(['Reading…']);
    const s = ran(cell.day);
    if (s < 0) return out.concat(['Not run yet.']);
    const g = (q) => val(c.Pw, s, q, c.b, r);
    if (!isFinite(g(SQ.mean))) return out.concat(['Not measured in this session.']);
    return out.concat(['power ' + sig(g(SQ.mean)) + ' log10 over ' + g(SQ.n) + ' rats',
      cell.day === ALL[0] ? '' : 'change from Precon1 ' + f3(g(SQ.chg)) + ' log10',
      'Drag it onto the panels above, or click it, to follow its power across the sessions.']);
  }
  function circSay(g) {
    const v = view();
    return (g && g !== 'prog' ? 'Cue 2 − Cue 1' : winSay(v.w)) + ' · ' + bandSay(v.b) + ' · ' + methodSay(v.m) + ' · '
      + (g && g !== 'prog' ? 'raw' : layerSay(v.layer)) + ' · ' + splitLabel(v.split);
  }
  /* One scale a mode, shared by all four sessions. */
  function scaleOf(v, q, b, x, n, edges) {
    let lo = Infinity, hi = -Infinity, amax = 0;
    for (let s = 0; s < order().length; s++) {
      for (let p = 0; p < n; p++) {
        const y = edges ? val(v, s, q, b, x, p) : val(v, s, q, b, p);
        if (!isFinite(y)) continue;
        if (y < lo) lo = y;
        if (y > hi) hi = y;
        if (Math.abs(y) > amax) amax = Math.abs(y);
      }
    }
    return { lo, hi, amax, signed: q === SQ.chg || (lo < 0 && hi > 0) };
  }
  function edgeLook(y, sc, hide) {
    const ink3 = rgb(css('--ink-3'));
    if (hide || !isFinite(y)) return { w: 0, o: 0, c: ink3 };
    if (sc.signed) {
      const t = sc.amax > 0 ? Math.min(1, Math.abs(y) / sc.amax) : 0;
      return { w: 0.6 + 6.4 * t, o: t < 0.01 ? 0 : 0.18 + 0.82 * t, c: rgb(css(y >= 0 ? '--up' : '--down')) };
    }
    const t = sc.hi > sc.lo ? (y - sc.lo) / (sc.hi - sc.lo) : 0.5;
    return { w: 0.6 + 6.4 * t, o: 0.1 + 0.9 * t, c: rgb(css('--arrow')) };
  }
  function nodeLook(y, sc, mode) {
    if (!isFinite(y)) return { r: 4.5, c: rgb(css('--node-grey')) };
    if (mode === 'chg') {
      const t = sc.amax > 0 ? Math.min(1, Math.abs(y) / sc.amax) : 0;
      return { r: 8, c: lerp3(rgb(css('--surface-2')), rgb(css(y >= 0 ? '--up' : '--down')), 0.15 + 0.85 * t) };
    }
    const t = sc.hi > sc.lo ? (y - sc.lo) / (sc.hi - sc.lo) : 0.5;
    return { r: 5 + 5 * t, c: rgb(css('--node')) };
  }
  /* Edges and nodes from where they are to `to`, over `ms`. */
  function morph(C, to, ms) {
    const from = C.cur || { e: to.e.map((x) => ({ w: 0, o: 0, c: x.c })), n: to.n.map((x) => ({ r: 0, c: x.c })) };
    C.cur = to;
    const frame = (t) => {
      C.paths.forEach((path, p) => {
        const a = from.e[p], b = to.e[p];
        path.setAttribute('stroke-width', lerp(a.w, b.w, t).toFixed(2));
        path.setAttribute('stroke-opacity', lerp(a.o, b.o, t).toFixed(3));
        path.setAttribute('stroke', rgbStr(lerp3(a.c, b.c, t)));
      });
      C.nodes.forEach((node, r) => {
        const a = from.n[r], b = to.n[r];
        node.setAttribute('r', lerp(a.r, b.r, t).toFixed(2));
        node.setAttribute('fill', rgbStr(lerp3(a.c, b.c, t)));
      });
    };
    if (ms) M().tween(ms, frame); else frame(1);
  }
  function legendOf(mode, sc, within) {
    if (!sc || !isFinite(sc.amax) || !(sc.amax > 0)) return 'Nothing measured in this view.';
    if (within) {
      return 'Red: Cue 2 higher than Cue 1; blue: lower. One scale for every session (the widest: ' + sig(sc.amax)
        + '). Descriptive: only the change is tested.';
    }
    if (mode === 'chg') {
      return 'Red: higher than on Precon1; blue: lower. The widest line is a change of ' + sig(sc.amax)
        + ', on one scale for all four sessions. The nodes: each region’s power, coloured the same way.';
    }
    return sc.signed ? 'Red: positive; blue: negative; the widest line is ' + sig(sc.amax) + ', on one scale for all four sessions.'
      : 'Thicker and darker: higher, from ' + sig(sc.lo) + ' (thinnest) to ' + sig(sc.hi) + ' (widest), on one scale for all four sessions. '
        + 'A larger node: more power.';
  }

  /* The Progress circuits' own controls, on the Monolith's card: the
     reading, the layout, how many lines. The view itself is the
     Monolith's (its controls on the right). */
  function renderControls() {
    const host = $('progctl');
    if (!host) return;
    host.innerHTML = '';
    host.appendChild(el('div', { class: 'progctl' }, [
      M().seg(MODES, P.mode, (id) => setMode(id), 'progmode'),
      M().seg(LAYOUTS, P.layout, (id) => setLayout(id), 'proglayout'),
      M().seg(TOPS.map(([n, label, title]) => [String(n), label, title]), String(P.top), (id) => { P.top = Number(id); remember(); renderControls(); drawProg(true); }, 'progtop'),
      el('label', { class: 'pctl pchk' }, [el('input', { type: 'checkbox', id: 'progonly', checked: P.only ? 'checked' : null,
        onchange: (e) => { P.only = e.target.checked; remember(); drawProg(true); } }),
        el('span', { text: 'Only the lines whose Precon4 − Precon1 passes the slider (' + M().LEVELS[M().state.level][0] + ', uncorrected)' })]),
      M().qh('progress.circuits'),
    ]));
  }
  function setMode(id) {
    if (id === P.mode) return;
    P.mode = id;
    remember();
    renderControls();
    drawProg(true);
    renderSeries();
  }
  function setLayout(id) {
    if (id === P.layout) return;
    P.layout = id;
    stopPlay();
    remember();
    renderControls();
    drawProg(true);
  }
  function stepTo(i) {
    P.step = Math.max(0, Math.min(ALL.length - 1, i));
    drawProg(true);
  }
  function stopPlay() {
    if (P.playing) clearTimeout(P.playing);
    P.playing = null;
  }
  function play() {
    if (P.playing) { stopPlay(); drawProg(false); return; }
    P.step = 0;
    drawProg(true);
    const next = () => {
      if (P.step >= ALL.length - 1) { P.playing = null; drawProg(false); return; }
      stepTo(P.step + 1);
      P.playing = setTimeout(next, 1300);
    };
    P.playing = setTimeout(next, 1300);
    renderStepper();
  }
  function renderStepper() {
    const host = $('progstep');
    if (!host) return;
    host.innerHTML = '';
    if (P.layout !== 'step') { host.hidden = true; return; }
    host.hidden = false;
    host.appendChild(el('div', { class: 'progstep' }, [
      M().seg(ALL.map((d, i) => [String(i), d + (ran(d) < 0 ? ' (not run)' : '')]), String(P.step), (i) => { stopPlay(); stepTo(Number(i)); }, 'progsess'),
      el('button', { type: 'button', class: 'more-btn', id: 'progplay', text: P.playing ? 'Stop' : 'Play ▶',
                     title: 'Precon1 to Precon4, each turning into the next', onclick: play }),
    ]));
  }

  /* One group's circuits: built once for a layout, then morphed. `o`:
     {host, rows, key, w (window index), layer, split, flat (cells straight
     into the host), title(cell), mode-reading per cell, legend host}. */
  async function drawGroup(name, o, animate) {
    const D = S();
    const g = G[name] || (G[name] = { key: null, circ: [], seq: 0, data: null });
    const host = $(o.host);
    if (!host) return;
    const fresh = o.key !== g.key || !g.circ.length || !g.circ[0].svg.isConnected;
    if (fresh) {
      g.key = o.key;
      host.innerHTML = '';
      g.circ = [];
      o.rows.forEach((row) => {
        const parent = o.flat ? host : el('div', { class: 'progrow' });
        if (!o.flat && P.mode === 'both' && P.layout === 'all' && name === 'prog') parent.appendChild(el('h3', { class: 'progrowh', text: MODE_SAY[row[0].mode] }));
        const grid = o.flat ? host : el('div', { class: 'progcells' + (P.layout === 'step' && name === 'prog' ? ' step' + (row.length === 1 ? ' one' : '') : '') });
        row.forEach((cell) => {
          const C = makeCircuit(cell, name);
          C.title = el('h4');
          C.say = el('p', { class: 'small muted plegend' });
          C.box = el('div', { class: 'progcell' }, [C.title, C.svg, C.say]);
          grid.appendChild(C.box);
          g.circ.push(C);
        });
        if (!o.flat) { parent.appendChild(grid); host.appendChild(parent); }
      });
    }
    const flat = [].concat(...o.rows);
    g.circ.forEach((C, i) => { C.cell = flat[i]; });
    for (const C of g.circ) {
      const day = C.cell.day;
      C.title.textContent = o.title(C.cell);
      C.box.setAttribute('data-day', day);
      C.box.setAttribute('data-mode', C.cell.mode);
      C.svg.setAttribute('data-day', day);
      C.svg.setAttribute('data-mode', C.cell.mode);
      C.svg.setAttribute('aria-label', o.title(C.cell) + ': ' + circSay(name));
    }
    const v = view();
    const b = idx(D.bands, v.b), m = idx(D.methods, v.m);
    const seq = ++g.seq;
    let E, Pw, pass = null;
    try {
      [E, Pw] = await Promise.all([sessArr('edges', o.layer, v.split, o.w), sessArr('power', o.layer, v.split, o.w).catch(() => null)]);
      if (P.only && name === 'prog') {
        const lk = v.layer + '__' + (v.split || 'all');
        await M().ensureLayer(lk);
        const ok = M().LEVELS[M().state.level][1];
        pass = new Set();
        for (let p = 0; p < D.pairs.length; p++) if (ok(M().E(lk, M().Q.p, o.w, b, m, p))) pass.add(p);
      }
    } catch (e) {
      if (seq !== g.seq) return;
      P.err = e.message;
      if ($(o.errHost)) $(o.errHost).textContent = 'Could not read the sessions: ' + e.message;
      return;
    }
    if (seq !== g.seq) return;
    P.err = null;
    if ($(o.errHost)) $(o.errHost).textContent = '';
    g.data = { E, Pw, b, m, w: o.w, pass };
    const sc = {
      value: { e: scaleOf(E, SQ.mean, b, m, D.pairs.length, true), n: Pw ? scaleOf(Pw, SQ.mean, b, null, D.regions.length, false) : null },
      chg: { e: scaleOf(E, SQ.chg, b, m, D.pairs.length, true), n: Pw ? scaleOf(Pw, SQ.chg, b, null, D.regions.length, false) : null },
    };
    for (const C of g.circ) {
      const s = ran(C.cell.day), mode = C.cell.mode, q = mode === 'chg' ? SQ.chg : SQ.mean;
      const ys = D.pairs.map((_x, p) => (s < 0 ? NaN : val(E, s, q, b, m, p)));
      // The strongest N of this session: by size, or by value when every
      // value is one sign.
      const by = (y) => (sc[mode].e.signed ? Math.abs(y) : y);
      const live = ys.map((y, p) => p).filter((p) => isFinite(ys[p]) && !(pass && !pass.has(p)));
      const keep = new Set(P.top ? live.sort((x, y) => by(ys[y]) - by(ys[x])).slice(0, P.top) : live);
      const e = ys.map((y, p) => edgeLook(y, sc[mode].e, !keep.has(p)));
      const n = D.regions.map((_x, r) => nodeLook(s < 0 || !Pw ? NaN : val(Pw, s, q, b, r), sc[mode].n || {}, mode));
      morph(C, { e, n }, animate && !fresh ? 650 : animate ? 380 : 0);
      C.none.textContent = s < 0 ? 'Not run yet' : (mode === 'chg' && s === 0 ? 'Precon1: the start' : '');
      const measured = ys.filter((y) => isFinite(y)).length;
      const drawn = e.filter((x) => x.o > 0).length;
      C.say.textContent = s < 0 ? 'Precon2 and Precon3 come from one run on the VACC: Drift → Monolith → “Run Precon2/3 and the pair window”.'
        : mode === 'chg' && s === 0 ? 'Every change is measured from here, so nothing is drawn.'
          : (P.top && drawn === Math.min(P.top, live.length) && live.length > P.top
            ? 'The ' + P.top + (mode === 'chg' ? ' that changed most' : ' strongest') + ' of ' + measured + ' region pairs'
            : drawn + ' of ' + measured + ' region pairs') + (pass ? ', of those that pass' : '') + '.';
    }
    if (o.legendHost && $(o.legendHost)) {
      const shown = Array.from(new Set(flat.map((c) => c.mode)));
      $(o.legendHost).textContent = shown.map((mode) => (shown.length > 1 ? MODE_SAY[mode] + ': ' : '') + legendOf(mode, sc[mode].e, name !== 'prog')).join(' ');
    }
    return sc;
  }
  /* Monolith Progress, on the Monolith's card. */
  function skeleton() {
    const host = $('progcircs');
    if (!host || host.dataset.built) return;
    host.dataset.built = '1';
    host.innerHTML = '';                    // what was said while there were no files
    host.appendChild(el('p', { class: 'small', id: 'progsay', text: 'Every Precon session measured as the Monolith measures Precon1 and Precon4, '
      + 'for the view on the right. Descriptive: nothing here is tested; the only p is the Monolith’s own, Precon4 − Precon1, uncorrected.' }));
    host.appendChild(el('div', { id: 'progctl' }));
    host.appendChild(el('div', { id: 'progstep' }));
    host.appendChild(el('p', { class: 'warn', id: 'progerr' }));
    host.appendChild(el('div', { id: 'progcircsin' }));
    host.appendChild(el('p', { class: 'small muted', id: 'proglegend' }));
  }
  function drawProg(animate) {
    if (!sess()) return noSessions('progcircs');
    skeleton();
    renderStepper();
    const D = S();
    return drawGroup('prog', { host: 'progcircsin', rows: cellsOf(), key: P.layout + '|' + (P.mode === 'both' ? 'both' : 'one'),
      w: idx(D.windows, view().w), layer: view().layer, errHost: 'progerr', legendHost: 'proglegend',
      title: (c) => (P.layout === 'step' ? c.day + ' · ' + MODE_SAY[c.mode] : c.day) }, animate);
  }
  /* Cue 2 − Cue 1 within each session: the c21 slot of the session files
     (raw: minus FP takes the same rest from both cues). */
  function drawWithin(animate) {
    if (!sess()) return noSessions('within');
    const D = S();
    const w = idx(D.windows, 'c21');
    if (w < 0) return null;
    const between = ALL.filter((d) => d !== 'Precon1' && d !== 'Precon4');
    drawGroup('within', { host: 'within', flat: true, rows: [['Precon1', 'Precon4'].map((day) => ({ mode: 'value', day }))],
      key: 'within', w, layer: 'raw', legendHost: 'withinlegend', errHost: 'withinlegend',
      title: (c) => 'Within ' + c.day + ' · descriptive' }, animate);
    const bh = $('between');
    if (bh && !bh.dataset.built) {
      bh.dataset.built = '1';
      bh.appendChild(el('h4', { class: 'boxh', text: 'Precon2 and Precon3, between them (descriptive)' }));
      bh.appendChild(el('div', { id: 'betweenin' }));
    }
    return drawGroup('between', { host: 'betweenin', rows: [between.map((day) => ({ mode: 'value', day }))], key: 'between', w, layer: 'raw',
      title: (c) => 'Within ' + c.day }, animate);
  }
  /* A build with no session files: say so, and make them here, now. */
  function noSessions(hostId) {
    const host = $(hostId);
    if (!host) return null;
    host.innerHTML = '';
    host.removeAttribute('data-built');
    for (const k in G) G[k].key = null;
    host.appendChild(el('div', { class: 'progmissing' }, [
      el('p', { class: 'small', text: 'This build of the Monolith has no session files, which ' + (hostId === 'within' ? 'the within-session circuits'
        : 'Monolith Progress') + ' needs: they are made here, from the arrays already fetched, in under a minute.' }),
      el('button', { type: 'button', class: 'more-btn makesessions', id: hostId === 'progcircs' ? 'makesessions' : null,
                     text: P.making ? 'Making them… ' + (P.makeNote || '') : 'Make them now',
                     disabled: P.making ? 'disabled' : null, onclick: makeSessions }),
      P.makeErr ? el('p', { class: 'small warn', text: P.makeErr }) : null,
    ]));
    return null;
  }
  async function makeSessions() {
    if (P.making) return;
    P.making = true; P.makeErr = null; P.makeNote = '';
    M().renderAll();
    try {
      await M().runHere('/sessions', { confirm: true }, (note) => {
        P.makeNote = note;
        for (const b of document.querySelectorAll('.makesessions')) b.textContent = 'Making them… ' + note;
      });
      ARR.clear(); SDATA.clear();
    } catch (e) {
      P.makeErr = /404|not found/i.test(e.message) ? 'Jarvis is running older code without this button: restart it, then press it again.'
        : 'They could not be made: ' + e.message;
    }
    P.making = false;
    M().renderAll();
    renderSeries();
  }

  /* ---------------- dragging an edge onto the panels ---------------- */
  function overDrop(e) {
    const z = $('progseries');
    if (!z) return false;
    const r = z.getBoundingClientRect();
    return e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
  }
  /* `onClick`: what a click does instead -- left out, it follows the line;
     null, nothing (the Monolith's own circuit lifts it out itself). */
  function dragSource(node, make, onClick) {
    let dragged = false;
    node.addEventListener('pointerdown', (ev) => {
      if (ev.button != null && ev.button !== 0) return;
      const x0 = ev.clientX, y0 = ev.clientY;
      let chip = null;
      const move = (e) => {
        if (!chip && Math.hypot(e.clientX - x0, e.clientY - y0) > 6) {
          chip = el('div', { class: 'progchip', id: 'progdrag', text: seriesTitle(make()) });
          document.body.appendChild(chip);
          const t = $('tip');
          if (t) t.style.display = 'none';
        }
        if (!chip) return;
        chip.style.left = (e.clientX + 12) + 'px';
        chip.style.top = (e.clientY + 12) + 'px';
        const z = $('progseries');
        if (z) z.classList.toggle('over', overDrop(e));
      };
      const up = (e) => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
        if (!chip) return;
        chip.remove();
        const z = $('progseries');
        if (z) z.classList.remove('over');
        dragged = true;
        setTimeout(() => { dragged = false; }, 0);
        if (overDrop(e)) addSeries(make(), true);
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    });
    if (onClick === null) return;
    const click = onClick || (() => addSeries(make(), true));
    node.addEventListener('click', () => { if (!dragged) click(); });
    node.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); click(); } });
  }

  /* ---------------- the series: one line across the sessions ---------------- */
  function seriesKey(s) {
    return [s.what, s.what === 'edges' ? s.p : s.r, s.w, s.b, s.what === 'edges' ? s.m : '', s.layer, s.split || 'all'].join('|');
  }
  function seriesTitle(s) {
    const D = S();
    const who = s.what === 'edges' ? short(D.regions[D.pairs[s.p][0]]) + ' – ' + short(D.regions[D.pairs[s.p][1]])
      : short(D.regions[s.r]) + ' power';
    return [who].concat(s.what === 'edges' ? [methodSay(s.m)] : []).concat([bandSay(s.b), winSay(s.w), layerSay(s.layer), splitLabel(s.split)]).join(' · ');
  }
  function addSeries(s, scroll) {
    if (!okSeries(s)) return;
    const k = seriesKey(s);
    if (!P.series.some((x) => seriesKey(x) === k)) P.series.unshift(s);
    remember();
    renderSeries();
    const box = document.querySelector('.progpanel[data-key="' + k + '"]');
    if (box) {
      box.classList.remove('flash');
      void box.offsetWidth;
      box.classList.add('flash');
      if (scroll) { try { box.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch (e) { /* old browser */ } }
    }
  }
  function removeSeries(k) {
    P.series = P.series.filter((x) => seriesKey(x) !== k);
    if (P.drill && P.drill.key === k) P.drill = null;
    remember();
    renderSeries();
  }
  function moveSeries(k, dir) {
    const i = P.series.findIndex((x) => seriesKey(x) === k), j = i + dir;
    if (i < 0 || j < 0 || j >= P.series.length) return;
    [P.series[i], P.series[j]] = [P.series[j], P.series[i]];
    remember();
    renderSeries();
  }
  function entryPath(s) {
    const D = S();
    const w = idx(D.windows, s.w), b = idx(D.bands, s.b);
    const at = s.what === 'edges' ? [w, b, idx(D.methods, s.m), s.p] : [w, b, s.r];
    return { at, path: '/entry?what=' + s.what + '&layer=' + s.layer + '&at=' + at.join(',')
      + (s.split && s.split !== 'all' ? '&split=' + s.split : '') };
  }
  /* A series' numbers: each session's mean, SE, rats and change (the
     session file), and each rat's own value in each session (the entry). */
  function seriesData(s) {
    const k = seriesKey(s);
    if (SDATA.has(k)) return SDATA.get(k);
    const D = S();
    const w = idx(D.windows, s.w), b = idx(D.bands, s.b);
    const { at, path } = entryPath(s);
    const got = Promise.all([
      sessArr(s.what, s.layer, s.split, w),
      M().entryJSON(path).catch((e) => ({ err: e.message })),
    ]).then(([v, det]) => {
      const x = s.what === 'edges' ? idx(D.methods, s.m) : s.r;
      const sessions = ALL.map((day) => {
        const si = ran(day);
        if (si < 0) return null;
        const g = (q) => (s.what === 'edges' ? val(v, si, q, b, x, s.p) : val(v, si, q, b, x));
        return { mean: g(SQ.mean), se: g(SQ.se), n: g(SQ.n), chg: g(SQ.chg), chg_se: g(SQ.chg_se) };
      });
      const rats = ((det && det.rats) || []).map((r) => {
        const xs = {};
        for (const day of ALL) {
          const slot = (r.days || {})[day] || (r.traj || {})[day];
          if (slot && slot.x != null) xs[day] = slot.x;
        }
        return { rat: r.rat, x: xs };
      });
      return { at, path, sessions, rats, det: det && !det.err ? det : null, detErr: det && det.err };
    });
    SDATA.set(k, got);
    got.catch(() => SDATA.delete(k));
    while (SDATA.size > 40) SDATA.delete(SDATA.keys().next().value);
    return got;
  }
  /* Round ticks, about `n` of them, inside lo..hi. */
  function ticks(lo, hi, n) {
    const span = hi - lo;
    if (!(span > 0)) return [lo];
    const raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((x) => x >= raw);
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : v);
    return out;
  }
  const ratY = (r, day, mode) => {
    const v = r.x[day];
    if (v == null) return null;
    if (mode !== 'chg') return v;
    return r.x[ALL[0]] == null ? null : v - r.x[ALL[0]];
  };

  function chart(s, d, mode, Wd) {
    const H = 210, l = 60, r = 14, t = 28, bo = 40;
    const q = mode === 'chg' ? 'chg' : 'mean', qs = mode === 'chg' ? 'chg_se' : 'se';
    const unit = s.what === 'edges' ? UNITS[s.m] || methodSay(s.m) : UNITS.power;
    const vals = [];
    d.sessions.forEach((x) => { if (x && isFinite(x[q])) { vals.push(x[q]); if (isFinite(x[qs])) vals.push(x[q] - x[qs], x[q] + x[qs]); } });
    for (const rr of d.rats) for (const day of ALL) { const y = ratY(rr, day, mode); if (y != null) vals.push(y); }
    if (mode === 'chg') vals.push(0);
    let lo = vals.length ? Math.min(...vals) : 0, hi = vals.length ? Math.max(...vals) : 1;
    if (!(hi > lo)) { lo -= 0.5 * (Math.abs(lo) || 1); hi += 0.5 * (Math.abs(hi) || 1); }
    const pad = 0.08 * (hi - lo);
    lo -= pad; hi += pad;
    const X = (i) => l + (Wd - l - r) * (i + 0.5) / ALL.length;
    const Y = (v) => t + (H - t - bo) * (1 - (v - lo) / (hi - lo));
    const svg = sv('svg', { viewBox: '0 0 ' + Wd + ' ' + H, width: '100%', class: 'mfig progfig', 'data-mode': mode,
                            role: 'img', 'aria-label': seriesTitle(s) + ' — ' + MODE_SAY[mode].toLowerCase() });
    svg.appendChild(sv('text', { x: 4, y: 12, 'font-size': 10.5, fill: css('--ink-2'), 'font-weight': 600 },
      (mode === 'chg' ? 'Change from Precon1, ' : '') + unit));
    svg.appendChild(sv('rect', { x: l, y: t, width: Wd - l - r, height: H - t - bo, fill: css('--surface-2'), stroke: css('--line') }));
    ticks(lo, hi, 4).forEach((v) => {
      svg.appendChild(sv('text', { x: l - 5, y: (Y(v) + 3.5).toFixed(1), 'text-anchor': 'end', 'font-size': 10, fill: css('--ink-3') }, String(+v.toFixed(10))));
      svg.appendChild(sv('line', { x1: l, x2: Wd - r, y1: Y(v).toFixed(1), y2: Y(v).toFixed(1), stroke: css('--line') }));
    });
    if (mode === 'chg') {
      svg.appendChild(sv('line', { x1: l, x2: Wd - r, y1: Y(0).toFixed(1), y2: Y(0).toFixed(1), stroke: css('--ink-3'), 'stroke-dasharray': '4 3' }));
    }
    ALL.forEach((day, i) => {
      const off = ran(day) < 0;
      svg.appendChild(sv('text', { x: X(i).toFixed(1), y: H - bo + 15, 'text-anchor': 'middle', 'font-size': 10.5,
                                   fill: off ? css('--ink-3') : css('--ink'), 'font-weight': off ? null : 600 }, day));
      if (off) svg.appendChild(sv('text', { x: X(i).toFixed(1), y: H - bo + 28, 'text-anchor': 'middle', 'font-size': 9.5, fill: css('--ink-3') }, 'not run yet'));
    });
    // Each rat, thin, its own colour.
    const n = d.rats.length;
    d.rats.forEach((rr, ri) => {
      let dd = '';
      const pts = [];
      ALL.forEach((day, i) => {
        const y = ratY(rr, day, mode);
        if (y == null) return;
        dd += (dd ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(y).toFixed(1);
        pts.push([day, i, y]);
      });
      const g = sv('g', { class: 'pratline', 'data-rat': String(rr.rat) });
      if (dd) g.appendChild(sv('path', { d: dd, fill: 'none', stroke: ratColor(ri, n), 'stroke-width': 1.1, 'stroke-opacity': 0.65 }));
      for (const [day, i, y] of pts) {
        const c = sv('circle', { cx: X(i).toFixed(1), cy: Y(y).toFixed(1), r: 2.8, fill: ratColor(ri, n), class: 'pratpt',
                                 'data-rat': String(rr.rat), 'data-day': day });
        M().hover(c, ['r' + rr.rat + ' · ' + day, (mode === 'chg' ? 'change from Precon1 ' + f3(y) : 'value ' + sig(y)),
                      'Click for its trials.']);
        c.addEventListener('click', () => openDrill(s, day, rr.rat));
        g.appendChild(c);
      }
      svg.appendChild(g);
    });
    // The mean over rats, ± SE, session by session.
    let md = '';
    d.sessions.forEach((x, i) => { if (x && isFinite(x[q])) md += (md ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(x[q]).toFixed(1); });
    if (md) svg.appendChild(sv('path', { d: md, fill: 'none', stroke: css('--ink'), 'stroke-width': 2.2, class: 'pmean' }));
    d.sessions.forEach((x, i) => {
      const day = ALL[i];
      if (!x || !isFinite(x[q])) return;
      if (isFinite(x[qs])) {
        svg.appendChild(sv('line', { x1: X(i).toFixed(1), x2: X(i).toFixed(1), y1: Y(x[q] - x[qs]).toFixed(1), y2: Y(x[q] + x[qs]).toFixed(1),
                                     stroke: css('--ink'), 'stroke-width': 1.4 }));
      }
      const g = sv('g', { class: 'progpt', 'data-day': day, tabindex: '0', role: 'button',
                          'aria-label': day + ': ' + sig(x[q]) + ', open its rats' });
      g.appendChild(sv('circle', { cx: X(i).toFixed(1), cy: Y(x[q]).toFixed(1), r: 13, fill: 'transparent' }));
      g.appendChild(sv('circle', { cx: X(i).toFixed(1), cy: Y(x[q]).toFixed(1), r: 5, fill: css('--ink'), stroke: css('--surface'), 'stroke-width': 1.5,
                                   class: 'pmeanpt', 'data-y': String(x[q]) }));
      M().hover(g, [day + ' · ' + MODE_SAY[mode].toLowerCase(), sig(x[q]) + (isFinite(x[qs]) ? ' ± ' + sig(x[qs]) + ' SE' : '') + ' over ' + x.n + ' rats',
        day === ALL[0] ? 'Where every change starts' : 'change from Precon1 ' + f3(x.chg), 'Click for this session’s rats, then a rat’s trials.']);
      g.addEventListener('click', () => openDrill(s, day, null));
      g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openDrill(s, day, null); } });
      svg.appendChild(g);
    });
    return svg;
  }

  function openDrill(s, day, rat) {
    const k = seriesKey(s);
    P.drill = { key: k, day, rat };
    const box = document.querySelector('.progpanel[data-key="' + k + '"]');
    if (box) seriesData(s).then((d) => renderDrill(box, s, d));
  }
  function renderDrill(box, s, d) {
    const host = box.querySelector('.progdrill');
    host.innerHTML = '';
    const k = seriesKey(s);
    if (!P.drill || P.drill.key !== k) return;
    const { day, rat } = P.drill;
    const dbox = el('div', { class: 'dbox', id: 'progdrill' });
    dbox.appendChild(el('div', { class: 'hrow' }, [el('h4', { text: day + ' · ' + seriesTitle(s) }),
      el('button', { type: 'button', class: 'more-btn pclose', text: 'Close ✕', onclick: () => { P.drill = null; renderDrill(box, s, d); } })]));
    host.appendChild(dbox);
    if (ran(day) < 0) {
      dbox.appendChild(el('p', { class: 'small muted', text: day + ' is not in this Monolith yet: Drift → Monolith → “Run Precon2/3 and the pair window”, then fetch.' }));
      return;
    }
    if (!d.det) { dbox.appendChild(el('p', { class: 'warn', text: 'Could not read the rats: ' + (d.detErr || 'no answer') })); return; }
    const minus = s.layer === 'minus_fp';
    dbox.appendChild(el('p', { class: 'small muted', text: 'Each rat’s ' + day + ' value: the mean over its trials'
      + (minus ? ', less the mean over its FP1/FP2 epochs' : '') + '. Click a rat for its trials.' }));
    const n = d.det.rats.length;
    dbox.appendChild(el('div', { class: 'prograts' }, d.det.rats.map((r, ri) => {
      const slot = (r.days || {})[day] || (r.traj || {})[day];
      const x = slot ? slot.x : null;
      const p1 = ((r.days || {})[ALL[0]] || {}).x;
      return el('button', { type: 'button', 'data-rat': String(r.rat), 'aria-pressed': String(rat === r.rat),
                            disabled: x == null ? 'disabled' : null, onclick: () => openDrill(s, day, r.rat) },
        [el('b', { class: 'sw', style: 'background:' + ratColor(ri, n) }),
         'r' + r.rat + ' ' + (x == null ? '—' : sig(x)) + (x != null && p1 != null && day !== ALL[0] ? ' (' + f3(x - p1) + ')' : '')]);
    })));
    if (rat == null) return;
    const r = d.det.rats.find((x) => x.rat === rat);
    const slot = r && ((r.days || {})[day] || (r.traj || {})[day]);
    if (!slot) { dbox.appendChild(el('p', { class: 'small muted', text: 'r' + rat + ' has no ' + day + ' here.' })); return; }
    const rest = minus && slot.rest != null ? slot.rest : 0;
    const units = (slot.units || []).map((u) => ({ id: u.id, label: u.label, pair: u.pair, seat_say: u.seat_say,
                                                   v: u.v == null ? null : u.v - rest, why: u.why }));
    dbox.appendChild(el('p', { class: 'small', text: 'r' + rat + ' · ' + day + ': ' + units.length + ' trials, in order'
      + (minus && slot.rest != null ? ', each less the session’s FP (' + sig(slot.rest) + ')' : '')
      + '. ' + (s.what === 'edges' ? 'Click one to see its traces and how its number was made.'
        : 'Power has no trace view of its own: follow one of this region’s edges to open a trial.') }));
    // A strip: each presentation's value, in order.
    const Wd = Math.max(280, Math.min(720, host.clientWidth || 560)), H = 120, l = 52, rr = 10, t = 10, bo = 22;
    const ys = units.map((u) => u.v).filter((v) => v != null);
    let lo = ys.length ? Math.min(...ys) : 0, hi = ys.length ? Math.max(...ys) : 1;
    if (!(hi > lo)) { lo -= 0.5; hi += 0.5; }
    const X = (i) => l + (Wd - l - rr) * (units.length === 1 ? 0.5 : i / (units.length - 1));
    const Y = (v) => t + (H - t - bo) * (1 - (v - lo) / (hi - lo));
    const svg = sv('svg', { viewBox: '0 0 ' + Wd + ' ' + H, width: '100%', class: 'mfig progstrip', role: 'img',
                            'aria-label': 'r' + rat + ' ' + day + ': every trial' });
    [lo, hi].forEach((v) => svg.appendChild(sv('text', { x: l - 5, y: (Y(v) + 3.5).toFixed(1), 'text-anchor': 'end', 'font-size': 10, fill: css('--ink-3') }, sig(v))));
    svg.appendChild(sv('line', { x1: l, x2: Wd - rr, y1: Y(slot.x != null ? slot.x : (lo + hi) / 2).toFixed(1), y2: Y(slot.x != null ? slot.x : (lo + hi) / 2).toFixed(1),
                                 stroke: css('--ink-3'), 'stroke-dasharray': '4 3' }));
    svg.appendChild(sv('text', { x: l, y: H - 6, 'font-size': 10, fill: css('--ink-3') }, 'first'));
    svg.appendChild(sv('text', { x: Wd - rr, y: H - 6, 'font-size': 10, 'text-anchor': 'end', fill: css('--ink-3') }, 'last trial'));
    const ids = units.map((u) => u.id);
    units.forEach((u, i) => {
      const g = sv('g', { class: 'progunit', 'data-unit': u.id, tabindex: u.v == null || s.what !== 'edges' ? null : '0' });
      g.appendChild(sv('circle', { cx: X(i).toFixed(1), cy: (u.v == null ? H - bo : Y(u.v)).toFixed(1), r: 4,
        fill: u.v == null ? 'none' : css('--ink'), stroke: u.v == null ? css('--ink-3') : css('--surface'), 'stroke-width': 1.2 }));
      M().hover(g, ['r' + rat + ' · ' + day + ' · ' + u.id, u.seat_say || ((u.label || '') + (u.pair ? ' (' + u.pair + ')' : '')),
        u.v == null ? 'Not measured: ' + (u.why || 'no value') : 'value ' + sig(u.v),
        s.what === 'edges' ? 'Click to see its traces.' : '']);
      if (s.what === 'edges' && u.v != null) {
        const open = () => M().openLeaf(rat, day, u.id, { at: d.at.slice(), units: { [day]: ids }, layer: s.layer });
        g.addEventListener('click', open);
        g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
      }
      svg.appendChild(g);
    });
    dbox.appendChild(svg);
  }

  function panelWidth(host) {
    const w = host.clientWidth || ($('progseries') || {}).clientWidth || 600;
    return Math.max(280, Math.min(900, P.mode === 'both' && w > 760 ? (w - 12) / 2 : w));
  }
  function renderSeries() {
    const host = $('progpanels');
    if (!host) return;
    if (!sess()) { noSessions('progpanels'); return; }
    host.innerHTML = '';
    $('progcount').textContent = P.series.length ? P.series.length + ' line' + (P.series.length === 1 ? '' : 's') + ' followed' : '';
    if (!P.series.length) {
      host.appendChild(el('p', { class: 'empty', text: 'No line followed yet. Drag an edge or a node from a circuit below into this box, '
        + 'click one, or build one with the form.' }));
      return;
    }
    P.series.forEach((s, i) => {
      const k = seriesKey(s);
      const plot = el('div', { class: 'progplot' + (P.mode === 'both' ? ' two' : '') });
      const sayP = el('p', { class: 'small muted progp' });
      const box = el('div', { class: 'progpanel', 'data-key': k }, [
        el('div', { class: 'hrow progph' }, [
          el('h3', { text: seriesTitle(s) }),
          s.what === 'edges' ? el('button', { type: 'button', text: 'On the circuit', title: 'Show this line on the circuit below, Precon4 − Precon1', onclick: () => toMonolith(s) }) : null,
          el('button', { type: 'button', text: '↑', title: 'Move up', 'aria-label': 'Move up', disabled: i === 0 ? 'disabled' : null, onclick: () => moveSeries(k, -1) }),
          el('button', { type: 'button', text: '↓', title: 'Move down', 'aria-label': 'Move down', disabled: i === P.series.length - 1 ? 'disabled' : null, onclick: () => moveSeries(k, 1) }),
          el('button', { type: 'button', text: '✕', title: 'Stop following it', 'aria-label': 'Remove', class: 'premove', onclick: () => removeSeries(k) }),
        ]),
        plot, sayP, el('div', { class: 'progdrill' }),
      ]);
      host.appendChild(box);
      plot.appendChild(el('p', { class: 'loading', text: 'Reading every session…' }));
      seriesData(s).then((d) => {
        if (!box.isConnected) return;
        plot.innerHTML = '';
        const Wd = panelWidth(plot);
        (P.mode === 'both' ? ['value', 'chg'] : [P.mode]).forEach((mode) => plot.appendChild(chart(s, d, mode, Wd)));
        const pl = (d.det || {}).pooled || {};
        sayP.textContent = 'Precon4 − Precon1 on the Monolith: ' + (pl.est != null ? f3(pl.est) : '—')
          + (pl.p != null ? ', p ' + fp(pl.p) + ' (uncorrected) over ' + pl.k + ' rats' : ', not tested' + (pl.why ? ' (' + pl.why + ')' : ''))
          + '. Precon2 and Precon3 are never tested: read the shape. Thick line: the mean over rats ± SE; thin lines: each rat.'
          + (d.detErr ? ' The rats could not be read: ' + d.detErr : '');
        renderDrill(box, s, d);
      }).catch((e) => {
        if (!box.isConnected) return;
        plot.innerHTML = '';
        plot.appendChild(el('p', { class: 'warn', text: 'Could not read it: ' + e.message }));
      });
    });
  }
  /* The line on the circuit itself: Precon4 − Precon1 (or its tab, for
     Cue 2 − Cue 1), selected. */
  async function toMonolith(s) {
    const D = S();
    const w = D.windows.find((x) => x.id === s.w);
    try { await M().ensureLayer(s.layer + '__' + (s.split || 'all')); } catch (e) { /* the Monolith says so */ }
    M().closeGhost(true);
    const tab = w.kind === 'contrast' ? 'c21' : 'main';
    if (M().state.tab !== tab) M().showTab(tab);
    M().set({ layer: s.layer, split: s.split || 'all', kind: w.kind, win: s.w, band: s.b, method: s.m, hi: null, sel: s.p, prog: false });
    const card = $('circcard');
    if (card) { try { card.scrollIntoView({ block: 'start' }); } catch (e) { /* old browser */ } }
  }

  /* ---------------- building a line by hand ---------------- */
  function renderBuilder() {
    const host = $('progbuild');
    if (!host) return;
    host.innerHTML = '';
    const D = S();
    const v0 = view();
    const v = P.build || (P.build = { what: 'edges', a: D.pairs[0][0], b: D.pairs[0][1], r: 0, m: v0.m, band: v0.b,
                                       w: v0.w, layer: v0.layer, split: v0.split });
    const pick = (label, id, opts, cur, on) => el('label', {}, [label, el('select', { id, onchange: (e) => { on(e.target.value); renderBuilder(); } },
      opts.map(([x, text]) => el('option', { value: x, selected: String(x) === String(cur) ? 'selected' : null, text })))]);
    const regs = D.regions.map((r, i) => [i, r]);
    const splits = [['all', 'AB and CD pooled']].concat(((D.splits || {}).groups || []).map((g) => [g.id, g.label]));
    const kids = [pick('What', 'pbwhat', [['edges', 'An edge'], ['power', 'A node’s power']], v.what, (x) => { v.what = x; })];
    if (v.what === 'edges') {
      kids.push(pick('Region', 'pba', regs, v.a, (x) => { v.a = Number(x); }));
      kids.push(pick('and', 'pbb', regs.filter(([i]) => i !== v.a), v.b, (x) => { v.b = Number(x); }));
      kids.push(pick('Measure', 'pbm', D.methods.map((m) => [m.id, m.label]), v.m, (x) => { v.m = x; }));
    } else {
      kids.push(pick('Region', 'pbr', regs, v.r, (x) => { v.r = Number(x); }));
    }
    kids.push(pick('Frequency', 'pbf', D.bands.map((b) => [b.id, b.named ? b.label : b.hz + ' Hz']), v.band, (x) => { v.band = x; }));
    kids.push(pick('Window', 'pbw', D.windows.map((w) => [w.id, w.label]), v.w, (x) => { v.w = x; }));
    kids.push(pick('', 'pbl', [['raw', 'Raw'], ['minus_fp', 'Minus FP']], v.layer, (x) => { v.layer = x; }));
    kids.push(pick('Cue pairs', 'pbs', splits, v.split, (x) => { v.split = x; }));
    kids.push(el('button', { type: 'button', class: 'more-btn', id: 'pbadd', text: 'Follow it', onclick: () => addSeries(built(), true) }));
    host.appendChild(el('div', { class: 'progbuild' }, kids));
  }
  /* The form's line. A directed measure asked the other way round is the
     pair's other direction. */
  function built() {
    const D = S(), v = P.build;
    if (v.what === 'power') return { what: 'power', r: v.r, w: v.w, b: v.band, layer: v.layer, split: v.split };
    if (v.a === v.b) v.b = D.pairs.find(([x, y]) => x === v.a || y === v.a).find((z) => z !== v.a);
    let p = D.pairs.findIndex(([x, y]) => x === v.a && y === v.b);
    let m = v.m;
    if (p < 0) {
      p = D.pairs.findIndex(([x, y]) => x === v.b && y === v.a);
      m = m === 'gc_ab' ? 'gc_ba' : m === 'gc_ba' ? 'gc_ab' : m;
    }
    return { what: 'edges', p, w: v.w, b: v.band, m, layer: v.layer, split: v.split };
  }

  /* ---------------- taking it away ---------------- */
  async function exportCSV() {
    const rows = [['line', 'what', 'layer', 'cue_pairs', 'window', 'frequency', 'measure', 'session', 'rat', 'value', 'se', 'rats', 'change_from_precon1', 'change_se']];
    const q = (x) => '"' + String(x == null ? '' : x).replace(/"/g, '""') + '"';
    const num = (x) => (x == null || !isFinite(x) ? '' : String(x));
    for (const s of P.series) {
      let d;
      try { d = await seriesData(s); } catch (e) { continue; }
      const base = [seriesTitle(s), s.what, s.layer, splitLabel(s.split), winSay(s.w), bandSay(s.b), s.what === 'edges' ? methodSay(s.m) : 'power'];
      ALL.forEach((day, i) => {
        const x = d.sessions[i];
        if (x) rows.push(base.concat([day, 'mean over rats', num(x.mean), num(x.se), num(x.n), num(x.chg), num(x.chg_se)]));
        for (const r of d.rats) {
          if (r.x[day] == null) continue;
          rows.push(base.concat([day, 'r' + r.rat, num(r.x[day]), '', '', num(r.x[ALL[0]] == null ? null : r.x[day] - r.x[ALL[0]]), '']));
        }
      });
    }
    const text = rows.map((r, ri) => r.map((c, i) => (ri === 0 || i < 9 ? q(c) : c)).join(',')).join('\n');
    M().download('monolith-progress.csv', new Blob([text], { type: 'text/csv' }));
  }
  function exportSVG() {
    const figs = Array.from(document.querySelectorAll('#progpanels .progpanel'));
    const Wd = 980;
    let y = 24;
    const out = document.createElementNS(NS, 'svg');
    out.setAttribute('xmlns', NS);
    const body = [];
    for (const box of figs) {
      const title = (box.querySelector('h3') || {}).textContent || '';
      body.push(['title', title, y]);
      y += 18;
      const svgs = Array.from(box.querySelectorAll('svg.progfig'));
      let x = 0, rowH = 0;
      for (const s of svgs) {
        const vb = (s.getAttribute('viewBox') || '0 0 600 210').split(/\s+/).map(Number);
        body.push(['fig', s, x, y, vb]);
        x += vb[2] + 12;
        rowH = Math.max(rowH, vb[3]);
      }
      y += rowH + 22;
    }
    const W2 = Math.max(Wd, ...body.filter((b) => b[0] === 'fig').map((b) => b[2] + b[4][2]));
    out.setAttribute('viewBox', '0 0 ' + W2 + ' ' + y);
    out.setAttribute('width', W2);
    out.setAttribute('height', y);
    const bg = sv('rect', { x: 0, y: 0, width: W2, height: y, fill: css('--surface') || '#fff' });
    out.appendChild(bg);
    for (const b of body) {
      if (b[0] === 'title') { out.appendChild(sv('text', { x: 0, y: b[2] + 12, 'font-size': 13, 'font-weight': 600, fill: css('--ink'), 'font-family': 'sans-serif' }, b[1])); continue; }
      const g = sv('g', { transform: 'translate(' + b[2] + ',' + b[3] + ')' });
      for (const c of Array.from(b[1].childNodes)) g.appendChild(c.cloneNode(true));
      out.appendChild(g);
    }
    M().download('monolith-progress.svg', new Blob([new XMLSerializer().serializeToString(out)], { type: 'image/svg+xml' }));
  }

  /* ---------------- on the page ---------------- */
  // The panels' card, in the Monolith tab's left column, over the circuit.
  function mountSeries() {
    const host = $('progseries');
    if (!host || !S()) return;
    if (!P.shown) { recall(); P.shown = true; }
    if (!host.dataset.built) {
      host.dataset.built = '1';
      const qh = (k) => M().qh(k);
      host.appendChild(el('div', { class: 'hrow' }, [el('h2', { text: 'Follow a line across the sessions' }), qh('progress.series'),
        el('span', { class: 'small muted', id: 'progcount' })]));
      host.appendChild(el('div', { class: 'progdrop', id: 'progdrop' }, [
        el('p', { class: 'small', text: 'Drag a line or a node here from any circuit, or build one.' }),
        el('div', { id: 'progbuild' }),
      ]));
      host.appendChild(el('div', { class: 'hrow progexp' }, [
        el('button', { type: 'button', class: 'more-btn', id: 'progcsv', text: 'CSV', title: 'Every line followed: each session and each rat', onclick: exportCSV }),
        el('button', { type: 'button', class: 'more-btn', id: 'progsvg', text: 'SVG', title: 'The panels, as one picture', onclick: exportSVG }),
      ]));
      host.appendChild(el('div', { id: 'progpanels' }));
    }
    renderBuilder();
    renderSeries();
  }
  // The circuit card, as the Monolith draws it on every render: Monolith
  // Progress's circuits (the Monolith tab, its button on), or Cue 2 − Cue 1
  // within each session (its own tab).
  function render(o) {
    if (!S()) return;
    if (!P.shown) { recall(); P.shown = true; }
    o = o || {};
    if (o.prog) { if (sess()) skeleton(); renderControls(); drawProg(true); } else stopPlay();
    if (o.contrast) drawWithin(true);
  }
  /* The line the Monolith has selected, followed in a panel. */
  function addFromMain() {
    const st = M().state;
    if (!P.shown) { recall(); P.shown = true; }
    if (st.sel != null) addSeries({ what: 'edges', p: st.sel, w: st.win, b: st.band, m: st.method, layer: st.layer, split: st.split || 'all' }, true);
  }
  /* A line of the Monolith's own circuit: it drags onto the panels too (a
     click there still lifts it out, as before). */
  function dragFromMain(node, p, bandId) {
    dragSource(node, () => Object.assign(edgeSeries(p), bandId ? { b: bandId } : {}), null);
  }
  let rz = null;
  window.addEventListener('resize', () => {
    clearTimeout(rz);
    rz = setTimeout(() => { const t = M() && M().state.tab; if ((t === 'main' || t === 'c21') && P.shown) renderSeries(); }, 200);
  });

  return {
    render, mountSeries, addFromMain, dragFromMain, addSeries, removeSeries, moveSeries, setMode, setLayout, stepTo, play, stopPlay,
    seriesKey, seriesTitle, exportCSV, exportSVG, built, makeSessions,
    // A Monolith read again (rebuilt, or Precon2/3 added): read every file again.
    forget() { ARR.clear(); SDATA.clear(); for (const k in G) G[k].key = null; },
    get state() { return { mode: P.mode, layout: P.layout, step: P.step, top: P.top, only: P.only,
                           series: P.series.slice(), drill: P.drill ? Object.assign({}, P.drill) : null, err: P.err, playing: !!P.playing,
                           making: !!P.making }; },
    get cur() { return (G.prog || {}).data; },
    get within() { return (G.within || {}).data; },
    set build(v) { P.build = v; renderBuilder(); },
    get build() { return P.build; },
  };
})();
