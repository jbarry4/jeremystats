/* ==========================================================================
   spotter.js -- Spotter, confirming interictal discharges one at a time.

   Step 2 of The Storm. Radar says where the cells are; a spotter drives out
   and confirms by eye. Doppler is the radar.

   WHAT IT REPLACES
   A folder of rendered PNGs dragged into Solid/, Sputter/, Flag/ and
   Garbage/, where the folder a picture ended up in WAS the decision --
   which is one `robocopy` away from being lost, and is why
   `tools/import_ied.py` had to exist. Here a decision is written the moment
   it is made, into this machine's own shard, and the picture is the live
   recording rather than something rendered hours ago.

   IT IS ITS OWN MODE, AND IT IS SHAPED LIKE CHECKUP
   The same curation machinery underneath -- sets, owners, the bench and the
   shelf, presence, per-machine shards, version history -- because all of
   that is about work somebody has open and none of it is about dentate
   spikes. What differs is what is on screen, and it differs for a reason:
   an IED is a cross-channel event, so the channels the detector says took
   part in THIS one are lit, and the whole recording is under the panes as
   one line per channel, colouring in as you decide.

   THE KEYBOARD IS THE MOCKUP'S
   1 Solid, 2 Sputter, 3 Garbage, 4 Flag -- which is not a divergence: the
   `ied` vocabulary in `curation.py` already declares those digits as each
   label's first key. Navigation is checked BEFORE the vocabulary, always,
   because the navigation has to be the one thing that does what it says.
   ========================================================================== */
'use strict';

BARRY.spotter = (function () {
  const $ = (s) => document.querySelector(s);

  let set_ = null;      // the curation set as the server has it
  let kind = null;      // { id, labels[] } -- COPIED from the set
  let sess = null;      // the open xplore session
  let entry = null;     // the bank entry it came from
  let index = 0;
  let span = 1.0;
  let history = [];     // [{id, from}] -- the undo stack
  let review = 'left';  // 'left' | 'flag' | 'all'
  let markRev = 0;
  let lastChange = null;
  let saving = 0;
  let aidWin = null;
  let beatTimer = null;
  let beatOthers = [];
  let toldAbout = new Set();
  let decidedAtEntry = 0;

  /* How strongly the channels an event was found on are tinted: 'lit',
     'faint' or 'off'. Remembered per person, because it is about how
     somebody likes to read traces and not about the recording. */
  const LIGHT = { lit: 0.22, faint: 0.08, off: 0 };
  let light = 'lit';
  try {
    const got = BARRY.prefs.get('spotter_light', 'lit');
    if (LIGHT[got] != null) light = got;
  } catch (e) { /* prefs not up yet; the default stands */ }

  /* What the detector said about each event, read out of Doppler's vault
     and matched to the banked stamps by time. An event in the bank has a
     `channel`, not a list of them, so this is the only way to know that an
     IED was on seven channels rather than one. Absent is fine: the peak
     channel is on the banked event and that alone still lights. */
  let part = null;              // [{start, channels[], peak_channel}]
  let partIdx = null;           // sorted starts, for the nearest lookup
  let chanRows = [];            // every channel, for the raster's rows

  const PRESENCE_BEAT = 20000;
  const MATCH_S = 0.002;        // how near a stamp has to be to claim a row
  const RASTER_ROW = 9;

  const clock = (t) => {
    if (t == null) return '—';
    const s = Math.max(0, Number(t));
    const m = Math.floor(s / 60);
    return m + ':' + String((s - m * 60).toFixed(2)).padStart(5, '0');
  };

  const events = () => (set_ && set_.events) || [];
  const current = () => events()[index] || null;
  const left = () => events().filter((e) => !e.label).length;

  /* Which labels mean "come back to this one". Read off the set's own
     vocabulary rather than hard-coded: a set copies its vocabulary when it
     is created, and an older one may not carry the marker yet. */
  const flagIds = () => {
    const out = new Set();
    for (const l of (kind && kind.labels) || []) {
      if (l.flagged || l.id === 'flag' || l.id === 'review') out.add(l.id);
    }
    return out;
  };
  const wanted = (ev) => {
    if (!ev) return false;
    if (review === 'all') return true;
    if (review === 'flag') return !!ev.label && flagIds().has(ev.label);
    return !ev.label;
  };
  const nWanted = () => events().filter(wanted).length;

  /* ==================================================================
     Entering and leaving
     ================================================================== */

  /* `entryId` is a bank entry, because that is what Doppler hands over and
     what a person picks out of a list of three runs on one recording. A set
     is made from it if there is not one already; if there is, and it came
     from a different entry, that is a question rather than something to do
     silently. */
  async function enter(gid, entryId, opts) {
    /* One mode at a time, and `enter` is responsible for it. All three take
       over the panes, the keyboard and the aid window; entering one on top
       of another leaves two toolbars stacked and two sets of key handlers
       fighting over the same presses. `active` is a GETTER -- calling it
       throws. */
    BARRY.modes.leaveAllBut('spotter');   // every other mode; see core.js
    if (set_) exit();

    if (entryId) {
      const made = await ensureSet(gid, entryId);
      if (!made) return false;
    }

    let data;
    try {
      data = await api('/api/curation/' + encodeURIComponent(gid) + '/ied');
    } catch (e) {
      toast('Could not open that set: ' + e.message, 'err', 9000);
      return false;
    }
    if (!data.set) {
      toast('Nothing has been banked for that recording yet. Run Doppler '
            + 'first, then bank what it found.', 'warn', 9000);
      return false;
    }
    set_ = data.set;
    kind = { id: set_.kind, labels: set_.labels || [] };

    /* `here[0]`, not `path`: a registry row carries the paths reachable
       from THIS machine, and asking for `path` returns undefined. */
    const path = ((data.session || {}).here || [])[0];
    if (!path) {
      toast('None of this recording’s paths are reachable from this '
            + 'machine, so there is nothing to look at.', 'err', 9000);
      set_ = null;
      return false;
    }

    setView('xplore');
    sess = await BARRY.views.xplore.open(path);
    if (!sess) { set_ = null; return false; }

    span = (opts && opts.span)
        || parseFloat(BARRY.prefs.get('spotter_span', 0)) || 1.0;
    if (!(span > 0)) span = 1.0;
    index = 0;
    history = [];
    review = 'left';

    /* Opening it is what puts it on the bench. Nothing else does: banking a
       run leaves the set closed, because a set nobody has opened is not
       work in progress, it is a list that exists. */
    apiPost('/api/curation/' + encodeURIComponent(gid) + '/ied/open',
            { open: true })
      .then((r) => { if (r && r.set) set_.assignee = r.set.assignee; })
      .catch(() => {});

    setMode('spotter', exit);
    chanRows = ((sess.info || {}).channels || []).slice();
    useIedBand();
    layout();
    sess.curation = { kind: set_.kind, set: set_, index: 0 };
    publishMarks();

    /* Open on a pass that has something in it. A run that has already been
       through once arrives fully decided, and the undecided pass would open
       on a blank screen. */
    if (!events().some((e) => !e.label)) {
      review = events().some((e) => e.label && flagIds().has(e.label))
        ? 'flag' : 'all';
    }

    const back = recallWhere();
    if (back) {
      const was = review;
      review = back.review;
      if (!nWanted()) review = was;
      goTo(back.index, true);
      const at = events().slice(0, index + 1).filter(wanted).length;
      toast(back.gone
        ? 'Back where you were — that one is no longer in this set, so '
          + 'this is the next along (' + at + ' of ' + nWanted() + ').'
        : 'Back where you left off: ' + at + ' of ' + nWanted() + '.',
        null, 5000);
    } else {
      goTo(firstWanted(), true);
    }
    render();

    // Best effort, after the mode is usable: the participation is a nicety
    // and waiting on it would delay the first event appearing.
    loadParticipation(gid);

    BARRY.activity.log('spotter.enter', {
      gid, n: events().length, left: left(),
    }, sess);

    decidedAtEntry = events().filter((e) => e.label).length;
    beatOthers = []; toldAbout = new Set();
    beat(true);
    if (beatTimer) clearInterval(beatTimer);
    beatTimer = setInterval(() => beat(false), PRESENCE_BEAT);
    return true;
  }

  /* Make the set from the bank entry, unless one is already there.

     One set per (recording, kind), which is the server's rule. If the one
     that exists came from a different run, replacing it would throw away
     decisions somebody made -- so it asks, and the question names both. */
  async function ensureSet(gid, entryId) {
    /* `/api/curation/<gid>/<kind>` is the one that answers "is there a set
       here", and `set` comes back null when there is not. `for-recording`
       answers a different question -- what is BANKED that a set could be
       started from -- and reading it as a list of sets found none, every
       time, so the first version replaced work silently. */
    let existing = null;
    try {
      const got = await api('/api/curation/' + encodeURIComponent(gid)
                            + '/ied');
      existing = got.set || null;
    } catch (e) { /* no set is the ordinary case */ }

    if (existing) {
      /* `bank_entry`, not `entry`: from-bank writes the source as
         {kind:'bank version', bank_entry, version, ...}. Reading `.entry`
         got undefined every time, so re-entering a set you had already
         started from this very run asked to replace it. */
      const from = (existing.source || {}).bank_entry;
      if (!entryId || from === entryId) return true;
      const ok = await BARRY.confirm(
        'There is already a set of IEDs on this recording',
        el('div', { class: 'fix-facts' }, [
          el('p', { text: '"' + (existing.name || 'the existing set')
              + '" has ' + ((existing.progress || {}).specified || 0)
              + ' of ' + ((existing.progress || {}).total || 0)
              + ' decided. Starting from this run instead replaces it.' }),
          el('p', { text: 'Its decisions are already banked as versions of '
              + 'the entry it came from, so they are not lost — but '
              + 'they will not be in front of you any more.' }),
        ]), 'Replace it', true);
      if (!ok) return true;   // curate what is there
    }
    try {
      await apiPost('/api/curation/from-bank', {
        gid, kind: 'ied', entry: entryId, version: 0, replace: true,
      });
    } catch (e) {
      toast('Could not make a set from that run: ' + e.message, 'err', 9000);
      return false;
    }
    entry = entryId;
    return true;
  }

  function exit() {
    if (!set_) return;
    /* Written now rather than in 350 ms. Preference writes are coalesced,
       and leaving is exactly the moment somebody is about to do something
       else -- the whole point is that it survives a tab switch. */
    rememberWhere();
    try { BARRY.prefs.flush(); } catch (e) { /* the timer will get it */ }
    BARRY.activity.log('spotter.leave',
                       { gid: set_.gid, left: left() }, sess);
    if (beatTimer) { clearInterval(beatTimer); beatTimer = null; }
    apiPost('/api/presence/release', { gid: set_.gid, kind: 'ied' })
      .catch(() => {});
    beatOthers = [];
    if (sess) { delete sess.curation; delete sess.curationMarks; }
    restoreBand();
    // Or the other windows keep drawing marks for a set nobody is deciding.
    if (sess && BARRY.views.xplore.publishCuration) {
      BARRY.views.xplore.publishCuration(sess, null);
    }
    if (aidWin && !aidWin.closed) { try { aidWin.close(); } catch (e) {} }
    aidWin = null;
    // Or the tinted lanes outlive the mode and sit on the traces of
    // whatever is looked at next.
    if (sess && BARRY.views.xplore.setChannelLines) {
      BARRY.views.xplore.setChannelLines(sess, []);
    }
    setMode(null);
    receipt(set_.gid, { quiet: true });
    if (BARRY.views.toolkit && BARRY.views.toolkit.curationChanged) {
      BARRY.views.toolkit.curationChanged();
    }
    set_ = null; kind = null; sess = null; entry = null;
    history = []; part = null; partIdx = null; chanRows = [];
    const bar = $('#spotBar');
    if (bar) bar.remove();
    const ras = $('#spotRaster');
    if (ras) ras.remove();
    document.removeEventListener('keydown', keys, true);
    if (BARRY.views.xplore.refreshAll) BARRY.views.xplore.refreshAll();
  }

  /* THE IED BAND, NOT WHATEVER THE RECORDING WAS LAST LOOKED AT THROUGH.

     Xplorefinder reopens a recording with the filter it was last viewed
     with, and on a recording Checkup has been through that is the dentate-
     spike preset: 5-100 Hz. An IED judged through that has lost its slow
     wave, which is half of what tells a discharge from a sharp artefact --
     and the aid window copies the same filter from the session.

     So the mode sets the `ied` preset's band for as long as it is open, and
     puts the previous one back when it closes. It does NOT save it: the
     recording's own remembered filter belongs to whoever set it, and a mode
     that rewrote it would change what the next person sees in Xplorefinder
     for reasons they cannot find. The numbers come from the preset itself,
     so editing the `ied` preset changes what Spotter shows. */
  let prevBand = null;
  const IED_FALLBACK = { highpass: 1, lowpass: 70, notch: 60 };

  function useIedBand() {
    if (!sess) return;
    const st = BARRY.views.xplore.state || {};
    const pr = (((st.presets || {}).filters) || [])
      .find((x) => x.id === 'ied') || IED_FALLBACK;
    prevBand = { hp: sess.hp, lp: sess.lp, notch: sess.notch };
    sess.hp = +pr.highpass || 0;
    sess.lp = +pr.lowpass || 0;
    sess.notch = +pr.notch || 0;
    if (BARRY.views.xplore.refreshAll) BARRY.views.xplore.refreshAll();
  }

  function restoreBand() {
    if (!sess || !prevBand) return;
    sess.hp = prevBand.hp; sess.lp = prevBand.lp; sess.notch = prevBand.notch;
    prevBand = null;
  }

  /* The traces get the window; the aids get their own.

     Three aid panes, not Checkup's four. Theta is a dentate-spike question
     and is not one you ask of a discharge; what is left is the laminar
     profile, the whole-probe picture and the time-frequency signature,
     which between them are how an IED is told from an artefact on one
     wire. */
  function layout() {
    BARRY.views.xplore.setPanes([{ panel: 'traces' }], { col: 0.5, row: 0.5 });
    openAids();
  }

  function openAids() {
    if (aidWin && !aidWin.closed) {
      try { aidWin.focus(); } catch (e) {}
      return;
    }
    const every8 = ((sess.info || {}).channels || [])
      .filter((c, i) => i % 8 === 0).map((c) => c.index);
    aidWin = BARRY.views.xplore.popOutPanes(sess, [
      { panel: 'csd' },
      { panel: 'voltage' },
      { panel: 'spectrogram', tfChannels: every8, tfMode: 'stack',
        fmin: 1, fmax: 250 },
    ], { role: 'aids', name: 'barry-spotter-aids', width: 720, height: 980,
         chrome: 'notabs,noheads,nostrip,nochannels' });
  }

  /* ==================================================================
     What the detector said
     ================================================================== */

  async function loadParticipation(gid) {
    try {
      const got = await apiPost('/api/doppler/participation', { gid });
      part = got.events || [];
      partIdx = part.map((e) => e.start);
    } catch (e) {
      part = []; partIdx = [];
    }
    drawRaster();
    if (BARRY.views.xplore.redraw) BARRY.views.xplore.redraw(0);
  }

  /* The channels this event was found on.

     Matched by time, to two milliseconds. Curation identity IS the
     timestamp here, and Eye may later move a stamp -- so a match that is
     merely near is refused rather than guessed at, and the peak channel on
     the banked event is the fallback. Lighting the wrong channels would be
     worse than lighting one. */
  function channelsFor(ev) {
    if (!ev) return [];
    if (partIdx && partIdx.length) {
      let lo = 0, hi = partIdx.length - 1, best = -1, bestD = Infinity;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        const d = Math.abs(partIdx[mid] - ev.start);
        if (d < bestD) { bestD = d; best = mid; }
        if (partIdx[mid] < ev.start) lo = mid + 1; else hi = mid - 1;
      }
      // `from_t` is what a moved stamp carries, so an aligned set still
      // finds its row rather than falling back for every event.
      if (best >= 0 && bestD <= MATCH_S) return part[best].channels || [];
      if (ev.from_t != null) {
        for (let i = 0; i < partIdx.length; i++) {
          if (Math.abs(partIdx[i] - ev.from_t) <= MATCH_S) {
            return part[i].channels || [];
          }
        }
      }
    }
    return ev.channel != null ? [Number(ev.channel)] : [];
  }

  /* ==================================================================
     Moving
     ================================================================== */

  function firstWanted() {
    const i = events().findIndex(wanted);
    return i < 0 ? 0 : i;
  }

  function goTo(i, quiet) {
    const n = events().length;
    if (!n) return;
    index = Math.max(0, Math.min(n - 1, i));
    const ev = current();
    if (!ev || !sess) return;
    publishMarks();
    // Centred, so the thing is where the eye already is.
    BARRY.views.xplore.setWindow(0, Math.max(0, ev.start - span / 2), span);
    // The channels this one is on -- published to the panes as a set of
    // lines, which is the same door Incisor uses for its three landmarks.
    lightChannels(ev);
    if (!quiet) render();
    warmAhead();
  }

  /* Light the channels this event was found on.

     By CSC NUMBER, not by lane. A lane is a fact about the pane, which may
     be showing every fourth channel; the number is a fact about the
     recording. `setChannelLines` looks the lane up and marks the edge when
     the channel is not on screen at all. */
  function lightChannels(ev) {
    if (!BARRY.views.xplore.setChannelLines) return;
    // Off is an empty list, not a zero alpha: nothing to draw is nothing
    // to hit-test or to publish to the other window either.
    if (light === 'off') {
      BARRY.views.xplore.setChannelLines(sess, []);
      return;
    }
    const nums = channelsFor(ev);
    const peak = ev && ev.channel != null ? Number(ev.channel) : null;
    const col = BARRY.token('--ok', '#2f9e6e');
    const dim = BARRY.token('--accent', '#3b82f6');
    const a = LIGHT[light];
    BARRY.views.xplore.setChannelLines(sess, nums.map((n) => ({
      key: 'spot' + n,
      number: Number(n),
      style: 'mark',
      // The peak channel a little stronger than the rest, so "which one
      // carried it" is still readable when seven are lit.
      alpha: Number(n) === peak ? a * 1.5 : a,
      colour: Number(n) === peak ? col : dim,
      label: 'CSC' + n,
    })));
  }

  function warmAhead() {
    if (!BARRY.views.xplore.prewarm) return;
    const all = events();
    if (!all.length) return;
    const want = [];
    for (let d = 1; d <= 8; d++) {
      if (all[index + d]) want.push(all[index + d].start);
      if (d <= 3 && all[index - d]) want.push(all[index - d].start);
    }
    if (want.length) BARRY.views.xplore.prewarm(want);
  }

  function step(d) {
    const n = events().length;
    if (!n) return;
    let i = index;
    for (let tries = 0; tries < n; tries++) {
      i += d;
      if (i < 0 || i >= n) {
        toast(d > 0 ? 'That was the last one.' : 'That is the first one.',
              null, 2500);
        return;
      }
      if (wanted(events()[i])) break;
    }
    goTo(i);
  }

  /* ==================================================================
     Deciding
     ================================================================== */

  async function assign(labelId) {
    const ev = current();
    if (!ev) return;
    const was = ev.label || null;

    /* Optimistic. The key press has to feel instant and the write follows;
       a failure puts back everything the optimistic step did, including the
       history entry, or `Z` later "undoes" a decision that never saved and
       writes the old value over the server's. */
    ev.label = labelId;
    const step_ = { id: ev.id, from: was };
    history.push(step_);
    markRev += 1;
    lastChange = { index, label: labelId };
    publishMarks({ local: true });
    if (history.length > 500) history.shift();
    render();
    drawRaster();
    step(1);                 // move on BEFORE the round trip

    saving += 1; updateSaving();
    try {
      const res = await apiPost(
        '/api/curation/' + encodeURIComponent(set_.gid) + '/ied/label',
        { event: ev.id, label: labelId });
      if (res.progress) set_._progress = res.progress;
      if (BARRY.views.toolkit && BARRY.views.toolkit.curationChanged) {
        BARRY.views.toolkit.curationChanged();
      }
    } catch (e) {
      ev.label = was;
      const back = history.indexOf(step_);
      if (back >= 0) history.splice(back, 1);
      markRev += 1;
      lastChange = { index: events().findIndex((x) => x.id === ev.id),
                     label: was };
      publishMarks();
      drawRaster();
      /* The set has been deleted out from under us. Every further keystroke
         would fail the same way and put another red toast on screen, which
         is how a trace ends up full of identical 400s. */
      if (/no curation set/i.test(e.message || '')) {
        toast('That set has been deleted, so there is nothing to save into. '
              + 'Leaving Spotter.', 'err', 9000);
        exit();
        return;
      }
      toast('That did not save: ' + e.message, 'err', 8000);
      render();
    } finally {
      saving -= 1; updateSaving();
    }
  }

  async function clearLabel() {
    const ev = current();
    if (!ev || !ev.label) return;
    await assignRaw(ev, null);
  }

  async function assignRaw(ev, labelId) {
    const was = ev.label || null;
    ev.label = labelId;
    history.push({ id: ev.id, from: was });
    markRev += 1;
    lastChange = { index: events().indexOf(ev), label: labelId };
    publishMarks();
    render(); drawRaster();
    try {
      await apiPost('/api/curation/' + encodeURIComponent(set_.gid)
                    + '/ied/label', { event: ev.id, label: labelId });
    } catch (e) {
      ev.label = was;
      history.pop();
      publishMarks(); render(); drawRaster();
      toast('That did not save: ' + e.message, 'err', 8000);
    }
  }

  /* Undo goes back a decision AND back to the one it was about. Undoing
     something you can no longer see is not undoing it. */
  async function undo() {
    const last = history.pop();
    if (!last) { toast('Nothing to undo.', null, 2000); return; }
    const at = events().findIndex((e) => e.id === last.id);
    if (at < 0) return;
    const was = events()[at].label || null;
    events()[at].label = last.from;
    markRev += 1;
    lastChange = { index: at, label: last.from };
    goTo(at);
    drawRaster();
    try {
      await apiPost('/api/curation/' + encodeURIComponent(set_.gid)
                    + '/ied/label', { event: last.id, label: last.from });
    } catch (e) {
      events()[at].label = was;
      history.push(last);
      markRev += 1;
      publishMarks();
      toast('That undo did not save: ' + e.message, 'err', 8000);
    }
    render();
  }

  /* ==================================================================
     The keyboard
     ================================================================== */

  /* NAVIGATION IS CHECKED FIRST and wins. The vocabulary only gets whatever
     is left, which is why `curation.py` keeps a RESERVED_KEYS set and
     strips those keys on the way out. Nothing here has to know which
     letters those are. */
  function keys(e) {
    if (!set_) return;
    if (isTyping(e)) return;
    const k = (e.key || '').toLowerCase();
    if ((e.ctrlKey || e.metaKey) && k === 'z') {
      e.preventDefault(); e.stopPropagation(); undo(); return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    const nav = {
      arrowright: () => step(1), arrowleft: () => step(-1),
      n: () => step(1), p: () => step(-1),
      z: undo, u: undo, backspace: undo,
      c: clearLabel,
      escape: exit,
    };
    if (nav[k]) {
      e.preventDefault(); e.stopPropagation();
      nav[k]();
      return;
    }
    for (const lab of (kind.labels || [])) {
      if (lab.computed) continue;
      if ((lab.keys || []).some((x) => String(x).toLowerCase() === k)) {
        e.preventDefault(); e.stopPropagation();
        assign(lab.id);
        return;
      }
    }
  }

  /* ==================================================================
     The bar
     ================================================================== */

  function render() {
    if (!set_) return;
    let bar = $('#spotBar');
    if (!bar) {
      bar = el('div', { id: 'spotBar', class: 'cur-bar spot-bar' });
      const body = $('#xfBody');
      if (body) body.appendChild(bar);
      // Once, when the bar is first built -- not on every render, or a
      // single keystroke fires as many times as the bar has been drawn.
      document.addEventListener('keydown', keys, true);
    }
    bar.innerHTML = '';
    const ev = current();
    const n = events().length;
    const at = events().slice(0, index + 1).filter(wanted).length;

    bar.appendChild(el('div', { class: 'cur-where' }, [
      el('strong', { text: set_.name || 'IEDs' }),
      el('span', { class: 'cur-sub', text: clock(ev && ev.start) }),
      ev && ev.channel != null
        ? el('span', { class: 'cur-sub', text: 'CSC' + ev.channel }) : null,
      el('span', { class: 'cur-count', text: at + ' / ' + nWanted() }),
      beatOthers.length
        ? BARRY.ui.chip(beatOthers.length + ' also here', { kind: 'warn' })
        : null,
    ].filter(Boolean)));

    const tally = {};
    for (const e of events()) if (e.label) tally[e.label] = (tally[e.label] || 0) + 1;
    const decided = events().filter((e) => e.label).length;
    // Checkup's own progress markup: `.cur-prog` fills through an `i`.
    bar.appendChild(el('div', { class: 'cur-prog' }, [
      el('i', { style: 'width:' + (n ? (100 * decided / n) : 0) + '%' }),
      el('span', {
        text: decided + ' decided · ' + left() + ' left' }),
    ]));

    const cats = el('div', { class: 'cur-cats' });
    for (const lab of (kind.labels || [])) {
      // A computed category is read-only: no key, no button. DS1/DS2 are
      // the precedent and the rule is the vocabulary's, not this mode's.
      if (lab.computed) continue;
      const key = (lab.keys || [])[0];
      cats.appendChild(el('button', {
        class: 'cur-cat' + (ev && ev.label === lab.id ? ' on' : ''),
        style: '--cat:' + lab.color,
        title: lab.name + (key ? '  [' + key + ']' : ''),
        onclick: () => assign(lab.id),
      }, [
        el('span', { text: lab.name }),
        key ? el('kbd', { text: String(key) }) : null,
        el('span', { class: 'cur-count', text: String(tally[lab.id] || 0) }),
      ].filter(Boolean)));
    }
    bar.appendChild(cats);

    bar.appendChild(el('div', { class: 'cur-nav' }, [
      el('button', { class: 'mini', text: '◀', title: 'Previous  [←]',
        onclick: () => step(-1) }),
      el('button', { class: 'mini', text: '▶', title: 'Next  [→]',
        onclick: () => step(1) }),
      el('button', { class: 'mini', text: 'Clear', title: 'Clear  [C]',
        disabled: (ev && ev.label) ? null : 'disabled',
        onclick: clearLabel }),
      el('button', { class: 'mini', text: '↶', title: 'Undo  [Z]',
        disabled: history.length ? null : 'disabled', onclick: undo }),
      BARRY.ui.seg([
        ['left', 'Undecided', 'The ones nobody has decided yet'],
        ['flag', 'Flagged (' + flagged() + ')', 'The ones put aside'],
        ['all', 'All', 'Every candidate, decided or not'],
      ], review, (id) => {
        review = id;
        if (!wanted(current())) goTo(firstWanted());
        render();
      }),
      BARRY.ui.seg([
        ['lit', 'Lit', 'Tint the channels this event was found on'],
        ['faint', 'Faint', 'Tint them lightly'],
        ['off', 'Off', 'Do not mark the channels at all'],
      ], light, (id) => {
        light = id;
        try { BARRY.prefs.set('spotter_light', id); } catch (e) {}
        lightChannels(current());
        render();
      }, { extra: 'spot-light' }),
      el('span', { id: 'spotSaving', class: 'cur-saving' }),
      el('span', { class: 'spacer' }),
      /* Checkup's own dialog and route, not a second copy of either: one
         entry, one new version, and the dialog says what that version
         will hold before anything is written. Every decision is already
         saved the moment it is made -- this is what turns them into a
         version of the entry Doppler banked. */
      el('button', { class: 'btn ghost sm', text: 'Bank the results\u2026',
        title: 'Write these decisions as a new version of the banked run',
        onclick: bank }),
      el('button', { class: 'btn ghost sm', text: 'Line them up…',
        title: 'Take the confirmed ones to Eye',
        onclick: () => {
          if (BARRY.views.toolkit) BARRY.views.toolkit.pick('eye');
          setView('toolkit');
        } }),
      el('button', { class: 'btn ghost sm', text: 'Leave', onclick: exit }),
    ]));
    updateSaving();
    ensureRaster();
  }

  function bank() {
    if (!set_ || !BARRY.curate || !BARRY.curate.bankAt) return;
    const t = {};
    for (const e of events()) if (e.label) t[e.label] = (t[e.label] || 0) + 1;
    return BARRY.curate.bankAt({
      gid: set_.gid, kind: set_.kind, name: set_.name,
      labels: (kind && kind.labels) || set_.labels || [],
      progress: { by_label: t, left: left() },
    });
  }

  const flagged = () => events().filter(
    (e) => e.label && flagIds().has(e.label)).length;

  function updateSaving() {
    const n = $('#spotSaving');
    if (n) n.textContent = saving ? 'saving…' : '';
  }

  /* ==================================================================
     The whole recording, under the panes
     ================================================================== */

  /* One line per channel, one tick per event, colouring in as you decide.

     The same picture Doppler's report draws, so the thing you looked at
     before starting is the thing filling in while you work. Checkup's
     overview strip is still there and still does its job -- that one is
     about the window in front of you, this one is about the recording. */
  function ensureRaster() {
    let host = $('#spotRaster');
    if (!host) {
      host = el('canvas', { id: 'spotRaster', class: 'spot-raster',
        onclick: rasterClick });
      const bar = $('#spotBar');
      if (bar && bar.parentNode) bar.parentNode.insertBefore(host, bar);
    }
    drawRaster();
  }

  /* The geometry the painter and the click share, so a click lands on the
     tick it looks like it lands on. */
  const RP = { l: 64, r: 10, t: 14, b: 16 };

  function rasterRows() {
    // Only the channels that were READ. On a 128-channel probe with half
    // of it left out, drawing every row gave the ticks 1.4 px each and
    // spent the rest on grey rules for channels that could never have a
    // tick. The ones not read are counted in the corner instead.
    const read = new Set();
    for (const e of (part || [])) {
      for (const n of (e.channels || [])) read.add(Number(n));
    }
    const all = chanRows.length ? chanRows : [];
    const rows = read.size ? all.filter((c) => read.has(Number(c.number)))
                           : all;
    return { rows, hidden: all.length - rows.length };
  }

  /* One line per channel, one tick per event, colouring in as you decide.

     Legible at 128 channels, which the first version was not: rows get at
     least 2 px, the per-row rules are only drawn when a row is tall enough
     to need one (otherwise every eighth, as a shank-sized guide), undecided
     ticks are a mid-grey rather than a near-invisible one, and the event
     you are on is a full-height accent line with a marker above it. */
  function drawRaster() {
    const cv = $('#spotRaster');
    if (!cv || !set_ || !sess) return;
    const { rows, hidden } = rasterRows();
    const n = Math.max(1, rows.length);
    const h = Math.max(70, Math.min(240, n * 2 + RP.t + RP.b));
    const w = Math.max(160, Math.round(cv.clientWidth
      || (cv.parentNode && cv.parentNode.clientWidth) || 600));
    const dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    cv.style.height = h + 'px';
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);

    const dur = (sess.info || {}).duration_s || 1;
    const plotW = Math.max(10, w - RP.l - RP.r);
    const plotH = Math.max(10, h - RP.t - RP.b);
    const step = plotH / n;
    const rowOf = {};
    rows.forEach((c, i) => { rowOf[Number(c.number)] = i; });
    const X = (t) => RP.l + (t / dur) * plotW;

    // Guides: every row when a row is tall enough to be told apart, every
    // eighth otherwise -- the lab's probes are banked in eights and that is
    // the unit anybody reads a laminar picture in.
    const every = step >= 6 ? 1 : 8;
    g.strokeStyle = BARRY.token('--border', '#333');
    g.lineWidth = 1;
    for (let i = 0; i <= n; i += every) {
      const y = Math.round(RP.t + i * step) + 0.5;
      g.globalAlpha = every === 1 ? 0.35 : 0.6;
      g.beginPath(); g.moveTo(RP.l, y); g.lineTo(RP.l + plotW, y); g.stroke();
    }
    g.globalAlpha = 1;

    const labs = {};
    for (const l of (kind.labels || [])) labs[l.id] = l.color;
    const undecided = BARRY.token('--text-2', '#9aa8a0');
    const tickW = step >= 3 ? 1.5 : 1.25;
    const evs = events();
    // Decided ones last, so a colour is never painted over by grey.
    const order = evs.map((e, k) => k)
      .sort((p, q2) => (evs[p].label ? 1 : 0) - (evs[q2].label ? 1 : 0));
    for (const k of order) {
      if (k === index) continue;
      const e = evs[k];
      const x = Math.round(X(e.start)) + 0.5;
      g.strokeStyle = e.label ? (labs[e.label] || BARRY.token('--accent'))
                              : undecided;
      g.globalAlpha = e.label ? 0.95 : 0.55;
      g.lineWidth = tickW;
      const nums = channelsFor(e);
      if (!nums.length) continue;
      g.beginPath();
      for (const num of nums) {
        const i = rowOf[Number(num)];
        if (i == null) continue;
        const y0 = RP.t + i * step;
        g.moveTo(x, y0 + (step > 3 ? 0.5 : 0));
        g.lineTo(x, y0 + Math.max(1.5, step - (step > 3 ? 0.5 : 0)));
      }
      g.stroke();
    }
    g.globalAlpha = 1;

    // Where you are: full height, in the accent, with a marker above it.
    const cur = evs[index];
    if (cur) {
      const x = Math.round(X(cur.start)) + 0.5;
      const acc = BARRY.token('--accent', '#E5A823');
      g.strokeStyle = acc; g.lineWidth = 2;
      g.beginPath(); g.moveTo(x, RP.t); g.lineTo(x, RP.t + plotH); g.stroke();
      g.fillStyle = acc;
      g.beginPath();
      g.moveTo(x - 5, 2); g.lineTo(x + 5, 2); g.lineTo(x, RP.t - 2);
      g.closePath(); g.fill();
      g.lineWidth = 1;
    }

    // The words: what this is, how much of the probe it shows, and time.
    g.fillStyle = BARRY.token('--text-2', '#9aa8a0');
    g.font = '10px system-ui';
    g.textBaseline = 'middle';
    g.textAlign = 'right';
    g.fillText(rows.length + ' channels', RP.l - 8, RP.t + plotH / 2 - 6);
    if (hidden) {
      g.fillStyle = BARRY.token('--text-3', '#6f8c7d');
      g.fillText(hidden + ' not read', RP.l - 8, RP.t + plotH / 2 + 7);
    }
    g.textBaseline = 'alphabetic';
    g.fillStyle = BARRY.token('--text-3', '#6f8c7d');
    g.textAlign = 'left';
    g.fillText('0 s', RP.l, h - 3);
    g.textAlign = 'right';
    g.fillText(Math.round(dur) + ' s', RP.l + plotW, h - 3);
    g.textAlign = 'left';
  }

  function rasterClick(e) {
    if (!set_ || !sess) return;
    const cv = $('#spotRaster');
    const r = cv.getBoundingClientRect();
    const plotW = Math.max(10, r.width - RP.l - RP.r);
    const dur = (sess.info || {}).duration_s || 1;
    const t = ((e.clientX - r.left) - RP.l) / plotW * dur;
    let best = -1, bestD = Infinity;
    events().forEach((ev, i) => {
      const d = Math.abs(ev.start - t);
      if (d < bestD) { bestD = d; best = i; }
    });
    if (best >= 0) {
      // Switch to the pass that contains it rather than refusing to go:
      // clicking a decided event in the Undecided pass is a request to look
      // at that one, not a mistake.
      if (!wanted(events()[best])) review = 'all';
      goTo(best);
    }
  }

  /* ==================================================================
     Marks, presence, the receipt, where-you-were
     ================================================================== */

  /* The only path by which the panes, the strip and the AID WINDOW learn
     about a candidate. The aid window is a separate page with no Spotter
     module in it, so anything it must draw has to reach it as data on the
     session rather than as a call. */
  function publishMarks(opts) {
    if (!sess || !set_) return;
    sess.curationMarks = {
      kind: set_.kind,
      index,
      at: (current() || {}).start,
      labels: (kind.labels || []).map((l) => ({ id: l.id, color: l.color,
                                                name: l.name })),
      events: events().map((e) => ({ start: e.start, label: e.label || null })),
      gid: set_.gid,
    };
    if (opts && opts.local) return;
    if (BARRY.views.xplore.publishCuration) {
      BARRY.views.xplore.publishCuration(sess, {
        gid: set_.gid, kind: set_.kind, index,
        at: (current() || {}).start, n: events().length,
        rev: markRev, changed: lastChange,
      });
    }
  }

  async function beat(first) {
    if (!set_) return;
    let res;
    try {
      res = await apiPost('/api/presence/beat', {
        gid: set_.gid, kind: 'ied', first: !!first, doing: 'spotting',
        n_total: events().length,
        n_decided: events().filter((e) => e.label).length,
        n_this_visit: events().filter((e) => e.label).length - decidedAtEntry,
        at_index: index, at_time_s: (current() || {}).start,
      });
    } catch (e) {
      // Deliberately silent. Presence is advisory and a network blip must
      // not put a red toast over somebody working.
      return;
    }
    beatOthers = res.others || [];
    if (sess) sess.curationOthers = beatOthers;
    for (const o of beatOthers) {
      const who = o.who || o.machine || 'somebody';
      if (toldAbout.has(who)) continue;
      toldAbout.add(who);
      toast(who + ' is in this set too. Nothing is locked — this is so '
            + 'you do not collide by accident.', 'warn', 8000);
    }
    render();
  }

  const WHERE_KEY = 'spotter_at';

  function rememberWhere() {
    if (!set_) return;
    const ev = current();
    let all = {};
    try { all = JSON.parse(BARRY.prefs.get(WHERE_KEY, '{}')) || {}; }
    catch (e) { all = {}; }
    all[set_.gid + ':ied'] = {
      review, index, id: ev && ev.id, t: ev && ev.start,
      at: Date.now(),
    };
    // Bounded, oldest out. A preference that grows for ever is a preference
    // that eventually cannot be written.
    const ks = Object.keys(all);
    if (ks.length > 60) {
      ks.sort((a, b) => (all[a].at || 0) - (all[b].at || 0));
      for (const k of ks.slice(0, ks.length - 60)) delete all[k];
    }
    BARRY.prefs.set(WHERE_KEY, JSON.stringify(all));
  }

  /* By id, then by time, then by nearest -- and it says when the candidate
     itself has gone, because landing somewhere unexplained reads as a bug
     and the whole point is to be able to trust it. */
  function recallWhere() {
    if (!set_) return null;
    let all = {};
    try { all = JSON.parse(BARRY.prefs.get(WHERE_KEY, '{}')) || {}; }
    catch (e) { return null; }
    const got = all[set_.gid + ':ied'];
    if (!got) return null;
    const evs = events();
    let i = evs.findIndex((e) => e.id === got.id);
    let gone = false;
    if (i < 0 && got.t != null) {
      i = evs.findIndex((e) => Math.abs(e.start - got.t) < 1e-4);
    }
    if (i < 0 && got.t != null) {
      gone = true;
      let bestD = Infinity;
      evs.forEach((e, k) => {
        const d = Math.abs(e.start - got.t);
        if (d < bestD) { bestD = d; i = k; }
      });
    }
    if (i < 0) return null;
    return { review: got.review || 'left', index: i, gone };
  }

  const RECEIPT_MIN = 8;

  async function receipt(gid, opts) {
    const quiet = !!(opts && opts.quiet);
    let got;
    try {
      got = await api('/api/curation/' + encodeURIComponent(gid)
                      + '/ied/receipt');
    } catch (e) { return; }
    const s = got.sitting || {};
    // Fewer than this is not a sitting, and on the way out it says nothing.
    if (quiet && (s.n || 0) < RECEIPT_MIN) return;
    const labs = {};
    for (const l of (got.labels || [])) labs[l.id] = l;
    BARRY.confirm(
      'That sitting',
      el('div', { class: 'rcpt' }, [
        el('div', { class: 'rcpt-big', text: (s.n || 0) + ' decided' }),
        el('div', { class: 'rcpt-sub',
          text: ((got.progress || {}).specified || 0) + ' of '
              + ((got.progress || {}).total || 0) + ' in this set' }),
        el('div', { class: 'rcpt-labs' },
          Object.keys(s.by_label || {}).map((id) => el('div', {
            class: 'rcpt-lab' }, [
            el('i', { style: 'background:' + ((labs[id] || {}).color || '#888') }),
            el('span', { class: 'rl-name',
              text: (labs[id] || {}).name || id }),
            el('span', { class: 'rl-n', text: String(s.by_label[id]) }),
          ]))),
      ]), 'Close');
  }

  /* ==================================================================
     Drawing on the panes
     ================================================================== */

  /* Called from xplore for every trace pane and every image panel. It must
     tolerate running in the AID WINDOW, which loaded this file but never
     entered the mode -- so it draws from the session, not from `set_`. */
  function draw(ctx, s, win, x0, plotW, y0, plotH, P) {
    const marks = s && s.curationMarks;
    if (!marks || marks.kind !== 'ied') return;
    const cur = (marks.events || [])[marks.index];
    if (!cur) return;
    const span_ = win.t1 - win.t0;
    if (cur.start < win.t0 || cur.start > win.t1) return;
    const x = x0 + ((cur.start - win.t0) / span_) * plotW;
    const byId = {};
    for (const l of (marks.labels || [])) byId[l.id] = l;
    const col = cur.label ? ((byId[cur.label] || {}).color || '#888')
                          : BARRY.token('--accent', '#E5A823');
    ctx.save();
    ctx.strokeStyle = col;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(Math.round(x) + 0.5, y0);
    ctx.lineTo(Math.round(x) + 0.5, y0 + plotH);
    ctx.stroke();
    ctx.fillStyle = col;
    ctx.beginPath();
    ctx.arc(Math.round(x) + 0.5, y0 + 7, 4, 0, Math.PI * 2);
    ctx.fill();
    if (cur.label) {
      ctx.font = '11px system-ui';
      ctx.textAlign = 'left';
      ctx.fillText((byId[cur.label] || {}).name || cur.label, x + 7, y0 + 24);
    }
    ctx.restore();
  }

  /* A reopen replaces the session object -- toggling even-only does it --
     and a mode holding the old one keeps painting into a detached tree. */
  function rebind(next) {
    if (!next || !set_) return;
    sess = next;
    sess.curation = { kind: set_.kind, set: set_, index };
    chanRows = ((sess.info || {}).channels || []).slice();
    // The new session object came back with the recording's saved filter.
    useIedBand();
    publishMarks();
    lightChannels(current());
    render();
  }

  function recentre() {
    const ev = current();
    if (!ev || !sess) return;
    const p = (BARRY.views.xplore.state.panes || [])[0];
    if (p && p.span) span = p.span;
  }

  return {
    enter, exit, draw, rebind, recentre, receipt,
    step: (d) => step(d),
    goTo: (i) => goTo(i),
    assign: (id) => assign(id),
    clear: clearLabel,
    bank,
    undo,
    events: () => events().map((e) => ({ start: e.start,
                                         label: e.label || null })),
    channelsFor,
    get review() { return review; },
    // A GETTER, not a method. Calling it throws, which is what every
    // `if (BARRY.spotter.active)` in the tree relies on.
    get active() { return !!set_; },
    get state() {
      return set_ ? { gid: set_.gid, kind: 'ied', index,
                      total: events().length, left: left() } : null;
    },
    _raster: drawRaster,
    _keys: keys,
    // For `_dev/spotter.html`: a computed category is read-only and gets no
    // button, and the harness has to count the ones that should.
    _kindLabels: () => ((kind && kind.labels) || []).slice(),
  };
})();

// One mode at a time, kept by the registry in core.js.
BARRY.modes.register('spotter', BARRY.spotter);
