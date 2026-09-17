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
    channel: null,      // null means "sweep and pick one"
    channels: null,     // which to sweep; null means "whatever is not bad"
    window_ms: 100,
    estimator: 'sd',
  };

  let cands = null;     // sets that could be aligned
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
        channel: q.channel,
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
        channel: q.channel,
        channels: q.channels,
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

  /* The progress bar, updated in place. Returns false when the panel is
     not showing one, which is when a full render is the right answer. */
  function paintJob() {
    const bar = document.querySelector('#brJob i');
    const step = document.querySelector('#brJob span');
    if (!bar || !step) { render(); return; }
    bar.style.width = Math.round(((job && job.frac) || 0) * 100) + '%';
    step.textContent = (job && job.step) || 'reading the channel…';
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
      const got = await apiPost(
        '/api/braces/set/' + encodeURIComponent(set_.set.set_id) + '/decide',
        { row: n, call: call, t: t });
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
    if (set_) { h.appendChild(setView()); return; }
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

    /* Which set. */
    const card = el('div', { class: 'card' });
    card.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                 text: 'Which set' }));
    const sel = el('select', {
      class: 'br-set',
      onchange: (e) => { q.entry = e.target.value; q.channel = null;
                         q.from_version = null; refreshPlan(); },
    });
    for (const c of cands) {
      const done = c.aligned ? '  · aligned' : '';
      sel.appendChild(el('option', {
        value: c.id, selected: c.id === q.entry ? 'selected' : null,
        text: (c.name || c.id) + '  · ' + c.n + ' stamps  · v'
              + c.current_version + done,
      }));
    }
    card.appendChild(sel);

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
      field('Channel', el('input', {
        type: 'number', placeholder: 'auto',
        value: q.channel == null
          ? ((plan && plan.channel && plan.channel.number) || '')
          : q.channel,
        onchange: (e) => {
          const v = parseInt(e.target.value, 10);
          q.channel = isNaN(v) ? null : v;
          refreshPlan();
        },
      }), (plan && plan.channel) ? plan.channel.how
          : 'blank = sweep them all'),
      field('Window ±ms', el('input', {
        type: 'number', step: '10', min: '5', value: String(q.window_ms),
        onchange: (e) => {
          q.window_ms = Math.max(5, parseFloat(e.target.value) || 100);
          render();
        },
      }), 'how far a stamp may move'),
    ]));
    if (plan && plan.ok && plan.sweeps) set.appendChild(channelPicker());
    set.appendChild(el('p', { class: 'hint', text:
      (plan && plan.sweeps)
        ? 'This set does not say which channel it came from, so every '
          + 'channel is read and the one these events are biggest on wins '
          + '— measured at the stamps themselves, not over the whole '
          + 'recording, because how loud a wire hums is a different question '
          + 'from where the dentate spikes are.'
        : 'Nothing is thresholded. A peak is already the largest thing '
          + 'within a hundred milliseconds of itself, and a height on top '
          + 'of that could only throw away the right answer for a real '
          + 'event that happens to be small here.' }));
    box.appendChild(set);

    /* Go. */
    const go = el('div', { class: 'br-go' });
    if (job) {
      go.appendChild(el('div', { class: 'br-job', id: 'brJob' }, [
        el('span', { text: job.step || 'reading the channel…' }),
        el('div', { class: 'br-bar' },
           [el('i', { style: 'width:' + Math.round((job.frac || 0) * 100)
                             + '%' })]),
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
      el('label', { text: 'Channels to sweep' }),
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
      plan.channel
        ? dt('Channel', 'CSC' + plan.channel.number
                        + '  (' + plan.channel.how + ')')
        : dt('Channel', 'swept — all '
                        + ((plan.channels || []).length || '')
                        + ' of them, then the one these events are '
                        + 'biggest on'),
      dt('Band', s.band ? s.band[0] + '–' + s.band[1] + ' Hz, on the '
                          + 'magnitude' : '—'),
      dt('Stamps', plan.entry.n + ' in v' + plan.current_version),
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
        v: 'v' + plan.current_version,
        chip: 'now',
        what: plan.entry.n + ' stamps, as they stand',
        does: 'the next version continues the line',
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
  function setView() {
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
          'CSC' + (s.params || {}).channel + '  ·  ±'
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

    /* Which channel the sweep chose, and how clear the win was. A margin
       of thirty per cent and a margin of two are different facts about a
       probe, and only the second is worth a second look -- the same reason
       Incisor shows its own margin rather than only its pick. */
    if (sum.sweep && sum.sweep.picked) {
      const p = sum.sweep.picked;
      const close = p.margin_pct != null && p.margin_pct < 5;
      box.appendChild(el('p', { class: 'hint br-note', text:
        (sum.sweep.reused_from
          ? 'Channel reused from an earlier sweep of this recording: '
          : 'Swept all ' + sum.sweep.n_channels + ' channels. ')
        + 'These events are biggest on CSC' + p.number + ' (median '
        + Math.round(p.median_uv) + ' µV'
        + (p.margin_pct != null
            ? ', ' + p.margin_pct + '% clear of CSC' + p.runner_up
            : '')
        + '). Measured at the stamps themselves, not over the whole '
        + 'recording.'
        + (close
            ? '  That margin is small — adjacent sites on a shank see '
              + 'the same spikes at almost the same size, so CSC'
              + p.runner_up + ' would do about as well. It is worth knowing '
              + 'rather than worth worrying about: the stamps land in the '
              + 'same place either way.'
            : '') }));
      box.appendChild(sweepTable(sum.sweep));
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

  /* Every channel the sweep read, in order. The shape of this column is
     the answer: a gradient down the shank is a probe working and a set
     measured against the right thing; a flat table is neither, and no
     single number says so. */
  function sweepTable(sw) {
    const ranked = sw.ranked || [];
    if (!ranked.length) return el('span');
    const card = el('div', { class: 'card' });
    const open = { on: false };
    const top = Math.max(...ranked.map((r) => r.median_uv || 0)) || 1;
    const body = el('div', { class: 'br-sweep hidden' });
    for (const r of ranked) {
      body.appendChild(el('div', {
        class: 'br-sweep-row' + (r.number === (sw.picked || {}).number
                                 ? ' won' : ''),
      }, [
        el('span', { class: 'n', text: 'CSC' + r.number }),
        el('span', { class: 'bar' },
           [el('i', { style: 'width:' + ((r.median_uv / top) * 100) + '%' })]),
        el('span', { class: 'v', text: Math.round(r.median_uv) + ' µV' }),
      ]));
    }
    const btn = el('button', {
      class: 'btn ghost sm',
      text: 'Show all ' + ranked.length + ' channels',
      onclick: () => {
        open.on = !open.on;
        body.classList.toggle('hidden', !open.on);
        btn.textContent = open.on ? 'Hide the channel table'
                                  : 'Show all ' + ranked.length + ' channels';
      },
    });
    card.appendChild(el('div', { class: 'br-chans-head' }, [
      el('label', { text: 'How every channel scored' }),
      el('div', { style: 'flex:1' }),
      btn,
    ]));
    if ((sw.skipped || []).length) {
      card.appendChild(el('p', { class: 'hint', text:
        'Not read: CSC' + sw.skipped.join(', CSC')
        + ' — unticked before the run.' }));
    }
    card.appendChild(body);
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
        el('td', { class: 'why', text: said
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
    bar.appendChild(el('button', {
      class: 'btn primary',
      text: 'Accept and bank…',
      onclick: () => commit(false),
    }));
    bar.appendChild(el('span', { class: 'hint', text: waiting
      ? waiting + ' flag' + (waiting === 1 ? '' : 's') + ' still unanswered. '
        + 'Those stamps stay exactly where they are — a flag nobody '
        + 'resolved is never moved on the assumption it was probably right.'
      : 'Every flag has been answered.' }));
    bar.appendChild(el('div', { style: 'flex:1' }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Discard this proposal',
      onclick: discard,
    }));
    return bar;
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
    const t0 = r.was - span, t1 = r.was + span;
    try {
      const got = await apiPost('/api/csc/window', {
        path: (plan && plan.session && plan.session.path)
              || (set_.session_path || ''),
        channels: [(s.params || {}).channel],
        t0: t0, t1: t1, px: 900,
        highpass: (s.params.band || [5, 100])[0],
        lowpass: (s.params.band || [5, 100])[1],
      });
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

    /* The magnitude, from the band-passed envelope. `max(|lo|,|hi|)` per
       column IS the magnitude envelope -- the same |x| the rule measured,
       at the resolution the screen can show. */
    const ser = ((bench.trace || {}).series || [])[0];
    if (ser && ser.min) {
      const n = ser.min.length;
      let top = 1;
      for (let i = 0; i < n; i++) {
        top = Math.max(top, Math.abs(ser.min[i]), Math.abs(ser.max[i]));
      }
      g.beginPath();
      for (let i = 0; i < n; i++) {
        const v = Math.max(Math.abs(ser.min[i]), Math.abs(ser.max[i]));
        const x = (i / (n - 1)) * w;
        const y = base - (v / top) * (base - 14);
        if (i) g.lineTo(x, y); else g.moveTo(x, y);
      }
      g.strokeStyle = tone('--accent-2', '#7FE3B0');
      g.lineWidth = 1.4;
      g.stroke();

      /* What the detector would have called an event on this channel.
         Not a threshold any more -- nothing is gated on it -- but a peak
         under this line is why a row reads "weak peak", and the line is
         how that stops being an assertion. */
      const thr = (s.summary || {}).thr_uv;
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
        g.fillText('detection threshold ' + Math.round(thr) + ' µV',
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
        'This becomes version ' + rep.next_version + ' of the set, '
        + (rep.from_version == null
           ? 'continuing from version ' + rep.current_version + '.'
           : 'branching off version ' + rep.from_version
             + ' and leaving everything after it alone.') }),
      el('ul', {}, [
        el('li', { text: rep.moved + ' stamp'
                         + (rep.moved === 1 ? '' : 's') + ' move, by '
                         + ms(rep.shift_min_ms) + ' to '
                         + ms(rep.shift_max_ms) + ' ms' }),
        el('li', { text: rep.unmoved + ' stay exactly where they are'
                         + (rep.left_alone
                            ? ', including ' + rep.left_alone
                              + ' flagged and unanswered' : '') }),
        el('li', { text: 'No label is read or changed. Nothing is deleted.' }),
        el('li', { text: 'Every moved stamp keeps the time it came from, so '
                         + 'this can be read back and undone.' }),
      ]),
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
    ask('Bank this alignment as v' + rep.next_version + '?', body, 'Bank it',
        () => commit(true));
  }

  /* The app's own modal, not a second one. `showModal` stacks, so the
     confirmation can open over the proposal without the proposal being
     rebuilt underneath it and losing the scroll position. */
  function ask(title, body, okText, onOk, danger) {
    const wrap = el('div', { class: 'modal br-modal' });
    wrap.appendChild(el('div', { class: 'modal-head' }, [
      el('strong', { text: title }),
    ]));
    wrap.appendChild(el('div', { class: 'modal-body' }, [body]));
    wrap.appendChild(el('div', { class: 'modal-foot' }, [
      el('div', { style: 'flex:1' }),
      el('button', { class: 'btn ghost', text: 'Cancel',
                     onclick: closeModal }),
      el('button', {
        class: 'btn' + (danger ? ' danger' : ''), text: okText,
        onclick: () => { closeModal(); onOk(); },
      }),
    ]));
    showModal(wrap);
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
    _reset: () => { set_ = null; bench = null; cands = null; },
  };
}());
