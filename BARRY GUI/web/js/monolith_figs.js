/* ==========================================================================
   monolith_figs.js -- the Monolith's small pictures, as SVG.

   One library for the page's ? popovers, its cue-pair view, its ghost stats
   card and the Guide page, so a picture of "how coherence is made" is the
   same picture wherever it appears. Every function takes plain numbers (as
   sweep.explain and the entry route return them) and gives back an <svg>.
   Colours are the page's tokens, read when drawn.
   ========================================================================== */
'use strict';

window.MONO_FIGS = (function () {
  const NS = 'http://www.w3.org/2000/svg';
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || '#888';
  function sv(tag, attrs, text) {
    const n = document.createElementNS(NS, tag);
    for (const k in (attrs || {})) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  function svg(w, h, label) {
    // Never drawn larger than designed, so its words keep their size.
    return sv('svg', { viewBox: '0 0 ' + w + ' ' + h, role: 'img', 'aria-label': label || '',
                       class: 'mfig', width: '100%', style: 'max-width:' + w + 'px' });
  }
  const fin = (v) => v != null && isFinite(v);
  function ext(arrs, pad, sym) {
    let lo = Infinity, hi = -Infinity;
    for (const a of arrs) for (const v of (a || [])) if (fin(v)) { if (v < lo) lo = v; if (v > hi) hi = v; }
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    if (sym) { const m = Math.max(Math.abs(lo), Math.abs(hi)) || 1; lo = -m; hi = m; }
    if (hi - lo < 1e-12) { lo -= 1; hi += 1; }
    const p = (hi - lo) * (pad == null ? 0.06 : pad);
    return [lo - p, hi + p];
  }
  function sig(v) {
    if (!fin(v)) return '—';
    const a = Math.abs(v);
    return a >= 100 ? v.toFixed(0) : a >= 1 ? v.toFixed(2) : a >= 0.01 ? v.toFixed(3) : a >= 0.001 ? v.toFixed(4)
      : a === 0 ? '0' : v.toExponential(1);
  }
  function path(xs, ys, X, Y) {
    let d = '', pen = false;
    for (let i = 0; i < xs.length; i++) {
      if (!fin(xs[i]) || !fin(ys[i])) { pen = false; continue; }
      d += (pen ? 'L' : 'M') + X(xs[i]).toFixed(1) + ',' + Y(ys[i]).toFixed(1);
      pen = true;
    }
    return d;
  }
  function frame(g, W, H, m, xr, yr, opts) {
    // Room on the left for the longer of the two y labels (m is the
    // caller's, widened in place so its own drawing agrees).
    const yfs = (opts && opts.fs) || 10;
    m.l = Math.max(m.l, 6 + 0.58 * yfs * Math.max(sig(yr[0]).length, sig(yr[1]).length));
    const X = (v) => m.l + (v - xr[0]) / (xr[1] - xr[0]) * (W - m.l - m.r);
    const Y = (v) => H - m.b - (v - yr[0]) / (yr[1] - yr[0]) * (H - m.t - m.b);
    g.appendChild(sv('line', { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: css('--line-2') }));
    g.appendChild(sv('line', { x1: m.l, x2: m.l, y1: m.t, y2: H - m.b, stroke: css('--line-2') }));
    const fs = (opts && opts.fs) || 10;
    xAxis(g, X, (opts && opts.xticks) || [], H - m.b + fs + 3, W - m.r, fs, opts && opts.xlabel);
    g.appendChild(sv('text', { x: m.l - 3, y: m.t + fs - 2, 'text-anchor': 'end', 'font-size': fs, fill: css('--ink-3') }, sig(yr[1])));
    g.appendChild(sv('text', { x: m.l - 3, y: H - m.b, 'text-anchor': 'end', 'font-size': fs, fill: css('--ink-3') }, sig(yr[0])));
    if (opts && opts.ylabel) {
      g.appendChild(sv('text', { x: m.l + 4, y: m.t + fs - 2, 'font-size': fs, fill: css('--ink-3') }, opts.ylabel));
    }
    if (opts && opts.zero && yr[0] < 0 && yr[1] > 0) {
      g.appendChild(sv('line', { x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0), stroke: css('--line-2'), 'stroke-dasharray': '3 3' }));
    }
    return { X, Y };
  }
  /* Tick labels along the bottom; the unit after the last one when that one
     is at the right edge (beside it, they would overlap), else at the edge. */
  function xAxis(g, X, vals, y, right, fs, unit) {
    const last = vals.length - 1;
    const joined = unit && last >= 0 && X(vals[last]) > right - 6 * (String(vals[last]).length + unit.length + 2);
    vals.forEach((v, i) => {
      const end = i === last && X(v) > right - 14;
      g.appendChild(sv('text', { x: end ? Math.min(X(v), right) : X(v), y, 'text-anchor': end ? 'end' : 'middle', 'font-size': fs, fill: css('--ink-3') },
                       String(v) + (i === last && joined ? ' ' + unit : '')));
    });
    if (unit && !joined) g.appendChild(sv('text', { x: right, y, 'text-anchor': 'end', 'font-size': fs, fill: css('--ink-3') }, unit));
  }
  function ticks(lo, hi, n) {
    const span = hi - lo;
    const step = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000].map((s) => s * Math.pow(10, Math.floor(Math.log10(span / n) || 0)))
      .find((s) => span / s <= n) || span;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
    return out;
  }
  function band(g, X, m, H, lo, hi) {
    g.appendChild(sv('rect', { x: X(lo), y: m.t, width: Math.max(1, X(hi) - X(lo)), height: H - m.t - m.b,
                               fill: css('--focus'), 'fill-opacity': 0.14 }));
  }

  /* Two (or more) traces against time, stacked: one row per series. */
  function traces(t, series, o) {
    o = o || {};
    const W = o.w || 640, rowH = o.rowH || 54, m = { l: 34, r: 8, t: (o.marks || []).length ? 16 : 6, b: 18 };
    const H = m.t + m.b + rowH * series.length;
    const s = svg(W, H, o.label || 'traces');
    const xr = [t[0], t[t.length - 1]];
    const X = (v) => m.l + (v - xr[0]) / (xr[1] - xr[0] || 1) * (W - m.l - m.r);
    for (const mk of o.marks || []) {
      if (mk.t1 < xr[0] || mk.t0 > xr[1]) continue;
      s.appendChild(sv('line', { x1: X(Math.max(mk.t0, xr[0])), x2: X(Math.max(mk.t0, xr[0])), y1: m.t, y2: H - m.b,
                                 stroke: css('--line-2'), 'stroke-dasharray': '2 3' }));
      s.appendChild(sv('text', { x: X(Math.max(mk.t0, xr[0])) + 3, y: 11, 'font-size': 9.5, fill: css('--ink-3') }, mk.name));
    }
    if (o.highlight) {
      const [h0, h1] = o.highlight;
      s.appendChild(sv('rect', { x: X(Math.max(h0, xr[0])), y: m.t, width: Math.max(1, X(Math.min(h1, xr[1])) - X(Math.max(h0, xr[0]))),
                                 height: H - m.t - m.b, fill: css('--focus'), 'fill-opacity': 0.13 }));
    }
    series.forEach((se, i) => {
      const y0 = m.t + i * rowH, y1 = y0 + rowH;
      const yr = se.range || ext([se.y], 0.05, se.sym);
      const Y = (v) => y1 - 4 - (v - yr[0]) / (yr[1] - yr[0]) * (rowH - 8);
      if (se.zero && yr[0] < 0 && yr[1] > 0) {
        s.appendChild(sv('line', { x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0), stroke: css('--line'), 'stroke-width': 0.6 }));
      }
      s.appendChild(sv('path', { d: path(t, se.y, X, Y), fill: 'none', stroke: se.color || css('--ink'), 'stroke-width': se.width || 1 }));
      if (se.y2) {
        s.appendChild(sv('path', { d: path(t, se.y2, X, Y), fill: 'none', stroke: se.color2 || css('--ink-3'), 'stroke-width': se.width || 1 }));
      }
      s.appendChild(sv('text', { x: m.l - 3, y: y0 + rowH / 2 + 3, 'text-anchor': 'end', 'font-size': 9.5, fill: css('--ink-2') }, se.short || ''));
      if (se.label) {
        s.appendChild(sv('text', { x: W - m.r - 2, y: y0 + 10, 'text-anchor': 'end', 'font-size': 9.5, fill: css('--ink-2'),
                                   stroke: css('--surface'), 'stroke-width': 3, 'paint-order': 'stroke', 'stroke-linejoin': 'round' }, se.label));
      }
    });
    xAxis(s, X, ticks(xr[0], xr[1], 8), H - 4, W - m.r, 9.5, 's');
    return s;
  }

  /* A curve against frequency, the band shaded. */
  function spectrum(f, ys, o) {
    o = o || {};
    const W = o.w || 300, H = o.h || 130, m = { l: 34, r: 8, t: 8, b: 20 };
    const s = svg(W, H, o.label || 'spectrum');
    const yr = o.range || ext(ys.map((x) => x.y), 0.06, o.sym);
    // A quantity that cannot go below zero is not drawn as if it could.
    if (!o.range && !o.sym && ys.every((x) => (x.y || []).every((v) => !fin(v) || v >= 0))) yr[0] = Math.max(yr[0], 0);
    const xr = [0, o.fmax || 60];
    const { X, Y } = frame(s, W, H, m, xr, yr, { xticks: [0, 10, 20, 30, 40, 50, 60].filter((v) => v <= xr[1]), xlabel: 'Hz', ylabel: o.ylabel, zero: o.zero });
    if (o.band) band(s, X, m, H, o.band[0], o.band[1]);
    for (const se of ys) {
      s.appendChild(sv('path', { d: path(f, se.y, X, Y), fill: 'none', stroke: se.color || css('--ink'), 'stroke-width': se.width || 1.4,
                                 'stroke-dasharray': se.dash || null }));
    }
    return s;
  }

  /* r against lag, its peak marked. */
  function lag(ms, r, o) {
    o = o || {};
    const W = o.w || 300, H = o.h || 140, m = { l: 34, r: 8, t: 18, b: 20 };
    const s = svg(W, H, o.label || 'cross-correlation');
    const xr = [ms[0], ms[ms.length - 1]];
    const { X, Y } = frame(s, W, H, m, xr, [-1, 1], { xticks: [xr[0], 0, xr[1]].map((v) => Math.round(v)), xlabel: 'lag ms', zero: true });
    s.appendChild(sv('path', { d: path(ms, r, X, Y), fill: 'none', stroke: o.color || css('--ink'), 'stroke-width': 1.4 }));
    if (o.peak && fin(o.peak[1])) {
      s.appendChild(sv('circle', { cx: X(o.peak[0]), cy: Y(o.peak[1]), r: 4, fill: css('--up') }));
      const say = 'r ' + sig(o.peak[1]) + ' at ' + Math.round(o.peak[0]) + ' ms';
      const half = say.length * 2.8;
      const tx = Math.min(W - m.r - half, Math.max(m.l + half, X(o.peak[0])));
      const ty = Math.min(H - m.b - 4, Math.max(11, Y(o.peak[1]) + (o.peak[1] > 0 ? -7 : 14)));
      s.appendChild(sv('text', { x: tx, y: ty, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-2'),
                                 stroke: css('--surface'), 'stroke-width': 3, 'paint-order': 'stroke', 'stroke-linejoin': 'round' }, say));
    }
    return s;
  }

  /* The phase differences around a circle (36 bins), and their mean
     vector: its length is the PLV. */
  function rose(hist, o) {
    o = o || {};
    const W = o.w || 150, H = o.h || 150, cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 14;
    const s = svg(W, H, o.label || 'phase differences');
    s.appendChild(sv('circle', { cx, cy, r: R, fill: 'none', stroke: css('--line-2') }));
    s.appendChild(sv('line', { x1: cx - R, x2: cx + R, y1: cy, y2: cy, stroke: css('--line') }));
    s.appendChild(sv('line', { x1: cx, x2: cx, y1: cy - R, y2: cy + R, stroke: css('--line') }));
    const mx = Math.max(1e-9, ...hist.filter(fin));
    const n = hist.length;
    hist.forEach((h, i) => {
      if (!fin(h)) return;
      const a0 = -Math.PI + 2 * Math.PI * i / n, a1 = a0 + 2 * Math.PI / n, r = R * h / mx;
      const p = (a, rr) => (cx + rr * Math.cos(a)).toFixed(1) + ',' + (cy - rr * Math.sin(a)).toFixed(1);
      s.appendChild(sv('path', { d: 'M' + cx + ',' + cy + ' L' + p(a0, r) + ' L' + p(a1, r) + ' z', fill: css('--ink-3'), 'fill-opacity': 0.55 }));
    });
    if (fin(o.angle) && fin(o.length)) {
      const x = cx + R * o.length * Math.cos(o.angle), y = cy - R * o.length * Math.sin(o.angle);
      s.appendChild(sv('line', { x1: cx, y1: cy, x2: x, y2: y, stroke: css('--up'), 'stroke-width': 3, 'stroke-linecap': 'round' }));
    }
    s.appendChild(sv('text', { x: cx + R + 2, y: cy - 3, 'font-size': 9, fill: css('--ink-3') }, '0'));
    s.appendChild(sv('text', { x: cx, y: cy - R - 3, 'text-anchor': 'middle', 'font-size': 9, fill: css('--ink-3') }, '+90°'));
    return s;
  }

  /* Each piece of the window as a point on the unit circle: PPC and the
     debiased wPLI count pairs of these. */
  function segs(angle, size, o) {
    o = o || {};
    const W = o.w || 150, H = o.h || 150, cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 12;
    const s = svg(W, H, o.label || 'segments');
    s.appendChild(sv('circle', { cx, cy, r: R, fill: 'none', stroke: css('--line-2') }));
    s.appendChild(sv('line', { x1: cx - R, x2: cx + R, y1: cy, y2: cy, stroke: css('--line') }));
    angle.forEach((a, i) => {
      if (!fin(a)) return;
      const r = R * (fin(size[i]) ? Math.max(0.15, size[i]) : 1);
      s.appendChild(sv('line', { x1: cx, y1: cy, x2: cx + r * Math.cos(a), y2: cy - r * Math.sin(a), stroke: css('--ink-2'), 'stroke-width': 1.2 }));
    });
    return s;
  }

  /* How often the first region leads vs lags (PLI), and by how much (wPLI). */
  function signs(p, o) {
    o = o || {};
    const W = o.w || 180, H = o.h || 110, m = { l: 8, r: 8, t: 10, b: 18 };
    const s = svg(W, H, o.label || 'lead and lag');
    const rows = [['leads (count)', p.lead_frac, p.lag_frac], ['leads (weighted)', p.w_lead, p.w_lag]];
    rows.forEach(([name, a, b], i) => {
      const y = m.t + i * 42, w = W - m.l - m.r;
      s.appendChild(sv('rect', { x: m.l, y, width: w * (a || 0), height: 16, fill: css('--up'), 'fill-opacity': 0.75 }));
      s.appendChild(sv('rect', { x: m.l + w * (a || 0), y, width: w * (b || 0), height: 16, fill: css('--down'), 'fill-opacity': 0.75 }));
      s.appendChild(sv('text', { x: m.l, y: y + 28, 'font-size': 9.5, fill: css('--ink-2') },
                       name + ': A ahead ' + Math.round(100 * (a || 0)) + '%, behind ' + Math.round(100 * (b || 0)) + '%'));
    });
    return s;
  }

  /* Phase-binned amplitude (PAC): one bar per phase bin, the flat line is
     what no coupling looks like. */
  function pacBars(p, o) {
    o = o || {};
    const W = o.w || 220, H = o.h || 110, m = { l: 26, r: 6, t: 8, b: 18 };
    const s = svg(W, H, o.label || 'phase-binned amplitude');
    const n = p.length, flat = 1 / n;
    const yr = [0, Math.max(flat * 1.6, ...p.filter(fin)) * 1.05];
    const { X, Y } = frame(s, W, H, m, [0, n], yr, { xticks: [], fs: 9 });
    p.forEach((v, i) => {
      if (!fin(v)) return;
      s.appendChild(sv('rect', { x: X(i) + 1, y: Y(v), width: Math.max(1, X(i + 1) - X(i) - 2), height: Math.max(0, Y(0) - Y(v)),
                                 fill: css('--ink-3'), 'fill-opacity': 0.7 }));
    });
    s.appendChild(sv('line', { x1: X(0), x2: X(n), y1: Y(flat), y2: Y(flat), stroke: css('--up'), 'stroke-dasharray': '4 3' }));
    s.appendChild(sv('text', { x: X(0), y: H - 4, 'font-size': 9, fill: css('--ink-3') }, '−180°'));
    s.appendChild(sv('text', { x: X(n), y: H - 4, 'text-anchor': 'end', 'font-size': 9, fill: css('--ink-3') }, '+180°'));
    if (o.mi != null) s.appendChild(sv('text', { x: X(n), y: m.t + 9, 'text-anchor': 'end', 'font-size': 10, fill: css('--ink-2') }, 'MI ' + sig(o.mi)));
    return s;
  }

  /* Each rat's change with its 95% interval, sized by its weight, and the
     pooled change as a diamond across the Hartung-Knapp interval. */
  function forest(rows, pooled, o) {
    o = o || {};
    const W = o.w || 420, rowH = 18, m = { l: 46, r: 12, t: 8, b: 22 };
    const H = m.t + m.b + rowH * (rows.length + 1.5);
    const s = svg(W, H, o.label || 'forest plot');
    const vals = [];
    rows.forEach((r) => { if (r.ci) vals.push(r.ci[0], r.ci[1]); else if (fin(r.delta)) vals.push(r.delta); });
    if (pooled && pooled.ci) vals.push(pooled.ci[0], pooled.ci[1]);
    vals.push(0);
    const xr = ext([vals], 0.08);
    const X = (v) => m.l + (v - xr[0]) / (xr[1] - xr[0]) * (W - m.l - m.r);
    s.appendChild(sv('line', { x1: X(0), x2: X(0), y1: m.t, y2: H - m.b, stroke: css('--ink-3'), 'stroke-dasharray': '3 3' }));
    const wmax = Math.max(1e-9, ...rows.map((r) => r.weight || 0));
    rows.forEach((r, i) => {
      const y = m.t + rowH * (i + 0.5);
      s.appendChild(sv('text', { x: m.l - 6, y: y + 3.5, 'text-anchor': 'end', 'font-size': 10.5, fill: css('--ink-2') }, r.rat));
      if (!fin(r.delta)) {
        s.appendChild(sv('text', { x: X(0) + 6, y: y + 3.5, 'font-size': 10, fill: css('--ink-3') }, r.why ? 'left out' : '—'));
        return;
      }
      const col = r.delta >= 0 ? css('--up') : css('--down');
      if (r.ci) s.appendChild(sv('line', { x1: X(r.ci[0]), x2: X(r.ci[1]), y1: y, y2: y, stroke: col, 'stroke-width': 1.4 }));
      const sz = 3 + 6 * Math.sqrt((r.weight || 0) / wmax);
      s.appendChild(sv('rect', { x: X(r.delta) - sz / 2, y: y - sz / 2, width: sz, height: sz, fill: col }));
    });
    if (pooled && fin(pooled.est)) {
      const y = m.t + rowH * (rows.length + 0.9);
      const lo = pooled.ci ? pooled.ci[0] : pooled.est, hi = pooled.ci ? pooled.ci[1] : pooled.est;
      s.appendChild(sv('path', { d: 'M' + X(lo) + ',' + y + ' L' + X(pooled.est) + ',' + (y - 7) + ' L' + X(hi) + ',' + y + ' L' + X(pooled.est) + ',' + (y + 7) + ' z',
                                 fill: css('--ink'), 'fill-opacity': 0.85 }));
      s.appendChild(sv('text', { x: m.l - 6, y: y + 3.5, 'text-anchor': 'end', 'font-size': 10.5, 'font-weight': 600, fill: css('--ink') }, 'pooled'));
    }
    for (const v of ticks(xr[0], xr[1], 5)) {
      s.appendChild(sv('text', { x: X(v), y: H - 6, 'text-anchor': 'middle', 'font-size': 9.5, fill: css('--ink-3') }, sig(v)));
    }
    return s;
  }

  /* Each rat's Precon1 and Precon4, joined: the change, rat by rat. */
  function slope(rows, o) {
    o = o || {};
    const W = o.w || 300, H = o.h || 170, m = { l: 44, r: 44, t: 14, b: 22 };
    const s = svg(W, H, o.label || 'Precon1 to Precon4, rat by rat');
    const ok = rows.filter((r) => fin(r.left) && fin(r.right));
    const yr = ext([ok.map((r) => r.left), ok.map((r) => r.right)], 0.08);
    const Y = (v) => H - m.b - (v - yr[0]) / (yr[1] - yr[0]) * (H - m.t - m.b);
    const x0 = m.l, x1 = W - m.r;
    s.appendChild(sv('line', { x1: x0, x2: x0, y1: m.t, y2: H - m.b, stroke: css('--line-2') }));
    s.appendChild(sv('line', { x1: x1, x2: x1, y1: m.t, y2: H - m.b, stroke: css('--line-2') }));
    s.appendChild(sv('text', { x: x0, y: H - 6, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-2') }, o.left || 'Precon1'));
    s.appendChild(sv('text', { x: x1, y: H - 6, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-2') }, o.right || 'Precon4'));
    s.appendChild(sv('text', { x: x0 - 4, y: Y(yr[1]) + 9, 'text-anchor': 'end', 'font-size': 9.5, fill: css('--ink-3') }, sig(yr[1])));
    s.appendChild(sv('text', { x: x0 - 4, y: Y(yr[0]), 'text-anchor': 'end', 'font-size': 9.5, fill: css('--ink-3') }, sig(yr[0])));
    for (const r of ok) {
      const col = r.right >= r.left ? css('--up') : css('--down');
      s.appendChild(sv('line', { x1: x0, x2: x1, y1: Y(r.left), y2: Y(r.right), stroke: col, 'stroke-width': 1.6, 'stroke-opacity': 0.85 }));
      s.appendChild(sv('circle', { cx: x0, cy: Y(r.left), r: 3, fill: col }));
      s.appendChild(sv('circle', { cx: x1, cy: Y(r.right), r: 3, fill: col }));
      s.appendChild(sv('text', { x: x1 + 6, y: Y(r.right) + 3, 'font-size': 9.5, fill: css('--ink-3') }, r.rat));
    }
    return s;
  }

  /* One dot per cue pair, the mean with its SE; groups side by side. */
  function dots(groups, o) {
    o = o || {};
    const W = o.w || 360, H = o.h || 160, m = { l: 40, r: 10, t: 10, b: 24 };
    const s = svg(W, H, o.label || 'cue pairs');
    const all = [];
    groups.forEach((g) => { all.push(...g.values.filter(fin)); if (fin(g.mean)) all.push(g.mean - (g.se || 0), g.mean + (g.se || 0)); });
    const yr = ext([all], 0.08);
    const Y = (v) => H - m.b - (v - yr[0]) / (yr[1] - yr[0]) * (H - m.t - m.b);
    const gw = (W - m.l - m.r) / Math.max(1, groups.length);
    s.appendChild(sv('text', { x: m.l - 4, y: Y(yr[1]) + 9, 'text-anchor': 'end', 'font-size': 9.5, fill: css('--ink-3') }, sig(yr[1])));
    s.appendChild(sv('text', { x: m.l - 4, y: Y(yr[0]), 'text-anchor': 'end', 'font-size': 9.5, fill: css('--ink-3') }, sig(yr[0])));
    groups.forEach((g, gi) => {
      const cx = m.l + gw * (gi + 0.5);
      const n = g.values.length;
      g.values.forEach((v, i) => {
        const x = cx - gw * 0.28 + (n > 1 ? gw * 0.56 * i / (n - 1) : 0);
        const dot = fin(v) ? sv('circle', { cx: x, cy: Y(v), r: 3.2, fill: g.color || css('--ink-2'), 'fill-opacity': 0.8, 'data-i': String(i) })
          : sv('circle', { cx: x, cy: H - m.b - 4, r: 3, fill: 'none', stroke: css('--ink-3'), 'data-i': String(i) });
        if (o.onDot) dot.addEventListener('click', () => o.onDot(gi, i));
        if (o.tip) o.tip(dot, gi, i);
        s.appendChild(dot);
      });
      if (fin(g.mean)) {
        s.appendChild(sv('line', { x1: cx - gw * 0.32, x2: cx + gw * 0.32, y1: Y(g.mean), y2: Y(g.mean), stroke: css('--ink'), 'stroke-width': 2.2 }));
        if (fin(g.se)) {
          s.appendChild(sv('line', { x1: cx, x2: cx, y1: Y(g.mean - g.se), y2: Y(g.mean + g.se), stroke: css('--ink'), 'stroke-width': 1.4 }));
        }
      }
      s.appendChild(sv('text', { x: cx, y: H - 6, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-2') }, g.name));
    });
    return s;
  }

  /* A small ring of regions and the pairs that passed. */
  function miniCircuit(regions, pairs, passed, o) {
    o = o || {};
    const W = o.w || 220, H = o.h || 220, cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 34;
    const s = svg(W, H, o.label || 'circuit');
    const pos = regions.map((_r, i) => {
      const a = -Math.PI / 2 + (i + 0.5) * 2 * Math.PI / regions.length;
      return [cx + R * Math.cos(a), cy + R * Math.sin(a), a];
    });
    s.appendChild(sv('circle', { cx, cy, r: R, fill: 'none', stroke: css('--line') }));
    for (const p of passed) {
      const [a, b] = pairs[p.pair];
      s.appendChild(sv('line', { x1: pos[a][0], y1: pos[a][1], x2: pos[b][0], y2: pos[b][1],
                                 stroke: (p.est || 0) >= 0 ? css('--up') : css('--down'), 'stroke-width': 2 }));
    }
    pos.forEach(([x, y, a], i) => {
      s.appendChild(sv('circle', { cx: x, cy: y, r: 4.5, fill: css('--node') }));
      // Beside the dot on the sides, above or below it at the top and bottom.
      const c = Math.cos(a), side = c > 0.3 ? 'start' : c < -0.3 ? 'end' : 'middle', rr = side === 'middle' ? R + 12 : R + 8;
      s.appendChild(sv('text', { x: cx + rr * c, y: cy + rr * Math.sin(a) + 3, 'text-anchor': side,
                                 'font-size': 8, fill: css('--ink-3') }, String(regions[i]).replace(/^Left /, 'L ').replace(/^Right /, 'R ')));
    });
    return s;
  }

  return { traces, spectrum, lag, rose, segs, signs, pacBars, forest, slope, dots, miniCircuit, sig, css, sv };
})();
