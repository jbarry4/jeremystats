/* ==========================================================================
   seahorse.js -- Seahorse: the mouse brain, down to the cells we record.

   Three ways to look at one circuit, kept in step:
     Schematic  the regional circuit, and the dentate laid out by layer
     3D         whole brain -> hippocampus -> a thin slab with real cells
     Slice      any coronal / sagittal / horizontal section, laminae over
                Nissl, with a probe you can place
   and a tracer that walks a pathway hop by hop through all three, plus
   "play DS1 / DS2". Everything is cited, and every claim that public data
   can test has been tested (tools/seahorse/crosscheck.py; the Checks panel).

   Data: web/seahorse/*.shb.gz, built offline by tools/seahorse/ from the
   Allen CCFv3, the Allen connectivity atlas and NeuroMorpho.Org. Nothing is
   fetched from the internet while the tab is open. Files load only when a
   view needs them, behind a loading window that says what is coming.
   ========================================================================== */
'use strict';

BARRY.views.seahorse = (function () {
  const BASE = 'seahorse/';
  const S = {
    built: false, kb: null, checks: null, manifest: null, blobs: {},
    mode: 'threed', schem: 'circuit', level: 'brain', sel: null, side: 'inspect',
    slice: { plane: 'coronal', pos: 7300, view: null, layer: 'lamina', cells: true },
    probe: { on: false, ap: 7300, ml: 7550, dv: 2450, contacts: 64, pitch: 20 },
    slab: { ap: 7300, thick: 300 },
    trace: { key: null, i: -1, timer: 0, ds: null },
    focus: null, stage3: null, three: null, loading: null,
  };
  let root = null;
  const $ = (sel, r) => (r || root).querySelector(sel);

  /* ==================================================================
     Small helpers
     ================================================================== */
  const store = {
    get() { try { return JSON.parse(localStorage.getItem('seahorse.ui') || '{}'); } catch (e) { return {}; } },
    set(o) { try { localStorage.setItem('seahorse.ui', JSON.stringify(Object.assign(store.get(), o))); } catch (e) { /* private window */ } },
  };
  const tok = (n, f) => (BARRY.token ? BARRY.token(n, f) : f) || f;
  function hexRgb(c) {
    c = (c || '#888').trim();
    if (c.startsWith('rgb')) { const m = c.match(/[\d.]+/g).map(Number); return [m[0], m[1], m[2]]; }
    if (c.length === 4) c = '#' + c[1] + c[1] + c[2] + c[2] + c[3] + c[3];
    const n = parseInt(c.slice(1, 7), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const fmtMB = (b) => (b / 1048576).toFixed(b > 1048576 * 10 ? 0 : 1) + ' MB';
  function cellOf(k) { return S.kb && S.kb.cells.find((c) => c.key === k); }
  function regionOf(k) { return S.kb && S.kb.regions.find((r) => r.key === k); }
  function connOf(k) { return S.kb && S.kb.connections.find((c) => c.key === k); }
  function lamOf(k) { const L = laminaList(); return L && L.find((l) => l.key === k); }
  function laminaList() { return (S.kb && S.kb.lamina) || []; }
  function verdictOf(key) { return (S.checks && S.checks.connections[key]) || { status: 'cited', detail: '' }; }
  function verdictChip(v) {
    const cls = (v.status || 'cited').replace(/\s+/g, '');
    const word = { supported: 'Supported by data', consistent: 'Placement consistent', weak: 'Weak in data',
                   'not seen': 'Not seen in data', cited: 'Cited, not tested', untested: 'Not testable here', error: 'Check failed' }[v.status] || v.status;
    return el('span', { class: 'sh-verdict ' + cls, text: word });
  }
  const SEAHORSE_SVG = '<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'
    + '<path d="M27 8c-4.5 0-7.5 3.2-7.5 7 0 2.2 1 3.7 2.2 4.8-3.7 2.3-6.2 6.3-6.2 10.9 0 5.4 3.9 8.8 8.4 8.8 3.6 0 5.9-2.3 5.9-5.2 0-2.6-1.9-4.2-4-4.2-1.8 0-3 1.2-3 2.6"/>'
    + '<path d="M27 8l8.5 1.6-4.7 3.6"/><circle cx="25.3" cy="12.6" r="1.1" fill="currentColor"/>'
    + '<path d="M21.7 19.8c3.8 1.4 6 4.6 6 8.4"/><path d="M15.8 27.4c-2.6-.4-4.4-2.1-4.6-4.4"/>'
    + '<path d="M29.4 18.2c2.2.2 3.8 1.4 4.6 3.2"/></svg>';

  /* ==================================================================
     Data: fetch with progress, gunzip, unpack
     ================================================================== */
  const DTYPE = { uint8: Uint8Array, int8: Int8Array, uint16: Uint16Array, int16: Int16Array,
                  uint32: Uint32Array, int32: Int32Array, float32: Float32Array, float64: Float64Array };
  async function fetchBytes(name, onBytes) {
    const res = await fetch(BASE + name, { cache: 'no-cache' });
    if (!res.ok) throw new Error(name + ': HTTP ' + res.status);
    const total = +res.headers.get('content-length') || 0;
    if (!res.body || !res.body.getReader) {
      const b = new Uint8Array(await res.arrayBuffer());
      onBytes && onBytes(b.length, b.length);
      return b;
    }
    const reader = res.body.getReader();
    const chunks = [];
    let got = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      got += value.length;
      onBytes && onBytes(got, total);
    }
    const out = new Uint8Array(got);
    let o = 0;
    for (const c of chunks) { out.set(c, o); o += c.length; }
    return out;
  }
  async function gunzip(u8) {
    if (!(u8[0] === 0x1f && u8[1] === 0x8b)) return u8;   // server already decoded it
    const ds = new Blob([u8]).stream().pipeThrough(new DecompressionStream('gzip'));
    return new Uint8Array(await new Response(ds).arrayBuffer());
  }
  function unpack(u8) {
    const magic = String.fromCharCode(u8[0], u8[1], u8[2], u8[3]);
    if (magic !== 'SHB1') throw new Error('not a Seahorse blob');
    const hlen = new DataView(u8.buffer, u8.byteOffset + 4, 4).getUint32(0, true);
    const header = JSON.parse(new TextDecoder().decode(u8.subarray(8, 8 + hlen)));
    const base = u8.byteOffset + 8 + hlen;
    const buf = (base % 8 === 0) ? u8.buffer : u8.slice().buffer;
    const b0 = (base % 8 === 0) ? base : 8 + hlen;
    const arrays = {};
    for (const a of header.arrays) {
      const T = DTYPE[a.dtype];
      arrays[a.name] = new T(buf, b0 + a.offset, a.nbytes / T.BYTES_PER_ELEMENT);
    }
    return { header, arrays };
  }
  async function getJSON(name) {
    const res = await fetch(BASE + name, { cache: 'no-cache' });
    if (!res.ok) throw new Error(name + ': HTTP ' + res.status);
    return res.json();
  }

  /* ---------- the loading window ---------- */
  const WHAT = {
    'three': ['Waking the 3D renderer', 'three.js, kept on this computer; loaded the first time 3D opens.'],
    'mesh_brain.shb.gz': ['The whole brain', 'Allen CCFv3 brain surface and its 12 major divisions, simplified from the Allen meshes.'],
    'mesh_hpf.shb.gz': ['The hippocampal formation', 'DG, CA1-3, subiculum, entorhinal, perirhinal and postrhinal cortex, both sides.'],
    'mesh_lamina.shb.gz': ['Its layers, at 10 µm', '28 laminar surfaces of the right hippocampus: OML1 to OML2, the CA strata. Derived where the Allen atlas has none.'],
    'cells.shb.gz': ['The cells', '11 neurons: 4 traced in atlas space by their authors, 6 slice tracings placed by fit, 1 drawn (no public tracing exists).'],
    'brain50.shb.gz': ['Whole-brain sections', '671 Allen structures and Nissl, every 50 µm.'],
    'hip20.shb.gz': ['Hippocampal sections', 'Laminae and Nissl through the whole hippocampus, every 20 µm.'],
    'hip10d.shb.gz': ['Dorsal hippocampus, fine', 'Laminae every 10 µm where the probes go.'],
    'build': ['Building', 'Turning the numbers into surfaces and sections.'],
  };
  function loadingWindow(title, sub, names) {
    const sizes = (S.manifest && S.manifest.files) || {};
    const items = names.map((n) => ({ n, bytes: (sizes[n] || {}).bytes || (n === 'three' ? 700000 : 400000), got: 0 }));
    const total = items.reduce((s, x) => s + x.bytes, 0);
    const steps = el('ul', { class: 'sh-load-steps' }, items.concat([{ n: 'build', bytes: 0 }]).map((it) => {
      const [label, what] = WHAT[it.n] || [it.n, ''];
      return el('li', { 'data-n': it.n }, [el('span', { class: 'mark' }),
        el('span', { class: 'what' }, [el('span', { text: label }), el('small', { text: what })]),
        el('span', { class: 'size', text: it.bytes && it.n !== 'three' ? fmtMB(it.bytes) : '' })]);
    }));
    const bar = el('i');
    const pct = el('span', { class: 'pct', text: '0%' });
    const said = el('span', { text: 'Starting' });
    const fact = el('div', { class: 'sh-load-fact' });
    const facts = (S.kb ? S.kb.cells : []).map((c) => c.label + ': ' + c.about);
    let fi = Math.floor(Math.random() * Math.max(1, facts.length));
    const showFact = () => { if (facts.length) { fact.textContent = facts[fi % facts.length]; fi++; } };
    showFact();
    const factTimer = setInterval(showFact, 5200);
    const node = el('div', { class: 'sh-load', role: 'status', 'aria-live': 'polite' }, [
      el('div', { class: 'sh-load-card' }, [
        el('div', { class: 'sh-load-head' }, [
          el('span', { html: SEAHORSE_SVG }),
          el('div', {}, [el('h2', { text: title }), el('p', { text: sub })]),
        ]),
        steps,
        el('div', { class: 'sh-load-bar' }, [bar]),
        el('div', { class: 'sh-load-foot' }, [said, pct]),
        fact,
      ]),
    ]);
    $('.sh-stage').appendChild(node);
    const mark = (n, cls) => {
      const li = steps.querySelector('[data-n="' + n + '"]');
      if (li) li.className = cls;
    };
    const paint = () => {
      const got = items.reduce((s, x) => s + Math.min(x.got, x.bytes), 0);
      const f = total ? got / total : 1;
      bar.style.width = (f * 96).toFixed(1) + '%';
      pct.textContent = Math.round(f * 96) + '%';
    };
    return {
      start(n) { mark(n, 'now'); said.textContent = (WHAT[n] || [n])[0] + '…'; },
      bytes(n, got, tot) {
        const it = items.find((x) => x.n === n);
        if (it) { if (tot) it.bytes = tot; it.got = got; }
        said.textContent = (WHAT[n] || [n])[0] + ' — ' + fmtMB(got) + (tot ? ' of ' + fmtMB(tot) : '');
        paint();
      },
      done(n) { const it = items.find((x) => x.n === n); if (it) it.got = it.bytes; mark(n, 'done'); paint(); },
      building() { mark('build', 'now'); said.textContent = 'Building surfaces and sections…'; bar.style.width = '98%'; pct.textContent = '98%'; },
      close() { clearInterval(factTimer); bar.style.width = '100%'; pct.textContent = '100%'; mark('build', 'done'); setTimeout(() => node.remove(), 220); },
      fail(msg) { clearInterval(factTimer); said.textContent = msg; said.style.color = tok('--err', 'red'); },
    };
  }
  /* Load the named blobs that are not here yet, behind the window. */
  async function need(names, title, sub) {
    const want = names.filter((n) => n === 'three' ? !S.three : !S.blobs[n]);
    if (!want.length) return true;
    if (S.loading) { await S.loading; return need(names, title, sub); }
    let release;
    S.loading = new Promise((r) => { release = r; });
    const win = loadingWindow(title, sub, want);
    try {
      for (const n of want) {
        win.start(n);
        if (n === 'three') {
          S.three = await import('./seahorse3d.js?v=1');
          win.bytes(n, 700000, 700000);
        } else {
          const raw = await fetchBytes(n, (g, t) => win.bytes(n, g, t));
          S.blobs[n] = unpack(await gunzip(raw));
        }
        win.done(n);
      }
      win.building();
      await new Promise((r) => setTimeout(r, 30));
      win.close();
      return true;
    } catch (err) {
      win.fail('Could not load: ' + err.message);
      reportClientError('seahorse:load', err.message, err.stack);
      toast('Seahorse could not load its atlas files: ' + err.message, 'err');
      return false;
    } finally {
      S.loading = null;
      release();
    }
  }

  /* ==================================================================
     Layout
     ================================================================== */
  function build() {
    root = document.getElementById('view-seahorse');
    const saved = store.get();
    if (saved.mode) S.mode = saved.mode;
    if (saved.schem) S.schem = saved.schem;
    if (saved.plane) S.slice.plane = saved.plane;
    const head = root.querySelector('.head-actions');
    head.innerHTML = '';
    head.appendChild(el('button', { class: 'btn ghost sm', text: 'Checks', title: 'What was tested against data, and how it came out',
      onclick: () => { S.side = S.side === 'checks' ? 'inspect' : 'checks'; renderSide(); } }));
    head.appendChild(el('button', { class: 'btn ghost sm', text: 'Save figure', title: 'The current view as an image (3D and slice: PNG; schematic: SVG)',
      onclick: saveFigure }));
    const body = root.querySelector('.sh-body');
    body.innerHTML = '';
    body.appendChild(el('div', { class: 'sh-bar' }));
    body.appendChild(el('div', { class: 'sh-stage' }, [
      el('div', { class: 'sh-pane', 'data-pane': 'schematic' }),
      el('div', { class: 'sh-pane', 'data-pane': 'threed' }),
      el('div', { class: 'sh-pane', 'data-pane': 'slice' }),
    ]));
    body.appendChild(el('div', { class: 'sh-trace' }));
    body.appendChild(el('aside', { class: 'sh-side' }));
    S.built = true;
    new MutationObserver(() => { if (BARRY.state.view === 'seahorse') themeChanged(); })
      .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'class', 'style'] });
  }

  function renderBar() {
    const bar = $('.sh-bar');
    bar.innerHTML = '';
    const seg = el('div', { class: 'seg', role: 'tablist', 'aria-label': 'View' },
      [['schematic', 'Schematic'], ['threed', '3D'], ['slice', 'Slice']].map(([k, t]) =>
        el('button', { class: S.mode === k ? 'active' : '', text: t, role: 'tab', 'aria-selected': String(S.mode === k),
          onclick: () => setMode(k) })));
    bar.appendChild(seg);
    if (S.mode === 'schematic') {
      bar.appendChild(el('div', { class: 'seg' }, [['circuit', 'Circuit'], ['dentate', 'Dentate, by layer']].map(([k, t]) =>
        el('button', { class: S.schem === k ? 'active' : '', text: t, onclick: () => { S.schem = k; store.set({ schem: k }); renderBar(); renderSchematic(); } }))));
    }
    if (S.mode === 'threed') {
      bar.appendChild(el('div', { class: 'seg', 'aria-label': 'Zoom level' }, [['brain', 'Brain'], ['hpf', 'Hippocampus'], ['slab', 'Slab + cells']].map(([k, t]) =>
        el('button', { class: S.level === k ? 'active' : '', text: t, onclick: () => setLevel(k) }))));
      if (S.level === 'slab') {
        bar.appendChild(rangeField('Slab at AP', 6300, 8600, 20, S.slab.ap, (v) => apText(v), (v) => {
          S.slab.ap = v; if (S.stage3) { S.stage3.setSlab(v, S.slab.thick); S.stage3.useSlab(true); } faceSoon(); }));
        bar.appendChild(rangeField('Thickness', 100, 1200, 20, S.slab.thick, (v) => v + ' µm', (v) => {
          S.slab.thick = v; if (S.stage3) { S.stage3.setSlab(S.slab.ap, v); S.stage3.useSlab(true); } }));
      }
    }
    if (S.mode === 'slice') {
      bar.appendChild(el('div', { class: 'seg', 'aria-label': 'Plane' }, [['coronal', 'Coronal'], ['sagittal', 'Sagittal'], ['horizontal', 'Horizontal']].map(([k, t]) =>
        el('button', { class: S.slice.plane === k ? 'active' : '', text: t, onclick: () => {
          S.slice.plane = k; S.slice.pos = defaultPos(k); S.slice.view = null; store.set({ plane: k }); renderBar(); drawSlice(); } }))));
      const lim = planeLimits(S.slice.plane);
      bar.appendChild(rangeField(lim.name, lim.lo, lim.hi, 10, S.slice.pos, (v) => posText(S.slice.plane, v), (v) => { S.slice.pos = v; drawSlice(); }));
      bar.appendChild(el('div', { class: 'seg', 'aria-label': 'Color by' }, [['lamina', 'Layers'], ['allen', 'Allen regions'], ['nissl', 'Nissl']].map(([k, t]) =>
        el('button', { class: S.slice.layer === k ? 'active' : '', text: t, onclick: () => { S.slice.layer = k; renderBar(); drawSlice(); } }))));
      bar.appendChild(el('span', { class: 'sh-kicker', text: 'Probe' }));
      bar.appendChild(el('div', { class: 'seg', 'aria-label': 'Probe' }, [[true, 'Shown'], [false, 'Hidden']].map(([k, t]) =>
        el('button', { class: S.probe.on === k ? 'active' : '', text: t, 'aria-pressed': String(S.probe.on === k), onclick: () => {
          S.probe.on = k; if (k && S.slice.plane === 'coronal') S.probe.ap = S.slice.pos; renderBar(); drawSlice(); syncProbe3d(); renderSide(); } }))));
      bar.appendChild(el('span', { class: 'sh-kicker', text: 'Cells' }));
      bar.appendChild(el('div', { class: 'seg', 'aria-label': 'Cells' }, [[true, 'Shown'], [false, 'Hidden']].map(([k, t]) =>
        el('button', { class: S.slice.cells === k ? 'active' : '', text: t, 'aria-pressed': String(S.slice.cells === k), onclick: async () => {
          S.slice.cells = k; if (k) await need(['cells.shb.gz'], 'Bringing in the cells', 'Real tracings, placed in the atlas.'); renderBar(); drawSlice(); } }))));
      bar.appendChild(el('span', { class: 'sh-gap' }));
      bar.appendChild(el('button', { class: 'mini', text: 'Whole section', onclick: () => { S.slice.view = null; drawSlice(); } }));
      bar.appendChild(el('button', { class: 'mini', text: 'Hippocampus', onclick: zoomHippocampus }));
    }
  }
  function rangeField(label, lo, hi, step, val, fmt, on) {
    const num = el('span', { class: 'sh-num', text: fmt(val) });
    const input = el('input', { type: 'range', min: lo, max: hi, step, value: val });
    let pend = 0;
    input.addEventListener('input', () => {
      const v = +input.value;
      num.textContent = fmt(v);
      if (pend) cancelAnimationFrame(pend);
      pend = requestAnimationFrame(() => { pend = 0; on(v); });
    });
    return el('label', { class: 'sh-field' }, [el('span', { text: label }), input, num]);
  }
  /* CCF to bregma: approximate (CCF is an average brain, not stereotaxic).
     Bregma is taken at CCF AP 5400 um, the midline at ML 5700 um. */
  const apText = (ap) => 'AP ' + ((5400 - ap) / 1000).toFixed(2) + ' mm';
  function posText(plane, v) {
    if (plane === 'coronal') return apText(v);
    if (plane === 'sagittal') return 'ML ' + ((v - 5700) / 1000).toFixed(2) + ' mm';
    return 'DV ' + (v / 1000).toFixed(2) + ' mm';
  }
  function planeLimits(p) {
    if (p === 'coronal') return { name: 'Section', lo: 400, hi: 12800 };
    if (p === 'sagittal') return { name: 'Section', lo: 5700, hi: 11200 };
    return { name: 'Section', lo: 400, hi: 7600 };
  }
  function defaultPos(p) { return p === 'coronal' ? 7300 : p === 'sagittal' ? 7300 : 2200; }

  async function setMode(m) {
    S.mode = m;
    store.set({ mode: m });
    $$('.sh-pane', root).forEach((p) => p.classList.toggle('on', p.dataset.pane === m));
    renderBar();
    if (S.stage3) (m === 'threed' ? S.stage3.resume() : S.stage3.pause());
    if (m === 'schematic') renderSchematic();
    if (m === 'threed') await ensure3d();
    if (m === 'slice') await ensureSlice();
  }
  function $$(sel, r) { return Array.from((r || root).querySelectorAll(sel)); }

  /* ==================================================================
     Schematic
     ================================================================== */
  const SVGNS = 'http://www.w3.org/2000/svg';
  function svg(tag, attrs, kids) {
    const n = document.createElementNS(SVGNS, tag);
    for (const k in (attrs || {})) {
      const v = attrs[k];
      if (v == null || v === false) continue;
      if (k === 'text') n.textContent = v;
      else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    (kids || []).forEach((c) => c && n.appendChild(c));
    return n;
  }
  function markers() {
    return svg('defs', {}, [['exc', 'var(--text-2)'], ['inh', 'var(--err)'], ['lit', 'var(--accent)']].map(([k, c]) =>
      svg('marker', { id: 'sh-ar-' + k, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' },
        [k === 'inh' ? svg('rect', { x: 3, y: 1, width: 4, height: 8, style: 'fill:' + c })
                     : svg('path', { d: 'M0,0 L10,5 L0,10 z', style: 'fill:' + c })])));
  }
  const BOX_W = 190, BOX_H = 54;
  function boxRect(r) { const w = r.w || BOX_W; return { x: r.pos[0] - w / 2, y: r.pos[1] - BOX_H / 2, w, h: BOX_H }; }
  function borderPoint(r, toward) {
    const b = boxRect(r), cx = r.pos[0], cy = r.pos[1];
    const dx = toward[0] - cx, dy = toward[1] - cy;
    if (!dx && !dy) return [cx, cy];
    const sx = (b.w / 2) / Math.abs(dx || 1e-6), sy = (b.h / 2) / Math.abs(dy || 1e-6);
    const s = Math.min(sx, sy);
    return [cx + dx * s, cy + dy * s];
  }
  function regionOfEnd(key) {
    const r = regionOf(key);
    if (r) return r;
    const c = cellOf(key);
    return c ? regionOf(c.region) : null;
  }
  const SHOW_LABEL = new Set(['lpp', 'mpp', 'mf_ca3', 'sc', 'ta', 'rc', 'sub_ec5', 'ec5_ctx', 'sub_subc']);

  function renderSchematic() {
    const pane = $('[data-pane="schematic"]');
    pane.innerHTML = '';
    if (!S.kb) return;
    const s = S.schem === 'dentate' ? dentateSvg() : circuitSvg();
    pane.appendChild(s);
    applyFocusSchematic();
  }

  function circuitSvg() {
    const kb = S.kb;
    const root_ = svg('svg', { class: 'sh-svg', viewBox: '0 0 1000 660', preserveAspectRatio: 'xMidYMid meet', role: 'img',
      'aria-label': 'Circuit of the hippocampal formation' }, [markers()]);
    // entorhinal frame
    root_.appendChild(svg('rect', { class: 'ec-box', x: 14, y: 220, width: 212, height: 340, rx: 8 }));
    root_.appendChild(svg('text', { class: 'ec-label', x: 120, y: 586, 'text-anchor': 'middle', text: 'ENTORHINAL CORTEX' }));
    const edges = svg('g', {});
    const boxes = svg('g', {});
    const labels = svg('g', { style: 'pointer-events:none' });
    root_.appendChild(edges);
    root_.appendChild(boxes);
    root_.appendChild(labels);
    const pairs = {};
    for (const c of kb.connections) {
      if (c.hidden) continue;
      const A = regionOfEnd(c.from), B = regionOfEnd(c.to);
      if (!A || !B) continue;
      if (A.key === B.key && c.key !== 'rc') continue;
      const pk = [A.key, B.key].sort().join('|');
      pairs[pk] = (pairs[pk] || 0) + 1;
      const nth = pairs[pk] - 1;
      let d, mid;
      if (A.key === B.key) {
        const b = boxRect(A);
        const x = b.x + b.w * 0.62, y = b.y;
        d = `M${x - 18},${y} C${x - 40},${y - 62} ${x + 52},${y - 62} ${x + 22},${y - 2}`;
        mid = [x + 4, y - 50];
      } else {
        const p0 = borderPoint(A, B.pos), p1 = borderPoint(B, A.pos);
        const dx = p1[0] - p0[0], dy = p1[1] - p0[1], len = Math.hypot(dx, dy) || 1;
        const bend = (0.12 + nth * 0.16) * (nth % 2 ? -1 : 1);
        const cx = (p0[0] + p1[0]) / 2 - dy / len * len * bend, cy = (p0[1] + p1[1]) / 2 + dx / len * len * bend;
        d = `M${p0[0]},${p0[1]} Q${cx},${cy} ${p1[0]},${p1[1]}`;
        mid = [0.25 * p0[0] + 0.5 * cx + 0.25 * p1[0], 0.25 * p0[1] + 0.5 * cy + 0.25 * p1[1]];
      }
      const v = verdictOf(c.key);
      const g = svg('g', { class: 'edge ' + c.sign + (c.dash ? ' dash' : ''), 'data-conn': c.key,
        onclick: (e) => { e.stopPropagation(); select({ type: 'conn', key: c.key }); } }, [
        svg('path', { class: 'hit', d }),
        svg('path', { class: 'ln', d, 'marker-end': 'url(#sh-ar-' + c.sign + ')' }),
        svg('circle', { class: 'badge', cx: mid[0], cy: mid[1], r: 4.2, style: 'fill:' + verdictColor(v.status) }),
        svg('title', { text: c.label + ' — ' + (v.status || 'cited') }),
      ]);
      edges.appendChild(g);
      if (SHOW_LABEL.has(c.key)) labels.appendChild(svg('g', { class: 'edge', 'data-conn': c.key }, [svg('text', { class: 'elabel', x: mid[0] + 8, y: mid[1] - 6, text: c.label })]));
    }
    for (const r of kb.regions) {
      const b = boxRect(r);
      boxes.appendChild(svg('g', { class: 'box', 'data-region': r.key, onclick: (e) => { e.stopPropagation(); select({ type: 'region', key: r.key }); } }, [
        svg('rect', { x: b.x, y: b.y, width: b.w, height: b.h, rx: 7 }),
        svg('text', { x: r.pos[0], y: r.pos[1] - 3, 'text-anchor': 'middle', 'font-size': 16, 'font-weight': 650, text: r.label }),
        svg('text', { class: 'sub', x: r.pos[0], y: r.pos[1] + 15, 'text-anchor': 'middle', text: r.sub }),
      ]));
    }
    root_.addEventListener('click', () => select(null));
    return root_;
  }
  function verdictColor(s) {
    return { supported: 'var(--ok)', consistent: 'var(--accent)', weak: 'var(--warn)', 'not seen': 'var(--err)', error: 'var(--err)' }[s] || 'var(--text-3)';
  }

  /* The dentate laid out by layer (the deck's slide, made exact): bands for
     each lamina, cells as glyphs, every connection ending in the layer
     where it really synapses. */
  const DG_BANDS = [['oml1', 46], ['mml1', 46], ['iml1', 34], ['gcl1', 36], ['hil', 92], ['gcl2', 36], ['iml2', 34], ['mml2', 46], ['oml2', 46]];
  const CA3_BANDS = [['ca3slm', 56], ['ca3sr', 92], ['ca3slu', 40], ['ca3sp', 40], ['ca3so', 70]];
  function dentateSvg() {
    const kb = S.kb, LC = kb.lamina_colors;
    const out = svg('svg', { class: 'sh-svg', viewBox: '0 0 1000 660', preserveAspectRatio: 'xMidYMid meet', role: 'img',
      'aria-label': 'Dentate gyrus microcircuit by layer' }, [markers()]);
    const Y = {};
    let y = 96;
    const bands = svg('g', {});
    out.appendChild(bands);
    for (const [k, h] of DG_BANDS) {
      Y[k] = [y, y + h];
      const lab = (lamOf(k) || { label: k.toUpperCase() }).label;
      bands.appendChild(svg('g', { class: 'band', 'data-layer': k, onclick: (e) => { e.stopPropagation(); select({ type: 'lamina', key: k }); } }, [
        svg('rect', { x: 200, y, width: 470, height: h, style: 'fill:' + LC[k] + ';opacity:0.32' }),
        svg('text', { x: 206, y: y + h / 2 + 4, text: lab }),
      ]));
      y += h;
    }
    let y3 = 150;
    for (const [k, h] of CA3_BANDS) {
      Y[k] = [y3, y3 + h];
      const lab = (lamOf(k) || { label: k }).label;
      bands.appendChild(svg('g', { class: 'band', 'data-layer': k, onclick: (e) => { e.stopPropagation(); select({ type: 'lamina', key: k }); } }, [
        svg('rect', { x: 760, y: y3, width: 220, height: h, style: 'fill:' + LC[k] + ';opacity:0.32' }),
        svg('text', { x: 766, y: y3 + h / 2 + 4, text: lab }),
      ]));
      y3 += h;
    }
    out.appendChild(svg('text', { x: 435, y: 80, 'text-anchor': 'middle', 'font-size': 16, 'font-weight': 650, text: 'Dentate gyrus' }));
    out.appendChild(svg('text', { x: 870, y: 134, 'text-anchor': 'middle', 'font-size': 16, 'font-weight': 650, text: 'CA3' }));
    out.appendChild(svg('text', { class: 'sub', x: 435, y: 598, 'text-anchor': 'middle', text: 'upper (suprapyramidal) blade above the hilus, lower (infrapyramidal) blade below' }));
    const mid = (k) => (Y[k][0] + Y[k][1]) / 2;
    const col = (k) => (cellOf(k) || {}).color || '#888';
    const g = (key, kids) => svg('g', { class: 'glyph', 'data-cell': key, onclick: (e) => { e.stopPropagation(); select({ type: 'cell', key }); } }, kids);
    const conn = (key, d, extra) => svg('g', { class: 'edge ' + ((connOf(key) || {}).sign || 'exc'), 'data-conn': key,
      onclick: (e) => { e.stopPropagation(); select({ type: 'conn', key }); } }, [
      svg('path', { class: 'hit', d }), svg('path', { class: 'ln', d, style: extra || '' })]);
    const conns = svg('g', {});
    const cells = svg('g', {});
    out.appendChild(conns);
    out.appendChild(cells);
    // entorhinal inputs on the left
    const ecL = [40, mid('oml1') - 60], ecM = [40, mid('mml2') + 40];
    cells.appendChild(g('fan', [svg('rect', { x: 18, y: ecL[1] - 22, width: 140, height: 44, rx: 7, style: 'fill:var(--bg-2);stroke:' + col('fan') + ';stroke-width:2' }),
      svg('text', { x: 88, y: ecL[1] - 2, 'text-anchor': 'middle', 'font-weight': 650, text: 'LEC II' }),
      svg('text', { class: 'sub', x: 88, y: ecL[1] + 14, 'text-anchor': 'middle', text: 'fan cells' })]));
    cells.appendChild(g('stel', [svg('rect', { x: 18, y: ecM[1] - 22, width: 140, height: 44, rx: 7, style: 'fill:var(--bg-2);stroke:' + col('stel') + ';stroke-width:2' }),
      svg('text', { x: 88, y: ecM[1] - 2, 'text-anchor': 'middle', 'font-weight': 650, text: 'MEC II' }),
      svg('text', { class: 'sub', x: 88, y: ecM[1] + 14, 'text-anchor': 'middle', text: 'stellate cells' })]));
    const lppS = 'stroke:' + col('fan'), mppS = 'stroke:' + col('stel');
    conns.appendChild(conn('lpp', `M158,${ecL[1]} C190,${ecL[1]} 190,${mid('oml1')} 230,${mid('oml1')} L660,${mid('oml1')}`, lppS));
    conns.appendChild(conn('lpp', `M158,${ecL[1] + 6} C182,${ecL[1] + 120} 180,${mid('oml2')} 230,${mid('oml2')} L660,${mid('oml2')}`, lppS));
    conns.appendChild(conn('mpp', `M158,${ecM[1]} C190,${ecM[1]} 190,${mid('mml2')} 230,${mid('mml2')} L660,${mid('mml2')}`, mppS));
    conns.appendChild(conn('mpp', `M158,${ecM[1] - 6} C176,${ecM[1] - 160} 180,${mid('mml1')} 230,${mid('mml1')} L660,${mid('mml1')}`, mppS));
    // granule cells, both blades
    const gcU = [300, mid('gcl1')], gcL = [300, mid('gcl2')];
    const gcDend = (x, y0, yTop) => `M${x},${y0} L${x - 34},${yTop} M${x},${y0} L${x - 8},${yTop} M${x},${y0} L${x + 16},${yTop} M${x},${y0} L${x + 38},${yTop}`;
    cells.appendChild(g('gc', [
      svg('path', { d: gcDend(gcU[0], gcU[1] - 8, Y.oml1[0] + 4), style: 'stroke:' + col('gc') + ';stroke-width:2;fill:none' }),
      svg('path', { d: `M${gcU[0] - 9},${gcU[1] + 6} L${gcU[0] + 9},${gcU[1] + 6} L${gcU[0]},${gcU[1] - 10} z`, style: 'fill:' + col('gc') }),
      svg('path', { d: gcDend(gcL[0], gcL[1] + 8, Y.oml2[1] - 4).replace(/L(\d+),(\d+)/g, (m, a, b) => 'L' + a + ',' + b), style: 'stroke:' + col('gc') + ';stroke-width:2;fill:none' }),
      svg('path', { d: `M${gcL[0] - 9},${gcL[1] - 6} L${gcL[0] + 9},${gcL[1] - 6} L${gcL[0]},${gcL[1] + 10} z`, style: 'fill:' + col('gc') }),
      svg('text', { x: gcU[0] + 14, y: gcU[1] + 4, 'font-size': 12, 'font-weight': 650, text: 'GC' }),
    ]));
    // mossy fiber: GC -> hilus collaterals -> CA3 stratum lucidum
    const mfY = mid('hil') - 18;
    conns.appendChild(conn('mf_ca3', `M${gcU[0]},${gcU[1] + 8} C${gcU[0] + 10},${mfY} ${gcU[0] + 40},${mfY} 520,${mfY} C660,${mfY} 700,${mid('ca3slu')} 760,${mid('ca3slu')} L940,${mid('ca3slu')}`,
      'stroke:' + col('gc') + ';stroke-width:2.6'));
    for (let x = 790; x < 940; x += 34) cells.appendChild(svg('circle', { cx: x, cy: mid('ca3slu'), r: 5, style: 'fill:' + col('gc') }));
    conns.appendChild(conn('mf_mc', `M360,${mfY} C370,${mfY + 18} 380,${mid('hil') + 8} 392,${mid('hil') + 10}`, 'stroke:' + col('gc')));
    conns.appendChild(conn('mf_int', `M470,${mfY} C478,${mfY + 10} 486,${mid('hil') + 10} 496,${mid('hil') + 14}`, 'stroke:' + col('gc')));
    // mossy cell (hilus) -> IML of both blades
    const mc = [400, mid('hil') + 18];
    conns.appendChild(conn('mc_gc', `M${mc[0]},${mc[1] - 6} C${mc[0] + 10},${mid('iml1')} ${mc[0] + 30},${mid('iml1')} 440,${mid('iml1')} L640,${mid('iml1')}`, 'stroke:' + col('mc')));
    conns.appendChild(conn('mc_gc', `M${mc[0]},${mc[1] + 6} C${mc[0] + 10},${mid('iml2')} ${mc[0] + 30},${mid('iml2')} 440,${mid('iml2')} L640,${mid('iml2')}`, 'stroke:' + col('mc')));
    cells.appendChild(g('mc', [
      svg('path', { d: `M${mc[0]},${mc[1]} l-28,-14 M${mc[0]},${mc[1]} l-30,16 M${mc[0]},${mc[1]} l26,-18 M${mc[0]},${mc[1]} l28,14`, style: 'stroke:' + col('mc') + ';stroke-width:3;fill:none' }),
      svg('circle', { cx: mc[0], cy: mc[1], r: 10, style: 'fill:' + col('mc') }),
      svg('text', { x: mc[0] - 9, y: mc[1] + 32, 'font-size': 12, 'font-weight': 650, text: 'MC' }),
    ]));
    // HIPP: hilus -> OML/MML of both blades
    const hp = [500, mid('hil') + 20];
    conns.appendChild(conn('hipp_gc', `M${hp[0]},${hp[1] - 8} C${hp[0] + 6},${Y.mml1[0]} ${hp[0] + 20},${mid('oml1') + 10} 530,${mid('oml1') + 8} L650,${mid('oml1') + 8}`));
    conns.appendChild(conn('hipp_gc', `M${hp[0]},${hp[1] + 8} C${hp[0] + 6},${Y.mml2[1]} ${hp[0] + 20},${mid('oml2') - 10} 530,${mid('oml2') - 8} L650,${mid('oml2') - 8}`));
    cells.appendChild(g('hipp', [svg('circle', { cx: hp[0], cy: hp[1], r: 9, style: 'fill:' + col('hipp') }),
      svg('path', { d: `M${hp[0]},${hp[1]} l-24,8 M${hp[0]},${hp[1]} l22,10`, style: 'stroke:' + col('hipp') + ';stroke-width:2' }),
      svg('text', { x: hp[0] + 12, y: hp[1] + 24, 'font-size': 12, 'font-weight': 650, text: 'HIPP' })]));
    // PV+ basket: soma at GCL1/hilus border, basket around GC somata
    const pv = [570, Y.gcl1[1] + 6];
    conns.appendChild(conn('pv_gc', `M${pv[0]},${pv[1]} C${pv[0] - 30},${mid('gcl1') + 2} ${gcU[0] + 60},${mid('gcl1')} ${gcU[0] + 12},${mid('gcl1')}`));
    conns.appendChild(conn('pp_pv', `M230,${mid('mml1') + 6} C420,${mid('mml1') + 6} ${pv[0] - 6},${mid('mml1') + 14} ${pv[0]},${Y.iml1[1]}`, 'stroke:' + col('stel') + ';stroke-dasharray:3 4'));
    conns.appendChild(conn('gc_pv', `M${gcU[0] + 30},${mfY} C480,${mfY - 4} ${pv[0] - 10},${pv[1] + 20} ${pv[0]},${pv[1] + 8}`, 'stroke:' + col('gc') + ';stroke-dasharray:3 4'));
    cells.appendChild(g('pvbc', [svg('path', { d: `M${pv[0]},${pv[1]} l-10,-36 M${pv[0]},${pv[1]} l12,-40 M${pv[0]},${pv[1]} l4,30`, style: 'stroke:' + col('pvbc') + ';stroke-width:2' }),
      svg('circle', { cx: pv[0], cy: pv[1], r: 9, style: 'fill:' + col('pvbc') }),
      svg('text', { x: pv[0] + 12, y: pv[1] + 20, 'font-size': 12, 'font-weight': 650, text: 'PV+ BC' })]));
    // axo-axonic: cartridges at the GCL/hilus border
    const aa = [628, Y.gcl1[1] + 10];
    conns.appendChild(conn('aac_gc', `M${aa[0]},${aa[1]} C${aa[0] - 40},${Y.gcl1[1] + 14} ${gcU[0] + 40},${Y.gcl1[1] + 10} ${gcU[0] + 4},${Y.gcl1[1] + 2}`));
    cells.appendChild(g('aac', [svg('path', { d: `M${aa[0]},${aa[1]} l-6,-44 M${aa[0]},${aa[1]} l10,-46`, style: 'stroke:' + col('aac') + ';stroke-width:2' }),
      svg('circle', { cx: aa[0], cy: aa[1], r: 8, style: 'fill:' + col('aac') }),
      svg('text', { x: aa[0] - 12, y: aa[1] + 24, 'font-size': 12, 'font-weight': 650, text: 'AAC' })]));
    // semilunar granule cell in the IML
    const sg = [440, mid('iml1')];
    conns.appendChild(conn('sgc_hil', `M${sg[0]},${sg[1] + 6} C${sg[0] - 6},${mid('hil') - 30} ${sg[0] - 30},${mid('hil') + 6} ${mc[0] + 12},${mc[1] - 6}`, 'stroke:' + col('sgc')));
    cells.appendChild(g('sgc', [svg('path', { d: `M${sg[0]},${sg[1]} L${sg[0] - 50},${Y.oml1[0] + 6} M${sg[0]},${sg[1]} L${sg[0] - 18},${Y.oml1[0] + 4} M${sg[0]},${sg[1]} L${sg[0] + 20},${Y.oml1[0] + 4} M${sg[0]},${sg[1]} L${sg[0] + 54},${Y.oml1[0] + 6}`, style: 'stroke:' + col('sgc') + ';stroke-width:2;fill:none' }),
      svg('ellipse', { cx: sg[0], cy: sg[1], rx: 11, ry: 6, style: 'fill:' + col('sgc') }),
      svg('text', { x: sg[0] + 14, y: sg[1] + 14, 'font-size': 12, 'font-weight': 650, text: 'SGC' })]));
    // CA3 pyramidal cell
    const c3 = [880, mid('ca3sp')];
    cells.appendChild(g('ca3', [svg('path', { d: `M${c3[0]},${c3[1] - 8} L${c3[0]},${Y.ca3slm[0] + 6} M${c3[0]},${mid('ca3sr')} l-30,-30 M${c3[0]},${mid('ca3sr')} l26,-34 M${c3[0]},${c3[1] + 8} l-22,40 M${c3[0]},${c3[1] + 8} l20,44`, style: 'stroke:' + col('ca3') + ';stroke-width:2.2;fill:none' }),
      svg('path', { d: `M${c3[0] - 11},${c3[1] + 8} L${c3[0] + 11},${c3[1] + 8} L${c3[0]},${c3[1] - 12} z`, style: 'fill:' + col('ca3') }),
      svg('text', { x: c3[0] + 14, y: c3[1] + 4, 'font-size': 12, 'font-weight': 650, text: 'CA3 PC' })]));
    conns.appendChild(conn('back', `M${c3[0] - 4},${c3[1] + 10} C${c3[0] - 60},${Y.ca3so[1] + 40} 600,${mid('hil') + 60} ${mc[0] + 14},${mc[1] + 8}`, 'stroke:' + col('ca3') + ';stroke-dasharray:6 5'));
    conns.appendChild(conn('rc', `M${c3[0] + 6},${c3[1] + 10} C${c3[0] + 80},${Y.ca3so[1]} ${c3[0] + 90},${mid('ca3sr')} ${c3[0] + 30},${mid('ca3sr')}`, 'stroke:' + col('ca3')));
    out.addEventListener('click', () => select(null));
    // the DS overlays live on the bands (applyFocusSchematic sets them)
    out._bandY = Y;
    return out;
  }

  function applyFocusSchematic() {
    const s = $('[data-pane="schematic"] svg');
    if (!s) return;
    const f = S.focus;
    s.querySelectorAll('.flow,.sinkrect').forEach((n) => n.remove());
    const on = f && (f.cells.size || f.regionKeys.size || f.conns.size || f.layers.size);
    s.querySelectorAll('[data-region]').forEach((n) => {
      const k = n.dataset.region;
      const lit = on && (f.regionKeys.has(k));
      n.classList.toggle('dim', !!on && !lit);
      n.classList.toggle('lit', !!lit);
      n.classList.toggle('sel', !!(S.sel && S.sel.type === 'region' && S.sel.key === k));
    });
    s.querySelectorAll('[data-cell]').forEach((n) => n.classList.toggle('dim', !!on && !f.cells.has(n.dataset.cell)));
    s.querySelectorAll('[data-layer]').forEach((n) => n.classList.toggle('dim', !!on && f.layers.size > 0 && !f.layers.has(n.dataset.layer)));
    s.querySelectorAll('[data-conn]').forEach((n) => {
      const k = n.dataset.conn;
      const lit = on && f.conns.has(k);
      n.classList.toggle('dim', !!on && !lit);
      n.classList.toggle('lit', !!lit);
      n.classList.toggle('sel', !!(S.sel && S.sel.type === 'conn' && S.sel.key === k));
      if (lit) {
        const p = n.querySelector('path.ln');
        if (p) n.appendChild(svg('path', { class: 'flow', d: p.getAttribute('d') }));
      }
    });
    // DS sinks and sources on the bands
    if (S.trace.ds) {
      const ds = S.trace.ds;
      s.querySelectorAll('[data-layer]').forEach((n) => {
        const k = n.dataset.layer;
        const r = n.querySelector('rect');
        if (!r) return;
        const sink = ds.sink.includes(k), src = ds.source.includes(k);
        if (!sink && !src) return;
        n.classList.remove('dim');
        n.insertBefore(svg('rect', { class: 'sinkrect ' + (sink ? 'sink' : ''), x: r.getAttribute('x'), y: r.getAttribute('y'),
          width: r.getAttribute('width'), height: r.getAttribute('height'),
          style: 'fill:' + (sink ? 'var(--err)' : 'var(--accent)') + ';opacity:' + (sink ? 0.55 : 0.28) }), r.nextSibling);
      });
    }
  }

  /* ==================================================================
     3D
     ================================================================== */
  function colorsFor3d() {
    return { shell: tok('--text-2', '#9aa'), hpf: tok('--accent', '#e5a823'), bg: tok('--bg', '#111'),
             probe: tok('--text', '#ddd'), contact: tok('--accent', '#e5a823') };
  }
  async function ensure3d() {
    const pane = $('[data-pane="threed"]');
    const ok = await need(['three', 'mesh_brain.shb.gz'], 'Seahorse is getting the brain ready', 'The first time only; after this it is instant.');
    if (!ok) return;
    if (!S.stage3) {
      pane.innerHTML = '';
      S.stage3 = S.three.create(pane, { colors: colorsFor3d(), onPick: pick3d });
      S.stage3.addBrain(S.blobs['mesh_brain.shb.gz']);
      pane.appendChild(el('div', { class: 'sh-hint', text: 'Drag to turn, right-drag to move, wheel to zoom. Click anything to read about it.' }));
      pane.appendChild(el('div', { class: 'sh-legend', 'data-legend': '1' }));
      S.stage3.setLevel('brain');
    }
    await setLevel(S.level, true);
  }
  const REGION_COLORS = { DG: '#2a9d8f', CA1: '#c2185b', CA2: '#e07a55', CA3: '#b8323c', SUB: '#c9a45c', ProS: '#b8934d',
    ENTl: '#d16ba5', ENTm: '#3d7dd8', PRE: '#9c7bd6', POST: '#8a6cc8', PAR: '#7b8fd9', PERI: '#a0a07a', ECT: '#8e8e6e', VISpor: '#6f9fae' };
  async function setLevel(lv, quiet) {
    S.level = lv;
    if (!quiet) renderBar(); else renderBar();
    if (!S.stage3) return;
    if (lv === 'hpf' || lv === 'slab') {
      const ok = await need(['mesh_hpf.shb.gz', 'mesh_lamina.shb.gz'].concat(lv === 'slab' ? ['cells.shb.gz'] : []),
        lv === 'slab' ? 'Opening a slab of the hippocampus' : 'Flying into the hippocampus',
        lv === 'slab' ? 'Layers at 10 µm, and the cells that live in them.' : 'Its regions, and the layers inside them.');
      if (!ok) return;
      if (!S.stage3.has('hpf')) S.stage3.addHpf(S.blobs['mesh_hpf.shb.gz'], (k) => REGION_COLORS[k]);
      if (!S.stage3.has('lamina')) S.stage3.addLamina(S.blobs['mesh_lamina.shb.gz'], S.kb.lamina_colors);
      if (lv === 'slab' && !S.stage3.has('cells')) S.stage3.addCells(S.blobs['cells.shb.gz'], (k) => (cellOf(k) || {}).color || '#ccc');
    }
    S.stage3.setSlab(S.slab.ap, S.slab.thick);
    S.stage3.setLevel(lv, { lamina: lv === 'slab' });
    renderLegend3d();
    if (lv === 'slab') faceSoon(); else S.stage3.setFace(null);
    syncProbe3d();
    applyFocus3d();
  }
  function renderLegend3d() {
    const lg = $('[data-legend]');
    if (!lg) return;
    lg.innerHTML = '';
    const item = (kind, key, label, color, shown, sq) => el('button', { 'aria-pressed': String(shown), title: 'Show or hide ' + label,
      onclick: (e) => { const on = e.currentTarget.getAttribute('aria-pressed') !== 'true'; e.currentTarget.setAttribute('aria-pressed', String(on)); S.stage3.setVisible(kind, key, on); } },
      [el('span', { class: 'sh-sw' + (sq ? ' sq' : ''), style: 'background:' + color }), el('span', { text: label })]);
    if (S.level === 'brain') {
      lg.appendChild(el('span', { class: 'sh-kicker', text: 'Show' }));
      const B = S.blobs['mesh_brain.shb.gz'].header.meshes;
      for (const m of B) lg.appendChild(item('brain', m.key, m.key === 'root' ? 'Brain surface' : m.name, m.key === 'HPF' ? tok('--accent', '#e5a823') : m.color, m.key === 'root' || m.key === 'HPF', true));
    } else if (S.level === 'hpf') {
      lg.appendChild(el('span', { class: 'sh-kicker', text: 'Regions' }));
      for (const m of S.blobs['mesh_hpf.shb.gz'].header.meshes) {
        if (!REGION_COLORS[m.key]) continue;
        lg.appendChild(item('hpf', m.key, m.key + ' — ' + m.name.replace(/^Entorhinal area, /, 'EC, '), REGION_COLORS[m.key],
          ['DG', 'CA1', 'CA2', 'CA3', 'SUB', 'ProS', 'ENTl', 'ENTm', 'PRE', 'POST', 'PAR'].includes(m.key), true));
      }
      lg.appendChild(el('span', { class: 'sh-kicker', text: 'Layers (right side)' }));
      lg.appendChild(el('button', { 'aria-pressed': 'false', onclick: (e) => { const on = e.currentTarget.getAttribute('aria-pressed') !== 'true'; e.currentTarget.setAttribute('aria-pressed', String(on));
        S.stage3.showLamina(on, ['alv', 'fi']); } },
        [el('span', { class: 'sh-sw sq', style: 'background:' + S.kb.lamina_colors.gcl1 }), el('span', { text: 'Laminae (alveus and fimbria left off)' })]));
    } else {
      lg.appendChild(el('span', { class: 'sh-kicker', text: 'Cells' }));
      for (const c of S.kb.cells) lg.appendChild(item('cells', c.key, c.label, c.color, true));
      lg.appendChild(el('span', { class: 'sh-kicker', text: 'Layers' }));
      for (const k of ['oml1', 'mml1', 'iml1', 'gcl1', 'hil', 'ca3sp', 'ca3slu', 'ca1so', 'ca1sp', 'ca1sr', 'ca1slm']) {
        const l = lamOf(k);
        lg.appendChild(item('lamina', k, l ? l.label : k, S.kb.lamina_colors[k], true, true));
      }
    }
  }
  function pick3d(ud) {
    if (!ud) { select(null); return; }
    if (ud.kind === 'cell') select({ type: 'cell', key: ud.key });
    else if (ud.kind === 'lamina') select({ type: 'lamina', key: ud.key });
    else if (ud.kind === 'region') {
      const r = S.kb.regions.find((x) => x.allen.includes(ud.key));
      select(r ? { type: 'region', key: r.key } : { type: 'allen', key: ud.key, name: ud.name });
    }
  }
  let faceTimer = 0;
  function faceSoon() {
    clearTimeout(faceTimer);
    faceTimer = setTimeout(async () => {
      if (!S.stage3 || S.level !== 'slab') return;
      if (!S.blobs['hip20.shb.gz']) {
        const ok = await need(['brain50.shb.gz', 'hip20.shb.gz', 'hip10d.shb.gz'], 'Cutting the section face', 'The atlas section that lies on the front of the slab.');
        if (!ok) return;
      }
      const box = { ap: S.slab.ap - S.slab.thick / 2, dv0: 900, dv1: 3500, ml0: 5700, ml1: 9300 };
      const c = renderSectionCanvas('coronal', box.ap, box.ml0, box.ml1, box.dv0, box.dv1, 4, 'lamina', true);
      S.stage3.setFace(c, box);
    }, 120);
  }
  function syncProbe3d() {
    if (S.stage3) S.stage3.setProbe(S.probe.on ? S.probe : null);
  }
  function applyFocus3d() {
    if (!S.stage3) return;
    const f = S.focus;
    if (!f) { S.stage3.focus(null); return; }
    const allen = new Set();
    f.regionKeys.forEach((k) => (regionOf(k) || { allen: [] }).allen.forEach((a) => allen.add(a)));
    f.cells.forEach((k) => { const c = cellOf(k); if (c) (regionOf(c.region) || { allen: [] }).allen.forEach((a) => allen.add(a)); });
    S.stage3.focus({ cells: f.cells, regions: allen, layers: f.layers });
  }

  /* ==================================================================
     Slice
     ================================================================== */
  async function ensureSlice() {
    const ok = await need(['brain50.shb.gz', 'hip20.shb.gz', 'hip10d.shb.gz'].concat(S.slice.cells ? ['cells.shb.gz'] : []),
      'Preparing the sections', 'The whole brain every 50 µm, the hippocampus every 20, its dorsal part every 10.');
    if (!ok) return;
    const pane = $('[data-pane="slice"]');
    if (!pane.querySelector('canvas')) {
      pane.innerHTML = '';
      const wrap = el('div', { class: 'sh-slice-wrap' }, [el('canvas', { class: 'base' }), el('canvas', { class: 'hl' }), el('canvas', { class: 'top' })]);
      pane.appendChild(wrap);
      pane.appendChild(el('div', { class: 'sh-hint', text: 'Wheel to zoom, drag to move. Hover for the structure; with the probe shown, drag its tip.' }));
      wireSlice(wrap);
      new ResizeObserver(() => { if (S.mode === 'slice') drawSlice(); }).observe(wrap);
    }
    if (!S.slice.view) zoomHippocampus();
    else drawSlice();
  }
  function lut() {
    if (S._lut) return S._lut;
    const b50 = S.blobs['brain50.shb.gz'].header.structures;
    const allen = new Uint8Array(b50.length * 3);
    b50.forEach((s, i) => { const c = hexRgb(s.color); allen.set(c, i * 3); });
    const lamCodes = S.blobs['hip20.shb.gz'].header.lamina;
    const lam = new Uint8Array(256 * 3);
    lamCodes.forEach((l) => { if (l.code) lam.set(hexRgb(S.kb.lamina_colors[l.key] || '#888'), l.code * 3); });
    S._lut = { allen, lam };
    return S._lut;
  }
  /* What is at one point (CCF um): the finest label that covers it. */
  function sampleAt(ap, dv, ml) {
    const out = { lam: 0, allen: 0, nissl: 0 };
    const B = S.blobs['brain50.shb.gz'], H = S.blobs['hip20.shb.gz'], D = S.blobs['hip10d.shb.gz'];
    let i = Math.floor(ap / 50), j = Math.floor(dv / 50), k = Math.floor(ml / 50);
    if (i >= 0 && j >= 0 && k >= 0 && i < 264 && j < 160 && k < 228) {
      const n = (i * 160 + j) * 228 + k;
      out.allen = B.arrays.labels[n];
      out.nissl = B.arrays.nissl[n] * 8;
    }
    const ho = H.header.origin_um, hs = H.header.arrays[0].shape;
    i = Math.floor((ap - ho[0]) / 20); j = Math.floor((dv - ho[1]) / 20); k = Math.floor((ml - ho[2]) / 20);
    if (i >= 0 && j >= 0 && k >= 0 && i < hs[0] && j < hs[1] && k < hs[2]) {
      const n = (i * hs[1] + j) * hs[2] + k;
      out.lam = H.arrays.labels[n];
      out.nissl = H.arrays.nissl[n] * 8;
    }
    const dO = D.header.origin_um, ds = D.header.arrays[0].shape;
    i = Math.floor((ap - dO[0]) / 10); j = Math.floor((dv - dO[1]) / 10); k = Math.floor((ml - dO[2]) / 10);
    if (i >= 0 && j >= 0 && k >= 0 && i < ds[0] && j < ds[1] && k < ds[2]) {
      out.lam = D.arrays.labels[(i * ds[1] + j) * ds[2] + k];
    }
    return out;
  }
  /* Plane coordinates (u right, v down, in um) -> CCF [ap, dv, ml]. */
  function planeToCcf(plane, pos, u, v) {
    if (plane === 'coronal') return [pos, v, u];
    if (plane === 'sagittal') return [u, v, pos];
    return [v, pos, u];   // horizontal: u = ML, v = AP
  }
  function planeExtent(plane) {
    if (plane === 'coronal') return { u0: 0, u1: 11400, v0: 0, v1: 8000 };
    if (plane === 'sagittal') return { u0: 0, u1: 13200, v0: 0, v1: 8000 };
    return { u0: 0, u1: 11400, v0: 0, v1: 13200 };
  }
  /* Draw a section into a canvas: um box, pixel scale, coloring mode. */
  function renderSectionCanvas(plane, pos, u0, u1, v0, v1, pxPerUm10, mode, face) {
    const W = Math.max(2, Math.round((u1 - u0) / 10 * pxPerUm10 / 4)), H = Math.max(2, Math.round((v1 - v0) / 10 * pxPerUm10 / 4));
    const c = document.createElement('canvas');
    c.width = W; c.height = H;
    paintSection(c, plane, pos, u0, (u1 - u0) / W, v0, (v1 - v0) / H, mode, face);
    return c;
  }
  function paintSection(canvas, plane, pos, u0, du, v0, dv, mode, face) {
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    const img = ctx.createImageData(W, H);
    const px = img.data;
    const L = lut();
    const bg = hexRgb(tok('--bg', '#111')), ink = hexRgb(tok('--text', '#eee'));
    const dark = (bg[0] + bg[1] + bg[2]) < 380;
    const ids = new Int32Array(W * H);
    for (let y = 0; y < H; y++) {
      const v = v0 + (y + 0.5) * dv;
      for (let x = 0; x < W; x++) {
        const u = u0 + (x + 0.5) * du;
        const p = planeToCcf(plane, pos, u, v);
        const s = sampleAt(p[0], p[1], p[2]);
        const o = (y * W + x) * 4;
        if (!s.allen && !s.lam) {
          if (face) { px[o + 3] = 0; } else { px[o] = bg[0]; px[o + 1] = bg[1]; px[o + 2] = bg[2]; px[o + 3] = 0; }
          ids[y * W + x] = -1;
          continue;
        }
        // Nissl: dense = ink, sparse = paper
        const n = Math.min(1, s.nissl / 255) * 0.85;
        const paper = dark ? [bg[0] + 14, bg[1] + 14, bg[2] + 16] : [252, 250, 246];
        let r = paper[0] + (ink[0] - paper[0]) * n, g = paper[1] + (ink[1] - paper[1]) * n, b = paper[2] + (ink[2] - paper[2]) * n;
        if (mode === 'lamina' && s.lam) {
          const a = 0.62;
          r = r * (1 - a) + L.lam[s.lam * 3] * a; g = g * (1 - a) + L.lam[s.lam * 3 + 1] * a; b = b * (1 - a) + L.lam[s.lam * 3 + 2] * a;
        } else if (face) {
          // the section face in 3D: Nissl only outside the laminae
        } else if (mode === 'allen' || (mode === 'lamina' && s.allen)) {
          const a = mode === 'allen' ? 0.72 : 0.14;
          r = r * (1 - a) + L.allen[s.allen * 3] * a; g = g * (1 - a) + L.allen[s.allen * 3 + 1] * a; b = b * (1 - a) + L.allen[s.allen * 3 + 2] * a;
        }
        px[o] = r; px[o + 1] = g; px[o + 2] = b; px[o + 3] = 255;
        ids[y * W + x] = (mode === 'lamina' && s.lam) ? 100000 + s.lam : s.allen;
      }
    }
    // outlines where the label changes
    const edgeA = mode === 'nissl' ? 0.18 : 0.42;
    for (let y = 0; y < H - 1; y++) {
      for (let x = 0; x < W - 1; x++) {
        const i = y * W + x, a = ids[i];
        if (a < 0 || (face && a < 100000)) continue;
        if (a !== ids[i + 1] || a !== ids[i + W]) {
          const o = i * 4;
          const k = (a >= 100000 || ids[i + 1] >= 100000 || ids[i + W] >= 100000) ? edgeA + 0.15 : edgeA;
          px[o] = px[o] * (1 - k) + ink[0] * k * 0.6; px[o + 1] = px[o + 1] * (1 - k) + ink[1] * k * 0.6; px[o + 2] = px[o + 2] * (1 - k) + ink[2] * k * 0.6;
        }
      }
    }
    ctx.putImageData(img, 0, 0);
  }
  function zoomHippocampus() {
    const p = S.slice.plane;
    if (p === 'coronal') S.slice.view = { cu: 7350, cv: 2350, umPerPx: 0 , fit: [5700, 9300, 900, 3800] };
    else if (p === 'sagittal') S.slice.view = { fit: [5200, 10200, 900, 5600] };
    else S.slice.view = { fit: [5700, 10200, 5600, 10600] };
    S.slice.view.umPerPx = 0;
    drawSlice();
  }
  let sliceRaf = 0;
  function drawSlice() {
    if (sliceRaf) return;
    sliceRaf = requestAnimationFrame(() => { sliceRaf = 0; drawSliceNow(); });
  }
  function sliceGeom(cv) {
    const r = cv.getBoundingClientRect();
    const dpr = Math.min(1.5, window.devicePixelRatio || 1);
    const W = Math.max(50, Math.round(r.width * dpr)), H = Math.max(50, Math.round(r.height * dpr));
    let v = S.slice.view;
    if (!v || !v.umPerPx) {
      const e = planeExtent(S.slice.plane);
      const f = (v && v.fit) || [e.u0, e.u1, e.v0, e.v1];
      const k = Math.max((f[1] - f[0]) / W, (f[3] - f[2]) / H) * 1.04;
      v = S.slice.view = { cu: (f[0] + f[1]) / 2, cv: (f[2] + f[3]) / 2, umPerPx: k };
    }
    return { W, H, dpr, u0: v.cu - v.umPerPx * W / 2, v0: v.cv - v.umPerPx * H / 2, k: v.umPerPx };
  }
  function drawSliceNow() {
    const wrap = $('.sh-slice-wrap');
    if (!wrap || !S.blobs['hip20.shb.gz']) return;
    const [base, hl, top] = wrap.querySelectorAll('canvas');
    const g = sliceGeom(base);
    [base, hl, top].forEach((c) => { c.width = g.W; c.height = g.H; });
    paintSection(base, S.slice.plane, S.slice.pos, g.u0, g.k, g.v0, g.k, S.slice.layer, false);
    paintHighlight(hl, g);
    paintTop(top, g);
    if (S.sel && S.sel.type === 'probe') renderSide();
  }
  /* Layers lit by the tracer / DS, on their own canvas so they can pulse. */
  function paintHighlight(cv, g) {
    const ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, cv.width, cv.height);
    const f = S.focus;
    const ds = S.trace.ds;
    const want = new Map();
    if (ds) { ds.sink.forEach((k) => want.set(k, hexRgb(tok('--err', '#e44')).concat(170))); ds.source.forEach((k) => want.set(k, hexRgb(tok('--accent', '#4ae')).concat(90))); }
    else if (f && f.layers.size) f.layers.forEach((k) => want.set(k, hexRgb(tok('--accent', '#e5a823')).concat(150)));
    if (!want.size) { cv.classList.remove('sh-pulse'); return; }
    const codes = new Map();
    for (const l of S.blobs['hip20.shb.gz'].header.lamina) if (want.has(l.key)) codes.set(l.code, want.get(l.key));
    const step = 2;
    const img = ctx.createImageData(cv.width, cv.height);
    for (let y = 0; y < cv.height; y += step) {
      for (let x = 0; x < cv.width; x += step) {
        const p = planeToCcf(S.slice.plane, S.slice.pos, g.u0 + (x + 1) * g.k, g.v0 + (y + 1) * g.k);
        const s = sampleAt(p[0], p[1], p[2]);
        const c = codes.get(s.lam);
        if (!c) continue;
        for (let yy = y; yy < Math.min(cv.height, y + step); yy++) for (let xx = x; xx < Math.min(cv.width, x + step); xx++) {
          const o = (yy * cv.width + xx) * 4;
          img.data[o] = c[0]; img.data[o + 1] = c[1]; img.data[o + 2] = c[2]; img.data[o + 3] = c[3];
        }
      }
    }
    ctx.putImageData(img, 0, 0);
    cv.style.animation = ds && !BARRY.ui.reducedMotion() ? 'sh-sink 1.4s ease-in-out infinite' : '';
  }
  function paintTop(cv, g) {
    const ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, cv.width, cv.height);
    const toPx = (u, v) => [(u - g.u0) / g.k, (v - g.v0) / g.k];
    const plane = S.slice.plane, pos = S.slice.pos;
    // cells within the slab around this plane
    if (S.slice.cells && S.blobs['cells.shb.gz']) {
      const C = S.blobs['cells.shb.gz'];
      const half = 150;
      const axisOf = plane === 'coronal' ? 0 : plane === 'sagittal' ? 2 : 1;
      const uv = (p, i) => plane === 'coronal' ? [p[i * 3 + 2], p[i * 3 + 1]] : plane === 'sagittal' ? [p[i * 3], p[i * 3 + 1]] : [p[i * 3 + 2], p[i * 3]];
      for (const c of C.header.cells) {
        const P = C.arrays['p:' + c.key], T = C.arrays['t:' + c.key], A = C.arrays['a:' + c.key];
        const dim = S.focus && S.focus.cells.size && !S.focus.cells.has(c.key);
        const col = (cellOf(c.key) || {}).color || '#ccc';
        ctx.lineCap = 'round';
        for (const pass of [2, 3]) {
          ctx.beginPath();
          for (let i = 0; i < T.length; i++) {
            const p = A[i];
            if (p < 0) continue;
            const t = T[i];
            if (pass === 2 ? t !== 2 : (t !== 3 && t !== 4)) continue;
            if (Math.abs(P[i * 3 + axisOf] - pos) > half && Math.abs(P[p * 3 + axisOf] - pos) > half) continue;
            const a = toPx(...uv(P, p)), b = toPx(...uv(P, i));
            ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]);
          }
          ctx.strokeStyle = col;
          ctx.globalAlpha = dim ? 0.12 : (pass === 2 ? 0.55 : 0.95);
          ctx.lineWidth = (pass === 2 ? 0.8 : 1.6) * g.dpr;
          ctx.stroke();
        }
        if (Math.abs(c.soma_um[axisOf] - pos) <= half) {
          const s = toPx(...(plane === 'coronal' ? [c.soma_um[2], c.soma_um[1]] : plane === 'sagittal' ? [c.soma_um[0], c.soma_um[1]] : [c.soma_um[2], c.soma_um[0]]));
          ctx.globalAlpha = dim ? 0.2 : 1;
          ctx.fillStyle = col;
          ctx.beginPath(); ctx.arc(s[0], s[1], 4.5 * g.dpr, 0, Math.PI * 2); ctx.fill();
          ctx.strokeStyle = tok('--bg', '#000'); ctx.lineWidth = 1.2 * g.dpr; ctx.stroke();
        }
        ctx.globalAlpha = 1;
      }
    }
    // the probe
    if (S.probe.on) {
      const pr = S.probe;
      const inPlane = plane === 'coronal' ? Math.abs(pr.ap - pos) < 60 : plane === 'sagittal' ? Math.abs(pr.ml - pos) < 60 : true;
      ctx.globalAlpha = inPlane ? 1 : 0.35;
      const surf = surfaceDv(pr.ap, pr.ml);
      let a, b;
      if (plane === 'coronal') { a = toPx(pr.ml, surf - 300); b = toPx(pr.ml, pr.dv); }
      else if (plane === 'sagittal') { a = toPx(pr.ap, surf - 300); b = toPx(pr.ap, pr.dv); }
      else { a = b = toPx(pr.ml, pr.ap); }
      const w = Math.max(3, 70 / g.k);
      ctx.fillStyle = tok('--text', '#eee');
      ctx.globalAlpha *= 0.85;
      ctx.beginPath();
      ctx.moveTo(a[0] - w / 2, a[1]); ctx.lineTo(b[0] - w / 2, b[1] - w); ctx.lineTo(b[0], b[1]); ctx.lineTo(b[0] + w / 2, b[1] - w); ctx.lineTo(a[0] + w / 2, a[1]); ctx.closePath();
      ctx.fill();
      ctx.globalAlpha = inPlane ? 1 : 0.35;
      if (plane !== 'horizontal') {
        ctx.fillStyle = tok('--accent', '#e5a823');
        for (let i = 0; i < pr.contacts; i++) {
          const c = plane === 'coronal' ? toPx(pr.ml, pr.dv - 40 - i * pr.pitch) : toPx(pr.ap, pr.dv - 40 - i * pr.pitch);
          ctx.fillRect(c[0] - Math.max(1.2, 8 / g.k), c[1] - Math.max(0.8, 5 / g.k), Math.max(2.4, 16 / g.k), Math.max(1.6, 10 / g.k));
        }
      }
      // the tip handle
      ctx.strokeStyle = tok('--accent', '#e5a823');
      ctx.lineWidth = 2 * g.dpr;
      ctx.beginPath(); ctx.arc(b[0], b[1], 7 * g.dpr, 0, Math.PI * 2); ctx.stroke();
      ctx.globalAlpha = 1;
    }
  }
  function surfaceDv(ap, ml) {
    for (let dv = 0; dv < 8000; dv += 50) { const s = sampleAt(ap, dv, ml); if (s.allen) return dv; }
    return 0;
  }
  /* Contacts -> layer, as runs (contact 1 = nearest the tip). */
  function probeRuns() {
    const pr = S.probe, runs = [];
    for (let i = 0; i < pr.contacts; i++) {
      const dv = pr.dv - 40 - i * pr.pitch;
      const s = sampleAt(pr.ap, dv, pr.ml);
      const lam = s.lam ? (S.blobs['hip20.shb.gz'].header.lamina.find((l) => l.code === s.lam) || {}) : null;
      const st = S.blobs['brain50.shb.gz'].header.structures[s.allen] || {};
      const name = lam ? lam.label : (st.acronym || 'outside');
      const key = lam ? lam.key : null;
      const last = runs[runs.length - 1];
      if (last && last.name === name) last.to = i + 1;
      else runs.push({ from: i + 1, to: i + 1, name, key, full: lam ? lam.name : st.name });
    }
    return runs;
  }
  function wireSlice(wrap) {
    const top = wrap.querySelector('canvas.top');
    const tip = el('div', { class: 'sh-tip', style: 'display:none' });
    wrap.appendChild(tip);
    let drag = null;
    const toUm = (e) => {
      const r = top.getBoundingClientRect();
      const g = sliceGeom(top);
      const x = (e.clientX - r.left) * g.dpr, y = (e.clientY - r.top) * g.dpr;
      return { u: g.u0 + x * g.k, v: g.v0 + y * g.k, x, y, g };
    };
    top.addEventListener('wheel', (e) => {
      e.preventDefault();
      const m = toUm(e);
      const v = S.slice.view;
      const f = Math.exp(e.deltaY * 0.0015);
      const k2 = Math.min(60, Math.max(1.2, v.umPerPx * f));
      v.cu = m.u + (v.cu - m.u) * (k2 / v.umPerPx);
      v.cv = m.v + (v.cv - m.v) * (k2 / v.umPerPx);
      v.umPerPx = k2;
      drawSlice();
    }, { passive: false });
    top.addEventListener('pointerdown', (e) => {
      const m = toUm(e);
      top.setPointerCapture(e.pointerId);
      if (S.probe.on && S.slice.plane !== 'horizontal') {
        const tu = S.slice.plane === 'coronal' ? S.probe.ml : S.probe.ap;
        if (Math.hypot((tu - m.u) / m.g.k, (S.probe.dv - m.v) / m.g.k) < 14 * m.g.dpr) { drag = { probe: true }; return; }
      }
      drag = { x: e.clientX, y: e.clientY, cu: S.slice.view.cu, cv: S.slice.view.cv, moved: false };
    });
    top.addEventListener('pointermove', (e) => {
      const m = toUm(e);
      if (drag && drag.probe) {
        if (S.slice.plane === 'coronal') { S.probe.ml = Math.round(m.u); S.probe.ap = S.slice.pos; } else S.probe.ap = Math.round(m.u);
        S.probe.dv = Math.round(m.v);
        drawSlice(); syncProbe3d();
        return;
      }
      if (drag) {
        const g = m.g;
        const dx = (e.clientX - drag.x) * g.dpr * g.k, dy = (e.clientY - drag.y) * g.dpr * g.k;
        if (Math.abs(dx) + Math.abs(dy) > 2) drag.moved = true;
        S.slice.view.cu = drag.cu - dx; S.slice.view.cv = drag.cv - dy;
        drawSlice();
        tip.style.display = 'none';
        return;
      }
      const p = planeToCcf(S.slice.plane, S.slice.pos, m.u, m.v);
      const s = sampleAt(p[0], p[1], p[2]);
      if (!s.allen && !s.lam) { tip.style.display = 'none'; return; }
      const st = S.blobs['brain50.shb.gz'].header.structures[s.allen] || {};
      const lam = s.lam ? S.blobs['hip20.shb.gz'].header.lamina.find((l) => l.code === s.lam) : null;
      tip.innerHTML = '';
      if (lam) tip.appendChild(el('div', {}, [el('b', { text: lam.label + ' ' }), document.createTextNode(lam.name)]));
      tip.appendChild(el('div', { text: (st.acronym ? st.acronym + ' — ' : '') + (st.name || '') }));
      if (lam && lam.how) tip.appendChild(el('small', { text: lam.how }));
      tip.appendChild(el('small', { text: 'CCF ' + p.map((x) => Math.round(x)).join(', ') + ' µm · ' + apText(p[0]) + ' (approx.)' }));
      const r = top.getBoundingClientRect();
      tip.style.display = 'block';
      tip.style.left = Math.min(r.width - 290, e.clientX - r.left + 14) + 'px';
      tip.style.top = Math.min(r.height - 90, e.clientY - r.top + 14) + 'px';
    });
    const end = (e) => {
      if (drag && drag.probe) { drag = null; S.sel = { type: 'probe' }; renderSide(); return; }
      if (drag && !drag.moved) {
        const m = toUm(e);
        const p = planeToCcf(S.slice.plane, S.slice.pos, m.u, m.v);
        const s = sampleAt(p[0], p[1], p[2]);
        const lam = s.lam ? S.blobs['hip20.shb.gz'].header.lamina.find((l) => l.code === s.lam) : null;
        if (lam) select({ type: 'lamina', key: lam.key });
        else if (s.allen) { const st = S.blobs['brain50.shb.gz'].header.structures[s.allen]; select({ type: 'allen', key: st.acronym, name: st.name }); }
      }
      drag = null;
    };
    top.addEventListener('pointerup', end);
    top.addEventListener('pointerleave', () => { tip.style.display = 'none'; });
  }

  /* ==================================================================
     Selection + the side panel
     ================================================================== */
  function select(sel) {
    S.sel = sel;
    if (S.side !== 'inspect') S.side = 'inspect';
    if (!S.trace.key) {
      S.focus = sel ? focusFor(sel) : null;
      applyFocusAll();
    }
    renderSide();
  }
  function focusFor(sel) {
    const f = { cells: new Set(), regionKeys: new Set(), conns: new Set(), layers: new Set() };
    if (sel.type === 'cell') {
      f.cells.add(sel.key);
      S.kb.connections.forEach((c) => { if (c.from === sel.key || c.to === sel.key) f.conns.add(c.key); });
    } else if (sel.type === 'region') {
      f.regionKeys.add(sel.key);
      (regionOf(sel.key).cells || []).forEach((k) => f.cells.add(k));
    } else if (sel.type === 'conn') {
      addConn(f, connOf(sel.key));
    } else if (sel.type === 'lamina') {
      f.layers.add(sel.key);
    }
    return f;
  }
  function addConn(f, c) {
    if (!c) return;
    f.conns.add(c.key);
    [c.from, c.to].forEach((k) => { if (cellOf(k)) { f.cells.add(k); f.regionKeys.add(cellOf(k).region); } else f.regionKeys.add(k); });
    (c.layer || []).forEach((l) => f.layers.add(l));
  }
  function applyFocusAll() {
    applyFocusSchematic();
    applyFocus3d();
    if (S.mode === 'slice') drawSlice();
  }

  function renderSide() {
    const side = $('.sh-side');
    side.innerHTML = '';
    if (S.side === 'checks') return renderChecks(side);
    const sel = S.sel;
    if (!sel) return renderAbout(side);
    if (sel.type === 'cell') return renderCell(side, cellOf(sel.key));
    if (sel.type === 'region') return renderRegion(side, regionOf(sel.key));
    if (sel.type === 'conn') return renderConn(side, connOf(sel.key));
    if (sel.type === 'lamina') return renderLamina(side, sel.key);
    if (sel.type === 'probe') return renderProbe(side);
    if (sel.type === 'allen') {
      side.appendChild(el('div', { class: 'sh-kicker', text: 'Allen CCFv3 structure' }));
      side.appendChild(el('h2', { text: sel.name || sel.key }));
      side.appendChild(el('p', { text: sel.key + ' in the Allen Mouse Brain Common Coordinate Framework (2017 annotation). Seahorse adds detail only inside the hippocampal formation; elsewhere it shows the Allen atlas as it is.' }));
      return;
    }
  }
  function refsList(keys) {
    return el('ol', { class: 'sh-refs' }, (keys || []).map((k) => el('li', { text: S.kb.refs[k] || k })));
  }
  function connRow(c) {
    const v = verdictOf(c.key);
    const name = (k) => (cellOf(k) || regionOf(k) || { label: k }).label;
    return el('div', { class: 'sh-check', onclick: () => select({ type: 'conn', key: c.key }), style: 'cursor:pointer' }, [
      el('div', {}, [el('b', { text: c.label }), document.createTextNode(' · ' + name(c.from) + ' → ' + name(c.to))]),
      el('div', {}, [verdictChip(v)]),
    ]);
  }
  function renderAbout(side) {
    const kb = S.kb;
    side.appendChild(el('div', { class: 'sh-kicker', text: 'Mouse brain atlas' }));
    side.appendChild(el('h2', {}, [el('span', { html: SEAHORSE_SVG, style: 'width:26px;height:26px;display:inline-flex;color:var(--accent)' }), el('span', { text: 'Seahorse' })]));
    side.appendChild(el('p', { text: 'The mouse brain from the Allen atlas, and the hippocampus down to its layers and the cells we record. Click anything, in any view, to read about it. Pick a pathway below to trace it hop by hop, or play a dentate spike.' }));
    const t = tally();
    side.appendChild(el('h3', { text: 'What was checked' }));
    side.appendChild(el('div', { class: 'sh-tally' }, Object.entries(t).map(([k, n]) => el('span', {}, [verdictChip({ status: k }), document.createTextNode(' ' + n)]))));
    side.appendChild(el('button', { class: 'mini', text: 'Open the checks', onclick: () => { S.side = 'checks'; renderSide(); } }));
    side.appendChild(el('h3', { text: 'Cells' }));
    side.appendChild(el('div', { class: 'sh-links' }, kb.cells.map((c) => el('button', { class: 'pill', onclick: () => select({ type: 'cell', key: c.key }) },
      [el('span', { class: 'sh-sw', style: 'display:inline-block;margin-right:6px;background:' + c.color }), document.createTextNode(c.short)]))));
    side.appendChild(el('h3', { text: 'Sources' }));
    side.appendChild(el('p', { text: 'Anatomy: Allen Mouse Brain CCFv3 (Wang et al. 2020), 2017 annotation, with Allen ARA Nissl. Connectivity tests: Allen Mouse Connectivity Atlas (Oh et al. 2014). Cells: NeuroMorpho.Org (Ascoli et al. 2007), each with its own archive and paper. All built on this computer by tools/seahorse; nothing is fetched while you use the tab.' }));
  }
  function tally() {
    const t = {};
    Object.values(S.checks ? S.checks.connections : {}).forEach((v) => { t[v.status] = (t[v.status] || 0) + 1; });
    return t;
  }
  function renderCell(side, c) {
    const cs = (S.checks && S.checks.cells[c.key]) || {};
    const blob = S.blobs['cells.shb.gz'];
    const src = blob ? (blob.header.cells.find((x) => x.key === c.key) || {}).source : null;
    side.appendChild(el('div', { class: 'sh-kicker', text: (regionOf(c.region) || {}).label + ' · ' + (c.sign === 'inh' ? 'inhibitory' : 'excitatory') }));
    side.appendChild(el('h2', {}, [el('span', { class: 'sh-sw', style: 'width:14px;height:14px;background:' + c.color }), el('span', { text: c.label })]));
    side.appendChild(el('p', { text: c.about }));
    side.appendChild(el('dl', {}, [
      el('dt', { text: 'Soma' }), el('dd', { text: c.soma }),
      el('dt', { text: 'Dendrites' }), el('dd', { text: c.dend }),
      el('dt', { text: 'Axon' }), el('dd', { text: c.axon }),
      c.markers ? el('dt', { text: 'Markers' }) : null, c.markers ? el('dd', { text: c.markers }) : null,
    ]));
    side.appendChild(el('h3', { text: 'The cell you see' }));
    const box = el('div', { class: 'sh-src' });
    if (cs.kind === 'drawn' || (src && src.kind === 'drawn')) {
      box.appendChild(el('div', {}, [verdictChip({ status: 'untested' }), document.createTextNode(' Drawn, not traced')]));
      box.appendChild(el('div', { text: (src && src.note) || 'No public tracing exists; drawn from its published description.' }));
    } else if (src) {
      box.appendChild(el('div', {}, [el('b', { text: src.neuron_name }), document.createTextNode(' · ' + src.archive + ' archive · ' + src.species)]));
      box.appendChild(el('div', { text: src.kind === 'ccf'
        ? 'Traced in the whole brain and registered to CCFv3 by its authors: it sits where it really was.'
        : 'Traced in a slice; placed here by fitting its arbors to the layers this cell type uses (fit ' + ((src.fit || {}).score || '?') + ' of 1.1).' }));
      box.appendChild(el('div', { text: [src.domain, src.integrity, (src.condition || []).join(', '), src.protocol].filter(Boolean).join(' · ') }));
      const links = el('div', { class: 'sh-links' });
      links.appendChild(el('a', { href: src.url, target: '_blank', rel: 'noopener', text: 'NeuroMorpho record' }));
      (src.doi || []).forEach((d) => links.appendChild(el('a', { href: 'https://doi.org/' + d, target: '_blank', rel: 'noopener', text: 'doi:' + d })));
      box.appendChild(links);
    } else {
      box.appendChild(el('div', { text: 'Open the 3D slab or the slice view to load the tracing.' }));
    }
    (cs.notes || []).forEach((n) => box.appendChild(el('div', { text: n })));
    side.appendChild(box);
    const conns = S.kb.connections.filter((x) => x.from === c.key || x.to === c.key);
    if (conns.length) { side.appendChild(el('h3', { text: 'Connections' })); conns.forEach((x) => side.appendChild(connRow(x))); }
    side.appendChild(el('div', { class: 'sh-links' }, [
      el('button', { class: 'mini', text: 'See it in the slab', onclick: async () => { await setMode('threed'); await setLevel('slab'); select({ type: 'cell', key: c.key }); } }),
      el('button', { class: 'mini', text: 'See it on the section', onclick: async () => {
        S.slice.plane = 'coronal'; const so = cs.soma_um || (src && src.soma_um) || null;
        await setMode('slice'); if (!S.blobs['cells.shb.gz']) await need(['cells.shb.gz'], 'Bringing in the cells', '');
        const cc = S.blobs['cells.shb.gz'].header.cells.find((x) => x.key === c.key);
        if (cc) { S.slice.pos = Math.round(cc.soma_um[0] / 10) * 10; S.slice.view = { cu: cc.soma_um[2], cv: cc.soma_um[1], umPerPx: 3 }; }
        S.slice.cells = true; renderBar(); drawSlice(); } }),
    ]));
    side.appendChild(el('h3', { text: 'References' }));
    side.appendChild(refsList(c.refs));
  }
  function renderRegion(side, r) {
    side.appendChild(el('div', { class: 'sh-kicker', text: 'Region' }));
    side.appendChild(el('h2', { text: r.label }));
    side.appendChild(el('p', { text: r.sub }));
    side.appendChild(el('dl', {}, [el('dt', { text: 'Allen' }), el('dd', { text: r.allen.join(', ') })]));
    if ((r.cells || []).length) {
      side.appendChild(el('h3', { text: 'Cells here' }));
      side.appendChild(el('div', { class: 'sh-links' }, r.cells.map((k) => el('button', { class: 'pill', text: cellOf(k).label, onclick: () => select({ type: 'cell', key: k }) }))));
    }
    const conns = S.kb.connections.filter((c) => !c.hidden && [c.from, c.to].some((k) => k === r.key || (cellOf(k) && cellOf(k).region === r.key)));
    if (conns.length) { side.appendChild(el('h3', { text: 'In and out' })); conns.forEach((x) => side.appendChild(connRow(x))); }
  }
  function renderConn(side, c) {
    const v = verdictOf(c.key);
    const name = (k) => (cellOf(k) || regionOf(k) || { label: k }).label;
    side.appendChild(el('div', { class: 'sh-kicker', text: (c.sign === 'inh' ? 'Inhibitory' : 'Excitatory') + ' connection' }));
    side.appendChild(el('h2', { text: c.label }));
    side.appendChild(el('p', { text: name(c.from) + ' → ' + name(c.to) + (c.layer ? ', ending in ' + c.layer.map((k) => (lamOf(k) || { label: k }).label).join(', ') : '') }));
    if (c.about) side.appendChild(el('p', { text: c.about }));
    side.appendChild(el('h3', { text: 'Checked against data' }));
    const box = el('div', { class: 'sh-src' }, [el('div', {}, [verdictChip(v)]), el('div', { text: v.detail || '' })]);
    if (v.top && v.top.length) box.appendChild(el('div', { text: 'Strongest: ' + v.top.slice(0, 3).map((x) => 'exp. ' + x.id + ' (' + x.line + ') ' + x.density).join('; ') }));
    side.appendChild(box);
    side.appendChild(el('h3', { text: 'References' }));
    side.appendChild(refsList(c.refs));
  }
  function renderLamina(side, key) {
    const l = lamOf(key) || { label: key, name: '', how: '' };
    const n = S.checks && S.checks.nissl_means ? S.checks.nissl_means[key] : null;
    side.appendChild(el('div', { class: 'sh-kicker', text: 'Layer' }));
    side.appendChild(el('h2', {}, [el('span', { class: 'sh-sw sq', style: 'width:14px;height:14px;background:' + (S.kb.lamina_colors[key] || '#888') }), el('span', { text: l.label })]));
    side.appendChild(el('p', { text: l.name }));
    side.appendChild(el('dl', {}, [el('dt', { text: 'Made by' }), el('dd', { text: l.how || 'Allen annotation' }),
      n != null ? el('dt', { text: 'Nissl' }) : null, n != null ? el('dd', { text: 'mean ' + n + ' of 255' }) : null]));
    const lc = (S.checks && S.checks.lamina || []).find((x) => x.layer === key);
    if (lc) side.appendChild(el('div', { class: 'sh-src' }, [verdictChip({ status: lc.ok ? 'supported' : 'not seen' }), el('div', { text: lc.detail })]));
    const ending = S.kb.connections.filter((c) => (c.layer || []).includes(key));
    if (ending.length) { side.appendChild(el('h3', { text: 'Inputs that end here' })); ending.forEach((x) => side.appendChild(connRow(x))); }
    const cellsHere = S.checks ? Object.entries(S.checks.cells).filter(([k, v]) => v.soma === key).map(([k]) => k) : [];
    if (cellsHere.length) {
      side.appendChild(el('h3', { text: 'Somata here' }));
      side.appendChild(el('div', { class: 'sh-links' }, cellsHere.map((k) => el('button', { class: 'pill', text: cellOf(k).label, onclick: () => select({ type: 'cell', key: k }) }))));
    }
  }
  function renderProbe(side) {
    const pr = S.probe;
    side.appendChild(el('div', { class: 'sh-kicker', text: 'Probe placement · no recording attached' }));
    side.appendChild(el('h2', { text: 'Linear probe, ' + pr.contacts + ' contacts' }));
    side.appendChild(el('p', { text: 'Tip at CCF ' + [pr.ap, pr.dv, pr.ml].join(', ') + ' µm · ' + apText(pr.ap) + ', ML ' + ((pr.ml - 5700) / 1000).toFixed(2) + ' mm, '
      + ((pr.dv - surfaceDv(pr.ap, pr.ml)) / 1000).toFixed(2) + ' mm below the brain surface (approximate: the CCF is an average brain, not stereotaxic). Contacts every ' + pr.pitch + ' µm; contact 1 is nearest the tip.' }));
    side.appendChild(el('h3', { text: 'Which contacts sit in which layer' }));
    side.appendChild(el('div', { class: 'sh-probe-table' }, probeRuns().map((r) => el('div', {}, [
      el('span', { class: 'ch', text: r.from === r.to ? 'ch ' + r.from : 'ch ' + r.from + '–' + r.to }),
      r.key ? el('span', { class: 'sh-sw sq', style: 'background:' + (S.kb.lamina_colors[r.key] || '#888') }) : el('span', { class: 'sh-sw sq', style: 'background:var(--line)' }),
      el('span', { text: r.name + (r.full ? ' — ' + r.full : '') }),
    ]))));
    side.appendChild(el('p', { text: 'Drag the ring at the tip on a coronal section to move it. Layers inside the hippocampus are Seahorse’s derived laminae; elsewhere, Allen structures.' }));
  }
  function renderChecks(side) {
    const ck = S.checks;
    side.appendChild(el('div', { class: 'sh-kicker', text: 'Auto cross-check · run ' + (ck ? ck.ran : '?') }));
    side.appendChild(el('h2', { text: 'Checks' }));
    side.appendChild(el('p', { text: 'Every connection was tested where public data can test it: Allen connectivity experiments for region-to-region claims, real tracings for cell-level ones, the Allen Nissl for the derived layers. The rest are cited, not tested.' }));
    side.appendChild(el('div', { class: 'sh-tally' }, Object.entries(tally()).map(([k, n]) => el('span', {}, [verdictChip({ status: k }), document.createTextNode(' ' + n)]))));
    const order = { 'not seen': 0, error: 0, weak: 1, consistent: 2, supported: 3, untested: 4, cited: 5 };
    const rows = S.kb.connections.slice().sort((a, b) => (order[verdictOf(a.key).status] ?? 9) - (order[verdictOf(b.key).status] ?? 9));
    side.appendChild(el('h3', { text: 'Connections' }));
    rows.forEach((c) => {
      const v = verdictOf(c.key);
      side.appendChild(el('div', { class: 'sh-check', style: 'cursor:pointer', onclick: () => select({ type: 'conn', key: c.key }) },
        [el('div', {}, [el('b', { text: c.label + ' ' }), verdictChip(v)]), el('div', { text: v.detail })]));
    });
    side.appendChild(el('h3', { text: 'Derived layers vs Nissl' }));
    (ck.lamina || []).forEach((l) => side.appendChild(el('div', { class: 'sh-check' }, [el('div', {}, [el('b', { text: (lamOf(l.layer) || { label: l.layer }).label + ' ' }), verdictChip({ status: l.ok ? 'supported' : 'not seen' })]), el('div', { text: l.detail })])));
    side.appendChild(el('h3', { text: 'Where each cell landed' }));
    Object.entries(ck.cells || {}).forEach(([k, v]) => side.appendChild(el('div', { class: 'sh-check', style: 'cursor:pointer', onclick: () => select({ type: 'cell', key: k }) },
      [el('div', {}, [el('b', { text: (cellOf(k) || { label: k }).label + ' ' }), verdictChip({ status: v.kind === 'drawn' ? 'untested' : v.soma_ok ? (v.identity === 'unconfirmed' ? 'weak' : 'supported') : 'not seen' })]),
        el('div', { text: (v.notes || []).join(' ') || ('Soma in ' + v.soma + '.') })])));
    side.appendChild(el('h3', { text: 'What the checks found' }));
    (ck.findings || []).forEach((f) => side.appendChild(el('div', { class: 'sh-check', text: f.text })));
    side.appendChild(el('h3', { text: 'Method' }));
    side.appendChild(el('p', { text: 'Allen: every experiment with its primary injection in the source; median projection density in the target against cerebellum (which none of these project to). Supported at median ≥ 0.002 and ≥ 5× control; weak when a quarter or more of the experiments reach 0.002. Tracings: the share of the exemplar’s arbor in the named layers; this is evidence only for cells registered to the atlas by their authors.' }));
  }

  /* ==================================================================
     The tracer
     ================================================================== */
  function renderTrace() {
    const t = $('.sh-trace');
    t.innerHTML = '';
    const kb = S.kb;
    const row = el('div', { class: 'sh-trace-row' }, [el('span', { class: 'sh-kicker', text: 'Trace a pathway' })]);
    kb.pathways.forEach((p) => row.appendChild(el('button', { class: 'pill' + (S.trace.key === p.key ? ' active' : ''), text: p.label, title: p.blurb,
      'aria-pressed': String(S.trace.key === p.key), onclick: () => startTrace(p.key) })));
    row.appendChild(el('span', { class: 'sh-kicker', text: 'Play', style: 'margin-left:12px' }));
    kb.ds.forEach((d) => row.appendChild(el('button', { class: 'pill sh-ds' + (S.trace.key === d.key ? ' active' : ''), text: d.label, title: d.say,
      'aria-pressed': String(S.trace.key === d.key), onclick: () => playDs(d.key) })));
    t.appendChild(row);
    const p = kb.pathways.find((x) => x.key === S.trace.key);
    const d = kb.ds.find((x) => x.key === S.trace.key);
    if (p) {
      const hop = p.hops[S.trace.i] || null;
      t.appendChild(el('div', { class: 'sh-caption' }, [
        el('span', { class: 'sh-step', text: (S.trace.i + 1) + ' / ' + p.hops.length }),
        el('div', { class: 'sh-dots' }, p.hops.map((h, i) => el('i', { class: i < S.trace.i ? 'done' : i === S.trace.i ? 'now' : '' }))),
        el('span', { class: 'sh-say', text: hop ? hop.say : p.blurb }),
        el('button', { class: 'btn ghost sm', text: 'Back', disabled: S.trace.i <= 0, onclick: () => stepTrace(-1) }),
        el('button', { class: 'btn ghost sm', text: S.trace.timer ? 'Pause' : 'Play through', onclick: togglePlay }),
        el('button', { class: 'btn sm', text: S.trace.i >= p.hops.length - 1 ? 'Done' : 'Next', onclick: () => (S.trace.i >= p.hops.length - 1 ? stopTrace() : stepTrace(1)) }),
      ]));
    } else if (d) {
      t.appendChild(el('div', { class: 'sh-caption' }, [
        el('span', { class: 'sh-step', text: d.label }),
        el('span', { class: 'sh-say', text: d.say }),
        el('button', { class: 'btn ghost sm', text: 'Again', onclick: () => playDs(d.key, true) }),
        el('button', { class: 'btn sm', text: 'Done', onclick: stopTrace }),
      ]));
    }
  }
  function startTrace(key) {
    if (S.trace.key === key) { stopTrace(); return; }
    clearInterval(S.trace.timer);
    S.trace = { key, i: 0, timer: 0, ds: null };
    showHop();
  }
  function stepTrace(d) {
    const p = S.kb.pathways.find((x) => x.key === S.trace.key);
    if (!p) return;
    S.trace.i = Math.max(0, Math.min(p.hops.length - 1, S.trace.i + d));
    showHop();
  }
  function togglePlay() {
    if (S.trace.timer) { clearInterval(S.trace.timer); S.trace.timer = 0; renderTrace(); return; }
    const p = S.kb.pathways.find((x) => x.key === S.trace.key);
    S.trace.timer = setInterval(() => {
      if (S.trace.i >= p.hops.length - 1) { clearInterval(S.trace.timer); S.trace.timer = 0; renderTrace(); return; }
      stepTrace(1);
    }, 3600);
    renderTrace();
  }
  function stopTrace() {
    clearInterval(S.trace.timer);
    S.trace = { key: null, i: -1, timer: 0, ds: null };
    S.focus = S.sel ? focusFor(S.sel) : null;
    renderTrace();
    applyFocusAll();
  }
  function showHop() {
    const p = S.kb.pathways.find((x) => x.key === S.trace.key);
    const hop = p.hops[S.trace.i];
    const f = { cells: new Set(), regionKeys: new Set(), conns: new Set(), layers: new Set() };
    if (hop.via) addConn(f, connOf(hop.via));
    if (hop.at) { if (cellOf(hop.at)) { f.cells.add(hop.at); f.regionKeys.add(cellOf(hop.at).region); } else f.regionKeys.add(hop.at); }
    S.focus = f;
    renderTrace();
    applyFocusAll();
    animateHop(hop);
    if (hop.via) { S.sel = { type: 'conn', key: hop.via }; renderSide(); }
    else if (hop.at) { S.sel = cellOf(hop.at) ? { type: 'cell', key: hop.at } : { type: 'region', key: hop.at }; renderSide(); }
  }
  function centroidOfEnd(key) {
    const st = S.stage3;
    if (!st) return null;
    if (cellOf(key) && st.has('cells')) return st.centroid('cells', key);
    const r = regionOf(key) || regionOf((cellOf(key) || {}).region);
    if (!r) return null;
    for (const a of r.allen) {
      const c = st.centroid('hpf', a, true) || st.centroid('brain', a, true);
      if (c) return c;
    }
    return null;
  }
  function animateHop(hop) {
    if (!S.stage3 || S.mode !== 'threed') return;
    const c = hop.via ? connOf(hop.via) : null;
    if (c) {
      if (cellOf(c.from) && S.stage3.has('cells') && S.level === 'slab') S.stage3.pulseCell(c.from);
      else {
        const a = centroidOfEnd(c.from), b = centroidOfEnd(c.to);
        if (a && b) S.stage3.volley(a, b, c.sign === 'inh' ? tok('--err', '#e44') : tok('--accent', '#e5a823'));
      }
    } else if (hop.at && cellOf(hop.at) && S.stage3.has('cells')) S.stage3.pulseCell(hop.at);
  }
  async function playDs(key, again) {
    if (S.trace.key === key && !again) { stopTrace(); return; }
    clearInterval(S.trace.timer);
    const d = S.kb.ds.find((x) => x.key === key);
    S.trace = { key, i: 0, timer: 0, ds: d };
    const f = { cells: new Set([d.from, 'gc', 'hipp', 'pvbc']), regionKeys: new Set(['dg', (cellOf(d.from) || {}).region]), conns: new Set([d.path]), layers: new Set(d.sink.concat(d.source)) };
    S.focus = f;
    S.sel = { type: 'conn', key: d.path };
    renderTrace();
    renderSide();
    applyFocusAll();
    if (S.mode === 'threed' && S.stage3) {
      const a = centroidOfEnd(d.from), b = centroidOfEnd('dg');
      if (a && b) S.stage3.volley(a, b, tok('--err', '#e44'), 1600);
      if (S.stage3.has('cells')) setTimeout(() => ['hipp', 'pvbc'].forEach((k) => S.stage3.pulseCell(k, 1800)), 1500);
    }
  }

  /* ==================================================================
     Figures
     ================================================================== */
  function download(url, name) {
    const a = el('a', { href: url, download: name });
    document.body.appendChild(a); a.click(); a.remove();
  }
  function saveFigure() {
    const stamp = new Date().toISOString().slice(0, 10);
    if (S.mode === 'threed' && S.stage3) {
      download(S.stage3.snapshot(3, true), 'seahorse-3d-' + S.level + '-' + stamp + '.png');
      toast('Saved a 3× PNG with a transparent background.', 'ok');
    } else if (S.mode === 'slice' && S.slice.view) {
      const base = $('.sh-slice-wrap canvas.base');
      const g = sliceGeom(base);
      const out = document.createElement('canvas');
      out.width = g.W * 2; out.height = g.H * 2;
      paintSection(out, S.slice.plane, S.slice.pos, g.u0, g.k / 2, g.v0, g.k / 2, S.slice.layer, false);
      const ctx = out.getContext('2d');
      const wrap = $('.sh-slice-wrap');
      wrap.querySelectorAll('canvas.hl, canvas.top').forEach((c) => ctx.drawImage(c, 0, 0, out.width, out.height));
      download(out.toDataURL('image/png'), 'seahorse-' + S.slice.plane + '-' + Math.round(S.slice.pos) + 'um-' + stamp + '.png');
      toast('Saved the section at twice the screen resolution.', 'ok');
    } else {
      const s = $('[data-pane="schematic"] svg');
      if (!s) return;
      const clone = s.cloneNode(true);
      const all = s.querySelectorAll('*'), call = clone.querySelectorAll('*');
      all.forEach((n, i) => {
        const cs = getComputedStyle(n);
        ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'opacity', 'font-size', 'font-weight', 'font-style', 'font-family'].forEach((p) => call[i].style.setProperty(p, cs.getPropertyValue(p)));
      });
      clone.setAttribute('xmlns', SVGNS);
      clone.querySelectorAll('.flow').forEach((n) => n.remove());
      const blob = new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml' });
      const url = URL.createObjectURL(blob);
      download(url, 'seahorse-' + S.schem + '-' + stamp + '.svg');
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      toast('Saved the schematic as SVG, with the theme’s colors written in.', 'ok');
    }
  }

  function themeChanged() {
    S._lut = null;
    if (S.mode === 'slice') drawSlice();
    if (S.stage3) S.stage3.theme(colorsFor3d());
  }

  /* ==================================================================
     The view's life
     ================================================================== */
  async function onShow() {
    if (!S.built) build();
    if (!S.kb) {
      try {
        const [kb, checks, manifest] = await Promise.all([getJSON('kb.json'), getJSON('checks.json'), getJSON('manifest.json').catch(() => null)]);
        S.kb = kb; S.checks = checks; S.manifest = manifest;
      } catch (err) {
        $('.sh-stage').appendChild(el('div', { class: 'empty-state', style: 'padding:40px', text: 'Seahorse’s atlas files are missing (web/seahorse/). Build them with: python tools/seahorse/build.py' }));
        reportClientError('seahorse:kb', err.message, err.stack);
        return;
      }
    }
    renderSide();
    renderTrace();
    await setMode(S.mode);
  }
  function onHide() {
    if (S.stage3) S.stage3.pause();
    if (S.trace.timer) { clearInterval(S.trace.timer); S.trace.timer = 0; }
  }
  function onReturn() {
    if (S.mode === 'threed' && S.stage3) S.stage3.resume();
    if (S.mode === 'slice') drawSlice();
  }

  return { onShow, onHide, onReturn, _state: S };
})();
