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
    // The picked registry row. A banked set has to say which animal and
    // session it belongs to, or it files itself under "Unfiled" and is
    // never found again.
    row: null,
    channels: null,       // null means every channel
    height_sd: 4.5,
    abs_uv: 300,
    dist_ms: 100,
    wlen_ms: 125,
    estimator: 'sd',
  };

  /* Toothy's own, from qparam.py. Named once so the "changed" tag and the
     reset cannot drift apart from what the fields start at. */
  const DEFAULTS = {
    height_sd: 4.5, abs_uv: 300, dist_ms: 100, wlen_ms: 125,
  };

  let est = null;        // what a scan would cost
  let job = null;        // the scan in flight
  let poll = null;
  let res = null;        // the finished scan
  let chosen = {};       // hilus / theta / ripple, after any correction
  let banking = false;
  let savingBad = false; // a bad-channel change on its way to the record
  let editorOpen = false;// the channel editor, kept open across repaints

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
  /* Listed in depth order, not in the order the code computes them.
     Theta sits at the fissure, the ripple channel in the pyramidal layer
     above the hilus, and the hilus below both -- so reading them down the
     panel reads them down the probe, which is how somebody looking at the
     traces beside it is already reading them. */
  const ROLES = [
    { key: 'theta', label: 'Theta', colour: '#3b82f6',
      why: 'most power in 6–10 Hz' },
    { key: 'ripple', label: 'Ripple', colour: '#22c55e',
      why: 'most ripple power relative to theta' },
    { key: 'hilus', label: 'Hilus (DS)', colour: '#e5484d',
      why: 'where the dentate spikes are detected' },
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
    pushLines();
  }

  /* ==================================================================
     The traces, in a window of their own
     ==================================================================
     Not by taking over XploreFinder in this window: that replaced the panel
     and left nowhere to go back to, and the lines had to be published into
     whatever recording happened to already be open -- which is why they
     sometimes did not appear at all.

     A window opens on the scanned recording because its URL says so, and
     closing it is the way back. The same arrangement Braid uses for its
     panels and its comodulogram. */
  let traceWin = null;

  function tracesOpen() {
    try { return !!(traceWin && !traceWin.closed); } catch (e) { return false; }
  }

  async function openTraces() {
    if (tracesOpen()) {
      try { traceWin.focus(); } catch (e) {}
      pushLines();
      return traceWin;
    }
    if (!q.path) return null;
    const url = traceUrl();
    traceWin = window.open(url, 'barry-incisor-traces',
                           'width=1180,height=900,menubar=no,toolbar=no');
    if (!traceWin) {
      toast('The traces window was blocked. Allow pop-ups for 127.0.0.1, '
            + 'then press “Show them on the traces” again.', 'err', 9000);
      return null;
    }
    paint();
    /* Waited for rather than assumed. The window is a whole app booting --
       it has to read the recording before it has lanes to draw a line on --
       and publishing into it early is how the lines went missing before. */
    const until = Date.now() + 60000;
    while (Date.now() < until) {
      if (!tracesOpen()) { paint(); return null; }
      if (pushLines()) { paint(); return traceWin; }
      await new Promise((r) => setTimeout(r, 250));
    }
    toast('The traces window did not finish opening that recording.',
          'err', 8000);
    return traceWin;
  }

  function traceUrl() {
    /* What it opens on.

       A CSD rather than the traces: this window exists to check a laminar
       landmark, and a landmark is a boundary -- the sink/source reversal at
       the fissure and the hilar sink are visible as bands on a CSD and are
       a matter of opinion on sixty-four stacked traces. Even channels,
       because a CSD wants one line of contacts at a known spacing and that
       is what the 32-channel probe on 64 inputs actually is. Five seconds,
       because a dentate spike is tens of milliseconds and a ten-second
       window puts three hundred of them in a pane.

       Starting points, not a cage: the window is the whole application and
       every one of them can be changed in it. */
    const args = new URLSearchParams({
      csc: q.path,
      panes: JSON.stringify([{ panel: 'csd' }]),
      even: '1',
      span: '5',
      chrome: 'notabs,noheads',
      role: 'incisor',
      theme: (BARRY.state && BARRY.state.theme) || 'dark',
    });
    return location.origin + '/?' + args.toString() + '#xplore';
  }

  /* Returns whether the lines actually landed, so the caller can keep
     waiting instead of believing it worked. */
  function pushLines() {
    if (!tracesOpen()) return false;
    let xf = null;
    try { xf = traceWin.barryXplore; } catch (e) { return false; }
    if (!xf || !xf.setChannelLines || !xf.current) return false;
    let sess = null;
    try { sess = xf.current(); } catch (e) { return false; }
    if (!sess) return false;
    try {
      xf.setChannelLines(sess, ROLES.map((r) => ({
        key: r.key, label: r.label, colour: r.colour,
        number: chosen[r.key] == null ? null : Number(chosen[r.key]),
        // Dragged in the other window, remembered in this one.
        onmove: (number) => { chosen[r.key] = number; paint(); },
      })).filter((x) => x.number != null));
    } catch (e) { return false; }
    return true;
  }

  function closeTraces() {
    if (tracesOpen()) { try { traceWin.close(); } catch (e) {} }
    traceWin = null;
    paint();
  }

  /* ==================================================================
     Painting
     ================================================================== */
  function paint() {
    const host = document.getElementById('tkResult');
    if (!host) return;
    /* Fails CLOSED. The first version was
     *   if (tk.tool && tk.tool() !== 'incisor') return;
     * which draws when it cannot tell which tool is open -- so a page
     * holding an older toolkit.js, where `tool` is not exported yet,
     * painted this panel over whatever was actually showing and threw from
     * inside it. The error then names Incisor's variables while the person
     * is looking at another tool, which is about as misleading as an error
     * can be. Not knowing is a reason not to draw.
     */
    const tk = BARRY.views.toolkit;
    if (!tk || typeof tk.tool !== 'function' || tk.tool() !== 'incisor') {
      return;
    }
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
        q.row = r;
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
    box.appendChild(selection());
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

  /* ---------------- what is being scanned ----------------
     Said out loud rather than left to be inferred from a channel count.
     Sixty-two channels on a sixty-four channel probe looks exactly like
     sixty-four unless the panel says two were dropped -- and the hilus,
     theta and ripple picks are argmaxes over whatever set was scanned, so
     what was left out is part of the answer rather than a detail of it. */
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
       you unable to tell that from a panel that never checked. */
    box.appendChild(el('p', { class: bad.length ? 'hint' : 'hint quiet',
      style: 'max-width:78ch',
      text: bad.length
        ? (bad.length + ' channel' + (bad.length === 1 ? '' : 's')
           + ' marked bad on this session '
           + (bad.length === 1 ? 'has' : 'have')
           + ' been removed from processing — '
           + bad.map((c) => c.label).join(', ')
           + '. They are not read at all, so they cannot win any of the '
           + 'three channel picks and no candidate comes off them.')
        : 'No channels are marked bad on this session, so every one of '
          + 'them is read.' }));

    /* How the file is read and how the probe is laid out. Neither changes
       when an event happened; both change which channels there were. */
    const scheme = p.channel_scheme || null;
    box.appendChild(el('p', { class: 'hint quiet', style: 'max-width:78ch',
      text: 'Probe configuration: ' + (p.probe_name || p.probe || 'H3')
          + '  ·  ' + (p.even_only ? 'even-numbered channels only'
                                        : 'every channel')
          + (p.n_csc_files ? ' of ' + p.n_csc_files + ' CSC files' : '')
          + '  ·  ' + (p.invert ? 'inverted, the lab convention'
                                     : 'not inverted') }));
    if (scheme && scheme.why) {
      box.appendChild(el('p', { class: 'hint quiet', style: 'max-width:78ch',
        text: 'Chosen by measurement: ' + scheme.why + '.' }));
    }

    box.appendChild(chanEditor(all, bad));
    return box;
  }

  /* Putting a channel back, or taking one out, and generating the times
     again.

     The tick writes through to the session record -- the same one the trace
     view reads and the same one every other tool honours -- rather than to
     a copy held in this panel, so a channel marked bad in either place is
     bad in both. */
  function chanEditor(all, bad) {
    const d = el('details', {
      class: 'inc-chan-edit', open: editorOpen ? 'open' : null,
      ontoggle: (e) => { editorOpen = e.target.open; },
    }, [
      el('summary', { text: 'Add or remove channels, and scan again' }),
      el('p', { class: 'hint quiet', style: 'max-width:74ch',
        text: 'Unticking a channel marks it bad for this session '
            + 'everywhere. Changing it discards the scan on purpose: every '
            + 'candidate time came out of reading a particular set of '
            + 'channels, and a result sitting under a selection it no '
            + 'longer matches is the kind of thing that gets banked by '
            + 'mistake. Press Scan to generate them again.' }),
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
    reset();            // the scan was made from a different set of channels
    editorOpen = true;  // survives the repaint, so you can untick two
    await refreshEstimate();
    paint();
  }

  function params() {
    /* Each number decides what counts as a dentate spike, so each says what
       it means and carries Toothy's own name for it -- `ds_height_thr` and
       the rest are what you would grep for in `qparam.py`, and a panel that
       renames them quietly makes that harder. */
    const FIELDS = [
      { key: 'height_sd', label: 'Height', unit: 'S.D.', step: 0.1,
        toothy: 'ds_height_thr',
        why: 'How far above this channel\u2019s own noise a peak has to '
           + 'reach. Multiplied by the standard deviation of its filtered '
           + 'trace, so it means the same thing on a quiet channel and a '
           + 'loud one.' },
      { key: 'abs_uv', label: 'Floor', unit: '\u00b5V', step: 10,
        toothy: 'ds_abs_thr',
        why: 'And never less than this, whatever the noise. Toothy\u2019s '
           + '0.3 mV. On a quiet channel this is what binds.' },
      { key: 'dist_ms', label: 'Min. spacing', unit: 'ms', step: 5,
        toothy: 'ds_dist_thr',
        why: 'Two peaks closer together than this are one event; the taller '
           + 'is kept.' },
      { key: 'wlen_ms', label: 'Width window', unit: 'ms', step: 5,
        toothy: 'ds_wlen',
        why: 'How far either side of a peak to look when measuring how wide '
           + 'it is. Does not decide what is detected \u2014 only what is '
           + 'recorded about it.' },
    ];

    const rows = FIELDS.map((f) => el('div', { class: 'inc-param' }, [
      el('div', { class: 'inc-param-head' }, [
        el('label', { class: 'inc-param-name' }, [
          el('span', { text: f.label }),
          el('input', {
            type: 'number', value: q[f.key], step: f.step,
            onchange: (e) => {
              const v = parseFloat(e.target.value);
              if (!isFinite(v)) { e.target.value = q[f.key]; return; }
              q[f.key] = v; refreshEstimate(); paint();
            },
          }),
          el('span', { class: 'inc-param-unit', text: f.unit }),
        ]),
        el('code', { class: 'inc-param-src', text: f.toothy,
                     title: 'Toothy\u2019s name for it, in qparam.py' }),
      ]),
      el('p', { class: 'inc-param-why', text: f.why }),
    ]));

    const changed = FIELDS.some((f) => q[f.key] !== DEFAULTS[f.key])
                    || q.estimator !== 'sd';

    return el('details', { class: 'incisor-params' }, [
      el('summary', {}, [
        el('span', { text: 'Detection parameters' }),
        el('span', { class: 'inc-param-tag',
                     text: changed ? 'changed' : 'Toothy\u2019s defaults' }),
      ]),
      el('div', { class: 'inc-param-body' }, [
        el('p', { class: 'hint quiet',
          text: 'These are the numbers that decide what counts as a dentate '
              + 'spike. The defaults are Toothy\u2019s own, from qparam.py, '
              + 'and a set detected with them is comparable with one of '
              + 'Toothy\u2019s.' }),
        el('div', { class: 'inc-params-grid' }, rows),
        el('div', { class: 'inc-param', style: 'grid-column:1/-1' }, [
          el('label', { class: 'comod-check' }, [
            el('input', {
              type: 'checkbox',
              checked: q.estimator === 'mad' ? 'checked' : null,
              onchange: (e) => {
                q.estimator = e.target.checked ? 'mad' : 'sd';
                refreshEstimate(); paint();
              },
            }),
            el('span', { text: 'Measure the noise with the median absolute '
                             + 'deviation' }),
          ]),
          el('p', { class: 'inc-param-why',
            text: 'Toothy uses the standard deviation, so that is the '
                + 'default and a number from it is comparable with a number '
                + 'from Toothy. The median absolute deviation is more '
                + 'robust \u2014 one large artifact raises the S.D. enough '
                + 'to hide every real event after it \u2014 but it is a '
                + 'departure from the reference, so it is asked for rather '
                + 'than assumed.' }),
        ]),
        changed ? el('div', { class: 'tk-actions' }, [
          el('button', {
            class: 'btn ghost sm', text: 'Back to Toothy\u2019s defaults',
            onclick: () => {
              Object.assign(q, DEFAULTS);
              q.estimator = 'sd';
              refreshEstimate(); paint();
            },
          }),
        ]) : null,
      ].filter(Boolean)),
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
    /* The question this step invites, answered before it is asked.

       The three picks are computed FROM the detection -- normalised
       amplitude x count for the hilus, band power for the other two -- so
       they cannot have fed back into it. Every channel was detected on
       separately and carries its own candidates; each time is that
       candidate's own sample index put through the .ncs record timestamps,
       which is one clock for the whole file. So switching a channel here
       swaps which set you are looking at, instantly and with nothing read
       again, and moves no event by a microsecond.

       What DOES move the picks is step 2: a channel added to or removed
       from the scan changes the set each argmax runs over. */
    box.appendChild(el('p', { class: 'hint quiet', style: 'max-width:78ch',
      text: 'Changing a channel here changes which candidates you are '
          + 'looking at, not when any of them happened — every channel '
          + 'was detected on separately, and every time came from the '
          + '.ncs record timestamps rather than from the channel. The picks '
          + 'came out of the scan, so switching one costs nothing and '
          + 'nothing is read again. To move the picks themselves, add or '
          + 'remove channels in step 2 and scan again.' }));
    const known = (est && est.known) || {};

    let unresolved = false;
    for (const r of ROLES) {
      const pick = (res.picked || {})[r.key];
      const was = known[KNOWN_KEY[r.key]];
      const clash = pick && was != null
                    && Number(was) !== Number(pick.number);
      const now = chosen[r.key];
      if (now == null) unresolved = true;

      /* The candidate count, on the hilus list only. That is the number
         that changes what step 4 banks, so seeing it in the list is the
         difference between choosing a channel and guessing at one. On the
         theta and ripple lists it would be the DS count, which has nothing
         to do with either pick, so it is left off. */
      const nOn = (c) => Number((res.n_by_channel || {})[String(c.index)] || 0);
      const opts = (res.channels || []).map((c) => el('option', {
        value: c.number,
        selected: Number(now) === Number(c.number) ? 'selected' : null,
        text: c.label + (c.bad ? '  (bad)' : '')
              + (r.key === 'hilus'
                  ? '  — ' + nOn(c) + ' candidate'
                    + (nOn(c) === 1 ? '' : 's')
                  : ''),
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
                pushLines(); paint();
              },
            }, [el('option', { value: '', text: '— choose —',
                               selected: now == null ? 'selected' : null })]
              .concat(opts)),
            pick ? el('button', {
              class: 'btn ghost sm', text: 'Reset',
              title: 'Back to what the scan chose: ' + pick.label,
              onclick: () => {
                chosen[r.key] = pick.number; pushLines(); paint();
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
        class: 'btn ghost',
        text: tracesOpen() ? 'Focus the traces window'
                           : 'Show them on the traces\u2026',
        title: 'Opens the recording in a window of its own with a line '
             + 'across each chosen channel. Drag a line to move it; close '
             + 'the window when you are done. This panel stays where it is.',
        onclick: openTraces,
      }),
      tracesOpen() ? el('button', {
        class: 'btn ghost sm', text: 'Close it', onclick: closeTraces,
      }) : null,
      unresolved ? el('span', { class: 'hint warn',
        text: 'Choose a channel above before banking.' }) : null,
    ].filter(Boolean)));
    /* What it opens on, before it opens.

       It is a starting point and all three can be changed in the window,
       but two of them are worth knowing in advance: on a probe where every
       channel carries signal, even-only shows half the contacts, and a pick
       on an odd channel then appears as a marked band at its own depth
       rather than as a line on a lane. Better said here than discovered
       there. */
    box.appendChild(el('p', { class: 'hint quiet', style: 'max-width:78ch',
      text: 'It opens on a CSD of the even-numbered channels over five '
          + 'seconds — a laminar boundary is a boundary, and it reads '
          + 'off a CSD where it is a matter of opinion on sixty-four '
          + 'stacked traces. All three can be changed in the window. A pick '
          + 'on a channel that view is not showing is marked at its own '
          + 'depth and labelled hidden.' }));
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
      /* A question, not a dead end. This is reached when the scan and the
         recording's own notes name different channels, and the panel
         deliberately picks neither -- so it has to say what to do next
         rather than leave a sentence with no verb in it. */
      box.appendChild(el('p', { class: 'hint',
        text: 'Pick the hilus channel in step 3 and the candidates on it '
            + 'appear here. Nothing is chosen for you because the scan and '
            + 'this recording’s own notes name different channels — look at '
            + 'them on the traces and decide.' }));
      box.appendChild(el('div', { class: 'tk-actions' }, [
        el('button', {
          class: 'btn ghost',
          text: tracesOpen() ? 'Focus the traces window'
                             : 'Show them on the traces\u2026',
          onclick: openTraces,
        }),
      ]));
      return box;
    }
    /* The count comes with the scan; the events themselves are fetched
       when they are needed. Shipping all sixty-four channels' events to
       draw one of them made a response large enough to be cut off in
       transit, which arrives as a 200 that will not parse. */
    const n = Number((res.n_by_channel || {})[String(row.index)] || 0);

    box.appendChild(el('p', { class: 'hint',
      text: n + ' candidate' + (n === 1 ? '' : 's')
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
        disabled: (banking || !n) ? 'disabled' : null,
        onclick: () => bank(row),
      }),
      el('span', { class: 'hint quiet',
        text: 'Banks them as an UNCURATED set and opens DS curation. '
            + 'Nothing is decided by this.' }),
    ]));
    return box;
  }

  async function bank(row) {
    const who = await BARRY.profile.who();
    if (!who) return;
    /* Fetched now rather than carried since the scan: out of the same cache
       the scan filled, so this costs a small request and no reading. */
    let evs;
    try {
      const got = await apiPost('/api/incisor/events',
                                body({ channel: row.index }));
      evs = got.events || [];
    } catch (e) {
      toast('Those candidates are no longer cached — run the scan again. ('
            + e.message + ')', 'err', 9000);
      return;
    }
    if (!evs.length) { toast('No candidates on that channel.', 'warn'); return; }
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
      const r = q.row || {};
      const added = await apiPost('/api/bank/add', {
        gid: q.gid,
        // Who this belongs to. Without it the entry is filed under
        // "Unfiled / m / s" and cannot be found by the animal it came from.
        project: r.project,
        mouse: r.mouse,
        session: r.session,
        session_key: r.key,
        session_loose_key: r.loose_key,
        session_label: r.label,
        duration_s: r.duration_s,
        type: 'ds',
        type_name: 'Dentate spike',
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

      /* `entry`, not `entry_id` -- and `replace` said out loud.
         A recording has one curation set per kind, so starting this one
         replaces whatever is there, and the route refuses unless the caller
         says it means to. Asked here rather than sent blindly: the set
         being replaced may be somebody's half-finished pass. */
      let existing = null;
      try {
        existing = await api('/api/curation/' + encodeURIComponent(q.gid)
                             + '/ds');
      } catch (e) { existing = null; }
      const had = ((existing || {}).set || {}).n || 0;
      if (had) {
        const go = await BARRY.confirm(
          'Replace the curation set on this recording?',
          el('div', { class: 'fix-facts' }, [
            el('p', { text: 'There is already a dentate spike set here with '
                + had + ' candidate(s) in it. Starting one from these '
                + 'candidates replaces it.' }),
            el('p', { class: 'hint quiet',
              text: 'The banked sets are untouched either way — this is '
                  + 'about which one is on the workbench. The one being '
                  + 'replaced can be started again from the bank.' }),
          ]), 'Replace it');
        if (!go) {
          toast('Banked, and left on the bench. Start it from the Event '
                + 'Bank when you are ready.', 'ok', 8000);
          banking = false; paint();
          return;
        }
      }
      await apiPost('/api/curation/from-bank', {
        gid: q.gid, kind: 'ds', entry: id, version: 0, replace: true,
      });
      await BARRY.curate.enter(q.gid, 'ds');
    } catch (e) {
      toast('Not banked: ' + e.message, 'err', 9000);
    }
    banking = false; paint();
  }

  return {
    paint, scan, reset,
    openTraces, closeTraces,
    _tracesOpen: tracesOpen,
    /* For the harness and for XploreFinder: what is selected now, and a way
       to set it without a mouse. */
    _state: () => ({ q, est, res, chosen }),
    /* The order the landmarks are listed in, the window's starting URL, and
       a way to mark a channel bad -- three things a harness has to read
       without a mouse or a pop-up blocker in the way. */
    _roles: () => ROLES.map((r) => r.key),
    _traceUrl: traceUrl,
    _setBad: setBadSet,
    _refresh: refreshEstimate,
    _choose: (key, number) => {
      chosen[key] = number == null ? null : Number(number);
      pushLines(); paint();
    },
  };
}());
