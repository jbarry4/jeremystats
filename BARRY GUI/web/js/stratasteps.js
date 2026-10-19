/* ==========================================================================
   stratasteps.js -- StrataScope's steps: from painting labels to a method.

   strata.js is the rail: pick channels, name a layer. That stays, for the
   odd channel. This is the part that says where the lines should go and
   why:

     0  Theta Walk          paint when the animal was walking, by hand, over
                            a guide strip of theta/delta, probe agreement,
                            the finder's ghost bouts and a 4-12 Hz
                            spectrogram
     1  Crystallize CA1     so / sp / sr / slm and the fissure
     2  Find the hilus      the two granule layers, the hilus between
     3  GCL IML MML OML     the molecular layer in thirds (Method A), checked
                            by pathway-specific gamma (Method B, ICA)
     4  Sign off            checks, then a version that keeps how it was
                            decided

   Every proposal is ghost lines -- dashed, on the depth strip beside the
   rail, on the traces and in the evidence window -- that you drag and then
   Accept. Each line's anchor says which measurement placed it (the lead)
   and what the others say (votes, with how many channels they disagree
   by); clicking a vote makes it the lead.

   NO DENTATE SPIKES anywhere in here, on purpose: these labels are what the
   DS results get checked against (see backend/stratasteps.py).

   The numbers are backend/stratasteps.py, through /api/strata/<gid>/*. The
   decisions are the layer sheet's strata_* fields (backend/layers.py).
   ========================================================================== */
'use strict';

BARRY.strataSteps = (function () {
  const STEPS = [
    { id: '0', name: 'Theta Walk', title: 'Step 0 · Theta Walk',
      blurb: 'Paint when the animal was walking. Theta curves, gamma and ICA '
           + 'use these seconds; ripples use the rest, less a buffer.' },
    { id: '1', name: 'CA1', title: 'Step 1 · Crystallize CA1',
      blurb: 'The pyramidal layer from ripples, the fissure from theta, and '
           + 'the CA1 layers between them.' },
    { id: '2', name: 'Hilus', title: 'Step 2 · Find the hilus',
      blurb: 'The two granule layers from multiunit activity, and the hilus '
           + 'between them. No dentate spikes: these labels are what DS '
           + 'results get checked against.' },
    { id: '3', name: 'GCL · IML · MML · OML', title: 'Step 3 · Define GCL, '
           + 'IML, MML, OML',
      blurb: 'The molecular layer cut in thirds between the fissure and the '
           + 'granule layer (Method A), checked by where slow and fast gamma '
           + 'generators sit (Method B, ICA).' },
    { id: '4', name: 'Sign off', title: 'Step 4 · Sign off',
      blurb: 'The checks, then a version of the sheet that keeps the '
           + 'parameters, the confidence of every line and who signed it.' },
  ];

  /* The depth curves. Colours are theme tokens, read when drawn, so the
     strip follows the theme like everything else. */
  const CURVES = [
    { id: 'mua', name: 'MUA', tok: '--c1',
      why: 'Multiunit power, 300-6000 Hz, all the time. Peaks where cells '
         + 'are packed: the pyramidal and granule layers.' },
    { id: 'ripple', name: 'Ripple', tok: '--event',
      why: 'Ripple-band power, 120-180 Hz, still time. Largest at the '
         + 'pyramidal layer, where ripples are made.' },
    { id: 'theta', name: 'Theta', tok: '--c3',
      why: 'Theta power, 6-10 Hz, Theta Walk. Largest near the fissure, and '
         + 'often again in the dentate.' },
    { id: 'theta_phase', name: 'Phase', tok: '--c4',
      why: 'How early or late each channel’s theta is, against the '
         + 'reference channel (the stopwatch). Shifts by about half a cycle '
         + 'from sp to the fissure.' },
    { id: 'theta_coherence', name: 'Coherence', tok: '--c5',
      why: 'How closely each channel’s theta follows the reference '
         + 'channel. Drops where a layer boundary is crossed.' },
    { id: 'slow_gamma', name: 'Slow γ', tok: '--c2',
      why: 'Slow gamma, 25-45 Hz, Theta Walk. A stratum radiatum marker.' },
    { id: 'mid_gamma', name: 'Mid γ', tok: '--warn',
      why: 'Mid gamma, 60-100 Hz, Theta Walk. Marks slm and the dentate '
         + 'molecular layer.' },
  ];
  const CONF = ['sure', 'likely', 'guess'];
  const CONF_WHY = {
    sure: 'You checked this line against the evidence and would defend it.',
    likely: 'The evidence mostly agrees; you have not checked it closely.',
    guess: 'Placed by geometry or a weak signal. Treat labels next to it '
         + 'as uncertain.',
  };
  /* How a line is drawn says how sure it is, everywhere it is drawn. */
  const CONF_DASH = { sure: [], likely: [7, 4], guess: [2, 4] };

  /* What each step is about. Everything else is greyed out while it is
     open (2026-10-12: "way too many lines and colours at one time"):

       regions  the layers the step writes; boundaries of any other layer
                go grey, and channels outside what Accept would write are
                dimmed on the rail, the strip, the traces and the aid
                window
       lead     the curves the step's lines are placed by, drawn full
       votes    the curves that vote, drawn faint
     Every other curve is off until somebody turns it on. */
  const FOCUS = {
    0: { regions: [], lead: ['theta'], votes: [] },
    1: { regions: ['ca1_so', 'ca1_sp', 'ca1_rad', 'ca1_slm', 'ca1_sr'],
         lead: ['ripple', 'theta'], votes: ['mua', 'theta_phase'] },
    2: { regions: ['dg_gcl1', 'hil', 'dg_gcl2', 'dg', 'dg2'],
         lead: ['mua'], votes: ['theta'] },
    3: { regions: ['dg_oml1', 'dg_mml1', 'dg_iml1', 'dg_gcl1', 'hil',
                   'dg_gcl2', 'dg_iml2', 'dg_mml2', 'dg_oml2', 'dg', 'dg2',
                   'thal'],
         lead: ['mua', 'theta'], votes: [] },
    // Sign off: everything, every layer in colour and every curve.
    4: { regions: null, lead: ['mua', 'ripple', 'theta', 'theta_phase',
                               'theta_coherence', 'slow_gamma', 'mid_gamma'],
         votes: [] },
  };
  const STRIP_W = 150;

  let H = null;            // the host: hooks strata.js hands over on enter
  let status = null;       // whether this recording has been read
  let estimate = null;     // seconds a read would take here
  let readPlan = null;     // what a read would do: channels, bad ones skipped
  let jobId = null;        // a read or an ICA running
  let jobKind = null;
  let jobSnap = null;
  let jobsNow = [];        // every read and ICA running, any recording
  let open = null;         // which step is open, '0'..'4', or null
  let sug = null;          // the last /suggest answer
  let guide = null;        // the last /guide answer (Step 0)
  let ghost = null;        // {step, lines: [...]} -- the editable proposal
  let overrides = {};      // anchors moved by clicking a vote
  let shown = new Set(['mua', 'theta']);
  let checks = null;
  let ica = null;
  let busy = '';
  let more = false;        // the step's ▸ More
  let loadSeq = 0;
  let wheelDraft = { on: '', off: '', note: '' };
  let stripCanvas = null;
  let strip = { top: 0, height: 0, lane: 0, n: 0 };
  let drag = null;         // a line being dragged on the depth strip
  let paint = null;        // a bout being painted on the Step 0 strip
  let saveTimer = null;
  let rev = 0;

  /* ==================================================================
     In and out
     ================================================================== */
  let enteredAt = 0;
  let cmdSeen = 0;

  async function enter(host) {
    H = host;
    enteredAt = Date.now();
    status = null; sug = null; guide = null; ghost = null; overrides = {};
    checks = null; ica = null; open = null; busy = '';
    jobId = null; jobKind = null; jobSnap = null; jobsNow = [];
    await refreshStatus();
    attachJob();
    if (status && status.scanned && status.current && jobKind !== 'scan') {
      await load();
    }
    H.render();
    watchElsewhere();
  }

  /* A read or ICA of this recording still running -- started before
     somebody left it -- is picked up again rather than offered twice.
     (Leaving used to keep the old run's kind and lose its id, so the next
     recording showed a Stop with nothing behind it: "No such run".) */
  function attachJob() {
    if (!H || jobId) return;
    const mine = jobsNow.find((j) => j.gid === H.gid);
    if (!mine) return;
    jobId = mine.id; jobKind = mine.kind; jobSnap = null;
    poll();
  }

  const elsewhere = () => (H ? jobsNow.filter((j) => j.gid !== H.gid) : []);

  /* Runs on other recordings: kept up to date while any is going, so the
     bar can say so and stop them. */
  let watching = false;
  async function watchElsewhere() {
    if (watching) return;
    watching = true;
    try {
      while (H && elsewhere().length) {
        await new Promise((r) => setTimeout(r, 2000));
        if (!H) break;
        let changed = false;
        for (const j of elsewhere()) {
          let snap = null;
          try { snap = (await api('/api/cfc/job/' + j.id)).job; } catch (e) { /* gone */ }
          const st = snap && (snap.stages || [])[0];
          if (!snap || snap.status !== 'running') {
            jobsNow = jobsNow.filter((x) => x.id !== j.id);
            changed = true;
          } else if (st && st.done !== j.done) {
            j.done = st.done; j.of = st.of;
            changed = true;
          }
        }
        if (changed && H) H.render();
      }
    } finally { watching = false; }
  }

  /* Stop a run, this recording's or another's. A run that has already
     ended is not an error: there is nothing left to stop. */
  async function stopJob(id) {
    if (!id) return;
    try {
      await apiPost('/api/cfc/job/' + id + '/cancel', {});
    } catch (e) {
      if (id === jobId) { jobId = null; jobKind = null; jobSnap = null; }
    }
    jobsNow = jobsNow.filter((x) => x.id !== id);
    if (H && id !== jobId) { await refreshStatus(); H.render(); }
  }

  function leave() {
    if (saveTimer) { clearTimeout(saveTimer); flushStates(); }
    publish({ off: true });
    const body = document.getElementById('xfBody');
    if (body) {
      const d = body.querySelector('.ss-drawer');
      if (d) d.remove();
      body.classList.remove('ss-drawer-on');
    }
    H = null; status = null; sug = null; guide = null; ghost = null;
    stripCanvas = null; open = null;
    // The run goes on on the server; whoever comes back picks it up.
    jobId = null; jobKind = null; jobSnap = null; jobsNow = [];
  }

  const sheet = () => (H && H.sheet()) || null;
  const strata = () => ((sheet() || {}).strata) || {};
  const allChans = () => (H.allChannels ? H.allChannels() : H.channels());
  const body = (extra) => Object.assign({
    path: H.path(), channels: allChans().map((c) => c.number),
  }, extra || {});
  const url = (what) => '/api/strata/' + encodeURIComponent(H.gid) + '/' + what;

  async function refreshStatus() {
    try {
      const res = await apiPost(url('status'), body());
      status = res.status;
      estimate = res.estimate_s;
      readPlan = res.plan || null;
      status.probe = res.probe;
      jobsNow = res.jobs || [];
    } catch (e) {
      status = { scanned: false, error: e.message };
    }
  }

  /* Everything the steps show, in one request. */
  async function load(keepGhost) {
    if (!H) return;
    confirming = null;            // it listed changes for the old lines
    const mine = ++loadSeq;
    busy = 'Working out the depth curves and proposals…';
    H.render();
    try {
      const res = await apiPost(url('suggest'), body({ overrides }));
      if (mine !== loadSeq || !H) return;
      sug = res;
      if (!keepGhost || !ghost || ghost.step !== open) resetGhost();
      busy = '';
    } catch (e) {
      if (mine !== loadSeq) return;
      busy = '';
      toast('StrataScope could not work out the steps: ' + e.message,
            'err', 9000);
    }
    if (!H) return;
    H.render();
    drawStrip();
    H.redraw();
    publish();
  }

  function resetGhost() {
    if (!sug || !open || !sug.steps || !sug.steps[open]) { ghost = null; return; }
    const lines = (sug.steps[open].lines || []).map((ln) => Object.assign({}, ln));
    /* A line somebody already rated keeps its rating. */
    const conf = strata().confidence || {};
    for (const ln of lines) if (conf[ln.id]) ln.confidence = conf[ln.id];
    ghost = { step: open, lines };
  }

  /* ==================================================================
     Reading the recording
     ================================================================== */
  async function scan(force) {
    if (!H || jobId) return;
    try {
      const res = await apiPost(url('scan'), body({ force: !!force }));
      if (res.cached) {
        status = res.status;
        await load();
        return;
      }
      jobId = res.job.id; jobKind = 'scan'; jobSnap = res.job;
      estimate = res.estimate_s || estimate;
      H.render();
      poll();
    } catch (e) {
      toast('Could not start the read: ' + e.message, 'err', 9000);
    }
  }

  async function poll() {
    while (jobId && H) {
      await new Promise((r) => setTimeout(r, 1200));
      if (!jobId || !H) return;
      let snap;
      try {
        snap = (await api('/api/cfc/job/' + jobId)).job;
      } catch (e) { continue; }
      jobSnap = snap;
      if (snap.status === 'running') { renderJob(); continue; }
      const kind = jobKind;
      jobId = null; jobKind = null;
      if (snap.status !== 'done') {
        toast((kind === 'ica' ? 'ICA' : 'The read') + ' stopped: '
              + (snap.error || snap.status), 'err', 9000);
        H.render();
        return;
      }
      if (kind === 'scan') {
        await refreshStatus();
        await load();
        if (open === '0') await loadGuide();
      } else if (kind === 'ica') {
        await peekIca();
        await load(true);
      }
      return;
    }
  }

  function jobPct() {
    const st = (jobSnap && jobSnap.stages) || [];
    const s = st.find((x) => x.status === 'running') || st[0];
    if (!s || !s.of) return 0;
    return Math.round(100 * (s.done || 0) / s.of);
  }

  function renderJob() {
    const bar = document.querySelector('.ss-job i');
    const txt = document.querySelector('.ss-job span');
    if (bar) bar.style.width = jobPct() + '%';
    if (txt) txt.textContent = jobText();
  }

  function jobText() {
    const all = (jobSnap && jobSnap.stages) || [];
    if (jobKind === 'ica') return 'Unmixing the gamma field \u2014 '
      + jobPct() + '%';
    const skip = (readPlan && readPlan.skipped) || [];
    const skipTxt = skip.length ? ' (' + skip.length + ' bad skipped)' : '';
    /* A read on the VACC goes through stages of its own (2026-10-14):
       said in the words of where it is, not as a channel count that sits
       at 0 while the job waits in the queue. */
    const run = all.find((x) => x.status === 'running');
    const st = all.find((x) => x.name === 'strata read') || all[0] || {};
    if (run && /^vacc stage/.test(run.name)) return 'Sending the job to the VACC';
    if (run && /^vacc queue/.test(run.name)) {
      return 'On the VACC: waiting for a node, then reading there';
    }
    if (run && run.name === 'strata fetch') {
      return 'Bringing the read home from the VACC \u2014 ' + (run.done || 0)
        + ' of ' + (run.of || '?') + ' MB';
    }
    if (run && /^vacc fetch/.test(run.name)) return 'The VACC is done; collecting it';
    return (onVacc() ? 'Reading on the VACC \u2014 ' : 'Reading the channels \u2014 ')
      + (st.done || 0) + ' of ' + (st.of || '?') + ' done' + skipTxt;
  }
  /* A recording only the cluster has: read there, used here. */
  const onVacc = () => !!(H && /^vacc:/.test(H.path() || ''));

  /* ==================================================================
     The bar: the step row, then whatever the open step needs
     ================================================================== */
  /* Is stamp a after stamp b? As times, not strings: the stamps come from
     the server (UTC, microseconds) and from this page (toISOString), and
     older sheets carry local "-0400" ones. */
  function later(a, b) {
    const ta = Date.parse(a), tb = Date.parse(String(b).replace(
      /([+-]\d\d)(\d\d)$/, '$1:$2'));
    const ua = isFinite(ta) ? ta : Date.parse(String(a).replace(
      /([+-]\d\d)(\d\d)$/, '$1:$2'));
    if (isFinite(ua) && isFinite(tb) && ua !== tb) return ua > tb;
    return String(a) > String(b);
  }

  function stepState(id) {
    const steps = strata().steps || {};
    const me = steps[id];
    if (!me || me.status !== 'done') return 'todo';
    // Something before it changed since it was accepted.
    for (const s of STEPS) {
      if (s.id >= id) break;
      const other = steps[s.id];
      if (other && other.at && me.at && later(other.at, me.at)) {
        return 'stale';
      }
    }
    return 'done';
  }

  function section() {
    const box = el('div', { class: 'ss', id: 'strataSteps' });
    if (!H) return box;
    /* One row, and only one, until Step 0 is open: the bar's height is the
       traces' height, and the rail's lanes are cut from the traces
       (web/_dev/stratacheck.html holds this). Whether the recording has
       been read, and the read's progress, sit in the same row. */
    box.appendChild(stepRow());
    if (status && status.scanned && status.current && jobKind !== 'scan'
        && open === '0') {
      box.appendChild(stepZero());
    }
    return box;
  }

  /* Steps 1-4 live in a drawer down the right of the traces, not in the
     bar under them. In the bar they took the height the traces need -- in a
     1000 px window the pane came down to a few pixels, the rail's lanes with
     it, and a dashed line could not be dragged because a channel was
     0.03 px tall. The drawer takes width instead, which the traces can
     spare; the lanes keep their height. */
  const DRAWER_W = 420;

  function drawer() {
    const body = document.getElementById('xfBody');
    if (!body) return;
    let d = body.querySelector('.ss-drawer');
    const want = !!(H && status && status.scanned && status.current
                    && open && open !== '0' && jobKind !== 'scan');
    if (!want) {
      if (d) d.remove();
      body.classList.remove('ss-drawer-on');
      return;
    }
    if (!d) {
      d = el('aside', { class: 'ss-drawer' });
      body.appendChild(d);
    }
    const keep = d.scrollTop;
    d.innerHTML = '';
    d.appendChild(open === '4' ? stepFour() : stepAnchors(open));
    d.scrollTop = keep;
    body.classList.add('ss-drawer-on');
    document.documentElement.style.setProperty('--ss-drawer-w',
                                               DRAWER_W + 'px');
  }

  function stepRow() {
    const row = el('div', { class: 'ss-row' });
    for (const s of STEPS) {
      const st = stepState(s.id);
      row.appendChild(el('button', {
        class: 'ss-step ' + st + (open === s.id ? ' on' : ''),
        title: s.blurb + (st === 'done' ? '\nDone.' : st === 'stale'
          ? '\nNeeds a look: an earlier step changed after this one was '
            + 'accepted.' : ''),
        disabled: (status && status.scanned && status.current) ? null
          : 'disabled',
        onclick: () => openStep(open === s.id ? null : s.id),
      }, [
        el('span', { class: 'ss-tick', text: st === 'done' ? '✓'
          : st === 'stale' ? '!' : s.id }),
        el('span', { text: s.name }),
      ]));
    }
    for (const j of elsewhere()) {
      const pct = j.of ? Math.round(100 * j.done / j.of) : 0;
      row.appendChild(el('span', { class: 'ss-else' }, [
        el('span', { text: (j.kind === 'ica' ? 'ICA on ' : 'Still reading ')
          + j.label + (j.kind === 'scan' ? ' · ' + pct + '%' : '') }),
        el('button', {
          class: 'mini', text: 'Stop',
          title: 'Stop that run. What it has read so far is thrown away.',
          onclick: () => stopJob(j.id),
        }),
      ]));
    }
    if (status && status.error) {
      row.appendChild(el('span', { class: 'ss-say err', text: status.error }));
    } else if (!status || !status.scanned || !status.current
               || jobKind === 'scan') {
      row.appendChild(readCard());
    } else if (busy) {
      row.appendChild(el('span', { class: 'ss-say', text: busy }));
    }
    if (status && status.scanned && status.current) {
      row.appendChild(el('button', {
        class: 'mini', text: 'Evidence window',
        title: 'The step’s evidence -- triggered averages, the phase '
             + 'and coherence, ICA -- in a second window that follows this '
             + 'one.',
        onclick: openAids,
      }));
    }
    return row;
  }

  function readCard() {
    const wrap = el('span', { class: 'ss-read' });
    if (jobKind === 'scan') {
      wrap.appendChild(el('div', { class: 'ss-job' }, [
        el('i', { style: 'width:' + jobPct() + '%' }),
        el('span', { text: jobText() }),
      ]));
      wrap.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Stop',
        onclick: () => stopJob(jobId),
      }));
      return wrap;
    }
    const mins = estimate ? Math.max(1, Math.round(estimate / 60)) : null;
    const stale = status && status.scanned && !status.current;
    /* Bad channels are not read (2026-10-13): they keep their place on the
       probe and are filled in from their neighbours wherever a picture
       needs them. */
    const skip = (readPlan && readPlan.skipped) || [];
    const skipTxt = skip.length ? skip.length + ' bad channel'
      + (skip.length === 1 ? '' : 's') + ' skipped' : '';
    wrap.appendChild(el('button', {
      class: 'btn sm', text: (stale ? 'Read it again' : 'Read the recording')
        + (onVacc() ? ' on the VACC' : '')
        + (mins ? ' \u00b7 about ' + mins + ' min' : '')
        + (skipTxt ? ' \u00b7 ' + skipTxt : ''),
      title: (stale ? (status.why || 'The files changed since this '
                       + 'recording was last read.') + '\n' : '')
           + 'The steps need every channel read once: ripples, theta, gamma '
           + 'and multiunit power, second by second. After that every '
           + 'answer comes back at once.'
           + (skip.length ? '\nNot read, because they are marked bad: ch '
             + skip.join(', ') + '. They keep their place on the probe and '
             + 'are filled in from their neighbours.' : '')
           + (onVacc() ? '\nThis recording is only on the VACC: a compute '
             + 'node reads it, and the read (the per-second numbers and a '
             + '1250 Hz copy, a few hundred MB) comes back here. Everything '
             + 'after that runs on this computer. Plus however long the '
             + 'queue is.' : ''),
      onclick: () => scan(true),
    }));
    if (stale && status.why) {
      wrap.appendChild(el('span', { class: 'ss-say warn', text: status.why }));
    }
    return wrap;
  }

  async function openStep(id) {
    open = id;
    confirming = null;
    icaPick = null;
    more = false;
    // Only what this step is decided from; the rest are a click away.
    const f = FOCUS[id];
    shown = new Set(f ? f.lead.concat(f.votes) : ['mua', 'theta']);
    resetGhost();
    if (id === '0' && !guide) await loadGuide();
    if (id === '4') await loadChecks();
    if (id === '3' && !ica) peekIca();
    H.render();
    drawStrip();
    H.redraw();
    publish();
  }

  /* ---------- Step 0: Theta Walk ---------- */
  async function loadGuide() {
    try {
      const res = await apiPost(url('guide'), body());
      guide = res;
    } catch (e) {
      toast('Could not draw the Theta Walk guide: ' + e.message, 'err', 8000);
    }
    if (H) H.render();
  }

  const walk = () => ((strata().states || {}).theta_walk || []);

  function fmtT(t) {
    const m = Math.floor(t / 60), s = Math.round(t - 60 * m);
    return m + ':' + String(s).padStart(2, '0');
  }

  function parseT(txt) {
    const v = String(txt || '').trim();
    if (!v) return null;
    const p = v.split(':').map(Number);
    if (p.some((x) => !isFinite(x))) return null;
    return p.length === 2 ? p[0] * 60 + p[1] : p[0];
  }

  function stepZero() {
    const box = el('div', { class: 'ss-zero' });
    const m = (sug && sug.masks) || (guide && guide.masks) || {};
    const secs = walk().reduce((a, b) => a + (b[1] - b[0]), 0);
    /* One line for what it is, what is painted and what to do next, so the
       strip -- the thing being worked on -- gets the height. */
    box.appendChild(el('div', { class: 'ss-zero-head' }, [
      el('strong', { text: STEPS[0].title }),
      el('span', { class: 'ss-say' + (walk().length ? '' : ' warn'),
                   text: walk().length
        ? walk().length + ' bout' + (walk().length === 1 ? '' : 's') + ', '
          + fmtT(secs) + ' of Theta Walk · ' + fmtT(m.still_s || 0)
          + ' still'
        : 'Nothing painted yet: theta will average the whole recording, '
          + 'dentate spikes and sharp waves included.' }),
      el('div', { style: 'flex:1' }),
      el('button', {
        class: 'btn ghost sm', text: 'Clear',
        title: 'Clear every painted Theta Walk bout',
        disabled: walk().length ? null : 'disabled',
        onclick: () => setWalk([]),
      }),
      el('button', {
        class: 'btn sm', text: 'Done — on to CA1',
        onclick: async () => {
          await flushStates();
          await accept('0', {});
          openStep('1');
        },
      }),
    ]));
    box.appendChild(finderRow());
    const g0 = guide && guide.guide;
    const cv = el('canvas', {
      class: 'ss-tw', height: '128',
      title: 'Drag to paint Theta Walk; drag a painted bout’s edge to move '
           + 'it; shift-drag to erase; a click moves the traces there.\n'
           + 'Top: spectrogram, 4-12 Hz' + (g0 ? ', ch ' + g0.channel : '')
           + '. Middle: theta (6-10 Hz) over delta (1-4 Hz) power on that '
           + 'channel, a three-second median; the dashed line is the '
           + 'finder’s level; hatched is where the finder would put '
           + 'bouts. Bottom: how much of the probe agrees on one theta '
           + 'frequency.',
    });
    box.appendChild(el('div', { class: 'ss-tw-wrap' }, [cv]));
    box.appendChild(wheelBox());
    /* Drawn once it is on the page, because it is sized from the page. A
       timer as well as a frame: whichever comes first (drawWalk is
       idempotent), and a frame alone never comes in a hidden tab. */
    setTimeout(() => drawWalk(cv), 0);
    requestAnimationFrame(() => drawWalk(cv));
    return box;
  }

  function wheelBox() {
    const list = strata().wheel || [];
    const box = el('div', { class: 'ss-wheel' }, [
      el('span', { class: 'ss-say', text: 'Drag to paint · drag an edge '
        + 'to move it · shift-drag erases · click moves the traces' }),
      el('div', { style: 'flex:1' }),
      el('span', { class: 'section-label', text: 'Wheel times' }),
    ]);
    list.forEach((w, i) => box.appendChild(el('span', { class: 'ss-chip' }, [
      el('span', { text: fmtT(w.t0) + '–' + fmtT(w.t1)
                         + (w.note ? ' · ' + w.note : '') }),
      el('button', {
        class: 'mini', text: 'Paint', title: 'Paint this as Theta Walk',
        onclick: () => setWalk(merge(walk().concat([[w.t0, w.t1]]))),
      }),
      el('button', {
        class: 'mini', text: '×', title: 'Remove this wheel time',
        onclick: () => saveStrata({ wheel: list.filter((x, k) => k !== i) }),
      }),
    ])));
    const on = el('input', { class: 'ss-in', placeholder: 'on m:ss',
                             value: wheelDraft.on,
                             oninput: (e) => { wheelDraft.on = e.target.value; } });
    const off = el('input', { class: 'ss-in', placeholder: 'off m:ss',
                              value: wheelDraft.off,
                              oninput: (e) => { wheelDraft.off = e.target.value; } });
    const note = el('input', { class: 'ss-in wide', placeholder: 'note',
                               value: wheelDraft.note,
                               oninput: (e) => { wheelDraft.note = e.target.value; } });
    box.appendChild(on); box.appendChild(off); box.appendChild(note);
    box.appendChild(el('button', {
      class: 'mini', text: 'Add',
      onclick: () => {
        const a = parseT(wheelDraft.on), b = parseT(wheelDraft.off);
        if (a == null || b == null || b <= a) {
          toast('Type the wheel time as minutes:seconds, on before off.',
                'err', 6000);
          return;
        }
        wheelDraft = { on: '', off: '', note: '' };
        saveStrata({ wheel: list.concat([{ t0: a, t1: b,
                                           note: note.value || null }]) });
      },
    }));
    return box;
  }

  /* The auto painter: what the finder calls a bout. Kept with the sheet's
     parameters; changing one redraws the ghost, and nothing is painted
     until "Paint them". */
  const FINDER = [
    { k: 'min_bout_s', name: 'Shortest bout', unit: 's', def: '2',
      why: 'A run of theta shorter than this is not a bout.' },
    { k: 'merge_gap_s', name: 'Join gaps under', unit: 's', def: '1',
      why: 'Two bouts closer than this become one.' },
    { k: 'ratio_threshold', name: 'θ/δ above', unit: '', def: null,
      why: 'The level the theta/delta curve has to clear: the dashed line. '
        + 'Empty: the finder picks it from this recording (Otsu).' },
    { k: 'theta_channel', name: 'Read on ch', unit: '', def: null,
      why: 'The channel the theta/delta curve and the spectrogram are read '
        + 'on. Empty: the good channel with the most theta.' },
  ];

  function finderRow() {
    const g = guide && guide.guide;
    const p = strata().params || {};
    const row = el('div', { class: 'ss-finder' }, [
      el('span', { class: 'section-label', text: 'Auto painter' })]);
    for (const f of FINDER) {
      const auto = f.def != null ? f.def
        : g ? 'auto: ' + (f.k === 'theta_channel' ? g.channel : g.threshold)
          : 'auto';
      row.appendChild(el('label', { class: 'ss-fin', title: f.why }, [
        el('span', { text: f.name }),
        el('input', {
          class: 'ss-in num', 'data-k': f.k, inputmode: 'decimal',
          // Wide enough for its own placeholder: never cut text short.
          style: 'width:' + (Math.max(4, String(auto).length) + 4) + 'ch',
          value: p[f.k] == null ? '' : String(p[f.k]), placeholder: auto,
          onchange: (e) => setFinder(f.k, e.target.value),
        }),
        f.unit ? el('span', { class: 'ss-unit', text: f.unit }) : null,
      ]));
    }
    const gb = (g && g.ghost) || [];
    const secs = gb.reduce((a, b) => a + (b[1] - b[0]), 0);
    row.appendChild(el('span', { class: 'ss-say', text: gb.length + ' bout'
      + (gb.length === 1 ? '' : 's') + ', ' + fmtT(secs) }));
    if (g && g.channel_note) {
      row.appendChild(el('span', { class: 'ss-say warn', text: g.channel_note }));
    }
    row.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Paint them',
      title: 'Adds every ghost bout to Theta Walk. They are yours from '
           + 'then on: drag their edges, or erase any you disagree with.',
      disabled: gb.length ? null : 'disabled',
      onclick: () => setWalk(merge(walk().concat(gb))),
    }));
    return row;
  }

  async function setFinder(k, raw) {
    const v = String(raw == null ? '' : raw).trim();
    let val = null;
    if (v !== '') {
      val = Number(v);
      if (!isFinite(val) || (k !== 'ratio_threshold' && val < 0)) {
        toast('The auto painter needs a number there.', 'err', 5000);
        H.render();
        return;
      }
      if (k === 'theta_channel') val = Math.round(val);
    }
    await saveStrata({ params: { [k]: val } }, true);
    await loadGuide();
  }

  function merge(bouts) {
    const got = bouts.map((b) => [Math.min(b[0], b[1]), Math.max(b[0], b[1])])
      .filter((b) => b[1] - b[0] > 0.2).sort((a, b) => a[0] - b[0]);
    const out = [];
    for (const b of got) {
      const last = out[out.length - 1];
      if (last && b[0] <= last[1]) last[1] = Math.max(last[1], b[1]);
      else out.push(b.slice());
    }
    return out;
  }

  function subtract(bouts, cut) {
    const out = [];
    for (const b of bouts) {
      if (cut[1] <= b[0] || cut[0] >= b[1]) { out.push(b); continue; }
      if (cut[0] > b[0]) out.push([b[0], cut[0]]);
      if (cut[1] < b[1]) out.push([cut[1], b[1]]);
    }
    return out;
  }

  /* Painting is saved a moment after the last stroke, not per stroke. */
  function setWalk(bouts) {
    const sh = sheet();
    if (!sh) return;
    sh.strata = Object.assign({}, sh.strata || {});
    sh.strata.states = Object.assign({}, sh.strata.states || {},
                                     { theta_walk: merge(bouts) });
    H.render();
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(flushStates, 700);
  }

  async function flushStates() {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
    if (!H) return;
    const steps = {};
    /* Painting IS step 0's work, so a change to it re-stamps step 0 -- and
       that is what marks an already-accepted step 1, 2 or 3 as needing a
       look. */
    if ((strata().steps || {})['0']) {
      steps['0'] = Object.assign({}, strata().steps['0'],
                                 { at: new Date().toISOString() });
    }
    await saveStrata(Object.assign({ states: { theta_walk: walk() } },
                                   Object.keys(steps).length ? { steps } : {}),
                     true);
    await load(true);
  }

  async function saveStrata(patch, quiet) {
    try {
      const res = await apiPost(url('state'), { patch });
      if (H) H.adoptSheet(res.sheet);
    } catch (e) {
      toast('That did not save: ' + e.message, 'err', 8000);
    }
    if (H && !quiet) H.render();
  }

  /* The Theta Walk strip. */
  function drawWalk(cv) {
    if (!cv || !cv.isConnected || !guide || !guide.guide) return;
    const g = guide.guide;
    const dpr = window.devicePixelRatio || 1;
    const W = cv.clientWidth || 800, Hh = 128;
    cv.width = Math.round(W * dpr); cv.height = Math.round(Hh * dpr);
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, Hh);
    const end = g.end_s || (g.t.length ? g.t[g.t.length - 1] + 1 : 1);
    const X = (t) => (t / end) * W;
    const specH = 54, ratioTop = 58, ratioH = 46, agreeTop = 108, agreeH = 16;
    const draw = () => {
      ctx.clearRect(0, 0, W, Hh);
      if (img.complete && img.naturalWidth) {
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(img, 0, 0, W, specH);
      }
      // the ghost: the finder's bouts, hatched
      ctx.save();
      ctx.strokeStyle = BARRY.token('--text-3');
      ctx.lineWidth = 1;
      for (const b of g.ghost || []) {
        const x0 = X(b[0]), x1 = X(b[1]);
        ctx.beginPath();
        for (let x = x0; x < x1; x += 5) {
          ctx.moveTo(x, ratioTop + ratioH); ctx.lineTo(Math.min(x1, x + 5),
                                                      ratioTop);
        }
        ctx.globalAlpha = 0.45;
        ctx.stroke();
      }
      ctx.restore();
      // the painted bouts, solid, full height -- or, while an edge is
      // being dragged, the bouts as they will be
      const bouts = paint && paint.bouts ? paint.bouts : walk();
      ctx.save();
      ctx.fillStyle = BARRY.token('--accent');
      ctx.globalAlpha = 0.28;
      for (const b of bouts) {
        const a = Math.min(b[0], b[1]), z = Math.max(b[0], b[1]);
        ctx.fillRect(X(a), 0, Math.max(1, X(z) - X(a)), Hh);
      }
      ctx.globalAlpha = 1;
      ctx.fillStyle = BARRY.token('--accent');
      for (const b of bouts) {
        const a = Math.min(b[0], b[1]), z = Math.max(b[0], b[1]);
        ctx.fillRect(X(a), Hh - 3, Math.max(1, X(z) - X(a)), 3);
        // the edges, which can be taken hold of
        ctx.globalAlpha = 0.85;
        ctx.fillRect(Math.round(X(a)) - 1, 0, 2, Hh);
        ctx.fillRect(Math.round(X(z)) - 1, 0, 2, Hh);
        ctx.globalAlpha = 1;
      }
      ctx.restore();
      // wheel times, on top
      ctx.fillStyle = BARRY.token('--ok');
      for (const w of strata().wheel || []) {
        ctx.fillRect(X(w.t0), 0, Math.max(1, X(w.t1) - X(w.t0)), 3);
      }
      // theta/delta
      const r = g.ratio.filter((v) => v != null);
      if (r.length) {
        let lo = Math.min(...r), hi = Math.max(...r);
        if (hi <= lo) hi = lo + 1;
        const Y = (v) => ratioTop + ratioH - ((v - lo) / (hi - lo)) * ratioH;
        ctx.strokeStyle = BARRY.token('--c3');
        ctx.lineWidth = 1;
        ctx.beginPath();
        let pen = false;
        g.ratio.forEach((v, i) => {
          if (v == null) { pen = false; return; }
          const x = X(g.t[i] + 0.5), y = Y(v);
          if (pen) ctx.lineTo(x, y); else { ctx.moveTo(x, y); pen = true; }
        });
        ctx.stroke();
        ctx.setLineDash([4, 3]);
        ctx.strokeStyle = BARRY.token('--text-2');
        ctx.beginPath();
        ctx.moveTo(0, Y(g.threshold)); ctx.lineTo(W, Y(g.threshold));
        ctx.stroke();
        ctx.setLineDash([]);
      }
      // agreement, as a thin band: brighter = the probe agrees
      g.agreement.forEach((v, i) => {
        if (v == null) return;
        ctx.globalAlpha = Math.max(0.05, v);
        ctx.fillStyle = v >= g.agree_min ? BARRY.token('--ok')
                                         : BARRY.token('--text-3');
        ctx.fillRect(X(g.t[i]), agreeTop, Math.max(1, X(g.t[i] + 1) - X(g.t[i])),
                     agreeH);
      });
      ctx.globalAlpha = 1;
      // where the traces are
      const s = H && H.sess();
      if (s && isFinite(s.t0)) {
        ctx.strokeStyle = BARRY.token('--text');
        ctx.lineWidth = 1.5;
        ctx.strokeRect(X(s.t0), 0.5, Math.max(2, X(s.t0 + s.span) - X(s.t0)),
                       Hh - 1);
      }
      if (paint && paint.grab) {
        // the time of the edge being moved, beside it
        const t = paint.bouts[paint.grab.i][paint.grab.side];
        const x = X(t);
        ctx.font = '600 11px system-ui, sans-serif';
        ctx.textBaseline = 'top';
        ctx.textAlign = x > W - 60 ? 'right' : 'left';
        ctx.fillStyle = BARRY.token('--text');
        ctx.fillText(fmtT(t), x + (x > W - 60 ? -5 : 5), 3);
      }
      if (paint && !paint.bouts) {
        ctx.fillStyle = paint.erase ? BARRY.token('--err')
                                    : BARRY.token('--accent');
        ctx.globalAlpha = 0.35;
        const a = Math.min(paint.t0, paint.t1), b = Math.max(paint.t0, paint.t1);
        ctx.fillRect(X(a), 0, Math.max(1, X(b) - X(a)), Hh);
        ctx.globalAlpha = 1;
      }
    };
    const img = new Image();
    img.onload = draw;
    img.src = g.spec_png;
    draw();
    cv._draw = draw;
    const tAt = (e) => {
      const r = cv.getBoundingClientRect();
      return Math.max(0, Math.min(end, ((e.clientX - r.left) / r.width) * end));
    };
    /* A painted bout's edge, if the pointer is on one: within a few pixels,
       the nearest. */
    const EDGE_PX = 6;
    const edgeAt = (e) => {
      const r = cv.getBoundingClientRect();
      const x = (e.clientX - r.left) * (W / (r.width || W));
      let best = null;
      walk().forEach((b, i) => [0, 1].forEach((side) => {
        const d = Math.abs(X(b[side]) - x);
        if (d <= EDGE_PX && (!best || d < best.d)) best = { i, side, d };
      }));
      return best;
    };
    cv.onmousemove = (e) => {
      if (paint) return;
      cv.style.cursor = !e.shiftKey && edgeAt(e) ? 'ew-resize' : '';
    };
    cv.onmousedown = (e) => {
      e.preventDefault();
      const grab = !(e.shiftKey || e.button === 2) && edgeAt(e);
      if (grab) {
        // Moving an edge: the bout is redrawn as it goes and saved on
        // release; dragged past its other edge or onto a neighbour, the
        // bouts are tidied (merged, a sliver dropped) as painting does.
        paint = { bouts: walk().map((b) => b.slice()), grab, x: e.clientX };
        const moveE = (ev) => {
          paint.bouts[grab.i][grab.side] = tAt(ev);
          draw();
        };
        const upE = (ev) => {
          window.removeEventListener('mousemove', moveE);
          window.removeEventListener('mouseup', upE);
          const p = paint;
          paint = null;
          if (Math.abs(ev.clientX - p.x) < 2) { draw(); return; }
          setWalk(p.bouts);
          requestAnimationFrame(() => {
            const c = document.querySelector('.ss-tw');
            if (c) drawWalk(c);
          });
        };
        window.addEventListener('mousemove', moveE);
        window.addEventListener('mouseup', upE);
        return;
      }
      paint = { t0: tAt(e), t1: tAt(e), erase: e.shiftKey || e.button === 2,
                x: e.clientX };
      const move = (ev) => { paint.t1 = tAt(ev); draw(); };
      const up = (ev) => {
        window.removeEventListener('mousemove', move);
        window.removeEventListener('mouseup', up);
        const p = paint;
        paint = null;
        if (Math.abs(ev.clientX - p.x) < 4) {
          // A click: move the traces there, half a window either side.
          const s = H.sess();
          const span = (s && s.span) || 10;
          BARRY.views.xplore.setWindow(0, Math.max(0, p.t0 - span / 2), span);
          setTimeout(draw, 300);
          return;
        }
        const cut = [Math.min(p.t0, p.t1), Math.max(p.t0, p.t1)];
        setWalk(p.erase ? subtract(walk(), cut) : walk().concat([cut]));
        requestAnimationFrame(() => {
          const c = document.querySelector('.ss-tw');
          if (c) drawWalk(c);
        });
      };
      window.addEventListener('mousemove', move);
      window.addEventListener('mouseup', up);
    };
    cv.oncontextmenu = (e) => e.preventDefault();
  }

  /* ---------- Steps 1-3: anchors, lines, Accept ---------- */
  const OVERRIDE_KEY = { sp: 'sp', fissure: 'fissure', sr_slm: 'sr_slm',
                         gcl1: 'gcl1', gcl2: 'gcl2' };

  function chName(row) {
    const ch = sug && sug.channels ? sug.channels[row] : null;
    return ch == null ? '—' : 'ch ' + ch;
  }

  /* The layers by the short names the strip has room for. "CA1", "DG" and
     "DG2" are the lab's placeholders for "in here, layer not decided" --
     stratum radiatum is ca1_rad. */
  const SHORT = {
    ca1_so: 'SO', ca1_sp: 'SP', ca1_rad: 'SR', ca1_slm: 'SLM', ca1_sr: 'CA1',
    dg_oml1: 'OML1', dg_mml1: 'MML1', dg_iml1: 'IML1', dg_gcl1: 'GCL1',
    hil: 'HIL', dg_gcl2: 'GCL2', dg_iml2: 'IML2', dg_mml2: 'MML2',
    dg_oml2: 'OML2',
  };

  function regionName(id) {
    if (!id) return 'below';
    const r = (H.regions() || []).find((x) => x.id === id);
    return r ? r.name : id;
  }

  function stepAnchors(id) {
    const st = STEPS[+id];
    const prop = sug && sug.steps ? sug.steps[id] : null;
    const box = el('div', { class: 'ss-anchors' });
    box.appendChild(el('div', { class: 'ss-zero-head' }, [
      el('strong', { text: st.title }),
      el('span', { class: 'ss-say', text: st.blurb }),
    ]));
    if (confirming && confirming.id === id) box.appendChild(confirmCard());
    box.appendChild(curveToggles());
    if (sug && sug.masks && sug.masks.theta_all_time && id !== '2') {
      box.appendChild(el('p', { class: 'ss-say warn', text: 'No Theta Walk '
        + 'is painted, so theta and gamma average the whole recording. '
        + 'Step 0 first gives cleaner curves.' }));
    }
    if (!prop) {
      box.appendChild(el('p', { class: 'ss-say', text: 'Nothing to propose '
        + 'yet.' }));
      return box;
    }
    for (const a of prop.anchors || []) box.appendChild(anchorRow(a));
    if (id === '1') box.appendChild(rippleRow());
    if (id === '3') box.appendChild(imlRow(prop));
    for (const n of prop.notes || []) {
      box.appendChild(el('p', { class: 'ss-say warn', text: n }));
    }
    if (id === '3') box.appendChild(icaRow(prop));

    const lines = (ghost && ghost.step === id) ? ghost.lines : [];
    const lbox = el('div', { class: 'ss-lines' });
    lines.forEach((ln) => {
      lbox.appendChild(el('div', { class: 'ss-line' }, [
        el('span', { class: 'ss-line-name', text: regionName(ln.above)
          + ' | ' + regionName(ln.below) }),
        el('span', { class: 'ss-line-at', text: ln.at == null ? 'not placed'
          : 'above ' + chName(ln.at) }),
        el('span', { class: 'ctl-seg', title: 'How sure you are of this '
          + 'line. Saved with the sheet when you accept, kept in the '
          + 'version when you sign off, and exported. It moves nothing.' },
        CONF.map((c) => el('button', {
          class: 'mini' + (ln.confidence === c ? ' on' : ''), text: c,
          title: c + ': ' + CONF_WHY[c] + '\nDrawn ' + (c === 'sure'
            ? 'solid' : c === 'likely' ? 'dashed' : 'dotted')
            + ' on the strip, the traces and the aid window.',
          onclick: () => { ln.confidence = c; H.render(); publish(); },
        }))),
      ]));
    });
    box.appendChild(lbox);
    box.appendChild(el('div', { class: 'ss-actions' }, [
      el('button', {
        class: 'mini', text: more ? '▾ Less' : '▸ More',
        onclick: () => { more = !more; H.render(); },
      }),
      el('button', {
        class: 'btn ghost sm', text: 'Back to the proposal',
        title: 'Put every line back where the evidence put it',
        onclick: () => { overrides = {}; load(); },
      }),
      el('div', { style: 'flex:1' }),
      el('span', { class: 'ss-say', text: 'Drag a dashed line on the strip '
        + 'beside the rail to move it.' }),
      el('button', {
        class: 'btn sm', text: 'Accept ' + st.title.split(' · ')[0],
        disabled: lines.some((l) => l.at != null) ? null : 'disabled',
        onclick: () => acceptLines(id),
      }),
    ]));
    if (more) {
      for (const a of prop.anchors || []) {
        box.appendChild(el('p', { class: 'ss-more' }, [
          el('strong', { text: a.name + '. ' }), a.why || '']));
      }
      box.appendChild(el('p', { class: 'ss-more', text: 'Click a vote to '
        + 'make it the lead: the lines that hang off that anchor move with '
        + 'it. Confidence starts at likely when the votes agree within two '
        + 'channels, guess when they do not.' }));
    }
    box.appendChild(paramsBox());
    return box;
  }

  /* The numbers the steps are worked out with, saved with the sheet (and
     frozen into its version at sign-off). Empty means the default. */
  const PARAMS = [
    ['spacing_um', 'Contact spacing (µm)', 'H3: 20 µm, as '
      + 'HippoCompass measures with'],
    ['species', 'Species', 'mouse or rat; sets the GCL default and '
      + 'whether the atlas checks apply'],
    ['gcl_half_um', 'GCL half-thickness (µm)', '30 mouse, 50 rat'],
    ['lower_ml_scale', 'Lower blade, × the upper', 'the lower '
      + 'molecular layer’s thickness against the upper’s'],
    ['sp_half_um', 'sp half-thickness (µm)', ''],
    ['still_buffer_s', 'Still: buffer around a walk (s)', ''],
    ['ref_channel', 'Reference channel', 'empty: CA1 pyramidal, wherever '
      + 'Step 1 puts it'],
    ['ripple_height_sd', 'Ripple peak (SD)', 'Toothy: 5'],
    ['ripple_edge_sd', 'Ripple edges (SD)', 'Toothy: 3'],
  ];
  let paramsOpen = false;
  let paramsDraft = {};

  function paramsBox() {
    const p = (sug && sug.params) || {};
    const box = el('div', { class: 'ss-params' });
    box.appendChild(el('button', {
      class: 'mini', text: (paramsOpen ? '▾' : '▸') + ' Parameters',
      onclick: () => { paramsOpen = !paramsOpen; paramsDraft = {}; H.render(); },
    }));
    if (!paramsOpen) return box;
    const grid = el('div', { class: 'ss-params-grid' });
    for (const [key, name, hint] of PARAMS) {
      const cur = key in paramsDraft ? paramsDraft[key] : p[key];
      const input = key === 'species'
        ? el('select', {
          class: 'ss-in wide',
          onchange: (e) => { paramsDraft[key] = e.target.value; },
        }, ['mouse', 'rat'].map((sp) => el('option', {
          value: sp, text: sp, selected: (cur || 'mouse') === sp ? 'selected'
            : null })))
        : el('input', {
          class: 'ss-in', value: cur == null ? '' : String(cur),
          placeholder: 'default',
          oninput: (e) => { paramsDraft[key] = e.target.value; },
        });
      grid.appendChild(el('label', { class: 'ss-param', title: hint }, [
        el('span', { text: name }), input]));
    }
    box.appendChild(grid);
    box.appendChild(el('div', { class: 'ss-actions' }, [
      el('button', {
        class: 'btn sm', text: 'Save and work it out again',
        onclick: async () => {
          const patch = {};
          for (const [key] of PARAMS) {
            if (!(key in paramsDraft)) continue;
            const v = String(paramsDraft[key]).trim();
            if (!v) { patch[key] = null; continue; }
            if (key === 'species') { patch[key] = v; continue; }
            const num = Number(v);
            if (!isFinite(num)) {
              toast(key.replace(/_/g, ' ') + ' has to be a number.', 'err',
                    6000);
              return;
            }
            patch[key] = num;
          }
          paramsDraft = {};
          await saveStrata({ params: patch }, true);
          await load();
        },
      }),
    ]));
    return box;
  }

  function anchorRow(a) {
    const key = OVERRIDE_KEY[a.key];
    const pick = (row) => {
      if (!key) return;
      overrides[key] = row;
      load();
    };
    return el('div', { class: 'ss-anchor' }, [
      el('span', { class: 'ss-anchor-name', text: a.name }),
      el('span', {
        class: 'ss-lead', title: 'The lead: what placed this.',
      }, [el('b', { text: chName(a.lead.row) }),
          el('span', { text: ' ' + a.lead.name })]),
      el('span', { class: 'ss-votes' }, (a.votes || []).map((v) =>
        el('button', {
          class: 'ss-vote' + (Math.abs(v.off || 0) <= 1 ? ' near'
            : Math.abs(v.off || 0) <= 3 ? '' : ' far'),
          title: v.name + ' — click to make it the lead',
          onclick: () => pick(v.row),
        }, [el('b', { text: chName(v.row) }),
            el('span', { text: ' ' + v.name + ' ' }),
            el('i', { text: v.off == null ? '' : (v.off > 0 ? '+' : '')
              + v.off })]))),
      el('span', { class: 'ss-conf ' + a.confidence, text: a.confidence }),
    ]);
  }

  /* Whether the molecular layer is cut in three (OML, MML, IML) or two
     (OML, then MML down to the granule layer -- the lab's own scheme). Saved
     with the sheet's parameters. */
  function imlRow(prop) {
    const scheme = prop.ml_scheme === 'iml' || prop.ml_scheme === 'mml'
      ? prop.ml_scheme : (prop.use_iml === false ? 'mml' : 'iml');
    const set = async (v) => {
      if (v === scheme) return;
      await saveStrata({ params: { ml_scheme: v, use_iml: v === 'iml' } }, true);
      await load();
    };
    const thal = (prop.below_lower || 'thal') === 'thal';
    const setBelow = async (v) => {
      if ((v === 'thal') === thal) return;
      await saveStrata({ params: { below_lower: v } }, true);
      await load();
    };
    return el('div', { class: 'ss-lines' }, [imlSwitch(), el('div', {
      class: 'ss-line' }, [
      el('span', { class: 'ss-line-name', text: 'Below the lower blade' }),
      el('span', { class: 'ctl-seg', title: 'The lower blade mirrors the '
        + 'upper one: from the hilus down the same distance as the fissure '
        + 'is above it (times "Lower blade" in Parameters). What is under '
        + 'that is thalamus, or can be left as it is.' }, [
        el('button', { class: 'mini' + (thal ? ' on' : ''), text: 'THAL',
                       onclick: () => setBelow('thal') }),
        el('button', { class: 'mini' + (thal ? '' : ' on'), text: 'leave as is',
                       onclick: () => setBelow('none') }),
      ]),
    ])]);

    function imlSwitch() {
    return el('div', { class: 'ss-line' }, [
      el('span', { class: 'ss-line-name', text: 'Inner molecular layer' }),
      el('span', { class: 'ctl-seg' }, [
        el('button', { class: 'mini' + (scheme === 'iml' ? ' on' : ''),
                       text: 'its own (IML)',
                       title: 'GCL at its thickness against the hilus; the '
                         + 'molecular layer above it in thirds: OML, MML, IML.',
                       onclick: () => set('iml') }),
        el('button', { class: 'mini' + (scheme === 'mml' ? ' on' : ''),
                       text: 'part of MML',
                       title: 'Leave IML out: the inner third is part of the '
                         + 'MML (the lab\u2019s scheme). The OML line stays '
                         + 'at a third, where the anatomy has it, and the GCL '
                         + 'keeps its own thickness: the molecular layer is '
                         + 'three bands of about equal width and the granule '
                         + 'layer is not one of them.',
                       onclick: () => set('mml') }),
      ]),
    ]);
    }
  }

  /* The ripples Step 1 leans on, and a way to keep them. They go into the
     Event Bank as a detector's output, type ripple, through the one bank
     dialog. Checkup has no ripple vocabulary yet (dentate spikes and IEDs
     only), so a banked set is a record of what the detector found until it
     does. */
  function rippleRow() {
    const r = sug && sug.ripples;
    const row = el('div', { class: 'ss-ica' });
    if (!r) return row;
    row.appendChild(el('span', { class: 'ss-say', text: r.n
      ? r.n + ' ripples in ' + fmtT(r.still_s || 0) + ' of still time on '
        + 'ch ' + r.channel + ' (' + r.rate_per_min + ' a minute), by '
        + 'Toothy\u2019s detector.'
      : (r.why || 'No ripples found in still time on ch ' + r.channel
         + '.') }));
    if (r.n) {
      row.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Bank the ripples\u2026',
        title: 'Put them in the Event Bank as a detector\u2019s output, '
             + 'with every parameter that found them.',
        onclick: bankRipples,
      }));
    }
    return row;
  }

  async function bankRipples() {
    let rip, row;
    try {
      rip = (await apiPost(url('ripples'), body({ channel: sug.ripples.channel,
                                                  overrides }))).ripples;
      row = (await api('/api/registry/' + encodeURIComponent(H.gid))).session
        || {};
    } catch (e) {
      toast('Could not read the ripples: ' + e.message, 'err', 8000);
      return;
    }
    const evs = rip.events || [];
    await BARRY.ui.bankDialog({
      kind: 'entry',
      title: 'Bank ' + evs.length + ' ripples',
      name: BARRY.bankName.suggest(row, 'Ripples ch ' + rip.channel),
      what: 'They go in as a detector\u2019s output, not as a curated set: '
          + 'nothing is decided. Checkup cannot vet ripples yet (it knows '
          + 'dentate spikes and IEDs), so for now this is the record of '
          + 'what the detector found.',
      where: 'Filed under ' + [row.project || 'Unfiled',
                               row.mouse != null ? 'm' + row.mouse : null,
                               row.session != null ? 's' + row.session : null]
        .filter(Boolean).join(' / ') + ' in the Event Bank.',
      facts: [
        'Still time only: the Theta Walk painted in Step 0, less '
          + (((sug.params || {}).still_buffer_s) || 2) + ' s either side.',
        'Every detection parameter goes with them: Toothy\u2019s '
          + 'get_swr_peaks, 120-180 Hz, 5 SD peaks, 3 SD edges.',
      ],
      okText: 'Bank them',
      onBank: async ({ name, note, who }) => {
        await apiPost('/api/bank/add', {
          gid: H.gid,
          project: row.project, mouse: row.mouse, session: row.session,
          session_key: row.key, session_loose_key: row.loose_key,
          session_label: row.label, duration_s: row.duration_s,
          type: 'ripple', type_name: 'Ripple',
          name, note: note || undefined,
          pipeline: 'StrataScope ripples (Toothy get_swr_peaks, still time)',
          added_by: who,
          session_path: H.path(),
          parameters: Object.assign({ channel: rip.channel,
                                      still_s: rip.still_s,
                                      theta_walk_bouts: walk().length },
                                    rip.params || {}),
          events: evs.map((e) => ({ start: e.t, end: e.end,
                                    channel: rip.channel,
                                    amplitude: e.amp })),
        });
        toast('Banked ' + evs.length + ' ripples.', 'ok');
        return true;
      },
    });
  }

  function icaRow(prop) {
    const row = el('div', { class: 'ss-ica' });
    if (jobKind === 'ica') {
      row.appendChild(el('div', { class: 'ss-job' }, [
        el('i', { style: 'width:' + jobPct() + '%' }),
        el('span', { text: jobText() }),
      ]));
      return row;
    }
    const chk = prop.ica_checks || [];
    const helpBtn = () => el('button', {
      class: 'ss-help' + (icaHelp ? ' on' : ''), text: '?',
      title: 'How Method B works',
      onclick: () => { icaHelp = !icaHelp; H.render(); },
    });
    if (!sug.ica_ready) {
      row.appendChild(el('span', { class: 'ss-say', text: 'Method B has not '
        + 'run on these Theta Walk seconds yet.' }));
      row.appendChild(helpBtn());
      row.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Run ICA (Method B)',
        title: 'Unmix the gamma field into its generators: 25-200 Hz, '
             + 'then 90-160 and 55-90 Hz on their own. Uses the Theta Walk '
             + 'seconds (at least 30 s); refits on each half to see which '
             + 'components are stable. Takes a minute or two.',
        onclick: runIca,
      }));
      const box0 = el('div', { class: 'ss-ica-box' }, [row]);
      if (icaHelp) box0.appendChild(icaExplain());
      return box0;
    }
    row.appendChild(el('span', { class: 'section-label', text: 'Method B '
      + 'says' }));
    row.appendChild(helpBtn());
    /* One verdict per layer, said plainly (2026-10-12: "indicate if it
       matches our expectations"): a tick where the gamma sits in the layer
       it should, a cross where it sits somewhere else, a dash where ICA
       found nothing it can vouch for. */
    const vs = chk.map(icaVerdict);
    const found = vs.filter((v) => v.status !== 'none');
    const good = vs.filter((v) => v.status === 'match');
    row.appendChild(el('span', { class: 'ss-say', text: !found.length
      ? 'Nothing it can vouch for yet.'
      : good.length === found.length
        ? 'Agrees with Method A wherever it found something.'
        : (found.length - good.length) + ' of ' + found.length
          + ' disagree with Method A.' }));
    const chips = el('div', { class: 'ss-verdicts' });
    chk.forEach((c, k) => {
      const v = vs[k];
      const on = icaPick && icaPick.region === c.region && icaPick.kind === c.kind;
      chips.appendChild(el('button', {
        class: 'ss-verdict ' + v.status + (on ? ' picked' : ''),
        title: 'Click to see it on the strip and the traces, and what it means',
        onclick: () => {
          icaPick = on ? null : c;
          H.render();
          drawStrip();
          H.redraw();
        },
      }, [el('b', { text: v.icon }), el('span', { text: v.text })]));
    });
    const box = el('div', { class: 'ss-ica-box' }, [row, chips]);
    if (icaPick) box.appendChild(icaCompare(icaPick));
    if (icaHelp) box.appendChild(icaExplain());
    return box;
  }

  let icaHelp = false;
  let icaPick = null;

  /* What one check means, in a sentence, and where it is on the strip and
     the traces (drawn while it is picked). */
  const layerShort = (id) => SHORT[id] || regionName(id);
  const kindName = (k) => (k === 'slow' ? 'slow \u03b3'
    : k === 'mid' ? 'mid \u03b3' : 'fast \u03b3');
  /* The colours are the depth curves' where there is one: slow gamma's
     curve is --c2, mid (60-100 Hz) is --warn. */
  const kindTok = (k) => (k === 'slow' ? '--c2' : k === 'mid' ? '--warn' : '--c4');
  /* Fernandez-Ruiz et al. 2021 (Science 372:eabf3119): the dentate's three
     gamma inputs, each into its own third of the molecular layer. */
  const KIND_WHY = {
    slow: 'Slow gamma (30-50 Hz) comes from the lateral entorhinal cortex, '
      + 'whose input ends in the outer third of the molecular layer',
    mid: 'Mid gamma (60-80 Hz) comes from the commissural input from the '
      + 'other hippocampus, which ends in the inner third',
    fast: 'Fast gamma (100-150 Hz) comes from the medial entorhinal cortex, '
      + 'whose input ends in the middle third',
  };

  function icaVerdict(c) {
    const layer = layerShort(c.region);
    if (c.row == null) {
      return { status: 'none', icon: '\u2013',
               text: kindName(c.kind) + ': nothing reliable in ' + layer };
    }
    if (c.agree) {
      return { status: 'match', icon: '\u2713',
               text: kindName(c.kind) + ' sits in ' + layer + ' ('
                 + chName(c.row) + ')' };
    }
    return { status: 'off', icon: '\u2717',
             text: kindName(c.kind) + ' sinks ' + Math.abs(c.off) + ' ch '
               + (c.off > 0 ? 'below ' : 'above ') + layer };
  }

  /* Where a channel sits now: in the step's proposal if it has one there,
     else on the sheet. */
  function regionAtRow(row) {
    const ch = sug && sug.channels ? sug.channels[row] : null;
    if (ch == null) return null;
    const prop = proposedLabels();
    const id = (prop && prop.get(ch)) || ((sheet() || {}).labels || {})[String(ch)];
    return id ? layerShort(id) : 'unlabelled';
  }

  /* What one verdict means, in plain words. */
  function icaCompare(c) {
    const layer = layerShort(c.region);
    const expect = (KIND_WHY[c.kind] || KIND_WHY.fast) + ', so it should '
      + 'sink in ' + layer + '.';
    let say;
    if (c.row == null) {
      // The strongest trusted source of this kind, to say where it went.
      const best = ((ica && ica.components) || [])
        .filter((x) => x.kind === c.kind && (x.stability || 0) >= 0.7)
        .sort((a, b) => b.variance - a.variance)[0];
      const near = ((ica && ica.components) || [])
        .filter((x) => x.kind === c.kind)
        .sort((a, b) => b.variance - a.variance)[0];
      const where = best && best.sink_row != null
        ? ' The strongest ' + kindName(c.kind) + ' source it does trust '
          + 'sinks at ch ' + best.sink_channel + ', in '
          + regionAtRow(best.sink_row) + ' -- not in ' + layer + '.'
        : near
          ? ' The nearest thing it found is a ' + near.peak_hz + ' Hz '
            + 'source, but it came back only '
            + Math.round(100 * (near.stability || 0)) + '% alike in the two '
            + 'halves (it needs 70%).'
          : ' ICA found no ' + kindName(c.kind) + ' source at all.';
      say = 'Nothing reliable means ICA found no ' + kindName(c.kind)
        + ' source it can trust sitting in ' + layer + '. To be trusted a '
        + 'source has to come back when ICA is run again on each half of '
        + 'the walking separately, and to count for ' + layer + ' its '
        + 'current sink has to be there.' + where + ' So Method B says '
        + 'nothing about this line: it neither confirms nor contradicts '
        + 'it.' + (c.kind === 'slow' ? '' : ' That is common for '
          + kindName(c.kind) + ' in mice, which is small and gets mixed '
          + 'into other sources.') + ' More Theta Walk helps.';
    } else if (c.agree) {
      say = 'Matches. ' + expect + ' It sinks at ' + chName(c.row)
        + ', which is in ' + layer + ' as Method A drew it.';
    } else {
      say = 'Does not match. ' + expect + ' It sinks at ' + chName(c.row)
        + ', in ' + regionAtRow(c.row) + ', ' + Math.abs(c.off) + ' channel'
        + (Math.abs(c.off) === 1 ? '' : 's') + ' '
        + (c.off > 0 ? 'below' : 'above') + ' where Method A put ' + layer
        + '. Either the thirds are off here, or this source is not that '
        + 'input. The strip and the traces mark where ' + layer + ' would '
        + 'reach to take it in.';
    }
    /* Off: the line that would take the sink in, and a button to move it
       there (the same as the evidence window's). */
    let mv = null;
    if (c.row != null && !c.agree && ghost && ghost.step === '3') {
      const top = ghost.lines.find((l) => l.below === c.region);
      const bot = ghost.lines.find((l) => l.above === c.region);
      if (c.off < 0 && top && top.at != null && c.row < top.at) {
        mv = { ln: top, to: c.row };
      } else if (c.off > 0 && bot && bot.at != null && c.row >= bot.at) {
        mv = { ln: bot, to: c.row + 1 };
      }
    }
    if (!mv) return el('p', { class: 'ss-more', text: say });
    return el('div', { class: 'ss-more' }, [
      el('p', { text: say }),
      el('button', {
        class: 'btn ghost sm ss-move',
        text: 'Move ' + layerShort(mv.ln.above) + ' | '
          + layerShort(mv.ln.below) + ' to above ' + chName(mv.to),
        title: 'It stays a proposal until you Accept.',
        onclick: () => moveGhost(mv.ln, mv.to),
      }),
    ]);
  }

  function icaExplain() {
    return el('div', { class: 'ss-more' }, [
      el('p', { text: 'Method B, in four steps.' }),
      el('p', { text: '1. The gamma-band field (25-200 Hz) recorded during '
        + 'Theta Walk is a mix of a few generators: groups of synapses '
        + 'firing together, each felt on every contact with a different '
        + 'strength. ICA (independent component analysis) unmixes them '
        + 'into about ten sources that are statistically independent of '
        + 'each other. Gamma power falls with frequency, so in that one '
        + 'run slow gamma takes every source; ICA is run again on 90-160 Hz '
        + 'and on 55-90 Hz alone, where fast and mid gamma are the biggest '
        + 'thing there is.' }),
      el('p', { text: '2. Each source has a loading -- how strongly it '
        + 'shows on each channel -- and a time course. The CSD of the '
        + 'loading has a sink where the generator\u2019s synapses are; '
        + 'that is the "where". The time course\u2019s spectrum says '
        + 'which frequency it carries; that is the "what".' }),
      el('p', { text: '3. In the dentate each input brings its own gamma '
        + '(Fern\u00e1ndez-Ruiz et al. 2021, Science): slow (30-50 Hz) from '
        + 'the lateral entorhinal cortex into the outer third of the '
        + 'molecular layer, fast (100-150 Hz) from the medial entorhinal '
        + 'cortex into the middle third, and mid (60-80 Hz) from the '
        + 'commissural input into the inner third. A source from the '
        + '90-160 Hz run is fast and one from the 55-90 Hz run is mid; one '
        + 'from the broad run is called by its peak (under 55 Hz slow, 55-90 '
        + 'mid, 90 and up fast). So a slow '
        + 'source should sink in OML, a mid one in IML, a fast one in MML '
        + '-- an answer that never used Method A\u2019s thirds. Mid is only '
        + 'checked when IML is its own layer.' }),
      el('p', { text: '4. Every source is fitted again on the first and the '
        + 'second half of the walking. Only sources that come back in both '
        + '(their loadings correlate at 0.7 or more) are trusted. "Agrees" '
        + 'means a trusted source sinks inside the layer Method A drew; '
        + '"N ch off" means it sinks N channels outside it; "nothing '
        + 'reliable" means no trusted source sinks there.' }),
    ]);
  }

  async function runIca() {
    try {
      const res = await apiPost(url('ica'), body({ overrides }));
      if (res.cached) { ica = res.ica; await load(true); return; }
      jobId = res.job.id; jobKind = 'ica'; jobSnap = res.job;
      H.render();
      poll();
    } catch (e) {
      toast('ICA could not start: ' + e.message, 'err', 9000);
    }
  }

  async function peekIca() {
    try {
      const res = await apiPost(url('ica'), body({ peek: true, overrides }));
      if (res.ica) ica = res.ica;
      else if (res.job && !jobId && H) {
        jobId = res.job.id; jobKind = 'ica'; jobSnap = res.job;
        H.render();
        poll();
      }
    } catch (e) { /* the button says so */ }
  }

  /* Rows -> region from a stack of lines: a row takes the region below the
     last line at or above it. The same rule as stratasteps.labels_from_lines,
     so the sheet gets what the strip shows. */
  function labelsFromLines(lines, start, end) {
    const ls = lines.filter((l) => l.at != null).slice()
      .sort((a, b) => a.at - b.at);
    const out = {};
    for (let r = Math.max(0, start); r < end; r++) {
      let region;
      for (const l of ls) {
        if (l.at <= r) region = l.below;
        else { if (region === undefined) region = l.above; break; }
      }
      if (region) out[r] = region;
    }
    return out;
  }

  function stepSpan(id, lines) {
    const n = sug.channels.length;
    const at = (b) => { const l = lines.find((x) => x.below === b
                                             || (b === null && x.below == null));
                        return l ? l.at : null; };
    const atAbove = (a) => { const l = lines.find((x) => x.above === a);
                             return l ? l.at : null; };
    if (id === '1') return [0, at('dg_oml1') != null ? at('dg_oml1') : n];
    if (id === '2') return [atAbove('dg_gcl1') != null ? atAbove('dg_gcl1') : 0,
                            at('dg_gcl2') != null ? at('dg_gcl2') : n];
    const top = at('dg_oml1');
    const bot = lines.find((x) => x.below == null);
    return [top != null ? top : 0, bot ? bot.at : n];
  }

  async function acceptLines(id) {
    const lines = (ghost && ghost.lines) || [];
    const [a, b] = stepSpan(id, lines);
    const rows = labelsFromLines(lines, a, b);
    const labels = {};
    for (const r in rows) labels[sug.channels[r]] = rows[r];
    const confidence = {};
    for (const l of lines) if (l.id) confidence[l.id] = l.confidence;
    const anchors = {};
    const prop = sug.steps[id];
    const chOf = (row) => (row == null ? null : sug.channels[row]);
    if (id === '1') {
      const sp = (prop.anchors || []).find((x) => x.key === 'sp');
      const f = lines.find((l) => l.below === 'dg_oml1');
      if (sp) anchors.sp = chOf(sp.lead.row);
      if (f && f.at != null) anchors.fissure_at = chOf(f.at);
    } else if (id === '2') {
      for (const k of ['gcl1', 'gcl2']) {
        const x = (prop.anchors || []).find((y) => y.key === k);
        if (x && x.lead.row != null) anchors[k] = chOf(x.lead.row);
      }
    }
    /* Not written yet: first the drawer says, channel by channel, what
       this would change, and waits for Continue (2026-10-12). */
    confirming = { id, labels, confidence, anchors,
                   changes: changeRuns(labels) };
    H.render();
    const d = document.querySelector('.ss-drawer');
    if (d) d.scrollTop = 0;
  }

  let confirming = null;

  /* What Accept would do to the sheet, as runs of neighbouring channels
     going from the same label to the same label: "ch 6-9: CA1 -> CA1 SR". */
  function changeRuns(labels) {
    const cur = ((sheet() || {}).labels) || {};
    const runs = [];
    let same = 0;
    for (const ch of sug.channels) {
      if (!(ch in labels) && !(String(ch) in labels)) continue;
      const now = labels[ch] || labels[String(ch)] || null;
      const was = cur[String(ch)] || null;
      if (now === was) { same += 1; continue; }
      const last = runs[runs.length - 1];
      if (last && last.was === was && last.now === now
          && sug.channels.indexOf(last.to) === sug.channels.indexOf(ch) - 1) {
        last.to = ch;
        last.n += 1;
      } else {
        runs.push({ from: ch, to: ch, n: 1, was, now });
      }
    }
    return { runs, same };
  }

  function confirmCard() {
    const c = confirming;
    const ch = (r) => (r.from === r.to ? 'Ch ' + r.from
                                        : 'Ch ' + r.from + '\u2013' + r.to);
    const name = (id) => (id ? regionName(id) : 'unlabelled');
    const list = el('ul', { class: 'ss-changes' }, c.changes.runs.map((r) =>
      el('li', {}, [
        el('b', { text: ch(r) }),
        el('span', { class: 'was', text: name(r.was) }),
        el('span', { class: 'arrow', text: '\u2192' }),
        el('span', { class: 'now', text: name(r.now) }),
      ])));
    const total = c.changes.runs.reduce((a, r) => a + r.n, 0);
    return el('div', { class: 'ss-confirm' }, [
      el('strong', { text: total
        ? 'This will change ' + total + ' channel' + (total === 1 ? '' : 's')
          + ':'
        : 'No channel changes.' }),
      total ? list : el('p', { class: 'ss-say', text: 'Accepting records '
        + 'the step as done, with the confidence of each line.' }),
      c.changes.same ? el('p', { class: 'ss-say', text: c.changes.same
        + ' channel' + (c.changes.same === 1 ? '' : 's')
        + ' in the step already say what it proposes.' }) : null,
      el('div', { class: 'ss-actions' }, [
        el('button', {
          class: 'btn ghost sm', text: 'Back',
          onclick: () => { confirming = null; H.render(); },
        }),
        el('div', { style: 'flex:1' }),
        el('button', {
          class: 'btn sm', text: 'Continue',
          onclick: async () => {
            const k = confirming;
            confirming = null;
            await accept(k.id, k.labels, k.confidence, k.anchors);
            openStep(String(+k.id + 1));
          },
        }),
      ]),
    ].filter(Boolean));
  }

  /* What Accept would write in the open step: channel -> region. Drawn
     hatched on the traces and the CSD until it is accepted. */
  function proposedLabels() {
    if (!open || open === '0' || open === '4' || !sug || !ghost
        || ghost.step !== open) return null;
    const [a, b] = stepSpan(open, ghost.lines);
    const rows = labelsFromLines(ghost.lines, a, b);
    const out = new Map();
    for (const r in rows) out.set(sug.channels[r], rows[r]);
    return out;
  }

  async function accept(id, labels, confidence, anchors) {
    try {
      const res = await apiPost(url('accept'), {
        step: id, labels, confidence: confidence || null,
        anchors: anchors && Object.keys(anchors).length ? anchors : null,
        basis: { overrides, at: new Date().toISOString() },
      });
      H.adoptSheet(res.sheet);
      toast(STEPS[+id].title + ' accepted' + (Object.keys(labels || {}).length
        ? ': ' + Object.keys(labels).length + ' channels labelled.' : '.'),
            'ok');
    } catch (e) {
      toast('Not accepted: ' + e.message, 'err', 9000);
    }
  }

  /* ---------- Step 4: checks and sign off ---------- */
  async function loadChecks() {
    try {
      checks = (await apiPost(url('checks'), body())).checks;
    } catch (e) {
      checks = null;
      toast('The checks could not run: ' + e.message, 'err', 8000);
    }
  }

  function stepFour() {
    const box = el('div', { class: 'ss-four' });
    box.appendChild(el('div', { class: 'ss-zero-head' }, [
      el('strong', { text: STEPS[4].title }),
      el('span', { class: 'ss-say', text: STEPS[4].blurb }),
    ]));
    const list = el('ul', { class: 'ss-checks' });
    for (const c of checks || []) {
      list.appendChild(el('li', { class: c.ok ? 'ok' : 'warn' }, [
        el('span', { class: 'ss-tick', text: c.ok ? '✓' : '!' }),
        el('span', { text: c.text }),
      ]));
    }
    if (!checks) list.appendChild(el('li', { text: 'Working…' }));
    box.appendChild(list);
    const signed = strata().signed || {};
    box.appendChild(el('div', { class: 'ss-actions' }, [
      el('span', { class: 'ss-say', text: signed.at
        ? 'Last signed off by ' + (signed.by || 'somebody') + ', '
          + String(signed.at).slice(0, 16).replace('T', ' ') + ' (v'
          + signed.v + ').'
        : 'Not signed off yet. Warnings never block; they are kept with the '
          + 'version.' }),
      el('div', { style: 'flex:1' }),
      el('button', {
        class: 'btn ghost sm', text: 'Export JSON',
        onclick: () => window.open(url('export.json'), '_blank'),
      }),
      el('button', {
        class: 'btn sm', text: 'Sign off',
        onclick: signOff,
      }),
    ]));
    return box;
  }

  async function signOff() {
    try {
      const res = await apiPost(url('signoff'), body());
      H.adoptSheet(res.sheet);
      checks = res.checks;
      const warn = (res.checks || []).filter((c) => !c.ok).length;
      toast('Signed off' + (warn ? ', with ' + warn + ' warning'
        + (warn === 1 ? '' : 's') + ' kept beside it.' : '.'), 'ok', 7000);
    } catch (e) {
      toast('Not signed off: ' + e.message, 'err', 9000);
    }
    H.render();
  }

  /* The channels Accept would write in the open step, or null when every
     channel is in play (no step, or Step 4). Step 0 writes no labels, so
     every channel is out of it. */
  function affected() {
    if (!H || !open || open === '4') return null;
    if (open === '0') return new Set();
    if (!sug || !sug.channels || !ghost || ghost.step !== open) return null;
    const [a, b] = stepSpan(open, ghost.lines);
    return new Set(sug.channels.slice(Math.max(0, a), Math.max(0, b)));
  }

  function focusRegions() {
    const f = open ? FOCUS[open] : null;
    return f && f.regions ? new Set(f.regions) : null;
  }

  /* Profile rows (every channel, sheet order) against lanes (the channels
     the traces draw). A line above profile row r sits above the first
     drawn channel at or after r. */
  function laneOfRow(row, chans) {
    if (row == null || !sug || !sug.channels) return null;
    const pos = new Map(chans.map((c, i) => [c.number, i]));
    for (let r = Math.max(0, row); r < sug.channels.length; r++) {
      const i = pos.get(sug.channels[r]);
      if (i != null) return i;
    }
    return chans.length;
  }

  function rowOfLane(i, chans) {
    if (!sug || !sug.channels) return null;
    if (i >= chans.length) return sug.channels.length;
    const r = sug.channels.indexOf(chans[Math.max(0, i)].number);
    return r < 0 ? null : r;
  }

  /* ==================================================================
     The depth strip, beside the rail
     ================================================================== */
  function railStrip(rail) {
    if (!H) return;
    let cv = rail.querySelector('.ss-strip');
    if (!cv) {
      cv = el('canvas', { class: 'ss-strip' });
      rail.appendChild(cv);
      cv.addEventListener('mousedown', stripDown);
      cv.addEventListener('mousemove', stripHover);
      cv.addEventListener('mouseleave', () => { cv.style.cursor = ''; });
    }
    stripCanvas = cv;
  }

  /* Which curves the strip draws: the open step's, at the top of its
     drawer. They used to sit in the rail above the strip, where there is
     not always room -- on a short pane they covered the channel count. The
     step's own curves first, full or faint as the strip draws them; the
     others after a divider, off until clicked. */
  function curveToggles() {
    const f = open ? FOCUS[open] : null;
    const mine = f ? f.lead.concat(f.votes) : ['mua', 'theta'];
    const chip = (c) => el('button', {
      class: 'ss-curve' + (shown.has(c.id) ? ' on' : '')
           + (f && f.votes.includes(c.id) ? ' vote' : ''),
      style: '--cv:var(' + c.tok + ')',
      title: c.why + '\nClick to show or hide it on the strip.',
      onclick: () => {
        if (shown.has(c.id)) shown.delete(c.id); else shown.add(c.id);
        H.render();
      },
    }, [el('i'), el('span', { text: c.name })]);
    const own = CURVES.filter((c) => mine.includes(c.id));
    const rest = CURVES.filter((c) => !mine.includes(c.id));
    return el('div', { class: 'ss-legend-row' }, [
      el('span', { class: 'section-label', text: 'On the strip' }),
      ...own.map(chip),
      rest.length ? el('span', { class: 'ss-legend-gap', text: '\u00b7' }) : null,
      ...rest.map(chip),
    ].filter(Boolean));
  }

  function stripWidth() { return H ? STRIP_W : 0; }

  /* Called by strata.js's alignRail with the lanes' geometry. */
  function layout(top, height, n) {
    strip = { top, height, n, lane: height / Math.max(1, n) };
    if (!stripCanvas) return;
    stripCanvas.style.top = top + 'px';
    stripCanvas.style.height = height + 'px';
    stripCanvas.style.width = STRIP_W + 'px';
    drawStrip();
  }

  function norm(vals) {
    const v = vals.filter((x) => x != null && isFinite(x));
    if (!v.length) return vals.map(() => null);
    let lo = Math.min(...v), hi = Math.max(...v);
    if (hi <= lo) hi = lo + 1;
    return vals.map((x) => (x == null || !isFinite(x)) ? null
                                                       : (x - lo) / (hi - lo));
  }

  function profileRows() {
    /* The strip is drawn on the rail's channels; the profile carries its
       own channel order, which can be shorter (a channel not read). */
    const chans = H.channels();
    const p = sug && sug.profile;
    if (!p) return null;
    const idx = new Map(p.channels.map((c, i) => [c, i]));
    return chans.map((c) => (idx.has(c.number) ? idx.get(c.number) : null));
  }

  function drawStrip() {
    const cv = stripCanvas;
    if (!cv || !cv.isConnected || !H) return;
    const dpr = window.devicePixelRatio || 1;
    const W = STRIP_W, Hh = Math.max(1, strip.height);
    cv.width = Math.round(W * dpr); cv.height = Math.round(Hh * dpr);
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, Hh);
    const chans = H.channels();
    const n = chans.length || 1;
    const lane = Hh / n;
    const pad = 6;
    if (!sug || !sug.profile) {
      ctx.fillStyle = BARRY.token('--text-3');
      ctx.font = '10.5px system-ui, sans-serif';
      ctx.textAlign = 'center';
      const say = (status && status.scanned) ? 'working\u2026'
                                             : 'not read yet';
      ctx.fillText(say, W / 2, Math.min(Hh / 2, 40));
      return;
    }
    const map = profileRows();
    const curves = sug.profile.curves;
    const f = open ? FOCUS[open] : null;
    const lead = new Set(f ? f.lead : []);
    // faint lane grid every 4 channels
    ctx.fillStyle = BARRY.token('--line-soft');
    for (let i = 0; i < n; i += 4) ctx.fillRect(0, Math.round(i * lane), W, 1);
    for (const c of CURVES) {
      if (!shown.has(c.id) || !curves[c.id]) continue;
      const v = norm(map.map((k) => (k == null ? null : curves[c.id][k])));
      const strong = !f || lead.has(c.id);
      ctx.globalAlpha = strong ? 1 : 0.45;
      ctx.strokeStyle = BARRY.token(c.tok);
      ctx.lineWidth = strong ? 1.8 : 1;
      curve(ctx, v.map((x, i) => (x == null ? null
        : [pad + x * (W - 2 * pad), (i + 0.5) * lane])));
    }
    ctx.globalAlpha = 1;
    // A channel with no value (marked bad, or not read): a small cross at
    // the edge, so the dotted stretch above says why it is dotted.
    if (map) {
      const bad = new Set((sug.bad || []).map(Number));
      ctx.fillStyle = BARRY.token('--text-3');
      ctx.font = '9px system-ui, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      chans.forEach((c, i) => {
        if (bad.has(c.number) || map[i] == null) {
          ctx.fillText('\u00d7', 1, (i + 0.5) * lane);
        }
      });
    }
    // the reference channel: R
    if (sug.ref_channel != null) {
      const i = chans.findIndex((c) => c.number === sug.ref_channel);
      if (i >= 0) {
        ctx.fillStyle = BARRY.token('--c4');
        ctx.font = 'bold 9px system-ui, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText('R', 1, (i + 0.5) * lane);
      }
    }
    /* Out of the step: channels Accept would not write are veiled, so the
       part of the probe the step is about is the only part in colour. */
    const aff = affected();
    if (aff) {
      ctx.fillStyle = BARRY.token('--bg');
      ctx.globalAlpha = 0.72;
      chans.forEach((c, i) => {
        if (!aff.has(c.number)) {
          ctx.fillRect(0, Math.floor(i * lane), W, Math.ceil(lane) + 1);
        }
      });
      ctx.globalAlpha = 1;
    }
    // accepted boundaries: the step's own layers in colour, the rest grey
    const sh = sheet();
    const lab = (c) => (sh && sh.labels ? sh.labels[String(c.number)] : null);
    const regs = H.regions() || [];
    const fr = focusRegions();
    for (let i = 1; i < n; i++) {
      const a = lab(chans[i - 1]), b = lab(chans[i]);
      if (a === b) continue;
      const y = Math.round(i * lane) + 0.5;
      const mineA = !fr || fr.has(a), mineB = !fr || fr.has(b);
      if (!(mineA || mineB)) {
        ctx.globalAlpha = 0.5;
        ctx.strokeStyle = BARRY.token('--text-3');
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
        ctx.globalAlpha = 1;
        continue;
      }
      const reg = regs.find((r) => r.id === (mineB ? b : a));
      ctx.globalAlpha = 0.7;
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = reg ? reg.color : BARRY.token('--accent');
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    }
    // the open step's anchors: lead as a filled mark, votes as rings
    const prop = open && sug.steps ? sug.steps[open] : null;
    for (const an of (prop && prop.anchors) || []) {
      const at = (row) => {
        const i = laneOfRow(row, chans);
        return i == null || i >= n ? null : (i + 0.5) * lane;
      };
      const y = at(an.lead.row);
      if (y != null) {
        ctx.fillStyle = BARRY.token('--accent');
        ctx.beginPath();
        ctx.moveTo(W - 1, y); ctx.lineTo(W - 8, y - 4); ctx.lineTo(W - 8, y + 4);
        ctx.closePath(); ctx.fill();
      }
      for (const v of an.votes || []) {
        const yy = at(v.row);
        if (yy == null) continue;
        ctx.strokeStyle = BARRY.token('--text-2');
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(W - 13, yy, 2.6, 0, Math.PI * 2); ctx.stroke();
      }
    }
    // a picked ICA check: the component's CSD, its sink, and the layer
    if (icaPick && open === '3' && ica && ica.components) {
      const comp = ica.components.find((x) => x.index === icaPick.component);
      const col = BARRY.token(kindTok(icaPick.kind));
      if (comp && comp.csd) {
        const idx = new Map((ica.channels || []).map((ch, k) => [ch, k]));
        const vals = chans.map((c) => {
          const k = idx.get(c.number);
          return k == null ? null : comp.csd[k];
        });
        const fin = vals.filter((x) => x != null);
        const lim = fin.length ? Math.max(...fin.map(Math.abs)) || 1 : 1;
        ctx.strokeStyle = col;
        ctx.lineWidth = 1.6;
        curve(ctx, vals.map((x, i) => (x == null ? null
          : [W / 2 + (x / lim) * (W / 2 - pad), (i + 0.5) * lane])));
      }
      const top = ghost && ghost.lines.find((l) => l.below === icaPick.region);
      const bot = ghost && ghost.lines.find((l) => l.above === icaPick.region);
      if (top && top.at != null) {
        const y0 = laneOfRow(top.at, chans) * lane;
        const y1 = (bot && bot.at != null ? laneOfRow(bot.at, chans) : n) * lane;
        const reg = (H.regions() || []).find((r) => r.id === icaPick.region);
        ctx.fillStyle = reg ? reg.color : col;
        ctx.fillRect(1, y0 + 1, 4, Math.max(2, y1 - y0 - 2));
      }
      if (icaPick.row != null) {
        const m = icaMark(icaPick, chans);
        if (m) {
          ctx.globalAlpha = 0.3;
          ctx.fillStyle = col;
          ctx.fillRect(0, m.a * lane, W, (m.b - m.a) * lane);
          ctx.globalAlpha = 1;
          if (m.edge != null) {
            const y = Math.round(m.edge * lane) + 0.5;
            ctx.setLineDash([5, 3]);
            ctx.strokeStyle = col;
            ctx.lineWidth = 2;
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
            ctx.setLineDash([]);
          }
        }
      }
    }
    // the proposal's lines, dashed by how sure they are
    if (ghost && ghost.step === open) {
      ctx.font = '9.5px system-ui, sans-serif';
      ctx.textBaseline = 'bottom';
      ctx.textAlign = 'right';
      for (const ln of ghost.lines) {
        const i = laneOfRow(ln.at, chans);
        if (i == null) continue;
        const y = Math.round(i * lane) + 0.5;
        const hot = drag && drag.line === ln;
        ctx.setLineDash(CONF_DASH[ln.confidence] || CONF_DASH.likely);
        ctx.strokeStyle = BARRY.token(hot ? '--text' : '--accent');
        ctx.lineWidth = hot ? 2.5 : 1.8;
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
        ctx.setLineDash([]);
        const txt = shortName(ln.below || ln.above);
        const tw = ctx.measureText(txt).width;
        ctx.fillStyle = 'rgba(0,0,0,0.6)';
        ctx.fillRect(W - 16 - tw - 4, y - 11, tw + 6, 11);
        ctx.fillStyle = BARRY.token('--accent');
        ctx.fillText(txt, W - 16, y);
      }
    }
  }

  /* A curve through points, some missing. Solid where neighbours are both
     there; across a missing channel (a bad one, usually) a faint dotted
     bridge, so a curve does not stop dead and start again further down
     looking like two curves (2026-10-12, "weird gap"). */
  function curve(ctx, pts) {
    let run = [];
    let lastEnd = null;
    const flush = () => {
      if (run.length) {
        if (lastEnd && run.length) {
          ctx.save();
          ctx.setLineDash([2, 3]);
          ctx.globalAlpha *= 0.6;
          ctx.beginPath();
          ctx.moveTo(lastEnd[0], lastEnd[1]);
          ctx.lineTo(run[0][0], run[0][1]);
          ctx.stroke();
          ctx.restore();
        }
        ctx.beginPath();
        ctx.moveTo(run[0][0], run[0][1]);
        for (let k = 1; k < run.length; k++) ctx.lineTo(run[k][0], run[k][1]);
        ctx.stroke();
        lastEnd = run[run.length - 1];
      }
      run = [];
    };
    for (const p of pts) {
      if (p) run.push(p);
      else flush();
    }
    flush();
  }

  function shortName(id) {
    if (SHORT[id]) return SHORT[id];
    const r = (H.regions() || []).find((x) => x.id === id);
    return r ? r.name.replace(/^CA1 |^DG /, '') : (id || 'below');
  }

  function stripRowAt(e) {
    const r = stripCanvas.getBoundingClientRect();
    const y = e.clientY - r.top;
    const n = H.channels().length || 1;
    return { y, lane: r.height / n, n };
  }

  function nearestLine(e) {
    const { y, lane } = stripRowAt(e);
    let best = null;
    if (ghost && ghost.step === open) {
      const chans = H.channels();
      for (const ln of ghost.lines) {
        const i = laneOfRow(ln.at, chans);
        if (i == null) continue;
        const d = Math.abs(i * lane - y);
        if (d <= 6 && (!best || d < best.d)) best = { d, kind: 'ghost', line: ln };
      }
    }
    if (best) return best;
    // an accepted boundary
    const chans = H.channels();
    const sh = sheet();
    const lab = (c) => (sh && sh.labels ? sh.labels[String(c.number)] : null);
    for (let i = 1; i < chans.length; i++) {
      if (lab(chans[i - 1]) === lab(chans[i])) continue;
      const d = Math.abs(i * lane - y);
      if (d <= 5 && (!best || d < best.d)) {
        best = { d, kind: 'label', at: i, above: lab(chans[i - 1]),
                 below: lab(chans[i]) };
      }
    }
    return best;
  }

  function stripHover(e) {
    if (drag || !stripCanvas) return;
    stripCanvas.style.cursor = nearestLine(e) ? 'ns-resize' : '';
  }

  function stripDown(e) {
    const hit = nearestLine(e);
    if (!hit) return;
    e.preventDefault();
    drag = hit;
    if (hit.kind === 'ghost') drag.line = hit.line;
    const move = (ev) => {
      const { y, lane, n } = stripRowAt(ev);
      const row = Math.max(0, Math.min(n, Math.round(y / lane)));
      if (drag.kind === 'ghost') {
        // Lanes on screen, rows of the whole probe in the proposal.
        const at = rowOfLane(row, H.channels());
        if (at != null && drag.line.at !== at) {
          drag.line.at = at;
          drawStrip();
          H.redraw();
        }
      } else {
        drag.to = row;
        drawStrip();
      }
    };
    const up = async () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
      const d = drag;
      drag = null;
      if (d.kind === 'ghost') {
        confirming = null;
        H.render();
        publish();
        return;
      }
      if (d.to == null || d.to === d.at) { drawStrip(); return; }
      /* Moving an accepted boundary relabels the channels it passes -- all of
         them, in the sheet's order, including any the traces are not
         drawing just now. Relabelling only the drawn ones would leave every
         hidden channel in between on the old side of the line. */
      const lanes = H.channels();
      const all = allChans().map((c) => c.number);
      const idx = (laneI) => (laneI >= lanes.length ? all.length
        : all.indexOf(lanes[laneI].number));
      const from = idx(d.at), to = idx(d.to);
      const map = {};
      if (from >= 0 && to >= 0) {
        if (to > from) for (let i = from; i < to; i++) map[all[i]] = d.above;
        else for (let i = to; i < from; i++) map[all[i]] = d.below;
      }
      await H.setLabels(map);
      drawStrip();
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  }

  /* ==================================================================
     On the traces and rasters: the ghost lines
     ================================================================== */
  function drawGhost(ctx, chans, x0, plotW, y0, lane) {
    if (!ghost || ghost.step !== open || !sug || !chans || !chans.length) return;
    ctx.save();
    for (const ln of ghost.lines) {
      const i = laneOfRow(ln.at, chans);
      if (i == null) continue;
      const y = Math.round(y0 + i * lane) + 0.5;
      ctx.setLineDash(CONF_DASH[ln.confidence] || CONF_DASH.likely);
      ctx.globalAlpha = 0.85;
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 3.5;
      ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + plotW, y); ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = BARRY.token('--accent');
      ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + plotW, y); ctx.stroke();
    }
    /* A picked ICA check: the channel its component sinks on, shaded edge
       to edge, and -- when that is outside the layer -- the boundary that
       would take it in, dashed, on the same channel edge any other line
       sits on. (It used to be a line through the middle of the channel,
       half way between two boundaries.) */
    if (icaPick && open === '3' && icaPick.row != null) {
      const m = icaMark(icaPick, chans);
      if (m) {
        const col = BARRY.token(kindTok(icaPick.kind));
        const ya = Math.round(y0 + m.a * lane), yb = Math.round(y0 + m.b * lane);
        ctx.setLineDash([]);
        ctx.globalAlpha = 0.22;
        ctx.fillStyle = col;
        ctx.fillRect(x0, ya, plotW, Math.max(1, yb - ya));
        ctx.globalAlpha = 1;
        ctx.font = '10px system-ui, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillStyle = col;
        if (m.edge != null) {
          const y = Math.round(y0 + m.edge * lane) + 0.5;
          ctx.setLineDash([6, 4]);
          ctx.strokeStyle = '#000';
          ctx.lineWidth = 3.5;
          ctx.globalAlpha = 0.8;
          ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + plotW, y); ctx.stroke();
          ctx.globalAlpha = 1;
          ctx.strokeStyle = col;
          ctx.lineWidth = 2;
          ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + plotW, y); ctx.stroke();
          ctx.setLineDash([]);
          ctx.textBaseline = m.edge === m.a ? 'bottom' : 'top';
          ctx.fillText('ICA: ' + layerShort(icaPick.region) + ' would '
                       + (m.edge === m.a ? 'start' : 'end') + ' here ('
                       + kindName(icaPick.kind) + ' sink, ' + chName(icaPick.row)
                       + ')', x0 + 6, m.edge === m.a ? y - 2 : y + 2);
        } else {
          ctx.textBaseline = 'bottom';
          ctx.fillText('ICA ' + kindName(icaPick.kind) + ' sink, '
                       + chName(icaPick.row), x0 + 6, ya - 2);
        }
      }
    }
    ctx.restore();
  }

  /* A line moved from the evidence window ("Move" beside what the phase
     map says). The command comes over /api/link, read by xplore's poll;
     only one newer than this visit, and only once. */
  function fromLink(channels) {
    if (!H || !channels) return;
    const slot = channels['strata-cmd:' + H.gid];
    const v = slot && slot.value;
    if (!v || !v.at || v.at <= cmdSeen) return;
    cmdSeen = v.at;
    if (v.at < enteredAt - 2000) return;
    if (open !== '3' || !ghost || ghost.step !== '3') {
      toast('Open Step 3 to move that line.', 'warn', 5000);
      return;
    }
    const ln = ghost.lines.find((l) => (v.id && l.id === v.id)
      || (l.above === v.above && l.below === v.below));
    if (!ln || v.to == null) return;
    moveGhost(ln, v.to);
  }

  /* Move a proposed line, from a Move button here or in the evidence
     window, and say so. */
  function moveGhost(ln, to) {
    const was = ln.at;
    ln.at = Math.max(0, Math.min(sug.channels.length, Number(to)));
    confirming = null;
    H.render();
    drawStrip();
    H.redraw();
    publish();
    const nm = (layerShort(ln.above) || '') + ' | ' + (layerShort(ln.below) || '');
    toast('Moved ' + nm + ' from above ' + chName(was) + ' to above '
          + chName(ln.at) + '. It is a proposal until you Accept.', 'ok', 6000);
  }

  /* Where a picked ICA check goes, in lanes: the sink channel's lane
     [a, b), and the boundary it would move -- the layer's top edge pulled
     up to the sink channel's top, or its bottom pushed down to the sink
     channel's bottom. Both are lane edges, found the way every other line
     is (laneOfRow), so they land exactly on them. Null when the sink
     channel is not drawn. */
  function icaMark(c, chans) {
    const a = laneOfRow(c.row, chans);
    const b = laneOfRow(c.row + 1, chans);
    if (a == null || b == null || b <= a) return null;
    const edge = c.agree || !c.off ? null : c.off < 0 ? a : b;
    return { a, b, edge };
  }

  /* ==================================================================
     The evidence window
     ================================================================== */
  const linkChannel = () => 'strata-steps:' + (H ? H.gid : '');

  /* Coalesced: dragging a line publishes on every row it crosses, and only
     the newest picture is worth sending. */
  let sending = false;
  let pending = null;

  function publish(force) {
    if (!H && !(force && force.off)) return;
    rev += 1;
    const value = (force && force.off) ? { off: true } : {
      gid: H.gid, path: H.path(), step: open, rev,
      channels: allChans().map((c) => c.number),
      labels: (sheet() || {}).labels || {},
      regions: H.regions(),
      lines: ghost && ghost.step === open ? ghost.lines : [],
      affected: (() => { const a = affected(); return a ? Array.from(a) : null; })(),
      proposed: (() => { const m = proposedLabels(); return m ? Object.fromEntries(m) : null; })(),
      ica_pick: icaPick ? icaPick.component : null,
      ica_ready: !!(sug && sug.ica_ready),
      focus: focusRegions() ? Array.from(focusRegions()) : null,
      overrides,
      states_n: walk().length,
      theme: (BARRY.state || {}).theme,
    };
    send({ channel: linkChannel(), origin: 'strata-main', value });
  }

  async function send(msg) {
    if (sending) { pending = msg; return; }
    sending = true;
    try {
      await apiPost('/api/link', msg);
    } catch (e) { /* best effort, like the rest of the linking */
    } finally {
      sending = false;
      const next = pending;
      pending = null;
      if (next) send(next);
    }
  }

  /* The aid window is StrataScope's own (strata.js opens it on the way in);
     this brings it forward, or opens it again if it was closed. */
  function openAids() {
    if (!H) return;
    if (!H.focusAids()) H.openAids();
    setTimeout(publish, 600);
  }

  return {
    enter, leave, section, drawer, railStrip, layout, drawStrip, drawGhost,
    stripWidth, publish, openAids,
    // strata.js tells this when the sheet changed under it
    sheetChanged: () => { drawStrip(); publish(); },
    get open() { return open; },
    get active() { return !!H; },
    // For web/_dev/stratasteps.html
    _state: () => ({ status, open, sug, ghost, overrides, guide, checks,
                     drag: drag ? { kind: drag.kind, at: drag.line ? drag.line.at : drag.at } : null,
                     paint }),
    _openStep: openStep,
    proposedLabels,
    affected,
    focusRegions,
    _labelsFromLines: labelsFromLines,
    _icaMark: (c) => (H ? icaMark(c, H.channels()) : null),
    _icaCompare: (c) => icaCompare(c),
    fromLink,
    _jobs: () => ({ jobId, jobKind, jobsNow }),
  };
})();
