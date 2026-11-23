/* ==========================================================================
   monolith_sanity.js -- the Monolith page's thirteenth tab: the sanity
   check report (2026-11-04).

   The last word before Joe's results leave the lab: the right
   data went in, the right logic was applied, the words match the numbers,
   it can be made again from the raw recordings, and what a careful reader
   should know. The checks are run by Jarvis and written to one report
   (monolith/sanity/sanity.json); this tab only reads it and says it
   plainly. A status is always a word and a shape of its own, never a
   colour alone: the report is read by people deciding whether to trust
   it, some of whom do not tell red from green.
   ========================================================================== */
'use strict';

window.MONO_SANITY = (function () {
  const M = () => window.MONO;
  const P = { data: null, err: null, loading: false, seq: 0, making: false, makeNote: '', makeErr: null, drawn: null };
  const $ = (id) => document.getElementById(id);
  const el = (...a) => M().el(...a);
  const NS = 'http://www.w3.org/2000/svg';

  /* A status as a word, the count's word, and its shape. */
  const STATUS = {
    ok: { word: 'OK', count: () => 'OK' },
    warn: { word: 'Check', count: () => 'to check' },
    fail: { word: 'Problem', count: (n) => (n === 1 ? 'problem' : 'problems') },
    info: { word: 'Note', count: (n) => (n === 1 ? 'note' : 'notes') },
  };
  const ORDER = ['ok', 'warn', 'fail', 'info'];
  // The verdict borrows a status's colour and shape: green is OK, amber a
  // check, red a problem.
  const VERDICT = { green: ['All clear', 'ok'], amber: ['Check these', 'warn'], red: ['Problems found', 'fail'] };
  const SECTION_SAY = { data: 'The right data went in', logic: 'The right logic was applied', words: 'The words match the numbers',
                        repro: 'It can be made again from the raw data', concerns: 'What a careful reader should know' };
  const stOf = (s) => (STATUS[s] ? s : 'info');
  const when = (s) => { try { return new Date(s).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' }); } catch (e) { return s; } };
  const size = (b) => (b == null || !isFinite(b) ? 'n/a' : b >= 1e9 ? (b / 1e9).toFixed(2) + ' GB' : b >= 1e6 ? (b / 1e6).toFixed(1) + ' MB'
    : b >= 1e3 ? (b / 1e3).toFixed(0) + ' kB' : b + ' bytes');
  const ratSay = (r) => (/^\d+$/.test(String(r)) ? 'J' + r : String(r));

  /* The shape of a status, drawn: a ticked circle, a triangle with a bar,
     a crossed octagon, a square with an i. Hidden from screen readers:
     the word beside it says the same. */
  function icon(s) {
    const sv = (tag, a) => { const n = document.createElementNS(NS, tag); for (const k in a) n.setAttribute(k, a[k]); return n; };
    const g = sv('svg', { viewBox: '0 0 16 16', class: 'sanicon', 'aria-hidden': 'true', focusable: 'false', 'data-shape': s });
    const add = (tag, a) => g.appendChild(sv(tag, a));
    if (s === 'ok') {
      add('circle', { cx: 8, cy: 8, r: 7.2, class: 'f' });
      add('path', { d: 'M4.6 8.4 7 10.7 11.5 5.6', class: 'k' });
    } else if (s === 'warn') {
      add('path', { d: 'M8 1.2 15.2 14.6H.8Z', class: 'f' });
      add('path', { d: 'M8 5.9v4', class: 'k' });
      add('circle', { cx: 8, cy: 12.4, r: 0.6, class: 'k' });
    } else if (s === 'fail') {
      add('path', { d: 'M5.1 .9h5.8l4.2 4.2v5.8l-4.2 4.2H5.1L.9 10.9V5.1Z', class: 'f' });
      add('path', { d: 'M5.4 5.4l5.2 5.2M10.6 5.4l-5.2 5.2', class: 'k' });
    } else {
      add('rect', { x: 1, y: 1, width: 14, height: 14, rx: 3, class: 'f' });
      add('path', { d: 'M8 7.2v4.6', class: 'k' });
      add('circle', { cx: 8, cy: 4.7, r: 0.6, class: 'k' });
    }
    return g;
  }
  const chip = (s) => el('span', { class: 'sanchip', 'data-s': s }, [icon(s), STATUS[s].word]);

  function card(id, title, help, kids, cls) {
    return el('div', { class: 'card' + (cls ? ' ' + cls : ''), id }, [el('div', { class: 'hrow' }, [el('h2', { text: title }), help ? M().qh(help) : null])].concat(kids));
  }

  async function load() {
    const seq = ++P.seq;
    P.loading = true;
    render();
    let got = null, err = null;
    try { got = await M().getJSON('/data/sanity'); } catch (e) { err = e.message; }
    if (seq !== P.seq) return;
    P.data = got && got.ok !== false ? got : null;
    P.err = err;
    P.loading = false;
    render();
  }

  async function make() {
    if (P.making) return;
    P.making = true; P.makeErr = null; P.makeNote = '';
    const b = $('sanmake');
    // Only the button says it is working: the report stays as it was
    // until the new one is read.
    if (b) { b.disabled = true; b.textContent = 'Working: starting'; }
    try {
      await M().runHere('/sanity', { confirm: true }, (note) => {
        P.makeNote = note;
        const n = $('sanmake');
        if (n) n.textContent = 'Working: ' + note;
      });
    } catch (e) {
      P.makeErr = /404|not found/i.test(e.message) ? 'Jarvis is running older code without this button: restart it, then press it again.'
        : 'The checks could not be run: ' + e.message;
    }
    P.making = false;
    load();
  }

  /* ---------------- copying a command ---------------- */
  /* The clipboard, or, where the browser refuses it, the command selected
     for the reader to copy by hand. */
  async function copy(text, codeNode, note) {
    const say = (t) => { const n = $(note); if (n) n.textContent = t; };
    try {
      if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error('no clipboard');
      await navigator.clipboard.writeText(text);
      say('Copied.');
    } catch (e) {
      try {
        const r = document.createRange();
        r.selectNodeContents(codeNode);
        const s = getSelection();
        s.removeAllRanges(); s.addRange(r);
      } catch (e2) { /* nothing selected */ }
      say('This browser would not let the page copy: the command is selected, press Ctrl+C.');
    }
  }

  /* ---------------- pieces ---------------- */
  function verdict(D) {
    const counts = D.counts || {};
    const all = (D.sections || []).flatMap((s) => (s.checks || []).map((c) => Object.assign({ section: s.id }, c)));
    const n = (k) => (counts[k] != null ? counts[k] : all.filter((c) => stOf(c.status) === k).length);
    const v = VERDICT[D.verdict] || (n('fail') ? VERDICT.red : n('warn') ? VERDICT.amber : VERDICT.green);
    // What to read first: every problem, then every check, each a button
    // to its row (opened there).
    const first = all.filter((c) => c.status === 'fail').concat(all.filter((c) => c.status === 'warn'));
    return el('div', { class: 'card sanverdict', id: 'sanverdict', 'data-s': v[1], 'data-verdict': D.verdict || '' }, [
      el('div', { class: 'hrow' }, [el('h2', { text: '13 · Sanity check report' }), M().qh('sanity')]),
      el('p', { class: 'sanword', id: 'sanword' }, [icon(v[1]), el('span', { text: v[0] })]),
      el('p', { class: 'sansay', id: 'sansay', text: D.say || '' }),
      el('div', { class: 'sancounts', id: 'sancounts', role: 'group', 'aria-label': 'How many checks of each kind' },
        ORDER.map((k) => el('span', { class: 'sanchip', 'data-s': k, id: 'sancount_' + k, 'data-n': String(n(k)) }, [icon(k), n(k) + ' ' + STATUS[k].count(n(k))]))),
      first.length ? el('div', { class: 'santodo' }, [el('p', { class: 'small muted', text: 'Read these first:' }),
        el('ul', { id: 'santodo' }, first.map((c) => el('li', {}, el('button', { type: 'button', class: 'linkish', 'data-check': c.id, onclick: () => goTo(c.id) },
          [chip(c.status), ' ' + c.id + ' · ' + c.title]))))]) : null,
      el('div', { class: 'sanrun' }, [
        el('button', { type: 'button', class: 'more-btn', id: 'sanmake', disabled: P.making ? 'disabled' : null, onclick: make,
                       text: P.making ? 'Working: ' + (P.makeNote || 'starting') : 'Run again' }),
        el('span', { class: 'small muted', id: 'sanmade', text: 'Made ' + when(D.made) + '.' })]),
      P.makeErr ? el('p', { class: 'warn', id: 'sanerr', text: P.makeErr }) : null]);
  }

  /* A check's row, opened and brought into view. */
  function goTo(id) {
    const r = $('sancheck_' + id);
    if (!r) return;
    const d = r.querySelector('details');
    if (d) d.open = true;
    try { r.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch (e) { r.scrollIntoView(); }
    r.classList.remove('lit'); void r.offsetWidth; r.classList.add('lit');
  }

  function table(t, id) {
    if (!t || !(t.rows || []).length) return null;
    return el('div', { class: 'tablewrap' }, el('table', { class: 'moretable santable', id }, [
      el('thead', {}, el('tr', {}, (t.head || []).map((h) => el('th', { text: String(h) })))),
      el('tbody', {}, t.rows.map((r) => el('tr', {}, r.map((x) => el('td', { text: x == null ? '' : String(x) })))))]));
  }

  function row(c, i, fresh) {
    const s = stOf(c.status);
    const detail = (c.detail || []).filter((x) => x != null && x !== '');
    const more = c.how || detail.length || (c.table && (c.table.rows || []).length);
    return el('li', { class: 'sanrow' + (fresh ? ' fresh' : ''), id: 'sancheck_' + c.id, 'data-s': s, style: '--i:' + i }, [
      el('div', { class: 'sanstat' }, chip(s)),
      el('div', { class: 'sanbody' }, [
        el('p', { class: 'santitle' }, [el('span', { class: 'sanid', text: c.id }), c.title || '']),
        el('p', { class: 'sanresult', text: c.result || '' }),
        more ? el('details', { class: 'sanmore' }, [el('summary', { text: 'More' }),
          c.how ? el('p', { class: 'sanhow' }, [el('b', { text: 'How it was checked: ' }), c.how]) : null,
          detail.length ? el('ul', { class: 'sandetail' }, detail.map((x) => el('li', { text: String(x) }))) : null,
          table(c.table, 'santable_' + c.id)]) : null])]);
  }

  function section(s, fresh) {
    const checks = s.checks || [];
    const tally = ORDER.map((k) => [k, checks.filter((c) => stOf(c.status) === k).length]).filter((x) => x[1]);
    return card('sansec_' + s.id, s.title || SECTION_SAY[s.id] || s.id, null, [
      s.say ? el('p', { class: 'muted', text: s.say }) : null,
      el('p', { class: 'small santally', text: tally.map(([k, n]) => n + ' ' + STATUS[k].count(n)).join(', ') + '.' }),
      checks.length ? el('ol', { class: 'sanchecks' }, checks.map((c, i) => row(c, i, fresh)))
        : el('p', { class: 'muted', text: 'Nothing was checked here.' })], 'sansection');
  }

  function regenerate(D) {
    const steps = D.regenerate || [];
    if (!steps.length) return null;
    const all = steps.map((x) => x.command).join('\n');
    return card('sanregencard', 'Make it all again', null, [
      el('p', { text: 'Every step from the raw recordings to what was checked here, in this order. Each command is run from the app’s folder (_Jarvis/app), with the code and the recordings listed under What it was made with.' }),
      el('ol', { class: 'sanregen', id: 'sanregen' }, steps.map((x, i) => {
        const code = el('code', { text: x.command });
        return el('li', {}, [el('p', { class: 'sanstep', text: x.step }),
          el('div', { class: 'sancmd' }, [code, el('button', { type: 'button', class: 'more-btn small', id: 'sancopy_' + i, text: 'Copy',
            'aria-label': 'Copy the command for: ' + x.step, onclick: () => copy(x.command, code, 'sancopynote') })])]);
      })),
      el('details', { class: 'sanmore', id: 'sanall' }, [el('summary', { text: 'Every command as one block' }),
        el('pre', { class: 'sanblock' }, el('code', { id: 'sanallcode', text: all }))]),
      el('div', { class: 'sanrun' }, [el('button', { type: 'button', class: 'more-btn small', id: 'sancopyall', text: 'Copy every command',
        onclick: () => { $('sanall').open = true; copy(all, $('sanallcode'), 'sancopynote'); } }),
        el('span', { class: 'small muted', id: 'sancopynote', role: 'status', 'aria-live': 'polite' })])]);
  }

  function madeWith(D) {
    const v = D.versions || {};
    const code = D.code || {};
    const dirty = code.dirty || [];
    const inp = D.inputs || {};
    const recs = inp.recordings || [];
    const rats = inp.rats || [];
    return card('sanwith', 'What it was made with', null, [
      el('h3', { class: 'moresub', text: 'The code' }),
      el('dl', { class: 'sankv', id: 'sancode' }, [el('dt', { text: 'Commit' }), el('dd', { text: code.commit || 'not known' })]),
      dirty.length ? el('div', { id: 'sandirty' }, [
        el('p', { class: 'sandirtysay' }, [chip('warn'), ' Changed since that commit and not yet committed (' + dirty.length + (dirty.length === 1 ? ' file' : ' files')
          + '): the run used these as they are on this machine.']),
        el('ul', { class: 'sanfiles' }, dirty.map((p) => el('li', {}, el('code', { text: p }))))])
        : el('p', { id: 'sandirty', class: 'small' }, [chip('ok'), ' Nothing that affects the results has changed since that commit.']),
      el('h3', { class: 'moresub', text: 'The tools' }),
      Object.keys(v).length ? el('dl', { class: 'sankv', id: 'sanversions' }, Object.keys(v).flatMap((k) => [el('dt', { text: k }), el('dd', { text: String(v[k]) })]))
        : el('p', { class: 'muted', text: 'Not recorded.' }),
      el('h3', { class: 'moresub', text: 'The recordings' }),
      el('p', { text: (inp.rat_days != null ? inp.rat_days + ' rat-days' : recs.length + ' recordings') + (rats.length ? ' from ' + rats.length + ' rats: ' + rats.map(ratSay).join(', ') + '.' : '.') }),
      recs.length ? table({ head: ['Rat', 'Session', 'Folder', 'Files', 'Size'],
        rows: recs.map((r) => [ratSay(r.rat), r.day || '', r.folder || '', r.files == null ? 'n/a' : String(r.files), size(r.bytes)]) }, 'saninputs') : null]);
  }

  /* ---------------- everything ---------------- */
  function render() {
    const pane = $('sanitypane');
    if (!pane) return;
    if (window.MONO_STATIC) {
      pane.replaceChildren(card('sanstatic', '13 · Sanity check report', null, [el('p', { text: 'Not in this copy: it opens in Jarvis.' })]));
      return;
    }
    if (P.loading && !P.data) {
      // Read once a session; a reading after Run again keeps the old
      // report on screen until the new one is in.
      if (!pane.firstElementChild || pane.firstElementChild.id !== 'sanmissing') {
        pane.replaceChildren(el('div', { class: 'card', id: 'sanreading' }, el('p', { class: 'muted', text: 'Reading the report.' })));
      }
      return;
    }
    if (P.loading) return;
    const D = P.data;
    if (!D) {
      const quiet = !P.err || /404|not been|not run|no such|not yet/i.test(P.err);
      pane.replaceChildren(card('sanmissing', 'Not run yet', 'sanity', [
        el('p', { text: (quiet ? '' : P.err + ' ')
          + 'The checks go through what Joe is given (tabs 11 and 12, his figures and his site) back to the recordings it came from, and say plainly whether the right data went in, the right logic was applied, the words match the numbers and it can all be made again. Press Run the checks.' }),
        el('div', { class: 'sanrun' }, [el('button', { type: 'button', class: 'more-btn', id: 'sanmake', disabled: P.making ? 'disabled' : null, onclick: make,
          text: P.making ? 'Working: ' + (P.makeNote || 'starting') : 'Run the checks' })]),
        P.makeErr ? el('p', { class: 'warn', id: 'sanerr', text: P.makeErr }) : null]));
      return;
    }
    // The rows come in once per report, not every time the tab is shown.
    const fresh = P.drawn !== D.made;
    P.drawn = D.made;
    pane.replaceChildren(verdict(D), ...(D.sections || []).map((s) => section(s, fresh)), regenerate(D), madeWith(D));
  }

  /* Shown again, the report already drawn stays as it is (and its open
     rows open): nothing is read or drawn again until it is run again. */
  function show() {
    if (!P.data && !P.loading) load();
    else if (!(P.data && P.drawn === P.data.made && $('sanverdict'))) render();
  }
  return { show, render, load, make, goTo, get state() { return { data: P.data, err: P.err, loading: P.loading, making: P.making }; } };
})();
