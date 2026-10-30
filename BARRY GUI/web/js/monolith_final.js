/* ==========================================================================
   monolith_final.js -- the Monolith page's twelfth tab: the final stage
   (Shahriar, 2026-10-30).

   What the lab's last two documents ask for, from tab 11's rat-days:
   within-region power (each region on its own), oscillation against
   background (FOOOF), which region leads (Granger) and theta-gamma
   coupling on tab 11's hits, the side question (not for Joe), the
   robustness of every result, and the methods written from the run.
   Worked out by backend/finalstage.py. The correction switch is tab
   11's (MONO_FDR): flipping it here flips it there.
   ========================================================================== */
'use strict';

window.MONO_FINAL = (function () {
  const M = () => window.MONO;
  const F = () => window.MONO_FDR;
  const P = { data: null, err: null, loading: false, seq: 0, making: false, makeNote: '', makeErr: null, band: 'theta' };
  const $ = (id) => document.getElementById(id);
  const el = (...a) => M().el(...a);
  const FILE = (name, save) => '/api/arc/monolith/final/file/' + encodeURIComponent(name) + (save ? '?download=1' : '');
  const EXPORT = (name) => '/api/arc/monolith/final/export/' + encodeURIComponent(name);
  const BAND_KEY = 'barry.final.band';
  try { const b = localStorage.getItem(BAND_KEY); if (b === 'theta' || b === 'gamma') P.band = b; } catch (e) { /* none */ }
  const PAIRS = ['RSC–dHC', 'RSC–ACC', 'RSC–OFC', 'RSC–PER', 'dHC–ACC', 'dHC–OFC', 'dHC–PER', 'ACC–OFC', 'ACC–PER', 'OFC–PER'];
  const CONTRASTS = [['cue1-base10', 'Cue 1 vs baseline'], ['cue2-base10', 'Cue 2 vs baseline'], ['cue2-cue1', 'Cue 2 vs cue 1']];

  const pSay = (p) => (p == null ? 'p n/a' : p < 0.001 ? 'p < 0.001' : 'p = ' + p.toFixed(3));
  const n3 = (x) => (x == null || !isFinite(x) ? 'n/a' : x.toFixed(3));
  const n2 = (x) => (x == null || !isFinite(x) ? 'n/a' : x.toFixed(2));
  const db = (x) => (x == null || !isFinite(x) ? 'n/a' : (x >= 0 ? '+' : '−') + Math.abs(x).toFixed(2) + ' dB');
  const star = (x) => (F().passes(x) ? ' *' : '');
  const when = (s) => { try { return new Date(s).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' }); } catch (e) { return s; } };
  const regionSay = (D, id) => (D.regions.find((r) => r.id === id) || {}).say || id;

  function card(id, title, help, kids, cls) {
    return el('div', { class: 'card' + (cls ? ' ' + cls : ''), id }, [el('div', { class: 'hrow' }, [el('h2', { text: title }), help ? M().qh(help) : null])].concat(kids));
  }

  async function load() {
    const seq = ++P.seq;
    P.loading = true;
    render();
    try {
      const got = await M().getJSON('/data/final');
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
      await M().runHere('/final', { confirm: true }, (note) => {
        P.makeNote = note;
        const b = $('finalmake');
        if (b) b.textContent = 'Working: ' + note;
      });
    } catch (e) {
      P.makeErr = /404|not found/i.test(e.message) ? 'Jarvis is running older code without this button: restart it, then press it again.'
        : 'It could not be done: ' + e.message;
    }
    P.making = false;
    load();
    if (window.MONO_EVENMORE) window.MONO_EVENMORE.load();          // tab 11 may have been worked out again first
  }

  function setBand(b) {
    P.band = b;
    try { localStorage.setItem(BAND_KEY, b); } catch (e) { /* none */ }
    render();
  }

  /* ---------------- pieces ---------------- */
  const filesOf = (f) => (F().get() === 'raw' && f.files_raw ? Object.assign({}, f.files, f.files_raw) : f.files) || {};
  const passOf = (f) => !!(f.passes && f.passes[F().get()]);

  function figCard(f, name) {
    const files = filesOf(f);
    const link = (k, say) => (files[k] ? el('a', { class: 'more-btn small', href: FILE(files[k], true), download: files[k], text: say }) : null);
    return el('div', { class: 'morefig' + (f.kind === 'all' ? ' pooled' : ''), id: 'finalfig_' + f.id }, [
      el('h3', {}, [el('span', {}, [el('span', { class: 'morefno', text: 'Figure ' + f.id.replace(/_/g, '.') }), ' · ' + name]),
        passOf(f) ? el('span', { class: 'chip sig', text: F().get() === 'fdr' ? 'passes after FDR' : 'passes, uncorrected' }) : null]),
      el('a', { class: 'morefimg', href: FILE(files.svg), target: '_blank', rel: 'noopener', title: 'Open the figure on its own' },
        el('img', { src: FILE(files.svg), alt: name + ', ' + ((f.legend || {}).title || ''), loading: 'lazy' })),
      el('details', { class: 'morelegend' }, [el('summary', { text: (f.legend || {}).title || 'Legend' }), el('p', { text: (f.legend || {}).body || '' })]),
      el('div', { class: 'row gap morefiles' }, [link('pdf', 'PDF'), link('svg', 'SVG'), link('png', 'PNG'), link('xlsx', 'Prism .xlsx'), link('pzfx', 'Prism .pzfx')])]);
  }

  function table(id, head, rows) {
    return el('div', { class: 'tablewrap' }, el('table', { class: 'moretable', id }, [
      el('thead', {}, el('tr', {}, head.map((t) => el('th', { text: t })))), el('tbody', {}, rows)]));
  }

  /* ---------------- the top ---------------- */
  function intro(D) {
    return card('finalhead', '12 · The final stage', 'final', [
      el('p', { text: 'Within-region power in each region on its own, the oscillation against its background, which region leads and theta–gamma coupling on tab 11’s results, '
        + 'whether each result holds without any one rat, and the methods written from this run.' }),
      el('details', { class: 'moremore' }, [
        el('summary', { text: 'More' }),
        el('ul', { class: 'moresteps' }, [
          el('li', { text: 'Power: Welch power with Dickson’s settings, pooled over each session’s trials (for power, pooling is just the mean), in dB re 1 µV²/Hz; a region is the mean of its two sides. Each region is tested on its own: 2 sessions × 3 periods (baseline, cue 1, cue 2), full 10 s windows, the cue-onset response included.' }),
          el('li', { text: 'No per-rat normalisation: the rat is the GEE’s cluster, and Session × Period (the key test) cancels slow drift between the days. The GEE for dB is normal with the identity link.' }),
          el('li', { text: 'FOOOF splits each spectrum into a 1/f background (its exponent and offset) and peaks; the theta peak’s frequency and height are tested the same way.' }),
          el('li', { text: 'Granger and theta–gamma coupling run only on the pairs (and their regions) that pass in tab 11, so the switch changes which ones are shown.' }),
          el('li', { text: 'The side question asks whether gamma changes when every trial is its own row, nothing pooled; it is not for Joe.' }),
        ])]),
      el('p', { class: 'warn', id: 'finaltwenty', text: (D && D.twenty) || '“20 × 16 × 8 × 2”, in the meeting notes, is waiting for confirmation from Joe.' }),
      el('div', { class: 'row gap moretools' }, [
        el('button', { type: 'button', class: 'more-btn', id: 'finalmake', disabled: P.making ? 'disabled' : null, onclick: make,
                       text: P.making ? 'Working: ' + (P.makeNote || 'starting') : D ? 'Work it out again' : 'Work it out' }),
        D ? el('span', { class: 'small muted', text: 'Made ' + when(D.at) + ' from tab 11 of ' + when(D.from) + '.' }) : null]),
      P.makeErr ? el('p', { class: 'warn', id: 'finalerr', text: P.makeErr }) : null]);
  }

  /* ---------------- power ---------------- */
  function power(D) {
    const per = (D.power || {})[P.band] || [];
    const rows = per.filter(Boolean).map((x) => {
      const sp = x.sp || {};
      const any = F().passes(sp) || CONTRASTS.some((c) => F().passes((x.contrasts || {})[c[0]]));
      return el('tr', { class: any ? 'sig' : '' }, [
        el('th', {}, [el('span', { class: 'moresw', style: '--c:' + (D.regions.find((r) => r.id === x.region) || {}).color }), regionSay(D, x.region)]),
        el('td', { text: String(x.rats.length) }),
        el('td', { text: sp.p == null ? (x.e1_error || 'n/a') : n2(sp.chi2) + ', ' + pSay(sp.p) + ', q ' + n3(sp.q) + star(sp) })]
        .concat(CONTRASTS.map((c) => { const r = (x.contrasts || {})[c[0]] || {}; return el('td', { text: r.diff == null ? 'n/a' : db(r.diff) + ', ' + pSay(r.p) + ', q ' + n3(r.q) + star(r) }); }))
        .concat([el('td', { class: 'weakcell', text: x.spf ? pSay(x.spf.p) : 'n/a' })]));
    });
    const figs = ((D.figures || {}).power || []).filter((f) => f.band === P.band);
    return card('finalpower', 'Within-region power · ' + (P.band === 'theta' ? 'Theta 5–12 Hz' : 'Gamma 30–90 Hz'), 'final.power', [
      el('p', { text: 'Did the cues change power inside each region differently on Precon4 than on Precon1? Session × Period on 2 df (robust), then the three planned contrasts, each a change in dB; corrected across the five regions.' }),
      table('finalpowertable', ['Region', 'Rats', 'Session × Period, χ²(2)'].concat(CONTRASTS.map((c) => 'Session × (' + c[1].toLowerCase() + ')')).concat(['× Frequency (model-based)']), rows),
      el('h3', { class: 'moresub', text: 'Each region alone' }),
      el('div', { class: 'morefigs' }, figs.filter((f) => f.kind === 'region').map((f) => figCard(f, regionSay(D, f.region)))),
      el('h3', { class: 'moresub', text: 'Every region, the plan’s layout' }),
      el('div', {}, figs.filter((f) => f.kind === 'all').map((f) => figCard(f, 'Every region')))]);
  }

  /* ---------------- FOOOF ---------------- */
  function fooof(D) {
    const params = D.fooof_params || [];
    const rows = params.map(([key, say]) => el('tr', {}, [el('th', { text: say })].concat(D.regions.map((r) => {
      const x = (D.fooof[key] || []).find((z) => z.region === r.id) || {};
      const sp = x.sp || {};
      return el('td', { class: F().passes(sp) ? 'sigcell' : '', text: x.error ? 'too few fits' : sp.p == null ? 'n/a' : pSay(sp.p) + ', q ' + n3(sp.q) + star(sp) });
    }))));
    return card('finalfooof', 'Oscillation against background (FOOOF)', 'final.fooof', [
      el('p', { text: 'A spectrum is a sloping background (1/f) plus peaks. A change in power can be either; FOOOF separates them. Session × Period for each part, in each region.' }),
      table('finalfoooftable', ['Session × Period'].concat(D.regions.map((r) => r.say)), rows),
      el('div', {}, ((D.figures || {}).fooof || []).map((f) => figCard(f, 'Every region')))]);
  }

  /* ---------------- Granger and PAC on the hits ---------------- */
  function follow(D) {
    const m = F().get();
    const hits = (D.hits || {})[m] || [];
    const G = (D.granger || []).filter((x) => x.in && x.in[m] && !x.error);
    const Pm = (D.pac || []).filter((x) => x.in && x.in[m] && !x.error);
    const gRows = G.map((x) => {
      const cell = (r) => (r && r.p != null ? '×' + n2(r.ratio) + ', ' + pSay(r.p) + ', q ' + n3(r.q) + star(r) : 'n/a');
      return el('tr', { class: F().passes(x.ab) || F().passes(x.ba) ? 'sig' : '' }, [
        el('th', { text: PAIRS[x.pair] + ', ' + x.band }), el('td', { text: String(x.rats.length) }),
        el('td', { text: x.a + ' → ' + x.b + ': ' + cell(x.ab) }), el('td', { text: x.b + ' → ' + x.a + ': ' + cell(x.ba) }), el('td', { text: cell(x.sd) })]);
    });
    const pRows = Pm.map((x) => el('tr', { class: F().passes(x.le) ? 'sig' : '' }, [
      el('th', { text: regionSay(D, x.region) }), el('td', { text: String(x.rats.length) }),
      el('td', { text: x.le && x.le.p != null ? '×' + n2(x.le.ratio) + ', ' + pSay(x.le.p) + ', q ' + n3(x.le.q) + star(x.le) : 'n/a' })]));
    const gF = ((D.figures || {}).granger || []).filter((f) => f.in && f.in[m]);
    const pF = ((D.figures || {}).pac || []).filter((f) => f.in && f.in[m]);
    return card('finalfollow', 'On tab 11’s results: which leads, and theta–gamma coupling', 'final.follow', [
      el('p', { id: 'finalhits', text: hits.length ? 'Tab 11’s results on this side of the switch: ' + hits.map((h) => PAIRS[h.pair] + ' (' + h.band + ')').join(', ') + '.'
        : 'Nothing in tab 11 passes on this side of the switch, so there is nothing to follow up.' }),
      gRows.length ? el('h3', { class: 'moresub', text: 'Which region leads (Granger), Late ÷ Early' }) : null,
      gRows.length ? table('finalgrangertable', ['Pair', 'Rats', 'One way', 'The other', 'Session × Direction'], gRows) : null,
      gF.length ? el('div', { class: 'morefigs' }, gF.map((f) => figCard(f, PAIRS[f.pair] + ', ' + f.band))) : null,
      pRows.length ? el('h3', { class: 'moresub', text: 'Theta–gamma coupling within each region, Late ÷ Early' }) : null,
      pRows.length ? table('finalpactable', ['Region', 'Rats', 'Modulation index'], pRows) : null,
      pF.length ? el('div', { class: 'morefigs' }, pF.map((f) => figCard(f, regionSay(D, f.region)))) : null]);
  }

  /* ---------------- robustness ---------------- */
  function robust(D, EM) {
    const nameOf = (r) => r.name || (PAIRS[r.pair] + ', ' + r.band + ': ' + r.label);
    const all = (EM && EM.robust ? EM.robust.map((r) => Object.assign({}, r, { name: 'Coherence, ' + PAIRS[r.pair] + ', ' + r.band + ': ' + r.label })) : []).concat(D.robust || []);
    const rows = all.filter((r) => (r.passes || {})[F().get()]);
    const body = rows.map((r) => {
      const t = r.test || {};
      const eff = t.ratio != null ? '×' + t.ratio.toFixed(2) : t.diff != null ? db(t.diff) : '';
      const lm = r.lmm || {};
      const lmOk = lm.p != null && lm.p < 0.05;
      const ok = r.survives && lmOk;
      return el('tr', { class: ok ? 'sig' : '' }, [el('th', { text: nameOf(r) }),
        el('td', { text: [eff, pSay(t.p), t.q != null ? 'q ' + n3(t.q) : ''].filter(Boolean).join(', ') }),
        el('td', { text: r.survives ? 'holds without any one rat' : 'fails without J' + (r.worst || {}).rat + ' (' + pSay((r.worst || {}).p) + ')' }),
        el('td', { text: lm.p == null ? (lm.error || 'not fitted') : 'F(' + lm.df1 + ', ' + lm.df2 + ') = ' + n2(lm.F) + ', ' + pSay(lm.p) }),
        el('td', { text: ok ? 'solid' : r.survives || lmOk ? 'shaky' : 'fragile' })]);
    });
    return card('finalrobust', 'Does it hold? Every result, tabs 11 and 12', 'more.robust', [
      el('p', { text: 'Each result that passes on this side of the switch, fitted again without each rat in turn, and in a linear mixed model. Solid: it holds both ways. Shaky: one of the two. Fragile: neither; read it as a lead.' }),
      body.length ? table('finalrobusttable', ['Result', 'GEE', 'Leave one rat out', 'Linear mixed model', 'Verdict'], body)
        : el('p', { class: 'muted', text: 'Nothing passes on this side of the switch.' })]);
  }

  /* ---------------- the side question ---------------- */
  function side(D) {
    const rows = (D.side || []).map((x) => {
      const le = x.le || {};
      return el('tr', { class: F().passes(le) ? 'sig' : '' }, [el('th', { text: PAIRS[x.pair] }), el('td', { text: String(x.n_rows || 0) }),
        el('td', { text: le.ratio == null ? (x.error || le.error || 'n/a') : '×' + n2(le.ratio) + ' (' + n2(le.lo) + ' to ' + n2(le.hi) + '), ' + pSay(le.p) + ', q ' + n3(le.q) + star(le) })]);
    });
    return card('finalside', 'Side question (not for Joe): gamma with every trial its own row', 'final.side', [
      el('p', { text: 'Is there a gamma effect if every trial is coded on its own, rather than pooled into one value a session? Each trial’s own coherence is a row; the rat is still the cluster.' }),
      table('finalsidetable', ['Pair', 'Trials', 'Late ÷ Early (95% interval)'], rows),
      el('div', {}, ((D.figures || {}).side || []).map((f) => figCard(f, 'Every pair')))], 'finalnotjoe');
  }

  /* ---------------- the methods ---------------- */
  function methods(D) {
    return card('finalmethods', 'Methods, written from this run', 'final.methods', [
      el('p', { text: 'Generated from the numbers above, every time the tab is worked out: what went in, how it was measured, the model, and every result that passes on each side of the switch.' }),
      el('div', { class: 'row gap' }, [el('a', { class: 'more-btn small', href: EXPORT('final_methods.docx'), download: 'final_methods.docx', text: 'Word (.docx)' }),
        el('a', { class: 'more-btn small', href: EXPORT('final_methods.txt'), download: 'final_methods.txt', text: 'Text (.txt)' })]),
      el('div', { class: 'finalmethods' }, (D.methods || []).map((s) => el('details', { class: 'finalmsec', open: /Waiting/.test(s.title) ? 'open' : null }, [
        el('summary', { text: s.title }), ...s.paras.map((t) => el('p', { text: t }))])))]);
  }

  /* ---------------- everything ---------------- */
  function render() {
    const pane = $('finalpane');
    if (!pane) return;
    if (window.MONO_STATIC) {
      pane.replaceChildren(card('finalstatic', '12 · The final stage', null, [el('p', { text: 'Not in this copy: it opens in Jarvis, and its figures go to Joe through tab 10.' })]));
      return;
    }
    if (P.loading && !P.data) {
      pane.replaceChildren(el('div', { class: 'card' }, el('p', { class: 'muted', text: 'Reading tab 12.' })));
      return;
    }
    const D = P.data;
    if (!D) {
      pane.replaceChildren(intro(null), card('finalmissing', 'Nothing yet', null, [
        el('p', { text: (P.err && !/404|not been/i.test(P.err) ? P.err + ' ' : '') + 'Press Work it out. It is made from tab 11’s rat-days (worked out again first if they predate this tab).' })]));
      return;
    }
    const EM = window.MONO_EVENMORE ? window.MONO_EVENMORE.state.data : null;
    const tiles = el('div', { class: 'moretiles', role: 'group', 'aria-label': 'Band' }, [['theta', 'Theta 5–12 Hz'], ['gamma', 'Gamma 30–90 Hz']].map(([b, say]) =>
      el('button', { type: 'button', class: 'moretile' + (b === P.band ? ' on' : ''), 'aria-pressed': b === P.band ? 'true' : 'false', id: 'finalband_' + b, text: say, onclick: () => setBand(b) })));
    const ex = card('finalexport', 'Files', null, [
      el('p', { text: 'Every row each model saw, every test, SPSS’s coefficients (the last level of each factor the reference, as SPSS prints them), scripts for R and SPSS, and the methods.' }),
      el('div', { class: 'row gap' }, (D.exports || []).map((n) => el('a', { class: 'more-btn small', href: EXPORT(n), download: n, text: n })))]);
    pane.replaceChildren(intro(D), el('div', { class: 'morebar' }, [tiles, F().node(el, 'finalfdr')]), power(D), fooof(D), follow(D), robust(D, EM), side(D), methods(D), ex);
    // the robustness card shows tab 11's checks too: read tab 11 once if it has not been
    if (!EM && !P.emAsked && window.MONO_EVENMORE) {
      P.emAsked = true;
      window.MONO_EVENMORE.load().then(() => { if ($('finalpane') && !$('finalpane').hidden) render(); });
    }
  }

  document.addEventListener('mono:fdr', () => { if ($('finalpane') && !$('finalpane').hidden) render(); });

  function show() {
    if (!P.data && !P.loading) load(); else render();
  }
  return { show, render, load, make, setBand, get state() { return { data: P.data, err: P.err, band: P.band, making: P.making }; } };
})();
