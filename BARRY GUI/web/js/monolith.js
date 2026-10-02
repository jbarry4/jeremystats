/* ==========================================================================
   monolith.js -- the Monolith page (web/monolith.html).

   Every coupling measure from 1 to 55 Hz, Precon1 -> Precon4, pooled over
   rats (backend/monolith.py). One node-edge circuit; to its right the
   controls -- raw or minus FP, state or transition, the window, a slider
   over every frequency with theta, beta and low gamma to snap to, the
   measure, the significance slider (stricter to the right), Granger arrows
   and node power -- and the points of interest, ten and then fifty, each
   of which snaps the controls to show it.

   Click an edge and a ghost of it lifts out of the circuit, its two regions
   turning until they sit level. Click the ghost edge and it opens into what
   it is the average of: one edge per rat. Click a rat and it opens into its
   two days; a day, into every cue pair (and, minus FP, every rest epoch).
   Hover anything for its numbers. The drill-down is one request,
   /api/arc/monolith/entry, which recomputes the entry with the same scalar
   functions every drift uses and says whether they agree with the arrays.

   The arrays are float32 files, the stacked QUANTITIES in C order, shapes in
   the summary: edges (q, window, band, method, pair), power (q, window,
   band, region), pac (q, state window, cell, phase region x amp region).
   ========================================================================== */
'use strict';

window.MONO = (function () {
  const API = '/api/arc/monolith';
  const NS = 'http://www.w3.org/2000/svg';
  const VIEW_KEY = 'barry.monolith.view';
  const Q = { est: 0, p: 1, k: 2, same: 3, se: 4, why: 5 };
  const W = 640, H = 600, CX = 320, CY = 306, RING = 208;
  const LEVELS = [
    ['every tested entry', (p) => isFinite(p)],
    ['p < .05', (p) => p < 0.05],
    ['p < .01', (p) => p < 0.01],
    ['p < .001', (p) => p < 0.001],
    ['p < .0001', (p) => p < 0.0001],
  ];
  const GROUPS = [['Spectral', ['coherence', 'icoh']],
                  ['Correlation', ['raw_cc', 'env_cc', 'env_cc0', 'orth_env']],
                  ['Phase', ['plv', 'ppc', 'pli', 'wpli', 'dwpli']],
                  ['Direction', ['gc_ab', 'gc_ba', 'gc_net']]];
  const LAYERS = [['raw', 'Raw'], ['minus_fp', 'Minus FP']];
  const DIRECTED = { gc_ab: 1, gc_ba: -1, gc_net: 0 };

  const D = { S: null, edges: {}, power: {}, pac: {}, err: null };
  const st = { layer: 'raw', kind: 'state', win: 'cue1', band: 'f08', method: 'coherence',
               level: 1, arrows: false, power: true, sel: null, showAll: false,
               pacWin: 'cue1', pacCell: null, pacPair: null, openMore: {} };

  /* ---------------- small helpers ---------------- */
  const $ = (id) => document.getElementById(id);
  function el(tag, attrs, kids) {
    const n = document.createElement(tag);
    for (const k in (attrs || {})) {
      const v = attrs[k];
      if (v == null || v === false) continue;
      if (k === 'text') n.textContent = v;
      else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const c of [].concat(kids || [])) {
      if (c != null && c !== false) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    }
    return n;
  }
  function sv(tag, attrs, text) {
    const n = document.createElementNS(NS, tag);
    for (const k in (attrs || {})) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  /* `a` toward `b` by t (0..1), for two #rrggbb tokens. Mixed here rather
     than with color-mix() in an SVG fill attribute, which not every
     renderer reads. */
  function mix(a, b, t) {
    const h = (c) => { c = String(c).replace('#', ''); if (c.length === 3) c = c.split('').map((x) => x + x).join('');
      return [0, 2, 4].map((i) => parseInt(c.slice(i, i + 2), 16)); };
    const A = h(a), B = h(b);
    if (A.some(isNaN) || B.some(isNaN)) return a;
    return 'rgb(' + A.map((x, i) => Math.round(x + (B[i] - x) * t)).join(',') + ')';
  }
  function sig(v, d) {
    if (v == null || !isFinite(v)) return '—';
    const a = Math.abs(v);
    const s = a >= 100 ? v.toFixed(0) : a >= 1 ? v.toFixed(2) : a >= 0.01 ? v.toFixed(d || 3)
      : a >= 0.001 ? v.toFixed(4) : a === 0 ? '0' : v.toExponential(1);
    return s;
  }
  const f3 = (v) => (v == null || !isFinite(v)) ? '—' : (v >= 0 ? '+' : '−') + sig(Math.abs(v));
  const fp = (v) => (v == null || !isFinite(v)) ? '—' : (v < 0.001 ? v.toExponential(1) : v.toFixed(3).replace(/^0/, ''));
  const plural = (n, one, many) => n + ' ' + (n === 1 ? one : (many || one + 's'));
  const short = (r) => String(r).replace(/^Left /, 'L ').replace(/^Right /, 'R ');

  function remember() {
    try {
      const keep = {};
      for (const k of ['layer', 'kind', 'win', 'band', 'method', 'level', 'arrows', 'power', 'pacWin']) keep[k] = st[k];
      localStorage.setItem(VIEW_KEY, JSON.stringify(keep));
    } catch (e) { /* per viewer only */ }
  }
  function recall() {
    try { Object.assign(st, JSON.parse(localStorage.getItem(VIEW_KEY) || '{}')); } catch (e) { /* none */ }
  }

  /* ---------------- data ---------------- */
  /* _dev/monolith.html loads this page in a frame and hands it made-up
     data through `MONO_FIXTURE` on itself, so the page can be checked with
     nothing built. Never set in Jarvis. */
  const FIX = (() => {
    try { return window.parent !== window && window.parent.MONO_FIXTURE ? window.parent.MONO_FIXTURE : null; }
    catch (e) { return null; }
  })();
  async function getJSON(path) {
    if (FIX) return FIX.json(path);
    const r = await fetch(API + path, { cache: 'no-cache' });
    let body = null;
    try { body = await r.json(); } catch (e) { /* not JSON */ }
    if (!r.ok || (body && body.ok === false)) throw new Error((body && (body.error || body.why)) || ('HTTP ' + r.status));
    return body;
  }
  async function getArray(name, shape) {
    if (FIX) return FIX.array(name, shape);
    const r = await fetch(API + '/data/' + name, { cache: 'no-cache' });
    if (!r.ok) throw new Error('The Monolith file ' + name + ' could not be read (HTTP ' + r.status + ').');
    const buf = await r.arrayBuffer();
    const want = shape.reduce((a, b) => a * b, 1) * 4;
    if (buf.byteLength !== want) {
      throw new Error(name + ' is ' + buf.byteLength + ' bytes; its shape says ' + want + '.');
    }
    return new Float32Array(buf);
  }
  async function ensureLayer(layer) {
    const S = D.S;
    const jobs = [];
    for (const what of ['edges', 'power', 'pac']) {
      if (D[what][layer]) continue;
      const f = S.files[what + '_' + layer + '.f32'];
      if (!f) continue;
      jobs.push(getArray(what + '_' + layer, f.shape).then((a) => { D[what][layer] = a; }));
    }
    await Promise.all(jobs);
  }

  const dims = () => {
    const S = D.S;
    return { W: S.windows.length, B: S.bands.length, M: S.methods.length, P: S.pairs.length,
             R: S.regions.length, C: S.pac_cells.length };
  };
  function E(layer, q, w, b, m, p) {
    const a = D.edges[layer];
    if (!a) return NaN;
    const d = dims();
    return a[(((q * d.W + w) * d.B + b) * d.M + m) * d.P + p];
  }
  function PW(layer, q, w, b, r) {
    const a = D.power[layer];
    if (!a) return NaN;
    const d = dims();
    return a[((q * d.W + w) * d.B + b) * d.R + r];
  }
  function PAC(layer, q, w, c, op) {
    const a = D.pac[layer];
    if (!a) return NaN;
    const d = dims();
    return a[((q * 4 + w) * d.C + c) * (d.R * d.R) + op];
  }

  const wi = () => D.S.windows.findIndex((w) => w.id === st.win);
  const bi = () => D.S.bands.findIndex((b) => b.id === st.band);
  const mi = () => D.S.methods.findIndex((m) => m.id === st.method);
  const band = () => D.S.bands[bi()];
  const method = () => D.S.methods[mi()];
  const win = () => D.S.windows[wi()];
  const pass = (p) => LEVELS[st.level][1](p);
  const layerSay = (l) => (LAYERS.find((x) => x[0] === l) || [])[1] || l;

  function viewSay() {
    const b = band();
    return win().label + ' · ' + (b.named ? b.label : b.hz + ' Hz') + ' · ' + method().label + ' · ' + layerSay(st.layer);
  }

  /* ---------------- help: the ? marks and "this one" ---------------- */
  const qh = (key) => (window.MONO_HELP ? MONO_HELP.q(key, () => here(key)) : null);
  /* How many of the 1 Hz bands this pair passes p < .05 at, here. */
  const BB_FRAC = 0.6;
  function bbCount(layer, w, m, p) {
    const S = D.S;
    let n = 0, of = 0;
    for (let b = 0; b < S.bands.length; b++) {
      if (S.bands[b].named) continue;
      const pv = E(layer, Q.p, w, b, m, p);
      if (!isFinite(pv)) continue;
      of++;
      if (pv < 0.05) n++;
    }
    return { n, of };
  }
  function broadband(layer, w, m, p) {
    const c = bbCount(layer, w, m, p);
    return c.of >= 20 && c.n >= BB_FRAC * c.of ? c : null;
  }
  function selEntry(mid) {
    if (st.sel == null) return null;
    const S = D.S;
    const m = S.methods.findIndex((x) => x.id === (mid || st.method));
    const w = wi(), b = bi(), p = st.sel;
    const [a, b2] = S.pairs[p];
    return { est: E(st.layer, Q.est, w, b, m, p), p: E(st.layer, Q.p, w, b, m, p), k: E(st.layer, Q.k, w, b, m, p),
             same: E(st.layer, Q.same, w, b, m, p), pair: S.regions[a] + ' – ' + S.regions[b2], a, b: b2, m };
  }
  function entSay(mid, layer) {
    const e = selEntry(mid);
    if (!e) return null;
    const S = D.S;
    const L = layer || st.layer;
    const w = wi(), b = bi();
    const est = E(L, Q.est, w, b, e.m, st.sel), p = E(L, Q.p, w, b, e.m, st.sel);
    const k = E(L, Q.k, w, b, e.m, st.sel), same = E(L, Q.same, w, b, e.m, st.sel);
    const where = win().label + ', ' + (band().named ? band().label : band().hz + ' Hz');
    return e.pair + ' at ' + where + ': ' + S.methods[e.m].label + (isFinite(est) ? ' changed ' + f3(est) : ' was not measured')
      + (isFinite(p) ? ' (p ' + fp(p) + ' uncorrected, ' + same + ' of ' + k + ' rats the same way, ' + layerSay(L) + ').'
        : ' (not tested in ' + layerSay(L) + ').');
  }
  function coverSay(d) {
    if (!d) return null;
    return 'Cue pairs that gave a value (Precon1 · Precon4): ' + (d.rats || []).map((r) => {
      const a = (r.days || {}).Precon1 || {}, b = (r.days || {}).Precon4 || {};
      return 'r' + r.rat + ' ' + (a.of != null ? a.n + '/' + a.of : '—') + ' · ' + (b.of != null ? b.n + '/' + b.of : '—')
        + (a.of_rest != null ? ' (rest ' + a.n_rest + '/' + a.of_rest + ' · ' + b.n_rest + '/' + b.of_rest + ')' : '');
    }).join('; ') + '.';
  }
  function here(key) {
    const S = D.S;
    if (!S) return null;
    if (S.methods.some((m) => m.id === key)) {
      return entSay(key) || 'Click an edge (or a point of interest) to see what ' + S.methods.find((m) => m.id === key).label
        + ' says for it here.';
    }
    const b = band();
    switch (key) {
      case 'measure': return entSay() || null;
      case 'layer': {
        const other = st.layer === 'raw' ? 'minus_fp' : 'raw';
        if (st.sel == null) return 'You are looking at ' + layerSay(st.layer) + '.';
        return entSay(null, st.layer) + (D.edges[other] ? ' ' + entSay(null, other) : '');
      }
      case 'windows': case 'window':
        return 'Now: ' + win().label + ', ' + (st.kind === 'state' ? '10 s' : (b.speed === 'slow' ? '−3 s / +3 s around the boundary'
          : '−1 s / +2 s around the boundary')) + '.';
      case 'frequency': case 'bands':
        return (b.named ? b.label : b.hz + ' Hz: the band ' + sig(b.low) + '–' + sig(b.high) + ' Hz') + ', lags searched up to ±'
          + Math.round(b.lag_s * 1000) + ' ms.';
      case 'sig': case 'circuit': return $('sigsay') ? $('sigsay').textContent : null;
      case 'arrows': return entSay('gc_net');
      case 'power': {
        if (st.sel == null) return null;
        const [a, b2] = S.pairs[st.sel];
        return [a, b2].map((r) => {
          const est = PW(st.layer, Q.est, wi(), bi(), r), p = PW(st.layer, Q.p, wi(), bi(), r);
          return S.regions[r] + ': power ' + f3(est) + ' log10' + (isFinite(p) ? ' (p ' + fp(p) + ')' : '');
        }).join('; ') + '.';
      }
      case 'points': {
        const t = ((S.top || {})[st.layer] || [])[0];
        return t ? 'First: ' + t.a + ' – ' + t.b + ', ' + poiSay(t) + ': ' + f3(t.est) + ', p ' + fp(t.p) + ', ' + t.same + '/' + t.k + ' rats.' : null;
      }
      case 'broadband': case 'spectrum': {
        if (st.sel == null) return null;
        const c = bbCount(st.layer, wi(), mi(), st.sel);
        return selEntry().pair + ' passes p < .05 at ' + c.n + ' of ' + c.of + ' tested frequencies in this window and measure'
          + (c.of >= 20 && c.n >= BB_FRAC * c.of ? ' -- broadband.' : '.');
      }
      case 'pac': case 'pac.circuit':
        return st.pacCell != null ? 'Cell: ' + S.pac_cells[st.pacCell].fp + ' Hz phase × ' + S.pac_cells[st.pacCell].fa + ' Hz amplitude, '
          + (S.windows.find((w) => w.id === st.pacWin) || {}).label + '.' : null;
      case 'verdict': {
        const c = (S.counts || {})[st.layer];
        return c ? layerSay(st.layer) + ': ' + c.p05.toLocaleString() + ' of ' + c.tested.toLocaleString() + ' pass p < .05; chance alone gives about '
          + c.chance_p05.toLocaleString() + '.' : null;
      }
      case 'coverage': return coverSay(GH.detail);
      case 'ghost.pooled': case 'ghost.rats': return GH.detail ? pooledSay(GH.detail) : null;
      case 'ghost.days': case 'ghost.units': {
        const top = GH.stack[GH.stack.length - 1] || {};
        const r = GH.detail && (GH.detail.rats || []).find((x) => x.rat === top.rat);
        return r ? 'r' + r.rat + ': Precon1 ' + sig(r.left) + ' → Precon4 ' + sig(r.right) + ', change ' + f3(r.delta) + '.' : null;
      }
      case 'leaf': return LF.data ? leafSay(LF.data) : null;
      default: return null;
    }
  }
  function pooledSay(d) {
    const P = d.pooled || {};
    const k = (d.rats || []).filter((r) => r.delta != null).length;
    const same = (d.rats || []).filter((r) => r.delta != null && P.est != null && r.delta !== 0 && (r.delta > 0) === (P.est > 0)).length;
    return 'Pooled change ' + f3(P.est) + (P.ci ? ', 95% interval ' + f3(P.ci[0]) + ' to ' + f3(P.ci[1]) : '')
      + ', p ' + fp(P.p) + ' (Hartung–Knapp t on ' + (P.df == null ? '—' : P.df) + ' df, uncorrected); ' + same + ' of ' + k + ' rats the same way.';
  }

  /* ---------------- tooltip ---------------- */
  function tip(evt, lines) {
    const t = $('tip');
    t.innerHTML = '';
    lines.filter((ln) => ln).forEach((ln, i) => t.appendChild(i === 0 ? el('b', { text: ln }) : el('div', { class: 'row', text: ln })));
    t.style.display = 'block';
    moveTip(evt);
  }
  function moveTip(evt) {
    const t = $('tip');
    const w = t.offsetWidth, h = t.offsetHeight;
    let x = evt.clientX + 14, y = evt.clientY + 14;
    if (x + w > innerWidth - 8) x = Math.max(8, innerWidth - w - 8);
    if (y + h > innerHeight - 8) y = Math.max(8, evt.clientY - h - 14);
    t.style.left = x + 'px';
    t.style.top = y + 'px';
  }
  const hideTip = () => { $('tip').style.display = 'none'; };
  function hover(node, lines) {
    node.addEventListener('mouseenter', (e) => tip(e, typeof lines === 'function' ? lines() : lines));
    node.addEventListener('mousemove', moveTip);
    node.addEventListener('mouseleave', hideTip);
  }

  /* ---------------- layout ---------------- */
  function layout() {
    const S = D.S;
    const app = $('app');
    app.innerHTML = '';
    // The tour: it starts by itself on a first visit (js/monolith_tour.js);
    // this button brings it back any time.
    app.appendChild(el('div', { class: 'pagehead' }, [
      el('h1', { text: 'The Monolith: Precon1 → Precon4, every measure, 1–55 Hz' }),
      el('button', { type: 'button', id: 'monoTour', class: 'tourbtn', text: 'Take the tour',
                     title: 'A walk through one real lead, from the circuit down to the recording',
                     onclick: () => { if (window.MONO_TOUR) window.MONO_TOUR.start(); } }),
    ]));
    app.appendChild(el('p', { class: 'lede', text: 'Each rat compared with itself, Precon4 minus Precon1, '
      + 'both cue pairings pooled; the changes pooled over rats (DerSimonian–Laird, Hartung–Knapp t on '
      + 'k − 1 df, at least ' + S.min_rats + ' rats). Every p on this page is uncorrected: this is for '
      + 'sifting, and the counts below say how many to expect by chance.' }));
    app.appendChild(el('div', { class: 'card', id: 'verdict' }));
    app.appendChild(el('p', { class: 'small muted guide-link' }, ['Every ? opens what that thing is, with a strong and a no-effect example '
      + 'made by this analysis’s own engine. All of it in one place: ', el('a', { href: 'monolith-guide.html', target: '_blank', rel: 'noopener', text: 'the Guide' }), '.']));
    app.appendChild(el('div', { class: 'grid' }, [
      el('div', { class: 'col-circ' }, [
        el('div', { class: 'card circ' }, [
          el('div', { class: 'hrow' }, [el('h2', { id: 'ctitle' }), qh('circuit')]),
          el('div', { class: 'crumbs', id: 'crumbs' }),
          el('div', { class: 'circ-svg', id: 'circwrap', style: 'position:relative' }, [
            el('div', { id: 'circ' }),
          ]),
          el('div', { class: 'gstats', id: 'gstats', hidden: 'hidden' }),
          el('div', { id: 'circempty' }),
          el('div', { class: 'legend', id: 'legend' }),
          el('p', { class: 'small muted', id: 'circsay' }),
        ]),
        el('div', { class: 'card spec', id: 'speccard' }, [
          el('div', { class: 'hrow' }, [el('h2', { id: 'spectitle' }), qh('spectrum')]), el('div', { id: 'spec' }),
          el('p', { class: 'small muted', id: 'specsay' }),
        ]),
        el('div', { class: 'card', id: 'paccard' }),
      ]),
      el('div', { class: 'col-ctl' }, [el('div', { class: 'card', id: 'controls' })]),
      el('div', { class: 'col-poi' }, [el('div', { class: 'card', id: 'poi' })]),
    ]));
    app.appendChild(el('div', { class: 'card', id: 'damage' }, [el('p', { class: 'loading', text: 'Counting what was lost…' })]));
    app.appendChild(el('div', { class: 'card foot', id: 'foot' }));
  }

  /* ---------------- the controls ---------------- */
  function seg(list, cur, pick, cls) {
    return el('div', { class: 'seg' + (cls ? ' ' + cls : ''), role: 'group' }, list.map(([id, label, title]) =>
      el('button', { type: 'button', 'aria-pressed': String(cur === id), 'data-id': id, text: label,
                     title: title || null, onclick: () => pick(id) })));
  }
  function set(patch) {
    const before = JSON.stringify([st.layer, st.win, st.band, st.method]);
    Object.assign(st, patch);
    remember();
    const after = JSON.stringify([st.layer, st.win, st.band, st.method]);
    renderAll(before !== after);
  }

  function lab(text, key, id) {
    return el('span', { class: 'lab hrow', id: id || null }, [el('span', { text }), qh(key)]);
  }
  function renderControls() {
    const S = D.S;
    const host = $('controls');
    host.innerHTML = '';
    host.appendChild(el('h2', { text: 'View' }));
    host.appendChild(el('div', { class: 'ctl' }, [lab('Layer', 'layer'),
      seg(LAYERS, st.layer, (id) => switchLayer(id), 'big')]));
    host.appendChild(el('div', { class: 'ctl' }, [lab('Windows', 'windows'),
      seg([['state', 'State'], ['transition', 'Transition']], st.kind, (id) => {
        if (id === st.kind) return;
        const first = S.windows.find((w) => w.kind === id);
        set({ kind: id, win: first.id });
      }, 'big')]));
    host.appendChild(el('div', { class: 'ctl' }, [lab('Window', 'window'),
      seg(S.windows.filter((w) => w.kind === st.kind).map((w) => [w.id, w.label]), st.win,
          (id) => set({ win: id }))]));

    // Frequency: a slider over every whole hertz, and the three named bands.
    const b = band();
    const slider = el('input', { type: 'range', min: '1', max: '55', step: '1', id: 'freq',
      value: String(b.named ? Math.round((b.low + b.high) / 2) : b.hz),
      'aria-label': 'Frequency, 1 to 55 Hz', 'aria-valuetext': b.named ? b.label : b.hz + ' Hz' });
    slider.addEventListener('input', (e) => set({ band: 'f' + String(e.target.value).padStart(2, '0') }));
    const lag = b.lag_s * 1000;
    const winLen = st.kind === 'state' ? '10 s windows'
      : (b.speed === 'slow' ? '−3 s / +3 s around each boundary' : '−1 s / +2 s around each boundary');
    host.appendChild(el('div', { class: 'ctl' }, [
      lab('Frequency — ' + (b.named ? b.label : b.hz + ' Hz'), 'frequency'),
      slider,
      el('div', { class: 'ticks', 'aria-hidden': 'true' }, ['1', '12', '25', '40', '55'].map((t) => el('span', { text: t }))),
      el('div', { class: 'hrow' }, [seg(S.bands.filter((x) => x.named).map((x) => [x.id, x.label.replace(/ \d.*$/, ''), x.label]), st.band,
          (id) => set({ band: id })), qh('bands')]),
      el('div', { class: 'readout', id: 'freqsay', text: (b.named ? b.label : b.hz + ' Hz, band '
        + sig(b.low) + '–' + sig(b.high) + ' Hz') + ' · lag up to ±' + Math.round(lag) + ' ms · ' + winLen }),
    ]));

    // The measure, grouped; each with its own ?.
    const mbox = el('div', { class: 'ctl' }, [lab('Measure', 'measure')]);
    for (const [g, ids] of GROUPS) {
      mbox.appendChild(el('div', { class: 'mgroup', text: g }));
      mbox.appendChild(el('div', { class: 'seg', role: 'group' }, ids.map((id) => {
        const m = S.methods.find((x) => x.id === id);
        return el('span', { class: 'mchip' }, [
          el('button', { type: 'button', 'aria-pressed': String(st.method === id), 'data-id': id, text: m.label,
                         title: m.say, onclick: () => set({ method: id }) }), qh(id)]);
      })));
    }
    host.appendChild(mbox);

    const lv = el('input', { type: 'range', min: '0', max: String(LEVELS.length - 1), step: '1', id: 'sig',
      value: String(st.level), 'aria-label': 'Significance: right is stricter',
      'aria-valuetext': LEVELS[st.level][0] });
    lv.addEventListener('input', (e) => set({ level: Number(e.target.value) }));
    host.appendChild(el('div', { class: 'ctl' }, [
      lab('Show edges — stricter →', 'sig'), lv,
      el('div', { class: 'ticks', 'aria-hidden': 'true' }, ['all', '.05', '.01', '.001', '.0001'].map((t) => el('span', { text: t }))),
      el('div', { class: 'readout', id: 'sigsay' }),
    ]));
    const tg = (key, label, title, help) => {
      const box = el('input', { type: 'checkbox', id: 'tg-' + key });
      box.checked = !!st[key];
      box.addEventListener('change', () => set({ [key]: box.checked }));
      return el('div', { class: 'hrow' }, [el('label', { class: 'toggle', title: title }, [box, label]), qh(help)]);
    };
    host.appendChild(el('div', { class: 'ctl' }, [
      tg('arrows', 'Granger arrows', 'Draw the net Granger direction (A→B minus B→A) as arrows, wherever it passes the slider', 'arrows'),
      tg('power', 'Node power', 'Colour each region by its own power change at this frequency', 'power'),
    ]));
  }

  async function switchLayer(id) {
    if (id === st.layer) return;
    try {
      await ensureLayer(id);
    } catch (e) {
      D.err = e.message;
    }
    set({ layer: id });
  }

  /* ---------------- the circuit ---------------- */
  function positions() {
    const regs = D.S.regions;
    const pos = {};
    regs.forEach((r, i) => {
      const a = -Math.PI / 2 + (i + 0.5) * (2 * Math.PI / regs.length);
      pos[i] = { x: CX + RING * Math.cos(a), y: CY + RING * Math.sin(a), a };
    });
    return pos;
  }

  function viewEdges() {
    const S = D.S;
    const w = wi(), b = bi(), m = mi();
    const out = [];
    for (let p = 0; p < S.pairs.length; p++) {
      const est = E(st.layer, Q.est, w, b, m, p);
      const pv = E(st.layer, Q.p, w, b, m, p);
      out.push({ p, est, pv, k: E(st.layer, Q.k, w, b, m, p), same: E(st.layer, Q.same, w, b, m, p),
                 se: E(st.layer, Q.se, w, b, m, p), why: E(st.layer, Q.why, w, b, m, p),
                 tested: isFinite(pv), shown: isFinite(pv) && pass(pv) });
    }
    return out;
  }

  /* A directed edge: the curve from a's centre towards b, stopped where its
     head begins, and the head, sized to the line, its tip at the edge of
     b's circle. A fixed-size marker on the curve's end was narrower than a
     thick line and sat under the node, so a strong arrow read as a blunt
     line (2026-10-02). `rEnd` is b's radius with its outline. */
  function arrowGeom(pa, q, pb, w, rEnd) {
    const at = (t) => {
      const u = 1 - t;
      return { x: u * u * pa.x + 2 * u * t * q.x + t * t * pb.x, y: u * u * pa.y + 2 * u * t * q.y + t * t * pb.y };
    };
    const L = Math.max(11, 2.2 * w + 6), hw = Math.max(5.5, 1.45 * w + 2.5);
    // The last t still `r` from b's centre, walking back from the end.
    const tAt = (r) => {
      for (let t = 1; t > 0; t -= 0.002) {
        const p = at(t);
        if (Math.hypot(p.x - pb.x, p.y - pb.y) >= r) return t;
      }
      return 0;
    };
    const tTip = tAt(rEnd + 3), tBase = tAt(rEnd + 3 + L);
    const T = at(tTip), B = at(tBase);
    const c = { x: pa.x + tBase * (q.x - pa.x), y: pa.y + tBase * (q.y - pa.y) };
    const len = Math.hypot(T.x - B.x, T.y - B.y) || 1;
    const ux = (T.x - B.x) / len, uy = (T.y - B.y) / len;
    const f = (v) => v.toFixed(2);
    return {
      d: 'M' + f(pa.x) + ',' + f(pa.y) + ' Q' + f(c.x) + ',' + f(c.y) + ' ' + f(B.x) + ',' + f(B.y),
      head: f(T.x) + ',' + f(T.y) + ' ' + f(B.x - uy * hw) + ',' + f(B.y + ux * hw) + ' ' + f(B.x + uy * hw) + ',' + f(B.y - ux * hw),
      tip: T, base: B, halfWidth: hw,
    };
  }

  function edgeLines(e) {
    const S = D.S;
    const [a, b] = S.pairs[e.p];
    const m = method();
    const dir = m.directed ? ' (' + (st.method === 'gc_net'
      ? (e.est >= 0 ? short(S.regions[a]) + ' → ' + short(S.regions[b]) : short(S.regions[b]) + ' → ' + short(S.regions[a]))
      : st.method === 'gc_ab' ? short(S.regions[a]) + ' → ' + short(S.regions[b])
      : short(S.regions[b]) + ' → ' + short(S.regions[a])) + ')' : '';
    const bb = e.tested ? broadband(st.layer, wi(), mi(), e.p) : null;
    return [S.regions[a] + ' – ' + S.regions[b], viewSay(),
      'change ' + f3(e.est) + (isFinite(e.se) ? ' (SE ' + sig(e.se) + ')' : '') + dir,
      e.tested ? 'p = ' + fp(e.pv) + ' (uncorrected), ' + e.same + ' of ' + e.k + ' rats this way'
        : 'not tested: ' + (S.why[String(e.why)] || 'no rat has it on both days'),
      bb ? 'Broadband: passes at ' + bb.n + ' of ' + bb.of + ' frequencies here -- check the traces for a non-neural cause.' : '',
      'Click to lift it out and open it up.'];
  }

  function renderCircuit() {
    const S = D.S;
    const host = $('circ');
    host.innerHTML = '';
    $('ctitle').textContent = viewSay();
    const edges = viewEdges();
    const shown = edges.filter((e) => e.shown);
    const tested = edges.filter((e) => e.tested);
    const max = Math.max(1e-12, ...tested.map((e) => Math.abs(e.est)));
    const pos = positions();
    const svg = sv('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', id: 'circsvg',
      'aria-label': 'Circuit: ' + shown.length + ' edges drawn of ' + tested.length + ' tested' });
    svg.appendChild(sv('circle', { cx: CX, cy: CY, r: RING, fill: 'none', stroke: css('--ring'), 'stroke-width': 1 }));
    const NODE_EDGE = 12.5;              // a node's radius (11) and half its outline
    const directed = method().directed;
    shown.sort((x, y) => Math.abs(x.est) - Math.abs(y.est));
    for (const e of shown) {
      let [a, b] = S.pairs[e.p];
      if (directed) {
        const flip = st.method === 'gc_ba' || (st.method === 'gc_net' && e.est < 0);
        if (flip) [a, b] = [b, a];
      }
      const pa = pos[a], pb = pos[b];
      const mx = (pa.x + pb.x) / 2, my = (pa.y + pb.y) / 2;
      const qx = CX + (mx - CX) * 0.35, qy = CY + (my - CY) * 0.35;
      const wpx = 1.4 + 6.5 * Math.abs(e.est) / max;
      const up = st.method === 'gc_net' ? true : e.est >= 0;
      const col = up ? css('--up') : css('--down');
      const g = directed ? arrowGeom(pa, { x: qx, y: qy }, pb, wpx, NODE_EDGE) : null;
      const path = sv('path', { d: g ? g.d : 'M' + pa.x + ',' + pa.y + ' Q' + qx + ',' + qy + ' ' + pb.x + ',' + pb.y,
        class: 'edge' + (st.sel === e.p ? ' sel' : ''), stroke: col,
        'stroke-width': wpx.toFixed(2), 'stroke-opacity': 0.9, tabindex: '0', 'data-pair': String(e.p),
        'data-to': g ? String(b) : null, 'aria-label': edgeLines(e).slice(0, 4).join(', ') });
      hover(path, () => edgeLines(e));
      const pick = () => { st.sel = e.p; hideTip(); renderCircuit(); renderSpectrum(); renderTop(); renderPac(); openGhost(e.p); };
      path.addEventListener('click', pick);
      path.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(); } });
      svg.appendChild(path);
      if (g) {
        const head = sv('polygon', { points: g.head, class: 'ahead' + (st.sel === e.p ? ' sel' : ''), fill: col,
                                     'data-pair': String(e.p), 'data-to': String(b) });
        hover(head, () => edgeLines(e));
        head.addEventListener('click', pick);
        svg.appendChild(head);
      }
    }
    // Granger arrows over a non-Granger view.
    let nArrows = 0;
    if (st.arrows && !directed) {
      const gn = S.methods.findIndex((m) => m.id === 'gc_net');
      const w = wi(), b = bi();
      const arr = [];
      for (let p = 0; p < S.pairs.length; p++) {
        const g = E(st.layer, Q.est, w, b, gn, p), gp = E(st.layer, Q.p, w, b, gn, p);
        if (isFinite(gp) && pass(gp)) arr.push({ p, g, gp });
      }
      const gmax = Math.max(1e-12, ...arr.map((x) => Math.abs(x.g)));
      for (const x of arr) {
        let [a, b2] = S.pairs[x.p];
        if (x.g < 0) [a, b2] = [b2, a];
        const pa = pos[a], pb = pos[b2];
        const mx = (pa.x + pb.x) / 2, my = (pa.y + pb.y) / 2;
        const qx = CX + (mx - CX) * 0.62, qy = CY + (my - CY) * 0.62;
        const aw = 1.2 + 2.6 * Math.abs(x.g) / gmax;
        const g = arrowGeom(pa, { x: qx, y: qy }, pb, aw, NODE_EDGE);
        svg.appendChild(sv('path', { d: g.d, class: 'arrowp', stroke: css('--arrow'), 'stroke-width': aw.toFixed(2),
          'stroke-dasharray': '5 3', 'data-arrow': String(x.p), 'data-to': String(b2) }));
        svg.appendChild(sv('polygon', { points: g.head, class: 'arrowh', fill: css('--arrow'), 'data-arrow': String(x.p), 'data-to': String(b2) }));
        nArrows++;
      }
    }
    // Nodes, coloured by their own power change.
    const w = wi(), b = bi();
    const pw = S.regions.map((_r, r) => ({ est: PW(st.layer, Q.est, w, b, r), p: PW(st.layer, Q.p, w, b, r),
      k: PW(st.layer, Q.k, w, b, r), same: PW(st.layer, Q.same, w, b, r) }));
    const pmax = Math.max(1e-12, ...pw.filter((x) => isFinite(x.p)).map((x) => Math.abs(x.est)));
    const anyEdge = (r) => edges.some((e) => e.tested && S.pairs[e.p].indexOf(r) >= 0);
    S.regions.forEach((name, r) => {
      const p = pos[r];
      const grey = !anyEdge(r) && !isFinite(pw[r].p);
      const x = pw[r];
      let fill = css('--node');
      if (st.power && isFinite(x.est) && !grey) {
        const t = Math.min(1, Math.abs(x.est) / pmax);
        fill = mix(css('--surface-2'), x.est >= 0 ? css('--up') : css('--down'), 0.15 + 0.85 * t);
      }
      const strong = st.power && isFinite(x.p) && pass(x.p);
      const c = sv('circle', { cx: p.x, cy: p.y, r: grey ? 7 : 11, class: 'node', 'data-region': String(r),
        fill: grey ? 'none' : fill, stroke: grey ? css('--node-grey') : strong ? css('--ink') : css('--surface'),
        'stroke-width': strong ? 3 : 2 });
      hover(c, () => [name, grey ? 'Not measured here: no rat has this region usable on both days.'
        : 'power ' + f3(x.est) + ' log10 (× ' + (isFinite(x.est) ? Math.pow(10, x.est).toFixed(2) : '—') + ')',
        isFinite(x.p) ? 'p = ' + fp(x.p) + ' (uncorrected), ' + x.same + ' of ' + x.k + ' rats this way'
          : (grey ? '' : 'power change not tested here'), viewSay().split(' · ').slice(0, 2).join(' · ')]);
      svg.appendChild(c);
      const lx = CX + (RING + 26) * Math.cos(p.a), ly = CY + (RING + 26) * Math.sin(p.a);
      const anchor = Math.abs(Math.cos(p.a)) < 0.2 ? 'middle' : (Math.cos(p.a) > 0 ? 'start' : 'end');
      svg.appendChild(sv('text', { x: lx, y: ly + 4, 'text-anchor': anchor, class: 'node-l' + (grey ? ' grey' : '') },
        name + (grey ? ' (not measured)' : '')));
    });
    host.appendChild(svg);
    const empty = $('circempty');
    empty.innerHTML = '';
    if (!tested.length) {
      empty.appendChild(el('p', { class: 'empty', text: 'Nothing was tested in this view: no region pair had at least '
        + S.min_rats + ' rats with it on both days.' }));
    } else if (!shown.length) {
      empty.appendChild(el('p', { class: 'empty', text: 'No edge passes “' + LEVELS[st.level][0]
        + '” here. Move the significance slider left to see weaker ones.' }));
    }
    $('sigsay').textContent = shown.length + ' of ' + tested.length + ' tested region pairs pass '
      + LEVELS[st.level][0] + (st.level ? ' (uncorrected)' : '') + (nArrows ? ' · ' + plural(nArrows, 'Granger arrow') : '');
    const lg = $('legend');
    lg.innerHTML = '';
    lg.appendChild(el('span', {}, [el('i', { style: 'border-color:' + css('--up') }), directed ? 'drive, and its direction' : 'stronger on Precon4']));
    if (!directed) lg.appendChild(el('span', {}, [el('i', { style: 'border-color:' + css('--down') }), 'weaker on Precon4']));
    if (st.arrows && !directed) lg.appendChild(el('span', {}, [el('i', { style: 'border-color:' + css('--arrow') + ';border-top-style:dashed' }), 'Granger net, A → B']));
    if (st.power) {
      lg.appendChild(el('span', {}, [el('b', { class: 'sw', style: 'background:' + css('--up') }), 'louder']));
      lg.appendChild(el('span', {}, [el('b', { class: 'sw', style: 'background:' + css('--down') }), 'quieter (node power)']));
    }
    lg.appendChild(el('span', { text: 'Thicker is a bigger change. A ringed node’s power change passes the slider.' }));
    $('circsay').textContent = (method().say || '') + (st.method === 'gc_net' ? ' An arrow points the way the net drive grew.' : '');
    if (GH.pair != null) drawGhostStatic();
  }

  /* ---------------- the spectrum strip ---------------- */
  function renderSpectrum() {
    const S = D.S;
    const host = $('spec');
    host.innerHTML = '';
    const bins = S.bands.filter((b) => !b.named);
    const w = wi(), m = mi();
    const counts = bins.map((b) => {
      const k = S.bands.indexOf(b);
      let n = 0;
      for (let p = 0; p < S.pairs.length; p++) {
        const pv = E(st.layer, Q.p, w, k, m, p);
        if (isFinite(pv) && pass(pv)) n++;
      }
      return n;
    });
    const sel = st.sel;
    const line = sel == null ? null : bins.map((b) => {
      const k = S.bands.indexOf(b);
      return { est: E(st.layer, Q.est, w, k, m, sel), p: E(st.layer, Q.p, w, k, m, sel) };
    });
    const SW = 640, SH = 150, l = 30, r = 12, t = 10, bt = 118;
    const X = (hz) => l + (hz - 1) / 54 * (SW - l - r);
    const svg = sv('svg', { viewBox: '0 0 ' + SW + ' ' + SH, role: 'img', id: 'specsvg',
      'aria-label': 'How many region pairs pass the slider at each frequency' });
    const cmax = Math.max(1, ...counts);
    bins.forEach((b, i) => {
      const h = (bt - t) * counts[i] / cmax;
      const rect = sv('rect', { x: X(b.hz) - 4, y: bt - h, width: 8, height: Math.max(0.5, h),
        fill: css('--line-2'), 'data-hz': String(b.hz) });
      hover(rect, [b.hz + ' Hz', counts[i] + ' region pairs pass ' + LEVELS[st.level][0],
        line ? 'selected pair: ' + f3(line[i].est) + ', p ' + fp(line[i].p) : 'Click to go there.']);
      svg.appendChild(rect);
    });
    if (st.kind === 'transition') {
      svg.appendChild(sv('line', { x1: X(12.5), x2: X(12.5), y1: t, y2: bt, stroke: css('--ink-3'), 'stroke-dasharray': '3 3' }));
      svg.appendChild(sv('text', { x: X(12.5) - 4, y: t + 10, 'text-anchor': 'end', 'font-size': 10, fill: css('--ink-3') }, '−3/+3 s'));
      svg.appendChild(sv('text', { x: X(12.5) + 4, y: t + 10, 'font-size': 10, fill: css('--ink-3') }, '−1/+2 s'));
    }
    if (line) {
      const vmax = Math.max(1e-12, ...line.filter((x) => isFinite(x.est)).map((x) => Math.abs(x.est)));
      const Y = (v) => (t + bt) / 2 - v / vmax * (bt - t) / 2 * 0.9;
      svg.appendChild(sv('line', { x1: l, x2: SW - r, y1: Y(0), y2: Y(0), stroke: css('--ink-3'), 'stroke-width': 0.5 }));
      let d = '';
      line.forEach((x, i) => { if (isFinite(x.est)) d += (d ? ' L' : 'M') + X(bins[i].hz) + ',' + Y(x.est); });
      if (d) svg.appendChild(sv('path', { d, fill: 'none', stroke: css('--ink'), 'stroke-width': 1.5 }));
      line.forEach((x, i) => {
        if (!isFinite(x.est)) return;
        const ok = isFinite(x.p) && pass(x.p);
        svg.appendChild(sv('circle', { cx: X(bins[i].hz), cy: Y(x.est), r: ok ? 3.4 : 2,
          fill: ok ? (x.est >= 0 ? css('--up') : css('--down')) : css('--surface'), stroke: css('--ink-2'), 'stroke-width': 0.8 }));
      });
    }
    const b = band();
    if (b.named) {
      svg.appendChild(sv('rect', { x: X(Math.max(1, b.low)), y: t, width: X(Math.min(55, b.high)) - X(Math.max(1, b.low)),
        height: bt - t, fill: css('--focus'), 'fill-opacity': 0.12 }));
    } else {
      svg.appendChild(sv('line', { x1: X(b.hz), x2: X(b.hz), y1: t, y2: bt, stroke: css('--focus'), 'stroke-width': 2 }));
    }
    for (const hz of [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]) {
      svg.appendChild(sv('text', { x: X(hz), y: bt + 16, 'text-anchor': 'middle', 'font-size': 10.5, fill: css('--ink-3') }, String(hz)));
    }
    svg.appendChild(sv('text', { x: SW - r, y: SH - 4, 'text-anchor': 'end', 'font-size': 10.5, fill: css('--ink-3') }, 'Hz'));
    svg.addEventListener('click', (e) => {
      const box = svg.getBoundingClientRect();
      const x = (e.clientX - box.left) / box.width * SW;
      const hz = Math.max(1, Math.min(55, Math.round((x - l) / (SW - l - r) * 54 + 1)));
      set({ band: 'f' + String(hz).padStart(2, '0') });
    });
    host.appendChild(svg);
    $('spectitle').textContent = 'Across frequencies · ' + win().label + ' · ' + method().label + ' · ' + layerSay(st.layer);
    const bbSel = sel != null ? broadband(st.layer, w, m, sel) : null;
    if (bbSel) {
      host.appendChild(el('p', { class: 'bbnote hrow' }, [el('span', { text: 'Broadband: the selected pair passes at ' + bbSel.n + ' of '
        + bbSel.of + ' frequencies here. Oscillatory coupling rarely does; look at its cue pairs’ traces.' }), qh('broadband')]));
    }
    $('specsay').textContent = 'Bars: how many region pairs pass ' + LEVELS[st.level][0] + ' at each frequency.'
      + (sel != null ? ' Line: ' + S.regions[S.pairs[sel][0]] + ' – ' + S.regions[S.pairs[sel][1]]
        + ' at every frequency, a filled dot where it passes.' : ' Click an edge to draw its line.')
      + ' Click anywhere to go to that frequency.';
  }

  /* ---------------- points of interest ---------------- */
  function poiSay(t) {
    const S = D.S;
    const w = S.windows.find((x) => x.id === t.w);
    const b = S.bands.find((x) => x.id === t.band);
    const m = S.methods.find((x) => x.id === t.m);
    return w.label + ' · ' + (b.named ? b.label : b.hz + ' Hz') + ' · ' + m.label;
  }
  function renderTop() {
    const S = D.S;
    const host = $('poi');
    host.innerHTML = '';
    const list = (S.top || {})[st.layer] || [];
    const n = st.showAll ? list.length : Math.min(10, list.length);
    host.appendChild(el('div', { class: 'hrow' }, [el('h2', { text: (st.showAll ? 'Top ' + list.length : 'Top 10') + ' points of interest · '
      + layerSay(st.layer) }), qh('points')]));
    host.appendChild(el('p', { class: 'small muted', text: S.points_rule + '. Click one to snap the view to it.' }));
    const ol = el('ol', { class: 'top', id: 'toplist' });
    list.slice(0, n).forEach((t) => {
      const pair = t.a + ' – ' + t.b;
      const li = el('li', { class: st.sel === t.pair && t.w === st.win && t.band === st.band && t.m === st.method ? 'sel' : null,
        tabindex: '0', 'data-rank': String(t.rank) }, [
        el('span', { class: 'rk', text: String(t.rank) }),
        el('span', { class: 'pr' }, [pair, el('span', { class: 'chip' + (t.same === t.k ? ' all' : ''),
          text: t.same + '/' + t.k + ' rats' }),
          (() => { const bb = broadband(st.layer, t.wi, t.mi, t.pair);
                   return bb ? el('span', { class: 'chip bb', title: 'Passes at ' + bb.n + ' of ' + bb.of + ' frequencies in this window and measure',
                                            text: 'broadband' }) : null; })()]),
        el('span', { class: 'bs num', text: poiSay(t) + ': ' + f3(t.est) + ', p ' + fp(t.p) }),
        t.n_more ? el('span', { class: 'mr' }, [
          el('button', { type: 'button', text: '+' + t.n_more + ' more like it', onclick: (e) => {
            e.stopPropagation();
            st.openMore[t.rank] = !st.openMore[t.rank];
            renderTop();
          } })]) : null,
        t.n_more && st.openMore[t.rank] ? el('ul', {}, t.more.map((x) => el('li', {}, [
          el('button', { type: 'button', class: 'linkish', text: poiSay(Object.assign({}, x)) + ': ' + f3(x.est) + ', p ' + fp(x.p)
            + ', ' + x.same + '/' + x.k, onclick: (e) => { e.stopPropagation(); go(Object.assign({}, x, { pair: t.pair })); } }),
        ])).concat(t.n_more > t.more.length ? [el('li', { text: 'and ' + (t.n_more - t.more.length) + ' more' })] : [])) : null,
      ]);
      li.addEventListener('click', () => go(t));
      li.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(t); });
      li.addEventListener('mouseenter', () => {
        if (t.w !== st.win || t.band !== st.band || t.m !== st.method) return;
        document.querySelectorAll('#circsvg .edge[data-pair="' + t.pair + '"], #circsvg .ahead[data-pair="' + t.pair + '"]')
          .forEach((x) => x.classList.add('hl'));
      });
      li.addEventListener('mouseleave', () => {
        document.querySelectorAll('#circsvg .hl').forEach((x) => x.classList.remove('hl'));
      });
      ol.appendChild(li);
    });
    if (!list.length) ol.appendChild(el('li', { class: 'empty', text: 'No entry in this layer has p < .05.' }));
    host.appendChild(ol);
    if (list.length > 10) {
      host.appendChild(el('button', { class: 'more-btn', type: 'button', id: 'showall',
        text: st.showAll ? 'Show the top 10' : 'Show all ' + list.length,
        onclick: () => { st.showAll = !st.showAll; renderTop(); } }));
    }
  }
  function go(t) {
    const S = D.S;
    const w = S.windows.find((x) => x.id === t.w);
    let level = st.level;
    if (!(isFinite(t.p) && LEVELS[level][1](t.p))) {
      level = 1;
      for (let i = LEVELS.length - 1; i >= 0; i--) if (LEVELS[i][1](t.p)) { level = i; break; }
    }
    closeGhost(true);
    st.sel = t.pair;
    set({ kind: w.kind, win: t.w, band: t.band, method: t.m, level });
  }

  /* ---------------- PAC ---------------- */
  function renderPac() {
    const S = D.S;
    const host = $('paccard');
    host.innerHTML = '';
    host.appendChild(el('div', { class: 'hrow' }, [el('h2', { text: 'Phase–amplitude coupling · ' + layerSay(st.layer) }), qh('pac')]));
    if (!D.pac[st.layer]) {
      host.appendChild(el('p', { class: 'empty', text: 'No PAC was built for this layer.' }));
      return;
    }
    const states = S.windows.filter((w) => w.kind === 'state');
    if (states.findIndex((w) => w.id === st.pacWin) < 0) st.pacWin = 'cue1';
    host.appendChild(el('p', { class: 'small muted', text: 'Measured in the four 10 s state windows (and rest): '
      + 'phase from 2–12 Hz in one region, amplitude around 15–50 Hz in another or the same one (Tort’s '
      + 'modulation index). Shown: the change Precon1 → Precon4. A cell with no colour cannot carry its sidebands.' }));
    host.appendChild(el('div', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Window' }),
      seg(states.map((w) => [w.id, w.label]), st.pacWin, (id) => { st.pacWin = id; remember(); renderPac(); })]));
    const pw = states.findIndex((w) => w.id === st.pacWin);
    const R = S.regions.length;
    let pair = st.sel != null ? S.pairs[st.sel] : st.pacPair;
    const top = (S.pac_top || {})[st.layer] || [];
    if (!pair && top.length) {
      pair = [Math.floor(top[0].op / R), top[0].op % R];
      if (pair[0] === pair[1]) pair = [pair[0], (pair[0] + 1) % R];
    }
    if (!pair) pair = [0, 1];
    const [a, b] = pair;
    const combos = [[a, a], [a, b], [b, a], [b, b]];
    const cells = S.pac_cells;
    const fps = [...new Set(cells.map((c) => c.fp))];
    const fas = [...new Set(cells.map((c) => c.fa))];
    let vmax = 1e-12;
    for (const [ph, am] of combos) {
      for (let c = 0; c < cells.length; c++) {
        const v = PAC(st.layer, Q.est, pw, c, ph * R + am);
        if (isFinite(v)) vmax = Math.max(vmax, Math.abs(v));
      }
    }
    if (st.pacCell == null && top.length) st.pacCell = top[0].cell;
    const grids = el('div', { class: 'pacgrids' });
    for (const [ph, am] of combos) {
      const GW = 300, GH = 190, l = 34, t = 8, r = 6, bo = 30;
      const cw = (GW - l - r) / fps.length, ch = (GH - t - bo) / fas.length;
      const svg = sv('svg', { viewBox: '0 0 ' + GW + ' ' + GH, role: 'img',
        'aria-label': 'PAC: phase in ' + S.regions[ph] + ', amplitude in ' + S.regions[am] });
      cells.forEach((cell, c) => {
        const x = l + fps.indexOf(cell.fp) * cw, y = t + (fas.length - 1 - fas.indexOf(cell.fa)) * ch;
        const v = PAC(st.layer, Q.est, pw, c, ph * R + am), p = PAC(st.layer, Q.p, pw, c, ph * R + am);
        const k = PAC(st.layer, Q.k, pw, c, ph * R + am), same = PAC(st.layer, Q.same, pw, c, ph * R + am);
        const ok = isFinite(p) && pass(p);
        let fill = css('--chip');
        if (isFinite(v) && cell.amp_band) {
          const tt = Math.min(1, Math.abs(v) / vmax);
          fill = mix(css('--surface'), v >= 0 ? css('--up') : css('--down'), 0.08 + 0.8 * tt);
        } else if (!cell.amp_band) fill = 'none';
        const rect = sv('rect', { x: x + 0.5, y: y + 0.5, width: cw - 1, height: ch - 1, fill, class: 'cell',
          stroke: st.pacCell === c ? css('--focus') : ok ? css('--ink') : css('--line'),
          'stroke-width': st.pacCell === c ? 2 : ok ? 1.5 : 0.5, 'data-cell': String(c) });
        hover(rect, () => [short(S.regions[ph]) + ' phase ' + cell.fp + ' Hz → ' + short(S.regions[am]) + ' amplitude ' + cell.fa + ' Hz',
          cell.amp_band ? 'amplitude band ' + sig(cell.amp_band[0]) + '–' + sig(cell.amp_band[1]) + ' Hz' : 'not measured: the amplitude band cannot carry the sidebands',
          'change in MI ' + f3(v) + (isFinite(p) ? ', p ' + fp(p) + ' (uncorrected), ' + same + '/' + k + ' rats' : ''),
          'Click for the PAC circuit at this cell.']);
        rect.addEventListener('click', () => { st.pacCell = c; renderPac(); });
        svg.appendChild(rect);
      });
      fps.forEach((f, i) => { if (f % 2 === 0) svg.appendChild(sv('text', { x: l + (i + 0.5) * cw, y: GH - bo + 13, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, String(f))); });
      fas.forEach((f, i) => svg.appendChild(sv('text', { x: l - 4, y: t + (fas.length - 1 - i + 0.5) * ch + 3, 'text-anchor': 'end', 'font-size': 10, fill: css('--ink-3') }, String(f))));
      svg.appendChild(sv('text', { x: l + (GW - l - r) / 2, y: GH - 3, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, 'phase Hz'));
      grids.appendChild(el('div', { class: 'pacgrid' }, [
        el('div', { class: 'cap', text: ph === am ? short(S.regions[ph]) + ' with itself' : short(S.regions[ph]) + ' phase → ' + short(S.regions[am]) + ' amplitude' }),
        svg]));
    }
    // The PAC circuit at one cell.
    const circ = el('div', {});
    if (st.pacCell != null) {
      const c = st.pacCell, cell = cells[c];
      const PWd = 300, PH = 290, pcx = 150, pcy = 145, pr = 100;
      const svg = sv('svg', { viewBox: '0 0 ' + PWd + ' ' + PH, role: 'img', id: 'pacsvg',
        'aria-label': 'PAC circuit at ' + cell.fp + ' Hz phase and ' + cell.fa + ' Hz amplitude' });
      const pos = S.regions.map((_n, i) => {
        const ang = -Math.PI / 2 + (i + 0.5) * (2 * Math.PI / R);
        return { x: pcx + pr * Math.cos(ang), y: pcy + pr * Math.sin(ang), a: ang };
      });
      const live = [];
      for (let ph = 0; ph < R; ph++) for (let am = 0; am < R; am++) {
        if (ph === am) continue;
        const p = PAC(st.layer, Q.p, pw, c, ph * R + am);
        if (isFinite(p) && pass(p)) live.push({ ph, am, v: PAC(st.layer, Q.est, pw, c, ph * R + am), p });
      }
      const m2 = Math.max(1e-12, ...live.map((x) => Math.abs(x.v)));
      for (const x of live) {
        const a2 = pos[x.ph], b2 = pos[x.am];
        const mx = (a2.x + b2.x) / 2, my = (a2.y + b2.y) / 2;
        const pwid = 1 + 3 * Math.abs(x.v) / m2;
        const pcol = x.v >= 0 ? css('--up') : css('--down');
        const g = arrowGeom(a2, { x: pcx + (mx - pcx) * 0.4, y: pcy + (my - pcy) * 0.4 }, b2, pwid, 9);
        const path = sv('path', { d: g.d, fill: 'none', stroke: pcol, 'stroke-width': pwid.toFixed(2), class: 'edge',
                                  'data-ph': String(x.ph), 'data-to': String(x.am) });
        const say = [short(S.regions[x.ph]) + ' phase → ' + short(S.regions[x.am]) + ' amplitude', 'change ' + f3(x.v) + ', p ' + fp(x.p)];
        hover(path, say);
        svg.appendChild(path);
        const head = sv('polygon', { points: g.head, class: 'ahead', fill: pcol, 'data-ph': String(x.ph), 'data-to': String(x.am) });
        hover(head, say);
        svg.appendChild(head);
      }
      S.regions.forEach((name, i) => {
        const v = PAC(st.layer, Q.est, pw, c, i * R + i), p = PAC(st.layer, Q.p, pw, c, i * R + i);
        const ok = isFinite(p) && pass(p);
        const node = sv('circle', { cx: pos[i].x, cy: pos[i].y, r: 8, fill: ok ? (v >= 0 ? css('--up') : css('--down')) : css('--node'),
          stroke: css('--surface'), 'stroke-width': 2 });
        hover(node, [name, 'its own PAC here: ' + f3(v) + (isFinite(p) ? ', p ' + fp(p) : '')]);
        svg.appendChild(node);
        const lx = pcx + (pr + 16) * Math.cos(pos[i].a), ly = pcy + (pr + 16) * Math.sin(pos[i].a);
        svg.appendChild(sv('text', { x: lx, y: ly + 3, 'text-anchor': Math.abs(Math.cos(pos[i].a)) < 0.2 ? 'middle' : Math.cos(pos[i].a) > 0 ? 'start' : 'end',
          'font-size': 9.5, fill: css('--ink-2') }, short(name)));
      });
      circ.appendChild(qh('pac.circuit'));
      circ.appendChild(el('div', { class: 'cap small', text: 'The PAC circuit at ' + cell.fp + ' Hz phase × ' + cell.fa
        + ' Hz amplitude: arrows from the phase region to the amplitude region, wherever the change passes the slider ('
        + live.length + '). A filled node: its own PAC changed.' }));
      circ.appendChild(svg);
    }
    const tops = el('div', {}, [el('h3', { text: 'Strongest PAC changes' }),
      el('ol', { class: 'top' }, top.slice(0, 6).map((x, i) => {
        const li = el('li', { tabindex: '0' }, [el('span', { class: 'rk', text: String(i + 1) }),
          el('span', { class: 'pr' }, [short(x.phase) + ' → ' + short(x.amp), el('span', { class: 'chip' + (x.same === x.k ? ' all' : ''), text: x.same + '/' + x.k })]),
          el('span', { class: 'bs num', text: S.windows[x.wi].label + ' · ' + x.fp + ' × ' + x.fa + ' Hz: ' + f3(x.est) + ', p ' + fp(x.p) })]);
        li.addEventListener('click', () => {
          st.pacWin = S.windows[x.wi].id; st.pacCell = x.cell;
          st.pacPair = [Math.floor(x.op / R), x.op % R];
          if (st.pacPair[0] === st.pacPair[1]) st.pacPair[1] = (st.pacPair[0] + 1) % R;
          st.sel = null; renderAll(false);
        });
        return li;
      }))]);
    host.appendChild(el('div', { class: 'pacrow' }, [grids, el('div', {}, [circ, tops])]));
  }

  /* ---------------- the verdict and the foot ---------------- */
  function renderVerdict() {
    const S = D.S;
    const v = $('verdict');
    v.innerHTML = '';
    v.appendChild(el('div', { class: 'hrow' }, [el('h2', { text: 'What it found' }), qh('verdict')]));
    for (const [id, name] of LAYERS) {
      const c = (S.counts || {})[id];
      if (!c) continue;
      const top = String(Math.max(...Object.keys(c.agree || {}).map(Number).concat([0])));
      const ag = (c.agree || {})[top] || {};
      v.appendChild(el('p', {}, [el('strong', { text: name + ': ' }),
        c.tested.toLocaleString() + ' entries tested; ' + c.p05.toLocaleString() + ' have p < .05, where about '
        + c.chance_p05.toLocaleString() + ' would by chance alone; ' + c.p001.toLocaleString() + ' have p < .001. '
        + (ag.tested ? 'All ' + top + ' rats the same way: ' + ag.all_same.toLocaleString() + ' (chance: about '
          + ag.chance_all_same.toLocaleString() + ').' : '')]));
    }
    if (DMG.data) {
      const c = DMG.data.whole.cue;
      v.appendChild(el('p', { class: 'small' }, [el('strong', { text: 'Lost on the way: ' }),
        c.lost + ' of ' + c.total + ' cue pairs entirely, ' + c.partial + ' partly. ',
        el('button', { type: 'button', class: 'linkish', text: 'See what was lost, rat by rat',
                       onclick: () => { const t = $('damage'); if (t) t.scrollIntoView({ block: 'start' }); } })]));
    }
    v.appendChild(el('p', { class: 'small muted', text: 'Every p here is uncorrected, by design: the Monolith is for '
      + 'finding leads, and with this many tests a good share of the p < .05 entries are chance. On made-up data '
      + 'with no change at all and days the size of these, 5.5% of entries came out p < .05 (tools/check_monolith.py). '
      + 'Trust a lead that is consistent across neighbouring frequencies, windows and measures, with every rat the same way.' }));
  }
  function renderFoot() {
    const S = D.S;
    const f = $('foot');
    f.innerHTML = '';
    f.appendChild(el('p', { text: 'Built ' + S.built_at + ' from run ' + S.run.rid + ' (array '
      + (S.run.arrays || []).join(', ') + ', ' + S.run.n_tasks + ' tasks, in ' + S.run.dest + '), code '
      + String(S.run.code || 'unrecorded').slice(0, 12) + ', manifest ' + S.manifest.digest + '. '
      + (S.missing_tasks.length ? S.missing_tasks.length + ' tasks had not answered: ' + S.missing_tasks.join(', ') + '. ' : '')
      + (S.n_refusals ? S.n_refusals + ' windows or units were refused on the node (clipping, short records, no clock); they are left out, never filled. ' : '') }));
    f.appendChild(el('p', { text: 'Windows: state ' + S.lengths.state + '; transitions ' + S.lengths.slow + ', ' + S.lengths.fast + '. '
      + 'Bands: every whole hertz ±15% (never under ±0.5 Hz), cut at 55 Hz.' }));
    const dl = el('dl', { class: 'meth' });
    for (const m of S.methods) { dl.appendChild(el('dt', { text: m.label })); dl.appendChild(el('dd', { text: m.say })); }
    f.appendChild(el('details', {}, [el('summary', { text: 'What each measure is' }), dl]));
    if ((S.manifest.notes || []).length) {
      f.appendChild(el('details', {}, [el('summary', { text: 'Notes on the recordings' }),
        el('ul', {}, S.manifest.notes.map((n) => el('li', { text: n })))]));
    }
  }

  /* ==================================================================
     The ghost: one edge lifted out, then opened up
     ================================================================== */
  const GX0 = 110, GX1 = 530, GY = 200;
  const GH = { pair: null, detail: null, err: null, stack: [], ghostSvg: null, from: null, lifted: false, info: null };
  const reduced = () => { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } };
  /* requestAnimationFrame, with a timer that always lands the last frame:
     a page in the background, or a headless browser on virtual time, may
     never give the frames. */
  function tween(ms, frame, done) {
    if (reduced()) ms = 0;
    let over = false;
    const t0 = performance.now();
    const finish = () => { if (over) return; over = true; frame(1); if (done) done(); };
    if (!ms) { finish(); return; }
    const step = (now) => {
      if (over) return;
      const t = Math.min(1, (now - t0) / ms);
      frame(1 - Math.pow(1 - t, 3));
      if (t < 1) requestAnimationFrame(step); else finish();
    };
    requestAnimationFrame(step);
    setTimeout(finish, ms + 120);
  }

  function ghostLayer() {
    let g = document.getElementById('ghostsvg');
    if (!g) {
      g = sv('svg', { id: 'ghostsvg', class: 'ghost', viewBox: '0 0 ' + W + ' ' + H,
        style: 'position:absolute;left:0;top:0;width:100%;height:100%' });
      $('circwrap').appendChild(g);
    }
    return g;
  }

  async function openGhost(pair) {
    const S = D.S;
    const pos = positions();
    const [a, b] = S.pairs[pair];
    GH.pair = pair;
    GH.stack = [{ lv: 'pooled' }];
    GH.detail = null;
    GH.err = null;
    GH.info = null;
    GH.at = [wi(), bi(), mi(), pair];
    GH.layer = st.layer;
    const A0 = pos[a], B0 = pos[b];
    const m0 = { x: (A0.x + B0.x) / 2, y: (A0.y + B0.y) / 2 };
    const th0 = Math.atan2(B0.y - A0.y, B0.x - A0.x);
    const r0 = Math.hypot(B0.x - A0.x, B0.y - A0.y) / 2;
    // Turn the shorter way until level: B ends on the right, or the left.
    let th1 = Math.abs(th0) <= Math.PI / 2 ? 0 : (th0 > 0 ? Math.PI : -Math.PI);
    GH.flip = th1 !== 0;
    const m1 = { x: CX, y: GY }, r1 = (GX1 - GX0) / 2;
    const g = ghostLayer();
    g.innerHTML = '';
    const bd = sv('rect', { x: 0, y: 0, width: W, height: H, class: 'ghost-bd', opacity: 0 });
    g.appendChild(bd);
    const line = sv('line', { stroke: css('--ink'), 'stroke-width': 4, 'stroke-linecap': 'round' });
    const na = sv('circle', { r: 12, fill: css('--node'), stroke: css('--surface'), 'stroke-width': 2 });
    const nb = sv('circle', { r: 12, fill: css('--node'), stroke: css('--surface'), 'stroke-width': 2 });
    const la = sv('text', { class: 'gname', 'text-anchor': 'middle' }, S.regions[a]);
    const lb = sv('text', { class: 'gname', 'text-anchor': 'middle' }, S.regions[b]);
    [line, na, nb, la, lb].forEach((n) => g.appendChild(n));
    renderCrumbs();
    const want = getJSON('/entry?what=edges&layer=' + st.layer + '&at=' + GH.at.join(','))
      .then((d) => { GH.detail = d; }).catch((e) => { GH.err = e.message; });
    await new Promise((resolve) => tween(560, (t) => {
      const th = th0 + (th1 - th0) * t;
      const r = r0 + (r1 - r0) * t;
      const mx = m0.x + (m1.x - m0.x) * t, my = m0.y + (m1.y - m0.y) * t;
      const ax = mx - r * Math.cos(th), ay = my - r * Math.sin(th);
      const bx = mx + r * Math.cos(th), by = my + r * Math.sin(th);
      bd.setAttribute('opacity', String(t));
      line.setAttribute('x1', ax); line.setAttribute('y1', ay);
      line.setAttribute('x2', bx); line.setAttribute('y2', by);
      na.setAttribute('cx', ax); na.setAttribute('cy', ay);
      nb.setAttribute('cx', bx); nb.setAttribute('cy', by);
      la.setAttribute('x', ax); la.setAttribute('y', ay - 20);
      lb.setAttribute('x', bx); lb.setAttribute('y', by - 20);
    }, resolve));
    GH.lifted = true;
    await want;
    if (GH.pair !== pair) return;
    drawLevel(true);
  }

  function closeGhost(quiet) {
    const g = document.getElementById('ghostsvg');
    GH.pair = null;
    GH.detail = null;
    GH.lifted = false;
    renderCrumbs();
    renderGhostStats();
    if (!g) return;
    if (quiet) { g.remove(); return; }
    tween(220, (t) => g.setAttribute('opacity', String(1 - t)), () => g.remove());
  }

  function drawGhostStatic() {
    // The circuit was redrawn under an open ghost: the view changed. The
    // ghost follows the view -- same pair, the entry the view now shows.
    if (GH.pair == null || !GH.lifted) return;
    const at = [wi(), bi(), mi(), GH.pair];
    if (at.join(',') !== GH.at.join(',') || GH.layer !== st.layer) {
      GH.at = at;
      GH.layer = st.layer;
      GH.stack = [{ lv: 'pooled' }];
      GH.detail = null;
      GH.info = null;
      drawLevel(false);
      getJSON('/entry?what=edges&layer=' + st.layer + '&at=' + at.join(','))
        .then((d) => { GH.detail = d; drawLevel(false); })
        .catch((e) => { GH.err = e.message; drawLevel(false); });
    }
  }

  function renderCrumbs() {
    const host = $('crumbs');
    if (!host) return;
    host.innerHTML = '';
    if (GH.pair == null) return;
    const names = { pooled: 'Pooled', rats: 'Rats' };
    GH.stack.forEach((s, i) => {
      if (i) host.appendChild(el('span', { class: 'sep', text: '›' }));
      const label = s.lv === 'pooled' ? names.pooled : s.lv === 'rats' ? names.rats
        : s.lv === 'days' ? 'r' + s.rat : s.day;
      host.appendChild(el('button', { type: 'button', text: label, 'aria-current': i === GH.stack.length - 1 ? 'true' : null,
        onclick: () => { GH.stack = GH.stack.slice(0, i + 1); GH.info = null; drawLevel(true); } }));
    });
    host.appendChild(el('span', { class: 'sep', text: ' ' }));
    host.appendChild(el('button', { type: 'button', text: 'Close ✕', title: 'Close (Esc)', onclick: () => closeGhost(false) }));
    if (GH.info) host.appendChild(el('span', { class: 'small muted', text: GH.info }));
  }

  /* What one level shows: [{key, label, value, width, color, dash, leaf, tip, onpick}] and the
     parent's value, for the number line. */
  function levelItems() {
    const S = D.S;
    const d = GH.detail;
    const top = GH.stack[GH.stack.length - 1];
    const ink = css('--ink'), ink3 = css('--ink-3'), up = css('--up'), down = css('--down');
    const minus = GH.layer === 'minus_fp';
    if (!d) return { items: [], parent: null, say: GH.err ? 'Could not read this entry: ' + GH.err : 'Reading every rat, day and cue pair…' };
    if (top.lv === 'pooled') {
      const P = d.pooled || {};
      const k = (d.rats || []).filter((r) => r.delta != null).length;
      const same = (d.rats || []).filter((r) => r.delta != null && P.est != null && r.delta !== 0 && (r.delta > 0) === (P.est > 0)).length;
      return { parent: null, say: 'The pooled change. Click the edge to open it into its rats.', items: [{
        key: 'pooled', label: 'pooled ' + f3(P.est) + ' · p ' + fp(P.p) + ' · ' + same + '/' + k + ' rats',
        value: P.est, width: 5, color: (P.est || 0) >= 0 ? up : down,
        tip: ['Pooled over rats', viewSay(), 'change ' + f3(P.est) + (P.se != null ? ' (SE ' + sig(P.se) + ')' : ''),
          'p = ' + fp(P.p) + ' (uncorrected), t on ' + (P.df == null ? '—' : P.df) + ' df, τ² ' + sig(P.tau2),
          d.agree === false ? 'The arrays and this recomputation disagree — report it.' : 'Recomputed with drift.pool_rats + hk_test: agrees with the arrays.',
          'Click to open it into its rats.'],
        onpick: () => push({ lv: 'rats' }) }] };
    }
    if (top.lv === 'rats') {
      const wmax = Math.max(1e-9, ...(d.rats || []).map((r) => r.weight || 0));
      return { parent: (d.pooled || {}).est, say: 'Each rat’s change, Precon4 − Precon1. Thicker carries more weight in the pool. Click a rat for its two days.',
        items: (d.rats || []).map((r) => r.delta == null ? {
          key: 'r' + r.rat, label: 'r' + r.rat + ' —', value: null, width: 1.2, color: ink3, dash: '4 4', leaf: true,
          tip: ['r' + r.rat, 'Left out of this entry: ' + (r.why || 'no value')] } : {
          key: 'r' + r.rat, label: 'r' + r.rat + ' ' + f3(r.delta), value: r.delta,
          width: 1.4 + 4.2 * (r.weight || 0) / wmax, color: r.delta >= 0 ? up : down,
          tip: ['r' + r.rat, 'change ' + f3(r.delta) + (r.v != null ? ' (SE ' + sig(Math.sqrt(r.v)) + ')' : ' (no SE: one usable value on a day)'),
            'Precon1 ' + sig(r.left) + ' → Precon4 ' + sig(r.right),
            'weight in the pool ' + (r.weight != null ? Math.round(100 * r.weight) + '%' : '—'),
            'Click for its two days.'],
          onpick: () => push({ lv: 'days', rat: r.rat }) }) };
    }
    const rat = (d.rats || []).find((r) => r.rat === top.rat) || {};
    if (top.lv === 'days') {
      return { parent: rat.delta, say: 'r' + rat.rat + ': ' + (minus ? 'each day’s cue value less its rest value.' : 'each day’s mean over its cue pairs, both pairings.')
        + ' Click a day for every cue pair' + (minus ? ' and rest epoch.' : '.'),
        items: ['Precon1', 'Precon4'].map((day) => {
          const s = (rat.days || {})[day] || {};
          const v = s.x;
          return { key: day, label: day + ' ' + sig(v) + (minus && s.cue != null ? ' = ' + sig(s.cue) + ' − ' + sig(s.rest) : ''),
            value: v, width: 3, color: day === 'Precon1' ? ink3 : ink,
            tip: [ 'r' + rat.rat + ' · ' + day, minus ? 'cue ' + sig(s.cue) + ' (n ' + s.n + ') − rest ' + sig(s.rest) + ' (n ' + s.n_rest + ') = ' + sig(v)
              : 'mean ' + sig(v) + ' over ' + plural(s.n || 0, 'cue pair'),
              s.se2 != null ? 'SE ' + sig(Math.sqrt(s.se2)) : 'no SE (one usable value)', 'Click for each cue pair.'],
            onpick: () => push({ lv: 'units', rat: rat.rat, day }) };
        }) };
    }
    // units
    const s = (rat.days || {})[top.day] || {};
    const items = (s.units || []).map((u) => ({
      key: u.id, label: u.id + ' ' + sig(u.v), value: u.v, width: 1.8, leaf: true,
      color: top.day === 'Precon1' ? ink3 : ink, dash: u.v == null ? '3 4' : null,
      tip: ['r' + rat.rat + ' · ' + top.day + ' · ' + u.id, u.label + ' (' + u.cue + ')',
        u.v == null ? 'Not measured: ' + (u.why || 'no value in this window') : 'value ' + sig(u.v),
        u.wires ? 'read on CSC ' + (u.wires[0] >= 0 ? u.wires[0] : '—') + ' and CSC ' + (u.wires[1] >= 0 ? u.wires[1] : '—') : '',
        'Click to see its traces and how each number was made.'],
      onopen: () => openLeaf(rat.rat, top.day, u.id) }));
    for (const e of (minus ? (s.rest_units || []) : [])) {
      items.push({ key: e.id, label: e.id + ' ' + sig(e.v) + ' rest', value: e.v, width: 1.4, leaf: true,
        color: css('--arrow'), dash: '5 3',
        tip: ['r' + rat.rat + ' · ' + top.day + ' · rest ' + e.id, e.label + ' (' + e.run + ')',
          e.v == null ? 'Not measured: ' + (e.why || 'no value') : 'value ' + sig(e.v),
          'Click to see its traces.'],
        onopen: () => openLeaf(rat.rat, top.day, e.id) });
    }
    return { parent: s.cue, say: 'r' + rat.rat + ' · ' + top.day + ': every cue pair' + (minus ? ' and, dashed, every rest epoch' : '')
      + '. The line below is the day’s mean' + (minus ? ' over cue pairs' : '') + '.', items };
  }

  function push(s) {
    GH.stack.push(s);
    GH.info = null;
    drawLevel(true, true);
  }
  /* Back up the ghost to `depth` levels (1 is the pooled edge), as the
     crumbs do. */
  function ghostTo(depth) {
    if (GH.pair == null || GH.stack.length <= depth) return;
    GH.stack = GH.stack.slice(0, Math.max(1, depth));
    GH.info = null;
    drawLevel(true);
  }

  function arcPath(c) {
    return 'M' + GX0 + ',' + GY + ' Q' + CX + ',' + (GY + c) + ' ' + GX1 + ',' + GY;
  }

  function drawLevel(animate, deeper) {
    if (GH.pair == null) return;
    const S = D.S;
    const g = ghostLayer();
    g.innerHTML = '';
    g.removeAttribute('opacity');
    const [a, b] = S.pairs[GH.pair];
    const left = GH.flip ? b : a, right = GH.flip ? a : b;
    g.appendChild(sv('rect', { x: 0, y: 0, width: W, height: H, class: 'ghost-bd' }));
    const L = levelItems();
    const N = L.items.length;
    const spread = N <= 1 ? 0 : Math.min(165, 20 + 11 * N);
    const target = L.items.map((_x, i) => N <= 1 ? 0 : -spread + 2 * spread * i / (N - 1));
    const arcs = [];
    const labels = [];
    L.items.forEach((it, i) => {
      const path = sv('path', { d: arcPath(animate ? 0 : target[i]), class: 'garc' + (it.leaf && !it.onopen ? ' leaf' : ''),
        stroke: it.color, 'stroke-width': it.width.toFixed(2), 'stroke-dasharray': it.dash || null,
        tabindex: it.onpick || it.onopen ? '0' : null, 'data-key': it.key, role: it.onpick || it.onopen ? 'button' : null,
        'aria-label': it.tip ? it.tip.join(', ') : it.label });
      if (it.tip) hover(path, it.tip);
      const pick = () => {
        hideTip();
        if (it.onpick) {
          const keep = path;
          tween(deeper === false ? 0 : 260, (t) => {
            arcs.forEach((p, j) => {
              if (p === keep) p.setAttribute('d', arcPath(target[j] * (1 - t)));
              else p.setAttribute('opacity', String(1 - t));
            });
            labels.forEach((x) => x.setAttribute('opacity', String(1 - t)));
          }, () => it.onpick());
        } else if (it.onopen) {
          it.onopen();
        } else if (it.tip) {
          GH.info = it.tip.slice(0, 3).join(' · ');
          renderCrumbs();
        }
      };
      path.addEventListener('click', pick);
      path.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } });
      g.appendChild(path);
      arcs.push(path);
      const side = N <= 1 ? 0 : (i % 2 ? 1 : -1);
      const tt = 0.5 + side * 92 / (GX1 - GX0);
      const lab = sv('text', { x: CX + side * 92, y: GY + 2 * tt * (1 - tt) * target[i] - 5, 'text-anchor': 'middle',
        class: 'gl', opacity: animate ? 0 : 1 }, it.label);
      g.appendChild(lab);
      labels.push(lab);
    });
    // The two regions, level.
    for (const [x, r] of [[GX0, left], [GX1, right]]) {
      g.appendChild(sv('circle', { cx: x, cy: GY, r: 12, class: 'gnode', fill: css('--node'), stroke: css('--surface'), 'stroke-width': 2 }));
      g.appendChild(sv('text', { x, y: GY - 20, class: 'gname', 'text-anchor': 'middle' }, S.regions[r]));
    }
    // The number line under it.
    const vals = L.items.map((x) => x.value).filter((v) => v != null && isFinite(v));
    if (L.parent != null && isFinite(L.parent)) vals.push(L.parent);
    if (vals.length) {
      const zero = GH.stack[GH.stack.length - 1].lv === 'rats' || GH.stack.length === 1;
      if (zero) vals.push(0);
      let lo = Math.min(...vals), hi = Math.max(...vals);
      if (hi - lo < 1e-12) { lo -= 1; hi += 1; }
      const pad = (hi - lo) * 0.08;
      lo -= pad; hi += pad;
      const y = 420, x0 = 70, x1 = 570;
      const X = (v) => x0 + (v - lo) / (hi - lo) * (x1 - x0);
      g.appendChild(sv('line', { x1: x0, x2: x1, y1: y, y2: y, stroke: css('--line-2') }));
      g.appendChild(sv('text', { x: x0, y: y + 16, class: 'gl', 'text-anchor': 'start' }, sig(lo)));
      g.appendChild(sv('text', { x: x1, y: y + 16, class: 'gl', 'text-anchor': 'end' }, sig(hi)));
      if (zero && lo < 0 && hi > 0) g.appendChild(sv('line', { x1: X(0), x2: X(0), y1: y - 10, y2: y + 10, stroke: css('--ink-3') }));
      if (L.parent != null && isFinite(L.parent)) {
        g.appendChild(sv('line', { x1: X(L.parent), x2: X(L.parent), y1: y - 16, y2: y + 16, stroke: css('--ink'), 'stroke-width': 3 }));
      }
      L.items.forEach((it) => {
        if (it.value == null || !isFinite(it.value)) return;
        const dot = sv('circle', { cx: X(it.value), cy: y, r: 5, fill: it.color, 'fill-opacity': 0.85, stroke: css('--surface') });
        if (it.tip) hover(dot, it.tip);
        g.appendChild(dot);
      });
    }
    // The whole sentence, wrapped -- never cut short.
    let line = '', yy = 470;
    for (const wd of L.say.split(' ')) {
      if (line && (line + ' ' + wd).length > 92) {
        g.appendChild(sv('text', { x: CX, y: yy, 'text-anchor': 'middle', class: 'gl gsay' }, line));
        line = wd;
        yy += 15;
      } else line = line ? line + ' ' + wd : wd;
    }
    if (line) g.appendChild(sv('text', { x: CX, y: yy, 'text-anchor': 'middle', class: 'gl gsay' }, line));
    renderCrumbs();
    renderGhostStats();
    if (animate) {
      tween(460, (t) => {
        arcs.forEach((p, i) => p.setAttribute('d', arcPath(target[i] * t)));
        labels.forEach((x) => x.setAttribute('opacity', String(t)));
      });
    }
  }

  document.addEventListener('keydown', (e) => {
    if (LF.open) {
      if (e.key === 'Escape') { closeLeaf(); e.preventDefault(); }
      else if (e.key === 'ArrowLeft') { stepLeaf(-1); e.preventDefault(); }
      else if (e.key === 'ArrowRight') { stepLeaf(1); e.preventDefault(); }
      return;
    }
    if (e.key === 'Escape' && GH.pair != null) closeGhost(false);
  });

  /* ==================================================================
     The ghost's numbers: each level's own picture, under the circuit
     ================================================================== */
  const LEVEL_SAY = { pooled: 'The pooled edge: each rat’s Precon1 → Precon4', rats: 'One edge per rat: the forest plot',
                      days: 'One rat’s two days: every cue pair', units: 'One day: every cue pair' };
  function dayGroups(r, days) {
    const G = window.MONO_FIGS;
    const out = [];
    for (const day of days) {
      const s = (r.days || {})[day] || {};
      out.push({ name: day + ' cue', day, kind: 'cue', units: s.units || [], values: (s.units || []).map((u) => u.v),
                 mean: s.cue, se: s.cue_se2 != null ? Math.sqrt(s.cue_se2) : null });
      if (GH.layer === 'minus_fp') {
        out.push({ name: day + ' rest', day, kind: 'rest', units: s.rest_units || [], values: (s.rest_units || []).map((u) => u.v),
                   mean: s.rest, se: s.rest_se2 != null ? Math.sqrt(s.rest_se2) : null, color: G.css('--arrow') });
      }
    }
    return out;
  }
  function renderGhostStats() {
    const host = $('gstats');
    if (!host) return;
    host.innerHTML = '';
    if (GH.pair == null || !GH.detail || !window.MONO_FIGS) { host.hidden = true; return; }
    host.hidden = false;
    const G = window.MONO_FIGS;
    const d = GH.detail;
    const top = GH.stack[GH.stack.length - 1] || { lv: 'pooled' };
    host.appendChild(el('div', { class: 'hrow' }, [el('h3', { text: LEVEL_SAY[top.lv] }), qh('ghost.' + top.lv)]));
    if (top.lv === 'pooled') {
      host.appendChild(G.slope((d.rats || []).filter((r) => r.delta != null).map((r) => ({ rat: 'r' + r.rat, left: r.left, right: r.right })),
                               { w: 560, h: 200 }));
      host.appendChild(el('p', { class: 'small', text: pooledSay(d) }));
    } else if (top.lv === 'rats') {
      host.appendChild(G.forest((d.rats || []).map((r) => ({ rat: 'r' + r.rat, delta: r.delta, ci: r.ci, weight: r.weight, why: r.why })),
                                { est: (d.pooled || {}).est, ci: (d.pooled || {}).ci }, { w: 560 }));
      host.appendChild(el('p', { class: 'small', text: pooledSay(d) }));
    } else {
      const r = (d.rats || []).find((x) => x.rat === top.rat) || {};
      const days = top.lv === 'days' ? ['Precon1', 'Precon4'] : [top.day];
      const groups = dayGroups(r, days);
      host.appendChild(G.dots(groups, {
        w: 560, h: 190,
        tip: (node, gi, i) => {
          const u = groups[gi].units[i] || {};
          hover(node, ['r' + r.rat + ' · ' + groups[gi].day + ' · ' + u.id, (u.label || '') + (u.cue ? ' (' + u.cue + ')' : u.run ? ' (' + u.run + ')' : ''),
            u.v == null ? 'Not measured: ' + (u.why || 'no value') : 'value ' + sig(u.v), 'Click to see its traces.']);
        },
        onDot: (gi, i) => { const u = groups[gi].units[i]; if (u) openLeaf(r.rat, groups[gi].day, u.id); },
      }));
      host.appendChild(el('p', { class: 'small', text: 'Each dot is one ' + (GH.layer === 'minus_fp' ? 'cue pair or rest epoch' : 'cue pair')
        + '; the bar is the mean and the whisker its standard error. A hollow dot at the bottom gave no value. Click any dot for its traces.' }));
    }
    host.appendChild(el('p', { class: 'small muted hrow' }, [el('span', { text: coverSay(d) }), qh('coverage')]));
  }

  /* ==================================================================
     One cue pair, down to its traces (read from the VACC copy)
     ================================================================== */
  const LF = { open: false, rat: null, day: null, unit: null, data: null, err: null, seq: 0, at: null, layer: null };
  function pacCellNow() {
    if (st.pacCell != null) return st.pacCell;
    const S = D.S;
    const i = S.pac_cells.findIndex((c) => c.fp === 6 && c.fa === 40);
    return i >= 0 ? i : 0;
  }
  function leafPath(rat, day, unit) {
    return '/leaf?layer=' + LF.layer + '&at=' + LF.at.join(',') + '&rat=' + rat + '&day=' + encodeURIComponent(day)
      + '&unit=' + encodeURIComponent(unit) + '&cell=' + pacCellNow();
  }
  function leafUnits(day) {
    const r = GH.detail && (GH.detail.rats || []).find((x) => x.rat === LF.rat);
    const s = r && (r.days || {})[day];
    if (!s) return [];
    const rest = String(LF.unit || '').charAt(0) === 'e';
    return (rest ? s.rest_units || [] : s.units || []).map((u) => u.id);
  }
  async function openLeaf(rat, day, unit) {
    Object.assign(LF, { open: true, rat, day, unit, data: null, err: null, at: (GH.at || [wi(), bi(), mi(), st.sel]).slice(),
                        layer: GH.layer || st.layer });
    const seq = ++LF.seq;
    hideTip();
    renderLeaf();
    try {
      const d = await getJSON(leafPath(rat, day, unit));
      if (seq !== LF.seq) return;
      LF.data = d;
    } catch (e) {
      if (seq !== LF.seq) return;
      LF.err = e.message;
    }
    renderLeaf();
    // The next cue pair, read now so stepping to it is quick.
    const ids = leafUnits(day), i = ids.indexOf(unit);
    if (i >= 0 && i + 1 < ids.length && !FIX) {
      fetch(API + leafPath(rat, day, ids[i + 1])).catch(() => null);
    }
  }
  function closeLeaf() {
    LF.open = false;
    LF.seq++;
    const h = $('leaf');
    if (h) h.remove();
  }
  function stepLeaf(dir) {
    const ids = leafUnits(LF.day);
    const i = ids.indexOf(LF.unit);
    if (i < 0) return;
    const j = i + dir;
    if (j >= 0 && j < ids.length) openLeaf(LF.rat, LF.day, ids[j]);
  }
  function switchDay(day) {
    if (day === LF.day) return;
    const ids = leafUnits(LF.day), other = leafUnits(day);
    const i = Math.max(0, ids.indexOf(LF.unit));
    if (other.length) openLeaf(LF.rat, day, other[Math.min(i, other.length - 1)]);
  }
  const secs = (v) => String(+(+v).toFixed(2));
  function leafSay(d) {
    return 'r' + d.rat + ' · ' + d.day + ' · ' + d.unit + (d.label ? ' (' + d.label + ')' : '') + ' · ' + d.window.name + ' window, '
      + secs(d.window.t1 - d.window.t0) + ' s · ' + (d.band.named ? d.band.label : d.band.hz + ' Hz') + ' · ' + d.regions.join(' – ');
  }
  const PLOT_OF = { coherence: 'coherence', icoh: 'icoh', raw_cc: 'raw_cc', env_cc: 'env_cc', env_cc0: 'env_cc0', orth_env: 'orth_env',
                    plv: 'plv', ppc: 'ppc', pli: 'pli', wpli: 'wpli', dwpli: 'dwpli', gc_ab: 'gc', gc_ba: 'gc', gc_net: 'gc' };
  function renderLeaf() {
    let host = $('leaf');
    if (!LF.open) { if (host) host.remove(); return; }
    if (!host) {
      host = el('div', { id: 'leaf', class: 'leafpanel', role: 'dialog', 'aria-label': 'One cue pair, down to its traces' });
      document.body.appendChild(host);
    }
    host.innerHTML = '';
    const S = D.S, G = window.MONO_FIGS, d = LF.data;
    const ids = leafUnits(LF.day), i = ids.indexOf(LF.unit);
    const bar = el('div', { class: 'leafbar' }, [
      el('div', { class: 'hrow' }, [el('h2', { text: d ? leafSay(d) : 'r' + LF.rat + ' · ' + LF.day + ' · ' + LF.unit }), qh('leaf')]),
      el('div', { class: 'leafctl' }, [
        el('button', { type: 'button', class: 'lbtn', text: '←', title: 'The previous cue pair (←)', disabled: i <= 0 ? 'disabled' : null,
                       onclick: () => stepLeaf(-1) }),
        el('span', { class: 'small muted', text: i >= 0 ? (i + 1) + ' of ' + ids.length : '' }),
        el('button', { type: 'button', class: 'lbtn', text: '→', title: 'The next cue pair (→)', disabled: i < 0 || i >= ids.length - 1 ? 'disabled' : null,
                       onclick: () => stepLeaf(1) }),
        seg([['Precon1', 'Precon1'], ['Precon4', 'Precon4']], LF.day, (day) => switchDay(day)),
        el('button', { type: 'button', class: 'lbtn', text: 'SVG', title: 'Save the figures as one SVG', disabled: d ? null : 'disabled', onclick: () => exportLeaf('svg') }),
        el('button', { type: 'button', class: 'lbtn', text: 'PNG', title: 'Save the figures as a PNG', disabled: d ? null : 'disabled', onclick: () => exportLeaf('png') }),
        el('button', { type: 'button', class: 'lbtn', text: 'CSV', title: 'Save the window’s traces and every number', disabled: d && d.explain ? null : 'disabled', onclick: () => exportLeaf('csv') }),
        el('button', { type: 'button', class: 'lbtn', text: 'Close ✕', title: 'Close (Esc)', onclick: closeLeaf }),
      ]),
    ]);
    host.appendChild(bar);
    const body = el('div', { class: 'leafbody' });
    host.appendChild(body);
    // Traces as wide as the panel, so their labels stay readable on a phone.
    const TW = Math.max(320, Math.min(1400, (body.clientWidth || 960) - 30));
    if (!d && !LF.err) {
      body.appendChild(el('p', { class: 'loading', text: 'Reading this cue pair from the VACC copy of the recording (a few seconds the first time)…' }));
      return;
    }
    if (LF.err) {
      body.appendChild(el('p', { class: 'warn', text: LF.err }));
      return;
    }
    if (d.measured === false) body.appendChild(el('p', { class: 'warn', text: 'Not measured here: ' + d.why }));
    const sec = (title, key, kids) => body.appendChild(el('section', { class: 'lsec' },
      [el('div', { class: 'hrow' }, [el('h3', { text: title }), key ? qh(key) : null])].concat(kids)));
    // 1. The whole cue pair.
    if (d.span && (d.span.a || d.span.b)) {
      const n = (d.span.a || d.span.b).length;
      const t = Array.from({ length: n }, (_x, k) => +(d.span.t0 + k / d.span.fs).toFixed(4));
      const rows = [];
      if (d.span.a) rows.push({ y: d.span.a, short: 'A', label: d.regions[0] + ' (µV, notched)', color: G.css('--up') });
      if (d.span.b) rows.push({ y: d.span.b, short: 'B', label: d.regions[1] + ' (µV, notched)', color: G.css('--down') });
      sec(d.rest ? 'The rest epoch, with 10 s either side' : 'The whole cue pair', null, [
        G.traces(t, rows, { w: TW, rowH: 70, marks: d.marks, highlight: [d.window.t0, d.window.t1], label: 'the recording' }),
        el('p', { class: 'small muted', text: 'Shaded: the ' + d.window.name + ' window this number was computed on ('
          + secs(d.window.t0) + '–' + secs(d.window.t1) + ' s into the recording). Dashed lines: where each window starts.' })]);
    }
    const ex = d.explain;
    if (!ex) return;
    // 2. The analysed window, four ways.
    const tr = ex.traces;
    sec('The analysed window', null, [G.traces(tr.t.map((x) => +(x + d.window.t0).toFixed(4)), [
      { y: tr.raw_a, short: 'A raw', color: G.css('--up') },
      { y: tr.raw_b, short: 'B raw', color: G.css('--down') },
      { y: tr.band_a, y2: tr.band_b, short: 'band', color: G.css('--up'), color2: G.css('--down'), label: sig(ex.band.low) + '–' + sig(ex.band.high) + ' Hz, A and B' },
      { y: tr.env_a, y2: tr.env_b, short: 'env', color: G.css('--up'), color2: G.css('--down'), label: 'envelopes' },
      { y: tr.dphi, short: 'Δφ', range: [-Math.PI, Math.PI], zero: true, label: 'phase of A − phase of B' },
    ], { w: TW, rowH: 56, label: 'the analysed window' })]);
    // 3. How each number was made: the one in view first.
    const order = [d.method].concat(GROUPS.flatMap((g) => g[1]).filter((m) => m !== d.method));
    const grid = el('div', { class: 'lgrid' });
    for (const m of order) {
      const meth = S.methods.find((x) => x.id === m);
      const v = (ex.values || {})[m];
      const card = el('div', { class: 'lcard' + (m === d.method ? ' sel' : '') }, [
        el('div', { class: 'hrow' }, [el('h4', { text: meth.label }), qh(m)]),
        el('div', { class: 'lval num', text: 'this cue pair: ' + sig(v) + (m === d.method && d.stored != null
          ? ' · stored ' + sig(d.stored) + (d.matches ? ' · matches' : ' · DIFFERS') : '') }),
      ]);
      const fig = window.MONO_HELP ? MONO_HELP.measurePlot(PLOT_OF[m], ex, { w: 300 }) : null;
      if (fig) card.appendChild(fig);
      grid.appendChild(card);
    }
    const pcard = el('div', { class: 'lcard' }, [el('div', { class: 'hrow' }, [el('h4', { text: 'Power' }), qh('power')]),
      el('div', { class: 'lval num', text: 'log10 power: A ' + sig(ex.power[0]) + ', B ' + sig(ex.power[1]) })]);
    const pf = window.MONO_HELP ? MONO_HELP.measurePlot('power', ex, { w: 300 }) : null;
    if (pf) pcard.appendChild(pf);
    grid.appendChild(pcard);
    sec('How each number was made', null, [grid]);
    // 4. PAC: the phase-binned amplitude for the chosen cell.
    if (ex.pac) {
      const P = ex.pac;
      const kids = [el('p', { class: 'small muted', text: P.fp + ' Hz phase × ' + P.fa + ' Hz amplitude'
        + (P.amp_band ? ' (amplitude band ' + sig(P.amp_band[0]) + '–' + sig(P.amp_band[1]) + ' Hz)' : ' -- not measured: this cell cannot carry its sidebands')
        + '. Bars: mean amplitude in each phase bin; dashed: what no coupling looks like. Choose another cell in the PAC panel.' })];
      if (P.aa) {
        const row = el('div', { class: 'lgrid' });
        for (const [k, name] of [['aa', 'A phase → A amplitude'], ['ab', 'A phase → B amplitude'], ['ba', 'B phase → A amplitude'], ['bb', 'B phase → B amplitude']]) {
          row.appendChild(el('div', { class: 'lcard' }, [el('h4', { text: name }), G.pacBars(P[k].p, { w: 240, mi: P[k].mi })]));
        }
        kids.push(row);
      }
      sec('Phase–amplitude coupling in this window', 'pac', kids);
    }
  }

  /* Save what is on screen: one SVG of every figure, a PNG of it, or the
     window's traces and every number as CSV. */
  function leafName(ext) {
    return 'monolith-r' + LF.rat + '-' + LF.day + '-' + LF.unit + '-' + (LF.data ? LF.data.window.name + '-' + LF.data.band.id + '-' + LF.data.method : '') + '.' + ext;
  }
  function download(name, blob) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }
  function composite() {
    const figs = Array.from(document.querySelectorAll('#leaf svg.mfig'));
    const W2 = 980;
    let y = 30;
    const out = document.createElementNS(NS, 'svg');
    out.setAttribute('xmlns', NS);
    out.appendChild(sv('rect', { x: 0, y: 0, width: W2, height: 10, fill: css('--surface') }));
    out.appendChild(sv('text', { x: 10, y: 20, 'font-size': 13, fill: css('--ink'), 'font-family': 'sans-serif' }, LF.data ? leafSay(LF.data) : ''));
    let x = 10, rowH = 0;
    for (const f of figs) {
      const vb = (f.getAttribute('viewBox') || '0 0 300 150').split(' ').map(Number);
      const w = vb[2], h = vb[3];
      if (x + w > W2 - 10) { x = 10; y += rowH + 12; rowH = 0; }
      const c = f.cloneNode(true);
      c.setAttribute('x', x);
      c.setAttribute('y', y);
      c.setAttribute('width', w);
      c.setAttribute('height', h);
      c.removeAttribute('class');
      out.appendChild(c);
      x += w + 12;
      rowH = Math.max(rowH, h);
    }
    const H2 = y + rowH + 10;
    out.setAttribute('viewBox', '0 0 ' + W2 + ' ' + H2);
    out.setAttribute('width', W2);
    out.setAttribute('height', H2);
    out.firstChild.setAttribute('height', H2);
    return { svg: out, w: W2, h: H2 };
  }
  function exportLeaf(kind) {
    const d = LF.data;
    if (!d) return;
    if (kind === 'csv') {
      const ex = d.explain || {};
      const tr = ex.traces || {};
      const lines = ['# ' + leafSay(d), '# stored ' + d.method + ' ' + d.stored + ', recomputed ' + d.recomputed];
      for (const [m, v] of Object.entries(ex.values || {})) lines.push('# ' + m + ',' + v);
      lines.push('t_s,raw_a,raw_b,band_a,band_b,env_a,env_b,dphi');
      for (let k = 0; k < (tr.t || []).length; k++) {
        lines.push([(tr.t[k] + d.window.t0).toFixed(4), tr.raw_a[k], tr.raw_b[k], tr.band_a[k], tr.band_b[k], tr.env_a[k], tr.env_b[k], tr.dphi[k]].join(','));
      }
      download(leafName('csv'), new Blob([lines.join('\n') + '\n'], { type: 'text/csv' }));
      return;
    }
    const c = composite();
    const text = new XMLSerializer().serializeToString(c.svg);
    if (kind === 'svg') { download(leafName('svg'), new Blob([text], { type: 'image/svg+xml' })); return; }
    const img = new Image();
    img.onload = () => {
      const cv = document.createElement('canvas');
      cv.width = c.w * 2;
      cv.height = c.h * 2;
      const g = cv.getContext('2d');
      g.fillStyle = css('--surface') || '#fff';
      g.fillRect(0, 0, cv.width, cv.height);
      g.scale(2, 2);
      g.drawImage(img, 0, 0);
      cv.toBlob((b) => b && download(leafName('png'), b), 'image/png');
    };
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(text);
  }

  /* ==================================================================
     What was lost: per rat and day, and in all
     ================================================================== */
  const DMG = { data: null, err: null };
  const REASON_LABEL = { kept: 'kept', histology: 'histology', bad: 'bad wire', clipped: 'clipped', unread: 'not measured' };
  function reasonColor(r) {
    return { kept: css('--ok'), histology: css('--node-grey'), bad: css('--arrow'), clipped: css('--up'), unread: css('--ink-3') }[r];
  }
  const pct = (a, b) => (b ? Math.round(100 * a / b) : 0) + '%';
  async function loadDamage() {
    try { DMG.data = await getJSON('/damage'); } catch (e) { DMG.err = e.message; }
    renderDamage();
    renderVerdict();
  }
  function sumTally(rows) {
    const t = { of: 0, kept: 0, histology: 0, bad: 0, clipped: 0, unread: 0 };
    for (const r of rows) for (const k in t) t[k] += r[k] || 0;
    return t;
  }
  /* One bar: how a set of region-windows went, kept first. */
  function damageBar(t, w) {
    const H = 16, svg = sv('svg', { viewBox: '0 0 ' + w + ' ' + H, class: 'mfig dbar', width: '100%', style: 'max-width:' + w + 'px',
      role: 'img', 'aria-label': 'kept ' + pct(t.kept, t.of) });
    let x = 0;
    for (const r of ['kept', 'histology', 'clipped', 'bad', 'unread']) {
      const v = t[r] || 0;
      if (!v) continue;
      const ww = w * v / t.of;
      const seg = sv('rect', { x: x.toFixed(2), y: 0, width: Math.max(0.5, ww).toFixed(2), height: H, fill: reasonColor(r), 'data-reason': r });
      hover(seg, [REASON_LABEL[r], v.toLocaleString() + ' of ' + t.of.toLocaleString() + ' region-windows (' + pct(v, t.of) + ')',
                  r === 'kept' ? '' : DMG.data.reason_say[r]]);
      svg.appendChild(seg);
      x += ww;
    }
    return svg;
  }
  /* Rats down, regions across, one panel per day; a cell is how many of
     that region's cue-pair windows were kept. */
  function damageMap(day) {
    const d = DMG.data, S = D.S;
    const days = d.days.filter((x) => x.day === day);
    const names = d.regions;
    const cw = 44, ch = 22, left = 34, top = 50;
    const W2 = left + cw * names.length + 4, H2 = top + ch * days.length + 6;
    const svg = sv('svg', { viewBox: '0 0 ' + W2 + ' ' + H2, class: 'mfig dmap', width: '100%', style: 'max-width:' + W2 + 'px',
      role: 'img', 'aria-label': 'What each rat kept, region by region, on ' + day, 'data-day': day });
    const defs = sv('defs');
    const pat = sv('pattern', { id: 'hatch-' + day, width: 6, height: 6, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' });
    pat.appendChild(sv('rect', { x: 0, y: 0, width: 6, height: 6, fill: css('--surface-2') }));
    pat.appendChild(sv('line', { x1: 0, y1: 0, x2: 0, y2: 6, stroke: css('--node-grey'), 'stroke-width': 2.5 }));
    defs.appendChild(pat);
    svg.appendChild(defs);
    svg.appendChild(sv('text', { x: left, y: 12, 'font-size': 11.5, 'font-weight': 600, fill: css('--ink') }, day));
    names.forEach((n, j) => {
      const x = left + cw * j + cw / 2;
      const [side, ...rest] = n.split(' ');
      svg.appendChild(sv('text', { x, y: top - 18, 'text-anchor': 'middle', 'font-size': 9.5, fill: css('--ink-3') }, side === 'Right' ? 'R' : side === 'Left' ? 'L' : side));
      svg.appendChild(sv('text', { x, y: top - 6, 'text-anchor': 'middle', 'font-size': 9.5, fill: css('--ink-2') }, rest.join(' ')));
    });
    days.forEach((dd, i) => {
      const y = top + ch * i;
      svg.appendChild(sv('text', { x: left - 5, y: y + ch / 2 + 3.5, 'text-anchor': 'end', 'font-size': 10.5, fill: css('--ink-2') }, 'r' + dd.rat));
      dd.regions.forEach((r, j) => {
        const x = left + cw * j;
        const t = r.state;
        const histo = t.histology === t.of && t.of > 0;
        const share = t.of ? t.kept / t.of : 0;
        const cell = sv('rect', { x: x + 1, y: y + 1, width: cw - 2, height: ch - 2, rx: 3,
          fill: histo ? 'url(#hatch-' + day + ')' : mix(css('--up'), css('--ok'), share), 'fill-opacity': histo ? 1 : 0.25 + 0.6 * share,
          'data-rat': String(dd.rat), 'data-region': r.name, 'data-kept': String(t.kept), 'data-of': String(t.of) });
        const why = ['histology', 'clipped', 'bad', 'unread'].filter((k) => t[k]).map((k) => t[k] + ' ' + REASON_LABEL[k]);
        hover(cell, ['r' + dd.rat + ' · ' + day + ' · ' + r.name,
          histo ? 'Not measured at all: ' + d.reason_say.histology + '.'
            : 'Cue-pair windows: ' + t.kept + ' of ' + t.of + ' kept' + (why.length ? ' (' + why.join(', ') + ')' : ''),
          histo ? '' : 'Transition windows: ' + r.trans.kept + ' of ' + r.trans.of + ' kept',
          histo ? '' : 'Rest epochs: ' + r.rest.kept + ' of ' + r.rest.of + ' kept']);
        svg.appendChild(cell);
        if (!histo) {
          svg.appendChild(sv('text', { x: x + cw / 2, y: y + ch / 2 + 3.5, 'text-anchor': 'middle', 'font-size': 9.5, 'pointer-events': 'none',
            fill: css('--ink') }, Math.round(100 * share) + ''));
        }
      });
    });
    return svg;
  }
  function renderDamage() {
    const host = $('damage');
    if (!host) return;
    host.innerHTML = '';
    host.appendChild(el('div', { class: 'hrow' }, [el('h2', { text: 'What was lost' }), qh('damage')]));
    const d = DMG.data;
    if (!d) {
      host.appendChild(el('p', { class: DMG.err ? 'warn' : 'loading', text: DMG.err ? 'The damage report could not be read: ' + DMG.err : 'Counting what was lost…' }));
      return;
    }
    const W0 = d.whole;
    const days = d.days;
    const rats = Array.from(new Set(days.map((x) => x.rat))).sort((a, b) => a - b);
    const dayNames = Array.from(new Set(days.map((x) => x.day)));
    const tS = sumTally(W0.state), tT = sumTally(W0.trans), tR = sumTally(W0.rest_regions);
    // In all.
    host.appendChild(el('p', {}, [el('strong', { text: 'In all: ' }),
      W0.cue.total + ' cue pairs over ' + rats.length + ' rats and ' + dayNames.length + ' days. ' + W0.cue.kept
      + ' kept every region histology allows, in every window; ' + W0.cue.partial + ' lost a region somewhere; '
      + W0.cue.lost + ' were lost entirely (no two regions read in any window). Rest epochs: ' + W0.rest.kept + ' of '
      + W0.rest.total + ' usable.']));
    const row = (label, t) => el('div', { class: 'drow' }, [el('span', { class: 'dlab small', text: label }), damageBar(t, 520),
      el('span', { class: 'small muted', text: pct(t.kept, t.of) + ' kept' })]);
    host.appendChild(el('div', { class: 'dbars' }, [
      row('Cue-pair windows', tS), row('Transition windows', tT), row('Rest epochs', tR)]));
    host.appendChild(el('div', { class: 'legend' }, ['kept', 'histology', 'clipped', 'bad', 'unread'].map((r) =>
      el('span', { title: r === 'kept' ? '' : d.reason_say[r] }, [el('b', { class: 'sw', style: 'background:' + reasonColor(r) }), REASON_LABEL[r]]))));
    // What it cost the pooled result.
    const E0 = d.entries[st.layer] || d.entries.raw;
    if (E0) {
      const why = Object.entries(E0.untested).map(([c, n]) => n.toLocaleString() + ' because ' + (d.why_say[c] || 'code ' + c));
      const none = E0.by_region.filter((x) => x.tested === 0).map((x) => x.name);
      host.appendChild(el('p', { class: 'small' }, [el('strong', { text: 'Entries: ' }),
        E0.tested.toLocaleString() + ' of ' + E0.entries.toLocaleString() + ' tested (' + pct(E0.tested, E0.entries) + '). '
        + (why.length ? 'Not tested: ' + why.join('; ') + '. ' : '')
        + (none.length ? 'Nothing at all with ' + none.join(' or ') + ': too few rats have it on both days.' : '')]));
    }
    if (d.aliasing) {
      const A = d.aliasing;
      host.appendChild(el('p', { class: 'small' }, [el('strong', { text: 'Aliasing: ' }), A.say || '',
        A.at ? el('span', { class: 'muted', text: ' (checked ' + String(A.at).slice(0, 10) + ')' }) : null, qh('aliasing')]));
    }
    // Rat by rat.
    host.appendChild(el('h3', { text: 'Each rat, each day' }));
    host.appendChild(el('div', { class: 'dmaps' }, dayNames.map((day) => damageMap(day))));
    host.appendChild(el('p', { class: 'small muted', text: 'A cell is the share of that region’s cue-pair windows (cue pairs × 4 windows) '
      + 'that were kept; hatched: histology says the probe is not there. Hover a cell for transitions and rest.' }));
    const tbl = el('table', { class: 'dtable' });
    const head = el('tr', {}, [el('th', { text: 'Rat' })].concat(dayNames.map((day) => el('th', { text: day }))).concat([el('th', { text: 'Both days' })]));
    tbl.appendChild(el('thead', {}, [head]));
    const body = el('tbody');
    const cueSay = (c, r) => c.kept + ' kept, ' + c.partial + ' partly, ' + c.lost + ' lost of ' + c.total + ' cue pairs · rest ' + r.kept + '/' + r.total;
    for (const rat of rats) {
      const mine = days.filter((x) => x.rat === rat);
      const cells = dayNames.map((day) => {
        const x = mine.find((y) => y.day === day);
        if (!x) return el('td', { class: 'muted', text: 'not in the Monolith' });
        const extra = [];
        if (x.refused) extra.push(x.refused + ' refused on the cluster');
        for (const n of x.notes) extra.push(n);
        return el('td', {}, [el('div', { text: cueSay(x.cue, x.rest) }), extra.length ? el('div', { class: 'small muted', text: extra.join(' · ') }) : null]);
      });
      const c = { total: 0, kept: 0, partial: 0, lost: 0 }, r = { total: 0, kept: 0 };
      for (const x of mine) { for (const k in c) c[k] += x.cue[k]; r.total += x.rest.total; r.kept += x.rest.kept; }
      const hist = (mine[0] || {}).histology || [];
      body.appendChild(el('tr', { 'data-rat': String(rat) }, [el('th', { text: 'r' + rat })].concat(cells).concat([el('td', {}, [
        el('div', { text: cueSay(c, r) }), hist.length ? el('div', { class: 'small muted', text: 'histology: no ' + hist.join(', ') }) : null])])));
    }
    const tot = el('tr', { class: 'dtot' }, [el('th', { text: 'All' })].concat(dayNames.map((day) => {
      const c = { total: 0, kept: 0, partial: 0, lost: 0 }, r = { total: 0, kept: 0 };
      for (const x of days.filter((y) => y.day === day)) { for (const k in c) c[k] += x.cue[k]; r.total += x.rest.total; r.kept += x.rest.kept; }
      return el('td', { text: cueSay(c, r) });
    })).concat([el('td', { text: cueSay(W0.cue, W0.rest) })]));
    body.appendChild(tot);
    tbl.appendChild(body);
    host.appendChild(el('div', { class: 'dtwrap' }, [tbl]));
  }

  /* ---------------- everything ---------------- */
  function renderAll(viewChanged) {
    renderControls();
    renderCircuit();
    renderSpectrum();
    renderTop();
    renderPac();
    if (viewChanged === undefined) { renderVerdict(); renderFoot(); }
  }

  async function init() {
    recall();
    try {
      D.S = await getJSON('/data/summary');
      const S = D.S;
      if (!S.bands.some((b) => b.id === st.band)) st.band = 'f08';
      if (!S.windows.some((w) => w.id === st.win)) st.win = 'cue1';
      st.kind = S.windows.find((w) => w.id === st.win).kind;
      if (!S.methods.some((m) => m.id === st.method)) st.method = 'coherence';
      if (!LAYERS.some((l) => l[0] === st.layer)) st.layer = 'raw';
      await ensureLayer(st.layer);
    } catch (e) {
      D.err = e.message;
      $('app').innerHTML = '';
      $('app').appendChild(el('h1', { text: 'The Monolith' }));
      $('app').appendChild(el('div', { class: 'card' }, [
        el('p', { text: /not been built/.test(e.message) ? 'The Monolith has not been built yet.' : 'The Monolith could not be read: ' + e.message }),
        el('p', { class: 'muted', text: 'In Jarvis: ToolKit → Drift → Monolith. Upload, check the VACC, run the job, fetch the results; then open this page again.' }),
      ]));
      return;
    }
    layout();
    // Open on the first point of interest when nothing was being looked at.
    const top = (D.S.top || {})[st.layer] || [];
    let fresh = true;
    try { fresh = !localStorage.getItem(VIEW_KEY); } catch (e) { /* no storage: a fresh view */ }
    if (top.length && st.sel == null && fresh) {
      const t = top[0];
      Object.assign(st, { kind: D.S.windows.find((w) => w.id === t.w).kind, win: t.w, band: t.band, method: t.m, sel: t.pair });
    }
    renderAll();
    loadDamage();
    try { matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { renderAll(); renderDamage(); }); } catch (e) { /* old browser */ }
    D.ready = true;
    document.dispatchEvent(new CustomEvent('monolith:ready'));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  return {
    get state() { return Object.assign({}, st); },
    get data() { return D; },
    get ghost() { return { pair: GH.pair, stack: GH.stack.slice(), lifted: GH.lifted, detail: GH.detail, info: GH.info }; },
    get ready() { return !!D.ready; },
    set, go, openGhost, closeGhost, push, ghostTo, renderAll, LEVELS, Q, openLeaf, closeLeaf, stepLeaf, switchDay,
    get leaf() { return Object.assign({}, LF); }, broadband, bbCount, here, arrowGeom, get damage() { return DMG.data; }, renderDamage,
  };
})();
