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
      W.data[id] = { version: (got.artifact || {}).version,
                     shown: version != null ? version : (got.shown || null),
                     newer: version != null ? null : (got.newer_definition || null),
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

  const FONT = (px, bold) => (bold ? '600 ' : '') + px + 'px '
    + (tok('--font-ui', 'system-ui') || 'system-ui');

  /* Ticks at round numbers, written the way Root Canal writes them. */
  function niceTicks(lo, hi, n) {
    const span = hi - lo;
    if (!(span > 0)) return [lo];
    const raw = span / Math.max(1, n || 4);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const st = [1, 2, 2.5, 5, 10].map((m) => m * mag)
      .find((s) => span / s <= (n || 4) + 0.5) || mag * 10;
    const out = [];
    for (let v = Math.ceil(lo / st) * st; v <= hi + st * 1e-9; v += st) {
      out.push(Math.abs(v) < st * 1e-9 ? 0 : v);
    }
    return out;
  }
  const tickText = (v) => {
    const a = Math.abs(v);
    if (a >= 1000) return (v / 1000).toFixed(a >= 10000 ? 0 : 1) + 'k';
    if (a >= 10 || a === 0) return String(Math.round(v));
    return String(Math.round(v * 10) / 10);
  };

  /* A plotting frame: the box, faint grid lines at the ticks, numbers on
     both axes, and the axis names. Returns the maps from values to pixels. */
  function axes2d(g, w, h, xr, yr, xl, yl, o) {
    const opt = o || {};
    const L = opt.L != null ? opt.L : 46, B = opt.B != null ? opt.B : 34;
    const T = opt.T != null ? opt.T : 8, R = opt.R != null ? opt.R : 10;
    const X = (v) => L + ((v - xr[0]) / (xr[1] - xr[0])) * (w - L - R);
    const Y = (v) => h - B - ((v - yr[0]) / (yr[1] - yr[0])) * (h - B - T);
    g.font = FONT(10);
    g.lineWidth = 1;
    for (const t of niceTicks(xr[0], xr[1], Math.max(2, Math.floor((w - L - R) / 70)))) {
      g.strokeStyle = tok('--line-soft', tok('--line'));
      g.beginPath(); g.moveTo(X(t), T); g.lineTo(X(t), h - B); g.stroke();
      g.fillStyle = tok('--text-3');
      g.textAlign = 'center';
      g.fillText((opt.xfmt || tickText)(t), X(t), h - B + 13);
    }
    if (!opt.noY) {
      for (const t of niceTicks(yr[0], yr[1], Math.max(2, Math.floor((h - B - T) / 34)))) {
        g.strokeStyle = tok('--line-soft', tok('--line'));
        g.beginPath(); g.moveTo(L, Y(t)); g.lineTo(w - R, Y(t)); g.stroke();
        g.fillStyle = tok('--text-3');
        g.textAlign = 'right';
        g.fillText((opt.yfmt || tickText)(t), L - 5, Y(t) + 3);
      }
    }
    g.strokeStyle = tok('--line');
    g.strokeRect(L, T, w - L - R, h - B - T);
    g.fillStyle = tok('--text-2');
    g.font = FONT(10.5);
    g.textAlign = 'center';
    if (xl) g.fillText(xl, (L + w - R) / 2, h - 6);
    if (yl) {
      g.save();
      g.translate(11, (T + h - B) / 2);
      g.rotate(-Math.PI / 2);
      g.fillText(yl, 0, 0);
      g.restore();
    }
    g.textAlign = 'left';
    return { X, Y, L, B, T, R };
  }

  /* The 3D view: amplitude across, HF up, half-width into the screen.

     THE FRAME IS THE AXES, NOT A BORDER (2026-11-05: "what is the other
     faint box?"). It spans what is on show, from the lowest value to the
     highest on each axis, and carries their tick values along its front
     edges; the borders are the coloured boxes inside it. */
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
    const s0 = sized(cv, o.h || 420);
    if (!s0) return;
    const { g, w, h } = s0;
    const view = o.view || W.view;
    const R = o.ranges || rangesOf(run);
    const scale = Math.min(w * 0.8, h) * (o.small ? 0.36 : 0.31) * (view.zoom || 1);
    const cx = w / 2, cy = h / 2 + (o.small ? 4 : 0);
    const P = (a, b, c) => project([a, b, c], view, scale, cx, cy);
    const depth = (a, b, c) => P(a, b, c)[2];
    // Which edges face the viewer: the ticks go on those.
    const zf = depth(0, -1, 1) > depth(0, -1, -1) ? 1 : -1;      // front, along amp
    const xf = depth(1, -1, 0) > depth(-1, -1, 0) ? 1 : -1;      // front, along hw
    // The frame, with its back edges fainter than its front ones.
    g.lineWidth = 1;
    for (const a of [-1, 1]) for (const b of [-1, 1]) {
      for (const [p0, p1] of [[[-1, a, b], [1, a, b]], [[a, -1, b], [a, 1, b]],
                              [[a, b, -1], [a, b, 1]]]) {
        const front = (p0[2] === zf || p1[2] === zf) && (p0[0] === xf || p1[0] === xf);
        g.strokeStyle = tok('--line');
        g.globalAlpha = front ? 0.9 : 0.45;
        line(g, P(...p0), P(...p1));
      }
    }
    g.globalAlpha = 1;
    if (!o.small) {
      // A floor grid at the amplitude and half-width ticks.
      g.strokeStyle = tok('--line-soft', tok('--line'));
      g.globalAlpha = 0.5;
      for (const t of niceTicks(R.amp[0], R.amp[1], 5)) {
        const u = norm(t, R.amp);
        if (Math.abs(u) < 0.999) line(g, P(u, -1, -1), P(u, -1, 1));
      }
      for (const t of niceTicks(R.hw[0], R.hw[1], 5)) {
        const u = norm(t, R.hw);
        if (Math.abs(u) < 0.999) line(g, P(-1, -1, u), P(1, -1, u));
      }
      g.globalAlpha = 1;
      // Tick values on the three front edges, and the axis names beyond them.
      g.font = FONT(10);
      g.fillStyle = tok('--text-3');
      const tickAlong = (ticks, at, off) => {
        for (const t of ticks) {
          const q = at(t);
          if (!q) continue;
          g.fillText(tickText(t), q[0] + off[0], q[1] + off[1]);
        }
      };
      const ampEdge = (t) => { const u = norm(t, R.amp);
        return Math.abs(u) <= 1.001 ? P(u, -1, zf) : null; };
      const hwEdge = (t) => { const u = norm(t, R.hw);
        return Math.abs(u) <= 1.001 ? P(xf, -1, u) : null; };
      const hfEdge = (t) => { const u = norm(t, R.hf);
        return Math.abs(u) <= 1.001 ? P(-xf, u, zf) : null; };
      g.textAlign = 'center';
      tickAlong(niceTicks(R.amp[0], R.amp[1], 5), ampEdge, [0, 15]);
      tickAlong(niceTicks(R.hw[0], R.hw[1], 4), hwEdge, [0, 15]);
      const hfLeft = P(-xf, 0, zf)[0] < cx;
      g.textAlign = hfLeft ? 'right' : 'left';
      tickAlong(niceTicks(R.hf[0], R.hf[1], 4), hfEdge, [hfLeft ? -6 : 6, 3]);
      g.font = FONT(11, true);
      g.fillStyle = tok('--text-2');
      g.textAlign = 'center';
      const a0 = P(0, -1, zf), h0 = P(xf, -1, 0), f0 = P(-xf, 1, zf);
      const out = (q, dx, dy) => [q[0] + dx, q[1] + dy];
      const am = out(a0, 0, 32), hm = out(h0, 0, 32);
      g.fillText('max amplitude · µV', am[0], am[1]);
      g.fillText('half-width · ms', hm[0], hm[1]);
      g.textAlign = hfLeft ? 'right' : 'left';
      g.fillText('HF power · dB', f0[0] + (hfLeft ? -6 : 6), f0[1] - 10);
      g.textAlign = 'left';
    }
    // The borders.
    for (const b of boxesOf(run, kind)) drawBox(g, b, R, P, o.small);
    // The dots: the context first, the stage's own on top, far ones first,
    // nearer ones a little larger and brighter -- the depth cue Root Canal's
    // own space uses.
    const set = stageSet(run, kind, stage);
    const shown = [];
    for (const p of set.pts) {
      if (!measured(p)) continue;
      const q = P(norm(p.amp, R.amp), norm(p.hf, R.hf), norm(p.hw, R.hw));
      shown.push({ p, q, keep: set.keep(p) });
    }
    shown.sort((a, b) => (a.keep - b.keep) || (a.q[2] - b.q[2]));
    let dlo = Infinity, dhi = -Infinity;
    for (const x of shown) { dlo = Math.min(dlo, x.q[2]); dhi = Math.max(dhi, x.q[2]); }
    const near = (d) => (dhi > dlo ? (d - dlo) / (dhi - dlo) : 1);
    // The picked ring only on the stage on show, never on a strip's thumbnails.
    const pick = !o.small && W.picked && W.picked.which === set.which ? W.picked.n : null;
    for (const x of shown) {
      const nr = near(x.q[2]);
      const r = o.small ? 1.2 : 1.8 + 1.4 * nr;
      g.globalAlpha = x.keep ? 0.45 + 0.5 * nr : 0.1;
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
        g.arc(x.q[0], x.q[1], 7, 0, 6.2832);
        g.stroke();
        g.lineWidth = 1;
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

  function drawBox(g, b, R, P, small) {
    const lo = [norm(b.lo.amp, R.amp), norm(b.lo.hf, R.hf), norm(b.lo.hw, R.hw)];
    const hi = [norm(b.hi.amp, R.amp), norm(b.hi.hf, R.hf), norm(b.hi.hw, R.hw)];
    if (lo.concat(hi).some((v) => !isFinite(v))) return;
    const c = (i, j, k) => P(i ? hi[0] : lo[0], j ? hi[1] : lo[1], k ? hi[2] : lo[2]);
    g.strokeStyle = b.colour;
    g.lineWidth = b.dashed ? 1 : (small ? 1.3 : 2);
    const dash = b.dashed ? [5, 4] : [];
    // A faint fill on the solid box's floor, so it reads as a volume.
    if (!b.dashed && !small) {
      g.fillStyle = b.colour;
      g.globalAlpha = 0.06;
      g.beginPath();
      const f = [c(0, 0, 0), c(1, 0, 0), c(1, 0, 1), c(0, 0, 1)];
      g.moveTo(f[0][0], f[0][1]);
      for (const q of f.slice(1)) g.lineTo(q[0], q[1]);
      g.closePath();
      g.fill();
      g.globalAlpha = 1;
    }
    for (const a of [0, 1]) for (const d of [0, 1]) {
      line(g, c(0, a, d), c(1, a, d), dash);
      line(g, c(a, 0, d), c(a, 1, d), dash);
      line(g, c(a, d, 0), c(a, d, 1), dash);
    }
  }

  /* A 2D view of two axes, with the boxes' edges on it. */
  function draw2d(cv, run, kind, stage, xa, ya, opt) {
    const o = opt || {};
    const s0 = sized(cv, o.h || 190);
    if (!s0) return;
    const { g, w, h } = s0;
    const R = o.ranges || rangesOf(run);
    const wx = AX.find((a) => a[0] === xa), wy = AX.find((a) => a[0] === ya);
    let X, Y;
    if (o.small) {
      const L = 3, B = 3, T = 3, Rr = 3;
      X = (v) => L + ((v - R[xa][0]) / (R[xa][1] - R[xa][0])) * (w - L - Rr);
      Y = (v) => h - B - ((v - R[ya][0]) / (R[ya][1] - R[ya][0])) * (h - B - T);
      g.strokeStyle = tok('--line');
      g.strokeRect(L, T, w - L - Rr, h - B - T);
    } else {
      const F = axes2d(g, w, h, R[xa], R[ya], wx[2] + ' · ' + wx[3],
                       wy[2] + ' · ' + wy[3], { L: 44, B: 32 });
      X = F.X; Y = F.Y;
    }
    const set = stageSet(run, kind, stage);
    const pts = (o.only ? set.pts.filter(o.only) : set.pts).filter(measured);
    const r = o.small ? 1 : 1.6;
    for (const keepPass of [false, true]) {
      for (const p of pts) {
        const k = set.keep(p);
        if (k !== keepPass) continue;
        g.globalAlpha = k ? 0.8 : 0.1;
        g.fillStyle = colourOf(kind, p.cls, set.which);
        g.beginPath();
        g.arc(X(p[xa]), Y(p[ya]), r, 0, 6.2832);
        g.fill();
      }
    }
    g.globalAlpha = 1;
    for (const b of boxesOf(run, kind)) {
      const x0 = X(b.lo[xa]), x1 = X(b.hi[xa]), y0 = Y(b.hi[ya]), y1 = Y(b.lo[ya]);
      if (![x0, x1, y0, y1].every(isFinite)) continue;
      g.strokeStyle = b.colour;
      g.lineWidth = b.dashed ? 1 : (o.small ? 1.2 : 1.8);
      g.setLineDash(b.dashed ? [5, 4] : []);
      g.strokeRect(x0, y0, x1 - x0, y1 - y0);
      g.setLineDash([]);
    }
    if (W.picked && W.picked.which === set.which && !o.small) {
      const p = pts.find((z) => z.n === W.picked.n);
      if (p) {
        g.strokeStyle = tok('--text');
        g.lineWidth = 2;
        g.beginPath(); g.arc(X(p[xa]), Y(p[ya]), 6, 0, 6.2832); g.stroke();
        g.lineWidth = 1;
      }
    }
    if (!o.small) cv.__pick = { which: set.which, pts: pts.filter((p) => set.keep(p))
      .map((p) => ({ p, q: [X(p[xa]), Y(p[ya])] })) };
  }

  /* How far every event is from the box on one axis, in box widths:
     below 0 inside (how deep), above 0 outside (how far out). */
  function drawDist(cv, run, kind, axisIx, which) {
    const s0 = sized(cv, 150);
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
    const F = axes2d(g, w, h, [lo, hi], [0, top * 1.08],
                     AX[axisIx][2] + ': distance from the box, in box widths',
                     'events', { L: 40, B: 32, T: 18,
                                 xfmt: (v) => (v > 0 ? '+' : '') + v });
    const col = which === 'b' || kind === 'pspike' ? tok('--call-p') : tok('--call-ds');
    for (let b = 0; b < nb; b++) {
      const v0 = lo + (b / nb) * (hi - lo), v1 = lo + ((b + 1) / nb) * (hi - lo);
      const x0 = F.X(v0), x1 = F.X(v1), y = F.Y(bins[b]);
      g.fillStyle = (v0 + v1) / 2 <= 0 ? col : tok('--text-3');
      g.globalAlpha = (v0 + v1) / 2 <= 0 ? 0.9 : 0.75;
      g.fillRect(x0 + 0.5, y, Math.max(1, x1 - x0 - 1), F.Y(0) - y);
    }
    g.globalAlpha = 1;
    g.strokeStyle = tok('--text');
    line(g, [F.X(0), F.T - 2], [F.X(0), h - F.B], [3, 3]);
    g.font = FONT(10, true);
    g.fillStyle = tok('--text-2');
    g.textAlign = 'right';
    g.fillText('inside ←', F.X(0) - 5, F.T - 5);
    g.textAlign = 'left';
    g.fillText('→ outside', F.X(0) + 5, F.T - 5);
    const nIn = pts.filter((p) => p[key][axisIx] <= 0).length;
    g.textAlign = 'right';
    g.font = FONT(10);
    g.fillText(nIn.toLocaleString() + ' in · ' + (pts.length - nIn).toLocaleString()
               + ' out on this axis', w - 12, F.T + 12);
    g.textAlign = 'left';
  }

  /* The grace sweep: how many of the target land inside, and how much of
     the border's own events the box leaves out, at every grace -- two
     y-axes, each in its own colour, the chosen grace marked and said. */
  function drawSweep(cv, run, kind) {
    const s0 = sized(cv, 210);
    if (!s0) return;
    const { g, w, h } = s0;
    const sw = run.sweep || [];
    if (!sw.length) return;
    const nmax = Math.max(1, ...sw.map((s) => s.target_inside));
    const omax = Math.max(0.1, ...sw.map((s) => s.source_outside));
    const grp = kind === 'ds' ? tok('--call-ds') : tok('--call-p');
    const F = axes2d(g, w, h, [0, 0.1], [0, nmax * 1.08], 'grace',
                     'target events inside', { L: 48, R: 44, B: 32, T: 10,
                       xfmt: (v) => +(v * 100).toFixed(0) + '%' });
    const Y2 = (v) => h - F.B - (v / (omax * 1.08)) * (h - F.B - F.T);
    // The right-hand axis: the share of the border's own events left out.
    g.font = FONT(10);
    g.fillStyle = tok('--warn');
    g.textAlign = 'left';
    for (const t of niceTicks(0, omax * 1.08, 4)) {
      g.fillText(+(t * 100).toFixed(1) + '%', w - F.R + 5, Y2(t) + 3);
    }
    const path = (ys, colour) => {
      g.strokeStyle = colour;
      g.lineWidth = 2.2;
      g.beginPath();
      sw.forEach((s, k) => { const x = F.X(s.grace), y = ys(s);
                             if (k) g.lineTo(x, y); else g.moveTo(x, y); });
      g.stroke();
      g.lineWidth = 1;
    };
    path((s) => F.Y(s.target_inside), grp);
    path((s) => Y2(s.source_outside), tok('--warn'));
    const at = sw.reduce((a, s) => (Math.abs(s.grace - run.grace) < Math.abs(a.grace - run.grace)
                                    ? s : a), sw[0]);
    g.strokeStyle = tok('--text');
    line(g, [F.X(run.grace), F.T], [F.X(run.grace), h - F.B], [3, 3]);
    for (const [y, c] of [[F.Y(at.target_inside), grp], [Y2(at.source_outside), tok('--warn')]]) {
      g.fillStyle = c;
      g.beginPath(); g.arc(F.X(run.grace), y, 4, 0, 6.2832); g.fill();
    }
    g.font = FONT(10.5, true);
    g.fillStyle = tok('--text');
    const label = 'grace ' + graceWords(run.grace) + ': '
      + at.target_inside.toLocaleString() + ' inside · ' + pct(at.source_outside)
      + ' of its own left out';
    const lx = Math.min(w - F.R - 6 - g.measureText(label).width,
                        Math.max(F.L + 6, F.X(run.grace) + 8));
    g.fillText(label, lx, F.T + 14);
    g.save();
    g.translate(w - 8, (F.T + h - F.B) / 2);
    g.rotate(Math.PI / 2);
    g.textAlign = 'center';
    g.font = FONT(10.5);
    g.fillStyle = tok('--warn');
    g.fillText('its own events left out', 0, 0);
    g.restore();
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
    const T = 26, B = 10, gap = 4;
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
    g.font = FONT(10.5, true);
    g.fillStyle = tok('--text-2');
    g.textAlign = 'right';
    g.fillText('mouse · events', lx1, 14);
    g.textAlign = 'left';
    g.fillText('where they went · events', rx0, 14);
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
    // Its four pictures at once, as Root Canal's own click panel does.
    const run = shownRun();
    const p = run && pickedPoint(run);
    const mem = run && ((W.picked.which === 'src' ? run.src_members : run.members) || []);
    const m = p && mem ? mem[p.m] || {} : {};
    if (p && m.event_body) loadEvent(m, p);
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
        r.defined_since ? BARRY.ui.chip('v' + r.defined_since + ' saved since, not run yet',
          { kind: 'warn', title: 'The pictures are v' + r.run_version + '’s run. Run it to use '
                                  + 'the newer definition.' }) : null,
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
        kind === 'ambiguous'
          ? BARRY.ui.button({ kind: 'primary', size: 'sm',
              text: r.ran ? 'Run again' : 'Run', extra: 'wf-run',
              title: 'Apply both borders to the target. Nothing is banked: tick '
                     + 'the events you want, then Bank the ticked.',
              onclick: () => runWorkflow(r, !!stale.length) })
          : BARRY.ui.button({ kind: 'primary', size: 'sm',
              text: 'Run and bank…', extra: 'wf-run-bank',
              title: 'Define the border, apply it, and bank every event inside it '
                     + 'as one Event Bank entry. A dialog says exactly what will '
                     + 'be written first.'
                     + (kind === 'pspike' ? ' The hand-sorted sets are made ready '
                        + 'first, by themselves.' : ''),
              onclick: () => runWorkflow(r, !!stale.length, { bank: true }) }),
        kind === 'ambiguous' ? null : BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: 'Run without banking', extra: 'wf-run',
          title: 'Define and apply, and keep the run as a version, with nothing '
                 + 'written to the Bank.',
          onclick: () => runWorkflow(r, !!stale.length, { bank: false }) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Edit',
          onclick: () => openBuilder(r) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: isArch ? 'Put back' : 'Archive', extra: 'wf-archive',
          title: 'Archived workflows leave the list for everyone, once it '
                 + 'syncs, and so do the bank entries they made. Nothing is '
                 + 'deleted; put it back from Show archived.',
          onclick: () => setArchived(r, !isArch) }),
      ].filter(Boolean)),
      kind === 'ambiguous' ? null : bankLine(r),
    ].filter(Boolean));
  }

  /* EXTRACT, AND WHERE IT GOES: on the Extract stage, the one place a
     person looks to bank -- what is banked, and the button that banks. */
  function bankCard(row, run, kind) {
    const word = kind === 'ds' ? 'dentate spikes' : 'P-spikes';
    if (W.preview) {
      return el('div', { class: 'wf-bankcard' }, [
        el('strong', { text: (run.kept || 0).toLocaleString() + ' verified ' + word
                             + ' would be banked' }),
        el('span', { text: 'This is a preview. Save the workflow, then press Run '
                     + 'and bank on its strip: a dialog says exactly what goes to '
                     + 'the Event Bank before anything does.' }),
        BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'Save this workflow',
          onclick: () => saveBuilder() }),
      ]);
    }
    const b = row.bank;
    const shownV = (W.data[row.artifact_id] || {}).shown;
    const thisRun = run.bank && run.bank.entry_id;
    return el('div', { class: 'wf-bankcard' + (thisRun ? ' done' : '') }, [
      el('strong', { text: thisRun
        ? 'This run is banked: ' + (run.bank.n || run.kept || 0).toLocaleString()
          + ' verified ' + word
        : (run.kept || 0).toLocaleString() + ' verified ' + word + ' extracted — '
          + 'not banked by this run' }),
      bankLine(row),
      el('div', { class: 'wf-bankcard-btns' }, [
        BARRY.ui.button({ kind: 'primary', size: 'sm',
          text: b && b.entry_id ? 'Run and bank again…' : 'Run and bank…',
          extra: 'wf-run-bank',
          title: 'Runs the workflow as it is defined and banks what is inside the '
                 + 'border. A dialog says exactly what is written first.',
          onclick: () => runWorkflow(row, !!(row.stale || []).length, { bank: true }) }),
        shownV && shownV !== row.version ? el('span', { class: 'hint', text:
          'You are looking at v' + shownV + '; the newest is v' + row.version + '.' })
          : null,
      ].filter(Boolean)),
    ]);
  }

  /* What this workflow has in the Bank, said plainly, with a door to it. */
  function bankLine(r) {
    const b = r.bank;
    if (!b || !b.entry_id) {
      return el('div', { class: 'wf-bankline none' }, [
        el('strong', { text: 'Not banked yet.' }),
        el('span', { text: 'Press Run and bank to put its extracted events in '
                     + 'the Event Bank, as one entry.' }),
      ]);
    }
    return el('div', { class: 'wf-bankline' }, [
      el('strong', { text: 'Banked' }),
      el('span', { text: (b.n || 0).toLocaleString() + ' events in ‘'
                   + (b.name || b.entry_id) + '’' + (b.version ? ', v' + b.version : '')
                   + (b.recordings ? ', from ' + b.recordings + ' recordings' : '')
                   + (r.bank_current === false ? ' — by an earlier run; the newest '
                      + 'run was not banked' : '') + '.' }),
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Open in the Event Bank',
        extra: 'wf-open-bank',
        onclick: () => (BARRY.views.eventbank && BARRY.views.eventbank.openEntry
          ? BARRY.views.eventbank.openEntry(b.entry_id) : null) }),
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
      /* NOT RUN, SAID (2026-11-05: "no visual -- what happened?"). A stage
         has a picture only once a run has made one; until then the space
         says why it is empty and what fills it. */
      run ? cv : el('span', { class: 'wf-thumb wf-thumb-empty', text: id === 'define'
        ? (kind === 'pspike' ? 'No picture yet: this workflow has not run. Run '
           + 'and bank makes the hand-sorted sets ready, then draws the border.'
           : 'No picture yet: this workflow has not run.')
        : 'No picture until it runs.' }),
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

  /* RUN, AND BANK ONLY WHEN ASKED (2026-11-05: "make the banking more
     explicit, not sure what to hit to bank").

     A P-spike workflow's hand-sorted sets are made ready first, by
     themselves ("have it do this part automatically"): put on the
     recording's clock, aligned and read here, each one only if it needs it.
     Then, to bank, the run is previewed and a dialog says exactly what will
     be written -- how many events, from how many recordings, into which
     entry, new or its next version -- under a name that can be changed.
     Nothing is written until its button, which says it banks, is pressed. */
  async function runWorkflow(r, fresh, opt) {
    const o = opt || {};
    if (W.busy) return;
    const nick = r.nickname || r.name;
    const dd = (((W.data[r.artifact_id] || {}).payload) || {}).definition
               || r.definition || {};
    let pinFresh = !!fresh;
    if (r.kind === 'pspike') {
      const ents = ((dd.source || {}).entries || []).map((e) => e.entry_id);
      W.busy = 'Making the hand-sorted sets ready';
      refresh();
      const ready = await prepareSets(ents, dd.target, (t) => { W.busy = t; refresh(); });
      if (ready.changed) pinFresh = true;   // the sets have new versions now
      if (ready.fails.length) {
        W.busy = null;
        toast('Not run: ' + ready.fails.length + ' hand-sorted set(s) could '
              + 'not be made ready — ' + ready.fails.join('; '), 'err', 20000);
        refresh();
        return;
      }
    }
    const bank = r.kind !== 'ambiguous' && o.bank !== false;
    const go = async (extra) => {
      W.busy = 'Running ‘' + nick + '’';
      refresh();
      let got;
      try {
        got = await apiPost('/api/rootcanal/workflow/'
                            + encodeURIComponent(r.artifact_id) + '/run',
                            Object.assign({ refresh: pinFresh, bank,
                                            refresh_sets: r.kind === 'pspike' }, extra || {}));
      } catch (e) {
        W.busy = null;
        refresh();
        throw e;
      }
      W.busy = null;
      const run = got.run || {};
      const b = run.bank;
      toast('‘' + nick + '’ v' + got.version + ': ' + (run.kept || 0).toLocaleString()
            + ' of ' + (run.n || 0).toLocaleString()
            + (r.kind === 'ambiguous' ? ' events are ambiguous; nothing was banked — '
               + 'tick the ones you want and press Bank the ticked.'
               : ' events inside the border. ' + (b ? 'Banked as '
                 + (b.new ? 'a new entry' : 'v' + (b.version || '?') + ' of')
                 + ' ‘' + (b.name || b.entry_id) + '’.'
                 : 'Nothing was banked.'))
            + (run.diff && run.diff.n ? ' ' + run.diff.n + ' changed class since '
               + 'the last run.' : ''), 'ok', 12000);
      BARRY.activity.log('rootcanal.workflow_run', { artifact: r.artifact_id,
                                                     version: got.version, banked: !!b });
      delete W.data[r.artifact_id];
      W.openId = r.artifact_id;
      W.stage = 'extract';
      W.list = null;
      await loadList();
      await loadOne(r.artifact_id, null);
      return got;
    };
    if (!bank) {
      try { await go(); } catch (e) {
        W.busy = null;
        toast('It did not run: ' + e.message, 'err', 14000);
        refresh();
      }
      return;
    }
    // What would be banked, exactly, before anything is.
    W.busy = 'Working out what would be banked';
    refresh();
    let pv;
    try {
      const body = Object.assign({}, dd);
      // A P-spike workflow measures its sets as prepared: their newest aligned versions.
      if (body.source && body.source.type === 'sets') {
        body.source = { entries: body.source.entries.map((e) => ({ entry_id: e.entry_id })) };
      }
      if (pinFresh) {
        for (const k of ['target', 'source']) {
          if (body[k] && body[k].type !== 'sets') body[k] = Object.assign({}, body[k], { version: null });
        }
        if (body.source && body.source.type === 'sets') {
          body.source = { entries: body.source.entries.map((e) => ({ entry_id: e.entry_id })) };
        }
      }
      pv = await apiPost('/api/rootcanal/workflow/preview', body);
    } catch (e) {
      W.busy = null;
      toast('It did not run: ' + e.message, 'err', 16000);
      refresh();
      return;
    }
    W.busy = null;
    refresh();
    const run = pv.run || {};
    const kept = run.kept || 0;
    const recs = new Set((run.cols || {}).g ? run.cols.g.filter((g, j) =>
      run.cols.cls[j] === 'inside') : []).size;
    const prior = r.bank && r.bank.entry_id ? r.bank : null;
    const word = r.kind === 'ds' ? 'dentate spikes' : 'P-spikes';
    const def = pv.definition || dd;
    const src = def.source || {};
    await BARRY.ui.bankDialog({
      title: 'Run ‘' + nick + '’ and bank ' + kept.toLocaleString() + ' verified ' + word,
      name: (prior && prior.name) || (KIND_WORDS[r.kind] + ' · ' + nick),
      what: 'This draws the border around ' + (src.type === 'sets'
        ? (src.entries || []).length + ' hand-sorted sets' : '‘' + src.nickname
          + '’ v' + src.version) + ' at grace ' + graceWords(def.grace)
        + ', applies it to ‘' + ((def.target || {}).nickname || '') + '’ v'
        + ((def.target || {}).version || '') + ', and banks the '
        + kept.toLocaleString() + ' of ' + (run.n || 0).toLocaleString()
        + ' events inside it as ONE Event Bank entry.',
      facts: [
        prior ? 'Banked as the NEXT VERSION of ‘' + (prior.name || prior.entry_id)
                + '’ (entry ' + prior.entry_id + '). The version before stays.'
              : 'Banked as a NEW entry.',
        kept.toLocaleString() + ' events from ' + recs + ' recording'
          + (recs === 1 ? '' : 's') + '; each says which recording and set it came from.',
        'Type ' + (r.kind === 'ds' ? 'Dentate spike' : 'P-spike') + ', pipeline “Root '
          + 'Canal workflow” — a border’s call, not a person’s, so not marked curated.',
        'The workflow keeps this run as its next version, and its border as a '
          + 'Root Canal border.',
      ],
      okText: 'Run and bank ' + kept.toLocaleString() + ' events',
      onBank: async (b) => { await go({ bank_name: b.name, bank_note: b.note }); },
    });
  }

  /* The hand-sorted sets, each made ready to be measured -- on the
     recording's own clock, aligned (Eye), read here -- doing only what each
     one needs. `say` hears every step. Returns the sets as they now stand,
     what could not be done, and whether anything was written. */
  async function checkSets(entries, target) {
    const got = await apiPost('/api/rootcanal/workflow/prepare', {
      entries, target: { artifact_id: (target || {}).artifact_id,
                         version: (target || {}).version } });
    return got.sets || [];
  }

  async function prepareSets(entries, target, say) {
    const fails = [];
    let changed = false;
    const tell = say || (() => {});
    let sets;
    try { sets = await checkSets(entries, target); }
    catch (e) { return { sets: [], fails: ['checking the sets — ' + e.message], changed }; }
    // 1. Onto the recording's own clock.
    for (const x of sets.filter((v) => v.clock && v.clock.retime)) {
      tell('Retiming ' + x.session_label + ' onto the recording’s clock');
      try {
        await apiPost('/api/session/retime', { path: x.path, entry_id: x.entry_id,
                                               gid: x.gid, kind: 'ied', apply: true });
        changed = true;
      } catch (e) { fails.push(x.session_label + ': retime — ' + e.message); }
    }
    if (changed) sets = await checkSets(entries, target);
    // 2. Aligned, in Eye's way, and committed as each lands.
    const need = sets.filter((v) => !v.aligned && !(v.clock && v.clock.retime));
    if (need.length) {
      tell('Aligning ' + need.length + ' hand-sorted set' + (need.length === 1 ? '' : 's')
           + ' in Eye');
      try {
        const got = await apiPost('/api/braces/batch', {
          entries: need.map((v) => ({ id: v.entry_id })), tool: 'eye' });
        const j = await waitJob((got.job || {}).id, (t) => tell('Aligning in Eye' + t));
        for (const m of j.members || []) {
          if (!m.set_id) { if (m.error) fails.push(m.label + ': align — ' + m.error); continue; }
          try {
            await apiPost('/api/braces/set/' + encodeURIComponent(m.set_id) + '/commit',
                          { apply: true });
            changed = true;
          } catch (e) { fails.push(m.label + ': commit — ' + e.message); }
        }
      } catch (e) { fails.push('align — ' + e.message); }
      sets = await checkSets(entries, target);
    }
    // 3. Read here.
    for (const x of sets.filter((v) => v.aligned && !v.read)) {
      tell('Reading ' + x.session_label);
      try {
        const got = await apiPost('/api/rootcanal/read', { entry_id: x.entry_id,
                                                           from_version: x.aligned_ref });
        if (got.job) {
          const j = await waitJob(got.job.id, (t) => tell('Reading ' + x.session_label + t));
          if (j.status !== 'done') fails.push(x.session_label + ': read — '
                                              + (j.error || j.status));
        }
      } catch (e) { fails.push(x.session_label + ': read — ' + e.message); }
    }
    sets = await checkSets(entries, target);
    for (const x of sets) {
      if (!x.aligned && !fails.some((f) => f.indexOf(x.session_label) === 0)) {
        fails.push(x.session_label + ': still not aligned');
      } else if (x.aligned && !x.read && !fails.some((f) => f.indexOf(x.session_label) === 0)) {
        fails.push(x.session_label + ': still not read here' + (x.read_why ? ' (' + x.read_why + ')' : ''));
      }
    }
    return { sets, fails, changed };
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
      d && d.newer && !W.preview ? el('p', { class: 'hint wf-warn', text: 'Showing v'
        + d.shown + ', the newest run. v' + d.newer + ' changed the definition and has '
        + 'not run yet: run it to see what it gives.' }) : null,
      d && (d.stale || []).length && !W.preview ? el('p', { class: 'hint wf-warn',
        text: 'Out of date: ' + d.stale.map((s) => s.what + ' ‘' + s.nickname
          + '’ is at ' + s.newest + ', this pins ' + s.pinned).join('; ')
          + '. Run with the newest inputs to make the next version from them.' })
        : null,
      legend(run, kind, W.stage),
      W.stage === 'extract' && kind !== 'ambiguous' ? bankCard(row, run, kind) : null,
      el('div', { class: 'wf-views' }, [
        el('div', { class: 'wf-3d-wrap' }, [big,
          el('span', { class: 'hint', text: 'Drag to turn, scroll to zoom, click '
                       + 'a dot to look at it.' })]),
        el('div', { class: 'wf-2d-col' }, flats),
      ]),
      inspector(run, kind),
      el('div', { class: 'wf-panels' }, [
        kind !== 'ambiguous' ? panel('Grace', 'What a different grace would '
          + 'have done, before choosing one. The dashed line is this run’s.',
          el('div', {}, [
            el('div', { class: 'wf-key' }, [
              el('span', { class: 'wf-lg' }, [el('i', { class: 'wf-lg-line',
                style: 'background:' + (kind === 'ds' ? tok('--call-ds') : tok('--call-p')) }),
                el('span', { text: 'target events inside the box (left axis)' })]),
              el('span', { class: 'wf-lg' }, [el('i', { class: 'wf-lg-line',
                style: 'background:' + tok('--warn') }),
                el('span', { text: 'the border’s own events it leaves out (right axis)' })]),
            ]),
            (() => { const cv = el('canvas', { class: 'wf-sweep' });
                     later(() => drawSweep(cv, run, kind)); return cv; })(),
          ])) : null,
        panel('How far from the border', 'On each axis, every target event’s '
          + 'distance from the box’s edge, in box widths: 0 is the edge, −1 the '
          + 'far side of the box, +0.5 half a box beyond it. Coloured: inside.',
          distPanel(run, kind)),
        panel('Where they went', 'Each mouse’s target events, left, to where '
          + 'the border put them, right; each band as wide as how many.', (() => {
            const cv = el('canvas', { class: 'wf-flow' });
            later(() => drawFlow(cv, run, kind)); return cv; })()),
        kind === 'ambiguous' ? panel('Conflicts', 'Events inside both borders '
          + 'are ambiguous (decided 2026-11-05) and drawn amber.',
          venn(run)) : null,
        panel('Every mouse', 'Each mouse on its own: amplitude across, HF up, '
          + 'the border’s box drawn in; under it how many came out of how many.',
          perMouse(run, kind, R)),
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

  /* EVERY MARK ON THE PICTURES, NAMED (2026-11-05: "blue solid is the
     border with grace, dashed with no grace, and what is the faint box?").
     The dots with how many of each, every box drawn, and the frame. */
  function legend(run, kind, stage) {
    const set = stageSet(run, kind, stage);
    const n = {};
    for (const p of set.pts) n[p.cls] = (n[p.cls] || 0) + 1;
    const tot = set.pts.length || 1;
    const cnt = (c) => (n[c] || 0).toLocaleString() + ' · ' + pct((n[c] || 0) / tot);
    const dot = (colour, text, c) => el('span', { class: 'wf-lg' }, [
      el('i', { class: 'wf-lg-dot', style: 'background:' + colour }),
      el('span', { text }), c != null ? el('b', { text: cnt(c) }) : null].filter(Boolean));
    const box = (colour, dashed, text) => el('span', { class: 'wf-lg' }, [
      el('i', { class: 'wf-lg-box' + (dashed ? ' dashed' : ''),
                style: 'border-color:' + colour }), el('span', { text })]);
    const dots = [];
    if (kind === 'ambiguous') {
      dots.push(dot(tok('--call-ds'), 'DS border only', 'ds'),
                dot(tok('--call-p'), 'P-spike border only', 'pspike'),
                dot(tok('--warn'), 'inside both: ambiguous', 'both'),
                dot(tok('--text-2'), 'outside both: ambiguous', 'neither'));
    } else {
      const grp = kind === 'ds' ? tok('--call-ds') : tok('--call-p');
      const w = kind === 'ds' ? 'DS' : 'P-spike';
      if (stage === 'define') {
        dots.push(dot(grp, 'the border’s own ' + w + ' events, inside it', 'inside'),
                  dot(tok('--warn'), 'its own, left outside by the grace', 'outside'));
      } else {
        dots.push(dot(grp, 'inside: verified ' + w, 'inside'),
                  dot(tok('--text-3'), 'outside the border', 'outside'));
      }
    }
    const boxes = boxesOf(run, kind).map((b) => box(b.colour, b.dashed,
      b.dashed ? b.label + ' (the widest the box gets)' : b.label));
    boxes.push(box(tok('--line'), false, 'frame: the axes, lowest to highest value on show'));
    return el('div', { class: 'wf-legend' }, [
      el('div', { class: 'wf-legend-row' }, [el('span', { class: 'wf-lg-h', text: 'Dots' })]
        .concat(dots)),
      el('div', { class: 'wf-legend-row' }, [el('span', { class: 'wf-lg-h', text: 'Boxes' })]
        .concat(boxes)),
      stage === 'extract' ? el('div', { class: 'wf-legend-row' }, [
        el('span', { class: 'wf-lg-h', text: 'Faded' }),
        el('span', { class: 'hint', text: kind === 'ambiguous'
          ? 'not ambiguous: they are inside exactly one border'
          : 'not extracted: outside the border' })]) : null,
    ].filter(Boolean));
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
             + 'counted' : '') + '. Its four pictures are below the 3D view, '
          + 'where a picked event’s are.' }));
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
    // An average on show takes the pictures' place, as in Root Canal.
    if (W.avg) {
      return el('div', { class: 'wf-insp' }, [
        el('div', { class: 'wf-insp-head' }, [
          el('strong', { text: 'Average · ' + W.avg.label }),
          W.avg.data && W.avg.data.n_away ? el('span', { class: 'hint', text:
            W.avg.data.n_away + ' read on another machine, not counted' }) : null,
          BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Close',
            onclick: () => { W.avg = null; refresh(); } }),
        ].filter(Boolean)),
        pictures(W.avg.busy ? { busy: true } : W.avg.err ? { err: W.avg.err }
                 : { data: W.avg.data }, null, {}, true),
      ]);
    }
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
        el('span', { class: 'swatch-dot', style: 'background:'
                     + colourOf(kind, p.cls, W.picked.which) }),
        el('strong', { text: (CLASS_WORDS[p.cls] || 'not measured') }),
        el('span', { class: 'hint', text: (m.session_label || p.gid || '') + ' · '
          + fmt(p.t, 3) + ' s' }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Read its traces again',
          extra: 'wf-ev-go', disabled: !m.event_body,
          title: m.event_body ? 'Its four pictures, from its own read.'
                 : 'Its read is not on this machine.',
          onclick: () => loadEvent(m, p) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Open in Xplorefinder',
          extra: 'wf-xplore', onclick: () => openX(p) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Close',
          onclick: () => { W.picked = null; W.ev = null; refresh(); } }),
      ]),
      el('div', { class: 'wf-insp-top' }, [
        el('table', { class: 'wf-cut' }, [
          el('tr', {}, [el('th', { text: '' }), el('th', { text: 'this event' }),
            ...boxes.map((b) => el('th', {}, [el('i', { class: 'wf-th-sw',
              style: 'border-color:' + b.colour }), b.label]))]),
          ...rowsT,
        ]),
        el('div', { class: 'wf-insp-hist' }, [
          el('strong', { text: 'Where it came from' }),
          el('ol', { class: 'wf-hist' }, hist.map((t) => el('li', { text: t }))),
        ]),
      ]),
    ];
    kids.push(pictures(E, m.event_body ? null
      : 'Its read is not on this machine' + (m.read_on ? ' (it was read on '
        + m.read_on + ')' : '') + ', so its numbers are here and its traces '
        + 'are not.', { cls: p.cls === 'pspike' ? 'ied' : p.cls === 'inside'
          ? ((shownDef() || {}).kind === 'pspike' ? 'ied' : 'ds') : p.cls }));
    return el('div', { class: 'wf-insp' }, kids);
  }

  /* Root Canal's own four pictures -- max-amp contact, spectrum, every
     contact, CSD -- drawn by Root Canal (rootcanal.js, `drawEvent`), for an
     event or for an average. */
  function pictures(E, away, e, average) {
    if (!H || !H.eventGrid) return null;
    const words = away ? away : !E ? null : E.busy ? (average ? 'Averaging…'
      : 'Reading its traces…') : E.err ? (average ? 'Not averaged: '
      : 'No traces: ') + E.err : null;
    const d = E && E.data ? E.data : (E && E.err ? { ok: false, error: E.err } : null);
    const grid = H.eventGrid(d, { average: !!average });
    later(() => H.drawEvent(d, e || {}));
    return el('div', { class: 'wf-pics' }, [
      words ? el('p', { class: 'hint' + (E && E.err ? ' wf-warn' : ''), text: words }) : null,
      grid,
    ].filter(Boolean));
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
      W.prep = { sets: await checkSets(Array.from(B.sets), { artifact_id: B.target }),
                 say: null };
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
      if (say) say(st.of ? ' — ' + (st.done || 0) + ' of ' + st.of : '');
      await new Promise((r) => setTimeout(r, 1500));
    }
    return { status: 'error', error: 'it took too long' };
  }

  async function prepareAll() {
    const B = W.builder;
    W.prep = Object.assign({}, W.prep || {}, { running: true, err: null });
    refresh();
    const got = await prepareSets(Array.from(B.sets), { artifact_id: B.target },
      (t) => { if (W.prep) { W.prep.say = t + '…'; refresh(); } });
    W.sources = null;
    await loadSources();
    W.prep = { sets: got.sets, running: false,
               say: got.fails.length ? 'Not everything is ready: ' + got.fails.join('; ')
                 : 'Every set is ready: on its clock, aligned and read here.' };
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
