/* ==========================================================================
   monolith_evenmore.js -- the Monolith page's eleventh tab: Narrowing down
   (even more) (Shahriar, 2026-10-28; the final stage's additions
   2026-10-30).

   Dickson 2022's Figure 3 on our rats, as the lab's Coherence Analysis
   Plan lays it out: ten region pairs, Early (Precon1) against Late
   (Precon4), theta and gamma, each pair alone and then all ten together;
   phase 2, cue 1 against cue 2 on each day; and coherence in the power
   plan's three periods (baseline, cue 1, cue 2). A GEE decides every
   significance; the figures are for looking. Everything is worked out by
   backend/evenmore.py; this file shows it, with the flag the user asked
   for on the pooled spectra.

   The switch (MONO_FDR, shared with tab 12): with the correction on, a
   result passes at FDR q < 0.05; off, at p < 0.05. Every star, table and
   figure follows it (each figure is drawn both ways).
   ========================================================================== */
'use strict';

/* The correction switch, one for tabs 11 and 12 (and remembered). */
window.MONO_FDR = (function () {
  const KEY = 'barry.final.fdr';
  let mode = 'fdr';
  try { if (localStorage.getItem(KEY) === 'raw') mode = 'raw'; } catch (e) { /* none */ }
  function set(m) {
    mode = m === 'raw' ? 'raw' : 'fdr';
    try { localStorage.setItem(KEY, mode); } catch (e) { /* none */ }
    document.dispatchEvent(new CustomEvent('mono:fdr', { detail: mode }));
  }
  /* Does a test pass under the switch: {p, q}. */
  const passes = (x) => !!x && (mode === 'fdr' ? x.q != null && x.q < 0.05 : x.p != null && x.p < 0.05);
  function node(el, id) {
    const b = (m, say) => el('button', { type: 'button', class: 'moretile' + (mode === m ? ' on' : ''), id: id + '_' + m,
                                        'aria-pressed': mode === m ? 'true' : 'false', text: say, onclick: () => set(m) });
    return el('div', { class: 'morefdr', role: 'group', 'aria-label': 'Correction for many tests' }, [
      el('span', { class: 'morefdrsay', text: 'Stars and follow-ups:' }),
      b('fdr', 'Corrected (FDR q < 0.05)'), b('raw', 'Uncorrected (p < 0.05)')]);
  }
  return { get: () => mode, set, passes, node };
})();

window.MONO_EVENMORE = (function () {
  const M = () => window.MONO;
  const F = () => window.MONO_FDR;
  const P = { data: null, err: null, loading: false, seq: 0, making: false, makeNote: '', makeErr: null, band: 'theta' };
  const $ = (id) => document.getElementById(id);
  const el = (...a) => M().el(...a);
  const FILE = (name, save) => '/api/arc/monolith/evenmore/file/' + encodeURIComponent(name) + (save ? '?download=1' : '');
  const BAND_KEY = 'barry.evenmore.band';
  try { const b = localStorage.getItem(BAND_KEY); if (b === 'theta' || b === 'gamma') P.band = b; } catch (e) { /* none */ }

  const pSay = (p) => (p == null ? 'p n/a' : p < 0.001 ? 'p < 0.001' : 'p = ' + p.toFixed(3));
  const n3 = (x) => (x == null || !isFinite(x) ? 'n/a' : x.toFixed(3));
  const n2 = (x) => (x == null || !isFinite(x) ? 'n/a' : x.toFixed(2));
  const star = (x) => (F().passes(x) ? ' *' : '');
  const when = (s) => { try { return new Date(s).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' }); } catch (e) { return s; } };

  function card(id, title, help, kids, cls) {
    return el('div', { class: 'card' + (cls ? ' ' + cls : ''), id }, [el('div', { class: 'hrow' }, [el('h2', { text: title }), help ? M().qh(help) : null])].concat(kids));
  }

  async function load() {
    const seq = ++P.seq;
    P.loading = true;
    render();
    try {
      const got = await M().getJSON('/data/evenmore');
      if (seq !== P.seq) return;
      P.data = got; P.err = null;
    } catch (e) {
      if (seq !== P.seq) return;
      P.data = null; P.err = e.message;
    }
    P.loading = false;
    render();
  }

  async function make() {
    if (P.making) return;
    P.making = true; P.makeErr = null; P.makeNote = '';
    render();
    try {
      await M().runHere('/evenmore', { confirm: true }, (note) => {
        P.makeNote = note;
        const b = $('moremake');
        if (b) b.textContent = 'Working: ' + note;
      });
    } catch (e) {
      P.makeErr = /404|not found/i.test(e.message) ? 'Jarvis is running older code without this button: restart it, then press it again.'
        : 'It could not be done: ' + e.message;
    }
    P.making = false;
    load();
  }

  function setBand(b) {
    P.band = b;
    try { localStorage.setItem(BAND_KEY, b); } catch (e) { /* none */ }
    render();
  }

  /* ---------------- the top: what this is, and the button ---------------- */
  function intro(D) {
    const pairs = D ? D.pairs : [];
    return card('morehead', '11 · Narrowing down (even more)', 'more', [
      el('p', { text: 'Dickson 2022’s Figure 3 on our rats: ten region pairs, Early (Precon1) against Late (Precon4), in theta and gamma; '
        + 'each pair alone, then all ten together; then cue 1 against cue 2 on each day, and coherence in the baseline, cue 1 and cue 2. A GEE decides what is significant; the pictures are for looking.' }),
      el('details', { class: 'moremore' }, [
        el('summary', { text: 'More' }),
        el('ul', { class: 'moresteps' }, [
          el('li', { text: 'The regions: RSC, dHC, ACC, OFC and PER, each with each (POR is out: no probe reached it). Ten pairs, in the plan’s order.' }),
          el('li', { text: 'Both sides of the brain: within a rat, a pair is the mean of its valid wire pairs, same side (ipsi) and across (contra) alike, each counting the same. '
            + 'Valid means histology v2 scored both probes “y”. Left RSC with right RSC (homotopic) is never used.' }),
          el('li', { text: 'The windows: each trial’s cue pair (cue 1 + cue 2, 20 s) for Early against Late; cue 1 and cue 2 for phase 2; the 10 s baseline, cue 1 and cue 2 for the periods. Every Precon trial is a matched pairing (A→B or C→D); they are pooled.' }),
          el('li', { text: 'Coherence as Dickson computes it (Jeremy’s mscohere: a 59–61 Hz notch, 1 s Hann pieces half overlapping, at 1 kHz), on the wires tab 8 chose. '
            + 'Theta at 0.49 Hz steps (the paper’s), gamma in 2 Hz steps without 59–61 Hz.' }),
          el('li', { text: 'The test: a GEE (Gamma family, log link, exchangeable, the rat as the cluster). A test of up to two things (2 df) uses the robust errors with a small-sample correction; '
            + 'a test of more uses the model’s own errors. Ten pairs are corrected together (FDR), and the switch below turns that on or off everywhere.' }),
        ])]),
      pairs.length ? el('div', { class: 'morepairs' }, pairs.map((p) => el('span', { class: 'morepair' }, [
        el('span', { class: 'moresw' + (p.dashed ? ' dashed' : ''), style: '--c:' + p.color }), (p.id + 1) + ' ' + p.say]))) : null,
      el('div', { class: 'row gap moretools' }, [
        el('button', { type: 'button', class: 'more-btn', id: 'moremake', disabled: P.making ? 'disabled' : null, onclick: make,
                       text: P.making ? 'Working: ' + (P.makeNote || 'starting') : D ? 'Work it out again' : 'Work it out' }),
        D ? el('span', { class: 'small muted', text: 'Made ' + when(D.at) + ' from ' + D.rats.length + ' rats, ' + Object.keys(D.trials).length + ' rat-days.' }) : null]),
      P.makeErr ? el('p', { class: 'warn', id: 'moreerr', text: P.makeErr }) : null]);
  }

  /* ---------------- the flag ---------------- */
  function flag(D) {
    const rows = [];
    for (const b of ['theta', 'gamma']) {
      for (const d of ['Precon1', 'Precon4']) {
        const f = (D.flag[b] || {})[d] || {};
        const less = f.trialmean ? 100 * (1 - f.pooled / f.trialmean) : null;
        rows.push(el('tr', {}, [el('th', { text: (b === 'theta' ? 'Theta' : 'Gamma') + ', ' + d }), el('td', { text: n3(f.pooled) }),
          el('td', { text: n3(f.trialmean) }), el('td', { text: less == null ? 'n/a' : Math.round(less) + '% lower' })]));
      }
    }
    const segs = Object.values(D.segments || {});
    const fewest = segs.length ? Math.min(...segs.filter((x) => x > 0)) : null;
    return card('moreflag', 'Read this first', null, [
      el('div', { class: 'moreflagitem' }, [
        el('h3', { text: 'Pooled spectra, not the mean of trials' }),
        el('p', { text: 'Within each rat and day, every 1 s piece of every trial goes into one spectrum before coherence is taken. Dickson and tabs 8 and 9 take one coherence a trial and average them. '
          + 'Pooling is less biased, but it is only high when the two regions keep the same timing across trials. So pooled values sit below the mean of trials:' }),
        el('div', { class: 'tablewrap' }, el('table', { class: 'moretable' }, [
          el('thead', {}, el('tr', {}, [el('th', { text: 'Mean over rats and pairs' }), el('th', { text: 'Pooled' }), el('th', { text: 'Mean of trials' }), el('th', { text: 'Pooled is' })])),
          el('tbody', {}, rows)])),
        fewest ? el('p', { class: 'small muted', text: 'Clipping leaves some rat-days few trials to pool: in one, even its best-covered wire pair has only ' + fewest
          + ' one-second pieces (about ' + Math.max(1, Math.round(fewest / 38)) + ' trials of 20 s).' }) : null]),
      el('div', { class: 'moreflagitem' }, [
        el('h3', { text: 'Tests of many things at once are weak here' }),
        el('p', { text: 'With 8 rats, the robust errors can test only one or two things at a time. Pair, Session × Pair and anything with Frequency use the model’s own errors instead, '
          + 'which lean on its assumptions; they are greyed out below. Trust each pair’s Late against Early, Session × Cue and Session × Period, and read the robustness card: '
          + 'with 5 or 6 rats a GEE can read stronger than it is.' })])], 'moreflag');
  }

  /* ---------------- the stats tables ---------------- */
  function termsTable(ts, err) {
    if (err) return el('p', { class: 'warn', text: 'Not fitted: ' + err });
    return el('div', { class: 'tablewrap' }, el('table', { class: 'moretable moreterms' }, [
      el('thead', {}, el('tr', {}, ['Term', 'χ²', 'df', 'p', 'Errors'].map((t) => el('th', { text: t })))),
      el('tbody', {}, (ts || []).map((t) => {
        const robust = t.errors !== 'model-based';
        return el('tr', { class: (robust ? '' : 'weak') + (robust && t.p < 0.05 ? ' sig' : '') }, [
          el('th', { text: t.term }), el('td', { text: n2(t.chi2) }), el('td', { text: String(t.df) }), el('td', { text: pSay(t.p) }),
          el('td', { text: robust ? 'robust' : 'model-based' })]);
      }))]));
  }

  const sw = (D, i) => el('span', { class: 'moresw' + (D.pairs[i].dashed ? ' dashed' : ''), style: '--c:' + D.pairs[i].color });

  function pairs1(D, B) {
    return el('div', { class: 'tablewrap' }, el('table', { class: 'moretable', id: 'moretable1' }, [
      el('thead', {}, el('tr', {}, ['Pair', 'Rats', 'Wire pairs', 'Late ÷ Early', 'χ²(1)', 'p', 'FDR q', 'Session × frequency'].map((t) => el('th', { text: t })))),
      el('tbody', {}, B.phase1.pairs.map((x, i) => {
        if (!x) return el('tr', { class: 'weak' }, [el('th', {}, [sw(D, i), D.pairs[i].say]), el('td', { colspan: '7', text: 'fewer than 4 rats' })]);
        const a = x.a2 || {};
        const sf = (x.b2 || []).find((t) => t.term === 'Session × Frequency');
        const w = D.pairs[i].wires || {};
        return el('tr', { class: F().passes(a) ? 'sig' : '' }, [
          el('th', {}, [sw(D, i), D.pairs[i].say]), el('td', { text: String(x.rats.length) }),
          el('td', { text: (w.ipsi || 0) + ' ipsi, ' + (w.contra || 0) + ' contra' }),
          el('td', { text: a.ratio == null ? (x.a2_error || 'n/a') : '×' + a.ratio.toFixed(2) + (a.ratio > 1 ? ' ▲' : ' ▼') }),
          el('td', { text: n2(a.chi2) }), el('td', { text: pSay(a.p) }), el('td', { text: n3(a.q) + star(a) }),
          el('td', { class: 'weakcell', text: sf ? pSay(sf.p) + ', q ' + n3(x.b2_q) : 'n/a' })]);
      }))]));
  }

  function pairs2(D, B) {
    return el('div', { class: 'tablewrap' }, el('table', { class: 'moretable', id: 'moretable2' }, [
      el('thead', {}, el('tr', {}, ['Pair', 'Rats', 'Session × Cue', 'FDR q', 'Cue 2 ÷ Cue 1, Precon1', 'Cue 2 ÷ Cue 1, Precon4'].map((t) => el('th', { text: t })))),
      el('tbody', {}, B.phase2.pairs.map((x, i) => {
        if (!x) return el('tr', { class: 'weak' }, [el('th', {}, [sw(D, i), D.pairs[i].say]), el('td', { colspan: '5', text: 'fewer than 4 rats' })]);
        const sc = (x.terms || []).find((t) => t.term === 'Session × Cue');
        const scx = { p: sc ? sc.p : null, q: x.q };
        const day = (d) => { const r = x.days[d] || {}; return r.ratio == null ? (r.error || 'n/a') : '×' + r.ratio.toFixed(2) + ', ' + pSay(r.p) + ', q ' + n3(r.q) + star(r); };
        return el('tr', { class: F().passes(scx) ? 'sig' : '' }, [
          el('th', {}, [sw(D, i), D.pairs[i].say]), el('td', { text: String(x.rats.length) }),
          el('td', { text: sc ? 'χ² ' + n2(sc.chi2) + ', ' + pSay(sc.p) : (x.error || 'n/a') }), el('td', { text: n3(x.q) + star(scx) }),
          el('td', { text: day('Precon1') }), el('td', { text: day('Precon4') })]);
      }))]));
  }

  const CONTRASTS = [['cue1-base10', 'Cue 1 vs baseline'], ['cue2-base10', 'Cue 2 vs baseline'], ['cue2-cue1', 'Cue 2 vs cue 1']];

  function pairs3(D, B) {
    const ph = (B.phase3 || {}).pairs || [];
    return el('div', { class: 'tablewrap' }, el('table', { class: 'moretable', id: 'moretable3' }, [
      el('thead', {}, el('tr', {}, ['Pair', 'Rats', 'Session × Period, χ²(2)', 'FDR q'].concat(CONTRASTS.map((c) => 'Session × (' + c[1].toLowerCase() + ')')).map((t) => el('th', { text: t })))),
      el('tbody', {}, ph.map((x, i) => {
        if (!x) return el('tr', { class: 'weak' }, [el('th', {}, [sw(D, i), D.pairs[i].say]), el('td', { colspan: '6', text: 'fewer than 4 rats' })]);
        const sp = x.sp || {};
        const any = F().passes(sp) || CONTRASTS.some((c) => F().passes(x.contrasts[c[0]]));
        return el('tr', { class: any ? 'sig' : '' }, [
          el('th', {}, [sw(D, i), D.pairs[i].say]), el('td', { text: String(x.rats.length) }),
          el('td', { text: sp.p == null ? (x.error || 'n/a') : n2(sp.chi2) + ', ' + pSay(sp.p) }), el('td', { text: n3(sp.q) + star(sp) })]
          .concat(CONTRASTS.map((c) => { const r = x.contrasts[c[0]] || {}; return el('td', { text: r.ratio == null ? 'n/a' : '×' + r.ratio.toFixed(2) + ', ' + pSay(r.p) + ', q ' + n3(r.q) + star(r) }); })));
      }))]));
  }

  /* ---------------- robustness: leave one rat out, and the mixed model ---------------- */
  function robustTable(items, nameOf, id) {
    const rows = (items || []).filter((r) => (r.passes || {})[F().get()]);
    if (!rows.length) return el('p', { class: 'muted', id, text: 'Nothing passes on this side of the switch, so nothing to check.' });
    return el('div', { class: 'tablewrap' }, el('table', { class: 'moretable', id }, [
      el('thead', {}, el('tr', {}, ['Result', 'GEE', 'Leave one rat out', 'Linear mixed model', 'Verdict'].map((t) => el('th', { text: t })))),
      el('tbody', {}, rows.map((r) => {
        const t = r.test || {};
        const eff = t.ratio != null ? '×' + t.ratio.toFixed(2) : t.diff != null ? (t.diff >= 0 ? '+' : '−') + Math.abs(t.diff).toFixed(2) + ' dB' : '';
        const lm = r.lmm || {};
        const lmOk = lm.p != null && lm.p < 0.05;
        const ok = r.survives && lmOk;
        return el('tr', { class: ok ? 'sig' : '' }, [
          el('th', { text: nameOf(r) }),
          el('td', { text: [eff, pSay(t.p), t.q != null ? 'q ' + n3(t.q) : ''].filter(Boolean).join(', ') }),
          el('td', { text: r.survives ? 'holds without any one rat' : 'fails without J' + (r.worst || {}).rat + ' (' + pSay((r.worst || {}).p) + ')' }),
          el('td', { text: lm.p == null ? (lm.error || 'not fitted') : 'F(' + lm.df1 + ', ' + lm.df2 + ') = ' + n2(lm.F) + ', ' + pSay(lm.p) }),
          el('td', { text: ok ? 'solid' : r.survives || lmOk ? 'shaky' : 'fragile' })]);
      }))]));
  }
  const nameOf11 = (D) => (r) => D.pairs[r.pair].say + ', ' + r.band + ': ' + r.label;

  /* ---------------- a figure ---------------- */
  function filesOf(f) {
    return F().get() === 'raw' && f.files_raw ? Object.assign({}, f.files, f.files_raw) : f.files;
  }
  const passOf = (f) => (f.passes && typeof f.passes === 'object' ? !!f.passes[F().get()] : !!f.passes);

  function figCard(D, f) {
    const no = 'D' + f.id.replace(/_/g, '.');           // D for Dickson: Joe's site has tab 9's Figure 1.1 too
    const name = f.kind === 'pooled' ? 'All ten pairs' : D.pairs[f.pair].say;
    const files = filesOf(f) || {};
    const link = (k, say) => (files[k] ? el('a', { class: 'more-btn small', href: FILE(files[k], true), download: files[k], text: say }) : null);
    return el('div', { class: 'morefig' + (f.kind === 'pooled' ? ' pooled' : ''), id: 'morefig_' + f.id }, [
      el('h3', {}, [el('span', {}, [el('span', { class: 'morefno', text: 'Figure ' + no }), ' · ' + name]),
        f.kind === 'pair' && passOf(f) ? el('span', { class: 'chip sig', text: F().get() === 'fdr' ? 'passes after FDR' : 'passes, uncorrected' }) : null]),
      el('a', { class: 'morefimg', href: FILE(files.svg), target: '_blank', rel: 'noopener', title: 'Open the figure on its own' },
        el('img', { src: FILE(files.svg), alt: name + ', ' + (f.legend || {}).title, loading: 'lazy' })),
      el('details', { class: 'morelegend' }, [el('summary', { text: (f.legend || {}).title || 'Legend' }), el('p', { text: (f.legend || {}).body || '' })]),
      el('div', { class: 'row gap morefiles' }, [link('pdf', 'PDF'), link('svg', 'SVG'), link('png', 'PNG'), link('xlsx', 'Prism .xlsx'), link('pzfx', 'Prism .pzfx')])]);
  }

  function figGrid(D, figs) {
    const pairs = figs.filter((f) => f.kind === 'pair');
    const pooled = figs.filter((f) => f.kind === 'pooled');
    return el('div', {}, [
      el('h3', { class: 'moresub', text: 'Each pair alone' }),
      el('div', { class: 'morefigs' }, pairs.map((f) => figCard(D, f))),
      el('h3', { class: 'moresub', text: 'All ten together, with the statistics' }),
      el('div', {}, pooled.map((f) => figCard(D, f)))]);
  }

  /* ---------------- everything ---------------- */
  function render() {
    const pane = $('morepane');
    if (!pane) return;
    if (window.MONO_STATIC) {
      pane.replaceChildren(card('morestatic', '11 · Narrowing down (even more)', null,
        [el('p', { text: 'Not in this copy: it opens in Jarvis, and its figures go to Joe through tab 10.' })]));
      return;
    }
    if (P.loading && !P.data) {
      pane.replaceChildren(el('div', { class: 'card' }, el('p', { class: 'muted', text: 'Reading tab 11.' })));
      return;
    }
    const D = P.data;
    if (!D) {
      pane.replaceChildren(intro(null), card('moremissing', 'Nothing yet', null, [
        el('p', { text: (P.err && !/404|not been/i.test(P.err) ? P.err + ' ' : '') + 'Press Work it out. It needs tab 8 worked out on this machine (it reads the wires tab 8 chose) and the recordings on the data drive.' })]));
      return;
    }
    const B = D.bands.find((b) => b.band === P.band) || D.bands[0];
    const tiles = el('div', { class: 'moretiles', role: 'group', 'aria-label': 'Band' }, D.bands.map((b) =>
      el('button', { type: 'button', class: 'moretile' + (b.band === B.band ? ' on' : ''), 'aria-pressed': b.band === B.band ? 'true' : 'false',
                     id: 'moreband_' + b.band, text: b.say, onclick: () => setBand(b.band) })));
    const ph1 = card('morephase1', 'Phase 1 · Early against Late, ' + B.say, 'more.phase1', [
      el('p', { text: 'Did each pair’s coherence in the cue pair change from Precon1 to Precon4? One row a pair; a star where it passes under the switch.' }),
      pairs1(D, B),
      el('h3', { class: 'moresub', text: 'All pairs together (the omnibus)' }),
      el('div', { class: 'moreomni' }, [
        el('div', {}, [el('h4', { text: 'On the band (A1)' }), termsTable(B.phase1.a1, B.phase1.a1_error)]),
        el('div', {}, [el('h4', { text: 'Across frequency steps (B1)' }), termsTable(B.phase1.b1, B.phase1.b1_error)])]),
      figGrid(D, B.phase1.figures)]);
    const ph2 = card('morephase2', 'Phase 2 · Cue 1 against cue 2, ' + B.say, 'more.phase2', [
      el('p', { text: 'The plan’s section 5, matched pairings only (every Precon trial is one). On each day, is coherence different in cue 2 than in cue 1, and does that difference change from Precon1 to Precon4 (Session × Cue)?' }),
      pairs2(D, B),
      el('h3', { class: 'moresub', text: 'All pairs together (Session × Cue × Pair)' }),
      termsTable(B.phase2.omnibus, B.phase2.error),
      figGrid(D, B.phase2.figures)]);
    const ph3 = B.phase3 ? card('morephase3', 'Baseline, cue 1, cue 2 · ' + B.say, 'more.phase3', [
      el('p', { text: 'The power plan’s three periods, for coherence: did the cues’ effect on each pair change from Precon1 to Precon4 (Session × Period), and against which period? A ratio of ratios above 1 means the cue raised coherence more on Precon4.' }),
      pairs3(D, B),
      figGrid(D, B.phase3.figures)]) : null;
    const rob = card('morerobust', 'Does it hold? Leave one rat out, and a mixed model', 'more.robust', [
      el('p', { text: 'For every result that passes: the GEE fitted again eight times, each without one rat, and a linear mixed model (a random intercept for the rat, Kenward–Roger’s degrees of freedom) on the same rows. Solid: it holds both ways. Shaky: one of the two. Fragile: neither.' }),
      robustTable(D.robust, nameOf11(D), 'morerobusttable')]);
    const ex = card('moreexport', 'Files', null, [
      el('p', { text: 'Every row each GEE saw, every test, and scripts that fit them again in R (geepack) and SPSS (GENLIN). Both give the plain robust errors; Jarvis adds a small-sample correction.' }),
      el('div', { class: 'row gap' }, (D.exports || []).map((n) => el('a', { class: 'more-btn small', href: '/api/arc/monolith/evenmore/export/' + encodeURIComponent(n), download: n, text: n }))),
      (D.notes || []).length ? el('details', {}, [el('summary', { text: D.notes.length + ' note' + (D.notes.length === 1 ? '' : 's') + ' from reading the recordings' }),
        el('ul', {}, D.notes.map((n) => el('li', { class: 'small', text: n })))]) : null]);
    const bar = el('div', { class: 'morebar' }, [tiles, F().node(el, 'morefdr')]);
    pane.replaceChildren(intro(D), flag(D), bar, ph1, ph2, ph3, rob, ex);
  }

  document.addEventListener('mono:fdr', () => { if ($('morepane') && !$('morepane').hidden) render(); });

  function show() {
    if (!P.data && !P.loading) load(); else render();
  }
  return { show, render, load, make, setBand, get state() { return { data: P.data, err: P.err, band: P.band, making: P.making }; } };
})();
