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

   LOCK IS THIS PANEL TOO (2026-10-22)
   "The set up should be very similar to Braces ... very carbon copy." Lock,
   step 3 of The Confluence, used to be Eye's three-measure panel pointed at
   a pooled set; it is now this one, built twice from `makeBraces(cfg)` --
   the same picker, Many, Alignments list, proposal, bench and trace review
   -- so a fix to one reaches both (constitution §6c). What differs is in
   `cfg`: the kind of set, the words, and Lock's one addition, keeping the
   stamps Braces already placed exactly where they are (`pin`).
   ========================================================================== */
'use strict';

/* How far a stamp may move, either way, unless somebody changes it: the
   baseline for Braces and Lock alike (100 until 2026-10-23). */
const WINDOW_MS = 200;

function makeBraces(cfg) {
  /* The words that differ, said once. */
  const W = cfg.words;
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
    // ±200 ms by default (2026-10-23: "make the baseline window 200").
    window_ms: WINDOW_MS,
    estimator: 'sd',
    // Lock: keep the stamps Braces placed where they are. Ticked by itself
    // whenever the set has any (`pinFor`); null until somebody changes it.
    // Lock: the origin groups held this run ('incisor', 'both',
    // 'doppler'); null until somebody changes it, and then `holdFor` says.
    hold: null,
    // Lock: which band the stamps are aligned through, 'ds' or 'ied'.
    band: 'ds',
  };

  let cands = null;     // sets that could be aligned
  /* Lock: pooled sets nobody has sorted in Panning yet. Not offered --
     Lock lines up Panning's results, never Junction's raw pool -- but
     counted, so the list says why they are not in it. */
  let unsorted = 0;

  /* The bulk queue.

     `pick` is entry id -> the version ref to read from, so changing one
     before the run starts is one assignment. `state` is entry id ->
     {state, msg, set_id} and is the only thing the table's right-hand
     column reads, so a row that failed says why for as long as the panel
     is open. */
  const bulk = {
    on: false, pick: {}, want: {},
    // Lock: entry id -> the origin groups held for that set, once changed.
    hold: {},
    // Read again even where these settings were run before.
    force: false,
    // Every set to the cluster, even the ones this computer has. Null
    // until somebody presses the chip: on wherever there is a cluster
    // (2026-10-27: "a send to VACC chip, on by default").
    allVacc: null,
    find: '',           // the search over the list
    rev: 0,             // bumped when what the rows say has changed
    rows: 0,            // bumped when one row was drawn again in place
  };
  /* The batches the server is running or has just run, from
     `/api/braces/inflight` -- the server's, not this page's, so leaving the
     view or reloading finds them again (2026-10-14). */
  let flights = [];
  let flightTimer = null;
  let flightsAsked = false;
  const flightSeen = new Set();     // "<job>:<set>" landings already counted
  const flightAnnounced = new Set();
  const flightLive = new Set();     // batches seen running from here
  let dismissed = new Set();
  try {
    dismissed = new Set(JSON.parse(localStorage.getItem(
      'barry.' + cfg.tool + '.dismissed') || '[]'));
  } catch (e) { /* a remembered dismissal is a convenience */ }
  let recentRev = 0;                // the Alignments list, read again
  let plan = null;      // what a run would read
  /* The alignment a run opened instead of reading again, so its page can
     say so and offer to read it again (2026-10-14). */
  let reused = null;
  /* The Alignments list: every one, grouped by set, searchable. */
  let allSets = null;
  const recentQ = { text: '', show: 'all' };
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
    warmRegistry();
    warmKnows();
    if (cfg.pin) {
      // What each set was last run with (its groups), and the bands' words.
      if (allSets === null) loadAllSets();
      if (!presets) loadPresets().then(() => { if (!job) render(); });
    }
    if (!cands) await loadCandidates();
    else freshen();
  }

  /* THE LIST, READ AGAIN ON EVERY VISIT (2026-10-30: "results banked in
     Panning do not show up in Lock unless a github sync is done ... even
     when Panning was banked on the same PC"). The sets were read once per
     page and kept, so anything banked after Lock was first opened -- here
     or anywhere -- stayed out of it until Jarvis was restarted, which a
     push happened to do. Asked in the background; the panel is drawn again
     only when the answer differs, and the alignments list with it. */
  let freshening = false;
  async function freshen() {
    if (freshening || job) return;
    freshening = true;
    let got = null;
    try {
      got = await api('/api/braces/candidates?type=' + cfg.type,
                      { priority: 'background' });
    } catch (e) { /* the list on screen stands */ }
    freshening = false;
    if (cfg.pin) loadAllSets();
    if (!got) return;
    const all = got.sets || [];
    const next = cfg.sorted ? all.filter(cfg.sorted) : all;
    const sig = (l) => JSON.stringify((l || []).map((c) => [
      c.id, c.current_name, (c.versions || []).length, c.n_good]));
    if (sig(next) === sig(cands) && all.length - next.length === unsorted) {
      return;
    }
    cands = next;
    unsorted = all.length - next.length;
    bulk.rev += 1;
    // Not over a proposal or a read: nothing on those screens is the list.
    if (set_ || job || bench || view) return;
    if (q.entry && !cands.some((c) => c.id === q.entry)) {
      q.entry = cands.length ? (cands.find((c) => c.gid) || cands[0]).id : null;
      q.from_version = null; q.channels = null; q.hold = null;
      render();
      if (q.entry) refreshPlan();
      return;
    }
    render();
  }

  /* What the cluster can read -- which decides the rows Many can send to
     the VACC. Cached for minutes in vacc.js, so usually already here. */
  function warmKnows() {
    if (!BARRY.vacc || !BARRY.vacc.loadKnows) return;
    BARRY.vacc.loadKnows().then(() => {
      bulk.rev += 1;
      if (shownPage === 'many') render();
    }).catch(() => { /* the drive answer stands */ });
  }

  /* The registry, read rather than hoped for.

     Three things on this panel are answered out of it and none of them can
     be answered without it: which contacts a recording has marked bad, which
     recordings this machine can open, and what to call them in the picker.
     ToolKit holds one sixty-second cache of it for every tool, and
     `registryRows` is a getter over that cache -- not a read. Whoever gets
     there first pays for it, and until somebody does, the getter returns an
     empty list.

     Which is indistinguishable, from here, from a registry that knows
     nothing. Braces was reached straight from the bundle, so usually nobody
     had been there first: the bulk table said "none bad" against every set
     -- including forty-six whose recordings have channels marked, which is
     the whole cohort -- and "46 can be read here" about a list where 368 of
     588 are actually mounted. Both read as facts. Neither was one.

     Not awaited: the read takes seconds on a network share and nothing on
     the first paint needs it, so the panel draws now and the columns that
     depend on it fill in when it lands. */
  async function warmRegistry() {
    const tk = BARRY.views.toolkit;
    if (!tk || !tk.loadRegistry || !tk.registryRows) return;
    if (tk.registryRows().length) return;        // somebody already paid
    try {
      await tk.loadRegistry();
    } catch (e) {
      // Left alone deliberately. Every reader of these rows already copes
      // with not having them -- a bad-channel chip that says "none bad" is
      // wrong but harmless, and a toast about a background read nobody asked
      // for is a worse answer than a column that fills in late or not at all.
      return;
    }
    /* Not while a read is going, nor over an open proposal -- none of what
       just arrived is on that screen, so rebuilding it would cost a scroll
       position and buy nothing. In Many the rows are rebuilt (`bulk.rev`):
       where each set can be aligned from is read off the registry. */
    bulk.rev += 1;
    if (!job && !set_) render();
  }

  async function loadCandidates() {
    try {
      const got = await api('/api/braces/candidates?type=' + cfg.type);
      const all = got.sets || [];
      /* Lock takes Panning's results and nothing else (2026-10-22: "direct
         input from Junction makes no sense"). A pool nobody has sorted is
         a detector list, not a set of spikes. */
      cands = cfg.sorted ? all.filter(cfg.sorted) : all;
      unsorted = all.length - cands.length;
    } catch (e) {
      toast('Could not read the event bank: ' + e.message, 'err', 8000);
      cands = [];
    }
    // Opened on a set the picker can show: one on a recording. A set with
    // no registry id has no recording tile to sit under.
    if ((!q.entry || !cands.some((c) => c.id === q.entry)) && cands.length) {
      q.entry = (cands.find((c) => c.gid) || cands[0]).id;
      q.from_version = null;
      q.channels = null;
      q.hold = null;
    }
    render();
    if (q.entry) refreshPlan();
  }

  async function refreshPlan() {
    if (!q.entry) return;
    /* The same set read again (another version, another band): the plan on
       screen stays, dimmed, until the new one lands -- blanking it to
       "Working it out" took the channel grid and the button with it, and
       put them back a second later. A different set starts clean. */
    const same = plan && plan.ok && plan.entry && plan.entry.id === q.entry;
    if (same) planBusy = true; else plan = null;
    planRev += 1;
    render();
    const asked = q.entry;
    let got;
    try {
      got = await apiPost('/api/braces/plan', {
        entry_id: q.entry,
        from_version: q.from_version,
        window_ms: q.window_ms,
        estimator: q.estimator,
        band_kind: cfg.bands ? q.band : undefined,
      });
    } catch (e) {
      got = { ok: false, error: e.message };
    }
    if (q.entry !== asked) return;      // another set was picked meanwhile
    plan = got;
    planBusy = false;
    planRev += 1;
    render();
  }

  /* ==================================================================
     Running
     ================================================================== */
  async function run(force) {
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
        hold: cfg.pin ? holdNow() : undefined,
        band_kind: cfg.bands ? q.band : undefined,
        force: !!force,
      });
      // The last setting it was run on, remembered (2026-10-26).
      if (cfg.pin) rememberHold(holdNow());
    } catch (e) {
      toast(e.message, 'err', 9000);
      return;
    }
    /* Asked before, with exactly these settings: the alignment already
       made is the answer, and nothing is read again. */
    if (started.existing) {
      reused = { set_id: started.existing.set_id,
                 line: setLine(started.existing) };
      await openSet(started.existing.set_id);
      toast('Aligned before with exactly these settings (' + reused.line
            + '), so that alignment is open and nothing was read again.',
            'ok', 9000);
      return;
    }
    reused = null;
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
    // A recording only the cluster has is aligned there (`_braces_vacc_run`).
    'vacc stage': 'Sending it to the cluster',
    'vacc queue': 'Waiting for VACC, then aligning there',
    'vacc fetch': 'Bringing the proposal back',
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
    'vacc queue':
      'This recording is not on this computer, so it is aligned on the '
      + 'cluster by the same rule. Waiting in the queue is not an error; '
      + 'the depth and the stretches are counted once it starts there.',
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
    if (!mine()) return;
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
    readOverlaps(set_.overlaps);
    /* Opening on the pass that wants an answer. An overlap only appears
       once somebody has been through the flags, so it comes second -- but
       it comes before "All", because a set that cannot be banked should not
       open on a list that does not say so. */
    filter = (set_.counts || {}).waiting ? 'flag'
      : ((set_.counts || {}).overlap ? 'overlap' : 'all');
    bench = null;
    render();
  }

  /* ==================================================================
     Deciding
     ================================================================== */
  /* An accepted proposal is the record of the version it became, and the
     server refuses any call on it. Autobank accepts it the moment the last
     flagged stamp has its call, so the next key pressed in the same breath
     was a red error, pressed again and again (2026-10-27, four times in
     twenty seconds on Strawbarry, twice elsewhere). Said here instead, once,
     as what it is. */
  let saidAccepted = null;
  function accepted() {
    const c = set_ && set_.set && set_.set.committed;
    if (!c) return false;
    if (saidAccepted !== set_.set.set_id) {
      saidAccepted = set_.set.set_id;
      toast('Already banked as version ' + c.version + ', so this pass is '
            + 'the record of it and is not changed. To change a stamp, run '
            + cfg.name + ' again on that version.', null, 9000);
    }
    return true;
  }

  async function decide(n, call, t) {
    if (!set_ || accepted()) return;
    try {
      /* A null call means "forget what was said about this row", and the
         route only reads `call` when it is not null -- so undoing has to go
         through `calls`, where an explicit null is the documented way to
         drop one. Sent as a single-row map rather than a second route. */
      const body = (call == null)
        ? { calls: { [String(n)]: null } }
        : { row: n, call: call, t: t,
            // A held stamp only gets here once somebody overrode the hold.
            override: isLocked(n) && overridden(n) ? true : undefined };
      const got = await apiPost(
        '/api/braces/set/' + encodeURIComponent(set_.set.set_id) + '/decide',
        body);
      set_.counts = got.counts;
      set_.would_move = got.would_move;
      set_.set.calls = got.calls;
      // A move onto a time its neighbour already holds flags both of them,
      // and moving either off unflags both -- so this is re-read on every
      // decision rather than only when the set is opened.
      set_.overlaps = got.overlaps;
      readOverlaps(got.overlaps);
    } catch (e) {
      toast(e.message, 'err', 8000);
    }
  }

  const callFor = (n) => ((set_.set.calls || {})[String(n)] || {}).call || null;

  /* THE OVERLAP FLAG, by row.

     Every other flag is measured once and written into the row. This one is
     a fact about the review -- two stamps sent to the same time, which the
     bank will not write -- so the server works it out from the calls and
     sends it with the set and with every decision. See `bracesset.OVERLAP`.

     Held as a lookup rather than walked per row: the table draws four
     hundred rows and the bench repaints on every keystroke. */
  let overlapAt = new Map();
  function readOverlaps(list) {
    overlapAt = new Map();
    (list || []).forEach((g) => (g.rows || []).forEach(
      (i) => overlapAt.set(i, g)));
  }
  const overlapping = (i) => overlapAt.get(i) || null;
  /* The OTHER stamp in the pair, which is the one somebody has to see for
     the flag to mean anything. */
  function overlapMate(i) {
    const g = overlapping(i);
    if (!g) return null;
    const other = (g.rows || []).filter((x) => x !== i);
    return other.length ? other[0] : null;
  }

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
      else if (filter === 'same' && r.same && !r.locked) out.push([r, n]);
      else if (filter === 'locked' && r.locked) out.push([r, n]);
      else if (filter === 'nopeak' && r.flag === 'no_peak') out.push([r, n]);
      else if (filter === 'overlap' && overlapping(n)) out.push([r, n]);
    });
    return out;
  }

  /* ==================================================================
     The page
     ================================================================== */
  /* THE PAGE, IN PARTS THAT ARE KEPT (2026-10-14).

     It was emptied and built again on every change, so ticking a set
     halfway down the many-sets table threw the table back to its top: the
     table is a scroll box of its own, and the new one started at 0. Many
     is now built the way Doppler's is -- each part kept as a node of its
     own and rebuilt only when what it shows has changed (`BARRY.ui.sections`)
     -- so a tick changes its row and the counts and nothing else. One set
     and a proposal are still drawn whole, with the page's scroll held where
     it was across the redraw. */
  let renders = 0;
  let shownPage = null;
  /* Whether this instance's tool is the one on screen. Braces and Lock
     share #tkResult, so a poll or a late answer from the one not shown
     must not draw over the other (2026-10-22). */
  function mine() {
    const tk = BARRY.views.toolkit;
    return !tk || typeof tk.tool !== 'function' || tk.tool() === cfg.tool;
  }

  function render() {
    const h = host();
    if (!h || !mine()) return;
    const page = set_ ? 'set'
      : (bulk.on && cands && cands.length) ? 'many' : 'one';
    const back = (page === shownPage && page !== 'set')
      ? BARRY.keepScroll(h) : null;
    shownPage = page;
    if (page === 'many') {
      BARRY.ui.sections(h, manyParts());
    } else if (page === 'one') {
      BARRY.ui.sections(h, oneParts());
    } else {
      renders += 1;
      BARRY.ui.sections(h, [{ key: page, sig: renders, enter: false,
        build: proposalView }]);
    }
    if (back) back();
    if (!flightsAsked) { flightsAsked = true; loadFlights(); }
  }

  /* ONE SET, IN PARTS THAT ARE KEPT (2026-10-27: "the entire settings panel
     is glitchy for one and many"). Every press rebuilt the whole page -- the
     picker, the plan, both lists of alignments (each fetched again) and the
     settings -- so a filter press blanked the plan, threw the channel grid
     away and back, and reloaded two lists nobody had touched. Now each part
     is rebuilt only when what it shows has changed, as Many's are. */
  let planRev = 0;
  let planBusy = false;
  const holdSig = () => (cfg.pin ? holdNow().join(',') : '');
  function oneParts() {
    if (!cands || !cands.length) {
      return [{ key: 'one-empty', enter: false,
                sig: [cands ? cands.length : -1, unsorted],
                build: pickView }];
    }
    const regN = (BARRY.views.toolkit && BARRY.views.toolkit.registryRows)
      ? BARRY.views.toolkit.registryRows().length : 0;
    return [
      { key: 'otop', enter: false,
        sig: ['otop', flights.filter(flightRunning).length],
        build: () => el('div', { class: 'br-wrap' }, [stepHead(), modeCard()]) },
      { key: 'pick', enter: false,
        sig: [q.gid, q.entry, q.from_version, cands.length, unsorted, regN],
        build: pickCard },
      { key: 'plan', enter: false,
        sig: [planRev, planBusy, q.from_version, holdSig(), q.band],
        build: planCard },
      q.entry ? { key: 'aligns', enter: false, sig: [q.entry, recentRev],
                  build: entryAlignments } : null,
      { key: 'settings', enter: false,
        sig: [q.entry, q.measure, q.window_ms, q.band, holdSig(), planRev,
              (q.channels || []).join(','), !!presets],
        build: settingsCard },
      { key: 'go', enter: false,
        sig: [q.entry, job ? job.id : null, planRev, planBusy, holdSig(),
              q.band],
        build: goCard },
      { key: 'recent', enter: false, sig: ['recent', recentRev],
        build: recentSets },
    ];
  }

  /* ---------- 1. what to align ---------- */
  function pickView() {
    const box = el('div', { class: 'br-wrap' });

    box.appendChild(stepHead());

    if (!cands) {
      box.appendChild(el('div', { class: 'card', text: 'Reading the bank…' }));
      return box;
    }
    if (!cands.length) {
      box.appendChild(el('div', { class: 'card br-empty' }, [
        el('strong', { text: 'Nothing to align yet.' }),
        el('p', { class: 'hint', text: W.empty }),
        unsorted ? el('p', { class: 'hint', text: unsortedWords() }) : null,
      ].filter(Boolean)));
      return box;
    }

    box.appendChild(modeCard());

    // One and Many are drawn by `oneParts` and `manyParts`; this is the
    // bank arriving, or there being nothing in it.
    return box;
  }

  function stepHead() {
    return BARRY.ui.stepHeader({
      title: cfg.name,
      step: BARRY.ui.stepOf(cfg.tool) || cfg.step,
      blurb: W.blurb,
    });
  }

  /* Lock's sentence for the pools it leaves out. */
  function unsortedWords() {
    return unsorted + ' pooled set' + (unsorted === 1 ? ' has' : 's have')
      + ' not been sorted in Panning yet, so ' + (unsorted === 1 ? 'it is'
      : 'they are') + ' not offered. Lock lines up Panning’s results — '
      + 'Junction’s raw pool still has the garbage in it.';
  }

  /* One set, or many.

     Two genuinely different jobs rather than two views of one. Choosing
     a set, checking what it would read and running it is a thing you do
     while thinking; aligning everything curated is a thing you set off
     and come back to. The switch is here rather than being a separate
     tool because the sets, the versions and the settings are the same
     in both. */
  function modeCard() {
    const running = flights.filter(flightRunning).length;
    return el('div', { class: 'card br-mode' }, [
      /* How many, through the run bar (constitution §6d): one component
         for the choice every tool makes, rather than a seg each tool drew
         for itself. Only local modes, so the bar shows How many alone. */
      BARRY.ui.runBar({
        modes: { local: ['one', 'many'] }, where: 'local',
        count: bulk.on ? 'many' : 'one',
        onChange: (w, c) => { bulk.on = c === 'many'; render(); },
      }),
      el('span', { class: 'br-hint', text: bulk.on
        ? 'Sends every set you tick as one batch: the ones on this computer '
          + 'are aligned here, the ones only the VACC has are aligned there, '
          + 'side by side. Each lands as a proposal — nothing is banked.'
        : 'Pick a recording, check what it would read, then run it.' }),
      /* A batch going while one set is on screen is still worth knowing
         about, and one click from its progress. */
      (!bulk.on && running) ? el('button', { class: 'btn ghost sm br-mode-go',
        text: 'A batch is going — show it',
        onclick: () => { bulk.on = true; render(); } }) : null,
    ].filter(Boolean));
  }

  function pickCard() {
    /* Which recording, then which of its banked entries.

       Two questions in that order, because the first narrows the second
       and because it is the order somebody already thinks in: you arrive
       with a recording in mind, not with the name of a banked entry. The
       version comes third: by recording, not by set (2026-10-22). It was a
       recording picker over a list of radio buttons -- "looks like an HTML
       website from 1997" -- and the version was further down, in the plan.
       Now it is one rail of three tiles, each answered in turn: which
       recording (type to find it), which of its sets (a menu of cards, each
       saying what is in it, whether it was aligned before and -- in Lock --
       whether Braces has already placed its dentate spikes), and which
       version of that set's stamps (the version tree, as a pop-up).

       Only recordings something is banked against. The registry holds
       every recording this machine has ever opened and this tool can do
       nothing with the ones that have no curated set, so offering all of
       them means most picks land on "nothing here", which reads as the
       tool being broken rather than as the recording being the wrong one.
       The registry row is used where there is one, because it knows the
       date and whether the recording can be read from here; where there is
       not -- an entry banked from a recording this machine has never
       opened -- the entry itself supplies enough to pick by. */
    const card = el('div', { class: 'card br-pick', 'data-tool': cfg.tool });
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
    // Natural order (2026-10-20): m1, m3, m5, m12.
    rows.sort((x, y) => BARRY.ui.natCompare(x.label || '', y.label || ''));

    // Opened on something workable rather than on nothing: the recording
    // of whatever is already chosen, else the first one that has entries.
    // The chosen set decides the recording, so the two never disagree.
    const chosenSet = cands.find((c) => c.id === q.entry);
    if (chosenSet && chosenSet.gid) q.gid = chosenSet.gid;
    else if (!q.gid || !seen.has(q.gid)) q.gid = (rows[0] || {}).gid || null;
    const mine = cands.filter((c) => c.gid === q.gid);
    const cur = mine.find((c) => c.id === q.entry) || null;

    card.appendChild(el('div', { class: 'section-label',
                                 text: 'What to line up' }));
    const rail = el('div', { class: 'br-rail' });
    rail.appendChild(railTile(1, 'Recording', !!q.gid, BARRY.pickSession({
      rows,
      value: q.gid,
      placeholder: 'Which recording? Type a mouse, session or date…',
      onpick: (r) => {
        if (r.gid === q.gid) return;
        q.gid = r.gid;
        // A different recording means a different set: its first one, so
        // the next two tiles are already answered and only need checking.
        const first = cands.find((c) => c.gid === r.gid);
        chooseSet(first ? first.id : null);
      },
    })));
    rail.appendChild(railTile(2, 'Set', !!cur, setButton(mine, cur)));
    rail.appendChild(railTile(3, 'Version', !!cur,
      cur ? versionPick(cur)
          : el('span', { class: 'br-rail-none', text: 'after the set' })));
    card.appendChild(rail);

    if (!mine.length) {
      card.appendChild(el('p', { class: 'confirm-msg', text: W.noneHere }));
    }
    if (unsorted) {
      card.appendChild(el('p', { class: 'hint quiet', text: unsortedWords() }));
    }
    if (cur && cur.aligned) {
      card.appendChild(el('p', { class: 'hint br-warn', text:
        'This set has already been aligned, as version '
        + cur.aligned.version
        + (cur.aligned.channel != null ? ' on CSC' + cur.aligned.channel : '')
        + '. Running it again proposes a fresh alignment on top of that '
        + 'one; it does not undo it.' }));
    }
    return card;
  }

  /* Settings, for the set on screen. */
  function settingsCard() {
    const cur = (cands || []).find((c) => c.id === q.entry) || null;
    const set = el('div', { class: 'card br-settings' });
    set.appendChild(el('div', { class: 'section-label',
                                text: 'Settings' }));
    /* Lock's first setting, above the rest: which origin groups it lines
       up, and which it holds where they are (2026-10-26). */
    if (cfg.pin) set.appendChild(originCard(cur));
    set.appendChild(settingsFields(false));
    if (plan && plan.ok) set.appendChild(channelPicker());
    set.appendChild(el('p', { class: 'hint', text: W.measureWhy(q.measure)
      + 'There is no channel to pick. ' + W.acrossShank
      + ' so the magnitudes are averaged over '
      + 'every ticked channel into one trace, and the stamp goes to the '
      + 'highest point of THAT inside the window. One noisy wire cannot '
      + 'carry it and a dead one cannot sink it — and nothing is '
      + 'thresholded, because a peak is already the largest thing within '
      + 'its window.' }));
    return set;
  }

  /* Go. */
  function goCard() {
    const cur = (cands || []).find((c) => c.id === q.entry) || null;
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
      // Lock, with every spike in a held group: nothing to move.
      const held = cfg.pin && heldAllOf(cur, holdNow());
      const ready = !!(plan && plan.ok) && !held && !planBusy;
      go.appendChild(el('button', {
        class: 'btn', text: 'Line them up',
        disabled: ready ? null : 'disabled',
        title: held ? 'Every spike in this set is in a group being held, '
            + 'so there is nothing left to move.'
          : ready ? 'If this set has been aligned with exactly these '
          + 'settings before, that alignment opens instead of the recording '
          + 'being read again.' : 'This set cannot be read here',
        onclick: () => run(false),
      }));
      if (held) {
        go.appendChild(el('span', { class: 'br-hint', text: 'Every spike '
          + 'here is in a group being held, so there is nothing for Lock to '
          + 'move. Tick a group above to line it up.' }));
      }
    }
    return go;
  }

  /* ---- the picker's rail (2026-10-22) ----------------------------------

     Three tiles in a row, numbered, each lit once it is answered, joined by
     a line that fills as they are. Not a form: a path through three
     questions, the way the steps of a bundle are drawn. */
  function railTile(n, label, done, control) {
    return el('div', { class: 'br-tile' + (done ? ' done' : ''),
                       style: '--i:' + (n - 1) }, [
      el('div', { class: 'br-tile-head' }, [
        el('span', { class: 'br-tile-n', text: String(n) }),
        el('span', { class: 'br-tile-label', text: label }),
      ]),
      el('div', { class: 'br-tile-body' }, [control]),
    ]);
  }

  /* A different set: everything chosen about the last one goes with it. */
  function chooseSet(id) {
    q.entry = id;
    q.channels = null;
    q.from_version = null;
    q.hold = null;
    plan = null;
    if (id) refreshPlan(); else render();
  }

  /* The padlock, with a pair of brackets on a wire across it: Braces' work,
     locked. Open when it is not. */
  const LOCK_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true">'
    + '<path class="lk-sh" d="M7.6 10.4V7.6a4.4 4.4 0 0 1 8.8 0v2.8"/>'
    + '<rect class="lk-bd" x="4" y="10.2" width="16" height="11" rx="2.6"/>'
    + '<path class="lk-wr" d="M5.6 15.7h12.8"/>'
    + '<rect class="lk-bk" x="7.6" y="13.7" width="3.2" height="4" rx=".7"/>'
    + '<rect class="lk-bk" x="13.2" y="13.7" width="3.2" height="4" rx=".7"/>'
    + '</svg>';
  const UNLOCK_SVG = LOCK_SVG.replace('M7.6 10.4V7.6a4.4 4.4 0 0 1 8.8 0v2.8',
                                      'M7.6 10.4V7.6a4.4 4.4 0 0 1 8.6-1.3');

  /* How many of a set's spikes Braces already placed (Lock). */
  const bracedN = (c) => ((c && c.braced && c.braced.n) || 0);

  /* LOCK'S THREE GROUPS (2026-10-26). A pooled spike was found by Incisor
     alone, by both detectors within the merge window, or by Doppler alone,
     and Lock lines up the groups ticked and holds the rest where they are
     -- "put in options to not move one or two of those three groups, and
     that sidesteps the issue of knowing if Braces was run". */
  const GROUPS = [['incisor', 'Incisor only'], ['both', 'Merged'],
                  ['doppler', 'Doppler only']];
  const HOLD_KEY = 'lock_hold';
  const groupName = (g) => (GROUPS.find((x) => x[0] === g) || [g, g])[1];
  const cleanHold = (v) => (Array.isArray(v) ? GROUPS.map((x) => x[0])
    .filter((g) => v.indexOf(g) >= 0) : null);

  /* What a set holds when nobody has said: what it was last run with, else
     the last setting Lock was run on anywhere, else nothing -- every group
     lined up ("have all, and then remember the last setting"). */
  function holdFor(c) {
    if (!cfg.pin || !c) return [];
    const had = (allSets || []).find((x) => x.entry_id === c.id);
    const rq = had && (had.params || {}).request;
    if (rq) return cleanHold(rq.hold) || [];
    let last = null;
    try { last = cleanHold(BARRY.prefs.get(HOLD_KEY, null)); } catch (e) { /* none */ }
    return last || [];
  }

  /* The one set on screen. */
  function holdNow() {
    if (!cfg.pin) return [];
    if (q.hold) return q.hold;
    return holdFor((cands || []).find((x) => x.id === q.entry));
  }

  function rememberHold(h) {
    try { BARRY.prefs.set(HOLD_KEY, cleanHold(h) || []); } catch (e) { /* session */ }
  }

  /* How many spikes each group holds: the plan's (the version picked)
     where there is one, else the set's own. */
  const originsOf = (c) => ((c && c.id === q.entry && plan && plan.ok
                             && plan.origins) || (c && c.origins) || {});

  /* Every spike in a held group: nothing for Lock to move. */
  function heldAllOf(c, hold) {
    if (!c || !hold || !hold.length) return false;
    const o = originsOf(c);
    const total = GROUPS.reduce((a, [g]) => a + (o[g] || 0), 0);
    const held = hold.reduce((a, g) => a + (o[g] || 0), 0);
    return total > 0 && held >= total;
  }

  // Kept for the harness and the older callers: whether anything is held.
  function pinOn() { return holdNow().length > 0; }

  /* "Has Braces been run on this one?", on the set itself. */
  function bracesChip(c) {
    const b = c.braced || {};
    const n = bracedN(c);
    return el('span', {
      class: 'br-set-tag br-set-braces' + (n ? ' on' : ''),
      title: n ? n + ' of these spikes are Incisor stamps Braces already '
                 + 'put on their peaks' + (b.ds_version != null
                   ? ' (v' + b.ds_version + ' of ' + (b.ds_name || 'the '
                     + 'dentate-spike set') + ')' : '')
                 + '. Lock keeps them where they are unless you say not to.'
        : b.why ? b.why
        : b.ds_aligned ? 'The dentate spikes were aligned in Braces, but none '
                         + 'of this set’s spikes sits on one of those stamps.'
        : 'Braces had not been run on the dentate spikes this pool was made '
          + 'from.',
    }, [
      el('span', { class: 'br-lock-ico', html: n ? LOCK_SVG : UNLOCK_SVG }),
      el('span', { text: n ? 'Braces ✓ ' + n : 'no Braces' }),
    ]);
  }

  /* One set, as the button and the menu both show it. */
  function setFace(c) {
    const n = goodOf(c);
    return [
      el('span', { class: 'br-set-name', text: c.name || c.id }),
      el('span', { class: 'br-set-chips' }, [
        el('span', { class: 'br-set-n',
                     text: n + ' ' + (n === 1 ? W.one : W.many) + ' of '
                           + c.n }),
        el('span', { class: 'br-set-tag', text: vName(c) }),
        cfg.pin ? bracesChip(c) : null,
        c.aligned ? el('span', { class: 'br-set-tag warn',
                                 text: 'aligned before' }) : null,
      ].filter(Boolean)),
    ];
  }

  function setButton(mine, cur) {
    if (!mine.length) {
      return el('span', { class: 'br-rail-none',
                          text: 'nothing banked on this recording' });
    }
    const btn = el('button', {
      type: 'button', class: 'br-setbtn' + (cur ? '' : ' empty'),
      'aria-haspopup': 'listbox', 'aria-expanded': 'false',
      title: mine.length === 1 ? 'The one set banked on this recording'
        : mine.length + ' sets are banked on this recording. Click to choose.',
    }, cur ? setFace(cur)
           : [el('span', { class: 'br-set-name',
                           text: 'Choose one of ' + mine.length })]);
    btn.appendChild(el('span', { class: 'br-setbtn-more',
      text: mine.length === 1 ? 'its only set' : mine.length + ' sets' }));
    btn.appendChild(el('span', { class: 'br-setbtn-caret', 'aria-hidden': 'true',
                                 text: '▾' }));
    btn.addEventListener('click', () => openSetMenu(btn, mine));
    btn.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        openSetMenu(btn, mine);
      }
    });
    return btn;
  }

  /* The menu: every set on the recording as a card, under the button (or
     over it where there is no room below). Arrows move, Enter chooses,
     Escape or a press anywhere else closes. On the page, not in a modal:
     it is one question in the middle of a form. */
  let setMenu = null;
  function closeSetMenu() {
    if (!setMenu) return;
    const m = setMenu;
    setMenu = null;
    m.off();
    m.classList.add('out');
    setTimeout(() => { if (m.parentNode) m.remove(); }, 140);
  }

  function openSetMenu(btn, mine) {
    if (setMenu) { closeSetMenu(); return; }
    const menu = el('div', { class: 'br-setmenu', role: 'listbox',
                             'aria-label': 'The sets banked on this recording' });
    let at = Math.max(0, mine.findIndex((c) => c.id === q.entry));
    const paint = () => opts.forEach((o, i) => o.classList.toggle('at', i === at));
    const opts = mine.map((c, i) => el('button', {
      type: 'button', role: 'option', style: '--i:' + i,
      class: 'br-setopt' + (c.id === q.entry ? ' on' : ''),
      'aria-selected': c.id === q.entry ? 'true' : 'false',
      onclick: () => { closeSetMenu(); if (c.id !== q.entry) chooseSet(c.id); },
      onmouseenter: () => { at = i; paint(); },
    }, [
      el('span', { class: 'br-setopt-tick', 'aria-hidden': 'true',
                   text: c.id === q.entry ? '✓' : '' }),
      el('span', { class: 'br-setopt-body' }, setFace(c)),
    ]));
    opts.forEach((o) => menu.appendChild(o));
    paint();
    const r = btn.getBoundingClientRect();
    menu.style.minWidth = Math.round(Math.max(r.width, 280)) + 'px';
    menu.style.left = Math.round(r.left) + 'px';
    menu.style.top = Math.round(r.bottom + 6) + 'px';
    document.body.appendChild(menu);
    // Kept on screen: flipped above when there is no room below, and
    // pulled in from the right edge.
    const h = menu.offsetHeight, w = menu.offsetWidth;
    if (r.bottom + 6 + h > window.innerHeight - 8 && r.top - h - 6 > 8) {
      menu.style.top = Math.round(r.top - h - 6) + 'px';
      menu.classList.add('up');
    }
    if (r.left + w > window.innerWidth - 8) {
      menu.style.left = Math.max(8, Math.round(window.innerWidth - w - 8)) + 'px';
    }
    btn.setAttribute('aria-expanded', 'true');
    btn.classList.add('open');
    const key = (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        at = (at + (e.key === 'ArrowDown' ? 1 : -1) + opts.length) % opts.length;
        paint();
        opts[at].focus({ preventScroll: true });
        opts[at].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter' || e.key === ' ') {
        opts[at].click();
      } else if (e.key === 'Escape') {
        closeSetMenu();
        btn.focus({ preventScroll: true });
      } else if (e.key === 'Tab') {
        closeSetMenu();
        return;
      } else {
        return;
      }
      e.preventDefault();
      e.stopPropagation();
    };
    const away = (e) => {
      if (menu.contains(e.target) || btn.contains(e.target)) return;
      closeSetMenu();
    };
    const gone = (e) => {
      if (e && e.target && e.target.nodeType === 1 && menu.contains(e.target)) return;
      closeSetMenu();
    };
    document.addEventListener('keydown', key, true);
    document.addEventListener('pointerdown', away, true);
    document.addEventListener('scroll', gone, true);
    window.addEventListener('resize', gone);
    menu.off = () => {
      document.removeEventListener('keydown', key, true);
      document.removeEventListener('pointerdown', away, true);
      document.removeEventListener('scroll', gone, true);
      window.removeEventListener('resize', gone);
      btn.setAttribute('aria-expanded', 'false');
      btn.classList.remove('open');
    };
    setMenu = menu;
    try { opts[at].focus({ preventScroll: true }); } catch (e) { /* ok */ }
  }

  /* Why a version cannot be where the stamps come from, or null. */
  function whyNotVersion(c, v) {
    if (!v.usable) {
      return v.why_not || 'No snapshot of this version is on this computer, '
        + 'so its stamps cannot be read back.';
    }
    return cfg.notFrom ? cfg.notFrom(v, c) : null;
  }

  /* The version tree for one set (constitution §6e): the lineage, newest on
     top, one lane per line, and "now" above it for the stamps as they
     stand. The "now" row is named by the tip's NAME -- labelling it with
     the maximum stored NUMBER put "v4" at the top of a list ending in v6. A
     version that cannot be a starting point is shown, disabled, with the
     reason: its count and note are still worth reading. */
  function versionOpts(c) {
    return {
      versions: c.versions || [],
      // What produced the set, as a chip above it (2026-10-20).
      producer: c.pipeline,
      producerType: c.type || cfg.type,
      idOf: (v) => v.ref,
      value: q.from_version,
      unit: 'stamps',
      notes: true,
      lead: {
        name: vName(c) + ' now',
        text: c.n + ' stamps, as they stand  ·  the newest there is',
      },
      disabled: (v) => whyNotVersion(c, v),
      state: (v) => (v.newest ? ['newest readable here'] : []),
      line: (v) => (whyNotVersion(c, v) || v.newest ? null
        : 'branches off it — nothing after it is touched'),
      heading: 'Which version of ' + (c.name || 'this set') + '’s stamps',
      sub: W.versionSub,
    };
  }

  function versionPick(c) {
    return el('div', { class: 'br-vers' }, [BARRY.ui.versionButton(
      Object.assign(versionOpts(c), {
        onpick: (v) => {
          q.from_version = v ? v.ref : null;
          refreshPlan();
        },
      }))]);
  }

  /* The groups, as three switches: lit lines a group up, a padlock holds
     it. Then, clearly labelled, whether Braces has been run on the dentate
     spikes this pool came from -- as a guide to what to hold, not as the
     thing that decides. */
  const MOVE_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true">'
    + '<path class="mv" d="M4 12h16M8 7.5 3.5 12 8 16.5M16 7.5l4.5 4.5-4.5 4.5"/>'
    + '</svg>';

  function originCard(c) {
    const o = originsOf(c);
    const hold = holdNow();
    const box = el('div', { class: 'br-origins' });
    box.appendChild(el('div', { class: 'br-origins-head' }, [
      el('label', { text: 'Line up' }),
      el('span', { class: 'br-hint', text: 'Lit groups are lined up. A held '
        + 'group stays exactly where it is: each of its stamps fills its own '
        + 'peak, and nothing else may take it.' }),
    ]));
    const row = el('div', { class: 'br-origin-row' });
    for (const [g, name] of GROUPS) {
      const n = o[g] || 0;
      const held = hold.indexOf(g) >= 0;
      row.appendChild(el('button', {
        type: 'button', role: 'switch', 'data-g': g,
        'aria-checked': held ? 'false' : 'true',
        class: 'br-origin' + (held ? ' held' : ' on') + (n ? '' : ' none'),
        title: (held ? 'Held: ' : 'Lined up: ') + n + ' ' + name
             + ' spike' + (n === 1 ? '' : 's') + '. Click to '
             + (held ? 'line them up.' : 'hold them where they are.'),
        onclick: (e) => {
          const next = held ? hold.filter((x) => x !== g) : hold.concat([g]);
          q.hold = cleanHold(next);
          const b = e.currentTarget;
          b.classList.toggle('held', !held);
          b.classList.toggle('on', held);
          setTimeout(render, 160);
        },
      }, [
        el('span', { class: 'br-origin-ico', html: held ? LOCK_SVG : MOVE_SVG }),
        el('span', { class: 'br-origin-words' }, [
          el('b', { text: name }),
          el('i', { text: n + ' spike' + (n === 1 ? '' : 's') + ' · '
                          + (held ? 'held' : 'lined up') }),
        ]),
      ]));
    }
    box.appendChild(row);
    if (c) box.appendChild(bracesLine(c));
    return box;
  }

  /* "Has Braces been run?", said plainly beside the groups. */
  function bracesLine(c) {
    const b = (c.id === q.entry && plan && plan.ok && plan.braced) || c.braced || {};
    const n = b.n || 0;
    return el('div', { class: 'br-braces-line' + (n ? ' on' : '') }, [
      el('span', { class: 'br-set-tag br-set-braces' + (n ? ' on' : '') }, [
        el('span', { class: 'br-lock-ico', html: n ? LOCK_SVG : UNLOCK_SVG }),
        el('span', { text: n ? 'Braces ✓' : 'no Braces' }),
      ]),
      el('span', { class: 'br-hint', text: n
        ? n + ' of these spikes are Incisor stamps Braces already put on '
          + 'their peaks' + (b.ds_version != null ? ' (v' + b.ds_version
            + ' of ' + (b.ds_name || 'the dentate-spike set') + ')' : '')
          + '. They are in Incisor only and Merged.'
        : (b.why ? b.why
           : b.ds_aligned ? 'The dentate spikes were aligned in Braces, but '
             + 'none of these spikes sits on one of those stamps.'
           : 'Braces had not been run on the dentate spikes this pool was '
             + 'made from.') }),
    ]);
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
    const countLine = () => q.channels.length + ' of ' + all.length
      + (nBad ? '  ·  ' + nBad + ' marked bad, unticked' : '');
    const count = el('span', { class: 'br-hint', text: countLine() });
    box.appendChild(el('div', { class: 'br-chans-head' }, [
      el('label', { text: 'Channels in the average' }),
      count,
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
          /* In place (2026-10-14): the box, the count over the grid and
             the plan's "Measured on" line, and nothing else -- a redraw
             of the panel for one tick is how the page lost its place. */
          onchange: (e) => {
            const next = new Set(q.channels);
            if (e.target.checked) next.add(c.number); else next.delete(c.number);
            q.channels = [...next].sort((a2, b2) => a2 - b2);
            e.target.closest('.br-chan').classList.toggle('on', e.target.checked);
            count.textContent = countLine();
            const mo = document.querySelector('.br-plan .br-measured');
            if (mo) mo.textContent = measuredOn();
          },
        }),
        el('span', { text: String(c.number) }),
      ]));
    }
    box.appendChild(grid);
    return box;
  }

  /* What the read is measured on, and how far a stamp may move. ONE pair of
     settings for one set and for many: a bulk run always sent these, but
     could neither show nor change them, so "many" read at ±100 ms unless
     somebody had changed it in the one-set panel first (2026-10-12).
     `lock` while a bulk run is going -- the queue already has its values. */
  function settingsFields(lock) {
    const off = lock ? 'disabled' : null;
    return el('div', { class: 'br-fields' }, [
      el('div', { class: 'br-field' }, [
        el('label', { text: 'Measured on' }),
        el('div', { class: 'seg sm br-measure' }, cfg.measures.map(
          ([id, label, title]) => el('button', {
            class: q.measure === id ? 'active' : '',
            disabled: off,
            title: title,
            onclick: () => { if (q.measure === id) return;
                             q.measure = id; render(); },
            text: label,
          }))),
        // Said once: where there is a Filter field beside it, it says it.
        cfg.bands ? null : el('span', { class: 'br-hint', text: bandWords() }),
      ].filter(Boolean)),
      /* Lock: which band the stamps are aligned through. The dentate-spike
         one by default (2026-10-26); the IED one is what Lock used before. */
      cfg.bands ? el('div', { class: 'br-field' }, [
        el('label', { text: 'Filter' }),
        el('div', { class: 'seg sm br-band' }, [
          ['ds', 'Dentate spike'], ['ied', 'IED'],
        ].map(([id, label]) => el('button', {
          class: q.band === id ? 'active' : '',
          disabled: off,
          title: (id === 'ds' ? 'The dentate-spike filter, as Braces aligns '
                   : 'The IED filter, as Lock aligned before 2026-10-26 ')
                 + '(' + bandText(id) + ')',
          onclick: () => {
            if (q.band === id) return;
            q.band = id;
            if (q.entry && !bulk.on) refreshPlan(); else render();
          },
          text: label,
        }))),
        el('span', { class: 'br-hint', text: bandText(q.band) }),
      ]) : null,
      field('Window ±ms', el('input', {
        type: 'number', step: '10', min: '5', value: String(q.window_ms),
        class: 'br-window', disabled: off,
        onchange: (e) => {
          q.window_ms = Math.max(5, parseFloat(e.target.value) || WINDOW_MS);
          render();
        },
      }), 'how far a stamp may move'),
    ]);
  }

  /* The band, as the plan read it from the filter preset where there is a
     plan: a pooled set is aligned through the IED band, not the DS one. */
  function bandWords() {
    const b = plan && plan.ok && plan.spec && plan.spec.band;
    return (b && b.length === 2)
      ? (+b[0]) + '–' + (+b[1]) + ' Hz either way' : W.band;
  }

  /* THE TWO BANDS (2026-10-26). The filter presets of the same names --
     `ds` 5-100 Hz and `ied` 1-70 Hz, each with the mains notched -- read
     from where the backend reads them, so the words and the traces say the
     numbers actually used. */
  let presets = null;
  function loadPresets() {
    if (presets) return Promise.resolve(presets);
    return api('/api/presets/filters').then((f) => {
      presets = {};
      for (const x of (f.presets || [])) presets[x.id] = x;
      return presets;
    }).catch(() => { presets = {}; return presets; });
  }
  const presetFilt = (id) => {
    const x = (presets || {})[id];
    return x ? { hp: +x.highpass || 0, lp: +x.lowpass || 0, notch: +x.notch || 0 }
             : (id === 'ied' ? { hp: 1, lp: 70, notch: 60 }
                             : { hp: 5, lp: 100, notch: 60 });
  };
  function bandText(id) {
    if (id === 'both') return '';
    const f = presetFilt(id);
    return f.hp + '–' + f.lp + ' Hz' + (f.notch ? ', ' + f.notch + ' Hz out' : '');
  }

  /* The traces in the review, through either band or both at once. Both
     is two lines on one trace, the IED band drawn over the dentate-spike
     one in its own colour (2026-10-27: "two overlapping lines, not two
     separate windows"), in every traces pane of the recording -- the
     support window's too, which learns it from the pointer. Remembered per
     tool, as a way of looking rather than a fact about a set. */
  const TRACE_KEY = () => cfg.tool + '_trace_band';
  function setTraceBand(id) {
    if (!view) return;
    view.traceBand = id;
    try { BARRY.prefs.set(TRACE_KEY(), id); } catch (e) { /* session */ }
    loadPresets().then(() => {
      if (!view) return;
      const xp = BARRY.views.xplore;
      const panes = (xp.state || {}).panes || [];
      // A second pane from the two-window version of this, put away.
      const own = panes.findIndex((x) => x.brBand);
      if (own >= 0) {
        xp.setPanes(panes.filter((x, i) => i !== own)
                         .map((x) => Object.assign({}, x)),
                    { col: 0.5, row: 0.5 });
      }
      const main = presetFilt(id === 'ied' ? 'ied' : 'ds');
      // For Both, the IED band over the dentate-spike one. Set on the
      // recording first, so the reads below fetch both.
      const want = id === 'both' ? presetFilt('ied') : null;
      const dualMoved = JSON.stringify(want)
                        !== JSON.stringify(view.sess.dual || null);
      view.sess.dual = want;
      // Every traces pane through the main band, through the Filter menu's
      // own route, so its header says so and it reads again.
      let read = false;
      (xp.state.panes || []).forEach((x, i) => {
        if (x.panel !== 'traces') return;
        if (JSON.stringify(x.filt || null) !== JSON.stringify(main)
            && xp.paneFilter) {
          xp.paneFilter(i, main);
          read = true;
        }
      });
      if (dualMoved && !read && xp.refreshAll) xp.refreshAll();
      // Every pane drawn again carries the marks, and the aid window
      // follows the pointer as before.
      view.sig = null;
      vPublish();
      vBar();
    });
  }

  function field(label, input, hint) {
    return el('div', { class: 'br-field' }, [
      el('label', { text: label }),
      input,
      hint ? el('span', { class: 'br-hint', text: hint }) : null,
    ].filter(Boolean));
  }

  function measuredOn() {
    return ((q.channels && q.channels.length)
            || ((plan && plan.channels) || []).filter((c) => !c.bad).length)
      + ' channels, averaged into one trace';
  }

  function planCard() {
    const card = el('div', { class: 'card br-plan' + (planBusy ? ' busy' : '') });
    card.appendChild(el('div', { class: 'section-label',
                                 text: 'What it will read' }));
    // Read again with what was just changed; what it said before stays.
    if (planBusy) {
      card.appendChild(el('span', { class: 'br-plan-busy', text: 'reading it again…' }));
    }
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
      dt('Measured on', measuredOn(), 'br-measured'),
      dt('Band', s.band ? s.band[0] + '–' + s.band[1] + ' Hz, on the '
                          + 'magnitude' : '—'),
      dt('Stamps', (() => {
        const v = q.from_version == null ? null
          : (plan.versions || []).find((x) => x.ref === q.from_version);
        return v ? (v.n != null ? v.n : '?') + ' in v' + v.name
                 : plan.entry.n + ' in ' + vName(plan) + ', as they stand';
      })()),
      /* Said before the button is pressed: a recording only the cluster has
         is aligned THERE, as a job, by the same rule -- and a job can wait
         in a queue, which is a different wait from a read off a drive. */
      plan.where === 'vacc'
        ? dt('Runs on', 'VACC — this computer has no copy, so it is read '
             + 'and aligned on the cluster and the proposal comes back here '
             + 'to review. Expect a few minutes, more if the queue is busy.')
        : null,
    ].filter(Boolean)));

    /* Lock: what is lined up and what is held, said where the read is
       described, because it changes it. */
    if (cfg.pin && plan.origins) {
      const hold = holdNow();
      const o = plan.origins;
      const moving = GROUPS.filter(([g]) => hold.indexOf(g) < 0);
      card.appendChild(el('p', { class: 'hint br-plan-braces'
                                 + (hold.length ? ' on' : ''),
        text: 'Lines up ' + (moving.length ? moving.map(([g, nm]) =>
          nm + ' (' + (o[g] || 0) + ')').join(', ') : 'nothing')
          + (hold.length ? '; holds ' + hold.map((g) => groupName(g) + ' ('
            + (o[g] || 0) + ')').join(', ') + ' where they are, each filling '
            + 'its own peak.' : '. Nothing is held.') }));
    }
    /* The version is the third tile of the picker above (2026-10-22), with
       the whole tree a click away; it is not asked twice. */
    return card;
  }

  const dt = (k, v, cls) => el('div', {}, [el('dt', { text: k }),
    el('dd', { class: cls || null, text: String(v) })]);

  /* What a version is CALLED. Never the stored number: two machines
     curating one entry both mint the next one and the union keeps both,
     so a history can run 0,1,2,3,4,3,4 and the maximum of it is 4 while
     the newest is the seventh. The lineage name is what the list itself
     shows, and it is what every other mention of a version has to show
     or they disagree on screen. The number is the fallback for a payload
     from a server that has not been restarted yet. */
  const vName = (o, key) => BARRY.ui.versionLabel((o && o[key || 'current_name'])
                                   != null
                                   ? o[key || 'current_name']
                                   : ((o || {}).current_version));

  /* Which version a bulk run should read, for one entry: the newest there
     is. The lineage's newest -- `versions` arrives in lineage order, so
     the last usable one is it -- and NOT the largest stored number, which
     is a different version on any entry two machines have both curated.
     An entry numbered 0,1,2,3,4,3,4 has a maximum of 4 and a newest of 6. */
  function newestOf(c) {
    const vs = (c.versions || []).filter((v) => !whyNotVersion(c, v));
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

  /* How many of a set's candidates are the thing Braces moves.

     `n` counts CANDIDATES. A set can be fully curated and hold no events
     at all -- somebody went through it and rejected every one -- and nine
     of the forty-eight sets in this bank are exactly that, one of them
     738 rejections. The server works the count out from the curation
     vocabulary rather than from a hard-coded word. */
  const goodOf = (c) => (c.n_good == null ? c.n : c.n_good);

  /* ==================================================================
     Many sets at once (2026-10-14)
     ================================================================== */
  /* WHERE A SET CAN BE ALIGNED FROM.

     This computer when it has the recording, the VACC when only the cluster
     does: the rule the one-set panel and every other tool follow
     (`BARRY.vacc.reachFor`; Braces is 'cluster' in ToolKit's READS). It used
     to be the registry's `reachable`, which means this computer only -- so
     on a laptop with no drives, where every recording is on the VACC, every
     row said "not on a drive this machine can reach", nothing could be
     ticked, and nothing was ever sent. */
  function reachOf(c) {
    const reg = (BARRY.views.toolkit && BARRY.views.toolkit.registryRows)
      ? BARRY.views.toolkit.registryRows() : [];
    if (!reg.length) {
      return { where: null, why: 'still reading which recordings this '
                                 + 'computer and the VACC can reach' };
    }
    const row = regRowOf(c);
    if (!row) {
      return { where: null, why: 'no recording with this set’s id is in '
                                 + 'this computer’s registry' };
    }
    if (!BARRY.vacc || !BARRY.vacc.reachFor) {
      const here = (row.here || []).length;
      return { where: here ? 'here' : null,
               why: here ? '' : 'not on a drive this computer can reach' };
    }
    const r = BARRY.vacc.reachFor(row, cfg.tool);
    // And whether the cluster could take it even so, for "every set to
    // the VACC".
    const up = !!(BARRY.vacc.canRead && BARRY.vacc.canRead(row)
                  && (BARRY.vacc.last || {}).configured && row.gid);
    return { where: r.where, why: r.why || '', vacc: up };
  }

  /* Why a set cannot be sent, in a sentence, or '' when it can. Ordered by
     what is most true: a set with nothing in it to align is not going to
     run wherever its recording is. */
  function whyNot(c, r) {
    if (!goodOf(c)) {
      return 'no ' + W.many + ' — all ' + c.n + ' candidate'
           + (c.n === 1 ? ' was' : 's were')
           + ' rejected or left undecided';
    }
    if (!newestRef(c)) return 'no version of its stamps can be read here';
    const at = r || reachOf(c);
    return at.where ? '' : (at.why || 'it cannot be reached from here');
  }

  const rowLabel = (c) => c.session_label || c.name || c.id;
  const flightRunning = (f) => ((f && f.job) || {}).status === 'running';
  const batchRunning = () => flights.some(flightRunning);

  /* Aligned before, with the settings on screen, from the version picked:
     the batch opens that alignment instead of reading the set again. The
     server decides for certain -- it hashes the whole question, bad
     channels and stamps included -- and this is the list saying so before
     anything is sent. */
  function answeredBefore(c) {
    const want = bulk.pick[c.id] || null;
    return (allSets || []).find((x) => {
      if (x.entry_id !== c.id) return false;
      const p = x.params || {};
      if ((p.measure || 'csd') !== q.measure) return false;
      if (Number(p.window_ms) !== Number(q.window_ms)) return false;
      const rq = p.request || {};
      // Lock: which groups were held -- a different question each.
      if (cfg.pin && (cleanHold(rq.hold) || []).join(',')
                     !== manyHold(c).join(',')) return false;
      if (cfg.bands && (rq.band_kind || 'ds') !== q.band) return false;
      const fv = ('from_version' in rq) ? rq.from_version : x.from_version;
      return (fv || null) === want;
    }) || null;
  }

  function manyRows() {
    const out = [];
    for (const c of cands || []) {
      if (bulk.pick[c.id] === undefined) bulk.pick[c.id] = newestRef(c);
      const r = reachOf(c);
      out.push({ c, r, why: whyNot(c, r) });
    }
    // By project, then recording, in natural order (2026-10-20).
    out.sort((a, b) => BARRY.ui.natCompare(a.c.project || '~', b.c.project || '~')
      || BARRY.ui.natCompare(rowLabel(a.c), rowLabel(b.c)));
    return out;
  }

  const chosen = () => manyRows().filter((x) => !x.why && bulk.want[x.c.id]
                                              && !heldAll(x.c));
  /* Lock: a set whose every spike is in a held group has nothing to move
     -- not sent, and its row says why. */
  const heldAll = (c) => cfg.pin && heldAllOf(c, manyHold(c));

  function rowSub(c, r) {
    const bad = badOf(c);
    const n = goodOf(c);
    return [
      c.name && c.name !== c.session_label ? c.name : null,
      c.project || null,
      n + ' ' + (n === 1 ? W.one : W.many)
        + (c.n !== n ? ' of ' + c.n + ' stamps' : ''),
      bad.length ? (bad.length <= 3 ? 'CSC' + bad.join(', CSC')
                                    : bad.length + ' contacts')
                   + ' marked bad' : null,
      r.where === 'here' ? 'aligned on this computer'
        : r.where === 'vacc' ? 'aligned on the VACC' : null,
    ].filter(Boolean).join('  ·  ');
  }

  function rowHay(c, r) {
    return [rowLabel(c), c.name, c.project,
            c.mouse != null ? 'm' + c.mouse : '',
            c.session != null ? 's' + c.session : '',
            r.where === 'vacc' ? 'vacc cluster' : 'here computer',
            c.aligned ? 'aligned' : 'never']
      .join(' ').toLowerCase();
  }

  /* The parts of the page, each kept until what it shows changes. */
  function manyParts() {
    if (allSets === null) loadAllSets();
    const f = shownFlight();
    return [
      { key: 'mtop', sig: 'mtop',
        build: () => el('div', { class: 'br-wrap' }, [stepHead(), modeCard()]) },
      { key: 'mpick', sig: 'mpick', build: manyPickShell,
        update: manyPickUpdate },
      { key: 'mrun', sig: 'mrun', build: manyRunShell, update: manyRunUpdate },
      f ? { key: 'mflight', sig: 'flight:' + f.id, build: flightShell,
            update: (node) => flightUpdate(node, f) } : null,
      { key: 'recent', sig: 'recent:' + recentRev, enter: false,
        build: recentSets },
    ];
  }

  let allSetsAsked = false;
  function loadAllSets() {
    if (allSetsAsked) return;
    allSetsAsked = true;
    api('/api/braces/sets?type=' + cfg.setTypes).then((got) => { allSets = got.sets || []; })
      .catch(() => { allSets = allSets || []; })
      .finally(() => {
        allSetsAsked = false;
        bulk.rev += 1;
        // Lock's groups default to what a set was last run with.
        if (shownPage === 'many' || (cfg.pin && shownPage === 'one'
                                     && !q.hold && !set_)) render();
      });
  }

  /* ---- 1. Which sets ---------------------------------------------- */
  function manyPickShell() {
    const box = el('div', { class: 'card br-many br-many-' + cfg.tool }, [
      el('div', { class: 'section-label', text: '1. Which sets' }),
      el('p', { class: 'hint br-many-say', style: 'max-width:80ch' }),
    ]);
    const search = el('input', {
      type: 'search', class: 'inc-search', value: bulk.find,
      placeholder: 'Type a mouse, session, project, or “vacc” or “here”',
      'aria-label': 'Search the sets', 'data-fk': 'br-many-search',
    });
    let t = null;
    search.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(() => { bulk.find = search.value; render(); }, 160);
    });
    box.appendChild(search);
    box.appendChild(el('div', { class: 'br-many-parts' }));
    return box;
  }

  function manyPickUpdate(node) {
    const rows = manyRows();
    const ok = rows.filter((x) => !x.why);
    const blocked = rows.filter((x) => x.why);
    const words = bulk.find.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const shown = ok.filter((x) => {
      const hay = rowHay(x.c, x.r);
      return words.every((w) => hay.indexOf(w) >= 0);
    });
    const nHere = ok.filter((x) => x.r.where === 'here').length;
    const say = node.querySelector('.br-many-say');
    const text = ok.length
      ? ok.length + ' ' + W.setWord + (ok.length === 1 ? '' : 's')
        + ' can be aligned: ' + nHere + ' on this computer, '
        + (ok.length - nHere) + ' on the VACC, where only the cluster has '
        + 'the recording. Tick any mix of them; each half runs where its '
        + 'data is, and both at once.'
      : 'None of the ' + W.setWord + 's can be aligned from here yet — the '
        + 'reasons are below.'
        + (unsorted ? ' ' + unsortedWords() : '');
    if (say && say.textContent !== text) say.textContent = text;
    const nTick = ok.filter((x) => bulk.want[x.c.id]).length;
    BARRY.ui.sections(node.querySelector('.br-many-parts'), [
      { key: 'tools', enter: false,
        sig: [bulk.rev, bulk.rows, bulk.find, nTick, q.measure, q.window_ms,
              q.band],
        build: () => pickTools(ok, shown) },
      { key: 'list', enter: false,
        sig: [bulk.rev, bulk.find, (cands || []).length, q.measure,
              q.window_ms, q.band],
        build: () => pickList(ok, shown) },
      { key: 'blocked', enter: false,
        sig: [bulk.rev, blocked.length],
        build: () => blockedPart(blocked) },
    ]);
  }

  function pickTools(ok, shown) {
    const all = (fn) => () => { fn(); bulk.rev += 1; render(); };
    const notYet = shown.filter((x) => !answeredBefore(x.c));
    const ticked = ok.filter((x) => bulk.want[x.c.id]);
    const tHere = ticked.filter((x) => x.r.where === 'here').length;
    return el('div', { class: 'tk-actions inc-pick-tools br-many-tools' }, [
      el('button', { class: 'btn ghost sm',
        text: 'Tick the ' + shown.length + ' shown',
        disabled: shown.length ? null : 'disabled',
        onclick: all(() => shown.forEach((x) => { bulk.want[x.c.id] = true; })) }),
      el('button', { class: 'btn ghost sm',
        text: 'Only the ' + notYet.length + ' not aligned with these settings',
        title: 'Ticks every set shown that has no alignment yet with the '
             + 'settings below, and unticks the ones that have',
        disabled: shown.length ? null : 'disabled',
        onclick: all(() => shown.forEach((x) => {
          if (answeredBefore(x.c)) delete bulk.want[x.c.id];
          else bulk.want[x.c.id] = true;
        })) }),
      el('button', { class: 'btn ghost sm', text: 'Clear',
        disabled: ticked.length ? null : 'disabled',
        onclick: all(() => { bulk.want = {}; }) }),
      el('span', { class: 'hint quiet br-bulk-count',
        text: ticked.length + ' ticked'
          + (ticked.length ? ' (' + tHere + ' here, ' + (ticked.length - tHere)
                             + ' on the VACC)' : '')
          + '  ·  ' + shown.length + ' of ' + ok.length + ' shown' }),
    ]);
  }

  function pickList(ok, shown) {
    const list = el('div', { class: 'inc-pick-list br-many-list',
                             'data-keep-scroll': 'br-many-list' });
    if (!shown.length) {
      list.appendChild(el('div', { class: 'empty-state', text: ok.length
        ? 'Nothing matches that. Clear the search to see all ' + ok.length + '.'
        : 'Nothing here can be aligned from this computer yet; the reasons '
          + 'are listed below.' }));
    }
    for (const x of shown) list.appendChild(manyRow(x.c, x.r));
    return list;
  }

  /* One set. A row rather than a label: the version list and the two
     buttons inside it must not also toggle the tick. A tick changes this
     row and the counts, IN PLACE -- the list is not rebuilt, so it keeps
     its scroll (the whole panel used to be). */
  function manyRow(c, r) {
    const on = !!bulk.want[c.id];
    const had = (allSets || []).filter((x) => x.entry_id === c.id);
    const before = answeredBefore(c);
    const vs = (c.versions || []).filter((v) => v.usable);
    const nBad = badOf(c).length;
    const row = el('div', {
      class: 'inc-pick br-bulk-row' + (on ? ' on' : '') + (before ? ' done' : ''),
      'data-id': c.id,
    }, [
      el('input', {
        type: 'checkbox', checked: on ? 'checked' : null,
        'aria-label': 'Align ' + rowLabel(c),
        onchange: (e) => {
          if (e.target.checked) bulk.want[c.id] = true;
          else delete bulk.want[c.id];
          row.classList.toggle('on', e.target.checked);
          render();
        },
      }),
      el('div', { class: 'ip-main' }, [
        el('span', { class: 'ip-name nm', text: rowLabel(c) }),
        el('span', { class: 'ip-sub', text: rowSub(c, r) }),
        // Lock: whether Braces has been run, on the row itself.
        cfg.pin ? el('span', { class: 'br-row-braces' }, [bracesChip(c)]) : null,
        before ? el('span', { class: 'ip-done', text:
          'aligned with these settings ' + String((before.created || {}).at || '')
            .slice(0, 10) + ' — sending it opens that one, nothing is read' })
          : null,
        heldAll(c) ? el('span', { class: 'ip-done br-held-all', text:
          'every spike is in a held group — nothing to move, so it is not '
          + 'sent. Light a group to line it up.' })
          : null,
      ].filter(Boolean)),
      /* The version, changeable before anything is sent: one button that
         opens the whole tree (2026-10-21: "Braces still had the old drop
         down version selection"), every version with who, when, what
         processed it and its note. Only readable versions can be picked;
         the rest are shown with why. */
      vs.length ? BARRY.ui.versionButton({
        versions: c.versions || [], idOf: (v) => v.ref,
        value: bulk.pick[c.id] || null, unit: 'stamps',
        producer: c.pipeline, producerType: c.type || cfg.type,
        // Per version, where something rules one out (Lock: Junction's
        // raw pool); the tree shows it greyed with the reason.
        disabled: cfg.notFrom ? (v) => whyNotVersion(c, v) : null,
        heading: 'Which version of ' + rowLabel(c) + '’s stamps to align',
        sub: 'The newest one this computer can read is chosen unless you '
           + 'pick another.',
        state: (v) => (v === newestOf(c) ? ['newest readable here'] : []),
        onpick: (v) => {
          if (!v) return;
          bulk.pick[c.id] = v.ref;
          redrawRow(c, row, '.vbtn');
        },
      }) : el('span', { class: 'br-hint', text: 'no readable version' }),
      /* Lock: the stamps Braces placed, locked or not, per set -- right
         after the version and before the bad channels (2026-10-22). Locked
         by itself wherever there are any; dim where Braces placed none. */
      cfg.pin ? manyOrigins(c) : null,
      /* The contacts this recording has marked bad, which the batch uses.
         Interpolated rather than dropped -- a second difference over an
         uneven grid is not a CSD -- so "which wires are not believed". */
      el('button', {
        class: 'mini br-bulk-bad' + (nBad ? ' some' : ''),
        title: nBad ? 'Interpolated on this recording: CSC'
                      + badOf(c).join(', CSC') + '. Click to change.'
                    : 'No contact is marked bad on this recording. Click to '
                      + 'mark one.',
        text: nBad ? nBad + ' bad' : 'none bad',
        onclick: () => editBad(c),
      }),
      r.where === 'vacc'
        ? (BARRY.vacc.mark({ gid: c.gid }, { compact: true })
           || el('span', { class: 'ip-where', text: 'VACC' }))
        : el('span', { class: 'ip-where', text: 'HERE',
                       title: 'Aligned on this computer' }),
      had.length ? el('button', { class: 'mini br-bulk-had',
        text: 'Open the newest of ' + had.length,
        title: 'Aligned ' + had.length + ' time' + (had.length === 1 ? '' : 's')
             + ' already. The newest: ' + setLine(had[0])
             + '. Opening it reads nothing.',
        onclick: () => { reused = null; openSet(had[0].set_id); } })
        : el('span', { class: 'br-bulk-none' }),
    ]);
    return row;
  }

  /* One row of Many drawn again where it stands (2026-10-27: "after
     selecting the version here it scrolls back to the top"). A version
     picked or a group held changes that row and the counts, not which rows
     there are, so the list is not rebuilt and its scroll is never at stake.
     `focus` is what had it in the old row, given back in the new one. */
  function redrawRow(c, node, focus) {
    const row = node && node.closest ? node.closest('.br-bulk-row') : null;
    if (row && row.isConnected) {
      const fresh = manyRow(c, reachOf(c));
      row.replaceWith(fresh);
      const f = focus ? fresh.querySelector(focus) : null;
      if (f) { try { f.focus({ preventScroll: true }); } catch (e) { /* gone */ } }
      bulk.rows += 1;
    } else {
      bulk.rev += 1;
    }
    render();
  }

  /* Whether a set in Many keeps Braces' stamps: yes, wherever it has any,
     until its lock is pressed open. */
  function manyPin(c) {
    return !!(cfg.pin && manyHold(c).length);
  }

  /* The groups one row of Many holds: changed on the row, else its own. */
  function manyHold(c) {
    if (!cfg.pin) return [];
    return bulk.hold[c.id] || holdFor(c);
  }

  /* One row's three groups, as small switches: I, M, D, lit when lined up
     and padlocked when held -- where the Braces lock was (2026-10-26). */
  function manyOrigins(c) {
    const o = c.origins || {};
    const box = el('span', { class: 'br-bulk-origins',
                             role: 'group', 'aria-label': 'Which groups to line up' });
    const face = () => {
      const hold = manyHold(c);
      box.innerHTML = '';
      for (const [g, name] of GROUPS) {
        const n = o[g] || 0;
        const held = hold.indexOf(g) >= 0;
        box.appendChild(el('button', {
          type: 'button', role: 'switch', 'data-g': g,
          'aria-checked': held ? 'false' : 'true',
          class: 'mini br-bulk-og' + (held ? ' held' : ' on') + (n ? '' : ' none'),
          title: name + ': ' + n + ' spike' + (n === 1 ? '' : 's') + ', '
               + (held ? 'held where they are. Click to line them up.'
                       : 'lined up. Click to hold them.'),
          onclick: () => {
            const now = manyHold(c);
            bulk.hold[c.id] = cleanHold(held ? now.filter((x) => x !== g)
                                             : now.concat([g]));
            face();
            redrawRow(c, box, '.br-bulk-og[data-g="' + g + '"]');
          },
        }, [
          held ? el('span', { class: 'br-lock-ico sm', html: LOCK_SVG }) : null,
          el('b', { text: name.charAt(0) }),
          el('span', { text: String(n) }),
        ].filter(Boolean)));
      }
    };
    face();
    return box;
  }

  function blockedPart(blocked) {
    const box = el('div', {});
    if (!blocked.length) return box;
    box.appendChild(el('details', { class: 'inc-blocked',
                                    'data-keep': 'br-many-blocked' }, [
      el('summary', { text: blocked.length + ' cannot be aligned from here, '
                            + 'so left out' }),
      el('div', {}, blocked.map((x) => el('div', { class: 'hint quiet',
        text: rowLabel(x.c) + ' — ' + x.why }))),
    ]));
    return box;
  }

  /* ---- 2. The alignment, for every set sent ------------------------ */
  function manyRunShell() {
    return el('div', { class: 'card br-bulk' }, [
      el('div', { class: 'section-label',
                  text: '2. Alignment, for every set sent' }),
      el('div', { class: 'br-many-run' }),
    ]);
  }

  function manyRunUpdate(node) {
    const inner = node.querySelector('.br-many-run');
    if (!inner) return;
    const run = batchRunning();
    const picks = Object.keys(bulk.want).sort().join(',');
    BARRY.ui.sections(inner, [
      { key: 'set', enter: false,
        sig: [q.measure, q.window_ms, q.band, bulk.force, allVaccOn(), run,
              !!(BARRY.vacc && (BARRY.vacc.last || {}).configured)],
        build: () => runSettings(run) },
      { key: 'cost', enter: false,
        sig: [picks, bulk.rev, bulk.rows, q.measure, q.window_ms, q.band,
              bulk.force, allVaccOn(), run],
        build: costLine },
      { key: 'go', enter: false, sig: [picks, bulk.rev, bulk.rows, run],
        build: manyGo },
    ]);
  }

  /* Whether there is a cluster to send to at all. */
  const clusterUp = () => !!(BARRY.vacc && (BARRY.vacc.last || {}).configured);
  /* Every set to the VACC: on by itself where there is one. */
  const allVaccOn = () => (bulk.allVacc == null ? clusterUp()
                                                : !!(bulk.allVacc && clusterUp()));

  const CLOUD_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true">'
    + '<path d="M7 18h10.5a4 4 0 0 0 .6-7.95A6 6 0 0 0 6.4 9.2 4.5 4.5 0 0 0 7 18z"/>'
    + '<path d="M12 15.5v-5M9.8 12.6 12 10.4l2.2 2.2"/></svg>';
  const AGAIN_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true">'
    + '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.8 4.5v4h-4"/></svg>';

  /* A switch that looks like one: a chip with its icon, what it does, what
     that means for this batch, and a light. Replaces two checkboxes with
     sentences after them (2026-10-27: "these buttons are weird"). */
  function chipSwitch(o) {
    return el('button', {
      type: 'button', class: 'br-chip' + (o.on ? ' on' : '') + (o.cls ? ' ' + o.cls : ''),
      'aria-pressed': o.on ? 'true' : 'false',
      disabled: o.lock ? 'disabled' : null,
      title: o.title,
      onclick: (e) => {
        // The chip answers at once; the counts below follow.
        const b = e.currentTarget;
        b.classList.toggle('on', !o.on);
        b.setAttribute('aria-pressed', !o.on ? 'true' : 'false');
        o.toggle(!o.on);
        setTimeout(render, 120);
      },
    }, [
      el('span', { class: 'br-chip-ico', html: o.icon }),
      el('span', { class: 'br-chip-words' }, [
        el('b', { text: o.label }),
        el('i', { text: o.on ? o.onText : o.offText }),
      ]),
      el('span', { class: 'br-chip-light', 'aria-hidden': 'true' }),
    ]);
  }

  function runSettings(lock) {
    const box = el('div', { class: 'br-bulk-settings' }, [settingsFields(lock)]);
    const chips = el('div', { class: 'br-chips' });
    if (clusterUp()) {
      chips.appendChild(chipSwitch({
        on: allVaccOn(), lock, icon: CLOUD_SVG, cls: 'vacc',
        label: 'Send to the VACC',
        onText: 'every set, side by side on the cluster',
        offText: 'only the sets this computer cannot read',
        title: 'On: every ticked set is aligned on the cluster, side by side. '
             + 'Off: this computer aligns the ones it has, one after another, '
             + 'and only the rest go to the cluster. A set the cluster cannot '
             + 'read stays here either way.',
        toggle: (v) => { bulk.allVacc = v; },
      }));
    }
    chips.appendChild(chipSwitch({
      on: !!bulk.force, lock, icon: AGAIN_SVG, cls: 'again',
      label: 'Read again',
      onText: 'even sets already run with these settings',
      offText: 'sets run before with these settings just open',
      title: 'A set already aligned with exactly these settings is opened '
           + 'from that alignment rather than read again. Turn this on to '
           + 'read every one again anyway.',
      toggle: (v) => { bulk.force = v; },
    }));
    box.appendChild(chips);
    box.appendChild(el('p', { class: 'br-hint br-bulk-say', text: 'Every set '
      + 'in this batch is read with these, and its proposal records them. '
      + 'They are the one-set panel’s too: changing them here changes them '
      + 'there.' }));
    return box;
  }

  /* Where a ticked set will actually run, this batch. */
  const runsOn = (x) => ((x.r.where === 'vacc'
                          || (allVaccOn() && x.r.vacc)) ? 'vacc' : 'here');

  function costLine() {
    const sel = chosen();
    if (!sel.length) {
      return el('p', { class: 'hint br-many-cost',
                       text: 'Tick the sets to send, above.' });
    }
    const h = sel.filter((x) => runsOn(x) === 'here').length;
    const v = sel.length - h;
    const again = bulk.force ? 0 : sel.filter((x) => answeredBefore(x.c)).length;
    const parts = [
      sel.length + ' to send',
      h ? h + ' aligned on this computer, one after another' : null,
      v ? v + ' on the VACC as one array job, side by side' : null,
      again ? again + ' already aligned with these settings, which open '
              + 'that alignment and read nothing' : null,
    ].filter(Boolean);
    return el('p', { class: 'hint br-many-cost', style: 'max-width:80ch',
      text: parts.join('  ·  ') + '. Both halves run at once, on the '
        + 'server rather than in this page: leave this view or reload and '
        + 'the batch carries on, with its progress here when you come back. '
        + 'Nothing is banked — every set lands as a proposal to review.' });
  }

  function manyGo() {
    const sel = chosen();
    const run = batchRunning();
    return el('div', { class: 'tk-actions br-many-go' }, [
      el('span', { class: 'spacer' }),
      el('button', {
        class: 'btn',
        text: run ? 'A batch is going'
          : sel.length ? 'Align ' + sel.length + ' set' + (sel.length === 1 ? '' : 's')
          : 'Tick the sets to align',
        title: run ? 'One batch at a time: the one below is still going' : null,
        disabled: (!sel.length || run) ? 'disabled' : null,
        onclick: sendBatch,
      }),
    ]);
  }

  async function sendBatch() {
    const sel = chosen();
    if (!sel.length || batchRunning()) return;
    let got;
    try {
      got = await apiPost('/api/braces/batch', {
        entries: sel.map((x) => ({ id: x.c.id,
                                   from_version: bulk.pick[x.c.id] || null,
                                   hold: cfg.pin ? manyHold(x.c) : undefined })),
        tool: cfg.tool,
        band_kind: cfg.bands ? q.band : undefined,
        measure: q.measure, window_ms: q.window_ms, estimator: q.estimator,
        force: !!bulk.force,
        where: allVaccOn() ? 'vacc' : null,
      });
    } catch (e) {
      toast(e.message, 'err', 12000);
      return;
    }
    const j = got.job || {};
    flights = [{ id: j.id, kind: 'many', started: Date.now() / 1000, job: j,
                 members: sel.map((x) => ({ id: x.c.id, gid: x.c.gid,
                                            label: rowLabel(x.c) })) }]
      .concat(flights.filter((f) => f.id !== j.id));
    flightLive.add(j.id);
    bulk.want = {};
    bulk.rev += 1;
    render();
    loadFlights();
  }

  /* ---- 3. The batch, as it goes ------------------------------------ */
  function shownFlight() {
    return flights.find((f) => !dismissed.has(f.id)) || null;
  }

  /* Asked of the server, which is where the batch is: every 1.5 s while
     one is going and not at all otherwise. Kept going while the panel is
     elsewhere, so a batch that lands is announced wherever you are. */
  async function loadFlights() {
    clearTimeout(flightTimer);
    flightTimer = null;
    const was = batchRunning();
    let got = null;
    try { got = await api('/api/braces/inflight?tool=' + cfg.tool); }
    catch (e) { /* next time */ }
    if (got) {
      flights = got.jobs || [];
      let landed = false;
      for (const f of flights) {
        const snap = f.job || {};
        if (snap.status === 'running') flightLive.add(f.id);
        for (const m of (snap.members || [])) {
          const k = f.id + ':' + m.id;
          if (m.status === 'done' && m.set_id && !flightSeen.has(k)) {
            flightSeen.add(k);
            landed = true;
          }
        }
        if (snap.status !== 'running' && flightLive.has(f.id)
            && !flightAnnounced.has(f.id)) {
          flightAnnounced.add(f.id);
          announce(f);
        }
      }
      // What landed is in the Alignments list and on its row.
      if (landed) { allSets = null; recentRev += 1; }
      if (onScreen() && (shownPage === 'many' || was !== batchRunning())) {
        render();
      }
    }
    if (batchRunning() || !got) {
      flightTimer = setTimeout(loadFlights, got ? 1500 : 5000);
    }
  }

  function onScreen() {
    const tk = BARRY.views.toolkit;
    return !!host() && !set_
      && (!tk || typeof tk.tool !== 'function' || tk.tool() === cfg.tool);
  }

  function tally(ms) {
    const n = { waiting: 0, queued: 0, running: 0, done: 0, failed: 0 };
    for (const m of ms) n[m.status in n ? m.status : 'waiting'] += 1;
    return n;
  }

  function announce(f) {
    const snap = f.job || {};
    const ms = snap.members || [];
    const n = tally(ms);
    const head = snap.status === 'done' ? 'The batch has landed: '
      : snap.status === 'canceled' ? 'The batch was stopped: '
      : 'The batch ended early (' + (snap.error || 'no reason given') + '): ';
    toast(head + n.done + ' of ' + ms.length + ' aligned'
          + (n.failed ? ', ' + n.failed + ' failed' : '')
          + '. Each is a proposal waiting to be reviewed — nothing has been '
          + 'banked.', (n.failed || snap.status !== 'done') ? 'warn' : 'ok',
          10000);
  }

  function flightShell() {
    return el('div', { class: 'card br-flight' }, [
      el('div', { class: 'section-label', text: '3. The batch' }),
      el('div', { class: 'br-flight-parts' }),
    ]);
  }

  function membersOf(f) {
    const snap = f.job || {};
    return snap.members || (f.members || []).map((m) => (
      { id: m.id, label: m.label, status: 'waiting' }));
  }

  function flightUpdate(node, f) {
    const inner = node.querySelector('.br-flight-parts');
    if (!inner) return;
    const snap = f.job || {};
    const ms = membersOf(f);
    const n = tally(ms);
    BARRY.ui.sections(inner, [
      { key: 'line', enter: false,
        sig: [snap.status, n.done, n.failed, n.running, n.queued,
              Math.floor((snap.elapsed || 0) / 15)],
        build: () => flightLine(f, ms, n) },
      { key: 'bar', enter: false, sig: 'bar',
        build: () => el('div', { class: 'br-fbar', role: 'progressbar',
                                 'aria-label': 'How far the batch has got' }, [
          el('i', { class: 'ok' }), el('i', { class: 'bad' }),
          el('i', { class: 'run' })]),
        update: (b) => paintFlightBar(b, ms, n) },
      { key: 'rows', enter: false,
        sig: ms.map((m) => [m.id, m.status, m.error, m.set_id, m.cached,
                            m.where].join(':')).join('|'),
        build: () => flightRows(ms),
        update: (box) => {
          // The step of a row that is going, without rebuilding the rows.
          for (const m of ms) {
            const cell = box.querySelector('[data-mid="' + cssEsc(m.id)
                                           + '"] .dop-batch-state');
            const w = memberWords(m);
            if (cell && cell.textContent !== w) cell.textContent = w;
          }
        } },
      { key: 'acts', enter: false, sig: [snap.status, n.failed, f.id],
        build: () => flightActs(f, ms) },
    ]);
  }

  function spellFor(sec) {
    const s_ = Math.max(0, Math.round(sec || 0));
    if (s_ < 90) return s_ + ' s';
    if (s_ < 5400) return Math.round(s_ / 60) + ' min';
    return (Math.round(s_ / 360) / 10) + ' h';
  }

  function flightLine(f, ms, n) {
    const snap = f.job || {};
    const at = f.started ? new Date(f.started * 1000) : null;
    const when = at ? at.toTimeString().slice(0, 5) : '';
    const here = ms.filter((m) => m.where === 'here').length;
    const vacc = ms.filter((m) => m.where === 'vacc').length;
    const state = snap.status === 'running' ? 'going'
      : snap.status === 'done' ? 'landed'
      : snap.status === 'canceled' ? 'stopped' : 'ended early';
    return el('div', { class: 'br-flight-line' }, [
      el('strong', { text: ms.length + ' set' + (ms.length === 1 ? '' : 's')
                           + ', ' + state }),
      el('span', { class: 'br-hint', text: [
        when ? 'sent ' + when + (f.by ? ' by ' + f.by : '') : null,
        (here || vacc) ? here + ' here, ' + vacc + ' on the VACC' : null,
        n.done + ' landed', n.failed ? n.failed + ' failed' : null,
        n.running ? n.running + ' aligning' : null,
        n.queued ? n.queued + ' in the cluster’s queue' : null,
        n.waiting ? n.waiting + ' waiting' : null,
        spellFor(snap.elapsed) + (snap.status === 'running' ? ' so far' : ''),
      ].filter(Boolean).join('  ·  ') }),
      snap.status !== 'running' && snap.status !== 'done' && snap.error
        ? el('p', { class: 'br-err', text: snap.error }) : null,
    ].filter(Boolean));
  }

  /* Landed, failed and aligning, as one bar: a row that is part-way
     through counts for the part it has done. */
  function paintFlightBar(b, ms, n) {
    const all = Math.max(1, ms.length);
    let part = 0;
    for (const m of ms) {
      if (m.status === 'running') {
        part += m.of ? Math.min(1, (m.done || 0) / m.of) * 0.9 + 0.05 : 0.1;
      }
    }
    const pct = (v) => (100 * v / all).toFixed(2) + '%';
    const [ok, bad, run] = b.children;
    ok.style.width = pct(n.done);
    bad.style.width = pct(n.failed);
    run.style.width = pct(part);
    b.setAttribute('aria-valuenow', String(Math.round(100 * (n.done + n.failed)
                                                       / all)));
    b.title = n.done + ' of ' + ms.length + ' landed'
      + (n.failed ? ', ' + n.failed + ' failed' : '');
  }

  function memberWords(m) {
    if (m.status === 'failed') return 'failed: ' + (m.error || 'no reason given');
    if (m.status === 'done') {
      return m.cached ? 'aligned before with these settings — opens that one'
                      : 'landed — open it to review';
    }
    if (m.status === 'running') {
      if (m.where === 'vacc' && !m.of) {
        return 'on a node' + (m.slurm_id ? ' (' + m.slurm_id + ')' : '');
      }
      const lbl = STAGE_NAMES[m.step] || m.step || 'Aligning';
      return m.of ? lbl + ' ' + Math.min((m.done || 0) + 1, m.of) + ' of ' + m.of
                  : lbl;
    }
    if (m.status === 'queued') {
      return 'in the cluster’s queue' + (m.slurm_id ? ' as ' + m.slurm_id : '');
    }
    return m.step || 'waiting its turn';
  }

  function flightRows(ms) {
    const box = el('div', { class: 'dop-batch br-flight-rows' });
    for (const m of ms) {
      const st = m.status || 'waiting';
      const open = st === 'done' && m.set_id;
      box.appendChild(el(open ? 'button' : 'div', {
        class: 'dop-batch-row ' + st, 'data-mid': m.id,
        title: open ? 'Open this proposal' : null,
        onclick: open ? () => { reused = null; openSet(m.set_id); } : null,
      }, [
        el('span', { class: 'dop-batch-dot', 'aria-hidden': 'true' }),
        el('span', { class: 'dop-batch-name', text: m.label || m.id }),
        m.where ? el('span', { class: 'ip-where',
                               text: m.where === 'vacc' ? 'VACC' : 'HERE' }) : null,
        el('span', { class: 'dop-batch-state', text: memberWords(m) }),
        open && !m.cached && m.n != null
          ? el('span', { class: 'dop-batch-n',
                         text: m.n + ' aligned · ' + (m.n_flagged || 0)
                               + ' flagged' }) : null,
        /* Whether it has reached the shared database, so a proposal made
           in this batch can be reviewed on another machine. */
        open && BARRY.syncState ? BARRY.syncState.mark('braces', m.set_id) : null,
      ].filter(Boolean)));
    }
    return box;
  }

  function flightActs(f, ms) {
    const run = flightRunning(f);
    const failed = ms.filter((m) => m.status === 'failed');
    return el('div', { class: 'tk-actions br-flight-acts' }, [
      run ? el('button', { class: 'btn ghost', text: 'Stop the batch',
        title: 'The set being read stops and the cluster’s jobs are '
             + 'cancelled. Every set already filed stays filed.',
        onclick: async () => {
          try {
            await apiPost('/api/braces/batch/' + encodeURIComponent(f.id)
                          + '/cancel', {});
            toast('Stopping. Every set already filed stays filed.', null, 6000);
          } catch (e) { toast(e.message, 'err', 8000); }
          loadFlights();
        } }) : null,
      (!run && failed.length) ? el('button', { class: 'btn ghost sm',
        text: 'Tick the ' + failed.length + ' that failed, to send again',
        onclick: () => {
          for (const m of failed) bulk.want[m.id] = true;
          bulk.rev += 1;
          render();
        } }) : null,
      el('span', { class: 'spacer' }),
      !run ? el('button', { class: 'btn ghost sm', text: 'Put this batch away',
        title: 'Every set it made stays in the Alignments list below',
        onclick: () => {
          dismissed.add(f.id);
          try {
            localStorage.setItem('barry.' + cfg.tool + '.dismissed',
                                 JSON.stringify([...dismissed].slice(-40)));
          } catch (e) { /* remembered for this page only */ }
          render();
        } }) : null,
    ].filter(Boolean));
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
    return BARRY.vacc.reachFor(row, cfg.tool).path;
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
            cfg.name + ' also screens for dead and railing contacts on every run '
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
            /* Re-read the registry, forced.

               `refresh` re-runs whichever ToolKit tool is on screen, which
               is this one -- so it repainted the table out of the same
               sixty-second cache the edit had just made wrong, and the chip
               went on saying what it said before for up to a minute. The
               cache has a force flag for exactly this: something changed
               underneath it. */
            const tk = BARRY.views.toolkit;
            if (tk && tk.loadRegistry) {
              try { await tk.loadRegistry(true); } catch (e2) {}
            }
            toast(want.length
              ? 'CSC' + want.join(', CSC') + ' will be interpolated on '
                + (c.session_label || c.name) + '.'
              : 'Nothing is marked bad on ' + (c.session_label || c.name)
                + ' any more.', null, 6000);
          } catch (e) {
            toast('Could not save that: ' + e.message, 'err', 8000);
          }
          bulk.rev += 1;
          render();
        });
  }

  /* Attribute selectors take a quoted value, and a bank id is hex -- but
     it is somebody else's string, so it is escaped rather than trusted. */
  function cssEsc(v) {
    return (window.CSS && CSS.escape) ? CSS.escape(String(v))
                                      : String(v).replace(/["\\]/g, '\\$&');
  }

  /* AN ALIGNMENT, IN ONE LINE: when, who, what it was read with, and where
     it stands. Said in full because a set aligned twice has two of these
     side by side, and "which one is the ±200 ms one" is the question. */
  const MEASURE_WORDS = { csd: 'CSD', voltage: 'voltage', slope: 'slope' };
  function setLine(s) {
    const p = s.params || {};
    const c = s.counts || {};
    const at = String((s.created || {}).at || '').slice(0, 16).replace('T', ' ');
    const by = (s.created || {}).by;
    return [at + (by ? ' by ' + by : ''),
            (MEASURE_WORDS[p.measure] || p.measure || 'CSD') + ', \u00b1'
              + (p.window_ms != null ? p.window_ms : '?') + ' ms, '
              + (p.n_channels != null ? p.n_channels : '?') + ' channels'
              + (s.from_version == null ? '' : ', an earlier version'),
            s.committed ? 'accepted as v' + s.committed.version
              : (c.waiting || 0) + ' still to answer \u00b7 ' + s.n + ' stamps']
      .filter(Boolean).join('  \u00b7  ');
  }

  function setRow(s, withName) {
    return el('button', {
      class: 'br-recent-row' + (s.committed ? ' done' : ''),
      'data-set': s.set_id,
      onclick: () => { reused = null; openSet(s.set_id); },
    }, [
      withName ? el('strong', { text: s.name || s.entry_id }) : null,
      el('span', { text: setLine(s) }),
      /* Whether it has reached the shared database, so a set reviewed
         here can be picked up on another machine (2026-10-06). */
      BARRY.syncState ? BARRY.syncState.mark('braces', s.set_id) : null,
    ].filter(Boolean));
  }

  /* EVERY ALIGNMENT, BY SET (2026-10-14).

     It showed the newest twelve, so a thirteenth run hid the oldest -- on
     this machine that was 75 of 87 -- and the only way back to one was to
     run it again. Nothing was ever deleted; it just could not be reached.
     Now every one is listed, grouped by the set it aligns with that set's
     newest first and the earlier ones folded under it, and there is a
     search. A set's own panel lists its alignments too
     (`entryAlignments`). */
  function recentSets() {
    const box = el('div', { class: 'card br-recent' });
    box.appendChild(el('div', { class: 'section-label',
                                text: 'Alignments' }));
    const count = el('span', { class: 'br-hint br-recent-n' });
    const listHost = el('div', { class: 'br-recent-body' }, [
      el('p', { class: 'hint', text: 'Looking\u2026' })]);
    const search = el('input', { type: 'search', class: 'br-recent-search',
      'aria-label': 'Find an alignment by set', value: recentQ.text,
      placeholder: 'Find a set, a mouse, a session',
      oninput: (e) => { recentQ.text = e.target.value;
                        fillRecent(listHost, count); } });
    const show = el('div', { class: 'seg sm br-recent-show' }, [
      ['all', 'All'], ['open', 'Still to answer'],
    ].map(([id, label]) => el('button', {
      class: recentQ.show === id ? 'active' : '',
      onclick: (e) => {
        recentQ.show = id;
        for (const b of e.target.parentNode.children) b.classList.remove('active');
        e.target.classList.add('active');
        fillRecent(listHost, count);
      },
      text: label,
    })));
    box.appendChild(el('div', { class: 'br-recent-bar' }, [search, show, count]));
    box.appendChild(listHost);
    api('/api/braces/sets?type=' + cfg.setTypes).then((got) => {
      allSets = got.sets || [];
      fillRecent(listHost, count);
    }).catch((e) => {
      listHost.replaceChildren(el('p', { class: 'hint br-warn',
        text: 'The alignments could not be listed: ' + e.message }));
    });
    return box;
  }

  function fillRecent(host, count) {
    const list = allSets || [];
    if (!list.length) {
      host.replaceChildren(el('p', { class: 'hint', text:
        'None yet. One appears here as soon as you run it, and every one is '
        + 'kept -- accepted or not -- so reviewing the flags does not have '
        + 'to happen in one sitting, and running another never hides one.' }));
      count.textContent = '';
      return;
    }
    const groups = new Map();
    for (const one of list) {                    // newest first already
      const k = one.entry_id || one.set_id;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(one);
    }
    const words = recentQ.text.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const out = [];
    let nSets = 0, nAl = 0;
    for (const ss of groups.values()) {
      const name = String(ss[0].name || ss[0].entry_id || '').toLowerCase();
      if (words.some((w) => name.indexOf(w) < 0)) continue;
      const pick = recentQ.show === 'open' ? ss.filter((x) => !x.committed) : ss;
      if (!pick.length) continue;
      nSets += 1;
      nAl += pick.length;
      const grp = el('div', { class: 'br-recent-grp' }, [setRow(pick[0], true)]);
      if (pick.length > 1) {
        const older = pick.slice(1);
        grp.appendChild(el('details', { class: 'br-recent-older' }, [
          el('summary', { text: older.length + ' earlier alignment'
            + (older.length === 1 ? '' : 's') + ' of this set' }),
        ].concat(older.map((x) => setRow(x, false)))));
      }
      out.push(grp);
    }
    count.textContent = nAl + ' alignment' + (nAl === 1 ? '' : 's') + ' of '
      + nSets + ' set' + (nSets === 1 ? '' : 's')
      + (nAl < list.length ? ', of ' + list.length + ' in all' : '');
    host.replaceChildren(out.length ? el('div', { class: 'br-recent-list' }, out)
      : el('p', { class: 'hint', text: 'Nothing matches that.' }));
  }

  /* The alignments already made of the set this panel is on: each opens
     without the recording being read. */
  function entryAlignments() {
    const box = el('div', { class: 'card br-entry-sets' });
    box.appendChild(el('div', { class: 'section-label',
                                text: 'Alignments of this set' }));
    const host = el('div', {}, [el('p', { class: 'hint quiet',
                                          text: 'Looking\u2026' })]);
    box.appendChild(host);
    const entry = q.entry;
    api('/api/braces/sets?entry_id=' + encodeURIComponent(entry)).then((got) => {
      if (q.entry !== entry) return;
      const list = got.sets || [];
      host.replaceChildren(...(list.length ? [
        el('p', { class: 'hint quiet', text: list.length + ' made already. '
          + 'Open one to review or bank it; nothing is read again. Running '
          + 'it again with settings already used opens that alignment '
          + 'instead of reading the recording.' }),
        el('div', { class: 'br-recent-list' }, list.map((x) => setRow(x, false))),
      ] : [el('p', { class: 'hint quiet', text: 'None yet.' })]));
    }).catch((e) => {
      host.replaceChildren(el('p', { class: 'hint br-warn',
        text: 'Could not be listed: ' + e.message }));
    });
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

    if (reused && reused.set_id === s.set_id) {
      box.appendChild(el('div', { class: 'card br-reused' }, [
        el('span', { text: 'Aligned before with exactly these settings ('
          + reused.line + '). This is that alignment: nothing was read '
          + 'again.' }),
        el('button', { class: 'btn ghost sm br-read-again',
          text: 'Read it again',
          title: 'Read the recording again with these settings and make a '
               + 'new alignment beside this one. This one is kept.',
          onclick: () => { set_ = null; bench = null; reused = null;
                           render(); run(true); } }),
      ]));
    }

    if (s.committed) {
      box.appendChild(el('div', { class: 'card br-done', text:
        'Accepted as version ' + s.committed.version + ' by '
        + s.committed.by + '. This is the record of how that version was '
        + 'made, so it cannot be changed — run ' + cfg.name + ' again to propose '
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
      /* Every spike first, then how it splits (2026-10-26: "108 spikes,
         83 locked" read as a set of 108 when it held 191). */
      count((s.rows || []).length, W.many),
      sum.n_locked ? count(sum.n, 'lined up') : null,
      sum.n_locked ? count(sum.n_locked, 'held', 'lock') : null,
      count((c.auto || 0) + (c.confirmed || 0) - heldAnswered(), 'confirmed',
            'ok'),
      count(c.waiting || 0, 'need you', (c.waiting ? 'warn' : null)),
      count(sum.n_same || 0, 'already aligned'),
      count(ms(sum.shift_median_ms), 'median Δ'),
      count(sum.shift_max_ms, 'largest move ms'),
    ].filter(Boolean)));

    /* What was deliberately not touched. Said out loud rather than left to
       be inferred from a count that does not add up: a curated set is not a
       list of events, and the ones somebody rejected are not moved. */
    if (sum.n_skipped) {
      const by = sum.skipped || {};
      const names = (set_.entry || {}).label_names || {};
      const bits = Object.keys(by).map((k) =>
        by[k] + ' ' + (names[k] || k));
      box.appendChild(el('p', { class: 'hint br-note', text:
        'Left alone: ' + bits.join(', ') + '. ' + cfg.name + ' moves only '
        + 'the stamps somebody called ' + W.aOne + ' — and they are kept out of '
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

  /* Held rows the counts call auto or confirmed: they were never in
     question, so "confirmed" leaves them out. */
  function heldAnswered() {
    const rows = (set_ && set_.set.rows) || [];
    let n = 0;
    rows.forEach((r, i) => { if (r.locked && callFor(i) !== 'keep') n += 1; });
    return n;
  }

  function count(v, label, tone) {
    return el('div', { class: 'br-count' + (tone ? ' ' + tone : '') }, [
      el('b', { text: String(v == null ? '—' : v) }),
      el('span', { text: label }),
    ]);
  }

  function histCard(sum) {
    const card = el('div', { class: 'card' });
    card.appendChild(el('div', { class: 'section-label',
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
    // Lock (2026-10-23): its own peak is one a locked Braces stamp fills,
    // and more than one other was left to choose from.
    locked_peak: 'pushed off a Braces stamp’s peak, several left',
    // Not one of the proposal's. Raised by the review and cleared by the
    // review -- see `overlapping`.
    overlap: 'shares a time with another stamp',
    // Not a flag either: Lock held it where it was.
    locked: 'held where it is',
  };

  function tableCard(c) {
    const card = el('div', { class: 'card br-table-card' });
    const all = (set_.set.rows || []);
    const pills = [
      ['flag', 'Needs you', c.waiting || 0],
      /* Only when there are any. A pass that is empty on every set anybody
         has ever run is a pill that teaches people to ignore pills -- and
         when it is not empty it is the one thing standing between this
         proposal and the bank, so it goes near the front. */
      ...(c.overlap ? [['overlap', 'Overlapping', c.overlap]] : []),
      ['all', 'All', all.length],
      ['done', 'Answered', (c.auto || 0) + (c.confirmed || 0)
                           + (c.kept || 0) + (c.moved || 0)],
      ['same', 'Already aligned', all.filter((r) => r.same && !r.locked).length],
      // Lock: the ones held where Braces put them.
      ...(all.some((r) => r.locked)
        ? [['locked', 'Locked by Braces', all.filter((r) => r.locked).length]]
        : []),
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
          : filter === 'overlap'
            ? 'No two stamps share a time. Nothing is standing in the way '
              + 'of banking this.'
            : 'Nothing in that pass.' }));
      return card;
    }

    const tb = el('tbody');
    for (const [r, n] of got.slice(0, 400)) {
      const said = callFor(n);
      /* An overlap outranks whatever else the row has to say. Every other
         state here is a description; this one is the reason the set cannot
         be banked, and it usually sits on a row that already reads as
         answered -- somebody moved a stamp, which is what caused it. */
      const clash = overlapping(n);
      tb.appendChild(el('tr', {
        class: clash ? 'flagged'
          : ((r.flag && !said) ? 'flagged' : (said ? 'said' : '')),
        onclick: () => openBench(n),
      }, [
        el('td', { class: 'st', html: r.locked
          ? '<span class="br-lock-ico sm">' + LOCK_SVG + '</span>'
          : clash
          ? '<span class="flagmark">⚑</span>'
          : (said
             ? (said === 'keep' ? '<span class="dim">—</span>'
                : '<span class="tick">✓</span>')
             : (r.flag ? '<span class="flagmark">⚑</span>'
                : '<span class="tick">✓</span>')) }),
        el('td', { text: clock(r.was) }),
        el('td', { text: r.peak == null ? 'unmoved' : clock(r.now) }),
        el('td', { text: ms(r.shift_ms) }),
        el('td', { text: r.peak_uv == null ? '—'
                         : String(Math.round(r.peak_uv)) }),
        el('td', { class: 'br-why', text: r.locked ? REASONS.locked
          : clash
          ? REASONS.overlap
          : (said
             ? (said === 'keep' ? 'left where it was'
                : said === 'move' ? 'moved by hand' : 'confirmed')
             : (REASONS[r.flag] || '')) }),
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

  /* How many stamps a bank would move: a row moves if what it would land
     on differs from where it started. Counted the way the write counts it
     -- `bracesset.settled`, rule for rule. A row whose peak is where it
     already sits (`same`) stays even when `now` is a sample off: counting
     it here is what banked a Lock set that moved nothing and came back
     "accepted as vnull" (2026-10-30). */
  function pendingMoves() {
    const s = set_ && set_.set;
    if (!s) return 0;
    return (s.rows || []).filter((r, i) => {
      const said = callFor(i);
      if (said === 'keep' || said === 'garbage') return false;
      const prop = (r.now != null && !r.same) ? r.now : r.was;
      const to = (said === 'move' && (s.calls || {})[String(i)])
        ? (s.calls || {})[String(i)].t
        : said === 'confirm' ? prop
          : r.flag ? r.was : prop;
      return Math.abs(to - r.was) > 1e-9;
    }).length;
  }

  /* Whether banking would write anything: a stamp moved, one thrown out
     here, or -- the first time these stamps are aligned at all -- nothing
     moved, which is still the alignment Root Canal waits for. */
  function pendingWrite() {
    const s = set_ && set_.set;
    if (!s) return false;
    if (pendingMoves()) return true;
    if ((s.rows || []).some((r, i) => callFor(i) === 'garbage')) return true;
    return set_.source_aligned === false;
  }

  /* Banked without being asked (2026-10-21: "autobank is a constant
     everywhere, and when you leave"), as Checkup, Spotter and Panning do:
     once every flagged stamp has its call, and on leaving the trace view.
     The same write as Bank it, so nothing new writes nothing; a proposal
     with calls still waiting is said, not banked half-decided. */
  function autoBank(why) {
    if (BARRY.testNoAutobank || busy || !set_ || !set_.set
        || set_.set.committed) return;
    if (!pendingWrite()) return;
    /* A first alignment that moves nothing banks when the last call is
       made, never on leaving: an old proposal opened and left again --
       every stamp held, the set aligned since by another run -- would
       otherwise be written as a branch nobody asked for. */
    if (why === 'leave' && !pendingMoves()
        && !(set_.set.rows || []).some((r, i) => callFor(i) === 'garbage')) {
      return;
    }
    const rows = set_.set.rows || [];
    const waiting = rows.filter((r, i) => r.flag && !callFor(i)).length;
    if (waiting) {
      if (why === 'leave') {
        toast('Not banked yet: ' + waiting + ' stamp'
              + (waiting === 1 ? ' is' : 's are') + ' still waiting for a '
              + 'call. ' + cfg.name + ' banks it by itself once they are decided.',
              null, 7000);
      }
      return;
    }
    commit(true);
  }

  function acceptBar(c) {
    const s = set_.set;
    const bar = el('div', { class: 'br-accept' });
    if (s.committed) return bar;
    const waiting = c.waiting || 0;
    const nextV = vName(set_.entry, 'next_name');
    /* Whether there is anything to write, said BEFORE the button is
       pressed. A set whose every stamp is already on its peak is a good
       set and a common one -- and offering "Bank it" on it, only to come
       back with "there is nothing to write", makes a finished set look
       like a failed one. Counted the way the write counts it: a row moves
       if what it would land on differs from where it started. */
    const moves = pendingWrite();
    bar.appendChild(el('button', {
      class: 'btn',
      disabled: moves ? null : 'disabled',
      text: moves ? 'Bank it as ' + nextV + '…' : 'Nothing to bank',
      title: moves
        ? (pendingMoves() ? 'Shows exactly what would be written before '
                            + 'writing it'
          : 'Nothing moves, but these stamps have not been aligned before: '
            + 'banking records that they are, so Root Canal can read them')
        : 'Every stamp is already where the recording puts it, so a new '
          + 'version would hold exactly what the last one does',
      onclick: () => commit(false),
    }));
    /* THE ONE THING THAT WILL STOP THE WRITE, said before the button is
       pressed rather than after. Two stamps on one time is a duplicate and
       the bank refuses it, so a proposal carrying one cannot be banked --
       and finding that out from a red toast at the end is how a person
       learns to distrust the button rather than the pair of stamps. */
    const clash = c.overlap || 0;
    if (clash) {
      bar.appendChild(el('span', { class: 'warn-line', text:
        clash + ' stamp' + (clash === 1 ? '' : 's') + ' share a time with '
        + 'another stamp, which is one event written twice. This cannot be '
        + 'banked until one of each pair moves.' }));
      bar.appendChild(el('button', {
        class: 'btn sm', text: 'Show me',
        title: 'The overlapping stamps, in the pass of their own',
        onclick: () => { filter = 'overlap'; render(); },
      }));
    }
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
  ].concat(cfg.pin ? [{ id: 'locked', name: 'held, not moved',
                        color: '#9db8ff' }] : []);

  const vRows = () => (view && set_ && set_.set.rows) || [];
  /* SEEN IS NOT STEPPED (2026-10-19). "We should be able to SEE all
     spikes, but only go next/previous to the ones needing a decision."
     Every stamp is drawn, at full strength, whatever the pass; the pass
     only decides where n / p and the arrows stop. A stop wears a cap (▼)
     on the traces, so you can see which ones the arrows will land on, and
     a press on any other stamp goes to it.

     Which stamps the pass walks. An overlapping row is wanted even when it
     arrived unflagged and has been answered: it is the one state a person
     has to come back to, so stepping must not walk past it. `i` is the row
     number -- every caller passes it, because `filter`, `findIndex` and
     `forEach` all hand it over anyway. */
  const vWanted = (r, i) => (!view || view.only === 'all')
    ? true : (!!r.flag || !!overlapping(i));
  const vAt = () => vRows()[view.at] || null;
  const vWaiting = (i) => !!(vRows()[i] || {}).flag && !callFor(i);

  async function enter() {
    const s = set_ && set_.set;
    if (!s) return false;
    // One aligner's review at a time: the other's, left open, is ended
    // first, or both would hear every key and draw on one recording.
    for (const other of makeBraces.all) {
      if (other !== api_ && other._view()) other._exitView();
    }
    const path = set_.session_path;
    if (!path) {
      toast('The recording this set came from is not reachable from this '
            + 'machine, so there is nothing to look at.', 'err', 9000);
      return false;
    }
    // One mode at a time, or two toolbars and two key handlers stack on
    // top of each other -- every other one, Panning included (2026-10-26:
    // Panning's bar for M22 s3 sat under Lock's for M1 s2).
    if (BARRY.modes) BARRY.modes.leaveAllBut(cfg.mode);

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
    /* Stepping stops at the decisions whenever the set has any --
       answered ones too, so a second look walks the same stops -- and at
       every stamp only when there is nothing to decide at all. */
    const stops = (s.rows || []).some((r, i) => r.flag || overlapping(i));
    view = { sess: sess, at: 0, rev: 0, curve: curvePref(),
             only: stops ? 'flag' : 'all' };
    {
      // The traces' band: the last one looked at here, else the run's.
      let tb = null;
      try { tb = BARRY.prefs.get(TRACE_KEY(), null); } catch (e) { tb = null; }
      const lo = Number((((s.params || {}).band) || [5])[0]);
      view.traceBand = (tb === 'ds' || tb === 'ied' || tb === 'both') ? tb
        : (lo < 3 ? 'ied' : 'ds');
    }
    /* THIS WINDOW OWNS THE MARKS.
       `xplore`'s live loop skips the window that is running a curation and
       calls `adoptCuration` on every other one -- and `adoptCuration` with
       nothing on the channel DELETES `curationMarks`. Without this flag the
       marks were published and then wiped a second later by the sync,
       which is why the trace view never changed. */
    sess.curation = { kind: 'braces', index: 0, set: set_.set };
    setMode(cfg.mode, exitView);
    vLayout();
    vGrab();
    // The traces through the band last looked at (Lock's always; Braces'
    // only when it is not the dentate-spike band the recording is read in).
    if (cfg.bands || view.traceBand !== 'ds') setTraceBand(view.traceBand);
    step('laid out', { view: BARRY.state.view });

    // Land on something the pass actually contains. Guarded: a throw here
    // used to take the bar and the marks with it and leave the mode half
    // open with no sign of why.
    try {
      // The first one still waiting, then the first stop of any kind.
      let first = vRows().findIndex((r, i) => vWaiting(i));
      if (first < 0) first = vRows().findIndex(vWanted);
      vGoTo(first >= 0 ? first : 0);
    } catch (err) {
      step('failed', { why: String((err && err.message) || err) });
      toast(cfg.name + ' could not draw on this recording: '
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
    /* The main window as Profile › Support panel preferences laid it out
       (2026-10-22), or the traces alone; the traces stay first. */
    const mp = BARRY.supportPanels
      ? BARRY.supportPanels.applyMain(cfg.panels, [{ panel: 'traces' }], view.sess,
                                      { col: 0.5, row: 0.5 })
      : (BARRY.views.xplore.setPanes([{ panel: 'traces' }], { col: 0.5, row: 0.5 }), null);
    // Profile's span, on every entry (a zoom here still changes it after).
    if (mp && mp.span) {
      try { BARRY.prefs.set(SPAN_KEY, mp.span); } catch (e) { /* session */ }
    }
    if (!vAids()) {
      /* The second window was blocked, and a blocked pop-up is how this
         mode ends up looking like it did nothing at all: the traces open,
         four panels do not, and there is no way to tell that from broken.
         So the aids come into THIS window instead. Cramped, and it says so
         -- but cramped is a thing somebody can work with and absent is
         not. */
      /* The main window's own choice is undone first, so its drawn layout
         does not land on a different set of panes; the fallback is then
         the traces and the second window's panels, as chosen. */
      if (BARRY.supportPanels) BARRY.supportPanels.restoreMain(true);
      const aidSpecs = (vAids.lastSpecs || [{ panel: 'csd' }, { panel: 'theta' },
                                           { panel: 'voltage' }]).slice(0, 7);
      BARRY.views.xplore.setPanes([{ panel: 'traces' }].concat(aidSpecs),
                                  { col: 0.5, row: 0.5 });
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
    const defaults = [
      { panel: 'csd' },
      { panel: 'theta' },
      { panel: 'voltage' },
      { panel: 'spectrogram', tfChannels: every8, tfMode: 'stack',
        fmin: 1, fmax: 250 },
    ];
    // What this person chose (Profile › Support panel preferences); off is
    // off, and nothing is crammed into the main window for it.
    const plan = BARRY.supportPanels
      ? BARRY.supportPanels.plan(cfg.panels, defaults, view.sess)
      : { specs: defaults };
    if (!plan) return true;
    vAids.lastSpecs = plan.specs;
    aidWin = BARRY.views.xplore.popOutPanes(view.sess, plan.specs, {
         ...(BARRY.supportPanels ? BARRY.supportPanels.opts(plan) : {}),
         role: 'aids', name: 'barry-' + cfg.tool + '-aids', width: 720, height: 1000,
         // Folded on arrival, as Checkup's are: these four are for glancing
         // at, and the headers and control strips cost more of a short pane
         // than they are worth.
         chrome: 'notabs,noheads,nostrip,nochannels' });
    return !!aidWin;
  }

  /* `opts.handoff`: another mode is being entered, and will say which view
     to show. */
  function exitView(opts) {
    if (!view) return;
    const handoff = !!(opts && opts.handoff);
    /* THE WAY OUT ALWAYS HAPPENS.

       Everything in the `try` is tidying: shut the aid window, hand back
       the pointer, drop the marks, take the bar off the screen. Everything
       in the `finally` is the way back to the proposal -- the key handler,
       the mode, the view -- and it runs whether or not the tidying did.

       This is not defensive programming for its own sake. `view` was set
       to null and then read four lines later, which threw, and the three
       lines after the throw were exactly the ones that bring the panel
       back: somebody pressing "Back to the proposal" stayed in the trace
       view with no way to reach the button that banks it. A half-tidied
       view is untidy; a panel nobody can get back to is somebody's
       afternoon. */
    try {
      if (aidWin && !aidWin.closed) {
        try { aidWin.close(); } catch (e) { /* it may already be gone */ }
      }
      aidWin = null;
      if (BARRY.views.xplore.grabTime) BARRY.views.xplore.grabTime(null);
      // The list is a modal, and it outlives the mode otherwise -- a
      // dialog of somebody else's stamps over the next view. Closed while
      // `view` still exists, which is the whole of the bug above.
      if (view.list) { view.list = false; closeModal(); }
      if (view.sess) {
        delete view.sess.curation;
        delete view.sess.curationMarks;
        if (view.sess.dual && BARRY.views.xplore.setDual) {
          BARRY.views.xplore.setDual(view.sess, null);
        }
        // Tell the other window the mode is over, or it keeps drawing
        // marks for a proposal nobody is looking at any more.
        if (BARRY.views.xplore.publishCuration) {
          BARRY.views.xplore.publishCuration(view.sess, null);
        }
      }
      if (BARRY.views.xplore.redraw) BARRY.views.xplore.redraw();
      const app = document.getElementById('app');
      if (app) app.classList.remove('mode-settling');
      const bar = document.getElementById('brViewBar');
      if (bar) bar.remove();
    } catch (e) {
      // Said, not swallowed: this should not happen, and if it does the
      // next person to see it should have something to go on.
      try {
        BARRY.activity.log('braces.exit', {
          step: 'tidying failed',
          why: String((e && e.message) || e),
        });
      } catch (e2) { /* the log is not worth a second failure */ }
    } finally {
      closeEnterAsk();
      closeCrowded();
      closeLockedSay();
      view = null;
      document.removeEventListener('keydown', vKeys, true);
      // A main window laid out from Profile goes back to its one pane.
      if (BARRY.supportPanels) BARRY.supportPanels.restoreMain();
      setMode(null);
      if (!handoff) setView('toolkit');
      // Banked on the way out, after the view has gone (autoBank).
      setTimeout(() => autoBank('leave'), 0);
    }
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
      /* EVERY STAMP IS DRAWN, in either pass (2026-10-15).

         "Needing a decision" used to leave every stamp outside the pass
         -- every one Braces was sure of -- out of the marks altogether. So
         the little bars showing where the other spikes are came and went
         with whether the set still had a flag open, and a stamp could be
         dragged onto a neighbour nobody could see. The pass decides which
         stamps the arrows step through (`vWanted`), not which exist.

         `o` says a stamp is not a stop. Since 2026-10-19 it is drawn at
         full strength all the same -- "we should be able to SEE all
         spikes" -- and it is the stops that are marked, with a cap. */
      // A locked stamp is never a stop: there is nothing to decide on it.
      const outside = (view.only === 'flag' && !r.flag && !overlapping(i))
        || !!r.locked;
      const mine = r === cur;
      const said = callFor(i);
      // What the dashed half says: answered, still being asked about, or
      // nobody has looked.
      // Held, unless somebody overrode the hold and moved or tossed it.
      const st = (r.locked && said !== 'garbage' && said !== 'move') ? 'locked'
        : said === 'garbage' ? 'garbage'
        : (said === 'confirm' || said === 'move') ? 'confirmed'
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
        evs.push({ start: r.was, k: 'now', st: st, f: mine ? 1 : 0, r: i,
                   o: outside ? 1 : 0 });
        return;
      }
      evs.push({ start: r.was, k: 'was', st: st, f: mine ? 1 : 0, r: i,
                 o: outside ? 1 : 0 });
      evs.push({ start: to, k: 'now', st: st, f: mine ? 1 : 0, r: i,
                 o: outside ? 1 : 0 });
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
        // The second band over the traces, for the support window too.
        dual: view.sess.dual || null,
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
    // Then a placement waiting on "are you sure" -- or being yoinked back.
    if (view && view.pending && view.pending.row === n) return view.pending.t;
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
    const span = vSpan();
    /* Centred on where the stamp WAS, not where it is proposed to go
       (2026-10-30): the search window is ±window_ms around the original,
       so a span of twice that shows the whole of it -- centred on the
       proposal, a peak near one edge put half the window off screen. */
    BARRY.views.xplore.setWindow(0, Math.max(0, r.was - span / 2), span);
    view.spanSet = true;
    vPublish();
    vBar();
  }

  /* THE SPAN IS YOURS (2026-10-13).

     Every move used to set the trace view's span again, to eight windows
     across -- 1.6 s at ±200 ms -- so a view zoomed to 1 s was undone by
     every step to the next flagged stamp. Now a move centres the stamp and
     leaves the width alone: whatever the pane shows is the span, kept from
     one stamp to the next and from one sitting to the next.

     Eight windows across is only where the very first review opens, so the
     neighbours that made a run contested are on screen beside it. The pane
     is read only once this review has centred something itself: before
     that it shows whatever was being browsed. `braces_span` is a local
     preference (backend/store.py PREFS_LOCAL), as Checkup's is: how wide
     somebody likes the window is about their screen. */
  const SPAN_KEY = 'braces_span';

  function vPaneSpan() {
    try {
      // Xplorefinder's own two cases (`winOf`): an unlinked pane carries
      // its own window, a linked one reads the session's.
      const XF = BARRY.views.xplore.state;
      const pane = (XF.panes || [])[0];
      const s = (XF.linkMode === 'none' && pane && pane.t0 != null)
        ? pane.span : (view && view.sess ? view.sess.span : null);
      return s > 0 ? s : null;
    } catch (e) {
      return null;
    }
  }

  function vSpan() {
    const kept = parseFloat(BARRY.prefs.get(SPAN_KEY, 0)) || 0;
    let span = kept > 0 ? kept
      : Math.max(0.4, ((set_.set.params || {}).window_ms || 100) / 1000 * 8);
    // Zoomed since the last stamp: that is the width wanted now. Only a
    // real change counts, as in Checkup -- the pane can round what it was
    // given, or clamp it at the end of the recording.
    const shown = view && view.spanSet ? vPaneSpan() : null;
    if (shown && Math.abs(shown - span) > Math.max(0.02, span * 0.02)) {
      span = shown;
    }
    if (Math.abs(span - kept) > 1e-6) {
      try { BARRY.prefs.set(SPAN_KEY, span); } catch (e) { /* ignore */ }
    }
    return span;
  }

  function vStep(d) {
    const all = vRows();
    let i = view.at + d;
    while (i >= 0 && i < all.length) {
      if (vWanted(all[i], i)) { vGoTo(i); return; }
      i += d;
    }
    const what = view.only === 'flag' ? 'needing a decision' : 'in this set';
    toast(d > 0 ? 'That is the last one ' + what + '.'
                : 'That is the first one ' + what + '.', null, 3500);
  }

  /* Moving one by hand. The marks repaint as it goes, so the line you are
     dragging is the line you are looking at. */
  async function vMove(deltaMs) {
    const r = vAt();
    if (!r) return;
    if (isHeld(view.at)) {
      lockedSay(view.at, 'move', () => vMove(deltaMs));
      return;
    }
    const t = Math.round((vNow(r) + deltaMs / 1000) * 1e6) / 1e6;
    await vDrop(view.at, vNow(r), t);
  }

  async function vSay(call) {
    const r = vAt();
    if (!r || accepted()) return;
    if ((call === 'move' || call === 'garbage') && isHeld(view.at)) {
      lockedSay(view.at, call, () => vSay(call));
      return;
    }
    await decide(view.at, call);
    vPublish();
    vNextOpen();
  }

  /* Straight on to the next one that still wants an answer, which is what
     makes a pass a pass rather than a list -- and when there is none left
     anywhere in the set, the pass is done, and that is said properly. */
  function vNextOpen() {
    if (!view) return;
    const all = vRows();
    for (let i = view.at + 1; i < all.length; i++) {
      if (vWaiting(i)) { vGoTo(i); return; }
    }
    /* None after it, but one skipped before it: back round to that one,
       said, rather than stopping as if the pass were done (2026-10-19). */
    for (let i = 0; i < view.at; i++) {
      if (vWaiting(i)) {
        toast('Back round to the first one still waiting, at '
              + clock(all[i].was) + '.', null, 4000);
        vGoTo(i);
        return;
      }
    }
    vBar();
    if (passDone()) { celebrate('pass'); autoBank('done'); }
  }

  /* ENTER AFTER A DRAG (2026-10-14).

     Enter is "Braces is right": it confirms the proposed peak. After
     somebody has dragged the green line somewhere on purpose, Enter took
     their spot away without a word -- the stamp jumped back to the
     proposal and the pass moved on. So when the stamp in view has been
     moved by hand, Enter asks first, and says how far the stamp would go:
     Enter again keeps their spot and moves on, R takes the recommended
     one, Esc does nothing. */
  let enterAsk = null;

  function vEnter() {
    const r = vAt();
    if (!r || (view && view.drag) || accepted()) return;
    const said = (set_.set.calls || {})[String(view.at)] || {};
    const prop = r.now == null ? r.was : r.now;
    const mine = (view.placed && view.placed.row === view.at) ? view.placed.t
      : (said.call === 'move' ? said.t : null);
    if (mine == null || Math.abs(mine - prop) < 5e-7) {
      vSay('confirm');
      return;
    }
    askEnter(mine, prop);
  }

  /* How far, in words: "15.0 ms later than your spot". */
  function enterWords(mine, prop) {
    const d = (prop - mine) * 1000;
    return Math.abs(d).toFixed(1) + ' ms ' + (d > 0 ? 'later' : 'earlier');
  }

  function askEnter(mine, prop) {
    closeEnterAsk();
    const at = view.at;
    const keep = () => { closeEnterAsk(); if (view && view.at === at) vNextOpen(); };
    const back = () => { closeEnterAsk(); if (view && view.at === at) vSay('confirm'); };
    const how = enterWords(mine, prop);
    const box = el('div', { class: 'br-enter-ask', role: 'alertdialog',
                            'aria-labelledby': 'brEnterAskT' }, [
      el('strong', { id: 'brEnterAskT',
                     text: 'Enter moves it back to the recommended spot' }),
      el('p', { text: 'You put this stamp at ' + clock(mine) + ' s. Enter on '
        + 'its own confirms where ' + cfg.name + ' recommends, ' + clock(prop)
        + ' s, which moves it away from your spot.' }),
      el('div', { class: 'br-enter-move' }, [
        el('b', { text: how }),
        el('span', { text: 'than where you put it' }),
      ]),
      el('div', { class: 'br-enter-acts' }, [
        el('button', { class: 'btn', onclick: keep }, [
          el('span', { text: 'Keep my spot' }), el('kbd', { text: 'Enter' })]),
        el('button', { class: 'btn ghost', onclick: back }, [
          el('span', { text: 'Use the recommended spot' }),
          el('kbd', { text: 'R' })]),
        el('button', { class: 'btn ghost sm', onclick: closeEnterAsk }, [
          el('span', { text: 'Cancel' }), el('kbd', { text: 'Esc' })]),
      ]),
    ]);
    document.body.appendChild(box);
    enterAsk = { box, keep, back, row: at, ms: (prop - mine) * 1000 };
    try { box.querySelector('.btn').focus({ preventScroll: true }); } catch (e) { /* ok */ }
  }

  function closeEnterAsk() {
    if (!enterAsk) return;
    const b = enterAsk.box;
    enterAsk = null;
    if (b && b.parentNode) b.parentNode.removeChild(b);
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

  /* THE STAMP UNDER A PRESS, if there is one (2026-10-19): any stamp but
     the one in view, either of its two lines, within HIT_PX on the pane
     pressed. Seconds per pixel from the pane itself, so it is the same
     few pixels at any zoom. */
  const HIT_PX = 6;
  function stampAt(t, index) {
    const X = BARRY.views.xplore.clientAtTime;
    if (!X || !view) return null;
    const a = X(t, index);
    const b = X(t + 0.01, index) || X(t - 0.01, index);
    if (!a || !b || Math.abs(b.x - a.x) < 1e-6) return null;
    const tol = HIT_PX * 0.01 / Math.abs(b.x - a.x);
    let best = null, bestD = tol;
    vRows().forEach((r, i) => {
      if (i === view.at) return;
      for (const tt of [r.was, vNow(r)]) {
        const d = Math.abs(tt - t);
        if (d <= bestD) { bestD = d; best = i; }
      }
    });
    return best;
  }

  function vGrab() {
    if (!BARRY.views.xplore.grabTime) return;
    BARRY.views.xplore.grabTime({
      onStart: (t, index) => {
        const r = vAt();
        if (!r) return false;
        // Within a window of the one being decided, or it is somebody
        // panning rather than aiming.
        const reach = ((set_.set.params || {}).window_ms || 100) / 1000;
        if (Math.abs(t - vNow(r)) > reach) {
          /* Out there, a press ON another stamp goes to it: every spike is
             drawn, so any of them can be looked at, stop or not. The
             gesture is kept (nothing pans) and no drag starts. Inside the
             reach a press still drags the one in view -- that is how a
             stamp is put down, even beside a neighbour. */
          /* Not while something is being asked about the one in view,
             or the glove is pulling it back: the question and the yoink
             are about THAT stamp, and going elsewhere under them would
             leave them answering for a stamp nobody is looking at. */
          if (enterAsk || closeAsk || lockedAsk || yoinking || view.pending) {
            return false;
          }
          const hit = stampAt(t, index);
          if (hit == null) return false;
          vGoTo(hit);
          return true;
        }
        // A held stamp is not picked up: it says so, and nothing moves
        // unless the hold is overridden -- then it is picked up next time.
        if (isHeld(view.at)) {
          lockedSay(view.at, 'move', () => {
            toast('Overridden: this one can be dragged now.', null, 4000);
          });
          return true;
        }
        view.drag = { row: view.at, t: vNow(r), last: 0, from: vNow(r) };
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
        const from = view.drag.from;
        const at = Math.round(t * 1e6) / 1e6;
        view.drag = null;
        await vDrop(row, from, at);
      },
    });
  }

  /* A stamp put down by hand: on top of another one it asks first
     (`crowds`); anywhere else it is decided at once. */
  async function vDrop(row, from, at) {
    if (!view) return;
    if (isHeld(row)) {
      vPublish();
      lockedSay(row, 'move', () => vDrop(row, from, at));
      return;
    }
    if (accepted()) { vPublish(); return; }
    const near = crowds(row, from, at);
    if (near) { crowdedReview(row, from, at, near); return; }
    // Held while the decision is on its way, so an Enter pressed the
    // instant the button comes up still knows the stamp was placed.
    view.placed = { row, t: at };
    await decide(row, 'move', at);
    if (view && view.placed && view.placed.row === row) view.placed = null;
    vPublish();
    vBar();
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
    if (!view || !set_ || accepted()) return;
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
      // A move onto a time its neighbour already holds flags both of them,
      // and moving either off unflags both -- so this is re-read on every
      // decision rather than only when the set is opened.
      set_.overlaps = got.overlaps;
      readOverlaps(got.overlaps);
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
      /* First, because it outranks everything else a row can be. The
         states below describe what was decided; this one says the decision
         cannot be written, and it is nearly always sitting on a row that
         otherwise reads as finished. A row called garbage is not written
         at all, so it can never be one of a pair. */
      if (overlapping(x.i)) return 'overlap';
      if (x.r.locked) return 'locked';
      if (said === 'garbage') return 'garbage';
      if (said === 'move') return 'moved';
      if (said === 'confirm') return 'confirmed';
      if (said === 'keep') return 'kept';
      return x.r.flag ? 'flagged' : 'auto';
    };
    const STATE_NAME = {
      moved: 'moved by hand', confirmed: 'confirmed', kept: 'left alone',
      flagged: 'needs a decision', auto: 'moving, unflagged',
      garbage: 'not an event', overlap: 'shares a time',
      locked: 'held, not moved',
    };
    const STATE_COLOUR = {
      moved: '#5cc98d', confirmed: '#5cc98d', kept: '#ED8B33',
      flagged: '#ED8B33', auto: 'var(--line)', garbage: '#d9534f',
      // Not the red that means "removed" and not the orange that means
      // "unanswered": a third thing, so the eye can find the pair in a
      // list of twelve hundred.
      overlap: '#c678dd',
      locked: '#9db8ff',
    };

    const tally = {};
    for (const x of rows) {
      const k = stateOf(x);
      tally[k] = (tally[k] || 0) + 1;
    }

    const wrap = el('div', { class: 'modal cur-list-modal' });
    wrap.appendChild(el('div', { class: 'mh' }, [
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
    for (const id of ['overlap', 'flagged', 'auto', 'confirmed', 'moved',
                      'kept', 'garbage'].concat(cfg.pin ? ['locked'] : [])) {
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
                       overlapping(x.i) ? REASONS.overlap : '',
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
        title: st === 'overlap'
          ? REASONS.overlap
            + (overlapMate(x.i) != null
               ? ' — stamp #' + (overlapMate(x.i) + 1) : '')
          : (x.r.flag ? (REASONS[x.r.flag] || x.r.flag)
                      : 'Nothing was flagged about this one'),
        onclick: () => { closeModal(); view.list = false; vGoTo(x.i); },
      }, [
        el('span', { class: 'cl-n', text: '#' + (x.i + 1) }),
        el('span', { class: 'cl-t', text: clock(x.r.was) }),
        el('span', { class: 'cl-move', text: ms(d) + ' ms' }),
        el('span', { class: 'cl-lab', text: STATE_NAME[st] }),
        el('span', { class: 'cl-who',
                     text: st === 'overlap'
                       ? (overlapMate(x.i) != null
                          ? 'with #' + (overlapMate(x.i) + 1) : REASONS.overlap)
                       : (x.r.flag ? (REASONS[x.r.flag] || x.r.flag) : '') }),
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
    wrap.appendChild(el('div', { class: 'mf' }, [
      el('div', { style: 'flex:1' }),
      el('button', { class: 'btn', text: 'Close',
                     onclick: () => { view.list = false; closeModal();
                                      vBar(); } }),
    ]));
    paint();
    showModal(wrap, { replace: true });
  }

  /* Asking twice, in words that change.

     One fixed sentence read four hundred times stops being read at all --
     which is the failure mode of every confirmation dialog ever written.
     These vary, they all say the same thing, and the thing they say is
     "this was curation's job and you are doing it here". */
  const GARBAGE_ASK = [
    'You already had a chance to mark this as garbage, %s. Are you really '
      + 'sure about this? Really really sure?',
    '%s. You saw this one in Checkup. You looked right at it. And now, '
      + 'here, at this hour, it is garbage? Are you certain? Genuinely '
      + 'certain?',
    'This went past you once already, %s. Nobody is counting. Are you '
      + 'sure? Are you sure you are sure?',
    'Right, %s \u2014 so the plan is to reject it NOW, is it? After it was '
      + 'offered to you, with a keyboard shortcut, in a tool built for '
      + 'exactly this. Really? Really really?',
    'A curated set, %s. Curated. By a person. Recently. And yet. Are you '
      + 'quite sure? Quite quite sure?',
  ];

  const GARBAGE_YES = [
    'Huh. I guess. Really should have been taken care of in the last step, '
      + 'but I suppose we can make an exception.',
    'Fine. Fine! It is not as though there is a whole tool for this. It is '
      + 'gone from the aligned version.',
    'Noted, with feeling. Out it goes \u2014 and the earlier versions still '
      + 'have it, so nobody has to take my word for any of this.',
    'Well. Nobody is perfect. Certainly not at the hour most of this gets '
      + 'done. Consider it rejected.',
    'I shall add it to the list of things that were definitely going to be '
      + 'handled in Checkup. It is out.',
    'Against my better judgement, which is not saying much at this point. '
      + 'Done.',
  ];

  const pick = (list) => list[Math.floor(Math.random() * list.length)];

  /* Who is being asked. The person, by the name their work is filed
     under, because "you already had your chance" needs somebody to be
     about. */
  function whoAmI() {
    try {
      const me = (BARRY.state && BARRY.state.me) || {};
      return me.name || me.user || BARRY.who || 'you';
    } catch (e) { return 'you'; }
  }

  /* Marking one as not an event after all. Two dialogs: the first asks,
     the second agrees to it and then does it. */
  function vGarbage() {
    if (!view) return;
    const r = vAt();
    if (!r) return;
    // Not relabelled either, unless the hold is overridden: Panning called
    // it a spike, Braces placed it.
    if (isHeld(view.at)) { lockedSay(view.at, 'garbage', vGarbage); return; }
    if (accepted()) return;
    const n = view.at;
    if (callFor(n) === 'garbage') {
      // Already rejected: the button takes it back, and putting something
      // back needs no persuading. `decide(null)` rather than `vSay`,
      // because vSay steps on to the next one and undoing is a thing you
      // do to the stamp in front of you.
      decide(n, null).then(() => { vPublish(); vBar(); });
      return;
    }
    ask('Mark this stamp as garbage?',
        el('div', {}, [
          el('p', { text: pick(GARBAGE_ASK).replace('%s', whoAmI())
                                .replace(/Checkup/g, cfg.passTool) }),
          el('p', { class: 'hint', text:
            'It is the stamp at ' + clock(r.was) + '. It will not be moved '
            + 'and it will not be in the banked version \u2014 an aligned '
            + 'version holds the spikes and nothing else. Every earlier '
            + 'version still has it exactly as it was.' }),
        ]),
        'Yes, it is garbage',
        () => {
          ask('If you insist.',
              el('div', {}, [
                el('p', { text: pick(GARBAGE_YES).replace(/Checkup/g,
                                                          cfg.passTool) }),
              ]),
              'Okay',
              async () => { await vSay('garbage'); },
              false);
        },
        true);
  }

  function vBar() {
    if (!view) return;
    let bar = document.getElementById('brViewBar');
    if (!bar) {
      bar = el('div', { class: 'cur-bar br-view-bar', id: 'brViewBar' });
      /* In the middle of the one mode bar (core.js `BARRY.modeSlot`,
         2026-10-20): the shell draws the mode's name, Simplify, ? and
         Leave at its ends, and Leave calls `exitView`. */
      BARRY.modeSlot().appendChild(bar);
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
    /* Where this one is: among the stops, and among every stamp -- every
       one is on the traces, so the count says how many there are. */
    const stop = vWanted(r, view.at);
    const where = view.only === 'all'
      ? 'stamp ' + (view.at + 1) + ' of ' + all.length
      : (stop ? 'decision ' + seen + ' of ' + n
              : 'no decision needed here')
        + '  ·  stamp ' + (view.at + 1) + ' of ' + all.length;

    bar.appendChild(el('div', { class: 'cur-where' }, [
      el('strong', { text: s.name || cfg.name }),
      el('span', { class: 'cur-sub', text:
        clock(r.was) + '  →  ' + clock(vNow(r))
        + '   ' + ms((vNow(r) - r.was) * 1000) + ' ms'
        /* The overlap first and instead: it is the only thing here that
           stops the set being banked, and the stamp it collides with is
           the thing a person needs named -- it is drawn underneath this
           one, a tenth of a millisecond away, where nothing on the trace
           can tell them apart. */
        + (r.locked ? '   ·   ' + (r.origin ? groupName(r.origin) + ', '
                                                 : '') + REASONS.locked
             + (r.fills != null ? ', holding the peak at ' + clock(r.fills)
                                : ', no peak under it')
           : overlapping(view.at)
           ? '   ·   ' + REASONS.overlap
             + (overlapMate(view.at) != null
                ? ' (stamp ' + (overlapMate(view.at) + 1) + ')' : '')
           : (r.flag ? '   ·   ' + (REASONS[r.flag] || r.flag) : '')) }),
      el('span', { class: 'cur-count', text: where }),
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
                              : r.locked ? 'held where it is'
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
    /* Not an event after all.

       Last, and in the colour of a thing that removes something, because
       it is the only control here that changes WHAT the set contains
       rather than where something in it sits. */
    acts.appendChild(el('button', {
      class: 'cur-cat' + (said === 'garbage' ? ' on' : '')
             + (isHeld(view.at) ? ' br-is-locked' : ''),
      style: '--cat:#d9534f',
      title: said === 'garbage'
        ? 'Take that back \u2014 it goes back to being a spike   (g)'
        : isHeld(view.at)
          ? 'Held where it is. Asks before overriding the hold.   (g)'
          : 'Not ' + W.aOne + ' at all. Asks first.   (g)',
      onclick: vGarbage,
    }, [
      el('kbd', { text: 'g' }),
      el('span', {}, [
        el('b', { text: said === 'garbage' ? 'Not garbage' : 'Garbage' }),
        el('i', { text: said === 'garbage' ? 'put it back'
                                           : 'not an event' }),
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
    /* Banked: nothing here can be decided any more (see `accepted`), so
       the answers give way to saying so. Stepping through still works. */
    bar.appendChild(s.committed
      ? el('div', { class: 'cur-cats br-acts' }, [
          el('span', { class: 'cur-sub', text: 'Banked as version '
            + s.committed.version + '. This pass is its record and does '
            + 'not change; run ' + cfg.name + ' again to change a stamp.' })])
      : acts);

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
      /* Which band the traces are drawn through: the dentate-spike one,
         the IED one, or both side by side (2026-10-26). */
      el('div', { class: 'ctl br-opt' }, [
        el('label', { text: 'Traces' }),
        el('div', { class: 'seg sm br-trace-seg' }, [
          ['ds', 'DS band', 'The traces through the dentate-spike filter'],
          ['ied', 'IED band', 'The traces through the IED filter'],
          ['both', 'Both', 'Two trace panes side by side, one through each'],
        ].map(([id, label, tip]) => el('button', {
          class: view.traceBand === id ? 'active' : '',
          title: tip + (bandText(id) ? ' (' + bandText(id) + ')' : ''),
          onclick: () => { setTraceBand(id); vBar(); },
          text: label,
        }))),
        view.traceBand === 'both' ? el('span', { class: 'br-dual-key' }, [
          el('i', { style: 'background:' + BARRY.token('--trace', '#7FE3B0') }),
          el('span', { text: bandText('ds') }),
          el('i', { style: 'background:' + BARRY.token('--trace-2', '#FF7AC8') }),
          el('span', { text: bandText('ied') }),
        ]) : null,
      ].filter(Boolean)),
      el('div', { class: 'ctl br-opt' }, [
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
      el('div', { class: 'ctl br-opt' }, [
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
      /* WHERE n / p STOP, not what is shown (2026-10-19). It was "Show",
         and every stamp is drawn whichever is picked. */
      el('div', { class: 'ctl br-opt' }, [
        el('label', { text: 'Step through' }),
        el('div', { class: 'seg sm br-step-seg' }, [
          ['flag', 'Needing a decision',
           'n / p and the arrows stop only at the ones needing a decision '
           + '(▼ on the traces). Every stamp is still drawn; press any of '
           + 'them to go to it.'],
          ['all', 'Every stamp',
           'n / p and the arrows stop at every stamp in the set.'],
        ].map(([id, label, tip]) => el('button', {
          class: view.only === id ? 'active' : '',
          title: tip,
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
            if (!vWanted(vAt(), view.at)) {
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
         ])).concat(view.only === 'flag' ? [el('span', {
           class: 'br-browse-sw br-stop-sw' }, [
           el('b', { style: 'color:' + DRAW.ask, text: '▼' }),
           el('span', { text: 'n / p stop here' }),
         ])] : [])),
      el('div', { style: 'flex:1' }),
      /* Its own end: the rare, sweeping one under More. Back to the
         proposal is the shell's Leave now, last on the bar. */
      BARRY.ui.modeEnd ? BARRY.ui.modeEnd({ more: [
        el('button', { class: 'btn ghost sm br-undo-all',
                       text: 'Undo every decision',
                       title: 'Clears the whole pass. The proposal itself is '
                            + 'untouched.',
                       onclick: vUndoAll }),
      ] }) : el('button', { class: 'btn ghost sm br-undo-all',
                            text: 'Undo every decision', onclick: vUndoAll }),
    ]));
  }

  function vKeys(e) {
    if (!view) return;
    const k = e.key.toLowerCase();
    // The question about a dragged stamp has the keys while it is up.
    if (enterAsk) {
      if (k === 'enter') enterAsk.keep();
      else if (k === 'r') enterAsk.back();
      else if (k === 'escape') closeEnterAsk();
      else return;
      e.preventDefault();
      e.stopPropagation();
      return;
    }
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
    if (k === 'n' || k === 'arrowright') vStep(1);
    else if (k === 'p' || k === 'arrowleft') vStep(-1);
    else if (k === 'enter') vEnter();
    else if (k === 'k') vSay('keep');
    else if (k === '[') vMove(-1);
    else if (k === ']') vMove(1);
    else if (k === 'g') vGarbage();
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
       everything else       a tick down from the top and one up from
                             the bottom, at full strength, stop or not
       a stop for n / p      a cap (▼) on the top edge
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
    bin: '#d9534f',        // not an event after all
    lock: '#9db8ff',       // held where Braces put it (Lock)
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
    // The marks' strength, handed in by the pane (Marks > Faded).
    const A = ctx.globalAlpha;
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
      /* A rejected stamp is red on BOTH halves -- it is not going
         anywhere and it is not being written, so drawing its new
         position in the colour of an accepted move would be a lie. */
      const colour = e.st === 'garbage' ? DRAW.bin
        : e.st === 'locked' ? DRAW.lock
        : e.k === 'now' ? DRAW.now
        : (e.st === 'confirmed' ? DRAW.ok
           : (e.st === 'flagged' ? DRAW.ask : DRAW.was));
      if (focus) {
        // Full height, and drawn last would be better still -- but there
        // are only two of them and forty of everything else, so a wider
        // line is enough to find them.
        ctx.globalAlpha = A;
        ctx.lineWidth = 2;
        ctx.setLineDash(e.k === 'now' ? [] : [3, 2]);
        ctx.strokeStyle = colour;
        ctx.beginPath();
        ctx.moveTo(x, topY);
        ctx.lineTo(x, botY);
        ctx.stroke();
        continue;
      }
      ctx.globalAlpha = (0.72) * A;
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
    ctx.globalAlpha = A;
    ctx.setLineDash([]);
    return true;
  }

  function draw(ctx, sess, win, x0, plotW, y0, plotH, P) {
    // The marks' strength, handed in by the pane (Marks > Faded).
    const A = ctx.globalAlpha;
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
      ctx.globalAlpha = A;
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
          ctx.globalAlpha = A;
          ctx.lineJoin = 'round';
          ctx.lineWidth = 3.4;
          ctx.strokeStyle = 'rgba(0,0,0,0.72)';
          ctx.stroke();
          ctx.lineWidth = 2;
          ctx.strokeStyle = '#ffe08a';
          ctx.stroke();
        }
        ctx.restore();
        ctx.globalAlpha = A;
      }
    }

    for (const e of evs) {
      if (e.start < t0 || e.start > t1) continue;
      const x = X(e.start);
      const focus = !!e.f;
      /* A neighbour is a tick from the bottom; the pair being decided
         runs the full height.

         Curation's proportions, not invented ones -- 18% of the pane,
         38% when the pane is short enough that 18% would be a few pixels
         -- so stepping from Checkup to Braces is the same picture with
         different colours rather than a second thing to learn.

         This was briefly removed, and the reason is worth remembering: a
         mark's size depends on a flag that travels between windows, and
         while that flag was going astray every mark drew as a neighbour,
         which made a panel look EMPTY rather than slightly wrong. Size
         can carry the focus again because the focus now arrives -- as a
         number on every pointer, and marks that arrive are adopted
         whatever the receiver thinks it already knows. */
      const small = plotH < 150;
      /* SEEN, EVERY ONE (2026-10-19). A neighbour was one short tick at
         the bottom -- 18% of the pane, drawn quieter still when it was
         not in the pass -- and on a busy raster, under the curve, that
         is nothing at all. Now it is two: down from the top and up from
         the bottom, each a quarter of the pane, so a stamp is found from
         either edge and the data between stays clear. The one being
         decided still runs the whole height. */
      const tick = plotH * (small ? 0.34 : 0.25);
      const spans = focus ? [[y0, y0 + plotH]]
        : [[y0, y0 + tick], [y0 + plotH - tick, y0 + plotH]];
      /* A rejected stamp is red on BOTH halves -- it is not going
         anywhere and it is not being written, so drawing its new
         position in the colour of an accepted move would be a lie. */
      const colour = e.st === 'garbage' ? DRAW.bin
        : e.st === 'locked' ? DRAW.lock
        : e.k === 'now' ? DRAW.now
        : (e.st === 'confirmed' ? DRAW.ok
           : (e.st === 'flagged' ? DRAW.ask : DRAW.was));
      const dashed = e.k !== 'now';

      /* A line that survives whatever is under it: a dark and a light
         hairline either side, the same trick the curation marks and the
         time gridlines use. On every mark, as curation does it -- a tick
         over a jet raster is exactly as invisible as a full-height line
         over one, and these are the ticks somebody is scanning for. */
      for (const [top, bottom] of spans) {
        ctx.setLineDash([]);
        ctx.lineWidth = focus ? 1.5 : 1;
        ctx.globalAlpha = (0.55) * A;
        ctx.strokeStyle = 'rgba(0,0,0,0.9)';
        ctx.beginPath(); ctx.moveTo(x - 1, top); ctx.lineTo(x - 1, bottom);
        ctx.stroke();
        ctx.strokeStyle = 'rgba(255,255,255,0.9)';
        ctx.beginPath(); ctx.moveTo(x + 1, top); ctx.lineTo(x + 1, bottom);
        ctx.stroke();
      }

      /* Curation's weights too: the one being decided is wider and fully
         opaque, a neighbour that has been answered is nearly so, and one
         nobody has looked at is quieter still and dashed. */
      /* Not quieter for being outside the pass, nor for nobody having
         looked: where it goes solid and nearly opaque, where it was
         dashed and a little less. */
      ctx.globalAlpha = (focus ? 1 : (dashed ? 0.8 : 0.92)) * A;
      ctx.setLineDash(dashed ? [4, 3] : []);
      ctx.lineWidth = focus ? 2.5 : 1.8;
      ctx.strokeStyle = colour;
      for (const [top, bottom] of spans) {
        ctx.beginPath();
        ctx.moveTo(x, top);
        ctx.lineTo(x, bottom);
        ctx.stroke();
      }

      /* A STOP: a cap on the top edge, once per stamp (on its "goes
         here" line), in the colour of what it is waiting for -- amber
         while it needs an answer, green once it has one, red when it was
         called garbage. What the arrows will land on, seen before they
         land on it. */
      if (!focus && !e.o && e.k === 'now') {
        const capCol = e.st === 'garbage' ? DRAW.bin
          : (e.st === 'confirmed' || e.st === 'kept') ? DRAW.ok : DRAW.ask;
        ctx.setLineDash([]);
        ctx.globalAlpha = A;
        ctx.beginPath();
        ctx.moveTo(x - 6, y0 + 1);
        ctx.lineTo(x + 6, y0 + 1);
        ctx.lineTo(x, y0 + 10);
        ctx.closePath();
        ctx.fillStyle = capCol;
        ctx.fill();
        ctx.lineWidth = 1;
        ctx.strokeStyle = 'rgba(0,0,0,0.85)';
        ctx.stroke();
      }
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
      ctx.globalAlpha = (0.9) * A;
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
      ctx.globalAlpha = (0.85) * A;
      ctx.fillStyle = 'rgba(0,0,0,0.65)';
      ctx.fillRect(mx - w / 2 - 3, y - 14, w + 6, 11);
      ctx.globalAlpha = A;
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
    // Where it was when the bench opened: what a yoink puts it back to.
    bench.from = bench.t;
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
      el('strong', { html: r.locked
        ? '<span class="br-lock-ico sm">' + LOCK_SVG + '</span> ' + REASONS.locked
        : (r.flag ? '<span class="flagmark">⚑</span> '
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
      el('button', { class: 'btn sm', text: 'Confirm',
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
    if (isHeld(n) && moved) {
      const want = bench.t;
      bench.t = r.was;
      drawBench();
      lockedSay(n, 'move', () => {
        if (!bench || bench.n !== n) return;
        bench.t = want;
        answer(call);
      });
      return;
    }
    const near = (call === 'confirm' && moved) ? crowds(n, bench.from, bench.t) : null;
    if (near) {
      crowdedBench(n, near);
      return;
    }
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
    // One skipped before it is gone back to, as in the review.
    for (let i = 0; i < from; i++) {
      if (all[i].flag && !callFor(i)) {
        toast('Back round to the first one still waiting, at '
              + clock(all[i].was) + '.', null, 4000);
        openBench(i);
        return;
      }
    }
    bench = null;
    render();
    if (passDone()) { celebrate('pass'); autoBank('done'); }
    else toast('That was the last one in this pass.', null, 4000);
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
                 + ((s.params || {}).band || [5, 100]).map(Number).join('–')
                 + ' Hz, mains out'
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
    if (isHeld(bench.n)) {
      lockedSay(bench.n, 'move', () => {
        toast('Overridden: this one can be dragged now.', null, 4000);
      });
      return;
    }
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
    /* "Are you sure, bud?" has the keys while it is up, and nothing moves
       while a stamp is being yoinked. First of the two key handlers (this
       one is registered at load, the review's on entering it), and
       IMMEDIATE, so the review's own Enter never also fires. */
    if (lockedAsk) {
      const k0 = e.key.toLowerCase();
      // Tab reaches "… anyway", and Enter on it is the override.
      const onAnyway = lockedAsk.anyway && document.activeElement
        && document.activeElement.classList.contains('ghost')
        && lockedAsk.box.contains(document.activeElement);
      if (k0 === 'tab') return;
      if ((k0 === 'enter' || k0 === ' ') && onAnyway) lockedAsk.anyway();
      else if (k0 === 'enter' || k0 === 'escape' || k0 === ' ') closeLockedSay();
      e.preventDefault();
      e.stopImmediatePropagation();
      return;
    }
    if (closeAsk || yoinking) {
      const k0 = e.key.toLowerCase();
      if (closeAsk && k0 === 'enter') closeAsk.keep();
      else if (closeAsk && k0 === 'escape') closeAsk.back();
      e.preventDefault();
      e.stopImmediatePropagation();
      return;
    }
    // The other aligner's bench, left open behind this one, hears nothing.
    if (!bench || !set_ || !mine() || otherReviewing()) return;
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
    const s = set_.set;
    const r = s.rows[bench.n];
    const k = e.key.toLowerCase();
    if (k === 'enter') { answer('confirm'); }
    else if (k === 'k') { answer('keep'); }
    else if (k === '0') { bench.t = r.now == null ? r.was : r.now;
                          render(); }
    else if ((k === '[' || k === ']') && isHeld(bench.n)) {
      const n = bench.n;
      lockedSay(n, 'move', () => {
        if (!bench || bench.n !== n) return;
        bench.t = Math.round((bench.t + (k === '[' ? -0.001 : 0.001)) * 1e6)
                  / 1e6;
        drawBench();
      });
    }
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
    /* "There is nothing to write" is an outcome, not a failure.

       A set whose every stamp is already on its peak is a good set, and a
       set looked at twice says this the second time. It used to come back
       as a red error, which reads as something having gone wrong with a
       proposal that is simply finished. */
    if (rep.nothing_to_do) {
      toast(rep.why || 'Every stamp is already where the recording puts '
            + 'it, so there is nothing to bank.', null, 8000);
      return;
    }
    if (rep.error) {
      toast(rep.error, 'err', 9000);
      /* A refusal naming rows is a refusal somebody can act on, so it puts
         them on those rows. In the bench, on the first of them; in the
         panel, on the pass that holds all of them. */
      if ((rep.overlaps || []).length) {
        readOverlaps(rep.overlaps);
        const first = rep.overlaps[0].rows[0];
        // Overlapping stamps are stops in either pass.
        if (view) { vGoTo(first); vBar(); }
        else { filter = 'overlap'; render(); }
      }
      return;
    }
    if (apply === true) {
      toast('Banked as version ' + rep.version + '. ' + rep.moved
            + ' stamp' + (rep.moved === 1 ? '' : 's') + ' moved.', 'ok', 7000);
      celebrate('banked', rep);
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



  /* ==================================================================
     On top of another one (2026-10-15)
     ================================================================== */
  /* A STAMP PUT DOWN ON TOP OF ANOTHER ONE.

     Two dentate spikes do not sit on top of each other: a spike is twenty
     milliseconds or so wide, and the detector these stamps came from never
     puts two closer than its own spacing (`dist_ms`, 100 ms). A stamp
     dragged onto a neighbour is nearly always a slip -- the wrong line
     grabbed, or a drag that ran on. So the screen shakes and asks. "Keep it
     there" places it as asked. "Place it somewhere else" sends a glove in to
     grab it and yank it back to where it was, and you put it down again.

     Only when the placement MAKES the pair: a stamp that was already that
     close to the same neighbour is not asked about again for every nudge.
     The bank's own rule -- two stamps on exactly one time cannot be written
     at all -- is still the overlap flag (`bracesset.overlaps`). */
  const TOO_CLOSE_MS = 20;

  /* Where row i will be written, the way `bracesset.settled` works it out. */
  function landsAt(i) {
    const r = ((set_ && set_.set.rows) || [])[i];
    if (!r) return null;
    const said = (set_.set.calls || {})[String(i)] || {};
    const prop = (r.now != null && !r.same) ? r.now : r.was;
    if (said.call === 'move') return said.t;
    if (said.call === 'garbage') return null;
    if (said.call === 'keep') return r.was;
    if (said.call === 'confirm') return prop;
    if (r.flag) return r.was;
    return prop;
  }

  /* The nearest other stamp within TOO_CLOSE_MS of `t`: where it will be
     written, and in the review where its line is drawn too. */
  function nearest(n, t) {
    const rows = (set_ && set_.set.rows) || [];
    let best = null;
    for (let i = 0; i < rows.length; i++) {
      if (i === n || callFor(i) === 'garbage') continue;
      const spots = [landsAt(i)];
      if (view) spots.push(vNow(rows[i]));
      for (const at of spots) {
        if (at == null) continue;
        const d = Math.abs(at - t) * 1000;
        if (d < TOO_CLOSE_MS && (!best || d < best.ms)) best = { i, ms: d, t: at };
      }
    }
    return best;
  }

  function crowds(n, from, to) {
    if (to == null) return null;
    const now = nearest(n, to);
    if (!now) return null;
    const was = from == null ? null : nearest(n, from);
    return (was && was.i === now.i) ? null : now;
  }

  let closeAsk = null;
  let yoinking = false;

  function eventWords() {
    const rq = (((set_ || {}).set || {}).params || {}).request || {};
    return rq.kind === 'ied' ? 'these 2 discharges'
      : rq.kind === 'pooled' ? 'these 2 spikes' : 'these 2 dentate spikes';
  }

  function shake() {
    if (BARRY.ui.reducedMotion && BARRY.ui.reducedMotion()) return;
    const app = document.getElementById('app') || document.body;
    app.classList.remove('br-shake');
    void app.offsetWidth;                   // so a second shake starts over
    app.classList.add('br-shake');
    setTimeout(() => app.classList.remove('br-shake'), 560);
  }

  /* A LOCKED STAMP, TRIED (Lock, 2026-10-22).

     "If someone tries to move it say... no second guessing. That's a bad
     scientific habit. You follow the protocol as best you can. And then
     you move on." Said once, plainly, and eased up: the screen gives a
     small shake, the padlock says it, Enter carries on.

     A WARNING, NOT A WALL (2026-10-30: "two spikes side by side, and I am
     not allowed to garbage this one? ... the warning is good, but not being
     able to toss this is a problem"). `go` is what was being tried, and
     "... anyway" does it. The row then stays overridden for the rest of
     this proposal, so nudging it a millisecond at a time does not ask
     again on every key, and the calls it sends carry `override` -- which
     the server wants (`bracesset.LOCKED_SAY`) and keeps on the call. */
  let lockedAsk = null;
  let overrode = { set: null, rows: new Set() };
  const isLocked = (i) => !!(((set_ && set_.set && set_.set.rows) || [])[i]
                             || {}).locked;
  // Here, or on a call the server kept with the override on it.
  const overridden = (i) => !!(set_ && (
    (overrode.set === set_.set.set_id && overrode.rows.has(i))
    || ((set_.set.calls || {})[String(i)] || {}).override));
  // Held, and nobody has chosen to override it in this proposal.
  const isHeld = (i) => isLocked(i) && !overridden(i);

  /* `n` the row, `what` 'move' or 'garbage', `go` the thing to do once the
     hold is overridden. Without `go` it is the old notice, and Enter is
     the only way on. */
  function lockedSay(n, what, go) {
    closeLockedSay();
    shake();
    const r = (set_ && set_.set.rows[n])
      || (vRows()[view ? view.at : -1])
      || (bench && set_ ? set_.set.rows[bench.n] : null) || {};
    const anyway = () => {
      closeLockedSay();
      if (set_) {
        if (overrode.set !== set_.set.set_id) {
          overrode = { set: set_.set.set_id, rows: new Set() };
        }
        overrode.rows.add(n);
      }
      go();
    };
    const box = el('div', { class: 'br-enter-ask br-close-ask br-locked-ask',
                            role: 'alertdialog', 'aria-labelledby': 'brLockedT' }, [
      el('div', { class: 'br-locked-ico', html: LOCK_SVG }),
      el('strong', { id: 'brLockedT', text: 'That one’s held' }),
      el('p', { class: 'br-close-q', text:
        (r.origin ? groupName(r.origin) + ' is' : 'Its group is')
        + ' held in this alignment: already lined up, so it stays where it '
        + 'is unless you override it.' }),
      el('p', { text: 'No second-guessing — follow the protocol as well as '
        + 'you can, then move on. If the result isn’t up to par, the fix is '
        + 'a better protocol, not a nudge by hand.' }),
      el('div', { class: 'br-enter-acts' }, [
        el('button', { class: 'btn', onclick: closeLockedSay }, [
          el('span', { text: go ? 'Leave it held' : 'Fair enough' }),
          el('kbd', { text: 'Enter' })]),
        go ? el('button', { class: 'btn ghost', onclick: anyway,
                            title: 'Override the hold on this one stamp. The '
                                 + 'call is kept with a note that the hold '
                                 + 'was overridden.' }, [
          el('span', { text: what === 'garbage' ? 'Garbage it anyway'
                                                : 'Move it anyway' })])
          : null,
      ].filter(Boolean)),
    ]);
    document.body.appendChild(box);
    lockedAsk = { box, anyway: go ? anyway : null };
    try { box.querySelector('.btn').focus({ preventScroll: true }); } catch (e) { /* ok */ }
  }

  function closeLockedSay() {
    if (!lockedAsk) return;
    const b = lockedAsk.box;
    lockedAsk = null;
    if (b && b.parentNode) b.parentNode.removeChild(b);
  }

  /* "Are you sure, bud?" -- `o` is { n, near, keep, back }. */
  function askCrowded(o) {
    closeCrowded();
    shake();
    const dist = Number((((set_ && set_.set) || {}).params || {}).dist_ms || 100);
    const box = el('div', { class: 'br-enter-ask br-close-ask', role: 'alertdialog',
                            'aria-labelledby': 'brCloseAskT' }, [
      el('strong', { id: 'brCloseAskT', text: 'Are you sure, bud?' }),
      el('p', { class: 'br-close-q', text: 'You’re telling me ' + eventWords()
                                           + ' were really that close?' }),
      el('div', { class: 'br-enter-move' }, [
        el('b', { text: o.near.ms.toFixed(1) + ' ms' }),
        el('span', { text: 'between stamp #' + (o.n + 1) + ' and stamp #'
                           + (o.near.i + 1) }),
      ]),
      el('p', { text: 'The detector these came from never puts two closer '
                      + 'than ' + Math.round(dist) + ' ms.' }),
      el('div', { class: 'br-enter-acts' }, [
        el('button', { class: 'btn', onclick: () => closeAsk && closeAsk.keep() }, [
          el('span', { text: 'Keep it there' }), el('kbd', { text: 'Enter' })]),
        el('button', { class: 'btn ghost', onclick: () => closeAsk && closeAsk.back() }, [
          el('span', { text: 'Place it somewhere else' }),
          el('kbd', { text: 'Esc' })]),
      ]),
    ]);
    document.body.appendChild(box);
    closeAsk = {
      box, n: o.n, near: o.near,
      keep: () => { closeCrowded(); o.keep(); },
      back: () => { closeCrowded(); o.back(); },
    };
    try { box.querySelector('.btn').focus({ preventScroll: true }); } catch (e) { /* ok */ }
  }

  function closeCrowded() {
    if (!closeAsk) return;
    const b = closeAsk.box;
    closeAsk = null;
    if (b && b.parentNode) b.parentNode.removeChild(b);
  }

  /* In the review: the line stays where it was put while the question is
     up, and either lands there or is yoinked back to `from`. */
  function crowdedReview(row, from, at, near) {
    view.pending = { row, t: at };
    vPublish({ local: true });
    askCrowded({
      n: row, near,
      keep: async () => {
        if (!view) return;
        view.placed = { row, t: at };
        await decide(row, 'move', at);
        if (view) {
          view.pending = null;
          if (view.placed && view.placed.row === row) view.placed = null;
          vPublish();
          vBar();
        }
      },
      back: () => {
        const X = BARRY.views.xplore.clientAtTime || (() => null);
        const a = X(at, 0);
        const b = X(from, 0);
        yoink(a && {
          x: a.x, y: a.top + Math.min(120, (a.bottom - a.top) * 0.3),
          dx: b ? b.x - a.x : (from > at ? 140 : -140),
        }, (f) => {
          if (!view || !view.pending) return;
          view.pending.t = at + (from - at) * f;
          vPublish({ local: true });
          vBarTimes();
        }, () => {
          if (!view) return;
          view.pending = null;
          vPublish();
          vBar();
        });
      },
    });
  }

  /* On the bench: its own line, on its own canvas. */
  function crowdedBench(n, near) {
    const at = bench.t;
    const from = bench.from;
    askCrowded({
      n, near,
      keep: async () => {
        await decide(n, 'move', at);
        nextFlag(n);
      },
      back: () => {
        const cv = document.getElementById('brBench');
        const r = set_.set.rows[n];
        const win = ((set_.set.params || {}).window_ms || 100) / 1000;
        const t0 = r.was - win * 3, t1 = r.was + win * 3;
        const rect = cv ? cv.getBoundingClientRect() : null;
        const X = (t) => rect.left + ((t - t0) / (t1 - t0)) * rect.width;
        yoink(rect && { x: X(at), y: rect.top + Math.min(90, rect.height * 0.3),
                        dx: X(from) - X(at) }, (f) => {
          if (!bench || bench.n !== n) return;
          bench.t = Math.round((at + (from - at) * f) * 1e6) / 1e6;
          drawBench();
        }, () => {
          if (!bench || bench.n !== n) return;
          bench.t = from;
          drawBench();
          const head = document.querySelector('.br-bench-head .br-sub');
          if (head) {
            head.textContent = 'was ' + clock(r.was) + '   →   now '
              + clock(bench.t) + '   ·   ' + ms((bench.t - r.was) * 1000) + ' ms';
          }
        });
      },
    });
  }

  /* THE GLOVE. Down onto the line, a grab, YOINK -- the line goes with it,
     back to where it was -- then it stands up and wags its finger: "We
     ain't doing that", uh, uh, uh. Timers, not
     `animationend` (the harness runner's virtual time never ends one), and
     the line itself is moved by `step(f)`, f from 0 to 1, in step with the
     glove. `geo` is { x, y, dx } in client pixels, or null when the line is
     not on screen: then the line still goes back, with no glove. */
  const GLOVE_SVG = '<svg viewBox="0 0 90 120" aria-hidden="true">'
    + '<path class="g-thumb" d="M16 34c-10 2-14 13-7 22l11 13c3 4 9 2 9-3V42z"/>'
    + '<path class="g-palm" d="M22 20h46c5 0 8 4 8 8v30c0 9-7 15-15 15H31'
    + 'c-9 0-16-6-16-15V28c0-4 3-8 7-8z"/>'
    + '<g class="g-fingers">'
    + '<rect x="21" y="58" width="12" height="40" rx="6"/>'
    + '<rect x="34" y="60" width="12" height="47" rx="6"/>'
    + '<rect x="47" y="60" width="12" height="45" rx="6"/>'
    + '<rect x="60" y="58" width="11" height="36" rx="5.5"/></g>'
    + '<path class="g-line" d="M34 42v14M47 42v16M60 42v14"/>'
    + '<rect class="g-cuff" x="20" y="2" width="50" height="22" rx="8"/>'
    + '<path class="g-seam" d="M25 10h40M25 16h40"/>'
    + '</svg>';

  /* And the same glove upright, index finger up, for "uh uh uh": three
     fingers curled over the palm, the thumb across them, cuff at the
     wrist. Wagged from the wrist by `.br-glove-wag`'s own animation. */
  const WAG_SVG = '<svg viewBox="0 0 90 132" aria-hidden="true">'
    + '<rect class="g-palm" x="18" y="56" width="56" height="52" rx="15"/>'
    + '<rect class="g-index" x="22" y="6" width="15" height="60" rx="7.5"/>'
    + '<path class="g-line" d="M25 44h9"/>'
    + '<rect class="g-curl" x="37" y="52" width="13" height="18" rx="6.5"/>'
    + '<rect class="g-curl" x="49" y="54" width="13" height="17" rx="6.5"/>'
    + '<rect class="g-curl" x="61" y="57" width="12" height="16" rx="6"/>'
    + '<path class="g-thumb" d="M20 76c6-6 22-6 30 0 4 3 2 9-3 9H26c-6 0-10-5-6-9z"/>'
    + '<rect class="g-cuff" x="20" y="104" width="52" height="24" rx="8"/>'
    + '<path class="g-seam" d="M25 112h42M25 118h42"/>'
    + '</svg>';

  function yoink(geo, step, done) {
    const calm = BARRY.ui.reducedMotion && BARRY.ui.reducedMotion();
    yoinking = true;
    const finish = () => { yoinking = false; done(); };
    if (calm || !geo || !isFinite(geo.x) || !isFinite(geo.dx)) {
      step(1);
      finish();
      toast('We ain’t doing that. It is back where it was.', null, 4000);
      return;
    }
    const box = el('div', { class: 'br-yoink' }, [
      el('div', { class: 'br-hand' }, [
        el('div', { class: 'br-glove' }),
        // The same glove, upright, finger up -- shown once it has yanked.
        el('div', { class: 'br-glove-wag' }),
        el('div', { class: 'br-yoink-word', text: 'YOINK!' }),
      ]),
      el('div', { class: 'br-yoink-say' }, [
        el('div', { text: 'We ain’t doing that.' }),
        // One "uh" for each wag of the finger.
        el('div', { class: 'br-uh' }, [0, 1, 2].map((i) => el('span', {
          text: 'uh', style: '--i:' + i }))),
      ]),
    ]);
    box.querySelector('.br-glove').innerHTML = GLOVE_SVG;
    box.querySelector('.br-glove-wag').innerHTML = WAG_SVG;
    box.style.left = Math.round(geo.x) + 'px';
    box.style.top = Math.round(geo.y) + 'px';
    box.style.setProperty('--dx', Math.round(geo.dx) + 'px');
    box.classList.toggle('left', geo.dx < 0);
    document.body.appendChild(box);
    // Ease-in-back, the same curve the glove's own transition uses: a
    // little wind-up toward the neighbour, then the yank.
    const ease = (f) => f * f * (2.2 * f - 1.2);
    setTimeout(() => box.classList.add('grab'), 420);
    setTimeout(() => {
      box.classList.add('pull');
      const t0 = Date.now();
      const D = 520;
      const tick = () => {
        const f = Math.min(1, (Date.now() - t0) / D);
        step(ease(f));
        if (f < 1) setTimeout(tick, 16);
        else finish();
      };
      tick();
    }, 600);
    // Then upright, finger wagging: no, no, no -- uh, uh, uh.
    setTimeout(() => box.classList.add('say'), 1150);
    setTimeout(() => box.classList.add('out'), 2750);
    setTimeout(() => { if (box.parentNode) box.remove(); }, 3200);
  }

  /* ==================================================================
     Done (2026-10-14)
     ================================================================== */
  /* Every flagged stamp in the set has an answer. */
  function passDone() {
    if (!set_ || !set_.set) return false;
    const rows = set_.set.rows || [];
    let flagged = 0;
    for (let i = 0; i < rows.length; i++) {
      if (!rows[i].flag) continue;
      flagged += 1;
      if (!callFor(i)) return false;
    }
    return flagged > 0;
  }

  /* A SET FINISHED IS A SET FINISHED, AND IT GETS A MOMENT.

     A grinning tooth in braces, a burst of brackets, and one line from the
     list below -- a different one each time, never the same twice running.
     Once when the pass is done and once when it is banked, but not twice
     inside a minute for the same set: finishing and banking straight after
     is one moment, not two. Over in under three seconds, ended on a timer
     as well as by the animation (the harness runner's virtual time never
     ends one), clicked away at once, and only a fade where motion is
     turned down. */
  const HYPE = [
    'Lesgooo!', 'Yo that’s lit 🔥', 'Goated af 🐐', 'No cap, that’s aligned',
    'Slay. Every spike on its peak 💅', 'It’s giving… perfectly aligned',
    'Ate and left no crumbs', 'Sheesh 🥶', 'W review. Massive W.',
    'Main character energy 🦷✨', 'Understood the assignment',
    'Built different 💪', 'Absolute cinema 🎬', 'Bussin’ fr fr',
    'Big brain moves only 🧠', '+1000 aura', 'Periodt. 💅',
    'Straight teeth, straight stamps 😤', 'That’s fire, no 🧢',
    'Sigma grindset: complete', 'Vibe check: passed ✅', 'GG EZ',
    'Rizz level: orthodontist', 'Cooked. In the good way 🍳',
    'Era: aligned 📈', 'Touch grass? After this one.',
    'Not delulu, just aligned', 'Mewing with perfect braces 😮‍💨',
    'Every peak hit. Insane.', 'The brackets are bracketing 🔩',
    'Certified spike whisperer', 'Skibidi stamps, fully aligned',
  ];
  let lastHype = -1;
  const partied = {};

  const passParty = {};
  function celebrate(moment, rep) {
    const sid = set_ && set_.set ? set_.set.set_id : '';
    const now = Date.now();
    // The pass is celebrated once a sitting: answering one again later is
    // not finishing it again.
    if (moment === 'pass') {
      if (passParty[sid]) return;
      passParty[sid] = true;
    }
    if (partied[sid] && now - partied[sid] < 60000) return;
    partied[sid] = now;
    let i = Math.floor(Math.random() * HYPE.length);
    if (i === lastHype) i = (i + 1) % HYPE.length;
    lastHype = i;
    const s_ = set_ && set_.set ? set_.set : {};
    const c = (set_ && set_.counts) || {};
    const sub = moment === 'banked'
      ? 'Banked as v' + ((rep || {}).version != null ? rep.version : '?') + ' · '
        + ((rep || {}).moved || 0) + ' stamp' + (((rep || {}).moved === 1) ? '' : 's')
        + ' moved · ' + (s_.name || 'this set')
      : 'Every flagged stamp has an answer · ' + (s_.name || 'this set')
        + (c.moved != null ? ' · ' + c.moved + ' moved by hand' : '');
    party(HYPE[i], sub);
  }

  /* The tooth: a plain tooth shape, four brackets on a wire, and a grin. */
  const TOOTH_SVG = '<svg viewBox="0 0 120 120" aria-hidden="true">'
    + '<path class="t" d="M30 18c10-8 22-6 30 0 8-6 20-8 30 0 12 9 13 30 6 '
    + '50-4 12-6 34-14 34-7 0-8-16-12-26-2-5-6-5-8 0-4 10-5 26-12 26-8 '
    + '0-10-22-14-34-7-20-6-41 6-50z"/>'
    + '<path class="w" d="M24 56 Q60 66 96 56"/>'
    + '<rect class="b" x="27" y="50" width="11" height="11" rx="2"/>'
    + '<rect class="b" x="45" y="54" width="11" height="11" rx="2"/>'
    + '<rect class="b" x="64" y="54" width="11" height="11" rx="2"/>'
    + '<rect class="b" x="82" y="50" width="11" height="11" rx="2"/>'
    + '<circle class="e" cx="46" cy="36" r="4"/><circle class="e" cx="74" cy="36" r="4"/>'
    + '<path class="m" d="M48 76 Q60 86 72 76"/>'
    + '</svg>';

  function party(line, sub) {
    const old = document.querySelector('.br-party');
    if (old) old.remove();
    const calm = BARRY.ui.reducedMotion && BARRY.ui.reducedMotion();
    const bits = el('div', { class: 'br-party-bits', 'aria-hidden': 'true' });
    if (!calm) {
      const marks = ['🦷', '✨', '🔩', '⭐', '💯', '🔥'];
      for (let k = 0; k < 22; k++) {
        const a = (k / 22) * Math.PI * 2 + Math.random() * 0.3;
        const d = 140 + Math.random() * 160;
        const b = el('i', { text: k % 3 === 0 ? marks[k % marks.length] : '' });
        b.style.setProperty('--dx', Math.round(Math.cos(a) * d) + 'px');
        b.style.setProperty('--dy', Math.round(Math.sin(a) * d) + 'px');
        b.style.setProperty('--r', Math.round(Math.random() * 540 - 270) + 'deg');
        b.style.setProperty('--d', Math.round(Math.random() * 160) + 'ms');
        bits.appendChild(b);
      }
    }
    const tooth = el('div', { class: 'br-party-tooth' });
    tooth.innerHTML = TOOTH_SVG;
    const box = el('div', { class: 'br-party' + (calm ? ' calm' : ''),
                            role: 'status', 'aria-live': 'polite',
                            title: 'Click to carry on',
                            onclick: () => box.remove() }, [
      el('div', { class: 'br-party-card' }, [
        bits, tooth,
        el('div', { class: 'br-party-line', text: line }),
        el('div', { class: 'br-party-sub', text: sub }),
      ]),
    ]);
    document.body.appendChild(box);
    // Out, then gone -- on timers, not on `animationend`.
    setTimeout(() => box.classList.add('out'), 2300);
    setTimeout(() => { if (box.parentNode) box.remove(); }, 2800);
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

  /* Is the other aligner's review the one running? */
  function otherReviewing() {
    return makeBraces.all.some((o) => o !== api_ && o._view());
  }

  const api_ = {
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
    _reused: () => reused,
    _allSets: () => allSets,
    _goTo: (n) => vGoTo(n),
    _step: (d) => vStep(d),
    _stampAt: (t, index) => stampAt(t, index || 0),
    _wanted: () => vRows().map((r, i) => vWanted(r, i)),
    _exitView: () => exitView(),
    _enterAsk: () => (enterAsk ? { row: enterAsk.row, ms: enterAsk.ms,
                                   text: enterAsk.box.textContent } : null),
    _party: (line, sub) => party(line || HYPE[0], sub || ''),
    /* A drop, as the drag's release would make it, and what is asking. */
    _drop: (t) => vDrop(view.at, vNow(vAt()), Math.round(t * 1e6) / 1e6),
    _crowds: (n, from, to) => crowds(n, from, to),
    _closeAsk: () => (closeAsk ? { n: closeAsk.n, near: closeAsk.near,
                                   text: closeAsk.box.textContent } : null),
    _yoinking: () => yoinking,
    /* The question and the glove on their own, for a picture of them. */
    _askDemo: (n, i, msAway) => askCrowded({ n, near: { i, ms: msAway },
                                             keep: () => {}, back: () => {} }),
    _yoinkDemo: (x, y, dx) => yoink({ x, y, dx }, () => {}, () => {}),
    _tooCloseMs: TOO_CLOSE_MS,
    _hype: () => HYPE.slice(),
    _reset: () => { set_ = null; bench = null; cands = null; },
    /* The plan card drawn from a given plan, for web/_dev/vtreetools.html:
       a set with several readable versions is what the version tree is for,
       and the harness cannot count on one being reachable here. The plan
       on the module is put back. */
    _planCard: (p) => {
      const was = plan;
      plan = p;
      try { return planCard(); } finally { plan = was; }
    },
    /* The version tree for a set, as the picker's third tile pops it up,
       drawn in place for web/_dev/vtreetools.html. */
    _versionTree: (c) => el('div', { class: 'br-vers' }, [
      BARRY.ui.versionTree(Object.assign(versionOpts(c), {
        onpick: (v) => { q.from_version = v ? v.ref : null; },
      }))]),
    /* Lock: whether this run keeps Braces' stamps, and the dialog a
       locked stamp answers with. */
    _pinOn: () => pinOn(),
    _manyPin: (c) => manyPin(c),
    _holdNow: () => holdNow(),
    _manyHold: (c) => manyHold(c),
    _traceBand: () => (view ? view.traceBand : null),
    _setTraceBand: (id) => setTraceBand(id),
    _lockedSay: (n, what, go) => lockedSay(n, what, go),
    _lockedAsk: () => (lockedAsk ? lockedAsk.box.textContent : null),
    _closeLockedSay: () => closeLockedSay(),
    _cands: () => cands,
    _unsorted: () => unsorted,
    _chooseSet: (id) => chooseSet(id),
    _setMenu: () => setMenu,
    _cfg: cfg,
  };
  makeBraces.all.push(api_);
  // Registered with the others, so entering any mode leaves this one.
  if (BARRY.modes) {
    BARRY.modes.register(cfg.mode, {
      get active() { return !!view; },
      exit: () => exitView({ handoff: true }),
    });
  }
  return api_;
}
/* Every instance, so one can end the other's review (Braces and Lock). */
makeBraces.all = [];

/* The two aligners. Everything that differs between them is here. */
BARRY.braces = makeBraces({
  tool: 'braces', name: 'Braces', mode: 'braces', panels: 'braces',
  step: 'step 3 of The Dentist',
  type: 'ds',
  // Its Alignments list: its own sets. Eye's opened here until Eye became
  // Braces built a third time (2026-10-30); they are in Eye's list now.
  setTypes: 'ds',
  passTool: 'Checkup',
  pin: false,
  measures: [
    ['csd', 'CSD', 'The current source density across depth — the part of '
                   + 'the signal that cannot be volume-conducted'],
    ['voltage', 'Voltage', 'The magnitude of the filtered voltage, which is '
                           + 'what the detectors these stamps came from were '
                           + 'run on'],
  ],
  words: {
    blurb: 'Every stamp onto the peak it belongs to. A ±200 ms window, the '
         + 'DS-filtered magnitude, and one peak per stamp — so a spike '
         + 'that drifted early is not corrected by stealing the next '
         + 'one’s. Nothing is written until you accept it.',
    empty: 'Braces works on curated dentate-spike sets. Run Incisor to find '
         + 'the candidates, then go through them in Checkup — moving '
         + 'stamps nobody has vetted is work done twice, because the flags '
         + 'would be about events that get thrown away an hour later.',
    noneHere: 'Nothing curated is banked against this recording, so there are '
            + 'no stamps to align. Run Incisor to find the candidates and go '
            + 'through them in Checkup first — moving stamps nobody has '
            + 'vetted is work done twice, because the flags would be about '
            + 'events that get thrown away an hour later.',
    one: 'dentate spike', many: 'dentate spikes', aOne: 'a dentate spike',
    setWord: 'curated set',
    band: '5–100 Hz either way',
    versionSub: 'The stamps as they stand are read unless you pick an earlier '
              + 'version. Picking one branches off it; nothing after it is '
              + 'touched.',
    acrossShank: 'A dentate spike appears across most of the shank at the '
               + 'same instant,',
    measureWhy: (m) => (m === 'voltage'
      ? 'The filtered voltage is what Incisor and Toothy were themselves '
        + 'run on, so aligning to it reproduces the detector’s own '
        + 'criterion. '
      : 'The CSD is the second derivative across depth, so it is the part '
        + 'of the signal that cannot have come from somewhere else on the '
        + 'probe — a dentate spike is a current sink, and this is '
        + 'where the current went. Smoothed across depth first, or one '
        + 'noisy contact dominates a derivative. '),
  },
});

/* LOCK, step 3 of The Confluence (2026-10-22): Braces on a pooled set.

   Fed by Panning and nothing else -- "direct input from Junction makes no
   sense": a pool nobody has sorted is not offered, and Junction's own
   version of one is never a starting point. Braces' engine on the IED band
   (the backend reads the band from the kind), with Eye's third measure, and
   one thing Braces has no need of: the Incisor stamps Braces already placed
   are kept where they are (`pin`), switched on by itself wherever a set has
   any, per set in Many, and refused a move in the review. */
const LOCK_PRODUCER = (v, c) => (BARRY.ui.versionProducer
  ? BARRY.ui.versionProducer(v, c.pipeline, 'pooled') : null);

BARRY.lock = makeBraces({
  tool: 'lock', name: 'Lock', mode: 'lock', panels: 'lock',
  // Aligned through the dentate-spike band unless told otherwise.
  bands: true,
  step: 'step 3 of The Confluence',
  type: 'pooled',
  setTypes: 'pooled',
  passTool: 'Panning',
  pin: true,
  sorted: (c) => (c.versions || []).some((v) => LOCK_PRODUCER(v, c) === 'Panning'),
  notFrom: (v, c) => (LOCK_PRODUCER(v, c) === 'Junction'
    ? 'Junction’s raw pool, from before Panning sorted it. Lock lines up '
      + 'Panning’s results, so it never starts here.' : null),
  measures: [
    ['csd', 'CSD', 'The current source density across depth — the part of '
                   + 'the signal that cannot be volume-conducted'],
    ['voltage', 'Voltage', 'The magnitude of the filtered voltage, which is '
                           + 'what Incisor and Doppler were run on'],
    ['slope', 'Slope', 'Where the voltage changes fastest — a discharge’s '
                       + 'sharpest edge, which can be tens of milliseconds '
                       + 'before its largest excursion'],
  ],
  words: {
    blurb: 'Every pooled spike — Incisor’s and Doppler’s, sorted in '
         + 'Panning — onto the peak it belongs to, so Root Canal measures '
         + 'each one at the same instant. Choose which groups to line up — '
         + 'Incisor only, Merged, Doppler only — and the rest are held where '
         + 'they are. Nothing is written until you accept it.',
    empty: 'Lock lines up pooled sets once Panning has sorted them. Pool a '
         + 'recording in Junction, sort it in Panning and bank the result — '
         + 'an unsorted pool still has the garbage in it, and moving stamps '
         + 'nobody has vetted is work done twice.',
    noneHere: 'Nothing Panning has sorted is banked against this recording, '
            + 'so there are no spikes to line up. Pool it in Junction and '
            + 'sort it in Panning first.',
    one: 'spike', many: 'spikes', aOne: 'a spike',
    setWord: 'sorted pooled set',
    band: 'the dentate-spike band either way',
    versionSub: 'The stamps as they stand are read unless you pick an earlier '
              + 'version. Junction’s own version is greyed: Lock starts from '
              + 'what Panning sorted.',
    acrossShank: 'An event in the pool — a dentate spike or a discharge — '
               + 'appears across the shank at the same instant,',
    measureWhy: (m) => (m === 'voltage'
      ? 'The filtered voltage is what Incisor and Doppler were themselves '
        + 'run on, so aligning to it reproduces the detectors’ own '
        + 'criterion. '
      : m === 'slope'
        ? 'The slope is where the voltage changes fastest: a discharge with '
          + 'a slow after-going wave has its largest excursion tens of '
          + 'milliseconds after its sharpest edge, and this lines them up on '
          + 'the edge. '
        : 'The CSD is the second derivative across depth, so it is the part '
          + 'of the signal that cannot have come from somewhere else on the '
          + 'probe — where the current went. Smoothed across depth first, '
          + 'or one noisy contact dominates a derivative. Through the '
          + 'dentate-spike band by default; the IED band keeps a discharge’s '
          + 'slow wave, and is one press away under Filter. '),
  },
});

/* EYE, step 3 of The Storm (2026-10-30: "Update the Eye gui to match the
   flow and steps of braces"). Braces built a third time, as Lock was on
   2026-10-22: the same picker, run, Many, Alignments and review, on the
   discharges Spotter confirmed. It was its own panel (eye.js
   `makeAligner`), which read all three measures and compared them, and
   sent its proposals to Braces' review to be answered -- so the one step
   of three without a review of its own. The engine was always Braces'.

   No band choice: an IED is aligned through the IED band, which the server
   reads from the kind (`_braces_spec`), because the dentate-spike filter
   takes away the slow wave that is half of what a discharge is. */
BARRY.eye = makeBraces({
  tool: 'eye', name: 'Eye', mode: 'eye', panels: 'eye',
  step: 'step 3 of The Storm',
  type: 'ied',
  setTypes: 'ied',
  passTool: 'Spotter',
  pin: false,
  measures: [
    ['csd', 'CSD', 'The current source density across depth — the part of '
                   + 'the signal that cannot be volume-conducted'],
    ['voltage', 'Voltage', 'The magnitude of the filtered voltage, which is '
                           + 'what Doppler was run on'],
    ['slope', 'Slope', 'Where the voltage changes fastest — a discharge’s '
                       + 'sharpest edge, which can be tens of milliseconds '
                       + 'before its largest excursion'],
  ],
  words: {
    blurb: 'Every confirmed discharge onto the part of itself the others are '
         + 'on, so an average of them is of the event and not of the jitter. '
         + 'A ±200 ms window through the IED band, and one peak per stamp. '
         + 'Nothing is written until you accept it.',
    empty: 'Eye works on discharges Spotter has confirmed. Run Doppler to find '
         + 'the candidates and go through them in Spotter — a raw detector '
         + 'list has nothing worth moving, because half of it is thrown away '
         + 'an hour later.',
    noneHere: 'Nothing confirmed is banked against this recording, so there '
            + 'are no discharges to line up. Run Doppler and go through what '
            + 'it finds in Spotter first.',
    one: 'discharge', many: 'discharges', aOne: 'a discharge',
    setWord: 'confirmed set',
    band: 'the IED band',
    versionSub: 'The stamps as they stand are read unless you pick an earlier '
              + 'version. Picking one branches off it; nothing after it is '
              + 'touched.',
    acrossShank: 'A discharge appears across most of the shank at the same '
               + 'instant,',
    measureWhy: (m) => (m === 'voltage'
      ? 'The filtered voltage is what Doppler was itself run on, so aligning '
        + 'to it reproduces the detector’s own criterion. '
      : m === 'slope'
        ? 'The slope is where the voltage changes fastest: a discharge with a '
          + 'slow after-going wave has its largest excursion tens of '
          + 'milliseconds after its sharpest edge, and this lines them up on '
          + 'the edge. '
        : 'The CSD is the second derivative across depth, so it is the part '
          + 'of the signal that cannot have come from somewhere else on the '
          + 'probe. Smoothed across depth first, or one noisy contact '
          + 'dominates a derivative. '),
  },
});
