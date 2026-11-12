/* ==========================================================================
   monolith_explain.js -- the Monolith page's things to play with instead of
   read (the lab, 2026-10-09: "make the website less of a chore").

     more(title, mount)   a ▸ More that, opened, mounts something to play
                          with, and plays it when it scrolls into view
     numberPlayer(...)    how one stat test's number is made: every trial,
                          each rat's day, (Minus FP), each rat's change, the
                          pooled change, the test
     shuffle(...)         what chance gives: the rats shuffled one way after
                          another, each shuffle's count dropping into a
                          histogram, and the real count landing last
     fpSlider(...)        Raw and Minus FP: drag a day's FP value and watch
                          the two changes
     soundSort(...)       the identity sheet: A/B/C/D, the noise-first and
                          tone-first rats, and every sound gathered from
                          wherever it sat

   Motion is playful (it overshoots, and a result that lands celebrates) and
   stops for prefers-reduced-motion. Every animation also ends on a timer:
   under the harness's virtual time a frame may never come. Load order:
   after monolith.js.
   ========================================================================== */
'use strict';

window.MONO_EXPLAIN = (function () {
  const M = () => window.MONO;
  const NS = 'http://www.w3.org/2000/svg';
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || '#888';
  const el = (...a) => M().el(...a);
  function sv(tag, attrs, text) {
    const n = document.createElementNS(NS, tag);
    for (const k in (attrs || {})) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  const sig = (v) => M().sig(v), f3 = (v) => M().f3(v), fp = (v) => M().fp(v);
  const fmt = (n) => (n == null ? '—' : Number(n).toLocaleString('en-US'));
  const reduced = () => { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } };
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const lerp = (a, b, t) => a + (b - a) * t;
  // Playful: a little past the mark and back.
  const EASE = {
    out: (t) => 1 - Math.pow(1 - t, 3),
    back: (t) => { const c1 = 1.5, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); },
    lin: (t) => t,
  };
  // One tween: frame(t) from 0 to 1, then done; it ends on a timer too.
  function tween(ms, frame, ease) {
    return new Promise((resolve) => {
      const e = EASE[ease || 'out'];
      if (reduced() || ms <= 0) { frame(1); resolve(); return; }
      let over = false;
      const t0 = performance.now();
      const finish = () => { if (over) return; over = true; frame(1); resolve(); };
      const step = (now) => {
        if (over) return;
        const t = Math.min(1, (now - t0) / ms);
        frame(e(t));
        if (t < 1) requestAnimationFrame(step); else finish();
      };
      requestAnimationFrame(step);
      setTimeout(finish, ms + 150);
    });
  }
  const wait = (ms) => new Promise((r) => setTimeout(r, reduced() ? 0 : ms));
  // Once, when at least 40% of it is on screen.
  function onVisible(node, fn) {
    if (typeof IntersectionObserver === 'undefined') { fn(); return; }
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) { io.disconnect(); fn(); }
    }, { threshold: 0.4 });
    io.observe(node);
  }
  // A little burst where a result lands.
  function celebrate(svg, x, y, color) {
    if (reduced()) return;
    const g = sv('g', { class: 'xburst' });
    svg.appendChild(g);
    const dots = Array.from({ length: 10 }, (_v, i) => {
      const c = sv('circle', { cx: x, cy: y, r: 3, fill: color || css('--up') });
      g.appendChild(c);
      return { c, a: (i / 10) * 2 * Math.PI };
    });
    tween(700, (t) => {
      for (const d of dots) {
        d.c.setAttribute('cx', (x + Math.cos(d.a) * 26 * t).toFixed(1));
        d.c.setAttribute('cy', (y + Math.sin(d.a) * 26 * t).toFixed(1));
        d.c.setAttribute('opacity', (1 - t).toFixed(2));
      }
    }, 'out').then(() => g.remove());
  }
  // A picture is drawn in its own units and scaled to its box; on a phone
  // its words would shrink with it. The factor that keeps them readable
  // (about 9 px at the least), and the words grown by it.
  function fsOf(host, VW) {
    const w = (host && host.clientWidth) || (typeof innerWidth === 'number' ? innerWidth - 40 : VW);
    return clamp(0.95 * VW / Math.max(240, w), 1, 2.2);
  }
  function grow(svg, fs) {
    if (!(fs > 1)) return;
    for (const t of svg.querySelectorAll('text')) {
      const f = parseFloat(t.getAttribute('font-size'));
      if (f) t.setAttribute('font-size', (f * fs).toFixed(1));
    }
  }
  // A token that cancels what an earlier play started.
  function runner() {
    let id = 0;
    return { next: () => ++id, live: (k) => k === id };
  }

  /* ---------------- ▸ More ---------------- */
  const OPEN = new Map();
  // What has played once already: a page that is drawn again (every view
  // change redraws the cards) does not play it again.
  const PLAYED = new Set();
  // Play a piece once, the first time it scrolls into view.
  function playOnce(key, node, piece) {
    if (!piece || !piece.play || PLAYED.has(key)) return;
    onVisible(node, () => { if (PLAYED.has(key)) return; PLAYED.add(key); piece.play(); });
  }
  function more(title, mount, opts) {
    opts = opts || {};
    const key = opts.key || title;
    const body = el('div', { class: 'xbody' });
    const d = el('details', { class: 'xmore', 'data-key': key }, [el('summary', {}, [el('span', { class: 'xchev', 'aria-hidden': 'true', text: '▸' }),
      el('span', { text: 'More: ' + title })]), body]);
    let mounted = false;
    const go = () => {
      if (mounted) return;
      mounted = true;
      const piece = mount(body);
      if (piece && piece.play && !PLAYED.has(key)) onVisible(body, () => { PLAYED.add(key); piece.play(); });
    };
    d.addEventListener('toggle', () => { OPEN.set(key, d.open); if (d.open) go(); });
    if (OPEN.get(key) || opts.open) { d.open = true; go(); }
    // Words only: there from the start (find-in-page sees them), still folded.
    else if (opts.eager) go();
    return d;
  }

  /* ==================================================================
     How a number is made
     ================================================================== */
  // One stat test's numbers, from /entry: every rat's trials (and FP
  // epochs), its days, its change and weight, and the pooled result.
  function npData(detail, minusFP) {
    const finite = (x) => x != null && isFinite(x);
    const rats = (detail.rats || []).filter((r) => r.days && r.days.Precon1 && r.days.Precon4 && finite(r.delta)).map((r) => {
      const d1 = r.days.Precon1, d4 = r.days.Precon4;
      const tri = (d) => (d.units || []).map((u) => u.v).filter(finite);
      const fpv = (d) => (d.rest_units || []).map((u) => u.v).filter(finite);
      return { rat: r.rat, t: [tri(d1), tri(d4)], f: [fpv(d1), fpv(d4)], c: [d1.cue, d4.cue],
               s: [Math.sqrt(d1.cue_se2 || 0), Math.sqrt(d4.cue_se2 || 0)], fm: [d1.rest, d4.rest], x: [d1.x, d4.x],
               xs: [Math.sqrt(d1.se2 || 0), Math.sqrt(d4.se2 || 0)], delta: r.delta, ci: r.ci || [r.delta, r.delta], w: r.weight || 1 };
    });
    const minus = !!minusFP && rats.some((r) => r.f[0].length || r.f[1].length);
    return { rats, minus, pooled: detail.pooled || {} };
  }
  function tDensity(t, df) {
    const lg = (z) => {           // log gamma, Lanczos
      const g = 7, c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059,
        12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
      if (z < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * z)) - lg(1 - z);
      z -= 1;
      let x = c[0];
      for (let i = 1; i < g + 2; i++) x += c[i] / (z + i);
      const tt = z + g + 0.5;
      return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(tt) - tt + Math.log(x);
    };
    return Math.exp(lg((df + 1) / 2) - lg(df / 2) - 0.5 * Math.log(df * Math.PI) - ((df + 1) / 2) * Math.log(1 + t * t / df));
  }
  function numberPlayer(host, detail, opts) {
    opts = opts || {};
    host.innerHTML = '';
    const D = npData(detail, opts.minusFP);
    const P0 = D.pooled;
    if (!D.rats.length || P0.est == null) {
      host.appendChild(el('p', { class: 'empty', text: 'Not enough rats with this stat test on both days to show it.' }));
      return null;
    }
    const n = D.rats.length;
    const fs = Math.min(2.1, fsOf(host, 720));
    const VW = 720, VH = 340, L = Math.round(20 + 34 * fs), R = 520, T = 26, B = 300, PX = 610;
    const colW = (R - L) / n;
    const colX = (i, d) => L + colW * (i + 0.5) + (d ? 0.22 : -0.22) * colW;
    const midX = (i) => L + colW * (i + 0.5);
    const scale = (vals) => {
      const v = vals.filter((x) => x != null && isFinite(x));
      let lo = Math.min(...v), hi = Math.max(...v);
      if (!(hi > lo)) { lo -= 1; hi += 1; }
      const pad = (hi - lo) * 0.08;
      lo -= pad; hi += pad;
      return { lo, hi, Y: (x) => B - (x - lo) / (hi - lo) * (B - T) };
    };
    const all = [];
    for (const r of D.rats) for (const d of [0, 1]) {
      all.push(...r.t[d], r.c[d] - r.s[d], r.c[d] + r.s[d]);
      if (D.minus) all.push(...r.f[d], r.fm[d]);
    }
    const SA = scale(all);
    const SB = scale(D.rats.flatMap((r) => [0, 1].flatMap((d) => [r.x[d] - r.xs[d], r.x[d] + r.xs[d]])));
    const SX = D.minus ? SB : SA;
    const SC = scale(D.rats.flatMap((r) => [r.ci[0], r.ci[1], r.delta]).concat([0, P0.ci ? P0.ci[0] : P0.est, P0.ci ? P0.ci[1] : P0.est]));
    const wmax = Math.max(...D.rats.map((r) => r.w));
    const up = (x) => css(x >= 0 ? '--up' : '--down');
    const jit = (j, m) => (m > 1 ? (j / (m - 1) - 0.5) * colW * 0.26 : 0);
    const STAGES = [['trials', 'Trials'], ['days', 'Each day']].concat(D.minus ? [['fp', 'FP'], ['sub', 'Minus FP']] : [],
      [['change', 'Each change'], ['side', 'Side by side'], ['pooled', 'Pooled'], ['test', 'The test']]);
    const sid = STAGES.map((s) => s[0]);
    const after = (st, name) => sid.indexOf(st) >= sid.indexOf(name);
    // The scene: every element, and where it is at every stage (null: not there).
    const E = [];
    const add = (kind, key, attrs, pose, extra) => E.push(Object.assign({ kind, key, attrs, pose }, extra || {}));
    let ti = 0;
    D.rats.forEach((r, i) => {
      for (const d of [0, 1]) {
        r.t[d].forEach((v, j) => {
          const k = ti++;
          add('circle', 'tr', { fill: d ? css('--ink-2') : 'none', stroke: css('--ink-2'), 'stroke-width': 1, class: 'xtrial' }, (st) =>
            st === 'trials' ? { cx: colX(i, d) + jit(j, r.t[d].length), cy: SA.Y(v), r: 2.6, opacity: 0.85 }
              : st === 'days' ? { cx: colX(i, d), cy: SA.Y(r.c[d]), r: 1.5, opacity: 0 } : null,
          { enter: { cy: T - 30, opacity: 0 }, delay: (k % 40) / 80 });
        });
        add('line', 'ds', { stroke: css('--ink'), class: 'xdayse' }, (st) => {
          if (st === 'trials' || after(st, 'side')) return null;
          const sub = D.minus && after(st, 'sub');
          const Y = sub ? SB.Y : SA.Y, c = sub ? r.x[d] : r.c[d], s = sub ? r.xs[d] : r.s[d];
          return { x1: colX(i, d), x2: colX(i, d), y1: Y(c - s), y2: Y(c + s), 'stroke-width': 1.4, opacity: st === 'change' ? 0.35 : 1 };
        });
        add('line', 'dm', { stroke: css('--ink'), class: 'xday', 'data-rat': String(r.rat), 'data-day': String(d) }, (st) => {
          if (st === 'trials' || after(st, 'side')) return null;
          const sub = D.minus && after(st, 'sub');
          const y = (sub ? SB.Y : SA.Y)(sub ? r.x[d] : r.c[d]);
          return { x1: colX(i, d) - 7, x2: colX(i, d) + 7, y1: y, y2: y, 'stroke-width': 3, opacity: st === 'change' ? 0.5 : 1 };
        });
        if (D.minus) {
          r.f[d].forEach((v, j) => add('circle', 'fp', { fill: css('--node-grey'), class: 'xfp' }, (st) =>
            st === 'fp' ? { cx: colX(i, d) + colW * 0.12 + jit(j, r.f[d].length) * 0.4, cy: SA.Y(v), r: 2.2, opacity: 0.9 }
              : st === 'sub' ? { cx: colX(i, d), cy: SB.Y(0), r: 1, opacity: 0 } : null, { enter: { opacity: 0, r: 0 } }));
          add('line', 'fm', { stroke: css('--ink-3'), 'stroke-dasharray': '3 2', class: 'xfpm' }, (st) => {
            const y = st === 'fp' ? SA.Y(r.fm[d]) : st === 'sub' ? SB.Y(0) : null;
            return y == null ? null : { x1: colX(i, d) - 9, x2: colX(i, d) + 13, y1: y, y2: y, 'stroke-width': 2, opacity: st === 'fp' ? 1 : 0 };
          });
        }
      }
      // The change: an arrow from Precon1 to Precon4, then a bar from zero.
      add('line', 'ar', { stroke: up(r.delta), 'stroke-linecap': 'round', class: 'xchange', 'data-rat': String(r.rat) }, (st) => {
        if (!after(st, 'change')) return null;
        if (st === 'change') return { x1: colX(i, 0), y1: SX.Y(r.x[0]), x2: colX(i, 1), y2: SX.Y(r.x[1]), 'stroke-width': 2.5, opacity: 1 };
        return { x1: midX(i), y1: SC.Y(0), x2: midX(i), y2: SC.Y(r.delta), 'stroke-width': 2 + 7 * r.w / wmax, opacity: st === 'side' ? 0.9 : 0.35 };
      });
      add('line', 'ci', { stroke: up(r.delta), class: 'xci' }, (st) => (after(st, 'side')
        ? { x1: midX(i) + 10, x2: midX(i) + 10, y1: SC.Y(r.ci[0]), y2: SC.Y(r.ci[1]), 'stroke-width': 1, opacity: st === 'side' ? 0.8 : 0.3 } : null));
      add('circle', 'fl', { fill: up(r.delta), class: 'xflow' }, (st) => (st === 'side' ? { cx: midX(i), cy: SC.Y(r.delta), r: 3 + 5 * r.w / wmax, opacity: 0.9 }
        : after(st, 'pooled') ? { cx: PX, cy: SC.Y(P0.est), r: 2, opacity: 0 } : null), { delay: i / (2 * n) });
      add('text', 'rl', { 'text-anchor': 'middle', 'font-size': 10.5, fill: css('--ink-3'), text: 'r' + r.rat }, (st) => ({ x: midX(i), y: B + 16, opacity: 1 }));
    });
    // Each scale's top and bottom, said at the left while it is the one drawn.
    const scaleOf = (st) => (['trials', 'days', 'fp'].includes(st) ? 'A' : st === 'sub' ? 'B' : st === 'change' ? (D.minus ? 'B' : 'A') : 'C');
    for (const [id, Sx] of [['A', SA], ['B', SB], ['C', SC]]) {
      for (const [end, v] of [['hi', Sx.hi], ['lo', Sx.lo]]) {
        add('text', 'y' + id + end, { 'text-anchor': 'end', 'font-size': 10, fill: css('--ink-3'), text: sig(v), class: 'xtick' }, (st) =>
          (scaleOf(st) === id && st !== 'test' ? { x: L - 6, y: Sx.Y(v) + (end === 'hi' ? 9 : -2), opacity: 1 } : null));
      }
    }
    add('text', 'y0', { 'text-anchor': 'end', 'font-size': 10, fill: css('--ink-3'), text: '0', class: 'xtick' }, (st) =>
      (scaleOf(st) === 'C' && st !== 'test' ? { x: L - 6, y: SC.Y(0) + 3.5, opacity: 1 } : null));
    add('line', 'zero', { stroke: css('--line-2'), class: 'xzero' }, (st) => (after(st, 'side') ? { x1: L, x2: PX + 40, y1: SC.Y(0), y2: SC.Y(0), 'stroke-width': 1, opacity: 1 } : null));
    const ci = P0.ci || [P0.est - 1.96 * (P0.se || 0), P0.est + 1.96 * (P0.se || 0)];
    add('line', 'pci', { stroke: css('--ink'), class: 'xpci' }, (st) => (after(st, 'pooled') ? { x1: PX, x2: PX, y1: SC.Y(ci[0]), y2: SC.Y(ci[1]), 'stroke-width': 1.5, opacity: 1 } : null));
    add('diamond', 'pd', { fill: css('--ink'), class: 'xpooled' }, (st) => (after(st, 'pooled') ? { cx: PX, cy: SC.Y(P0.est), hw: 9, hh: 9, opacity: 1 } : null),
      { enter: { hw: 0, hh: 0, opacity: 0 } });
    add('text', 'pl', { 'text-anchor': 'middle', 'font-size': 11, 'font-weight': 600, fill: css('--ink'), text: 'pooled ' + f3(P0.est) }, (st) =>
      (after(st, 'pooled') ? { x: PX, y: Math.max(T + 10, SC.Y(ci[1]) - 8), opacity: 1 } : null));
    // The test: the t distribution, its tails past the real t shaded.
    const df = P0.df || (P0.k || n) - 1;
    const tval = P0.se ? P0.est / P0.se : null;
    const TX0 = 540, TX1 = 712, TY0 = 60, TY1 = 250;
    const span = Math.max(5, Math.min(8, Math.abs(tval || 0) + 1));
    const tX = (t) => TX0 + (clamp(t, -span, span) + span) / (2 * span) * (TX1 - TX0);
    const dmax = tDensity(0, df);
    const tY = (dv) => TY1 - dv / dmax * (TY1 - TY0);
    let curve = '';
    for (let k = 0; k <= 80; k++) { const t = -span + 2 * span * k / 80; curve += (k ? 'L' : 'M') + tX(t).toFixed(1) + ',' + tY(tDensity(t, df)).toFixed(1); }
    const tail = (sgn) => {
      const a = Math.min(span, Math.abs(tval || 0));
      let d = 'M' + tX(sgn * a).toFixed(1) + ',' + TY1;
      for (let k = 0; k <= 30; k++) { const t = sgn * (a + (span - a) * k / 30); d += 'L' + tX(t).toFixed(1) + ',' + tY(tDensity(t, df)).toFixed(1); }
      return d + 'L' + tX(sgn * span).toFixed(1) + ',' + TY1 + 'Z';
    };
    // At the test the rats' changes stay, faint, and the pooled marker makes
    // way for the t distribution on the right.
    for (const e of E) {
      const p0 = e.pose;
      if (['ar', 'ci', 'zero'].includes(e.key)) {
        e.pose = (st) => { if (st !== 'test') return p0(st); const a = p0('pooled'); return a && Object.assign({}, a, { opacity: 0.22 }); };
      } else if (['fl', 'pci', 'pd', 'pl'].includes(e.key)) {
        e.pose = (st) => (st === 'test' ? null : p0(st));
      }
    }
    add('path', 'tc', { d: curve, fill: 'none', stroke: css('--ink-2'), 'stroke-width': 1.6, class: 'xtcurve' }, (st) => (st === 'test' ? { opacity: 1 } : null));
    for (const sgn of [-1, 1]) add('path', 'tt', { d: tail(sgn), fill: css('--up'), class: 'xttail' }, (st) => (st === 'test' ? { opacity: 0.35 } : null));
    add('line', 'tm', { stroke: css('--up'), class: 'xtmark' }, (st) => (st === 'test' && tval != null
      ? { x1: tX(tval), x2: tX(tval), y1: TY0 - 10, y2: TY1, 'stroke-width': 2.5, opacity: 1 } : null), { enter: { y1: TY1, opacity: 0 } });
    add('line', 'tz', { stroke: css('--line-2') }, (st) => (st === 'test' ? { x1: TX0, x2: TX1, y1: TY1, y2: TY1, 'stroke-width': 1, opacity: 1 } : null));
    add('text', 'tl', { 'text-anchor': tval != null && tval > 0 ? 'end' : 'start', 'font-size': 12, 'font-weight': 600, fill: css('--up'),
                        text: 't = ' + (tval == null ? '—' : tval.toFixed(1)) + (tval != null && Math.abs(tval) > span ? (tval > 0 ? ' →' : ' ←') : '') },
        (st) => (st === 'test' ? { x: tval != null && tval > 0 ? Math.min(TX1, tX(tval) - 4) : Math.max(TX0, tX(tval || 0) + 4), y: TY0 - 14, opacity: 1 } : null));
    add('text', 'tp', { 'text-anchor': 'middle', 'font-size': 16, 'font-weight': 700, fill: css('--ink'), class: 'xtp', text: 'p = ' + fp(P0.p) },
        (st) => (st === 'test' ? { x: (TX0 + TX1) / 2, y: TY1 + 34, opacity: 1 } : null), { enter: { opacity: 0, y: TY1 + 60 } });
    // Draw.
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', class: 'xnum', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': 'How this stat test’s number is made' });
    for (const e of E) {
      const tag = e.kind === 'diamond' ? 'polygon' : e.kind;
      const a = Object.assign({}, e.attrs);
      const text = a.text;
      delete a.text;
      e.node = sv(tag, a, text);
      e.node.setAttribute('opacity', '0');
      svg.appendChild(e.node);
    }
    grow(svg, fs);
    const setA = (e, a) => {
      if (!a) { e.node.setAttribute('opacity', '0'); return; }
      for (const k in a) {
        if (e.kind === 'diamond' && (k === 'cx' || k === 'cy' || k === 'hw' || k === 'hh')) continue;
        e.node.setAttribute(k, typeof a[k] === 'number' ? a[k].toFixed(k === 'opacity' ? 2 : 1) : a[k]);
      }
      if (e.kind === 'diamond') {
        e.node.setAttribute('points', [[a.cx, a.cy - a.hh], [a.cx + a.hw, a.cy], [a.cx, a.cy + a.hh], [a.cx - a.hw, a.cy]].map((q) => q.map((x) => x.toFixed(1)).join(',')).join(' '));
      }
    };
    const blend = (a, b, t) => {
      const o = {};
      for (const k in b) o[k] = typeof b[k] === 'number' && typeof a[k] === 'number' ? lerp(a[k], b[k], t) : b[k];
      return o;
    };
    // The words under it: one line a stage, with this stat test's numbers.
    const nTr = D.rats.reduce((s, r) => s + r.t[0].length + r.t[1].length, 0);
    const nUp = D.rats.filter((r) => r.delta > 0).length;
    const SAY = {
      trials: nTr + ' trials from ' + n + ' rats: ○ Precon1, ● Precon4. Each dot is one trial’s value.',
      days: 'Each rat’s day: the mean of its trials, ± how sure that mean is.',
      fp: 'Minus FP: the same measure in that day’s FP1 and FP2 (grey).',
      sub: '… comes off each day first.',
      change: 'Each rat’s change, Precon1 → Precon4: ' + nUp + ' of ' + n + ' up.',
      side: 'Side by side from zero. Thicker: a steadier rat, which counts for more.',
      pooled: 'Pooled over the rats: ' + f3(P0.est) + ' (95% interval ' + f3(ci[0]) + ' to ' + f3(ci[1]) + ').',
      test: 't = ' + f3(P0.est) + ' ÷ ' + sig(P0.se) + ' = ' + (tval == null ? '—' : tval.toFixed(1)) + ' on ' + df + ' df → p = ' + fp(P0.p)
        + (P0.p != null && P0.p < 0.05 ? ': passes p < .05 (uncorrected).' : ': does not pass p < .05.'),
    };
    const cap = el('p', { class: 'xcap', id: opts.capId || null });
    const chips = el('div', { class: 'xsteps' });
    const btn = (text, title, on) => el('button', { type: 'button', class: 'xbtn', title, text, onclick: on });
    const run = runner();
    let cur = -1, trans = 0;
    const show = (k) => {
      cur = k;
      cap.textContent = SAY[sid[k]];
      Array.from(chips.children).forEach((c, i) => c.setAttribute('aria-pressed', String(i === k)));
      host.dataset.stage = sid[k];
    };
    async function goTo(k, ms) {
      const from = cur < 0 ? null : sid[cur], to = sid[k];
      const my = ++trans;             // a later step stops this one drawing
      show(k);
      const pairs = E.map((e) => {
        const b = e.pose(to);
        const a = from == null ? null : e.pose(from);
        const start = a || (b ? Object.assign({}, b, e.enter || {}, { opacity: 0 }) : null);
        const end = b || (a ? Object.assign({}, a, { opacity: 0 }) : null);
        return [e, start, end];
      });
      await tween(ms == null ? 900 : ms, (t) => {
        if (my !== trans) return;
        for (const [e, a, b] of pairs) {
          if (!a || !b) { setA(e, b); continue; }
          const d = e.delay || 0;
          const tt = clamp((t - d) / Math.max(0.2, 1 - d), 0, 1.2);
          setA(e, blend(a, b, tt));
        }
      }, 'back');
      if (my !== trans) return;
      for (const [e, , b] of pairs) setA(e, b);
      if (to === 'test' && P0.p != null && P0.p < 0.05 && tval != null) celebrate(svg, tX(tval), TY0 - 10, css('--up'));
    }
    STAGES.forEach(([id, label], k) => chips.appendChild(el('button', { type: 'button', class: 'xstep', 'data-stage': id, text: label,
      onclick: () => { run.next(); goTo(k); } })));
    async function play() {
      const tok = run.next();
      for (let k = 0; k < sid.length; k++) {
        if (!run.live(tok)) return;
        await goTo(k);
        await wait(k === sid.length - 1 ? 0 : 1100);
      }
    }
    const ctl = el('div', { class: 'xctl' }, [
      btn('◀', 'Back a step', () => { run.next(); if (cur > 0) goTo(cur - 1); }),
      btn('▶ Play', 'Play every step', () => play()),
      btn('▶|', 'Next step', () => { run.next(); if (cur < sid.length - 1) goTo(cur + 1); }),
      chips]);
    const wrap = el('div', { class: 'xplayer xnumplayer' }, [opts.title ? el('div', { class: 'xtitle', text: opts.title }) : null, svg, cap, ctl]);
    host.appendChild(wrap);
    goTo(0, 0);
    return {
      play, el: wrap, data: D, stages: sid.slice(),
      get stage() { return sid[cur]; },
      jump: (name) => { run.next(); const k = sid.indexOf(name); if (k >= 0) return goTo(k, 0); return Promise.resolve(); },
    };
  }

  /* ==================================================================
     Shuffle: what chance gives
     ================================================================== */
  // The i-th way of signing n rats, as the backend lists them (the first
  // rat always +), or the i-th split of them into two halves (the first rat
  // always in the first half), in the same order.
  function signsOf(i, n) { return [1].concat(Array.from({ length: n - 1 }, (_v, j) => ((i >> j) & 1 ? -1 : 1))); }
  function splits(n) {
    const out = [];
    const h = n / 2;
    const rec = (start, pick) => {
      if (pick.length === h) { if (pick[0] === 0) out.push(pick.slice()); return; }
      for (let i = start; i < n; i++) { pick.push(i); rec(i + 1, pick); pick.pop(); }
    };
    rec(0, []);
    return out;
  }
  function shuffle(host, o) {
    host.innerHTML = '';
    const counts = (o.counts || []).slice();
    if (!counts.length) return null;
    const real = o.realIndex == null ? 0 : o.realIndex;
    const obs = o.observed != null ? o.observed : counts[real];
    const n = (o.rats || []).length || 8;
    const kind = o.kind || 'sign';
    const SPL = kind === 'split' ? splits(n) : null;
    const fs = fsOf(host, 640);
    const VW = 640, VH = 240, L = 20, R = 620, HT = Math.round(60 + 16 * fs), HB = 204;
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', class: 'xshuf', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': o.title || 'What chance gives' });
    // The rats, as tokens.
    const tok = (o.rats || Array.from({ length: n }, (_v, i) => 'r' + i)).map((name, i) => {
      const x = VW / 2 + (i - (n - 1) / 2) * 44 * Math.min(fs, 1.3);
      const g = sv('g', { class: 'xtok', transform: 'translate(' + x + ',' + Math.round(14 + 16 * Math.min(fs, 1.3)) + ')' });
      const c = sv('circle', { cx: 0, cy: 0, r: 15 * Math.min(fs, 1.3), fill: css('--chip'), stroke: css('--line-2') });
      const t = sv('text', { x: 0, y: 4, 'text-anchor': 'middle', 'font-size': 10.5, fill: css('--ink') }, String(name));
      // Its sign up and to the right, clear of its name at any size.
      const rr = 15 * Math.min(fs, 1.3);
      const s = sv('text', { x: (0.8 * rr).toFixed(1), y: (-0.4 * rr).toFixed(1), 'text-anchor': 'start', 'font-size': 12, 'font-weight': 700, fill: css('--ink-2') }, '');
      g.appendChild(c); g.appendChild(t); g.appendChild(s);
      svg.appendChild(g);
      return { g, c, s, x };
    });
    const paint = (i) => {
      if (kind === 'sign') {
        const sg = signsOf(i, n);
        tok.forEach((t, j) => { t.c.setAttribute('fill', css(sg[j] > 0 ? '--up' : '--down')); t.c.setAttribute('fill-opacity', '0.25'); t.s.textContent = sg[j] > 0 ? '+' : '−'; });
      } else if (kind === 'split') {
        const a = new Set(SPL[i] || []);
        tok.forEach((t, j) => { t.c.setAttribute('fill', css(a.has(j) ? '--up' : '--down')); t.c.setAttribute('fill-opacity', '0.25'); t.s.textContent = ''; });
      } else {
        tok.forEach((t) => { t.c.setAttribute('fill', css('--chip')); t.s.textContent = '?'; });
      }
    };
    // The histogram, empty.
    const vals = counts.concat([obs, o.expected]).filter((v) => v != null && isFinite(v));
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (hi - lo < 1) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.05;
    lo = Math.max(0, lo - pad); hi += pad;
    const nb = Math.min(30, Math.max(8, Math.round(Math.sqrt(counts.length) * 2.5)));
    const step = (hi - lo) / nb;
    const binOf = (v) => clamp(Math.floor((v - lo) / step), 0, nb - 1);
    const others = counts.map((c, i) => [c, i]).filter(([, i]) => i !== real);
    const tall = Math.max(1, ...Array.from({ length: nb }, (_v, b) => others.filter(([c]) => binOf(c) === b).length));
    const X = (v) => L + (R - L) * (v - lo) / (hi - lo);
    const bh = Math.min(10, (HB - HT) / tall);
    const bw = Math.max(2, (R - L) / nb - 2);
    svg.appendChild(sv('line', { x1: L, x2: R, y1: HB, y2: HB, stroke: css('--line-2') }));
    [[lo, 'start'], [hi, 'end']].forEach(([v, a]) => svg.appendChild(sv('text', { x: X(v), y: HB + 14, 'text-anchor': a, 'font-size': 10, fill: css('--ink-3') }, fmt(Math.round(v)))));
    svg.appendChild(sv('text', { x: VW / 2, y: HB + 28, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, o.axis || 'stat tests with p < .05'));
    if (o.expected != null) {
      svg.appendChild(sv('line', { x1: X(o.expected), x2: X(o.expected), y1: HT - 4, y2: HB, stroke: css('--ink-3'), 'stroke-dasharray': '3 2', class: 'xexp' }));
    }
    const stacks = new Array(nb).fill(0);
    const blocks = sv('g', { class: 'xblocks' });
    svg.appendChild(blocks);
    // Other sortings of the same rats worth seeing among the shuffles.
    for (const m of (o.marks || [])) {
      if (m.v == null || !isFinite(m.v)) continue;
      svg.appendChild(sv('line', { x1: X(m.v), x2: X(m.v), y1: HT - 4, y2: HB, stroke: m.color || css('--arrow'), 'stroke-width': 2,
                                   class: 'xmark', 'data-mark': m.id || null }));
    }
    const mark = sv('g', { class: 'xreal', opacity: '0' });
    const mx = X(obs);
    mark.appendChild(sv('line', { x1: mx, x2: mx, y1: HT - 10, y2: HB, stroke: css('--up'), 'stroke-width': 2.5 }));
    // The real count's label: beside its line, on whichever side it fits
    // (its width guessed from its letters, the words grown on a phone).
    const mlText = (o.realLabel || 'the real rats') + ': ' + fmt(obs);
    const mlW = mlText.length * 11.5 * fs * 0.56;
    const mlAt = mx > VW / 2 ? (mx - 6 - mlW >= 0 ? ['end', mx - 6] : mx + 6 + mlW <= VW ? ['start', mx + 6] : ['middle', clamp(mx, mlW / 2, VW - mlW / 2)])
      : (mx + 6 + mlW <= VW ? ['start', mx + 6] : mx - 6 - mlW >= 0 ? ['end', mx - 6] : ['middle', clamp(mx, mlW / 2, VW - mlW / 2)]);
    const ml = sv('text', { x: mlAt[1], y: HT - 14, 'text-anchor': mlAt[0], 'font-size': 11.5, 'font-weight': 700, fill: css('--up') }, mlText);
    mark.appendChild(ml);
    svg.appendChild(mark);
    const cap = el('p', { class: 'xcap' });
    const beyond = o.rank != null && o.rank <= Math.max(1, Math.floor(0.05 * counts.length));
    const done = o.rankSay || (o.rank != null ? 'The real rats rank ' + o.rank + ' of ' + counts.length + ': '
      + (beyond ? 'beyond nearly every shuffle.' : o.rank <= 2 * Math.max(1, Math.floor(0.05 * counts.length)) ? 'borderline.' : 'an ordinary count among the shuffles.') : '');
    const run = runner();
    const drop = (c, quick) => {
      const b = binOf(c);
      const y = HB - (stacks[b] + 1) * bh;
      stacks[b]++;
      const r = sv('rect', { x: X(lo + b * step) + 1, y: quick ? y : HT - 20, width: bw, height: Math.max(1, bh - 0.6), fill: css('--node-grey'), class: 'xblock' });
      blocks.appendChild(r);
      if (!quick) tween(320, (t) => r.setAttribute('y', lerp(HT - 20, y, t).toFixed(1)), 'back');
    };
    const reset = () => { blocks.innerHTML = ''; stacks.fill(0); mark.setAttribute('opacity', '0'); paint(real); };
    async function play() {
      const tk = run.next();
      reset();
      cap.textContent = o.say || 'Each shuffle mixes the rats’ changes up; its count drops in. Chance, built shuffle by shuffle.';
      if (reduced()) { others.forEach(([c]) => drop(c, true)); land(); return; }
      for (let k = 0; k < others.length; k++) {
        if (!run.live(tk)) return;
        const [c, i] = others[k];
        paint(i);
        drop(c, k > 8);
        await wait(k < 6 ? 420 : k < 20 ? 60 : 14);
      }
      if (!run.live(tk)) return;
      paint(real);
      await wait(250);
      land();
    }
    function land() {
      mark.setAttribute('opacity', '1');
      tween(600, (t) => mark.setAttribute('transform', 'translate(0,' + ((1 - t) * -40).toFixed(1) + ')'), 'back');
      cap.textContent = done;
      if (beyond) celebrate(svg, mx, HT - 10, css('--up'));
    }
    const ctl = el('div', { class: 'xctl' }, [el('button', { type: 'button', class: 'xbtn', text: '▶ Shuffle', onclick: () => play() }),
      el('span', { class: 'small muted', text: fmt(counts.length - 1) + ' shuffles' + (o.expected != null ? ' · dashed: 5% by chance' : '') })]);
    const key = (o.marks || []).filter((m) => m.v != null && isFinite(m.v)).length ? el('div', { class: 'xkey' }, (o.marks || [])
      .filter((m) => m.v != null && isFinite(m.v)).map((m) => el('span', {}, [el('i', { style: 'background:' + (m.color || css('--arrow')) + ';width:3px' }),
        m.label + ': ' + fmt(m.v)]))) : null;
    // Before it plays: the finished picture, so a glance still says it.
    others.forEach(([c]) => drop(c, true));
    paint(real);
    mark.setAttribute('opacity', '1');
    cap.textContent = done;
    grow(svg, fs);
    const wrap = el('div', { class: 'xplayer xshuffle' }, [o.title ? el('div', { class: 'xtitle', text: o.title }) : null, svg, key, cap, ctl]);
    host.appendChild(wrap);
    return { play, el: wrap, get blocks() { return blocks.childElementCount; } };
  }

  /* ==================================================================
     Found against chance: a bar a count, chance marked on it
     ================================================================== */
  // rows: [{ id, label, found, chance, active, title }]. With opts.onPick
  // each row is a button. The bars grow in, then chance drops onto them.
  function chanceBars(host, rows, opts) {
    opts = opts || {};
    host.innerHTML = '';
    rows = rows.filter((r) => r.found != null && isFinite(r.found));
    if (!rows.length) return null;
    const max = Math.max(1, ...rows.map((r) => Math.max(r.found, r.chance || 0))) * 1.06;
    const pc = (v) => (100 * clamp(v, 0, max) / max).toFixed(2) + '%';
    const more = (r) => (r.chance > 0 ? Math.round(100 * (r.found / r.chance - 1)) : null);
    const ratio = (r) => { const m = more(r); return m == null ? '' : m > 0 ? m + '% more than chance' : m < 0 ? -m + '% fewer than chance' : 'as chance gives'; };
    const items = rows.map((r) => {
      const f = el('i', { class: 'xbf' }), c = el('i', { class: 'xbc' });
      const num = el('b', { text: fmt(r.found) });
      const x = el('span', { class: 'xbx', text: r.chance != null ? ' · chance ' + fmt(Math.round(r.chance)) : '' });
      const row = el(opts.onPick ? 'button' : 'div', { class: 'xbarrow', 'data-id': r.id, type: opts.onPick ? 'button' : null,
        'aria-pressed': opts.onPick ? String(!!r.active) : null, title: r.title || ratio(r) || null,
        onclick: opts.onPick ? () => opts.onPick(r.id) : null },
      [el('span', { class: 'xbl', text: r.label }), el('span', { class: 'xbt' }, [f, c]), el('span', { class: 'xbn' }, [num, x])]);
      return { r, f, c, num, row };
    });
    // Each row a little after the one above it; every one lands on its
    // value, and the overshoot of the easing gives the bounce.
    const set = (t, tc) => items.forEach(({ r, f, c }, i) => {
      const d = Math.min(0.5, 0.15 * i);
      const ti = clamp((t - d) / (1 - d), 0, 1.2);
      f.style.width = pc(r.found * ti);
      c.style.left = pc(r.chance || 0);
      c.style.opacity = String(clamp(tc, 0, 1));
      c.style.transform = 'translateY(' + ((1 - clamp(tc, 0, 1)) * -10).toFixed(1) + 'px)';
    });
    const run = runner();
    async function play() {
      const tk = run.next();
      set(0, 0);
      await tween(900, (t) => { if (run.live(tk)) set(t, 0); }, 'back');
      if (!run.live(tk)) return;
      await tween(380, (t) => { if (run.live(tk)) set(1, t); }, 'back');
      if (!run.live(tk)) return;
      items.forEach(({ num }) => { num.classList.remove('xpop'); void num.offsetWidth; num.classList.add('xpop'); });
    }
    const box = el('div', { class: 'xbars' }, items.map((x) => x.row));
    const key = el('div', { class: 'xkey' }, [el('span', {}, [el('i'), opts.found || 'found']),
      el('span', {}, [el('i', { class: 'dash' }), opts.chance || 'what chance alone gives']),
      opts.onPick ? el('span', { text: opts.pickSay || 'click a row to show it' }) : null]);
    const wrap = el('div', { class: 'xplayer xchance' }, [box, key]);
    host.appendChild(wrap);
    if (opts.key && PLAYED.has(opts.key)) set(1, 1);
    else { set(0, 0); onVisible(wrap, () => { if (opts.key) PLAYED.add(opts.key); play(); }); }
    return { play, el: wrap, ratio };
  }

  /* ==================================================================
     Phase–amplitude coupling, to play with
     ================================================================== */
  // A slow wave, a fast one whose loudness follows the slow one's phase by
  // the slider's amount, and the fast wave's mean loudness in each of the
  // 18 phase bins: flat is no coupling (MI 0), a lean is coupling.
  function pacToy(host, opts) {
    opts = opts || {};
    host.innerHTML = '';
    const NB = 18, SW = 400, SH = 176;
    // Two pictures side by side, each its own size: on a phone they stack.
    const sig1 = sv('svg', { viewBox: '0 0 ' + SW + ' ' + SH, width: '100%', class: 'xpac xpacsig', role: 'img', style: 'max-width:' + SW + 'px',
                             'aria-label': 'A slow wave, and a fast one whose loudness follows it' });
    sig1.appendChild(sv('text', { x: 0, y: 12, 'font-size': 11, fill: css('--ink-3') }, 'slow wave (4 Hz): its phase'));
    sig1.appendChild(sv('text', { x: 0, y: 90, 'font-size': 11, fill: css('--ink-3') }, 'fast wave (25 Hz): how loud it is'));
    const slow = sv('path', { fill: 'none', stroke: css('--ink-2'), 'stroke-width': 1.6, class: 'xpacslow' });
    const fast = sv('path', { fill: 'none', stroke: css('--arrow'), 'stroke-width': 1.1, class: 'xpacfast' });
    const env = sv('path', { fill: 'none', stroke: css('--up'), 'stroke-width': 1.4, 'stroke-dasharray': '3 2', class: 'xpacenv' });
    sig1.appendChild(slow); sig1.appendChild(fast); sig1.appendChild(env);
    const BW = 220, BH = 196, BL = 6, BR = 214, BT = 30, BB = 160;
    const sig2 = sv('svg', { viewBox: '0 0 ' + BW + ' ' + BH, width: '100%', class: 'xpac xpacbins', role: 'img', style: 'max-width:' + BW + 'px',
                             'aria-label': 'How loud the fast wave is, in each of the slow wave’s phase bins' });
    sig2.appendChild(sv('text', { x: BL, y: 12, 'font-size': 11, fill: css('--ink-3') }, 'how loud, by phase'));
    sig2.appendChild(sv('line', { x1: BL, x2: BR, y1: BB, y2: BB, stroke: css('--line-2') }));
    const flat = sv('line', { x1: BL, x2: BR, stroke: css('--ink-3'), 'stroke-dasharray': '3 2' });
    sig2.appendChild(flat);
    const bw = (BR - BL) / NB;
    const bars = Array.from({ length: NB }, (_v, j) => { const r = sv('rect', { x: (BL + j * bw + 1).toFixed(1), width: (bw - 2).toFixed(1),
      fill: css('--arrow'), class: 'xpacbin' }); sig2.appendChild(r); return r; });
    sig2.appendChild(sv('text', { x: BL, y: BB + 14, 'font-size': 10, fill: css('--ink-3') }, '−180°'));
    sig2.appendChild(sv('text', { x: BR, y: BB + 14, 'text-anchor': 'end', 'font-size': 10, fill: css('--ink-3') }, '+180°'));
    sig2.appendChild(sv('text', { x: (BL + BR) / 2, y: BB + 30, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, 'the slow wave’s phase'));
    const v = { k: opts.k != null ? opts.k : 0.7, ph: 0 };
    const mi = (k) => {
      const A = Array.from({ length: NB }, (_v, j) => 1 + k * Math.cos(-Math.PI + (j + 0.5) * 2 * Math.PI / NB));
      const s = A.reduce((a, b) => a + b, 0);
      const H = -A.reduce((h, a) => (a > 0 ? h + (a / s) * Math.log(a / s) : h), 0);
      return { A, s, v: (Math.log(NB) - H) / Math.log(NB) };
    };
    const out = el('b', { class: 'xpacmi' });
    const range = el('input', { type: 'range', min: '0', max: '100', value: String(Math.round(v.k * 100)), 'aria-label': 'How strongly the fast wave follows the slow one',
                                class: 'xpacrange' });
    const draw = () => {
      let ds = '', df = '', de = '';
      for (let x = 0; x <= SW; x += 2) {
        const t = x / SW;
        const p = 2 * Math.PI * 4 * t + v.ph;
        const amp = 1 + v.k * Math.cos(p);
        ds += (x ? 'L' : 'M') + x + ',' + (48 - 24 * Math.cos(p)).toFixed(1);
        df += (x ? 'L' : 'M') + x + ',' + (136 - 18 * amp * Math.sin(2 * Math.PI * 25 * t)).toFixed(1);
        de += (x ? 'L' : 'M') + x + ',' + (136 - 18 * amp).toFixed(1);
      }
      slow.setAttribute('d', ds); fast.setAttribute('d', df); env.setAttribute('d', de);
      const M2 = mi(v.k);
      const top = 2 / NB;
      M2.A.forEach((a, j) => { const h = (BB - BT) * (a / M2.s) / top; bars[j].setAttribute('y', (BB - h).toFixed(1)); bars[j].setAttribute('height', h.toFixed(1)); });
      const yf = BB - (BB - BT) * (1 / NB) / top;
      flat.setAttribute('y1', yf.toFixed(1)); flat.setAttribute('y2', yf.toFixed(1));
      out.textContent = 'MI = ' + (M2.v < 0.001 && M2.v > 0 ? M2.v.toExponential(1) : M2.v.toFixed(3));
    };
    const run = runner();
    range.addEventListener('input', () => { run.next(); v.k = Number(range.value) / 100; draw(); });
    async function play() {
      const tk = run.next();
      const k1 = v.k;
      v.k = 0;
      draw();
      await tween(1600, (t) => { if (run.live(tk)) { v.k = k1 * t; v.ph = 2 * Math.PI * t; draw(); } }, 'back');
      if (run.live(tk)) { v.k = k1; range.value = String(Math.round(k1 * 100)); draw(); }
    }
    draw();
    const ctl = el('div', { class: 'xctl' }, [el('button', { type: 'button', class: 'xbtn', text: '▶ Play', onclick: () => play() }),
      el('label', { class: 'small' }, ['none ', range, ' strong']), out]);
    const cap = el('p', { class: 'xcap', text: 'Slide it: the more the fast wave follows the slow one’s phase, the more the bins lean, and the higher the MI. '
      + 'Flat bins (dashed) are no coupling. ' + (opts.say || '') });
    const wrap = el('div', { class: 'xplayer xpactoy' }, [el('div', { class: 'xpacrow' }, [sig1, sig2]), ctl, cap]);
    host.appendChild(wrap);
    grow(sig1, fsOf(host, SW));
    grow(sig2, fsOf(host, BW * 1.6));
    return { play, el: wrap, set: (k) => { run.next(); v.k = k; range.value = String(Math.round(k * 100)); draw(); }, mi: (k) => mi(k).v };
  }

  /* ==================================================================
     Raw and Minus FP: drag a day's FP value
     ================================================================== */
  function fpSlider(host, ex) {
    host.innerHTML = '';
    const v = { c1: ex.c1, f1: ex.f1, c4: ex.c4, f4: ex.f4 };
    const VW = 560, VH = 250, B = 210, T = 24;
    const all = [v.c1, v.f1, v.c4, v.f4];
    let lo = Math.min(...all), hi = Math.max(...all);
    const pad = Math.max(0.02, (hi - lo) * 0.9);
    lo -= pad; hi += pad;
    const Y = (x) => B - (x - lo) / (hi - lo) * (B - T);
    const Yinv = (y) => lo + (B - y) / (B - T) * (hi - lo);
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', class: 'xfp', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': 'Raw and Minus FP, worked both ways' });
    const days = [['1', 'Precon1', 90], ['4', 'Precon4', 250]];
    const node = {};
    for (const [d, name, x] of days) {
      svg.appendChild(sv('text', { x: x + 18, y: B + 18, 'text-anchor': 'middle', 'font-size': 11, fill: css('--ink-2') }, name));
      node['c' + d] = sv('rect', { x, width: 30, fill: css('--ink-2'), class: 'xfpcue', 'data-day': d });
      node['f' + d] = sv('rect', { x: x + 34, width: 22, fill: css('--node-grey'), class: 'xfpfp', 'data-day': d });
      node['h' + d] = sv('rect', { x: x + 30, width: 30, height: 12, rx: 6, fill: css('--arrow'), class: 'xhandle', tabindex: '0',
                                   role: 'slider', 'aria-label': name + ' FP value', style: 'cursor:ns-resize' });
      svg.appendChild(node['c' + d]); svg.appendChild(node['f' + d]); svg.appendChild(node['h' + d]);
    }
    svg.appendChild(sv('text', { x: 105, y: T - 8, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, 'trials'));
    svg.appendChild(sv('text', { x: 135, y: T - 8, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, 'FP'));
    const arrRaw = sv('line', { stroke: css('--ink'), 'stroke-width': 2, 'marker-end': null, class: 'xfpraw' });
    svg.appendChild(arrRaw);
    const out = el('div', { class: 'xfpout' }, [
      el('div', { class: 'xbig' }, [el('span', { class: 'lab', text: 'Raw' }), el('b', { class: 'xraw' })]),
      el('div', { class: 'xbig' }, [el('span', { class: 'lab', text: 'Minus FP' }), el('b', { class: 'xmfp' })]),
      el('p', { class: 'small muted', text: 'Drag either FP handle. Raw is trials only, so it never moves; Minus FP takes each day’s FP off first.' })]);
    const draw = () => {
      for (const [d, , x] of days) {
        const c = v['c' + d], f = v['f' + d];
        node['c' + d].setAttribute('y', Y(c).toFixed(1)); node['c' + d].setAttribute('height', (B - Y(c)).toFixed(1));
        node['f' + d].setAttribute('y', Y(f).toFixed(1)); node['f' + d].setAttribute('height', (B - Y(f)).toFixed(1));
        node['h' + d].setAttribute('y', (Y(f) - 6).toFixed(1));
        node['h' + d].setAttribute('aria-valuenow', f.toFixed(3));
      }
      arrRaw.setAttribute('x1', 105); arrRaw.setAttribute('x2', 265);
      arrRaw.setAttribute('y1', Y(v.c1).toFixed(1)); arrRaw.setAttribute('y2', Y(v.c4).toFixed(1));
      const raw = v.c4 - v.c1, mfp = (v.c4 - v.f4) - (v.c1 - v.f1);
      const rb = out.querySelector('.xraw'), mb = out.querySelector('.xmfp');
      rb.textContent = f3(raw); mb.textContent = f3(mfp);
      rb.style.color = css(raw >= 0 ? '--up' : '--down'); mb.style.color = css(mfp >= 0 ? '--up' : '--down');
      if (Math.sign(mfp) !== Math.sign(drawn.mfp || mfp)) { mb.classList.remove('xwiggle'); void mb.offsetWidth; mb.classList.add('xwiggle'); }
      drawn.mfp = mfp;
    };
    const drawn = {};
    for (const [d] of days) {
      const h = node['h' + d];
      let drag = false;
      const at = (e) => { const r = svg.getBoundingClientRect(); return (e.clientY - r.top) * (VH / r.height); };
      h.addEventListener('pointerdown', (e) => { drag = true; try { h.setPointerCapture(e.pointerId); } catch (x) { /* none */ } e.preventDefault(); });
      h.addEventListener('pointermove', (e) => { if (!drag) return; v['f' + d] = clamp(Yinv(at(e)), lo, hi); draw(); });
      h.addEventListener('pointerup', () => { drag = false; });
      h.addEventListener('keydown', (e) => {
        const st = (hi - lo) / 40;
        if (e.key === 'ArrowUp') { v['f' + d] = Math.min(hi, v['f' + d] + st); draw(); e.preventDefault(); }
        if (e.key === 'ArrowDown') { v['f' + d] = Math.max(lo, v['f' + d] - st); draw(); e.preventDefault(); }
      });
    }
    const run = runner();
    async function play() {
      const tk = run.next();
      const f4 = ex.f4;
      await tween(900, (t) => { if (run.live(tk)) { v.f4 = lerp(v.f1, f4, t); draw(); } }, 'back');
    }
    const ctl = el('div', { class: 'xctl' }, [el('button', { type: 'button', class: 'xbtn', text: '▶ Play', onclick: () => play() }),
      el('button', { type: 'button', class: 'xbtn', text: '↺ Reset', onclick: () => { run.next(); Object.assign(v, { c1: ex.c1, f1: ex.f1, c4: ex.c4, f4: ex.f4 }); draw(); } }),
      ex.label ? el('span', { class: 'small muted', text: ex.label }) : null]);
    draw();
    grow(svg, fsOf(host, VW));
    const wrap = el('div', { class: 'xplayer xfpslider' }, [el('div', { class: 'xfprow' }, [svg, out]), ctl]);
    host.appendChild(wrap);
    return { play, el: wrap, set: (patch) => { Object.assign(v, patch); draw(); }, get values() { return Object.assign({}, v); } };
  }

  /* ==================================================================
     The identity sheet, sorted
     ================================================================== */
  function soundSort(host, I, opts) {
    opts = opts || {};
    host.innerHTML = '';
    const seats = (I || {}).seats || {};
    const say = Object.assign({ Click: 'Click', Noise: 'Noise', High: 'High tone', Low: 'Low tone' }, (I || {}).sound_say || {});
    const rats = Object.keys(seats).map(Number).sort((a, b) => a - b);
    if (!rats.length) return null;
    const noisy = (x) => x === 'Click' || x === 'Noise';
    const kind = (r) => (noisy(seats[r].A) && noisy(seats[r].C) ? 'noise' : 'tone');
    const SOUNDS = ['Click', 'Noise', 'High', 'Low'];
    const col = (x) => css({ Click: '--down', Noise: '--arrow', High: '--up', Low: '--ok' }[x] || '--ink-2');
    const VW = 660;
    // On a phone the words grow, so the chips and rows do too, and a chip
    // says High or Low rather than High tone.
    const fs = fsOf(host, VW), g1 = Math.min(fs, 1.4);
    const CW = Math.round(72 * Math.min(fs, 1.3)), CH = Math.round(19 * g1), rowH = Math.round(26 * g1), top = Math.round(40 * g1);
    const chipSay = (s) => (fs > 1.2 ? ({ High: 'High', Low: 'Low' }[s] || say[s]) : say[s]);
    const VH = top + rats.length * rowH + 30;
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', class: 'xsort', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': 'The identity sheet: A, B, C, D, and each sound gathered' });
    const LET = ['A', 'B', 'C', 'D'];
    const gx0 = Math.round(26 + 90 * fs), gstep = (VW - gx0 - CW - 4) / 3;
    const gx = (j) => gx0 + j * gstep;
    const heads = LET.map((x, j) => sv('text', { x: gx(j) + CW / 2, y: top - 12, 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 700, fill: css('--ink-2'), class: 'xshead' },
                                       x + (j % 2 ? '' : ' (opens)')));
    heads.forEach((h) => svg.appendChild(h));
    const sx = (k) => 6 + k * (VW - 12 - CW) / 3;
    const sheads = SOUNDS.map((s, k) => sv('text', { x: sx(k) + CW / 2, y: top - 12, 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 700, fill: col(s), opacity: '0' }, chipSay(s)));
    sheads.forEach((h) => svg.appendChild(h));
    const glow = LET.map((x, j) => sv('rect', { x: gx(j) - 4, y: top - 4, width: CW + 8, height: rats.length * rowH + 4, rx: 6, fill: css('--arrow'), opacity: '0' }));
    glow.forEach((g) => svg.insertBefore(g, svg.firstChild));
    const labels = rats.map((r) => { const t = sv('text', { x: 6, y: 0, 'font-size': 11.5, fill: css('--ink'), 'font-weight': 600 }, 'J' + r); svg.appendChild(t); return t; });
    const tags = rats.map((r) => { const t = sv('text', { x: Math.round(10 + 30 * fs), y: 0, 'font-size': 10, fill: css(kind(r) === 'noise' ? '--down' : '--up'), opacity: '0' },
                                                  kind(r) === 'noise' ? 'noise-first' : 'tone-first'); svg.appendChild(t); return t; });
    const chips = [];
    rats.forEach((r, i) => LET.forEach((x, j) => {
      const s = seats[r][x];
      const g = sv('g', { class: 'xchip', 'data-rat': String(r), 'data-letter': x, 'data-sound': s });
      g.appendChild(sv('rect', { x: 0, y: 0, width: CW, height: CH, rx: 4, fill: col(s), 'fill-opacity': x === 'A' || x === 'C' ? 0.32 : 0.16, stroke: col(s) }));
      const t = sv('text', { x: CW / 2, y: CH * 0.71, 'text-anchor': 'middle', 'font-size': 10.5, fill: css('--ink') }, chipSay(s));
      g.appendChild(t);
      svg.appendChild(g);
      chips.push({ g, t, r, i, j, s, x });
    }));
    // Where everything is, step by step.
    const order0 = rats.slice();
    const orderG = rats.filter((r) => kind(r) === 'noise').concat(rats.filter((r) => kind(r) !== 'noise'));
    const rowY = (r, order) => top + order.indexOf(r) * rowH;
    const pose = (step) => chips.map((c) => {
      if (step < 3) {
        const order = step >= 2 ? orderG : order0;
        return { x: gx(c.j), y: rowY(c.r, order), text: chipSay(c.s) };
      }
      const k = SOUNDS.indexOf(c.s);
      const inCol = chips.filter((z) => z.s === c.s);
      const at = inCol.indexOf(c);
      return { x: sx(k), y: top + at * rowH, text: 'J' + c.r + ' · ' + c.x };
    });
    const place = (P, t, from) => chips.forEach((c, i) => {
      const a = from ? from[i] : P[i], b = P[i];
      c.g.setAttribute('transform', 'translate(' + lerp(a.x, b.x, t).toFixed(1) + ',' + lerp(a.y, b.y, t).toFixed(1) + ')');
      if (t >= 0.5) c.t.textContent = b.text;
    });
    const placeRows = (order, t, from) => rats.forEach((r, i) => {
      const y0 = from ? rowY(r, from) : rowY(r, order), y1 = rowY(r, order);
      labels[i].setAttribute('y', (lerp(y0, y1, t) + CH * 0.71).toFixed(1));
      tags[i].setAttribute('y', (lerp(y0, y1, t) + CH * 0.71).toFixed(1));
    });
    const cap = el('p', { class: 'xcap' });
    const SAY = ['Every rat heard all four sounds, each at a different letter. A and C open its two pairs; B and D close them.',
      'Look down A and C: for four rats both are Click or Noise (blue/purple), for the other four both are a tone.',
      'So the rats fall into two groups: noise-first and tone-first. The Monolith pools all eight by letter.',
      'Gathered by sound instead: each sound comes from a different letter in different rats. That is how tab 6 tests the sounds.'];
    let step = 0, trans = 0;
    const run = runner();
    async function to(k, ms) {
      const my = ++trans;
      const from = pose(step);
      const fromOrder = step >= 2 && step < 3 ? orderG : order0;
      step = k;
      cap.textContent = SAY[k];
      host.dataset.step = String(k);
      glow[0].setAttribute('opacity', k === 1 ? '0.12' : '0'); glow[2].setAttribute('opacity', k === 1 ? '0.12' : '0');
      tags.forEach((t) => t.setAttribute('opacity', k >= 2 && k < 3 ? '1' : '0'));
      const P = pose(k);
      const rowsVisible = k < 3;
      labels.forEach((t) => t.setAttribute('opacity', rowsVisible ? '1' : '0'));
      heads.forEach((h) => h.setAttribute('opacity', rowsVisible ? '1' : '0'));
      sheads.forEach((h) => h.setAttribute('opacity', rowsVisible ? '0' : '1'));
      await tween(ms == null ? 1000 : ms, (t) => { if (my === trans) { place(P, t, from); placeRows(k >= 2 && k < 3 ? orderG : order0, t, fromOrder); } }, 'back');
    }
    async function play() {
      const tk = run.next();
      chips.forEach((c) => c.g.setAttribute('opacity', '0'));
      await to(0, 0);
      for (let i = 0; i < chips.length; i++) {
        if (!run.live(tk)) return;
        const c = chips[i];
        c.g.setAttribute('opacity', '1');
        if (!reduced()) tween(260, (t) => c.g.setAttribute('opacity', t.toFixed(2)), 'out');
        await wait(28);
      }
      for (let k = 1; k < 4; k++) {
        await wait(1500);
        if (!run.live(tk)) return;
        await to(k);
      }
    }
    const ctl = el('div', { class: 'xctl' }, [el('button', { type: 'button', class: 'xbtn', text: '▶ Play', onclick: () => play() }),
      el('div', { class: 'xsteps' }, ['The sheet', 'A and C', 'Two groups', 'By sound'].map((x, k) => el('button', { type: 'button', class: 'xstep', text: x,
        onclick: () => { run.next(); to(k); } })))]);
    grow(svg, fs);
    const wrap = el('div', { class: 'xplayer xsoundsort' }, [svg, cap, ctl]);
    host.appendChild(wrap);
    to(0, 0);
    return { play, el: wrap, to: (k) => { run.next(); return to(k, 0); }, get step() { return step; } };
  }

  return { more, playOnce, numberPlayer, shuffle, chanceBars, pacToy, fpSlider, soundSort, tween, celebrate, signsOf, splits, reduced, onVisible };
})();
