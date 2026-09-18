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
    /* Which half of the tool is showing: this computer, or the cluster.
       Local until VACC Mode is on and somebody asks for the other one. */
    tab: 'local',
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

  async function scan(force, where) {
    if (!q.path || job) return;
    let started;
    try {
      started = await apiPost('/api/incisor/scan',
                              body(where ? { where: where } : null));
    } catch (e) {
      toast(e.message, 'err', 9000);
      return;
    }
    // A result already in hand, from either machine. The cluster's answers
    // go into the same cache under the same key, so this branch does not
    // care which one computed it -- which is the whole point.
    if (started.cached) { adopt(started.result); paint(); return; }
    job = started.job;
    // The rail pulses while the cluster is actually working, and only then.
    if (where && BARRY.vaccBusy) BARRY.vaccBusy.start();
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
      if (where && BARRY.vaccBusy) BARRY.vaccBusy.stop();
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
    host.appendChild(tabs());

    if (q.tab === 'vacc') {
      /* The cluster half. Same detector, same plots, same bank -- the only
         thing that differs is that the reading happens somewhere else and
         that many recordings can go at once.

         Separate from the local half rather than mixed into it, because
         "run this one here" and "run these thirty over there" are different
         acts with different answers to "what will this cost", and a single
         panel that tried to be both kept having to say which one it meant. */
      host.appendChild(vaccPickCard());
      if (batchJob) host.appendChild(batchCard());
      host.appendChild(reviewCard());
    } else {
      host.appendChild(pickCard());
      if (est && est.plan) host.appendChild(planCard());
      if (job) host.appendChild(stageCard());
      if (res) host.appendChild(channelCard());
      if (res) host.appendChild(resultCard());
    }
    /* Drawn now, and again on the next frame.

       Now, because a frame is not guaranteed to come: `requestAnimationFrame`
       does not fire in a background tab, and a panel whose plots are blank
       until you look at it twice is worse than one that costs a layout. The
       nodes are in the live document by this point, so reading
       `clientWidth` flushes layout and the canvas sizes correctly -- which
       is the thing the rAF was there to wait for.

       And again on the next frame, because the first measurement can still
       be taken before a scrollbar appears or a webfont settles, and the
       second one is a redraw of three small canvases from data already in
       hand. Found by a harness: after a repick the canvases were still at
       the HTML default 300x150 with nothing on them, because under a
       virtual-time budget the rAF had not run yet. */
    if (res) { wirePlots(); drawPlots(); requestAnimationFrame(drawPlots); }
  }

  /* ==================================================================
     The batch, and the queue it leaves behind
     ==================================================================
     Sending thirty recordings to the cluster is easy. The part that needed
     thinking about is what comes back, because a batch that banks its own
     answers is a batch nobody looks at -- and banking has a person's name
     on it.

     So a finished scan is a row here, and reviewing one does not need a
     second way to render a scan: selecting it points the panel at that
     recording and re-runs, which comes straight back out of the vault as a
     cache hit. The three plots, the hilus pick and the bank button are then
     the ordinary ones, on the ordinary path, which is why they behave the
     same whether the numbers were computed here or on a compute node.
     ================================================================== */
  let reviews = null;        // null until asked for
  let batchJob = null;
  let batchPoll = null;
  let openGid = null;        // which review row is expanded, if any
  let vaccList = null;       // what the cluster can reach, per recording
  const picked = new Set();  // gids ticked for a run

  /* The two halves, and which one is showing.

     A tab rather than a switch inside one panel: the local half answers
     "scan this recording" and the cluster half answers "scan these thirty",
     and a control that silently changed which question was being asked kept
     producing the other one's answer.

     The VACC tab is only reachable while VACC Mode is on -- which is what
     the mode is FOR. It is never the only way to reach something, because
     everything it does to one recording the local tab also does. */
  function tabs() {
    const on = vaccOn();
    if (!on && q.tab === 'vacc') q.tab = 'local';
    const bar = el('div', { class: 'inc-tabs' });
    const mk = (id, label, sub, enabled) => el('button', {
      class: 'inc-tab' + (q.tab === id ? ' on' : '')
             + (enabled ? '' : ' locked'),
      disabled: enabled ? null : 'disabled',
      title: enabled ? sub
        : 'Turn VACC Mode on in the bar at the bottom left to run these on '
          + 'the cluster.',
      onclick: () => { q.tab = id; paint(); },
    }, [
      el('strong', { text: label }),
      el('span', { text: enabled ? sub : 'VACC Mode is off' }),
    ]);
    bar.appendChild(mk('local', 'This computer',
                       'one recording at a time', true));
    bar.appendChild(mk('vacc', 'VACC',
                       'many at once, on the cluster', on));
    return bar;
  }

  /* ---------------- which recordings, on the cluster ----------------

     The recordings this lab already knows about, marked with what the
     cluster makes of each -- not a separate list of cluster things. A
     recording is the same recording whichever machine can read it, and a
     second inventory to keep in step with the registry would be a second
     thing to be wrong.

     "Scan all on VACC" was the first version of this and it was a bad
     control: it did not say what it was about to do, there was no way to
     leave one out, and the answer to "which thirty?" was buried in a
     route. Picking is the point. */
  async function loadVaccList() {
    try {
      const got = await api('/api/incisor/batch/plan');
      vaccList = got;
      // Everything runnable, ticked. The common case is "do the lot", and
      // un-ticking three is less work than ticking twenty-five.
      picked.clear();
      for (const r of (got.todo || [])) picked.add(r.gid);
    } catch (e) {
      vaccList = { todo: [], blocked: [], error: e.message };
    }
    paint();
  }

  function vaccPickCard() {
    const box = el('div', { class: 'card' });
    box.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: '1. Which recordings' }));
    if (!vaccList) {
      box.appendChild(el('p', { class: 'hint quiet',
                                text: 'Asking the cluster what it can read…' }));
      loadVaccList();
      return box;
    }
    if (vaccList.error) {
      box.appendChild(el('p', { class: 'warn-line', text: vaccList.error }));
      return box;
    }
    const todo = vaccList.todo || [];
    const blocked = vaccList.blocked || [];
    const doneGids = new Set((reviews || []).map((r) => r.gid));

    box.appendChild(el('p', { class: 'hint', style: 'max-width:78ch',
      text: todo.length + ' of the recordings Jarvis knows about are readable '
          + 'from the cluster. Ones already scanned with these settings are '
          + 'marked — running them again costs nothing, because the answer '
          + 'comes back out of the store rather than being recomputed.' }));

    const head = el('div', { class: 'tk-actions' }, [
      el('button', { class: 'btn ghost sm', text: 'All',
        onclick: () => { todo.forEach((r) => picked.add(r.gid)); paint(); } }),
      el('button', { class: 'btn ghost sm', text: 'None',
        onclick: () => { picked.clear(); paint(); } }),
      el('button', { class: 'btn ghost sm', text: 'Only the unscanned',
        onclick: () => { picked.clear();
                         todo.forEach((r) => { if (!doneGids.has(r.gid)) picked.add(r.gid); });
                         paint(); } }),
      el('span', { class: 'hint quiet', text: picked.size + ' selected' }),
    ]);
    box.appendChild(head);

    const list = el('div', { class: 'inc-pick-list' });
    for (const r of todo) {
      const done = doneGids.has(r.gid);
      list.appendChild(el('label', { class: 'inc-pick' + (done ? ' done' : '') }, [
        el('input', {
          type: 'checkbox', checked: picked.has(r.gid) ? 'checked' : null,
          onchange: (e) => { if (e.target.checked) picked.add(r.gid);
                             else picked.delete(r.gid); paint(); },
        }),
        el('span', { class: 'ip-name', text: r.label }),
        el('span', { class: 'ip-where', text: 'on VACC',
                     title: r.remote || '' }),
        el('span', { class: 'ip-done', text: done ? 'scanned' : '' }),
      ]));
    }
    box.appendChild(list);

    if (blocked.length) {
      box.appendChild(el('details', { class: 'inc-blocked' }, [
        el('summary', { text: blocked.length + ' left out' }),
        el('div', {}, blocked.map((b) => el('div', { class: 'hint quiet',
          text: b.label + ' — ' + b.why }))),
      ]));
    }

    box.appendChild(el('div', { class: 'tk-actions' }, [
      el('button', {
        class: 'btn',
        text: batchJob ? 'Running…'
            : ('Scan ' + picked.size + ' on VACC'),
        disabled: (batchJob || !picked.size) ? 'disabled' : null,
        onclick: startBatch,
      }),
      batchJob ? el('button', { class: 'btn ghost', text: 'Stop',
        onclick: () => apiPost('/api/cfc/job/' + batchJob.id + '/cancel', {}) })
        : null,
      el('span', { class: 'hint quiet',
        text: 'They go as one job array, so the cluster runs them side by '
            + 'side rather than one after another.' }),
    ].filter(Boolean)));
    return box;
  }

  async function loadReviews() {
    try {
      const got = await api('/api/incisor/reviews');
      reviews = got.reviews || [];
    } catch (e) {
      reviews = [];
    }
    paint();
  }

  async function startBatch() {
    if (batchJob) return;
    let started;
    try {
      started = await apiPost('/api/incisor/batch',
                              body({ gids: Array.from(picked) }));
    } catch (e) {
      toast(e.message, 'err', 9000);
      return;
    }
    batchJob = started.job;
    if (BARRY.vaccBusy) BARRY.vaccBusy.start();
    paint();
    clearInterval(batchPoll);
    batchPoll = setInterval(async () => {
      if (!batchJob) { clearInterval(batchPoll); return; }
      let got;
      try { got = await api('/api/cfc/job/' + batchJob.id); } catch (e) { return; }
      batchJob = got.job;
      paint();
      if (batchJob.status === 'running') return;
      clearInterval(batchPoll);
      if (BARRY.vaccBusy) BARRY.vaccBusy.stop();
      const done = batchJob; batchJob = null;
      if (done.status === 'failed') toast(done.error || 'The batch failed.',
                                          'err', 10000);
      loadReviews();
    }, 900);
  }

  async function toggleReview(r) {
    if (openGid === r.gid) { openGid = null; res = null; paint(); return; }
    openGid = r.gid;
    await openReview(r);
  }

  async function openReview(r) {
    if (!r.local) {
      toast('That recording was scanned on the cluster, and this computer '
            + 'has no path to it — so its plots cannot be drawn here.',
            'err', 9000);
      return;
    }
    q.path = r.local;
    q.gid = r.gid;
    /* The registry row travels with the review, and it is not decoration:
       `bank` reads project, mouse and session off it, and an entry without
       them files itself under "Unfiled" and can never be found by the
       animal it came from. Opening a review is the only way into banking
       that does not go through the session picker, so this is the only
       place that row can come from. */
    q.row = r.row || null;
    res = null;
    await refreshEstimate();
    // Comes back cached, out of the vault, on either machine's answer.
    await scan();
  }

  function batchCard() {
    const box = el('div', { class: 'card' });
    box.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: '2. On the cluster' }));
    box.appendChild(batchRows());
    return box;
  }

  function reviewCard() {
    const box = el('div', { class: 'card' });
    box.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: '3. Look at them, then bank' }));
    box.appendChild(el('p', { class: 'hint', style: 'max-width:78ch',
      text: 'Nothing is banked on its own. Open one, read the three plots, '
          + 'take the pick or move it, and send it — a set goes to the bank '
          + 'under your name or not at all.' }));
    if (!reviews) { loadReviews(); }
    box.appendChild(reviewRows());
    return box;
  }

  function batchRows() {
    const ms = (batchJob && batchJob.members) || [];
    const wrap = el('div', { class: 'inc-batch' });
    const n = ms.length;
    const done = ms.filter((m) => m.status === 'done').length;
    wrap.appendChild(el('div', { class: 'hint quiet',
      text: done + ' of ' + n + ' done' }));
    for (const m of ms) {
      if (m.status === 'waiting') continue;
      wrap.appendChild(el('div', { class: 'inc-batch-row ' + (m.status || '') }, [
        el('span', { class: 'ib-name', text: m.label || m.id }),
        el('span', { class: 'ib-state',
          text: m.error ? m.error
              : m.cached ? 'already answered'
              : (m.step || m.status || '') }),
      ]));
    }
    return wrap;
  }

  function reviewRows() {
    const wrap = el('div', { class: 'inc-reviews' });
    if (!reviews) {
      wrap.appendChild(el('p', { class: 'hint quiet', text: 'Loading…' }));
      return wrap;
    }
    if (!reviews.length) {
      wrap.appendChild(el('p', { class: 'hint quiet',
        text: 'Nothing scanned yet.' }));
      return wrap;
    }
    for (const r of reviews) {
      const hil = (r.picked || {}).hilus || {};
      const on = openGid === r.gid;
      wrap.appendChild(el('button', {
        class: 'inc-review' + (on ? ' on' : '') + (r.banked ? ' banked' : ''),
        onclick: () => toggleReview(r),
      }, [
        el('span', { class: 'ir-name', text: r.label || r.gid }),
        el('span', { class: 'ir-pick',
          text: hil.label ? ('hilus ' + hil.label) : 'no hilus pick' }),
        // How clear-cut the argmax was. A margin near zero means the plots
        // are the answer and the number is a coin toss.
        /* A small margin is the interesting case, not a defect: it means
           the two top channels scored almost the same and the argmax could
           have gone either way. Measured on this lab's first batch, the
           margins were 1%, 2% and 3% -- so the plots ARE the answer here
           and the number is a formality. Flagged rather than buried. */
        el('span', {
          class: 'ir-margin' + (hil.margin != null && hil.margin < 0.1
                                ? ' close' : ''),
          title: hil.margin != null && hil.margin < 0.1
            ? 'The winning channel barely beat the runner-up — worth looking '
              + 'at the plots rather than taking the pick'
            : 'How far the winning channel stood above the runner-up',
          text: hil.margin != null
            ? ('margin ' + Math.round(hil.margin * 100) + '%') : '' }),
        el('span', { class: 'ir-where',
          title: r.slurm_id ? ('slurm job ' + r.slurm_id) : '',
          text: r.ran_on === 'vacc' ? 'VACC' : '' }),
        el('span', { class: 'ir-banked',
          text: r.banked ? ('banked · ' + (r.banked.n || 0)) : 'not banked' }),
      ]));

      /* The plots for the row you opened, directly under that row.

         They used to be appended after the whole list, so on a queue of
         thirty the thing you had just clicked was thirty rows above what it
         had produced, and deciding a hilus meant scrolling between the
         picture and the name of the recording it belonged to.

         One at a time, deliberately: the three canvases have fixed ids, and
         -- more to the point -- a hilus is a judgement about one recording
         and looking at four sets of plots at once is not how anybody makes
         it. */
      if (on) {
        const drop = el('div', { class: 'inc-drop' });
        if (!res) {
          drop.appendChild(el('p', { class: 'hint quiet',
                                     text: 'Fetching the scan…' }));
        } else {
          drop.appendChild(channelCard());
          drop.appendChild(resultCard());
        }
        wrap.appendChild(drop);
      }
    }
    return wrap;
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
      vaccButton(),
      el('span', { class: 'hint quiet',
        text: est.cached ? 'Already scanned — this will be instant.'
          : 'Detects on every channel. That is not wasteful: the hilus '
            + 'estimate is computed from the per-channel counts, so there '
            + 'is no cheaper way to make it.' }),
    ]));
    const vs = vaccSentence();
    if (vs) box.appendChild(vs);
    box.appendChild(params());
    return box;
  }

  /* ---------------- running it somewhere else ----------------

     The second button is never a replacement for the first. Two machines,
     two caches, two answers that have to be compared rather than assumed --
     and a recording the cluster cannot reach still has a perfectly good
     local Scan beside it.

     Shown only while VACC Mode is on AND the server says there is a cluster
     configured. The mode gates the LOOK; `configured` gates the capability.
     That split matters: turning the glow off because your eyes hurt must
     not take away the Cancel button for a job still running on a shared
     machine, so nothing here is ever the only way to reach something. */
  function vaccOn() {
    return !!(BARRY.state.vacc && BARRY.vacc
              && (BARRY.vacc.last || {}).configured);
  }

  function vaccButton() {
    if (!vaccOn()) return null;
    const v = (est && est.vacc) || {};
    const busy = !!job;
    return el('button', {
      class: 'btn ghost',
      text: busy ? 'Scanning…' : 'Scan on VACC',
      // Disabled with the reason ON it rather than hidden. A control that
      // vanishes teaches nothing; `canOpen` in sessions.js carries the same
      // note about reading an absent answer as a "no".
      disabled: (busy || !v.can) ? 'disabled' : null,
      title: v.can ? ('Runs the same detector on ' + (v.remote || 'the cluster'))
                   : (v.reason || 'The cluster cannot reach this recording.'),
      onclick: () => scan(false, 'vacc'),
    });
  }

  function vaccSentence() {
    if (!vaccOn()) return null;
    const v = (est && est.vacc) || {};
    if (!v.can) {
      return el('div', { class: 'hint quiet vacc-why', text: v.reason || '' });
    }
    const here = Math.max(1, Math.round(((est.plan || {}).seconds) || 0));
    const there = Math.max(1, Math.round(v.seconds || 0));
    const q = v.queued ? (', ' + v.queued + ' ahead of you in the queue') : '';
    // Says plainly when the cluster figure is still the local seed rather
    // than something the cluster has actually done. An estimate borrowed
    // from a different computer is not a measurement of this one.
    const how = v.measured ? '' : ' (estimated from this machine until the '
                                + 'cluster has run one)';
    return el('div', { class: 'hint quiet vacc-why',
      text: 'About ' + here + ' s here · about ' + there + ' s on VACC'
            + q + how + '.' });
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
  /* How much of the bar each stage is worth. Reading dominates a local
     scan, which is why it is forty to one.

     The VACC stages are here because an unlisted stage gets weight 1 by
     default, and a queue that can sit for an hour beside a read worth forty
     gives a bar that holds at two percent and then leaps. `vacc queue` is
     weighted like the read it is standing in for; the transfers are small. */
  const WEIGHT = {
    'ds read': 40, 'ds detect': 1,
    'vacc stage': 4, 'vacc queue': 30, 'vacc fetch': 2,
  };

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

  /* ==================================================================
     Every channel, three ways
     ==================================================================
     Toothy's `ephys.py:1144 plot_channel_events` draws exactly these three
     beside its channel picker, and people have been reading them for years:
     how many dentate spikes each channel carried, how big they were, and
     how far each one stood above its own surround. They are here because
     the hilus pick is an argmax over the first and second of them, and an
     argmax is a number -- these are the picture it came out of, which is
     what tells you whether the pick is obvious or a coin toss.

     Same colours as Toothy, deliberately: seaborn's cubehelix at
     `dark=0.2, light=0.9, rot=0.4`, light for little and dark for a lot. A
     plot somebody already knows how to read should not change its palette
     on the way into a second tool.
     ================================================================== */

  /* Is the page dark? Read off the background token rather than off the
     theme's name: there are ten themes and the list grows, and what this
     needs to know is one thing about the pixels behind the plot.

     Read ONCE per draw, into `dark` below. `BARRY.token` is a
     `getComputedStyle` on the document element, and `cubehelix` is called
     per mark -- sixty-four channels of four hundred amplitudes is
     twenty-five thousand marks, and asking the style system the same
     question twenty-five thousand times to draw one small canvas is a
     forced layout per dot. */
  function readDark() {
    const bg = BARRY.token('--bg', '#ffffff').trim();
    let r = 255, g = 255, b = 255;
    let m = bg.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (m) {
      const hex = m[1].length === 3
        ? m[1].split('').map((c) => c + c).join('') : m[1];
      r = parseInt(hex.slice(0, 2), 16);
      g = parseInt(hex.slice(2, 4), 16);
      b = parseInt(hex.slice(4, 6), 16);
    } else if ((m = bg.match(/(\d+)[,\s]+(\d+)[,\s]+(\d+)/))) {
      r = +m[1]; g = +m[2]; b = +m[3];
    }
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 128;
  }

  /* Green's cubehelix, the matplotlib formula (`_cm.cubehelix`), at
     seaborn's `dark=0.2, light=0.9, rot=0.4` -- Toothy's palette, so that a
     plot somebody has been reading for two years looks like itself here.
     `t` is 0 for the smallest value and 1 for the largest.

     Which END the largest value gets depends on the page, and this is the
     one place the copy is deliberately not exact. Toothy draws on white,
     where seaborn's walk from light to dark puts the busiest channel at the
     darkest, most prominent point. On a dark theme that same walk makes the
     busiest channel the one you cannot see -- measured on screen: the tall
     bars came out near-black on a near-black ground. So the ramp is
     oriented to the background rather than to the source: "a lot" is always
     the end that stands out, which is the thing the colour is FOR. On the
     light themes it is Toothy's ramp exactly. */
  let dark = false;   // set by drawPlots, before anything is coloured
  function cubehelix(t) {
    const LIGHT = 0.9, DARK = 0.2, START = 0.0, ROT = 0.4, HUE = 0.8;
    const u = Math.max(0, Math.min(1, t || 0));
    const lo = dark ? DARK : LIGHT;
    const hi = dark ? LIGHT : DARK;
    const x = lo + (hi - lo) * u;
    const a = HUE * x * (1 - x) / 2;
    const phi = 2 * Math.PI * (START / 3 + ROT * x);
    const cos = Math.cos(phi), sin = Math.sin(phi);
    const ch = (p0, p1) => Math.round(255 * Math.max(0, Math.min(1,
      x + a * (p0 * cos + p1 * sin))));
    return 'rgb(' + ch(-0.14861, 1.78277) + ',' + ch(-0.29227, -0.90649)
         + ',' + ch(1.97294, 0.0) + ')';
  }
  /* A channel that was not read. Toothy greys its noise channels in place
     rather than dropping them, and so does this: a gap you can see is the
     point -- it is how "CSC41 is excluded" reads off the plot instead of
     off a sentence above it. */
  const GREY = 'rgba(150,150,150,0.55)';

  /* The x axis every plot shares: every channel on the probe, in order,
     whether or not it was read. `est.channels` is the whole list and
     `res.channels` only the scanned ones, so the axis comes from the first
     and the data from the second. */
  function plotAxis() {
    const all = (est && est.channels) || [];
    const by = {};
    for (const c of (res && res.channels) || []) by[Number(c.number)] = c;
    const axis = (all.length ? all : (res && res.channels) || [])
      .map((c) => Number(c.number)).sort((a, b) => a - b);
    return { axis, by };
  }

  /* Deterministic jitter, so a redraw does not reshuffle the dots.

     seaborn's stripplot jitters within the category so that events at the
     same amplitude are not one dot. Its jitter is random; this one is a
     hash of the channel and the index, which looks the same and stops the
     cloud crawling every time the panel repaints. */
  function jitter(ch, i) {
    const h = Math.sin(ch * 127.1 + i * 311.7) * 43758.5453;
    return (h - Math.floor(h)) - 0.5;
  }

  /* Size from the canvas's OWN laid-out width. `parentNode.clientWidth`
     includes the card's padding, which is how Panorama's canvases came out
     wider than the box they sit in. */
  function plotCanvas(id, h) {
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

  const PLOT_PAD = { l: 44, r: 8, t: 22, b: 26 };

  /* The frame the three share: the chosen channel's band behind
     everything, the axes, the channel ticks and the two titles. Returns the
     scales, because every caller then needs them. */
  function plotFrame(c, axis, title, ylab, ymax, ymin) {
    const { g, W, H } = c;
    const k = {
      text: BARRY.token('--text', '#222'),
      dim: BARRY.token('--text-3', '#888'),
      faint: BARRY.token('--border', '#ddd'),
    };
    const P = PLOT_PAD;
    const plotW = Math.max(10, W - P.l - P.r);
    const plotH = Math.max(10, H - P.t - P.b);
    const lo = ymin || 0;
    const hi = (ymax > lo) ? ymax : lo + 1;
    // Half a step of margin at each end, so the first and last channel are
    // not drawn on the axis line. Toothy's `xmargin=0.05`.
    const step = plotW / Math.max(1, axis.length);
    const sx = (num) => {
      const i = axis.indexOf(Number(num));
      return P.l + (i < 0 ? 0 : (i + 0.5) * step);
    };
    const sy = (v) => P.t + plotH - ((v - lo) / (hi - lo)) * plotH;

    // The chosen hilus channel, behind the data. Toothy marks it with an
    // `axvspan` for the same reason: the pick has to be findable in the
    // picture without counting ticks across to it.
    const hil = chosen.hilus;
    if (hil != null && axis.indexOf(Number(hil)) >= 0) {
      g.fillStyle = BARRY.token('--accent', '#FFB81C');
      g.globalAlpha = 0.22;
      g.fillRect(sx(hil) - step / 2, P.t, Math.max(2, step), plotH);
      g.globalAlpha = 1;
    }

    g.strokeStyle = k.faint;
    g.lineWidth = 1;
    g.beginPath();
    g.moveTo(P.l + 0.5, P.t);
    g.lineTo(P.l + 0.5, P.t + plotH + 0.5);
    g.lineTo(W - P.r, P.t + plotH + 0.5);
    g.stroke();

    g.font = '600 11px system-ui, sans-serif';
    g.fillStyle = k.text;
    g.textAlign = 'center';
    g.fillText(title, P.l + plotW / 2, 12);

    g.font = '9.5px system-ui, sans-serif';
    g.fillStyle = k.dim;
    // About ten of them, on round numbers, the way Toothy's MaxNLocator
    // does it -- not every channel, which is unreadable at sixty-four.
    const every = Math.max(1, Math.ceil(axis.length / 9));
    g.textAlign = 'center';
    for (let i = 0; i < axis.length; i += every) {
      g.fillText(String(axis[i]), sx(axis[i]), H - P.b + 12);
    }
    g.textAlign = 'right';
    // Three, not two. Top and bottom alone leave the reader interpolating
    // across a hundred and twenty pixels to place a bar, which is most of
    // what these are looked at for.
    g.fillText(fmtTick(hi), P.l - 4, P.t + 4);
    g.fillText(fmtTick((lo + hi) / 2), P.l - 4, P.t + plotH / 2 + 3);
    g.fillText(fmtTick(lo), P.l - 4, P.t + plotH + 3);
    g.save();
    g.translate(10, P.t + plotH / 2);
    g.rotate(-Math.PI / 2);
    g.textAlign = 'center';
    g.fillText(ylab, 0, 0);
    g.restore();
    return { sx, sy, step, plotW, plotH, P, lo, hi };
  }

  /* A count is a count. The first version ran every axis through the same
     decimal rule and labelled the event axis "73.0" and "0.00", which reads
     as a measurement with a precision it does not have -- there is no such
     thing as 73.0 dentate spikes. Whole numbers print whole. */
  const fmtTick = (v) => {
    if (!isFinite(v)) return '';
    if (Math.abs(v - Math.round(v)) < 1e-9) return String(Math.round(v));
    if (Math.abs(v) >= 100) return String(Math.round(v));
    if (Math.abs(v) >= 1) return (Math.round(v * 10) / 10).toFixed(1);
    return (Math.round(v * 100) / 100).toFixed(2);
  };

  /* 1. How many. Toothy's `ax0`: a bar per channel, coloured by its own
     height, which is half of what the hilus argmax multiplies. */
  function drawCount() {
    const c = plotCanvas('incPlotCount', 170);
    if (!c) return;
    const { axis, by } = plotAxis();
    const ns = axis.map((n) => Number((by[n] || {}).n || 0));
    const top = Math.max(1, Math.max.apply(null, ns));
    const f = plotFrame(c, axis, 'DS count', '# events', top);
    const g = c.g;
    for (let i = 0; i < axis.length; i += 1) {
      const row = by[axis[i]];
      const x = f.sx(axis[i]);
      const w = Math.max(1, f.step * 0.8);
      if (!row) { drawGap(g, x, f); continue; }
      g.fillStyle = cubehelix(ns[i] / top);
      const y = f.sy(ns[i]);
      g.fillRect(x - w / 2, y, w, f.P.t + f.plotH - y);
    }
  }

  /* A channel that was not read: a thin grey column the full height, so it
     is obviously absent rather than obviously zero. Those are different
     facts and a bar of height nothing says the wrong one. */
  function drawGap(g, x, f) {
    g.fillStyle = GREY;
    g.globalAlpha = 0.18;
    g.fillRect(x - 1, f.P.t, 2, f.plotH);
    g.globalAlpha = 1;
  }

  /* 2. How big. Toothy's `ax1`: a stripplot of EVERY event's amplitude,
     hued by the amplitude itself. What travels here is a sample of at most
     four hundred per channel, taken at an even stride -- see
     `AMP_SAMPLE_MAX` in incisor.py. The count above is exact; this is the
     shape of the distribution, which is all it is read for. */
  function drawAmp() {
    const c = plotCanvas('incPlotAmp', 170);
    if (!c) return;
    const { axis, by } = plotAxis();
    let top = 0, bot = Infinity;
    for (const n of axis) {
      for (const a of ((by[n] || {}).amp_sample || [])) {
        if (a > top) top = a;
        if (a < bot) bot = a;
      }
    }
    /* Scaled to the amplitudes, not to zero.

       A bar chart has to start at zero or its bars lie about their ratios.
       A cloud of amplitudes does not, and pinning this one to zero wasted
       the lower two thirds of the panel on the range below the detection
       threshold -- which is empty BY CONSTRUCTION, since nothing under the
       threshold is an event. Toothy's axis starts at its data too. */
    if (!isFinite(bot) || top <= 0) { bot = 0; top = 1; }
    const pad = (top - bot) * 0.06 || 1;
    const f = plotFrame(c, axis, 'DS amplitude', 'Amplitude µV',
                        top + pad, Math.max(0, bot - pad));
    const g = c.g;
    const rad = Math.max(0.7, Math.min(1.8, f.step * 0.14));
    for (const n of axis) {
      const row = by[n];
      if (!row) { drawGap(g, f.sx(n), f); continue; }
      const xs = f.sx(n);
      const amps = row.amp_sample || [];
      for (let i = 0; i < amps.length; i += 1) {
        g.fillStyle = cubehelix(amps[i] / top);
        g.beginPath();
        g.arc(xs + jitter(n, i) * f.step * 0.7, f.sy(amps[i]), rad, 0,
              Math.PI * 2);
        g.fill();
      }
    }
  }

  /* 3. How far above the surround. Toothy's `ax2`: the mean of
     `width_height` with its standard error, drawn as a bar through a ring.
     `width_height` is where `peak_widths(rel_height=0.5)` measured the
     width -- the trace level halfway down the peak's own prominence --
     and "prominence / 2" is Toothy's name for that axis, kept. */
  function drawProm() {
    const c = plotCanvas('incPlotProm', 170);
    if (!c) return;
    const { axis, by } = plotAxis();
    let top = 0, bot = Infinity;
    for (const n of axis) {
      const r = by[n];
      if (!r || r.width_height_mean == null) continue;
      top = Math.max(top, r.width_height_mean + (r.width_height_sem || 0));
      bot = Math.min(bot, r.width_height_mean - (r.width_height_sem || 0));
    }
    if (!isFinite(bot)) { bot = 0; top = 1; }
    const pad = (top - bot) * 0.12 || 1;
    const f = plotFrame(c, axis, 'DS height above surround',
                        'prominence / 2', top + pad, bot - pad);
    const g = c.g;
    const rad = Math.max(2.5, Math.min(5, f.step * 0.35));
    for (const n of axis) {
      const r = by[n];
      if (!r) { drawGap(g, f.sx(n), f); continue; }
      if (r.width_height_mean == null) continue;
      const t = (r.width_height_mean - f.lo) / (f.hi - f.lo);
      const col = cubehelix(t);
      const x = f.sx(n), y = f.sy(r.width_height_mean);
      const e = r.width_height_sem || 0;
      g.strokeStyle = col;
      g.lineWidth = Math.max(1.5, Math.min(3.5, f.step * 0.22));
      g.beginPath();
      g.moveTo(x, f.sy(r.width_height_mean - e));
      g.lineTo(x, f.sy(r.width_height_mean + e));
      g.stroke();
      // White first, then a wash of the same colour over it: Toothy draws
      // the ring twice for this, and the white is what keeps a ring legible
      // where the error bars of its neighbours run behind it.
      g.fillStyle = BARRY.token('--bg', '#fff');
      g.beginPath(); g.arc(x, y, rad, 0, Math.PI * 2); g.fill();
      g.globalAlpha = 0.2; g.fillStyle = col;
      g.beginPath(); g.arc(x, y, rad, 0, Math.PI * 2); g.fill();
      g.globalAlpha = 1;
      g.strokeStyle = col;
      g.lineWidth = 2;
      g.beginPath(); g.arc(x, y, rad, 0, Math.PI * 2); g.stroke();
    }
  }

  function drawPlots() {
    if (!res || !document.getElementById('incPlotCount')) return;
    // Once, here, for every mark in all three. See `readDark`.
    dark = readDark();
    try { drawCount(); drawAmp(); drawProm(); } catch (e) { /* non-fatal */ }
  }

  /* Which channel is under a pointer at `x` on any of the three. They
     share an axis, so one function serves all of them. */
  function channelAtX(cv, x) {
    const { axis } = plotAxis();
    if (!axis.length) return null;
    const w = cv.getBoundingClientRect().width;
    const step = Math.max(1, (w - PLOT_PAD.l - PLOT_PAD.r) / axis.length);
    const i = Math.floor((x - PLOT_PAD.l) / step);
    return axis[Math.max(0, Math.min(axis.length - 1, i))];
  }

  function plotBlock() {
    const box = el('div', {});
    box.appendChild(el('p', { class: 'hint quiet', style: 'max-width:78ch',
      text: 'The three Toothy draws beside its own channel picker, on this '
          + 'scan. The hilus pick is an argmax over normalised count × '
          + 'normalised amplitude, so the first two plots are the picture '
          + 'that argmax came out of. Click any of them to put the hilus on '
          + 'that channel. Grey columns were not read.' }));
    const wrap = el('div', { class: 'inc-plots' });
    for (const id of ['incPlotCount', 'incPlotAmp', 'incPlotProm']) {
      const cv = el('canvas', {
        id, class: 'inc-plot',
        title: 'Click to put the hilus on this channel',
        onclick: (e) => {
          const n = channelAtX(e.target,
                               e.clientX - e.target.getBoundingClientRect().left);
          if (n == null) return;
          chosen.hilus = Number(n);
          pushLines(); paint();
        },
        onmousemove: (e) => {
          const n = channelAtX(e.target,
                               e.clientX - e.target.getBoundingClientRect().left);
          const out = document.getElementById('incPlotRead');
          if (!out || n == null) return;
          const { by } = plotAxis();
          const r = by[Number(n)];
          out.textContent = r
            ? ('CSC' + n + ' — ' + r.n + ' candidate'
               + (r.n === 1 ? '' : 's') + ', mean '
               + (r.mean_amp || 0).toFixed(0) + ' µV, '
               + (r.width_height_mean == null ? 'no height'
                  : (r.width_height_mean.toFixed(2) + ' above surround')))
            : ('CSC' + n + ' — not read');
        },
        onmouseleave: () => {
          const out = document.getElementById('incPlotRead');
          if (out) out.textContent = '';
        },
      });
      wrap.appendChild(cv);
    }
    box.appendChild(wrap);
    box.appendChild(el('p', { class: 'hint quiet inc-plot-read',
                              id: 'incPlotRead', text: '' }));
    return box;
  }

  /* Redrawn on a resize, because the canvases are sized from their laid-out
     width and a narrower pane is a different picture, not the same one
     squashed. Attached once. */
  let plotsWired = false;
  function wirePlots() {
    if (plotsWired) return;
    plotsWired = true;
    let t = null;
    window.addEventListener('resize', () => {
      clearTimeout(t);
      t = setTimeout(drawPlots, 160);
    });
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
    box.appendChild(plotBlock());
    const known = (est && est.known) || {};

    const most = (res.alternates || {}).most_spikes;

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
            /* The other answer to the same question, offered as a button.
               Toothy's estimate -- and so this one -- is an argmax over a
               PRODUCT of normalised amplitude and normalised count, which
               is usually the right trade and sometimes is not: a hilus site
               next to a quiet one can come second on amplitude while
               carrying nearly every spike in the recording. Pressing this
               is somebody saying they mean the count. */
            (r.key === 'hilus' && most) ? el('button', {
              class: 'btn ghost sm'
                     + (Number(now) === Number(most.number) ? ' on' : ''),
              text: 'Most spikes: ' + most.label,
              title: most.label + ' carried the most dentate spikes of any '
                   + 'channel scanned (' + (most.value || 0) + ', ahead of '
                   + 'the next by ' + (100 * (most.margin || 0)).toFixed(0)
                   + '%). That is not the same claim as “this is the '
                   + 'hilus”: the scan’s own pick weighs amplitude as well '
                   + 'as count.',
              onclick: () => {
                chosen.hilus = Number(most.number); pushLines(); paint();
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
          (r.key === 'hilus' && most && pick
           && Number(most.number) !== Number(pick.number))
            ? el('p', { class: 'hint quiet',
                text: 'The most dentate spikes are on ' + most.label
                    + ' (' + (most.value || 0) + '), not on ' + pick.label
                    + '. The scan weighs how big they are as well as how '
                    + 'many, so the two part company when a channel carries '
                    + 'a lot of small events. The plots above are that '
                    + 'disagreement drawn out.' })
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
       the scan filled, so this costs a small request and no reading.

       The busy state used to start three lines below this, after the profile
       lookup and this request had both completed -- so pressing Bank showed
       nothing at all and then a confirmation dialog appeared out of nowhere,
       which is the whole complaint in one button. */
    let evs;
    banking = true; paint();
    try {
      const got = await apiPost('/api/incisor/events',
                                body({ channel: row.index }));
      evs = got.events || [];
    } catch (e) {
      toast('Those candidates are no longer cached — run the scan again. ('
            + e.message + ')', 'err', 9000);
      return;
    } finally {
      // Down again for the dialog: the question is the person's to answer in
      // their own time, and a button that says "Banking…" behind it is a lie.
      banking = false; paint();
    }
    if (!evs.length) { toast('No candidates on that channel.', 'warn'); return; }

    /* What this set will be called, chosen here rather than assembled
       silently. It used to go in as "Incisor CSC61", which is plenty while
       you are looking at the recording and says nothing at all in a list of
       forty-five — so the name is offered, with the session already in it,
       at the one moment somebody knows what this set is for. */
    const nameBox = el('input', {
      type: 'text', class: 'inc-name',
      value: BARRY.bankName.suggest(q.row || {}, 'Incisor ' + row.label),
    });
    const ok = await BARRY.confirm(
      'Bank ' + evs.length + ' candidate(s) from ' + row.label + '?',
      el('div', { class: 'fix-facts' }, [
        el('div', { class: 'field' }, [
          el('label', { text: 'Call this set' }),
          nameBox,
          el('span', { class: 'hint', text:
            'The session is in it already. Anything you type here is what '
            + 'the Event Bank lists it under, and it can be changed later.' }),
        ]),
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
        // What the dialog was left showing. Blank falls back to the
        // suggestion rather than to nothing: an entry with no name at all
        // is the one thing worse than a vague one.
        name: (nameBox.value || '').trim()
              || BARRY.bankName.suggest(q.row || {}, 'Incisor ' + row.label),
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
    /* The plots' own axis arithmetic, so a harness can ask "which channel
       is under this pixel" with the same function the click handler uses
       rather than a second copy of it to drift from the first. */
    _plotAxis: plotAxis,
    _channelAtX: channelAtX,
    _drawPlots: drawPlots,
    _choose: (key, number) => {
      chosen[key] = number == null ? null : Number(number);
      pushLines(); paint();
    },
  };
}());
