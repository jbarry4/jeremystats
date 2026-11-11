/* ==========================================================================
   inside.js -- Inside Jarvis: the showcase's fourth tab.

   Everything the lab has put into Jarvis, counted live from its own records
   (backend/inside.py) and drawn five ways:

   - The Sunflower: every banked event, oldest at the centre, newest at the
     rim, on the golden angle a sunflower head uses, coloured by the
     detector that found it.
   - Powers of Ten: one zoom from a single sample of one real recording out
     to every recording there is. The trace at the deep end is simulated and
     says so; every circle is a real recording, animal and project, sized by
     how many samples it holds.
   - The Gyrus: every version as a granule cell along a dentate gyrus. Its
     dendrites are its patch note's own outline; its mossy fibres run to the
     tools it names.
   - The Connectome: every module a neuron, every call between them an axon,
     with spikes running along them.
   - The River: every candidate in every curation set, from the kind of set,
     through who made the last call, to the call.

   It adapts. Each part has a signature, only a part that moved is sent
   again, and what arrived since you last looked grows in.

   And the printer: "Last 7 days' work" (backend/weekly.py), a printout of
   the week for the PI, written by Hater of AI from the commits, the patch
   notes, the records and the Lab Operations sheet.

   Every picture is drawn inside a try, as the other destinations are: one
   that throws stops, and the rest carry on.
   ========================================================================== */
(function () {
  'use strict';
  if (typeof document === 'undefined') return;
  const B = (typeof BARRY !== 'undefined') ? BARRY : null;
  const SEEN_KEY = 'jarvis.inside.seen';
  const GOLD = Math.PI * (3 - Math.sqrt(5));
  const TAU = Math.PI * 2;

  /* ------------------------------------------------------------------------
     Small things
     ------------------------------------------------------------------------ */
  const fx = () => (B && B.jarvisfx) || window.JarvisFX || null;
  const sfx = (name, a) => { try { const f = fx(); if (f && f[name]) f[name](a); } catch (e) { /* silence */ } };
  const tok = (n, f) => {
    try {
      if (B && B.token) return B.token(n, f) || f;
      return getComputedStyle(document.documentElement).getPropertyValue(n).trim() || f;
    } catch (e) { return f; }
  };
  const reduced = () => {
    try {
      if (B && B.ui && B.ui.reducedMotion) return B.ui.reducedMotion();
      return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) { return false; }
  };
  const ratio = () => Math.min(2, window.devicePixelRatio || 1);
  const fmt = (n) => Math.round(Number(n) || 0).toLocaleString();
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, u) => a + (b - a) * u;
  const ease = (u) => 1 - Math.pow(1 - clamp(u, 0, 1), 3);
  const easeIO = (u) => { u = clamp(u, 0, 1); return u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2; };

  function h(tag, cls, text, attrs) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null && text !== '') n.textContent = text;
    if (attrs) for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }
  function oops(where, e) {
    try {
      if (typeof reportClientError === 'function') {
        reportClientError('inside.' + where, (e && e.message) || String(e), e && e.stack);
      }
    } catch (x) { /* nowhere to say it */ }
  }
  async function getJSON(path) {
    if (typeof api === 'function') return api(path, { priority: 'background' });
    const r = await fetch(path);
    return r.json();
  }
  async function postJSON(path, body) {
    if (typeof apiPost === 'function') return apiPost(path, body);
    const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                  body: JSON.stringify(body || {}) });
    return r.json();
  }

  /* A theme colour as numbers, whatever form the token is written in. */
  const RGB = new Map();
  function rgb(css) {
    if (RGB.has(css)) return RGB.get(css);
    let out = [128, 128, 128];
    try {
      const c = document.createElement('canvas');
      c.width = c.height = 1;
      const g = c.getContext('2d');
      g.fillStyle = '#808080';
      g.fillStyle = css;
      g.fillRect(0, 0, 1, 1);
      const d = g.getImageData(0, 0, 1, 1).data;
      out = [d[0], d[1], d[2]];
    } catch (e) { /* grey */ }
    RGB.set(css, out);
    return out;
  }
  const rgba = (css, a) => { const c = rgb(css); return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a + ')'; };

  function palette() {
    return {
      ds: tok('--call-ds', '#5aa9ff'), p: tok('--call-p', '#ff6b5e'), gold: tok('--accent', '#FFB81C'),
      c1: tok('--c1', '#FFB81C'), c2: tok('--c2', '#7FE3B0'), c3: tok('--c3', '#8ec5ff'),
      c4: tok('--c4', '#f59fb4'), c5: tok('--c5', '#8aa39a'),
      text: tok('--text', '#e9f2ed'), text2: tok('--text-2', '#a3bdb0'), text3: tok('--text-3', '#6f8c7d'),
      line: tok('--line', '#244737'), bg: tok('--bg', '#0a1310'), bg2: tok('--bg-2', '#0f1e18'),
      bg3: tok('--bg-3', '#15291f'), mono: tok('--mono', 'ui-monospace, Consolas, monospace'),
    };
  }
  let PAL = null;
  const pal = () => PAL || (PAL = palette());

  /* The backing store at the screen's ratio, read at draw time (Jarvis
     Light reads 1). Returns the context with CSS pixels as its unit. */
  function fit(cv) {
    const k = ratio();
    const w = Math.max(1, cv.clientWidth), hh = Math.max(1, cv.clientHeight);
    const W = Math.round(w * k), H = Math.round(hh * k);
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    const g = cv.getContext('2d');
    g.setTransform(k, 0, 0, k, 0, 0);
    return { g, w, h: hh, k };
  }

  /* A label on a canvas sits on a patch of the ground, and never on top of
     another one: `boxes` is what has been placed this frame. */
  function label(g, text, x, y, o) {
    const opt = o || {};
    const P = pal();
    g.font = (opt.weight || '600') + ' ' + (opt.size || 11) + 'px ' + (opt.font || 'system-ui, sans-serif');
    const w = g.measureText(text).width;
    const hgt = (opt.size || 11) + 6;
    const align = opt.align || 'center';
    const x0 = align === 'left' ? x : align === 'right' ? x - w - 8 : x - w / 2 - 4;
    const box = [x0, y - hgt / 2, w + 8, hgt];
    if (opt.boxes) {
      for (const b of opt.boxes) {
        if (box[0] < b[0] + b[2] && b[0] < box[0] + box[2] && box[1] < b[1] + b[3] && b[1] < box[1] + box[3]) return false;
      }
      opt.boxes.push(box);
    }
    g.fillStyle = rgba(P.bg2, opt.ground == null ? 0.82 : opt.ground);
    g.fillRect(box[0], box[1], box[2], box[3]);
    g.fillStyle = opt.color || P.text;
    g.textBaseline = 'middle';
    g.textAlign = 'left';
    g.fillText(text, x0 + 4, y + 0.5);
    return true;
  }

  function hash(n) {
    let x = (n | 0) ^ 0x9e3779b9;
    x = Math.imul(x ^ (x >>> 16), 0x85ebca6b);
    x = Math.imul(x ^ (x >>> 13), 0xc2b2ae35);
    x ^= x >>> 16;
    return (x >>> 0) / 4294967296;
  }
  function seeded(seed) {
    let s = (seed >>> 0) || 1;
    return () => { s = Math.imul(s ^ (s >>> 15), 0x2c1b3c6d) + 0x6d2b79f5 | 0; return ((s >>> 0) % 100000) / 100000; };
  }
  function strHash(str) {
    let x = 2166136261;
    for (let i = 0; i < str.length; i++) x = Math.imul(x ^ str.charCodeAt(i), 16777619);
    return x >>> 0;
  }

  function duration(sec) {
    if (sec < 1e-3) return Math.round(sec * 1e6) + ' microseconds';
    if (sec < 1) { const ms = sec * 1e3; return (ms < 10 ? ms.toFixed(1) : Math.round(ms)) + ' milliseconds'; }
    if (sec < 60) return (sec < 10 ? sec.toFixed(1) : Math.round(sec)) + ' seconds';
    if (sec < 3600) return Math.round(sec / 60) + ' minutes';
    return (sec / 3600).toFixed(sec < 36000 ? 1 : 0) + ' hours';
  }
  function bigWords(n) {
    if (n >= 1e12) return (n / 1e12).toFixed(2) + ' trillion';
    if (n >= 1e9) return (n / 1e9).toFixed(n >= 1e11 ? 0 : 1) + ' billion';
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e8 ? 0 : 1) + ' million';
    return fmt(n);
  }
  const day = (iso) => {
    try {
      return new Date(iso + (iso.length === 10 ? 'T12:00:00' : ''))
        .toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
    } catch (e) { return iso; }
  };

  /* ------------------------------------------------------------------------
     One animation loop for every picture that is moving and on screen
     ------------------------------------------------------------------------ */
  const LOOP = { on: new Set(), raf: 0 };
  function wake(sc) {
    LOOP.on.add(sc);
    if (!LOOP.raf) LOOP.raf = requestAnimationFrame(frame);
  }
  function frame(now) {
    LOOP.raf = 0;
    for (const sc of Array.from(LOOP.on)) {
      if (!sc.visible) { LOOP.on.delete(sc); continue; }
      let more = false;
      try { more = sc.tick(now); } catch (e) { more = false; oops(sc.key + '.tick', e); }
      if (!more) LOOP.on.delete(sc);
    }
    if (LOOP.on.size) LOOP.raf = requestAnimationFrame(frame);
  }

  /* A picture's frame: a heading, a sentence on how to read it, the canvas,
     and beside it what it shows and what is under the pointer. */
  function sceneFrame(key, title, lede) {
    const sec = h('section', 'in-scene');
    sec.dataset.scene = key;
    sec.id = 'in-' + key;
    const head = h('header', 'in-scene-head');
    head.append(h('h3', null, title), h('p', 'in-scene-lede', lede));
    const grid = h('div', 'in-scene-grid');
    const stage = h('div', 'in-stage');
    const cv = h('canvas', 'in-canvas');
    stage.append(cv);
    const aside = h('aside', 'in-aside');
    const facts = h('dl', 'in-facts');
    const legend = h('div', 'in-legend');
    const read = h('div', 'in-read', null, { 'aria-live': 'polite' });
    aside.append(facts, legend, read);
    grid.append(stage, aside);
    sec.append(head, grid);
    return { sec, stage, cv, aside, facts, legend, read };
  }
  function setFacts(dl, rows) {
    const sig = JSON.stringify(rows);
    if (dl.__sig === sig) return;
    dl.__sig = sig;
    dl.textContent = '';
    rows.forEach(([k, v]) => dl.append(h('dt', null, k), h('dd', null, v)));
  }
  function setLegend(node, rows) {
    const sig = JSON.stringify(rows);
    if (node.__sig === sig) return;
    node.__sig = sig;
    node.textContent = '';
    rows.forEach(([colour, words]) => {
      const r = h('span', 'in-key');
      const i = h('i');
      i.style.background = colour;
      r.append(i, h('span', null, words));
      node.append(r);
    });
  }
  function setRead(node, title, lines) {
    node.textContent = '';
    if (!title) { node.append(h('span', 'in-read-hint', lines && lines[0])); return; }
    node.append(h('strong', null, title));
    (lines || []).forEach((l) => node.append(h('span', null, l)));
  }

  /* ========================================================================
     The Sunflower: every banked event
     ======================================================================== */
  function Sunflower() {
    const f = sceneFrame('sunflower', 'The Sunflower',
      'Every event ever banked, one dot each: the oldest at the centre, the newest at the rim, '
      + 'set out on the golden angle a sunflower uses. Blue is a dentate spike, red a P-spike, '
      + 'and the two mixed where both detectors found it. Point at a ring to see the entry it came from.');
    const st = { rows: null, N: 0, cum: null, cls: null, ux: null, uy: null, img: null,
                 t0: 0, grow: true, seen: 0, rot: 0, last: 0, hover: -1, until: 0 };
    const sc = { key: 'sunflower', node: f.sec, visible: false };

    function set(part, seenEvents) {
      const rows = part.rows || [];
      let N = 0;
      const cum = new Float64Array(rows.length + 1);
      rows.forEach((r, i) => { N += r[2] || 0; cum[i + 1] = N; });
      const cls = new Uint8Array(N);
      let at = 0;
      const tally = [0, 0, 0, 0];
      rows.forEach((r) => {
        const n = r[2] || 0;
        if (r[1] === 'pooled' && r[6]) {
          // Interleaved as they are mixed: each event goes to the detector
          // furthest behind its share.
          const want = r[6], got = [0, 0, 0], tot = want[0] + want[1] + want[2] || 1;
          for (let j = 0; j < n; j++) {
            let best = 0, gap = -Infinity;
            for (let c = 0; c < 3; c++) {
              const g = want[c] * (j + 1) / tot - got[c];
              if (g > gap) { gap = g; best = c; }
            }
            got[best] += 1;
            cls[at + j] = best;
          }
        } else {
          const c = r[1] === 'ds' ? 0 : r[1] === 'ied' ? 1 : 3;
          cls.fill(c, at, at + n);
        }
        at += n;
      });
      for (let i = 0; i < N; i++) tally[cls[i]] += 1;
      const ux = new Float32Array(N), uy = new Float32Array(N);
      for (let i = 0; i < N; i++) {
        const r = Math.sqrt((i + 0.5) / N), t = i * GOLD;
        ux[i] = r * Math.cos(t);
        uy[i] = r * Math.sin(t);
      }
      const first = !st.rows;
      Object.assign(st, { rows, N, cum, cls, ux, uy, tally });
      st.seen = Math.min(N, seenEvents == null ? N : seenEvents);
      if (first || st.seen < N) {
        st.t0 = 0; st.grow = !reduced(); st.until = 0;
        // Ended on a timer too: under the harness runner frames stall.
        clearTimeout(st.endTimer);
        st.endTimer = setTimeout(() => { if (st.grow) { st.grow = false; draw(performance.now()); } }, 3000);
      }
      const P = pal();
      setFacts(f.facts, [['Events', fmt(N)], ['Bank entries', fmt(rows.length)],
                         ['Oldest', rows.length && rows[0][3] ? day(new Date(rows[0][3] * 1000).toISOString().slice(0, 10)) : '—'],
                         ['Newest', rows.length && rows[rows.length - 1][3]
                           ? day(new Date(rows[rows.length - 1][3] * 1000).toISOString().slice(0, 10)) : '—']]);
      setLegend(f.legend, [[P.ds, 'Dentate spikes · ' + fmt(tally[0])], [P.p, 'P-spikes · ' + fmt(tally[1])],
                           [both(), 'Found by both · ' + fmt(tally[2])], [P.c5, 'Other events · ' + fmt(tally[3])]]);
      if (st.hover < 0) setRead(f.read, null, ['Point at a ring of the flower.']);
      st.offKey = '';
      draw(performance.now());
      if (sc.visible) wake(sc);
    }

    /* Found by both detectors: the two detectors' colours mixed, so it reads
       as both in every theme rather than as a third thing. */
    function both() {
      const P = pal(), a = rgb(P.ds), b = rgb(P.p);
      return 'rgb(' + ((a[0] + b[0]) >> 1) + ',' + ((a[1] + b[1]) >> 1) + ',' + ((a[2] + b[2]) >> 1) + ')';
    }
    function colours() {
      const P = pal();
      return [P.ds, P.p, both(), P.c5];
    }

    /* The flower is drawn once, dot by dot at its true sub-pixel place (so
       the golden spirals show and no grid of pixels beats against them),
       onto a canvas of its own; each frame turns that whole picture. While
       it grows, only the new dots are added. */
    function paintDots(D, upto) {
      const o = st.off.getContext('2d');
      const R = D / 2 - 2, c = D / 2;
      const s = Math.max(0.6, R * Math.sqrt(Math.PI / st.N) * 0.8);
      const cols = colours();
      let last = -1;
      // A shade that comes round every 34 dots, so one family of the
      // flower's spirals shows (34 is a Fibonacci number; out at the rim the
      // family runs nearly straight, like spokes). The colour is still the
      // detector's; only its strength changes.
      for (let i = st.drawn; i < upto; i++) {
        const k = st.cls[i];
        if (k !== last) { o.fillStyle = cols[k]; last = k; }
        o.globalAlpha = 0.58 + 0.42 * (0.5 + 0.5 * Math.cos((TAU * (i % 34)) / 34));
        o.fillRect(c + st.ux[i] * R - s / 2, c + st.uy[i] * R - s / 2, s, s);
      }
      o.globalAlpha = 1;
      st.drawn = Math.max(st.drawn, upto);
    }

    function draw(now) {
      const { g, w, h: hh, k } = fit(f.cv);
      g.clearRect(0, 0, w, hh);
      if (!st.N) return;
      const Rc = Math.min(w, hh) * 0.47, ccx = w / 2, ccy = hh / 2;
      const D = Math.ceil((Rc * 2 + 4) * k);
      const key = D + ':' + st.N + ':' + colours().join(',');
      if (!st.off) st.off = document.createElement('canvas');
      if (st.offKey !== key) {
        st.off.width = D; st.off.height = D;
        st.off.getContext('2d').clearRect(0, 0, D, D);
        st.offKey = key;
        st.drawn = 0;
      }
      let upto = st.N;
      if (st.grow) {
        if (!st.t0) st.t0 = now;
        const u = (now - st.t0) / 2600;
        const from = st.seen < st.N && st.seen > 0 ? st.seen : 0;
        upto = Math.floor(lerp(from, st.N, ease(u)));
        if (u >= 1) { st.grow = false; upto = st.N; }
      }
      if (upto > st.drawn) paintDots(D, upto);
      g.save();
      g.translate(ccx, ccy);
      g.rotate(st.rot);
      g.drawImage(st.off, -D / (2 * k), -D / (2 * k), D / k, D / k);
      g.restore();
      const P = pal();
      // What arrived since you last looked: the rim it grew, lit once.
      if (st.seen < st.N && st.seen > 0) {
        if (!st.until) st.until = now + 6000;
        const left = st.until - now;
        if (left > 0) {
          const a = 0.5 * clamp(left / 6000, 0, 1) * (0.6 + 0.4 * Math.sin(now / 260));
          ring(g, ccx, ccy, Rc * Math.sqrt(st.seen / st.N), Rc * Math.sqrt(Math.min(upto, st.N) / st.N),
               rgba(P.gold, a * 0.5), rgba(P.gold, a));
        }
      }
      if (st.hover >= 0) {
        ring(g, ccx, ccy, Rc * Math.sqrt(st.cum[st.hover] / st.N),
             Math.max(Rc * Math.sqrt(st.cum[st.hover + 1] / st.N), Rc * Math.sqrt(st.cum[st.hover] / st.N) + 1.5),
             rgba(P.text, 0.16), rgba(P.text, 0.85));
      }
    }
    function ring(g, x, y, r0, r1, fill, stroke) {
      g.beginPath();
      g.arc(x, y, r1, 0, TAU);
      if (r0 > 0.5) g.arc(x, y, r0, 0, TAU, true);
      g.fillStyle = fill;
      g.fill('evenodd');
      g.lineWidth = 1;
      g.strokeStyle = stroke;
      g.beginPath(); g.arc(x, y, r1, 0, TAU); g.stroke();
      if (r0 > 0.5) { g.beginPath(); g.arc(x, y, r0, 0, TAU); g.stroke(); }
    }

    function tick(now) {
      if (!st.N) return false;
      const dt = st.last ? Math.min(64, now - st.last) : 16;
      st.last = now;
      const still = reduced();
      if (!still) st.rot += dt * 0.000035;
      draw(now);
      return !still || st.grow;
    }

    function hover(e) {
      if (!st.N) return;
      const r = f.cv.getBoundingClientRect();
      const x = e.clientX - r.left - r.width / 2, y = e.clientY - r.top - r.height / 2;
      const R = Math.min(r.width, r.height) * 0.47;
      const rn = Math.hypot(x, y) / R;
      let idx = -1;
      if (rn <= 1.01) {
        const target = clamp(rn * rn * st.N, 0, st.N - 1);
        let lo = 0, hi = st.rows.length - 1;
        while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (st.cum[mid] <= target) lo = mid; else hi = mid - 1; }
        idx = lo;
      }
      if (idx === st.hover) return;
      st.hover = idx;
      if (idx < 0) setRead(f.read, null, ['Point at a ring of the flower.']);
      else {
        const row = st.rows[idx];
        const kind = { ds: 'Dentate spikes', ied: 'P-spikes', pooled: 'Pooled: both detectors' }[row[1]] || 'Events (' + row[1] + ')';
        setRead(f.read, row[0], [kind + ' · ' + fmt(row[2]) + ' events',
                                 (row[4] || 'No project') + (row[3] ? ' · banked ' + day(new Date(row[3] * 1000).toISOString().slice(0, 10)) : ''),
                                 row[5] ? row[5] + ' saved versions' : 'One version']);
      }
      if (!sc.visible || !LOOP.on.has(sc)) draw(performance.now());
    }
    f.cv.addEventListener('pointermove', hover);
    f.cv.addEventListener('pointerleave', () => {
      if (st.hover < 0) return;
      st.hover = -1;
      setRead(f.read, null, ['Point at a ring of the flower.']);
      draw(performance.now());
    });
    setRead(f.read, null, ['Counting the bank…']);
    return Object.assign(sc, { set, draw: () => draw(performance.now()), tick,
                               needsLoop: () => !!st.N && (!reduced() || st.grow) });
  }

  /* ========================================================================
     Powers of Ten: from one sample to everything
     ======================================================================== */
  const animalWords = (name) => (!name || name === '?' ? 'animal not on record' : 'animal ' + name);
  const Z_TRACE = 0.40;      // the simulated trace ends at a minute here
  const Z_REC = 0.48;        // ... and has become the recording's own circle
  const Z_KEYS = [[Z_REC, 0], [0.66, 1], [0.84, 2], [1, 3]];   // recording, animal, project, all

  function Powers() {
    const f = sceneFrame('powers', 'Powers of Ten',
      'One real recording, from a single sample on every channel out to every recording Jarvis '
      + 'knows. Below a minute the trace is simulated; every circle after that is real, sized by '
      + 'the samples it holds. Drag the slider, scroll on the picture, or press Play.');
    const sc = { key: 'powers', node: f.sec, visible: false };
    const st = { tree: null, target: null, z: 1, play: null, played: false, hoverNode: null,
                 chain: null, total: 0 };
    const ctl = h('div', 'in-zoom');
    const playBtn = h('button', 'jx-btn', 'Play', { type: 'button' });
    const shuffle = h('button', 'jx-btn ghost', 'Another recording', { type: 'button' });
    const slider = h('input', 'in-slider', null, { type: 'range', min: '0', max: '1000', step: '1',
                                                    value: '1000', 'aria-label': 'Zoom' });
    slider.id = 'insideZoom';
    const stops = h('div', 'in-stops');
    ctl.append(playBtn, slider, shuffle);
    const sim = h('div', 'in-sim', 'Simulated trace');
    f.stage.append(sim);
    const big = h('div', 'in-zoom-big');
    const bigNum = h('strong', null, '');
    const bigWord = h('span', null, '');
    big.append(bigNum, bigWord);
    f.aside.insertBefore(big, f.aside.firstChild);
    f.sec.querySelector('.in-scene-grid').after(ctl, stops);

    /* -- the real part: recordings packed into animals, projects, all -- */
    function pack(cs) {
      const n = cs.length;
      if (!n) return 0;
      cs.sort((a, b) => b.r - a.r);
      const span = Math.sqrt(cs.reduce((s, c) => s + c.r * c.r, 0));
      cs.forEach((c, i) => {
        const rr = span * Math.sqrt((i + 0.5) / n), t = i * GOLD;
        c.x = rr * Math.cos(t); c.y = rr * Math.sin(t);
      });
      for (let it = 0; it < 140; it++) {
        const pull = it < 110 ? 0.985 : 1;
        for (const c of cs) { c.x *= pull; c.y *= pull; }
        for (let i = 0; i < n; i++) {
          const a = cs[i];
          for (let j = i + 1; j < n; j++) {
            const b = cs[j];
            const dx = b.x - a.x, dy = b.y - a.y;
            const min = (a.r + b.r) * 1.05;
            if (Math.abs(dx) > min || Math.abs(dy) > min) continue;
            const d = Math.hypot(dx, dy) || 1e-6;
            if (d >= min) continue;
            const push = (min - d) / d;
            const wa = (b.r * b.r) / (a.r * a.r + b.r * b.r), wb = 1 - wa;
            a.x -= dx * push * wa; a.y -= dy * push * wa;
            b.x += dx * push * wb; b.y += dy * push * wb;
          }
        }
      }
      let cx = 0, cy = 0, m = 0;
      cs.forEach((c) => { const w = c.r * c.r; cx += c.x * w; cy += c.y * w; m += w; });
      cx /= m; cy /= m;
      let R = 0;
      cs.forEach((c) => { c.x -= cx; c.y -= cy; R = Math.max(R, Math.hypot(c.x, c.y) + c.r); });
      return R * 1.04;
    }
    function place(node, ox, oy) {
      node.ax = ox + (node.x || 0);
      node.ay = oy + (node.y || 0);
      (node.kids || []).forEach((k) => place(k, node.ax, node.ay));
    }
    function build(part) {
      const rows = part.rows || [];
      const sizes = rows.filter((r) => r[3] && r[4] && r[5]).map((r) => r[3] * r[4] * r[5]).sort((a, b) => a - b);
      const med = sizes.length ? sizes[sizes.length >> 1] : 1e9;
      const projects = new Map();
      rows.forEach((r) => {
        const size = r[3] && r[4] && r[5] ? r[3] * r[4] * r[5] : null;
        let p = projects.get(r[0]);
        if (!p) { p = { kind: 'project', name: r[0], m: new Map(), samples: 0, n: 0 }; projects.set(r[0], p); }
        let a = p.m.get(r[1]);
        if (!a) { a = { kind: 'animal', name: r[1], project: r[0], kids: [], samples: 0, n: 0, seconds: 0 }; p.m.set(r[1], a); }
        a.kids.push({ kind: 'rec', row: r, samples: size, r: Math.sqrt(size || med) });
        a.samples += size || 0; a.n += 1; a.seconds += r[3] || 0;
        p.samples += size || 0; p.n += 1;
      });
      const names = Array.from(projects.keys()).sort();
      const plist = [];
      for (const p of projects.values()) {
        p.kids = Array.from(p.m.values());
        p.kids.forEach((a) => { a.r = pack(a.kids); });
        p.r = pack(p.kids);
        p.hue = p.name === 'Unfiled' ? 5 : (names.filter((n) => n !== 'Unfiled').indexOf(p.name) % 4) + 1;
        delete p.m;
        plist.push(p);
      }
      const root = { kind: 'all', name: 'everything', kids: plist, samples: plist.reduce((s, p) => s + p.samples, 0),
                     n: rows.length, projects: plist.length };
      root.r = pack(plist);
      root.x = 0; root.y = 0;
      place(root, 0, 0);
      return root;
    }
    function leaves(root) {
      const out = [];
      root.kids.forEach((p) => p.kids.forEach((a) => a.kids.forEach((l) => { if (l.samples) out.push([l, a, p]); })));
      return out;
    }
    function pick(seed) {
      const all = leaves(st.tree);
      if (!all.length) return null;
      // A recording with enough channels to look like one, when there is.
      const good = all.filter(([l]) => (l.row[4] || 0) >= 16);
      const from = good.length ? good : all;
      const [leaf, animal, project] = from[Math.floor(hash(seed) * from.length) % from.length];
      return [leaf, animal, project, st.tree];
    }
    function set(part) {
      const keep = st.chain && st.chain[0].row[6];
      st.tree = build(part);
      st.total = st.tree.samples;
      st.chain = null;
      if (keep) {
        for (const [l, a, p] of leaves(st.tree)) if (l.row[6] === keep) { st.chain = [l, a, p, st.tree]; break; }
      }
      if (!st.chain) st.chain = pick(strHash(new Date().toISOString().slice(0, 10)));
      setFacts(f.facts, [['Recordings', fmt(st.tree.n)], ['Projects', fmt(st.tree.projects)],
                         ['Animals', fmt(st.tree.kids.reduce((s, p) => s + p.kids.length, 0))],
                         ['Samples, where known', bigWords(st.total)]]);
      const P = pal();
      setLegend(f.legend, st.tree.kids.slice().sort((a, b) => b.n - a.n)
        .map((p) => [P['c' + p.hue], p.name + ' · ' + fmt(p.n)]));
      buildStops();
      if (!st.played && !reduced() && sc.visible) startPlay(0);
      draw();
    }

    /* -- the simulated part: a dentate gyrus recording, any window -- */
    const FS = 30000, NCH = 12, DS_EVERY = 1.37, P_EVERY = 7.9;
    const dsAt = (i) => i * DS_EVERY + 0.35 * hash(i * 7 + 1);
    const pAt = (j) => j * P_EVERY + 2.3 + 1.7 * hash(j * 11 + 3);
    const T0 = dsAt(40);
    function events(c, t) {
      let v = 0;
      const i0 = Math.floor((t - 0.06) / DS_EVERY) - 1;
      for (let i = i0; i <= i0 + 3; i++) {
        if (i < 0) continue;
        const d = t - dsAt(i);
        if (Math.abs(d) > 0.04) continue;
        const amp = c >= 6 ? 2.6 * (1 - Math.abs(c - 8.5) * 0.22) : -0.55 * (c / 6);
        v += amp * Math.exp(-(d * d) / (2 * 0.006 * 0.006));
      }
      const j0 = Math.floor((t - 2.3 - 0.05) / P_EVERY) - 1;
      for (let j = j0; j <= j0 + 2; j++) {
        if (j < 0) continue;
        const d = t - pAt(j);
        if (Math.abs(d) > 0.03) continue;
        v += -3.2 * (0.8 + 0.02 * c) * (Math.exp(-(d * d) / (2 * 0.0028 * 0.0028))
                                        - 0.42 * Math.exp(-((d - 0.007) * (d - 0.007)) / (2 * 0.005 * 0.005)));
      }
      return v;
    }
    function eventNear(t, half) {
      const i = Math.round((t - 0.17) / DS_EVERY);
      for (let k = i - 1; k <= i + 1; k++) if (k >= 0 && Math.abs(t - dsAt(k)) <= half) return 'ds';
      const j = Math.round((t - 3.1) / P_EVERY);
      for (let k = j - 1; k <= j + 1; k++) if (k >= 0 && Math.abs(t - pAt(k)) <= half) return 'p';
      return null;
    }
    function smooth(x, c) {
      const i = Math.floor(x), u = x - i, a = hash(i * 31 + c * 977), b = hash((i + 1) * 31 + c * 977);
      return lerp(a, b, u * u * (3 - 2 * u)) - 0.5;
    }
    function sig(c, t) {
      const k = Math.floor(t * FS);
      return 0.55 * Math.sin(TAU * 7.6 * t + c * 0.22) + 0.25 * Math.sin(TAU * 0.7 * t + c * 0.05)
        + 0.12 * Math.sin(TAU * 41 * t + c * 1.3) * (0.6 + 0.4 * Math.sin(TAU * 7.6 * t))
        + 0.09 * (hash(k * 13 + c * 101) - 0.5) + 0.22 * smooth(k / 40, c) + events(c, t);
    }

    const windowAt = (z) => Math.pow(10, lerp(Math.log10(1 / FS), Math.log10(60), clamp(z / Z_TRACE, 0, 1)));

    function drawTrace(g, w, hh, z, alpha) {
      const P = pal();
      const W = windowAt(z);
      const t0 = T0 - W / 2;
      const top = 18, rowH = (hh - top - 34) / NCH, amp = rowH * 0.42;
      const n = W * FS;
      g.save();
      g.globalAlpha = alpha;
      g.lineJoin = 'round';
      for (let c = 0; c < NCH; c++) {
        const y0 = top + (c + 0.5) * rowH;
        g.strokeStyle = rgba(P.line, 0.6);
        g.lineWidth = 1;
        g.beginPath(); g.moveTo(0, y0); g.lineTo(w, y0); g.stroke();
        if (n <= 600) {
          // Few enough to be samples: each one a point, the line between.
          const k0 = Math.ceil(t0 * FS), k1 = Math.floor((t0 + W) * FS);
          const kk = [];
          for (let k = k0; k <= Math.max(k0, k1); k++) kk.push(k);
          if (k1 < k0) kk.length = 1;
          g.strokeStyle = rgba(P.text2, 0.8);
          g.lineWidth = 1.25;
          g.beginPath();
          kk.forEach((k, i) => {
            const x = kk.length === 1 ? w / 2 : ((k / FS - t0) / W) * w;
            const y = y0 - sig(c, k / FS) * amp;
            if (i === 0) g.moveTo(x, y); else g.lineTo(x, y);
          });
          if (kk.length > 1) g.stroke();
          const dot = n <= 80 ? clamp(5 - n / 20, 2, 4.5) : 1.4;
          kk.forEach((k) => {
            const x = kk.length === 1 ? w / 2 : ((k / FS - t0) / W) * w;
            const v = sig(c, k / FS), y = y0 - v * amp;
            const ev = eventNear(k / FS, 0.012);
            g.fillStyle = ev === 'ds' ? P.ds : ev === 'p' ? P.p : P.text;
            if (n <= 80) {
              g.strokeStyle = rgba(P.text3, 0.7);
              g.beginPath(); g.moveTo(x, y0); g.lineTo(x, y); g.stroke();
            }
            g.beginPath(); g.arc(x, y, dot, 0, TAU); g.fill();
          });
        } else {
          // More samples than pixels: the trace as its envelope, column by
          // column, with every event's peak kept so none is stepped over.
          const cols = Math.ceil(w);
          const per = 8;
          g.strokeStyle = rgba(P.text2, 0.85);
          g.lineWidth = 1;
          g.beginPath();
          for (let x = 0; x < cols; x++) {
            const ta = t0 + (x / w) * W, tb = t0 + ((x + 1) / w) * W;
            let lo = Infinity, hi = -Infinity;
            for (let s = 0; s < per; s++) {
              const v = sig(c, lerp(ta, tb, (s + 0.5) / per));
              if (v < lo) lo = v; if (v > hi) hi = v;
            }
            if (x === 0) g.moveTo(x + 0.5, y0 - hi * amp);
            g.lineTo(x + 0.5, y0 - hi * amp);
            g.lineTo(x + 0.5, y0 - lo * amp);
          }
          g.stroke();
          // The events, in their colours, at their true peaks.
          const marks = [];
          const i0 = Math.max(0, Math.floor(t0 / DS_EVERY) - 1), i1 = Math.ceil((t0 + W) / DS_EVERY) + 1;
          for (let i = i0; i <= i1; i++) marks.push([dsAt(i), 'ds']);
          const j0 = Math.max(0, Math.floor((t0 - 2.3) / P_EVERY) - 1), j1 = Math.ceil((t0 + W) / P_EVERY) + 1;
          for (let j = j0; j <= j1; j++) marks.push([pAt(j), 'p']);
          marks.forEach(([te, kind]) => {
            if (te < t0 || te > t0 + W) return;
            const span = kind === 'ds' ? 0.02 : 0.012;
            const xa = ((te - span - t0) / W) * w, xb = ((te + span - t0) / W) * w;
            g.strokeStyle = kind === 'ds' ? P.ds : P.p;
            g.lineWidth = 1.6;
            g.beginPath();
            const steps = Math.max(6, Math.ceil(xb - xa) * 2);
            for (let s = 0; s <= steps; s++) {
              const t = lerp(te - span, te + span, s / steps);
              const x = ((t - t0) / W) * w, y = y0 - sig(c, t) * amp;
              if (s === 0) g.moveTo(x, y); else g.lineTo(x, y);
            }
            g.stroke();
          });
        }
      }
      // The scale: a bar a fifth of the width, and what it measures.
      const bar = w * 0.2;
      g.strokeStyle = P.text2;
      g.lineWidth = 2;
      g.beginPath(); g.moveTo(14, hh - 14); g.lineTo(14 + bar, hh - 14); g.stroke();
      label(g, duration(W * 0.2), 14 + bar + 8, hh - 14, { align: 'left', color: P.text2, weight: '500' });
      g.restore();
    }

    /* -- the camera -- */
    function view(z) {
      const ch = st.chain;
      if (z <= Z_REC) return { x: ch[0].ax, y: ch[0].ay, r: ch[0].r, u: 0, seg: 0 };
      for (let i = 0; i < Z_KEYS.length - 1; i++) {
        const [za, ia] = Z_KEYS[i], [zb, ib] = Z_KEYS[i + 1];
        if (z > zb) continue;
        const a = ch[ia], b = ch[ib];
        const u = (z - za) / (zb - za);
        const r = Math.exp(lerp(Math.log(a.r), Math.log(Math.max(b.r, a.r * 1.0001)), easeIO(u)));
        const wgt = Math.abs(b.r - a.r) < 1e-9 ? u : clamp((r - a.r) / (b.r - a.r), 0, 1);
        return { x: lerp(a.ax, b.ax, wgt), y: lerp(a.ay, b.ay, wgt), r, u, seg: i };
      }
      const t = ch[3];
      return { x: t.ax, y: t.ay, r: t.r, u: 1, seg: 2 };
    }

    function drawCircles(g, w, hh, z, alpha) {
      const P = pal();
      const v = view(z);
      const s = (Math.min(w, hh) / 2 * 0.92) / v.r;
      const X = (x) => w / 2 + (x - v.x) * s, Y = (y) => hh / 2 + (y - v.y) * s;
      const vis = (n) => { const r = n.r * s, x = X(n.ax), y = Y(n.ay); return x + r > 0 && x - r < w && y + r > 0 && y - r < hh; };
      const boxes = [];
      g.save();
      g.globalAlpha = alpha;
      const root = st.tree;
      g.strokeStyle = rgba(P.text3, 0.45);
      g.lineWidth = 1;
      g.beginPath(); g.arc(X(root.ax), Y(root.ay), root.r * s, 0, TAU); g.stroke();
      const later = [];
      root.kids.forEach((p) => {
        if (!vis(p)) return;
        const col = P['c' + p.hue];
        const pr = p.r * s;
        g.fillStyle = rgba(col, 0.06);
        g.strokeStyle = rgba(col, 0.55);
        g.beginPath(); g.arc(X(p.ax), Y(p.ay), pr, 0, TAU); g.fill(); g.stroke();
        if (pr > 26 && pr < hh * 0.75) later.push(() => label(g, p.name + ' · ' + fmt(p.n), X(p.ax), Y(p.ay) - Math.min(pr, hh) * 0.86, { boxes, color: P.text }));
        if (pr < 3) return;
        p.kids.forEach((a) => {
          const ar = a.r * s;
          if (ar < 0.6 || !vis(a)) return;
          g.strokeStyle = rgba(P.text3, 0.5);
          g.beginPath(); g.arc(X(a.ax), Y(a.ay), ar, 0, TAU); g.stroke();
          if (ar > 34 && ar < hh * 0.75) later.push(() => label(g, animalWords(a.name), X(a.ax), Y(a.ay) - ar * 0.8, { boxes, color: P.text2, weight: '500' }));
          if (ar < 2) return;
          a.kids.forEach((l) => {
            const lr = l.r * s;
            if (lr < 0.4) return;
            const lx = X(l.ax), ly = Y(l.ay);
            if (lx + lr < 0 || lx - lr > w || ly + lr < 0 || ly - lr > hh) return;
            g.beginPath(); g.arc(lx, ly, Math.max(lr, 0.6), 0, TAU);
            if (l.samples) { g.fillStyle = rgba(col, 0.5); g.fill(); }
            else {
              g.setLineDash([3, 3]); g.strokeStyle = rgba(col, 0.75); g.stroke(); g.setLineDash([]);
            }
            if (lr > 22 && l.row[4]) {
              // A recording, close up: one line a channel.
              g.save();
              g.beginPath(); g.arc(lx, ly, lr, 0, TAU); g.clip();
              const nch = Math.min(64, l.row[4]);
              g.strokeStyle = rgba(P.text, 0.18);
              g.lineWidth = 1;
              for (let c = 0; c < nch; c++) {
                const yy = ly - lr + (c + 0.5) * (2 * lr / nch);
                g.beginPath(); g.moveTo(lx - lr, yy); g.lineTo(lx + lr, yy); g.stroke();
              }
              g.restore();
            }
            if (l === st.chain[0]) {
              g.strokeStyle = P.gold; g.lineWidth = 2;
              g.beginPath(); g.arc(lx, ly, Math.max(lr, 3) + 2, 0, TAU); g.stroke();
              g.lineWidth = 1;
            }
            if (st.hoverNode === l) {
              g.strokeStyle = P.text; g.lineWidth = 1.5;
              g.beginPath(); g.arc(lx, ly, Math.max(lr, 2) + 1, 0, TAU); g.stroke();
              g.lineWidth = 1;
            }
          });
        });
      });
      later.forEach((fn) => fn());
      g.restore();
      return { v, s, X, Y };
    }

    let geom = null;
    function draw() {
      const { g, w, h: hh } = fit(f.cv);
      g.clearRect(0, 0, w, hh);
      if (!st.tree || !st.chain) return;
      const z = st.z;
      geom = null;
      if (z < Z_REC) drawTrace(g, w, hh, Math.min(z, Z_TRACE), z <= Z_TRACE ? 1 : 1 - (z - Z_TRACE) / (Z_REC - Z_TRACE));
      if (z > Z_TRACE) geom = drawCircles(g, w, hh, z, z >= Z_REC ? 1 : (z - Z_TRACE) / (Z_REC - Z_TRACE));
      sim.hidden = z >= Z_REC;
      readout(z);
      slider.value = String(Math.round(z * 1000));
    }

    function samplesAt(z) {
      const ch = st.chain;
      const nch = ch[0].row[4] || 1;
      if (z <= Z_TRACE) return Math.max(1, windowAt(z) * FS) * nch;
      if (z <= Z_REC) {
        const a = Math.log(windowAt(Z_TRACE) * FS * nch), b = Math.log(ch[0].samples);
        return Math.exp(lerp(a, b, (z - Z_TRACE) / (Z_REC - Z_TRACE)));
      }
      const v = view(z);
      const [za, ia] = Z_KEYS[v.seg], [, ib] = Z_KEYS[v.seg + 1] || Z_KEYS[v.seg];
      const a = ch[ia].samples || 1, b = ch[ib].samples || 1;
      return Math.exp(lerp(Math.log(a), Math.log(b), easeIO(v.u)));
    }
    let lastWords = '';
    function readout(z) {
      const ch = st.chain;
      const [l, a, p] = ch;
      const n = samplesAt(z);
      bigNum.textContent = z >= 0.995 ? fmt(st.total) : n < 1e6 ? fmt(n) : bigWords(n);
      // A number too long for the column steps down a size rather than
      // breaking between its digits.
      bigNum.classList.toggle('long', bigNum.textContent.length > 11);
      let words;
      if (z <= Z_TRACE) {
        const W = windowAt(z);
        words = W * FS < 1.5 ? 'samples in view: one moment, on every channel of ' + l.row[6]
          : 'samples in view: ' + duration(W) + ' of ' + l.row[6] + ', on ' + l.row[4] + ' channels';
      } else if (z < 0.57) {
        words = 'samples in this recording: ' + l.row[6] + ', ' + duration(l.row[3]) + ' on ' + l.row[4] + ' channels';
      } else if (z < 0.75) {
        words = 'samples in this animal: ' + p.name + ', ' + animalWords(a.name) + ', ' + fmt(a.n) + ' recordings';
      } else if (z < 0.92) {
        words = 'samples in this project: ' + p.name + ', ' + fmt(p.n) + ' recordings';
      } else {
        words = 'samples in everything Jarvis knows: ' + fmt(st.tree.n) + ' recordings in '
          + st.tree.projects + ' projects';
      }
      if (words !== lastWords) { bigWord.textContent = words; lastWords = words; }
      const ticks = stops.querySelectorAll('button');
      ticks.forEach((b) => b.classList.toggle('on', Math.abs(Number(b.dataset.z) - z) < 0.012));
    }

    function buildStops() {
      stops.textContent = '';
      const zOf = (sec) => Z_TRACE * (Math.log10(sec) - Math.log10(1 / FS)) / (Math.log10(60) - Math.log10(1 / FS));
      [[0, 'one sample'], [zOf(1e-3), 'a millisecond'], [zOf(0.08), 'a dentate spike'], [zOf(1), 'a second'],
       [Z_TRACE, 'a minute'], [Z_REC, 'a recording'], [0.66, 'an animal'], [0.84, 'a project'], [1, 'everything']]
        .forEach(([z, words]) => {
          const b = h('button', 'in-stop', words, { type: 'button' });
          b.dataset.z = String(z);
          b.addEventListener('click', () => { stopPlay(); tween(z, 900); });
          stops.append(b);
        });
    }

    /* Every move ends on a timer as well as on its last frame: under the
       harness runner's virtual time frames stall, and a zoom left half way
       would read the wrong number. */
    function endOn(p) {
      clearTimeout(st.endTimer);
      st.endTimer = setTimeout(() => {
        if (st.play !== p) return;
        st.z = p.to;
        stopPlay();
        draw();
      }, p.ms + 120);
    }
    function tween(to, ms) {
      if (reduced()) { st.z = to; draw(); return; }
      st.play = { from: st.z, to, t0: 0, ms, kind: 'tween' };
      endOn(st.play);
      wake(sc);
    }
    function startPlay(from) {
      st.played = true;
      if (reduced()) { st.z = 1; draw(); return; }
      st.z = from;
      st.play = { from, to: 1, t0: 0, ms: 15000 * (1 - from) + 1500, kind: 'play' };
      endOn(st.play);
      playBtn.textContent = 'Pause';
      draw();
      wake(sc);
    }
    function stopPlay() {
      if (st.play && st.play.kind === 'play') playBtn.textContent = 'Play';
      st.play = null;
    }
    function tick(now) {
      if (!st.play) return false;
      const p = st.play;
      if (!p.t0) p.t0 = now;
      const u = (now - p.t0) / p.ms;
      st.z = lerp(p.from, p.to, p.kind === 'play' ? u * u * (3 - 2 * u) * 0.5 + u * 0.5 : easeIO(u));
      if (u >= 1) { st.z = p.to; stopPlay(); }
      draw();
      return !!st.play;
    }

    playBtn.addEventListener('click', () => {
      if (st.play && st.play.kind === 'play') { stopPlay(); return; }
      startPlay(st.z >= 0.995 ? 0 : st.z);
    });
    shuffle.addEventListener('click', () => {
      if (!st.tree) return;
      st.chain = pick(Math.floor(Math.random() * 1e9));
      draw();
    });
    slider.addEventListener('input', () => { stopPlay(); st.z = Number(slider.value) / 1000; draw(); });
    f.cv.addEventListener('wheel', (e) => {
      if (!st.tree) return;
      e.preventDefault();
      stopPlay();
      st.z = clamp(st.z + e.deltaY * 0.0005, 0, 1);
      draw();
    }, { passive: false });
    f.cv.addEventListener('pointermove', (e) => {
      if (!geom || !st.tree) return;
      const r = f.cv.getBoundingClientRect();
      const mx = e.clientX - r.left, my = e.clientY - r.top;
      let found = null;
      for (const p of st.tree.kids) {
        for (const a of p.kids) {
          for (const l of a.kids) {
            const dx = geom.X(l.ax) - mx, dy = geom.Y(l.ay) - my, lr = Math.max(l.r * geom.s, 3);
            if (dx * dx + dy * dy <= lr * lr) { found = [l, a, p]; break; }
          }
          if (found) break;
        }
        if (found) break;
      }
      const l = found && found[0];
      if (st.hoverNode === l) return;
      st.hoverNode = l;
      if (!found) setRead(f.read, null, ['Point at a circle: each one is a real recording.']);
      else {
        const row = l.row;
        setRead(f.read, row[6], [found[2].name + ' · ' + animalWords(found[1].name),
                                 row[3] ? duration(row[3]) + ' on ' + (row[4] || '?') + ' channels' : 'Length not on record',
                                 l.samples ? bigWords(l.samples) + ' samples' : 'Samples unknown: drawn at the median size, dashed']);
      }
      if (!st.play) draw();
    });
    setRead(f.read, null, ['Point at a circle: each one is a real recording.']);
    return Object.assign(sc, { set, draw, tick, onShow: () => { if (!st.played && st.tree && !reduced()) startPlay(0); },
                               needsLoop: () => !!st.play });
  }

  /* ========================================================================
     The Gyrus: every version a granule cell
     ======================================================================== */
  function Gyrus() {
    const f = sceneFrame('gyrus', 'The Gyrus',
      'Every version of Jarvis as a granule cell along a dentate gyrus, the oldest at the top '
      + 'blade. Each cell’s dendrites are its own patch note: one branch for each change, '
      + 'a twig for each of its parts. Its axons run out to the tools it changed. The cells '
      + 'of the last seven days are lit.');
    const sc = { key: 'gyrus', node: f.sec, visible: false };
    const st = { part: null, cells: null, tools: null, grow: 1, t0: 0, growing: false, base: null,
                 hover: null, seenN: 0, lastSig: '' };
    const playBtn = h('button', 'jx-btn ghost in-replay', 'Grow it again', { type: 'button' });
    const when = h('div', 'in-when');
    f.stage.append(when);
    f.aside.append(playBtn);

    function layout(w, hh) {
      const vs = st.part.versions;
      const n = vs.length;
      const cx = w * 0.40, cy = hh * 0.5, ax = Math.min(w * 0.25, hh * 0.52), ay = hh * 0.33;
      const th0 = (318 * Math.PI) / 180, th1 = (42 * Math.PI) / 180;
      const cut = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
      const cells = vs.map((v, i) => {
        const u = n > 1 ? i / (n - 1) : 0.5;
        const th = lerp(th0, th1, u);          // top blade, round the crest, to the lower blade
        const rnd = seeded(strHash(v.v));
        const jit = (rnd() - 0.5) * 9;
        let nx = Math.cos(th) / ax, ny = Math.sin(th) / ay;
        const nl = Math.hypot(nx, ny); nx /= nl; ny /= nl;
        const x = cx + ax * Math.cos(th) + nx * jit, y = cy + ay * Math.sin(th) + ny * jit;
        return { v, i, x, y, nx, ny, rnd, recent: v.day >= cut, segs: null, at: (i + 1) / n };
      });
      // CA3: the tools, on an arc beyond the gyrus's open end.
      const used = new Map();
      cells.forEach((c) => (c.v.tools || []).forEach((t) => used.set(t, (used.get(t) || 0) + 1)));
      const order = Array.from(used.keys()).sort((a, b) => a - b);
      // Evenly down the height, bowed a little: an even step is what lets
      // every one of them keep its name.
      const tools = order.map((t, i) => {
        const u = order.length > 1 ? i / (order.length - 1) : 0.5;
        const ang = lerp(-1.1, 1.1, u);
        return { t, name: st.part.tools[t], n: used.get(t),
                 x: w * 0.78 + Math.cos(ang) * w * 0.045, y: lerp(hh * 0.05, hh * 0.95, u) };
      });
      const byT = new Map(tools.map((t) => [t.t, t]));
      // Dendrites: the outline of the patch note, grown outward.
      const reach = Math.min(w, hh) * 0.17;
      cells.forEach((c) => {
        const segs = [];
        const words = Math.max(20, c.v.words || 20);
        const L0 = reach * clamp(0.32 + Math.log10(words) * 0.12, 0.35, 0.62);
        const base = Math.atan2(c.ny, c.nx);
        const grow = (x, y, ang, len, kids, depth, t0, t1) => {
          const x2 = x + Math.cos(ang) * len, y2 = y + Math.sin(ang) * len;
          segs.push([x, y, x2, y2, depth, t0, t1]);
          const m = kids.length;
          if (!m) {
            if (depth < 4) {
              // Every tip ends as a fork, the way a dendrite does.
              [-1, 1].forEach((sgn) => grow(x2, y2, ang + sgn * (0.28 + c.rnd() * 0.2), len * 0.5, [], depth + 9, t1, t1 + (t1 - t0) * 0.6));
            }
            return;
          }
          const spread = Math.min(1.25, 0.32 * m + 0.2);
          kids.forEach((k, i) => {
            const a2 = ang + (m === 1 ? (c.rnd() - 0.5) * 0.3 : lerp(-spread / 2, spread / 2, i / (m - 1))) + (c.rnd() - 0.5) * 0.18;
            grow(x2, y2, a2, len * (0.66 + c.rnd() * 0.12), k, depth + 1, t1, t1 + (t1 - t0) * 0.85);
          });
        };
        const top = c.v.tree && c.v.tree.length ? c.v.tree : [[]];
        grow(c.x, c.y, base, L0 * 0.35, top, 0, 0, 0.25);
        c.segs = segs;
        c.fibres = (c.v.tools || []).map((t) => byT.get(t)).filter(Boolean);
      });
      return { cells, tools, cx, cy };
    }

    function set(part, seenVersions) {
      const sig = part.versions.length + ':' + (part.versions.length ? part.versions[part.versions.length - 1].v : '');
      st.part = part;
      st.seenN = seenVersions == null ? part.versions.length : Math.min(seenVersions, part.versions.length);
      const vs = part.versions;
      const cut = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
      const week = vs.filter((v) => v.day >= cut).length;
      const commits = Object.values(part.commits || {}).reduce((s, n) => s + n, 0);
      setFacts(f.facts, [['Versions', fmt(vs.length)], ['In the last 7 days', fmt(week)],
                         ['Commits', fmt(commits)], ['First', vs.length ? day(vs[0].day) : '—']]);
      const P = pal();
      setLegend(f.legend, [[P.gold, 'A version of the last 7 days'], [P.c2, 'An older version'],
                           [P.c3, 'A tool it changed']]);
      st.layoutKey = '';
      if (sig !== st.lastSig) {
        st.lastSig = sig;
        st.t0 = 0;
        st.growing = !reduced();
        st.grow = st.growing ? (st.seenN < vs.length && st.seenN > 0 ? st.seenN / vs.length : 0) : 1;
        st.growFrom = st.grow;
        st.armed = false;
        if (st.growing && sc.visible) endGrowth();
      }
      if (!st.hover) setRead(f.read, null, ['Point at a cell to read its version.']);
      draw();
      if (sc.visible && st.growing) wake(sc);
    }

    function ensure(w, hh) {
      const key = w + 'x' + hh + ':' + st.lastSig;
      if (st.layoutKey !== key) { st.L = layout(w, hh); st.layoutKey = key; }
      return st.L;
    }

    function draw() {
      const { g, w, h: hh } = fit(f.cv);
      g.clearRect(0, 0, w, hh);
      if (!st.part || !st.part.versions.length) return;
      const L = ensure(w, hh);
      const P = pal();
      const T = st.grow;               // 0..1 of the history shown
      const shown = L.cells.filter((c) => c.at <= T + 1e-9 || c.at - 1 / L.cells.length < T);
      const hi = st.hover;
      // Mossy fibres first, under everything.
      g.lineWidth = 1;
      shown.forEach((c) => {
        const lit = hi && (hi.cell === c || (hi.tool && c.fibres.indexOf(hi.tool) >= 0));
        c.fibres.forEach((t) => {
          if (hi && hi.tool && t !== hi.tool && !lit) return;
          g.strokeStyle = lit ? rgba(P.c3, 0.75) : rgba(P.c3, c.recent ? 0.16 : 0.055);
          g.beginPath();
          g.moveTo(c.x, c.y);
          g.bezierCurveTo(L.cx + (c.x - L.cx) * 0.25, L.cy + (c.y - L.cy) * 0.25, t.x - 90, t.y, t.x, t.y);
          g.stroke();
        });
      });
      // Dendrites.
      shown.forEach((c) => {
        const local = clamp((T - (c.at - 1 / L.cells.length)) * L.cells.length, 0, 1);
        const col = c.recent ? P.gold : P.c2;
        const lit = hi && hi.cell === c;
        const dim = hi && !lit;
        g.strokeStyle = rgba(col, dim ? 0.12 : lit ? 0.95 : c.recent ? 0.7 : 0.32);
        c.segs.forEach((s) => {
          if (s[5] >= local) return;
          const u = clamp((local - s[5]) / Math.max(1e-6, s[6] - s[5]), 0, 1);
          g.lineWidth = s[4] >= 9 ? 0.6 : s[4] === 0 ? 1.6 : Math.max(0.7, 1.4 - s[4] * 0.25);
          g.beginPath();
          g.moveTo(s[0], s[1]);
          g.lineTo(lerp(s[0], s[2], u), lerp(s[1], s[3], u));
          g.stroke();
        });
      });
      // Somata on top.
      shown.forEach((c) => {
        const lit = hi && hi.cell === c;
        g.fillStyle = c.recent || lit ? P.gold : P.c2;
        g.strokeStyle = P.bg2;
        g.lineWidth = 1.5;
        g.beginPath();
        g.ellipse(c.x, c.y, lit ? 4.6 : c.recent ? 3.6 : 2.6, lit ? 3.6 : c.recent ? 2.8 : 2, Math.atan2(c.ny, c.nx), 0, TAU);
        g.fill();
        g.stroke();
      });
      // CA3: the tools.
      const boxes = [];
      const sorted = L.tools.slice().sort((a, b) => b.n - a.n);
      L.tools.forEach((t) => {
        const lit = hi && (hi.tool === t || (hi.cell && hi.cell.fibres.indexOf(t) >= 0));
        g.fillStyle = lit ? P.text : P.c3;
        g.strokeStyle = P.bg2;
        g.lineWidth = 2;
        g.beginPath(); g.arc(t.x, t.y, 2.5 + Math.sqrt(t.n) * 0.9, 0, TAU); g.fill(); g.stroke();
      });
      sorted.forEach((t) => {
        const lit = hi && (hi.tool === t || (hi.cell && hi.cell.fibres.indexOf(t) >= 0));
        label(g, t.name, t.x + 8 + Math.sqrt(t.n) * 0.9, t.y, { align: 'left', boxes, size: 11,
                                                                color: lit ? P.text : P.text2, weight: lit ? '700' : '500' });
      });
      const lastShown = shown.length ? shown[shown.length - 1].v : null;
      when.textContent = lastShown ? day(lastShown.day) + ' · v' + lastShown.v : '';
      when.hidden = !st.growing;
    }

    function tick(now) {
      if (!st.growing) return false;
      if (!st.t0) st.t0 = now;
      const dur = 7000 * (1 - (st.growFrom || 0)) + 900;
      const u = (now - st.t0) / dur;
      st.grow = lerp(st.growFrom || 0, 1, clamp(u, 0, 1));
      if (u >= 1) { st.grow = 1; st.growing = false; }
      draw();
      return st.growing;
    }
    /* The growth starts when the picture is first on screen, and ends on a
       timer too (frames stall under the harness runner). */
    function endGrowth() {
      clearTimeout(st.endTimer);
      st.armed = true;
      st.endTimer = setTimeout(() => {
        if (!st.growing) return;
        st.grow = 1; st.growing = false;
        draw();
      }, 7000 * (1 - (st.growFrom || 0)) + 2500);
    }
    playBtn.addEventListener('click', () => {
      if (reduced() || !st.part) return;
      st.growFrom = 0; st.grow = 0; st.t0 = 0; st.growing = true;
      endGrowth();
      wake(sc);
    });

    f.cv.addEventListener('pointermove', (e) => {
      if (!st.L) return;
      const r = f.cv.getBoundingClientRect();
      const mx = e.clientX - r.left, my = e.clientY - r.top;
      let best = null, bd = 100;
      st.L.cells.forEach((c) => { const d = (c.x - mx) ** 2 + (c.y - my) ** 2; if (d < bd) { bd = d; best = { cell: c }; } });
      if (!best) {
        let td = 144;
        st.L.tools.forEach((t) => { const d = (t.x - mx) ** 2 + (t.y - my) ** 2; if (d < td) { td = d; best = { tool: t }; } });
      }
      const same = (a, b) => (!a && !b) || (a && b && a.cell === b.cell && a.tool === b.tool);
      if (same(best, st.hover)) return;
      st.hover = best;
      if (!best) setRead(f.read, null, ['Point at a cell to read its version.']);
      else if (best.cell) {
        const v = best.cell.v;
        const parts = (v.tree || []).length;
        const commits = (st.part.commits || {})[v.day];
        setRead(f.read, 'v' + v.v + ' · ' + day(v.day), [v.title,
          parts + (parts === 1 ? ' change, ' : ' changes, ') + fmt(v.words) + ' words of notes',
          (best.cell.fibres.length ? 'Changed ' + best.cell.fibres.map((t) => t.name).join(', ') : 'No tool named')
            + (commits ? ' · ' + commits + ' commits that day' : '')]);
      } else {
        setRead(f.read, best.tool.name, ['Named in ' + fmt(best.tool.n) + ' versions']);
      }
      if (!st.growing) draw();
    });
    f.cv.addEventListener('pointerleave', () => {
      if (!st.hover) return;
      st.hover = null;
      setRead(f.read, null, ['Point at a cell to read its version.']);
      if (!st.growing) draw();
    });
    return Object.assign(sc, { set, draw, tick, needsLoop: () => st.growing,
                               onShow: () => { if (st.growing && !st.armed) { st.t0 = 0; endGrowth(); } } });
  }

  /* ========================================================================
     The Connectome: every module a neuron
     ======================================================================== */
  function Connectome() {
    const f = sceneFrame('connectome', 'The Connectome',
      'Every part of Jarvis’s code as a neuron: the server’s modules on one side, the '
      + 'interface’s scripts on the other, sized by their lines. Each axon is a real call '
      + 'between two of them, and the light running along them is spikes.');
    const sc = { key: 'connectome', node: f.sec, visible: false };
    const st = { nodes: null, links: null, settle: 0, pulses: [], last: 0, hover: -1, adj: null,
                 sig: '', scale: null };

    function set(part) {
      const sig = part.nodes.length + ':' + part.links.length + ':' + part.nodes.reduce((s, n) => s + n[1], 0);
      const P = pal();
      setFacts(f.facts, [['Modules', fmt(part.nodes.length)], ['Connections', fmt(part.links.length)],
                         ['Routes', fmt(part.routes)],
                         ['Lines of code', fmt(part.languages.reduce((s, l) => s + l[1], 0))]]);
      setLegend(f.legend, [[P.c2, 'The server · Python'], [P.c1, 'The interface · JavaScript']]
        .concat(part.languages.slice(0, 6).map((l) => [P.line, l[0] + ' · ' + fmt(l[1]) + ' lines in ' + fmt(l[2]) + ' files'])));
      if (sig === st.sig) return;
      st.sig = sig;
      const old = new Map((st.nodes || []).map((n) => [n.path, n]));
      const rnd = seeded(7);
      // The layout's own frame has the picture's shape, so what settles in
      // it fills the picture rather than a square in the middle of it.
      const cw = f.cv.clientWidth || 1000, ch = f.cv.clientHeight || 520;
      st.W0 = 1000;
      st.H0 = 1000 * clamp(ch / cw, 0.35, 1.2);
      st.nodes = part.nodes.map((row, i) => {
        const o = old.get(row[0]);
        const server = row[0].startsWith('backend/');
        return { i, path: row[0], name: row[0].split('/').pop(), lines: row[1], purpose: row[2], server,
                 r: 2.2 + Math.sqrt(row[1]) / 11, deg: 0,
                 x: o ? o.x : (server ? -1 : 1) * st.W0 * (0.05 + rnd() * 0.38),
                 y: o ? o.y : (rnd() - 0.5) * st.H0 * 0.8,
                 dx: 0, dy: 0, flash: 0, fresh: !o && !!st.nodes };
      });
      st.links = part.links.map(([a, b, w]) => ({ a: st.nodes[a], b: st.nodes[b], w }));
      st.adj = st.nodes.map(() => []);
      st.links.forEach((l) => { l.a.deg += 1; l.b.deg += 1; st.adj[l.a.i].push(l); st.adj[l.b.i].push(l); });
      st.k = 0.8 * Math.sqrt((st.W0 * st.H0) / Math.max(1, st.nodes.length));
      st.settle = old.size ? 140 : 420;
      st.temp = old.size ? st.W0 / 40 : st.W0 / 9;
      st.pulses = [];
      if (reduced()) { while (st.settle > 0) step(); }
      else {
        // Settled by a timer if the frames never come (the harness runner).
        clearTimeout(st.endTimer);
        st.endTimer = setTimeout(() => {
          if (st.settle <= 0) return;
          while (st.settle > 0) step();
          draw();
        }, 9000);
      }
      if (!st.hover || st.hover < 0) setRead(f.read, null, ['Point at a neuron to see which part of the code it is.']);
      draw();
      if (sc.visible) wake(sc);
    }

    /* Fruchterman and Reingold: every pair pushes apart, every call pulls
       its two ends together, and a cooling step size lets it settle. Two
       hemispheres: the server is drawn to the left half, the interface to
       the right. Everything is kept inside the frame. */
    function step() {
      const ns = st.nodes, n = ns.length, k = st.k, k2 = k * k;
      const hw = st.W0 / 2, hh2 = st.H0 / 2;
      for (let i = 0; i < n; i++) { ns[i].dx = 0; ns[i].dy = 0; }
      for (let i = 0; i < n; i++) {
        const a = ns[i];
        for (let j = i + 1; j < n; j++) {
          const b = ns[j];
          let dx = a.x - b.x, dy = a.y - b.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 0.01) { dx = 0.1 * (i - j); dy = 0.1; d2 = dx * dx + dy * dy; }
          // Beyond three ideal lengths two neurons no longer push: without
          // this a module nothing calls is pushed out to the frame's edge.
          if (d2 > 9 * k2) continue;
          const room = a.r + b.r + 4;
          const f = k2 / d2 + (d2 < room * room ? 2 : 0);
          a.dx += dx * f; a.dy += dy * f;
          b.dx -= dx * f; b.dy -= dy * f;
        }
      }
      st.links.forEach((l) => {
        const dx = l.a.x - l.b.x, dy = l.a.y - l.b.y, d = Math.hypot(dx, dy) || 0.1;
        const f = (d / k) * (0.35 + 0.2 * Math.log(1 + l.w));
        l.a.dx -= dx * f; l.a.dy -= dy * f;
        l.b.dx += dx * f; l.b.dy += dy * f;
      });
      const t = st.temp;
      ns.forEach((p) => {
        p.dx += ((p.server ? -0.25 : 0.25) * st.W0 - p.x) * 0.9;
        p.dy += -p.y * 0.35;
        const len = Math.hypot(p.dx, p.dy);
        if (len > 0) {
          const m = Math.min(len, t) / len;
          p.x += p.dx * m; p.y += p.dy * m;
        }
        p.x = clamp(p.x, -hw + p.r + 6, hw - p.r - 6);
        p.y = clamp(p.y, -hh2 + p.r + 6, hh2 - p.r - 6);
      });
      st.temp = Math.max(0.6, st.temp * 0.986);
      st.settle -= 1;
      st.scale = null;
    }

    function frameOf(w, hh) {
      if (st.scale && st.scale.w === w && st.scale.h === hh) return st.scale;
      const s = Math.min((w - 24) / st.W0, (hh - 24) / st.H0);
      st.scale = { w, h: hh, s, ox: w / 2, oy: hh / 2 };
      return st.scale;
    }

    function draw(now) {
      const { g, w, h: hh } = fit(f.cv);
      g.clearRect(0, 0, w, hh);
      if (!st.nodes) return;
      const P = pal();
      const F = frameOf(w, hh);
      const X = (x) => F.ox + x * F.s, Y = (y) => F.oy + y * F.s;
      const hv = st.hover >= 0 ? st.nodes[st.hover] : null;
      const near = hv ? new Set(st.adj[hv.i].map((l) => (l.a === hv ? l.b : l.a))) : null;
      g.lineWidth = 1;
      st.links.forEach((l) => {
        const on = hv && (l.a === hv || l.b === hv);
        if (hv && !on) { g.strokeStyle = rgba(P.text3, 0.03); }
        else g.strokeStyle = on ? rgba(P.text, 0.55) : rgba(P.text3, clamp(0.06 + Math.log(1 + l.w) * 0.05, 0.06, 0.28));
        g.beginPath(); g.moveTo(X(l.a.x), Y(l.a.y)); g.lineTo(X(l.b.x), Y(l.b.y)); g.stroke();
      });
      // Spikes in flight.
      st.pulses.forEach((p) => {
        const u = p.u;
        const x = lerp(X(p.l.a.x), X(p.l.b.x), p.dir ? u : 1 - u), y = lerp(Y(p.l.a.y), Y(p.l.b.y), p.dir ? u : 1 - u);
        const col = (p.dir ? p.l.a : p.l.b).server ? P.c2 : P.c1;
        g.fillStyle = rgba(col, 0.25);
        g.beginPath(); g.arc(x, y, 4, 0, TAU); g.fill();
        g.fillStyle = col;
        g.beginPath(); g.arc(x, y, 1.6, 0, TAU); g.fill();
      });
      st.nodes.forEach((p) => {
        const dim = hv && p !== hv && !near.has(p);
        const col = p.server ? P.c2 : P.c1;
        const r = Math.max(1.6, p.r * Math.min(1.4, Math.max(0.55, F.s)));
        if (p.flash > 0) {
          g.fillStyle = rgba(col, 0.35 * p.flash);
          g.beginPath(); g.arc(X(p.x), Y(p.y), r + 6 * p.flash, 0, TAU); g.fill();
        }
        g.fillStyle = dim ? rgba(col, 0.2) : col;
        g.strokeStyle = P.bg2;
        g.lineWidth = 2;
        g.beginPath(); g.arc(X(p.x), Y(p.y), r, 0, TAU); g.fill(); g.stroke();
        if (p.fresh) {
          g.strokeStyle = P.gold; g.lineWidth = 1.5;
          g.beginPath(); g.arc(X(p.x), Y(p.y), r + 3, 0, TAU); g.stroke();
        }
      });
      // Names: the hovered one and its neighbours, else the busiest.
      const boxes = [];
      const named = hv ? [hv].concat(Array.from(near).sort((a, b) => b.deg - a.deg).slice(0, 10))
        : st.nodes.slice().sort((a, b) => b.deg - a.deg).slice(0, 16);
      named.forEach((p, i) => {
        const r = Math.max(1.6, p.r * Math.min(1.4, Math.max(0.55, F.s)));
        label(g, p.name, X(p.x), Y(p.y) - r - 9, { boxes, size: i === 0 && hv ? 12 : 10.5,
                                                   color: p === hv ? P.text : P.text2, weight: p === hv ? '700' : '500' });
      });
    }

    function tick(now) {
      if (!st.nodes) return false;
      const dt = st.last ? Math.min(64, now - st.last) : 16;
      st.last = now;
      if (st.settle > 0) { step(); step(); step(); }
      const still = reduced();
      if (!still) {
        if (st.pulses.length < 26 && st.links.length && Math.random() < 0.55) {
          const l = st.links[Math.floor(Math.random() * st.links.length)];
          st.pulses.push({ l, u: 0, dir: Math.random() < 0.5, v: 0.0011 + Math.random() * 0.0012 });
        }
        st.pulses.forEach((p) => { p.u += p.v * dt; if (p.u >= 1) { (p.dir ? p.l.b : p.l.a).flash = 1; } });
        st.pulses = st.pulses.filter((p) => p.u < 1);
        st.nodes.forEach((p) => { if (p.flash > 0) p.flash = Math.max(0, p.flash - dt / 500); });
      }
      draw(now);
      return !still || st.settle > 0;
    }

    f.cv.addEventListener('pointermove', (e) => {
      if (!st.nodes || !st.scale) return;
      const r = f.cv.getBoundingClientRect();
      const mx = e.clientX - r.left, my = e.clientY - r.top;
      const F = st.scale;
      let best = -1, bd = Infinity;
      st.nodes.forEach((p) => {
        const dx = F.ox + p.x * F.s - mx, dy = F.oy + p.y * F.s - my, d = dx * dx + dy * dy;
        const rr = Math.max(8, p.r * F.s + 5);
        if (d < rr * rr && d < bd) { bd = d; best = p.i; }
      });
      if (best === st.hover) return;
      st.hover = best;
      if (best < 0) setRead(f.read, null, ['Point at a neuron to see which part of the code it is.']);
      else {
        const p = st.nodes[best];
        const outs = st.adj[best].filter((l) => l.a === p).length, ins = st.adj[best].length - outs;
        setRead(f.read, p.name, [p.purpose || (p.server ? 'A server module.' : 'An interface script.'),
                                 fmt(p.lines) + ' lines · ' + (p.server ? 'the server' : 'the interface'),
                                 'Calls ' + outs + ', called by ' + ins]);
      }
      if (!LOOP.on.has(sc)) draw();
    });
    f.cv.addEventListener('pointerleave', () => {
      if (st.hover < 0) return;
      st.hover = -1;
      setRead(f.read, null, ['Point at a neuron to see which part of the code it is.']);
      if (!LOOP.on.has(sc)) draw();
    });
    return Object.assign(sc, { set, draw: () => draw(performance.now()), tick,
                               needsLoop: () => !!st.nodes && (!reduced() || st.settle > 0) });
  }

  /* ========================================================================
     The River: every candidate, to its call
     ======================================================================== */
  const KIND_WORDS = { ds: 'Dentate spike sets', ied: 'P-spike sets', pooled: 'Pooled sets', other: 'Other sets' };
  const WHO_WORDS = { person: 'A person', model: 'A model, for a person to check', nobody: 'Nobody yet' };
  const OUT_WORDS = { spike: 'A real event', garbage: 'Not an event', flagged: 'Flagged for a closer look', waiting: 'Waiting for a call' };

  function River() {
    const f = sceneFrame('river', 'The River',
      'Every candidate in every curation set, flowing from the kind of set it is in, through who '
      + 'made its last call, to what the call was. Each band is as wide as the candidates in it.');
    const sc = { key: 'river', node: f.sec, visible: false };
    const st = { flows: null, bands: null, cols: null, parts: [], last: 0, hover: null, sig: '' };

    function set(part) {
      const sig = JSON.stringify(part.flows);
      const total = part.flows.reduce((s, x) => s + x[3], 0);
      const people = part.flows.filter((x) => x[1] === 'person').reduce((s, x) => s + x[3], 0);
      const models = part.flows.filter((x) => x[1] === 'model').reduce((s, x) => s + x[3], 0);
      setFacts(f.facts, [['Candidates', fmt(total)], ['Sets', fmt(Object.values(part.sets || {}).reduce((s, n) => s + n, 0))],
                         ['Called by people', fmt(people)], ['Called by models', fmt(models)]]);
      const P = pal();
      setLegend(f.legend, [[P.ds, KIND_WORDS.ds], [P.p, KIND_WORDS.ied], [P.gold, KIND_WORDS.pooled]]);
      if (sig === st.sig) return;
      st.sig = sig;
      st.flows = part.flows.map((x) => ({ kind: x[0], who: x[1], out: x[2], n: x[3] })).filter((x) => x.n > 0);
      st.layoutKey = '';
      st.parts = [];
      if (!st.hover) setRead(f.read, null, ['Point at a band to read it.']);
      draw();
      if (sc.visible) wake(sc);
    }

    function layout(g, w, hh) {
      const order = { kind: ['ds', 'ied', 'pooled', 'other'], who: ['person', 'model', 'nobody'],
                      out: ['spike', 'garbage', 'flagged', 'waiting'] };
      const total = st.flows.reduce((s, x) => s + x.n, 0) || 1;
      // The outer columns stand in from the edges by their own labels'
      // widths, so a label is never cut off at the side.
      g.font = '600 11px system-ui, sans-serif';
      const widest = (key, words) => {
        const sums = new Map();
        st.flows.forEach((x) => sums.set(x[key], (sums.get(x[key]) || 0) + x.n));
        let m = 0;
        sums.forEach((n, id) => { m = Math.max(m, g.measureText(words[id] + ' · ' + fmt(n)).width); });
        return m + 22;
      };
      const nw = 12, gap = 22, top = 30;
      const x0 = Math.min(w * 0.4, widest('kind', KIND_WORDS)), x2 = Math.max(w * 0.6, w - widest('out', OUT_WORDS) - nw);
      const xs = [x0 + nw / 2, (x0 + x2) / 2 + nw / 2, x2 + nw / 2];
      const cols = ['kind', 'who', 'out'].map((key, ci) => {
        const sums = new Map();
        st.flows.forEach((x) => sums.set(x[key], (sums.get(x[key]) || 0) + x.n));
        const ids = order[key].filter((id) => sums.has(id));
        const room = hh - top * 2 - gap * (ids.length - 1);
        const minH = 4;
        let y = top;
        const nodes = ids.map((id) => {
          const hgt = Math.max(minH, (sums.get(id) / total) * room);
          const n = { key, id, n: sums.get(id), x: xs[ci] - nw / 2, y, h: hgt, used: 0, usedR: 0 };
          y += hgt + gap;
          return n;
        });
        // Squeeze back in if the minimum heights pushed past the bottom.
        const over = y - gap - (hh - top);
        if (over > 0) nodes.forEach((n) => { n.y -= over * ((n.y - top) / Math.max(1, y - top)); });
        return { key, nodes, by: new Map(nodes.map((n) => [n.id, n])) };
      });
      const ko = order.kind, wo = order.who, oo = order.out;
      const flows = st.flows.slice().sort((a, b) => ko.indexOf(a.kind) - ko.indexOf(b.kind)
        || wo.indexOf(a.who) - wo.indexOf(b.who) || oo.indexOf(a.out) - oo.indexOf(b.out));
      const bands = flows.map((x) => {
        const A = cols[0].by.get(x.kind), M = cols[1].by.get(x.who), Z = cols[2].by.get(x.out);
        const ta = (x.n / A.n) * A.h, tm = (x.n / M.n) * M.h, tz = (x.n / Z.n) * Z.h;
        const b = { x, A, M, Z, ya: A.y + A.used + ta / 2, ym: M.y + M.used + tm / 2, ta, tm, tz };
        A.used += ta; M.used += tm;
        return b;
      });
      // Into the third column in its own order, so the bands do not cross there.
      bands.slice().sort((a, b) => oo.indexOf(a.x.out) - oo.indexOf(b.x.out) || wo.indexOf(a.x.who) - wo.indexOf(b.x.who)
        || ko.indexOf(a.x.kind) - ko.indexOf(b.x.kind)).forEach((b) => {
        b.yz = b.Z.y + b.Z.usedR + b.tz / 2; b.Z.usedR += b.tz;
      });
      return { cols, bands, nw };
    }
    function ensure(g, w, hh) {
      const key = w + 'x' + hh + ':' + st.sig;
      if (st.layoutKey !== key) { st.L = layout(g, w, hh); st.layoutKey = key; st.parts = []; }
      return st.L;
    }
    const kindCol = (k) => { const P = pal(); return k === 'ds' ? P.ds : k === 'ied' ? P.p : k === 'pooled' ? P.gold : P.c5; };
    function bez(x0, y0, x1, y1, u) {
      const mx = (x0 + x1) / 2, v = 1 - u;
      return [v * v * v * x0 + 3 * v * v * u * mx + 3 * v * u * u * mx + u * u * u * x1,
              v * v * v * y0 + 3 * v * v * u * y0 + 3 * v * u * u * y1 + u * u * u * y1];
    }
    function pathOf(b, nw, t) {
      // t 0..1 along the whole band: the first half to the middle, the second on.
      if (t < 0.5) return bez(b.A.x + nw, b.ya, b.M.x, b.ym, t * 2);
      return bez(b.M.x + nw, b.ym, b.Z.x, b.yz, (t - 0.5) * 2);
    }
    function ribbon(g, x0, y0, t0, x1, y1, t1) {
      const mx = (x0 + x1) / 2;
      g.beginPath();
      g.moveTo(x0, y0 - t0 / 2);
      g.bezierCurveTo(mx, y0 - t0 / 2, mx, y1 - t1 / 2, x1, y1 - t1 / 2);
      g.lineTo(x1, y1 + t1 / 2);
      g.bezierCurveTo(mx, y1 + t1 / 2, mx, y0 + t0 / 2, x0, y0 + t0 / 2);
      g.closePath();
      g.fill();
    }
    function draw() {
      const { g, w, h: hh } = fit(f.cv);
      g.clearRect(0, 0, w, hh);
      if (!st.flows || !st.flows.length) return;
      const L = ensure(g, w, hh);
      const P = pal();
      const hv = st.hover;
      L.bands.forEach((b) => {
        const on = hv && hv.band === b;
        const nodeOn = hv && hv.node && (hv.node === b.A || hv.node === b.M || hv.node === b.Z);
        const a = hv ? (on || nodeOn ? 0.62 : 0.08) : 0.3;
        g.fillStyle = rgba(kindCol(b.x.kind), a);
        ribbon(g, b.A.x + L.nw, b.ya, b.ta, b.M.x, b.ym, b.tm);
        ribbon(g, b.M.x + L.nw, b.ym, b.tm, b.Z.x, b.yz, b.tz);
      });
      // The current: specks carried along each band, as many as it is wide.
      st.parts.forEach((p) => {
        const b = L.bands[p.b];
        if (!b) return;
        const [x, y] = pathOf(b, L.nw, p.t);
        const thick = p.t < 0.5 ? lerp(b.ta, b.tm, p.t * 2) : lerp(b.tm, b.tz, (p.t - 0.5) * 2);
        g.fillStyle = rgba(P.text, 0.55);
        g.fillRect(x - 0.9, y + p.off * Math.max(0, thick - 2) - 0.9, 1.8, 1.8);
      });
      const words = { kind: KIND_WORDS, who: WHO_WORDS, out: OUT_WORDS };
      L.cols.forEach((c, ci) => {
        c.nodes.forEach((n) => {
          g.fillStyle = c.key === 'kind' ? kindCol(n.id) : P.text2;
          g.fillRect(n.x, n.y, L.nw, n.h);
          const txt = words[c.key][n.id] + ' · ' + fmt(n.n);
          const y = n.y + n.h / 2;
          if (ci === 0) label(g, txt, n.x - 6, y, { align: 'right', color: P.text });
          else if (ci === 2) label(g, txt, n.x + L.nw + 6, y, { align: 'left', color: P.text });
          else label(g, txt, n.x + L.nw / 2, n.y - 10, { color: P.text });
        });
      });
    }
    function tick(now) {
      if (!st.L) return false;
      const dt = st.last ? Math.min(64, now - st.last) : 16;
      st.last = now;
      if (reduced()) return false;
      const total = st.L.bands.reduce((s, b) => s + b.x.n, 0) || 1;
      if (st.parts.length < 420) {
        for (let k = 0; k < 6; k++) {
          let r = Math.random() * total, i = 0;
          while (i < st.L.bands.length - 1 && r > st.L.bands[i].x.n) { r -= st.L.bands[i].x.n; i += 1; }
          st.parts.push({ b: i, t: 0, off: Math.random() - 0.5, v: 0.00008 + Math.random() * 0.00005 });
        }
      }
      st.parts.forEach((p) => { p.t += p.v * dt; });
      st.parts = st.parts.filter((p) => p.t < 1);
      draw();
      return true;
    }
    f.cv.addEventListener('pointermove', (e) => {
      if (!st.L) return;
      const r = f.cv.getBoundingClientRect();
      const mx = e.clientX - r.left, my = e.clientY - r.top;
      let hit = null;
      for (const c of st.L.cols) for (const n of c.nodes) {
        if (mx >= n.x - 4 && mx <= n.x + st.L.nw + 4 && my >= n.y - 2 && my <= n.y + n.h + 2) hit = { node: n };
      }
      if (!hit) {
        for (const b of st.L.bands) {
          for (let s = 0; s <= 40; s++) {
            const t = s / 40;
            const [x, y] = pathOf(b, st.L.nw, t);
            const thick = t < 0.5 ? lerp(b.ta, b.tm, t * 2) : lerp(b.tm, b.tz, (t - 0.5) * 2);
            if (Math.abs(x - mx) < 8 && Math.abs(y - my) <= thick / 2 + 2) { hit = { band: b }; break; }
          }
          if (hit) break;
        }
      }
      const key = hit ? (hit.band ? 'b' + st.L.bands.indexOf(hit.band) : 'n' + hit.node.key + hit.node.id) : '';
      if (key === (st.hoverKey || '')) return;
      st.hoverKey = key;
      st.hover = hit;
      if (!hit) setRead(f.read, null, ['Point at a band to read it.']);
      else if (hit.band) {
        const x = hit.band.x;
        const what = x.who === 'nobody' ? 'are waiting for a call'
          : (x.who === 'person' ? 'a person called ' : 'a model called, for a person to check: ') + OUT_WORDS[x.out].toLowerCase();
        setRead(f.read, fmt(x.n) + ' candidates', ['In ' + KIND_WORDS[x.kind].toLowerCase() + ': ' + what + '.']);
      } else {
        const n = hit.node;
        const words = { kind: KIND_WORDS, who: WHO_WORDS, out: OUT_WORDS }[n.key][n.id];
        setRead(f.read, words, [fmt(n.n) + ' candidates']);
      }
      if (!LOOP.on.has(sc)) draw();
    });
    f.cv.addEventListener('pointerleave', () => {
      if (!st.hover) return;
      st.hover = null; st.hoverKey = '';
      setRead(f.read, null, ['Point at a band to read it.']);
      if (!LOOP.on.has(sc)) draw();
    });
    return Object.assign(sc, { set, draw, tick, needsLoop: () => !!st.flows && !reduced() });
  }

  /* ========================================================================
     The printer: Last 7 days' work
     ======================================================================== */
  function Printer() {
    const box = h('div', 'in-printer-wrap');
    const printer = h('div', 'in-printer');
    const slot = h('div', 'in-slot');
    const btn = h('button', 'jx-btn in-print', 'Last 7 days’ work', { type: 'button' });
    btn.id = 'insidePrint';
    const sub = h('div', 'in-print-sub', 'A printout of the week for the PI, written by Hater of AI.');
    printer.append(btn, sub, slot);
    const paper = h('div', 'in-paper');
    paper.hidden = true;
    const earlier = h('details', 'in-earlier', null, { 'data-keep': 'inside-earlier' });
    earlier.append(h('summary', null, 'Earlier printouts'));
    const list = h('div', 'in-earlier-list');
    earlier.append(list);
    earlier.hidden = true;
    printer.insertBefore(earlier, slot);
    box.append(printer, paper);
    const st = { timer: 0, running: false, open: null, alive: true, lastSteps: '', mail: {} };

    function steps(run) {
      paper.hidden = false;
      paper.classList.remove('printed');
      const lines = (run.steps || []).map((s) => s.text);
      const sig = lines.join('\n');
      if (sig === st.lastSteps && paper.querySelector('.in-feed')) return;
      st.lastSteps = sig;
      paper.textContent = '';
      const feed = h('div', 'in-feed');
      feed.append(h('div', 'in-feed-head', 'Printing the last 7 days…'));
      const ul = h('ol', 'in-feed-steps');
      lines.slice(-6).forEach((t, i, a) => ul.append(h('li', i === a.length - 1 ? 'now' : null, t)));
      if (!lines.length) ul.append(h('li', 'now', 'starting'));
      feed.append(ul);
      const stop = h('button', 'jx-btn ghost', 'Stop', { type: 'button' });
      stop.addEventListener('click', async () => {
        try { await postJSON('/api/inside/week/stop', {}); } catch (e) { oops('week.stop', e); }
        poll();
      });
      feed.append(stop);
      paper.append(feed);
    }

    function showReport(rep, text, fresh, why) {
      const n = rep.numbers || {}, note = rep.note || {};
      paper.hidden = false;
      paper.textContent = '';
      const slip = h('article', 'in-slip');
      const d = (s) => (s || '').slice(0, 10);
      slip.append(h('div', 'in-slip-kicker', 'Last 7 days’ work'),
                  h('div', 'in-slip-dates', day(d(rep.since)) + ' to ' + day(d(rep.until))));
      if (note.headline) slip.append(h('h4', null, note.headline));
      if (note.summary) slip.append(h('p', 'in-slip-summary', note.summary));
      [['Progress', 'progress'], ['At the bench', 'bench'], ['The data', 'data'], ['Next', 'next'],
       ['Keeping an eye on', 'watch']].forEach(([title, k]) => {
        const items = note[k] || [];
        if (!items.length) return;
        slip.append(h('div', 'in-slip-rule'));
        slip.append(h('h5', null, title));
        const ul = h('ul');
        items.forEach((x) => ul.append(h('li', null, x)));
        slip.append(ul);
      });
      slip.append(h('div', 'in-slip-rule'));
      slip.append(h('h5', null, 'By the numbers'));
      const tbl = h('dl', 'in-slip-nums');
      [['Versions shipped', n.versions], ['Commits', n.commits],
       ['Lines changed', n.lines_added != null ? '+' + fmt(n.lines_added) + ' / −' + fmt(n.lines_removed) : null],
       ['Events banked', n.events_banked], ['Calls by people', n.calls_people], ['Calls by models', n.calls_models],
       ['Procedures on the lab sheet', n.procedures], ['People at work', n.people]]
        .forEach(([k, v]) => { if (v == null) return; tbl.append(h('dt', null, k), h('dd', null, typeof v === 'number' ? fmt(v) : v)); });
      slip.append(tbl);
      const bench = rep.bench || {};
      if (bench.error) slip.append(h('p', 'in-slip-note', 'The Lab Operations sheet could not be read this time.'));
      slip.append(h('div', 'in-slip-rule'));
      // Why Hater of AI did not write it, in the server's plain words for
      // the reader, not the engine's own message.
      const who = rep.writer === 'Hater of AI' ? 'Written by Hater of AI'
        : 'Written by Jarvis from the numbers, because ' + (why || 'Hater of AI could not be asked this time');
      const sent = (rep.emailed || []).filter((x) => x.ok)
        .map((x) => 'Emailed to ' + x.n + (x.n === 1 ? ' person, ' : ' people, ') + new Date(x.at).toLocaleString() + '.');
      slip.append(h('p', 'in-slip-foot', who + '. Printed ' + new Date(rep.at).toLocaleString() + ' by '
                    + (rep.who || 'someone') + (rep.machine ? ' on ' + rep.machine : '') + '.'
                    + (sent.length ? ' ' + sent.join(' ') : '')));
      const acts = h('div', 'in-slip-acts');
      const copy = h('button', 'jx-btn ghost', 'Copy', { type: 'button' });
      copy.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(text); toastSay('Copied the printout', 'ok'); }
        catch (e) {
          const ta = h('textarea'); ta.value = text; document.body.append(ta); ta.select();
          try { document.execCommand('copy'); toastSay('Copied the printout', 'ok'); } catch (x) { toastSay('Copy was refused here', 'warn'); }
          ta.remove();
        }
      });
      const save = h('button', 'jx-btn ghost', 'Save to Results', { type: 'button' });
      save.addEventListener('click', async () => {
        try {
          const r = await postJSON('/api/inside/week/save', { id: rep.id, shard: rep.shard });
          if (r && r.ok) toastSay('Saved to Results' + (r.saved && r.saved.rel ? ': ' + r.saved.rel : ''), 'ok');
          else toastSay((r && r.error) || 'Could not save it', 'err');
        } catch (e) { oops('week.save', e); toastSay('Could not save it', 'err'); }
      });
      const mailBtn = h('button', 'jx-btn ghost', 'Email…', { type: 'button' });
      const m = st.mail || {};
      if (!m.here) {
        mailBtn.disabled = true;
        mailBtn.title = 'Emailing is set up on the computer that sends the weekly email, not this one';
      }
      const panel = mailPanel(rep);
      panel.hidden = true;
      mailBtn.addEventListener('click', () => { panel.hidden = !panel.hidden; });
      const fold = h('button', 'jx-btn ghost', 'Close', { type: 'button' });
      fold.addEventListener('click', () => { paper.hidden = true; paper.textContent = ''; st.open = null; });
      acts.append(copy, save, mailBtn, fold);
      paper.append(slip, acts, panel);
      st.open = rep.id;
      if (fresh && !reduced()) {
        paper.classList.add('printed');
        setTimeout(() => paper.classList.remove('printed'), 1600);
      }
    }
    /* Email this printout: a test to the test list at once, or the lab,
       only after it has been confirmed. Who is on each list is shown, read
       from this computer's own settings. */
    function mailPanel(rep) {
      const m = st.mail || {};
      const box = h('div', 'in-mail');
      box.append(h('strong', null, 'Email this printout'),
                 h('span', 'in-mail-sub', 'Sent from barrylabuvm@gmail.com, as a formatted email with a plain-text copy.'));
      const say = h('p', 'in-mail-say', null, { 'aria-live': 'polite' });
      const testTo = (m.testTo || []).join(', ') || 'the test list';
      const labTo = (m.labTo || []);
      const testBtn = h('button', 'jx-btn ghost', 'Send a test to ' + testTo, { type: 'button' });
      const labBtn = h('button', 'jx-btn', 'Send to the lab (' + (labTo.length || m.lab || 0) + ' people)…', { type: 'button' });
      const confirmRow = h('div', 'in-mail-confirm');
      confirmRow.hidden = true;
      const sure = h('button', 'jx-btn', 'Send it', { type: 'button' });
      const cancel = h('button', 'jx-btn ghost', 'Cancel', { type: 'button' });
      confirmRow.append(h('span', null, 'This goes to ' + (labTo.join(', ') || 'the lab list') + '.'), sure, cancel);
      const btns = h('div', 'in-mail-btns');
      btns.append(testBtn, labBtn);
      box.append(btns, confirmRow, say);
      const busy = (on) => { [testBtn, labBtn, sure, cancel].forEach((b) => { b.disabled = on; }); };
      async function send(to) {
        busy(true);
        say.textContent = 'Sending…';
        try {
          const r = await postJSON('/api/inside/week/email', { id: rep.id, shard: rep.shard, to });
          if (r && r.ok) {
            say.textContent = 'Sent to ' + r.sent + (r.sent === 1 ? ' person.' : ' people.');
            toastSay('Emailed the printout to ' + r.sent + (r.sent === 1 ? ' person' : ' people'), 'ok');
            confirmRow.hidden = true;
            // Said on the slip in place: reopening it would rebuild the
            // panel under the person's pointer.
            const foot = paper.querySelector('.in-slip-foot');
            if (foot) foot.textContent += ' Emailed to ' + r.sent + (r.sent === 1 ? ' person, ' : ' people, ')
              + new Date().toLocaleString() + '.';
          } else {
            say.textContent = 'Not sent: ' + ((r && r.error) || 'the mailer did not answer') + '.';
          }
        } catch (e) {
          say.textContent = 'Not sent: ' + ((e && e.message) || 'the mailer did not answer') + '.';
        } finally { busy(false); }
      }
      testBtn.addEventListener('click', () => send('test'));
      labBtn.addEventListener('click', () => { confirmRow.hidden = false; say.textContent = ''; });
      cancel.addEventListener('click', () => { confirmRow.hidden = true; });
      sure.addEventListener('click', () => send('lab'));
      return box;
    }

    function toastSay(msg, kind) {
      try { if (typeof toast === 'function') toast(msg, kind); } catch (e) { /* none */ }
    }

    async function openReport(id, shard, fresh) {
      try {
        const r = await getJSON('/api/inside/week/report?id=' + encodeURIComponent(id)
                                + (shard ? '&shard=' + encodeURIComponent(shard) : ''));
        if (!st.alive) return;
        if (r && r.ok) {
          showReport(r.report, r.text, fresh, r.why);
          if (fresh) sfx('bell');
        } else toastSay((r && r.error) || 'That printout is not on this computer', 'warn');
      } catch (e) { oops('week.open', e); }
    }

    function paintList(reports) {
      const sig = JSON.stringify(reports.map((r) => r.id));
      earlier.hidden = !reports.length;
      if (list.__sig === sig) return;
      list.__sig = sig;
      list.textContent = '';
      reports.forEach((r) => {
        const b = h('button', 'in-earlier-row', null, { type: 'button' });
        b.append(h('strong', null, new Date(r.at).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })),
                 h('span', null, r.headline || ''), h('em', null, (r.who || 'someone') + (r.writer === 'Hater of AI' ? ' · Hater of AI' : ' · from the numbers')));
        b.addEventListener('click', () => openReport(r.id, r.shard, false));
        list.append(b);
      });
    }

    async function poll() {
      clearTimeout(st.timer);
      let r = null;
      try { r = await getJSON('/api/inside/week'); } catch (e) { oops('week.poll', e); }
      if (!st.alive) return;
      if (!r || !r.ok) { st.timer = setTimeout(poll, 4000); return; }
      paintList(r.reports || []);
      // Where this computer emails the printout, it says so, and when.
      const m = r.mail || {};
      st.mail = m;
      sub.textContent = 'A printout of the week for the PI, written by Hater of AI.'
        + (m.here && m.schedule ? ' Emailed to the lab (' + m.lab + ' people) ' + m.schedule + ', from this computer.' : '');
      const run = r.run || {};
      const wasRunning = st.running;
      st.running = !!run.running;
      btn.disabled = st.running;
      btn.textContent = st.running ? 'Printing…' : 'Last 7 days’ work';
      printer.classList.toggle('busy', st.running);
      if (st.running) {
        steps(run);
        st.timer = setTimeout(poll, 1500);
      } else if (wasRunning && run.id) {
        const mine = (r.reports || []).find((x) => x.id === run.id);
        if (mine) openReport(mine.id, mine.shard, true);
        else {
          paper.textContent = '';
          paper.append(h('p', 'in-slip-note', 'The printing stopped before it finished. Press the printer to try again.'));
        }
      }
    }

    btn.addEventListener('click', async () => {
      if (st.running) return;
      btn.disabled = true;
      try {
        const r = await postJSON('/api/inside/week/print', {});
        if (!r || !r.ok) { toastSay((r && r.error) || 'The printer would not start', 'err'); btn.disabled = false; return; }
        st.running = true;
        btn.textContent = 'Printing…';
        printer.classList.add('busy');
        steps(r.run || {});
        st.timer = setTimeout(poll, 800);
      } catch (e) { oops('week.print', e); btn.disabled = false; }
    });

    return { node: box, attach: () => { st.alive = true; poll(); },
             detach: () => { st.alive = false; clearTimeout(st.timer); },
             press: () => btn.click() };
  }

  /* ========================================================================
     The page
     ======================================================================== */
  const MEM = { parts: {}, sigs: {}, totals: null };
  let live = null;

  function readSeen() {
    try { return JSON.parse(localStorage.getItem(SEEN_KEY) || 'null'); } catch (e) { return null; }
  }
  function writeSeen(t) {
    try { localStorage.setItem(SEEN_KEY, JSON.stringify({ at: Date.now(), totals: t })); } catch (e) { /* fine */ }
  }

  const COUNTERS = [
    ['recordings', 'recordings'], ['events', 'events banked'], ['calls', 'calls made'],
    ['versions', 'versions shipped'], ['lines', 'lines of code'], ['days', 'days of building'],
  ];

  function render(body) {
    stopAll();
    PAL = palette();
    const L = { body, scenes: [], timer: 0, alive: true, seen: readSeen(), seenSaved: false, io: null, counters: {} };
    live = L;

    const hero = h('section', 'in-hero');
    const intro = h('div', 'in-intro');
    intro.append(h('h2', null, 'Inside Jarvis'),
                 h('p', 'jx-lede', 'Everything the lab has put into Jarvis, counted live from its own '
                   + 'records. Every picture below is drawn from the real data and grows as the work does.'));
    const counters = h('div', 'in-counters');
    COUNTERS.forEach(([k, words]) => {
      const c = h('div', 'in-count');
      const v = h('strong', null, '—');
      const d = h('em', 'in-delta');
      d.hidden = true;
      c.append(v, h('span', null, words), d);
      counters.append(c);
      L.counters[k] = { v, d, shown: null };
    });
    const status = h('p', 'in-status', 'Counting…');
    intro.append(counters, status);
    const printer = Printer();
    hero.append(intro, printer.node);

    const nav = h('nav', 'in-nav', null, { 'aria-label': 'The pictures' });
    const scenes = [Sunflower(), Powers(), Gyrus(), Connectome(), River()];
    scenes.forEach((s) => {
      const b = h('button', 'in-nav-btn', s.node.querySelector('h3').textContent, { type: 'button' });
      b.addEventListener('click', () => { try { s.node.scrollIntoView({ behavior: reduced() ? 'auto' : 'smooth', block: 'start' }); } catch (e) { /* fine */ } });
      nav.append(b);
    });
    body.append(hero, nav);
    scenes.forEach((s) => body.append(s.node));
    L.scenes = scenes;
    L.byKey = { events: scenes[0], zoom: scenes[1], versions: scenes[2], modules: scenes[3], calls: scenes[4] };
    L.printer = printer;

    // Only what is on screen moves.
    if ('IntersectionObserver' in window) {
      L.io = new IntersectionObserver((es) => {
        es.forEach((e) => {
          const s = scenes.find((x) => x.node === e.target);
          if (!s) return;
          s.visible = e.isIntersecting;
          if (s.visible) {
            try { s.draw(); } catch (x) { oops(s.key + '.draw', x); }
            if (s.onShow) s.onShow();
            if (s.needsLoop()) wake(s);
          }
        });
      }, { root: body, threshold: 0.05 });
      scenes.forEach((s) => L.io.observe(s.node));
    } else scenes.forEach((s) => { s.visible = true; });
    L.ro = ('ResizeObserver' in window) ? new ResizeObserver(() => {
      scenes.forEach((s) => { if (s.visible && !LOOP.on.has(s)) { try { s.draw(); } catch (e) { oops(s.key + '.resize', e); } } });
    }) : null;
    if (L.ro) scenes.forEach((s) => L.ro.observe(s.node.querySelector('.in-canvas')));

    // What is already here, at once; then whatever moved.
    if (Object.keys(MEM.parts).length) apply({ parts: MEM.parts, totals: MEM.totals, busy: false }, true);
    census();
    printer.attach();
    return () => {
      L.alive = false;
      clearTimeout(L.timer);
      if (L.io) L.io.disconnect();
      if (L.ro) L.ro.disconnect();
      scenes.forEach((s) => { s.visible = false; LOOP.on.delete(s); });
      printer.detach();
      if (live === L) live = null;
    };
  }

  function stopAll() {
    if (live) {
      live.alive = false;
      clearTimeout(live.timer);
      if (live.io) live.io.disconnect();
      if (live.ro) live.ro.disconnect();
      live.scenes.forEach((s) => { s.visible = false; LOOP.on.delete(s); });
      if (live.printer) live.printer.detach();
      live = null;
    }
  }

  async function census() {
    const L = live;
    if (!L || !L.alive) return;
    clearTimeout(L.timer);
    const have = Object.keys(MEM.sigs).map((k) => k + '=' + MEM.sigs[k]).join(',');
    let r = null;
    try { r = await getJSON('/api/inside/census' + (have ? '?have=' + encodeURIComponent(have) : '')); }
    catch (e) { oops('census', e); }
    if (!L.alive || live !== L) return;
    if (r && r.ok) {
      Object.keys(r.parts || {}).forEach((k) => { MEM.parts[k] = r.parts[k]; });
      MEM.sigs = Object.assign({}, r.sigs || {});
      MEM.totals = r.totals;
      apply(r, false);
    } else {
      const status = L.body.querySelector('.in-status');
      if (status) status.textContent = 'Could not count just now; trying again in a minute.';
    }
    // A recount on the server: ask again soon. Otherwise look again in a
    // minute, which is how the page keeps up while it is open.
    L.timer = setTimeout(census, r && r.busy ? 2500 : 60000);
  }

  function apply(r, fromMemory) {
    const L = live;
    if (!L) return;
    const seen = (L.seen && L.seen.totals) || null;
    const t = r.totals || {};
    COUNTERS.forEach(([k]) => {
      const c = L.counters[k];
      const val = t[k];
      if (val == null) return;
      if (c.shown !== val) {
        if (B && B.ui && B.ui.countUp && c.shown == null && !fromMemory) B.ui.countUp(c.v, val, { ms: 1400 });
        else if (B && B.ui && B.ui.countUp && c.shown != null) B.ui.countUp(c.v, val, { from: c.shown, ms: 900 });
        else c.v.textContent = fmt(val);
        c.shown = val;
      }
      const was = seen && seen[k];
      const delta = was != null ? val - was : 0;
      c.d.hidden = !(delta > 0);
      if (delta > 0) c.d.textContent = '+' + fmt(delta) + ' since you last looked';
    });
    const status = L.body.querySelector('.in-status');
    if (status) {
      const words = [];
      if (t.since) words.push('Building since ' + day(t.since) + '.');
      if (t.samples) words.push(bigWords(t.samples) + ' voltage samples in the recordings whose length is on record.');
      if (r.busy) words.push('Recounting what changed…');
      status.textContent = words.join(' ');
    }
    const parts = r.parts || {};
    const P = parts;
    try { if (P.events) L.byKey.events.set(P.events, seen ? seen.events : null); } catch (e) { oops('sunflower.set', e); }
    try { if (P.zoom) L.byKey.zoom.set(P.zoom); } catch (e) { oops('powers.set', e); }
    try { if (P.versions) L.byKey.versions.set(P.versions, seen ? seen.versions : null); } catch (e) { oops('gyrus.set', e); }
    try { if (P.modules) L.byKey.modules.set(P.modules); } catch (e) { oops('connectome.set', e); }
    try { if (P.calls) L.byKey.calls.set(P.calls); } catch (e) { oops('river.set', e); }
    // What you have seen now is this, a few seconds after it arrives.
    if (!fromMemory && !L.seenSaved && t.events != null && t.versions != null) {
      L.seenSaved = true;
      setTimeout(() => writeSeen(t), 5000);
    }
  }

  /* A theme change: every colour is read again and every picture redrawn. */
  function repaint() {
    PAL = palette();
    if (!live) return;
    live.scenes.forEach((s) => { try { s.draw(); } catch (e) { oops(s.key + '.repaint', e); } });
  }

  /* Open the showcase on this tab, from anywhere (the palette, the start
     menu, ?inside=1). */
  function open(o) {
    const S = B && B.jarvisshow;
    if (!S) return;
    S.open('inside', {});
    if (o && o.print) setTimeout(() => { if (live && live.printer) live.printer.press(); }, 400);
  }

  // `_census` asks again now: for _dev/inside.html, which checks that an
  // answer with nothing new in it rebuilds nothing.
  const api = { render, repaint, open, _census: () => census() };
  if (B) B.inside = api; else window.JarvisInside = api;

  try {
    const q = new URLSearchParams(location.search);
    if (q.get('inside') && window.top === window) {
      window.addEventListener('load', () => setTimeout(() => open(), 900));
    }
  } catch (e) { /* no deep link */ }
})();
