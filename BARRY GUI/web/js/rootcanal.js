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
  const DEF = { lo_hz: 1, hi_hz: 100, win_ms: 25, band_lo: 500, band_hi: 1000,
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
    lo_hz: DEF.lo_hz, hi_hz: DEF.hi_hz, win_ms: DEF.win_ms,
    band_lo: DEF.band_lo, band_hi: DEF.band_hi, cross_ms: DEF.cross_ms,
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
    lo_hz: DEF.lo_hz, hi_hz: DEF.hi_hz, win_ms: DEF.win_ms,
    band_lo: DEF.band_lo, band_hi: DEF.band_hi, cross_ms: DEF.cross_ms,
  };
  const PKEYS = ['lo_hz', 'hi_hz', 'win_ms', 'band_lo', 'band_hi', 'cross_ms'];

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

  const bulk = { on: false, plan: null, pick: {}, job: null, poll: null };

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
    fit: null, fitting: false, gen: 0, lastBody: null, dirty: false,
    evs: null, evsFor: null,
    picked: null, evData: null, evFor: null, evGen: 0, evBusy: false,
    shelf: null, shelfErr: null, open: null, saved: false,
    fitErr: null,       // the server's sentence when it refused the members
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
  async function paint() {
    render();
    if (viewMode === 'pooled') { await loadPool(); return; }
    if (!cands) await loadCandidates();
  }

  async function loadCandidates() {
    try {
      const got = await api('/api/rootcanal/candidates');
      cands = got.sets || [];
    } catch (e) {
      toast('Could not read the event bank: ' + e.message, 'err', 8000);
      reportClientError('rootcanal.candidates', e.message,
                        String(e && e.stack));
      cands = [];
    }
    if (!q.entry && cands.length) {
      const first = cands.find((c) => c.readable !== false && c.aligned)
                 || cands.find((c) => c.readable !== false);
      if (first) { pickSet(first.entry_id); return; }
    }
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

  function pickSet(id) {
    q.entry = id;
    const s = setOf(id);
    q.gid = s ? s.gid : null;
    const v = defaultVersion(s);
    q.from_version = v ? versionRef(v) : null;
    forget();
    render();
  }

  /* Everything that belongs to one read, dropped together. */
  function forget() {
    q.read = null;
    q.flips = [];
    q.centres = null;
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
      lo_hz: +q.lo_hz, hi_hz: +q.hi_hz, win_ms: +q.win_ms,
      band_lo: +q.band_lo, band_hi: +q.band_hi, cross_ms: +q.cross_ms,
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
      fit = { ok: false, error: e.message };
      fitting = false;
      live = null;
      render();
      return;
    }
    if (mine !== fitGen) return;
    fit = got;
    fitting = false;
    live = null;
    /* The server's own statement of what it computed, back into the form
       where the form is still asking that. It can round a corner or cap a
       band; the chips then describe the picture rather than the request. */
    const p = fit.params || {};
    for (const k of PKEYS) {
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
    pushXplore();
    if (bankAfterFit) {
      bankAfterFit = false;
      // After the pictures are drawn, so the figures filed are real.
      requestAnimationFrame(() => requestAnimationFrame(() => bankDialog()));
    }
  }, 60);

  function refit() { refitSoon(); }

  /* Recompute: the typed settings become the question.

     Checked here rather than sent to be refused. Every one of these has a
     reason a person can act on, and the server's refusal would be the same
     sentence one round trip later. */
  function problems(p) {
    const out = [];
    const n = (k) => Number(p[k]);
    if (!(n('lo_hz') >= 0)) out.push('the filter’s low corner is not a number');
    if (!(n('hi_hz') > 0)) out.push('the filter’s high corner is not a number');
    if (n('hi_hz') <= n('lo_hz')) {
      out.push('the filter’s high corner has to be above its low one');
    }
    if (n('hi_hz') > LP_MAX) {
      out.push('the snippets are kept at 2 kHz, so the filter stops at '
               + LP_MAX + ' Hz');
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

  function recompute() {
    if (!pending() || fitting) return false;
    const bad = problems(pend);
    if (bad.length) { toast('Not yet: ' + bad[0] + '.', 'warn', 7000); return false; }
    for (const k of PKEYS) q[k] = Number(pend[k]);
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
    box.innerHTML = '';
    box.appendChild(intro());
    box.appendChild(viewBar());
    if (viewMode === 'pooled') { paintPool(box); return; }
    if (!cands) { box.appendChild(loading('Reading the event bank')); return; }
    if (!cands.length) { box.appendChild(nothing()); return; }
    box.appendChild(modeSwitch());
    if (bulk.on) { box.appendChild(bulkCard()); return; }
    box.appendChild(chooser());
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

  function intro() {
    return BARRY.ui.stepHeader({
      title: 'Root Canal',
      step: 'step 4 of The Dentist',
      blurb: 'Takes the interictal discharges out of an aligned set of '
           + 'dentate spikes — amplitude, half-width and high-frequency '
           + 'power per event, split in two by k-means.',
    });
  }

  function loading(what, sub) {
    return el('div', { class: 'card rc-load' }, [loader(what, sub)]);
  }

  function nothing() {
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
      el('span', { class: 'hint', text: bulk.on
        ? 'Reads them one after another. Nothing is banked by the queue — '
          + 'each set is still looked at and banked by somebody.'
        : 'Pick an aligned set, read it once, then look at what it splits '
          + 'into.' }),
      bulk.job && !bulk.on
        ? el('span', { class: 'hint rc-bulk-note', text: (() => {
            const st = (bulk.job.stages || [])[0] || {};
            return 'Batch still reading — ' + (st.done || 0) + ' of '
                 + (st.of || '?') + '.';
          })() })
        : null,
    ].filter(Boolean));
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
      return el('div', { class: 'card rc-choose rc-folded' }, [
        el('strong', { text: cur.session_label || cur.gid || cur.entry_id }),
        el('span', { class: 'hint', text:
          (cur.name || 'DS set ' + cur.entry_id)
          + '  ·  ' + (v ? BARRY.ui.versionLabel(v) : 'as it is now')
          + '  ·  ' + ((v && v.n) || cur.n) + ' events'
          + (v && v.aligned ? '  ·  aligned' : '') }),
        el('span', { class: 'spacer' }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Change set',
          title: 'Show the recording, entry and version lists again. The '
               + 'read and the answer stay until you pick something else.',
          onclick: () => { chooserOpen = true; render(); } }),
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
    rows.sort((x, y) => String(x.label || '').localeCompare(
      String(y.label || '')));
    if (!q.gid || !seen.has(q.gid)) {
      q.gid = (cur && cur.gid) || (rows[0] || {}).gid || null;
    }

    box.appendChild(el('div', { class: 'section-label', text: 'Recording' }));
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
        idOf: versionRef,
        value: q.from_version,
        unit: 'stamps',
        disabled: (v) => (usable(v) ? null : (v.why_not || 'not readable here')),
        state: (v) => [
          v.tag === 'rootcanal' ? 'Root Canal’s own output' : null,
          v.aligned ? null : 'not aligned',
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
    return el('div', { class: 'card rc-read' }, [
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
    ]);
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

  function modeChip() {
    const p = shownParams();
    const stale = pending() || fitting;
    return el('span', {
      class: 'rc-chip' + (stale ? ' rc-chip-stale' : ''),
      title: stale
        ? 'This picture is still the previous answer, computed with these '
          + 'settings. Recompute to see the new ones.'
        : 'The filter and the band this picture was computed with.',
      text: hz(p.lo_hz) + '–' + hz(p.hi_hz) + ' Hz filter  ·  ±'
            + hz(p.win_ms) + ' ms  ·  half-width ±'
            + hz(p.cross_ms != null ? p.cross_ms : q.cross_ms) + ' ms  ·  '
            + hz(p.band_lo) + '–' + hz(p.band_hi)
            + ' Hz band' + (stale ? '  (recompute)' : ''),
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
        num('lo_hz', 'filter', { unit: '–', min: 0, max: LP_MAX, title:
          'The low corner of the zero-phase filter amplitude and half-width '
          + 'are measured through. 1 Hz by default.' }),
        num('hi_hz', '', { unit: 'Hz', min: 1, max: LP_MAX, title:
          'The high corner. 100 Hz by default; the snippets are kept at '
          + '2 kHz, so up to ' + LP_MAX + ' Hz means something.' }),
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
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'reset centres',
          disabled: !q.centres || fitting,
          title: 'Put both centres back where k-means placed them.',
          onclick: resetCentres }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: 'clear flips' + (q.flips.length ? ' (' + q.flips.length + ')'
                                                 : ''),
          disabled: !q.flips.length || fitting,
          title: 'Undo every class set by hand.',
          onclick: clearFlips }),
        p ? BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'put them back',
              title: 'Go back to the settings the picture was computed with.',
              onclick: revertPending }) : null,
        BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: fitting ? 'Recomputing…' : 'Recompute ↵',
          extra: 'rc-recompute',
          disabled: !p || bad.length || fitting,
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
    if (go) go.disabled = !p || !!bad.length || fitting;
    for (const c of box.querySelectorAll('.rc-chip')) c.replaceWith(modeChip());
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
          c.wide ? BARRY.ui.chip(c.wide + ' by the widened search', {
            kind: 'warn', extra: 'rc-count-wide',
            title: 'Their half-width was found only with the search reaching '
                 + 'past v1’s ' + CROSS_V1 + ' ms. Drawn with a dashed '
                 + 'outline.' }) : null,
          cs.length === 2 ? BARRY.ui.chip(
            (fit.n_placed != null ? fit.n_placed : fit.n_used) + ' of '
            + fit.n + ' classified') : null,
        ].filter(Boolean)),
      ]),
      BARRY.ui.actions([
        BARRY.ui.button({ kind: 'primary', text: bankLabel(),
          extra: 'rc-bank',
          disabled: fitting || !fit.ok,
          title: 'Bank the DS class as the next version of this set and the '
               + 'IED class as a set of candidate IEDs. A dialog first.',
          onclick: bankDialog }),
      ]),
    ];
    return el('div', { class: 'card rc-why' }, kids);
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
      e.flipped ? BARRY.ui.chip('set by hand', { kind: 'warn' }) : null,
      e.partial ? BARRY.ui.chip('2 of 3 axes', { kind: 'warn' }) : null,
      e.wide ? BARRY.ui.chip('widened search', { kind: 'warn' }) : null,
      el('span', { class: 'spacer' }),
      BARRY.ui.actions([
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: '◀ prev',
                          title: 'The previous event. Or ←.',
                          onclick: () => step(-1) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'next ▶',
                          title: 'The next event. Or →.',
                          onclick: () => step(+1) }),
        e.cls == null
          ? el('span', { class: 'hint', text: 'not measured, so no class' })
          : BARRY.ui.seg([
              ['ds', 'DS', 'A dentate spike: kept in the set.'],
              ['ied', 'IED', 'An interictal discharge: taken out of the set '
                           + 'and banked as a candidate IED.'],
            ], e.cls, (cls) => setClass(e.i, cls), { extra: 'rc-toggle' }),
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
        viewMode === 'pooled' ? poolChip() : modeChip(),
        el('span', { class: 'hint', text:
          'z-scored · drag to turn · wheel to zoom · double-click to reset' }),
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
        viewMode === 'pooled' ? poolChip() : modeChip(),
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
    const away = viewMode === 'pooled' ? poolEventNote() : null;
    return el('div', { class: 'rc-pane rc-event' }, [
      away ? el('p', { class: 'rc-ev-why rc-ev-away', text: away }) : null,
      why ? el('p', { class: 'rc-ev-why', text: why }) : null,
      el('div', { class: 'rc-ev-grid' }, [
        cell('rcTrace', 'Max-amp contact', (e.contact != null
          ? 'CSC' + e.contact : 'the contact the read names') + ', the fit filter'),
        cell('rcSpec', 'Spectrum', 'event against its baseline'),
        cell('rcStack', 'Every contact', 'max contact marked'),
        cell('rcCsd', 'CSD', 'the fit filter, down the probe'),
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

  /* The legend for the marks, once, above the pictures. */
  function legend() {
    const item = (cls, text) => el('span', { class: 'rc-lg' }, [
      el('i', { class: 'rc-lg-m ' + cls }), el('span', { text })]);
    return el('div', { class: 'rc-legend' }, [
      item('rc-lg-ds', 'DS'),
      item('rc-lg-ied', 'IED'),
      item('rc-lg-square', 'on 2 of 3 axes'),
      item('rc-lg-wide', 'half-width by the widened search'),
      item('rc-lg-flip', 'set by hand'),
      item('rc-lg-hollow', 'not measured'),
      item('rc-lg-centre', 'centre'),
    ]);
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
    pushXplore();
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
    const key = JSON.stringify([picked, q.read, q.lo_hz, q.hi_hz, q.win_ms,
                                q.band_lo, q.band_hi, q.cross_ms]);
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
    const body = el('div', { class: 'rc-ask' }, [
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
      toast(rep.already, 'warn', 9000);
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
    // The set's versions have changed, so the chooser is stale.
    cands = null;
    loadCandidates();
    return rep;
  }

  /* ==================================================================
     Many sets at once
     ================================================================== */
  function bulkCard() {
    const kids = [
      el('div', { class: 'section-label', text: 'Read a batch' }),
    ];
    if (bulk.job) {
      const st = (bulk.job.stages || [])[0] || {};
      kids.push(el('div', { class: 'hint', text:
        'Reading ' + (st.done || 0) + ' of ' + (st.of || '?') + ' sets' }));
      kids.push(el('div', { class: 'rc-bar' }, [
        el('i', { style: 'width:'
                  + (100 * (st.of ? (st.done || 0) / st.of : 0)).toFixed(1)
                  + '%' })]));
      /* A SET THAT IS DONE CAN BE OPENED -- AND BANKED -- WHILE THE REST
         RUN. The read is the expensive half and it is finished for that
         one. "Bank" opens it and puts the bank dialog up once its pictures
         are drawn, so what is filed is what was on screen; the queue itself
         never banks anything. */
      kids.push(el('table', { class: 'tbl rc-bulk' }, [
        el('tbody', {}, (bulk.job.members || []).map((m) => {
          const ready = m.status === 'done';
          return el('tr', {
            class: m.status === 'error' ? 'bad' : (ready ? 'ready' : null),
          }, [
            el('td', {}, [
              ready ? BARRY.ui.button({ kind: 'mini', text: m.label,
                        title: 'Open this one now. The rest keep reading.',
                        onclick: () => openRead(m.id) })
                    : el('span', { text: m.label }),
            ]),
            el('td', { text: m.cached ? 'already read'
                             : m.status === 'running'
                               ? (m.of ? m.done + ' / ' + m.of : 'reading…')
                               : m.status }),
            el('td', {}, [ready ? BARRY.ui.button({ kind: 'mini',
              text: 'Bank…', title: 'Open it and put up the bank dialog '
                                  + 'for the answer as fitted.',
              onclick: () => openRead(m.id, { bank: true }) }) : null]),
            el('td', { class: 'dim', text: m.error || '' }),
          ]);
        })),
      ]));
      kids.push(BARRY.ui.actions([
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Stop',
          title: 'Stop the batch. The sets already read are kept.',
          onclick: () => apiPost('/api/cfc/job/' + bulk.job.id + '/cancel', {})
                           .catch(() => {}) }),
      ]));
      return el('div', { class: 'card rc-bulk-card' }, kids);
    }
    if (!bulk.plan) {
      kids.push(loader('Working out what could be read'));
      return el('div', { class: 'card rc-bulk-card' }, kids);
    }
    const bp = bulk.plan;
    kids.push(el('div', { class: 'hint', text:
      (bp.n || 0) + ' could be read now  ·  ' + (bp.n_done || 0)
      + ' already read  ·  ' + (bp.n_blocked || 0) + ' cannot be' }));
    if ((bp.done || []).length) {
      kids.push(el('div', { class: 'section-label', text: 'Already read' }));
      kids.push(el('div', { class: 'rc-done-list' },
        bp.done.map((r) => BARRY.ui.button({ kind: 'mini', text: r.label,
          title: 'Open it. The read is cached, so this is immediate.',
          onclick: () => openRead(r.entry_id) }))));
    }
    if ((bp.todo || []).length) {
      kids.push(el('table', { class: 'tbl rc-bulk' }, [
        el('thead', {}, [el('tr', {}, ['', 'set', 'events', 'probe']
          .map((t) => el('th', { text: t })))]),
        el('tbody', {}, bp.todo.map((r) => el('tr', {}, [
          el('td', {}, [el('input', {
            type: 'checkbox', checked: bulk.pick[r.entry_id] !== false || null,
            onchange: (e) => { bulk.pick[r.entry_id] = e.target.checked; },
          })]),
          el('td', { text: r.label }),
          el('td', { text: String(r.n_good != null ? r.n_good : (r.n || '')) }),
          /* Every row here is aligned -- a set Braces has not lined up is
             listed under "Left out" with that reason -- so the column says
             the other thing worth knowing before paying for a read. */
          el('td', { class: 'dim', text: r.probe || '' }),
        ]))),
      ]));
      kids.push(BARRY.ui.actions([
        BARRY.ui.button({ kind: 'primary', text: 'Read the ticked',
                          onclick: runBulk }),
      ]));
    }
    if ((bp.blocked || []).length) {
      kids.push(el('div', { class: 'section-label', text: 'Left out' }));
      kids.push(el('table', { class: 'tbl rc-bulk' }, [
        el('tbody', {}, bp.blocked.map((r) => el('tr', {}, [
          el('td', { text: r.label }),
          el('td', { class: 'dim', text: r.why }),
        ]))),
      ]));
    }
    return el('div', { class: 'card rc-bulk-card' }, kids);
  }

  async function loadBulk() {
    try {
      bulk.plan = await api('/api/rootcanal/batch/plan');
    } catch (e) {
      bulk.plan = { ok: false, todo: [], done: [], blocked: [],
                    n: 0, n_done: 0, n_blocked: 0 };
      toast(e.message, 'err', 8000);
    }
    render();
  }

  function openRead(entryId, o) {
    if (!entryId) return;
    bulk.on = false;
    pickSet(entryId);
    /* The batch reads each set as it stands (`from_version` null), so that
       is what is opened; anything else could be a read nobody has paid for
       yet, and "Open" would quietly start one. */
    q.from_version = null;
    bankAfterFit = !!(o && o.bank);
    BARRY.activity.log('rootcanal.open_from_batch', { entry: entryId });
    // The read is done, so this comes back cached and goes straight to a fit.
    startRead();
  }

  async function runBulk() {
    const want = ((bulk.plan && bulk.plan.todo) || [])
      .filter((r) => bulk.pick[r.entry_id] !== false)
      .map((r) => r.entry_id);
    if (!want.length) { toast('Nothing is ticked.', 'warn', 5000); return; }
    try {
      const got = await apiPost('/api/rootcanal/batch', { entries: want });
      bulk.job = got.job;
      render();
      watchBulk();
    } catch (e) {
      toast(e.message, 'err', 10000);
    }
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
           X-ray's lesson. */
        if (!swap('.rc-bulk-card', bulkCard())) swap('.rc-mode', modeSwitch());
        return;
      }
      clearInterval(bulk.poll);
      bulk.poll = null;
      const done = bulk.job;
      bulk.job = null;
      const n = (done.members || []).filter((m) => m.status === 'done').length;
      const quit = done.status === 'canceled';
      toast(quit
        ? ('Stopped. ' + n + ' of ' + (done.members || []).length
           + ' were read and are kept; the rest were not started.')
        : ('Read ' + n + ' of ' + (done.members || []).length
           + '. Nothing was banked.'),
        quit ? 'warn' : 'ok', 8000);
      bulk.plan = null;
      if (bulk.on) loadBulk();
      else swap('.rc-mode', modeSwitch());
    }, 900);
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
    if (a === 0) return 'max amplitude · µV';
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
      fill: (e) => colOf(e.cls),
      shape: () => null,
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
      g.strokeStyle = k.bg;
      g.lineWidth = 0.7;
      g.stroke();
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
                 fill: S.fill(e), shape: S.shape(e), ringed: S.ringed(e) });
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

    for (const it of items) {
      if (it.kind === 'e') {
        const e = it.e;
        const near = shade(it.d);
        const r = 2.6 + 1.4 * near;
        drawMark(g, k, it.P.x, it.P.y, r, e, it.mk,
                 (0.45 + 0.55 * near) * it.al, S);
      } else {
        drawCentre(g, k, it.c, it.P.x, it.P.y);
      }
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

    GEOM.space = { w: s.w, h: s.h, cx, cy, scale, R, L,
                   view: Object.assign({}, view), pts, centres: cpts,
                   axes: axes.map((ax, j) => Object.assign({}, ax,
                                                           { label: labels[j] })),
                   picked: pickedAt };
  }

  function drawCentre(g, k, c, x, y) {
    const col = colOf(c.cls);
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
    g.fillText((c.cls === 'ied' ? 'IED' : 'DS') + ' centre', x + 10, y + 3);
    g.restore();
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
                 ringed: S.ringed(e) });
    }
    g.restore();
    const cpts = [];
    for (const c of cs) {
      const vx = (c.raw || [])[xa], vy = (c.raw || [])[ya];
      if (vx == null || vy == null || !isFinite(vx) || !isFinite(vy)) continue;
      const x = Math.max(x0, Math.min(x1, X(vx)));
      const y = Math.max(y0, Math.min(y1, Y(vy)));
      drawCentre(g, k, c, x, y);
      cpts.push({ k: c.k, x, y, cls: c.cls });
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
    const e = pickedEvent();
    if (!e) return;
    const d = viewMode === 'pooled' ? pool.evData : evData;
    const ok = d && d.ok !== false;
    drawTrace(ok ? d.trace : null, e, d);
    drawSpec(ok ? d.spectrum : null, d);
    drawStack(ok ? d.stack : null, e, d);
    drawCsd(ok ? d.csd : null, ok ? d.stack : null, e, d);
  }

  /* An event canvas with nothing yet to draw on it, saying why. */
  function waitText(s, k, d) {
    s.g.fillStyle = d && d.ok === false ? k.warn : k.dim;
    const f = fitText(s.g, d && d.ok === false ? d.error : 'reading…',
                      s.w - 16, 10);
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
    const ys = finite(t.y).concat(finite([t.baseline, t.peak_uV, t.half_uV]));
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
    if (p.id === 'rcSpace') {
      if (!p.moved) {
        const at = local(e, cv);
        const i = pickSpace(at.x, at.y);
        const S = scene();
        if (i != null && S) S.onPick(i);
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
  document.addEventListener('dblclick', (e) => {
    if (e.target && e.target.id === 'rcSpace') resetView();
  });
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
    try { if (tk.loadRegistry) await tk.loadRegistry(); } catch (e) { /* below */ }
    const want = gid || q.gid;
    const row = (tk.registryRows ? tk.registryRows() : [])
      .find((r) => r.gid === want);
    return (row && (row.here || [])[0]) || null;
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
      };
    }
    const e = pickedEvent();
    if (!e || !fit || !fit.ok) return null;
    const p = shownParams();
    return { gid: q.gid, now: e, evs: fit.events || [], lo: p.lo_hz,
             hi: p.hi_hz };
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
      // The fit's own filter, so the window shows what was measured.
      hp: String(p.lo_hz), lp: String(p.hi_hz),
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
      pushXplore();
      return true;
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
    BARRY.activity.log('rootcanal.xplore', { gid: xt.gid, t: e.t, cls: e.cls,
                                             pooled: viewMode === 'pooled' });
    /* WAITED FOR, not assumed. The window is a whole application booting
       and reading the recording before it has anything to put a mark on. */
    const until = Date.now() + 60000;
    while (Date.now() < until) {
      if (!xOpen()) return false;
      if (pushXplore()) return true;
      await new Promise((r) => setTimeout(r, 250));
    }
    return false;
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
    const evs = xt.evs;
    const at = evs.indexOf(xt.now);
    const now = at >= 0 ? evs[at] : null;
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

  async function loadPool() {
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
    if (viewMode === 'pooled') render();
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
    if (!quiet && viewMode === 'pooled') swap('.rc-shelf', shelfCard());
  }

  const candOf = (key) => (pool.cands || []).find((c) => c.key === key) || null;

  /* The settings an unbanked member is fitted at: Single's, as they stand.
     Stated on the members card, because a pool whose members were fitted at
     different settings without saying so is not one question. */
  function singleParams() {
    const out = {};
    for (const k2 of PKEYS) out[k2] = Number(q[k2]);
    return out;
  }

  function typeFor(mk, fallback) {
    return pool.types[mk] || fallback || '';
  }

  function toggleMember(key, on) {
    const c = candOf(key);
    const have = pool.sel.findIndex((m) => m.key === key);
    if (on && have < 0) {
      pool.sel.push(c && !c.banked ? { key, params: singleParams() } : { key });
      pool.fitErr = null;
    } else if (!on && have >= 0) {
      pool.sel.splice(have, 1);
    } else {
      return;
    }
    pool.dirty = true;
    render();
  }

  function setType(mk, value, fallback) {
    const v = String(value || '').trim();
    if (!v || v === (fallback || '')) delete pool.types[mk];
    else pool.types[mk] = v;
    pool.dirty = true;
    render();
  }

  function serverFocus() {
    const f = pool.focus;
    if (!f) return null;
    if (f.mouse_key) return { mouse_key: f.mouse_key };
    if (f.mouse_type) return { mouse_type: f.mouse_type };
    return null;            // a member focus is a dimming, not a second test
  }

  function poolBody() {
    return {
      members: pool.sel.map((m) => (m.params ? { key: m.key, params: m.params }
                                             : { key: m.key })),
      mouse_types: Object.assign({}, pool.types),
      focus: serverFocus(),
    };
  }

  async function runPool() {
    if (!pool.sel.length) {
      toast('Tick at least one recording to pool.', 'warn', 5000);
      return null;
    }
    const mine = ++pool.gen;
    const body = poolBody();
    pool.lastBody = body;
    pool.fitting = true;
    tickBusy();
    let got;
    try {
      got = await apiPost('/api/rootcanal/pool/fit', body);
    } catch (e) {
      if (mine !== pool.gen) return null;
      pool.fitting = false;
      /* A REFUSAL IS ABOUT THE MEMBERS, so it is said beside them -- members
         measured over different HF bands, most often, which cannot share
         one power axis. The picture that was on screen stays: it is still
         the answer for the members it was drawn from. */
      pool.fitErr = e.message;
      if (!pool.fit || !pool.fit.ok) pool.fit = { ok: false, error: e.message };
      toast(e.message, 'err', 10000);
      render();
      return null;
    }
    if (mine !== pool.gen) return null;
    pool.fitting = false;
    pool.fitErr = null;
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
      members: body.members.length, focus: body.focus,
    });
    render();
    if (pool.picked != null) loadPoolEvent();
    return got;
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
      list = Array.from(seen).sort((a, b) => String(a).localeCompare(String(b)));
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
      shape: poolShape,
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
    pushXplore();
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
    // The server's own word: no request body means no read here to ask.
    if (Object.prototype.hasOwnProperty.call(m, 'event_body')
        && m.event_body == null) return false;
    if (m.here === false) return false;
    const c = candOf(m.key);
    return !(c && c.here === false);
  }

  const AWAY = 'This member’s read is not on this machine: it was banked '
             + 'from a read made elsewhere, so its pooled numbers are here and '
             + 'its trace is not. Open it in Single on the machine that read it.';

  function poolEventNote() {
    const e = poolPicked();
    if (!e) return null;
    const m = poolMember(e);
    if (m && !memberHere(m)) return AWAY;
    if (pool.evFor === pool.picked && pool.evData && pool.evData.ok === false) {
      return pool.evData.error;
    }
    return null;
  }

  const loadPoolEvent = debounce(async function loadPoolEvent_() {
    const j = pool.picked;
    const e = poolPicked();
    if (!e) return;
    const m = poolMember(e);
    if (!memberHere(m)) {
      pool.evData = { ok: false, error: AWAY };
      pool.evFor = j;
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

  function paintPool(box) {
    if (!pool.cands && !pool.candsErr) {
      box.appendChild(loading('Reading what can be pooled',
                              'banked Root Canal results and reads cached here'));
      return;
    }
    box.appendChild(shelfCard());
    if (pool.open || pool.fit || pool.sel.length) box.appendChild(openPoolCard());
    box.appendChild(membersCard());
    /* Always in the tree, so the first pool -- half a minute cold -- has a
       line to say so in. Before, it only existed inside the workbench, and
       there is no workbench until something has been pooled. */
    box.appendChild(poolBusyLine());
    const w = poolWork();
    if (w) box.appendChild(w);
  }

  /* The saved pools: the shelf. Opening one restores its members, its
     overrides and its focus, and draws what was saved -- no refit, no
     recording read. */
  function shelfCard() {
    const kids = [el('div', { class: 'section-label', text: 'Saved pools' })];
    if (!pool.shelf) {
      kids.push(el('p', { class: 'hint', text: 'Reading the saved pools…' }));
    } else if (pool.shelfErr) {
      kids.push(el('p', { class: 'hint rc-warn', text:
        'The saved pools could not be read: ' + pool.shelfErr }));
    } else if (!pool.shelf.length) {
      kids.push(el('div', { class: 'empty-state rc-shelf-empty' }, [
        el('p', { text: 'No pool has been saved yet. Tick recordings below, '
                      + 'pool them, and save the pool under a label.' }),
      ]));
    } else {
      kids.push(el('div', { class: 'bm-list rc-shelf-list' }, pool.shelf.map((p) => {
        const id = p.artifact_id || p.id;
        const on = !!(pool.open && pool.open.artifact_id === id);
        return el('div', { class: 'bm-row rc-shelf-row' + (on ? ' on' : '') }, [
          el('span', { class: 'mk-name', text: p.nickname || p.name || id }),
          p.version != null ? el('span', { class: 'flagchip',
                                           text: 'v' + p.version }) : null,
          el('span', { class: 'flagchip', text: (p.n_members != null ? p.n_members
                                                  : (p.n || 0)) + ' recordings' }),
          unbankedChip(p.n_unbanked || 0),
          el('span', { class: 'person-what', text: p.name || '' }),
          BARRY.ui.button({ kind: 'mini', text: on ? 'Open' : 'Open',
            title: 'Reopen it as it was saved. Nothing is refitted and no '
                 + 'recording is read.',
            onclick: () => openSaved(id) }),
        ].filter(Boolean));
      })));
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
     how many recordings and mice, and whether any of it is unbanked. */
  function openPoolCard() {
    const f = pool.fit && pool.fit.ok ? pool.fit : null;
    const members = f ? (f.members || []) : pool.sel.map((m) => candOf(m.key))
      .filter(Boolean);
    const mice = new Set(members.map((m) => m.mouse_key).filter(Boolean));
    const nUnb = f ? unbankedOf(members)
                   : pool.sel.filter((m) => { const c = candOf(m.key);
                                              return c && !c.banked; }).length;
    const primarySave = !pool.dirty && !!f;
    return BARRY.ui.workbenchCard({
      title: pool.open ? pool.open.nickname : 'A pool not saved yet',
      extra: 'rc-pool-card',
      chips: [
        BARRY.ui.chip(pool.open ? 'v' + pool.open.version : 'not saved',
                      { flag: true }),
        pool.saved ? BARRY.ui.chip('as saved: nothing refitted', { flag: true })
                   : null,
        pool.dirty ? BARRY.ui.chip('changed: pool again to see it',
                                   { flag: true, kind: 'warn' }) : null,
        unbankedChip(nUnb),
      ].filter(Boolean),
      count: members.length + ' recording' + (members.length === 1 ? '' : 's')
             + ' · ' + mice.size + ' mice',
      owner: { name: (pool.open && pool.open.by) || null },
      when: pool.open && pool.open.updated ? String(pool.open.updated) : null,
      actions: [
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Close this pool',
          title: 'Puts it down. Closing saves nothing and costs nothing; a '
               + 'saved pool is on the shelf above.',
          onclick: closePool }),
        BARRY.ui.button({ kind: primarySave ? 'primary' : 'ghost', size: 'sm',
          text: saveLabel(), extra: 'rc-save',
          disabled: !pool.sel.length,
          title: 'Saved as a Jarvis artifact, refitted on the server from its '
               + 'members. Nothing goes to the Event Bank.',
          onclick: saveDialog }),
      ],
    });
  }

  /* Which recordings, and what type each mouse is. */
  function membersCard() {
    const kids = [el('div', { class: 'section-label', text: 'Recordings in the pool' })];
    if (pool.candsErr) {
      kids.push(el('p', { class: 'hint rc-warn', text:
        'What can be pooled could not be read: ' + pool.candsErr }));
    }
    const sp = singleParams();
    kids.push(el('p', { class: 'hint', text:
      'A banked result reads no recording. An unbanked one is a Root Canal '
      + 'read cached on this machine, fitted at Single’s settings as they '
      + 'stand when it is ticked: ' + hz(sp.lo_hz) + '–' + hz(sp.hi_hz)
      + ' Hz, ±' + hz(sp.win_ms) + ' ms, half-width ±' + hz(sp.cross_ms)
      + ' ms, ' + hz(sp.band_lo) + '–' + hz(sp.band_hi) + ' Hz. Only sets '
      + 'that have been through Braces are offered.' }));
    const cs = pool.cands || [];
    if (!cs.length && !pool.candsErr) {
      kids.push(el('div', { class: 'empty-state rc-pool-empty' }, [
        el('p', { text: 'Nothing can be pooled yet. Bank a set in Single, or '
                      + 'read one there: a read cached on this machine can '
                      + 'join a pool before it is banked.' }),
      ]));
    }
    const sel = new Set(pool.sel.map((m) => m.key));
    if (cs.length) {
      kids.push(el('table', { class: 'tbl rc-pool-cands' }, [
        el('thead', {}, [el('tr', {}, ['', 'recording', 'mouse', 'type',
                                       'kind', 'events']
          .map((t) => el('th', { text: t })))]),
        el('tbody', {}, cs.map((c) => {
          const can = c.banked || c.here !== false;
          return el('tr', { class: sel.has(c.key) ? 'on' : null,
                            'data-key': c.key }, [
            el('td', {}, [el('input', {
              type: 'checkbox', class: 'rc-pool-pick',
              checked: sel.has(c.key) ? 'checked' : null,
              disabled: can ? null : 'disabled',
              title: can ? '' : 'Its read is not on this machine, and it is '
                              + 'not banked, so there is nothing to pool.',
              onchange: (ev2) => toggleMember(c.key, ev2.target.checked),
            })]),
            el('td', { text: c.session_label || c.entry_id }),
            el('td', { text: c.mouse_key || '' }),
            el('td', { text: typeFor(c.mouse_key, c.mouse_type) }),
            el('td', {}, [
              c.banked
                ? BARRY.ui.chip('banked' + (c.version ? ' v' + c.version : ''),
                                { flag: true })
                : BARRY.ui.chip('not banked', { flag: true, kind: 'warn' }),
              c.here === false
                ? BARRY.ui.chip('read elsewhere', { flag: true,
                    title: 'Its numbers can be pooled; its traces cannot be '
                         + 'opened on this machine.' })
                : null,
            ].filter(Boolean)),
            /* The set's size. Its DS/IED counts are not drawn here: an
               unbanked read is fitted when it is pooled, not to draw a list. */
            el('td', { text: String(c.n != null ? c.n : '') }),
          ]);
        })),
      ]));
    }
    // Members of an opened pool that this machine does not offer.
    const missing = pool.sel.filter((m) => !candOf(m.key));
    if (missing.length) {
      kids.push(el('p', { class: 'hint rc-warn', text:
        missing.length + ' member' + (missing.length === 1 ? '' : 's')
        + ' of this pool ' + (missing.length === 1 ? 'is' : 'are') + ' not among '
        + 'what this machine can pool. They stay in the pool as saved; pooling '
        + 'again here would need them.' }));
    }

    /* Mouse type, per mouse in the pool: the registry's filing unless
       somebody says otherwise, free text with the types already in use as
       suggestions. The override is the pool's, not the registry's. */
    const mice = new Map();
    for (const m of pool.sel) {
      const c = candOf(m.key);
      if (c && c.mouse_key && !mice.has(c.mouse_key)) mice.set(c.mouse_key, c);
    }
    if (mice.size) {
      const inUse = new Set();
      for (const c of cs) if (c.mouse_type) inUse.add(c.mouse_type);
      for (const k2 of Object.keys(pool.types)) inUse.add(pool.types[k2]);
      kids.push(el('div', { class: 'section-label', text: 'Mouse type' }));
      kids.push(el('datalist', { id: 'rcTypeList' },
        Array.from(inUse).sort().map((t) => el('option', { value: t }))));
      kids.push(el('div', { class: 'rc-types' }, Array.from(mice.entries())
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
    }

    const nMice = mice.size;
    if (pool.fitErr) {
      kids.push(el('p', { class: 'hint rc-warn rc-pool-refused',
                          text: 'Not pooled: ' + pool.fitErr }));
    }
    kids.push(BARRY.ui.actions([
      el('span', { class: 'hint', text: pool.sel.length + ' recording'
        + (pool.sel.length === 1 ? '' : 's') + ' ticked, ' + nMice + ' mice'
        + (pool.dirty && pool.fit ? ' — changed since the picture below' : '') }),
      BARRY.ui.button({
        kind: (pool.dirty || !pool.fit) ? 'primary' : 'ghost',
        text: 'Pool ' + pool.sel.length + ' recording'
              + (pool.sel.length === 1 ? '' : 's'),
        extra: 'rc-pool-run',
        disabled: !pool.sel.length || pool.fitting,
        title: 'One z-score over the pooled raw numbers, one k-means, and the '
             + '1-vs-2 group test. Banked members read no recording.',
        onclick: runPool,
      }),
    ]));
    return el('div', { class: 'card rc-members' }, kids);
  }

  function poolChip() {
    const f = pool.fit && pool.fit.ok ? pool.fit : null;
    const n = f ? (f.members || []).length : 0;
    return el('span', {
      class: 'rc-chip' + (pool.dirty ? ' rc-chip-stale' : ''),
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
      return el('div', { class: 'rc-work' }, [
        el('div', { class: 'card rc-err' }, [
          el('strong', { text: 'That pool could not be fitted' }),
          el('p', { class: 'hint', text: f.error }),
        ]),
      ]);
    }
    return el('div', { class: 'rc-work rc-pool-work' }, [
      poolTop(),
      poolPickBar(),
      poolLegend(),
      el('div', { class: 'rc-main' }, [spacePane(), flatsPane(), eventPane()]),
      gmmPanel(),
      switchPanel(),
    ]);
  }

  const pct = (r) => (r == null || !isFinite(r) ? '—'
                      : (100 * r).toFixed(1) + '%');

  function poolTop() {
    const f = pool.fit;
    const c = f.counts || {};
    const sw = f.switches || {};
    const colour = el('select', { class: 'rc-colour',
      onchange: (e) => setColour(e.target.value) },
      COLOURS.map(([id, nm]) => el('option', { value: id, text: nm,
        selected: pool.colour === id ? 'selected' : null })));
    const mice = Array.from(new Set(poolEvents().map((e) => e.mouse_key)
      .filter(Boolean))).sort();
    const types = Array.from(new Set(poolEvents().map((e) => e.mouse_type)
      .filter(Boolean))).sort();
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
          disabled: !memberHere(m),
          title: memberHere(m)
            ? 'That recording at this event, in a window of its own that '
              + 'follows as you step.'
            : AWAY,
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
    if (mode === 'pool' || mode === 'single') {
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
    return el('div', { class: 'card rc-switch' }, [
      el('div', { class: 'section-label', text:
        'Identity switches: each event’s own call against the pooled one' }),
      el('div', { class: 'rc-sw-top' }, [
        el('table', { class: 'tbl rc-crosstab' }, [
          el('thead', {}, [el('tr', {}, ['single ↓  pooled →', 'DS', 'IED']
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
    ]);
    let rep = null;
    return BARRY.ui.bankDialog({
      kind: 'entry',
      title: pool.open ? 'Save v' + nextPoolVersion() + ' of ‘' + pool.open.nickname + '’'
                       : 'Save this pool',
      name: pool.open ? pool.open.nickname : '',
      what,
      okText: pool.open ? 'Save as v' + nextPoolVersion() : 'Save pool',
      onBank: async ({ name, note }) => {
        const nick = String(name || '').trim();
        if (!nick) throw new Error('A pool needs a label to be saved under.');
        rep = await apiPost('/api/rootcanal/pool/save', {
          artifact_id: pool.open ? pool.open.artifact_id : null,
          nickname: nick,
          members: poolBody().members,
          mouse_types: Object.assign({}, pool.types),
          focus: pool.focus,
          note: note || '',
        });
      },
    }).then((ok) => {
      if (!ok || !rep) return null;
      afterSave(rep);
      return rep;
    });
  }

  function afterSave(rep) {
    pool.open = {
      artifact_id: rep.artifact_id, version: rep.version,
      nickname: rep.nickname, name: rep.name,
      by: (pool.open && pool.open.by) || null, updated: null,
    };
    toast(rep.confirmed
      ? 'Nothing has changed since v' + rep.version + ' of ‘' + rep.nickname
        + '’, so that version is confirmed rather than a new one made.'
      : 'Saved as v' + rep.version + ' of ‘' + rep.nickname + '’.',
      rep.confirmed ? 'warn' : 'ok', 8000);
    BARRY.activity.log('rootcanal.pool_save', {
      artifact: rep.artifact_id, version: rep.version, confirmed: !!rep.confirmed,
    });
    pool.shelf = null;
    loadShelf();
    render();
  }

  async function openSaved(id, version) {
    let got;
    try {
      got = await api('/api/rootcanal/pool/' + encodeURIComponent(id)
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
    pool.sel = (pay.members || []).map((m) => (m.banked === false
      ? { key: m.key, params: (m.pin || {}).params || singleParams() }
      : { key: m.key }));
    pool.types = Object.assign({}, pay.mouse_types || {});
    pool.focus = pay.focus || null;
    pool.open = {
      artifact_id: art.artifact_id || art.id || id,
      version: art.version != null ? art.version : pay.version,
      nickname: art.nickname || '', name: art.name || '',
      by: art.by || (art.added || {}).by || null,
      updated: art.updated || null,
    };
    BARRY.activity.log('rootcanal.pool_open', { artifact: pool.open.artifact_id,
                                                version: pool.open.version });
    render();
    return got;
  }

  function closePool() {
    pool.sel = []; pool.types = {}; pool.focus = null;
    pool.fit = null; pool.evs = null; pool.saved = false; pool.dirty = false;
    pool.open = null; pool.picked = null; pool.evData = null; pool.evFor = null;
    render();
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

  return {
    paint,
    /* For web/_dev/rootcanal.html, which drives the real panel rather than
       a copy of it. A harness that reimplements the thing it is testing
       tests nothing. */
    _state: () => ({ q, pend, fit, picked, job, cands, evData, busy,
                     fitting, chooserOpen, live, view: Object.assign({}, view),
                     bulk }),
    _pickSet: pickSet,
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
    _tickBulk: () => (swap('.rc-bulk-card', bulkCard())
                      || swap('.rc-mode', modeSwitch())),
    _endBulk: () => { bulk.job = null; bulk.on = false; render(); },
    /* Pooled, for web/_dev/rootcanalpool.html. */
    _setView: setView,
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
    _reset: () => {
      cands = null; q.entry = null; q.gid = null; q.from_version = null;
      forget();
      for (const k of PKEYS) { q[k] = DEF[k]; pend[k] = DEF[k]; }
      view.yaw = YAW0; view.pitch = PITCH0; view.zoom = 1;
    },
  };
}());
