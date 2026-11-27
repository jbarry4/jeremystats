/* ==========================================================================
   seahorse.js -- Seahorse: the mouse brain, down to the cells we record.
   Rebuilt 11-24 as one designed thing rather than three rounds of parts.

   The layout, everywhere:
     Header      the mode (3D / Slice / Schematic), search, the quiz, Share.
     Stage       the atlas, full bleed. Only glass panels float on it:
                   navigator  (top left)   how close you are (a ladder) and
                                           where the plane is (cut, section)
                   tools      (top right)  the View sheet (every display
                                           switch, in named states), Recenter
                   dock       (bottom)     what plays: rides, events, tours
                                           and pathways share one transport
     Rail        the inspector: the circuit map that follows you, over one
                 card for whatever is selected.

   Hover   anything, anywhere: a card says what it is and how we know; the
           same thing glows in every view and the rest steps back.
   Click   selects it everywhere and hones the view in on it.
   Rides   a signal along real, touching tracings (rides.json, built by
           tools/seahorse/rides.py), the camera gliding behind it.
   Events  DS1, DS2, sharp-wave ripples and theta as MODEL laminar profiles
           (seahorse_phys.js), played at whatever scale you are looking at.

   Modules: seahorse3d.js (the stage, an ES module loaded on first use),
   seahorse_schem.js (drawings), seahorse_phys.js (event models),
   seahorse_learn.js (tours, quiz, search), seahorse_ui.js (the controls).
   Lab notes, saved views and quiz progress are shared through
   GUI_logs/seahorse (backend/seahorse.py).

   Data: web/seahorse/*, built offline by tools/seahorse/. Nothing is
   fetched from the internet while the tab is open.
   ========================================================================== */
'use strict';

BARRY.views.seahorse = (function () {
  const BASE = 'seahorse/';
  const UI = BARRY.shUI;
  const S = {
    built: false, kb: null, checks: null, manifest: null, rides: null, blobs: {},
    mode: '3d', level: 'hpf', schemPick: 'auto', schemShown: null, schemFullPick: 'circuit', follow: true,
    sel: null, hover: null, focus: null, here: null, trail: [], reach: null,
    slice: { plane: 'coronal', pos: 7300, tiltA: 0, tiltB: 0, C: null, k: 0, layer: 'lamina', cells: true, mini: true },
    probe: { on: false, ap: -1.9, ml: 1.4, depth: 2.3, angML: 0, angAP: 0, contacts: 64, pitch: 20, first: 40, tip: null, dir: null },
    cut: { kind: 'coronal', pos: 8490 }, story: true, exploded: false, crowd: true,
    play: null, tour: null, stage: null, three: null, loading: null, volumesUp: false, crowdMade: false,
    lab: { notes: {}, views: {}, me: '' }, quiz: null, rec: null, railW: null, railSplit: 0.46,
    times: {}, paths: true, labels: true, hist: { list: [], i: -1 }, evSpeed: null, evLoop: true, folds: {},
    tilt: false, rideAuto: false,
    compose: { lec: { on: true, amp: 1, t: 24 }, mec: { on: false, amp: 1, t: 30 }, ca3: { on: false, amp: 1, t: 72 }, ec3: { on: false, amp: 0.8, t: 40 }, ripple: false, theta: false },
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
  /* how long the heavy steps took (ms), for the frame-time sweep: _state.times */
  function timed(name, fn) { const t0 = performance.now(); const r = fn(); S.times[name] = Math.round(performance.now() - t0); return r; }
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
  const isRide = () => !!(S.play && S.play.kind === 'ride');
  const isEvent = () => !!(S.play && S.play.kind === 'event');
  const isStory = () => !!(S.play && S.play.kind === 'story');
  const isSext = () => !!(S.play && S.play.kind === 'sextant');
  /* a ride or a story has the stage to itself: the navigator and the tools step away */
  const cinematic = () => isRide() || isStory() || isSext();
  function regionOfLayer(k) {
    if (!k) return null;
    if (/^(oml|mml|iml|gcl)/.test(k) || k === 'hil') return 'dg';
    if (k.startsWith('ca1')) return 'ca1';
    if (k.startsWith('ca2')) return 'ca2';
    if (k.startsWith('ca3')) return 'ca3';
    if (k === 'sub' || k === 'pros') return 'sub';
    return null;
  }
  function refText(k) { return (S.kb && S.kb.refs[k]) || (S.rides && S.rides.refs[k]) || (BARRY.shStory && BARRY.shStory.REFS[k]) || (BARRY.shSextant && BARRY.shSextant.REFS[k]) || k; }
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
  const VERDICT_WORDS = { supported: 'Supported by data', consistent: 'Placement consistent', weak: 'Weak in data',
    'not seen': 'Not seen in data', cited: 'Cited, not tested', untested: 'Not testable here', error: 'Check failed' };
  function verdictChip(v) {
    const cls = (v.status || 'cited').replace(/\s+/g, '');
    return el('span', { class: 'sh-verdict ' + cls, text: VERDICT_WORDS[v.status] || v.status });
  }
  /* the tab's mark: a filled seahorse, snout left, tail curled */
  const SEAHORSE_SVG = '<svg viewBox="4 2 50 62" style="fill:currentColor;stroke:none"><path fill-rule="evenodd" d="M9 19.6 L19.6 18 C20.6 12.8 24.6 8.8 29.6 8.2 L31.4 3.8 L33.2 8.4 L36.6 6 L36.4 10.4 C39.6 12.2 41.2 15.8 40.8 19.4 L45 20.8 L41.4 23.6 C44.6 26.4 46.8 30.4 46.6 35 L51 37 L46.4 39.2 C45.6 44 42.4 47.8 38 49.8 C35.4 51 34 53.4 34.6 56 C35.6 59.8 33 62.4 29.4 61.8 C25.8 61.2 24.4 57.6 26.4 55.4 C27.8 53.9 30.4 54.6 30.2 56.6 C31.8 55 31.6 51.8 29.6 49.2 C26.4 45 23.6 39.6 24.6 33.6 C25.2 30.4 26.6 28 27.6 25.6 C27.9 24.8 27.7 23.6 26.9 23.2 L19.6 22.4 L9 22.6 C8 22.6 8 19.6 9 19.6 Z M30.6 13.6 a2.3 2.3 0 1 0 .01 0 Z"/></svg>';
  /* CCF to bregma: approximate (CCF is an average brain, not stereotaxic).
     Bregma is taken at CCF AP 5400 um, the midline at ML 5700 um. */
  const apMm = (ap) => (5400 - ap) / 1000;
  const signed = (v, d) => (v < 0 ? '−' : '') + Math.abs(v).toFixed(d);
  const apText = (ap) => 'AP ' + signed(apMm(ap), 2) + ' mm';
  const defaultCutPos = (k) => k === 'coronal' ? 8490 : k === 'sagittal' ? 7700 : 2600;
  const cutLimits = (k) => k === 'coronal' ? [400, 12800] : k === 'sagittal' ? [5700, 11200] : [400, 7600];
  function cutText(k, v) {
    if (k === 'coronal') return apText(v);
    if (k === 'sagittal') return 'ML ' + signed((v - 5700) / 1000, 2) + ' mm';
    return 'DV ' + (v / 1000).toFixed(2) + ' mm';
  }

  /* ==================================================================
     The palette. Regions are clay in 3D and the accent bar of their box in
     the circuit; layers and cells are data (kb.json). One plate: the
     dentate in teal-blues, CA3 brick, CA2 terracotta, CA1 rose, the
     subiculum sand, the entorhinal cortex blue (medial) and orchid
     (lateral), the para-hippocampal rim in lavender and stone.
     ================================================================== */
  const REGION_COLORS = { DG: '#3d9a8f', CA1: '#cc5f80', CA2: '#d98a63', CA3: '#bd4e52', SUB: '#d2b06c', ProS: '#c4a364',
    ENTl: '#c785b0', ENTm: '#5f8acb', PRE: '#a196cc', POST: '#968bc4', PAR: '#8d9ccc', PERI: '#b3b292', ECT: '#a7a68c', VISpor: '#86aab4' };
  /* the circuit's boxes (kb region keys) in the same colors */
  const SCHEM_COLORS = { ctx: '#a9b2ae', per: REGION_COLORS.PERI, por: REGION_COLORS.VISpor, lec2: REGION_COLORS.ENTl, mec2: REGION_COLORS.ENTm,
    ec3: '#9aa3cb', ec5: '#8c95b8', dg: REGION_COLORS.DG, ca3: REGION_COLORS.CA3, ca2: REGION_COLORS.CA2, ca1: REGION_COLORS.CA1,
    sub: REGION_COLORS.SUB, prepar: REGION_COLORS.PRE, subc: '#c4baa5' };
  const regionColor = (k) => SCHEM_COLORS[k] || REGION_COLORS[k] || '#9aa';
  const lamColor = (k) => (S.kb && S.kb.lamina_colors[k]) || '#999';

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
      if (r % 2 === 1) await new Promise((z) => setTimeout(z, 0));     // let the loading window breathe
    }
    bmp.close && bmp.close();
    return vol;
  }

  /* ---------- the loading window ---------- */
  const WHAT = {
    three: ['Waking the renderer', 'three.js, kept on this computer; it draws both the 3D and the sections.'],
    'mesh_brain.shb.gz': ['The whole brain', 'The Allen CCFv3 brain surface.'],
    'mesh_hpf.shb.gz': ['The hippocampal formation', 'Dentate gyrus, CA1 to CA3, subiculum, entorhinal, perirhinal and postrhinal cortex.'],
    'mesh_lamina.shb.gz': ['Its layers, at 10 µm', '28 laminar surfaces from OML1 to OML2 and the CA strata; derived where the Allen atlas has none.'],
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
      el('div', { class: 'sh-load-card sh-glass' }, [
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
        said.textContent = (WHAT[n] || [n])[0] + ' · ' + fmtMB(got) + (tot ? ' of ' + fmtMB(tot) : '');
        paint();
      },
      done(n) { const it = items.find((x) => x.n === n); if (it) it.got = it.bytes; mark(n, 'done'); paint(); },
      building(what) { mark('build', 'now'); said.textContent = what || 'Building…'; bar.style.width = '98%'; pct.textContent = '98%'; },
      close() {
        clearInterval(factTimer); bar.style.width = '100%'; pct.textContent = '100%'; mark('build', 'done');
        setTimeout(() => { node.classList.add('leaving'); setTimeout(() => node.remove(), 220); }, 120);
      },
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
          S.three = await import('./seahorse3d.js?v=7');
          win.bytes(n, 700000, 700000);
        } else if (n === 'rides.json') {
          S.rides = await getJSON('rides.json');
        } else {
          const raw = await fetchBytes(n, (g, t) => win.bytes(n, g, t));
          S.blobs[n] = unpack(await gunzip(raw));
          if (n === 'fine10.shb.gz') { win.building('Unpacking the 10 µm Nissl…'); const t0 = performance.now(); S.blobs[n].nissl = await decodeFine(S.blobs[n]); S.times.decodeFine = Math.round(performance.now() - t0); }
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
    if (S.blobs['mesh_brain.shb.gz'] && !st.has('brain')) timed('addBrain', () => st.addBrain(S.blobs['mesh_brain.shb.gz']));
    if (S.blobs['mesh_hpf.shb.gz'] && !st.has('hpf')) timed('addHpf', () => st.addHpf(S.blobs['mesh_hpf.shb.gz'], (k) => REGION_COLORS[k]));
    if (S.blobs['mesh_lamina.shb.gz'] && !st.has('lamina')) timed('addLamina', () => st.addLamina(S.blobs['mesh_lamina.shb.gz'], S.kb.lamina_colors));
    if (S.blobs['cells.shb.gz'] && !st.has('cells')) {
      timed('addCells', () => st.addCells(S.blobs['cells.shb.gz'], (t) => (cellOf(t) || {}).color || '#ccc'));
      st.setStory(S.story);
      showExtras();
    }
    if (!S.volumesUp && S.blobs['brain50.shb.gz'] && S.blobs['hip20.shb.gz']) {
      S.volumesUp = 'loading';
      const t0 = performance.now();
      await st.setVolumes(volumesForStage());
      S.times.volumes = Math.round(performance.now() - t0);
      st.setLuts(luts());
      S.volumesUp = true;
      applyHighlights();
    }
    makePaths();
  }
  /* The two inputs no single tracing shows, drawn as bundles: the medial
     perforant path (MEC II -> the middle molecular layer) and the
     temporoammonic path (EC III -> CA1 lacunosum-moleculare). Their
     routes are the ones the rides use (rides.json). */
  const DRAWN = { mpp: { ride: 'ds2', color: () => (cellOf('stel') || {}).color || '#3d7dd8' },
                  ta: { ride: 'caside', color: () => '#7a8fd9' } };
  function drawnPath(key) {
    const r = S.rides && (S.rides.rides || []).find((x) => x.key === DRAWN[key].ride);
    const st = r && r.steps.find((s) => s.conn === key && s.path && s.path.length);
    return st ? st.path : null;
  }
  function makePaths() {
    const st = S.stage;
    if (!st || S.pathsMade || !S.rides || !st.has('cells') || !st.setPath) return;
    S.pathsMade = true;
    syncPaths();
  }
  function showPaths(on) {
    S.paths = !!on;
    store.set({ paths: S.paths });
    syncPaths();
  }
  function syncPaths() {
    // shown at the hippocampus and the slab (and in sections), not over the whole brain, and not during a ride (it draws its own)
    const on = S.paths && !isRide() && !(S.mode === '3d' && S.level === 'brain');
    if (S.stage && S.pathsMade) Object.keys(DRAWN).forEach((k) => { const p = drawnPath(k); if (p) S.stage.setPath(k, p, DRAWN[k].color(), on); });
  }
  /* The second LEC cell (AA1002: 230 mm of axon) only joins in when it has
     something to show: the DS1 volley, or when LEC cells are selected. */
  function showExtras() {
    if (!S.stage || !S.stage.has('cells')) return;
    const want = (isRide() && S.play.key === 'ds1') || (S.sel && S.sel.type === 'cell' && S.sel.key === 'fan');
    S.stage.setVisible('cells', 'fan_b', !!want);
  }

  /* ---------- volumes, colors and the CPU sampler ---------- */
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
    for (const l of S.kb.lamina) { const c = hexRgb(lamColor(l.key)); lam.set([c[0], c[1], c[2], 255], l.code * 4); }
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
     The shell: header, stage, rail
     ================================================================== */
  function build() {
    root = document.getElementById('view-seahorse');
    const saved = store.get();
    ['mode', 'level', 'schemPick', 'schemFullPick', 'follow', 'story', 'crowd', 'railW', 'railSplit', 'paths', 'labels', 'evSpeed', 'evLoop', 'folds', 'tilt', 'rideAuto']
      .forEach((k) => { if (saved[k] != null) S[k] = saved[k]; });
    if (saved.slice) Object.assign(S.slice, saved.slice);
    if (saved.probe) Object.assign(S.probe, saved.probe);
    if (saved.cut) Object.assign(S.cut, saved.cut);
    // the header: the mode, search, the quiz, Share
    const head = root.querySelector('.head-actions');
    head.innerHTML = '';
    head.appendChild(el('div', { class: 'sh-head-modes' }, [UI.seg('', [
      ['3d', '3D', 'The brain, the hippocampus and a slab of it, turning in 3D'],
      ['slice', 'Slice', 'Any section through the atlas, smooth at every zoom'],
      ['schematic', 'Schematic', 'The circuit, and the hippocampus by layer']], S.mode, (k) => setMode(k), { aria: 'View' })]));
    const search = el('div', { class: 'sh-search' }, [
      el('label', { class: 'sh-search-box' }, [UI.icon('search'),
        el('input', { type: 'search', placeholder: 'Search the atlas', title: 'Cells, layers, regions, pathways, rides, events, tours, saved views', 'aria-label': 'Search Seahorse', spellcheck: 'false' }),
        el('span', { class: 'sh-kbd', text: '/', title: 'Press / to search' })]),
      el('div', { class: 'sh-search-res', role: 'listbox' }),
    ]);
    head.appendChild(search);
    wireSearch(search);
    head.appendChild(UI.button({ icon: 'quiz', text: 'Quiz', title: 'Quiz cards drawn from the atlas, spaced like Anki', onclick: () => openQuiz() }));
    head.appendChild(UI.button({ icon: 'share', text: 'Share', cls: 'sh-share-btn', title: 'Save this view for the lab, save a figure, record a video',
      onclick: (e) => shareMenu(e.currentTarget) }));
    // the body: stage | divider | rail
    const body = root.querySelector('.sh-body');
    body.innerHTML = '';
    body.appendChild(el('div', { class: 'sh-stage' }, [
      el('div', { class: 'sh-miniframe' }),
      el('div', { class: 'sh-host' }),
      el('div', { class: 'sh-vignette' }),
      el('div', { class: 'sh-schem-full' }),
      el('div', { class: 'sh-minicap', text: 'This section in the brain' }),
      el('nav', { class: 'sh-nav', 'aria-label': 'Where you are' }),
      el('div', { class: 'sh-tools' }),
      el('div', { class: 'sh-dock' }),
      el('div', { class: 'sh-tip', style: 'display:none' }),
      el('div', { class: 'sh-inset sh-glass', style: 'display:none' }),
    ]));
    body.appendChild(el('div', { class: 'sh-vdiv', title: 'Drag to resize', role: 'separator', 'aria-orientation': 'vertical' }));
    body.appendChild(el('aside', { class: 'sh-rail', 'aria-label': 'Inspector' }, [
      el('div', { class: 'sh-rail-head' }),
      el('div', { class: 'sh-map' }),
      el('div', { class: 'sh-hdiv', title: 'Drag to resize', role: 'separator', 'aria-orientation': 'horizontal' }),
      el('div', { class: 'sh-card' }),
    ]));
    const card = $('.sh-card');
    card.addEventListener('scroll', () => card.classList.toggle('scrolled', card.scrollTop > 4), { passive: true });
    wireDividers(body);
    applyRailSize();
    new ResizeObserver(() => { fitSchemText(); updateLabels(); placeMini(); }).observe(body);
    S.built = true;
    let themeT = 0;
    new MutationObserver(() => { if (BARRY.state.view !== 'seahorse') return; clearTimeout(themeT); themeT = setTimeout(themeChanged, 60); })
      .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    document.addEventListener('keydown', onKey);
  }
  function wireDividers(body) {
    const v = $('.sh-vdiv'), h = $('.sh-hdiv');
    let drag = null;
    v.addEventListener('pointerdown', (e) => { drag = { kind: 'v', x: e.clientX, w: $('.sh-rail').getBoundingClientRect().width }; v.setPointerCapture(e.pointerId); v.classList.add('drag'); });
    h.addEventListener('pointerdown', (e) => { const r = $('.sh-rail').getBoundingClientRect(); drag = { kind: 'h', y: e.clientY, top: r.top, hgt: r.height }; h.setPointerCapture(e.pointerId); h.classList.add('drag'); });
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
    const up = () => { if (drag) { drag = null; v.classList.remove('drag'); h.classList.remove('drag'); store.set({ railW: S.railW, railSplit: S.railSplit }); } };
    [v, h].forEach((n) => { n.addEventListener('pointermove', move); n.addEventListener('pointerup', up); n.addEventListener('pointercancel', up); });
  }
  function applyRailSize() {
    const body = $('.sh-body');
    if (!body) return;
    const w = S.railW || Math.max(360, Math.round(body.getBoundingClientRect().width * 0.3));
    body.style.setProperty('--sh-rail-w', Math.round(w) + 'px');
    body.style.setProperty('--sh-split', (S.railSplit * 100).toFixed(1) + '%');
  }

  /* ==================================================================
     The navigator (top left): how close you are, and where the plane is.
     One ladder for every mode: Brain > Hippocampus > Slab in 3D, Section >
     Hippocampus > Dentate in a slice, Circuit > By layer in the schematic.
     ================================================================== */
  const LADDERS = {
    '3d': [['brain', 'Brain', 'The whole brain, the hippocampal formation inside it'], ['hpf', 'Hippocampus', 'The hippocampal formation as clay, cut open'],
           ['slab', 'Slab', 'A 300 µm coronal slab, down to the cells']],
    slice: [['whole', 'Section', 'The whole section'], ['hippocampus', 'Hippocampus', 'The hippocampus, filling the view'], ['dg', 'Dentate', 'Close in on the dentate gyrus']],
    schematic: [['circuit', 'Circuit', 'The hippocampal formation, region to region'], ['dentate', 'By layer', 'Dentate gyrus to subiculum, every connection in the layer where it lands']],
  };
  const sliceStep = () => { const k = S.slice.k || 4; return k > 9 ? 'whole' : k > 3.2 ? 'hippocampus' : 'dg'; };
  function ladderNow() {
    if (S.mode === '3d') return S.level;
    if (S.mode === 'schematic') return S.schemFullPick || 'circuit';
    return sliceStep();
  }
  function ladderGo(k) {
    if (S.mode === '3d') { if (k === S.level) recenter(); else setLevel(k); }
    else if (S.mode === 'slice') sliceZoom(k);
    else { S.schemFullPick = k; store.set({ schemFullPick: k }); renderSchemFull(); syncLadder(); }
  }
  function syncLadder() {
    const now = ladderNow();
    $$('.sh-ladder-step').forEach((b) => { const on = b.dataset.k === now; b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on)); });
  }
  function renderNav() {
    const nav = $('.sh-nav');
    if (!nav) return;
    nav.innerHTML = '';
    nav.classList.toggle('away', cinematic());
    const now = ladderNow();
    const lad = el('div', { class: 'sh-ladder sh-glass', role: 'group', 'aria-label': 'How close' });
    (LADDERS[S.mode] || []).forEach(([k, words, tip], i) => {
      if (i) { const sep = UI.icon('right'); sep.classList.add('sh-ladder-sep'); lad.appendChild(sep); }
      lad.appendChild(el('button', { type: 'button', class: 'sh-ladder-step' + (k === now ? ' on' : ''), 'data-k': k, title: tip, 'aria-pressed': String(k === now),
        onclick: () => ladderGo(k) }, [el('i'), words]));
    });
    nav.appendChild(lad);
    const plane = planePanel();
    if (plane) nav.appendChild(plane);
  }
  function planeRange(label, kind, val, on, done) {
    const lim = cutLimits(kind);
    return UI.range({ label, min: lim[0], max: lim[1], step: 10, value: val, fmt: (v) => cutText(kind, v), on, done, wide: true, aria: 'Where the plane is' });
  }
  function planePanel() {
    if (S.mode === 'schematic' || (S.mode === '3d' && S.level === 'brain')) return null;
    const p = el('div', { class: 'sh-plane sh-glass' });
    if (S.mode === '3d') {
      if (S.level === 'slab') {
        p.appendChild(el('div', { class: 'sh-plane-row' }, [planeRange('Slab', 'coronal', S.cut.pos, (v) => { S.cut.pos = v; applyCut(); }, () => store.set({ cut: S.cut }))]));
        return p;
      }
      p.appendChild(el('div', { class: 'sh-plane-row' }, [UI.seg('Cut', [['none', 'None', 'The clay whole'], ['coronal', 'Coronal'], ['sagittal', 'Sagittal'], ['horizontal', 'Horizontal']],
        S.cut.kind, (k) => { S.cut.kind = k; S.cut.pos = defaultCutPos(k); store.set({ cut: S.cut }); applyCut(); renderNav(); })]));
      if (S.cut.kind !== 'none') p.appendChild(el('div', { class: 'sh-plane-row' }, [planeRange('', S.cut.kind, S.cut.pos, (v) => { S.cut.pos = v; applyCut(); }, () => store.set({ cut: S.cut }))]));
      return p;
    }
    p.appendChild(el('div', { class: 'sh-plane-row' }, [UI.seg('Plane', [['coronal', 'Coronal'], ['sagittal', 'Sagittal'], ['horizontal', 'Horizontal']], S.slice.plane, (k) => {
      S.slice.plane = k; S.slice.pos = defaultCutPos(k); S.slice.tiltA = 0; S.slice.tiltB = 0; S.slice.C = null; S.slice.custom = null; sliceZoom('hippocampus'); renderNav(); })]));
    p.appendChild(el('div', { class: 'sh-plane-row' }, [planeRange('', S.slice.plane, S.slice.pos, (v) => moveSlice(v), saveSlice)]));
    const tilted = !!(S.slice.tiltA || S.slice.tiltB);
    p.appendChild(el('div', { class: 'sh-plane-row' }, [
      UI.button({ text: 'Tilt', icon: 'section', cls: 'sm', pressed: S.tilt || tilted, title: 'Tilt the plane for an oblique section',
        onclick: () => { S.tilt = !(S.tilt || tilted); if (!S.tilt && tilted) { S.slice.tiltA = 0; S.slice.tiltB = 0; S.slice.custom = null; pushSlice(); } store.set({ tilt: S.tilt }); renderNav(); } }),
      UI.button({ text: 'Down the probe', icon: 'probe', cls: 'sm', title: 'A section along the probe track', onclick: sliceDownProbe }),
    ]));
    if (S.tilt || tilted) {
      const tilt = (key, label) => UI.range({ label, min: -45, max: 45, step: 1, value: S.slice[key], fmt: (v) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v) + '°', wide: true,
        on: (v) => { S.slice[key] = v; S.slice.custom = null; pushSlice(); }, done: () => renderNav() });
      p.appendChild(el('div', { class: 'sh-tilt' }, [tilt('tiltA', 'Tilt ↕'), tilt('tiltB', 'Tilt ↔'),
        tilted ? el('div', { class: 'sh-plane-row' }, [UI.button({ text: 'Level it', cls: 'sm', onclick: () => { S.slice.tiltA = 0; S.slice.tiltB = 0; S.slice.custom = null; pushSlice(); renderNav(); } })]) : null]));
    }
    return p;
  }

  /* ==================================================================
     The tools (top right): the View sheet and Recenter
     ================================================================== */
  function renderTools() {
    const t = $('.sh-tools');
    if (!t) return;
    t.innerHTML = '';
    t.classList.toggle('away', cinematic());
    if (S.mode === 'schematic') return;
    t.appendChild(UI.button({ icon: 'sliders', text: 'View', cls: 'sh-view-btn', title: 'What the stage shows', onclick: (e) => openViewSheet(e.currentTarget) }));
    t.appendChild(UI.button({ icon: 'frame', cls: 'icon', aria: 'Recenter', title: 'Recenter the view', onclick: recenter }));
  }
  function recenter() {
    if (!S.stage) return;
    if (S.mode === '3d') { if (isRide()) { S.stage.reframe(); return; } S.stage.setLevel(S.level, {}); applyCut(); }
    else if (S.mode === 'slice') sliceZoom(sliceStep());
  }
  const SHOWN = [[true, 'Shown'], [false, 'Hidden']];
  function openViewSheet(anchor) { UI.sheet(anchor, buildViewSheet, { width: 360, where: 'below-end', aria: 'What the stage shows' }); }
  function setting(box, name, say, opts, cur, on) {
    box.appendChild(el('div', { class: 'sh-set' }, [el('span', { class: 'sh-set-k', text: name }), UI.seg('', opts, cur, on, { aria: name, small: true }),
      say ? el('span', { class: 'sh-set-say', text: say }) : null]));
  }
  function buildViewSheet(box) {
    box.appendChild(el('div', { class: 'sh-sheet-h' }, [el('b', { text: S.mode === 'slice' ? 'The section shows' : 'The stage shows' }),
      UI.button({ icon: 'close', cls: 'sm icon quiet', aria: 'Close', onclick: () => UI.closeAll() })]));
    if (S.mode === '3d') {
      if (S.level !== 'brain') {
        box.appendChild(el('div', { class: 'sh-sheet-sec', text: 'Cells' }));
        setting(box, 'Placement', 'Story: each cell moved by its gap to touch its partner (at most 120 µm). As traced: where each tracing was registered.',
          [['story', 'Story'], ['traced', 'As traced']], S.story ? 'story' : 'traced', (k) => setStory(k === 'story'));
        setting(box, 'Crowd', 'One soma per cell at true density, in the sheet at the cut; drawn out as cells as you close in.', SHOWN, S.crowd, (k) => setCrowdOn(k));
        box.appendChild(el('div', { class: 'sh-sheet-sec', text: 'Tissue' }));
        setting(box, 'Layers', 'Exploded pulls the 28 layers apart, from the hilus out.', [['together', 'Together'], ['exploded', 'Exploded']], S.exploded ? 'exploded' : 'together', (k) => setExploded(k === 'exploded'));
        setting(box, 'Labels', 'Layer names on the cut face.', SHOWN, S.labels, (k) => setLabels(k));
      }
      box.appendChild(el('div', { class: 'sh-sheet-sec', text: 'Drawn in' }));
      setting(box, 'Paths', 'The medial perforant path (MEC to the dentate) and the temporoammonic path (EC III to CA1), drawn: no single tracing shows them.', SHOWN, S.paths, (k) => showPaths(k));
      setting(box, 'Probe', '64 contacts 20 µm apart, from the surgery coordinates in its card.', SHOWN, S.probe.on, (k) => showProbe(k));
    } else if (S.mode === 'slice') {
      box.appendChild(el('div', { class: 'sh-sheet-sec', text: 'The section' }));
      setting(box, 'Color', 'Layers: Seahorse\'s layer colors over the Nissl. Allen: the atlas\'s region colors. Nissl: the stain alone.',
        [['lamina', 'Layers'], ['allen', 'Allen'], ['nissl', 'Nissl']], S.slice.layer, (k) => { S.slice.layer = k; if (S.stage) S.stage.setSliceMode(k); saveSlice(); });
      setting(box, 'Labels', 'Layer names on the section; Allen names too when the whole section shows.', SHOWN, S.labels, (k) => setLabels(k));
      setting(box, 'Crowd', 'One soma per cell, in a thin sheet at the section.', SHOWN, S.crowd, (k) => setCrowdOn(k));
      box.appendChild(el('div', { class: 'sh-sheet-sec', text: 'Around it' }));
      setting(box, 'Probe', 'Drag its tip on the section to move it.', SHOWN, S.probe.on, (k) => showProbe(k));
      setting(box, 'Mini 3D', 'Where this section sits in the brain.', SHOWN, S.slice.mini, (k) => { S.slice.mini = k; if (S.stage) S.stage.mini = k; saveSlice(); placeMini(); updateLabels(); });
    }
    box.appendChild(el('div', { class: 'sh-set' }, [UI.button({ icon: 'probe', text: 'Place the probe', cls: 'sm', title: 'Surgery coordinates and angle', onclick: () => { UI.closeAll(); select({ type: 'probe' }); } })]));
  }
  function setStory(on) {
    S.story = !!on;
    store.set({ story: S.story });
    if (S.stage) S.stage.setStory(S.story);
    toast(S.story ? 'Showing the cells placed for the story: each moved by its gap to touch its partner.' : 'Showing every tracing where it was registered: the synapses open up by their gaps.', 'ok');
  }
  function setCrowdOn(on) { S.crowd = !!on; store.set({ crowd: S.crowd }); ensureCrowd(); if (S.stage) S.stage.showCrowd(S.crowd); }
  function setExploded(on) { S.exploded = !!on; if (S.stage) S.stage.explode(S.exploded ? 1 : 0); updateLabels(); }
  function setLabels(on) { S.labels = !!on; store.set({ labels: S.labels }); updateLabels(); }

  /* ==================================================================
     Modes and the stage
     ================================================================== */
  async function setMode(m) {
    if (isRide() && m !== '3d') stopPlay();
    if ((isStory() || isSext()) && !S.play.moving && m !== S.mode) stopPlay();       // you took the wheel: the story ends
    UI.closeAll();
    const changed = S.mode !== m;
    S.mode = m;
    store.set({ mode: m });
    root.classList.toggle('sh-mode-schem', m === 'schematic');
    UI.setSeg($('.sh-head-modes .seg'), m);
    renderNav();
    renderTools();
    placeMini();
    if (m === 'schematic') { renderSchemFull(); if (S.stage) S.stage.pause(); renderRail(); updateLabels(); return; }
    const ok = await ensureStage();
    if (!ok) return;
    S.stage.resume();
    // the stage arrives rather than snaps: a short fade as the view changes
    const host = $('.sh-host');
    if (host && changed && !reducedMotion()) { host.classList.remove('sh-swap'); void host.offsetWidth; host.classList.add('sh-swap'); }
    if (m === '3d') {
      S.stage.setView('3d');
      await setLevel(S.level, true);
    } else {
      const ok2 = await need(['brain50.shb.gz', 'hip20.shb.gz', 'fine10.shb.gz', 'cells.shb.gz'], 'Preparing the sections',
        'The whole brain every 50 µm, the hippocampus every 20, its dorsal part every 10 with the real Allen Nissl.');
      if (!ok2) return;
      S.stage.setView('slice');
      S.stage.setSliceMode(S.slice.layer);
      S.stage.mini = S.slice.mini && !isStory() && !isSext();
      if (!S.slice.C) sliceZoom('hippocampus'); else pushSlice();
      ensureCrowd();
    }
    placeMini();
    syncPaths();
    syncProbe();
    applyFocusAll();
    renderRail();
    renderNav();
    updateLabels();
  }
  async function ensureStage() {
    if (S.stage) return true;
    const ok = await need(['three', 'mesh_brain.shb.gz', 'mesh_hpf.shb.gz'], 'Seahorse is getting the brain ready', 'The first time only; after this it opens at once.');
    if (!ok) return false;
    const host = $('.sh-host');
    host.innerHTML = '';
    S.stage = S.three.create(host, {
      colors: stageColors(), onPick: onStagePick, onHover: onStageHover, onCamera: onStageCamera, onProbe: onProbeDrag,
      onFrame: onStageFrame, onDark: (on) => setNight(on),
    });
    await afterLoad();
    S.stage.setLevel('brain', { keepCam: true });
    return true;
  }
  /* The stage goes dark for a ride: the panels on it go night-glass with it, and the
     theme's accent is lifted so it still reads on the dark (a light theme's accent is dark). */
  function setNight(on) {
    const s = $('.sh-stage');
    if (!s) return;
    const a = hexRgb(tok('--accent', '#e5a823'));
    const lum = (0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2]) / 255;
    const k = lum < 0.5 ? 0.55 : 0;
    s.style.setProperty('--sh-night-accent', 'rgb(' + a.map((x) => Math.round(x + (255 - x) * k)).join(',') + ')');
    s.classList.toggle('night', !!on);
  }
  function stageColors() {
    return { shell: tok('--text-2', '#9aa'), hpf: REGION_COLORS.DG, bg: tok('--bg', '#111'), bg2: tok('--bg-2', '#181818'),
             probe: tok('--text', '#ddd'), contact: '#f2c14e', accent: tok('--accent', '#e5a823'), err: tok('--err', '#e05555'),
             ink: tok('--text', '#1d2421'), paper: paperColor(), drawn: tok('--text-3', '#aaa'), dark: isDarkTheme() };
  }
  function isDarkTheme() { const bg = hexRgb(tok('--bg', '#fff')); return bg[0] + bg[1] + bg[2] < 380; }
  function paperColor() {
    const bg = hexRgb(tok('--bg', '#fff'));
    return isDarkTheme() ? 'rgb(' + (bg[0] + 16) + ',' + (bg[1] + 17) + ',' + (bg[2] + 19) + ')' : '#fbfaf6';
  }
  async function setLevel(lv, quiet) {
    S.level = lv;
    store.set({ level: lv });
    renderNav();
    renderTools();
    if (!S.stage) return;
    if (lv !== 'brain') {
      const ok = await need(['mesh_hpf.shb.gz', 'mesh_lamina.shb.gz', 'cells.shb.gz', 'brain50.shb.gz', 'hip20.shb.gz', 'fine10.shb.gz'],
        lv === 'slab' ? 'Opening a slab of the hippocampus' : 'Flying into the hippocampus',
        'Its regions as clay, a cut through them painted with the real 10 µm Nissl, and the cells.');
      if (!ok) return;
    }
    S.stage.setLevel(lv, quiet && S.stage.level === lv ? { keepCam: true } : {});
    applyCut();
    syncPaths();
    if (lv !== 'brain') ensureCrowd();
    syncProbe();
    applyFocusAll();
    renderRail();
  }
  function applyCut() {
    if (!S.stage || S.mode !== '3d' || cinematic()) return;
    if (S.level === 'brain') S.stage.setCut({ kind: 'none' });
    else if (S.level === 'slab') S.stage.setCut({ kind: 'slab', pos: S.cut.pos, thick: 300 });
    else S.stage.setCut({ kind: S.cut.kind, pos: S.cut.pos });
    updateLabels();
  }
  /* the mini 3D's frame and caption, where the renderer leaves its corner clear */
  function placeMini() {
    const f = $('.sh-miniframe'), cap = $('.sh-minicap');
    if (!f) return;
    const on = S.mode === 'slice' && S.slice.mini && S.stage && S.stage.view === 'slice' && S.stage.miniRect && !isStory() && !isSext();
    f.classList.toggle('on', !!on);
    cap.classList.toggle('on', !!on);
    if (!on) return;
    const r = S.stage.miniRect();
    Object.assign(f.style, { left: r.x + 'px', top: r.y + 'px', width: r.w + 'px', height: r.h + 'px', right: 'auto' });
    Object.assign(cap.style, { left: r.x + 'px', top: (r.y + r.h + 8) + 'px', width: r.w + 'px', right: 'auto' });
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
    const A = S.slice.custom || sliceAxes();
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
    syncLadder();
  }
  function sliceDownProbe() {
    computeProbe();
    const d = S.probe.dir, t = S.probe.tip;
    const cr = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
    const nrm = (v) => { const l = Math.hypot(v[0], v[1], v[2]) || 1; return v.map((x) => x / l); };
    let N = nrm(cr([0, 0, 1], d));                    // the plane holds the shank and the ML axis
    if (!isFinite(N[0]) || Math.hypot(...N) < 0.5) N = [1, 0, 0];
    const V = nrm(d);
    const U = nrm(cr(V, N));
    const L = 40 + S.probe.contacts * S.probe.pitch;
    const place = () => {
      S.slice.custom = { N, U, V };
      S.slice.C = t.map((x, i) => x - d[i] * L * 0.6);
      const host = $('.sh-host').getBoundingClientRect();
      S.slice.k = Math.max(2200 / Math.max(100, host.width), (L * 2.2) / Math.max(100, host.height));
      pushSlice();
      syncLadder();
    };
    if (!S.probe.on) showProbe(true);
    if (S.mode !== 'slice') setMode('slice').then(place); else place();
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
      return { title: type.label + ' · ' + name, line: type.line || type.about, tag, swatch: type.color, extra: moved > 0.5 ? 'Moved ' + moved.toFixed(0) + ' µm to meet its partner' : '',
               sel: { type: 'cell', key: type.key, inst: ud.key } };
    }
    if (ud.kind === 'lamina') return lamInfo(ud.key);
    if (ud.kind === 'region') {
      const acr = ud.key;
      const r = S.kb.regions.find((x) => (x.allen || []).includes(acr));
      return { title: (ud.name || acr) + ' (' + acr + ')', line: (S.kb.region_lines || {})[acr] || (r ? r.sub : ''), tag: ['allen', 'Allen CCFv3'], swatch: REGION_COLORS[acr] || null,
               sel: r ? { type: 'region', key: r.key } : { type: 'allen', key: acr, name: ud.name } };
    }
    if (ud.kind === 'cap' && ud.ccf) return pointInfo(ud.ccf);
    return null;
  }
  function lamInfo(key) {
    const l = lamOf(key) || { label: key, name: '' };
    const derived = (l.how || '').startsWith('derived');
    return { title: l.label + ' · ' + l.name, line: l.line || '', swatch: lamColor(key), square: true,
             tag: derived ? ['derived', 'Derived (' + l.how.replace(/^derived: /, '') + ')'] : ['allen', 'Allen CCFv3'], sel: { type: 'lamina', key } };
  }
  function pointInfo(c) {
    const s = sampleAt(c[0], c[1], c[2]);
    if (s.lam) { const l = lamByCode(s.lam); if (l) { const i = lamInfo(l.key); i.where = c; return i; } }
    if (s.allen) {
      const st = allenStruct(s.allen);
      return { title: st.name + (st.acronym ? ' (' + st.acronym + ')' : ''), line: (S.kb.region_lines || {})[st.acronym] || '', tag: ['allen', 'Allen CCFv3'], swatch: st.color || null, square: true,
               sel: { type: 'allen', key: st.acronym, name: st.name, idx: s.allen }, where: c };
    }
    return null;
  }
  function showTip(info, cx, cy) {
    const tip = $('.sh-tip');
    if (!info) { tip.style.display = 'none'; return; }
    tip.innerHTML = '';
    tip.appendChild(el('div', { class: 'sh-tip-title' }, [info.swatch ? el('span', { class: 'sh-sw' + (info.square ? ' sq' : ''), style: 'background:' + info.swatch }) : null, info.title]));
    if (info.line) tip.appendChild(el('div', { class: 'sh-tip-line', text: info.line }));
    const foot = el('div', { class: 'sh-tip-foot' }, [el('span', { class: 'sh-tag ' + info.tag[0], text: info.tag[1] })]);
    if (info.extra) foot.appendChild(el('span', { text: info.extra }));
    if (info.where) foot.appendChild(el('span', { text: apText(info.where[0]) + ' (approx.)' }));
    tip.appendChild(foot);
    const r = $('.sh-stage').getBoundingClientRect();
    tip.style.display = 'flex';
    const w = tip.offsetWidth || 280, h = tip.offsetHeight || 80;
    let x = cx - r.left + 18, y = cy - r.top + 18;
    if (x + w > r.width - 10) x = cx - r.left - w - 16;
    if (y + h > r.height - 10) y = cy - r.top - h - 16;
    tip.style.left = Math.max(8, x) + 'px';
    tip.style.top = Math.max(8, y) + 'px';
  }
  function onStageHover(ud, cx, cy) {
    const info = infoFor(ud);
    showTip(info, cx, cy);
    setHover(info ? info.sel : null, 'stage');
  }
  function onStagePick(ud) {
    const info = infoFor(ud);
    if (info) pick(info.sel, 'stage'); else select(null);
  }
  let camT = 0;
  function onStageCamera() {
    clearTimeout(camT);
    camT = setTimeout(updateHere, 160);
    if (S.mode === 'slice') syncLadder();
    if (isStory()) { storyOverlay(true); return; }
    if (isSext()) { sextOverlay(true); return; }
    const lb = $('.sh-labels');
    if (lb && S.mode === '3d') lb.classList.add('moving');
    clearTimeout(labT);
    labT = setTimeout(() => { drawLabels(); const l2 = $('.sh-labels'); if (l2) l2.classList.remove('moving'); }, S.mode === '3d' ? 220 : 60);
  }
  function onStageFrame() {
    if (isRide()) updateRideTag();
    else if (isStory()) placeStoryWords();
    else placeSelTag();
  }
  /* What sits at the middle of the view: the "you are here" of the map. */
  function updateHere() {
    if (!S.stage || isRide()) return;
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
     Words on the stage: layer names on the section, the probe's runs of
     contacts, and a tag on whatever is selected. Words keep off the
     glass panels and the mini 3D, and never overlap one another.
     ================================================================== */
  let labT = 0;
  function updateLabels() { clearTimeout(labT); labT = setTimeout(drawLabels, 90); }
  function stageBox() {
    const host = $('.sh-host'), stg = $('.sh-stage');
    if (!host || !stg) return null;
    const hr = host.getBoundingClientRect(), sr = stg.getBoundingClientRect();
    return { ox: hr.left - sr.left, oy: hr.top - sr.top, W: hr.width, H: hr.height, sr };
  }
  const sectionShowing = () => S.mode === 'slice' || (S.mode === '3d' && S.level !== 'brain' && !S.exploded && (S.cut.kind !== 'none' || S.level === 'slab'));
  /* the panels floating on the stage, as boxes in stage pixels */
  function panelBoxes(B) {
    const out = [];
    $$('.sh-nav > *, .sh-tools > *, .sh-dock > *').forEach((n) => {
      const r = n.getBoundingClientRect();
      if (r.width && r.height) out.push([r.left - B.sr.left - B.ox - 6, r.top - B.sr.top - B.oy - 6, r.width + 12, r.height + 12]);
    });
    if (S.mode === 'slice' && S.slice.mini && S.stage && S.stage.miniRect) { const m = S.stage.miniRect(); out.push([m.x - 6, m.y - 6, m.w + 12, m.h + 30]); }
    return out;
  }
  function drawLabels() { timed('labels', drawLabels0); }
  function drawLabels0() {
    const stg = $('.sh-stage');
    if (!stg) return;
    let box = $('.sh-labels');
    if (!box) { box = el('div', { class: 'sh-labels', 'aria-hidden': 'true' }); stg.appendChild(box); }
    box.innerHTML = '';
    S.labelPos = new Map();
    const B = stageBox();
    if (!B || !S.stage || S.mode === 'schematic' || !S.volumesUp || cinematic()) { placeSelTag(); return; }
    const placed = panelBoxes(B);
    const put = (x, y, text, cls, w0, kids) => {
      const w = w0 || text.length * 6.6 + 10, h = 18;
      const bx = x - w / 2, by = y - h / 2;
      if (bx < 6 || by < 6 || bx + w > B.W - 6 || by + h > B.H - 6) return false;
      if (placed.some((r) => bx < r[0] + r[2] + 4 && bx + w + 4 > r[0] && by < r[1] + r[3] + 3 && by + h + 3 > r[1])) return false;
      placed.push([bx, by, w, h]);
      box.appendChild(el('span', { class: 'sh-word ' + (cls || ''), style: 'left:' + Math.round(B.ox + x) + 'px;top:' + Math.round(B.oy + y) + 'px' }, kids || [text]));
      return true;
    };
    // the probe: each run of contacts in one layer, beside the ribbon
    if (S.probe.on && S.blobs['brain50.shb.gz']) {
      computeProbe();
      const W = S.three.W;
      probeRuns().forEach((r) => {
        const mid = contactCcf(Math.round((r.from + r.to) / 2) - 1);
        let p;
        if (S.mode === 'slice') { p = S.stage.ccfToSlicePx(mid); if (Math.abs(p[2]) > 250) return; }
        else { p = S.stage.project(W(mid[0], mid[1], mid[2])); if (p[2] > 1) return; }
        const text = (r.from === r.to ? 'ch ' + r.from : 'ch ' + r.from + '–' + r.to) + ' · ' + r.name;
        const w = text.length * 6.2 + 26;
        const kids = [el('span', { class: 'sw', style: 'background:' + (r.key ? lamColor(r.key) : 'var(--sh-ink-3)') }), text];
        if (!put(p[0] + 28 + w / 2, p[1], text, 'probe', w, kids)) put(p[0] - 28 - w / 2, p[1], text, 'probe', w, kids);
      });
    }
    if (S.labels && sectionShowing()) {
      const step = 12, acc = new Map();
      const wide = S.mode === 'slice' && S.slice.k > 9;
      const Bl = S.blobs['brain50.shb.gz'];
      for (let y = step / 2; y < B.H; y += step) for (let x = step / 2; x < B.W; x += step) {
        const c = S.stage.screenToSection(x, y);
        if (!c) continue;
        let key = null;
        const lab = labAt(c[0], c[1], c[2]);
        if (lab) key = 'L' + lab;
        else if (wide && Bl) {
          const i = Math.floor(c[0] / 50), j = Math.floor(c[1] / 50), k = Math.floor(c[2] / 50);
          if (i >= 0 && j >= 0 && k >= 0 && i < 264 && j < 160 && k < 228) { const a = Bl.arrays.labels[(i * 160 + j) * 228 + k]; if (a) key = 'A' + a; }
        }
        if (!key) continue;
        let g = acc.get(key);
        if (!g) { g = { n: 0, sx: 0, sy: 0, pts: [] }; acc.set(key, g); }
        g.n++; g.sx += x; g.sy += y; g.pts.push(x, y);
      }
      const groups = [...acc.entries()].filter(([k, g]) => g.n >= (k[0] === 'L' ? 5 : 30)).sort((a, b) => b[1].n - a[1].n);
      for (const [k, g] of groups) {
        // the sample nearest the middle that is inside it (a C-shaped layer's middle is outside)
        const mx = g.sx / g.n, my = g.sy / g.n;
        let bx = 0, by = 0, bd = 1e18;
        for (let i = 0; i < g.pts.length; i += 2) { const d = (g.pts[i] - mx) ** 2 + (g.pts[i + 1] - my) ** 2; if (d < bd) { bd = d; bx = g.pts[i]; by = g.pts[i + 1]; } }
        S.labelPos.set(k, [bx, by]);
        let text;
        if (k[0] === 'L') { const l = lamByCode(+k.slice(1)); text = l ? l.label : ''; }
        else { const st = allenStruct(+k.slice(1)); text = st.acronym || ''; }
        if (text) put(bx, by, text, k[0] === 'L' ? 'layer' : 'allen');
      }
    }
    placeSelTag();
  }
  /* the selected thing's tag: on its label in a section, else at its middle */
  function selName(sel) {
    if (sel.type === 'cell') return (cellOf(sel.key) || {}).label || sel.key;
    if (sel.type === 'region') return (regionOf(sel.key) || {}).label || sel.key;
    if (sel.type === 'lamina') { const l = lamOf(sel.key); return l ? l.label + ' · ' + l.name : sel.key; }
    if (sel.type === 'conn') return (connOf(sel.key) || {}).label || sel.key;
    return sel.name || sel.key;
  }
  function selWorld(sel) {
    const st = S.stage;
    const t = targetsFor(sel);
    if (t.cells.size) return st.cellSomaW([...t.cells][0]);
    const b = (t.layers.size === 1 && st.bounds('lamina', [...t.layers][0], true)) || ([...t.regions].length && st.bounds('hpf', [...t.regions][0], true));
    return b ? b[0].clone().add(b[1]).multiplyScalar(0.5) : null;
  }
  function placeSelTag() {
    const stg = $('.sh-stage');
    if (!stg) return;
    let tag = $('.sh-seltag');
    const sel = S.sel;
    const show = sel && NAVIGABLE.has(sel.type) && S.stage && S.mode !== 'schematic' && !isRide();
    if (!show) { if (tag) tag.style.display = 'none'; return; }
    if (!tag) { tag = el('div', { class: 'sh-seltag', 'aria-hidden': 'true' }); stg.appendChild(tag); }
    const B = stageBox();
    let p = null;
    if (sel.type === 'lamina' || sel.type === 'region') {
      const t = targetsFor(sel);
      const room = (q) => B && q[0] > 30 && q[1] > 40 && q[0] < B.W - 30 && q[1] < B.H - 10;
      for (const k of t.layers) { const q = S.labelPos && S.labelPos.get('L' + (lamOf(k) || {}).code); if (q && room(q)) { p = q; break; } }
    }
    if (!p && sel.type !== 'allen') {
      if (!S.selAnchor) S.selAnchor = selWorld(sel);
      if (S.selAnchor) { const q = S.stage.project(S.selAnchor); if (q[2] <= 1) p = q; }
    }
    // the tag rides 34 px above its point: too near the top and it would be cut off, so it waits
    if (!p || !B || p[0] < 4 || p[1] < 40 || p[0] > B.W - 4 || p[1] > B.H - 4) { tag.style.display = 'none'; return; }
    const text = selName(sel);
    if (tag.textContent !== text) tag.textContent = text;
    tag.style.display = 'block';
    // near the right edge the tag hangs to the left of its point, so it is never cut off
    const left = p[0] + 16 + tag.offsetWidth > B.W - 6;
    tag.classList.toggle('left', left);
    tag.style.transform = 'translate(' + Math.round(B.ox + p[0] - (left ? tag.offsetWidth + 24 : 0)) + 'px,' + Math.round(B.oy + p[1]) + 'px)';
  }

  /* ==================================================================
     Selection, hover and focus, kept in step across the views
     ================================================================== */
  const NAVIGABLE = new Set(['cell', 'region', 'conn', 'lamina', 'allen']);
  function select(sel, o) {
    o = o || {};
    S.sel = sel;
    if (!o.keepReach) S.reach = null;
    if (sel && NAVIGABLE.has(sel.type)) setHere(normHere(sel));
    if (!isRide()) {
      S.focus = sel ? focusFor(sel) : null;
      applyFocusAll();
    }
    // back / forward: every selection of a thing is a stop
    if (!o.hist && sel && NAVIGABLE.has(sel.type)) {
      const H = S.hist, cur = H.list[H.i];
      if (!cur || cur.type !== sel.type || cur.key !== sel.key) {
        H.list = H.list.slice(0, H.i + 1);
        H.list.push(Object.assign({}, sel));
        if (H.list.length > 60) H.list.shift();
        H.i = H.list.length - 1;
      }
    }
    if (S.stage && S.stage.highlight) S.stage.highlight('sel', sel && NAVIGABLE.has(sel.type) ? targetsFor(sel) : null);
    S.selAnchor = null;
    showExtras();
    showCard(sel);
    renderRail();
    placeSelTag();
  }
  /* A click from the schematic, a card or the search: select it and hone
     the view in on it (with context: about 40% of the view). */
  function pick(sel, from) {
    select(sel);
    if (sel && NAVIGABLE.has(sel.type)) hone(sel, from);
  }
  function histGo(d) {
    const H = S.hist;
    const i = H.i + d;
    if (i < 0 || i >= H.list.length) return;
    H.i = i;
    const sel = H.list[i];
    select(sel, { hist: true });
    hone(sel, 'hist');
  }
  /* What a selection is on the stage: hpf meshes (their Allen keys),
     lamina keys and cell instances. */
  const HPF_KEYS = ['DG', 'CA1', 'CA2', 'CA3', 'SUB', 'ProS', 'ENTl', 'ENTm', 'PRE', 'POST', 'PAR', 'PERI', 'ECT', 'VISpor'];
  const hpfKeyOf = (acr) => HPF_KEYS.filter((k) => acr === k || acr.startsWith(k)).sort((a, b) => b.length - a.length)[0] || null;
  const layersOfRegion = (rk) => S.kb.lamina.filter((l) => regionOfLayer(l.key) === rk).map((l) => l.key);
  function targetsFor(sel) {
    const t = { regions: new Set(), layers: new Set(), cells: new Set(), allen: new Set() };
    if (!sel || !S.kb) return t;
    const addRegion = (rk) => ((regionOf(rk) || {}).allen || []).forEach((a) => { t.allen.add(a); const h = hpfKeyOf(a); if (h) t.regions.add(h); });
    if (sel.type === 'cell') instancesOfType(sel.key).forEach((k) => t.cells.add(k));
    else if (sel.type === 'region') { addRegion(sel.key); layersOfRegion(sel.key).forEach((k) => t.layers.add(k)); }
    else if (sel.type === 'lamina') { t.layers.add(sel.key); const rk = regionOfLayer(sel.key); if (rk) ((regionOf(rk) || {}).allen || []).forEach((a) => { const h = hpfKeyOf(a); if (h) t.regions.add(h); }); }
    else if (sel.type === 'conn') {
      const c = connOf(sel.key);
      if (c) {
        [c.from, c.to].forEach((k) => { if (cellOf(k)) instancesOfType(k).forEach((i) => t.cells.add(i)); else addRegion(k); });
        (c.layer || []).forEach((l) => t.layers.add(l));
      }
    } else if (sel.type === 'allen' && sel.key) { t.allen.add(sel.key); const h = hpfKeyOf(sel.key); if (h) t.regions.add(h); }
    return t;
  }
  /* Allen acronym -> every label index under it in the 50 um annotation. */
  const allenIdxCache = new Map();
  function allenIdxFor(acr) {
    if (allenIdxCache.has(acr)) return allenIdxCache.get(acr);
    const B = S.blobs['brain50.shb.gz'];
    const out = [];
    if (B) {
      const st = B.header.structures;
      const top = st.find((s) => s.acronym === acr);
      if (top) st.forEach((s, i) => { if (s.id === top.id || (s.path || []).includes(top.id)) out.push(i); });
      allenIdxCache.set(acr, out);
    }
    return out;
  }
  /* The middle of a label in the 20 um hippocampus volume (CCF um), right side. */
  const codeCentre = new Map();
  function labelCentre(codes) {
    const key = codes.slice().sort().join(',');
    if (codeCentre.has(key)) return codeCentre.get(key);
    const H = S.blobs['hip20.shb.gz'];
    if (!H) return null;
    const want = new Set(codes);
    const o = H.header.origin_um, sh = H.header.arrays[0].shape, L = H.arrays.labels;
    let n = 0, a = 0, d = 0, m = 0;
    for (let i = 0; i < sh[0]; i += 2) for (let j = 0; j < sh[1]; j++) for (let k = 0; k < sh[2]; k++) {
      if (!want.has(L[(i * sh[1] + j) * sh[2] + k])) continue;
      n++; a += i; d += j; m += k;
    }
    const c = n ? [o[0] + (a / n) * 20 + 10, o[1] + (d / n) * 20 + 10, o[2] + (m / n) * 20 + 10] : null;
    codeCentre.set(key, c);
    return c;
  }
  /* Hone in: frame the thing with room around it; open a cut through it
     when it is hidden inside the clay; in a section, move to the plane
     nearest it. Honing never backs the camera out. */
  async function hone(sel, from) {
    if (!sel || !S.stage || S.mode === 'schematic' || isRide()) return;
    const t = targetsFor(sel);
    const THREE_W = S.three.W;
    if (S.mode === '3d') {
      if (from === 'stage' && sel.type !== 'cell' && sel.type !== 'region') return;
      if (S.level === 'brain' && sel.type !== 'allen') { await setLevel('hpf'); }
      const st = S.stage;
      const pts = [];
      const pad = (v, r) => { pts.push({ x: v.x - r, y: v.y - r, z: v.z - r }, { x: v.x + r, y: v.y + r, z: v.z + r }); };
      t.cells.forEach((k) => { const s = st.cellSomaW(k); if (s) pad(s, 0.28); });
      t.layers.forEach((k) => { const b = st.bounds('lamina', k, true); if (b) pts.push(...b); });
      if (!t.layers.size) t.regions.forEach((k) => { const b = st.bounds('hpf', k, true); if (b) pts.push(...b); });
      if (!pts.length) return;
      let dir = null;
      // a layer is inside the clay: cut through it, and look at the cut face
      if (sel.type === 'lamina' && from !== 'stage') {
        const code = (lamOf(sel.key) || {}).code;
        const c = code ? labelCentre([code]) : null;
        if (c) {
          if (S.level === 'slab') { S.cut.pos = Math.round(c[0] / 10) * 10; }
          else {
            if (S.cut.kind === 'none') S.cut.kind = 'coronal';
            S.cut.pos = Math.round((S.cut.kind === 'coronal' ? c[0] : S.cut.kind === 'sagittal' ? c[2] : c[1]) / 10) * 10;
          }
          store.set({ cut: S.cut });
          applyCut();
          renderNav();
          const kind = S.level === 'slab' ? 'coronal' : S.cut.kind;
          const n = kind === 'coronal' ? [0, 0, 1] : kind === 'sagittal' ? [1, 0, 0] : [0, -1, 0];
          const d0 = st.camDir();
          const dn = d0[0] * n[0] + d0[1] * n[1] + d0[2] * n[2];
          if (dn > -0.45) dir = [0, 1, 2].map((i) => d0[i] - n[i] * (dn + 0.8));
          // frame the layer where the cut crosses it, not its whole sweep
          const w = THREE_W(c[0], c[1], c[2]);
          pts.length = 0;
          pad({ x: w[0], y: w[1], z: w[2] }, 0.55);
        }
      }
      st.frameOn(pts, 1100, 0.4, dir, { noFarther: true });
      return;
    }
    if (S.mode === 'slice') {
      if (from === 'stage') return;
      let c = null;
      if (t.cells.size) { const s = S.stage.cellSomaW([...t.cells][0]); if (s) c = S.stage.toCcf(s.x, s.y, s.z); }
      if (!c) {
        const codes = [...t.layers].map((k) => (lamOf(k) || {}).code).filter(Boolean);
        if (codes.length) c = labelCentre(codes);
      }
      if (!c) return;
      const ax = S.slice.custom || sliceAxes();
      // move the plane (keeping its tilt) so it passes through the thing
      const b = BASES[S.slice.plane];
      S.slice.pos = Math.round(c[0] * b.N[0] + c[1] * b.N[1] + c[2] * b.N[2]);
      const onPlane = c.slice();
      S.slice.C = onPlane;
      // center on the nearest voxel of a layer on this plane (its middle can be in the hilus)
      const codes = new Set([...t.layers].map((k) => (lamOf(k) || {}).code).filter(Boolean));
      if (codes.size && !t.cells.size) {
        let best = null, bd = 1e18;
        for (let du = -1500; du <= 1500; du += 40) for (let dv = -1500; dv <= 1500; dv += 40) {
          const p = [0, 1, 2].map((i) => onPlane[i] + ax.U[i] * du + ax.V[i] * dv);
          if (codes.has(sampleAt(p[0], p[1], p[2]).lam)) { const d = du * du + dv * dv; if (d < bd) { bd = d; best = p; } }
        }
        if (best) S.slice.C = best;
      }
      const host = $('.sh-host').getBoundingClientRect();
      const want = Math.max(2600 / Math.max(100, host.width), 2000 / Math.max(100, host.height));
      if (S.slice.k > want) S.slice.k = want;
      renderNav();
      pushSlice();
    }
  }
  function normHere(sel) {
    if (sel.type === 'allen') return null;
    return { type: sel.type, key: sel.key };
  }
  function setHover(sel, from) {
    const same = (a, b) => (!a && !b) || (a && b && a.type === b.type && a.key === b.key);
    if (same(sel, S.hover)) return;
    S.hover = sel;
    S.hoverFrom = from;
    applySchem();
    // the schematic or a card is hovering: the same thing glows on the stage and the rest steps back
    if (from !== 'stage' && S.stage && S.stage.highlight) S.stage.highlight('hover', sel ? targetsFor(sel) : null);
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
  const SINK = '#d8453a', SOURCE = '#3a76d6';
  function applyHighlights() {
    if (!S.stage || !S.volumesUp) return;
    const acc = hexRgb(tok('--accent', '#e5a823'));
    const lam = new Map(), allen = new Map(), pulse = new Map();
    const codeOf = (k) => (lamOf(k) || {}).code;
    if (S.focus) S.focus.layers.forEach((k) => { const c = codeOf(k); if (c) lam.set(c, acc.concat(0.32)); });
    if (S.sel && S.sel.type === 'lamina') { const c = codeOf(S.sel.key); if (c) lam.set(c, acc.concat(0.5)); }
    if (S.sel && S.sel.type === 'allen' && S.sel.idx) allen.set(S.sel.idx, acc.concat(0.4));
    // hover: the thing glows in the section and everything else steps back
    let dimRest = false;
    if (S.hover) {
      if (S.hover.type === 'allen') { if (S.hover.idx) { allen.set(S.hover.idx, acc.concat(0.45)); dimRest = true; } }
      else {
        const t = targetsFor(S.hover);
        t.layers.forEach((k) => { const c = codeOf(k); if (c) { lam.set(c, acc.concat(0.55)); dimRest = true; } });
        if (!t.layers.size) t.allen.forEach((a) => allenIdxFor(a).forEach((i) => { allen.set(i, acc.concat(0.42)); dimRest = true; }));
      }
    }
    // the quiz's layer: lit strongly, and pulsing, so it is unmistakable
    if (S.quiz && S.quiz.open && S.quizLayer) { const c = codeOf(S.quizLayer); if (c) pulse.set(c, acc.concat(0.85)); }
    const P = S.play;
    if (P && P.kind === 'event' && P.model) {
      // the event's current source density at this moment, painted into its layers
      const sink = hexRgb(SINK), src = hexRgb(SOURCE);
      const live = liveCsd(P);
      for (const [k, v] of live) { const c = codeOf(k); if (c && Math.abs(v) > 0.04) pulse.set(c, (v < 0 ? sink : src).concat(Math.min(0.92, 0.4 + Math.abs(v) * 0.8))); }
      // the layers' own colors step back, so red and blue mean sink and source only
      dimRest = true;
    } else if (P && P.kind === 'ride' && P.sink) {
      const sink = hexRgb(SINK), src = hexRgb(SOURCE);
      P.sink.forEach((k) => { const c = codeOf(k); if (c) pulse.set(c, sink.concat(0.7)); });
      (P.source || []).forEach((k) => { const c = codeOf(k); if (c) pulse.set(c, src.concat(0.45)); });
    } else if (P && P.kind === 'story') {
      // the story: recorded zones in ember (how far each is from its quiet self), or the model's
      // sink and source, or the loop's burning cut face; everything else steps back
      const R = BARRY.shStory;
      const put = (k, lv) => { const c = codeOf(k), a = R.alphaOf(lv); if (c && a) pulse.set(c, R.ramp(lv).concat(Math.min(0.88, a))); };
      if (P.stop && P.stop.measure) P.D.zones.forEach((z) => z.layers.forEach((k) => put(k, P.levels[z.key] || 0)));
      else if (P.extra) for (const [k, lv] of P.extra) put(k, lv);
      else if (P.modelPaint) {
        const sink = hexRgb(SINK), src = hexRgb(SOURCE);
        for (const [k, v] of P.modelPaint) { const c = codeOf(k); if (c && Math.abs(v) > 0.04) pulse.set(c, (v < 0 ? sink : src).concat(Math.min(0.92, 0.4 + Math.abs(v) * 0.8))); }
      }
      if (P.light != null) { const c = codeOf('hil'); if (c) pulse.set(c, hexRgb(LIGHT).concat(0.16 + 0.64 * P.light)); }
      dimRest = !!(P.stop && (P.stop.measure || P.model || P.extra || P.light != null));
    }
    S.stage.setHighlights({ lam, allen, pulse, dimRest });
    if (P && P.kind === 'event' && S.stage.setPulse) S.stage.setPulse(1);
  }

  /* ==================================================================
     The rail: the map that follows you, over the card
     ================================================================== */
  const schemHelpers = () => ({
    kb: S.kb, cellOf, regionOf, connOf, lamOf, verdictOf, regionOfLayer, regionColor,
    select: (sel) => pick(sel, 'schem'), hover: (sel) => { setHover(sel, 'schem'); if (sel) showSchemTip(sel); else hideSchemTip(); },
    notes: (type, key) => notesFor(type, key).length,
  });
  function schemKind() {
    if (S.schemPick !== 'auto') return S.schemPick;
    if (S.mode === 'schematic') return S.schemFullPick || 'circuit';
    if (isStory() && S.play.stop) return S.play.stop.map || 'dentate';
    if (S.sel && S.sel.type === 'cell' && !isRide()) return 'cell';
    if (S.play && (S.play.kind === 'event' || ['ds1', 'ds2', 'dentate'].includes(S.play.key))) return 'dentate';
    if (S.mode === '3d' && S.level === 'slab') return 'dentate';
    const hr = S.here ? (S.here.type === 'lamina' ? regionOfLayer(S.here.key) : S.here.type === 'region' ? S.here.key : null) : null;
    if (S.mode === 'slice' && S.slice.k && S.slice.k < 5 && (hr === 'dg' || hr === 'ca3')) return 'dentate';
    return 'circuit';
  }
  const mapCell = (kind) => kind === 'cell' ? ((S.sel && S.sel.type === 'cell') ? S.sel.key : (S.lastCell || 'gc')) : null;
  function mapTitle(kind) {
    if (kind === 'cell') { const c = cellOf(mapCell(kind)) || {}; return [c.label || 'One cell', 'What feeds it, where it leads']; }
    if (kind === 'dentate') return ['Dentate gyrus to subiculum', 'By layer'];
    return ['Hippocampal formation', 'Region to region'];
  }
  function renderRail() {
    if (!S.kb) return;
    const head = $('.sh-rail-head');
    const kind = S.mode === 'schematic' ? null : schemKind();
    head.innerHTML = '';
    const H = S.hist;
    head.appendChild(UI.button({ icon: 'left', cls: 'sm icon quiet', aria: 'Back', title: 'Back to the last thing you selected (Alt+←)', disabled: H.i <= 0, onclick: () => histGo(-1) }));
    head.appendChild(UI.button({ icon: 'right', cls: 'sm icon quiet', aria: 'Forward', title: 'Forward (Alt+→)', disabled: H.i >= H.list.length - 1, onclick: () => histGo(1) }));
    if (kind) {
      const [t, sub] = mapTitle(kind);
      head.appendChild(el('div', { class: 'sh-rail-title' }, [t, el('small', { text: (S.schemPick === 'auto' ? 'Following you · ' : '') + sub })]));
      const b = UI.button({ icon: 'nodes', text: 'Map', cls: 'sm', title: 'What the map shows, and whether it follows you', onclick: (e) => mapMenu(e.currentTarget) });
      const caret = UI.icon('down'); caret.classList.add('caret'); b.appendChild(caret);
      head.appendChild(b);
    }
    const box = $('.sh-map');
    const cellKey = mapCell(kind);
    const sig = kind + ':' + (cellKey || '') + ':' + Object.keys(S.lab.notes || {}).length;
    if (kind && (S.schemShown !== sig || !box.firstChild)) {
      const svgNode = kind === 'cell' ? BARRY.shSchem.cell(schemHelpers(), cellKey) : kind === 'dentate' ? BARRY.shSchem.dentate(schemHelpers()) : BARRY.shSchem.circuit(schemHelpers());
      // the drawing under the pointer is going away: so is its hover (no pointerleave will come)
      if (S.hover && S.hoverFrom === 'schem') { setHover(null, 'schem'); hideSchemTip(); }
      box.innerHTML = '';
      box.appendChild(svgNode);
      if (!reducedMotion()) svgNode.classList.add('sh-fade-in');
      S.schemShown = sig;
    }
    if (cellKey) S.lastCell = cellKey;
    applySchem();
    fitSchemText();
  }
  function mapMenu(anchor) {
    const setPick = (k) => { S.schemPick = k; store.set({ schemPick: k }); renderRail(); };
    const setFollow = (v) => { S.follow = v; store.set({ follow: v }); renderRail(); };
    UI.menu(anchor, [
      { title: 'The map shows', items: [
        { label: 'Whatever you look at', sub: 'The circuit, the layers or one cell\'s wiring, by zoom and selection', icon: 'spark', active: S.schemPick === 'auto', on: () => setPick('auto') },
        { label: 'The circuit', sub: 'The hippocampal formation, region to region', icon: 'nodes', active: S.schemPick === 'circuit', on: () => setPick('circuit') },
        { label: 'By layer', sub: 'Dentate gyrus to subiculum, each connection in its layer', icon: 'section', active: S.schemPick === 'dentate', on: () => setPick('dentate') },
        { label: 'One cell\'s wiring', sub: 'The selected cell: what feeds it and where it leads', icon: 'ride', active: S.schemPick === 'cell', on: () => setPick('cell') },
      ] },
      { title: 'As you move', items: [
        { label: 'Leans toward where you are', sub: 'The map glides a little toward what is in the middle of the view', icon: 'frame', active: S.follow, on: () => setFollow(true) },
        { label: 'Holds still', sub: 'The whole drawing stays in place', icon: 'views', active: !S.follow, on: () => setFollow(false) },
      ] },
    ], { where: 'below-end', width: 330 });
  }
  /* words in the drawings stay the same size on screen however the rail is sized */
  let fitT = 0;
  function fitSchemText(later) {
    clearTimeout(fitT);
    const go = () => { if (!root) return; root.querySelectorAll('.sh-map svg, .sh-schem-full svg').forEach((s) => BARRY.shSchem.fitText(s)); };
    if (later) fitT = setTimeout(go, later); else go();
  }
  function applySchem() {
    const st = { focus: S.focus, hover: S.hover, sel: S.sel, here: S.here, trail: S.trail,
                 ds: S.play && S.play.sink ? { sink: S.play.sink, source: S.play.source || [] } : null,
                 cellRegion: (k) => (cellOf(k) || {}).region };
    const rail = $('.sh-map svg');
    if (rail) { BARRY.shSchem.apply(rail, st); BARRY.shSchem.follow(rail, S.here, S.follow); fitSchemText(650); }
    const full = $('.sh-schem-full svg');
    if (full) BARRY.shSchem.apply(full, st);
  }
  function renderSchemFull() {
    const box = $('.sh-schem-full');
    if (S.hover && S.hoverFrom === 'schem') setHover(null, 'schem');
    box.innerHTML = '';
    const pickK = S.schemFullPick || 'circuit';
    const svgNode = pickK === 'dentate' ? BARRY.shSchem.dentate(schemHelpers()) : BARRY.shSchem.circuit(schemHelpers());
    if (!reducedMotion()) svgNode.classList.add('sh-fade-in');
    box.appendChild(svgNode);
    applySchem();
    fitSchemText();
  }
  let schemTipT = 0;
  function showSchemTip(sel) {
    clearTimeout(schemTipT);
    const tip = $('.sh-tip');
    let info = null;
    if (sel.type === 'cell') { const c = cellOf(sel.key); if (c) info = { title: c.label, line: c.line || c.about, tag: ['tracing', 'Real tracings in 3D'], swatch: c.color }; }
    else if (sel.type === 'lamina') info = lamInfo(sel.key);
    else if (sel.type === 'region') { const r = regionOf(sel.key); if (r) info = { title: r.label, line: r.sub, tag: ['allen', (r.allen || []).join(', ')], swatch: regionColor(r.key) }; }
    else if (sel.type === 'conn') { const c = connOf(sel.key); const v = verdictOf(sel.key); if (c) info = { title: c.label, line: c.about || '', tag: [v.status === 'supported' ? 'tracing' : 'allen', VERDICT_WORDS[v.status] || v.status] }; }
    if (!info) { tip.style.display = 'none'; return; }
    const r = $('.sh-stage').getBoundingClientRect();
    showTip(info, r.right - 330, r.top + 64);
  }
  function hideSchemTip() { schemTipT = setTimeout(() => { $('.sh-tip').style.display = 'none'; }, 120); }

  /* ==================================================================
     Cards: one system. A sticky head (kicker, name), a lede, the things
     you can do, then sections that fold (remembered by their heading).
     ================================================================== */
  const FOLDED = new Set(['References', 'Sources', 'The crowd', 'Method', 'Every stop', 'The recording']);
  function showCard(sel) {
    if (S.quiz && S.quiz.open && !(sel && sel.type === 'quiz')) S.quiz.open = false;
    const card = $('.sh-card');
    if (S.hover && S.hoverFrom === 'card') setHover(null, 'card');
    card.innerHTML = '';
    card.scrollTop = 0;
    card.classList.remove('scrolled');
    routeCard(card, sel);
    if (!sel || !['quiz', 'event', 'compose', 'pspike'].includes(sel.type)) foldCard(card);
    // rows that open something are reachable from the keyboard too
    card.querySelectorAll('.sh-check.link').forEach((n) => {
      n.tabIndex = 0;
      n.setAttribute('role', 'button');
      n.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); n.click(); } });
    });
  }
  function routeCard(card, sel) {
    if (!sel) return renderAbout(card);
    if (sel.type === 'compose') return renderCompose(card);
    if (sel.type === 'pspike') return renderPspike(card);
    if (sel.type === 'cell') return renderCell(card, cellOf(sel.key), sel.inst);
    if (sel.type === 'region') return renderRegion(card, regionOf(sel.key));
    if (sel.type === 'conn') return renderConn(card, connOf(sel.key));
    if (sel.type === 'lamina') return renderLamina(card, sel.key);
    if (sel.type === 'probe') return renderProbe(card);
    if (sel.type === 'checks') return renderChecks(card);
    if (sel.type === 'views') return renderViews(card, sel);
    if (sel.type === 'quiz') return renderQuiz(card);
    if (sel.type === 'event') return renderEventCard(card);
    if (sel.type === 'story') return renderStoryCard(card);
    if (sel.type === 'sextant') return renderSextantCard(card);
    if (sel.type === 'allen') return renderAllen(card, sel);
    return renderAbout(card);
  }
  const foldKey = (t) => t.replace(/\s*\(.*\)\s*$/, '').trim();
  function foldCard(card) {
    let cur = null;
    const fold = (title) => {
      const k = foldKey(title);
      const open = S.folds[k] != null ? S.folds[k] : !FOLDED.has(k);
      const d = el('details', { class: 'sh-fold', open: open ? '' : null });
      d.appendChild(el('summary', {}, [title]));
      d.addEventListener('toggle', () => { S.folds[k] = d.open; store.set({ folds: S.folds }); });
      return d;
    };
    for (const n of Array.from(card.children)) {
      if (n.classList.contains('sh-card-head')) continue;
      if (n.tagName === 'H3') { cur = fold(n.textContent); n.replaceWith(cur); continue; }
      if (n.classList.contains('sh-notes')) {
        const h = n.querySelector(':scope > h3');
        if (h) { const d = fold(h.textContent); h.remove(); n.replaceWith(d); d.appendChild(n); }
        cur = null;
        continue;
      }
      if (cur) cur.appendChild(n);
    }
  }
  function cardHead(kicker, title, o) {
    o = o || {};
    return el('div', { class: 'sh-card-head' }, [
      el('div', { class: 'sh-kicker' }, [].concat(kicker)),
      el('h2', {}, [o.lead || null, el('span', { text: title })]),
      o.extra || null,
    ]);
  }
  const swatch = (color, sq) => el('span', { class: 'sh-sw lg' + (sq ? ' sq' : ''), style: 'background:' + color });
  const refsList = (keys) => el('ol', { class: 'sh-refs' }, (keys || []).map((k) => el('li', { text: refText(k) })));
  const citeChips = (keys) => el('span', { class: 'sh-cites' }, (keys || []).map((k) => el('button', { type: 'button', class: 'sh-cite', text: refShort(k), title: refText(k), onclick: () => showRefs([k]) })));
  function showRefs(keys) {
    const card = $('.sh-card');
    const old = card.querySelector('.sh-refbox');
    if (old) old.remove();
    const box = el('div', { class: 'sh-src sh-refbox' }, [el('div', { class: 'sh-check-top' }, [el('b', { text: 'Reference' }),
      UI.button({ icon: 'close', cls: 'sm icon quiet', aria: 'Close', onclick: () => box.remove() })]), refsList(keys)]);
    const head = card.querySelector('.sh-card-head');
    if (head) head.after(box); else card.prepend(box);
    card.scrollTop = 0;
  }
  const hoverable = (sel) => ({ onpointerenter: () => setHover(sel, 'card'), onpointerleave: () => setHover(null, 'card') });
  function cellChip(k) {
    const c = cellOf(k);
    if (!c) return null;
    return el('button', Object.assign({ type: 'button', class: 'sh-chip', title: c.label, onclick: () => pick({ type: 'cell', key: k }, 'card') }, hoverable({ type: 'cell', key: k })),
      [el('span', { class: 'sh-sw', style: 'background:' + c.color }), c.short]);
  }
  function connRow(c) {
    const v = verdictOf(c.key);
    const name = (k) => (cellOf(k) || regionOf(k) || { label: k }).label;
    return el('div', Object.assign({ class: 'sh-check link', onclick: () => pick({ type: 'conn', key: c.key }, 'card') }, hoverable({ type: 'conn', key: c.key })), [
      el('div', { class: 'sh-check-top' }, [el('b', { text: c.label }), verdictChip(v)]),
      el('div', { text: name(c.from) + ' → ' + name(c.to) + (c.layer && c.layer.length ? ', in ' + c.layer.map((k) => (lamOf(k) || { label: k }).label).join(', ') : '') }),
    ]);
  }
  const tile = (icon, title, sub, on) => el('button', { type: 'button', class: 'sh-tile', onclick: on }, [UI.icon(icon), el('b', { text: title }), el('small', { text: sub })]);
  const hint = (k, t) => el('span', {}, [el('span', { class: 'sh-kbd', text: k }), t]);
  function renderAbout(card) {
    const kb = S.kb;
    card.appendChild(cardHead('Mouse brain atlas', 'Seahorse', { lead: el('span', { html: SEAHORSE_SVG, class: 'sh-logo' }) }));
    card.appendChild(el('p', { class: 'sh-lede', text: 'The mouse brain from the Allen atlas, and the hippocampus down to its layers and the cells we record. Everything on the stage can be pointed at: hover to read what it is and how we know, click to select it in every view.' }));
    card.appendChild(el('div', { class: 'sh-hint' }, [hint('Hover', 'to read'), hint('Click', 'to select'), hint('Drag', 'to turn'), hint('Scroll', 'to come closer')]));
    card.appendChild(el('h3', { text: 'Start here' }));
    const tours = BARRY.shLearn.tours(kb, { probeAp: 5400 - S.probe.ap * 1000 });
    card.appendChild(el('div', { class: 'sh-tiles' }, [
      tile('ride', 'Ride a signal', 'Entorhinal cortex to CA1, along four real cells that touch', () => startRide('trisynaptic')),
      tile('wave', 'Play a dentate spike', 'DS2 on the probe\'s 64 contacts, in whatever view you are in', () => playEvent('ds2')),
      tile('tour', 'Take a tour', tours[0] ? tours[0].label + ': ' + (tours[0].blurb || '') : 'Guided tours', () => { if (tours[0]) startTour(tours[0].key); }),
      tile('quiz', 'Quiz yourself', 'Cards drawn from the atlas, spaced like Anki', () => openQuiz()),
    ]));
    card.appendChild(el('h3', { text: 'Cells' }));
    card.appendChild(el('div', { class: 'sh-chips' }, kb.cells.map((c) => cellChip(c.key))));
    card.appendChild(el('h3', { text: 'What was checked' }));
    card.appendChild(el('div', { class: 'sh-tally' }, Object.entries(tally()).map(([k, n]) => el('span', {}, [verdictChip({ status: k }), String(n)]))));
    card.appendChild(el('div', { class: 'sh-actions' }, [UI.button({ icon: 'check', text: 'Open the checks', cls: 'sm', onclick: () => showCard({ type: 'checks' }) })]));
    if (kb.crowd) {
      card.appendChild(el('h3', { text: 'The crowd' }));
      card.appendChild(el('p', { class: 'sh-small', text: kb.crowd.note + (S.crowdN ? ' ' + S.crowdN.toLocaleString() + ' somata placed.' : '') + ' Up close, the cells in the section are drawn out with dendrites in the shape of their kind: drawn, not traced; a third of the granule cells and half the pyramids, so the layers stay readable.' }));
    }
    card.appendChild(el('h3', { text: 'Sources' }));
    card.appendChild(el('p', { class: 'sh-small', text: 'Anatomy: Allen Mouse Brain CCFv3 (Wang et al. 2020), 2017 annotation, with the Allen ARA Nissl at 10 µm. Connectivity tests: Allen Mouse Connectivity Atlas (Oh et al. 2014). Cells: NeuroMorpho.Org (Ascoli et al. 2007); whole-brain tracings from MouseLight (Winnubst et al. 2019). Built on this computer by tools/seahorse; nothing is fetched while you use the tab.' }));
  }
  function tally() {
    const t = {};
    Object.values(S.checks ? S.checks.connections : {}).forEach((v) => { t[v.status] = (t[v.status] || 0) + 1; });
    return t;
  }
  /* Everything that was tested, and how it came out (restored 11-24: the
     card had gone missing and the Checks button threw). */
  function renderChecks(card) {
    const ck = S.checks || {};
    card.appendChild(cardHead('Auto cross-check · run ' + (ck.ran || '?'), 'What was checked', { lead: el('span', { class: 'sh-logo' }, [UI.icon('check')]) }));
    card.appendChild(el('p', { class: 'sh-lede', text: 'Every connection was tested where public data can test it: Allen connectivity experiments for region-to-region claims, real tracings for cell-level ones, the Allen Nissl for the derived layers. The rest are cited, not tested.' }));
    card.appendChild(el('div', { class: 'sh-tally' }, Object.entries(tally()).map(([k, n]) => el('span', {}, [verdictChip({ status: k }), String(n)]))));
    const order = { 'not seen': 0, error: 0, weak: 1, consistent: 2, supported: 3, untested: 4, cited: 5 };
    const rows = S.kb.connections.slice().sort((a, b) => (order[verdictOf(a.key).status] ?? 9) - (order[verdictOf(b.key).status] ?? 9));
    card.appendChild(el('h3', { text: 'Connections (' + rows.length + ')' }));
    rows.forEach((c) => {
      const v = verdictOf(c.key);
      card.appendChild(el('div', Object.assign({ class: 'sh-check link', onclick: () => pick({ type: 'conn', key: c.key }, 'card') }, hoverable({ type: 'conn', key: c.key })),
        [el('div', { class: 'sh-check-top' }, [el('b', { text: c.label }), verdictChip(v)]), v.detail ? el('div', { text: v.detail }) : null]));
    });
    card.appendChild(el('h3', { text: 'Derived layers against the Nissl' }));
    (ck.lamina || []).forEach((l) => card.appendChild(el('div', Object.assign({ class: 'sh-check link', onclick: () => pick({ type: 'lamina', key: l.layer }, 'card') }, hoverable({ type: 'lamina', key: l.layer })),
      [el('div', { class: 'sh-check-top' }, [el('b', { text: (lamOf(l.layer) || { label: l.layer }).label }), verdictChip({ status: l.ok ? 'supported' : 'not seen' })]), el('div', { text: l.detail })])));
    card.appendChild(el('h3', { text: 'Where each cell landed' }));
    Object.entries(ck.cells || {}).forEach(([k, v]) => card.appendChild(el('div', { class: 'sh-check link', onclick: () => pick({ type: 'cell', key: typeOfInst(k) }, 'card') },
      [el('div', { class: 'sh-check-top' }, [el('b', { text: (cellOf(typeOfInst(k)) || { label: k }).label + (k !== typeOfInst(k) ? ' (' + k + ')' : '') }),
        verdictChip({ status: v.kind === 'drawn' ? 'untested' : v.soma_ok ? (v.identity === 'unconfirmed' ? 'weak' : 'supported') : 'not seen' })]),
        el('div', { text: (v.notes || []).join(' ') || ('Soma in ' + v.soma + '.') })])));
    if ((ck.findings || []).length) {
      card.appendChild(el('h3', { text: 'What the checks found' }));
      ck.findings.forEach((f) => card.appendChild(el('div', { class: 'sh-check', text: f.text })));
    }
    card.appendChild(el('h3', { text: 'Method' }));
    card.appendChild(el('p', { class: 'sh-small', text: ck.method || 'Allen: every experiment with its primary injection in the source; median projection density in the target against cerebellum (which none of these project to). Supported at median ≥ 0.002 and ≥ 5× control; weak when a quarter or more of the experiments reach 0.002. Tracings: the share of the exemplar\'s arbor in the named layers; this is evidence only for cells registered to the atlas by their authors.' }));
  }
  function tracingBox(inst) {
    const src = inst.source || {};
    const box = el('div', { class: 'sh-src' });
    const sto = inst.story || {};
    if (src.kind === 'drawn') {
      box.appendChild(el('div', { class: 'sh-check-top' }, [el('b', { text: 'Drawn' }), el('span', { class: 'sh-tag drawn', text: 'No public tracing exists' })]));
      if (src.note) box.appendChild(el('div', { text: src.note }));
    } else {
      box.appendChild(el('div', { class: 'sh-check-top' }, [el('b', { text: src.neuron_name + (inst.key !== inst.type ? '  (' + inst.key + ')' : '') }),
        el('span', { class: 'sh-tag ' + (src.kind === 'ccf' ? 'tracing' : 'placed'), text: src.kind === 'ccf' ? 'Registered by its authors' : 'Slice tracing, placed' })]));
      box.appendChild(el('div', { text: src.archive + ' · ' + (src.species || 'mouse') + ' · ' + (src.kind === 'ccf' ? 'traced through the whole brain' + (src.mirrored ? ', mirrored into the right hemisphere' : '')
        : 'placed by its layers (fit ' + ((src.fit || {}).score || '?') + ' of 1.1)') }));
      box.appendChild(el('div', { class: 'sh-small', text: 'Axon ' + (inst.axon_mm || 0) + ' mm · dendrites ' + (inst.dend_mm || 0) + ' mm · soma in ' + ((lamOf(inst.soma_lamina) || {}).label || inst.soma_allen) }));
      const links = el('div', { class: 'sh-actions' });
      if (src.url) links.appendChild(el('a', { href: src.url, target: '_blank', rel: 'noopener', text: 'NeuroMorpho record' }));
      (src.doi || []).forEach((d) => links.appendChild(el('a', { href: 'https://doi.org/' + d, target: '_blank', rel: 'noopener', text: 'doi:' + d })));
      if (links.childNodes.length) box.appendChild(links);
    }
    if (sto.meets) box.appendChild(el('div', { class: 'sh-small', text: 'Meets ' + sto.meets + '\'s axon in ' + ((lamOf(sto.layer) || {}).label || sto.layer) + ': '
      + sto.gap_um + ' µm apart where traced' + (sto.moved ? '; moved ' + Math.hypot(...sto.shift_um).toFixed(1) + ' µm to touch.' : '.') }));
    if (sto.reaches && sto.gap_um != null) box.appendChild(el('div', { class: 'sh-small', text: 'Placed so its axon reaches ' + sto.reaches + '\'s ' + ({ dend: 'dendrite', soma: 'soma', ais: 'axon initial segment' }[sto.what] || '') + ' (moved ' + sto.gap_um + ' µm).' }));
    return box;
  }
  function renderCell(card, c, instKey) {
    if (!c) return renderAbout(card);
    S.lastCell = c.key;
    card.appendChild(cardHead([(regionOf(c.region) || {}).label || 'Cell', el('span', { text: '·' }), c.sign === 'inh' ? 'inhibitory' : 'excitatory'], c.label, { lead: swatch(c.color) }));
    card.appendChild(el('p', { class: 'sh-lede', text: c.about }));
    const reach = S.reach;
    card.appendChild(el('div', { class: 'sh-actions' }, [
      UI.button({ text: 'Where does it lead?', cls: 'sm', pressed: !!(reach && reach.dir === 'out'), onclick: () => startReach(c.key, 'out') }),
      UI.button({ text: 'What feeds it?', cls: 'sm', pressed: !!(reach && reach.dir === 'in'), onclick: () => startReach(c.key, 'in') }),
      reach ? UI.button({ text: 'Next hop (' + (reach.hops + 1) + ')', cls: 'sm', disabled: !reach.frontier.length, onclick: nextHop }) : null,
      UI.button({ icon: 'frame', text: 'Fly to it', cls: 'sm', onclick: () => flyToCell(instKey || instancesOfType(c.key)[0]) }),
      rideFor(c.key) ? UI.button({ icon: 'ride', text: 'Ride from here', cls: 'sm', onclick: () => startRide(rideFor(c.key)) }) : null,
    ]));
    if (reach) card.appendChild(el('div', { class: 'sh-reach', text: reachText(reach) }));
    card.appendChild(el('h3', { text: 'Identity' }));
    card.appendChild(el('dl', {}, [
      el('dt', { text: 'Soma' }), el('dd', { text: c.soma }),
      el('dt', { text: 'Dendrites' }), el('dd', { text: c.dend }),
      el('dt', { text: 'Axon' }), el('dd', { text: c.axon }),
      c.markers ? el('dt', { text: 'Markers' }) : null, c.markers ? el('dd', { text: c.markers }) : null,
    ]));
    if ((c.phys || []).length || c.lab) {
      card.appendChild(el('h3', { text: 'Physiology' }));
      (c.phys || []).forEach((p) => card.appendChild(el('p', {}, [p.text + ' ', citeChips(p.refs)])));
      if (c.lab) card.appendChild(el('div', { class: 'sh-lab' }, [el('b', { text: 'For the lab: ' }), c.lab.text + ' ', citeChips(c.lab.refs)]));
    }
    card.appendChild(el('h3', { text: 'The tracing' + (instancesOfType(c.key).length > 1 ? 's' : '') }));
    if (S.blobs['cells.shb.gz']) instancesOfType(c.key).forEach((k) => card.appendChild(tracingBox(instOf(k))));
    else card.appendChild(el('p', { class: 'sh-small', text: 'Open the hippocampus in 3D, or a slice, to load the tracings.' }));
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
  /* For the schematic's boxes the Allen lines do not cover (a layer of a
     region, or a group of regions). */
  const REGION_ABOUT = {
    ctx: 'The association neocortex: where what reaches the hippocampus starts (through perirhinal and postrhinal cortex) and where what it sends out ends up.',
    lec2: 'Layer II of the lateral entorhinal cortex. Its fan cells send the lateral perforant path to the outer third of the dentate molecular layer and to CA3 lacunosum-moleculare.',
    mec2: 'Layer II of the medial entorhinal cortex, where grid cells are. Its stellate cells send the medial perforant path to the middle third of the dentate molecular layer.',
    ec3: 'Layer III pyramidal cells of both entorhinal areas: the temporoammonic path, straight to CA1 stratum lacunosum-moleculare and to the subiculum.',
    ec5: 'The deep layers (V and VI) of the entorhinal cortex take in CA1 and subiculum output and pass it on to the neocortex and back up to the superficial layers.',
    subc: 'Through the fimbria-fornix the hippocampus reaches the septum, the mammillary bodies, the nucleus accumbens and the hypothalamus.',
  };
  function renderRegion(card, r) {
    if (!r) return renderAbout(card);
    card.appendChild(cardHead(['Region', el('span', { text: '·' }), (r.allen || []).join(', ')], r.label, { lead: swatch(regionColor(r.key), true) }));
    card.appendChild(el('p', { class: 'sh-lede', text: (r.allen || []).map((a) => (S.kb.region_lines || {})[a]).filter(Boolean)[0] || REGION_ABOUT[r.key] || r.sub }));
    if ((r.cells || []).length) {
      card.appendChild(el('h3', { text: 'Cells here' }));
      card.appendChild(el('div', { class: 'sh-chips' }, r.cells.map((k) => cellChip(k))));
    }
    const conns = S.kb.connections.filter((c) => !c.hidden && [c.from, c.to].some((k) => k === r.key || (cellOf(k) && cellOf(k).region === r.key)));
    if (conns.length) { card.appendChild(el('h3', { text: 'In and out (' + conns.length + ')' })); conns.forEach((x) => card.appendChild(connRow(x))); }
    card.appendChild(notesBlock('region', r.key));
  }
  const RIDE_OF_CONN = { lpp: 'trisynaptic', mf_ca3: 'trisynaptic', sc: 'trisynaptic', ca1_sub: 'trisynaptic', mpp: 'ds2', mf_mc: 'dentate', mc_gc: 'dentate',
                         hipp_gc: 'dentate', pv_gc: 'dentate', aac_gc: 'dentate', rc: 'caside', ta: 'caside', olm_ca1: 'caside', ca1_olm: 'caside' };
  function renderConn(card, c) {
    if (!c) return renderAbout(card);
    const v = verdictOf(c.key);
    const name = (k) => (cellOf(k) || regionOf(k) || { label: k }).label;
    card.appendChild(cardHead((c.sign === 'inh' ? 'Inhibitory' : 'Excitatory') + ' connection', c.label, { extra: el('div', {}, [verdictChip(v)]) }));
    card.appendChild(el('p', { class: 'sh-lede', text: name(c.from) + ' → ' + name(c.to) + (c.layer ? ', ending in ' + c.layer.map((k) => (lamOf(k) || { label: k }).label).join(', ') : '') + '.' }));
    if (c.about) card.appendChild(el('p', { text: c.about }));
    if (RIDE_OF_CONN[c.key]) card.appendChild(el('div', { class: 'sh-actions' }, [UI.button({ icon: 'ride', text: 'Ride it', cls: 'sm', onclick: () => startRide(RIDE_OF_CONN[c.key]) })]));
    card.appendChild(el('h3', { text: 'Checked against data' }));
    const box = el('div', { class: 'sh-src' }, [el('div', {}, [verdictChip(v)]), v.detail ? el('div', { text: v.detail }) : null]);
    if (v.top && v.top.length) box.appendChild(el('div', { class: 'sh-small', text: 'Strongest: ' + v.top.slice(0, 3).map((x) => 'exp. ' + x.id + ' (' + x.line + ') ' + x.density).join('; ') }));
    card.appendChild(box);
    card.appendChild(notesBlock('conn', c.key));
    card.appendChild(el('h3', { text: 'References' }));
    card.appendChild(refsList(c.refs));
  }
  function renderLamina(card, key) {
    const l = lamOf(key) || { label: key, name: '', how: '' };
    const n = S.checks && S.checks.nissl_means ? S.checks.nissl_means[key] : null;
    const rk = regionOfLayer(key);
    card.appendChild(cardHead(['Layer', rk ? el('span', { text: '·' }) : null, rk ? (regionOf(rk) || {}).label : null].filter(Boolean), l.label + ' · ' + l.name, { lead: swatch(lamColor(key), true) }));
    if (l.line) card.appendChild(el('p', { class: 'sh-lede', text: l.line }));
    if (BARRY.shLearn.RECORDS[key]) card.appendChild(el('div', { class: 'sh-lab' }, [el('b', { text: 'On a probe: ' }), BARRY.shLearn.RECORDS[key]]));
    card.appendChild(el('dl', {}, [el('dt', { text: 'Made by' }), el('dd', { text: l.how || 'Allen annotation' }),
      n != null ? el('dt', { text: 'Nissl' }) : null, n != null ? el('dd', { text: 'mean ' + n + ' of 255 (' + ((S.checks || {}).nissl_source || 'Allen Nissl') + ')' }) : null]));
    const lc = (S.checks && S.checks.lamina || []).find((x) => x.layer === key);
    if (lc) card.appendChild(el('div', { class: 'sh-src' }, [verdictChip({ status: lc.ok ? 'supported' : 'not seen' }), el('div', { text: lc.detail })]));
    const ending = S.kb.connections.filter((c) => (c.layer || []).includes(key));
    if (ending.length) { card.appendChild(el('h3', { text: 'Inputs that end here (' + ending.length + ')' })); ending.forEach((x) => card.appendChild(connRow(x))); }
    const here = S.kb.cells.filter((c) => instancesOfType(c.key).some((k) => (instOf(k) || {}).soma_lamina === key));
    if (here.length) {
      card.appendChild(el('h3', { text: 'Somata here' }));
      card.appendChild(el('div', { class: 'sh-chips' }, here.map((c) => cellChip(c.key))));
    }
    card.appendChild(notesBlock('lamina', key));
  }
  function renderAllen(card, sel) {
    const st = sel.idx ? allenStruct(sel.idx) : {};
    card.appendChild(cardHead('Allen CCFv3 structure', sel.name || sel.key, { lead: st.color ? swatch(st.color, true) : null }));
    card.appendChild(el('p', { class: 'sh-lede', text: (sel.key ? sel.key + ' in the Allen Mouse Brain Common Coordinate Framework (2017 annotation). ' : '') + 'Seahorse adds detail only inside the hippocampal formation; elsewhere it shows the Allen atlas as it is.' }));
    const line = (S.kb.region_lines || {})[sel.key];
    if (line) card.appendChild(el('p', { text: line }));
    card.appendChild(notesBlock('allen', sel.key));
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
        const mine = R.dir === 'out' ? c.from === t : c.to === t;
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
        UI.button({ text: 'Delete', cls: 'sm quiet danger', onclick: async () => { if (!confirm('Delete this note for everyone?')) return; await saveNote({ id: n.id, delete: true }); showCard(S.sel); renderRail(); } })]),
    ])));
    const ta = el('textarea', { rows: 2, placeholder: 'A note for the lab (shared with every lab machine)…' });
    box.appendChild(ta);
    box.appendChild(el('div', { class: 'sh-actions' }, [UI.button({ icon: 'note', text: 'Add note', cls: 'sm', onclick: async () => {
      const t = ta.value.trim();
      if (!t) return;
      await saveNote({ target: { type, key }, text: t });
      showCard(S.sel); renderRail();
    } })]));
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
    renderNav();
  }
  const viewCode = (v) => 'seahorse:' + btoa(unescape(encodeURIComponent(JSON.stringify(v))));
  function parseCode(s) {
    const m = String(s || '').trim().match(/^seahorse:([A-Za-z0-9+/=]+)$/);
    if (!m) return null;
    try { return JSON.parse(decodeURIComponent(escape(atob(m[1])))); } catch (e) { return null; }
  }
  function renderViews(card, o) {
    card.appendChild(cardHead('Shared with the lab', 'Saved views', { lead: el('span', { class: 'sh-logo' }, [UI.icon('views')]) }));
    card.appendChild(el('p', { class: 'sh-lede', text: 'A view keeps the mode, the camera, the cut, the section, the probe and the selection. Views travel to every lab machine with the shared records; Copy code gives a line you can paste into Seahorse\'s search box anywhere.' }));
    const name = el('input', { type: 'text', class: 'sh-input', placeholder: 'Name this view', title: 'For example: Probe through dorsal DG' });
    card.appendChild(el('div', { class: 'sh-row' }, [name, UI.button({ icon: 'bookmark', text: 'Save this view', cls: 'solid', onclick: async () => {
      try {
        const r = await apiPost('/api/seahorse/view', { name: name.value || 'Untitled view', state: captureView() });
        if (r && r.ok) { S.lab.views = r.views || {}; toast('Saved for the lab.', 'ok'); showCard({ type: 'views' }); }
        else toast((r && r.error) || 'Not saved.', 'err');
      } catch (e) { toast('Not saved: ' + e.message, 'err'); }
    } })]));
    if (o && o.focus) setTimeout(() => name.focus(), 60);
    const list = Object.entries(S.lab.views || {}).filter(([, v]) => v).sort((a, b) => (b[1].at || '').localeCompare(a[1].at || ''));
    card.appendChild(el('h3', { text: 'Views (' + list.length + ')' }));
    if (!list.length) card.appendChild(el('p', { class: 'sh-small', text: 'No saved views yet.' }));
    list.forEach(([id, v]) => card.appendChild(el('div', { class: 'sh-check' }, [
      el('div', { class: 'sh-check-top' }, [el('b', { text: v.name }), el('span', { class: 'sh-small', text: (v.by || 'someone') + ' · ' + (v.at || '').slice(0, 10) })]),
      el('div', { class: 'sh-actions' }, [
        UI.button({ text: 'Open', cls: 'sm', onclick: () => openView(v.state) }),
        UI.button({ text: 'Copy code', cls: 'sm quiet', onclick: async () => { try { await navigator.clipboard.writeText(viewCode(v.state)); toast('Copied. Paste it into Seahorse\'s search box to open this view.', 'ok'); } catch (e) { toast('The clipboard is not available here.', 'err'); } } }),
        UI.button({ text: 'Delete', cls: 'sm quiet danger', onclick: async () => {
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
    if (isSext()) { sextStage(S.play); updateLabels(); return; }
    // a story draws its own probe (the recorded one) on the section
    const pr = S.probe.on && !isStory() ? probeForStage() : null;
    // the ribbon beside the shank: each contact in its layer's color
    if (pr && S.blobs['brain50.shb.gz']) pr.ribbon = contactLayers().map((k) => (k ? lamColor(k) : null) || '#8a8a8a');
    S.stage.setProbe(pr);
    updateLabels();
  }
  function showProbe(on) {
    S.probe.on = !!on;
    store.set({ probe: probeSave() });
    syncProbe();
    if (S.sel && S.sel.type === 'probe') showCard(S.sel);
  }
  const probeSave = () => ({ on: S.probe.on, ap: S.probe.ap, ml: S.probe.ml, depth: S.probe.depth, angML: S.probe.angML, angAP: S.probe.angAP });
  function onProbeDrag(ccf, end) {
    if (isSext() && S.play.review) { sextDrag(ccf, end); return; }
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
    card.appendChild(cardHead('Probe placement · no recording attached', 'Linear probe, ' + P.contacts + ' contacts', { lead: el('span', { class: 'sh-logo' }, [UI.icon('probe')]),
      extra: el('div', {}, [UI.seg('', SHOWN, S.probe.on, (k) => showProbe(k), { aria: 'Probe', small: true })]) }));
    const f = (label, key, step, unit) => el('label', { class: 'sh-coord' }, [el('span', { text: label }),
      el('input', { type: 'number', step, value: P[key], onchange: (e) => { P[key] = +e.target.value; store.set({ probe: probeSave() }); syncProbe(); showCard({ type: 'probe' }); } }),
      el('small', { text: unit })]);
    card.appendChild(el('div', { class: 'sh-coords' }, [f('AP', 'ap', 0.05, 'mm from bregma'), f('ML', 'ml', 0.05, 'mm, + right'), f('Depth', 'depth', 0.05, 'mm along the shank'),
      f('ML angle', 'angML', 1, '° (tip lateral +)'), f('AP angle', 'angAP', 1, '° (tip posterior +)')]));
    card.appendChild(el('p', { class: 'sh-small', text: 'Tip at CCF ' + P.tip.map((x) => Math.round(x)).join(', ') + ' µm. Depth is from the brain surface where the shank enters (approximate: the CCF is an average brain, not stereotaxic). Contacts every ' + P.pitch + ' µm; contact 1 is nearest the tip. Drag the tip on a section to move it.' }));
    card.appendChild(el('div', { class: 'sh-actions' }, [
      UI.button({ icon: 'section', text: 'Section down the probe', cls: 'sm', onclick: sliceDownProbe }),
      UI.button({ icon: 'wave', text: 'Model DS1 here', cls: 'sm', onclick: () => playEvent('ds1') }),
      UI.button({ icon: 'wave', text: 'Model DS2 here', cls: 'sm', onclick: () => playEvent('ds2') }),
    ]));
    card.appendChild(el('h3', { text: 'Which contacts sit in which layer' }));
    card.appendChild(el('div', { class: 'sh-probe-table' }, probeRuns().slice().reverse().map((r) => el('div', {
      onpointerenter: () => r.key && setHover({ type: 'lamina', key: r.key }, 'card'), onpointerleave: () => setHover(null, 'card') }, [
      el('span', { class: 'ch', text: r.from === r.to ? 'ch ' + r.from : 'ch ' + r.from + '–' + r.to }),
      el('span', { class: 'sh-sw sq', style: 'background:' + (r.key ? lamColor(r.key) : 'var(--sh-ink-3)') }),
      el('span', { text: r.name + (r.full ? ' · ' + r.full : '') }),
    ]))));
  }

  /* ==================================================================
     The crowd: one dot per cell
     ================================================================== */
  function ensureCrowd() {
    if (S.crowdMade || !S.crowd || !S.stage || !S.volumesUp) return;
    S.crowdMade = true;
    setTimeout(() => { makeCrowd().catch((e) => reportClientError('seahorse:crowd', e.message, e.stack)); }, 60);
  }
  /* Drawn-out crowd cells: their shape, and which way their dendrites run
     (toward these layers, away from those). Principal cells are the
     crowd; the interneurons among them are quieter dots, so the layers
     still read. */
  const GLYPH = {
    gc: { shape: 'gc', alpha: 0.2, every: 3, dot: 0.9, to: ['iml1', 'iml2', 'mml1', 'mml2', 'oml1', 'oml2'], away: ['hil'] },
    ca1: { shape: 'pyr1', alpha: 0.24, every: 2, dot: 0.9, to: ['ca1sr', 'ca1slm'], away: ['ca1so', 'alv'] },
    ca3: { shape: 'pyr3', alpha: 0.28, every: 2, dot: 0.9, to: ['ca3slu', 'ca3sr', 'ca3slm', 'ca2sr', 'ca2slm'], away: ['ca3so', 'ca2so', 'alv'] },
    mc: { shape: 'multi', alpha: 0.4, dot: 0.75 },
    hipp: { shape: 'hipp', alpha: 0.4, dot: 0.7 },
    pvbc: { shape: 'basket', alpha: 0.16, every: 2, dot: 0.42 },
  };
  /* the finest layer label at a point (no Allen lookup: this runs for every drawn cell) */
  function labAt(ap, dv, ml) {
    if (ml < 5700) ml = 11400 - ml;
    const F = S.blobs['fine10.shb.gz'], H = S.blobs['hip20.shb.gz'];
    if (F) {
      const o = F.header.origin_um, sh = F.header.shape;
      const i = Math.floor((ap - o[0]) / 10), j = Math.floor((dv - o[1]) / 10), k = Math.floor((ml - o[2]) / 10);
      if (i >= 0 && j >= 0 && k >= 0 && i < sh[0] && j < sh[1] && k < sh[2]) return F.arrays.labels[(i * sh[1] + j) * sh[2] + k];
    }
    if (H) {
      const o = H.header.origin_um, sh = H.header.arrays[0].shape;
      const i = Math.floor((ap - o[0]) / 20), j = Math.floor((dv - o[1]) / 20), k = Math.floor((ml - o[2]) / 20);
      if (i >= 0 && j >= 0 && k >= 0 && i < sh[0] && j < sh[1] && k < sh[2]) return H.arrays.labels[(i * sh[1] + j) * sh[2] + k];
    }
    return 0;
  }
  // 14 directions (the 6 axes and 8 diagonals), two distances: enough to tell which way a layer lies
  const DIRS26 = (() => { const out = []; for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) for (let c = -1; c <= 1; c++) { const n = Math.abs(a) + Math.abs(b) + Math.abs(c); if (n !== 1 && n !== 3) continue; const l = Math.hypot(a, b, c); out.push([a / l, b / l, c / l]); } return out; })();
  function orientAt(kd, ccf) {
    if (!kd || !kd.orient) return null;
    let x = 0, y = 0, z = 0;
    for (const d of DIRS26) {
      for (const r of [70, 170]) {
        const c = labAt(ccf[0] + d[0] * r, ccf[1] + d[1] * r, ccf[2] + d[2] * r);
        const w = kd.to.has(c) ? 1 : kd.away.has(c) ? -1 : 0;
        if (w) { x += d[0] * w; y += d[1] * w; z += d[2] * w; }
      }
    }
    return (x || y || z) ? [x, y, z] : null;
  }
  /* Built in slices of about 25 ms so opening the hippocampus never
     freezes the page (it took 1.4 s in one go: sweep 1, 11-21). */
  async function makeCrowd() {
    const t00 = performance.now();
    let t = t00;
    const breathe = async () => { if (performance.now() - t > 25) { await new Promise((r) => setTimeout(r, 0)); t = performance.now(); } };
    const H = S.blobs['hip20.shb.gz'], F = S.blobs['fine10.shb.gz'];
    const spec = (S.kb.crowd || {}).kinds || [];
    if (!H || !spec.length) return;
    const codeOf = (k) => (lamOf(k) || {}).code;
    // code -> bit mask of the kinds that live in it
    const mask = new Uint16Array(256);
    spec.forEach((sp, i) => sp.layers.forEach((k) => { const c = codeOf(k); if (c) mask[c] |= 1 << i; }));
    const lists = spec.map(() => ({ fine: [], hip: [] }));
    const fo = F ? F.header.origin_um : null, fs = F ? F.header.shape : null;
    if (F) {
      const L = F.arrays.labels, row = fs[1] * fs[2];
      for (let n0 = 0; n0 < L.length; n0 += row) {
        const n1 = Math.min(L.length, n0 + row);
        for (let n = n0; n < n1; n++) { const m = mask[L[n]]; if (m) for (let k = 0; m >> k; k++) if (m & (1 << k)) lists[k].fine.push(n); }
        await breathe();
      }
    }
    const ho = H.header.origin_um, hs = H.header.arrays[0].shape, LH = H.arrays.labels;
    const inFine = (ap, dv, ml) => F && ap >= fo[0] && dv >= fo[1] && ml >= fo[2] && ap < fo[0] + fs[0] * 10 && dv < fo[1] + fs[1] * 10 && ml < fo[2] + fs[2] * 10;
    for (let i = 0; i < hs[0]; i++) {
      for (let j = 0; j < hs[1]; j++) for (let k = 0; k < hs[2]; k++) {
        const n = (i * hs[1] + j) * hs[2] + k;
        const m = mask[LH[n]];
        if (!m) continue;
        if (inFine(ho[0] + i * 20 + 10, ho[1] + j * 20 + 10, ho[2] + k * 20 + 10)) continue;
        for (let kk = 0; m >> kk; kk++) if (m & (1 << kk)) lists[kk].hip.push(n);
      }
      await breathe();
    }
    let seed = 12345;
    const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    const pos = [], col = [], size = [], kind = [], alpha = [];
    let total = 0;
    let tick = 0;
    for (let si = 0; si < spec.length; si++) {
      const s = spec[si];
      const vol = lists[si].fine.length * 1000 + lists[si].hip.length * 8000;
      if (!vol) continue;
      const per = s.total ? s.total / vol : s.per_um3;
      const c = hexRgb((cellOf(s.key) || {}).color || '#aaa').map((x) => x / 255);
      const a = (GLYPH[s.key] || GLYPH.mc).dot;
      const put = (ap, dv, ml) => {
        pos.push((ml - 5700) / 1000, (4000 - dv) / 1000, (ap - 6600) / 1000);
        col.push(c[0] * 0.82, c[1] * 0.82, c[2] * 0.82);
        size.push(s.soma_um / 1000);
        kind.push(si);
        alpha.push(a);
        total++;
      };
      for (const n of lists[si].fine) {
        if ((++tick & 4095) === 0) await breathe();
        let m = per * 1000; let cnt = Math.floor(m); if (rnd() < m - cnt) cnt++;
        if (!cnt) continue;
        const i = Math.floor(n / (fs[1] * fs[2])), j = Math.floor(n / fs[2]) % fs[1], k = n % fs[2];
        for (let q = 0; q < cnt; q++) put(fo[0] + (i + rnd()) * 10, fo[1] + (j + rnd()) * 10, fo[2] + (k + rnd()) * 10);
      }
      for (const n of lists[si].hip) {
        if ((++tick & 4095) === 0) await breathe();
        let m = per * 8000; let cnt = Math.floor(m); if (rnd() < m - cnt) cnt++;
        if (!cnt) continue;
        const i = Math.floor(n / (hs[1] * hs[2])), j = Math.floor(n / hs[2]) % hs[1], k = n % hs[2];
        for (let q = 0; q < cnt; q++) put(ho[0] + (i + rnd()) * 20, ho[1] + (j + rnd()) * 20, ho[2] + (k + rnd()) * 20);
      }
    }
    S.crowdN = total;
    const kinds = spec.map((s) => {
      const g = GLYPH[s.key] || GLYPH.mc;
      const c = hexRgb((cellOf(s.key) || {}).color || '#aaa').map((x) => x / 255);
      return { shape: g.shape, col: c, alpha: g.alpha, every: g.every || 1, orient: !!g.to,
               to: new Set((g.to || []).map(codeOf).filter(Boolean)), away: new Set((g.away || []).map(codeOf).filter(Boolean)) };
    });
    if (!S.stage) return;
    S.times.crowd = Math.round(performance.now() - t00);
    S.stage.setCrowd({ pos: new Float32Array(pos), col: new Float32Array(col), size: new Float32Array(size), kind: new Uint8Array(kind), alpha: new Float32Array(alpha),
                       kinds, orient: (ki, ccf) => orientAt(kinds[ki], ccf) });
    S.stage.showCrowd(S.crowd);
  }

  /* ==================================================================
     Rides
     ================================================================== */
  async function startRide(key, o) {
    o = o || {};
    if (!o.fromTour) endTour();
    stopPlay(true);
    UI.closeAll();
    const ok = await need(['three', 'mesh_brain.shb.gz', 'mesh_hpf.shb.gz', 'mesh_lamina.shb.gz', 'cells.shb.gz', 'rides.json', 'brain50.shb.gz', 'hip20.shb.gz', 'fine10.shb.gz'],
      'Getting the ride ready', 'The cells, where they touch, and the sections the cut will paint.');
    if (!ok) return;
    const ride = (S.rides.rides || []).find((r) => r.key === key);
    if (!ride) return;
    if (S.mode !== '3d') await setMode('3d');
    if (S.level === 'brain') await setLevel('hpf');
    S.story = true;
    S.play = { kind: 'ride', key, ride, i: 0, fromTour: o.fromTour || null, sink: null, source: null };
    if (ride.kind === 'event' && BARRY.shPhys.EVENTS[key]) S.play.event = key;
    S.focus = { cells: new Set(), regionKeys: new Set(), conns: new Set(), layers: new Set() };
    S.stage.focus(null);
    showExtras();
    showTip(null);
    syncPaths();
    S.stage.ride(ride.steps, {
      auto: !!S.rideAuto,
      onHold: () => { if (isRide()) renderDock(); },
      onStep: (i, st) => onRideStep(i, st),
      onSynapse: (i, st) => showInset(st),
      onDone: () => onRideDone(),
    });
    renderNav();
    renderTools();
    renderDock();
    renderRail();
    updateLabels();
  }
  function onRideStep(i, st) {
    if (!isRide()) return;
    S.play.i = i;
    S.play.step = st;
    // the map lights what is being crossed
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
    renderDock();
  }
  /* the somata the ride went through, to frame when it ends */
  function ridePts(ride) {
    const keys = [...new Set((ride.steps || []).map((s) => s.cell).filter(Boolean))];
    return keys.map((k) => S.stage.cellSomaW(k)).filter(Boolean);
  }
  function onRideDone() {
    const P = S.play;
    if (!P || P.kind !== 'ride') return;
    P.done = true;
    hideInset();
    renderDock();
    if (S.rec && S.rec.untilDone) stopRecord();
    // hold on the last moment, then fade back to the light stage and glide
    // out to everything the ride went through (no snap, no lost camera)
    setTimeout(() => {
      if (S.play !== P) return;
      const tour = P.fromTour;
      settleRide(P);
      if (tour) resumeTour(tour);
    }, reducedMotion() ? 0 : 1400);
  }
  function settleRide(P) {
    if (S.stage) S.stage.settle(ridePts(P.ride), 1800);
    S.play = null;
    syncPaths();
    const rt = $('.sh-ridetag'); if (rt) rt.remove();
    hideInset();
    showExtras();
    S.focus = S.sel ? focusFor(S.sel) : null;
    applyFocusAll();
    applyCut();
    renderNav();
    renderTools();
    renderDock();
    renderRail();
    updateLabels();
  }
  function stopPlay(quiet) {
    if (!S.play) return;
    const p = S.play;
    if (p.kind === 'ride' && S.stage) {
      if (!quiet && S.mode === '3d') { settleRide(p); return; }
      S.stage.stopRide(true);
      S.play = null;
      syncPaths();
    }
    if (p.kind === 'event') { stopEventAnim(); if (S.stage && S.stage.setPulse) S.stage.setPulse(null); }
    if (p.kind === 'story') endStory(p);
    if (p.kind === 'sextant') endSextant(p);
    S.play = null;
    if (p.kind === 'event' || p.kind === 'story') applyHighlights();      // the paint goes with it
    hideInset();
    // an event's model panel and a story's card belong to them: give the card back
    if (($('.sh-card .sh-lam') || $('.sh-card .sh-story-head') || $('.sh-card .sh-sext-head')) && !(S.quiz && S.quiz.open)) showCard(S.sel);
    const rt = $('.sh-ridetag'); if (rt) rt.remove();
    showExtras();
    if (p.kind === 'story' || p.kind === 'sextant') { syncProbe(); placeMini(); renderNav(); renderTools(); renderDock(); renderRail(); applyCut(); updateLabels(); }
    if (!quiet) {
      S.focus = S.sel ? focusFor(S.sel) : null;
      applyFocusAll();
      applyCut();
      renderNav();
      renderTools();
      renderDock();
      renderRail();
      updateLabels();
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
    const text = (t ? (cellOf(t) || {}).short + (inst && inst.source && inst.source.neuron_name ? ' ' + inst.source.neuron_name : '') : 'drawn path') + (st.layer ? ' · ' + ((lamOf(st.layer) || {}).label || st.layer) : '');
    if (tag.textContent !== text) tag.textContent = text;
    tag.style.transform = 'translate(' + Math.round(p[0] + 16) + 'px,' + Math.round(p[1] - 30) + 'px)';
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
    box.appendChild(el('div', { class: 'sh-inset-k', text: 'At the synapse' }));
    box.appendChild(el('div', { class: 'sh-inset-art', html: synapseArt(st.synapse, preC, postC) }));
    box.appendChild(el('div', { class: 'sh-inset-title', text: syn.title }));
    box.appendChild(el('div', { class: 'sh-inset-say', text: syn.say }));
    box.appendChild(citeChips(syn.refs));
    box.style.display = 'flex';
    box.classList.remove('sh-pop-in'); void box.offsetWidth; box.classList.add('sh-pop-in');
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
    const wrap = (s) => `<svg viewBox="0 0 260 130" width="100%" height="118" xmlns="http://www.w3.org/2000/svg" style="font-family:var(--sans)">${s}</svg>`;
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
     Events: model laminar profiles, played wherever you are
     ================================================================== */
  /* What each source sets off, for every view: the cells that fire, the
     drawn bundle that carries it, the regions a volley crosses at the
     whole-brain scale, and the connections lit in the map. */
  const SOURCES = {
    lec: { label: 'LEC II', cells: ['fan'], from: 'ENTl', to: 'DG', conns: ['lpp'], regions: ['lec2', 'dg'] },
    mec: { label: 'MEC II', cells: ['stel'], path: 'mpp', from: 'ENTm', to: 'DG', conns: ['mpp'], regions: ['mec2', 'dg'] },
    ca3: { label: 'CA3', cells: ['ca3'], then: ['ca1'], from: 'CA3', to: 'CA1', conns: ['sc', 'rc'], regions: ['ca3', 'ca1'] },
    ec3: { label: 'EC III', cells: [], path: 'ta', from: 'ENTm', to: 'CA1', conns: ['ta'], regions: ['ec3', 'ca1'] },
    burst: { label: 'Hilar interneurons', cells: ['hipp', 'pvbc'], conns: ['hipp_gc', 'pv_gc'], regions: ['dg'] },
    theta: { label: 'Theta', cells: [], path: 'ta', conns: ['ta', 'lpp', 'mpp'], regions: ['ec3', 'ca1', 'dg'] },
  };
  const SPEEDS = [[0.02, '1/50'], [0.05, '1/20'], [0.2, '1/5']];
  const firstSentence = (t) => (String(t || '').match(/^.*?[.!?](?=\s|$)/) || [String(t || '')])[0];
  async function playEvent(key, o) {
    o = o || {};
    UI.closeAll();
    if (key === 'pspike') { if (!o.fromTour) endTour(); stopPlay(true); showCard({ type: 'pspike' }); renderDock(); return; }
    if (!o.fromTour) endTour();
    const ev = key === 'custom' ? BARRY.shPhys.compose(S.compose) : BARRY.shPhys.EVENTS[key];
    if (!ev) { toast('Switch on at least one source to play your event.', 'warn'); return; }
    const files = ['brain50.shb.gz', 'hip20.shb.gz', 'fine10.shb.gz'];
    if (S.mode === '3d' && S.stage) files.push('mesh_hpf.shb.gz', 'mesh_lamina.shb.gz', 'cells.shb.gz', 'rides.json');
    const ok = await need(files, 'Getting the layers ready', 'The event is read by the probe from the layers it crosses.');
    if (!ok) return;
    stopPlay(true);
    if (S.mode === 'slice' && !S.probe.on) { S.probe.on = true; syncProbe(); }
    const layers = contactLayers();
    const z = layers.map((_, i) => S.probe.first + i * S.probe.pitch);
    const model = BARRY.shPhys.compute(ev, layers, z);
    const speed = SPEEDS.some(([v]) => v === S.evSpeed) ? S.evSpeed : (ev.ms > 300 ? 0.2 : 0.02);
    S.play = { kind: 'event', key, ev, model, t: 0, speed, paused: false, fired: new Set(), fromTour: o.fromTour || null, sink: [], source: [], sig: '' };
    // the map lights the pathways the event runs along
    const f = { cells: new Set(), regionKeys: new Set(), conns: new Set(), layers: new Set() };
    (ev.drives || []).forEach((d) => { const s = SOURCES[d.src]; if (s) { s.conns.forEach((c) => f.conns.add(c)); s.regions.forEach((r) => f.regionKeys.add(r)); } });
    S.focus = f;
    applySchem();
    if (reducedMotion()) { peakMoment(S.play); S.play.paused = true; }
    if (o.card !== false) showEventPanel();
    renderDock();
    renderRail();
    startEventClock();
  }
  /* the moment of the strongest current, for a still picture */
  function peakMoment(P) {
    let best = 0, bt = 0;
    for (let t = 0; t <= P.ev.ms; t += 1) {
      let m = 0;
      for (const v of BARRY.shPhys.layerCsd(P.ev, t).values()) m = Math.max(m, Math.abs(v));
      if (m > best) { best = m; bt = t; }
    }
    P.t = bt;
    (P.ev.drives || []).forEach((d, i) => { if (d.t <= bt) P.fired.add(i); });
  }
  function liveCsd(P) {
    const m = BARRY.shPhys.layerCsd(P.ev, P.t);
    const cm = P.model.cmax || 1;
    for (const [k, v] of m) m.set(k, v / cm);
    return m;
  }
  let evRaf = 0, evLast = 0;
  function startEventClock() {
    if (evRaf) cancelAnimationFrame(evRaf);
    evLast = performance.now();
    const tick = (now) => {
      const P = S.play;
      if (!P || P.kind !== 'event') { evRaf = 0; return; }
      const dt = Math.min(100, now - evLast);
      evLast = now;
      if (!P.paused) {
        P.t += dt * P.speed;
        if (P.t >= P.ev.ms) {
          if (S.evLoop) { P.t = 0; P.fired.clear(); }
          else { P.t = P.ev.ms; P.paused = true; syncEventPlay(); }
        }
      }
      eventFrame(P);
      evRaf = requestAnimationFrame(tick);
    };
    evRaf = requestAnimationFrame(tick);
  }
  function eventFrame(P) {
    // what fires now
    (P.ev.drives || []).forEach((d, i) => { if (d.t <= P.t && !P.fired.has(i)) { P.fired.add(i); fireDrive(d, P); } });
    if (P.lastT === P.t) return;
    P.lastT = P.t;
    applyHighlights();
    // the map's sink and source boxes follow the moment
    const live = liveCsd(P), sink = [], source = [];
    for (const [k, v] of live) { if (v < -0.15) sink.push(k); else if (v > 0.15) source.push(k); }
    const sig = sink.join(',') + '|' + source.join(',');
    if (sig !== P.sig) { P.sig = sig; P.sink = sink; P.source = source; applySchem(); }
    const cv = $('.sh-card canvas.sh-lam');
    if (cv) BARRY.shPhys.draw(cv, P.model, { cursor: P.t, layerColors: S.kb.lamina_colors, labelOf: (k) => (lamOf(k) || {}).label, ink: tok('--text-2', '#888'), accent: tok('--accent', '#e5a823'),
      font: tok('--sans', 'sans-serif'), sink: SINK, source: SOURCE });
    const sc = $('.sh-tr-scrub');
    if (sc && sc.set) sc.set(P.t);
  }
  /* One source going off, drawn at the scale you are looking at. */
  function fireDrive(d, P) {
    const s = SOURCES[d.src];
    const st = S.stage;
    if (!s || !st || S.mode === 'schematic') return;
    const dur = Math.max(700, Math.min(3600, 24 / P.speed));
    if (S.mode === '3d' && S.level === 'brain') {
      const col = (cellOf(s.cells[0]) || {}).color || '#7a8fd9';
      if (s.from && s.to) {
        const a = st.centroid('hpf', s.from, true), b = st.centroid('hpf', s.to, true);
        if (a && b) st.volley(a, b, col, dur);
      } else {
        const c = st.centroid('hpf', s.to || 'DG', true) || st.centroid('hpf', 'CA1', true);
        if (c) st.flareAt(c, col, dur);
      }
      return;
    }
    if (S.mode === '3d') {
      s.cells.forEach((t) => instancesOfType(t).forEach((k) => st.pulseCell(k, dur)));
      (s.then || []).forEach((t) => setTimeout(() => { if (S.play === P) instancesOfType(t).forEach((k) => st.pulseCell(k, dur)); }, dur * 0.4));
      if (s.path && S.paths) st.pulsePath(s.path, dur);
    }
  }
  /* The laminar panel for the playing event, in the card. */
  function showEventPanel() {
    const P = S.play;
    if (!P || P.kind !== 'event') return;
    const ev = P.ev;
    const card = $('.sh-card');
    card.innerHTML = '';
    card.classList.remove('scrolled');
    card.appendChild(cardHead('Model · not a recording', ev.label + ' on the probe\'s ' + S.probe.contacts + ' contacts', { lead: el('span', { class: 'sh-logo' }, [UI.icon('wave')]) }));
    card.appendChild(el('p', { class: 'sh-lede' }, [ev.say + ' ', citeChips(ev.refs)]));
    card.appendChild(el('canvas', { class: 'sh-lam' }));
    card.appendChild(el('div', { class: 'sh-lam-legend' }, [el('span', { class: 'sink', text: 'sink' }), el('span', { class: 'source', text: 'source' }),
      el('span', { text: 'lines: potential on every other contact; the shallowest contact at the top' })]));
    card.appendChild(el('p', { class: 'sh-small', text: 'Currents placed in the layers the literature names, read by each contact\'s layer; potentials from the laminar disc model (Nicholson & Freeman 1975). Shape, not amplitude. The same currents light the layers in the sections as the event plays.' }));
    P.lastT = null;
  }
  function eventChips(cur) {
    const chips = Object.entries(BARRY.shPhys.EVENTS).map(([k, e]) => el('button', { type: 'button', class: 'sh-chip ev-' + e.kind + (k === cur ? ' active' : ''), 'aria-pressed': String(k === cur),
      title: k === 'pspike' ? 'The Barry lab is working on the P-spike profile' : e.say, onclick: () => (S.play && S.play.key === k ? stopPlay() : playEvent(k)) }, [el('span', { class: 'sh-sw' }), e.label]));
    chips.push(el('button', { type: 'button', class: 'sh-chip ev-custom' + (cur === 'custom' ? ' active' : ''), 'aria-pressed': String(cur === 'custom'),
      title: 'Compose an event: sources, strengths, onsets', onclick: () => showCard({ type: 'compose' }) }, [el('span', { class: 'sh-sw' }), 'Your own']));
    return chips;
  }
  function stopEventAnim() { if (evRaf) cancelAnimationFrame(evRaf); evRaf = 0; }
  function renderEventCard(card) { if (isEvent()) showEventPanel(); else renderAbout(card); }
  function renderPspike(card) {
    card.appendChild(cardHead('Event', 'P-spike', { lead: el('span', { class: 'sh-sw lg', style: 'background:' + tok('--call-p', '#e05555') }) }));
    card.appendChild(el('div', { class: 'sh-lab' }, [el('b', { text: 'The Barry lab is working on it. ' }),
      'The P-spike profile will play here from the lab\'s own recordings once it is ready. Until then Seahorse has no model of it, on purpose: a made-up profile would teach the wrong shape.']));
    card.appendChild(el('h3', { text: 'Meanwhile' }));
    card.appendChild(el('div', { class: 'sh-chips' }, eventChips('pspike').filter((b) => !b.classList.contains('ev-pspike'))));
  }
  /* Make your own event: sources, strengths, onsets; presets fill it in. */
  const PRESET_SPEC = {
    ds1: { lec: { on: true, amp: 1, t: 24 }, mec: { on: false }, ca3: { on: false }, ec3: { on: false }, ripple: false, theta: false },
    ds2: { lec: { on: false }, mec: { on: true, amp: 1, t: 24 }, ca3: { on: false }, ec3: { on: false }, ripple: false, theta: false },
    swr: { lec: { on: false }, mec: { on: false }, ca3: { on: true, amp: 1, t: 72 }, ec3: { on: false }, ripple: true, theta: false },
    theta: { lec: { on: false }, mec: { on: false }, ca3: { on: false }, ec3: { on: false }, ripple: false, theta: true },
  };
  function renderCompose(card) {
    const C = S.compose;
    card.appendChild(cardHead('Model · make your own', 'Compose an event', { lead: el('span', { class: 'sh-logo' }, [UI.icon('plus')]) }));
    card.appendChild(el('p', { class: 'sh-lede', text: 'Switch sources on, set how strong each is and when it fires, then play it. Each source puts its sink in the layers the literature names; the probe reads it and the sections light as it plays.' }));
    card.appendChild(el('div', { class: 'sh-actions' }, [el('span', { class: 'sh-field-k', text: 'Start from' })].concat(Object.keys(PRESET_SPEC).map((k) =>
      el('button', { type: 'button', class: 'sh-chip', text: BARRY.shPhys.EVENTS[k].label, onclick: () => {
        const p = PRESET_SPEC[k];
        ['lec', 'mec', 'ca3', 'ec3'].forEach((s) => { C[s].on = !!p[s].on; if (p[s].amp != null) C[s].amp = p[s].amp; if (p[s].t != null) C[s].t = p[s].t; });
        C.ripple = p.ripple; C.theta = p.theta;
        showCard({ type: 'compose' });
      } })))));
    const rows = [['lec', 'to the outer molecular layer (lateral perforant path)'], ['mec', 'to the middle molecular layer (medial perforant path)'],
      ['ca3', 'to CA1 radiatum (Schaffer collaterals)'], ['ec3', 'to CA1 lacunosum-moleculare (temporoammonic path)']];
    rows.forEach(([k, what]) => {
      const c = C[k];
      const row = el('div', { class: 'sh-compose' + (c.on ? '' : ' off') });
      row.appendChild(el('div', { class: 'sh-compose-head' }, [el('b', { text: SOURCES[k].label }), el('span', { class: 'sh-small', text: what }),
        UI.seg('', [[true, 'On'], [false, 'Off']], !!c.on, (v) => { c.on = v; row.classList.toggle('off', !v); }, { aria: SOURCES[k].label, small: true })]));
      row.appendChild(UI.range({ label: 'Strength', min: 0.1, max: 2, step: 0.05, value: c.amp, fmt: (v) => '×' + (+v).toFixed(2), on: (v) => { c.amp = v; }, wide: true }));
      row.appendChild(UI.range({ label: 'Onset', min: 0, max: 300, step: 1, value: c.t, fmt: (v) => v + ' ms', on: (v) => { c.t = v; }, wide: true }));
      card.appendChild(row);
    });
    card.appendChild(el('div', { class: 'sh-actions' }, [
      UI.seg('Ripple', [[true, 'On'], [false, 'Off']], !!C.ripple, (v) => { C.ripple = v; }, { small: true }),
      UI.seg('Theta', [[true, 'On'], [false, 'Off']], !!C.theta, (v) => { C.theta = v; }, { small: true }),
    ]));
    card.appendChild(el('div', { class: 'sh-actions' }, [UI.button({ icon: 'play', text: 'Play it', cls: 'solid', onclick: () => playEvent('custom') })]));
  }

  /* ==================================================================
     Stories: one recorded event told click by click (seahorse_story.js).
     On the probe, the section is painted from the recording itself; beyond
     it, the 3D stage draws our hypothesis. The stage goes dark for it, and
     nothing moves on to the next stop without a click.
     ================================================================== */
  const ST = () => BARRY.shStory;
  const STORY_SPEEDS = [[0.05, '1/20'], [0.2, '1/5'], [0.5, '1/2'], [1, 'Real time'], [2, '2×']];
  const COOL = '#6fd3ff';                // the septum's pacing
  const LIGHT = '#4f9dff';               // the light on the hilus
  const EMBER = (lv) => 'rgb(' + ST().ramp(lv).join(',') + ')';
  const fmtStoryT = (t, span) => (t < -0.0049 ? '−' : '') + Math.abs(t).toFixed(span > 12 ? 1 : 2) + ' s';
  async function startStory(key, o) {
    o = o || {};
    const story = ST().stories().find((s) => s.key === key);
    if (!story) return;
    if (!o.fromTour) endTour();
    stopPlay(true);
    UI.closeAll();
    const ok = await need(['three', 'mesh_brain.shb.gz', 'mesh_hpf.shb.gz', 'mesh_lamina.shb.gz', 'cells.shb.gz', 'brain50.shb.gz', 'hip20.shb.gz', 'fine10.shb.gz'],
      'Getting the seizure ready', 'The section the probe went through, the hippocampus around it, and the whole brain beyond.');
    if (!ok) return;
    let D = S.storyData && S.storyData[key];
    if (!D) {
      try { D = await getJSON(story.data); } catch (err) {
        toast('The story\'s recording is missing (web/seahorse/' + story.data + '). Build it with: python tools/seahorse/story_m459.py', 'err');
        return;
      }
      S.storyData = Object.assign(S.storyData || {}, { [key]: D });
    }
    const P = { kind: 'story', key, story, D, i: -1, stop: null, t: 0, speed: 1, paused: true, held: false, levels: {}, extra: null,
                fxN: {}, timers: [], words: [], moving: false, speeds: {}, seq: 0 };
    P.geo = storyGeo(story, D);
    S.play = P;
    allenCentres();
    await runStop(o.at || 0);
    startStoryClock();
  }
  /* Where each recorded zone sits on a probe line through the atlas's section:
     its layers, top to bottom, sampled along the shank. */
  function storyGeo(story, D) {
    const ap = story.probe.ap, ml = story.probe.ml;
    const codeZone = new Map();
    D.zones.forEach((z) => z.layers.forEach((k) => { const l = lamOf(k); if (l) codeZone.set(l.code, z.key); }));
    const zones = {};
    for (let dv = 900; dv <= 3400; dv += 10) {
      const zk = codeZone.get(sampleAt(ap, dv, ml).lam);
      if (!zk) continue;
      const z = zones[zk] || (zones[zk] = { dv0: dv, dv1: dv + 10 });
      z.dv0 = Math.min(z.dv0, dv); z.dv1 = Math.max(z.dv1, dv + 10);
    }
    // a zone the atlas misses here keeps the place it has on the measured line (AP -1.80, ML 1.40 mm)
    const FALLBACK = { ca1o: [1420, 1600], ca1r: [1600, 2000], supd: [2000, 2160], supp: [2160, 2230], supg: [2230, 2340],
                       hil: [2340, 2520], infg: [2520, 2600], infp: [2600, 2670], infd: [2670, 2790] };
    D.zones.forEach((z) => { if (!zones[z.key] && FALLBACK[z.key]) zones[z.key] = { dv0: FALLBACK[z.key][0], dv1: FALLBACK[z.key][1] }; });
    const vals = Object.values(zones);
    const top = Math.min(...vals.map((z) => z.dv0)), bottom = Math.max(...vals.map((z) => z.dv1));
    // the sorted unit: its contact's place inside its zone
    const uz = D.zones.find((z) => D.unit.csc >= z.csc[0] && D.unit.csc <= z.csc[1]);
    const g = uz && zones[uz.key];
    const unitDv = g ? g.dv0 + (g.dv1 - g.dv0) * ((D.unit.csc - uz.csc[0] + 0.5) / (uz.csc[1] - uz.csc[0] + 1)) : null;
    return { ap, ml, zones, top, bottom, unitDv };
  }
  /* Allen structures' middles (CCF um) on each side, from the 50 um labels, in
     one pass: the septum, the cortex the discharge reaches, the thalamus, the brainstem. */
  const ALLEN_IDS = { MS: 564, MOp: 985, SSp: 322, AUD: 247, VISp: 385, RSP: 254, ACA: 31, TH: 549, MB: 313, P: 771, MY: 354 };
  let allenC = null;
  function allenCentres() {
    if (allenC) return allenC;
    const B = S.blobs['brain50.shb.gz'];
    if (!B) return {};
    const st = B.header.structures, names = Object.keys(ALLEN_IDS), ids = names.map((n) => ALLEN_IDS[n]);
    const slot = new Int16Array(st.length).fill(-1);
    st.forEach((s, i) => { const hit = ids.findIndex((id) => s.id === id || (s.path || []).includes(id)); if (hit >= 0) slot[i] = hit; });
    const acc = new Float64Array(ids.length * 8), L = B.arrays.labels;
    for (let i = 0; i < 264; i++) for (let j = 0; j < 160; j++) {
      const row = (i * 160 + j) * 228;
      for (let k = 0; k < 228; k++) {
        const s = slot[L[row + k]];
        if (s < 0) continue;
        const o = (s * 2 + (k * 50 + 25 >= 5700 ? 0 : 1)) * 4;
        acc[o]++; acc[o + 1] += i; acc[o + 2] += j; acc[o + 3] += k;
      }
    }
    allenC = {};
    names.forEach((n, s) => {
      const get = (side) => { const o = (s * 2 + side) * 4, c = acc[o]; return c ? [acc[o + 1] / c * 50 + 25, acc[o + 2] / c * 50 + 25, acc[o + 3] / c * 50 + 25] : null; };
      const r = get(0), l = get(1);
      allenC[n] = { r, l, m: r && l ? [(r[0] + l[0]) / 2, (r[1] + l[1]) / 2, 5700] : (r || l) };
    });
    return allenC;
  }
  const allenW = (name, side) => { const c = (allenCentres()[name] || {})[side || 'r']; return c ? S.three.W(c[0], c[1], c[2]) : null; };
  const hpfW = (k, side) => { const c = S.stage && S.stage.centroid('hpf', k, true); return c && side === 'l' ? [-c[0], c[1], c[2]] : c; };
  const geoW = (P, dv) => S.three.W(P.geo.ap, dv, P.geo.ml);

  async function runStop(i) {
    const P = S.play;
    if (!P || P.kind !== 'story') return;
    const stops = P.story.stops;
    i = Math.max(0, Math.min(stops.length - 1, i));
    clearStoryFx(P);
    const st = stops[i];
    P.i = i; P.stop = st; P.seq++;
    const seq = P.seq;
    P.levels = {}; P.extra = null; P.fxN = {}; P.bump = {}; P.fxT0 = performance.now(); P.drawAt = 0; P.schemAt = 0;
    if (st.clip) {
      P.t = st.clip[0];
      P.speed = P.speeds[st.key] || st.speed || 1;
      P.paused = false; P.held = false;
      // a still picture where motion is unwelcome: the clip's busiest moment
      if (reducedMotion()) { P.t = storyPeak(P, st); P.paused = true; P.held = true; }
    } else { P.t = 0; P.paused = false; P.held = true; }
    P.model = st.model ? storyModel(st.model) : null;
    // the rail: the map lit for this stop, and the story's card
    S.focus = { cells: new Set(), regionKeys: new Set((st.focus || {}).regions || []), conns: new Set((st.focus || {}).conns || []), layers: new Set() };
    renderDock();
    showCard({ type: 'story' });
    renderRail();
    P.moving = true;
    try { await storyView(P, st); } finally { P.moving = false; }
    if (S.play !== P || P.seq !== seq || !S.stage) return;
    S.stage.setDark(true);
    S.stage.mini = false;
    if (S.stage.setPulse) S.stage.setPulse(1);
    if (S.stage.setPulseSide) S.stage.setPulseSide(1);      // the probe was in the right hemisphere
    placeMini();
    syncProbe();
    // the cells this stop is about stand out; the rest step back
    const types = (st.focus || {}).cells || [];
    if (types.length && S.mode !== 'schematic') S.stage.focus({ cells: new Set(types.flatMap((t) => instancesOfType(t))), regions: new Set(), layers: new Set() });
    else S.stage.focus(null);
    P.words = storyWords(P, st);
    renderNav();
    renderTools();
    applyHighlights();
    storyOverlay(true);
    updateLabels();
  }
  function storyGo(i) { const P = S.play; if (P && P.kind === 'story') runStop(i); }
  function storyNext() {
    const P = S.play;
    if (!P || P.kind !== 'story') return;
    if (P.i >= P.story.stops.length - 1) stopPlay(); else runStop(P.i + 1);
  }
  /* The view a stop asks for: the section through the probe (gliding, not
     jumping, from one framing to the next), or the 3D hippocampus or brain. */
  async function storyView(P, st) {
    const v = st.view;
    if (v === 'probe' || v === 'dentate') {
      const fr = storyFrame(P, v);
      const ap = fr.C[0];
      const same = S.mode === 'slice' && S.slice.plane === 'coronal' && Math.abs(S.slice.pos - ap) < 1 && !S.slice.tiltA && !S.slice.tiltB && !S.slice.custom;
      S.slice.plane = 'coronal'; S.slice.pos = ap; S.slice.tiltA = 0; S.slice.tiltB = 0; S.slice.custom = null;
      if (S.mode !== 'slice') { S.slice.C = fr.C; S.slice.k = fr.k; await setMode('slice'); }
      else await glideSlice(fr.C, fr.k, same ? 900 : 0);
      return;
    }
    const lv = v === 'hpf' ? 'hpf' : 'brain';
    if (S.mode !== '3d') { S.level = lv; await setMode('3d'); }
    else if (S.level !== lv) await setLevel(lv);
    if (!S.stage) return;
    // the hippocampus is cut open at the probe's section; the brain is whole
    S.stage.setCut(lv === 'brain' ? { kind: 'none' } : { kind: 'coronal', pos: P.geo.ap });
    const cam = storyCam(P, v);
    if (cam) S.stage.fly(cam.pos, cam.target, 1700);
  }
  /* Where the camera stands for a 3D stop: far enough back to see the whole
     of what the stop is about, aimed a little low so it sits above the dock
     (the 3D camera sees 35 degrees top to bottom). */
  function storyCam(P, v) {
    const aim = (target, dir, d) => {
      const n = Math.hypot(...dir);
      return { pos: target.map((x, i) => x + dir[i] / n * d), target };
    };
    if (v === 'hpf') return aim([2.6, -0.8, 1.5], [0.72, 0.5, -0.48], 14.5);          // the right hippocampal formation, cut at the probe
    if (v === 'brain-septum') return aim([1.4, -0.9, 0.3], [0.9, 0.36, -0.25], 17);     // the septum, the dentate, the entorhinal cortex
    if (v === 'brain') return aim([0, -1.4, 0.2], [0.82, 0.42, 0.38], 27);              // the whole brain from the right, a little behind
    return null;
  }
  /* The middle of some layers where a coronal plane crosses them (right side, CCF um). */
  const planeC = new Map();
  function planeCentre(keys, ap) {
    const id = keys.join(',') + '@' + ap;
    if (planeC.has(id)) return planeC.get(id);
    const codes = new Set(keys.map((k) => (lamOf(k) || {}).code).filter(Boolean));
    let n = 0, d = 0, m = 0;
    for (let ml = 5760; ml < 10200; ml += 20) for (let dv = 900; dv < 4600; dv += 20) { if (codes.has(sampleAt(ap, dv, ml).lam)) { n++; d += dv; m += ml; } }
    const c = n ? [ap, d / n, m / n] : null;
    planeC.set(id, c);
    return c;
  }
  /* The loop's stations: the dentate, CA3 and CA1 where the probe's section crosses
     them; the subiculum and the entorhinal cortex behind it. */
  function loopPt(P, k) {
    const lay = { DG: ['hil'], CA3: ['ca3sp'], CA1: ['ca1sp'] }[k];
    const c = lay && planeCentre(lay, P.geo.ap);
    return c ? S.three.W(c[0], c[1], c[2]) : hpfW(k);
  }
  /* The section's framing: the probe, top to bottom (or closer, on the dentate), in the room above the dock. */
  function storyFrame(P, v) {
    const g = P.geo;
    const host = $('.sh-host').getBoundingClientRect();
    const W = Math.max(240, host.width), H = Math.max(240, host.height);
    const dock = $('.sh-dock');
    const dockH = dock ? dock.getBoundingClientRect().height : 190;
    const room = Math.max(180, H - dockH - 2 * 16 - 24);
    const ap = g.ap;
    let wUm, hUm, cx, cy;
    if (v === 'dentate') { wUm = 2400; hUm = (g.zones.infd || { dv1: g.bottom }).dv1 - (g.zones.supd || { dv0: g.top }).dv0 + 420; cx = g.ml + 260; cy = ((g.zones.supd || { dv0: g.top }).dv0 + (g.zones.infd || { dv1: g.bottom }).dv1) / 2; }
    else { wUm = 4400; hUm = g.bottom - g.top + 320; cx = g.ml + 300; cy = (g.top + g.bottom) / 2; }
    const k = Math.max(wUm / (W * 0.94), hUm / room);
    const yWant = 16 + room / 2;
    return { C: [ap, cy + (H / 2 - yWant) * k, cx], k };
  }
  let glideRaf = 0;
  const overlayNow = () => { if (isSext()) sextOverlay(true); else storyOverlay(true); };
  function glideSlice(C1, k1, ms) {
    cancelAnimationFrame(glideRaf);
    const A = S.slice.custom || sliceAxes();
    const C0 = S.slice.C ? S.slice.C.slice() : C1.slice(), k0 = S.slice.k || k1;
    if (!S.stage || reducedMotion() || !ms) { S.slice.C = C1; S.slice.k = k1; pushSlice(); syncLadder(); overlayNow(); return Promise.resolve(); }
    return new Promise((done) => {
      const t0 = performance.now();
      const step = (now) => {
        const u = Math.min(1, (now - t0) / ms);
        const e = u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
        S.slice.C = C0.map((x, i) => x + (C1[i] - x) * e);
        S.slice.k = Math.exp(Math.log(k0) + (Math.log(k1) - Math.log(k0)) * e);       // zoom evenly
        if (S.stage) S.stage.setSlice({ N: A.N, U: A.U, V: A.V, C: S.slice.C, k: S.slice.k });
        overlayNow();
        if (u < 1) glideRaf = requestAnimationFrame(step);
        else { glideRaf = 0; pushSlice(); syncLadder(); done(); }
      };
      glideRaf = requestAnimationFrame(step);
    });
  }
  /* The model dentate spike (the gate stop): seahorse_phys.js's DS2, its sink held at its peak. */
  function storyModel(key) {
    const ev = BARRY.shPhys.EVENTS[key];
    if (!ev) return null;
    let cm = 1e-9, peak = 0;
    for (let t = 0; t <= ev.ms; t += 0.5) for (const v of BARRY.shPhys.layerCsd(ev, t).values()) if (Math.abs(v) > cm) { cm = Math.abs(v); peak = t; }
    return { ev, cm, peak };
  }
  function storyPeak(P, st) {
    let best = st.clip[0], bv = -1;
    for (let t = st.clip[0]; t <= st.clip[1]; t += 0.02) {
      const lv = ST().zoneLevels(P.D, t, st.measure);
      const s = Object.values(lv).reduce((a, b) => a + b, 0);
      if (s > bv) { bv = s; best = t; }
    }
    return best;
  }

  /* the lights come back up: everything the story put on the stage goes */
  function endStory(P) {
    stopStoryClock();
    cancelAnimationFrame(glideRaf);
    P.seq++;
    clearStoryFx(P);
    if (S.stage) {
      S.stage.setDark(false);
      if (S.stage.setPulse) S.stage.setPulse(null);
      if (S.stage.setPulseSide) S.stage.setPulseSide(0);
      S.stage.mini = S.slice.mini;
      S.stage.focus(null);
    }
    ['.sh-story-over', '.sh-story-words'].forEach((q) => { const n = $(q); if (n) n.remove(); });
    const svg = $('.sh-map svg');
    if (svg && BARRY.shSchem.heat) BARRY.shSchem.heat(svg, new Map());
  }

  /* ---------- the story's clock ---------- */
  let stRaf = 0, stLast = 0;
  function startStoryClock() {
    cancelAnimationFrame(stRaf);
    stLast = performance.now();
    const tick = (now) => {
      const P = S.play;
      if (!P || P.kind !== 'story') { stRaf = 0; return; }
      const dt = Math.min(100, now - stLast);
      stLast = now;
      try { storyTick(P, now, dt); } catch (err) { reportClientError('seahorse:story', err.message, err.stack); }
      stRaf = requestAnimationFrame(tick);
    };
    stRaf = requestAnimationFrame(tick);
  }
  function stopStoryClock() { cancelAnimationFrame(stRaf); stRaf = 0; }
  function storyTick(P, now, dt) {
    const st = P.stop;
    if (!st || P.moving && st.view !== 'probe' && st.view !== 'dentate') return;
    if (st.clip && !P.paused) {
      P.t += dt / 1000 * P.speed;
      if (P.t >= st.clip[1]) { P.t = st.clip[1]; P.paused = true; syncStoryPlay(); if (!P.held) { P.held = true; renderDock(); } }
    }
    if (st.measure) {
      // recorded: each zone's level now, with a short afterglow on screen so a 50 ms discharge still reads
      const lv = ST().zoneLevels(P.D, P.t, st.measure);
      const fall = Math.exp(-dt / 240);
      for (const k in lv) P.levels[k] = P.paused ? lv[k] : Math.max(lv[k], (P.levels[k] || 0) * fall);
    } else if (P.model) {
      // the volley arrives, the sink holds long enough to be read, it fades, a rest
      const M = P.model, ms = (now - P.fxT0) % 3200;
      let t = null;
      if (ms < 700) t = M.peak - 14 + 14 * (ms / 700);
      else if (ms < 2000) t = M.peak;
      else if (ms < 2600) t = M.peak + 20 * ((ms - 2000) / 600);
      P.modelT = t;
      const m = new Map();
      if (t != null) for (const [k, v] of BARRY.shPhys.layerCsd(M.ev, t)) m.set(k, v / M.cm);
      P.modelPaint = m;
    }
    if (st.fx && S.mode !== 'schematic' && S.stage) storyFx(P, now - P.fxT0);
    applyHighlights();
    paintStoryOverlay(P);
    if (now - P.drawAt > 33) { P.drawAt = now; drawStoryPanels(P); syncStoryTime(P); }
    if (now - P.schemAt > 120) { P.schemAt = now; storySchemHeat(P); }
  }
  function toggleStoryPause() {
    const P = S.play;
    if (!P || P.kind !== 'story' || !P.stop.clip) return;
    if (P.paused && P.t >= P.stop.clip[1] - 1e-6) { P.t = P.stop.clip[0]; P.levels = {}; }
    P.paused = !P.paused;
    syncStoryPlay();
  }
  function syncStoryPlay() {
    const P = S.play;
    const b = $('.sh-tr-play');
    if (!b || !P || P.kind !== 'story') return;
    b.replaceWith(playBtn(!P.paused, toggleStoryPause));
  }
  function syncStoryTime(P) {
    const t = $('.sh-story-t b');
    if (t) t.textContent = fmtStoryT(P.t, P.stop.clip ? P.stop.clip[1] - P.stop.clip[0] : 0);
    const sc = $('.sh-tr-scrub');
    if (sc && sc.set && !sc.matches(':active')) sc.set(P.t);
  }

  /* ---------- what the 3D stage draws beyond the probe (all of it hypothesis) ---------- */
  function clearStoryFx(P) {
    P.timers.forEach(clearTimeout);
    P.timers = [];
    P.extra = null; P.modelPaint = null; P.light = null; P.words = [];
    const w = $('.sh-story-words'); if (w) w.innerHTML = '';
    const st = S.stage;
    if (!st || !st.setHeat) return;
    st.clearBeacons(); st.glowBrain(null); st.setHeat(null); st.fadeCrowd(null);
  }
  const fxOnce = (P, key, ms, at, fn) => { if (ms >= at && !P.fxN[key]) { P.fxN[key] = 1; fn(); } };
  const fxEvery = (P, key, ms, period, fn) => { const n = Math.floor(ms / period); if (P.fxN[key] == null || P.fxN[key] < n) { P.fxN[key] = n; fn(n); } };
  const fxLater = (P, ms, fn) => { const id = setTimeout(() => { if (S.play === P && P.stop) fn(); }, ms); P.timers.push(id); };
  const LOOP_LAYERS = ['oml1', 'mml1', 'iml1', 'gcl1', 'hil', 'gcl2', 'iml2', 'mml2', 'oml2', 'ca3so', 'ca3sp', 'ca3slu', 'ca3sr', 'ca2so', 'ca2sp', 'ca2sr', 'ca1so', 'ca1sp', 'ca1sr', 'ca1slm'];
  function storyFx(P, ms) {
    const st = S.stage, f = P.stop.fx, now = performance.now();
    P.bump = P.bump || {};
    // the clay keeps its own colors: a low glow where a region is seizing, and a flash where a discharge lands
    const land = (k) => { P.bump[k] = performance.now(); };
    const glow = (base) => {
      const h = {};
      ['DG', 'CA3', 'CA2', 'CA1', 'SUB', 'ProS', 'ENTm', 'ENTl'].forEach((k) => {
        const b = P.bump[k] ? 0.6 * Math.exp(-(now - P.bump[k]) / 650) : 0;
        h[k] = Math.min(1, (base[k] != null ? base[k] : base._ || 0) + b);
      });
      st.setHeat(h, '#ff6a2a');
    };
    if (f === 'loop') {
      // laps around the loop, each landing harder on the dentate; the cut face burns hotter lap by lap
      const LAP = 3000, lap = ms / LAP;
      fxEvery(P, 'lap', ms, LAP, (n) => {
        const w = Math.min(1, 0.35 + n * 0.22);
        [['DG', 'CA3', 'gc'], ['CA3', 'CA1', 'ca3'], ['CA1', 'SUB', 'ca1'], ['SUB', 'ENTm', null], ['ENTm', 'DG', 'stel']].forEach(([a, b, cell], i) => fxLater(P, i * 540, () => {
          const A = loopPt(P, a), B = loopPt(P, b);
          if (A && B) st.volley(A, B, EMBER(0.5 + 0.45 * w), 1050, { size: 0.9 + w * 0.9, lift: 0.6 });
          if (cell) instancesOfType(cell).forEach((k) => st.pulseCell(k, 950));
          fxLater(P, 870, () => land(b));
        }));
      });
      glow({ _: Math.min(0.26, 0.04 + lap * 0.06) });
      const h = Math.min(0.78, 0.22 + lap * 0.12);
      const flick = 0.8 + 0.2 * Math.sin(ms / 120) * Math.sin(ms / 410);
      P.extra = new Map(LOOP_LAYERS.map((k, i) => [k, Math.min(1, h * flick * (0.78 + 0.22 * Math.sin(i * 1.7 + ms / 300)))]));
    } else if (f === 'septum') {
      const sep = allenW('MS', 'm');
      fxOnce(P, 'beacon', ms, 0, () => { if (sep) st.beacon('septum', sep, COOL, { hz: 0.72, size: 1.25 }); });
      // each breath of the septum (theta, slowed down to be seen) goes out to the hilus and the entorhinal cortex
      fxEvery(P, 'pace', ms, 1390, () => {
        const dg = loopPt(P, 'DG'), ec = hpfW('ENTm');
        if (sep && dg) st.volley(sep, dg, COOL, 1150, { size: 0.85, lift: 0.35, land: false });
        if (sep && ec) fxLater(P, 240, () => st.volley(sep, ec, COOL, 1350, { size: 0.85, lift: 0.5, land: false }));
        // and the disinhibited dentate answers, in ember
        fxLater(P, 1000, () => { const d = loopPt(P, 'DG'); if (d) st.flareAt(d, EMBER(0.72), 950); land('DG'); });
      });
      glow({ DG: 0.24, _: 0.1 });
    } else if (f === 'global') {
      const ec = hpfW('ENTl') || hpfW('ENTm');
      fxEvery(P, 'wave', ms, 3400, () => {
        land('ENTl'); land('ENTm');
        ['SSp', 'MOp', 'AUD', 'VISp', 'RSP', 'ACA'].forEach((n, i) => fxLater(P, i * 240, () => { const b = allenW(n, 'r'); if (ec && b) st.volley(ec, b, EMBER(0.7), 1350, { size: 1.15, lift: 0.4 }); }));
        fxLater(P, 500, () => { const th = allenW('TH', 'r'), dg = hpfW('DG'); if (th && dg) st.volley(dg, th, EMBER(0.62), 1250, { size: 1.05, lift: 0.3 }); });
        // across the commissure to the other hippocampus
        fxLater(P, 1300, () => { const a = hpfW('DG'), b = hpfW('DG', 'l'); if (a && b) st.volley(a, b, EMBER(0.8), 1400, { size: 1.15, lift: 0.55 }); });
      });
      const k = Math.min(1, ms / 6500);
      st.glowBrain({ Isocortex: { color: '#ff7a2f', a: 0.12 + 0.48 * k }, TH: { color: '#ff9a3c', a: 0.1 + 0.42 * k } });
      glow({ _: 0.22 });
    } else if (f === 'clonic') {
      // jerks in time with the cortical discharge (drawn at a pace you can follow)
      const beat = 2.2, ph = (ms / 1000 * beat) % 1, kick = Math.exp(-ph * 5);
      st.glowBrain({ Isocortex: { color: '#ff7a2f', a: 0.26 + 0.5 * kick }, TH: { color: '#ff9a3c', a: 0.4 } });
      fxEvery(P, 'jerk', ms, 1000 / beat, () => { ['r', 'l'].forEach((s) => { const p = allenW('MOp', s); if (p) st.flareAt(p, '#ffe0a0', 650); }); });
      glow({ _: 0.22 });
    } else if (f === 'tonic') {
      const k = Math.min(1, ms / 2600), sh = 0.9 + 0.1 * Math.sin(ms / 230);
      const stem = { color: '#ffd27a', a: (0.3 + 0.6 * k) * sh };
      st.glowBrain({ Isocortex: { color: '#ff7a2f', a: 0.3 }, TH: { color: '#ff9a3c', a: 0.4 }, MB: stem, P: stem, MY: stem });
      fxEvery(P, 'stiff', ms, 1100, () => { const p = allenW('P', 'm') || allenW('P', 'r'); if (p) st.flareAt(p, '#fff1c0', 1300); });
      glow({ _: 0.22 });
    } else if (f === 'damage') {
      // the hilar interneurons stand out for a moment, then fade away, somata and tracings both
      const up = Math.min(1, ms / 800), k = Math.max(0, Math.min(1, (ms - 1300) / 4200));
      const v = (1 + 1.6 * up) * (1 - 0.96 * k * k * (3 - 2 * k));
      st.fadeCells(instancesOfType('hipp'), Math.min(1, v));
      const hk = ((S.kb.crowd || {}).kinds || []).findIndex((x) => x.key === 'hipp');
      if (hk >= 0) st.fadeCrowd(hk, v);
    } else if (f === 'opto') {
      // light on the hilus at a steady rhythm (drawn at 2 a second); with each flash the hilar interneurons fire together
      const ph = (ms / 1000 * 2) % 1;
      P.light = ph < 0.42 ? 1 - ph : 0.1;
      const hk = ((S.kb.crowd || {}).kinds || []).findIndex((x) => x.key === 'hipp');
      if (hk >= 0) st.fadeCrowd(hk, 1 + 1.6 * P.light);
      fxEvery(P, 'flash', ms, 500, () => instancesOfType('hipp').forEach((k) => st.pulseCell(k, 430)));
    }
  }
  /* Words on the 3D stage for what the hypothesis stops talk about. */
  function storyWords(P, st) {
    if (S.mode === 'schematic') return [];
    const w = (text, at, cls) => (at ? { text, at, cls } : null);
    const f = st.fx;
    let out = [];
    if (f === 'loop') out = [w('Dentate gyrus', loopPt(P, 'DG')), w('CA3', loopPt(P, 'CA3')), w('CA1', loopPt(P, 'CA1')), w('Subiculum', hpfW('SUB')), w('Entorhinal cortex', hpfW('ENTm'))];
    else if (f === 'septum') out = [w('Medial septum', allenW('MS', 'm'), 'cool'), w('Dentate gyrus', loopPt(P, 'DG')), w('Entorhinal cortex', hpfW('ENTm'))];
    else if (f === 'global') out = [w('Neocortex', allenW('SSp', 'r')), w('Thalamus', allenW('TH', 'r')), w('The other hippocampus', hpfW('DG', 'l')), w('Entorhinal cortex', hpfW('ENTl'))];
    else if (f === 'clonic') out = [w('Motor cortex', allenW('MOp', 'r')), w('Motor cortex', allenW('MOp', 'l'))];
    else if (f === 'tonic') out = [w('Brainstem', allenW('P', 'm') || allenW('P', 'r')), w('Motor cortex', allenW('MOp', 'r'))];
    else if (f === 'damage' || f === 'opto') {
      const h = P.geo.zones.hil, at = h ? geoW(P, (h.dv0 + h.dv1) / 2) : null;
      out = [w(f === 'damage' ? 'Hilar interneurons: fewer after seizures?' : 'Light on the hilus', at, f === 'opto' ? 'cool' : '')];
    }
    return out.filter(Boolean);
  }
  function placeStoryWords() {
    const P = S.play;
    let box = $('.sh-story-words');
    if (!P || P.kind !== 'story' || !P.words || !P.words.length || S.mode === 'schematic' || !S.stage) { if (box && box.childNodes.length) box.innerHTML = ''; return; }
    const B = stageBox();
    if (!B) return;
    if (!box) { box = el('div', { class: 'sh-story-words', 'aria-hidden': 'true' }); $('.sh-stage').appendChild(box); }
    if (box.childNodes.length !== P.words.length) { box.innerHTML = ''; P.words.forEach((x) => box.appendChild(el('span', { class: 'sh-word sh-sword ' + (x.cls || ''), text: x.text }))); }
    // whole words only: one that would run off the stage is slid back onto it, and one
    // that would sit under the dock (or is far off the stage) waits until it can be read whole
    const dk = $('.sh-dock > *'), dr = dk ? dk.getBoundingClientRect() : null, sr = B.sr;
    P.words.forEach((x, i) => {
      const p = S.stage.project(x.at);
      const n = box.childNodes[i];
      const w = n.offsetWidth || x.text.length * 7, h = 18;
      let cx = p[0], cy = p[1] - 22;
      const far = p[2] > 1 || cx < -80 || cy < -80 || cx > B.W + 80 || cy > B.H + 80;
      cx = Math.max(w / 2 + 8, Math.min(B.W - w / 2 - 8, cx));
      cy = Math.max(h / 2 + 8, Math.min(B.H - h / 2 - 8, cy));
      const ax = sr.left + B.ox + cx, ay = sr.top + B.oy + cy;
      const under = dr && ax + w / 2 > dr.left - 6 && ax - w / 2 < dr.right + 6 && ay + h / 2 > dr.top - 6 && ay - h / 2 < dr.bottom + 6;
      n.style.visibility = far || under ? 'hidden' : '';
      n.style.transform = 'translate(' + Math.round(B.ox + cx) + 'px,' + Math.round(B.oy + cy) + 'px) translate(-50%, -50%)';
    });
  }

  /* ---------- the probe on the section ---------- */
  function storyOverlay(rebuild) {
    const P = S.play;
    let box = $('.sh-story-over');
    const on = P && P.kind === 'story' && P.stop && P.stop.probe !== false && (P.stop.view === 'probe' || P.stop.view === 'dentate') && S.mode === 'slice' && S.stage && S.stage.view === 'slice';
    if (!on) { if (box) box.remove(); return; }
    const B = stageBox();
    if (!B) return;
    if (!box) { box = el('div', { class: 'sh-story-over', 'aria-hidden': 'true' }); $('.sh-stage').appendChild(box); rebuild = true; }
    if (rebuild) buildProbeOverlay(box, P, B);
    paintStoryOverlay(P);
  }
  function buildProbeOverlay(box, P, B) {
    const g = P.geo, R = ST();
    const px = (dv) => S.stage.ccfToSlicePx([g.ap, dv, g.ml]);
    const a = px(g.top - 150), b = px(g.bottom + 150);
    const x = a[0];
    const svg = el('svg', { class: 'sh-svg', width: B.W, height: B.H, viewBox: '0 0 ' + B.W + ' ' + B.H });
    svg.appendChild(el('line', { class: 'shank-halo', x1: x, y1: a[1], x2: b[0], y2: b[1] }));
    svg.appendChild(el('line', { class: 'shank', x1: x, y1: a[1], x2: b[0], y2: b[1] }));
    svg.appendChild(el('path', { class: 'tip', d: 'M' + (b[0] - 4) + ',' + b[1] + ' L' + b[0] + ',' + (b[1] + 9) + ' L' + (b[0] + 4) + ',' + b[1] + ' Z' }));
    // the zones along the shank, and their names in a column beside it
    const rows = P.D.zones.map((z) => { const gz = g.zones[z.key]; const p0 = px(gz.dv0), p1 = px(gz.dv1); return { z, y0: p0[1], y1: p1[1], ym: (p0[1] + p1[1]) / 2, x: p0[0] }; });
    rows.forEach((r) => svg.appendChild(el('line', { class: 'zone', 'data-z': r.z.key, style: '--zc:' + lamColor(r.z.layers[0]), x1: r.x, y1: r.y0 + 1.5, x2: r.x, y2: Math.max(r.y0 + 2, r.y1 - 1.5) })));
    // names only for the zones in view (a close framing leaves CA1 above the top), laid out so none overlap
    const named = rows.filter((r) => r.ym > 14 && r.ym < B.H - 14);
    const lx = x + 30, gap = 17;
    const ys = named.map((r) => r.ym);
    for (let i = 1; i < ys.length; i++) ys[i] = Math.max(ys[i], ys[i - 1] + gap);
    const over = ys.length ? ys[ys.length - 1] - (B.H - 18) : 0;
    if (over > 0) for (let i = ys.length - 1; i >= 0; i--) { ys[i] -= over; if (i && ys[i - 1] > ys[i] - gap) ys[i - 1] = ys[i] - gap; }
    named.forEach((r, i) => {
      const zc = '--zc:' + lamColor(r.z.layers[0]);
      const y = ys[i];
      svg.appendChild(el('path', { class: 'lead', d: 'M' + (r.x + 6) + ',' + r.ym + ' C' + (r.x + 18) + ',' + r.ym + ' ' + (lx - 14) + ',' + y + ' ' + (lx - 4) + ',' + y }));
      svg.appendChild(el('circle', { class: 'zdot', 'data-z': r.z.key, style: zc, cx: lx + 1, cy: y, r: 3.6 }));
      svg.appendChild(el('text', { class: 'zlabel', x: lx + 10, y: y + 3.8 }, [R.ZONE_WORDS[r.z.key][0]]));
    });
    if (P.stop.unit && g.unitDv != null) {
      const u = px(g.unitDv);
      const uc = (cellOf('hipp') || {}).color || '#8fd';
      svg.appendChild(el('circle', { class: 'unit-halo', cx: u[0] - 12, cy: u[1], r: 9, fill: uc }));
      svg.appendChild(el('circle', { class: 'unit', cx: u[0] - 12, cy: u[1], r: 4.2, fill: uc }));
      const ut = el('text', { class: 'ulabel', x: u[0] - 26, y: u[1] + 4 }, ['contact ' + P.D.unit.csc]);
      svg.appendChild(ut);
    }
    box.innerHTML = '';
    box.appendChild(svg);
    Object.assign(box.style, { left: B.ox + 'px', top: B.oy + 'px', width: B.W + 'px', height: B.H + 'px' });
  }
  function paintStoryOverlay(P) {
    const box = $('.sh-story-over');
    if (!box || !P.stop) return;
    const R = ST(), measure = P.stop.measure;
    box.querySelectorAll('[data-z]').forEach((n) => {
      const k = n.getAttribute('data-z');
      if (measure) {
        const lv = P.levels[k] || 0, a = R.alphaOf(lv);
        const c = 'rgb(' + R.ramp(lv).join(',') + ')';
        n.style.stroke = n.tagName === 'line' ? (a ? c : '') : '';
        n.style.fill = n.tagName === 'circle' ? (a ? c : '') : '';
        n.style.opacity = n.tagName === 'line' ? String(Math.max(0.34, a)) : String(a ? Math.max(0.5, a) : 0.35);
      } else { n.style.stroke = ''; n.style.fill = ''; n.style.opacity = ''; }
    });
    const u = box.querySelector('circle.unit'), uh = box.querySelector('circle.unit-halo');
    if (u) {
      const hz = R.unitRate(P.D, P.t), k = Math.min(1, hz / 60);
      u.setAttribute('r', (3.4 + 3.6 * k).toFixed(2));
      uh.setAttribute('r', (6 + 12 * k).toFixed(2));
      uh.style.opacity = (0.08 + 0.5 * k).toFixed(3);
      u.style.opacity = (0.45 + 0.55 * Math.min(1, hz / 8)).toFixed(3);
    }
  }
  /* the map: the same heat in the plate's bands */
  function storySchemHeat(P) {
    const svg = $('.sh-map svg');
    if (!svg || !BARRY.shSchem.heat) return;
    const R = ST(), m = new Map();
    if (P.stop && P.stop.measure) P.D.zones.forEach((z) => { const lv = P.levels[z.key] || 0, a = R.alphaOf(lv); if (a) z.layers.forEach((k) => m.set(k, ['rgb(' + R.ramp(lv).join(',') + ')', Math.min(0.9, a)])); });
    else if (P.extra) for (const [k, lv] of P.extra) { const a = R.alphaOf(lv); if (a) m.set(k, ['rgb(' + R.ramp(lv).join(',') + ')', Math.min(0.9, a)]); }
    else if (P.modelPaint) for (const [k, v] of P.modelPaint) if (Math.abs(v) > 0.06) m.set(k, [v < 0 ? SINK : SOURCE, Math.min(0.85, 0.3 + Math.abs(v) * 0.7)]);
    BARRY.shSchem.heat(svg, m);
  }

  /* ---------- the dock ---------- */
  function fillStory(box) {
    const P = S.play, st = P.stop, R = ST();
    if (!st) return;
    const n = P.story.stops.length;
    const act = R.ACTS.find((a) => a.key === st.act) || { label: '' };
    const tag = R.TAGS[st.tag] || R.TAGS.recorded;
    box.appendChild(trHead('Seizure · mouse 459', act.label, [ofN('Stop', P.i + 1, n),
      st.clip ? el('span', { class: 'sh-story-t', title: 'Seconds from the hilar onset, 888.7 s into the session' }, ['t = ', el('b', { text: fmtStoryT(P.t, st.clip[1] - st.clip[0]) })]) : null]));
    box.appendChild(el('div', { class: 'sh-tr-say' }, [el('span', { class: 'sh-evtag ' + tag.cls, title: tag.label + ': ' + tag.sub, text: tag.label }), ' ', el('b', { text: st.title + '. ' }), st.say]));
    box.appendChild(storyDots(P));
    const last = P.i >= n - 1;
    const ctl = el('div', { class: 'sh-tr-ctl' }, [
      UI.button({ icon: 'prev', cls: 'icon quiet', aria: 'Back a stop', title: 'Back a stop (←)', disabled: P.i <= 0, onclick: () => storyGo(P.i - 1) })]);
    if (st.clip) {
      ctl.appendChild(playBtn(!P.paused, toggleStoryPause));
      const span = st.clip[1] - st.clip[0];
      const scrub = UI.range({ min: st.clip[0], max: st.clip[1], step: span > 12 ? 0.05 : 0.01, value: P.t, fmt: (v) => fmtStoryT(+v, span), aria: 'Time in the recording', wide: true,
        on: (v) => { P.paused = true; P.t = +v; syncStoryPlay(); } });
      scrub.classList.add('sh-tr-scrub');
      ctl.appendChild(scrub);
    } else ctl.appendChild(el('span', { class: 'grow' }));
    ctl.appendChild(UI.button({ icon: 'next', text: last ? 'Finish' : 'Next', cls: 'sm sh-next' + (P.held ? ' solid sh-ready' : ''),
      title: (last ? 'Finish the story' : 'Next stop') + ' (→)', onclick: () => storyNext() }));
    box.appendChild(ctl);
    const ctl2 = el('div', { class: 'sh-tr-ctl' });
    if (st.clip) ctl2.appendChild(UI.seg('Speed', STORY_SPEEDS.map(([v, t]) => [v, t, t === 'Real time' ? 'As it happened' : t === '2×' ? 'Twice as fast as it happened' : t + ' of real time']), P.speed,
      (v) => { P.speed = v; P.speeds[st.key] = v; }, { small: true }));
    ctl2.appendChild(storyLegend(P));
    ctl2.appendChild(el('span', { class: 'grow' }));
    ctl2.appendChild(UI.button({ text: 'End', cls: 'sm quiet', title: 'End the story (Esc)', onclick: () => stopPlay() }));
    box.appendChild(ctl2);
  }
  function storyDots(P) {
    const R = ST();
    const box = el('div', { class: 'sh-story-dots' });
    R.ACTS.forEach((a) => {
      const idx = P.story.stops.map((s, i) => [s, i]).filter(([s]) => s.act === a.key);
      if (!idx.length) return;
      box.appendChild(el('div', { class: 'sh-story-act' + (idx.some(([, i]) => i === P.i) ? ' on' : ''), title: a.label, style: '--n:' + idx.length }, idx.map(([s, i]) =>
        el('button', { type: 'button', tabindex: '-1', class: (i < P.i ? 'done ' : i === P.i ? 'now ' : '') + (R.TAGS[s.tag] || {}).cls, title: s.title, 'aria-label': 'Stop ' + (i + 1) + ': ' + s.title, onclick: () => storyGo(i) }))));
    });
    return box;
  }
  function storyLegend(P) {
    const st = P.stop;
    if (st.measure) {
      const [lo, hi] = ST().SCALE[st.measure];
      return el('span', { class: 'sh-heatkey', title: st.measure === 'mua' ? 'Each zone\'s multi-unit firing against its own quiet baseline' : 'Each zone\'s current density against its own quiet baseline (figure A\'s measure)' }, [
        el('span', { text: st.measure === 'mua' ? 'Firing' : 'Current' }), el('i', { style: 'background:' + ST().rampCss() }),
        el('span', { class: 'ends', text: lo + '× to ' + hi + '× quiet' })]);
    }
    if (P.model) return el('span', { class: 'sh-legend' }, [el('span', { class: 'sink', text: 'sink' }), el('span', { class: 'source', text: 'source' })]);
    if (st.fx) return el('span', { class: 'sh-small', text: 'Drawn, not recorded' });
    return el('span');
  }

  /* ---------- the card ---------- */
  function renderStoryCard(card) {
    const P = S.play;
    if (!P || P.kind !== 'story' || !P.stop) return renderAbout(card);
    const st = P.stop, R = ST(), tag = R.TAGS[st.tag] || R.TAGS.recorded;
    const act = R.ACTS.find((a) => a.key === st.act) || { label: '' };
    const head = cardHead([el('span', { class: 'sh-evtag ' + tag.cls, text: tag.label }), el('span', { text: tag.sub })], st.title, {});
    head.classList.add('sh-story-head');
    card.appendChild(head);
    card.appendChild(el('p', { class: 'sh-lede', text: st.lede || '' }));
    (st.panels || []).forEach((p) => { const n = storyPanel(P, st, p); if (n) card.appendChild(n); });
    (st.more || []).forEach((t) => card.appendChild(el('p', { text: t })));
    if (st.refs && st.refs.length) card.appendChild(el('div', { class: 'sh-actions' }, [citeChips(st.refs)]));
    card.appendChild(el('h3', { text: 'Every stop (' + P.story.stops.length + ')' }));
    card.appendChild(el('div', { class: 'sh-story-toc' }, R.ACTS.map((a) => {
      const idx = P.story.stops.map((s, i) => [s, i]).filter(([s]) => s.act === a.key);
      if (!idx.length) return null;
      return el('div', { class: 'sh-story-tocact' }, [el('div', { class: 'k', text: a.label })].concat(idx.map(([s, i]) =>
        el('button', { type: 'button', class: 'sh-story-tocrow' + (i === P.i ? ' on' : ''), onclick: () => storyGo(i) }, [
          el('i', { class: (R.TAGS[s.tag] || {}).cls }), el('span', { text: s.title })]))));
    })));
    const D = P.D;
    card.appendChild(el('h3', { text: 'The recording' }));
    card.appendChild(el('div', { class: 'sh-src' }, [
      el('div', {}, [el('b', { text: D.what + '. ' }), 't = 0 is the hilar onset, ' + D.onset_s + ' s into the session; quiet baseline ' + D.baseline_s[0] + ' to ' + D.baseline_s[1] + ' s.']),
      el('div', { text: D.source + '. Built by tools/seahorse/story_m459.py (' + D.built + ').' }),
      el('div', { text: 'The section places each zone where its layers are in the atlas, on a probe line at AP −1.80, ML +1.40 mm; the zones themselves are the recorded contacts.' }),
      el('div', { text: 'No video: the session\'s camera file tracked nothing, and no movie was saved.' }),
    ]));
    requestAnimationFrame(() => drawStoryPanels(P, true));
  }
  function storyPanel(P, st, kind) {
    const R = ST();
    if (kind === 'zones') {
      return el('div', { class: 'sh-probe-table' }, P.D.zones.map((z) => el('div', {
        onpointerenter: () => setHover({ type: 'lamina', key: z.layers[0] }, 'card'), onpointerleave: () => setHover(null, 'card') }, [
        el('span', { class: 'ch', text: 'ch ' + z.csc[0] + '–' + z.csc[1] }),
        el('span', { class: 'sh-sw sq', style: 'background:' + lamColor(z.layers[0]) }),
        el('span', { text: R.ZONE_WORDS[z.key][0] }),
      ])));
    }
    if (kind === 'figure' && st.figure != null) {
      const bar = ['red', 'green', 'blue', 'purple'][st.figure];
      const s = (x) => (x < 0 ? '−' : '') + String(+Math.abs(x).toFixed(2));
      return el('figure', { class: 'sh-story-fig' }, [
        el('img', { src: BASE + P.story.figures[st.figure], alt: 'Figure A, stage ' + (st.figure + 1) + ': current source density on every contact over one second', loading: 'lazy' }),
        el('figcaption', { text: 'Figure A, stage ' + (st.figure + 1) + ' (' + s(st.win[0]) + ' to ' + s(st.win[1]) + ' s): red sink, blue source, the potentials drawn over them; the ' + bar + ' bar marks the zone.' }),
      ]);
    }
    const cap = {
      timeline: st.measure === 'mua' ? 'Each zone\'s firing against its own quiet level, top of the probe to bottom.' : 'Each zone\'s current density against its own quiet level, top of the probe to bottom (figure A\'s measure).',
      unit: 'The hilar interneuron on contact ' + P.D.unit.csc + ' (spike ' + P.D.unit.width_ms + ' ms wide): its firing in 0.25 s bins, 10 s before to 90 s after the onset.',
      raster: 'Every discharge in the 40 s before the onset, one tick each.',
      offs: 'How long each zone kept firing after the onset.',
    }[kind];
    if (!cap) return null;
    return el('div', { class: 'sh-story-panel' }, [el('canvas', { class: 'sh-story-cv', 'data-k': kind }), el('div', { class: 'sh-small', text: cap })]);
  }
  function drawStoryPanels(P, force) {
    const cvs = $$('.sh-card canvas.sh-story-cv');
    if (!cvs.length || !P.stop) return;
    const R = ST(), st = P.stop;
    const tx = hexRgb(tok('--text', '#222'));
    const ink = (a) => 'rgba(' + tx[0] + ',' + tx[1] + ',' + tx[2] + ',' + a + ')';
    const o = { ink: tok('--text', '#222'), ink1: ink(0.06), ink2: ink(0.62), ink3: ink(0.42), soft: ink(0.07), accent: tok('--accent', '#e5a823'), font: tok('--sans', 'sans-serif'),
                hot: 'rgb(' + R.ramp(0.55).join(',') + ')', cellColor: (cellOf('hipp') || {}).color || '#3d9a8f', cursor: st.clip ? P.t : null, win: st.clip || null };
    cvs.forEach((cv) => {
      const k = cv.dataset.k;
      if (k === 'timeline') {
        const span = st.key === 'stumble' ? [-12, 0.5] : st.measure === 'mua' ? [0, 50] : [-0.5, 6.5];
        R.drawTimeline(cv, P.D, Object.assign({}, o, { t0: span[0], t1: span[1], measure: st.measure || 'absx', win: st.win || null, stage: st.figure != null ? st.figure + 1 : '' }));
      } else if (k === 'unit') R.drawUnit(cv, P.D, o);
      else if (k === 'raster') R.drawRaster(cv, P.D, o);
      else if (k === 'offs') R.drawOffs(cv, P.D, o);
    });
  }

  /* ==================================================================
     Sextant: where was the probe? One recording placed in the atlas from its
     own signals, click by click. seahorse_sextant.js has the words and the
     card's drawing; backend/sextant/ did the work, into
     web/seahorse/sextant/<gid>.json. The section is the coronal one through
     the answer; the cloud is every probe still plausible at that stop.
     ================================================================== */
  const SX = () => BARRY.shSextant;
  let sextIdx = null;
  async function sextIndex(force) {
    if (sextIdx && !force) return sextIdx;
    try { sextIdx = await getJSON('sextant/index.json'); } catch (err) { sextIdx = { recordings: [] }; }
    return sextIdx;
  }
  const sideWord = (s) => (s === 'L' ? 'left' : s === 'R' ? 'right' : 'side unknown');
  async function sextMenu(anchor) {
    const idx = await sextIndex();
    const rows = idx.recordings || [];
    if (!rows.length) { toast('No placements yet. Make them with: python tools/sextant/run.py --all', 'err', 8000); return; }
    const item = (r) => ({ label: r.mouse + ' · ' + (r.group === 'CTL' ? 'control' : 'PTEN') + ' · ' + sideWord(r.side),
      sub: SX().ap(r.entry.ap) + ', ' + SX().ml(Math.abs(r.entry.ml), r.side) + ' mm from bregma · AP ' + r.words.ap + ', ML ' + r.words.ml,
      icon: 'sextant', on: () => startSextant(r.gid) });
    UI.menu(anchor, [
      { title: 'Controls', items: rows.filter((r) => r.group === 'CTL').map(item) },
      { title: 'PTEN', items: rows.filter((r) => r.group !== 'CTL').map(item) },
    ].filter((g) => g.items.length), { where: 'above-center', width: 420 });
  }
  const lineMid = (l) => l[0].map((x, i) => (x + l[1][i]) / 2);
  /* contact x (0-based) on a 64-contact line; with a stretch {k, hinge} the
     dentate below the hinge is k times as spread out in the atlas (PTEN) */
  function lineAt(l, x, st) {
    let f = x / 63;
    if (st && st.k && st.hinge != null && Math.abs(st.k - 1) > 1e-3) {
      const h = st.hinge, k = st.k;
      f = (x <= h ? x : h + k * (x - h)) / (h + k * (63 - h));
    }
    return l[0].map((v, i) => v + (l[1][i] - v) * f);
  }
  const sextStretch = (P, st) => {
    const a = P && P.D && P.D.answer.stretch;
    return a ? { k: (st && st.k) || a.k, hinge: a.hinge } : null;
  };
  /* the layer under each of the 64 contacts of a line (the atlas's 10 um laminae) */
  function layersAlong(l, st) {
    const out = [];
    for (let c = 0; c < 64; c++) { const p = lineAt(l, c, st); const s = sampleAt(p[0], p[1], p[2]); const lam = s.lam ? lamByCode(s.lam) : null; out.push(lam ? lam.key : ''); }
    return out;
  }
  async function startSextant(gid, o) {
    o = o || {};
    endTour();
    stopPlay(true);
    UI.closeAll();
    const ok = await need(['three', 'mesh_brain.shb.gz', 'mesh_hpf.shb.gz', 'mesh_lamina.shb.gz', 'cells.shb.gz', 'brain50.shb.gz', 'hip20.shb.gz', 'fine10.shb.gz'],
      'Getting Sextant ready', 'The section the probe went through, and the hippocampus around it.');
    if (!ok) return;
    let D;
    try { D = await getJSON('sextant/' + gid + '.json'); } catch (err) {
      toast('This placement is missing (web/seahorse/sextant/' + gid + '.json). Make it with: python tools/sextant/run.py', 'err', 8000);
      return;
    }
    const stops = D.stops.slice();
    stops.push({ id: 'brain', title: 'In the brain', landmarks: [], profiles: [], best: D.answer.line, cloud: D.cloud });
    const P = { kind: 'sextant', gid, D, stops, i: -1, stop: null, seq: 0, moving: false, review: null, accepted: null,
                ap: lineMid(D.answer.line)[0] };
    S.play = P;
    sextAccepted(P);
    getJSON('sextant/planted.json').then((pl) => { P.planted = pl; if (S.play === P && (P.stop || {}).id === 'both') showCard({ type: 'sextant' }); }).catch(() => {});
    await runSextStop(o.at || 0);
  }
  async function runSextStop(i) {
    const P = S.play;
    if (!P || P.kind !== 'sextant') return;
    i = Math.max(0, Math.min(P.stops.length - 1, i));
    const st = P.stops[i];
    P.i = i; P.stop = st; P.seq++;
    const seq = P.seq;
    if (st.id !== 'both') P.review = null;
    st.layers = st.layers || layersAlong(st.best, sextStretch(P, st));
    S.focus = null;
    renderDock();
    showCard({ type: 'sextant' });
    renderRail();
    P.moving = true;
    try { await sextView(P, st); } finally { P.moving = false; }
    if (S.play !== P || P.seq !== seq || !S.stage) return;
    S.stage.mini = false;
    placeMini();
    syncProbe();
    renderNav();
    renderTools();
    sextOverlay(true);
    updateLabels();
  }
  function sextGo(i) { const P = S.play; if (P && P.kind === 'sextant') runSextStop(i); }
  function sextNext() {
    const P = S.play;
    if (!P || P.kind !== 'sextant') return;
    if (P.i >= P.stops.length - 1) stopPlay(); else runSextStop(P.i + 1);
  }
  /* the section through the answer, framed on what the stop's cloud spans --
     wide while the evidence is thin, closer as it narrows; the last stop
     stands back in 3D */
  async function sextView(P, st) {
    if (st.id === 'brain') {
      if (S.mode !== '3d') { S.level = 'hpf'; await setMode('3d'); } else if (S.level !== 'hpf') await setLevel('hpf');
      if (!S.stage) return;
      S.stage.setCut({ kind: 'coronal', pos: P.ap });
      const c = S.three.W(...lineMid(P.D.answer.line));
      const dir = [0.78, 0.42, -0.46], n = Math.hypot(...dir), d = 7.5;
      S.stage.fly(c.map((x, k) => x + dir[k] / n * d), c, 1600);
      return;
    }
    const fr = sextFrame(P, st);
    const same = S.mode === 'slice' && S.slice.plane === 'coronal' && Math.abs(S.slice.pos - P.ap) < 1 && !S.slice.tiltA && !S.slice.tiltB && !S.slice.custom;
    S.slice.plane = 'coronal'; S.slice.pos = P.ap; S.slice.tiltA = 0; S.slice.tiltB = 0; S.slice.custom = null;
    if (S.mode !== 'slice') { S.slice.C = fr.C; S.slice.k = fr.k; await setMode('slice'); }
    else await glideSlice(fr.C, fr.k, same ? 1100 : 0);
  }
  function sextFrame(P, st) {
    const host = $('.sh-host').getBoundingClientRect();
    const W = Math.max(240, host.width), H = Math.max(240, host.height);
    const dock = $('.sh-dock');
    const dockH = dock ? dock.getBoundingClientRect().height : 190;
    const room = Math.max(180, H - dockH - 2 * 16 - 24);
    const pts = [st.best].concat(st.cloud.slice(0, 40)).flatMap((l) => l);
    let m0 = Infinity, m1 = -Infinity, d0 = Infinity, d1 = -Infinity;
    pts.forEach((p) => { m0 = Math.min(m0, p[2]); m1 = Math.max(m1, p[2]); d0 = Math.min(d0, p[1]); d1 = Math.max(d1, p[1]); });
    const wUm = Math.max(1800, m1 - m0 + 900), hUm = Math.max(1500, d1 - d0 + 700);
    const k = Math.max(wUm / (W * 0.92), hUm / room);
    const yWant = 16 + room / 2;
    const cx = (m0 + m1) / 2, cy = (d0 + d1) / 2;
    return { C: [P.ap, cy + (H / 2 - yWant) * k, cx], k };
  }
  /* the probe as the stage draws it: the H3 from contact 64 up, its ribbon the
     layer under each contact */
  function sextProbeSpec(l, layers) {
    const d = [0, 1, 2].map((i) => l[1][i] - l[0][i]);
    const len = Math.hypot(...d), u = d.map((x) => x / len);
    const pitch = len / 63, first = 50 * pitch / 20;
    const tip = l[1].map((x, i) => x + u[i] * first);
    const ribbon = [];
    for (let i = 0; i < 64; i++) { const k = layers[63 - i]; ribbon.push(k ? lamColor(k) : '#8a8a8a'); }
    return { tip, dir: u, contacts: 64, pitch, first, length: 3200, ribbon };
  }
  /* what the 3D stage holds during Sextant: in 3D the answer and its cloud; on
     the section only the probe you are moving (the rest is the overlay) */
  function sextStage(P) {
    if (!S.stage || !P || !P.stop) return;
    if (S.mode === '3d') {
      S.stage.setProbe(sextProbeSpec(P.D.answer.line, P.D.answer.layers));
      if (S.stage.setCloud) S.stage.setCloud(P.stop.cloud, { color: tok('--accent', '#e5a823'), opacity: 0.16 });
    } else {
      if (S.stage.setCloud) S.stage.setCloud(null);
      S.stage.setProbe(P.review ? sextProbeSpec(P.review.line, P.review.layers) : null);
    }
  }
  function sextSeen(P) {
    const seen = new Set();
    for (let j = 0; j <= P.i; j++) (SX().LM_OF[P.stops[j].id] || []).forEach((k) => seen.add(k));
    if (P.stop && (P.stop.id === 'both' || P.stop.id === 'brain')) P.D.landmarks.forEach((l) => seen.add(l.key));
    return seen;
  }
  function sextOverlay(rebuild) {
    const P = S.play;
    let box = $('.sh-sext-over');
    const on = P && P.kind === 'sextant' && P.stop && P.stop.id !== 'brain' && S.mode === 'slice' && S.stage && S.stage.view === 'slice';
    if (!on) { if (box) box.remove(); return; }
    const B = stageBox();
    if (!B) return;
    if (!box) { box = el('div', { class: 'sh-sext-over', 'aria-hidden': 'true' }); $('.sh-stage').appendChild(box); rebuild = true; }
    if (rebuild) buildSextOverlay(box, P, B);
  }
  function buildSextOverlay(box, P, B) {
    const st = P.stop, D = P.D;
    const px = (p) => S.stage.ccfToSlicePx(p);
    const svg = el('svg', { class: 'sh-svg', width: B.W, height: B.H, viewBox: '0 0 ' + B.W + ' ' + B.H });
    // the cloud: every plausible probe, fainter the farther it runs from this section
    const g = el('g', { class: 'sext-cloud' });
    st.cloud.forEach((l) => {
      const a = px(l[0]), b = px(l[1]);
      const off = (Math.abs(a[2]) + Math.abs(b[2])) / 2;
      const op = 0.08 + 0.42 * Math.max(0, 1 - off / 700);
      g.appendChild(el('line', { x1: a[0], y1: a[1], x2: b[0], y2: b[1], style: 'opacity:' + op.toFixed(3) }));
    });
    svg.appendChild(g);
    const line = P.review ? P.review.line : st.best;
    const lay = P.review ? P.review.layers : st.layers;
    const stx = sextStretch(P, P.review ? null : st);
    const a = px(line[0]), b = px(line[1]);
    const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1;
    const nx = -dy / L, ny = dx / L;                      // across the shank
    if (!P.review) {
      svg.appendChild(el('line', { class: 'shank-halo', x1: a[0], y1: a[1], x2: b[0], y2: b[1] }));
      svg.appendChild(el('line', { class: 'shank', x1: a[0], y1: a[1], x2: b[0], y2: b[1] }));
    }
    // the layer ribbon beside the shank, contact by contact
    const rib = el('g', { class: 'sext-ribbon' });
    for (let c = 0; c < 64; c++) {
      if (!lay[c]) continue;
      const p0 = px(lineAt(line, c - 0.5, stx)), p1 = px(lineAt(line, c + 0.5, stx));
      rib.appendChild(el('line', { x1: p0[0] + nx * 7, y1: p0[1] + ny * 7, x2: p1[0] + nx * 7, y2: p1[1] + ny * 7, style: 'stroke:' + lamColor(lay[c]) }));
    }
    svg.appendChild(rib);
    // contact 1 and 64
    [[0, '1'], [63, '64']].forEach(([c, t]) => {
      const p = px(lineAt(line, c, stx));
      svg.appendChild(el('text', { class: 'sext-cno', x: p[0] - nx * 10 - (nx > 0 ? 14 : 0), y: p[1] - ny * 10 + 4 }, [t]));
    });
    // the landmarks found so far, on the shank, named in a column beside it
    const seen = sextSeen(P), mine = new Set(SX().LM_OF[st.id] || []);
    const rows = D.landmarks.filter((l) => seen.has(l.key) && l.fit !== false).map((l) => {
      const p = px(lineAt(line, Math.max(0, Math.min(63, l.x)), stx));
      return { l, x: p[0], y: p[1], mine: mine.has(l.key) };
    }).sort((u, v) => u.y - v.y);
    const lx = Math.max(a[0], b[0]) + 40, gap = 16;
    const ys = rows.map((r) => r.y);
    for (let i = 1; i < ys.length; i++) ys[i] = Math.max(ys[i], ys[i - 1] + gap);
    const over = ys.length ? ys[ys.length - 1] - (B.H - 18) : 0;
    if (over > 0) for (let i = ys.length - 1; i >= 0; i--) { ys[i] -= over; if (i && ys[i - 1] > ys[i] - gap) ys[i - 1] = ys[i] - gap; }
    rows.forEach((r, i) => {
      const y = ys[i], cls = r.mine ? ' mine' : '';
      svg.appendChild(el('circle', { class: 'sext-lm' + cls, cx: r.x, cy: r.y, r: r.mine ? 4.2 : 3 }));
      svg.appendChild(el('path', { class: 'lead' + cls, d: 'M' + (r.x + 6) + ',' + r.y + ' C' + (r.x + 20) + ',' + r.y + ' ' + (lx - 16) + ',' + y + ' ' + (lx - 4) + ',' + y }));
      svg.appendChild(el('text', { class: 'sext-lmlabel' + cls, x: lx, y: y + 4 }, [(SX().LM_WORDS[r.l.key] || r.l.key) + ' · ' + (r.l.side ? 'above 1' : (r.l.x + 1).toFixed(1))]));
    });
    box.innerHTML = '';
    box.appendChild(svg);
    Object.assign(box.style, { left: B.ox + 'px', top: B.oy + 'px', width: B.W + 'px', height: B.H + 'px' });
  }
  function endSextant(P) {
    P.seq++;
    cancelAnimationFrame(glideRaf);
    const n = $('.sh-sext-over'); if (n) n.remove();
    if (S.stage) {
      if (S.stage.setCloud) S.stage.setCloud(null);
      S.stage.setProbe(null);
      S.stage.mini = S.slice.mini;
    }
  }

  /* ---------- the dock ---------- */
  function sextAnswerWords(D) {
    const a = D.answer, r = a.ranges, w = a.words;
    const lean = (v, pos, neg) => (Math.abs(v) < 1 ? '' : Math.abs(v).toFixed(1) + '° ' + (v > 0 ? pos : neg));
    const leans = [lean(a.tilt_ml, 'lateral', 'medial'), lean(a.tilt_ap, 'back', 'forward')].filter(Boolean);
    return 'In at ' + SX().ap(a.entry.ap) + ', ' + SX().ml(Math.abs(a.entry.ml), D.side) + ' mm from bregma' +
      (leans.length ? ', leaning ' + leans.join(' and ') : ', straight down') +
      '; contact 1 ' + (a.depth_um.contact1 / 1000).toFixed(2) + ' mm deep, contact 64 ' + (a.depth_um.contact64 / 1000).toFixed(2) + ' mm. ' +
      'AP ' + w.ap + ' (±' + r.entry_ap.half.toFixed(2) + ' mm), ML ' + w.ml + ' (±' + r.entry_ml.half.toFixed(2) + '), depth ' + w.depth + ' (±' + Math.round(r.depth1.half) + ' µm), tilt ' + w.tilt + '.';
  }
  function fillSextant(box) {
    const P = S.play, st = P.stop, D = P.D;
    if (!st) return;
    const n = P.stops.length;
    box.appendChild(trHead('Sextant', D.mouse + ' · ' + (D.group === 'CTL' ? 'control' : 'PTEN' + (D.ko != null ? ' ' + D.ko + '% knockout' : '')) + ' · ' + sideWord(D.side) + ' hemisphere',
      [ofN('Stop', P.i + 1, n), P.accepted ? el('span', { class: 'sh-sext-acc', title: 'Accepted ' + (P.accepted.at || '').slice(0, 16).replace('T', ' ') + (P.accepted.by ? ' by ' + P.accepted.by : ''), text: 'Accepted' }) : null]));
    const prev = P.i > 0 ? P.stops[P.i - 1] : null;
    let words = st.id === 'brain' ? sextAnswerWords(D) : SX().say(D, st, prev);
    if (P.review) words = P.review.say || 'Grab the probe’s tip on the section and move it. When you let go, Sextant refits around where you put it, and says how well that fits against its own answer.';
    box.appendChild(el('div', { class: 'sh-tr-say' }, [el('b', { text: (P.review ? 'Your probe' : st.title) + '. ' }), words]));
    box.appendChild(el('div', { class: 'sh-tr-dots sh-sext-dots' }, P.stops.map((s, i) => el('button', { type: 'button', tabindex: '-1',
      class: (i < P.i ? 'done' : i === P.i ? 'now' : ''), title: s.title, 'aria-label': 'Stop ' + (i + 1) + ': ' + s.title, onclick: () => sextGo(i) }))));
    const last = P.i >= n - 1;
    const ctl = el('div', { class: 'sh-tr-ctl' }, [
      UI.button({ icon: 'prev', cls: 'icon quiet', aria: 'Back a stop', title: 'Back a stop (←)', disabled: P.i <= 0, onclick: () => sextGo(P.i - 1) }),
      el('span', { class: 'grow' }),
    ]);
    if (st.id === 'both' || st.id === 'brain') {
      ctl.appendChild(UI.seg('Probe', [['answer', 'Sextant’s', 'Sextant’s answer, from the recording alone'], ['review', 'Yours', 'Move the probe yourself; Sextant refits around it']],
        P.review ? 'review' : 'answer', (v) => sextReview(v === 'review'), { small: true }));
      ctl.appendChild(UI.button({ icon: 'check', text: P.review && P.review.state === 'refit' ? 'Accept yours' : 'Accept', cls: 'sm',
        title: 'Keep this placement for ' + D.mouse + ' (StrataScope then offers its layers as a proposal)', onclick: () => sextAccept() }));
    }
    ctl.appendChild(UI.button({ icon: 'next', text: last ? 'Finish' : 'Next', cls: 'sm sh-next solid sh-ready', title: (last ? 'Finish' : 'Next stop') + ' (→)', onclick: () => sextNext() }));
    box.appendChild(ctl);
    const ctl2 = el('div', { class: 'sh-tr-ctl' }, [
      el('span', { class: 'sh-small', text: P.stop.id === 'prior' ? 'Faint lines: every probe still plausible. Solid: the best so far.' : 'Faint: still plausible. Solid: the best. Dots: what the recording found.' }),
      el('span', { class: 'grow' }),
      UI.button({ text: 'End', cls: 'sm quiet', title: 'End (Esc)', onclick: () => stopPlay() }),
    ]);
    box.appendChild(ctl2);
  }

  /* ---------- review: you move it, Sextant refits ---------- */
  function sextReview(on) {
    const P = S.play;
    if (!P || P.kind !== 'sextant') return;
    if (!on) { P.review = null; renderDock(); sextStage(P); sextOverlay(true); showCard({ type: 'sextant' }); return; }
    P.review = { line: P.D.answer.line.map((p) => p.slice()), layers: P.D.answer.layers.slice(), state: 'answer', say: null };
    const go = () => { renderDock(); sextStage(P); sextOverlay(true); showCard({ type: 'sextant' }); };
    const both = P.stops.findIndex((s) => s.id === 'both');
    if (P.stop.id === 'brain') runSextStop(both).then(() => { P.review = P.review || { line: P.D.answer.line.map((p) => p.slice()), layers: P.D.answer.layers.slice(), state: 'answer' }; go(); });
    else go();
  }
  function sextDrag(ccf, end) {
    const P = S.play;
    if (!P || !P.review) return;
    if (!end) {
      if (!ccf) return;
      const l = P.review.line;
      const len = Math.hypot(...l[1].map((x, i) => x - l[0][i]));
      const u = l[1].map((x, i) => (x - l[0][i]) / len);
      const pitch = len / 63, first = 50 * pitch / 20;
      const c64 = ccf.map((x, i) => x - u[i] * first);
      P.review.line = [c64.map((x, i) => x - u[i] * len), c64];
      P.review.layers = layersAlong(P.review.line, sextStretch(P, null));
      P.review.state = 'moved';
      sextStage(P);
      sextOverlay(true);
      return;
    }
    sextRefit(P);
  }
  async function sextRefit(P) {
    const seq = P.seq;
    P.review.say = 'Refitting around where you put it…';
    renderDock();
    try {
      const res = await apiPost('/api/sextant/' + encodeURIComponent(P.gid) + '/refit', { line: P.review.line });
      if (S.play !== P || P.seq !== seq || !P.review) return;
      P.review.line = res.line;
      P.review.layers = layersAlong(res.line, sextStretch(P, null));
      P.review.state = 'refit';
      P.review.res = res;
      const d = res.delta;
      P.review.say = 'Sextant refitted around where you put it (it moved ' + Math.round(res.moved_um) + ' µm to fit). ' +
        (d > -2 ? 'It fits about as well as Sextant’s own answer: the recording cannot tell the two apart.' :
          'It fits worse than Sextant’s own answer by ' + Math.abs(d).toFixed(1) + ' (log-likelihood): ' + (res.worst ? res.worst + ' disagree most.' : ''));
      sextStage(P);
      sextOverlay(true);
      renderDock();
      showCard({ type: 'sextant' });
    } catch (err) {
      P.review.say = 'The refit needs Jarvis’s server (' + err.message + ').';
      renderDock();
    }
  }
  async function sextAccepted(P) {
    try {
      const res = await apiPost('/api/sextant/' + encodeURIComponent(P.gid) + '/accepted', {});
      if (S.play === P && res && res.accepted) { P.accepted = res.accepted; renderDock(); }
    } catch (err) { /* no server: nothing accepted to show */ }
  }
  async function sextAccept() {
    const P = S.play;
    if (!P || P.kind !== 'sextant') return;
    const line = P.review ? P.review.line : P.D.answer.line;
    try {
      const res = await apiPost('/api/sextant/' + encodeURIComponent(P.gid) + '/accept',
        { line, source: P.review ? P.review.state : 'sextant', layers: P.review ? P.review.layers : P.D.answer.layers });
      P.accepted = res.accepted;
      toast('Accepted for ' + P.D.mouse + '. StrataScope now offers these layers as a proposal on this recording.', 'ok', 7000);
      renderDock();
    } catch (err) { toast('Not accepted: ' + err.message, 'err', 8000); }
  }

  /* ---------- the card ---------- */
  function renderSextantCard(card) {
    const P = S.play;
    if (!P || P.kind !== 'sextant' || !P.stop) return renderAbout(card);
    const st = P.stop, D = P.D, R = SX();
    const head = cardHead([el('span', { class: 'sh-evtag rec', text: st.id === 'prior' ? 'Before' : st.id === 'both' || st.id === 'brain' ? 'The answer' : 'On the probe' }),
      el('span', { text: D.mouse + ' · ' + (D.label || D.gid) })], st.title, {});
    head.classList.add('sh-sext-head');
    card.appendChild(head);
    const prev = P.i > 0 ? P.stops[P.i - 1] : null;
    card.appendChild(el('p', { class: 'sh-lede', text: st.id === 'brain' ? sextAnswerWords(D) : R.say(D, st, prev) }));
    if (st.id !== 'prior') card.appendChild(el('div', { class: 'sh-story-panel' }, [el('canvas', { class: 'sh-sext-cv' }),
      el('div', { class: 'sh-small', text: 'Down the shank, contact 1 at the top. Each curve on its own scale; currents as bars (sinks red, to the left; sources blue). Lines cross at what the recording found; the strip is the layer the atlas puts under each contact for the best probe.' })]));
    const keys = new Set(R.LM_OF[st.id] || []);
    const found = D.landmarks.filter((l) => keys.has(l.key));
    if (found.length) {
      card.appendChild(el('h3', { text: 'What the recording found' }));
      card.appendChild(el('div', { class: 'sh-probe-table' }, found.map((l) => el('div', {}, [
        el('span', { class: 'ch', text: l.side ? 'above 1' : 'contact ' + (l.x + 1).toFixed(1) }),
        el('span', { text: (R.LM_WORDS[l.key] || l.key) + (l.fit === false ? ' (shown, not fitted)' : '') + ': ' + l.why + ' (' + l.source + ').' }),
      ]))));
    }
    if (st.id === 'both' || st.id === 'brain') {
      const a = D.answer, r = a.ranges;
      const row = (k, v, rr, w) => el('div', {}, [el('span', { class: 'ch', text: k }), el('span', { text: v + (rr ? '  [' + rr + ']' : '') }), w ? el('span', { class: 'sh-sext-word ' + w, text: w }) : null]);
      card.appendChild(el('h3', { text: 'The answer' }));
      card.appendChild(el('div', { class: 'sh-probe-table sh-sext-nums' }, [
        row('Entry AP', R.mm(a.entry.ap) + ' mm', R.mm(r.entry_ap.lo) + ' to ' + R.mm(r.entry_ap.hi), a.words.ap),
        row('Entry ML', (D.side === 'L' ? '−' : '+') + Math.abs(a.entry.ml).toFixed(2) + ' mm', r.entry_ml.lo.toFixed(2) + ' to ' + r.entry_ml.hi.toFixed(2), a.words.ml),
        row('Contact 1', (a.depth_um.contact1 / 1000).toFixed(2) + ' mm deep', (r.depth1.lo / 1000).toFixed(2) + ' to ' + (r.depth1.hi / 1000).toFixed(2), a.words.depth),
        row('Contact 64', (a.depth_um.contact64 / 1000).toFixed(2) + ' mm deep', (r.depth64.lo / 1000).toFixed(2) + ' to ' + (r.depth64.hi / 1000).toFixed(2), null),
        row('Tilt', a.tilt_ml.toFixed(1) + '° lateral, ' + a.tilt_ap.toFixed(1) + '° back', null, a.words.tilt),
        row('Size', '×' + a.scale.toFixed(2) + ' the atlas along the shank', r.scale.lo.toFixed(2) + ' to ' + r.scale.hi.toFixed(2), null),
      ].concat(a.stretch ? [row('Dentate', '×' + a.stretch.k.toFixed(2) + ' as thick as CA1’s size says' + (a.stretch.normal ? ' (controls ×' + a.stretch.normal.lo.toFixed(2) + ' to ×' + a.stretch.normal.hi.toFixed(2) + ')' : ''),
        r.k ? r.k.lo.toFixed(2) + ' to ' + r.k.hi.toFixed(2) : null, a.stretch.normal ? (a.stretch.outside ? 'outside normal' : 'normal') : null)] : [])));
      card.appendChild(el('p', { class: 'sh-small', text: 'Ranges are 95% of the cloud. Sure: within ±0.15 mm (±60 µm in depth, ±4° tilt); likely: within ±0.35 mm (±150 µm, ±9°); wider is a guess. AP is the hardest from one shank: the hippocampus changes slowly front to back.' }));
      const pl = P.planted && P.planted.summary;
      if (pl) {
        const pc = (k) => Math.round(100 * pl[k].covered) + '%';
        card.appendChild(el('p', { class: 'sh-small', text: 'Found again: ' + P.planted.n + ' probes planted at known places near the craniotomy, their evidence made from the atlas with each detector’s own scatter, and searched for blind. Sextant was off by a median ' +
          pl.ap.median_abs.toFixed(2) + ' mm in AP, ' + pl.ml.median_abs.toFixed(2) + ' mm in ML, ' + Math.round(1000 * pl.depth.median_abs) + ' µm in depth and ' + pl.tilt_ml.median_abs.toFixed(1) + '° in tilt; the 95% ranges held the plant ' +
          pc('ap') + ' (AP), ' + pc('ml') + ' (ML), ' + pc('depth') + ' (depth) of the time. That is the method’s own precision when the atlas is right; a real brain that differs from the atlas adds to it.' }));
      }
      const M = D.methods;
      const gap = (x, y) => Math.round(1000 * Math.hypot(x.entry.ap - y.entry.ap, Math.abs(x.entry.ml) - Math.abs(y.entry.ml)));
      card.appendChild(el('h3', { text: 'Each method alone' }));
      card.appendChild(el('div', { class: 'sh-probe-table' }, [
        row('Landmarks', R.ap(M.A.entry.ap) + ', ' + R.ml(Math.abs(M.A.entry.ml), D.side), gap(M.A, M.consolidated) + ' µm from the answer', null),
        row('Simulated', R.ap(M.B.entry.ap) + ', ' + R.ml(Math.abs(M.B.entry.ml), D.side), gap(M.B, M.consolidated) + ' µm from the answer', null),
      ]));
      card.appendChild(el('p', { class: 'sh-small', text: 'Landmarks (Method A): where each layer’s signal was found, against where the atlas puts that layer on each candidate probe. Simulated (Method B): each pathway’s current laid on the atlas layers of a candidate probe, turned into voltage at all 64 contacts, and matched to the recording’s dentate spikes, sharp waves and theta as currents. The answer adds the two.' }));
      card.appendChild(el('h3', { text: 'Drop one signal' }));
      card.appendChild(el('div', { class: 'sh-probe-table' }, D.drops.map((d) => el('div', {}, [
        el('span', { class: 'ch', text: d.kind === 'profile' ? 'curve' : 'landmark' }),
        el('span', { text: (R.LM_WORDS[d.key] || { ds: 'dentate spikes', ps: 'P-spikes', bt: 'borderline transients', spw: 'sharp wave', theta: 'theta', mua: 'multiunit', rip: 'ripple power' }[d.key] || d.key) + ': the answer moves ' + d.move_um + ' µm' }),
        d.fragile ? el('span', { class: 'sh-sext-word guess', text: 'leans on it' }) : null,
      ]))));
      card.appendChild(el('p', { class: 'sh-small', text: 'Each signal taken out in turn and the probe found again. "Leans on it": without that one signal the answer moves farther than the cloud is wide.' }));
    }
    const refs = (R.FAMILY[st.id] || {}).refs || [];
    if (refs.length) card.appendChild(el('div', { class: 'sh-actions' }, [citeChips(refs)]));
    card.appendChild(el('h3', { text: 'Every stop (' + P.stops.length + ')' }));
    card.appendChild(el('div', { class: 'sh-story-toc' }, P.stops.map((s, i) => el('button', { type: 'button', class: 'sh-story-tocrow' + (i === P.i ? ' on' : ''), onclick: () => sextGo(i) }, [
      el('i', { class: 'rec' }), el('span', { text: s.title })]))));
    card.appendChild(el('h3', { text: 'About Sextant' }));
    const c = D.evidence.counts;
    card.appendChild(el('div', { class: 'sh-src' }, [
      el('div', {}, [el('b', { text: 'The recording. ' }), (D.label || D.gid) + '. ' + c.ripples + ' ripples, ' + c.troughs + ' theta cycles, ' + c.ds + ' dentate spikes' + (c.ps ? ', ' + c.ps + ' P-spikes' : '') + (c.bt ? ', ' + c.bt + ' borderline transients' : '') + ' (Root Canal’s Halo run). ' + Math.round(D.evidence.walk_s) + ' s of theta walking (' + (D.evidence.states === 'painted' ? 'painted in StrataScope' : 'found by StrataScope’s finder') + '). Contacts left out: ' + (D.bad.length ? D.bad.join(', ') : 'none') + '.']),
      el('div', { text: 'The probe: an H3, 64 contacts 20 µm apart, contact 1 at the top. Recorded in the ' + sideWord(D.side) + ' hemisphere (the lab’s feeder sheet); drawn on the right, where the layer atlas is.' }),
      el('div', { text: 'The atlas: Allen CCFv3 (2017) at 10 µm, with Seahorse’s derived CA strata and molecular-layer thirds. Bregma is the International Brain Laboratory’s (AP 5400, DV 332 µm in the CCF); the CCF has no official one.' }),
      el('div', { text: 'Never used: the lab’s layer labels, as evidence or as a check. The craniotomy (AP −2.2, ML ±1.4 mm) is a loose prior (±0.6 mm AP, ±0.5 mm ML).' }),
    ].concat((D.notes || []).map((t) => el('div', { text: t })))));
    requestAnimationFrame(() => drawSextPanels(P));
  }
  function drawSextPanels(P) {
    const cv = $('.sh-card canvas.sh-sext-cv');
    if (!cv || !P.stop) return;
    const tx = hexRgb(tok('--text', '#222'));
    const ink = (a) => 'rgba(' + tx[0] + ',' + tx[1] + ',' + tx[2] + ',' + a + ')';
    const st = P.review ? Object.assign({}, P.stop, { layers: P.review.layers }) : P.stop;
    SX().drawEvidence(cv, P.D, st, { font: tok('--sans', 'sans-serif'), ink1: ink(0.1), ink2: ink(0.62), ink3: ink(0.42), soft: ink(0.05),
      line: tok('--text', '#222'), accent: tok('--accent', '#e5a823'), sink: SINK, source: SOURCE, seen: sextSeen(P),
      layerColor: (k) => (k ? lamColor(k) : null), layerShort: (k) => (k ? ((lamOf(k) || {}).label || k) : '—') });
  }

  /* ==================================================================
     Tours, and the pathways hop by hop
     ================================================================== */
  function startTour(key) {
    stopPlay(true);
    UI.closeAll();
    const ts = BARRY.shLearn.tours(S.kb, { probeAp: 5400 - S.probe.ap * 1000 });
    const t = ts.find((x) => x.key === key);
    if (!t) return;
    let beats = t.beats;
    if (key === 'probe') {
      if (!S.blobs['brain50.shb.gz']) { need(['brain50.shb.gz', 'hip20.shb.gz', 'fine10.shb.gz'], 'Getting the layers ready', '').then((ok) => { if (ok) startTour(key); }); return; }
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
    renderDock();
    for (const a of b.do || []) { if (S.tour !== T) return; await doAction(a); }
    renderDock();
  }
  function resumeTour() { if (S.tour) renderDock(); }
  function endTour() { if (S.tour) { S.tour = null; renderDock(); } }
  async function doAction([op, arg]) {
    if (op === 'mode') { if (S.mode !== arg) await setMode(arg); }
    else if (op === 'level') { if (S.level !== arg || S.mode !== '3d') await setLevel(arg); }
    else if (op === 'slice') { S.slice.plane = arg.plane || 'coronal'; S.slice.pos = arg.pos || S.slice.pos; S.slice.tiltA = 0; S.slice.tiltB = 0; if (S.mode !== 'slice') await setMode('slice'); sliceZoom(arg.zoom || 'hippocampus'); renderNav(); }
    else if (op === 'layers') { S.focus = { cells: new Set(), regionKeys: new Set(), conns: new Set(), layers: new Set(arg) }; applyFocusAll(); }
    else if (op === 'schem') { S.schemPick = arg; renderRail(); }
    else if (op === 'select') select(arg);
    else if (op === 'event') await playEvent(arg, { fromTour: S.tour && S.tour.key });
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
  /* the region-level pathways: hop by hop in the map */
  function startPath(key) {
    stopPlay(true);
    endTour();
    UI.closeAll();
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
    renderDock();
    renderRail();
  }

  /* ==================================================================
     The dock: what plays. Idle, three menus; playing, one transport for
     rides, events, tours and pathways.
     ================================================================== */
  function dockKind() { return S.tour ? 'tour' : S.play ? S.play.kind : 'launch'; }
  function renderDock() {
    const dock = $('.sh-dock');
    if (!dock || !S.kb) return;
    const kind = dockKind();
    let box = dock.firstElementChild;
    if (!box || box.dataset.kind !== kind) {
      dock.innerHTML = '';
      box = el('div', { class: (kind === 'launch' ? 'sh-launch' : 'sh-tr') + ' sh-glass', 'data-kind': kind, role: kind === 'launch' ? 'toolbar' : 'region', 'aria-label': kind === 'launch' ? 'Play' : 'Now playing' });
      dock.appendChild(box);
    } else box.innerHTML = '';
    dock.classList.toggle('playing', kind !== 'launch');
    if (kind === 'launch') fillLauncher(box);
    else if (kind === 'tour') fillTour(box);
    else if (kind === 'ride') fillRide(box);
    else if (kind === 'event') fillEvent(box);
    else if (kind === 'path') fillPath(box);
    else if (kind === 'story') fillStory(box);
    else if (kind === 'sextant') fillSextant(box);
    updateLabels();
  }
  function fillLauncher(box) {
    const b = (icon, text, title, menu) => {
      const x = UI.button({ icon, text, title, onclick: (e) => menu(e.currentTarget) });
      const c = UI.icon('up'); c.classList.add('caret'); x.appendChild(c);
      x.setAttribute('aria-haspopup', 'menu');
      return x;
    };
    box.appendChild(b('ride', 'Ride a signal', 'Follow one signal along real cells', rideMenu));
    box.appendChild(el('span', { class: 'sep' }));
    box.appendChild(b('wave', 'Play an event', 'Dentate spikes, ripples, theta: model laminar profiles', eventMenu));
    box.appendChild(el('span', { class: 'sep' }));
    box.appendChild(b('tour', 'Take a tour', 'Guided tours, and the pathways hop by hop', tourMenu));
    box.appendChild(el('span', { class: 'sep' }));
    box.appendChild(b('burst', 'Watch a seizure', 'A recorded seizure, click by click: where the circuit first fails, how it spreads, what follows', storyMenu));
    box.appendChild(el('span', { class: 'sep' }));
    box.appendChild(b('sextant', 'Place a probe', 'Sextant: where a recording\u2019s probe was, from its own signals, click by click', sextMenu));
  }
  function storyMenu(anchor) {
    UI.menu(anchor, [{ title: 'Recorded, then explained', items: ST().stories().map((s) => ({ label: s.label, sub: s.blurb, icon: 'burst', on: () => startStory(s.key) })) }],
      { where: 'above-center', width: 380 });
  }
  const evColor = (kind) => kind === 'ds' ? tok('--call-ds', '#5aa9ff') : kind === 'pspike' ? tok('--call-p', '#ff6b5e') : kind === 'custom' ? tok('--text-3', '#999') : tok('--accent', '#e5a823');
  function rideMenu(anchor) {
    const rides = ((S.rides && S.rides.rides) || []).filter((r) => r.kind !== 'event');
    UI.menu(anchor, [{ title: 'Along real cells that touch', items: rides.map((r) => ({ label: r.label, sub: r.blurb, icon: 'ride', on: () => startRide(r.key) })) }],
      { where: 'above-center', width: 380 });
  }
  function eventMenu(anchor) {
    const E = BARRY.shPhys.EVENTS;
    UI.menu(anchor, [
      { title: 'Models on the probe\'s ' + S.probe.contacts + ' contacts', items: Object.entries(E).map(([k, e]) => ({ label: e.label,
        sub: k === 'pspike' ? 'The Barry lab is working on it' : firstSentence(e.say), swatch: evColor(e.kind), on: () => playEvent(k) })) },
      { items: [{ label: 'Your own', sub: 'Choose the sources, their strengths and onsets, then play it', icon: 'plus', on: () => showCard({ type: 'compose' }) }] },
    ], { where: 'above-center', width: 380 });
  }
  function tourMenu(anchor) {
    const ts = BARRY.shLearn.tours(S.kb, { probeAp: 5400 - S.probe.ap * 1000 });
    UI.menu(anchor, [
      { title: 'Guided tours', items: ts.map((t) => ({ label: t.label, sub: t.blurb, icon: 'tour', on: () => startTour(t.key) })) },
      { title: 'Pathways, hop by hop', items: (S.kb.pathways || []).map((p) => ({ label: p.label, sub: p.blurb, icon: 'nodes', on: () => startPath(p.key) })) },
    ], { where: 'above-center', width: 380 });
  }
  function playBtn(playing, on) {
    return UI.button({ icon: playing ? 'pause' : 'play', cls: 'icon sh-tr-play' + (playing ? '' : ' solid'), aria: playing ? 'Pause' : 'Play', title: (playing ? 'Pause' : 'Play') + ' (Space)', onclick: on });
  }
  const trHead = (k, title, meta) => el('div', { class: 'sh-tr-head' }, [el('span', { class: 'sh-tr-k', text: k }), el('span', { class: 'sh-tr-title', text: title }), meta ? el('span', { class: 'sh-tr-meta' }, [].concat(meta)) : null]);
  const ofN = (word, i, n) => el('span', {}, [word + ' ', el('b', { text: String(i) }), ' of ' + n]);
  function fillRide(box) {
    const P = S.play;
    const st = P.step || P.ride.steps[0];
    const n = P.ride.steps.length;
    const rs = S.stage && S.stage.rideState;
    const clockTip = st.velocity ? st.velocity.source : ((S.rides.delay[st.kind] || {}).source || '');
    box.appendChild(trHead('Ride', P.ride.label, [ofN('Step', Math.min(n, P.i + 1), n), el('span', { title: clockTip }, ['t = ', el('b', { text: (st.ms ? st.ms[0].toFixed(1) : '0.0') + ' ms' })])]));
    const say = el('div', { class: 'sh-tr-say' }, [el('b', { text: st.title + '. ' }), st.say ? st.say + ' ' : '', citeChips(st.cite)]);
    if (st.drawn) say.appendChild(el('span', { class: 'sh-tag drawn', text: 'Drawn path' }));
    box.appendChild(say);
    if (st.velocity) box.appendChild(el('div', { class: 'sh-small', text: '+' + st.ms[1].toFixed(1) + ' ms: ' + (st.len_um / 1000).toFixed(2) + ' mm at ' + st.velocity.m_per_s + ' m/s (' + st.velocity.source + ')' }));
    if (st.lab) box.appendChild(el('div', { class: 'sh-tr-lab', text: st.lab }));
    box.appendChild(el('div', { class: 'sh-tr-dots', 'aria-hidden': 'true' }, P.ride.steps.map((s, i) => el('i', { class: (i < P.i ? 'done' : i === P.i ? 'now' : '') + ' ' + s.kind, title: s.title }))));
    box.appendChild(el('div', { class: 'sh-tr-ctl' }, rideButtons(P, rs).concat([
      rs && rs.manual ? UI.button({ icon: 'frame', text: 'Follow', cls: 'sm', title: 'Let the camera follow the signal again (F)', onclick: () => { S.stage.reframe(); renderDock(); } }) : null,
      el('span', { class: 'grow' }),
      UI.button({ icon: 'record', text: S.rec ? 'Stop recording' : 'Record the ride', cls: 'sm' + (S.rec ? ' sh-rec-on' : ''), onclick: () => (S.rec ? stopRecord() : recordRide()) }),
      UI.button({ text: P.done ? 'Done' : 'End', cls: 'sm', onclick: () => stopPlay() }),
    ])));
    box.appendChild(el('div', { class: 'sh-tr-ctl' }, [
      UI.seg('Advance', [[false, 'Step by step', 'Each step waits for your click'], [true, 'Play through', 'The steps follow one another on their own']], !!S.rideAuto,
        (v) => { S.rideAuto = v; store.set({ rideAuto: v }); if (S.stage) S.stage.setRideAuto(v); renderDock(); }, { small: true }),
      rs && rs.hold && !P.done ? el('span', { class: 'sh-small', text: 'Waiting for you: Next step, or the → key.' }) : null,
    ]));
  }
  /* Back, pause and Next step for a ride; Next step lights up while the ride waits for you. */
  function rideButtons(P, rs) {
    const n = P.ride.steps.length;
    const holding = !!(rs && rs.hold) && !P.done;
    const last = P.i >= n - 1;
    return [
      UI.button({ icon: 'prev', cls: 'icon quiet', aria: 'Back a step', title: 'Back a step (←)', disabled: P.i <= 0 || P.done, onclick: () => S.stage.stepRide(-1) }),
      UI.button({ icon: rs && rs.paused ? 'play' : 'pause', cls: 'icon quiet', aria: rs && rs.paused ? 'Play' : 'Pause', title: (rs && rs.paused ? 'Play' : 'Pause') + ' this step',
        disabled: holding || P.done, onclick: () => { S.stage.pauseRide(); renderDock(); } }),
      UI.button({ icon: 'next', text: last ? 'Finish' : 'Next step', cls: 'sm sh-next' + (holding ? ' solid sh-ready' : ''), title: (last ? 'Finish the ride' : 'Next step') + ' (→ or Space)',
        disabled: P.done, onclick: () => S.stage.stepRide(1) }),
    ];
  }
  function fillEvent(box) {
    const P = S.play;
    box.appendChild(trHead('Model · not a recording', P.ev.label, [el('span', { class: 'sh-legend' }, [el('span', { class: 'sink', text: 'sink' }), el('span', { class: 'source', text: 'source' })])]));
    box.appendChild(el('div', { class: 'sh-tr-say' }, [P.ev.say + ' ', citeChips(P.ev.refs)]));
    box.appendChild(el('div', { class: 'sh-tr-evs' }, eventChips(P.key)));
    const scrub = UI.range({ min: 0, max: P.ev.ms, step: P.ev.ms > 300 ? 1 : 0.25, value: P.t, fmt: (v) => (+v).toFixed(1) + ' / ' + P.ev.ms + ' ms', aria: 'Time in the event', wide: true,
      on: (v) => { P.paused = true; P.t = v; P.fired = new Set((P.ev.drives || []).map((d, i) => (d.t <= P.t - 4 ? i : -1)).filter((i) => i >= 0)); syncEventPlay(); } });
    scrub.classList.add('sh-tr-scrub');
    box.appendChild(el('div', { class: 'sh-tr-ctl' }, [playBtn(!P.paused, toggleEventPause), scrub]));
    box.appendChild(el('div', { class: 'sh-tr-ctl' }, [
      UI.seg('Speed', SPEEDS.map(([v, t]) => [v, t, t + ' of real time']), P.speed, (v) => { P.speed = v; S.evSpeed = v; store.set({ evSpeed: v }); }, { small: true }),
      UI.seg('Loop', [[true, 'On'], [false, 'Off']], S.evLoop, (v) => { S.evLoop = v; store.set({ evLoop: v }); }, { small: true }),
      el('span', { class: 'grow' }),
      UI.button({ text: 'Done', cls: 'sm solid', onclick: () => stopPlay() }),
    ]));
  }
  function syncEventPlay() {
    const P = S.play;
    const b = $('.sh-tr-play');
    if (!b || !P || P.kind !== 'event') return;
    b.replaceWith(playBtn(!P.paused, toggleEventPause));
  }
  function toggleEventPause() {
    const P = S.play;
    if (!P || P.kind !== 'event') return;
    if (P.paused && P.t >= P.ev.ms) { P.t = 0; P.fired.clear(); }
    P.paused = !P.paused;
    syncEventPlay();
  }
  function fillTour(box) {
    const T = S.tour, b = T.beats[T.i], P = S.play;
    box.appendChild(trHead('Tour', T.label, [ofN('Stop', T.i + 1, T.beats.length)]));
    box.appendChild(el('div', { class: 'sh-tr-say' }, [el('b', { text: b.title + '. ' }), b.say || '']));
    if (P && P.kind === 'ride' && P.step) box.appendChild(el('div', { class: 'sh-tr-lab' }, [el('b', { text: P.step.title + ': ' }), P.step.say || '']));
    if (P && P.kind === 'event') box.appendChild(el('div', { class: 'sh-tr-lab' }, [el('b', { text: P.ev.label + ', a model: ' }), 'the layers light red where the current sinks and blue where it returns.']));
    box.appendChild(el('div', { class: 'sh-tr-dots', 'aria-hidden': 'true' }, T.beats.map((x, i) => el('i', { class: i < T.i ? 'done' : i === T.i ? 'now' : '', title: x.title }))));
    const ctl = el('div', { class: 'sh-tr-ctl' });
    if (P && P.kind === 'ride') { rideButtons(P, S.stage && S.stage.rideState).forEach((b) => ctl.appendChild(b)); ctl.appendChild(el('span', { class: 'sep-v' })); }
    if (P && P.kind === 'event') ctl.appendChild(playBtn(!P.paused, toggleEventPause));
    ctl.appendChild(UI.button({ icon: 'left', text: 'Back a stop', cls: 'sm', disabled: T.i <= 0, onclick: () => { T.i--; runBeat(); } }));
    ctl.appendChild(UI.button({ text: T.i >= T.beats.length - 1 ? 'Finish the tour' : 'Next stop', cls: 'sm' + (P && P.kind === 'ride' && !P.done ? '' : ' solid'), onclick: () => { if (T.i >= T.beats.length - 1) { endTour(); stopPlay(); } else { T.i++; runBeat(); } } }));
    ctl.appendChild(el('span', { class: 'grow' }));
    ctl.appendChild(UI.button({ text: 'End tour', cls: 'sm quiet', onclick: () => { endTour(); stopPlay(); } }));
    box.appendChild(ctl);
  }
  function fillPath(box) {
    const P = S.play, hop = P.path.hops[P.i];
    box.appendChild(trHead('Pathway', P.path.label, [ofN('Hop', P.i + 1, P.path.hops.length)]));
    box.appendChild(el('div', { class: 'sh-tr-say', text: hop.say }));
    box.appendChild(el('div', { class: 'sh-tr-dots', 'aria-hidden': 'true' }, P.path.hops.map((x, i) => el('i', { class: i < P.i ? 'done' : i === P.i ? 'now' : '' }))));
    box.appendChild(el('div', { class: 'sh-tr-ctl' }, [
      UI.button({ icon: 'left', text: 'Back', cls: 'sm', disabled: P.i <= 0, onclick: () => { P.i--; showHop(); } }),
      UI.button({ text: P.i >= P.path.hops.length - 1 ? 'Done' : 'Next', cls: 'sm solid', onclick: () => { if (P.i >= P.path.hops.length - 1) stopPlay(); else { P.i++; showHop(); } } }),
      el('span', { class: 'grow' }),
      UI.button({ text: 'End', cls: 'sm quiet', onclick: () => stopPlay() }),
    ]));
  }

  /* ==================================================================
     Quiz
     ================================================================== */
  async function openQuiz() {
    endTour();
    stopPlay();
    UI.closeAll();
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
    const kicker = 'Quiz · ' + Q.q.due.length + ' due · ' + Q.q.fresh.length + ' new' + (S.lab.me ? ' · ' + S.lab.me : '');
    if (!c) {
      card.appendChild(cardHead(kicker, 'All done for now', { lead: el('span', { class: 'sh-logo' }, [UI.icon('check')]) }));
      card.appendChild(el('p', { class: 'sh-lede', text: 'Nothing is due. Cards come back on the Anki schedule: a day, a few days, then longer as you get them right.' }));
      card.appendChild(el('div', { class: 'sh-actions' }, [UI.button({ text: 'Close the quiz', cls: 'sm', onclick: () => { S.quiz = null; showCard(S.sel); } })]));
      return;
    }
    card.appendChild(cardHead(kicker, c.prompt, { lead: el('span', { class: 'sh-logo' }, [UI.icon('quiz')]) }));
    if (!Q.shown) { Q.shown = true; await showQuizVisual(c); }
    const opts = el('div', { class: 'sh-quiz-opts' }, c.options.map((o) => el('button', {
      type: 'button', class: 'sh-quiz-opt' + (Q.answered ? (o === c.answer ? ' right' : o === Q.answered ? ' wrong' : '') : ''), text: o, disabled: Q.answered ? 'disabled' : null,
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
      card.appendChild(el('div', { class: 'sh-actions' }, [
        UI.button({ text: 'Again (10 min)', cls: 'sm', onclick: () => grade(0) }),
        UI.button({ text: 'Hard', cls: 'sm', onclick: () => grade(3) }),
        UI.button({ text: 'Good', cls: 'sm solid', onclick: () => grade(right ? 4 : 3) }),
        UI.button({ text: 'Easy', cls: 'sm', onclick: () => grade(5) }),
      ]));
    }
    card.appendChild(el('div', { class: 'sh-actions' }, [UI.button({ text: 'End the quiz', cls: 'sm quiet', onclick: () => { S.quiz = null; S.quizLayer = null; applyHighlights(); showCard(S.sel); } })]));
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
      items.forEach((it, i) => res.appendChild(el('button', { type: 'button', class: 'sh-search-item' + (i === at ? ' on' : ''), role: 'option', 'aria-selected': String(i === at),
        onmousedown: (e) => { e.preventDefault(); go(it); } }, [el('span', { class: 'k', text: it.kind }), el('b', { text: it.label }), el('small', { text: it.sub || '' })])));
    };
    const go = (it) => {
      items = []; paint(); input.value = ''; input.blur();
      const t = it.target;
      if (t.code) openView(t.code);
      else if (t.ride) startRide(t.ride);
      else if (t.event) playEvent(t.event);
      else if (t.tour) startTour(t.tour);
      else if (t.story) startStory(t.story);
      else if (t.view) openView((S.lab.views[t.view] || {}).state);
      else pick(t, 'search');
    };
    input.addEventListener('input', () => {
      const v = input.value.trim();
      const code = parseCode(v);
      if (code) { items = [{ label: 'Open the shared view', sub: 'From a copied code', kind: 'view', target: { code } }]; at = 0; paint(); return; }
      const idx = BARRY.shLearn.index(S.kb, { rides: (S.rides || {}).rides, events: BARRY.shPhys.EVENTS,
        tours: BARRY.shLearn.tours(S.kb, { probeAp: 7300 }), views: Object.entries(S.lab.views || {}).filter(([, x]) => x).map(([id, x]) => ({ id, name: x.name, by: x.by })),
        stories: ST().stories() });
      items = BARRY.shLearn.search(idx, v);
      at = 0;
      paint();
    });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { at = Math.min(items.length - 1, at + 1); paint(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { at = Math.max(0, at - 1); paint(); e.preventDefault(); }
      else if (e.key === 'Enter' && items[at]) go(items[at]);
      else if (e.key === 'Escape') { items = []; paint(); input.blur(); }
    });
    input.addEventListener('blur', () => setTimeout(() => { items = []; paint(); }, 150));
  }

  /* ==================================================================
     Share: views for the lab, figures, video
     ================================================================== */
  function shareMenu(anchor) {
    const canStage = S.mode !== 'schematic' && !!S.stage;
    const nViews = Object.values(S.lab.views || {}).filter(Boolean).length;
    UI.menu(anchor, [
      { title: 'For the lab', items: [
        { label: 'Save this view', sub: 'The mode, camera, cut, section, probe and selection, on every lab machine', icon: 'bookmark', on: () => showCard({ type: 'views', focus: true }) },
        { label: 'Saved views', sub: nViews ? nViews + ' saved by the lab' : 'None yet', icon: 'views', on: () => showCard({ type: 'views' }) },
      ] },
      { title: 'Files', items: [
        { label: 'Save a figure', sub: S.mode === 'schematic' ? 'The schematic as SVG, with the theme\'s colors written in' : 'The stage as a PNG at ' + (S.mode === '3d' ? 3 : 2) + '× resolution', icon: 'camera', on: saveFigure },
        { label: S.rec ? 'Stop recording' : 'Record a video', sub: S.rec ? 'Save what has been recorded so far' : canStage ? 'The stage at 1080p, captioned during rides and events' : 'Works on the 3D and slice views',
          icon: S.rec ? 'record' : 'video', disabled: !S.rec && !canStage, on: toggleRecord },
      ] },
    ], { where: 'below-end', width: 340 });
  }
  function syncShare() {
    const b = $('.sh-share-btn');
    if (!b) return;
    b.classList.toggle('sh-rec-on', !!S.rec);
    b.innerHTML = '';
    b.appendChild(UI.icon(S.rec ? 'record' : 'share'));
    b.appendChild(el('span', { text: S.rec ? 'Recording' : 'Share' }));
  }
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
    const s = $('.sh-schem-full svg') || $('.sh-map svg');
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
    else if (P && P.kind === 'event') { title = P.ev.label + ' (model)'; say = P.ev.say; clock = 't = ' + P.t.toFixed(1) + ' ms'; }
    if (!title) return;
    const pad = 40, boxH = 136;
    const g = ctx.createLinearGradient(0, h - boxH - 40, 0, h);
    g.addColorStop(0, 'rgba(6,9,12,0)'); g.addColorStop(0.35, 'rgba(6,9,12,0.62)'); g.addColorStop(1, 'rgba(6,9,12,0.8)');
    ctx.fillStyle = g;
    ctx.fillRect(0, h - boxH - 40, w, boxH + 40);
    ctx.fillStyle = '#fff';
    ctx.font = '650 30px ' + tok('--sans', 'sans-serif');
    ctx.fillText(title, pad, h - boxH + 44);
    ctx.font = '22px ' + tok('--sans', 'sans-serif');
    ctx.fillStyle = 'rgba(255,255,255,0.86)';
    const words = say.split(' ');
    let line = '', y = h - boxH + 84;
    for (const wd of words) {
      if (ctx.measureText(line + wd).width > w - pad * 2 - 240) { ctx.fillText(line, pad, y); line = ''; y += 29; if (y > h - 10) break; }
      line += wd + ' ';
    }
    if (y <= h - 10) ctx.fillText(line, pad, y);
    if (clock) { ctx.font = '600 26px ' + tok('--sans', 'sans-serif'); ctx.textAlign = 'right'; ctx.fillText(clock, w - pad, h - boxH + 44); ctx.textAlign = 'left'; }
  }
  function toggleRecord() { if (S.rec) stopRecord(); else startRecord(); }
  function startRecord(o) {
    if (!S.stage || S.mode === 'schematic') { toast('Recording works on the 3D and slice views.', 'warn'); return; }
    if (!window.MediaRecorder) { toast('This browser cannot record video.', 'err'); return; }
    S.rec = S.stage.record({ paint: captionPainter, width: 1920, height: 1080, fps: 30 });
    S.rec.untilDone = !!(o && o.untilDone);
    root.classList.add('sh-recording');
    syncShare();
    toast('Recording the stage at 1080p' + (S.rec.mime.includes('mp4') ? ' (MP4)' : ' (WebM)') + '.', 'ok');
    renderDock();
  }
  async function stopRecord() {
    if (!S.rec) return;
    const R = S.rec;
    S.rec = null;
    root.classList.remove('sh-recording');
    syncShare();
    const blob = await R.stop();
    const ext = R.mime.includes('mp4') ? 'mp4' : 'webm';
    const url = URL.createObjectURL(blob);
    download(url, 'seahorse-' + (S.play && S.play.key ? S.play.key : 'view') + '-' + stamp() + '.' + ext);
    setTimeout(() => URL.revokeObjectURL(url), 8000);
    toast('Saved the video (' + fmtMB(blob.size) + ', ' + ext.toUpperCase() + ').', 'ok');
    renderDock();
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
    const tg = (e.target && e.target.tagName) || '';
    if (/^(input|textarea|select)$/i.test(tg)) return;
    // "/" goes to the search box (Ctrl+K stays Jarvis's palette)
    if (e.key === '/' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); const i = $('.sh-search-box input'); if (i) i.focus(); return; }
    if (e.key === ' ' && /^(button|summary|a)$/i.test(tg)) return;     // space presses the focused control
    const P = S.play;
    if (e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); histGo(e.key === 'ArrowLeft' ? -1 : 1); return; }
    if (P && P.kind === 'ride' && S.stage) {
      if (e.key === ' ') { e.preventDefault(); const rs = S.stage.rideState; if (rs && rs.hold) S.stage.stepRide(1); else S.stage.pauseRide(); renderDock(); return; }
      if (e.key === 'ArrowRight') { S.stage.stepRide(1); return; }
      if (e.key === 'ArrowLeft') { S.stage.stepRide(-1); return; }
      if (e.key === 'f' || e.key === 'F') { S.stage.reframe(); renderDock(); return; }
    }
    if (P && P.kind === 'event' && e.key === ' ') { e.preventDefault(); toggleEventPause(); return; }
    if (P && P.kind === 'story') {
      // Space: pause and play a clip, or on to the next stop when this one waits for you
      if (e.key === ' ') { e.preventDefault(); if (P.held && (!P.stop.clip || P.paused)) storyNext(); else toggleStoryPause(); return; }
      if (e.key === 'ArrowRight') { e.preventDefault(); storyNext(); return; }
      if (e.key === 'ArrowLeft') { e.preventDefault(); storyGo(P.i - 1); return; }
    }
    if (P && P.kind === 'sextant') {
      if (e.key === 'ArrowRight' || (e.key === ' ' && !P.review)) { e.preventDefault(); sextNext(); return; }
      if (e.key === 'ArrowLeft') { e.preventDefault(); sextGo(P.i - 1); return; }
    }
    if (e.key === 'Escape') {
      if (UI.current()) return;
      if (S.tour) { endTour(); stopPlay(); }
      else if (S.play) stopPlay();
      else select(null);
    }
  }
  function themeChanged() {
    if (S.stage) { S.stage.theme(stageColors()); applyHighlights(); }
    S.schemShown = null;
    renderRail();
    if (S.mode === 'schematic') renderSchemFull();
  }

  async function onShow() {
    if (!S.built) build();
    if (!S.kb) {
      try {
        const [kb, checks, manifest, rides] = await Promise.all([getJSON('kb.json'), getJSON('checks.json'),
          getJSON('manifest.json').catch(() => null), getJSON('rides.json').catch(() => null)]);
        S.kb = kb; S.checks = checks; S.manifest = manifest; S.rides = rides;
      } catch (err) {
        $('.sh-stage').appendChild(el('div', { class: 'sh-empty', text: 'Seahorse\'s atlas files are missing (web/seahorse/). Build them with: python tools/seahorse/build.py' }));
        reportClientError('seahorse:kb', err.message, err.stack);
        return;
      }
      loadLab();
    }
    showCard(S.sel);
    renderDock();
    renderRail();
    renderNav();
    renderTools();
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
    UI.closeAll();
    if (S.stage) S.stage.pause();
    if (isRide() && S.stage) S.stage.pauseRide(true);
    stopEventAnim();
    stopStoryClock();
  }
  function onReturn() {
    if (S.stage && S.mode !== 'schematic') S.stage.resume();
    if (isEvent()) { showEventPanel(); startEventClock(); }
    if (isStory()) startStoryClock();
  }

  // _do: the tab's own verbs, for the screenshot harnesses (tools/ui_shots.py --steps)
  return { onShow, onHide, onReturn, _state: S,
           _do: { select, pick, showCard, setMode, setLevel, playEvent, startRide, stopPlay, startTour, startPath, openQuiz, startStory, storyGo, startSextant, sextGo, sextReview, sextDrag } };
})();
