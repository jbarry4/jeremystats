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
    if (zmapFor === fit) return zmap;
    zmapFor = fit;
    zmap = [0, 1, 2].map((a) => {
      let n = 0, sz = 0, sr = 0, szz = 0, szr = 0;
      for (const e of ((fit && fit.events) || [])) {
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
      const cs = (fit && fit.centres) || [];
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
    if (q.read && fit && fit.ok && document.getElementById('rcSpace')) {
      drawAll();
    }
    watchSize();
  }

  function paint_() {
    const box = host();
    if (!box) return;
    box.innerHTML = '';
    box.appendChild(intro());
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
      BARRY.ui.seg([
        ['one', 'One set at a time'],
        ['many', 'Many sets at once'],
      ], mode, (id) => {
        bulk.on = id === 'many';
        render();
        if (bulk.on && !bulk.plan) loadBulk();
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
          + '  ·  ' + (v ? 'v' + v.name : 'as it is now')
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
      const vlist = el('div', { class: 'bm-list rc-list' });
      const want = defaultVersion(cur);
      for (const v of vers) {
        const ref = versionRef(v);
        const on = String(ref) === String(q.from_version);
        const ok = usable(v);
        const rcOut = v.tag === 'rootcanal';
        vlist.appendChild(el('label', {
          class: 'bm-row' + (on ? ' on' : '') + (ok ? '' : ' off'),
          title: ok ? (v.note || '') : (v.why_not || 'not readable here'),
        }, [
          el('input', {
            type: 'radio', name: 'rcVer',
            disabled: ok ? null : 'disabled',
            checked: on ? 'checked' : null,
            onchange: () => {
              q.from_version = ref;
              forget();
              render();
            },
          }),
          el('span', { class: 'mk-name', text: 'v' + v.name }),
          v.n != null ? el('span', { class: 'flagchip',
                                     text: v.n + ' stamps' }) : null,
          rcOut ? el('span', { class: 'flagchip rc-done',
                               text: 'Root Canal’s own output' }) : null,
          el('span', { class: 'person-what', text:
            (v.aligned ? 'aligned' : 'not aligned')
            + (v.by ? '  ' + v.by : '')
            + (want && versionRef(want) === ref ? '  · the default' : '') }),
        ].filter(Boolean)));
      }
      box.appendChild(vlist);
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
  function nextName(c) {
    const vs = (c && c.versions) || [];
    const tip = vs.length ? String(vs[vs.length - 1].name) : null;
    if (tip != null && /^\d+$/.test(tip)) return String(Number(tip) + 1);
    return null;
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
    return 'Bank: ' + nDs + ' DS as ' + (nx ? 'v' + nx : 'a new version')
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
        modeChip(),
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
        modeChip(),
        el('span', { class: 'hint', text: 'raw units · drag a centre to move it' }),
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
    return el('div', { class: 'rc-pane rc-event' }, [
      why ? el('p', { class: 'rc-ev-why', text: why }) : null,
      el('div', { class: 'rc-ev-grid' }, [
        cell('rcTrace', 'Max-amp contact', 'CSC' + e.contact + ', the fit filter'),
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
    const cross = hz(shownParams().cross_ms);
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
    if (picked == null || !fit || !fit.ok) return null;
    return (fit.events || []).find((x) => x.i === picked) || null;
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
    const note = el('input', { type: 'text', class: 'rc-note',
      placeholder: 'A note for the version, if there is anything to say' });
    const body = el('div', { class: 'rc-ask' }, [
      el('p', { text: bankLabel() + '.' }),
      el('ul', {}, [
        el('li', { text: (c.ds || 0) + ' dentate spikes stay in the set, '
                         + 'read from ' + (v ? 'v' + v.name : 'the set as it '
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
      note,
    ]);
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Bank this root canal?' }),
        el('div', { class: 'spacer' })]),
      el('div', { class: 'mb' }, [body]),
      BARRY.ui.modalFoot([], [
        BARRY.ui.button({ kind: 'ghost', text: 'Cancel', onclick: closeModal }),
        BARRY.ui.button({ kind: 'primary', text: 'Bank it',
          onclick: () => { const t = note.value.trim(); closeModal();
                           commit(t); } }),
      ]),
    ]), { replace: true });
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

  async function commit(note, again) {
    let rep;
    const expect = fit.counts || {};
    try {
      rep = await apiPost('/api/rootcanal/commit', fitBody({
        note: note || '', pngs: pngs(),
        again: again ? true : undefined,
      }));
    } catch (e) {
      /* A SET ROOT CANAL HAS ALREADY CLEANED IS REFUSED, and says why.

         Running this over its own output takes a second bite: k-means
         will still split a clean set in two, and the "IEDs" it finds are
         the loudest dentate spikes. The server's sentence is shown as it
         is, and cleaning again anyway is on offer only as the secondary
         action of a dialog -- a deliberate second press, never the
         default one. */
      const v = versionOf(setOf(), q.from_version);
      if (!again && ((v && v.tag === 'rootcanal') || /again/i.test(e.message))) {
        refusedDialog(e.message, note);
      } else {
        toast(e.message, 'err', 12000);
      }
      return null;
    }
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

  function drawAll() {
    drawMain();
    drawEvent();
    watchSize();
  }

  function drawMain() {
    if (!fit || !fit.ok) return;
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

  function drawMark(g, k, x, y, r, e, kind, alpha) {
    g.globalAlpha = alpha == null ? 1 : alpha;
    if (kind === 'hollow') {
      g.beginPath();
      g.arc(x, y, r, 0, 6.2832);
      g.strokeStyle = e.cls ? colOf(e.cls) : k.dim;
      g.lineWidth = 1.2;
      g.stroke();
    } else if (kind === 'square') {
      const s2 = r * 0.95;
      g.fillStyle = colOf(e.cls);
      g.fillRect(x - s2, y - s2, 2 * s2, 2 * s2);
      g.strokeStyle = k.text;
      g.lineWidth = 1;
      g.strokeRect(x - s2, y - s2, 2 * s2, 2 * s2);
    } else {
      g.beginPath();
      g.arc(x, y, r, 0, 6.2832);
      g.fillStyle = colOf(e.cls);
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
    if (e.flipped) {
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
    if (!s || !fit || !fit.ok) return;
    const k = ink();
    const g = s.g;
    const evs = fit.events || [];
    const cs = centresShown();
    const p = shownParams();

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
      items.push({ d: P.d, kind: 'e', e, P, hollow: zz.hollow, mk });
      pts.push({ i: e.i, x: P.x, y: P.y, depth: P.d, hollow: zz.hollow,
                 r: 3.4, mark: mk, wide: !!e.wide }); 
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
        drawMark(g, k, it.P.x, it.P.y, r, e, it.mk, 0.45 + 0.55 * near);
      } else {
        drawCentre(g, k, it.c, it.P.x, it.P.y);
      }
    }

    // The picked one, on top of everything, in all four views.
    let pickedAt = null;
    if (picked != null) {
      const pp = pts.find((x) => x.i === picked);
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
    for (const e of (fit.events || [])) {
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
    if (!s || !fit || !fit.ok) return;
    const k = ink();
    const g = s.g;
    const p = shownParams();
    const cs = centresShown();
    /* The range is the fit's, not the drag's. A centre dragged to the edge
       would otherwise stretch the axes under the pointer as it went, and
       the drop would land somewhere other than where it was let go. */
    const fcs = ((fit.centres) || []);
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
    for (const e of (fit.events || [])) {
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
      drawMark(g, k, x, y, 3.2, e, mk, hollow ? 1 : 0.9);
      pts.push({ i: e.i, x, y, hollow, mark: mk, wide: !!e.wide,
                 edge: !hx || !hy });
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
    if (picked != null) {
      const pp = pts.find((x) => x.i === picked);
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
    const d = evData;
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
    const cross = Number(shownParams().cross_ms) || CROSS_V1;
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
    if (!fit || !fit.ok) return;
    const cv = e.target;
    const at = local(e, cv);
    press = { id, x: at.x, y: at.y, yaw: view.yaw, pitch: view.pitch,
              moved: false, centre: null };
    if (id !== 'rcSpace') {
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
        if (i != null) setPicked(i);
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
      if (i != null) setPicked(i);
    }
  }

  function onWheel(e) {
    if (!e.target || e.target.id !== 'rcSpace' || !fit || !fit.ok) return;
    e.preventDefault();
    view.zoom = Math.max(0.4, Math.min(8, view.zoom * Math.exp(-e.deltaY * 0.0015)));
    drawSpace();
  }

  function resetView() {
    view.yaw = YAW0; view.pitch = PITCH0; view.zoom = 1;
    drawSpace();
  }

  function onKey(e) {
    if (!q.read || !fit || !fit.ok) return;
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
                      'rcTrace', 'rcSpec', 'rcStack', 'rcCsd'];
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
    if (redrawing || press || !fit || !fit.ok || !mismatched()) return;
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
  async function recordingPath() {
    const tk = BARRY.views.toolkit;
    if (!tk) return null;
    try { if (tk.loadRegistry) await tk.loadRegistry(); } catch (e) { /* below */ }
    const row = (tk.registryRows ? tk.registryRows() : [])
      .find((r) => r.gid === q.gid);
    return (row && (row.here || [])[0]) || null;
  }

  function xUrl(path, t) {
    const p = shownParams();
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
    const e = pickedEvent();
    if (!e) return false;
    if (xOpen()) {
      try { xWin.focus(); } catch (err) { /* not important */ }
      pushXplore();
      return true;
    }
    const path = await recordingPath();
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
    BARRY.activity.log('rootcanal.xplore', { gid: q.gid, t: e.t, cls: e.cls });
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
    if (!xOpen() || !fit || !fit.ok) return false;
    let xf = null;
    try { xf = xWin.barryXplore; } catch (e) { return false; }
    if (!xf || !xf.current) return false;
    let sess = null;
    try { sess = xf.current(); } catch (e) { return false; }
    if (!sess) return false;
    const evs = fit.events || [];
    const at = picked == null ? -1 : evs.findIndex((e) => e.i === picked);
    const now = at >= 0 ? evs[at] : null;
    try {
      sess.curationMarks = {
        kind: 'rootcanal',
        index: Math.max(0, at),
        at: now ? now.t : null,
        gid: q.gid,
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
      space: GEOM.space, ev: GEOM.ev,
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
    _reset: () => {
      cands = null; q.entry = null; q.gid = null; q.from_version = null;
      forget();
      for (const k of PKEYS) { q[k] = DEF[k]; pend[k] = DEF[k]; }
      view.yaw = YAW0; view.pitch = PITCH0; view.zoom = 1;
    },
  };
}());
