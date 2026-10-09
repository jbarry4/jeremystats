/* ==========================================================================
   monolith_narrow.js -- the Monolith's seventh tab: narrowing down.

   Every p on the page is uncorrected, by the lab's choice. This tab says how
   those p were made, asks whether there is more than chance at all, shows
   what each correction for the number of tests would keep, and runs tests
   that assume less -- exact relabellings of the eight rats, the sign test,
   runs of neighbouring frequencies, replication across the two pairs. It
   changes nothing anywhere else on the page. backend/narrow.py makes its
   numbers: narrow.json, and narrow_<layer>.f32 (the quantities NQ at every
   entry). Load order: after monolith.js.
   ========================================================================== */
'use strict';

window.MONO_NARROW = (function () {
  const M = () => window.MONO;
  const NS = 'http://www.w3.org/2000/svg';
  const NQ = ['hk_p', 'perm_p', 'sign_p', 'bh_q', 'by_q', 'holm_p', 'maxt_p', 'cluster_p', 'rep', 'est'];
  const QI = Object.fromEntries(NQ.map((q, i) => [q, i]));
  const P = { data: null, err: null, loading: false, layer: 'raw', leads: 'monolith', all: false, method: 'bh', view: null,
              arr: new Map(), making: false, makeNote: '', makeErr: null, seq: 0, cseq: 0 };
  const $ = (id) => document.getElementById(id);
  const el = (...a) => M().el(...a);
  function sv(tag, attrs, text) {
    const n = document.createElementNS(NS, tag);
    for (const k in (attrs || {})) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const S = () => M().data.S;
  const sig = (v) => M().sig(v), f3 = (v) => M().f3(v), fp = (v) => M().fp(v), short = (r) => M().short(r);
  const fmt = (n) => (n == null ? '—' : Number(n).toLocaleString('en-US'));
  const pct = (a, b) => (b ? (100 * a / b).toFixed(a && 100 * a / b < 0.1 ? 3 : 1) + '%' : '—');
  const cut = (n) => Math.max(1, Math.floor(0.05 * n));
  // Where the real count falls among the relabellings, in one wording for
  // the whole tab: beyond (the top 5%), borderline (the top 10%), ordinary.
  const rankWord = (g) => (g.rank <= cut(g.n || 128) ? 'beyond nearly every shuffle'
    : g.rank <= 2 * cut(g.n || 128) ? 'borderline: about ' + Math.round(100 * g.rank / g.n) + '% of shuffles do as well'
      : 'an ordinary count among them');
  const LAYER_SAY = { raw: 'Raw', minus_fp: 'Minus FP' };
  function seg(list, cur, pick, id) {
    const g = M().seg(list, cur, pick, id);
    g.id = id;
    return g;
  }
  function section(id, title, help, kids) {
    return el('div', { class: 'card', id }, [el('div', { class: 'hrow' }, [el('h2', { text: title }), help ? M().qh(help) : null])].concat(kids));
  }
  // The methods, in the order the page lists them: what each keeps and what
  // it promises.
  const METHODS = [
    ['uncorrected', 'Uncorrected, p < .05', 'nothing: about 5% of tests pass by chance alone', 'every p on the page'],
    ['bonferroni', 'Bonferroni', 'the chance of even one false finding (family-wise), assuming nothing', 'p < .05 ÷ the number of tests'],
    ['holm', 'Holm', 'the same as Bonferroni, a little less strict', 'step by step from the smallest p'],
    ['bh', 'Benjamini–Hochberg', 'the share of false findings among those kept (5%)', 'the false discovery rate'],
    ['by', 'Benjamini–Yekutieli', 'the same share, whatever the tests’ dependence', 'BH, made safe for any correlation'],
    ['maxt', 'Permutation max-t', 'one false finding anywhere, from the data’s own correlations', 'Westfall–Young, 128 signings'],
    ['clusters', 'Frequency clusters', 'one false run of frequencies anywhere', 'runs of neighbouring 1 Hz bands, 128 shuffles'],
    ['perm', 'Exact permutation, p < .05', 'nothing (uncorrected), but no normality assumed', 'each stat test against its 128 shuffles'],
    ['perm_bh', 'Exact permutation, then BH', 'the false discovery rate, no normality assumed', 'its smallest p is 1/128'],
    ['sign', 'Exact sign test, p < .05', 'nothing (uncorrected); only which way each rat went', 'all 8 rats one way: p = .0078'],
  ];

  /* ---------------- data ---------------- */
  async function load() {
    const seq = ++P.seq;
    P.loading = true;
    render();
    try {
      const got = await M().getJSON('/data/narrow');
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
  async function arrayOf(layer) {
    const name = 'narrow_' + layer;
    if (P.arr.has(name)) return P.arr.get(name);
    const S0 = S();
    const shape = [NQ.length, S0.windows.length, S0.bands.length, S0.methods.length, S0.pairs.length];
    const v = M().getArray(name, shape).then((a) => ({ a, shape }));
    P.arr.set(name, v);
    v.catch(() => P.arr.delete(name));
    return v;
  }
  const at = (v, q, w, b, m, p) => { const sh = v.shape; return v.a[(((q * sh[1] + w) * sh[2] + b) * sh[3] + m) * sh[4] + p]; };
  async function make() {
    if (P.making) return;
    P.making = true; P.makeErr = null; P.makeNote = '';
    render();
    try {
      await M().runHere('/narrow', { confirm: true }, (note) => { P.makeNote = note; const b = $('narrowmake'); if (b) b.textContent = 'Working: ' + note; });
      P.arr.clear();
    } catch (e) {
      P.makeErr = /404|not found/i.test(e.message) ? 'Jarvis is running older code without this button: restart it, then press it again.'
        : 'It could not be made: ' + e.message;
    }
    P.making = false;
    load();
  }

  /* ---------------- small pictures ---------------- */
  // A histogram of the counts the relabellings gave, the real count and
  // chance marked, and a legend under it.
  function hist(counts, marks, title) {
    const W = 360, H = 104, l = 12, r = 12, t = 18, bo = 26;
    const vals = counts.concat(marks.map((m) => m.v)).filter((v) => v != null && isFinite(v));
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (hi - lo < 1) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.04;
    lo = Math.max(0, lo - pad); hi += pad;
    const nb = Math.min(24, Math.max(6, Math.round(Math.sqrt(counts.length) * 2)));
    const step = (hi - lo) / nb;
    const bins = new Array(nb).fill(0);
    for (const c of counts) bins[Math.max(0, Math.min(nb - 1, Math.floor((c - lo) / step)))]++;
    const top = Math.max(1, ...bins);
    const X = (v) => l + (W - l - r) * ((v - lo) / (hi - lo));
    const g = sv('svg', { viewBox: '0 0 ' + W + ' ' + H, width: '100%', class: 'mfig narhist', role: 'img', 'aria-label': title,
                          style: 'max-width:' + W + 'px' });
    g.appendChild(sv('text', { x: 4, y: 12, 'font-size': 10.5, fill: css('--ink-2'), 'font-weight': 600 }, title));
    bins.forEach((n, i) => {
      const h = (H - bo - t - 4) * n / top;
      g.appendChild(sv('rect', { x: X(lo + i * step).toFixed(1), y: (H - bo - h).toFixed(1), width: Math.max(1, X(lo + step) - X(lo) - 1).toFixed(1),
                                 height: h.toFixed(1), fill: css('--node-grey'), class: 'hbin', 'data-n': String(n) }));
    });
    g.appendChild(sv('line', { x1: l, x2: W - r, y1: H - bo, y2: H - bo, stroke: css('--line-2') }));
    [[lo, 'start'], [hi, 'end']].forEach(([v, anchor]) => g.appendChild(sv('text', { x: X(v).toFixed(1), y: H - bo + 13, 'text-anchor': anchor,
      'font-size': 10, fill: css('--ink-3') }, fmt(Math.round(v)))));
    g.appendChild(sv('text', { x: W / 2, y: H - 3, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, 'stat tests with p < .05'));
    for (const m of marks) {
      if (m.v == null || !isFinite(m.v)) continue;
      g.appendChild(sv('line', { x1: X(m.v).toFixed(1), x2: X(m.v).toFixed(1), y1: t, y2: H - bo, stroke: m.color, 'stroke-width': m.dash ? 1.2 : 2,
                                 'stroke-dasharray': m.dash ? '3 2' : null, class: 'hmark', 'data-mark': m.id, 'data-v': String(m.v) }));
    }
    const key = el('div', { class: 'hlegend' }, marks.filter((m) => m.v != null && isFinite(m.v)).map((m) =>
      el('span', { 'data-mark': m.id }, [el('i', { class: m.dash ? 'dash' : null, style: 'border-color:' + m.color }), m.label + ' ' + fmt(m.v)])));
    return el('div', { class: 'hfig' }, [g, key]);
  }
  // A bar on a log scale, for counts from tens of thousands down to none.
  function logbar(n, max) {
    const W = 150, H = 12;
    const x = n > 0 ? 4 + (W - 8) * Math.log10(1 + n) / Math.log10(1 + Math.max(1, max)) : 0;
    const g = sv('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, class: 'narbar', role: 'img', 'aria-label': fmt(n) });
    g.appendChild(sv('rect', { x: 2, y: 2, width: W - 4, height: H - 4, fill: css('--surface-2'), stroke: css('--line') }));
    if (n > 0) g.appendChild(sv('rect', { x: 2, y: 2, width: Math.max(1.5, x - 2).toFixed(1), height: H - 4, fill: css('--arrow') }));
    return g;
  }

  /* ---------------- the cards ---------------- */
  // The bottom line, said first: is there more than chance, and does any
  // single entry survive a correction? Both layers, the whole Monolith and
  // the core family chosen before looking.
  function answer() {
    const D = P.data;
    const C = D.counts || {}, G = D.global || {};
    const c = (C.all || {}).raw || {};
    if (!c.m) return null;
    const rk = (f, L) => ((G[f] || {})[L] || {});
    const beyond = (g) => g.rank != null && g.rank <= cut(g.n || 128);
    const say1 = (g) => 'ranks ' + g.rank + ' of ' + g.n + ' (' + rankWord(g) + ')';
    const looks = [rk('all', 'raw'), rk('all', 'minus_fp'), rk('core', 'raw'), rk('core', 'minus_fp')].filter((g) => g.n);
    const anyBeyond = looks.some(beyond);
    const keep = (x) => (x.bonferroni || 0) + (x.holm || 0) + (x.bh || 0) + (x.maxt || 0) + (x.cluster_cells || 0);
    const kept = ['all', 'named', 'states_named', 'core'].some((f) => keep((C[f] || {}).raw || {}) + keep((C[f] || {}).minus_fp || {}) > 0);
    const rp = D.replication || {};
    const head = anyBeyond && !kept ? 'The answer: as a whole, the Monolith holds a little more than chance; no single stat test survives a correction.'
      : anyBeyond ? 'The answer: there is more here than chance, and a few stat tests survive a correction.'
        : kept ? 'The answer: the count is within what chance gives, but a few stat tests survive a correction.'
          : 'The answer: the count is within what chance gives, and no single stat test survives a correction.';
    const cm = (C.all || {}).minus_fp || {}, cc = (C.core || {}).raw || {};
    const say = 'Uncorrected, ' + fmt(c.uncorrected) + ' of ' + fmt(c.m) + ' Raw tests pass p < .05, where chance alone would give about '
      + fmt(Math.round(c.chance)) + ' (Minus FP: ' + fmt(cm.uncorrected) + '). Against every shuffle of the eight rats, the Raw count '
      + say1(rk('all', 'raw')) + ', and Minus FP ' + say1(rk('all', 'minus_fp')) + '; in the core family chosen before looking (' + fmt(cc.m)
      + ' tests), Raw ' + say1(rk('core', 'raw')) + ' and Minus FP ' + say1(rk('core', 'minus_fp')) + '. '
      + (kept ? 'Corrected for every test, a few stat tests survive: see the table below. '
        : 'But no single stat test survives any correction (Bonferroni, Holm, Benjamini–Hochberg, the permutation max-t or a run of frequencies), '
          + 'in any family, even the ' + fmt(cc.m) + ' core tests. ')
      + (rp.n ? 'The clearest sign of something real is replication: ' + fmt(rp.observed) + ' stat tests pass in both pairs, AB and CD, the same way, '
          + 'where independent pairs would give about ' + fmt(Math.round(rp.expected_independent)) + ', ranking ' + rp.rank + ' of ' + rp.n + '. ' : '')
      + 'With eight rats, the evidence is in the pattern, not in any one line. Every other card on the page stays uncorrected.';
    const X = window.MONO_EXPLAIN;
    return el('div', { class: 'physanswer ' + (anyBeyond || kept ? 'ok' : 'warn'), id: 'naranswer' }, [
      el('p', { class: 'head', text: head }),
      X ? X.more('the details', (body) => { body.appendChild(el('p', { id: 'naranswersay', text: say })); return null; }, { key: 'nar-answer', eager: true })
        : el('p', { id: 'naranswersay', text: say })]);
  }
  function intro() {
    return section('narintro', 'Narrowing down', 'narrow', [
      answer(),
      el('p', { class: 'takeaway', id: 'narwhat', text: 'Every p on the page is uncorrected. Here: how they were made, whether there is more than chance, '
        + 'and what a correction keeps. Nothing here changes the rest of the page.' }),
    ]);
  }
  function howCard() {
    const D = P.data;
    const L0 = ((D.how || {}).lead) || null;
    const S0 = S();
    const meth = (id) => (S0.methods.find((m) => m.id === id) || {}).label || id;
    const win = (id) => (S0.windows.find((w) => w.id === id) || {}).label || id;
    const ex = L0 && L0.se ? 'The Monolith’s first top result, ' + short(L0.a) + ' – ' + short(L0.b) + ', ' + win(L0.w) + ', '
      + (L0.hz ? L0.hz + ' Hz' : L0.band) + ', ' + meth(L0.m) + ': the change pooled over its ' + L0.k + ' rats is ' + f3(L0.est)
      + ' with a standard error of ' + sig(L0.se) + '. t = ' + f3(L0.est) + ' ÷ ' + sig(L0.se) + ' = ' + (L0.est / L0.se).toFixed(1)
      + ' on ' + (L0.k - 1) + ' degrees of freedom, so p = ' + fp(L0.p) + ' (two-sided). ' + L0.same + ' of the ' + L0.k + ' rats went that way.' : null;
    const steps = [
      'Each trial gives the stat test one number, in its window (Cue 1 is ten seconds, say).',
      'Each rat-day: the mean over its trials, and how sure that mean is (its standard error: the spread ÷ √ the number of trials).',
      'Each rat: its Precon4 mean less its Precon1 mean (in Minus FP, each day less its FP first); its uncertainty, the two days’ added.',
      'Over rats: DerSimonian–Laird pooling. Each rat is weighted by 1 ÷ (its own uncertainty + τ²), τ² being how much the rats differ beyond '
        + 'their own noise. A rat with steadier numbers counts for more.',
      'The test: Hartung–Knapp. t = the pooled change ÷ its standard error, on (rats − 1) degrees of freedom; the p is two-sided. It needs at least '
        + (S0.min_rats || 4) + ' rats with the stat test on both days.',
      'One test per stat test, every window × frequency × measure × region pair: ' + fmt(((D.counts || {}).all || {}).raw ? D.counts.all.raw.m : null)
        + ' tests in Raw. Each has a 5% chance of passing when nothing changed, and they are not independent: neighbouring frequencies, '
        + 'related measures and the windows that share samples move together.',
    ];
    const X = window.MONO_EXPLAIN;
    const box = el('div', { id: 'narplayer' });
    const words = [el('ol', { class: 'qsteps' }, steps.map((x) => el('li', { text: x }))),
      el('p', { class: 'small muted', text: 'The t is a good test when each rat’s change is roughly normal; with eight rats that cannot be checked, '
        + 'which is why the exact shuffles below assume nothing of the kind. Its small p also extrapolate the t distribution’s tails: with 7 '
        + 'degrees of freedom a t of 13 gives p = .000004, while the most an exact test of eight rats can say is 1 in 128.' })];
    const card = section('narhow', 'How every p on the page was made', 'narrow.how', [
      el('p', { class: 'takeaway', id: 'narhowsay', text: L0 ? 'Played on the Monolith’s first top result, ' + short(L0.a) + ' – ' + short(L0.b) + ', '
        + win(L0.w) + ', ' + (L0.hz ? L0.hz + ' Hz' : L0.band) + ', ' + meth(L0.m) + ':' : 'Every stat test is made the same way.' }),
      box,
      X ? X.more('the steps, in words', (body) => { if (ex) body.appendChild(el('p', { class: 'qexample small', id: 'narexample', text: ex }));
        words.forEach((x) => body.appendChild(x)); return null; }, { key: 'nar-steps', eager: true })
        : el('div', {}, [ex ? el('p', { class: 'qexample small', id: 'narexample', text: ex }) : null].concat(words)),
    ]);
    const at = L0 ? [S0.windows.findIndex((w) => w.id === L0.w), S0.bands.findIndex((b) => b.id === L0.band), S0.methods.findIndex((m) => m.id === L0.m), L0.pair] : null;
    if (X && at && at.every((x) => x != null && x >= 0)) {
      box.appendChild(el('p', { class: 'loading', text: 'Reading every rat, day and trial' }));
      M().entryJSON('/entry?what=edges&layer=raw&at=' + at.join(',')).then((d) => {
        if (!box.isConnected) return;
        X.playOnce('nar-player', box, X.numberPlayer(box, d, { minusFP: false, capId: 'narcap' }));
      }).catch((e) => { box.innerHTML = ''; box.appendChild(el('p', { class: 'small muted', text: 'Could not read it: ' + e.message })); });
    }
    return card;
  }
  function globalCard() {
    const D = P.data;
    const L = P.layer;
    const g = ((D.global || {}).all || {})[L] || {};
    const gc = ((D.contrast || {}).global) || {};
    const c = ((D.counts || {}).all || {})[L] || {};
    const figs = el('div', { class: 'physhists' });
    const X = window.MONO_EXPLAIN;
    const rats = (D.rats || []).map((r) => 'r' + r);
    const shuf = (id, gg, title) => {
      const h = el('div', { 'data-perm': id });
      figs.appendChild(h);
      const p = X.shuffle(h, { counts: gg.counts, realIndex: 0, observed: gg.observed, rank: gg.rank, expected: gg.expected, kind: 'sign', rats,
                               realLabel: 'the real rats', title, say: 'Each shuffle flips some rats’ changes, as if nothing had changed, and counts again.',
                               rankSay: 'The real count ranks ' + gg.rank + ' of ' + gg.n + ': ' + rankWord(gg) + '.' });
      X.playOnce('nar-shuf-' + id + '-' + L, h, p);
    };
    if (X) {
      if (g.counts) shuf('all', g, 'The Monolith (' + LAYER_SAY[L] + '), stat tests at p < .05, in every shuffle of the rats (' + (g.n - 1) + ')');
      if (gc.counts) shuf('contrast', gc, 'Cue 2 − Cue 1, in every shuffle of the rats (' + (gc.n - 1) + ')');
    } else if (g.counts) {
      figs.appendChild(el('div', { 'data-perm': 'all' }, [hist(g.counts.slice(1), [
        { id: 'chance', v: Math.round(g.expected), label: 'chance (5%)', color: css('--ink-3'), dash: true },
        { id: 'observed', v: g.observed, label: 'the rats as they are', color: css('--up') }],
        'The Monolith (' + LAYER_SAY[L] + ') in every shuffle of the rats (' + (g.n - 1) + ')'),
        el('p', { class: 'small muted', text: 'The real count ranks ' + g.rank + ' of ' + g.n + ': ' + rankWord(g) + '.' })]));
    }
    if (!X && gc.counts) {
      figs.appendChild(el('div', { 'data-perm': 'contrast' }, [hist(gc.counts.slice(1), [
        { id: 'chance', v: Math.round(gc.expected), label: 'chance (5%)', color: css('--ink-3'), dash: true },
        { id: 'observed', v: gc.observed, label: 'the rats as they are', color: css('--up') }],
        'Cue 2 − Cue 1 in every shuffle of the rats (' + (gc.n - 1) + ')'),
        el('p', { class: 'small muted', text: 'The real count ranks ' + gc.rank + ' of ' + gc.n + ': ' + rankWord(gc) + '.' })]));
    }
    const why = 'If nothing changed from Precon1 to Precon4, each rat’s change is as likely to have come out the other way. Flipping the rats’ '
      + 'signs every possible way (128 ways for eight rats) and pooling each exactly as the Monolith does gives the counts chance alone would '
      + 'give, with every correlation between stat tests kept.';
    return section('narglobal', 'Is there anything at all? The whole Monolith against shuffle', 'narrow.global', [
      seg([['raw', 'Raw'], ['minus_fp', 'Minus FP']], L, (id) => { P.layer = id; render(); }, 'narlayer'),
      el('p', { class: 'takeaway', id: 'narglobalsay', text: fmt(c.uncorrected) + ' stat tests pass p < .05 with the rats as they are; the shuffles give '
        + (g.counts ? fmt(Math.min(...g.counts.slice(1))) + ' to ' + fmt(Math.max(...g.counts.slice(1))) : '—') + '.' }),
      figs,
      X ? X.more('why shuffling is fair', (body) => { body.appendChild(el('p', { class: 'small', text: why })); return null; }, { key: 'nar-why', eager: true })
        : el('p', { text: why }),
    ]);
  }
  function correctCard() {
    const D = P.data;
    const C = (D.counts || {}).all || {};
    const cc = (D.contrast || {}).counts || {};
    const cols = [['raw', 'Raw', C.raw || {}], ['minus_fp', 'Minus FP', C.minus_fp || {}], ['contrast', 'Cue 2 − Cue 1', cc]];
    const val = (c, id) => (id === 'clusters' ? c.cluster_cells : c[id]);
    const max = Math.max(1, ...cols.map(([, , c]) => c.uncorrected || 0));
    const rows = METHODS.map(([id, name, what, how]) => el('tr', { 'data-method': id }, [
      el('th', {}, [el('div', { text: name }), el('div', { class: 'small muted', text: how })]),
      el('td', { class: 'small', 'data-label': 'controls', text: what })].concat(cols.map(([cid, _l, c]) => el('td', { class: 'num', 'data-col': cid,
        'data-label': _l }, [el('div', { text: fmt(val(c, id)) + (id === 'clusters' && c.clusters != null ? ' (' + fmt(c.clusters) + ' runs)' : '') }),
        el('div', { class: 'small muted', text: pct(val(c, id) || 0, c.m) + ' of ' + fmt(c.m) })])), [
        el('td', { class: 'bar' }, [logbar(val(C.raw || {}, id) || 0, max)])])));
    const X = window.MONO_EXPLAIN;
    const promise = 'Family-wise methods (Bonferroni, Holm, max-t, clusters) promise that even one false finding is unlikely; the '
      + 'false-discovery methods (Benjamini–Hochberg, –Yekutieli) promise that at most 5% of what they keep is false. The exact tests do not '
      + 'correct; they test each stat test without assuming the rats’ changes are normal. ';
    const bars = 'Bonferroni’s bar in Raw: p < ' + sig((C.raw || {}).bonferroni_p) + '. Benjamini–Hochberg '
        + ((C.raw || {}).bh_p != null ? 'keeps every p up to ' + sig(C.raw.bh_p) : 'keeps nothing: no set of the smallest p is small enough') + '. The permutation max-t keeps a stat test whose |t| beats ' + sig((C.raw || {}).maxt_t)
        + ', the largest |t| anywhere in the Monolith in 95% of the shuffles: that shuffled rats reach a |t| that large shows how far a t-test '
        + 'on a few rats strays when they happen to agree closely. Frequency clusters: runs of neighbouring 1 Hz bands passing p < .05 '
        + 'the same way, each weighed by its summed |t| against the heaviest run anywhere in each shuffle (counts are bands in surviving runs). '
        + 'With eight rats, no exact test can go below 1/128 = .0078, so an exact test corrected over hundreds of thousands of stat tests keeps nothing; '
        + 'that is a limit of eight rats, not a sign that nothing changed.';
    return section('narcorrect', 'What correcting does', 'narrow.correct', [
      el('p', { class: 'takeaway', id: 'narcorrectsay', text: 'Each correction sets a higher bar, from how many tests there are. What clears it:' }),
      el('div', { class: 'dtwrap' }, [el('table', { class: 'linetable narcorrect', id: 'narcorrecttbl' }, [
        el('thead', {}, [el('tr', {}, ['Method', 'Controls', 'Raw', 'Minus FP', 'Cue 2 − Cue 1', 'Raw, log scale'].map((h) => el('th', { text: h })))]),
        el('tbody', {}, rows)])]),
      X ? X.more('what each one promises, and its bar', (body) => { body.appendChild(el('p', { class: 'small', id: 'narbars', text: promise + bars })); return null; },
        { key: 'nar-bars', eager: true }) : el('p', { class: 'small muted', text: promise + bars }),
    ]);
  }
  function familiesCard() {
    const D = P.data;
    const L = P.layer;
    const fam = D.families || [];
    const rows = fam.map((f) => {
      const c = ((D.counts || {})[f.id] || {})[L] || {};
      return el('tr', { 'data-family': f.id }, [el('th', { text: f.id === 'all' ? 'Every stat test the Monolith runs' : f.label }),
        el('td', { class: 'num', 'data-label': 'tests', text: fmt(c.m) }),
        el('td', { class: 'num', 'data-label': 'p < .05', text: fmt(c.uncorrected) + ' (chance ' + fmt(Math.round(c.chance || 0)) + ')' }),
        el('td', { class: 'num', 'data-label': 'Bonferroni', text: fmt(c.bonferroni) }),
        el('td', { class: 'num', 'data-label': 'Holm', text: fmt(c.holm) }),
        el('td', { class: 'num', 'data-label': 'BH', text: fmt(c.bh) }),
        el('td', { class: 'num', 'data-label': 'max-t', text: fmt(c.maxt) })]);
    });
    const fn = (D.funnel || {})[L] || [];
    const FSAY = { tested: 'Every stat test run', p05: 'p < .05, uncorrected', replicated: 'and in both pairs, AB and CD, the same way',
                   layers: 'and in Raw and Minus FP alike', cluster: 'and in a run of frequencies that survives', bh: 'or, instead, Benjamini–Hochberg q < .05' };
    const fmax = Math.max(1, ...fn.map((s) => s.n));
    const funnel = el('div', { class: 'narfunnel', id: 'narfunnel' }, fn.map((s) => el('div', { class: 'fstep', 'data-step': s.id }, [
      el('span', { class: 'fl', text: FSAY[s.id] || s.id }), logbar(s.n, fmax), el('b', { text: fmt(s.n) })])));
    const rp = D.replication || {};
    const rfig = rp.counts ? hist(rp.counts.slice(1), [
      { id: 'expected', v: rp.expected_independent, label: 'if the pairs were independent', color: css('--ink-3'), dash: true },
      { id: 'observed', v: rp.observed, label: 'the rats as they are', color: css('--up') }], 'Stat tests passing in both pairs, in every shuffle (' + (rp.n - 1) + ')')
      : null;
    const cl = (D.cluster || {})[L] || {};
    const S0 = S();
    const meth = (id) => (S0.methods.find((m) => m.id === id) || {}).label || id;
    const win = (id) => (S0.windows.find((w) => w.id === id) || {}).label || id;
    const runs = (cl.top || []).filter((x) => x.p <= 0.05).slice(0, 10);
    return section('narfamilies', 'Ways to narrow it down', 'narrow.families', [
      seg([['raw', 'Raw'], ['minus_fp', 'Minus FP']], L, (id) => { P.layer = id; render(); }, 'narlayer2'),
      el('h3', { text: '1. Ask fewer questions, chosen before looking' }),
      el('p', { class: 'small', text: 'A correction’s bar falls with the number of tests. Deciding the family first — the named bands, the cue windows, '
        + 'one measure of each kind — keeps the bar within reach. It only counts if the family is chosen before the results are seen.' }),
      el('div', { class: 'dtwrap' }, [el('table', { class: 'linetable narfam', id: 'narfamtbl' }, [
        el('thead', {}, [el('tr', {}, ['Family', 'Tests', 'p < .05', 'Bonferroni', 'Holm', 'BH', 'max-t'].map((h) => el('th', { text: h })))]),
        el('tbody', {}, rows)])]),
      el('h3', { text: '2. Ask more of each finding' }),
      el('p', { class: 'small', text: 'A real change should show at neighbouring frequencies, in both of a rat’s pairs (AB and CD are separate '
        + 'trials), and Raw or Minus FP. Each step keeps only what passed the one before.' }),
      funnel,
      rfig ? el('div', { class: 'physhists' }, [(() => {
        const say = fmt(rp.observed) + ' stat tests pass in AB and in CD the same way (Raw); if the two pairs were independent, '
          + 'about ' + fmt(Math.round(rp.expected_independent)) + ' would. Against the same shuffle of both pairs, that ranks ' + rp.rank + ' of ' + rp.n
          + ': ' + rankWord(rp) + '.';
        const X = window.MONO_EXPLAIN;
        if (!X) return el('div', { 'data-perm': 'replication' }, [rfig, el('p', { class: 'small muted', text: say })]);
        const h = el('div', { 'data-perm': 'replication' });
        const p = X.shuffle(h, { counts: rp.counts, realIndex: 0, observed: rp.observed, rank: rp.rank, expected: rp.expected_independent, kind: 'sign',
                                 rats: (D.rats || []).map((r) => 'r' + r), realLabel: 'the real rats',
                                 title: 'Stat tests passing in both pairs, in every shuffle (' + (rp.n - 1) + ')',
                                 say: 'Each shuffle flips the same rats in AB and in CD, and counts what passes in both.', rankSay: say });
        X.playOnce('nar-shuf-rep', h, p);
        return h;
      })()]) : null,
      el('h3', { text: '3. Read runs of frequencies, not single bands' }),
      runs.length ? el('ol', { class: 'narruns', id: 'narruns' }, runs.map((x) => el('li', {}, [
        el('b', { text: short(x.a) + ' – ' + short(x.b) }), ' · ' + win(x.w) + ' · ' + meth(x.m) + ' · ' + x.from_hz + '–' + x.to_hz + ' Hz ('
          + x.n_bands + ' bands, ' + (x.sign > 0 ? 'up' : 'down') + ') · p ' + fp(x.p)])))
        : el('p', { class: 'small muted', id: 'narruns', text: 'No run of frequencies survives in ' + LAYER_SAY[L] + '.' }),
    ]);
  }
  function leadsCard() {
    const D = P.data;
    const S0 = S();
    const kind = P.leads;
    const L = kind === 'monolith_m' ? 'minus_fp' : 'raw';
    const list = (((D.leads || {})[kind === 'contrast' ? 'contrast' : 'monolith']) || {})[L] || [];
    const n = P.all ? list.length : Math.min(10, list.length);
    const win = (id) => (S0.windows.find((w) => w.id === id) || {}).label || id;
    const meth = (id) => (S0.methods.find((m) => m.id === id) || {}).label || id;
    const band = (t) => (t.hz ? t.hz + ' Hz' : ((S0.bands.find((b) => b.id === t.band) || {}).label || t.band));
    const pass = (v) => v != null && v < 0.05;
    const kept = (t) => [['BH', pass(t.bh_q)], ['Holm', pass(t.holm_p)], ['max-t', t.maxt_p != null && t.maxt_p <= 0.05],
                         ['cluster', t.cluster && t.cluster.p <= 0.05], ['both pairs', t.rep && t.rep.replicated],
                         ['Raw and Minus FP', t.other && pass(t.other.p) && Math.sign(t.other.est) === Math.sign(t.est)]].filter((x) => x[1]).map((x) => x[0]);
    const rows = list.slice(0, n).map((t, i) => {
      const k = kept(t);
      const tr = el('tr', { class: 'lead', 'data-rank': String(i + 1), tabindex: '0' }, [
        el('td', { class: 'num rank', text: String(i + 1) }),
        el('td', { class: 'lead-name' }, [el('div', { text: short(t.a) + ' – ' + short(t.b) }),
          el('div', { class: 'small muted', text: win(t.w) + ' · ' + band(t) + ' · ' + meth(t.m) })]),
        el('td', { class: 'num', 'data-label': 'change (t-test p)', text: f3(t.est) + ' (p ' + fp(t.p) + ')' }),
        el('td', { class: 'num', 'data-label': 'exact permutation', text: fp(t.perm_p) }),
        el('td', { class: 'num', 'data-label': 'sign test', text: fp(t.sign_p) + ' (' + t.same + '/' + t.k + ')' }),
        el('td', { class: 'num', 'data-label': 'BH q', text: fp(t.bh_q) }),
        el('td', { class: 'num', 'data-label': 'Holm', text: fp(t.holm_p) }),
        el('td', { class: 'num', 'data-label': 'max-t', text: fp(t.maxt_p) }),
        el('td', { class: 'num', 'data-label': 'frequency run', text: t.cluster ? (t.cluster.from_hz === t.cluster.to_hz ? t.cluster.from_hz : t.cluster.from_hz + '–' + t.cluster.to_hz)
          + ' Hz, p ' + fp(t.cluster.p) : 'no run' }),
        el('td', { class: 'num', 'data-label': 'AB · CD', text: t.rep ? fp(t.rep.ab_p) + ' · ' + fp(t.rep.cd_p) : '—' }),
        el('td', { class: 'num', 'data-label': 'Raw/Minus FP, other', text: t.other ? fp(t.other.p) : '—' }),
        el('td', { class: 'kept', 'data-label': 'survives' }, k.length ? k.map((x) => el('span', { class: 'chip', text: x })) : [el('span', { class: 'muted', text: 'none' })]),
      ]);
      const go = () => {
        const w0 = S0.windows.find((w) => w.id === t.w);
        M().showTab(w0 && w0.kind === 'contrast' ? 'c21' : 'main');
        M().go(Object.assign({}, t, { layer: L, split: 'all' }));
      };
      tr.addEventListener('click', go);
      tr.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
      return tr;
    });
    const tally = {};
    for (const t of list) for (const k of kept(t)) tally[k] = (tally[k] || 0) + 1;
    return section('narleads', 'Every test, on each top result', 'narrow.leads', [
      seg([['monolith', 'The Monolith · Raw'], ['monolith_m', 'The Monolith · Minus FP'], ['contrast', 'Cue 2 − Cue 1']], kind,
        (id) => { P.leads = id; P.all = false; render(); }, 'narleadsel'),
      el('p', { class: 'small', id: 'narleadsay', text: 'Of these ' + list.length + ' top results: '
        + ['BH', 'Holm', 'max-t', 'cluster', 'both pairs', 'Raw and Minus FP'].map((x) => (tally[x] || 0) + ' ' + x).join(', ')
        + '. The exact permutation and sign tests cannot go below .0078 with eight rats; read them as “as strong as eight rats can show”, '
        + 'not corrected.' }),
      el('div', { class: 'dtwrap' }, [el('table', { class: 'linetable narleadtbl', id: 'narleadtbl' }, [
        el('thead', {}, [el('tr', {}, ['#', 'Top result', 'Change (t-test p)', 'Exact permutation p', 'Sign test p', 'BH q', 'Holm p', 'max‑t p',
          'Frequency run', 'AB · CD p', 'Other of Raw/Minus FP p', 'Survives'].map((h) => el('th', { text: h })))]),
        el('tbody', {}, rows)])]),
      list.length > 10 ? el('button', { type: 'button', class: 'more-btn', id: 'narall', text: P.all ? 'Show the top 10' : 'Show all ' + list.length,
                                        onclick: () => { P.all = !P.all; render(); } }) : null,
      el('p', { class: 'small muted', title: '“Survives” lists what it passes: Benjamini–Hochberg q < .05, Holm p < .05, the permutation max-t, a run of '
        + 'neighbouring frequencies that survives, p < .05 in both pairs the same way, and in Raw and Minus FP.', text: 'Click one to open it on the Monolith.' }),
    ]);
  }
  // What survives, as a circuit, for a view chosen here.
  const CMETHODS = [['uncorrected', 'Uncorrected'], ['bh', 'BH q < .05'], ['holm', 'Holm'], ['maxt', 'max-t'], ['clusters', 'Frequency runs'],
                    ['perm', 'Exact permutation'], ['rep', 'Both pairs']];
  const passOf = (id, v) => ({
    uncorrected: (x) => x.hk_p < 0.05, bh: (x) => x.bh_q < 0.05, holm: (x) => x.holm_p < 0.05, maxt: (x) => x.maxt_p <= 0.05,
    clusters: (x) => x.cluster_p <= 0.05, perm: (x) => x.perm_p < 0.05, rep: (x) => x.rep === 1 }[id])(v);
  function viewNow() {
    const S0 = S(), st = M().state;
    const v = P.view || {};
    P.view = {
      w: S0.windows.some((w) => w.id === v.w) ? v.w : (S0.windows.some((w) => w.id === st.win) ? st.win : 'cue1'),
      b: S0.bands.some((b) => b.id === v.b) ? v.b : st.band,
      m: S0.methods.some((m) => m.id === v.m) ? v.m : st.method,
      layer: v.layer === 'raw' || v.layer === 'minus_fp' ? v.layer : st.layer,
    };
    if ((S0.windows.find((w) => w.id === P.view.w) || {}).kind === 'contrast') P.view.layer = 'raw';
    return P.view;
  }
  function circuitCard() {
    const S0 = S(), v = viewNow();
    const pick = (label, id, opts, cur, on) => el('label', { class: 'pctl' }, [el('span', { class: 'lab', text: label }),
      el('select', { id, onchange: (e) => on(e.target.value) }, opts.map(([x, text]) =>
        el('option', { value: x, selected: String(x) === String(cur) ? 'selected' : null, text })))]);
    const set = (patch) => { Object.assign(P.view, patch); render(); };
    const card = section('narcirc', 'What survives, as a circuit', 'narrow.circuit', [
      seg(CMETHODS, P.method, (id) => { P.method = id; render(); }, 'narmethod'),
      el('div', { class: 'progctl' }, [
        pick('Window', 'narw', S0.windows.map((w) => [w.id, w.label]), v.w, (x) => set({ w: x })),
        pick('Frequency', 'narb', S0.bands.map((b) => [b.id, b.named ? b.label : b.hz + ' Hz']), v.b, (x) => set({ b: x })),
        pick('Measure', 'narm', S0.methods.map((m) => [m.id, m.label]), v.m, (x) => set({ m: x })),
        (S0.windows.find((w) => w.id === v.w) || {}).kind === 'contrast' ? el('span', { class: 'small muted', text: 'Raw only' })
          : pick('', 'narl', [['raw', 'Raw'], ['minus_fp', 'Minus FP']], v.layer, (x) => set({ layer: x })),
      ]),
      el('div', { id: 'narcircsvg' }),
      el('p', { class: 'small muted', id: 'narcircsay' }),
    ]);
    drawCircuit();
    return card;
  }
  async function drawCircuit() {
    const S0 = S(), v = viewNow();
    const seq = ++P.cseq;
    let A;
    try { A = await arrayOf(v.layer); } catch (e) {
      const h0 = $('narcircsvg');
      if (h0) h0.textContent = 'Could not read narrow_' + v.layer + ': ' + e.message;
      return;
    }
    if (seq !== P.cseq) return;
    const host = $('narcircsvg');
    if (!host) return;
    host.innerHTML = '';
    const w = S0.windows.findIndex((x) => x.id === v.w), b = S0.bands.findIndex((x) => x.id === v.b), m = S0.methods.findIndex((x) => x.id === v.m);
    const Wd = 520, Hd = 470, cx = 260, cy = 236, R = 170;
    const regs = S0.regions;
    const pos = regs.map((_r, i) => { const a = -Math.PI / 2 + (i + 0.5) * (2 * Math.PI / regs.length); return { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a), a }; });
    const edges = S0.pairs.map(([pa, pb], p) => {
      const x = {};
      for (const q of NQ) x[q] = at(A, QI[q], w, b, m, p);
      return Object.assign({ p, pa, pb }, x);
    });
    const tested = edges.filter((e) => isFinite(e.hk_p));
    const shown = tested.filter((e) => passOf(P.method, e));
    const unc = tested.filter((e) => e.hk_p < 0.05).length;
    const max = Math.max(1e-12, ...tested.map((e) => Math.abs(e.est)));
    const svg = sv('svg', { viewBox: '0 0 ' + Wd + ' ' + Hd, width: '100%', class: 'mfig narcircuit', role: 'img', style: 'max-width:' + Wd + 'px',
                            'aria-label': shown.length + ' of ' + tested.length + ' region pairs survive' });
    svg.appendChild(sv('circle', { cx, cy, r: R, fill: 'none', stroke: css('--ring') }));
    for (const e of shown.sort((x, y) => Math.abs(x.est) - Math.abs(y.est))) {
      const A0 = pos[e.pa], B0 = pos[e.pb];
      const mx = (A0.x + B0.x) / 2, my = (A0.y + B0.y) / 2;
      const qx = cx + (mx - cx) * 0.35, qy = cy + (my - cy) * 0.35;
      const path = sv('path', { d: 'M' + A0.x.toFixed(1) + ',' + A0.y.toFixed(1) + ' Q' + qx.toFixed(1) + ',' + qy.toFixed(1) + ' ' + B0.x.toFixed(1) + ',' + B0.y.toFixed(1),
        fill: 'none', stroke: css(e.est >= 0 ? '--up' : '--down'), 'stroke-width': (1.2 + 5 * Math.abs(e.est) / max).toFixed(2), 'stroke-opacity': 0.9,
        class: 'nedge', 'data-pair': String(e.p) });
      M().hover(path, [regs[e.pa] + ' – ' + regs[e.pb], 'change ' + f3(e.est) + ', t-test p ' + fp(e.hk_p),
        'BH q ' + fp(e.bh_q) + ' · Holm ' + fp(e.holm_p) + ' · max-t ' + fp(e.maxt_p),
        'exact permutation ' + fp(e.perm_p) + ' · run of frequencies ' + (isFinite(e.cluster_p) ? fp(e.cluster_p) : 'none')]);
      svg.appendChild(path);
    }
    regs.forEach((name0, i) => {
      const p0 = pos[i];
      svg.appendChild(sv('circle', { cx: p0.x.toFixed(1), cy: p0.y.toFixed(1), r: 6, fill: css('--node'), stroke: css('--surface'), 'stroke-width': 2 }));
      const lx = cx + (R + 14) * Math.cos(p0.a), ly = cy + (R + 14) * Math.sin(p0.a);
      const anchor = Math.abs(Math.cos(p0.a)) < 0.2 ? 'middle' : (Math.cos(p0.a) > 0 ? 'start' : 'end');
      svg.appendChild(sv('text', { x: lx.toFixed(1), y: (ly + 4).toFixed(1), 'text-anchor': anchor, 'font-size': 12, fill: css('--ink-2') }, short(name0)));
    });
    host.appendChild(svg);
    $('narcircsay').textContent = shown.length + ' of ' + tested.length + ' tested region pairs survive “' + (CMETHODS.find((x) => x[0] === P.method) || [0, ''])[1]
      + '” here; uncorrected, ' + unc + ' pass p < .05 (about ' + (0.05 * tested.length).toFixed(1) + ' by chance). Red: up from Precon1 to Precon4; blue: down; '
      + 'thicker, a bigger change.';
  }

  function render() {
    const pane = $('narrowpane');
    if (!pane) return;
    pane.innerHTML = '';
    if (P.loading && !P.data) { pane.appendChild(el('p', { class: 'loading', text: 'Reading the corrections' })); return; }
    if (!P.data) {
      pane.appendChild(section('narintro', 'Narrowing down', 'narrow', [
        el('p', { text: 'This build of the Monolith has not been narrowed down yet. It is worked out here, from the arrays already fetched, in a '
          + 'few minutes: every shuffle of the eight rats, pooled as the Monolith pools, Raw and Minus FP.' }),
        window.MONO_STATIC ? el('p', { class: 'small muted', text: 'Not in this copy: it opens in Jarvis.' })
          : el('button', { type: 'button', class: 'more-btn', id: 'narrowmake', disabled: P.making ? 'disabled' : null,
                           text: P.making ? 'Working: ' + (P.makeNote || 'starting') : 'Work it out now', onclick: make }),
        P.makeErr ? el('p', { class: 'small warn', text: P.makeErr }) : null,
      ]));
      return;
    }
    pane.appendChild(intro());
    pane.appendChild(howCard());
    pane.appendChild(globalCard());
    pane.appendChild(correctCard());
    pane.appendChild(familiesCard());
    pane.appendChild(leadsCard());
    pane.appendChild(circuitCard());
  }
  function show() {
    if (!P.data && !P.loading) load(); else render();
  }
  return {
    show, render, load, make,
    get state() { return { layer: P.layer, leads: P.leads, all: P.all, method: P.method, view: P.view ? Object.assign({}, P.view) : null,
                           data: P.data, err: P.err, making: P.making }; },
  };
})();
