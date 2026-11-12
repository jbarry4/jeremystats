/* rcmeta.js -- Root Canal's Meta Workflow (2026-11-11).

   "In addition to The Workflow, create a Meta Workflow: run the verified
   dentate spike workflow, the verified P-spike workflow and the Ambiguous
   workflow, and note how much the two overlap. Find the set of parameters
   that leads to the minimum amount of ambiguous spikes -- a single output of
   the best parameters. Two instances, one for 5% and one at 10% grace."

   One module, painted by Root Canal when its view bar says Meta Workflow
   (rootcanal.js). The server searches (backend/rcmeta.py, the
   /api/rootcanal/meta* routes); this shows each instance's one answer: the
   best settings beside today's, and how many fewer purple they leave. How
   it got there, the next best and the checks are folded under it.

   WHILE IT SEARCHES (2026-11-11: "show progress with descriptive
   descriptions / loading, and if it crashes out it can pick up where it
   left off"): every step of the plan, ticked as it finishes; the one
   running in words, with a bar, what it is measuring and roughly how long
   is left; the best found so far. A run Jarvis lost (a restart, a crash)
   says where it stopped and offers Resume, which replays the search off
   the measurements kept on disk and goes on from there. Runs wait in line
   for one another. */
'use strict';

BARRY.rcMeta = (function () {
  const M = { list: null, err: null, amb: [], loading: false, open: {}, newOn: false,
              newGrace: 0.05, newAmb: null, newName: '', busy: false, plan: [] };
  const ACTIVE = (r) => !!(r.run && (r.run.status === 'running' || r.run.status === 'queued'));
  let root = null;
  let H = null;
  let pollT = null;

  const fmtN = (v) => (v == null ? '—' : Number(v).toLocaleString());
  const pct = (a, n) => (a == null || !n ? '—' : (100 * a / n).toFixed(a / n < 0.1 ? 1 : 0) + '%');
  const graceWords = (g) => (g == null ? '—' : Math.round(Number(g) * 1000) / 10 + '%');
  const since = (t) => { const s = Math.max(0, Math.round(Date.now() / 1000 - t));
    return s < 90 ? s + ' s' : Math.round(s / 60) + ' min'; };

  async function load() {
    if (M.loading) return;
    M.loading = true;
    try {
      const got = await api('/api/rootcanal/meta');
      M.list = got.metas || [];
      M.amb = got.ambiguous || [];
      M.plan = got.plan || [];
      if (!M.newAmb && M.amb.length) M.newAmb = M.amb[0].artifact_id;
      M.err = null;
    } catch (e) {
      M.err = e.message;
      if (M.list === null) M.list = [];
    }
    M.loading = false;
    refresh();
    clearTimeout(pollT);
    if ((M.list || []).some(ACTIVE)) {
      pollT = setTimeout(() => { if (root && root.isConnected) load(); }, 2000);
    }
  }

  async function run(r, quiet) {
    try {
      await apiPost('/api/rootcanal/meta/' + encodeURIComponent(r.artifact_id) + '/run', {});
      if (!quiet) {
        const st = r.run || {};
        toast(st.status === 'interrupted' || st.status === 'failed'
          ? '‘' + r.name + '’ picks up where it left off: what it measured before is read back from disk.'
          : '‘' + r.name + '’ is searching. It takes a while; this page shows where it is.', 'ok', 7000);
      }
    } catch (e) {
      toast('Not started: ' + e.message, 'err', 9000);
    }
    load();
  }

  /* Every instance not already going, in line, one after another: they
     share every measurement, so the second is quicker than the first. */
  async function runAll() {
    const todo = (M.list || []).filter((r) => !ACTIVE(r));
    for (const r of todo) await run(r, true);
    if (todo.length) toast(todo.length + ' meta workflow' + (todo.length === 1 ? '' : 's')
      + ' in line. They run one after another; this page shows where each is.', 'ok', 7000);
  }

  async function create() {
    if (M.busy) return;
    M.busy = true;
    try {
      await apiPost('/api/rootcanal/meta', { grace: M.newGrace, name: M.newName,
        ambiguous: { artifact_id: M.newAmb } });
      M.newOn = false;
      M.newName = '';
    } catch (e) {
      toast('Not made: ' + e.message, 'err', 9000);
    }
    M.busy = false;
    load();
  }

  function node(helpers) {
    H = helpers || H;
    if (M.list === null) load();
    root = build();
    return root;
  }

  function refresh() {
    if (root && root.isConnected) {
      const fresh = build();
      root.replaceWith(fresh);
      root = fresh;
    } else if (H && H.render) {
      H.render();
    }
  }

  function build() {
    try {
      return el('div', { class: 'meta' }, [
        head(),
        M.newOn ? newCard() : null,
        M.err ? el('p', { class: 'hint wf-err', text: 'The meta workflows could not be listed: ' + M.err }) : null,
        M.list === null ? el('div', { class: 'card' }, [loader('Reading the meta workflows')])
          : M.list.length ? el('div', { class: 'meta-list' }, M.list.map(card))
          : el('div', { class: 'card' }, [el('p', { class: 'hint', text: 'No meta workflow yet. '
              + 'Make one: it finds the settings that leave the fewest events ambiguous.' })]),
      ].filter(Boolean));
    } catch (e) {
      try { reportClientError('rootcanal.meta.build', e.message, String(e && e.stack)); } catch (err) { /* fine */ }
      return el('div', { class: 'card' }, [el('p', { class: 'hint wf-err',
        text: 'The Meta Workflow could not be drawn: ' + e.message })]);
    }
  }

  function head() {
    return el('div', { class: 'card wf-head' }, [
      el('div', { class: 'wf-head-row' }, [
        el('strong', { text: 'Meta Workflow' }),
        el('span', { class: 'hint', text: 'The measurement settings that leave the fewest events ambiguous '
          + '(purple: inside both the DS box and the P-spike box of an Ambiguous Dataset workflow). '
          + 'It turns the amplitude filter, the peak window, the half-width search and the HF band, '
          + 'and gives one answer: the best settings.' }),
      ]),
      el('div', { class: 'wf-head-row' }, [
        BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'Run all', extra: 'meta-runall',
          disabled: !(M.list || []).some((r) => !ACTIVE(r)), onclick: runAll }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'New meta workflow', extra: 'meta-new',
          onclick: () => { M.newOn = !M.newOn; refresh(); } }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Refresh', onclick: () => load() }),
      ]),
    ]);
  }

  function newCard() {
    return el('div', { class: 'card meta-newcard' }, [
      el('div', { class: 'wf-head-row' }, [
        el('span', { class: 'section-label', text: 'Improve' }),
        el('select', { id: 'metaAmb', onchange: (e) => { M.newAmb = e.target.value; } },
          M.amb.map((a) => el('option', { value: a.artifact_id, selected: a.artifact_id === M.newAmb,
            text: a.nickname + ' · v' + a.version }))),
        el('span', { class: 'section-label', text: 'Grace' }),
        BARRY.ui.seg([[0.05, '5%'], [0.1, '10%']], M.newGrace, (v) => { M.newGrace = v; refresh(); },
          { extra: 'meta-grace' }),
        el('input', { id: 'metaName', type: 'text', placeholder: 'Name (optional)', value: M.newName,
          oninput: (e) => { M.newName = e.target.value; } }),
        BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'Make it', disabled: M.busy || !M.newAmb,
          onclick: create }),
      ]),
    ]);
  }

  /* ONE ANSWER PER INSTANCE: the best settings beside today's, and the
     purple they leave. The rest is folded. */
  function card(r) {
    const d = r.definition || {};
    const res = r.result;
    const st = r.run || {};
    const running = st.status === 'running', queued = st.status === 'queued';
    const stopped = st.status === 'interrupted' || st.status === 'failed';
    const kids = [el('div', { class: 'meta-top' }, [
      el('div', { class: 'meta-title' }, [
        el('strong', { text: r.name }),
        el('span', { class: 'hint', text: 'grace ' + graceWords(d.grace) + ' · improves ‘'
          + ((d.ambiguous || {}).nickname || '?') + '’' + (r.version ? ' · v' + r.version : '')
          + (res && res.at ? ' · ' + new Date(res.at).toLocaleString() + (res.by ? ' · ' + res.by : '') : '') }),
      ]),
      BARRY.ui.button({ kind: stopped || !res ? 'primary' : 'ghost', size: 'sm', extra: 'meta-run',
        text: running ? 'Searching…' : queued ? 'Waiting…' : stopped ? 'Resume' : res ? 'Run again' : 'Run',
        disabled: running || queued, onclick: () => run(r) }),
    ])];
    if (running) kids.push(progress(st));
    else if (queued) kids.push(waiting(r));
    else if (stopped) kids.push(stoppedNote(st));
    if (!res) {
      if (!running && !queued && !stopped) kids.push(el('p', { class: 'hint', text: 'Not run yet.' }));
      return el('div', { class: 'card meta-card', 'data-id': r.artifact_id }, kids);
    }
    if (running || queued || stopped) {
      kids.push(el('p', { class: 'section-label meta-last', text: 'The last answer' }));
    }
    const b = res.best || {}, t = res.today || {};
    const bs = b.score || {}, ts = t.score || {};
    const n = bs.n || ts.n;
    const drop = ts.purple ? (ts.purple - bs.purple) / ts.purple : null;
    kids.push(el('div', { class: 'meta-answer' }, [
      el('div', { class: 'meta-big' }, [
        el('span', { class: 'meta-purple-dot' }),
        el('span', { class: 'meta-num', text: fmtN(bs.purple) }),
        el('span', { class: 'meta-of', text: 'ambiguous of ' + fmtN(n) + ' (' + pct(bs.purple, n) + ')' }),
        el('span', { class: 'meta-was', text: 'today ' + fmtN(ts.purple) + ' (' + pct(ts.purple, n) + ')'
          + (drop != null ? ' · ' + Math.round(100 * drop) + '% fewer' : '') }),
      ]),
      settingsTable(t, b),
      classBars(ts, bs, n),
    ]));
    kids.push(fold('How it got there', trail(res)));
    kids.push(fold('The next best settings', near(res)));
    kids.push(fold('Checks', checks(res)));
    return el('div', { class: 'card meta-card', 'data-id': r.artifact_id }, kids);
  }

  function settingsTable(t, b) {
    const row = (name, a, z) => el('tr', { class: a === z ? '' : 'meta-changed' }, [
      el('th', { text: name }), el('td', { text: a }), el('td', { text: z })]);
    const band = (s) => Math.round(s.band_lo) + '–' + Math.round(s.band_hi) + ' Hz';
    return el('div', { class: 'meta-tablewrap' }, [el('table', { class: 'meta-table' }, [
      el('thead', {}, [el('tr', {}, [el('th', { text: '' }), el('th', { text: 'Today' }),
        el('th', { text: 'Best' })])]),
      el('tbody', {}, [
        row('Amplitude filter', t.filter_words, b.filter_words),
        row('Peak window', '±' + t.win_ms + ' ms', '±' + b.win_ms + ' ms'),
        row('Half-width search', '±' + t.cross_ms + ' ms', '±' + b.cross_ms + ' ms'),
        row('HF power band', band(t), band(b)),
      ]),
    ])]);
  }

  /* WHERE THE SEARCH IS: every step of the plan, ticked as it finishes;
     the one running in words, with a bar, what it is measuring and about
     how long is left in it; and the best found so far. */
  const mins = (s) => (s < 60 ? Math.max(1, Math.round(s)) + ' s' : s < 5400 ? Math.round(s / 60) + ' min'
    : (s / 3600).toFixed(1) + ' h');
  function progress(st) {
    const now = Date.now() / 1000;
    const doneSteps = new Set(st.done_steps || []);
    const plan = M.plan.length ? M.plan : [[st.step || 'search', st.words || 'Searching']];
    const at = plan.findIndex(([k]) => k === st.step);
    const rows = plan.map(([k, words], i) => {
      const state = doneSteps.has(k) && k !== st.step ? 'done' : k === st.step ? 'now' : i < at ? 'done' : 'todo';
      if (state !== 'now') {
        return el('li', { class: 'meta-step ' + state, 'data-step': k }, [
          el('span', { class: 'meta-tick', text: state === 'done' ? '✓' : '○' }),
          el('span', { text: words })]);
      }
      const of = st.of || 0, done = st.done || 0;
      const frac = of ? Math.min(1, done / of) : null;
      const inStep = st.step_started ? now - st.step_started : 0;
      const left = frac && frac < 1 && done > 0 ? inStep / done * (of - done) : null;
      return el('li', { class: 'meta-step now', 'data-step': k }, [
        el('span', { class: 'meta-tick' }, [el('span', { class: 'meta-spin' })]),
        el('div', { class: 'meta-now' }, [
          el('span', { class: 'meta-now-words', text: st.words || words }),
          frac != null ? el('div', { class: 'meta-prog', role: 'progressbar', 'aria-valuemin': '0',
            'aria-valuemax': String(of), 'aria-valuenow': String(done) }, [
            el('span', { style: 'width:' + (100 * frac).toFixed(1) + '%' })]) : null,
          el('span', { class: 'hint meta-now-item', text: [
            of ? done + ' of ' + of : null,
            st.item || null,
            left ? 'about ' + mins(left) + ' left in this step' : null,
          ].filter(Boolean).join(' · ') || 'working' }),
        ].filter(Boolean)),
      ]);
    });
    return el('div', { class: 'meta-progress' }, [
      el('div', { class: 'meta-prog-head' }, [
        el('strong', { text: 'Searching · ' + mins(now - (st.started || now)) }),
        st.best != null ? el('span', { class: 'meta-sofar', text: 'best so far ' + fmtN(st.best) + ' purple'
          + (st.today != null ? ' (today ' + fmtN(st.today) + ')' : '') }) : null,
      ].filter(Boolean)),
      st.best_words ? el('span', { class: 'hint', text: st.best_words }) : null,
      el('ol', { class: 'meta-steps' }, rows),
      el('span', { class: 'hint', text: (st.resumed ? 'Picked up where the last run stopped: what it '
        + 'measured is read back from disk. ' : '') + 'Every measurement is kept on disk as it is made: '
        + 'if Jarvis stops, Resume picks up from here.' }),
    ].filter(Boolean));
  }

  function waiting(r) {
    const ahead = (M.list || []).find((x) => x.run && x.run.status === 'running');
    return el('p', { class: 'meta-status' }, [loader(ahead
      ? 'Waiting in line behind ‘' + ahead.name + '’; it starts when that one is done.'
      : 'Waiting in line; it starts in a moment.')]);
  }

  function stoppedNote(st) {
    const where = st.words ? ' while: ' + st.words : '';
    return el('div', { class: 'meta-stopped' }, [
      el('strong', { text: st.status === 'failed' ? 'The last search stopped with an error' + where + '.'
        : 'The last search was interrupted' + where + (st.ended ? ' (' + new Date(st.ended * 1000).toLocaleString() + ')' : '') + '.' }),
      st.error ? el('span', { class: 'hint wf-err', text: st.error }) : null,
      el('span', { class: 'hint', text: 'Resume picks up where it left off: every measurement it made is '
        + 'read back from disk, and it goes on from there.' }),
    ].filter(Boolean));
  }

  /* Today's four classes and the best's, as two bars on one scale. */
  function classBars(ts, bs, n) {
    const parts = [['purple', 'both (ambiguous)', 'meta-c-both'], ['ds', 'DS box only', 'meta-c-ds'],
                   ['pspike', 'P-spike box only', 'meta-c-p'], ['neither', 'neither', 'meta-c-none']];
    const bar = (s, label) => el('div', { class: 'meta-barrow' }, [
      el('span', { class: 'meta-barlab', text: label }),
      el('div', { class: 'meta-bar' }, parts.map(([k, w, c]) => el('span', {
        class: 'meta-seg ' + c, style: 'flex-grow:' + Math.max(0, s[k] || 0),
        title: w + ': ' + fmtN(s[k]) + ' (' + pct(s[k], n) + ')' }))),
    ]);
    return el('div', { class: 'meta-bars' }, [
      bar(ts, 'Today'), bar(bs, 'Best'),
      el('div', { class: 'meta-key' }, parts.map(([k, w, c]) => el('span', {}, [
        el('i', { class: 'meta-sw ' + c }),
        document.createTextNode(w + ' ' + fmtN(ts[k]) + ' → ' + fmtN(bs[k]))]))),
    ]);
  }

  function fold(title, body) {
    return el('details', { class: 'meta-fold' }, [el('summary', { text: title }), body]);
  }

  function trail(res) {
    return el('ol', { class: 'meta-trail' }, (res.trail || []).map((x) => el('li', {}, [
      el('strong', { text: x.words + ': ' + fmtN(x.purple) + ' purple' }),
      el('span', { class: 'hint', text: ' · ' + fmtN(x.tried) + ' setting' + (x.tried === 1 ? '' : 's')
        + ' tried · best then: ' + settingWords(x.setting) }),
    ])));
  }

  const settingWords = (s) => (s ? s.filter_words + ' · peak ±' + s.win_ms + ' ms · half-width ±'
    + s.cross_ms + ' ms · HF ' + Math.round(s.band_lo) + '–' + Math.round(s.band_hi) + ' Hz' : '—');

  function near(res) {
    return el('ol', { class: 'meta-trail' }, (res.near || []).map((x) => el('li', {}, [
      el('strong', { text: fmtN(x.purple) + ' purple' }),
      el('span', { class: 'hint', text: ' · ' + settingWords(x.setting) }),
    ])));
  }

  function checks(res) {
    const ds = res.dataset || {};
    const t = (res.today || {}).score || {};
    const same = ds.purple != null && Math.abs(Number(ds.grace) - Number(res.grace)) < 1e-9;
    const lines = [
      same ? (t.purple === ds.purple
        ? 'Today’s settings, measured again here, leave ' + fmtN(t.purple) + ' purple: the same as ‘'
          + ds.nickname + '’ v' + ds.version + ' itself.'
        : 'Today’s settings, measured again here, leave ' + fmtN(t.purple) + ' purple, but ‘' + ds.nickname
          + '’ v' + ds.version + ' says ' + fmtN(ds.purple) + '. The answer may not carry over.')
        : '‘' + ds.nickname + '’ ran at ' + graceWords(ds.grace) + ' grace (' + fmtN(ds.purple)
          + ' purple there); this asks the same boxes at ' + graceWords(res.grace) + '.',
      'Every number is Root Canal’s own measure, on the reads on this machine: the DS box around the '
        + fmtN(((res.pools || {}).ctl || {}).n) + ' events of ‘' + (((res.pools || {}).ctl || {}).nickname || '?')
        + '’, the P-spike box around the ' + fmtN(((res.pools || {}).p || {}).n) + ' hand-sorted P-spikes, '
        + 'applied to the ' + fmtN(((res.pools || {}).tgt || {}).n) + ' events of ‘'
        + (((res.pools || {}).tgt || {}).nickname || '?') + '’.',
      'A setting that measures fewer than ' + Math.round(100 * (res.guard || 0.95)) + '% as many events as '
        + 'today’s (on any of the three) does not count: losing events is the cheapest way to fewer purple.',
      fmtN(res.evaluated) + ' settings scored, ' + fmtN(res.eligible) + ' of them allowed; '
        + fmtN(res.passes) + ' measuring passes'
        + (res.kept ? ', and ' + fmtN(res.kept) + ' measurements read back from an earlier run' : '')
        + '; ' + Math.round((res.seconds_total || 0) / 60) + ' min.',
    ].concat(res.mismatch || []);
    return el('ul', { class: 'meta-checks' }, lines.map((w) => el('li', { text: w })));
  }

  return { node, _state: () => M, _load: load, _progress: progress };
})();
