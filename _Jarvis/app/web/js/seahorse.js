/* ==========================================================================
   seahorse.js -- Seahorse: the mouse brain, down to the cells we record.

   One stage on the left (3D or Slice, both drawn by seahorse3d.js on one
   WebGL canvas, or the Schematic full size), a rail on the right with the
   schematic that follows you (circuit, dentate by layer, or one cell's
   wiring) over the card for whatever is selected, and a step bar along the
   bottom for rides, events and tours.

     Hover   anything, anywhere: a label says what it is, what happens
             there and how we know; the same thing glows in every view.
     Click   selects it everywhere; a cell's card can light where it leads
             and what feeds it, one hop at a time.
     Rides   a signal followed along real, touching tracings (rides.json,
             built by tools/seahorse/rides.py), the camera behind it, the
             schematic lighting each connection as it is crossed.
     Events  DS1, DS2, sharp-wave ripples, theta and P-spikes as MODEL
             laminar profiles on the probe's 64 contacts (seahorse_phys.js).
     Tours, the quiz and search: seahorse_learn.js. Schematics:
             seahorse_schem.js. Lab notes, saved views and quiz progress
             are shared through GUI_logs/seahorse (backend/seahorse.py).

   Data: web/seahorse/*, built offline by tools/seahorse/. Nothing is
   fetched from the internet while the tab is open.
   ========================================================================== */
'use strict';

BARRY.views.seahorse = (function () {
  const BASE = 'seahorse/';
  const S = {
    built: false, kb: null, checks: null, manifest: null, rides: null, blobs: {},
    mode: '3d', level: 'hpf', schemPick: 'auto', schemShown: null, follow: true,
    sel: null, hover: null, focus: null, here: null, trail: [], reach: null,
    slice: { plane: 'coronal', pos: 7300, tiltA: 0, tiltB: 0, C: null, k: 0, layer: 'lamina', cells: true, mini: true },
    probe: { on: false, ap: -1.9, ml: 1.4, depth: 2.3, angML: 0, angAP: 0, contacts: 64, pitch: 20, first: 40, tip: null, dir: null },
    cut: { kind: 'coronal', pos: 8490 }, story: true, exploded: false, crowd: true,
    play: null, stage: null, three: null, loading: null, volumesUp: false, crowdMade: false,
    lab: { notes: {}, views: {}, me: '' }, quiz: null, rec: null, railW: null, railSplit: 0.52,
  };
  let root = null;
  const $ = (sel, r) => (r || root).querySelector(sel);
  const $$ = (sel, r) => Array.from((r || root).querySelectorAll(sel));

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
  const reducedMotion = () => !!(BARRY.ui && BARRY.ui.reducedMotion && BARRY.ui.reducedMotion());
  const cellOf = (k) => S.kb && S.kb.cells.find((c) => c.key === k);
  const regionOf = (k) => S.kb && S.kb.regions.find((r) => r.key === k);
  const connOf = (k) => S.kb && S.kb.connections.find((c) => c.key === k);
  const lamOf = (k) => S.kb && S.kb.lamina.find((l) => l.key === k);
  const lamByCode = (code) => S.kb && S.kb.lamina.find((l) => l.code === code);
  const verdictOf = (key) => (S.checks && S.checks.connections[key]) || { status: 'cited', detail: '' };
  const instances = () => (S.blobs['cells.shb.gz'] ? S.blobs['cells.shb.gz'].header.cells : []);
  const instOf = (key) => instances().find((c) => c.key === key);
  const instancesOfType = (type) => instances().filter((c) => (c.type || c.key) === type).map((c) => c.key);
  const typeOfInst = (key) => { const i = instOf(key); return i ? (i.type || i.key) : key; };
  function regionOfLayer(k) {
    if (!k) return null;
    if (/^(oml|mml|iml|gcl)/.test(k) || k === 'hil') return 'dg';
    if (k.startsWith('ca1')) return 'ca1';
    if (k.startsWith('ca2')) return 'ca2';
    if (k.startsWith('ca3')) return 'ca3';
    if (k === 'sub' || k === 'pros') return 'sub';
    return null;
  }
  function refText(k) { return (S.kb && S.kb.refs[k]) || (S.rides && S.rides.refs[k]) || k; }
  /* "Wong RKS, Traub RD (1983) ..." -> "Wong & Traub 1983"; three or more
     authors -> "Amaral et al. 2007". */
  function refShort(k) {
    const t = refText(k);
    const m = t.match(/^(.*?)\s*\((\d{4})\)/);
    if (!m) return k;
    const who = m[1].replace(/\s+et al\.?$/, ', X');
    const authors = who.split(/,\s*/).filter(Boolean);
    const sur = (a) => a.trim().split(/\s+/)[0];
    if (authors.length === 1) return sur(authors[0]) + ' ' + m[2];
    if (authors.length === 2 && !/et al/.test(m[1])) return sur(authors[0]) + ' & ' + sur(authors[1]) + ' ' + m[2];
    return sur(authors[0]) + ' et al. ' + m[2];
  }
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
  /* a named two-or-more-state switch (pressed = what is showing) */
  function seg(label, opts, cur, on) {
    const g = el('div', { class: 'seg', role: 'group', 'aria-label': label },
      opts.map(([k, t, tip]) => el('button', { class: cur === k ? 'active' : '', text: t, title: tip || '', 'aria-pressed': String(cur === k),
        onclick: () => { if (cur !== k) on(k); } })));
    return label ? el('span', { class: 'sh-segwrap' }, [el('span', { class: 'sh-kicker', text: label }), g]) : g;
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
  const apMm = (ap) => (5400 - ap) / 1000;
  const apText = (ap) => 'AP ' + apMm(ap).toFixed(2) + ' mm';

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
    if (!(u8[0] === 0x1f && u8[1] === 0x8b)) return u8;
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
  /* The fine Nissl travels as one JPEG sheet of coronal tiles; turn it back
     into a volume, a row of tiles at a time. */
  async function decodeFine(blob) {
    const h = blob.header, J = h.nissl_jpeg;
    const bmp = await createImageBitmap(new Blob([blob.arrays.nissl_jpeg], { type: 'image/jpeg' }));
    const [th, tw] = J.tile;
    const vol = new Uint8Array(J.slices * th * tw);
    const cv = document.createElement('canvas');
    cv.width = bmp.width; cv.height = th;
    const ctx = cv.getContext('2d', { willReadFrequently: true });
    for (let r = 0; r < J.rows; r++) {
      ctx.clearRect(0, 0, cv.width, th);
      ctx.drawImage(bmp, 0, r * th, bmp.width, th, 0, 0, bmp.width, th);
      const px = ctx.getImageData(0, 0, cv.width, th).data;
      for (let c = 0; c < J.cols; c++) {
        const i = r * J.cols + c;
        if (i >= J.slices) break;
        for (let y = 0; y < th; y++) {
          const src = (y * cv.width + c * tw) * 4, dst = (i * th + y) * tw;
          for (let x = 0; x < tw; x++) vol[dst + x] = px[src + x * 4];
        }
      }
    }
    bmp.close && bmp.close();
    return vol;
  }

  /* ---------- the loading window ---------- */
  const WHAT = {
    three: ['Waking the renderer', 'three.js, kept on this computer; it draws both the 3D and the sections.'],
    'mesh_brain.shb.gz': ['The whole brain', 'Allen CCFv3 brain surface and its major divisions.'],
    'mesh_hpf.shb.gz': ['The hippocampal formation', 'DG, CA1-3, subiculum, entorhinal, perirhinal and postrhinal cortex.'],
    'mesh_lamina.shb.gz': ['Its layers, at 10 µm', '28 laminar surfaces: OML1 to OML2, the CA strata. Derived where the Allen atlas has none.'],
    'cells.shb.gz': ['The cells', 'Real tracings: whole-brain cells that touch each other, slice cells placed by their layers, one drawn mossy cell.'],
    'rides.json': ['The rides', 'Where each axon meets the next dendrite, with conduction times from the literature.'],
    'brain50.shb.gz': ['Whole-brain sections', '671 Allen structures and Nissl, every 50 µm.'],
    'hip20.shb.gz': ['The hippocampus', 'Laminae and the real Allen Nissl, every 20 µm.'],
    'fine10.shb.gz': ['The dorsal hippocampus at 10 µm', 'Where the probes go: layers and the real 10 µm Allen Nissl.'],
    build: ['Building', 'Sending the volumes to the graphics card and growing the cells.'],
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
    const bar = el('i'), pct = el('span', { class: 'pct', text: '0%' }), said = el('span', { text: 'Starting' });
    const fact = el('div', { class: 'sh-load-fact' });
    const facts = (S.kb ? S.kb.cells : []).map((c) => c.label + ': ' + c.about).concat((S.kb ? S.kb.cells : []).flatMap((c) => (c.phys || []).map((p) => c.label + ': ' + p.text)));
    let fi = Math.floor(Math.random() * Math.max(1, facts.length));
    const showFact = () => { if (facts.length) { fact.textContent = facts[fi % facts.length]; fi++; } };
    showFact();
    const factTimer = setInterval(showFact, 5200);
    const node = el('div', { class: 'sh-load', role: 'status', 'aria-live': 'polite' }, [
      el('div', { class: 'sh-load-card' }, [
        el('div', { class: 'sh-load-head' }, [el('span', { html: SEAHORSE_SVG }), el('div', {}, [el('h2', { text: title }), el('p', { text: sub })])]),
        steps, el('div', { class: 'sh-load-bar' }, [bar]), el('div', { class: 'sh-load-foot' }, [said, pct]), fact,
      ]),
    ]);
    $('.sh-stage').appendChild(node);
    const mark = (n, cls) => { const li = steps.querySelector('[data-n="' + n + '"]'); if (li) li.className = cls; };
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
      building(what) { mark('build', 'now'); said.textContent = what || 'Building…'; bar.style.width = '98%'; pct.textContent = '98%'; },
      close() { clearInterval(factTimer); bar.style.width = '100%'; pct.textContent = '100%'; mark('build', 'done'); setTimeout(() => node.remove(), 220); },
      fail(msg) { clearInterval(factTimer); said.textContent = msg; said.style.color = tok('--err', 'red'); },
    };
  }
  /* Load what is not here yet, behind the window; then build what needs it. */
  async function need(names, title, sub) {
    const want = names.filter((n) => n === 'three' ? !S.three : n === 'rides.json' ? !S.rides : !S.blobs[n]);
    if (!want.length) return true;
    if (S.loading) { await S.loading; return need(names, title, sub); }
    let release;
    S.loading = new Promise((r) => { release = r; });
    const win = loadingWindow(title, sub, want);
    try {
      for (const n of want) {
        win.start(n);
        if (n === 'three') {
          S.three = await import('./seahorse3d.js?v=2');
          win.bytes(n, 700000, 700000);
        } else if (n === 'rides.json') {
          S.rides = await getJSON('rides.json');
        } else {
          const raw = await fetchBytes(n, (g, t) => win.bytes(n, g, t));
          S.blobs[n] = unpack(await gunzip(raw));
          if (n === 'fine10.shb.gz') { win.building('Unpacking the 10 µm Nissl…'); S.blobs[n].nissl = await decodeFine(S.blobs[n]); }
        }
        win.done(n);
      }
      win.building();
      await new Promise((r) => setTimeout(r, 30));
      await afterLoad();
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
  /* Whatever the newly loaded data lets the stage do. */
  async function afterLoad() {
    const st = S.stage;
    if (!st) return;
    if (S.blobs['mesh_brain.shb.gz'] && !st.has('brain')) st.addBrain(S.blobs['mesh_brain.shb.gz']);
    if (S.blobs['mesh_hpf.shb.gz'] && !st.has('hpf')) st.addHpf(S.blobs['mesh_hpf.shb.gz'], (k) => REGION_COLORS[k]);
    if (S.blobs['mesh_lamina.shb.gz'] && !st.has('lamina')) st.addLamina(S.blobs['mesh_lamina.shb.gz'], S.kb.lamina_colors);
    if (S.blobs['cells.shb.gz'] && !st.has('cells')) {
      st.addCells(S.blobs['cells.shb.gz'], (t) => (cellOf(t) || {}).color || '#ccc');
      st.setStory(S.story);
      showExtras();
    }
    if (!S.volumesUp && S.blobs['brain50.shb.gz'] && S.blobs['hip20.shb.gz']) {
      st.setVolumes(volumesForStage());
      st.setLuts(luts());
      S.volumesUp = true;
      applyHighlights();
    }
  }
  /* The second LEC cell (AA1002: 230 mm of axon) only joins in when it has
     something to show: the DS1 volley, or when LEC cells are selected. */
  function showExtras() {
    if (!S.stage || !S.stage.has('cells')) return;
    const want = (S.play && S.play.kind === 'ride' && S.play.key === 'ds1') || (S.sel && S.sel.type === 'cell' && S.sel.key === 'fan');
    S.stage.setVisible('cells', 'fan_b', !!want);
  }
  const REGION_COLORS = { DG: '#2a9d8f', CA1: '#c2185b', CA2: '#e07a55', CA3: '#b8323c', SUB: '#c9a45c', ProS: '#b8934d',
    ENTl: '#d16ba5', ENTm: '#3d7dd8', PRE: '#9c7bd6', POST: '#8a6cc8', PAR: '#7b8fd9', PERI: '#a0a07a', ECT: '#8e8e6e', VISpor: '#6f9fae' };

  /* ---------- volumes, colours and the CPU sampler ---------- */
  function volumesForStage() {
    const B = S.blobs['brain50.shb.gz'], H = S.blobs['hip20.shb.gz'], F = S.blobs['fine10.shb.gz'];
    const x8 = (a, s) => { const o = new Uint8Array(a.length); for (let i = 0; i < a.length; i++) o[i] = Math.min(255, a[i] * (s || 8)); return o; };
    const v = {
      brain: { labels: B.arrays.labels, nissl: x8(B.arrays.nissl, B.header.nissl_scale), dims: B.header.arrays[0].shape },
      hip: { labels: H.arrays.labels, nissl: x8(H.arrays.nissl, H.header.nissl_scale), dims: H.header.arrays[0].shape, origin: H.header.origin_um },
    };
    if (F && F.nissl) v.fine = { labels: F.arrays.labels, nissl: F.nissl, dims: F.header.shape, origin: F.header.origin_um };
    return v;
  }
  function luts() {
    const lam = new Uint8Array(256 * 4);
    for (const l of S.kb.lamina) { const c = hexRgb(S.kb.lamina_colors[l.key] || '#888'); lam.set([c[0], c[1], c[2], 255], l.code * 4); }
    const structs = S.blobs['brain50.shb.gz'].header.structures;
    const allen = new Uint8Array(1024 * 4);
    structs.forEach((s, i) => {
      if (i >= 1024) return;
      const c = hexRgb(s.color);
      allen.set([c[0], c[1], c[2], (s.path || []).includes(1089) ? 255 : 0], i * 4);
    });
    return { lam, allen };
  }
  /* What is at one point (CCF um): the finest label that covers it. */
  function sampleAt(ap, dv, ml) {
    const out = { lam: 0, allen: 0, nissl: 0 };
    const B = S.blobs['brain50.shb.gz'], H = S.blobs['hip20.shb.gz'], F = S.blobs['fine10.shb.gz'];
    if (!B) return out;
    let i = Math.floor(ap / 50), j = Math.floor(dv / 50), k = Math.floor(ml / 50);
    if (i >= 0 && j >= 0 && k >= 0 && i < 264 && j < 160 && k < 228) {
      const n = (i * 160 + j) * 228 + k;
      out.allen = B.arrays.labels[n];
      out.nissl = B.arrays.nissl[n] * 8;
    }
    // the laminae are for the right hemisphere; the annotation is symmetric
    if (ml < 5700) ml = 11400 - ml;
    if (H) {
      const ho = H.header.origin_um, hs = H.header.arrays[0].shape;
      i = Math.floor((ap - ho[0]) / 20); j = Math.floor((dv - ho[1]) / 20); k = Math.floor((ml - ho[2]) / 20);
      if (i >= 0 && j >= 0 && k >= 0 && i < hs[0] && j < hs[1] && k < hs[2]) out.lam = H.arrays.labels[(i * hs[1] + j) * hs[2] + k];
    }
    if (F) {
      const fo = F.header.origin_um, fs = F.header.shape;
      i = Math.floor((ap - fo[0]) / 10); j = Math.floor((dv - fo[1]) / 10); k = Math.floor((ml - fo[2]) / 10);
      if (i >= 0 && j >= 0 && k >= 0 && i < fs[0] && j < fs[1] && k < fs[2]) out.lam = F.arrays.labels[(i * fs[1] + j) * fs[2] + k];
    }
    return out;
  }
  const allenStruct = (idx) => (S.blobs['brain50.shb.gz'] ? S.blobs['brain50.shb.gz'].header.structures[idx] : null) || {};
  function surfaceDvAt(ap, ml) {
    for (let dv = 0; dv < 8000; dv += 25) { if (sampleAt(ap, dv, ml).allen) return dv; }
    return 0;
  }

  /* ==================================================================
     Layout
     ================================================================== */
  function build() {
    root = document.getElementById('view-seahorse');
    const saved = store.get();
    ['mode', 'level', 'schemPick', 'follow', 'story', 'crowd', 'railW', 'railSplit'].forEach((k) => { if (saved[k] != null) S[k] = saved[k]; });
    if (saved.slice) Object.assign(S.slice, saved.slice);
    if (saved.probe) Object.assign(S.probe, saved.probe);
    if (saved.cut) Object.assign(S.cut, saved.cut);
    const head = root.querySelector('.head-actions');
    head.innerHTML = '';
    const search = el('div', { class: 'sh-search' }, [
      el('input', { type: 'search', placeholder: 'Search: MML, mossy cell, DS2, Schaffer…', 'aria-label': 'Search Seahorse', spellcheck: 'false' }),
      el('div', { class: 'sh-search-res', role: 'listbox' }),
    ]);
    head.appendChild(search);
    wireSearch(search);
    head.appendChild(el('button', { class: 'btn ghost sm', text: 'Tours', title: 'Guided tours', onclick: (e) => menuTours(e.currentTarget) }));
    head.appendChild(el('button', { class: 'btn ghost sm', text: 'Quiz', title: 'Quiz cards drawn from the atlas, spaced like Anki', onclick: () => openQuiz() }));
    head.appendChild(el('button', { class: 'btn ghost sm', text: 'Views', title: 'Saved views: yours and your labmates\'', onclick: () => showCard({ type: 'views' }) }));
    head.appendChild(el('button', { class: 'btn ghost sm', text: 'Checks', title: 'What was tested against data, and how it came out', onclick: () => showCard({ type: 'checks' }) }));
    head.appendChild(el('button', { class: 'btn ghost sm', text: 'Save figure', title: 'The current view as an image (3D and slice: PNG; schematic: SVG)', onclick: saveFigure }));
    head.appendChild(el('button', { class: 'btn ghost sm sh-rec-btn', text: 'Record', title: 'Record the stage as a video (MP4 where the browser can, else WebM)', onclick: toggleRecord }));
    const body = root.querySelector('.sh-body');
    body.innerHTML = '';
    body.appendChild(el('div', { class: 'sh-bar' }));
    body.appendChild(el('div', { class: 'sh-stage' }, [
      el('div', { class: 'sh-host' }),
      el('div', { class: 'sh-schem-full' }),
      el('div', { class: 'sh-tip', style: 'display:none' }),
      el('div', { class: 'sh-inset', style: 'display:none' }),
      el('div', { class: 'sh-hud' }),
    ]));
    body.appendChild(el('div', { class: 'sh-vdiv', title: 'Drag to resize', role: 'separator', 'aria-orientation': 'vertical' }));
    body.appendChild(el('aside', { class: 'sh-rail' }, [
      el('div', { class: 'sh-rail-head' }),
      el('div', { class: 'sh-rail-schem' }),
      el('div', { class: 'sh-hdiv', title: 'Drag to resize', role: 'separator', 'aria-orientation': 'horizontal' }),
      el('div', { class: 'sh-card' }),
    ]));
    body.appendChild(el('div', { class: 'sh-steps' }));
    wireDividers(body);
    applyRailSize();
    S.built = true;
    new MutationObserver(() => { if (BARRY.state.view === 'seahorse') themeChanged(); })
      .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'class', 'style'] });
    document.addEventListener('keydown', onKey);
  }
  function wireDividers(body) {
    const v = $('.sh-vdiv'), h = $('.sh-hdiv');
    let drag = null;
    v.addEventListener('pointerdown', (e) => { drag = { kind: 'v', x: e.clientX, w: $('.sh-rail').getBoundingClientRect().width }; v.setPointerCapture(e.pointerId); });
    h.addEventListener('pointerdown', (e) => { const r = $('.sh-rail').getBoundingClientRect(); drag = { kind: 'h', y: e.clientY, top: r.top, hgt: r.height }; h.setPointerCapture(e.pointerId); });
    const move = (e) => {
      if (!drag) return;
      if (drag.kind === 'v') {
        const bw = body.getBoundingClientRect().width;
        S.railW = Math.max(300, Math.min(bw * 0.62, drag.w - (e.clientX - drag.x)));
      } else {
        S.railSplit = Math.max(0.18, Math.min(0.82, (e.clientY - drag.top) / drag.hgt));
      }
      applyRailSize();
    };
    const up = () => { if (drag) { drag = null; store.set({ railW: S.railW, railSplit: S.railSplit }); } };
    [v, h].forEach((n) => { n.addEventListener('pointermove', move); n.addEventListener('pointerup', up); });
  }
  function applyRailSize() {
    const body = $('.sh-body');
    if (!body) return;
    const w = S.railW || Math.max(340, Math.round(body.getBoundingClientRect().width * 0.36));
    body.style.setProperty('--sh-rail-w', w + 'px');
    body.style.setProperty('--sh-split', (S.railSplit * 100).toFixed(1) + '%');
  }

  /* ---------------------------------------------------------------- the bar */
  function renderBar() {
    const bar = $('.sh-bar');
    bar.innerHTML = '';
    bar.appendChild(seg('', [['3d', '3D'], ['slice', 'Slice'], ['schematic', 'Schematic']], S.mode, (k) => setMode(k)));
    if (S.mode === '3d') {
      bar.appendChild(seg('', [['brain', 'Brain'], ['hpf', 'Hippocampus'], ['slab', 'Slab']], S.level, (k) => setLevel(k)));
      if (S.level !== 'brain') {
        bar.appendChild(seg('Cut', [['none', 'None'], ['coronal', 'Coronal'], ['sagittal', 'Sagittal'], ['horizontal', 'Horizontal']],
          S.level === 'slab' ? 'coronal' : S.cut.kind, (k) => { S.cut.kind = k; S.cut.pos = defaultCutPos(k); store.set({ cut: S.cut }); applyCut(); renderBar(); }));
        if (S.cut.kind !== 'none' || S.level === 'slab') {
          const lim = cutLimits(S.level === 'slab' ? 'coronal' : S.cut.kind);
          bar.appendChild(rangeField('', lim[0], lim[1], 10, S.cut.pos, (v) => cutText(S.level === 'slab' ? 'coronal' : S.cut.kind, v),
            (v) => { S.cut.pos = v; store.set({ cut: S.cut }); applyCut(); }));
        }
        bar.appendChild(seg('Layers', [['together', 'Together'], ['exploded', 'Exploded']], S.exploded ? 'exploded' : 'together',
          (k) => { S.exploded = k === 'exploded'; if (S.stage) S.stage.explode(S.exploded ? 1 : 0); renderBar(); }));
        bar.appendChild(seg('Cells', [['story', 'Story', 'Each cell moved by the gap to meet its partner (at most 120 µm)'], ['traced', 'As traced', 'Where each tracing was registered']],
          S.story ? 'story' : 'traced', (k) => { S.story = k === 'story'; store.set({ story: S.story }); if (S.stage) S.stage.setStory(S.story); renderBar();
            toast(S.story ? 'Showing cells positioned for the story: each moved by its gap to touch its partner.' : 'Showing every tracing where it was registered; the synapses open up by their gaps.', 'ok'); }));
        bar.appendChild(seg('Crowd', [['on', 'Shown'], ['off', 'Hidden']], S.crowd ? 'on' : 'off', (k) => { S.crowd = k === 'on'; store.set({ crowd: S.crowd }); ensureCrowd(); if (S.stage) S.stage.showCrowd(S.crowd); renderBar(); }));
      }
    }
    if (S.mode === 'slice') {
      bar.appendChild(seg('', [['coronal', 'Coronal'], ['sagittal', 'Sagittal'], ['horizontal', 'Horizontal']], S.slice.plane, (k) => {
        S.slice.plane = k; S.slice.pos = defaultCutPos(k); S.slice.tiltA = 0; S.slice.tiltB = 0; S.slice.C = null; sliceZoom('hippocampus'); renderBar(); }));
      const lim = cutLimits(S.slice.plane);
      bar.appendChild(rangeField('', lim[0], lim[1], 10, S.slice.pos, (v) => cutText(S.slice.plane, v), (v) => moveSlice(v)));
      bar.appendChild(rangeField('Tilt ↕', -45, 45, 1, S.slice.tiltA, (v) => v + '°', (v) => { S.slice.tiltA = v; pushSlice(); }));
      bar.appendChild(rangeField('Tilt ↔', -45, 45, 1, S.slice.tiltB, (v) => v + '°', (v) => { S.slice.tiltB = v; pushSlice(); }));
      if (S.slice.tiltA || S.slice.tiltB) bar.appendChild(el('button', { class: 'mini', text: 'Level it', onclick: () => { S.slice.tiltA = 0; S.slice.tiltB = 0; pushSlice(); renderBar(); } }));
      bar.appendChild(el('button', { class: 'mini', text: 'Down the probe', title: 'Cut along the probe track', onclick: sliceDownProbe }));
      bar.appendChild(seg('Color', [['lamina', 'Layers'], ['allen', 'Allen'], ['nissl', 'Nissl']], S.slice.layer, (k) => { S.slice.layer = k; if (S.stage) S.stage.setSliceMode(k); renderBar(); saveSlice(); }));
      bar.appendChild(seg('Probe', [[true, 'Shown'], [false, 'Hidden']], S.probe.on, (k) => { showProbe(k); renderBar(); }));
      bar.appendChild(seg('Mini 3D', [[true, 'Shown'], [false, 'Hidden']], S.slice.mini, (k) => { S.slice.mini = k; if (S.stage) S.stage.mini = k; renderBar(); saveSlice(); }));
      bar.appendChild(el('span', { class: 'sh-gap' }));
      bar.appendChild(el('button', { class: 'mini', text: 'Whole section', onclick: () => sliceZoom('whole') }));
      bar.appendChild(el('button', { class: 'mini', text: 'Hippocampus', onclick: () => sliceZoom('hippocampus') }));
      bar.appendChild(el('button', { class: 'mini', text: 'Dentate', onclick: () => sliceZoom('dg') }));
    }
  }
  const defaultCutPos = (k) => k === 'coronal' ? 8490 : k === 'sagittal' ? 7700 : 2600;
  const cutLimits = (k) => k === 'coronal' ? [400, 12800] : k === 'sagittal' ? [5700, 11200] : [400, 7600];
  function cutText(k, v) {
    if (k === 'coronal') return apText(v);
    if (k === 'sagittal') return 'ML ' + ((v - 5700) / 1000).toFixed(2) + ' mm';
    return 'DV ' + (v / 1000).toFixed(2) + ' mm';
  }

  /* ==================================================================
     Modes and the stage
     ================================================================== */
  async function setMode(m) {
    if (S.play && S.play.kind === 'ride' && m !== '3d') stopPlay();
    S.mode = m;
    store.set({ mode: m });
    root.classList.toggle('sh-mode-schem', m === 'schematic');
    renderBar();
    if (m === 'schematic') { renderSchemFull(); if (S.stage) S.stage.pause(); renderRail(); return; }
    const ok = await ensureStage();
    if (!ok) return;
    S.stage.resume();
    if (m === '3d') {
      S.stage.setView('3d');
      await setLevel(S.level, true);
    } else {
      const ok2 = await need(['brain50.shb.gz', 'hip20.shb.gz', 'fine10.shb.gz', 'cells.shb.gz'], 'Preparing the sections',
        'The whole brain every 50 µm, the hippocampus every 20, its dorsal part every 10 with the real Allen Nissl.');
      if (!ok2) return;
      S.stage.setView('slice');
      S.stage.setSliceMode(S.slice.layer);
      S.stage.mini = S.slice.mini;
      if (!S.slice.C) sliceZoom('hippocampus'); else pushSlice();
      ensureCrowd();
    }
    syncProbe();
    applyFocusAll();
    renderRail();
  }
  async function ensureStage() {
    if (S.stage) return true;
    const ok = await need(['three', 'mesh_brain.shb.gz'], 'Seahorse is getting the brain ready', 'The first time only; after this it is instant.');
    if (!ok) return false;
    const host = $('.sh-host');
    host.innerHTML = '';
    S.stage = S.three.create(host, {
      colors: stageColors(), onPick: onStagePick, onHover: onStageHover, onCamera: onStageCamera, onProbe: onProbeDrag,
      onFrame: onStageFrame,
    });
    await afterLoad();
    S.stage.setLevel('brain', { keepCam: true });
    return true;
  }
  function stageColors() {
    const acc = hexRgb(tok('--accent', '#e5a823'));
    const soft = 'rgb(' + acc.map((x) => Math.round(x + (255 - x) * 0.55)).join(',') + ')';
    return { shell: tok('--text-2', '#9aa'), hpf: soft, bg: tok('--bg', '#111'), bg2: tok('--bg-2', '#181818'),
             probe: tok('--text', '#ddd'), contact: '#f2c14e', accent: tok('--accent', '#e5a823'), err: tok('--err', '#e05555'),
             ink: tok('--text', '#1d2421'), paper: paperColor(), drawn: tok('--text-3', '#aaa') };
  }
  function paperColor() {
    const bg = hexRgb(tok('--bg', '#fff'));
    const dark = bg[0] + bg[1] + bg[2] < 380;
    return dark ? 'rgb(' + (bg[0] + 18) + ',' + (bg[1] + 18) + ',' + (bg[2] + 20) + ')' : '#fbfaf6';
  }
  async function setLevel(lv, quiet) {
    S.level = lv;
    store.set({ level: lv });
    renderBar();
    if (!S.stage) return;
    if (lv !== 'brain') {
      const ok = await need(['mesh_hpf.shb.gz', 'mesh_lamina.shb.gz', 'cells.shb.gz', 'brain50.shb.gz', 'hip20.shb.gz', 'fine10.shb.gz'],
        lv === 'slab' ? 'Opening a slab of the hippocampus' : 'Flying into the hippocampus',
        'Its regions as clay, a cut through them painted with the real 10 µm Nissl, and the cells.');
      if (!ok) return;
    }
    S.stage.setLevel(lv, quiet && S.stage.level === lv ? { keepCam: true } : {});
    applyCut();
    if (lv !== 'brain') ensureCrowd();
    syncProbe();
    applyFocusAll();
    renderRail();
  }
  function applyCut() {
    if (!S.stage || S.mode !== '3d' || (S.play && S.play.kind === 'ride')) return;
    if (S.level === 'brain') S.stage.setCut({ kind: 'none' });
    else if (S.level === 'slab') S.stage.setCut({ kind: 'slab', pos: S.cut.pos, thick: 300 });
    else S.stage.setCut({ kind: S.cut.kind, pos: S.cut.pos });
  }

  /* ---------- the slice ---------- */
  const BASES = {
    coronal: { N: [1, 0, 0], U: [0, 0, 1], V: [0, 1, 0] },
    sagittal: { N: [0, 0, 1], U: [1, 0, 0], V: [0, 1, 0] },
    horizontal: { N: [0, 1, 0], U: [0, 0, 1], V: [1, 0, 0] },
  };
  function rot(v, axis, deg) {
    const a = deg * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
    const [x, y, z] = axis, d = v[0] * x + v[1] * y + v[2] * z;
    const cr = [y * v[2] - z * v[1], z * v[0] - x * v[2], x * v[1] - y * v[0]];
    return [0, 1, 2].map((i) => v[i] * c + cr[i] * s + axis[i] * d * (1 - c));
  }
  function sliceAxes() {
    const b = BASES[S.slice.plane];
    let N = b.N, U = b.U, V = b.V;
    if (S.slice.tiltA) { N = rot(N, b.U, S.slice.tiltA); V = rot(V, b.U, S.slice.tiltA); }
    if (S.slice.tiltB) { N = rot(N, V, S.slice.tiltB); U = rot(U, V, S.slice.tiltB); }
    return { N, U, V };
  }
  function pushSlice() {
    if (!S.stage || !S.slice.C) return;
    const ax = S.slice.axes || sliceAxes();
    S.slice.axes = null;
    const A = S.slice.custom || ax;
    S.stage.setSlice({ N: A.N, U: A.U, V: A.V, C: S.slice.C, k: S.slice.k });
    saveSlice();
    onStageCamera(null);
  }
  function saveSlice() { store.set({ slice: { plane: S.slice.plane, pos: S.slice.pos, tiltA: S.slice.tiltA, tiltB: S.slice.tiltB, C: S.slice.C, k: S.slice.k, layer: S.slice.layer, mini: S.slice.mini } }); }
  function moveSlice(v) {
    const b = BASES[S.slice.plane];
    const d = v - S.slice.pos;
    S.slice.pos = v;
    S.slice.custom = null;
    if (S.slice.C) S.slice.C = S.slice.C.map((x, i) => x + b.N[i] * d);
    pushSlice();
  }
  function sliceZoom(which) {
    const p = S.slice.plane, pos = S.slice.pos;
    const host = $('.sh-host').getBoundingClientRect();
    const fit = (wu, hu) => Math.max(wu / Math.max(100, host.width), hu / Math.max(100, host.height)) * 1.06;
    const at = (u, v) => {
      // a point on the plane at in-plane coordinates (u, v) of the untilted base
      if (p === 'coronal') return [pos, v, u];
      if (p === 'sagittal') return [u, v, pos];
      return [v, pos, u];
    };
    S.slice.custom = null;
    if (which === 'whole') {
      const e = p === 'coronal' ? [5700, 4000, 11400, 8000] : p === 'sagittal' ? [6600, 4000, 13200, 8000] : [5700, 6600, 11400, 13200];
      S.slice.C = at(e[0], e[1]); S.slice.k = fit(e[2], e[3]);
    } else if (which === 'dg') {
      const c = p === 'coronal' ? [7150, 2350] : p === 'sagittal' ? [7400, 2400] : [7200, 7400];
      S.slice.C = at(c[0], c[1]); S.slice.k = fit(1500, 1100);
    } else {
      const c = p === 'coronal' ? [7500, 2350, 3600, 2900] : p === 'sagittal' ? [7700, 3200, 5000, 4700] : [7900, 8100, 4500, 5000];
      S.slice.C = at(c[0], c[1]); S.slice.k = fit(c[2], c[3]);
    }
    pushSlice();
  }
  function sliceDownProbe() {
    computeProbe();
    const d = S.probe.dir, t = S.probe.tip;
    let N = [d[1] * 1 - d[2] * 0, d[2] * 0 - d[0] * 1, d[0] * 0 - d[1] * 0];   // d x ML
    N = [d[1] * 1 - d[2] * 0, d[2] * 0 - d[0] * 1, 0];
    const cr = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
    const nrm = (v) => { const l = Math.hypot(v[0], v[1], v[2]) || 1; return v.map((x) => x / l); };
    N = nrm(cr([0, 0, 1], d));                    // the plane holds the shank and the ML axis
    if (!isFinite(N[0]) || Math.hypot(...N) < 0.5) N = [1, 0, 0];
    const V = nrm(d);
    const U = nrm(cr(V, N));
    const L = 40 + S.probe.contacts * S.probe.pitch;
    S.slice.custom = { N, U, V };
    S.slice.C = t.map((x, i) => x - d[i] * L * 0.6);
    const host = $('.sh-host').getBoundingClientRect();
    S.slice.k = Math.max(2200 / Math.max(100, host.width), (L * 2.2) / Math.max(100, host.height));
    if (S.mode !== 'slice') setMode('slice').then(() => { S.slice.custom = { N, U, V }; S.slice.C = t.map((x, i) => x - d[i] * L * 0.6); pushSlice(); });
    else pushSlice();
    if (!S.probe.on) showProbe(true);
  }

  /* ==================================================================
     Hover, pick, camera: from the stage
     ================================================================== */
  function infoFor(ud) {
    if (!ud) return null;
    if (ud.kind === 'cell') {
      const inst = instOf(ud.key) || {}, type = cellOf(inst.type || ud.key) || {};
      const src = inst.source || {};
      const tag = src.kind === 'ccf' ? ['tracing', 'Whole-brain tracing, registered'] : src.kind === 'slice' ? ['placed', 'Slice tracing, placed by its layers'] : ['drawn', 'Drawn: no public tracing'];
      const name = src.neuron_name ? src.neuron_name : 'drawn';
      const sto = inst.story || {};
      const moved = sto.moved && sto.shift_um ? Math.hypot(...sto.shift_um) : 0;
      return { title: type.label + ' · ' + name, line: type.line || type.about, tag, extra: moved > 0.5 ? 'Moved ' + moved.toFixed(0) + ' µm to meet its partner' : '',
               sel: { type: 'cell', key: type.key, inst: ud.key } };
    }
    if (ud.kind === 'lamina') return lamInfo(ud.key);
    if (ud.kind === 'region') {
      const acr = ud.key;
      const r = S.kb.regions.find((x) => (x.allen || []).includes(acr));
      return { title: (ud.name || acr) + ' (' + acr + ')', line: (S.kb.region_lines || {})[acr] || (r ? r.sub : ''), tag: ['allen', 'Allen CCFv3'],
               sel: r ? { type: 'region', key: r.key } : { type: 'allen', key: acr, name: ud.name } };
    }
    if (ud.kind === 'cap' && ud.ccf) return pointInfo(ud.ccf);
    return null;
  }
  function lamInfo(key) {
    const l = lamOf(key) || { label: key, name: '' };
    const derived = (l.how || '').startsWith('derived');
    return { title: l.label + ' · ' + l.name, line: l.line || '', tag: derived ? ['derived', 'Derived (' + l.how.replace(/^derived: /, '') + ')'] : ['allen', 'Allen CCFv3'],
             sel: { type: 'lamina', key } };
  }
  function pointInfo(c) {
    const s = sampleAt(c[0], c[1], c[2]);
    if (s.lam) { const l = lamByCode(s.lam); if (l) { const i = lamInfo(l.key); i.where = c; return i; } }
    if (s.allen) {
      const st = allenStruct(s.allen);
      return { title: st.name + (st.acronym ? ' (' + st.acronym + ')' : ''), line: (S.kb.region_lines || {})[st.acronym] || '', tag: ['allen', 'Allen CCFv3'],
               sel: { type: 'allen', key: st.acronym, name: st.name, idx: s.allen }, where: c };
    }
    return null;
  }
  function showTip(info, cx, cy) {
    const tip = $('.sh-tip');
    if (!info) { tip.style.display = 'none'; return; }
    tip.innerHTML = '';
    tip.appendChild(el('div', { class: 'sh-tip-title', text: info.title }));
    if (info.line) tip.appendChild(el('div', { class: 'sh-tip-line', text: info.line }));
    const foot = el('div', { class: 'sh-tip-foot' }, [el('span', { class: 'sh-tag ' + info.tag[0], text: info.tag[1] })]);
    if (info.extra) foot.appendChild(el('span', { text: info.extra }));
    if (info.where) foot.appendChild(el('span', { text: apText(info.where[0]) + ' (approx.)' }));
    tip.appendChild(foot);
    const r = $('.sh-stage').getBoundingClientRect();
    tip.style.display = 'block';
    const w = tip.offsetWidth || 280, h = tip.offsetHeight || 80;
    let x = cx - r.left + 16, y = cy - r.top + 16;
    if (x + w > r.width - 8) x = cx - r.left - w - 14;
    if (y + h > r.height - 8) y = cy - r.top - h - 14;
    tip.style.left = Math.max(6, x) + 'px';
    tip.style.top = Math.max(6, y) + 'px';
  }
  function onStageHover(ud, cx, cy) {
    const info = infoFor(ud);
    showTip(info, cx, cy);
    setHover(info ? info.sel : null, 'stage');
  }
  function onStagePick(ud) {
    const info = infoFor(ud);
    select(info ? info.sel : null);
  }
  let camT = 0;
  function onStageCamera() {
    clearTimeout(camT);
    camT = setTimeout(updateHere, 160);
  }
  function onStageFrame() {
    if (S.play && S.play.kind === 'ride') updateRideTag();
  }
  /* What sits at the middle of the view: the "you are here" of the schematic. */
  function updateHere() {
    if (!S.stage || (S.play && S.play.kind === 'ride')) return;
    let ccf = null;
    if (S.mode === 'slice' && S.slice.C) ccf = S.slice.C;
    else if (S.mode === '3d') { const c = S.stage.getCam(); ccf = S.stage.toCcf(c.target[0], c.target[1], c.target[2]); }
    if (!ccf) return;
    const s = sampleAt(ccf[0], ccf[1], ccf[2]);
    let here = null;
    if (s.lam) { const l = lamByCode(s.lam); if (l) here = { type: 'lamina', key: l.key }; }
    else if (s.allen) {
      const acr = allenStruct(s.allen).acronym || '';
      const r = S.kb.regions.find((x) => (x.allen || []).some((a) => acr.startsWith(a)));
      if (r) here = { type: 'region', key: r.key };
    }
    setHere(here);
  }
  function setHere(here) {
    const key = (x) => x ? x.type + ':' + x.key : '';
    if (key(here) === key(S.here)) return;
    if (S.here) { S.trail.push(S.here); if (S.trail.length > 8) S.trail.shift(); }
    S.here = here;
    renderRail(true);
  }

  /* ==================================================================
     Selection, hover and focus, kept in step across the views
     ================================================================== */
  function select(sel, o) {
    o = o || {};
    S.sel = sel;
    if (!o.keepReach) S.reach = null;
    if (sel && sel.type !== 'probe' && sel.type !== 'views' && sel.type !== 'checks') setHere(normHere(sel));
    if (!S.play || S.play.kind !== 'ride') {
      S.focus = sel ? focusFor(sel) : null;
      applyFocusAll();
    }
    showExtras();
    showCard(sel);
    renderRail();
  }
  function normHere(sel) {
    if (sel.type === 'allen') return null;
    return { type: sel.type, key: sel.key };
  }
  function setHover(sel, from) {
    const same = (a, b) => (!a && !b) || (a && b && a.type === b.type && a.key === b.key);
    if (same(sel, S.hover)) return;
    S.hover = sel;
    applySchem();
    if (from !== 'stage' && S.stage) {
      // the schematic is hovering: light the same thing on the stage
      if (sel && sel.type === 'cell') S.stage.glowCells(instances().map((c) => c.key), false), S.stage.glowCells(instancesOfType(sel.key), true);
      else S.stage.glowCells(instances().map((c) => c.key), false);
    }
    applyHighlights();
  }
  function focusFor(sel) {
    const f = { cells: new Set(), regionKeys: new Set(), conns: new Set(), layers: new Set() };
    if (sel.type === 'cell') {
      f.cells.add(sel.key);
      f.regionKeys.add((cellOf(sel.key) || {}).region);
      S.kb.connections.forEach((c) => { if (c.from === sel.key || c.to === sel.key) f.conns.add(c.key); });
      if (S.reach) { S.reach.cells.forEach((k) => f.cells.add(k)); S.reach.conns.forEach((k) => f.conns.add(k)); S.reach.layers.forEach((k) => f.layers.add(k)); S.reach.regions.forEach((k) => f.regionKeys.add(k)); }
    } else if (sel.type === 'region') {
      f.regionKeys.add(sel.key);
      ((regionOf(sel.key) || {}).cells || []).forEach((k) => f.cells.add(k));
      S.kb.connections.forEach((c) => {
        const touches = [c.from, c.to].some((k) => k === sel.key || (cellOf(k) && cellOf(k).region === sel.key));
        if (touches && !c.hidden) f.conns.add(c.key);
      });
    } else if (sel.type === 'conn') {
      addConn(f, connOf(sel.key));
    } else if (sel.type === 'lamina') {
      f.layers.add(sel.key);
      S.kb.connections.forEach((c) => { if ((c.layer || []).includes(sel.key)) f.conns.add(c.key); });
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
    applySchem();
    applyStageFocus();
    applyHighlights();
  }
  function applyStageFocus() {
    if (!S.stage) return;
    const f = S.focus;
    if (!f) { S.stage.focus(null); markReach(); return; }
    const cells = new Set();
    f.cells.forEach((t) => instancesOfType(t).forEach((k) => cells.add(k)));
    const regions = new Set();
    f.regionKeys.forEach((k) => ((regionOf(k) || {}).allen || []).forEach((a) => regions.add(a)));
    S.stage.focus({ cells, regions, layers: f.layers });
    markReach();
  }
  /* Paint the selection, the hover and any event into the sections. */
  function applyHighlights() {
    if (!S.stage || !S.volumesUp) return;
    const acc = hexRgb(tok('--accent', '#e5a823'));
    const lam = new Map(), allen = new Map(), pulse = new Map();
    const codeOf = (k) => (lamOf(k) || {}).code;
    if (S.focus) S.focus.layers.forEach((k) => { const c = codeOf(k); if (c) lam.set(c, acc.concat(0.32)); });
    if (S.sel && S.sel.type === 'lamina') { const c = codeOf(S.sel.key); if (c) lam.set(c, acc.concat(0.5)); }
    if (S.sel && S.sel.type === 'allen' && S.sel.idx) allen.set(S.sel.idx, acc.concat(0.4));
    if (S.hover && S.hover.type === 'lamina') { const c = codeOf(S.hover.key); if (c) lam.set(c, acc.concat(0.42)); }
    if (S.hover && S.hover.type === 'allen' && S.hover.idx) allen.set(S.hover.idx, acc.concat(0.3));
    // the quiz's layer: lit strongly, and pulsing, so it is unmistakable
    if (S.quiz && S.quiz.open && S.quizLayer) { const c = codeOf(S.quizLayer); if (c) pulse.set(c, acc.concat(0.85)); }
    const ev = S.play && (S.play.kind === 'event' || (S.play.kind === 'ride' && S.play.sink)) ? S.play : null;
    if (ev && ev.sink) {
      const sink = hexRgb(tok('--err', '#d6362e')), src = hexRgb('#2e70d6');
      ev.sink.forEach((k) => { const c = codeOf(k); if (c) pulse.set(c, sink.concat(0.7)); });
      (ev.source || []).forEach((k) => { const c = codeOf(k); if (c) pulse.set(c, src.concat(0.45)); });
    }
    S.stage.setHighlights({ lam, allen, pulse });
  }

  /* ==================================================================
     The rail: the schematic that follows you, over the card
     ================================================================== */
  const schemHelpers = () => ({
    kb: S.kb, cellOf, regionOf, connOf, lamOf, verdictOf, regionOfLayer,
    select: (sel) => select(sel), hover: (sel) => { setHover(sel, 'schem'); if (sel) showSchemTip(sel); else hideSchemTip(); },
    notes: (type, key) => notesFor(type, key).length,
  });
  function schemKind() {
    if (S.schemPick !== 'auto') return S.schemPick;
    if (S.mode === 'schematic') return S.schemFullPick || 'circuit';
    if (S.sel && S.sel.type === 'cell' && !(S.play && S.play.kind === 'ride')) return 'cell';
    if (S.play && ['ds1', 'ds2', 'dentate'].includes(S.play.key)) return 'dentate';
    if (S.mode === '3d' && S.level === 'slab') return 'dentate';
    const hr = S.here ? (S.here.type === 'lamina' ? regionOfLayer(S.here.key) : S.here.type === 'region' ? S.here.key : null) : null;
    if (S.mode === 'slice' && S.slice.k && S.slice.k < 5 && (hr === 'dg' || hr === 'ca3')) return 'dentate';
    return 'circuit';
  }
  function renderRail(soft) {
    if (!S.kb) return;
    const head = $('.sh-rail-head');
    const kind = S.mode === 'schematic' ? null : schemKind();
    root.classList.toggle('sh-no-schem', S.mode === 'schematic');
    head.innerHTML = '';
    if (kind) {
      head.appendChild(seg('', [['auto', 'Auto', 'Follows what you look at'], ['circuit', 'Circuit'], ['dentate', 'By layer'], ['cell', 'Cell', 'The selected cell\'s inputs and outputs']], S.schemPick,
        (k) => { S.schemPick = k; store.set({ schemPick: k }); renderRail(); }));
      head.appendChild(el('span', { class: 'sh-rail-what', text: kind === 'cell' ? 'Wiring of the ' + ((cellOf((S.sel || {}).key) || {}).label || 'cell') : kind === 'dentate' ? 'Dentate and CA3, by layer' : 'Hippocampal formation' }));
      head.appendChild(seg('Follow', [[true, 'On'], [false, 'Off']], S.follow, (k) => { S.follow = k; store.set({ follow: k }); renderRail(); }));
    }
    const box = $('.sh-rail-schem');
    const cellKey = kind === 'cell' ? ((S.sel && S.sel.type === 'cell') ? S.sel.key : (S.lastCell || 'gc')) : null;
    const sig = kind + ':' + (cellKey || '') + ':' + Object.keys(S.lab.notes || {}).length;
    if (kind && (S.schemShown !== sig || !box.firstChild)) {
      const svgNode = kind === 'cell' ? BARRY.shSchem.cell(schemHelpers(), cellKey) : kind === 'dentate' ? BARRY.shSchem.dentate(schemHelpers()) : BARRY.shSchem.circuit(schemHelpers());
      box.innerHTML = '';
      box.appendChild(svgNode);
      if (!reducedMotion()) { svgNode.classList.add('sh-fade-in'); }
      S.schemShown = sig;
    }
    if (cellKey) S.lastCell = cellKey;
    applySchem();
  }
  function applySchem() {
    const st = { focus: S.focus, hover: S.hover, sel: S.sel, here: S.here, trail: S.trail,
                 ds: S.play && S.play.sink ? { sink: S.play.sink, source: S.play.source || [] } : null,
                 cellRegion: (k) => (cellOf(k) || {}).region };
    const rail = $('.sh-rail-schem svg');
    if (rail) { BARRY.shSchem.apply(rail, st); BARRY.shSchem.follow(rail, S.here, S.follow); }
    const full = $('.sh-schem-full svg');
    if (full) BARRY.shSchem.apply(full, st);
  }
  function renderSchemFull() {
    const box = $('.sh-schem-full');
    box.innerHTML = '';
    const pick = S.schemFullPick || 'circuit';
    box.appendChild(el('div', { class: 'sh-schem-tabs' }, [seg('', [['circuit', 'Circuit'], ['dentate', 'Dentate, by layer']], pick,
      (k) => { S.schemFullPick = k; renderSchemFull(); })]));
    box.appendChild(pick === 'dentate' ? BARRY.shSchem.dentate(schemHelpers()) : BARRY.shSchem.circuit(schemHelpers()));
    applySchem();
  }
  let schemTipT = 0;
  function showSchemTip(sel) {
    clearTimeout(schemTipT);
    const tip = $('.sh-tip');
    let info = null;
    if (sel.type === 'cell') { const c = cellOf(sel.key); if (c) info = { title: c.label, line: c.line || c.about, tag: ['tracing', 'Real tracings in 3D'] }; }
    else if (sel.type === 'lamina') info = lamInfo(sel.key);
    else if (sel.type === 'region') { const r = regionOf(sel.key); if (r) info = { title: r.label, line: r.sub, tag: ['allen', (r.allen || []).join(', ')] }; }
    else if (sel.type === 'conn') { const c = connOf(sel.key); const v = verdictOf(sel.key); if (c) info = { title: c.label, line: c.about || '', tag: [v.status === 'supported' ? 'tracing' : 'allen', ({ supported: 'Supported by data', consistent: 'Placement consistent', weak: 'Weak in data', cited: 'Cited, not tested', untested: 'Not testable here' }[v.status] || v.status)] }; }
    if (!info) { tip.style.display = 'none'; return; }
    const r = $('.sh-stage').getBoundingClientRect();
    showTip(info, r.right - 300, r.top + 14);
  }
  function hideSchemTip() { schemTipT = setTimeout(() => { $('.sh-tip').style.display = 'none'; }, 120); }

  /* ==================================================================
     Cards
     ================================================================== */
  function showCard(sel) {
    if (S.quiz && S.quiz.open && !(sel && sel.type === 'quiz')) S.quiz.open = false;
    const card = $('.sh-card');
    card.innerHTML = '';
    card.scrollTop = 0;
    if (!sel) return renderAbout(card);
    if (sel.type === 'cell') return renderCell(card, cellOf(sel.key), sel.inst);
    if (sel.type === 'region') return renderRegion(card, regionOf(sel.key));
    if (sel.type === 'conn') return renderConn(card, connOf(sel.key));
    if (sel.type === 'lamina') return renderLamina(card, sel.key);
    if (sel.type === 'probe') return renderProbe(card);
    if (sel.type === 'checks') return renderChecks(card);
    if (sel.type === 'views') return renderViews(card);
    if (sel.type === 'quiz') return renderQuiz(card);
    if (sel.type === 'event') return renderEventCard(card);
    if (sel.type === 'allen') {
      card.appendChild(el('div', { class: 'sh-kicker', text: 'Allen CCFv3 structure' }));
      card.appendChild(el('h2', { text: sel.name || sel.key }));
      card.appendChild(el('p', { text: sel.key + ' in the Allen Mouse Brain Common Coordinate Framework (2017 annotation). Seahorse adds detail only inside the hippocampal formation; elsewhere it shows the Allen atlas as it is.' }));
      card.appendChild(notesBlock('allen', sel.key));
    }
  }
  const refsList = (keys) => el('ol', { class: 'sh-refs' }, (keys || []).map((k) => el('li', { text: refText(k) })));
  const citeChips = (keys) => el('span', { class: 'sh-cites' }, (keys || []).map((k) => el('button', { class: 'sh-cite', text: refShort(k), title: refText(k), onclick: () => showRefs([k]) })));
  function showRefs(keys) {
    const card = $('.sh-card');
    const box = el('div', { class: 'sh-src sh-refbox' }, [el('b', { text: 'Reference' }), refsList(keys)]);
    card.prepend(box);
    card.scrollTop = 0;
  }
  function connRow(c) {
    const v = verdictOf(c.key);
    const name = (k) => (cellOf(k) || regionOf(k) || { label: k }).label;
    return el('div', { class: 'sh-check', onclick: () => select({ type: 'conn', key: c.key }), onpointerenter: () => setHover({ type: 'conn', key: c.key }, 'card'),
      onpointerleave: () => setHover(null, 'card'), style: 'cursor:pointer' }, [
      el('div', {}, [el('b', { text: c.label }), document.createTextNode(' · ' + name(c.from) + ' → ' + name(c.to)
        + (c.layer && c.layer.length ? ', in ' + c.layer.map((k) => (lamOf(k) || { label: k }).label).join(', ') : ''))]),
      el('div', {}, [verdictChip(v)]),
    ]);
  }
  function renderAbout(card) {
    const kb = S.kb;
    card.appendChild(el('div', { class: 'sh-kicker', text: 'Mouse brain atlas' }));
    card.appendChild(el('h2', {}, [el('span', { html: SEAHORSE_SVG, class: 'sh-logo' }), el('span', { text: 'Seahorse' })]));
    card.appendChild(el('p', { text: 'The mouse brain from the Allen atlas, and the hippocampus down to its layers and the cells we record. Hover anything to read what it is; click to select it in every view. Ride a signal along real cells, play a dentate spike, or take a tour.' }));
    card.appendChild(el('h3', { text: 'Ride a signal' }));
    card.appendChild(el('div', { class: 'sh-links' }, ((S.rides && S.rides.rides) || []).filter((r) => r.kind !== 'event').map((r) =>
      el('button', { class: 'pill', text: r.label, title: r.blurb || '', onclick: () => startRide(r.key) }))));
    card.appendChild(el('h3', { text: 'Cells' }));
    card.appendChild(el('div', { class: 'sh-links' }, kb.cells.map((c) => el('button', { class: 'pill', onclick: () => select({ type: 'cell', key: c.key }),
      onpointerenter: () => setHover({ type: 'cell', key: c.key }, 'card'), onpointerleave: () => setHover(null, 'card') },
      [el('span', { class: 'sh-sw', style: 'display:inline-block;margin-right:6px;background:' + c.color }), document.createTextNode(c.short)]))));
    const t = tally();
    card.appendChild(el('h3', { text: 'What was checked' }));
    card.appendChild(el('div', { class: 'sh-tally' }, Object.entries(t).map(([k, n]) => el('span', {}, [verdictChip({ status: k }), document.createTextNode(' ' + n)]))));
    card.appendChild(el('button', { class: 'mini', text: 'Open the checks', onclick: () => showCard({ type: 'checks' }) }));
    if (kb.crowd) { card.appendChild(el('h3', { text: 'The crowd' })); card.appendChild(el('p', { class: 'sh-small', text: kb.crowd.note + (S.crowdN ? ' ' + S.crowdN.toLocaleString() + ' somata placed.' : '') })); }
    card.appendChild(el('h3', { text: 'Sources' }));
    card.appendChild(el('p', { class: 'sh-small', text: 'Anatomy: Allen Mouse Brain CCFv3 (Wang et al. 2020), 2017 annotation, with the Allen ARA Nissl at 10 µm. Connectivity tests: Allen Mouse Connectivity Atlas (Oh et al. 2014). Cells: NeuroMorpho.Org (Ascoli et al. 2007); whole-brain tracings from MouseLight (Winnubst et al. 2019). Built on this computer by tools/seahorse; nothing is fetched while you use the tab.' }));
  }
  function tally() {
    const t = {};
    Object.values(S.checks ? S.checks.connections : {}).forEach((v) => { t[v.status] = (t[v.status] || 0) + 1; });
    return t;
  }
  function tracingBox(inst) {
    const src = inst.source || {};
    const box = el('div', { class: 'sh-src' });
    const sto = inst.story || {};
    if (src.kind === 'drawn') {
      box.appendChild(el('div', {}, [el('span', { class: 'sh-tag drawn', text: 'Drawn' }), document.createTextNode(' no public tracing exists')]));
      box.appendChild(el('div', { text: src.note || '' }));
    } else {
      box.appendChild(el('div', {}, [el('b', { text: src.neuron_name }), document.createTextNode(' · ' + src.archive + ' · ' + (src.species || 'mouse')),
        document.createTextNode(inst.key !== inst.type ? '  (' + inst.key + ')' : '')]));
      box.appendChild(el('div', {}, [el('span', { class: 'sh-tag ' + (src.kind === 'ccf' ? 'tracing' : 'placed'), text: src.kind === 'ccf' ? 'Registered by its authors' : 'Slice tracing, placed' }),
        document.createTextNode(src.kind === 'ccf' ? ' traced through the whole brain' + (src.mirrored ? ', mirrored into the right hemisphere' : '')
          : ' placed by its layers (fit ' + ((src.fit || {}).score || '?') + ' of 1.1)')]));
      box.appendChild(el('div', { class: 'sh-small', text: 'Axon ' + (inst.axon_mm || 0) + ' mm · dendrites ' + (inst.dend_mm || 0) + ' mm · soma in ' + ((lamOf(inst.soma_lamina) || {}).label || inst.soma_allen) }));
      const links = el('div', { class: 'sh-links' });
      if (src.url) links.appendChild(el('a', { href: src.url, target: '_blank', rel: 'noopener', text: 'NeuroMorpho record' }));
      (src.doi || []).forEach((d) => links.appendChild(el('a', { href: 'https://doi.org/' + d, target: '_blank', rel: 'noopener', text: 'doi:' + d })));
      box.appendChild(links);
    }
    if (sto.meets) box.appendChild(el('div', { class: 'sh-small', text: 'Meets ' + sto.meets + '\'s axon in ' + ((lamOf(sto.layer) || {}).label || sto.layer) + ': '
      + sto.gap_um + ' µm apart where traced' + (sto.moved ? '; moved ' + Math.hypot(...sto.shift_um).toFixed(1) + ' µm to touch.' : '.') }));
    if (sto.reaches && sto.gap_um != null) box.appendChild(el('div', { class: 'sh-small', text: 'Placed so its axon reaches ' + sto.reaches + '\'s ' + ({ dend: 'dendrite', soma: 'soma', ais: 'axon initial segment' }[sto.what] || '') + ' (moved ' + sto.gap_um + ' µm).' }));
    return box;
  }
  function renderCell(card, c, instKey) {
    if (!c) return renderAbout(card);
    S.lastCell = c.key;
    card.appendChild(el('div', { class: 'sh-kicker', text: (regionOf(c.region) || {}).label + ' · ' + (c.sign === 'inh' ? 'inhibitory' : 'excitatory') }));
    card.appendChild(el('h2', {}, [el('span', { class: 'sh-sw', style: 'width:14px;height:14px;background:' + c.color }), el('span', { text: c.label })]));
    card.appendChild(el('p', { text: c.about }));
    // what to do with it
    const reach = S.reach;
    card.appendChild(el('div', { class: 'sh-links sh-actions' }, [
      el('button', { class: 'btn sm' + (reach && reach.dir === 'out' ? '' : ' ghost'), text: 'Where does it lead?', onclick: () => startReach(c.key, 'out') }),
      el('button', { class: 'btn sm' + (reach && reach.dir === 'in' ? '' : ' ghost'), text: 'What feeds it?', onclick: () => startReach(c.key, 'in') }),
      reach ? el('button', { class: 'btn sm ghost', text: 'Next hop (' + (reach.hops + 1) + ')', disabled: !reach.frontier.length, onclick: nextHop }) : null,
      el('button', { class: 'btn sm ghost', text: 'Fly to it', onclick: () => flyToCell(instKey || instancesOfType(c.key)[0]) }),
      rideFor(c.key) ? el('button', { class: 'btn sm ghost', text: 'Ride from here', onclick: () => startRide(rideFor(c.key)) }) : null,
    ]));
    if (reach) card.appendChild(el('div', { class: 'sh-reach', text: reachText(reach) }));
    card.appendChild(el('h3', { text: 'Identity' }));
    card.appendChild(el('dl', {}, [
      el('dt', { text: 'Soma' }), el('dd', { text: c.soma }),
      el('dt', { text: 'Dendrites' }), el('dd', { text: c.dend }),
      el('dt', { text: 'Axon' }), el('dd', { text: c.axon }),
      c.markers ? el('dt', { text: 'Markers' }) : null, c.markers ? el('dd', { text: c.markers }) : null,
    ]));
    if ((c.phys || []).length) {
      card.appendChild(el('h3', { text: 'Physiology' }));
      c.phys.forEach((p) => card.appendChild(el('p', {}, [document.createTextNode(p.text + ' '), citeChips(p.refs)])));
    }
    if (c.lab) card.appendChild(el('div', { class: 'sh-lab' }, [el('b', { text: 'For the lab: ' }), document.createTextNode(c.lab.text + ' '), citeChips(c.lab.refs)]));
    card.appendChild(el('h3', { text: 'The tracing' + (instancesOfType(c.key).length > 1 ? 's' : '') }));
    if (S.blobs['cells.shb.gz']) instancesOfType(c.key).forEach((k) => card.appendChild(tracingBox(instOf(k))));
    else card.appendChild(el('p', { class: 'sh-small', text: 'Open 3D (Hippocampus) or a slice to load the tracings.' }));
    const cs = (S.checks && S.checks.cells) || {};
    instancesOfType(c.key).forEach((k) => (cs[k] && cs[k].notes || []).slice(0, 2).forEach((n) => card.appendChild(el('div', { class: 'sh-small', text: n }))));
    const ins = S.kb.connections.filter((x) => x.to === c.key), outs = S.kb.connections.filter((x) => x.from === c.key);
    if (ins.length || outs.length) {
      card.appendChild(el('h3', { text: 'Wiring' }));
      if (ins.length) { card.appendChild(el('div', { class: 'sh-sub', text: 'Inputs' })); ins.forEach((x) => card.appendChild(connRow(x))); }
      if (outs.length) { card.appendChild(el('div', { class: 'sh-sub', text: 'Outputs' })); outs.forEach((x) => card.appendChild(connRow(x))); }
    }
    card.appendChild(notesBlock('cell', c.key));
    card.appendChild(el('h3', { text: 'References' }));
    card.appendChild(refsList(c.refs));
  }
  function rideFor(type) {
    const want = { gc: 'trisynaptic', fan: 'trisynaptic', ca3: 'trisynaptic', ca1: 'trisynaptic', mc: 'dentate', hipp: 'dentate', pvbc: 'dentate', aac: 'dentate', olm: 'caside', stel: 'ds2' };
    return want[type] || null;
  }
  function renderRegion(card, r) {
    if (!r) return renderAbout(card);
    card.appendChild(el('div', { class: 'sh-kicker', text: 'Region' }));
    card.appendChild(el('h2', { text: r.label }));
    card.appendChild(el('p', { text: (r.allen || []).map((a) => (S.kb.region_lines || {})[a]).filter(Boolean)[0] || r.sub }));
    card.appendChild(el('dl', {}, [el('dt', { text: 'Allen' }), el('dd', { text: (r.allen || []).join(', ') })]));
    if ((r.cells || []).length) {
      card.appendChild(el('h3', { text: 'Cells here' }));
      card.appendChild(el('div', { class: 'sh-links' }, r.cells.map((k) => el('button', { class: 'pill', text: cellOf(k).label, onclick: () => select({ type: 'cell', key: k }) }))));
    }
    const conns = S.kb.connections.filter((c) => !c.hidden && [c.from, c.to].some((k) => k === r.key || (cellOf(k) && cellOf(k).region === r.key)));
    if (conns.length) { card.appendChild(el('h3', { text: 'In and out' })); conns.forEach((x) => card.appendChild(connRow(x))); }
    card.appendChild(notesBlock('region', r.key));
  }
  function renderConn(card, c) {
    if (!c) return renderAbout(card);
    const v = verdictOf(c.key);
    const name = (k) => (cellOf(k) || regionOf(k) || { label: k }).label;
    card.appendChild(el('div', { class: 'sh-kicker', text: (c.sign === 'inh' ? 'Inhibitory' : 'Excitatory') + ' connection' }));
    card.appendChild(el('h2', { text: c.label }));
    card.appendChild(el('p', { text: name(c.from) + ' → ' + name(c.to) + (c.layer ? ', ending in ' + c.layer.map((k) => (lamOf(k) || { label: k }).label).join(', ') : '') }));
    if (c.about) card.appendChild(el('p', { text: c.about }));
    const rk = Object.entries(RIDE_OF_CONN).find(([k]) => k === c.key);
    if (rk) card.appendChild(el('div', { class: 'sh-links' }, [el('button', { class: 'btn sm', text: 'Ride it', onclick: () => startRide(rk[1]) })]));
    card.appendChild(el('h3', { text: 'Checked against data' }));
    const box = el('div', { class: 'sh-src' }, [el('div', {}, [verdictChip(v)]), el('div', { text: v.detail || '' })]);
    if (v.top && v.top.length) box.appendChild(el('div', { class: 'sh-small', text: 'Strongest: ' + v.top.slice(0, 3).map((x) => 'exp. ' + x.id + ' (' + x.line + ') ' + x.density).join('; ') }));
    card.appendChild(box);
    card.appendChild(notesBlock('conn', c.key));
    card.appendChild(el('h3', { text: 'References' }));
    card.appendChild(refsList(c.refs));
  }
  const RIDE_OF_CONN = { lpp: 'trisynaptic', mf_ca3: 'trisynaptic', sc: 'trisynaptic', ca1_sub: 'trisynaptic', mpp: 'ds2', mf_mc: 'dentate', mc_gc: 'dentate',
                         hipp_gc: 'dentate', pv_gc: 'dentate', aac_gc: 'dentate', rc: 'caside', ta: 'caside', olm_ca1: 'caside', ca1_olm: 'caside' };
  function renderLamina(card, key) {
    const l = lamOf(key) || { label: key, name: '', how: '' };
    const n = S.checks && S.checks.nissl_means ? S.checks.nissl_means[key] : null;
    card.appendChild(el('div', { class: 'sh-kicker', text: 'Layer' }));
    card.appendChild(el('h2', {}, [el('span', { class: 'sh-sw sq', style: 'width:14px;height:14px;background:' + (S.kb.lamina_colors[key] || '#888') }), el('span', { text: l.label + ' · ' + l.name })]));
    if (l.line) card.appendChild(el('p', { text: l.line }));
    if (BARRY.shLearn.RECORDS[key]) card.appendChild(el('div', { class: 'sh-lab' }, [el('b', { text: 'On a probe: ' }), document.createTextNode(BARRY.shLearn.RECORDS[key])]));
    card.appendChild(el('dl', {}, [el('dt', { text: 'Made by' }), el('dd', { text: l.how || 'Allen annotation' }),
      n != null ? el('dt', { text: 'Nissl' }) : null, n != null ? el('dd', { text: 'mean ' + n + ' of 255 (' + ((S.checks || {}).nissl_source || 'Allen Nissl') + ')' }) : null]));
    const lc = (S.checks && S.checks.lamina || []).find((x) => x.layer === key);
    if (lc) card.appendChild(el('div', { class: 'sh-src' }, [verdictChip({ status: lc.ok ? 'supported' : 'not seen' }), el('div', { text: lc.detail })]));
    const ending = S.kb.connections.filter((c) => (c.layer || []).includes(key));
    if (ending.length) { card.appendChild(el('h3', { text: 'Inputs that end here' })); ending.forEach((x) => card.appendChild(connRow(x))); }
    const here = S.kb.cells.filter((c) => instancesOfType(c.key).some((k) => (instOf(k) || {}).soma_lamina === key));
    if (here.length) {
      card.appendChild(el('h3', { text: 'Somata here' }));
      card.appendChild(el('div', { class: 'sh-links' }, here.map((c) => el('button', { class: 'pill', text: c.label, onclick: () => select({ type: 'cell', key: c.key }) }))));
    }
    card.appendChild(notesBlock('lamina', key));
  }

  /* ---------- where it leads, what feeds it ---------- */
  function startReach(type, dir) {
    S.reach = { origin: type, dir, hops: 1, cells: new Set(), conns: new Set(), layers: new Set(), regions: new Set(), frontier: [type], seen: new Set([type]) };
    hop();
    select({ type: 'cell', key: type }, { keepReach: true });
    flyToReach();
  }
  function hop() {
    const R = S.reach;
    const next = [];
    for (const t of R.frontier) {
      for (const c of S.kb.connections) {
        if (c.hidden) continue;
        const mine = R.dir === 'out' ? c.from === t || (!cellOf(c.from) && c.from === (cellOf(t) || {}).region && false) : c.to === t;
        if (!mine) continue;
        const other = R.dir === 'out' ? c.to : c.from;
        R.conns.add(c.key);
        (c.layer || []).forEach((l) => R.layers.add(l));
        if (cellOf(other)) { R.cells.add(other); if (!R.seen.has(other)) { R.seen.add(other); next.push(other); } }
        else R.regions.add(other);
      }
    }
    R.frontier = next;
  }
  function nextHop() {
    if (!S.reach || !S.reach.frontier.length) return;
    S.reach.hops += 1;
    hop();
    S.focus = focusFor(S.sel);
    applyFocusAll();
    showCard(S.sel);
    flyToReach();
  }
  function reachText(R) {
    const names = [...R.cells].map((k) => (cellOf(k) || {}).short || k);
    const regs = [...R.regions].map((k) => (regionOf(k) || {}).label || k);
    const what = names.concat(regs);
    return (R.dir === 'out' ? 'Leads to' : 'Fed by') + ' (' + R.hops + ' hop' + (R.hops > 1 ? 's' : '') + '): ' + (what.length ? what.join(', ') : 'nothing listed') + '.'
      + (R.layers.size ? ' Layers: ' + [...R.layers].map((k) => (lamOf(k) || { label: k }).label).join(', ') + '.' : '');
  }
  /* light the origin's axon where it runs in the target layers */
  function markReach() {
    if (!S.stage || !S.stage.markArbor) return;
    instances().forEach((c) => S.stage.markArbor(c.key, null));
    const R = S.reach;
    if (!R || !R.layers.size) return;
    const codes = new Set([...R.layers].map((k) => (lamOf(k) || {}).code));
    const test = (ccf) => codes.has(sampleAt(ccf[0], ccf[1], ccf[2]).lam);
    const arbor = R.dir === 'out' ? 'axon' : 'dend';
    instancesOfType(R.origin).forEach((k) => S.stage.markArbor(k, test, arbor));
    if (R.dir === 'out') R.cells.forEach((t) => instancesOfType(t).forEach((k) => S.stage.markArbor(k, test, 'dend')));
  }
  function flyToReach() {
    if (!S.stage || S.mode !== '3d') return;
    const R = S.reach;
    const keys = instancesOfType(R.origin).concat([...R.cells].flatMap((t) => instancesOfType(t)));
    const pts = keys.map((k) => S.stage.cellSomaW(k)).filter(Boolean);
    if (pts.length) S.stage.frameOn(pts);
  }
  async function flyToCell(key) {
    if (!key) return;
    if (S.mode !== '3d') await setMode('3d');
    if (S.level === 'brain') await setLevel('hpf');
    const pts = S.stage && S.stage.cellBounds(key);
    if (pts && pts.length) S.stage.frameOn(pts);
  }

  /* ==================================================================
     Lab notes and saved views (shared through GUI_logs/seahorse)
     ================================================================== */
  async function loadLab() {
    try {
      const r = await api('/api/seahorse/lab');
      if (r && r.ok) S.lab = { notes: r.notes || {}, views: r.views || {}, me: r.me || '' };
    } catch (e) { /* an older server: notes stay local to nothing */ }
  }
  function notesFor(type, key) {
    return Object.entries(S.lab.notes || {}).filter(([, n]) => n && n.target && n.target.type === type && n.target.key === key)
      .map(([id, n]) => Object.assign({ id }, n)).sort((a, b) => (a.at || '').localeCompare(b.at || ''));
  }
  function notesBlock(type, key) {
    const list = notesFor(type, key);
    const box = el('div', { class: 'sh-notes' }, [el('h3', { text: 'Lab notes' + (list.length ? ' (' + list.length + ')' : '') })]);
    list.forEach((n) => box.appendChild(el('div', { class: 'sh-note' }, [
      el('div', { class: 'sh-note-text', text: n.text }),
      el('div', { class: 'sh-note-foot' }, [el('span', { text: (n.by || 'someone') + ' · ' + (n.at || '').slice(0, 10) }),
        el('button', { class: 'mini', text: 'Delete', onclick: async () => { if (!confirm('Delete this note for everyone?')) return; await saveNote({ id: n.id, delete: true }); showCard(S.sel); renderRail(); } })]),
    ])));
    const ta = el('textarea', { rows: 2, placeholder: 'Add a note for the lab (shared with every lab machine)…' });
    box.appendChild(ta);
    box.appendChild(el('button', { class: 'mini', text: 'Add note', onclick: async () => {
      const t = ta.value.trim();
      if (!t) return;
      await saveNote({ target: { type, key }, text: t });
      showCard(S.sel); renderRail();
    } }));
    return box;
  }
  async function saveNote(body) {
    try {
      const r = await apiPost('/api/seahorse/note', body);
      if (r && r.ok) { S.lab.notes = r.notes || {}; S.lab.views = r.views || S.lab.views; toast(body.delete ? 'Note deleted.' : 'Note saved; it travels to the other lab machines with the shared records.', 'ok'); }
      else toast((r && r.error) || 'The note was not saved.', 'err');
    } catch (e) { toast('The note was not saved: ' + e.message, 'err'); }
  }
  function captureView() {
    const v = { mode: S.mode, level: S.level, cut: Object.assign({}, S.cut), sel: S.sel && { type: S.sel.type, key: S.sel.key },
                slice: { plane: S.slice.plane, pos: S.slice.pos, tiltA: S.slice.tiltA, tiltB: S.slice.tiltB, C: S.slice.C, k: S.slice.k, layer: S.slice.layer, custom: S.slice.custom || null },
                probe: Object.assign({}, S.probe, { tip: null, dir: null }), story: S.story, exploded: S.exploded };
    if (S.stage && S.mode === '3d') v.cam = S.stage.getCam();
    return v;
  }
  async function openView(v) {
    if (!v) return;
    S.cut = Object.assign(S.cut, v.cut || {});
    Object.assign(S.slice, v.slice || {});
    Object.assign(S.probe, v.probe || {});
    S.story = v.story !== false;
    S.exploded = !!v.exploded;
    S.level = v.level || S.level;
    await setMode(v.mode || '3d');
    if (S.stage) {
      S.stage.setStory(S.story);
      S.stage.explode(S.exploded ? 1 : 0);
      if (v.cam && S.mode === '3d') S.stage.setCam(v.cam, 1000);
    }
    if (v.sel) select(v.sel);
    syncProbe();
  }
  const viewCode = (v) => 'seahorse:' + btoa(unescape(encodeURIComponent(JSON.stringify(v))));
  function parseCode(s) {
    const m = String(s || '').trim().match(/^seahorse:([A-Za-z0-9+/=]+)$/);
    if (!m) return null;
    try { return JSON.parse(decodeURIComponent(escape(atob(m[1])))); } catch (e) { return null; }
  }
  function renderViews(card) {
    card.appendChild(el('div', { class: 'sh-kicker', text: 'Shared with the lab' }));
    card.appendChild(el('h2', { text: 'Saved views' }));
    card.appendChild(el('p', { text: 'A view keeps the mode, camera, cut, section, probe and selection. Views travel to every lab machine with the shared records; Copy code gives a line you can paste into Seahorse\'s search box anywhere.' }));
    const name = el('input', { type: 'text', placeholder: 'Name this view (e.g. "Probe through dorsal DG")' });
    card.appendChild(el('div', { class: 'sh-row' }, [name, el('button', { class: 'btn sm', text: 'Save this view', onclick: async () => {
      try {
        const r = await apiPost('/api/seahorse/view', { name: name.value || 'Untitled view', state: captureView() });
        if (r && r.ok) { S.lab.views = r.views || {}; toast('Saved for the lab.', 'ok'); showCard({ type: 'views' }); }
        else toast((r && r.error) || 'Not saved.', 'err');
      } catch (e) { toast('Not saved: ' + e.message, 'err'); }
    } })]));
    const list = Object.entries(S.lab.views || {}).filter(([, v]) => v).sort((a, b) => (b[1].at || '').localeCompare(a[1].at || ''));
    if (!list.length) card.appendChild(el('p', { class: 'sh-small', text: 'No saved views yet.' }));
    list.forEach(([id, v]) => card.appendChild(el('div', { class: 'sh-check' }, [
      el('div', {}, [el('b', { text: v.name }), document.createTextNode(' · ' + (v.by || 'someone') + ' · ' + (v.at || '').slice(0, 10))]),
      el('div', { class: 'sh-links' }, [
        el('button', { class: 'mini', text: 'Open', onclick: () => openView(v.state) }),
        el('button', { class: 'mini', text: 'Copy code', onclick: async () => { try { await navigator.clipboard.writeText(viewCode(v.state)); toast('Copied. Paste it into Seahorse\'s search box to open this view.', 'ok'); } catch (e) { toast('The clipboard is not available here.', 'err'); } } }),
        el('button', { class: 'mini', text: 'Delete', onclick: async () => {
          if (!confirm('Delete "' + v.name + '" for everyone?')) return;
          const r = await apiPost('/api/seahorse/view', { id, delete: true });
          if (r && r.ok) { S.lab.views = r.views || {}; showCard({ type: 'views' }); }
        } }),
      ]),
    ])));
  }

  /* ==================================================================
     The probe: surgery coordinates, the shank, its contacts
     ================================================================== */
  function computeProbe() {
    const P = S.probe;
    const a = (P.angAP || 0) * Math.PI / 180, b = (P.angML || 0) * Math.PI / 180;
    const d = [Math.tan(a), 1, Math.tan(b)];
    const L = Math.hypot(...d);
    P.dir = d.map((x) => x / L);
    const ap = 5400 - P.ap * 1000, ml = 5700 + P.ml * 1000;
    const dv0 = S.blobs['brain50.shb.gz'] ? surfaceDvAt(ap, ml) : 900;
    P.entry = [ap, dv0, ml];
    P.tip = P.entry.map((x, i) => x + P.dir[i] * P.depth * 1000);
    return P;
  }
  function probeForStage() {
    const P = computeProbe();
    return { tip: P.tip, dir: P.dir, contacts: P.contacts, pitch: P.pitch, first: P.first, length: P.depth * 1000 + 400 };
  }
  function syncProbe() {
    if (!S.stage) return;
    S.stage.setProbe(S.probe.on ? probeForStage() : null);
  }
  function showProbe(on) {
    S.probe.on = !!on;
    store.set({ probe: probeSave() });
    syncProbe();
    if (on && S.sel && S.sel.type === 'probe') showCard(S.sel);
  }
  const probeSave = () => ({ on: S.probe.on, ap: S.probe.ap, ml: S.probe.ml, depth: S.probe.depth, angML: S.probe.angML, angAP: S.probe.angAP });
  function onProbeDrag(ccf, end) {
    if (end) { store.set({ probe: probeSave() }); select({ type: 'probe' }); return; }
    if (!ccf) return;
    // keep the angle, slide the tip: the entry follows along the shank
    const P = S.probe;
    const d = P.dir || [0, 1, 0];
    let e = ccf.slice();
    for (let i = 0; i < 400; i++) { const s = sampleAt(e[0], e[1], e[2]); if (!s.allen) break; e = e.map((x, j) => x - d[j] * 25); }
    P.ap = +((5400 - e[0]) / 1000).toFixed(3);
    P.ml = +((e[2] - 5700) / 1000).toFixed(3);
    P.depth = +(Math.hypot(ccf[0] - e[0], ccf[1] - e[1], ccf[2] - e[2]) / 1000).toFixed(3);
    syncProbe();
  }
  function contactCcf(i) {
    const P = S.probe;
    return P.tip.map((x, k) => x - P.dir[k] * (P.first + i * P.pitch));
  }
  function probeRuns() {
    computeProbe();
    const P = S.probe, runs = [];
    for (let i = 0; i < P.contacts; i++) {
      const c = contactCcf(i);
      const s = sampleAt(c[0], c[1], c[2]);
      const lam = s.lam ? lamByCode(s.lam) : null;
      const st = allenStruct(s.allen);
      const name = lam ? lam.label : (st.acronym || 'outside');
      const key = lam ? lam.key : null;
      const last = runs[runs.length - 1];
      if (last && last.name === name) last.to = i + 1;
      else runs.push({ from: i + 1, to: i + 1, name, key, full: lam ? lam.name : st.name });
    }
    return runs;
  }
  const contactLayers = () => { computeProbe(); const out = []; for (let i = 0; i < S.probe.contacts; i++) { const c = contactCcf(i); const s = sampleAt(c[0], c[1], c[2]); const l = s.lam ? lamByCode(s.lam) : null; out.push(l ? l.key : ''); } return out; };
  function renderProbe(card) {
    const P = computeProbe();
    card.appendChild(el('div', { class: 'sh-kicker', text: 'Probe placement · no recording attached' }));
    card.appendChild(el('h2', { text: 'Linear probe, ' + P.contacts + ' contacts' }));
    const f = (label, key, step, unit) => el('label', { class: 'sh-coord' }, [el('span', { text: label }),
      el('input', { type: 'number', step, value: P[key], onchange: (e) => { P[key] = +e.target.value; store.set({ probe: probeSave() }); syncProbe(); showCard({ type: 'probe' }); } }),
      el('small', { text: unit })]);
    card.appendChild(el('div', { class: 'sh-coords' }, [f('AP', 'ap', 0.05, 'mm from bregma'), f('ML', 'ml', 0.05, 'mm, + right'), f('Depth', 'depth', 0.05, 'mm along the shank'),
      f('ML angle', 'angML', 1, '° (tip lateral +)'), f('AP angle', 'angAP', 1, '° (tip posterior +)')]));
    card.appendChild(el('p', { class: 'sh-small', text: 'Tip at CCF ' + P.tip.map((x) => Math.round(x)).join(', ') + ' µm. Depth is from the brain surface where the shank enters (approximate: the CCF is an average brain, not stereotaxic). Contacts every ' + P.pitch + ' µm; contact 1 is nearest the tip. Drag the tip on a section to move it.' }));
    card.appendChild(el('div', { class: 'sh-links' }, [
      el('button', { class: 'mini', text: S.probe.on ? 'Hide the probe' : 'Show the probe', onclick: () => { showProbe(!S.probe.on); renderBar(); showCard({ type: 'probe' }); } }),
      el('button', { class: 'mini', text: 'Section down the probe', onclick: sliceDownProbe }),
      el('button', { class: 'mini', text: 'Model DS1 here', onclick: () => playEvent('ds1') }),
      el('button', { class: 'mini', text: 'Model DS2 here', onclick: () => playEvent('ds2') }),
    ]));
    card.appendChild(el('h3', { text: 'Which contacts sit in which layer' }));
    card.appendChild(el('div', { class: 'sh-probe-table' }, probeRuns().slice().reverse().map((r) => el('div', {
      onpointerenter: () => r.key && setHover({ type: 'lamina', key: r.key }, 'card'), onpointerleave: () => setHover(null, 'card') }, [
      el('span', { class: 'ch', text: r.from === r.to ? 'ch ' + r.from : 'ch ' + r.from + '–' + r.to }),
      r.key ? el('span', { class: 'sh-sw sq', style: 'background:' + (S.kb.lamina_colors[r.key] || '#888') }) : el('span', { class: 'sh-sw sq', style: 'background:var(--line)' }),
      el('span', { text: r.name + (r.full ? ' · ' + r.full : '') }),
    ]))));
  }

  /* ==================================================================
     The crowd: one dot per cell
     ================================================================== */
  function ensureCrowd() {
    if (S.crowdMade || !S.crowd || !S.stage || !S.volumesUp) return;
    S.crowdMade = true;
    setTimeout(makeCrowd, 60);
  }
  function makeCrowd() {
    const H = S.blobs['hip20.shb.gz'], F = S.blobs['fine10.shb.gz'];
    const spec = (S.kb.crowd || {}).kinds || [];
    if (!H || !spec.length) return;
    const codeOf = (k) => (lamOf(k) || {}).code;
    const kindOfCode = new Map();
    spec.forEach((s, i) => s.layers.forEach((k) => { const c = codeOf(k); if (c) { if (!kindOfCode.has(c)) kindOfCode.set(c, []); kindOfCode.get(c).push(i); } }));
    const lists = spec.map(() => ({ fine: [], hip: [] }));
    const fo = F ? F.header.origin_um : null, fs = F ? F.header.shape : null;
    const inFine = (ap, dv, ml) => F && ap >= fo[0] && dv >= fo[1] && ml >= fo[2] && ap < fo[0] + fs[0] * 10 && dv < fo[1] + fs[1] * 10 && ml < fo[2] + fs[2] * 10;
    if (F) {
      const L = F.arrays.labels;
      for (let n = 0; n < L.length; n++) { const ks = kindOfCode.get(L[n]); if (ks) for (const k of ks) lists[k].fine.push(n); }
    }
    const ho = H.header.origin_um, hs = H.header.arrays[0].shape, LH = H.arrays.labels;
    for (let i = 0; i < hs[0]; i++) for (let j = 0; j < hs[1]; j++) for (let k = 0; k < hs[2]; k++) {
      const n = (i * hs[1] + j) * hs[2] + k;
      const ks = kindOfCode.get(LH[n]);
      if (!ks) continue;
      if (inFine(ho[0] + i * 20 + 10, ho[1] + j * 20 + 10, ho[2] + k * 20 + 10)) continue;
      for (const kk of ks) lists[kk].hip.push(n);
    }
    let seed = 12345;
    const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    const pos = [], col = [], size = [];
    let total = 0;
    spec.forEach((s, si) => {
      const vol = lists[si].fine.length * 1000 + lists[si].hip.length * 8000;
      if (!vol) return;
      const per = s.total ? s.total / vol : s.per_um3;
      const c = hexRgb((cellOf(s.key) || {}).color || '#aaa').map((x) => x / 255);
      const put = (ap, dv, ml) => {
        pos.push((ml - 5700) / 1000, (4000 - dv) / 1000, (ap - 6600) / 1000);
        col.push(c[0] * 0.85, c[1] * 0.85, c[2] * 0.85);
        size.push(s.soma_um / 1000);
        total++;
      };
      for (const n of lists[si].fine) {
        let m = per * 1000; let cnt = Math.floor(m); if (rnd() < m - cnt) cnt++;
        if (!cnt) continue;
        const i = Math.floor(n / (fs[1] * fs[2])), j = Math.floor(n / fs[2]) % fs[1], k = n % fs[2];
        for (let q = 0; q < cnt; q++) put(fo[0] + (i + rnd()) * 10, fo[1] + (j + rnd()) * 10, fo[2] + (k + rnd()) * 10);
      }
      for (const n of lists[si].hip) {
        let m = per * 8000; let cnt = Math.floor(m); if (rnd() < m - cnt) cnt++;
        if (!cnt) continue;
        const i = Math.floor(n / (hs[1] * hs[2])), j = Math.floor(n / hs[2]) % hs[1], k = n % hs[2];
        for (let q = 0; q < cnt; q++) put(ho[0] + (i + rnd()) * 20, ho[1] + (j + rnd()) * 20, ho[2] + (k + rnd()) * 20);
      }
    });
    S.crowdN = total;
    S.stage.setCrowd({ pos: new Float32Array(pos), col: new Float32Array(col), size: new Float32Array(size) });
    S.stage.showCrowd(S.crowd);
  }

  /* ==================================================================
     Rides
     ================================================================== */
  async function startRide(key, o) {
    o = o || {};
    if (!o.fromTour) endTour();
    stopPlay(true);
    const ok = await need(['three', 'mesh_brain.shb.gz', 'mesh_hpf.shb.gz', 'mesh_lamina.shb.gz', 'cells.shb.gz', 'rides.json', 'brain50.shb.gz', 'hip20.shb.gz', 'fine10.shb.gz'],
      'Getting the ride ready', 'The cells, where they touch, and the sections the cut will paint.');
    if (!ok) return;
    const ride = (S.rides.rides || []).find((r) => r.key === key);
    if (!ride) return;
    if (S.mode !== '3d') await setMode('3d');
    if (S.level === 'brain') await setLevel('hpf');
    S.story = true;
    renderBar();
    S.play = { kind: 'ride', key, ride, i: 0, fromTour: o.fromTour || null, sink: null, source: null };
    if (ride.kind === 'event') {
      const ev = BARRY.shPhys.EVENTS[key];
      if (ev) { S.play.event = key; }
    }
    S.focus = { cells: new Set(), regionKeys: new Set(), conns: new Set(), layers: new Set() };
    S.stage.focus(null);
    showExtras();
    showTip(null);
    S.stage.ride(ride.steps, {
      onStep: (i, st) => onRideStep(i, st),
      onSynapse: (i, st) => showInset(st),
      onDone: () => onRideDone(),
    });
    renderSteps();
    renderRail();
  }
  function onRideStep(i, st) {
    if (!S.play || S.play.kind !== 'ride') return;
    S.play.i = i;
    S.play.step = st;
    // the schematic lights what is being crossed
    const f = { cells: new Set(), regionKeys: new Set(), conns: new Set(), layers: new Set() };
    if (st.conn) addConn(f, connOf(st.conn));
    const t = st.cell ? typeOfInst(st.cell) : null;
    if (t && cellOf(t)) { f.cells.add(t); f.regionKeys.add(cellOf(t).region); }
    if (st.layer) f.layers.add(st.layer);
    ((st.also || {}).regions || []).forEach((r) => f.regionKeys.add(r));
    S.focus = f;
    const here = st.conn ? { type: 'conn', key: st.conn } : t ? { type: 'cell', key: t } : null;
    if (here) { if (S.here && (S.here.key !== here.key)) { S.trail.push(S.here); if (S.trail.length > 8) S.trail.shift(); } S.here = t ? { type: 'cell', key: t } : here; }
    if (st.kind === 'sink') { S.play.sink = (st.also || {}).sink || []; S.play.source = (st.also || {}).source || []; }
    else if (st.kind !== 'burst') { S.play.sink = null; S.play.source = null; }
    if (st.kind !== 'synapse') hideInset();
    applySchem();
    applyHighlights();
    renderSteps();
    if (st.kind === 'sink' && S.play.event) showEventPanel(S.play.event);
  }
  function onRideDone() {
    if (!S.play || S.play.kind !== 'ride') return;
    S.play.done = true;
    hideInset();
    renderSteps();
    if (S.rec && S.rec.untilDone) stopRecord();
    if (S.play.fromTour) setTimeout(() => { const tour = S.play && S.play.fromTour; if (tour) resumeTour(tour); }, 900);
  }
  function stopPlay(quiet) {
    if (!S.play) return;
    const p = S.play;
    if (p.kind === 'ride' && S.stage) {
      S.stage.stopRide(true);
      // back out to where you were looking from, so the end of a ride is not a lost camera
      if (!quiet && S.mode === '3d') S.stage.setLevel(S.level);
    }
    if (p.kind === 'event' || p.event) stopEventAnim();
    S.play = null;
    hideInset();
    // an event's model panel belongs to the event: give the card back
    if ($('.sh-card .sh-lam') && !(S.quiz && S.quiz.open)) showCard(S.sel);
    $('.sh-ridetag') && $('.sh-ridetag').remove();
    showExtras();
    if (!quiet) {
      S.focus = S.sel ? focusFor(S.sel) : null;
      applyFocusAll();
      applyCut();
      renderSteps();
      renderRail();
    }
  }
  function updateRideTag() {
    const rs = S.stage && S.stage.rideState;
    let tag = $('.sh-ridetag');
    if (!rs || !rs.head || !S.play || !S.play.step) { if (tag) tag.remove(); return; }
    const st = S.play.step;
    if (!tag) { tag = el('div', { class: 'sh-ridetag' }); $('.sh-stage').appendChild(tag); }
    const p = S.stage.project(rs.head);
    const t = st.cell ? typeOfInst(st.cell) : null;
    const inst = st.cell ? instOf(st.cell) : null;
    tag.textContent = (t ? (cellOf(t) || {}).short + (inst && inst.source && inst.source.neuron_name ? ' ' + inst.source.neuron_name : '') : 'drawn path') + (st.layer ? ' · ' + ((lamOf(st.layer) || {}).label || st.layer) : '');
    tag.style.transform = 'translate(' + Math.round(p[0] + 14) + 'px,' + Math.round(p[1] - 26) + 'px)';
  }
  /* the synapse close-up */
  function showInset(st) {
    const syn = S.rides && S.rides.synapses[st.synapse];
    const box = $('.sh-inset');
    if (!syn) { box.style.display = 'none'; return; }
    box.innerHTML = '';
    const pre = (S.play && S.play.ride && S.play.ride.steps[Math.max(0, S.play.i - 1)] || {}).cell;
    const preC = pre ? (cellOf(typeOfInst(pre)) || {}).color : '#d16ba5';
    const postC = st.cell ? (cellOf(typeOfInst(st.cell)) || {}).color : '#2a9d8f';
    box.appendChild(el('div', { class: 'sh-inset-art', html: synapseArt(st.synapse, preC, postC) }));
    box.appendChild(el('div', { class: 'sh-inset-title', text: syn.title }));
    box.appendChild(el('div', { class: 'sh-inset-say', text: syn.say }));
    box.appendChild(citeChips(syn.refs));
    box.style.display = 'block';
    box.classList.remove('sh-pop'); void box.offsetWidth; box.classList.add('sh-pop');
  }
  function hideInset() { const b = $('.sh-inset'); if (b) b.style.display = 'none'; }
  /* Close-up drawings: schematic, but in the right proportions (the giant
     mossy bouton dwarfs a Schaffer bouton; inhibitory synapses sit on the
     shaft, the soma or the axon initial segment). */
  function synapseArt(type, pre, post) {
    const ink = 'var(--text-2)';
    const ves = (cx, cy, r, n, seed) => { let s = seed || 3, out = ''; for (let i = 0; i < n; i++) { s = (s * 9301 + 49297) % 233280; const a = s / 233280 * 6.283; s = (s * 9301 + 49297) % 233280; const d = Math.sqrt(s / 233280) * r; out += `<circle cx="${(cx + Math.cos(a) * d).toFixed(1)}" cy="${(cy + Math.sin(a) * d).toFixed(1)}" r="2.1" fill="none" stroke="${ink}" stroke-width="0.9"/>`; } return out; };
    const shaft = `<path d="M10,96 L250,96" stroke="${post}" stroke-width="18" stroke-linecap="round" fill="none" opacity="0.9"/>`;
    const spine = (x) => `<path d="M${x},88 L${x},62" stroke="${post}" stroke-width="5" fill="none"/><ellipse cx="${x}" cy="54" rx="11" ry="9" fill="${post}"/>`;
    const small = (x, y) => `<ellipse cx="${x}" cy="${y}" rx="15" ry="12" fill="${pre}" opacity="0.9"/>${ves(x, y - 2, 8, 9, x)}<path d="M${x - 8},${y + 11} L${x + 8},${y + 11}" stroke="${ink}" stroke-width="2.4"/>`;
    const wrap = (s) => `<svg viewBox="0 0 260 130" width="100%" height="118" xmlns="http://www.w3.org/2000/svg">${s}</svg>`;
    if (type === 'mf_giant' || type === 'mf_thorn_mc') {
      return wrap(`<path d="M10,104 L250,104" stroke="${post}" stroke-width="22" stroke-linecap="round" fill="none" opacity="0.9"/>`
        + [90, 118, 146, 172].map((x, i) => `<path d="M${x},94 L${x + (i % 2 ? 4 : -4)},74" stroke="${post}" stroke-width="5"/><circle cx="${x + (i % 2 ? 4 : -4)}" cy="${68 - (i % 2) * 6}" r="8" fill="${post}"/>`).join('')
        + `<path d="M58,70 C58,18 210,6 214,62 C216,82 196,74 186,86 C170,70 98,72 78,88 C64,90 58,84 58,70 Z" fill="${pre}" opacity="0.88"/>`
        + ves(136, 40, 34, 46, 7)
        + [96, 122, 150, 176].map((x) => `<path d="M${x - 6},64 L${x + 6},62" stroke="${ink}" stroke-width="2.4"/>`).join('')
        + `<text x="236" y="24" text-anchor="end" font-size="10" fill="${ink}">4-10 µm</text>`);
    }
    if (type === 'inh_peri') {
      return wrap(`<circle cx="130" cy="66" r="34" fill="${post}" opacity="0.9"/>` + [0, 1, 2, 3, 4, 5].map((i) => {
        const a = i / 6 * 6.283; const x = 130 + Math.cos(a) * 44, y = 66 + Math.sin(a) * 44;
        return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="9" fill="${pre}"/>`; }).join('')
        + `<text x="130" y="122" text-anchor="middle" font-size="10" fill="${ink}">GABA on the soma</text>`);
    }
    if (type === 'inh_ais') {
      return wrap(`<circle cx="60" cy="40" r="26" fill="${post}" opacity="0.9"/><path d="M80,56 L230,112" stroke="${post}" stroke-width="7"/>`
        + [0, 1, 2, 3, 4].map((i) => { const x = 102 + i * 24, y = 64 + i * 9; return `<circle cx="${x}" cy="${y - 11}" r="6.5" fill="${pre}"/>`; }).join('')
        + `<path d="M96,40 L222,86" stroke="${pre}" stroke-width="2" fill="none"/><text x="236" y="126" text-anchor="end" font-size="10" fill="${ink}">axon initial segment</text>`);
    }
    if (type === 'inh_dend') {
      return wrap(shaft + `<ellipse cx="130" cy="74" rx="16" ry="11" fill="${pre}"/>` + ves(130, 72, 8, 8, 5)
        + `<path d="M120,85 L140,85" stroke="${ink}" stroke-width="1.6"/><text x="130" y="124" text-anchor="middle" font-size="10" fill="${ink}">GABA on the shaft</text>`);
    }
    return wrap(shaft + spine(130) + small(130, 30) + `<text x="236" y="124" text-anchor="end" font-size="10" fill="${ink}">about 1 µm</text>`);
  }

  /* ==================================================================
     Events: model laminar profiles
     ================================================================== */
  async function playEvent(key, o) {
    o = o || {};
    if (!o.fromTour) endTour();
    const ev = BARRY.shPhys.EVENTS[key];
    if (!ev) return;
    const ok = await need(['brain50.shb.gz', 'hip20.shb.gz', 'fine10.shb.gz'], 'Getting the layers ready', 'The probe reads the layers it crosses.');
    if (!ok) return;
    // DS1/DS2 in 3D ride the real cells too
    if ((key === 'ds1' || key === 'ds2') && S.mode === '3d' && !o.modelOnly && S.stage) { await startRide(key, o); S.play && (S.play.event = key); showEventPanel(key); return; }
    stopPlay(true);
    if (!S.probe.on) { S.probe.on = true; syncProbe(); renderBar(); }
    const sink = [], source = [];
    ev.comps.forEach((c) => (c.amp < 0 ? sink : source).push(...c.layers));
    S.play = { kind: 'event', key, ev, sink: [...new Set(sink)], source: [...new Set(source)].filter((k) => !sink.includes(k)), fromTour: o.fromTour || null };
    applyHighlights();
    applySchem();
    if (S.stage && S.mode === '3d') {
      (ev.cells || []).forEach((k, i) => setTimeout(() => S.stage && S.stage.pulseCell(k, 1400), i * 500));
    }
    showEventPanel(key);
    renderSteps();
    renderRail();
  }
  let evAnim = 0;
  function showEventPanel(key) {
    const ev = BARRY.shPhys.EVENTS[key];
    const layers = contactLayers();
    const z = layers.map((_, i) => S.probe.first + i * S.probe.pitch);
    const model = BARRY.shPhys.compute(key, layers, z);
    S.eventModel = model;
    const card = $('.sh-card');
    card.innerHTML = '';
    card.appendChild(el('div', { class: 'sh-kicker', text: 'Model · not a recording' }));
    card.appendChild(el('h2', { text: ev.label + ' on the probe\'s 64 contacts' }));
    card.appendChild(el('p', {}, [document.createTextNode(ev.say + ' '), citeChips(ev.refs)]));
    const cv = el('canvas', { class: 'sh-lam' });
    card.appendChild(cv);
    card.appendChild(el('div', { class: 'sh-lam-legend' }, [el('span', { class: 'sink', text: 'sink' }), el('span', { class: 'source', text: 'source' }),
      el('span', { text: 'lines: potential (every other contact); top = shallowest contact' })]));
    card.appendChild(el('p', { class: 'sh-small', text: 'Currents placed in the layers the literature names, read by each contact\'s layer; potentials from the laminar disc model (Nicholson & Freeman 1975). Shape, not amplitude. Replace with your recordings when they are linked.' }));
    card.appendChild(el('div', { class: 'sh-links' }, Object.entries(BARRY.shPhys.EVENTS).map(([k, e]) =>
      el('button', { class: 'pill' + (k === key ? ' active' : ''), text: e.label, onclick: () => playEvent(k, { modelOnly: true }) }))));
    stopEventAnim();
    const t0 = performance.now(), loop = ev.ms > 300 ? 4000 : 2600;
    const draw = (now) => {
      if (!cv.isConnected) { evAnim = 0; return; }
      const cur = reducedMotion() ? ev.ms : ((now - t0) % loop) / loop * ev.ms;
      BARRY.shPhys.draw(cv, model, { cursor: cur, layerColors: S.kb.lamina_colors, labelOf: (k) => (lamOf(k) || {}).label, ink: tok('--text-2', '#888'), accent: tok('--accent', '#e5a823'), font: tok('--sans', 'sans-serif') });
      if (!reducedMotion()) evAnim = requestAnimationFrame(draw);
    };
    evAnim = requestAnimationFrame(draw);
  }
  function stopEventAnim() { if (evAnim) cancelAnimationFrame(evAnim); evAnim = 0; }
  function renderEventCard(card) { if (S.play && S.play.kind === 'event') showEventPanel(S.play.key); else renderAbout(card); }

  /* ==================================================================
     Tours
     ================================================================== */
  function menuTours(anchor) {
    const ts = BARRY.shLearn.tours(S.kb, { probeAp: 5400 - S.probe.ap * 1000 });
    const pathways = S.kb.pathways || [];
    const m = el('div', { class: 'sh-menu', role: 'menu' }, [
      el('div', { class: 'sh-kicker', text: 'Guided tours' }),
      ...ts.map((t) => el('button', { class: 'sh-menu-item', role: 'menuitem', onclick: () => { close(); startTour(t.key); } },
        [el('b', { text: t.label }), el('small', { text: t.blurb })])),
      el('div', { class: 'sh-kicker', text: 'Pathways in the schematic' }),
      ...pathways.map((p) => el('button', { class: 'sh-menu-item', role: 'menuitem', onclick: () => { close(); startPath(p.key); } },
        [el('b', { text: p.label }), el('small', { text: p.blurb })])),
    ]);
    const r = anchor.getBoundingClientRect();
    m.style.top = (r.bottom + 6) + 'px';
    m.style.left = Math.max(8, r.right - 340) + 'px';
    document.body.appendChild(m);
    const close = () => { m.remove(); document.removeEventListener('pointerdown', away, true); };
    const away = (e) => { if (!m.contains(e.target)) close(); };
    setTimeout(() => document.addEventListener('pointerdown', away, true), 0);
  }
  function startTour(key) {
    stopPlay(true);
    const ts = BARRY.shLearn.tours(S.kb, { probeAp: 5400 - S.probe.ap * 1000 });
    const t = ts.find((x) => x.key === key);
    if (!t) return;
    let beats = t.beats;
    if (key === 'probe') {
      if (!S.blobs['brain50.shb.gz']) { need(['brain50.shb.gz', 'hip20.shb.gz', 'fine10.shb.gz'], 'Getting the layers ready', '').then(() => startTour(key)); return; }
      beats = [{ title: 'The probe', say: 'A 64-contact linear probe, 20 µm apart, from the surgery coordinates in its card. Each stop is a run of contacts in one layer, from the deepest up.', do: [['probe', 'show'], ['downProbe']] }]
        .concat(BARRY.shLearn.probeBeats(probeRuns(), S.kb));
    }
    S.tour = { key, label: t.label, beats, i: 0 };
    runBeat();
  }
  async function runBeat() {
    const T = S.tour;
    if (!T) return;
    const b = T.beats[T.i];
    stopPlay(true);                   // whatever the last beat started
    renderSteps();
    for (const a of b.do || []) { if (S.tour !== T) return; await doAction(a); }
    renderSteps();
  }
  function resumeTour() { if (S.tour) renderSteps(); }
  function endTour() { if (S.tour) { S.tour = null; renderSteps(); } }
  async function doAction([op, arg]) {
    if (op === 'mode') await setMode(arg);
    else if (op === 'level') await setLevel(arg);
    else if (op === 'slice') { S.slice.plane = arg.plane || 'coronal'; S.slice.pos = arg.pos || S.slice.pos; S.slice.tiltA = 0; S.slice.tiltB = 0; if (S.mode !== 'slice') await setMode('slice'); sliceZoom(arg.zoom || 'hippocampus'); renderBar(); }
    else if (op === 'layers') { S.focus = { cells: new Set(), regionKeys: new Set(), conns: new Set(), layers: new Set(arg) }; applyFocusAll(); }
    else if (op === 'schem') { S.schemPick = arg; renderRail(); }
    else if (op === 'select') select(arg);
    else if (op === 'event') await playEvent(arg, { fromTour: S.tour && S.tour.key, modelOnly: S.mode !== '3d' });
    else if (op === 'probe') showProbe(true);
    else if (op === 'downProbe') sliceDownProbe();
    else if (op === 'ride') await startRide(arg, { fromTour: S.tour && S.tour.key });
    else if (op === 'focus') { if (S.stage) S.stage.focus({ cells: new Set(arg), regions: new Set(), layers: new Set() }); }
    else if (op === 'cell') { select({ type: 'cell', key: arg }); await flyToCell(instancesOfType(arg)[0]); }
    else if (op === 'probeRun') {
      if (S.mode !== 'slice') await setMode('slice');
      if (arg.key) { S.focus = { cells: new Set(), regionKeys: new Set(), conns: new Set(), layers: new Set([arg.key]) }; applyFocusAll(); }
      const mid = contactCcf(Math.round((arg.from + arg.to) / 2) - 1);
      if (S.slice.C) { S.slice.C = mid; pushSlice(); }
    }
  }
  /* the old region-level pathways: hop by hop in the schematic */
  function startPath(key) {
    stopPlay(true);
    endTour();
    const p = (S.kb.pathways || []).find((x) => x.key === key);
    if (!p) return;
    S.play = { kind: 'path', key, path: p, i: 0 };
    showHop();
  }
  function showHop() {
    const P = S.play;
    const hop = P.path.hops[P.i];
    const f = { cells: new Set(), regionKeys: new Set(), conns: new Set(), layers: new Set() };
    if (hop.via) addConn(f, connOf(hop.via));
    if (hop.at) { if (cellOf(hop.at)) { f.cells.add(hop.at); f.regionKeys.add(cellOf(hop.at).region); } else f.regionKeys.add(hop.at); }
    S.focus = f;
    if (hop.via) { S.sel = { type: 'conn', key: hop.via }; showCard(S.sel); }
    else if (hop.at) { S.sel = cellOf(hop.at) ? { type: 'cell', key: hop.at } : { type: 'region', key: hop.at }; showCard(S.sel); }
    applyFocusAll();
    renderSteps();
    renderRail();
  }

  /* ==================================================================
     The step bar
     ================================================================== */
  function renderSteps() {
    const bar = $('.sh-steps');
    if (!bar || !S.kb) return;
    bar.innerHTML = '';
    const row = el('div', { class: 'sh-steps-row' });
    row.appendChild(el('span', { class: 'sh-kicker', text: 'Ride' }));
    ((S.rides && S.rides.rides) || [])
      .filter((r) => r.kind !== 'event').forEach((r) => row.appendChild(el('button', { class: 'pill' + (S.play && S.play.kind === 'ride' && S.play.key === r.key ? ' active' : ''), text: r.label, title: r.blurb || '',
        'aria-pressed': String(!!(S.play && S.play.key === r.key)), onclick: () => (S.play && S.play.key === r.key ? stopPlay() : startRide(r.key)) })));
    row.appendChild(el('span', { class: 'sh-kicker', text: 'Play', style: 'margin-left:10px' }));
    Object.entries(BARRY.shPhys.EVENTS).forEach(([k, e]) => row.appendChild(el('button', { class: 'pill sh-ev ' + e.kind + (S.play && S.play.key === k ? ' active' : ''), text: e.label,
      title: e.say, 'aria-pressed': String(!!(S.play && S.play.key === k)), onclick: () => (S.play && S.play.key === k ? stopPlay() : playEvent(k)) })));
    bar.appendChild(row);
    const P = S.play;
    if (S.tour) {
      // a tour owns the bar; a ride or event it started gets compact controls
      const T = S.tour, b = T.beats[T.i];
      const cap = el('div', { class: 'sh-caption' });
      cap.appendChild(el('span', { class: 'sh-step', text: T.label + ' · ' + (T.i + 1) + ' / ' + T.beats.length }));
      const say = el('div', { class: 'sh-say' }, [el('b', { text: b.title + '. ' }), document.createTextNode(b.say || '')]);
      if (P && P.kind === 'ride' && P.step) say.appendChild(el('div', { class: 'sh-small' }, [el('b', { text: P.step.title + ': ' }), document.createTextNode(P.step.say || '')]));
      cap.appendChild(say);
      const ctl = el('div', { class: 'sh-ctl' });
      if (P && P.kind === 'ride') {
        const rs = S.stage && S.stage.rideState;
        ctl.appendChild(el('button', { class: 'btn ghost sm', text: rs && rs.paused ? 'Play' : 'Pause', onclick: () => { S.stage.pauseRide(); renderSteps(); } }));
      }
      ctl.appendChild(el('button', { class: 'btn ghost sm', text: 'Back', disabled: T.i <= 0, onclick: () => { T.i--; runBeat(); } }));
      ctl.appendChild(el('button', { class: 'btn sm', text: T.i >= T.beats.length - 1 ? 'Finish' : 'Next', onclick: () => { if (T.i >= T.beats.length - 1) { endTour(); stopPlay(); } else { T.i++; runBeat(); } } }));
      ctl.appendChild(el('button', { class: 'btn ghost sm', text: 'End tour', onclick: () => { endTour(); stopPlay(); } }));
      cap.appendChild(ctl);
      bar.appendChild(cap);
      return;
    }
    if (!P) return;
    const cap = el('div', { class: 'sh-caption' });
    if (P.kind === 'ride') {
      const st = P.step || P.ride.steps[0];
      const n = P.ride.steps.length;
      cap.appendChild(el('div', { class: 'sh-dots' }, P.ride.steps.map((s, i) => el('i', { class: (i < P.i ? 'done' : i === P.i ? 'now' : '') + ' ' + s.kind, title: s.title }))));
      const txt = el('div', { class: 'sh-say' }, [el('b', { text: st.title }), document.createTextNode(st.say ? ' ' + st.say + ' ' : ' '), citeChips(st.cite)]);
      if (st.drawn) txt.appendChild(el('span', { class: 'sh-tag drawn', text: 'Drawn path' }));
      cap.appendChild(txt);
      if (st.lab) cap.appendChild(el('div', { class: 'sh-lab', text: st.lab }));
      const clock = el('div', { class: 'sh-clock', title: st.velocity ? st.velocity.source : ((S.rides.delay[st.kind] || {}).source || '') }, [
        el('span', { class: 'big', text: 't = ' + (st.ms ? st.ms[0].toFixed(1) : '0.0') + ' ms' }),
        el('small', { text: st.velocity ? '+' + st.ms[1].toFixed(1) + ' ms: ' + (st.len_um / 1000).toFixed(2) + ' mm at ' + st.velocity.m_per_s + ' m/s'
          : st.ms && st.ms[1] ? '+' + st.ms[1].toFixed(1) + ' ms' : '' }),
      ]);
      cap.appendChild(clock);
      const rs = S.stage && S.stage.rideState;
      cap.appendChild(el('div', { class: 'sh-ctl' }, [
        el('button', { class: 'btn ghost sm', text: '◀', title: 'Back a step (←)', onclick: () => S.stage.stepRide(-1) }),
        el('button', { class: 'btn ghost sm', text: rs && rs.paused ? 'Play' : 'Pause', title: 'Space', onclick: () => { S.stage.pauseRide(); renderSteps(); } }),
        el('button', { class: 'btn ghost sm', text: '▶', title: 'Next step (→)', onclick: () => S.stage.stepRide(1) }),
        rs && rs.manual ? el('button', { class: 'btn ghost sm', text: 'Follow (F)', onclick: () => { S.stage.reframe(); renderSteps(); } }) : null,
        el('button', { class: 'btn ghost sm', text: S.rec ? 'Stop recording' : 'Record ride', onclick: () => (S.rec ? stopRecord() : recordRide()) }),
        el('button', { class: 'btn sm', text: P.done ? 'Done' : 'End', onclick: () => stopPlay() }),
      ]));
    } else if (P.kind === 'event') {
      cap.appendChild(el('div', { class: 'sh-say' }, [el('span', { class: 'sh-tag model', text: 'Model' }), el('b', { text: ' ' + P.ev.label + '. ' }), document.createTextNode(P.ev.say + ' '), citeChips(P.ev.refs)]));
      cap.appendChild(el('div', { class: 'sh-ctl' }, [el('button', { class: 'btn ghost sm', text: 'Again', onclick: () => playEvent(P.key, { modelOnly: true }) }),
        el('button', { class: 'btn sm', text: 'Done', onclick: () => stopPlay() })]));
    } else if (P.kind === 'path') {
      const hop = P.path.hops[P.i];
      cap.appendChild(el('span', { class: 'sh-step', text: P.path.label + ' · ' + (P.i + 1) + ' / ' + P.path.hops.length }));
      cap.appendChild(el('div', { class: 'sh-say', text: hop.say }));
      cap.appendChild(el('div', { class: 'sh-ctl' }, [
        el('button', { class: 'btn ghost sm', text: 'Back', disabled: P.i <= 0, onclick: () => { P.i--; showHop(); } }),
        el('button', { class: 'btn sm', text: P.i >= P.path.hops.length - 1 ? 'Done' : 'Next', onclick: () => { if (P.i >= P.path.hops.length - 1) stopPlay(); else { P.i++; showHop(); } } }),
      ]));
    }
    bar.appendChild(cap);
  }

  /* ==================================================================
     Quiz
     ================================================================== */
  async function openQuiz() {
    endTour();
    stopPlay();
    let states = {};
    try { const r = await api('/api/seahorse/quiz'); if (r && r.ok) states = r.cards || {}; } catch (e) { /* offline: this session only */ }
    const all = BARRY.shLearn.cards(S.kb);
    S.quiz = { open: true, all, states, q: BARRY.shLearn.queue(all, states), i: 0, answered: null };
    showCard({ type: 'quiz' });
  }
  async function renderQuiz(card) {
    const Q = S.quiz;
    if (!Q) return renderAbout(card);
    Q.open = true;
    const c = Q.q.next[Q.i];
    card.appendChild(el('div', { class: 'sh-kicker', text: 'Quiz · ' + Q.q.due.length + ' due · ' + Q.q.fresh.length + ' new' + (S.lab.me ? ' · ' + S.lab.me : '') }));
    if (!c) {
      card.appendChild(el('h2', { text: 'All done for now' }));
      card.appendChild(el('p', { text: 'Nothing is due. Cards come back on the Anki schedule: a day, a few days, then longer as you get them right.' }));
      card.appendChild(el('button', { class: 'btn sm', text: 'Close', onclick: () => { S.quiz = null; showCard(S.sel); } }));
      return;
    }
    card.appendChild(el('h2', { text: c.prompt }));
    if (!Q.shown) { Q.shown = true; await showQuizVisual(c); }
    const opts = el('div', { class: 'sh-quiz-opts' }, c.options.map((o) => el('button', {
      class: 'sh-quiz-opt' + (Q.answered ? (o === c.answer ? ' right' : o === Q.answered ? ' wrong' : '') : ''), text: o, disabled: !!Q.answered,
      onclick: () => { Q.answered = o; showCard({ type: 'quiz' }); } })));
    card.appendChild(opts);
    if (Q.answered) {
      const right = Q.answered === c.answer;
      card.appendChild(el('p', { class: right ? 'sh-ok' : 'sh-bad', text: (right ? 'Right. ' : 'Not quite: ' + c.answer + '. ') + (c.explain || '') }));
      const grade = async (g) => {
        const st = BARRY.shLearn.schedule(Q.states[c.id], g);
        Q.states[c.id] = st;
        try { await apiPost('/api/seahorse/quiz', { card: c.id, state: st }); } catch (e) { /* kept for this session */ }
        Q.i++; Q.answered = null; Q.shown = false; S.quizLayer = null; applyHighlights();
        if (Q.i >= Q.q.next.length) { Q.q = BARRY.shLearn.queue(Q.all, Q.states); Q.i = 0; }
        showCard({ type: 'quiz' });
      };
      card.appendChild(el('div', { class: 'sh-links' }, [
        el('button', { class: 'btn ghost sm', text: 'Again (10 min)', onclick: () => grade(0) }),
        el('button', { class: 'btn ghost sm', text: 'Hard', onclick: () => grade(3) }),
        el('button', { class: 'btn sm', text: 'Good', onclick: () => grade(right ? 4 : 3) }),
        el('button', { class: 'btn ghost sm', text: 'Easy', onclick: () => grade(5) }),
      ]));
    }
    card.appendChild(el('button', { class: 'mini', text: 'End quiz', onclick: () => { S.quiz = null; S.quizLayer = null; applyHighlights(); showCard(S.sel); } }));
  }
  async function showQuizVisual(c) {
    const [op, arg] = c.show || [];
    if (op === 'layer') {
      if (S.mode !== 'slice') await setMode('slice');
      S.focus = { cells: new Set(), regionKeys: new Set(), conns: new Set(), layers: new Set() };
      S.quizLayer = arg;
      applyHighlights();
    } else if (op === 'conn') {
      S.focus = focusFor({ type: 'conn', key: arg });
      S.focus.layers = new Set();       // do not give the answer away
      applySchem(); applyStageFocus();
    } else if (op === 'spot' || op === 'cell') {
      await flyToCell(instancesOfType(arg)[0]);
      if (S.stage) S.stage.focus({ cells: new Set(instancesOfType(arg)), regions: new Set(), layers: new Set() });
    } else if (op === 'event') {
      /* shown after answering */
    }
  }

  /* ==================================================================
     Search
     ================================================================== */
  function wireSearch(box) {
    const input = box.querySelector('input'), res = box.querySelector('.sh-search-res');
    let items = [], at = 0;
    const paint = () => {
      res.innerHTML = '';
      res.style.display = items.length ? 'block' : 'none';
      items.forEach((it, i) => res.appendChild(el('button', { class: 'sh-search-item' + (i === at ? ' on' : ''), role: 'option',
        onmousedown: (e) => { e.preventDefault(); go(it); } }, [el('span', { class: 'k', text: it.kind }), el('b', { text: it.label }), el('small', { text: it.sub || '' })])));
    };
    const go = (it) => {
      items = []; paint(); input.value = ''; input.blur();
      const t = it.target;
      if (t.ride) startRide(t.ride);
      else if (t.event) playEvent(t.event);
      else if (t.tour) startTour(t.tour);
      else if (t.view) openView((S.lab.views[t.view] || {}).state);
      else { select(t); goTo(t); }
    };
    input.addEventListener('input', () => {
      const v = input.value.trim();
      const code = parseCode(v);
      if (code) { items = [{ label: 'Open the shared view', sub: 'from a copied code', kind: 'view', target: { code } }]; at = 0; paint(); return; }
      const idx = BARRY.shLearn.index(S.kb, { rides: (S.rides || {}).rides, events: BARRY.shPhys.EVENTS,
        tours: BARRY.shLearn.tours(S.kb, { probeAp: 7300 }), views: Object.entries(S.lab.views || {}).filter(([, x]) => x).map(([id, x]) => ({ id, name: x.name, by: x.by })) });
      items = BARRY.shLearn.search(idx, v);
      at = 0;
      paint();
    });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { at = Math.min(items.length - 1, at + 1); paint(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { at = Math.max(0, at - 1); paint(); e.preventDefault(); }
      else if (e.key === 'Enter' && items[at]) {
        const it = items[at];
        if (it.target.code) { openView(it.target.code); items = []; paint(); input.value = ''; return; }
        go(it);
      } else if (e.key === 'Escape') { items = []; paint(); input.blur(); }
    });
    input.addEventListener('blur', () => setTimeout(() => { items = []; paint(); }, 150));
  }
  /* fly the current view to a selection */
  async function goTo(sel) {
    if (!sel) return;
    if (sel.type === 'cell') return flyToCell(instancesOfType(sel.key)[0]);
    if (sel.type === 'lamina' || sel.type === 'region') {
      if (S.mode === 'schematic') return;
      if (S.mode === '3d' && S.stage) {
        if (S.level === 'brain') await setLevel('hpf');
        const r = sel.type === 'region' ? regionOf(sel.key) : regionOf(regionOfLayer(sel.key));
        const acr = r && (r.allen || [])[0];
        const c = acr && (S.stage.centroid('hpf', acr, true) || S.stage.centroid('brain', acr, true));
        if (c) S.stage.frameOn([{ x: c[0] - 0.6, y: c[1] - 0.5, z: c[2] - 0.6 }, { x: c[0] + 0.6, y: c[1] + 0.5, z: c[2] + 0.6 }]);
      } else if (S.mode === 'slice' && sel.type === 'lamina') {
        // centre the section on the nearest voxel of that layer, on this plane
        const code = (lamOf(sel.key) || {}).code;
        const C = S.slice.C;
        if (!C || !code) return;
        let best = null, bd = 1e18;
        const ax = S.stage.slice;
        for (let du = -2500; du <= 2500; du += 50) for (let dv = -2500; dv <= 2500; dv += 50) {
          const p = [0, 1, 2].map((i) => C[i] + ax.U[i] * du + ax.V[i] * dv);
          if (sampleAt(p[0], p[1], p[2]).lam === code) { const d = du * du + dv * dv; if (d < bd) { bd = d; best = p; } }
        }
        if (best) { S.slice.C = best; pushSlice(); }
      }
    }
  }

  /* ==================================================================
     Figures and video
     ================================================================== */
  function download(url, name) {
    const a = el('a', { href: url, download: name });
    document.body.appendChild(a); a.click(); a.remove();
  }
  const stamp = () => new Date().toISOString().slice(0, 10);
  function saveFigure() {
    if ((S.mode === '3d' || S.mode === 'slice') && S.stage) {
      download(S.stage.snapshot(S.mode === '3d' ? 3 : 2), 'seahorse-' + (S.mode === '3d' ? '3d-' + S.level : S.slice.plane) + '-' + stamp() + '.png');
      toast('Saved a ' + (S.mode === '3d' ? '3' : '2') + '× PNG of the stage.', 'ok');
      return;
    }
    const s = $('.sh-schem-full svg') || $('.sh-rail-schem svg');
    if (!s) return;
    const clone = s.cloneNode(true);
    const all = s.querySelectorAll('*'), call = clone.querySelectorAll('*');
    all.forEach((n, i) => {
      const cs = getComputedStyle(n);
      ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'opacity', 'font-size', 'font-weight', 'font-style', 'font-family'].forEach((p) => call[i].style.setProperty(p, cs.getPropertyValue(p)));
    });
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    clone.querySelectorAll('.flow,.here-pin,.trail').forEach((n) => n.remove());
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml' }));
    download(url, 'seahorse-schematic-' + stamp() + '.svg');
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    toast('Saved the schematic as SVG, with the theme\'s colors written in.', 'ok');
  }
  function captionPainter(ctx, w, h) {
    const P = S.play;
    let title = '', say = '', clock = '';
    if (P && P.kind === 'ride' && P.step) { title = P.step.title; say = P.step.say || ''; clock = P.step.ms ? 't = ' + P.step.ms[0].toFixed(1) + ' ms' : ''; }
    else if (P && P.kind === 'event') { title = P.ev.label + ' (model)'; say = P.ev.say; }
    if (!title) return;
    const pad = 36, boxH = 128;
    ctx.fillStyle = 'rgba(8,10,14,0.66)';
    ctx.fillRect(0, h - boxH, w, boxH);
    ctx.fillStyle = '#fff';
    ctx.font = '600 30px ' + tok('--sans', 'sans-serif');
    ctx.fillText(title, pad, h - boxH + 44);
    ctx.font = '22px ' + tok('--sans', 'sans-serif');
    ctx.fillStyle = 'rgba(255,255,255,0.86)';
    const words = say.split(' ');
    let line = '', y = h - boxH + 82;
    for (const wd of words) {
      if (ctx.measureText(line + wd).width > w - pad * 2 - 220) { ctx.fillText(line, pad, y); line = ''; y += 28; if (y > h - 10) break; }
      line += wd + ' ';
    }
    if (y <= h - 10) ctx.fillText(line, pad, y);
    if (clock) { ctx.font = '600 26px ' + tok('--mono', 'monospace'); ctx.textAlign = 'right'; ctx.fillText(clock, w - pad, h - boxH + 44); ctx.textAlign = 'left'; }
  }
  function toggleRecord() { if (S.rec) stopRecord(); else startRecord(); }
  function startRecord(o) {
    if (!S.stage || S.mode === 'schematic') { toast('Recording works on the 3D and slice views.', 'warn'); return; }
    if (!window.MediaRecorder) { toast('This browser cannot record video.', 'err'); return; }
    S.rec = S.stage.record({ paint: captionPainter, width: 1920, height: 1080, fps: 30 });
    S.rec.untilDone = !!(o && o.untilDone);
    root.classList.add('sh-recording');
    const b = $('.sh-rec-btn'); if (b) b.textContent = 'Stop recording';
    toast('Recording the stage at 1080p' + (S.rec.mime.includes('mp4') ? ' (MP4)' : ' (WebM)') + '.', 'ok');
    renderSteps();
  }
  async function stopRecord() {
    if (!S.rec) return;
    const R = S.rec;
    S.rec = null;
    root.classList.remove('sh-recording');
    const b = $('.sh-rec-btn'); if (b) b.textContent = 'Record';
    const blob = await R.stop();
    const ext = R.mime.includes('mp4') ? 'mp4' : 'webm';
    const url = URL.createObjectURL(blob);
    download(url, 'seahorse-' + (S.play && S.play.key ? S.play.key : 'view') + '-' + stamp() + '.' + ext);
    setTimeout(() => URL.revokeObjectURL(url), 8000);
    toast('Saved the video (' + fmtMB(blob.size) + ', ' + ext.toUpperCase() + ').', 'ok');
    renderSteps();
  }
  async function recordRide() {
    const key = S.play && S.play.key;
    if (!key) return;
    await startRide(key);
    startRecord({ untilDone: true });
  }

  /* ==================================================================
     Keys, theme, life
     ================================================================== */
  function onKey(e) {
    if (BARRY.state.view !== 'seahorse') return;
    if (/^(input|textarea|select)$/i.test((e.target && e.target.tagName) || '')) return;
    const P = S.play;
    if (P && P.kind === 'ride' && S.stage) {
      if (e.key === ' ') { e.preventDefault(); S.stage.pauseRide(); renderSteps(); return; }
      if (e.key === 'ArrowRight') { S.stage.stepRide(1); return; }
      if (e.key === 'ArrowLeft') { S.stage.stepRide(-1); return; }
      if (e.key === 'f' || e.key === 'F') { S.stage.reframe(); renderSteps(); return; }
    }
    if (e.key === 'Escape') { if (S.play) stopPlay(); else select(null); }
  }
  function themeChanged() {
    if (S.stage) { S.stage.theme(stageColors()); applyHighlights(); }
    S.schemShown = null;
    renderRail();
  }

  async function onShow() {
    if (!S.built) build();
    if (!S.kb) {
      try {
        const [kb, checks, manifest, rides] = await Promise.all([getJSON('kb.json'), getJSON('checks.json'),
          getJSON('manifest.json').catch(() => null), getJSON('rides.json').catch(() => null)]);
        S.kb = kb; S.checks = checks; S.manifest = manifest; S.rides = rides;
      } catch (err) {
        $('.sh-stage').appendChild(el('div', { class: 'empty-state', style: 'padding:40px', text: 'Seahorse\'s atlas files are missing (web/seahorse/). Build them with: python tools/seahorse/build.py' }));
        reportClientError('seahorse:kb', err.message, err.stack);
        return;
      }
      loadLab();
    }
    showCard(S.sel);
    renderSteps();
    renderRail();
    // the first open of the day flies in from the whole brain; later opens resume
    const today = new Date().toISOString().slice(0, 10);
    const flyIn = store.get().flyin !== today && S.mode !== 'schematic';
    if (flyIn) {
      store.set({ flyin: today });
      S.mode = '3d';
      const want = S.level === 'brain' ? 'hpf' : S.level;
      S.level = 'brain';
      await setMode('3d');
      setTimeout(() => setLevel(want), reducedMotion() ? 0 : 700);
    } else {
      await setMode(S.mode);
    }
  }
  function onHide() {
    if (S.stage) S.stage.pause();
    if (S.play && S.play.kind === 'ride' && S.stage) S.stage.pauseRide(true);
    stopEventAnim();
  }
  function onReturn() {
    if (S.stage && S.mode !== 'schematic') S.stage.resume();
    if (S.play && S.play.kind === 'event') showEventPanel(S.play.key);
  }

  return { onShow, onHide, onReturn, _state: S };
})();
