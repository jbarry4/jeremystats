/* ==========================================================================
   doppler.js -- Doppler, the interictal discharge detector.

   Step 1 of The Storm. Radar sweeps the whole recording and says where the
   cells are; a Spotter then confirms by eye what radar saw. That is
   detect -> curate, and it is also the split between the cluster and this
   computer.

   IT RUNS ON THE CLUSTER, AND ONLY THERE
   The line-length transform is taken over every kept channel of a whole
   recording at its native rate. The lab's own .sbat files ask for 800 GB to
   do it. So there is no "this computer" tab: a button that fails on every
   real recording and works on the demo is worse than a sentence saying
   where the work happens. The detector itself is an ordinary function --
   `tools/check_doppler_parity.py` calls it directly, and that is what keeps
   it honest against the MATLAB.

   THE SHAPE OF THE PANEL
     1. pick a recording
     2. check the channels -- the ones marked bad arrive already unticked
     3. settings, with NO FILTERING by default, so a first run reproduces
        the numbers the lab's MATLAB produces and any difference from them
        is something somebody chose
     4. run it, and read the report
     5. bank it under a name, and take it to Spotter

   WHAT THE REPORT IS FOR
   A feel for what came in, not a figure for a paper. Four things, in the
   order you want them: how many and how often, what they look like on
   average, where they are, and which channels they came off. Then the
   parameters in a form you can quote, and anything that should make you
   distrust the run.
   ========================================================================== */
'use strict';

BARRY.doppler = (function () {
  /* What is being asked for. Held here rather than read off the DOM, so a
     redraw cannot lose a half-filled form. */
  const q = {
    gid: null,
    path: null,
    // The picked registry row. A banked set has to say which animal and
    // session it belongs to or it files itself under "Unfiled" and is never
    // found again.
    row: null,
    llw_s: 0.040,
    prc: 99.9,
    // BOTH OFF. See the header: the default is the legacy answer.
    notch_hz: null,
    band_lo: 3,
    band_hi: 70,
    band_on: false,
    /* Channels left out of THIS RUN ONLY, by CSC number. Not bad channels:
       a bad channel is a claim about the recording that every other tool
       acts on, and this is a question somebody is asking of one run --
       "what does it find on the odd shank alone". Numbers, never row
       indices, because an index shifts the moment a file goes missing. */
    exclude: [],
    preset: 'all',
    // One recording or many (constitution §6d). Both run on the VACC.
    count: 'one',
  };

  /* The .m file's own, named once so the "changed" tag and the reset cannot
     drift apart from what the fields start at. */
  const DEFAULTS = { llw_s: 0.040, prc: 99.9, notch_hz: null, band_on: false };

  let est = null;        // what a run would cost
  let job = null;        // the run in flight
  let poll = null;
  let res = null;        // the finished run
  let snips = null;      // the sample of raw waveforms, fetched once
  let reviews = null;    // runs that have already landed
  let batch = null;      // a batch in flight
  let batchPlan = null;
  let editorOpen = false;
  /* Settings stays open across a repaint. Every change to it re-estimates
     and repaints, and `paint()` rebuilds the panel -- so a `<details>` that
     does not remember it was open snaps shut on each keystroke, which is
     exactly when somebody is in the middle of using it. */
  let paramsOpen = false;
  let savingBad = false;
  let banking = false;
  let hoverEv = null;    // the tick under the pointer on the raster
  let dark = true;

  /* `api`, `apiPost`, `el`, `toast`, `setView` and `reportClientError` are
     module-level globals in core.js, not properties of BARRY -- BARRY is a
     `const`, so it is not a property of `window` either. `clock` is a local
     in every module that wants one, and this is this module's. */
  const clock = (t) => {
    if (t == null) return '—';
    const s = Math.max(0, Number(t));
    const m = Math.floor(s / 60);
    return m + ':' + String((s - m * 60).toFixed(2)).padStart(5, '0');
  };

  /* ---------------------------------------------------------------- paint */

  /* Fails CLOSED. Anything that repaints the toolkit calls this, and a
     guard written as `!==` let a stale timer paint Doppler's report over
     whatever tool had since been opened. */
  function paint() {
    if (!BARRY.views.toolkit || BARRY.views.toolkit.tool() !== 'doppler') {
      return;
    }
    const host = document.getElementById('tkResult');
    if (!host) return;
    dark = !!(BARRY.state && BARRY.state.dark !== false);
    host.innerHTML = '';

    host.appendChild(head());
    /* Where and how many (constitution §6d). Doppler runs only on the
       VACC, so there is no Where to choose -- the bar shows How many, and
       says why nothing can run when the VACC is not set up. One recording
       and many used to be on screen together, one under the other. */
    host.appendChild(BARRY.ui.runBar({
      modes: { vacc: ['one', 'many'] },
      where: 'vacc', count: q.count,
      onChange: (w, c) => { q.count = c; paint(); },
    }));
    if (q.count === 'many') {
      host.appendChild(batchCard());
      host.appendChild(reviewCard());
    } else {
      if (!q.gid) openOnSomething();
      host.appendChild(pickCard());
      if (est) host.appendChild(planCard());
      if (job) host.appendChild(stageCard());
      if (res) host.appendChild(reportCard());
      if (res) host.appendChild(bankCard());
      host.appendChild(reviewCard());
    }

    if (res) {
      // Twice on purpose: now, so a repaint that is not a layout change
      // draws immediately, and again next frame, when the canvases have
      // been given their real width by the grid.
      drawPlots();
      requestAnimationFrame(drawPlots);
    }
    if (job && !poll) startPoll();
  }

  function head() {
    return BARRY.ui.stepHeader({
      title: 'Doppler',
      step: BARRY.ui.stepOf('doppler'),
      blurb: 'Interictal discharges by line length, on the cluster. The '
           + 'detector is Kleen’s LLspikedetector, checked event for '
           + 'event against the MATLAB it came from.',
    });
  }

  /* ------------------------------------------------------- 1. a recording */

  /* A recording this computer can open: Doppler reads the channel list
     here before it sends anything, so a recording with no reachable path
     has nothing to run. */
  const rows = () => (BARRY.views.toolkit.registryRows &&
                      BARRY.views.toolkit.registryRows()) || [];
  const usable = (r) => ((r.here || []).length ? true
    : 'None of this recording’s paths are reachable from this computer, so '
      + 'its channel list cannot be read and there is nothing to send.');

  function choose(r) {
    q.gid = r ? r.gid : null;
    q.row = r || null;
    /* `here[0]`, not `path`. A registry row carries the paths reachable
       from THIS machine and the field is called `here`; asking for
       `path` returns undefined for every recording. */
    q.path = r ? ((r.here || [])[0] || null) : null;
    // Left-out channels belong to the recording they were chosen on.
    // CSC12 on the next one is a different wire.
    q.exclude = []; q.preset = 'all';
    reset();
  }

  /* Open on something workable, never on nothing (§6e). State only: the
     estimate is asked for after, and repaints when it lands. */
  function openOnSomething() {
    const g = BARRY.ui.openOn(rows(), usable, null);
    const r = g && rows().find((x) => x.gid === g);
    if (!r) return;
    choose(r);
    refreshEstimate().then(paint);
  }

  function pickCard() {
    const box = el('div', { class: 'card' });
    box.appendChild(BARRY.ui.pickRecording({
      rows: rows(),
      usable,
      value: q.gid,
      emptyText: 'No recording Jarvis knows about can be opened from this '
               + 'computer, so there is no channel list to send.',
      onpick: (r) => {
        choose(r);
        refreshEstimate().then(paint);
        paint();
      },
    }));
    return box;
  }

  /* ------------------------------------------- 2 and 3. channels, settings */

  function planCard() {
    const p = (est && est.plan) || {};
    const box = el('div', { class: 'card' }, [
      el('div', { class: 'section-label',
        text: '2. What it will read' }),
    ]);

    /* A recording in more than one piece, said before anything is
       submitted. Reading only part one reports a rate for a third of a
       recording and looks entirely healthy doing it. */
    if (est && est.split) {
      box.appendChild(el('p', { class: 'warn-line', text: est.split }));
    }

    box.appendChild(selection());
    box.appendChild(params());

    const c = (est && est.continuity) || {};
    if (c.n_segments > 1) {
      box.appendChild(el('p', { class: 'hint quiet', style: 'max-width:78ch',
        text: 'This recording is in ' + c.n_segments + ' pieces with '
            + (Math.round((c.seconds_lost || 0) * 10) / 10) + ' s missing '
            + 'between them. Detection runs on the pieces joined end to '
            + 'end, which is what the line-length transform has always been '
            + 'given; the times that come back are converted to the '
            + 'recording’s own clock, so a gap never becomes a lie '
            + 'about when something happened.' }));
    }

    box.appendChild(el('div', { class: 'tk-actions' }, [
      vaccSentence(),
      el('span', { class: 'spacer' }),
      job ? el('button', { class: 'btn ghost', text: 'Cancel',
        onclick: cancel }) : null,
      runButton(),
    ].filter(Boolean)));
    return box;
  }

  function vaccOn() {
    return !!(BARRY.vacc && (BARRY.vacc.last || {}).configured);
  }

  function runButton() {
    const v = (est && est.vacc) || {};
    const why = !vaccOn()
      ? 'No cluster is configured on this computer.'
      : (!v.can ? (v.reason || 'The cluster cannot reach this recording.')
                : ('Runs on ' + (v.remote || 'the cluster')));
    return el('button', {
      class: 'btn',
      text: job ? 'Running…' : 'Run on the VACC',
      // Disabled with the reason ON it rather than hidden: a control that
      // vanishes teaches nothing.
      disabled: (job || !vaccOn() || !v.can || (est && est.split))
        ? 'disabled' : null,
      title: why,
      onclick: () => run(false),
    });
  }

  function vaccSentence() {
    const v = (est && est.vacc) || {};
    if (!vaccOn()) {
      return el('div', { class: 'hint quiet vacc-why',
        text: 'Doppler reads every channel of the whole recording at once, '
            + 'so it runs on the cluster. No cluster is configured here.' });
    }
    if (!v.can) {
      return el('div', { class: 'hint quiet vacc-why',
        text: v.reason || '' });
    }
    const there = Math.max(1, Math.round(v.seconds || 0));
    const qd = v.queued ? (', ' + v.queued + ' ahead of you in the queue')
                        : '';
    // Says plainly when the figure is still a seed rather than something
    // the cluster has actually done.
    const how = v.measured ? ''
      : ' (estimated until the cluster has run one)';
    return el('div', { class: 'hint quiet vacc-why',
      text: 'About ' + there + ' s on VACC' + qd + how
          + '. It reads the recording twice — the threshold is a '
          + 'percentile over every kept channel and is not knowable until '
          + 'all of them have been transformed once.' });
  }

  /* What is being read, said out loud rather than left to be inferred from
     a channel count. Fifty-eight of sixty-four looks exactly like
     sixty-four unless the panel says six were dropped, and what was left
     out is part of the answer rather than a detail of it. */
  function selection() {
    const p = (est && est.plan) || {};
    const all = (est && est.channels) || [];
    const bad = all.filter((c) => c.bad);
    const total = all.length || p.n_channels || 0;
    const box = el('div', { class: 'inc-selection' });

    box.appendChild(el('p', { class: 'inc-sel-head',
      text: p.n_channels + ' of ' + total + ' channel'
          + (total === 1 ? '' : 's') + ' will be read' }));

    /* Both ways round. "None are marked" is a fact about this recording
       too, and a panel that only speaks when something was removed leaves
       you unable to tell that from one that never checked. */
    box.appendChild(el('p', { class: bad.length ? 'hint' : 'hint quiet',
      style: 'max-width:78ch',
      text: bad.length
        ? (bad.length + ' channel' + (bad.length === 1 ? '' : 's')
           + ' marked bad on this recording '
           + (bad.length === 1 ? 'has' : 'have') + ' been unticked — '
           + bad.map((c) => c.label).join(', ')
           + '. They are not read at all, so they cannot start an event or '
           + 'widen one, and they take no part in the threshold.')
        : 'No channels are marked bad on this recording, so every one of '
          + 'them is read.' }));

    box.appendChild(chanEditor(all, bad));
    box.appendChild(excludeEditor(all));
    return box;
  }

  /* ---- leaving channels out of this run --------------------------------

     The presets say what is READ, and everything else is left out. "Evens"
     meaning "read the evens" rather than "leave out the evens" is the
     reading the button can be pressed with confidence under, and the line
     under it says the other half out loud so nobody has to guess which
     way round it went.

     Halves are by channel NUMBER, in probe order -- the first half of the
     numbers, not the first half of whatever the list happens to be sorted
     by today. */
  const PRESETS = [
    ['all', 'Every channel', 'Leave nothing out'],
    ['even', 'Evens', 'Read the even-numbered channels only'],
    ['odd', 'Odds', 'Read the odd-numbered channels only'],
    ['first', 'First half', 'Read the lower half of the channel numbers'],
    ['second', 'Second half', 'Read the upper half of the channel numbers'],
  ];

  function presetKeeps(id, all) {
    const nums = all.map((c) => Number(c.number)).sort((a, b) => a - b);
    const half = Math.ceil(nums.length / 2);
    if (id === 'even') return new Set(nums.filter((n) => n % 2 === 0));
    if (id === 'odd') return new Set(nums.filter((n) => n % 2 === 1));
    if (id === 'first') return new Set(nums.slice(0, half));
    if (id === 'second') return new Set(nums.slice(half));
    return new Set(nums);
  }

  function applyPreset(id) {
    const all = (est && est.channels) || [];
    const keep = presetKeeps(id, all);
    q.preset = id;
    q.exclude = all.map((c) => Number(c.number)).filter((n) => !keep.has(n));
    reset();
    refreshEstimate().then(paint);
    paint();
  }

  function toggleExclude(number) {
    const n = Number(number);
    const set = new Set(q.exclude);
    if (set.has(n)) set.delete(n); else set.add(n);
    q.exclude = Array.from(set).sort((a, b) => a - b);
    q.preset = q.exclude.length ? 'custom' : 'all';
    reset();
    refreshEstimate().then(paint);
    paint();
  }

  function excludeEditor(all) {
    const out = new Set(q.exclude);
    const bad = new Set(all.filter((c) => c.bad).map((c) => Number(c.number)));
    const wrap = el('div', { class: 'dop-exclude' }, [
      el('div', { class: 'section-label', text: 'Leave out for this run only' }),
    ]);

    /* A preset that would leave nothing to read is disabled with the
       reason on it, rather than offered and then refused by the server.
       On a recording with no odd-numbered files, "Odds" is exactly that. */
    const segBox = el('div', { class: 'seg dop-presets' });
    for (const [id, label, title] of PRESETS) {
      const keep = presetKeeps(id, all);
      const readable = Array.from(keep).filter((n) => !bad.has(n)).length;
      segBox.appendChild(el('button', {
        class: q.preset === id ? 'active' : '',
        text: label,
        title: readable ? title
          : 'Nothing would be left to read: every channel it keeps is '
            + 'already marked bad, or is not in this recording.',
        disabled: readable ? null : 'disabled',
        onclick: () => { if (q.preset !== id) applyPreset(id); },
      }));
    }
    wrap.appendChild(segBox);

    const grid = el('div', { class: 'inc-chan-grid' });
    for (const c of all) {
      const n = Number(c.number);
      const isBad = bad.has(n);
      grid.appendChild(el('label', {
        class: 'inc-chan' + (isBad ? ' bad' : '') + (out.has(n) ? ' off' : ''),
        title: isBad ? c.label + ' is marked bad, so it is not read anyway'
          : (out.has(n) ? c.label + ' is left out of this run'
                        : c.label + ' is read in this run'),
      }, [
        el('input', {
          type: 'checkbox',
          checked: (!isBad && !out.has(n)) ? 'checked' : null,
          disabled: isBad ? 'disabled' : null,
          onchange: () => toggleExclude(n),
        }),
        el('span', { text: c.label }),
      ]));
    }
    wrap.appendChild(grid);

    const left = all.filter((c) => out.has(Number(c.number))
                                   && !bad.has(Number(c.number)));
    wrap.appendChild(el('p', { class: left.length ? 'hint' : 'hint quiet',
      style: 'max-width:78ch',
      text: left.length
        ? (left.length + ' left out of this run: '
           + left.map((c) => c.label).join(', ')
           + '. They are not read, take no part in the threshold, and '
           + 'nothing about them is written to the recording \u2014 the '
           + 'next run starts with every channel again. The report and the '
           + 'bank note both say which were left out.')
        : 'Nothing left out beyond the bad channels. Leaving channels out '
          + 'here changes this run only; marking one bad above changes the '
          + 'recording for every tool.' }));
    return wrap;
  }

  /* Putting a channel back, or taking one out.

     The tick writes through to the recording's own record -- the same one
     the trace view reads and every other tool honours -- rather than to a
     copy held here, so a channel marked bad in either place is bad in
     both. */
  function chanEditor(all, bad) {
    const d = el('details', {
      class: 'inc-chan-edit', open: editorOpen ? 'open' : null,
      ontoggle: (e) => { editorOpen = e.target.open; },
    }, [
      el('summary', { text: 'Add or remove channels, and run again' }),
      el('p', { class: 'hint quiet', style: 'max-width:74ch',
        text: 'Unticking a channel marks it bad for this recording '
            + 'everywhere. Changing it discards the run on purpose: every '
            + 'event came out of reading a particular set of channels, and '
            + 'a result sitting under a selection it no longer matches is '
            + 'the kind of thing that gets banked by mistake.' }),
    ]);
    const grid = el('div', { class: 'inc-chan-grid' });
    for (const c of all) {
      grid.appendChild(el('label', {
        class: 'inc-chan' + (c.bad ? ' bad' : ''),
        title: c.bad ? c.label + ' is marked bad and is not read'
                     : c.label + ' is read',
      }, [
        el('input', {
          type: 'checkbox', checked: c.bad ? null : 'checked',
          disabled: savingBad ? 'disabled' : null,
          onchange: (e) => setBad(c.number, !e.target.checked),
        }),
        el('span', { text: c.label }),
      ]));
    }
    d.appendChild(grid);
    d.appendChild(el('div', { class: 'tk-actions' }, [
      el('button', { class: 'btn ghost sm', text: 'Put them all back',
        disabled: (savingBad || !bad.length) ? 'disabled' : null,
        onclick: () => setBadSet([]) }),
      savingBad ? el('span', { class: 'hint quiet', text: 'Saving…' })
                : null,
    ].filter(Boolean)));
    return d;
  }

  function setBad(number, bad) {
    const now = new Set(((est && est.channels) || [])
      .filter((c) => c.bad).map((c) => Number(c.number)));
    if (bad) now.add(Number(number)); else now.delete(Number(number));
    setBadSet(Array.from(now));
  }

  async function setBadSet(numbers) {
    if (!q.path || savingBad) return;
    savingBad = true; paint();
    try {
      await apiPost('/api/session/bad-for-path', {
        path: q.path,
        bad_channels: numbers.map(Number).sort((a, b) => a - b),
      });
    } catch (e) {
      savingBad = false; paint();
      toast(e.message, 'err', 9000);
      return;
    }
    savingBad = false;
    reset();            // the run was made from a different set of channels
    editorOpen = true;  // survives the repaint, so you can untick two
    await refreshEstimate();
    paint();
  }

  const FIELDS = [
    { key: 'llw_s', label: 'Line-length window', unit: 's', step: 0.005,
      mname: 'llw',
      why: 'How much signal each line-length value is measured over. '
         + 'Shorter favours sharper things.' },
    { key: 'prc', label: 'Threshold', unit: 'percentile', step: 0.05,
      mname: 'prc',
      why: 'Where the bar sits in the distribution of line-length values, '
         + 'pooled across every channel that is read.' },
  ];

  function params() {
    const changed = q.llw_s !== DEFAULTS.llw_s || q.prc !== DEFAULTS.prc
                 || !!q.notch_hz || q.band_on;
    const d = el('details', {
      class: 'incisor-params', open: paramsOpen ? 'open' : null,
      ontoggle: (e) => { paramsOpen = e.target.open; },
    }, [
      el('summary', {}, [
        el('span', { text: '3. Settings' }),
        el('span', { class: changed ? 'inc-param-tag on' : 'inc-param-tag',
          text: changed ? 'changed' : 'the detector’s own defaults' }),
      ]),
    ]);
    const grid = el('div', { class: 'wiz-grid' });
    for (const f of FIELDS) {
      grid.appendChild(BARRY.ui.field({
        label: f.label + ' (' + f.unit + ')',
        hint: f.why + '  MATLAB calls it ' + f.mname + '.',
        control: el('input', {
          type: 'number', class: 'num', step: f.step, value: q[f.key],
          onchange: (e) => {
            const v = Number(e.target.value);
            if (!isFinite(v) || v <= 0) return;
            q[f.key] = v;
            reset();
            refreshEstimate().then(paint);
          },
        }),
      }));
    }
    d.appendChild(grid);

    /* FILTERING IS OFF BY DEFAULT, and the reason is on the control rather
       than in a document nobody opens. The original detector does none, so
       an unfiltered run is the one that can be held against it. */
    d.appendChild(el('p', { class: 'hint quiet', style: 'max-width:78ch',
      text: 'The original detector does no filtering at all, so nothing is '
          + 'filtered here unless you ask. An unfiltered run is the one '
          + 'that reproduces the numbers the lab’s MATLAB produces; '
          + 'anything else is a different question, worth asking, and '
          + 'worth banking as its own run so the two can be compared.' }));

    d.appendChild(el('label', { class: 'toggle' }, [
      el('input', {
        type: 'checkbox', checked: q.notch_hz ? 'checked' : null,
        onchange: (e) => {
          q.notch_hz = e.target.checked ? 60 : null;
          reset(); refreshEstimate().then(paint); paint();
        },
      }),
      el('span', { text: 'Notch 60 Hz and its harmonics first' }),
    ]));
    d.appendChild(el('p', { class: 'hint quiet', style: 'max-width:78ch',
      text: 'Mains sits inside the band a line-length transform is most '
          + 'sensitive to, so a channel with more of it produces more '
          + 'events for no physiological reason.' }));

    d.appendChild(el('label', { class: 'toggle' }, [
      el('input', {
        type: 'checkbox', checked: q.band_on ? 'checked' : null,
        onchange: (e) => {
          q.band_on = e.target.checked;
          reset(); refreshEstimate().then(paint); paint();
        },
      }),
      el('span', { text: 'Band-pass before the transform' }),
    ]));
    if (q.band_on) {
      d.appendChild(el('div', { class: 'wiz-grid' }, [
        BARRY.ui.field({ label: 'Low (Hz)', inline: true,
          control: el('input', { type: 'number', class: 'num', step: 1,
            value: q.band_lo,
            onchange: (e) => { q.band_lo = Number(e.target.value);
                               reset(); refreshEstimate().then(paint); } }) }),
        BARRY.ui.field({ label: 'High (Hz)', inline: true,
          control: el('input', { type: 'number', class: 'num', step: 5,
            value: q.band_hi,
            onchange: (e) => { q.band_hi = Number(e.target.value);
                               reset(); refreshEstimate().then(paint); } }) }),
      ]));
    }

    if (changed) {
      d.appendChild(el('div', { class: 'tk-actions' }, [
        el('button', { class: 'btn ghost sm',
          text: 'Back to the detector’s defaults',
          onclick: () => {
            q.llw_s = DEFAULTS.llw_s; q.prc = DEFAULTS.prc;
            q.notch_hz = null; q.band_on = false;
            reset(); refreshEstimate().then(paint); paint();
          } }),
      ]));
    }
    return d;
  }

  /* ------------------------------------------------------------ the run */

  function body(extra) {
    const b = {
      path: q.path,
      llw_s: q.llw_s,
      prc: q.prc,
      notch_hz: q.notch_hz,
      band: q.band_on ? [q.band_lo, q.band_hi] : null,
    };
    /* Only when something is left out, and as INDICES because that is what
       the spec takes -- translated from the numbers here, at the last
       moment, from the channel list this recording actually has. The
       channel set is in the cache key, so a different set is a different
       question and is never answered from another one's result. */
    if (q.exclude.length && est && est.channels) {
      const out = new Set(q.exclude);
      b.channels = est.channels
        .filter((c) => !out.has(Number(c.number)))
        .map((c) => Number(c.index));
      b.left_out = q.exclude.slice();
      b.preset = q.preset;
    }
    return Object.assign(b, extra || {});
  }

  function reset() {
    res = null; snips = null; job = null; hoverEv = null;
    if (poll) { clearInterval(poll); poll = null; }
  }

  async function refreshEstimate() {
    if (!q.path) { est = null; return; }
    try {
      est = await apiPost('/api/doppler/estimate', body());
    } catch (e) {
      est = null;
      reportClientError('doppler.estimate', e.message, q.path);
    }
  }

  async function run(force) {
    if (!q.path || job) return;
    let started;
    try {
      started = await apiPost('/api/doppler/scan', body({ where: 'vacc',
        force: !!force }));
    } catch (e) {
      toast(e.message, 'err', 9000);
      return;
    }
    if (started.cached) { adopt(started.result); paint(); return; }
    job = started.job;
    if (BARRY.vaccBusy) BARRY.vaccBusy.start();
    paint();
  }

  function startPoll() {
    poll = setInterval(async () => {
      let got;
      try {
        got = await api('/api/cfc/job/' + job.id);
      } catch (e) { return; }
      job = got.job;
      paintStages();
      if (job.status === 'running') return;
      clearInterval(poll); poll = null;
      const done = job;
      job = null;
      if (BARRY.vaccBusy) BARRY.vaccBusy.stop();
      if (done.status === 'done') {
        try {
          const r = await api('/api/cfc/result/' + done.id);
          adopt(r.result);
          /* Announced even when you are not looking at this tool. A cluster
             job can sit in the queue long enough that nobody is watching
             the tab it was started from. */
          toast('Doppler found ' + (r.result || {}).n + ' IEDs on '
                + ((q.row || {}).label || 'that recording') + '.', 'ok', 8000);
        } catch (e) {
          toast(e.message, 'err', 9000);
        }
      } else if (done.status === 'canceled') {
        toast('The run was cancelled.', 'warn', 5000);
      } else {
        toast(done.error || 'The run failed.', 'err', 12000);
      }
      loadReviews(true);
      paint();
    }, 700);
  }

  async function cancel() {
    if (!job) return;
    try { await apiPost('/api/cfc/job/' + job.id + '/cancel', {}); }
    catch (e) { /* the poll will notice */ }
  }

  function adopt(out) {
    res = out || null;
    snips = null;
    if (res) fetchSnippets();
  }

  async function fetchSnippets() {
    try {
      const got = await apiPost('/api/doppler/snippets', body());
      snips = got.snippets || null;
    } catch (e) { snips = null; }
  }

  /* Stage weights, so a queued job's bar does not stall at 2%. The queue is
     the long pole and is weighted as such. */
  const WEIGHT = { 'ied read': 40, 'ied detect': 2,
                   'vacc stage': 4, 'vacc queue': 30, 'vacc fetch': 2 };

  /* What each stage IS, rather than what it is called in the job. "ied
     read" twice over is not a repeat; it says so, because a bar that
     reaches half and starts again reads as a fault. */
  const STAGE_WORDS = {
    'ied read': 'Read every channel, twice',
    'ied detect': 'Transform and threshold',
    'vacc stage': 'Send the code over',
    'vacc queue': 'Waiting for the cluster',
    'vacc fetch': 'Bring the answer back',
  };

  /* Incisor's progress card, not a second one that measures the same.
     The two tools do the same thing on the same cluster and a person
     watching one should not have to learn the other. */
  function stageCard() {
    return el('div', { class: 'card comod-run' }, [
      el('div', { class: 'comod-run-head' }, [
        el('strong', { text: 'Running on the cluster' }),
        el('div', { style: 'flex:1' }),
      ]),
      el('div', { id: 'dopStages', class: 'comod-stages' }),
      el('div', { class: 'comod-total' }, [
        el('div', { class: 'comod-bar' }, [
          el('div', { id: 'dopBarFill', class: 'comod-bar-fill' }),
        ]),
        el('span', { id: 'dopEta', class: 'comod-eta' }),
      ]),
      el('pre', { id: 'dopLog', class: 'dop-log', style: 'display:none' }),
      el('p', { class: 'hint quiet', style: 'max-width:78ch',
        text: 'You can leave this view. The run is on the cluster and does '
            + 'not belong to this page; come back to Doppler and it will '
            + 'still be here, or find it under runs that have landed.' }),
    ]);
  }

  function paintStages() {
    const host = document.getElementById('dopStages');
    if (!host || !job) return;
    host.innerHTML = '';
    let total = 0, done = 0;

    /* IN THE ORDER THEY HAPPEN, not the order the job lists them. `cfc.Job`
       keeps stages in the order of its global STAGES table, where the
       cluster's own stages come last -- so "read every channel" was drawn
       above "waiting for the cluster" and looked skipped. It is not
       skipped: the reading happens INSIDE the cluster job, and this page
       only learns it is done when the answer comes back. */
    const ORDER = ['vacc stage', 'vacc queue', 'ied read', 'ied detect',
                   'vacc fetch'];
    const stages = (job.stages || []).slice().sort(
      (a, b) => ORDER.indexOf(a.name) - ORDER.indexOf(b.name));
    const qs = stages.find((x) => x.name === 'vacc queue');
    const nodeBusy = stages.some((x) => (x.name === 'ied read'
      || x.name === 'ied detect') && x.status === 'running');
    const queued = !!qs && qs.status !== 'done' && !(qs.done >= 1)
                   && !nodeBusy;
    const onNode = nodeBusy || (!!qs && qs.status !== 'done' && qs.done >= 1);
    const inside = (name) => name === 'ied read' || name === 'ied detect';

    for (const s of stages) {
      const w = WEIGHT[s.name] || 1;
      total += w;
      const frac = s.of ? Math.min(1, (s.done || 0) / s.of) : 0;
      done += w * (s.status === 'done' ? 1 : frac);
      const running = s.status === 'running';
      host.appendChild(el('div', {
        class: 'comod-stage' + (running ? ' on' : '')
               + (s.status === 'done' ? ' done' : '')
               + (s.status === 'failed' ? ' bad' : ''),
      }, [
        el('span', { class: 'comod-tick',
          text: s.status === 'done' ? '\u2713' : running ? '\u25b8'
            : s.status === 'failed' ? '\u2717' : '' }),
        el('span', { class: 'comod-stage-name',
          text: s.name === 'vacc queue'
            ? (onNode ? 'Running on a cluster node'
                      : 'Waiting in the cluster\u2019s queue')
            : (STAGE_WORDS[s.name] || s.name) }),
        el('span', { class: 'comod-stage-count',
          // The node's own counts, replayed from its log by
          // `VaccRun.follow`. Until the first line arrives there is nothing
          // to count, and "- / 57,400" would read as a stall.
          text: inside(s.name) && s.status === 'waiting'
            ? (onNode ? 'starting on the node' : 'after the queue')
            : (s.of > 1 ? ((s.status === 'waiting' ? '\u2013'
              : (s.done || 0).toLocaleString()) + ' / '
              + s.of.toLocaleString() + ' ' + (s.unit || '')) : '') }),
        running && s.of > 1
          ? el('div', { class: 'comod-mini' }, [
              el('div', { class: 'comod-mini-fill',
                          style: 'width:' + (frac * 100).toFixed(1) + '%' })])
          : null,
        el('span', { class: 'comod-stage-time',
          text: s.seconds != null ? s.seconds.toFixed(2) + ' s' : '' }),
      ].filter(Boolean)));
    }
    /* What the node printed that was not progress: `module load`, a
       warning, the start of a traceback. Shown because when a cluster run
       goes wrong this is the first thing anybody asks for, and it used to
       mean an ssh and a `cat` by hand. */
    const logBox = document.getElementById('dopLog');
    if (logBox) {
      const lines = job.log || [];
      logBox.textContent = lines.join('\n');
      logBox.style.display = lines.length ? '' : 'none';
    }

    const fill = document.getElementById('dopBarFill');
    if (fill) fill.style.width = (100 * done / Math.max(1, total)) + '%';
    /* NO ETA WHILE QUEUED. How long the queue takes is the cluster's
       business and is deliberately never learned (`_NOLEARN` in cfc.py),
       so the job's own figure leaves it out entirely -- which is how a run
       sitting behind other people's jobs said "about 1 s left". Say what
       is actually known instead: how long it has been waiting. */
    const eta = document.getElementById('dopEta');
    if (eta) {
      const el_s = Number(job.elapsed || 0);
      const since = el_s < 90 ? Math.round(el_s) + ' s'
                              : Math.round(el_s / 60) + ' min';
      eta.textContent = queued
        ? ('queued for ' + since + ' \u2014 the cluster decides when it '
           + 'starts')
        : onNode
          ? ('running on the cluster, ' + since + ' so far')
          : (job.eta_s ? ('about ' + Math.max(1, Math.round(job.eta_s))
                          + ' s left') : '');
    }
  }

  /* ---------------------------------------------------------- the report */

  function reportCard() {
    const p = res.params || {};
    const box = el('div', { class: 'card dop-report' }, [
      el('div', { class: 'section-label', text: 'What came in' }),
    ]);

    box.appendChild(chips());

    box.appendChild(el('div', { class: 'dop-two' }, [
      el('div', {}, [
        BARRY.ui.chip ? el('div', { class: 'section-label',
          text: 'Average waveform' }) : null,
        el('canvas', { id: 'dopProfile' }),
        el('p', { class: 'hint quiet',
          text: 'Mean ± SEM across every event, on the channel that '
              + 'carried the most of them.' }),
      ].filter(Boolean)),
      el('div', {}, [
        el('div', { class: 'section-label',
          text: 'Per-channel participation' }),
        el('canvas', { id: 'dopPerCh' }),
        el('p', { class: 'hint quiet',
          text: 'How many events each channel took part in. A channel on '
              + 'nearly everything is suspect, not busy.' }),
      ]),
    ]));

    box.appendChild(el('div', { class: 'section-label',
      text: 'Where they are' }));
    box.appendChild(el('canvas', { id: 'dopRaster',
      onmousemove: rasterHover, onmouseleave: () => {
        if (hoverEv) { hoverEv = null; drawRaster(); readout(''); }
      }, onclick: rasterClick }));
    box.appendChild(el('div', { id: 'dopRead', class: 'hint quiet',
      text: 'One line per channel, one tick per event. Click a tick to open '
          + 'the recording there.' }));

    for (const w of (res.warnings || [])) {
      box.appendChild(el('p', { class: 'warn-line', text: w }));
    }

    box.appendChild(paramsLine(p));
    const cmp = comparison();
    if (cmp) box.appendChild(cmp);
    return box;
  }

  function chips() {
    const dur = res.duration_s || 1;
    const perMin = res.n / dur * 60;
    const meanCh = res.n
      ? (res.events || []).reduce((a, e) => a + e.n_channels, 0) / res.n
      : 0;
    const p = res.params || {};
    const kept = (p.channels || []).length;
    const excl = (p.excluded || []).length;
    return BARRY.ui.chipRow([
      BARRY.ui.chip(res.n.toLocaleString() + ' IEDs'),
      BARRY.ui.chip((Math.round(perMin * 10) / 10) + ' /min'),
      BARRY.ui.chip((Math.round(meanCh * 10) / 10) + ' channels each'),
      BARRY.ui.chip(kept + ' of ' + (kept + excl) + ' channels read'),
      BARRY.ui.chip(Math.round(dur) + ' s'),
    ]);
  }

  function paramsLine(p) {
    const bits = [
      p.band ? ('band-pass ' + p.band[0] + '–' + p.band[1] + ' Hz')
             : 'no band-pass',
      p.notch_hz ? ('notched at ' + p.notch_hz + ' Hz') : 'no notch',
      'line-length window ' + (p.llw_s * 1000) + ' ms',
      'threshold at the ' + p.prc + 'th percentile (' + p.threshold + ')',
      (p.channels || []).length + ' channels',
      'stamped at the ' + p.stamp,
      'events closer than ' + (p.merge_s * 1000) + ' ms merged',
      'shorter than ' + (p.min_event_s * 1000) + ' ms dropped',
    ];
    const d = el('details', { class: 'dop-params' }, [
      el('summary', { text: 'Ran with: ' + bits.slice(0, 3).join(' · ')
                          + ' …' }),
    ]);
    d.appendChild(el('p', { class: 'hint', style: 'max-width:88ch',
      text: bits.join('. ') + '.' }));
    if ((p.left_out || []).length) {
      d.appendChild(el('p', { class: 'hint quiet', style: 'max-width:88ch',
        text: 'Left out of this run by choice: '
            + p.left_out.map((c) => c.label || ('CSC' + c.number)).join(', ')
            + (p.preset && p.preset !== 'custom' && p.preset !== 'all'
               ? ' (the \u201c' + p.preset + '\u201d preset)' : '')
            + '. Not marked bad; the recording is unchanged.' }));
    }
    if ((p.excluded || []).length) {
      d.appendChild(el('p', { class: 'hint quiet', style: 'max-width:88ch',
        text: 'Left out: '
            + p.excluded.map((c) => c.label || ('CSC' + c.number)).join(', ')
            + ' — marked bad on this recording, so not read at all.' }));
    }
    d.appendChild(el('p', { class: 'hint quiet', style: 'max-width:88ch',
      text: 'Times are seconds from the start of the recording, converted '
          + 'from the joined signal through this recording’s own gap '
          + 'map (' + (p.gap_map_sha || 'no gaps').slice(0, 12) + ').' }));
    return d;
  }

  /* Held against the last run banked on this recording. "v2, a different
     filter" is only readable if something says what changed. */
  function comparison() {
    const prev = ((reviews || []).find(
      (r) => r.gid === q.gid && r.params_hash !== (res.params || {}).hash
             && (r.banked || []).length) || null);
    if (!prev || !prev.n || prev.n === res.n) return null;
    const d = res.n - prev.n;
    return el('p', { class: 'hint',
      text: 'Against ' + (prev.banked[0].name || 'the last banked run')
          + ' on this recording: ' + prev.n.toLocaleString() + ' → '
          + res.n.toLocaleString() + ' ('
          + (d > 0 ? '+' : '') + d.toLocaleString() + ').' });
  }

  /* ------------------------------------------------------------ drawing */

  function tok(name, fb) { return BARRY.token(name, fb); }

  function canvasFor(id, h) {
    const cv = document.getElementById(id);
    if (!cv || !cv.parentNode) return null;
    cv.style.width = '100%';
    const w = Math.max(160, Math.round(
      cv.clientWidth || cv.getBoundingClientRect().width
      || cv.parentNode.clientWidth));
    const dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    cv.style.height = h + 'px';
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    return { cv, g, W: w, H: h };
  }

  function drawPlots() {
    if (!res) return;
    try { drawProfile(); drawPerCh(); drawRaster(); }
    catch (e) { reportClientError('doppler.draw', e.message, q.path); }
  }

  /* Mean +/- SEM, the band SHADED rather than the trace cropped to it --
     the same idiom X-ray uses, and for the same reason: a picture of only
     the middle of the spread cannot answer how wide the spread is. */
  function drawProfile() {
    const c = canvasFor('dopProfile', 190);
    if (!c) return;
    const prof = res.profile || {};
    const mean = prof.mean || [], sem = prof.sem || [], ms = prof.ms || [];
    if (!mean.length || !ms.length) { empty(c, 'No events to average.'); return; }

    // The channel that carried the most events: one curve, not thirty-two.
    let best = 0, bestN = -1;
    (res.per_channel || []).forEach((r, i) => {
      if (r.n > bestN) { bestN = r.n; best = i; }
    });
    const m = mean[best] || [], s = sem[best] || [];
    if (!m.length) { empty(c, 'No events to average.'); return; }

    const P = { l: 46, r: 10, t: 8, b: 24 };
    const plotW = Math.max(10, c.W - P.l - P.r);
    const plotH = Math.max(10, c.H - P.t - P.b);
    let lo = Infinity, hi = -Infinity;
    for (let i = 0; i < m.length; i++) {
      lo = Math.min(lo, m[i] - (s[i] || 0));
      hi = Math.max(hi, m[i] + (s[i] || 0));
    }
    const pad = (hi - lo) * 0.08 || 1;
    lo -= pad; hi += pad;
    const sx = (i) => P.l + (i / Math.max(1, m.length - 1)) * plotW;
    const sy = (v) => P.t + plotH - ((v - lo) / (hi - lo)) * plotH;

    frame(c, P, plotW, plotH, lo, hi, 'µV');

    // zero on the time axis -- where the stamp is
    const g = c.g;
    const mid = sx((m.length - 1) / 2);
    g.strokeStyle = tok('--border', '#555');
    g.setLineDash([3, 3]);
    g.beginPath(); g.moveTo(mid, P.t); g.lineTo(mid, P.t + plotH); g.stroke();
    g.setLineDash([]);

    const col = tok('--accent', '#E5A823');
    g.fillStyle = col; g.globalAlpha = 0.20;
    g.beginPath();
    for (let i = 0; i < m.length; i++) g.lineTo(sx(i), sy(m[i] + (s[i] || 0)));
    for (let i = m.length - 1; i >= 0; i--) {
      g.lineTo(sx(i), sy(m[i] - (s[i] || 0)));
    }
    g.closePath(); g.fill(); g.globalAlpha = 1;

    g.strokeStyle = col; g.lineWidth = 2;
    g.beginPath();
    for (let i = 0; i < m.length; i++) g.lineTo(sx(i), sy(m[i]));
    g.stroke(); g.lineWidth = 1;

    g.fillStyle = tok('--text-3', '#888');
    g.font = '10px system-ui';
    g.textAlign = 'center';
    g.fillText(ms[0] + ' ms', P.l + 16, c.H - 8);
    g.fillText(ms[ms.length - 1] + ' ms', P.l + plotW - 16, c.H - 8);
    g.textAlign = 'left';
    const lab = ((res.per_channel || [])[best] || {}).label
             || ('CSC' + ((prof.channels || [])[best]));
    g.fillText(lab + ', n=' + (prof.n || 0), P.l + 4, P.t + 12);
  }

  function drawPerCh() {
    const c = canvasFor('dopPerCh', 190);
    if (!c) return;
    const rows = res.per_channel || [];
    if (!rows.length) { empty(c, 'Nothing was read.'); return; }
    const P = { l: 46, r: 10, t: 8, b: 24 };
    const plotW = Math.max(10, c.W - P.l - P.r);
    const plotH = Math.max(10, c.H - P.t - P.b);
    const hi = Math.max(1, ...rows.map((r) => r.n));
    frame(c, P, plotW, plotH, 0, hi, 'events');
    const g = c.g;
    const step = plotW / rows.length;
    const suspect = 0.90 * (res.n || 1);
    rows.forEach((r, i) => {
      const h = (r.n / hi) * plotH;
      // A suspect channel is coloured as a warning, not as a winner: the
      // tallest bar here is the thing you should distrust first.
      g.fillStyle = r.n >= suspect ? tok('--warn', '#E5A823')
                                   : tok('--accent', '#3b82f6');
      g.fillRect(P.l + i * step + 1, P.t + plotH - h,
                 Math.max(1, step - 2), h);
    });
    g.fillStyle = tok('--text-3', '#888');
    g.font = '10px system-ui';
    g.textAlign = 'center';
    g.fillText(rows[0].label || ('CSC' + rows[0].number), P.l + step / 2,
               c.H - 8);
    const last = rows[rows.length - 1];
    g.fillText(last.label || ('CSC' + last.number),
               P.l + plotW - step / 2, c.H - 8);
    g.textAlign = 'left';
  }

  const RASTER_ROW = 13;

  /* One line per channel, one tick per event on the channels that took
     part. An EXCLUDED channel keeps its row and draws a dimmed rule saying
     so, rather than vanishing: a missing row and a silent row are different
     facts and a reader cannot tell them apart from a gap. */
  function drawRaster() {
    const all = (est && est.channels) || [];
    const rows = all.length ? all : (res.per_channel || []);
    const h = Math.max(80, rows.length * RASTER_ROW + 34);
    const c = canvasFor('dopRaster', h);
    if (!c) return;
    const P = { l: 52, r: 10, t: 6, b: 22 };
    const plotW = Math.max(10, c.W - P.l - P.r);
    const g = c.g;
    const dur = res.duration_s || 1;
    const byNum = {};
    for (const r of (res.per_channel || [])) byNum[Number(r.number)] = r;

    g.font = '9px system-ui';
    g.textBaseline = 'middle';
    rows.forEach((r, i) => {
      const y = P.t + i * RASTER_ROW + RASTER_ROW / 2;
      const num = Number(r.number);
      const read = !!byNum[num];
      g.fillStyle = tok('--text-3', '#6f8c7d');
      g.textAlign = 'right';
      g.fillText(r.label || ('CSC' + num), P.l - 6, y);
      g.strokeStyle = tok('--border', '#333');
      if (!read) {
        g.setLineDash([3, 4]);
        g.beginPath(); g.moveTo(P.l, y); g.lineTo(P.l + plotW, y); g.stroke();
        g.setLineDash([]);
        g.fillStyle = tok('--text-3', '#6f8c7d');
        g.textAlign = 'left';
        // WHICH kind of absent. A bad channel is a fact about the
        // recording; a left-out one is a choice about this run.
        const lo = ((res.params || {}).left_out || [])
          .some((c) => Number(c.number) === num);
        g.fillText(lo ? 'left out of this run' : 'bad', P.l + 6, y - 5);
        return;
      }
      g.globalAlpha = 0.35;
      g.beginPath(); g.moveTo(P.l, y); g.lineTo(P.l + plotW, y); g.stroke();
      g.globalAlpha = 1;
    });

    const rowOf = {};
    rows.forEach((r, i) => { rowOf[Number(r.number)] = i; });
    const evs = res.events || [];
    g.strokeStyle = tok('--accent', '#E5A823');
    for (let k = 0; k < evs.length; k++) {
      const e = evs[k];
      const x = P.l + (e.start / dur) * plotW;
      const on = (hoverEv === k);
      g.globalAlpha = on ? 1 : 0.6;
      g.strokeStyle = on ? tok('--ok', '#2f9e6e') : tok('--accent', '#E5A823');
      g.lineWidth = on ? 2 : 1;
      for (const num of (e.channels || [])) {
        const i = rowOf[Number(num)];
        if (i == null) continue;
        const y = P.t + i * RASTER_ROW + RASTER_ROW / 2;
        g.beginPath();
        g.moveTo(Math.round(x) + 0.5, y - 4);
        g.lineTo(Math.round(x) + 0.5, y + 4);
        g.stroke();
      }
    }
    g.globalAlpha = 1; g.lineWidth = 1;

    g.fillStyle = tok('--text-3', '#888');
    g.textAlign = 'left';
    g.fillText('0 s', P.l, c.H - 9);
    g.textAlign = 'right';
    g.fillText(Math.round(dur) + ' s', P.l + plotW, c.H - 9);
    g.textAlign = 'left';
  }

  function rasterAt(e) {
    if (!res) return null;
    const cv = document.getElementById('dopRaster');
    if (!cv) return null;
    const r = cv.getBoundingClientRect();
    const P = { l: 52, r: 10 };
    const plotW = Math.max(10, r.width - P.l - P.r);
    const t = ((e.clientX - r.left) - P.l) / plotW * (res.duration_s || 1);
    let best = null, bestD = Infinity;
    (res.events || []).forEach((ev, i) => {
      const d = Math.abs(ev.start - t);
      if (d < bestD) { bestD = d; best = i; }
    });
    // Within four pixels, in seconds. A click that is not on a tick should
    // do nothing rather than open the nearest thing a screen away.
    const tol = 4 / plotW * (res.duration_s || 1);
    return (best != null && bestD <= tol) ? best : null;
  }

  function readout(text) {
    const n = document.getElementById('dopRead');
    if (n) {
      n.textContent = text || 'One line per channel, one tick per event. '
                    + 'Click a tick to open the recording there.';
    }
  }

  function rasterHover(e) {
    const i = rasterAt(e);
    if (i === hoverEv) return;
    hoverEv = i;
    drawRaster();
    if (i == null) { readout(''); return; }
    const ev = res.events[i];
    readout('IED ' + (i + 1) + ' of ' + res.n + ' at '
            + clock(ev.start) + ' · ' + ev.n_channels
            + ' channels · ' + Math.round(ev.peak_uv) + ' µV'
            + (ev.near_stitch ? ' · within 125 ms of a join' : ''));
  }

  function rasterClick(e) {
    const i = rasterAt(e);
    if (i == null || !q.path) return;
    const ev = res.events[i];
    BARRY.views.xplore.open(q.path).then((sess) => {
      setView('xplore');
      BARRY.views.xplore.setWindow(0, Math.max(0, ev.start - 0.5), 1.0);
    }).catch((err) => toast(err.message, 'err', 8000));
  }

  function frame(c, P, plotW, plotH, lo, hi, ylab) {
    const g = c.g;
    g.strokeStyle = tok('--border', '#444');
    g.beginPath();
    g.moveTo(P.l, P.t); g.lineTo(P.l, P.t + plotH);
    g.lineTo(P.l + plotW, P.t + plotH);
    g.stroke();
    g.fillStyle = tok('--text-3', '#888');
    g.font = '10px system-ui';
    g.textAlign = 'right';
    g.fillText(fmt(hi), P.l - 5, P.t + 9);
    g.fillText(fmt(lo), P.l - 5, P.t + plotH);
    g.textAlign = 'left';
    g.fillText(ylab, 4, P.t + 9);
  }

  function fmt(v) {
    const a = Math.abs(v);
    if (a >= 1000) return Math.round(v / 100) / 10 + 'k';
    if (a >= 10) return String(Math.round(v));
    return String(Math.round(v * 10) / 10);
  }

  function empty(c, msg) {
    c.g.fillStyle = tok('--text-3', '#888');
    c.g.font = '11px system-ui';
    c.g.textAlign = 'center';
    c.g.fillText(msg, c.W / 2, c.H / 2);
    c.g.textAlign = 'left';
  }

  /* ------------------------------------------------------------- banking */

  function bankCard() {
    const box = el('div', { class: 'card' }, [
      el('div', { class: 'section-label', text: '4. Bank them' }),
      el('p', { class: 'hint', style: 'max-width:78ch',
        text: 'Each run is banked as its own entry under a name you choose, '
            + 'so two filters on the same recording sit side by side and '
            + 'can be compared. Versions inside an entry then mean only '
            + 'what a person did to that list — confirmed in Spotter, '
            + 'reviewed again, lined up in Eye.' }),
      el('div', { class: 'tk-actions' }, [
        el('span', { class: 'spacer' }),
        el('button', { class: 'btn', text: banking ? 'Banking…'
                                                   : 'Bank them',
          disabled: (banking || !res.n) ? 'disabled' : null,
          onclick: bank }),
      ]),
    ]);
    return box;
  }

  async function bank() {
    /* Through the one bank dialog (constitution §6e): a new entry, named,
       with the session already in the name. Who comes from the profile --
       this used to return without a word when nobody was set, so Bank did
       nothing at all -- and the note is the account of how the run was
       made, there to be read and changed before it is filed. */
    const p = res.params || {};
    const r = q.row || {};
    const suggested = BARRY.bankName.suggest(
      r, 'Doppler ' + (p.band ? (p.band[0] + '–' + p.band[1] + ' Hz')
                              : 'unfiltered'));
    let added = null;
    const ok = await BARRY.ui.bankDialog({
      kind: 'entry',
      title: 'Bank ' + res.n.toLocaleString() + ' IEDs from '
             + (r.label || 'this recording') + '?',
      name: suggested,
      note: bankNote(),
      what: 'It goes in as a detector’s output, not as a curated set — '
          + 'nothing is decided about any of them yet, and the next step is '
          + 'confirming them in Spotter.',
      where: 'Filed under ' + [r.project || r.group || 'Unfiled',
                               r.mouse != null ? 'm' + r.mouse : null,
                               r.session != null ? 's' + r.session : null]
        .filter(Boolean).join(' / ') + ' in the Event Bank, as its own entry '
        + 'beside any other run on this recording.',
      okText: 'Bank them',
      onBank: async ({ name, note, who }) => {
        banking = true; paint();
        try {
          /* `channel` is the one the peak was taken from. An event in the
             bank has a channel, not a list of them -- the whitelist in
             `eventbank.add` is deliberate, and a `channels` field would be
             dropped on the way in and would not survive a version restore.
             The full participation stays in Doppler's own vault and
             Spotter reads it back from there. */
          const evs = (res.events || []).map((e) => ({
            start: e.start,
            end: e.end || undefined,
            channel: e.peak_channel,
            amplitude: e.peak_uv,
          }));
          added = await apiPost('/api/bank/add', {
            project: r.project || r.group,
            mouse: r.mouse, session: r.session,
            session_key: r.key, session_loose_key: r.loose_key,
            session_label: r.label, session_path: q.path,
            recording_start: r.start, duration_s: r.duration_s,
            gid: q.gid,
            type: 'ied', type_name: 'IED',
            name,
            note: note || bankNote(),
            events: evs,
            pipeline: 'Doppler (line length)',
            detector: 'LLspikedetector',
            time_basis: 'recording',
            parameters: p,
            added_by: who,
            version_note: 'The detector’s own list, nothing decided about '
                        + 'it yet.',
          });
        } finally {
          banking = false; paint();
        }
      },
    });
    if (!ok || !added) return;
    toast('Banked. Confirm them in Spotter.', 'ok', 7000);
    loadReviews(true);
    paint();
    /* Offered, not taken. Banking and confirming are two steps of a
       bundle and the second one is a sitting somebody chooses to start. */
    const entryId = (added.entry || {}).id || added.id;
    const go = await BARRY.confirm(
      'Confirm them now?',
      el('p', { text: res.n.toLocaleString() + ' candidates are banked. '
          + 'Spotter walks them one at a time.' }),
      'Open Spotter');
    if (go && BARRY.spotter) BARRY.spotter.enter(q.gid, entryId);
  }

  function bankNote() {
    const p = res.params || {};
    return 'Detected by Doppler on the VACC, ' + p.detector + '. '
      + (p.band ? ('Band-passed ' + p.band[0] + '–' + p.band[1] + ' Hz'
                   + (p.notch_hz ? ' after a ' + p.notch_hz + ' Hz notch'
                                 : '') + '. ')
                : 'No filtering, which is what the original detector does. ')
      + 'Line-length window ' + (p.llw_s * 1000) + ' ms, threshold at the '
      + p.prc + 'th percentile of the line-length values pooled over the '
      + (p.channels || []).length + ' channels that were read'
      + ((p.excluded || []).length
         ? ' (' + p.excluded.length + ' marked bad were not read at all, so '
           + 'they neither started events nor took part in the threshold)'
         : '')
      + ((p.left_out || []).length
         ? '. ' + p.left_out.length + ' more were left out of this run by '
           + 'choice (' + p.left_out.map((c) => c.label
                                           || ('CSC' + c.number)).join(', ')
           + '), without marking them bad'
         : '')
      + '. Each stamp is the largest deflection inside the detector’s '
      + 'window, measured only on the channels that took part. Times are '
      + 'seconds from the start of the recording, converted from the joined '
      + 'signal through this recording’s gap map.';
  }

  /* ------------------------------------------------- runs that have landed */

  async function loadReviews(force) {
    if (reviews && !force) return;
    try {
      const got = await api('/api/doppler/reviews');
      reviews = got.reviews || [];
    } catch (e) { reviews = []; }
  }

  function reviewCard() {
    const box = el('div', { class: 'card' }, [
      el('div', { class: 'section-label', text: 'Runs that have landed' }),
    ]);
    if (reviews === null) {
      loadReviews().then(paint);
      BARRY.skeleton.into(box, 'row', 3);
      return box;
    }
    if (!reviews.length) {
      box.appendChild(el('div', { class: 'empty-state',
        text: 'Nothing has been run yet. Pick a recording above and send it '
            + 'to the cluster — a batch of them is at the bottom.' }));
      return box;
    }
    const list = el('div', { class: 'dop-reviews' });
    for (const r of reviews) {
      list.appendChild(el('button', {
        class: 'dop-review', onclick: () => openReview(r),
      }, [
        el('strong', { text: r.label || r.gid }),
        el('span', { text: (r.n || 0).toLocaleString() + ' IEDs' }),
        (r.banked || []).length
          ? BARRY.ui.chip('banked', { kind: 'ok' })
          : BARRY.ui.chip('not banked'),
        (r.warnings || []).length
          ? BARRY.ui.chip(r.warnings.length + ' to look at', { kind: 'warn' })
          : null,
      ].filter(Boolean)));
    }
    box.appendChild(list);
    return box;
  }

  async function openReview(r) {
    if (!r.local) {
      toast('None of that recording’s paths are reachable from this '
            + 'computer, so there is nothing to look at.', 'warn', 9000);
      return;
    }
    q.gid = r.gid; q.path = r.local; q.row = r.row || null;
    const sp = r.spec || {};
    if (sp.llw_s) q.llw_s = sp.llw_s;
    if (sp.prc) q.prc = sp.prc;
    q.notch_hz = sp.notch_hz || null;
    q.band_on = !!sp.band;
    if (sp.band) { q.band_lo = sp.band[0]; q.band_hi = sp.band[1]; }
    reset();
    await refreshEstimate();
    // The answer is already in the vault, so this is a cache hit and not a
    // second way to render a run.
    try {
      const got = await apiPost('/api/doppler/scan', body());
      if (got.cached) adopt(got.result);
    } catch (e) { toast(e.message, 'err', 9000); }
    paint();
  }

  /* --------------------------------------------------------------- batch */

  function batchCard() {
    const box = el('div', { class: 'card' }, [
      el('div', { class: 'section-label', text: 'Many recordings at once' }),
      el('p', { class: 'hint', style: 'max-width:78ch',
        text: 'One array job, so the cluster runs them side by side rather '
            + 'than this computer running them one after another. A '
            + 'recording already answered with these settings is skipped in '
            + 'milliseconds, so a batch that dies halfway costs nothing to '
            + 'start again.' }),
    ]);
    if (batchPlan) {
      box.appendChild(BARRY.ui.chipRow([
        BARRY.ui.chip(batchPlan.n + ' to run'),
        BARRY.ui.chip((batchPlan.already || []).length + ' already done'),
        (batchPlan.blocked || []).length
          ? BARRY.ui.chip(batchPlan.blocked.length + ' cannot',
                          { kind: 'warn' }) : null,
      ].filter(Boolean)));
      for (const b of (batchPlan.blocked || []).slice(0, 6)) {
        box.appendChild(el('p', { class: 'inc-blocked',
          text: (b.label || b.gid) + ' — ' + b.why }));
      }
    }
    if (batch) {
      const rows = el('div', { class: 'inc-batch' });
      for (const m of (batch.members || [])) {
        rows.appendChild(el('div', { class: 'inc-batch-row ' + (m.status || '') }, [
          el('span', { text: m.label || m.id }),
          el('span', { class: 'hint quiet',
            text: m.error || m.step || m.status || '' }),
        ]));
      }
      box.appendChild(rows);
    }
    box.appendChild(el('div', { class: 'tk-actions' }, [
      el('span', { class: 'spacer' }),
      /* The primary is last and names what it will do (§6d), with the
         count once it is known. It was a second ghost button, "Run the
         batch", beside the first. */
      el('button', { class: 'btn ghost', text: 'Check what it would run',
        disabled: !vaccOn() ? 'disabled' : null,
        onclick: planBatch }),
      el('button', { class: 'btn',
        text: batch ? 'Running…'
              : (batchPlan && batchPlan.n
                   ? 'Submit ' + batchPlan.n + ' to VACC' : 'Submit to VACC'),
        disabled: (batch || !batchPlan || !batchPlan.n) ? 'disabled' : null,
        onclick: runBatch }),
    ]));
    return box;
  }

  async function planBatch() {
    try {
      batchPlan = await apiPost('/api/doppler/batch/plan', body());
    } catch (e) { toast(e.message, 'err', 9000); }
    paint();
  }

  async function runBatch() {
    try {
      const started = await apiPost('/api/doppler/batch', body());
      batch = started.job;
      if (BARRY.vaccBusy) BARRY.vaccBusy.start();
      pollBatch();
    } catch (e) { toast(e.message, 'err', 12000); }
    paint();
  }

  function pollBatch() {
    const t = setInterval(async () => {
      let got;
      try { got = await api('/api/cfc/job/' + batch.id); }
      catch (e) { return; }
      batch = got.job;
      paint();
      if (batch.status === 'running') return;
      clearInterval(t);
      if (BARRY.vaccBusy) BARRY.vaccBusy.stop();
      const done = batch; batch = null;
      toast(done.status === 'done'
        ? 'The batch finished.' : (done.error || 'The batch failed.'),
        done.status === 'done' ? 'ok' : 'err', 9000);
      loadReviews(true).then(paint);
    }, 1500);
  }

  /* A poll belongs to the view that started it. Leaving Doppler must not
     leave a timer behind asking the server about a job nobody is looking
     at -- but the JOB is not cancelled, because it is on the cluster and
     does not belong to this page. */
  function onHide() {
    if (poll) { clearInterval(poll); poll = null; }
  }

  return {
    paint, run, reset, onHide,
    _state: () => q,
    // For `_dev/storm.html`: the report's drawing and reading are checkable
    // without waiting forty minutes for the cluster to prove a canvas has
    // ink on it. The detector's own arithmetic is checked against the
    // MATLAB by tools/check_doppler_parity.py, which is where it belongs.
    _adopt: (out) => { res = out || null; snips = null; },
    _res: () => res,
    _draw: drawPlots,
    _rasterAt: rasterAt,
    _bankNote: bankNote,
  };
})();
