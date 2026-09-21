/* ==========================================================================
   braces.js -- Braces, step three of The Dentist.

   Braces move teeth into the position they should already have been in.
   This moves stamps, for the same reason: the event is real and correctly
   called, it is just not quite where the record says it is.

   THE SHAPE OF THE PANEL
   Three states, and each one has to finish before the next means anything:

     1. pick a curated dentate-spike set, a channel and a window
     2. look at the proposal -- the counts, the shift histogram, the table
     3. go through the flags on the bench, and accept

   State 2 leads with the HISTOGRAM rather than the table on purpose. "Is
   this the right channel" is a question about the whole set and is answered
   in one glance -- one lobe off zero is a systematic offset and is what this
   tool is for; a flat smear means the channel is wrong and every row in the
   table below it is noise. Asking "is this stamp right" first would have
   somebody review twenty-six flags before finding that out.

   WHY THE BENCH IS NOT THE TRACE VIEW
   Checkup enters the explorer, because deciding whether something is a
   dentate spike means seeing it in context -- the other channels, the
   theta, what happened either side. Alignment is the opposite question: it
   is about one channel over six hundred milliseconds, and everything that
   makes the explorer good at the first question is in the way of the
   second. So the bench is a magnifier drawn here, on the one channel being
   measured, showing exactly what the rule saw.
   ========================================================================== */
'use strict';

BARRY.braces = (function () {
  /* What is being asked for. Held here, not read off the DOM, so a redraw
     cannot lose a half-filled form. */
  const q = {
    entry: null,        // the chosen bank entry id
    from_version: null, // null means "the stamps as they are now"
    channels: null,     // which go into the profile; null = whatever is good
    measure: 'csd',     // 'csd' or 'voltage'
    gid: null,          // the chosen recording
    find: '',           // kept so the harness can still drive the old box
    finding: false,
    window_ms: 100,
    estimator: 'sd',
  };

  let cands = null;     // sets that could be aligned

  /* The bulk queue.

     `pick` is entry id -> the version ref to read from, so changing one
     before the run starts is one assignment. `state` is entry id ->
     {state, msg, set_id} and is the only thing the table's right-hand
     column reads, so a row that failed says why for as long as the panel
     is open. */
  const bulk = {
    on: false, pick: {}, want: {}, state: {},
    running: false, stop: false, now: null,
  };
  let plan = null;      // what a run would read
  let job = null;       // the read, while it is happening
  let set_ = null;      // the proposal being looked at
  let filter = 'flag';  // which rows the table is showing
  let bench = null;     // { row, t, trace } while one is open
  let busy = false;

  const $ = (s) => document.querySelector(s);
  const host = () => document.getElementById('tkResult');

  /* Times are read to the millisecond everywhere in this panel. A stamp is
     a moment, and 27.894 is how everything else in the app spells one. */
  const clock = (t) => (t == null ? '—' : Number(t).toFixed(3));
  const ms = (v) => (v == null ? '—'
    : (v > 0 ? '+' : '') + Number(v).toFixed(1));

  /* ==================================================================
     Loading
     ================================================================== */
  async function paint() {
    render();
    if (!cands) await loadCandidates();
  }

  async function loadCandidates() {
    try {
      const got = await api('/api/braces/candidates');
      cands = got.sets || [];
    } catch (e) {
      toast('Could not read the event bank: ' + e.message, 'err', 8000);
      cands = [];
    }
    if (!q.entry && cands.length) q.entry = cands[0].id;
    render();
    if (q.entry) refreshPlan();
  }

  async function refreshPlan() {
    if (!q.entry) return;
    plan = null;
    render();
    try {
      plan = await apiPost('/api/braces/plan', {
        entry_id: q.entry,
        window_ms: q.window_ms,
        estimator: q.estimator,
      });
    } catch (e) {
      plan = { ok: false, error: e.message };
    }
    render();
  }

  /* ==================================================================
     Running
     ================================================================== */
  async function run() {
    if (!q.entry || job) return;
    let started;
    try {
      started = await apiPost('/api/braces/run', {
        entry_id: q.entry,
        channels: q.channels,
        measure: q.measure,
        from_version: q.from_version,
        window_ms: q.window_ms,
        estimator: q.estimator,
      });
    } catch (e) {
      toast(e.message, 'err', 9000);
      return;
    }
    job = started.job;
    render();
    const poll = setInterval(async () => {
      let got;
      try { got = await api('/api/cfc/job/' + job.id); } catch (e) { return; }
      job = got.job;
      /* The bar only, not the panel.
         A full render empties #tkResult, which takes ToolKit's tool feed
         with it -- and the feed's own observer then mounts a fresh one,
         which is a fetch. At four ticks a second that was fifteen requests
         for /api/toolfeed/braces in half a minute, none of them asked for.
         Nothing on this panel changes while a read is running except how
         far through it is. */
      paintJob();
      if (job.status === 'running') return;
      clearInterval(poll);
      const done = job; job = null;
      if (done.status === 'done') {
        let res;
        try {
          res = (await api('/api/cfc/result/' + done.id)).result;
        } catch (e) {
          toast('The read finished but its result could not be read: '
                + e.message, 'err', 9000);
          render();
          return;
        }
        await openSet(res.set_id);
        return;
      }
      if (done.status !== 'cancelled') {
        toast(done.error || 'The read did not finish.', 'err', 9000);
      }
      render();
    }, 400);
  }

  /* What a job is doing, in words somebody waiting can use.

     A job's snapshot carries `stages` -- each with a name, how many units it
     has and how many are done -- plus an ETA. It has no `frac` and no
     `step`, which is what the first version of this read: the bar never
     moved and the line said "reading the channel" for three minutes while
     sixty-four of them went past. */
  const STAGE_NAMES = {
    'ds depth': 'Finding the depth — stretch',
    'ds windows': 'Reading stretch',
    'ds profile': 'Reading channel',
    'ds detect': 'Finding the peaks',
    'ds read': 'Reading',
  };

  /* What each stage is doing, and why its count is not the number of
     spikes. The second half is the point: a bar counting stretches, on a
     set somebody knows holds twelve hundred spikes, reads as the tool
     having lost most of them. */
  const STAGE_NOTES = {
    'ds depth':
      'The CSD averaged over a sample of these stamps at their curated '
      + 'times, to find the depth the spike sits at. A sample, not all of '
      + 'them — where the sink is is a fact about the probe rather than '
      + 'about any one spike.',
    'ds windows':
      'One read per STRETCH of recording the stamps can reach, not one per '
      + 'spike. Stamps closer together than a second are read as one '
      + 'stretch, which is why this is minutes of an hour rather than the '
      + 'whole hour.',
  };

  function jobSays(j) {
    const stages = (j && j.stages) || [];
    const now = stages.find((x) => x.status === 'running')
             || stages.find((x) => (x.done || 0) < (x.of || 0))
             || stages[stages.length - 1] || {};
    const name = STAGE_NAMES[now.name] || now.name || 'Working';
    const of = now.of || 0;
    const done = Math.min(now.done || 0, of);
    // Counted units where the stage has them -- "channel 12 of 64" is the
    // sentence somebody wants, not a percentage of an unnamed whole.
    const what = of > 1 ? name + ' ' + (done + 1) + ' of ' + of
                        : name + '…';
    let total = 0, spent = 0;
    for (const st of stages) {
      const n = st.of || 1;
      total += n;
      spent += Math.min(st.done || 0, n);
    }
    const eta = (j && j.eta_s) ? spellLeft(j.eta_s) : '';
    /* And the number it is NOT. Named beside the count rather than left to
       be inferred, because the two differ by a factor nobody can guess. */
    let note = STAGE_NOTES[now.name] || '';
    const n = (plan && plan.entry) ? plan.entry.n : null;
    if (note && n) {
      note += '  This set holds ' + n + ' stamp' + (n === 1 ? '' : 's') + '.';
    }
    return { what: what, frac: total ? spent / total : 0, eta: eta,
             note: note, elapsed: (j && j.elapsed) || 0 };
  }

  function spellLeft(sec) {
    const n = Math.round(sec);
    if (n < 45) return 'about ' + Math.max(5, Math.round(n / 5) * 5)
                     + ' seconds left';
    const m = Math.round(n / 60);
    return 'about ' + m + (m === 1 ? ' minute left' : ' minutes left');
  }

  /* Updated in place rather than by re-rendering: a full render empties the
     panel host, which takes ToolKit's tool feed with it, and the feed then
     re-mounts itself -- a request per tick. */
  function paintJob() {
    const host = document.getElementById('brJob');
    if (!host) { render(); return; }
    const say = jobSays(job);
    const bar = host.querySelector('i');
    const step = host.querySelector('.br-job-what');
    const sub = host.querySelector('.br-job-sub');
    // The note changes when the stage does, so it is repainted with
    // everything else rather than written once at the start.
    const note = host.querySelector('.br-job-note');
    if (note) note.textContent = say.note;
    if (bar) bar.style.width = Math.round(say.frac * 100) + '%';
    if (step) step.textContent = say.what;
    if (sub) {
      sub.textContent = [say.eta,
                         say.elapsed > 4
                           ? Math.round(say.elapsed) + 's so far' : '']
        .filter(Boolean).join('  ·  ');
    }
  }

  async function cancel() {
    if (!job) return;
    try { await apiPost('/api/cfc/job/' + job.id + '/cancel', {}); } catch (e) {}
  }

  async function openSet(setId) {
    try {
      set_ = await api('/api/braces/set/' + encodeURIComponent(setId));
    } catch (e) {
      toast('Could not open that alignment: ' + e.message, 'err', 8000);
      return;
    }
    filter = (set_.counts || {}).waiting ? 'flag' : 'all';
    bench = null;
    render();
  }

  /* ==================================================================
     Deciding
     ================================================================== */
  async function decide(n, call, t) {
    if (!set_) return;
    try {
      /* A null call means "forget what was said about this row", and the
         route only reads `call` when it is not null -- so undoing has to go
         through `calls`, where an explicit null is the documented way to
         drop one. Sent as a single-row map rather than a second route. */
      const body = (call == null)
        ? { calls: { [String(n)]: null } }
        : { row: n, call: call, t: t };
      const got = await apiPost(
        '/api/braces/set/' + encodeURIComponent(set_.set.set_id) + '/decide',
        body);
      set_.counts = got.counts;
      set_.would_move = got.would_move;
      set_.set.calls = got.calls;
    } catch (e) {
      toast(e.message, 'err', 8000);
    }
  }

  const callFor = (n) => ((set_.set.calls || {})[String(n)] || {}).call || null;

  /* Which rows the table is showing. `flag` is the pass that matters: the
     ones the tool would not vouch for and nobody has answered yet. */
  function rows() {
    const all = (set_ && set_.set.rows) || [];
    if (filter === 'all') return all.map((r, n) => [r, n]);
    const out = [];
    all.forEach((r, n) => {
      const said = callFor(n);
      if (filter === 'flag' && r.flag && !said) out.push([r, n]);
      else if (filter === 'done' && (said || !r.flag)) out.push([r, n]);
      else if (filter === 'same' && r.same) out.push([r, n]);
      else if (filter === 'nopeak' && r.flag === 'no_peak') out.push([r, n]);
    });
    return out;
  }

  /* ==================================================================
     The page
     ================================================================== */
  function render() {
    const h = host();
    if (!h) return;
    h.innerHTML = '';
    if (set_) { h.appendChild(proposalView()); return; }
    h.appendChild(pickView());
  }

  /* ---------- 1. what to align ---------- */
  function pickView() {
    const box = el('div', { class: 'br-wrap' });

    box.appendChild(el('div', { class: 'card br-intro' }, [
      el('div', { class: 'section-label', style: 'margin-top:0',
                  text: 'Braces · step 3 of The Dentist' }),
      el('p', { class: 'hint', text:
        'Every stamp onto the peak it belongs to. A ±100 ms window, the '
        + 'DS-filtered magnitude, and one peak per stamp — so a spike '
        + 'that drifted early is not corrected by stealing the next '
        + 'one’s. Nothing is written until you accept it.' }),
    ]));

    if (!cands) {
      box.appendChild(el('div', { class: 'card', text: 'Reading the bank…' }));
      return box;
    }
    if (!cands.length) {
      box.appendChild(el('div', { class: 'card br-empty' }, [
        el('strong', { text: 'Nothing to align yet.' }),
        el('p', { class: 'hint', text:
          'Braces works on curated dentate-spike sets. Run Incisor to find '
          + 'the candidates, then go through them in Checkup — moving '
          + 'stamps nobody has vetted is work done twice, because the flags '
          + 'would be about events that get thrown away an hour later.' }),
      ]));
      return box;
    }

    /* One set, or many.

       Two genuinely different jobs rather than two views of one. Choosing
       a set, checking what it would read and running it is a thing you do
       while thinking; aligning everything curated is a thing you set off
       and come back to. The switch is here rather than being a separate
       tool because the sets, the versions and the settings are the same
       in both. */
    box.appendChild(el('div', { class: 'card br-mode' }, [
      el('div', { class: 'seg' }, [
        ['one', 'One set at a time'],
        ['many', 'Many sets at once'],
      ].map(([id, label]) => el('button', {
        class: (bulk.on ? 'many' : 'one') === id ? 'active' : '',
        onclick: () => { if ((bulk.on ? 'many' : 'one') === id) return;
                         bulk.on = id === 'many'; render(); },
        text: label,
      }))),
      el('span', { class: 'br-hint', text: bulk.on
        ? 'Reads them one after another and leaves a proposal for each. '
          + 'Nothing is banked — every set still has to be reviewed.'
        : 'Pick a recording, check what it would read, then run it.' }),
    ]));

    if (bulk.on) {
      box.appendChild(bulkCard());
      box.appendChild(recentSets());
      return box;
    }

    /* Which recording, then which of its banked entries.

       Two questions in that order, because the first narrows the second
       and because it is the order somebody already thinks in: you arrive
       with a recording in mind, not with the name of a banked entry. The
       same two controls the curation wizard uses -- one picker, one radio
       list -- so somebody who has started a curation set already knows how
       to start an alignment.

       Only recordings something is banked against. The registry holds
       every recording this machine has ever opened and Braces can do
       nothing with the ones that have no curated dentate spikes, so
       offering all of them means most picks land on "nothing here", which
       reads as the tool being broken rather than as the recording being
       the wrong one. The registry row is used where there is one, because
       it knows the date and whether the recording can be read from here;
       where there is not -- an entry banked from a recording this machine
       has never opened -- the entry itself supplies enough to pick by. */
    const card = el('div', { class: 'card' });
    const regRows = (BARRY.views.toolkit && BARRY.views.toolkit.registryRows)
      ? BARRY.views.toolkit.registryRows() : [];
    const byGid = new Map();
    for (const r of regRows) byGid.set(r.gid, r);
    const rows = [];
    const seen = new Set();
    for (const c of cands) {
      if (!c.gid || seen.has(c.gid)) continue;
      seen.add(c.gid);
      rows.push(byGid.get(c.gid) || {
        gid: c.gid,
        label: c.session_label || c.name,
        project: c.project, mouse: c.mouse, session: c.session,
        reachable: true,
      });
    }
    rows.sort((x, y) => String(x.label || '').localeCompare(
      String(y.label || '')));

    // Opened on something workable rather than on nothing: the recording
    // of whatever is already chosen, else the first one that has entries.
    if (!q.gid || !seen.has(q.gid)) {
      const on = cands.find((c) => c.id === q.entry);
      q.gid = (on && on.gid) || (rows[0] || {}).gid || null;
    }

    card.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                 text: 'Recording' }));
    card.appendChild(BARRY.pickSession({
      rows,
      value: q.gid,
      placeholder: 'Which recording? Type a mouse, session or date\u2026',
      onpick: (r) => {
        if (r.gid === q.gid) return;
        q.gid = r.gid;
        // A different recording means a different entry. Keeping the old
        // one would leave the panel below describing a set that is no
        // longer among the ones on offer.
        q.entry = null;
        q.channels = null;
        q.from_version = null;
        plan = null;
        render();
      },
    }));

    const mine = cands.filter((c) => c.gid === q.gid);
    if (!mine.length) {
      card.appendChild(el('p', { class: 'confirm-msg', text:
        'Nothing curated is banked against this recording, so there are no '
        + 'stamps to align. Run Incisor to find the candidates and go '
        + 'through them in Checkup first \u2014 moving stamps nobody has '
        + 'vetted is work done twice, because the flags would be about '
        + 'events that get thrown away an hour later.' }));
    } else {
      card.appendChild(el('div', { class: 'section-label',
                                   text: 'Which banked entry' }));
      const list = el('div', { class: 'bm-list' });
      for (const c of mine) {
        list.appendChild(el('label', {
          class: 'bm-row' + (c.id === q.entry ? ' on' : ''),
        }, [
          el('input', {
            type: 'radio', name: 'brEntry',
            checked: c.id === q.entry ? 'checked' : null,
            onchange: () => {
              q.entry = c.id;
              q.channels = null;
              q.from_version = null;
              refreshPlan();
            },
          }),
          el('span', { class: 'mk-name', text: c.name || c.id }),
          el('span', { class: 'flagchip', text: c.n + ' stamps' }),
          el('span', { class: 'person-what',
                       text: vName(c)
                             + (c.aligned ? '  \u00b7 aligned before' : '') }),
        ]));
      }
      card.appendChild(list);
    }

    const cur = cands.find((c) => c.id === q.entry);
    if (cur && cur.aligned) {
      card.appendChild(el('p', { class: 'hint br-warn', text:
        'This set has already been aligned, as version '
        + cur.aligned.version + ' on CSC' + cur.aligned.channel
        + '. Running it again proposes a fresh alignment on top of that '
        + 'one; it does not undo it.' }));
    }
    box.appendChild(card);

    /* What it would read. */
    box.appendChild(planCard());

    /* Settings. */
    const set = el('div', { class: 'card' });
    set.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: 'Settings' }));
    set.appendChild(el('div', { class: 'br-fields' }, [
      el('div', { class: 'br-field' }, [
        el('label', { text: 'Measured on' }),
        el('div', { class: 'seg sm' }, [
          ['csd', 'CSD'],
          ['voltage', 'Voltage'],
        ].map(([id, label]) => el('button', {
          class: q.measure === id ? 'active' : '',
          title: id === 'csd'
            ? 'The current source density across depth — the part of '
              + 'the signal that cannot be volume-conducted'
            : 'The magnitude of the filtered voltage, which is what the '
              + 'detectors these stamps came from were run on',
          onclick: () => { if (q.measure === id) return;
                           q.measure = id; render(); },
          text: label,
        }))),
        el('span', { class: 'br-hint', text: '5–100 Hz either way' }),
      ]),
      field('Window ±ms', el('input', {
        type: 'number', step: '10', min: '5', value: String(q.window_ms),
        onchange: (e) => {
          q.window_ms = Math.max(5, parseFloat(e.target.value) || 100);
          render();
        },
      }), 'how far a stamp may move'),
    ]));
    if (plan && plan.ok) set.appendChild(channelPicker());
    set.appendChild(el('p', { class: 'hint', text:
      (q.measure === 'csd'
        ? 'The CSD is the second derivative across depth, so it is the part '
          + 'of the signal that cannot have come from somewhere else on the '
          + 'probe — a dentate spike is a current sink, and this is '
          + 'where the current went. Smoothed across depth first, or one '
          + 'noisy contact dominates a derivative. '
        : 'The filtered voltage is what Incisor and Toothy were themselves '
          + 'run on, so aligning to it reproduces the detector’s own '
          + 'criterion. ')
      + 'There is no channel to pick. A dentate spike appears across most of '
      + 'the shank at the same instant, so the magnitudes are averaged over '
      + 'every ticked channel into one trace, and the stamp goes to the '
      + 'highest point of THAT inside the window. One noisy wire cannot '
      + 'carry it and a dead one cannot sink it — and nothing is '
      + 'thresholded, because a peak is already the largest thing within a '
      + 'hundred milliseconds of itself.' }));
    box.appendChild(set);

    /* Go. */
    const go = el('div', { class: 'br-go' });
    if (job) {
      const say = jobSays(job);
      go.appendChild(el('div', { class: 'br-job', id: 'brJob' }, [
        el('div', { class: 'br-job-line' }, [
          el('span', { class: 'br-job-what', text: say.what }),
          el('span', { class: 'br-job-sub', text: say.eta }),
        ]),
        el('div', { class: 'br-bar' },
           [el('i', { style: 'width:' + Math.round(say.frac * 100) + '%' })]),
        el('span', { class: 'br-hint br-job-note', text: say.note }),
      ]));
      go.appendChild(el('button', { class: 'btn ghost', text: 'Stop',
                                    onclick: cancel }));
    } else {
      /* Runnable means a readable recording AND a channel. `plan.ok` is
         true while the channel is still missing -- that state is a prompt,
         and a button that offers to start a read it cannot aim is worse
         than one that waits. */
      const ready = !!(plan && plan.ok);
      go.appendChild(el('button', {
        class: 'btn primary', text: 'Line them up',
        disabled: ready ? null : 'disabled',
        title: ready ? '' : 'This set cannot be read here',
        onclick: run,
      }));
    }
    box.appendChild(go);

    box.appendChild(recentSets());
    return box;
  }

  /* Which channels the sweep reads.

     Every one of them, with the ones this recording has marked bad already
     unticked. Not hidden: a sweep that silently leaves eight channels out
     produces a ranking somebody will read as complete, and the one thing
     worse than a bad channel in a table is a good one missing from it with
     nothing to say so. */
  function channelPicker() {
    const all = (plan && plan.channels) || [];
    if (!all.length) return el('span');
    if (q.channels == null) {
      q.channels = all.filter((c) => !c.bad).map((c) => c.number);
    }
    const on = new Set(q.channels);
    const nBad = all.filter((c) => c.bad).length;

    const box = el('div', { class: 'br-chans' });
    box.appendChild(el('div', { class: 'br-chans-head' }, [
      el('label', { text: 'Channels in the average' }),
      el('span', { class: 'br-hint',
                   text: on.size + ' of ' + all.length
                         + (nBad ? '  ·  ' + nBad + ' marked bad, '
                                   + 'unticked' : '') }),
      el('div', { style: 'flex:1' }),
      el('button', { class: 'btn ghost sm', text: 'All',
        onclick: () => { q.channels = all.map((c) => c.number); render(); } }),
      el('button', { class: 'btn ghost sm', text: 'Good ones',
        onclick: () => { q.channels = all.filter((c) => !c.bad)
                                          .map((c) => c.number);
                         render(); } }),
    ]));
    const grid = el('div', { class: 'br-chan-grid' });
    for (const c of all) {
      const id = 'brCh' + c.number;
      grid.appendChild(el('label', {
        class: 'br-chan' + (c.bad ? ' bad' : '') + (on.has(c.number) ? ' on' : ''),
        title: c.bad ? 'Marked bad on this recording' : (c.label || ''),
      }, [
        el('input', {
          type: 'checkbox', id: id,
          checked: on.has(c.number) ? 'checked' : null,
          onchange: (e) => {
            const next = new Set(q.channels);
            if (e.target.checked) next.add(c.number); else next.delete(c.number);
            q.channels = [...next].sort((a2, b2) => a2 - b2);
            render();
          },
        }),
        el('span', { text: String(c.number) }),
      ]));
    }
    box.appendChild(grid);
    return box;
  }

  function field(label, input, hint) {
    return el('div', { class: 'br-field' }, [
      el('label', { text: label }),
      input,
      hint ? el('span', { class: 'br-hint', text: hint }) : null,
    ].filter(Boolean));
  }

  function planCard() {
    const card = el('div', { class: 'card br-plan' });
    card.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                 text: 'What it will read' }));
    if (!plan) {
      card.appendChild(el('p', { class: 'hint', text: 'Working it out…' }));
      return card;
    }
    if (!plan.ok) {
      card.appendChild(el('p', { class: 'br-err', text: plan.error }));
      return card;
    }
    const s = plan.spec || {};
    card.appendChild(el('dl', { class: 'br-dl' }, [
      dt('Recording', (plan.session || {}).name || '—'),
      /* `plan.channel` is null whenever nothing could work one out, which
         is most of this archive -- 41 of 45 sets were banked before Incisor
         existed and say nothing about which channel they came from. That is
         a prompt, not a failure, so the row says so rather than throwing. */
      dt('Measured on', ((q.channels && q.channels.length)
                         || (plan.channels || []).filter((c) => !c.bad).length)
                        + ' channels, averaged into one trace'),
      dt('Band', s.band ? s.band[0] + '–' + s.band[1] + ' Hz, on the '
                          + 'magnitude' : '—'),
      dt('Stamps', plan.entry.n + ' in ' + vName(plan)),
    ].filter(Boolean)));



    /* Which version supplies the stamps. Only where there is a choice --
       a set with one version does not need a dropdown saying so. */
    /* Which version supplies the stamps.

       A list rather than a dropdown, in the same shape the curation version
       chooser uses -- the radio, the version chip, what it did, who and
       when. Not the same FUNCTION: that one is built around a curation
       history, with a bench to restore onto and a mix of labels per
       version, and reshaping this into that contract would be inventing
       fields to satisfy an adapter. The look is what is worth sharing.

       It earns the room. A dropdown shows one line at a time, and the thing
       being chosen between is "which pass of curation" -- which is a
       question about who did what and when, not about a number. */
    const usable = (plan.versions || []).filter((v) => v.usable);
    if (usable.length > 1) {
      const group = 'brver' + Math.random().toString(36).slice(2, 8);
      const list = el('div', { class: 'bm-list ver-pick-list br-vers' });

      const row = (opts) => {
        const r = el('label', {
          class: 'bm-row' + (opts.off ? ' off' : ''),
          title: opts.title || null,
        }, [
          el('input', {
            type: 'radio', name: group,
            disabled: opts.off ? 'disabled' : null,
            checked: opts.on ? 'checked' : null,
            onchange: () => {
              q.from_version = opts.ref;
              // Only the chips that say what is selected need repainting,
              // and a full render would rebuild the radio being clicked.
              for (const n of list.querySelectorAll('.bm-row')) {
                n.classList.toggle('on', n === r);
              }
            },
          }),
          el('span', { class: 'ver-n', text: opts.v }),
          opts.chip ? el('span', { class: 'flagchip', text: opts.chip }) : null,
          el('div', { class: 'ver-pick-mid' }, [
            el('span', { class: 'mk-name', text: opts.what }),
            el('span', { class: 'ver-does' + (opts.branch ? ' branch' : ''),
                         text: opts.does }),
          ]),
          el('span', { class: 'person-what', text: opts.who }),
        ].filter(Boolean));
        if (opts.on) r.classList.add('on');
        return r;
      };

      const tip = usable[usable.length - 1];
      list.appendChild(row({
        ref: null, on: q.from_version == null,
        // The tip's NAME. This row is the entry's current events, which
        // is the newest state there is -- labelling it with the maximum
        // stored NUMBER put "v4" at the top of a list ending in v6 and
        // read as the chooser having defaulted two versions back.
        v: vName(plan),
        chip: 'now',
        what: plan.entry.n + ' stamps, as they stand',
        does: 'the newest there is \u2014 '
              + vName(plan, 'next_name') + ' continues the line',
        who: '',
      }));
      for (const v of usable) {
        list.appendChild(row({
          ref: v.ref,
          on: q.from_version === v.ref,
          v: 'v' + (v.name || v.v),
          chip: v.aligned ? 'aligned' : null,
          what: (v.note || (v.n || 0) + ' stamps').slice(0, 70),
          does: v === tip ? 'the newest of these'
                          : 'branches off it — nothing after it is touched',
          branch: v !== tip,
          who: (v.by || 'unknown')
               + (v.at && BARRY.when ? '  ·  ' + BARRY.when(v.at, 'minute')
                                     : ''),
        }));
      }

      /* The ones that cannot be a starting point, said rather than hidden:
         their counts and their notes are still worth reading, and a version
         that silently is not in the list reads as a version that does not
         exist. */
      for (const v of (plan.versions || []).filter((x) => !x.usable)) {
        list.appendChild(row({
          ref: v.ref, off: true, title: v.why_not,
          v: 'v' + (v.name || v.v),
          what: (v.note || (v.n || 0) + ' stamps').slice(0, 70),
          does: v.why_not || 'cannot be read back',
          who: v.by || '',
        }));
      }

      card.appendChild(el('div', { class: 'br-field br-vers-field' }, [
        el('label', { text: 'Read the stamps from' }),
        list,
      ]));
    }
    return card;
  }

  const dt = (k, v) => el('div', {}, [el('dt', { text: k }),
                                      el('dd', { text: String(v) })]);

  /* What a version is CALLED. Never the stored number: two machines
     curating one entry both mint the next one and the union keeps both,
     so a history can run 0,1,2,3,4,3,4 and the maximum of it is 4 while
     the newest is the seventh. The lineage name is what the list itself
     shows, and it is what every other mention of a version has to show
     or they disagree on screen. The number is the fallback for a payload
     from a server that has not been restarted yet. */
  const vName = (o, key) => 'v' + ((o && o[key || 'current_name'])
                                   != null
                                   ? o[key || 'current_name']
                                   : ((o || {}).current_version));

  /* Which version a bulk run should read, for one entry: the newest there
     is. The lineage's newest -- `versions` arrives in lineage order, so
     the last usable one is it -- and NOT the largest stored number, which
     is a different version on any entry two machines have both curated.
     An entry numbered 0,1,2,3,4,3,4 has a maximum of 4 and a newest of 6. */
  function newestOf(c) {
    const vs = (c.versions || []).filter((v) => v.usable);
    if (!vs.length) return null;
    /* The newest version that can actually be READ here, which the server
       works out and flags.

       Three things it is not. Not the largest stored number: that is not
       unique, so a history running 0,1,2,3,4,3,4 has a largest of 4 and a
       newest of 6. Not the last in the list: the list is in creation
       order, which is lineage order only until something branches. And
       not simply the newest, because a version can arrive as a row
       without its snapshot -- a name, a count and no times -- which is 14
       of the 49 sets in this bank. Falling back through those in the same
       order, for a payload from a server that has not been restarted. */
    return vs.find((v) => v.newest)
        || vs.find((v) => v.name === c.newest_usable_name)
        || vs.find((v) => v.name === c.current_name)
        || vs[vs.length - 1];
  }

  function newestRef(c) {
    const v = newestOf(c);
    return v ? v.ref : null;
  }

  /* Whether this machine could actually read the recording.

     From the registry, joined on the gid. A bulk run of things that cannot
     be opened is forty-eight failures in a row, so "select everything
     ready" means everything reachable -- and a row that is not says so
     rather than being hidden, because the answer to "why is that one not
     ticked" has to be on the screen. */
  function reachable(c) {
    const reg = (BARRY.views.toolkit && BARRY.views.toolkit.registryRows)
      ? BARRY.views.toolkit.registryRows() : [];
    if (!reg.length) return true;      // nothing to judge against
    const row = reg.find((r) => r.gid === c.gid);
    return row ? !!row.reachable : false;
  }

  function bulkReady(c) {
    return reachable(c) && !!newestRef(c);
  }

  /* The counts on the bar, which change as rows are ticked and as a run
     goes. Written in place for the same reason the status cells are: the
     table under them must not move. */
  function paintBulkBar() {
    const host = document.querySelector('.br-bulk-count');
    if (!host) return;
    const n = cands.filter((c) => bulk.want[c.id]).length;
    const ready = cands.filter(bulkReady).length;
    const done = Object.keys(bulk.state)
      .filter((k) => (bulk.state[k] || {}).state === 'done').length;
    host.textContent = n + ' of ' + cands.length + ' ticked \u00b7 ' + ready
      + ' can be read here' + (done ? ' \u00b7 ' + done + ' done' : '');
  }

  function bulkCard() {
    const card = el('div', { class: 'card br-bulk' });
    card.appendChild(el('div', { class: 'br-chans-head' }, [
      el('label', { text: 'Align many sets' }),
      el('span', { class: 'br-hint', text:
        'One read after another, leaving a proposal per entry. Nothing is '
        + 'banked \u2014 every set still has to be reviewed.' }),
    ]));

    const ready = cands.filter(bulkReady);
    const bar = el('div', { class: 'br-bulk-bar' });
    bar.appendChild(el('button', {
      class: 'btn sm', disabled: bulk.running ? 'disabled' : null,
      text: 'Every ready session, newest version',
      title: 'Ticks every set whose recording can be read from this '
           + 'machine, each at the newest version of its stamps',
      onclick: () => {
        for (const c of ready) {
          bulk.want[c.id] = true;
          bulk.pick[c.id] = newestRef(c);
        }
        render();
      },
    }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', disabled: bulk.running ? 'disabled' : null,
      text: 'Clear',
      onclick: () => { bulk.want = {}; render(); },
    }));
    /* And one that leaves alone anything already done.

       "Everything ready" ticks a set that has been aligned as readily as
       one that has not, so a second pass over a bank re-reads the lot.
       This is the button somebody wants on the second run: the ones that
       have never been through. */
    const fresh = ready.filter((c) => !c.aligned);
    bar.appendChild(el('button', {
      class: 'btn sm', disabled: (bulk.running || !fresh.length)
                                 ? 'disabled' : null,
      text: 'Only the ' + fresh.length + ' never aligned',
      title: 'Every ready set that has no alignment banked against it yet, '
           + 'each at its newest version',
      onclick: () => {
        for (const c of fresh) {
          bulk.want[c.id] = true;
          bulk.pick[c.id] = newestRef(c);
        }
        render();
      },
    }));
    const n = cands.filter((c) => bulk.want[c.id]).length;
    bar.appendChild(el('span', { class: 'br-hint br-bulk-count', text:
      n + ' of ' + cands.length + ' ticked \u00b7 ' + ready.length
      + ' can be read here' }));
    bar.appendChild(el('div', { style: 'flex:1' }));
    if (bulk.running) {
      bar.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Stop after this one',
        onclick: () => { bulk.stop = true; render(); },
      }));
    } else {
      bar.appendChild(el('button', {
        class: 'btn primary', disabled: n ? null : 'disabled',
        text: 'Align ' + n + ' set' + (n === 1 ? '' : 's'),
        onclick: runBulk,
      }));
    }
    card.appendChild(bar);

    const tbl = el('div', { class: 'br-bulk-rows' });
    for (const c of cands) {
      const st = bulk.state[c.id] || {};
      const ok = bulkReady(c);
      if (bulk.pick[c.id] === undefined) bulk.pick[c.id] = newestRef(c);
      const vs = (c.versions || []).filter((v) => v.usable);
      tbl.appendChild(el('div', {
        class: 'br-bulk-row' + (bulk.want[c.id] ? ' on' : '')
               + (ok ? '' : ' away') + (st.state ? ' ' + st.state : ''),
        // So a tick can find one row without rebuilding the table.
        'data-id': c.id,
      }, [
        el('input', {
          type: 'checkbox', disabled: (bulk.running || !ok) ? 'disabled' : null,
          checked: bulk.want[c.id] ? 'checked' : null,
          onchange: (e) => {
            if (e.target.checked) bulk.want[c.id] = true;
            else delete bulk.want[c.id];
            render();
          },
        }),
        el('span', { class: 'nm', text: c.name || c.id }),
        el('span', { class: 'ss', text: c.session_label || '\u2014' }),
        el('span', { class: 'ct', text: c.n + ' stamps' }),
        /* The contacts this recording has marked bad, which a bulk run
           uses and could not previously be seen, let alone changed, from
           here. They are interpolated rather than dropped -- a second
           difference over an uneven grid is not a CSD -- so this is
           "which wires are not believed", not "which are missing". */
        el('button', {
          class: 'mini br-bulk-bad' + (badOf(c).length ? ' some' : ''),
          disabled: bulk.running ? 'disabled' : null,
          title: badOf(c).length
            ? 'Interpolated on this recording: CSC'
              + badOf(c).join(', CSC') + '. Click to change.'
            : 'No contact is marked bad on this recording. Click to mark '
              + 'one.',
          text: badOf(c).length ? badOf(c).length + ' bad' : 'none bad',
          onclick: () => editBad(c),
        }),
        /* The version, changeable before anything runs. A short ordered
           list per entry, so a select is the right control here -- unlike
           a list of every recording, which is why that one is typed. */
        vs.length ? el('select', {
          class: 'br-bulk-v',
          disabled: bulk.running ? 'disabled' : null,
          onchange: (e) => { bulk.pick[c.id] = e.target.value || null; },
        }, vs.map((v) => el('option', {
          value: v.ref,
          selected: bulk.pick[c.id] === v.ref ? 'selected' : null,
          text: 'v' + v.name + (v === newestOf(c) ? '  (newest)' : '')
                + (v.n != null ? '  \u00b7 ' + v.n + ' stamps' : ''),
        }))) : el('span', { class: 'br-hint', text: 'no readable version' }),
        /* What it is doing, or why it cannot. The "newest is not
           readable" case is said out loud rather than left as a version
           number somebody would have to notice was one behind. */
        el('span', { class: 'st', text: st.msg
          || (!ok ? 'the recording is not on a drive this machine can reach'
              : (c.newest_usable_name
                 && c.newest_name !== c.newest_usable_name
                 ? 'v' + c.newest_name + ' never reached this machine — '
                   + 'v' + c.newest_usable_name + ' is the newest readable'
                 : '')) }),
        st.set_id ? el('button', {
          class: 'mini', text: 'Open',
          onclick: () => openSet(st.set_id),
        }) : null,
      ].filter(Boolean)));
    }
    card.appendChild(tbl);
    return card;
  }

  /* Which contacts a recording has marked bad.

     Read from the registry rather than from the bank: it is a fact about
     the recording, and the same list every other tool in Jarvis reads. */
  function regRowOf(c) {
    const reg = (BARRY.views.toolkit && BARRY.views.toolkit.registryRows)
      ? BARRY.views.toolkit.registryRows() : [];
    return reg.find((r) => r.gid === c.gid) || null;
  }

  function badOf(c) {
    const row = regRowOf(c) || {};
    const got = row.bad_channels || row.bad || [];
    return got.map(Number).sort((a, b) => a - b);
  }

  /* Where the recording is, on this machine.

     `here` and not `path`: a registry row lists every place it has been
     seen and which of them can be reached from here, and asking for
     `path` returns nothing at all. */
  function pathOf(c) {
    const row = regRowOf(c) || {};
    const here = row.here || [];
    return here.length ? here[0] : null;
  }

  /* Editing them from the bulk table.

     A text field rather than sixty-four tick boxes: the answer is almost
     always one or two numbers somebody already knows, and a grid of
     sixty-four here would be a second channel picker with a different
     shape from the one in the single-set view. */
  function editBad(c) {
    const now = badOf(c).join(', ');
    const input = el('input', {
      type: 'text', value: now, placeholder: 'e.g. 59, 12',
      style: 'width:100%',
    });
    ask('Contacts not to believe on ' + (c.session_label || c.name),
        el('div', {}, [
          el('p', { text:
            'These are interpolated from their neighbours rather than '
            + 'dropped \u2014 a current source density is a difference '
            + 'across depth, and taking a contact out of the middle leaves '
            + 'the rest unevenly spaced, which is not a CSD. A dead wire '
            + 'left in is worse still: a second difference amplifies it, so '
            + 'it becomes the largest thing on the shank.' }),
          el('p', { class: 'hint', text:
            'Braces also screens for dead and railing contacts on every run '
            + 'and reports what it found, so this is for the ones you know '
            + 'about rather than a list you have to keep complete.' }),
          input,
        ]),
        'Save', async () => {
          const want = String(input.value || '')
            .split(/[^0-9]+/).filter(Boolean).map(Number);
          const where = pathOf(c);
          if (!where) {
            toast('That recording is not on a drive this machine can '
                  + 'reach, so its bad contacts cannot be changed here.',
                  'err', 8000);
            return;
          }
          try {
            /* The same route Incisor uses, which takes a PATH: it works
               the mouse and session out from the folder the way the scan
               does, so a contact marked here and one marked in the trace
               view land on one record rather than two. */
            await apiPost('/api/session/bad-for-path', {
              path: where,
              bad_channels: want.sort((a, b) => a - b),
            });
            if (BARRY.views.toolkit && BARRY.views.toolkit.refresh) {
              await BARRY.views.toolkit.refresh();
            }
            toast(want.length
              ? 'CSC' + want.join(', CSC') + ' will be interpolated on '
                + (c.session_label || c.name) + '.'
              : 'Nothing is marked bad on ' + (c.session_label || c.name)
                + ' any more.', null, 6000);
          } catch (e) {
            toast('Could not save that: ' + e.message, 'err', 8000);
          }
          render();
        });
  }

  /* One read after another. */
  async function runBulk() {
    const queue = cands.filter((c) => bulk.want[c.id] && bulkReady(c));
    if (!queue.length || bulk.running) return;
    bulk.running = true;
    bulk.stop = false;
    for (const c of queue) bulk.state[c.id] = { state: 'queued',
                                                msg: 'waiting' };
    render();

    for (const c of queue) {
      if (bulk.stop) {
        bulk.state[c.id] = { state: '', msg: 'stopped before this one' };
        continue;
      }
      bulk.now = c.id;
      bulk.state[c.id] = { state: 'going', msg: 'reading\u2026' };
      paintBulkRow(c.id);
      try {
        const started = await apiPost('/api/braces/run', {
          entry_id: c.id,
          from_version: bulk.pick[c.id] || null,
          measure: q.measure,
          window_ms: q.window_ms,
        });
        const id = (started.job || {}).id;
        if (!id) throw new Error('the read did not start');
        const res = await waitForJob(id, (j) => {
          const st = (j.stages || []).find((x) => x.status === 'running')
                  || (j.stages || [])[0] || {};
          // The same words the single-set bar uses. The raw stage name
          // is `ds windows`, which is the code's name for it and not a
          // thing to put in front of somebody.
          const lbl = STAGE_NAMES[st.name] || st.name || 'Reading';
          bulk.state[c.id] = { state: 'going', msg:
            lbl + ' ' + Math.min((st.done || 0) + 1, st.of || 0)
            + ' of ' + (st.of || 0) };
          paintBulkRow(c.id);
        });
        const summ = res.summary || {};
        bulk.state[c.id] = {
          state: 'done', set_id: res.set_id,
          msg: summ.n + ' aligned, ' + (summ.n_flagged || 0) + ' flagged, '
               + 'median ' + ms(summ.shift_median_ms || 0) + ' ms',
        };
      } catch (e) {
        // Named and kept. A bulk run that swallows one failure is a bulk
        // run somebody has to check by hand afterwards anyway.
        bulk.state[c.id] = { state: 'failed', msg: e.message || String(e) };
      }
      // The row, not the panel: see `paintBulkRow`. The whole thing is
      // rendered once at the end, when nothing is moving.
      paintBulkRow(c.id);
      paintBulkBar();
    }
    bulk.now = null;
    bulk.running = false;
    bulk.stop = false;
    render();
    const done = queue.filter((c) => (bulk.state[c.id] || {}).state === 'done');
    toast(done.length + ' of ' + queue.length + ' aligned. Each is a '
          + 'proposal waiting to be reviewed \u2014 nothing has been banked.',
          done.length === queue.length ? null : 'warn', 9000);
  }

  /* Poll one job to the end. Separate from `run`'s own loop because that
     one repaints the single-set panel as it goes and this one repaints a
     table row. */
  function waitForJob(id, onTick) {
    return new Promise((resolve, reject) => {
      const poll = setInterval(async () => {
        let got;
        try { got = await api('/api/cfc/job/' + id); } catch (e) { return; }
        const j = got.job || {};
        if (j.status === 'running') { if (onTick) onTick(j); return; }
        clearInterval(poll);
        if (j.status !== 'done') {
          reject(new Error(j.error || 'the read did not finish'));
          return;
        }
        try {
          const r = await api('/api/cfc/result/' + id);
          resolve(r.result || {});
        } catch (e) { reject(e); }
      }, 400);
    });
  }

  /* ONE ROW'S STATUS, and nothing else.

     Replacing the card on every tick threw away the scroll position, the
     focus, and any version list somebody had open -- four times a second,
     for the whole minute a read takes, which is exactly when somebody is
     trying to read the table. The status column is the only thing that
     changes while a run is going, so it is the only thing written. */
  function paintBulkRow(id) {
    const row = document.querySelector('.br-bulk-row[data-id="'
                                       + cssEsc(id) + '"]');
    if (!row) return;
    const st = bulk.state[id] || {};
    const cell = row.querySelector('.st');
    if (cell) cell.textContent = st.msg || '';
    for (const k of ['queued', 'going', 'done', 'failed']) {
      row.classList.toggle(k, st.state === k);
    }
  }

  /* Attribute selectors take a quoted value, and a bank id is hex -- but
     it is somebody else's string, so it is escaped rather than trusted. */
  function cssEsc(v) {
    return (window.CSS && CSS.escape) ? CSS.escape(String(v))
                                      : String(v).replace(/["\\]/g, '\\$&');
  }

  function recentSets() {
    const box = el('div', { class: 'card br-recent' });
    box.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: 'Alignments on this machine' }));
    box.appendChild(el('p', { class: 'hint', id: 'brRecent',
                              text: 'Looking…' }));
    api('/api/braces/sets').then((got) => {
      const n = document.getElementById('brRecent');
      if (!n) return;
      const list = got.sets || [];
      if (!list.length) {
        n.textContent = 'None yet. One appears here as soon as you run it, '
                      + 'and stays until you accept it — so reviewing '
                      + 'the flags does not have to happen in one sitting.';
        return;
      }
      const wrap = el('div', { class: 'br-recent-list' });
      for (const s of list.slice(0, 12)) {
        const c = s.counts || {};
        wrap.appendChild(el('button', {
          class: 'br-recent-row' + (s.committed ? ' done' : ''),
          onclick: () => openSet(s.set_id),
        }, [
          el('strong', { text: s.name || s.entry_id }),
          el('span', { text: s.committed
            ? 'accepted as v' + s.committed.version
            : (c.waiting || 0) + ' still to answer · ' + s.n
              + ' stamps' }),
        ]));
      }
      n.replaceWith(wrap);
    }).catch(() => {});
    return box;
  }

  /* ---------- 2. the proposal ---------- */
  /* NOT `setView`. That is core.js's function for changing which view the
     app is showing, and a local one of the same name shadows it for this
     whole module -- so `setView('xplore')` built a proposal panel, threw
     the argument away, and left the app on the ToolKit page. Which is
     exactly what "the main window never changes" looked like. */
  function proposalView() {
    const s = set_.set;
    const sum = s.summary || {};
    const c = set_.counts || {};
    const box = el('div', { class: 'br-wrap' });

    box.appendChild(el('div', { class: 'br-head' }, [
      el('button', { class: 'btn ghost sm', text: '← Back',
                     onclick: () => { set_ = null; bench = null; render(); } }),
      el('div', {}, [
        el('strong', { text: s.name || s.entry_id }),
        el('span', { class: 'br-sub', text:
          ((s.params || {}).n_channels || '?') + ' channels  ·  ±'
          + (s.params || {}).window_ms + ' ms  ·  '
          + ((s.params || {}).band || [5, 100]).join('–') + ' Hz'
          + (s.from_version == null ? '' : '  ·  read from an earlier '
                                           + 'version') }),
      ]),
    ]));

    if (s.committed) {
      box.appendChild(el('div', { class: 'card br-done', text:
        'Accepted as version ' + s.committed.version + ' by '
        + s.committed.by + '. This is the record of how that version was '
        + 'made, so it cannot be changed — run Braces again to propose '
        + 'something different.' }));
    }

    /* What this would do, in one sentence, before any of the numbers.

       The counts, the histogram and the table each answer a different
       question and all three are worth having, but none of them says the
       thing somebody wants first: is this worth banking. Nothing here is
       written until the button at the bottom, and a proposal that opens on
       six panels of statistics does not make that obvious. */
    if (!s.committed) {
      const willMove = set_.would_move || 0;
      const waiting = c.waiting || 0;
      box.appendChild(el('div', { class: 'br-verdict' }, [
        el('strong', { text: willMove
          ? willMove + ' stamp' + (willMove === 1 ? '' : 's') + ' would move'
          : 'Nothing would move' }),
        el('span', { text: willMove
          ? 'by ' + ms(sum.shift_median_ms) + ' ms typically, '
            + (sum.shift_max_ms || 0).toFixed(1) + ' ms at most. '
            + (waiting
                ? waiting + ' need a decision first — look at those '
                  + 'below, then bank it.'
                : 'Look them over below, then bank it.')
          : 'These stamps are already where the recording puts them.' }),
        el('span', { class: 'br-verdict-sub', text:
          'Nothing has been written. The set is still on '
          + vName(set_.entry) + '.' }),
      ]));
    }

    /* The counts. */
    box.appendChild(el('div', { class: 'br-counts' }, [
      count(sum.n, 'dentate spikes'),
      count((c.auto || 0) + (c.confirmed || 0), 'confirmed', 'ok'),
      count(c.waiting || 0, 'need you', (c.waiting ? 'warn' : null)),
      count(sum.n_same || 0, 'already aligned'),
      count(ms(sum.shift_median_ms), 'median Δ'),
      count(sum.shift_max_ms, 'largest move ms'),
    ]));

    /* What was deliberately not touched. Said out loud rather than left to
       be inferred from a count that does not add up: a curated set is not a
       list of events, and the ones somebody rejected are not moved. */
    if (sum.n_skipped) {
      const by = sum.skipped || {};
      const names = (set_.entry || {}).label_names || {};
      const bits = Object.keys(by).map((k) =>
        by[k] + ' ' + (names[k] || k));
      box.appendChild(el('p', { class: 'hint br-note', text:
        'Left alone: ' + bits.join(', ') + '. Braces moves only the stamps '
        + 'somebody called a dentate spike — and they are kept out of '
        + 'the run entirely, so a rejected candidate cannot take the peak a '
        + 'real spike beside it needed.' }));
    }

    /* The histogram, before the table. */
    box.appendChild(histCard(sum));

    if (sum.depth) box.appendChild(depthCard(sum.depth, sum));

    /* What it was measured on. Only worth a line, now that there is no
       channel to second-guess -- but which channels went in, and which were
       left out, is still the difference between a number and a number you
       can act on. */
    if (sum.n_channels) {
      /* DEPTHS, not channels, and the difference is the whole sentence.

         A current source density is a difference ACROSS depth, so a depth
         sits between contacts and the two at the ends of what was read
         have none. Sixteen depths come from eighteen contacts. Calling
         the sixteen "channels" invited the reasonable question of which
         sixteen, and there is no answer because they are not contacts.

         And a screened contact is INTERPOLATED, not left out -- dropping
         one would leave the rest unevenly spaced, which is not a CSD at
         all. It used to say "leaving out CSC59" about a contact that was
         interpolated, at the depth pass, and that is not even in the band
         this was measured on. */
      const band = ((sum.depth || {}).channels) || [];
      const scr = (sum.screened && Object.keys(sum.screened)) || [];
      box.appendChild(el('p', { class: 'hint br-note', text:
        'Averaged over ' + sum.n_channels + ' depth'
        + (sum.n_channels === 1 ? '' : 's')
        + (band.length ? ' across CSC' + band[0] + '–CSC'
                         + band[band.length - 1] : '')
        + ', read from ' + (sum.n_channels + 2) + ' contacts — a depth '
        + 'is a difference between contacts, so the two at each end have '
        + 'none. Each stamp went to the highest point of that average '
        + 'inside its ±' + (s.params || {}).window_ms + ' ms window.'
        + (scr.length
            ? '  CSC' + scr.join(', CSC') + ' '
              + (scr.length === 1 ? 'was' : 'were')
              + ' replaced by the interpolation of '
              + (scr.length === 1 ? 'its' : 'their') + ' neighbours: '
              + scr.map((k) => sum.screened[k]).join('; ') + '.'
            : '')
        + ((sum.skipped_channels || []).length
            ? '  ' + sum.skipped_channels.length + ' could not be read: '
              + sum.skipped_channels.map((x) => 'CSC' + x.number).join(', ')
              + '.'
            : '') }));
    }

    /* Why the rule earned its keep. Only when it actually did. */
    if (sum.greedy_stranded) {
      box.appendChild(el('p', { class: 'hint br-note', text:
        'Nearest-peak-wins would have stranded ' + sum.greedy_stranded
        + ' of these — real stamps left behind because a neighbour '
        + 'took the peak first. Those are the rows flagged '
        + '“not the nearest peak”.' }));
    }

    /* The table. */
    box.appendChild(tableCard(c));

    /* Accept. */
    box.appendChild(acceptBar(c));

    if (bench) box.appendChild(benchCard());
    return box;
  }

  /* Where on the shank these events are.

     The one picture that says whether the measurement is being made in the
     right place. A dentate spike is depth-specific: the profile should rise
     to a peak across the hilus and fall away either side, and a flat one
     means the set is being measured against something that is not a dentate
     spike. No count says that; the shape does. */
  function depthCard(d, sum) {
    const prof = d.profile || [];
    if (!prof.length) return el('span');
    const card = el('div', { class: 'card' });
    const inBand = new Set(d.channels || []);
    const top = Math.max(...prof.map((r) => r.score || 0)) || 1;
    card.appendChild(el('div', { class: 'br-chans-head' }, [
      el('label', { text: 'Where these events are on the shank' }),
      el('span', { class: 'br-hint',
        text: 'averaged over CSC' + (d.channels || [])[0] + '–CSC'
              + (d.channels || [])[(d.channels || []).length - 1]
              + '  ·  ' + (d.channels || []).length + ' of ' + d.of }),
    ]));
    const list = el('div', { class: 'br-depth' });
    for (const r of prof) {
      list.appendChild(el('div', {
        class: 'br-depth-row' + (inBand.has(r.number) ? ' on' : ''),
      }, [
        el('span', { class: 'n', text: 'CSC' + r.number }),
        el('span', { class: 'bar' },
           [el('i', { style: 'width:' + ((r.score / top) * 100) + '%' })]),
        el('span', { class: 'v',
                     text: (100 * (r.score / top)).toFixed(0) + '%' }),
      ]));
    }
    card.appendChild(list);
    const scr = d.screened || {};
    const names = Object.keys(scr);
    if (names.length) {
      card.appendChild(el('p', { class: 'hint', text:
        'Interpolated from their neighbours, not believed: '
        + names.map((n) => 'CSC' + n + ' (' + scr[n] + ')').join(', ')
        + '. A current source density is a second difference across depth, '
        + 'so a dead contact is not merely included in it — it is the '
        + 'largest thing on the shank.' }));
    }
    card.appendChild(el('p', { class: 'hint', text:
      'The CSD averaged over a sample of these stamps at their curated '
      + 'times. A dentate spike is time-locked to them so it adds; the '
      + 'noise and anything a bad wire is doing are not, so they fall away '
      + 'as one over the root of the count. Each bar is how much of that '
      + 'average sits on that contact. A profile that does not rise to a '
      + 'peak and fall away means this set is not what it says it is.' }));
    return card;
  }

  function count(v, label, tone) {
    return el('div', { class: 'br-count' + (tone ? ' ' + tone : '') }, [
      el('b', { text: String(v == null ? '—' : v) }),
      el('span', { text: label }),
    ]);
  }

  function histCard(sum) {
    const card = el('div', { class: 'card' });
    card.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                 text: 'How far they moved' }));
    const hist = sum.hist || [];
    const top = Math.max(1, ...hist);
    const n = hist.length || 1;
    const edge = Math.floor(n * 0.1);
    card.appendChild(el('div', { class: 'br-hist' }, hist.map((v, i) =>
      el('i', {
        class: (i < edge || i >= n - edge) ? 'edge' : '',
        style: 'height:' + Math.max(v ? 2 : 0, (v / top) * 100) + '%',
        title: v + ' stamp' + (v === 1 ? '' : 's'),
      }))));
    card.appendChild(el('div', { class: 'br-axis' }, [
      el('span', { text: String(sum.hist_lo_ms) }),
      el('span', { text: '0' }),
      el('span', { text: '+' + sum.hist_hi_ms + ' ms' }),
    ]));
    card.appendChild(el('p', { class: 'hint', text:
      'One lobe off zero is a systematic offset, which is what this tool is '
      + 'for. A flat smear, or a second lobe against the window edge, means '
      + 'the channel is wrong — go back before accepting anything.' }));
    return card;
  }

  const REASONS = {
    no_peak: 'no peak in reach',
    edge: 'near the edge',
    contested: 'not the nearest peak',
    weak: 'weak peak',
    outlier: 'unlike the others',
  };

  function tableCard(c) {
    const card = el('div', { class: 'card br-table-card' });
    const all = (set_.set.rows || []);
    const pills = [
      ['flag', 'Needs you', c.waiting || 0],
      ['all', 'All', all.length],
      ['done', 'Answered', (c.auto || 0) + (c.confirmed || 0)
                           + (c.kept || 0) + (c.moved || 0)],
      ['same', 'Already aligned', all.filter((r) => r.same).length],
    ];
    card.appendChild(el('div', { class: 'br-pills' }, pills.map(([id, name, n]) =>
      el('button', {
        class: 'pill' + (filter === id ? ' active' : ''),
        onclick: () => { filter = id; render(); },
      }, [el('span', { text: name }), el('span', { class: 'tk-pill-sub',
                                                  text: String(n) })]))));

    const got = rows();
    if (!got.length) {
      card.appendChild(el('p', { class: 'hint', text:
        filter === 'flag'
          ? 'Nothing left to answer. Every flag has a decision on it.'
          : 'Nothing in that pass.' }));
      return card;
    }

    const tb = el('tbody');
    for (const [r, n] of got.slice(0, 400)) {
      const said = callFor(n);
      tb.appendChild(el('tr', {
        class: (r.flag && !said) ? 'flagged' : (said ? 'said' : ''),
        onclick: () => openBench(n),
      }, [
        el('td', { class: 'st', html: said
          ? (said === 'keep' ? '<span class="dim">—</span>'
             : '<span class="tick">✓</span>')
          : (r.flag ? '<span class="flagmark">⚑</span>'
             : '<span class="tick">✓</span>') }),
        el('td', { text: clock(r.was) }),
        el('td', { text: r.peak == null ? 'unmoved' : clock(r.now) }),
        el('td', { text: ms(r.shift_ms) }),
        el('td', { text: r.peak_uv == null ? '—'
                         : String(Math.round(r.peak_uv)) }),
        el('td', { class: 'br-why', text: said
          ? (said === 'keep' ? 'left where it was'
             : said === 'move' ? 'moved by hand' : 'confirmed')
          : (REASONS[r.flag] || '') }),
      ]));
    }
    const tbl = el('table', { class: 'br-tbl' }, [
      el('thead', {}, [el('tr', {}, ['', 'was', 'now', 'Δ ms',
                                     'peak µV', 'why'].map((t) =>
        el('th', { text: t })))]),
      tb,
    ]);
    card.appendChild(el('div', { class: 'br-scroll' }, [tbl]));
    if (got.length > 400) {
      card.appendChild(el('p', { class: 'hint', text:
        'Showing the first 400 of ' + got.length + '.' }));
    }
    return card;
  }

  function acceptBar(c) {
    const s = set_.set;
    const bar = el('div', { class: 'br-accept' });
    if (s.committed) return bar;
    const waiting = c.waiting || 0;
    const nextV = vName(set_.entry, 'next_name');
    bar.appendChild(el('button', {
      class: 'btn primary',
      text: 'Bank it as ' + nextV + '…',
      title: 'Shows exactly what would be written before writing it',
      onclick: () => commit(false),
    }));
    bar.appendChild(el('span', { class: 'hint', text: waiting
      ? waiting + ' flag' + (waiting === 1 ? '' : 's') + ' still unanswered. '
        + 'Those stamps stay exactly where they are — a flag nobody '
        + 'resolved is never moved on the assumption it was probably right.'
      : 'Every flag has been answered.' }));
    bar.appendChild(el('button', {
      class: 'btn sm', text: 'Open on the recording\u2026',
      title: 'The trace view, with every stamp drawn where it was and where '
           + 'it is going \u2014 step through them, move them, decide them',
      onclick: enter,
    }));
    bar.appendChild(el('div', { style: 'flex:1' }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Discard this proposal',
      onclick: discard,
    }));
    return bar;
  }

  /* ==================================================================
     The Braces view

     A mode, the way Checkup is a mode -- not a panel with a trace behind
     it. `setMode` is what makes that true: it puts the app into the mode,
     puts a banner on it, and gives the app one way out that runs `exit`
     however somebody leaves. The first version of this set some marks and
     appended a bar, which is why nothing about it worked like the view it
     was supposed to resemble.

     What it shows that Checkup does not: every stamp TWICE. Where it was,
     muted, and where it is going, in the accent -- so a whole run of them
     reads at a glance, and the one being decided is the one the window is
     centred on.
     ================================================================== */
  let view = null;      // { sess, at, only } while the mode is open

  /* The three marks, in the vocabulary every pane already speaks. */
  const VIEW_LABELS = [
    { id: 'was', name: 'was here', color: '#6f8c7d' },
    { id: 'now', name: 'goes here', color: '#FFB81C' },
    { id: 'ask', name: 'needs you', color: '#ED8B33' },
    { id: 'here', name: 'the one you are on', color: '#7FE3B0' },
  ];

  const vRows = () => (view && set_ && set_.set.rows) || [];
  const vWanted = (r) => (!view || view.only === 'all') ? true : !!r.flag;
  const vAt = () => vRows()[view.at] || null;

  async function enter() {
    const s = set_ && set_.set;
    if (!s) return false;
    const path = set_.session_path;
    if (!path) {
      toast('The recording this set came from is not reachable from this '
            + 'machine, so there is nothing to look at.', 'err', 9000);
      return false;
    }
    // One mode at a time, or two toolbars and two key handlers stack on
    // top of each other. Same note as the top of `curate.enter`.
    if (BARRY.strata && BARRY.strata.active) BARRY.strata.exit();
    if (BARRY.curate && BARRY.curate.active) BARRY.curate.exit();

    /* Every step, recorded. This mode has failed in four different places
       now -- a blocked pop-up, a missing registry entry, a sync that
       deleted its marks, and the layout -- and each time the report was
       that nothing happened, which is the one report nothing can be done
       with. The trail is in the activity log either way. */
    const step = (what, extra) => {
      BARRY.activity.log('braces.enter', Object.assign(
        { set: s.set_id, step: what }, extra || {}));
    };
    step('opening', { path: path });

    /* Dim the workspace for the duration of the arrival. Everything between
       here and `settled` moves the page -- the view swap, the open, the
       banner, the pane rebuild, the jump to the first stamp -- and dimming
       through all of it turns five snaps into one fade. */
    const app = document.getElementById('app');
    if (app) app.classList.add('mode-settling');
    const settled = () => {
      if (!app) return;
      // Two frames: one for the new layout to be in the DOM, one for the
      // browser to have laid it out. Removing the class in the same frame
      // as the last change means the transition has nothing to run from.
      requestAnimationFrame(() => requestAnimationFrame(
        () => app.classList.remove('mode-settling')));
    };

    setView('xplore');
    const sess = await BARRY.views.xplore.open(path);
    if (!sess) {
      step('failed', { why: 'the recording would not open' });
      toast('That recording could not be opened here.', 'err', 8000);
      settled();
      return false;
    }
    step('opened', { view: BARRY.state.view });
    view = { sess: sess, at: 0, rev: 0, curve: curvePref(),
             only: (set_.counts || {}).waiting ? 'flag' : 'all' };
    /* THIS WINDOW OWNS THE MARKS.
       `xplore`'s live loop skips the window that is running a curation and
       calls `adoptCuration` on every other one -- and `adoptCuration` with
       nothing on the channel DELETES `curationMarks`. Without this flag the
       marks were published and then wiped a second later by the sync,
       which is why the trace view never changed. */
    sess.curation = { kind: 'braces', index: 0, set: set_.set };
    setMode('braces', exitView);
    vLayout();
    vGrab();
    step('laid out', { view: BARRY.state.view });

    // Land on something the pass actually contains. Guarded: a throw here
    // used to take the bar and the marks with it and leave the mode half
    // open with no sign of why.
    try {
      const first = vRows().findIndex(vWanted);
      vGoTo(first >= 0 ? first : 0);
    } catch (err) {
      step('failed', { why: String((err && err.message) || err) });
      toast('Braces could not draw on this recording: '
            + ((err && err.message) || err), 'err', 10000);
      settled();
      exitView();
      return false;
    }

    /* The last word on which view is showing.

       `setView` is called at the top, before the recording is opened --
       and something between there and here has been putting the workspace
       back on the ToolKit panel, so the mode ended up running underneath a
       page that was still showing its own summary. Said again, after
       everything else is in place: whatever else happened, this is the view
       the mode is in. */
    if (BARRY.state.view !== 'xplore') {
      step('view bounced', { was: BARRY.state.view });
      setView('xplore');
    }
    settled();
    step('ready', { n: vRows().length, view: BARRY.state.view });
    return true;
  }

  /* The traces get the window, the aids get their own.

     The same arrangement Checkup uses, and for a stronger reason: deciding
     whether a stamp is on the right deflection means looking at the CSD and
     the theta beside it, because a dentate spike has a shape across depth
     and a single trace does not show it. The aid window reads the same
     `sess.curationMarks` this mode publishes, so the old and new positions
     are drawn on all four panels too, not only on the traces.

     Its own window NAME, so it does not fight Checkup for the same one --
     `window.open` reuses a window by name, and two modes sharing a name
     means entering one steals the other's panels. */
  let aidWin = null;

  function vLayout() {
    BARRY.views.xplore.setPanes([{ panel: 'traces' }], { col: 0.5, row: 0.5 });
    if (!vAids()) {
      /* The second window was blocked, and a blocked pop-up is how this
         mode ends up looking like it did nothing at all: the traces open,
         four panels do not, and there is no way to tell that from broken.
         So the aids come into THIS window instead. Cramped, and it says so
         -- but cramped is a thing somebody can work with and absent is
         not. */
      BARRY.views.xplore.setPanes([
        { panel: 'traces' },
        { panel: 'csd' },
        { panel: 'theta' },
        { panel: 'voltage' },
      ], { col: 0.5, row: 0.5 });
      toast('The second window was blocked, so the aid panels are in this '
            + 'one. Allow pop-ups for 127.0.0.1 and re-enter for the '
            + 'roomier layout.', 'warn', 11000);
    }
  }

  /* True when the four aids are up in their own window. False means the
     pop-up was blocked, which the caller turns into an in-window layout
     rather than leaving the mode looking like it did nothing. */
  function vAids() {
    /* Whatever happens below, the next publish sends the marks in full.
       A window that has just been opened, or raised, holds nothing or
       holds something old, and the thinning cannot know which. */
    if (view) { view.sig = null; view.sentAt = 0; }
    if (aidWin && !aidWin.closed) {
      try { aidWin.focus(); } catch (e) { /* not important */ }
      return true;
    }
    const chans = ((view.sess.info || {}).channels || []);
    const every8 = chans.filter((c, i) => i % 8 === 0).map((c) => c.index);
    aidWin = BARRY.views.xplore.popOutPanes(view.sess, [
      { panel: 'csd' },
      { panel: 'theta' },
      { panel: 'voltage' },
      { panel: 'spectrogram', tfChannels: every8, tfMode: 'stack',
        fmin: 1, fmax: 250 },
    ], { role: 'aids', name: 'barry-braces-aids', width: 720, height: 1000,
         // Folded on arrival, as Checkup's are: these four are for glancing
         // at, and the headers and control strips cost more of a short pane
         // than they are worth.
         chrome: 'notabs,noheads,nostrip,nochannels' });
    return !!aidWin;
  }

  function exitView() {
    if (!view) return;
    if (aidWin && !aidWin.closed) {
      try { aidWin.close(); } catch (e) { /* it may already be gone */ }
    }
    aidWin = null;
    if (BARRY.views.xplore.grabTime) BARRY.views.xplore.grabTime(null);
    if (view.sess) {
      delete view.sess.curation;
      delete view.sess.curationMarks;
      // Tell the other window the mode is over, or it keeps drawing marks
      // for a proposal nobody is looking at any more.
      if (BARRY.views.xplore.publishCuration) {
        BARRY.views.xplore.publishCuration(view.sess, null);
      }
    }
    if (BARRY.views.xplore.redraw) BARRY.views.xplore.redraw();
    view = null;
    const app = document.getElementById('app');
    if (app) app.classList.remove('mode-settling');
    const bar = document.getElementById('brViewBar');
    if (bar) bar.remove();
    // And the list, which is a modal and outlives the mode otherwise --
    // a dialog of somebody else's stamps over the next view.
    if (view.list) { view.list = false; closeModal(); }
    document.removeEventListener('keydown', vKeys, true);
    setMode(null);
    setView('toolkit');
  }

  /* Every stamp, twice.

     `curationMarks` is the shape every pane, the overview strip and the
     pop-out aid window read, so this draws everywhere without a second
     drawing path. The one being decided gets its own colour rather than
     only being centred: centred is a fact about the window, and panning
     away should not lose which one you were on. */
  /* The curve, for the stamp in focus.

     Fetched once per stamp and carried on the marks, so every pane and
     every pop-out draws the same samples -- and so that a window with no
     proposal in it can draw it at all. Three windows wide, which is what
     the bench asks for: enough either side to see that the maximum picked
     is the maximum there is.

     `seq` guards the order. Stepping faster than the reads come back
     otherwise leaves whichever request finished last on screen, which is
     not necessarily the stamp anybody is looking at. */
  let curveSeq = 0;

  /* Whether the curve is drawn, remembered between sessions.

     It is a way of working rather than a property of a set: somebody who
     wants to see what the rule looked at wants that on every stamp of
     every alignment, and somebody who finds it busy wants it gone for
     good. On by default, because it is the only thing on screen that says
     why the green line is where it is. */
  const CURVE_KEY = 'braces_curve';

  function curvePref() {
    try {
      return BARRY.prefs.get(CURVE_KEY, true) !== false;
    } catch (e) { return true; }
  }

  function setCurvePref(on) {
    try { BARRY.prefs.set(CURVE_KEY, !!on); } catch (e) { /* ignore */ }
  }

  async function loadCurve() {
    if (!view || !view.curve) return;
    const s = set_.set;
    const r = vAt();
    if (!r) return;
    /* The reach exactly. A stamp may move within the window and nowhere
       else, so a sample outside it is not a candidate and cannot be the
       answer -- drawing three windows of curve put two thirds of a
       picture on screen that no decision could ever be taken from, and
       read as though the rule had considered it. */
    const span = ((s.params || {}).window_ms || 100) / 1000;
    const mine = ++curveSeq;
    try {
      const got = await apiPost(
        '/api/braces/set/' + encodeURIComponent(s.set_id) + '/profile',
        { t0: r.was - span, t1: r.was + span });
      if (!view || !view.curve || mine !== curveSeq) return;
      view.trace = got;
      vPublish();
    } catch (e) {
      if (view && mine === curveSeq) { view.trace = null; vPublish(); }
    }
  }

  /* Weights for the signature, one per state a dashed mark can be in.
     Small, distinct, and not multiples of one another, so no combination
     of them adds up to another -- a signature that collides is a change
     that never leaves this window. */
  const ST_W = { open: 0, flagged: 0.0031, confirmed: 0.0057, kept: 0.0083 };

  function vPublish(opts) {
    if (!view) return;
    // `local` draws here and tells nobody: dragging repaints far
    // faster than anything should be published at.
    const quiet = !!(opts && opts.local);
    const s = set_.set;
    const cur = vAt();
    const evs = [];
    vRows().forEach((r, i) => {
      if (view.only === 'flag' && !r.flag && r !== cur) return;
      const mine = r === cur;
      const said = callFor(i);
      // What the dashed half says: answered, still being asked about, or
      // nobody has looked.
      const st = (said === 'confirm' || said === 'move') ? 'confirmed'
        : (said === 'keep' ? 'kept'
           : (r.flag ? 'flagged' : 'open'));
      const to = vNow(r);
      // `r` is the row this mark belongs to. Carried so that a window
      // holding these marks can be told "the focus is now row 412" and
      // work out its own `f` flags, instead of being sent every mark
      // again to learn one number.
      if (Math.abs(to - r.was) < 1e-9) {
        // It is not going anywhere, so one mark, not two on top of
        // each other.
        evs.push({ start: r.was, k: 'now', st: st, f: mine ? 1 : 0, r: i });
        return;
      }
      evs.push({ start: r.was, k: 'was', st: st, f: mine ? 1 : 0, r: i });
      evs.push({ start: to, k: 'now', st: st, f: mine ? 1 : 0, r: i });
    });
    evs.sort((a, b) => a.start - b.start);
    view.sess.curationMarks = {
      kind: 'braces',
      // How far a stamp was allowed to move. Carried, because the painter
      // runs in the aid window too and there is no proposal loaded there.
      window_ms: (s.params || {}).window_ms || 100,
      index: view.at,
      at: cur ? vNow(cur) : null,
      labels: VIEW_LABELS,
      events: evs,
      // Where the window is centred, as a time.
      //
      // Not "find the mark with the focus flag on it". That worked until a
      // pointer went astray, and then the reach silently stopped being
      // drawn -- which is a thing nobody can report as a bug because the
      // absence of a shaded region looks like a view with no region in it.
      home_t: cur ? cur.was : null,
      // What the rule looked at, if it has been asked for. One window's
      // worth of samples, which is small enough to travel with the marks
      // and is the only way the aid windows can draw it.
      curve: (view.curve && view.trace) ? view.trace : null,
      gid: s.gid,
    };
    if (view.sess.curation) view.sess.curation.index = view.at;
    if (BARRY.views.xplore.redraw) BARRY.views.xplore.redraw();

    /* And to the aid window, which is a separate page with no braces module
       in it. The marks travel WITH the pointer rather than being fetched,
       because there is no route that serves them -- see the note beside
       `adoptCuration`. */
    view.rev = (view.rev || 0) + 1;
    if (!quiet && BARRY.views.xplore.publishCuration) {
      /* The marks themselves only when they have actually changed.
         Stepping through a set of twelve hundred publishes twenty-four
         hundred marks on every arrow key otherwise -- and the receiving
         side already knows how to follow a pointer without them, as long
         as the count still matches what it holds. A float sum of the times
         is enough to tell a move from a step: it changes when any mark
         moves and not when only the cursor does. */
      /* Everything about the marks EXCEPT which one is in focus.

         The focus changes on every step and the marks do not, so folding
         it in here would send twenty-four hundred objects through the
         live slot on every arrow key -- which is the thing this exists to
         prevent. It travels as a number instead, below, and the flags are
         recomputed where they are drawn.

         The sum has to move when a stamp moves AND when a decision is
         made, because both change what is drawn: `k` says whether a mark
         is the old position or the new one, and `st` says what colour the
         dashed half is. Two offsets too small to collide with a time in
         seconds, added per mark, do that without building a string per
         publish. */
      let sum = 0;
      for (const e of evs) {
        sum += e.start + (e.k === 'now' ? 0.017 : 0) + (ST_W[e.st] || 0);
      }
      /* Thinned, but never for long.

         A window that opens between two marks-carrying pointers would
         otherwise wait for somebody to MOVE something before it had any
         marks to draw -- there is no route it can ask, which is the whole
         reason these travel on the pointer. So the full set goes out
         again if it has not for a second and a half, whatever the
         signature says. On a set of twelve hundred that is one extra send
         per second and a half of continuous stepping, which is nothing
         beside being the only thing that can fill a new window. */
      const now = Date.now();
      const stale = !view.sentAt || (now - view.sentAt) > 1500;
      const sig = evs.length + ':' + view.only + ':' + sum.toFixed(4);
      const same = sig === view.sig && !stale;
      view.sig = sig;
      if (!same) view.sentAt = now;
      BARRY.views.xplore.publishCuration(view.sess, Object.assign({
        gid: s.gid, kind: 'braces', index: view.at,
        at: view.sess.curationMarks.at,
        // Which row is in focus, and how far it was allowed to move.
        // Both are read by the painter and neither is on the marks, so
        // both have to travel with every pointer -- a window that adopted
        // its marks an hour ago still has to draw the right reach around
        // the right stamp.
        focus: view.at,
        window_ms: view.sess.curationMarks.window_ms,
        n: evs.length, rev: view.rev,
        // Sent whenever it changes, which is once per stamp rather than
        // once per keystroke: `curveAt` is the stamp it was read for.
        curve: (view.curve && view.trace) ? view.trace : null,
        curveAt: view.curve ? view.at : null,
        home_t: cur ? cur.was : null,
      }, same ? {} : { labels: VIEW_LABELS, events: evs }));
    }
  }

  /* Where a row is going, including anywhere somebody has moved it by
     hand -- the decision outranks the proposal. */
  function vNow(r) {
    const n = vRows().indexOf(r);
    // A drag in flight outranks both: the line has to follow the pointer
    // now, not after a round trip.
    if (view && view.drag && view.drag.row === n) return view.drag.t;
    const said = ((set_.set.calls || {})[String(n)] || {});
    if (said.call === 'move' && said.t != null) return said.t;
    if (said.call === 'keep') return r.was;
    return r.now == null ? r.was : r.now;
  }

  function vGoTo(n) {
    const all = vRows();
    if (!all.length || !view) return;
    view.at = Math.max(0, Math.min(all.length - 1, n));
    /* THEN the curve, not before: `loadCurve` reads `view.at`, and asking
       for it up here fetched the stamp we were leaving. The samples came
       back for the wrong window, were clipped to the reach around the new
       one, and drew nothing -- which is why the curve appeared only after
       being toggled off and on, the one path that asked again from a
       settled `view.at`. Cleared first so a stale one is never drawn under
       a different stamp's marks even for a frame. */
    if (view.curve) { view.trace = null; loadCurve(); }
    const r = all[view.at];
    // Eight windows across, so the neighbours that made a run contested
    // are on screen beside it rather than just off the edge.
    const span = Math.max(0.4,
                          ((set_.set.params || {}).window_ms || 100) / 1000 * 8);
    BARRY.views.xplore.setWindow(0, Math.max(0, vNow(r) - span / 2), span);
    vPublish();
    vBar();
  }

  function vStep(d) {
    const all = vRows();
    let i = view.at + d;
    while (i >= 0 && i < all.length) {
      if (vWanted(all[i])) { vGoTo(i); return; }
      i += d;
    }
    toast(d > 0 ? 'That is the last one in this pass.'
                : 'That is the first one in this pass.', null, 3500);
  }

  /* Moving one by hand. The marks repaint as it goes, so the line you are
     dragging is the line you are looking at. */
  async function vMove(deltaMs) {
    const r = vAt();
    if (!r) return;
    const t = Math.round((vNow(r) + deltaMs / 1000) * 1e6) / 1e6;
    await decide(view.at, 'move', t);
    vPublish();
    vBar();
  }

  async function vSay(call) {
    const r = vAt();
    if (!r) return;
    await decide(view.at, call);
    vPublish();
    // Straight on to the next one that still wants an answer, which is what
    // makes a pass a pass rather than a list.
    const all = vRows();
    for (let i = view.at + 1; i < all.length; i++) {
      if (all[i].flag && !callFor(i)) { vGoTo(i); return; }
    }
    vBar();
  }

  /* Dragging a stamp onto its peak.

     `xplore` hands the time under the pointer; everything else is this
     module's. Three rules:

       the line follows the pointer immediately, locally, because a line
       that lags the mouse is worse than no line;

       the other windows follow on a throttle, because the marks are the
       payload and twelve hundred stamps is twenty-four hundred of them --
       at sixty moves a second that is a megabyte of publishing for a
       gesture that lasts half of one;

       nothing is decided until the button comes up. A drag that is still
       happening is not an answer.

     Only the stamp being looked at can be dragged. Grabbing whichever mark
     is nearest the pointer would let a twitch move a stamp three screens
     from the one being decided, and there would be nothing on screen to say
     which. */
  const DRAG_PUBLISH_MS = 120;

  function vGrab() {
    if (!BARRY.views.xplore.grabTime) return;
    BARRY.views.xplore.grabTime({
      onStart: (t) => {
        const r = vAt();
        if (!r) return false;
        // Within a window of the one being decided, or it is somebody
        // panning rather than aiming.
        const reach = ((set_.set.params || {}).window_ms || 100) / 1000;
        if (Math.abs(t - vNow(r)) > reach) return false;
        view.drag = { row: view.at, t: vNow(r), last: 0 };
        return true;
      },
      onMove: (t) => {
        if (!view || !view.drag) return;
        view.drag.t = Math.round(t * 1e6) / 1e6;
        vPublish({ local: true });
        vBarTimes();
        const now = Date.now();
        if (now - view.drag.last > DRAG_PUBLISH_MS) {
          view.drag.last = now;
          vPublish();
        }
      },
      onEnd: async (t) => {
        if (!view || !view.drag) return;
        const row = view.drag.row;
        const at = Math.round(t * 1e6) / 1e6;
        view.drag = null;
        await decide(row, 'move', at);
        vPublish();
        vBar();
      },
    });
  }

  /* The two numbers in the bar, without rebuilding it. Dragging repaints
     these forty times a second and a full rebuild would take the focus off
     whatever has it. */
  function vBarTimes() {
    const r = vAt();
    if (!r) return;
    const sub = document.querySelector('#brViewBar .cur-sub');
    if (sub) {
      sub.textContent = clock(r.was) + '  \u2192  ' + clock(vNow(r))
        + '   ' + ms((vNow(r) - r.was) * 1000) + ' ms'
        + (r.flag ? '   \u00b7   ' + (REASONS[r.flag] || r.flag) : '');
    }
  }

  /* Forget what was decided about the one in view. Through the same route
     as every other decision -- an explicit null on that row -- so the
     server, this window and the aid window all learn about it the way they
     learned about the decision. */
  async function vUndo() {
    if (!view || !callFor(view.at)) return;
    await decide(view.at, null);
    vPublish();
    vBar();
  }

  async function vUndoAll() {
    if (!view || !set_) return;
    const keys = Object.keys(set_.set.calls || {});
    if (!keys.length) {
      toast('Nothing has been decided yet.', null, 3500);
      return;
    }
    const ok = await BARRY.confirm(
      'Forget all ' + keys.length + ' decision'
      + (keys.length === 1 ? '' : 's') + ' on this proposal?',
      'The proposal itself is untouched \u2014 this clears only what has '
      + 'been said about it, so the pass starts again. Nothing has been '
      + 'written to the set either way.',
      'Forget them');
    if (!ok) return;
    const patch = {};
    for (const k of keys) patch[k] = null;
    try {
      const got = await apiPost(
        '/api/braces/set/' + encodeURIComponent(set_.set.set_id) + '/decide',
        { calls: patch });
      set_.counts = got.counts;
      set_.would_move = got.would_move;
      set_.set.calls = got.calls;
    } catch (e) {
      toast(e.message, 'err', 8000);
      return;
    }
    vPublish();
    vBar();
  }

  /* The set as a list, in the dialog Checkup uses.

     Not a panel of its own. The classes are shared rather than copied, so
     the two look identical because they are the same markup -- and
     somebody who has been through a curation set already knows how to
     read this one. What differs is what a row can be sorted and filtered
     by, because an alignment's categories are not a curation's: not which
     label, but whether it moves, whether it was flagged, and whether
     anybody has answered.

     Rendered whole rather than windowed: twelve hundred rows of five
     spans is well inside what a browser draws without complaint, and
     virtualising it would mean keeping the scroll position and the focus
     in step by hand. */
  const listQ = { by: 'time', text: '', only: 'all' };

  function vList() {
    if (!view || !set_) return;
    // The toggle turns it off by calling this, which is the one place that
    // knows the dialog is a modal rather than a panel to remove.
    if (!view.list) { closeModal(); return; }
    const all = vRows();
    const rows = all.map((r, i) => ({ r: r, i: i }));

    const shiftOf = (x) => (vNow(x.r) - x.r.was) * 1000;
    const saidOf = (x) => callFor(x.i);
    const stateOf = (x) => {
      const said = saidOf(x);
      if (said === 'move') return 'moved';
      if (said === 'confirm') return 'confirmed';
      if (said === 'keep') return 'kept';
      return x.r.flag ? 'flagged' : 'auto';
    };
    const STATE_NAME = {
      moved: 'moved by hand', confirmed: 'confirmed', kept: 'left alone',
      flagged: 'needs a decision', auto: 'moving, unflagged',
    };
    const STATE_COLOUR = {
      moved: '#5cc98d', confirmed: '#5cc98d', kept: '#ED8B33',
      flagged: '#ED8B33', auto: 'var(--line)',
    };

    const tally = {};
    for (const x of rows) {
      const k = stateOf(x);
      tally[k] = (tally[k] || 0) + 1;
    }

    const wrap = el('div', { class: 'modal cur-list-modal' });
    wrap.appendChild(el('div', { class: 'modal-head' }, [
      el('h2', { text: 'Every stamp in this alignment' }),
      el('p', { class: 'sub',
                text: rows.length + ' stamps  \u00b7  '
                    + ((set_.counts || {}).waiting || 0)
                    + ' still to answer  \u00b7  '
                    + (set_.set.name || '') }),
    ]));

    const rowsHost = el('div', { class: 'cur-list' });

    const controls = el('div', { class: 'cur-list-bar' }, [
      el('div', { class: 'seg sm' }, [
        ['time', 'By time'],
        ['move', 'By how far it moves'],
      ].map(([id, label]) => el('button', {
        class: listQ.by === id ? 'active' : '', text: label,
        onclick: (ev) => {
          listQ.by = id;
          Array.from(ev.target.parentNode.children).forEach(
            (b) => b.classList.toggle('active', b === ev.target));
          paint();
        },
      }))),
      el('input', {
        type: 'search', class: 'cur-list-search', value: listQ.text,
        placeholder: 'Find a time, a distance, a reason\u2026',
        oninput: (e) => { listQ.text = e.target.value; paint(); },
      }),
      el('span', { class: 'hint', id: 'brListCount' }),
    ]);

    const chips = el('div', { class: 'res-toolbar cur-list-chips' });
    const chip = (id, label, n) => el('button', {
      class: 'pill' + (listQ.only === id ? ' active' : ''),
      disabled: (!n && id !== 'all') ? 'disabled' : null,
      text: label + ' (' + n + ')',
      onclick: () => {
        listQ.only = id;
        Array.from(chips.children).forEach(
          (b) => b.classList && b.classList.toggle(
            'active', b.textContent.indexOf(label + ' (') === 0));
        paint();
      },
    });
    chips.appendChild(chip('all', 'All', rows.length));
    for (const id of ['flagged', 'auto', 'confirmed', 'moved', 'kept']) {
      chips.appendChild(chip(id, STATE_NAME[id], tally[id] || 0));
    }

    function matching() {
      const q = listQ.text.trim().toLowerCase();
      const out = [];
      for (const x of rows) {
        const st = stateOf(x);
        if (listQ.only !== 'all' && st !== listQ.only) continue;
        if (q) {
          const hay = [clock(x.r.was), x.r.was.toFixed(3),
                       ms(shiftOf(x)) + ' ms', STATE_NAME[st],
                       x.r.flag ? (REASONS[x.r.flag] || x.r.flag) : '']
            .filter(Boolean).join(' ').toLowerCase();
          if (hay.indexOf(q) < 0) continue;
        }
        out.push(x);
      }
      if (listQ.by === 'move') {
        // Furthest first: the ones worth a second look are the ones that
        // moved most, and reading down from the top is the review.
        out.sort((a, b) => Math.abs(shiftOf(b)) - Math.abs(shiftOf(a)));
      }
      return out;
    }

    function rowFor(x) {
      const st = stateOf(x);
      const d = shiftOf(x);
      return el('div', {
        class: 'cur-list-row' + (x.i === view.at ? ' here' : '')
             + (st === 'flagged' ? ' undecided' : ''),
        style: '--cat:' + STATE_COLOUR[st],
        title: x.r.flag ? (REASONS[x.r.flag] || x.r.flag)
                        : 'Nothing was flagged about this one',
        onclick: () => { closeModal(); view.list = false; vGoTo(x.i); },
      }, [
        el('span', { class: 'cl-n', text: '#' + (x.i + 1) }),
        el('span', { class: 'cl-t', text: clock(x.r.was) }),
        el('span', { class: 'cl-move', text: ms(d) + ' ms' }),
        el('span', { class: 'cl-lab', text: STATE_NAME[st] }),
        el('span', { class: 'cl-who',
                     text: x.r.flag ? (REASONS[x.r.flag] || x.r.flag) : '' }),
        x.i === view.at ? el('span', { class: 'pill sm', text: 'here' })
                        : null,
      ].filter(Boolean));
    }

    function paint() {
      rowsHost.innerHTML = '';
      const got = matching();
      const count = document.getElementById('brListCount');
      if (count) {
        count.textContent = got.length === rows.length
          ? got.length + ' stamps'
          : got.length + ' of ' + rows.length;
      }
      if (!got.length) {
        rowsHost.appendChild(el('div', { class: 'hint',
          text: 'Nothing matches that.' }));
        return;
      }
      /* By time, with a marker wherever the stamps thin out -- a gap of a
         minute is a fact about the recording, and the same marker Checkup
         puts in for the same reason. */
      let last = null;
      for (const x of got) {
        if (listQ.by === 'time' && last !== null && x.r.was - last > 30) {
          rowsHost.appendChild(el('div', { class: 'cl-gap',
            text: '\u2026 ' + Math.round(x.r.was - last)
                + 's with no stamps \u2026' }));
        }
        rowsHost.appendChild(rowFor(x));
        last = x.r.was;
      }
      const on = rowsHost.querySelector('.cur-list-row.here');
      if (on && on.scrollIntoView) on.scrollIntoView({ block: 'nearest' });
    }

    wrap.appendChild(controls);
    wrap.appendChild(chips);
    wrap.appendChild(rowsHost);
    wrap.appendChild(el('div', { class: 'modal-foot' }, [
      el('div', { style: 'flex:1' }),
      el('button', { class: 'btn', text: 'Close',
                     onclick: () => { view.list = false; closeModal();
                                      vBar(); } }),
    ]));
    paint();
    showModal(wrap, { replace: true });
  }

  function vBar() {
    if (!view) return;
    let bar = document.getElementById('brViewBar');
    if (!bar) {
      bar = el('div', { class: 'cur-bar br-view-bar', id: 'brViewBar' });
      const body = document.getElementById('xfBody');
      (body || document.body).appendChild(bar);
      document.addEventListener('keydown', vKeys, true);
    }
    bar.innerHTML = '';
    const s = set_.set;
    const all = vRows();
    const r = vAt() || {};
    const said = callFor(view.at);
    const n = all.filter(vWanted).length;
    const seen = all.slice(0, view.at + 1).filter(vWanted).length;
    const left = (set_.counts || {}).waiting || 0;

    bar.appendChild(el('div', { class: 'cur-where' }, [
      el('strong', { text: s.name || 'Braces' }),
      el('span', { class: 'cur-sub', text:
        clock(r.was) + '  →  ' + clock(vNow(r))
        + '   ' + ms((vNow(r) - r.was) * 1000) + ' ms'
        + (r.flag ? '   ·   ' + (REASONS[r.flag] || r.flag) : '') }),
      el('span', { class: 'cur-count', text: seen + ' / ' + n }),
    ]));

    bar.appendChild(el('div', { class: 'cur-prog' }, [
      el('i', { style: 'width:' + (n ? (seen / n * 100) : 0) + '%' }),
      el('span', { text: left + ' still to decide' }),
    ]));

    /* Two answers to one question: does this stamp move, or not.

       They were "Confirm" and "Keep it", which say what the BUTTON does and
       not what happens to the stamp -- and "keep it" reads as "keep the new
       one" at least as readily as "keep the old one". Each now names the
       time it lands on, so there is nothing left to infer. */
    const moves = Math.abs(vNow(r) - r.was) > 1e-9;
    const acts = el('div', { class: 'cur-cats br-acts' });
    acts.appendChild(el('button', {
      class: 'cur-cat' + (said === 'confirm' || said === 'move' ? ' on' : ''),
      style: '--cat:#5cc98d',
      title: 'Move the stamp to ' + clock(vNow(r)) + '   (Enter)',
      onclick: () => vSay('confirm'),
    }, [
      el('kbd', { text: '\u21b5' }),
      el('span', {}, [
        el('b', { text: moves ? 'Move it' : 'It is right' }),
        el('i', { text: moves ? '\u2192 ' + clock(vNow(r))
                              : 'already on the peak' }),
      ]),
    ]));
    acts.appendChild(el('button', {
      class: 'cur-cat' + (said === 'keep' ? ' on' : ''),
      style: '--cat:#ED8B33',
      title: 'Leave the stamp at ' + clock(r.was) + '   (k)',
      onclick: () => vSay('keep'),
    }, [
      el('kbd', { text: 'k' }),
      el('span', {}, [
        el('b', { text: 'Leave it' }),
        el('i', { text: 'stays at ' + clock(r.was) }),
      ]),
    ]));
    /* Undo. A decision made with one key has to be undoable with one key,
       or people stop pressing the key. */
    acts.appendChild(el('button', {
      class: 'cur-cat br-undo',
      disabled: said ? null : 'disabled',
      title: said ? 'Forget what was decided about this one   (u)'
                  : 'Nothing has been decided about this one',
      onclick: () => vUndo(),
    }, [
      el('kbd', { text: 'u' }),
      el('span', {}, [
        el('b', { text: 'Undo' }),
        el('i', { text: said ? 'this one' : '\u2014' }),
      ]),
    ]));
    bar.appendChild(acts);

    bar.appendChild(el('div', { class: 'cur-nav' }, [
      el('button', { class: 'mini', text: '◀', title: 'Previous  (p)',
                     onclick: () => vStep(-1) }),
      el('button', { class: 'mini', text: '▶', title: 'Next  (n)',
                     onclick: () => vStep(1) }),
      /* Moving it. Millisecond steps, because that is the grid everything
         here is measured on -- one sample at the rate the traces are
         decimated to. */
      el('div', { class: 'ctl' }, [
        el('label', { text: 'Move' }),
        el('div', { class: 'br-nudge' }, [
          el('button', { class: 'mini', text: '− 5',
                         title: 'Five milliseconds earlier',
                         onclick: () => vMove(-5) }),
          el('button', { class: 'mini', text: '− 1',
                         title: 'One millisecond earlier   ([)',
                         onclick: () => vMove(-1) }),
          el('button', { class: 'mini', text: '+ 1',
                         title: 'One millisecond later   (])',
                         onclick: () => vMove(1) }),
          el('button', { class: 'mini', text: '+ 5',
                         title: 'Five milliseconds later',
                         onclick: () => vMove(5) }),
        ]),
      ]),
      el('div', { class: 'ctl' }, [
        el('label', { text: 'Curve' }),
        el('div', { class: 'seg sm' }, [
          el('button', {
            class: view.curve ? 'active' : '',
            title: 'Draw the trace the rule took its maximum from \u2014 '
                 + 'mean |CSD| over the band, mains out. The green line is '
                 + 'this curve\u2019s largest peak in the window.',
            text: view.curve ? 'On' : 'Off',
            onclick: () => {
              view.curve = !view.curve;
              setCurvePref(view.curve);
              if (view.curve) loadCurve();
              else { view.trace = null; vPublish(); }
              vBar();
            },
          }),
        ]),
      ]),
      el('div', { class: 'ctl' }, [
        el('label', { text: 'List' }),
        el('div', { class: 'seg sm' }, [
          el('button', {
            class: view.list ? 'active' : '',
            title: 'Every stamp in the set, with what was decided \u2014 '
                 + 'click one to go to it   (l)',
            text: view.list ? 'On' : 'Off',
            onclick: () => { view.list = !view.list; vList(); vBar(); },
          }),
        ]),
      ]),
      el('div', { class: 'ctl' }, [
        el('label', { text: 'Show' }),
        el('div', { class: 'seg sm' }, [
          ['flag', 'Needing a decision'],
          ['all', 'All of them'],
        ].map(([id, label]) => el('button', {
          class: view.only === id ? 'active' : '',
          onclick: () => {
            if (view.only === id) return;
            const was = view.only;
            view.only = id;
            if (!vRows().filter(vWanted).length) {
              view.only = was;
              toast('Nothing is waiting for a decision.', null, 4000);
              vBar();
              return;
            }
            if (!vWanted(vAt())) {
              const i = vRows().findIndex(vWanted);
              if (i >= 0) { vGoTo(i); return; }
            }
            vPublish(); vBar();
          },
          text: label,
        }))),
      ]),
      el('span', { class: 'br-view-key' },
         VIEW_LABELS.map((l) => el('span', { class: 'br-browse-sw' }, [
           el('i', { style: 'background:' + l.color }),
           el('span', { text: l.name }),
         ]))),
      el('div', { style: 'flex:1' }),
      el('button', { class: 'btn ghost sm', text: 'Undo every decision',
                     title: 'Clears the whole pass. The proposal itself is '
                          + 'untouched.',
                     onclick: vUndoAll }),
      el('button', { class: 'btn ghost sm', text: 'Back to the proposal',
                     onclick: exitView }),
    ]));
  }

  function vKeys(e) {
    if (!view) return;
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
    const k = e.key.toLowerCase();
    if (k === 'n' || k === 'arrowright') vStep(1);
    else if (k === 'p' || k === 'arrowleft') vStep(-1);
    else if (k === 'enter') vSay('confirm');
    else if (k === 'k') vSay('keep');
    else if (k === '[') vMove(-1);
    else if (k === ']') vMove(1);
    else if (k === 'l') { view.list = !view.list; vList(); vBar(); }
    else if (k === 'u' || k === '0') vUndo();
    else if (k === 'escape') exitView();
    else return;
    e.preventDefault();
    e.stopPropagation();
  }

  /* ==================================================================
     Drawing the marks

     Not the generic curation painter. That one draws every mark the same
     way, which is right for curation -- one mark per candidate, coloured by
     the decision -- and wrong here, where each stamp is TWO marks that mean
     different things and the pair being decided has to stand out from the
     forty others on screen.

     The rules, which are the whole function:

       the one in focus      full height
       everything else       a short tick from the top
       where it goes         solid, green
       where it was          dashed, and the colour says what was decided:
                             green once confirmed, amber while flagged,
                             faint while nobody has said anything

     Read entirely off `sess.curationMarks`, never off this module's state,
     because the aid window runs this same file with no proposal loaded --
     everything it needs has to have travelled with the marks.
     ================================================================== */
  const DRAW = {
    now: '#5cc98d',        // where it goes
    was: '#6f8c7d',        // where it was, undecided
    ok: '#5cc98d',         // where it was, confirmed
    ask: '#ED8B33',        // where it was, flagged and unanswered
  };

  /* The same set, a whole recording wide.

     Not the same drawing. At forty pixels tall and an hour across there is
     no room for a dash pattern or a label, and the question the strip
     answers is different: not "where exactly does this stamp go" but
     "where in the recording is the work, and how much of it is done". So
     the two halves of each stamp are separated by HEIGHT rather than by
     dash -- where it goes on the top half, where it was on the bottom --
     and the one being decided runs the full height in the accent colour so
     it can be found at a glance.

     Read off `sess.curationMarks` like everything else, so the pop-out
     windows get it without knowing what Braces is. */
  function drawStrip(ctx, sess, w, h, dur) {
    const marks = sess && sess.curationMarks;
    if (!marks || marks.kind !== 'braces' || !dur) return false;
    const evs = marks.events || [];
    if (!evs.length) return true;

    ctx.save();
    const mid = Math.round(h * 0.52);
    const topY = 4;
    const botY = h - 9;
    for (const e of evs) {
      const x = Math.round((e.start / dur) * w) + 0.5;
      if (x < 0 || x > w) continue;
      const focus = !!e.f;
      const colour = e.k === 'now' ? DRAW.now
        : (e.st === 'confirmed' ? DRAW.ok
           : (e.st === 'flagged' ? DRAW.ask : DRAW.was));
      if (focus) {
        // Full height, and drawn last would be better still -- but there
        // are only two of them and forty of everything else, so a wider
        // line is enough to find them.
        ctx.globalAlpha = 1;
        ctx.lineWidth = 2;
        ctx.setLineDash(e.k === 'now' ? [] : [3, 2]);
        ctx.strokeStyle = colour;
        ctx.beginPath();
        ctx.moveTo(x, topY);
        ctx.lineTo(x, botY);
        ctx.stroke();
        continue;
      }
      ctx.globalAlpha = 0.72;
      ctx.lineWidth = 1;
      ctx.setLineDash([]);
      ctx.strokeStyle = colour;
      ctx.beginPath();
      if (e.k === 'now') {
        ctx.moveTo(x, topY);
        ctx.lineTo(x, mid - 1);
      } else {
        ctx.moveTo(x, mid + 1);
        ctx.lineTo(x, botY);
      }
      ctx.stroke();
    }
    ctx.restore();
    ctx.globalAlpha = 1;
    ctx.setLineDash([]);
    return true;
  }

  function draw(ctx, sess, win, x0, plotW, y0, plotH, P) {
    const marks = sess && sess.curationMarks;
    if (!marks || marks.kind !== 'braces') return;
    const evs = marks.events || [];
    if (!evs.length) return;
    const t0 = win.t0, t1 = win.t1 != null ? win.t1 : win.t0 + win.span;
    const span = t1 - t0;
    if (!(span > 0)) return;

    const X = (t) => x0 + ((t - t0) / span) * plotW;

    ctx.save();
    ctx.lineCap = 'butt';

    /* The window the focused stamp was allowed to move in, shaded.

       The rule made visible. Two lines ninety milliseconds apart mean
       nothing without it -- there is no way to tell whether the far one was
       even a candidate -- and it is the single thing somebody asked of this
       view that a pair of lines cannot answer. */
    /* The stamp the window is around, from the marks rather than from
       whichever of them claims the focus -- see `vPublish`. The search
       through the marks is still there as a fallback, for a window that
       adopted its copy before this field existed. */
    const homeT = marks.home_t != null ? marks.home_t
      : ((evs.find((e) => e.f && e.k === 'was')
          || evs.find((e) => e.f) || {}).start);
    const home = homeT == null ? null : { start: homeT };
    const reach = ((marks.window_ms || 100) / 1000);
    if (home) {
      const xa = X(home.start - reach), xb = X(home.start + reach);
      const la = Math.max(x0, xa), lb = Math.min(x0 + plotW, xb);
      ctx.globalAlpha = 1;
      /* Strong enough to survive a raster.

         At five per cent over a CSD image this read as a rendering
         artefact rather than as a region -- and the raster panels are
         exactly where somebody is deciding whether the new line sits on
         the sink, so it is where knowing what was reachable matters most.
         A visible wash, and both edges as solid rules with a bracket at
         the top, which is what makes it a REGION rather than two lines
         that happen to be there. */
      if (lb > la) {
        ctx.fillStyle = 'rgba(255, 184, 28, 0.20)';
        ctx.fillRect(la, y0, lb - la, plotH);
      }
      ctx.strokeStyle = 'rgba(255, 196, 60, 0.92)';
      ctx.lineWidth = 1.5;
      for (const xe of [xa, xb]) {
        if (xe < x0 || xe > x0 + plotW) continue;
        ctx.beginPath();
        ctx.moveTo(xe + 0.5, y0); ctx.lineTo(xe + 0.5, y0 + plotH);
        ctx.stroke();
      }
      if (lb > la) {
        ctx.beginPath();
        ctx.moveTo(la, y0 + 0.5); ctx.lineTo(lb, y0 + 0.5);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(la, y0 + plotH - 0.5);
        ctx.lineTo(lb, y0 + plotH - 0.5);
        ctx.stroke();
      }
    }

    /* The curve, under the marks.

       Drawn into the bottom third and scaled to its own maximum, because
       the units are current density and nothing else on this panel is --
       the shape and where it peaks are the whole content. Behind the
       marks on purpose: the green line is the answer and the curve is the
       working. */
    const cv = marks.curve;
    if (cv && cv.values && cv.values.length && cv.fs) {
      const vals = cv.values;
      let top = 0;
      for (const v of vals) if (v > top) top = v;
      if (top > 0) {
        const bandH = Math.max(18, plotH * 0.3);
        const baseY = y0 + plotH;
        /* Never outside the reach, whatever was read. The window is what
           the rule searched; a curve running past its edge invites the
           reading that the peak out there was passed over, when it was
           never a candidate. */
        const lo = home ? home.start - reach : -Infinity;
        const hi = home ? home.start + reach : Infinity;
        ctx.save();
        ctx.beginPath();
        let started = false;
        for (let i = 0; i < vals.length; i++) {
          const t = cv.t0 + i / cv.fs;
          if (t < lo || t > hi) continue;
          if (t < t0 - 0.001 || t > t1 + 0.001) continue;
          const x = X(t);
          const y = baseY - (vals[i] / top) * bandH;
          if (started) ctx.lineTo(x, y); else { ctx.moveTo(x, y);
                                                started = true; }
        }
        if (started) {
          /* Three strokes, because this has to read over white, over
             saturated blue and over saturated red in the same panel and
             no single colour does. A wide dark stroke underneath is the
             outline; the bright line goes inside it. The same trick the
             marks and the gridlines use, one step heavier because a
             curve is thinner than a rule and crosses more of the image.  */
          ctx.globalAlpha = 1;
          ctx.lineJoin = 'round';
          ctx.lineWidth = 3.4;
          ctx.strokeStyle = 'rgba(0,0,0,0.72)';
          ctx.stroke();
          ctx.lineWidth = 2;
          ctx.strokeStyle = '#ffe08a';
          ctx.stroke();
        }
        ctx.restore();
        ctx.globalAlpha = 1;
      }
    }

    for (const e of evs) {
      if (e.start < t0 || e.start > t1) continue;
      const x = X(e.start);
      const focus = !!e.f;
      /* EVERY mark is full height.

         Short ticks for the ones not being decided were the wrong trade.
         They made the focused pair easy to find and everything else easy
         to miss -- and worse, they made a mark's VISIBILITY depend on a
         flag that travels between windows, so any pointer that went
         astray left a panel that looked empty rather than a panel that
         looked slightly wrong. Emphasis can carry the focus instead:
         wider, opaque, and haloed against whatever is underneath. */
      const top = y0;
      const bottom = y0 + plotH;
      const colour = e.k === 'now' ? DRAW.now
        : (e.st === 'confirmed' ? DRAW.ok
           : (e.st === 'flagged' ? DRAW.ask : DRAW.was));
      const dashed = e.k !== 'now';

      /* A line that survives whatever is under it: a dark and a light
         hairline either side, the same trick the curation marks and the
         time gridlines use. Only on the focused pair, which is now the
         only thing telling it apart from its neighbours -- so it is worth
         the three strokes. */
      if (focus) {
        ctx.setLineDash([]);
        ctx.lineWidth = 1;
        ctx.globalAlpha = 0.5;
        ctx.strokeStyle = 'rgba(0,0,0,0.9)';
        ctx.beginPath(); ctx.moveTo(x - 1.5, top); ctx.lineTo(x - 1.5, bottom);
        ctx.stroke();
        ctx.strokeStyle = 'rgba(255,255,255,0.85)';
        ctx.beginPath(); ctx.moveTo(x + 1.5, top); ctx.lineTo(x + 1.5, bottom);
        ctx.stroke();
      }

      /* Forty full-height lines could be a fence, so the ones not being
         decided are thin and quiet -- present, readable, and clearly not
         the thing being asked about. The focused pair is twice the width,
         fully opaque and haloed, which is a bigger difference than height
         ever was. */
      ctx.globalAlpha = focus ? 1 : 0.34;
      ctx.setLineDash(dashed ? (focus ? [6, 4] : [3, 4]) : []);
      ctx.lineWidth = focus ? 2.2 : 1;
      ctx.strokeStyle = colour;
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, bottom);
      ctx.stroke();
    }

    /* Which way the focused pair moved, drawn once: a hairline between the
       two with the number on it. The distance is the decision, and reading
       it off two lines and a time axis is arithmetic somebody should not
       have to do. */
    const a = evs.find((e) => e.f && e.k === 'was');
    const b = evs.find((e) => e.f && e.k === 'now');
    if (a && b && Math.abs(a.start - b.start) > 1e-9) {
      const xa = X(a.start), xb = X(b.start);
      const y = y0 + Math.min(plotH - 6, 16);
      ctx.setLineDash([]);
      ctx.globalAlpha = 0.9;
      ctx.lineWidth = 1;
      ctx.strokeStyle = DRAW.now;
      ctx.beginPath(); ctx.moveTo(xa, y); ctx.lineTo(xb, y); ctx.stroke();
      // A head on the end it is going to.
      const dir = xb >= xa ? -1 : 1;
      ctx.beginPath();
      ctx.moveTo(xb, y);
      ctx.lineTo(xb + dir * 5, y - 3.5);
      ctx.lineTo(xb + dir * 5, y + 3.5);
      ctx.closePath();
      ctx.fillStyle = DRAW.now;
      ctx.fill();
      const ms_ = (b.start - a.start) * 1000;
      const txt = (ms_ > 0 ? '+' : '') + ms_.toFixed(1) + ' ms';
      ctx.font = '10px ui-monospace, Consolas, monospace';
      const w = ctx.measureText(txt).width;
      const mx = (xa + xb) / 2;
      ctx.globalAlpha = 0.85;
      ctx.fillStyle = 'rgba(0,0,0,0.65)';
      ctx.fillRect(mx - w / 2 - 3, y - 14, w + 6, 11);
      ctx.globalAlpha = 1;
      ctx.fillStyle = DRAW.now;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'alphabetic';
      ctx.fillText(txt, mx - w / 2, y - 5);
    }
    ctx.restore();
  }

  /* ---------- 3. the bench ---------- */
  function openBench(n) {
    const r = (set_.set.rows || [])[n];
    if (!r) return;
    const said = (set_.set.calls || {})[String(n)] || {};
    bench = {
      n: n,
      t: said.t != null ? said.t : (r.now != null ? r.now : r.was),
      trace: null,
    };
    render();
    loadTrace();
  }

  function benchNeighbours() {
    /* Every row in the same run, so a contested flag can show WHY it gave
       up a nearer peak rather than asserting it. A run is the group that
       could reach a common peak, which on screen is simply the rows whose
       windows overlap this one's. */
    const r = set_.set.rows[bench.n];
    const w = ((set_.set.params || {}).window_ms || 100) / 1000;
    return (set_.set.rows || []).filter((o) => o !== r
      && Math.abs((o.now == null ? o.was : o.now) - r.was) < w * 2.2);
  }

  async function loadTrace() {
    const s = set_.set;
    const r = s.rows[bench.n];
    const span = ((s.params || {}).window_ms || 100) / 1000 * 3;
    try {
      /* The summed profile, which is the thing the rule looked at. Drawing
         one channel here would be drawing something else -- a trace that
         peaks a few milliseconds from where the decision was made, shown to
         the person being asked to adjudicate that exact disagreement. */
      const got = await apiPost(
        '/api/braces/set/' + encodeURIComponent(s.set_id) + '/profile',
        { t0: r.was - span, t1: r.was + span });
      if (bench) { bench.trace = got; drawBench(); }
    } catch (e) {
      if (bench) { bench.error = e.message; render(); }
    }
  }

  function benchCard() {
    const s = set_.set;
    const r = s.rows[bench.n];
    const card = el('div', { class: 'card br-bench' });
    card.appendChild(el('div', { class: 'br-bench-head' }, [
      el('strong', { html: (r.flag ? '<span class="flagmark">⚑</span> '
                            : '') + (REASONS[r.flag] || 'confirmed') }),
      el('span', { class: 'br-sub', text:
        'was ' + clock(r.was) + '   →   now ' + clock(bench.t)
        + '   ·   ' + ms((bench.t - r.was) * 1000) + ' ms'
        + (r.peak_uv ? '   ·   ' + Math.round(r.peak_uv) + ' µV'
           : '') }),
      el('div', { style: 'flex:1' }),
      el('button', { class: 'btn ghost sm', text: 'Close',
                     onclick: () => { bench = null; render(); } }),
    ]));
    card.appendChild(el('canvas', { id: 'brBench', class: 'br-canvas',
                                    height: '190' }));
    if (bench.error) {
      card.appendChild(el('p', { class: 'br-err', text:
        'The recording could not be read here: ' + bench.error }));
    }
    if (r.flag === 'contested') {
      card.appendChild(el('p', { class: 'hint', text:
        'This stamp gave up a closer peak so the next one could have it. '
        + 'The other stamps in its run are drawn faintly — moving this '
        + 'one back onto the near peak would leave one of them with '
        + 'nothing.' }));
    }
    card.appendChild(el('div', { class: 'br-bench-bar' }, [
      el('button', { class: 'btn primary sm', text: 'Confirm',
                     onclick: () => answer('confirm') }),
      el('button', { class: 'btn ghost sm', text: 'Keep it where it was',
                     onclick: () => answer('keep') }),
      el('button', { class: 'btn ghost sm', text: 'Reset',
                     onclick: () => { bench.t = r.now == null ? r.was : r.now;
                                      render(); drawBench(); } }),
      el('div', { style: 'flex:1' }),
      keyHint('↵', 'confirm'), keyHint('[ ]', 'nudge 1 ms'),
      keyHint('0', 'reset'), keyHint('k', 'keep'),
      keyHint('n p', 'step'),
    ]));
    setTimeout(drawBench, 0);
    return card;
  }

  const keyHint = (k, what) => el('span', { class: 'br-key' }, [
    el('kbd', { text: k }), el('span', { text: what })]);

  async function answer(call) {
    if (!bench) return;
    const n = bench.n;
    const r = set_.set.rows[n];
    const moved = Math.abs(bench.t - (r.now == null ? r.was : r.now)) > 1e-6;
    if (call === 'confirm' && moved) {
      await decide(n, 'move', bench.t);
    } else {
      await decide(n, call);
    }
    nextFlag(n);
  }

  function nextFlag(from) {
    const all = set_.set.rows || [];
    for (let i = from + 1; i < all.length; i++) {
      if (all[i].flag && !callFor(i)) { openBench(i); return; }
    }
    bench = null;
    render();
    toast('That was the last one in this pass.', null, 4000);
  }

  function stepBench(d) {
    const all = set_.set.rows || [];
    let i = bench.n + d;
    while (i >= 0 && i < all.length) {
      if (all[i].flag) { openBench(i); return; }
      i += d;
    }
  }

  /* ---------- drawing the bench ---------- */
  function drawBench() {
    const cv = document.getElementById('brBench');
    if (!cv || !bench) return;
    const s = set_.set;
    const r = s.rows[bench.n];
    const dpr = window.devicePixelRatio || 1;
    const w = cv.clientWidth || 700, h = 190;
    cv.width = w * dpr; cv.height = h * dpr;
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const css = getComputedStyle(document.documentElement);
    const tone = (n, f) => (css.getPropertyValue(n) || f).trim() || f;
    g.clearRect(0, 0, w, h);

    const win = ((s.params || {}).window_ms || 100) / 1000;
    const span = win * 3;
    const t0 = r.was - span, t1 = r.was + span;
    const X = (t) => ((t - t0) / (t1 - t0)) * w;
    const base = h - 26;

    /* The window the rule was allowed to look in. */
    g.fillStyle = tone('--accent-soft', 'rgba(255,184,28,.12)');
    g.fillRect(X(r.was - win), 0, X(r.was + win) - X(r.was - win), base);

    /* The summed profile itself, sample for sample. Its own time base --
       the read starts where the file's records start, not where the window
       was asked for, and drawing it against the asked-for edges would slide
       the whole trace by up to a sample. */
    const pf = bench.trace || {};
    const vals = pf.values || [];
    if (vals.length && pf.fs) {
      let top = 1;
      for (const v of vals) top = Math.max(top, v);
      g.beginPath();
      for (let i = 0; i < vals.length; i++) {
        const x = X(pf.t0 + i / pf.fs);
        const y = base - (vals[i] / top) * (base - 14);
        if (i) g.lineTo(x, y); else g.moveTo(x, y);
      }
      g.strokeStyle = tone('--accent-2', '#7FE3B0');
      g.lineWidth = 1.6;
      g.stroke();
      g.fillStyle = tone('--text-3', '#6f8c7d');
      g.font = '10px ui-monospace, monospace';
      g.fillText('mean |CSD| over ' + pf.n_channels + ' contacts · '
                 + '5–100 Hz, mains out'
                 + (pf.smooth_ms ? ' · smoothed ' + pf.smooth_ms + ' ms'
                                 : ''),
                 4, 12);

      /* What a candidate had to clear HERE.
         Measured on this window's own quiet rather than pooled over the
         set, which is why it comes back with the trace instead of off the
         summary: two windows in different parts of a recording do not
         share a baseline, and one number drawn across both would be a
         line neither of them was judged against. */
      const thr = pf.floor || (s.summary || {}).thr_uv;
      if (thr && thr < top) {
        const y = base - (thr / top) * (base - 14);
        g.save();
        g.setLineDash([3, 4]);
        g.strokeStyle = tone('--text-3', '#6f8c7d');
        g.lineWidth = 1;
        g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke();
        g.restore();
        g.fillStyle = tone('--text-3', '#6f8c7d');
        g.font = '10px ui-monospace, monospace';
        g.fillText('4.5 SD over the background · '
                   + Math.round(thr) + ' (nothing is gated on it)',
                   4, y - 3);
      }
    }
    g.strokeStyle = tone('--line', '#244737');
    g.lineWidth = 1;
    g.beginPath(); g.moveTo(0, base); g.lineTo(w, base); g.stroke();

    /* The other stamps in the run, faintly, so a contested flag shows its
       reason rather than asserting it. */
    for (const o of benchNeighbours()) {
      const t = o.now == null ? o.was : o.now;
      if (t < t0 || t > t1) continue;
      g.save();
      g.globalAlpha = 0.45;
      g.setLineDash([5, 4]);
      g.strokeStyle = tone('--text-3', '#6f8c7d');
      g.beginPath(); g.moveTo(X(t), 18); g.lineTo(X(t), base); g.stroke();
      g.restore();
    }

    /* Where it was. */
    g.save();
    g.setLineDash([5, 4]);
    g.strokeStyle = tone('--text-2', '#a3bdb0');
    g.lineWidth = 1.5;
    g.beginPath(); g.moveTo(X(r.was), 8); g.lineTo(X(r.was), base); g.stroke();
    g.restore();
    label(g, 'was ' + clock(r.was), X(r.was) + 4, 18,
          tone('--text-2', '#a3bdb0'));

    /* Where it is going. */
    g.strokeStyle = tone('--accent', '#FFB81C');
    g.lineWidth = 2;
    g.beginPath(); g.moveTo(X(bench.t), 8); g.lineTo(X(bench.t), base);
    g.stroke();
    label(g, 'now ' + clock(bench.t), X(bench.t) + 4, 32,
          tone('--accent', '#FFB81C'));

    /* The axis, in milliseconds from where the stamp was -- which is the
       number the decision is actually about. */
    g.fillStyle = tone('--text-3', '#6f8c7d');
    g.font = '10px ui-monospace, monospace';
    for (const d of [-win * 2, -win, 0, win, win * 2]) {
      const x = X(r.was + d);
      g.fillText((d > 0 ? '+' : '') + Math.round(d * 1000), x - 10, h - 8);
    }
    cv.onpointerdown = benchDrag;
  }

  function label(g, text, x, y, colour) {
    g.fillStyle = colour;
    g.font = '11px ui-monospace, monospace';
    g.fillText(text, x, y);
  }

  function benchDrag(e) {
    const cv = e.currentTarget;
    const s = set_.set;
    const r = s.rows[bench.n];
    const win = ((s.params || {}).window_ms || 100) / 1000;
    const span = win * 3;
    const t0 = r.was - span, t1 = r.was + span;
    const move = (ev) => {
      const rect = cv.getBoundingClientRect();
      const f = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
      bench.t = Math.round((t0 + f * (t1 - t0)) * 1e6) / 1e6;
      drawBench();
      const head = document.querySelector('.br-bench-head .br-sub');
      if (head) {
        head.textContent = 'was ' + clock(r.was) + '   →   now '
          + clock(bench.t) + '   ·   '
          + ms((bench.t - r.was) * 1000) + ' ms';
      }
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    move(e);
  }

  /* ---------- keys ---------- */
  function keys(e) {
    if (!bench || !set_) return;
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
    const s = set_.set;
    const r = s.rows[bench.n];
    const k = e.key.toLowerCase();
    if (k === 'enter') { answer('confirm'); }
    else if (k === 'k') { answer('keep'); }
    else if (k === '0') { bench.t = r.now == null ? r.was : r.now;
                          render(); }
    else if (k === '[') { bench.t = Math.round((bench.t - 0.001) * 1e6) / 1e6;
                          drawBench(); }
    else if (k === ']') { bench.t = Math.round((bench.t + 0.001) * 1e6) / 1e6;
                          drawBench(); }
    else if (k === 'n') { stepBench(1); }
    else if (k === 'p') { stepBench(-1); }
    else if (k === 'escape') { bench = null; render(); }
    else return;
    e.preventDefault();
    e.stopPropagation();
  }
  document.addEventListener('keydown', keys, true);

  /* ---------- accepting ---------- */
  async function commit(apply) {
    if (busy || !set_) return;
    busy = true;
    let out;
    try {
      out = await apiPost('/api/braces/set/'
                          + encodeURIComponent(set_.set.set_id) + '/commit',
                          { apply: apply === true });
    } catch (e) {
      busy = false;
      toast(e.message, 'err', 9000);
      return;
    }
    busy = false;
    const rep = out.report || {};
    if (rep.error) { toast(rep.error, 'err', 9000); return; }
    if (apply === true) {
      toast('Banked as version ' + rep.version + '. ' + rep.moved
            + ' stamp' + (rep.moved === 1 ? '' : 's') + ' moved.', 'ok', 7000);
      await openSet(set_.set.set_id);
      cands = null;
      return;
    }
    confirmDialog(rep);
  }

  /* What the write would do, before it does it. A timestamp rewrite that
     cannot be read before it happens should not be offered at all -- the
     rule `retime` set, and for the same reason. */
  function confirmDialog(rep) {
    const body = el('div', { class: 'br-confirm' }, [
      el('p', { text:
        /* Continuing or branching, as the server worked it out.
           It used to say "branching off" whenever a version had been
           picked, which produced "becomes version 4, branching off
           version 3" -- two different writes in one sentence, since
           branching off v3 is v3.1 and v4 is what continuing it looks
           like. And the version it named was the REF it had been sent,
           not a name anybody would recognise. */
        'This becomes v' + (rep.next_name != null ? rep.next_name
                            : rep.next_version) + ' of the set, '
        + (rep.branching
           ? 'branching off v' + rep.from_name
             + ' and leaving everything already built on it alone.'
           : 'continuing from v' + (rep.from_name != null ? rep.from_name
                                    : rep.current_name) + '.') }),
      el('ul', {}, [
        el('li', { text: rep.moved + ' stamp'
                         + (rep.moved === 1 ? '' : 's') + ' move, by '
                         + ms(rep.shift_min_ms) + ' to '
                         + ms(rep.shift_max_ms) + ' ms' }),
        el('li', { text: rep.unmoved + ' stay exactly where they are'
                         + (rep.left_alone
                            ? ', including ' + rep.left_alone
                              + ' flagged and unanswered' : '') }),
        /* What is being left out, said before it happens. "Nothing is
           deleted" stopped being true when an aligned version started
           holding the spikes and not the candidates somebody rejected. */
        rep.n_dropped
          ? el('li', { text: rep.n_dropped + ' left out for not being an '
                             + 'event ('
                             + Object.keys(rep.dropped || {})
                                 .map((k) => (rep.dropped[k]) + ' ' + k)
                                 .join(', ')
                             + '). Every earlier version still holds them.' })
          : null,
        el('li', { text: 'No label is read or changed, and nothing is '
                         + 'removed from any version that already exists.' }),
        el('li', { text: 'Every moved stamp keeps the time it came from, so '
                         + 'this can be read back and undone.' }),
      ].filter(Boolean)),
    ]);
    const sample = (rep.moves || []).slice(0, 6);
    if (sample.length) {
      body.appendChild(el('div', { class: 'br-scroll' }, [
        el('table', { class: 'br-tbl' }, [
          el('thead', {}, [el('tr', {}, ['was', 'now', 'Δ ms', 'why']
            .map((t) => el('th', { text: t })))]),
          el('tbody', {}, sample.map((m) => el('tr', {}, [
            el('td', { text: clock(m[0]) }),
            el('td', { text: clock(m[1]) }),
            el('td', { text: ms(m[2]) }),
            el('td', { text: REASONS[m[4]] || '' }),
          ]))),
        ]),
      ]));
    }
    ask('Bank this alignment as v' + (rep.next_name != null ? rep.next_name
                                      : rep.next_version) + '?',
        body, 'Bank it',
        () => commit(true));
  }

  /* The app's own modal, not a second one. `showModal` stacks, so the
     confirmation can open over the proposal without the proposal being
     rebuilt underneath it and losing the scroll position. */
  /* A confirmation, in the shape every other dialog in this app uses.

     It used to build its own `.modal` and hand that to `showModal`, which
     puts whatever it is given INSIDE `#bigModalBox` -- and that box is
     already a `.modal.big`. So the result was a modal inside a modal: a
     620px bordered panel sitting at the left edge of a 1240px one, with
     the header, the body and the footer laid out against the wrong box.
     That is the "weird" of it.

     `mh` / `mb` / `mf` are what the big box is built to hold: the header
     and footer pinned, the body the only thing that scrolls. The reading
     width is capped inside the body instead, which is a thing to do to a
     column of text rather than to a dialog. */
  function ask(title, body, okText, onOk, danger) {
    const wrap = el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: title }),
        el('div', { class: 'spacer' }),
      ]),
      el('div', { class: 'mb br-ask' }, [body]),
      el('div', { class: 'mf' }, [
        el('div', { style: 'flex:1' }),
        el('button', { class: 'btn ghost', text: 'Cancel',
                       onclick: closeModal }),
        el('button', {
          class: 'btn' + (danger ? ' danger' : ''), text: okText,
          onclick: () => { closeModal(); onOk(); },
        }),
      ]),
    ]);
    showModal(wrap, { replace: true });
  }

  async function discard() {
    ask('Throw this proposal away?',
        el('p', { text:
          'The measurement and every decision made about it go. The set '
          + 'itself is untouched — nothing has been written to it.' }),
        'Discard',
        async () => {
          try {
            await apiPost('/api/braces/set/'
                          + encodeURIComponent(set_.set.set_id) + '/delete',
                          {});
            set_ = null; bench = null; render();
          } catch (e) { toast(e.message, 'err', 8000); }
        },
        true);
  }

  return {
    paint,
    /* For the harness: what is on screen now, and a way to drive it
       without a mouse. */
    _state: () => ({ q, plan, set: set_, bench, filter, job }),
    _open: openSet,
    _run: run,
    _decide: decide,
    _bench: openBench,
    _answer: answer,
    _commit: commit,
    _rows: rows,
    draw,
    drawStrip,
    _enter: enter,
    _view: () => view,
    _reset: () => { set_ = null; bench = null; cands = null; },
  };
}());
