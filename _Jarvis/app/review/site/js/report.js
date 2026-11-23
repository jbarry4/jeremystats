/* ==========================================================================
   report.js -- the review's write-up: what the Monolith asked, how, what
   was kept, what came out, and the open questions.

   Every number comes from data/review.json, which tools/export_review.py
   writes from the built Monolith the site was made from; the questions
   from /api/questions (the lab's Supabase).
   ========================================================================== */
'use strict';

(function () {
  const host = document.getElementById('report');
  const WHO_KEY = 'dm.review.who';
  // The windows in the lab's words (as the Monolith page says them).
  const WTITLE = {
    pre: 'The ten seconds before cue 1 starts.',
    cue1: 'Cue 1 sounding: A or C, 10 s.',
    cue2: 'Cue 2 sounding: B or D, 10 s.',
    post: 'The ten seconds after cue 2 ends.',
    pair: 'The whole pair as heard, cue 1 onset to cue 2 offset (20 s). A wire counts only if it is clean in both cues.',
    onset: 'Around cue 1 starting: −3/+3 s for bands up to 12 Hz, −1/+2 s above.',
    switch: 'Around cue 1 giving way to cue 2, with the same lengths.',
    offset: 'Around cue 2 ending, with the same lengths.',
    c21: 'Within each trial, Cue 2 minus Cue 1 (B − A, D − C), then Precon4 against Precon1. Raw only: the FP that Minus FP takes away is the same for both cues, so it cancels exactly.',
  };
  const GROUP_SAY = { pooled: 'AB and CD pooled', ab: 'AB only', cd: 'CD only' };
  const LAYER_SAY = { raw: 'Raw', minus_fp: 'Minus FP' };

  function el(tag, attrs, kids) {
    const n = document.createElement(tag);
    for (const k in (attrs || {})) {
      const v = attrs[k];
      if (v == null || v === false) continue;
      if (k === 'text') n.textContent = v;
      else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const c of [].concat(kids || [])) if (c != null && c !== false) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    return n;
  }
  const fmt = (n) => (n == null ? '—' : Number(n).toLocaleString('en-US'));
  function sig(v) {
    if (v == null || !isFinite(v)) return '—';
    const a = Math.abs(v);
    return a >= 100 ? v.toFixed(0) : a >= 1 ? v.toFixed(2) : a >= 0.01 ? v.toFixed(3) : a >= 0.001 ? v.toFixed(4) : a === 0 ? '0' : v.toExponential(1);
  }
  const signed = (v) => (v == null || !isFinite(v) ? '—' : (v >= 0 ? '+' : '−') + sig(Math.abs(v)));
  const pSay = (p) => (p == null || !isFinite(p) ? '—' : p < 0.001 ? p.toExponential(1) : p.toFixed(3).replace(/^0/, ''));
  const short = (r) => String(r).replace(/^Left /, 'L ').replace(/^Right /, 'R ');
  const date = (s) => { try { return new Date(s).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }); } catch (e) { return s; } };

  async function signOut() {
    try { await fetch('/api/logout', { method: 'POST' }); } catch (e) { /* signing out anyway */ }
    location.href = '/login.html';
  }

  function section(id, title, kids) {
    return el('section', { class: 'card', id }, [el('h2', { text: title })].concat(kids));
  }
  function table(head, rows, cls) {
    return el('div', { class: 'twrap' }, [el('table', { class: cls || null }, [
      el('thead', {}, [el('tr', {}, head.map((h) => el('th', { class: h.num ? 'num' : null, text: h.text || h })))]),
      el('tbody', {}, rows),
    ])]);
  }

  /* ---------------- the sections ---------------- */
  function head(R) {
    return [
      el('h1', { text: 'The DEWEY Monolith: Precon1 → Precon4, every coupling measure, 1–55 Hz' }),
      el('p', { class: 'lede', text: 'For review. Built ' + date(R.built_at) + ' under histology v' + ((R.histology || {}).version || '?')
        + ', from run ' + (R.rid || '—') + '. This page says what was asked and how; the Monolith itself is the explorer, '
        + 'down to any rat, trial and trace.' }),
      el('div', { class: 'uncorrected' }, [el('strong', { text: 'Every p on this site is uncorrected. ' }),
        'No correction for multiple comparisons was applied, on purpose: the Monolith is for finding things to follow up, not for proving them. '
        + 'Each count of p < .05 below is shown beside how many would pass by chance alone.']),
      el('nav', { class: 'nav' }, [
        el('a', { class: 'btn primary', href: 'monolith.html', text: 'Open the Monolith' }),
        el('a', { class: 'btn', href: 'monolith-guide.html', text: 'The Guide: every measure and test, with examples' }),
        el('a', { class: 'btn', href: '#questions', text: 'Open questions' }),
        el('button', { type: 'button', text: 'Sign out', onclick: signOut }),
      ]),
      el('p', { class: 'toc' }, ['On this page: ',
        ...[['scope', 'What was asked'], ['abcd', 'A, B, C and D'], ['windows', 'The windows'], ['minusfp', 'Minus FP'],
            ['histology', 'Histology v2'], ['kept', 'What was kept'], ['results', 'What came out'], ['questions', 'Open questions'],
            ['site', 'About this site']]
          .map(([id, t], i) => el('span', {}, [i ? '· ' : '', el('a', { href: '#' + id, text: t })]))]),
    ];
  }

  function scope(R) {
    const c = ((R.counts || {}).pooled || {}).raw || {};
    return section('scope', 'What was asked', [
      el('p', { text: 'Did the coupling between brain regions change from the first pre-conditioning session (Precon1) to the last (Precon4)? '
        + 'Each rat is compared with itself, Precon4 minus Precon1, and the changes are pooled over rats (DerSimonian–Laird random effects, '
        + 'Hartung–Knapp t on k − 1 degrees of freedom). A stat test is tested only where at least ' + R.min_rats + ' rats have it on both days.' }),
      el('div', { class: 'facts' }, [
        [R.rats.length, 'rats (' + R.rats.map((r) => 'J' + r).join(', ') + ')'],
        [R.regions.length, 'regions; ' + R.n_pairs + ' region pairs'],
        [R.methods.length, 'coupling measures'],
        [R.bands.n_hz + ' + ' + R.bands.named.length, '1 Hz bands from ' + R.bands.lo + ' to ' + R.bands.hi + ' Hz, and ' + R.bands.named.join(', ')],
        [R.windows.length, 'windows around each trial, and the Cue 2 − Cue 1 contrast'],
        [fmt(c.tested), 'stat tests tested (raw, AB and CD pooled), of ' + fmt(c.entries)],
      ].map(([b, s]) => el('div', { class: 'fact' }, [el('b', { text: String(b) }), el('span', { text: s })]))),
      el('p', { class: 'small muted', text: 'Raw, the cue windows as measured, and Minus FP, each session less its FP1/FP2. '
        + 'Three ways of taking the pairs: AB and CD pooled, AB only, CD only. The measures: ' + R.methods.map((m) => m.label).join(', ') + '. '
        + 'Precon2 and Precon3 are measured the same way for the trajectory and Monolith Progress, and never enter the test.' }),
    ]);
  }

  function abcd(R) {
    const I = R.identity || { seats: {}, sound_say: {} };
    const say = (s) => (I.sound_say || {})[s] || s;
    const rows = R.rats.map((r) => {
      const s = (I.seats || {})[r] || {};
      return el('tr', {}, [el('th', { text: 'J' + r })].concat(['A', 'B', 'C', 'D'].map((x) => el('td', { text: s[x] ? say(s[x]) : '—' }))));
    });
    return section('abcd', 'Which cue is which: A, B, C and D', [
      el('p', { text: 'Each rat heard two cue pairs, counterbalanced across rats, so a physical sound is never a role. The roles come from the lab’s '
        + 'identity sheet (' + (I.sheet || 'the identity sheet') + '): AB is the pair heard as A then B, CD as C then D. Cue 1 is always A or C '
        + '(the opener), Cue 2 always B or D. Nothing is read from the conditioning sessions.' }),
      table(['Rat', 'A', 'B', 'C', 'D'], rows),
      el('p', { class: 'small muted', text: 'In the Monolith, opening a line and then a rat shows a physical-cue check: each rat’s value by A/B/C/D and '
        + 'by sound, and whether a change follows A/B/C/D (the role) or the sound.' }),
    ]);
  }

  function windows(R) {
    return section('windows', 'The windows', [
      el('p', { text: 'Every trial is measured in these windows. The states and the whole pair are cut the same length in every band; '
        + 'the transitions are cut longer for slow bands so that a few cycles fit.' }),
      el('dl', { class: 'windows' }, [].concat(...R.windows.concat(R.contrast_window ? [R.contrast_window] : [])
        .map((w) => [el('dt', { text: w.label }), el('dd', { text: WTITLE[w.id] || '' })]))),
    ]);
  }

  function minusfp() {
    return section('minusfp', 'How Minus FP works', [
      el('p', { text: 'Every session has two FP recordings, one before the cue session (FP1) and one after (FP2): the same rat, the same '
        + 'wires, no cues. They are cut into FP epochs as long as the window they stand against (10 s for every window, 20 s for the whole pair) '
        + 'and measured exactly as the cue windows are.' }),
      el('p', { text: 'A session’s Minus FP value is the mean over its trials less the mean over its own FP epochs. The change is then '
        + 'taken as for Raw: Precon4 minus Precon1, rat by rat, and pooled. What is shared by the trials and FP of that day — the wires, the '
        + 'reference, the day’s state — is taken away; what is left is what the cues add.' }),
      el('p', { class: 'small muted', text: 'The Cue 2 − Cue 1 contrast is Raw only: the FP taken away from each cue window is the same number, '
        + 'so it cancels exactly, and Minus FP would show the same values. The Monolith’s first tab draws each step.' }),
    ]);
  }

  function histology(R) {
    const H = R.histology || {};
    const ch = R.histology_changes || {};
    const rows = [];
    for (const rat of Object.keys(ch).sort((a, b) => a - b)) {
      for (const c of ch[rat]) {
        rows.push(el('tr', {}, [el('th', { text: 'J' + rat }), el('td', { text: c.region }),
          el('td', { text: (c.v1 || '—') + ' → ' + (c.v2 || '—') }), el('td', { text: c.monolith ? 'used' : 'left out' })]));
      }
    }
    return section('histology', 'Histology v2', [
      el('p', { text: (H.say || '') + ' ' + (H.rule ? 'The rule: ' + H.rule + '.' : '') }),
      el('p', { text: 'Left POR-SUB uses the POR channel mapping. A region needs at least ' + R.min_rats
        + ' rats with it on both days before any pair with it is tested.' }),
      rows.length ? el('h3', { text: 'What v2 changed from v1' }) : null,
      rows.length ? table(['Rat', 'Region', 'v1 → v2', 'In the Monolith now'], rows) : el('p', { class: 'muted', text: 'v2 scored every probe as v1 did.' }),
    ]);
  }

  function kept(R) {
    const K = R.damage || {};
    const c = K.cue || {}, r = K.rest || {};
    const causes = Object.entries(K.causes || {}).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]);
    return section('kept', 'What was kept', [
      el('p', { text: 'A trial is one cue pair heard, cue 1 then cue 2. Of ' + fmt(c.total) + ' trials over ' + R.rats.length + ' rats and the sessions built, '
        + fmt(c.kept) + ' kept every region histology allows in every window, ' + fmt(c.partial) + ' lost a region somewhere, and '
        + fmt(c.lost) + ' were lost entirely. FP epochs (flower-pot): ' + fmt(r.kept) + ' of ' + fmt(r.total) + ' usable.' }),
      causes.length ? el('p', { class: 'small', text: 'Region-windows lost, by cause: ' + causes.map(([k, n]) => k + ' ' + fmt(n)).join(' · ') + '.' }) : null,
      el('p', { class: 'small muted' }, ['Rat by rat, region by region, with each loss’s reason: ', el('a', { href: 'monolith.html', text: 'the Monolith' }),
        ', tab 1 · What was kept.']),
    ]);
  }

  function results(R) {
    const box = el('div');
    const countRows = [];
    for (const g of ['pooled', 'ab', 'cd']) {
      for (const layer of ['raw', 'minus_fp']) {
        const c = ((R.counts || {})[g] || {})[layer];
        if (!c) continue;
        countRows.push(el('tr', {}, [el('th', { text: GROUP_SAY[g] + ' · ' + LAYER_SAY[layer] }), el('td', { class: 'num', text: fmt(c.tested) }),
          el('td', { class: 'num', text: fmt(c.p05) }), el('td', { class: 'num', text: fmt(c.chance_p05) }), el('td', { class: 'num', text: fmt(c.p01) }),
          el('td', { class: 'num', text: fmt(c.p001) })]));
      }
      const cc = (R.contrast || {})[g];
      if (cc) {
        countRows.push(el('tr', {}, [el('th', { text: GROUP_SAY[g] + ' · Cue 2 − Cue 1' }), el('td', { class: 'num', text: fmt(cc.tested) }),
          el('td', { class: 'num', text: fmt(cc.p05) }), el('td', { class: 'num', text: fmt(cc.chance_p05) }), el('td', { class: 'num', text: fmt(cc.p01) }),
          el('td', { class: 'num', text: fmt(cc.p001) })]));
      }
    }
    const st = { g: 'pooled', layer: 'raw' };
    const leadHost = el('div');
    const kinds = [['pooled', 'AB and CD pooled'], ['ab', 'AB only'], ['cd', 'CD only']];
    const layers = [['raw', 'Raw'], ['minus_fp', 'Minus FP'], ['contrast', 'Cue 2 − Cue 1']];
    const segOf = (list, key) => el('div', { class: 'seg', role: 'group' }, list.map(([id, label]) => el('button', { type: 'button', 'data-id': id,
      'aria-pressed': String(st[key] === id), text: label, onclick: () => { st[key] = id; draw(); } })));
    function draw() {
      leadHost.innerHTML = '';
      leadHost.appendChild(segOf(kinds, 'g'));
      leadHost.appendChild(segOf(layers, 'layer'));
      const list = st.layer === 'contrast' ? ((R.contrast_leads || {})[st.g] || []) : (((R.leads || {})[st.g] || {})[st.layer] || []);
      if (!list.length) { leadHost.appendChild(el('p', { class: 'muted', text: 'Nothing passed p < .05 here.' })); return; }
      const layer = st.layer === 'contrast' ? 'raw' : st.layer;
      leadHost.appendChild(table(['#', 'Region pair', 'Measure', 'Frequency', 'Window', { text: 'Change', num: true }, { text: 'p (uncorrected)', num: true },
        { text: 'Rats the same way', num: true }, ''], list.map((t, i) => {
        const link = 'monolith.html#go=' + [layer, t.w, t.band, t.m, t.pair, st.g === 'pooled' ? 'all' : st.g].join(',');
        return el('tr', { class: 'lead' }, [el('td', { class: 'num', text: String(i + 1) }), el('td', { text: short(t.a) + ' – ' + short(t.b) }),
          el('td', { text: R.method_say[t.m] || t.m }), el('td', { text: t.hz ? t.hz + ' Hz' : (R.band_say[t.band] || t.band) }),
          el('td', { text: R.window_say[t.w] || t.w }), el('td', { class: 'num ' + (t.est >= 0 ? 'up' : 'down'), text: signed(t.est) }),
          el('td', { class: 'num', text: pSay(t.p) }), el('td', { class: 'num', text: t.same + ' of ' + t.k }),
          el('td', {}, [el('a', { href: link, text: 'Open' })])]);
      })));
      leadHost.appendChild(el('p', { class: 'small muted', text: 'The first ten top results: p < .05 (uncorrected), most rats the same way first, '
        + 'then p, at most three per region pair. Open takes you to that line in the Monolith, where it opens into its rats, trials and traces.' }));
    }
    draw();
    box.appendChild(el('p', { text: 'How many stat tests passed, against how many would by chance. A top result is something to look at, not a finding.' }));
    box.appendChild(table(['Comparison', { text: 'Tested', num: true }, { text: 'p < .05', num: true }, { text: 'By chance', num: true },
      { text: 'p < .01', num: true }, { text: 'p < .001', num: true }], countRows));
    box.appendChild(el('h3', { text: 'The top results' }));
    box.appendChild(leadHost);
    return section('results', 'What came out', [box]);
  }

  /* ---------------- open questions ---------------- */
  const QS = { list: null, err: null, show: 'open' };
  async function qapi(method, body) {
    const r = await fetch('/api/questions', { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
    if (r.status === 401) { location.href = '/login.html?next=/'; throw new Error('Sign in first.'); }
    const b = await r.json().catch(() => ({}));
    if (!r.ok || !b.ok) throw new Error(b.error || ('HTTP ' + r.status));
    return b.questions || [];
  }
  function who() { try { return localStorage.getItem(WHO_KEY) || ''; } catch (e) { return ''; } }
  function rememberWho(v) { try { localStorage.setItem(WHO_KEY, v); } catch (e) { /* this browser only */ } }
  async function loadQuestions() {
    try { QS.list = await qapi('GET'); QS.err = null; } catch (e) { QS.err = e.message; }
    drawQuestions();
  }
  function merge(rows) {
    for (const q of rows) {
      const i = QS.list.findIndex((x) => x.id === q.id);
      if (i >= 0) QS.list[i] = q; else QS.list.push(q);
    }
  }
  function drawQuestions() {
    const host2 = document.getElementById('qlist');
    if (!host2) return;
    host2.innerHTML = '';
    if (QS.err) { host2.appendChild(el('p', { class: 'warn', text: 'The questions could not be read: ' + QS.err })); return; }
    if (!QS.list) { host2.appendChild(el('p', { class: 'loading', text: 'Reading the questions…' })); return; }
    const n = (s) => QS.list.filter((q) => s === 'all' || q.status === s).length;
    host2.appendChild(el('div', { class: 'seg', role: 'group' }, [['open', 'Open'], ['answered', 'Answered'], ['closed', 'Closed'], ['all', 'All']]
      .map(([id, label]) => el('button', { type: 'button', 'aria-pressed': String(QS.show === id), text: label + ' (' + n(id) + ')',
                                           onclick: () => { QS.show = id; drawQuestions(); } }))));
    const shown = QS.list.filter((q) => QS.show === 'all' || q.status === QS.show);
    if (!shown.length) host2.appendChild(el('p', { class: 'muted', text: 'None here.' }));
    for (const q of shown) host2.appendChild(question(q));
  }
  function question(q) {
    const box = el('div', { class: 'q ' + q.status, 'data-id': String(q.id) });
    box.appendChild(el('div', { class: 'meta', text: '#' + q.id + ' · ' + (q.asked_by || '—') + ' · ' + date(q.created_at)
      + (q.about ? ' · about ' + q.about : '') + ' · ' + q.status }));
    box.appendChild(el('div', { class: 'text', text: q.text }));
    if (q.answer) box.appendChild(el('div', { class: 'answer', text: q.answer + (q.answered_by ? '  — ' + q.answered_by : '') }));
    const acts = el('div', { class: 'acts' });
    const set = async (patch) => {
      try { merge(await qapi('PATCH', Object.assign({ id: q.id }, patch))); drawQuestions(); } catch (e) { alert('Not saved: ' + e.message); }
    };
    acts.appendChild(el('button', { type: 'button', text: q.answer ? 'Edit the answer' : 'Answer', onclick: () => {
      const ta = el('textarea', { 'aria-label': 'Answer' });
      ta.value = q.answer || '';
      const by = el('input', { type: 'text', class: 'who', placeholder: 'Your name', 'aria-label': 'Your name' });
      by.value = who();
      const form = el('form', { class: 'add' }, [ta, el('div', { class: 'row' }, [by, el('button', { type: 'submit', text: 'Save the answer' })])]);
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        if (!by.value.trim()) { by.focus(); return; }
        rememberWho(by.value.trim());
        set({ answer: ta.value, answered_by: by.value.trim(), status: ta.value.trim() ? 'answered' : q.status });
      });
      acts.replaceWith(form);
      ta.focus();
    } }));
    if (q.status !== 'closed') acts.appendChild(el('button', { type: 'button', text: 'Close', onclick: () => set({ status: 'closed' }) }));
    else acts.appendChild(el('button', { type: 'button', text: 'Reopen', onclick: () => set({ status: 'open' }) }));
    box.appendChild(acts);
    return box;
  }
  function questions() {
    const text = el('textarea', { id: 'qtext', placeholder: 'A question about the analysis, a result, a choice made', 'aria-label': 'Your question' });
    const about = el('input', { type: 'text', id: 'qabout', placeholder: 'About (optional): a section, a result, a link', 'aria-label': 'What it is about' });
    const by = el('input', { type: 'text', id: 'qwho', class: 'who', placeholder: 'Your name', 'aria-label': 'Your name' });
    by.value = who();
    const say = el('span', { class: 'small', role: 'status' });
    const form = el('form', { class: 'add', id: 'qadd' }, [text, about, el('div', { class: 'row' }, [by, el('button', { type: 'submit', text: 'Add the question' }), say])]);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!text.value.trim()) { text.focus(); return; }
      if (!by.value.trim()) { by.focus(); return; }
      rememberWho(by.value.trim());
      say.textContent = 'Adding…';
      try {
        merge(await qapi('POST', { text: text.value, asked_by: by.value.trim(), about: about.value }));
        text.value = ''; about.value = '';
        say.textContent = 'Added.';
        QS.show = 'open';
        drawQuestions();
      } catch (err) { say.textContent = 'Not added: ' + err.message; }
    });
    return section('questions', 'Open questions', [
      el('p', { text: 'Anything to settle before the next round: add it here, answer it, close it. Everyone with the password sees the same list.' }),
      el('div', { id: 'qlist' }), el('h3', { text: 'Ask one' }), form,
    ]);
  }

  function about(R) {
    const C = R.copy || {};
    const A = C.ahead || {};
    return section('site', 'About this site', [
      el('p', { text: 'The Monolith here is the one in Jarvis, read only, on the numbers it was built with. Every line opens to its '
        + 'pooled numbers; the review’s top results open further, down to each rat and trial (' + fmt(A.entry) + ' stat tests), and '
        + fmt(A.leaf) + ' trials open down to their traces, all copied when the site was made. Anything else opens that far '
        + 'in Jarvis, which reads the recordings on the university’s cluster.' }),
      C.omitted && C.omitted.length ? el('p', { class: 'small muted', text: C.omitted.length + ' of Progress’s files did not fit in the '
        + 'upload: those views say so, and open in Jarvis.' }) : null,
      el('p', { class: 'small muted', text: 'Made ' + date(R.made_at) + ' by tools/export_review.py. Barry lab, University of Vermont.' }),
    ]);
  }

  async function main() {
    let R;
    try {
      const r = await fetch('data/review.json', { cache: 'no-cache' });
      if (r.status === 401) { location.href = '/login.html?next=/'; return; }
      R = await r.json();
    } catch (e) {
      host.innerHTML = '';
      host.appendChild(el('p', { class: 'warn', text: 'The review could not be read: ' + e.message }));
      return;
    }
    host.innerHTML = '';
    for (const n of head(R)) host.appendChild(n);
    for (const n of [scope(R), abcd(R), windows(R), minusfp(), histology(R), kept(R), results(R), questions(), about(R)]) host.appendChild(n);
    if (location.hash) { const t = document.getElementById(location.hash.slice(1)); if (t) t.scrollIntoView(); }
    loadQuestions();
  }
  main();
})();
