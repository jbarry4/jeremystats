/* ==========================================================================
   AI Beta -- Checkup's sandbox.

   Can a model sort dentate spike candidates the way people did? This panel
   trains one on the settled decisions of every finished set and tests it on
   mice it never saw, then says how it did. That is all. It writes no label,
   no set and no bank version; Braces never sees it. Running it on new,
   undecided sets is a later step and deliberately not here.

   Drawn inside Checkup (toolkit.js, `renderCuration`) when the header's
   Sets | AI Beta switch says so. The server half is backend/aibeta.py.
   ========================================================================== */
BARRY.aibeta = (function () {
  let st = null;            // GET /api/aibeta/state
  let stErr = null;
  let loading = false;
  let planned = null;       // POST /api/aibeta/plan, for the current pick
  let planning = false;
  let planSeq = 0;
  let job = null;           // the running job's snapshot
  let poll = null;
  let shown = null;         // the run on screen, in full
  let shownId = null;
  let shownErr = null;

  const pick = {
    entries: null,          // a Set of entry ids, or null for every one
    families: null,         // a Set of family ids
    model: 'hgb',
    channels: 'all',        // 'all', or 'even' for CSC 2, 4 ... 64 only
    choosing: false,        // the recording list unfolded
    skipped: false,         // the "not used" list unfolded
    byRec: false,           // the per-recording results unfolded
  };

  const STAGE = {
    'ai read': 'Reading recordings',
    'ai train': 'Training and testing',
  };

  /* ---------- small formatting ---------- */
  const pct = (x, dp) => (x === null || x === undefined || !isFinite(x))
    ? '—' : (100 * x).toFixed(dp === undefined ? 1 : dp) + '%';
  const num = (x) => (x === null || x === undefined) ? '—'
    : Number(x).toLocaleString();
  const plural = (n, one, many) => num(n) + ' ' + (n === 1 ? one : (many || one + 's'));

  /* "-0400" without its colon is what the server writes, and Date will not
     always take it. */
  function when(at) {
    const raw = String(at || '').trim().replace(' ', 'T')
      .replace(/([+-]\d{2})(\d{2})$/, '$1:$2');
    return raw ? fmtWhen(raw) : '';
  }

  function famName(id) {
    const f = ((st && st.families) || []).find((x) => x.id === id);
    return f ? f.name : id;
  }

  function modelName(id) {
    const m = ((st && st.models) || []).find((x) => x.id === id);
    return m ? m.name : id;
  }

  /* ---------- loading ---------- */
  async function load() {
    if (loading) return;
    loading = true;
    stErr = null;
    try {
      st = await api('/api/aibeta/state');
    } catch (e) {
      stErr = e.message;
      st = null;
    }
    loading = false;
    if (st) {
      if (!pick.families) {
        pick.families = new Set(st.families.filter((f) => f.default)
                                           .map((f) => f.id));
      }
      if (st.running && !job) {
        job = st.running;
        startPoll();
      }
      if (!shownId && st.runs.length) shownId = st.runs[0].id;
    }
    render();
    if (st) {
      requestPlan();
      if (shownId && (!shown || shown.id !== shownId)) openRun(shownId);
    }
  }

  async function openRun(id) {
    shownId = id;
    shownErr = null;
    try {
      shown = (await api('/api/aibeta/run/' + encodeURIComponent(id))).run;
    } catch (e) {
      shown = null;
      shownErr = e.message;
    }
    paintResults();
  }

  function chosenIds() {
    if (!st) return [];
    return st.entries.filter((e) => !pick.entries || pick.entries.has(e.entry_id))
                     .map((e) => e.entry_id);
  }

  /* What a run would cost, asked again whenever the pick changes. Opening
     every recording is a few seconds, so the newest answer wins and an older
     one arriving late is dropped. */
  async function requestPlan() {
    if (!st) return;
    const seq = ++planSeq;
    planning = true;
    paintPlan();
    let got = null;
    try {
      got = await apiPost('/api/aibeta/plan', {
        entries: pick.entries ? chosenIds() : null,
        channels: pick.channels });
    } catch (e) {
      got = { ok: false, error: e.message };
    }
    if (seq !== planSeq) return;
    planning = false;
    planned = got;
    paintPlan();
  }

  /* ---------- running ---------- */
  async function train() {
    if (job) return;
    const ids = chosenIds();
    if (!ids.length) { toast('Pick at least one recording.', 'warn'); return; }
    if (!pick.families.size) {
      toast('Pick at least one kind of input.', 'warn');
      return;
    }
    let got;
    try {
      got = await apiPost('/api/aibeta/train', {
        entries: pick.entries ? ids : null,
        families: Array.from(pick.families),
        model: pick.model,
        channels: pick.channels,
      });
    } catch (e) {
      toast(e.message, 'err', 9000);
      return;
    }
    job = got.job;
    startPoll();
    render();
  }

  async function stop() {
    if (!job) return;
    try { await apiPost('/api/cfc/job/' + job.id + '/cancel', {}); } catch (e) {}
  }

  function startPoll() {
    if (poll) return;
    poll = setInterval(tick, 1000);
  }

  function stopPoll() {
    if (poll) clearInterval(poll);
    poll = null;
  }

  async function tick() {
    if (!job) { stopPoll(); return; }
    /* Nobody is looking: the panel is not on the page. Stop asking, and
       pick the job up again from `paint` when it is drawn. */
    if (!document.getElementById('aiBeta')) { stopPoll(); return; }
    let got;
    try { got = await api('/api/cfc/job/' + job.id); } catch (e) { return; }
    job = got.job;
    paintJob();
    if (job.status === 'running') return;
    stopPoll();
    const done = job;
    job = null;
    if (done.status === 'done') {
      let res = null;
      try { res = (await api('/api/cfc/result/' + done.id)).result; }
      catch (e) { /* the list below still finds it */ }
      if (res && res.id) {
        shownId = res.id;
        shown = null;
      }
      toast('Trained and tested.', 'ok');
    } else if (done.status !== 'canceled') {
      toast(done.error || 'The training run did not finish.', 'err', 9000);
    }
    st = null;
    load();
  }

  /* ---------- drawing ---------- */
  function paint(host) {
    const root = el('div', { class: 'ai-beta', id: 'aiBeta' });
    host.appendChild(root);
    if (!st && !loading) { load(); return; }
    render();
    if (job) startPoll();
  }

  function render() {
    const root = document.getElementById('aiBeta');
    if (!root) return;
    root.innerHTML = '';
    if (!st) {
      if (stErr) {
        root.appendChild(el('div', { class: 'empty-state' }, [
          el('p', { text: 'AI Beta could not read what it learns from: '
                          + stErr }),
          BARRY.ui.button({ text: 'Try again', onclick: () => load() }),
        ]));
      } else {
        root.appendChild(el('div', { class: 'tk-loading' }, [
          loader('AI Beta', 'reading the Event Bank for finished sets')]));
      }
      return;
    }
    if (!st.have_sklearn) {
      root.appendChild(el('div', { class: 'card ai-warn' }, [
        el('p', { text: 'Training needs scikit-learn, which is not '
                        + 'installed on this machine. Everything below can '
                        + 'be read; nothing can be trained here.' })]));
    }
    root.appendChild(introCard());
    if ((st.reports || []).length) root.appendChild(reportCard());
    root.appendChild(setupCard());
    root.appendChild(el('div', { id: 'aiJob' }));
    root.appendChild(el('div', { id: 'aiResults' }));
    root.appendChild(runsCard());
    paintPlan();
    paintJob();
    paintResults();
  }

  function introCard() {
    const s = st.summary || {};
    const src = s.by_source || {};
    return el('div', { class: 'card ai-intro' }, [
      el('p', { class: 'ai-lede', text:
        'A sandbox. The model learns from finished Checkup sets and is '
        + 'tested on mice it never saw. Nothing here changes a set, a bank '
        + 'entry or anything Braces reads.' }),
      BARRY.ui.chipRow([
        BARRY.ui.chip(plural(s.n_recordings || 0, 'recording')),
        BARRY.ui.chip(plural(s.n_mice || 0, 'mouse', 'mice')),
        BARRY.ui.chip(num(s.n_ds) + ' DS'),
        BARRY.ui.chip(num(s.n_garbage) + ' Garbage'),
        ...Object.keys(src).sort().map((k) =>
          BARRY.ui.chip(src[k] + ' from ' + k)),
      ]),
      el('p', { class: 'hint', text:
        'What it learns from, for each recording: the undecided version '
        + '(v0) as the candidates, and the last version before Braces that '
        + 'holds only DS and Garbage as the answer. Every stamp is put on '
        + 'the recording’s own clock before anything is read. A recording '
        + 'rejected whole, every candidate Garbage, is left out: that is a '
        + 'call about the recording, not about any one candidate.' }),
    ]);
  }

  /* ---------- the setup ---------- */
  function setupCard() {
    const card = el('div', { class: 'card ai-setup' });
    const all = st.entries.length;
    const n = chosenIds().length;
    const mice = new Set(st.entries
      .filter((e) => !pick.entries || pick.entries.has(e.entry_id))
      .map((e) => e.mouse_key)).size;

    card.appendChild(BARRY.ui.field({
      label: 'Learn from',
      control: el('div', { class: 'ai-row' }, [
        el('span', { class: 'ai-strong', text:
          (n === all ? 'All ' : '') + plural(n, 'recording') + ' · '
          + plural(mice, 'mouse', 'mice') }),
        BARRY.ui.button({ kind: 'mini',
          text: pick.choosing ? 'Done choosing' : 'Choose…',
          onclick: () => { pick.choosing = !pick.choosing; render(); } }),
        st.skipped.length ? BARRY.ui.button({ kind: 'mini',
          text: (pick.skipped ? 'Hide ' : 'Show ')
                + plural(st.skipped.length, 'entry', 'entries')
                + ' not used',
          onclick: () => { pick.skipped = !pick.skipped; render(); } })
          : null,
      ].filter(Boolean)),
    }));
    if (pick.choosing) card.appendChild(entryList());
    if (pick.skipped) card.appendChild(skippedList());

    card.appendChild(BARRY.ui.field({
      label: 'Inputs',
      control: el('div', { class: 'ai-input-groups' }, [
        el('div', { class: 'ai-sub', text: 'The candidate' }),
        el('div', { class: 'ai-toggles' },
           st.families.filter((f) => !f.phys).map(toggleFor)),
        el('div', { class: 'ai-sub', text: 'Physiology — a second read' }),
        el('div', { class: 'ai-toggles' },
           st.families.filter((f) => f.phys && !f.group).map(toggleFor)),
        el('div', { class: 'ai-sub',
                    text: 'Pictures at the aligned peak — the second read' }),
        el('div', { class: 'ai-toggles' },
           st.families.filter((f) => f.group === 'pictures').map(toggleFor)),
      ]),
      hint: 'Each read takes every input in its group at once, so changing '
            + 'these later costs only the training. The second read is '
            + 'about an hour the first time, and only happens when one of '
            + 'its inputs is ticked.',
    }));

    const m = st.models.find((x) => x.id === pick.model) || st.models[0];
    card.appendChild(BARRY.ui.field({
      label: 'Model',
      control: BARRY.ui.seg(st.models.map((x) => [x.id, x.name, x.blurb]),
                            pick.model,
                            (v) => { pick.model = v; render(); }),
      hint: m ? m.blurb : null,
    }));

    /* Which contacts the reads see. Even only is every other contact on a
       linear array, read as such: twice the pitch apart, with the windows
       that are counted in contacts halved to cover the same depth. Its
       reads are cached apart from the full ones. */
    card.appendChild(BARRY.ui.field({
      label: 'Channels',
      control: BARRY.ui.seg([
        ['all', 'All', 'Every channel the recording has.'],
        ['even', 'Even only', 'CSC 2, 4, 6 and on: every other contact.'],
      ], pick.channels, (v) => { pick.channels = v; render(); requestPlan(); }),
      hint: pick.channels === 'even'
        ? 'Every other contact, read as twice the pitch apart. Read '
          + 'separately from the full channels the first time.'
        : 'Every channel the recording has.',
    }));

    card.appendChild(BARRY.ui.field({
      label: 'How it is tested',
      control: el('p', { class: 'ai-plain', text:
        'Whole mice are held out, ' + st.folds + ' ways round, so every '
        + 'score comes from animals the model never saw. The bar for calling '
        + 'something a dentate spike is set inside the training mice to keep '
        + pct(st.keep_ds, 0) + ' of real ones; anything under it is a flag '
        + 'for a person, never thrown away. Classes are balanced.' }),
    }));

    card.appendChild(el('div', { class: 'ai-go' }, [
      el('div', { class: 'ai-plan', id: 'aiPlan' }),
      BARRY.ui.button({
        kind: 'primary', id: 'aiTrain',
        text: 'Train and test on ' + plural(n, 'recording'),
        disabled: !!job || !n || !pick.families.size || !st.have_sklearn,
        onclick: train,
      }),
    ]));
    return card;
  }

  function toggleFor(f) {
    const on = pick.families.has(f.id);
    return el('label', { class: 'toggle' + (on ? ' on' : ''),
                         title: f.blurb }, [
      el('input', { type: 'checkbox', checked: on ? 'checked' : null,
        onchange: (ev) => {
          if (ev.target.checked) pick.families.add(f.id);
          else pick.families.delete(f.id);
          render();
        } }),
      el('span', { text: f.name }),
    ]);
  }

  function entryList() {
    const box = el('div', { class: 'ai-pick' });
    box.appendChild(el('div', { class: 'ai-row' }, [
      BARRY.ui.button({ kind: 'mini', text: 'All', onclick: () => {
        pick.entries = null; render(); requestPlan(); } }),
      BARRY.ui.button({ kind: 'mini', text: 'None', onclick: () => {
        pick.entries = new Set(); render(); requestPlan(); } }),
    ]));
    const rows = st.entries.map((e) => {
      const on = !pick.entries || pick.entries.has(e.entry_id);
      const fp = e.first_pass;
      return el('label', { class: 'ai-pick-row' + (on ? '' : ' off') }, [
        el('input', { type: 'checkbox', checked: on ? 'checked' : null,
          onchange: (ev) => {
            if (!pick.entries) {
              pick.entries = new Set(st.entries.map((x) => x.entry_id));
            }
            if (ev.target.checked) pick.entries.add(e.entry_id);
            else pick.entries.delete(e.entry_id);
            if (pick.entries.size === st.entries.length) pick.entries = null;
            render();
            requestPlan();
          } }),
        el('span', { class: 'ai-pick-name', text: e.label }),
        el('span', { class: 'ai-pick-meta', text:
          e.source + ' · answer from ' + e.version_name
          + (e.events_from === 'curation set' ? ' (via the curation set)' : '') }),
        el('span', { class: 'ai-pick-n', text:
          num(e.n_ds) + ' DS · ' + num(e.n_garbage) + ' Garbage' }),
        el('span', { class: 'ai-pick-meta', text: fp && fp.called
          ? 'first pass agreed ' + pct(fp.agree / fp.called, 0) : '' }),
      ]);
    });
    box.appendChild(el('div', { class: 'ai-pick-list' }, rows));
    return box;
  }

  function skippedList() {
    return el('div', { class: 'ai-pick' }, [
      el('div', { class: 'ai-pick-list' }, st.skipped.map((s) =>
        el('div', { class: 'ai-pick-row static' }, [
          el('span', { class: 'ai-pick-name', text: s.label || s.entry_id }),
          el('span', { class: 'ai-pick-meta', text: s.why }),
        ]))),
    ]);
  }

  function paintPlan() {
    const host = document.getElementById('aiPlan');
    if (!host) return;
    host.innerHTML = '';
    if (planning || !planned) {
      host.appendChild(el('span', { class: 'hint',
        text: 'Checking which recordings are already read…' }));
      return;
    }
    if (!planned.ok) {
      host.appendChild(el('span', { class: 'hint',
        text: 'Could not check what is already read: ' + planned.error }));
      return;
    }
    const bits = [];
    if (planned.to_read) {
      bits.push(plural(planned.to_read, 'recording') + ' to read ('
                + num(planned.events_to_read) + ' candidates), about '
                + spell(planned.read_s));
    }
    if (planned.cached) {
      bits.push(planned.cached + ' already read');
    }
    bits.push('training about ' + spell(planned.train_s));
    host.appendChild(el('span', { class: 'hint', text: bits.join(' · ') }));
    if ((planned.unreadable || []).length) {
      host.appendChild(el('span', { class: 'hint ai-bad', text:
        plural(planned.unreadable.length, 'recording')
        + ' cannot be opened here and will be left out: '
        + planned.unreadable.map((u) => u.label + ' (' + u.why + ')')
                            .join('; ') }));
    }
  }

  function spell(sec) {
    const s = Math.max(0, Math.round(sec || 0));
    if (s < 90) return Math.max(5, Math.round(s / 5) * 5) + ' seconds';
    return Math.round(s / 60) + ' minutes';
  }

  /* ---------- the job ---------- */
  function paintJob() {
    const host = document.getElementById('aiJob');
    if (!host) return;
    const btn = document.getElementById('aiTrain');
    if (btn) btn.disabled = !!job || !chosenIds().length
                          || !(pick.families && pick.families.size);
    if (!job) { host.innerHTML = ''; return; }
    const stages = job.stages || [];
    const now = stages.find((x) => x.status === 'running')
             || stages.find((x) => (x.done || 0) < (x.of || 0))
             || stages[stages.length - 1] || {};
    let total = 0, spent = 0;
    for (const s of stages) {
      total += s.of || 0;
      spent += Math.min(s.done || 0, s.of || 0);
    }
    const name = STAGE[now.name] || now.name || 'Working';
    const what = (now.of || 0) > 1
      ? name + ' — ' + num(Math.min(now.done || 0, now.of)) + ' of '
        + num(now.of) + (now.name === 'ai read' ? ' done' : '')
      : name + '…';
    const reading = (job.members || []).filter((m) => m.status === 'reading');
    const failed = (job.members || []).filter((m) => m.status === 'failed');
    const sub = [
      job.eta_s ? 'about ' + spell(job.eta_s) + ' left' : '',
      job.elapsed > 4 ? Math.round(job.elapsed) + ' s so far' : '',
    ].filter(Boolean).join('  ·  ');

    host.innerHTML = '';
    host.appendChild(el('div', { class: 'card ai-job' }, [
      el('div', { class: 'ai-row' }, [
        el('strong', { text: what }),
        el('span', { class: 'hint', text: sub }),
        el('div', { class: 'spacer' }),
        BARRY.ui.button({ size: 'sm', text: 'Stop',
          title: 'Stop after the recordings being read now. Whatever has '
               + 'been read is kept and will not be read again.',
          onclick: stop }),
      ]),
      el('div', { class: 'br-bar' }, [el('i', {
        style: 'width:' + Math.round(total ? 100 * spent / total : 0) + '%' })]),
      reading.length ? el('p', { class: 'hint', text: 'Now reading: '
        + reading.map((m) => m.label + (m.of ? ' (' + m.done + ' of '
                                        + m.of + ' stretches)' : ''))
                 .join(', ') }) : null,
      failed.length ? el('p', { class: 'hint ai-bad', text: 'Could not read: '
        + failed.map((m) => m.label + ' — ' + (m.error || 'unknown'))
                .join('; ') }) : null,
      el('p', { class: 'hint', text: 'Reading is done once per recording '
        + 'and kept; later runs only train. Each read takes a few hundred '
        + 'milliseconds around every candidate, on every channel.' }),
    ].filter(Boolean)));
  }

  /* ---------- results ---------- */
  function paintResults() {
    const host = document.getElementById('aiResults');
    if (!host) return;
    host.innerHTML = '';
    if (shownErr) {
      host.appendChild(el('div', { class: 'card ai-warn' }, [
        el('p', { text: 'That run could not be opened: ' + shownErr })]));
      return;
    }
    if (!shownId) {
      host.appendChild(el('div', { class: 'card' }, [
        el('div', { class: 'empty-state' }, [
          el('p', { text: 'No model has been trained yet. Choose what it '
                          + 'learns from above and press Train and test.' }),
        ])]));
      return;
    }
    if (!shown) {
      host.appendChild(el('div', { class: 'card' }, [
        loader('Opening the run', '')]));
      return;
    }
    host.appendChild(resultCard(shown));
  }

  function resultCard(run) {
    const res = run.results || {};
    const p = res.pooled || {};
    const d = run.data || {};
    const s = run.settings || {};
    const card = el('div', { class: 'card ai-result' });

    /* Whether this run is Tooth Fairy -- the model Checkup's Tooth Fairy
       sweeps sets with -- and whether it could be. Any run with the four
       bars and the held-out scores the tolerance is set from can. */
    const tf = st && st.tooth_fairy;
    const isTf = !!(tf && tf.ready && tf.run_id === run.id);
    const canTf = !!(res.policy && res.oof);
    card.appendChild(el('div', { class: 'ai-row ai-result-head' }, [
      el('strong', { text: 'How it did' }),
      el('span', { class: 'hint', text:
        when(run.at) + (run.by ? ' · ' + run.by : '') + ' · '
        + modelName(s.model) + ' · ' + (s.families || []).map(famName)
                                                          .join(', ')
        + (s.channels === 'even' ? ' · even channels only' : '') }),
      el('div', { class: 'spacer' }),
      isTf ? el('span', { class: 'stat-chip ok tf-chip',
        title: 'Checkup’s Tooth Fairy sorts sets with this run.' },
        [BARRY.toothFairy ? BARRY.toothFairy.icon() : null,
         'This is Tooth Fairy'].filter(Boolean)) : null,
      (!isTf && canTf) ? BARRY.ui.button({ size: 'sm',
          text: 'Make this Tooth Fairy',
          title: 'Sort sets with this run from Checkup’s Tooth Fairy, '
               + 'using its bars.',
          onclick: () => makeToothFairy(run.id) }) : null,
    ].filter(Boolean)));

    card.appendChild(el('p', { class: 'ai-lede', text:
      'On ' + plural(d.n_mice || 0, 'mouse', 'mice') + ' it never saw ('
      + num(p.n) + ' candidates), it kept ' + pct(p.ds_kept_frac)
      + ' of the real dentate spikes and caught ' + pct(p.garbage_caught_frac)
      + ' of the garbage. ' + pct(p.flagged_frac) + ' of the candidates '
      + 'would go to a person as flags.' }));
    const bk = res.by_kind || {};
    const more = [];
    if (bk.mixed && bk.mixed.within_auc_median !== null
        && bk.mixed.within_auc_median !== undefined) {
      more.push('Inside a recording that has both, a real spike scores '
                + 'above a piece of garbage ' + pct(bk.mixed.within_auc_median, 0)
                + ' of the time (the median over '
                + plural(bk.mixed.within_auc_n, 'recording') + ').');
    }
    if (bk.all_garbage) {
      more.push('Of the ' + num(bk.all_garbage.n) + ' candidates in '
                + plural(bk.all_garbage.n_recordings, 'recording')
                + ' people rejected whole, it caught '
                + num(bk.all_garbage.garbage_caught) + '.');
    }
    if (more.length) {
      card.appendChild(el('p', { class: 'ai-plain', text: more.join(' ') }));
    }

    card.appendChild(el('div', { class: 'br-counts' }, [
      count(num(p.ds_kept) + ' / ' + num(p.n_ds), 'real DS kept', 'ok'),
      count(num(p.ds_flagged), 'real DS flagged (a person would see them)'),
      count(num(p.garbage_caught) + ' / ' + num(p.n_garbage),
            'garbage caught', 'ok'),
      count(num(p.garbage_through), 'garbage let through as DS',
            p.garbage_through ? 'warn' : ''),
      count(num(p.flagged), 'flagged for a person: '
            + num(p.flag_likely_garbage) + ' likely garbage, '
            + num(p.flag_unsure) + ' unsure'),
    ]));

    const fp = d.first_pass;
    card.appendChild(el('dl', { class: 'br-dl ai-dl' }, [
      dl('Ranking (AUC)', (p.auc === null || p.auc === undefined ? '—'
         : p.auc.toFixed(3)) + '  —  1.0 puts every real DS above every '
         + 'piece of garbage; 0.5 is a coin toss.'),
      dl('Agrees with the settled call', pct(p.agreement)
         + ' of candidates, calling flags garbage.'),
      dl('Calling everything DS', pct(p.baseline_all_ds)
         + '  —  what agreement costs nothing. The model has to beat this '
         + 'on garbage, not on agreement.'),
      dl('As a plain 50/50 classifier', 'accuracy ' + pct((p.at_half || {}).accuracy)
         + ', balanced ' + pct((p.at_half || {}).balanced)),
      fp && fp.called ? dl('A person’s first pass', pct(fp.agree / fp.called)
         + ' matched the settled call, with ' + num(fp.flagged)
         + ' flagged. Often a Toothy-era sort by somebody else, so a '
         + 'reference, not a target.') : null,
      dl('Bar used', 'thresholds ' + (p.thresholds || []).join(', ')
         + ' per fold; ' + (run.model || {}).threshold + ' for the saved model'),
    ].filter(Boolean)));

    const kinds = res.by_kind || null;
    if (kinds) {
      const KIND = {
        mixed: 'Both DS and Garbage',
        all_garbage: 'Rejected whole (all Garbage)',
        all_ds: 'No Garbage at all',
      };
      card.appendChild(el('div', { class: 'section-label', text:
        'Three kinds of recording' }));
      card.appendChild(el('p', { class: 'hint', text:
        'A recording with both labels asks which candidates are garbage. '
        + 'One rejected whole asks whether the recording is any good — a '
        + 'call about all of its candidates at once. They are counted '
        + 'apart because a model can be good at one and not the other.' }));
      card.appendChild(el('div', { class: 'br-scroll' }, [
        el('table', { class: 'br-tbl ai-tbl' }, [
          el('thead', {}, [el('tr', {}, ['Recordings', 'How many',
            'Candidates', 'DS kept', 'Garbage caught', 'Ranking (AUC)',
            'Ranking inside one recording'].map((h) => el('th', { text: h })))]),
          el('tbody', {}, ['mixed', 'all_garbage', 'all_ds']
            .filter((k) => kinds[k]).map((k) => {
              const r = kinds[k];
              return el('tr', {}, [
                el('td', { text: KIND[k] }),
                el('td', { text: num(r.n_recordings) }),
                el('td', { text: num(r.n) }),
                el('td', { text: r.n_ds ? num(r.ds_kept) + ' / '
                                          + num(r.n_ds) : '—' }),
                el('td', { text: r.n_garbage ? num(r.garbage_caught) + ' / '
                                               + num(r.n_garbage) : '—' }),
                el('td', { text: r.auc === null || r.auc === undefined
                                 ? '—' : r.auc.toFixed(3) }),
                el('td', { text: r.within_auc_median === null
                                 || r.within_auc_median === undefined ? '—'
                  : r.within_auc_median.toFixed(3) + ' (median of '
                    + r.within_auc_n + ')' }),
              ]);
            })),
        ])]));
    }

    const catchRows = res.catch || null;
    if (catchRows) {
      card.appendChild(el('div', { class: 'section-label', text:
        'Catching the garbage first' }));
      card.appendChild(el('p', { class: 'hint', text:
        'Each bar is set inside the training mice to flag that share of '
        + 'their garbage, then used on the mice held out. What it costs is '
        + 'the real spikes flagged with it — a person sees them, nothing '
        + 'is lost. 100% in the training mice can still let some through '
        + 'on mice it never saw.' }));
      card.appendChild(el('div', { class: 'br-scroll' }, [
        el('table', { class: 'br-tbl ai-tbl' }, [
          el('thead', {}, [el('tr', {}, ['Asked to catch',
            'Garbage caught', 'Garbage missed', 'Real DS flagged',
            'of all real DS', 'Flagged overall']
            .map((h) => el('th', { text: h })))]),
          el('tbody', {}, catchRows.map((c) => el('tr', {}, [
            el('td', { text: pct(c.target, 0) }),
            el('td', { text: pct(c.garbage_caught_frac) }),
            el('td', { text: num(c.garbage_missed) }),
            el('td', { text: num(c.ds_flagged) }),
            el('td', { text: pct(c.ds_flagged_frac) }),
            el('td', { text: pct(c.flagged_frac) }),
          ]))),
        ])]));
    }

    const trade = res.tradeoff || null;
    if (trade) {
      card.appendChild(el('div', { class: 'section-label', text:
        'The price of keeping spikes' }));
      card.appendChild(el('p', { class: 'hint', text:
        'Each bar is set inside the training mice and tested on the mice '
        + 'held out, as the main one is. Keeping more real spikes means '
        + 'catching less garbage.' }));
      card.appendChild(el('div', { class: 'br-scroll' }, [
        el('table', { class: 'br-tbl ai-tbl' }, [
          el('thead', {}, [el('tr', {}, ['Asked to keep', 'DS kept',
            'Garbage caught', 'in mixed recordings', 'Flagged',
            'Garbage let through'].map((h) => el('th', { text: h })))]),
          el('tbody', {}, trade.map((t) => el('tr', {
            class: Math.abs(t.keep - (s.keep_ds || 0)) < 1e-9 ? 'ai-on' : '',
          }, [
            el('td', { text: pct(t.keep, 0) }),
            el('td', { text: pct(t.ds_kept_frac) }),
            el('td', { text: pct(t.garbage_caught_frac) }),
            el('td', { text: pct(t.garbage_caught_mixed_frac) }),
            el('td', { text: pct(t.flagged_frac) }),
            el('td', { text: num(t.garbage_through) }),
          ]))),
        ])]));
    }

    const leaned = res.leaned_on || [];
    if (leaned.length) {
      const top = Math.max(0.001, ...leaned.map((x) => Math.max(0, x.auc_drop || 0)));
      card.appendChild(el('div', { class: 'section-label', text:
        'What it leaned on' }));
      card.appendChild(el('p', { class: 'hint', text:
        'How far its ranking (AUC) of the held-out mice falls when one kind '
        + 'of input is shuffled. Longer means it depends on it more.' }));
      card.appendChild(el('div', { class: 'ai-bars' }, leaned.map((x) =>
        el('div', { class: 'ai-bar-row' }, [
          el('span', { class: 'ai-bar-name', text: x.name }),
          el('span', { class: 'ai-bar' }, [el('i', { style: 'width:'
            + Math.round(100 * Math.max(0, x.auc_drop || 0) / top) + '%' })]),
          el('span', { class: 'ai-bar-n', text: x.auc_drop === null ? '—'
            : (x.auc_drop >= 0 ? 'falls ' : 'rises ')
              + Math.abs(x.auc_drop).toFixed(3) }),
        ]))));
    }

    card.appendChild(el('div', { class: 'section-label', text:
      'Each held-out group of mice' }));
    card.appendChild(el('div', { class: 'br-scroll' }, [
      el('table', { class: 'br-tbl ai-tbl' }, [
        el('thead', {}, [el('tr', {}, ['Fold', 'Mice', 'Recordings',
          'Candidates', 'DS kept', 'Garbage caught', 'Flagged', 'AUC']
          .map((h) => el('th', { text: h })))]),
        el('tbody', {}, (res.folds || []).map((f) => el('tr', {}, [
          el('td', { text: String(f.fold) }),
          el('td', { class: 'ai-wrap', text: (f.mice || []).join(', ') }),
          el('td', { text: num(f.n_recordings) }),
          el('td', { text: num(f.n) }),
          el('td', { text: num(f.ds_kept) + ' / ' + num(f.n_ds) }),
          el('td', { text: f.n_garbage ? num(f.garbage_caught) + ' / '
                                         + num(f.n_garbage) : '—' }),
          el('td', { text: num(f.flagged) }),
          el('td', { text: f.auc === null || f.auc === undefined ? '—'
                                                    : f.auc.toFixed(3) }),
        ]))),
      ])]));

    card.appendChild(el('div', { class: 'ai-row' }, [
      BARRY.ui.button({ kind: 'mini',
        text: (pick.byRec ? 'Hide' : 'Show') + ' each recording',
        onclick: () => { pick.byRec = !pick.byRec; paintResults(); } }),
    ]));
    if (pick.byRec) {
      card.appendChild(el('div', { class: 'br-scroll' }, [
        el('table', { class: 'br-tbl ai-tbl' }, [
          el('thead', {}, [el('tr', {}, ['Recording', 'Mouse', 'From',
            'Labels', 'Fold', 'DS kept', 'Garbage caught', 'Flagged',
            'Agrees']
            .map((h) => el('th', { text: h })))]),
          el('tbody', {}, (res.by_recording || []).slice()
            .sort((a, b) => a.agreement - b.agreement)
            .map((r) => el('tr', {}, [
              el('td', { class: 'ai-wrap', text: r.label }),
              el('td', { text: r.mouse }),
              el('td', { text: r.source }),
              el('td', { text: ({ mixed: 'both', all_garbage: 'all Garbage',
                                  all_ds: 'all DS' })[r.kind] || '' }),
              el('td', { text: String(r.fold) }),
              el('td', { text: num(r.ds_kept) + ' / ' + num(r.n_ds) }),
              el('td', { text: r.n_garbage ? num(r.garbage_caught) + ' / '
                                             + num(r.n_garbage) : '—' }),
              el('td', { text: num(r.flagged) }),
              el('td', { text: pct(r.agreement, 0) }),
            ]))),
        ])]));
    }

    const notes = [];
    if (d.missed) notes.push(plural(d.missed, 'candidate') + ' could not be '
                             + 'read (past the end, or inside a gap) and '
                             + (d.missed === 1 ? 'was' : 'were')
                             + ' left out.');
    if ((d.failed || []).length) {
      notes.push('Left out: ' + d.failed.map((f) => (f.label || f.entry_id)
                 + ' (' + f.why + ')').join('; ') + '.');
    }
    const clocks = (d.entries || []).map((e) => e.clock).filter(Boolean);
    if (clocks.length) {
      const moved = clocks.filter((c) => Math.abs(c.median_ms) >= 1);
      const big = Math.max(0, ...clocks.map((c) => c.max_abs_ms || 0));
      notes.push('Clock: ' + plural(moved.length, 'recording')
                 + ' needed ' + (moved.length === 1 ? 'its' : 'their')
                 + ' stamps nudged after conversion, by up to '
                 + big.toFixed(0) + ' ms; the rest were already on the '
                 + 'recording’s own clock.');
    }
    const secs = run.seconds || {};
    notes.push('Saved model: ' + ((run.model || {}).file || 'none') + ', '
               + num((run.model || {}).n_features) + ' inputs. Read '
               + Math.round(secs.read || 0) + ' s, trained '
               + Math.round(secs.train || 0) + ' s.');
    card.appendChild(el('div', { class: 'ai-notes' },
                        notes.map((t) => el('p', { class: 'hint', text: t }))));
    return card;
  }

  async function makeToothFairy(id) {
    try {
      await apiPost('/api/aibeta/tooth-fairy', { run_id: id });
    } catch (e) {
      toast(e.message, 'err', 9000);
      return;
    }
    toast('Tooth Fairy now sorts sets with this run.', 'ok', 5000);
    st = null;
    load();
  }

  function count(big, small, kind) {
    return el('div', { class: 'br-count' + (kind ? ' ' + kind : '') }, [
      el('b', { text: big }), el('span', { text: small })]);
  }

  function dl(term, def) {
    return el('div', {}, [el('dt', { text: term }), el('dd', { text: def })]);
  }

  /* ---------- what has been tried ---------- */

  /* The summary report: one section per question, each with the answer
     first and the numbers under it. Every number is what the comparison
     measured on mice the model never saw, filed when it was run -- nothing
     here is recomputed. A cell is tinted by how it compares with the
     reference row (or the reference value of a matrix): green better,
     red worse, by the column's own sense of better. */
  const openReports = new Set();

  function reportCard() {
    const reps = st.reports || [];
    const card = el('div', { class: 'card ai-report' }, [
      el('div', { class: 'ai-row' }, [
        el('strong', { text: 'What has been tried' }),
        el('span', { class: 'hint', text: plural(reps.length, 'question')
          + ' · every number is from mice the model never saw' }),
      ]),
    ]);
    for (const r of reps) card.appendChild(reportSection(r));
    return card;
  }

  function reportSection(r) {
    const open = openReports.has(r.id);
    const sec = el('div', { class: 'ai-rep' + (open ? ' open' : '') });
    sec.appendChild(el('button', {
      class: 'ai-rep-head', 'data-id': r.id,
      onclick: () => {
        if (openReports.has(r.id)) openReports.delete(r.id);
        else openReports.add(r.id);
        sec.replaceWith(reportSection(r));
      },
    }, [
      el('span', { class: 'ai-rep-caret', text: open ? '▾' : '▸' }),
      el('span', { class: 'ai-rep-title', text: r.title || r.id }),
      el('span', { class: 'ai-rep-when', text: when(r.at) }),
    ]));
    if (r.verdict) sec.appendChild(el('p', { class: 'ai-rep-verdict',
                                            text: r.verdict }));
    if (!open) return sec;
    if (r.question) sec.appendChild(el('p', { class: 'hint',
                                             text: r.question }));
    if (r.how) sec.appendChild(el('p', { class: 'hint', text: r.how }));
    for (const t of (r.tables || [])) {
      if (t.title) sec.appendChild(el('div', { class: 'ai-sub',
                                              text: t.title }));
      sec.appendChild(t.kind === 'matrix' ? reportMatrix(t) : reportRows(t));
      if (t.note) sec.appendChild(el('p', { class: 'hint', text: t.note }));
    }
    return sec;
  }

  function fmtCell(v, fmt) {
    if (v === null || v === undefined || !isFinite(v)) return '—';
    if (fmt === 'pct') return (100 * v).toFixed(1) + '%';
    if (fmt === 'auc') return v.toFixed(3);
    if (fmt === 'int') return num(v);
    return String(v);
  }

  /* How much better or worse than the reference, as a tint. Scaled so two
     points of flagged share, or 0.005 of AUC, is a full tint. */
  function tint(v, ref, fmt, better) {
    if (ref === null || ref === undefined || v === null || v === undefined
        || !isFinite(v) || !isFinite(ref) || !better) return null;
    const scale = fmt === 'auc' ? 0.005 : 0.02;
    let d = (v - ref) / scale;
    if (better === 'low') d = -d;
    const a = Math.max(0, Math.min(1, Math.abs(d)));
    if (a < 0.1) return null;
    const tok = d > 0 ? '--ok' : '--err';
    return 'background: color-mix(in srgb, var(' + tok + ') '
      + Math.round(8 + 24 * a) + '%, transparent)';
  }

  function reportRows(t) {
    const cols = t.columns || [];
    const ref = (t.rows || []).find((x) => x.ref);
    const best = {};
    for (const c of cols) {
      if (!c.better) continue;
      const vals = (t.rows || []).map((x) => (x.values || {})[c.key])
        .filter((v) => v !== null && v !== undefined && isFinite(v));
      // A best only where the rows differ: a column of ties has none.
      if (vals.length > 1 && Math.min(...vals) !== Math.max(...vals)) {
        best[c.key] = c.better === 'low' ? Math.min(...vals)
                                         : Math.max(...vals);
      }
    }
    return el('div', { class: 'br-scroll' }, [el('table', {
      class: 'br-tbl ai-tbl ai-rep-tbl' }, [
      el('thead', {}, [el('tr', {}, [el('th', { text: t.row_head || '' })]
        .concat(cols.map((c) => el('th', { text: c.label }))))]),
      el('tbody', {}, (t.rows || []).map((x) => el('tr', {
        class: x.ref ? 'ai-rep-ref' : (x.chosen ? 'ai-rep-chosen' : ''),
      }, [el('td', { class: 'ai-wrap', text: x.label
          + (x.ref ? ' (reference)' : '') + (x.chosen ? ' ← chosen' : '') })]
        .concat(cols.map((c) => {
          const v = (x.values || {})[c.key];
          const isBest = c.key in best && v === best[c.key];
          return el('td', {
            class: 'ai-num' + (isBest ? ' ai-best' : ''),
            style: x.ref || !ref ? null
              : tint(v, (ref.values || {})[c.key], c.fmt, c.better),
            text: fmtCell(v, c.fmt),
          });
        }))))),
    ])]);
  }

  function reportMatrix(t) {
    return el('div', { class: 'br-scroll' }, [el('table', {
      class: 'br-tbl ai-tbl ai-rep-tbl' }, [
      el('thead', {}, [el('tr', {}, [el('th', { text: t.corner || '' })]
        .concat((t.col_labels || []).map((c) => el('th', { text: c }))))]),
      el('tbody', {}, (t.row_labels || []).map((rl, i) => el('tr', {}, [
        el('td', { text: rl })].concat(((t.cells || [])[i] || []).map((v) =>
          el('td', {
            class: 'ai-num',
            style: tint(v, t.ref_value, t.fmt, t.better),
            text: fmtCell(v, t.fmt),
          })))))),
    ])]);
  }

  /* ---------- every run so far ---------- */
  function runsCard() {
    const runs = st.runs || [];
    const card = el('div', { class: 'card ai-runs' }, [
      el('div', { class: 'section-label', text: 'Runs' })]);
    if (!runs.length) {
      card.appendChild(el('p', { class: 'hint',
        text: 'None yet. Each run is kept, with what it learned from and the '
              + 'model it made.' }));
      return card;
    }
    card.appendChild(el('div', { class: 'br-scroll' }, [
      el('table', { class: 'br-tbl ai-tbl' }, [
        el('thead', {}, [el('tr', {}, ['When', 'Model', 'Inputs',
          'Candidates', 'AUC', 'Garbage caught at 98% DS kept',
          'DS flagged to catch 95%', 'to catch 99%']
          .map((h) => el('th', { text: h })))]),
        el('tbody', {}, runs.map((r) => el('tr', {
          class: r.id === shownId ? 'ai-on' : '',
          onclick: () => { openRun(r.id); paintRunsSel(); },
        }, [
          el('td', {}, [el('span', { text: when(r.at) }),
            // Whether the run's record has reached the shared database.
            BARRY.syncState ? BARRY.syncState.mark('aibeta', r.id) : null,
          ].filter(Boolean)),
          el('td', { text: modelName((r.settings || {}).model)
            + (st && st.tooth_fairy && st.tooth_fairy.run_id === r.id
               ? ' · Tooth Fairy' : '') }),
          el('td', { class: 'ai-wrap', text: ((r.settings || {}).families
                                              || []).map(famName).join(', ')
            + ((r.settings || {}).channels === 'even'
               ? ' · even channels only' : '') }),
          el('td', { text: num(r.n_events) }),
          el('td', { text: r.auc === null || r.auc === undefined ? '—'
                                                 : r.auc.toFixed(3) }),
          el('td', { text: pct(r.garbage_caught_frac) }),
          el('td', { text: pct(((r.catch || {})['0.95'] || {}).ds_flagged) }),
          el('td', { text: pct(((r.catch || {})['0.99'] || {}).ds_flagged) }),
        ]))),
      ])]));
    return card;
  }

  function paintRunsSel() {
    const card = document.querySelector('#aiBeta .ai-runs');
    if (!card) return;
    card.replaceWith(runsCard());
  }

  return { paint: paint, reload: () => { st = null; load(); } };
})();
