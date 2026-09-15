/* ==========================================================================
   incisor.js -- Incisor, the dentate spike detector.

   Dentate means "toothed", and an incisor is the sharp one. It is a hand
   port of Toothy's `ephys.get_ds_peaks`, checked against Toothy's own code
   on identical input: 4430 events across ten real and ten synthetic
   recordings, every one at the same sample.

   WHAT IT IS FOR
   Detection used to live outside the workbench. You left Jarvis, ran a PyQt
   application, and imported the result -- and that result was stamped in
   concatenated time, so every acquisition gap shifted the dentate spikes
   after it earlier by the cumulative gap. Eighty-two of the two hundred and
   forty-six recordings checked here have that problem. Incisor reads the
   `.ncs` files through Jarvis's own readers and stamps the recording's own
   clock, so a set it produces never needs the correction.

   THE SHAPE OF THE PANEL
   Four steps, in the order they happen, and each one has to finish before
   the next means anything:

     1. pick a recording
     2. scan -- detect on every channel, which is the only way the hilus
        estimate can be made, because that estimate is computed FROM the
        per-channel detection
     3. look at the channel it chose, and correct it
     4. bank the candidates and vet them in DS curation

   Step 3 is not a formality. Measured against Toothy over ten sessions: the
   detector agrees to the sample every time, and the CHANNEL was wrong in
   four of them -- usually by one or two, once by thirty-four. The margins
   are often single digits, because adjacent sites on a shank see the same
   spikes at slightly different amplitude and the pick is an argmax over a
   product of two normalised numbers. So this shows the margin, shows the
   runner-up, and refuses to choose when the recording's own anatomy
   disagrees with the scan.
   ========================================================================== */
'use strict';

BARRY.incisor = (function () {
  /* What is being asked for. Held here, not read off the DOM, so a redraw
     cannot lose a half-filled form. */
  const q = {
    gid: null,
    path: null,
    channels: null,       // null means every channel
    height_sd: 4.5,
    abs_uv: 300,
    dist_ms: 100,
    wlen_ms: 125,
    estimator: 'sd',
  };

  let est = null;        // what a scan would cost
  let job = null;        // the scan in flight
  let poll = null;
  let res = null;        // the finished scan
  let chosen = {};       // hilus / theta / ripple, after any correction
  let banking = false;

  const round2 = (v) => Math.round((v || 0) * 100) / 100;
  const human = (s) => (s == null ? ''
    : s < 1 ? 'a moment' : s < 90 ? Math.round(s) + ' s'
      : Math.round(s / 60) + ' min');
  const dur = (s) => {
    s = Math.max(0, s || 0);
    if (s < 90) return s.toFixed(1) + ' s';
    const m = Math.floor(s / 60);
    return m + ' min ' + Math.round(s - m * 60) + ' s';
  };

  /* The three landmarks, in Toothy's colours: DS red, ripple green, theta
     blue (`README.md:274`). Named once so the panel, the lines on the
     traces and the legend cannot drift apart. */
  const ROLES = [
    { key: 'hilus', label: 'Hilus (DS)', colour: '#e5484d',
      why: 'where the dentate spikes are detected' },
    { key: 'theta', label: 'Theta', colour: '#3b82f6',
      why: 'most power in 6–10 Hz' },
    { key: 'ripple', label: 'Ripple', colour: '#22c55e',
      why: 'most ripple power relative to theta' },
  ];
  /* Which registry field corroborates which pick. `fissure_channel` is the
     landmark the theta estimate is about -- the workbook records the
     fissure, and the theta channel is the one nearest it. */
  const KNOWN_KEY = { hilus: 'hilus_channel', theta: 'fissure_channel',
                      ripple: 'ripple_channel' };

  function reset() {
    est = null; res = null; chosen = {}; banking = false;
    if (poll) { clearInterval(poll); poll = null; }
    job = null;
  }

  /* ==================================================================
     Talking to the server
     ================================================================== */
  function body(extra) {
    return Object.assign({
      path: q.path,
      channels: q.channels,
      height_sd: q.height_sd,
      abs_uv: q.abs_uv,
      dist_ms: q.dist_ms,
      wlen_ms: q.wlen_ms,
      estimator: q.estimator,
    }, extra || {});
  }

  let estSeq = 0;
  async function refreshEstimate() {
    if (!q.path) { est = null; return; }
    const mine = ++estSeq;
    try {
      const got = await apiPost('/api/incisor/estimate', body());
      if (mine !== estSeq) return;
      est = got;
    } catch (e) {
      est = { error: e.message };
    }
    paint();
  }

  async function scan() {
    if (!q.path || job) return;
    let started;
    try {
      started = await apiPost('/api/incisor/scan', body());
    } catch (e) {
      toast(e.message, 'err', 9000);
      return;
    }
    if (started.cached) { adopt(started.result); paint(); return; }
    job = started.job;
    paint();
    clearInterval(poll);
    poll = setInterval(async () => {
      if (!job) { clearInterval(poll); return; }
      let got;
      try { got = await api('/api/cfc/job/' + job.id); } catch (e) { return; }
      job = got.job;
      paintStages();
      if (job.status === 'running') return;
      clearInterval(poll);
      const done = job; job = null;
      if (done.status === 'done') {
        try {
          adopt((await api('/api/cfc/result/' + done.id)).result);
        } catch (e) {
          toast('The scan finished but its result could not be read: '
                + e.message, 'err', 9000);
        }
      } else if (done.status === 'failed') {
        toast(done.error || 'The scan failed.', 'err', 10000);
      }
      paint();
    }, 400);
  }

  async function cancel() {
    if (!job) return;
    try { await apiPost('/api/cfc/job/' + job.id + '/cancel', {}); } catch (e) {}
  }

  /* What the scan chose, and what the recording already believed.

     Where the two agree, the channel is selected and says so. Where they
     disagree, NEITHER is selected: a disagreement between the anatomy
     somebody recorded and what this recording's own data says is a finding
     about the probe, not a tie to be broken automatically. */
  function adopt(out) {
    res = out;
    chosen = {};
    const known = (est && est.known) || {};
    for (const r of ROLES) {
      const pick = (out.picked || {})[r.key];
      const was = known[KNOWN_KEY[r.key]];
      if (pick && was != null && Number(was) !== Number(pick.number)) {
        chosen[r.key] = null;          // they disagree; ask
      } else if (pick) {
        chosen[r.key] = pick.number;
      }
    }
    publishLines();
  }

  /* ==================================================================
     The lines on XploreFinder
     ================================================================== */
  /* The point of the whole step: the chosen channels, drawn across the
     traces, draggable. XploreFinder owns the geometry -- it knows which
     lane a channel is on, because it drew them -- so this publishes what to
     mark and lets it do the marking. */
  function publishLines() {
    const xf = BARRY.views.xplore;
    if (!xf || !xf.setChannelLines) return;
    const sess = xf.current && xf.current();
    if (!sess || sess.path !== q.path) return;
    xf.setChannelLines(sess, ROLES.map((r) => ({
      key: r.key, label: r.label, colour: r.colour,
      number: chosen[r.key] == null ? null : Number(chosen[r.key]),
      onmove: (number) => { chosen[r.key] = number; publishLines(); paint(); },
    })).filter((x) => x.number != null || res));
  }

  async function openRecording() {
    if (!q.path) return;
    setView('xplore');
    const sess = await BARRY.views.xplore.open(q.path);
    if (sess) publishLines();
    return sess;
  }

  /* ==================================================================
     Painting
     ================================================================== */
  function paint() {
    const host = document.getElementById('tkResult');
    if (!host || (BARRY.views.toolkit.tool
                  && BARRY.views.toolkit.tool() !== 'incisor')) return;
    host.innerHTML = '';
    host.appendChild(head());
    host.appendChild(pickCard());
    if (est && est.plan) host.appendChild(planCard());
    if (job) host.appendChild(stageCard());
    if (res) host.appendChild(channelCard());
    if (res) host.appendChild(resultCard());
  }

  function head() {
    return el('div', { class: 'card' }, [
      el('div', { class: 'section-label', style: 'margin-top:0',
                  text: 'Incisor — dentate spike detection' }),
      el('p', { class: 'hint', style: 'max-width:78ch;line-height:1.6',
        text: 'A port of Toothy’s detector, checked against Toothy’s '
            + 'own code on identical input: 4430 events across twenty '
            + 'recordings, every one at the same sample. The difference is '
            + 'the clock — this reads the .ncs record timestamps, so a '
            + 'set from here already accounts for acquisition gaps and never '
            + 'needs the concatenation correction.' }),
    ]);
  }

  function pickCard() {
    const box = el('div', { class: 'card' });
    box.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: '1. Which recording' }));
    const rows = BARRY.views.toolkit.registryRows
      ? BARRY.views.toolkit.registryRows() : [];
    box.appendChild(BARRY.pickSession({
      rows, value: q.gid,
      placeholder: 'Type a mouse, session or date…',
      onpick: (r) => {
        q.gid = r.gid;
        q.path = (r.here || [])[0] || null;
        reset();
        refreshEstimate();
        paint();
      },
    }));
    if (q.path) {
      box.appendChild(el('p', { class: 'hint quiet', text: q.path }));
    }
    return box;
  }

  function planCard() {
    const p = est.plan || {};
    const c = est.continuity || {};
    const box = el('div', { class: 'card' });
    box.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: '2. Scan every channel' }));
    if (est.error) {
      box.appendChild(el('p', { class: 'warn-line', text: est.error }));
      return box;
    }
    box.appendChild(el('p', { class: 'hint',
      text: dur(p.span_s) + ' × ' + p.n_channels + ' channel'
          + (p.n_channels === 1 ? '' : 's') + '  ·  '
          + Math.round(p.megasamples).toLocaleString() + ' million samples'
          + '  ·  about ' + human(p.seconds)
          + (p.network ? '  ·  over the network' : '') }));
    /* The recording's own condition, because it decides whether the times
       this produces mean anything. */
    box.appendChild(el('p', { class: 'hint quiet',
      text: c.n_segments + ' segment' + (c.n_segments === 1 ? '' : 's')
          + (c.seconds_lost ? ', ' + c.seconds_lost.toFixed(2)
                              + ' s lost to gaps' : ', no gaps')
          + (c.n_short_inside ? ', ' + c.n_short_inside
                                + ' short record(s) inside a segment' : '')
          + '  ·  clock good to '
          + Math.round(c.residual_sd_us || 0) + ' µs' }));
    if ((c.mismatches || []).length) {
      box.appendChild(el('p', { class: 'warn-line',
        text: 'The channels checked for gaps disagree with one another, so '
            + 'there is no single clock to stamp events on. Nothing will '
            + 'be detected until that is resolved.' }));
      return box;
    }
    box.appendChild(el('div', { class: 'tk-actions' }, [
      el('button', {
        class: 'btn', text: job ? 'Scanning…' : 'Scan',
        disabled: job ? 'disabled' : null, onclick: scan,
      }),
      el('span', { class: 'hint quiet',
        text: est.cached ? 'Already scanned — this will be instant.'
          : 'Detects on every channel. That is not wasteful: the hilus '
            + 'estimate is computed from the per-channel counts, so there '
            + 'is no cheaper way to make it.' }),
    ]));
    box.appendChild(params());
    return box;
  }

  function params() {
    const num = (key, label, step, title) => el('label', {
      class: 'comod-field', title: title,
    }, [
      el('span', { text: label }),
      el('input', {
        type: 'number', value: q[key], step: step,
        onchange: (e) => {
          const v = parseFloat(e.target.value);
          if (!isFinite(v)) { e.target.value = q[key]; return; }
          q[key] = v; refreshEstimate(); paint();
        },
      }),
    ]);
    return el('details', { class: 'incisor-params' }, [
      el('summary', { text: 'Detection parameters' }),
      el('p', { class: 'hint quiet',
        text: 'Toothy’s defaults, from qparam.py. Changing one changes '
            + 'what counts as a dentate spike.' }),
      el('div', { class: 'comod-row' }, [
        num('height_sd', 'Height (S.D.)', 0.1,
            'Peak height in standard deviations of this channel’s '
            + 'filtered trace. Toothy’s ds_height_thr.'),
        num('abs_uv', 'Floor (µV)', 10,
            'Absolute minimum height. Toothy’s ds_abs_thr of 0.3 mV.'),
        num('dist_ms', 'Min. spacing (ms)', 5,
            'Minimum interval between events. Toothy’s ds_dist_thr.'),
        num('wlen_ms', 'Width window (ms)', 5,
            'Window for evaluating peak width. Toothy’s ds_wlen.'),
      ]),
      el('label', { class: 'comod-check',
        title: 'Toothy uses the standard deviation, so that is the default '
             + 'and a number from it is comparable with a number from '
             + 'Toothy. The median absolute deviation is more robust — '
             + 'one large artifact raises the S.D. enough to hide every '
             + 'real event after it — but it is a deviation from the '
             + 'reference, so it is asked for rather than assumed.' }, [
        el('input', {
          type: 'checkbox', checked: q.estimator === 'mad' ? 'checked' : null,
          onchange: (e) => {
            q.estimator = e.target.checked ? 'mad' : 'sd';
            refreshEstimate(); paint();
          },
        }),
        el('span', { text: 'Use the median absolute deviation instead of '
                         + 'the S.D. (not what Toothy does)' }),
      ]),
    ]);
  }

  /* ---------------- the scan in flight ---------------- */
  function stageCard() {
    const box = el('div', { class: 'card comod-run' });
    box.appendChild(el('div', { class: 'comod-run-head' }, [
      el('strong', { text: 'Scanning every channel' }),
      el('span', { class: 'hint', text: (est && est.plan)
        ? dur(est.plan.span_s) + ' × ' + est.plan.n_channels + ' channels'
        : '' }),
      el('div', { style: 'flex:1' }),
      el('button', { class: 'btn ghost sm', text: 'Cancel', onclick: cancel }),
    ]));
    box.appendChild(el('div', { class: 'comod-stages', id: 'incStages' }));
    box.appendChild(el('div', { class: 'comod-total' }, [
      el('div', { class: 'comod-bar' }, [
        el('div', { class: 'comod-bar-fill', id: 'incBarFill' }),
      ]),
      el('span', { class: 'comod-eta', id: 'incEta' }),
    ]));
    setTimeout(paintStages, 0);
    return box;
  }

  /* Reading is nearly all of it: the detection happens interleaved with it
     to keep one channel in memory at a time, so the second stage is a count
     of channels finished rather than a phase with a duration. */
  const WEIGHT = { 'ds read': 40, 'ds detect': 1 };

  function paintStages() {
    const host = document.getElementById('incStages');
    if (!host || !job) return;
    const stages = job.stages || [];
    const w = stages.map((s) => WEIGHT[s.name] || 1);
    const total = w.reduce((a, b) => a + b, 0) || 1;
    let done = 0;
    host.innerHTML = '';
    stages.forEach((s, i) => {
      const running = s.status === 'running';
      const frac = s.of ? Math.min(s.done / s.of, 1) : 0;
      done += w[i] * (s.status === 'done' ? 1 : frac);
      host.appendChild(el('div', {
        class: 'comod-stage' + (running ? ' on' : '')
               + (s.status === 'done' ? ' done' : '')
               + (s.status === 'failed' ? ' bad' : ''),
      }, [
        el('span', { class: 'comod-tick',
          text: s.status === 'done' ? '✓' : running ? '▸'
            : s.status === 'failed' ? '✗' : '' }),
        el('span', { class: 'comod-stage-name',
          text: s.name === 'ds read'
            ? 'Read and decimate to 1 kHz'
            : 'Detect and rank the channels' }),
        el('span', { class: 'comod-stage-count',
          text: s.of > 1 ? ((s.status === 'waiting' ? '–'
            : s.done.toLocaleString()) + ' / ' + s.of.toLocaleString()
            + ' ' + s.unit) : '' }),
        running && s.of > 1
          ? el('div', { class: 'comod-mini' }, [
              el('div', { class: 'comod-mini-fill',
                          style: 'width:' + (frac * 100).toFixed(1) + '%' })])
          : null,
        el('span', { class: 'comod-stage-time',
          text: s.seconds != null ? s.seconds.toFixed(2) + ' s' : '' }),
      ].filter(Boolean)));
    });
    const fill = document.getElementById('incBarFill');
    if (fill) fill.style.width = (100 * done / total).toFixed(1) + '%';
    const eta = document.getElementById('incEta');
    if (eta) {
      eta.textContent = job.eta_s != null ? 'about ' + human(job.eta_s)
        + ' left' : (job.status === 'running' ? 'working it out' : '');
    }
  }

  /* ---------------- step 3: the channel ---------------- */
  function channelCard() {
    const box = el('div', { class: 'card' });
    box.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: '3. Which channel' }));
    const known = (est && est.known) || {};

    let unresolved = false;
    for (const r of ROLES) {
      const pick = (res.picked || {})[r.key];
      const was = known[KNOWN_KEY[r.key]];
      const clash = pick && was != null
                    && Number(was) !== Number(pick.number);
      const now = chosen[r.key];
      if (now == null) unresolved = true;

      const opts = (res.channels || []).map((c) => el('option', {
        value: c.number,
        selected: Number(now) === Number(c.number) ? 'selected' : null,
        text: c.label + (c.bad ? '  (bad)' : ''),
      }));

      box.appendChild(el('div', { class: 'inc-role' }, [
        el('i', { class: 'inc-dot', style: 'background:' + r.colour }),
        el('div', { class: 'inc-role-main' }, [
          el('div', { class: 'inc-role-head' }, [
            el('strong', { text: r.label }),
            el('select', {
              onchange: (e) => {
                chosen[r.key] = e.target.value === ''
                  ? null : parseInt(e.target.value, 10);
                publishLines(); paint();
              },
            }, [el('option', { value: '', text: '— choose —',
                               selected: now == null ? 'selected' : null })]
              .concat(opts)),
            pick ? el('button', {
              class: 'btn ghost sm', text: 'Reset',
              title: 'Back to what the scan chose: ' + pick.label,
              onclick: () => {
                chosen[r.key] = pick.number; publishLines(); paint();
              },
            }) : null,
          ].filter(Boolean)),
          el('p', { class: 'hint quiet',
            text: pick
              ? ('the scan chose ' + pick.label + ' — ' + pick.how
                 + ', ahead of the next by '
                 + (100 * pick.margin).toFixed(0) + '%')
              : 'the scan could not choose one' }),
          (was != null && pick)
            ? el('p', { class: clash ? 'warn-line' : 'hint quiet',
                text: clash
                  ? ('This recording is on file as CSC' + was + ' for this '
                     + 'landmark and the scan says ' + pick.label + '. '
                     + 'Neither is selected: a disagreement between the '
                     + 'anatomy somebody recorded and what this recording’s '
                     + 'own data says is worth a look, not a coin toss.')
                  : ('agrees with the CSC' + was + ' on file for this '
                     + 'recording') })
            : null,
          (pick && !clash && pick.margin < 0.1)
            ? el('p', { class: 'hint warn',
                text: 'Only ' + (100 * pick.margin).toFixed(0) + '% ahead of '
                    + 'the next channel. Adjacent sites see the same spikes '
                    + 'at slightly different amplitude, so a margin this '
                    + 'small is close to a tie — worth checking on the '
                    + 'traces.' })
            : null,
        ].filter(Boolean)),
      ]));
    }

    box.appendChild(el('div', { class: 'tk-actions' }, [
      el('button', {
        class: 'btn ghost', text: 'Show them on the traces',
        title: 'Opens the recording in XploreFinder with a line across each '
             + 'chosen channel. Drag one to move it.',
        onclick: openRecording,
      }),
      unresolved ? el('span', { class: 'hint warn',
        text: 'Choose a channel above before banking.' }) : null,
    ].filter(Boolean)));
    return box;
  }

  /* ---------------- step 4: bank and vet ---------------- */
  function resultCard() {
    const hil = chosen.hilus;
    const row = (res.channels || []).find(
      (c) => Number(c.number) === Number(hil));
    const box = el('div', { class: 'card' });
    box.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: '4. Bank the candidates' }));
    if (!row) {
      box.appendChild(el('p', { class: 'hint quiet',
        text: 'Choose a hilus channel above first.' }));
      return box;
    }
    const evs = ((res.by_channel || {})[String(row.index)]) || [];

    box.appendChild(el('p', { class: 'hint',
      text: evs.length + ' candidate' + (evs.length === 1 ? '' : 's')
          + ' on ' + row.label + '  ·  threshold '
          + (row.thr_uv || 0).toFixed(1) + ' µV ('
          + (row.thr_source === 'sd'
              ? (q.height_sd + ' × ' + (row.sd_uv || 0).toFixed(1)
                 + ' µV S.D.')
              : row.thr_source === 'override' ? 'set by hand'
                : 'the ' + q.abs_uv + ' µV floor, which is higher here')
          + ')' }));
    if (row.n_near_stitch) {
      box.appendChild(el('p', { class: 'hint warn',
        text: row.n_near_stitch + ' of them sit within a filter length of a '
            + 'gap in the recording, so they may be the filter ringing '
            + 'against the step rather than dentate spikes. They are banked '
            + 'and flagged, not dropped.' }));
    }

    box.appendChild(el('details', {}, [
      el('summary', { text: 'Every channel, as the scan ranked them' }),
      el('p', { class: 'hint quiet',
        text: 'The pick is an argmax over normalised amplitude × count, '
            + 'so a channel that lost narrowly lost on one of those two. '
            + 'Both are here.' }),
      el('div', { class: 'psd-table-scroll' }, [
        el('table', { class: 'psd-table' }, [
          el('thead', {}, [el('tr', {},
            ['channel', 'events', 'rate Hz', 'mean µV',
             'threshold µV', 'S.D. µV', 'score'].map(
              (t) => el('th', { text: t })))]),
          el('tbody', {}, (res.channels || []).slice()
            .sort((a, b) => (b.score || 0) - (a.score || 0))
            .map((c) => el('tr', {
              class: Number(c.number) === Number(hil) ? 'on' : '',
            }, [
              el('td', {}, [el('span', { text: c.label })]),
              el('td', { text: String(c.n) }),
              el('td', { text: (c.rate_hz || 0).toFixed(3) }),
              el('td', { text: (c.mean_amp || 0).toFixed(0) }),
              el('td', { text: (c.thr_uv || 0).toFixed(0) }),
              el('td', { text: (c.sd_uv || 0).toFixed(1) }),
              el('td', { text: (c.score || 0).toFixed(3) }),
            ]))),
        ]),
      ]),
    ]));

    box.appendChild(el('div', { class: 'tk-actions' }, [
      el('button', {
        class: 'btn', text: banking ? 'Banking…' : 'Bank and vet…',
        disabled: (banking || !evs.length) ? 'disabled' : null,
        onclick: () => bank(row, evs),
      }),
      el('span', { class: 'hint quiet',
        text: 'Banks them as an UNCURATED set and opens DS curation. '
            + 'Nothing is decided by this.' }),
    ]));
    return box;
  }

  async function bank(row, evs) {
    const who = await BARRY.profile.who();
    if (!who) return;
    const ok = await BARRY.confirm(
      'Bank ' + evs.length + ' candidate(s) from ' + row.label + '?',
      el('div', { class: 'fix-facts' }, [
        el('p', { text: 'They go in as a detector’s output, not as a '
            + 'curated set — nothing is decided, and the next step is '
            + 'vetting them in DS curation.' }),
        el('ul', { class: 'fix-steps' }, [
          el('li', { text: 'Times are on the recording’s own clock, so '
              + 'this set never needs the concatenation correction.' }),
          el('li', { text: 'Every detection parameter is recorded with them, '
              + 'so the set can say how it was made.' }),
          el('li', { text: 'Re-running the detector later reuses the ids of '
              + 'candidates at the same times, so decisions survive.' }),
        ]),
      ]), 'Bank them');
    if (!ok) return;
    banking = true; paint();
    try {
      const added = await apiPost('/api/bank/add', {
        gid: q.gid,
        type: 'ds',
        name: 'Incisor ' + row.label,
        pipeline: 'Incisor (dentate spike)',
        added_by: who,
        session_path: q.path,
        parameters: Object.assign({}, res.params, {
          channel: row.number, channel_label: row.label,
        }),
        events: evs.map((e) => ({
          start: e.start, channel: e.channel, amplitude: e.amp,
        })),
      });
      const id = (added.entry || {}).id || added.id;
      toast(evs.length + ' candidate(s) banked.', 'ok');
      await apiPost('/api/curation/from-bank',
                    { entry_id: id, gid: q.gid, kind: 'ds' });
      await BARRY.curate.enter(q.gid, 'ds');
    } catch (e) {
      toast('Not banked: ' + e.message, 'err', 9000);
    }
    banking = false; paint();
  }

  return {
    paint, scan, reset, openRecording,
    /* For the harness and for XploreFinder: what is selected now, and a way
       to set it without a mouse. */
    _state: () => ({ q, est, res, chosen }),
    _choose: (key, number) => {
      chosen[key] = number == null ? null : Number(number);
      publishLines(); paint();
    },
  };
}());
