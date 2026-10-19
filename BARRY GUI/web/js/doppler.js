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
     3. settings -- the validated Storm method by default (the IED detector
        study's choice), and the lab's MATLAB exactly one switch away, for
        comparing with runs made before it
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
    /* THE VALIDATED DEFAULTS -- the Storm method. Every field is one of
       backend/doppler.py's STORM, which the IED detector study chose: it
       catches every hand-sorted Solid on the ten PTEN recordings with the
       fewest other candidates. Legacy, the lab's MATLAB exactly, is one
       click away in Settings. */
    method: 'storm',
    llw_s: 0.015,
    prc: 99.9,
    notch_hz: 60,
    band_lo: 20,
    band_hi: 300,
    band_on: true,
    car: true,
    min_channels: 7,
    merge_s: 0.3,
    min_event_s: 0.0125,
    detect_on: 'even',
    /* A channel RANGE, by CSC number, applied before everything else: a
       128-channel recording run on CSC1 to CSC64 only. Null is every
       channel. A setting, not a choice about one recording -- it stays
       when the recording changes, and a batch runs every recording with
       it. */
    ch_lo: null,
    ch_hi: null,
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

  /* Each method's own, named once so the "changed" tag and the reset cannot
     drift apart from what the fields start at. These mirror STORM and LEGACY
     in backend/doppler.py; the server fills in the same values when a field
     is not sent, so the two can only disagree about what is DISPLAYED. */
  const METHODS = {
    storm: { llw_s: 0.015, prc: 99.9, notch_hz: 60, band_on: true,
             band_lo: 20, band_hi: 300, car: true, min_channels: 7,
             merge_s: 0.3, min_event_s: 0.0125, detect_on: 'even',
             ch_lo: null, ch_hi: null },
    legacy: { llw_s: 0.040, prc: 99.9, notch_hz: null, band_on: false,
              band_lo: 10, band_hi: 300, car: false, min_channels: 1,
              merge_s: 0.3, min_event_s: 0.025, detect_on: 'all',
              ch_lo: null, ch_hi: null },
  };
  const PARAM_FIELDS = Object.keys(METHODS.storm);

  function useMethod(m) {
    q.method = m;
    Object.assign(q, METHODS[m]);
  }

  function isDefault() {
    const d = METHODS[q.method] || METHODS.storm;
    return PARAM_FIELDS.every((k) => q[k] === d[k]);
  }

  /* The Many picker's state. Nothing is ticked for you: the list is every
     recording the cluster can read, hundreds of them, and one click sending
     all of them is not a default. */
  let vaccList = null;
  let vaccListSeq = 0;
  let vaccFilter = '';
  const picked = new Set();

  let est = null;        // what a run would cost
  let res = null;        // the run on screen
  let snips = null;      // the sample of raw waveforms, fetched once
  let reviews = null;    // runs that have already landed

  /* EVERY RUN ON THE CLUSTER, by job id -- {id, kind: 'one'|'many',
     members: [{gid, label}], path, params, snap}. One map for single runs
     and batches, filled from the server (`/api/doppler/inflight`) whenever
     the panel is shown, so leaving the view or reloading the page does not
     lose a run. The panel used to keep the run it had started in a
     variable and nothing else: leave and come back and it was gone, or it
     kept asking about a job the server had dropped and said "running"
     beside the same run already landed. */
  const flights = new Map();
  let loop = null;       // the one timer that follows them
  let attached = false;  // asked the server since this panel was last shown

  let landedOpen = null; // key of the landed run on screen
  const freshKeys = new Set();   // landed while this panel was watching
  let landedAll = false; // the whole landed list, not the latest few
  let revealNext = false;        // the next report drawn plays its reveal
  let pickRev = 0;       // bumps when ticks change in bulk
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

  /* A stable small number for an object, so "is this the same estimate /
     the same result / the same list as last time" can go in a section's
     signature without writing the whole thing out. */
  const ids = new WeakMap();
  let idn = 0;
  function oid(o) {
    if (!o || typeof o !== 'object') return String(o);
    if (!ids.has(o)) ids.set(o, ++idn);
    return ids.get(o);
  }

  /* Fails CLOSED. Anything that repaints the toolkit calls this, and a
     guard written as `!==` let a stale timer paint Doppler's report over
     whatever tool had since been opened.

     NOTHING IS REBUILT THAT HAS NOT CHANGED. The panel is a list of parts,
     each with a signature of what it shows (`BARRY.ui.sections`); a poll,
     an estimate landing or a tick rebuilds only the parts it touched. It
     used to empty the host and build everything on every call -- the
     batch poll did that every 1.5 s -- which is what "the UI keeps
     reloading" was. */
  function paint() {
    if (!BARRY.views.toolkit || BARRY.views.toolkit.tool() !== 'doppler') {
      return;
    }
    const host = document.getElementById('tkResult');
    if (!host) return;
    dark = !!(BARRY.state && BARRY.state.dark !== false);
    /* Shown afresh -- a reload, or back from another tool, which empties
       the host -- so ask the server what is out on the cluster and what has
       landed meanwhile. */
    if (!host.querySelector(':scope > [data-sec="head"]')) attached = false;
    if (!attached) { attached = true; attach(); }
    if (q.count !== 'many' && !q.gid) openOnSomething();

    const qs = JSON.stringify(paramsBody()) + '|' + q.exclude.join(',')
             + '|' + q.preset;
    const mine = myFlight();
    const list = [
      { key: 'head', sig: 'head', build: head },
      /* Where and how many (constitution §6d). Doppler runs only on the
         VACC, so there is no Where to choose -- the bar shows How many,
         and says why nothing can run when the VACC is not set up. */
      { key: 'bar', sig: [q.count, vaccOn()], build: () => BARRY.ui.runBar({
          modes: { vacc: ['one', 'many'] },
          where: 'vacc', count: q.count,
          onChange: (w, c) => { q.count = c; paint(); },
        }) },
    ];
    if (q.count === 'many') {
      list.push({ key: 'mpick', sig: [oid(vaccList)], build: manyPickCard,
                  update: manyPickUpdate });
      list.push({ key: 'mrun', sig: 'mrun', build: manyRunShell,
                  update: manyRunUpdate });
    } else {
      list.push({ key: 'pick', sig: [q.gid, rows().length], build: pickCard });
      if (est) {
        list.push({ key: 'plan', sig: [q.gid], build: planShell,
                    update: (node) => planUpdate(node, qs, mine) });
      }
      if (mine) {
        list.push({ key: 'stages', sig: mine.id, build: stageCard,
                    update: () => paintStages(mine.snap) });
      }
      if (res) {
        list.push({ key: 'report', sig: [oid(res), (q.row || {}).label],
                    build: reportCard });
        list.push({ key: 'bank', sig: [oid(res), banking], build: bankCard });
      }
    }
    list.push({ key: 'runs', sig: 'runs', build: runsShell,
                update: runsUpdate });

    const built = BARRY.ui.sections(host, list);
    if (built.report) {
      /* Now, so a rebuild draws at once; and next frame, when the grid has
         given the canvases their real width. The reveal plays once, on the
         first of the two. */
      const reveal = revealNext;
      revealNext = false;
      drawPlots(reveal);
      requestAnimationFrame(() => { if (!reveal) drawPlots(false); });
    }
    if (flights.size && !loop) startLoop();
  }

  function head() {
    return BARRY.ui.stepHeader({
      title: 'Doppler',
      step: BARRY.ui.stepOf('doppler'),
      blurb: 'Interictal discharges by line length, on the cluster. By '
           + 'default the validated Storm settings, which caught every '
           + 'hand-sorted IED on the PTEN recordings; the lab’s original '
           + 'MATLAB is one click away in Settings.',
    });
  }

  /* ------------------------------------------------------- 1. a recording */

  /* A recording this computer can open, or one the cluster can read
     (VACC loaded): the run happens on the cluster either way, and the
     channel list of one this computer has no copy of comes over the link. */
  const rows = () => (BARRY.views.toolkit.registryRows &&
                      BARRY.views.toolkit.registryRows()) || [];
  /* The one predicate every picker uses (BARRY.vacc.usableFor); Doppler is
     'cluster' in toolkit.js's READS. */
  const usable = (r) => BARRY.vacc.usableFor('doppler')(r);

  function choose(r) {
    q.gid = r ? r.gid : null;
    q.row = r || null;
    /* Through `reach`, never `path` (a registry row has `here`, not
       `path`, and asking for `path` returns undefined for every one). */
    q.path = r ? BARRY.vacc.reachFor(r, 'doppler').path : null;
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
      emptyText: 'No recording Jarvis knows about is on this computer or '
               + 'VACC loaded, so there is nothing to run. Add the ones '
               + 'found on VACC in Sessions, or upload some.',
      onpick: (r) => {
        choose(r);
        refreshEstimate().then(paint);
        paint();
      },
    }));
    return box;
  }

  /* ------------------------------------------- 2 and 3. channels, settings */

  /* "2. What it will read": one card, three parts inside it that change
     for different reasons -- the channels (the estimate, the exclusions),
     the settings (the parameters) and the run line (the estimate and
     whether a run is on the cluster). Reconciled inside the card, so a run
     starting does not rebuild the settings somebody has open. */
  function planShell() {
    return el('div', { class: 'card' }, [
      el('div', { class: 'section-label', text: '2. What it will read' }),
      el('div', { class: 'dop-plan-parts' }),
    ]);
  }

  function planUpdate(node, qs, mine) {
    const inner = node.querySelector('.dop-plan-parts');
    if (!inner) return;
    BARRY.ui.sections(inner, [
      { key: 'chans', enter: false,
        sig: [oid(est), q.exclude.join(','), q.preset, savingBad],
        build: () => el('div', {}, [
          /* A recording in more than one piece, said before anything is
             submitted. Reading only part one reports a rate for a third
             of a recording and looks entirely healthy doing it. */
          est && est.split ? el('p', { class: 'warn-line', text: est.split })
                           : null,
          selection(),
        ].filter(Boolean)) },
      { key: 'params', enter: false, sig: [qs], build: params },
      { key: 'cont', enter: false, sig: [oid(est)], build: continuityNote },
      { key: 'feed', enter: false, sig: [oid(est)], build: feedPart },
      { key: 'go', enter: false,
        sig: [oid(est), mine ? mine.id : '', vaccOn(), qs],
        build: () => el('div', { class: 'tk-actions dop-actions dop-go' }, [
          vaccSentence(),
          el('span', { class: 'spacer' }),
          mine ? el('button', { class: 'btn ghost', text: 'Cancel',
                                onclick: () => cancel(mine.id) }) : null,
          runButton(mine),
        ].filter(Boolean)) },
    ]);
  }

  /* "Before I run it I want to see the list of channels fed in." Every
     channel by name, in the role the run gives it, right above the run
     button. From the estimate's `feed`, which the server works out by the
     engine's own rules (doppler.feed) from the spec the run will be sent
     -- so this list and what the cluster reads cannot disagree. */
  function feedPart() {
    const f = est && est.feed;
    if (!f) return el('div', {});
    const box = el('div', { class: 'dop-feed' }, [
      el('div', { class: 'dop-feed-top' }, [
        el('div', { class: 'section-label', text: 'What goes in' }),
        el('span', { class: 'hint quiet',
          text: [f.range ? rangeWords(f.range) + ' only' : 'every channel',
                 f.rule === 'all' ? 'detection on every channel read'
                                  : 'detection on the ' + f.rule + ' ones',
                 'bad ones left out'].join(' · ') }),
      ]),
    ]);
    const group = (kind, title, why, labels, chipText) => {
      if (!labels || !labels.length) return;
      box.appendChild(el('div', { class: 'dop-feed-g ' + kind }, [
        el('div', { class: 'dop-feed-h' }, [
          el('strong', { text: title }),
          el('span', { class: 'dop-feed-n', text: String(labels.length) }),
          why ? el('span', { class: 'dop-feed-why', text: why }) : null,
        ].filter(Boolean)),
        el('div', { class: 'dop-feed-chips' },
          (chipText || labels).map((t) => el('span', { class: 'dop-feed-chip',
                                                         text: t }))),
      ]));
    };
    group('det', 'Detected on',
          f.rule === 'all' ? 'every channel read'
                           : 'the ' + f.rule + '-numbered channels read',
          f.detect);
    group('ref', f.car ? 'Read for the common reference only'
                       : 'Read, not detected on',
          f.car ? 'averaged into their probe bank’s reference; detection '
                  + 'does not run on them' : null,
          f.reference);
    group('bad', 'Marked bad, not read', 'on this recording, for every tool',
          f.bad);
    group('left', 'Left out of this run', 'your choice, this run only',
          f.left_out);
    group('nc', 'On a bank marked not connected', 'not read', f.not_connected);
    group('out', 'Outside the range, not read', rangeWords(f.range) + ' only',
          f.out_of_range, runsOf(f.out_of_range));
    return box;
  }

  /* Labels as runs: CSC65 to CSC128 is one chip, not sixty-four. Every
     channel is still in it -- a run is written out, never cut short. */
  function runsOf(labels) {
    const nums = (labels || []).map((l) => Number(String(l).replace(/\D+/g, '')))
      .filter(isFinite).sort((a, b) => a - b);
    const out = [];
    for (let i = 0; i < nums.length;) {
      let j = i;
      while (j + 1 < nums.length && nums[j + 1] === nums[j] + 1) j++;
      out.push(j > i ? 'CSC' + nums[i] + ' to CSC' + nums[j] : 'CSC' + nums[i]);
      i = j + 1;
    }
    return out;
  }

  function continuityNote() {
    const c = (est && est.continuity) || {};
    if (c.pending) {
      /* Only the cluster has this recording: the gaps, and whether it is
         in more than one piece, are checked there as part of the run. */
      return el('p', { class: 'hint quiet', style: 'max-width:78ch',
        text: 'Not on this computer — read off the cluster. ' + (c.note || '')
            + ' A recording in pieces is refused there with the same '
            + 'sentence it gets here.' });
    }
    if (c.n_segments > 1) {
      return el('p', { class: 'hint quiet', style: 'max-width:78ch',
        text: 'This recording is in ' + c.n_segments + ' pieces with '
            + (Math.round((c.seconds_lost || 0) * 10) / 10) + ' s missing '
            + 'between them. Detection runs on the pieces joined end to '
            + 'end, which is what the line-length transform has always been '
            + 'given; the times that come back are converted to the '
            + 'recording’s own clock, so a gap never becomes a lie '
            + 'about when something happened.' });
    }
    return el('div', {});
  }

  function vaccOn() {
    return !!(BARRY.vacc && (BARRY.vacc.last || {}).configured);
  }

  function runButton(mine) {
    const v = (est && est.vacc) || {};
    const why = !vaccOn()
      ? 'No cluster is configured on this computer.'
      : (!v.can ? (v.reason || 'The cluster cannot reach this recording.')
                : ('Runs on ' + (v.remote || 'the cluster')));
    return el('button', {
      class: 'btn',
      text: mine ? 'On the cluster' : 'Run on the VACC',
      // Disabled with the reason ON it rather than hidden: a control that
      // vanishes teaches nothing.
      disabled: (mine || !vaccOn() || !v.can || (est && est.split))
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
    const twice = ((est && est.plan) || {}).passes === 2;
    return el('div', { class: 'hint quiet vacc-why',
      text: 'About ' + human(there) + ' on VACC' + qd + how + '. '
          + (twice
            ? 'It reads the recording twice: the threshold is a percentile '
              + 'over every kept channel and is not knowable until all of '
              + 'them have been transformed once.'
            : 'It reads the recording once, decimating as it goes, and takes '
              + 'the threshold from every detection channel at the end.') });
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
    const rng = chRange();
    for (const c of all) {
      const n = Number(c.number);
      const isBad = bad.has(n);
      // Outside the channel range: not read whatever is ticked here.
      const beyond = !!rng && (n < rng[0] || n > rng[1]);
      grid.appendChild(el('label', {
        class: 'inc-chan' + (isBad ? ' bad' : '') + (out.has(n) ? ' off' : '')
               + (beyond ? ' beyond' : ''),
        title: beyond ? c.label + ' is outside ' + rangeWords(rng)
                        + ', so it is not read'
          : isBad ? c.label + ' is marked bad, so it is not read anyway'
          : (out.has(n) ? c.label + ' is left out of this run'
                        : c.label + ' is read in this run'),
      }, [
        el('input', {
          type: 'checkbox',
          checked: (!isBad && !out.has(n) && !beyond) ? 'checked' : null,
          disabled: (isBad || beyond) ? 'disabled' : null,
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
    d.appendChild(el('div', { class: 'tk-actions dop-actions' }, [
      el('button', { class: 'btn ghost sm', text: 'Put them all back',
        disabled: (savingBad || !bad.length) ? 'disabled' : null,
        onclick: () => setBadSet([]) }),
      savingBad ? el('span', { class: 'hint quiet', text: 'Saving…' })
                : null,
    ].filter(Boolean)));
    return d;
  }

  /* One channel is sent as a change, not as this panel's list with one
     channel different: that list was read when the estimate was, and a
     channel marked in the trace view since then was wiped by it. */
  function setBad(number, bad) {
    const now = new Set(((est && est.channels) || [])
      .filter((c) => c.bad).map((c) => Number(c.number)));
    if (bad) now.add(Number(number)); else now.delete(Number(number));
    // The list too, for a Jarvis older than `add` / `remove`.
    const n = [Number(number)];
    setBadSet(Array.from(now), bad ? { add: n } : { remove: n });
  }

  async function setBadSet(numbers, change) {
    if (!q.path || savingBad) return;
    savingBad = true; paint();
    try {
      await apiPost('/api/session/bad-for-path', Object.assign({
        path: q.path,
        bad_channels: numbers.map(Number).sort((a, b) => a - b),
      }, change || {}));
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

  /* ---- settings ---------------------------------------------------------

     Two methods, one switch. STORM is what the IED detector study chose:
     every hand-sorted Solid on the ten PTEN recordings (169 of 169) in 2,595
     candidates, where the lab's original settings catch 111 in 4,447 -- and
     still all 169 one step stricter on either the threshold or the channel
     count, which is why it was chosen over cheaper settings that sit on a
     cliff. Its numbers are in `FOOOF Playgroun/IED detection and such/
     README.md`, and each field says what it fixed. LEGACY is the MATLAB
     exactly. */
  function numField(label, key, step, unit, why, scale) {
    const k = scale || 1;
    return BARRY.ui.field({
      label: label + (unit ? ' (' + unit + ')' : ''), hint: why,
      control: el('input', {
        type: 'number', class: 'num', step: step, 'data-fk': 'num-' + key,
        value: q[key] == null ? '' : +(q[key] * k).toFixed(4),
        onchange: (e) => {
          const v = Number(e.target.value);
          if (!isFinite(v) || v <= 0) return;
          q[key] = v / k;
          changedParams();
        },
      }),
    });
  }

  /* The channel range: two CSC numbers, either blank. A box that only takes
     positive numbers could not be emptied again (numField refuses 0), so
     this one takes blank as "no limit at that end". */
  function rangeField() {
    const box = (key, ph) => el('input', {
      type: 'number', class: 'num', min: '1', step: '1', placeholder: ph,
      'data-fk': 'range-' + key,
      'aria-label': key === 'ch_lo' ? 'First channel' : 'Last channel',
      value: q[key] == null ? '' : String(q[key]),
      onchange: (e) => {
        const raw = String(e.target.value || '').trim();
        const v = raw === '' ? null : Math.round(Number(raw));
        if (v != null && !(isFinite(v) && v >= 1)) {
          e.target.value = q[key] == null ? '' : String(q[key]);
          return;
        }
        q[key] = v;
        if (q.ch_lo != null && q.ch_hi != null && q.ch_hi < q.ch_lo) {
          const t = q.ch_lo; q.ch_lo = q.ch_hi; q.ch_hi = t;
        }
        changedParams();
      },
    });
    const set = q.ch_lo != null || q.ch_hi != null;
    return BARRY.ui.field({
      label: 'Channels', inline: true, extra: 'dop-range-field',
      hint: 'By CSC number, and applied first: a channel outside the range '
          + 'is not read at all, and everything else runs inside it -- '
          + (q.method === 'storm' ? 'the channels detected on, ' : '')
          + 'the bad ones left out'
          + (q.method === 'storm' ? ', the common reference' : '')
          + '. Blank is every channel. For a 128-channel recording where '
          + 'only the first probe is wanted: 1 to 64.',
      control: el('div', { class: 'dop-range' }, [
        el('span', { class: 'dop-range-w', text: 'CSC' }),
        box('ch_lo', 'first'),
        el('span', { class: 'dop-range-w', text: 'to CSC' }),
        box('ch_hi', 'last'),
        set ? el('button', { class: 'mini', text: 'Every channel',
          onclick: () => { q.ch_lo = null; q.ch_hi = null; changedParams(); } })
            : null,
      ].filter(Boolean)),
    });
  }

  function changedParams() {
    reset();
    if (q.count === 'many') loadVaccList();
    else refreshEstimate().then(paint);
    paint();
  }

  function toggle(label, key, onVal, offVal, why) {
    return el('div', {}, [
      el('label', { class: 'toggle' }, [
        el('input', {
          type: 'checkbox', checked: q[key] === onVal ? 'checked' : null,
          onchange: (e) => { q[key] = e.target.checked ? onVal : offVal;
                             changedParams(); },
        }),
        el('span', { text: label }),
      ]),
      why ? el('p', { class: 'hint quiet', style: 'max-width:78ch',
                      text: why }) : null,
    ].filter(Boolean));
  }

  function params() {
    const changed = !isDefault();
    const d = el('details', {
      class: 'incisor-params', open: paramsOpen ? 'open' : null,
      ontoggle: (e) => { paramsOpen = e.target.open; },
    }, [
      el('summary', {}, [
        // Inside Many's "2. Detection" card the number would be a third
        // step that is not one.
        el('span', { text: q.count === 'many' ? 'Settings' : '3. Settings' }),
        el('span', { class: changed ? 'inc-param-tag on' : 'inc-param-tag',
          text: changed ? 'changed'
            : (q.method === 'storm' ? 'the validated defaults'
                                    : 'the lab’s MATLAB, exactly') }),
      ]),
    ]);

    d.appendChild(BARRY.ui.field({
      label: 'Method', inline: true,
      control: BARRY.ui.seg([
        ['storm', 'Validated', 'The Storm method: the settings that caught '
         + 'every hand-sorted IED with the fewest other candidates'],
        ['legacy', 'Legacy MATLAB', 'Kleen’s LLspikedetector exactly as the '
         + 'lab ran it -- for comparing with old runs'],
      ], q.method, (m) => { useMethod(m); changedParams(); }),
    }));
    d.appendChild(el('p', { class: 'hint', style: 'max-width:80ch',
      text: q.method === 'storm'
        ? 'Validated on the ten PTEN hand-sorts: it catches all 169 '
          + 'confirmed IEDs with about 15 candidates per IED, and still '
          + 'catches all of them one step stricter -- chosen for that margin, '
          + 'not just the count. The lab’s original settings catch 111 of '
          + 'them with 4,447 candidates. '
          + 'Common-average referencing and the band-pass do most of the '
          + 'work -- they stop one noisy channel, whole-probe movement and '
          + 'fast unit or muscle activity from counting as discharges.'
        : 'The original detector, exactly: raw signal at its native rate, '
          + 'a 40 ms window, one pooled 99.9th percentile, every channel '
          + 'read. Checked event for event against the MATLAB. Use it to '
          + 'compare with runs made before the Storm method existed.' }));

    const grid = el('div', { class: 'wiz-grid' });
    grid.appendChild(numField('Line-length window', 'llw_s', 2.5, 'ms',
      q.method === 'storm'
        ? '15 ms was best; 10, 12.5, 20 and 30 cost more candidates.'
        : 'MATLAB calls it llw.', 1000));
    grid.appendChild(numField('Threshold', 'prc', 0.05, 'percentile',
      'Where the bar sits in the line-length values, pooled over the '
      + 'detection channels of this recording.'));
    if (q.method === 'storm') {
      grid.appendChild(numField('At least this many channels', 'min_channels',
        1, '', 'An event has to show up on this many detection channels. '
          + 'The lower half of the lab’s 5–10 rule; an upper limit never '
          + 'helped.'));
      grid.appendChild(numField('Merge events closer than', 'merge_s', 50,
        'ms', 'Discharges this close together are one event -- the lab’s '
          + 'own definition. Longer looks cheaper only because it folds '
          + 'two IEDs into one candidate.', 1000));
      grid.appendChild(numField('Shortest event', 'min_event_s', 2.5, 'ms',
        'Shorter crossings are dropped.', 1000));
    }
    d.appendChild(grid);

    d.appendChild(rangeField());

    if (q.method === 'storm') {
      d.appendChild(toggle('Common-average reference (per probe bank)', 'car',
        true, false,
        'The single biggest improvement. Subtracts each bank’s mean of its '
        + 'good channels, so a noisy channel or the whole probe moving does '
        + 'not read as a discharge. A bank marked not connected is left out.'));
      d.appendChild(BARRY.ui.field({
        label: 'Detect on', inline: true,
        control: BARRY.ui.seg([
          ['even', 'Even channels', 'What the study validated, and the '
           + 'lab’s convention'],
          ['all', 'Every channel', 'The channel-count rule was not validated '
           + 'on this'],
          ['odd', 'Odd channels', ''],
        ], q.detect_on, (v) => { q.detect_on = v; changedParams(); }),
      }));
    }

    d.appendChild(toggle('Notch 60 Hz and its harmonics', 'notch_hz', 60, null,
      null));
    d.appendChild(toggle('Band-pass before the transform', 'band_on', true,
      false, q.method === 'storm'
        ? '20–300 Hz. Raw line length counts fast unit and muscle activity, '
          + 'which is most of what the original let through. The low edge '
          + 'matters little -- 5, 10, 20 Hz or none are within a few percent '
          + '-- and 20 Hz was the one with margin.' : null));
    if (q.band_on) {
      d.appendChild(el('div', { class: 'wiz-grid' }, [
        numField('Low', 'band_lo', 1, 'Hz', ''),
        numField('High', 'band_hi', 5, 'Hz', ''),
      ]));
    }

    if (changed) {
      d.appendChild(el('div', { class: 'tk-actions dop-actions' }, [
        el('button', { class: 'btn ghost sm',
          text: q.method === 'storm' ? 'Back to the validated defaults'
                                     : 'Back to the MATLAB’s own',
          onclick: () => { useMethod(q.method); changedParams(); } }),
      ]));
    }
    return d;
  }

  /* ------------------------------------------------------------ the run */

  function body(extra) {
    const b = Object.assign({ path: q.path }, paramsBody());
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

  /* Every detection parameter, as backend/doppler.py's `params_from` reads
     it. Sent in full, so the server never has to guess which default a
     missing field meant. */
  function paramsBody() {
    return {
      method: q.method,
      llw_s: q.llw_s, prc: q.prc,
      notch_hz: q.notch_hz,
      band: q.band_on ? [q.band_lo, q.band_hi] : null,
      car: q.car, min_channels: q.min_channels,
      merge_s: q.merge_s, min_event_s: q.min_event_s,
      detect_on: q.detect_on,
      channel_range: chRange(),
    };
  }

  /* [first, last] by CSC number, or null for every channel. "From 65" with
     no end runs to the last channel there is. */
  function chRange() {
    if (q.ch_lo == null && q.ch_hi == null) return null;
    return [q.ch_lo || 1, q.ch_hi || 9999];
  }

  function rangeWords(r) {
    if (!r) return null;
    return 'CSC' + r[0] + ' to ' + (r[1] >= 9999 ? 'the last channel'
                                                  : 'CSC' + r[1]);
  }

  /* What is on screen is about to stop being true: a different recording,
     different channels, different settings. The run on the cluster is NOT
     touched -- it belongs to the cluster, and lands in the list whatever
     the panel is showing by then. */
  function reset() {
    res = null; snips = null; hoverEv = null; landedOpen = null;
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

  /* ---- runs on the cluster -------------------------------------------- */

  /* The single run started from THIS recording, if one is on the cluster:
     the One panel shows its progress card. A run of another recording is
     in the runs list, not here -- a stage card for a recording you are not
     looking at reads as this one being busy. */
  function myFlight() {
    for (const f of flights.values()) {
      if (f.kind === 'one' && (f.members[0] || {}).gid === q.gid) return f;
    }
    return null;
  }
  function batchFlight() {
    let out = null;
    for (const f of flights.values()) {
      if (f.kind === 'many' && (!out || f.started > out.started)) out = f;
    }
    return out;
  }

  function track(snap, kind, members, extra) {
    if (!snap || !snap.id) return;
    const had = flights.get(snap.id);
    flights.set(snap.id, Object.assign(had || {
      id: snap.id, kind, members: members || [], started: Date.now() / 1000,
    }, extra || {}, { snap }));
    if (!had && BARRY.vaccBusy) BARRY.vaccBusy.start();
    startLoop();
  }

  /* Whatever the server says is on the cluster, picked up again. Asked once
     each time the panel is shown, so a run started before a reload, from
     another view, or before the panel was last left is found where it is. */
  async function attach() {
    /* What landed while the panel was away, marked new; and the list read
       again rather than trusted from before, which is how a run that had
       landed went on being shown as running. */
    const before = reviews ? new Set(reviews.map((r) => r.gid + '/' + r.key))
                           : null;
    let got = null;
    try { got = await api('/api/doppler/inflight'); }
    catch (e) { /* an older server, or none: nothing to pick up */ }
    for (const it of ((got && got.jobs) || [])) {
      const s = it.job || {};
      if (s.status !== 'running' || flights.has(it.id)) continue;
      track(s, it.kind, it.members, { path: it.path, params: it.params,
                                      started: it.started });
    }
    await loadReviews(true);
    if (before) {
      for (const r of (reviews || [])) {
        if (!before.has(r.gid + '/' + r.key)) freshKeys.add(r.key);
      }
    }
    paint();
  }

  async function run(force) {
    if (!q.path || myFlight()) return;
    let started;
    try {
      started = await apiPost('/api/doppler/scan', body({ where: 'vacc',
        force: !!force }));
    } catch (e) {
      toast(e.message, 'err', 9000);
      return;
    }
    if (started.cached) {
      adopt(started.result, true);
      paint();
      return;
    }
    track(started.job, 'one',
          [{ gid: q.gid, label: (q.row || {}).label || null }],
          { path: q.path, params: paramsBody() });
    paint();
  }

  function startLoop() {
    if (loop) return;
    loop = setInterval(follow, 1000);
  }
  function stopLoop() {
    if (loop) { clearInterval(loop); loop = null; }
  }

  /* One timer for every run on the cluster. A job the server no longer
     knows -- it was restarted, or dropped it -- is let go of with a word,
     rather than polled for ever beside its own landed result. */
  let following = false;
  async function follow() {
    if (following) return;
    if (!flights.size) { stopLoop(); return; }
    following = true;
    try {
      for (const f of Array.from(flights.values())) {
        let got;
        try { got = await api('/api/cfc/job/' + f.id); }
        catch (e) {
          if (/No such run/.test(e.message || '')) {
            flights.delete(f.id);
            if (BARRY.vaccBusy) BARRY.vaccBusy.stop();
            toast('Lost track of a Doppler run on ' + flightName(f)
                  + ' — Jarvis was restarted while it ran. If it finished, '
                  + 'it is in the landed list.', 'warn', 9000);
            loadReviews(true).then(paint);
          }
          continue;
        }
        f.snap = got.job;
        if (f.kind === 'many') {
          /* A recording of a batch that has landed goes in the landed list
             as it lands, not when the last of them does. */
          const n = (f.snap.members || []).filter((m) => m.status === 'done')
            .length;
          if (n > (f.doneSeen || 0)) {
            f.doneSeen = n;
            await refreshLanded();
          }
        }
        if (f.snap.status === 'running') continue;
        flights.delete(f.id);
        if (BARRY.vaccBusy) BARRY.vaccBusy.stop();
        await landed(f);
      }
    } finally {
      following = false;
    }
    if (!flights.size) stopLoop();
    paint();
  }

  function flightName(f) {
    const m = f.members || [];
    if (f.kind === 'many') return m.length + ' recording' + (m.length === 1 ? '' : 's');
    return (m[0] || {}).label || 'a recording';
  }

  /* A run has ended. Where it lands depends on what you are looking at: on
     the recording it was for, the report opens with its reveal; anywhere
     else it is announced, and marked new in the landed list. */
  async function landed(f) {
    const s = f.snap || {};
    if (s.status === 'canceled') {
      toast('The run on ' + flightName(f) + ' was cancelled.', 'warn', 5000);
      return;
    }
    if (s.status !== 'done') {
      toast((s.error || 'The run failed') + ' (' + flightName(f) + ')',
            'err', 12000);
      return;
    }
    const before = new Set((reviews || []).map((r) => r.gid + '/' + r.key));
    if (f.kind === 'many') {
      const ms = s.members || [];
      const ok = ms.filter((m) => m.status === 'done').length;
      const bad = ms.filter((m) => m.status === 'failed').length;
      toast('The batch has landed: ' + ok + ' of ' + ms.length + ' done'
            + (bad ? ', ' + bad + ' failed' : '') + '.', bad ? 'warn' : 'ok',
            9000);
      vaccList = null;            // "already run" marks have changed
    } else {
      let out = null;
      try { out = (await api('/api/cfc/result/' + f.id)).result; }
      catch (e) { toast(e.message, 'err', 9000); }
      const gid = (f.members[0] || {}).gid;
      if (out && gid === q.gid && q.count !== 'many') {
        adopt(out, true);
        landedOpen = out.key || null;
      }
      /* Announced even when you are not looking at this tool. A cluster
         job can sit in the queue long enough that nobody is watching the
         tab it was started from. */
      toast('Doppler found ' + ((out || {}).n || 0).toLocaleString()
            + ' IEDs on ' + flightName(f) + '.', 'ok', 8000);
    }
    chime();
    await refreshLanded(before);
    // The one just opened above is on screen; it is not "new".
    if (landedOpen) freshKeys.delete(landedOpen);
  }

  /* The landed list read again, and whatever is in it that was not before
     marked new. */
  async function refreshLanded(before) {
    const had = before || (reviews
      ? new Set(reviews.map((r) => r.gid + '/' + r.key)) : null);
    await loadReviews(true);
    if (!had) return;
    for (const r of (reviews || [])) {
      if (!had.has(r.gid + '/' + r.key)) freshKeys.add(r.key);
    }
  }

  /* The one sound Doppler makes: a soft low bell when a run lands, from
     the reveal's own instrument (jarvisfx.js), and only through it -- so
     the one mute switch silences this too. Nothing for a run opened from
     the list: arriving is the event, looking is not. */
  function chime() {
    try {
      const fx = BARRY.jarvisfx || window.JarvisFX;
      if (fx && !fx.muted && fx.land) fx.land();
    } catch (e) { /* a decoration never stops a result */ }
  }

  async function cancel(id) {
    if (!id) return;
    try { await apiPost('/api/cfc/job/' + id + '/cancel', {}); }
    catch (e) { /* the loop will notice */ }
  }

  /* `reveal`: the report plays its arrival -- the count, the waveform
     drawing itself in, the sweep across the raster. For a run that has
     just come back; not for a redraw of one already on screen. */
  function adopt(out, reveal) {
    res = out || null;
    snips = null;
    revealNext = !!(res && reveal);
    if (res) fetchSnippets();
  }

  async function fetchSnippets() {
    try {
      /* A run made for a recording only the cluster has carries its `key`,
         and is asked for by recording and key -- no copy needed here, and
         the snippets are the run's own even if a field above has moved. */
      const got = await apiPost('/api/doppler/snippets',
        (res && res.key && q.gid) ? { gid: q.gid, key: res.key } : body());
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
    'ied read': 'Read every channel',
    'ied detect': 'Transform and threshold',
    'vacc stage': 'Send the code over',
    'vacc queue': 'Waiting for the cluster',
    'vacc fetch': 'Bring the answer back',
  };

  /* The radar. Doppler is the sweep that finds things, so while a run is
     out the card shows one: rings, a turning beam, a blip now and then.
     Slow and dim while the job waits in the queue; quicker once a node has
     it. Pure CSS, stopped under reduced motion. */
  function radar(extra) {
    return el('div', { class: 'dop-radar' + (extra ? ' ' + extra : ''),
                       'aria-hidden': 'true' }, [
      el('span', { class: 'dop-radar-beam' }),
      el('span', { class: 'dop-radar-blip b1' }),
      el('span', { class: 'dop-radar-blip b2' }),
      el('span', { class: 'dop-radar-blip b3' }),
    ]);
  }

  /* Incisor's progress rows inside, so a person who has watched one
     cluster run has watched them all; the radar and the words on top are
     Doppler's own. */
  function stageCard() {
    const f = myFlight();
    // Said only when the estimate knows: a guess here would be a claim.
    const st = est && est.vacc && est.vacc.state;
    const where = st === 'native' ? 'netfiles, read in place'
      : st === 'staged' ? 'a copy in VACC scratch' : null;
    return el('div', { class: 'card comod-run dop-flight' }, [
      el('div', { class: 'dop-flight-head' }, [
        radar('queued'),
        el('div', { class: 'dop-flight-words' }, [
          el('strong', { class: 'dop-flight-title', text: 'Out on the cluster' }),
          el('span', { class: 'hint quiet',
            text: [(f && f.members[0] && f.members[0].label)
                   || (q.row || {}).label || 'this recording', where]
              .filter(Boolean).join(' · ') }),
        ]),
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
        text: 'You can leave this view, or reload the page. The run is on '
            + 'the cluster and does not belong to this page; Doppler finds '
            + 'it again when you come back, and it lands in the list below.' }),
    ]);
  }

  /* The rows are rebuilt each second -- they are small, and every one can
     change -- but the card around them, the radar and the bar are not, so
     the bar slides rather than jumps and the beam keeps turning. */
  function paintStages(job) {
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

    const card = host.closest('.dop-flight');
    if (card) {
      const r = card.querySelector('.dop-radar');
      if (r) {
        r.classList.toggle('queued', queued);
        r.classList.toggle('live', !queued);
      }
      const t = card.querySelector('.dop-flight-title');
      const fetching = stages.some((x) => x.name === 'vacc fetch'
                                          && x.status === 'running');
      if (t) {
        t.textContent = queued ? 'Waiting in the cluster’s queue'
          : fetching ? 'Bringing the answer back'
            : onNode ? 'Sweeping on a cluster node' : 'Out on the cluster';
      }
    }

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
    const label = (q.row || {}).label || '';
    const open = landedOpen && (reviews || []).find((r) => r.key === landedOpen);
    const at = open && open.computed && open.computed.at;
    const box = el('div', { class: 'card dop-report' + (revealNext ? ' landing' : '') }, [
      el('div', { class: 'dop-report-head' }, [
        el('div', { class: 'section-label', text: 'What came in' }),
        el('span', { class: 'dop-report-sub',
          text: [label, p.method === 'storm' ? 'Validated method'
                                              : 'Legacy MATLAB',
                 at ? 'landed ' + whenWords(at) : null]
            .filter(Boolean).join(' · ') }),
      ]),
    ]);

    box.appendChild(stats());

    box.appendChild(el('div', { class: 'dop-two' }, [
      el('div', { class: 'dop-plot' }, [
        el('div', { class: 'section-label', text: 'Average waveform' }),
        el('canvas', { id: 'dopProfile' }),
        el('p', { class: 'hint quiet',
          text: 'Mean ± SEM across every event, on the channel that '
              + 'carried the most of them.' }),
      ]),
      el('div', { class: 'dop-plot' }, [
        el('div', { class: 'section-label',
          text: 'Per-channel participation' }),
        el('canvas', { id: 'dopPerCh' }),
        el('p', { class: 'hint quiet',
          text: 'How many events each detection channel took part in. A '
              + 'channel on nearly everything is suspect, not busy.' }),
      ]),
    ]));

    box.appendChild(el('div', { class: 'section-label',
      text: 'Where they are' }));
    box.appendChild(el('canvas', { id: 'dopRaster',
      onmousemove: rasterHover, onmouseleave: () => {
        if (hoverEv != null) { hoverEv = null; drawRaster(1); readout(''); }
      }, onclick: rasterClick }));
    box.appendChild(el('div', { id: 'dopRead', class: 'hint quiet',
      text: READOUT }));
    const gone = rasterRows().referenceOnly;
    if (gone) {
      box.appendChild(el('p', { class: 'hint quiet', style: 'max-width:88ch',
        text: 'Detected on the ' + (p.detect_on || 'even') + ' channels. The '
            + gone + ' other channel' + (gone === 1 ? ' was' : 's were')
            + ' read and went into the common-average reference, but '
            + 'detection does not run on ' + (gone === 1 ? 'it' : 'them')
            + ', so ' + (gone === 1 ? 'it has' : 'they have')
            + ' no row here. Not bad, not left out.' }));
    }

    const warns = realWarnings(res.warnings, res.n);
    if (warns.length) {
      box.appendChild(el('div', { class: 'dop-warns' },
        warns.map((w) => el('p', { class: 'warn-line', text: w }))));
    }

    box.appendChild(paramsLine(p));
    const cmp = comparison();
    if (cmp) box.appendChild(cmp);
    return box;
  }

  /* The warnings worth reading. "CSCn took part in 100% of events" means
     a broken channel when there are hundreds of events and nothing at all
     when there is one -- runs filed before doppler.SUSPECT_MIN_EVENTS carry
     one such warning per channel, so they are dropped here too. */
  function realWarnings(list, n) {
    return (list || []).filter((w) => (n || 0) >= 20
                                      || !/took part in \d+% of events/.test(w));
  }

  const READOUT = 'One line per detection channel, one tick per event. '
                + 'Point at a tick to read it; click to open the recording '
                + 'there.';

  /* "12 minutes ago", "yesterday", "3 Oct" -- in words, because this sits
     in a sentence, where ui.when's "12m" would read as a size. */
  function whenWords(at) {
    const t = Date.parse(at || '');
    if (!isFinite(t)) return '';
    const s = Math.max(0, (Date.now() - t) / 1000);
    if (s < 60) return 'just now';
    if (s < 3600) {
      const m = Math.round(s / 60);
      return m + ' minute' + (m === 1 ? '' : 's') + ' ago';
    }
    if (s < 86400) {
      const h = Math.round(s / 3600);
      return h + ' hour' + (h === 1 ? '' : 's') + ' ago';
    }
    if (s < 2 * 86400) return 'yesterday';
    return new Date(t).toLocaleDateString(undefined,
      { day: 'numeric', month: 'short' });
  }

  /* The numbers first, large. A count somebody reads in a glance rather
     than a row of chips that all weigh the same; on arrival the count
     runs up to its value. */
  function stats() {
    const dur = res.duration_s || 1;
    const perMin = res.n / dur * 60;
    const meanCh = res.n
      ? (res.events || []).reduce((a, e) => a + e.n_channels, 0) / res.n
      : 0;
    const p = res.params || {};
    const det = (p.channels || []).length;
    const read = (p.read_channels || p.channels || []).length;
    const excl = (p.excluded || []).length;
    const one = (k, value, label, title, big) => el('div', {
      class: 'dop-stat' + (big ? ' big' : ''), 'data-k': k, title: title || null,
    }, [
      el('span', { class: 'dop-stat-v', text: value }),
      el('span', { class: 'dop-stat-l', text: label }),
    ]);
    const row = el('div', { class: 'dop-stats' }, [
      one('n', res.n.toLocaleString(), res.n === 1 ? 'IED' : 'IEDs',
          'Events the detector kept', true),
      one('rate', String(Math.round(perMin * 10) / 10), 'per minute'),
      one('each', String(Math.round(meanCh * 10) / 10), 'channels each',
          'How many detection channels an event spans, on average'),
      one('det', String(det), det === read ? 'channels read'
                                             : 'detection channels',
          det === read ? null : (read + ' read; detection runs on ' + det)),
      excl ? one('bad', String(excl), 'marked bad', 'Not read at all')
           : null,
      one('dur', human(dur), 'recorded'),
    ].filter(Boolean));
    if (revealNext) {
      const v = row.querySelector('[data-k="n"] .dop-stat-v');
      if (v) {
        v.textContent = '0';
        // Next frame, so the count runs on screen rather than off it.
        requestAnimationFrame(() => BARRY.ui.countUp(v, res.n, { ms: 900 }));
      }
    }
    return row;
  }

  function paramsLine(p) {
    const storm = p.method === 'storm';
    const bits = [
      storm ? 'the validated Storm method' : 'the lab’s MATLAB, exactly',
      storm ? (p.car ? 'common-average referenced per probe bank'
                     : 'not re-referenced') : null,
      p.band ? ('band-pass ' + p.band[0] + '–' + p.band[1] + ' Hz')
             : 'no band-pass',
      p.notch_hz ? ('notched at ' + p.notch_hz + ' Hz') : 'no notch',
      'line-length window ' + (p.llw_s * 1000) + ' ms',
      'threshold at the ' + p.prc + 'th percentile (' + p.threshold + ')',
      (p.channels || []).length + ' channels',
      'stamped at the ' + p.stamp,
      'events closer than ' + (p.merge_s * 1000) + ' ms merged',
      'shorter than ' + (p.min_event_s * 1000) + ' ms dropped',
      storm ? ('detected on ' + (p.detect_on || 'even') + ' channels, kept '
               + 'when ' + (p.min_channels || 1) + ' or more took part')
            : null,
      storm && p.fs_work ? ('worked at ' + Math.round(p.fs_work) + ' Hz')
                         : null,
      (p.not_connected || []).length
        ? (p.not_connected.length + ' channels on a bank marked not '
           + 'connected left out') : null,
    ].filter(Boolean);
    /* The summary is a sentence of its own, not the first three items of
       the list with an ellipsis after them -- nothing in this interface is
       cut short to fit. */
    const brief = [
      storm ? 'Validated method' : 'Legacy MATLAB',
      p.channel_range ? rangeWords(p.channel_range) + ' only' : null,
      p.band ? (p.band[0] + '–' + p.band[1] + ' Hz') : 'unfiltered',
      (p.llw_s * 1000) + ' ms window',
      storm ? ('at least ' + (p.min_channels || 1) + ' of '
               + (p.channels || []).length + ' ' + (p.detect_on || 'even')
               + ' channels') : ((p.channels || []).length + ' channels'),
    ];
    const d = el('details', { class: 'dop-params', 'data-keep': 'ran-with' }, [
      el('summary', { text: 'How it was run: '
                            + brief.filter(Boolean).join(', ') }),
    ]);
    d.appendChild(el('p', { class: 'hint', style: 'max-width:88ch',
      text: bits.join('. ') + '.' }));
    d.appendChild(el('p', { class: 'hint', style: 'max-width:88ch',
      text: channelsSentence(p) }));
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

  /* `reveal`: the arrival. The waveform draws itself left to right, the
     bars rise, and a sweep crosses the raster leaving each event behind it
     -- about a second in all, the three a beat apart. Anything else draws
     the finished picture at once. The last frame is drawn on a timer as
     well as by the animation, so under reduced motion, in a background tab
     or under the harness runner's virtual time the picture is still whole. */
  let animSeq = 0;
  function drawPlots(reveal) {
    if (!res) return;
    const mine = ++animSeq;
    const all = (k) => {
      try {
        drawProfile(clamp01((k - 0.0) / 0.55));
        drawPerCh(clamp01((k - 0.12) / 0.55));
        drawRaster(clamp01((k - 0.25) / 0.75));
      } catch (e) { reportClientError('doppler.draw', e.message, q.path); }
    };
    if (!reveal || BARRY.ui.reducedMotion()) { all(1); return; }
    const ms = 1300;
    const t0 = performance.now();
    const step = (now) => {
      if (mine !== animSeq) return;
      const k = Math.min(1, (now - t0) / ms);
      all(k);
      if (k < 1) requestAnimationFrame(step);
    };
    all(0);
    requestAnimationFrame(step);
    setTimeout(() => { if (mine === animSeq) { animSeq++; all(1); } }, ms + 80);
  }
  const clamp01 = (x) => Math.max(0, Math.min(1, x));
  const easeOut = (x) => 1 - Math.pow(1 - clamp01(x), 3);

  /* Mean +/- SEM, the band SHADED rather than the trace cropped to it --
     the same idiom X-ray uses, and for the same reason: a picture of only
     the middle of the spread cannot answer how wide the spread is. */
  function drawProfile(k) {
    const kk = k == null ? 1 : k;
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

    const P = PAD;
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
    g.strokeStyle = tok('--line', '#555');
    g.setLineDash([3, 3]);
    g.beginPath(); g.moveTo(mid, P.t); g.lineTo(mid, P.t + plotH); g.stroke();
    g.setLineDash([]);

    const col = tok('--accent', '#E5A823');
    // The band comes up as the line draws; the line runs left to right.
    const upto = Math.max(1, Math.round(easeOut(kk) * (m.length - 1)));
    g.fillStyle = col; g.globalAlpha = 0.20 * easeOut(kk);
    g.beginPath();
    for (let i = 0; i < m.length; i++) g.lineTo(sx(i), sy(m[i] + (s[i] || 0)));
    for (let i = m.length - 1; i >= 0; i--) {
      g.lineTo(sx(i), sy(m[i] - (s[i] || 0)));
    }
    g.closePath(); g.fill(); g.globalAlpha = 1;

    g.strokeStyle = col; g.lineWidth = 2;
    g.lineJoin = 'round';
    g.beginPath();
    for (let i = 0; i <= upto; i++) g.lineTo(sx(i), sy(m[i]));
    g.stroke(); g.lineWidth = 1;

    g.fillStyle = tok('--text-3', '#888');
    g.font = '10px system-ui';
    g.textBaseline = 'alphabetic';
    g.textAlign = 'left';
    g.fillText(ms[0] + ' ms', P.l, c.H - 8);
    g.textAlign = 'center';
    g.fillText('0', mid, c.H - 8);
    g.textAlign = 'right';
    g.fillText(ms[ms.length - 1] + ' ms', P.l + plotW, c.H - 8);
    // Which channel and how many, top right -- the unit owns top left.
    const lab = ((res.per_channel || [])[best] || {}).label
             || ('CSC' + ((prof.channels || [])[best]));
    g.fillText(lab + ' · n = ' + (prof.n || 0).toLocaleString(),
               P.l + plotW, 11);
    g.textAlign = 'left';
  }

  function drawPerCh(k) {
    const kk = k == null ? 1 : k;
    const c = canvasFor('dopPerCh', 190);
    if (!c) return;
    const rows = res.per_channel || [];
    if (!rows.length) { empty(c, 'Nothing was read.'); return; }
    const P = PAD;
    const plotW = Math.max(10, c.W - P.l - P.r);
    const plotH = Math.max(10, c.H - P.t - P.b);
    const hi = Math.max(1, ...rows.map((r) => r.n));
    frame(c, P, plotW, plotH, 0, hi, 'events');
    const g = c.g;
    const step = plotW / rows.length;
    const suspect = 0.90 * (res.n || 1);
    rows.forEach((r, i) => {
      // Left to right, each a moment after its neighbour.
      const grow = easeOut((kk - 0.5 * i / rows.length) / 0.5);
      const h = (r.n / hi) * plotH * grow;
      // A suspect channel is coloured as a warning, not as a winner: the
      // tallest bar here is the thing you should distrust first.
      g.fillStyle = r.n >= suspect ? tok('--warn', '#E5A823')
                                   : tok('--accent', '#3b82f6');
      g.globalAlpha = 0.85;
      g.fillRect(P.l + i * step + 1, P.t + plotH - h,
                 Math.max(1, step - 2), h);
    });
    g.globalAlpha = 1;
    g.fillStyle = tok('--text-3', '#888');
    g.font = '10px system-ui';
    g.textBaseline = 'alphabetic';
    g.textAlign = 'left';
    g.fillText(rows[0].label || ('CSC' + rows[0].number), P.l, c.H - 8);
    const last = rows[rows.length - 1];
    g.textAlign = 'right';
    g.fillText(last.label || ('CSC' + last.number), P.l + plotW, c.H - 8);
    g.textAlign = 'left';
  }

  /* Room for the unit ABOVE the axis, so it never sits on the top value:
     "events" and "273" were drawn into the same 40 pixels at the same
     height, and read as "evens273" (2026-10-13). */
  const PAD = { l: 46, r: 10, t: 20, b: 24 };

  const RASTER_ROW = 13;

  /* Which channels get a row, and why the absent ones are absent.

     A row per DETECTION channel: on the Storm method that is the even (or
     odd) channels; every other channel was read for the common-average
     reference only and has no row -- the report says so in a sentence. The
     raster used to give every channel on the probe a row and call the
     reference-only ones "bad", which they are not. A detection channel
     that is marked bad, or left out of this run, keeps its row as a
     dashed rule saying which: a missing row and a silent row are different
     facts. From the result itself, not the estimate, so a run opened from
     the list draws right before -- or without -- a fresh estimate. */
  function rasterRows() {
    const p = res.params || {};
    const storm = p.method === 'storm';
    const rule = storm ? (p.detect_on || 'even') : 'all';
    const takes = (n) => rule === 'all' || (rule === 'even' ? n % 2 === 0
                                                            : n % 2 === 1);
    const byNum = new Map();
    for (const r of (res.per_channel || [])) {
      byNum.set(Number(r.number), { number: Number(r.number),
        label: r.label || ('CSC' + r.number), read: true });
    }
    const absent = (list, why) => {
      for (const c of (list || [])) {
        const n = Number(c.number != null ? c.number : c);
        if (!isFinite(n) || byNum.has(n) || !takes(n)) continue;
        byNum.set(n, { number: n, label: c.label || ('CSC' + n),
                       read: false, why });
      }
    };
    absent(p.excluded, 'bad');
    absent(p.left_out, 'left out of this run');
    const rows = Array.from(byNum.values()).sort((a, b) => a.number - b.number);
    const read = (p.read_channels || []).map(Number);
    const referenceOnly = storm && rule !== 'all'
      ? read.filter((n) => !takes(n)).length : 0;
    return { rows, referenceOnly };
  }

  function drawRaster(k) {
    const kk = k == null ? 1 : k;
    const rows = rasterRows().rows;
    const h = Math.max(80, rows.length * RASTER_ROW + 34);
    const c = canvasFor('dopRaster', h);
    if (!c) return;
    const P = { l: 52, r: 10, t: 6, b: 22 };
    const plotW = Math.max(10, c.W - P.l - P.r);
    const g = c.g;
    const dur = res.duration_s || 1;
    const sweep = P.l + easeOut(kk) * plotW;   // how far the reveal has got

    g.font = '9px system-ui';
    g.textBaseline = 'middle';
    const ground = tok('--bg-2', '#0f1e18');
    rows.forEach((r, i) => {
      const y = P.t + i * RASTER_ROW + RASTER_ROW / 2;
      g.fillStyle = tok('--text-3', '#6f8c7d');
      g.textAlign = 'right';
      g.fillText(r.label, P.l - 6, y);
      g.strokeStyle = tok('--line', '#333');
      if (!r.read) {
        g.setLineDash([3, 4]);
        g.beginPath(); g.moveTo(P.l, y); g.lineTo(P.l + plotW, y); g.stroke();
        g.setLineDash([]);
        // On the row, at its right end, on a patch of the ground so the
        // dashes do not run through it -- never between two rows, where
        // it reads as belonging to either.
        const tw = g.measureText(r.why).width;
        g.fillStyle = ground;
        g.fillRect(P.l + plotW - tw - 10, y - 6, tw + 10, 12);
        g.fillStyle = tok('--text-3', '#6f8c7d');
        g.fillText(r.why, P.l + plotW - 2, y);
        return;
      }
      g.globalAlpha = 0.35;
      g.beginPath(); g.moveTo(P.l, y); g.lineTo(P.l + plotW, y); g.stroke();
      g.globalAlpha = 1;
    });

    const rowOf = {};
    rows.forEach((r, i) => { if (r.read) rowOf[r.number] = i; });
    const evs = res.events || [];
    for (let j = 0; j < evs.length; j++) {
      const e = evs[j];
      const x = P.l + (e.start / dur) * plotW;
      if (x > sweep) continue;
      const on = (hoverEv === j);
      // Just behind the sweep a tick is bright and settles: the trail.
      const fresh_ = kk < 1 ? clamp01(1 - (sweep - x) / 60) : 0;
      g.globalAlpha = on ? 1 : 0.6 + 0.4 * fresh_;
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

    if (kk < 1) {
      // The beam: a bright line with a fading wash behind it.
      const top = P.t, bot = P.t + rows.length * RASTER_ROW;
      const wash = g.createLinearGradient(sweep - 70, 0, sweep, 0);
      wash.addColorStop(0, 'rgba(0,0,0,0)');
      wash.addColorStop(1, tok('--accent-soft', 'rgba(255,184,28,.15)'));
      g.fillStyle = wash;
      g.fillRect(sweep - 70, top, 70, bot - top);
      g.strokeStyle = tok('--accent', '#E5A823');
      g.lineWidth = 1.5;
      g.beginPath(); g.moveTo(sweep, top); g.lineTo(sweep, bot); g.stroke();
      g.lineWidth = 1;
    }

    g.fillStyle = tok('--text-3', '#888');
    g.textBaseline = 'alphabetic';
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
      n.textContent = text || READOUT;
      n.classList.toggle('on', !!text);
    }
  }

  function rasterHover(e) {
    const i = rasterAt(e);
    if (i === hoverEv) return;
    hoverEv = i;
    drawRaster(1);
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

  /* The axes, the two end values beside the axis, a faint line at the
     top value, and the unit ABOVE the plot on its own line -- the unit
     and the top value used to share a row and overprint. */
  function frame(c, P, plotW, plotH, lo, hi, ylab) {
    const g = c.g;
    g.strokeStyle = tok('--line', '#444');
    g.globalAlpha = 0.45;
    g.setLineDash([2, 4]);
    g.beginPath();
    g.moveTo(P.l, P.t + 0.5); g.lineTo(P.l + plotW, P.t + 0.5);
    g.stroke();
    g.setLineDash([]);
    g.globalAlpha = 1;
    g.beginPath();
    g.moveTo(P.l + 0.5, P.t); g.lineTo(P.l + 0.5, P.t + plotH);
    g.lineTo(P.l + plotW, P.t + plotH + 0.5);
    g.stroke();
    g.fillStyle = tok('--text-3', '#888');
    g.font = '10px system-ui';
    g.textBaseline = 'middle';
    g.textAlign = 'right';
    g.fillText(fmt(hi), P.l - 6, P.t);
    g.fillText(fmt(lo), P.l - 6, P.t + plotH);
    g.textBaseline = 'alphabetic';
    g.textAlign = 'left';
    g.fillText(ylab, P.l, 11);
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
      el('div', { class: 'tk-actions dop-actions' }, [
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
    const storm = p.method === 'storm';
    return 'Detected by Doppler on the VACC, ' + p.detector + '. '
      + (storm ? ('Validated on the PTEN hand-sorts (every confirmed IED '
                  + 'caught). Decimated to ' + Math.round(p.fs_work || 2000)
                  + ' Hz, '
                  + (p.car ? 'common-average referenced per probe bank, '
                           : '')
                  + 'detected on ' + (p.detect_on || 'even') + ' channels, '
                  + 'kept when ' + (p.min_channels || 1) + ' or more took '
                  + 'part. ') : '')
      + (p.band ? ('Band-passed ' + p.band[0] + '–' + p.band[1] + ' Hz'
                   + (p.notch_hz ? ' after a ' + p.notch_hz + ' Hz notch'
                                 : '') + '. ')
                : (storm ? 'No band-pass. '
                         : 'No filtering, which is what the original '
                           + 'detector does. '))
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
      + 'signal through this recording’s gap map. '
      + channelsSentence(p);
  }

  /* The channels a run was given, written out for the notes and the
     report: the range, then every channel by role, whole lists by name. A
     note is what somebody reads six months later to know what was detected
     on, and "31 channels" does not answer that. */
  function channelsSentence(p) {
    const storm = p.method === 'storm';
    const num = (x) => Number(x && x.number != null ? x.number : x);
    const csc = (n) => 'CSC' + n;
    const label = (x) => (x && x.label) || csc(num(x));
    const det = (p.channels || []).map(Number);
    const read = (p.read_channels || p.channels || []).map(Number);
    const detSet = new Set(det);
    const ref = read.filter((n) => !detSet.has(n));
    const parts = [];
    if (p.channel_range) {
      const out = (p.out_of_range || []).map(num).filter(isFinite);
      parts.push('Channels ' + rangeWords(p.channel_range) + ' only'
        + (out.length ? ' (' + runsOf(out.map(csc)).join(', ')
                        + ' not read)' : '') + '.');
    }
    parts.push('Detected on '
      + (storm && p.detect_on && p.detect_on !== 'all'
        ? 'the ' + det.length + ' ' + p.detect_on + ' channels'
        : det.length + ' channel' + (det.length === 1 ? '' : 's'))
      + ': ' + det.map(csc).join(', ') + '.');
    if (ref.length) {
      parts.push((storm && p.car ? 'Read for the common reference only'
                                 : 'Read, not detected on')
        + ' (' + ref.length + '): ' + ref.map(csc).join(', ') + '.');
    }
    if ((p.excluded || []).length) {
      parts.push('Marked bad and not read: '
        + p.excluded.map(label).join(', ') + '.');
    }
    if ((p.left_out || []).length) {
      parts.push('Left out of this run by choice: '
        + p.left_out.map(label).join(', ') + '.');
    }
    if ((p.not_connected || []).length) {
      parts.push('On a bank marked not connected, not read: '
        + p.not_connected.map((n) => csc(num(n))).join(', ') + '.');
    }
    return parts.join(' ');
  }

  /* ------------------------------------------------- runs that have landed */

  async function loadReviews(force) {
    if (reviews && !force) return;
    try {
      const got = await api('/api/doppler/reviews');
      reviews = got.reviews || [];
    } catch (e) { reviews = []; }
  }

  /* ---- the runs: out on the cluster, and landed ------------------------

     One card, two groups, and a run is in exactly one of them: out on the
     cluster while its job runs, landed once it is in the vault. The panel
     used to keep the run it had started in a variable, and could say
     "running" beside the same run already landed -- and the landed list
     opened a run by asking for it again, which could start a new one. */
  function runsShell() {
    return el('div', { class: 'card dop-runs' }, [
      el('div', { class: 'section-label', text: 'Runs' }),
      el('div', { class: 'dop-runs-parts' }),
    ]);
  }

  const LANDED_FEW = 8;

  function runsUpdate(node) {
    const inner = node.querySelector('.dop-runs-parts');
    if (!inner) return;
    if (reviews === null) loadReviews().then(paint);
    const out = Array.from(flights.values())
      .sort((a, b) => b.started - a.started);
    const parts = [];
    if (out.length) {
      parts.push({ key: 'fh', sig: 'fh', build: () => el('div',
        { class: 'dop-runs-h', text: 'Out on the cluster' }) });
      for (const f of out) {
        parts.push({ key: 'f-' + f.id, sig: flightSig(f),
                     build: () => flightRow(f) });
      }
    }
    parts.push({ key: 'lh', sig: [reviews ? reviews.length : -1],
      build: () => el('div', { class: 'dop-runs-h' }, [
        el('span', { text: 'Landed' }),
        reviews && reviews.length
          ? el('span', { class: 'dop-runs-n',
                         text: reviews.length.toLocaleString() }) : null,
      ].filter(Boolean)) });
    parts.push({ key: 'll', enter: false,
      sig: [oid(reviews), landedOpen, Array.from(freshKeys).join(','),
            landedAll, Math.floor(Date.now() / 60000)],
      build: landedList });
    BARRY.ui.sections(inner, parts);
  }

  /* What a flight row shows, coarse enough that it is rebuilt when a word
     on it changes and not on every poll -- the seconds tick in place. */
  function flightSig(f) {
    const s = f.snap || {};
    const ms = (s.members || []).map((m) => m.status).join(',');
    return [f.id, s.status, s.stage, ms, Math.floor((s.elapsed || 0) / 10)];
  }

  function flightWords(f) {
    const s = f.snap || {};
    if (f.kind === 'many') {
      const ms = s.members || [];
      const n = (st) => ms.filter((m) => m.status === st).length;
      const parts = [
        n('done') ? n('done') + ' landed' : null,
        n('running') ? n('running') + ' running' : null,
        (n('queued') + n('waiting')) ? (n('queued') + n('waiting'))
                                       + ' waiting' : null,
        n('failed') ? n('failed') + ' failed' : null,
      ].filter(Boolean);
      return parts.join(' · ') || 'starting';
    }
    const st = s.stages || [];
    const qs = st.find((x) => x.name === 'vacc queue');
    const node_ = st.some((x) => (x.name === 'ied read' || x.name === 'ied detect')
                                 && x.status === 'running');
    if (qs && qs.status !== 'done' && !(qs.done >= 1) && !node_) {
      return 'waiting in the queue';
    }
    if (st.some((x) => x.name === 'vacc fetch' && x.status === 'running')) {
      return 'bringing the answer back';
    }
    return node_ || (qs && qs.done >= 1) ? 'sweeping on a node'
                                         : 'getting ready';
  }

  function flightRow(f) {
    const s = f.snap || {};
    const el_s = Number(s.elapsed || 0);
    const since = el_s < 90 ? Math.round(el_s) + ' s'
                            : Math.round(el_s / 60) + ' min';
    const queued = /queue/.test(flightWords(f));
    const name = f.kind === 'many'
      ? 'A batch of ' + f.members.length + ' recording'
        + (f.members.length === 1 ? '' : 's')
      : ((f.members[0] || {}).label || 'A recording');
    return el('button', {
      class: 'dop-run flying',
      title: f.kind === 'many' ? 'Show the batch' : 'Show this run',
      onclick: () => {
        if (f.kind === 'many') { q.count = 'many'; paint(); return; }
        const gid = (f.members[0] || {}).gid;
        const r = rows().find((x) => x.gid === gid);
        q.count = 'one';
        if (r && gid !== q.gid) { choose(r); refreshEstimate().then(paint); }
        paint();
      },
    }, [
      radar('mini ' + (queued ? 'queued' : 'live')),
      el('span', { class: 'dop-run-main' }, [
        el('span', { class: 'dop-run-name', text: name }),
        el('span', { class: 'dop-run-sub',
                     text: flightWords(f) + ' · ' + since + ' so far' }),
      ]),
      f.kind === 'one' && !queued ? el('span', { class: 'dop-run-bar' }, [
        el('span', { style: 'width:' + Math.round(100 * flightFrac(s)) + '%' }),
      ]) : null,
    ].filter(Boolean));
  }

  /* The share of a single run that is done, by the same weights as the
     progress card -- the queue counted, so a queued job is not at 2%. */
  function flightFrac(s) {
    let total = 0, done = 0;
    for (const st of (s.stages || [])) {
      const w = WEIGHT[st.name] || 1;
      total += w;
      const frac = st.of ? Math.min(1, (st.done || 0) / st.of) : 0;
      done += w * (st.status === 'done' ? 1 : frac);
    }
    return total ? done / total : 0;
  }

  function landedList() {
    const box = el('div', { class: 'dop-landed' });
    if (reviews === null) {
      BARRY.skeleton.into(box, 'row', 3);
      return box;
    }
    if (!reviews.length) {
      box.appendChild(el('div', { class: 'empty-state',
        text: 'Nothing has landed yet. Pick a recording and run it on the '
            + 'cluster, or send a batch from Many; each run lands here, and '
            + 'opens from here.' }));
      return box;
    }
    const shown = landedAll ? reviews : reviews.slice(0, LANDED_FEW);
    for (const r of shown) box.appendChild(landedRow(r));
    if (reviews.length > LANDED_FEW) {
      box.appendChild(el('button', { class: 'btn ghost sm dop-landed-more',
        text: landedAll ? 'Show the latest ' + LANDED_FEW
                        : 'Show all ' + reviews.length.toLocaleString(),
        onclick: () => { landedAll = !landedAll; paint(); } }));
    }
    return box;
  }

  function landedRow(r) {
    const sp = r.spec || {};
    const storm = sp.method === 'storm';
    const at = (r.computed || {}).at;
    const open = landedOpen === r.key;
    const isNew = freshKeys.has(r.key);
    const bits = [
      storm ? 'Validated' : 'Legacy MATLAB',
      sp.channel_range ? rangeWords(sp.channel_range) + ' only' : null,
      sp.band ? (sp.band[0] + '–' + sp.band[1] + ' Hz') : 'unfiltered',
      sp.llw_s ? Math.round(sp.llw_s * 10000) / 10 + ' ms' : null,
      storm && sp.min_channels ? 'at least ' + sp.min_channels + ' channels'
                               : null,
      at ? whenWords(at) : null,
    ].filter(Boolean);
    const warns = realWarnings(r.warnings, r.n);
    const warn = warns.length;
    return el('button', {
      class: 'dop-run' + (open ? ' open' : '') + (isNew ? ' fresh' : ''),
      title: open ? 'On screen above' : 'Open this run',
      'aria-current': open ? 'true' : null,
      onclick: () => openRun(r),
    }, [
      el('span', { class: 'dop-run-dot', 'aria-hidden': 'true' }),
      el('span', { class: 'dop-run-main' }, [
        el('span', { class: 'dop-run-name', text: r.label || r.gid }),
        el('span', { class: 'dop-run-sub', text: bits.join(' · ') }),
      ]),
      el('span', { class: 'dop-run-tags' }, [
        isNew ? BARRY.ui.chip('new', { kind: 'ok' }) : null,
        open ? BARRY.ui.chip('open') : null,
        (r.banked || []).length
          ? BARRY.ui.chip('banked', { kind: 'ok',
              title: r.banked.map((b) => b.name).filter(Boolean).join(', ') })
          : BARRY.ui.chip('not banked'),
        warn ? BARRY.ui.chip(warn + ' to look at', { kind: 'warn',
                  title: warns.join('\n') }) : null,
      ].filter(Boolean)),
      el('span', { class: 'dop-run-n' }, [
        el('strong', { text: (r.n || 0).toLocaleString() }),
        el('span', { text: (r.n === 1 ? 'IED' : 'IEDs') }),
      ]),
    ]);
  }

  /* Opening a landed run READS it -- by recording and key, from the vault,
     the cache or the run directory on the cluster -- and never asks for a
     run. It used to post the same question to /api/doppler/scan and hope
     for a cache hit; a run filed with channels left out, or a recording
     opened by another path, was not one, and that quietly submitted a new
     cluster job whose answer the panel threw away. And from Many it set
     the result and painted the Many view, which has no report: the click
     did nothing at all. */
  let opening = null;
  async function openRun(r) {
    if (!r || !r.key || opening === r.key) return;
    if (landedOpen === r.key && res && q.count !== 'many') {
      scrollToReport();
      return;
    }
    opening = r.key;
    let got;
    try {
      got = await api('/api/doppler/run?gid=' + encodeURIComponent(r.gid)
                      + '&key=' + encodeURIComponent(r.key));
    } catch (e) {
      opening = null;
      toast(e.message, 'err', 9000);
      return;
    }
    opening = null;
    q.count = 'one';
    q.gid = r.gid;
    q.path = got.path || r.local || r.path;
    q.row = got.row || r.row || null;
    /* The settings on screen become the ones the report was made with: a
       report under settings it was not made with is the thing that gets
       banked by mistake. */
    const sp = got.spec || r.spec || {};
    useMethod(sp.method === 'storm' ? 'storm' : 'legacy');
    for (const k of ['llw_s', 'prc', 'min_channels', 'merge_s',
                     'min_event_s', 'detect_on']) {
      if (sp[k] != null) q[k] = sp[k];
    }
    if ('car' in sp) q.car = !!sp.car;
    q.notch_hz = sp.notch_hz || null;
    q.band_on = !!sp.band;
    if (sp.band) { q.band_lo = sp.band[0]; q.band_hi = sp.band[1]; }
    const rng = sp.channel_range || null;
    q.ch_lo = rng ? rng[0] : null;
    q.ch_hi = rng ? (rng[1] >= 9999 ? null : rng[1]) : null;
    q.exclude = (sp.left_out || []).map((c) => Number(
      c && c.number != null ? c.number : c)).filter(isFinite);
    q.preset = sp.preset || (q.exclude.length ? 'custom' : 'all');
    est = null;
    adopt(got.result, true);
    landedOpen = r.key;
    freshKeys.delete(r.key);
    /* The estimate is for the plan card above the report; a moment is
       given for it so the card is there before the report draws, rather
       than arriving after and pushing the report down the page. */
    await Promise.race([refreshEstimate(),
                        new Promise((ok) => setTimeout(ok, 1200))]);
    paint();
    scrollToReport();
    if (!est) refreshEstimate().then(paint);
  }

  function scrollToReport() {
    requestAnimationFrame(() => {
      const n = document.querySelector('#tkResult [data-sec="report"]');
      if (n && n.scrollIntoView) {
        n.scrollIntoView({ block: 'start',
          behavior: BARRY.ui.reducedMotion() ? 'auto' : 'smooth' });
      }
    });
  }

  /* --------------------------------------------------------------- batch */

  /* ---- Many --------------------------------------------------------------

     Incisor's picker, for Doppler: every recording the cluster can read --
     on the lab's netfiles share, read in place, or as a copy in scratch --
     whether or not this computer has it too. Search, tick, see the cost,
     send. A recording already run with these exact settings says so and is
     skipped unless asked again; one the cluster cannot read is named with
     its reason, and one only missing from the cluster can be uploaded from
     here. */
  async function loadVaccList() {
    const mine = ++vaccListSeq;
    try {
      const got = await apiPost('/api/doppler/batch/plan', paramsBody());
      if (mine !== vaccListSeq) return;
      vaccList = got;
      // What stays ticked is what is still runnable.
      const runnable = new Set((got.todo || []).map((r) => r.gid));
      for (const g of Array.from(picked)) {
        if (!runnable.has(g)) picked.delete(g);
      }
    } catch (e) {
      if (mine !== vaccListSeq) return;
      vaccList = { todo: [], blocked: [], error: e.message };
    }
    paint();
  }

  function rowMatches(r) {
    if (!vaccFilter) return true;
    const hay = [r.label, r.project, r.mouse != null ? 'm' + r.mouse : '',
                 r.session != null ? 's' + r.session : '', r.start,
                 r.remote, r.state === 'native' ? 'netfiles' : 'scratch']
      .join(' ').toLowerCase();
    return vaccFilter.toLowerCase().split(/\s+/).filter(Boolean)
      .every((w) => hay.includes(w));
  }

  function rowSub(r) {
    const bad = r.bad_channels || [];
    // The folder itself, because a recording's id can hold several: a DEWEY
    // day is one id across FP1, SPC and FP2, and this is the one that runs.
    const folder = String(r.remote || '').split('/').filter(Boolean)
      .slice(-2).join('/');
    return (r.state === 'native' ? 'netfiles, read in place'
                                 : 'a copy in VACC scratch')
      + (folder ? ' · ' + folder : '')
      + ' · ' + (r.n_channels ? r.n_channels + ' channels'
                              : 'channels read on the cluster')
      + (r.duration_s ? ' · ' + Math.round(r.duration_s / 60) + ' min' : '')
      + (bad.length ? ' · ' + bad.length + ' marked bad' : '')
      + (r.here ? ' · also on this computer' : '');
  }

  function human(sec) {
    const s_ = Math.max(0, Math.round(sec || 0));
    if (s_ < 90) return s_ + ' s';
    if (s_ < 5400) return Math.round(s_ / 60) + ' min';
    return (Math.round(s_ / 360) / 10) + ' h';
  }

  /* "1. Which recordings". The card, the sentence and the search box are
     built once per list; what changes as you type and tick -- the counts,
     the rows, the left-out ones -- is reconciled inside it, so the search
     box keeps its cursor and the list keeps its scroll. It used to rebuild
     the whole card on every letter and every tick. */
  function manyPickCard() {
    const box = el('div', { class: 'card' }, [
      el('div', { class: 'section-label', text: '1. Which recordings' }),
    ]);
    if (!vaccList) {
      box.appendChild(loader('Asking what the cluster can read',
        'the registry, the lab’s netfiles share and scratch -- about '
        + 'half a minute'));
      loadVaccList();
      return box;
    }
    if (vaccList.error) {
      box.appendChild(el('p', { class: 'warn-line', text: vaccList.error }));
      return box;
    }
    const todo = vaccList.todo || [];
    const nNative = todo.filter((r) => r.state === 'native').length;
    box.appendChild(el('p', { class: 'hint', style: 'max-width:80ch',
      text: todo.length.toLocaleString() + ' recordings are VACC loaded: '
          + nNative.toLocaleString() + ' on the lab’s netfiles share, read '
          + 'in place, and ' + (todo.length - nNative).toLocaleString()
          + ' as copies in scratch. Whether this computer has them does '
          + 'not matter: the run happens where the data is and comes back '
          + 'here. Ones already run with these settings are marked.' }));

    const search = el('input', {
      type: 'search', class: 'inc-search', value: vaccFilter,
      placeholder: 'Type a mouse, session, date, project or “netfiles”',
      'aria-label': 'Search the recordings', 'data-fk': 'many-search',
    });
    let t = null;
    search.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(() => { vaccFilter = search.value; paint(); }, 160);
    });
    box.appendChild(search);
    box.appendChild(el('div', { class: 'dop-many-parts' }));
    return box;
  }

  function manyPickUpdate(node) {
    const inner = node.querySelector('.dop-many-parts');
    if (!inner || !vaccList || vaccList.error) return;
    const todo = vaccList.todo || [];
    const shown = todo.filter(rowMatches);
    BARRY.ui.sections(inner, [
      { key: 'tools', enter: false,
        sig: [oid(vaccList), vaccFilter, picked.size, pickRev],
        build: () => pickTools(todo, shown) },
      { key: 'list', enter: false, sig: [oid(vaccList), vaccFilter, pickRev],
        build: () => pickList(todo, shown) },
      { key: 'blocked', enter: false, sig: [oid(vaccList)],
        build: blockedPart },
    ]);
  }

  function pickTools(todo, shown) {
    const bulk = (fn) => () => { fn(); pickRev++; paint(); };
    return el('div', { class: 'tk-actions inc-pick-tools' }, [
      el('button', { class: 'btn ghost sm',
        text: 'Tick the ' + shown.length.toLocaleString() + ' shown',
        onclick: bulk(() => shown.forEach((r) => picked.add(r.gid))) }),
      el('button', { class: 'btn ghost sm', text: 'Only the ones not yet run',
        onclick: bulk(() => shown.forEach((r) => {
          if (r.answered) picked.delete(r.gid); else picked.add(r.gid);
        })) }),
      el('button', { class: 'btn ghost sm', text: 'Clear',
        disabled: picked.size ? null : 'disabled',
        onclick: bulk(() => picked.clear()) }),
      el('span', { class: 'hint quiet',
        text: picked.size.toLocaleString() + ' ticked · '
            + shown.length.toLocaleString() + ' of '
            + todo.length.toLocaleString() + ' shown' }),
    ]);
  }

  function pickList(todo, shown) {
    const list = el('div', { class: 'inc-pick-list',
                             'data-keep-scroll': 'many-list' });
    if (!shown.length) {
      list.appendChild(el('div', { class: 'empty-state',
        text: todo.length ? 'Nothing matches that. Clear the search to see '
                            + 'all ' + todo.length + '.'
          : 'Nothing is VACC loaded yet. In Sessions ▸ Everything VACC '
            + 'knows, add the recordings found on VACC or on netfiles, or '
            + 'upload some.' }));
    }
    for (const r of shown) {
      const on = picked.has(r.gid);
      const row = el('label', { class: 'inc-pick' + (r.answered ? ' done' : '')
                                         + (on ? ' on' : '') }, [
        el('input', {
          type: 'checkbox', checked: on ? 'checked' : null,
          'aria-label': 'Send ' + r.label,
          /* One tick changes one row, in place; only the counts and the
             cost line are rebuilt. */
          onchange: (e) => {
            if (e.target.checked) picked.add(r.gid); else picked.delete(r.gid);
            row.classList.toggle('on', e.target.checked);
            paint();
          },
        }),
        el('div', { class: 'ip-main' }, [
          el('span', { class: 'ip-name', text: r.label }),
          el('span', { class: 'ip-sub', text: rowSub(r) }),
        ]),
        // THE cluster mark (§6c): one renderer, never a chip of its own.
        BARRY.vacc.mark({ gid: r.gid }, { compact: true }) || el('span', {}),
        el('span', { class: 'ip-done',
                     text: r.answered ? 'already run' : '' }),
      ]);
      list.appendChild(row);
    }
    return list;
  }

  function blockedPart() {
    const box = el('div', {});
    const blocked = vaccList.blocked || [];
    const nBlocked = vaccList.blocked_total != null
      ? vaccList.blocked_total : blocked.length;
    if (!nBlocked) return box;
    box.appendChild(el('details', { class: 'inc-blocked',
                                    'data-keep': 'many-blocked' }, [
      el('summary', { text: nBlocked.toLocaleString()
                            + ' not VACC loaded, so left out' }),
      el('div', {}, blocked.map((b) => el('div', { class: 'hint quiet',
        text: b.label + ' — ' + b.why }))
        .concat(nBlocked > blocked.length
          ? [el('div', { class: 'hint quiet',
              text: 'and ' + (nBlocked - blocked.length) + ' more.' })]
          : [])),
    ]));
    /* The ones only missing from the cluster can be sent -- the same
       upload Sessions runs, re-planned afterwards. */
    if (BARRY.vacc && BARRY.vacc.uploadMissing) {
      const offer = BARRY.vacc.uploadMissing(blocked, () => {
        vaccList = null;
        paint();
      }, vaccList.upload_gids);
      if (offer) box.appendChild(offer);
    }
    return box;
  }

  /* "2. Detection, for every recording sent": the settings once for the
     whole batch, the cost before the primary (§6d: say the cost before it
     is spent; the primary is last and names what it does), and -- while a
     batch is out -- its recordings, each saying where it is. */
  function manyRunShell() {
    return el('div', { class: 'card' }, [
      el('div', { class: 'section-label',
                  text: '2. Detection, for every recording sent' }),
      el('div', { class: 'dop-many-run' }),
    ]);
  }

  function manyRunUpdate(node) {
    const inner = node.querySelector('.dop-many-run');
    if (!inner) return;
    const qs = JSON.stringify(paramsBody());
    const b = batchFlight();
    const pick = Array.from(picked).sort().join(',');
    BARRY.ui.sections(inner, [
      { key: 'params', enter: false, sig: [qs], build: params },
      { key: 'rule', enter: false, sig: [qs], build: manyRule },
      { key: 'cost', enter: false,
        sig: [qs, pick, oid(vaccList), b ? b.id : '', b ? flightWords(b) : ''],
        build: () => costLine(b) },
      b ? { key: 'batch', sig: [b.id, batchRowsSig(b)],
            build: () => batchRows(b) } : null,
      { key: 'go', enter: false,
        sig: [qs, pick, oid(vaccList), b ? b.id : '', vaccOn()],
        build: () => manyGo(b) },
    ]);
  }

  /* What each recording of a batch is given, in words. The channel lists
     themselves differ from recording to recording -- each has its own bad
     channels -- so they are written into each run's report and bank note,
     by name, and here the rule is said once. */
  function manyRule() {
    const r = chRange();
    const storm = q.method === 'storm';
    return el('p', { class: 'hint dop-many-rule', style: 'max-width:80ch',
      text: 'Channels, for each recording: '
          + (r ? rangeWords(r) + ' only' : 'every channel')
          + (storm && q.detect_on !== 'all'
            ? ', detection on the ' + q.detect_on + ' ones'
            : ', detection on every channel read')
          + ', its own bad channels left out'
          + (storm && q.car ? ', the rest read for the common reference' : '')
          + '. Each run’s report and bank note list every channel by name.' });
  }

  function chosenRows() {
    const todo = (vaccList && vaccList.todo) || [];
    const chosen = todo.filter((r) => picked.has(r.gid));
    return { chosen, fresh: chosen.filter((r) => !r.answered) };
  }

  function costLine(b) {
    if (b) {
      return el('p', { class: 'hint', style: 'max-width:80ch',
        text: 'A batch of ' + b.members.length + ' is on the cluster: '
            + flightWords(b) + '. Each recording lands in the list below as '
            + 'it finishes; you can leave this view, or reload, and it '
            + 'carries on.' });
    }
    const { chosen, fresh } = chosenRows();
    const secs = fresh.reduce((a, r) => a + ((r.plan || {}).seconds || 0), 0);
    const guessed = fresh.filter((r) => !(r.plan || {}).size_known).length;
    const native = fresh.some((r) => r.state === 'native');
    const cap = (vaccList && vaccList.cap) || 8;
    const queued = vaccList && vaccList.queued;
    return el('p', { class: 'hint', style: 'max-width:80ch',
      text: chosen.length
        ? (fresh.length.toLocaleString() + ' to run'
           + (chosen.length > fresh.length
             ? ', ' + (chosen.length - fresh.length) + ' already run with '
               + 'these settings and skipped' : '')
           + ' · as one array job, side by side on the cluster'
           + ' · about ' + human(secs) + ' of cluster time asked for in all'
           + (guessed ? ' (' + guessed + ' with no recorded length, sized as '
                        + 'an hour of 64 channels so they are not cut off)'
                      : '')
           + ' · ' + ((vaccList && vaccList.partition) || 'general')
           + ' partition'
           + (queued ? ' · ' + queued + ' ahead in the queue' : '')
           + (native ? ' · at most ' + cap + ' at once, because the netfiles '
                       + 'share slows under many readers' : '')
           + '.')
        : 'Tick the recordings to send, above.' });
  }

  function batchRowsSig(b) {
    return ((b.snap || {}).members || [])
      .map((m) => m.status + ':' + (m.step || '') + ':' + (m.error || ''))
      .join('|');
  }

  const MEMBER_WORDS = {
    waiting: 'waiting its turn', queued: 'in the cluster’s queue',
    running: 'on a node', done: 'landed', failed: 'failed',
  };

  function batchRows(b) {
    const ms = (b.snap || {}).members
      || b.members.map((m) => ({ id: m.gid, label: m.label, status: 'waiting' }));
    const box = el('div', { class: 'dop-batch' });
    for (const m of ms) {
      const st = m.status || 'waiting';
      const done = st === 'done';
      const r = done && (reviews || []).find((x) => x.gid === m.id);
      box.appendChild(el(r ? 'button' : 'div', {
        class: 'dop-batch-row ' + st,
        title: r ? 'Open this run' : null,
        onclick: r ? () => openRun(r) : null,
      }, [
        el('span', { class: 'dop-batch-dot', 'aria-hidden': 'true' }),
        el('span', { class: 'dop-batch-name', text: m.label || m.id }),
        el('span', { class: 'dop-batch-state',
          text: m.error ? ('failed: ' + m.error)
            : (m.cached ? 'already answered' : (MEMBER_WORDS[st] || st)) }),
        r ? el('span', { class: 'dop-batch-n',
                         text: (r.n || 0).toLocaleString() + ' IEDs' })
          : null,
      ].filter(Boolean)));
    }
    return box;
  }

  function manyGo(b) {
    if (b) {
      return el('div', { class: 'tk-actions dop-actions' }, [
        el('button', { class: 'btn ghost', text: 'Stop the batch',
          onclick: () => cancel(b.id) }),
        el('span', { class: 'spacer' }),
        el('button', { class: 'btn', text: 'On the cluster',
                       disabled: 'disabled' }),
      ]);
    }
    const { chosen, fresh } = chosenRows();
    return el('div', { class: 'tk-actions dop-actions' }, [
      chosen.length > fresh.length ? el('button', {
        class: 'btn ghost sm', text: 'Run the ones already run again too',
        title: 'Send every ticked recording, including the ones already run '
             + 'with these settings',
        onclick: () => runBatch(true),
      }) : null,
      el('span', { class: 'spacer' }),
      el('button', {
        class: 'btn',
        text: fresh.length ? 'Submit ' + fresh.length.toLocaleString()
                             + ' to VACC' : 'Nothing new to submit',
        disabled: (!fresh.length || !vaccOn()) ? 'disabled' : null,
        onclick: () => runBatch(false),
      }),
    ].filter(Boolean));
  }

  async function runBatch(force) {
    if (batchFlight()) return;
    const todo = (vaccList && vaccList.todo) || [];
    const send = todo.filter((r) => picked.has(r.gid)
                                    && (force || !r.answered));
    if (!send.length) return;
    try {
      const started = await apiPost('/api/doppler/batch',
        Object.assign({ gids: send.map((r) => r.gid), force: !!force },
                      paramsBody()));
      track(started.job, 'many',
            send.map((r) => ({ gid: r.gid, label: r.label })),
            { params: paramsBody() });
      if ((started.blocked || []).length) {
        toast(started.blocked.length + ' of them could not be sent: '
              + started.blocked.map((x) => x.label + ' (' + x.why + ')')
                .join('; '), 'warn', 12000);
      }
    } catch (e) { toast(e.message, 'err', 12000); }
    paint();
  }

  /* For a host that says when Doppler is put away. ToolKit does not today
     (core.js calls a VIEW's onHide, not a tool's), and that is deliberate
     for this timer: it follows runs on the cluster while you are elsewhere,
     so a run that lands is announced wherever you are, and it stops by
     itself when nothing is out. Stopping it cancels no run; showing the
     panel again asks the server what is out there. */
  function onHide() {
    stopLoop();
    attached = false;
  }

  return {
    paint, run, reset, onHide,
    _state: () => q,
    // For `_dev/storm.html`: the report's drawing and reading are checkable
    // without waiting forty minutes for the cluster to prove a canvas has
    // ink on it. The detector's own arithmetic is checked against the
    // MATLAB by tools/check_doppler_parity.py, which is where it belongs.
    _adopt: (out) => { res = out || null; snips = null; revealNext = false; },
    _res: () => res,
    _draw: () => drawPlots(false),
    _rasterAt: rasterAt,
    _rasterRows: () => (res ? rasterRows() : null),
    _bankNote: bankNote,
    _flights: () => Array.from(flights.values()).map((f) => ({
      id: f.id, kind: f.kind, status: (f.snap || {}).status })),
    _track: track,
    _follow: follow,
    _openRun: openRun,
  };
})();
