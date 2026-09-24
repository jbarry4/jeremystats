/* ==========================================================================
   dspca.js -- X-ray, step four of The Dentist.

   An X-ray is how a dentist tells one kind of tooth from another. This tells
   DS1 from DS2: Incisor found the spikes, Checkup said which are real,
   Braces put each stamp on its own peak, and here they are split into types.

   THE SHAPE OF THE PANEL
   Three states, and each has to finish before the next means anything:

     1. pick a curated set, and a version to read it from
     2. read it -- minutes, once, cached
     3. the workbench: tune the box, choose the rule, look at what you got

   State 3 is three columns and the middle one is the point:

     CONTROLS          TWO PANES                    THE ANSWER
     the box           voltage traces               PCA scatter
     classes, rule     CSD raster <- drag here      depth profiles +- SEM
     notch, screen     5-100 Hz, 60 Hz notched      DS1/DS2 mean rasters
                       average, or one spike        how it was decided

   WHY THE MIDDLE PANES ARE DRAWN HERE
   The central gesture is a rubber band over DEPTH and TIME at once.
   Xplorefinder's panes hand a mode the time under the pointer and nothing
   else -- `grabTime` has no depth axis in it -- so a pane of our own is the
   honest answer. What is shared is the thing worth sharing: the server's own
   renderer, so the colormap, the robust percentile and the transparent NaN
   for an unread channel are the app's rather than this panel's.

   `Open in Xplorefinder` hands the picked spike to the real view for a
   proper look, filters pinned to the same 5-100 Hz and 60 Hz notch.

   WHAT IS CHEAP AND WHAT IS NOT
   The read is minutes and happens once per (recording, read settings). The
   fit is milliseconds, which is why the box is live rather than behind a
   recompute button -- one request per drag, settled at 60 ms.
   ========================================================================== */
'use strict';

BARRY.dspca = (function () {
  /* What is being asked for. Held here, not read off the DOM, so a redraw
     cannot lose a half-filled form. */
  const q = {
    entry: null,          // the chosen bank entry id
    from_version: null,   // null means "the events as they are now"
    gid: null,
    read: null,           // the read hash, once there is one
    refine: 'off',        // Braces has already done this; see dspca.py

    // The box, in the units a person and a URL both understand.
    sel_lo: null, sel_hi: null,
    t_lo_ms: 0, t_hi_ms: 0,

    nclasses: 2,
    rule: 'tort',
    notch: true,
    screen: false,
    /* How each event's patch becomes the vector the PCA sees. See
       `FEATURES` below, and `normalize_block` in backend/dspca.py. */
    features: 'minmax',
    /* WHICH METHOD. `delta` by default: the thing being clustered is then
       the thing somebody meant to cluster on, and the boundary is a
       threshold that can be read off an axis and quoted. All three are
       computed on every fit either way -- see `METHODS`. */
    method: 'delta',
    min_sep: 5,
    gap_weight: 1,
    /* The depth profile drawn over the raster. On, because it is the
       curve the whole analysis is about and a raster does not show a
       trough well; off is one click for anybody who wants the field
       clean. */
    depth_line: true,
    /* Contacts taken out by hand, on top of whatever the recording is
       already marked with. Repaired, not dropped -- see the note in
       `Params` on the server. */
    manual_bad: [],
    /* A threshold placed by hand on the delta axis, instead of the one
       k-means fitted. Null means "use k-means". */
    delta_cut: null,
    flip: false,
    gain: 4,
    cmap: 'jet',
  };

  let cands = null;     // sets that could be classified
  let plan = null;      // what a run would read
  let job = null;       // the read, while it is happening
  let poll = null;      // its interval
  let fit = null;       // the current answer
  let picked = null;    // which event the panes are showing; null = average
  let pics = {};        // the four pictures, by kind
  let regions = null;   // the layer vocabulary, fetched once
  /* Which request the pictures on screen belong to.
     Three POSTs go out per refresh and a drag can start another before they
     land. Without this the slow answer to an old box arrives last and wins,
     which shows a raster of a selection nobody has any more. */
  let picGen = 0;
  /* The same guard, for the plan.

     Switching sets while a plan is in flight left the OLD set's plan on
     screen: `pickSet` fires one request per set and the answers are not
     guaranteed to come back in the order they went out. The version picker
     is built from `plan.versions`, so the list then belonged to the
     previous set -- and choosing from it asked for a version this set does
     not have, which is the "This set has no version 5" dead end. */
  let planGen = 0;

  /* The box has been dragged and the answer on screen is the previous
     box's. See `onUp`. */
  let dirty = false;
  let fitting = false;         // a fit is in flight
  let drawingWhat = null;      // which picture is being fetched, if any
  let busy = false;
  let dragging = null;  // a rubber band in progress
  /* A cut being dragged along its rail. `at` is the live value, which is
     drawn while the pointer is down and only committed on release: a
     refit per pointermove would be a second of server per pixel. */
  let cutDrag = null;

  /* ---------- guides ----------

     Named depth lines. They are the aid this panel is hardest to use
     without: a sink at CSC30 means nothing until somebody has said where
     the hilus is, and the whole job is comparing one depth against another
     across five pictures at once.

     So they are drawn on EVERY panel that has a depth axis -- the traces,
     the CSD you drag on, the class-average profiles, the class-mean
     rasters -- and dragging one on any of them moves it on all of them,
     because they are one line seen five ways rather than five lines that
     happen to agree.

     They live with the recording (`backend/guides.py`), not with this
     panel, which is what lets Xplorefinder draw the same lines through
     `setChannelLines`. */
  let guides = [];
  let palette = [];       // the inks on offer, from the server
  let dragGuide = null;   // {id, from, at} while one is being moved
  let showLayers = false; // StrataScope's boundaries, as faint context

  /* Where each canvas puts a contact number, recorded as it draws.
     The drag handler inverts these, so a line can be taken hold of on
     whichever picture it is most legible against. */
  const DEPTH = {};
  /* The bulk queue. `on` is whether the card is open, `plan` what a run
     would do, `pick` which entries are ticked, and `job` the run itself.
     Kept beside `q` rather than inside it because none of it is part of the
     question the workbench is asking. */
  const bulk = { on: false, plan: null, pick: {}, job: null, poll: null };

  const $ = (s) => document.querySelector(s);
  const host = () => document.getElementById('tkResult');
  const num = (v, d) => (v == null || !isFinite(v) ? (d || '—') : v);
  const pct = (v) => Math.round(100 * (v || 0)) + '%';

  /* ==================================================================
     Loading
     ================================================================== */
  async function paint() {
    render();
    if (!regions) loadRegions();
    if (!cands) await loadCandidates();
  }

  async function loadGuides() {
    if (!q.gid) { guides = []; return; }
    try {
      const got = await api('/api/guides/' + encodeURIComponent(q.gid));
      guides = got.guides || [];
      palette = got.palette || palette;
    } catch (e) {
      guides = [];
    }
    toXplore();
    render();
    drawAll();
  }

  /* Put a guide somewhere, or move/rename one that is already there.

     The line moves on screen first and the write follows. A guide is an aid
     somebody is dragging while looking at something else; making the
     picture wait for a round trip would make it feel stuck to the pointer
     by a rubber band. */
  async function saveGuide(csc, label, id, color) {
    if (!q.gid) return;
    try {
      const body = { csc: Math.round(csc) };
      if (label !== undefined) body.label = label;
      if (id) body.id = id;
      if (color) body.color = color;
      if (plan && plan.ok) body.session_label = plan.entry.session_label;
      const got = await apiPost('/api/guides/' + encodeURIComponent(q.gid),
                                body);
      guides = got.guides || [];
      palette = got.palette || palette;
    } catch (e) {
      toast(e.message, 'err', 8000);
      await loadGuides();
      return;
    }
    toXplore();
    render();
    drawAll();
  }

  async function dropGuide(id) {
    if (!q.gid) return;
    try {
      const got = await apiPost(
        '/api/guides/' + encodeURIComponent(q.gid) + '/delete',
        id ? { id } : {});
      guides = got.guides || [];
    } catch (e) {
      toast(e.message, 'err', 8000);
    }
    toXplore();
    render();
    drawAll();
  }

  /* The same lines, in Xplorefinder.

     `setChannelLines` is how Incisor already puts a mark on a traces window
     it opened, and it draws on the rasters too -- so this is one call
     rather than a second implementation of a line. `onmove` closes the
     loop: dragging the line THERE writes back here, and the next read of
     this panel has it in its new place.

     Silent when the view has never been opened; a guide is not a reason to
     load a recording. */
  function toXplore() {
    const XF = BARRY.views.xplore;
    if (!XF || !XF.setChannelLines || !XF.current) return;
    const sess = XF.current();
    if (!sess || !q.gid) return;
    /* `sess.identity.gid`, not `sess.gid` -- there is no such property, and
       reading it makes this whole push a silent no-op that looks exactly
       like a working one. xplore.js carries the same warning over its own
       probe write, which is where this was learnt.

       The path is the fallback, for a window opened before its identity has
       been read back. */
    const theirs = (sess.identity || {}).gid;
    const samePath = plan && plan.ok && plan.session
                     && sess.path === plan.session.path;
    if (theirs !== q.gid && !samePath) return;
    XF.setChannelLines(sess, guides.map((g) => ({
      key: 'dspca:' + g.id,
      label: g.label || 'guide',
      colour: g.color || '#101010',
      number: g.csc,
      onmove: (number) => saveGuide(number, undefined, g.id),
    })));
  }

  async function loadRegions() {
    /* Not awaited and not fatal. The guides are a help, not the answer:
       a recording nobody has labelled draws no boundaries and the panel is
       still usable, so a failure here must not stop it painting. */
    try {
      const got = await api('/api/layers/regions');
      regions = got.regions || [];
    } catch (e) { regions = []; }
  }

  async function loadCandidates() {
    try {
      const got = await api('/api/dspca/candidates');
      cands = got.sets || [];
    } catch (e) {
      toast('Could not read the event bank: ' + e.message, 'err', 8000);
      cands = [];
    }
    if (!q.entry && cands.length) pickSet(cands[0].id);
    else render();
  }

  function setOf(id) {
    return (cands || []).find((s) => s.id === (id == null ? q.entry : id));
  }

  function pickSet(id) {
    q.entry = id;
    const s = setOf(id);
    q.gid = s ? s.gid : null;
    /* Start from the newest version that has been through Braces, where
       there is one. Every feature here is read at ONE INSTANT relative to
       the stamp, so a set whose stamps are a few milliseconds out does not
       classify badly -- it classifies a smear. Falling back to the newest
       readable version rather than to the newest, because a version whose
       snapshot never reached this machine has a name, a count and no times. */
    q.from_version = s ? (s.newest_aligned_name || s.newest_usable_name) : null;
    q.read = null;
    fit = null;
    picked = null;
    pics = {};
    render();
    refreshPlan();
  }

  async function refreshPlan() {
    if (!q.entry) { plan = null; render(); return; }
    const mine = ++planGen;
    let got;
    try {
      got = await apiPost('/api/dspca/plan', {
        entry_id: q.entry, from_version: q.from_version, refine: q.refine,
      });
    } catch (e) {
      got = { ok: false, error: e.message };
    }
    // A newer set has been picked since this went out; its plan is the one
    // that belongs on screen, and this one would replace it.
    if (mine !== planGen) return;
    plan = got;
    /* What the server actually read from.

       It falls back when the version asked for is not in this set, and
       says so in `version_note`. Keeping the asked-for one would send the
       same impossible request on every refresh from here on. */
    if (plan && plan.ok && plan.version_note) {
      q.from_version = plan.read_version || null;
    }
    if (plan && plan.ok) {
      q.gid = plan.entry.gid;
      if (plan.read && plan.read.cached) q.read = plan.read.hash;
    }
    render();
    loadGuides();
    if (q.read) refit();
  }

  async function startRead(force) {
    if (busy) return;
    busy = true;
    try {
      const got = await apiPost('/api/dspca/read', {
        entry_id: q.entry, from_version: q.from_version,
        refine: q.refine, force: !!force,
      });
      if (got.cached) {
        q.read = got.read;
        busy = false;
        render();
        refit();
        return;
      }
      job = got.job;
      render();
      watch(got.read);
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
      if (job.status === 'running') { swap('.dp-job', progress()); return; }
      clearInterval(poll);
      poll = null;
      busy = false;
      if (job.status === 'error') {
        toast('The read failed: ' + (job.error || 'no reason given'),
              'err', 12000);
        job = null;
        render();
        return;
      }
      job = null;
      q.read = hash;
      render();
      refit();
    }, 700);
  }

  /* ==================================================================
     The answer, and the pictures
     ================================================================== */

  /* The box the pictures are drawn with.

     While a drag is waiting to be recomputed this is the one in `q`, not
     the one the fit on screen was computed from. The rectangle has to
     follow the pointer -- a box that sprang back to where it was while the
     numbers under it stayed put would read as the drag having failed. Once
     the fit lands the two are the same thing again. */
  /* Which class the spike being looked at was put in, or null for the
     average. Every panel that highlights it asks this one function, so
     the ring on the PCA, the curve on the profile and the outlined class
     mean cannot disagree about which one is on screen. */
  function pickedClass() {
    if (picked == null || !fit || !fit.ok) return null;
    const e = (fit.events || []).find((x) => x.i === picked);
    return e ? e.type : null;
  }

  function shownBox() {
    if (dirty && q.sel_lo != null && q.sel_hi != null) {
      return { lo: q.sel_lo, hi: q.sel_hi,
               t_lo_ms: q.t_lo_ms, t_hi_ms: q.t_hi_ms };
    }
    return (fit && fit.ok && fit.box) || null;
  }

  function fitBody(extra) {
    return Object.assign({
      gid: q.gid, read: q.read,
      nclasses: q.nclasses, rule: q.rule,
      notch: q.notch, screen: q.screen, flip: q.flip,
      features: q.features,
      method: q.method, min_sep: q.min_sep, gap_weight: q.gap_weight,
      manual_bad: q.manual_bad, delta_cut: q.delta_cut,
      sel_lo: q.sel_lo, sel_hi: q.sel_hi,
      t_lo_ms: q.t_lo_ms, t_hi_ms: q.t_hi_ms,
    }, extra || {});
  }

  /* Settled at 60 ms.

     A drag fires pointermove at the display's rate, and a fit is 20 ms of
     server -- so without this the panel would have sixty requests in flight
     and draw the answer to a box nobody is looking at any more. Short enough
     that letting go feels instant. */
  let lastBody = null;          // what the last fit actually asked for
  let fitGen = 0;

  /* Is the box in the form still the one this request asked for? */
  function sameBox(body) {
    return String(body.sel_lo) === String(q.sel_lo)
        && String(body.sel_hi) === String(q.sel_hi)
        && String(body.t_lo_ms) === String(q.t_lo_ms)
        && String(body.t_hi_ms) === String(q.t_hi_ms);
  }

  let refitFrom = null;
  const refitSoon = debounce(async function refit_() {
    if (!q.read) return;
    const mine = ++fitGen;
    const body = fitBody();
    lastBody = body;
    fitting = true;
    /* Just the two lines that changed. Rebuilding the whole panel to say
       "working" would be the most expensive possible way to say it, and it
       would take the ToolKit's activity feed with it. */
    const hadBusy = swap('.dp-busy', busyLine());
    const hadBar = swap('.dp-applybar', applyBar());
    if (!hadBusy || !hadBar) render();
    let got;
    try {
      got = await apiPost('/api/dspca/fit', body);
    } catch (e) {
      if (mine !== fitGen) return;     // a newer fit is already on its way
      /* The box crossing a probe column lands here, and it is the one error
         worth keeping on screen rather than toasting: it is a statement
         about the box that is still selected. */
      fit = { ok: false, error: e.message };
      fitting = false;
      dirty = false;
      render();
      return;
    }
    // Superseded while it was away. Its answer is about a question nobody
    // is asking any more, and showing it would be the slow reply winning.
    if (mine !== fitGen) return;
    fit = got;
    fitting = false;

    /* WHAT THE SERVER SETTLED ON, BACK INTO THE FORM -- but only if the
       form is still asking what this request asked.

       The first fit has no box at all and the server chooses one from the
       event-triggered template, so without this the next drag would start
       from nothing. The guard is the other half, and it is a real fault
       rather than a precaution: a fit takes about a second over seven
       hundred events, a box can be dragged in that second, and this wrote
       the OLD box back over the new one when the answer arrived. From the
       outside the drag simply undid itself a moment after you let go --
       and the recompute that followed then asked for the box you had just
       been moved off.

       Found by the harness: the panel asked for CSC8-12 and the request
       that went out said CSC7-9. */
    const stillMine = sameBox(body);
    if (stillMine) {
      dirty = false;
      q.sel_lo = got.box.lo;
      q.sel_hi = got.box.hi;
      q.t_lo_ms = got.box.t_lo_ms;
      q.t_hi_ms = got.box.t_hi_ms;
    }
    render();
    drawAll();
    /* THE PANE DEPENDS ON THE BOX NOW, and it did not use to.

       The two centre panes are a whole-shank average, and for a long
       time the box really did not enter into them: moving it moved a
       white rectangle drawn client-side and nothing else. The depth
       profile on the raster changed that -- it is averaged over the
       feature window and its landmarks are the sinks the gap was
       measured between, so both move with the box.

       Leaving it out of the refetch left a line on screen that was
       drawn for a box nobody had any more, which is exactly the fault
       the rest of this file is careful about. It costs one more request
       per fit; being right costs that.

       The FIRST fit after a read has no pictures at all, so that one
       still fetches everything. */
    pictures(pics.pane ? ['classes', 'features', 'pane'] : null);
  }, 60);

  /* Wrapped, so the caller is recorded where the call is MADE.

     `debounce` fires the body from a timer, so a stack captured inside it
     is the timer and nothing else -- which is exactly what it said when
     something was refitting and nobody could see what. */
  function refit() {
    try { throw new Error('x'); } catch (e2) {
      refitFrom = String(e2.stack || '').split(String.fromCharCode(10))
        .slice(1, 5).join(' | ');
    }
    return refitSoon.apply(null, arguments);
  }
  refit.now = () => refitSoon();

  /* WHAT ACTUALLY CHANGED, and nothing else.

     The two centre panes show a whole-shank average (or one spike). Neither
     depends on the feature box at all -- moving the box moves the white
     rectangle drawn over them, which is client-side. Only the class means
     change with the box. So a drag refetches one picture rather than three,
     and picking a spike refetches the other two.

     `which` is a list of kinds; omitted means all of them, which is what a
     fresh read wants. */
  async function pictures(which) {
    if (!q.read) { drawingWhat = null; tickBusy(); return; }
    const paneKind = picked == null ? 'shank' : 'event';
    const all = {
      traces: { what: 'traces', index: picked, gain: q.gain },
      pane: { what: paneKind, index: picked },
      classes: { what: 'classes' },
      features: { what: 'features' },
    };
    const want = which && which.length ? which : Object.keys(all);
    const mine = ++picGen;
    for (const key of want) {
      const extra = all[key];
      if (!extra) continue;
      drawingWhat = key;
      tickBusy();
      try {
        const got = await apiPost('/api/dspca/raster',
                                  fitBody(Object.assign({ cmap: q.cmap },
                                                        extra)));
        // A newer request has been made since this one went out; its answer
        // is the one that belongs on screen.
        if (mine !== picGen) return;
        pics[key] = got;
        drawAll();
      } catch (e) {
        if (mine !== picGen) return;
        pics[key] = { ok: false, error: e.message };
      }
    }
    if (mine === picGen) { drawingWhat = null; tickBusy(); }
  }

  /* ==================================================================
     The page
     ================================================================== */
  /* The panel, rebuilt -- around the one thing in this host that is not
     ours.

     The ToolKit mounts its activity feed into `#tkResult`, the same element
     this panel draws into. `innerHTML = ''` therefore destroyed it, the
     ToolKit's watcher saw `.tf` was gone and mounted a fresh one, and that
     one said "Reading..." and fetched. Every fit did it once and a running
     read did it twice a second.

     The feed is lifted out and put back rather than left to be rebuilt:
     the same element, so its rows, its poller and its listener all survive
     and the ToolKit never sees it missing. */
  function render() {
    const box = host();
    if (!box) return;
    watchSize();
    const feed = box.querySelector('.tf');
    if (feed) box.removeChild(feed);
    try {
      paint_();
    } finally {
      if (feed) box.appendChild(feed);
    }
  }

  function paint_() {
    const box = host();
    if (!box) return;
    box.innerHTML = '';
    box.appendChild(intro());
    if (!cands) { box.appendChild(loading('Reading the event bank')); return; }
    if (!cands.length) { box.appendChild(nothing()); return; }
    box.appendChild(modeSwitch());
    if (bulk.on) {
      box.appendChild(bulkCard());
      return;
    }
    box.appendChild(chooser());
    if (job) { box.appendChild(progress()); return; }
    if (!q.read) { box.appendChild(readCard()); return; }
    box.appendChild(workbench());
    requestAnimationFrame(() => { drawAll(); });
  }

  /* A tick of a running read, without rebuilding the panel.

     `render()` empties the host and appends a fresh tree. That is right
     when the answer changes and wrong twice a second while a read is
     running, because the host is not ours alone: the ToolKit mounts its
     activity feed into the same element. Wiping it took the feed with it,
     the ToolKit's watcher saw `.tf` gone and mounted a new one, and that
     one said "Reading..." and fetched -- so for the whole of a long read
     the feed cycled: Reading..., rows, gone, Reading..., rows, gone. On a
     348-window read it never once finished arriving, and it was a request
     every time round.

     This is the same fault the Braces read had, arriving again in a tool
     written after it was fixed. The ToolKit side coalesces remounts; it
     cannot stop them, because a wiped feed does have to come back. The
     half that has to live here is not wiping it: the progress card is
     swapped for a fresh one where it stands, and everything else in the
     host -- the feed included -- is left where it is.

     A card that is not on screen is not redrawn. Either the tool has been
     left or the batch card is deliberately shut, and rebuilding the host
     to discover that is the thing being fixed. The next change of state
     calls `render()` in full anyway. */
  function swap(sel, node) {
    const box = host();
    const old = box && node ? box.querySelector(sel) : null;
    if (!old) return false;
    old.replaceWith(node);
    return true;
  }

  /* ---------- the bulk queue ----------

     The reads, and only the reads. Typing a set is a decision with somebody's
     name on it, and forty of them made by a queue while nobody looked is
     exactly what every maintenance action in this app is built to avoid.
     What this does is pay the expensive half in advance, so that afterwards
     each of those sets is a box somebody can drag at milliseconds. */
  function bulkCard() {
    /* No shut state any more: the mode switch above is what opens and
       closes this, and a card that also closed itself meant two controls
       for one thing and a panel that could be in neither mode. */
    const kids = [
      el('div', { class: 'dp-row' }, [
        el('div', { class: 'section-label', style: 'margin:0',
                    text: 'Read a batch' }),
        el('div', { style: 'flex:1' }),
      ]),
    ];
    if (bulk.job) {
      const st = (bulk.job.stages || [])[0] || {};
      kids.push(el('div', { class: 'hint', text:
        'Reading ' + (st.done || 0) + ' of ' + (st.of || '?')
        + ' recordings' }));
      kids.push(el('div', { class: 'dp-bar' }, [
        el('i', { style: 'width:'
                  + (100 * (st.of ? (st.done || 0) / st.of : 0)).toFixed(1)
                  + '%' })]));
      /* A SET THAT IS DONE CAN BE OPENED WHILE THE REST RUN.

         The read is the expensive half and it is finished for that one;
         nothing about the others is in its way. The queue used to be a
         plain table, so the answer to "this one is done, let me look at
         it" was to wait for the whole batch -- which on a cohort is the
         difference between a coffee and an afternoon. The same thing
         Braces does with the proposals it files as they land.

         The batch keeps running. Opening a set only changes what this
         panel is showing; the job is on the server and the poll below
         does not stop, which is why the switch above keeps reporting it. */
      kids.push(el('table', { class: 'tbl dp-bulk' }, [
        el('tbody', {}, (bulk.job.members || []).map((m) => {
          const ready = m.status === 'done';
          return el('tr', {
            class: m.status === 'error' ? 'bad' : (ready ? 'ready' : null),
          }, [
            el('td', {}, [
              ready
                ? el('button', {
                    class: 'mini', text: m.label,
                    title: 'Open this one now. The rest of the batch keeps '
                         + 'reading.',
                    onclick: () => openRead(m.id),
                  })
                : el('span', { text: m.label }),
            ]),
            el('td', { text: m.cached ? 'already read'
                             : m.status === 'running'
                               ? (m.of ? m.done + ' / ' + m.of
                                       : 'reading\u2026')
                               : m.status }),
            el('td', { class: 'dim', text: m.error || '' }),
          ]);
        })),
      ]));
      kids.push(el('button', { class: 'btn ghost sm', text: 'Stop',
        onclick: () => apiPost('/api/cfc/job/' + bulk.job.id + '/cancel', {})
                         .catch(() => {}) }));
      return el('div', { class: 'card dp-bulk-card' }, kids);
    }
    if (!bulk.plan) {
      kids.push(loading('Working out what could be read'));
      return el('div', { class: 'card dp-bulk-card' }, kids);
    }
    const bp = bulk.plan;
    kids.push(el('div', { class: 'hint', text:
      bp.n + ' could be read now  \u00b7  ' + bp.n_done + ' already read  '
      + '\u00b7  ' + bp.n_blocked + ' cannot be' }));

    /* Already read, and therefore instant to open. These were listed as a
       count and nothing else, so the reading paid for last week was
       reachable only by going back to one-at-a-time and finding the set
       in the picker. */
    if ((bp.done || []).length) {
      kids.push(el('div', { class: 'section-label', text: 'Already read' }));
      kids.push(el('div', { class: 'dp-done-list' },
        bp.done.slice(0, 24).map((r) => el('button', {
          class: 'mini', text: r.label,
          title: 'Open it. The read is cached, so this is immediate.',
          onclick: () => openRead(r.entry_id),
        }))));
    }
    if (bp.todo.length) {
      kids.push(el('table', { class: 'tbl dp-bulk' }, [
        el('thead', {}, [el('tr', {}, ['', 'set', 'spikes', 'aligned']
          .map((t) => el('th', { text: t })))]),
        el('tbody', {}, bp.todo.map((r) => el('tr', {}, [
          el('td', {}, [el('input', {
            type: 'checkbox', checked: bulk.pick[r.entry_id] !== false || null,
            onchange: (e) => { bulk.pick[r.entry_id] = e.target.checked; },
          })]),
          el('td', { text: r.label }),
          el('td', { text: String(r.n_good) }),
          /* Said rather than enforced. A set can be classified without
             having been through Braces and the numbers are still numbers --
             but every feature here is read at one instant relative to the
             stamp, so it is worth seeing before spending the read. */
          el('td', { class: r.aligned ? '' : 'dim',
                     text: r.aligned ? ('v' + r.aligned) : 'not aligned' }),
        ]))),
      ]));
      kids.push(el('button', { class: 'btn', text: 'Read the ticked',
                               onclick: runBulk }));
    }
    if (bp.blocked.length) {
      kids.push(el('div', { class: 'section-label', text: 'Left out' }));
      kids.push(el('table', { class: 'tbl dp-bulk' }, [
        el('tbody', {}, bp.blocked.slice(0, 12).map((r) => el('tr', {}, [
          el('td', { text: r.label }),
          el('td', { class: 'dim', text: r.why }),
        ]))),
      ]));
      if (bp.blocked.length > 12) {
        kids.push(el('p', { class: 'hint',
                            text: 'and ' + (bp.blocked.length - 12)
                                  + ' more' }));
      }
    }
    return el('div', { class: 'card dp-bulk-card' }, kids);
  }

  async function loadBulk() {
    try {
      bulk.plan = await api('/api/dspca/batch/plan');
    } catch (e) {
      bulk.plan = { ok: false, todo: [], done: [], blocked: [],
                    n: 0, n_done: 0, n_blocked: 0 };
      toast(e.message, 'err', 8000);
    }
    render();
  }

  /* Open one set from the queue, leaving the queue running.

     `pickSet` does the rest: the plan comes back saying the read is
     cached, so `refreshPlan` sets the hash and the fit follows without
     touching the disk. */
  function openRead(entryId) {
    if (!entryId) return;
    bulk.on = false;
    pickSet(entryId);
    BARRY.activity.log('dspca.open_from_batch', { entry: entryId });
  }

  async function runBulk() {
    const want = (bulk.plan.todo || [])
      .filter((r) => bulk.pick[r.entry_id] !== false)
      .map((r) => r.entry_id);
    if (!want.length) { toast('Nothing is ticked.', 'warn', 5000); return; }
    try {
      const got = await apiPost('/api/dspca/batch', { entries: want });
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
        /* WHICHEVER MODE YOU ARE IN.
           
           Taking a finished set out of the queue to look at it switches
           to one-at-a-time, and the queue card is then not on screen --
           so a poll that only refreshed that card left the count frozen
           at whatever it said when you left. The batch was still
           running; the panel had simply stopped saying so, which reads
           exactly like it had stopped. The mode switch carries the
           count in that case, so refresh whichever of the two is
           there. */
        if (!swap('.dp-bulk-card', bulkCard())) {
          swap('.dp-mode', modeSwitch());
        }
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
           + '. Nothing was classified or banked.'),
        quit ? 'warn' : 'ok', 8000);
      // The plan has changed: what was `todo` is now `done`.
      bulk.plan = null;
      loadBulk();
      // And the switch stops saying a batch is running, wherever you
      // happen to be standing.
      if (!bulk.on) swap('.dp-mode', modeSwitch());
    }, 900);
  }

  function intro() {
    return BARRY.ui.stepHeader({
      title: 'X-ray',
      step: 'step 4 of The Dentist',
      blurb: 'Which kind of dentate spike each one is — drag a box on the '
           + 'CSD to choose the depth and time the features come from.',
    });
  }

  function loading(what) {
    return el('div', { class: 'card dp-load' }, [
      loader(what),
    ]);
  }

  function nothing() {
    return el('div', { class: 'card' }, [
      el('p', { class: 'hint', text:
        'Nothing here is ready to classify. A set has to have been through '
        + 'Checkup — a list of candidates nobody has ruled on is a list of '
        + 'maybes, and clustering those would be a PCA of whatever the '
        + 'detector mistook for an event.' }),
    ]);
  }

  /* One set, or many.

     Two genuinely different jobs rather than two views of one. Picking a
     set, checking what it would read and reading it is a thing you do
     while thinking; paying the reading for a whole cohort is a thing you
     set off and come back to. Braces draws exactly this switch for
     exactly this reason, and this is the same control rather than a
     second answer to the same question.

     It replaces a `Read a batch...` button that sat above the panel in
     both modes -- so the batch queue and the workbench were on screen
     together, each taking room from the other, and neither of them was
     what you had come to do. */
  function modeSwitch() {
    return el('div', { class: 'card dp-mode' }, [
      el('div', { class: 'seg' }, [
        ['one', 'One set at a time'],
        ['many', 'Many sets at once'],
      ].map(([id, label]) => el('button', {
        class: (bulk.on ? 'many' : 'one') === id ? 'active' : '',
        onclick: () => {
          if ((bulk.on ? 'many' : 'one') === id) return;
          bulk.on = id === 'many';
          render();
          if (bulk.on && !bulk.plan) loadBulk();
        },
        text: label,
      }))),
      el('span', { class: 'hint', text: bulk.on
        ? 'Reads them one after another and stops there. Nothing is '
          + 'classified and nothing is banked \u2014 every set still has to '
          + 'be read through and called by somebody.'
        : 'Pick a recording, check what it would read, then read it.' }),
      /* A batch left running while you look at one of its results. It is
         still going, and a panel that stopped mentioning it would read as
         having cancelled it. */
      bulk.job && !bulk.on
        ? el('span', { class: 'hint dp-bulk-note', text: (() => {
            const st = (bulk.job.stages || [])[0] || {};
            return 'Batch still reading \u2014 ' + (st.done || 0) + ' of '
                 + (st.of || '?') + '.';
          })() })
        : null,
    ]);
  }

  /* ---------- 1. the set, and which version to read ----------

     The same three controls every other tool in the bundle uses, in the
     same order: a recording you type the name of, the banked entries on
     it as a radio list, and the versions of the chosen one as another.

     It was two dropdowns. A <select> of every curated set in the lab is a
     list you scroll rather than one you search, and it put the recording
     and the entry on one line of text so neither could be read -- with
     the version box beside it, being a second <select>, indistinguishable
     from it. Braces answered this already; this is its answer rather than
     a second one. */
  function chooser() {
    const box = el('div', { class: 'card dp-choose' });

    // One row per recording, named from the registry where it knows the
    // recording and from the set itself where it does not.
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
        gid: c.gid, label: c.session_label || c.name,
        project: c.project, mouse: c.mouse, session: c.session,
        reachable: true,
      });
    }
    rows.sort((x, y) => String(x.label || '').localeCompare(
      String(y.label || '')));

    // Opened on something workable rather than on nothing.
    if (!q.gid || !seen.has(q.gid)) {
      const on = (cands || []).find((c) => c.id === q.entry);
      q.gid = (on && on.gid) || (rows[0] || {}).gid || null;
    }

    box.appendChild(el('div', { class: 'section-label',
                                text: 'Recording' }));
    box.appendChild(BARRY.pickSession({
      rows,
      value: q.gid,
      placeholder: 'Which recording? Type a mouse, session or date\u2026',
      onpick: (r) => {
        if (r.gid === q.gid) return;
        q.gid = r.gid;
        /* A different recording means a different entry, and everything
           downstream of it. Keeping the old one left the panel describing
           a set no longer among the ones on offer -- and asking for its
           version, which is the "no version 5" dead end from the other
           side. */
        /* The first one that can actually be READ, not just the first.
           Auto-picking an unreadable set is how the panel opened on a
           refusal without anybody having chosen anything. */
        const mineHere = (cands || []).filter((c) => c.gid === r.gid);
        const first = mineHere.find((c) => c.readable !== false
                                           && (c.n_good || 0) > 0)
                   || mineHere.find((c) => c.readable !== false);
        plan = null;
        if (first) { pickSet(first.id); return; }
        q.entry = null; q.from_version = null; q.read = null; fit = null;
        render();
      },
    }));

    const mine = (cands || []).filter((c) => c.gid === q.gid);
    if (!mine.length) {
      box.appendChild(el('p', { class: 'confirm-msg', text:
        'Nothing curated is banked against this recording, so there is '
        + 'nothing to classify. Incisor finds the candidates, Checkup goes '
        + 'through them and Braces times them; this is step four.' }));
      return box;
    }

    box.appendChild(el('div', { class: 'section-label',
                                text: 'Which banked entry' }));
    const list = el('div', { class: 'bm-list' });
    for (const c of mine) {
      /* A set with no spikes left in it is SHOWN and cannot be picked.
         Shown, because "every candidate was rejected" is a real answer,
         and a row that silently is not there reads as a set that does not
         exist. */
      const good = c.n_good || 0;
      /* TWO WAYS OF BEING UNPICKABLE, and they are different sentences.

         No spikes left is about the curation. Not readable is about the
         recording -- no registry id, an id this machine has never seen,
         or a recording that is not mounted here. Both are SHOWN and
         disabled rather than left out: "this set exists and cannot be
         used, and here is why" is a real answer, and a row that silently
         is not there reads as a set that does not exist.

         This is the picker no longer offering what the next step
         refuses. It used to list them, and the plan then said "this set
         is not attached to a recording" under the name of the
         recording. */
      const can = c.readable !== false;
      const why = !good
        ? 'Every candidate here was rejected or left undecided, so there '
          + 'are no dentate spikes to classify.'
        : !can ? ('This set cannot be read here: ' + (c.why_not || 'the '
                  + 'recording could not be found') + '.')
        : '';
      const pickable = good && can;
      list.appendChild(el('label', {
        class: 'bm-row' + (c.id === q.entry ? ' on' : '')
               + (pickable ? '' : ' off'),
        title: why,
      }, [
        el('input', {
          type: 'radio', name: 'dpEntry',
          disabled: pickable ? null : 'disabled',
          checked: c.id === q.entry ? 'checked' : null,
          onchange: () => pickSet(c.id),
        }),
        el('span', { class: 'mk-name', text: c.name || c.id }),
        el('span', { class: 'flagchip', text: good
          ? good + ' spike' + (good === 1 ? '' : 's') + ' of ' + c.n
          : c.n + ' stamps, none of them spikes' }),
        !can ? el('span', { class: 'flagchip warn',
                            text: 'cannot be read here' }) : null,
        el('span', { class: 'person-what', text: !can
          ? (c.why_not || '')
          : c.newest_aligned_name ? 'v' + c.newest_aligned_name + '  aligned'
          : c.newest_usable_name ? 'v' + c.newest_usable_name
          : 'not through Braces' }),
      ].filter(Boolean)));
    }
    box.appendChild(list);

    /* And which version of it to read the stamps from.

       Radios rather than a second dropdown: a version is a decision with
       somebody's name on it, and the count and whether it has been
       aligned are the whole of how anybody chooses between two. A version
       whose snapshot never reached this machine is shown and disabled
       with the reason on the row -- it has a name, a count and no times,
       and leaving it out would read as it not existing. */
    const vers = ((plan && plan.ok && plan.versions) || []);
    if (vers.length) {
      box.appendChild(el('div', { class: 'section-label',
                                  text: 'Read the stamps from' }));
      const vlist = el('div', { class: 'bm-list dp-vers' });
      /* "As they are now" is a real choice and needs a row.

         `from_version` null means the server reads `rec["events"]` --
         the set as it currently stands, which is what a set nobody has
         banked a version of has and what the plan falls back to when the
         version asked for is not here. With no row for it, that state
         left every radio unchecked: the list looked like a set with no
         version rather than a set being read at its newest. */
      const nowOn = q.from_version == null;
      vlist.appendChild(el('label', {
        class: 'bm-row' + (nowOn ? ' on' : ''),
        title: 'The stamps as this set currently stands, rather than a '
             + 'banked version of it.',
      }, [
        el('input', {
          type: 'radio', name: 'dpVer', checked: nowOn ? 'checked' : null,
          onchange: () => {
            q.from_version = null;
            q.read = null;
            fit = null;
            refreshPlan();
          },
        }),
        el('span', { class: 'mk-name', text: 'as they are now' }),
        el('span', { class: 'flagchip', text: (plan.stamps || {}).of != null
          ? (plan.stamps.of + ' stamps') : '' }),
        el('span', { class: 'person-what', text: 'not a banked version' }),
      ]));
      for (const v of vers) {
        const on = String(v.ref) === String(q.from_version)
                   || String(v.name) === String(q.from_version);
        vlist.appendChild(el('label', {
          class: 'bm-row' + (on ? ' on' : '') + (v.usable ? '' : ' off'),
          title: v.usable ? (v.note || '') : (v.why_not || ''),
        }, [
          el('input', {
            type: 'radio', name: 'dpVer',
            disabled: v.usable ? null : 'disabled',
            checked: on ? 'checked' : null,
            onchange: () => {
              q.from_version = v.ref;
              q.read = null;
              fit = null;
              refreshPlan();
            },
          }),
          el('span', { class: 'mk-name', text: 'v' + v.name }),
          el('span', { class: 'flagchip', text: v.n + ' stamps' }),
          el('span', { class: 'person-what', text:
            (v.aligned ? 'aligned' : 'not aligned')
            + (v.by ? '  ' + v.by : '')
            + (v.usable ? '' : '  ' + (v.why_not || 'not readable here')) }),
        ]));
      }
      box.appendChild(vlist);
    }

    const cur = setOf();
    const tail = [
      plan && plan.ok && plan.version_note
        ? el('p', { class: 'hint dp-warn', text:
            plan.version_note + ' Reading the events as they are now \u2014 '
            + 'pick a version above if you wanted a different one.' })
        : null,
      cur && !cur.newest_aligned_name
        ? el('p', { class: 'hint dp-warn', text:
            'Nothing in this set has been through Braces. Every feature '
            + 'here is read at one instant relative to the stamp, so stamps '
            + 'that are a few milliseconds out do not classify badly \u2014 '
            + 'they classify a smear. Step 3 first is worth the minutes.' })
        : null,
      plan && !plan.ok
        ? el('p', { class: 'hint err', text: plan.error })
        : planLine(),
    ].filter(Boolean);
    for (const t of tail) box.appendChild(t);
    return box;
  }

  function planLine() {
    if (!plan || !plan.ok) return null;
    const pr = plan.probe || {};
    const st = plan.stamps || {};
    const rd = plan.read || {};
    const bits = [
      st.n + ' of ' + st.of + ' curated as spikes',
      plan.session.n_channels + ' contacts',
      rd.n_windows + ' window' + (rd.n_windows === 1 ? '' : 's') + ' to read',
      'refine ' + rd.refine,
    ];
    return el('div', { class: 'dp-plan' }, [
      el('div', { class: 'hint', text: bits.join('  ·  ') }),
      probeLine(pr),
    ]);
  }

  /* The probe, and how sure anybody is of it.

     Said out loud because "H3" and "nobody has told us" are different
     things and only one of them is safe to run a CSD on. An H10-D read as a
     linear array is a second difference between contacts that are not
     neighbours, and the number that comes out is not a small error. */
  function probeLine(pr) {
    if (!pr || !pr.id) return null;
    const known = pr.state === 'confirmed';
    return el('div', { class: 'dp-probe' + (known ? '' : ' unsure') }, [
      el('strong', { text: pr.short || pr.id }),
      el('span', { text: ' · ' + pr.pitch_um + ' µm between contacts' }),
      pr.runs && pr.runs.length > 1
        ? el('span', { text: ' · ' + pr.runs.length + ' columns, and a CSD '
                             + 'runs down one of them at a time' })
        : null,
      known ? null : el('span', { class: 'dp-unsure',
                                  text: ' · ' + (pr.why || 'unconfirmed') }),
    ].filter(Boolean));
  }

  function readCard() {
    if (!plan || !plan.ok) return el('div', {});
    const rd = plan.read || {};
    return el('div', { class: 'card dp-read' }, [
      el('p', { class: 'hint', text:
        'Reading takes a window around every stamp on every contact, at '
        + 'three filterings, so the notch and the box can be changed '
        + 'afterwards without touching the disk again. It is cached against '
        + 'the read settings, so this is once.' }),
      el('div', { class: 'dp-row' }, [
        el('button', { class: 'btn', text: 'Read ' + (plan.stamps.n)
                       + ' spikes', onclick: () => startRead(false) }),
        rd.cached ? el('button', {
          class: 'btn', text: 'Read again',
          onclick: () => startRead(true) }) : null,
      ].filter(Boolean)),
    ]);
  }

  function progress() {
    const st = (job && job.stages && job.stages[0]) || {};
    const frac = st.of ? Math.min(1, (st.done || 0) / st.of) : 0;
    return el('div', { class: 'card dp-job' }, [
      el('div', { class: 'hint', text:
        'Reading — ' + (st.done || 0) + ' of ' + (st.of || '?') + ' '
        + (st.unit || 'windows')
        + (job && job.eta_s ? '  ·  about ' + Math.ceil(job.eta_s)
                              + ' s left' : '') }),
      el('div', { class: 'dp-bar' }, [
        el('i', { style: 'width:' + (100 * frac).toFixed(1) + '%' })]),
      el('button', { class: 'btn', text: 'Stop', onclick: async () => {
        try { await apiPost('/api/cfc/job/' + job.id + '/cancel', {}); }
        catch (e) { /* it may already be done */ }
      } }),
    ]);
  }

  /* ---------- 3. the workbench ---------- */
  /* THE PICTURES GET THE SCREEN.

     Three equal columns gave each graph a third of the width and left the
     bottom two thirds of the middle one empty -- on a wide monitor the
     rasters were letterboxes and the controls had a column to themselves
     they did not need. So: the graphs across the top at full height, and
     everything you set along the bottom, with the PCA beside it.

     The scatter belongs down there rather than with the other pictures
     because it is the only one without a depth axis -- it does not line up
     with them, it is not something a guide crosses, and it is what you look
     at after the box is right rather than while setting it. */
  function workbench() {
    return el('div', {}, [
      busyLine(),
      statusStrip(),
      el('div', { class: 'dp-top' }, [
        el('div', { class: 'dp-col dp-panes' }, panes()),
        el('div', { class: 'dp-col dp-answer' }, answer()),
      ]),
      el('div', { class: 'dp-bottom' }, [
        el('div', { class: 'dp-col dp-controls' }, controls()),
        el('div', { class: 'dp-col dp-pca' }, pcaPane()),
      ]),
    ]);
  }

  /* What the panel is doing, while it is doing it.

     A fit over seven hundred spikes is about a second of server: the
     feature matrix, the PCA, the k-means and then the mean CSD of every
     class over every event in the set. A second of nothing reads as a
     hang, and the thing that fixes that is not a spinner but naming the
     stage -- "fitting 712 spikes" is a wait somebody understands.

     It is in the tree even when there is nothing to say, so that it can be
     swapped in place. Rebuilding the panel to show that it is busy would
     be the most expensive way possible to say so, and it would take the
     activity feed with it. */
  const PIC_WORDS = {
    traces: 'Drawing the voltage traces',
    pane: 'Drawing the CSD',
    classes: 'Averaging the CSD of each class',
    features: 'Laying out the feature matrix',
  };

  function busyLine() {
    const n = (plan && plan.ok && plan.stamps && plan.stamps.n) || null;
    const what = fitting
      /* THE SIZE OF THE JOB, and what is actually in it.

         All three methods are fitted every time, which is the honest
         thing to say while somebody waits: two PCAs, three k-means and
         the class means over every event in the set. Not a stepLoader --
         the constitution is explicit that naming stages which do not
         each take real time is a progress bar lying about where the time
         goes, and this is one request that either has returned or has
         not. One loader, and the size said. */
      ? ('Fitting' + (n ? ' ' + n + ' spikes' : '')
         + ' — all three methods, then the class means')
      : (drawingWhat ? (PIC_WORDS[drawingWhat] || 'Drawing') : null);
    if (!what) return el('div', { class: 'dp-busy' });
    return el('div', { class: 'dp-busy on' }, [
      loader(what),
    ]);
  }

  function tickBusy() {
    swap('.dp-busy', busyLine());
  }

  /* A box that has moved, and nothing recomputed yet.

     Dragging used to refit on every release, and a fit is a second: a few
     adjustments to get the window right meant a few seconds of the whole
     panel being rebuilt under the pointer, three requests each time. The
     drag now sets the box and says so; the answer is recomputed when it is
     asked for.

     Only the drag. `1 sample`, `auto depth`, the rule, the class count and
     the two checkboxes are single deliberate clicks that each mean one
     fit, and making those wait for a second click would be ceremony. */
  function applyBar() {
    if (!dirty) return el('span', { class: 'dp-applybar' });
    const b = shownBox() || {};
    return el('span', { class: 'dp-applybar on' }, [
      el('span', { class: 'hint dp-moved', text:
        'box moved to CSC' + b.lo + '–' + b.hi + ', '
        + fmtMs(b.t_lo_ms) + ' to ' + fmtMs(b.t_hi_ms) }),
      el('button', { class: 'btn ghost sm', text: 'put it back',
                     disabled: fitting || null, onclick: revertBox }),
      el('button', { class: 'btn ghost sm', text: 'Recompute & compare',
                     disabled: fitting || null,
                     title: 'Keep the answer on screen, compute the new '
                          + 'one, and show which events changed identity '
                          + 'between them.',
                     onclick: () => refitCompare() }),
      el('button', { class: 'btn sm', text:
                     fitting ? 'Recomputing…' : 'Recompute  ↵',
                     disabled: fitting || null,
                     title: 'The answer below is still the previous box’s. '
                          + 'Or press Enter.',
                     onclick: () => refit() }),
    ]);
  }

  /* ==================================================================
     Recompute, and compare

     A fit is a question with eight parts -- the box, the class count, the
     rule, the features, the notch, the flip -- and changing one of them
     replaces the answer with no record of what it replaced. So the
     honest question, "did moving the band actually change anything, or
     did it just move the picture", could only be answered by
     remembering. People were screenshotting the panel before dragging.

     This keeps the answer that is on screen, computes the new one, and
     puts them side by side with the thing neither picture shows on its
     own: WHICH EVENTS CHANGED IDENTITY. Both fits are over the same read
     and the same list of events, so `events[i].type` before against
     after is an exact crosstab rather than an estimate -- and the count
     off its diagonal is the answer to the question.

     One caution it states rather than hides: a class NUMBER is not a
     class. Classes are renumbered by depth on every fit, so DS1 before
     and DS1 after are both "the shallower one" and need not contain the
     same events at all. That is exactly what the crosstab is for. */
  let compare = null;

  async function refitCompare() {
    if (!fit || !fit.ok || fitting) return;
    /* Cleared first. A comparison left over from last time is a pair of
       answers to a question nobody is asking, and anything reading
       `compare` while this one is still computing would get it. */
    compare = null;
    /* THE OLD QUESTION IS THE ONE THE OLD ANSWER ANSWERED, and that is
       not what `q` holds.

       A dragged box sits in `q` waiting to be recomputed -- that is the
       whole point of the apply bar -- so by the time this runs, `q`
       already describes the NEW question. Snapshotting it gave a
       "before" whose box was the after's, so the settings diff showed no
       box change at all and "put the old answer back" put the new box
       back. The fit carries the box it was computed from; everything
       else in `q` refits as it is changed and so already agrees with
       it. */
    const f0 = fit;
    const before = {
      fit: f0,
      q: Object.assign({}, q, {
        sel_lo: f0.box.lo, sel_hi: f0.box.hi,
        t_lo_ms: f0.box.t_lo_ms, t_hi_ms: f0.box.t_hi_ms,
      }),
      pics: Object.assign({}, pics),
    };
    await refit.now ? refit.now() : refit();
    /* `refit` is debounced, so it has not necessarily run yet. Waited for
       rather than slept through: a fit is milliseconds on a small set and
       about a second on seven hundred events. */
    const until = Date.now() + 30000;
    while (Date.now() < until) {
      if (!fitting && fit && fit !== f0) break;
      await new Promise((r) => setTimeout(r, 60));
    }
    if (!fit || !fit.ok || fit === f0) {
      toast('Nothing to compare: the new fit did not arrive.', 'warn', 7000);
      return;
    }
    compare = { before, after: { fit, q: Object.assign({}, q) } };
    // The pictures for the new answer, so both sides are drawn from the
    // server rather than one of them being redrawn from memory.
    await pictures(['classes', 'features']);
    compare.after.pics = Object.assign({}, pics);
    showCompare();
    BARRY.activity.log('dspca.compare', {
      gid: q.gid, moved: crosstab(compare).moved,
    });
  }

  /* The crosstab, and the one number that summarises it. */
  function crosstab(cmp) {
    const a = (cmp.before.fit.events || []);
    const b = (cmp.after.fit.events || []);
    const byI = new Map();
    for (const e of b) byI.set(e.i, e.type);
    const ka = cmp.before.fit.k, kb = cmp.after.fit.k;
    const cells = [];
    for (let i = 0; i <= ka; i++) cells.push(new Array(kb + 1).fill(0));
    let moved = 0, seen = 0;
    for (const e of a) {
      const to = byI.get(e.i);
      if (to == null) continue;
      seen += 1;
      cells[e.type][to] += 1;
      if (e.type !== to) moved += 1;
    }
    return { cells, ka, kb, moved, seen };
  }

  /* What actually differs between the two questions. Listing every
     setting would bury the one that changed. */
  const Q_WORDS = [
    ['sel_lo', 'depth from'], ['sel_hi', 'depth to'],
    ['t_lo_ms', 'time from'], ['t_hi_ms', 'time to'],
    ['nclasses', 'classes'], ['rule', 'rule'],
    ['features', 'features'], ['notch', '60 Hz notch'],
    ['flip', 'flipped'], ['screen', 'CSD screen'],
  ];

  function settingsDiff(cmp) {
    const out = [];
    for (const [key, word] of Q_WORDS) {
      const was = cmp.before.q[key], now = cmp.after.q[key];
      if (String(was) === String(now)) continue;
      out.push({ word, was, now });
    }
    return out;
  }

  function showCompare() {
    const cmp = compare;
    if (!cmp) return;
    const ct = crosstab(cmp);
    const diff = settingsDiff(cmp);
    const wrap = el('div', { class: 'modal big dp-cmp' });

    wrap.appendChild(el('div', { class: 'mh' }, [
      el('h3', { text: 'Before and after' }),
      el('span', { class: 'sub', text: diff.length
        ? diff.map((d) => d.word + ': ' + fmtVal(d.was) + ' \u2192 '
                          + fmtVal(d.now)).join('   \u00b7   ')
        : 'Nothing about the question changed, so any difference below is '
          + 'the K-means seed and not your edit.' }),
      el('span', { class: 'spacer' }),
      el('button', { class: 'btn ghost sm', text: 'Close',
                     onclick: closeModal }),
    ]));

    /* `mb` IS THE SCROLLING ELEMENT, and leaving it off is why this
       dialog had no scrollbar and lost its bottom half.

       `.modal.big` is a flex column of header, body and footer, and
       `.modal.big > *` gives every child `flex: 1; overflow: hidden`.
       The body is only rescued from that by `.mb`, which is where the
       `overflow-y: auto` and the padding live. Without it the body was
       a clipped box: the feature matrices were cut off mid-panel, the
       profiles below them were not reachable at all, and there was
       nothing to scroll. */
    const body = el('div', { class: 'mb dp-cmp-body' });

    /* THE HEADLINE. Not the pictures -- two heatmaps that look slightly
       different is exactly the evidence this panel exists to replace. */
    body.appendChild(el('div', { class: 'section-label',
                                 text: 'Which events changed identity' }));
    body.appendChild(el('p', { class: 'hint', text:
      ct.moved + ' of ' + ct.seen + ' events ('
      + (100 * ct.moved / Math.max(1, ct.seen)).toFixed(1)
      + '%) are in a different class than before. A class NUMBER is not a '
      + 'class: they are renumbered by depth on every fit, so DS1 means '
      + '\u201cthe shallower one\u201d both times and need not hold the '
      + 'same events.' }));

    const head = [el('th', { text: 'before \u2193  after \u2192' })];
    for (let j = 1; j <= ct.kb; j++) {
      head.push(el('th', {}, [
        el('i', { class: 'dp-swatch', style: 'background:' + colorOf(j) }),
        el('span', { text: ' DS' + j }),
      ]));
    }
    const rows = [];
    for (let i = 1; i <= ct.ka; i++) {
      const tds = [el('th', {}, [
        el('i', { class: 'dp-swatch', style: 'background:' + colorOf(i) }),
        el('span', { text: ' DS' + i }),
      ])];
      for (let j = 1; j <= ct.kb; j++) {
        const n = ct.cells[i][j];
        tds.push(el('td', {
          class: 'dp-cmp-n' + (i === j ? ' same' : (n ? ' moved' : '')),
          text: n ? String(n) : '\u00b7',
        }));
      }
      rows.push(el('tr', {}, tds));
    }
    body.appendChild(el('table', { class: 'tbl dp-cmp-tab' }, [
      el('thead', {}, [el('tr', {}, head)]),
      el('tbody', {}, rows),
    ]));

    /* And then the pictures, the same ones the panel draws, in the same
       order, so the eye can go from the number to the thing it is about. */
    body.appendChild(sideBySide('Mean CSD per class', cmp, 'classes'));
    body.appendChild(sideBySide('The features, every event', cmp, 'features'));
    body.appendChild(profilesSide(cmp));

    wrap.appendChild(body);
    wrap.appendChild(el('div', { class: 'mf' }, [
      el('span', { class: 'hint', text: ct.moved
        ? ct.moved + ' of ' + ct.seen + ' events moved class'
        : 'No event changed class' }),
      el('span', { class: 'spacer' }),
      el('button', { class: 'btn ghost sm', text: 'Put the old answer back',
                     onclick: () => { revertCompare(); closeModal(); } }),
      el('button', { class: 'btn sm', text: 'Keep the new one',
                     onclick: closeModal }),
    ]));
    showModal(wrap, { replace: true });
  }

  function fmtVal(v) {
    if (v === true) return 'on';
    if (v === false) return 'off';
    if (v == null) return 'auto';
    return String(v);
  }

  /* The old question, put back. The comparison is only useful if the
     answer it showed you is one you can return to. */
  function revertCompare() {
    if (!compare) return;
    Object.assign(q, compare.before.q);
    dirty = false;
    refit();
  }

  /* One picture, twice. Server-rendered images either side, which is why
     this is a few lines rather than a second copy of every draw routine:
     both sides are the same picture from the same encoder. */
  function sideBySide(title, cmp, kind) {
    const box = el('div', { class: 'dp-cmp-pair' });
    box.appendChild(el('div', { class: 'section-label', text: title }));
    const row = el('div', { class: 'dp-cmp-row' });
    for (const [label, side] of [['before', cmp.before], ['after', cmp.after]]) {
      const cell = el('div', { class: 'dp-cmp-cell' });
      cell.appendChild(el('span', { class: 'dp-cmp-lab', text: label }));
      const pic = (side.pics || {})[kind];
      if (!pic || !pic.ok) {
        cell.appendChild(el('p', { class: 'hint', text:
          'Not drawn for this one.' }));
      } else if (kind === 'features') {
        cell.appendChild(el('img', { class: 'dp-cmp-img', src: pic.image,
                                     alt: title + ', ' + label }));
        cell.appendChild(el('span', { class: 'hint', text:
          pic.mode_name + '  \u00b7  ' + pic.n_events + ' events' }));
      } else {
        const strip = el('div', { class: 'dp-cmp-strip' });
        for (const c of (pic.classes || [])) {
          if (!c.image) continue;
          strip.appendChild(el('div', { class: 'dp-cmp-cls' }, [
            el('img', { class: 'dp-cmp-img', src: c.image,
                        alt: 'DS' + c.c }),
            el('span', { class: 'hint', style: 'color:' + colorOf(c.c),
                         text: 'DS' + c.c + '  n=' + c.n
                               + (c.peak != null
                                  ? '  \u00b1' + fmtPeak(c.peak) : '') }),
          ]));
        }
        cell.appendChild(strip);
      }
      row.appendChild(cell);
    }
    box.appendChild(row);
    return box;
  }

  /* The depth profiles, drawn rather than fetched -- they are the one
     panel the server does not render as an image, and the landmark each
     rule chose is the whole point of showing them here. */
  function profilesSide(cmp) {
    const box = el('div', { class: 'dp-cmp-pair' });
    box.appendChild(el('div', { class: 'section-label', text:
      'Class-average depth profile, and the landmark each rule chose' }));
    const row = el('div', { class: 'dp-cmp-row' });
    for (const [label, side] of [['before', cmp.before], ['after', cmp.after]]) {
      const cell = el('div', { class: 'dp-cmp-cell' });
      cell.appendChild(el('span', { class: 'dp-cmp-lab', text: label }));
      const list = el('div', { class: 'dp-cmp-decide' });
      for (const d of (side.fit.decide || [])) {
        if (!d.n) continue;
        list.appendChild(el('div', { class: 'dp-cmp-drow' }, [
          el('i', { class: 'dp-swatch', style: 'background:' + colorOf(d.c) }),
          el('strong', { text: 'DS' + d.c }),
          el('span', { class: 'hint', text: 'n=' + d.n }),
          el('span', { class: 'hint', text: d.csc != null
            ? 'landmark CSC' + d.csc : 'no landmark' }),
        ]));
      }
      cell.appendChild(list);
      cell.appendChild(el('span', { class: 'hint', text:
        (side.fit.box ? ('CSC' + side.fit.box.lo + '\u2013'
                         + side.fit.box.hi + '  \u00b7  ')
                      : '')
        + (side.fit.n_features || '?') + ' features  \u00b7  PC1 '
        + pct((side.fit.explained || [])[0]) }));
      row.appendChild(cell);
    }
    box.appendChild(row);
    return box;
  }

  /* Back to the box the answer on screen was computed from. */
  function revertBox() {
    const b = (fit && fit.ok && fit.box) || null;
    if (b) {
      q.sel_lo = b.lo; q.sel_hi = b.hi;
      q.t_lo_ms = b.t_lo_ms; q.t_hi_ms = b.t_hi_ms;
    }
    dirty = false;
    render();
  }

  /* The whole question, on one line, over the columns that set it.

     Every part of this is settable in the column on the left, and reading it
     back off those controls means reconstructing the question from its
     parts. This is the question -- and it is what somebody screenshotting
     the panel needs to be in the picture. */
  function statusStrip() {
    if (!fit || !fit.ok) return el('div', {});
    const b = fit.box;
    const bits = [
      'CSC' + b.lo + '\u2013' + b.hi,
      fmtMs(b.t_lo_ms) + ' to ' + fmtMs(b.t_hi_ms),
      b.n_contacts + ' \u00d7 ' + b.n_samples + ' = ' + fit.n_features
        + ' features',
      fit.k + ' classes',
      RULE_NAME[q.rule] || q.rule,
      q.notch ? '60 Hz out' : 'broadband (Toothy)',
    ];
    return el('div', { class: 'dp-strip' }, [
      el('span', { class: 'dp-strip-n',
                   text: (plan && plan.ok ? plan.entry.session_label : '') }),
    ].concat(
      bits.map((t) => el('span', { class: 'dp-strip-b', text: t })),
      [el('div', { style: 'flex:1' })],
      (fit.profiles || []).filter((x) => x.n).map((x) =>
        el('span', { class: 'dp-tag' }, [
          el('i', { style: 'background:' + colorOf(x.c) }),
          el('span', { text: 'DS' + x.c + ' ' + x.n }),
        ]))));
  }

  /* The controls, in the order somebody works through them: where the
     features come from, how many kinds to look for, which kind is DS1, and
     then the two things that are written down.

     Every control carries its own `title`. The panel used to explain itself
     in a paragraph at the top and in a sentence under each rule, which is
     documentation -- and documentation in a 230px column is most of the
     column. What is on screen is the question; the reasons are one hover
     away. */
  function controls() {
    const b = shownBox() || {};
    const out = [];


    /* THE ORDER THE QUESTION IS ACTUALLY ASKED IN.

       How to split them FIRST, because it decides which of the settings
       below mean anything. `delta` has no feature vector to normalise, so
       "what the PCA sees" is not a choice it has -- offering `sign +-1`
       beside a method with no PCA in it is offering a setting that does
       nothing, and a control that does nothing is worse than no control.
       The gap settings are the mirror of that and already conditional.

       Which one is DS1 comes LAST because it is not part of computing the
       split at all: it names the two groups once they exist, and it is
       the only thing here that can be changed without recomputing what
       the groups ARE.

       The box, the class count and the notch apply to all three and sit
       between them. */

    /* WHICH SPLIT, and the two numbers the sink gap is shaped by.

       First, because it decides what every panel below is showing. The
       other two are computed beside whichever is chosen, so switching is
       free and the comparison is always one click away. */
    out.push(label('How to split them'));
    out.push(el('div', { class: 'dp-rules' }, METHODS.map(([id, nm, why]) =>
      el('label', {
        class: 'dp-rule' + (q.method === id ? ' on' : ''), title: why,
      }, [
        el('input', { type: 'radio', name: 'dpMethod',
                      checked: q.method === id || null,
                      onchange: () => { q.method = id; refit(); } }),
        el('strong', { text: nm }),
        q.method === id ? el('span', { class: 'dp-why', text: why }) : null,
      ].filter(Boolean)))));
    out.push(methodAgree());

    /* The two numbers the gap is made of. Both matter and both have a
       defensible default, so they are shown rather than buried. */
    if (q.method !== 'pca') {
      out.push(label('The sink gap'));
      out.push(el('div', { class: 'dp-row' }, [
        el('label', { class: 'dp-lab2', text: 'two sinks at least' }),
        el('input', {
          type: 'number', class: 'dp-gnum', min: '1', max: '40',
          value: String(q.min_sep),
          title: 'Two dips closer than this are one sink seen twice '
               + 'through a spatial filter, not two laminar sinks. A '
               + '3-point taper plus a second difference will routinely '
               + 'split one trough into a pair. Contacts are 30 um, so 5 '
               + 'is 150 um \u2014 under the OML-to-MML spacing and over '
               + 'anything the smoothing can manufacture.',
          onchange: (e) => {
            q.min_sep = Math.max(1, parseInt(e.target.value, 10) || 5);
            refit();
          },
        }),
        el('span', { class: 'hint', text: 'contacts apart' }),
      ]));
    }
    if (q.method === 'delta') {
      /* A HAND-PLACED THRESHOLD BEATS A FITTED ONE when you can see the
         axis. k-means minimises within-cluster variance, which on a
         lopsided one-dimensional spread puts the boundary where the
         arithmetic wants it rather than where the gap in the data is.
         Here the axis has units and every event is on it. */
      const dv = (fit && fit.ok && (fit.variants || {}).delta) || {};
      out.push(el('div', { class: 'dp-row' }, [
        el('span', { class: 'hint', text: dv.manual
          ? 'cut placed by hand'
          : 'cut fitted by k-means' }),
        el('span', { class: 'flagchip', text:
          (dv.bounds || []).map((b2) => b2.toFixed(3)).join(', ')
          || 'none' }),
        dv.manual ? el('button', {
          class: 'btn ghost sm', text: 'back to k-means',
          title: 'Let k-means place the boundary again.',
          onclick: () => { q.delta_cut = null; refit(); },
        }) : null,
      ].filter(Boolean)));
      out.push(el('p', { class: 'hint', text:
        'Click the sink-gap panel to move the cut; right-click it to '
        + 'hand it back to k-means.' }));
    }
    if (q.method === 'pca_gap') {
      out.push(el('div', { class: 'dp-row' }, [
        el('label', { class: 'dp-lab2', text: 'gap column \u00d7' }),
        el('input', {
          type: 'number', class: 'dp-gnum', min: '0', step: '1',
          value: String(q.gap_weight),
          title: 'One column against sixteen is about 3% of the feature '
               + 'variance, which is why at 1 it shifts every event and '
               + 'moves none across a boundary. Turn it up deliberately: '
               + 'the first version of this feature was effectively 9 and '
               + 'took PC1\u2019s correlation with loudness from 0.52 to '
               + '0.75.',
          onchange: (e) => {
            q.gap_weight = Math.max(0, parseFloat(e.target.value) || 0);
            refit();
          },
        }),
        el('span', { class: 'hint', text: 'one column among many at 1' }),
      ]));
    }

    /* Only where there is a PCA to feed it. */
    if (q.method !== 'delta') {
      /* WHAT THE PCA IS ALLOWED TO SEE.

         Min-max is Toothy, and it removes SCALE exactly -- in principle. In
         practice the scale is set by two samples, the single min and the
         single max, so a quiet event riding the same background noise
         normalizes to a NOISIER shape, and that is an amplitude effect that
         survives the normalization. Measured on M2ctls3jan23: under min-max
         the two classes differ in amplitude by 3.07x and PC1 correlates
         0.52 with log amplitude. The clusters were substantially loud
         against quiet.

         The other two throw the magnitudes away and keep the laminar
         pattern; on the same recording sign drops that ratio to 1.12x.
         Read the answer with the amplitude question in mind: if the classes
         stop separating once the magnitudes go, they were separating on
         magnitude. */
      out.push(label('What the PCA sees'));
      out.push(el('div', { class: 'dp-rules' }, FEATURES.map(([id, nm, why]) =>
        el('label', {
          class: 'dp-rule' + (q.features === id ? ' on' : ''), title: why,
        }, [
          el('input', { type: 'radio', name: 'dpFeat',
                        checked: q.features === id || null,
                        onchange: () => { q.features = id; refit(); } }),
          el('strong', { text: nm }),
          q.features === id ? el('span', { class: 'dp-why', text: why }) : null,
        ].filter(Boolean)))));

    }
    // The box reads off the strip above the columns; here are only the two
    // ways of setting it that a drag cannot express.
    /* EVERY CONTACT IN THE BOX, and whether the analysis is using it.

       The recording's own bad channels come from the shared record and
       arrive already ticked off -- the same list Braces and the ToolKit
       read, so unticking a wire here does not mean something different
       from unticking it there. Anything taken out on top of that is
       this panel's, and says so.

       REPAIRED, NOT DROPPED. A CSD is a second difference over depth: a
       contact taken out of the middle leaves the rest unevenly spaced,
       and a second difference over an uneven grid is not a CSD. So a
       contact that is out is interpolated from its neighbours, which is
       what the line under the class means has always said. */
    if (fit && fit.ok && (fit.channels || []).length) {
      out.push(label('Contacts in the box'));
      out.push(el('div', { class: 'dp-chans' }, fit.channels.map((c) => {
        const out_ = c.bad || c.by_hand;
        return el('label', {
          class: 'dp-chan' + (out_ ? ' off' : '')
                 + (c.by_hand ? ' hand' : ''),
          title: c.by_hand ? 'Taken out here. Click to put it back.'
               : c.bad ? ('Out: ' + (c.why || 'marked bad on this '
                          + 'recording') + '. Repaired from its '
                          + 'neighbours.')
               : 'In use. Click to take it out and repair it from its '
                 + 'neighbours.',
        }, [
          el('input', {
            type: 'checkbox', checked: out_ ? null : 'checked',
            onchange: () => {
              const have = new Set(q.manual_bad || []);
              if (have.has(c.number)) have.delete(c.number);
              else have.add(c.number);
              q.manual_bad = Array.from(have).sort((a2, b2) => a2 - b2);
              refit();
            },
          }),
          el('span', { text: 'CSC' + c.number }),
        ]);
      })));
      const nOut = fit.channels.filter((c) => c.bad || c.by_hand).length;
      out.push(el('p', { class: 'hint', text: nOut
        ? nOut + ' of ' + fit.channels.length + ' repaired from their '
          + 'neighbours, not dropped \u2014 a CSD needs an even grid.'
        : 'All ' + fit.channels.length + ' in use.' }));
    }

    out.push(label('The box', true));
    out.push(el('div', { class: 'dp-row' }, [
      el('button', { class: 'btn ghost sm', text: '1 sample', title:
        'Toothy’s own feature window: one instant at the stamp. '
        + 'Pulled here, this panel is Toothy exactly.',
        onclick: () => { q.t_lo_ms = 0; q.t_hi_ms = 0; refit(); } }),
      el('button', { class: 'btn ghost sm', text: 'auto depth', title:
        'The contiguous run of contacts holding most of the '
        + 'event-triggered template.',
        onclick: () => { q.sel_lo = null; q.sel_hi = null; refit(); } }),
    ]));

    /* Which column of the probe, where there is more than one.

       A contact-number range is not a column on an interleaved probe, so
       this is a picker rather than a hint: an H10-D's CSC1, 2 and 3 are
       three different columns, and a CSD down them is a second difference
       between contacts that are not neighbours. */
    const runs = ((plan && plan.ok && plan.probe && plan.probe.runs) || []);
    if (runs.length > 1) {
      out.push(label('Column'));
      out.push(el('select', {
        onchange: (e) => {
          const r = runs[+e.target.value];
          if (!r) return;
          q.sel_lo = r.lo; q.sel_hi = r.hi; refit();
        },
      }, runs.map((r, i) => el('option', {
        value: i,
        selected: (b.lo >= r.lo && b.hi <= r.hi) || null,
        text: r.label + '  (CSC' + r.lo + '–' + r.hi + ')',
      }))));
    }

    out.push(label('Classes'));
    out.push(el('div', { class: 'dp-row' }, [
      /* The number follows the thumb; the FIT waits for it to be let go.
         `refit` ends in a `render`, and a render replaces this slider --
         under the pointer dragging it, which drops the drag on the first
         intermediate value. It also makes 2 -> 5 one fit rather than
         four. */
      el('input', {
        type: 'range', min: 2, max: 5, step: 1, value: q.nclasses,
        class: 'dp-slider',
        oninput: (e) => {
          const n = $('#dpK');
          if (n) n.textContent = e.target.value;
        },
        onchange: (e) => { q.nclasses = +e.target.value; refit(); },
      }),
      el('span', { id: 'dpK', class: 'dp-val', text: String(q.nclasses) }),
    ]));

    out.push(label('The features'));
    out.push(el('div', { class: 'dp-checks' }, [
      el('label', { class: 'dp-check', title:
        'Toothy leaves the mains in its features and measures nothing about '
        + 'it. The picture is notched either way.' }, [
        el('input', { type: 'checkbox', checked: q.notch || null,
                      onchange: (e) => { q.notch = e.target.checked;
                                         refit(); } }),
        el('span', { text: '60 Hz notch' }),
      ]),
      /* The line over the raster. A view setting and not a question, so
         it does not refit -- it redraws. */
      el('label', { class: 'dp-check', title:
        'The CSD averaged across the feature window, drawn down the '
        + 'raster. The two sinks the gap was measured between are '
        + 'bracketed on it, and every other candidate sink is ticked.' }, [
        el('input', { type: 'checkbox', checked: q.depth_line || null,
                      onchange: (e) => { q.depth_line = e.target.checked;
                                         render(); } }),
        el('span', { text: 'depth profile on the raster' }),
      ]),
      /* The CSD screen is gone from here.

         It was a checkbox for a heuristic that looks for contacts a
         CSD cannot be run down, repairs them, and goes round again up
         to five times. Off by default, and on a probe worth analysing
         it finds nothing -- so what it looked like from the panel was
         a control that did nothing at all, which is worse than not
         having one. The screen itself is still in backend/dspca.py
         and still reachable as `screen` on the API for a probe that
         needs it; it is not a decision to put in front of somebody
         mid-analysis. */
    ]));
    out.push(label('Which one is DS1'));
    out.push(el('div', { class: 'dp-rules' }, RULES.map(([id, name, why]) =>
      el('label', {
        class: 'dp-rule' + (q.rule === id ? ' on' : ''), title: why,
      }, [
        el('input', { type: 'radio', name: 'dpRule',
                      checked: q.rule === id || null,
                      onchange: () => { q.rule = id; refit(); } }),
        el('strong', { text: name }),
        // Only the rule in force explains itself. The other three carry the
        // same sentence as a tooltip, which is where the explanation of a
        // thing you have not chosen belongs.
        q.rule === id ? el('span', { class: 'dp-why', text: why }) : null,
      ].filter(Boolean)))));
    if (q.rule === 'anatomy' && fit && fit.ok
        && !Object.keys(fit.layers || {}).length) {
      out.push(el('p', { class: 'hint dp-warn', text:
        'Nobody has labelled this recording’s layers, so there is no '
        + 'hilus to measure against and the tortlab rule is in use '
        + 'instead. StrataScope is where they are set.' }));
    }
    out.push(el('button', {
      class: 'btn' + (q.flip ? '' : ' ghost') + ' sm',
      text: q.flip ? 'flipped by hand' : 'flip DS1/DS2',
      title: 'The last word on the labels is anatomy’s.',
      onclick: () => { q.flip = !q.flip; refit(); },
    }));

    out.push(mainsLine());

    out.push(label('Guides'));
    out.push(guideList());

    out.push(el('div', { class: 'dp-spacer' }));
    out.push(el('button', {
      class: 'btn dp-commit', disabled: !(fit && fit.ok) || null,
      text: 'Commit DS1/DS2…',
      title: 'Write the call as the next version of the bank entry. '
             + 'A preview first, always.',
      onclick: preview,
    }));
    out.push(el('p', { class: 'hint', text:
      'Two more labels on the same events — nothing detected, nothing '
      + 'deleted, no stamp moved.' }));
    return out.filter(Boolean);
  }

  /* The three ways a patch becomes a feature vector, in the order they
     throw information away. */
  /* The three ways of splitting the events, in order of how much they
     lean on the sink gap. All three are computed on every fit -- a PCA
     over a few dozen columns is milliseconds, and having all three is the
     only way to know whether the gap is carrying the split or is along
     for the ride. */
  const METHODS = [
    ['pca', 'PCA, no gap',
     'The laminar profile and nothing else \u2014 the whole selected patch, '
     + 'normalised and rotated. What this tool did before the gap '
     + 'existed.'],
    ['pca_gap', 'PCA + gap',
     'The same, with one extra column: how far apart the event\u2019s two '
     + 'sinks are, on a 0\u20131 scale. One column among many, so it '
     + 'nudges rather than decides \u2014 turn the weight up to make it '
     + 'decide, and watch what that does.'],
    ['delta', 'delta only, no PCA',
     'One number per event, and k-means partitions that line directly. '
     + 'No rotation and no variance to be dominated by: what is clustered '
     + 'IS what you meant to cluster on, and the boundary is a threshold '
     + 'you can read off the axis and quote.'],
  ];

  const METHOD_NAMES = {};
  // Filled from METHODS below, so there is one list of names.

  const FEATURES = [
    ['minmax', 'min-max (Toothy)',
     'Each event scaled to 0-1 over the whole patch. Toothy’s own features '
     + '— and the scale is set by two samples, so an amplitude effect '
     + 'survives it.'],
    ['sign', 'sign ±1',
     'Source or sink per contact and nothing else: the laminar pattern with '
     + 'the magnitudes thrown away. If the classes survive this, they are '
     + 'not a loud-against-quiet split.'],
    ['sign_dead', 'sign + deadband',
     'Sign, but everything within 15% of the patch’s own peak counts as '
     + 'neither. Stops a contact where the CSD is essentially zero getting '
     + 'as much vote as the one at the sink.'],
  ];

  for (const [id, nm] of METHODS) METHOD_NAMES[id] = nm;

  const RULES = [
    ['tort', 'tortlab', 'the main sink above the main source; the '
      + 'shallower one is DS1'],
    ['sink', 'Toothy', 'argmin of each class’s mean profile — the '
      + 'deepest sink anywhere'],
    ['sources', 'source peaks', 'the most prominent source peak, ranked by '
      + 'prominence rather than height'],
    ['anatomy', 'anatomy', 'against the labelled hilus, so the answer '
      + 'survives a probe inserted the other way up'],
  ];

  const RULE_NAME = {
    tort: 'tortlab rule', sink: 'Toothy rule',
    sources: 'source peaks', anatomy: 'anatomy',
  };

  /* `first` is no longer used for spacing: `.card > .section-label
     :first-child` in app.css does that for every label that opens a card,
     everywhere, rather than each call site undoing the house margin by
     hand. Kept as an argument so the call sites still read as "this one
     opens the group", and ignored. */
  function label(text) {
    return el('div', { class: 'section-label', text });
  }

  /* ---------- committing ----------

     The dry run is the first thing this calls and the thing it shows. Every
     maintenance operation in this app works that way, and the fear that
     stops somebody pressing the button is always the same one: that a
     labelling they spent an afternoon on is about to be overwritten. So the
     preview says, in as many words, what is not happening. */
  async function preview() {
    if (!fit || !fit.ok) return;
    let rep;
    try {
      rep = await apiPost('/api/dspca/commit',
                          fitBody({ entry_id: q.entry,
                                    from_version: q.from_version,
                                    dry_run: true }));
    } catch (e) {
      toast(e.message, 'err', 10000);
      return;
    }
    const names = rep.label_names || {};
    const body = el('div', {}, [
      el('p', { text: rep.classified + ' of ' + rep.n + ' events get a type. '
                      + rep.unchanged + ' are left exactly as they are — '
                      + 'rejections, anything still undecided, and any stamp '
                      + 'the read could not place.' }),
      el('ul', {}, Object.keys(rep.counts || {}).sort().map((k) =>
        el('li', { text: rep.counts[k] + '  ' + (names[k] || k) }))),
      el('p', { class: 'hint', text:
        'Every labelled event keeps its event. Nothing is re-detected, '
        + 'nothing is dropped, and every stamp comes out at exactly the '
        + 'time it went in — which is checked before anything is written, '
        + 'not assumed.' }),
      el('table', { class: 'tbl dp-preview' }, [
        el('thead', {}, [el('tr', {}, ['time', 'was', 'now']
          .map((t) => el('th', { text: t })))]),
        el('tbody', {}, (rep.sample || []).map((m) => el('tr', {}, [
          el('td', { text: Number(m.t).toFixed(3) }),
          el('td', { text: m.was }),
          el('td', { text: m.now }),
        ]))),
      ]),
      el('p', { class: 'hint', text: rep.note }),
    ]);
    ask('Bank this as v' + rep.next_name + '?', body, 'Bank it',
        () => apply());
  }

  /* The panels as they are on screen, for filing beside the call.

     From here because this is where they were drawn. `dspca.py` is
     forbidden matplotlib at any depth -- the whole claim of the module is
     that it does not draw -- so rendering them again on the server would
     mean a second implementation of every panel and a figure that is not
     the one anybody looked at.

     A canvas that was never drawn (the feature matrix before its picture
     lands) is skipped rather than filed blank. */
  const FIG_PANELS = [
    ['shank', 'dpShank'], ['classes', 'dpClasses'],
    ['profile', 'dpProfile'], ['space', 'dpScatter'],
    ['features', 'dpFeat'], ['traces', 'dpTraces'],
  ];

  function panelPngs() {
    const out = [];
    for (const [id, cv] of FIG_PANELS) {
      const n = document.getElementById(cv);
      if (!n || !n.width || !n.height) continue;
      try {
        out.push({ id, png: n.toDataURL('image/png') });
      } catch (e) {
        // A tainted or oversized canvas is not worth failing a bank over.
        reportClientError('dspca.figure', e.message, String(e && e.stack));
      }
    }
    return out;
  }

  async function apply() {
    let rep;
    try {
      rep = await apiPost('/api/dspca/commit',
                          fitBody({ entry_id: q.entry,
                                    from_version: q.from_version,
                                    dry_run: false,
                                    /* Filed with the version, so the
                                       pictures and the numbers and the
                                       stamps are one act rather than
                                       three that can half-happen. */
                                    figures: panelPngs() }));
    } catch (e) {
      toast(e.message, 'err', 12000);
      return;
    }
    if (!rep.stamps_held) {
      toast(rep.warning || 'The bank came back with different stamps. '
            + 'Restore the previous version.', 'err', 15000);
      return;
    }
    /* A commit that changed nothing wrote nothing, and says so.

       `EventBank.add` mints a version only when something actually moved,
       which is right -- pressing this twice on the same answer should not
       put two identical versions in the history. Announcing a version
       either way would be confirming something that did not happen. */
    if (!rep.written) {
      toast(rep.already || 'Nothing changed, so nothing was written.',
            'warn', 8000);
      return;
    }
    /* The NAME, matching what the preview offered. The stored number and the
       lineage name are not the same thing once a number has been skipped,
       and showing one in the dialog and the other in the confirmation reads
       as two different commits. */
    toast('Banked as v' + (rep.version_name != null ? rep.version_name
                                                    : rep.version)
          + ' — ' + rep.relabelled + ' events typed, no stamp moved. '
          + 'The previous version is kept.', 'ok', 9000);
    // The set's counts have changed, so the chooser is stale.
    cands = null;
    loadCandidates();
  }

  /* The app's own modal, in the shape every other dialog uses: `mh`/`mb`/`mf`
     is what `#bigModalBox` is built to hold, and handing it a `.modal` of
     our own would put a modal inside a modal. */
  function ask(title, body, okText, onOk) {
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: title }), el('div', { class: 'spacer' })]),
      el('div', { class: 'mb dp-ask' }, [body]),
      el('div', { class: 'mf' }, [
        el('div', { style: 'flex:1' }),
        el('button', { class: 'btn ghost', text: 'Cancel',
                       onclick: closeModal }),
        el('button', { class: 'btn', text: okText,
                       onclick: () => { closeModal(); onOk(); } }),
      ]),
    ]), { replace: true });
  }

  /* The guide list: what is on the probe, and one row to add another.

     The contact box is pre-filled with the middle of the current feature
     box, because that is where somebody putting in their first guide is
     looking -- and it is a number they can then drag, rather than one they
     have to be right about first time. */
  function guideList() {
    const b = (fit && fit.ok && fit.box) || {};
    const mid = b.lo ? Math.round((b.lo + b.hi) / 2) : '';
    const csc = el('input', { class: 'dp-gnum', type: 'number',
                              placeholder: 'CSC', value: mid });
    const name = el('input', { class: 'dp-gname', type: 'text',
                               placeholder: 'name, e.g. hilus' });
    const add = () => {
      const n = parseInt(csc.value, 10);
      if (!isFinite(n)) { toast('Which contact?', 'warn', 4000); return; }
      saveGuide(n, name.value.trim() || '');
      name.value = '';
    };
    name.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); add(); }
    });

    const rows = guides.map((g) => el('div', { class: 'dp-guide' }, [
      /* The chip IS the picker. It already has to be on the row to say
         which line this is, and a separate swatch beside it would be two
         controls for one fact -- in a column this narrow, that is the
         difference between a list and a form.

         A native colour input rather than a row of swatches, for the reason
         Storyboard keeps one beside its swatches: the useful case is
         matching a colour that is already in a figure. The defaults are
         handed out server-side so this is rarely touched. */
      el('input', {
        class: 'dp-gcolor', type: 'color', value: g.color || '#e5484d',
        title: 'The ink this guide is drawn in, here and in Xplorefinder',
        onchange: (e) => saveGuide(g.csc, undefined, g.id, e.target.value),
      }),
      el('input', {
        class: 'dp-gedit', type: 'text', value: g.label || '',
        placeholder: 'name',
        onchange: (e) => saveGuide(g.csc, e.target.value.trim(), g.id),
      }),
      el('span', { class: 'dp-gcsc', text: 'CSC' + g.csc }),
      el('button', { class: 'linkish dp-gdrop', text: '\u00d7',
                     title: 'Take this guide off',
                     onclick: () => dropGuide(g.id) }),
    ]));

    return el('div', { class: 'dp-guides' }, [
      el('div', { class: 'dp-grow' }, [csc, name,
        el('button', { class: 'btn ghost sm', text: 'add', onclick: add })]),
      rows.length ? el('div', { class: 'dp-glist' }, rows)
                  /* Short, because it sits in the control strip and the
                     strip is settings rather than documentation. The
                     whole sentence is on the `add` button's title. */
                  : el('p', { class: 'hint', text:
                      'None yet. A named line at one contact, on every '
                      + 'panel here and in Xplorefinder.' }),
      rows.length ? el('div', { class: 'dp-grow' }, [
        el('button', { class: 'linkish', text: 'clear all',
                       onclick: () => dropGuide(null) }),
        el('span', { class: 'hint', text: 'drag a line to move it' }),
      ]) : null,
      Object.keys((fit && fit.layers) || {}).length
        ? el('label', { class: 'dp-check', title:
            'StrataScope\u2019s per-contact regions, as faint boundaries. '
            + 'Useful for placing the first guide; noisy once there are '
            + 'several.' }, [
            el('input', { type: 'checkbox', checked: showLayers || null,
                          onchange: (e) => { showLayers = e.target.checked;
                                             drawAll(); } }),
            el('span', { text: 'show StrataScope layers' }),
          ])
        : null,
    ].filter(Boolean));
  }

  /* What the methods nobody chose made of the same events.

     The headline of the comparison, and the reason all three are
     computed: if the three agree, the split is in the data rather than in
     the method; if they do not, the choice of method IS the answer and
     should be made on purpose. */
  /* WHICH MODE THIS PICTURE IS OF.

     Off `fit`, never off `q`: `q.method` is what has been ASKED for and
     changes the instant a radio is clicked, while the chart underneath
     is still the previous answer until the refit lands. A chip that
     renamed the picture before the picture changed would be a label
     telling you something untrue about what you are looking at -- which
     is the one thing a label on a chart must not do. */
  function modeChip() {
    if (!fit || !fit.ok || !fit.method_name) return null;
    const pending = q.method !== fit.method;
    return el('span', {
      class: 'dp-chip' + (pending ? ' dp-chip-stale' : ''),
      title: pending
        ? 'This is still the previous answer — ' + fit.method_name
          + '. Recompute to see ' + (METHOD_NAMES[q.method] || q.method) + '.'
        : 'The method this chart was computed with.',
      text: fit.method_name + (pending ? '  (recompute)' : ''),
    });
  }

  /* A section heading with the mode it is showing beside it. */
  function modeLabel(text) {
    return el('div', { class: 'section-label dp-modelab' }, [
      el('span', { text }),
      modeChip(),
    ].filter(Boolean));
  }

  function methodAgree() {
    const vs = (fit && fit.ok && fit.variants) || null;
    if (!vs) return el('div', {});
    const n = (fit.events || []).length || 1;
    const rows = METHODS
      .filter(([id]) => id !== q.method && vs[id])
      .map(([id, nm]) => {
        const v = vs[id];
        const same = v.agree || 0;
        return el('div', { class: 'dp-agree-row' }, [
          el('span', { class: 'hint', text: nm }),
          el('span', {
            class: 'flagchip' + (same === n ? ' ok' : ''),
            title: same === n
              ? 'Every event lands in the same class either way, so this '
                + 'split does not depend on the method.'
              : (n - same) + ' event(s) change class under this method. '
                + 'The choice of method is part of the answer.',
            text: same === n ? 'same answer'
                             : same + ' of ' + n + ' agree',
          }),
        ]);
      });
    if (!rows.length) return el('div', {});
    return el('div', { class: 'dp-agree' }, rows);
  }

  function mainsLine() {
    if (!fit || !fit.ok) return null;
    const m = fit.mains_uv, w = fit.wideband_uv;
    if (m == null || !w) return null;
    return el('div', { class: 'hint dp-mains', text:
      'mains ' + m.toFixed(1) + ' µV rms of ' + w.toFixed(0) + ' µV ('
      + (100 * m / Math.max(w, 1e-9)).toFixed(0) + '%)' });
  }

  /* ---------- the two panes ---------- */
  function panes() {
    const what = picked == null ? 'the average' : ('spike ' + (picked + 1));
    return [
      el('div', { class: 'dp-pane-head' }, [
        el('strong', { text: 'Voltage and CSD' }),
        el('span', { class: 'dp-chip', text: '5–100 Hz · 60 Hz notched' }),
        el('span', { class: 'dp-showing', text: what }),
      ]),
      el('canvas', { class: 'dp-canvas dp-traces', id: 'dpTraces' }),
      el('canvas', { class: 'dp-canvas dp-shank', id: 'dpShank' }),
      el('div', { class: 'dp-pane-foot' }, [
        el('span', { class: 'hint', text: 'drag a box: depth × time' }),
        el('button', { class: 'btn ghost sm', text: '◀ prev',
                       onclick: () => step(-1) }),
        el('button', { class: 'btn ghost sm', text: 'next ▶',
                       onclick: () => step(+1) }),
        el('button', { class: 'btn ghost sm', text: 'show average',
                       disabled: picked == null || null,
                       onclick: () => { picked = null; render();
                                        pictures(['traces', 'pane']); } }),
        el('button', { class: 'btn ghost sm', text: 'Open in Xplorefinder',
                       disabled: picked == null || null,
                       onclick: openInXplore }),
        el('button', { class: 'btn ghost sm', text: 'Under the hood',
                       title: 'Every number between this spike\u2019s CSD '
                            + 'patch and the class it was put in.',
                       onclick: openHood }),
        /* Here, and not in a bar over the pictures.

           It is about the box, the box is dragged on the panel just above,
           and a bar across the top of the panel put the thing you press
           furthest from the thing you just did. */
        applyBar(),
      ]),
    ];
  }

  /* ---------- the answer ---------- */
  function answer() {
    if (fit && !fit.ok) {
      return [el('div', { class: 'card dp-err' }, [
        el('strong', { text: 'That box cannot be used' }),
        el('p', { class: 'hint', text: fit.error }),
      ])];
    }
    if (!fit) return [loading('Fitting')];
    const out = [];
    out.push(modeLabel('Class-average depth profile ± SEM'));
    out.push(el('canvas', { class: 'dp-canvas dp-profile', id: 'dpProfile' }));

    out.push(el('div', { class: 'section-label', text: 'Mean CSD per class' }));
    out.push(el('canvas', { class: 'dp-canvas dp-classes', id: 'dpClasses' }));

    /* The feature matrix itself: one column per event, sorted by class.

       NOT DECORATION. Every other picture here is an average, and an
       average is exactly where one bad column hides. On this one a dead
       contact is a solid stripe running the width of the sheet, which is
       how the first version of this analysis was caught classifying one
       wire rather than one kind of event.

       It is also the only panel showing what the PCA actually sees: the
       rasters are the band-limited, mains-out CSD because that is what is
       legible, and this is whatever the feature mode returned. */
    out.push(modeLabel('The features, every event'));
    out.push(el('canvas', { class: 'dp-canvas dp-feat', id: 'dpFeat' }));
    if (pics.features && pics.features.ok) {
      const pf = pics.features;
      out.push(el('p', { class: 'hint', text:
        pf.n_features + ' features (' + pf.n_contacts + ' contacts '
        + '× ' + pf.n_samples + ' sample'
        + (pf.n_samples === 1 ? '' : 's') + ') down, ' + pf.n_events
        + ' events across, sorted by class — ' + pf.mode_name
        + '. A dead contact is a stripe.' }));
    }

    out.push(whyCard());
    out.push(repairedLine());
    return out.filter(Boolean);
  }

  /* The PCA, beside the controls.

     Click a dot and the two panes above stop showing the average and show
     that event -- which is the check that separates a type from a line
     drawn through a cloud, and the reason this sits where the controls are
     rather than with the depth pictures. */
  function pcaPane() {
    if (!fit || !fit.ok) return [];
    return [
      el('div', { class: 'dp-pane-head' }, [
        el('strong', { text: isDelta() ? 'Sink gap' : 'PCA' }),
        modeChip(),
        el('span', { class: 'dp-chip', text: fit.n_features + ' feature'
                     + (fit.n_features === 1 ? '' : 's') }),
        el('span', { class: 'hint', text: isDelta()
          ? 'no rotation — this is the number itself'
          : 'PC1 ' + pct((fit.explained || [])[0])
            + ' · PC2 ' + pct((fit.explained || [])[1]) }),
        el('div', { style: 'flex:1' }),
        el('span', { class: 'hint', text: isDelta()
          ? 'one number per event; click a dot to see that spike'
          : 'click a dot to see that spike' }),
      ]),
      el('canvas', { class: 'dp-canvas dp-scatter', id: 'dpScatter' }),
    ];
  }

  /* A panel whose whole job is to show its working.

     The rule is one argmin off a curve that often has three or four
     excursions. Stated in a legend it reads as a fact about anatomy, which
     it is not. */
  function whyCard() {
    const rows = (fit && fit.decide) || [];
    const how = {
      tort: 'the main SINK above the main SOURCE; the shallower one is DS1',
      sink: 'argmin of each class’s mean profile — the deepest sink; '
            + 'shallower is DS1',
      sources: 'the most prominent SOURCE peak; the shallower one is DS1',
      anatomy: 'each class’s main sink against the labelled hilus',
    }[q.rule];
    const src = q.rule === 'sources';
    const kids = [
      el('div', { class: 'section-label', text: 'How DS1/DS2 was decided' }),
      el('p', { class: 'hint', text: how }),
    ];
    if (fit && fit.tort_upside) {
      kids.push(el('p', { class: 'hint dp-warn', text:
        'The classes landed on the same contact, so the profile was re-read '
        + 'upside down — which is what CSDbC does, because a probe inserted '
        + 'the other way round makes “above the source” point the wrong '
        + 'way.' }));
    }
    for (const d of rows) {
      if (!d.n) {
        kids.push(el('div', { class: 'dp-decide dim',
                              text: 'DS' + d.c + '   no events' }));
        continue;
      }
      kids.push(el('div', { class: 'dp-decide' }, [
        el('i', { style: 'background:' + colorOf(d.c) }),
        el('span', { text: 'DS' + d.c + '  n=' + d.n + '  '
                           + (src ? 'source' : 'sink') + ' CSC' + d.csc }),
      ]));
      if (d.lows && d.lows.length > 1 && q.rule === 'sink') {
        kids.push(el('div', { class: 'hint dp-warn', text:
          'CAREFUL — DS' + d.c + ' dips at CSC' + d.lows.join(', CSC')
          + '. argmin takes the deepest dip, not the shallowest. Narrow the '
          + 'box, or use the tortlab rule.' }));
      }
    }
    if (q.flip) {
      kids.push(el('div', { class: 'hint dp-warn',
                            text: 'Flipped by hand.' }));
    }
    return el('div', { class: 'card dp-why' }, kids);
  }

  function repairedLine() {
    const s = (fit && fit.screened) || {};
    const ns = Object.keys(s);
    if (!ns.length) return null;
    return el('p', { class: 'hint dp-repaired', text:
      'Repaired, not dropped: ' + ns.map((n) => 'CSC' + n).join(', ')
      + '. A contact taken out of the middle leaves the rest unevenly '
      + 'spaced, and a second difference over an uneven grid is not a CSD.' });
  }

  /* ==================================================================
     Drawing
     ================================================================== */
  function ink() {
    const css = getComputedStyle(document.documentElement);
    const t = (n, f) => (css.getPropertyValue(n) || f).trim() || f;
    return {
      text: t('--text', '#222'), dim: t('--text-3', '#888'),
      line: t('--line', '#ccc'), bg: t('--bg', '#fff'),
      accent: t('--accent', '#c8a'), warn: t('--warn', '#a4531c'),
    };
  }

  function colorOf(c) {
    const cols = (fit && fit.colors) || ['#1a7f37', '#7b3fa0', '#b8620a',
                                         '#1f6feb', '#a3155f'];
    return cols[(c - 1) % cols.length];
  }

  /* A canvas, with a backing store that matches the box it is drawn in.

     `fill` is for the canvases their column STRETCHES. `.dp-pca .dp-canvas`
     and the CSD pane are `flex: 1 1 auto`, so the spare height of the row
     goes into them -- and a backing store built for the height we asked
     for was then stretched by the browser to the height it actually got.
     That is what made the PCA look low resolution: the dots were drawn as
     circles into a 268px bitmap and shown 400px tall, so they arrived as
     furry vertical ellipses, and every label with them.

     So the height is MEASURED when the box decides it, and imposed only
     when it does not. Measuring first and writing the same number back is
     not a layout loop: the value written is the one already computed. */
  function sized(id, h, fill) {
    const cv = document.getElementById(id);
    if (!cv) return null;
    if (!fill) cv.style.height = h + 'px';
    /* The CONTENT box, which is what `clientHeight` is and what
       `getBoundingClientRect` is not.

       Every one of these canvases has a 1px border. Measuring the outside
       and then drawing that many pixels INSIDE makes a bitmap two pixels
       too big for the box it is shown in, and the browser scales the
       difference -- the same fault as the one above, two pixels instead of
       a hundred and thirty. Measured: shown 455x235, drawn 453x233. */
    const got = cv.clientHeight;
    // Nothing laid out yet: draw the asked-for height rather than a
    // zero-pixel canvas, and come back on the next draw.
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

  /* THE FIXED-HEIGHT PANELS FIRST, and the order is not arbitrary.

     `sized` gives those an explicit height, which changes how much of the
     column is left for the ones that stretch. Drawing a stretching panel
     before them measures a share that is about to change -- and nothing
     tells it to try again, because what ended up wrong is the canvas's
     backing store and not its box, so no resize is observed. That is what
     left the profile and the scatter drawn at the wrong size on some runs
     and not others.

     Fixed first, then stretching, and then one more pass if anything is
     still mismatched. Bounded at two: a third would not be a fix, it
     would be a loop. */
  function drawPass() {
    drawTraces();
    drawClasses();
    drawShank();
    drawScatter();
    drawProfile();
    drawFeatures();
  }

  function drawAll() {
    drawPass();
    if (mismatched()) drawPass();
    watchSize();
  }

  const PAD = { l: 34, r: 8, t: 6, b: 18 };

  /* The stacked voltage panel.

     Traces overlapping is how a stacked ephys raster is supposed to look --
     the gain is in CONTACT UNITS, so the biggest deflection on the shank
     spans `gain` contacts. The server has already done that conversion; this
     draws `contact - value`. */
  function drawTraces() {
    const s = sized('dpTraces', 250);
    const d = pics.traces;
    if (!s || !d || !d.ok) return;
    const k = ink();
    const ns = d.contacts;
    const lo = ns[0] - d.gain, hi = ns[ns.length - 1] + d.gain;
    const X = (i) => PAD.l + (i / (d.t_ms.length - 1)) * (s.w - PAD.l - PAD.r);
    const Y = (v) => PAD.t + ((v - lo) / (hi - lo)) * (s.h - PAD.t - PAD.b);
    const bx = shownBox();
    const inBox = (n) => !!bx && n >= bx.lo && n <= bx.hi;

    // The time window the features come from, shaded on the trace panel too:
    // the box is a fact about both pictures.
    if (bx) {
      s.g.fillStyle = k.accent;
      s.g.globalAlpha = 0.12;
      const a = XofMs(bx.t_lo_ms, d.t_ms, s.w);
      const b = XofMs(bx.t_hi_ms, d.t_ms, s.w);
      s.g.fillRect(a, PAD.t, Math.max(1.5, b - a), s.h - PAD.t - PAD.b);
      s.g.globalAlpha = 1;
    }
    for (let r = 0; r < d.rows.length; r++) {
      const n = ns[r];
      const on = inBox(n);
      s.g.strokeStyle = on ? k.text : k.dim;
      s.g.globalAlpha = on ? 1 : 0.4;
      s.g.lineWidth = on ? 0.9 : 0.6;
      s.g.beginPath();
      const row = d.rows[r];
      for (let i = 0; i < row.length; i++) {
        const x = X(i), y = Y(n + row[i]);
        if (i) s.g.lineTo(x, y); else s.g.moveTo(x, y);
      }
      s.g.stroke();
    }
    s.g.globalAlpha = 1;
    // The stamp.
    const zero = XofMs(0, d.t_ms, s.w);
    s.g.strokeStyle = '#b03030';
    s.g.setLineDash([4, 3]);
    s.g.beginPath(); s.g.moveTo(zero, PAD.t); s.g.lineTo(zero, s.h - PAD.b);
    s.g.stroke(); s.g.setLineDash([]);
    axesDepth(s, k, ns[0], ns[ns.length - 1], lo, hi);
    axisMs(s, k, d.t_ms);
    layerLines(s, k, lo, hi);
    depthAt('dpTraces', s, lo, hi);
    drawGuides(s, 'dpTraces');
  }

  function XofMs(ms, t_ms, w) {
    const a = t_ms[0], b = t_ms[t_ms.length - 1];
    return PAD.l + ((ms - a) / (b - a)) * (w - PAD.l - PAD.r);
  }

  /* The CSD raster, and the thing you drag on. */
  function drawShank() {
    const s = sized('dpShank', 330, true);
    const d = pics.pane;
    if (!s || !d || !d.ok) return;
    const k = ink();
    const img = imageFor('pane', d.image, drawShank);
    const x0 = PAD.l, y0 = PAD.t;
    const pw = s.w - PAD.l - PAD.r, ph = s.h - PAD.t - PAD.b;
    if (img) s.g.drawImage(img, x0, y0, pw, ph);

    s.shankGeom = { x0, y0, pw, ph, lo: d.lo, hi: d.hi, ext: d.extent };
    GEOM.shank = s.shankGeom;

    // The box, ruled on the picture rather than described under it.
    const bx = shownBox();
    if (bx) {
      const bx0 = x0 + frac(bx.t_lo_ms, d.extent) * pw;
      const bx1 = x0 + frac(bx.t_hi_ms, d.extent) * pw;
      const by0 = y0 + ((bx.lo - 0.5 - d.lo) / (d.hi - d.lo + 1)) * ph;
      const by1 = y0 + ((bx.hi + 0.5 - d.lo) / (d.hi - d.lo + 1)) * ph;
      s.g.strokeStyle = '#ffffff';
      s.g.lineWidth = 1.6;
      s.g.strokeRect(bx0, by0, Math.max(2, bx1 - bx0), by1 - by0);
      s.g.strokeStyle = 'rgba(0,0,0,.55)';
      s.g.lineWidth = 0.7;
      s.g.strokeRect(bx0, by0, Math.max(2, bx1 - bx0), by1 - by0);
    }

    /* THE DEPTH PROFILE OF WHAT THIS RASTER IS SHOWING.

       A raster is a field, and the eye is bad at reading a trough out
       of one -- "where is the sink" is a question about a curve. This
       is that curve, over the same time window the features come from,
       drawn down the right so it does not cover the event.

       The line is the picture's own signal; the marks on it are the
       measurement's, which is the band-limited, mains-out CSD inside
       the selected band. Same split the box has, said rather than
       hidden. */
    const dl = d.line;
    if (q.depth_line && dl && (dl.values || []).length) {
      const lw = Math.min(140, pw * 0.26);
      const lx = x0 + pw - lw - 4;
      let lo2 = Infinity, hi2 = -Infinity;
      for (const v of dl.values) {
        if (v == null || !isFinite(v)) continue;
        lo2 = Math.min(lo2, v); hi2 = Math.max(hi2, v);
      }
      const mag = Math.max(Math.abs(lo2), Math.abs(hi2)) || 1;
      const LX = (v) => lx + lw / 2 + (v / mag) * (lw / 2 - 2);
      const LY = (n) => y0 + ((n - d.lo) / (d.hi - d.lo + 1)) * ph;

      // A ground for it, so the sign is readable.
      s.g.strokeStyle = k.line;
      s.g.lineWidth = 1;
      s.g.setLineDash([2, 3]);
      s.g.beginPath();
      s.g.moveTo(LX(0), y0); s.g.lineTo(LX(0), y0 + ph);
      s.g.stroke();
      s.g.setLineDash([]);

      s.g.strokeStyle = k.text;
      s.g.lineWidth = 1.6;
      s.g.beginPath();
      dl.values.forEach((v, j) => {
        const n = (dl.contacts || [])[j];
        if (n == null) return;
        const x = LX(v), y = LY(n);
        if (j) s.g.lineTo(x, y); else s.g.moveTo(x, y);
      });
      s.g.stroke();

      // Every candidate sink, ticked; the two the gap used, bracketed.
      s.g.strokeStyle = k.dim;
      s.g.lineWidth = 1;
      for (const n of (dl.peaks || [])) {
        const y = LY(n);
        s.g.beginPath();
        s.g.moveTo(lx - 3, y); s.g.lineTo(lx + 1, y);
        s.g.stroke();
      }
      if (dl.sinks) {
        drawGap(s, k, dl.sinks, LY, lx - 8,
                colorOf(picked == null ? 1 : (pickedClass() || 1)), true);
      }
      s.g.fillStyle = k.dim;
      s.g.font = '9px system-ui, sans-serif';
      s.g.fillText(fmtMs(dl.window_ms[0]) + ' to ' + fmtMs(dl.window_ms[1]),
                   lx, y0 + ph + 10);
    }

    /* AND THE DELTA FOR WHAT THIS RASTER IS SHOWING.

       One spike when one is picked; nothing for the whole-shank average,
       because the gap is a per-event measure and an average of the
       rasters is not an event. */
    if (picked != null) {
      const one_ = gapOf(picked);
      if (one_) {
        const yOf = (n) => y0 + ((n - d.lo) / (d.hi - d.lo + 1)) * ph;
        drawGap(s, k, one_, yOf, x0 + 12,
                colorOf(pickedClass() || 1), true);
      }
    }
    if (dragging && dragging.live) {
      s.g.strokeStyle = '#ffffff';
      s.g.setLineDash([4, 3]);
      s.g.lineWidth = 1.3;
      const r = dragging.live;
      s.g.strokeRect(r.x, r.y, r.w, r.h);
      s.g.setLineDash([]);
    }
    axesDepth(s, k, d.lo, d.hi, d.lo - 0.5, d.hi + 0.5);
    axisMsExtent(s, k, d.extent);
    layerLines(s, k, d.lo - 0.5, d.hi + 0.5);
    depthAt('dpShank', s, d.lo - 0.5, d.hi + 0.5);
    drawGuides(s, 'dpShank');
  }

  const GEOM = {};
  const IMGS = {};

  /* Data URIs decode asynchronously, so the first draw after a fetch has no
     bitmap yet. Cached by source and redrawn on load rather than drawn from
     a handler that might fire after the next fetch has replaced it. */
  function imageFor(key, src, then) {
    if (!src) return null;
    const have = IMGS[key];
    if (have && have.src === src && have.img.complete) return have.img;
    if (!have || have.src !== src) {
      const img = new Image();
      IMGS[key] = { src, img };
      img.onload = () => { if (IMGS[key] && IMGS[key].src === src) then(); };
      img.src = src;
      return null;
    }
    return null;
  }

  /* A CSD peak, short enough for a corner. Three significant figures is
     more than the picture carries and two is enough to compare on. */
  function fmtPeak(v) {
    const x = Math.abs(v);
    if (!isFinite(x) || x === 0) return '0';
    if (x >= 1000) return (x / 1000).toFixed(1) + 'k';
    if (x >= 100) return String(Math.round(x));
    if (x >= 10) return x.toFixed(1);
    if (x >= 1) return x.toFixed(2);
    return x.toExponential(1);
  }

  function frac(ms, ext) {
    return (ms - ext[0]) / (ext[1] - ext[0]);
  }

  function axesDepth(s, k, lo, hi, vlo, vhi) {
    s.g.strokeStyle = k.line;
    s.g.lineWidth = 1;
    s.g.strokeRect(PAD.l, PAD.t, s.w - PAD.l - PAD.r, s.h - PAD.t - PAD.b);
    s.g.fillStyle = k.dim;
    s.g.font = '9px system-ui, sans-serif';
    s.g.textAlign = 'right';
    const step = Math.max(1, Math.round((hi - lo) / 6));
    for (let n = lo; n <= hi; n += step) {
      const y = PAD.t + ((n - vlo) / (vhi - vlo)) * (s.h - PAD.t - PAD.b);
      s.g.fillText(String(n), PAD.l - 4, y + 3);
    }
    s.g.textAlign = 'left';
  }

  function axisMs(s, k, t_ms) {
    axisMsExtent(s, k, [t_ms[0], t_ms[t_ms.length - 1]]);
  }

  function axisMsExtent(s, k, ext) {
    s.g.fillStyle = k.dim;
    s.g.font = '9px system-ui, sans-serif';
    s.g.textAlign = 'center';
    const span = ext[1] - ext[0];
    const step = span > 60 ? 25 : span > 20 ? 10 : 5;
    for (let t = Math.ceil(ext[0] / step) * step; t <= ext[1]; t += step) {
      const x = PAD.l + frac(t, ext) * (s.w - PAD.l - PAD.r);
      s.g.fillText((t > 0 ? '+' : '') + t, x, s.h - 5);
    }
    s.g.textAlign = 'left';
  }

  /* StrataScope's laminar boundaries, as faint context.

     Off by default, and that is a change from the first version. Once a
     recording has real guides on it, drawing sixty-four contacts' worth of
     region changes underneath them is more line than data -- which is the
     same argument `MAX_GUIDES` makes. They are a checkbox because on a
     recording somebody HAS labelled they are the fastest way to put the
     first guide in the right place. */
  function layerLines(s, k, vlo, vhi) {
    if (!showLayers) return;
    const labs = (fit && fit.layers) || {};
    const ids = Object.keys(labs);
    if (!ids.length || !regions || !regions.length) return;
    const byNum = ids.map(Number).sort((a, b) => a - b);
    let last = null;
    for (const n of byNum) {
      const id = labs[String(n)];
      if (id === last) continue;
      last = id;
      const y = PAD.t + ((n - 0.5 - vlo) / (vhi - vlo)) * (s.h - PAD.t - PAD.b);
      if (y < PAD.t || y > s.h - PAD.b) continue;
      const reg = regions.find((r) => r.id === id);
      s.g.save();
      s.g.strokeStyle = 'rgba(255,255,255,.9)';
      s.g.lineWidth = 2.6;
      s.g.setLineDash([6, 3]);
      s.g.beginPath(); s.g.moveTo(PAD.l, y); s.g.lineTo(s.w - PAD.r, y);
      s.g.stroke();
      s.g.strokeStyle = '#101010';
      s.g.lineWidth = 1.05;
      s.g.stroke();
      s.g.setLineDash([]);
      if (reg) {
        s.g.font = '9px system-ui, sans-serif';
        s.g.lineWidth = 2.4;
        s.g.strokeStyle = 'rgba(255,255,255,.95)';
        s.g.strokeText(reg.name, PAD.l + 3, y - 2);
        s.g.fillStyle = '#101010';
        s.g.fillText(reg.name, PAD.l + 3, y - 2);
      }
      s.g.restore();
    }
  }

  /* ==================================================================
     Guides -- one line, five pictures
     ================================================================== */
  /* Every depth panel records how it maps a contact number to a y, as it
     draws. Two things read it back: the guide drawer, so a line lands on
     the same contact in all of them, and the drag handler, so a line can be
     taken hold of wherever it is easiest to see.

     Recorded rather than recomputed because each panel has a different
     range -- the traces show the whole shank with a margin for the gain,
     the profile shows only the box -- and a second copy of that arithmetic
     is a second chance to get it wrong. */
  function depthAt(id, s, vlo, vhi) {
    const top = PAD.t, h = s.h - PAD.t - PAD.b;
    DEPTH[id] = {
      x0: PAD.l, x1: s.w - PAD.r, y0: top, h,
      vlo, vhi,
      yOf: (n) => top + ((n - vlo) / (vhi - vlo)) * h,
      cscOf: (y) => vlo + ((y - top) / h) * (vhi - vlo),
    };
    return DEPTH[id];
  }

  /* A guide, drawn.

     Solid and haloed rather than dashed, for the reason Xplorefinder's own
     channel lines are: a dash reads as provisional when this is the most
     definite thing on the panel, and it breaks the horizontal continuity
     that makes a line findable at a glance across a wide plot. The label
     sits in a filled pill so it is legible over a jet colormap, which no
     single ink is. */
  /* A MARK AT A DEPTH, NOT A LINE OVER THE DATA.

     The first version drew each guide as a solid rule from edge to edge.
     With four of them on a CSD raster that is four opaque bars across the
     thing you are trying to read -- and the sink you are placing them
     against is exactly what they cover.

     So: a short tack at each edge, which is what says "this depth" and is
     also what you take hold of, and a faint dotted hairline between them so
     the eye can still carry the depth across a wide plot. The hairline is
     at a fifth of the ink and dotted, which reads as a reference rather
     than as data.

     Dragging one makes it solid for as long as the drag lasts, because
     while you are placing it, it IS the thing being looked at. */
  function drawGuides(s, id) {
    const g = DEPTH[id];
    if (!g || !guides.length) return;
    const ctx = s.g;
    const span = g.x1 - g.x0;
    const tack = Math.max(14, Math.min(34, span * 0.045));
    // Label rows already taken on this panel, so two guides a contact apart
    // do not print on top of each other.
    const taken = [];
    ctx.save();
    for (const gd of guides) {
      const on = !!(dragGuide && dragGuide.id === gd.id);
      const live = on ? dragGuide.at : gd.csc;
      const y = Math.round(g.yOf(live)) + 0.5;
      if (y < g.y0 - 1 || y > g.y0 + g.h + 1) continue;
      const col = gd.color || '#e5484d';

      // The hairline across, faint. Solid and full strength only while the
      // guide is being dragged.
      ctx.setLineDash(on ? [] : [2, 5]);
      ctx.globalAlpha = on ? 0.9 : 0.28;
      ctx.strokeStyle = col;
      ctx.lineWidth = on ? 1.6 : 1;
      ctx.beginPath();
      ctx.moveTo(g.x0 + tack, y); ctx.lineTo(g.x1 - tack, y);
      ctx.stroke();
      ctx.setLineDash([]);

      // The tacks. White under the ink, because no single colour holds
      // against a jet colormap on its own.
      ctx.globalAlpha = 1;
      for (const [ax, bx] of [[g.x0, g.x0 + tack], [g.x1 - tack, g.x1]]) {
        ctx.strokeStyle = 'rgba(255,255,255,0.95)';
        ctx.lineWidth = on ? 5 : 3.6;
        ctx.beginPath(); ctx.moveTo(ax, y); ctx.lineTo(bx, y); ctx.stroke();
        ctx.strokeStyle = col;
        ctx.lineWidth = on ? 2.6 : 1.8;
        ctx.beginPath(); ctx.moveTo(ax, y); ctx.lineTo(bx, y); ctx.stroke();
      }

      // The name, over the left tack, nudged clear of any label already
      // printed. Only where the panel is wide enough to hold one -- on a
      // narrow pane the tacks and the colour say which is which.
      const text = (gd.label || 'guide') + ' ' + Math.round(live);
      ctx.font = '600 10px ui-sans-serif, system-ui, sans-serif';
      const w = ctx.measureText(text).width + 10;
      if (w > span * 0.45) continue;
      let ly = y - 13;
      for (let n = 0; n < 8 && taken.some(
             (t) => Math.abs(t - ly) < 13); n++) ly += 13;
      ly = Math.max(g.y0 + 1, Math.min(g.y0 + g.h - 13, ly));
      taken.push(ly);
      ctx.globalAlpha = on ? 1 : 0.92;
      ctx.fillStyle = col;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(g.x0 + 2, ly, w, 12, 6);
      else ctx.rect(g.x0 + 2, ly, w, 12);
      ctx.fill();
      ctx.fillStyle = '#ffffff';
      ctx.fillText(text, g.x0 + 7, ly + 9);
    }
    ctx.restore();
    ctx.globalAlpha = 1;
  }

  /* Which guide is under the pointer on this panel, if any. */
  function guideAt(id, y) {
    const g = DEPTH[id];
    if (!g) return null;
    let best = null, bd = 7;
    for (const gd of guides) {
      const d = Math.abs(g.yOf(gd.csc) - y);
      if (d < bd) { bd = d; best = gd; }
    }
    return best;
  }

  /* The PCA scatter. Click a dot and the panes stop showing the average and
     show that event -- the check that separates a type from a line drawn
     through a cloud. */
  const isDelta = () => (fit && fit.ok && fit.method === 'delta');
  /* Where k-means drew its line. Off the active variant, so it is the
     boundary of the answer on screen and not of one beside it. */
  /* The boundaries as they should be DRAWN: the dragged one follows the
     pointer, the rest are the answer's. */
  function deltaBoundsLive() {
    const base = (q.delta_cut || deltaBounds()).slice();
    if (cutDrag && cutDrag.at_i != null && cutDrag.at != null) {
      base[cutDrag.at_i] = cutDrag.at;
      base.sort((a, b) => a - b);
    }
    return base;
  }

  const deltaBounds = () => {
    const v = (fit && fit.ok && (fit.variants || {})[fit.method]) || null;
    return (v && v.bounds) || [];
  };

  /* THE DELTA SPACE IS A LINE.

     One number per event, so there is no plane and no rotation: the
     events are laid along the axis they were clustered on, jittered
     vertically only so that ties are countable, and the boundary
     k-means drew is a vertical rule at a value that can be read off and
     quoted. That is the whole argument for this method -- a threshold
     somebody can put in a methods section, rather than "the first two
     components of a rotation".

     Drawn here rather than by bending the scatter: a strip plot and a
     cloud share an axis convention and nothing else, and the version
     that tried to be both drew the boundary as a diagonal. */
  /* How tall the cut's own strip is. Everything below it belongs to
     the dots. */
  const CUT_RAIL = 22;

  function drawDeltaSpace(s, k) {
    const evs = (fit.events || []).filter((e) => e.pc1 != null);
    if (!evs.length) return;
    const x0 = PAD.l, pw = s.w - PAD.l - PAD.r;
    const rail0 = PAD.t;
    const y0 = PAD.t + CUT_RAIL, ph = s.h - y0 - PAD.b;
    const X = (v) => x0 + Math.max(0, Math.min(1, v)) * pw;

    /* THE CUT HAS ITS OWN STRIP, and the dots have the rest.

       It used to be that a click anywhere on this panel moved the
       boundary, with shift to pick an event instead. That is backwards:
       clicking a dot to look at the spike is the thing you do
       constantly, and moving the cut is the thing you do once. So a
       click on a dot picks it, and the cut is dragged on a rail of its
       own above them, where there is nothing else to hit. */
    s.g.fillStyle = k.bg2 || k.bg;
    s.g.fillRect(x0, rail0, pw, CUT_RAIL);
    s.g.strokeStyle = k.line;
    s.g.strokeRect(x0, rail0, pw, CUT_RAIL);
    s.g.strokeRect(x0, y0, pw, ph);
    s.g.fillStyle = k.dim;
    s.g.font = '9px system-ui, sans-serif';
    s.g.fillText('drag the cut', x0 + 4, rail0 + 14);

    // The boundary, first, so the dots sit on top of it.
    const live = deltaBoundsLive();
    live.forEach((b, i2) => {
      const bx = X(b);
      s.g.strokeStyle = k.text;
      s.g.lineWidth = 1.4;
      s.g.setLineDash([4, 3]);
      s.g.beginPath();
      s.g.moveTo(bx, y0);
      s.g.lineTo(bx, y0 + ph);
      s.g.stroke();
      s.g.setLineDash([]);
      // The grip, in the rail: a solid handle rather than a dashed line,
      // because this is the part you are meant to grab.
      s.g.fillStyle = cutDrag && cutDrag.at_i === i2 ? k.accent : k.text;
      s.g.fillRect(bx - 1.5, rail0 + 3, 3, CUT_RAIL - 6);
      s.g.beginPath();
      s.g.moveTo(bx - 5, rail0 + 3);
      s.g.lineTo(bx + 5, rail0 + 3);
      s.g.lineTo(bx, rail0 + 9);
      s.g.closePath();
      s.g.fill();
      s.g.font = '10px system-ui, sans-serif';
      s.g.fillText(b.toFixed(3), bx + 7, rail0 + 13);
    });

    /* Jittered by INDEX, not at random: the same event lands in the same
       place on every redraw, so stepping through them does not make the
       cloud shuffle under the pointer. */
    const seen = {};
    const geom = { evs: [], X: null, Y: null };
    for (const e of evs) {
      const key = e.pc1.toFixed(4);
      const n = (seen[key] = (seen[key] || 0) + 1);
      const y = y0 + ph * (0.5 + 0.34 * Math.sin(n * 2.399963));
      const x = X(e.pc1);
      s.g.beginPath();
      s.g.arc(x, y, 4.2, 0, 6.2832);
      s.g.fillStyle = colorOf(e.type);
      s.g.fill();
      s.g.strokeStyle = k.bg;
      s.g.lineWidth = 0.8;
      s.g.stroke();
      geom.evs.push({ i: e.i, x, y, pc1: e.pc1, pc2: 0 });
      if (picked != null && e.i === picked) {
        s.g.beginPath();
        s.g.arc(x, y, 8.5, 0, 6.2832);
        s.g.strokeStyle = k.text;
        s.g.lineWidth = 1.8;
        s.g.stroke();
      }
    }
    // Clicking uses the same geometry the scatter does, in the same
    // shape, so `onScatterClick` needs to know nothing about this.
    GEOM.scatter = {
      evs: geom.evs.map((g) => ({ i: g.i, pc1: g.pc1, pc2: g.pc2 })),
      X: (v) => X(v), Y: () => 0,
      pick: geom.evs,
      // A pixel back to a gap value, for placing the cut by hand.
      axis: (px) => Math.max(0, Math.min(1, (px - x0) / pw)),
      // Where the cut's strip is, so a press can tell the two apart.
      rail: { y0: rail0, y1: rail0 + CUT_RAIL, x0, pw },
    };
    s.g.fillStyle = k.dim;
    s.g.font = '9px system-ui, sans-serif';
    s.g.fillText('0  sinks adjacent', x0 + 2, s.h - 5);
    s.g.textAlign = 'right';
    s.g.fillText('full band  1', x0 + pw - 2, s.h - 5);
    s.g.textAlign = 'left';
  }

  /* THE TWO SINKS, AND THE GAP BETWEEN THEM.

     One function, used by every panel that shows it, because the whole
     claim of the measure is that the pair on screen is the pair the
     number came from. Drawn as two ticks and a bracket at a fixed
     horizontal place, so it sits clear of the data and lines up with the
     contacts vertically however the panel is scaled.

     `Y` maps a contact number to a pixel, which is the only thing that
     differs between the profile, the raster and the class means. */
  function drawGap(s, k, mark, Y, x, col, label) {
    if (!mark || !mark.csc || mark.csc.length !== 2) return;
    const [c1, c2] = mark.csc;
    const y1 = Y(c1), y2 = Y(c2);
    s.g.strokeStyle = col;
    s.g.lineWidth = 2.4;
    for (const y of [y1, y2]) {
      s.g.beginPath();
      s.g.moveTo(x - 5, y);
      s.g.lineTo(x + 5, y);
      s.g.stroke();
    }
    if (c1 !== c2) {
      s.g.lineWidth = 1.8;
      s.g.beginPath();
      s.g.moveTo(x, y1);
      s.g.lineTo(x, y2);
      s.g.stroke();
    }
    if (label) {
      /* Nudged off the bracket, and staggered by WHICH bracket it is:
         two classes whose sinks sit at similar depths put their labels
         on the same line and printed one over the other. */
      s.g.fillStyle = col;
      s.g.font = '9px system-ui, sans-serif';
      s.g.textAlign = 'left';
      s.g.fillText('Δ ' + mark.contacts + ' → '
                   + (mark.value != null ? mark.value.toFixed(2) : '?'),
                   x + 7, (y1 + y2) / 2 + 3 + (label === 2 ? 11 : 0));
    }
  }

  /* The pair for ONE event, as contact numbers. `gap.rows` indexes the
     selected band; the panels are drawn on the whole shank. */
  function gapOf(i) {
    const g = (fit && fit.ok && fit.gap) || null;
    if (!g || i == null) return null;
    const at = (fit.events || []).findIndex((e) => e.i === i);
    if (at < 0 || !(g.rows || [])[at]) return null;
    const rows = g.rows[at];
    const ns = fit.contacts || [];
    if (ns[rows[0]] == null || ns[rows[1]] == null) return null;
    return { rows, csc: [ns[rows[0]], ns[rows[1]]],
             contacts: (g.contacts || [])[at],
             value: (g.values || [])[at] };
  }

  function drawScatter() {
    const s = sized('dpScatter', 268, true);
    if (!s || !fit || !fit.ok) return;
    const k = ink();
    // A line, not a plane: `delta` has one coordinate per event.
    if (isDelta()) { drawDeltaSpace(s, k); return; }
    const evs = fit.events || [];
    if (!evs.length) return;
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const e of evs) {
      x0 = Math.min(x0, e.pc1); x1 = Math.max(x1, e.pc1);
      y0 = Math.min(y0, e.pc2); y1 = Math.max(y1, e.pc2);
    }
    const px = (x1 - x0) * 0.08 || 1, py = (y1 - y0) * 0.08 || 1;
    x0 -= px; x1 += px; y0 -= py; y1 += py;
    const X = (v) => PAD.l + ((v - x0) / (x1 - x0)) * (s.w - PAD.l - PAD.r);
    const Y = (v) => s.h - PAD.b - ((v - y0) / (y1 - y0)) * (s.h - PAD.t - PAD.b);

    s.g.strokeStyle = k.line;
    s.g.strokeRect(PAD.l, PAD.t, s.w - PAD.l - PAD.r, s.h - PAD.t - PAD.b);
    GEOM.scatter = { X, Y, evs, x0, x1, y0, y1, s };
    for (const e of evs) {
      s.g.beginPath();
      s.g.arc(X(e.pc1), Y(e.pc2), 4.2, 0, 6.2832);
      s.g.fillStyle = colorOf(e.type);
      s.g.fill();
      s.g.strokeStyle = '#ffffff';
      s.g.lineWidth = 0.8;
      s.g.stroke();
    }
    if (picked != null) {
      const e = evs.find((v) => v.i === picked) || evs[picked];
      if (e) {
        s.g.beginPath();
        s.g.arc(X(e.pc1), Y(e.pc2), 8.5, 0, 6.2832);
        s.g.strokeStyle = k.text;
        s.g.lineWidth = 1.8;
        s.g.stroke();
      }
    }
    s.g.fillStyle = k.dim;
    s.g.font = '9px system-ui, sans-serif';
    s.g.fillText('PC1', s.w - PAD.r - 20, s.h - 5);
    s.g.save();
    s.g.translate(10, PAD.t + 20);
    s.g.rotate(-Math.PI / 2);
    s.g.fillText('PC2', 0, 0);
    s.g.restore();
  }

  /* The panel that says whether the box is in the right place.

     Two curves differing in SHAPE -- sinks at different depths -- are two
     kinds of event. Two of the same shape at different heights are one kind,
     loud and quiet, which is a badly placed box sorting events by
     amplitude. */
  function drawProfile() {
    const s = sized('dpProfile', 322, true);
    if (!s || !fit || !fit.ok) return;
    const k = ink();
    const ps = (fit.profiles || []).filter((p) => p.n);
    if (!ps.length) return;
    const ns = ps[0].contacts;
    let lo = Infinity, hi = -Infinity;
    for (const p of ps) {
      for (let i = 0; i < p.mean.length; i++) {
        lo = Math.min(lo, p.mean[i] - p.sem[i]);
        hi = Math.max(hi, p.mean[i] + p.sem[i]);
      }
    }
    const pad = (hi - lo) * 0.08 || 1;
    lo -= pad; hi += pad;
    const X = (v) => PAD.l + ((v - lo) / (hi - lo)) * (s.w - PAD.l - PAD.r);
    const Y = (n) => PAD.t + ((n - (ns[0] - 0.5))
                              / ((ns[ns.length - 1] + 0.5) - (ns[0] - 0.5)))
                             * (s.h - PAD.t - PAD.b);
    s.g.strokeStyle = k.line;
    s.g.strokeRect(PAD.l, PAD.t, s.w - PAD.l - PAD.r, s.h - PAD.t - PAD.b);

    /* The curve runs down the whole shank; the FEATURES came from part of
       it. Shaded rather than cropped: a picture of only the inside of the
       box cannot answer the question people bring to it, which is whether
       the box is in the right place. The band is left bright and the rest
       is dimmed, so the measurement is still the thing your eye goes to. */
    const bd = ps[0].band;
    if (bd && bd.length === 2) {
      const yA = Y(bd[0] - 0.5), yB = Y(bd[1] + 0.5);
      s.g.fillStyle = k.bg;
      s.g.globalAlpha = 0.55;
      s.g.fillRect(PAD.l, PAD.t, s.w - PAD.l - PAD.r, yA - PAD.t);
      s.g.fillRect(PAD.l, yB, s.w - PAD.l - PAD.r, s.h - PAD.b - yB);
      s.g.globalAlpha = 1;
      s.g.strokeStyle = k.accent;
      s.g.lineWidth = 1;
      s.g.setLineDash([2, 2]);
      for (const y of [yA, yB]) {
        s.g.beginPath();
        s.g.moveTo(PAD.l, y); s.g.lineTo(s.w - PAD.r, y);
        s.g.stroke();
      }
      s.g.setLineDash([]);
    }

    // Zero: the line between a sink and a source.
    s.g.strokeStyle = k.dim;
    s.g.setLineDash([3, 3]);
    s.g.beginPath();
    s.g.moveTo(X(0), PAD.t); s.g.lineTo(X(0), s.h - PAD.b);
    s.g.stroke(); s.g.setLineDash([]);

    /* The class of the spike on screen, brought forward.

       Stepping through spikes one at a time is the check that separates a
       type from a line drawn through a cloud, and the question at each
       step is "which of these two is this one". The PCA rings the dot;
       without the same thing here the answer was on one panel only. */
    const pc = pickedClass();
    for (const p of ps) {
      const col = colorOf(p.c);
      const off = pc != null && p.c !== pc;
      s.g.fillStyle = col;
      s.g.globalAlpha = off ? 0.05 : 0.18;
      s.g.beginPath();
      for (let i = 0; i < ns.length; i++) {
        const x = X(p.mean[i] - p.sem[i]);
        if (i) s.g.lineTo(x, Y(ns[i])); else s.g.moveTo(x, Y(ns[i]));
      }
      for (let i = ns.length - 1; i >= 0; i--) {
        s.g.lineTo(X(p.mean[i] + p.sem[i]), Y(ns[i]));
      }
      s.g.closePath(); s.g.fill();
      s.g.globalAlpha = off ? 0.3 : 1;
      s.g.strokeStyle = col;
      s.g.lineWidth = off ? 1.1 : 2.6;
      s.g.beginPath();
      for (let i = 0; i < ns.length; i++) {
        const x = X(p.mean[i]);
        if (i) s.g.lineTo(x, Y(ns[i])); else s.g.moveTo(x, Y(ns[i]));
      }
      s.g.stroke();
      // The point the ACTIVE rule used, marked. Without it the legend
      // asserts a landmark and the curve beside it has three.
      /* By CONTACT NUMBER, not by row.

         `row` indexes the selected band, which is what the rule was
         scored on; this curve now runs down the whole shank, so the same
         index points at a different contact. `csc` is the number and
         means the same thing in both. */
      const d = (fit.decide || []).find((x) => x.c === p.c);
      const di = d && d.csc != null ? ns.indexOf(d.csc) : -1;
      s.g.globalAlpha = 1;
      if (di >= 0) {
        s.g.beginPath();
        s.g.arc(X(p.mean[di]), Y(ns[di]), 4.5, 0, 6.2832);
        s.g.fillStyle = col; s.g.fill();
        s.g.strokeStyle = '#fff'; s.g.lineWidth = 1.4; s.g.stroke();
      }
    }

    /* THE DELTA, on the curve it was measured from.

       Per class when the average is showing, and for the one event when
       a spike is picked -- the same pair the feature vector holds for
       whatever is on screen. Placed left of the curves so it never sits
       on top of them. */
    if (picked == null) {
      ps.forEach((p, idx) => {
        drawGap(s, k, p.sinks, (n) => Y(n), PAD.l + 10 + idx * 13,
                colorOf(p.c), ps.length <= 2 ? (idx + 1) : 0);
      });
    } else {
      const one_ = gapOf(picked);
      if (one_) {
        drawGap(s, k, one_, (n) => Y(n), PAD.l + 10,
                colorOf(pickedClass() || 1), true);
      }
    }

    axesDepth(s, k, ns[0], ns[ns.length - 1], ns[0] - 0.5,
              ns[ns.length - 1] + 0.5);
    layerLines(s, k, ns[0] - 0.5, ns[ns.length - 1] + 0.5);
    depthAt('dpProfile', s, ns[0] - 0.5, ns[ns.length - 1] + 0.5);
    drawGuides(s, 'dpProfile');
  }

  /* The class means, side by side and on ONE colour scale.

     Two heatmaps with independent scales say nothing about which event is
     larger, and "DS2 is the big one" is a claim people make off exactly this
     picture. */
  function drawClasses() {
    const s = sized('dpClasses', 236);
    const d = pics.classes;
    if (!s || !d || !d.ok) return;
    const k = ink();
    const cs = (d.classes || []).filter((c) => c.image);
    if (!cs.length) return;
    const gap = 8;
    const each = (s.w - PAD.l - PAD.r - gap * (cs.length - 1)) / cs.length;
    cs.forEach((c, i) => {
      const x0 = PAD.l + i * (each + gap);
      const img = imageFor('cls' + c.c, c.image, drawClasses);
      const ph = s.h - PAD.t - PAD.b;
      if (img) s.g.drawImage(img, x0, PAD.t, each, ph);

      /* The panel is the whole shank; the FEATURES came from a band of
         it. Dimmed rather than cropped, for the same reason as the depth
         profile beside it: cropping makes the picture agree with the
         measurement and useless for deciding whether the band is in the
         right place. */
      if (c.band && c.band.length === 2) {
        const span = (c.hi + 0.5) - (c.lo - 0.5);
        const yOf = (n) => PAD.t + ((n - (c.lo - 0.5)) / span) * ph;
        const yA = yOf(c.band[0] - 0.5), yB = yOf(c.band[1] + 0.5);
        s.g.fillStyle = k.bg;
        s.g.globalAlpha = 0.5;
        s.g.fillRect(x0, PAD.t, each, yA - PAD.t);
        s.g.fillRect(x0, yB, each, PAD.t + ph - yB);
        s.g.globalAlpha = 1;
      }
      // The class of the spike on screen, outlined rather than merely
      // bordered like the others.
      const isPicked = pickedClass() === c.c;
      s.g.strokeStyle = colorOf(c.c);
      s.g.lineWidth = isPicked ? 3 : 1.5;
      s.g.strokeRect(x0, PAD.t, each, ph);
      // Where the feature box sits inside the surround.
      const a = x0 + frac(c.box_ms[0], c.extent) * each;
      const b = x0 + frac(c.box_ms[1], c.extent) * each;
      s.g.strokeStyle = k.accent;
      s.g.lineWidth = 1.1;
      let yTop = PAD.t, yBot = PAD.t + ph;
      if (c.band && c.band.length === 2) {
        const span = (c.hi + 0.5) - (c.lo - 0.5);
        const yOf = (n) => PAD.t + ((n - (c.lo - 0.5)) / span) * ph;
        yTop = yOf(c.band[0] - 0.5); yBot = yOf(c.band[1] + 0.5);
      }
      // The box, closed on all four sides now that there is shank above
      // and below it: two vertical rules on a full-depth panel would say
      // the features came from the whole of it.
      s.g.strokeRect(a, yTop, Math.max(1.5, b - a), yBot - yTop);
      s.g.fillStyle = colorOf(c.c);
      s.g.font = '10px system-ui, sans-serif';
      s.g.fillText('DS' + c.c + '  n=' + c.n, x0 + 2, s.h - 5);
      /* EACH PANEL SAYS WHAT ITS OWN SCALE IS.

         They are scaled to themselves now, so a class with a quarter of
         the amplitude fills its panel as completely as the loud one --
         which is the point, because the shape is the question. It also
         means the colours no longer compare, and somebody will read "DS2
         is the big one" off two panels that say no such thing. The peak
         is printed so that comparison is a number, which the pictures
         can actually support. */
      if (c.peak != null) {
        s.g.fillStyle = k.dim;
        s.g.font = '9px system-ui, sans-serif';
        s.g.textAlign = 'right';
        s.g.fillText('±' + fmtPeak(c.peak), x0 + each - 2, s.h - 5);
        s.g.textAlign = 'left';
      }
    });
    s.g.fillStyle = k.dim;
    s.g.font = '9px system-ui, sans-serif';
    s.g.textAlign = 'right';
    s.g.fillText('CSC' + cs[0].lo, PAD.l - 4, PAD.t + 8);
    s.g.fillText('CSC' + cs[0].hi, PAD.l - 4, s.h - PAD.b - 2);
    s.g.textAlign = 'left';
    // One mapping for the whole canvas: every class covers the same
    // contacts, side by side, so a guide runs across all of them at one
    // height -- which is what makes them comparable at a glance.
    depthAt('dpClasses', s, cs[0].lo - 0.5, cs[0].hi + 0.5);
    layerLines(s, k, cs[0].lo - 0.5, cs[0].hi + 0.5);
    drawGuides(s, 'dpClasses');
  }

  /* The feature matrix: features down, events across, grouped by class.

     The groups are ruled AND named. A white line between two blocks says
     "these are two groups"; it does not say which one is DS1, and that is
     the only question anybody brings to this picture. */
  function drawFeatures() {
    const s = sized('dpFeat', 210, true);
    const d = pics.features;
    if (!s || !d || !d.ok) return;
    const k = ink();
    const x0 = PAD.l, y0 = PAD.t;
    const pw = s.w - PAD.l - PAD.r, ph = s.h - PAD.t - PAD.b - 10;
    /* NEAREST NEIGHBOUR, not the browser's default smoothing.

       This bitmap is one pixel per event across and one per feature
       down -- about 37 by 48 on a small set -- shown five hundred pixels
       wide. Smoothed, each event is blended into the two beside it, and
       what arrives is a soft wash: that is the blur.

       It is also wrong rather than merely soft. A column here is ONE
       EVENT and a row is ONE FEATURE; neither is a sample of something
       continuous, so there is nothing in between two of them to
       interpolate. The whole reason this panel exists is that a single
       bad column shows up on it -- a dead contact as a stripe, one odd
       event as a line -- and smoothing is precisely the operation that
       blends a single odd column into its neighbours until it is not
       visible. The CSD rasters are left smoothed because a field
       sampled at contacts really does have something in between.

       Restored afterwards: the context is shared with everything else
       drawn on this canvas. */
    /* Set and LEFT set. Nothing else drawn on this canvas is an image --
       the rest is strokes, fills and text, which the flag does not touch
       -- so restoring it afterwards changed nothing except to make the
       state unreadable from outside, which is how the harness checks
       it. */
    s.g.imageSmoothingEnabled = false;
    const img = imageFor('feat', d.image, drawFeatures);
    if (img) s.g.drawImage(img, x0, y0, pw, ph);
    s.g.strokeStyle = k.line;
    s.g.lineWidth = 1;
    s.g.strokeRect(x0, y0, pw, ph);

    const total = Math.max(1, d.n_events);
    const at = (n) => x0 + (n / total) * pw;
    for (const g of (d.groups || [])) {
      if (!g.n) continue;
      if (g.x1 < total) {
        s.g.strokeStyle = k.bg;
        s.g.lineWidth = 1.6;
        s.g.beginPath();
        s.g.moveTo(at(g.x1), y0);
        s.g.lineTo(at(g.x1), y0 + ph);
        s.g.stroke();
      }
      const a = at(g.x0), b = at(g.x1);
      s.g.fillStyle = colorOf(g.c);
      s.g.fillRect(a, y0 + ph + 2, Math.max(1, b - a), 3);
      s.g.font = '10px system-ui, sans-serif';
      const tag = 'DS' + g.c + '  n=' + g.n;
      if (b - a > s.g.measureText(tag).width + 6) {
        s.g.fillText(tag, a + 3, s.h - 2);
      }
    }
    /* THE DELTA FOR EVERY EVENT, as one thin line across the sheet.

       The columns here are the events in class order, so the gap can be
       drawn straight over them: a line that steps up where the sinks are
       far apart and down where they are close. Under `delta` that line
       IS the feature vector, and the class boundaries below should line
       up with the steps in it -- which is the whole claim of the method,
       visible rather than asserted.

       Thin, and over the top: it is an annotation on the matrix, not a
       second panel. */
    const gv = (fit && fit.ok && fit.gap && fit.gap.values) || null;
    if (gv && gv.length && (d.groups || []).length) {
      const order = [];
      for (const g of d.groups) {
        const cls = g.c;
        (fit.events || []).forEach((e, at) => {
          if (e.type === cls) order.push(gv[at]);
        });
      }
      if (order.length === d.n_events) {
        const yOf = (v) => y0 + ph - 2 - Math.max(0, Math.min(1, v))
                           * (ph - 4);
        s.g.strokeStyle = k.text;
        s.g.lineWidth = 1.2;
        s.g.globalAlpha = 0.85;
        s.g.beginPath();
        order.forEach((v, j) => {
          const x = x0 + ((j + 0.5) / d.n_events) * pw;
          if (j) s.g.lineTo(x, yOf(v)); else s.g.moveTo(x, yOf(v));
        });
        s.g.stroke();
        s.g.globalAlpha = 1;
        s.g.fillStyle = k.text;
        s.g.font = '9px system-ui, sans-serif';
        s.g.fillText('\u0394 0\u20131', x0 + 3, yOf(1) + 8);
      }
    }

    s.g.fillStyle = k.dim;
    s.g.font = '9px system-ui, sans-serif';
    s.g.textAlign = 'right';
    s.g.fillText('feature', PAD.l - 4, y0 + 8);
    s.g.fillText(String(d.n_features), PAD.l - 4, y0 + ph - 1);
    s.g.textAlign = 'left';
  }


  /* ==================================================================
     Under the hood

     Everything else in this tool draws an ANSWER. A picture cannot be
     checked: "DS1 is the shallower one" and "this event is DS2" are
     claims, and the only way to test a claim is to follow the arithmetic
     that produced it. This is that arithmetic for one event, in the order
     it is computed, with the numbers rather than a description of them.

     WHY NOT A NETWORK. It was asked. PCA is a linear rotation -- the
     "weights" are a matrix that exists, can be printed, and can be
     reshaped back into a depth-by-time picture of what the component
     measures. A network would replace a method whose workings can be
     read with one whose workings cannot, to answer a question that is
     already answerable; and with tens to hundreds of events there is
     nothing to train it on anyway. The honest under-the-hood view of a
     linear method is the linear algebra, shown.

     Four things here are not visible anywhere else in the panel:

       * the PCA sees a FLATTENED patch, so feature 37 is (contact 5,
         sample 2) and not a depth or a time;
       * the mean is subtracted first, so a loading weights a DEVIATION
         from the average event, not a value;
       * k-means runs on the two PCA coordinates, so everything past PC2
         is computed and thrown away before anything is clustered;
       * the class NUMBER comes last, from a landmark depth, and is not
         what k-means returned.
     ================================================================== */
  let hood = null;              // the last answer, for the open panel
  let hoodFor = null;           // which event it is about
  let hoodBusy = false;
  let hoodPC = 0;               // which component the maps are showing

  async function openHood() {
    if (!fit || !fit.ok || hoodBusy) return;
    const evs = fit.events || [];
    if (!evs.length) return;
    const want = picked == null ? evs[0].i : picked;
    hoodBusy = true;
    try {
      hood = await apiPost('/api/dspca/underhood',
                           fitBody({ index: want }));
      hoodFor = want;
    } catch (e) {
      toast(e.message, 'err', 10000);
      hoodBusy = false;
      return;
    }
    hoodBusy = false;
    showHood();
    BARRY.activity.log('dspca.underhood', { gid: q.gid, event: want });
  }

  const f3 = (v) => (v == null || !isFinite(v) ? '—'
                     : Math.abs(v) >= 100 ? v.toFixed(0)
                     : Math.abs(v) >= 1 ? v.toFixed(2)
                     : Math.abs(v) >= 0.001 ? v.toFixed(4)
                     : v.toExponential(1));

  function showHood() {
    const h = hood;
    if (!h || !h.ok) return;
    const wrap = el('div', { class: 'modal big dp-hood' });

    wrap.appendChild(el('div', { class: 'mh' }, [
      el('h3', { text: 'Under the hood' }),
      el('span', { class: 'sub', text:
        'spike ' + (h.event + 1) + ' of ' + h.n_events + ', and every '
        + 'number between its CSD patch and DS' + h.type }),
      el('span', { class: 'spacer' }),
      el('button', {
        class: 'btn ghost sm', text: '◀ prev',
        onclick: () => hoodStep(-1),
      }),
      el('button', {
        class: 'btn ghost sm', text: 'next ▶',
        onclick: () => hoodStep(+1),
      }),
      el('button', { class: 'btn ghost sm', text: 'Close',
                     onclick: closeModal }),
    ]));

    const b = el('div', { class: 'mb dp-hood-body' });

    /* ---- the shape of the thing, first, because everything below is
       an index into it ---- */
    b.appendChild(stage(1, 'The patch', h.shape.contacts + ' contacts × '
      + h.shape.samples + ' sample' + (h.shape.samples === 1 ? '' : 's')
      + ' = ' + h.n_features + ' features',
      'CSC' + h.contacts[0] + '–' + h.contacts[h.contacts.length - 1]
      + ', ' + fmtMs(h.times_ms[0]) + ' to '
      + fmtMs(h.times_ms[h.times_ms.length - 1])
      + '. These are the CSD values themselves, broadband — the rasters '
      + 'are band-limited for legibility and the features are not. Every '
      + 'number below comes from this grid.'));
    b.appendChild(grid(h, h.raw, 'raw'));

    /* ---- what the normalisation did ---- */
    b.appendChild(stage(2, 'Normalised', h.features_mode_name,
      h.features_mode === 'minmax'
        ? 'Scaled to 0–1 over the whole patch, one min and one max for '
          + 'all of it. Toothy’s own features.'
        : h.features_mode === 'sign'
          ? 'Every value replaced by its sign. The magnitudes are gone, '
            + 'so what is left is the laminar pattern and nothing else.'
          : 'Sign, with everything within ' + (100 * h.dead).toFixed(0)
            + '% of this patch’s own peak counted as neither.'));
    b.appendChild(grid(h, h.norm, 'norm'));

    /* ---- the flattening, which is where the index comes from ---- */
    b.appendChild(stage(3, 'Flattened', 'feature f = row × '
      + h.shape.samples + ' + column',
      'The PCA sees one row of ' + h.n_features + ' numbers, not a grid. '
      + 'Hover any cell above: it names the feature index it becomes.'));

    /* ---- the components ---- */
    const ex = h.explained || [];
    b.appendChild(stage(4, 'The components',
      'PC1 ' + pct(ex[0]) + ' · PC2 ' + pct(ex[1]),
      'A component is one weight per feature, so it has the shape of the '
      + 'patch and can be drawn as one. Red is a feature this component '
      + 'adds, blue one it subtracts. The mean event is subtracted first, '
      + 'so a weight acts on the DEVIATION from average, not the value.'));
    b.appendChild(el('div', { class: 'dp-hood-seg' }, [
      el('div', { class: 'seg' }, [[0, 'PC1'], [1, 'PC2']].map(
        ([i2, lab]) => el('button', {
          class: hoodPC === i2 ? 'active' : '',
          text: lab,
          onclick: () => { hoodPC = i2; repaintHood(); },
        }))),
      el('span', { class: 'hint', text:
        'weights for the component, laid back out over the patch' }),
    ]));
    b.appendChild(grid(h, compGrid(h, hoodPC), 'w'));

    /* ---- the multiply, with the biggest terms named ---- */
    const sc = h.score || [], rc = h.score_recomputed || [];
    b.appendChild(stage(5, 'The score',
      'PC' + (hoodPC + 1) + ' = ' + f3(sc[hoodPC]),
      'The sum over every feature of (value − mean) × weight. Recomputed '
      + 'here from the parts as a check: ' + f3(rc[hoodPC])
      + (Math.abs((rc[hoodPC] || 0) - (sc[hoodPC] || 0)) < 1e-6
         ? ' — agrees.'
         : ' — DOES NOT AGREE with the transform, which is a fault.')));
    b.appendChild(terms(h, hoodPC));

    /* ---- what was thrown away ---- */
    b.appendChild(stage(6, 'What is not used',
      (h.scree || []).length + ' components computed',
      'K-means runs on ' + h.km.on + '. Every component past the second '
      + 'is computed and then discarded before anything is clustered, so '
      + 'the bars past PC2 are variance the classification never saw.'));
    b.appendChild(scree(h));

    /* ---- the cluster step ---- */
    b.appendChild(stage(7, 'The cluster',
      'k-means, ' + h.k + ' clusters',
      'In the PC1–PC2 plane, not in feature space. This event went to the '
      + 'nearest centre.'));
    b.appendChild(centres(h));

    /* ---- and the renaming, which is the part people assume ---- */
    const dec = (h.decide || []).find((d) => d.c === h.type) || {};
    b.appendChild(stage(8, 'The name',
      'cluster ' + (h.km.label == null ? '?' : h.km.label)
      + ' → DS' + h.type,
      'The number is NOT what k-means returned. Clusters are renumbered '
      + 'by the depth of the landmark each one’s mean profile has, so DS1 '
      + 'is always the shallower — which is why DS1 before and after a '
      + 'refit need not hold the same events. Rule in force: '
      + (RULE_NAME[h.rule] || h.rule)
      + (h.flip ? ', flipped by hand' : '')
      + (dec.csc != null ? '. This class’s landmark is CSC' + dec.csc + '.'
                         : '.')));

    wrap.appendChild(b);
    wrap.appendChild(el('div', { class: 'mf' }, [
      el('span', { class: 'hint', text:
        'Every figure in the panel is drawn from these numbers.' }),
      el('span', { class: 'spacer' }),
      el('button', { class: 'btn ghost sm', text: 'Show this spike',
        onclick: () => {
          picked = hoodFor;
          closeModal();
          render();
          pictures(['traces', 'pane']);
          pushXray();
        } }),
      el('button', { class: 'btn sm', text: 'Done', onclick: closeModal }),
    ]));
    showModal(wrap, { replace: true });
  }

  function repaintHood() {
    const open = document.querySelector('.dp-hood');
    if (!open) return;
    showHood();
  }

  async function hoodStep(d) {
    if (!fit || !fit.ok) return;
    const evs = fit.events || [];
    if (!evs.length) return;
    const at = evs.findIndex((e) => e.i === hoodFor);
    const next = ((at + d) % evs.length + evs.length) % evs.length;
    const want = evs[next].i;
    try {
      hood = await apiPost('/api/dspca/underhood', fitBody({ index: want }));
      hoodFor = want;
    } catch (e) {
      toast(e.message, 'err', 9000);
      return;
    }
    showHood();
  }

  function stage(n, title, chip, why) {
    return el('div', { class: 'dp-hood-stage' }, [
      el('div', { class: 'dp-hood-head' }, [
        el('span', { class: 'dp-hood-n', text: String(n) }),
        el('strong', { text: title }),
        chip ? el('span', { class: 'dp-chip', text: chip }) : null,
      ].filter(Boolean)),
      why ? el('p', { class: 'hint', text: why }) : null,
    ].filter(Boolean));
  }

  /* One component, laid back out over the patch. */
  function compGrid(h, c) {
    const w = (h.components || [])[c] || [];
    const nt = h.shape.samples;
    const out = [];
    for (let r = 0; r < h.shape.contacts; r++) {
      const row = [];
      for (let j = 0; j < nt; j++) row.push(w[r * nt + j]);
      out.push(row);
    }
    return out;
  }

  /* THE NUMBERS, as numbers.

     A heatmap of twenty-five values is a picture of something small
     enough to read, and reading it is the point: this is the panel
     somebody opens to check a figure against the arithmetic. Coloured as
     well, so the shape is still visible, and every cell says which
     feature index it is -- which is the whole of tracing a dot on the
     scatter back to a contact and a millisecond. */
  function grid(h, rows, kind) {
    const nt = h.shape.samples;
    let lo = Infinity, hi = -Infinity;
    for (const r of rows) for (const v of r) {
      if (v == null || !isFinite(v)) continue;
      lo = Math.min(lo, v); hi = Math.max(hi, v);
    }
    const span = Math.max(Math.abs(lo), Math.abs(hi)) || 1;
    const box = el('div', { class: 'dp-hood-gridwrap' });
    const tab = el('table', { class: 'dp-hood-grid' });
    const head = [el('th', { class: 'corner', text: kind === 'w' ? 'w' : '' })];
    for (let j = 0; j < nt; j++) {
      head.push(el('th', { text: fmtMs(h.times_ms[j]) }));
    }
    tab.appendChild(el('thead', {}, [el('tr', {}, head)]));
    const body = [];
    for (let r = 0; r < rows.length; r++) {
      const tds = [el('th', { text: 'CSC' + h.contacts[r] })];
      for (let j = 0; j < nt; j++) {
        const v = rows[r][j];
        const f = r * nt + j;
        // Diverging for anything signed, one-sided for min-max.
        const t = span ? v / span : 0;
        const bg = kind === 'norm' && h.features_mode === 'minmax'
          ? 'rgba(127,127,127,' + Math.max(0, Math.min(1, v)).toFixed(3) + ')'
          : (t >= 0
             ? 'color-mix(in srgb, var(--err) ' + (100 * Math.min(1, t)).toFixed(0) + '%, transparent)'
             : 'color-mix(in srgb, var(--accent) ' + (100 * Math.min(1, -t)).toFixed(0) + '%, transparent)');
        tds.push(el('td', {
          class: 'dp-hood-cell',
          style: 'background:' + bg,
          title: 'feature ' + f + '  ·  CSC' + h.contacts[r] + '  ·  '
               + fmtMs(h.times_ms[j]) + '  ·  ' + f3(v),
          text: f3(v),
        }));
      }
      body.push(el('tr', {}, tds));
    }
    tab.appendChild(el('tbody', {}, body));
    box.appendChild(tab);
    return box;
  }

  /* The dozen features that actually moved the score. */
  function terms(h, c) {
    const rows = ((h.top || {})[c === 0 ? 'pc1' : 'pc2']) || [];
    if (!rows.length) return el('div', {});
    const box = el('div', { class: 'dp-hood-gridwrap' });
    box.appendChild(el('table', { class: 'tbl dp-hood-terms' }, [
      el('thead', {}, [el('tr', {}, ['feature', 'where', 'value', 'mean',
                                     'deviation', 'weight', 'contribution']
        .map((t) => el('th', { text: t })))]),
      el('tbody', {}, rows.map((r) => el('tr', {}, [
        el('td', { text: String(r.f) }),
        el('td', { text: 'CSC' + r.csc + '  ' + fmtMs(r.t_ms) }),
        el('td', { text: f3(r.x) }),
        el('td', { text: f3(r.mean) }),
        el('td', { text: f3(r.dev) }),
        el('td', { text: f3(r.w) }),
        el('td', { class: r.contrib >= 0 ? 'pos' : 'neg',
                   text: f3(r.contrib) }),
      ]))),
    ]));
    return box;
  }

  function scree(h) {
    const vals = h.scree && h.scree.length ? h.scree : (h.explained || []);
    const box = el('div', { class: 'dp-hood-scree' });
    vals.forEach((v, i) => {
      box.appendChild(el('div', {
        class: 'dp-hood-bar' + (i < 2 ? ' used' : ''),
        title: 'PC' + (i + 1) + '  ' + pct(v)
             + (i < 2 ? '  (clustered on)' : '  (computed, then discarded)'),
      }, [
        el('i', { style: 'height:' + (100 * Math.min(1, v / (vals[0] || 1)))
                         .toFixed(1) + '%' }),
        el('span', { class: 'hint', text: 'PC' + (i + 1) }),
        el('span', { class: 'hint', text: pct(v) }),
      ]));
    });
    return box;
  }

  function centres(h) {
    const d = h.km.distances || [];
    const sorted = d.slice().sort((a, b2) => a - b2);
    const margin = d.length > 1 ? sorted[1] - sorted[0] : null;
    return el('div', { class: 'dp-hood-gridwrap' }, [
      el('table', { class: 'tbl dp-hood-terms' }, [
        el('thead', {}, [el('tr', {}, ['cluster', 'centre (PC1, PC2)',
                                       'distance', '']
          .map((t) => el('th', { text: t })))]),
        el('tbody', {}, (h.km.centres || []).map((c, i) => el('tr', {
          class: i === h.km.label ? 'on' : null,
        }, [
          el('td', { text: String(i) }),
          el('td', { text: f3(c[0]) + ',  ' + f3(c[1]) }),
          el('td', { text: f3(d[i]) }),
          el('td', { text: i === h.km.label ? 'nearest' : '' }),
        ]))),
      ]),
      el('p', { class: 'hint', text: margin == null ? ''
        : 'This event sits ' + f3(margin) + ' further from the next centre '
          + 'than from its own. A small margin is an event the split is '
          + 'not confident about, whatever the colour of its dot.' }),
    ]);
  }

  /* ==================================================================
     Interaction
     ================================================================== */
  /* A guide first, then the box.

     Both live on the CSD raster and both start with a press, so one of them
     has to win. The guide does, within a few pixels of the line: a box can
     be drawn anywhere on a large panel and a line can only be grabbed where
     it is, so giving the box priority would make a guide on a busy raster
     almost impossible to pick up. */
  function onDown(e) {
    const id = e.target && e.target.id;
    if (!DEPTH[id] || e.button !== 0) return;
    const cv = document.getElementById(id);
    if (!cv) return;
    const r = cv.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;

    /* THE CUT'S RAIL, before anything else on this canvas.

       Only inside the rail: a press on a dot is a press on a dot. */
    if (id === 'dpScatter' && isDelta()) {
      const G = GEOM.scatter;
      const rail = G && G.rail;
      if (rail && y >= rail.y0 && y <= rail.y1) {
        const cur = (q.delta_cut || deltaBounds() || []).slice();
        const v = Math.max(0, Math.min(1, (x - rail.x0) / rail.pw));
        let idx = 0;
        if (!cur.length) { cur.push(v); }
        else {
          cur.forEach((c, i2) => {
            if (Math.abs(c - v) < Math.abs(cur[idx] - v)) idx = i2;
          });
        }
        cutDrag = { at_i: idx, at: v, base: cur };
        try { cv.setPointerCapture(e.pointerId); } catch (err) { /* fine */ }
        drawScatter();
        e.preventDefault();
        return;
      }
      // Below the rail this canvas is read-only: the click handler picks
      // the dot. Nothing to start a drag for.
      return;
    }

    const hit = guideAt(id, y);
    if (hit) {
      dragGuide = { id: hit.id, on: id, from: hit.csc, at: hit.csc };
      try { cv.setPointerCapture(e.pointerId); } catch (err) { /* fine */ }
      e.preventDefault();
      return;
    }

    // Only the raster takes a rubber band; the other three are read-only
    // pictures with a depth axis.
    if (id !== 'dpShank') return;
    const g = GEOM.shank;
    if (!g) return;
    if (x < g.x0 || x > g.x0 + g.pw || y < g.y0 || y > g.y0 + g.ph) return;
    dragging = { x, y, live: null };
    cv.setPointerCapture(e.pointerId);
    e.preventDefault();
  }

  function onMove(e) {
    if (dragGuide) {
      const g = DEPTH[dragGuide.on];
      const cv = document.getElementById(dragGuide.on);
      if (!g || !cv) return;
      const r = cv.getBoundingClientRect();
      const y = Math.max(g.y0, Math.min(g.y0 + g.h, e.clientY - r.top));
      dragGuide.at = Math.round(g.cscOf(y));
      // Every panel, not the one under the pointer. They are one line seen
      // five ways, and a drag that moved it on one of them would say
      // otherwise.
      drawAll();
      return;
    }
    if (!dragging) return;
    const cv = document.getElementById('dpShank');
    const g = GEOM.shank;
    if (!cv || !g) return;
    const r = cv.getBoundingClientRect();
    const x = Math.max(g.x0, Math.min(g.x0 + g.pw, e.clientX - r.left));
    const y = Math.max(g.y0, Math.min(g.y0 + g.ph, e.clientY - r.top));
    dragging.live = {
      x: Math.min(dragging.x, x), y: Math.min(dragging.y, y),
      w: Math.abs(x - dragging.x), h: Math.abs(y - dragging.y),
    };
    drawShank();
  }

  function onUp(e) {
    if (dragGuide) {
      const moved = dragGuide.at !== dragGuide.from;
      const id = dragGuide.id, at = dragGuide.at;
      dragGuide = null;
      // Drawn at the new place immediately; the write follows. See
      // `saveGuide` -- waiting for a round trip would make the line feel
      // tied to the pointer by a rubber band.
      if (moved) {
        const gd = guides.find((x) => x.id === id);
        if (gd) gd.csc = at;
        drawAll();
        saveGuide(at, undefined, id);
      } else {
        drawAll();
      }
      return;
    }
    if (cutDrag) {
      const cv2 = document.getElementById('dpScatter');
      const G = GEOM.scatter;
      if (cv2 && G && G.rail) {
        const r2 = cv2.getBoundingClientRect();
        cutDrag.at = Math.max(0, Math.min(
          1, (e.clientX - r2.left - G.rail.x0) / G.rail.pw));
        drawScatter();
      }
      return;
    }
    if (cutDrag) {
      /* COMMITTED ON RELEASE, not on every move. A refit is a second of
         server on a real set; one per pixel of drag would be minutes. */
      const cur = cutDrag.base.slice();
      cur[cutDrag.at_i] = cutDrag.at;
      cutDrag = null;
      q.delta_cut = cur.sort((a, b) => a - b);
      refit();
      return;
    }
    if (!dragging) return;
    const g = GEOM.shank;
    const live = dragging.live;
    dragging = null;
    if (!g || !live) { drawShank(); return; }
    const toMs = (px) => g.ext[0] + ((px - g.x0) / g.pw) * (g.ext[1] - g.ext[0]);
    const toCsc = (py) => g.lo + ((py - g.y0) / g.ph) * (g.hi - g.lo + 1) - 0.5;
    q.t_lo_ms = Math.round(toMs(live.x) * 10) / 10;
    q.t_hi_ms = Math.round(toMs(live.x + live.w) * 10) / 10;
    let lo = Math.round(toCsc(live.y));
    let hi = Math.round(toCsc(live.y + live.h));
    // A CSD is a second derivative across depth; three contacts is the
    // floor. Widened rather than refused -- a drag that lands on two is
    // somebody asking for the thinnest box there is.
    if (hi - lo < 2) hi = lo + 2;
    q.sel_lo = Math.max(g.lo, lo);
    q.sel_hi = Math.min(g.hi, hi);
    /* Set, and NOT recomputed. See `applyBar`: a fit is a second of server
       and getting a window right takes several goes. The rectangle moves
       now -- `shownBox` draws the pending one -- and the answer follows
       when it is asked for. */
    dirty = true;
    render();
  }

  /* Where the boundary goes, said with a pointer.

     The nearest existing cut moves, so with three classes the two lines
     are edited one at a time rather than replaced together. Shift-click
     still picks the event under the pointer, because looking at one
     spike is the other thing this panel is for. */
  function onCutClick(e) {
    const G = GEOM.scatter;
    const cv = document.getElementById('dpScatter');
    if (!G || !cv || !G.axis) return;
    const r = cv.getBoundingClientRect();
    const v = G.axis(e.clientX - r.left);
    if (!isFinite(v)) return;
    const dv = (fit.variants || {}).delta || {};
    const cur = (q.delta_cut || dv.bounds || []).slice();
    if (!cur.length) cur.push(v);
    else {
      let at = 0;
      cur.forEach((c, i2) => {
        if (Math.abs(c - v) < Math.abs(cur[at] - v)) at = i2;
      });
      cur[at] = v;
    }
    q.delta_cut = cur.sort((a2, b2) => a2 - b2);
    refit();
  }

  function onScatterClick(e) {
    const G = GEOM.scatter;
    const cv = document.getElementById('dpScatter');
    if (!G || !cv) return;
    const r = cv.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    let best = null, bd = 1e9;
    /* `pick` is where the dots ACTUALLY landed, which the strip plot has
       to say outright: it jitters events vertically so that ties can be
       counted, and a y computed from the coordinate would be the same
       for all of them. The scatter has no jitter and needs no list. */
    const pts = G.pick || G.evs.map((ev) => ({
      i: ev.i, x: G.X(ev.pc1), y: G.Y(ev.pc2) }));
    for (const ev of pts) {
      const dx = ev.x - x, dy = ev.y - y;
      const d = dx * dx + dy * dy;
      if (d < bd) { bd = d; best = ev; }
    }
    if (!best || bd > 18 * 18) return;
    picked = best.i;
    // Clicking a dot moves the recording window as well, when there is one.
    setTimeout(pushXray, 0);
    render();
    pictures(['traces', 'pane']);
  }

  function step(delta) {
    if (!fit || !fit.ok) return;
    const evs = fit.events || [];
    if (!evs.length) return;
    const at = picked == null ? -1 : evs.findIndex((e) => e.i === picked);
    const next = ((at + delta) % evs.length + evs.length) % evs.length;
    picked = evs[next].i;
    render();
    pictures(['traces', 'pane']);
    // The other window is looking at this spike too, if it is open.
    pushXray();
  }

  /* The real view, for when the picture here is not enough.

     Same filters, same window, and the recording itself rather than an
     average of it -- which is the one thing this panel cannot show. */
  /* ==================================================================
     The recording itself, in a window of its own
     ==================================================================
     NOT by taking over XploreFinder in this window, which is what this
     did. `setView('xplore')` replaced the panel: the box, the classes and
     the PCA were gone, and the way back was to find X-ray in the ToolKit
     again and wait for the fit. Checking one spike against the raw
     recording is something you do WHILE reading the panel, so the panel
     has to still be there.

     A second window, on the recording, which every other tool in this
     application that needs one already opens the same way -- Incisor for
     its channel lines, Braid for its panels. It is named, so pressing the
     button again focuses the one that is open rather than opening a
     third.

     And it FOLLOWS. Every spike this panel steps to is pushed into it, as
     curation marks: the same `sess.curationMarks` Checkup publishes, so
     the window draws every dentate spike in the set coloured by the class
     it was put in, with the one being looked at marked. Nothing in the
     other window had to learn about X-ray for that -- it already knows how
     to draw a curated set. */
  let xrayWin = null;

  function xrayOpen() {
    try { return !!(xrayWin && !xrayWin.closed); } catch (e) { return false; }
  }

  function xrayUrl(path, t) {
    /* A CSD over the traces, five hundred milliseconds wide.

       The CSD because that is what the classes are made of and what the
       panel is showing; the traces beside it because a sink that is only
       on the CSD is worth being suspicious of. Starting points, not a
       cage: the window is the whole application. */
    const args = new URLSearchParams({
      csc: path,
      panes: JSON.stringify([{ panel: 'csd' }, { panel: 'traces' }]),
      t0: Math.max(0, t - 0.25).toFixed(4),
      span: '0.5',
      hp: '5', lp: '100', notch: '60',
      chrome: 'notabs,noheads',
      role: 'xray',
      theme: (BARRY.state && BARRY.state.theme) || 'dark',
    });
    return location.origin + '/?' + args.toString() + '#xplore';
  }

  async function openInXplore() {
    if (picked == null || !plan || !plan.ok) return;
    const ev = (fit.events || []).find((e) => e.i === picked);
    if (!ev) return;
    const path = plan.session.path;
    if (!path) {
      toast('This set does not say which recording it came from.', 'err', 8000);
      return;
    }
    if (xrayOpen()) {
      try { xrayWin.focus(); } catch (e) { /* not important */ }
      pushXray();
      return;
    }
    xrayWin = window.open(xrayUrl(path, ev.t), 'barry-xray-traces',
                          'width=1180,height=900,menubar=no,toolbar=no');
    if (!xrayWin) {
      toast('The recording window was blocked. Allow pop-ups for 127.0.0.1, '
            + 'then press \u201cOpen in Xplorefinder\u201d again.', 'err', 9000);
      return;
    }
    render();
    /* WAITED FOR, not assumed. The window is a whole application booting,
       and it has to read the recording before it has anything to draw a
       mark on. Publishing into it early is how Incisor's lines went
       missing, and this is the same arrangement. */
    const until = Date.now() + 60000;
    while (Date.now() < until) {
      if (!xrayOpen()) { render(); return; }
      if (pushXray()) { render(); break; }
      await new Promise((r) => setTimeout(r, 250));
    }
    BARRY.activity.log('dspca.xplore', { gid: q.gid, t: ev.t, type: ev.type });
  }

  /* Every spike in the set, coloured by class, with the current one
     marked -- pushed into the other window.

     Returns whether it actually landed, so the opener above can keep
     waiting rather than believing it worked. */
  function pushXray() {
    if (!xrayOpen() || !fit || !fit.ok) return false;
    let xf = null;
    try { xf = xrayWin.barryXplore; } catch (e) { return false; }
    if (!xf || !xf.current) return false;
    let sess = null;
    try { sess = xf.current(); } catch (e) { return false; }
    if (!sess) return false;

    const evs = fit.events || [];
    const at = picked == null ? -1 : evs.findIndex((e) => e.i === picked);
    const now = at >= 0 ? evs[at] : null;
    try {
      /* The same shape Checkup publishes. `label` is the class, so the
         other window colours DS1 and DS2 differently without knowing what
         a dentate spike class is. */
      sess.curationMarks = {
        kind: 'dspca',
        index: Math.max(0, at),
        at: now ? now.t : null,
        gid: q.gid,
        labels: Array.from({ length: fit.k }, (_x, i) => ({
          id: 'DS' + (i + 1), name: 'DS' + (i + 1), color: colorOf(i + 1),
        })),
        events: evs.map((e) => ({ start: e.t, label: 'DS' + e.type })),
      };
      /* THE DELTA, IN THE OTHER WINDOW TOO.

         As channel lines, which is the mechanism XploreFinder already
         has for "a laminar landmark, marked across the panes" -- the
         same one Incisor puts its layer picks on. So the two sinks the
         gap was measured between are drawn on the raw recording, at the
         contacts they were found on, and can be checked against the
         data the tool never touched.

         Nothing in that window had to learn what a dentate spike class
         is; it already knows how to draw a line at a contact. */
      const mk = now ? gapOf(now.i) : null;
      if (xf.setChannelLines) {
        const lines = [];
        if (mk && mk.csc) {
          const col = colorOf(pickedClass() || 1);
          mk.csc.forEach((n, j) => lines.push({
            key: 'dspca-sink' + j,
            label: j === 0 ? ('sink 1  Δ ' + mk.contacts + ' ctc')
                           : 'sink 2',
            colour: col, number: Number(n),
          }));
        }
        xf.setChannelLines(sess, lines);
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

  function onKey(e) {
    if (!q.read || !fit || !fit.ok) return;
    const tag = (document.activeElement || {}).tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (e.key === 'Enter' && dirty && !fitting) refit();
    else if (e.key === 'ArrowRight' || e.key === 'n') step(+1);
    else if (e.key === 'ArrowLeft' || e.key === 'p') step(-1);
    else if (e.key === 'Escape') {
      picked = null; render(); pictures(['traces', 'pane']);
    }
    else return;
    e.preventDefault();
  }

  /* One set of listeners for the life of the page, delegated by id, because
     every render replaces the canvases -- binding per render is how sixty
     rebuilds leak two hundred and forty listeners on detached nodes. */
  document.addEventListener('pointerdown', onDown);
  document.addEventListener('pointermove', onMove);
  document.addEventListener('pointerup', onUp);
  document.addEventListener('click', (e) => {
    if (!e.target || e.target.id !== 'dpScatter') return;
    /* A CLICK ON A DOT PICKS THAT DOT, on every method.

       It used to move the cut on the delta panel, with shift to pick
       instead -- which got the frequencies backwards: looking at a
       spike is constant and moving the boundary is occasional, and a
       click that does the rare thing by default is a click that does
       the wrong thing. The cut has a rail of its own above the dots
       now; see `drawDeltaSpace`. */
    onScatterClick(e);
  });
  // Right-click hands it back to the fit.
  /* Right-click the RAIL to hand the boundary back to k-means. On the
     rail and not the whole panel, so a right-click near a dot is still
     the browser's. */
  document.addEventListener('contextmenu', (e) => {
    if (!e.target || e.target.id !== 'dpScatter' || !isDelta()) return;
    if (q.delta_cut == null) return;
    const G = GEOM.scatter;
    const cv = document.getElementById('dpScatter');
    if (!G || !G.rail || !cv) return;
    const y = e.clientY - cv.getBoundingClientRect().top;
    if (y < G.rail.y0 || y > G.rail.y1) return;
    e.preventDefault();
    q.delta_cut = null;
    refit();
  });
  document.addEventListener('keydown', onKey);
  /* Redraw when the PANEL changes size, not only when the window does.

     Every canvas here takes its bitmap from the box it is drawn in, so
     anything that changes that box has to redraw it or the browser shows
     one size stretched to another -- which is the whole of "the PCA is
     blurry". A window listener catches a window being dragged and misses
     every other cause: the rail collapsing, the top row going from two
     columns to one, a panel opening beside it.

     Measured in `web/_dev/dspca.html`: squeezing the harness log from
     820px to 150px left the scatter shown at 539x704 and drawn at
     453x227. The window never changed size, so nothing redrew.

     The host outlives every render; the canvases inside it do not, so it
     is the host that is watched. */
  let sizeWatch = null;
  let sizeWatched = null;
  let redrawSoon = null;
  let redrawing = false;
  let roSeen = 0;              // notifications that reached onBoxResize
  let roDrew = 0;              // of those, the ones that redrew

  const CANVAS_IDS = ['dpTraces', 'dpShank', 'dpScatter', 'dpProfile',
                      'dpClasses', 'dpFeat'];

  /* Is any picture being shown at a size it was not drawn at?

     The condition, asked directly, rather than "did something resize".
     Two things fall out of that. A notification that changed nothing --
     including the one a ResizeObserver delivers the moment it starts
     watching -- costs a measurement and no redraw, so watching the
     canvases cannot make them redraw forever. And a resize this code
     never heard about still gets corrected the next time anything asks,
     which is what stops one missed notification leaving the panel blurry
     until it is reopened. */
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

  function onBoxResize() {
    roSeen += 1;
    if (redrawing) return;              // no re-entry from our own drawing
    /* DEBOUNCED, not throttled.

       This used to return early whenever a check was already pending,
       which DROPS a notification rather than coalescing it. A resize
       arrives as a burst; if the pending check then ran a moment before
       the layout had settled it found nothing mismatched, and the
       notifications that would have caught it a frame later had already
       been thrown away. Nothing was left to tell the panel, so it stayed
       drawn at its old size until something else happened to redraw it.

       Measured in the harness, which is the only reason this was ever
       more than a theory: after squeezing the log, `seen` had gone up by
       two, `drew` was still nought and `mismatched` was true. Re-arming
       means the check always happens after the LAST notification. */
    if (redrawSoon) clearTimeout(redrawSoon);
    redrawSoon = setTimeout(() => {
      redrawSoon = null;
      if (!q.read || !fit || !mismatched()) return;
      redrawing = true;
      roDrew += 1;
      try { drawAll(); } finally { redrawing = false; }
    }, 120);
  }

  /* The canvases, not the host.

     Watching the host meant watching ONE element, and `#tkResult` is not
     ours -- when the ToolKit replaces it the observer is left holding a
     detached node, which never reports anything again. That is why the
     redraw worked on one harness run and not the next. The canvases are
     rebuilt by every render, so they are re-observed by every draw, and
     `disconnect` drops the previous set rather than accumulating it. */
  /* A CHECK, not only a notification.

     The notification is not guaranteed. Measured in the harness, four
     runs of the same page: on two of them squeezing the log changed the
     layout, moved every panel, and produced no resize notification
     inside the frame at all -- `seen` did not move and the pictures
     stayed drawn at their old size. A design that can only react to
     being told is wrong whenever it is not told.

     So the invariant is also checked on a slow tick while the panel is
     on screen: six `getElementById`s and a few reads, no request, and no
     work at all when nothing has moved. It stops itself as soon as the
     panel is gone, which is what keeps it from being a poller left
     running for a tool nobody is looking at. */
  let sizeTick = null;

  function startSizeTick() {
    if (sizeTick) return;
    sizeTick = setInterval(() => {
      if (!document.getElementById('dpShank')) {
        clearInterval(sizeTick);
        sizeTick = null;
        return;
      }
      if (redrawing || redrawSoon) return;
      if (!q.read || !fit || !mismatched()) return;
      redrawing = true;
      roDrew += 1;
      try { drawAll(); } finally { redrawing = false; }
    }, 400);
  }

  function watchSize() {
    startSizeTick();
    if (typeof ResizeObserver !== 'function') return;
    if (!sizeWatch) sizeWatch = new ResizeObserver(onBoxResize);
    sizeWatch.disconnect();
    const h = host();
    if (h) sizeWatch.observe(h);
    for (const id of CANVAS_IDS) {
      const cv = document.getElementById(id);
      if (cv) sizeWatch.observe(cv);
    }
    sizeWatched = h;
  }

  // Still listened for, because a browser without ResizeObserver would
  // otherwise never redraw at all. Both go through the same coalesce.
  window.addEventListener('resize', onBoxResize);

  function fmtMs(v) {
    return (v > 0 ? '+' : '') + (Math.round(v * 10) / 10) + ' ms';
  }

  /* Published as a real property so the OTHER window can drive this one.

     `BARRY` is declared `const` in core.js, which makes it a lexical
     binding and not a property of `window` -- `opener.BARRY` is undefined
     however completely this page has loaded. `barryXplore`, `barryCfc`
     and `barrySpectrum` exist for the same reason, and the recording
     window reaches back through this one. */
  window.barryDspca = {
    step: (d) => step(d || 1),
    pick: (i) => { picked = i; render(); pictures(['traces', 'pane']);
                   pushXray(); },
    current: () => (picked == null ? null
                    : (fit && fit.ok
                       ? (fit.events || []).find((e) => e.i === picked)
                       : null)),
    classOf: (i) => {
      const e = fit && fit.ok
        ? (fit.events || []).find((x) => x.i === i) : null;
      return e ? e.type : null;
    },
  };

  return {
    paint,
    // For web/_dev/dspca.html, which drives the real panel rather than a
    // copy of it. A harness that reimplements the thing it is testing tests
    // nothing.
    _state: () => ({ q, plan, fit, picked, job, cands, pics }),
    _pick: pickSet,
    _read: startRead,
    _fit: refit,
    _box: (lo, hi, a, b) => {
      q.sel_lo = lo; q.sel_hi = hi; q.t_lo_ms = a; q.t_hi_ms = b; refit();
    },
    _rule: (r) => { q.rule = r; refit(); },
    // Same shape as `_rule`: set it and recompute, which is what the
    // radio beside it does.
    _features: (m) => { q.features = m; refit(); },
    _method: (m) => { q.method = m; refit(); },
    _minSep: (n) => { q.min_sep = Math.max(1, n | 0); refit(); },
    _gapWeight: (w) => { q.gap_weight = Math.max(0, +w || 0); refit(); },
    _panelPngs: panelPngs,
    _repaint: render,
    _refitFrom: () => refitFrom,
    /* The method CHANGED but not recomputed, which is the state the
       stale chip exists for. A harness poking `q` through `_state`
       relies on the shape of a debug export; this is the state itself. */
    _methodPending: (m) => { q.method = m; render(); },
    _takeOut: (n) => {
      const have = new Set(q.manual_bad || []);
      if (have.has(n)) have.delete(n); else have.add(n);
      q.manual_bad = Array.from(have).sort((a2, b2) => a2 - b2);
      refit();
    },
    _cut: (c) => { q.delta_cut = c; refit(); },
    /* Where the dots and the cut's rail actually landed, so a harness
       can press on one without knowing how the panel is laid out. */
    _scatterGeom: () => (GEOM.scatter
      ? { rail: GEOM.scatter.rail,
          pick: (GEOM.scatter.pick || []).map(
            (p) => ({ i: p.i, x: p.x, y: p.y })) }
      : null),
    _fitBody: () => fitBody({}),
    _pickedClass: pickedClass,
    _hood: openHood,
    _hoodData: () => hood,
    _compare: refitCompare,
    _crosstab: () => (compare ? crosstab(compare) : null),
    _cmpDiff: () => (compare ? settingsDiff(compare) : null),
    _lastBody: () => lastBody,
    _cmpQ: () => (compare ? { before: compare.before.q,
                              after: compare.after.q } : null),
    _esc: () => { picked = null; render(); pictures(['traces', 'pane']); },
    _k: (n) => { q.nclasses = n; refit(); },
    _step: step,
    _draw: drawAll,
    _preview: preview,
    _commit: apply,
    _bulk: () => bulk,
    _bulkPlan: loadBulk,
    _guides: () => guides,
    _addGuide: saveGuide,
    _dropGuide: dropGuide,
    _depth: () => DEPTH,
    /* A guide drag, without a pointer.

       `web/_dev/dspca.html` uses it to check that a line moved on one panel
       moves on all of them. It is the tail of `onUp` rather than a
       reimplementation of it: the same optimistic redraw and the same
       write, so the check is of the real path. */
    _dragGuide: (id, csc) => {
      const gd = guides.find((x) => x.id === id);
      if (!gd) return false;
      gd.csc = csc;
      drawAll();
      saveGuide(csc, undefined, id);
      return true;
    },
    /* A read in progress, and a tick of it, without a read.

       The flicker this pair checks only shows while a job is running, and
       a real one is minutes of disk. These put the panel in exactly the
       state the poll puts it in -- `job` set, the progress card drawn by
       the same `render()` -- and then run the running branch of `watch`
       itself, so what the harness drives is the path, not a copy of it. */
    _fakeJob: (st) => {
      job = { id: 'harness', status: 'running',
              stages: [Object.assign({ done: 0, of: 348, unit: 'windows' },
                                     st || {})] };
      render();
    },
    _tick: (st) => {
      if (!job) return false;
      job.stages = [Object.assign({}, (job.stages || [])[0], st || {})];
      return swap('.dp-job', progress());
    },
    _endJob: () => { job = null; render(); },
    /* A box drag, without a pointer.

       The tail of `onUp` rather than a reimplementation of it: the same
       deferral, the same redraw. `_box` is the other half -- set a box AND
       recompute, which is what a drag followed by the Recompute button
       does. */
    _dragBox: (lo, hi, a, b) => {
      q.sel_lo = lo; q.sel_hi = hi; q.t_lo_ms = a; q.t_hi_ms = b;
      dirty = true;
      render();
    },
    _dirty: () => dirty,
    /* Why a resize did or did not redraw. `seen` counts notifications
       that reached the handler at all, which is the half a harness
       cannot otherwise see. */
    _resizeInfo: () => ({ seen: roSeen, drew: roDrew,
                          watching: !!sizeWatch, mismatched: mismatched() }),
    _reset: () => { cands = null; plan = null; fit = null; q.read = null;
                    q.entry = null; picked = null; pics = {}; },
  };
}());
