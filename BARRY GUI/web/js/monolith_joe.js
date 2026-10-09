/* ==========================================================================
   monolith_joe.js -- the Monolith page's eighth tab: Joe's data.

   The tests Joe's dissertation proposal names, and nothing more (the lab,
   2026-10-06, "the middle path"; Shahriar's 25 answers of 2026-10-09):
   coherence between regions, theta 5-12 Hz and gamma 30-90 Hz, Precon1
   against Precon4, in a handful of planned comparisons; the follow-ups only
   where those pass; the SPSS files and a standalone script that reproduces
   them without Jarvis. backend/joe.py makes the numbers (joe.json).

   One line a card, then ▸ More, with something to play with in place of
   paragraphs: the windows on a trial, the mains and its harmonics, and the
   old Minus FP against this tab's FP comparison. Load order: after
   monolith.js and monolith_explain.js.
   ========================================================================== */
'use strict';

window.MONO_JOE = (function () {
  const M = () => window.MONO;
  const X = () => window.MONO_EXPLAIN;
  const NS = 'http://www.w3.org/2000/svg';
  const P = { data: null, err: null, loading: false, band: 'theta', method: 'welch', seq: 0,
              making: false, makeNote: '', makeErr: null, scripting: false, scriptNote: '', scriptErr: null };
  const $ = (id) => document.getElementById(id);
  const el = (...a) => M().el(...a);
  function sv(tag, attrs, text) {
    const n = document.createElementNS(NS, tag);
    for (const k in (attrs || {})) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || '#888';
  const sig = (v) => M().sig(v), f3 = (v) => M().f3(v), fp = (v) => M().fp(v);
  const fmt = (n) => (n == null ? '—' : Number(n).toLocaleString('en-US'));
  const reduced = () => { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } };
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const lerp = (a, b, t) => a + (b - a) * t;
  const ALPHA = 0.05;
  const FILE = (name) => (window.MONO_STATIC ? 'data/joe/' + name : '/api/arc/monolith/joe/file/' + encodeURIComponent(name));

  function section(id, title, help, kids) {
    return el('div', { class: 'card', id }, [el('div', { class: 'hrow' }, [el('h2', { text: title }), help ? M().qh(help) : null])].concat(kids));
  }
  function seg(list, cur, pick, id) {
    const g = M().seg(list, cur, pick, id);
    g.id = id;
    return g;
  }
  const fmtF = (t) => (t && t.F != null ? 'F(' + t.df1 + ', ' + t.df2 + ') = ' + (t.F >= 100 ? t.F.toFixed(0) : t.F.toFixed(2)) + ', p ' + fp(t.p) : '—');
  const unitWord = (m) => (m.unit === 'pair' ? 'Pair' : 'Region');
  const three = (m) => 'Day × ' + m.factor + ' × ' + unitWord(m);
  const two = (m) => 'Day × ' + m.factor;
  const modelOf = (id) => (P.data.models || []).find((m) => m.id === id);
  const resOf = (mid, band, method) => (P.data.results || []).find((r) => r.model === mid && r.band === band
    && (r.method === method || modelOf(mid).unit === 'region'));

  /* ---------------- data ---------------- */
  async function load() {
    const seq = ++P.seq;
    P.loading = true;
    render();
    try {
      const got = await M().getJSON('/data/joe');
      if (seq !== P.seq) return;
      P.data = got;
      P.err = null;
    } catch (e) {
      if (seq !== P.seq) return;
      P.data = null;
      P.err = e.message;
    }
    P.loading = false;
    render();
  }
  async function make(what) {
    const script = what === 'script';
    if (script ? P.scripting : P.making) return;
    if (script) { P.scripting = true; P.scriptErr = null; P.scriptNote = ''; } else { P.making = true; P.makeErr = null; P.makeNote = ''; }
    render();
    try {
      await M().runHere('/joe', { confirm: true, what: script ? 'script' : 'joe' }, (note) => {
        if (script) P.scriptNote = note; else P.makeNote = note;
        const b = $(script ? 'joescriptrun' : 'joemake');
        if (b) b.textContent = (script ? 'Running the script: ' : 'Working: ') + note;
      });
    } catch (e) {
      const msg = /404|not found/i.test(e.message) ? 'Jarvis is running older code without this button: restart it, then press it again.'
        : 'It could not be done: ' + e.message;
      if (script) P.scriptErr = msg; else P.makeErr = msg;
    }
    if (script) P.scripting = false; else P.making = false;
    load();
  }

  /* ---------------- the answer ---------------- */
  // Every model x band x method: the test of interest's p, and Day x factor's
  // beneath it; a cell that opens follow-ups is marked.
  function answerTable() {
    const D = P.data;
    const cols = [];
    for (const b of D.bands) for (const m of D.methods) cols.push([b, m]);
    const head = el('tr', {}, [el('th', { text: 'Model' })].concat(cols.map(([b, m]) => el('th', {}, [
      el('div', { text: b.label }), el('div', { class: 'small muted', text: m.id === 'welch' ? 'Welch' : 'Dickson' })]))));
    const row = (m) => el('tr', { 'data-model': m.id, class: m.kind }, [el('th', {}, [el('div', { text: m.label }),
      el('div', { class: 'small muted', text: m.kind === 'check' ? 'check · expected null' : (m.unit === 'region' ? 'power, per region' : 'coherence, per pair') })])]
      .concat(cols.map(([b, me]) => {
        if (m.unit === 'region' && me.id !== 'welch') return el('td', { class: 'muted small', text: 'one way' });
        const r = resOf(m.id, b.id, me.id);
        if (!r || !r.mixed || !r.mixed.ok) return el('td', { class: 'muted small', text: r && r.mixed ? (r.mixed.why || 'not fitted') : '—' });
        const t3 = (r.mixed.terms || {})[three(m)], t2 = (r.mixed.terms || {})[two(m)];
        const pass = r.gate && r.gate.passed;
        const td = el('td', { class: 'jcell' + (pass ? ' pass' : ''), tabindex: '0', 'data-band': b.id, 'data-method': me.id,
                              title: three(m) + ': ' + fmtF(t3) + '\n' + two(m) + ': ' + fmtF(t2) + (pass ? '\nOpens follow-ups (' + r.gate.by + ')' : '') },
        [el('div', { class: 'jp', text: t3 ? 'p ' + fp(t3.p) : '—' }), el('div', { class: 'small muted', text: t2 ? two(m).replace('Day × ', 'Day×') + ' p ' + fp(t2.p) : '' }),
          pass ? el('span', { class: 'chip jgate', text: 'follow-ups' }) : null]);
        const go = () => { P.band = b.id; P.method = me.id; render(); const c = $('jm-' + m.id); if (c) c.scrollIntoView({ block: 'start', behavior: 'smooth' }); };
        td.addEventListener('click', go);
        td.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
        return td;
      })));
    const first = D.models.filter((m) => m.kind === 'first'), checks = D.models.filter((m) => m.kind === 'check');
    return el('div', { class: 'dtwrap' }, [el('table', { class: 'linetable jans', id: 'joeanswer' }, [el('thead', {}, [head]),
      el('tbody', {}, first.map(row).concat([el('tr', { class: 'jsep' }, [el('th', { colspan: String(cols.length + 1), class: 'small muted', text: 'Checks: these should show nothing' })])],
        checks.map(row)))])]);
  }
  function summaryLine() {
    const D = P.data;
    let nf = 0, nfp = 0, nc = 0, ncp = 0;
    for (const r of D.results || []) {
      const m = modelOf(r.model);
      if (!r.mixed || !r.mixed.ok) continue;
      if (m.kind === 'first') { nf++; if (r.gate && r.gate.passed) nfp++; } else { nc++; if (r.gate && r.gate.passed) ncp++; }
    }
    return nfp + ' of ' + nf + ' first-pass model fits change from Precon1 to Precon4 at p < .05, and ' + ncp + ' of ' + nc
      + ' checks (which should show nothing).';
  }
  function intro() {
    const D = P.data;
    return section('joeintro', '8 · Joe’s data: the proposal’s tests', 'joe', [
      el('p', { class: 'takeaway', id: 'joesay', text: summaryLine() }),
      answerTable(),
      el('p', { class: 'xfacts', id: 'joefacts' }, [el('span', { text: (D.rats || []).length + ' rats' }), el('span', { text: (D.pairs || []).length + ' region pairs' }),
        el('span', { text: 'Precon1 vs Precon4 tested; 2 and 3 drawn' }), el('span', { text: 'mixed model, RM-ANOVA beside it' }),
        el('span', { text: 'p uncorrected, except the post hocs (Holm)' })]),
      X().more('what each cell is', (body) => {
        body.appendChild(el('p', { class: 'small', text: 'Each cell is one model fitted in one band with one way of computing coherence. The big p is the test of interest, '
          + 'Day × factor × Pair: did the change from Precon1 to Precon4 differ between the levels in some pairs more than others? Beneath it, Day × factor: did it '
          + 'differ on average over the pairs? A model whose either one passes p < .05 opens its follow-ups. Click a cell for its plot.' }));
        return null;
      }, { key: 'joe-cell', eager: true }),
    ]);
  }

  /* ---------------- what is measured: three things to play with ---------------- */
  // The windows on one trial's timeline; a model chosen lights its two.
  const WIN = { base20: [-20, 0, 'Baseline 20 s'], base10: [-10, 0, 'Baseline 10 s'], cue1: [0, 10, 'Cue 1'], cue2: [10, 20, 'Cue 2'],
                pair: [0, 20, 'Cue 1 + Cue 2'], swa: [8, 10, '8–10 s'], swb: [10, 12, '10–12 s'], fp: [null, null, 'FP snippets'] };
  const MODEL_WINS = { m1: ['base20', 'pair'], m2: ['base10', 'cue1'], m3: ['base10', 'cue2'], m4: ['swa', 'swb'], m5: ['cue1', 'cue2'],
                       m6a: ['pair', 'fp'], m6b: ['cue1', 'cue2', 'fp'], m7: ['base20', 'pair'], c1: ['cue1', 'cue2'], c2: ['cue1', 'cue2'],
                       c3: ['cue1', 'cue2'], c4: ['cue1', 'cue2'] };
  function timeline(host) {
    host.innerHTML = '';
    const D = P.data;
    const VW = 640, rows = ['base20', 'base10', 'cue1', 'cue2', 'pair', 'swa', 'swb', 'fp'], RH = 19, T = 26;
    const VH = T + rows.length * RH + 30;
    const L = 120, R = 560;
    const tx = (s) => L + (s + 20) / 40 * (R - L);
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', class: 'mfig jtime', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': 'The windows of one trial, from 20 s before cue 1 to the end of cue 2' });
    svg.appendChild(sv('rect', { x: tx(0), y: T - 18, width: tx(10) - tx(0), height: 12, rx: 3, fill: css('--arrow'), 'fill-opacity': 0.25 }));
    svg.appendChild(sv('rect', { x: tx(10), y: T - 18, width: tx(20) - tx(10), height: 12, rx: 3, fill: css('--up'), 'fill-opacity': 0.25 }));
    svg.appendChild(sv('text', { x: tx(5), y: T - 9, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-2') }, 'cue 1'));
    svg.appendChild(sv('text', { x: tx(15), y: T - 9, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-2') }, 'cue 2'));
    for (const s of [-20, -10, 0, 10, 20]) {
      svg.appendChild(sv('line', { x1: tx(s), x2: tx(s), y1: T - 4, y2: T + rows.length * RH, stroke: css('--line'), 'stroke-dasharray': '2 3' }));
      svg.appendChild(sv('text', { x: tx(s), y: T + rows.length * RH + 14, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, (s > 0 ? '+' : '') + s + ' s'));
    }
    const bars = {};
    rows.forEach((w, i) => {
      const y = T + i * RH;
      svg.appendChild(sv('text', { x: L - 8, y: y + 13, 'text-anchor': 'end', 'font-size': 10.5, fill: css('--ink-2') }, WIN[w][2]));
      const [a, b] = WIN[w];
      let r;
      if (w === 'fp') {
        r = sv('g', { class: 'jwin', 'data-w': w });
        for (let k = 0; k < 4; k++) r.appendChild(sv('rect', { x: L + 18 + k * 84, y: y + 3, width: 30, height: 12, rx: 3, fill: css('--node-grey') }));
        r.appendChild(sv('text', { x: R, y: y + 13, 'text-anchor': 'end', 'font-size': 9.5, fill: css('--ink-3') }, 'in FP1 and FP2, at random'));
      } else {
        r = sv('rect', { x: tx(a), y: y + 3, width: tx(b) - tx(a), height: 12, rx: 3, fill: css('--ink-2'), class: 'jwin', 'data-w': w });
      }
      r.setAttribute('opacity', '0.25');
      svg.appendChild(r);
      bars[w] = r;
    });
    const cap = el('p', { class: 'xcap' });
    const chips = el('div', { class: 'xsteps' });
    const say = (m) => {
      const ws = MODEL_WINS[m.id];
      return m.label + ': ' + ws.map((w) => WIN[w][2]).join(' against ') + (m.kind === 'check' ? ', each cue by what it was (the sound, or its letter)' : '') + '.';
    };
    let cur = null;
    const pick = (m) => {
      cur = m.id;
      host.dataset.model = m.id;
      const on = new Set(MODEL_WINS[m.id]);
      for (const w of rows) {
        const b = bars[w];
        const want = on.has(w) ? 1 : 0.18;
        const from = Number(b.getAttribute('opacity'));
        X().tween(320, (t) => b.setAttribute('opacity', lerp(from, want, t).toFixed(2)), 'back');
        if (b.tagName === 'rect') b.setAttribute('fill', css(on.has(w) ? '--arrow' : '--ink-2'));
      }
      cap.textContent = say(m);
      Array.from(chips.children).forEach((c) => c.setAttribute('aria-pressed', String(c.dataset.model === m.id)));
    };
    const CHIP = { m1: 'Baseline vs both cues', m2: 'Baseline vs cue 1', m3: 'Baseline vs cue 2', m4: 'The switch', m5: 'Cue 1 vs cue 2',
                   m6a: 'Trials vs FP, 20 s', m6b: 'Trials vs FP, 10 s', m7: 'Power', c1: 'Noise vs Click', c2: 'Four sounds', c3: 'A/B/C/D',
                   c4: 'High vs Low' };
    for (const m of D.models) chips.appendChild(el('button', { type: 'button', class: 'xstep', 'data-model': m.id, text: CHIP[m.id] || m.label,
                                                            title: m.label, onclick: () => { run++; pick(m); } }));
    let run = 0;
    async function play() {
      const tk = ++run;
      for (const m of D.models.filter((x) => x.kind === 'first')) {
        if (tk !== run) return;
        pick(m);
        await new Promise((r) => setTimeout(r, reduced() ? 0 : 1300));
      }
    }
    const wrap = el('div', { class: 'xplayer jtimeline' }, [svg, cap, el('div', { class: 'xctl' }, [el('button', { type: 'button', class: 'xbtn', text: '▶ Play', onclick: () => play() }), chips])]);
    host.appendChild(wrap);
    pick(D.models[0]);
    return { play, el: wrap };
  }

  // The mains: 60 Hz and its whole multiples, notched; the bands lit.
  function harmonics(host) {
    host.innerHTML = '';
    const VW = 640, VH = 230, L = 40, R = 620, T = 18, B = 180;
    const fx = (f) => L + f / 500 * (R - L);
    const base = (f) => 0.9 - 0.55 * Math.log10(1 + f / 4) / Math.log10(126);
    const fy = (v) => B - v * (B - T);
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', class: 'mfig jharm', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': 'A spectrum with the mains at 60 Hz and its harmonics, notched out' });
    const bandG = sv('g', { opacity: '0' });
    svg.appendChild(bandG);
    const th = sv('rect', { x: fx(5), y: T, width: Math.max(2, fx(12) - fx(5)), height: B - T, fill: css('--ok'), 'fill-opacity': 0.25 });
    const ga = sv('rect', { x: fx(30), y: T, width: fx(90) - fx(30), height: B - T, fill: css('--arrow'), 'fill-opacity': 0.18 });
    bandG.appendChild(th); bandG.appendChild(ga);
    bandG.appendChild(sv('text', { x: fx(8.5), y: T + 12, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-2') }, 'theta'));
    bandG.appendChild(sv('text', { x: fx(60), y: T + 12, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-2') }, 'gamma 30–90 Hz'));
    svg.appendChild(sv('line', { x1: L, x2: R, y1: B, y2: B, stroke: css('--line-2') }));
    for (const f of [0, 60, 120, 180, 240, 300, 360, 420, 480]) {
      svg.appendChild(sv('text', { x: fx(f), y: B + 14, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, String(f)));
    }
    svg.appendChild(sv('text', { x: (L + R) / 2, y: B + 30, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, 'Hz'));
    const line = sv('path', { fill: 'none', stroke: css('--ink-2'), 'stroke-width': 1.6, class: 'jspec' });
    svg.appendChild(line);
    const tags = [];
    for (let k = 1; k <= 8; k++) {
      const t = sv('text', { x: fx(60 * k), y: T + 28, 'text-anchor': 'middle', 'font-size': 10, 'font-weight': 700, fill: css('--up'), opacity: '0', class: 'jhtag' },
        k === 1 ? '60' : '×' + k);
      svg.appendChild(t);
      tags.push(t);
    }
    // spike height per harmonic (0..1) and notch depth per harmonic (0..1)
    const v = { spike: new Array(8).fill(0), notch: new Array(8).fill(0) };
    const draw = () => {
      let d = '';
      for (let f = 0; f <= 500; f += 0.5) {
        let y = base(f);
        for (let k = 1; k <= 8; k++) {
          const f0 = 60 * k, w = 1.2;
          const g = Math.exp(-0.5 * ((f - f0) / w) ** 2);
          y += v.spike[k - 1] * (0.42 / Math.sqrt(k)) * g;
          y -= v.notch[k - 1] * 0.25 * Math.exp(-0.5 * ((f - f0) / 2.2) ** 2);
        }
        d += (f ? 'L' : 'M') + fx(f).toFixed(1) + ',' + fy(clamp(y, 0.02, 1)).toFixed(1);
      }
      line.setAttribute('d', d);
    };
    const SAY = ['The mains, 60 Hz, gets into every wire: a spike in the spectrum.',
      'And its harmonics, the whole multiples of 60: 120, 180, 240 Hz and on. A hum that is not a perfect sine wave carries them.',
      'The notch takes each one out, a narrow dip at every multiple, and leaves the rest of the spectrum alone.',
      'Theta (5–12 Hz) is far from all of them. Gamma (30–90 Hz) holds only the first, 60 Hz; its notched bins (59–61 Hz) are left out of the average.'];
    const cap = el('p', { class: 'xcap' });
    const chips = el('div', { class: 'xsteps' }, ['The mains', 'Its harmonics', 'Notched', 'The bands'].map((x, k) => el('button', { type: 'button', class: 'xstep', text: x,
      onclick: () => { run++; to(k, true); } })));
    let run = 0, step = 0;
    async function to(k, quick) {
      const tk = run;
      step = k;
      host.dataset.step = String(k);
      cap.textContent = SAY[k];
      Array.from(chips.children).forEach((c, i) => c.setAttribute('aria-pressed', String(i === k)));
      const target = { spike: v.spike.map((_x, i) => (k >= 1 ? 1 : i === 0 ? 1 : 0)), notch: v.notch.map(() => (k >= 2 ? 1 : 0)) };
      tags.forEach((t, i) => t.setAttribute('opacity', k >= 1 && (k < 3 || i === 0) ? '1' : '0'));
      bandG.setAttribute('opacity', k >= 3 ? '1' : '0');
      if (quick || reduced()) { Object.assign(v, target); draw(); return; }
      for (let i = 0; i < 8; i++) {
        if (tk !== run) return;
        const a0 = v.spike[i], b0 = v.notch[i];
        if (a0 === target.spike[i] && b0 === target.notch[i]) continue;
        await X().tween(k === 1 || k === 2 ? 220 : 400, (t) => { v.spike[i] = lerp(a0, target.spike[i], t); v.notch[i] = lerp(b0, target.notch[i], t); draw(); }, 'back');
      }
      Object.assign(v, target);
      draw();
    }
    async function play() {
      const tk = ++run;
      for (let k = 0; k < 4; k++) {
        if (tk !== run) return;
        await to(k);
        await new Promise((r) => setTimeout(r, reduced() ? 0 : 1400));
      }
    }
    v.spike[0] = 1;
    draw();
    to(0, true);
    const wrap = el('div', { class: 'xplayer jharmonics' }, [svg, cap, el('div', { class: 'xctl' }, [el('button', { type: 'button', class: 'xbtn', text: '▶ Play', onclick: () => play() }), chips])]);
    host.appendChild(wrap);
    return { play, el: wrap, to: (k) => { run++; return to(k, true); }, get step() { return step; } };
  }

  // The old Minus FP against this tab's: the same number per rat, asked
  // differently.
  function fpCompare(host, ex) {
    host.innerHTML = '';
    const v = ex;
    const VW = 620, VH = 262, B = 200, T = 30;
    const all = [v.c1, v.c4, v.f1, v.f4];
    const hi = Math.max(...all) * 1.15, lo = 0;
    const Y = (x) => B - (x - lo) / (hi - lo) * (B - T);
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', class: 'mfig jfp', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': 'The old Minus FP against the change in the trials set against the change in FP' });
    svg.appendChild(sv('line', { x1: 20, x2: 600, y1: B, y2: B, stroke: css('--line-2') }));
    const X0 = { c1: 60, f1: 100, c4: 200, f4: 240 };
    const bars = {};
    for (const k of ['c1', 'f1', 'c4', 'f4']) {
      const r = sv('rect', { x: X0[k], width: 32, fill: css(k[0] === 'c' ? '--ink-2' : '--node-grey'), class: 'jfpbar', 'data-k': k });
      svg.appendChild(r);
      bars[k] = r;
    }
    svg.appendChild(sv('text', { x: 96, y: B + 16, 'text-anchor': 'middle', 'font-size': 11, fill: css('--ink-2') }, 'Precon1'));
    svg.appendChild(sv('text', { x: 236, y: B + 16, 'text-anchor': 'middle', 'font-size': 11, fill: css('--ink-2') }, 'Precon4'));
    svg.appendChild(sv('text', { x: 76, y: T - 10, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, 'trials'));
    svg.appendChild(sv('text', { x: 116, y: T - 10, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, 'FP'));
    const right = sv('g', { class: 'jfpright' });
    svg.appendChild(right);
    const out = el('div', { class: 'jfpout' });
    const cap = el('p', { class: 'xcap' });
    const old = (v.c4 - v.f4) - (v.c1 - v.f1), dT = v.c4 - v.c1, dF = v.f4 - v.f1;
    const SAY = ['The old Minus FP: each day’s trials less that day’s FP, then the change between the days.',
      'This tab’s: the change in the trials, Precon1 → Precon4, and the change in FP, side by side.',
      'Their difference is the same number as the old Minus FP: ' + f3(dT) + ' − ' + f3(dF) + ' = ' + f3(dT - dF) + '.',
      'What is new: FP is random snippets of FP1 and FP2, as many as the day has trials, not evenly spaced pieces; and the model asks whether FP itself changed.'];
    const chips = el('div', { class: 'xsteps' }, ['Old Minus FP', 'Two changes', 'Their difference', 'What is new'].map((x, k) => el('button', { type: 'button', class: 'xstep', text: x,
      onclick: () => { run++; to(k, true); } })));
    const setBar = (k, val, alpha) => { const y = Y(val); bars[k].setAttribute('y', y.toFixed(1)); bars[k].setAttribute('height', Math.max(0.5, B - y).toFixed(1));
      bars[k].setAttribute('opacity', String(alpha == null ? 1 : alpha)); };
    const arrow = (x, a, b, col, label, id) => {
      const g = sv('g', { class: 'jarrow', 'data-id': id });
      g.appendChild(sv('line', { x1: x, x2: x, y1: Y(a), y2: Y(b), stroke: col, 'stroke-width': 4, 'stroke-linecap': 'round' }));
      g.appendChild(sv('circle', { cx: x, cy: Y(b), r: 5, fill: col }));
      g.appendChild(sv('text', { x: x + 10, y: (Y(a) + Y(b)) / 2 + 4, 'font-size': 11, fill: css('--ink') }, label));
      return g;
    };
    let run = 0, step = 0;
    async function to(k, quick) {
      const tk = run;
      step = k;
      host.dataset.step = String(k);
      cap.textContent = SAY[k];
      Array.from(chips.children).forEach((c, i) => c.setAttribute('aria-pressed', String(i === k)));
      right.innerHTML = '';
      out.textContent = '';
      for (const kk of ['c1', 'f1', 'c4', 'f4']) setBar(kk, v[kk], 1);
      if (k === 0) {
        const steps = 24;
        for (let i = 0; i <= steps; i++) {
          if (tk !== run) return;
          const t = (quick || reduced()) ? 1 : i / steps;
          setBar('c1', v.c1 - v.f1 * t, 1); setBar('c4', v.c4 - v.f4 * t, 1);
          setBar('f1', v.f1, 1 - 0.7 * t); setBar('f4', v.f4, 1 - 0.7 * t);
          if (t >= 1) break;
          await new Promise((r) => setTimeout(r, 25));
        }
        right.appendChild(arrow(420, v.c1 - v.f1, v.c4 - v.f4, css(old >= 0 ? '--up' : '--down'), 'change: ' + f3(old), 'old'));
        out.textContent = 'Old Minus FP: ' + f3(old);
      } else {
        right.appendChild(arrow(380, v.c1, v.c4, css('--ink-2'), 'trials: ' + f3(dT), 'trials'));
        right.appendChild(arrow(500, v.f1, v.f4, css('--node-grey'), 'FP: ' + f3(dF), 'fp'));
        if (k >= 2) {
          out.textContent = 'Trials − FP = ' + f3(dT - dF) + ' · old Minus FP = ' + f3(old) + (Math.abs(dT - dF - old) < 1e-9 ? ' · the same' : '');
          if (!quick && !reduced()) X().celebrate(svg, 440, Y((v.c4 + v.f4) / 2), css('--ok'));
        }
        if (k === 3) {
          const g = sv('g', { class: 'jsnips' });
          g.appendChild(sv('text', { x: 360, y: B + 34, 'font-size': 10, fill: css('--ink-3') }, 'FP1'));
          g.appendChild(sv('text', { x: 360, y: B + 48, 'font-size': 10, fill: css('--ink-3') }, 'FP2'));
          const xs = [391, 433, 462, 520, 571, 409, 488, 547];
          xs.forEach((x, i) => g.appendChild(sv('rect', { x, y: B + 26 + (i < 5 ? 0 : 14), width: 10, height: 8, rx: 2, fill: css('--node-grey') })));
          right.appendChild(g);
        }
      }
    }
    async function play() {
      const tk = ++run;
      for (let k = 0; k < 4; k++) {
        if (tk !== run) return;
        await to(k);
        await new Promise((r) => setTimeout(r, reduced() ? 0 : 1600));
      }
    }
    to(0, true);
    const wrap = el('div', { class: 'xplayer jfpcompare' }, [el('div', { class: 'xfprow' }, [svg, out]), cap,
      el('div', { class: 'xctl' }, [el('button', { type: 'button', class: 'xbtn', text: '▶ Play', onclick: () => play() }), chips,
        ex.label ? el('span', { class: 'small muted', text: ex.label }) : null])]);
    host.appendChild(wrap);
    return { play, el: wrap, to: (k) => { run++; return to(k, true); }, get step() { return step; }, values: { old, dT, dF } };
  }

  function defsCard() {
    const D = P.data;
    const tl = el('div', { id: 'joetimeline' });
    const card = section('joedefs', 'What is measured', 'joe.defs', [
      el('p', { class: 'takeaway', text: 'Seven windows a trial, two bands, coherence computed two ways, and random FP snippets.' }),
      tl,
      X().more('mains and its harmonics', (body) => {
        const h = el('div', { id: 'joeharm' });
        body.appendChild(h);
        return harmonics(h);
      }, { key: 'joe-harm' }),
      X().more('FP: the old Minus FP and this', (body) => {
        const h = el('div', { id: 'joefp' });
        body.appendChild(h);
        // The real numbers: trials vs FP (20 s), theta, Welch, mean over rats.
        const r = resOf('m6a', 'theta', 'welch');
        const c = r && r.cells;
        const ex = c && c.Precon1 && c.Precon4 && c.Precon1.trials.mean != null && c.Precon1.fp.mean != null
          ? { c1: c.Precon1.trials.mean, c4: c.Precon4.trials.mean, f1: c.Precon1.fp.mean, f4: c.Precon4.fp.mean,
              label: 'theta coherence, the mean over rats and pairs' }
          : { c1: 0.42, c4: 0.49, f1: 0.38, f4: 0.43, label: 'made-up numbers' };
        return fpCompare(h, ex);
      }, { key: 'joe-fp' }),
      X().more('the definitions, in words', (body) => {
        const lis = [
          'Days: Precon1 and Precon4 are the two levels of Day in every model; Precon2 and Precon3 are drawn, never tested.',
          'Trials: each rat’s 16 cue pairs a day (8 AB, 8 CD), as the Event Bank has them. Each window’s value is the mean over the day’s trials.',
          'Windows, from each trial’s own cue times: the 20 s and the 10 s before cue 1, cue 1, cue 2, both cues (20 s), the last 2 s of cue 1 (8–10 s) and the first 2 s of cue 2 (10–12 s). A baseline is as long as what it is compared with.',
          'FP snippets: random 10 s and 20 s pieces of the day’s FP1 and FP2 recordings, as many as the day has trials, 10 s from either end, seeded so they are the same every time.',
          'Bands: theta 5–12 Hz and gamma 30–90 Hz, from the proposal. Mains and its harmonics are notched; the notch’s own 59–61 Hz bins are left out of gamma.',
          'Coherence, Welch: the circuits’ method (1 s Hann segments, half overlapping, FFT twice as long). Dickson: Jeremy’s MATLAB, a 59–61 Hz Butterworth notch, then mscohere with hanning(1024), 512 overlap, 2048 points.',
          'Pairs: every pair of the ' + (D.regions || []).length + ' regions, kept in a model when at least ' + D.min_rats + ' rats have it at every level on both days.',
          'Clipping: measured here for every window (the rail, or a flat top, for 16 samples or more), as Spark measures it; a clipped wire gives way to its region’s next.',
          'Models: a mixed model (Day × factor × Pair, the rat random, with rat × Day, rat × factor and rat × Day × factor) and the repeated-measures ANOVA on the rats with every cell.',
        ];
        body.appendChild(el('ul', { class: 'small' }, lis.map((x) => el('li', { text: x }))));
        return null;
      }, { key: 'joe-words', eager: true }),
    ]);
    X().playOnce('joe-timeline', tl, timeline(tl));
    return card;
  }

  /* ---------------- each model ---------------- */
  function plotOf(m, r) {
    const D = P.data;
    const levels = m.levels;
    const VW = 480, VH = 230, L = 52, R = 300, T = 22, B = 178;
    const vals = [];
    for (const d of D.days) for (const lv of levels) {
      const c = ((r.cells || {})[d] || {})[lv.id];
      if (c && c.mean != null) { vals.push(c.mean - (c.se || 0), c.mean + (c.se || 0)); }
    }
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', class: 'mfig jplot', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': m.label + ': Precon1 and Precon4 at each ' + m.factor.toLowerCase(), 'data-model': m.id });
    if (!vals.length) {
      svg.appendChild(sv('text', { x: VW / 2, y: VH / 2, 'text-anchor': 'middle', 'font-size': 11, fill: css('--ink-3') }, 'not measured'));
      return svg;
    }
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = (hi - lo) * 0.15 || 0.01;
    lo -= pad; hi += pad;
    const Y = (x) => B - (x - lo) / (hi - lo) * (B - T);
    const Xl = (i) => L + (levels.length === 1 ? 0.5 : i / (levels.length - 1)) * (R - L);
    svg.appendChild(sv('line', { x1: L, x2: L, y1: T, y2: B, stroke: css('--line-2') }));
    svg.appendChild(sv('line', { x1: L, x2: R, y1: B, y2: B, stroke: css('--line-2') }));
    for (const v of [lo + pad, hi - pad]) svg.appendChild(sv('text', { x: L - 6, y: Y(v) + 3.5, 'text-anchor': 'end', 'font-size': 10, fill: css('--ink-3') }, sig(v)));
    svg.appendChild(sv('text', { x: 12, y: (T + B) / 2, 'font-size': 10, fill: css('--ink-3'), transform: 'rotate(-90 12 ' + ((T + B) / 2) + ')', 'text-anchor': 'middle' },
      m.unit === 'region' ? 'log10 power' : 'coherence'));
    levels.forEach((lv, i) => svg.appendChild(sv('text', { x: Xl(i), y: B + 15, 'text-anchor': 'middle', 'font-size': 10.5, fill: css('--ink-2') }, lv.label)));
    const style = { Precon1: [css('--down'), '5 3', 2.2, 1], Precon2: [css('--ink-3'), '1 3', 1, 0.6], Precon3: [css('--ink-3'), '1 3', 1, 0.6], Precon4: [css('--up'), null, 2.6, 1] };
    for (const d of D.days) {
      const [col, dash, w, op] = style[d] || [css('--ink-3'), null, 1, 0.6];
      let path = '';
      levels.forEach((lv, i) => {
        const c = ((r.cells || {})[d] || {})[lv.id];
        if (!c || c.mean == null) return;
        path += (path ? 'L' : 'M') + Xl(i).toFixed(1) + ',' + Y(c.mean).toFixed(1);
        if (c.se != null && D.tested.includes(d)) {
          svg.appendChild(sv('line', { x1: Xl(i), x2: Xl(i), y1: Y(c.mean - c.se), y2: Y(c.mean + c.se), stroke: col, 'stroke-width': 1.2, opacity: op }));
        }
        svg.appendChild(sv('circle', { cx: Xl(i), cy: Y(c.mean), r: D.tested.includes(d) ? 3.5 : 2, fill: col, opacity: op, class: 'jpt', 'data-day': d, 'data-level': lv.id }));
      });
      if (path) svg.appendChild(sv('path', { d: path, fill: 'none', stroke: col, 'stroke-width': w, 'stroke-dasharray': dash, opacity: op, class: 'jline', 'data-day': d }));
    }
    // The legend, with the statistics in it (Joe's notes: F, df and p in the legend).
    const t3 = ((r.mixed || {}).terms || {})[three(m)], t2 = ((r.mixed || {}).terms || {})[two(m)];
    const lg = [['Precon1', css('--down'), '5 3'], ['Precon4', css('--up'), null], ['Precon2, 3 (not tested)', css('--ink-3'), '1 3']];
    lg.forEach(([t, c, dash], i) => {
      const y = T + 6 + i * 16;
      svg.appendChild(sv('line', { x1: R + 14, x2: R + 34, y1: y, y2: y, stroke: c, 'stroke-width': 2.2, 'stroke-dasharray': dash }));
      svg.appendChild(sv('text', { x: R + 38, y: y + 3.5, 'font-size': 10, fill: css('--ink-2') }, t));
    });
    const stats = [three(m).replace(' × ', '×').replace(' × ', '×') + ':', t3 ? 'F(' + t3.df1 + ', ' + t3.df2 + ') = ' + t3.F.toFixed(2) : '—', t3 ? 'p ' + fp(t3.p) : '',
      two(m).replace(' × ', '×') + ':', t2 ? 'F(' + t2.df1 + ', ' + t2.df2 + ') = ' + t2.F.toFixed(2) : '—', t2 ? 'p ' + fp(t2.p) : ''];
    stats.forEach((s, i) => svg.appendChild(sv('text', { x: R + 14, y: T + 64 + i * 14, 'font-size': 10, fill: css(i % 3 === 0 ? '--ink-2' : '--ink'),
                                                       'font-weight': i % 3 === 0 ? 600 : 400, class: 'jstat' }, s)));
    svg.appendChild(sv('text', { x: R + 14, y: T + 64 + 6 * 14 + 4, 'font-size': 9.5, fill: css('--ink-3') }, 'mixed model, uncorrected'));
    return svg;
  }
  // Each unit's own Day x factor contrast, sorted, those Holm keeps marked.
  function stripOf(m, r) {
    const post = (r.post || []).filter((x) => x.p != null);
    const two2 = m.levels.length === 2;
    const val = (x) => (two2 ? x.delta : x.F);
    const rows = post.slice().sort((a, b) => (val(b) || 0) - (val(a) || 0));
    const VW = 420, H = 90, L = 10, R = 410, mid = 50;
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + (H + 20), width: '100%', class: 'mfig jstrip', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': 'Each ' + (m.unit === 'pair' ? 'pair' : 'region') + '’s own change, sorted' });
    if (!rows.length) return svg;
    const mx = Math.max(1e-12, ...rows.map((x) => Math.abs(val(x) || 0)));
    const bw = (R - L) / rows.length;
    const base = two2 ? mid : H;
    svg.appendChild(sv('line', { x1: L, x2: R, y1: base, y2: base, stroke: css('--line-2') }));
    rows.forEach((x, i) => {
      const v = val(x) || 0;
      const h = (two2 ? 40 : 80) * Math.abs(v) / mx;
      const y = two2 ? (v >= 0 ? base - h : base) : base - h;
      const keep = x.p_holm != null && x.p_holm < ALPHA;
      const raw = x.p < ALPHA;
      const rc = sv('rect', { x: (L + i * bw + 0.5).toFixed(1), y: y.toFixed(1), width: Math.max(1, bw - 1).toFixed(1), height: Math.max(0.6, h).toFixed(1),
                              fill: css(keep ? '--up' : raw ? '--arrow' : '--node-grey'), class: 'jbar' + (keep ? ' holm' : raw ? ' raw' : ''), 'data-unit': x.unit });
      M().hover(rc, [x.unit, two2 ? 'Day × ' + m.factor.toLowerCase() + ' contrast ' + f3(x.delta) + ', t(' + x.df + ') = ' + (x.t != null ? x.t.toFixed(2) : '—')
        : 'F(' + x.df1 + ', ' + x.df2 + ') = ' + (x.F != null ? x.F.toFixed(2) : '—'), 'p ' + fp(x.p) + ' · Holm ' + fp(x.p_holm) + ' · ' + x.n + ' rats']);
      svg.appendChild(rc);
    });
    const nk = rows.filter((x) => x.p_holm != null && x.p_holm < ALPHA).length, nr = rows.filter((x) => x.p < ALPHA).length;
    svg.appendChild(sv('text', { x: L, y: H + 16, 'font-size': 10, fill: css('--ink-3') },
      rows.length + ' ' + (m.unit === 'pair' ? 'pairs' : 'regions') + ', sorted · ' + nr + ' at p < .05 · ' + nk + ' after Holm'));
    return svg;
  }
  function exportFig(svg, name, kind) {
    const s = new XMLSerializer().serializeToString(svg);
    if (kind === 'svg') { M().download(name + '.svg', new Blob([s], { type: 'image/svg+xml' })); return; }
    const vb = svg.viewBox.baseVal;
    const img = new Image();
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = vb.width * 3; c.height = vb.height * 3;
      const g = c.getContext('2d');
      g.fillStyle = css('--surface'); g.fillRect(0, 0, c.width, c.height);
      g.drawImage(img, 0, 0, c.width, c.height);
      c.toBlob((b) => M().download(name + '.png', b), 'image/png');
    };
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(s);
  }
  function termsTable(m, r) {
    const names = new Set(Object.keys(((r.mixed || {}).terms) || {}).concat(Object.keys(((r.rm || {}).terms) || {})));
    const order = ['Day', m.factor, unitWord(m), two(m), 'Day × ' + unitWord(m), m.factor + ' × ' + unitWord(m), three(m)];
    const rows = order.filter((n) => names.has(n));
    return el('div', { class: 'dtwrap' }, [el('table', { class: 'linetable jterms' }, [
      el('thead', {}, [el('tr', {}, ['Term', 'Mixed model', 'RM-ANOVA (' + ((r.rm || {}).n_rats != null ? r.rm.n_rats + ' of ' + r.rm.of + ' rats' : '—') + ')'].map((h) => el('th', { text: h })))]),
      el('tbody', {}, rows.map((n) => el('tr', { class: n === three(m) ? 'jkey' : null }, [el('th', { text: n }),
        el('td', { class: 'num', text: fmtF(((r.mixed || {}).terms || {})[n]) }),
        el('td', { class: 'num', text: (r.rm || {}).ok ? fmtF(r.rm.terms[n]) : (n === rows[0] ? (r.rm || {}).why || '—' : '') })])))]),
      el('p', { class: 'small muted', text: 'Mixed model: ' + ((r.mixed || {}).random || '') + '; ' + fmt((r.mixed || {}).n_obs) + ' rat × day × level × '
        + (m.unit === 'pair' ? 'pair' : 'region') + ' values from ' + ((r.mixed || {}).n_rats || 0) + ' rats. F from Wald tests with between-within df; SPSS MIXED '
        + '(Satterthwaite), from the exported syntax, is the reference.' })]);
  }
  function postTable(m, r) {
    const two2 = m.levels.length === 2;
    const rows = (r.post || []).filter((x) => x.p != null).slice().sort((a, b) => a.p - b.p);
    return el('div', { class: 'dtwrap' }, [el('table', { class: 'linetable jpost' }, [
      el('thead', {}, [el('tr', {}, [m.unit === 'pair' ? 'Pair' : 'Region', two2 ? 'Contrast' : 'F', 'p', 'Holm p', 'Rats'].map((h) => el('th', { text: h })))]),
      el('tbody', {}, rows.map((x) => el('tr', { class: x.p_holm < ALPHA ? 'jkeep' : null, 'data-unit': x.unit }, [el('th', { text: x.unit }),
        el('td', { class: 'num', text: two2 ? f3(x.delta) + ' (t(' + x.df + ') ' + (x.t != null ? x.t.toFixed(2) : '—') + ')' : 'F(' + x.df1 + ', ' + x.df2 + ') ' + (x.F != null ? x.F.toFixed(2) : '—') }),
        el('td', { class: 'num', text: fp(x.p) }), el('td', { class: 'num', text: fp(x.p_holm) }),
        el('td', { class: 'num', text: two2 && x.same != null ? x.same + '/' + x.n + ' same way' : String(x.n) })])))])]);
  }
  function followTable(m, r) {
    const D = P.data;
    const f = r.follow;
    if (!f || !f.pairs.length) return el('p', { class: 'small muted', text: 'No single pair passes on its own, so there is nothing to follow up.' });
    const keys = ['pli', 'icoh', 'gc_ab', 'gc_ba', 'xlag', 'pac_ab', 'pac_ba', 'pac_aa', 'pac_bb'];
    const kids = [el('p', { class: 'small', text: 'The pairs ' + f.basis + ' keeps, each measured the same way, in the same windows. Each row: the Day × '
      + m.factor.toLowerCase() + ' contrast of that measure, and its p across rats (uncorrected).' })];
    for (const pr of f.pairs) {
      kids.push(el('h4', {}, [pr.pair + (pr.bilateral ? ' · the two sides of one structure' : '')]));
      kids.push(el('div', { class: 'dtwrap' }, [el('table', { class: 'linetable jfollow', 'data-pair': pr.pair }, [
        el('thead', {}, [el('tr', {}, ['Measure', 'Contrast', 'p'].map((h) => el('th', { text: h })))]),
        el('tbody', {}, keys.map((k) => {
          const x = pr.measures[k] || {};
          const name = (D.follow_say[k] || k).replace(/\bA\b/g, pr.a).replace(/\bB\b/g, pr.b);
          return el('tr', { 'data-k': k }, [el('th', { text: name }), el('td', { class: 'num', text: x.delta != null ? f3(x.delta) : '—' }),
            el('td', { class: 'num' + (x.p != null && x.p < ALPHA ? ' up' : ''), text: x.p != null ? fp(x.p) : '—' })]);
        }))])]));
    }
    return el('div', {}, kids);
  }
  function modelCard(m) {
    const r = resOf(m.id, P.band, m.unit === 'region' ? 'welch' : P.method);
    const card = el('div', { class: 'jmodel' + (m.kind === 'check' ? ' check' : ''), id: 'jm-' + m.id, 'data-model': m.id });
    card.appendChild(el('div', { class: 'hrow' }, [el('h3', { text: m.label }), el('span', { class: 'chip' + (m.kind === 'check' ? '' : ' all'),
      text: m.kind === 'check' ? 'check · expected null' : 'first pass' })]));
    if (!r || !r.mixed || !r.mixed.ok) {
      card.appendChild(el('p', { class: 'small muted', text: r && r.mixed ? 'Not fitted: ' + (r.mixed.why || 'too few rats') + '.' : 'Not measured.' }));
      return card;
    }
    const t3 = r.mixed.terms[three(m)], t2 = r.mixed.terms[two(m)];
    card.appendChild(el('p', { class: 'jline1' }, [el('b', { text: three(m) + ': ' }), fmtF(t3) + ' · ', el('b', { text: two(m) + ': ' }), fmtF(t2),
      r.gate && r.gate.passed ? el('span', { class: 'chip jgate', text: 'opens follow-ups (' + r.gate.by + ')' }) : null]));
    const plot = plotOf(m, r), strip = stripOf(m, r);
    card.appendChild(el('div', { class: 'jfigs' }, [el('div', {}, [plot]), el('div', {}, [strip])]));
    const nm = 'joe_' + m.id + '_' + P.band + '_' + r.method;
    card.appendChild(el('div', { class: 'hrow jexp' }, [
      el('button', { type: 'button', class: 'more-btn', text: 'SVG', onclick: () => exportFig(plot, nm, 'svg') }),
      el('button', { type: 'button', class: 'more-btn', text: 'PNG', onclick: () => exportFig(plot, nm, 'png') }),
      el('span', { class: 'small muted', text: r.n_units + ' ' + (m.unit === 'pair' ? 'pairs' : 'regions') + (r.left_out && r.left_out.length ? '; ' + r.left_out.length + ' left out (too few rats)' : '') })]));
    card.appendChild(X().more('every term, both models', (body) => { body.appendChild(termsTable(m, r)); return null; }, { key: 'jt-' + m.id }));
    card.appendChild(X().more('which ' + (m.unit === 'pair' ? 'pairs' : 'regions') + ' drive it', (body) => { body.appendChild(postTable(m, r)); return null; },
      { key: 'jp-' + m.id }));
    if (r.follow) {
      card.appendChild(X().more('follow-ups: PLI, direction and PAC for the pairs it lets through', (body) => { body.appendChild(followTable(m, r)); return null; },
        { key: 'jf-' + m.id }));
    }
    // Within one structure, left against right: the proposal's bilateral
    // coherence, read off the same model for the pairs that are one
    // structure's two sides (only rats with both sides usable have them).
    if (r.gate && r.gate.passed && m.unit === 'pair') {
      const bl = new Set(P.data.bilateral || []);
      const rows = (r.post || []).filter((x) => bl.has(x.unit));
      card.appendChild(X().more('left against right, within each structure', (body) => {
        if (!rows.length) {
          body.appendChild(el('p', { class: 'small muted', text: 'No structure has both sides in enough rats for this model.' }));
          return null;
        }
        body.appendChild(postTable(m, Object.assign({}, r, { post: rows })));
        const missing = (P.data.bilateral || []).filter((u) => !rows.some((x) => x.unit === u));
        if (missing.length) body.appendChild(el('p', { class: 'small muted', text: 'Not here (too few rats with both sides): ' + missing.join(', ') + '.' }));
        return null;
      }, { key: 'jb-' + m.id }));
    }
    return card;
  }
  function modelsCard() {
    const D = P.data;
    const body = [
      el('p', { class: 'takeaway', text: 'Each model, Precon1 against Precon4, in the band and coherence method chosen here.' }),
      el('div', { class: 'hrow' }, [seg(D.bands.map((b) => [b.id, b.label]), P.band, (id) => { P.band = id; render(); }, 'joeband'),
        seg(D.methods.map((m) => [m.id, m.id === 'welch' ? 'Welch' : 'Dickson 2022']), P.method, (id) => { P.method = id; render(); }, 'joemethod')]),
    ];
    body.push(el('h3', { class: 'jgroup', text: 'First pass' }));
    for (const m of D.models.filter((x) => x.kind === 'first')) body.push(modelCard(m));
    body.push(el('h3', { class: 'jgroup', text: 'Checks: these should show nothing' }));
    for (const m of D.models.filter((x) => x.kind === 'check')) body.push(modelCard(m));
    return section('joemodels', 'The models', 'joe.models', body);
  }

  /* ---------------- take it away ---------------- */
  function exportsCard() {
    const D = P.data;
    const A = D.agreement;
    const files = (D.exports || []).slice();
    const kids = [
      el('p', { class: 'takeaway', text: 'One .csv and one .sps per model, band and method. Open the .sps in SPSS: it reads the .csv, declares 999 as missing and runs both models.' }),
      el('div', { class: 'hrow' }, [el('a', { class: 'more-btn', id: 'joezip', href: FILE('joe_tab8_spss.zip'), download: 'joe_tab8_spss.zip', text: 'Download everything (.zip)' }),
        el('a', { class: 'more-btn', id: 'joescript', href: FILE('joe_standalone.py'), download: 'joe_standalone.py', text: 'The standalone script (.py)' }),
        window.MONO_STATIC ? null : el('a', { class: 'more-btn', href: FILE('joe_inputs.json'), download: 'joe_inputs.json', text: 'Its inputs (.json)' })]),
      X().more('every file', (body) => {
        body.appendChild(el('ul', { class: 'small jfiles' }, files.map((f) => el('li', {}, [el('a', { href: FILE(f), download: f, text: f })]))));
        return null;
      }, { key: 'joe-files', eager: true }),
      el('h3', { text: 'Does the standalone script agree?' }),
    ];
    if (A) {
      const bad = A.files.filter((x) => !x.ok);
      kids.push(el('p', { class: 'physanswer ' + (A.ok ? 'ok' : 'warn'), id: 'joeagree' }, [el('span', { class: 'head', text: A.ok
        ? 'Yes: ' + A.files.length + ' files, every cell within ' + A.tol + ' (largest difference ' + sig(Math.max(...A.files.map((x) => x.worst || 0))) + ').'
        : 'Not everywhere: ' + bad.length + ' of ' + A.files.length + ' files differ.' }), el('span', { class: 'small muted', text: ' Run ' + A.ran_at + '.' })]));
      if (bad.length) {
        kids.push(el('ul', { class: 'small' }, bad.slice(0, 12).map((x) => el('li', { text: x.file + ': ' + (x.why || ('largest difference ' + sig(x.worst)
          + (x.missing_differs ? ', ' + x.missing_differs + ' cells missing in one only' : ''))) }))));
      }
    } else {
      kids.push(el('p', { class: 'small muted', id: 'joeagree', text: 'Not run yet. The script reads the recordings itself, with nothing from Jarvis, and writes the same files.' }));
    }
    if (!window.MONO_STATIC) {
      kids.push(el('button', { type: 'button', class: 'more-btn', id: 'joescriptrun', disabled: P.scripting ? 'disabled' : null,
                               text: P.scripting ? 'Running the script: ' + (P.scriptNote || 'starting') : 'Run it here and compare (about 30 minutes)',
                               onclick: () => make('script') }));
      if (P.scriptErr) kids.push(el('p', { class: 'small warn', text: P.scriptErr }));
    }
    kids.push(el('p', { class: 'small muted', text: 'Elsewhere: python joe_standalone.py --inputs joe_inputs.json --out <folder>. It needs Python 3, numpy and scipy, and the recordings at the paths in the inputs.' }));
    return section('joeexports', 'Take it away: SPSS, and a script that does it all again', 'joe.exports', kids);
  }
  function notesCard() {
    const D = P.data;
    if (!(D.notes || []).length) return null;
    return el('div', { class: 'card', id: 'joenotes' }, [X().more('notes from the recordings (' + D.notes.length + ')', (body) => {
      body.appendChild(el('ul', { class: 'small' }, D.notes.map((n) => el('li', { text: n }))));
      return null;
    }, { key: 'joe-notes' })]);
  }

  function render() {
    const pane = $('joepane');
    if (!pane) return;
    pane.innerHTML = '';
    if (P.loading && !P.data) { pane.appendChild(el('p', { class: 'loading', text: 'Reading tab 8…' })); return; }
    if (!P.data) {
      pane.appendChild(section('joemissing', '8 · Joe’s data: the proposal’s tests', 'joe', [
        el('p', { class: 'takeaway', text: 'Coherence between regions, theta and gamma, Precon1 against Precon4: the tests Joe’s proposal names. Not worked out yet.' }),
        el('p', { class: 'small', text: 'It is worked out here, from the recordings: about 20 minutes the first time (every trial of every rat, four days), seconds after that.' }),
        window.MONO_STATIC ? el('p', { class: 'small muted', text: 'Not in this copy: it opens in Jarvis.' })
          : el('button', { type: 'button', class: 'more-btn', id: 'joemake', disabled: P.making ? 'disabled' : null,
                           text: P.making ? 'Working: ' + (P.makeNote || 'starting') : 'Work it out now', onclick: () => make('joe') }),
        P.makeErr ? el('p', { class: 'small warn', text: P.makeErr }) : null,
      ]));
      return;
    }
    pane.appendChild(intro());
    pane.appendChild(defsCard());
    pane.appendChild(modelsCard());
    pane.appendChild(exportsCard());
    const nc = notesCard();
    if (nc) pane.appendChild(nc);
    if (!window.MONO_STATIC) {
      pane.appendChild(el('p', { class: 'small muted' }, ['Worked out ' + (P.data.at || '') + ' from ' + P.data.n_days + ' rat-days. ',
        el('button', { type: 'button', class: 'linkish', id: 'joemake', disabled: P.making ? 'disabled' : null,
                       text: P.making ? 'Working: ' + (P.makeNote || 'starting') : 'Work it out again', onclick: () => make('joe') })]));
    }
  }
  function show() {
    if (!P.data && !P.loading) load(); else render();
  }
  return {
    show, render, load, make, timeline, harmonics, fpCompare,
    get state() { return { band: P.band, method: P.method, data: P.data, err: P.err, making: P.making, scripting: P.scripting }; },
    set band(v) { P.band = v; render(); },
    set method(v) { P.method = v; render(); },
  };
})();
