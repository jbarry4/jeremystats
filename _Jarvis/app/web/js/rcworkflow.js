/* rcworkflow.js -- Root Canal's Workflow tab (2026-11-05).

   "Create a Workflow tab in Root Canal: 1. Verified dentate spikes,
   2. Verified P-spikes, 3. Ambiguous -- Define border, Apply border,
   Extract spikes. I want to be able to see the 3D graphs of each stage.
   Workflows can be constructed and archived. Their results go to the bank,
   viewable and easily reconstructed, and every event can be traced back to
   the recording's waveforms."

   One module, painted by Root Canal when its view bar says Workflow
   (rootcanal.js, `paint_`). The server does every number
   (backend/rcworkflow.py, the /api/rootcanal/workflow* routes); this draws
   them:

     the pipeline strip   three stage cards per workflow, each a small
                          picture, its counts and its state
     the stage in 3D      rotatable, with the border's box (and the other
                          border's, for Ambiguous), every dot pickable
     beside it            the three 2D views with the cut-offs, how far each
                          event is from the box, the grace sweep, the flow
                          from mice to classes, every mouse on its own, the
                          class averages and the conflicts
     the picked event     its three numbers against the cut-offs, its
                          history, its waveform and CSD, and Xplorefinder
     the lineage          every version, what each run moved, rebuild

   Nothing here banks or saves without a press that says it will. */
'use strict';

BARRY.rcWorkflow = (function () {
  const ARCH_KEY = 'rootcanal_workflow_archive';
  const KIND_WORDS = {
    ds: 'Verified dentate spikes', pspike: 'Verified P-spikes',
    ambiguous: 'Ambiguous',
  };
  const KIND_ORDER = ['ds', 'pspike', 'ambiguous'];
  const STAGES = [['define', 'Define border'], ['apply', 'Apply border'],
                  ['extract', 'Extract']];
  // Column name, event key, words, unit.
  const AX = [['amp', 'amp_uV', 'max amplitude', 'µV'],
              ['hf', 'hf_db', 'HF power', 'dB'],
              ['hw', 'hw_ms', 'half-width', 'ms']];
  const GRACES = [[0, 'none'], [0.01, '1%'], [0.05, '5%']];

  const W = {
    list: null, listErr: null, loading: false,
    sources: null, sourcesErr: null,
    data: {},            // artifact id -> {version, payload, lines, stale}
    openId: null, openVersion: null, stage: 'apply',
    builder: null, prep: null, preview: null,
    showArchived: false,
    view: { yaw: -0.65, pitch: 0.42, zoom: 1 },
    picked: null,        // {which: 'src'|'tgt', n}
    ev: null,            // the picked event's traces: {busy, data, err}
    avg: null,           // {label, busy, data, err}
    ambShow: 'all', ambPick: new Set(), ambType: 'ied',
    busy: null,
  };
  let H = null;          // what Root Canal lends: render, openPool, path
  let root = null;

  const tok = (n, f) => BARRY.token(n, f);
  const fmt = (v, d) => (v == null || !isFinite(v) ? '—'
    : Math.abs(v) >= 100 ? Math.round(v).toLocaleString()
    : Number(v).toFixed(d == null ? 1 : d));
  const pct = (v) => (v == null ? '—' : (100 * v).toFixed(v < 0.1 ? 1 : 0) + '%');
  const graceWords = (g) => (Number(g) === 0 ? 'none'
    : +(100 * Number(g)).toFixed(2) + '%');

  /* ==================================================================
     Archive (a shared preference, like the borders' -- rootcanal.js)
     ================================================================== */
  function archived() {
    try { return (BARRY.prefs && BARRY.prefs.get(ARCH_KEY, {})) || {}; }
    catch (e) { return {}; }
  }

  async function setArchived(row, on) {
    const m = Object.assign({}, archived());
    if (on) m[row.artifact_id] = { at: new Date().toISOString() };
    else delete m[row.artifact_id];
    BARRY.prefs.set(ARCH_KEY, m);
    /* And what it banked, with it (decided 2026-11-05): archived, never
       deleted, and put back the same way. */
    const ids = new Set();
    const d = W.data[row.artifact_id];
    for (const ln of (d && d.lines) || []) {
      if (ln.bank && ln.bank.entry_id) ids.add(ln.bank.entry_id);
    }
    if (row.bank && row.bank.entry_id) ids.add(row.bank.entry_id);
    let n = 0;
    for (const id of ids) {
      try {
        await apiPost('/api/bank/' + encodeURIComponent(id) + '/archive',
                      { archived: !!on });
        n += 1;
      } catch (e) {
        toast('The workflow was ' + (on ? 'archived' : 'put back')
              + ' but its bank entry ' + id + ' was not: ' + e.message,
              'warn', 9000);
      }
    }
    toast((on ? 'Archived ‘' : 'Put back ‘') + (row.nickname || row.name) + '’'
          + (n ? ', and the ' + n + ' bank entr' + (n === 1 ? 'y' : 'ies')
                 + ' it made' : '') + '.', 'ok', 6000);
    BARRY.activity.log('rootcanal.workflow_archive',
                       { artifact: row.artifact_id, archived: !!on });
    refresh();
  }

  /* ==================================================================
     Loading
     ================================================================== */
  async function loadList() {
    if (W.loading) return;
    W.loading = true;
    try {
      const got = await api('/api/rootcanal/workflows');
      W.list = got.workflows || [];
      W.listErr = null;
    } catch (e) {
      W.list = W.list || [];
      W.listErr = e.message;
    }
    W.loading = false;
    refresh();
    // Each workflow's newest version, for its strip's pictures.
    for (const r of W.list || []) {
      if (r.ran && !(W.data[r.artifact_id]
                     && W.data[r.artifact_id].version === r.version)) {
        loadOne(r.artifact_id, null, true);
      }
    }
  }

  async function loadSources() {
    if (W.sources) return W.sources;
    try {
      W.sources = await api('/api/rootcanal/workflow/sources');
      W.sourcesErr = null;
    } catch (e) {
      W.sourcesErr = e.message;
      W.sources = { pools: [], sets: [] };
    }
    return W.sources;
  }

  async function loadOne(id, version, quiet) {
    try {
      const got = await api('/api/rootcanal/workflow/' + encodeURIComponent(id)
                            + (version != null ? '?version=' + version : ''));
      W.data[id] = { version: (got.artifact || {}).version, shown: version,
                     payload: got.payload || {}, lines: got.lines || [],
                     stale: got.stale || [] };
    } catch (e) {
      if (!quiet) toast('That workflow could not be opened: ' + e.message,
                        'err', 9000);
      return null;
    }
    refresh();
    return W.data[id];
  }

  /* The run on show: a preview, or the open workflow's chosen version. */
  function shownRun() {
    if (W.preview) return W.preview.run;
    const d = W.openId && W.data[W.openId];
    return d && d.payload ? d.payload.run : null;
  }
  function shownDef() {
    if (W.preview) return W.preview.definition;
    const d = W.openId && W.data[W.openId];
    return d && d.payload ? d.payload.definition : null;
  }

  /* ==================================================================
     Events, out of a run's columns
     ================================================================== */
  function pointsOf(col) {
    if (!col) return [];
    const out = [];
    const n = (col.t || []).length;
    for (let j = 0; j < n; j++) {
      out.push({
        n: j, amp: col.amp[j], hf: col.hf[j], hw: col.hw[j],
        cls: col.cls[j], g: col.g[j], m: col.m[j], i: col.i[j],
        t: col.t[j], mouse: (col.mouse || [])[j],
        gid: (col.gids || [])[col.g[j]] || null,
        da: col.d_a ? col.d_a[j] : null, db: col.d_b ? col.d_b[j] : null,
      });
    }
    return out;
  }

  const finite = (v) => v != null && isFinite(v);
  const measured = (p) => finite(p.amp) && finite(p.hf) && finite(p.hw);

  /* One frame for every picture of a run: every axis spans the same values
     in every stage, so a box does not seem to move when the stage does. */
  function rangesOf(run) {
    const all = pointsOf(run.cols).concat(pointsOf(run.src_cols));
    const out = {};
    for (const [c] of AX) {
      const v = all.map((p) => p[c]).filter(finite).sort((a, b) => a - b);
      if (!v.length) { out[c] = [0, 1]; continue; }
      const q = (f) => v[Math.min(v.length - 1, Math.max(0, Math.floor(f * (v.length - 1))))];
      let lo = q(0.005), hi = q(0.995);
      if (hi <= lo) { lo -= 1; hi += 1; }
      const pad = (hi - lo) * 0.06;
      out[c] = [lo - pad, hi + pad];
    }
    return out;
  }

  /* The boxes of a run: [{lo, hi (by column), colour, dashed, label}]. */
  function boxesOf(run, kind) {
    const out = [];
    const add = (border, grace, colour, words) => {
      if (!border) return;
      const lv = (border.levels || []).find(
        (l) => Math.abs(Number(l.grace) - Number(grace)) < 1e-9);
      const st = border.strict || {};
      const mk = (src) => {
        const lo = {}, hi = {};
        for (const [c, k] of AX) { lo[c] = (src[k] || {}).lo; hi[c] = (src[k] || {}).hi; }
        return { lo, hi };
      };
      if (lv) out.push(Object.assign(mk(lv.edges || {}), { colour, dashed: false,
        label: words + ' border, grace ' + graceWords(grace) }));
      if (Number(grace) > 0) {
        out.push(Object.assign(mk(st), { colour, dashed: true,
          label: words + ' border at no grace' }));
      }
    };
    if (kind === 'ambiguous') {
      const b = run.borders || {};
      add(b.ds && b.ds.border, b.ds && b.ds.grace, tok('--call-ds'), 'DS');
      add(b.pspike && b.pspike.border, b.pspike && b.pspike.grace,
          tok('--call-p'), 'P-spike');
    } else {
      add(run.border, run.grace, kind === 'ds' ? tok('--call-ds') : tok('--call-p'),
          kind === 'ds' ? 'DS' : 'P-spike');
    }
    return out;
  }

  function colourOf(kind, cls, which) {
    const DS = tok('--call-ds'), P = tok('--call-p');
    if (kind === 'ambiguous') {
      return cls === 'ds' ? DS : cls === 'pspike' ? P
        : cls === 'both' ? tok('--warn') : cls === 'neither' ? tok('--text-2')
        : tok('--text-3');
    }
    const grp = kind === 'ds' ? DS : P;
    if (cls === 'inside') return grp;
    if (cls === 'outside') return which === 'src' ? tok('--warn') : tok('--text-3');
    return tok('--text-3');
  }

  const CLASS_WORDS = {
    inside: 'inside the border', outside: 'outside the border',
    ds: 'inside the DS border only', pspike: 'inside the P-spike border only',
    both: 'inside both borders', neither: 'outside both borders',
    null: 'not measured',
  };

  /* What a stage shows: which events, and whether each is drawn. */
  function stageSet(run, kind, stage) {
    if (stage === 'define' && kind !== 'ambiguous') {
      return { which: 'src', pts: pointsOf(run.src_cols), keep: () => true };
    }
    const pts = pointsOf(run.cols);
    if (stage === 'extract') {
      const keep = kind === 'ambiguous'
        ? (p) => p.cls === 'both' || p.cls === 'neither'
        : (p) => p.cls === 'inside';
      return { which: 'tgt', pts, keep };
    }
    return { which: 'tgt', pts, keep: () => true };
  }

  /* ==================================================================
     Canvases
     ================================================================== */
  function sized(cv, h) {
    if (!cv || !cv.isConnected) return null;
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(60, cv.clientWidth || cv.parentNode.clientWidth || 300);
    const hh = h || cv.clientHeight || 200;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(hh * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(hh * dpr);
    }
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, hh);
    return { g, w, h: hh };
  }

  const FONT = (px) => px + 'px ' + (tok('--font-ui', 'system-ui') || 'system-ui');

  /* The 3D view: amplitude across, HF up, half-width into the screen. */
  function project(u, view, s, cx, cy) {
    const cyw = Math.cos(view.yaw), syw = Math.sin(view.yaw);
    const cp = Math.cos(view.pitch), sp = Math.sin(view.pitch);
    const x = u[0] * cyw - u[2] * syw;
    const z = u[0] * syw + u[2] * cyw;
    const y = u[1] * cp - z * sp;
    const d = u[1] * sp + z * cp;
    return [cx + x * s, cy - y * s, d];
  }

  function norm(v, r) {
    return ((v - r[0]) / (r[1] - r[0])) * 2 - 1;
  }

  function draw3d(cv, run, kind, stage, opt) {
    const o = opt || {};
    const s0 = sized(cv, o.h || 380);
    if (!s0) return;
    const { g, w, h } = s0;
    const view = o.view || W.view;
    const R = o.ranges || rangesOf(run);
    const scale = Math.min(w, h) * 0.34 * (view.zoom || 1);
    const cx = w / 2, cy = h / 2 + (o.small ? 4 : 10);
    const P = (a, b, c) => project([a, b, c], view, scale, cx, cy);
    // The cube.
    g.strokeStyle = tok('--line');
    g.lineWidth = 1;
    const C = [-1, 1];
    for (const a of C) for (const b of C) {
      line(g, P(-1, a, b), P(1, a, b));
      line(g, P(a, -1, b), P(a, 1, b));
      line(g, P(a, b, -1), P(a, b, 1));
    }
    if (!o.small) {
      g.fillStyle = tok('--text-2');
      g.font = FONT(10);
      g.textAlign = 'center';
      const lab = (pt, t) => g.fillText(t, pt[0], pt[1]);
      lab(P(0, -1.18, 1), 'amplitude (µV)  ' + fmt(R.amp[0], 0) + ' – ' + fmt(R.amp[1], 0));
      lab(P(-1.12, 0, 1), 'HF (dB)');
      lab(P(-1, -1.18, 0), 'half-width (ms)');
    }
    // The boxes.
    for (const b of boxesOf(run, kind)) {
      drawBox(g, b, R, P);
    }
    // The dots: the context first, the stage's own on top, far ones first.
    const set = stageSet(run, kind, stage);
    const shown = [];
    for (const p of set.pts) {
      if (!measured(p)) continue;
      const q = P(norm(p.amp, R.amp), norm(p.hf, R.hf), norm(p.hw, R.hw));
      shown.push({ p, q, keep: set.keep(p) });
    }
    shown.sort((a, b) => (a.keep - b.keep) || (b.q[2] - a.q[2]));
    const r = o.small ? 1.2 : 2.3;
    const pick = W.picked && W.picked.which === set.which ? W.picked.n : null;
    for (const x of shown) {
      g.globalAlpha = x.keep ? 0.9 : 0.14;
      g.fillStyle = colourOf(kind, x.p.cls, set.which);
      g.beginPath();
      g.arc(x.q[0], x.q[1], r, 0, 6.2832);
      g.fill();
    }
    g.globalAlpha = 1;
    if (pick != null) {
      const x = shown.find((z) => z.p.n === pick);
      if (x) {
        g.strokeStyle = tok('--text');
        g.lineWidth = 2;
        g.beginPath();
        g.arc(x.q[0], x.q[1], r + 4, 0, 6.2832);
        g.stroke();
      }
    }
    cv.__pick = { which: set.which, pts: shown.filter((x) => x.keep) };
  }

  function line(g, a, b, dash) {
    g.setLineDash(dash || []);
    g.beginPath();
    g.moveTo(a[0], a[1]);
    g.lineTo(b[0], b[1]);
    g.stroke();
    g.setLineDash([]);
  }

  function drawBox(g, b, R, P) {
    const lo = [norm(b.lo.amp, R.amp), norm(b.lo.hf, R.hf), norm(b.lo.hw, R.hw)];
    const hi = [norm(b.hi.amp, R.amp), norm(b.hi.hf, R.hf), norm(b.hi.hw, R.hw)];
    if (lo.concat(hi).some((v) => !isFinite(v))) return;
    const c = (i, j, k) => P(i ? hi[0] : lo[0], j ? hi[1] : lo[1], k ? hi[2] : lo[2]);
    g.strokeStyle = b.colour;
    g.lineWidth = b.dashed ? 1 : 1.8;
    const dash = b.dashed ? [4, 4] : [];
    for (const a of [0, 1]) for (const d of [0, 1]) {
      line(g, c(0, a, d), c(1, a, d), dash);
      line(g, c(a, 0, d), c(a, 1, d), dash);
      line(g, c(a, d, 0), c(a, d, 1), dash);
    }
  }

  /* A 2D view of two axes, with the boxes' edges on it. */
  function draw2d(cv, run, kind, stage, xa, ya, opt) {
    const o = opt || {};
    const s0 = sized(cv, o.h || 170);
    if (!s0) return;
    const { g, w, h } = s0;
    const R = o.ranges || rangesOf(run);
    const L = o.small ? 4 : 34, B = o.small ? 4 : 26, T = 6, Rr = 6;
    const X = (v) => L + ((v - R[xa][0]) / (R[xa][1] - R[xa][0])) * (w - L - Rr);
    const Y = (v) => h - B - ((v - R[ya][0]) / (R[ya][1] - R[ya][0])) * (h - B - T);
    g.strokeStyle = tok('--line');
    g.strokeRect(L, T, w - L - Rr, h - B - T);
    if (!o.small) {
      g.fillStyle = tok('--text-2');
      g.font = FONT(10);
      g.textAlign = 'center';
      const wx = AX.find((a) => a[0] === xa), wy = AX.find((a) => a[0] === ya);
      g.fillText(wx[2] + ' (' + wx[3] + ')', (L + w) / 2, h - 6);
      g.save();
      g.translate(11, (T + h - B) / 2);
      g.rotate(-Math.PI / 2);
      g.fillText(wy[2] + ' (' + wy[3] + ')', 0, 0);
      g.restore();
    }
    const set = stageSet(run, kind, stage);
    const pts = (o.only ? set.pts.filter(o.only) : set.pts).filter(measured);
    const r = o.small ? 1 : 1.8;
    for (const keepPass of [false, true]) {
      for (const p of pts) {
        const k = set.keep(p);
        if (k !== keepPass) continue;
        g.globalAlpha = k ? 0.85 : 0.12;
        g.fillStyle = colourOf(kind, p.cls, set.which);
        g.fillRect(X(p[xa]) - r, Y(p[ya]) - r, 2 * r, 2 * r);
      }
    }
    g.globalAlpha = 1;
    for (const b of boxesOf(run, kind)) {
      const x0 = X(b.lo[xa]), x1 = X(b.hi[xa]), y0 = Y(b.hi[ya]), y1 = Y(b.lo[ya]);
      if (![x0, x1, y0, y1].every(isFinite)) continue;
      g.strokeStyle = b.colour;
      g.lineWidth = b.dashed ? 1 : 1.6;
      g.setLineDash(b.dashed ? [4, 4] : []);
      g.strokeRect(x0, y0, x1 - x0, y1 - y0);
      g.setLineDash([]);
    }
    if (!o.small) cv.__pick = { which: set.which, pts: pts.filter((p) => set.keep(p))
      .map((p) => ({ p, q: [X(p[xa]), Y(p[ya])] })) };
  }

  /* How far every event is from the box on one axis, in box widths:
     below 0 inside, above 0 outside, the edge at 0. */
  function drawDist(cv, run, kind, axisIx, which) {
    const s0 = sized(cv, 120);
    if (!s0) return;
    const { g, w, h } = s0;
    const key = which === 'b' ? 'db' : 'da';
    const pts = pointsOf(run.cols).filter((p) => p[key] && finite(p[key][axisIx]));
    const lo = -1, hi = 1.5, nb = 50;
    const bins = new Array(nb).fill(0);
    for (const p of pts) {
      const v = Math.max(lo, Math.min(hi - 1e-9, p[key][axisIx]));
      bins[Math.floor(((v - lo) / (hi - lo)) * nb)] += 1;
    }
    const top = Math.max(1, ...bins);
    const L = 6, B = 22, T = 14;
    const X = (v) => L + ((v - lo) / (hi - lo)) * (w - 2 * L);
    const col = which === 'b' ? tok('--call-p') : kind === 'pspike' ? tok('--call-p')
      : tok('--call-ds');
    for (let b = 0; b < nb; b++) {
      const x0 = X(lo + (b / nb) * (hi - lo)), x1 = X(lo + ((b + 1) / nb) * (hi - lo));
      const hh = (bins[b] / top) * (h - B - T);
      const mid = lo + ((b + 0.5) / nb) * (hi - lo);
      g.fillStyle = mid <= 0 ? col : tok('--text-3');
      g.fillRect(x0 + 0.5, h - B - hh, Math.max(1, x1 - x0 - 1), hh);
    }
    g.strokeStyle = tok('--text');
    line(g, [X(0), T - 4], [X(0), h - B + 3], [3, 3]);
    g.fillStyle = tok('--text-2');
    g.font = FONT(10);
    g.textAlign = 'center';
    g.fillText('edge', X(0), T - 5 < 8 ? 9 : T - 5);
    g.fillText('← inside      ' + AX[axisIx][2] + '      outside →', w / 2, h - 6);
  }

  /* The grace sweep: how many of the target land inside, and how much of
     the source's own the box leaves out, at every grace. */
  function drawSweep(cv, run, kind) {
    const s0 = sized(cv, 170);
    if (!s0) return;
    const { g, w, h } = s0;
    const sw = run.sweep || [];
    if (!sw.length) return;
    const L = 40, Rr = 40, T = 10, B = 26;
    const gx = (v) => L + (v / 0.1) * (w - L - Rr);
    const nmax = Math.max(1, ...sw.map((s) => s.target_inside));
    const omax = Math.max(0.1, ...sw.map((s) => s.source_outside));
    const Y1 = (v) => h - B - (v / nmax) * (h - B - T);
    const Y2 = (v) => h - B - (v / omax) * (h - B - T);
    g.strokeStyle = tok('--line');
    g.strokeRect(L, T, w - L - Rr, h - B - T);
    const grp = kind === 'ds' ? tok('--call-ds') : tok('--call-p');
    const path = (ys, colour) => {
      g.strokeStyle = colour;
      g.lineWidth = 2;
      g.beginPath();
      sw.forEach((s, k) => { const x = gx(s.grace), y = ys(s);
                             if (k) g.lineTo(x, y); else g.moveTo(x, y); });
      g.stroke();
    };
    path((s) => Y1(s.target_inside), grp);
    path((s) => Y2(s.source_outside), tok('--warn'));
    g.strokeStyle = tok('--text');
    line(g, [gx(run.grace), T], [gx(run.grace), h - B], [3, 3]);
    g.fillStyle = tok('--text-2');
    g.font = FONT(10);
    g.textAlign = 'center';
    for (const t of [0, 0.02, 0.04, 0.06, 0.08, 0.1]) {
      g.fillText(+(t * 100).toFixed(0) + '%', gx(t), h - B + 13);
    }
    g.fillText('grace', (L + w - Rr) / 2, h - 3);
    g.textAlign = 'right';
    g.fillStyle = grp;
    g.fillText(String(nmax), L - 4, T + 8);
    g.textAlign = 'left';
    g.fillStyle = tok('--warn');
    g.fillText(pct(omax), w - Rr + 4, T + 8);
  }

  /* From mice to classes: a band per mouse and class, as wide as how many
     of its events went that way. */
  function drawFlow(cv, run, kind) {
    const rows = run.by_mouse || [];
    const s0 = sized(cv, Math.max(160, 22 * rows.length + 30));
    if (!s0) return;
    const { g, w, h } = s0;
    const classes = kind === 'ambiguous' ? ['ds', 'pspike', 'both', 'neither']
                                         : ['inside', 'outside'];
    const total = rows.reduce((a, r) => a + (r.n || 0), 0) || 1;
    const T = 10, B = 10, gap = 4;
    const span = h - T - B;
    const lx0 = 110, lx1 = 122, rx0 = w - 150, rx1 = w - 138;
    const usable = (n, k) => span - gap * (k - 1);
    let y = T;
    const left = rows.map((r) => {
      const hh = (r.n / total) * usable(total, rows.length);
      const o = { r, y0: y, y1: y + hh, at: y };
      y += hh + gap;
      return o;
    });
    const ctot = {};
    for (const c of classes) ctot[c] = rows.reduce((a, r) => a + (r[c] || 0), 0);
    y = T;
    const right = {};
    for (const c of classes) {
      const hh = (ctot[c] / total) * usable(total, classes.length);
      right[c] = { y0: y, y1: y + hh, at: y };
      y += hh + gap;
    }
    const scale = usable(total, rows.length) / total;
    const rscale = usable(total, classes.length) / total;
    for (const L of left) {
      for (const c of classes) {
        const n = L.r[c] || 0;
        if (!n) continue;
        const a0 = L.at, a1 = L.at + n * scale;
        const b0 = right[c].at, b1 = right[c].at + n * rscale;
        L.at = a1;
        right[c].at = b1;
        g.globalAlpha = 0.32;
        g.fillStyle = colourOf(kind, c, 'tgt');
        g.beginPath();
        g.moveTo(lx1, a0);
        g.bezierCurveTo((lx1 + rx0) / 2, a0, (lx1 + rx0) / 2, b0, rx0, b0);
        g.lineTo(rx0, b1);
        g.bezierCurveTo((lx1 + rx0) / 2, b1, (lx1 + rx0) / 2, a1, lx1, a1);
        g.closePath();
        g.fill();
      }
    }
    g.globalAlpha = 1;
    g.font = FONT(10);
    for (const L of left) {
      g.fillStyle = tok('--text-2');
      g.fillRect(lx0, L.y0, lx1 - lx0, Math.max(1, L.y1 - L.y0));
      g.textAlign = 'right';
      g.fillStyle = tok('--text');
      g.fillText(String(L.r.key).replace(/^[^|]*\|/, '') + ' · ' + L.r.n,
                 lx0 - 4, (L.y0 + L.y1) / 2 + 3);
    }
    for (const c of classes) {
      const R = right[c];
      g.fillStyle = colourOf(kind, c, 'tgt');
      g.fillRect(rx0, R.y0, rx1 - rx0, Math.max(1, R.y1 - R.y0));
      g.textAlign = 'left';
      g.fillStyle = tok('--text');
      g.fillText(shortClass(c) + ' · ' + ctot[c], rx1 + 4, (R.y0 + R.y1) / 2 + 3);
    }
  }

  const shortClass = (c) => ({ inside: 'inside', outside: 'outside',
    ds: 'DS only', pspike: 'P-spike only', both: 'both', neither: 'neither' })[c] || c;

  /* An event's waveform, as the server measured it. */
  function drawTrace(cv, tr) {
    const s0 = sized(cv, 150);
    if (!s0 || !tr) return;
    const { g, w, h } = s0;
    const xs = tr.t_ms || [], ys = tr.y || [];
    const fy = ys.filter(finite);
    if (!fy.length) return;
    const L = 40, B = 22, T = 8, Rr = 8;
    const x0 = xs[0], x1 = xs[xs.length - 1];
    let lo = Math.min(...fy), hi = Math.max(...fy);
    if (hi <= lo) hi = lo + 1;
    const X = (v) => L + ((v - x0) / (x1 - x0)) * (w - L - Rr);
    const Y = (v) => h - B - ((v - lo) / (hi - lo)) * (h - B - T);
    g.strokeStyle = tok('--line');
    g.strokeRect(L, T, w - L - Rr, h - B - T);
    g.strokeStyle = tok('--text');
    g.lineWidth = 1.4;
    g.beginPath();
    let on = false;
    xs.forEach((x, k) => {
      if (!finite(ys[k])) { on = false; return; }
      if (on) g.lineTo(X(x), Y(ys[k])); else g.moveTo(X(x), Y(ys[k]));
      on = true;
    });
    g.stroke();
    g.strokeStyle = tok('--accent');
    if (finite(tr.peak_ms)) line(g, [X(tr.peak_ms), T], [X(tr.peak_ms), h - B], [3, 3]);
    if (finite(tr.half_uV) && finite(tr.left_ms) && finite(tr.right_ms)) {
      line(g, [X(tr.left_ms), Y(tr.half_uV)], [X(tr.right_ms), Y(tr.half_uV)]);
    }
    g.fillStyle = tok('--text-2');
    g.font = FONT(10);
    g.textAlign = 'center';
    g.fillText('ms from the stamp', (L + w) / 2, h - 5);
    g.textAlign = 'right';
    g.fillText(fmt(hi, 0) + ' µV', L - 3, T + 9);
    g.fillText(fmt(lo, 0), L - 3, h - B);
  }

  function drawCsd(cv, c) {
    const s0 = sized(cv, 150);
    if (!s0 || !c || !(c.rows || []).length) return;
    const { g, w, h } = s0;
    const rows = c.rows, n = rows.length, m = rows[0].length;
    const lim = (c.clim && c.clim[1]) || 1;
    const L = 40, B = 22, T = 8, Rr = 8;
    const cw = (w - L - Rr) / m, rh = (h - B - T) / n;
    const pos = rgb(tok('--call-p')), neg = rgb(tok('--call-ds'));
    for (let r = 0; r < n; r++) {
      for (let k = 0; k < m; k++) {
        const v = Math.max(-1, Math.min(1, rows[r][k] / lim));
        const col = v >= 0 ? pos : neg;
        g.fillStyle = 'rgba(' + col.join(',') + ',' + Math.abs(v).toFixed(3) + ')';
        g.fillRect(L + k * cw, T + r * rh, cw + 0.5, rh + 0.5);
      }
    }
    g.strokeStyle = tok('--line');
    g.strokeRect(L, T, w - L - Rr, h - B - T);
    g.fillStyle = tok('--text-2');
    g.font = FONT(10);
    g.textAlign = 'center';
    g.fillText('CSD down the column (sink and source)', (L + w) / 2, h - 5);
    g.textAlign = 'right';
    g.fillText('CSC' + c.nums[0], L - 3, T + 9);
    g.fillText('CSC' + c.nums[n - 1], L - 3, h - B);
  }

  function rgb(css) {
    const g = document.createElement('canvas').getContext('2d');
    g.fillStyle = css;
    const v = g.fillStyle;
    if (/^#/.test(v)) {
      const x = parseInt(v.slice(1), 16);
      return [(x >> 16) & 255, (x >> 8) & 255, x & 255];
    }
    const m = v.match(/\d+/g) || [128, 128, 128];
    return m.slice(0, 3).map(Number);
  }

  /* ==================================================================
     Picking a dot
     ================================================================== */
  function pickAt(cv, x, y) {
    const pk = cv.__pick;
    if (!pk) return;
    let best = null, bd = 9 * 9;
    for (const z of pk.pts) {
      const dx = z.q[0] - x, dy = z.q[1] - y;
      const d = dx * dx + dy * dy;
      if (d < bd) { bd = d; best = z; }
    }
    if (!best) return;
    W.picked = { which: pk.which, n: best.p.n };
    W.ev = null;
    W.avg = null;
    refresh();
  }

  /* Turned by dragging, on the canvas's own pointer: nothing is left
     listening on the window when the canvas is rebuilt. */
  function wire3d(cv, run, kind, stage) {
    let drag = null;
    cv.addEventListener('pointerdown', (e) => {
      drag = { x: e.clientX, y: e.clientY, yaw: W.view.yaw, pitch: W.view.pitch,
               moved: false };
      try { cv.setPointerCapture(e.pointerId); } catch (err) { /* fine */ }
    });
    cv.addEventListener('pointermove', (e) => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
      W.view.yaw = drag.yaw + dx * 0.008;
      W.view.pitch = Math.max(-1.45, Math.min(1.45, drag.pitch + dy * 0.008));
      draw3d(cv, run, kind, stage);
    });
    cv.addEventListener('pointerup', (e) => {
      if (!drag) return;
      const was = drag;
      drag = null;
      if (!was.moved) {
        const b = cv.getBoundingClientRect();
        pickAt(cv, e.clientX - b.left, e.clientY - b.top);
      }
    });
    cv.addEventListener('wheel', (e) => {
      e.preventDefault();
      W.view.zoom = Math.max(0.4, Math.min(4, W.view.zoom * (e.deltaY < 0 ? 1.1 : 0.9)));
      draw3d(cv, run, kind, stage);
    }, { passive: false });
  }

  function wire2d(cv) {
    cv.addEventListener('click', (e) => {
      const b = cv.getBoundingClientRect();
      pickAt(cv, e.clientX - b.left, e.clientY - b.top);
    });
  }

  /* ==================================================================
     The page
     ================================================================== */
  function node(helpers) {
    H = helpers || H;
    if (W.list === null && !W.loading) loadList();
    root = build();
    return root;
  }

  /* Only this tab's part of the page is rebuilt: the rest of Root Canal,
     and the ToolKit's feed, are left as they are. */
  function refresh() {
    if (root && root.isConnected) {
      const fresh = build();
      root.replaceWith(fresh);
      root = fresh;
      drawSoon();
    } else if (H && H.render) {
      H.render();
    }
  }

  let drawQueue = [];
  function drawAll() {
    const q = drawQueue;
    drawQueue = [];
    for (const f of q) { try { f(); } catch (e) { /* a canvas that left */ } }
  }
  const later = (f) => { drawQueue.push(f); };
  /* On the next frame, or a timer if no frame comes: a background tab, or
     the harness's virtual clock, can hold frames back as long as it likes. */
  function drawSoon() {
    requestAnimationFrame(drawAll);
    setTimeout(drawAll, 40);
  }

  /* A part that cannot be drawn says so, rather than leaving the last one
     on show as though nothing had happened. */
  function build() {
    try {
      return build_();
    } catch (e) {
      try { reportClientError('rootcanal.workflow.build', e.message, String(e && e.stack)); }
      catch (err) { /* not important */ }
      return el('div', { class: 'card wf-err-card' }, [
        el('p', { class: 'hint wf-err', text: 'The Workflow tab could not be drawn: '
          + e.message }),
      ]);
    }
  }

  function build_() {
    drawQueue = [];
    const box = el('div', { class: 'wf' }, [
      head(),
      W.builder ? builderCard() : null,
      W.listErr ? el('p', { class: 'hint wf-err', text: 'The workflows could not '
        + 'be listed: ' + W.listErr }) : null,
      W.list === null ? el('div', { class: 'card' }, [loader('Reading the workflows')])
                      : listCards(),
      W.preview || W.openId ? detail() : null,
    ].filter(Boolean));
    drawSoon();
    return box;
  }

  function head() {
    const arch = archived();
    const nArch = (W.list || []).filter((r) => arch[r.artifact_id]).length;
    return el('div', { class: 'card wf-head' }, [
      el('div', { class: 'wf-head-row' }, [
        el('strong', { text: 'Workflows' }),
        el('span', { class: 'hint', text: 'Define a border, apply it to a pool, '
          + 'extract what is inside. Every run is a version, pinned to the '
          + 'versions it read; what it extracts goes to the Bank as one entry.' }),
      ]),
      el('div', { class: 'wf-head-row' }, [
        BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'New workflow',
          extra: 'wf-new', onclick: () => openBuilder(null) }),
        nArch ? BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: (W.showArchived ? 'Hide' : 'Show') + ' archived · ' + nArch,
          extra: 'wf-show-arch',
          onclick: () => { W.showArchived = !W.showArchived; refresh(); } }) : null,
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Refresh',
          onclick: () => { W.list = null; W.sources = null; loadList(); } }),
      ].filter(Boolean)),
    ]);
  }

  /* ---------- the list: a strip per workflow ---------- */
  function listCards() {
    const arch = archived();
    const rows = (W.list || []).filter((r) => W.showArchived || !arch[r.artifact_id]);
    if (!rows.length) {
      return el('div', { class: 'card wf-empty' }, [
        el('p', { text: 'No workflows yet. Press New workflow: Verified dentate '
          + 'spikes first (its border is drawn around the controls), then '
          + 'Verified P-spikes (around the hand-sorted ones), then Ambiguous, '
          + 'which borrows both borders.' }),
      ]);
    }
    rows.sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind)
              || String(a.nickname).localeCompare(String(b.nickname)));
    return el('div', { class: 'wf-list' }, rows.map((r) => strip(r, !!arch[r.artifact_id])));
  }

  function strip(r, isArch) {
    const d = W.data[r.artifact_id];
    const run = d && d.payload && d.payload.run;
    const open = W.openId === r.artifact_id && !W.preview;
    const kind = r.kind;
    const stale = r.stale || [];
    return el('div', { class: 'card wf-strip' + (open ? ' on' : '')
                       + (isArch ? ' archived' : ''),
                       'data-wf': r.artifact_id }, [
      el('div', { class: 'wf-strip-head' }, [
        el('span', { class: 'wf-kind wf-kind-' + kind, text: KIND_WORDS[kind] || kind }),
        el('strong', { class: 'wf-name', text: r.nickname || r.name }),
        BARRY.ui.chip('v' + r.version),
        r.sync && BARRY.ui.syncChip ? BARRY.ui.syncChip(r.sync) : null,
        isArch ? BARRY.ui.chip('archived', { kind: 'warn' }) : null,
        r.ran ? null : BARRY.ui.chip('not run yet'),
        stale.length ? BARRY.ui.chip('out of date', { kind: 'warn',
          title: stale.map((s) => s.what + ' ‘' + s.nickname + '’: pinned at '
                 + s.pinned + ', newest ' + s.newest).join('\n') }) : null,
        (r.mismatch || []).length ? BARRY.ui.chip('measured differently',
          { kind: 'warn', title: r.mismatch.join('\n') }) : null,
      ].filter(Boolean)),
      el('div', { class: 'wf-stages' }, STAGES.map(([id, words]) =>
        stageCard(r, run, kind, id, words))),
      el('div', { class: 'wf-strip-foot' }, [
        BARRY.ui.button({ kind: open ? 'primary' : 'ghost', size: 'sm',
          text: open ? 'Open below' : 'Open', extra: 'wf-open',
          onclick: () => openWorkflow(r.artifact_id) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: r.ran ? 'Run again' : 'Run', extra: 'wf-run',
          title: 'Define, apply and extract with the inputs this workflow pins.'
                 + (kind === 'ambiguous' ? ' Nothing is banked: you choose.'
                    : ' What is inside goes to the Bank, as one entry.'),
          onclick: () => runWorkflow(r, false) }),
        stale.length ? BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: 'Run with the newest inputs', extra: 'wf-run-fresh',
          onclick: () => runWorkflow(r, true) }) : null,
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Edit',
          onclick: () => openBuilder(r) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: isArch ? 'Put back' : 'Archive', extra: 'wf-archive',
          title: 'Archived workflows leave the list for everyone, once it '
                 + 'syncs, and so do the bank entries they made. Nothing is '
                 + 'deleted; put it back from Show archived.',
          onclick: () => setArchived(r, !isArch) }),
        r.bank && r.bank.entry_id ? el('span', { class: 'hint',
          text: 'Banked: ' + (r.bank.n || 0).toLocaleString() + ' events in one '
                + 'entry (' + r.bank.entry_id + ').' }) : null,
      ].filter(Boolean)),
    ]);
  }

  function stageCard(r, run, kind, id, words) {
    const cv = el('canvas', { class: 'wf-thumb' });
    if (run) later(() => draw3d(cv, run, kind, id, { small: true, h: 92,
      view: { yaw: -0.65, pitch: 0.42, zoom: 1 } }));
    const def = (W.data[r.artifact_id] || {}).payload || {};
    const dd = def.definition || r.definition || {};
    let line1 = '', line2 = '';
    if (id === 'define') {
      if (kind === 'ambiguous') {
        line1 = 'Both borders';
        line2 = ['ds', 'pspike'].map((k) => ((dd.uses || {})[k] || {}).nickname)
          .filter(Boolean).join(' + ');
      } else {
        const src = dd.source || {};
        line1 = (kind === 'ds' ? 'Around DS · ' : 'Around P-spikes · ')
                + 'grace ' + graceWords(dd.grace);
        line2 = src.type === 'sets' ? (src.entries || []).length + ' hand-sorted sets'
                                    : (src.nickname || '') + (src.version ? ' v' + src.version : '');
      }
    } else if (id === 'apply') {
      const t = dd.target || (run && run.target) || {};
      line1 = 'To ' + (t.nickname || 'the target') + (t.version ? ' v' + t.version : '');
      line2 = run ? Object.entries(run.counts || {}).map(([c, n]) => shortClass(c)
        + ' ' + n).join(' · ') : 'not run yet';
    } else {
      line1 = kind === 'ambiguous' ? 'Shown, for you to choose' : 'To the Bank';
      line2 = run ? (run.kept || 0).toLocaleString() + ' of ' + (run.n || 0).toLocaleString()
        + (kind === 'ambiguous' ? ' ambiguous' : ' extracted') : '—';
    }
    return el('button', { class: 'wf-stage', type: 'button',
      title: 'Open this stage in 3D',
      onclick: () => { W.stage = id; openWorkflow(r.artifact_id); } }, [
      el('span', { class: 'wf-stage-n', text: words }),
      cv,
      el('span', { class: 'wf-stage-l', text: line1 }),
      el('span', { class: 'hint wf-stage-l', text: line2 }),
    ]);
  }

  async function openWorkflow(id) {
    W.preview = null;
    W.openId = id;
    W.picked = null; W.ev = null; W.avg = null;
    const d = W.data[id];
    refresh();
    if (!d) await loadOne(id, null);
    else refresh();
    const n = root && root.querySelector('.wf-detail');
    if (n && n.scrollIntoView) n.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  async function runWorkflow(r, fresh) {
    if (W.busy) return;
    W.busy = 'Running ‘' + (r.nickname || r.name) + '’';
    refresh();
    let got;
    try {
      got = await apiPost('/api/rootcanal/workflow/' + encodeURIComponent(r.artifact_id)
                          + '/run', { refresh: !!fresh });
    } catch (e) {
      W.busy = null;
      toast('It did not run: ' + e.message, 'err', 14000);
      refresh();
      return;
    }
    W.busy = null;
    const run = got.run || {};
    toast('‘' + (r.nickname || r.name) + '’ v' + got.version + ': '
          + (run.kept || 0).toLocaleString() + ' of ' + (run.n || 0).toLocaleString()
          + (r.kind === 'ambiguous' ? ' events are ambiguous. Nothing was banked.'
             : ' events inside the border' + (run.bank ? ', banked as one entry.' : '.'))
          + (run.diff && run.diff.n ? ' ' + run.diff.n + ' changed class since '
             + 'the last run.' : ''), 'ok', 10000);
    BARRY.activity.log('rootcanal.workflow_run', { artifact: r.artifact_id,
                                                   version: got.version });
    delete W.data[r.artifact_id];
    W.openId = r.artifact_id;
    W.list = null;
    await loadList();
    await loadOne(r.artifact_id, null);
  }

  /* ==================================================================
     The open workflow (or a preview)
     ================================================================== */
  function detail() {
    const run = shownRun();
    const def = shownDef() || {};
    const kind = def.kind;
    const d = W.openId && W.data[W.openId];
    const row = (W.list || []).find((r) => r.artifact_id === W.openId) || {};
    if (!run) {
      return el('div', { class: 'card wf-detail' }, [
        el('div', { class: 'wf-detail-head' }, [
          el('strong', { text: W.preview ? 'Preview' : (row.nickname || '') }),
          BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Close',
            onclick: () => { W.openId = null; W.preview = null; refresh(); } }),
        ]),
        d ? el('p', { class: 'hint', text: 'Defined, not run yet. Press Run on '
                      + 'its strip.' }) : loader('Opening the workflow'),
        d ? lineage(row, d) : null,
      ].filter(Boolean));
    }
    const shownV = d && (d.shown || d.version);
    const stages = STAGES.filter(([id]) => !(kind === 'ambiguous' && id === 'define'
                                            && false));
    const big = el('canvas', { class: 'wf-3d' });
    later(() => { draw3d(big, run, kind, W.stage); });
    wire3d(big, run, kind, W.stage);
    const R = rangesOf(run);
    const flats = [['amp', 'hf'], ['hf', 'hw'], ['amp', 'hw']].map(([xa, ya]) => {
      const cv = el('canvas', { class: 'wf-2d' });
      later(() => draw2d(cv, run, kind, W.stage, xa, ya, { ranges: R }));
      wire2d(cv);
      return cv;
    });
    return el('div', { class: 'card wf-detail' }, [
      el('div', { class: 'wf-detail-head' }, [
        el('span', { class: 'wf-kind wf-kind-' + kind, text: KIND_WORDS[kind] }),
        el('strong', { text: W.preview ? 'Preview · nothing saved'
                       : (row.nickname || '') + ' · v' + shownV }),
        W.busy ? BARRY.ui.chip(W.busy) : null,
        BARRY.ui.seg(stages.map(([id, w]) => [id, w,
          id === 'define' ? 'What the border is drawn from, and the box.'
          : id === 'apply' ? 'The target, every event by the border.'
          : 'What comes out.']), W.stage,
          (v) => { W.stage = v; W.picked = null; W.ev = null; refresh(); },
          { extra: 'wf-stage-seg' }),
        W.preview ? BARRY.ui.button({ kind: 'primary', size: 'sm',
          text: 'Save this workflow', onclick: () => saveBuilder() }) : null,
        H && H.openPool && !W.preview ? BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: 'Open in Pooled', extra: 'wf-to-pooled',
          title: 'The same picture in Pooled, with the border applied: its '
                 + 'click panel, averages, lasso and Xplorefinder.',
          onclick: () => toPooled(run, kind) }) : null,
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Close',
          onclick: () => { W.openId = null; W.preview = null; refresh(); } }),
      ].filter(Boolean)),
      el('p', { class: 'hint wf-rule', text: ruleWords(run, kind) }),
      (run.mismatch || []).length ? el('p', { class: 'hint wf-warn',
        text: 'Measured differently: ' + run.mismatch.join('; ') + '.' }) : null,
      d && (d.stale || []).length && !W.preview ? el('p', { class: 'hint wf-warn',
        text: 'Out of date: ' + d.stale.map((s) => s.what + ' ‘' + s.nickname
          + '’ is at ' + s.newest + ', this pins ' + s.pinned).join('; ')
          + '. Run with the newest inputs to make the next version from them.' })
        : null,
      legend(kind, W.stage),
      el('div', { class: 'wf-views' }, [
        el('div', { class: 'wf-3d-wrap' }, [big,
          el('span', { class: 'hint', text: 'Drag to turn, scroll to zoom, click '
                       + 'a dot to look at it.' })]),
        el('div', { class: 'wf-2d-col' }, flats),
      ]),
      inspector(run, kind),
      el('div', { class: 'wf-panels' }, [
        kind !== 'ambiguous' ? panel('Grace', 'How the box would change with '
          + 'the grace: the target events inside it (in the border’s colour) '
          + 'and the share of the border’s own events it leaves out (amber).',
          (() => { const cv = el('canvas', { class: 'wf-sweep' });
                   later(() => drawSweep(cv, run, kind)); return cv; })()) : null,
        panel('How far from the border', 'Every target event’s distance from '
          + 'the box on each axis, in box widths: left of the line inside, '
          + 'right of it outside.', distPanel(run, kind)),
        panel('Where they went', 'From each mouse to each class, as wide as '
          + 'how many of its events.', (() => {
            const cv = el('canvas', { class: 'wf-flow' });
            later(() => drawFlow(cv, run, kind)); return cv; })()),
        kind === 'ambiguous' ? panel('Conflicts', 'Events inside both borders '
          + 'are ambiguous (decided 2026-11-05) and drawn amber.',
          venn(run)) : null,
        panel('Every mouse', 'Each mouse’s target events on amplitude and HF, '
          + 'with how many came out.', perMouse(run, kind, R)),
        panel('Averages', 'The four pictures averaged over a class, from every '
          + 'recording whose read is on this machine.', averages(run, kind)),
      ].filter(Boolean)),
      kind === 'ambiguous' && W.stage !== 'define' ? ambTable(run) : null,
      d ? lineage(row, d) : null,
    ].filter(Boolean));
  }

  function ruleWords(run, kind) {
    if (kind === 'ambiguous') {
      const b = run.borders || {};
      return 'DS border from ‘' + (((b.ds || {}).workflow) || {}).nickname
        + '’ at grace ' + graceWords((b.ds || {}).grace) + ', P-spike border from ‘'
        + (((b.pspike || {}).workflow) || {}).nickname + '’ at grace '
        + graceWords((b.pspike || {}).grace) + '. Ambiguous: outside both, or '
        + 'inside both.';
    }
    return run.rule || '';
  }

  function legend(kind, stage) {
    const item = (colour, text) => el('span', { class: 'wf-lg' }, [
      el('i', { style: 'background:' + colour }), el('span', { text })]);
    const kids = [];
    if (kind === 'ambiguous') {
      kids.push(item(tok('--call-ds'), 'inside the DS border only'),
                item(tok('--call-p'), 'inside the P-spike border only'),
                item(tok('--warn'), 'inside both (ambiguous)'),
                item(tok('--text-2'), 'outside both (ambiguous)'));
    } else {
      const grp = kind === 'ds' ? tok('--call-ds') : tok('--call-p');
      const w = kind === 'ds' ? 'DS' : 'P-spike';
      kids.push(item(grp, stage === 'define' ? 'the border’s own ' + w
                           + ' events, inside it' : 'inside: verified ' + w));
      kids.push(item(stage === 'define' ? tok('--warn') : tok('--text-3'),
                     stage === 'define' ? 'left outside by the grace'
                                        : 'outside'));
    }
    kids.push(el('span', { class: 'hint', text: 'Solid box: the border at its '
      + 'grace. Dashed: at no grace.' }));
    if (stage === 'extract') kids.push(el('span', { class: 'hint',
      text: 'Faded: not extracted.' }));
    return el('div', { class: 'wf-legend' }, kids);
  }

  function panel(title, words, body) {
    return el('div', { class: 'wf-panel' }, [
      el('strong', { text: title }),
      el('span', { class: 'hint', text: words }),
      body,
    ]);
  }

  function distPanel(run, kind) {
    const out = [];
    for (const which of kind === 'ambiguous' ? ['a', 'b'] : ['a']) {
      if (kind === 'ambiguous') {
        out.push(el('span', { class: 'hint', text: which === 'a'
          ? 'From the DS border' : 'From the P-spike border' }));
      }
      for (let a = 0; a < 3; a++) {
        const cv = el('canvas', { class: 'wf-dist' });
        later(() => drawDist(cv, run, kind, a, which));
        out.push(cv);
      }
    }
    return el('div', { class: 'wf-dist-grid' }, out);
  }

  function venn(run) {
    const c = run.counts || {};
    const n = (k) => (c[k] || 0).toLocaleString();
    return el('div', { class: 'wf-venn' }, [
      el('div', { class: 'wf-venn-c ds' }, [el('span', { text: 'DS only' }),
                                            el('strong', { text: n('ds') })]),
      el('div', { class: 'wf-venn-c both' }, [el('span', { text: 'both' }),
                                              el('strong', { text: n('both') })]),
      el('div', { class: 'wf-venn-c p' }, [el('span', { text: 'P-spike only' }),
                                           el('strong', { text: n('pspike') })]),
      el('span', { class: 'hint', text: 'Outside both: ' + n('neither') + '.' }),
    ]);
  }

  function perMouse(run, kind, R) {
    const pts = pointsOf(run.cols);
    const mice = Array.from(new Set(pts.map((p) => p.mouse))).filter(Boolean)
      .sort((a, b) => (BARRY.ui.natCompare ? BARRY.ui.natCompare(a, b)
                       : String(a).localeCompare(String(b))));
    const rows = run.by_mouse || [];
    const cards = mice.map((mk) => {
      const cv = el('canvas', { class: 'wf-mouse-cv' });
      later(() => draw2d(cv, run, kind, 'apply', 'amp', 'hf',
                         { small: true, h: 80, ranges: R,
                           only: (p) => p.mouse === mk }));
      const r = rows.find((x) => x.key === mk) || {};
      const kept = kind === 'ambiguous' ? (r.both || 0) + (r.neither || 0)
                                        : (r.inside || 0);
      return el('div', { class: 'wf-mouse' }, [
        el('strong', { text: String(mk).replace(/^[^|]*\|/, '') }),
        cv,
        el('span', { class: 'hint', text: kept + ' of ' + (r.n || 0) + ' · '
          + pct((r.n ? kept / r.n : null)) }),
      ]);
    });
    return el('div', { class: 'wf-mice' }, cards);
  }

  /* ---------- the class averages ---------- */
  function averages(run, kind) {
    const classes = kind === 'ambiguous' ? ['ds', 'pspike', 'both', 'neither']
                                         : ['inside', 'outside'];
    const kids = [el('div', { class: 'wf-avg-btns' }, classes.map((c) =>
      BARRY.ui.button({ kind: 'mini', text: 'Average ' + shortClass(c),
        onclick: () => average(run, kind, c) })))];
    const A = W.avg;
    if (A) {
      kids.push(el('span', { class: 'hint', text: A.busy ? 'Averaging ' + A.label + '…'
        : A.err ? 'Not averaged: ' + A.err
        : A.label + ': ' + (A.data.n || '?') + ' events'
          + (A.data.n_away ? ', ' + A.data.n_away + ' read elsewhere and not '
             + 'counted' : '') + '.' }));
      if (A.data && A.data.trace) {
        const t = el('canvas', { class: 'wf-ev-cv' });
        const c = el('canvas', { class: 'wf-ev-cv' });
        later(() => { drawTrace(t, A.data.trace); drawCsd(c, A.data.csd); });
        kids.push(el('div', { class: 'wf-ev-pics' }, [t, c]));
      }
    }
    return el('div', {}, kids);
  }

  async function average(run, kind, cls) {
    const pts = pointsOf(run.cols).filter((p) => p.cls === cls);
    const mem = run.members || [];
    const events = pts.map((p) => [(mem[p.m] || {}).key, p.i])
      .filter((x) => x[0] != null && x[1] != null);
    if (!events.length) { toast('Nothing in that class to average.', null, 5000); return; }
    const label = shortClass(cls) + ' · ' + events.length + ' events';
    W.avg = { label, busy: true };
    refresh();
    const t = run.target || {};
    try {
      const data = await apiPost('/api/rootcanal/pool/group', {
        members: mem.map((m) => ({ key: m.key })),
        measure: run.measure || null, band: null, k: 2,
        saved: { artifact_id: t.artifact_id, version: t.version },
        events, label,
      });
      W.avg = { label, data };
    } catch (e) {
      W.avg = { label, err: e.message };
    }
    refresh();
  }

  /* ---------- the picked event ---------- */
  function pickedPoint(run) {
    if (!W.picked) return null;
    const col = W.picked.which === 'src' ? run.src_cols : run.cols;
    return pointsOf(col)[W.picked.n] || null;
  }

  function inspector(run, kind) {
    const p = pickedPoint(run);
    if (!p) {
      return el('div', { class: 'wf-insp wf-insp-empty' }, [el('span', {
        class: 'hint', text: 'Click a dot in any picture to see its three numbers '
          + 'against the cut-offs, where it came from, and its waveform.' })]);
    }
    const mem = (W.picked.which === 'src' ? run.src_members : run.members) || [];
    const m = mem[p.m] || {};
    const boxes = boxesOf(run, kind).filter((b) => !b.dashed);
    const dist = (W.picked.which === 'src' || kind !== 'ambiguous') ? [p.da]
                                                                   : [p.da, p.db];
    const rowsT = AX.map(([c, k, w, u], ai) => el('tr', {}, [
      el('th', { text: w }),
      el('td', { text: fmt(p[c], 1) + ' ' + u }),
      ...boxes.map((b, bi) => {
        const lo = b.lo[c], hi = b.hi[c];
        const inside = p[c] != null && p[c] >= lo && p[c] <= hi;
        const d = (dist[bi] || [])[ai];
        return el('td', { class: inside ? 'wf-in' : 'wf-out', text: fmt(lo, 1) + ' – '
          + fmt(hi, 1) + (inside ? ' · inside' : ' · outside')
          + (d != null ? ' (' + (d <= 0 ? (-d).toFixed(2) + ' box widths in'
                                         : d.toFixed(2) + ' box widths out') + ')' : '') });
      }),
    ]));
    const def = shownDef() || {};
    const d = W.openId && W.data[W.openId];
    const row = (W.list || []).find((r) => r.artifact_id === W.openId) || {};
    const hist = [];
    hist.push('Recording: ' + (m.session_label || p.gid || '?') + ', at '
              + fmt(p.t, 3) + ' s.');
    if (m.entry_id) {
      hist.push('Set: bank entry ' + m.entry_id + (m.from_version != null
        ? ', version ' + m.from_version : ', as it stood') + '. '
        + (W.picked.which === 'src' && def.kind === 'pspike'
          ? 'Hand-sorted, retimed and aligned before it was read.'
          : 'Found by Incisor, checked in Checkup and aligned in Braces before '
            + 'Root Canal read it.'));
    }
    const pl = W.picked.which === 'src' ? def.source : (run.target || def.target);
    if (pl && pl.nickname) hist.push((W.picked.which === 'src' ? 'Border drawn from '
      : 'Pooled in ') + '‘' + pl.nickname + '’' + (pl.version ? ' v' + pl.version : '') + '.');
    if (run.border_ref) hist.push('Border ‘' + run.border_ref.nickname + '’ v'
      + run.border_ref.version + ', at grace ' + graceWords(run.grace) + '.');
    if (!W.preview && row.nickname) hist.push('Classified by the workflow ‘'
      + row.nickname + '’ v' + (d && (d.shown || d.version)) + ': '
      + CLASS_WORDS[p.cls] + '.');
    if (run.bank && p.cls === 'inside') hist.push('Banked in entry '
      + run.bank.entry_id + '.');
    const E = W.ev;
    const kids = [
      el('div', { class: 'wf-insp-head' }, [
        el('strong', { text: (CLASS_WORDS[p.cls] || 'not measured') }),
        el('span', { class: 'swatch-dot', style: 'background:'
                     + colourOf(kind, p.cls, W.picked.which) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Show its waveform',
          extra: 'wf-ev-go', disabled: !m.event_body,
          title: m.event_body ? 'Its trace on the contact it was measured on, '
                 + 'and the CSD down the column.'
                 : 'Its read is not on this machine.',
          onclick: () => loadEvent(m, p) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Open in Xplorefinder',
          extra: 'wf-xplore', onclick: () => openX(p) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Close',
          onclick: () => { W.picked = null; W.ev = null; refresh(); } }),
      ]),
      el('table', { class: 'wf-cut' }, [
        el('tr', {}, [el('th', { text: '' }), el('th', { text: 'this event' }),
          ...boxes.map((b) => el('th', { text: b.label }))]),
        ...rowsT,
      ]),
      el('ul', { class: 'wf-hist' }, hist.map((t) => el('li', { text: t }))),
    ];
    if (E) {
      kids.push(el('span', { class: 'hint', text: E.busy ? 'Reading its traces…'
        : E.err ? 'No traces here: ' + E.err : (E.data.filter_label || '') }));
      if (E.data && E.data.trace) {
        const t = el('canvas', { class: 'wf-ev-cv' });
        const c = el('canvas', { class: 'wf-ev-cv' });
        later(() => { drawTrace(t, E.data.trace); drawCsd(c, E.data.csd); });
        kids.push(el('div', { class: 'wf-ev-pics' }, [t, c]));
      }
    }
    return el('div', { class: 'wf-insp' }, kids);
  }

  async function loadEvent(m, p) {
    if (!m.event_body) return;
    W.ev = { busy: true };
    refresh();
    try {
      const data = await apiPost('/api/rootcanal/event',
                                 Object.assign({}, m.event_body, { i: p.i }));
      W.ev = { data };
    } catch (e) {
      W.ev = { err: e.message };
    }
    refresh();
  }

  async function openX(p) {
    const path = H && H.recordingPath ? await H.recordingPath(p.gid) : null;
    if (!path) {
      toast('That event’s recording is not reachable from this machine, so '
            + 'the recording window cannot show it.', 'err', 9000);
      return;
    }
    const run = shownRun() || {};
    const ms = run.measure || {};
    const args = new URLSearchParams({
      csc: path,
      panes: JSON.stringify([{ panel: 'traces' }, { panel: 'csd' }]),
      t0: Math.max(0, p.t - 0.25).toFixed(4), span: '0.5',
      hp: String(ms.lo_hz != null ? ms.lo_hz : 5),
      lp: String(ms.hi_hz != null ? ms.hi_hz : 100),
      notch: ms.mains_out ? '60' : '0',
      chrome: 'notabs,noheads', role: 'rootcanal',
      theme: (BARRY.state && BARRY.state.theme) || 'dark',
    });
    const w = window.open(location.origin + '/?' + args.toString() + '#xplore',
                          'barry-rootcanal-traces',
                          'width=1180,height=900,menubar=no,toolbar=no');
    if (!w) toast('The recording window was blocked. Allow pop-ups for this '
                  + 'page, then press it again.', 'err', 9000);
    BARRY.activity.log('rootcanal.workflow_xplore', { gid: p.gid, t: p.t });
  }

  async function toPooled(run, kind) {
    const t = run.target || {};
    const b = kind === 'ambiguous' ? null : run.border_ref;
    if (W.stage === 'define' && kind === 'ds') {
      const s = (shownDef() || {}).source || {};
      return H.openPool({ artifact_id: s.artifact_id, version: s.version },
                        b ? { artifact_id: b.artifact_id, version: b.version,
                              grace: run.grace } : null);
    }
    if (W.stage === 'define' && kind === 'pspike') {
      toast('The hand-sorted sets are not a saved pool, so this stage has no '
            + 'Pooled picture; the target does.', null, 7000);
    }
    return H.openPool({ artifact_id: t.artifact_id, version: t.version },
                      b ? { artifact_id: b.artifact_id, version: b.version,
                            grace: run.grace } : null);
  }

  /* ---------- the ambiguous ones, to choose from ---------- */
  function ambTable(run) {
    const pts = pointsOf(run.cols).filter((p) => (W.ambShow === 'all'
      ? (p.cls === 'both' || p.cls === 'neither') : p.cls === W.ambShow));
    const mem = run.members || [];
    const picks = W.ambPick;
    const MAX = 400;
    const shown = pts.slice(0, MAX);
    return el('div', { class: 'card wf-amb' }, [
      el('div', { class: 'wf-amb-head' }, [
        el('strong', { text: 'Ambiguous events, to choose from' }),
        BARRY.ui.seg([['all', 'all'], ['neither', 'outside both'], ['both', 'inside both']],
                     W.ambShow, (v) => { W.ambShow = v; refresh(); }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Tick all shown',
          onclick: () => { shown.forEach((p) => picks.add(p.n)); refresh(); } }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Untick all',
          onclick: () => { picks.clear(); refresh(); } }),
        el('span', { class: 'hint', text: picks.size + ' ticked' }),
        BARRY.ui.seg([['ied', 'as P-spikes'], ['ds', 'as DS'], ['other', 'as ambiguous']],
                     W.ambType, (v) => { W.ambType = v; refresh(); }),
        BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'Bank the ticked',
          disabled: !picks.size || !!W.preview,
          title: W.preview ? 'Save and run the workflow first.' : null,
          onclick: () => bankPicked() }),
      ]),
      pts.length > MAX ? el('span', { class: 'hint', text: 'Showing the first '
        + MAX + ' of ' + pts.length + '; narrow it with the switch above.' }) : null,
      el('table', { class: 'wf-amb-tab' }, [
        el('tr', {}, ['', 'recording', 't · s', 'amp · µV', 'HF · dB', 'hw · ms', 'why']
          .map((t) => el('th', { text: t }))),
        ...shown.map((p) => el('tr', {
          class: W.picked && W.picked.which === 'tgt' && W.picked.n === p.n ? 'on' : '',
          onclick: (e) => {
            if (e.target && e.target.tagName === 'INPUT') return;
            W.picked = { which: 'tgt', n: p.n }; W.ev = null; refresh();
          } }, [
          el('td', {}, [el('input', { type: 'checkbox',
            checked: picks.has(p.n) ? 'checked' : null,
            onchange: (e) => { if (e.target.checked) picks.add(p.n);
                               else picks.delete(p.n);
                               refresh(); } })]),
          el('td', { text: (mem[p.m] || {}).session_label || p.gid || '?' }),
          el('td', { text: fmt(p.t, 3) }),
          el('td', { text: fmt(p.amp, 0) }),
          el('td', { text: fmt(p.hf, 1) }),
          el('td', { text: fmt(p.hw, 1) }),
          el('td', { text: CLASS_WORDS[p.cls] }),
        ])),
      ]),
    ].filter(Boolean));
  }

  async function bankPicked() {
    const id = W.openId;
    const d = W.data[id];
    if (!id || !d) return;
    const typeWord = { ied: 'P-spikes', ds: 'dentate spikes', other: 'ambiguous' }[W.ambType];
    const ok = await BARRY.ui.bankDialog({
      title: 'Bank ' + W.ambPick.size + ' picked events as ' + typeWord,
      name: 'Picked ' + typeWord + ' · ' + ((W.list || []).find((r) => r.artifact_id === id) || {}).nickname,
      onBank: async (o) => {
        const got = await apiPost('/api/rootcanal/workflow/' + encodeURIComponent(id)
                                  + '/bank', { version: d.shown || d.version,
                                               picks: Array.from(W.ambPick),
                                               type: W.ambType, name: o.name });
        toast(got.n + ' events banked as one entry (' + got.entry_id + ').',
              'ok', 8000);
        W.ambPick.clear();
      },
    });
    if (ok) refresh();
  }

  /* ---------- the lineage ---------- */
  function lineage(row, d) {
    const lines = (d.lines || []).slice().reverse();
    const shown = d.shown || d.version;
    return el('div', { class: 'wf-lineage' }, [
      el('strong', { text: 'Versions' }),
      el('span', { class: 'hint', text: 'Every definition and every run, newest '
        + 'first. A run pins the exact versions it read, and says what moved '
        + 'since the run before it.' }),
      el('div', { class: 'wf-lines' }, lines.map((ln) => el('div', {
        class: 'wf-line' + (ln.version === shown ? ' on' : '') }, [
        el('strong', { text: 'v' + ln.version }),
        el('span', { text: !ln.here ? 'on another machine, not synced here yet'
          : ln.ran ? 'run' + (ln.by ? ' by ' + ln.by : '') + (ln.at ? ', '
            + new Date(ln.at).toLocaleString() : '') : 'defined' }),
        ln.ran ? el('span', { class: 'hint', text: (ln.kept || 0).toLocaleString()
          + ' kept · grace ' + graceWords(ln.grace)
          + ' · ' + defWords(ln.definition) }) : el('span', { class: 'hint',
          text: defWords(ln.definition) }),
        ln.diff ? el('span', { class: 'hint wf-diff', text: ln.diff.n
          ? ln.diff.n + ' changed since the run before: ' + Object.entries(
            ln.diff.moves || {}).map(([k, n]) => k + ' ' + n).join(', ')
          : 'nothing changed since the run before' }) : null,
        ln.bank ? el('span', { class: 'hint', text: 'bank entry ' + ln.bank.entry_id }) : null,
        ln.border_ref ? el('span', { class: 'hint', text: 'border ‘'
          + ln.border_ref.nickname + '’ v' + ln.border_ref.version }) : null,
        ln.here && ln.ran && ln.version !== shown ? BARRY.ui.button({ kind: 'mini',
          text: 'Show this version', onclick: async () => {
            W.picked = null; await loadOne(row.artifact_id, ln.version); } }) : null,
        ln.here && ln.definition ? BARRY.ui.button({ kind: 'mini',
          text: 'Rebuild from here', title: 'Make this version’s definition the '
            + 'newest, with the same pinned inputs, and run it again.',
          onclick: () => rebuild(row, ln) }) : null,
      ].filter(Boolean)))),
      shownDiff(d),
    ]);
  }

  function defWords(dd) {
    if (!dd) return '';
    if (dd.kind === 'ambiguous') {
      return ['ds', 'pspike'].map((k) => ((dd.uses || {})[k] || {}))
        .map((u) => '‘' + u.nickname + '’ v' + u.version).join(' + ');
    }
    const s = dd.source || {};
    return (s.type === 'sets' ? (s.entries || []).length + ' hand-sorted sets'
            : '‘' + s.nickname + '’ v' + s.version) + ' → ‘'
           + ((dd.target || {}).nickname || '') + '’ v' + ((dd.target || {}).version || '');
  }

  function shownDiff(d) {
    const run = d.payload && d.payload.run;
    const df = run && run.diff;
    if (!df || !df.n) return null;
    return el('details', { class: 'wf-diff-box' }, [
      el('summary', { text: 'What changed class since the run before: '
                      + df.n + ' events' }),
      el('table', { class: 'wf-amb-tab' }, [
        el('tr', {}, ['recording', 't · s', 'was', 'now'].map((t) => el('th', { text: t }))),
        ...(df.examples || []).map((x) => {
          const m = (run.members || []).find((mm) => mm.gid === x.gid) || {};
          return el('tr', {}, [el('td', { text: m.session_label || x.gid }),
            el('td', { text: fmt(x.t, 3) }),
            el('td', { text: CLASS_WORDS[x.was] || x.was }),
            el('td', { text: CLASS_WORDS[x.now] || x.now })]);
        }),
      ]),
    ]);
  }

  async function rebuild(row, ln) {
    const dd = ln.definition || {};
    try {
      await apiPost('/api/rootcanal/workflow/save', Object.assign({}, dd, {
        artifact_id: row.artifact_id, nickname: row.nickname }));
    } catch (e) {
      toast('Not rebuilt: ' + e.message, 'err', 9000);
      return;
    }
    W.list = null;
    await loadList();
    const r = (W.list || []).find((x) => x.artifact_id === row.artifact_id);
    if (r) await runWorkflow(r, false);
  }

  /* ==================================================================
     Building one
     ================================================================== */
  async function openBuilder(row) {
    const src = await loadSources();
    const pools = src.pools || [];
    const byNick = (n) => (pools.find((p) => p.nickname === n) || {}).artifact_id;
    const dd = (row && ((W.data[row.artifact_id] || {}).payload || {}).definition)
               || (row && row.definition) || {};
    const kind = dd.kind || 'ds';
    W.builder = {
      artifact_id: row ? row.artifact_id : null,
      nickname: row ? row.nickname : '',
      kind,
      grace: dd.grace != null ? dd.grace : 0.05,
      custom: '',
      source: (dd.source || {}).artifact_id
        || byNick('PTEN CTL Baseline Full Incisor')
        || ((pools.find((p) => p.all_ds) || {}).artifact_id) || null,
      target: (dd.target || {}).artifact_id
        || byNick('PTEN ALL PTEN Baseline Full Incisor') || null,
      sets: new Set(((dd.source || {}).entries || []).map((e) => e.entry_id)
                    .concat(dd.source && dd.source.entries ? []
                            : (src.sets || []).filter((s) => s.hand_sorted)
                              .map((s) => s.entry_id))),
      uses: { ds: ((dd.uses || {}).ds || {}).artifact_id || null,
              pspike: ((dd.uses || {}).pspike || {}).artifact_id || null },
    };
    if (!W.builder.uses.ds) {
      const r = (W.list || []).find((x) => x.kind === 'ds' && x.ran);
      W.builder.uses.ds = r ? r.artifact_id : null;
    }
    if (!W.builder.uses.pspike) {
      const r = (W.list || []).find((x) => x.kind === 'pspike' && x.ran);
      W.builder.uses.pspike = r ? r.artifact_id : null;
    }
    W.prep = null;
    refresh();
  }

  function builderBody() {
    const B = W.builder;
    const body = { kind: B.kind, nickname: B.nickname };
    if (B.kind !== 'ambiguous') {
      const g = B.custom !== '' && isFinite(Number(B.custom))
        ? Number(B.custom) / 100 : B.grace;
      body.grace = g;
      body.target = { artifact_id: B.target };
      if (B.kind === 'ds') body.source = { artifact_id: B.source };
      else body.source = { entries: Array.from(B.sets).map((id) => ({ entry_id: id })) };
    } else {
      body.uses = { ds: { artifact_id: B.uses.ds }, pspike: { artifact_id: B.uses.pspike } };
    }
    return body;
  }

  function builderCard() {
    const B = W.builder;
    const S = W.sources || { pools: [], sets: [] };
    const poolOpts = (cur, onPick, filt) => el('select', { class: 'wf-sel',
      onchange: (e) => { onPick(e.target.value); refresh(); } },
      (S.pools || []).filter(filt || (() => true)).map((p) => el('option', {
        value: p.artifact_id, selected: p.artifact_id === cur ? 'selected' : null,
        text: p.nickname + ' · v' + p.version + ' · ' + (p.events || 0).toLocaleString()
              + ' events' + (p.all_ds ? ' · every event DS' : '') })));
    const wfOpts = (k) => el('select', { class: 'wf-sel',
      onchange: (e) => { B.uses[k] = e.target.value; refresh(); } },
      [el('option', { value: '', text: 'Pick one' })].concat(
        (W.list || []).filter((r) => r.kind === k).map((r) => el('option', {
          value: r.artifact_id, selected: r.artifact_id === B.uses[k] ? 'selected' : null,
          text: r.nickname + ' · v' + r.version + (r.ran ? '' : ' · not run yet') }))));
    const rows = [
      el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'Which' }),
        BARRY.ui.seg(KIND_ORDER.map((k) => [k, KIND_WORDS[k]]), B.kind,
                     (v) => { B.kind = v; W.prep = null; refresh(); }),
      ]),
      el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'Name' }),
        el('input', { type: 'text', class: 'wf-name-in', value: B.nickname,
          placeholder: 'e.g. ' + KIND_WORDS[B.kind] + ' · PTEN baseline',
          oninput: (e) => { B.nickname = e.target.value; } }),
      ]),
    ];
    if (B.kind === 'ds') {
      rows.push(el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'Border around DS, from' }),
        poolOpts(B.source, (v) => { B.source = v; }),
        el('span', { class: 'hint', text: 'Every event of this pool is taken as a '
          + 'dentate spike: the controls.' }),
      ]));
    }
    if (B.kind === 'pspike') {
      rows.push(el('div', { class: 'wf-b-row wf-b-col' }, [
        el('span', { class: 'wf-b-l', text: 'Border around P-spikes, from' }),
        el('div', { class: 'wf-sets' }, (S.sets || []).map((s) => el('label', {
          class: 'wf-set' }, [
          el('input', { type: 'checkbox', checked: B.sets.has(s.entry_id) ? 'checked' : null,
            onchange: (e) => { if (e.target.checked) B.sets.add(s.entry_id);
                               else B.sets.delete(s.entry_id); W.prep = null; refresh(); } }),
          el('span', { text: s.session_label + ' · ' + s.n + ' · ' + s.name }),
          s.aligned ? BARRY.ui.chip('aligned ' + s.aligned_name, { kind: 'ok' })
                    : BARRY.ui.chip('not aligned'),
        ]))),
        prepCard(),
      ]));
    }
    if (B.kind !== 'ambiguous') {
      rows.push(el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'Applied to' }),
        poolOpts(B.target, (v) => { B.target = v; W.prep = null; }),
      ]));
      rows.push(el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'Grace' }),
        BARRY.ui.seg(GRACES.map(([g, w]) => [String(g), w]),
                     B.custom !== '' ? '' : String(B.grace),
                     (v) => { B.grace = Number(v); B.custom = ''; refresh(); }),
        el('input', { type: 'number', class: 'wf-custom', min: '0', max: '50',
          step: '0.5', value: B.custom, placeholder: 'custom %',
          oninput: (e) => { B.custom = e.target.value; } }),
        el('span', { class: 'hint', text: 'The share of the border’s own events '
          + 'the box may leave out.' }),
      ]));
    } else {
      rows.push(el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'DS border from' }), wfOpts('ds')]));
      rows.push(el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'P-spike border from' }), wfOpts('pspike')]));
      rows.push(el('p', { class: 'hint', text: 'Applied to the DS workflow’s '
        + 'target. Outside both borders, or inside both, is ambiguous: shown, '
        + 'not banked, for you to choose from.' }));
    }
    rows.push(el('div', { class: 'wf-b-row' }, [
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Preview',
        extra: 'wf-preview', title: 'Everything a run would find, with nothing '
          + 'saved.', onclick: () => previewBuilder() }),
      BARRY.ui.button({ kind: 'primary', size: 'sm',
        text: B.artifact_id ? 'Save as the next version' : 'Save',
        extra: 'wf-save', onclick: () => saveBuilder() }),
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Cancel',
        onclick: () => { W.builder = null; W.preview = null; W.prep = null; refresh(); } }),
      W.busy ? BARRY.ui.chip(W.busy) : null,
    ].filter(Boolean)));
    return el('div', { class: 'card wf-builder' }, [
      el('strong', { text: B.artifact_id ? 'Edit ‘' + B.nickname + '’' : 'New workflow' }),
    ].concat(rows));
  }

  async function previewBuilder() {
    if (W.busy) return;
    W.busy = 'Previewing';
    refresh();
    try {
      const got = await apiPost('/api/rootcanal/workflow/preview', builderBody());
      W.preview = { definition: got.definition, run: got.run };
      W.openId = null;
      W.stage = 'apply';
      W.picked = null;
    } catch (e) {
      toast('No preview: ' + e.message, 'err', 14000);
    }
    W.busy = null;
    refresh();
  }

  async function saveBuilder() {
    const B = W.builder;
    if (!B) return;
    if (!String(B.nickname || '').trim()) {
      toast('Give it a name first.', 'warn', 6000);
      const n = root && root.querySelector('.wf-name-in');
      if (n) n.focus();
      return;
    }
    let got;
    try {
      got = await apiPost('/api/rootcanal/workflow/save',
                          Object.assign(builderBody(), { artifact_id: B.artifact_id }));
    } catch (e) {
      toast('Not saved: ' + e.message, 'err', 12000);
      return;
    }
    toast('Saved ‘' + got.nickname + '’ v' + got.version + '. Press Run on its '
          + 'strip to define, apply and extract.', 'ok', 8000);
    // Only this builder: another opened while the save was on its way stays.
    if (W.builder === B) {
      W.builder = null;
      W.prep = null;
    }
    W.preview = null;
    W.openId = got.artifact_id;
    W.list = null;
    await loadList();
    await loadOne(got.artifact_id, null);
  }

  /* ---------- the hand-sorted sets, made ready ---------- */
  function prepCard() {
    const P = W.prep;
    const kids = [
      el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'hint', text: 'Each set has to be on the recording’s '
          + 'own clock, aligned (Eye), and read here, measured the way the '
          + 'target was, before a border can be drawn around it.' }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Check the sets',
          extra: 'wf-prep-check', onclick: () => checkPrep() }),
        P && P.sets && P.sets.some((s) => s.clock && s.clock.retime || !s.aligned || !s.read)
          ? BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'Prepare all',
              extra: 'wf-prep-go', disabled: !!(P && P.running),
              title: 'Retime what needs it, align what is not aligned (Eye, '
                     + 'committed as it lands), then read each one here.',
              onclick: () => prepareAll() }) : null,
      ].filter(Boolean)),
    ];
    if (P && P.err) kids.push(el('p', { class: 'hint wf-err', text: P.err }));
    if (P && P.say) kids.push(el('p', { class: 'hint', text: P.say }));
    if (P && P.sets) {
      kids.push(el('table', { class: 'wf-prep' }, [
        el('tr', {}, ['set', 'clock', 'aligned', 'read here'].map((t) => el('th', { text: t }))),
        ...P.sets.map((s) => el('tr', {}, [
          el('td', { text: (s.session_label || s.entry_id) + ' · ' + (s.n || 0) }),
          el('td', { class: s.clock && s.clock.retime ? 'wf-out' : 'wf-in',
                     text: s.clock && s.clock.retime ? 'needs retiming'
                       : 'on the recording’s clock',
                     title: (s.clock || {}).why || '' }),
          el('td', { class: s.aligned ? 'wf-in' : 'wf-out',
                     text: s.aligned ? s.aligned_name : 'not yet' }),
          el('td', { class: s.read ? 'wf-in' : 'wf-out',
                     text: s.read ? 'yes' : 'not yet', title: s.read_why || '' }),
        ])),
      ]));
    }
    return el('div', { class: 'wf-prep-card' }, kids);
  }

  async function checkPrep() {
    const B = W.builder;
    W.prep = Object.assign({}, W.prep, { say: 'Checking the sets…', err: null });
    refresh();
    try {
      const got = await apiPost('/api/rootcanal/workflow/prepare', {
        entries: Array.from(B.sets), target: { artifact_id: B.target } });
      W.prep = { sets: got.sets || [], say: null };
    } catch (e) {
      W.prep = { err: e.message };
    }
    refresh();
  }

  async function waitJob(id, say) {
    for (let k = 0; k < 3600; k++) {
      let j;
      try { j = (await api('/api/cfc/job/' + encodeURIComponent(id))).job || {}; }
      catch (e) { return { status: 'error', error: e.message }; }
      if (j.status && j.status !== 'running' && j.status !== 'queued') return j;
      const st = (j.stages || [])[0] || {};
      if (say) { W.prep.say = say + (st.of ? ' — ' + (st.done || 0) + ' of ' + st.of : ''); refresh(); }
      await new Promise((r) => setTimeout(r, 1500));
    }
    return { status: 'error', error: 'it took too long' };
  }

  async function prepareAll() {
    const B = W.builder;
    if (!W.prep || !W.prep.sets) await checkPrep();
    if (!W.prep || !W.prep.sets) return;
    W.prep.running = true;
    const fails = [];
    // 1. Onto the recording's own clock.
    for (const s of W.prep.sets.filter((x) => x.clock && x.clock.retime)) {
      W.prep.say = 'Retiming ' + s.session_label + '…';
      refresh();
      try {
        await apiPost('/api/session/retime', { path: s.path, entry_id: s.entry_id,
                                               gid: s.gid, kind: 'ied', apply: true });
      } catch (e) { fails.push(s.session_label + ': retime — ' + e.message); }
    }
    await checkPrep();
    W.prep.running = true;
    // 2. Aligned, in Eye's way, and committed as each lands.
    const need = W.prep.sets.filter((x) => !x.aligned && !(x.clock && x.clock.retime));
    if (need.length) {
      W.prep.say = 'Aligning ' + need.length + ' set(s)…';
      refresh();
      try {
        const got = await apiPost('/api/braces/batch', {
          entries: need.map((s) => ({ id: s.entry_id })), tool: 'eye' });
        const j = await waitJob((got.job || {}).id, 'Aligning');
        for (const m of j.members || []) {
          if (!m.set_id) { if (m.error) fails.push(m.label + ': align — ' + m.error); continue; }
          try {
            await apiPost('/api/braces/set/' + encodeURIComponent(m.set_id) + '/commit',
                          { apply: true });
          } catch (e) { fails.push(m.label + ': commit — ' + e.message); }
        }
      } catch (e) { fails.push('align — ' + e.message); }
    }
    await checkPrep();
    W.prep.running = true;
    // 3. Read here.
    for (const s of W.prep.sets.filter((x) => x.aligned && !x.read)) {
      W.prep.say = 'Reading ' + s.session_label + '…';
      refresh();
      try {
        const got = await apiPost('/api/rootcanal/read', { entry_id: s.entry_id,
                                                           from_version: s.aligned_ref });
        if (got.job) {
          const j = await waitJob(got.job.id, 'Reading ' + s.session_label);
          if (j.status !== 'done') fails.push(s.session_label + ': read — '
                                              + (j.error || j.status));
        }
      } catch (e) { fails.push(s.session_label + ': read — ' + e.message); }
    }
    await checkPrep();
    W.prep.running = false;
    W.sources = null;
    await loadSources();
    W.prep.say = fails.length ? 'Not everything is ready: ' + fails.join('; ')
      : 'Every set is ready: on its clock, aligned and read here.';
    refresh();
  }

  function reset() {
    W.list = null; W.data = {}; W.openId = null; W.preview = null;
    W.builder = null; W.prep = null; W.sources = null; W.picked = null;
    W.ev = null; W.avg = null; W.ambPick = new Set();
  }

  return {
    node, reset,
    // For the harness.
    _state: () => W,
    _draw: () => drawAll(),
    _pointsOf: pointsOf,
    _rangesOf: rangesOf,
    _boxesOf: boxesOf,
  };
})();
