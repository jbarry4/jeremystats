/* film.js -- "Watching a seizure spread": Seahorse's seizure story (KCNT1
   mouse 459) as a standalone video for an outside audience, directed frame by
   frame. Loaded into the Jarvis app after the Seahorse view is open, with
   vt.js (virtual time) in the page from the start. FILM.init(assets) builds
   the overlay; FILM.step() moves the film on by one frame; FILM.cues() says
   where the music changes mood and where each sound goes (soundtrack.py
   writes them). Colours are the KCNT1 poster's (v8): CA1 green, the granule
   cell blades pink, the hilus and its brake cells amber; CSD sinks blue. */
(() => {
'use strict';
if (window.FILM) return;
const SH = BARRY.views.seahorse, S = SH._state, R = BARRY.shStory, V = window.__vt;
const FPS = 30, DT = 1000 / FPS;
const VW = innerWidth, VH = innerHeight, DPR = devicePixelRatio || 1;
const F = window.FILM = { FPS, frame: 0, cur: null, log: [], assets: {}, after: null, waitStory: false };

/* ------------------------------------------------------------ helpers */
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const lerp = (a, b, u) => a + (b - a) * u;
const lerp3 = (a, b, u) => [0, 1, 2].map((i) => lerp(a[i], b[i], u));
const ease = (u) => { u = clamp(u, 0, 1); return u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2; };
const smooth = (u) => { u = clamp(u, 0, 1); return u * u * (3 - 2 * u); };
const fade = (t, a, b, fi, fo) => clamp(Math.min((t - a) / (fi || 0.5), (b - t) / (fo || 0.5)), 0, 1);
const norm = (v) => { const n = Math.hypot(...v) || 1; return v.map((x) => x / n); };
const add = (a, b, k) => a.map((x, i) => x + b[i] * (k == null ? 1 : k));
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const hex = (h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
const rgba = (c, a) => 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + (+a).toFixed(3) + ')';
const W3 = (ap, dv, ml) => S.three.W(ap, dv, ml);
const P = () => S.play;
const D = () => S.play.D;
const B = () => S.play.B;
const FONT = '"Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif';
const BG = [5, 8, 12];
const C = {
  text: '#f3f6f8', text2: '#b9c5cd', text3: '#7f8d97', ember: '#ffad5a', hot: '#ff7a2f',
  hyp: '#b9a2ff', next: '#6fb7ff', atlas: '#62d2c4', map: '#8fd3c8', text4: '#ffc58a',
  // the KCNT1 poster's plate (v8), as words on the dark: its fills, a touch lighter
  ca1: '#a9dc6e', up: '#f0868d', hil: '#f2c45a', low: '#f5b0c9', gc: '#f0868d', ca3: '#5cc6bd', sub: '#e2c27f', ec: '#86a8ea', neo: '#c9d2d9',
  brake: '#ffd27a',
};
/* the bars and the cells in the poster's own colours */
const BAR = { ca1: '#9fd062', up: '#e9807f', hil: '#f2c45a', low: '#f2a9c4' };

/* ------------------------------------------------------------ the atlas */
const lamOf = (k) => S.kb.lamina.find((l) => l.key === k);
const lamByCode = (c) => S.kb.lamina.find((l) => l.code === c);
const lamColor = (k) => S.kb.lamina_colors[k] || '#999999';
function lamAt(ap, dv, ml) {
  if (ml < 5700) ml = 11400 - ml;
  let lam = 0;
  const H = S.blobs['hip20.shb.gz'], Fb = S.blobs['fine10.shb.gz'];
  if (H) {
    const o = H.header.origin_um, s = H.header.arrays[0].shape;
    const i = Math.floor((ap - o[0]) / 20), j = Math.floor((dv - o[1]) / 20), k = Math.floor((ml - o[2]) / 20);
    if (i >= 0 && j >= 0 && k >= 0 && i < s[0] && j < s[1] && k < s[2]) lam = H.arrays.labels[(i * s[1] + j) * s[2] + k];
  }
  if (Fb) {
    const o = Fb.header.origin_um, s = Fb.header.shape;
    const i = Math.floor((ap - o[0]) / 10), j = Math.floor((dv - o[1]) / 10), k = Math.floor((ml - o[2]) / 10);
    if (i >= 0 && j >= 0 && k >= 0 && i < s[0] && j < s[1] && k < s[2]) lam = Fb.arrays.labels[(i * s[1] + j) * s[2] + k];
  }
  return lam;
}
/* the middle of some layers where a coronal plane crosses them (right side, CCF um);
   near: prefer the part nearest this [dv, ml] (a layer can show in two places) */
const planeMemo = new Map();
function planeCentre(keys, ap, near) {
  const id = keys.join(',') + '@' + ap + (near ? '~' + near.join(',') : '');
  if (planeMemo.has(id)) return planeMemo.get(id);
  const codes = new Set(keys.map((k) => (lamOf(k) || {}).code).filter(Boolean));
  const pts = [];
  for (let ml = 5760; ml < 10400; ml += 20) for (let dv = 600; dv < 5200; dv += 20) if (codes.has(lamAt(ap, dv, ml))) pts.push([dv, ml]);
  let use = pts;
  if (near && pts.length) {
    const d = pts.map((p) => Math.hypot(p[0] - near[0], p[1] - near[1]));
    const lim = Math.min(...d) + 450;
    use = pts.filter((p, i) => d[i] < lim);
  }
  let c = null;
  if (use.length) {
    const m = use.reduce((a, p) => [a[0] + p[0], a[1] + p[1]], [0, 0]).map((x) => x / use.length);
    // the sample nearest the middle that is inside the layer (a curved layer's middle is outside it)
    let best = use[0], bd = 1e18;
    for (const p of use) { const dd = (p[0] - m[0]) ** 2 + (p[1] - m[1]) ** 2; if (dd < bd) { bd = dd; best = p; } }
    c = [ap, best[0], best[1]];
  }
  planeMemo.set(id, c);
  return c;
}
/* where a layer crosses the vertical line at ml on the plane ap: the middle of its run nearest nearDv */
function layerMid(key, ap, ml, nearDv) {
  const code = (lamOf(key) || {}).code;
  if (!code) return null;
  let best = null, run = null;
  for (let dv = 300; dv <= 5700; dv += 5) {
    const on = lamAt(ap, dv, ml) === code;
    if (on) { if (run) run[1] = dv; else run = [dv, dv]; }
    if ((!on || dv === 5700) && run) { const m = (run[0] + run[1]) / 2; if (best == null || Math.abs(m - nearDv) < Math.abs(best - nearDv)) best = m; run = null; }
  }
  return best;
}
/* Allen structures' middles (CCF um) on each side, from the 50 um labels (as seahorse.js does) */
const ALLEN_IDS = { MS: 564, MOp: 985, SSp: 322, TH: 549, P: 771, MY: 354, MB: 313, AUD: 247, VISp: 385, RSP: 254, ACA: 31 };
let allenC = null;
const inStruct = (id) => { const st = S.blobs['brain50.shb.gz'].header.structures; return st.map((s) => (s.id === id || (s.path || []).includes(id) ? 1 : 0)); };
function allenCentres() {
  if (allenC) return allenC;
  const Bb = S.blobs['brain50.shb.gz'];
  const st = Bb.header.structures, names = Object.keys(ALLEN_IDS), ids = names.map((n) => ALLEN_IDS[n]);
  const slot = new Int16Array(st.length).fill(-1);
  st.forEach((s, i) => { const hit = ids.findIndex((id) => s.id === id || (s.path || []).includes(id)); if (hit >= 0) slot[i] = hit; });
  const acc = new Float64Array(ids.length * 8), L = Bb.arrays.labels;
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
    allenC[n] = { r: get(0), l: get(1) };
  });
  return allenC;
}
const allenW = (n, side) => { const c = (allenCentres()[n] || {})[side || 'r']; return c ? W3(c[0], c[1], c[2]) : null; };
/* the top surface of an Allen structure, both sides: the highest 50 um voxel of every other column, in world mm */
const topMemo = {};
function allenTop(name) {
  if (topMemo[name]) return topMemo[name];
  const L = S.blobs['brain50.shb.gz'].arrays.labels, inS = inStruct(ALLEN_IDS[name]), pts = [];
  for (let i = 0; i < 264; i++) for (let k = 0; k < 228; k++) {
    for (let j = 0; j < 160; j++) if (inS[L[(i * 160 + j) * 228 + k]]) { pts.push(W3(i * 50 + 25, j * 50 + 25, k * 50 + 25)); break; }
  }
  return (topMemo[name] = pts);
}
const hpfMemo = {};
const hpfW = (k, side) => { const c = hpfMemo[k] || (hpfMemo[k] = S.stage.centroid('hpf', k, true)); return c && side === 'l' ? [-c[0], c[1], c[2]] : c; };
const cellsH = () => S.blobs['cells.shb.gz'].header.cells;

/* ------------------------------------------------------------ the story's stops, and the film's own */
const story = R.stories()[0];
const STOPS = story.stops;
const idxOf = (key) => STOPS.findIndex((s) => s.key === key);
function addStop(st) {
  Object.assign(st, { title: st.title || 'Film', say: st.say || '', pic: st.pic || {} });
  let i = idxOf(st.key);
  if (i < 0) { STOPS.push(st); i = STOPS.length - 1; } else STOPS[i] = st;
  return i;
}
const STAGES = [[0.0, 1.0, 'Hilus'], [1.3, 2.3, 'Upper blade'], [2.6, 3.6, 'Lower blade'], [4.6, 5.6, 'CA1']];
let FS = null;
function makeStops() {
  FS = {
    brain: addStop({ key: 'film_brain', act: 'open', tag: 'model', view: 'brain', map: 'circuit' }),
    hpf: addStop({ key: 'film_hpf', act: 'open', tag: 'model', view: 'hpf', map: 'circuit' }),
    probe: addStop({ key: 'film_probe', act: 'open', tag: 'recorded', view: 'probe', map: 'dentate' }),
    dentate: addStop({ key: 'film_dentate', act: 'open', tag: 'recorded', view: 'dentate', map: 'dentate' }),
    spread: addStop({ key: 'film_spread', act: 'probe', tag: 'recorded', view: 'probe', map: 'dentate', clip: [-0.4, 6.1], speed: 0.2, measure: 'absx', unit: true, pic: { win: [-0.4, 6.1] } }),
    opto: idxOf('opto'),
  };
}
/* go to a stop. The section never glides (the film frames it itself), and the
   film waits for the stop to be set up before it moves on. */
function go(i) {
  S.slice.pos = -999;
  SH._do.storyGo(i);
  F.waitStory = true;
}

/* ------------------------------------------------------------ section and camera */
const AX = { N: [1, 0, 0], U: [0, 0, 1], V: [0, 1, 0] };
function setSlice(fr) {
  S.slice.C = fr.C.slice(); S.slice.k = fr.k;
  S.stage.setSlice({ N: AX.N, U: AX.U, V: AX.V, C: fr.C, k: fr.k });
}
/* the probe line at x = xf * width, depths dv0..dv1 between screen rows y0..y1 */
function framing(xf, y0, y1, dv0, dv1, ml) {
  const g = P().geo;
  const k = (dv1 - dv0) / (y1 - y0);
  return { C: [g.ap, (dv0 + dv1) / 2 + (VH / 2 - (y0 + y1) / 2) * k, (ml || g.ml) + (VW / 2 - xf * VW) * k], k };
}
const toPx = (ap, dv, ml) => S.stage.ccfToSlicePx([ap, dv, ml]);
function camAt(pos, target) { S.stage.setCam({ pos, target }, 0); }
/* a camera dir turned about the vertical */
function yaw(dir, deg) { const a = deg * Math.PI / 180, c = Math.cos(a), s = Math.sin(a); return [dir[0] * c + dir[2] * s, dir[1], -dir[0] * s + dir[2] * c]; }
function look(target, dir, dist, shiftRight, shiftUp) {
  const d = norm(dir), fwd = d.map((x) => -x), right = norm(cross(fwd, [0, 1, 0])), up = cross(right, fwd);
  const t = add(add(target, right, -(shiftRight || 0)), up, -(shiftUp || 0));
  camAt(add(t, d, dist), t);
}
const proj = (w) => S.stage.project(w);
/* a camera that holds each view and glides to the next: keys [[t, target, dir, dist]], each glide g s long, ending at its key */
function camKeys(t, keys, g) {
  let i = 0;
  while (i < keys.length - 1 && t >= keys[i + 1][0]) i++;
  const k = keys[i], nx = keys[i + 1];
  const drift = (tt) => (tt - k[0]) * 0.7;
  let tgt = k[1], dir = yaw(norm(k[2]), drift(t)), dist = k[3];
  if (nx && t > nx[0] - g) {
    const u = ease((t - (nx[0] - g)) / g);
    tgt = lerp3(tgt, nx[1], u); dir = norm(lerp3(dir, norm(nx[2]), u)); dist = Math.exp(lerp(Math.log(dist), Math.log(nx[3]), u));
  }
  look(tgt, dir, dist);
}

/* ------------------------------------------------------------ the overlay */
let root, cv, ctx, frz, fctx, el = {};
const CSS = `
#film { position: fixed; inset: 0; z-index: 2147480500; pointer-events: none; font-family: ${FONT}; color: ${C.text};
  -webkit-font-smoothing: antialiased; font-kerning: normal; }
#film * { box-sizing: border-box; }
#film canvas { position: absolute; inset: 0; width: 100%; height: 100%; }
#film-scrim { position: absolute; left: 0; right: 0; bottom: 0; height: 230px;
  background: linear-gradient(to top, rgba(4,6,9,0.93) 0%, rgba(4,6,9,0.72) 38%, rgba(4,6,9,0) 100%); }
#film-cap { position: absolute; left: 58px; bottom: 42px; width: 900px; }
#film-cap .main { font-size: 26px; font-weight: 600; line-height: 1.3; letter-spacing: -0.003em; text-wrap: balance;
  text-shadow: 0 1px 12px rgba(0,0,0,0.6); }
#film-cap .sub { margin-top: 7px; font-size: 15.5px; font-weight: 500; color: ${C.text2}; letter-spacing: 0.005em; }
#film-chap { position: absolute; left: 58px; top: 32px; display: flex; flex-direction: column; gap: 9px; }
#film-chap .t { font-size: 13px; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; color: #d9e2e8; }
#film-chap .t b { color: ${C.ember}; font-weight: 700; margin-right: 9px; }
#film-chap .dots { display: flex; gap: 5px; }
#film-chap .dots i { width: 16px; height: 3px; border-radius: 2px; background: rgba(255,255,255,0.16); }
#film-chap .dots i.on { background: ${C.ember}; }
#film-chap .dots i.done { background: rgba(255,173,90,0.45); }
#film-tag { position: absolute; right: 54px; top: 28px; display: flex; align-items: center; gap: 9px; padding: 7px 14px 7px 12px;
  border-radius: 999px; background: rgba(12,17,23,0.72); border: 1px solid rgba(255,255,255,0.13);
  font-size: 13px; font-weight: 650; letter-spacing: 0.04em; color: #e6edf1; }
#film-tag i { width: 9px; height: 9px; border-radius: 50%; background: var(--tc); box-shadow: 0 0 10px var(--tc); }
#film-tag small { font-size: 12px; font-weight: 500; color: ${C.text2}; letter-spacing: 0.02em; }
#film-title { position: absolute; left: 84px; top: 50%; width: 560px; transform: translateY(-50%); }
#film-title .kick { font-size: 14px; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase; color: ${C.ember}; }
#film-title h1 { margin: 14px 0 0; font-size: 58px; line-height: 1.04; font-weight: 700; letter-spacing: -0.02em; }
#film-title p { margin: 18px 0 0; font-size: 21px; line-height: 1.4; color: ${C.text2}; font-weight: 500; }
#film-title .by { margin-top: 38px; display: flex; align-items: center; gap: 16px; font-size: 14.5px; color: ${C.text2}; font-weight: 500; line-height: 1.45; }
#film-title .by img { height: 54px; }
#film-model { position: absolute; left: 0; top: 0; bottom: 0; width: 760px; padding: 118px 0 0 58px;
  background: linear-gradient(to right, rgba(5,8,12,0.94) 0%, rgba(5,8,12,0.86) 62%, rgba(5,8,12,0) 100%); }
#film-model .kick { font-size: 13px; font-weight: 700; letter-spacing: 0.16em; text-transform: uppercase; color: ${C.ember}; }
#film-model h2 { margin: 10px 0 26px; font-size: 40px; font-weight: 700; letter-spacing: -0.015em; }
#film-model ol { list-style: none; margin: 0; padding: 0; width: 600px; }
#film-model li { display: grid; grid-template-columns: 38px 1fr; margin: 0 0 20px; }
#film-model li .n { width: 26px; height: 26px; border-radius: 50%; border: 1.5px solid rgba(255,173,90,0.7); color: ${C.ember};
  font-size: 13px; font-weight: 700; display: grid; place-items: center; margin-top: 2px; }
#film-model li b { display: block; font-size: 22px; font-weight: 600; line-height: 1.3; text-wrap: balance; }
#film-model li small { display: block; margin-top: 4px; font-size: 14.5px; color: ${C.text2}; font-weight: 500; }
#film-card { position: absolute; inset: 0; display: grid; place-items: center; text-align: center; background: rgba(5,8,12,0.86); }
#film-card .kick { font-size: 14px; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase; color: ${C.ember}; }
#film-card h2 { margin: 12px 0 10px; font-size: 52px; font-weight: 700; letter-spacing: -0.02em; }
#film-card p { margin: 0; font-size: 19px; color: ${C.text2}; font-weight: 500; }
#film-end { position: absolute; inset: 0; background: radial-gradient(120% 120% at 78% 40%, #2a1650 0%, #140c26 42%, #06070c 100%); }
#film-end .l { position: absolute; left: 76px; top: 112px; width: 610px; }
#film-end .kick { font-size: 14px; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase; color: #7fd6cf; }
#film-end h2 { margin: 12px 0 0; font-size: 64px; line-height: 1.0; font-weight: 750; letter-spacing: -0.025em; }
#film-end .at { margin-top: 18px; font-size: 22px; line-height: 1.35; font-weight: 600; }
#film-end .when { margin-top: 18px; font-size: 18px; line-height: 1.55; color: #d9cdf5; font-weight: 500; }
#film-end .when b { color: #fff; font-weight: 650; }
#film-end .lab { margin-top: 34px; display: flex; align-items: center; gap: 16px; font-size: 15px; color: ${C.text2}; line-height: 1.45; font-weight: 500; }
#film-end .lab img { height: 62px; }
#film-end .art { position: absolute; right: 78px; top: 112px; width: 408px; height: 408px; border-radius: 18px; overflow: hidden;
  box-shadow: 0 30px 80px -20px rgba(0,0,0,0.8), 0 0 0 1px rgba(255,255,255,0.08); }
#film-end .art img { width: 100%; height: 100%; display: block; }
#film-end .cred { position: absolute; left: 76px; right: 76px; bottom: 30px; font-size: 11.5px; line-height: 1.5; color: #8d86a6; font-weight: 500; }
#film-black { position: absolute; inset: 0; background: #000; opacity: 0; }
`;
function build(assets) {
  F.assets = assets || {};
  const st = document.createElement('style'); st.textContent = CSS + `
    .sh-story-over, .sh-labels, .sh-story-words, .sh-seltag, .sh-load, .sh-loading, #toasts, .toasts, .toast-wrap { display: none !important; }`;
  document.head.appendChild(st);
  root = document.createElement('div'); root.id = 'film';
  const A = F.assets;
  root.innerHTML = `
    <canvas id="film-cv"></canvas>
    <canvas id="film-frz"></canvas>
    <div id="film-scrim"></div>
    <div id="film-cap"><div class="main"></div><div class="sub"></div></div>
    <div id="film-title">
      <div class="kick">A KCNT1 seizure, recorded</div>
      <h1>Watching a seizure spread</h1>
      <p>Inside the hippocampus of a mouse with a KCNT1 variant</p>
      <div class="by">${A.lab ? '<img src="' + A.lab + '">' : ''}<span>Epilepsy Cognition Development Lab<br>University of Vermont</span></div>
    </div>
    <div id="film-model">
      <h2>Mice with a KCNT1 variant</h2>
      <ol>
        <li><span class="n">1</span><span><b>They carry a change found in people with KCNT1 epilepsy.</b><small>Kcnt1 Y777H in mice; KCNT1 Y796H in people</small></span></li>
        <li><span class="n">2</span><span><b>It makes a potassium channel overactive.</b><small>The sodium-activated K<sup>+</sup> channel K<sub>Na</sub>1.1, or Slack</small></span></li>
        <li><span class="n">3</span><span><b>That quiets inhibitory neurons, the brain's brakes.</b></span></li>
        <li><span class="n">4</span><span><b>Mice with two copies have frequent seizures, many of them in sleep.</b><small>Shore et al., Cell Reports 2020</small></span></li>
      </ol>
    </div>
    <div id="film-chap"><div class="t"></div><div class="dots"></div></div>
    <div id="film-tag"><i></i><span></span></div>
    <div id="film-card"><div><div class="kick">Mouse 459</div><h2>One seizure, recorded</h2><p>Kcnt1 Y777H, two copies · awake · December 6, 2024</p></div></div>
    <div id="film-end">
      <div class="l">
        <div class="kick">See you in Denver</div>
        <h2>Come chat<br>with us</h2>
        <div class="at">at the 2026 KCNT1 Family &amp; Professional Conference</div>
        <div class="when"><b>December 3–4, 2026</b> · Grand Hyatt Denver<br>Scientific Roundtable Dec 3 · Family Conference Dec 4</div>
        <div class="lab">${A.lab ? '<img src="' + A.lab + '">' : ''}<span>Epilepsy Cognition Development Lab<br>Larner College of Medicine, University of Vermont</span></div>
      </div>
      <div class="art">${A.art ? '<img src="' + A.art + '">' : ''}</div>
      <div class="cred">Recording: Kcnt1 Y777H mouse 459 (two copies), awake, 64-contact silicon probe through CA1 and the dentate gyrus. Beyond the probe: drawn, not recorded (the loop is our hypothesis; the spread across the brain is the textbook).
        Anatomy: Allen Mouse Brain Common Coordinate Framework (CCFv3). Neuron tracings: Janelia MouseLight and NeuroMorpho.Org. Colors as on our KCNT1 poster. Made with Seahorse.</div>
    </div>
    <div id="film-black"></div>`;
  document.body.appendChild(root);
  cv = root.querySelector('#film-cv'); frz = root.querySelector('#film-frz');
  [cv, frz].forEach((c) => { c.width = Math.round(VW * DPR); c.height = Math.round(VH * DPR); });
  ctx = cv.getContext('2d'); fctx = frz.getContext('2d');
  ['scrim', 'chap', 'tag', 'cap', 'title', 'model', 'card', 'end', 'black'].forEach((k) => { el[k] = root.querySelector('#film-' + k); });
  el.capMain = el.cap.querySelector('.main'); el.capSub = el.cap.querySelector('.sub');
  el.chapT = el.chap.querySelector('.t'); el.dots = el.chap.querySelector('.dots');
  el.tagText = el.tag.querySelector('span');
  el.modelItems = Array.from(el.model.querySelectorAll('li'));
  for (let i = 0; i < CHAPTERS.length; i++) el.dots.appendChild(document.createElement('i'));
  frz.style.opacity = 0;
  ['chap', 'tag', 'cap', 'title', 'model', 'card', 'end', 'black'].forEach((k) => show(el[k], 0));
}
const show = (node, a, dy) => {
  const v = +a.toFixed(3);
  if (node._a !== v) { node.style.opacity = v; node.style.visibility = v > 0.001 ? 'visible' : 'hidden'; node._a = v; }
  if (dy != null) { const tr = 'translateY(' + (dy * (1 - a)).toFixed(2) + 'px)'; if (node._tr !== tr) { node.style.transform = tr; node._tr = tr; } }
};
const setText = (node, s) => { if (node._s !== s) { node.innerHTML = s; node._s = s; } };

/* ------------------------------------------------------------ chapters, tags, captions */
const CHAPTERS = ['The brain', 'The hippocampus', 'The model', 'How we listen', 'Cells and layers', 'A seizure, recorded', 'How it spreads',
  'Around the loop', 'Across the brain', "What's next"];
const TAGS = {
  atlas: [C.atlas, 'From the atlas', 'Allen mouse brain'],
  cells: [C.atlas, 'Real traced neurons', 'placed in their layers'],
  model: [C.ember, 'Kcnt1 Y777H mice', ''],
  rec: [C.ember, 'Recorded', 'mouse 459'],
  probe: [C.ember, 'Mouse 459', 'the probe’s path, on the atlas'],
  map: [C.map, 'The circuit', 'as anatomy books draw it'],
  hyp: [C.hyp, 'Our hypothesis', 'drawn, not recorded'],
  book: [C.hyp, 'How seizures spread', 'the textbook, not recorded here'],
  next: [C.next, 'Next experiment', ''],
};
let TAGLINE = [];
function hud(sc, lt) {
  // the chapter, its dots
  const ch = sc.chap || 0, ca = sc.chap ? fade(F.t, sc.chapIn, sc.chapOut, 0.6, 0.6) : 0;
  if (ch) {
    setText(el.chapT, '<b>' + ch + '</b>' + CHAPTERS[ch - 1]);
    Array.from(el.dots.children).forEach((d, i) => { const c = i + 1 === ch ? 'on' : i + 1 < ch ? 'done' : ''; if (d.className !== c) d.className = c; });
  }
  show(el.chap, ca);
  // what kind of thing the viewer is looking at (a tag can change inside a scene; it stays up across scenes that share it)
  const seg = TAGLINE.find((s) => F.t >= s[0] - 1e-6 && F.t < s[1] - 1e-6);
  const tg = seg && TAGS[seg[2]];
  if (tg) {
    setText(el.tagText, tg[1] + (tg[2] ? ' <small>· ' + tg[2] + '</small>' : ''));
    if (el.tag._c !== tg[0]) { el.tag.style.setProperty('--tc', tg[0]); el.tag._c = tg[0]; }
  }
  show(el.tag, tg ? fade(F.t, seg[0] + 0.2, seg[1] - 0.2, 0.5, 0.5) : 0);
  // the caption
  let cap = null;
  for (const c of sc.cap || []) if (lt >= c[0] - 0.01 && lt <= c[1] + 0.01) { cap = c; break; }
  if (cap) { setText(el.capMain, cap[2]); setText(el.capSub, cap[3] || ''); }
  show(el.cap, cap ? fade(lt, cap[0], cap[1], 0.45, 0.4) : 0, 10);
  show(el.scrim, sc.scrim == null ? 1 : sc.scrim);
}

/* ------------------------------------------------------------ drawing on the overlay */
function text(c, s, x, y, o) {
  o = o || {};
  c.font = (o.w || 600) + ' ' + (o.size || 15) + 'px ' + FONT;
  c.textAlign = o.align || 'left'; c.textBaseline = o.base || 'middle';
  if (o.halo !== false) { c.lineWidth = o.haloW || 4; c.lineJoin = 'round'; c.strokeStyle = o.halo || 'rgba(3,5,8,0.85)'; c.strokeText(s, x, y); }
  c.fillStyle = o.color || C.text; c.fillText(s, x, y);
  return c.measureText(s).width;
}
/* a label on a point: a dot, a short leader and the words */
function pin(c, x, y, s, o) {
  o = o || {};
  const a = o.alpha == null ? 1 : o.alpha;
  if (a <= 0.001) return;
  c.save(); c.globalAlpha = a;
  const col = o.color || C.text, dx = o.dx == null ? 0 : o.dx, dy = o.dy == null ? -26 : o.dy;
  c.fillStyle = col; c.strokeStyle = 'rgba(3,5,8,0.8)'; c.lineWidth = 3;
  c.beginPath(); c.arc(x, y, o.r || 4, 0, Math.PI * 2); c.stroke(); c.fill();
  c.strokeStyle = rgba(hex(col.length === 7 ? col : '#ffffff'), 0.75); c.lineWidth = 1.4;
  c.beginPath(); c.moveTo(x, y); c.lineTo(x + dx * 0.86, y + dy * 0.72); c.stroke();
  text(c, s, x + dx, y + dy - (dy < 0 ? 4 : -6), { size: o.size || 17, w: o.w || 650, align: o.align || (dx > 4 ? 'left' : dx < -4 ? 'right' : 'center'), base: dy < 0 ? 'alphabetic' : 'top', color: o.tcolor || col });
  if (o.sub) text(c, o.sub, x + dx, y + dy + (dy < 0 ? 15 : 26), { size: 13, w: 500, align: o.align || (dx > 4 ? 'left' : dx < -4 ? 'right' : 'center'), base: dy < 0 ? 'alphabetic' : 'top', color: C.text2 });
  c.restore();
}
function pin3(c, w, s, o) {
  if (!w) return;
  const p = proj(w);
  if (p[2] > 1 || p[0] < -50 || p[0] > VW + 50 || p[1] < -50 || p[1] > VH + 50) return;
  pin(c, p[0], p[1], s, o);
}
function rrect(c, x, y, w, h, r) { c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r); c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath(); }
function panel(c, x, y, w, h, a) {
  c.save(); c.globalAlpha = a;
  rrect(c, x, y, w, h, 14); c.fillStyle = 'rgba(10,14,20,0.82)'; c.fill();
  c.strokeStyle = 'rgba(255,255,255,0.1)'; c.lineWidth = 1; c.stroke();
  c.restore();
}
/* a soft light: a sprite drawn once, stamped with 'lighter' */
let glowSpr = null;
function glowSprite() {
  if (glowSpr) return glowSpr;
  glowSpr = document.createElement('canvas'); glowSpr.width = glowSpr.height = 64;
  const g = glowSpr.getContext('2d'), gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.35, 'rgba(255,255,255,0.45)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
  return glowSpr;
}
const tintMemo = {};
function tinted(col) {
  if (tintMemo[col]) return tintMemo[col];
  const s = glowSprite(), t = document.createElement('canvas'); t.width = t.height = 64;
  const g = t.getContext('2d'); g.drawImage(s, 0, 0); g.globalCompositeOperation = 'source-in'; g.fillStyle = col; g.fillRect(0, 0, 64, 64);
  return (tintMemo[col] = t);
}

/* the probe's zones in four groups: the four stages of the spread */
const GROUPS = [
  { key: 'ca1', name: 'CA1', zones: ['ca1o', 'ca1r'], lam: 'ca1sp', stage: 3 },
  { key: 'up', name: 'Upper blade', zones: ['supd', 'supp', 'supg'], lam: 'gcl1', stage: 1 },
  { key: 'hil', name: 'Hilus', zones: ['hil'], lam: 'hil', stage: 0 },
  { key: 'low', name: 'Lower blade', zones: ['infg', 'infp', 'infd'], lam: 'gcl2', stage: 2 },
];
const groupDv = (g) => { const z = P().geo.zones; return [Math.min(...g.zones.map((k) => z[k].dv0)), Math.max(...g.zones.map((k) => z[k].dv1))]; };
const groupLevel = (g) => Math.max(...g.zones.map((k) => P().levels[k] || 0));
const groupColor = (g) => BAR[g.key];
const groupWord = (g) => C[g.key];
/* the probe on the section: the shank, its 64 sites, the groups beside it, their names */
function drawShank(c, o) {
  const g = P().geo;
  const a = o.alpha == null ? 1 : o.alpha;
  if (a <= 0.001) return;
  const top = toPx(g.ap, g.top - 330, g.ml), tip = toPx(g.ap, g.bottom + 170, g.ml);
  const x = top[0];
  c.save(); c.globalAlpha = a;
  // the shank, haloed
  c.lineCap = 'round';
  c.strokeStyle = 'rgba(3,5,8,0.7)'; c.lineWidth = 7; c.beginPath(); c.moveTo(x, top[1]); c.lineTo(x, tip[1] - 8); c.stroke();
  c.strokeStyle = 'rgba(226,232,238,0.95)'; c.lineWidth = 3; c.beginPath(); c.moveTo(x, top[1]); c.lineTo(x, tip[1] - 8); c.stroke();
  c.fillStyle = 'rgba(226,232,238,0.95)'; c.beginPath(); c.moveTo(x - 4, tip[1] - 10); c.lineTo(x, tip[1] + 2); c.lineTo(x + 4, tip[1] - 10); c.closePath(); c.fill();
  // its 64 sites, from CA1 to the lower blade
  const y0 = toPx(g.ap, g.top, g.ml)[1], y1 = toPx(g.ap, g.bottom, g.ml)[1];
  c.fillStyle = '#f2c14e';
  for (let i = 0; i < 64; i++) { const y = lerp(y0, y1, i / 63); c.fillRect(x - 1.6, y - 0.8, 3.2, 1.6); }
  // the groups: a bar each in the poster's colour, lit by how far the recording is from its quiet self
  const bx = x + 9;
  GROUPS.forEach((gr) => {
    const [d0, d1] = groupDv(gr), ya = toPx(g.ap, d0, g.ml)[1] + 1, yb = toPx(g.ap, d1, g.ml)[1] - 1;
    const lv = o.levels ? groupLevel(gr) : 0;
    const lit = o.lit ? o.lit.has(gr.key) : true;
    const col = lv > 0.03 ? 'rgb(' + R.ramp(lv).join(',') + ')' : groupColor(gr);
    c.globalAlpha = a * (lit ? 1 : 0.35);
    if (lv > 0.03) { c.shadowColor = col; c.shadowBlur = 6 + 14 * lv; }
    c.fillStyle = col; c.fillRect(bx, ya, 5, Math.max(2, yb - ya));
    c.shadowBlur = 0;
    gr._y = [ya, yb];
  });
  c.globalAlpha = a;
  // names, never overlapping
  if (o.names !== false) {
    const ys = GROUPS.map((gr) => (gr._y[0] + gr._y[1]) / 2);
    for (let i = 1; i < ys.length; i++) ys[i] = Math.max(ys[i], ys[i - 1] + 24);
    GROUPS.forEach((gr, i) => {
      const lit = o.lit ? o.lit.has(gr.key) : true, lv = o.levels ? groupLevel(gr) : 0;
      const foc = o.focus ? o.focus.has(gr.key) : null;
      const mid = (gr._y[0] + gr._y[1]) / 2, lx = bx + 30;
      c.globalAlpha = a * (lit ? 1 : 0.45) * (foc === false ? 0.6 : 1);
      c.strokeStyle = 'rgba(220,228,235,0.45)'; c.lineWidth = 1;
      c.beginPath(); c.moveTo(bx + 8, mid); c.bezierCurveTo(bx + 18, mid, lx - 12, ys[i], lx - 4, ys[i]); c.stroke();
      const nm = (o.dgNames && gr.key !== 'ca1' && gr.key !== 'hil') ? 'Dentate gyrus, ' + gr.name.toLowerCase() : gr.name;
      let col = groupWord(gr), wt = 650;
      if (foc) { col = '#ffe2b8'; wt = 750; }
      else if (foc === null && lv > 0.25) { col = 'rgb(' + R.ramp(Math.max(0.55, lv)).join(',') + ')'; wt = 750; }
      const tw = text(c, nm, lx, ys[i], { size: o.size || 16.5, w: wt, color: col });
      if (foc) { c.fillStyle = C.ember; c.beginPath(); c.arc(lx + tw + 12, ys[i], 4, 0, Math.PI * 2); c.fill(); }
    });
  }
  c.restore();
  return { x, y0, y1, top, tip };
}
/* the hilar interneuron on the probe: an amber dot that swells with its firing */
function drawUnit(c, a) {
  const g = P().geo, p = P();
  if (g.unitDv == null || a <= 0.001) return;
  const u = toPx(g.ap, g.unitDv, g.ml);
  const hz = R.unitRate(p.D, p.t), k = Math.min(1, hz / 60);
  c.save(); c.globalAlpha = a;
  const x = u[0] - 22, y = u[1], col = hex(C.hil);
  c.fillStyle = rgba(col, 0.12 + 0.45 * k); c.beginPath(); c.arc(x, y, 7 + 16 * k, 0, Math.PI * 2); c.fill();
  c.fillStyle = rgba(col, 0.55 + 0.45 * Math.min(1, hz / 8)); c.beginPath(); c.arc(x, y, 4.5 + 3 * k, 0, Math.PI * 2); c.fill();
  c.strokeStyle = 'rgba(255,255,255,0.8)'; c.lineWidth = 1.3; c.stroke();
  text(c, 'brake cell', x - 14 - 16 * k, y, { size: 14.5, w: 650, align: 'right', color: C.brake });
  c.restore();
}

/* ------------------------------------------------------------ the recording, drawn */
let LUT = null;
function lut() { if (!LUT) LUT = R.csdLut(true, BG); return LUT; }
/* the CSD of [t0, t1] as cols x 58 pixels (a column keeps its strongest sample) */
function csdImg(t0, t1, cols) {
  const Bp = B(), H = Bp.header.csd, A = Bp.arrays.csd, rows = H.csc.length, n = A.length / rows, fs = H.fs, T0 = Bp.header.t0, vmax = H.vmax, L = lut();
  const img = new ImageData(cols, rows), px = img.data, spc = (t1 - t0) * fs / cols;
  for (let cI = 0; cI < cols; cI++) {
    const ta = (t0 - T0) * fs + cI * spc, tb = ta + spc, mid = (ta + tb) / 2;
    for (let r = 0; r < rows; r++) {
      const base = r * n;
      let v = 0;
      if (mid >= 0 && mid <= n - 1) {
        if (spc <= 1.5) { const i = Math.min(n - 2, Math.floor(mid)), f = mid - i; v = A[base + i] * (1 - f) + A[base + i + 1] * f; }
        else { const ia = Math.max(0, Math.floor(ta)), ib = Math.min(n - 1, Math.ceil(tb)); for (let i = ia; i <= ib; i++) { const s = A[base + i]; if (Math.abs(s) > Math.abs(v)) v = s; } }
      }
      const k = Math.max(0, Math.min(512, Math.round((v / vmax + 1) * 256))) * 3, o = (r * cols + cI) * 4;
      px[o] = L[k]; px[o + 1] = L[k + 1]; px[o + 2] = L[k + 2]; px[o + 3] = 255;
    }
  }
  const c = document.createElement('canvas'); c.width = cols; c.height = rows;
  c.getContext('2d').putImageData(img, 0, 0);
  return c;
}
/* a picture of [t0, t1]: the CSD under the potentials, w x h CSS px, in device pixels */
function recordingPicture(t0, t1, w, h, o) {
  o = o || {};
  const Bp = B(), c = document.createElement('canvas');
  c.width = Math.round(w * DPR); c.height = Math.round(h * DPR);
  const x = c.getContext('2d');
  x.setTransform(DPR, 0, 0, DPR, 0, 0);
  x.imageSmoothingEnabled = true; x.imageSmoothingQuality = 'high';
  x.drawImage(csdImg(t0, t1, Math.round(w * DPR)), 0, 0, w, h);
  const rows = Bp.header.csd.csc.length, rowH = h / rows, c0 = Bp.header.csd.csc[0];
  // the zones' borders, faint
  x.strokeStyle = 'rgba(255,255,255,0.13)'; x.setLineDash([3, 4]); x.lineWidth = 1;
  D().zones.forEach((z, i) => { if (!i) return; const y = Math.round((Math.max(c0, z.csc[0]) - c0) * rowH) + 0.5; x.beginPath(); x.moveTo(0, y); x.lineTo(w, y); x.stroke(); });
  x.setLineDash([]);
  // the potentials: every (o.every)th of figure A's traces; the gap spans o.span contacts; clipped to its lane
  const H = Bp.header.lfp, A = Bp.arrays.lfp, nt = H.csc.length, n = A.length / nt, fs = H.fs, T0 = Bp.header.t0;
  const every = o.every || 1, span = o.span || 4;
  const k = span * rowH / H.gap_uv / (o.gainDiv || 1), lim = o.clipPx ? o.clipPx / k : 1.3 * H.gap_uv;
  const sm = o.smooth || 1;
  const i0 = Math.max(0, Math.floor((t0 - T0) * fs)), i1 = Math.min(n - 1, Math.ceil((t1 - T0) * fs));
  const cols = Math.round(w * DPR), per = (i1 - i0) / cols;
  x.strokeStyle = o.trace || 'rgba(240,244,248,0.62)'; x.lineWidth = o.lw || 0.9; x.lineJoin = 'round';
  for (let j = (o.first || 0); j < nt; j += every) {
    const yb = (H.csc[j] - c0 + 0.5) * rowH;
    let src = A, base = j * n;
    if (sm > 1) {
      // a running mean over sm samples: the slow potential, without the fast fuzz
      const out = new Float32Array(n), hw = sm >> 1;
      let acc = 0;
      for (let i = 0; i < Math.min(n, hw + 1); i++) acc += A[base + i];
      for (let i = 0; i < n; i++) {
        const lo = i - hw, hi = i + hw;
        out[i] = acc / (Math.min(n - 1, hi) - Math.max(0, lo) + 1);
        if (hi + 1 < n) acc += A[base + hi + 1];
        if (lo >= 0) acc -= A[base + lo];
      }
      src = out; base = 0;
    }
    const Y = (v) => yb - (v > lim ? lim : v < -lim ? -lim : v) * k;
    x.beginPath();
    if (per <= 1.2) {
      for (let i = i0; i <= i1; i++) { const xx = ((T0 + i / fs) - t0) / (t1 - t0) * w; if (i === i0) x.moveTo(xx, Y(src[base + i])); else x.lineTo(xx, Y(src[base + i])); }
    } else {
      for (let cI = 0; cI < cols; cI++) {
        const a = i0 + Math.floor(cI * per), b = Math.min(i1, i0 + Math.floor((cI + 1) * per));
        let lo = 32767, hi = -32768;
        for (let i = a; i <= b; i++) { const v = src[base + i]; if (v < lo) lo = v; if (v > hi) hi = v; }
        const xx = (cI + 0.5) / DPR;
        if (cI === 0) x.moveTo(xx, Y(hi)); else x.lineTo(xx, Y(hi));
        x.lineTo(xx, Y(lo));
      }
    }
    x.stroke();
  }
  return c;
}
/* the probe's groups beside a picture of the recording: a bracket and a name each */
function groupBrackets(c, x, y0, h, o) {
  o = o || {};
  const Bp = B(), rows = Bp.header.csd.csc.length, rowH = h / rows, c0 = Bp.header.csd.csc[0], c1 = Bp.header.csd.csc[rows - 1];
  const zs = Object.fromEntries(D().zones.map((z) => [z.key, z]));
  GROUPS.forEach((gr) => {
    const a = Math.max(c0, Math.min(...gr.zones.map((k) => zs[k].csc[0]))), b = Math.min(c1, Math.max(...gr.zones.map((k) => zs[k].csc[1])));
    const ya = y0 + (a - c0) * rowH + 2, yb = y0 + (b - c0 + 1) * rowH - 2;
    const lit = o.lit ? o.lit(gr) : 0;
    const col = lit > 0.02 ? 'rgb(' + R.ramp(0.45 + 0.5 * lit).join(',') + ')' : groupColor(gr);
    c.save();
    c.globalAlpha = (o.alpha == null ? 1 : o.alpha) * (o.dim && o.dim(gr) ? 0.4 : 1);
    c.fillStyle = col; c.fillRect(x - 7, ya, 4, yb - ya);
    text(c, gr.name, x - 15, (ya + yb) / 2, { size: o.size || 15, w: lit > 0.02 ? 750 : 650, align: 'right', color: lit > 0.02 ? col : groupWord(gr) });
    c.restore();
  });
}
function timeAxis(c, x0, x1, y, t0, t1, step, o) {
  o = o || {};
  c.save();
  c.fillStyle = C.text3; c.strokeStyle = C.text3;
  for (let t = Math.ceil(t0 / step) * step; t <= t1 + 1e-9; t += step) {
    const x = x0 + (t - t0) / (t1 - t0) * (x1 - x0);
    if (o.upto != null && t > o.upto + 1e-6) continue;
    c.fillRect(Math.round(x), y, 1, 5);
    const s = (Math.abs(t) < 1e-9 ? '0' : (t < 0 ? '−' : '') + Math.abs(+t.toFixed(2))) + ' s';
    text(c, s, x, y + 15, { size: o.size || 13, w: 500, align: 'center', color: C.text2, halo: false });
  }
  c.restore();
}
/* a bracket over [xa, xb] at y, with words above it */
function bracket(c, xa, xb, y, s, col, a) {
  if (a <= 0.001) return;
  c.save(); c.globalAlpha = a;
  c.strokeStyle = col; c.lineWidth = 2;
  c.beginPath(); c.moveTo(xa + 1, y + 7); c.lineTo(xa + 1, y); c.lineTo(xb - 1, y); c.lineTo(xb - 1, y + 7); c.stroke();
  if (s) text(c, s, (xa + xb) / 2, y - 13, { size: 15, w: 700, align: 'center', color: col, halo: false });
  c.restore();
}

/* ------------------------------------------------------------ real neurons, drawn on the section */
const shapeMemo = {};
function cellShape(key) {
  if (shapeMemo[key]) return shapeMemo[key];
  const Bc = S.blobs['cells.shb.gz'], info = cellsH().find((c) => c.key === key);
  if (!info) return null;
  const p = Bc.arrays['p:' + key], ty = Bc.arrays['t:' + key], par = Bc.arrays['a:' + key], rad = Bc.arrays['r:' + key], n = ty.length;
  // path length from the soma to every point (parents may come after their children: walk from the roots)
  const kids = Array.from({ length: n }, () => []), d = new Float32Array(n).fill(-1), q = [];
  for (let i = 0; i < n; i++) { const j = par[i]; if (j >= 0 && j < n) kids[j].push(i); else { d[i] = 0; q.push(i); } }
  for (let h = 0; h < q.length; h++) {
    const i = q[h];
    for (const k of kids[i]) { d[k] = d[i] + Math.hypot(p[k * 3] - p[i * 3], p[k * 3 + 1] - p[i * 3 + 1], p[k * 3 + 2] - p[i * 3 + 2]); q.push(k); }
  }
  // the soma: the first soma point (else the root)
  let s0 = q[0];
  for (let i = 0; i < n; i++) if (ty[i] === 1) { s0 = i; break; }
  const soma = [p[s0 * 3], p[s0 * 3 + 1], p[s0 * 3 + 2]];
  // which way its dendrites run in the coronal plane (the apical tree if it has one), which way its axon runs,
  // and how far its arbors reach along their paths
  const hasApical = Array.prototype.some.call(ty, (x) => x === 4);
  let vd = [0, 0], va = [0, 0], dMax = 1, aMax = 1;
  for (let i = 0; i < n; i++) {
    const dv = p[i * 3 + 1] - soma[1], ml = p[i * 3 + 2] - soma[2];
    if (ty[i] === 4 || (!hasApical && ty[i] === 3)) { vd[0] += dv; vd[1] += ml; }
    if (ty[i] === 3 || ty[i] === 4) dMax = Math.max(dMax, d[i]);
    else if (ty[i] === 2) { va[0] += dv; va[1] += ml; aMax = Math.max(aMax, d[i]); }
  }
  return (shapeMemo[key] = { key, info, p, ty, par, rad, n, d, soma, dendDir: Math.atan2(vd[1], vd[0]), axonDir: Math.atan2(va[1], va[0]), dMax, aMax });
}
/* the turn (radians, in the (dv, ml) plane) that points a cell's dendrites (or axon) along [dv, ml] */
const turnTo = (from, want) => Math.atan2(want[1], want[0]) - from;
/* one neuron, its soma moved to (dvT, mlT) on the section through the probe and turned by rot in that plane;
   grown out along its own paths: dendrites to reveal, axon to revealA (um of path); o.keepA: which axon points to draw */
function drawNeuron(c, sh, dvT, mlT, rot, col, o) {
  o = o || {};
  const g = P().geo, ap = g.ap, a = o.alpha == null ? 1 : o.alpha;
  if (a <= 0.001 || !sh) return;
  const o0 = toPx(ap, dvT, mlT), odv = toPx(ap, dvT + 1000, mlT), oml = toPx(ap, dvT, mlT + 1000);
  const ax = [(odv[0] - o0[0]) / 1000, (odv[1] - o0[1]) / 1000], am = [(oml[0] - o0[0]) / 1000, (oml[1] - o0[1]) / 1000];
  const { p, ty, par, rad, n, d, soma } = sh, cr = Math.cos(rot || 0), sr = Math.sin(rot || 0), mir = o.mirror ? -1 : 1;
  const X = new Float32Array(n), Y = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const v0 = p[i * 3 + 1] - soma[1], m0 = mir * (p[i * 3 + 2] - soma[2]), ddv = v0 * cr - m0 * sr, dml = v0 * sr + m0 * cr;
    X[i] = o0[0] + ax[0] * ddv + am[0] * dml; Y[i] = o0[1] + ax[1] * ddv + am[1] * dml;
  }
  const rev = o.reveal == null ? 1e9 : o.reveal, revA = o.revealA == null ? 0 : o.revealA;
  // four strokes: thick, middle and fine dendrites, then the axon
  const buckets = [[], [], [], []];
  for (let i = 0; i < n; i++) {
    const j = par[i];
    if (j < 0 || j >= n) continue;
    const t = ty[i];
    if (t === 2) { if (d[i] <= revA && (!o.keepA || (o.keepA[i] && o.keepA[j]))) buckets[3].push(i); continue; }
    if (t !== 3 && t !== 4 && t !== 1) continue;
    if (d[i] > rev) continue;
    const r = rad[i] || 0.5;
    buckets[r > 1.4 ? 0 : r > 0.7 ? 1 : 2].push(i);
  }
  const W = [3.0, 2.0, 1.4, 1.0], cc = hex(col);
  c.save(); c.globalAlpha = a; c.lineCap = 'round'; c.lineJoin = 'round';
  // an ink line under each stroke, so the cell reads over the coloured layers
  for (let pass = 0; pass < 2; pass++) {
    buckets.forEach((bk, bi) => {
      if (!bk.length) return;
      c.beginPath();
      for (const i of bk) { const j = par[i]; c.moveTo(X[j], Y[j]); c.lineTo(X[i], Y[i]); }
      if (pass === 0) { c.strokeStyle = bi === 3 ? 'rgba(4,6,9,0.35)' : 'rgba(4,6,9,0.62)'; c.lineWidth = W[bi] + 2.2; }
      else { c.strokeStyle = bi === 3 ? rgba(cc, 0.62 * (o.axonA == null ? 1 : o.axonA)) : col; c.lineWidth = W[bi]; }
      c.stroke();
    });
  }
  // the soma
  const r0 = 4.6;
  c.fillStyle = col; c.strokeStyle = 'rgba(4,6,9,0.85)'; c.lineWidth = 2.2;
  c.beginPath(); c.arc(o0[0], o0[1], r0, 0, Math.PI * 2); c.stroke(); c.fill();
  c.strokeStyle = 'rgba(255,255,255,0.75)'; c.lineWidth = 1; c.stroke();
  c.restore();
  return o0;
}

/* ------------------------------------------------------------ the scenes */
const SC = [];
const scene = (o) => SC.push(o);
/* the probe line, framed for the scenes on the section */
const frProbe = (xf) => { const g = P().geo; return framing(xf, 104, 548, g.top - 40, g.bottom + 40); };
const frDentate = (xf) => { const g = P().geo, z = g.zones; return framing(xf, 112, 548, z.supd.dv0 - 140, z.infd.dv1 + 90); };
const brainC = () => [0, 0.25, 0.35];
const BRAIN_DIR = [0.46, 0.76, 0.48];

scene({ name: 'title', dur: 6.5, scrim: 0, mood: 'open',
  card: ['Title card', 'A KCNT1 SEIZURE, RECORDED', 'Watching a seizure spread', 'Inside the hippocampus of a mouse with a KCNT1 variant', 'Epilepsy Cognition Development Lab, University of Vermont'],
  enter() { go(FS.brain); },
  update(t) {
    look(brainC(), yaw(BRAIN_DIR, -14 + F.t * 1.1), 22, 4.0, 0.3);
    show(el.black, 1 - smooth(t / 2.2));
    show(el.title, fade(t, 1.0, 6.0, 0.9, 0.7), 12);
  },
  exit() { show(el.title, 0); show(el.black, 0); },
});
scene({ name: 'brain', dur: 9, chap: 1, tag: 'atlas', mood: 'open', sfx: [[6.4, 'whoosh', { gain: 0.8, dur: 2.4 }]],
  enter() { if (P().stop.key !== 'film_brain') go(FS.brain); },
  cap: [[0.3, 4.3, 'This is a mouse brain, about a centimeter long.', 'A 3D reconstruction from the Allen Mouse Brain Atlas'],
        [4.6, 8.8, 'Inside it, in color: the hippocampus, one on each side.']],
  update(t) {
    const u = smooth((t - 0.0) / 3.0), z = ease((t - 6.6) / 2.4);
    const dir = yaw(BRAIN_DIR, -14 + F.t * 1.1);
    const hip = hpfW('DG') || [2.4, 1.2, 1.4];
    const tgt = lerp3(brainC(), lerp3(brainC(), hip, 0.75), z);
    look(tgt, dir, lerp(22, 12.5, z), 4.0 * (1 - u), 0.3 * (1 - u));
  },
  post(c, t) {
    const a = fade(t, 4.8, 8.9, 0.6, 0.4);
    pin3(c, hpfW('DG'), 'Hippocampus', { alpha: a, color: '#ffd27f', dx: 36, dy: -40 });
    pin3(c, hpfW('DG', 'l'), 'Hippocampus', { alpha: a * 0.95, color: '#ffd27f', dx: -36, dy: -40 });
  },
});
const HPF_DIR = [0.62, 0.48, -0.62];
scene({ name: 'hippo', dur: 11, chap: 2, tag: 'atlas', xin: 0.9, mood: 'open',
  cap: [[0.5, 5.4, 'The hippocampus helps us form memories.', 'Its name means “seahorse,” after its curled shape.'],
        [5.7, 10.8, 'It is also one of the brain\'s most seizure-prone circuits.']],
  enter() { go(FS.hpf); },
  update(t) {
    const hip = hpfW('DG') || [2.4, 1.2, 1.4];
    const cut = W3(P().geo.ap, 2300, P().geo.ml + 300);
    const u = ease(t / 11);
    look(lerp3(lerp3(brainC(), hip, 0.75), lerp3(hip, cut, 0.55), u), yaw(HPF_DIR, lerp(-6, 12, u)), lerp(12.5, 8.6, u));
  },
  post(c, t) {
    const a = fade(t, 5.6, 11.2, 0.7, 0.3), g = P().geo;
    const dg = planeCentre(['gcl1', 'gcl2', 'hil'], g.ap), ca3 = planeCentre(['ca3sp'], g.ap), ca1 = planeCentre(['ca1sp'], g.ap);
    if (dg) pin3(c, W3(dg[0] - 5, dg[1], dg[2]), 'Dentate gyrus', { alpha: a, color: C.gc, dx: 46, dy: 56 });
    if (ca3) pin3(c, W3(ca3[0] - 5, ca3[1], ca3[2]), 'CA3', { alpha: a, color: C.ca3, dx: -44, dy: 46 });
    if (ca1) pin3(c, W3(ca1[0] - 5, ca1[1], ca1[2]), 'CA1', { alpha: a, color: C.ca1, dx: 0, dy: -38 });
  },
});
scene({ name: 'model', dur: 12.5, chap: 3, tag: 'model', scrim: 0, mood: 'open', sfx: [[0.15, 'swell', { gain: 0.5 }]],
  card: ['The model (a card)', 'Mice with a KCNT1 variant', '1  They carry a change found in people with KCNT1 epilepsy. (Kcnt1 Y777H in mice; KCNT1 Y796H in people)',
    '2  It makes a potassium channel overactive. (The sodium-activated K+ channel KNa1.1, or Slack)', '3  That quiets inhibitory neurons, the brain’s brakes.',
    '4  Mice with two copies have frequent seizures, many of them in sleep. (Shore et al., Cell Reports 2020)'],
  enter() { if (P().stop.key !== 'film_hpf') go(FS.hpf); },
  update(t) {
    const hip = hpfW('DG') || [2.4, 1.2, 1.4];
    const cut = W3(P().geo.ap, 2300, P().geo.ml + 300);
    look(lerp3(hip, cut, 0.55), yaw(HPF_DIR, 12 + t * 1.2), 8.6, 2.6 * smooth(t / 1.5), 0);
    show(el.model, fade(t, 0.2, 12.9, 0.8, 0.5));
    el.modelItems.forEach((li, i) => show(li, fade(t, 0.9 + i * 2.8, 99, 0.6, 0.1), 10));
  },
  exit() { show(el.model, 0); },
});
const PROBE_DIR0 = [0.58, 0.42, -1], PROBE_DIR1 = [0.06, 0.03, -1];
let probeSet = null;
function probeAt(depthU, ribbon) {
  // the recorded probe: vertical, AP -1.8, ML +1.4, its 64 sites spanning CA1 to the lower blade
  const g = P().geo, pitch = (g.bottom - g.top) / 63, first = 40;
  const tipF = g.bottom + first, tipDv = lerp(-900, tipF, depthU);
  const key = tipDv.toFixed(1) + (ribbon ? 'r' : '');
  if (probeSet === key) return;
  probeSet = key;
  const pr = { tip: [g.ap, tipDv, g.ml], dir: [0, 1, 0], contacts: 64, pitch, first, length: tipDv + 1600 };
  if (ribbon) pr.ribbon = Array.from({ length: 64 }, (_, i) => { const l = lamByCode(lamAt(g.ap, tipF - first - i * pitch, g.ml)); return l ? lamColor(l.key) : '#777777'; });
  S.stage.setProbe(pr);
}
scene({ name: 'probe3d', dur: 9, chap: 4, tag: 'atlas', xin: 0.8, mood: 'method', sfx: [[0.9, 'slide', { gain: 0.55, dur: 4.4 }]],
  enter() { if (P().stop.key !== 'film_hpf') go(FS.hpf); },
  cap: [[0.5, 8.8, 'To listen in, we lower a thin probe with 64 recording sites through the hippocampus.', 'A silicon probe, in an awake mouse']],
  update(t) {
    const g = P().geo, mid = W3(g.ap, (g.top + g.bottom) / 2 - 150, g.ml);
    const u = ease(t / 9);
    look(add(mid, [0.25 * u, 0, 0]), norm(lerp3(norm(PROBE_DIR0), norm(PROBE_DIR1), u)), lerp(6.6, 4.4, u), 0.0, 0.0);
    probeAt(ease((t - 0.6) / 4.4), t > 5.4);
  },
  post(c, t) {
    const g = P().geo, pitch = (g.bottom - g.top) / 63, first = 40, tipF = g.bottom + first;
    const tipDv = lerp(-900, tipF, ease((t - 0.6) / 4.4));
    const a = proj(W3(g.ap, Math.max(-900, tipDv - 1600), g.ml)), b = proj(W3(g.ap, tipDv, g.ml));
    if (a[2] > 1 || b[2] > 1) return;
    c.save();
    c.strokeStyle = 'rgba(235,242,248,0.85)'; c.lineWidth = 1.3; c.shadowColor = 'rgba(200,225,255,0.9)'; c.shadowBlur = 8;
    c.beginPath(); c.moveTo(a[0], a[1]); c.lineTo(b[0], b[1]); c.stroke();
    c.shadowBlur = 0; c.fillStyle = '#ffd36b';
    for (let i = 0; i < 64; i++) { const dv = tipDv - first - i * pitch; if (dv < -900) continue; const q = proj(W3(g.ap, dv, g.ml)); c.fillRect(q[0] - 1.3, q[1] - 0.5, 2.6, 1.0); }
    c.restore();
  },
  exit() { probeSet = null; S.stage.setProbe(null); },
});
scene({ name: 'probe2d', dur: 8.5, chap: 4, tag: 'probe', xin: 1.0, mood: 'method',
  cap: [[0.6, 8.3, 'Each site hears its own layer, from CA1 at the top down through the dentate gyrus.']],
  enter() { go(FS.probe); },
  update() { setSlice(frProbe(0.42)); },
  post(c, t) { drawShank(c, { alpha: fade(t, 0.3, 99, 0.8), size: 17, dgNames: true }); },
});
/* cells and layers: the same section and the same framing, with real traced neurons drawn into their layers */
let CELLS2 = null;
const STROKE = { up: '#ff9ea4', low: '#ffc2d8', hil: '#ffd05a', ca1: '#b4ee78', ca3: '#5fd8cc' };
const DG_LAYERS = ['oml1', 'mml1', 'iml1', 'gcl1', 'hil', 'gcl2', 'iml2', 'mml2', 'oml2'];
function placeCells() {
  const g = P().geo, z = g.zones, mid = (k) => (z[k].dv0 + z[k].dv1) / 2;
  // a tracing put with its soma in a layer at ml (um from the probe), its dendrites (or axon) turned to run along want [dv, ml]
  const put = (key, lay, dml, nearDv, want, col, byAxon, mirror) => {
    const sh = cellShape(key);
    if (!sh) return null;
    const ml = g.ml + dml, dv = layerMid(lay, g.ap, ml, nearDv);
    if (dv == null) return null;
    const from = byAxon ? sh.axonDir : sh.dendDir;
    const rot = want ? turnTo(mirror ? -from : from, want) : 0;
    return { key, sh, dv, ml, rot, col, mirror: !!mirror };
  };
  const up = [-1, 0], down = [1, 0];
  const ca3c = planeCentre(['ca3sp'], g.ap, [mid('hil') + 250, g.ml + 1500]);
  // the granule cells: one tracing (MouseLight AA0573), two to a blade, the second its mirror image
  const L = {
    gcUp: [put('gc', 'gcl1', -470, mid('supg'), up, STROKE.up, false, false), put('gc', 'gcl1', 150, mid('supg'), up, STROKE.up, false, true)].filter(Boolean),
    gcLow: [put('gc', 'gcl2', -500, mid('infg'), down, STROKE.low, false, true), put('gc', 'gcl2', -190, mid('infg'), down, STROKE.low, false, false)].filter(Boolean),
    hipp: put('hipp', 'hil', 230, mid('hil'), up, STROKE.hil, true),
    ca1: put('ca1', 'ca1sp', -420, mid('ca1o'), down, STROKE.ca1),
    ca3: null,
  };
  if (ca3c) {
    const sh = cellShape('ca3'), toHil = [mid('hil') - ca3c[1], g.ml + 350 - ca3c[2]];
    L.ca3 = { key: 'ca3', sh, dv: ca3c[1], ml: ca3c[2], rot: turnTo(sh.dendDir, toHil), col: STROKE.ca3 };
  }
  // the brake cell's axon, kept to the dentate gyrus, where it lands
  if (L.hipp) {
    const codes = new Set(DG_LAYERS.map((k) => (lamOf(k) || {}).code)), { p, n, soma } = L.hipp.sh, cr = Math.cos(L.hipp.rot), sr = Math.sin(L.hipp.rot);
    L.hipp.keepA = new Uint8Array(n);
    for (let i = 0; i < n; i++) {
      const v0 = p[i * 3 + 1] - soma[1], m0 = p[i * 3 + 2] - soma[2];
      L.hipp.keepA[i] = codes.has(lamAt(g.ap, L.hipp.dv + v0 * cr - m0 * sr, L.hipp.ml + v0 * sr + m0 * cr)) ? 1 : 0;
    }
  }
  CELLS2 = L;
}
const LAYER_GLOW = [['ca1sp', BAR.ca1], ['gcl1', BAR.up], ['gcl2', BAR.low], ['hil', BAR.hil], ['ca3sp', '#45b0a8']];
const CELL_STEPS = { gc: 0.4, hipp: 5.3, ca: 11.2, all: 16.6 };
scene({ name: 'cells2d', dur: 21, chap: 5, tag: 'cells', mood: 'method',
  cap: [[0.5, 5.0, 'Granule cells fill the two blades of the dentate gyrus. Their branches reach out to catch signals from the cortex.', 'Real neurons, traced one by one, placed in their layers'],
        [5.3, 10.9, 'Between the blades, in the hilus, inhibitory cells are the brakes: they reach up to where those signals land and keep granule cells from firing all at once.', 'KCNT1 variants weaken inhibitory cells like these.'],
        [11.2, 16.3, 'What gets through goes on to CA3, then to CA1, whose cells line up in a layer of their own.'],
        [16.6, 20.8, 'Each kind of cell keeps its body in its own layer, and our probe passes through them all.']],
  sfx: [[0.5, 'bloom', { gain: 0.5, pitch: 0 }], [5.4, 'bloom', { gain: 0.5, pitch: 4 }], [11.3, 'bloom', { gain: 0.5, pitch: 7 }]],
  enter() { if (P().stop.key !== 'film_probe') go(FS.probe); CELLS2 = null; },
  update(t) {
    setSlice(frProbe(0.42));
    if (!CELLS2 && P().stop.key === 'film_probe') placeCells();
    const k1 = fade(t, CELL_STEPS.gc, 99, 1.2), k2 = fade(t, CELL_STEPS.hipp, 99, 1.2), k3 = fade(t, CELL_STEPS.ca, 99, 1.2);
    const pulse = new Map(), on = { ca1sp: k3, gcl1: k1, gcl2: k1, hil: k2, ca3sp: k3 };
    LAYER_GLOW.forEach(([lk, col]) => { const code = (lamOf(lk) || {}).code; if (code && on[lk] > 0.01) pulse.set(code, hex(col).concat(0.5 * on[lk])); });
    S.stage.setHighlights({ lam: new Map(), allen: new Map(), pulse, dimRest: t > 0.6 });
  },
  post(c, t) {
    if (!CELLS2) { drawShank(c, { alpha: 1, size: 17, names: false }); return; }
    const L = CELLS2, grow = (t0, dur, sh) => sh ? ease((t - t0) / dur) * sh.dMax * 1.02 : 0, growA = (t0, dur, sh) => sh ? ease((t - t0) / dur) * Math.min(sh.aMax, 2400) : 0;
    const on = (step) => (t < step ? 0 : 1);
    // the cells of the moment at full strength, the ones already met a step back, all of them at the end
    const focusA = (from, to) => 0.45 + 0.55 * Math.max(fade(t, from, to, 0.5, 0.5), fade(t, CELL_STEPS.all, 99, 0.6));
    const kGc = focusA(CELL_STEPS.gc, CELL_STEPS.hipp), kHi = focusA(CELL_STEPS.hipp, CELL_STEPS.ca), kCa = focusA(CELL_STEPS.ca, CELL_STEPS.all);
    // the granule cells, two in each blade
    L.gcUp.concat(L.gcLow).forEach((x, i) => drawNeuron(c, x.sh, x.dv, x.ml, x.rot, x.col, { alpha: on(CELL_STEPS.gc) * kGc, mirror: x.mirror, reveal: grow(CELL_STEPS.gc + (i % 2) * 0.35 + (i > 1 ? 0.2 : 0), 2.4, x.sh), revealA: growA(CELL_STEPS.gc + 1.4, 3.0, x.sh), axonA: 0.55 }));
    // the hilar brake cell, its axon climbing to the molecular layer, where the cortex's input lands
    if (L.hipp) drawNeuron(c, L.hipp.sh, L.hipp.dv, L.hipp.ml, L.hipp.rot, L.hipp.col, { alpha: on(CELL_STEPS.hipp) * kHi, reveal: grow(CELL_STEPS.hipp, 1.6, L.hipp.sh), revealA: growA(CELL_STEPS.hipp + 0.8, 3.6, L.hipp.sh), axonA: 1, keepA: L.hipp.keepA });
    // CA3 and CA1 pyramidal cells
    [L.ca3, L.ca1].forEach((x, i) => { if (x && x.sh) drawNeuron(c, x.sh, x.dv, x.ml, x.rot, x.col, { alpha: on(CELL_STEPS.ca) * kCa, reveal: grow(CELL_STEPS.ca + i * 1.1, 2.6, x.sh), revealA: 0 }); });
    drawShank(c, { alpha: 1, size: 17, names: false, lit: t > CELL_STEPS.all ? null : new Set() });
    // names
    const g = P().geo, at = (x) => toPx(g.ap, x.dv, x.ml);
    const nA = (from, k) => fade(t, from + 0.8, 99, 0.6) * (0.55 + 0.45 * (k - 0.45) / 0.55);
    if (L.gcUp[0]) { const q = at(L.gcUp[0]); pin(c, q[0], q[1], 'Granule cells', { alpha: nA(CELL_STEPS.gc, kGc), color: C.up, dx: -64, dy: -40, sub: 'upper blade' }); }
    if (L.gcLow[0]) { const q = at(L.gcLow[0]); pin(c, q[0], q[1], 'Granule cells', { alpha: nA(CELL_STEPS.gc, kGc), color: C.low, dx: -70, dy: 40, sub: 'lower blade' }); }
    if (L.hipp) { const q = at(L.hipp); pin(c, q[0], q[1], 'Hilar brake cell', { alpha: nA(CELL_STEPS.hipp, kHi), color: C.hil, dx: 120, dy: 14, sub: 'an inhibitory interneuron' }); }
    if (L.ca3) { const q = at(L.ca3); pin(c, q[0], q[1], 'CA3 pyramidal cell', { alpha: nA(CELL_STEPS.ca, kCa), color: C.ca3, dx: 58, dy: -64 }); }
    if (L.ca1) { const q = at(L.ca1); pin(c, q[0], q[1], 'CA1 pyramidal cell', { alpha: nA(CELL_STEPS.ca + 1.1, kCa), color: C.ca1, dx: -60, dy: -34 }); }
  },
  exit() { S.stage.setHighlights({ lam: new Map(), allen: new Map(), pulse: new Map(), dimRest: false }); },
});
scene({ name: 'sztitle', dur: 3.6, chap: 6, tag: 'rec', scrim: 0, mood: 'tense', sfx: [[0.05, 'impact', { gain: 0.8 }]],
  card: ['A card', 'MOUSE 459', 'One seizure, recorded', 'Kcnt1 Y777H, two copies · awake · December 6, 2024'],
  enter() { if (P().stop.view !== 'dentate' && P().stop.view !== 'probe') go(FS.dentate); },
  update(t) { setSlice(frDentate(0.36)); show(el.card, fade(t, 0.0, 3.6, 0.6, 0.6)); },
  exit() { show(el.card, 0); },
});

/* ---- the whole seizure at a glance, then step by step ---- */
let wall = null, wallZ = null;
const OV = { x0: 216, x1: VW - 52, y0: 106, y1: 412, t0: -12, t1: 60, dy0: 424, dy1: 442, by0: 452, by1: 470, ay: 478 };
const SZ_END = 43.8;
/* the window of the recording on screen: the whole of it, or (the run-up) zoomed in on its start */
const ZOOM = [-12, 6.5];
let OVW = [OV.t0, OV.t1];
const ovX = (tt) => OV.x0 + (tt - OVW[0]) / (OVW[1] - OVW[0]) * (OV.x1 - OV.x0);
function ensureWall() {
  if (!wall) wall = recordingPicture(OV.t0, OV.t1, OV.x1 - OV.x0, OV.y1 - OV.y0,
    { trace: 'rgba(244,247,250,0.82)', lw: 1.0, every: 2, first: 1, span: 8, gainDiv: 1.7, clipPx: 25, smooth: 9 });
  if (!wallZ) wallZ = recordingPicture(ZOOM[0], ZOOM[1], OV.x1 - OV.x0, OV.y1 - OV.y0,
    { trace: 'rgba(244,247,250,0.85)', lw: 1.0, every: 2, first: 1, span: 8, gainDiv: 1.7, clipPx: 25, smooth: 3 });
}
/* the reading head: held at the seizure's start and at its end, quick in between (s of the recording at scene time t) */
const OVH = [[0, -12], [0.8, -12], [4.0, 0], [6.2, 0], [11.4, SZ_END], [12.8, SZ_END], [14.0, 60]];
function headAt(t, keys) {
  if (t <= keys[0][0]) return keys[0][1];
  for (let i = 1; i < keys.length; i++) if (t <= keys[i][0]) { const [ta, va] = keys[i - 1], [tb, vb] = keys[i]; return va + (vb - va) * smooth((t - ta) / (tb - ta)); }
  return keys[keys.length - 1][1];
}
/* the picture with its rows: discharges and the brake cell's spikes under it, the axis, the onset and the end.
   upto: drawn up to this time; o.veil: [[from, to, alpha]] dimmed; o.glow: the discharges lit up to here */
function drawWall(c, upto, a, o) {
  o = o || {};
  const { x0, x1, y0, y1 } = OV, [w0, w1] = OVW, hx = clamp(ovX(Math.min(upto, w1)), x0, x1);
  c.save(); c.globalAlpha = a;
  c.fillStyle = 'rgb(5,8,12)'; c.fillRect(0, 0, VW, VH);
  c.fillStyle = 'rgba(255,255,255,0.025)'; c.fillRect(x0, y0, x1 - x0, y1 - y0);
  c.save(); c.beginPath(); c.rect(x0, y0 - 2, hx - x0, y1 - y0 + 4); c.clip();
  // the whole recording, stretched to the window; once zoomed, the window drawn sharp over it
  const sx = (w0 - OV.t0) / (OV.t1 - OV.t0) * wall.width, sw = (w1 - w0) / (OV.t1 - OV.t0) * wall.width;
  c.drawImage(wall, sx, 0, sw, wall.height, x0, y0, x1 - x0, y1 - y0);
  if (o.sharp > 0.001 && wallZ) { c.globalAlpha = a * o.sharp; c.drawImage(wallZ, x0, y0, x1 - x0, y1 - y0); c.globalAlpha = a; }
  c.restore();
  groupBrackets(c, x0, y0, y1 - y0, { alpha: 1, size: 14.5 });
  const inWin = (s) => s >= w0 && s <= Math.min(upto, w1);
  // the discharges in the dentate gyrus, one tick each
  const p = P(), wide = (w1 - w0) < 30;
  c.fillStyle = 'rgba(255,255,255,0.04)'; c.fillRect(x0, OV.dy0, x1 - x0, OV.dy1 - OV.dy0);
  for (const d of p.D.discharges) {
    if (!inWin(d)) continue;
    const lit = o.glow != null && d <= o.glow && d > o.glowFrom;
    c.fillStyle = lit ? (d > o.glow - 0.4 ? '#fff4dc' : C.ember) : 'rgba(255,173,90,0.55)';
    c.fillRect(Math.round(ovX(d)) - 0.8, OV.dy0 + 2, wide ? 2.2 : lit ? 1.6 : 1.2, OV.dy1 - OV.dy0 - 4);
  }
  text(c, 'Discharges', x0 - 15, (OV.dy0 + OV.dy1) / 2, { size: 13.5, w: 600, align: 'right', color: C.text4 });
  // the brake cell's spikes; from 3.7 s the seizure's discharges drown them (figure A masks them too)
  c.fillStyle = 'rgba(255,255,255,0.04)'; c.fillRect(x0, OV.by0, x1 - x0, OV.by1 - OV.by0);
  const sp = p.B.arrays.spikes, ms = p.B.header.unit.masked;
  c.fillStyle = C.hil;
  for (let i = 0; i < sp.length; i++) { const s = sp[i]; if (!inWin(s) || (s >= ms[0] && s <= ms[1])) continue; c.fillRect(Math.round(ovX(s)) - 0.5, OV.by0 + 3, wide ? 1.4 : 1.1, OV.by1 - OV.by0 - 6); }
  if (upto > ms[0] && ms[0] < w1) {
    const xa = ovX(ms[0]), xe = ovX(Math.min(ms[1], w1)), xb = Math.min(hx, xe);
    c.save(); c.beginPath(); c.rect(xa, OV.by0, xb - xa, OV.by1 - OV.by0); c.clip();
    c.strokeStyle = 'rgba(255,255,255,0.12)'; c.lineWidth = 1; c.beginPath();
    for (let xx = xa - 30; xx < xb + 30; xx += 6) { c.moveTo(xx, OV.by1); c.lineTo(xx + 18, OV.by0); } c.stroke();
    c.restore();
    if (upto > ms[0] + 12 && xe - xa > 220) { const s1 = 'its spikes hidden under the seizure', cx = (xa + xe) / 2; c.font = '600 11px ' + FONT; const tw = c.measureText(s1).width + 12; c.fillStyle = 'rgba(8,11,16,0.92)'; c.fillRect(cx - tw / 2, OV.by0 + 2, tw, OV.by1 - OV.by0 - 4); text(c, s1, cx, (OV.by0 + OV.by1) / 2 + 0.5, { size: 11, w: 600, align: 'center', color: C.text2, halo: false }); }
  }
  text(c, 'Brake cell', x0 - 15, (OV.by0 + OV.by1) / 2, { size: 13.5, w: 600, align: 'right', color: C.brake });
  timeAxis(c, x0, x1, OV.ay, w0, w1, (w1 - w0) > 30 ? 10 : 2, { upto: upto + 0.01 });
  // dimmed spans
  (o.veil || []).forEach(([fa, fb, va]) => {
    if (va <= 0.001) return;
    const xa = ovX(Math.max(fa, w0)), xb = ovX(Math.min(fb, w1));
    if (xb <= xa) return;
    c.fillStyle = 'rgba(5,8,12,' + va.toFixed(3) + ')'; c.fillRect(xa, y0 - 3, xb - xa, OV.by1 - y0 + 6);
  });
  // the onset and the end
  if (upto >= 0 && w0 <= 0 && w1 >= 0) {
    const x = ovX(0);
    c.fillStyle = 'rgba(255,214,160,0.9)'; c.fillRect(Math.round(x), y0 - 30, 1.5, OV.by1 - y0 + 30);
    if (o.onsetLabel !== false) text(c, 'Seizure begins', x + 8, y0 - 22, { size: 14.5, w: 700, color: C.ember, halo: false });
  }
  if (upto >= SZ_END && w1 >= SZ_END) {
    const x = ovX(SZ_END);
    c.fillStyle = 'rgba(255,214,160,0.75)'; c.fillRect(Math.round(x), y0 - 30, 1.5, OV.by1 - y0 + 30);
    text(c, 'Seizure ends', x + 8, y0 - 22, { size: 14.5, w: 700, color: C.ember, halo: false });
  }
  c.restore();
  return hx;
}
/* the clock, under the picture at its right: how far into the seizure, said so it always agrees with the words */
function ovClock(c, tt, a, speedTxt) {
  if (a <= 0.001) return;
  c.save(); c.globalAlpha = a;
  const x = OV.x1, y = OV.ay + 44;
  let big, small, col = C.text;
  if (tt < -0.05) { big = Math.abs(tt).toFixed(1) + ' s'; small = 'before the seizure'; }
  else if (tt <= SZ_END + 0.05) { big = Math.max(0, tt).toFixed(1) + ' s'; small = 'into the seizure'; col = C.ember; }
  else { big = tt.toFixed(1) + ' s'; small = 'since it began: it is over'; }
  c.font = '500 14px ' + FONT; const lw = c.measureText(small).width;
  text(c, big, x - lw - 10, y, { size: 22, w: 750, align: 'right', color: col, halo: false });
  text(c, small, x, y + 1, { size: 14, w: 500, align: 'right', color: C.text2, halo: false });
  if (speedTxt) text(c, speedTxt, x, y + 22, { size: 12.5, w: 600, align: 'right', color: C.text3, halo: false });
  c.restore();
}
scene({ name: 'overview', dur: 16, chap: 6, tag: 'rec', mood: 'tense', xin: 0.6,
  cap: [[0.3, 4.0, 'Here is the whole recording at a glance, sped up.', 'Each line is the voltage at one depth; the colors show current flowing into cells (blue) and out of them (red).'],
        [4.1, 6.3, 'At zero, the seizure begins…'],
        [6.5, 11.3, '…and the whole hippocampus fires again and again, for about 40 seconds…'],
        [11.5, 13.6, '…then it stops.'],
        [13.9, 15.8, 'Now let’s take it step by step.']],
  sfx: [[4.0, 'impact', { gain: 1.0 }], [6.25, 'rush', { gain: 0.7, dur: 5.2 }], [11.4, 'release', { gain: 0.7 }]],
  enter() { ensureWall(); },
  update() { setSlice(frDentate(0.36)); },
  post(c, t) {
    OVW = [OV.t0, OV.t1];
    const a = fade(t, 0, 99, 0.5), tt = headAt(t, OVH);
    const hx = drawWall(c, tt, a, {});
    c.save(); c.globalAlpha = a;
    // the reading head, and a flash where it holds
    if (tt < OV.t1 - 0.01) {
      const gr = c.createLinearGradient(hx - 46, 0, hx, 0); gr.addColorStop(0, 'rgba(255,190,110,0)'); gr.addColorStop(1, 'rgba(255,190,110,0.22)');
      c.fillStyle = gr; c.fillRect(hx - 46, OV.y0, 46, OV.by1 - OV.y0);
      c.fillStyle = 'rgba(255,214,160,0.95)'; c.fillRect(hx - 1, OV.y0 - 6, 2, OV.by1 - OV.y0 + 12);
    }
    const flash = Math.max(fade(t, 4.0, 6.2, 0.15, 1.4), fade(t, 11.4, 12.8, 0.15, 1.0) * 0.7);
    if (flash > 0.01) { c.globalAlpha = a * flash; c.drawImage(tinted('#ffb066'), hx - 60, OV.y0 - 40, 120, OV.by1 - OV.y0 + 80); }
    c.globalAlpha = a;
    // the seizure, bracketed as it goes
    if (tt > 0) {
      const xe = ovX(Math.min(tt, SZ_END)), yb = OV.y0 - 6;
      c.strokeStyle = C.ember; c.lineWidth = 2; c.beginPath(); c.moveTo(ovX(0), yb); c.lineTo(xe, yb); if (tt >= SZ_END) c.lineTo(xe, yb + 5); c.stroke();
      if (tt >= SZ_END) { c.globalAlpha = a * fade(t, 11.4, 99, 0.8); text(c, 'about 40 seconds', (ovX(0) + ovX(SZ_END)) / 2, yb - 14, { size: 15, w: 700, align: 'center', color: C.ember, halo: false }); }
    }
    c.restore();
    ovClock(c, tt, a, t > 0.8 && t < 14.2 && Math.abs(tt) > 0.05 && Math.abs(tt - SZ_END) > 0.05 ? 'sped up' : '');
  },
});
/* the run-up, on the same picture: the discharges coming faster, the brake cell driven hard; then the onset */
const PRE = { zoom: [0.2, 1.9], sweep: [2.1, 9.1], brake: [9.3, 15.7], onset: [15.9, 19.5] };
scene({ name: 'preictal', dur: 19.5, chap: 6, tag: 'rec', mood: 'tense',
  cap: [[0.4, 9.1, 'First, the run-up. In the half-minute before, small discharges come faster and faster.', '69 in the last 36 seconds; each stripe across the dentate gyrus is one.'],
        [9.3, 15.7, 'Meanwhile a brake cell in the hilus fires harder and harder: nearly 60 times a second, just before the start.', 'Its usual pace is about 12 a second. Its narrow spikes mark it as a likely inhibitory interneuron.'],
        [15.9, 19.4, 'Then, at zero, the seizure begins. Let’s slow its first six seconds down five times.']],
  sfx: (add) => {
    // a soft knock for each discharge as the reading head passes it
    const [s0, s1] = PRE.sweep;
    for (const d of P().D.discharges) if (d >= -12 && d < 0) add(s0 + (d + 12) / 12 * (s1 - s0), 'knock', { gain: 0.42 });
    add(PRE.brake[0] + 0.1, 'bloom', { gain: 0.45, pitch: 5 });
    add(PRE.onset[0] + 0.1, 'impact', { gain: 0.55 });
  },
  enter() { ensureWall(); },
  update() { setSlice(frDentate(0.36)); },
  post(c, t) {
    const [s0, s1] = PRE.sweep, [b0, b1] = PRE.brake, [o0] = PRE.onset, [z0, z1] = PRE.zoom;
    // the timeline zooms in on its first 18 seconds: the run-up and the seizure's start
    const zu = ease((t - z0) / (z1 - z0)), span = Math.exp(lerp(Math.log(OV.t1 - OV.t0), Math.log(ZOOM[1] - ZOOM[0]), zu));
    OVW = [OV.t0, OV.t0 + span];
    const vPost = fade(t, 0.2, o0 + 0.1, 0.9, 0.6) * 0.72, vPre = fade(t, o0, 99, 0.9) * 0.72;
    const head = -12 + 12 * clamp((t - s0) / (s1 - s0), 0, 1);
    const veil = [[0, OV.t1, vPost], [OV.t0, -0.4, vPre], [6.1, OV.t1, fade(t, o0, 99, 0.9) * 0.72]];
    drawWall(c, OV.t1, 1, { veil, glow: t >= s0 ? head : null, glowFrom: -12, sharp: fade(t, z1, 99, 0.35), onsetLabel: t < o0 });
    c.save();
    // the run-up, bracketed
    bracket(c, ovX(-12), ovX(0), OV.y0 - 8, 'Before: the run-up', C.ember, fade(t, 0.3, o0 + 0.2, 0.6, 0.5));
    // the second reading head
    if (t > s0 - 0.2 && t < s1 + 0.6) {
      const hx = ovX(head);
      c.globalAlpha = fade(t, s0 - 0.2, s1 + 0.6, 0.3, 0.5);
      c.fillStyle = 'rgba(255,214,160,0.95)'; c.fillRect(hx - 1, OV.y0 - 4, 2, OV.by1 - OV.y0 + 8);
      c.globalAlpha = 1;
    }
    // the brake cell's pace, over its run-up: spikes a second in 1 s windows, against its usual 12
    const ka = fade(t, b0, o0 + 0.3, 0.6, 0.6);
    if (ka > 0.01) {
      const yb = OV.y1 - 4, yh = 250, hz = (tt) => { let s = 0; for (let k = 0; k < 4; k++) s += R.unitRate(P().D, tt - 0.875 + k * 0.25); return s / 4; };
      const reveal = clamp((t - b0) / 2.4, 0, 1), tEnd = lerp(-10, 0, reveal);
      c.globalAlpha = ka;
      c.fillStyle = 'rgba(5,8,12,0.62)'; c.fillRect(ovX(-12), OV.y0, ovX(0) - ovX(-12), OV.y1 - OV.y0);
      c.beginPath(); c.moveTo(ovX(-10), yb);
      for (let tt = -10; tt <= tEnd + 1e-6; tt += 0.125) c.lineTo(ovX(tt), yb - Math.min(1, hz(tt) / 100) * yh);
      c.lineTo(ovX(tEnd), yb); c.closePath();
      const gr = c.createLinearGradient(0, yb - yh, 0, yb); gr.addColorStop(0, 'rgba(242,196,90,0.85)'); gr.addColorStop(1, 'rgba(242,196,90,0.18)');
      c.fillStyle = gr; c.fill();
      c.strokeStyle = C.hil; c.lineWidth = 2; c.beginPath();
      for (let tt = -10; tt <= tEnd + 1e-6; tt += 0.125) { const y = yb - Math.min(1, hz(tt) / 100) * yh; if (tt === -10) c.moveTo(ovX(tt), y); else c.lineTo(ovX(tt), y); }
      c.stroke();
      // its usual pace
      const y12 = yb - 12.4 / 100 * yh;
      c.setLineDash([4, 4]); c.strokeStyle = 'rgba(255,255,255,0.55)'; c.lineWidth = 1.2; c.beginPath(); c.moveTo(ovX(-12), y12); c.lineTo(ovX(0), y12); c.stroke(); c.setLineDash([]);
      text(c, 'its usual pace, 12 a second', ovX(-11.8), y12 + 12, { size: 12.5, w: 600, color: C.text2 });
      c.globalAlpha = ka * fade(t, b0 + 2.4, 99, 0.6);
      const yp = yb - 58 / 100 * yh;
      text(c, 'brake cell:', ovX(-2.6), yp - 52, { size: 13, w: 600, align: 'center', color: C.brake });
      text(c, '58 spikes a second', ovX(-2.6), yp - 33, { size: 16, w: 750, align: 'center', color: C.brake });
      c.globalAlpha = 1;
    }
    // the onset, and the six seconds to come
    const kb = fade(t, o0, 99, 0.6);
    if (kb > 0.01) {
      bracket(c, ovX(-0.4), ovX(6.1), OV.y0 - 8, 'The first six seconds', C.ember, kb);
      c.globalAlpha = kb * fade(t, o0, o0 + 2.2, 0.2, 1.6);
      c.drawImage(tinted('#ffb066'), ovX(0) - 60, OV.y0 - 40, 120, OV.by1 - OV.y0 + 80);
      c.globalAlpha = 1;
    }
    c.restore();
    ovClock(c, t < s0 ? -12 : head, fade(t, 0, s1 + 0.7, 0.4, 0.5), '');
  },
});
/* the spread, slowed */
let spreadPic = null;
const SPR = { x0: 770, x1: VW - 46, y0: 170, y1: 528, t0: -0.4, t1: 6.1 };
const stageNow = (t) => { let k = -1; STAGES.forEach((s, i) => { if (t >= s[0]) k = i; }); return k; };
const CAPS_SPREAD = [
  [0.3, 8.3, 'Slowed down five times: the seizure starts in the hilus…'],
  [8.5, 14.8, '…sweeps through the upper blade of the dentate gyrus…'],
  [15.0, 24.8, '…then the lower blade, as the brake cell falls silent…'],
  [25.0, 32.3, '…and reaches CA1 last, about four seconds after it began.'],
];
scene({ name: 'spread', dur: 32.5, chap: 7, tag: 'rec', xin: 0.9, mood: 'tense',
  cap: CAPS_SPREAD.map((c) => c.concat(['Blue: current flowing into cells · red: flowing out · white lines: voltage'])),
  sfx: STAGES.map((s, i) => [(s[0] + 0.4) * 5, 'bloom', { gain: 0.55, pitch: [0, 2, 3, 7][i] }]),
  enter() {
    go(FS.spread);
    if (!spreadPic) spreadPic = recordingPicture(SPR.t0, SPR.t1, SPR.x1 - SPR.x0, SPR.y1 - SPR.y0, { trace: 'rgba(240,244,248,0.75)', lw: 1.0 });
  },
  update() { setSlice(frProbe(0.2)); },
  post(c, t) {
    const p = P();
    const sk = stageNow(p.t);
    drawShank(c, { alpha: 1, levels: true, size: 15.5, focus: new Set(sk >= 0 ? [GROUPS.find((g) => g.stage === sk).key] : []) });
    drawUnit(c, 1);
    const { x0, x1, y0, y1, t0, t1 } = SPR, a = fade(t, 0.2, 99, 0.6);
    const X = (tt) => x0 + (tt - t0) / (t1 - t0) * (x1 - x0);
    c.save(); c.globalAlpha = a;
    panel(c, x0 - 128, 92, x1 - x0 + 128 + 24, 512, 1);
    c.drawImage(spreadPic, x0, y0, x1 - x0, y1 - y0);
    // what is still to come, veiled
    const px = clamp(X(p.t), x0, x1);
    c.fillStyle = 'rgba(8,11,16,0.8)'; c.fillRect(px, y0 - 1, x1 - px, y1 - y0 + 2);
    c.fillStyle = 'rgba(255,224,180,0.95)'; c.fillRect(px - 1, y0 - 8, 2, y1 - y0 + 16);
    // the stages, bracketed above
    STAGES.forEach(([s0, s1, name], i) => {
      const xa = X(s0), xb = X(s1), y = y0 - 12;
      const on = p.t >= s0 && p.t <= s1 + 0.25, past = p.t > s1 + 0.25, seen = p.t >= s0;
      const col = on ? C.ember : past ? '#c9a27a' : 'rgba(255,255,255,0.25)';
      c.strokeStyle = col; c.lineWidth = on ? 2 : 1.4;
      c.beginPath(); c.moveTo(xa + 1, y + 6); c.lineTo(xa + 1, y); c.lineTo(xb - 1, y); c.lineTo(xb - 1, y + 6); c.stroke();
      const cx = (xa + xb) / 2;
      c.fillStyle = on ? C.ember : seen ? 'rgba(255,173,90,0.25)' : 'rgba(255,255,255,0.08)';
      c.beginPath(); c.arc(cx, y - 15, 10.5, 0, Math.PI * 2); c.fill();
      text(c, String(i + 1), cx, y - 14.5, { size: 13, w: 750, align: 'center', color: on ? '#1a0f04' : seen ? C.ember : C.text3, halo: false });
      if (seen) text(c, name, cx, y - 37, { size: 13.5, w: on ? 700 : 550, align: 'center', color: on ? C.text : C.text2, halo: false });
    });
    groupBrackets(c, x0, y0, y1 - y0, { lit: (gr) => { const s = STAGES[gr.stage]; return p.t >= s[0] && p.t <= s[1] + 0.25 ? 1 : 0; }, size: 14.5 });
    // the brake cell's spikes, under the picture
    const uy = y1 + 12, uh = 20;
    c.fillStyle = 'rgba(255,255,255,0.05)'; c.fillRect(x0, uy, x1 - x0, uh);
    const sp = p.B.arrays.spikes, ms = p.B.header.unit.masked;
    for (let i = 0; i < sp.length; i++) { const s = sp[i]; if (s < t0 || s > Math.min(t1, p.t) || s >= ms[0]) continue; c.fillStyle = C.hil; c.fillRect(Math.round(X(s)) - 0.6, uy + 3, 1.3, uh - 6); }
    if (p.t > ms[0]) {
      // from 3.7 s the seizure's discharges drown its single spikes (figure A masks them too):
      // hatched, and said, uncovered by the reading head like everything else
      const xa = X(ms[0]), xe = X(Math.min(t1, ms[1])), xb = Math.min(px, x1);
      c.save(); c.beginPath(); c.rect(xa, uy, xb - xa, uh); c.clip();
      c.strokeStyle = 'rgba(255,255,255,0.13)'; c.lineWidth = 1; c.beginPath();
      for (let xx = xa - 30; xx < xe + 30; xx += 6) { c.moveTo(xx, uy + uh); c.lineTo(xx + uh, uy); } c.stroke();
      const s1 = 'spikes hidden by the seizure', cx = (xa + xe) / 2;
      c.font = '600 11px ' + FONT; const tw = c.measureText(s1).width + 12;
      c.fillStyle = 'rgba(10,14,20,0.94)'; c.fillRect(cx - tw / 2, uy + 2, tw, uh - 4);
      text(c, s1, cx, uy + uh / 2 + 0.5, { size: 11, w: 600, align: 'center', color: C.text2, halo: false });
      c.restore();
    }
    text(c, 'Brake cell', x0 - 15, uy + uh / 2, { size: 14.5, w: 600, align: 'right', color: C.brake });
    timeAxis(c, x0, x1, uy + uh + 6, t0, t1, 1, {});
    // the clock, in the panel's corner
    text(c, (p.t < -0.005 ? '−' : '') + Math.abs(p.t).toFixed(2) + ' s', x0 - 112, 124, { size: 22, w: 750, color: p.t < 0 ? C.text : C.ember, halo: false });
    text(c, p.t < -0.005 ? 'before the seizure' : 'into the seizure', x0 - 112, 146, { size: 12.5, w: 500, color: C.text2, halo: false });
    c.restore();
  },
});

/* ---- beyond the probe: the loop, as a map first ---- */
const NODE = {
  neo: { x: 96, y: 104, w: 214, h: 48, name: 'Neocortex', col: C.neo, bar: '#a9b2ae' },
  ecu: { x: 96, y: 236, w: 214, h: 112, name: 'Entorhinal cortex', col: C.ec, bar: '#5f8acb' },
  ecd: { x: 96, y: 348, w: 214, h: 112, name: '', col: C.ec, bar: '#5f8acb' },
  dg: { x: 440, y: 204, w: 206, h: 56, name: 'Dentate gyrus', col: C.gc, bar: BAR.up },
  ca3: { x: 812, y: 204, w: 176, h: 56, name: 'CA3', col: C.ca3, bar: '#45b0a8' },
  ca1: { x: 1000, y: 380, w: 176, h: 56, name: 'CA1', col: C.ca1, bar: BAR.ca1 },
  sub: { x: 600, y: 452, w: 196, h: 56, name: 'Subiculum', col: C.sub, bar: '#d2b06c' },
  brk: { x: 470, y: 300, w: 146, h: 34, name: 'hilus: brakes', col: C.hil, bar: BAR.hil },
};
const nc = (k) => { const n = NODE[k]; return [n.x + n.w / 2, n.y + n.h / 2]; };
/* the arrows: a quadratic curve each (from, control, to), and what it is called */
const ARC = {
  neo_ec: { p: [[284, 152], [294, 194], [284, 236]], name: '' },
  ec_dg: { p: [[310, 286], [380, 232], [440, 232]], name: 'perforant path', at: [372, 214] },
  dg_ca3: { p: [[646, 232], [730, 232], [812, 232]], name: 'mossy fibers', at: [729, 214] },
  ca3_rec: { p: [[868, 204], [900, 140], [932, 204]], name: '', loop: true },
  ca3_ca1: { p: [[988, 246], [1086, 268], [1088, 380]], name: 'Schaffer collaterals', at: [1102, 300], align: 'left' },
  ca1_sub: { p: [[1000, 420], [900, 470], [796, 478]], name: '', },
  sub_ec: { p: [[600, 482], [450, 478], [310, 420]], name: '' },
  ecd_ecu: { p: [[272, 420], [300, 352], [272, 300]], name: '' },
  ecd_neo: { p: [[96, 420], [40, 260], [96, 128]], name: '' },
  brk_dg: { p: [[543, 300], [543, 284], [543, 262]], name: '', inh: true },
};
const qpt = (p, u) => { const v = 1 - u; return [v * v * p[0][0] + 2 * v * u * p[1][0] + u * u * p[2][0], v * v * p[0][1] + 2 * v * u * p[1][1] + u * u * p[2][1]]; };
const LOOP_PATH = ['ec_dg', 'dg_ca3', 'ca3_ca1', 'ca1_sub', 'sub_ec', 'ecd_ecu'];
/* what each moment of the map lights: [from, to, arc or node, kind] */
const MAP_STEPS = [
  { t: 4.8, arcs: ['neo_ec', 'ec_dg'], nodes: ['neo', 'ecu', 'dg'] },
  { t: 9.9, arcs: ['ec_dg', 'brk_dg'], nodes: ['dg', 'brk'] },
  { t: 15.0, arcs: ['dg_ca3', 'ca3_rec', 'ca3_ca1'], nodes: ['ca3', 'ca1'] },
  { t: 19.3, arcs: ['ca1_sub'], nodes: ['sub'] },
  { t: 23.2, arcs: ['sub_ec', 'ecd_neo', 'ecd_ecu'], nodes: ['ecd', 'ecu', 'neo'] },
];
const MAP_PULSES = [ // [start, arc, duration]
  [5.2, 'neo_ec', 0.9], [6.4, 'ec_dg', 1.1], [7.9, 'ec_dg', 1.1],
  [10.2, 'ec_dg', 1.1], [11.3, 'brk_dg', 0.6], [12.6, 'ec_dg', 1.1], [13.7, 'brk_dg', 0.6],
  [15.2, 'dg_ca3', 1.0], [16.3, 'ca3_rec', 0.9], [17.3, 'ca3_ca1', 1.1],
  [19.6, 'ca1_sub', 1.2],
  [23.4, 'sub_ec', 1.3], [24.9, 'ecd_neo', 1.2], [26.1, 'ecd_ecu', 0.9],
];
const LAPS = { t0: 28.4, durs: [2.9, 2.3, 1.85, 1.5, 1.25] };
function lapAt(t) {
  let s = LAPS.t0;
  for (let i = 0; i < LAPS.durs.length; i++) { const d = LAPS.durs[i]; if (t < s + d) return { i, u: (t - s) / d, s }; s += d; }
  return null;
}
function drawMap(c, t, a) {
  c.save(); c.globalAlpha = a;
  c.fillStyle = 'rgb(5,8,12)'; c.fillRect(0, 0, VW, VH);
  const vg = c.createRadialGradient(VW * 0.55, VH * 0.45, 80, VW * 0.55, VH * 0.45, 760); vg.addColorStop(0, 'rgba(40,52,66,0.35)'); vg.addColorStop(1, 'rgba(5,8,12,0)');
  c.fillStyle = vg; c.fillRect(0, 0, VW, VH);
  const lapNow = t >= LAPS.t0 ? lapAt(t) : null, laps = t >= LAPS.t0;
  const heat = laps ? clamp((t - LAPS.t0) / 7, 0, 1) : 0;
  const step = MAP_STEPS.filter((s) => t >= s.t).pop();
  const litN = new Set(step ? step.nodes : []), litA = new Set(step ? step.arcs : []);
  const appear = (i) => fade(t, 0.4 + i * 0.32, 99, 0.5);
  // the hippocampus, as one: a dashed line round its four parts
  c.globalAlpha = a * fade(t, 1.4, 99, 0.8);
  rrect(c, 414, 126, 792, 408, 22); c.setLineDash([6, 6]); c.strokeStyle = 'rgba(200,215,228,0.26)'; c.lineWidth = 1.3; c.stroke(); c.setLineDash([]);
  text(c, 'The hippocampus', 434, 148, { size: 13, w: 650, color: 'rgba(214,226,236,0.62)', halo: false });
  c.globalAlpha = a;
  // the arrows
  Object.entries(ARC).forEach(([k, A], i) => {
    const on = laps ? (LOOP_PATH.includes(k) || k === 'ca3_rec') : litA.has(k);
    const ap = fade(t, 2.4 + i * 0.12, 99, 0.6);
    if (ap <= 0.001) return;
    const brkOff = laps && (k === 'brk_dg');
    c.globalAlpha = a * ap * (brkOff ? 0.25 : on ? 1 : 0.38);
    const col = on ? (laps ? 'rgb(' + R.ramp(0.55 + 0.4 * heat).join(',') + ')' : '#eef2f5') : 'rgba(200,210,220,0.75)';
    c.strokeStyle = A.inh ? C.hil : col; c.lineWidth = on ? 2.4 : 1.6;
    if (k === 'ecd_neo' && !on) c.setLineDash([5, 5]);
    c.beginPath(); c.moveTo(A.p[0][0], A.p[0][1]); c.quadraticCurveTo(A.p[1][0], A.p[1][1], A.p[2][0], A.p[2][1]); c.stroke();
    c.setLineDash([]);
    // the head: an arrow, or a bar for inhibition
    const e = A.p[2], b = qpt(A.p, 0.9), ang = Math.atan2(e[1] - b[1], e[0] - b[0]);
    c.fillStyle = A.inh ? C.hil : col;
    c.save(); c.translate(e[0], e[1]); c.rotate(ang);
    if (A.inh) c.fillRect(-2, -9, 4, 18); else { c.beginPath(); c.moveTo(1, 0); c.lineTo(-11, -6); c.lineTo(-11, 6); c.closePath(); c.fill(); }
    c.restore();
    if (A.name && A.at) { c.globalAlpha = a * ap * (on ? 0.95 : 0.55); text(c, A.name, A.at[0], A.at[1], { size: 12.5, w: 600, align: A.align || 'center', color: C.text2, halo: false }); }
  });
  // the boxes
  const order = ['ecu', 'ecd', 'dg', 'ca3', 'ca1', 'sub', 'neo', 'brk'];
  order.forEach((k, i) => {
    const n = NODE[k], ap = appear(k === 'ecd' ? 0 : i);
    if (ap <= 0.001) return;
    const brkOff = laps && k === 'brk';
    const on = laps ? !brkOff && k !== 'neo' : litN.has(k);
    c.globalAlpha = a * ap * (brkOff ? 0.5 : 1);
    const hot = laps && on ? 0.25 + 0.6 * heat * (0.75 + 0.25 * Math.sin(t * 6 + i)) : 0;
    rrect(c, n.x, n.y, n.w, n.h, 10);
    c.fillStyle = hot > 0 ? 'rgba(' + R.ramp(0.35 + 0.4 * heat).join(',') + ',' + (0.16 + 0.3 * hot).toFixed(3) + ')' : on ? 'rgba(30,40,52,0.96)' : 'rgba(16,22,30,0.92)';
    c.fill();
    c.strokeStyle = on ? n.col : 'rgba(255,255,255,0.16)'; c.lineWidth = on ? 2 : 1;
    if (on) { c.shadowColor = n.col; c.shadowBlur = 14; }
    c.stroke(); c.shadowBlur = 0;
    // the accent bar in the region's colour
    c.fillStyle = n.bar; c.fillRect(n.x + 1, n.y + 8, 4, n.h - 16);
    if (k === 'ecu' || k === 'ecd') {
      const lab = k === 'ecu' ? ['upper layers (II, III)', 'gather input, send it in'] : ['deep layers (V)', 'take the output back'];
      text(c, lab[0], n.x + 18, n.y + n.h / 2 - 9, { size: 15, w: 650, color: on ? C.text : C.text2, halo: false });
      text(c, lab[1], n.x + 18, n.y + n.h / 2 + 12, { size: 12.5, w: 500, color: C.text3, halo: false });
    } else if (k === 'brk') {
      text(c, 'hilus: brake cells', n.x + 16, n.y + n.h / 2, { size: 13.5, w: 650, color: C.hil, halo: false });
      if (brkOff) { c.strokeStyle = '#ff6a4a'; c.lineWidth = 2.4; c.beginPath(); c.moveTo(n.x + 8, n.y + 6); c.lineTo(n.x + n.w - 8, n.y + n.h - 6); c.stroke(); }
    } else {
      text(c, n.name, n.x + 18, n.y + n.h / 2, { size: 18, w: 700, color: on ? n.col : C.text, halo: false });
    }
  });
  // the entorhinal cortex's name, over its two halves, and the line between them
  c.globalAlpha = a * appear(0);
  text(c, 'Entorhinal cortex', NODE.ecu.x + 2, NODE.ecu.y - 16, { size: 18, w: 700, color: C.ec, halo: false });
  c.strokeStyle = 'rgba(255,255,255,0.14)'; c.lineWidth = 1; c.beginPath(); c.moveTo(NODE.ecu.x + 10, NODE.ecd.y); c.lineTo(NODE.ecu.x + NODE.ecu.w - 10, NODE.ecd.y); c.stroke();
  c.globalAlpha = a;
  // the pulses: a bright bead and its trail along an arrow
  const bead = (A, u, col, sz) => {
    for (let j = 0; j < 7; j++) {
      const uu = u - j * 0.035;
      if (uu < 0 || uu > 1) continue;
      const q = qpt(A.p, uu), r = (sz || 1) * (5.5 - j * 0.6);
      c.globalAlpha = a * (1 - j / 7);
      c.drawImage(tinted(col), q[0] - r * 3, q[1] - r * 3, r * 6, r * 6);
    }
    c.globalAlpha = a;
  };
  if (!laps) {
    MAP_PULSES.forEach(([s, k, d]) => { const u = (t - s) / d; if (u >= 0 && u <= 1.15) bead(ARC[k], Math.min(1, u), ARC[k].inh ? C.hil : '#fff2d0', ARC[k].inh ? 0.8 : 1); });
  } else if (lapNow) {
    const seg = Math.floor(lapNow.u * LOOP_PATH.length), su = lapNow.u * LOOP_PATH.length - seg;
    bead(ARC[LOOP_PATH[Math.min(seg, LOOP_PATH.length - 1)]], su, 'rgb(' + R.ramp(0.7 + 0.3 * heat).join(',') + ')', 1 + 0.5 * heat);
  }
  c.restore();
}
const MAP_CAPS = [
  [0.4, 4.6, 'Past the probe, nothing was recorded. To follow the seizure further, here is the circuit it can travel, as a map.'],
  [4.8, 9.7, 'The entorhinal cortex is the hippocampus’s front door: its upper layers gather signals from across the cortex and send them in.'],
  [9.9, 14.8, 'In the dentate gyrus, granule cells receive them while the hilus’s brake cells keep most of them quiet. The dentate gyrus is a gate.'],
  [15.0, 19.1, 'What gets through goes to CA3, whose cells excite one another, and on to CA1.'],
  [19.3, 23.0, 'CA1 hands it to the subiculum, the hippocampus’s main exit.'],
  [23.2, 28.2, 'The subiculum sends it back to the entorhinal cortex’s deep layers, which pass it out to the cortex and up to the front door again: a loop.'],
  [28.4, 34.8, 'In a seizure, we think the brakes fail. Nothing stops the activity at the gate, so it goes around again and again, each lap stronger.', 'Our hypothesis'],
];
scene({ name: 'loopmap', dur: 35, chap: 8, tag: [[0, 28.3, 'map'], [28.3, 35, 'hyp']], xin: 0.9, mood: 'loop', cap: MAP_CAPS,
  sfx: (add) => {
    MAP_PULSES.forEach(([s, k], i) => add(s, 'pluck', { gain: k === 'brk_dg' ? 0.25 : 0.4, pitch: [0, 4, 7, 9, 12][i % 5] }));
    let s = LAPS.t0;
    LAPS.durs.forEach((d, i) => { for (let j = 0; j < LOOP_PATH.length; j++) add(s + d * j / LOOP_PATH.length, 'pluck', { gain: 0.3 + 0.06 * i, pitch: [-3, 0, 4, 7, 9, 12][j] }); s += d; });
    add(LAPS.t0, 'swell', { gain: 0.6, dur: 6.5 });
  },
  enter() { go(FS.hpf); },
  update() { },
  post(c, t) { drawMap(c, t, fade(t, 0, 99, 0.6)); },
});
/* the same loop on the hippocampus itself, one hop at a time, then lap after lap */
const LOOP_REG = ['DG', 'CA3', 'CA2', 'CA1', 'SUB', 'ProS', 'ENTm', 'ENTl'];
const loopPt = (k) => {
  const g = P().geo, lay = { DG: ['hil'], CA3: ['ca3sp'], CA1: ['ca1sp'] }[k];
  const c = lay && planeCentre(lay, g.ap);
  return c ? W3(c[0], c[1], c[2]) : hpfW(k);
};
const HOPS = [['ENTm', 'DG'], ['DG', 'CA3'], ['CA3', 'CA1'], ['CA1', 'SUB'], ['SUB', 'ENTm']];
const HOP_T = [0.9, 1.9, 2.9, 3.9, 4.9], LAP3 = [6.6, 8.9, 10.8, 12.4];
let loopFx = null;
scene({ name: 'loop3d', dur: 14, chap: 8, tag: 'hyp', xin: 1.0, mood: 'loop',
  cap: [[0.4, 6.4, 'Here is that loop in the mouse’s hippocampus.', 'Drawn, not recorded: the probe saw only CA1 and the dentate gyrus.'],
        [6.6, 13.8, 'Lap after lap, more of the hippocampus is drawn in.']],
  sfx: (add) => { HOP_T.forEach((h, i) => add(h, 'pluck', { gain: 0.38, pitch: [0, 4, 7, 9, 12][i] })); LAP3.forEach((h, i) => add(h, 'bloom', { gain: 0.35 + 0.08 * i, pitch: [-3, 0, 4, 7][i] })); },
  enter() { camFrom = null; loopFx = { fired: new Set() }; if (P().stop.key !== 'film_hpf') go(FS.hpf); },
  update(t) {
    hold3d(t, [0.7, 0.5, -0.5], 13.2, [2.4, -0.7, 1.4]);
    if (P().stop.key !== 'film_hpf') return;
    if (!loopFx.setup) {
      loopFx.setup = true;
      cellsH().forEach((c) => S.stage.setVisible('cells', c.key, false));
      S.stage.focus({ cells: new Set(), regions: new Set(LOOP_REG), layers: new Set() });
    }
    const st = S.stage, fire = (id, at, fn) => { if (t >= at && !loopFx.fired.has(id)) { loopFx.fired.add(id); fn(); } };
    const hop = ([a, b], col, ms, size) => { const A = loopPt(a), Bp = loopPt(b); if (A && Bp) st.volley(A, Bp, col, ms, { size, lift: 0.55 }); };
    // one hop at a time, each named as it lands
    HOPS.forEach((h, i) => fire('h' + i, HOP_T[i], () => hop(h, '#ffd9a0', 1000, 1.1)));
    // then laps, each quicker and hotter than the last: a hop leaves every fifth of a lap
    LAP3.forEach((l, li) => {
      const lap = (LAP3[li + 1] || l + 1.4) - l, gap = lap / HOPS.length;
      HOPS.forEach((h, i) => fire('l' + li + '_' + i, l + i * gap, () => hop(h, 'rgb(' + R.ramp(0.62 + 0.1 * li).join(',') + ')', gap * 2000, 1.0 + 0.25 * li)));
    });
    const k = t < LAP3[0] ? 0.12 * smooth(t / 5) : 0.12 + 0.5 * smooth((t - LAP3[0]) / 7);
    const flick = 0.85 + 0.15 * Math.sin(t * 7.3) * Math.sin(t * 2.1);
    const h = {}; LOOP_REG.forEach((r) => { h[r] = k * flick; });
    st.setHeat(h, '#ff6a2a');
  },
  post(c, t) {
    const lab = [['ENTm', 'Entorhinal cortex', C.ec, -36, 36], ['DG', 'Dentate gyrus', C.gc, 34, -36], ['CA3', 'CA3', C.ca3, 34, 32], ['CA1', 'CA1', C.ca1, -28, -34], ['SUB', 'Subiculum', C.sub, -34, -32]];
    lab.forEach(([k, s, col, dx, dy], i) => pin3(c, loopPt(k), s, { alpha: fade(t, (i ? HOP_T[i - 1] + 0.85 : 0.5), 14.2, 0.5, 0.3), color: col, dx, dy }));
  },
  exit() {
    cellsH().forEach((c) => S.stage.setVisible('cells', c.key, true));
    S.stage.focus(null); S.stage.setHeat(null);
  },
});
let camFrom = null;
function hold3d(t, dir0, dist, tgt) {
  if (t < 0.05 || !camFrom) camFrom = S.stage.getCam();
  const u = ease(t / 1.8);
  const pos = lerp3(camFrom.pos, add(tgt, norm(dir0), dist), u), tg = lerp3(camFrom.target, tgt, u);
  if (t < 1.8) camAt(pos, tg);
  else look(tgt, yaw(dir0, (t - 1.8) * 1.3), dist);
}

/* ---- across the brain, a step at a time ---- */
const GSTEP = { hip: 0, neo: 8.6, other: 17.4, th: 25.6, mo: 34.4, bs: 43.6, end: 53 };
const GCAP = [
  [0.4, 8.2, 'The seizure need not stay in the hippocampus. Here is how a seizure like this one can spread across the brain.', 'What is known about how seizures spread; none of it was recorded in this mouse.'],
  [8.6, 17.0, 'Out through the entorhinal cortex, it reaches the neocortex, the brain’s outer layer.'],
  [17.4, 25.2, 'A bridge of fibers carries it across to the hippocampus on the other side.'],
  [25.6, 34.0, 'Deep in the middle, the thalamus is wired to the whole cortex. Once it joins, both halves of the brain can seize together.'],
  [34.4, 43.2, 'When it reaches the motor cortex, which moves the body, the body jerks in time with it: a convulsive seizure.', 'No video was recorded with this seizure, so we can’t say what mouse 459’s body did.'],
  [43.6, 52.8, 'If it reaches the brainstem, which holds the body’s posture, the whole body stiffens: the tonic part of a big seizure.'],
];
let gfx = null;
const gKeys = () => {
  const hip = hpfW('DG') || [2.4, 1.2, 1.4], th = allenW('TH', 'r') || [1, 0.4, 0.2], mo = allenW('MOp', 'r') || [1.5, 2.5, -2], bs = allenW('P', 'r') || [0.4, -1.8, 2.6];
  return [
    [GSTEP.hip, lerp3([0, -0.4, 0.6], hip, 0.35), [0.92, 0.3, 0.26], 19.5],
    [GSTEP.neo, [0, -0.3, 0.3], [0.9, 0.38, 0.2], 21.5],
    [GSTEP.other, [0, 0.6, 1.9], [0.05, 0.86, 0.5], 18.5],
    [GSTEP.th, lerp3([0, -0.2, 0.4], th, 0.6), [0.94, 0.12, 0.3], 19],
    [GSTEP.mo, [0, mo[1] * 0.7, mo[2] + 0.9], [0.14, 0.93, -0.34], 16.5],
    [GSTEP.bs, lerp3([0, -1.6, 2.2], bs, 0.5), [0.78, -0.12, 0.62], 19.5],
  ];
};
let GKEYS = null;
scene({ name: 'global', dur: 53.4, chap: 9, tag: 'book', xin: 1.0, mood: 'spread', cap: GCAP,
  sfx: (add) => {
    [GSTEP.neo, GSTEP.other, GSTEP.th, GSTEP.mo, GSTEP.bs].forEach((s, i) => { add(s - 1.0, 'whoosh', { gain: 0.75, dur: 2.0 }); add(s + 0.2, 'bloom', { gain: 0.5, pitch: [3, 10, 8, 5, 7][i], low: true }); });
    for (let k = 0; k < 16; k++) add(GSTEP.mo + 1.2 + k / 2.0, 'thud', { gain: 0.3 + 0.2 * Math.min(1, k / 6) });
    add(GSTEP.bs + 0.6, 'swell', { gain: 0.75, dur: 8.5 });
  },
  enter() { gfx = { fired: new Set() }; go(FS.brain); GKEYS = null; },
  update(t) {
    if (P().stop.key !== 'film_brain') return;
    if (!GKEYS) GKEYS = gKeys();
    camKeys(t, GKEYS, 1.9);
    const st = S.stage, k = (s, d) => smooth((t - s) / (d || 2.5));
    const fire = (id, at, fn) => { if (t >= at && !gfx.fired.has(id)) { gfx.fired.add(id); fn(); } };
    // the hippocampus, seizing all along
    const hh = 0.35 + 0.15 * Math.sin(t * 5.1) * Math.sin(t * 1.7);
    st.setHeat({ DG: hh, CA3: hh, CA2: hh, CA1: hh, SUB: hh * 0.9, ProS: hh * 0.8, ENTm: hh * 0.8 * k(GSTEP.neo - 1), ENTl: hh * 0.8 * k(GSTEP.neo - 1) }, '#ff6a2a');
    const ec = hpfW('ENTl') || hpfW('ENTm');
    // the neocortex: waves out of the entorhinal cortex
    ['SSp', 'MOp', 'AUD', 'VISp', 'RSP', 'ACA'].forEach((n, i) => [0, 3.4].forEach((d, j) => fire('neo' + n + j, GSTEP.neo + 0.5 + d + i * 0.26, () => { const b = allenW(n, 'r'); if (ec && b) st.volley(ec, b, '#ff9a4a', 1350, { size: 1.15, lift: 0.4 }); })));
    // across to the other hippocampus
    [0, 2.6].forEach((d, j) => fire('com' + j, GSTEP.other + 1.0 + d, () => { const a = hpfW('DG'), b = hpfW('DG', 'l'); if (a && b) st.volley(a, b, '#ffc07a', 1500, { size: 1.25, lift: 0.5 }); }));
    // the motor cortex, flashing with each jerk, both sides
    for (let k = 0; k < 16; k++) fire('jerk' + k, GSTEP.mo + 1.2 + k / 2.0, () => ['r', 'l'].forEach((s) => { const p = allenW('MOp', s); if (p) st.flareAt(p, '#ffe9b8', 560); }));
    // the thalamus, both ways with the cortex
    [0, 2.8].forEach((d, j) => {
      fire('th' + j, GSTEP.th + 0.8 + d, () => { const th = allenW('TH', 'r'), a = hpfW('SUB') || hpfW('DG'); if (th && a) st.volley(a, th, '#ffb060', 1250, { size: 1.1, lift: 0.3 }); });
      ['SSp', 'MOp', 'ACA', 'VISp'].forEach((n, i) => fire('tc' + n + j, GSTEP.th + 1.9 + d + i * 0.18, () => { const th = allenW('TH', 'r'), b = allenW(n, i % 2 ? 'l' : 'r'); if (th && b) st.volley(th, b, '#ffb060', 1200, { size: 1.0, lift: 0.35 }); }));
    });
    const cortex = 0.1 + 0.5 * k(GSTEP.neo + 0.8, 4) + 0.15 * k(GSTEP.th + 1.5, 4);
    const glow = { Isocortex: { color: '#ff7a2f', a: cortex * (t > GSTEP.mo ? 0.75 : 1) } };
    if (t > GSTEP.th) glow.TH = { color: '#ffb35c', a: 0.15 + 0.55 * k(GSTEP.th + 0.6, 3) };
    if (t > GSTEP.bs) { const sb = 0.12 + 0.6 * k(GSTEP.bs + 0.5, 3) * (0.9 + 0.1 * Math.sin(t * 4.4)); glow.MB = { color: '#ffd27a', a: sb }; glow.P = { color: '#ffd27a', a: sb }; glow.MY = { color: '#ffd27a', a: sb }; }
    st.glowBrain(glow);
  },
  post(c, t) {
    if (P().stop.key !== 'film_brain') return;
    // the motor cortex: its surface, lit in time with the jerks
    const km = fade(t, GSTEP.mo + 0.6, GSTEP.end, 0.8, 0.6);
    if (km > 0.01) {
      const ph = ((t - GSTEP.mo - 1.2) * 2.0) % 1, kick = t > GSTEP.mo + 1.2 ? Math.exp(-ph * 4.5) : 0;
      const pts = allenTop('MOp'), spr = tinted('#fff0c2');
      c.save(); c.globalCompositeOperation = 'lighter';
      // ~90 stamps overlap at any point of the patch: each one faint
      c.globalAlpha = km * (0.005 + 0.014 * kick) * (t > GSTEP.bs ? 0.6 : 1);
      for (const w of pts) { const p = proj(w); if (p[2] > 1) continue; c.drawImage(spr, p[0] - 15, p[1] - 15, 30, 30); }
      c.restore();
    }
    const a = (s, e) => fade(t, s, e == null ? GSTEP.end : e, 0.6, 0.5);
    pin3(c, hpfW('DG'), 'Hippocampus', { alpha: a(0.8, GSTEP.other + 0.4), color: '#ffd27f', dx: 30, dy: 44 });
    pin3(c, hpfW('ENTl') || hpfW('ENTm'), 'Entorhinal cortex', { alpha: a(GSTEP.neo + 0.2, GSTEP.other), color: C.ec, dx: 36, dy: 40 });
    pin3(c, allenW('SSp', 'r'), 'Neocortex', { alpha: a(GSTEP.neo + 1.0, GSTEP.other + 0.2), color: '#ffb36b', dx: 34, dy: -38 });
    pin3(c, hpfW('DG', 'l'), 'The other hippocampus', { alpha: a(GSTEP.other + 1.8, GSTEP.th), color: '#ffd27f', dx: -34, dy: -38 });
    pin3(c, hpfW('DG'), 'Hippocampus', { alpha: a(GSTEP.other + 0.6, GSTEP.th), color: '#ffd27f', dx: 34, dy: -38 });
    pin3(c, allenW('TH', 'r'), 'Thalamus', { alpha: a(GSTEP.th + 1.0, GSTEP.mo), color: '#ffc98a', dx: 38, dy: 38 });
    pin3(c, allenW('MOp', 'r'), 'Motor cortex', { alpha: a(GSTEP.mo + 1.0, GSTEP.bs + 0.3), color: '#ffd98a', dx: 40, dy: -40 });
    pin3(c, allenW('MOp', 'l'), 'Motor cortex', { alpha: a(GSTEP.mo + 1.3, GSTEP.bs + 0.3), color: '#ffd98a', dx: -40, dy: -40 });
    pin3(c, allenW('P', 'r'), 'Brainstem', { alpha: a(GSTEP.bs + 1.0), color: '#ffe3a0', dx: 40, dy: 40 });
  },
  exit() { S.stage.glowBrain(null); S.stage.setHeat(null); },
});
scene({ name: 'next', dur: 8.6, chap: 10, tag: 'next', xin: 0.9, mood: 'hope',
  cap: [[0.5, 8.4, 'Our next question: if we pace these brake cells with light, can we keep a stumble from becoming a seizure?']],
  enter() { go(FS.opto); },
  update() { setSlice(frProbe(0.42)); },
  post(c, t) {
    drawShank(c, { alpha: 1, size: 15.5, lit: new Set(['hil']) });
    const g = P().geo, h = g.zones.hil, q = toPx(g.ap, (h.dv0 + h.dv1) / 2 + 10, g.ml + 430);
    pin(c, q[0], q[1], 'Light on the hilus', { alpha: fade(t, 1.0, 99, 0.6), color: C.next, dx: 120, dy: 92, sub: 'paced at a steady rhythm' });
  },
});
scene({ name: 'end', dur: 22, scrim: 0, mood: 'hope',
  card: ['End card', 'SEE YOU IN DENVER', 'Come chat with us', 'at the 2026 KCNT1 Family & Professional Conference', 'December 3–4, 2026 · Grand Hyatt Denver',
    'Scientific Roundtable Dec 3 · Family Conference Dec 4', 'Epilepsy Cognition Development Lab, Larner College of Medicine, University of Vermont',
    '[the conference’s “Rising Higher Together” artwork, from kcnt1epilepsy.org]',
    'Credits: Recording: Kcnt1 Y777H mouse 459 (two copies), awake, 64-contact silicon probe through CA1 and the dentate gyrus. Beyond the probe: drawn, not recorded (the loop is our hypothesis; the spread across the brain is the textbook). Anatomy: Allen Mouse Brain Common Coordinate Framework (CCFv3). Neuron tracings: Janelia MouseLight and NeuroMorpho.Org. Colors as on our KCNT1 poster. Made with Seahorse.'], sfx: [[-0.1, 'whoosh', { gain: 0.6, dur: 2.0 }], [0.1, 'swell', { gain: 0.5, dur: 6 }]],
  update(t) {
    show(el.end, fade(t, 0, 99, 1.0));
    show(el.black, smooth((t - 20.2) / 1.7));
  },
});
let T = 0;
SC.forEach((s) => { s.t0 = T; T += s.dur; });
// the chapter stays up across scenes that share it
SC.forEach((s, i) => {
  let j = i; while (j > 0 && SC[j - 1].chap === s.chap) j--; s.chapIn = SC[j].t0 + (j === i && s.chap ? 0.2 : 0);
  let k = i; while (k < SC.length - 1 && SC[k + 1].chap === s.chap) k++; s.chapOut = SC[k].t0 + SC[k].dur - 0.2;
});
// the tags, in film time, merged where one runs on into the next scene
SC.forEach((s) => {
  const segs = !s.tag ? [] : typeof s.tag === 'string' ? [[0, s.dur, s.tag]] : s.tag;
  segs.forEach(([a, b, k]) => {
    const last = TAGLINE[TAGLINE.length - 1], A = s.t0 + a, Bt = s.t0 + b;
    if (last && last[2] === k && Math.abs(last[1] - A) < 0.05) last[1] = Bt; else TAGLINE.push([A, Bt, k]);
  });
});
F.total = T;
F.scenes = SC.map((s) => ({ name: s.name, t0: +s.t0.toFixed(3), dur: s.dur, mood: s.mood || '' }));
// the words, in order, with their times in the film (for proofreading, or a narrator)
F.script = () => SC.flatMap((s) => (s.card ? [{ scene: s.name, chapter: s.chap ? CHAPTERS[s.chap - 1] : '', from: +s.t0.toFixed(1), to: +(s.t0 + s.dur).toFixed(1), card: s.card }] : [])
  .concat((s.cap || []).map((c) => ({ scene: s.name, chapter: s.chap ? CHAPTERS[s.chap - 1] : '', from: +(s.t0 + c[0]).toFixed(1), to: +(s.t0 + c[1]).toFixed(1), main: c[2], sub: c[3] || '' }))));
F.frames = Math.round(T * FPS);
/* the sound: a whoosh wherever the picture changes its angle, the scenes' own effects, the music's moods */
F.cues = () => {
  const out = [];
  const addAt = (t, kind, o) => out.push(Object.assign({ t: +t.toFixed(3), kind }, o || {}));
  SC.forEach((s, i) => {
    if (i && s.xin) addAt(s.t0 - 0.1, 'whoosh', { gain: 0.85, dur: 1.6 + s.xin });
    const fx = typeof s.sfx === 'function' ? (() => { const l = []; s.sfx((t, k, o) => l.push([t, k, o])); return l; })() : (s.sfx || []);
    fx.forEach(([t, k, o]) => addAt(s.t0 + t, k, o));
  });
  out.sort((a, b) => a.t - b.t);
  return { total: F.total, fps: FPS, scenes: F.scenes, cues: out };
};

/* ------------------------------------------------------------ the clock */
function sceneAt(t) { for (const s of SC) if (t >= s.t0 - 1e-9 && t < s.t0 + s.dur - 1e-9) return s; return SC[SC.length - 1]; }
let xf = null;
F.tick = (t) => {
  F.t = t;
  const sc = sceneAt(t);
  if (F.cur !== sc) {
    if (F.cur && F.cur.exit) F.cur.exit();
    F.cur = sc;
    if (sc.xin && F.frame > 0) xf = { t0: t, dur: sc.xin };
    if (sc.enter) sc.enter();
  }
  const lt = t - sc.t0;
  if (sc.update) sc.update(lt);
  hud(sc, lt);
};
F.post = (t) => {
  const sc = F.cur, lt = t - sc.t0;
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  ctx.clearRect(0, 0, VW, VH);
  if (sc.post) sc.post(ctx, lt);
  // a cross-fade from the last frame of the scene before
  if (xf) {
    const k = (t - xf.t0) / xf.dur;
    if (k >= 1) { xf = null; frz.style.opacity = 0; } else frz.style.opacity = (1 - smooth(k)).toFixed(3);
  }
  // the last frame of a scene is kept for the next one's cross-fade
  const nx = sceneAt(t + 1 / FPS + 1e-6);
  if (nx !== sc && nx.xin) {
    fctx.setTransform(1, 0, 0, 1, 0, 0);
    fctx.clearRect(0, 0, frz.width, frz.height);
    fctx.fillStyle = 'rgb(5,8,12)'; fctx.fillRect(0, 0, frz.width, frz.height);
    const sc3 = document.querySelector('.sh3-canvas');
    if (sc3) fctx.drawImage(sc3, 0, 0, frz.width, frz.height);
    fctx.drawImage(cv, 0, 0);
  }
};
F.init = async (assets) => {
  build(assets);
  // no drawn pathways (the perforant and temporoammonic bundles): the film draws its own arcs. In memory only, not saved.
  S.paths = false;
  makeStops();
  allenCentres();
  return { total: F.total, frames: F.frames, scenes: F.scenes };
};
/* one frame: the clocks move on, the film sets up the frame, the page draws it */
F.step = async () => {
  const t = F.frame / FPS;
  if (F.frame > 0) V.advance(DT);
  F.tick(t);
  V.frame();
  F.post(t);
  await V.settle(2);
  if (F.waitStory) {
    const t0 = V.real.now();
    while (P() && P().moving && V.real.now() - t0 < 5000) await V.settle(1);
    F.waitStory = false;
    if (F.after) { const f = F.after; F.after = null; f(); }
    // the new stop is set up: draw this frame again with it
    F.tick(t); V.frame(); F.post(t);
    await V.settle(1);
  }
  F.frame++;
  return { t: +t.toFixed(3), scene: F.cur.name, errors: V.errors.length };
};
F.seekScene = (name) => { const s = SC.find((x) => x.name === name); F.frame = Math.round(s.t0 * FPS); F.cur = null; return F.frame; };
})();
