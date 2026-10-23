/* ==========================================================================
   rootcanal.js -- Root Canal, step four of The Dentist.

   A root canal is what a dentist does when the tooth looks fine from the
   outside and is not. Incisor's "dentate spikes" hide interictal discharges:
   an IED under a dentate-spike detector is a large, fast, sharp event, and
   Checkup and Braces never took them out, because nothing in those steps
   looks for them. This step does, so that X-ray, one step later, works on
   dentate spikes and nothing else.

   THE MEASUREMENT (decided with the user; see ROOTCANAL-SPEC.md)
   Three numbers per event, and a 2-class k-means in the space they make:

     max amplitude   on the contact with the largest |x - baseline| near
                     the stamp, from a real baseline, larger polarity wins
     half-width      full width at half amplitude on THAT contact
     HF power        v5's measure, the best contact's dB against its own
                     baseline -- in a band that is adjustable here

   Each axis is z-scored per recording before the clustering, and the
   cluster whose centre has the higher HF power is called IED. The server
   says which one it called and why, and the panel says it back.

   THE SHAPE OF THE PANEL
   The same three states X-ray has, and each has to finish before the next
   means anything:

     1. pick an aligned set, and a version to read it from
     2. read it -- minutes, once, cached (5 kHz; the snippets and spectra)
     3. the workbench: the space, three flat views of it, one event

   State 3, top to bottom, in the order it is used:

     the fit settings        filter, amp window, HF band; Recompute
     why, and Bank           the naming rule in a sentence; the one primary
     the picked event        which one, DS or IED, prev/next, Xplorefinder
     the space | flat views  3D on a canvas of our own; amp x hw, amp x
                             power, hw x power; drag a centre on any of them
     the event itself        trace, spectrum, stack + CSD

   Every control is above the pictures, so nothing you press is below the
   fold on a laptop. The pictures are what you scroll to if anything.

   WHY THE 3D IS HAND-BUILT
   There is no plotting library in this application and there is not going
   to be one for a scatter. An orthographic projection of three coordinates
   is a rotation and a scale -- a dozen lines -- and owning it is what lets
   the picking and the depth order be right rather than approximately right:
   a dot is picked where it is DRAWN, and the one drawn in front is the one
   you get. See `project` and `pickSpace`.

   WHAT IS CHEAP AND WHAT IS NOT
   The read is minutes and happens once per (recording, version). The fit
   is filter -> max contact -> amp/hw, band -> dB, z-score, k-means, naming,
   overrides, and is fast -- but not keystroke-fast over seven hundred
   events, so the SETTINGS wait for Recompute the way X-ray's box does,
   while a flip or a dragged centre, which are single deliberate acts,
   refit on release.
   ========================================================================== */
'use strict';

BARRY.rootcanal = (function () {
  /* The fit's defaults, in the units the API takes.

     1-100 Hz because that is what the lab's scripts measured amplitude and
     half-width on; 25 ms because it is v4's `--win-ms`; 500-1000 Hz because
     it is v5's band. All four are FIT params on the server: changing them
     re-filters the cached snippets and never re-reads the recording. */
  /* WHICH FILTER AMPLITUDE AND HALF-WIDTH ARE MEASURED ON -- four choices,
     the server's `rootcanal.FILTERS` mirrored here so the panel can name a
     preset before it has been fitted. A preset is its own numbers; only
     Custom reads the corner fields and the mains box. LFP stays the default
     so nothing already fitted moves under anyone. */
  const FILTERS = {
    none: { label: 'No filter', lo_hz: 0, hi_hz: 0, mains_out: false,
            title: 'The stored 2 kHz snippet as it is. Nothing taken out, '
                 + 'the 60 Hz mains included -- the baseline every other '
                 + 'choice is a change from.' },
    ds: { label: 'DS', lo_hz: 5, hi_hz: 100, mains_out: true,
          title: 'The dentate-spike filter: 5–100 Hz, the band Incisor found '
               + 'these on and X-ray measures them on, with the 60 Hz mains '
               + 'fitted out the way the CSD’s is.' },
    lfp: { label: 'LFP', lo_hz: 1, hi_hz: 100, mains_out: false,
           title: '1–100 Hz, the LFP / morphology band the epilepsy '
                + 'literature measures field-spike shape on '
                + '(ied_ds_lit.py). The mains is left in, as that band is '
                + 'used. This tool’s default since it was built.' },
    custom: { label: 'Custom', title: 'Your own corners, with the 60 Hz '
                                    + 'mains taken out or not.' },
  };
  const FILTER_ORDER = ['none', 'ds', 'lfp', 'custom'];
  const presetOf = (f) => (f && f !== 'custom' && FILTERS[f]) || null;

  const DEF = { filt: 'lfp', mains_out: true, k: 2, complete_only: false,
                lo_hz: 1, hi_hz: 100, win_ms: 25, band_lo: 500, band_hi: 1000,
                /* How far either side of the peak the half-amplitude
                   crossings are hunted. 50 ms is v1's own search; wider finds
                   the slow ones, and every event only found that way is
                   flagged `wide` rather than quietly counted as found. */
                cross_ms: 50 };
  const CROSS_MIN = 10, CROSS_MAX = 200, CROSS_V1 = 50;
  /* THE ANTI-ALIAS CORNER, NOT THE NYQUIST.

     The read is at 5 kHz, so 2500 Hz is its Nyquist -- but the band is not
     good up to there. `scipy.signal.decimate` puts its IIR low-pass corner
     at 0.8 of the new Nyquist, so the top fifth is already being cut on its
     way down. Measured on 24 real events against the raw 30 kHz: the two
     agree to within 0.27 dB up to 2000 Hz, and are 9.5 dB apart between
     2000 and 2500. A band edge above 2000 would be measuring the decimator,
     so the inputs stop there and the server refuses past it too. */
  const BAND_MAX = 2000;
  /* The snippets are decimated to 2 kHz and are +-250 ms. A low-pass corner
     much past 400 Hz stops meaning anything on them. Said, not enforced
     silently: the spec's own number. */
  const LP_MAX = 400;
  /* And the amp window is looked for inside the part of the snippet the
     click panel shows: `rootcanal.DISPLAY_MS`. */
  const WIN_MAX = 100;

  /* What is being asked for. Held here, not read off the DOM, so a redraw
     cannot lose a half-filled form. */
  const q = {
    entry: null,          // the chosen bank entry id
    from_version: null,   // a version ref, or null for "as it is now"
    gid: null,
    read: null,           // the read hash, once there is one
    filt: DEF.filt, mains_out: DEF.mains_out, k: DEF.k,
    complete_only: DEF.complete_only,
    lo_hz: DEF.lo_hz, hi_hz: DEF.hi_hz, win_ms: DEF.win_ms,
    band_lo: DEF.band_lo, band_hi: DEF.band_hi, cross_ms: DEF.cross_ms,
    /* Calls given by hand to whole clusters, by rank: {"2": "ied"}. Like a
       flip, applied at once rather than through Recompute. */
    cluster_calls: {},
    /* A saved margin to apply: { artifact_id, version, mode }. */
    margin: null,
    /* A saved border to classify by: { artifact_id, version, grace }. */
    border: null,
    /* Clusters drawn by hand with the lasso: [{ events: [i...], call }]. */
    drawn: [],
    /* Names given to clusters: {"<rank>": { name, type }} -- the type is the
       cluster's call. From the lab's list or typed (2026-10-06). */
    cluster_names: {},
    /* Events with no half-width, searched again with the widest search the
       read allows -- on request, one or all. A fit param. */
    retry: [],
    /* The two overrides, both FIT params so a result can be rebuilt from
       params alone: the event indices flipped by hand, and the centres in
       z-space (null means "k-means placed them"). */
    flips: [],
    centres: null,
  };

  /* The settings as TYPED, before Recompute.

     Separate from `q` on purpose. A flip refits at once, and if the fields
     wrote straight into `q` that flip would also quietly apply a half-typed
     band -- the picture would change for a reason nobody asked for. These
     only reach `q` when Recompute is pressed. */
  const pend = {
    filt: DEF.filt, mains_out: DEF.mains_out, k: DEF.k,
    complete_only: DEF.complete_only,
    lo_hz: DEF.lo_hz, hi_hz: DEF.hi_hz, win_ms: DEF.win_ms,
    band_lo: DEF.band_lo, band_hi: DEF.band_hi, cross_ms: DEF.cross_ms,
  };
  /* ONE SET OF SETTINGS FOR BOTH VIEWS. Single and Pooled measure and
     cluster with these same values, shown in the same controls bar, so a
     pool is always the recordings' own question asked of them together. */
  const PKEYS = ['filt', 'mains_out', 'k', 'complete_only', 'lo_hz', 'hi_hz',
                 'win_ms', 'band_lo', 'band_hi', 'cross_ms'];
  /* How many clusters k-means looks for: 1 to 6, two by default. */
  const K_MAX = 6;
  /* Saved margins, listed only to name the one a version or a pool
     carries (a single saved from a pool carries the pool's calls that
     way); and the last refusal of carried calls. */
  let margins = null;
  let marginsLoading = false;
  const marginsAsked = new Set();
  let marginErr = null;
  /* What the server says when carried calls cannot be used here (app.py's
     margin load and checks, rootcanal.py's refine). Any other error is the
     set's or the pool's own, and the calls stay. */
  const MARGIN_REFUSAL = /^(The margin |There is no saved Root Canal margin|That version of the margin |A margin |Refining a \d+-cluster margin)/;
  /* Saved borders, the same way (2026-10-06), and Single's last refusal. */
  let borders = null;
  let bordersErr = null;
  let bordersLoading = false;
  let borderErr = null;
  /* What the Borders card has picked, per view (2026-10-19): which saved
     border and which grace, before Apply -- kept across repaints, so a list
     arriving does not throw the pick away. */
  const borderPick = {};
  /* AVERAGES AND THE LASSO. `avg` is Single's average on show ({ label,
     n, data, err, busy }); Pooled keeps its own in `pool.avg`. `lasso` is
     the path being drawn on the 3D view, `lassoSel` the dots drawn round
     (scene ids), and `lassoMode` makes a plain drag draw rather than turn. */
  let avg = null;
  let avgGen = 0;
  /* SAVED VERSIONS OF THIS SET (2026-10-06). `single` is the set's
     `rootcanal_single` artifact ({ artifact_id, versions }) or null;
     `viewing` the version the picture is ({ artifact_id, v, nickname });
     `savedOnly` set when the picture is drawn from a version's numbers
     alone because its read is on another machine ({ read_on }), which
     makes the settings read-only until the set is read here; `cleanSig`
     the settings as last saved, opened or first fitted -- the picture is
     "changed" when they differ. */
  let single = null;
  /* Banked results of this set not kept as a version yet (banked before
     Bank kept one): offered as "import as a version". */
  let singleBanked = [];
  let singleGen = 0;
  let viewing = null;
  let savedOnly = null;
  let cleanSig = null;
  let lasso = null;
  let lassoMode = false;
  let lassoSel = [];
  /* Two of them are not numbers: the filter's name and the mains box. */
  const asParam = (k, v) => (k === 'filt' ? String(v)
    : (k === 'mains_out' || k === 'complete_only') ? (v === true || v === 'true')
    : Number(v));

  /* The filter a set of params names, in words -- off the preset where it is
     one, so what is named is what the server applies. */
  function filterWords(p, short) {
    const f = (p && p.filt) || DEF.filt;
    if (f === 'none') return short ? 'no filter' : 'no filter (60 Hz mains left in)';
    const pre = FILTERS[f] && f !== 'custom' ? FILTERS[f] : null;
    const lo = pre ? pre.lo_hz : Number(p.lo_hz);
    const hi = pre ? pre.hi_hz : Number(p.hi_hz);
    const out = pre ? pre.mains_out : !!asParam('mains_out', p.mains_out);
    const name = f === 'custom' ? 'custom' : pre.label;
    const band = lo > 0 ? hz(lo) + '–' + hz(hi) + ' Hz' : 'low-pass ' + hz(hi) + ' Hz';
    return name + ' ' + band + (out ? ', mains out' : (short ? '' : ', mains left in'));
  }

  let cands = null;       // sets that could be put through this
  let job = null;         // the read, while it is happening
  let poll = null;
  let jobSeen = { done: -1, at: 0 };  // when the count last moved
  let busy = false;
  let fit = null;         // the current answer
  let fitting = false;
  let fitGen = 0;
  let lastBody = null;
  let picked = null;      // which event (its `i`), or null
  let evData = null;      // the click panel's arrays, for `evKey`
  let evKey = null;
  let evGen = 0;
  let evBusy = false;
  /* The chooser folds to one line once there is a read. Three lists of
     radios above the workbench put the fit settings a screen down, and
     "no scrolling to reach a control" is the rule this panel is built to. */
  let chooserOpen = true;
  /* A dragged centre, between the pointer letting go and the fit landing.
     Drawn where it was dropped, so it does not spring back to the old place
     for the second the refit takes -- a drag that visibly undid itself would
     read as the drag having failed. */
  let live = null;        // { k, z: [a,h,f], raw: [a,h,f] }
  let bankAfterFit = false;

  /* MANY SETS AT ONCE (rebuilt 2026-10-19 in the house's picker shape:
     Doppler's and Braces' Many). `want` is what is ticked, by entry id --
     NOTHING is ticked to begin with: every todo row used to start ticked,
     so one press read forty-two sets, which is hours of disk. `filt` is the
     search and the chips (OR inside one category, AND across them); `rev`
     moves when a new plan lands, so every part built from the old one is
     rebuilt. */
  const bulk = { on: false, plan: null, want: {}, job: null, poll: null,
                 rev: 0, filt: { q: '' },
                 // The send in flight and what it sent, a Stop pressed, and
                 // the batch before, said on the picker until the next.
                 sending: false, sent: null, stopping: false, last: null };

  /* SINGLE OR POOLED, remembered per viewer. Browser storage, because it is
     a convenience of the person looking and nothing else reads it; wrapped,
     because a browser set to block site data throws on the accessor. */
  const VIEW_KEY = 'barry.rootcanal.view';
  let viewMode = (() => {
    try { return localStorage.getItem(VIEW_KEY) === 'pooled' ? 'pooled' : 'single'; }
    catch (e) { return 'single'; }
  })();

  /* The pool, while one is open. See "POOLED" below. */
  const pool = {
    cands: null, candsErr: null,
    sel: [],            // [{ key, params? }] -- params only for unbanked
    types: {},          // mouse_key -> type: the overrides, never the defaults
    focus: null,        // { mouse_key } | { mouse_type } | { member } | null
    colour: 'pool',
    /* The pool's own calls by hand and margin. Its settings -- measurement,
       k, complete events -- are Single's own (`q`): one set for both views. */
    cluster_calls: {}, margin: null, marginErr: null,
    /* A saved border to classify the pool by, and its last refusal. */
    border: null, borderErr: null,
    /* The deep dive (steps 7-10), for the request it was gathered from. */
    deep: null,
    /* Pooled's own average on show, dots drawn round, and drawn clusters
       as [member key, event number] pairs. */
    avg: null, lassoSel: [], drawn: [],
    /* The opened pool's members as it saved them: the rows for the ones
       this machine does not offer. */
    savedMembers: [],
    /* Names given to the pool's own clusters: {"<rank>": {name, type}}. */
    cluster_names: {},
    /* What the member list shows (2026-10-06): a search, and chips per
       category -- each category a set of values, OR within one category
       and AND across them -- and the name the pool is limited to, if any. */
    filt: { q: '', group: [], subgroup: [], condition: [], project: [],
            kind: [] },
    name: null,
    /* WHICH LEVEL (2026-10-06): pooling recordings, or pooling saved pools
       (a pool of pools). At the second level `sel` holds the pools, as
       "P:<artifact>:<version>". */
    level: 'pool',
    dshelf: null, dshelfErr: null,
    /* Every event of this pool is DS -- the controls (step 7). */
    all_ds: false,
    fit: null, fitting: false, gen: 0, lastBody: null, dirty: false,
    evs: null, evsFor: null,
    picked: null, evData: null, evFor: null, evGen: 0, evBusy: false,
    shelf: null, shelfErr: null, open: null, saved: false,
    fitErr: null,       // the server's sentence when it refused the members
    /* WHICH SCREEN (2026-10-19). Pooled was one long page -- the shelf, the
       table of recordings and the picture one under the other -- so Open on
       the shelf drew the pool at the very bottom, under the table, and read
       as though it had done nothing. Three screens now, at both levels:
       'home' (the saved pools, and New pool), 'build' (choosing what goes
       in) and 'view' (the picture, with nothing to choose). `paintPool`. */
    screen: 'home',
    /* The answer a recording's row offers while it is not ticked, by
       recording: what a tick puts in. */
    pickSrc: {},
    /* A refusal that names members ({ error, away: [keys], from: 'fit' |
       'save' | 'singles' }), and the run that reads them here again. */
    refusal: null, redo: null,
    /* The label typed into the save dialog, for when it comes back. */
    lastNick: '',
  };

  /* The 3D view. Yaw about the vertical, then pitch about the screen's
     horizontal.

     THE DEFAULT IS CHOSEN, not zero. Head-on, the power axis points out of
     the screen and the two clusters -- which the naming rule separates on
     power -- land on top of one another. A third of a turn round and a
     quarter down from above puts all three axes on screen with power
     vertical, which is the one the answer is read off. */
  const YAW0 = -0.62, PITCH0 = 0.42;
  const view = { yaw: YAW0, pitch: PITCH0, zoom: 1 };

  const KEYS = ['amp_uV', 'hw_ms', 'hf_db'];

  const $ = (s) => document.querySelector(s);
  const host = () => document.getElementById('tkResult');

  /* ==================================================================
     Loading
     ================================================================== */
  /* Which sets the picker offers: dentate-spike sets in The Dentist, pooled
     ones in The Confluence. Switching bundles starts the picker again, so a
     set chosen in one is never left open under the other's name. */
  let candsCtx = null;

  async function paint() {
    const ctx = inConfluence() ? 'pooled' : 'ds';
    if (candsCtx !== ctx) {
      if (candsCtx !== null) {
        cands = null; q.entry = null; q.gid = null; q.from_version = null;
        forget(); single = null;
      }
      candsCtx = ctx;
    }
    /* NOT A SECOND TIME (2026-10-20). The ToolKit calls this on every
       refresh it runs, and each call rebuilt the whole page: in Pooled the
       table being ticked was replaced mid-press ("it keeps reloading").
       Painted once for this bundle and this view, it is left alone; what
       is still missing is loaded, and repaints only the part it fills. */
    const box = host();
    const mine = !!(box && box.dataset.rcPainted === ctx + ':' + viewMode
                    && box.querySelector('.rc-viewbar'));
    if (!mine) render();
    if (viewMode === 'pooled') { await loadPool(); return; }
    loadDone();
    if (!cands) await loadCandidates();
  }

  async function loadCandidates() {
    try {
      const got = await api('/api/rootcanal/candidates');
      const want = inConfluence() ? 'pooled' : 'ds';
      cands = (got.sets || []).filter((c) => (c.type || 'ds') === want);
    } catch (e) {
      toast('Could not read the event bank: ' + e.message, 'err', 8000);
      reportClientError('rootcanal.candidates', e.message,
                        String(e && e.stack));
      cands = [];
    }
    // What was done is asked again whenever the sets are: a bank, a save.
    if (doneQ.rows) loadDone(true);
    if (!q.entry && cands.length) {
      const first = cands.find((c) => c.readable !== false && c.aligned)
                 || cands.find((c) => c.readable !== false);
      if (first) { pickSet(first.entry_id); return; }
    }
    singleRender();
  }

  /* SINGLE'S OWN ARRIVALS REPAINT SINGLE ONLY (2026-10-20). The sets, a
     set's saved versions and the first pick land a few seconds after Root
     Canal opens; somebody who has gone on to Pooled by then had the whole
     Pooled page rebuilt under them -- the table they were ticking replaced
     mid-press. Single draws them when it is shown. */
  function singleRender() {
    if (viewMode === 'pooled') return;
    render();
  }

  function setOf(id) {
    return (cands || []).find(
      (s) => s.entry_id === (id == null ? q.entry : id)) || null;
  }

  /* What a version row is called when it is sent back.

     The per-version id where there is one: the NUMBER is not unique (this
     bank holds an entry numbered 0,1,2,3,4,3,4) and the bank refuses an
     ambiguous one rather than guessing, which is right. `ref` first in
     case the server hands one out the way X-ray's plan does. */
  function versionRef(v) {
    if (!v) return null;
    if (v.ref != null) return v.ref;
    if (v.id != null) return v.id;
    return v.name != null ? v.name : v.v;
  }

  const usable = (v) => v && v.usable !== false;

  /* Which version to read from, when nobody has said.

     The newest ALIGNED one that Root Canal did not itself write. Aligned,
     because every number here is read at one instant relative to the stamp
     and Braces is what makes that instant right. Not Root Canal's own
     output, because running this on its own answer takes a second bite:
     a clean set still has a top end, k-means will still split it in two,
     and the "IEDs" it finds the second time are the loudest dentate
     spikes. Re-running from the version the last run started from is what
     makes banking twice the same act rather than a ratchet. */
  function defaultVersion(c) {
    const vs = ((c && c.versions) || []).filter(usable);
    const last = (f) => {
      for (let i = vs.length - 1; i >= 0; i--) if (f(vs[i])) return vs[i];
      return null;
    };
    return last((v) => v.aligned && v.tag !== 'rootcanal')
        || last((v) => v.tag !== 'rootcanal')
        || last(() => true);
  }

  function versionOf(c, ref) {
    return ((c && c.versions) || []).find(
      (v) => String(versionRef(v)) === String(ref)) || null;
  }

  /* Leaving a set whose picture has changed since it was saved, opened or
     first fitted asks "save as vN?" first -- yes by default (2026-10-06). */
  function pickSet(id) {
    if (id !== q.entry && isDirty()) {
      nudgeThen(() => pickSetNow(id));
      return;
    }
    pickSetNow(id);
  }

  function pickSetNow(id) {
    q.entry = id;
    const s = setOf(id);
    q.gid = s ? s.gid : null;
    const v = defaultVersion(s);
    q.from_version = v ? versionRef(v) : null;
    forget();
    single = null;
    loadSingle();
    singleRender();
  }

  /* Everything that belongs to one read, dropped together. */
  function forget() {
    doneQ.pinned = null;
    q.read = null;
    q.flips = [];
    q.centres = null;
    q.drawn = [];
    q.retry = [];
    q.cluster_names = {};
    // Calls a version carried are that version's, not the next set's.
    q.margin = null;
    marginErr = null;
    avg = null;
    lassoSel = [];
    viewing = null;
    savedOnly = null;
    cleanSig = null;
    fit = null;
    picked = null;
    evData = null;
    evKey = null;
    live = null;
    chooserOpen = true;
  }

  async function startRead() {
    if (busy || !q.entry) return;
    busy = true;
    try {
      const got = await apiPost('/api/rootcanal/read', {
        entry_id: q.entry, from_version: q.from_version,
      });
      if (got.cached || !got.job) {
        q.read = got.read;
        busy = false;
        chooserOpen = false;
        render();
        refit();
        return;
      }
      job = got.job;
      jobSeen = { done: -1, at: Date.now() };
      render();
      watch(got.read);
      BARRY.activity.log('rootcanal.read', { entry: q.entry, gid: q.gid,
                                             from_version: q.from_version });
    } catch (e) {
      busy = false;
      toast(e.message, 'err', 9000);
      render();
    }
  }

  function watch(hash) {
    if (poll) clearInterval(poll);
    poll = setInterval(async () => {
      if (!job) { clearInterval(poll); poll = null; return; }
      let got;
      try {
        got = await api('/api/cfc/job/' + job.id);
      } catch (e) { return; }         // a poll that missed; the next one will
      job = got.job || job;
      if (job.status === 'running') { tickJob(); return; }
      clearInterval(poll);
      poll = null;
      busy = false;
      if (job.status === 'error' || job.status === 'canceled') {
        const quit = job.status === 'canceled';
        toast(quit ? 'Stopped. Nothing was kept from that read.'
                   : 'The read failed: ' + (job.error || 'no reason given'),
              quit ? 'warn' : 'err', 12000);
        job = null;
        render();
        return;
      }
      job = null;
      q.read = hash;
      chooserOpen = false;
      loadDone(true);
      render();
      refit();
    }, 700);
  }

  /* ==================================================================
     The fit
     ================================================================== */
  function fitBody(extra) {
    return Object.assign({
      entry_id: q.entry, from_version: q.from_version,
      /* The read this answer is over, by the hash /read handed back. The
         cache is keyed on the stamps, not the version label, and saying
         which read is meant is cheaper than the server working it out. */
      read: q.read,
      /* Under a preset, the preset's own numbers -- not the corners last
         typed for Custom, which the server would ignore but a banked
         request would still carry, saying 3–150 Hz about a fit on LFP. */
      filt: q.filt,
      mains_out: presetOf(q.filt) ? presetOf(q.filt).mains_out : !!q.mains_out,
      lo_hz: presetOf(q.filt) ? presetOf(q.filt).lo_hz : +q.lo_hz,
      hi_hz: presetOf(q.filt) ? presetOf(q.filt).hi_hz : +q.hi_hz,
      win_ms: +q.win_ms,
      band_lo: +q.band_lo, band_hi: +q.band_hi, cross_ms: +q.cross_ms,
      k: +q.k,
      complete_only: !!q.complete_only,
      cluster_calls: Object.assign({}, q.cluster_calls),
      margin: q.margin ? Object.assign({}, q.margin) : null,
      border: q.border ? Object.assign({}, q.border) : null,
      drawn: q.drawn.map((g) => ({ events: g.events.slice(), call: g.call })),
      retry: q.retry.slice(),
      cluster_names: JSON.parse(JSON.stringify(q.cluster_names || {})),
      flips: q.flips.slice(),
      centres: q.centres ? q.centres.map((c) => c.slice()) : null,
    }, extra || {});
  }

  /* Settled at 60 ms, for the same reason X-ray's is: a flip and a step can
     land in the same breath, and the slow answer to an older question must
     not arrive last and win. `fitGen` is that guard. */
  const refitSoon = debounce(async function refit_() {
    if (!q.read) return;
    const mine = ++fitGen;
    const body = fitBody();
    lastBody = body;
    fitting = true;
    tickBusy();
    let got;
    try {
      got = await apiPost('/api/rootcanal/fit', body);
    } catch (e) {
      if (mine !== fitGen) return;
      /* A REFUSED BORDER, or refused carried calls (a version saved from a
         pool carries the pool's calls as a margin), are about those, not the
         set: taken off, said, and the set fitted afresh -- the picture
         should not vanish because centres from another measurement did not
         fit. */
      if (body.border && /^The border /.test(e.message)) {
        borderErr = e.message;
        q.border = null;
        fitting = false;
        refit();
        return;
      }
      if (body.margin && MARGIN_REFUSAL.test(e.message)) {
        marginErr = e.message;
        q.margin = null;
        toast('Fitted afresh: the calls this version carried could not be '
              + 'used here. ' + e.message, 'warn', 10000);
        fitting = false;
        refit();
        return;
      }
      fit = { ok: false, error: e.message };
      fitting = false;
      live = null;
      render();
      return;
    }
    if (body.margin) marginErr = null;
    if (mine !== fitGen) return;
    fit = got;
    fitting = false;
    live = null;
    // The settings this set was first fitted with are its clean state.
    if (cleanSig == null) cleanSig = sigOf(body);
    /* The server's own statement of what it computed, back into the form
       where the form is still asking that. It can round a corner or cap a
       band; the chips then describe the picture rather than the request. */
    const p = fit.params || {};
    // A preset's corners and mains setting are the preset's, not the form's:
    // copied back, they would overwrite what was typed for Custom, and
    // choosing Custom again would not show it.
    const presetOwns = p.filt && p.filt !== 'custom'
      ? new Set(['lo_hz', 'hi_hz', 'mains_out']) : new Set();
    for (const k of PKEYS) {
      if (presetOwns.has(k)) continue;
      if (p[k] != null && String(body[k]) === String(q[k])
          && String(pend[k]) === String(q[k])) {
        q[k] = p[k];
        pend[k] = p[k];
      }
    }
    if (picked != null && !(fit.events || []).some((e) => e.i === picked)) {
      picked = null;
    }
    render();
    loadEvent();
    followXplore();
    if (bankAfterFit) {
      bankAfterFit = false;
      // After the pictures are drawn, so the figures filed are real.
      requestAnimationFrame(() => requestAnimationFrame(() => bankDialog()));
    }
  }, 60);

  function refit() {
    if (savedOnly) { refusedSavedOnly(); return; }
    refitSoon();
  }

  /* Recompute: the typed settings become the question.

     Checked here rather than sent to be refused. Every one of these has a
     reason a person can act on, and the server's refusal would be the same
     sentence one round trip later. */
  function problems(p) {
    const out = [];
    const n = (k) => Number(p[k]);
    // The corners only mean anything on a custom filter; a preset is its
    // own numbers.
    if (p.filt === 'custom') {
      if (!(n('lo_hz') >= 0)) out.push('the filter’s low corner is not a number');
      if (!(n('hi_hz') > 0)) out.push('the filter’s high corner is not a number');
      if (n('hi_hz') <= n('lo_hz')) {
        out.push('the filter’s high corner has to be above its low one');
      }
      if (n('hi_hz') > LP_MAX) {
        out.push('the snippets are kept at 2 kHz, so the filter stops at '
                 + LP_MAX + ' Hz');
      }
    }
    if (!(n('k') >= 1) || n('k') > K_MAX || n('k') !== Math.round(n('k'))) {
      out.push('the number of clusters has to be 1 to ' + K_MAX);
    }
    if (!(n('win_ms') >= 1) || n('win_ms') > WIN_MAX) {
      out.push('the amp window has to be 1 to ' + WIN_MAX + ' ms either side '
               + 'of the stamp');
    }
    if (!(n('cross_ms') >= CROSS_MIN) || n('cross_ms') > CROSS_MAX) {
      out.push('the half-width search has to reach ' + CROSS_MIN + ' to '
               + CROSS_MAX + ' ms either side of the peak (v1’s is '
               + CROSS_V1 + ')');
    }
    if (!(n('band_lo') >= 0)) out.push('the band’s low edge is not a number');
    if (n('band_hi') <= n('band_lo')) {
      out.push('the band’s high edge has to be above its low one');
    }
    if (n('band_hi') > BAND_MAX || n('band_lo') > BAND_MAX) {
      out.push('the band stops at ' + BAND_MAX + ' Hz: above that the 5 kHz '
               + 'read is shaped by its own anti-alias filter, not by the '
               + 'recording');
    }
    return out;
  }

  const pending = () => PKEYS.some((k) => String(pend[k]) !== String(q[k]));

  /* A typed number, held to [lo, hi]. Anything that is not a number is
     left as typed, for `problems` to name. */
  function clampTo(raw, lo, hi) {
    const x = Number(raw);
    if (raw === '' || !isFinite(x)) return raw;
    const c = Math.min(hi == null ? x : hi, Math.max(lo == null ? x : lo, x));
    return c === x ? raw : String(c);
  }

  /* A CLICK IS APPLIED AT ONCE. A button or a box -- a filter, k, the mains
     or complete events -- refits the moment it is pressed, in whichever view
     is open: the fit behind it is a tenth of a second, and a choice that sat
     waiting for Recompute read as the picture not updating. Typed numbers
     still wait, so a half-typed band does not refit. */
  function applyNow(key, v) {
    if (savedOnly && viewMode !== 'pooled') {
      refusedSavedOnly();
      swapTop();
      return;
    }
    pend[key] = v;
    const was = q[key];
    q[key] = asParam(key, v);
    if (key === 'k' && Number(was) !== Number(q.k)) {
      q.centres = null; q.cluster_calls = {}; pool.cluster_calls = {};
      q.cluster_names = {}; pool.cluster_names = {};
    }
    swapTop();
    if (viewMode === 'pooled') {
      if (pool.sel.length) runPool(); else render();
    } else {
      refit();
    }
  }

  function recompute() {
    if (viewMode === 'pooled') {
      if (!pending() || pool.fitting) return false;
      const bad0 = problems(pend);
      if (bad0.length) { toast('Not yet: ' + bad0[0] + '.', 'warn', 7000); return false; }
      if (Number(pend.k) !== Number(q.k)) pool.cluster_calls = {};
      for (const k of PKEYS) q[k] = asParam(k, pend[k]);
      swapTop();
      if (pool.sel.length) runPool(); else render();
      return true;
    }
    if (savedOnly) { refusedSavedOnly(); return false; }
    if (!pending() || fitting) return false;
    const bad = problems(pend);
    if (bad.length) { toast('Not yet: ' + bad[0] + '.', 'warn', 7000); return false; }
    /* A NEW k OUTDATES what was given for the old one: dragged centres are
       one per cluster (the server refuses the wrong number), and a call
       given to "cluster 2" of three is about a different cluster at five. */
    if (Number(pend.k) !== Number(q.k)) { q.centres = null; q.cluster_calls = {}; }
    for (const k of PKEYS) q[k] = asParam(k, pend[k]);
    refit();
    swapTop();
    return true;
  }

  function revertPending() {
    for (const k of PKEYS) pend[k] = q[k];
    swapTop();
  }

  /* ---------- the overrides ---------- */
  function flipEvent(i) {
    if (!fit || !fit.ok) return;
    const e = (fit.events || []).find((x) => x.i === i);
    /* An event with no measurement has no class to flip. Refused out loud:
       putting it in a list the server then ignores would be a click that
       did nothing and said nothing. */
    if (!e || e.cls == null) {
      toast('This one was not measured, so it has no class to flip.',
            'warn', 6000);
      return;
    }
    const have = new Set(q.flips);
    if (have.has(i)) have.delete(i); else have.add(i);
    q.flips = Array.from(have).sort((a, b) => a - b);
    BARRY.activity.log('rootcanal.flip', { gid: q.gid, i, to:
      e.cls === 'ied' ? 'ds' : 'ied' });
    refit();
  }

  /* SEARCHED AGAIN, WIDER. An event with an amplitude but no half-width
     never came back to half height inside the search: the usual reason
     "only events on all 3 axes" leaves one out. On request it is measured
     once more out to the widest search the read allows (the server says
     how far), and only it. */
  function retryMs() {
    return Number((fit && fit.retry_cross_ms) || 200);
  }
  function canRetry(e) {
    return !!e && e.amp_uV != null && e.hw_ms == null && e.retried == null
      && !(q.retry || []).includes(e.i);
  }
  function retryWider(ids) {
    const add = ids.filter((i) => !q.retry.includes(i));
    if (!add.length) return;
    q.retry = q.retry.concat(add).sort((a, b) => a - b);
    BARRY.activity.log('rootcanal.retry', { gid: q.gid, n: add.length });
    refit();
  }

  /* Set one event's class to `cls`, flipping only if it is not already. */
  function setClass(i, cls) {
    const e = fit && fit.ok ? (fit.events || []).find((x) => x.i === i) : null;
    if (!e || e.cls === cls) return;
    flipEvent(i);
  }

  function moveCentre(k, z3) {
    if (!fit || !fit.ok || !(fit.centres || [])[k]) return;
    const now = q.centres
      ? q.centres.map((c) => c.slice())
      : fit.centres.map((c) => (c.z || []).slice());
    now[k] = z3.map(Number);
    q.centres = now;
    live = { k, z: now[k].slice(), raw: zToRaw(now[k]) };
    BARRY.activity.log('rootcanal.centre', { gid: q.gid, k, z: now[k] });
    drawMain();
    refit();
  }

  function resetCentres() {
    if (!q.centres) return;
    q.centres = null;
    live = null;
    refit();
  }

  function clearFlips() {
    if (!q.flips.length) return;
    q.flips = [];
    refit();
  }

  /* ==================================================================
     z <-> raw

     The space is z-scored; the flat views are in the units the numbers were
     measured in. A centre dragged on a flat view is a position in µV and ms
     and dB that has to become a z-coordinate to be sent back.

     The map per axis is a straight line, and it is FITTED from the events
     rather than recomputed: every measured event carries both its raw value
     and its z, so the slope and intercept are exactly the recording's SD and
     mean whatever convention the server used for the SD. Computing them
     here from the raw values would be a second implementation of the
     scaling with its own chance of disagreeing by a factor of n/(n-1).
     ================================================================== */
  let zmap = null;       // [{m, s}] per axis, for the fit on screen
  let zmapFor = null;

  function scaling() {
    const S = scene();
    const evs = (S && S.events) || [];
    if (zmapFor === evs) return zmap;
    zmapFor = evs;
    const cents = (S && S.fitCentres) || [];
    zmap = [0, 1, 2].map((a) => {
      let n = 0, sz = 0, sr = 0, szz = 0, szr = 0;
      for (const e of evs) {
        const r = e[KEYS[a]], z = (e.z || [])[a];
        if (!isFinite(r) || r == null || z == null || !isFinite(z)) continue;
        n += 1; sz += z; sr += r; szz += z * z; szr += z * r;
      }
      if (n >= 2) {
        const vz = szz - sz * sz / n;
        if (vz > 1e-12) {
          const s = (szr - sz * sr / n) / vz;
          return { m: (sr - s * sz) / n, s };
        }
      }
      // Two centres carry both too, which is enough for a line.
      const cs = cents;
      if (cs.length === 2) {
        const z0 = (cs[0].z || [])[a], z1 = (cs[1].z || [])[a];
        const r0 = (cs[0].raw || [])[a], r1 = (cs[1].raw || [])[a];
        if (isFinite(z0) && isFinite(z1) && Math.abs(z1 - z0) > 1e-9) {
          const s = (r1 - r0) / (z1 - z0);
          return { m: r0 - s * z0, s };
        }
      }
      return { m: 0, s: 1 };
    });
    return zmap;
  }

  const rawToZ = (a, r) => {
    const m = scaling()[a];
    return (r - m.m) / (m.s || 1);
  };
  const zToRawA = (a, z) => {
    const m = scaling()[a];
    return m.m + m.s * z;
  };
  const zToRaw = (z3) => z3.map((z, a) => zToRawA(a, z));

  /* The centres as they should be DRAWN: the dragged one where it was
     dropped, the rest as the fit placed them. */
  function centresShown() {
    const cs = ((fit && fit.ok && fit.centres) || []).map((c, k) => ({
      k, cls: c.cls, n: c.n,
      z: (c.z || []).slice(), raw: (c.raw || []).slice(),
    }));
    if (live && cs[live.k]) {
      cs[live.k].z = live.z.slice();
      cs[live.k].raw = live.raw.slice();
      cs[live.k].moving = true;
    }
    return cs;
  }

  /* ==================================================================
     The page
     ================================================================== */
  /* The panel, rebuilt -- around the one thing in this host that is not
     ours. The ToolKit mounts its activity feed into `#tkResult`, the same
     element this draws into, and `innerHTML = ''` destroyed it; the
     watcher then mounted a fresh one that said "Reading..." and fetched.
     X-ray learnt this the hard way (see its `render`) and so did Braces
     before it. The feed is lifted out and put back: the same element, so
     its rows, its poller and its listener all survive. */
  function render() {
    const box = host();
    if (!box) return;
    /* Only while Root Canal is the tool open. A read of the bank that lands
       after somebody has moved on -- to Junction, say -- painted Root Canal
       over the panel they were now in (_dev/confluence.html caught it: one
       run in three). */
    const tk = BARRY.views && BARRY.views.toolkit;
    if (tk && typeof tk.tool === 'function' && tk.tool() !== 'rootcanal') return;
    const feed = box.querySelector('.tf');
    if (feed) box.removeChild(feed);
    try {
      paint_();
    } finally {
      if (feed) box.appendChild(feed);
    }
    /* DRAWN NOW, not only on the next frame. A frame is not guaranteed to
       come soon -- a background tab, or the harness's virtual clock, can
       hold it back for as long as it likes -- and until it does every canvas
       is a blank 300 x 150 being stretched to its box. Reading the boxes
       forces the layout, so drawing here draws at the size they will have.
       The frame's pass stays as a second chance for anything that moves
       once the fonts arrive. */
    if (scene() && document.getElementById('rcSpace')
        && (viewMode === 'pooled' || q.read)) {
      drawAll();
    }
    watchSize();
  }

  function paint_() {
    const box = host();
    if (!box) return;
    box.dataset.rcPainted = (inConfluence() ? 'pooled' : 'ds') + ':' + viewMode;
    /* The list of sets already done is one node kept across these rebuilds;
       emptying the page takes the caret out of its search and its list
       back to the top. Both are put back once it is in again. */
    const act = document.activeElement;
    const keep = doneNode && act && doneNode.contains(act) ? {
      el: act, a: act.selectionStart, b: act.selectionEnd } : null;
    const dl = doneNode && doneNode.querySelector('.rc-done-list');
    const dScroll = dl ? dl.scrollTop : 0;
    box.innerHTML = '';
    box.appendChild(intro());
    box.appendChild(viewBar());
    if (viewMode === 'pooled') { paintPool(box); return; }
    if (!cands) { box.appendChild(loading('Reading the event bank')); return; }
    if (!cands.length) { box.appendChild(nothing()); return; }
    box.appendChild(modeSwitch());
    if (bulk.on) { box.appendChild(bulkCard()); return; }
    box.appendChild(chooser());
    if (keep && keep.el.isConnected && document.activeElement !== keep.el) {
      keep.el.focus();
      try { if (keep.a != null) keep.el.setSelectionRange(keep.a, keep.b); } catch (e) { /* not text */ }
    }
    const dl2 = doneNode && doneNode.querySelector('.rc-done-list');
    if (dl2 && dScroll) dl2.scrollTop = dScroll;
    if (job) { box.appendChild(progress()); return; }
    if (!q.read) { box.appendChild(readCard()); return; }
    box.appendChild(workbench());
    requestAnimationFrame(() => { drawAll(); });
  }

  /* One card replaced where it stands, and nothing else touched. The
     reason this exists at all is the activity feed above. */
  function swap(sel, node) {
    const box = host();
    const old = box && node ? box.querySelector(sel) : null;
    if (!old) return false;
    old.replaceWith(node);
    return true;
  }

  /* Which bundle Root Canal is being worked in: The Dentist cleans a
     dentate-spike set, The Confluence teases a pooled one apart. The same
     tool, said two ways (toolkit.js, `bundleOf`). */
  function inConfluence() {
    const tk = BARRY.views && BARRY.views.toolkit;
    return !!(tk && tk.via && tk.via() === 'confluence');
  }

  function intro() {
    return BARRY.ui.stepHeader({
      title: 'Root Canal',
      step: BARRY.ui.stepOf('rootcanal') || 'step 4 of The Dentist',
      blurb: inConfluence()
        ? 'Teases a pooled set apart — Incisor’s and Doppler’s events '
          + 'together, sorted in Panning and lined up in Lock — by '
          + 'amplitude, half-width and high-frequency power, each dot '
          + 'coloured by its DS / IED call. Nothing is taken out: each '
          + 'event is named by its cluster.'
        : 'Takes the interictal discharges out of an aligned set of '
          + 'dentate spikes — amplitude, half-width and high-frequency '
          + 'power per event, split in two by k-means.',
    });
  }

  function loading(what, sub) {
    return el('div', { class: 'card rc-load' }, [loader(what, sub)]);
  }

  function nothing() {
    if (inConfluence()) {
      return el('div', { class: 'card rc-none' }, [
        el('div', { class: 'empty-state' }, [
          el('p', { text:
            'No pooled set is ready yet. Pool a recording in Junction, sort '
            + 'it in Panning and bank the results, then line it up in Lock: '
            + 'every number here is read at one instant relative to the '
            + 'stamp, and a stamp a few milliseconds out measures a smear.' }),
          BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Open Lock',
            onclick: () => { const tk = BARRY.views.toolkit;
                             if (tk && tk.pick) tk.pick('lock'); } }),
        ]),
      ]);
    }
    return el('div', { class: 'card rc-none' }, [
      el('div', { class: 'empty-state' }, [
        el('p', { text:
          'Nothing is ready for a root canal yet. A set has to have been '
          + 'through Braces first: every number here is read at one instant '
          + 'relative to the stamp, and a stamp that is a few milliseconds '
          + 'out measures a smear. Open Braces (step 3) and line a set up.' }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Open Braces',
          onclick: () => { const tk = BARRY.views.toolkit;
                           if (tk && tk.pick) tk.pick('braces'); } }),
      ]),
    ]);
  }

  /* One set, or many -- the same control X-ray and Braces draw for the
     same choice, and for the same reason: picking and reading one set is
     done while thinking, paying for a cohort's reads is set off and come
     back to. */
  function modeSwitch() {
    const mode = bulk.on ? 'many' : 'one';
    return el('div', { class: 'card rc-mode' }, [
      /* How many, through the run bar (constitution §6d): one component
         for the choice every tool makes, rather than a seg each tool drew
         for itself. Only local modes, so the bar shows How many alone. */
      BARRY.ui.runBar({
        modes: { local: ['one', 'many'] }, where: 'local', count: mode,
        onChange: (w, c) => {
          bulk.on = c === 'many';
          render();
          if (bulk.on && !bulk.plan) loadBulk();
        },
      }),
      // Said once here; the card under it says what a tick costs.
      el('span', { class: 'hint', text: bulk.on
        ? 'Read many sets in one go, while you do something else. Each is '
          + 'still looked at and banked by a person, one at a time.'
        : 'Pick an aligned set, read it once, then look at what it splits '
          + 'into.' }),
      bulk.job && !bulk.on
        ? el('span', { class: 'hint rc-bulk-note', text: (() => {
            const st = (bulk.job.stages || [])[0] || {};
            return 'Batch still reading — ' + (st.done || 0) + ' of '
                 + (st.of || '?') + '.';
          })() })
        : null,
      // Back to it in one press, rather than through How many.
      bulk.job && !bulk.on
        ? BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Show the batch',
            extra: 'rc-bulk-show',
            onclick: () => { bulk.on = true; render(); } })
        : null,
    ].filter(Boolean));
  }

  /* ==================================================================
     ALREADY THROUGH ROOT CANAL (2026-10-20)

     "Root Canal in the single view needs a way to see every session with
     Root Canal already ran. Similar to the Checkup view." Checkup's shelf,
     in Checkup's own classes: a toggle saying how many, a search, chips
     with counts, named columns, and a row per set -- what Root Canal left
     on it (versions kept, a banked call, a read and where it is), whose
     hands it was last in and when, and whether it is shared.

     Open puts it in front of you the way it was left: its newest saved
     version as saved; else its read, if the read is on this machine, at
     once (never a new read -- the server is asked for a cached one only);
     else it is picked, and the toast says where its read is. The shelf
     folds itself once something is open, to one line.

     Kept as one node across the page's redraws (the page is rebuilt
     whole), its parts through `BARRY.ui.sections`, so a press on a chip or
     a word typed changes the list and nothing else.
     ================================================================== */
  /* `pinned` is a press on the toggle; until there is one the list is open
     while a set is being chosen and folds itself to its line once a set's
     picture is up -- the picture's own controls stay on the first screen.
     Picking another set hands it back (`forget`). */
  const doneQ = { pinned: null, filt: { q: '' }, show: 'all', sort: 'recent',
                  rows: null, err: null, ctx: null, loading: false, rev: 0 };
  const doneOpen = () => (doneQ.pinned != null ? doneQ.pinned
                                                : !(q.read || job));
  let doneNode = null;

  async function loadDone(force) {
    const ctx = inConfluence() ? 'pooled' : 'ds';
    /* Asked again while a read of it is out (a bank, a save): read again
       once that one lands, or the list stays one change behind. */
    /* Compared with the bundle being READ, not the one last shown: while
       the first read is out `ctx` still names the old list (or none), so a
       second ordinary call would have queued a pointless re-read. */
    if (doneQ.loading) { if (force || doneQ.loadingCtx !== ctx) doneQ.again = true; return; }
    if (doneQ.rows && doneQ.ctx === ctx && !force) return;
    doneQ.loading = true;
    doneQ.loadingCtx = ctx;
    doneQ.again = false;
    try {
      const got = await api('/api/rootcanal/done?type=' + ctx);
      doneQ.rows = got.sets || [];
      doneQ.err = null;
    } catch (e) {
      // A failed read keeps this bundle's rows, never the other bundle's
      // under this one's name.
      doneQ.rows = (doneQ.ctx === ctx && doneQ.rows) || [];
      doneQ.err = e.message;
    }
    doneQ.ctx = ctx;
    doneQ.loading = false;
    doneQ.rev += 1;
    if (doneQ.again) { doneQ.again = false; loadDone(true); }
    if (viewMode !== 'pooled' && !bulk.on) {
      if (doneNode && doneNode.isConnected) doneFill();
      else render();
    }
  }

  /* Each mark stroked on `currentColor` at 16 px, as the Many view's are. */
  const DONE_ICO = {
    all: 'M2.5 4h11M2.5 8h11M2.5 12h11',
    saved: 'M4 1.8h8v12.4l-4-3-4 3z',
    banked: 'M1.8 6L8 2.3 14.2 6M3.2 6.6v5.6M6.4 6.6v5.6M9.6 6.6v5.6M12.8 '
            + '6.6v5.6M1.8 13.4h12.4',
    read: 'M8 4.2C6.6 3 4.6 2.6 2 2.8v9.6c2.6-.2 4.6.2 6 1.4 1.4-1.2 3.4-1.6 '
          + '6-1.4V2.8c-2.6-.2-4.6.2-6 1.4zM8 4.2v9.6',
    here: 'M2 3h12v8H2zM5.5 14h5M8 11v3',
    tick: 'M3.5 8.5l3 3 6-7',
  };
  const doneIco = (d, extra) => el('svg', {
    class: 'rc-bulk-ico' + (extra ? ' ' + extra : ''), viewBox: '0 0 16 16',
    'aria-hidden': 'true', html: '<path d="' + d + '" />' });

  /* What was done, as a chip: [id, words, test, mark, what it means]. */
  const DONE_SHOW = [
    ['all', 'All', () => true, DONE_ICO.all,
     'Every set Root Canal has been run on.'],
    ['saved', 'Saved versions', (r) => !!r.saved, DONE_ICO.saved,
     'Kept as versions: they reopen, and pool, on any machine.'],
    ['banked', 'Banked', (r) => !!r.banked, DONE_ICO.banked,
     'Its call is in the Event Bank, as the set’s next version.'],
    ['readonly', 'Read, nothing kept',
     (r) => !!r.reads && !r.saved && !r.banked, DONE_ICO.read,
     'Read, and neither saved as a version nor banked yet.'],
    ['here', 'Read on this machine', (r) => !!(r.reads && r.reads.here),
     DONE_ICO.here, 'Its read is on this computer, so it opens at once.'],
  ];
  const DONE_SORTS = [['recent', 'Last touched'], ['name', 'Recording'],
                      ['events', 'Most events']];
  const DONE_DID = { read: 'read', banked: 'banked', saved: 'saved' };

  const doneLabel = (r) => r.session_label || r.gid || r.entry_id;
  /* The entry's own name less the recording it repeats, as the folded
     chooser says it. */
  function doneSetName(r) {
    const title = doneLabel(r);
    let nm = String(r.name || '');
    if (nm.indexOf(title) === 0 && nm.length > title.length) {
      nm = nm.slice(title.length).replace(/^\s*[·:–-]\s*/, '');
    }
    return nm || 'set ' + r.entry_id;
  }

  function doneHay(r) {
    const sv = r.saved && r.saved.last;
    const b = r.banked && r.banked.last;
    const last = r.last || {};
    return [doneLabel(r), r.name, r.project, r.mouse_type, r.group,
            r.subgroup, r.condition,
            r.mouse != null ? 'm' + r.mouse : '',
            r.session != null ? 's' + r.session : '',
            sv && sv.nickname, sv && sv.filter, sv && sv.by, sv && sv.machine,
            b && b.by, b && b.machine, last.by, last.machine,
            ((r.reads && r.reads.machines) || []).join(' '),
            r.saved ? 'saved version' : '', r.banked ? 'banked' : '',
            r.reads ? 'read' : '']
      .filter(Boolean).join(' ').toLowerCase();
  }

  function doneShown(r) {
    const sh = DONE_SHOW.find((x) => x[0] === doneQ.show) || DONE_SHOW[0];
    if (!sh[2](r)) return false;
    for (const [key, , get] of BULK_CATS) {
      const want = doneQ.filt[key] || [];
      if (want.length && want.indexOf(String(get(r))) < 0) return false;
    }
    const words = String(doneQ.filt.q || '').trim().toLowerCase()
      .split(/\s+/).filter(Boolean);
    if (!words.length) return true;
    const hay = doneHay(r);
    return words.every((w) => hay.indexOf(w) >= 0);
  }

  function doneOrder(a, b) {
    if (doneQ.sort === 'name') {
      return natural(a.project || '~', b.project || '~')
        || natural(doneLabel(a), doneLabel(b));
    }
    if (doneQ.sort === 'events') {
      return (b.n || 0) - (a.n || 0) || natural(doneLabel(a), doneLabel(b));
    }
    return ((b.last || {}).t || 0) - ((a.last || {}).t || 0);
  }

  /* The list itself, in the set card under the line its toggle is on;
     folded, it is nothing at all, so a set's picture is not pushed a line
     further down by it (the controls stay on the first screen). */
  function doneCard() {
    if (!doneNode) {
      doneNode = el('div', { class: 'rc-donelist' }, [
        el('div', { class: 'cur-shelf rc-done-shelf' }),
      ]);
    }
    doneFill();
    return doneNode;
  }

  function doneToggle() {
    const n = doneQ.rows && doneQ.ctx === (inConfluence() ? 'pooled' : 'ds')
      ? doneQ.rows.length : null;
    const open = doneOpen();
    return el('button', {
      type: 'button',
      class: 'cur-shelf-toggle rc-done-toggle' + (open ? ' on' : ''),
      'aria-expanded': open ? 'true' : 'false',
      title: open ? 'Fold the list away.'
        : 'Every set Root Canal has been run on: read, kept as versions, or '
          + 'banked -- here or on another machine.',
      text: (open ? '▾  ' : '▸  ') + 'Already through Root Canal'
        + (n == null ? '  ·  reading…'
           : '  ·  ' + n + ' set' + (n === 1 ? '' : 's')),
      onclick: () => { doneQ.pinned = !open; doneFill(); },
    });
  }

  function doneFill() {
    for (const t of Array.from(document.querySelectorAll('.rc-done-toggle'))) {
      t.replaceWith(doneToggle());
    }
    if (!doneNode) return;
    const shelf = doneNode.querySelector('.rc-done-shelf');
    const open = doneOpen();
    doneNode.hidden = !open;
    shelf.hidden = !open;
    if (open) BARRY.ui.sections(shelf, doneParts());
  }

  function doneParts() {
    // Another bundle's list is never shown under this one's name.
    const rows = doneQ.ctx === (inConfluence() ? 'pooled' : 'ds')
      ? doneQ.rows : null;
    const say = (key, text, cls) => [{ key: key, enter: false, sig: text,
      build: () => el('p', { class: 'hint' + (cls ? ' ' + cls : ''),
                             text: text }) }];
    if (!rows) return say('wait', 'Reading what Root Canal has done…');
    if (!rows.length) {
      return say(doneQ.err ? 'err' : 'none', doneQ.err
        ? 'The list could not be read: ' + doneQ.err
        : 'Root Canal has not been run on any set yet. Pick one below and '
          + 'read it; it is listed here from then on.',
        doneQ.err ? 'rc-warn' : null);
    }
    const shown = rows.filter(doneShown).sort(doneOrder);
    const fs = JSON.stringify([doneQ.filt, doneQ.show, doneQ.sort]);
    return [
      { key: 'find', enter: false, sig: 'find', build: doneFind },
      { key: 'show', enter: false, sig: [doneQ.rev, doneQ.show],
        build: () => doneShowChips(rows) },
      { key: 'chips', enter: false, sig: [doneQ.rev, fs],
        build: () => bulkChips(rows, doneQ.filt, doneFill) },
      { key: 'count', enter: false, sig: [shown.length, rows.length],
        build: () => el('div', { class: 'hint rc-done-count', text:
          shown.length === rows.length
            ? rows.length + ' set' + (rows.length === 1 ? '' : 's')
            : shown.length + ' of ' + rows.length }) },
      { key: 'cols', enter: false, sig: 'cols', build: doneCols },
      { key: 'list', enter: false,
        sig: [doneQ.rev, fs, q.entry || '', viewing ? viewing.v : null],
        build: () => doneList(shown) },
    ];
  }

  function doneFind() {
    const f = BARRY.ui.searchField({
      placeholder: 'Type a set, mouse, session, person, machine or nickname',
      value: doneQ.filt.q, width: '30rem',
      title: 'Every word has to match: the set’s name, the mouse (m13), the '
           + 'session (s2), the project, group or condition, who touched it '
           + 'and on which machine, or a saved version’s nickname.',
      oninput: (e) => { doneQ.filt.q = e.target.value; doneFill(); },
    });
    f.classList.add('rc-done-find');
    f.input.setAttribute('data-fk', 'rc-done-search');
    f.input.setAttribute('aria-label', 'Search the sets Root Canal has done');
    const sort = el('select', {
      class: 'rc-in rc-done-sort', title: 'Order',
      'aria-label': 'Order',
      onchange: (e) => { doneQ.sort = e.target.value; doneFill(); },
    }, DONE_SORTS.map(([v, t]) => el('option', {
      value: v, text: t, selected: doneQ.sort === v ? 'selected' : null })));
    return el('div', { class: 'cur-filter rc-done-filter' }, [f, sort]);
  }

  /* One of them at a time: pressed again, back to All. */
  function doneShowChips(rows) {
    return el('div', { class: 'rc-bulk-chips rc-done-show' }, [
      el('div', { class: 'rc-bulk-cat', 'data-cat': 'done' }, [
        el('span', { class: 'rc-bulk-k', text: 'what was done' }),
        el('div', { class: 'rc-bulk-vals' }, DONE_SHOW.map(
          ([id, words, test, d, tip]) => {
            const n = rows.filter(test).length;
            const lit = doneQ.show === id;
            const b = BARRY.ui.button({ kind: 'mini', on: lit,
              extra: 'rc-bulk-chip rc-done-chip',
              disabled: !n && id !== 'all',
              title: tip + ' ' + n + ' set' + (n === 1 ? '' : 's') + '.'
                     + (lit && id !== 'all' ? ' Press again for all of them.'
                                            : ''),
              onclick: () => {
                doneQ.show = lit && id !== 'all' ? 'all' : id;
                doneFill();
              },
              children: [
                doneIco(lit ? DONE_ICO.tick : d, lit ? 'rc-bulk-lit' : null),
                el('span', { class: 'rc-bulk-chip-v', text: words }),
                el('span', { class: 'rc-bulk-chip-n', text: String(n) }),
              ] });
            b.type = 'button';
            b.setAttribute('aria-pressed', lit ? 'true' : 'false');
            b.dataset.v = id;
            return b;
          })),
      ]),
    ]);
  }

  /* Named columns, sharing the row's grid, and not a row themselves. */
  function doneCols() {
    return el('div', { class: 'cur-shelf-cols rc-done-cols' }, [
      el('span', { class: 'csr-name', text: 'Set' }),
      el('span', { class: 'csr-sess', text: 'Recording' }),
      el('span', { class: 'csr-did', text: 'What Root Canal left' }),
      el('span', { class: 'csr-who', text: 'Last by' }),
      el('span', { class: 'csr-when', text: 'Last touched' }),
      el('span', {}),
    ]);
  }

  function doneList(shown) {
    const box = el('div', { class: 'cur-shelf-list rc-done-list' });
    if (!shown.length) {
      box.appendChild(el('div', { class: 'hint', text:
        'Nothing matches that. Clear the search, or press All.' }));
      return box;
    }
    for (const r of shown) box.appendChild(doneRow(r));
    return box;
  }

  const doneStamp = (at) => (at ? String(at).replace('T', ' ').slice(0, 16)
                                : '');
  function doneAgo(at) {
    const w = BARRY.ui.when(at);
    if (!w) return '';
    return (w === 'just now' || /^\d{4}-/.test(w)) ? w : w + ' ago';
  }

  /* What Open will do with it, said before it is pressed. */
  function doneOpenWhat(r) {
    const sv = r.saved && r.saved.last;
    if (sv) {
      return 'Open v' + sv.v + (sv.nickname ? ' ‘' + sv.nickname + '’' : '')
        + ' as it was saved' + (sv.here === false
          ? ', drawn from its numbers (its read is not on this machine)' : '')
        + '.';
    }
    const rd = r.reads || {};
    if (rd.here || (r.banked && r.banked.last.here)) {
      return 'Open its read, which is on this machine, at once, at the '
           + 'settings on now.';
    }
    return 'Pick it. Its read is on ' + ((rd.machines || []).join(', ')
      || 'another machine') + ', so it would be read again here.';
  }

  function doneRow(r) {
    const on = r.entry_id === q.entry;
    const sv = r.saved && r.saved.last;
    const b = r.banked && r.banked.last;
    const rd = r.reads;
    const did = [];
    if (sv) {
      did.push(el('span', { class: 'flagchip rc-done-saved',
        title: r.saved.n_versions + ' version' + (r.saved.n_versions === 1
          ? '' : 's') + ' kept. The newest, v' + sv.v + ': '
          + [sv.k != null ? 'k = ' + sv.k : null, sv.filter,
             sv.ds != null ? sv.ds + ' DS, ' + (sv.ied || 0) + ' IED' : null,
             'saved by ' + (sv.by || 'someone')
               + (sv.machine ? ' on ' + sv.machine : '')
               + (sv.at ? ', ' + doneStamp(sv.at) : '')]
            .filter(Boolean).join(' · '),
        text: (r.saved.n_versions > 1 ? r.saved.n_versions + ' versions · '
                                      : '') + 'v' + sv.v
          + (sv.nickname ? ' ‘' + sv.nickname + '’' : '') }));
    }
    if (b) {
      did.push(el('span', { class: 'flagchip rc-done',
        title: 'Banked into the set as v' + b.ds_version
          + (b.k != null ? ', k = ' + b.k : '') + ', by ' + (b.by || 'someone')
          + (b.machine ? ' on ' + b.machine : '')
          + (b.at ? ', ' + doneStamp(b.at) : '')
          + (r.banked.n > 1 ? '. Banked ' + r.banked.n + ' times.' : '.'),
        text: 'banked v' + b.ds_version + (b.ds != null
          ? ' · ' + b.ds + ' DS · ' + (b.ied || 0) + ' IED' : '') }));
    }
    if (rd) {
      const where = rd.here ? 'read here'
        : 'read on ' + ((rd.machines || []).join(', ') || 'another machine');
      did.push(el('span', { class: 'flagchip rc-done-read'
                                    + (rd.here ? ' here' : ''),
        title: 'Read ' + rd.n + ' time' + (rd.n === 1 ? '' : 's')
          + (rd.machines && rd.machines.length ? ', on ' + rd.machines.join(
            ', ') : '') + '. ' + (rd.here
            ? rd.here + ' of the reads ' + (rd.here === 1 ? 'is' : 'are')
              + ' on this machine.'
            : 'None of the reads is on this machine.'),
        text: where }));
    }
    const last = r.last || {};
    const can = !!sv || r.readable !== false;
    return el('div', {
      class: 'cur-shelf-row rc-done-row' + (on ? ' on' : ''),
      'data-entry': r.entry_id,
    }, [
      el('span', { class: 'csr-name', text: doneSetName(r) }),
      el('span', { class: 'csr-sess', text: doneLabel(r) }),
      el('span', { class: 'csr-did' }, did),
      el('span', { class: 'csr-who' + (last.by ? '' : ' none'),
                   text: (last.by || '—')
                         + (last.machine ? ' · ' + last.machine : '') }),
      el('span', { class: 'csr-when', title: doneStamp(last.at) }, [
        (DONE_DID[last.what] ? DONE_DID[last.what] + ' ' : '')
          + (doneAgo(last.at) || '—'),
        BARRY.syncState
          ? (r.saved ? BARRY.syncState.mark('artifacts', r.saved.artifact_id)
             : r.banked ? BARRY.syncState.mark('bank', r.entry_id) : null)
          : null,
      ].filter(Boolean)),
      el('div', { class: 'csr-acts' }, [
        BARRY.ui.button({ kind: 'ghost', size: 'sm', extra: 'rc-done-open',
          text: on ? 'Open again' : 'Open',
          disabled: !can,
          title: can ? doneOpenWhat(r)
                     : (r.why_not || 'It cannot be read on this machine.'),
          onclick: () => openDone(r) }),
      ]),
    ]);
  }

  async function openDone(r) {
    const go = async () => {
      if (!setOf(r.entry_id)) {
        toast('‘' + doneLabel(r) + '’ is not one of the sets offered here '
              + 'any more (it may have been archived).', 'warn', 8000);
        return;
      }
      pickSetNow(r.entry_id);
      // Folded for what was opened, whatever it turns out to need.
      doneQ.pinned = false;
      const sv = r.saved && r.saved.last;
      if (sv) {
        await openVersion(r.saved.artifact_id, sv.v);
        return;
      }
      /* The version its newest read here was made from, where it is still
         in the list: the same stamps make the same read. */
      const rd = (r.reads && r.reads.last_here)
        || (r.banked && r.banked.last.here ? r.banked.last : null);
      const fv = rd ? rd.from_version : null;
      if (fv != null && versionOf(setOf(), fv)) q.from_version = fv;
      if (rd) {
        let got = null;
        try {
          got = await apiPost('/api/rootcanal/read', {
            entry_id: q.entry, from_version: q.from_version,
            only_cached: true });
        } catch (e) {
          toast(e.message, 'err', 9000);
        }
        if (got && got.cached && q.entry === r.entry_id) {
          q.read = got.read;
          chooserOpen = false;
          render();
          refit();
          return;
        }
      }
      const elsewhere = ((r.reads && r.reads.machines) || []).join(', ');
      toast(rd ? 'Its read here was made with other settings, so it is not '
                 + 'opened by itself: press Read to read it again.'
               : 'Its read is on ' + (elsewhere || 'another machine')
                 + ', not this one. Press Read to read it here'
                 + (r.banked ? ', or keep its banked call as a version.'
                             : '.'), null, 9000);
      render();
    };
    if (r.entry_id !== q.entry && isDirty()) nudgeThen(go);
    else go();
  }

  /* ---------- 1. the set, and which version to read ----------

     The same three controls every other step in the bundle uses, in the
     same order: a recording you type the name of, the banked entries on it
     as a radio list, and the versions of the chosen one as another. */
  function chooser() {
    const cur = setOf();
    if (q.read && !chooserOpen && cur) {
      /* FOLDED, once there is a read. The whole choice on one line, and one
         button to unfold it. */
      const v = versionOf(cur, q.from_version);
      const title = cur.session_label || cur.gid || cur.entry_id;
      /* The entry's own name less the session it repeats: the line said
         "PTEN m13 s2 2023-08-01" twice in a row (2026-10-19). */
      let nm = String(cur.name || 'DS set ' + cur.entry_id);
      if (nm.indexOf(title) === 0 && nm.length > title.length) {
        nm = nm.slice(title.length).replace(/^\s*[·:–-]\s*/, '');
      }
      return el('div', { class: 'card rc-choose rc-folded' }, [
        el('strong', { text: title }),
        el('span', { class: 'hint', text:
          nm + '  ·  ' + (v ? BARRY.ui.versionLabel(v) : 'as it is now')
          + '  ·  ' + ((v && v.n) || cur.n) + ' events'
          + (v && v.aligned ? '  ·  aligned' : '') }),
        el('span', { class: 'spacer' }),
        // What has been done already (2026-10-20); its list drops down here.
        doneToggle(),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Change set',
          title: 'Show the recording, entry and version lists again. The '
               + 'read and the answer stay until you pick something else.',
          onclick: () => { chooserOpen = true; render(); } }),
        doneCard(),
      ]);
    }

    const box = el('div', { class: 'card rc-choose' });
    const regRows = (BARRY.views.toolkit && BARRY.views.toolkit.registryRows)
      ? BARRY.views.toolkit.registryRows() : [];
    const byGid = new Map();
    for (const r of regRows) byGid.set(r.gid, r);
    const rows = [];
    const seen = new Set();
    for (const c of (cands || [])) {
      if (!c.gid || seen.has(c.gid)) continue;
      seen.add(c.gid);
      rows.push(byGid.get(c.gid) || {
        gid: c.gid, label: c.session_label || c.gid,
        project: c.project, mouse: c.mouse, session: c.session,
        reachable: c.readable !== false,
      });
    }
    rows.sort((x, y) => natural(x.label || '', y.label || ''));
    if (!q.gid || !seen.has(q.gid)) {
      q.gid = (cur && cur.gid) || (rows[0] || {}).gid || null;
    }

    box.appendChild(el('div', { class: 'rc-choose-top' }, [
      el('div', { class: 'section-label', text: 'Recording' }),
      el('span', { class: 'spacer' }),
      // What has been done already (2026-10-20); its list drops down here.
      doneToggle(),
    ]));
    /* DROPPED DOWN WHERE IT WAS PRESSED (2026-10-21): it opened above the
       set card, so the card -- and the toggle -- jumped down, and folding
       it meant finding the toggle again somewhere else. */
    box.appendChild(doneCard());
    box.appendChild(BARRY.pickSession({
      rows,
      value: q.gid,
      placeholder: 'Which recording? Type a mouse, session or date…',
      onpick: (r) => {
        if (r.gid === q.gid) return;
        q.gid = r.gid;
        const here = (cands || []).filter((c) => c.gid === r.gid);
        const first = here.find((c) => c.readable !== false && c.aligned)
                   || here.find((c) => c.readable !== false);
        if (first) { pickSet(first.entry_id); return; }
        q.entry = null; q.from_version = null;
        forget();
        render();
      },
    }));

    const mine = (cands || []).filter((c) => c.gid === q.gid);
    if (!mine.length) {
      box.appendChild(el('p', { class: 'confirm-msg', text:
        'No aligned set of dentate spikes is banked against this recording. '
        + 'Incisor finds them, Checkup goes through them and Braces lines '
        + 'them up; this is step four.' }));
      return box;
    }

    box.appendChild(el('div', { class: 'section-label',
                                text: 'Which banked set' }));
    const list = el('div', { class: 'bm-list rc-list' });
    for (const c of mine) {
      /* SHOWN AND DISABLED rather than left out, with the reason on the
         row: "this set exists and cannot be used, and here is why" is a real
         answer, and a row that silently is not there reads as a set that
         does not exist. */
      const can = c.readable !== false;
      const rc = c.rootcanal || {};
      list.appendChild(el('label', {
        class: 'bm-row' + (c.entry_id === q.entry ? ' on' : '')
               + (can ? '' : ' off'),
        title: can ? '' : (c.why_not || 'This set cannot be read here.'),
      }, [
        el('input', {
          type: 'radio', name: 'rcEntry',
          disabled: can ? null : 'disabled',
          checked: c.entry_id === q.entry ? 'checked' : null,
          onchange: () => pickSet(c.entry_id),
        }),
        el('span', { class: 'mk-name', text: c.name || c.session_label
                                             || c.entry_id }),
        el('span', { class: 'flagchip', text: c.n + ' events' }),
        c.aligned ? el('span', { class: 'flagchip', text: 'aligned' }) : null,
        rc.done ? el('span', { class: 'flagchip rc-done',
                               title: 'Root Canal has been banked on this '
                                    + 'set before.',
                               text: 'Root Canal done'
                                     + (rc.version ? ' · v' + rc.version : '') })
                : null,
        el('span', { class: 'person-what', text: can
          ? (c.aligned ? '' : 'not through Braces')
          : (c.why_not || 'cannot be read here') }),
      ].filter(Boolean)));
    }
    box.appendChild(list);

    const vers = (cur && cur.versions) || [];
    if (vers.length) {
      box.appendChild(el('div', { class: 'section-label',
                                  text: 'Read the stamps from' }));
      const want = defaultVersion(cur);
      /* The version tree (constitution §6e): the lineage, newest on top,
         with Root Canal's own output and the default said on the row. It
         was a list of radios, oldest first. */
      box.appendChild(el('div', { class: 'rc-vers' }, [BARRY.ui.versionTree({
        versions: vers,
        // What produced the set, as a chip above it (2026-10-20).
        producer: (cur || {}).pipeline,
        producerType: (cur || {}).type,
        idOf: versionRef,
        value: q.from_version,
        unit: 'stamps',
        disabled: (v) => (usable(v) ? null : (v.why_not || 'not readable here')),
        /* The tree says "aligned" on the rows that are; "not aligned" on
           every other row was the same two words eight times over, and
           the warning under the tree says it where it matters (2026-10-19). */
        state: (v) => [
          v.tag === 'rootcanal' ? 'Root Canal’s own output' : null,
          want && versionRef(want) === versionRef(v) ? 'the default' : null,
        ].filter(Boolean),
        onpick: (v) => {
          q.from_version = versionRef(v);
          forget();
          render();
        },
      })]));
      if (want && want.tag !== 'rootcanal'
          && vers.some((v) => v.tag === 'rootcanal')) {
        box.appendChild(el('p', { class: 'hint', text:
          'Reading from v' + want.name + ', the version the last Root Canal '
          + 'started from, not from its output: a second pass over a set '
          + 'that has already been cleaned would still split it in two, and '
          + 'the "IEDs" it found would be the loudest dentate spikes.' }));
      }
    }
    if (cur && !cur.aligned) {
      box.appendChild(el('p', { class: 'hint rc-warn', text:
        'Nothing in this set has been through Braces. Amplitude and '
        + 'half-width are measured about the stamp, so stamps a few '
        + 'milliseconds out measure a smear. Step 3 first is worth it.' }));
    }
    if (q.read) {
      box.appendChild(BARRY.ui.actions([
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Fold this away',
          onclick: () => { chooserOpen = false; render(); } }),
      ]));
    }
    return box;
  }

  function readCard() {
    const cur = setOf();
    if (!cur) return el('div', {});
    const v = versionOf(cur, q.from_version);
    const n = (v && v.n) || cur.n;
    const vs = ((single && single.versions) || []).slice().reverse();
    return el('div', { class: 'card rc-read' }, [
      /* Saved versions open from their numbers, here or on any machine:
         the read is only needed to change their settings or see traces. */
      singleBanked.length ? el('div', { class: 'chip-row rc-import' },
                               importButtons()) : null,
      vs.length ? el('div', { class: 'rc-saved-versions' }, [
        el('p', { class: 'hint', text: 'Saved versions of this set. Each '
          + 'opens from its numbers, without a read, on any machine.' }),
        el('div', { class: 'chip-row' }, vs.map((x) => BARRY.ui.button({
          kind: 'ghost', size: 'sm', extra: 'rc-open-ver',
          text: 'Open v' + x.v + ' · ' + (x.nickname || 'no nickname'),
          title: versionHover(x),
          onclick: () => openVersion(single.artifact_id, x.v) })).concat([
          BARRY.syncState ? BARRY.syncState.mark('artifacts',
                                                 single.artifact_id) : null,
        ].filter(Boolean))),
      ]) : null,
      el('p', { class: 'hint', text:
        'Reading takes every event on every contact at 5 kHz: a ±250 ms '
        + 'snippet kept at 2 kHz, and the event and baseline spectra. That '
        + 'is minutes the first time and cached after, and it is what lets '
        + 'the filter and the band be changed afterwards without touching '
        + 'the disk again.' }),
      BARRY.ui.actions([
        BARRY.ui.button({ kind: 'primary', text: 'Read ' + n + ' events',
          disabled: cur.readable === false || busy,
          onclick: () => startRead() }),
      ]),
    ].filter(Boolean));
  }

  /* ==================================================================
     Saved versions of a Single
     ================================================================== */
  const SIG_KEYS = ['filt', 'mains_out', 'lo_hz', 'hi_hz', 'win_ms', 'band_lo',
                    'band_hi', 'cross_ms', 'k', 'complete_only',
                    'cluster_calls', 'cluster_names', 'margin', 'drawn',
                    'retry', 'flips', 'centres'];
  const SIG_WORDS = { filt: 'the filter', mains_out: 'the mains',
    lo_hz: 'the filter', hi_hz: 'the filter', win_ms: 'the amplitude window',
    band_lo: 'the HF band', band_hi: 'the HF band',
    cross_ms: 'the half-width search', k: 'k',
    complete_only: 'only events on all 3 axes', cluster_calls: 'the calls',
    cluster_names: 'the names',
    margin: 'the calls it carried', drawn: 'the drawn clusters',
    retry: 'the events searched again', flips: 'the flips',
    centres: 'the centres' };

  function sigOf(body) {
    const b = body || fitBody();
    const keep = {};
    for (const k of SIG_KEYS) keep[k] = b[k] === undefined ? null : b[k];
    return JSON.stringify(keep);
  }

  function isDirty() {
    return !!(fit && fit.ok && !savedOnly && cleanSig != null
              && sigOf() !== cleanSig);
  }

  function changedWords() {
    let was = {};
    try { was = JSON.parse(cleanSig || '{}'); } catch (e) { was = {}; }
    const now = JSON.parse(sigOf());
    const out = [];
    for (const k of SIG_KEYS) {
      if (JSON.stringify(was[k]) !== JSON.stringify(now[k])
          && out.indexOf(SIG_WORDS[k]) < 0) out.push(SIG_WORDS[k]);
    }
    return out.join(', ') || 'the settings';
  }

  async function loadSingle() {
    const entry = q.entry;
    const mine = ++singleGen;
    if (!entry) { single = null; return; }
    let got;
    try {
      got = await api('/api/rootcanal/singles?entry_id='
                      + encodeURIComponent(entry));
    } catch (e) {
      return;            // no list is no versions; the panel still works
    }
    if (mine !== singleGen || q.entry !== entry) return;
    single = (got.singles || [])[0] || null;
    singleBanked = got.banked || [];
    singleRender();
  }

  /* A banked result kept as the next version: from its read where it is
     here, from the numbers the bank filed where it is not. */
  async function importBanked(b) {
    let rep;
    try {
      rep = await apiPost('/api/rootcanal/single/import', {
        entry_id: q.entry, params_hash: b.params_hash });
    } catch (e) {
      toast('It could not be imported: ' + e.message, 'err', 9000);
      return null;
    }
    single = rep.single;
    singleBanked = singleBanked.filter((x) => x.params_hash !== b.params_hash);
    toast(rep.confirmed ? 'It was already v' + rep.version + ', so that '
          + 'version is confirmed.' : 'Kept as v' + rep.version
          + ' of this set.', rep.confirmed ? 'warn' : 'ok', 8000);
    BARRY.activity.log('rootcanal.single_import', {
      artifact: rep.artifact_id, version: rep.version, entry: q.entry });
    loadDone(true);
    render();
    return rep;
  }

  /* Ghost and small, as Save and Open beside them are (2026-10-19: they were
     minis, a size smaller than the buttons on either side of them). */
  function importButtons() {
    return singleBanked.map((b) => BARRY.ui.button({ kind: 'ghost', size: 'sm',
      extra: 'rc-import-banked',
      text: 'Keep banked v' + b.ds_version + ' as a saved version',
      title: 'Banked ' + String(b.at || '').replace('T', ' ').slice(0, 16)
        + (b.k ? ' at k = ' + b.k : '') + ': ' + (b.counts.ds || 0) + ' DS, '
        + (b.counts.ied || 0) + ' IED. Kept '
        + (b.here ? 'from its read, refitted' : 'from the numbers the bank '
                    + 'filed (its read is not on this machine)')
        + ', so it can be pooled and reopened like any version.',
      onclick: () => importBanked(b) }));
  }

  function nextVersion() {
    const vs = (single && single.versions) || [];
    return vs.length ? Math.max.apply(null, vs.map((x) => x.v)) + 1 : 1;
  }

  /* What a version is, for its hover: settings, counts, who/when/where. */
  function versionHover(x) {
    if (!x) return '';
    const m = x.measure || {};
    const ns = x.n_summary || {};
    const set = ['k' + (x.k != null ? x.k : '?'),
                 m.filter_label || 'filter not recorded',
                 m.band_lo != null ? hz(m.band_lo) + '–' + hz(m.band_hi)
                                     + ' Hz power' : null,
                 m.win_ms != null ? 'amplitude ±' + hz(m.win_ms) + ' ms' : null,
                 m.cross_ms != null ? 'half-width search ±' + hz(m.cross_ms)
                                      + ' ms' : null,
                 x.complete_only ? 'only events on all 3 axes' : null,
                 x.retry ? x.retry + ' searched again' : null,
                 x.margin ? 'calls carried from a pool' : null].filter(Boolean);
    const cnt = [ns.events != null ? ns.events + ' events' : null,
                 ns.ds != null ? ns.ds + ' DS' : null,
                 ns.ied != null ? ns.ied + ' IED' : null,
                 (ns.names || []).length ? 'names: ' + ns.names.join(', ')
                                         : null].filter(Boolean);
    return ['v' + x.v + ' · ' + (x.nickname || 'no nickname'),
            'Settings: ' + set.join(' · '),
            'Counts: ' + (cnt.join(' · ') || 'not recorded'),
            ns.stats ? 'Are the clusters different? ' + verdictWords(ns.stats)
                       + ' (SigClust)'
              : (x.k === 2 ? 'Are the clusters different? not tested' : null),
            'Saved by ' + (x.by || 'someone') + (x.machine ? ' on '
              + x.machine : '') + (x.at ? ', ' + String(x.at).replace('T', ' ')
              .slice(0, 16) : '') + (x.app_version ? ' (Jarvis '
              + x.app_version + ')' : ''),
            x.confirmed ? 'Confirmed ' + x.confirmed + ' time'
              + (x.confirmed === 1 ? '' : 's') + ' since' : null,
            x.note ? 'Note: ' + x.note : null].filter(Boolean).join('\n');
  }

  /* The picker and Save, beside Bank. */
  function versionStrip() {
    const vs = ((single && single.versions) || []).slice().reverse();
    const cur = viewing && single && viewing.artifact_id === single.artifact_id
      ? vs.find((x) => x.v === viewing.v) : null;
    const dirty = isDirty();
    const out = [];
    if (vs.length) {
      /* A MENU, NOT A SELECT (2026-10-20). A select is as wide as its
         longest option, and a version saved from a pool is named for it
         ("v2 · from pool ‘PTEN ALL PTEN Baseline Full Incisor’ v1"): the
         row of counts wrapped to a third line round it, and the picked
         event's bar went below the fold (952 px down on a 908 screen). The
         closed menu says which version is up, short; open, it lists every
         version by its whole name, wrapped, with its hover. */
      const det = el('details', { class: 'rc-ver-pick' }, [
        el('summary', {
          class: 'rc-ver-sum',
          title: cur ? versionHover(cur) + (dirty ? '\n(changed since)' : '')
                     : 'Saved versions of this set. Pick one to open it.',
          text: (cur ? 'v' + cur.v + (dirty ? ' (changed)' : '')
                     : (dirty ? 'not saved: changed' : 'not saved as a version'))
                + '  ·  ' + vs.length + ' saved ▾',
        }),
        el('div', { class: 'rc-ver-pop' }, vs.map((x) => el('button', {
          type: 'button',
          class: 'rc-ver-opt' + (cur && cur.v === x.v ? ' on' : ''),
          title: versionHover(x),
          'data-v': String(x.v),
          text: 'v' + x.v + ' · ' + (x.nickname || 'no nickname'),
          onclick: () => {
            det.open = false;
            const go = () => openVersion(single.artifact_id, x.v);
            if (isDirty()) nudgeThen(go); else go();
          },
        }))),
      ]);
      // Shut by a press anywhere else, as the mode bar's More is.
      if (!versionStrip.wired) {
        versionStrip.wired = true;
        document.addEventListener('mousedown', (e) => {
          for (const d of document.querySelectorAll('details.rc-ver-pick[open]')) {
            if (!d.contains(e.target)) d.open = false;
          }
        });
      }
      out.push(det);
      if (BARRY.syncState) {
        out.push(BARRY.syncState.mark('artifacts', single.artifact_id));
      }
    }
    for (const b of importButtons()) out.push(b);
    out.push(BARRY.ui.button({ kind: 'ghost', size: 'sm',
      text: 'Save as v' + nextVersion() + '…', extra: 'rc-save-ver',
      disabled: fitting || !fit || !fit.ok || !!savedOnly,
      title: 'Keep this picture -- every event’s numbers and call, and the '
           + 'settings that made them -- as a version you can reopen and pool '
           + 'on any machine. Nothing goes to the Event Bank.',
      onclick: saveVersionDialog }));
    return out;
  }

  function refusedSavedOnly() {
    toast('This version is drawn from its saved numbers; its read is on '
          + (savedOnly ? savedOnly.read_on : 'another machine')
          + '. Read the set here to change its settings.', 'warn', 8000);
  }

  async function saveVersionDialog() {
    if (!fit || !fit.ok || fitting || savedOnly) return null;
    let sug = '';
    try {
      sug = (await apiPost('/api/rootcanal/single/suggest', fitBody()))
        .nickname || '';
    } catch (e) { /* a name can still be typed */ }
    const cur = setOf();
    const nv = nextVersion();
    const what = el('div', { class: 'rc-ask' }, [
      el('p', { text: 'Keeps this picture as v' + nv + ' of '
        + ((cur && (cur.session_label || cur.name)) || 'this set')
        + ': every event’s three numbers and its call, with the settings '
        + 'that made them. If nothing has changed since a saved version, '
        + 'that one is confirmed and no new one is made.' }),
      el('ul', {}, [
        el('li', { text: 'A few kilobytes, shared with every machine: it '
          + 'reopens and pools anywhere, without this recording’s read.' }),
        el('li', { text: 'Nothing is written to the Event Bank. Bank does '
          + 'that, and keeps a version of its own.' }),
      ]),
    ]);
    let rep = null;
    return BARRY.ui.bankDialog({
      kind: 'entry',
      title: 'Save this as v' + nv,
      name: sug,
      what,
      okText: 'Save as v' + nv,
      onBank: async ({ name, note }) => {
        const nick = String(name || '').trim();
        if (!nick) throw new Error('A version needs a nickname.');
        rep = await apiPost('/api/rootcanal/single/save',
                            fitBody({ nickname: nick, note: note || '' }));
      },
    }).then((ok) => {
      if (!ok || !rep) return null;
      single = rep.single;
      const row = (single.versions || []).find((x) => x.v === rep.version);
      viewing = { artifact_id: rep.artifact_id, v: rep.version,
                  nickname: row ? row.nickname : null };
      cleanSig = sigOf();
      toast(rep.confirmed
        ? 'Nothing has changed since v' + rep.version + ', so that version '
          + 'is confirmed rather than a new one made.'
        : 'Saved as v' + rep.version + ' of this set.',
        rep.confirmed ? 'warn' : 'ok', 8000);
      BARRY.activity.log('rootcanal.single_save', {
        artifact: rep.artifact_id, version: rep.version,
        confirmed: rep.confirmed, entry: q.entry });
      loadDone(true);
      render();
      return rep;
    });
  }

  /* Open a saved version. Its settings come back into the controls. Where
     its read is here it is refitted from the read (traces and all); where
     it is not, it is drawn from its numbers, read-only. */
  async function openVersion(aid, v) {
    let got;
    try {
      got = await api('/api/rootcanal/single/' + encodeURIComponent(aid)
                      + '?version=' + encodeURIComponent(v));
    } catch (e) {
      toast('That version could not be opened: ' + e.message, 'err', 9000);
      return null;
    }
    const pay = got.payload || {};
    const pp = pay.params || {};
    for (const k of PKEYS) {
      if (pp[k] != null) { q[k] = asParam(k, pp[k]); pend[k] = q[k]; }
    }
    q.cluster_calls = Object.assign({}, pp.cluster_calls || {});
    q.cluster_names = JSON.parse(JSON.stringify(pp.cluster_names || {}));
    q.margin = pp.margin || null;
    q.drawn = (pp.drawn || []).map((g) => ({ events: (g.events || []).slice(),
                                            call: g.call }));
    q.retry = (pp.retry || []).slice();
    q.flips = (pp.flips || []).slice();
    q.centres = pp.centres ? pp.centres.map((c) => c.slice()) : null;
    if (pay.from_version != null) q.from_version = pay.from_version;
    viewing = { artifact_id: aid, v: got.version, nickname: got.nickname };
    avg = null; lassoSel = []; picked = null; evData = null; evKey = null;
    chooserOpen = false;
    q.read = pay.read;
    if (got.here) {
      savedOnly = null;
      cleanSig = sigOf();
      refit();
    } else {
      savedOnly = { read_on: pay.read_on || 'another machine' };
      fit = Object.assign({ ok: true }, got.fit);
      cleanSig = sigOf();
      render();
    }
    BARRY.activity.log('rootcanal.single_open', { artifact: aid,
                                                  version: got.version,
                                                  here: !!got.here });
    return got;
  }

  /* "Save as vN?" before leaving a changed picture -- yes by default. */
  function nudgeThen(go) {
    const nv = nextVersion();
    showModal(el('div', { class: 'rc-nudge' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Save this as v' + nv + ' first?' }),
        el('div', { class: 'spacer' })]),
      el('div', { class: 'mb' }, [el('div', { class: 'rc-ask' }, [
        el('p', { text: 'This set’s picture has changed since it was '
          + (viewing ? 'opened from v' + viewing.v : 'first fitted')
          + ': ' + changedWords() + '. Saved, it is a version you can '
          + 'reopen and pool on any machine.' }),
      ])]),
      BARRY.ui.modalFoot([], [
        BARRY.ui.button({ kind: 'ghost', text: 'Leave without saving',
          extra: 'rc-nudge-skip',
          onclick: () => { closeModal(); cleanSig = null; go(); } }),
        BARRY.ui.button({ kind: 'primary', text: 'Save as v' + nv + '…',
          extra: 'rc-nudge-save',
          onclick: () => {
            closeModal();
            saveVersionDialog().then((rep) => { if (rep) go(); });
          } }),
      ]),
    ]), { replace: true });
  }

  /* The read, while it runs.

     A loader rather than a bar alone, because a bar that has not moved in a
     minute looks exactly like a hang: the words say what is being read and
     how far through it is. Updated IN PLACE on each tick rather than
     replaced -- a replaced loader restarts its animation twice a second,
     and a replaced card is still a card that could take the feed with it. */
  function progress() {
    const st = (job && job.stages && job.stages[0]) || {};
    const frac = st.of ? Math.min(1, (st.done || 0) / st.of) : 0;
    const cur = setOf();
    return el('div', { class: 'card rc-job' }, [
      loader('Reading ' + ((cur && cur.session_label) || 'the recording')
             + ' at 5 kHz', jobWords()),
      el('div', { class: 'rc-bar' }, [
        el('i', { style: 'width:' + (100 * frac).toFixed(1) + '%' })]),
      BARRY.ui.actions([
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Stop',
          title: 'Stop the read. Nothing from it is kept.',
          onclick: async () => {
            try { await apiPost('/api/cfc/job/' + job.id + '/cancel', {}); }
            catch (e) { /* it may already be done */ }
          } }),
      ]),
    ]);
  }

  function jobWords() {
    const st = (job && job.stages && job.stages[0]) || {};
    const done = st.done || 0;
    if (done !== jobSeen.done) jobSeen = { done, at: Date.now() };
    const still = Date.now() - jobSeen.at;
    return done + ' of ' + (st.of || '?') + ' ' + (st.unit || 'events')
      + (job && job.eta_s ? '  ·  about ' + Math.ceil(job.eta_s) + ' s left'
                          : '')
      /* Said when it is taking longer than it should. A network drive that
         has gone to sleep looks, from here, exactly like a slow read. */
      + (still > 30000 && done
         ? '  ·  no progress for ' + Math.round(still / 1000) + ' s — a '
           + 'drive that has gone to sleep looks like this'
         : '');
  }

  function tickJob() {
    const box = host();
    const card = box && box.querySelector('.rc-job');
    if (!card) return false;
    const st = (job && job.stages && job.stages[0]) || {};
    const frac = st.of ? Math.min(1, (st.done || 0) / st.of) : 0;
    const sub = card.querySelector('.loader-text span');
    if (sub) sub.textContent = jobWords();
    const bar = card.querySelector('.rc-bar > i');
    if (bar) bar.style.width = (100 * frac).toFixed(1) + '%';
    return true;
  }

  /* ---------- 3. the workbench ---------- */
  function workbench() {
    if (fit && !fit.ok) {
      return el('div', { class: 'rc-work' }, [
        busyLine(),
        controlsBar(),
        el('div', { class: 'card rc-err' }, [
          el('strong', { text: 'That could not be fitted' }),
          el('p', { class: 'hint', text: fit.error }),
        ]),
      ]);
    }
    if (!fit) {
      return el('div', { class: 'rc-work' }, [
        busyLine(), loading('Fitting', 'the first answer for this read')]);
    }
    return el('div', { class: 'rc-work' }, [
      busyLine(),
      controlsBar(),
      whyBar(),
      lassoBar(),
      pickBar(),
      legend(),
      el('div', { class: 'rc-main' }, [
        spacePane(),
        flatsPane(),
        eventPane(),
      ]),
    ]);
  }

  /* What the panel is doing, while it is doing it. One loader, and the size
     of the job said -- not a stepLoader, because a fit is one request that
     has either returned or not. Always in the tree, so it can be swapped. */
  function busyLine() {
    if (viewMode === 'pooled') return poolBusyLine();
    const n = fit && fit.ok ? fit.n : null;
    const what = fitting
      ? 'Fitting' + (n ? ' ' + n + ' events' : '')
        + ' — filter, max contact, half-width, band power, k-means'
      : evBusy ? 'Reading event ' + (picked == null ? '' : picked + 1)
               + ' — its trace, spectrum and the probe around it'
      : null;
    if (!what) return el('div', { class: 'rc-busy' });
    return el('div', { class: 'rc-busy on' }, [loader(what)]);
  }

  function tickBusy() { swap('.rc-busy', busyLine()); }

  /* The settings the picture is computed with, and whether the picture is
     still computed with them.

     Off `fit.params`, never off the form: the form is what has been ASKED
     for, and the chart under the chip is the previous answer until
     Recompute lands. A chip that renamed the picture before the picture
     changed would be a label saying something untrue about what you are
     looking at. */
  function shownParams() {
    const p = Object.assign({}, lastBody || {}, (fit && fit.params) || {});
    for (const k of PKEYS) if (p[k] == null) p[k] = q[k];
    return p;
  }

  const hz = (v) => {
    const x = Number(v);
    return isFinite(x) ? String(Math.round(x * 100) / 100) : '?';
  };

  function hfLabel(p) {
    const pp = p || shownParams();
    // A pool can hold members measured in different bands, so it says its
    // own: the server's axis label, never one reconstructed here.
    if (pp && pp.hf_label) return pp.hf_label;
    return hz(pp.band_lo) + '–' + hz(pp.band_hi) + ' Hz power · dB re baseline';
  }

  /* k comes from a margin when one is applied in the view that is open. */
  function kFromMargin() {
    const r = viewMode === 'pooled' ? pool.margin : q.margin;
    // Its name, or `true` while the name is not known yet.
    return r ? (marginNick(r) || true) : null;
  }

  /* The pool's own statement of what it was measured and clustered with,
     in the same keys Single's chip reads. */
  function poolShownParams() {
    const f = pool.fit && pool.fit.ok ? pool.fit : null;
    const m = (f && f.params && f.params.measure) || null;
    if (!m) return Object.assign({}, q);
    return Object.assign({}, m, { k: f.k, complete_only: f.params.complete_only });
  }

  function modeChip() {
    const p = viewMode === 'pooled' ? poolShownParams() : shownParams();
    const stale = pending() || (viewMode === 'pooled' ? pool.fitting : fitting);
    return el('span', {
      class: 'rc-chip' + (stale ? ' rc-chip-stale' : ''),
      title: stale
        ? 'This picture is still the previous answer, computed with these '
          + 'settings. Recompute to see the new ones.'
        : 'The filter and the band this picture was computed with.',
      text: filterWords(p, true) + '  ·  ±'
            + hz(p.win_ms) + ' ms  ·  half-width ±'
            + hz(p.cross_ms != null ? p.cross_ms : q.cross_ms) + ' ms  ·  '
            + hz(p.band_lo) + '–' + hz(p.band_hi)
            + ' Hz band  ·  k = ' + (p.k || 2)
            + (p.complete_only ? '  ·  3 axes only' : '')
            + (stale ? '  (recompute)' : ''),
    });
  }

  /* The fit settings, in one compact row. */
  function controlsBar() {
    const num = (k, label, o) => el('label', { class: 'rc-num',
                                              title: o.title }, [
      el('span', { class: 'rc-num-l', text: label }),
      el('input', {
        type: 'number', class: 'rc-in' + (o.extra ? ' ' + o.extra : ''),
        value: String(pend[k]),
        min: o.min, max: o.max, step: o.step || 'any',
        oninput: (e) => { pend[k] = e.target.value; tickPending(); },
        /* Clamped to the field's own limits when it is left, so a band
           typed past the anti-alias corner comes back to it where it can be
           seen, rather than sitting there waiting to be refused. */
        onchange: (e) => {
          const v = clampTo(e.target.value, o.min, o.max);
          if (v !== e.target.value) e.target.value = v;
          pend[k] = v;
          tickPending();
        },
        onkeydown: (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            const v = clampTo(e.target.value, o.min, o.max);
            e.target.value = v;
            pend[k] = v;
            recompute();
          }
        },
      }),
      el('span', { class: 'rc-num-u', text: o.unit }),
    ]);
    const bad = problems(pend);
    const p = pending();
    return el('div', { class: 'card rc-controls' }, [
      el('div', { class: 'rc-group' }, [
        el('span', { class: 'rc-group-l', text: 'Amplitude and width' }),
        el('span', { class: 'rc-num-l', text: 'filter' }),
        BARRY.ui.seg(FILTER_ORDER.map((k) => [k, FILTERS[k].label,
                                              FILTERS[k].title]),
          pend.filt, (v) => applyNow('filt', v),
          { extra: 'rc-filt' }),
        pend.filt === 'custom' ? num('lo_hz', '', { unit: '–', min: 0,
          max: LP_MAX, title: 'The low corner of the zero-phase filter '
          + 'amplitude and half-width are measured through. 0 makes it a '
          + 'low-pass.' }) : null,
        pend.filt === 'custom' ? num('hi_hz', '', { unit: 'Hz', min: 1,
          max: LP_MAX, title: 'The high corner. The snippets are kept at '
          + '2 kHz, so up to ' + LP_MAX + ' Hz means something.' }) : null,
        pend.filt === 'custom' ? el('label', { class: 'rc-num rc-mains',
          title: 'Fit the 60 Hz mains out of each contact before filtering, '
               + 'the way the CSD’s is. On PTEN m1 s2 the mains left in '
               + 'put 23 of 64 events’ measurement on a mains-heavy '
               + 'contact.' }, [
          el('input', { type: 'checkbox',
            checked: asParam('mains_out', pend.mains_out) ? 'checked' : null,
            onchange: (e) => applyNow('mains_out', e.target.checked) }),
          el('span', { class: 'rc-num-l', text: '60 Hz out' }),
        ]) : el('span', { class: 'hint rc-filt-is',
                          text: filterWords(pend).replace(/^\S+ /, '') }),
        null,
      ].filter(Boolean)),
      el('div', { class: 'rc-group rc-k' }, [
        el('span', { class: 'rc-group-l', text: 'Clusters' }),
        kControl(pend.k, (v) => applyNow('k', v), kFromMargin()),
        el('label', { class: 'rc-num rc-complete',
          title: 'Leave out every event missing an axis -- a half-width that '
               + 'never came back to half amplitude, an HF window too near an '
               + 'edge -- instead of placing it on the two it has. Counted as '
               + 'left out; in Pooled not drawn.' }, [
          el('input', { type: 'checkbox',
            checked: asParam('complete_only', pend.complete_only) ? 'checked' : null,
            onchange: (e) => applyNow('complete_only', e.target.checked) }),
          el('span', { class: 'rc-num-l', text: 'only events on all 3 axes' }),
        ]),
      ]),
      el('div', { class: 'rc-group' }, [
        el('span', { class: 'rc-group-l', text: 'Window and search' }),
        num('win_ms', 'window ±', { unit: 'ms', min: 1, max: WIN_MAX, title:
          'How far either side of the stamp the max-amp contact and its '
          + 'peak are looked for. v4 used 25 ms.' }),
        num('cross_ms', 'half-width search ±', { unit: 'ms', min: CROSS_MIN,
          max: CROSS_MAX, extra: 'rc-in-cross', title:
          'How far either side of the peak the trace is followed back down '
          + 'to half amplitude. v1 used 50 ms. Wider finds the slow events; '
          + 'every one found only that way is marked “widened”, and one '
          + 'still not found is placed on its other two axes and marked.' }),
      ]),
      el('div', { class: 'rc-group' }, [
        el('span', { class: 'rc-group-l', text: 'HF power' }),
        num('band_lo', 'band', { unit: '–', min: 0, max: BAND_MAX, title:
          'The low edge of the band HF power is integrated over. v5 used '
          + '500 Hz.' }),
        num('band_hi', '', { unit: 'Hz', min: 1, max: BAND_MAX, title:
          'The high edge. v5 used 1000 Hz; the read is 5 kHz, so the edge '
          + 'stops at ' + BAND_MAX + ' Hz, where its anti-alias filter '
          + 'begins.' }),
      ]),
      el('span', { class: 'spacer' }),
      el('span', { class: 'hint rc-pend' + (p ? ' on' : ''), text: p
        ? (bad.length ? 'Not yet: ' + bad[0] + '.'
                      : 'Changed — the picture is the old settings until '
                        + 'Recompute.')
        : '' }),
      BARRY.ui.actions([
        viewMode === 'pooled' ? null : BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'reset centres',
          disabled: !q.centres || fitting,
          title: 'Put both centres back where k-means placed them.',
          onclick: resetCentres }),
        viewMode === 'pooled' ? null : BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: 'clear flips' + (q.flips.length ? ' (' + q.flips.length + ')'
                                                 : ''),
          disabled: !q.flips.length || fitting,
          title: 'Undo every class set by hand.',
          onclick: clearFlips }),
        p ? BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'put them back',
              title: 'Go back to the settings the picture was computed with.',
              onclick: revertPending }) : null,
        BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: (viewMode === 'pooled' ? pool.fitting : fitting)
            ? 'Recomputing…' : 'Recompute ↵',
          extra: 'rc-recompute',
          disabled: !p || bad.length
                    || (viewMode === 'pooled' ? pool.fitting : fitting),
          title: 'Refit with the settings typed here. Or press Enter in any '
               + 'of them. The read is not touched.',
          onclick: recompute }),
      ], { extra: 'rc-acts' }),
    ]);
  }

  /* The pending hint, the Recompute button's state and the stale chips,
     without rebuilding the row the person is typing in. */
  function tickPending() {
    const box = host();
    if (!box) return;
    const p = pending();
    const bad = problems(pend);
    const hint = box.querySelector('.rc-pend');
    if (hint) {
      hint.classList.toggle('on', p);
      hint.textContent = p ? (bad.length ? 'Not yet: ' + bad[0] + '.'
                                         : 'Changed — the picture is the old '
                                           + 'settings until Recompute.')
                           : '';
    }
    const go = box.querySelector('.rc-recompute');
    if (go) go.disabled = !p || !!bad.length
                          || (viewMode === 'pooled' ? pool.fitting : fitting);
    for (const c of box.querySelectorAll('.rc-chip:not(.rc-pool-chip)')) {
      c.replaceWith(modeChip());
    }
  }

  /* After Recompute, or a revert: the controls row and the chips. */
  function swapTop() {
    swap('.rc-controls', controlsBar());
    tickPending();
  }

  /* THE "WHY" LINE, and the one thing this panel is for doing.

     The naming rule in the server's own words, because "which cluster was
     called IED" is a decision with a reason and the reason is two numbers
     that can be read. The Bank button says what it will write, in numbers,
     before it is pressed. */
  function whyBar() {
    const c = fit.counts || {};
    const cs = fit.centres || [];
    const kids = [
      el('div', { class: 'rc-why-t' }, [
        el('p', { class: 'rc-rule', text: fit.rule || '' }),
        el('div', { class: 'chip-row' }, [
          chipC('DS ' + (c.ds || 0), 'ds'),
          chipC('IED ' + (c.ied || 0), 'ied'),
          c.unmeasured ? BARRY.ui.chip((c.unmeasured) + ' not measured', {
            title: 'An unresolved half-width or a missed HF window. Left out '
                 + 'of the clustering and drawn hollow — never filled in.' })
                       : null,
          q.flips.length ? BARRY.ui.chip(q.flips.length + ' set by hand', {
            kind: 'warn' }) : null,
          q.centres ? BARRY.ui.chip('centres moved by hand', { kind: 'warn' })
                    : null,
          /* PLACED, not fitted: `n_used` is the complete events k-means
             was fitted on, and `n_placed` adds the ones put on their two
             axes afterwards. The second is how many have a class. */
          c.partial ? BARRY.ui.chip(c.partial + ' on 2 of 3 axes', {
            kind: 'warn', extra: 'rc-count-partial',
            title: 'Placed by the nearest centre on the two axes they have. '
                 + 'Drawn as squares.' }) : null,
          (() => {
            const n = (fit.events || []).filter(canRetry).length;
            return n ? BARRY.ui.button({ kind: 'mini', extra: 'rc-retry-all',
              text: 'Search the ' + n + ' with no half-width again, to ±'
                    + hz(retryMs()) + ' ms',
              title: 'Each of them is measured once more out to the widest '
                   + 'search the stored waveform allows. Everything else '
                   + 'keeps its numbers. Found ones are marked.',
              onclick: () => retryWider((fit.events || []).filter(canRetry)
                                        .map((e) => e.i)) }) : null;
          })(),
          c.wide ? BARRY.ui.chip(c.wide + ' by the widened search', {
            kind: 'warn', extra: 'rc-count-wide',
            title: 'Their half-width was found only with the search reaching '
                 + 'past v1’s ' + CROSS_V1 + ' ms. Drawn with a dashed '
                 + 'outline.' }) : null,
          cs.length ? (() => {
            const placed = fit.n_placed != null ? fit.n_placed : fit.n_used;
            return BARRY.ui.chip(placed === fit.n ? 'all ' + fit.n + ' classified'
                                 : placed + ' of ' + fit.n + ' classified');
          })() : null,
          /* Its saved versions and Save, in the row of counts: beside Bank
             they made the card a line taller and put the picked event's
             bar below the fold (measured: 912 px down on a 908 screen). */
          ...versionStrip(),
        ].filter(Boolean)),
        clusterChips(fit.clusters,
          (rank, call) => {
            // A drawn cluster's call is its drawing's; the rest are relabels.
            const dj = rank - (fit.k || 0);
            if (dj >= 0 && q.drawn[dj]) q.drawn[dj].call = call;
            else q.cluster_calls[String(rank)] = call;
            refit();
          },
          () => { q.cluster_calls = {}; refit(); },
          (fit.clusters || []).some((c) => c.call_by === 'hand'),
          { onName: (c) => nameDialog(c, (nm) => {
              if (nm) q.cluster_names[String(c.rank)] = nm;
              else delete q.cluster_names[String(c.rank)];
              refit();
            }),
            onAvg: (c) => showAverage('cluster #' + (c.rank + 1) + ' '
                                       + (c.name || c.call.toUpperCase()),
                                       (fit.events || []).filter(
                                         (e) => e.cluster === c.rank)),
            onRemove: (c) => { q.drawn.splice(c.rank - (fit.k || 0), 1);
                               refit(); },
            /* Beside the clusters it asks about, SHORT: at 455 px wide
               the row has 116 px left after two clusters (the counts row
               65), and a control that wraps either one puts the picked
               event's bar below the fold (measured: 910 on a 908 screen,
               882 without it). */
            tail: statsButton('single') }),
        // Margins were taken out on 2026-10-21; the Borders fold is the one.
        el('div', { class: 'rc-folds' }, [
          bordersCard(singleBorderCtx()),
        ]),
      ]),
      savedOnly ? el('p', { class: 'hint rc-warn rc-saved-only', text:
        'Drawn from v' + (viewing ? viewing.v : '?') + '’s saved numbers. Its '
        + 'read is on ' + savedOnly.read_on + ', so the settings cannot be '
        + 'changed and the traces cannot be opened here.' }) : null,
      BARRY.ui.actions([
        savedOnly ? BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: 'Read the set here', extra: 'rc-read-here',
          title: 'Read this set on this machine, then work on it as usual. '
               + 'Minutes, once.',
          onclick: () => { savedOnly = null; q.read = null; fit = null;
                           render(); startRead(); } }) : null,
        BARRY.ui.button({ kind: 'primary', text: bankLabel(),
          extra: 'rc-bank',
          disabled: fitting || !fit.ok || !!savedOnly,
          title: 'Bank the DS class as the next version of this set and the '
               + 'IED class as a set of candidate IEDs. A dialog first.',
          onclick: bankDialog }),
      ].filter(Boolean)),
    ];
    return el('div', { class: 'card rc-why' }, kids.filter(Boolean));
  }

  /* How many clusters: a seg of 1..6, or -- for a version or a pool that
     carries its own calls (a single saved from a pool is made that way) --
     a line saying where they come from, and a way to fit afresh. Margins
     themselves were taken out on 2026-10-21; nothing can apply one now. */
  function kControl(cur, onPick, fromMargin) {
    if (fromMargin) {
      return el('span', { class: 'rc-k-margin' }, [
        el('span', { class: 'hint', text: 'k and the calls are this '
          + (viewMode === 'pooled' ? 'pool' : 'version') + '’s own'
          + (typeof fromMargin === 'string' ? ', from ‘' + fromMargin + '’'
                                            : ', saved with it') }),
        BARRY.ui.button({ kind: 'mini', text: 'Fit afresh',
          extra: 'rc-fit-afresh',
          title: 'Let k-means find the clusters again, at the k you pick.',
          onclick: () => {
            if (viewMode === 'pooled') {
              pool.margin = null; pool.marginErr = null; runPool();
              return;
            }
            /* Read elsewhere, there is nothing here to fit afresh from: said,
               and the calls kept -- as every other setting is. */
            if (savedOnly) { refusedSavedOnly(); return; }
            q.margin = null; marginErr = null; refit();
          } }),
      ]);
    }
    return BARRY.ui.seg(
      Array.from({ length: K_MAX }, (_, j) => [String(j + 1), String(j + 1),
        j === 0 ? 'One cluster: no split, every event DS — the null a split '
                  + 'is compared against.'
        : j === 1 ? 'Two clusters: DS and IED, as this tool was built.'
        : (j + 1) + ' clusters, ranked by HF power; the highest is IED by '
          + 'the rule, and any can be relabelled.']),
      String(cur), (v) => onPick(Number(v)), { extra: 'rc-kseg' });
  }

  /* One chip per cluster, lowest HF first: its colour, n, its centre in
     raw units and its call -- and pressing it calls that cluster the other
     thing. The rule's call, a carried one and a hand's are said apart. */
  function clusterChips(clusters, onToggle, onReset, anyHand, more) {
    if (!clusters || !clusters.length) return null;
    const ex = more || {};
    const row = [];
    clusters.forEach((c) => row.push(el('span', { class: 'rc-clu-g' }, [el('button', {
      type: 'button',
      class: 'rc-clu' + (c.call === 'ied' ? ' ied' : ' ds')
             + (c.call_by === 'hand' ? ' hand' : '')
             + (c.call_by === 'drawn' ? ' drawn' : '')
             + (c.name ? ' named' : ''),
      title: 'Cluster ' + (c.rank + 1) + ' of ' + clusters.length + ': '
           + (c.n || 0) + ' events, centre ' + hz(c.centre_raw[0]) + ' µV, '
           + hz(c.centre_raw[1]) + ' ms, ' + hz(c.centre_raw[2]) + ' dB. '
           + 'Called ' + c.call.toUpperCase() + ' '
           + (c.call_by === 'hand' ? 'by hand' : c.call_by === 'margin'
              ? 'by the calls this ' + (viewMode === 'pooled' ? 'pool' : 'version')
                + ' carries' : c.call_by === 'drawn'
              ? 'as drawn round by hand' : c.call_by === 'name'
              ? 'by its name, ‘' + c.name + '’' : 'by the rule') + '. '
           + (c.name && ex.onName ? 'Press to rename it.'
              : 'Press to call it ' + (c.call === 'ied' ? 'DS' : 'IED') + '.'),
      onclick: () => (c.name && ex.onName ? ex.onName(c)
                      : onToggle(c.rank, c.call === 'ied' ? 'ds' : 'ied')),
    }, [
      el('i', { class: 'rc-swatch', style: 'background:' + cluFill(c.rank, c.call) }),
      el('span', { text: '#' + (c.rank + 1) + ' '
                         + (c.name ? c.name : c.call.toUpperCase())
                         + ' · ' + (c.n || 0)
                         + (c.call_by === 'hand' ? ' · by hand'
                            : c.call_by === 'margin' ? ' · carried'
                            : c.call_by === 'drawn' ? ' · drawn' : '') }),
    ]),
      /* Its name, from the lab's list or typed; the name's type is its call. */
      ex.onName ? el('button', { type: 'button', class: 'rc-clu-x rc-clu-name',
        text: c.name ? 'rename' : 'name',
        title: 'Give cluster ' + (c.rank + 1) + ' a name from the lab’s list, '
             + 'or a new one -- “DS slow”, “IED big”. The name says whether it '
             + 'is a DS or an IED, travels with the version, the pool and the '
             + 'bank, and becomes a chip to pool by.',
        onclick: () => ex.onName(c) }) : null,
      /* Its average: the four pictures of a dot, over every event in it. */
      ex.onAvg ? el('button', { type: 'button', class: 'rc-clu-x rc-clu-avg',
        text: 'avg', title: 'The average of cluster ' + (c.rank + 1)
          + ' -- its max-amp trace, spectrum, every contact and CSD, over '
          + 'its ' + (c.n || 0) + ' events -- in the event panel.',
        onclick: () => ex.onAvg(c) }) : null,
      (c.call_by === 'drawn' && ex.onRemove) ? el('button', { type: 'button',
        class: 'rc-clu-x rc-clu-rm', text: '×',
        title: 'Undraw this cluster: its events go back to k-means.',
        onclick: () => ex.onRemove(c) }) : null,
    ].filter(Boolean))));
    if (anyHand) {
      row.push(BARRY.ui.button({ kind: 'mini', text: 'Calls back to the rule',
        title: 'Undo every cluster called by hand.', onclick: onReset }));
    }
    // Whatever is asked of the clusters as a whole, after them.
    if (ex.tail) row.push(ex.tail);
    return el('div', { class: 'chip-row rc-clusters' }, row);
  }

  /* THE LAB'S NAMES, and the picker. A name is picked from the list or
     typed new with its type (DS or IED); a new one joins the list for
     everybody. One name means one thing: the server refuses a name that is
     already on the list as the other type. */
  let labNames = null;

  async function loadNames() {
    try {
      labNames = (await api('/api/rootcanal/names')).names || [];
    } catch (e) {
      labNames = labNames || [];
    }
    return labNames;
  }

  async function nameDialog(c, onDone) {
    const names = await loadNames();
    let typ = c.call === 'ied' ? 'ied' : 'ds';
    const input = el('input', { type: 'text', class: 'rc-in rc-name-in',
                                placeholder: 'A new name', value: '' });
    const errP = el('p', { class: 'hint rc-warn rc-name-err', text: '' });
    const typeSeg = BARRY.ui.seg([['ds', 'DS', 'A dentate spike name.'],
                                  ['ied', 'IED', 'An IED name.']],
      typ, (v) => { typ = v; }, { extra: 'rc-name-type' });
    const use = (nm) => { closeModal(); onDone(nm); };
    const byType = (t) => names.filter((n) => n.type === t);
    const list = (t) => byType(t).length ? el('div', { class: 'chip-row' },
      [el('span', { class: 'rc-sel-k', text: t === 'ds' ? 'DS names'
                                                       : 'IED names' })]
        .concat(byType(t).map((n) => BARRY.ui.button({ kind: 'mini',
          text: n.name, extra: 'rc-name-pick', on: c.name === n.name,
          title: 'Added by ' + (n.by || 'someone')
               + (n.at ? ' on ' + String(n.at).slice(0, 10) : '') + '.',
          onclick: () => use({ name: n.name, type: n.type }) })))) : null;
    showModal(el('div', { class: 'rc-name-dlg' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Name cluster #' + (c.rank + 1) }),
        el('div', { class: 'spacer' })]),
      el('div', { class: 'mb' }, [el('div', { class: 'rc-ask' }, [
        el('p', { class: 'hint', text: 'Its ' + (c.n || 0) + ' events, centre '
          + hz(c.centre_raw[0]) + ' µV, ' + hz(c.centre_raw[1]) + ' ms, '
          + hz(c.centre_raw[2]) + ' dB. A name says what the cluster is: '
          + 'its type is its call.' }),
        names.length ? null : el('p', { class: 'hint',
          text: 'The lab’s list is empty: the first name typed starts it.' }),
        list('ds'), list('ied'),
        el('div', { class: 'rc-name-new' }, [input, typeSeg,
          BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Add and use',
            extra: 'rc-name-add',
            onclick: async () => {
              const nm = String(input.value || '').trim();
              if (!nm) { errP.textContent = 'Type a name first.'; return; }
              try {
                await apiPost('/api/rootcanal/names', { name: nm, type: typ });
              } catch (e) { errP.textContent = e.message; return; }
              labNames = null;
              use({ name: nm, type: typ });
            } })]),
        errP,
      ].filter(Boolean))]),
      BARRY.ui.modalFoot([
        c.name ? BARRY.ui.button({ kind: 'ghost', text: 'Remove the name',
          extra: 'rc-name-clear', onclick: () => use(null) }) : null,
      ].filter(Boolean), [
        BARRY.ui.button({ kind: 'ghost', text: 'Cancel',
                          onclick: closeModal }),
      ]),
    ]), { replace: true });
  }

  function curAvg() { return viewMode === 'pooled' ? pool.avg : avg; }

  /* THE AVERAGE OF A SET OF DOTS, in the event panel: the max-amp trace
     (each event's own contact, aligned on the stamp, with its spread), the
     spectrum against baseline, every contact and the CSD. A cluster's, or
     the dots drawn round with the lasso. */
  async function showAverage(label, evs) {
    const pooled = viewMode === 'pooled';
    const st = { label, n: evs.length, data: null, err: null, busy: true };
    if (pooled) pool.avg = st; else avg = st;
    const gen = ++avgGen;
    render();
    let url, body;
    if (pooled) {
      const mem = (pool.fit && pool.fit.members) || [];
      url = '/api/rootcanal/pool/group';
      body = Object.assign(poolBody(), { label, events: evs.map(
        (e) => [(mem[e.m] || {}).key, e.src_i != null ? e.src_i : e.i]) });
    } else {
      url = '/api/rootcanal/group';
      body = Object.assign(fitBody(), { label, events: evs.map((e) => e.i) });
    }
    try {
      st.data = await apiPost(url, body);
    } catch (e) {
      st.err = e.message;
    }
    if (gen !== avgGen) return;
    st.busy = false;
    render();
  }

  function closeAverage() {
    if (viewMode === 'pooled') pool.avg = null; else avg = null;
    avgGen++;
    render();
  }

  function avgPane(A) {
    const d = A.data && A.data.ok !== false ? A.data : null;
    const cell = (id, title, sub) => el('div', { class: 'rc-ev-cell' }, [
      el('div', { class: 'rc-ev-t' }, [
        el('strong', { text: title }),
        sub ? el('span', { class: 'hint', text: sub }) : null,
      ].filter(Boolean)),
      el('canvas', { class: 'rc-canvas rc-ev', id }),
    ]);
    const tr = d ? d.trace || {} : {};
    const about = d
      ? ('n = ' + d.n + (d.n_reads > 1 ? ' from ' + d.n_reads + ' recordings' : '')
         + (tr.flipped ? ' · ' + tr.flipped + ' flipped to the common polarity' : '')
         + (d.n_away ? ' · ' + d.n_away + ' left out: their read is not on this machine' : ''))
      : (A.err ? 'Not averaged: ' + A.err : 'Averaging ' + A.n + ' events…');
    return el('div', { class: 'rc-pane rc-event rc-avg' }, [
      el('div', { class: 'rc-avg-head' }, [
        el('strong', { text: 'Average of ' + A.label }),
        el('span', { class: 'hint' + (A.err ? ' rc-warn' : ''), text: about }),
        el('span', { class: 'spacer' }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Back to the picked dot',
          extra: 'rc-avg-close', onclick: closeAverage }),
      ]),
      el('div', { class: 'rc-ev-grid' }, [
        cell('rcTrace', 'Max-amp contact', 'each event’s own, aligned on the '
             + 'stamp · mean ± SD'),
        cell('rcSpec', 'Spectrum', 'each event’s HF contact, against its '
             + 'baseline · mean'),
        cell('rcStack', 'Every contact', d && d.n_reads > 1
          ? 'mean · ' + (d.probe_from || 'one recording') + ' (' + d.probe_from_n
            + ' events): a probe means something inside one recording'
          : 'mean'),
        cell('rcCsd', 'CSD', ((d && d.csd && d.csd.filter)
                              || '5–100 Hz, 60 Hz mains taken out')
                             + ' · of the mean'),
      ]),
    ]);
  }

  /* What a cluster is DRAWN in: its call's colour, on its chip, its
     centre and its dots alike. Colouring by cluster, or by which detector
     found an event, was taken out on 2026-10-21. */
  function cluFill(rank, call) {
    return colOf(call);
  }

  /* Once at a time, and only the controls bar repainted when it lands:
     it changes one name in the k slot, not the page. */
  async function loadMargins() {
    if (marginsLoading) return;
    marginsLoading = true;
    try {
      const got = await api('/api/rootcanal/margins');
      margins = got.margins || [];
    } catch (e) {
      margins = margins || [];
    }
    marginsLoading = false;
    swapTop();
  }

  /* The name of the calls a version or a pool carries: the fit's own answer
     says it; failing that the saved list, asked again for an id it has not
     seen -- a propagate or a pool's singles make new ones. '' while it is
     not known, never the bare id. */
  function marginNick(ref) {
    const r = ref || q.margin;
    if (!r) return null;
    const f = viewMode === 'pooled' ? pool.fit : fit;
    const mu = f && f.margin_used;
    if (mu && mu.artifact_id === r.artifact_id && mu.nickname) return mu.nickname;
    const m = (margins || []).find((x) => x.artifact_id === r.artifact_id);
    if (m) return m.nickname || m.name || '';
    if (!marginsAsked.has(r.artifact_id)) {
      marginsAsked.add(r.artifact_id);
      loadMargins();
    }
    return '';
  }

  /* ==================================================================
     A DS / IED BORDER IN THREE NUMBERS, WITH GRACE (2026-10-06)
     ================================================================== */
  /* Drawn in Pooled (either level) against each event's own identity;
     applied anywhere measured the same way, where it classifies every event
     by its three numbers alone: solid DS, solid IED or ambiguous. The
     k-means clusters stay underneath, for what is counted against them. */
  const graceWords = (g) => (Number(g) === 0 ? 'none'
                             : +(100 * Number(g)).toFixed(2) + '%');
  const BAX = [['amp_uV', 'amplitude', 'µV'], ['hf_db', 'HF', 'dB'],
               ['hw_ms', 'half-width', 'ms']];
  const bnum = (v) => (v == null ? '?' : Math.abs(v) >= 100
                       ? Number(v).toFixed(0) : Number(v).toFixed(1));

  async function loadBorders() {
    if (bordersLoading) return;
    bordersLoading = true;
    try {
      borders = (await api('/api/rootcanal/borders')).borders || [];
      bordersErr = null;
    } catch (e) {
      borders = [];
      bordersErr = e.message;
    }
    bordersLoading = false;
    render();
  }

  /* TWO KINDS OF BORDER (2026-10-19). "between" is the one above: cut-offs
     drawn between DS and IED. "envelope" is drawn AROUND one identity when
     the other has too few events to draw a line between -- a pool of
     controls is every event DS, and drawing one from a pool of 1263 DS and
     0 IED was refused ("at least 5 of each are needed"). It is a box in µV,
     dB and ms: inside it is solid <that identity>, outside it on any axis
     is ambiguous, and grace is how many of the group's OWN events it may
     leave out -- none wraps every one, 1% and 5% pull every side in,
     ignoring more and more outliers (backend/rcborder.py `envelope`). A
     border with no `kind` is an older one, and is "between". */
  const isEnv = (b) => !!b && b.kind === 'envelope';
  const bGroup = (b) => ((b && b.group) === 'ied' ? 'IED' : 'DS');
  const bOther = (b) => ((b && b.group) === 'ied' ? 'DS' : 'IED');
  const bspan = (r) => bnum((r || {}).lo) + '–' + bnum((r || {}).hi);
  const sameG = (a, b) => a != null && b != null
                          && Math.abs(Number(a) - Number(b)) < 1e-9;

  /* One side of a band: "amplitude ≥ 1482 µV · HF ≥ 13.2 dB · ...". An
     envelope has no sides: its edges are a range on every axis --
     "amplitude 220–1613 µV · HF 3.1–14.2 dB · ..." -- and `side` is not
     read. */
  function edgeWords(b, edges, side) {
    if (isEnv(b)) {
      return BAX.map(([k, word, unit]) => word + ' ' + bspan((edges || {})[k])
                                          + ' ' + unit).join(' · ');
    }
    const ab = b.ied_above || {};
    return BAX.map(([k, word, unit]) => {
      const up = ab[k] !== false;
      const op = side === 'ied' ? (up ? '≥' : '≤') : (up ? '<' : '>');
      return word + ' ' + op + ' ' + bnum(((edges || {})[k] || {})[side + '_at'])
             + ' ' + unit;
    }).join(' · ');
  }

  /* A saved border's numbers in a line: "Envelope · DS · 220–1613 µV ·
     3.1–14.2 dB · 12.0–40.3 ms", or "Between DS and IED · 1193 µV · ...".
     Its nickname, measurement and source are said beside it, in the
     Borders card, rather than run into one long line as the old picker's
     options were. */
  function borderWords(r) {
    const st = r.strict || {};
    if (isEnv(r)) {
      return 'Envelope · ' + bGroup(r) + ' · '
        + BAX.map(([k, , unit]) => bspan(st[k]) + ' ' + unit).join(' · ');
    }
    return 'Between DS and IED · '
      + BAX.map(([k, , unit]) => bnum(st[k]) + ' ' + unit).join(' · ');
  }

  /* What one grace does to one border, in a phrase. */
  function graceMeans(b, g) {
    if (isEnv(b)) {
      return Number(g) === 0 ? 'wraps every ' + bGroup(b) + ' event'
        : 'leaves out the outermost ' + graceWords(g) + ' of the '
          + bGroup(b) + ' events';
    }
    return Number(g) === 0
      ? 'the widest band: no event lands in the other identity’s solid class'
      : 'a narrower band: at most ' + graceWords(g) + ' of the events land '
        + 'in the other identity’s solid class';
  }

  /* What a border made of the events: "1203 inside · 60 outside" round one
     identity; solid DS, solid IED and ambiguous between two. */
  function borderCounts(b, c) {
    const n = c || {};
    if (isEnv(b)) {
      return (n[b.group === 'ied' ? 'ied' : 'ds'] || 0) + ' inside · '
             + (n.amb || 0) + ' outside';
    }
    return (n.ds || 0) + ' solid DS · ' + (n.ied || 0) + ' solid IED · '
           + (n.amb || 0) + ' ambiguous';
  }

  /* The same, for the card's folded line: what inside means, said. */
  function borderShort(b, c) {
    const n = c || {};
    return isEnv(b) ? (n[b.group === 'ied' ? 'ied' : 'ds'] || 0) + ' solid '
                      + bGroup(b) + ' · ' + (n.amb || 0) + ' outside'
                    : borderCounts(b, n);
  }

  /* How this view was measured, in the server's words for it
     (`Params.filter_label` in rootcanal.py) -- which is what a saved
     border's listing carries, so one measured on another filter can be
     said to be refused before Apply is pressed. Pooled has the server's
     own; Single's is built from the params its fit was made with, the same
     way. Only the filter is in the listing: a border on the same filter
     can still differ in its band or window, and the server, which checks
     all of them, has the last word. */
  function measureHere(where) {
    if (where === 'pool') {
      const m = pool.fit && pool.fit.params && pool.fit.params.measure;
      return (m && m.filter_label) || null;
    }
    const p = (fit && fit.params) || null;
    if (!p || !p.filt) return null;
    if (p.filt === 'none') return 'no filter (60 Hz mains left in)';
    const lo = Number(p.lo_hz), hi = Number(p.hi_hz);
    if (!isFinite(lo) || !isFinite(hi)) return null;
    const name = { ds: 'DS filter', lfp: 'LFP filter' }[p.filt] || 'custom filter';
    return name + ', ' + (lo > 0 ? lo + '–' + hi + ' Hz' : 'low-pass ' + hi + ' Hz')
      + ', ' + (asParam('mains_out', p.mains_out) ? '60 Hz mains out'
                                                  : '60 Hz mains left in');
  }

  /* The applied border's rule, and how it sits with this view's own
     identities: round one identity, how many of the OTHER are inside the
     box; between two, how many land in the other's solid class. */
  function borderRule(bu) {
    let tail = '';
    if (bu.switch_rate != null) {
      tail = !isEnv(bu)
        ? ' Here ' + bu.wrong + ' of ' + bu.n_identity + ' events with an '
          + 'identity (' + pct(bu.switch_rate) + ') land in the other’s solid '
          + 'class.'
        : bu.wrong ? ' Here ' + bu.wrong + ' of ' + bu.n_identity + ' events '
          + 'with an identity (' + pct(bu.switch_rate) + ') are '
          + bOther(bu) + ' events inside the box.'
        : ' No ' + bOther(bu) + ' event here is inside the box.';
    }
    return (bu.rule || '') + tail;
  }

  /* One saved border in the card's list: a row picked by pressing it
     anywhere, in the house's pick-list shape (Braces' and Doppler's Many).
     Its nickname and kind, its numbers, its rule in words, the measurement
     it was made under -- and whether that is this view's -- and where it
     was drawn. */
  function borderItem(r, ctx) {
    const ns = (r.current && r.current.n_summary) || {};
    const v = r.version != null ? r.version : (r.current || {}).v;
    const fits = r.measure && ctx.here ? r.measure === ctx.here : null;
    const what = ctx.where === 'pool' ? 'pool' : 'set';
    const lvl = r.level === 'double' ? 'a pool of pools' : 'a pool';
    const size = [
      r.events != null ? r.events + ' events' : null,
      ns.recordings != null ? ns.recordings + ' recording'
        + (ns.recordings === 1 ? '' : 's') : null,
      ns.mice != null ? ns.mice + (ns.mice === 1 ? ' mouse' : ' mice') : null,
    ].filter(Boolean).join(', ');
    const st = r.strict || {};
    const rule = isEnv(r)
      ? 'Solid ' + bGroup(r) + ' inside the box, ambiguous outside it on any '
        + 'axis. At no grace the box is ' + edgeWords(r, st) + '.'
      : 'Solid IED past all three cut-offs, solid DS short of all three, '
        + 'anything else ambiguous. The cut-offs: ' + BAX.map(([k, word, unit]) =>
          word + ' ' + bnum(st[k]) + ' ' + unit).join(' · ') + '.';
    const on = r.artifact_id === ctx.pickId();
    return el('label', { class: 'inc-pick rc-border-item' + (on ? ' on' : ''),
                         'data-id': r.artifact_id }, [
      el('input', { type: 'radio', name: 'rc-border-pick-' + ctx.where,
                    value: r.artifact_id, checked: on ? 'checked' : null,
                    onchange: () => ctx.onPick(r.artifact_id) }),
      el('div', { class: 'ip-main' }, [
        el('span', { class: 'ip-name rc-border-name' }, [
          el('strong', { text: r.nickname || r.name || r.artifact_id }),
          v != null ? el('span', { class: 'hint', text: 'v' + v }) : null,
          BARRY.ui.chip(isEnv(r) ? 'drawn around the ' + bGroup(r) + ' events'
                                 : 'drawn between DS and IED',
                        { extra: 'rc-border-kind' }),
          ctx.appliedId === r.artifact_id
            ? BARRY.ui.chip('applied here', { kind: 'ok', extra: 'rc-border-here' })
            : null,
          ctx.onArchive ? BARRY.ui.button({ kind: 'mini', text: 'Archive',
            extra: 'rc-border-archive',
            title: 'Put it away: it leaves this list, on every machine once '
                 + 'it syncs, and stays saved. It is listed under Archived '
                 + 'borders and can be put back.',
            onclick: (e) => { e.preventDefault(); e.stopPropagation();
                              ctx.onArchive(r.artifact_id); } }) : null,
        ]),
        el('span', { class: 'ip-sub rc-border-nums', text: borderWords(r) }),
        el('span', { class: 'ip-sub rc-border-what', text: rule }),
        el('span', { class: 'ip-sub rc-border-meas'
                            + (fits === false ? ' rc-border-no' : ''),
          text: !r.measure ? 'How it was measured was not recorded.'
            : 'Measured on ' + r.measure + (fits === true
              ? ': the same filter as this ' + what + '.'
              : fits === false ? '. This ' + what + ' is measured on '
                + ctx.here + '. It can still be applied: its cut-offs are '
                + 'numbers of the measurement it was drawn under, so here they '
                + 'ask a slightly different question.' : '.') }),
        el('span', { class: 'ip-sub rc-border-from', text: (r.source
          ? 'Drawn from ‘' + r.source + '’, ' + lvl
          : 'Drawn from ' + lvl + ' that was not saved')
          + (size ? ': ' + size : '') + '.' }),
      ]),
    ]);
  }

  /* THE BORDERS CARD (2026-10-19), in Pooled's picture and in Single.
     Applying a saved border was a small row inside the margins card -- a
     select, a grace select and "Apply" -- and how it was done was not
     clear (asked for: "make it more clear how we apply the existing
     borders"). It is a card of its own now, saying, top to bottom:
       - what is applied -- "Classified by ‘x’ at grace 5%: 1203 inside ·
         60 outside", its rule, and how it is drawn on the flat views -- or
         that no border is;
       - the saved borders, a list to pick from, each with its rule, its
         kind, the measurement it was made under (and whether that is this
         view's: the server refuses another) and where it was drawn;
       - the picked one's graces, each with what it means for that border;
       - Clear, in Pooled "Draw a new border from this pool…", and the
         primary last, naming what it does: "Apply to this pool" / "set".
     A pick ticks in place: the rows, the grace and the buttons change
     where they stand, and nothing is rebuilt until Apply. The pick is kept
     per view in `borderPick`, so a repaint -- the list arriving, a poll --
     does not throw it away. The class names the suites read are kept on
     the parts doing the same jobs (rc-border-row, -pick, -grace, -apply,
     -clear, -on, -rule, -err). */
  /* ARCHIVED BORDERS (2026-10-19): "allow us to archive borders". An
     archived border leaves the list -- everyone's, once it syncs -- and
     stays saved: it is listed under "Archived borders" and can be put back,
     and one that is applied stays applied, saying so. Kept in a shared
     preference merged per border (backend/store.py PREFS_SPEC). */
  const ARCH_KEY = 'rootcanal_border_archive';

  function archivedBorders() {
    try {
      return (BARRY.prefs && BARRY.prefs.get(ARCH_KEY, {})) || {};
    } catch (e) {
      return {};
    }
  }

  function setArchived(id, on) {
    const m = Object.assign({}, archivedBorders());
    if (on) m[id] = { at: new Date().toISOString() };
    else delete m[id];
    BARRY.prefs.set(ARCH_KEY, m);
    const r = (borders || []).find((x) => x.artifact_id === id) || {};
    toast((on ? 'Archived ‘' : 'Put back ‘') + (r.nickname || r.name || id)
          + (on ? '’. It is listed under Archived borders, and can be put '
                  + 'back from there.' : '’.'), 'ok', 6000);
    BARRY.activity.log('rootcanal.border_archive', { artifact: id,
                                                     archived: !!on });
    render();
  }

  function bordersCard(b) {
    if (borders === null) loadBorders();
    const arch = archivedBorders();
    const shelved = (borders || []).filter((r) => arch[r.artifact_id]);
    const list = (borders || []).filter((r) => !arch[r.artifact_id]);
    const st = borderPick[b.where] || (borderPick[b.where] = {});
    const bu = b.used || null;
    const rowOf = (id) => list.find((x) => x.artifact_id === id) || null;
    const aid = b.applied ? b.applied.artifact_id : null;
    /* A border applied from elsewhere -- saved and applied at once, or
       opened with a saved pool -- becomes the pick. */
    if (st.seen !== aid) {
      st.seen = aid;
      if (aid) {
        st.id = aid;
        st.grace = b.applied.grace != null ? b.applied.grace
                                           : bu ? bu.grace : null;
      }
    }
    if (borders !== null && !rowOf(st.id)) {
      st.id = list[0] ? list[0].artifact_id : null;
      st.grace = null;
    }
    const here = measureHere(b.where);
    const what = b.where === 'pool' ? 'pool' : 'set';
    const isOn = () => !!(bu && bu.artifact_id === st.id
                          && sameG(bu.grace, st.grace));
    const fixGrace = () => {
      const r = rowOf(st.id);
      const lv = (r && r.levels) || [];
      if (!r || lv.some((x) => sameG(x.grace, st.grace))) return;
      st.grace = bu && bu.artifact_id === st.id && bu.grace != null ? bu.grace
        : r.grace_default != null ? r.grace_default
        : lv[0] ? lv[0].grace : null;
    };
    const gHold = el('div', { class: 'rc-border-grace', role: 'radiogroup',
                              'aria-label': 'grace' });
    const aHold = el('div', { class: 'rc-border-acts' });
    let gFor;
    const fillGrace = () => {
      gFor = st.id;
      const r = rowOf(st.id);
      if (!r) { gHold.replaceChildren(); return; }
      const lv = r.levels || [];
      gHold.replaceChildren(
        el('div', { class: 'rc-group-l', text: 'Grace for ‘'
                    + (r.nickname || r.name || r.artifact_id) + '’' }),
        ...(lv.length ? lv.map((x) => {
          const on = sameG(x.grace, st.grace);
          return el('label', { class: 'rc-border-gopt' + (on ? ' on' : ''),
                               'data-grace': String(x.grace) }, [
            el('input', { type: 'radio', name: 'rc-border-g-' + b.where,
                          checked: on ? 'checked' : null,
                          onchange: () => { st.grace = x.grace; sync(); } }),
            el('span', { class: 'rc-border-gw', text: graceWords(x.grace) }),
            el('span', { class: 'hint', text: graceMeans(r, x.grace)
              + (x.counts ? '. Where it was drawn: '
                            + borderCounts(r, x.counts) + '.' : '.') }),
          ]);
        }) : [el('p', { class: 'hint', text: 'This border was saved with no '
                                             + 'grace to apply it at.' })]));
    };
    const fillActs = () => {
      const r = rowOf(st.id);
      const on = isOn();
      aHold.replaceChildren(BARRY.ui.actions([
        b.applied ? BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Clear',
          extra: 'rc-border-clear',
          title: 'Take the border off: every event is called by its cluster '
               + 'again.',
          onclick: () => b.onApply(null) }) : null,
        b.onDraw ? BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: 'Draw a new border from this pool…', extra: 'rc-border-draw',
          title: 'Between the events’ own identities, or around them when the '
               + 'pool is all one identity. Previewed at every grace before '
               + 'it is saved.',
          onclick: () => b.onDraw() }) : null,
        /* The primary in Pooled, where the card is a surface of its own;
           in Single it sits inside the card whose one primary is Bank, so
           there it is the last of its row but not filled. */
        BARRY.ui.button({ kind: b.where === 'pool' ? 'primary' : 'ghost',
          size: 'sm', text: (on ? 'Applied to this ' : 'Apply to this ') + what,
          extra: 'rc-border-apply', disabled: !r || st.grace == null || on,
          title: r ? 'Classify every event of this ' + what + ' by ‘'
                     + (r.nickname || r.name || r.artifact_id) + '’ at grace '
                     + graceWords(st.grace) + ', by its three numbers alone.'
                   : 'Pick a saved border first.',
          onclick: () => {
            if (r && r.measure && here && r.measure !== here) {
              toast('‘' + (r.nickname || r.name || r.artifact_id) + '’ was '
                    + 'drawn on ' + r.measure + ', and this ' + what + ' is '
                    + 'measured on ' + here + '. Applying it all the same.',
                    'warn', 9000);
            }
            b.onApply({ artifact_id: st.id, version: null, grace: st.grace });
          } }),
      ], { extra: 'rc-border-actions' }));
    };
    const items = list.map((r) => borderItem(r, {
      where: b.where, here, appliedId: bu ? bu.artifact_id : null,
      pickId: () => st.id,
      onPick: (id) => { st.id = id; st.grace = null; sync(); },
      onArchive: (id) => setArchived(id, true) }));
    const sync = () => {
      for (const it of items) {
        const on = it.getAttribute('data-id') === st.id;
        it.classList.toggle('on', on);
        const inp = it.querySelector('input');
        if (inp) inp.checked = on;
      }
      fixGrace();
      if (gFor !== st.id) {
        fillGrace();
      } else {
        for (const o of gHold.querySelectorAll('.rc-border-gopt')) {
          const on = sameG(Number(o.getAttribute('data-grace')), st.grace);
          o.classList.toggle('on', on);
          const inp = o.querySelector('input');
          if (inp) inp.checked = on;
        }
      }
      fillActs();
    };
    fixGrace();
    fillGrace();
    fillActs();
    const c = (bu && bu.counts) || {};
    const state = bu
      ? el('div', { class: 'rc-border-state' }, [
          el('p', { class: 'rc-border-now' }, [
            el('strong', { text: 'Classified by ‘' + bu.nickname + '’'
              + (bu.version != null ? ' v' + bu.version : '') + ' at grace '
              + bu.grace_words + ':' }),
            BARRY.ui.chip(borderCounts(bu, c), { extra: 'rc-border-on',
              title: isEnv(bu)
                ? 'Inside the box is solid ' + bGroup(bu) + '; outside it on '
                  + 'any axis is ambiguous, drawn in its own call’s colour, '
                  + 'faded, with a dotted edge. An event missing one of the '
                  + 'three numbers counts as outside.'
                : 'Every event by its three numbers alone: solid DS, solid IED '
                  + 'or ambiguous -- an ambiguous one in its own call’s '
                  + 'colour, faded, with a dotted edge.' }),
            c.none ? BARRY.ui.chip(c.none + ' with no numbers', {
              title: 'Not measured on any axis, so no border can place them.' })
                   : null,
            (bu.mismatch || []).length ? BARRY.ui.chip('measured another way', {
              kind: 'warn', extra: 'rc-border-is-mismatch',
              title: bu.mismatch.join('; ') }) : null,
            arch[bu.artifact_id] ? BARRY.ui.chip('archived', {
              extra: 'rc-border-is-archived',
              title: 'Archived, and still applied here. Put it back from '
                   + 'Archived borders below, or Clear it.' }) : null,
          ]),
          (bu.mismatch || []).length ? el('p', { class: 'hint rc-warn rc-border-mismatch',
            text: 'Measured another way: ' + bu.mismatch.join('; ') + '. It is '
              + 'applied all the same, as asked -- read its cut-offs as numbers '
              + 'of the measurement it was drawn under.' }) : null,
          el('p', { class: 'hint rc-border-rule', text: borderRule(bu) }),
          bu.edges ? el('p', { class: 'hint rc-border-drawn', text: isEnv(bu)
            ? 'On the flat views it is the box, outlined, with everything '
              + 'outside it shaded.'
            : 'On the flat views it is two dashed lines on each axis, with '
              + 'the ambiguous band between them shaded: where solid DS ends '
              + '(in the DS colour) and where solid IED begins (in the IED '
              + 'colour).' }) : null,
        ])
      : el('p', { class: 'rc-border-now rc-border-none',
                  text: 'No border applied: every event is called by its '
                        + 'cluster.' });
    /* OPEN IN POOLED, under the pictures. FOLDED IN SINGLE unless a border
       was just refused: there the card sits above the pictures, in a card
       455 px wide, and open it put the picked event's own controls below
       the fold -- its folded line says what is applied. Opened or folded
       by hand, it stays that way across repaints and applies. */
    const dflt = b.where === 'pool' || !!b.err;
    const open = st.open != null ? st.open : dflt;
    return el('details', { class: 'card rc-borders', open: open ? 'open' : null,
      ontoggle: (e) => { st.open = e.target.open === dflt ? null
                                                          : e.target.open; } }, [
      el('summary', { class: 'rc-border-sum',
        title: 'A border classifies every event by its three numbers alone '
             + '-- amplitude, HF power and half-width -- in place of its '
             + 'cluster’s call. A saved one can be applied to any ' + what
             + ' measured the same way.',
        text: 'Borders · ' + (bu ? 'Classified by ‘' + bu.nickname
          + '’ at grace ' + bu.grace_words + ': ' + borderShort(bu, c)
          : b.err ? 'not applied, said below'
          // The archived ones are said inside, under their own fold.
          : 'No border applied' + (list.length ? ' · ' + list.length
                                                 + ' saved' : '')) }),
      state,
      b.err ? el('p', { class: 'hint rc-warn rc-border-err',
                        text: 'Not applied: ' + b.err }) : null,
      bordersErr ? el('p', { class: 'hint rc-warn',
                             text: 'Saved borders could not be listed: '
                                 + bordersErr }) : null,
      el('div', { class: 'rc-border-row' }, [
        el('div', { class: 'rc-group-l', text: list.length
          ? 'Saved borders: pick one' : 'Saved borders' }),
        borders === null && !bordersErr
          ? el('p', { class: 'hint', text: 'Listing the saved borders…' })
          : list.length
            ? el('div', { class: 'inc-pick-list rc-border-pick',
                          role: 'radiogroup', 'aria-label': 'saved borders' },
                 items)
            : el('p', { class: 'hint rc-border-empty', text: b.where === 'pool'
                ? 'No border has been saved yet. Draw one from this pool: it '
                  + 'is saved under a nickname, and can then be applied here '
                  + 'or to anything measured the same way.'
                : 'No border has been saved yet.' }),
        gHold,
        aHold,
        shelved.length ? el('details', { class: 'rc-border-archived',
                                         'data-keep': 'rc-border-archived-'
                                                      + b.where }, [
          el('summary', { text: 'Archived borders (' + shelved.length + ')' }),
          el('div', { class: 'rc-border-arch-list' }, shelved.map((r) =>
            el('div', { class: 'rc-border-arch-row',
                        'data-id': r.artifact_id }, [
              el('span', { class: 'rc-border-arch-name',
                           text: borderWords(r) }),
              BARRY.ui.button({ kind: 'mini', text: 'Put back',
                extra: 'rc-border-unarchive',
                title: 'Back in the list of saved borders, on every machine '
                     + 'once it syncs.',
                onclick: () => setArchived(r.artifact_id, false) }),
            ]))),
        ]) : null,
        b.where === 'single' ? el('p', { class: 'hint rc-border-where',
          text: 'New borders are drawn in Pooled, against each event’s own '
              + 'identity, which one recording on its own does not have.' })
          : null,
      ].filter(Boolean)),
    ].filter(Boolean));
  }

  function singleBorderCtx() {
    return {
      where: 'single', applied: q.border, used: fit && fit.border_used,
      err: borderErr,
      onApply: (ref) => { q.border = ref; borderErr = null; refit(); },
    };
  }

  function poolBorderCtx() {
    return {
      where: 'pool', applied: pool.border,
      used: pool.fit && pool.fit.border_used, err: pool.borderErr,
      onApply: (ref) => {
        pool.border = ref;
        pool.borderErr = null;
        if (ref) pool.colour = 'border';
        else if (pool.colour === 'border') pool.colour = 'pool';
        if (pool.sel.length) runPool(); else render();
      },
      onDraw: borderDialog,
    };
  }

  /* Each grace's band: its counts, its switch rate, and its edges. An
     envelope's (2026-10-19) is its box instead: how many of the group are
     inside it (solid), how many of the group it leaves outside, how many
     of the OTHER identity are inside it, and the box's range on each axis
     with what that grace does. */
  function borderTable(b, pick, onPick) {
    const env = isEnv(b);
    const gk = b.group === 'ied' ? 'ied' : 'ds';
    const known = (v) => (v == null ? '?' : String(v));
    const rows = [];
    for (const lv of b.levels || []) {
      const on = Math.abs(lv.grace - pick) < 1e-9;
      const c = lv.counts || {};
      const cells = env
        ? [known(c[gk]),
           known(lv.outside) + ' (' + pct(lv.outside_rate) + ')',
           known(lv.wrong)]
        : [String(c.ds), String(c.ied), String(c.amb),
           pct(lv.switch_rate) + ' (' + lv.wrong + ')'
           + (lv.reached ? '' : ', not reached')];
      rows.push(el('tr', { class: 'rc-border-lv' + (on ? ' on' : ''),
                           'data-grace': String(lv.grace) }, [
        el('td', {}, [el('label', { class: 'rc-border-pickg' }, [
          el('input', { type: 'radio', name: 'rc-border-grace',
                        checked: on ? 'checked' : null,
                        onchange: () => onPick(lv.grace) }),
          el('span', { text: graceWords(lv.grace) })])]),
      ].concat(cells.map((t) => el('td', { text: t })))));
      rows.push(el('tr', { class: 'rc-border-edges' }, [el('td', {
        colspan: String(cells.length + 1), class: 'hint',
        text: env
          ? 'the box: ' + edgeWords(b, lv.edges) + '; it '
            + graceMeans(b, lv.grace)
          : 'solid IED: ' + edgeWords(b, lv.edges, 'ied') + '; solid DS: '
            + edgeWords(b, lv.edges, 'ds')
            + (lv.s_sd ? ' (band ±' + lv.s_sd + ' SD)' : ' (no band)') })]));
    }
    const heads = env
      ? ['grace', 'solid ' + bGroup(b) + ' (inside)', bGroup(b) + ' left outside',
         bOther(b) + ' inside']
      : ['grace', 'solid DS', 'solid IED', 'ambiguous', 'switches'];
    return el('table', { class: 'tbl rc-border-tab' + (env ? ' rc-border-env' : '') }, [
      el('thead', {}, [el('tr', {}, heads.map((t) => el('th', { text: t })))]),
      el('tbody', {}, rows)]);
  }

  /* Draw one from this pool, preview it at every grace, and save it. */
  async function borderDialog() {
    const lvl = pool.level === 'double' ? 'double' : 'pool';
    const src = pool.saved && pool.open
      ? { artifact_id: pool.open.artifact_id,
          version: (pool.open.source || {}).version || pool.open.version }
      : null;
    const base = () => Object.assign({}, pool.lastBody || poolBody(),
                                     { level: lvl, source: src, border: null });
    let prev;
    try {
      prev = await apiPost('/api/rootcanal/border/preview', base());
    } catch (e) {
      toast('No border could be drawn: ' + e.message, 'err', 12000);
      return null;
    }
    let pick = 0.05;
    let custom = null;
    let applyNow = true;
    const holder = el('div', { class: 'rc-border-prev' });
    const draw = () => holder.replaceChildren(borderTable(prev, pick,
      (g) => { pick = g; draw(); }));
    draw();
    const cin = el('input', { type: 'number', class: 'rc-in rc-border-custom',
      min: '0', max: '50', step: '0.5', 'aria-label': 'another grace, in %' });
    const cgo = BARRY.ui.button({ kind: 'mini', text: 'Add this grace',
      extra: 'rc-border-custom-go', onclick: async () => {
        const v = Number(cin.value);
        if (cin.value === '' || !isFinite(v) || v < 0 || v > 50) {
          toast(isEnv(prev) ? 'A grace is the share of the ' + bGroup(prev)
                              + ' events the box may leave out, between 0% '
                              + 'and 50%.'
                            : 'A grace is a switch rate between 0% and 50%.',
                'warn', 6000);
          return;
        }
        try {
          prev = await apiPost('/api/rootcanal/border/preview',
                               Object.assign(base(), { custom: v / 100 }));
        } catch (e) {
          toast(e.message, 'err', 9000);
          return;
        }
        custom = v / 100;
        pick = custom;
        draw();
      } });
    /* ROUND ONE IDENTITY (2026-10-19): a pool whose events are all DS --
       or with too few IED to draw a line between -- is answered with an
       envelope, and the dialog says what that is instead of the cut-offs
       it does not have. */
    const env = isEnv(prev);
    const nf = prev.fit || {};
    const filtWords = (prev.measure || {}).filter_label || 'this measurement';
    const what = el('div', { class: 'rc-ask rc-border-dlg' + (env ? ' rc-border-env' : '') }, (env ? [
      el('p', { text: (nf.n_other
          ? 'Only ' + nf.n_other + ' event' + (nf.n_other === 1 ? ' here is '
                                                                : 's here are ')
            + bOther(prev) + ' (' + nf.n_group + ' are ' + bGroup(prev)
            + '), too few to draw a line between them'
          : 'Every event here is ' + bGroup(prev) + ' (' + nf.n_group + ' '
            + bGroup(prev) + ', 0 ' + bOther(prev) + '), so there is nothing '
            + 'to draw a line between')
        + '. Instead the border is a box around the ' + bGroup(prev)
        + ' events, in µV, dB and ms: inside it is solid ' + bGroup(prev)
        + ', and outside it on any axis is ambiguous.' }),
      el('p', { class: 'rc-border-strict', text: 'The box at no grace: '
        + edgeWords(prev, prev.strict) + '.' }),
      el('p', { class: 'hint', text: 'Grace pulls the box in: none wraps '
        + 'every ' + bGroup(prev) + ' event, and 1% and 5% leave out the '
        + 'outermost 1% and 5% of them, ignoring more and more outliers. Pick '
        + 'the grace it applies at; every one listed is saved with it. It is '
        + 'the same border only where things are measured the same way ('
        + filtWords + ').' }),
    ] : [
      el('p', { text: 'Three cut-offs, one each in µV, dB and ms, drawn '
        + 'between the events’ own identities: ' + (lvl === 'double'
          ? 'what each event’s own pool called it (v0)'
          : 'what each event’s single called it')
        + '. Past all three is solid IED, short of all three solid DS, and '
        + 'anything else ambiguous. It is the same border only where things '
        + 'are measured the same way (' + filtWords + ').' }),
      el('p', { class: 'rc-border-strict', text: 'The border: '
        + BAX.map(([k, word, unit]) => word + ' ' + bnum(prev.strict[k]) + ' '
                  + unit).join(' · ') + ', on ' + prev.n_identity
        + ' events with an identity.' }),
      el('p', { class: 'hint', text: 'Grace is the identity-switch rate '
        + 'allowed. Each cut-off widens into a band, the same number of '
        + 'standard deviations on every axis, until at most that share of '
        + 'the events land in the other identity’s solid class; the events '
        + 'in a band are ambiguous. Pick the grace it applies at; every one '
        + 'listed is saved with it.' }),
    ]).concat([
      holder,
      el('div', { class: 'chip-row rc-border-custom-row' }, [
        el('span', { class: 'hint', text: 'Another grace, in %:' }), cin, cgo]),
      el('label', { class: 'rc-num rc-border-apply-now' }, [
        el('input', { type: 'checkbox', checked: 'checked',
                      onchange: (e) => { applyNow = e.target.checked; } }),
        el('span', { class: 'rc-num-l', text: 'classify this pool by it once '
                                            + 'saved' })]),
    ]));
    const sugg = (env ? 'border around ' + bGroup(prev) + ' · ' : 'border · ')
      + ((pool.open && pool.open.nickname)
         || (lvl === 'double' ? 'pool of pools' : 'pool'));
    let rep = null;
    return BARRY.ui.bankDialog({
      kind: 'entry', name: sugg, what,
      title: env ? 'Save a border around the ' + bGroup(prev) + ' events'
                 : 'Save a DS / IED border',
      okText: 'Save the border',
      onBank: async ({ name, note }) => {
        const nick = String(name || '').trim();
        if (!nick) throw new Error('A border needs a nickname.');
        rep = await apiPost('/api/rootcanal/border/save', Object.assign(base(),
          { nickname: nick, note: note || '', grace: pick, custom }));
      },
    }).then((ok) => {
      if (!ok || !rep) return null;
      toast(applyNow ? 'Saved the border ‘' + rep.nickname + '’; this pool is '
                       + 'classified by it at grace ' + graceWords(rep.grace)
                       + '.'
                     : 'Saved the border ‘' + rep.nickname + '’. Apply it from '
                       + 'the Borders card.', 'ok', 8000);
      BARRY.activity.log('rootcanal.border_save', { artifact: rep.artifact_id,
                                                    grace: rep.grace });
      borders = null;
      if (applyNow) {
        pool.border = { artifact_id: rep.artifact_id, version: rep.version,
                        grace: rep.grace };
        pool.borderErr = null;
        pool.colour = 'border';
        runPool();
      } else {
        render();
      }
      return rep;
    });
  }

  function chipC(text, cls) {
    return el('span', { class: 'stat-chip rc-cls-chip' }, [
      el('i', { class: 'rc-swatch', style: 'background:' + colOf(cls) }),
      el('span', { text }),
    ]);
  }

  /* The name the next version of this set will get. The lineage names are
     the ones a person reads (`label_rows` on the server), so the tip's name
     plus one where it is a plain number, and "the next version" where it is
     a branch -- a branch's successor is the server's to name. */
  /* What the bank will call the new version: the rule in versions.py, from
     the version being read. It was the tip plus one, which is wrong
     whenever an older version is read -- that bank is a branch. */
  function nextName(c) {
    const vs = (c && c.versions) || [];
    if (!vs.length) return null;
    const from = versionOf(c, q.from_version) || vs[vs.length - 1];
    return BARRY.ui.versionNext(vs, from).name;
  }

  function bankLabel() {
    const c = (fit && fit.counts) || {};
    const cur = setOf();
    const nx = nextName(cur);
    const ied = (cur && cur.rootcanal && cur.rootcanal.ied_entry);
    const nDs = (c.ds || 0) + (c.unmeasured || 0);
    const flags = [
      c.partial ? c.partial + ' on 2 of 3 axes' : null,
      c.wide ? c.wide + ' by the widened search' : null,
    ].filter(Boolean);
    return 'Bank: ' + nDs + ' DS as ' + (nx ? BARRY.ui.versionLabel(nx) : 'a new version')
      + ', ' + (c.ied || 0) + ' IED as '
      + (ied ? 'a new version of its IED set' : 'a new entry')
      + (flags.length ? ' (' + flags.join(', ') + ')' : '');
  }

  /* The picked event's line: which one, what it was called, and the four
     things you do to it. Above the pictures, so none of them is below the
     fold. */
  function pickBar() {
    const e = pickedEvent();
    if (!e) {
      return el('div', { class: 'card rc-pickbar' }, [
        el('span', { class: 'hint', text:
          'Click a dot in any view to look at that event. ← and → step '
          + 'through them.' }),
      ]);
    }
    const n = (fit.events || []).length;
    const at = (fit.events || []).findIndex((x) => x.i === e.i);
    return el('div', { class: 'card rc-pickbar' }, [
      el('strong', { text: 'Event ' + (at + 1) + ' of ' + n }),
      el('span', { class: 'hint', text:
        't = ' + fmt(e.t, 3) + ' s  ·  CSC' + e.contact + ' (max amp, '
        + (e.polarity === 'min' ? 'negative' : 'positive') + ')  ·  '
        + fmt(e.amp_uV, 0) + ' µV  ·  ' + (e.hw_ms == null || !isFinite(e.hw_ms)
                                           ? 'half-width unresolved'
                                           : fmt(e.hw_ms, 1) + ' ms')
        + '  ·  ' + (e.hf_db == null || !isFinite(e.hf_db) ? 'no HF'
                     : fmt(e.hf_db, 1) + ' dB') }),
      /* THE CALL IS SHOWN, NOT SET. An event's identity comes from its
         cluster -- the rule, a name, a margin -- and never from a button
         on the event itself (asked for 2026-10-06). An older result whose
         events were flipped by hand still says so. */
      e.cls == null
        ? BARRY.ui.chip('not measured, so no class', { extra: 'rc-ev-call' })
        : BARRY.ui.chip(e.cls.toUpperCase() + (e.cluster != null
            ? ' · cluster #' + (e.cluster + 1) : ''), {
            kind: e.cls === 'ied' ? 'warn' : null, extra: 'rc-ev-call',
            title: 'Its cluster’s call. An event’s identity follows its '
                 + 'cluster; it is not set one event at a time.' }),
      e.flipped ? BARRY.ui.chip('flipped by hand in an older result',
                                { kind: 'warn' }) : null,
      e.partial ? BARRY.ui.chip('2 of 3 axes', { kind: 'warn' }) : null,
      e.wide ? BARRY.ui.chip(e.retried ? 'found by searching again'
                                       : 'widened search', { kind: 'warn' })
             : null,
      e.retried === false ? BARRY.ui.chip('searched again: none found',
                                          { kind: 'warn' }) : null,
      el('span', { class: 'spacer' }),
      BARRY.ui.actions([
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: '◀ prev',
                          title: 'The previous event. Or ←.',
                          onclick: () => step(-1) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'next ▶',
                          title: 'The next event. Or →.',
                          onclick: () => step(+1) }),
        canRetry(e) ? BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: 'Search again, to ±' + hz(retryMs()) + ' ms',
          extra: 'rc-retry-one',
          title: 'Its half-width was not found within ±' + hz(shownParams()
            .cross_ms) + ' ms. Searches this event again, out to the widest '
            + 'the stored waveform allows; everything else keeps its '
            + 'numbers.',
          onclick: () => retryWider([e.i]) }) : null,
        BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: 'Open in Xplorefinder',
          title: 'The recording itself at this event, in a window of its '
               + 'own that follows as you step.',
          onclick: openInXplore }),
      ], { extra: 'rc-acts' }),
    ].filter(Boolean));
  }

  function spacePane() {
    return el('div', { class: 'rc-pane rc-space-pane' }, [
      el('div', { class: 'rc-pane-head' }, [
        el('strong', { text: 'The space' }),
        /* The same settings chip in both views, and in Pooled what it
           pools beside it. */
        modeChip(),
        viewMode === 'pooled' ? poolChip() : null,
        el('span', { class: 'hint', text:
          'z-scored · drag to turn · Shift-drag to lasso · wheel to zoom · '
          + 'double-click a dot to open it in Xplorefinder · double-click '
          + 'elsewhere to reset' }),
        el('span', { class: 'spacer' }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: 'Open in Xplorefinder', extra: 'rc-space-xplore',
          title: 'The dot you picked, in its recording, at its time, in a '
               + 'window of its own that follows every dot you pick. Or '
               + 'double-click a dot.',
          onclick: openPickedInXplore }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: lassoMode ? 'Lasso: on' : 'Lasso',
          extra: 'rc-lasso-toggle' + (lassoMode ? ' on' : ''),
          title: 'When on, a drag on the 3D view draws round dots instead of '
               + 'turning it. Shift-drag does the same either way.',
          onclick: () => { lassoMode = !lassoMode; render(); } }),
      ]),
      el('canvas', { class: 'rc-canvas rc-space', id: 'rcSpace' }),
    ]);
  }

  const FLATS = [
    ['rcFlatAH', 0, 1],
    ['rcFlatAP', 0, 2],
    ['rcFlatHP', 1, 2],
  ];

  function flatsPane() {
    return el('div', { class: 'rc-pane rc-flats-pane' }, [
      el('div', { class: 'rc-pane-head' }, [
        el('strong', { text: 'Flat views' }),
        /* The same settings chip in both views, and in Pooled what it
           pools beside it. */
        modeChip(),
        viewMode === 'pooled' ? poolChip() : null,
        el('span', { class: 'hint', text: viewMode === 'pooled'
          ? 'pooled raw units · click a dot to open it'
          : 'raw units · drag a centre to move it' }),
      ]),
      el('div', { class: 'rc-flats' }, FLATS.map(([id]) =>
        el('canvas', { class: 'rc-canvas rc-flat', id }))),
    ]);
  }

  /* The event itself: four pictures of one event, from the read's own
     arrays. Nothing here is a thumbnail of something drawn elsewhere. */
  function eventPane() {
    const A = curAvg();
    if (A) return avgPane(A);
    const e = pickedEvent();
    if (!e) {
      return el('div', { class: 'rc-pane rc-event' }, [
        el('div', { class: 'empty-state rc-event-empty' }, [
          el('p', { text: 'Pick a dot to see its max-amp contact, its '
                        + 'spectrum against its own baseline, and the probe '
                        + 'around it.' }),
        ]),
      ]);
    }
    const cell = (id, title, sub) => el('div', { class: 'rc-ev-cell' }, [
      el('div', { class: 'rc-ev-t' }, [
        el('strong', { text: title }),
        sub ? el('span', { class: 'hint', text: sub }) : null,
      ].filter(Boolean)),
      el('canvas', { class: 'rc-canvas rc-ev', id }),
    ]);
    const why = eventWhy(e);
    /* Pooled: what is known about the trace -- read elsewhere and being
       read here, or why it is not -- as wrapping words above the pictures
       (2026-10-19). Always in the tree, so its progress can be swapped. */
    const away = viewMode === 'pooled'
      ? poolEventNote() || el('div', { class: 'rc-ev-note' }) : null;
    return el('div', { class: 'rc-pane rc-event' }, [
      away,
      why ? el('p', { class: 'rc-ev-why', text: why }) : null,
      el('div', { class: 'rc-ev-grid' }, [
        cell('rcTrace', 'Max-amp contact', (e.contact != null
          ? 'CSC' + e.contact : 'the contact the read names') + ', '
          + filterWords(shownParams(), true)),
        cell('rcSpec', 'Spectrum', 'event against its baseline'),
        cell('rcStack', 'Every contact', 'max contact marked'),
        /* Not the fit filter: the server takes the CSD on the dentate-spike
           band with the mains fitted out, and says so on the answer. On the
           fit filter, mains that differs a little between contacts survived
           the second difference and striped the picture. Before the answer
           arrives, the same words the server uses. */
        cell('rcCsd', 'CSD', ((evData && evData.ok !== false && evData.csd
                               && evData.csd.filter)
                              || '5–100 Hz, 60 Hz mains taken out')
                             + ' · down the probe'),
      ]),
    ].filter(Boolean));
  }

  /* Why this event is marked, in a sentence, or null when it is not.

     The words are about the measurement, not the flag: "2 of 3 axes" is
     what the square means, and the reason is what somebody deciding
     whether to trust it needs. */
  const MISSING_WORDS = {
    hw_ms: (x) => 'the half-width never came back to half-amplitude within '
                  + x + ' ms',
    hf_db: () => 'no HF power was measured',
    amp_uV: () => 'no amplitude was measured',
  };

  function eventWhy(e) {
    const cross = hz(crossFor(e));
    const miss = (e.missing || []).map((k2) =>
      (MISSING_WORDS[k2] || (() => k2 + ' is missing'))(cross));
    if (e.cls == null) {
      return 'Not placed: ' + (miss.join(', and ') || 'too few axes were '
             + 'measured') + ', so it is on fewer than two axes and has no '
             + 'class.';
    }
    const out = [];
    if (e.partial) {
      out.push('Assigned on 2 of 3 axes — ' + miss.join(', and ')
               + '. It went to the nearer centre on the two it has.');
    }
    if (e.wide) {
      out.push('Half-width found only with the search widened to ' + cross
               + ' ms: ' + fmt(e.hw_ms, 1) + ' ms. v1’s ' + CROSS_V1
               + ' ms search does not find it.');
    }
    return out.length ? out.join(' ') : null;
  }

  function legend() {
    const item = (cls, text) => el('span', { class: 'rc-lg' }, [
      el('i', { class: 'rc-lg-m ' + cls }), el('span', { text })]);
    const byBorder = !!(fit && fit.border_used);
    return el('div', { class: 'rc-legend' }, [
      item('rc-lg-ds', byBorder ? 'solid DS' : 'DS'),
      item('rc-lg-ied', byBorder ? 'solid IED' : 'IED'),
      byBorder ? item('rc-lg-amb rc-lg-amb-ds', 'outside, called DS') : null,
      byBorder ? item('rc-lg-amb rc-lg-amb-ied', 'outside, called IED') : null,
      item('rc-lg-square', 'on 2 of 3 axes'),
      item('rc-lg-wide', 'half-width by the widened search'),
      item('rc-lg-flip', 'set by hand'),
      item('rc-lg-hollow', 'not measured'),
      item('rc-lg-centre', 'centre'),
    ].filter(Boolean));
  }

  function pickedEvent() {
    if (viewMode === 'pooled') return poolPicked();
    if (picked == null || !fit || !fit.ok) return null;
    return (fit.events || []).find((x) => x.i === picked) || null;
  }

  /* The half-width search the picked event was measured with: Single's
     setting, or the pooled member's own. */
  function crossFor(e) {
    if (viewMode === 'pooled') {
      const pp = (poolMember(e) || {}).pin || {};
      const pr = pp.params || {};
      return Number(pr.cross_ms) || CROSS_V1;
    }
    return Number(shownParams().cross_ms) || CROSS_V1;
  }

  function fmt(v, d) {
    if (v == null || !isFinite(v)) return '—';
    return Number(v).toFixed(d == null ? 2 : d);
  }

  /* ==================================================================
     Picking, stepping
     ================================================================== */
  function setPicked(i) {
    if (!fit || !fit.ok) return;
    if (!(fit.events || []).some((e) => e.i === i)) return;
    picked = i;
    swap('.rc-pickbar', pickBar());
    swap('.rc-event', eventPane());
    drawAll();
    loadEvent();
    followXplore();
  }

  function step(d) {
    if (viewMode === 'pooled') { poolStep(d); return; }
    if (!fit || !fit.ok) return;
    const evs = fit.events || [];
    if (!evs.length) return;
    const at = picked == null ? (d > 0 ? -1 : 0)
                              : evs.findIndex((e) => e.i === picked);
    const next = ((at + d) % evs.length + evs.length) % evs.length;
    setPicked(evs[next].i);
  }

  /* The click panel's arrays, for the picked event.

     Keyed on the event AND the settings that change what it looks like --
     the filter, the window, the band, the half-width search. A flip or a moved centre changes the
     event's class and nothing about its trace, so it does not refetch. */
  const loadEvent = debounce(async function loadEvent_() {
    if (picked == null || !q.read || !fit || !fit.ok) return;
    if (savedOnly) {
      evData = { ok: false, error: 'This version is drawn from its saved '
        + 'numbers: its read is on ' + savedOnly.read_on + ', not here, so '
        + 'its traces open only there. Read the set here to see them.' };
      evKey = null;
      drawEvent();
      return;
    }
    // The filter is in it: on a new filter the same event's trace is a
    // different trace, and a key without it showed the old one.
    const key = JSON.stringify([picked, q.read, q.filt, q.mains_out, q.lo_hz,
                                q.hi_hz, q.win_ms, q.band_lo, q.band_hi,
                                q.cross_ms]);
    if (key === evKey && evData) { drawEvent(); return; }
    const mine = ++evGen;
    evBusy = true;
    tickBusy();
    let got;
    try {
      got = await apiPost('/api/rootcanal/event', fitBody({ i: picked }));
    } catch (e) {
      if (mine !== evGen) return;
      evBusy = false;
      tickBusy();
      evData = { ok: false, error: e.message };
      evKey = key;
      drawEvent();
      return;
    }
    if (mine !== evGen) return;
    evBusy = false;
    evData = got;
    evKey = key;
    tickBusy();
    drawEvent();
  }, 70);

  /* ==================================================================
     Banking
     ================================================================== */
  /* The two pictures this answer is, as they are on screen: the space, and
     the three flat views side by side on one sheet. From here because this
     is where they were drawn -- the backend never draws, the same rule
     dspca.py keeps. */
  function pngs() {
    const out = {};
    const k = ink();
    try {
      const sp = document.getElementById('rcSpace');
      if (sp && sp.width && sp.height) out.space = sp.toDataURL('image/png');
      const cvs = FLATS.map(([id]) => document.getElementById(id))
        .filter((c) => c && c.width && c.height);
      if (cvs.length) {
        const gap = Math.round(8 * (window.devicePixelRatio || 1));
        const w = cvs.reduce((a, c) => a + c.width, 0) + gap * (cvs.length - 1);
        const h = Math.max.apply(null, cvs.map((c) => c.height));
        const sheet = document.createElement('canvas');
        sheet.width = w; sheet.height = h;
        const g = sheet.getContext('2d');
        g.fillStyle = k.bg;
        g.fillRect(0, 0, w, h);
        let x = 0;
        for (const c of cvs) { g.drawImage(c, x, 0); x += c.width + gap; }
        out.flat = sheet.toDataURL('image/png');
      }
    } catch (e) {
      // A tainted or oversized canvas is not worth failing a bank over.
      reportClientError('rootcanal.figure', e.message, String(e && e.stack));
    }
    return out;
  }

  function bankDialog() {
    if (!fit || !fit.ok || fitting) return;
    const c = fit.counts || {};
    const cur = setOf();
    const v = versionOf(cur, q.from_version);
    const pooledSet = cur && cur.type === 'pooled';
    const body = pooledSet ? el('div', { class: 'rc-ask' }, [
      el('p', { text: bankLabel() + '.' }),
      el('ul', {}, [
        el('li', { text: 'Every event stays in the set, read from '
                         + (v ? BARRY.ui.versionLabel(v) : 'the set as it is '
                         + 'now') + ', with its stamp, label and origin as '
                         + 'they are. Nothing is taken out: a pooled set is '
                         + 'meant to hold both kinds.' }),
        el('li', { text: (c.ds || 0) + ' are named by a DS-like cluster and '
                         + (c.ied || 0) + ' by an IED-like one, each with its '
                         + 'cluster’s name' + (c.unmeasured
                           ? '; ' + c.unmeasured + ' could not be measured '
                             + 'and keep no name' : '') + '.' }),
        el('li', { text: 'How many of Incisor’s, Doppler’s and both '
                         + 'detectors’ events fell on each side goes in the '
                         + 'version’s note.' }),
        el('li', { text: 'The rule, the settings, the ' + q.flips.length
                         + ' event(s) set by hand and both pictures are '
                         + 'filed with it.' }),
      ]),
      el('p', { class: 'hint', text: fit.rule || '' }),
    ]) : el('div', { class: 'rc-ask' }, [
      el('p', { text: bankLabel() + '.' }),
      el('ul', {}, [
        el('li', { text: (c.ds || 0) + ' dentate spikes stay in the set, '
                         + 'read from ' + (v ? BARRY.ui.versionLabel(v) : 'the set as it '
                         + 'is now') + ', each with its stamp, label and '
                         + 'channel exactly as they are.' }),
        c.unmeasured
          ? el('li', { text: c.unmeasured + ' could not be measured and were '
                             + 'never clustered. Nothing showed them to be '
                             + 'IEDs, so they are counted with the dentate '
                             + 'spikes above; the reply says where they '
                             + 'actually went.' })
          : null,
        el('li', { text: (c.ied || 0) + ' go to “Hidden IEDs (Root Canal)” '
                         + 'as candidates, not decisions — a classifier said '
                         + 'this, not a person, so Checkup’s IED kind can go '
                         + 'through them.' }),
        (c.partial || c.wide)
          ? el('li', { text: [
              c.partial ? c.partial + ' were placed on two of their three '
                          + 'axes' : null,
              c.wide ? c.wide + ' have a half-width found only with the '
                       + 'search widened to ±' + hz(shownParams().cross_ms)
                       + ' ms' : null,
            ].filter(Boolean).join('; ') + '. Both are marked in the '
              + 'numbers filed with it.' })
          : null,
        el('li', { text: 'The rule, the settings, the ' + q.flips.length
                         + ' event(s) set by hand'
                         + (q.centres ? ', the moved centres' : '')
                         + ' and both pictures are filed with it.' }),
      ].filter(Boolean)),
      el('p', { class: 'hint', text: fit.rule || '' }),
    ]);
    /* The one bank dialog (constitution §6e), with Root Canal's account of
       what it files as its body. The shared one adds the entry's name, the
       note, who, and the sentence saying which version this becomes --
       "continues v5 -> v6" or "branches from v3 -> v3.1" off the version
       it read, which the label above used to guess as the tip plus one.

       A refusal stays in the dialog, except the one that has a dialog of
       its own: a set Root Canal has already cleaned, where cleaning again
       is offered as a deliberate second press. */
    let refused = null, rep = null;
    return BARRY.ui.bankDialog({
      kind: 'version',
      title: 'Bank this root canal?',
      entry: { name: (cur && cur.name) || '', versions: (cur && cur.versions) || [] },
      from: q.from_version,
      what: body,
      okText: 'Bank it',
      onBank: async ({ note }) => {
        try {
          rep = await send(note, false);
        } catch (e) {
          if (cleanedAlready(e)) { refused = { msg: e.message, note }; return; }
          throw e;
        }
      },
    }).then((ok) => {
      if (refused) { refusedDialog(refused.msg, refused.note); return null; }
      return ok && rep ? after(rep, fit.counts || {}) : null;
    });
  }

  function refusedDialog(msg, note) {
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'This set has been through Root Canal already' }),
        el('div', { class: 'spacer' })]),
      el('div', { class: 'mb' }, [el('div', { class: 'rc-ask' }, [
        el('p', { text: msg }),
        el('p', { class: 'hint', text:
          'Reading from the version before it is almost always what was '
          + 'meant: pick it under “Read the stamps from”. Cleaning again '
          + 'takes events out of a set that has already had its IEDs '
          + 'removed.' }),
      ])]),
      BARRY.ui.modalFoot([], [
        BARRY.ui.button({ kind: 'ghost', text: 'Clean again anyway',
          extra: 'rc-again',
          title: 'Bank a second pass over Root Canal’s own output.',
          onclick: () => { closeModal(); commit(note, true); } }),
        BARRY.ui.button({ kind: 'primary', text: 'Close',
                          onclick: closeModal }),
      ]),
    ]), { replace: true });
  }

  function send(note, again) {
    return apiPost('/api/rootcanal/commit', fitBody({
      note: note || '', pngs: pngs(),
      again: again ? true : undefined,
    }));
  }

  function cleanedAlready(e) {
    const v = versionOf(setOf(), q.from_version);
    return (v && v.tag === 'rootcanal') || /again/i.test((e && e.message) || '');
  }

  async function commit(note, again) {
    let rep;
    const expect = fit.counts || {};
    try {
      rep = await send(note, again);
    } catch (e) {
      /* A SET ROOT CANAL HAS ALREADY CLEANED IS REFUSED, and says why.

         Running this over its own output takes a second bite: k-means
         will still split a clean set in two, and the "IEDs" it finds are
         the loudest dentate spikes. The server's sentence is shown as it
         is, and cleaning again anyway is on offer only as the secondary
         action of a dialog -- a deliberate second press, never the
         default one. */
      if (!again && cleanedAlready(e)) {
        refusedDialog(e.message, note);
      } else {
        toast(e.message, 'err', 12000);
      }
      return null;
    }
    return after(rep, expect);
  }

  /* What a commit that went through does next, whichever way it was sent. */
  function after(rep, expect) {
    /* A commit that changed nothing wrote nothing, and says so -- pressing
       it twice on one answer must not read as two versions. */
    if (rep.already) {
      /* Information, not a failure (2026-10-20): the bank already holds
         this set, nothing at all was written, and the sentence says how to
         keep these numbers if they are wanted. */
      toast(rep.already, null, 12000);
      return rep;
    }
    /* A pooled set is named, not split (app.py, `_rootcanal_commit_pooled`):
       nothing comes out, so there is no IED count to hold against. */
    if (rep.pooled) {
      const nm = rep.named || {};
      toast('Banked: every event named by its cluster, as v' + rep.ds_version
            + ' — ' + (nm.ds || 0) + ' DS-like, ' + (nm.ied || 0)
            + ' IED-like, nothing removed. The previous version is kept.',
            'ok', 10000);
      BARRY.activity.log('rootcanal.commit', {
        gid: q.gid, entry: q.entry, ds_version: rep.ds_version,
        pooled: true, named: rep.named,
      });
      loadSingle();
      cands = null;
      loadCandidates();
      return rep;
    }
    toast('Banked: the set as v' + rep.ds_version + ' with ' + rep.kept
          + ' kept' + (rep.ied_entry
            ? ', and ' + rep.removed + ' IED' + (rep.removed === 1 ? '' : 's')
              + ' as v' + rep.ied_version + ' of “Hidden IEDs (Root Canal)”'
            : ', and no IEDs to bank')
          + '. The previous version is kept.', 'ok', 10000);
    const want = (expect.ds || 0) + (expect.unmeasured || 0);
    if (rep.kept !== want || rep.removed !== (expect.ied || 0)) {
      toast('The bank kept ' + rep.kept + ' and removed ' + rep.removed
            + '; the panel said ' + want + ' and ' + (expect.ied || 0)
            + '. Check the new version before anything reads it.',
            'warn', 15000);
    }
    BARRY.activity.log('rootcanal.commit', {
      gid: q.gid, entry: q.entry, ds_version: rep.ds_version,
      ied_entry: rep.ied_entry, kept: rep.kept, removed: rep.removed,
    });
    // The set's versions have changed, so the chooser is stale -- and Bank
    // kept a version of the single too.
    if (rep.single) {
      viewing = { artifact_id: rep.single.artifact_id,
                  v: rep.single.version, nickname: null };
      cleanSig = sigOf();
    }
    loadSingle();
    cands = null;
    loadCandidates();
    return rep;
  }

  /* ==================================================================
     Many sets at once
     ================================================================== */
  /* REBUILT 2026-10-19 in the house's picker shape -- Doppler's and Braces'
     Many: what the plan says in a sentence, a search, a chip for each value
     of each thing a set is, the tools that tick what is shown, the list,
     the sets that cannot be read with their reasons, and the primary last,
     naming what it will do.

     ONE CARD, RECONCILED IN PLACE. `render()` empties the panel and builds
     it again, which is right for a change of view and wrong for a tick: the
     list lost its scroll and the search box its cursor on every one. So
     the card is a shell whose parts are kept by `BARRY.ui.sections`, and a
     tick, a chip, a letter typed or a poll of a running batch goes through
     `bulkRefresh()`, which rebuilds only the parts whose content changed.
     A tick rebuilds nothing in the list at all: its row is changed where it
     stands (`syncTicks`).

     ALREADY READ IS FOLDED UNDER THE LIST, counted, beside "Left out"
     (2026-10-19): the list is the sets that cost a read, and the ones that
     cost nothing are a fold away with Open and Bank… on each row. They
     tick like the rest -- ticking one costs nothing, the batch finds its
     read on file and the row lands at once beside the fresh ones -- and
     the search and the chips narrow the folds as they narrow the list. */
  function bulkCard() {
    const card = el('div', { class: 'card rc-bulk-card' }, [
      el('div', { class: 'section-label', text: 'Read a batch' }),
      el('div', { class: 'rc-bulk-body' }),
    ]);
    bulkFill(card);
    return card;
  }

  function bulkFill(card) {
    const body = card.querySelector('.rc-bulk-body');
    if (!body) return;
    BARRY.ui.sections(body, bulk.job || bulk.sending ? bulkRunParts()
      : bulk.plan ? bulkPickParts()
      : [{ key: 'wait', enter: false, sig: 'wait', build: () => el('div', {}, [
          loader('Working out what could be read',
                 'every aligned set in the bank, checked against what this '
                 + 'computer has read')]) }]);
  }

  /* The card where it stands; false when it is not on screen. */
  function bulkRefresh() {
    const box = host();
    const card = box && box.querySelector('.rc-bulk-card');
    if (!card) return false;
    bulkFill(card);
    return true;
  }

  /* What a set can be filtered by, each with its mark: stroked on
     `currentColor` at 16 px, the ToolKit's own convention (toolkit.js,
     `TOOL_ICONS`), so a mark takes its chip's state in every theme. */
  const BULK_ICO = {
    project: 'M1.5 3.5h4.5l1.5 1.5h7v7.5h-13z',
    // Side on, nose to the right: it was a dome with its tail curled over
    // it, which read as a shoe at 13 px.
    mouse: 'M3 11.5c0-3 2.5-5.5 5.5-5.5 2.4 0 4.5 1.9 5 4.3.1.7-.4 1.2-1.1 '
           + '1.2zM8.9 6.2a1.7 1.7 0 1 1 2.8 1M11.4 9h.01M3 11.5c-1.3.1-1.9 '
           + '1-1.5 2',
    group: 'M5.5 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM1.5 13c0-2.2 1.8-4 4-4s4 '
           + '1.8 4 4M11 7.2a1.7 1.7 0 1 0 0-3.4M12 9.2c1.5.4 2.5 1.9 2.5 3.8',
    subgroup: 'M3.5 2.5v10M3.5 7.5h5M3.5 12.5h5M10.5 6h3.5v3h-3.5zM10.5 '
              + '11h3.5v3h-3.5z',
    condition: 'M6 2h4M6.5 2v4.2L2.8 12.4c-.5.9.1 1.6 1 1.6h8.4c.9 0 1.5-.7 '
               + '1-1.6L9.5 6.2V2M4.6 9.5h6.8',
    probe: 'M7 1.5h2v10l-1 3-1-3zM8 4.5h.01M8 7h.01M8 9.5h.01',
    tick: 'M3.5 8.5l3 3 6-7',
    // The folds: a set already read (an open book), and one left out.
    done: 'M8 4.2C6.6 3 4.6 2.6 2 2.8v9.6c2.6-.2 4.6.2 6 1.4 1.4-1.2 3.4-1.6 '
          + '6-1.4V2.8c-2.6-.2-4.6.2-6 1.4zM8 4.2v9.6',
    left: 'M8 1.8a6.2 6.2 0 1 0 0 12.4A6.2 6.2 0 0 0 8 1.8zM3.6 3.6l8.8 8.8',
  };
  const bulkIco = (d, extra) => el('svg', {
    class: 'rc-bulk-ico' + (extra ? ' ' + extra : ''), viewBox: '0 0 16 16',
    'aria-hidden': 'true', html: '<path d="' + d + '" />' });

  /* [key, words, value of a row, mark]. A category is offered once it
     splits the sets two ways -- a chip that every set has filters nothing.
     Read or not is not one of them: that is the list against its fold. */
  const BULK_CATS = [
    ['project', 'project', (r) => r.project, BULK_ICO.project],
    ['mouse_type', 'mouse type', (r) => r.mouse_type, BULK_ICO.mouse],
    ['group', 'group', (r) => r.group, BULK_ICO.group],
    ['subgroup', 'subgroup', (r) => r.subgroup, BULK_ICO.subgroup],
    ['condition', 'condition', (r) => r.condition, BULK_ICO.condition],
    ['probe', 'probe', (r) => r.probe, BULK_ICO.probe],
  ];

  const numOr = (v) => (v == null || v === '' || !isFinite(Number(v))
    ? Infinity : Number(v));
  /* Names in natural order, the page's one rule (ui.js `natCompare`,
     2026-10-20): m1, m3, m5, m12 -- numbers by value, case ignored. */
  const natural = (a, b) => (BARRY.ui && BARRY.ui.natCompare
    ? BARRY.ui.natCompare(a, b)
    : String(a).localeCompare(String(b), undefined, { numeric: true }));
  /* Project, then mouse and session as NUMBERS: as strings m13 came
     before m2. */
  function bulkOrder(a, b) {
    return String(a.project || '~').localeCompare(String(b.project || '~'))
      || (numOr(a.mouse) - numOr(b.mouse)) || natural(a.mouse, b.mouse)
      || (numOr(a.session) - numOr(b.session))
      || natural(a.label, b.label);
  }

  /* Every set that can be read here: not read yet, and already read. */
  let bulkMemo = { plan: null, rows: [] };
  function bulkRows() {
    if (bulkMemo.plan === bulk.plan) return bulkMemo.rows;
    const bp = bulk.plan || {};
    bulkMemo = { plan: bulk.plan,
                 rows: (bp.todo || []).concat(bp.done || []).sort(bulkOrder) };
    return bulkMemo.rows;
  }

  const bulkFiltered = () => !!String(bulk.filt.q || '').trim()
    || BULK_CATS.some(([k]) => (bulk.filt[k] || []).length);

  function bulkHay(r) {
    return [r.label, r.name, r.project, r.mouse_type, r.group, r.subgroup,
            r.condition, r.probe, r.date,
            r.mouse != null ? 'm' + r.mouse : '',
            r.session != null ? 's' + r.session : '',
            r.cached ? 'already read' : 'not read yet']
      .filter(Boolean).join(' ').toLowerCase();
  }

  /* Every word typed has to match somewhere; inside one category any chip
     pressed will do, and every category with one pressed has to match. */
  function bulkShown(r) {
    const f = bulk.filt;
    for (const [key, , get] of BULK_CATS) {
      const want = f[key] || [];
      if (want.length && want.indexOf(String(get(r))) < 0) return false;
    }
    const words = String(f.q || '').trim().toLowerCase().split(/\s+/)
      .filter(Boolean);
    if (!words.length) return true;
    const hay = bulkHay(r);
    return words.every((w) => hay.indexOf(w) >= 0);
  }

  /* The list is the sets not read yet; the ones already read are the fold
     under it. Both are narrowed by the search and the chips. */
  function bulkPickParts() {
    const rows = bulkRows();
    const todo = rows.filter((r) => !r.cached);
    const done = rows.filter((r) => r.cached);
    const left = (bulk.plan && bulk.plan.blocked) || [];
    const shown = rows.filter(bulkShown);
    const ticked = rows.filter((r) => bulk.want[r.entry_id]);
    const fs = JSON.stringify(bulk.filt);
    const tk = ticked.map((r) => r.entry_id).join(',');
    return [
      { key: 'say', enter: false, sig: [bulk.rev, bulk.last],
        build: () => bulkSay(todo, done, left) },
      { key: 'find', enter: false, sig: 'find', build: bulkSearch },
      { key: 'chips', enter: false, sig: [bulk.rev, fs],
        build: () => bulkChips(rows) },
      { key: 'tools', enter: false, sig: [bulk.rev, fs, tk],
        build: () => bulkTools(rows, shown, ticked) },
      { key: 'list', enter: false, sig: [bulk.rev, fs],
        build: () => bulkList(todo, shown.filter((r) => !r.cached)) },
      { key: 'done', enter: false, sig: [bulk.rev, fs],
        build: () => bulkDone(done, shown.filter((r) => r.cached)),
        // How many of them are ticked, said without rebuilding the rows.
        update: (box) => {
          const n = done.filter((r) => bulk.want[r.entry_id]).length;
          const t = box.querySelector('.rc-bulk-fold-tk');
          const w = n ? n + ' ticked' : '';
          if (t && t.textContent !== w) t.textContent = w;
        } },
      { key: 'left', enter: false, sig: [bulk.rev, fs],
        build: () => bulkLeft(left) },
      { key: 'go', enter: false, sig: [bulk.rev, tk, !!bulk.sending],
        build: () => bulkGo(ticked) },
    ];
  }

  /* One sentence: how many, and what a tick costs. That the batch banks
     nothing is said once, on the line beside the primary. */
  function bulkSay(todo, done, left) {
    if (bulk.plan && bulk.plan.ok === false) {
      return el('p', { class: 'warn-line rc-bulk-say', text:
        'The list of sets could not be worked out: '
        + (bulk.plan.error || 'no reason given') });
    }
    const s = (n) => (n === 1 ? '' : 's');
    const L = bulk.last;
    return el('div', { class: 'rc-bulk-say' }, [
      el('p', { class: 'hint', text: todo.length || done.length
        ? todo.length + ' set' + s(todo.length) + ' not read yet, '
          + 'each minutes of disk'
          + (done.length ? ', and ' + done.length + ' already read, which '
                           + 'open at once' : '')
          + '. Tick the ones to read.'
        : 'No set can be read from here yet.'
          + (left.length ? ' The reasons are below.' : '') }),
      // The batch before, until the next one: what landed, what failed.
      L ? el('p', { class: 'rc-bulk-last' + (L.failed.length ? ' bad' : ''),
        text: 'The last batch ' + (L.quit ? 'was stopped: ' : 'read ')
          + L.n + ' of ' + L.of + (L.quit ? ' read' : '')
          + (L.failed.length
            ? '. ' + L.failed.length + ' failed, and '
              + (L.failed.length === 1 ? 'is' : 'are') + ' still ticked to '
              + 'send again: ' + L.failed.map((f) => f.label + ' ('
                + (f.why || 'no reason given') + ')').join('; ')
            : '') + '.' }) : null,
    ]);
  }

  /* Built once and kept (its sig never changes), so it keeps its cursor
     while the list under it changes. */
  function bulkSearch() {
    const f = BARRY.ui.searchField({
      placeholder: 'Type a set, mouse, session, date or project',
      value: bulk.filt.q, width: '30rem',
      title: 'Every word has to match: the set’s name, the mouse (m13), the '
           + 'session (s2), the date, the project, the group or condition.',
      oninput: (e) => { bulk.filt.q = e.target.value; bulkRefresh(); },
    });
    f.classList.add('rc-bulk-find');
    f.input.setAttribute('data-fk', 'rc-bulk-search');
    f.input.setAttribute('aria-label', 'Search the sets');
    return f;
  }

  /* A category whose every value is another's, word for word, is one
     category said twice (a mouse type that is only ever its project's
     name): the second is not offered. Only word for word (2026-10-19): a
     condition that merely happened to split the sets as the projects do
     was hidden, and "where is condition?" has no answer on the page. */
  function samePartition(rows, a, b) {
    return rows.every((r) => String(a(r)) === String(b(r)));
  }

  function bulkChips(rows, filt, again) {
    const f = filt || bulk.filt;
    const refresh = again || bulkRefresh;
    const cats = [];
    const offered = [];
    for (const [key, words, get, d] of BULK_CATS) {
      const counts = new Map();
      for (const r of rows) {
        const v = get(r);
        if (v == null || v === '') continue;
        counts.set(String(v), (counts.get(String(v)) || 0) + 1);
      }
      const on = f[key] || [];
      if (!on.length && (counts.size < 2
          || offered.some((g) => samePartition(rows, g, get)))) continue;
      offered.push(get);
      /* A value no set has any more (its sets were read and banked) but
         still pressed stays offered, at 0, so it can be let go of. */
      for (const v of on) if (!counts.has(v)) counts.set(v, 0);
      cats.push(el('div', { class: 'rc-bulk-cat', 'data-cat': key }, [
        el('span', { class: 'rc-bulk-k', text: words }),
        el('div', { class: 'rc-bulk-vals' },
          Array.from(counts.keys()).sort(natural).map((v) => {
            const lit = on.indexOf(v) >= 0;
            const n = counts.get(v);
            // The shared button (§3), its mark and its count inside it.
            const b = BARRY.ui.button({ kind: 'mini', on: lit,
              extra: 'rc-bulk-chip',
              title: lit
                ? 'Showing only ' + words + ' ' + v + '. Press again to show '
                  + 'every ' + words + '.'
                : 'Show only ' + words + ' ' + v + ' (with any other ' + words
                  + ' pressed too): ' + n + ' set' + (n === 1 ? '' : 's') + '.',
              onclick: () => {
                f[key] = lit ? on.filter((x) => x !== v) : on.concat([v]);
                refresh();
              },
              children: [
                bulkIco(lit ? BULK_ICO.tick : d, lit ? 'rc-bulk-lit' : null),
                el('span', { class: 'rc-bulk-chip-v', text: v }),
                el('span', { class: 'rc-bulk-chip-n', text: String(n) }),
              ] });
            b.type = 'button';
            b.setAttribute('aria-pressed', lit ? 'true' : 'false');
            b.dataset.v = v;
            return b;
          })),
      ]));
    }
    return el('div', { class: 'rc-bulk-chips' }, cats);
  }

  /* A tick, or many, changed where the rows stand: the list is not rebuilt,
     so it keeps its scroll. Then the counts and the primary. */
  function bulkTick(fn) {
    fn();
    syncTicks();
    bulkRefresh();
  }

  function syncTicks() {
    const box = host();
    for (const row of (box ? box.querySelectorAll('.rc-bulk-row[data-id]') : [])) {
      const on = !!bulk.want[row.dataset.id];
      const cb = row.querySelector('input[type=checkbox]');
      if (cb && cb.checked !== on) cb.checked = on;
      row.classList.toggle('on', on);
    }
  }

  function bulkTools(rows, shown, ticked) {
    const notYet = shown.filter((r) => !r.cached);
    const hidden = ticked.filter((r) => !bulkShown(r)).length;
    return el('div', { class: 'tk-actions inc-pick-tools rc-bulk-tools' }, [
      BARRY.ui.button({ kind: 'ghost', size: 'sm', extra: 'rc-bulk-all',
        text: 'Select all ' + shown.length + ' shown',
        disabled: !shown.length,
        title: 'Tick every set the search and the chips show, the list and '
             + '“Already read” alike. Ones they hide keep whatever they had.',
        onclick: () => bulkTick(() => {
          for (const r of shown) bulk.want[r.entry_id] = true;
        }) }),
      BARRY.ui.button({ kind: 'ghost', size: 'sm', extra: 'rc-bulk-fresh',
        text: 'Only the ' + notYet.length + ' not read yet',
        disabled: !notYet.length,
        title: 'Of the sets shown, tick the ones never read here and untick '
             + 'the ones already read.',
        onclick: () => bulkTick(() => {
          for (const r of shown) {
            if (r.cached) delete bulk.want[r.entry_id];
            else bulk.want[r.entry_id] = true;
          }
        }) }),
      BARRY.ui.button({ kind: 'ghost', size: 'sm', extra: 'rc-bulk-none',
        text: 'Unselect all', disabled: !ticked.length,
        title: 'Untick every set, shown or not.',
        onclick: () => bulkTick(() => { bulk.want = {}; }) }),
      bulkFiltered() ? BARRY.ui.button({ kind: 'link',
        extra: 'rc-bulk-unfilter', text: 'Clear the search and chips',
        title: 'Show every set again. What is ticked stays ticked.',
        onclick: () => {
          bulk.filt = { q: '' };
          const box = host();
          const inp = box && box.querySelector('.rc-bulk-find input');
          if (inp) inp.value = '';
          bulkRefresh();
        } }) : null,
      el('span', { class: 'hint quiet rc-bulk-count', text:
        ticked.length + ' ticked  ·  ' + shown.length + ' of ' + rows.length
        + ' shown' + (hidden ? '  ·  ' + hidden + ' of the ticked '
                              + (hidden === 1 ? 'is' : 'are')
                              + ' hidden by the filters' : '') }),
    ]);
  }

  /* The sets not read yet. `todo` is all of them, `shown` the ones the
     search and the chips leave. */
  function bulkList(todo, shown) {
    const list = el('div', { class: 'inc-pick-list rc-bulk-list',
                             'data-keep-scroll': 'rc-bulk-list' });
    if (!shown.length) {
      const done = bulkRows().length - todo.length;
      list.appendChild(el('div', { class: 'empty-state rc-bulk-empty',
        text: todo.length
          ? 'No set that is not read yet matches that. Clear the search and '
            + 'the chips to see all ' + todo.length + '.'
          : done ? 'Every set that can be read here has been read. They are '
                   + 'under “Already read”, ready to open.'
          : 'No set can be read from here yet; the reasons are below.' }));
    }
    for (const r of shown) list.appendChild(bulkRow(r));
    return list;
  }

  /* Under the name: what tells two sets of one session apart (the entry's
     own name, less the session it repeats), the events, the probe, and
     the facts the chips filter by. */
  function bulkSub(r) {
    let nm = r.name && r.name !== r.label ? String(r.name) : '';
    if (nm && r.label && nm.indexOf(r.label) === 0) {
      nm = nm.slice(r.label.length).replace(/^\s*[·:–-]\s*/, '');
    }
    const n = r.n_good != null ? r.n_good : r.n;
    return [
      nm || null,
      n != null ? n + ' event' + (n === 1 ? '' : 's') : null,
      r.probe ? 'probe ' + r.probe : null,
      r.mouse_type && r.mouse_type !== r.project ? r.mouse_type : null,
      r.group ? 'group ' + r.group : null,
      r.subgroup ? 'subgroup ' + r.subgroup : null,
      r.condition || null,
    ].filter(Boolean).join('  ·  ');
  }

  /* One set. The tick and the name are one label, so the name ticks it
     too; an already-read set has Open and Bank… of its own beside them,
     outside the label, so pressing one does not also tick it. A tick
     changes this row and the counts IN PLACE. */
  function bulkRow(r) {
    const on = !!bulk.want[r.entry_id];
    const row = el('div', {
      class: 'inc-pick rc-bulk-row' + (on ? ' on' : '') + (r.cached ? ' done' : ''),
      'data-id': r.entry_id,
    }, [
      el('label', { class: 'rc-bulk-tick' }, [
        el('input', {
          type: 'checkbox', checked: on ? 'checked' : null,
          'aria-label': 'Read ' + r.label,
          onchange: (e) => {
            if (e.target.checked) bulk.want[r.entry_id] = true;
            else delete bulk.want[r.entry_id];
            row.classList.toggle('on', e.target.checked);
            bulkRefresh();
          },
        }),
        el('span', { class: 'ip-main' }, [
          el('span', { class: 'ip-name', text: r.label }),
          el('span', { class: 'ip-sub', text: bulkSub(r) }),
        ]),
      ]),
      r.cached ? el('span', { class: 'rc-bulk-row-acts' }, [
        BARRY.ui.button({ kind: 'mini', text: 'Open', extra: 'rc-bulk-open',
          title: 'Open it now. Its read is on file, so nothing is read.',
          onclick: () => openRead(r.entry_id) }),
        BARRY.ui.button({ kind: 'mini', text: 'Bank…', extra: 'rc-bulk-bank',
          title: 'Open it and put up the bank dialog for the answer as '
               + 'fitted. Nothing is banked until you say so there.',
          onclick: () => openRead(r.entry_id, { bank: true }) }),
      ]) : null,
    ]);
    return row;
  }

  /* The sets already read, folded, with how many there are, how many the
     search and the chips leave, and how many are ticked (kept up to date
     by the part's `update`, without rebuilding the rows). */
  function bulkDone(done, shown) {
    const box = el('div', {});
    if (!done.length) return box;
    box.appendChild(el('details', { class: 'inc-blocked rc-bulk-fold rc-bulk-done',
                                    'data-keep': 'rc-bulk-done' }, [
      el('summary', {}, [
        bulkIco(BULK_ICO.done),
        el('span', { class: 'rc-bulk-fold-h', text: 'Already read' }),
        el('span', { class: 'rc-bulk-fold-n', text: bulkFiltered()
          ? shown.length + ' of ' + done.length : String(done.length) }),
        el('span', { class: 'rc-bulk-fold-tk' }),
        el('span', { class: 'rc-bulk-fold-say', text:
          'open at once; nothing is read again' }),
      ]),
      el('div', { class: 'inc-pick-list rc-bulk-list rc-bulk-done-list',
                  'data-keep-scroll': 'rc-bulk-done-list' },
        shown.length ? shown.map(bulkRow)
          : [el('div', { class: 'empty-state rc-bulk-empty', text:
              'None of the ' + done.length + ' matches that.' })]),
    ]));
    return box;
  }

  /* The sets that cannot be read yet, folded, grouped by their reason --
     a hundred rows each repeating "Braces hasn't aligned this set yet" is
     a reason said a hundred times. The search and the chips narrow it too,
     so "why is m13 s5 not in the list" is answered by typing it. */
  function bulkLeft(left) {
    const box = el('div', {});
    if (!left.length) return box;
    const shown = left.filter(bulkShown);
    const by = new Map();
    for (const r of shown) {
      const w = String(r.why || 'no reason given');
      if (!by.has(w)) by.set(w, []);
      by.get(w).push(r);
    }
    const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
    box.appendChild(el('details', { class: 'inc-blocked rc-bulk-fold rc-bulk-left',
                                    'data-keep': 'rc-bulk-left' }, [
      el('summary', {}, [
        bulkIco(BULK_ICO.left),
        el('span', { class: 'rc-bulk-fold-h', text: 'Left out' }),
        el('span', { class: 'rc-bulk-fold-n', text: bulkFiltered()
          ? shown.length + ' of ' + left.length : String(left.length) }),
        el('span', { class: 'rc-bulk-fold-say', text:
          'cannot be read yet; each with its reason' }),
      ]),
      shown.length ? null : el('p', { class: 'hint quiet rc-bulk-empty', text:
        'None of the ' + left.length + ' matches that.' }),
      el('div', { class: 'rc-bulk-whys' }, Array.from(by.entries())
        .sort((a, b) => b[1].length - a[1].length)
        .map(([why, rs]) => el('div', { class: 'rc-bulk-why' }, [
          el('div', { class: 'rc-bulk-why-h' }, [
            el('strong', { text: cap(why) }),
            el('span', { class: 'rc-bulk-why-n', text: String(rs.length) }),
          ]),
          el('p', { class: 'rc-bulk-why-sets',
                    text: rs.map((r) => r.label).join('  ·  ') }),
        ]))),
    ]));
    return box;
  }

  /* The cost, said before it is spent, and the one primary, last. */
  function bulkGo(ticked) {
    const fresh = ticked.filter((r) => !r.cached);
    const again = ticked.length - fresh.length;
    const evs = fresh.reduce((s, r) => s + (Number(r.n_good) || 0), 0);
    const words = !ticked.length ? 'Tick the sets to read, above.'
      : [fresh.length ? fresh.length + ' to read (' + evs.toLocaleString()
                        + ' events), one after another, minutes each'
                      : null,
         again ? again + ' already read, which ' + (again === 1 ? 'lands' : 'land')
                 + ' at once' : null].filter(Boolean).join('  ·  ')
        + '. Each can be opened and banked as soon as it lands; the batch '
        + 'itself banks nothing.';
    return BARRY.ui.actions([
      el('p', { class: 'hint rc-bulk-cost', text: words }),
      BARRY.ui.button({ kind: 'primary', extra: 'rc-bulk-go',
        text: ticked.length ? 'Read the ' + ticked.length + ' ticked'
                            : 'Read the ticked',
        disabled: !ticked.length || bulk.sending, onclick: runBulk }),
    ], { extra: 'rc-bulk-go-row' });
  }

  /* ---- the batch, while it reads ---------------------------------------
     A row per set with its own state and a dot, and one bar over them:
     Braces' batch card (`flightRows`, `.br-fbar`). A set that has landed
     can be opened -- and banked -- while the rest read: the read is the
     expensive half and it is finished for that one. "Bank…" opens it and
     puts the bank dialog up once its pictures are drawn, so what is filed
     is what was on screen; the batch itself never banks anything. */
  function bulkMembers() {
    const ms = (bulk.job && bulk.job.members) || [];
    if (ms.length) return ms;
    // Sent, and the server has not listed them yet: they are waiting.
    return (bulk.sent || []).map((m) => ({ id: m.id, label: m.label,
                                           status: 'waiting' }));
  }

  function bulkTally(ms) {
    const n = { waiting: 0, running: 0, done: 0, cached: 0, error: 0,
                stopped: 0 };
    for (const m of ms) {
      if (m.status === 'done' && m.cached) n.cached += 1;
      n[m.status in n ? m.status : 'waiting'] += 1;
    }
    return n;
  }

  function bulkRunParts() {
    const ms = bulkMembers();
    const n = bulkTally(ms);
    const j = bulk.job || {};
    return [
      { key: 'rline', enter: false,
        sig: [j.status, !!bulk.stopping, ms.length, n.done, n.cached,
              n.running, n.waiting, n.error, n.stopped],
        build: () => bulkRunLine(ms, n) },
      { key: 'rbar', enter: false, sig: 'rbar',
        build: () => el('div', { class: 'br-fbar rc-bulk-bar', role: 'progressbar',
                                 'aria-label': 'How far the batch has got',
                                 'aria-valuemin': '0', 'aria-valuemax': '100' }, [
          el('i', { class: 'ok' }), el('i', { class: 'bad' }),
          el('i', { class: 'run' })]),
        update: (b) => paintBulkBar(b, ms, n) },
      { key: 'rrows', enter: false,
        sig: ms.map((m) => [m.id, m.status, m.cached ? 1 : 0, m.error || '']
          .join(':')).join('|'),
        build: () => bulkRunRows(ms),
        // How far the one reading has got, without rebuilding the rows.
        update: (box) => {
          for (const row of box.querySelectorAll('[data-mid]')) {
            const m = ms.find((x) => x.id === row.dataset.mid);
            const cell = row.querySelector('.dop-batch-state');
            const w = m ? bulkMemberWords(m) : null;
            if (cell && w && cell.textContent !== w) cell.textContent = w;
          }
        } },
      { key: 'racts', enter: false, sig: [j.id, j.status, !!bulk.stopping],
        build: bulkRunActs },
    ];
  }

  function bulkRunLine(ms, n) {
    const j = bulk.job || {};
    const state = bulk.stopping || j.status === 'canceled' ? 'stopping'
      : j.id ? 'reading' : 'sending';
    return el('div', { class: 'rc-bulk-line' }, [
      el('strong', { text: ms.length + ' set' + (ms.length === 1 ? '' : 's')
                           + ', ' + state }),
      el('span', { class: 'hint', text: [
        n.done - n.cached ? (n.done - n.cached) + ' read' : null,
        n.cached ? n.cached + ' already read' : null,
        n.running ? n.running + ' reading now' : null,
        n.waiting ? n.waiting + ' waiting' : null,
        n.error ? n.error + ' failed' : null,
        n.stopped ? n.stopped + ' stopped' : null,
      ].filter(Boolean).join('  ·  ') || 'starting' }),
    ]);
  }

  /* Landed, failed and reading, as one bar that never goes back: a set
     part-way through counts for the part it has read. */
  function paintBulkBar(b, ms, n) {
    const all = Math.max(1, ms.length);
    let part = 0;
    for (const m of ms) {
      if (m.status === 'running') {
        part += m.of ? Math.min(1, (m.done || 0) / m.of) * 0.9 + 0.05 : 0.05;
      }
    }
    const pct = (v) => (100 * v / all).toFixed(2) + '%';
    const [ok, bad, run] = b.children;
    ok.style.width = pct(n.done);
    bad.style.width = pct(n.error);
    run.style.width = pct(part);
    b.setAttribute('aria-valuenow', String(Math.round(100 * (n.done + n.error)
                                                       / all)));
    b.title = n.done + ' of ' + ms.length + ' read'
      + (n.error ? ', ' + n.error + ' failed' : '');
  }

  function bulkMemberWords(m) {
    if (m.status === 'error') return 'failed: ' + (m.error || 'no reason given');
    if (m.status === 'done') {
      return m.cached ? 'already read — opens at once'
                      : 'read — open it to look, or bank it';
    }
    if (m.status === 'running') {
      return m.of ? 'reading channel ' + Math.min((m.done || 0) + 1, m.of)
                    + ' of ' + m.of
                  : 'getting it ready';
    }
    if (m.status === 'stopped') return 'stopped part-way; nothing of it kept';
    return 'waiting its turn';
  }

  function bulkRunRows(ms) {
    const box = el('div', { class: 'dop-batch rc-bulk-run',
                            'data-keep-scroll': 'rc-bulk-run' });
    for (const m of ms) {
      const st = m.status === 'error' ? 'failed' : (m.status || 'waiting');
      const ready = m.status === 'done';
      box.appendChild(el('div', {
        class: 'dop-batch-row rc-bulk-member ' + st, 'data-mid': m.id,
      }, [
        el('span', { class: 'dop-batch-dot', 'aria-hidden': 'true' }),
        el('span', { class: 'dop-batch-name', text: m.label || m.id }),
        el('span', { class: 'dop-batch-state', text: bulkMemberWords(m) }),
        // Always there, empty until it lands, so the columns hold.
        el('span', { class: 'rc-bulk-row-acts' }, ready ? [
          BARRY.ui.button({ kind: 'mini', text: 'Open', extra: 'rc-bulk-open',
            title: 'Open this one now. The rest keep reading.',
            onclick: () => openRead(m.id) }),
          BARRY.ui.button({ kind: 'mini', text: 'Bank…', extra: 'rc-bulk-bank',
            title: 'Open it and put up the bank dialog for the answer as '
                 + 'fitted. Nothing is banked until you say so there.',
            onclick: () => openRead(m.id, { bank: true }) }),
        ] : []),
      ]));
    }
    return box;
  }

  function bulkRunActs() {
    const j = bulk.job || {};
    return BARRY.ui.actions([
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Stop',
        extra: 'rc-bulk-stop',
        disabled: !j.id || bulk.stopping || j.status === 'canceled',
        title: 'Stop the batch. The sets already read are kept; the one '
             + 'being read stops where it is, and nothing of it is kept.',
        onclick: stopBulk }),
    ]);
  }

  async function loadBulk() {
    if (bulk.loading) return;
    bulk.loading = true;
    try {
      bulk.plan = await api('/api/rootcanal/batch/plan');
    } catch (e) {
      bulk.plan = { ok: false, error: e.message, todo: [], done: [],
                    blocked: [], n: 0, n_done: 0, n_blocked: 0 };
      toast(e.message, 'err', 8000);
    } finally {
      bulk.loading = false;
    }
    bulk.rev += 1;
    // What stays ticked is what can still be read.
    const can = new Set(bulkRows().map((r) => r.entry_id));
    for (const id of Object.keys(bulk.want)) {
      if (!can.has(id)) delete bulk.want[id];
    }
    if (!bulkRefresh() && bulk.on) render();
  }

  /* THROUGH THE NUDGE, AND THEN THE READ (2026-10-19). It called
     `pickSet`, which on a changed picture puts "Save as vN first?" up and
     returns -- and then read the set still open, the one being left, at
     `from_version` null. Everything now waits for the answer. */
  function openRead(entryId, o) {
    if (!entryId) return;
    const go = () => {
      bulk.on = false;
      pickSetNow(entryId);
      /* The batch reads each set as it stands (`from_version` null), so
         that is what is opened; anything else could be a read nobody has
         paid for yet, and "Open" would quietly start one. */
      q.from_version = null;
      bankAfterFit = !!(o && o.bank);
      BARRY.activity.log('rootcanal.open_from_batch', { entry: entryId });
      // The read is done, so this comes back cached and goes to a fit.
      startRead();
    };
    if (entryId !== q.entry && isDirty()) { nudgeThen(go); return; }
    go();
  }

  /* What is ticked, in the list's order, and nothing else (2026-10-19: it
     read `bulk.pick`, where an untouched row counted as ticked). Until the
     server lists the members, the card shows the ones sent as waiting. */
  async function runBulk() {
    if (bulk.sending || bulk.job) return;
    const rows = bulkRows().filter((r) => bulk.want[r.entry_id]);
    if (!rows.length) { toast('Nothing is ticked.', 'warn', 5000); return; }
    bulk.sending = true;
    bulk.stopping = false;
    bulk.last = null;
    bulk.sent = rows.map((r) => ({ id: r.entry_id, label: r.label }));
    bulkRefresh();
    try {
      const got = await apiPost('/api/rootcanal/batch',
                                { entries: rows.map((r) => r.entry_id) });
      bulk.job = got.job;
      watchBulk();
    } catch (e) {
      bulk.sent = null;
      toast(e.message, 'err', 10000);
    } finally {
      bulk.sending = false;
    }
    if (!bulkRefresh() && bulk.on) render();
  }

  function stopBulk() {
    const j = bulk.job;
    if (!j || bulk.stopping) return;
    bulk.stopping = true;
    bulkRefresh();
    apiPost('/api/cfc/job/' + j.id + '/cancel', {}).catch((e) => {
      bulk.stopping = false;
      toast('It could not be stopped: ' + e.message, 'err', 8000);
      bulkRefresh();
    });
  }

  function watchBulk() {
    if (bulk.poll) clearInterval(bulk.poll);
    bulk.poll = setInterval(async () => {
      if (!bulk.job) { clearInterval(bulk.poll); bulk.poll = null; return; }
      let got;
      try { got = await api('/api/cfc/job/' + bulk.job.id); }
      catch (e) { return; }
      bulk.job = got.job || bulk.job;
      if (bulk.job.status === 'running') {
        /* WHICHEVER MODE YOU ARE IN. Opening a finished set switches to one
           at a time, and a poll that only refreshed the batch card then
           froze the count -- which reads exactly like the batch stopping.
           X-ray's lesson. The card is reconciled in place (2026-10-19): it
           was built again from nothing on every poll. */
        if (!bulkRefresh()) swap('.rc-mode', modeSwitch());
        return;
      }
      clearInterval(bulk.poll);
      bulk.poll = null;
      endBulk(bulk.job);
    }, 900);
  }

  /* A batch over: said in a toast and, with what failed and why, on the
     picker's first line until the next batch. What landed is unticked --
     it is under "Already read" now -- and what failed stays ticked, so
     "Read the N ticked" sends it again. */
  function endBulk(done) {
    const ms = (done && done.members) || [];
    bulk.job = null;
    bulk.sent = null;
    bulk.stopping = false;
    for (const m of ms) if (m.status === 'done') delete bulk.want[m.id];
    const n = ms.filter((m) => m.status === 'done').length;
    const quit = done && done.status === 'canceled';
    bulk.last = { n, of: ms.length, quit,
                  failed: ms.filter((m) => m.status === 'error')
                    .map((m) => ({ label: m.label || m.id, why: m.error })) };
    toast(quit
      ? 'Stopped. ' + n + ' of ' + ms.length + ' were read and are kept; '
        + 'the rest were not started.'
      : 'Read ' + n + ' of ' + ms.length + '. Nothing was banked.',
      quit ? 'warn' : 'ok', 8000);
    bulk.plan = null;
    if (bulk.on) { bulkRefresh(); loadBulk(); } else swap('.rc-mode', modeSwitch());
  }

  /* ==================================================================
     Drawing
     ================================================================== */
  function tok(n) { return BARRY.token(n); }

  function ink() {
    return {
      text: tok('--text'), dim: tok('--text-3'), mid: tok('--text-2'),
      line: tok('--line'), soft: tok('--line-soft'), bg: tok('--bg'),
      bg2: tok('--bg-2'), accent: tok('--accent'), warn: tok('--warn'),
      /* Meaning, not looks: a dentate spike is what the set keeps, an IED
         is what comes out of it. The semantic tokens say exactly that in
         every theme. */
      ds: tok('--ok'), ied: tok('--err'),
    };
  }

  function colOf(cls) {
    return cls === 'ied' ? tok('--err') : cls === 'ds' ? tok('--ok')
                                                        : tok('--text-3');
  }

  /* OUTSIDE THE BORDER, BUT STILL SOMETHING (2026-10-19). With a border
     applied, every event it left ambiguous was drawn the same grey, so
     what they had been called was lost exactly where it was most worth
     seeing. Now an ambiguous dot keeps its own call's colour, faded halfway
     to the grey, and wears a dotted grey edge (`outside` in the scene):
     clearly not solid, and still DS-ish or IED-ish at a glance. */
  function outsideCol(cls) {
    if (cls !== 'ds' && cls !== 'ied') return tok('--text-3');
    const a = rgbOf(colOf(cls)), b = rgbOf(tok('--text-3'));
    return 'rgb(' + [0, 1, 2].map((j) => Math.round(a[j] * 0.55 + b[j] * 0.45))
      .join(',') + ')';
  }

  /* The colour a border gives an event: solid DS or IED in full, and an
     ambiguous one its own call, faded. */
  function borderCol(e, own) {
    return e.border === 'amb' ? outsideCol(own) : colOf(e.border);
  }

  /* A colour as three numbers, for the CSD's interpolation. Through a
     canvas rather than a parser, so a token written as a name, a hex or an
     rgb() all come out the same. */
  const RGB = {};
  function rgbOf(col) {
    if (RGB[col]) return RGB[col];
    const g = document.createElement('canvas').getContext('2d');
    g.fillStyle = col;
    const s = String(g.fillStyle);
    let out;
    if (s[0] === '#') {
      out = [1, 3, 5].map((j) => parseInt(s.slice(j, j + 2), 16));
    } else {
      out = (s.match(/[\d.]+/g) || ['128', '128', '128']).slice(0, 3)
        .map(Number);
    }
    RGB[col] = out;
    return out;
  }

  /* A canvas with a backing store that matches the box it is drawn in --
     X-ray's `sized`, for the reasons written over it there: a flexed canvas
     drawn at the height it was ASKED for and shown at the height it GOT is
     a blurry one, and the border is not part of the content box. */
  function sized(id, h, fill) {
    const cv = document.getElementById(id);
    if (!cv) return null;
    if (!fill) cv.style.height = h + 'px';
    const got = cv.clientHeight;
    if (got > 60) h = got;
    else if (fill) { cv.style.height = h + 'px'; h = cv.clientHeight || h; }
    const w = cv.clientWidth || 320;
    const dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    return { cv, g, w, h };
  }

  const FONT = (px, bold) => (bold ? '600 ' : '') + px
    + 'px ui-sans-serif, system-ui, sans-serif';

  /* Text that is never cut. Shrunk until it fits, down to 7px; past that
     it is broken onto two lines at the middle-most space. An axis label
     with its end missing is worse than a small one -- and "dB re baseline"
     is exactly the half that would go. */
  function fitText(g, text, room, px, bold) {
    let pt = px || 10;
    g.font = FONT(pt, bold);
    while (pt > 7 && g.measureText(text).width > room) {
      pt -= 0.5;
      g.font = FONT(pt, bold);
    }
    if (g.measureText(text).width <= room) return { lines: [text], pt };
    const mid = text.length / 2;
    let best = -1;
    for (let j = 0; j < text.length; j++) {
      if (text[j] === ' ' && (best < 0 || Math.abs(j - mid) < Math.abs(best - mid))) {
        best = j;
      }
    }
    if (best < 0) return { lines: [text], pt };
    return { lines: [text.slice(0, best), text.slice(best + 1)], pt };
  }

  function drawLines(g, fitted, x, y, lh) {
    fitted.lines.forEach((ln, j) => g.fillText(ln, x, y + j * (lh || fitted.pt + 2)));
  }

  function axisLabel(a, p) {
    /* The amplitude is measured on the filtered trace, so it says which
       filter -- the same number under another filter is another number. */
    if (a === 0) {
      const src = viewMode === 'pooled' ? poolShownParams()
        : (p && p.filt ? p : shownParams());
      return 'max amplitude on ' + filterWords(src, true) + ' · µV';
    }
    if (a === 1) return 'half-width · ms';
    return hfLabel(p);
  }

  /* Ticks at round numbers. */
  function ticks(lo, hi, n) {
    const span = hi - lo;
    if (!(span > 0)) return [lo];
    const raw = span / Math.max(1, n || 4);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const st = [1, 2, 2.5, 5, 10].map((m) => m * mag)
      .find((s) => span / s <= (n || 4) + 0.5) || mag * 10;
    const out = [];
    for (let v = Math.ceil(lo / st) * st; v <= hi + st * 1e-9; v += st) {
      out.push(Math.abs(v) < st * 1e-9 ? 0 : v);
    }
    return out;
  }

  const tickText = (v) => {
    const a = Math.abs(v);
    if (a >= 1000) return (v / 1000).toFixed(a >= 10000 ? 0 : 1) + 'k';
    if (a >= 10 || a === 0) return String(Math.round(v));
    return String(Math.round(v * 10) / 10);
  };

  const GEOM = { space: null, flats: {}, ev: {} };

  /* ==================================================================
     THE SCENE: what the one drawing path draws.

     Single and Pooled show the same space and the same three flat views,
     and they are drawn by the same functions -- `drawSpace`, `drawFlat`,
     `drawMark`, the picking and the stepping. What differs is handed in
     here: the events, the centres, the colour each dot takes, how bright
     it is, whether it is ringed, what a click does. Two copies of a
     renderer is how two views of one thing stop agreeing (constitution
     §6c), so there is one, and each view says what it wants of it.

     Single's scene is its fit as it always was: coloured by class, ringed
     where a class was set by hand, a centre draggable. Pooled's is built in
     `poolScene`, below.
     ================================================================== */
  function scene() {
    if (viewMode === 'pooled') return poolScene();
    if (!fit || !fit.ok) return null;
    return {
      kind: 'single',
      events: fit.events || [],
      centres: centresShown(),
      fitCentres: fit.centres || [],
      params: shownParams(),
      picked,
      /* With a border on, the call shown is the border's: solid DS,
         solid IED, or ambiguous (grey, and filled -- not hollow, which is
         "not measured"). */
      fill: (e) => (fit.border_used ? borderCol(e, e.cls) : colOf(e.cls)),
      outside: (e) => !!fit.border_used && e.border === 'amb',
      shape: () => null,
      centreFill: (c) => cluFill(c.k, c.cls),
      alpha: () => 1,
      ringed: (e) => !!e.flipped,
      draggable: true,
      onPick: setPicked,
    };
  }

  function drawAll() {
    drawMain();
    drawEvent();
    if (viewMode === 'pooled') drawPoolHists();
    watchSize();
  }

  function drawMain() {
    if (!scene()) return;
    // Fixed heights first, then the one that stretches to meet them.
    for (const [id, xa, ya] of FLATS) drawFlat(id, xa, ya);
    drawSpace();
    if (mismatched()) {
      for (const [id, xa, ya] of FLATS) drawFlat(id, xa, ya);
      drawSpace();
    }
  }

  /* ---------- the space ----------

     Orthographic. Amplitude across, POWER UP (it is the axis the naming
     rule reads), half-width into the screen. Yaw turns about the vertical,
     pitch tips it towards you; depth is what comes out of the screen, and
     larger is nearer. */
  function project(p) {
    const X = p[0], Y = p[2], Z = p[1];
    const cy = Math.cos(view.yaw), sy = Math.sin(view.yaw);
    const x1 = X * cy + Z * sy, z1 = -X * sy + Z * cy;
    const cp = Math.cos(view.pitch), sp = Math.sin(view.pitch);
    const y2 = Y * cp - z1 * sp, z2 = Y * sp + z1 * cp;
    return [x1, y2, z2];
  }

  /* Where an event sits in z-space, including one that was not measured.

     NOT MEASURED IS NOT ZERO. An axis with no value is put on the floor of
     that axis -- the far end, well away from the mean -- and the dot is
     drawn hollow, so it is visible, pickable and obviously not a
     measurement. Placing it at z = 0 would put it in the middle of the
     cloud looking exactly like an average event. */
  function zOf(e, floor) {
    const ok = (v) => v != null && isFinite(v);
    if (e.z && e.z.length === 3 && e.z.every(ok)) {
      return { z: e.z.slice(), hollow: false, partial: false };
    }
    /* PLACED ON TWO AXES: the server's own z for those two, and the floor
       for the one it does not have -- the same place a hollow one goes, so
       "has no position here" looks the same wherever it happens. */
    if (e.z && e.z.length === 3 && e.cls != null) {
      return { z: e.z.map((v) => (ok(v) ? v : -floor)), hollow: false,
               partial: true };
    }
    const z = [0, 1, 2].map((a) => {
      const r = e[KEYS[a]];
      return (r != null && isFinite(r)) ? rawToZ(a, r) : -floor;
    });
    return { z, hollow: true, partial: false };
  }

  /* ONE MARK PER EVENT, the same four ways in every view.

       filled dot      measured on all three axes
       filled square   placed on two of the three (`partial`)
       dashed outline  its half-width was only found with the search widened
                       past v1's 50 ms (`wide`)
       hollow dot      not placed at all
       solid ring      its class was set by hand

     A shape for partial, not a colour: the colour already says DS or IED,
     and a third colour would read as a third class. The wide outline is
     dashed so it can never be mistaken for the hand-flip's solid ring. */
  function markOf(e, hollow) {
    if (hollow || e.cls == null) return 'hollow';
    return e.partial ? 'square' : 'dot';
  }

  /* `S` is the scene: it says the colour, the shape a categorical colour
     falls back to once the palette has run out, and whether the dot is
     ringed. Square (two of three axes), hollow (not placed) and the wide
     outline mean the same thing in every scene and every colour mode. */
  function drawMark(g, k, x, y, r, e, kind, alpha, S) {
    const sc = S || scene();
    const fill = sc ? sc.fill(e) : colOf(e.cls);
    const alt = kind === 'dot' && sc ? sc.shape(e) : null;
    g.globalAlpha = alpha == null ? 1 : alpha;
    if (kind === 'hollow') {
      g.beginPath();
      g.arc(x, y, r, 0, 6.2832);
      g.strokeStyle = e.cls ? fill : k.dim;
      g.lineWidth = 1.2;
      g.stroke();
    } else if (kind === 'square') {
      const s2 = r * 0.95;
      g.fillStyle = fill;
      g.fillRect(x - s2, y - s2, 2 * s2, 2 * s2);
      g.strokeStyle = k.text;
      g.lineWidth = 1;
      g.strokeRect(x - s2, y - s2, 2 * s2, 2 * s2);
    } else if (alt === 'tri' || alt === 'itri') {
      const up = alt === 'tri' ? 1 : -1, t2 = r * 1.25;
      g.beginPath();
      g.moveTo(x, y - up * t2);
      g.lineTo(x + t2 * 0.9, y + up * t2 * 0.7);
      g.lineTo(x - t2 * 0.9, y + up * t2 * 0.7);
      g.closePath();
      g.fillStyle = fill;
      g.fill();
      g.strokeStyle = k.bg;
      g.lineWidth = 0.7;
      g.stroke();
    } else {
      g.beginPath();
      g.arc(x, y, r, 0, 6.2832);
      g.fillStyle = fill;
      g.fill();
      if (sc && sc.outside && sc.outside(e)) {
        // Outside the border: a dotted grey edge round its faded colour.
        g.strokeStyle = k.dim;
        g.lineWidth = 1;
        g.setLineDash([1.4, 1.4]);
        g.stroke();
        g.setLineDash([]);
      } else {
        g.strokeStyle = k.bg;
        g.lineWidth = 0.7;
        g.stroke();
      }
    }
    if (e.wide) {
      g.beginPath();
      g.arc(x, y, r + 2, 0, 6.2832);
      g.strokeStyle = k.text;
      g.lineWidth = 1.1;
      g.setLineDash([2, 1.6]);
      g.stroke();
      g.setLineDash([]);
    }
    if (sc ? sc.ringed(e) : e.flipped) {
      g.beginPath();
      g.arc(x, y, r + (e.wide ? 4.4 : 2.6), 0, 6.2832);
      g.strokeStyle = k.warn;
      g.lineWidth = 1.2;
      g.stroke();
    }
    g.globalAlpha = 1;
  }

  function drawSpace() {
    const s = sized('rcSpace', 380, true);
    const S = scene();
    if (!s || !S) return;
    const k = ink();
    const g = s.g;
    const evs = S.events;
    const cs = S.centres;
    const p = S.params;

    // The extent is a SPHERE, so turning the view never rescales it.
    let R = 2.2;
    for (const e of evs) {
      if (!e.z) continue;
      const r = Math.hypot(e.z[0] || 0, e.z[1] || 0, e.z[2] || 0);
      if (isFinite(r)) R = Math.max(R, r);
    }
    for (const c of cs) {
      const r = Math.hypot(c.z[0] || 0, c.z[1] || 0, c.z[2] || 0);
      if (isFinite(r)) R = Math.max(R, r);
    }
    const floor = R * 0.9;
    const L = R * 1.02;
    const cx = s.w / 2, cy = s.h / 2;
    const scale = view.zoom * (Math.min(s.w, s.h) / 2 - 34) / L;
    const toScreen = (z3) => {
      const r = project(z3);
      return { x: cx + scale * r[0], y: cy - scale * r[1], d: r[2] };
    };

    /* The axes, through the mean. The half behind zero is dashed and faint;
       the half in front is solid, with a tick at every whole SD. */
    const axes = [];
    for (let a = 0; a < 3; a++) {
      const lo = [0, 0, 0], hi = [0, 0, 0];
      lo[a] = -L; hi[a] = L;
      const A = toScreen(lo), B = toScreen(hi), O = toScreen([0, 0, 0]);
      g.strokeStyle = k.dim;
      g.lineWidth = 1;
      g.globalAlpha = 0.5;
      g.setLineDash([3, 4]);
      g.beginPath(); g.moveTo(A.x, A.y); g.lineTo(O.x, O.y); g.stroke();
      g.setLineDash([]);
      g.globalAlpha = 0.9;
      g.beginPath(); g.moveTo(O.x, O.y); g.lineTo(B.x, B.y); g.stroke();
      for (let t = -Math.floor(L); t <= Math.floor(L); t++) {
        if (!t) continue;
        const z3 = [0, 0, 0]; z3[a] = t;
        const P = toScreen(z3);
        g.beginPath(); g.arc(P.x, P.y, 1.3, 0, 6.2832);
        g.fillStyle = k.dim; g.fill();
      }
      g.globalAlpha = 1;
      axes.push({ a, x0: A.x, y0: A.y, x1: B.x, y1: B.y });
    }

    borderOutline3d(g, k, S, toScreen, L);

    // Everything that has a depth, sorted far to near.
    const items = [];
    const pts = [];
    for (const e of evs) {
      const zz = zOf(e, floor);
      const P = toScreen(zz.z);
      const mk = markOf(e, zz.hollow);
      const al = S.alpha(e);
      items.push({ d: P.d, kind: 'e', e, P, hollow: zz.hollow, mk, al });
      pts.push({ i: e.i, x: P.x, y: P.y, depth: P.d, hollow: zz.hollow,
                 r: 3.4, mark: mk, wide: !!e.wide, alpha: al,
                 fill: S.fill(e), shape: S.shape(e), ringed: S.ringed(e),
                 outside: !!(S.outside && S.outside(e)) });
    }
    const cpts = [];
    for (const c of cs) {
      const P = toScreen(c.z);
      items.push({ d: P.d, kind: 'c', c, P });
      cpts.push({ k: c.k, x: P.x, y: P.y, depth: P.d, cls: c.cls });
    }
    items.sort((a, b) => a.d - b.d);
    const dlo = items.length ? items[0].d : 0;
    const dhi = items.length ? items[items.length - 1].d : 1;
    const shade = (d) => (dhi > dlo ? (d - dlo) / (dhi - dlo) : 1);

    const taken = [];
    const cLabels = {};
    for (const it of items) {
      if (it.kind === 'e') {
        const e = it.e;
        const near = shade(it.d);
        const r = 2.6 + 1.4 * near;
        drawMark(g, k, it.P.x, it.P.y, r, e, it.mk,
                 (0.45 + 0.55 * near) * it.al, S);
      } else {
        cLabels[it.c.k] = drawCentre(g, k, it.c, it.P.x, it.P.y, S, taken);
      }
    }
    for (const cp of cpts) {
      if (cLabels[cp.k]) { cp.label = cLabels[cp.k]; cp.fill = cLabels[cp.k].fill; }
    }

    // The picked one, on top of everything, in all four views.
    let pickedAt = null;
    if (S.picked != null) {
      const pp = pts.find((x) => x.i === S.picked);
      if (pp) {
        ring(g, k, pp.x, pp.y);
        pickedAt = { x: pp.x, y: pp.y };
      }
    }

    // The axis names, last, where they can be read.
    const labels = [];
    for (const ax of axes) {
      const text = axisLabel(ax.a, p) + ', z';
      const dx = ax.x1 - cx, dy = ax.y1 - cy;
      const room = Math.max(80, dx >= 0 ? s.w - ax.x1 - 6 : ax.x1 - 6);
      const f = fitText(g, text, Math.min(room, s.w * 0.6), 10);
      const w = Math.max.apply(null, f.lines.map((ln) => g.measureText(ln).width));
      let x = dx >= 0 ? ax.x1 + 4 : ax.x1 - 4 - w;
      let y = ax.y1 + (dy >= 0 ? 12 : -4) - (f.lines.length - 1) * (f.pt + 2);
      x = Math.max(2, Math.min(s.w - 2 - w, x));
      y = Math.max(f.pt + 1, Math.min(s.h - 3 - (f.lines.length - 1) * (f.pt + 2), y));
      // Two labels in one place get pushed apart rather than overprinted.
      for (let n = 0; n < 4 && labels.some((l) => Math.abs(l.y - y) < f.pt + 3
             && x < l.x + l.w && l.x < x + w); n++) y += f.pt + 3;
      g.fillStyle = k.mid;
      drawLines(g, f, x, y);
      labels.push({ a: ax.a, text, x, y, w, lines: f.lines });
    }

    /* The lasso being drawn, and the dots already drawn round. */
    const selIds = new Set(lassoIds());
    if (selIds.size) {
      g.save();
      g.strokeStyle = k.accent;
      g.lineWidth = 1.4;
      for (const pt of pts) {
        if (!selIds.has(pt.i)) continue;
        g.beginPath(); g.arc(pt.x, pt.y, 5.5, 0, 6.2832); g.stroke();
      }
      g.restore();
    }
    if (lasso && lasso.length > 1) {
      g.save();
      g.strokeStyle = k.accent;
      g.lineWidth = 1.5;
      g.setLineDash([4, 3]);
      g.beginPath();
      g.moveTo(lasso[0][0], lasso[0][1]);
      for (const [lx, ly] of lasso.slice(1)) g.lineTo(lx, ly);
      g.stroke();
      g.restore();
    }
    GEOM.space = { w: s.w, h: s.h, cx, cy, scale, R, L, selected: selIds.size,
                   view: Object.assign({}, view), pts, centres: cpts,
                   axes: axes.map((ax, j) => Object.assign({}, ax,
                                                           { label: labels[j] })),
                   picked: pickedAt };
  }

  /* Where a centre's label goes: to its right, else left, above or below,
     whichever does not land on a label already drawn on this canvas. At
     k = 6 four "DS centre" labels used to pile on one another. */
  function placeLabel(g, text, x, y, taken) {
    const w = g.measureText(text).width, h = 11;
    const tries = [[x + 10, y + 3], [x - 10 - w, y + 3], [x - w / 2, y - 11],
                   [x - w / 2, y + 18]];
    const hit = (a, b) => !(a.x + a.w < b.x || b.x + b.w < a.x
                            || a.y < b.y - b.h || b.y < a.y - a.h);
    for (const [lx, ly] of tries) {
      const r = { x: lx, y: ly, w, h };
      if (!(taken || []).some((t) => hit(r, t))) {
        if (taken) taken.push(r);
        return r;
      }
    }
    const r = { x: tries[0][0], y: tries[0][1], w, h };
    if (taken) taken.push(r);
    return r;
  }

  function drawCentre(g, k, c, x, y, S, taken) {
    const col = S && S.centreFill ? S.centreFill(c) : colOf(c.cls);
    g.save();
    g.beginPath();
    g.moveTo(x, y - 8); g.lineTo(x + 8, y); g.lineTo(x, y + 8); g.lineTo(x - 8, y);
    g.closePath();
    g.fillStyle = col;
    g.globalAlpha = c.moving ? 0.6 : 0.95;
    g.fill();
    g.globalAlpha = 1;
    g.strokeStyle = k.text;
    g.lineWidth = 1.4;
    if (c.moving) g.setLineDash([3, 2]);
    g.stroke();
    g.setLineDash([]);
    g.fillStyle = k.text;
    g.font = FONT(9.5, true);
    // Numbered as the chips are: "#3 IED" is the third cluster by HF power.
    const text = '#' + ((c.k || 0) + 1) + ' ' + (c.cls === 'ied' ? 'IED' : 'DS');
    const at = placeLabel(g, text, x, y, taken);
    g.fillText(text, at.x, at.y);
    g.restore();
    return { text, x: at.x, y: at.y, w: at.w, fill: col };
  }

  function ring(g, k, x, y) {
    g.save();
    g.beginPath();
    g.arc(x, y, 8.5, 0, 6.2832);
    g.strokeStyle = k.bg;
    g.lineWidth = 4;
    g.stroke();
    g.strokeStyle = k.accent;
    g.lineWidth = 2;
    g.stroke();
    g.restore();
  }

  /* SCREEN-SPACE PICKING, the front dot winning.

     A dot is picked where it is DRAWN. Any dot actually under the pointer
     -- within its own radius -- beats every dot that is merely near it, and
     among those the nearest to the viewer wins, because it is the one
     painted on top and therefore the one being pointed at. Only when
     nothing is under the pointer does "nearest within 6 px" apply, and a
     tie there goes to the front too. */
  function pickSpace(x, y) {
    const G = GEOM.space;
    if (!G) return null;
    let under = null, near = null, nd = 36;
    for (const p of G.pts) {
      const d2 = (p.x - x) * (p.x - x) + (p.y - y) * (p.y - y);
      if (d2 <= (p.r + 1.5) * (p.r + 1.5)) {
        if (!under || p.depth > under.depth) under = p;
      }
      if (d2 < nd || (near && d2 === nd && p.depth > near.depth)) {
        nd = d2; near = p;
      }
    }
    const hit = under || near;
    return hit ? hit.i : null;
  }

  /* ---------- the flat views ----------

     Raw units: µV, ms, dB. Clicking is exact here -- there is no depth to
     be wrong about -- and a centre can be taken hold of and moved. */
  const FPAD = { l: 44, r: 10, t: 8, b: 34 };

  function flatRange(a, extra) {
    let lo = Infinity, hi = -Infinity;
    const S = scene();
    for (const e of ((S && S.events) || [])) {
      const v = e[KEYS[a]];
      if (v == null || !isFinite(v)) continue;
      lo = Math.min(lo, v); hi = Math.max(hi, v);
    }
    for (const v of (extra || [])) {
      if (v == null || !isFinite(v)) continue;
      lo = Math.min(lo, v); hi = Math.max(hi, v);
    }
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    if (!(hi > lo)) { hi = lo + 1; }
    const pad = (hi - lo) * 0.06;
    return [lo - pad, hi + pad];
  }

  function drawFlat(id, xa, ya) {
    const s = sized(id, 180);
    const S = scene();
    if (!s || !S) return;
    const k = ink();
    const g = s.g;
    const p = S.params;
    const cs = S.centres;
    /* The range is the fit's, not the drag's. A centre dragged to the edge
       would otherwise stretch the axes under the pointer as it went, and
       the drop would land somewhere other than where it was let go. */
    const fcs = S.fitCentres || [];
    const xr = flatRange(xa, fcs.map((c) => (c.raw || [])[xa]));
    const yr = flatRange(ya, fcs.map((c) => (c.raw || [])[ya]));
    const x0 = FPAD.l, x1 = s.w - FPAD.r, y0 = FPAD.t, y1 = s.h - FPAD.b;
    const X = (v) => x0 + ((v - xr[0]) / (xr[1] - xr[0])) * (x1 - x0);
    const Y = (v) => y1 - ((v - yr[0]) / (yr[1] - yr[0])) * (y1 - y0);

    g.strokeStyle = k.line;
    g.lineWidth = 1;
    g.strokeRect(x0, y0, x1 - x0, y1 - y0);
    g.fillStyle = k.dim;
    g.font = FONT(9);
    g.textAlign = 'center';
    for (const t of ticks(xr[0], xr[1], Math.max(2, Math.floor((x1 - x0) / 60)))) {
      const x = X(t);
      g.fillRect(x, y1, 1, 3);
      g.fillText(tickText(t), x, y1 + 12);
    }
    g.textAlign = 'right';
    for (const t of ticks(yr[0], yr[1], Math.max(2, Math.floor((y1 - y0) / 34)))) {
      const y = Y(t);
      g.fillRect(x0 - 3, y, 3, 1);
      g.fillText(tickText(t), x0 - 5, y + 3);
    }
    g.textAlign = 'left';
    // A zero line on the power axis: below it the band was quieter than
    // the event's own baseline, which is a different claim from "less".
    if (ya === 2 && yr[0] < 0 && yr[1] > 0) {
      g.strokeStyle = k.dim;
      g.globalAlpha = 0.6;
      g.setLineDash([2, 3]);
      g.beginPath(); g.moveTo(x0, Y(0)); g.lineTo(x1, Y(0)); g.stroke();
      g.setLineDash([]);
      g.globalAlpha = 1;
    }

    borderOverlay(id, g, k, S, xa, ya, X, Y, { x0, y0, x1, y1 });
    // The dots. Not measured on either axis of THIS view: on that edge,
    // hollow, so it is counted rather than lost.
    const pts = [];
    let unm = 0;
    g.save();
    g.beginPath(); g.rect(x0, y0, x1 - x0, y1 - y0); g.clip();
    for (const e of S.events) {
      const vx = e[KEYS[xa]], vy = e[KEYS[ya]];
      const hx = vx != null && isFinite(vx), hy = vy != null && isFinite(vy);
      const x = hx ? X(vx) : x0 + 3;
      const y = hy ? Y(vy) : y1 - 3;
      /* On the edge when this view's axis is the one it lacks, exactly as a
         hollow one is -- but drawn as the square it is everywhere else, so
         a partial event reads the same in all four views. */
      const hollow = e.cls == null;
      const mk = markOf(e, hollow);
      if (!hx || !hy) unm += 1;
      const al = S.alpha(e);
      drawMark(g, k, x, y, 3.2, e, mk, (hollow ? 1 : 0.9) * al, S);
      pts.push({ i: e.i, x, y, hollow, mark: mk, wide: !!e.wide,
                 edge: !hx || !hy, alpha: al, fill: S.fill(e),
                 ringed: S.ringed(e), outside: !!(S.outside && S.outside(e)) });
    }
    // The dots drawn round in the 3D view, ringed here too.
    const selF = new Set(lassoIds());
    if (selF.size) {
      g.strokeStyle = ink().accent;
      g.lineWidth = 1.3;
      for (const pt of pts) {
        if (!selF.has(pt.i)) continue;
        g.beginPath(); g.arc(pt.x, pt.y, 5, 0, 6.2832); g.stroke();
      }
    }
    g.restore();
    const cpts = [];
    const takenF = [];
    for (const c of cs) {
      const vx = (c.raw || [])[xa], vy = (c.raw || [])[ya];
      if (vx == null || vy == null || !isFinite(vx) || !isFinite(vy)) continue;
      const x = Math.max(x0, Math.min(x1, X(vx)));
      const y = Math.max(y0, Math.min(y1, Y(vy)));
      const lab = drawCentre(g, k, c, x, y, S, takenF);
      cpts.push({ k: c.k, x, y, cls: c.cls, label: lab, fill: lab.fill });
    }
    let pickedAt = null;
    if (S.picked != null) {
      const pp = pts.find((x) => x.i === S.picked);
      if (pp) { ring(g, k, pp.x, pp.y); pickedAt = { x: pp.x, y: pp.y }; }
    }

    // Both axes named, in every state.
    const xl = axisLabel(xa, p), yl = axisLabel(ya, p);
    g.fillStyle = k.mid;
    const fx = fitText(g, xl, x1 - x0 - 4, 10);
    g.textAlign = 'center';
    drawLines(g, fx, (x0 + x1) / 2, s.h - 5 - (fx.lines.length - 1) * (fx.pt + 1),
              fx.pt + 1);
    g.textAlign = 'left';
    const fy = fitText(g, yl, y1 - y0 - 2, 10);
    g.save();
    g.translate(11 - (fy.lines.length - 1) * (fy.pt + 1) / 2 + 1, (y0 + y1) / 2);
    g.rotate(-Math.PI / 2);
    g.textAlign = 'center';
    drawLines(g, fy, 0, 0, fy.pt + 1);
    g.restore();
    g.textAlign = 'left';
    if (unm) {
      g.fillStyle = k.dim;
      g.font = FONT(8.5);
      g.fillText(unm + ' without a value here, on the edge', x0 + 4, y0 + 10);
    }

    GEOM.flats[id] = {
      id, xa, ya, w: s.w, h: s.h, xr, yr,
      box: { x0, y0, x1, y1 }, pts, centres: cpts, picked: pickedAt,
      labels: { x: xl, y: yl },
      toRaw: (x, y) => [xr[0] + ((x - x0) / (x1 - x0)) * (xr[1] - xr[0]),
                        yr[0] + ((y1 - y) / (y1 - y0)) * (yr[1] - yr[0])],
    };
  }

  /* THE APPLIED BORDER ON A FLAT VIEW (2026-10-19), drawn under the dots
     from one line in `drawFlat`. A border classifies by the same three
     numbers the flat views plot, so it can be shown where it cuts:
       - round one identity (an envelope), the box from lo to hi on both
         axes of the view, outlined in the accent colour, with a light wash
         over everything outside it -- outside is what it calls ambiguous;
       - between two, each axis's two cut-offs as dashed lines, where solid
         DS ends (in the DS colour) and where solid IED begins (in the IED
         colour), with the ambiguous band between them faint. A view shows
         two of the three axes, so a dot past both lines here can still be
         ambiguous by the third: the lines are where it cuts, not the call.
     Inside the plot's clip. Its label is drawn after the clip, in the
     corner with the fewest dots, so it is never cut off, and kept short --
     the Borders card names the border. What was drawn is kept in
     `GEOM.border[id]`, for the suites. */
  /* THE BORDER IN 3D (2026-10-19): "make a faint outline of where the
     borders are in the 3d graph". The flat views draw it; the cloud did
     not, so a border applied to a pool was colour alone there. Now its
     regions are outlined, faint and behind the dots:
       around one group (an envelope)  its box, in the accent colour;
       between DS and IED              the solid-DS region and the solid-IED
                                       region, each a box cut off at the
                                       axes' ends, dashed, in their colours.
     In the view's own z units, through the same raw-to-z line the dots
     use, so a box edge and a dot at that number land in one place.
     `GEOM.border3d` holds what was drawn, for the harness. */
  function borderOutline3d(g, k, S, toScreen, L) {
    GEOM.border3d = null;
    const bu = S.kind === 'pooled' ? pool.fit && pool.fit.border_used
                                   : fit && fit.border_used;
    const ed = bu && bu.edges;
    if (!ed) return;
    const ok = (v) => v != null && isFinite(v);
    const clamp = (z) => Math.max(-L, Math.min(L, z));
    const boxes = [];
    if (isEnv(bu)) {
      const r = [0, 1, 2].map((a) => {
        const e = ed[KEYS[a]] || {};
        return ok(e.lo) && ok(e.hi)
          ? [clamp(rawToZ(a, e.lo)), clamp(rawToZ(a, e.hi))] : null;
      });
      if (r.every(Boolean)) boxes.push({ cls: 'env', r, col: k.accent, dash: [] });
    } else {
      const up = bu.ied_above || {};
      const ied = [], ds = [];
      for (let a = 0; a < 3; a++) {
        const e = ed[KEYS[a]] || {};
        if (!ok(e.ied_at) || !ok(e.ds_at)) return;
        const zi = rawToZ(a, e.ied_at), zd = rawToZ(a, e.ds_at);
        const above = up[KEYS[a]] !== false;
        ied.push(above ? [clamp(zi), L] : [-L, clamp(zi)]);
        ds.push(above ? [-L, clamp(zd)] : [clamp(zd), L]);
      }
      const real = (r) => r.every(([a, b]) => b - a > 1e-6);
      if (real(ds)) boxes.push({ cls: 'ds', r: ds, col: colOf('ds'), dash: [4, 4] });
      if (real(ied)) boxes.push({ cls: 'ied', r: ied, col: colOf('ied'), dash: [4, 4] });
    }
    if (!boxes.length) return;
    g.save();
    g.lineWidth = 1;
    for (const bx of boxes) {
      const [xr, yr, zr] = bx.r;
      const corner = (i, j, l) => toScreen([xr[i], yr[j], zr[l]]);
      g.strokeStyle = bx.col;
      g.setLineDash(bx.dash);
      g.globalAlpha = 0.32;
      g.beginPath();
      for (let i = 0; i < 2; i++) {
        for (let j = 0; j < 2; j++) {
          for (let l = 0; l < 2; l++) {
            const P0 = corner(i, j, l);
            // The three edges leaving this corner towards the far side.
            if (!i) { const Q = corner(1, j, l); g.moveTo(P0.x, P0.y); g.lineTo(Q.x, Q.y); }
            if (!j) { const Q = corner(i, 1, l); g.moveTo(P0.x, P0.y); g.lineTo(Q.x, Q.y); }
            if (!l) { const Q = corner(i, j, 1); g.moveTo(P0.x, P0.y); g.lineTo(Q.x, Q.y); }
          }
        }
      }
      g.stroke();
    }
    g.restore();
    g.globalAlpha = 1;
    g.setLineDash([]);
    GEOM.border3d = { kind: isEnv(bu) ? 'envelope' : 'between',
                      boxes: boxes.map((b) => ({ cls: b.cls, r: b.r })) };
  }

  function borderOverlay(id, g, k, S, xa, ya, X, Y, bx) {
    const all = GEOM.border || (GEOM.border = {});
    delete all[id];
    const bu = S.kind === 'pooled' ? pool.fit && pool.fit.border_used
                                   : fit && fit.border_used;
    const ed = bu && bu.edges;
    const ex = ed && ed[KEYS[xa]], ey = ed && ed[KEYS[ya]];
    if (!ex || !ey) return;
    const ok = (v) => v != null && isFinite(v);
    const env = isEnv(bu);
    const w = bx.x1 - bx.x0, h = bx.y1 - bx.y0;
    const out = { kind: env ? 'envelope' : 'between', grace: bu.grace };
    g.save();
    g.beginPath(); g.rect(bx.x0, bx.y0, w, h); g.clip();
    if (env) {
      if (![ex.lo, ex.hi, ey.lo, ey.hi].every(ok)) { g.restore(); return; }
      const L = X(ex.lo), R = X(ex.hi), T = Y(ey.hi), B = Y(ey.lo);
      g.fillStyle = k.accent;
      g.globalAlpha = 0.08;
      g.beginPath();
      g.rect(bx.x0, bx.y0, w, h);
      g.rect(L, T, R - L, B - T);
      g.fill('evenodd');
      g.globalAlpha = 0.95;
      g.strokeStyle = k.accent;
      g.lineWidth = 1.5;
      g.strokeRect(L, T, R - L, B - T);
      out.rect = { x0: L, y0: T, x1: R, y1: B };
    } else {
      out.lines = [];
      for (const [axis, e, P, key] of [['x', ex, X, KEYS[xa]],
                                       ['y', ey, Y, KEYS[ya]]]) {
        if (!ok(e.ied_at) || !ok(e.ds_at)) continue;
        const a = P(e.ied_at), d = P(e.ds_at);
        g.globalAlpha = 0.1;
        g.fillStyle = k.accent;
        if (axis === 'x') g.fillRect(Math.min(a, d), bx.y0, Math.abs(a - d), h);
        else g.fillRect(bx.x0, Math.min(a, d), w, Math.abs(a - d));
        g.globalAlpha = 0.95;
        g.lineWidth = 1.4;
        g.setLineDash([5, 4]);
        for (const [v, col] of [[a, k.ied], [d, k.ds]]) {
          g.strokeStyle = col;
          g.beginPath();
          if (axis === 'x') { g.moveTo(v, bx.y0); g.lineTo(v, bx.y1); }
          else { g.moveTo(bx.x0, v); g.lineTo(bx.x1, v); }
          g.stroke();
        }
        g.setLineDash([]);
        out.lines.push({ axis, key, ied: a, ds: d });
      }
      if (!out.lines.length) { g.restore(); return; }
    }
    g.restore();
    /* The label: in the emptiest corner, and never over the line that
       says how many dots sit on the edge without a value (top left). */
    const gw = bu.grace_words || graceWords(bu.grace);
    const text = env ? bGroup(bu) + ' envelope · grace ' + gw
                     : 'DS / IED border · grace ' + gw;
    g.save();
    const ft = fitText(g, text, Math.max(40, w - 12), 9, true);
    const lh = ft.pt + 2;
    const lw = Math.ceil(Math.max(...ft.lines.map((ln) => g.measureText(ln)
                                                          .width))) + 8;
    const lhh = ft.lines.length * lh + 4;
    const edge = S.events.some((e) => !ok(e[KEYS[xa]]) || !ok(e[KEYS[ya]]));
    const spots = [[bx.x1 - 3 - lw, bx.y0 + 3], [bx.x1 - 3 - lw, bx.y1 - 3 - lhh],
                   [bx.x0 + 3, bx.y1 - 3 - lhh]]
      .concat(edge ? [] : [[bx.x0 + 3, bx.y0 + 3]]);
    let best = spots[0], bn = Infinity;
    for (const [sx, sy] of spots) {
      let n = 0;
      for (const e of S.events) {
        const vx = e[KEYS[xa]], vy = e[KEYS[ya]];
        if (!ok(vx) || !ok(vy)) continue;
        const px = X(vx), py = Y(vy);
        if (px >= sx - 3 && px <= sx + lw + 3 && py >= sy - 3
            && py <= sy + lhh + 3) n += 1;
      }
      if (n < bn) { bn = n; best = [sx, sy]; }
    }
    const [lx, ly] = best;
    g.globalAlpha = 0.9;
    g.fillStyle = k.bg;
    g.fillRect(lx, ly, lw, lhh);
    g.globalAlpha = 1;
    g.strokeStyle = k.accent;
    g.lineWidth = 1;
    g.strokeRect(lx + 0.5, ly + 0.5, lw - 1, lhh - 1);
    g.fillStyle = k.text;
    g.textAlign = 'left';
    drawLines(g, ft, lx + 4, ly + 2 + ft.pt, lh);
    g.restore();
    out.label = { text, lines: ft.lines, x: lx, y: ly, w: lw, h: lhh, dots: bn };
    all[id] = out;
  }

  function pickFlat(id, x, y) {
    const G = GEOM.flats[id];
    if (!G) return null;
    let best = null, bd = 36;
    for (const p of G.pts) {
      const d2 = (p.x - x) * (p.x - x) + (p.y - y) * (p.y - y);
      if (d2 < bd) { bd = d2; best = p; }
    }
    return best ? best.i : null;
  }

  function centreAt(id, x, y) {
    const G = GEOM.flats[id];
    if (!G) return null;
    let best = null, bd = 11 * 11;
    for (const c of G.centres) {
      const d2 = (c.x - x) * (c.x - x) + (c.y - y) * (c.y - y);
      if (d2 < bd) { bd = d2; best = c; }
    }
    return best;
  }

  /* ---------- the event ---------- */
  const EPAD = { l: 42, r: 8, t: 10, b: 30 };

  function drawEvent() {
    const A = curAvg();
    if (A) {
      const d = A.data && A.data.ok !== false && !A.busy ? A.data : null;
      const dd = d || (A.err ? { ok: false, error: A.err } : null);
      // A stand-in for "the picked event": the average's own contact, and
      // nothing missing -- it is one mean trace, measured as one.
      const pe = { contact: d ? d.trace.contact : null, missing: [],
                   partial: false, wide: false, m: -1 };
      drawTrace(d ? d.trace : null, pe, dd);
      drawSpec(d ? d.spectrum : null, dd);
      drawStack(d ? d.stack : null, pe, dd);
      drawCsd(d ? d.csd : null, d ? d.stack : null, pe, dd);
      return;
    }
    const e = pickedEvent();
    if (!e) return;
    const d = viewMode === 'pooled' ? pool.evData : evData;
    const ok = d && d.ok !== false;
    drawTrace(ok ? d.trace : null, e, d);
    drawSpec(ok ? d.spectrum : null, d);
    drawStack(ok ? d.stack : null, e, d);
    drawCsd(ok ? d.csd : null, ok ? d.stack : null, e, d);
  }

  /* An event canvas with nothing yet to draw on it, saying why.

     POOLED SAYS IT IN WORDS, NOT HERE (2026-10-19): "Its trace could not
     be read here…" was drawn into each of the four canvases and cut off
     at every edge. The sentence is above the pictures now, as text that
     wraps (`poolEventNote`); a pooled event's canvas says only "reading…"
     or "no trace". */
  function waitText(s, k, d) {
    const failed = d && d.ok === false;
    const pooledEv = viewMode === 'pooled' && !curAvg();
    const words = pooledEv
      ? (failed && !evComing() ? 'no trace' : 'reading…')
      : (failed ? d.error : 'reading…');
    s.g.fillStyle = failed && words !== 'reading…' ? k.warn : k.dim;
    const f = fitText(s.g, words, s.w - 16, 10);
    drawLines(s.g, f, 8, 18);
  }

  /* `noY` for a contact axis: it is named by CSC number by its caller,
     and numbered ticks under those would be a second, wrong scale. */
  function frame(s, k, xr, yr, xl, yl, noY) {
    const g = s.g;
    const x0 = EPAD.l, x1 = s.w - EPAD.r, y0 = EPAD.t, y1 = s.h - EPAD.b;
    const X = (v) => x0 + ((v - xr[0]) / (xr[1] - xr[0])) * (x1 - x0);
    const Y = (v) => y1 - ((v - yr[0]) / (yr[1] - yr[0])) * (y1 - y0);
    g.strokeStyle = k.line;
    g.lineWidth = 1;
    g.strokeRect(x0, y0, x1 - x0, y1 - y0);
    g.fillStyle = k.dim;
    g.font = FONT(9);
    g.textAlign = 'center';
    for (const t of ticks(xr[0], xr[1], Math.max(2, Math.floor((x1 - x0) / 55)))) {
      g.fillText(tickText(t), X(t), y1 + 11);
    }
    g.textAlign = 'right';
    if (!noY) {
      for (const t of ticks(yr[0], yr[1],
                            Math.max(2, Math.floor((y1 - y0) / 30)))) {
        g.fillText(tickText(t), x0 - 4, Y(t) + 3);
      }
    }
    g.textAlign = 'center';
    g.fillStyle = k.mid;
    const fx = fitText(g, xl, x1 - x0, 9.5);
    drawLines(g, fx, (x0 + x1) / 2, s.h - 4 - (fx.lines.length - 1) * (fx.pt + 1),
              fx.pt + 1);
    const fy = fitText(g, yl, y1 - y0, 9.5);
    g.save();
    g.translate(10, (y0 + y1) / 2);
    g.rotate(-Math.PI / 2);
    drawLines(g, fy, 0, 0, fy.pt + 1);
    g.restore();
    g.textAlign = 'left';
    return { X, Y, x0, x1, y0, y1 };
  }

  const finite = (arr) => (arr || []).filter((v) => v != null && isFinite(v));

  function drawTrace(t, e, d) {
    const s = sized('rcTrace', 200);
    if (!s) return;
    const k = ink();
    if (!t) { waitText(s, k, d); return; }
    const g = s.g;
    const sdv = t.sd || null;
    const ys = finite(t.y).concat(finite([t.baseline, t.peak_uV, t.half_uV]))
      .concat(sdv ? finite(t.y.map((v, j) => (v == null || sdv[j] == null ? null
                                               : v + sdv[j])))
                     .concat(finite(t.y.map((v, j) => (v == null || sdv[j] == null
                                                       ? null : v - sdv[j]))))
                  : []);
    let lo = Math.min.apply(null, ys), hi = Math.max.apply(null, ys);
    const pad = (hi - lo) * 0.08 || 1;
    lo -= pad; hi += pad;
    const xr = [t.t_ms[0], t.t_ms[t.t_ms.length - 1]];
    const F = frame(s, k, xr, [lo, hi], 'time from the stamp · ms',
                    'µV · CSC' + (t.contact != null ? t.contact : e.contact));
    const { X, Y, x0, x1 } = F;
    g.save();
    g.beginPath(); g.rect(F.x0, F.y0, F.x1 - F.x0, F.y1 - F.y0); g.clip();
    // The stamp.
    g.strokeStyle = k.dim;
    g.setLineDash([3, 3]);
    g.beginPath(); g.moveTo(X(0), F.y0); g.lineTo(X(0), F.y1); g.stroke();
    // The baseline, which is a real baseline and not zero.
    if (isFinite(t.baseline)) {
      g.beginPath(); g.moveTo(x0, Y(t.baseline)); g.lineTo(x1, Y(t.baseline));
      g.stroke();
    }
    g.setLineDash([]);
    /* The spread round an average, ±1 SD: how alike the events were. */
    if (sdv) {
      g.fillStyle = k.accent;
      g.globalAlpha = 0.16;
      g.beginPath();
      let started = false;
      t.t_ms.forEach((ms, j) => {
        const v = t.y[j], d2 = sdv[j];
        if (v == null || d2 == null || !isFinite(v) || !isFinite(d2)) return;
        if (started) g.lineTo(X(ms), Y(v + d2)); else { g.moveTo(X(ms), Y(v + d2)); started = true; }
      });
      for (let j = t.t_ms.length - 1; j >= 0; j--) {
        const v = t.y[j], d2 = sdv[j];
        if (v == null || d2 == null || !isFinite(v) || !isFinite(d2)) continue;
        g.lineTo(X(t.t_ms[j]), Y(v - d2));
      }
      g.closePath();
      g.fill();
      g.globalAlpha = 1;
    }
    g.strokeStyle = k.text;
    g.lineWidth = 1.2;
    g.beginPath();
    t.t_ms.forEach((ms, j) => {
      const v = t.y[j];
      if (v == null || !isFinite(v)) return;
      if (j) g.lineTo(X(ms), Y(v)); else g.moveTo(X(ms), Y(v));
    });
    g.stroke();
    // The half-amplitude level, and the width measured across it.
    if (isFinite(t.half_uV)) {
      g.strokeStyle = k.accent;
      g.globalAlpha = 0.6;
      g.setLineDash([2, 3]);
      g.beginPath(); g.moveTo(x0, Y(t.half_uV)); g.lineTo(x1, Y(t.half_uV));
      g.stroke();
      g.setLineDash([]);
      g.globalAlpha = 1;
    }
    /* WHICH CROSSING WAS NOT FOUND. An unresolved search reports the edge
       of the window it gave up at, and drawing a span to there would be
       drawing a half-width that was never measured. The server's own flags
       when it sends them; otherwise a crossing sitting on the search's
       edge is the one that was not found. */
    const cross = crossFor(e);
    const atEdge = (ms) => ms == null || !isFinite(ms)
                           || Math.abs(ms) >= cross - 0.75;
    const unres = !!(t.unresolved || e.partial && (e.missing || [])
                     .indexOf('hw_ms') >= 0);
    let lFound = t.left_found != null ? !!t.left_found
                 : !(unres && atEdge(t.left_ms));
    let rFound = t.right_found != null ? !!t.right_found
                 : !(unres && atEdge(t.right_ms));
    if (unres && lFound && rFound) { lFound = false; rFound = false; }
    const hasW = lFound && rFound && t.left_ms != null && t.right_ms != null
                 && isFinite(t.left_ms) && isFinite(t.right_ms);
    if (!hasW && isFinite(t.half_uV)) {
      const y = Y(t.half_uV);
      g.strokeStyle = k.warn;
      g.fillStyle = k.warn;
      g.lineWidth = 1.2;
      for (const [found, ms, side] of [[lFound, t.left_ms, -1],
                                       [rFound, t.right_ms, +1]]) {
        if (found && ms != null && isFinite(ms)) {
          const x = X(ms);
          g.beginPath(); g.moveTo(x, y - 5); g.lineTo(x, y + 5); g.stroke();
          continue;
        }
        // Not found: an open arrow at the search's edge (or the picture's,
        // if the search reaches past what is drawn), pointing outward.
        const x = Math.max(x0 + 6, Math.min(x1 - 6, X(side * cross)));
        g.setLineDash([2, 2]);
        g.beginPath(); g.moveTo(x, F.y0); g.lineTo(x, F.y1); g.stroke();
        g.setLineDash([]);
        g.beginPath();
        g.moveTo(x + side * 6, y); g.lineTo(x, y - 4); g.lineTo(x, y + 4);
        g.closePath(); g.fill();
      }
    }
    if (hasW && isFinite(t.half_uV)) {
      const a = X(t.left_ms), b = X(t.right_ms), y = Y(t.half_uV);
      g.strokeStyle = k.accent;
      g.lineWidth = 3;
      g.beginPath(); g.moveTo(a, y); g.lineTo(b, y); g.stroke();
      g.lineWidth = 1.4;
      for (const x of [a, b]) {
        g.beginPath(); g.moveTo(x, y - 5); g.lineTo(x, y + 5); g.stroke();
      }
    }
    if (isFinite(t.peak_ms) && isFinite(t.peak_uV)) {
      g.beginPath();
      g.arc(X(t.peak_ms), Y(t.peak_uV), 4, 0, 6.2832);
      g.fillStyle = colOf(e.cls);
      g.fill();
      g.strokeStyle = k.text;
      g.lineWidth = 1;
      g.stroke();
    }
    g.restore();
    // What was measured, said on the picture it was measured from.
    g.fillStyle = k.mid;
    g.font = FONT(9.5);
    const amp = t.amp_uV != null && isFinite(t.amp_uV) ? t.amp_uV
      : Math.abs(t.peak_uV - (t.baseline || 0));
    const side = !lFound && !rFound ? 'either side'
               : !lFound ? 'before the peak' : 'after the peak';
    const said = fmt(amp, 0) + ' µV from baseline  ·  ' + (hasW
        ? 'half-width ' + fmt(t.right_ms - t.left_ms, 1) + ' ms'
          + (e.wide ? ' (widened search)' : '')
        : 'half-width not found ' + side + ' within ±' + hz(cross) + ' ms');
    const f = fitText(g, said, F.x1 - F.x0 - 8, 9.5);
    if (!hasW) g.fillStyle = k.warn;
    drawLines(g, f, F.x0 + 4, F.y0 + 11);
    GEOM.ev.trace = { baseline: t.baseline, half: t.half_uV, hasW,
                      leftFound: lFound, rightFound: rFound,
                      peak: [t.peak_ms, t.peak_uV] };
  }

  /* Power, as dB. The API sends Welch PSDs; if a row arrives already in dB
     (anything at or below zero is not a power) it is drawn as it is. */
  function asDb(arr, flag) {
    const a = arr || [];
    if (flag === true || a.some((v) => v != null && v <= 0)) return a;
    return a.map((v) => (v == null || !isFinite(v) ? null
                                                   : 10 * Math.log10(v)));
  }

  function drawSpec(sp, d) {
    const s = sized('rcSpec', 200);
    if (!s) return;
    const k = ink();
    if (!sp) { waitText(s, k, d); return; }
    const g = s.g;
    const ev = asDb(sp.event, sp.db), bl = asDb(sp.baseline, sp.db);
    const ys = finite(ev).concat(finite(bl));
    let lo = Math.min.apply(null, ys), hi = Math.max.apply(null, ys);
    const pad = (hi - lo) * 0.08 || 1;
    lo -= pad; hi += pad;
    const f = sp.f || [];
    const xr = [f[0] || 0, f[f.length - 1] || 1];
    const F = frame(s, k, xr, [lo, hi], 'frequency · Hz', 'power · dB');
    const band = sp.band || [shownParams().band_lo, shownParams().band_hi];
    g.save();
    g.beginPath(); g.rect(F.x0, F.y0, F.x1 - F.x0, F.y1 - F.y0); g.clip();
    g.fillStyle = k.accent;
    g.globalAlpha = 0.14;
    const a = F.X(band[0]), b = F.X(band[1]);
    g.fillRect(a, F.y0, Math.max(1, b - a), F.y1 - F.y0);
    g.globalAlpha = 1;
    const line = (arr, col, w) => {
      g.strokeStyle = col;
      g.lineWidth = w;
      g.beginPath();
      let on = false;
      f.forEach((hzv, j) => {
        const v = arr[j];
        if (v == null || !isFinite(v)) { on = false; return; }
        if (on) g.lineTo(F.X(hzv), F.Y(v)); else g.moveTo(F.X(hzv), F.Y(v));
        on = true;
      });
      g.stroke();
    };
    line(bl, k.dim, 1.2);
    line(ev, colOf((pickedEvent() || {}).cls) || k.text, 1.5);
    g.restore();
    g.font = FONT(9);
    g.fillStyle = k.mid;
    g.fillText(hz(band[0]) + '–' + hz(band[1]) + ' Hz', Math.min(a + 3, F.x1 - 60),
               F.y0 + 10);
    g.fillStyle = colOf((pickedEvent() || {}).cls);
    g.fillText('event', F.x1 - 70, F.y0 + 22);
    g.fillStyle = k.dim;
    g.fillText('baseline', F.x1 - 70, F.y0 + 33);
    GEOM.ev.spectrum = { band: band.slice() };
  }

  /* Every contact, one line each, scaled to fit.

     Scaled HERE, robustly, rather than trusting any one unit: the biggest
     deflection on the shank is a contact and a half, whatever it is in
     microvolts. The max-amp contact is drawn in the accent and named, and a
     bad contact is dashed -- still drawn, because "this one was out" is part
     of what is being looked at. */
  function drawStack(st, e, d) {
    const s = sized('rcStack', 240);
    if (!s) return;
    const k = ink();
    if (!st) { waitText(s, k, d); return; }
    const g = s.g;
    const rows = st.rows || [];
    const nums = st.nums || [];
    /* One flag per ROW, as the API sends it. A list of CSC numbers is
       accepted too, so either spelling reads the same. */
    const badList = st.bad || [];
    const byRow = badList.length === nums.length
                  && badList.every((b) => typeof b === 'boolean');
    const badNums = new Set(byRow ? [] : badList.map(Number));
    const isBadRow = (j) => (byRow ? !!badList[j] : badNums.has(Number(nums[j])));
    const n = rows.length;
    if (!n) return;
    /* The server has already put the rows in CONTACT units -- the gain is
       how many contacts the biggest deflection spans, the convention
       X-ray's traces use -- so a row is drawn at its index plus its value,
       downward being positive. Only without a gain is it scaled here. */
    let unit = 1;
    if (st.gain == null) {
      const mags = [];
      for (const r of rows) for (const v of r) {
        if (v != null && isFinite(v)) mags.push(Math.abs(v));
      }
      mags.sort((a, b) => a - b);
      const top = mags.length ? mags[Math.floor(mags.length * 0.995)] || 1 : 1;
      unit = 1.5 / top;
    }
    const t = st.t_ms || [];
    const xr = [t[0], t[t.length - 1]];
    const F = frame(s, k, xr, [0, 1], 'time from the stamp · ms',
                    'contact', true);
    const rowH = (F.y1 - F.y0) / n;
    const Yr = (j, v) => F.y0 + (j + 0.5 + v * unit) * rowH;
    const maxRow = nums.findIndex((x) => Number(x) === Number(e.contact));
    g.save();
    g.beginPath(); g.rect(F.x0, F.y0, F.x1 - F.x0, F.y1 - F.y0); g.clip();
    g.strokeStyle = k.dim;
    g.setLineDash([3, 3]);
    g.beginPath(); g.moveTo(F.X(0), F.y0); g.lineTo(F.X(0), F.y1); g.stroke();
    g.setLineDash([]);
    rows.forEach((r, j) => {
      const isMax = j === maxRow;
      const isBad = isBadRow(j);
      g.strokeStyle = isMax ? k.accent : (isBad ? k.dim : k.text);
      g.globalAlpha = isMax ? 1 : (isBad ? 0.5 : 0.75);
      g.lineWidth = isMax ? 1.8 : 0.8;
      if (isBad) g.setLineDash([2, 2]);
      g.beginPath();
      r.forEach((v, c) => {
        if (v == null || !isFinite(v)) return;
        const x = F.X(t[c]), y = Yr(j, v);
        if (c) g.lineTo(x, y); else g.moveTo(x, y);
      });
      g.stroke();
      g.setLineDash([]);
    });
    g.globalAlpha = 1;
    g.restore();
    g.fillStyle = k.dim;
    g.font = FONT(8.5);
    g.textAlign = 'right';
    const every = Math.max(1, Math.ceil(10 / rowH));
    nums.forEach((num, j) => {
      if (j % every && j !== maxRow) return;
      g.fillStyle = j === maxRow ? k.accent : k.dim;
      g.font = FONT(j === maxRow ? 9.5 : 8.5, j === maxRow);
      g.fillText(String(num), F.x0 - 4, F.y0 + (j + 0.5) * rowH + 3);
    });
    g.textAlign = 'left';
    GEOM.ev.stack = { rows: n, nums: nums.slice(), maxRow,
                      bad: nums.filter((_x, j) => isBadRow(j)),
                      maxY: maxRow >= 0 ? F.y0 + (maxRow + 0.5) * rowH : null };
  }

  /* The CSD, as a field, from the theme's own colours: sink one way, source
     the other, nothing in between is the background. Drawn at one pixel per
     sample and row and then scaled, smoothed, because a CSD sampled at
     contacts really does have something in between them. */
  function drawCsd(c, st, e, d) {
    const s = sized('rcCsd', 240);
    if (!s) return;
    const k = ink();
    if (!c) { waitText(s, k, d); return; }
    const g = s.g;
    const rows = c.rows || [];
    const nr = rows.length;
    const t = c.t_ms || (st && st.t_ms) || [];
    const nc = t.length;
    if (!nr || !nc) return;
    const all = (st && st.nums) || [];
    const nums = c.nums
      || (all.length === nr ? all
          : all.length === nr + 2 ? all.slice(1, -1) : null)
      || rows.map((_r, j) => j + 1);
    const lim = (c.clim && c.clim.length === 2)
      ? Math.max(Math.abs(c.clim[0]), Math.abs(c.clim[1])) : 0;
    let top = lim;
    if (!top) {
      for (const r of rows) for (const v of r) if (v != null && isFinite(v)) {
        top = Math.max(top, Math.abs(v));
      }
    }
    top = top || 1;
    const bg = rgbOf(k.bg), sink = rgbOf(k.ied), src = rgbOf(k.accent);
    const off = document.createElement('canvas');
    off.width = nc; off.height = nr;
    const og = off.getContext('2d');
    const img = og.createImageData(nc, nr);
    for (let j = 0; j < nr; j++) {
      for (let q2 = 0; q2 < nc; q2++) {
        const v = rows[j][q2];
        const at = (j * nc + q2) * 4;
        let rgb = bg;
        if (v != null && isFinite(v)) {
          const f = Math.max(-1, Math.min(1, v / top));
          const to = f < 0 ? sink : src;
          const w = Math.abs(f);
          rgb = [0, 1, 2].map((m) => bg[m] + (to[m] - bg[m]) * w);
        }
        img.data[at] = rgb[0]; img.data[at + 1] = rgb[1];
        img.data[at + 2] = rgb[2]; img.data[at + 3] = 255;
      }
    }
    og.putImageData(img, 0, 0);
    const xr = [t[0], t[nc - 1]];
    const F = frame(s, k, xr, [0, 1], 'time from the stamp · ms', 'contact',
                    true);
    g.imageSmoothingEnabled = true;
    g.drawImage(off, F.x0, F.y0, F.x1 - F.x0, F.y1 - F.y0);
    g.strokeStyle = k.line;
    g.strokeRect(F.x0, F.y0, F.x1 - F.x0, F.y1 - F.y0);
    const rowH = (F.y1 - F.y0) / nr;
    g.fillStyle = k.dim;
    g.font = FONT(8.5);
    g.textAlign = 'right';
    const every = Math.max(1, Math.ceil(10 / rowH));
    const maxRow = nums.findIndex((x) => Number(x) === Number(e.contact));
    nums.forEach((num, j) => {
      if (j % every && j !== maxRow) return;
      g.fillStyle = j === maxRow ? k.accent : k.dim;
      g.font = FONT(j === maxRow ? 9.5 : 8.5, j === maxRow);
      g.fillText(String(num), F.x0 - 4, F.y0 + (j + 0.5) * rowH + 3);
    });
    g.textAlign = 'left';
    if (maxRow >= 0) {
      const y = F.y0 + (maxRow + 0.5) * rowH;
      g.strokeStyle = k.accent;
      g.lineWidth = 1.2;
      g.setLineDash([4, 3]);
      g.beginPath(); g.moveTo(F.x0, y); g.lineTo(F.x1, y); g.stroke();
      g.setLineDash([]);
    }
    g.strokeStyle = k.dim;
    g.setLineDash([3, 3]);
    g.beginPath(); g.moveTo(F.X(0), F.y0); g.lineTo(F.X(0), F.y1); g.stroke();
    g.setLineDash([]);
    // The two colours, named.
    g.font = FONT(9);
    g.fillStyle = k.ied;
    g.fillText('sink', F.x1 - 58, F.y0 + 10);
    g.fillStyle = k.accent;
    g.fillText('source', F.x1 - 34, F.y0 + 10);
    GEOM.ev.csd = { rows: nr, maxRow, nums: nums.slice() };
  }

  /* ==================================================================
     Interaction

     One set of listeners for the life of the page, delegated by id,
     because every render replaces the canvases -- binding per render is how
     sixty rebuilds leak two hundred and forty listeners on detached nodes.
     ================================================================== */
  let press = null;   // { id, x, y, yaw, pitch, moved, centre }

  function local(e, cv) {
    const r = cv.getBoundingClientRect();
    return { x: e.clientX - r.left - cv.clientLeft,
             y: e.clientY - r.top - cv.clientTop };
  }

  const FLAT_IDS = FLATS.map(([id]) => id);

  function onDown(e) {
    const id = e.target && e.target.id;
    if (e.button !== 0) return;
    if (id !== 'rcSpace' && FLAT_IDS.indexOf(id) < 0) return;
    const S = scene();
    if (!S) return;
    const cv = e.target;
    const at = local(e, cv);
    /* THE LASSO: Shift and drag on the 3D view -- or a plain drag while
       the Lasso button is on -- draws round dots instead of turning. */
    if (id === 'rcSpace' && (e.shiftKey || lassoMode)) {
      press = { id, lasso: true, moved: false };
      lasso = [[at.x, at.y]];
      try { cv.setPointerCapture(e.pointerId); } catch (err) { /* fine */ }
      e.preventDefault();
      return;
    }
    press = { id, x: at.x, y: at.y, yaw: view.yaw, pitch: view.pitch,
              moved: false, centre: null };
    // A centre is taken hold of only where the view says it can be moved:
    // Single's override. The pooled centres are the pool's k-means'.
    if (id !== 'rcSpace' && S.draggable) {
      const c = centreAt(id, at.x, at.y);
      if (c) press.centre = c.k;
    }
    try { cv.setPointerCapture(e.pointerId); } catch (err) { /* fine */ }
    e.preventDefault();
  }

  function onMove(e) {
    if (!press) return;
    const cv = document.getElementById(press.id);
    if (!cv) { press = null; return; }
    const at = local(e, cv);
    if (press.lasso) {
      const last = lasso[lasso.length - 1];
      if ((at.x - last[0]) ** 2 + (at.y - last[1]) ** 2 >= 9) {
        lasso.push([at.x, at.y]);
        press.moved = true;
        drawSpace();
      }
      return;
    }
    const dx = at.x - press.x, dy = at.y - press.y;
    if (!press.moved && dx * dx + dy * dy < 9) return;
    press.moved = true;
    if (press.id === 'rcSpace') {
      /* Turning, not dragging a dot: a press that moves is a rotation,
         one that does not is a pick. Pitch stops short of straight down
         so the view never flips over the top. */
      view.yaw = press.yaw + dx * 0.01;
      view.pitch = Math.max(-1.45, Math.min(1.45, press.pitch + dy * 0.01));
      drawSpace();
      return;
    }
    if (press.centre != null) {
      const G = GEOM.flats[press.id];
      const c0 = centresShown()[press.centre];
      if (!G || !c0) return;
      const x = Math.max(G.box.x0, Math.min(G.box.x1, at.x));
      const y = Math.max(G.box.y0, Math.min(G.box.y1, at.y));
      const r2 = G.toRaw(x, y);
      const raw = c0.raw.slice();
      raw[G.xa] = r2[0];
      raw[G.ya] = r2[1];
      const z = c0.z.slice();
      z[G.xa] = rawToZ(G.xa, r2[0]);
      z[G.ya] = rawToZ(G.ya, r2[1]);
      live = { k: press.centre, z, raw };
      drawMain();
    }
  }

  function onUp(e) {
    if (!press) return;
    const p = press;
    press = null;
    const cv = document.getElementById(p.id);
    if (!cv) return;
    if (p.lasso) { finishLasso(); return; }
    if (p.id === 'rcSpace') {
      if (!p.moved) {
        const at = local(e, cv);
        const i = pickSpace(at.x, at.y);
        const S = scene();
        if (i != null && S) {
          if (curAvg()) { if (viewMode === 'pooled') pool.avg = null; else avg = null; }
          S.onPick(i);
        }
      }
      return;
    }
    if (p.centre != null) {
      /* COMMITTED ON RELEASE. The refit is one request; one per pixel of
         drag would be a queue of answers to positions nobody is at. */
      if (p.moved && live) {
        moveCentre(live.k, live.z);
      } else {
        live = null;
        drawMain();
      }
      return;
    }
    if (!p.moved) {
      const at = local(e, cv);
      const i = pickFlat(p.id, at.x, at.y);
      const S = scene();
      if (i != null && S) S.onPick(i);
    }
  }

  /* Whether a point is inside a drawn path (even-odd ray casting). */
  function inPath(x, y, path) {
    let inside = false;
    for (let a = 0, b = path.length - 1; a < path.length; b = a++) {
      const [xa, ya] = path[a], [xb, yb] = path[b];
      if (((ya > y) !== (yb > y))
          && (x < (xb - xa) * (y - ya) / ((yb - ya) || 1e-9) + xa)) inside = !inside;
    }
    return inside;
  }

  /* The dots inside the path, as the 3D view drew them. Only the dots that
     are on show: in Pooled, a focus that dims the rest keeps them out. */
  function finishLasso() {
    const path = lasso || [];
    lasso = null;
    if (path.length < 3) { drawSpace(); return; }
    const pts = ((GEOM.space || {}).pts || []).filter(
      (pt) => (pt.alpha == null || pt.alpha > 0.5) && inPath(pt.x, pt.y, path));
    setLassoSel(pts.map((pt) => pt.i));
  }

  function lassoIds() { return viewMode === 'pooled' ? pool.lassoSel : lassoSel; }
  function setLassoSel(ids) {
    if (viewMode === 'pooled') pool.lassoSel = ids; else lassoSel = ids;
    render();
  }

  /* What can be done with dots drawn round: look at their average, or make
     them a cluster of their own and call it DS or IED. */
  function lassoBar() {
    const ids = lassoIds();
    const evs = ((scene() || {}).events || []).filter(
      (e) => ids.indexOf(e.i) >= 0);
    // Nothing drawn round, no bar: the 3D view's heading says how, and a
    // line here pushed the event's own controls below the fold.
    if (!evs.length) return null;
    return el('div', { class: 'card rc-lasso-bar' }, [
      el('strong', { text: evs.length + ' dot' + (evs.length === 1 ? '' : 's')
                           + ' drawn round' }),
      el('span', { class: 'spacer' }),
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Average them',
        extra: 'rc-lasso-avg',
        onclick: () => showAverage('the ' + evs.length + ' drawn round', evs) }),
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Make a DS cluster',
        extra: 'rc-lasso-ds', onclick: () => addDrawn(evs, 'ds') }),
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Make an IED cluster',
        extra: 'rc-lasso-ied', onclick: () => addDrawn(evs, 'ied') }),
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Clear',
        extra: 'rc-lasso-clear', onclick: () => setLassoSel([]) }),
    ]);
  }

  /* A drawn cluster: its events are held out of k-means and called as
     drawn. A dot can be in one drawn cluster only -- the newer drawing
     takes it -- and the request carries them, so the result rebuilds. */
  function addDrawn(evs, call) {
    if (viewMode === 'pooled') {
      const mem = (pool.fit && pool.fit.members) || [];
      const ids = evs.map((e) => [(mem[e.m] || {}).key, e.src_i]);
      const keyOf = (x) => x[0] + '|' + x[1];
      const mine = new Set(ids.map(keyOf));
      pool.drawn = pool.drawn.map((g) => ({ call: g.call,
        events: g.events.filter((x) => !mine.has(keyOf(x))) }))
        .filter((g) => g.events.length);
      pool.drawn.push({ events: ids, call });
      pool.lassoSel = [];
      runPool();
      return;
    }
    const ids = evs.map((e) => e.i);
    const mine = new Set(ids);
    q.drawn = q.drawn.map((g) => ({ call: g.call,
      events: g.events.filter((i) => !mine.has(i)) }))
      .filter((g) => g.events.length);
    q.drawn.push({ events: ids, call });
    lassoSel = [];
    refit();
  }

  function onWheel(e) {
    if (!e.target || e.target.id !== 'rcSpace' || !scene()) return;
    e.preventDefault();
    view.zoom = Math.max(0.4, Math.min(8, view.zoom * Math.exp(-e.deltaY * 0.0015)));
    drawSpace();
  }

  function resetView() {
    view.yaw = YAW0; view.pitch = PITCH0; view.zoom = 1;
    drawSpace();
  }

  function onKey(e) {
    if (!scene()) return;
    if (viewMode !== 'pooled' && !q.read) return;
    if (!document.getElementById('rcSpace')) return;
    const box = host();
    if (!box || !box.offsetParent) return;
    const tag = (document.activeElement || {}).tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (e.key === 'ArrowRight') step(+1);
    else if (e.key === 'ArrowLeft') step(-1);
    else return;
    e.preventDefault();
  }

  document.addEventListener('pointerdown', onDown);
  document.addEventListener('pointermove', onMove);
  document.addEventListener('pointerup', onUp);
  document.addEventListener('pointercancel', () => {
    press = null;
    if (live && !fitting) { live = null; drawMain(); }
  });
  document.addEventListener('wheel', onWheel, { passive: false });
  /* A DOUBLE-CLICK ON A DOT opens it in Xplorefinder (2026-10-20); on
     empty space it still puts the view back. The first click of the two
     has already picked it, so this opens the dot under the pointer. */
  document.addEventListener('dblclick', (e) => {
    const cv = e.target;
    if (!cv || !cv.id) return;
    const flat = FLATS.some(([id]) => id === cv.id);
    if (cv.id !== 'rcSpace' && !flat) return;
    const at = local(e, cv);
    const i = cv.id === 'rcSpace' ? pickSpace(at.x, at.y)
                                  : pickFlat(cv.id, at.x, at.y);
    const S = scene();
    if (i != null && S) {
      S.onPick(i);
      openPickedInXplore();
      return;
    }
    if (cv.id === 'rcSpace') resetView();
  });

  /* The picked dot in Xplorefinder, or why not. */
  function openPickedInXplore() {
    const e = pickedEvent();
    if (!e) {
      toast('Pick a dot first: click one, then press this -- or double-click '
            + 'it.', null, 5000);
      return Promise.resolve(false);
    }
    return openInXplore();
  }

  /* Whether a recording can be opened from here, as far as the registry
     already read says: the recording window needs the recording, not the
     member's read (a member read on another machine is still a recording
     on this one). Before the registry is read, yes; opening it says if it
     is not. */
  function recordingHere(gid) {
    const tk = BARRY.views.toolkit;
    const rows = tk && tk.registryRows ? tk.registryRows() : [];
    if (!rows.length || !gid) return true;
    const row = rows.find((r) => r.gid === gid);
    // Read, and not in it: not a recording this machine knows.
    if (!row) return false;
    try { return !!BARRY.vacc.reachFor(row, 'rootcanal').path; } catch (e) { return true; }
  }
  document.addEventListener('keydown', onKey);

  /* ==================================================================
     Redraw when the panel changes size -- X-ray's machinery, for X-ray's
     reasons: a notification is not guaranteed, so the invariant is also
     checked on a slow tick while the panel is on screen, and the tick stops
     itself as soon as it is not.
     ================================================================== */
  const CANVAS_IDS = ['rcSpace', 'rcFlatAH', 'rcFlatAP', 'rcFlatHP',
                      'rcTrace', 'rcSpec', 'rcStack', 'rcCsd',
                      'rcHistA', 'rcHistH', 'rcHistF', 'rcHistS'];
  let sizeWatch = null;
  let sizeTick = null;
  let redrawSoon = null;
  let redrawing = false;

  function mismatched() {
    const dpr = window.devicePixelRatio || 1;
    for (const id of CANVAS_IDS) {
      const cv = document.getElementById(id);
      if (!cv || !cv.width || !cv.clientWidth) continue;
      if (Math.abs(cv.clientWidth - cv.width / dpr) > 1
          || Math.abs(cv.clientHeight - cv.height / dpr) > 1) return true;
    }
    return false;
  }

  function redrawIfNeeded() {
    if (redrawing || press || !scene() || !mismatched()) return;
    redrawing = true;
    try { drawAll(); } finally { redrawing = false; }
  }

  function onBoxResize() {
    if (redrawing) return;
    if (redrawSoon) clearTimeout(redrawSoon);
    redrawSoon = setTimeout(() => { redrawSoon = null; redrawIfNeeded(); }, 120);
  }

  function watchSize() {
    if (!sizeTick) {
      sizeTick = setInterval(() => {
        if (!document.getElementById('rcSpace')) {
          clearInterval(sizeTick);
          sizeTick = null;
          return;
        }
        if (!redrawSoon) redrawIfNeeded();
      }, 400);
    }
    if (typeof ResizeObserver !== 'function') return;
    if (!sizeWatch) sizeWatch = new ResizeObserver(onBoxResize);
    sizeWatch.disconnect();
    const h = host();
    if (h) sizeWatch.observe(h);
    for (const id of CANVAS_IDS) {
      const cv = document.getElementById(id);
      if (cv) sizeWatch.observe(cv);
    }
  }
  window.addEventListener('resize', onBoxResize);

  /* ==================================================================
     The recording itself, in a window of its own

     X-ray's arrangement, and for X-ray's reason: checking one event
     against the raw recording is done WHILE reading the panel, so the
     panel has to still be there. A named window, so pressing the button
     again focuses the one that is open rather than opening another; and it
     FOLLOWS -- every event stepped to here is pushed into it as curation
     marks, which that window already knows how to draw, coloured DS and
     IED, with the max contact as a channel line.
     ================================================================== */
  let xWin = null;

  function xOpen() {
    try { return !!(xWin && !xWin.closed); } catch (e) { return false; }
  }

  /* Where the recording is, from THIS machine. Registry rows carry `here`,
     the paths reachable from here -- not `path`, which is not a field and
     reads as undefined for every recording. */
  async function recordingPath(gid) {
    const tk = BARRY.views.toolkit;
    if (!tk) return null;
    const want = gid || q.gid;
    const find = () => (tk.registryRows ? tk.registryRows() : [])
      .find((r) => r.gid === want);
    /* The rows already read first (2026-10-20). The registry is held for a
       minute and takes seconds to read again, so every dot opened after
       that minute sat waiting on it before the window moved -- long
       enough to look like the wrong event was showing. A recording's
       paths do not change mid-sitting; read again only for one not in
       them. */
    let row = find();
    if (!row) {
      try { if (tk.loadRegistry) await tk.loadRegistry(); } catch (e) { /* below */ }
      row = find();
    }
    return row ? BARRY.vacc.reachFor(row, 'rootcanal').path : null;
  }

  /* Which recording the window is about, its events, and the one being
     looked at. In Pooled that is the picked dot's member: a pool is many
     recordings, and the window shows one of them at a time. */
  function xTarget() {
    if (viewMode === 'pooled') {
      const e = poolPicked();
      const m = e ? poolMember(e) : null;
      if (!e || !m) return null;
      const pr = (m.pin || {}).params || {};
      return {
        gid: m.gid, now: e,
        evs: poolEvents().filter((x) => x.m === e.m),
        lo: pr.lo_hz != null ? pr.lo_hz : DEF.lo_hz,
        hi: pr.hi_hz != null ? pr.hi_hz : DEF.hi_hz,
        mains: !!pr.mains_out,
      };
    }
    const e = pickedEvent();
    if (!e || !fit || !fit.ok) return null;
    const p = shownParams();
    return { gid: q.gid, now: e, evs: fit.events || [], lo: p.lo_hz,
             hi: p.hi_hz, mains: !!asParam('mains_out', p.mains_out) };
  }

  function xUrl(path, t) {
    const xt = xTarget() || {};
    const p = { lo_hz: xt.lo != null ? xt.lo : DEF.lo_hz,
                hi_hz: xt.hi != null ? xt.hi : DEF.hi_hz };
    const args = new URLSearchParams({
      csc: path,
      panes: JSON.stringify([{ panel: 'traces' }, { panel: 'csd' }]),
      t0: Math.max(0, t - 0.25).toFixed(4),
      span: '0.5',
      // The fit's own filter, so the window shows what was measured: 0
      // and 0 is Xplorefinder's "no filter", and a filter that took the
      // mains out asks for its notch.
      hp: String(p.lo_hz), lp: String(p.hi_hz),
      notch: xt.mains ? '60' : '0',
      chrome: 'notabs,noheads',
      role: 'rootcanal',
      theme: (BARRY.state && BARRY.state.theme) || 'dark',
    });
    return location.origin + '/?' + args.toString() + '#xplore';
  }

  async function openInXplore() {
    const xt = xTarget();
    const e = xt && xt.now;
    if (!e) return false;
    if (xOpen()) {
      try { xWin.focus(); } catch (err) { /* not important */ }
      if (pushXplore() === true) return true;
      return chaseXplore();
    }
    const path = await recordingPath(xt.gid);
    if (!path) {
      toast('None of this recording’s paths are reachable from this machine, '
            + 'so there is nothing to look at.', 'err', 9000);
      return false;
    }
    xWin = window.open(xUrl(path, e.t), 'barry-rootcanal-traces',
                       'width=1180,height=900,menubar=no,toolbar=no');
    if (!xWin) {
      toast('The recording window was blocked. Allow pop-ups for this page, '
            + 'then press “Open in Xplorefinder” again.', 'err', 9000);
      return false;
    }
    xNav = { gid: xt.gid, path: path, at: Date.now() };
    BARRY.activity.log('rootcanal.xplore', { gid: xt.gid, t: e.t, cls: e.cls,
                                             pooled: viewMode === 'pooled' });
    /* WAITED FOR, not assumed. The window is a whole application booting
       and reading the recording before it has anything to put a mark on --
       and whatever is picked while it does is what it shows once it has. */
    return chaseXplore();
  }

  /* THE PICKED DOT, WHEREVER IT IS (2026-10-20: "select a dot and open that
     specific event in Xplorefinder -- make sure it pulls out the right
     one"). The window follows every pick. A dot from another recording --
     another member of a pool, or a set picked since -- used to have its
     marks and its time pushed onto whatever recording the window already
     showed. Now the window is sent to the dot's own recording, at the dot,
     and the marks go on once it has opened it. Only the newest pick is
     followed if several land while it is opening. */
  let xGen = 0;
  let xSaid = { gid: null, at: 0 };
  /* Where the window was last sent: the recording, and the path it was
     opened by -- a folder registered under two ids is still the folder it
     was sent to. */
  let xNav = null;
  function followXplore() {
    if (!xOpen()) return;
    if (pushXplore() !== true) chaseXplore();
  }

  /* Until the window shows the CURRENT pick: asked afresh every turn, so a
     dot picked while the window is still opening the last one is the one
     it ends on. Sent to the pick's recording when it is on another one and
     has not already been sent there. One chase at a time; the newest
     takes over. */
  async function chaseXplore() {
    const mine = ++xGen;
    const until = Date.now() + 60000;
    while (Date.now() < until && mine === xGen) {
      if (!xOpen()) return false;
      const xt = xTarget();
      const e = xt && xt.now;
      if (!e) return false;
      const r = pushXplore();
      if (r === true) return true;
      // Sent there already and still opening it: wait, rather than send
      // it again (and again) while it boots.
      const going = xNav && xNav.gid === xt.gid && Date.now() - xNav.at < 45000;
      if (r === 'elsewhere' && !going) {
        const path = await recordingPath(xt.gid);
        if (mine !== xGen) return false;
        if (!path) {
          // Said once for a pick, though the pick and the press both ask.
          if (xSaid.gid !== xt.gid || Date.now() - xSaid.at > 4000) {
            toast('That dot’s recording is not reachable from this machine, '
                  + 'so the recording window cannot show it.', 'err', 9000);
          }
          xSaid = { gid: xt.gid, at: Date.now() };
          return false;
        }
        try {
          xWin.location.href = xUrl(path, e.t);
        } catch (err) {
          return false;
        }
        xNav = { gid: xt.gid, path: path, at: Date.now() };
        BARRY.activity.log('rootcanal.xplore', { gid: xt.gid, t: e.t,
          cls: e.cls, pooled: viewMode === 'pooled', moved: true });
      }
      await new Promise((res) => setTimeout(res, 250));
    }
    return false;
  }

  /* Where the picked event is in the window's list. By its number as well
     as by identity: in Pooled the picked event is a COPY (it carries its
     trace's contact), so `indexOf` never found it -- the window was never
     moved to it and the mark said the member's first event. A second dot
     opened showed the first one. */
  function xIndex(xt) {
    const n = xt && xt.now;
    if (!n) return -1;
    const at = xt.evs.indexOf(n);
    if (at >= 0) return at;
    return xt.evs.findIndex((x) => x.i === n.i
      && (n.m == null || x.m === n.m));
  }

  /* Every event in the set, coloured by class, the current one marked and
     its max contact drawn across the panes. Returns whether it landed, so
     the opener can keep waiting rather than believing it worked. */
  function pushXplore() {
    const xt = xTarget();
    if (!xOpen() || !xt) return false;
    let xf = null;
    try { xf = xWin.barryXplore; } catch (e) { return false; }
    if (!xf || !xf.current) return false;
    let sess = null;
    try { sess = xf.current(); } catch (e) { return false; }
    if (!sess) return false;
    /* Another recording in the window: nothing is put on it. The folder it
       was sent to counts as the recording asked for, whatever id the
       registry gives that folder. */
    const shown = (sess.identity || {}).gid;
    const sent = xNav && xNav.gid === xt.gid && sess.path
      && String(sess.path) === String(xNav.path);
    if (shown && xt.gid && shown !== xt.gid && !sent) return 'elsewhere';
    const evs = xt.evs;
    const at = xIndex(xt);
    const now = at >= 0 ? xt.now : null;
    try {
      sess.curationMarks = {
        kind: 'rootcanal',
        index: Math.max(0, at),
        at: now ? now.t : null,
        gid: xt.gid,
        labels: [
          { id: 'DS', name: 'DS', color: colOf('ds') },
          { id: 'IED', name: 'IED', color: colOf('ied') },
        ],
        events: evs.map((e) => ({
          start: e.t,
          label: e.cls === 'ied' ? 'IED' : e.cls === 'ds' ? 'DS' : null,
        })),
      };
      if (xf.setChannelLines) {
        xf.setChannelLines(sess, now && now.contact != null ? [{
          key: 'rootcanal-max',
          // Faded and hidden with the marks (2026-10-21): it is one of them.
          followsMarks: true,
          label: 'max amp' + (now.cls ? ' · ' + now.cls.toUpperCase() : ''),
          colour: colOf(now.cls), number: Number(now.contact),
        }] : []);
      }
      if (now && xf.setWindow) {
        const span = (sess.span && sess.span > 0.01) ? sess.span : 0.5;
        xf.setWindow(0, Math.max(0, now.t - span / 2), span);
      }
      if (xf.redraw) { xf.redraw(0); xf.redraw(1); }
      else if (xf.refreshAll) xf.refreshAll();
    } catch (e) {
      return false;
    }
    return true;
  }

  /* ==================================================================
     POOLED (ROOTCANAL-POOL-SPEC.md; every decision in it is the user's)

     The question: do dentate spikes and IEDs form two clear clusters, or
     one ambiguous spectrum -- across recordings, by mouse and by mouse
     type, and for any one mouse on its own.

     What joins a pool is a Root Canal single: a BANKED result, which
     already holds every event's numbers and reads no recording, or an
     UNBANKED read cached on this machine, fitted at the settings it is
     added with. The pool pools the raw numbers and z-scores them ONCE,
     clusters them once, and keeps every event's own single call beside
     the pooled one -- which is what makes "did pooling change its mind"
     a count rather than an impression.

     Nothing in here writes to the Event Bank. A pool is saved as a Jarvis
     artifact of its own, under a label somebody types.
     ================================================================== */
  function setView(mode) {
    const want = mode === 'pooled' ? 'pooled' : 'single';
    viewMode = want;
    try { localStorage.setItem(VIEW_KEY, want); } catch (e) { /* fine */ }
    press = null;
    render();
    if (want === 'pooled') loadPool();
    else if (!cands) loadCandidates();
  }

  /* The bar, under the header: one choice between two views of the tool,
     which is what a seg is for (constitution §2). */
  function viewBar() {
    return el('div', { class: 'rc-viewbar' }, [
      BARRY.ui.seg([
        ['single', 'Single', 'One recording: read it, split it, bank it.'],
        ['pooled', 'Pooled', 'Many recordings in one space: two clear groups, '
                           + 'or one spectrum?'],
      ], viewMode, setView, { extra: 'rc-viewseg' }),
      el('span', { class: 'hint', text: viewMode === 'pooled'
        ? 'Root Canal singles pooled into one space. Nothing here is banked; '
          + 'a pool is saved under a label of its own.'
        : 'One aligned set at a time, banked as the next version of that set.' }),
    ]);
  }

  /* One read of the lists at a time (2026-10-19): the ToolKit paints twice
     on opening and the view bar once more, and each asked for the
     candidates again while the first answer was still on its way -- four
     reads of the bank for one press. */
  let poolLoading = null;
  function loadPool() {
    if (!poolLoading) {
      poolLoading = loadPool_().finally(() => { poolLoading = null; });
    }
    return poolLoading;
  }

  async function loadPool_() {
    const jobs = [];
    if (!pool.cands) {
      jobs.push(api('/api/rootcanal/pool/candidates').then((got) => {
        pool.cands = got.singles || [];
        pool.candsErr = null;
      }).catch((e) => {
        pool.cands = [];
        pool.candsErr = e.message;
        reportClientError('rootcanal.pool.candidates', e.message,
                          String(e && e.stack));
      }));
    }
    if (!pool.shelf) jobs.push(loadShelf(true));
    await Promise.all(jobs);
    // Only when something arrived: a call with everything loaded is not a
    // reason to rebuild the page.
    if (jobs.length && viewMode === 'pooled') render();
  }

  async function loadShelf(quiet) {
    try {
      const got = await api('/api/rootcanal/pools');
      pool.shelf = got.pools || [];
      pool.shelfErr = null;
    } catch (e) {
      pool.shelf = [];
      pool.shelfErr = e.message;
    }
    // Not the pools-of-pools shelf, which carries `.rc-shelf` too.
    if (!quiet && viewMode === 'pooled') swap('.rc-shelf:not(.rc-dshelf)', shelfCard());
  }

  /* A candidate by a member's key. A saved single is ONE candidate whatever
     version of it is picked: "s:<artifact>:<v>" finds it by its artifact. */
  function candOf(key) {
    const cs = pool.cands || [];
    const hit = cs.find((c) => c.key === key);
    if (hit) return hit;
    const m = /^s:([^:]+):/.exec(String(key || ''));
    return m ? cs.find((c) => c.kind === 'single' && c.artifact_id === m[1])
               || null : null;
  }

  /* The selection entry for a candidate, whichever version is picked. */
  function selOf(c) {
    if (!c) return null;
    if (c.kind === 'single') {
      return pool.sel.find((m) => String(m.key)
        .indexOf('s:' + c.artifact_id + ':') === 0) || null;
    }
    return pool.sel.find((m) => m.key === c.key) || null;
  }

  /* The version of a saved single a member uses: its picked one, the one
     its row offers while unticked (2026-10-19), or the latest. */
  function versionOfCand(c) {
    const m = selOf(c);
    const at = /^s:([^:]+):(\d+)$/.exec(String(m ? m.key
                                              : pool.pickSrc[recOf(c)] || ''));
    const v = at && at[1] === c.artifact_id ? Number(at[2]) : c.version;
    return (c.versions || []).find((x) => x.v === v) || null;
  }

  /* ONE ROW PER RECORDING (2026-10-19). The server offers every ANSWER
     about a recording as a candidate of its own -- its banked result
     ("b:"), a read cached here and not banked ("u:"), each version of a
     saved single ("s:<artifact>:<v>") -- because they are different
     answers. Listed as they came, one recording showed two or three times
     ("some events are duplicates here"), and ticking both counted every
     one of its events twice. So the list is of RECORDINGS, by bank entry:
     one row and one tick each, and a choice of which answer where there is
     more than one -- the banked one unless another is chosen, else the
     newest saved single, else the read here. Only one answer about a
     recording goes into a pool; the server refuses a second by name. */
  const recOf = (c) => String((c && (c.entry_id || c.gid || c.key)) || '');
  const KIND_ORDER = { single: 0, banked: 1, read: 2, saved: 3 };
  let recMemo = { sig: null, list: [], byKey: new Map(), byId: new Map(),
                  byArt: new Map() };

  function recordings() {
    const cs = pool.cands || [];
    const sm = pool.savedMembers || [];
    const sig = [cs, cs.length, sm, sm.length];
    const was = recMemo.sig;
    if (was && sig.every((x, j) => x === was[j])) return recMemo.list;
    const byId = new Map(), byKey = new Map(), byArt = new Map();
    const recFor = (id, facts) => {
      let r = byId.get(id);
      if (!r) {
        r = { id, facts: [], answers: [], keys: new Set(), def: null };
        byId.set(id, r);
      }
      r.facts.push(facts);
      return r;
    };
    const add = (r, a) => {
      if (r.keys.has(a.key)) return;     // offered twice is one answer
      r.answers.push(a); r.keys.add(a.key); byKey.set(a.key, r);
    };
    /* ONE ENTRY PER ANSWER (2026-10-20: "so many different versions, all
       with different amounts"). Banking keeps a version of the single
       too, and importing a banked result makes one -- the SAME numbers as
       the banked result, which was then listed twice. A saved version that
       is a listed banked result joins it: the banked answer says it is
       also saved, and the version is not offered again. */
    const bankedPh = new Map();          // recording -> {params_hash: banked}
    for (const c of cs) {
      if (c.banked && c.kind !== 'single' && c.params_hash) {
        const m = bankedPh.get(recOf(c)) || new Map();
        m.set(c.params_hash, c);
        bankedPh.set(recOf(c), m);
      }
    }
    const savedAs = new Map();           // banked key -> [saved versions]
    for (const c of cs) {
      const r = recFor(recOf(c), c);
      if (c.kind === 'single') {
        byArt.set(c.artifact_id, r);
        const vs = (c.versions || []).filter((x) => x.here !== false)
          .sort((a, b) => b.v - a.v);
        if (!vs.length) vs.push({ v: c.version, nickname: c.nickname });
        for (const x of vs) {
          const imp = (((x.inputs || [])[0]) || {}).imported_from;
          const twin = imp && (bankedPh.get(recOf(c)) || new Map()).get(imp);
          if (twin) {
            const l = savedAs.get(twin.key) || [];
            l.push(x);
            savedAs.set(twin.key, l);
            continue;
          }
          const ns = x.n_summary || {};
          add(r, { key: 's:' + c.artifact_id + ':' + x.v, kind: 'single', cand: c,
                   ver: x, n: ns.events != null ? ns.events : c.n,
                   filt: (x.measure || {}).filter_label || null, k: x.k,
                   words: 'saved v' + x.v + (x.nickname ? ' · ' + x.nickname : ''),
                   title: versionHover(x) });
        }
      } else if (c.banked) {
        add(r, { key: c.key, kind: 'banked', cand: c, n: c.n,
                 filt: c.filter_label || null, k: c.k, older: !!c.older,
                 words: 'banked' + (c.version ? ' v' + c.version : ''),
                 title: 'Its banked result' + (c.version ? ', v' + c.version
                   + ' of the set' : '') + (c.filter_label ? ', measured on '
                   + c.filter_label : '') + (c.k != null ? ', k = ' + c.k : '')
                   + (c.from_name ? ', read from v' + c.from_name : '')
                   + ': the numbers are in the bank, so it reads no recording.'
                   + (c.older ? ' It is about an earlier version of the set '
                     + 'than the one the bank holds now.' : '') });
      } else {
        /* Which version of the set's stamps it read: its events alone did
           not say -- "37 events" and "53 events" were two reads of two
           versions, and only the counts told them apart. */
        const of = c.live ? 'of v' + c.from_name + ', the set as it is'
          : c.from_name ? 'of v' + c.from_name : 'of an earlier version';
        add(r, { key: c.key, kind: 'read', cand: c, n: c.n, older: !!c.older,
                 words: 'read here, not banked · ' + of,
                 title: 'The read cached on this machine, not banked ('
                      + of + (c.n != null ? ', ' + c.n + ' events' : '')
                      + '): fitted at Single’s settings as they stand when '
                      + 'it is ticked.' });
      }
    }
    // The banked answers that are saved as versions too, said on them.
    for (const [key, xs] of savedAs) {
      const r = byKey.get(key);
      const a = r && r.answers.find((x) => x.key === key);
      if (!a) continue;
      xs.sort((p, q) => p.v - q.v);
      a.saved = xs;
      a.title += ' Also kept as saved ' + xs.map((x) => 'v' + x.v
        + (x.nickname ? ' ‘' + x.nickname + '’' : '')).join(', ')
        + ': the same numbers, offered once.';
    }
    /* A member of the opened pool that this machine does not offer: read
       on another machine, its numbers in the save. It joins its
       recording's row if this machine has one. */
    for (const m of sm) {
      if (byKey.has(m.key) || candOf(m.key)) continue;
      const fm = poolMemberByKey(m.key) || m;
      const r = recFor(recOf(m), {
        session_label: m.session_label, entry_id: m.entry_id, gid: m.gid,
        mouse_key: m.mouse_key, project: m.project, banked: !!m.banked,
        mouse_type: m.mouse_type_default || m.mouse_type, kind: 'saved', n: m.n,
      });
      add(r, { key: m.key, kind: 'saved', member: m, n: m.n,
               read_on: fm.read_on || 'another machine',
               words: (m.banked ? 'banked' : 'not banked') + ', as saved',
               title: 'Its read is on ' + (fm.read_on || 'another machine')
                    + ', not here. Its numbers come from the saved pool, '
                    + 'exactly as they were saved, so it pools as saved. '
                    + 'Measuring it another way needs its read.' });
    }
    /* Two answers that read the same are told apart by WHAT DIFFERS
       (2026-10-20): the filter they were measured on, then how many
       clusters, then their events -- and only failing all three by a name
       nobody reads ("result 794f36" was two measurements, LFP and DS). */
    const twins = (r) => r.answers.filter((a, j) => r.answers.some(
      (b, i) => i !== j && b.words === a.words));
    const differ = (xs, f) => new Set(xs.map(f)).size > 1;
    for (const r of byId.values()) {
      let tw = twins(r);
      if (tw.length && differ(tw, (a) => a.filt || '')) {
        for (const a of tw) if (a.filt) a.words += ' · ' + a.filt;
      }
      tw = twins(r);
      if (tw.length && differ(tw, (a) => a.k)) {
        for (const a of tw) if (a.k != null) a.words += ' · k = ' + a.k;
      }
      tw = twins(r);
      if (tw.length && differ(tw, (a) => a.n)) {
        for (const a of tw) if (a.n != null) a.words += ' · ' + a.n + ' events';
      }
      for (const a of twins(r)) {
        const tail = String(a.key).split(':').pop();
        a.words += (a.kind === 'banked' ? ' · result ' : ' · read ') + tail.slice(0, 6);
      }
      for (const a of r.answers) {
        if (a.saved) {
          a.words += ' · saved as ' + a.saved.map((x) => 'v' + x.v).join(', ');
        }
      }
    }
    for (const r of byId.values()) {
      // The ones about earlier versions of the set last, under their fold.
      r.answers.sort((a, b) => (a.older ? 1 : 0) - (b.older ? 1 : 0)
        || KIND_ORDER[a.kind] - KIND_ORDER[b.kind]);
      const now = r.answers.filter((a) => !a.older);
      r.def = (now.find((a) => a.kind === 'banked')
               || now.find((a) => a.kind === 'single')
               || now.find((a) => a.kind === 'read')
               || now[0] || r.answers[0]).key;
    }
    /* By project, then recording, in natural order (2026-10-20): they came
       in the server's string order, PTEN m2, m21, m22, m26, m51, m59, m6. */
    const lab = (r) => (r.facts[0] || {}).session_label || r.id;
    const list = Array.from(byId.values()).sort((a, b) =>
      natural((a.facts[0] || {}).project || '~', (b.facts[0] || {}).project || '~')
      || natural(lab(a), lab(b)));
    recMemo = { sig, list, byKey, byId, byArt };
    return recMemo.list;
  }

  /* The recording an answer is about. A saved single's version that is not
     listed (one measured again just now) is found by its artifact. */
  function recOfKey(key) {
    recordings();
    const k = String(key || '');
    if (recMemo.byKey.has(k)) return recMemo.byKey.get(k);
    const m = /^s:([^:]+):/.exec(k);
    return m ? recMemo.byArt.get(m[1]) || null : null;
  }

  /* What of one recording is in the pool: one answer, or -- in a pool
     opened from the shelf that was saved with two -- more. */
  function recSel(rec) {
    return rec ? pool.sel.filter((m) => recOfKey(m.key) === rec) : [];
  }

  function curKey(rec) {
    const mine = recSel(rec);
    if (mine.length) return mine[0].key;
    const want = pool.pickSrc[rec.id];
    return want && rec.keys.has(want) ? want : rec.def;
  }

  /* Its answers, and any in the pool that the list does not name. */
  function answersOf(rec) {
    const extra = recSel(rec).filter((m) => !rec.keys.has(m.key)).map((m) => ({
      key: m.key, kind: 'single', cand: candOf(m.key), n: null,
      words: 'saved v' + String(m.key).split(':').pop(), title: '' }));
    return extra.length ? rec.answers.concat(extra) : rec.answers;
  }

  const answerOf = (rec, key) => answersOf(rec).find((a) => a.key === key) || null;

  /* What goes into `pool.sel` for an answer. A read here is fitted at
     Single's settings as they stand; a saved single pools its own numbers;
     a member read elsewhere keeps the settings it was saved at. */
  function entryFor(key) {
    const c = candOf(key);
    if (c && !c.banked && c.kind !== 'single') return { key, params: singleParams() };
    const sm = (pool.savedMembers || []).find((x) => x.key === key);
    if (!c && sm && sm.banked === false) {
      return { key, params: (sm.pin || {}).params || singleParams() };
    }
    return { key };
  }

  /* Something about who is in changed: said in place (`membersRefresh`),
     not by repainting the page. */
  function touched() {
    pool.dirty = true;
    pool.fitErr = null;
    pool.refusal = null;
    membersRefresh();
  }

  /* A row's choice of answer. Ticked, it is swapped in where the other
     stood; unticked, it is what a tick will put in. */
  function setRecAnswer(rec, key) {
    if (!recSel(rec).length) {
      pool.pickSrc[rec.id] = key;
      syncRows();
    } else {
      toggleMember(key, true);
    }
    // The names on offer are the chosen versions'.
    swap('.rc-sel', selectBar());
  }

  /* One answer about the recording kept, the others taken out. */
  function keepOnly(rec, key) {
    const mine = recSel(rec);
    const keep = mine.find((m) => m.key === key) || mine[0];
    pool.sel = pool.sel.filter((m) => m === keep || mine.indexOf(m) < 0);
    touched();
  }

  /* The settings an unbanked member is fitted at: Single's, as they stand.
     Stated on the members card, because a pool whose members were fitted at
     different settings without saying so is not one question. */
  function singleParams() {
    const out = {};
    for (const k2 of PKEYS) out[k2] = asParam(k2, q[k2]);
    return out;
  }

  function typeFor(mk, fallback) {
    return pool.types[mk] || fallback || '';
  }

  /* In or out, ONE ANSWER PER RECORDING (2026-10-19): ticking an answer
     about a recording that already has one in swaps it in where the other
     stood; unticking takes every answer about it out. Said in place. */
  function toggleMember(key, on) {
    const rec = recOfKey(key);
    const mine = rec ? recSel(rec) : pool.sel.filter((m) => m.key === key);
    if (on) {
      if (mine.length === 1 && mine[0].key === key) return;
      const entry = entryFor(key);
      if (mine.length) {
        pool.sel = pool.sel.filter((m) => m === mine[0] || mine.indexOf(m) < 0);
        pool.sel.splice(pool.sel.indexOf(mine[0]), 1, entry);
      } else {
        pool.sel.push(entry);
      }
    } else {
      if (!mine.length) return;
      pool.sel = pool.sel.filter((m) => mine.indexOf(m) < 0);
    }
    touched();
  }

  /* ---------- choosing who is in the pool ---------- */
  const CATS = [
    ['group', 'group', (c) => c.group],
    ['subgroup', 'subgroup', (c) => c.subgroup],
    ['condition', 'condition', (c) => c.condition],
    ['project', 'project', (c) => c.project],
    ['kind', 'kind', (c) => (c.kind === 'single' ? 'saved'
                             : c.banked ? 'banked' : 'read here')],
  ];

  function facetValues(cs, f) {
    return Array.from(new Set(cs.map(f).filter((v) => v != null && v !== '')))
      .sort(natural);
  }

  /* A recording is shown when ANY of its answers fits each category
     pressed -- the kind chip "banked" shows every recording that has a
     banked answer -- and every word typed is somewhere in it. */
  function recShown(rec) {
    const f = pool.filt;
    for (const [key, _w, get] of CATS) {
      const want = f[key] || [];
      if (want.length && !rec.facts.some((c) => want.indexOf(get(c)) >= 0)) {
        return false;
      }
    }
    const text = String(f.q || '').trim().toLowerCase();
    if (text) {
      const hay = rec.facts.map((c) => [c.session_label, c.mouse_key, c.group,
                                         c.subgroup, c.condition, c.project,
                                         c.nickname, c.entry_id]
        .filter(Boolean).join(' ')).concat(rec.answers.map((a) => a.words))
        .join(' ').toLowerCase();
      if (text.split(/\s+/).some((w) => hay.indexOf(w) < 0)) return false;
    }
    return true;
  }

  /* The names a candidate's picked version holds. */
  function namesOf(c) {
    if (c.kind !== 'single') return [];
    const v = versionOfCand(c);
    return ((v && v.n_summary) || {}).names || [];
  }

  /* A name chip: every saved single holding that name, for that name's
     events only. Pressed again, the pool is every event again. It CHOOSES
     (2026-10-19), and Pool pools: choosing and looking are two screens now,
     and a chip that pooled on the choosing one fitted a picture nobody
     could see. */
  function pickName(nm, cs) {
    if (pool.name === nm) {
      pool.name = null;
      for (const m of pool.sel) delete m.names;
    } else {
      pool.name = nm;
      pool.sel = cs.filter((c) => namesOf(c).indexOf(nm) >= 0).map((c) => {
        const m = selOf(c);
        const want = pool.pickSrc[recOf(c)];
        const key = m ? m.key : (want && String(want).indexOf('s:' + c.artifact_id
          + ':') === 0 ? want : c.key);
        return { key, names: [nm] };
      });
    }
    swap('.rc-sel', selectBar());
    touched();
  }

  /* The search, the chips, and the tools that tick what is shown. Counted
     in RECORDINGS (2026-10-19), and "Select all shown" ticks one answer
     each -- the one its row offers. */
  function selectBar() {
    const cs = pool.cands || [];
    const f = pool.filt;
    const groups = CATS.map(([key, words, get]) => {
      const vals = facetValues(cs, get);
      if (vals.length < 2 && !(f[key] || []).length) return null;
      return el('div', { class: 'rc-sel-cat' }, [
        el('span', { class: 'rc-sel-k', text: words }),
      ].concat(vals.map((v) => BARRY.ui.button({ kind: 'mini',
        text: String(v), on: (f[key] || []).indexOf(v) >= 0,
        extra: 'rc-sel-chip',
        title: 'Show only ' + words + ' ' + v + ' (with any other '
             + words + ' pressed too).',
        onclick: () => {
          const have = f[key] || [];
          f[key] = have.indexOf(v) >= 0 ? have.filter((x) => x !== v)
                                        : have.concat([v]);
          swap('.rc-sel', selectBar());
          swap('.rc-pool-cands', membersTable());
        } }))));
    }).filter(Boolean);
    const names = Array.from(new Set([].concat(...cs.map(namesOf)))).sort();
    const recs = recordings();
    const nShown = recs.filter(recShown).length;
    return el('div', { class: 'rc-sel' }, [
      el('div', { class: 'rc-sel-top' }, [
        BARRY.ui.searchField({ placeholder: 'Find a recording, mouse or nickname',
          value: f.q, width: '22rem',
          title: 'Words in the session, the mouse, its group, condition or '
               + 'a saved version’s nickname -- every word has to match.',
          oninput: (ev2) => {
            f.q = ev2.target.value;
            swap('.rc-pool-cands', membersTable());
            shownCount();
          } }),
        el('span', { class: 'hint rc-sel-n', text: nShown + ' of '
                     + recs.length + ' recordings shown' }),
        el('span', { class: 'spacer' }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: 'Select all ' + nShown + ' shown', extra: 'rc-sel-all',
          title: 'Tick every recording the search and the chips show, one '
               + 'answer each: the one its row offers. Ones they hide keep '
               + 'whatever they had.',
          onclick: () => {
            for (const rec of recordings().filter(recShown)) {
              if (!recSel(rec).length) pool.sel.push(entryFor(curKey(rec)));
            }
            touched();
          } }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Unselect all',
          extra: 'rc-sel-none',
          title: 'Untick every recording, shown or not.',
          onclick: () => { pool.sel = []; pool.name = null; touched(); } }),
      ]),
      groups.length ? el('div', { class: 'rc-sel-cats' }, groups) : null,
      names.length ? el('div', { class: 'rc-sel-cat rc-sel-names' }, [
        el('span', { class: 'rc-sel-k', text: 'names' }),
      ].concat(names.map((nm) => BARRY.ui.button({ kind: 'mini', text: nm,
        on: pool.name === nm, extra: 'rc-name-chip',
        title: 'Tick every saved single holding a cluster named “' + nm
             + '”, for only those clusters’ events; Pool pools them. Press '
             + 'again for every event.',
        onclick: () => pickName(nm, cs) })))) : null,
    ].filter(Boolean));
  }

  /* The counts the search changes, where they stand. */
  function shownCount() {
    const box = host();
    if (!box) return;
    const recs = recordings();
    const n = recs.filter(recShown).length;
    const say = box.querySelector('.rc-sel-n');
    if (say) say.textContent = n + ' of ' + recs.length + ' recordings shown';
    const all = box.querySelector('.rc-sel-all');
    if (all) all.textContent = 'Select all ' + n + ' shown';
  }

  /* The recordings, one row each (2026-10-19), and under a row that holds
     two answers about one recording, the warning that its events would be
     counted twice, with a press to keep one. A tick changes its row where
     it stands: the table is not rebuilt (`syncRows`). */
  function membersTable() {
    const tb = el('tbody', {});
    for (const rec of recordings().filter(recShown)) {
      tb.appendChild(recRow(rec));
      const mine = recSel(rec);
      if (mine.length > 1) tb.appendChild(dupRow(rec, mine));
    }
    return el('table', { class: 'tbl rc-pool-cands' }, [
      el('thead', {}, [el('tr', {}, ['', 'recording', 'mouse', 'group',
                                     'condition', 'answer', 'events']
        .map((t) => el('th', { text: t })))]),
      tb,
    ]);
  }

  function recRow(rec) {
    const f = rec.facts[0] || {};
    const label = f.session_label || f.entry_id || rec.id;
    const fromSave = rec.answers.every((a) => a.kind === 'saved');
    const tr = el('tr', { class: 'rc-rec-row' + (fromSave ? ' rc-from-save' : ''),
                          'data-rec': rec.id }, [
      el('td', {}, [el('input', {
        type: 'checkbox', class: 'rc-pool-pick', 'aria-label': 'Pool ' + label,
        onchange: (ev2) => toggleMember(curKey(rec), ev2.target.checked),
      })]),
      el('td', { class: 'rc-rec-name', text: label,
        title: [f.session_label, f.group ? 'Group ' + f.group : null,
                f.subgroup ? 'Subgroup ' + f.subgroup : null,
                f.condition ? 'Condition ' + f.condition
                  + (f.condition_from ? ' (' + f.condition_from + ')' : '') : null,
                f.facts_from ? 'Group from the ' + f.facts_from : null]
          .filter(Boolean).join('\n') }),
      el('td', { text: f.mouse_key || '' }),
      el('td', { text: [f.group, f.subgroup && f.subgroup !== f.group
                        ? f.subgroup : null].filter(Boolean).join(' · ')
                       || typeFor(f.mouse_key, f.mouse_type) }),
      el('td', { text: f.condition || '' }),
      el('td', { class: 'rc-rec-answer' }),
      el('td', { class: 'rc-rec-n' }),
    ]);
    fillRow(tr, rec);
    return tr;
  }

  /* A row brought up to date in place: its tick, which answer it shows,
     the chips saying what that answer is, and its events. The choice is
     only rebuilt when its options change, so it keeps its focus. */
  function fillRow(tr, rec) {
    const mine = recSel(rec);
    const key = curKey(rec);
    const as = answersOf(rec);
    const a = answerOf(rec, key) || as[0];
    const sig = JSON.stringify([mine.map((m) => m.key), key,
                                as.map((x) => x.key)]);
    if (tr.__sig === sig) return;
    const optsSig = JSON.stringify(as.map((x) => x.key));
    const on = mine.length > 0;
    tr.classList.toggle('on', on);
    tr.dataset.key = key;
    const cb = tr.querySelector('.rc-pool-pick');
    if (cb && cb.checked !== on) cb.checked = on;
    const cell = tr.querySelector('.rc-rec-answer');
    const pick = cell && cell.querySelector('.rc-rec-src');
    if (cell && (!pick || tr.__opts !== optsSig)) {
      cell.innerHTML = '';
      const opt = (x) => el('option', { value: x.key, title: x.title || null,
                                        text: x.words });
      const now = as.filter((x) => !x.older);
      const old = as.filter((x) => x.older);
      /* Answers about earlier versions of the set -- banked from an older
         version, a read of older stamps -- under a fold of their own at the
         bottom (2026-10-20), so the ones about the set as it is come first. */
      cell.appendChild(as.length > 1
        ? el('select', {
            class: 'rc-in rc-rec-src',
            'aria-label': 'Which answer about '
                          + ((rec.facts[0] || {}).session_label || rec.id),
            onchange: (ev2) => setRecAnswer(rec, ev2.target.value),
          }, now.map(opt).concat(old.length ? [el('optgroup', {
            label: 'Older: about earlier versions of the set' },
            old.map(opt))] : []))
        : el('span', { class: 'rc-rec-one' }, [answerChip(a)]));
      cell.appendChild(el('span', { class: 'rc-rec-chips' }));
    }
    const sel2 = cell && cell.querySelector('.rc-rec-src');
    if (sel2) {
      if (sel2.value !== key) sel2.value = key;
      sel2.title = (a && a.title) || '';
    }
    const chips = cell && cell.querySelector('.rc-rec-chips');
    if (chips) {
      chips.innerHTML = '';
      for (const n of answerChips(a)) chips.appendChild(n);
    }
    const ev = tr.querySelector('.rc-rec-n');
    if (ev) ev.textContent = a && a.n != null ? String(a.n) : '';
    tr.__sig = sig;
    tr.__opts = optsSig;
    // Two answers about it in the pool: the warning under the row.
    const next = tr.nextElementSibling;
    const dup = next && next.classList.contains('rc-rec-dup') ? next : null;
    if (mine.length > 1 && tr.parentNode) {
      const d = dupRow(rec, mine);
      if (dup) dup.replaceWith(d); else tr.after(d);
    } else if (dup) {
      dup.remove();
    }
  }

  /* An answer that is the only one, said as a chip. */
  function answerChip(a) {
    if (!a) return null;
    if (a.kind === 'read') {
      return BARRY.ui.chip('read here, not banked', { flag: true, kind: 'warn',
                                                      title: a.title });
    }
    if (a.kind === 'saved') {
      return BARRY.ui.chip(a.member && a.member.banked ? 'banked' : 'not banked',
                           { flag: true, kind: a.member && a.member.banked
                             ? null : 'warn', title: a.title });
    }
    return BARRY.ui.chip(a.words, { flag: true, title: a.title });
  }

  /* What else is worth knowing about the answer shown: the filter a saved
     single was measured on, whether it has reached the shared tables, and
     where its read is when it is not here. */
  function answerChips(a) {
    if (!a) return [];
    const c = a.cand;
    const vv = a.kind === 'single' ? a.ver || (c ? versionOfCand(c) : null) : null;
    return [
      a.kind === 'single' && c && BARRY.syncState
        ? BARRY.syncState.mark('artifacts', c.artifact_id) : null,
      vv && vv.measure
        ? BARRY.ui.chip(String(vv.measure.filter_label || '').split(',')[0],
            { flag: true, extra: 'rc-cand-filter',
              title: vv.measure.filter_label }) : null,
      a.kind === 'banked' && c && c.filter_label
        ? BARRY.ui.chip(String(c.filter_label).split(',')[0],
            { flag: true, extra: 'rc-cand-filter', title: c.filter_label })
        : null,
      a.older
        ? BARRY.ui.chip('older version', { flag: true, kind: 'warn',
            extra: 'rc-cand-older', title: a.title }) : null,
      c && c.here === false
        ? BARRY.ui.chip('read elsewhere', { flag: true,
            title: 'Its numbers can be pooled; its traces are on another '
                 + 'machine, and Jarvis reads it here when they are asked '
                 + 'for.' }) : null,
      a.kind === 'saved'
        ? BARRY.ui.chip('read on ' + a.read_on, { flag: true,
            extra: 'rc-read-on', title: a.title }) : null,
    ].filter(Boolean);
  }

  /* The warning under a row holding two answers about one recording. */
  function dupRow(rec, mine) {
    const ws = mine.map((m) => (answerOf(rec, m.key) || { words: m.key }).words);
    const n = mine.length;
    return el('tr', { class: 'rc-rec-dup', 'data-rec': rec.id }, [
      el('td', { colspan: '7' }, [el('div', { class: 'rc-dup' }, [
        el('p', { class: 'rc-dup-say', text: 'This pool holds ' + n
          + ' answers about this one recording — ' + ws.join(' and ')
          + ' — so each of its events would be counted '
          + (n === 2 ? 'twice' : n + ' times') + '. Keep one:' }),
        el('div', { class: 'rc-dup-acts' }, mine.map((m, j) => BARRY.ui.button({
          kind: 'mini', extra: 'rc-dup-keep', text: 'Keep this one: ' + ws[j],
          title: 'Keeps ' + ws[j] + ' and takes the other answer'
               + (n === 2 ? '' : 's') + ' about this recording out of the pool.',
          onclick: () => keepOnly(rec, m.key) }))),
      ])]),
    ]);
  }

  /* Every row on screen brought up to date, in place. */
  function syncRows() {
    const box = host();
    const tb = box && box.querySelector('.rc-pool-cands tbody');
    if (!tb) return;
    recordings();
    for (const tr of Array.from(tb.querySelectorAll('tr.rc-rec-row'))) {
      const rec = recMemo.byId.get(tr.dataset.rec);
      if (rec) fillRow(tr, rec);
    }
  }

  /* Who is in changed, on the choosing screen: the rows, the card above,
     the mouse types, the refusal and the button, each where it stands --
     the list is not rebuilt, so it keeps its scroll and the search its
     cursor. Elsewhere, the card that counts them. */
  function membersRefresh() {
    const box = host();
    if (!box || viewMode !== 'pooled') return;
    if (pool.level === 'double') {
      swap('.rc-build-card', buildCard());
      swap('.rc-pools-foot', poolsFoot());
      swap('.rc-pools-refused', refusedPart('pools'));
      return;
    }
    if (!box.querySelector('.rc-members')) {
      swap('.rc-pool-card', openPoolCard());
      return;
    }
    syncRows();
    swap('.rc-build-card', buildCard());
    swap('.rc-from-save-box', fromSaveNote());
    swap('.rc-types-box', typesBox());
    swap('.rc-members-refused', refusedPart('members'));
    swap('.rc-members-foot', membersFoot());
  }

  function setType(mk, value, fallback) {
    const v = String(value || '').trim();
    if (!v || v === (fallback || '')) delete pool.types[mk];
    else pool.types[mk] = v;
    pool.dirty = true;
    membersRefresh();
  }

  function serverFocus() {
    const f = pool.focus;
    if (!f) return null;
    if (f.mouse_key) return { mouse_key: f.mouse_key };
    if (f.mouse_type) return { mouse_type: f.mouse_type };
    return null;            // a member focus is a dimming, not a second test
  }

  function poolBody() {
    if (pool.level === 'double') {
      return {
        pools: pool.sel.map((m) => {
          const parts = String(m.key).split(':');
          return { artifact_id: parts[1], version: Number(parts[2]) };
        }),
        mouse_types: Object.assign({}, pool.types),
        focus: serverFocus(),
        k: +q.k,
        complete_only: !!q.complete_only,
        cluster_calls: Object.assign({}, pool.cluster_calls),
        cluster_names: JSON.parse(JSON.stringify(pool.cluster_names || {})),
        margin: pool.margin ? Object.assign({}, pool.margin) : null,
        border: pool.border ? Object.assign({}, pool.border) : null,
        drawn: pool.drawn.map((g) => ({ events: g.events.map((x) => x.slice()),
                                        call: g.call })),
      };
    }
    return {
      all_ds: pool.all_ds || undefined,
      members: pool.sel.map((m) => Object.assign({ key: m.key },
        m.params ? { params: m.params } : {},
        (m.names && m.names.length) ? { names: m.names.slice() } : {})),
      mouse_types: Object.assign({}, pool.types),
      focus: serverFocus(),
      /* The SAME settings as Single: every member measured with them and
         the pool clustered with them. Banked members measured another way
         are re-measured from their reads, and marked. */
      measure: {
        filt: q.filt,
        mains_out: presetOf(q.filt) ? presetOf(q.filt).mains_out : !!q.mains_out,
        lo_hz: presetOf(q.filt) ? presetOf(q.filt).lo_hz : +q.lo_hz,
        hi_hz: presetOf(q.filt) ? presetOf(q.filt).hi_hz : +q.hi_hz,
        win_ms: +q.win_ms, cross_ms: +q.cross_ms,
        band_lo: +q.band_lo, band_hi: +q.band_hi,
      },
      k: +q.k,
      complete_only: !!q.complete_only,
      cluster_calls: Object.assign({}, pool.cluster_calls),
      cluster_names: JSON.parse(JSON.stringify(pool.cluster_names || {})),
      margin: pool.margin ? Object.assign({}, pool.margin) : null,
      border: pool.border ? Object.assign({}, pool.border) : null,
      drawn: pool.drawn.map((g) => ({ events: g.events.map((x) => x.slice()),
                                      call: g.call })),
      /* The saved version this pool was opened from. A member whose read is
         on another machine is pooled from it, as it was saved -- so a pool
         saved where its members were read works anywhere for everything
         that does not measure them again. */
      saved: pool.open && pool.open.source
        ? Object.assign({}, pool.open.source) : null,
    };
  }

  function measureSig() {
    const b = poolBody();
    return JSON.stringify([b.members.map((m) => m.key).sort(), b.measure]);
  }

  async function measuresAgreed() {
    const sig = measureSig();
    if (pool.measureOk === sig) return true;
    let got;
    try {
      got = await apiPost('/api/rootcanal/pool/measures', {
        members: poolBody().members, measure: poolBody().measure,
        saved: poolBody().saved });
    } catch (e) {
      return true;          // no answer: the pool says what it can't do
    }
    if (!got.mismatch) { pool.measureOk = sig; return true; }
    // Waiting on a person now, not on the pool.
    pool.fitting = false;
    tickBusy();
    return measureDialog(got);
  }

  /* The table of who was measured how, and the choice of one for all. */
  function measureDialog(got) {
    return new Promise((resolve) => {
      const words = (m) => m.filter_label + ' · ±' + hz(m.win_ms)
        + ' ms · search ±' + hz(m.cross_ms) + ' ms · ' + hz(m.band_lo) + '–'
        + hz(m.band_hi) + ' Hz';
      const choose = async (m) => {
        closeModal();
        // The bar takes the chosen measurement, so Single and Pooled agree.
        for (const k2 of ['filt', 'mains_out', 'lo_hz', 'hi_hz', 'win_ms',
                          'cross_ms', 'band_lo', 'band_hi']) {
          if (m[k2] != null) { q[k2] = asParam(k2, m[k2]); pend[k2] = q[k2]; }
        }
        swapTop();
        let rep;
        try {
          rep = await apiPost('/api/rootcanal/pool/remeasure', {
            members: poolBody().members, measure: poolBody().measure });
        } catch (e) {
          toast('The singles could not be measured again: ' + e.message,
                'err', 10000);
          resolve(false);
          return;
        }
        for (const d of rep.done || []) {
          const sm = pool.sel.find((x) => x.key === d.key);
          if (sm) sm.key = d.new_key;
        }
        if ((rep.done || []).length) {
          toast((rep.done.length) + ' single' + (rep.done.length === 1
            ? ' was' : 's were') + ' measured again as a new version: '
            + rep.done.map((d) => d.label).join(', ') + '.', 'ok', 10000);
          loadPool();
        }
        if ((rep.away || []).length) {
          toast(rep.away.length + ' could not be: '
            + rep.away.map((a) => a.label + ' (read on '
              + (a.read_on || 'another machine') + ')').join(', ')
            + '. Take ' + (rep.away.length === 1 ? 'it' : 'them')
            + ' out, or measure ' + (rep.away.length === 1 ? 'it' : 'them')
            + ' on the machine that read ' + (rep.away.length === 1
              ? 'it' : 'them') + '.', 'warn', 15000);
        }
        pool.measureOk = measureSig();
        resolve(!(rep.away || []).length);
      };
      const target = got.target;
      const others = (got.distinct || []).filter((m) => words(m) !== words(target));
      showModal(el('div', { class: 'rc-measure-dlg' }, [
        el('div', { class: 'mh' }, [
          el('h3', { text: 'One measurement for the whole pool' }),
          el('div', { class: 'spacer' })]),
        el('div', { class: 'mb' }, [el('div', { class: 'rc-ask' }, [
          el('p', { text: 'These members were not all measured the way the '
            + 'pool asks (' + words(target) + '). Amplitude and half-width '
            + 'measured on two filters are two measurements under one axis, '
            + 'so they all have to be one. Choose which; each saved single '
            + 'measured another way is measured again to it as a new version, '
            + 'where its read is on this machine.' }),
          el('table', { class: 'tbl rc-measure-tbl' }, [
            el('thead', {}, [el('tr', {}, ['member', 'kind', 'measured',
                                           'read'].map((t) => el('th', { text: t })))]),
            el('tbody', {}, (got.members || []).map((r) => el('tr', {
              class: r.same ? '' : 'rc-measure-diff' }, [
              el('td', { text: r.label }),
              el('td', { text: r.kind }),
              el('td', { text: words(r.measure) + (r.same ? '' : ' (differs)') }),
              el('td', { text: r.here ? 'here' : 'on ' + (r.read_on
                                                            || 'another machine') }),
            ]))),
          ]),
        ])]),
        BARRY.ui.modalFoot([
          BARRY.ui.button({ kind: 'ghost', text: 'Cancel', extra: 'rc-measure-cancel',
            onclick: () => { closeModal(); resolve(false); } }),
        ], others.map((m) => BARRY.ui.button({ kind: 'ghost',
          text: 'All on ' + m.filter_label.split(',')[0], extra: 'rc-measure-other',
          title: words(m), onclick: () => choose(m) })).concat([
          BARRY.ui.button({ kind: 'primary', extra: 'rc-measure-bar',
            text: 'All on ' + target.filter_label.split(',')[0],
            title: 'The settings bar’s: ' + words(target),
            onclick: () => choose(target) }),
        ])),
      ]), { replace: true });
    });
  }

  /* THE POOL'S IDENTITY BACK INTO ITS SINGLES (2026-10-06): after a pool is
     saved, a new version of each of its singles carrying the pooled call
     and name of every event -- yes by default. */
  function propagateDialog(rep) {
    const n = pool.sel.length;
    showModal(el('div', { class: 'rc-prop-dlg' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'New versions of the ' + n + ' single'
                         + (n === 1 ? '' : 's') + '?' }),
        el('div', { class: 'spacer' })]),
      el('div', { class: 'mb' }, [el('div', { class: 'rc-ask' }, [
        el('p', { text: 'Each member gets a new version of its single with '
          + 'this pool’s identity: every event called and named as the pool '
          + 'called it, at the pool’s measurement, named “from pool ‘'
          + rep.nickname + '’ v' + rep.version + '”.' }),
        el('ul', {}, [
          el('li', { text: 'Each event keeps the call the pool gave it: the '
            + 'nearest of the pool’s centres, on the pool’s scale, is how the '
            + 'pool placed it.' }),
          el('li', { text: 'A cluster drawn by hand is not a centre: its '
            + 'events go to the nearest one.' }),
          el('li', { text: 'A saved single whose read is elsewhere is done '
            + 'from its saved numbers. Nothing goes to the Event Bank.' }),
        ]),
      ])]),
      BARRY.ui.modalFoot([], [
        BARRY.ui.button({ kind: 'ghost', text: 'Not now', extra: 'rc-prop-no',
          onclick: closeModal }),
        BARRY.ui.button({ kind: 'primary', text: 'Make the new versions',
          extra: 'rc-prop-yes',
          onclick: async () => {
            closeModal();
            let got;
            try {
              got = await apiPost('/api/rootcanal/pool/propagate',
                Object.assign(poolBody(), { pool: {
                  artifact_id: rep.artifact_id, version: rep.version,
                  nickname: rep.nickname } }));
            } catch (e) {
              toast('No new versions were made: ' + e.message, 'err', 12000);
              return;
            }
            const left = (got.results || []).filter((r) => !r.ok);
            toast(got.made + ' new version' + (got.made === 1 ? '' : 's')
              + ' made with this pool’s identity'
              + (left.length ? '; ' + left.length + ' left: '
                 + left.map((r) => r.why).join('; ') : '') + '.',
              left.length ? 'warn' : 'ok', 14000);
            BARRY.activity.log('rootcanal.pool_propagate', {
              artifact: rep.artifact_id, version: rep.version,
              made: got.made, left: left.length });
            loadPool();
          } }),
      ]),
    ]), { replace: true });
  }

  function poolMemberByKey(key) {
    return ((pool.fit && pool.fit.members) || []).find((m) => m.key === key)
      || null;
  }

  async function runPool() {
    if (!pool.sel.length) {
      toast('Tick at least one recording to pool.', 'warn', 5000);
      return null;
    }
    /* ONE MEASUREMENT (2026-10-06): before a pool is fitted, its saved and
       banked members are asked how they were measured. Where they differ
       from each other or from the settings bar, the person chooses which
       one they all take, and the saved singles are measured again to it as
       new versions -- asked once per members-and-measurement, not on every
       press. */
    // Busy at once, so the press is answered before the question is asked.
    pool.fitting = true;
    tickBusy();
    if (pool.level !== 'double' && !(await measuresAgreed())) {
      pool.fitting = false;
      tickBusy();
      render();
      return null;
    }
    const mine = ++pool.gen;
    const body = poolBody();
    pool.lastBody = body;
    /* A pooled dot's id is its place in the pool, which a refit can move
       (complete events only, a member in or out): dots drawn round are let
       go rather than left pointing at different ones. */
    pool.lassoSel = [];
    pool.fitting = true;
    tickBusy();
    let got;
    try {
      got = await apiPost(pool.level === 'double' ? '/api/rootcanal/dpool/fit'
                                                  : '/api/rootcanal/pool/fit',
                          body);
    } catch (e) {
      if (mine !== pool.gen) return null;
      pool.fitting = false;
      /* A REFUSAL IS ABOUT THE MEMBERS, so it is said beside them -- members
         measured over different HF bands, most often, which cannot share
         one power axis. The picture that was on screen stays: it is still
         the answer for the members it was drawn from. */
      /* Refused carried calls are theirs, not the pool's: taken off, said
         in a toast, and the pool fitted afresh. */
      if (body.border && /^The border /.test(e.message)) {
        pool.borderErr = e.message;
        pool.border = null;
        pool.fitting = false;
        render();
        return runPool();
      }
      if (body.margin && MARGIN_REFUSAL.test(e.message)) {
        pool.marginErr = e.message;
        pool.margin = null;
        toast('Pooled afresh: the calls this pool carried could not be used '
              + 'here. ' + e.message, 'warn', 10000);
        pool.fitting = false;
        render();
        return runPool();
      }
      pool.fitErr = e.message;
      /* A refusal about PARTICULAR members names them (2026-10-19): ones
         read elsewhere that would have to be measured again, or the second
         answer about one recording. The panel then offers to fix exactly
         those -- read them here, or take the copy out. */
      const away = (e.data && e.data.away) || [];
      pool.refusal = away.length ? { error: e.message, away: away.slice(),
                                     from: 'fit' } : null;
      if (!pool.fit || !pool.fit.ok) pool.fit = { ok: false, error: e.message };
      /* MEMBERS THAT ONLY NEED READING HERE ARE READ (2026-10-19). Changing
         the filter on a pool with members read on another machine was a red
         error -- "3 members of this pool were measured another way and read
         on Strawbarry..." -- for something Jarvis can simply do. So the
         reads start by themselves, said calmly, and the pool fits again when
         they land. Once per request: when reading did not fix it, the
         refusal and its button stay, with the reasons. */
      const toRead = readKeys(pool.refusal);
      const ask = JSON.stringify([toRead.slice().sort(), body.measure || null,
                                  body.band || null]);
      if (toRead.length && toRead.length === away.length
          && pool.autoRedoFor !== ask) {
        pool.autoRedoFor = ask;
        toast('Reading ' + toRead.length + ' recording'
              + (toRead.length === 1 ? '' : 's') + ' here so '
              + (toRead.length === 1 ? 'it' : 'they') + ' can be measured the '
              + 'pool’s way -- ' + (toRead.length === 1 ? 'its read was' : 'their '
              + 'reads were') + ' made on another machine. The pool fits again '
              + 'when ' + (toRead.length === 1 ? 'it lands' : 'they land') + '.',
              null, 9000);
        render();
        startRedo();
        return null;
      }
      toast(e.message, 'err', 10000);
      render();
      return null;
    }
    if (mine !== pool.gen) return null;
    pool.fitting = false;
    pool.fitErr = null;
    pool.refusal = null;
    pool.fit = got;
    pool.saved = false;
    pool.dirty = false;
    pool.evs = null;
    if (pool.picked != null && pool.picked >= (got.events || []).length) {
      pool.picked = null;
    }
    pool.evData = null;
    pool.evFor = null;
    BARRY.activity.log('rootcanal.pool_fit', {
      // A pool of pools names its pools, not its members.
      members: (body.members || []).length,
      pools: body.pools ? body.pools.length : undefined, focus: body.focus,
    });
    render();
    if (pool.picked != null) loadPoolEvent();
    else autoPick();
    return got;
  }

  /* THE FOUR EVENT CHARTS AT ONCE (2026-10-19): "any time a pool is
     created, render the 4 charts as soon as pooling is pulled up". They
     waited for a dot to be clicked, so a pool came up as a cloud beside
     four empty boxes. Now, when nothing is picked, the event nearest the
     centre of its own cluster is -- the most typical dot there is, of the
     first cluster, from a recording whose read is here when there is one,
     so its traces draw straight away rather than starting a read. Picking
     another dot works as it always did. */
  function autoPick() {
    const f = pool.fit;
    if (!f || !f.ok || pool.picked != null) return;
    const evs = poolEvents();
    if (!evs.length) return;
    const cents = f.centres || [];
    const dist = (e) => {
      const c = cents.find((x) => x.cls === e.cls_pool) || cents[0];
      if (!c || !e.z || !c.z) return Infinity;
      let d = 0;
      for (let a = 0; a < 3; a++) {
        const v = e.z[a], w = c.z[a];
        if (v == null || !isFinite(v) || w == null || !isFinite(w)) return Infinity;
        d += (v - w) * (v - w);
      }
      return d;
    };
    let best = -1, bestD = Infinity, bestHere = false;
    evs.forEach((e, j) => {
      const here = memberHere(poolMember(e));
      const d = dist(e);
      // Here beats elsewhere; then nearer beats farther.
      if ((here && !bestHere) || (here === bestHere && d < bestD)) {
        best = j; bestD = d; bestHere = here;
      }
    });
    if (best >= 0) poolPick(best);
  }

  /* The pool's events, in the shape the shared renderer draws: `i` is the
     dot's place in the pool, `cls` the POOLED call, and the single call
     and the switch carried beside it. Built once per answer. */
  function poolEvents() {
    const f = pool.fit;
    if (!f || !f.ok) return [];
    if (pool.evsFor === f && pool.evs) return pool.evs;
    pool.evsFor = f;
    pool.evs = (f.events || []).map((e, j) => Object.assign({}, e, {
      i: j, src_i: e.i,
      cls: e.cls_pool != null ? e.cls_pool : null,
      flipped: false,
      missing: e.missing || KEYS.filter((k2) => e[k2] == null || !isFinite(e[k2])),
    }));
    return pool.evs;
  }

  function poolMember(e) {
    return e && pool.fit && pool.fit.ok ? (pool.fit.members || [])[e.m] || null
                                        : null;
  }

  /* ---------- colour by ---------- */
  const COLOURS = [
    ['pool', 'pooled call'], ['single', 'single call'], ['switches', 'switches'],
    ['recording', 'recording'], ['mouse', 'mouse'], ['type', 'mouse type'],
    ['border', 'border'],
  ];
  /* The categorical palette is the theme's own (`--c1`..`--c4`, what
     `BARRY.hues` hands out once its neutral is dropped). Past four the
     colours come round again, and the SHAPE changes each time they do, so
     the fifth recording is not the first one's twin. */
  const CAT_N = 4;
  const CAT_SHAPES = [null, 'tri', 'itri'];
  const CAT_SHAPE_WORDS = ['circle', 'triangle', 'inverted triangle'];

  function catKey(e, mode) {
    if (mode === 'recording') {
      const m = poolMember(e);
      return m ? m.key : String(e.m);
    }
    if (mode === 'mouse') return e.mouse_key || '?';
    if (mode === 'type') return e.mouse_type || 'no type';
    return null;
  }

  function catName(key, mode) {
    if (mode === 'recording') {
      const m = ((pool.fit && pool.fit.members) || []).find((x) => x.key === key);
      return m ? memberName(m) : key;
    }
    return key;
  }

  /* Worked out once per answer and mode: every dot asks for its colour on
     every draw, and a list rebuilt per dot is a pool's events squared. */
  let catMemo = { fit: null, mode: null, list: [], at: new Map() };

  function catList(mode) {
    if (['recording', 'mouse', 'type'].indexOf(mode) < 0) return [];
    if (catMemo.fit === pool.fit && catMemo.mode === mode) return catMemo.list;
    let list;
    if (mode === 'recording') {
      list = ((pool.fit && pool.fit.members) || []).map((m) => m.key);
    } else {
      const seen = new Set();
      for (const e of poolEvents()) seen.add(catKey(e, mode));
      list = Array.from(seen).sort(natural);
    }
    catMemo = { fit: pool.fit, mode, list,
                at: new Map(list.map((k2, j) => [k2, j])) };
    return list;
  }

  function catStyle(key, mode) {
    catList(mode);
    const at = Math.max(0, catMemo.at.has(key) ? catMemo.at.get(key) : 0);
    return { fill: tok('--c' + ((at % CAT_N) + 1)),
             shape: CAT_SHAPES[Math.floor(at / CAT_N) % CAT_SHAPES.length],
             at };
  }

  function switchKind(e) {
    if (e.cls_pool == null || e.cls_single == null) return 'none';
    if (!e.switched) return 'same';
    return e.cls_single === 'ds' ? 'd2i' : 'i2d';
  }

  function poolFill(e) {
    const mode = pool.colour;
    if (mode === 'border') {
      return pool.fit && pool.fit.border_used ? borderCol(e, e.cls_pool)
                                              : colOf(e.cls_pool);
    }
    if (mode === 'single') return colOf(e.cls_single);
    if (mode === 'switches') {
      const sk = switchKind(e);
      return sk === 'd2i' ? tok('--warn') : sk === 'i2d' ? tok('--accent')
           : tok('--text-2');
    }
    if (mode === 'recording' || mode === 'mouse' || mode === 'type') {
      return catStyle(catKey(e, mode), mode).fill;
    }
    return colOf(e.cls_pool);
  }

  function poolShape(e) {
    const mode = pool.colour;
    if (mode === 'recording' || mode === 'mouse' || mode === 'type') {
      return catStyle(catKey(e, mode), mode).shape;
    }
    return null;
  }

  /* ---------- focus ---------- */
  function inFocus(e) {
    const f = pool.focus;
    if (!f) return true;
    if (f.mouse_key) return e.mouse_key === f.mouse_key;
    if (f.mouse_type) return e.mouse_type === f.mouse_type;
    if (f.member) { const m = poolMember(e); return !!m && m.key === f.member; }
    return true;
  }

  function focusName(f) {
    const g = f || pool.focus;
    if (!g) return '';
    if (g.mouse_key) return 'mouse ' + g.mouse_key;
    if (g.mouse_type) return 'type ' + g.mouse_type;
    if (g.member) {
      const m = ((pool.fit && pool.fit.members) || []).find((x) => x.key === g.member);
      return m ? memberName(m) : g.member;
    }
    return '';
  }

  /* The dim goes on at once; the focused mouse's own GMM line is the
     server's, so a mouse or a type is asked for again. A recording focus is
     a dimming only -- the spec's second test is per mouse and per type. */
  const focusSoon = debounce(() => {
    if (pool.fit && pool.fit.ok && !pool.dirty) runPool();
  }, 600);

  function setFocus(f) {
    const had = serverFocus();
    pool.focus = f && (f.mouse_key || f.mouse_type || f.member) ? f : null;
    render();
    /* The dim is immediate; the focused test is the server's and a cold pool
       is half a minute, so it waits for the choice to settle and says it is
       running. Only when the question changed: a recording focus asks the
       server nothing new. */
    if (JSON.stringify(had) !== JSON.stringify(serverFocus())) focusSoon();
  }

  function setColour(mode) {
    if (!COLOURS.some(([id]) => id === mode)) return;
    pool.colour = mode;
    swap('.rc-legend', poolLegend());
    drawMain();
  }

  /* ---------- the scene the shared renderer draws ---------- */
  function poolScene() {
    const f = pool.fit;
    if (!f || !f.ok) return null;
    const ax = (f.axes || [])[2] || {};
    return {
      kind: 'pooled',
      events: poolEvents(),
      centres: (f.centres || []).map((c, k2) => ({
        k: k2, cls: c.cls, n: c.n, z: (c.z || []).slice(),
        raw: (c.raw || []).slice() })),
      fitCentres: f.centres || [],
      params: { hf_label: ax.label ? ax.label + (ax.unit ? ' · ' + ax.unit : '')
                                   : hfLabel(DEF) },
      picked: pool.picked,
      fill: poolFill,
      outside: (e) => pool.colour === 'border' && !!(pool.fit
                      && pool.fit.border_used) && e.border === 'amb',
      shape: poolShape,
      centreFill: (c) => cluFill(c.k, c.cls),
      alpha: (e) => (inFocus(e) ? 1 : 0.12),
      /* Ringed where pooling changed its mind, in every colour mode. */
      ringed: (e) => !!e.switched,
      draggable: false,
      onPick: poolPick,
    };
  }

  function poolPicked() {
    if (pool.picked == null) return null;
    const e = poolEvents()[pool.picked];
    if (!e) return null;
    const tr = pool.evFor === pool.picked && pool.evData && pool.evData.trace;
    return Object.assign({}, e, { contact: tr ? tr.contact : null,
                                  polarity: tr ? tr.polarity : null });
  }

  function poolPick(j) {
    const evs = poolEvents();
    if (!evs[j]) return;
    pool.picked = j;
    swap('.rc-pickbar', poolPickBar());
    swap('.rc-event', eventPane());
    drawAll();
    loadPoolEvent();
    followXplore();
  }

  function poolStep(d) {
    const evs = poolEvents();
    if (!evs.length) return;
    const at = pool.picked == null ? (d > 0 ? -1 : 0) : pool.picked;
    poolPick(((at + d) % evs.length + evs.length) % evs.length);
  }

  /* The click panel, for a pooled dot: the same /api/rootcanal/event Single
     calls, with that member's entry, read and settings. A banked member
     whose read was made on another machine has its numbers here and its
     trace there -- said in a sentence, never left as an empty panel. */
  function eventBodyFor(e) {
    const m = poolMember(e);
    if (!m) return null;
    if (m.event_body) return Object.assign({}, m.event_body, { i: e.src_i });
    const pin = m.pin || {};
    return Object.assign({ entry_id: m.entry_id }, pin.params || {}, {
      read: pin.read || null,
      from_version: pin.from_version !== undefined ? pin.from_version
                   : (pin.ds_version !== undefined ? pin.ds_version : null),
      i: e.src_i,
    });
  }

  function memberHere(m) {
    if (!m) return false;
    // Read here since the pool was fitted (2026-10-19).
    const R = evRedoOf(m);
    if (R && R.landed) return true;
    // The server's own word: no request body means no read here to ask.
    if (Object.prototype.hasOwnProperty.call(m, 'event_body')
        && m.event_body == null) return false;
    if (m.here === false) return false;
    const c = candOf(m.key);
    return !(c && c.here === false);
  }

  function awayText(m) {
    return 'This recording’s read is not on this machine'
      + (m && m.read_on ? ': it was read on ' + m.read_on : '')
      + ', so its pooled numbers are here and its trace is not.';
  }

  /* ==================================================================
     READING A MEMBER AGAIN, HERE (2026-10-19)

     A member read on another machine pools from its numbers, but cannot
     be measured another way, and its traces are not here. The panel used
     to say so and stop -- "read that set on this machine in Single" --
     and a save measured the pool's way was refused outright. Now Jarvis
     reads it again itself: `/api/rootcanal/pool/reread` finds the
     recording the way every tool does (a drive on this computer first,
     the VACC second) and reads it exactly as it was read there -- the
     same set, the same stamps, so the same read. A job per saved pool the
     members come from (a pool of pools' members each belong to one), each
     polled until it ends, one row per member: its step, its channels done
     of how many, and whether it is on this computer or the VACC.
     ================================================================== */
  const REREAD_OVER = ['done', 'failed', 'canceled', 'error'];

  function rereadRun(asks, onPaint, onEnd) {
    const R = { asks, groups: [], state: 'sending', poll: null, ended: false,
                landed: false };
    for (const a of asks) {
      const sk = JSON.stringify(a.saved || null);
      let g = R.groups.find((x) => x.sk === sk);
      if (!g) {
        g = { sk, saved: a.saved || null, asks: [], job: null, here: [],
              refused: [], err: null, lost: 0 };
        R.groups.push(g);
      }
      g.asks.push(a);
    }
    const live = (g) => !!(g.job && !g.err
                           && REREAD_OVER.indexOf(g.job.status) < 0);
    const end = () => {
      if (R.ended) return;
      R.ended = true;
      R.state = 'ended';
      if (R.poll) { clearInterval(R.poll); R.poll = null; }
      R.landed = rereadRows(R).some((x) => x.status === 'done'
                                           || x.status === 'here');
      onPaint(R);
      onEnd(R);
    };
    R.live = () => R.groups.some(live);
    R.stop = () => {
      R.stopping = true;
      for (const g of R.groups.filter(live)) {
        apiPost('/api/cfc/job/' + encodeURIComponent(g.job.id) + '/cancel', {})
          .catch(() => {});
      }
      onPaint(R);
    };
    (async () => {
      await Promise.all(R.groups.map(async (g) => {
        try {
          const got = await apiPost('/api/rootcanal/pool/reread', {
            members: g.asks.map((a) => ({ key: a.key })), saved: g.saved });
          g.job = got.job || null;
          g.here = got.here || [];
          g.refused = got.refused || [];
        } catch (e) {
          g.err = e.message;
        }
      }));
      if (R.ended) return;
      if (!R.live()) { end(); return; }
      R.state = 'running';
      onPaint(R);
      let busy = false;
      R.poll = setInterval(async () => {
        if (busy || R.ended) return;
        busy = true;
        try {
          for (const g of R.groups.filter(live)) {
            try {
              const got = await api('/api/cfc/job/' + encodeURIComponent(g.job.id));
              g.job = got.job || g.job;
              g.lost = 0;
            } catch (e) {
              // A job the server no longer knows is not waited on for ever.
              g.lost += 1;
              if (g.lost >= 6) g.err = 'Jarvis lost track of the read: ' + e.message;
            }
          }
        } finally {
          busy = false;
        }
        if (R.ended) return;
        if (!R.live()) end(); else onPaint(R);
      }, 900);
    })();
    return R;
  }

  /* One row per member asked about, whatever has happened to it. */
  function rereadRows(R) {
    const out = [];
    for (const g of R.groups) {
      const jm = (g.job && g.job.members) || [];
      const over = g.job && REREAD_OVER.indexOf(g.job.status) >= 0;
      for (const a of g.asks) {
        const row = { id: a.id, key: a.key, label: a.label || a.key,
                      status: 'waiting' };
        const ref = g.refused.find((x) => x.key === a.key);
        const m = jm.find((x) => x.id === a.key);
        if (ref) Object.assign(row, { status: 'failed', error: ref.why });
        else if (g.here.indexOf(a.key) >= 0) row.status = 'here';
        else if (m) {
          Object.assign(row, { label: m.label || row.label,
                               status: m.status || 'waiting', step: m.step,
                               done: m.done, of: m.of, where: m.where,
                               error: m.error });
        }
        if (g.err && row.status !== 'done' && row.status !== 'here'
            && row.status !== 'failed') {
          Object.assign(row, { status: 'failed', error: g.err });
        } else if (over && (row.status === 'waiting' || row.status === 'running')) {
          row.status = g.job.status === 'canceled' ? 'stopped' : 'failed';
          if (row.status === 'failed' && !row.error) {
            row.error = (g.job && g.job.error) || 'the read ended without it';
          }
        }
        out.push(row);
      }
    }
    return out;
  }

  function rereadWhere(x) {
    return x.where === 'vacc' ? 'on the VACC'
      : x.where === 'here' ? 'on this computer' : null;
  }

  function rereadWords(x) {
    if (!x) return 'getting ready';
    if (x.status === 'here') return 'already read here — nothing to read';
    if (x.status === 'done') {
      return 'read again' + (rereadWhere(x) ? ' ' + rereadWhere(x) : '')
        + ' — its read is here now';
    }
    if (x.status === 'failed') return 'could not be read: ' + (x.error || 'no reason given');
    if (x.status === 'stopped') return 'stopped part-way; nothing of it kept';
    if (x.status === 'running') {
      return [x.step || 'reading',
              x.of ? Math.min(Number(x.done) || 0, x.of) + ' of ' + x.of
                     + ' channels done' : null,
              rereadWhere(x)].filter(Boolean).join(' · ');
    }
    return 'waiting its turn';
  }

  /* The rows, as the house draws a batch (Doppler's `dop-batch`): a dot
     for its state, the name, and what it is doing in words. */
  function rereadList(R) {
    return el('div', { class: 'dop-batch rc-redo-rows' }, rereadRows(R).map((x) => {
      const st = x.status === 'here' ? 'done' : x.status;
      return el('div', { class: 'dop-batch-row rc-redo-row ' + st,
                         'data-mid': x.id }, [
        el('span', { class: 'dop-batch-dot', 'aria-hidden': 'true' }),
        el('span', { class: 'dop-batch-name', text: x.label }),
        el('span', { class: 'dop-batch-state rc-redo-state', text: rereadWords(x) }),
      ]);
    }));
  }

  /* What a pool member is asked about as. At the second level a member is
     a recording INSIDE one of the saved pools: asked for by its key in
     that pool, with that pool's version (`pin.pool`). */
  function askOfMember(m) {
    const pp = (m && m.pin && m.pin.pool) || null;
    if (pp && pp.member) {
      return { id: m.key, key: pp.member, label: m.session_label || pp.member,
               saved: { artifact_id: pp.artifact_id, version: pp.version } };
    }
    return { id: m.key, key: m.key, label: m.session_label || m.key,
             saved: pool.open && pool.open.source
               ? Object.assign({}, pool.open.source) : null };
  }

  const askId = (a) => a.key + '@' + (a.saved ? a.saved.artifact_id + ':'
                                                + a.saved.version : '');

  /* THE CLICK PANEL READS IT ITSELF: a dot whose member is read elsewhere
     starts its read here at once -- once per member per page load, so a
     dot pressed again does not start a second -- and the event opens
     when it lands. */
  const evRedo = new Map();

  function evRedoOf(m) {
    return m ? evRedo.get(askId(askOfMember(m))) || null : null;
  }

  function startEvRedo(m, again) {
    const a = askOfMember(m);
    const id = askId(a);
    if (evRedo.has(id) && !again) return evRedo.get(id);
    const R = rereadRun([a], paintEvNote, () => {
      const e = poolPicked();
      const now = e ? poolMember(e) : null;
      if (R.landed) refreshCandsQuietly();
      if (R.landed && now && now.key === m.key) { loadPoolEvent(); return; }
      if (now && now.key === m.key) drawEvent();
    });
    evRedo.set(id, R);
    return R;
  }

  /* What the click panel says about a member read elsewhere, above its
     four pictures: in words that wrap, never drawn into a canvas, where a
     sentence is cut off at the canvas's edge. */
  function awayNote(m) {
    const R = evRedoOf(m);
    const x = R ? rereadRows(R)[0] : null;
    let say;
    if (!R || R.state === 'sending') {
      say = 'Reading it here, so its trace can be drawn: Jarvis looks for the '
        + 'recording on this computer’s drives first and on the VACC after, '
        + 'and reads it exactly as it was read there.';
    } else if (!R.ended) {
      say = 'Reading it here: ' + rereadWords(x) + '.';
    } else if (R.landed) {
      say = 'Read here. Opening the event…';
    } else {
      say = 'It could not be read here: ' + (x && x.status === 'stopped'
        ? 'it was stopped' : (x && x.error) || 'no reason given') + '. Its '
        + 'pooled numbers are still in the pool; its trace opens on the machine '
        + 'that read it.';
    }
    return el('div', { class: 'rc-ev-note' }, [
      el('p', { class: 'rc-ev-why rc-ev-away', text: awayText(m) }),
      el('p', { class: 'rc-ev-progress', text: say }),
      R && !R.ended ? BARRY.ui.button({ kind: 'mini', text: 'Stop',
        extra: 'rc-ev-stop', disabled: !!R.stopping,
        title: 'Stop reading it. Nothing of a part-read set is kept.',
        onclick: () => R.stop() }) : null,
      R && R.ended && !R.landed ? BARRY.ui.button({ kind: 'mini',
        text: 'Try again', extra: 'rc-ev-retry',
        title: 'Ask for its read here once more.',
        onclick: () => { startEvRedo(m, true); paintEvNote(); } }) : null,
    ].filter(Boolean));
  }

  function poolEventNote() {
    const e = poolPicked();
    if (!e) return null;
    const m = poolMember(e);
    if (m && !memberHere(m)) return awayNote(m);
    if (pool.evFor === pool.picked && pool.evData && pool.evData.ok === false
        && pool.evData.error) {
      return el('div', { class: 'rc-ev-note' }, [
        el('p', { class: 'rc-ev-why rc-ev-away', text: pool.evData.error })]);
    }
    return null;
  }

  function paintEvNote() {
    swap('.rc-ev-note', poolEventNote() || el('div', { class: 'rc-ev-note' }));
  }

  /* Whether the picked dot's trace is on its way: its canvases say
     "reading…" until it lands, and "no trace" if it cannot. */
  function evComing() {
    const e = poolPicked();
    const m = e ? poolMember(e) : null;
    if (!m || memberHere(m)) return false;
    const R = evRedoOf(m);
    return !R || !R.ended;
  }

  /* The candidates again, without repainting the picture: what was read
     here is offered as here now. */
  function refreshCandsQuietly() {
    api('/api/rootcanal/pool/candidates').then((got) => {
      pool.cands = got.singles || [];
      pool.candsErr = null;
      if (poolScreen() === 'build') render();
    }).catch(() => { /* the list keeps what it had */ });
  }

  const loadPoolEvent = debounce(async function loadPoolEvent_() {
    const j = pool.picked;
    const e = poolPicked();
    if (!e) return;
    const m = poolMember(e);
    if (!memberHere(m)) {
      pool.evData = { ok: false, away: true };
      pool.evFor = j;
      if (m) startEvRedo(m);
      swap('.rc-event', eventPane());
      drawEvent();
      return;
    }
    const mine = ++pool.evGen;
    pool.evBusy = true;
    tickBusy();
    let got;
    try {
      got = await apiPost('/api/rootcanal/event', eventBodyFor(e));
    } catch (err) {
      if (mine !== pool.evGen) return;
      got = { ok: false, error: 'Its trace could not be read here: '
                                + err.message };
    }
    if (mine !== pool.evGen) return;
    pool.evBusy = false;
    pool.evData = got;
    pool.evFor = j;
    tickBusy();
    swap('.rc-pickbar', poolPickBar());
    swap('.rc-event', eventPane());
    drawEvent();
  }, 70);

  /* ---------- the page ---------- */
  function memberName(m) {
    return (m.session_label || m.entry_id || m.key)
      + (m.banked ? '' : ' (not banked)');
  }

  function unbankedOf(members) {
    return (members || []).filter((m) => m && m.banked === false).length;
  }

  function unbankedChip(n) {
    if (!n) return null;
    return BARRY.ui.chip(n + ' member' + (n === 1 ? '' : 's') + ' not banked', {
      kind: 'warn', extra: 'rc-unbanked',
      title: 'An unbanked member is a Root Canal read cached on this machine, '
           + 'fitted at the settings it was added with -- not a banked result. '
           + 'The pool can only be rebuilt while those reads are on this '
           + 'machine.' });
  }

  function poolBusyLine() {
    const what = pool.fitting
      ? 'Pooling ' + pool.sel.length + ' recording' + (pool.sel.length === 1 ? '' : 's')
        + ' — one z-score across the pool, one k-means, the 1-vs-2 GMM test'
      : pool.evBusy ? 'Reading that event from its own recording'
      : null;
    if (!what) return el('div', { class: 'rc-busy' });
    return el('div', { class: 'rc-busy on' }, [loader(what)]);
  }

  /* THREE SCREENS (2026-10-19), the same at both levels -- "clearly
     bifurcate the creation and viewing workflow":

       home   the saved pools, the main thing on the page, with New pool
              (New pool of pools) and, while one is in hand, a row to
              carry on with it;
       build  choosing: what the pool is, the settings, the recordings (or
              the pools) and the button that pools them -- which goes
              straight to the picture;
       view   looking: the pool's card, the settings, the waiting line and
              the picture. No table of recordings under it.

     Open on the shelf goes to view, at the top of the tool. */
  function poolScreen() {
    const s = pool.screen;
    if (s === 'view' && !pool.fit && !pool.fitting && !pool.sel.length
        && !pool.open && !pool.refusal) return 'home';
    return s === 'build' || s === 'view' ? s : 'home';
  }

  function paintPool(box) {
    if (!pool.cands && !pool.candsErr) {
      box.appendChild(loading('Reading what can be pooled',
                              'banked Root Canal results and reads cached here'));
      return;
    }
    const dbl = pool.level === 'double';
    box.appendChild(levelBar());
    const scr = poolScreen();
    if (scr === 'home') {
      box.appendChild(dbl ? dshelfCard() : shelfCard());
      return;
    }
    if (scr === 'build') {
      box.appendChild(buildCard());
      /* The same controls bar as Single: one set of settings for both views. */
      box.appendChild(controlsBar());
      box.appendChild(dbl ? poolsCard() : membersCard());
      return;
    }
    box.appendChild(openPoolCard());
    box.appendChild(controlsBar());
    const refused = refusalCard();
    if (refused) box.appendChild(refused);
    /* Always in the tree, so the first pool -- half a minute cold -- has a
       line to say so in. */
    box.appendChild(poolBusyLine());
    const w = poolWork();
    if (w) box.appendChild(w);
  }

  /* To a screen, with the tool's top in sight: a shelf long enough to
     scroll left the opened pool below the fold. */
  function goScreen(s) {
    pool.screen = s;
    render();
    toTop();
  }

  function toTop() {
    const box = host();
    if (!box) return;
    let sc = box;
    while (sc && sc !== document.body && sc !== document.documentElement) {
      const oy = getComputedStyle(sc).overflowY;
      if ((oy === 'auto' || oy === 'scroll') && sc.scrollHeight > sc.clientHeight + 1) {
        if (sc === box) {
          sc.scrollTop = 0;
        } else {
          const d = box.getBoundingClientRect().top - sc.getBoundingClientRect().top;
          if (d < 0) sc.scrollTop += d;
        }
      }
      sc = sc.parentElement;
    }
  }

  /* New pool: an empty one, on the choosing screen. A pool in hand that
     was never saved is asked about first -- it is only ticks, but ticks
     somebody chose. */
  async function newPool() {
    const unsaved = (pool.sel.length || pool.fit) && (!pool.open || pool.dirty);
    if (unsaved) {
      const n = pool.sel.length;
      const what = pool.level === 'double' ? 'pool' : 'recording';
      const ok = await BARRY.confirm(
        pool.level === 'double' ? 'Start a new pool of pools?' : 'Start a new pool?',
        (pool.open ? 'The changes to ‘' + pool.open.nickname + '’ are put down'
                   : 'The pool you were building is put down')
          + ': ' + n + ' ' + what + (n === 1 ? '' : 's') + ', not saved. '
          + 'Nothing else is lost.',
        'Start a new one', false);
      if (!ok) return;
    }
    closePool(true);
    goScreen('build');
  }

  /* Back to what was in hand: its picture if it has one, else its choosing. */
  function carryOn() {
    goScreen(pool.fit && pool.fit.ok ? 'view' : 'build');
  }

  /* Pool pressed on the choosing screen: straight to the picture, with the
     waiting line saying what it is doing while it fits. A pool that does
     not happen -- the one-measurement question cancelled -- goes back. */
  async function poolAndView() {
    if (!pool.sel.length) {
      toast('Tick at least one ' + (pool.level === 'double' ? 'pool' : 'recording')
            + ' to pool.', 'warn', 5000);
      return null;
    }
    // Started first: it says it is pooling before the screen is drawn.
    const fitting = runPool();
    goScreen('view');
    const got = await fitting;
    if (!got && !pool.fitErr && !pool.refusal && !(pool.fit && pool.fit.ok)) {
      goScreen('build');
    }
    return got;
  }

  /* POOL RECORDINGS | POOL POOLS. The second level pools saved pools: the
     controls' (every event DS) and the IED mice's, say. Each event keeps
     what its own pool called it -- its v0 -- and the identity switch is
     counted against that, and against its single. */
  function levelBar() {
    return el('div', { class: 'rc-levelbar' }, [
      BARRY.ui.seg([
        ['pool', 'Pool recordings', 'Recordings -- saved singles, banked '
                                    + 'results, reads here -- pooled.'],
        ['double', 'Pool pools', 'Saved pools pooled: a pool of pools. Each '
                                 + 'event keeps what its own pool called it.'],
      ], pool.level, (v) => setLevel(v), { extra: 'rc-level' }),
    ]);
  }

  /* A level is chosen on its saved pools (2026-10-19): home. */
  function setLevel(v) {
    if (v === pool.level) return;
    closePool(true);
    pool.level = v;
    pool.screen = 'home';
    if (v === 'double' && !pool.dshelf) loadDshelf();
    if (!pool.shelf) loadShelf(true);
    render();
    toTop();
  }

  async function loadDshelf() {
    try {
      pool.dshelf = (await api('/api/rootcanal/dpools')).dpools || [];
      pool.dshelfErr = null;
    } catch (e) {
      pool.dshelf = [];
      pool.dshelfErr = e.message;
    }
    if (viewMode === 'pooled' && pool.level === 'double') render();
  }

  /* The home screen's head (2026-10-19): what the shelf is, and the one
     primary -- a new pool -- last. */
  function shelfHead(title, newText, newTitle) {
    return el('div', { class: 'rc-shelf-head' }, [
      el('div', { class: 'section-label', text: title }),
      el('span', { class: 'spacer' }),
      BARRY.ui.button({ kind: 'primary', text: newText, extra: 'rc-new-pool',
                        title: newTitle, onclick: newPool }),
    ]);
  }

  /* A pool in hand while the shelf is up: carried on with, or put down. */
  function carryRow() {
    if (!pool.sel.length && !pool.fit) return null;
    const dbl = pool.level === 'double';
    const n = pool.sel.length;
    const what = n + ' ' + (dbl ? 'pool' : 'recording') + (n === 1 ? '' : 's');
    const pooled = !!(pool.fit && pool.fit.ok);
    const nick = pool.open && pool.open.nickname;
    return el('div', { class: 'rc-carry' }, [
      el('span', { class: 'rc-carry-say', text: nick
        ? '‘' + nick + '’ v' + pool.open.version + ' is open: ' + what
          + (pool.dirty ? ', changed since it was pooled' : '')
        : 'A pool you were building: ' + what + ', '
          + (pooled ? 'pooled' : 'not pooled yet') + ', not saved.' }),
      el('span', { class: 'spacer' }),
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Put it down',
        extra: 'rc-carry-drop',
        title: 'Closes it. Closing saves nothing and costs nothing.',
        onclick: () => closePool() }),
      BARRY.ui.button({ kind: 'ghost', size: 'sm', extra: 'rc-carry-go',
        text: nick ? 'Carry on with ‘' + nick + '’'
                   : 'Carry on with the pool you were building',
        title: pooled ? 'Back to its picture.' : 'Back to choosing what is in it.',
        onclick: carryOn }),
    ]);
  }

  function dshelfCard() {
    const kids = [shelfHead('Saved pools of pools', 'New pool of pools',
      'Choose saved pools and pool them into one: a pool of pools. Each event '
      + 'keeps what its own pool called it.')];
    const carry = carryRow();
    if (carry) kids.push(carry);
    const list = pool.dshelf;
    if (!list) {
      kids.push(el('p', { class: 'hint', text: 'Reading them…' }));
    } else if (pool.dshelfErr) {
      kids.push(el('p', { class: 'hint rc-warn', text: 'They could not be read: '
                                                       + pool.dshelfErr }));
    } else if (!list.length) {
      kids.push(el('div', { class: 'empty-state rc-shelf-empty' }, [
        el('p', { text: 'None saved yet. Press New pool of pools, tick saved '
                      + 'pools, pool them, and save that under a label.' }),
      ]));
    } else {
      kids.push(foldersBar());
      kids.push(folderedList(list, 'rc-dshelf-list', (p, folders) => {
        const id = p.artifact_id || p.id;
        const cur = p.current || {};
        return shelfRow(p, folders, [
          el('span', { class: 'mk-name', text: p.nickname || p.name || id }),
          p.version != null ? el('span', { class: 'flagchip',
                                           text: 'v' + p.version }) : null,
          el('span', { class: 'flagchip', text: ((cur.n_summary || {}).pools
                                                 || 0) + ' pools' }),
          BARRY.syncState ? BARRY.syncState.mark('artifacts', id) : null,
          moveSelect(id, folders),
          BARRY.ui.button({ kind: 'mini', text: 'Open', extra: 'rc-shelf-open',
            title: 'Open its picture as it was saved. Nothing is refitted.',
            onclick: () => openSaved(id) }),
        ]);
      }));
    }
    return el('div', { class: 'card rc-shelf rc-dshelf' }, kids);
  }

  /* What a saved pool version is, for its hover. */
  function poolHover(p, v) {
    const ns = (v && v.n_summary) || {};
    const pp = (v && v.params) || {};
    return [(p.nickname || p.name) + ' · v' + (v ? v.v : '?')
              + (v && v.nickname ? ' · ' + v.nickname : ''),
            (ns.members != null ? ns.members + ' recordings' : null),
            (ns.events != null ? ns.events + ' events' : null),
            (ns.mice != null ? ns.mice + ' mice' : null),
            pp.all_ds ? 'every event DS' : (pp.k ? 'k = ' + pp.k : null),
            (pp.measure && pp.measure.filter_label) || null,
            ns.stats ? 'Are the clusters different? ' + verdictWords(ns.stats)
                       + ' (SigClust)' : null,
            v ? 'Saved by ' + (v.by || 'someone') + (v.machine ? ' on '
              + v.machine : '') + (v.at ? ', ' + String(v.at).replace('T', ' ')
              .slice(0, 16) : '') : null]
      .filter(Boolean).join('\n');
  }

  /* The saved pools, to pool: each at a version, the latest unless
     another is picked. */
  function poolsCard() {
    const kids = [el('div', { class: 'section-label', text: 'Pools in the pool' }),
      el('p', { class: 'hint', text: 'Each event keeps what its own pool '
        + 'called it (its v0); the identity switch below is counted against '
        + 'that, and against what its single called it. Pools measured '
        + 'differently, or sharing a session, are refused by name.' })];
    const list = pool.shelf || [];
    if (!list.length) {
      kids.push(el('p', { class: 'hint', text: 'No pool has been saved yet. '
        + 'Pool recordings first, and save the pools.' }));
    }
    const selOfPool = (id) => pool.sel.find((m) => String(m.key)
      .indexOf('P:' + id + ':') === 0) || null;
    if (list.length) {
      kids.push(el('table', { class: 'tbl rc-pool-pools' }, [
        el('thead', {}, [el('tr', {}, ['', 'pool', 'version', 'recordings',
                                       'identity']
          .map((t) => el('th', { text: t })))]),
        el('tbody', {}, list.map((p) => {
          const id = p.artifact_id || p.id;
          const vs = (p.versions || []).filter((v) => v.here !== false);
          const sm = selOfPool(id);
          const curV = sm ? Number(String(sm.key).split(':')[2])
                          : (vs.length ? vs[vs.length - 1].v : p.version);
          const vrow = vs.find((v) => v.v === curV) || vs[vs.length - 1];
          const pp = (vrow && vrow.params) || {};
          const tr = el('tr', { class: sm ? 'on' : null, 'data-pool': id }, [
            /* A tick changes its row where it stands (2026-10-19). */
            el('td', {}, [el('input', { type: 'checkbox', class: 'rc-pool-pick',
              checked: sm ? 'checked' : null,
              onchange: (ev2) => {
                if (ev2.target.checked && !selOfPool(id)) {
                  const vSel = tr.querySelector('.rc-pool-ver');
                  pool.sel.push({ key: 'P:' + id + ':'
                                       + (vSel ? Number(vSel.value) : curV) });
                } else if (!ev2.target.checked) {
                  pool.sel = pool.sel.filter((m) => m !== selOfPool(id));
                }
                tr.classList.toggle('on', ev2.target.checked);
                touched();
              } })]),
            el('td', { text: p.nickname || p.name || id,
                       title: poolHover(p, vrow) }),
            el('td', {}, [el('select', { class: 'rc-in rc-pool-ver',
              title: poolHover(p, vrow),
              onchange: (ev2) => {
                // A ticked pool takes the version; an unticked one is
                // ticked at it when it is ticked.
                const v = Number(ev2.target.value);
                const m = selOfPool(id);
                if (!m) return;
                m.key = 'P:' + id + ':' + v;
                pool.dirty = true;
                render();
              } }, vs.slice().reverse().map((v) => el('option', {
                value: String(v.v), title: poolHover(p, v),
                selected: v.v === curV ? 'selected' : null,
                text: 'v' + v.v + (v.nickname ? ' · ' + v.nickname : '') })))]),
            el('td', { text: String(((vrow || {}).n_summary || {}).members
                                    || p.n_members || '') }),
            el('td', {}, [
              pp.all_ds ? BARRY.ui.chip('every event DS', { flag: true })
                        : BARRY.ui.chip('k = ' + (pp.k || 2), { flag: true }),
              BARRY.syncState ? BARRY.syncState.mark('artifacts', id) : null,
            ].filter(Boolean)),
          ]);
          return tr;
        })),
      ]));
    }
    kids.push(refusedPart('pools'));
    kids.push(poolsFoot());
    return el('div', { class: 'card rc-members rc-pools' }, kids);
  }

  /* How many pools are ticked, and the button that pools them -- and goes
     straight to the picture. */
  function poolsFoot() {
    const n = pool.sel.length;
    return BARRY.ui.actions([
      el('span', { class: 'hint', text: n + ' pool' + (n === 1 ? '' : 's')
        + ' ticked' + (pool.dirty && pool.fit && pool.fit.ok
          ? ' — changed since its picture' : '') }),
      BARRY.ui.button({ kind: 'primary',
        text: 'Pool ' + n + ' pool' + (n === 1 ? '' : 's'),
        extra: 'rc-pool-run', disabled: !n || pool.fitting,
        title: 'Pools their events in one space and shows the picture.',
        onclick: poolAndView }),
    ], { extra: 'rc-pools-foot' });
  }

  /* After a pool of pools is saved: its identity down, to its pools and/or
     its singles, each a new version -- both ticked by default. */
  function dpropagateDialog(rep) {
    const toPools = el('input', { type: 'checkbox', class: 'rc-dprop-pools',
                                  checked: 'checked' });
    const toSingles = el('input', { type: 'checkbox', class: 'rc-dprop-singles',
                                    checked: 'checked' });
    showModal(el('div', { class: 'rc-prop-dlg rc-dprop-dlg' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Carry this identity down?' }),
        el('div', { class: 'spacer' })]),
      el('div', { class: 'mb' }, [el('div', { class: 'rc-ask' }, [
        el('p', { text: 'New versions named “from pool of pools ‘'
          + rep.nickname + '’ v' + rep.version + '”, each event called and '
          + 'named as this pool of pools called it.' }),
        el('label', { class: 'rc-dprop-row' }, [toPools,
          el('span', { text: ' the pools: a new version of each, its members '
                             + 're-clustered with these clusters' })]),
        el('label', { class: 'rc-dprop-row' }, [toSingles,
          el('span', { text: ' the singles: a new version of each recording’s '
                             + 'single' })]),
      ])]),
      BARRY.ui.modalFoot([], [
        BARRY.ui.button({ kind: 'ghost', text: 'Not now', extra: 'rc-prop-no',
                          onclick: closeModal }),
        BARRY.ui.button({ kind: 'primary', text: 'Make the new versions',
          extra: 'rc-prop-yes',
          onclick: async () => {
            const tp = toPools.checked, ts = toSingles.checked;
            closeModal();
            if (!tp && !ts) return;
            let got;
            try {
              got = await apiPost('/api/rootcanal/dpool/propagate',
                Object.assign(poolBody(), { to_pools: tp, to_singles: ts,
                  dpool: { artifact_id: rep.artifact_id, version: rep.version,
                           nickname: rep.nickname } }));
            } catch (e) {
              toast('No new versions were made: ' + e.message, 'err', 12000);
              return;
            }
            const res = got.results || {};
            const left = (res.pools || []).concat(res.singles || [])
              .filter((r) => !r.ok);
            toast(got.made + ' new version' + (got.made === 1 ? '' : 's')
              + ' made' + (left.length ? '; ' + left.length + ' left: '
                + left.map((r) => r.why).join('; ') : '') + '.',
              left.length ? 'warn' : 'ok', 14000);
            loadShelf(true);
          } }),
      ]),
    ]), { replace: true });
  }

  /* ==================================================================
     FOLDERS FOR SAVED POOLS (2026-10-20)

     "To the pools of recordings and pools of pools add a folder structure
     where we can create new folders and drag all our pools into it. For
     every existing one, put them in a folder called Preliminary analysis."

     One set of folders for both shelves: a folder made on one is there on
     the other, each shelf showing its own kind of pool inside. A pool is
     dragged onto a folder -- or moved with the folder menu on its row,
     which is the same thing without a mouse -- and "Not in a folder" takes
     one out. Folders are made, renamed and deleted here; deleting one
     deletes no pool, its pools are simply out of it.

     Kept in two shared preferences merged key by key (backend/store.py
     PREFS_SPEC), so they travel to every machine and two people filing
     different pools both keep theirs:
       rootcanal_pool_folders   {folder id: {name, at, by, gone}}
       rootcanal_pool_in        {pool id: folder id, or "" for none}

     A pool nobody has filed was saved before folders existed: it is in
     Preliminary analysis. That is the rule rather than a move written for
     each one, so a pool saved on a machine that has not pulled this yet
     lands there too, and nothing is written until somebody files one. A
     pool saved from here is filed as it is saved (the dialog asks where).
     ================================================================== */
  const FOLD_KEY = 'rootcanal_pool_folders';
  const IN_KEY = 'rootcanal_pool_in';
  const PRELIM = { id: 'prelim', name: 'Preliminary analysis' };
  const DRAG_TYPE = 'text/x-rc-pool';
  const foldShut = {};          // folders folded shut, this sitting
  let foldEdit = null;          // { id: null for a new one, text }

  function prefMap(k) {
    try {
      return (BARRY.prefs && BARRY.prefs.get(k, {})) || {};
    } catch (e) {
      return {};
    }
  }

  /* Every folder, by name; Preliminary analysis unless it was deleted. */
  function poolFolders() {
    const m = prefMap(FOLD_KEY);
    const out = [];
    for (const id of Object.keys(m)) {
      const f = m[id];
      if (!f || f.gone) continue;
      out.push({ id: id, name: f.name || 'Untitled folder', at: f.at,
                 by: f.by });
    }
    if (!m[PRELIM.id]) out.push({ id: PRELIM.id, name: PRELIM.name });
    out.sort((a, b) => natural(a.name, b.name));
    return out;
  }

  /* Where a saved pool is: where it was put, else -- saved before folders
     -- Preliminary analysis. In a folder since deleted, it is in none. */
  function folderOf(id, folders) {
    const fs = folders || poolFolders();
    const inm = prefMap(IN_KEY);
    const has = (fid) => !!fid && fs.some((f) => f.id === fid);
    if (Object.prototype.hasOwnProperty.call(inm, id)) {
      return has(inm[id]) ? inm[id] : '';
    }
    return has(PRELIM.id) ? PRELIM.id : '';
  }

  function folderName(fid, folders) {
    if (!fid) return 'Not in a folder';
    const f = (folders || poolFolders()).find((x) => x.id === fid);
    return f ? f.name : 'Not in a folder';
  }

  function putInFolder(id, fid, quiet) {
    const m = Object.assign({}, prefMap(IN_KEY));
    m[id] = fid || '';
    BARRY.prefs.set(IN_KEY, m);
    BARRY.activity.log('rootcanal.pool_folder', { artifact: id,
                                                  folder: fid || null });
    if (!quiet) {
      const p = (pool.shelf || []).concat(pool.dshelf || [])
        .find((x) => (x.artifact_id || x.id) === id) || {};
      toast('‘' + (p.nickname || p.name || id) + '’ '
            + (fid ? 'is in ‘' + folderName(fid) + '’ now.'
                   : 'is out of its folder now.'), 'ok', 4000);
    }
  }

  function writeFolder(id, fields) {
    const m = Object.assign({}, prefMap(FOLD_KEY));
    m[id] = Object.assign({}, m[id] || {}, fields, {
      at: new Date().toISOString(),
      by: (BARRY.profile && BARRY.profile.who && BARRY.profile.who())
          || null });
    BARRY.prefs.set(FOLD_KEY, m);
  }

  function newFolderId() {
    return 'f' + Date.now().toString(36)
      + Math.floor(Math.random() * 1679616).toString(36);
  }

  /* Made or renamed from the line it is typed on. A name already taken is
     refused: two folders called the same are one folder said twice. */
  function finishFolder() {
    const ed = foldEdit;
    if (!ed) return;
    const name = String(ed.text || '').trim().replace(/\s+/g, ' ');
    if (!name) { toast('A folder needs a name.', 'warn', 4000); return; }
    if (name.length > 80) {
      toast('A folder name is a name, not a note: keep it under 80 '
            + 'characters.', 'warn', 5000);
      return;
    }
    const clash = poolFolders().find((f) => f.id !== ed.id
      && f.name.toLowerCase() === name.toLowerCase());
    if (clash) {
      toast('There is a folder called ‘' + clash.name + '’ already.', 'warn',
            5000);
      return;
    }
    const id = ed.id || newFolderId();
    writeFolder(id, { name: name, gone: false });
    BARRY.activity.log('rootcanal.pool_folder_' + (ed.id ? 'rename' : 'new'),
                       { folder: id, name: name });
    foldEdit = null;
    delete foldShut[id];
    toast(ed.id ? 'Renamed to ‘' + name + '’.'
                : 'Made ‘' + name + '’. Drag pools onto it, or move them '
                  + 'with the folder menu on their row.', 'ok', 5000);
    render();
  }

  async function deleteFolder(f, n) {
    const ok = await BARRY.confirm('Delete the folder ‘' + f.name + '’?',
      (n ? 'The ' + n + ' saved pool' + (n === 1 ? '' : 's') + ' in it '
           + (n === 1 ? 'is' : 'are') + ' taken out of it, to Not in a '
           + 'folder. ' : 'It is empty. ')
      + 'No pool is deleted, on this shelf or the other one.',
      'Delete folder', true);
    if (!ok) return;
    writeFolder(f.id, { name: f.name, gone: true });
    BARRY.activity.log('rootcanal.pool_folder_delete', { folder: f.id,
                                                         name: f.name });
    toast('Deleted the folder ‘' + f.name + '’.', 'ok', 4000);
    render();
  }

  /* Above the folders: making one. */
  function foldersBar() {
    const typing = foldEdit && !foldEdit.id;
    return el('div', { class: 'rc-folders-bar' }, [
      typing ? folderInput('Name the new folder') : null,
      typing ? BARRY.ui.button({ kind: 'mini', text: 'Make it',
        extra: 'rc-folder-make', onclick: finishFolder }) : null,
      typing ? BARRY.ui.button({ kind: 'mini', text: 'Cancel',
        onclick: () => { foldEdit = null; render(); } }) : null,
      typing ? null : BARRY.ui.button({ kind: 'ghost', size: 'sm',
        text: 'New folder', extra: 'rc-folder-new',
        title: 'A folder for saved pools, on this shelf and the pools-of-'
             + 'pools one. Drag pools onto it.',
        onclick: () => { foldEdit = { id: null, text: '' }; render(); } }),
      el('span', { class: 'hint', text: typing ? ''
        : 'Drag a pool onto a folder to file it.' }),
    ].filter(Boolean));
  }

  function folderInput(placeholder) {
    const inp = el('input', {
      type: 'text', class: 'rc-in rc-folder-input', value: foldEdit.text,
      placeholder: placeholder, maxlength: '80',
      'aria-label': placeholder,
      oninput: (e) => { if (foldEdit) foldEdit.text = e.target.value; },
      onkeydown: (e) => {
        if (e.key === 'Enter') { e.preventDefault(); finishFolder(); }
        if (e.key === 'Escape') { e.preventDefault(); foldEdit = null; render(); }
      },
    });
    const focusIt = () => {
      if (inp.isConnected && document.activeElement !== inp) {
        inp.focus();
        inp.setSelectionRange(inp.value.length, inp.value.length);
      }
    };
    // On the next frame, and on a timer too: a frame can be held back.
    requestAnimationFrame(focusIt);
    setTimeout(focusIt, 0);
    return inp;
  }

  const FOLDER_SVG = '<path d="M1.5 3.5h4.5l1.5 1.5h7v7.5h-13z" />';
  const FOLDER_OPEN_SVG = '<path d="M1.5 3.5h4.5l1.5 1.5h6v2M1.5 3.5v9h11.2'
    + 'l2-5.5H3.7l-2.2 5.5" />';

  /* A shelf's pools, in their folders, and the ones in none last. */
  function folderedList(list, cls, rowOf) {
    const folders = poolFolders();
    const groups = new Map(folders.map((f) => [f.id, []]));
    const loose = [];
    for (const p of list) {
      const fid = folderOf(p.artifact_id || p.id, folders);
      (fid && groups.has(fid) ? groups.get(fid) : loose).push(p);
    }
    const box = el('div', { class: 'rc-folders ' + cls });
    for (const f of folders) {
      box.appendChild(folderBox(f, groups.get(f.id), rowOf, folders));
    }
    box.appendChild(folderBox({ id: '', name: 'Not in a folder' }, loose,
                              rowOf, folders));
    return box;
  }

  function folderBox(f, items, rowOf, folders) {
    const shut = !!foldShut[f.id];
    const editing = foldEdit && foldEdit.id && foldEdit.id === f.id;
    const n = items.length;
    const head = el('div', { class: 'rc-folder-head' }, [
      el('button', {
        class: 'rc-folder-twist', type: 'button',
        'aria-expanded': shut ? 'false' : 'true',
        title: shut ? 'Open the folder' : 'Fold it shut',
        onclick: () => { foldShut[f.id] = !shut; render(); },
      }, [el('svg', { class: 'rc-bulk-ico rc-folder-ico', viewBox: '0 0 16 16',
                      'aria-hidden': 'true',
                      html: f.id ? (shut ? FOLDER_SVG : FOLDER_OPEN_SVG)
                                 : '<path d="M2.5 8h11" />' }),
          editing ? null : el('span', { class: 'rc-folder-name',
                                        text: f.name })]),
      editing ? folderInput('Rename ‘' + f.name + '’') : null,
      editing ? BARRY.ui.button({ kind: 'mini', text: 'Rename',
        extra: 'rc-folder-make', onclick: finishFolder }) : null,
      editing ? BARRY.ui.button({ kind: 'mini', text: 'Cancel',
        onclick: () => { foldEdit = null; render(); } }) : null,
      el('span', { class: 'flagchip rc-folder-n',
                   text: n + ' pool' + (n === 1 ? '' : 's') }),
      el('span', { class: 'spacer' }),
      f.id && !editing ? BARRY.ui.button({ kind: 'mini', text: 'Rename',
        extra: 'rc-folder-rename', title: 'Rename this folder',
        onclick: () => { foldEdit = { id: f.id, text: f.name }; render(); } })
        : null,
      f.id && !editing ? BARRY.ui.button({ kind: 'mini', text: 'Delete',
        extra: 'rc-folder-delete',
        title: 'Delete the folder. Its pools are taken out of it; no pool '
             + 'is deleted.',
        onclick: () => deleteFolder(f, n) }) : null,
    ].filter(Boolean));
    const body = shut ? null : el('div', { class: 'bm-list rc-folder-body' },
      n ? items.map((p) => rowOf(p, folders))
        : [el('p', { class: 'hint rc-folder-empty', text: f.id
            ? 'Empty. Drag a pool here.'
            : 'Every pool is in a folder. Drag one here to take it out.' })]);
    const box = el('div', {
      class: 'rc-folder' + (shut ? ' shut' : '') + (f.id ? '' : ' loose'),
      'data-folder': f.id,
    }, [head, body].filter(Boolean));
    dropTarget(box, f.id);
    return box;
  }

  /* Somewhere a dragged pool can be put down. */
  function dropTarget(node, fid) {
    const ours = (e) => Array.from((e.dataTransfer && e.dataTransfer.types)
                                   || []).indexOf(DRAG_TYPE) >= 0;
    node.addEventListener('dragover', (e) => {
      if (!ours(e)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      node.classList.add('rc-drop-on');
    });
    node.addEventListener('dragleave', (e) => {
      if (!e.relatedTarget || !node.contains(e.relatedTarget)) {
        node.classList.remove('rc-drop-on');
      }
    });
    node.addEventListener('drop', (e) => {
      node.classList.remove('rc-drop-on');
      if (!ours(e)) return;
      e.preventDefault();
      e.stopPropagation();
      const id = e.dataTransfer.getData(DRAG_TYPE);
      if (!id || folderOf(id) === (fid || '')) return;
      putInFolder(id, fid);
      render();
    });
  }

  /* A row on a shelf: dragged by any part of it that is not a control. */
  function shelfRow(p, folders, cells) {
    const id = p.artifact_id || p.id;
    const on = !!(pool.open && pool.open.artifact_id === id);
    const row = el('div', {
      class: 'bm-row rc-shelf-row' + (on ? ' on' : ''),
      draggable: 'true', 'data-pool': id,
      title: 'Drag it onto a folder to file it.',
      ondragstart: (e) => {
        if (e.target && e.target.closest
            && e.target.closest('button, select, input')) {
          e.preventDefault();
          return;
        }
        e.dataTransfer.setData(DRAG_TYPE, id);
        e.dataTransfer.effectAllowed = 'move';
        row.classList.add('rc-dragging');
      },
      ondragend: () => {
        row.classList.remove('rc-dragging');
        const box = host();
        if (box) {
          for (const n of Array.from(box.querySelectorAll('.rc-drop-on'))) {
            n.classList.remove('rc-drop-on');
          }
        }
      },
    }, [el('span', { class: 'rc-grip', 'aria-hidden': 'true', text: '⠿' })]
       .concat(cells.filter(Boolean)));
    return row;
  }

  /* The same move as a drag, from the row: for a keyboard, a touch screen,
     or a folder scrolled out of reach. */
  function moveSelect(id, folders) {
    const here = folderOf(id, folders);
    return el('select', {
      class: 'rc-in rc-move-folder', title: 'Move it to another folder',
      'aria-label': 'Folder',
      onchange: (e) => { putInFolder(id, e.target.value); render(); },
    }, folders.map((f) => el('option', { value: f.id, text: f.name,
      selected: f.id === here ? 'selected' : null }))
      .concat([el('option', { value: '', text: 'Not in a folder',
                              selected: here ? null : 'selected' })]));
  }

  /* The saved pools: the shelf. Opening one restores its members, its
     overrides and its focus, and draws what was saved -- no refit, no
     recording read. */
  function shelfCard() {
    /* THE HOME SCREEN (2026-10-19): the saved pools first, as they were --
       "that we can see all the saved pools at the start is good" -- with
       New pool beside them, and a pool in hand one row above the list. */
    const kids = [shelfHead('Saved pools', 'New pool',
      'Choose recordings and pool them. You see the picture as soon as it is '
      + 'pooled; nothing is saved until you save it.')];
    const carry = carryRow();
    if (carry) kids.push(carry);
    if (!pool.shelf) {
      kids.push(el('p', { class: 'hint', text: 'Reading the saved pools…' }));
    } else if (pool.shelfErr) {
      kids.push(el('p', { class: 'hint rc-warn', text:
        'The saved pools could not be read: ' + pool.shelfErr }));
    } else if (!pool.shelf.length) {
      kids.push(el('div', { class: 'empty-state rc-shelf-empty' }, [
        el('p', { text: 'No pool has been saved yet. Press New pool, tick '
                      + 'recordings, pool them, and save the pool under a '
                      + 'label.' }),
      ]));
    } else {
      kids.push(foldersBar());
      kids.push(folderedList(pool.shelf, 'rc-shelf-list', (p, folders) => {
        const id = p.artifact_id || p.id;
        return shelfRow(p, folders, [
          el('span', { class: 'mk-name', text: p.nickname || p.name || id }),
          p.version != null ? el('span', { class: 'flagchip',
                                           text: 'v' + p.version }) : null,
          el('span', { class: 'flagchip', text: (p.n_members != null ? p.n_members
                                                  : (p.n || 0)) + ' recordings' }),
          unbankedChip(p.n_unbanked || 0),
          el('span', { class: 'person-what', text: p.name || '' }),
          moveSelect(id, folders),
          BARRY.ui.button({ kind: 'mini', text: 'Open', extra: 'rc-shelf-open',
            title: 'Open its picture as it was saved. Nothing is refitted and '
                 + 'no recording is read.',
            onclick: () => openSaved(id) }),
        ]);
      }));
    }
    return el('div', { class: 'card rc-shelf' }, kids);
  }

  function nextPoolVersion() {
    const v = pool.open && Number(pool.open.version);
    return isFinite(v) && v > 0 ? v + 1 : 2;
  }

  /* The button says what it will do: a new pool, or the next version of
     the one that is open. */
  function saveLabel() {
    return pool.open
      ? 'Save as v' + nextPoolVersion() + ' of ‘' + pool.open.nickname + '’'
      : 'Save as new pool…';
  }

  /* The pool that is open, on the bench: what it is called, which version,
     how many recordings and mice, and whether any of it is unbanked. On
     the picture's screen (2026-10-19) it is the screen's head: back to the
     saved pools, change what is in it, save it -- as a pool, or each
     recording as a single of its own -- and close it. */
  function openPoolCard() {
    const dbl = pool.level === 'double';
    const f = pool.fit && pool.fit.ok ? pool.fit : null;
    const members = f ? (f.members || []) : pool.sel.map((m) => candOf(m.key))
      .filter(Boolean);
    const mice = new Set(members.map((m) => m.mouse_key).filter(Boolean));
    const nUnb = f ? unbankedOf(members)
                   : pool.sel.filter((m) => { const c = candOf(m.key);
                                              return c && !c.banked; }).length;
    // Not while it is being pooled: the waiting line says that.
    const changed = pool.dirty && !pool.fitting;
    // A pool saved with two answers about one recording, said up here too.
    const nDup = dbl ? 0 : recordings().filter((r) => recSel(r).length > 1).length;
    const again = changed && pool.sel.length > 0;
    const primarySave = !pool.dirty && !!f;
    return BARRY.ui.workbenchCard({
      title: pool.open ? pool.open.nickname : 'A pool not saved yet',
      extra: 'rc-pool-card',
      chips: [
        BARRY.ui.chip(pool.open ? 'v' + pool.open.version : 'not saved',
                      { flag: true }),
        pool.saved ? BARRY.ui.chip('as saved: nothing refitted', { flag: true })
                   : null,
        changed ? BARRY.ui.chip('changed: pool again to see it',
                                { flag: true, kind: 'warn' }) : null,
        nDup ? BARRY.ui.chip(nDup + ' recording' + (nDup === 1 ? '' : 's')
                             + ' in twice', { flag: true, kind: 'warn',
          extra: 'rc-dup-chip',
          title: 'This pool holds two answers about ' + (nDup === 1
            ? 'one recording' : nDup + ' recordings') + ', so ' + (nDup === 1
            ? 'its' : 'their') + ' events are counted twice. Change recordings '
            + 'says which, with a press to keep one.' }) : null,
        unbankedChip(nUnb),
      ].filter(Boolean),
      count: members.length + ' recording' + (members.length === 1 ? '' : 's')
             + ' · ' + mice.size + ' mice',
      owner: { name: (pool.open && pool.open.by) || null },
      when: pool.open && pool.open.updated ? String(pool.open.updated) : null,
      actions: [
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Back to pools',
          extra: 'rc-back',
          title: 'The saved pools. This one stays in hand: “Carry on” there '
               + 'brings it back as it is.',
          onclick: () => goScreen('home') }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', extra: 'rc-change',
          text: dbl ? 'Change pools' : 'Change recordings',
          title: dbl ? 'Choose which saved pools are in it, and their versions.'
                     : 'Choose which recordings are in it, and which answer '
                       + 'about each.',
          onclick: () => goScreen('build') }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Close this pool',
          extra: 'rc-close',
          title: 'Puts it down. Closing saves nothing and costs nothing; a '
               + 'saved pool stays on the shelf.',
          onclick: () => closePool() }),
        f ? BARRY.ui.button({ kind: 'ghost', size: 'sm', extra: 'rc-singles',
          text: 'Save as singles…',
          title: 'Save any of its recordings as Root Canal singles of their '
               + 'own, measured the pool’s way. Nothing is banked.',
          onclick: singlesDialog }) : null,
        again ? BARRY.ui.button({ kind: 'primary', size: 'sm',
          text: 'Pool again', extra: 'rc-pool-again',
          title: 'Fits it again with what is in it now.',
          onclick: () => runPool() }) : null,
        BARRY.ui.button({ kind: primarySave ? 'primary' : 'ghost', size: 'sm',
          text: saveLabel(), extra: 'rc-save',
          disabled: !pool.sel.length,
          title: 'Saved as a Jarvis artifact, refitted on the server from its '
               + 'members. Nothing goes to the Event Bank.',
          onclick: saveDialog }),
      ].filter(Boolean),
    });
  }

  /* The choosing screen's head (2026-10-19): a new pool, or the one open
     being changed, what is ticked so far, and the way back. */
  function buildCard() {
    const dbl = pool.level === 'double';
    const nick = pool.open && pool.open.nickname;
    const n = pool.sel.length;
    const chips = [];
    let count;
    if (dbl) {
      count = n + ' pool' + (n === 1 ? '' : 's') + ' ticked';
    } else {
      const mice = new Set(pool.sel.map((m) => {
        const c = candOf(m.key);
        const sm = (pool.savedMembers || []).find((x) => x.key === m.key);
        return (c && c.mouse_key) || (sm && sm.mouse_key) || null;
      }).filter(Boolean));
      count = n + ' recording' + (n === 1 ? '' : 's') + ' ticked · ' + mice.size
              + ' mice';
      chips.push(unbankedChip(pool.sel.filter((m) => {
        const c = candOf(m.key);
        return c && !c.banked;
      }).length));
    }
    if (pool.open) {
      chips.unshift(BARRY.ui.chip('v' + pool.open.version + ' open',
                                  { flag: true }));
    }
    if (pool.dirty && pool.fit && pool.fit.ok) {
      chips.push(BARRY.ui.chip('changed since its picture',
                               { flag: true, kind: 'warn' }));
    }
    return BARRY.ui.workbenchCard({
      title: nick ? 'Changing ‘' + nick + '’'
                  : (dbl ? 'New pool of pools' : 'New pool'),
      extra: 'rc-build-card',
      chips: chips.filter(Boolean),
      count,
      owner: { name: (pool.open && pool.open.by) || null },
      extras: [el('p', { class: 'hint rc-build-say', text: dbl
        ? 'Tick the saved pools to pool together, each at a version, then '
          + 'pool them: the picture comes up as soon as they are pooled, and '
          + 'nothing is saved until you save it.'
        : 'Tick the recordings, one answer about each, then pool them: the '
          + 'picture comes up as soon as they are pooled, and nothing is saved '
          + 'until you save it.' })],
      actions: [
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Back to pools',
          extra: 'rc-back',
          title: 'The saved pools. What is ticked stays: “Carry on” there '
               + 'brings it back.',
          onclick: () => goScreen('home') }),
        pool.fit && pool.fit.ok ? BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: 'Back to the picture', extra: 'rc-to-view',
          title: pool.dirty ? 'The picture as it was last pooled; it says it '
                              + 'has changed until it is pooled again.'
                            : 'The picture, as it was.',
          onclick: () => goScreen('view') }) : null,
      ].filter(Boolean),
    });
  }

  /* Which recordings -- one row each, one answer each (2026-10-19) -- and
     what type each mouse is. */
  function membersCard() {
    const kids = [el('div', { class: 'section-label', text: 'Recordings in the pool' })];
    if (pool.candsErr) {
      kids.push(el('p', { class: 'hint rc-warn', text:
        'What can be pooled could not be read: ' + pool.candsErr }));
    }
    const sp = singleParams();
    kids.push(el('p', { class: 'hint', text:
      'One row per recording. Where Jarvis has more than one answer about a '
      + 'recording — its banked result, a saved single, a read cached here — '
      + 'its row says which goes in, and only that one does. A banked result '
      + 'reads no recording. A read here, not banked, is fitted at Single’s '
      + 'settings as they stand when it is ticked: ' + filterWords(sp) + ', ±'
      + hz(sp.win_ms) + ' ms, half-width ±' + hz(sp.cross_ms) + ' ms, '
      + hz(sp.band_lo) + '–' + hz(sp.band_hi) + ' Hz. Only sets that have been '
      + 'through Braces are offered.' }));
    const cs = pool.cands || [];
    const recs = recordings();
    if (cs.length) kids.push(selectBar());
    if (!recs.length && !pool.candsErr) {
      kids.push(el('div', { class: 'empty-state rc-pool-empty' }, [
        el('p', { text: 'Nothing can be pooled yet. Bank a set in Single, or '
                      + 'read one there: a read cached on this machine can '
                      + 'join a pool before it is banked.' }),
      ]));
    }
    /* In a box of its own that scrolls across on a narrow panel, so a
       recording's answers are never cut and the page never scrolls
       sideways. */
    if (recs.length) {
      kids.push(el('div', { class: 'rc-pool-cands-wrap' }, [membersTable()]));
    }
    kids.push(fromSaveNote());
    kids.push(typesBox());
    kids.push(refusedPart('members'));
    kids.push(el('label', { class: 'rc-all-ds',
      title: 'Every event of this pool is a dentate spike: one cluster, '
           + 'called DS, saved with the pool -- the controls. In a pool of '
           + 'pools its events go in as DS.' }, [
      el('input', { type: 'checkbox', class: 'rc-all-ds-box',
        checked: pool.all_ds ? 'checked' : null,
        onchange: (ev2) => { pool.all_ds = ev2.target.checked;
                             pool.dirty = true; membersRefresh(); } }),
      el('span', { text: ' every event is DS (the controls)' }),
    ]));
    kids.push(membersFoot());
    return el('div', { class: 'card rc-members' }, kids);
  }

  /* Members of an opened pool that this machine does not offer. They
     pool from the saved version, number for number, so everything that
     works on numbers works; what would measure them again needs their
     reads, which Jarvis reads here when it is asked to (2026-10-19). */
  function fromSaveNote() {
    const box = el('div', { class: 'rc-from-save-box' });
    const missing = pool.sel.filter((m) => !candOf(m.key));
    if (!missing.length) return box;
    const one_ = missing.length === 1;
    const src = pool.open && pool.open.source;
    const wh = Array.from(new Set(missing.map((m) =>
      (poolMemberByKey(m.key) || {}).read_on).filter(Boolean)));
    box.appendChild(el('p', { class: 'hint rc-from-save-note', text:
      missing.length + ' member' + (one_ ? '' : 's') + ' of this pool '
      + (one_ ? 'was' : 'were') + ' read on '
      + (wh.length ? wh.join(' and ') : 'another machine') + ', so '
      + (one_ ? 'its read is' : 'their reads are') + ' not here. '
      + (src
        ? (one_ ? 'It pools' : 'They pool') + ' from v' + src.version
          + (pool.open.nickname ? ' of ‘' + pool.open.nickname + '’' : '')
          + ', number for number as saved: k, calls, focus, margins and '
          + 'drawn clusters all work. Measuring ' + (one_ ? 'it' : 'them')
          + ' another way (filter, window, half-width search, HF band) '
          + 'needs ' + (one_ ? 'its read' : 'their reads') + ': where that '
          + 'is asked for, Jarvis offers to read ' + (one_ ? 'it' : 'them')
          + ' here, and a dot of ' + (one_ ? 'its' : 'theirs') + ' opened on '
          + 'the picture is read here by itself.'
        : 'Pooling again here would need ' + (one_ ? 'it' : 'them')
          + ', which Jarvis offers to read here when it is refused.') }));
    return box;
  }

  /* The mice of the pool, from what is ticked: kept apart so a tick can
     bring it up to date without the table around it. */
  function poolMice() {
    const mice = new Map();
    for (const m of pool.sel) {
      // A member pooled from the save is still a mouse whose type can be
      // set: what the save knew of it stands in for a candidate.
      const sm = (pool.savedMembers || []).find((x) => x.key === m.key);
      const c = candOf(m.key) || (sm && { mouse_key: sm.mouse_key,
        mouse_type: sm.mouse_type_default || sm.mouse_type });
      if (c && c.mouse_key && !mice.has(c.mouse_key)) mice.set(c.mouse_key, c);
    }
    return mice;
  }

  /* Mouse type, per mouse in the pool: the registry's filing unless
     somebody says otherwise, free text with the types already in use as
     suggestions. The override is the pool's, not the registry's. */
  function typesBox() {
    const box = el('div', { class: 'rc-types-box' });
    const mice = poolMice();
    if (!mice.size) return box;
    const inUse = new Set();
    for (const c of pool.cands || []) if (c.mouse_type) inUse.add(c.mouse_type);
    for (const k2 of Object.keys(pool.types)) inUse.add(pool.types[k2]);
    box.appendChild(el('div', { class: 'section-label', text: 'Mouse type' }));
    box.appendChild(el('datalist', { id: 'rcTypeList' },
      Array.from(inUse).sort().map((t) => el('option', { value: t }))));
    box.appendChild(el('div', { class: 'rc-types' }, Array.from(mice.entries())
      .map(([mk, c]) => el('label', { class: 'rc-type' }, [
        el('span', { class: 'rc-type-k', text: mk }),
        el('input', {
          type: 'text', class: 'rc-in rc-type-in', list: 'rcTypeList',
          value: typeFor(mk, c.mouse_type), 'data-mouse': mk,
          title: 'The registry files this mouse as “' + (c.mouse_type || 'no '
               + 'type') + '”. Type another to override it in this pool.',
          onchange: (ev2) => setType(mk, ev2.target.value, c.mouse_type),
        }),
        pool.types[mk]
          ? el('span', { class: 'hint', text: 'set here; the registry says '
                                              + (c.mouse_type || 'nothing') })
          : el('span', { class: 'hint', text: 'from the registry' }),
      ]))));
    return box;
  }

  /* How many are ticked, and the button that pools them -- and goes
     straight to the picture (2026-10-19). */
  function membersFoot() {
    const n = pool.sel.length;
    const nMice = poolMice().size;
    return BARRY.ui.actions([
      el('span', { class: 'hint rc-members-count', text: n + ' recording'
        + (n === 1 ? '' : 's') + ' ticked, ' + nMice + ' mice'
        + (pool.dirty && pool.fit && pool.fit.ok ? ' — changed since its picture'
                                                 : '') }),
      BARRY.ui.button({
        kind: 'primary',
        text: 'Pool ' + n + ' recording' + (n === 1 ? '' : 's')
              + (pool.name ? ' (“' + pool.name + '” only)' : ''),
        extra: 'rc-pool-run',
        disabled: !n || pool.fitting,
        title: 'One z-score over the pooled raw numbers, one k-means, and the '
             + '1-vs-2 group test, and then the picture. Banked members read '
             + 'no recording.',
        onclick: poolAndView,
      }),
    ], { extra: 'rc-members-foot' });
  }

  /* ==================================================================
     A REFUSAL ABOUT MEMBERS, AND ITS FIX (2026-10-19)

     "It should be able to just redo the analysis when I ask it to." A
     refusal that names members (`away`) is about one of two things: a
     member read elsewhere that would have to be measured again -- read it
     here, then pool again -- or a second answer about a recording already
     in the pool -- take the copy out. Each is offered beside the sentence,
     wherever the refusal is said: the choosing screen, the picture's,
     either level. When the reading is done the pool is fitted again, and a
     save that was refused is offered again.
     ================================================================== */
  function refusalOf() {
    return pool.refusal || (pool.fitErr ? { error: pool.fitErr, away: [],
                                            from: 'fit' } : null);
  }

  /* A key is a SECOND COPY when its recording has more than one answer in
     the pool and it is not the first. */
  function isSecondCopy(k) {
    const rec = pool.level === 'double' ? null : recOfKey(k);
    if (!rec) return false;
    const mine = recSel(rec);
    return mine.length > 1 && mine[0].key !== k;
  }

  const readKeys = (r) => ((r && r.away) || []).filter((k) => !isSecondCopy(k));
  const copyKeys = (r) => ((r && r.away) || []).filter(isSecondCopy);

  function labelOfKey(k) {
    const m = poolMemberByKey(k)
      || (pool.savedMembers || []).find((x) => x.key === k);
    if (m && m.session_label) return m.session_label;
    const c = candOf(k);
    if (c && c.session_label) return c.session_label;
    const rec = recOfKey(k);
    return (rec && (rec.facts[0] || {}).session_label) || k;
  }

  /* What each named member is asked for as: its own key and the saved
     pool it is read from, or -- in a pool of pools -- its key inside the
     member pool it belongs to, with that pool's version. */
  function asksFor(keys) {
    return keys.map((k) => {
      const m = poolMemberByKey(k);
      if (m) return askOfMember(m);
      const p = /^p:([^:]+):(\d+):(.+)$/.exec(String(k));
      if (p) {
        return { id: k, key: p[3], label: labelOfKey(k),
                 saved: { artifact_id: p[1], version: Number(p[2]) } };
      }
      return { id: k, key: k, label: labelOfKey(k),
               saved: pool.open && pool.open.source
                 ? Object.assign({}, pool.open.source) : null };
    });
  }

  function startRedo() {
    const r = refusalOf();
    const keys = readKeys(r);
    if (!keys.length) return;
    if (pool.redo && !pool.redo.ended) return;
    const R = rereadRun(asksFor(keys), paintRedo, () => redoEnded(R));
    R.from = (r && r.from) || 'fit';
    pool.redo = R;
    paintRedo();
  }

  /* Read again: the candidates are asked for afresh (what was read is
     here now), the pool is fitted again, and a refused save or singles
     save is offered again once it has fitted. Nothing is fitted when
     nothing landed: the rows say why. */
  async function redoEnded(R) {
    if (pool.redo !== R) return;
    const rows = rereadRows(R);
    const got = rows.filter((x) => x.status === 'done' || x.status === 'here');
    const bad = rows.length - got.length;
    toast(got.length
      ? got.length + ' read here' + (bad ? '; ' + bad + ' could not be — '
          + 'the reasons are in the pool’s card' : '') + '. Pooling again.'
      : 'Nothing could be read here; the reasons are in the pool’s card.',
      bad ? 'warn' : 'ok', 10000);
    if (!got.length) return;
    pool.cands = null;
    loadPool();
    pool.refusal = null;
    pool.fitErr = null;
    if (pool.fit && !pool.fit.ok) pool.fit = null;
    const fitted = await runPool();
    if (!fitted || pool.redo !== R) return;
    if (R.from === 'save') saveDialog();
    else if (R.from === 'singles') singlesDialog();
  }

  /* Every place the run is shown, brought up to date: the words of each
     row in place while its rows stay the same, and the box rebuilt when
     they change. */
  function paintRedo() {
    const box = host();
    if (!box) return;
    for (const n of Array.from(box.querySelectorAll('.rc-redo'))) {
      const fresh = redoBox();
      if (n.__shape && n.__shape === fresh.__shape) {
        const words = Array.from(fresh.querySelectorAll('.rc-redo-state'));
        Array.from(n.querySelectorAll('.rc-redo-state')).forEach((s, j) => {
          if (words[j] && s.textContent !== words[j].textContent) {
            s.textContent = words[j].textContent;
          }
        });
      } else {
        n.replaceWith(fresh);
      }
    }
  }

  /* The sentence, the press that fixes it, and the run while it reads. */
  function redoBox() {
    const R = pool.redo;
    const r = refusalOf();
    const keys = readKeys(r);
    const running = !!(R && !R.ended);
    const kids = [];
    if (R && (running || r)) {
      const rows = rereadRows(R);
      const n = rows.length;
      kids.push(el('p', { class: 'hint rc-redo-line', text: running
        ? (R.state === 'sending' ? 'Asking for ' : 'Reading ') + n
          + ' recording' + (n === 1 ? '' : 's') + ' here again, one after '
          + 'another, from a drive on this computer or on the VACC — exactly '
          + 'as ' + (n === 1 ? 'it was' : 'they were') + ' read. The pool is '
          + 'fitted again when ' + (n === 1 ? 'it lands' : 'they land') + '.'
        : 'The last time ' + (n === 1 ? 'it was' : 'they were')
          + ' asked for here:' }));
      kids.push(rereadList(R));
      if (running) {
        kids.push(BARRY.ui.actions([
          BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Stop',
            extra: 'rc-redo-stop', disabled: !!R.stopping || R.state === 'sending',
            title: 'Stop reading. A set read part-way is not kept; the ones '
                 + 'already read are.',
            onclick: () => R.stop() }),
        ]));
      }
    }
    if (!running && keys.length) {
      const names = keys.map(labelOfKey);
      const one = keys.length === 1;
      kids.push(el('p', { class: 'rc-redo-say', text: names.join(', ')
        + (one ? ' has' : ' have') + ' to be measured again for this, and '
        + (one ? 'its read is' : 'their reads are') + ' not on this machine. '
        + 'Jarvis can read ' + (one ? 'it' : 'them') + ' here — from a drive '
        + 'on this computer if the recording is on one, otherwise on the '
        + 'VACC — exactly as ' + (one ? 'it was' : 'they were') + ' read, '
        + 'and then redo the analysis.' }));
      kids.push(BARRY.ui.actions([
        BARRY.ui.button({ kind: 'primary', extra: 'rc-redo-go',
          text: 'Read them here and redo the analysis',
          title: 'Reads ' + names.join(', ') + ' again here, then pools again'
               + (r && r.from === 'save' ? ' and offers the save again.'
                  : r && r.from === 'singles'
                    ? ' and offers to save the singles again.' : '.'),
          onclick: startRedo }),
      ]));
    }
    const box = el('div', { class: 'rc-redo' }, kids);
    box.__shape = JSON.stringify([R ? rereadRows(R).map((x) => [x.id, x.status])
                                    : null, running, !!(R && R.stopping),
                                  R && R.state, keys]);
    return box;
  }

  /* A refusal, where it is said: the sentence, and its fix. */
  function refusedPart(where) {
    const box = el('div', { class: 'rc-refused-box rc-' + where + '-refused' });
    const r = refusalOf();
    const running = !!(pool.redo && !pool.redo.ended);
    if (!r && !running) return box;
    if (r) {
      // The picture's card says what was refused in its heading.
      box.appendChild(el('p', { class: 'hint rc-warn rc-pool-refused', text:
        (where === 'view' ? '' : r.from === 'save' ? 'Not saved: '
          : r.from === 'singles' ? 'Not saved as singles: ' : 'Not pooled: ')
        + r.error }));
    }
    const copies = copyKeys(r);
    if (copies.length) {
      box.appendChild(el('div', { class: 'rc-dup rc-dup-fix-row' }, [
        el('p', { class: 'rc-dup-say', text: 'The pool holds two answers about '
          + copies.map(labelOfKey).join(', ') + ', and a recording can be in a '
          + 'pool once. Take the second out and pool again, or choose which '
          + 'to keep in its row.' }),
        BARRY.ui.button({ kind: readKeys(r).length ? 'ghost' : 'primary',
          size: 'sm', extra: 'rc-dup-fix',
          text: 'Take the second copies out and pool again',
          onclick: () => {
            pool.sel = pool.sel.filter((m) => copies.indexOf(m.key) < 0);
            pool.refusal = null;
            pool.fitErr = null;
            pool.dirty = true;
            poolAndView();
          } }),
      ]));
    }
    if (readKeys(r).length || pool.redo) box.appendChild(redoBox());
    return box;
  }

  /* On the picture's screen: a card of its own, above the picture -- which
     stays, being the answer for the members it was drawn from. */
  function refusalCard() {
    const r = refusalOf();
    const running = !!(pool.redo && !pool.redo.ended);
    if (!r && !running) return null;
    return el('div', { class: 'card rc-err rc-refusal' }, [
      el('strong', { text: !r ? 'Reading recordings here again'
        : r.from === 'save' ? 'That pool could not be saved'
        : r.from === 'singles' ? 'Those singles could not be saved'
        : 'That pool could not be fitted' }),
      refusedPart('view'),
    ]);
  }

  function poolChip() {
    const f = pool.fit && pool.fit.ok ? pool.fit : null;
    const n = f ? (f.members || []).length : 0;
    return el('span', {
      class: 'rc-chip rc-pool-chip' + (pool.dirty ? ' rc-chip-stale' : ''),
      title: pool.dirty ? 'The members or the types have changed since this '
                        + 'picture. Pool again to see them.'
                        : 'What this picture pools, and on what scale.',
      text: 'pooled raw · ' + n + ' recording' + (n === 1 ? '' : 's')
            + (pool.dirty ? '  (pool again)' : ''),
    });
  }

  function poolWork() {
    const f = pool.fit;
    if (!f) return null;
    if (!f.ok) {
      // Said once, in the refusal's own card, with its fix (2026-10-19).
      if (refusalOf()) return null;
      return el('div', { class: 'rc-work' }, [
        el('div', { class: 'card rc-err' }, [
          el('strong', { text: 'That pool could not be fitted' }),
          el('p', { class: 'hint', text: f.error }),
        ]),
      ]);
    }
    return el('div', { class: 'rc-work rc-pool-work' }, [
      poolTop(),
      poolClusterBar(),
      lassoBar(),
      poolPickBar(),
      poolLegend(),
      el('div', { class: 'rc-main' }, [spacePane(), flatsPane(), eventPane()]),
      bordersCard(poolBorderCtx()),
      gmmPanel(),
      switchPanel(),
      deepPanel(),
    ]);
  }

  /* The pool's clusters, and what it left out or re-measured. */
  function poolClusterBar() {
    const f = pool.fit;
    const c = (f && f.counts) || {};
    const reb = ((f && f.members) || []).filter((m) => m.rebanded_from);
    const notes = [];
    if (c.excluded) {
      notes.push(BARRY.ui.chip(c.excluded + ' left out: missing an axis', {
        kind: 'warn', extra: 'rc-count-excluded',
        title: 'Only events measured on all three axes are pooled. By '
             + 'recording: ' + ((f.excluded && f.excluded.by_member) || [])
               .map((x) => ((poolMemberByKey(x.key) || {}).session_label
                            || x.key) + ' ' + x.n).join(', ') }));
    }
    if (reb.length) {
      notes.push(BARRY.ui.chip(reb.length + ' re-banded', {
        kind: 'warn', extra: 'rc-count-rebanded',
        title: reb.map((m) => (m.session_label || m.key) + ': banked over '
          + m.rebanded_from.map(hz).join('–') + ' Hz, measured here over '
          + 'the pool’s band -- its single call is at the pool’s band, not '
          + 'the one that was banked').join('; ') }));
    }
    const memMeasured = (f && f.members) || [];
    return el('div', { class: 'card rc-pool-clusters' }, [
      el('div', { class: 'chip-row' }, notes),
      memMeasured.length ? el('details', { class: 'rc-pool-measured' }, [
        el('summary', { text: 'How each member was measured' }),
        el('table', { class: 'tbl' }, [el('tbody', {}, memMeasured.map((m) => {
          const pp = (m.pin || {}).params || {};
          return el('tr', {}, [
            el('td', { text: m.session_label || m.key }),
            el('td', { text: filterWords(pp, true) + ' · ±' + hz(pp.win_ms)
              + ' ms · ' + hz(pp.band_lo) + '–' + hz(pp.band_hi) + ' Hz'
              + ((m.remeasured || []).length ? ' (measured again here)' : '') }),
            el('td', { class: 'hint', text: (m.pin || {}).single
              ? 'saved v' + m.pin.single.version
              : m.banked ? 'banked' : 'read here' }),
          ]);
        }))]),
      ]) : null,
      clusterChips(f && f.clusters,
        (rank, call) => {
          const dj = rank - ((f && f.k) || 0);
          if (dj >= 0 && pool.drawn[dj]) pool.drawn[dj].call = call;
          else pool.cluster_calls[String(rank)] = call;
          runPool();
        },
        () => { pool.cluster_calls = {}; runPool(); },
        ((f && f.clusters) || []).some((x) => x.call_by === 'hand'),
        { onName: (c) => nameDialog(c, (nm) => {
            if (nm) pool.cluster_names[String(c.rank)] = nm;
            else delete pool.cluster_names[String(c.rank)];
            runPool();
          }),
          onAvg: (c) => showAverage('pooled cluster #' + (c.rank + 1) + ' '
                                     + (c.name || c.call.toUpperCase()),
                                     poolEvents().filter(
                                       (e) => e.cluster === c.rank)),
          onRemove: (c) => { pool.drawn.splice(c.rank - ((f && f.k) || 0), 1);
                             runPool(); } }),
    ].filter(Boolean));
  }

  const pct = (r) => (r == null || !isFinite(r) ? '—'
                      : (100 * r).toFixed(1) + '%');

  function poolTop() {
    const f = pool.fit;
    const c = f.counts || {};
    const sw = f.switches || {};
    const colour = el('select', { class: 'rc-colour',
      onchange: (e) => setColour(e.target.value) },
      COLOURS.filter(([id]) => id !== 'border' || f.border_used)
        .map(([id, nm]) => el('option', { value: id, text: nm,
        selected: pool.colour === id ? 'selected' : null })));
    const mice = Array.from(new Set(poolEvents().map((e) => e.mouse_key)
      .filter(Boolean))).sort(natural);
    const types = Array.from(new Set(poolEvents().map((e) => e.mouse_type)
      .filter(Boolean))).sort(natural);
    const cur = pool.focus ? (pool.focus.mouse_key ? 'mouse_key:' + pool.focus.mouse_key
      : pool.focus.mouse_type ? 'mouse_type:' + pool.focus.mouse_type
      : 'member:' + pool.focus.member) : '';
    const opt = (v, t) => el('option', { value: v, text: t,
                                         selected: cur === v ? 'selected' : null });
    const focus = el('select', { class: 'rc-focus',
      onchange: (e) => {
        const v = e.target.value;
        const at = v.indexOf(':');
        if (!v) { setFocus(null); return; }
        const kind = v.slice(0, at), val = v.slice(at + 1);
        setFocus({ [kind]: val });
      } }, [
      opt('', 'nothing: every dot bright'),
      el('optgroup', { label: 'a mouse' }, mice.map((m) => opt('mouse_key:' + m, m))),
      el('optgroup', { label: 'a mouse type' }, types.map((t) => opt('mouse_type:' + t, t))),
      el('optgroup', { label: 'a recording' }, (f.members || []).map((m) =>
        opt('member:' + m.key, memberName(m)))),
    ]);
    return el('div', { class: 'card rc-why rc-pool-top' }, [
      el('div', { class: 'rc-why-t' }, [
        el('p', { class: 'rc-rule', text: f.rule || '' }),
        el('p', { class: 'hint rc-scale', text:
          'Scale: pooled raw units, z-scored once across the whole pool — so '
          + 'differences in size between mice stay visible, impedance and '
          + 'placement included.' }),
        el('div', { class: 'chip-row' }, [
          chipC('DS ' + (c.ds || 0), 'ds'),
          chipC('IED ' + (c.ied || 0), 'ied'),
          c.unmeasured ? BARRY.ui.chip(c.unmeasured + ' not measured') : null,
          c.partial ? BARRY.ui.chip(c.partial + ' on 2 of 3 axes', { kind: 'warn' })
                    : null,
          c.wide ? BARRY.ui.chip(c.wide + ' by the widened search', { kind: 'warn' })
                 : null,
          BARRY.ui.chip((sw.switched || 0) + ' of ' + (sw.n || 0) + ' switched ('
                        + pct(sw.rate) + ')', { kind: sw.switched ? 'warn' : null,
                                               extra: 'rc-switch-count' }),
          BARRY.ui.chip(f.n_used + ' of ' + f.n + ' clustered on all three axes'),
        ].filter(Boolean)),
      ]),
      el('div', { class: 'rc-pool-ctl' }, [
        BARRY.ui.field({ label: 'Colour by', control: colour, inline: true }),
        BARRY.ui.field({ label: 'Focus', control: focus, inline: true }),
      ]),
    ]);
  }

  function poolPickBar() {
    const e = poolPicked();
    if (!e) {
      return el('div', { class: 'card rc-pickbar' }, [
        el('span', { class: 'hint', text:
          'Click a dot in any view to open that event from its own recording. '
          + '← and → step through the pool.' }),
      ]);
    }
    const m = poolMember(e);
    const n = poolEvents().length;
    return el('div', { class: 'card rc-pickbar' }, [
      el('strong', { text: 'Event ' + (pool.picked + 1) + ' of ' + n }),
      el('span', { class: 'hint', text:
        (m ? memberName(m) : '') + '  ·  ' + (e.mouse_key || '') + ' ('
        + (e.mouse_type || 'no type') + ')  ·  t = ' + fmt(e.t, 3) + ' s  ·  '
        + fmt(e.amp_uV, 0) + ' µV  ·  ' + (e.hw_ms == null || !isFinite(e.hw_ms)
          ? 'half-width unresolved' : fmt(e.hw_ms, 1) + ' ms') + '  ·  '
        + (e.hf_db == null || !isFinite(e.hf_db) ? 'no HF' : fmt(e.hf_db, 1) + ' dB') }),
      el('span', { class: 'hint rc-calls', text:
        'pooled ' + (e.cls_pool ? e.cls_pool.toUpperCase() : '—') + ', single '
        + (e.cls_single ? e.cls_single.toUpperCase() : '—') }),
      e.switched ? BARRY.ui.chip('switched', { kind: 'warn' }) : null,
      e.partial ? BARRY.ui.chip('2 of 3 axes', { kind: 'warn' }) : null,
      e.wide ? BARRY.ui.chip('widened search', { kind: 'warn' }) : null,
      el('span', { class: 'spacer' }),
      BARRY.ui.actions([
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: '◀ prev',
                          title: 'The previous event in the pool. Or ←.',
                          onclick: () => poolStep(-1) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'next ▶',
                          title: 'The next event in the pool. Or →.',
                          onclick: () => poolStep(+1) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: 'Open in Xplorefinder',
          disabled: !recordingHere(m && m.gid),
          title: recordingHere(m && m.gid)
            ? 'That recording at this event, in a window of its own that '
              + 'follows as you step.'
            : 'None of this recording’s paths are reachable from this '
              + 'machine, so there is nothing to look at.',
          onclick: openInXplore }),
      ], { extra: 'rc-acts' }),
    ].filter(Boolean));
  }

  /* One legend per colour mode, and the marks, which mean the same in all
     of them. Tokens only: the swatch is a class, or a palette token. */
  function poolLegend() {
    const item = (cls, text, style) => el('span', { class: 'rc-lg' }, [
      el('i', { class: 'rc-lg-m ' + cls, style: style || null }),
      el('span', { text })]);
    const mode = pool.colour;
    const kids = [el('span', { class: 'rc-lg-h', text: (COLOURS.find(
      ([id]) => id === mode) || [0, ''])[1] + ':' })];
    if (mode === 'border' && pool.fit && pool.fit.border_used) {
      kids.push(item('rc-lg-ds', 'solid DS'), item('rc-lg-ied', 'solid IED'),
                item('rc-lg-amb rc-lg-amb-ds', 'outside, pooled as DS'),
                item('rc-lg-amb rc-lg-amb-ied', 'outside, pooled as IED'));
    } else if (mode === 'pool' || mode === 'single' || mode === 'border') {
      kids.push(item('rc-lg-ds', 'DS'), item('rc-lg-ied', 'IED'));
    } else if (mode === 'switches') {
      kids.push(item('rc-lg-same', 'unchanged'),
                item('rc-lg-d2i', 'DS → IED when pooled'),
                item('rc-lg-i2d', 'IED → DS when pooled'));
    } else {
      const list = catList(mode);
      list.forEach((key, at) => {
        const shape = CAT_SHAPES[Math.floor(at / CAT_N) % CAT_SHAPES.length];
        kids.push(item('rc-lg-cat' + (shape ? ' rc-lg-' + shape : ''),
                       catName(key, mode),
                       'background: var(--c' + ((at % CAT_N) + 1) + ')'));
      });
      if (list.length > CAT_N) {
        kids.push(el('span', { class: 'hint rc-lg-note', text:
          'The theme has ' + CAT_N + ' colours for this; past them the '
          + 'colours come round again and the shape changes each time ('
          + CAT_SHAPE_WORDS.join(', ') + ').' }));
      }
    }
    kids.push(item('rc-lg-flip', 'ringed: switched'),
              item('rc-lg-square', 'on 2 of 3 axes'),
              item('rc-lg-wide', 'half-width by the widened search'),
              item('rc-lg-hollow', 'not measured'),
              item('rc-lg-centre', 'pooled centre'));
    if (pool.focus) kids.push(item('rc-lg-faint', 'faint: outside ' + focusName()));
    return el('div', { class: 'rc-legend rc-pool-legend' }, kids);
  }

  /* ---------- clear vs blur ---------- */
  /* ==================================================================
     ARE THESE CLUSTERS STATISTICALLY DIFFERENT? (2026-10-06)
     ================================================================== */
  /* k-means always finds two clusters when it is asked for two, so a test
     BETWEEN them (a t-test, a MANOVA) says "different" of any cloud at all
     and is not offered. Each test here asks whether ONE cloud would have
     done as well. The answer comes back on the picture itself (`stats` on
     a fit) from the server, which keeps it by what the picture is: a refit
     of the same picture brings it back, a changed one does not, and a
     version saved of it carries it. At k = 2 only: past two there is no
     single yes or no. */
  let statsAbout = null;          // the four tests in words, asked once
  let statsPick = null;           // the tests ticked: all four at first
  let statsBusy = null;           // the level being tested, while it is
  const STATS_LEVEL = { single: 'single recording', pool: 'pool',
                        double: 'pool of pools' };

  async function statsAboutNow() {
    if (!statsAbout) statsAbout = await api('/api/rootcanal/stats/about');
    if (!statsPick) statsPick = (statsAbout.tests || []).slice();
    return statsAbout;
  }

  function statsName(t) {
    return (((statsAbout || {}).about || {})[t] || {}).name || t;
  }

  /* What a test asks, its pro and its con: wherever a test is named. */
  function statsHover(t) {
    const a = ((statsAbout || {}).about || {})[t];
    if (!a) return null;
    return a.name + ' asks: ' + a.asks + '\nPro: ' + a.pro + '\nCon: '
      + a.con + (t === (statsAbout || {}).recommended ? '\nRecommended.' : '');
  }

  /* The picture at a level: its fit, the request that made it, and the
     verdict a saved version of it carried when the answer itself is not
     here (after a restart the server no longer has it). */
  function statsCtx(lvl) {
    if (lvl === 'single') {
      let savedV = null;
      if (viewing && single && viewing.artifact_id === single.artifact_id
          && !isDirty()) {
        const row = (single.versions || []).find((x) => x.v === viewing.v);
        const v = row && (row.n_summary || {}).stats;
        if (v) savedV = { v: row.v, verdict: v };
      }
      /* A version drawn from its saved numbers is asked of by those. */
      const body = savedOnly && viewing
        ? () => ({ single: { artifact_id: viewing.artifact_id,
                             version: viewing.v } })
        : () => lastBody || fitBody();
      return { level: 'single', f: fit, body, savedV };
    }
    return { level: pool.level === 'double' ? 'double' : 'pool',
             f: pool.fit, body: () => pool.lastBody || poolBody(),
             savedV: null };
  }

  function verdictWords(v) {
    return v === 'genuine' ? 'two genuine groups'
      : v === 'could be forced' ? 'could be one group cut in two'
        : 'no verdict';
  }

  function statsLines(st) {
    const T = st.tests || {};
    return ['Are these clusters different? ' + verdictWords(st.verdict)
              + ', by ' + statsName(st.recommended) + ' (recommended).']
      .concat(Object.keys(T).map((t) => statsName(t) + ': '
                                        + (T[t].error || T[t].say)))
      .concat(['Press for the table, and each test’s pros and cons.'])
      .join('\n');
  }

  /* The control: before the tests, the question; after, the answer. Its
     words are short on purpose -- in Single it shares the clusters' row --
     and the hover says the whole of it. */
  const STATS_SAID = { genuine: 'genuine split',
                       'could be forced': 'maybe forced' };

  function statsButton(lvl) {
    const c = statsCtx(lvl);
    const f = c.f;
    if (!f || !f.ok) return null;
    if (!statsAbout) statsAboutNow().catch(() => {});
    if (statsBusy === c.level) {
      return BARRY.ui.chip('testing', { extra: 'rc-stats-go rc-stats-busy',
        title: 'The cluster tests are running: a few seconds.' });
    }
    const st = f.stats || null;
    const verdict = st ? st.verdict : (c.savedV ? c.savedV.verdict : null);
    if (f.k !== 2) {
      // In Single the row has no room to spare for a control that is off.
      if (lvl === 'single') return null;
      return BARRY.ui.button({ kind: 'mini', extra: 'rc-stats-go',
        text: 'Test the split', disabled: true,
        title: 'The tests ask one group or two, so they run at k = 2. This '
             + 'picture has ' + f.k + ' cluster' + (f.k === 1 ? '' : 's')
             + '.' });
    }
    if (!verdict) {
      return BARRY.ui.button({ kind: 'mini', extra: 'rc-stats-go',
        text: 'Test the split',
        title: 'Are these clusters statistically different? k-means always '
             + 'finds two when asked for two. Four tests of whether one '
             + 'cloud would have done as well: pick which, each with its '
             + 'pros and cons. A few seconds.',
        onclick: () => statsDialog(lvl) });
    }
    const ok = verdict === 'genuine';
    return BARRY.ui.button({ kind: 'mini',
      extra: 'rc-stats-go rc-stats-done ' + (ok ? 'ok' : 'warn')
             + (st ? '' : ' rc-stats-saved'),
      text: STATS_SAID[verdict] || verdict,
      title: st ? statsLines(st)
        : 'Saved with v' + c.savedV.v + ': ' + verdictWords(verdict)
          + '. Press to run the tests again and see each one.',
      onclick: () => statsDialog(lvl) });
  }

  async function statsDialog(lvl) {
    try {
      await statsAboutNow();
    } catch (e) {
      toast('The tests could not be described: ' + e.message, 'err', 9000);
      return;
    }
    const f = statsCtx(lvl).f;
    if (f && f.stats) statsShow(lvl, f.stats, false);
    else statsAsk(lvl, false);
  }

  function statsHead() {
    return el('div', { class: 'mh' }, [
      el('h3', { text: 'Are these clusters statistically different?' }),
      el('div', { class: 'spacer' })]);
  }

  /* Which tests: all four offered, the recommended one marked, each one's
     pros and cons on hover. */
  function statsAsk(lvl, replace) {
    const A = statsAbout || {};
    const c = statsCtx(lvl);
    const n = c.f ? c.f.n_used : null;
    const go = BARRY.ui.button({ kind: 'primary', text: 'Run the tests',
      extra: 'rc-stats-run', disabled: !statsPick.length,
      onclick: () => statsRun(lvl) });
    const rows = (A.tests || []).map((t) => {
      const a = (A.about || {})[t] || {};
      return el('label', { class: 'rc-stats-pick', title: statsHover(t) }, [
        el('input', { type: 'checkbox', value: t,
          checked: statsPick.indexOf(t) >= 0 ? 'checked' : null,
          onchange: (e) => {
            statsPick = (A.tests || []).filter((x) => (x === t
              ? e.target.checked : statsPick.indexOf(x) >= 0));
            go.disabled = !statsPick.length;
          } }),
        el('strong', { text: a.name || t }),
        t === A.recommended ? BARRY.ui.chip('recommended',
                                            { kind: 'ok', flag: true }) : null,
        el('span', { class: 'hint', text: a.asks || '' }),
      ].filter(Boolean));
    });
    showModal(el('div', { class: 'rc-stats-dlg' }, [
      statsHead(),
      el('div', { class: 'mb' }, [el('div', { class: 'rc-ask' }, [
        el('p', { text: 'k-means always finds two clusters when it is asked '
          + 'for two. Each test asks whether ONE cloud of events would have '
          + 'done as well. A test between the two clusters, such as a '
          + 't-test, is not offered: k-means makes them differ, so it would '
          + 'say “different” of any cloud.' }),
        el('div', { class: 'rc-stats-picks' }, rows),
        el('p', { class: 'hint', text: 'On the '
          + (n != null ? n + ' ' : '') + 'complete events of this '
          + STATS_LEVEL[c.level] + (n != null && n > A.max_n
            ? ', ' + A.max_n + ' of them drawn for speed (seeded, so the '
              + 'same each time)' : '')
          + '. Simulated: ' + A.n_sim + ' null draws and ' + A.n_boot
          + ' resamples, a few seconds. Hover a test for its pros and '
          + 'cons.' }),
      ])]),
      BARRY.ui.modalFoot([], [
        BARRY.ui.button({ kind: 'ghost', text: 'Cancel',
                          extra: 'rc-stats-cancel', onclick: closeModal }),
        go,
      ]),
    ]), replace ? { replace: true } : undefined);
  }

  async function statsRun(lvl) {
    const c = statsCtx(lvl);
    const f0 = c.f;
    const body = Object.assign({}, c.body(), { level: c.level,
                                               tests: statsPick.slice() });
    statsBusy = c.level;
    showModal(el('div', { class: 'rc-stats-dlg' }, [
      statsHead(),
      el('div', { class: 'mb' }, [loader('Running ' + statsPick.map(statsName)
        .join(', ') + ': a few seconds')]),
    ]), { replace: true });
    render();
    let got;
    try {
      got = await apiPost('/api/rootcanal/stats', body);
    } catch (e) {
      statsBusy = null;
      render();
      statsAsk(lvl, true);
      toast('The tests did not run: ' + e.message, 'err', 12000);
      return null;
    }
    statsBusy = null;
    /* Onto the picture it was asked of, if that is still the one on
       screen; a picture changed meanwhile asks again. */
    if (f0 && statsCtx(lvl).f === f0) f0.stats = got;
    BARRY.activity.log('rootcanal.stats', { level: c.level,
      verdict: got.verdict, n: got.n, tests: Object.keys(got.tests || {}) });
    render();
    statsShow(lvl, got, true);
    return got;
  }

  /* The answer: the recommended test's verdict first, then every test's
     own answer and how it reads, each with its pros and cons on hover. */
  function statsShow(lvl, st, replace) {
    const A = statsAbout || {};
    const T = st.tests || {};
    const rec = st.recommended || A.recommended;
    const order = (A.tests || Object.keys(T)).filter((t) => T[t]);
    const ok = st.verdict === 'genuine';
    const recR = T[rec] || {};
    const head = st.verdict
      ? (ok ? 'Two genuine groups. ' : 'Could be forced. ') + statsName(rec)
        + ', recommended: ' + (recR.say || '') + '.'
      : 'No verdict: the recommended test, ' + statsName(rec) + ', '
        + (recR.error ? 'did not run: ' + recR.error : 'was not asked') + '.';
    const rows = order.map((t) => {
      const r = T[t];
      return el('tr', { title: statsHover(t),
                        class: 'rc-stats-r-' + t + (t === rec ? ' rc-stats-rec'
                                                              : '') }, [
        el('th', {}, [el('span', { text: statsName(t) }),
          t === rec ? BARRY.ui.chip('recommended', { kind: 'ok', flag: true })
                    : null].filter(Boolean)),
        el('td', { text: r.error || r.say || '' }),
        el('td', {}, [r.error ? BARRY.ui.chip('did not run', { flag: true })
          : BARRY.ui.chip(r.genuine ? 'genuine' : 'could be forced',
                          { kind: r.genuine ? 'ok' : 'warn', flag: true })]),
      ]);
    });
    const ran = order.filter((t) => !T[t].error);
    const nGen = ran.filter((t) => T[t].genuine).length;
    showModal(el('div', { class: 'rc-stats-dlg' }, [
      statsHead(),
      el('div', { class: 'mb' }, [el('div', { class: 'rc-ask' }, [
        el('p', { class: 'rc-stats-verdict ' + (st.verdict ? (ok ? 'ok'
                                                                 : 'warn')
                                                           : ''),
                  text: head }),
        el('table', { class: 'tbl rc-stats-tab' }, [
          el('thead', {}, [el('tr', {}, ['test', 'its answer', 'reads as']
            .map((x) => el('th', { text: x })))]),
          el('tbody', {}, rows),
        ]),
        el('p', { class: 'hint', text: nGen + ' of ' + ran.length + ' test'
          + (ran.length === 1 ? '' : 's') + ' read the split as genuine, on '
          + st.n + ' complete events of this ' + (STATS_LEVEL[st.level]
                                                  || 'picture')
          + (st.subsampled ? ' (' + st.n_used + ' of them drawn for speed, '
                             + 'seeded)' : '')
          + '. The verdict is the recommended test’s. A version saved of '
          + 'this picture carries this answer. Hover a test for its pros '
          + 'and cons.' }),
      ])]),
      BARRY.ui.modalFoot([BARRY.ui.button({ kind: 'ghost',
        text: 'Run other tests', extra: 'rc-stats-again',
        onclick: () => statsAsk(lvl, true) })], [
        BARRY.ui.button({ kind: 'primary', text: 'Close',
                          extra: 'rc-stats-close', onclick: closeModal }),
      ]),
    ]), replace ? { replace: true } : undefined);
  }

  function gmmBlock(g, title, cls) {
    const kids = [el('strong', { text: title })];
    const finiteN = (v) => v != null && isFinite(v);
    if (!g || !(finiteN(g.bic1) && finiteN(g.bic2))) {
      /* Fewer than twenty complete events and the server says so in a
         sentence instead of numbers: two components fitted to a dozen
         points is a number that means nothing. */
      kids.push(el('p', { class: 'rc-verdict', text: (g && (g.verdict
        || g.sentence || g.reason || g.error))
        || 'Not enough complete events here for the test.' }));
      return el('div', { class: 'rc-gmm-b' + (cls ? ' ' + cls : '') }, kids);
    }
    kids.push(el('p', { class: 'rc-verdict', text: g.verdict || '' }));
    if (g.support) {
      kids.push(BARRY.ui.chip(g.support, { extra: 'rc-gmm-support' }));
    }
    const num = (v) => (v == null || !isFinite(v) ? '—' : Number(v).toFixed(1));
    kids.push(el('table', { class: 'tbl rc-gmm-tab' }, [
      el('tbody', {}, [
        el('tr', {}, [el('th', { text: 'BIC, one group' }), el('td', { text: num(g.bic1) })]),
        el('tr', {}, [el('th', { text: 'BIC, two groups' }), el('td', { text: num(g.bic2) })]),
        el('tr', {}, [el('th', { text: 'ΔBIC = BIC1 − BIC2' }),
                      el('td', { text: num(g.delta) })]),
        el('tr', {}, [el('th', { text: 'complete events' }),
                      el('td', { text: String(g.n != null ? g.n : '—') })]),
      ]),
    ]));
    /* WHETHER THE TWO COMPONENTS ARE THE TWO KINDS OF EVENT. A large ΔBIC
       says two Gaussians fit better than one; it does not say they are the
       DS/IED split -- two Gaussians fit a skewed cloud too. The adjusted
       Rand index between the components and the k-means call says which,
       and it sits beside ΔBIC so neither is read without the other. */
    const ag = g.agree;
    if (ag && ag.ari != null && isFinite(ag.ari)) {
      kids.push(el('table', { class: 'tbl rc-gmm-tab rc-gmm-agree' }, [
        el('tbody', {}, [el('tr', {}, [
          el('th', { text: 'agreement with the DS / IED call (adjusted Rand, '
                         + '1 = same split, 0 = chance)' }),
          el('td', { text: Number(ag.ari).toFixed(2) }),
        ])]),
      ]));
      const x = ag.crosstab || {};
      const n2 = (a, b) => String(((x[a] || {})[b]) || 0);
      kids.push(el('table', { class: 'tbl rc-gmm-tab rc-gmm-x' }, [
        el('thead', {}, [el('tr', {}, ['k-means call ↓  GMM component →',
                                       'DS-like', 'IED-like']
          .map((t) => el('th', { text: t })))]),
        el('tbody', {}, [
          el('tr', {}, [el('th', { text: 'DS' }), el('td', { text: n2('ds', 'ds_like') }),
                        el('td', { text: n2('ds', 'ied_like') })]),
          el('tr', {}, [el('th', { text: 'IED' }), el('td', { text: n2('ied', 'ds_like') }),
                        el('td', { text: n2('ied', 'ied_like') })]),
        ]),
      ]));
    }
    const ws = g.weights || [], ms = g.means_raw || [];
    if (ws.length) {
      kids.push(el('table', { class: 'tbl rc-gmm-tab rc-gmm-comp' }, [
        el('thead', {}, [el('tr', {}, ['component', 'weight', 'amp · µV',
                                       'half-width · ms', 'HF · dB']
          .map((t) => el('th', { text: t })))]),
        el('tbody', {}, ws.map((w, j) => el('tr', {}, [
          el('td', { text: String(j + 1) }),
          el('td', { text: pct(w) }),
          el('td', { text: fmt((ms[j] || [])[0], 0) }),
          el('td', { text: fmt((ms[j] || [])[1], 1) }),
          el('td', { text: fmt((ms[j] || [])[2], 1) }),
        ]))),
      ]));
    }
    return el('div', { class: 'rc-gmm-b' + (cls ? ' ' + cls : '') }, kids);
  }

  const HISTS = [
    ['rcHistA', 0, 'Max amplitude'],
    ['rcHistH', 1, 'Half-width'],
    ['rcHistF', 2, 'HF power'],
    ['rcHistS', 's', 'The split axis'],
  ];

  function gmmPanel() {
    const f = pool.fit;
    const fg = pool.focus && (pool.focus.mouse_key || pool.focus.mouse_type);
    return el('div', { class: 'card rc-gmm' }, [
      el('div', { class: 'section-label', text: 'Two clear groups, or one spectrum?' }),
      el('div', { class: 'chip-row rc-stats-row' },
         [statsButton('pool')].filter(Boolean)),
      el('div', { class: 'rc-gmm-row' }, [
        gmmBlock(f.gmm, 'The whole pool', 'rc-gmm-pool'),
        /* The visual check the sentence points at, right beside it: two
           humps either side of 0 is two groups; one hump cut by it is one. */
        histCell('rcHistS', 'The split axis', 'rc-hist-split'),
        fg ? (pool.fitting || (f.gmm_focus === undefined)
              ? el('div', { class: 'rc-gmm-b rc-gmm-focus' }, [
                  el('strong', { text: 'Focused: ' + focusName() + ' alone' }),
                  loader('Testing ' + focusName() + ' on its own'),
                ])
              : gmmBlock(f.gmm_focus, 'Focused: ' + focusName() + ' alone',
                         'rc-gmm-focus'))
           : null,
      ].filter(Boolean)),
      el('p', { class: 'hint', text:
        'A Gaussian mixture with one component against one with two, compared '
        + 'by BIC on the complete events in the pooled z-space; a positive ΔBIC '
        + 'favours two groups. BIC compares Gaussian shapes: one skewed cloud '
        + 'can earn two components, so this is evidence, not proof.' }),
      el('div', { class: 'rc-hists' }, HISTS.filter(([id]) => id !== 'rcHistS')
        .map(([id, , title]) => histCell(id, title))),
    ]);
  }

  function histCell(id, title, extra) {
    return el('div', { class: 'rc-ev-cell' + (extra ? ' ' + extra : '') }, [
      el('div', { class: 'rc-ev-t' }, [
        el('strong', { text: title }),
        el('span', { class: 'hint', text: 'split by pooled call' }),
      ]),
      el('canvas', { class: 'rc-canvas rc-hist', id }),
    ]);
  }

  /* A histogram per axis, and one along the line through the two k-means
     centres: the visual half of the question. Two groups make two humps on
     that line; one spectrum makes one, cut in the middle. */
  function drawPoolHists() {
    const f = pool.fit;
    if (!f || !f.ok) return;
    const evs = poolEvents();
    const S = poolScene();
    const split = ((f.split_axis || {}).values) || [];
    for (const [id, a] of HISTS) {
      const vals = a === 's' ? evs.map((e, j) => split[j]) : evs.map((e) => e[KEYS[a]]);
      const xl = a === 's' ? 'split axis · z, 0 midway between the two centres'
                           : axisLabel(a, S.params);
      drawHist(id, vals, evs.map((e) => e.cls_pool), xl, a === 's');
    }
  }

  function drawHist(id, vals, cls, xl, isSplit) {
    const s = sized(id, 150);
    if (!s) return;
    const k = ink();
    const g = s.g;
    const fin = [];
    vals.forEach((v, j) => {
      if (v != null && isFinite(v) && cls[j]) fin.push([Number(v), cls[j]]);
    });
    let lo = Infinity, hi = -Infinity;
    for (const [v] of fin) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    if (!(hi > lo)) hi = lo + 1;
    const NB = 24;
    const w = (hi - lo) / NB;
    const ds = new Array(NB).fill(0), ied = new Array(NB).fill(0);
    for (const [v, c] of fin) {
      const b = Math.min(NB - 1, Math.max(0, Math.floor((v - lo) / w)));
      if (c === 'ied') ied[b] += 1; else ds[b] += 1;
    }
    const top = Math.max(1, Math.max.apply(null, ds.concat(ied)));
    // The axes and both labels first, whatever there is to draw: an empty
    // histogram still says what it would have shown.
    const F = frame(s, k, [lo, hi], [0, top * 1.08], xl, 'events');
    if (!fin.length) {
      g.fillStyle = k.dim;
      g.font = FONT(9.5);
      g.fillText('no events with a value here', F.x0 + 6, F.y0 + 14);
    }
    for (const [arr, col] of [[ds, colOf('ds')], [ied, colOf('ied')]]) {
      g.fillStyle = col;
      g.strokeStyle = col;
      for (let b = 0; b < NB; b++) {
        if (!arr[b]) continue;
        const x0 = F.X(lo + b * w), x1 = F.X(lo + (b + 1) * w);
        const y = F.Y(arr[b]);
        g.globalAlpha = 0.45;
        g.fillRect(x0, y, Math.max(1, x1 - x0 - 0.5), F.y1 - y);
        g.globalAlpha = 1;
        g.lineWidth = 1;
        g.strokeRect(x0, y, Math.max(1, x1 - x0 - 0.5), F.y1 - y);
      }
    }
    g.font = FONT(9);
    if (isSplit) {
      /* 0 is the midpoint between the two centres; the DS centre is on the
         negative side and the IED one on the positive. Two humps either
         side of the line is two groups; one hump cut by it is one. */
      if (lo < 0 && hi > 0) {
        g.strokeStyle = k.text;
        g.lineWidth = 1;
        g.setLineDash([3, 3]);
        g.beginPath(); g.moveTo(F.X(0), F.y0); g.lineTo(F.X(0), F.y1); g.stroke();
        g.setLineDash([]);
      }
      g.fillStyle = colOf('ds');
      g.textAlign = 'left';
      g.fillText('← DS side', F.x0 + 4, F.y0 + 11);
      g.fillStyle = colOf('ied');
      g.textAlign = 'right';
      g.fillText('IED side →', F.x1 - 4, F.y0 + 11);
      g.textAlign = 'left';
    } else {
      g.fillStyle = colOf('ds');
      g.fillText('DS', F.x1 - 44, F.y0 + 11);
      g.fillStyle = colOf('ied');
      g.fillText('IED', F.x1 - 24, F.y0 + 11);
    }
    GEOM.hist = GEOM.hist || {};
    GEOM.hist[id] = { xl, yl: 'events', n: fin.length, lo, hi,
                      ds: ds.reduce((x, y) => x + y, 0),
                      ied: ied.reduce((x, y) => x + y, 0) };
  }

  /* ==================================================================
     THE DEEP DIVE (2026-10-06, steps 7-10)
     ================================================================== */
  /* Every event whose identity does not sit still: switched at this level,
     or ambiguous under the border applied. Gathered by the server from the
     picture's own request, so each row's `j` is its dot. A refit is a
     different picture, and the dive is gathered again for it. */
  const DEEP_GROUPS = [['mouse_key', 'mouse'], ['mouse_type', 'mouse type'],
                       ['group', 'group'], ['subgroup', 'subgroup'],
                       ['condition', 'condition']];

  const deepSig = () => JSON.stringify(pool.lastBody || null);

  function deepNoun() {
    return pool.level === 'double' ? 'pool of pools' : 'pool';
  }

  function deepSource() {
    return pool.saved && pool.open
      ? { artifact_id: pool.open.artifact_id,
          version: (pool.open.source || {}).version || pool.open.version }
      : null;
  }

  function swapDeep() {
    if (!swap('.rc-deep', deepPanel())) render();
    const on = host() && host().querySelector('.rc-deep tr.on');
    if (on && on.scrollIntoView) on.scrollIntoView({ block: 'nearest' });
  }

  async function loadDeep() {
    const body = Object.assign({}, pool.lastBody || poolBody(),
                               { level: pool.level === 'double' ? 'double'
                                                                : 'pool' });
    const sig = deepSig();
    pool.deep = { for: sig, busy: true, filter: 'all', at: -1,
                  group: (pool.deep && pool.deep.group) || 'mouse_key' };
    swapDeep();
    let got;
    try {
      got = await apiPost('/api/rootcanal/switches', body);
    } catch (e) {
      if (deepSig() !== sig) return null;
      pool.deep = { for: null, err: e.message };
      swapDeep();
      return null;
    }
    // The picture changed while it was gathered: that answer is not its.
    if (deepSig() !== sig || !pool.deep) return null;
    Object.assign(pool.deep, got, { busy: false });
    BARRY.activity.log('rootcanal.deep_open', { level: got.level,
                                                rows: (got.counts || {}).rows });
    swapDeep();
    return got;
  }

  function deepRows() {
    const d = pool.deep;
    const rs = (d && d.rows) || [];
    if (!d || d.filter === 'all') return rs;
    if (d.filter === 'switched') return rs.filter((r) => r.switch);
    return rs.filter((r) => r.border === 'amb');
  }

  /* Step to the k-th listed event: its dot picked, its traces opened, and
     Xplorefinder following, as for any dot. */
  function deepPick(k) {
    const rs = deepRows();
    const d = pool.deep;
    if (!rs.length || !d) return;
    d.at = ((k % rs.length) + rs.length) % rs.length;
    poolPick(rs[d.at].j);
    swapDeep();
  }

  function deepCsv() {
    const d = pool.deep;
    if (!d || !d.csv) return;
    const nick = pool.open && pool.open.nickname
      ? String(pool.open.nickname).replace(/[^\w.-]+/g, '_') : deepNoun()
        .replace(/ /g, '-');
    const name = 'rootcanal-deep-dive-' + nick + '.csv';
    // A byte-order mark, so a spreadsheet reads the µ and the arrows.
    BARRY.saveText(name, '\ufeff' + d.csv, 'text/csv;charset=utf-8');
    BARRY.activity.log('rootcanal.deep_csv', { rows: (d.rows || []).length });
    toast('Saved ' + name + ': ' + (d.rows || []).length + ' events.', 'ok',
          6000);
  }

  function deepBank() {
    const d = pool.deep;
    if (!d || !d.counts) return;
    const c = d.counts;
    const src = deepSource();
    const noun = deepNoun();
    const note = el('textarea', { class: 'rc-in rc-deep-note', rows: '2',
      'aria-label': 'a note for the entries',
      placeholder: 'A note for the entries, if any' });
    showModal(el('div', { class: 'rc-deep-dlg' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Bank the ' + c.rows + ' events?' }),
        el('div', { class: 'spacer' })]),
      el('div', { class: 'mb' }, [el('div', { class: 'rc-ask' }, [
        el('p', { text: 'One Event Bank entry per recording ('
          + c.recordings + '), named “Switching and ambiguous events (Root '
          + 'Canal)”, from ' + (src ? 'the saved ' + noun + ' ‘'
            + pool.open.nickname + '’'
            : 'this ' + noun + ', which is not saved: save it first for the '
              + 'entries to name it') + '.' }),
        el('ul', {}, [
          el('li', { text: 'Of type “Ambiguous DS / IED”, never DS or IED: '
            + 'nothing that reads a recording’s DS set or its IED candidates '
            + 'picks these up.' }),
          el('li', { text: 'Each stamp keeps what the recording’s own set has '
            + 'at that time. Why it is here -- its calls, its border class, '
            + 'its numbers -- is kept with the entry.' }),
          el('li', { text: 'Banking again from the same source adds a version '
            + 'to the same entries.' }),
        ]),
        note,
      ])]),
      BARRY.ui.modalFoot([], [
        BARRY.ui.button({ kind: 'ghost', text: 'Cancel',
                          extra: 'rc-deep-bank-no', onclick: closeModal }),
        BARRY.ui.button({ kind: 'primary', text: 'Bank ' + c.rows + ' events',
          extra: 'rc-deep-bank-yes', onclick: async () => {
            closeModal();
            let got;
            try {
              got = await apiPost('/api/rootcanal/switches/bank',
                Object.assign({}, pool.lastBody || poolBody(), {
                  level: d.level, source: src, note: note.value || '',
                  by: (BARRY.profile && BARRY.profile.who
                       && BARRY.profile.who()) || '' }));
            } catch (e) {
              toast('Nothing was banked: ' + e.message, 'err', 12000);
              return;
            }
            const made = got.made || [];
            const left = got.left || [];
            d.banked = got;
            toast('Banked ' + made.reduce((a, m) => a + m.n, 0) + ' events in '
              + made.length + ' entr' + (made.length === 1 ? 'y' : 'ies')
              + (left.length ? '; not banked: ' + left.map((x) =>
                x.session_label + ' (' + x.why + ')').join('; ') : '') + '.',
              left.length ? 'warn' : 'ok', 14000);
            BARRY.activity.log('rootcanal.deep_bank', { entries: made.length,
                                                        left: left.length });
            swapDeep();
          } }),
      ]),
    ]));
  }

  function deepPanel() {
    const f = pool.fit;
    if (!f || !f.ok) return el('div', { class: 'rc-deep' });
    const dbl = f.level === 'double';
    const d = pool.deep;
    const kids = [el('div', { class: 'section-label', text: 'The deep dive: '
      + 'the events whose identity does not sit still' })];
    const fresh = d && !d.err && d.for === deepSig();
    if (!fresh || d.busy) {
      kids.push(el('p', { class: 'hint', text: 'Every event that switched '
        + 'identity ' + (dbl ? 'between its own pool (v0) and this pool of pools'
                             : 'between its single and this pool')
        + (f.border_used ? ', and every one the border ‘'
                           + f.border_used.nickname + '’ leaves ambiguous'
                         : ' (apply a border, in the Borders card above, to '
                           + 'add the ones it leaves ambiguous)')
        + '. Step through them with their traces, average them, see where '
        + 'they come from by mouse, type, group, subgroup and condition, '
        + 'export them as a CSV and bank them.' }));
      kids.push(el('p', { class: 'hint rc-deep-recipe', text: 'Steps 7–10: '
        + 'pool the controls with “every event is DS”, pool the IED mice at '
        + 'k = 2, pool those two pools (“Pool pools”), draw a border from the '
        + 'identity switches, apply it, then open this.' }));
      if (d && d.err) {
        kids.push(el('p', { class: 'hint rc-warn rc-deep-err',
                            text: 'Not gathered: ' + d.err }));
      }
      kids.push(d && d.busy && fresh ? loader('Gathering the events')
        : BARRY.ui.actions([BARRY.ui.button({ kind: 'ghost', size: 'sm',
            text: 'Open the deep dive', extra: 'rc-deep-go',
            onclick: loadDeep })]));
      return el('div', { class: 'card rc-deep' }, kids);
    }
    const c = d.counts || {};
    const bu = d.border_used;
    kids.push(el('p', { class: 'rc-deep-count', text: c.rows + ' of ' + c.n
      + ' events: ' + c.switched + ' switched (' + c.ds_to_ied + ' DS → IED, '
      + c.ied_to_ds + ' IED → DS)'
      + (bu ? ', ' + c.ambiguous + ' ambiguous under the border ‘'
              + bu.nickname + '’ at grace ' + bu.grace_words : '')
      + ', from ' + c.recordings + ' recording'
      + (c.recordings === 1 ? '' : 's') + '. An event can be both.' }));
    const items = [['all', 'all ' + c.rows], ['switched', 'switched ' + c.switched]];
    if (bu) items.push(['ambiguous', 'ambiguous ' + c.ambiguous]);
    const rs = deepRows();
    kids.push(el('div', { class: 'chip-row rc-deep-bar' }, [
      BARRY.ui.seg(items, d.filter, (v) => { d.filter = v; d.at = -1; swapDeep(); },
                   { extra: 'rc-deep-filter' }),
      BARRY.ui.button({ kind: 'mini', text: '◀', extra: 'rc-deep-prev',
        title: 'The one before: its dot, its traces.', disabled: !rs.length,
        onclick: () => deepPick(d.at < 0 ? rs.length - 1 : d.at - 1) }),
      el('span', { class: 'rc-deep-at', text: d.at >= 0 && rs.length
        ? (d.at + 1) + ' of ' + rs.length : rs.length + ' listed' }),
      BARRY.ui.button({ kind: 'mini', text: '▶', extra: 'rc-deep-next',
        title: 'The next one: its dot, its traces.', disabled: !rs.length,
        onclick: () => deepPick(d.at + 1) }),
      BARRY.ui.button({ kind: 'mini', text: 'Average these ' + rs.length,
        extra: 'rc-deep-avg', disabled: !rs.length,
        onclick: () => {
          const evs = poolEvents();
          showAverage('deep dive · ' + d.filter, rs.map((r) => evs[r.j])
            .filter(Boolean));
        } }),
      BARRY.ui.button({ kind: 'mini', text: 'Export all ' + c.rows + ' as CSV',
        extra: 'rc-deep-csv', disabled: !c.rows, onclick: deepCsv }),
      BARRY.ui.button({ kind: 'mini', text: 'Bank all ' + c.rows + '…',
        extra: 'rc-deep-bank', disabled: !c.rows, onclick: deepBank }),
    ]));
    if (d.banked) {
      const mk = d.banked.made || [];
      kids.push(el('p', { class: 'hint rc-deep-banked', text: 'Banked: '
        + mk.map((m) => m.session_label + ' ' + m.n + (m.replaced
          ? ' (a new version)' : '')).join(', ')
        + ((d.banked.left || []).length ? '. Not banked: ' + d.banked.left
          .map((x) => x.session_label + ', ' + x.why).join('; ') : '') + '.' }));
    }
    const callTd = (v) => el('td', { class: v ? 'rc-call-' + v : null,
                                     text: v ? v.toUpperCase() : '—' });
    const head = ['session', 't · s', 'amp · µV', 'hw · ms', 'HF · dB',
                  'single', dbl ? 'pool (v0)' : 'pool',
                  dbl ? 'pool of pools' : null, bu ? 'border' : null, 'why']
      .filter(Boolean);
    kids.push(el('div', { class: 'rc-deep-scroll' }, [
      el('table', { class: 'tbl rc-deep-tab' }, [
        el('thead', {}, [el('tr', {}, head.map((h) => el('th', { text: h })))]),
        el('tbody', {}, rs.map((r, k) => el('tr', {
          class: 'rc-deep-row' + (k === d.at ? ' on' : ''),
          'data-j': String(r.j), title: 'Pick this event: its dot and traces.',
          onclick: () => deepPick(k) }, [
          el('td', { text: r.session_label || r.gid || '?' }),
          el('td', { text: fmt(r.t, 3) }),
          el('td', { text: fmt(r.amp_uV, 0) }),
          el('td', { text: fmt(r.hw_ms, 1) }),
          el('td', { text: fmt(r.hf_db, 1) }),
          callTd(r.single), callTd(r.pool), dbl ? callTd(r.double) : null,
          bu ? el('td', { text: r.border === 'amb' ? 'ambiguous'
            : r.border ? 'solid ' + r.border.toUpperCase() : '—' }) : null,
          el('td', { text: (r.why || []).join('; ') }),
        ].filter(Boolean)))),
      ])]));
    const sm = (d.summary || {})[d.group] || { rows: [] };
    kids.push(el('div', { class: 'chip-row rc-deep-sumbar' }, [
      el('strong', { text: 'Where they come from, by' }),
      BARRY.ui.seg(DEEP_GROUPS, d.group, (v) => { d.group = v; swapDeep(); },
                   { extra: 'rc-deep-group' })]));
    kids.push(el('div', { class: 'rc-deep-scroll rc-deep-sumwrap' }, [
      el('table', { class: 'tbl rc-deep-sum' }, [
        el('thead', {}, [el('tr', {}, [sm.label || d.group, 'recordings', 'events',
          'switched', 'DS → IED', 'IED → DS', bu ? 'ambiguous' : null]
          .filter(Boolean).map((h) => el('th', { text: h })))]),
        el('tbody', {}, (sm.rows || []).map((x) => el('tr', {}, [
          el('td', { text: x.value }),
          el('td', { text: String(x.recordings) }),
          el('td', { text: String(x.n) }),
          el('td', { text: x.switched + ' (' + pct(x.switch_rate) + ')' }),
          el('td', { text: String(x.ds_to_ied) }),
          el('td', { text: String(x.ied_to_ds) }),
          bu ? el('td', { text: x.ambiguous + ' (' + pct(x.ambiguous_rate) + ')' })
             : null,
        ].filter(Boolean)))),
      ])]));
    kids.push(el('p', { class: 'hint', text: 'Group, subgroup and condition '
      + 'are the lab’s session workbook’s, the mouse book’s where it is '
      + 'silent, and “not recorded” where neither says. Each rate is of that '
      + 'row’s own events.' }));
    return el('div', { class: 'card rc-deep' }, kids);
  }

  /* ---------- identity switches ---------- */
  function switchPanel() {
    const sw = (pool.fit && pool.fit.switches) || {};
    const ct = sw.crosstab || {};
    const cell = (a, b) => String(((ct[a] || {})[b]) || 0);
    const rowsOf = (list, keyOf, nameOf, focusOf, isOn) => (list || []).map((r) => {
      const on = isOn(r);
      return el('tr', { class: on ? 'on' : null }, [
        el('td', {}, [BARRY.ui.button({ kind: 'mini', text: nameOf(r),
          extra: 'rc-focus-row',
          title: on ? 'Focused. Press again to clear the focus.'
                    : 'Focus this one: its dots stay bright and the rest go faint.',
          onclick: () => setFocus(on ? null : focusOf(r)) })]),
        el('td', { text: String(r.n != null ? r.n : '') }),
        el('td', { text: String(r.switched != null ? r.switched : '') }),
        el('td', { text: pct(r.rate) }),
        el('td', { text: String(r.ds_to_ied != null ? r.ds_to_ied : '') }),
        el('td', { text: String(r.ied_to_ds != null ? r.ied_to_ds : '') }),
      ]);
    });
    const table = (title, rows) => el('div', { class: 'rc-sw-t' }, [
      el('strong', { text: title }),
      el('table', { class: 'tbl rc-sw-tab' }, [
        el('thead', {}, [el('tr', {}, ['', 'events', 'switched', 'rate',
                                       'DS → IED', 'IED → DS']
          .map((t) => el('th', { text: t })))]),
        el('tbody', {}, rows),
      ]),
    ]);
    const f = pool.focus || {};
    const members = (pool.fit && pool.fit.members) || [];
    const dbl = !!(pool.fit && pool.fit.level === 'double');
    const sw2 = dbl ? (pool.fit.switches_single || {}) : null;
    return el('div', { class: 'card rc-switch' }, [
      el('div', { class: 'section-label', text: dbl
        ? 'Identity switches: each event’s call in its own pool (v0) against '
          + 'the pool of pools'
        : 'Identity switches: each event’s own call against the pooled one' }),
      sw2 ? el('p', { class: 'hint rc-sw-single', text: 'Against its single '
        + 'instead: ' + (sw2.switched || 0) + ' of ' + (sw2.n || 0) + ' ('
        + pct(sw2.rate) + ') -- ' + (sw2.ds_to_ied || 0) + ' DS → IED, '
        + (sw2.ied_to_ds || 0) + ' IED → DS.' }) : null,
      /* Steps 8-9: the border between these identities, with grace. */
      el('div', { class: 'chip-row rc-border-go-row' }, [
        BARRY.ui.button({ kind: 'mini', extra: 'rc-border-go',
          text: 'Draw a border from these identities…',
          title: 'Three cut-offs, in µV, dB and ms, between the events’ own '
               + 'identities (' + (dbl ? 'their own pools’ calls'
                                       : 'their singles’ calls')
               + '): past all three is solid IED, short of all three solid '
               + 'DS, anything else ambiguous. With grace, the switch rate '
               + 'allowed. Previewed before it is saved. A pool that is all '
               + 'one identity gets a box drawn around it instead.',
          onclick: borderDialog })]),
      el('div', { class: 'rc-sw-top' }, [
        el('table', { class: 'tbl rc-crosstab' }, [
          el('thead', {}, [el('tr', {}, [(pool.fit && pool.fit.level === 'double'
              ? 'pool ↓  double →' : 'single ↓  pooled →'), 'DS', 'IED']
            .map((t) => el('th', { text: t })))]),
          el('tbody', {}, [
            el('tr', {}, [el('th', { text: 'DS' }), el('td', { text: cell('ds', 'ds') }),
                          el('td', { class: 'rc-sw-off', text: cell('ds', 'ied') })]),
            el('tr', {}, [el('th', { text: 'IED' }),
                          el('td', { class: 'rc-sw-off', text: cell('ied', 'ds') }),
                          el('td', { text: cell('ied', 'ied') })]),
          ]),
        ]),
        el('p', { class: 'rc-sw-rate', text: (sw.switched || 0) + ' of '
          + (sw.n || 0) + ' events (' + pct(sw.rate) + ') changed class when '
          + 'pooled. The two off the diagonal are the switches; each switched '
          + 'dot is ringed in every colour mode.' }),
      ]),
      el('div', { class: 'rc-sw-tables' }, [
        table('By recording', rowsOf(sw.by_member, (r) => r.key, (r) => {
          const m = members.find((x) => x.key === r.key);
          return m ? memberName(m) : r.key;
        }, (r) => ({ member: r.key }), (r) => f.member === r.key)),
        table('By mouse', rowsOf(sw.by_mouse, (r) => r.mouse_key,
          (r) => r.mouse_key, (r) => ({ mouse_key: r.mouse_key }),
          (r) => f.mouse_key === r.mouse_key)),
        table('By mouse type', rowsOf(sw.by_type, (r) => r.mouse_type,
          (r) => r.mouse_type || 'no type', (r) => ({ mouse_type: r.mouse_type }),
          (r) => f.mouse_type === r.mouse_type)),
      ]),
    ]);
  }

  /* ---------- saving, and the shelf ---------- */
  /* Saved through the one bank dialog (constitution §6e), with its no-empty
     -name rule: the LABEL is the artifact's nickname and is required; the
     name is the server's, from what is in the pool. The server refits from
     the members -- it never trusts a picture -- and a re-save that changes
     nothing is a confirmation, not a version. */
  function saveDialog() {
    if (!pool.sel.length) return Promise.resolve(null);
    /* A NEW pool is filed as it is saved (2026-10-20): in the folder the
       last pool opened was in, unless another is picked. A new version of
       one stays where its pool is. */
    const isNew = !pool.open;
    const folders = isNew ? poolFolders() : [];
    const hint = pool.folderHint != null && (pool.folderHint === ''
      || folders.some((f) => f.id === pool.folderHint)) ? pool.folderHint : '';
    const folderPick = isNew ? el('select', {
      class: 'rc-in rc-save-folder', 'aria-label': 'Folder' },
      folders.map((f) => el('option', { value: f.id, text: f.name,
        selected: f.id === hint ? 'selected' : null }))
        .concat([el('option', { value: '', text: 'Not in a folder',
                                selected: hint ? null : 'selected' })])) : null;
    const members = pool.fit && pool.fit.ok ? (pool.fit.members || []) : [];
    const nUnb = members.length ? unbankedOf(members)
      : pool.sel.filter((m) => { const c = candOf(m.key); return c && !c.banked; }).length;
    const what = el('div', { class: 'rc-ask' }, [
      el('p', { text: pool.open
        ? 'Saves this pool as v' + nextPoolVersion() + ' of ‘' + pool.open.nickname
          + '’. If nothing about it has changed since v' + pool.open.version
          + ', that version is confirmed instead and no new one is made.'
        : 'Saves this pool as a new Jarvis artifact, under the label you give '
          + 'it here.' }),
      el('ul', {}, [
        el('li', { text: pool.sel.length + ' recording(s), each pinned: a banked '
          + 'one by its version and result, an unbanked one by its read, its '
          + 'settings and the rows they produced.' }),
        el('li', { text: 'Refitted on the server from those members, then every '
          + 'dot, the centres, the group test and the switch tables are kept, so '
          + 'it reopens with no recording read.' }),
        nUnb ? el('li', { class: 'rc-warn', text: nUnb + ' member(s) are not '
          + 'banked: the pool can only be rebuilt while their reads are on this '
          + 'machine.' }) : null,
        el('li', { text: 'Nothing is written to the Event Bank.' }),
      ].filter(Boolean)),
      folderPick ? el('label', { class: 'rc-save-folder-row' }, [
        el('span', { class: 'section-label', text: 'Folder' }), folderPick,
      ]) : null,
    ].filter(Boolean));
    let rep = null;
    let into = null;
    return BARRY.ui.bankDialog({
      kind: 'entry',
      title: pool.open ? 'Save v' + nextPoolVersion() + ' of ‘' + pool.open.nickname + '’'
                       : 'Save this pool',
      // The label typed last time, when a refused save comes back.
      name: pool.open ? pool.open.nickname : (pool.lastNick || ''),
      what,
      okText: pool.open ? 'Save as v' + nextPoolVersion() : 'Save pool',
      onBank: async ({ name, note }) => {
        const nick = String(name || '').trim();
        if (!nick) throw new Error('A pool needs a label to be saved under.');
        into = folderPick ? folderPick.value : null;
        /* EVERYTHING THE PICTURE WAS MADE WITH. This sent the members,
           the types and the focus alone, and the server refitted at its
           defaults: a pool shown at k = 1 was saved at k = 2, and its
           relabels, margin, drawn clusters and measurement were lost. */
        try {
          rep = await apiPost(pool.level === 'double'
            ? '/api/rootcanal/dpool/save' : '/api/rootcanal/pool/save', Object.assign(
            poolBody(), {
              artifact_id: pool.open ? pool.open.artifact_id : null,
              nickname: nick,
              // The whole focus, a recording's included: it is the saved
              // pool's to reopen with, not only the server's second test.
              focus: pool.focus,
              note: note || '',
            }));
        } catch (e) {
          /* A SAVE REFUSED ABOUT MEMBERS (2026-10-19) -- "banked measured
             differently, and its read is not on this machine" -- is not a
             dead end: the dialog closes and the pool's card says it, with
             "Read them here and redo the analysis", which opens this
             dialog again once the pool has been fitted. */
          const away = (e.data && e.data.away) || [];
          if (!away.length) throw e;
          pool.refusal = { error: e.message, away: away.slice(), from: 'save' };
          pool.lastNick = nick;
          rep = null;
        }
      },
    }).then((ok) => {
      if (pool.refusal && pool.refusal.from === 'save' && !rep) {
        goScreen('view');
        return null;
      }
      if (!ok || !rep) return null;
      pool.lastNick = '';
      /* Filed before the shelf is read again, so it is drawn where it
         goes. Only a pool this save made: one it confirmed already had a
         place. */
      if (isNew && into !== null && !rep.confirmed
          && !Object.prototype.hasOwnProperty.call(prefMap(IN_KEY),
                                                   rep.artifact_id)) {
        putInFolder(rep.artifact_id, into, true);
        pool.folderHint = into;
      }
      afterSave(rep);
      if (!rep.confirmed) {
        if (pool.level === 'double') dpropagateDialog(rep);
        else propagateDialog(rep);
      }
      return rep;
    });
  }

  function afterSave(rep) {
    pool.open = {
      artifact_id: rep.artifact_id, version: rep.version,
      nickname: rep.nickname, name: rep.name,
      by: (pool.open && pool.open.by) || null, updated: null,
      source: { artifact_id: rep.artifact_id, version: rep.version },
    };
    pool.savedMembers = ((pool.fit && pool.fit.members) || []).slice();
    toast(rep.confirmed
      ? 'Nothing has changed since v' + rep.version + ' of ‘' + rep.nickname
        + '’, so that version is confirmed rather than a new one made.'
      : 'Saved as v' + rep.version + ' of ‘' + rep.nickname + '’.',
      rep.confirmed ? 'warn' : 'ok', 8000);
    BARRY.activity.log('rootcanal.pool_save', {
      artifact: rep.artifact_id, version: rep.version, confirmed: !!rep.confirmed,
    });
    pool.refusal = null;
    /* Its own shelf (2026-10-19): a pool of pools saved reloaded the
       recordings' shelf and left its own showing what it showed before. */
    if (pool.level === 'double') {
      pool.dshelf = null;
      loadDshelf();
    } else {
      pool.shelf = null;
      loadShelf();
    }
    // It stays on its picture: saving is not leaving.
    render();
  }

  async function openSaved(id, version) {
    pool.folderHint = folderOf(id);
    let got;
    try {
      got = await api((pool.level === 'double' ? '/api/rootcanal/dpool/'
                                               : '/api/rootcanal/pool/')
                      + encodeURIComponent(id)
                      + (version != null ? '?version=' + encodeURIComponent(version)
                                         : ''));
    } catch (e) {
      toast('That pool could not be opened: ' + e.message, 'err', 9000);
      return null;
    }
    const pay = got.payload || {};
    const art = got.artifact || {};
    pool.fit = Object.assign({ ok: true }, pay);
    pool.saved = true;
    pool.dirty = false;
    pool.evs = null;
    pool.picked = null;
    pool.evData = null;
    pool.evFor = null;
    pool.sel = pool.level === 'double'
      ? (pay.pools || []).map((p) => ({ key: 'P:' + p.artifact_id + ':'
                                             + p.version }))
      : (pay.members || []).map((m) => (m.banked === false
        ? { key: m.key, params: (m.pin || {}).params || singleParams() }
        : { key: m.key }));
    pool.all_ds = !!((pay.params || {}).all_ds);
    pool.types = Object.assign({}, pay.mouse_types || {});
    pool.focus = pay.focus || null;
    const pp = pay.params || {};
    pool.cluster_calls = Object.assign({}, pp.cluster_calls || {});
    pool.cluster_names = JSON.parse(JSON.stringify(pp.cluster_names || {}));
    pool.drawn = (pp.drawn || []).map((g) => ({ call: g.call,
      events: (g.events || []).map((x) => x.slice()) }));
    pool.avg = null; pool.lassoSel = [];
    /* The settings are shared, so a saved pool brings its own back into
       them -- the controls then say what the reopened picture was made
       with, in both views. */
    const ms = pp.measure || {};
    const back = { k: pp.k || 2, complete_only: !!pp.complete_only };
    for (const key of ['filt', 'mains_out', 'lo_hz', 'hi_hz', 'win_ms',
                       'cross_ms', 'band_lo', 'band_hi']) {
      if (ms[key] != null) back[key] = ms[key];
    }
    for (const key of Object.keys(back)) {
      q[key] = asParam(key, back[key]);
      pend[key] = q[key];
    }
    const mu = pay.margin_used;
    pool.margin = mu ? { artifact_id: mu.artifact_id, version: mu.version,
                         mode: mu.mode || 'fixed' } : null;
    // And the border it was classified by, coloured by it.
    pool.border = pp.border ? Object.assign({}, pp.border) : null;
    if (pool.border) pool.colour = 'border';
    else if (pool.colour === 'border') pool.colour = 'pool';
    /* The band reopens as the pool's own only when it set one: a pool that
       kept each member's band saved that band in params all the same. */

    pool.open = {
      artifact_id: art.artifact_id || art.id || id,
      version: art.version != null ? art.version : pay.version,
      nickname: art.nickname || '', name: art.name || '',
      by: art.by || (art.added || {}).by || null,
      updated: art.updated || null,
      // The version actually opened, which holds these members' numbers.
      source: { artifact_id: art.artifact_id || art.id || id,
                version: got.version != null ? got.version : version },
    };
    pool.savedMembers = (pay.members || []).slice();
    pool.refusal = null; pool.fitErr = null; pool.redo = null;
    pool.lastNick = '';
    BARRY.activity.log('rootcanal.pool_open', { artifact: pool.open.artifact_id,
                                                version: pool.open.version });
    /* OPEN OPENS IT (2026-10-19): its picture, on a screen of its own, at
       the top of the tool -- not drawn under the table of recordings at
       the bottom of the page, which is where "Open" used to put it. */
    goScreen('view');
    if (pool.picked == null) autoPick();
    return got;
  }

  /* `quiet`: the caller paints next. */
  function closePool(quiet) {
    pool.sel = []; pool.types = {}; pool.focus = null;
    pool.fit = null; pool.evs = null; pool.saved = false; pool.dirty = false;
    pool.open = null; pool.picked = null; pool.evData = null; pool.evFor = null;
    // And what was drawn and called on it: the next pool's clusters are
    // its own.
    pool.savedMembers = []; pool.drawn = []; pool.cluster_calls = {};
    pool.cluster_names = {}; pool.name = null; pool.measureOk = null;
    pool.all_ds = false;
    pool.margin = null; pool.marginErr = null; pool.avg = null;
    pool.border = null; pool.borderErr = null;
    if (pool.colour === 'border') pool.colour = 'pool';
    pool.lassoSel = []; pool.fitErr = null; pool.deep = null;
    /* And the screen it was on (2026-10-19): back to the saved pools. A
       read running for a refusal goes on on the server -- what it reads is
       kept -- and is no longer watched from here. */
    if (pool.redo && pool.redo.poll) clearInterval(pool.redo.poll);
    pool.refusal = null; pool.redo = null; pool.lastNick = '';
    pool.pickSrc = {};
    pool.screen = 'home';
    if (quiet !== true) render();
  }

  /* ==================================================================
     SAVE AS SINGLES (2026-10-19)

     "And then have the option to save the single ones individually if I
     want." Any member of the pool on the picture saved as a Root Canal
     single of its own -- a new version of that recording's single --
     measured the pool's way, its own analysis redone from its read here.
     None is ticked to begin with. At the second level the recordings come
     from the member pools, and each member pool is asked once for its own.
     A member whose read is not here is said, with its reason, and with an
     offer to read it here first. Nothing is banked.
     ================================================================== */
  function measureWords(ms) {
    if (!ms) return 'the pool’s measurement';
    return [ms.filter_label || filterWords(ms),
            ms.win_ms != null ? '±' + hz(ms.win_ms) + ' ms' : null,
            ms.cross_ms != null ? 'half-width search ±' + hz(ms.cross_ms) + ' ms'
                                : null,
            ms.band_lo != null ? hz(ms.band_lo) + '–' + hz(ms.band_hi) + ' Hz'
                               : null].filter(Boolean).join(' · ');
  }

  function singlesDialog() {
    const f = pool.fit && pool.fit.ok ? pool.fit : null;
    const ms = (f && f.members) || [];
    if (!ms.length) {
      toast('Pool it first: the singles are saved measured the pool’s way.',
            'warn', 6000);
      return;
    }
    const dbl = pool.level === 'double';
    const picks = new Set();
    const goBtn = BARRY.ui.button({ kind: 'primary', extra: 'rc-singles-go',
      text: 'Tick the recordings to save', disabled: true, onclick: () => go() });
    const sync = () => {
      goBtn.textContent = picks.size
        ? 'Save ' + picks.size + ' as single' + (picks.size === 1 ? '' : 's')
        : 'Tick the recordings to save';
      goBtn.disabled = !picks.size;
    };
    const boxes = [];
    const list = el('div', { class: 'rc-singles-list' }, ms.map((m) => {
      const cb = el('input', { type: 'checkbox', class: 'rc-singles-pick',
        'data-key': m.key,
        onchange: (e) => {
          if (e.target.checked) picks.add(m.key); else picks.delete(m.key);
          sync();
        } });
      boxes.push(cb);
      const pp = (m.pin && m.pin.pool) || null;
      return el('label', { class: 'rc-singles-row' }, [
        cb,
        el('span', { class: 'rc-singles-name', text: m.session_label || m.key }),
        el('span', { class: 'hint rc-singles-sub', text: [
          pp ? 'in ‘' + (pp.nickname || pp.artifact_id) + '’' : null,
          m.banked ? 'banked' : (m.pin && m.pin.single ? 'saved single v'
                                 + m.pin.single.version : 'not banked'),
          memberHere(m) ? 'read here' : 'read ' + (m.read_on ? 'on ' + m.read_on
                                                            : 'elsewhere'),
        ].filter(Boolean).join(' · ') }),
      ]);
    }));
    const tickAll = BARRY.ui.button({ kind: 'link', text: 'Tick all',
      extra: 'rc-singles-all',
      onclick: () => {
        for (const cb of boxes) { cb.checked = true; picks.add(cb.dataset.key); }
        sync();
      } });
    const meas = dbl ? (f.params || {}).measure : poolBody().measure;
    const body = el('div', { class: 'mb' }, [el('div', { class: 'rc-ask' }, [
      el('p', { text: 'Each recording you tick is saved as its own Root Canal '
        + 'single — a new version of that recording’s single — measured the '
        + 'pool’s way (' + measureWords(meas) + ', k = ' + (+q.k) + '). Its own '
        + 'analysis is redone from its read on this machine. The pool is not '
        + 'changed, and nothing is banked.' }),
      el('div', { class: 'rc-singles-tools' }, [
        tickAll,
        el('span', { class: 'hint', text: ms.length + ' recording'
                     + (ms.length === 1 ? '' : 's') + ' in the pool' }),
      ]),
      list,
    ])]);
    const shell = el('div', { class: 'rc-singles-dlg' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Save recordings as singles' }),
        el('div', { class: 'spacer' })]),
      body,
      BARRY.ui.modalFoot([], [
        BARRY.ui.button({ kind: 'ghost', text: 'Cancel', extra: 'rc-singles-no',
                          onclick: closeModal }),
        goBtn,
      ]),
    ]);
    showModal(shell, { replace: true });

    async function go() {
      const keys = ms.map((m) => m.key).filter((k) => picks.has(k));
      if (!keys.length) return;
      goBtn.disabled = true;
      goBtn.textContent = 'Saving…';
      /* One request per pool the members are from: the pool itself, or at
         the second level each member pool, with its own version. */
      const asks = asksFor(keys);
      const groups = [];
      for (const a of asks) {
        const sk = JSON.stringify(a.saved || null);
        let g = groups.find((x) => x.sk === sk);
        if (!g) { g = { sk, saved: a.saved || null, asks: [] }; groups.push(g); }
        g.asks.push(a);
      }
      const done = [], away = [];
      for (const g of groups) {
        const req = dbl
          ? { measure: meas || null, k: +q.k, saved: g.saved,
              members: g.asks.map((a) => ({ key: a.key })),
              keys: g.asks.map((a) => a.key) }
          : Object.assign(poolBody(), { keys: g.asks.map((a) => a.key) });
        const back = (k) => (g.asks.find((a) => a.key === k) || { id: k });
        try {
          const got = await apiPost('/api/rootcanal/pool/singles', req);
          for (const d of got.done || []) {
            done.push(Object.assign({}, d, { id: back(d.key).id,
              label: d.label || back(d.key).label }));
          }
          for (const a of got.away || []) {
            away.push(Object.assign({}, a, { id: back(a.key).id,
              label: a.label || back(a.key).label || a.key }));
          }
        } catch (e) {
          for (const a of g.asks) away.push({ id: a.id, key: a.key, label: a.label,
                                              why: e.message });
        }
      }
      singlesReport(done, away);
    }
  }

  /* What was saved and what was not, with why -- and, for what was not,
     the offer to read it here first. */
  function singlesReport(done, away) {
    const vOf = (d) => String(d.new_key || '').split(':').pop();
    toast(done.length + ' saved as single' + (done.length === 1 ? '' : 's')
          + (away.length ? ', ' + away.length + ' not' : '') + '. Nothing was '
          + 'banked.', away.length ? 'warn' : 'ok', 10000);
    if (done.length) refreshCandsQuietly();
    showModal(el('div', { class: 'rc-singles-dlg rc-singles-report' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: done.length ? 'Saved as singles' : 'Nothing was saved' }),
        el('div', { class: 'spacer' })]),
      el('div', { class: 'mb' }, [el('div', { class: 'rc-ask' }, [
        done.length ? el('div', { class: 'section-label', text: 'Saved' }) : null,
        done.length ? el('ul', { class: 'rc-singles-done' }, done.map((d) =>
          el('li', { text: (d.label || d.key) + ' — ' + (d.confirmed
            ? 'nothing had changed, so v' + vOf(d) + ' of its single is confirmed'
            : 'saved as v' + vOf(d) + ' of its single') }))) : null,
        away.length ? el('div', { class: 'section-label', text: 'Not saved' }) : null,
        away.length ? el('ul', { class: 'rc-singles-away' }, away.map((a) =>
          el('li', { text: (a.label || a.key) + ' — ' + (a.why
                                                          || 'no reason given') })))
          : null,
        away.length ? el('p', { class: 'hint', text: 'A recording whose read is '
          + 'not on this machine can be read here first: Jarvis finds it on a '
          + 'drive here or on the VACC, reads it as it was read, and offers this '
          + 'save again.' }) : null,
      ].filter(Boolean))]),
      BARRY.ui.modalFoot([], [
        BARRY.ui.button({ kind: away.length ? 'ghost' : 'primary', text: 'Close',
                          extra: 'rc-singles-close', onclick: closeModal }),
        away.length ? BARRY.ui.button({ kind: 'primary', extra: 'rc-singles-redo',
          text: 'Read them here first',
          title: 'Reads them here, pools again, and offers to save the singles '
               + 'again.',
          onclick: () => {
            closeModal();
            pool.refusal = { error: away.length + ' could not be saved as '
              + 'singles here: their reads are not on this machine.',
              away: away.map((a) => a.id), from: 'singles' };
            goScreen('view');
            startRedo();
          } }) : null,
      ]),
    ]), { replace: true });
  }

  /* Published as a real property so the OTHER window can drive this one.
     `BARRY` is a const in core.js -- a lexical binding, not a property of
     `window` -- so `opener.BARRY` is undefined however completely this page
     has loaded. `barryDspca` exists for the same reason. */
  window.barryRootcanal = {
    step: (d) => step(d || 1),
    pick: (i) => setPicked(i),
    current: () => pickedEvent(),
    classOf: (i) => {
      const e = fit && fit.ok ? (fit.events || []).find((x) => x.i === i)
                              : null;
      return e ? e.cls : null;
    },
    flip: (i) => flipEvent(i),
  };

  /* ==================================================================
     The figure builder (figure.js, 2026-10-22)

     "Grab what you see": the space and the three flat views, as two
     panels, with the settings they were fitted at. A picture that IS a
     saved version (opened and not changed since) is grabbed as that
     version, whose numbers open on any machine; anything else as the fit's
     own question, which this machine can ask its read. Pooled is several
     recordings, and a figure is one.
     ================================================================== */
  function figureParams() {
    const params = fitBody({});
    delete params.border;
    if (viewing && viewing.artifact_id && !isDirty()) {
      params.artifact = { artifact_id: viewing.artifact_id, v: viewing.v };
    }
    // The turn of the 3D view, in matplotlib's terms (degrees).
    params.view = { elev: Math.round(view.pitch * 180 / Math.PI),
                    azim: Math.round(-90 - view.yaw * 180 / Math.PI) };
    return params;
  }

  if (BARRY.figure && BARRY.figure.source) {
    BARRY.figure.source('rootcanal', {
      label: 'Root Canal',
      grab: () => {
        if (viewMode === 'pooled') {
          return { why: 'The pooled view is several recordings, and a figure '
                      + 'is one. Switch to Single to grab a recording.' };
        }
        if (!q.entry || !fit || !fit.ok) {
          return { why: 'Pick a set and fit it first, then grab it.' };
        }
        const cur = setOf() || {};
        const params = figureParams();
        return {
          recording: { gid: q.gid || cur.gid || null,
                       label: cur.session_label || cur.gid || q.entry,
                       identity: { gid: q.gid || cur.gid || null,
                                   label: cur.session_label || null } },
          title: 'Root Canal — ' + (cur.session_label || q.entry),
          panels: [
            { tool: 'rootcanal', plot: 'space', row: 0, col: 0, params },
            { tool: 'rootcanal', plot: 'flat', row: 0, col: 1,
              params: JSON.parse(JSON.stringify(params)) },
          ],
        };
      },
      palette: (lay) => (lay.panels.some((p) => p.tool === 'rootcanal')
        ? [['flat', 'The three flat views'], ['amp_hw', 'Amplitude against half-width'],
           ['amp_hf', 'Amplitude against HF power'], ['hw_hf', 'Half-width against HF power'],
           ['space', 'The three numbers, in 3D']]
          .map(([plot, name]) => ({ tool: 'rootcanal', plot, name }))
        : []),
      panelFor: (tool, plot, lay) => {
        const near = lay.panels.find((p) => p.tool === 'rootcanal');
        return near ? { tool: 'rootcanal', plot,
                        params: JSON.parse(JSON.stringify(near.params)) } : null;
      },
      openPanel: async (p) => {
        const want = p.params || {};
        if (BARRY.views.toolkit && BARRY.views.toolkit.pick) {
          setView('toolkit');
          BARRY.views.toolkit.pick('rootcanal');
        }
        if (want.entry_id && want.entry_id !== q.entry) await pickSetNow(want.entry_id);
        if (want.from_version !== undefined) q.from_version = want.from_version;
        for (const k of PKEYS) {
          if (want[k] !== undefined) { q[k] = want[k]; pend[k] = want[k]; }
        }
        q.flips = (want.flips || []).slice();
        q.centres = want.centres ? want.centres.map((c) => c.slice()) : null;
        q.cluster_calls = Object.assign({}, want.cluster_calls);
        q.cluster_names = JSON.parse(JSON.stringify(want.cluster_names || {}));
        if (want.read) q.read = want.read;
        await refit();
        return 'Root Canal is open on set ' + want.entry_id
          + ', with the panel’s settings.';
      },
    });
  }

  /* The walk-through (figreplay.js): Root Canal opened on the panel's set
     with its settings, then what Root Canal is showing read back. A panel
     that is a saved version is opened as that version. */
  if (BARRY.figreplay && BARRY.figreplay.register) {
    const WALK_KEYS = ['filt', 'lo_hz', 'hi_hz', 'mains_out', 'win_ms',
                       'band_lo', 'band_hi', 'cross_ms', 'k'];
    BARRY.figreplay.register('rootcanal', {
      async open() { return 'Root Canal opens on each panel’s set.'; },
      async setup(p) {
        const want = p.params || {};
        setView('toolkit');
        BARRY.views.toolkit.pick('rootcanal');
        if (viewMode === 'pooled') {
          viewMode = 'single';
          try { localStorage.setItem(VIEW_KEY, 'single'); } catch (e) { /* blocked */ }
        }
        if (want.entry_id && want.entry_id !== q.entry) await pickSetNow(want.entry_id);
        if (want.artifact && want.artifact.artifact_id) {
          await openVersion(want.artifact.artifact_id, want.artifact.v);
          return 'Root Canal shows saved version v' + (want.artifact.v || '?')
            + ' of set ' + want.entry_id + '.';
        }
        q.from_version = want.from_version === undefined ? q.from_version
                                                          : want.from_version;
        for (const k of PKEYS) {
          if (want[k] !== undefined) { q[k] = want[k]; pend[k] = want[k]; }
        }
        q.flips = (want.flips || []).slice();
        q.centres = want.centres ? want.centres.map((c) => c.slice()) : null;
        q.cluster_calls = Object.assign({}, want.cluster_calls);
        q.cluster_names = JSON.parse(JSON.stringify(want.cluster_names || {}));
        if (want.read) q.read = want.read;
        await refit();
        return 'Root Canal is fitted on set ' + want.entry_id
          + ' with the panel’s settings.';
      },
      async ready() {
        let last = null;
        for (let i = 0; i < 120; i++) {
          await new Promise((r) => setTimeout(r, 150));
          const now = fit && fit.ok && !fitting ? sigOf() : null;
          if (now && now === last) return true;
          last = now;
        }
        return false;
      },
      async readback() {
        if (!fit || !fit.ok) return null;
        const got = figureParams();
        delete got.view;
        return got;
      },
      differences(want, got) {
        const out = [];
        const say = (v) => (v === null || v === undefined ? 'none' : String(v));
        if (want.entry_id !== got.entry_id) out.push('it is a different set');
        if (say(want.from_version) !== say(got.from_version)) {
          out.push('it is version ' + say(got.from_version) + ', not '
                   + say(want.from_version));
        }
        for (const k of WALK_KEYS) {
          if (want[k] === undefined) continue;
          if (String(want[k]) !== String(got[k])) {
            out.push(k.replace(/_/g, ' ') + ' is ' + say(got[k]) + ', not '
                     + say(want[k]));
          }
        }
        if (!BARRY.figreplay.sameSet(want.flips, got.flips)) {
          out.push((got.flips || []).length + ' events are flipped by hand, not '
                   + (want.flips || []).length);
        }
        if (!!want.artifact !== !!got.artifact) {
          out.push(got.artifact ? 'it is now a saved version'
                                : 'it is not the saved version any more');
        }
        return out;
      },
    });
  }

  return {
    paint,
    /* For web/_dev/rootcanal.html, which drives the real panel rather than
       a copy of it. A harness that reimplements the thing it is testing
       tests nothing. */
    _state: () => ({ q, pend, fit, picked, job, cands, evData, busy,
                     fitting, chooserOpen, live, view: Object.assign({}, view),
                     bulk }),
    // Straight to the set, as the harness's own steps mean it; the nudge
    // a person gets on leaving a changed picture is `_leaveTo`.
    _pickSet: pickSetNow,
    // A saved single version, opened as the Versions card opens it.
    _openVersion: openVersion,
    _figureParams: () => figureParams(),
    _leaveTo: pickSet,
    _read: startRead,
    _fit: refit,
    _fitBody: () => fitBody({}),
    _lastBody: () => lastBody,
    _draw: drawAll,
    /* Where everything landed, in canvas CSS pixels (content box): every
       dot and both centres in the space and in each flat view, the axes and
       their labels, and the picked dot in each. */
    _geom: () => JSON.parse(JSON.stringify({
      space: GEOM.space, ev: GEOM.ev, hist: GEOM.hist || {},
      flats: Object.keys(GEOM.flats).reduce((acc, id) => {
        const f = GEOM.flats[id];
        acc[id] = { id, xa: f.xa, ya: f.ya, w: f.w, h: f.h, xr: f.xr,
                    yr: f.yr, box: f.box, pts: f.pts, centres: f.centres,
                    picked: f.picked, labels: f.labels };
        return acc;
      }, {}),
    })),
    _pick: (i) => setPicked(i),
    _pickAt: (id, x, y) => (id === 'rcSpace' ? pickSpace(x, y)
                                             : pickFlat(id, x, y)),
    _rotate: (yaw, pitch) => {
      if (yaw != null) view.yaw = yaw;
      if (pitch != null) view.pitch = Math.max(-1.45, Math.min(1.45, pitch));
      drawSpace();
      return Object.assign({}, view);
    },
    _zoom: (z) => { view.zoom = z; drawSpace(); },
    _resetView: resetView,
    _view: () => Object.assign({}, view, { yaw0: YAW0, pitch0: PITCH0 }),
    _flip: flipEvent,
    _setClass: setClass,
    _moveCentre: moveCentre,
    _resetCentres: resetCentres,
    _clearFlips: clearFlips,
    _rawToZ: rawToZ,
    _border3d: () => GEOM.border3d || null,
    _poolFillOf: (j) => poolFill(poolEvents()[j]),
    _autoPick: () => autoPick(),
    _zToRaw: zToRaw,
    /* A setting typed but not recomputed, which is the state the stale
       chip exists for; and Recompute, which is the button. */
    _setParam: (k, v) => { pend[k] = v; tickPending(); },
    _recompute: recompute,
    _pending: pending,
    _problems: () => problems(pend),
    _step: step,
    _pngs: pngs,
    _bankLabel: bankLabel,
    _bankDialog: bankDialog,
    _commit: commit,
    _defaultVersion: defaultVersion,
    _openXplore: openInXplore,
    _openPicked: () => openPickedInXplore(),
    _poolEvents: () => poolEvents(),
    _recordingHere: (gid) => recordingHere(gid),
    _xTarget: () => {
      const xt = xTarget();
      return xt ? { gid: xt.gid, t: xt.now.t, i: xt.now.i, m: xt.now.m,
                    at: xIndex(xt), n: xt.evs.length } : null;
    },
    _pushXplore: pushXplore,
    _xWin: () => (xOpen() ? xWin : null),
    _closeXplore: () => { try { if (xWin) xWin.close(); } catch (e) { /* ok */ }
                          xWin = null; },
    _mismatched: mismatched,
    _repaint: render,
    _bulk: () => bulk,
    _bulkPlan: loadBulk,
    /* A read in progress, and a tick of it, without a read -- the path the
       poll takes, driven by hand, because the flicker these check only
       shows while a job runs and a real one is minutes of disk. */
    _fakeJob: (st) => {
      job = { id: 'harness', status: 'running',
              stages: [Object.assign({ done: 0, of: 296, unit: 'events' },
                                     st || {})] };
      render();
    },
    _tick: (st) => {
      if (!job) return false;
      job.stages = [Object.assign({}, (job.stages || [])[0], st || {})];
      return tickJob();
    },
    _endJob: () => { job = null; render(); },
    /* A batch with some members finished, without running one: what the
       list does with a finished row is the thing being checked. */
    _fakeBulk: (members) => {
      bulk.on = true;
      bulk.job = { id: 'harness-bulk', status: 'running',
                   stages: [{ done: (members || []).filter(
                     (m) => m.status === 'done').length,
                     of: (members || []).length }],
                   members: members || [] };
      render();
    },
    // The poll's own path (2026-10-19: the card is reconciled, not swapped).
    _tickBulk: () => (bulkRefresh() || swap('.rc-mode', modeSwitch())),
    _endBulk: () => { bulk.job = null; bulk.sent = null; bulk.on = false;
                      render(); },
    /* Pooled, for web/_dev/rootcanalpool.html. */
    _setView: setView,
    _marginErr: () => marginErr,
    _relabel: (rank, call) => { q.cluster_calls[String(rank)] = call; refit(); },
    _avg: () => curAvg(),
    _single: () => single,
    _setLevel: setLevel,
    _measuresAgreed: measuresAgreed,
    _deep: () => pool.deep,
    _loadDeep: loadDeep,
    _deepPick: deepPick,
    _borderDialog: borderDialog,
    _borders: () => borders,
    _loadBorders: loadBorders,
    _setBorder: (ref) => { q.border = ref; borderErr = null; refit(); },
    _borderErr: () => borderErr,
    /* What the applied border drew on each flat view (2026-10-19): its
       box or its lines, in canvas pixels, and its label. */
    _borderGeom: () => JSON.parse(JSON.stringify(GEOM.border || {})),
    _borderPick: () => JSON.parse(JSON.stringify(borderPick)),
    _statsDialog: statsDialog,
    _statsRun: statsRun,
    _statsPick: (ts) => { if (ts) statsPick = ts.slice(); return statsPick; },
    _propagateDialog: propagateDialog,
    _render: () => render(),
    _done: () => doneQ,
    _folders: () => poolFolders(),
    _folderOf: (id) => folderOf(id),
    _openDone: (id) => {
      const r = (doneQ.rows || []).find((x) => x.entry_id === id);
      return r ? openDone(r) : null;
    },
    _nameDialog: nameDialog,
    _names: loadNames,
    _pickName: (nm) => pickName(nm, pool.cands || []),
    _singleBanked: () => singleBanked,
    _importBanked: importBanked,
    _loadSingle: loadSingle,
    _viewing: () => viewing,
    _savedOnly: () => savedOnly,
    _dirty: () => isDirty(),
    _openVersion: openVersion,
    _saveVersion: saveVersionDialog,
    _pickSetNow: pickSetNow,
    _showAverage: showAverage,
    _lasso: (path) => { lasso = path.map((p2) => p2.slice()); finishLasso();
                        return lassoIds().slice(); },
    _lassoSel: () => lassoIds().slice(),
    _drawn: () => (viewMode === 'pooled' ? pool.drawn : q.drawn),
    _viewMode: () => viewMode,
    _pool: () => pool,
    _poolLoad: loadPool,
    _poolToggle: (key, on) => toggleMember(key, on),
    _poolRun: runPool,
    _poolBody: () => poolBody(),
    _poolColour: setColour,
    _poolFocus: setFocus,
    _poolType: setType,
    _poolPick: poolPick,
    _poolSave: saveDialog,
    _poolSaveLabel: saveLabel,
    _poolOpen: openSaved,
    _poolClose: closePool,
    _poolCats: (mode) => catList(mode || pool.colour),
    /* The screens, the recordings and the read-again runs (2026-10-19). */
    _poolScreen: () => poolScreen(),
    _poolGo: goScreen,
    _poolNew: newPool,
    _poolRecs: () => recordings().map((r) => ({ id: r.id, def: r.def,
      cur: curKey(r), keys: r.answers.map((a) => a.key),
      words: r.answers.map((a) => a.words),
      label: (r.facts[0] || {}).session_label || r.id })),
    _poolRedo: () => pool.redo && { state: pool.redo.state, ended: pool.redo.ended,
                                    rows: rereadRows(pool.redo) },
    _poolEvRedo: () => Array.from(evRedo.entries()).map(([id, R]) => ({
      id, state: R.state, ended: R.ended, landed: R.landed, rows: rereadRows(R) })),
    _poolSingles: singlesDialog,
    _reset: () => {
      cands = null; q.entry = null; q.gid = null; q.from_version = null;
      forget();
      for (const k of PKEYS) { q[k] = DEF[k]; pend[k] = DEF[k]; }
      view.yaw = YAW0; view.pitch = PITCH0; view.zoom = 1;
    },
  };
}());
