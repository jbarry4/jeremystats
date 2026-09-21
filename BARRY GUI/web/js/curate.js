/* ==========================================================================
   curate.js -- Going through candidates one at a time.

   The same shape of job whether the candidates are dentate spikes or
   interictal discharges: jump to one, look at it, press a key, move on. So
   this is one mode with a vocabulary handed to it, not two tools.

   Three things it has to get right, all of which the standalone sorters got
   right and are the reason people liked them:

   It has to be fast. A key per category, no confirmation, no dialog. Six
   hundred candidates at two seconds each is twenty minutes; at five seconds
   it is an afternoon.

   It has to be undoable. The hand moves faster than the eye and the wrong
   key gets pressed. Undo goes back a decision AND back a candidate, because
   that is what "undo" means when you have already moved on.

   It must not lose anything. Every keystroke is written through to the
   server, so closing the laptop mid-set costs nothing. The set lives against
   the recording's global id, so it is the same set on the next machine.

   The layout it opens with -- voltage traces large, with a spectrogram, CSD
   and voltage raster beside them -- is the one you would build by hand
   before starting, so it is built for you.
   ========================================================================== */
'use strict';

BARRY.curate = (function () {
  let set_ = null;        // the curation set as the server has it
  let kind = null;        // its vocabulary
  let sess = null;        // the open recording
  let index = 0;          // which candidate
  let span = 1.0;         // seconds of recording shown around it
  let history = [];       // {id, from} so undo means something
  let saving = 0;
  /* Which candidates the arrows visit.

       left   the ones with no decision yet -- the first pass
       flag   the ones marked Flag, which is the second pass over the ones
              that needed a longer look
       all    everything, for checking work

     `onlyLeft` was a boolean here, and a flagged candidate counts as
     decided, so there was no way to come back to them short of stepping
     through the whole set again. */
  let review = 'left';
  /* Bumped whenever a decision changes, so another window can tell a move
     (cheap, nothing to re-read) from a relabel (its copy is now stale). */
  let markRev = 0;
  /* What this set has been banked as, and which of those versions the
     decisions on screen came from. Carried in the same fetch that opens the
     set -- the bar says which version you are writing onto, and that is not
     a question worth a second round trip on a network share. */
  let vhist = [];

  /* ---------- presence ----------
     Saying "somebody is in this set" often enough that the answer is still
     true, and rarely enough that it is not a request per keystroke. Half the
     server's TTL, so a single dropped beat does not make somebody vanish
     mid-sentence. */
  const PRESENCE_BEAT = 20000;
  let beatTimer = null;
  let decidedAtEntry = 0;      // so "this visit" means this visit
  let beatOthers = [];         // who else is in here, as of the last beat
  let toldAbout = new Set();   // machines already announced, so it says it once
  let toldTaken = false;

  /* ==================================================================
     Entering and leaving
     ================================================================== */
  async function enter(gid, kindId, opts) {
    // See the same note in strata.js: one mode at a time, or the two stack
    // their toolbars and their key handlers on top of each other.
    // `active` is a getter, not a method -- calling it throws.
    if (BARRY.strata && BARRY.strata.active) BARRY.strata.exit();
    if (set_) exit();
    let data;
    try {
      data = await api('/api/curation/' + encodeURIComponent(gid) + '/'
                       + encodeURIComponent(kindId));
    } catch (e) {
      toast('Could not open that curation set: ' + e.message, 'err', 8000);
      return false;
    }
    set_ = data.set;
    vhist = data.history || [];
    kind = { id: set_.kind, labels: set_.labels || [] };

    const known = (data.session || {});
    const path = (known.here || [])[0];
    if (!path) {
      toast('None of this recording’s paths are reachable from this '
            + 'machine, so there is nothing to look at.', 'err', 9000);
      return false;
    }

    setView('xplore');
    sess = await BARRY.views.xplore.open(path);
    if (!sess) return false;

    /* One second either way, the FIRST time. A dentate spike is a few
       tens of milliseconds and what you need around it is enough context
       to tell it from an artifact -- 0.6 s was tight enough that a spike
       near the edge of the window had nothing on one side of it.

       Remembered after that. This line used to reset it on every entry,
       and entry happens every time a set is picked up -- from four call
       sites, none of which pass a span -- so widening the window lasted
       until the next set and no longer. */
    span = (opts && opts.span)
        || parseFloat(BARRY.prefs.get('curate_span', 0)) || 1.0;
    if (!(span > 0)) span = 1.0;
    index = 0;
    history = [];
    /* Open on a pass that has something in it.

       An imported sort arrives with every candidate already decided, so the
       undecided pass is empty and the mode would open on a blank screen --
       which is exactly the case this was built for: "a lot of them have been
       sorted and we just need to review the flagged items". */
    review = 'left';

    /* Opening it is what puts it on the workbench. Nothing else does:
       importing candidates leaves a set closed, because a set nobody has
       opened is not work in progress, it is just a list that exists. */
    apiPost('/api/curation/' + encodeURIComponent(gid) + '/'
            + encodeURIComponent(kindId) + '/open', { open: true })
      .then((res) => { if (res && res.set) set_.assignee = res.set.assignee; })
      .catch((e) => {
        /* An archived set is not put on the bench by being curated -- that
           would un-archive it as a side effect of looking at it, which is
           the thing archiving is supposed to survive. Curating still works;
           it just says the set is still filed away. */
        if (/archived/i.test((e && e.message) || '')) {
          toast('This set is archived, so it is not on the bench. Curating '
                + 'it still works and still saves; un-archive it from the '
                + 'ToolKit if you want it back in the list.', null, 8000);
        }
      });

    setMode('curate', exit);
    layout();
    // So the bar can say who else is here without asking again.
    sess.curationOthers = beatOthers;
    // Hand the candidates to the session so the trace can draw them.
    sess.curation = { kind: set_.kind, set: set_, index: 0 };
    publishMarks();
    if (!events().some((e) => !e.label)) {
      review = events().some((e) => e.label && flagIds().has(e.label))
      ? 'flag' : 'all';
    }

    /* Back where you left off, if you have been here before.

       The pass is restored first, because landing on candidate 208 while
       the Undecided pass is showing would put you on a candidate the pass
       does not contain -- and n/p would then walk away from it. A
       remembered pass with nothing in it is dropped rather than restored:
       that happens when somebody finishes the undecided pass and comes back,
       and opening on an empty screen is the fault this is next to. */
    const back = recallWhere();
    if (back) {
      const was = review;
      review = back.review;
      if (!nWanted()) review = was;
      goTo(back.index, true);
      /* Said out loud. Landing in the middle of a set with no explanation
         reads as a bug, and the whole point is to be able to trust it -- so
         it names the number, and says when the candidate itself has gone
         and this is the next one along. */
      const total = nWanted();
      const at = events().slice(0, index + 1).filter(wanted).length;
      toast(back.gone
        ? 'Back where you were — that candidate is no longer in this '
          + 'set, so this is the next one along (' + at + ' of ' + total + ').'
        : 'Back where you left off: ' + at + ' of ' + total + '.',
        null, 5000);
    } else {
      goTo(firstWanted(), true);
    }
    render();

    BARRY.activity.log('curation.enter', {
      gid, kind: set_.kind, n: (set_.events || []).length,
      left: left(),
    }, sess);

    /* Announce it, and keep announcing. The first beat carries `first`,
       which is what starts the clock on "how long they have been at it" --
       every later beat leaves that alone. */
    decidedAtEntry = events().filter((e) => e.label).length;
    beatOthers = [];
    toldAbout = new Set();
    toldTaken = false;
    beat(true);
    if (beatTimer) clearInterval(beatTimer);
    beatTimer = setInterval(() => beat(false), PRESENCE_BEAT);
    return true;
  }

  /* One beat: where we are, and who else is here.

     Deliberately quiet about failure. Presence is a courtesy -- the network
     being down is not a reason to interrupt somebody deciding candidates,
     and the server's TTL means a machine that goes silent stops holding the
     set on its own. */
  async function beat(first) {
    if (!set_) return null;
    const evs = events();
    const decided = evs.filter((e) => e.label).length;
    let res = null;
    try {
      res = await apiPost('/api/presence/beat', {
        gid: set_.gid, kind: set_.kind, first: !!first,
        doing: 'curating',
        n_total: evs.length,
        n_decided: decided,
        n_this_visit: Math.max(0, decided - decidedAtEntry),
        at_index: index,
        at_time_s: (evs[index] || {}).start,
      });
    } catch (e) {
      return null;
    }
    if (!res || !res.ok) return null;

    beatOthers = res.others || [];
    /* Somebody has appeared in the set you are in. Said once per machine:
       it is news the first time and nagging every twenty seconds after. */
    for (const o of beatOthers) {
      if (toldAbout.has(o.machine)) continue;
      toldAbout.add(o.machine);
      toast((o.person || o.device || 'Somebody')
            + ' is curating this set too, on ' + (o.device || o.machine)
            + '. Both of you are deciding the same candidates.',
            'err', 12000);
      BARRY.activity.log('curation.collision',
                         { gid: set_.gid, other: o.machine,
                           person: o.person }, sess);
    }

    /* And somebody has taken it. Which does not stop you -- nothing here
       can, and a decision already made is already written -- but carrying on
       without being told is the silent collision this exists to prevent. */
    if (res.taken && !toldTaken) {
      toldTaken = true;
      toast((res.taken.by || 'Somebody') + ' has taken this set over. Your '
            + 'decisions are still being saved, but you are both in it \u2014 '
            + 'worth a word before you carry on.', 'err', 15000);
      BARRY.activity.log('curation.taken',
                         { gid: set_.gid, by: res.taken.by }, sess);
    }
    render();
    return res;
  }

  function exit() {
    if (!set_) return;
    /* The place, written now rather than in 350 ms. Preference writes are
       coalesced, and leaving is exactly the moment somebody is about to do
       something else -- the whole point is that it survives a tab switch,
       so it must not depend on a timer that has not fired yet. */
    rememberWhere();
    try { BARRY.prefs.flush(); } catch (e) { /* the timer will get it */ }
    BARRY.activity.log('curation.leave', {
      gid: set_.gid, kind: set_.kind, left: left(),
    }, sess);

    /* Stop beating, and say so. The TTL would free the set in a couple of
       minutes anyway; doing it now matters because the person waiting to
       pick it up is usually standing next to you. */
    if (beatTimer) { clearInterval(beatTimer); beatTimer = null; }
    apiPost('/api/presence/release',
            { gid: set_.gid, kind: set_.kind }).catch(() => {});
    beatOthers = [];
    if (sess) { delete sess.curation; delete sess.curationMarks; }
    // Tell the other windows the mode is over, or they keep drawing marks
    // for a set nobody is deciding any more.
    if (sess && BARRY.views.xplore.publishCuration) {
      BARRY.views.xplore.publishCuration(sess, null);
    }
    if (aidWin && !aidWin.closed) { try { aidWin.close(); } catch (e) {} }
    aidWin = null;
    setMode(null);
    /* What the sitting came to, on the way out -- but only if there was a
       sitting. `quiet` makes it say nothing for a set somebody opened,
       looked at and left, which is most of the times this runs. Fired
       without awaiting: leaving must not wait on a fetch. */
    receipt(set_.gid, set_.kind, { quiet: true });
    if (BARRY.views.toolkit && BARRY.views.toolkit.curationChanged) {
      BARRY.views.toolkit.curationChanged();
    }
    set_ = null; kind = null; sess = null; history = []; vhist = [];
    const bar = $('#curBar');
    if (bar) bar.remove();
    document.removeEventListener('keydown', keys, true);
    if (BARRY.views.xplore.refreshAll) BARRY.views.xplore.refreshAll();
  }

  /* The layout the job wants: the traces big, the aids beside them.

     Rasters and a spectrogram are what tell you whether a deflection is the
     thing you are looking for or an artifact on one wire, so they are up
     from the start rather than something you go and enable. Everything is
     still an ordinary pane, so it can be rearranged like any other. */
  let aidWin = null;

  function layout() {
    // Same reasoning as StrataScope: what you are deciding -- is this
    // deflection a dentate spike or one bad wire -- is read off the traces,
    // so they get the window and the aids get their own.
    BARRY.views.xplore.setPanes([{ panel: 'traces' }], { col: 0.5, row: 0.5 });
    openAids();
  }

  function openAids() {
    if (aidWin && !aidWin.closed) { try { aidWin.focus(); } catch (e) {} return; }
    const every8 = (sess.info.channels || [])
      .filter((c, i) => i % 8 === 0).map((c) => c.index);
    aidWin = BARRY.views.xplore.popOutPanes(sess, [
      { panel: 'csd' },
      { panel: 'theta' },
      { panel: 'voltage' },
      { panel: 'spectrogram', tfChannels: every8, tfMode: 'stack',
        fmin: 1, fmax: 250 },
    ], { role: 'aids', name: 'barry-curate-aids', width: 720, height: 1000,
         // Folded on arrival. These four are for glancing at: the headers,
         // control strips and channel lists cost more of a short pane than
         // they are worth, and every one of them has a sliver to bring it
         // back if you want it.
         chrome: 'notabs,noheads,nostrip,nochannels' });
  }

  /* ==================================================================
     Moving
     ================================================================== */
  const events = () => (set_ && set_.events) || [];
  /* Does this candidate belong to the pass being made? */
  /* Which labels mean "come back to this one".

     Read off the set's own vocabulary rather than hard-coded, because a set
     copies its vocabulary when it is created and older ones do not carry
     the marker yet -- and because DS has two of them. The Flagged pass was
     matching only `flag`, so every candidate marked Flag for Deep Review
     was invisible in the pass that exists to find them. */
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
  const current = () => events()[index] || null;
  const left = () => events().filter((e) => !e.label).length;

  function firstUndecided() {
    const i = events().findIndex((e) => !e.label);
    return i < 0 ? 0 : i;
  }

  /* The first candidate in whichever pass is on. */
  function firstWanted() {
    const i = events().findIndex(wanted);
    return i < 0 ? 0 : i;
  }

  /* Put the marks where everything that draws can find them.

     The image panels and the overview strip read sess.curationMarks, and so
     does the aid window -- a separate page with no curate module in it. This
     is the only path by which any of them learn about a candidate. */
  let lastChange = null;

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
    // `local` updates what this window draws and tells nobody. The
    // caller that actually settles the position does the publishing.
    if (opts && opts.local) return;
    if (BARRY.views.xplore.publishCuration) {
      BARRY.views.xplore.publishCuration(sess, {
        gid: set_.gid, kind: set_.kind, index,
        at: (current() || {}).start, n: events().length,
        rev: markRev,
        /* The decision that was just made, so the other window can apply it
           without re-reading five hundred events. It refetches only if the
           revision has jumped by more than one, which means it missed
           something -- the live slot holds the latest value, so a burst of
           fast keystrokes can coalesce. */
        changed: lastChange,
      });
    }
  }

  /* The span, and the one place it is written down.

     Kept in preferences rather than in this closure because the closure
     is rebuilt on every `enter()`, which is every time a set is picked
     up. `curate_span` is in PREFS_LOCAL: how wide somebody likes their
     window is about this screen, not about the project. */
  function setSpan(v) {
    const want = Math.max(0.05, parseFloat(v) || 1);
    if (Math.abs(want - span) < 1e-6) return;
    span = want;
    BARRY.prefs.set('curate_span', span);
  }

  /* What the pane is actually showing. Curation centres the window on
     each candidate, and it used to do that with its own remembered span
     whatever the pane had been zoomed to -- so widening the view to see
     what surrounded a spike was undone by moving to the next one. */
  function paneSpan() {
    try {
      // The same two cases `winOf` has in xplore.js: an unlinked pane
      // carries its own window, a linked one reads the session's.
      const XF = BARRY.views.xplore.state;
      const pane = (XF.panes || [])[0];
      const s = (XF.linkMode === 'none' && pane && pane.t0 != null)
        ? pane.span
        : (sess ? sess.span : null);
      return (s > 0) ? s : null;
    } catch (e) {
      return null;
    }
  }

  /* ==================================================================
     Where you were

     Leaving a set keeps the decisions and used to lose the place. Coming
     back to 430 candidates with no idea whether you had reached 134 or 208
     means re-reviewing the overlap to be safe, every time -- which is the
     cost of a tab switch, paid in minutes.

     Kept per (recording, kind) in the synced preferences, which is where
     `span` already lives and what that file's own header calls "where was
     I". BY EVENT, NOT BY INDEX: a set can gain or lose candidates between
     sittings -- a re-import, a dedupe, a snapshot folder absorbed -- and an
     index would then point at a different spike with perfect confidence.
     The id is what survives that; the time is the fallback for a set
     rebuilt from a snapshot, which does not carry ids.
     ================================================================== */
  const WHERE_KEY = 'curate_at';
  // Enough to cover everything anybody has open at once, several times
  // over. Trimmed rather than unbounded: this file syncs.
  const WHERE_MAX = 60;

  const whereKey = (gid, k) => String(gid) + ':' + String(k);

  function rememberWhere() {
    if (!set_ || !kind) return;
    const ev = current();
    if (!ev) return;
    const all = Object.assign({}, BARRY.prefs.get(WHERE_KEY, {}) || {});
    all[whereKey(set_.gid, set_.kind)] = {
      id: ev.id || null,
      t: ev.start,
      review: review,
      n: events().length,
      at: Date.now(),
    };
    const keys = Object.keys(all);
    if (keys.length > WHERE_MAX) {
      keys.sort((a, b) => (all[b].at || 0) - (all[a].at || 0));
      for (const k of keys.slice(WHERE_MAX)) delete all[k];
    }
    BARRY.prefs.set(WHERE_KEY, all);
  }

  /* Where to land, and what to say about it. Returns null for a set nobody
     has been in, which opens at the start as it always did. */
  function recallWhere() {
    if (!set_) return null;
    const got = (BARRY.prefs.get(WHERE_KEY, {}) || {})[
      whereKey(set_.gid, set_.kind)];
    if (!got) return null;
    const all = events();
    let i = -1;
    if (got.id) i = all.findIndex((e) => e.id === got.id);
    if (i < 0 && got.t != null) {
      // Same candidate, no id to prove it: four places is 0.1 ms, which is
      // the tolerance the bank calls one event written twice.
      const want = Math.round(got.t * 1e4);
      i = all.findIndex((e) => Math.round(e.start * 1e4) === want);
    }
    if (i < 0 && got.t != null) {
      // The one you were on is gone. The next one along is where you would
      // have got to, which is better than the top of the set.
      i = all.findIndex((e) => e.start > got.t);
    }
    if (i < 0) return null;
    return { index: i, review: got.review || 'left', gone: !got.id
             || all[i].id !== got.id };
  }

  function goTo(i, quiet) {
    const n = events().length;
    if (!n) return;
    index = Math.max(0, Math.min(n - 1, i));
    const ev = current();
    if (sess.curation) sess.curation.index = index;
    rememberWhere();
    publishMarks();
    // Somebody zoomed the pane: that is the window they want, so take it
    // rather than putting it back. Only a real change counts -- the
    // centring below sets the span itself, so every jump reports one.
    const shown = paneSpan();
    if (shown && Math.abs(shown - span) > Math.max(0.02, span * 0.02)) {
      setSpan(shown);
    }
    // Centred, so the thing is where the eye already is.
    BARRY.views.xplore.setWindow(0, Math.max(0, ev.start - span / 2), span);
    if (!quiet) render();
    warmAhead();
  }

  /* Have the next few candidates rendered before they are asked for.

     This is the loop the whole mode is: jump, look, press a key, jump. The
     scalogram is a couple of seconds of work and it was paid on every jump,
     including jumping back to one already seen. Both directions are warmed
     because u and p go backwards, and going back used to cost exactly as
     much as going forward for no reason at all. */
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

    // Optimistic: the key press has to feel instant. The write follows, and
    // a failure puts it back and says so rather than pretending.
    ev.label = labelId;
    const step_ = { id: ev.id, from: was };
    history.push(step_);
    markRev += 1;
    lastChange = { index, label: labelId };
    /* Locally only. The colour has to change on this screen now, but the
       other windows do not need to be told twice: `step(1)` below moves to
       the next candidate and publishes the settled state a moment later.
       Publishing here as well meant two /api/link POSTs per keystroke,
       which is what filled the connection pool. */
    publishMarks({ local: true });
    if (history.length > 500) history.shift();
    render();
    // Move on before the round trip, which is the whole point of the mode.
    step(1);

    saving += 1;
    updateSaving();
    try {
      const res = await apiPost(
        '/api/curation/' + encodeURIComponent(set_.gid) + '/'
        + encodeURIComponent(set_.kind) + '/label',
        { event: ev.id, label: labelId });
      if (res.progress) set_._progress = res.progress;
      if (BARRY.views.toolkit && BARRY.views.toolkit.curationChanged) {
        BARRY.views.toolkit.curationChanged();
      }
    } catch (e) {
      /* Put back everything the optimistic step did, not only the
         label. The history entry it pushed stayed behind, so `u`
         later "undid" a decision that had never saved and wrote the
         old value over the server's -- and the other windows kept
         drawing the colour of a decision that did not exist. */
      ev.label = was;
      const back = history.indexOf(step_);
      if (back >= 0) history.splice(back, 1);
      markRev += 1;
      lastChange = { index: events().findIndex((x) => x.id === ev.id),
                     label: was };
      publishMarks();
      /* The set has been deleted out from under us -- from the ToolKit, or
         on another machine. Every further keystroke would fail the same way
         and put another red toast on screen, which is how a trace ends up
         full of identical 400s. Say it once and leave the mode, because
         there is nothing left to curate. */
      if (/no curation set/i.test(e.message || '')) {
        toast('That curation set has been deleted, so there is nothing to '
              + 'save into. Leaving curation.', 'err', 9000);
        exit();
        return;
      }
      toast('That did not save: ' + e.message, 'err', 8000);
      render();
    } finally {
      saving -= 1;
      updateSaving();
    }
  }

  async function undo() {
    const last = history.pop();
    if (!last) { toast('Nothing to undo.', null, 2000); return; }
    const at = events().findIndex((e) => e.id === last.id);
    if (at < 0) return;
    const was = events()[at].label || null;
    events()[at].label = last.from;
    // Same as a decision as far as the other windows are concerned: a mark
    // just changed colour, and goTo below is what tells them.
    markRev += 1;
    lastChange = { index: at, label: last.from };
    // Back to the one that was got wrong, which is what undo has to mean
    // once you have already moved on.
    goTo(at);
    try {
      await apiPost('/api/curation/' + encodeURIComponent(set_.gid) + '/'
                    + encodeURIComponent(set_.kind) + '/label',
                    { event: last.id, label: last.from });
    } catch (e) {
      /* The undo did not save, so the server still holds the decision.
         Showing it as undone would be a lie, and the history entry is
         already gone -- so put both back and say so. */
      events()[at].label = was;
      history.push(last);
      markRev += 1;
      lastChange = { index: at, label: was };
      publishMarks();
      toast('That undo did not save: ' + e.message, 'err', 8000);
    }
    render();
  }

  /* ==================================================================
     The bar
     ================================================================== */
  function render() {
    if (!set_) return;
    let bar = $('#curBar');
    if (!bar) {
      bar = el('div', { class: 'cur-bar', id: 'curBar' });
      const body = $('#xfBody');
      if (body) body.appendChild(bar); else document.body.appendChild(bar);
      document.addEventListener('keydown', keys, true);
    }
    bar.innerHTML = '';

    const n = events().length;
    const done = n - left();
    const ev = current();

    bar.appendChild(el('div', { class: 'cur-where' }, [
      el('strong', { text: set_.name || 'Curating' }),
      el('span', { class: 'cur-sub',
        text: (ev ? clock(ev.start) : '—')
            + (ev && ev.channel != null ? '  ·  CSC ' + ev.channel : '') }),
      el('span', { class: 'cur-count',
        text: (index + 1) + ' / ' + n }),
      verChip(),
    ]));

    bar.appendChild(el('div', { class: 'cur-prog' }, [
      el('i', { style: 'width:' + (n ? (done / n * 100) : 0) + '%' }),
      el('span', { text: done + ' decided · ' + left() + ' left' }),
    ]));

    const cats = el('div', { class: 'cur-cats' });
    for (const lab of (kind.labels || [])) {
      const on = ev && ev.label === lab.id;
      cats.appendChild(el('button', {
        class: 'cur-cat' + (on ? ' on' : ''),
        style: '--cat:' + lab.color,
        title: lab.name + '   (' + lab.keys.join(' or ') + ')',
        onclick: () => assign(on ? null : lab.id),
      }, [
        el('kbd', { text: lab.keys[0] }),
        el('span', { text: lab.name }),
      ]));
    }
    bar.appendChild(cats);

    bar.appendChild(el('div', { class: 'cur-nav' }, [
      el('button', { class: 'mini', text: '◀', title: 'Previous  (p)',
                     onclick: () => step(-1) }),
      el('button', { class: 'mini', text: '▶', title: 'Next  (n)',
                     onclick: () => step(1) }),
      el('button', { class: 'mini', text: '↶', title: 'Undo the last decision  (u, or Ctrl+Z)',
                     disabled: history.length ? null : 'disabled',
                     onclick: undo }),
      /* Which pass you are making. Flagged is the one that was missing:
         Flag is already a label in both vocabularies, and marking one used
         to mean never finding it again without walking the whole set. */
      el('div', { class: 'ctl' }, [
        el('label', { text: 'Review' }),
        el('div', { class: 'seg sm', id: 'curReview' }, [
          ['left', 'Undecided', 'The ones with no decision yet'],
          ['flag', 'Flagged', 'The ones marked Flag or Flag for Deep '
                            + 'Review \u2014 the second pass over '
                            + 'everything that needed a longer look'],
          ['all', 'All', 'Everything, including the ones already decided'],
        ].map(([id, label, tip]) => el('button', {
          class: review === id ? 'active' : '',
          title: tip,
          onclick: () => {
            if (review === id) return;
            const before = review;
            review = id;
            const n2 = nWanted();
            if (!n2) {
              review = before;
              toast(id === 'flag'
                ? 'Nothing is flagged yet \u2014 press f, or r for a deeper '
                  + 'look, on a candidate you want to come back to.'
                : 'Nothing left in that pass.', null, 5000);
              render();
              return;
            }
            BARRY.activity.log('curation.review', { mode: id, n: n2 }, sess);
            // Land on the first one in the new pass rather than staying on
            // a candidate that is not part of it.
            if (!wanted(current())) {
              const i = events().findIndex(wanted);
              if (i >= 0) { goTo(i); return; }
            }
            render();
          },
          // Counted the same way the pass selects, or the button
          // advertises three and the pass holds four.
          text: label + (id === 'flag'
            ? ' (' + events().filter(
                (e) => e.label && flagIds().has(e.label)).length + ')'
            : ''),
        }))),
      ]),
      el('div', { class: 'ctl' }, [
        el('label', { text: 'Window s' }),
        el('input', {
          type: 'number', step: '0.1', value: String(span),
          style: 'width:56px',
          onchange: (e) => {
            setSpan(Math.max(0.05, parseFloat(e.target.value) || 1));
            goTo(index);
          },
        }),
      ]),
      el('span', { class: 'cur-saving', id: 'curSaving', text: '' }),
      el('div', { style: 'flex:1' }),
      el('button', { class: 'btn ghost sm', text: 'List all\u2026',
                     title: 'Every candidate in this set, by time or by '
                          + 'category. Click one to go to it.',
                     onclick: listAll }),
      el('button', { class: 'btn ghost sm', text: 'Bank the results…',
                     onclick: bank }),
      el('button', { class: 'btn ghost sm', text: 'Leave', onclick: exit }),
    ]));

    // Only the overlay changed, so repaint rather than refetch. The window
    // move in goTo() is what asks the server for new samples, and it does
    // that once.
    if (BARRY.views.xplore.redraw) BARRY.views.xplore.redraw();
  }

  function updateSaving() {
    const n = $('#curSaving');
    if (n) n.textContent = saving ? 'saving…' : '';
  }

  /* ==================================================================
     Which version you are working on
     ==================================================================
     A set is one row per recording per kind, but the bank behind it keeps
     every pass anybody has ever banked. Until now the bench silently wrote
     onto whatever was newest, which is right nine times in ten and wrong in
     exactly the case that matters: going back to an older pass because the
     first one used the wrong channel.

     So the version is said on the bar, and it is a button. Switching puts
     the current one down and picks the chosen one up -- the decisions on
     screen become that version's, and every keystroke after it writes onto
     it. That is destructive to what is on the bench, so the dialog says so
     in the count of candidates it is about to re-stamp.
     ================================================================== */

  /* Which banked version the decisions here came from, with its lineage
     name. `based_on` is the stored integer, which is what the cloud table
     is keyed on; the name is worked out from what each version was banked
     from. Null until a set has been picked up from a version at least once
     -- 44 of the 45 sets here predate that being askable. */
  function verNow() {
    if (!set_) return null;
    const bo = set_.based_on;
    if (bo === null || bo === undefined) return null;
    for (const ent of vhist) {
      for (const x of BARRY.vers.labelRows(ent.versions || [])) {
        if (x.row.v === bo) {
          return { entry: ent.entry, v: x.row.v, name: x.name, row: x.row };
        }
      }
    }
    return null;
  }

  function verChip() {
    if (!BARRY.vers.askable(vhist)) return null;
    const now = verNow();
    return el('button', {
      class: 'cur-ver' + (now ? '' : ' none'),
      text: now ? 'from v' + now.name : 'pick a version',
      title: now
        ? 'The decisions here came from v' + now.name + ', and banking '
          + 'writes the next one onto it. Click to work from a different '
          + 'version instead.'
        : 'This set was not picked up from any particular banked version, '
          + 'so banking lands on whatever is newest. Click to choose one.',
      onclick: switchVersion,
    });
  }

  /* Put this version down and pick that one up, without leaving the mode.

     Restore is what does it: it stamps the chosen version's snapshot back
     over the candidates AND records what the set is now based on, so the
     next bank lands as a pass on that version rather than on top of
     whatever happened to be newest. */
  async function switchVersion() {
    if (!set_) return;
    if (!BARRY.vers.askable(vhist)) {
      toast('There is only one banked version of this set, so there is '
            + 'nothing to switch to. Bank a pass and there will be.',
            null, 6000);
      return;
    }
    const now = verNow();
    const gid = set_.gid, kd = set_.kind;
    const pick = await BARRY.pickVersion(vhist, {
      title: 'Switch to another version',
      sub: set_.name || '',
      lead: 'Switching puts this version down and picks the chosen one up. '
          + 'The decisions on screen become that version\u2019s, and '
          + 'everything you press after it is written onto that line. '
          + 'Nothing is deleted \u2014 every version stays in the bank.',
      labels: (kind && kind.labels) || [],
      mode: 'switch',
      current: now ? { entry: now.entry, v: now.v } : null,
      danger: true, verb: 'Switch to', okLabel: 'Switch',
    });
    if (!pick) return;
    if (now && pick.entry === now.entry && pick.v === now.v) {
      toast('Already working from v' + now.name + '.', null, 4000);
      return;
    }

    let res;
    try {
      res = await apiPost('/api/curation/' + encodeURIComponent(gid) + '/'
                          + encodeURIComponent(kd) + '/restore',
                          { entry: pick.entry, version: pick.v });
    } catch (e) {
      toast('Could not switch to v' + pick.name + ': ' + e.message, 'err', 9000);
      return;
    }

    /* Re-read rather than patch. The restore touched an unknown number of
       candidates on the server and set what the record is based on; guessing
       either of those from here is how the bar ends up claiming a version
       the next bank will not use. */
    let data;
    try {
      data = await api('/api/curation/' + encodeURIComponent(gid) + '/'
                       + encodeURIComponent(kd));
    } catch (e) {
      toast('Switched, but could not re-read the set: ' + e.message,
            'err', 9000);
      return;
    }
    set_ = data.set;
    vhist = data.history || [];
    kind = { id: set_.kind, labels: set_.labels || [] };
    /* Undo does not cross a switch. It goes back one decision at a time and
       the decisions it remembers belong to the version that was just put
       down -- replaying one onto this version would put a call nobody made
       into a pass they did not make it in. */
    history = [];
    markRev += 1;
    if (index >= events().length) index = Math.max(0, events().length - 1);
    if (sess) sess.curation = { kind: set_.kind, set: set_, index };
    /* Same reason as on the way in: a version with everything decided has an
       empty undecided pass, and landing on a blank screen after a switch
       reads as the switch having emptied the set. */
    if (!events().some((e) => !e.label) && review === 'left') {
      review = events().some((e) => e.label && flagIds().has(e.label))
        ? 'flag' : 'all';
    }
    publishMarks();
    if (!wanted(current())) {
      const i = events().findIndex(wanted);
      if (i >= 0) { goTo(i, true); }
    }
    render();

    const changed = (res && res.changed) || 0;
    toast('Now working from v' + pick.name + '. '
          + (changed ? changed + ' decision(s) changed to match it'
                     : 'Nothing on the bench had to change')
          + ((res && res.missing)
              ? ', ' + res.missing + ' of its candidate(s) are not in this '
                + 'set any more' : '')
          + '. Banking from here '
          + BARRY.vers.describe(
              (vhist.find((e) => e.entry === pick.entry) || {}).versions || [],
              pick.row) + '.', 'ok', 9000);
    BARRY.activity.log('curation.version', {
      gid, kind: kd, entry: pick.entry, version: pick.v,
      label: pick.name, changed,
    }, sess);
    if (BARRY.views.toolkit && BARRY.views.toolkit.curationChanged) {
      BARRY.views.toolkit.curationChanged();
    }
  }

  function keys(e) {
    if (!set_) return;
    if (isTyping(e)) return;
    const k = e.key.toLowerCase();

    /* Navigation is checked first, and wins.

       The server strips reserved keys out of every vocabulary, so this should
       never actually matter -- but "should never" is how `p` ended up meaning
       both "previous" and "sputter", and the key that moves you has to be the
       one thing that always moves you. */
    /* Ctrl/Cmd+Z as well as `u`.

       `u` is the fast key and stays the one on the button, because a hand
       already on the vocabulary keys should not have to reach for a
       modifier. But Ctrl+Z is what everybody tries first, and having it do
       nothing where there is plainly an undo button is its own small
       betrayal. */
    if ((e.ctrlKey || e.metaKey) && k === 'z') {
      e.preventDefault(); e.stopPropagation();
      undo();
      return;
    }
    // Any other modified key belongs to the browser or the app, not here.
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    const map = {
      n: () => step(1), arrowright: () => step(1),
      p: () => step(-1), arrowleft: () => step(-1),
      u: undo, backspace: undo,
      escape: exit,
    };
    if (map[k]) { e.preventDefault(); e.stopPropagation(); map[k](); return; }

    for (const lab of (kind.labels || [])) {
      if ((lab.keys || []).includes(k)) {
        e.preventDefault(); e.stopPropagation();
        assign(lab.id);
        return;
      }
    }
  }

  /* Asking for a version note, with the previous versions in front of you.

     Resolves to the note, or to null if it is called off. */
  /* `at` is the set as it was when Bank was clicked -- gid, kind and name.
     Passed in rather than read off `set_`, which may be null by now. */
  /* ==================================================================
     The receipt
     ==================================================================
     What a sitting came to, in a card. Worth having for two unrelated
     reasons: it is pleasant to see the afternoon add up, and the pace is
     the only thing here that says anything about the deciding rather than
     the data. A set decided at forty a minute and a set decided at four
     are not the same evidence, and nothing in the interface used to show
     which one you had.

     Shown on the way out when the sitting was long enough to be worth a
     card, and on demand from the workbench.
     ================================================================== */
  const RECEIPT_MIN = 8;         // fewer decisions than this is not a sitting

  async function receipt(gid, kind, opts) {
    const o = opts || {};
    let r;
    try {
      r = await api('/api/curation/' + encodeURIComponent(gid) + '/'
                    + encodeURIComponent(kind) + '/receipt'
                    + (o.who ? '?who=' + encodeURIComponent(o.who) : ''));
    } catch (e) {
      if (!o.quiet) toast(e.message, 'err');
      return null;
    }
    const s = r.sitting;
    /* On the way out this is silent when there is nothing worth a card --
       a modal for three decisions is an interruption, not a reward. */
    if (o.quiet && (!s || s.n < RECEIPT_MIN)) return null;
    if (!s) {
      toast('Nothing has been decided on this set yet.', 'warn');
      return null;
    }

    const pr = r.progress || {};
    /* The headline is the sentence somebody would say out loud. Everything
       under it is the same fact broken down, for anybody who wants it.

       The duration is only claimed when it is one. A snapshot import stamps
       the whole set at one instant, and "1,224 decided in 0 seconds" reads
       as a bug rather than as the truth about an import. */
    const timed = s.seconds >= 60 && s.bulk < s.n;
    const head = s.n.toLocaleString() + ' decided'
      + (timed ? ' in ' + spellSpan(s.seconds) : '');

    const labels = (r.labels || []).map((l) => {
      const n = (s.by_label || {})[l.id] || 0;
      return n ? el('div', { class: 'rcpt-lab' }, [
        el('i', { style: 'background:' + (l.color || '#888') }),
        el('span', { class: 'rl-name', text: l.name || l.id }),
        el('strong', { class: 'rl-n', text: String(n) }),
      ]) : null;
    }).filter(Boolean);

    showModal(el('div', { class: 'rcpt-wrap' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Session receipt' }),
        el('span', { class: 'sub', text: r.session || r.name || gid }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'rcpt' }, [
          el('div', { class: 'rcpt-big', text: head }),
          el('div', { class: 'rcpt-sub', text: (r.name || kind)
            + (s.who && s.who.length ? '  ·  ' + s.who.join(', ') : '') }),
          /* Pace, and only when it means something. A rate off two
             decisions in one second is a number, not a fact, and the
             server declines to produce one -- so this has nothing to
             say rather than something wrong. */
          s.per_min
            ? el('div', { class: 'rcpt-rate' }, [
                el('strong', { text: s.per_min.toFixed(1) }),
                el('span', { text: ' a minute' }),
                el('span', { class: 'rcpt-rate-note',
                  text: '  ·  about ' + spellSpan(60 / s.per_min)
                      + ' on each one'
                      + (s.bulk ? ', over the ' + s.paced.toLocaleString()
                                  + ' decided one at a time' : '') }),
              ])
            : el('div', { class: 'rcpt-rate quiet',
                text: s.bulk >= s.n
                  ? 'No pace to report: these were all stamped together.'
                  : 'Too short a stretch to put a rate on.' }),
          /* Said plainly rather than folded into the average. Fourteen
             candidates on one timestamp is one fill-down, and counting it
             as fourteen keystrokes is how you get a receipt claiming seven
             decisions a second. */
          s.bulk
            ? el('div', { class: 'rcpt-bulk' }, [
                el('strong', { text: s.bulk.toLocaleString() + ' of them ' }),
                el('span', { text: s.bulk >= s.n
                  ? 'share a single timestamp — an import or a fill-down '
                    + 'stamped the set all at once, so nobody sat and '
                    + 'decided them one by one.'
                  : 'came in groups on one timestamp'
                    + (s.bulk_biggest > 1
                        ? ' (up to ' + s.bulk_biggest + ' at a time)' : '')
                    + ', so they are left out of the pace above.' }),
              ])
            : null,
          labels.length ? el('div', { class: 'rcpt-labs' }, labels) : null,
          el('div', { class: 'rcpt-foot' }, [
            el('span', { text: pr.specified + ' of ' + pr.total
                             + ' decided altogether' }),
            pr.left ? el('span', { text: '  ·  ' + pr.left + ' left' }) : null,
            s.sittings > 1
              ? el('span', { text: '  ·  ' + s.sittings
                                 + ' sittings on this set' })
              : null,
          ].filter(Boolean)),
        ].filter(Boolean)),
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        /* No Cancel. There is nothing to cancel -- it is a statement of
           what already happened. */
        el('button', { class: 'btn', text: 'Done', onclick: closeModal }),
      ]),
    ]), { replace: !!o.replace });
    return r;
  }

  /* "38 minutes", "2h 14m", "4 seconds" -- whichever reads as a duration
     rather than as a measurement. */
  function spellSpan(sec) {
    if (!isFinite(sec)) return '';
    if (sec < 1) return Math.round(sec * 1000) + ' ms';
    if (sec < 90) {
      const n = sec < 10 ? sec.toFixed(1) : String(Math.round(sec));
      return n + ' second' + (Math.round(sec) === 1 ? '' : 's');
    }
    const m = Math.round(sec / 60);
    if (m < 90) return m + ' minute' + (m === 1 ? '' : 's');
    return Math.floor(m / 60) + 'h ' + (m % 60) + 'm';
  }

  function bankDialog(entry, who, at) {
    return new Promise((resolve) => {
      const labs = (kind && kind.labels)
        || (at && at.labels) || [];
      const nameOf = (id) => (labs.find((l) => l.id === id) || {}).name
                          || (id === 'unspecified' ? 'undecided' : id);
      /* The mix, from the set if it is still open and from the last
         progress the server reported if it is not -- leaving curation
         empties events() and the dialog would then claim the set was
         empty. */
      const tally = {};
      const live = events();
      if (live.length) {
        for (const e of live) {
          if (e.label) tally[e.label] = (tally[e.label] || 0) + 1;
        }
      } else {
        const by = ((at && at.progress) || {}).by_label || {};
        for (const k in by) tally[k] = by[k];
      }
      const stillLeft = live.length
        ? left() : (((at && at.progress) || {}).left || 0);
      const vs = (entry && entry.versions) || [];
      /* Highest so far plus one, which is what the server does. The
         count is not the same number: the detector's import sits at
         version zero, so an entry with v0 and v1 has two versions
         and its next one is v2. The dialog offered to write v3 and
         the server wrote v2. */
      const next = vs.reduce((hi, v) => Math.max(hi, v.v || 0), 0) + 1;

      const wrap = el('div', { class: 'modal bank-dialog' });
      wrap.appendChild(el('div', { class: 'modal-head' }, [
        el('h2', { text: vs.length ? 'Bank this as version ' + next
                                   : 'Bank this set' }),
        el('p', { class: 'sub', text: (at && at.name) || '' }),
      ]));

      /* What is about to be written. */
      wrap.appendChild(el('div', { class: 'section-label',
                                   text: 'What this version will hold' }));
      wrap.appendChild(el('div', { class: 'ver-mix' },
        Object.keys(tally).sort((a, b) => tally[b] - tally[a]).map(
          (k) => el('span', { class: 'ver-chip',
                              text: nameOf(k) + ' ' + tally[k] }))
        .concat(stillLeft
          ? [el('span', { class: 'ver-chip',
                          text: stillLeft + ' still undecided, not banked' })]
          : [])));

      if (vs.length) {
        /* "Already banked as N versions" is wrong when the history it is
           about to join belongs to the detector's export rather than to a
           previous bank of this set -- v0 was nobody banking anything. */
        wrap.appendChild(el('div', { class: 'section-label',
          text: entry && entry.adopted
            ? 'Carrying on from ' + (entry.source || 'the detector')
              + '  ·  ' + vs.length + ' version'
              + (vs.length === 1 ? '' : 's') + ' so far'
            : 'Already banked as ' + vs.length + ' version'
              + (vs.length === 1 ? '' : 's') }));
        const list = el('div', { class: 'ver-list compact' });
        for (let i = vs.length - 1; i >= 0; i--) {
          const v = vs[i];
          list.appendChild(el('div', { class: 'ver-row' }, [
            el('div', { class: 'ver-top' }, [
              el('span', { class: 'ver-n', text: 'v' + v.v }),
              v.imported ? el('span', { class: 'flagchip',
                                        text: 'the import' }) : null,
              el('span', { class: 'ver-when',
                           title: BARRY.whenRaw(v.at),
                           text: BARRY.when(v.at, 'minute') }),
              el('span', { class: 'ver-who', text: v.by || 'unknown' }),
              el('span', { class: 'ver-count', text: (v.n || 0) + ' events' }),
            ]),
            v.note ? el('div', { class: 'ver-note', text: v.note })
                   : el('div', { class: 'ver-note none', text: 'no note' }),
            /* What each version holds, so the history is readable as a
               history rather than as a list of dates. */
            v.by_label && Object.keys(v.by_label).length
              ? el('div', { class: 'ver-mix small' },
                  Object.keys(v.by_label)
                    .sort((a, b) => v.by_label[b] - v.by_label[a])
                    .map((k) => el('span', { class: 'ver-chip',
                                             text: nameOf(k) + ' '
                                                 + v.by_label[k] })))
              : null,
            v.changed
              ? el('div', { class: 'ver-shifts' }, [
                  el('span', { class: 'ver-since',
                               text: v.changed + ' decision'
                                   + (v.changed === 1 ? '' : 's')
                                   + ' changed' })])
              : null,
          ].filter(Boolean)));
        }
        wrap.appendChild(list);
      } else {
        wrap.appendChild(el('p', { class: 'hint',
          text: 'This set has not been banked before. From now on each bank '
              + 'writes a version onto the same entry, so the entry keeps '
              + 'its whole history rather than the bank filling up with '
              + 'copies.' }));
      }

      const box = el('textarea', {
        class: 'ver-note-input', rows: '3',
        placeholder: 'What changed in this pass? (optional)',
      });
      wrap.appendChild(el('div', { class: 'section-label',
                                   text: 'Note for version ' + next }));
      wrap.appendChild(box);
      wrap.appendChild(el('p', { class: 'hint',
        text: 'Banking as ' + who + '.' }));

      let settled = false;
      const done = (val) => {
        if (settled) return;
        settled = true;
        closeModal();
        resolve(val);
      };
      wrap.appendChild(el('div', { class: 'modal-foot' }, [
        el('div', { style: 'flex:1' }),
        el('button', { class: 'btn ghost', text: 'Cancel',
                       onclick: () => done(null) }),
        el('button', { class: 'btn', text: vs.length
                         ? 'Bank as v' + next : 'Bank',
                       onclick: () => done(box.value || '') }),
      ]));
      showModal(wrap);
      setTimeout(() => { try { box.focus(); } catch (e) {} }, 30);
    });
  }

  /* How the list was last looked at, kept across openings so a person who
     prefers the tally does not have to ask for it every time. */
  const listQ = { by: 'time', text: '', only: 'all' };

  function listAll() {
    const wrap = el('div', { class: 'modal cur-list-modal' });
    const labs = (kind && kind.labels) || [];
    const labOf = (id) => labs.find((l) => l.id === id) || null;
    const nameOf = (id) => (labOf(id) || {}).name || 'undecided';
    const colorOf = (id) => (labOf(id) || {}).color || null;
    const flags = flagIds();

    const tally = {};
    for (const e of events()) {
      const k = e.label || '';
      tally[k] = (tally[k] || 0) + 1;
    }

    wrap.appendChild(el('div', { class: 'modal-head' }, [
      el('h2', { text: 'Everything in this set' }),
      el('p', { class: 'sub',
                text: events().length + ' candidates  \u00b7  '
                    + left() + ' still undecided  \u00b7  '
                    + (set_.name || '') }),
    ]));

    const rowsHost = el('div', { class: 'cur-list' });

    const controls = el('div', { class: 'cur-list-bar' }, [
      el('div', { class: 'seg sm' }, [
        ['time', 'By time'],
        ['type', 'By category'],
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
        placeholder: 'Find a time, a category, a name\u2026',
        oninput: (e) => { listQ.text = e.target.value; paint(); },
      }),
      el('span', { class: 'hint', id: 'curListCount' }),
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
    chips.appendChild(chip('all', 'All', events().length));
    chips.appendChild(chip('left', 'Undecided', tally[''] || 0));
    chips.appendChild(chip('flagged', 'Flagged',
      events().filter((e) => e.label && flags.has(e.label)).length));
    for (const l of labs) {
      chips.appendChild(chip(l.id, l.name, tally[l.id] || 0));
    }

    /* Times read as mm:ss.mmm rather than seconds-since-start: nobody
       scrubbing a recording thinks in 1483.2 seconds. */
    const clock = (t) => {
      const m = Math.floor(t / 60);
      const s = t - m * 60;
      return m + ':' + (s < 10 ? '0' : '') + s.toFixed(3);
    };

    function matching() {
      const q = listQ.text.trim().toLowerCase();
      const out = [];
      events().forEach((e, i) => {
        if (listQ.only === 'left' && e.label) return;
        if (listQ.only === 'flagged'
            && !(e.label && flags.has(e.label))) return;
        if (listQ.only !== 'all' && listQ.only !== 'left'
            && listQ.only !== 'flagged' && e.label !== listQ.only) return;
        if (q) {
          const hay = [clock(e.start), e.start.toFixed(3), nameOf(e.label),
                       e.by, (e.reviews || []).map((r) => r.by).join(' ')]
            .filter(Boolean).join(' ').toLowerCase();
          if (hay.indexOf(q) < 0) return;
        }
        out.push({ e: e, i: i });
      });
      return out;
    }

    function rowFor(rec) {
      const e = rec.e;
      const revs = (e.reviews || []).filter((r) => r.by);
      return el('div', {
        class: 'cur-list-row' + (rec.i === index ? ' here' : '')
             + (e.label ? '' : ' undecided'),
        style: e.label ? '--cat:' + (colorOf(e.label) || 'var(--line)') : '',
        title: revs.length > 1
          ? 'Looked at by ' + revs.map((r) => r.by).join(', ')
          : (e.by ? 'Decided by ' + e.by : 'Nobody has decided this one'),
        onclick: () => { closeModal(); goTo(rec.i); },
      }, [
        el('span', { class: 'cl-n', text: '#' + (rec.i + 1) }),
        el('span', { class: 'cl-t', text: clock(e.start) }),
        el('span', { class: 'cl-lab',
                     text: e.label ? nameOf(e.label) : 'undecided' }),
        el('span', { class: 'cl-who', text: e.by || '' }),
        revs.length > 1
          ? el('span', { class: 'cl-revs', text: revs.length + ' reviewers' })
          : null,
        rec.i === index ? el('span', { class: 'pill sm', text: 'here' }) : null,
      ].filter(Boolean));
    }

    function paint() {
      rowsHost.innerHTML = '';
      const rows = matching();
      const count = document.getElementById('curListCount');
      if (count) {
        count.textContent = rows.length === events().length
          ? rows.length + ' candidates'
          : rows.length + ' of ' + events().length;
      }
      if (!rows.length) {
        rowsHost.appendChild(el('div', { class: 'hint',
          text: 'Nothing matches that.' }));
        return;
      }
      if (listQ.by === 'type') {
        // Undecided last: it is the work remaining, not a result.
        const order = labs.map((l) => l.id).concat(['']);
        for (const id of order) {
          const mine = rows.filter((r) => (r.e.label || '') === id);
          if (!mine.length) continue;
          rowsHost.appendChild(el('div', { class: 'cl-head' }, [
            el('span', { class: 'cl-dot',
              style: 'background:' + (colorOf(id) || 'var(--text-3)') }),
            el('strong', { text: id ? nameOf(id) : 'Undecided' }),
            el('span', { class: 'count', text: mine.length + '' }),
          ]));
          mine.forEach((r) => rowsHost.appendChild(rowFor(r)));
        }
        return;
      }
      /* By time, with a marker wherever the candidates thin out -- a
         half-minute with nothing in it is a fact about the recording. */
      let last = null;
      for (const r of rows) {
        if (last !== null && r.e.start - last > 30) {
          rowsHost.appendChild(el('div', { class: 'cl-gap',
            text: '\u2026 ' + Math.round(r.e.start - last)
                + 's with no candidates \u2026' }));
        }
        rowsHost.appendChild(rowFor(r));
        last = r.e.start;
      }
    }

    wrap.appendChild(controls);
    wrap.appendChild(chips);
    wrap.appendChild(rowsHost);
    wrap.appendChild(el('div', { class: 'modal-foot' }, [
      el('div', { style: 'flex:1' }),
      el('button', { class: 'btn', text: 'Close', onclick: closeModal }),
    ]));
    showModal(wrap);
    paint();
    // Land on where you actually are, rather than at the top of six hundred.
    const here = rowsHost.querySelector('.cur-list-row.here');
    if (here && here.scrollIntoView) {
      here.scrollIntoView({ block: 'center' });
    }
  }

  /* Banking is not instant, and the set can go away while it is being
     set up: reading the previous versions is a round trip, the dialog waits
     on a person, and leaving curation sets `set_` to null. So every step
     re-checks, and the identity is captured once at the start rather than
     read off `set_` three times.

     It used to read `set_.gid` after each await and `set_.name` inside the
     dialog. On a loaded queue the first await took twenty-one seconds, the
     user left, and the dialog threw `null.name` into the console -- outside
     the try, so nothing told them, and nothing was banked. */
  let banking = false;

  async function bank() {
    if (!set_) return;
    if (banking) {
      toast('Already opening the banking dialog\u2026', null, 2500);
      return;
    }
    const at = {
      gid: set_.gid, kind: set_.kind, name: set_.name,
      labels: (kind && kind.labels) || set_.labels || [],
      progress: { by_label: (() => {
        const t = {};
        for (const e of events()) {
          if (e.label) t[e.label] = (t[e.label] || 0) + 1;
        }
        return t;
      })(), left: left() },
    };
    /* Who is in the profile. Asking again every time was a field to retype
       and a chance to type it differently. */
    banking = true;
    try {
      const who = (BARRY.profile && BARRY.profile.who())
        || await askPath('Who is banking these?', 'your name or email', '');
      if (!who) return;
      /* What it has been banked as before, so the note is written knowing
         what it follows rather than into a blank box. */
      let known = null;
      try {
        known = await api('/api/curation/' + encodeURIComponent(at.gid) + '/'
                          + encodeURIComponent(at.kind) + '/banked');
      } catch (e) { /* never banked, or an older server; the dialog copes */ }
      const note = await bankDialog(known && known.entry, who, at);
      if (note === null) return;
      const res = await apiPost(
        '/api/curation/' + encodeURIComponent(at.gid) + '/'
        + encodeURIComponent(at.kind) + '/bank',
        { added_by: who, note: note });
      /* One entry, one version. Says which version, and what is in it, so
         the toast confirms the thing that was written rather than a count
         of records. */
      const it = res.entries[0] || {};
      const names = it.label_names || {};
      const mix = Object.keys(it.by_label || {})
        .sort((a, b) => it.by_label[b] - it.by_label[a])
        .map((k) => (names[k] || k) + ' ' + it.by_label[k])
        .join(' \u00b7 ');
      const gone = (res.removed || []).length;
      toast((it.replaced ? (it.new_version
                              ? 'Saved as version ' + it.version
                              : 'Unchanged \u2014 still version '
                                + it.version)
                         : 'Banked as version 1')
            + ': ' + it.n + ' events \u2014 ' + mix
            /* When the first bank continued the detector's export
               instead of filing beside it, say so -- otherwise the
               entry looks like it has a version 1 nobody wrote. */
            + (it.adopted ? '. Carried on from \"' + it.adopted
                            + '\", now version 1' : '')
            + (gone ? '. Folded in ' + gone + ' older entr'
                      + (gone === 1 ? 'y' : 'ies')
                      + ' this set had been split into.' : '.'),
            'ok', 9000);
      BARRY.refreshSync();
    } catch (e) {
      toast('That did not bank: ' + (e && e.message || e), 'err', 9000);
    } finally {
      banking = false;
    }
  }

  /* ==================================================================
     What the trace shows
     ================================================================== */
  /* What the last paint actually did, so "the marker vanished" can be
     measured instead of argued about. Read by web/_dev/curmarks.html. */
  let lastDraw = null;

  function draw(ctx, s, win, x0, plotW, y0, plotH, P) {
    if (!s || !s.curation || !set_) {
      lastDraw = { ok: false, why: !s ? 'no session'
                   : (!s.curation ? 'session has no curation'
                                  : 'no set loaded') };
      return;
    }
    const evs = events();
    const cur = evs[index];
    lastDraw = {
      ok: true, index, n: evs.length,
      t0: win.t0, t1: win.t1,
      current: cur ? cur.start : null,
      label: cur ? (cur.label || null) : null,
      // The one thing that matters: was the candidate being decided inside
      // the window that got painted?
      inWindow: !!(cur && cur.start >= win.t0 && cur.start <= win.t1),
      drew: 0,
    };
    const dur = win.t1 - win.t0;
    const colorOf = (id) => {
      const l = (kind.labels || []).find((x) => x.id === id);
      return l ? l.color : null;
    };

    ctx.save();
    for (let i = 0; i < evs.length; i++) {
      const e = evs[i];
      if (e.start < win.t0 || e.start > win.t1) continue;
      const x = Math.round(x0 + ((e.start - win.t0) / dur) * plotW) + 0.5;
      const isNow = i === index;
      const c = e.label ? colorOf(e.label) : P.text3 || '#7593a2';

      // The one being decided gets a full-height line; the others get a tick,
      // so the candidate in question is never ambiguous.
      ctx.globalAlpha = isNow ? 0.95 : (e.label ? 0.55 : 0.4);
      ctx.strokeStyle = isNow ? (e.label ? c : P.accent) : c;
      ctx.lineWidth = isNow ? 2 : 1;
      if (!isNow && !e.label) ctx.setLineDash([3, 3]); else ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(x, isNow ? y0 : y0 + plotH - 18);
      ctx.lineTo(x, y0 + plotH);
      ctx.stroke();
      lastDraw.drew += 1;
      if (isNow) lastDraw.drewCurrent = true;

      if (isNow) {
        ctx.setLineDash([]);
        ctx.globalAlpha = 1;
        ctx.fillStyle = e.label ? c : P.accent;
        ctx.beginPath();
        ctx.arc(x, y0 + 7, 4.5, 0, Math.PI * 2);
        ctx.fill();
        const name = e.label
          ? ((kind.labels.find((l) => l.id === e.label) || {}).name || '')
          : 'undecided';
        ctx.font = '10px ' + (P.mono || 'monospace');
        ctx.textAlign = 'center';
        ctx.fillText(name, x, y0 + 24);
      }
    }
    ctx.restore();
  }

  function clock(t) {
    const m = Math.floor(t / 60);
    const s = t - m * 60;
    return m + ':' + (s < 10 ? '0' : '') + s.toFixed(2);
  }

  return {
    enter, exit, draw, receipt,
    // Diagnostics for the marker: what the last paint saw and drew.
    lastDraw: () => lastDraw,
    at: () => index,
    /* The colour the current candidate's marker is drawn in, so a harness
       can look for it on the canvas rather than guess where it should be. */
    currentColor: () => {
      const e = events()[index];
      if (!e) return null;
      if (!e.label) return BARRY.token('--accent', '#FFB81C');
      const l = (kind.labels || []).find((x) => x.id === e.label);
      return (l && l.color) || null;
    },
    // So a harness can move the way the keyboard does.
    /* Put the current candidate back in the middle, at whatever span the
       window is now on. Called by setWindow after a zoom. */
    recentre: () => {
      if (!set_ || !sess) return;
      span = sess.span || span;
      goTo(index, true);
    },
    step: (d) => step(d),
    goTo: (i) => goTo(i),
    assign: (labelId) => assign(labelId),
    events: () => events().map((e) => ({ start: e.start, label: e.label })),
    /* Which candidates the pass currently on actually holds. "The Flagged
       pass skips the deep-review ones" is then measurable rather than a
       thing to argue about. */
    inPass: () => events().filter(wanted)
      .map((e) => ({ start: e.start, label: e.label })),
    get review() { return review; },
    /* Point at a different session object for the same recording.

       Toggling even-only reopens the recording, which replaces the session
       object. This module keeps its own reference; without being told, it
       carries on drawing onto the replaced one, and the candidate marks
       look to you like they have been lost. */
    rebind: (next) => {
      if (!next || !set_) return;
      sess = next;
      sess.curation = { kind: set_.kind, set: set_, index };
      // The marks live on the session, and this is a different session
      // object for the same recording, so they have to be put back on it.
      publishMarks();
      render();
    },
    get active() { return !!set_; },
    /* The version facts, for the harness and for anything that wants to say
       which pass is on the bench without re-deriving the lineage. */
    get version() {
      const v = verNow();
      return v ? { entry: v.entry, v: v.v, name: v.name } : null;
    },
    get banked() { return vhist; },
    switchVersion: () => switchVersion(),
    get state() {
      return set_ ? { gid: set_.gid, kind: set_.kind, index,
                      total: events().length, left: left() } : null;
    },
  };
})();

/* ==========================================================================
   BARRY.vers -- which version you are about to work on, and what that does.

   The Event Bank numbers versions with a plain integer, because the cloud
   table's `version` is an integer column and cloudsync casts to int. The
   name a person says out loud -- "1.1" -- is not that number: it is worked
   out from which version each one was banked FROM, and the rule lives in
   backend/versions.py. This is the same walk in JavaScript.

   Why here rather than asked for: the consequence of a click has to be on
   screen BEFORE the click, and there are eight radio buttons in the worst
   real case (entry 7d5fa32206b4). Asking the server what each one would be
   called if it existed is eight round trips on a network share to answer a
   question nobody has committed to yet.

   Kept in step with label_rows() in backend/versions.py, and the harness
   (_dev/curversion.html) re-derives every label the server already sent for
   every set and compares. If the two ever drift that fails loudly, rather
   than the interface quietly promising the wrong outcome.
   ========================================================================== */
BARRY.vers = (function () {
  /* "1.10" after "1.9", not before. Same reason as the Python: a history
     that lists itself in the wrong order is worse than one with no numbers
     at all. */
  function key(vid) {
    if (vid === null || vid === undefined) return [];
    const out = [];
    for (const part of String(vid).trim().replace(/^[vV]+/, '').split('.')) {
      const p = part.trim();
      if (!p) continue;
      const n = parseInt(p, 10);
      // Not a number: sorts last rather than throwing, so one odd id in a
      // history does not take the whole list down with it.
      if (!isFinite(n) || String(n) !== p) return [1e9];
      out.push(n);
    }
    return out;
  }

  const fmt = (parts) => parts.map((p) => String(Math.trunc(p))).join('.') || '0';

  const parentOf = (vid) => {
    const k = key(vid);
    return k.length > 1 ? fmt(k.slice(0, -1)) : null;
  };

  const num = (v) => {
    const n = parseInt(v, 10);
    return isFinite(n) ? n : 1e9;
  };

  const bump = (k) => k.slice(0, -1).concat([k[k.length - 1] + 1]);

  /* [{row, name}] in creation order, for one entry's whole history.

     Rows rather than a lookup keyed on the version number, because that
     number is not unique in this bank: entry 7d5fa32206b4 holds seven
     versions numbered 0,1,2,3,4,3,4 -- two machines minted 3 and 4
     independently and the union rightly kept both. Keyed on the number,
     two of those would share a name and a third would vanish from the list. */
  function labelRows(rows) {
    const got = (rows || []).slice().sort((a, b) => {
      const d = num(a.v) - num(b.v);
      if (d) return d;
      const x = String(a.at || ''), y = String(b.at || '');
      return x < y ? -1 : x > y ? 1 : 0;
    });
    const name = {}, kids = {}, used = new Set();

    /* The name, or the next one along if something already holds it. Two
       versions with one name is worse than an ugly name -- the history gets
       read to settle which pass a number refers to, and a duplicate makes
       that unanswerable. */
    const take = (want) => {
      let k = key(want);
      while (used.has(fmt(k))) k = bump(k);
      const got_ = fmt(k);
      used.add(got_);
      return got_;
    };

    let trunk = 0;
    const out = [];
    for (const r of got) {
      let nm;
      const par = r.from_v;
      if (par === null || par === undefined || !(par in name)) {
        // A root. The detector's import is 0 and the first pass is 1; a
        // version whose parent this machine has never seen is treated as one
        // rather than dropped, because a branch can arrive from the cloud
        // ahead of what it came from and still has to appear.
        nm = take(String(trunk));
        trunk = key(nm)[key(nm).length - 1] + 1;
      } else {
        const seen = kids[par] || 0;
        kids[par] = seen + 1;
        const base = key(name[par]);
        // Nothing built on the parent yet means continue its line; something
        // already built on it means branch. That is the whole rule.
        nm = take(seen === 0 ? fmt(bump(base)) : fmt(base.concat([seen])));
      }
      name[r.v] = nm;
      out.push({ row: r, name: nm });
    }
    return out;
  }

  /* What banking after picking `row` up would produce.

     Simulated by re-walking the history with one extra row on the end,
     rather than reasoned about. The name depends both on how many versions
     already sit on the same parent and on which names are already taken, and
     a shortcut gets the second one wrong: on the demo entry, where no
     version records what it came from, picking up v1 continues the trunk at
     5 because 2, 3 and 4 are spoken for -- not at 2. */
  function nextFor(rows, row) {
    const all = rows || [];
    const top = all.reduce((hi, r) => Math.max(hi, num(r.v)), -1);
    const probe = { v: top + 1, from_v: row.v, at: '9999', _probe: true };
    const named = labelRows(all.concat([probe]));
    const mine = named.find((x) => x.row._probe);
    const was = named.find((x) => x.row === row);
    const from = was ? was.name
                     : String(row.label != null ? row.label : row.v);
    const to = mine ? mine.name : '';
    return { from, to, branches: parentOf(to) !== parentOf(from) };
  }

  /* The same sentence backend/versions.py describe() produces, because it is
     the sentence the user asked for: the consequence, not the number. */
  function describe(rows, row) {
    const n = nextFor(rows, row);
    return n.branches
      ? 'branches off v' + n.from + ' as v' + n.to
        + ', leaving what came after it alone'
      : 'continues from v' + n.from + ' as v' + n.to;
  }

  /* What a fresh pick-up defaults to: the highest stored number, which is
     what the server's based_on_default() picks and so what happens if this
     sends nothing. The highest LABEL would be a different row -- "1.10" and
     "2" are not comparable as lineage, and the question being answered is
     "what did I last see", which is about time. */
  function newest(rows) {
    let best = null;
    for (const r of (rows || [])) if (!best || num(r.v) >= num(best.v)) best = r;
    return best;
  }

  const usable = (rows) => (rows || []).filter((r) => r.has_snap);

  /* Does this set have anything worth asking about? One version is not a
     choice, and a set nobody has ever banked has no versions at all -- 1 of
     the 45 sets here is in that state and must keep picking up in one click. */
  function askable(history) {
    let n = 0;
    for (const e of (history || [])) n += usable(e.versions).length;
    return n > 1;
  }

  /* ------------------------------------------------------------------
     The list on screen
     ------------------------------------------------------------------
     Deliberately the same object as the "New curation set" wizard's version
     step -- .bm-row, .ver-n, ' off' for one that cannot be used -- because
     it is the same question asked in a second place, and two visual
     languages for one question is how people learn to distrust both.

     `mode` is 'pickup' or 'switch', and the only difference is what it says
     about the decisions that are already there. Switching always puts that
     version's decisions on the bench; picking up only does so when the
     chosen version is not the one the set already reflects. */
  let seq = 0;

  function chooser(history, opts) {
    const o = opts || {};
    const labs = o.labels || [];
    const nameOf = (id) => (labs.find((l) => l.id === id) || {}).name
                        || (id === 'unspecified' ? 'undecided' : id);
    const group = 'verpick' + (++seq);
    const said = el('div', { class: 'ver-said' });
    const host = el('div', { class: 'ver-pick' });
    const marks = [];             // [rowNode, choice] so `on` can move
    let pick = null;

    const entries = (history || []).filter((e) => (e.versions || []).length);
    const many = entries.length > 1;

    const announce = () => {
      for (const [node, ch] of marks) {
        /* Matched on the version ITSELF, not on its number.
           The stored number is not unique -- two machines curating one
           entry both mint the next one and the union keeps both, which is
           what the per-version id exists for -- so `ch.v === pick.v` lit up
           every row sharing a number. On an entry holding two v1s that is
           two rows highlighted and one radio filled, which reads as the
           dialog having lost track of what you picked.

           `ch.row` is the version object the row was built from, so
           identity settles it and needs no id to be present: the histories
           that predate ids are exactly the ones most likely to collide. */
        node.classList.toggle('on', !!pick && ch.row === pick.row);
      }
      said.innerHTML = '';
      if (pick) {
        said.appendChild(el('p', { class: 'confirm-sub',
                                   text: pick.lineage }));
        said.appendChild(el('p', {
          class: 'confirm-sub' + (pick.restores ? ' warn' : ''),
          text: pick.bench }));
        if (pick.row.note) {
          said.appendChild(el('p', { class: 'hint',
                                     text: '“' + pick.row.note + '”' }));
        }
      }
      if (typeof o.onpick === 'function') o.onpick(pick);
    };

    for (const ent of entries) {
      const rows = ent.versions || [];
      const tip = newest(rows);
      if (many) {
        host.appendChild(el('div', { class: 'section-label',
          text: ent.name + '  ·  ' + (ent.n || 0) + ' candidates' }));
      }
      const list = el('div', { class: 'bm-list ver-pick-list' });
      for (const v of rows) {
        const nxt = nextFor(rows, v);
        const restores = o.mode === 'switch' || v !== tip;
        const here = o.current && o.current.entry === ent.entry
                  && o.current.v === v.v;
        const choice = {
          entry: ent.entry, v: v.v, row: v, name: nxt.from, next: nxt.to,
          branches: nxt.branches, restores,
          lineage: 'Banking after this ' + describe(rows, v) + '.',
          bench: restores
            ? 'The decisions on the set are replaced by v' + nxt.from
              + '’s — ' + (v.n || 0) + ' candidate(s) re-stamped '
              + 'from its snapshot. Anything decided since then and never '
              + 'banked goes with it.'
            : 'The decisions already on the set are left exactly as they '
              + 'are. This only says where the next bank lands.',
        };
        const mix = Object.keys(v.by_label || {})
          .sort((a, b) => v.by_label[b] - v.by_label[a])
          .map((k) => nameOf(k) + ' ' + v.by_label[k]).join('  ·  ');
        const row = el('label', {
          class: 'bm-row' + (v.has_snap ? '' : ' off'),
          title: v.has_snap ? null
            : 'Only the recent versions keep a candidate-by-candidate '
              + 'snapshot. Without one there is nothing to put on the '
              + 'bench, so this version cannot be a starting point — '
              + 'its counts and its note are still here.',
        }, [
          el('input', {
            type: 'radio', name: group,
            disabled: v.has_snap ? null : 'disabled',
            onchange: () => { pick = choice; announce(); },
          }),
          el('span', { class: 'ver-n', text: 'v' + nxt.from }),
          v.imported ? el('span', { class: 'flagchip', text: 'the detector' })
                     : null,
          here ? el('span', { class: 'flagchip on-bench', text: 'on the bench' })
               : null,
          el('div', { class: 'ver-pick-mid' }, [
            el('span', { class: 'mk-name', text: mix || (v.n || 0) + ' events' }),
            /* The consequence on every row, not only the chosen one. Which
               version you are about to make is the thing being decided, and
               it cannot be the thing you find out afterwards. */
            el('span', { class: 'ver-does' + (nxt.branches ? ' branch' : ''),
              text: v.has_snap ? describe(rows, v)
                               : 'no snapshot kept — cannot be worked from' }),
          ]),
          el('span', { class: 'person-what',
            text: (v.by || 'unknown') + '  ·  '
                + (BARRY.when ? BARRY.when(v.at, 'minute') : (v.at || '')) }),
        ].filter(Boolean));
        marks.push([row, choice]);
        list.appendChild(row);
        if (o.start && o.start(v, ent, tip)) {
          const box = row.querySelector('input');
          if (box && !box.disabled) { box.checked = true; pick = choice; }
        }
      }
      host.appendChild(list);
    }

    const wrap = el('div', {}, [host, said]);
    announce();
    return { node: wrap, get pick() { return pick; } };
  }

  return { key, fmt, parentOf, labelRows, nextFor, describe, newest,
           usable, askable, chooser };
})();

/* ==========================================================================
   Asking which version -- the dialog both doors use.

   Two doors lead here: picking a set up off the ToolKit shelf, and switching
   while it is already on the bench. Same list, same rules, different weight
   -- switching replaces what is on the bench, so its button is the danger
   one and the sentence under the list says so before it is pressed.

   Resolves to the chosen {entry, v, name, restores} or to null.
   ========================================================================== */
BARRY.pickVersion = function pickVersion(history, opts) {
  const o = opts || {};
  return new Promise((resolve) => {
    let settled = false;
    const done = (val) => {
      if (settled) return;
      settled = true;
      closeModal();
      resolve(val);
    };

    const ok = el('button', { class: 'btn' + (o.danger ? ' danger' : ''),
                              text: o.okLabel || 'Use this version' });
    const pick = BARRY.vers.chooser(history, {
      labels: o.labels,
      mode: o.mode,
      current: o.current,
      /* Default to the newest, which is what happens anyway if nothing is
         sent -- so the default choice and the default behaviour agree. A
         version with no snapshot cannot take the default, and the dialog
         then opens with nothing chosen rather than with something that
         would fail at the click. */
      start: (v, ent, tip) => v === tip,
      onpick: (p) => {
        ok.disabled = p ? null : 'disabled';
        ok.textContent = p
          ? (o.verb || 'Use') + ' v' + p.name
          : (o.okLabel || 'Use this version');
      },
    });
    ok.addEventListener('click', () => done(pick.pick));

    /* mh / mb / mf, not a nested .modal. showModal drops whatever it is
       given straight into #bigModalBox, which is itself .modal.big and the
       flex column -- its three parts have to be that column's children or
       the body does not scroll and the footer falls out the bottom. */
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: o.title || 'Which version to work from' }),
        o.sub ? el('span', { class: 'sub', text: o.sub }) : null,
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: () => done(null),
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ].filter(Boolean)),
      el('div', { class: 'mb' }, [
        el('div', { class: 'ver-pick-wrap' }, [
          o.lead ? el('p', { class: 'confirm-msg', text: o.lead }) : null,
          pick.node,
        ].filter(Boolean)),
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel',
                       onclick: () => done(null) }),
        ok,
      ]),
    ]));
  });
};
