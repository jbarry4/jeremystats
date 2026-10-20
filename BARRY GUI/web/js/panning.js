/* ==========================================================================
   panning.js -- Panning, step 2 of The Confluence: sort them.

   Prospectors pan a river for what is worth keeping, and that is the job:
   Junction has poured Incisor's dentate spikes and Doppler's discharges
   into one pool, and each event in it is a spike, or garbage, or one to
   come back to. 1 Spike, 2 Garbage, 3 Flag -- the `pooled` vocabulary in
   curation.py, whose first keys these are.

   IT IS A MODE, SHAPED LIKE SPOTTER
   The same curation machinery -- sets, the bench, presence, per-machine
   shards, versions -- and Spotter's keyboard, bar and aid window. What
   differs is the question, so what is on screen differs:

     WHERE IT CAME FROM is always visible. Every event is drawn in its
     detector's colour -- Incisor's, Doppler's -- and an event both found
     is drawn in both, two-tone, with Doppler's own stamp shown beside the
     one it kept (Incisor's). The same two colours the ToolKit's stream and
     Root Canal use.

     TWO EVENTS CAN BE MADE ONE. The window strip under the traces lays out
     the events in view on two lanes, Incisor's above Doppler's: click one,
     shift-click another, press M. Without a second one picked, M takes the
     nearest. The survivor is whichever carries Incisor's time, so no stamp
     ever moves; Z undoes it, and there is no split -- a merge undone is the
     undo (decided with the user, 2026-10-14).

     PASSES BY ORIGIN as well as by decision: All, Merged, Incisor only,
     Doppler only -- so "what did only Doppler see" is one click.

   ADDED 2026-10-19, asked for in so many words:
     MERGE TO INCISOR OR TO DOPPLER. M keeps Incisor's time, as before; D
     keeps Doppler's. Either way the survivor is the candidate already
     carrying that time, so still no stamp moves -- and the event says
     whose it is (`stamp: 'doppler'`), so its two times are never read the
     wrong way round. A pool Junction made at Doppler's time arrives the
     same way.
     LABEL MANY at once: "every merged and every Incisor-only one is a
     spike" is one write and one Z, from Label many… or from the list.
     THE LIST: every event in the pool, by time, decision or origin,
     searchable -- Checkup's List all, with where each came from on it.
   ========================================================================== */
'use strict';

BARRY.panning = (function () {
  /* The kind of every pool's set, and the set's OWN kind (2026-10-20):
     "pooled" for an older set -- one per recording -- or "pooled.e<entry>"
     for the set of one pool. Every route is asked with the set's own. */
  const KIND = 'pooled';
  let setKind = KIND;
  const $ = (s) => document.querySelector(s);

  let set_ = null;      // the curation set as the server has it
  let kind = null;      // { id, labels[] } -- COPIED from the set
  let sess = null;      // the open xplore session
  let index = 0;
  let span = 1.0;
  let banked = null;    // what the bank holds of this set (api _cur_banked)
  let bankDirty = false; // a decision or merge made since `banked` was read
  let history = [];     // [{type:'label', id, from} | {type:'merge', ...}]
  let review = 'left';  // 'left' | 'flag' | 'all'
  let origin = 'all';   // 'all' | 'both' | 'incisor' | 'doppler'
  let mark = null;      // the second event picked for a merge (its id)
  let markRev = 0;
  let lastChange = null;
  let saving = 0;
  let aidWin = null;
  let beatTimer = null;
  let beatOthers = [];
  let toldAbout = new Set();
  let decidedAtEntry = 0;
  let lastWin = null;   // the trace window as last drawn: {t0, t1}
  let fuse = null;      // a merge being drawn on the window strip

  const PRESENCE_BEAT = 60000;
  const FUSE_MS = 280;
  const FAR_MS = 50;    // a nearest neighbour further than this is asked about

  const tok = (n, d) => BARRY.token(n, d);
  const oCol = (o) => (o === 'doppler' ? tok('--o-doppler', '#f59fb4')
                                       : tok('--o-incisor', '#8ec5ff'));
  const ORIGIN_WORD = { incisor: 'Incisor', doppler: 'Doppler', both: 'both' };

  /* Whose stamp an event's `start` is: 'incisor', 'doppler', or null when
     its origin is not known. One both detectors found is Incisor's unless
     it says Doppler's (curation._stamp_of, the same rule). */
  const stampOf = (e) => {
    if (!e) return null;
    if (e.origin === 'both') return e.stamp === 'doppler' ? 'doppler' : 'incisor';
    return e.origin === 'incisor' || e.origin === 'doppler' ? e.origin : null;
  };
  /* The time `who` put on it, or null when that detector did not find it.
     An event of no known origin is drawn as Incisor's, as it always was. */
  const timeBy = (e, who) => {
    const s = stampOf(e) || 'incisor';
    if (s === who) return e.start;
    if (e.origin === 'both') return e.pair_t != null ? e.pair_t : e.start;
    return null;
  };
  const otherOf = (who) => (who === 'doppler' ? 'incisor' : 'doppler');
  const KEEP_WORD = { incisor: 'Incisor', doppler: 'Doppler' };
  const fx = () => BARRY.jarvisfx || window.JarvisFX || null;
  const sfx = (name, a) => {
    try { const f = fx(); if (f && !f.muted && f[name]) f[name](a); }
    catch (e) { /* a decoration never stops anything */ }
  };
  const reduced = () => !!(BARRY.ui.reducedMotion && BARRY.ui.reducedMotion());

  const clock = (t) => {
    if (t == null) return '—';
    const s = Math.max(0, Number(t));
    const m = Math.floor(s / 60);
    return m + ':' + String((s - m * 60).toFixed(3)).padStart(6, '0');
  };
  const url = (what) => BARRY.ui.setUrl(set_.gid, setKind, what || null);

  const events = () => (set_ && set_.events) || [];
  const current = () => events()[index] || null;
  const left = () => events().filter((e) => !e.label).length;

  const flagIds = () => {
    const out = new Set();
    for (const l of (kind && kind.labels) || []) {
      if (l.flagged || l.id === 'flag') out.add(l.id);
    }
    return out;
  };
  const byOrigin = (ev, o) => {
    const want = o || origin;
    return want === 'all' || ev.origin === want;
  };
  const byDecision = (ev) => {
    if (review === 'all') return true;
    if (review === 'flag') return !!ev.label && flagIds().has(ev.label);
    return !ev.label;
  };
  const wanted = (ev) => !!ev && byDecision(ev) && byOrigin(ev);
  const nWanted = () => events().filter(wanted).length;
  const nOrigin = (o) => events().filter((e) => byDecision(e)
                                         && byOrigin(e, o)).length;

  /* ==================================================================
     Entering and leaving
     ================================================================== */
  /* `entryId` is the pool's bank entry: its set is opened, and made first
     if there is none. `opts.kind` opens a set by its kind -- the
     workbench's way in. */
  async function enter(gid, entryId, opts) {
    BARRY.modes.leaveAllBut('panning');
    if (set_) exit();
    let want = (opts && opts.kind) || KIND;
    if (entryId) {
      const made = await ensureSet(gid, entryId);
      if (!made) return false;
      want = made;
    }
    let data;
    try {
      data = await api(BARRY.ui.setUrl(gid, want));
    } catch (e) {
      toast('Could not open that pool: ' + e.message, 'err', 9000);
      return false;
    }
    if (!data.set) {
      toast('Nothing has been pooled for that recording yet. Pool it in '
            + 'Junction first.', 'warn', 9000);
      return false;
    }
    set_ = data.set;
    setKind = set_.kind || want;
    kind = { id: set_.kind, labels: set_.labels || [] };

    const got = BARRY.vacc.reachFor(
      Object.assign({ gid: gid }, data.session || {}), 'panning');
    if (!got.path) {
      toast(got.why || ('None of this recording’s paths are reachable '
            + 'from this machine, so there is nothing to look at.'), 'err', 9000);
      set_ = null;
      return false;
    }
    setView('xplore');
    sess = await BARRY.views.xplore.open(got.path);
    if (!sess) { set_ = null; return false; }

    /* The width somebody last looked at events with, and 1 s the first
       time -- the same as Spotter and Checkup. It was 0.6 s and was put
       back on every event, whatever the span field had been set to. */
    span = (opts && opts.span)
        || parseFloat(BARRY.prefs.get('panning_span', 0)) || 1.0;
    if (!(span > 0)) span = 1.0;
    index = 0; history = []; review = 'left'; origin = 'all'; mark = null;
    lastWin = null;
    banked = data.banked || null;
    bankDirty = false;

    apiPost(url('open'), { open: true })
      .then((r) => { if (r && r.set) set_.assignee = r.set.assignee; })
      .catch(() => {});

    setMode('panning', exit);
    useBand();
    layout();
    sess.curation = { kind: set_.kind, set: set_, index: 0 };
    publishMarks();

    if (!events().some((e) => !e.label)) {
      review = events().some((e) => e.label && flagIds().has(e.label))
        ? 'flag' : 'all';
    }
    const back = recallWhere();
    if (back) {
      const was = [review, origin];
      review = back.review; origin = back.origin || 'all';
      if (!nWanted()) { review = was[0]; origin = was[1]; }
      goTo(back.index, true, true);
      const at = events().slice(0, index + 1).filter(wanted).length;
      toast(back.gone
        ? 'Back where you were — that one is no longer in this pool, so '
          + 'this is the next along (' + at + ' of ' + nWanted() + ').'
        : 'Back where you left off: ' + at + ' of ' + nWanted() + '.',
        null, 5000);
    } else {
      goTo(firstWanted(), true, true);
    }
    render();

    BARRY.activity.log('panning.enter', {
      gid, n: events().length, left: left(),
    }, sess);
    decidedAtEntry = events().filter((e) => e.label).length;
    beatOthers = []; toldAbout = new Set();
    beat(true);
    if (beatTimer) clearInterval(beatTimer);
    beatTimer = setInterval(() => { if (!away()) beat(false); }, PRESENCE_BEAT);
    return true;
  }

  function away() {
    return BARRY.idle ? BARRY.idle.away() : document.hidden;
  }
  if (BARRY.idle) {
    BARRY.idle.onWake(() => { if (beatTimer && set_) beat(false); });
  }

  /* The set that stands for this pool, made if there is none, and its kind
     returned (null when somebody was asked and called it off). A set
     belongs to ONE bank entry since 2026-10-20, so a second pool on a
     recording makes a second set and replaces nothing. */
  async function ensureSet(gid, entryId) {
    try {
      const have = await BARRY.ui.setForEntry(gid, KIND, entryId);
      if (have) return have;
    } catch (e) { /* no set is the ordinary case */ }
    const pick = await chooseVersion(gid, entryId);
    if (pick === null) return null;
    let res;
    try {
      res = await apiPost('/api/curation/from-bank', {
        gid, kind: KIND, entry: entryId, open: true,
        version: pick && pick.id != null ? pick.id : (pick ? pick.v : 0),
      });
    } catch (e) {
      const d = e && e.data;
      if (d && d.exists && d.kind) return d.kind;
      toast('Could not make a set from that pool: ' + e.message, 'err', 9000);
      return null;
    }
    return res.kind || KIND;
  }

  async function chooseVersion(gid, entryId) {
    let info = null;
    try {
      info = await api('/api/curation/for-recording/' + encodeURIComponent(gid));
    } catch (e) { return false; }
    const ent = ((info && info.entries) || []).find((e) => e.id === entryId);
    const vs = (ent && ent.versions) || [];
    const usable = vs.filter((v) => v.usable);
    if (!usable.length) return false;
    let pick = usable[0];
    if (usable.length === 1) return pick;
    const names = ent.label_names || {};
    const nameOf = (k) => names[k] || (k === 'unspecified' ? 'undecided' : k);
    const said = el('p', { class: 'confirm-msg' });
    const say = () => {
      const decided = Object.keys(pick.by_label || {})
        .filter((k) => k !== 'unspecified')
        .reduce((n, k) => n + pick.by_label[k], 0);
      said.textContent = 'The set will start from ' + BARRY.ui.versionLabel(pick)
        + ': ' + (pick.n || 0) + ' event(s)'
        + (decided ? ', ' + decided + ' already decided.'
                   : ', none decided — a fresh pass.');
    };
    say();
    const ok = await BARRY.confirm('Which version to start from',
      el('div', { class: 'spot-vers' }, [
        el('p', { class: 'hint', text: (ent.name || 'This pool') + ' has been '
            + 'worked on before. v0 is Junction’s pool, nothing decided; '
            + 'a later one carries the decisions made in it.' }),
        BARRY.ui.versionTree({
          versions: vs,
          idOf: (v) => (v.id != null ? v.id : 'v' + v.v),
          value: pick.id != null ? pick.id : 'v' + pick.v,
          disabled: (v) => (v.usable ? null : 'no snapshot kept — a set '
                                            + 'cannot be built from it'),
          state: (v) => (v.imported ? ['Junction’s pool'] : []),
          notes: (v) => Object.keys(v.by_label || {})
            .sort((a, b) => v.by_label[b] - v.by_label[a])
            .map((k) => nameOf(k) + ' ' + v.by_label[k]).join('  ·  ')
            || ((v.n || 0) + ' events'),
          onpick: (v) => { pick = v; say(); },
        }),
        said,
      ]), 'Start from this version');
    return ok ? pick : null;
  }

  function exit() {
    if (!set_) return;
    /* Leaving with decisions or merges the bank does not have: banked on
       the way out, when that is on (quietBank, below). */
    {
      const decided = events().filter((e) => e.label).length;
      if (autoOn() && decided
          && (bankDirty || !banked || banked.changed)) {
        quietBank(set_.gid, 'Banked on leaving Panning.', setKind);
      }
    }
    rememberWhere();
    try { BARRY.prefs.flush(); } catch (e) { /* the timer will get it */ }
    BARRY.activity.log('panning.leave', { gid: set_.gid, left: left() }, sess);
    if (beatTimer) { clearInterval(beatTimer); beatTimer = null; }
    apiPost('/api/presence/release', { gid: set_.gid, kind: setKind })
      .catch(() => {});
    beatOthers = [];
    if (sess) { delete sess.curation; delete sess.curationMarks; }
    restoreBand();
    if (sess && BARRY.views.xplore.publishCuration) {
      BARRY.views.xplore.publishCuration(sess, null);
    }
    if (aidWin && !aidWin.closed) { try { aidWin.close(); } catch (e) {} }
    aidWin = null;
    if (sess && BARRY.views.xplore.setChannelLines) {
      BARRY.views.xplore.setChannelLines(sess, []);
    }
    setMode(null);
    receipt(set_.gid, { quiet: true });
    if (BARRY.views.toolkit && BARRY.views.toolkit.curationChanged) {
      BARRY.views.toolkit.curationChanged();
    }
    set_ = null; kind = null; sess = null;
    history = []; mark = null; lastWin = null; fuse = null;
    for (const id of ['#panBar', '#panWin', '#panAll']) {
      const n = $(id);
      if (n) n.remove();
    }
    document.removeEventListener('keydown', keys, true);
    if (BARRY.views.xplore.refreshAll) BARRY.views.xplore.refreshAll();
  }

  /* Through the IED band, for the reason Spotter gives: a pooled set holds
     discharges, and a discharge judged through the dentate-spike band has
     lost its slow wave. A dentate spike keeps its shape in this band. Put
     back on the way out, never saved. */
  let prevBand = null;
  const IED_FALLBACK = { highpass: 1, lowpass: 70, notch: 60 };

  function useBand() {
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
    ], { role: 'aids', name: 'barry-panning-aids', width: 720, height: 980,
         chrome: 'notabs,noheads,nostrip,nochannels' });
  }

  /* ==================================================================
     Moving
     ================================================================== */
  function firstWanted() {
    const i = events().findIndex(wanted);
    return i < 0 ? 0 : i;
  }

  /* The span, and the one place it is written down: per machine, in
     preferences (`panning_span` is in PREFS_LOCAL), because how wide
     somebody likes the window is about this screen. */
  function setSpan(v) {
    const want = Math.max(0.05, parseFloat(v) || 1);
    if (Math.abs(want - span) < 1e-6) return;
    span = want;
    try { BARRY.prefs.set('panning_span', span); } catch (e) { /* later */ }
  }

  /* What the pane is actually showing -- Checkup's `paneSpan`, for the
     reason it gives: the mode centres the window on each event, and doing
     that with its own remembered span undid every zoom and every span
     typed into the field the moment the next event came up. */
  function paneSpan() {
    try {
      const XF = BARRY.views.xplore.state;
      const pane = (XF.panes || [])[0];
      const s = (XF.linkMode === 'none' && pane && pane.t0 != null)
        ? pane.span : (sess ? sess.span : null);
      return (s > 0) ? s : null;
    } catch (e) {
      return null;
    }
  }

  function goTo(i, quiet, ownSpan) {
    const n = events().length;
    if (!n) return;
    index = Math.max(0, Math.min(n - 1, i));
    const ev = current();
    if (!ev || !sess) return;
    publishMarks();
    // Somebody zoomed the pane or typed a span: that is the window they
    // want, so take it rather than putting it back. Only a real change --
    // the centring below sets the span itself, and the edge of a recording
    // can trim it a little.
    // Not on the way in: the pane then still shows whatever the recording
    // was last looked at with, and the span this mode remembers wins.
    const shown = ownSpan ? null : paneSpan();
    if (shown && Math.abs(shown - span) > Math.max(0.02, span * 0.02)) {
      setSpan(shown);
    }
    BARRY.views.xplore.setWindow(0, Math.max(0, ev.start - span / 2), span);
    lightChannel(ev);
    if (!quiet) render();
    drawStrips();
    warmAhead();
  }

  /* The channel the event was stamped on, in its detector's colour. */
  function lightChannel(ev) {
    if (!BARRY.views.xplore.setChannelLines || !sess) return;
    if (!ev || ev.channel == null) {
      BARRY.views.xplore.setChannelLines(sess, []);
      return;
    }
    BARRY.views.xplore.setChannelLines(sess, [{
      key: 'pan' + ev.channel, number: Number(ev.channel), style: 'mark',
      alpha: 0.2, colour: oCol(ev.origin), label: 'CSC' + ev.channel,
    }]);
  }

  function warmAhead() {
    if (!BARRY.views.xplore.prewarm) return;
    const all = events();
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
    mark = null;
    goTo(i);
  }

  /* ==================================================================
     Deciding
     ================================================================== */
  async function assign(labelId) {
    const ev = current();
    if (!ev) return;
    const was = ev.label || null;
    ev.label = labelId;
    bankDirty = true;
    const h = { type: 'label', id: ev.id, from: was };
    history.push(h);
    if (history.length > 500) history.shift();
    markRev += 1;
    lastChange = { index, label: labelId };
    publishMarks({ local: true });
    render();
    step(1);
    saving += 1; updateSaving();
    try {
      const res = await apiPost(url('label'), { event: ev.id, label: labelId });
      if (res.progress) set_._progress = res.progress;
      // The last one decided: bank it, if banking without asking is on.
      if (set_ && autoOn() && !left()) {
        quietBank(set_.gid, 'Every event decided in Panning.', setKind);
      }
      if (BARRY.views.toolkit && BARRY.views.toolkit.curationChanged) {
        BARRY.views.toolkit.curationChanged();
      }
    } catch (e) {
      ev.label = was;
      const back = history.indexOf(h);
      if (back >= 0) history.splice(back, 1);
      markRev += 1;
      publishMarks();
      if (/no curation set/i.test(e.message || '')) {
        toast('That set has been deleted, so there is nothing to save into. '
              + 'Leaving Panning.', 'err', 9000);
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
    const was = ev.label;
    ev.label = null;
    bankDirty = true;
    const h = { type: 'label', id: ev.id, from: was };
    history.push(h);
    markRev += 1;
    publishMarks(); render();
    try {
      await apiPost(url('label'), { event: ev.id, label: null });
    } catch (e) {
      ev.label = was;
      history.splice(history.indexOf(h), 1);
      publishMarks(); render();
      toast('That did not save: ' + e.message, 'err', 8000);
    }
  }

  /* ==================================================================
     Merging
     ================================================================== */

  /* Which of two survives: the server's rule (curation.merge_events), so
     the optimistic step and the write agree. `want` is whose time to keep,
     Incisor's unless D asked for Doppler's: the one already carrying it
     survives, else the earlier. */
  function leadOf(a, b, want) {
    const w = want || 'incisor';
    const ha = stampOf(a) === w, hb = stampOf(b) === w;
    if (hb && !ha) return b;
    if (ha || a.start <= b.start) return a;
    return b;
  }

  /* Whether a merge can keep `want`'s time: one of the two has to carry it.
     Incisor's is always offered -- with neither carrying it, the earlier
     survives, which is the rule for two of Doppler's. */
  function canKeep(a, b, want) {
    if (!a || !b) return false;
    if (want !== 'doppler') return true;
    return stampOf(a) === 'doppler' || stampOf(b) === 'doppler';
  }

  function nearestOther(a) {
    const evs = events();
    const i = evs.indexOf(a);
    const cand = [evs[i - 1], evs[i + 1]].filter(Boolean);
    cand.sort((x, y) => Math.abs(x.start - a.start) - Math.abs(y.start - a.start));
    return cand[0] || null;
  }

  function partner() {
    const a = current();
    if (!a) return null;
    if (mark) {
      const b = events().find((e) => e.id === mark);
      if (b && b !== a) return b;
    }
    return nearestOther(a);
  }

  const KEEP = ['origin', 'pair_t', 'stamp', 'label', 'by', 'at', 'channel',
                'merged_by', 'merged_at'];
  const BACK = ['start', 'end', 'channel', 'amplitude', 'origin', 'pair_t',
                'stamp', 'label', 'by', 'at', 'note'];
  const pickOf = (e, keys) => {
    const out = {};
    for (const k of keys) if (e[k] !== undefined && e[k] !== null) out[k] = e[k];
    return out;
  };

  async function merge(want) {
    const keepT = want === 'doppler' ? 'doppler' : 'incisor';
    const a = current();
    const b = partner();
    if (!a || !b) {
      toast('There is nothing next to this one to merge it with.', null, 4000);
      return;
    }
    if (!canKeep(a, b, keepT)) {
      toast('Neither of these two carries Doppler’s time, so there is no '
            + 'Doppler stamp to merge to. M merges them at Incisor’s.',
            'warn', 6000);
      return;
    }
    const gap = Math.abs(b.start - a.start) * 1000;
    if (!mark && gap > FAR_MS) {
      const ok = await BARRY.confirm(
        'Merge two events ' + gap.toFixed(1) + ' ms apart?',
        el('p', { text: 'The nearest other event is ' + gap.toFixed(1)
            + ' ms away — further than two detectors usually disagree '
            + 'about one event. Shift-click the one you mean on the strip '
            + 'under the traces to be sure.' }),
        'Merge them');
      if (!ok) return;
    }
    const lead = leadOf(a, b, keepT);
    const other = lead === a ? b : a;
    const before = pickOf(lead, KEEP);
    const dropped = pickOf(other, BACK);
    const dropAt = events().indexOf(other);
    const fromX = other.start;
    const leadStamp = stampOf(lead);

    // Optimistic, as the server will do it.
    if (!lead.label && other.label) {
      lead.label = other.label;
      if (other.by) lead.by = other.by;
      if (other.at) lead.at = other.at;
    }
    lead.pair_t = other.start;
    const srcs = new Set();
    for (const o of [lead.origin, other.origin]) {
      if (o === 'both') { srcs.add('incisor'); srcs.add('doppler'); }
      else if (o) srcs.add(o);
    }
    if (srcs.size) lead.origin = srcs.size > 1 ? 'both' : [...srcs][0];
    // Which of its two times `start` is, once it has two detectors'.
    if (lead.origin === 'both' && leadStamp) lead.stamp = leadStamp;
    if (lead.channel == null && other.channel != null) lead.channel = other.channel;
    lead.merged_at = new Date().toISOString();
    events().splice(dropAt, 1);
    index = Math.max(0, events().indexOf(lead));
    const h = { type: 'merge', keep: lead.id, before, dropped, dropId: other.id };
    history.push(h);
    mark = null;
    markRev += 1;
    lastChange = { index, merged: true };
    fuse = { from: fromX, to: lead.start, at: performance.now(),
             o: other.origin };
    sfx('select');
    bankDirty = true;
    /* Bring up what comes next, the way a decision does. It used to stay
       put without redrawing, so the traces still showed the event that had
       just gone and nothing moved until an arrow was pressed.

       Which "next" depends on what is left to do here: a survivor that is
       already decided -- you called it and then merged its twin into it --
       is done, so the next event of this pass comes up; one that is still
       undecided stays, centred and redrawn as one event, to be called. */
    let to = index;
    if (lead.label) {
      const evs = events();
      for (let i = index + 1; i < evs.length; i++) {
        if (wanted(evs[i])) { to = i; break; }
      }
    }
    goTo(to);
    animateFuse();

    saving += 1; updateSaving();
    try {
      const res = await apiPost(url('merge'), { keep: a.id, drop: b.id,
                                                stamp: keepT });
      if (res.event) Object.assign(lead, res.event);
      if (res.progress) set_._progress = res.progress;
      if (res.dropped && res.dropped !== other.id) {
        // The server chose otherwise; its answer is the truth.
        await reload();
      } else if (set_) {
        render();          // who merged it, as the server stamped it
      }
      BARRY.activity.log('panning.merge', { gid: set_.gid, kept: lead.id,
                                            gap_ms: +gap.toFixed(2),
                                            stamp: keepT }, sess);
      if (BARRY.views.toolkit && BARRY.views.toolkit.curationChanged) {
        BARRY.views.toolkit.curationChanged();
      }
    } catch (e) {
      // Everything the optimistic step did, put back.
      for (const k of KEEP) {
        if (before[k] !== undefined) lead[k] = before[k];
        else if (k === 'label') lead.label = null;
        else delete lead[k];
      }
      events().splice(dropAt, 0, other);
      const back = history.indexOf(h);
      if (back >= 0) history.splice(back, 1);
      markRev += 1;
      goTo(events().indexOf(a));
      toast('That merge did not save: ' + e.message, 'err', 8000);
    } finally {
      saving -= 1; updateSaving();
    }
  }

  async function reload() {
    try {
      const got = await api(url(''));
      if (got.set) {
        const at = (current() || {}).id;
        set_ = got.set;
        kind = { id: set_.kind, labels: set_.labels || kind.labels };
        const i = events().findIndex((e) => e.id === at);
        if (i >= 0) index = i;
        publishMarks(); render();
      }
    } catch (e) { /* the next action will say so */ }
  }

  /* Undo goes back a decision -- or a merge -- AND back to the event it
     was about. A merge undone puts the other event back (under a new id;
     see curation.unmerge) and the survivor as it was. */
  async function undo() {
    const last = history.pop();
    if (!last) { toast('Nothing to undo.', null, 2000); return; }
    bankDirty = true;
    if (last.type === 'merge') { await undoMerge(last); return; }
    if (last.type === 'bulk') { await undoBulk(last); return; }
    const at = events().findIndex((e) => e.id === last.id);
    if (at < 0) return;
    const was = events()[at].label || null;
    events()[at].label = last.from;
    markRev += 1;
    lastChange = { index: at, label: last.from };
    goTo(at);
    try {
      await apiPost(url('label'), { event: last.id, label: last.from });
    } catch (e) {
      events()[at].label = was;
      history.push(last);
      markRev += 1;
      publishMarks();
      toast('That undo did not save: ' + e.message, 'err', 8000);
    }
    render();
  }

  async function undoMerge(last) {
    const lead = events().find((e) => e.id === last.keep);
    if (!lead) {
      toast('That event is no longer in this pool, so the merge cannot be '
            + 'undone here.', 'warn', 6000);
      return;
    }
    const now = pickOf(lead, KEEP);
    for (const k of KEEP) {
      if (last.before[k] !== undefined) lead[k] = last.before[k];
      else if (k === 'label') lead.label = null;
      else delete lead[k];
    }
    const back = Object.assign({ id: 'pending-' + Date.now() }, last.dropped);
    const evs = events();
    let at = evs.findIndex((e) => e.start > back.start);
    if (at < 0) at = evs.length;
    evs.splice(at, 0, back);
    markRev += 1;
    goTo(evs.indexOf(back));
    saving += 1; updateSaving();
    try {
      const res = await apiPost(url('unmerge'), {
        keep: last.keep, before: last.before, dropped: last.dropped });
      if (res.restored) Object.assign(back, res.restored);
      if (res.event) Object.assign(lead, res.event);
      publishMarks();
      BARRY.activity.log('panning.unmerge', { gid: set_.gid, kept: lead.id }, sess);
    } catch (e) {
      for (const k of KEEP) {
        if (now[k] !== undefined) lead[k] = now[k]; else delete lead[k];
      }
      evs.splice(evs.indexOf(back), 1);
      history.push(last);
      markRev += 1;
      publishMarks();
      toast('That undo did not save: ' + e.message, 'err', 8000);
    } finally {
      saving -= 1; updateSaving();
    }
    render();
  }

  /* ==================================================================
     Many at once: one label for many events, and the list
     ================================================================== */

  const labelOf = (id) => ((kind && kind.labels) || []).find((l) => l.id === id) || null;
  const labelName = (id) => (id ? (labelOf(id) || {}).name || id : 'undecided');
  const goodLabel = () => ((kind && kind.labels) || []).find((l) => l.good) || null;
  const ORIGINS = [
    ['both', 'Merged', 'The ones both detectors found'],
    ['incisor', 'Incisor only', 'Found by Incisor and not by Doppler'],
    ['doppler', 'Doppler only', 'Found by Doppler and not by Incisor'],
    ['none', 'Origin not known', 'Carries no origin'],
  ];
  const originKey = (e) => (ORIGIN_WORD[e.origin] ? e.origin : 'none');
  const plural = (n, one, many) => n + ' ' + (n === 1 ? one : (many || one + 's'));

  /* One label for many events, in one write -- and one step of undo that
     puts every one of them back the way it was. Checkup's All Garbage, for
     any label and any selection. `labelId` null makes them undecided. On
     screen first, as a single decision is, and put back if the write fails. */
  async function labelMany(evs, labelId) {
    const own = set_;
    if (!own) return false;
    const want = labelId || null;
    const change = (evs || []).filter((e) => (e.label || null) !== want);
    if (!change.length) {
      toast('Nothing to change: ' + ((evs || []).length === 1 ? 'it is'
            : 'they are all') + ' ' + labelName(want) + ' already.', null, 4000);
      return false;
    }
    await settled();
    if (set_ !== own) return false;
    const h = { type: 'bulk', label: want,
                items: change.map((e) => ({ id: e.id, from: e.label || null })) };
    const pairs = {};
    for (const e of change) { pairs[e.id] = want; e.label = want; }
    history.push(h);
    if (history.length > 500) history.shift();
    bankDirty = true;
    markRev += 1;
    lastChange = null;
    publishMarks();
    if (BARRY.views.xplore.redraw) BARRY.views.xplore.redraw();
    render(); drawStrips();
    saving += 1; updateSaving();
    try {
      const res = await apiPost(url('label'), { labels: pairs });
      if (res.progress) own._progress = res.progress;
      if (BARRY.views.toolkit && BARRY.views.toolkit.curationChanged) {
        BARRY.views.toolkit.curationChanged();
      }
    } catch (e) {
      if (set_ === own) {
        const byId = new Map(events().map((x) => [x.id, x]));
        for (const it of h.items) {
          const ev = byId.get(it.id);
          if (ev) ev.label = it.from;
        }
        const back = history.indexOf(h);
        if (back >= 0) history.splice(back, 1);
        markRev += 1;
        publishMarks(); render(); drawStrips();
      }
      toast('That did not save: ' + e.message, 'err', 9000);
      return false;
    } finally {
      saving -= 1; updateSaving();
    }
    BARRY.activity.log('panning.label_many',
                       { gid: own.gid, n: change.length, label: want }, sess);
    // The last ones decided: banked, as a single decision would be.
    if (set_ === own && want && autoOn() && !left()) {
      quietBank(own.gid, 'Every event decided in Panning.', own.kind);
    }
    toast(plural(change.length, 'event') + ' '
          + (want ? 'labelled ' + labelName(want) : 'made undecided')
          + '. Z puts ' + (change.length === 1 ? 'it' : 'them all') + ' back.',
          'ok', 8000);
    // The one on screen may have just left this pass.
    if (set_ === own && !wanted(current()) && nWanted()) goTo(firstWanted());
    return true;
  }

  /* Undoing that: every one back to what it was, in one write. */
  async function undoBulk(last) {
    const own = set_;
    const byId = new Map(events().map((x) => [x.id, x]));
    const pairs = {}, now = {};
    for (const it of last.items) {
      const ev = byId.get(it.id);
      if (!ev) continue;
      now[it.id] = ev.label || null;
      ev.label = it.from;
      pairs[it.id] = it.from;
    }
    markRev += 1;
    lastChange = null;
    publishMarks();
    if (BARRY.views.xplore.redraw) BARRY.views.xplore.redraw();
    render(); drawStrips();
    saving += 1; updateSaving();
    try {
      await apiPost(url('label'), { labels: pairs });
      toast(plural(Object.keys(pairs).length, 'event') + ' put back the way '
            + (Object.keys(pairs).length === 1 ? 'it was.' : 'they were.'),
            'ok', 4000);
    } catch (e) {
      if (set_ === own) {
        for (const id in now) {
          const ev = byId.get(id);
          if (ev) ev.label = now[id];
        }
        history.push(last);
        markRev += 1;
        publishMarks(); render(); drawStrips();
      }
      toast('That undo did not save: ' + e.message, 'err', 8000);
    } finally {
      saving -= 1; updateSaving();
    }
  }

  /* LABEL MANY: which events, by where they came from and what they are
     now, and the one label they all get. "Every merged one and every
     Incisor-only one is a spike" is three clicks and a button. */
  const bulkQ = { origins: null, from: null, to: null };

  function bulkDialog() {
    if (!set_) return;
    const labs = ((kind && kind.labels) || []).filter((l) => !l.computed);
    const nO = (o) => events().filter((e) => originKey(e) === o).length;
    const nF = (f) => events().filter((e) => (e.label || '') === f).length;
    // What it opens on: what was asked last time, else the pass on screen,
    // the undecided ones, and the label that means "a real event".
    const origins = new Set(bulkQ.origins
      || (origin === 'all' ? ['both', 'incisor', 'doppler', 'none'] : [origin]));
    const from = new Set(bulkQ.from || ['']);
    let to = bulkQ.to !== null && bulkQ.to !== undefined ? bulkQ.to
      : ((goodLabel() || labs[0] || {}).id || '');

    const body = el('div', { class: 'mb pan-bulk' });
    const okBtn = el('button', { class: 'btn' });
    const picked = () => events().filter(
      (e) => origins.has(originKey(e)) && from.has(e.label || ''));

    const toggle = (set, id, label, n, title) => el('label', {
      class: 'pan-bulk-opt' + (set.has(id) ? ' on' : '') + (n ? '' : ' none'),
      title: title || null,
    }, [
      el('input', { type: 'checkbox', checked: set.has(id) ? 'checked' : null,
        onchange: (e) => {
          if (e.target.checked) set.add(id); else set.delete(id);
          paint();
        } }),
      id && ORIGIN_WORD[id] ? originDot(id) : null,
      el('span', { text: label }),
      el('span', { class: 'cur-count', text: n.toLocaleString() }),
    ].filter(Boolean));

    const paint = () => {
      body.innerHTML = '';
      body.appendChild(el('div', { class: 'section-label',
                                   text: 'Found by' }));
      body.appendChild(el('div', { class: 'pan-bulk-row' },
        ORIGINS.filter(([id]) => id !== 'none' || nO('none'))
          .map(([id, label, title]) => toggle(origins, id, label, nO(id), title))));
      body.appendChild(el('div', { class: 'section-label',
                                   text: 'That are now' }));
      body.appendChild(el('div', { class: 'pan-bulk-row' },
        [toggle(from, '', 'Undecided', nF(''), 'Nobody has decided these yet')]
          .concat(labs.map((l) => toggle(from, l.id, l.name, nF(l.id),
                                         'Already called ' + l.name)))));
      body.appendChild(el('div', { class: 'section-label',
                                   text: 'Label them' }));
      body.appendChild(el('div', { class: 'pan-bulk-row' },
        labs.map((l) => el('button', {
          class: 'cur-cat' + (to === l.id ? ' on' : ''),
          style: '--cat:' + l.color,
          onclick: () => { to = l.id; paint(); },
        }, [el('span', { text: l.name })]))
          .concat([el('button', {
            class: 'cur-cat' + (to === '' ? ' on' : ''),
            title: 'Take the decision off them, so they are to do again',
            onclick: () => { to = ''; paint(); },
          }, [el('span', { text: 'Undecided' })])])));

      const sel = picked();
      const change = sel.filter((e) => (e.label || '') !== to);
      const byO = {};
      for (const e of change) byO[originKey(e)] = (byO[originKey(e)] || 0) + 1;
      const said = { both: 'merged', incisor: 'Incisor only',
                     doppler: 'Doppler only', none: 'of no known origin' };
      const mix = ORIGINS.filter(([id]) => byO[id])
        .map(([id]) => byO[id].toLocaleString() + ' ' + said[id])
        .join(', ');
      body.appendChild(el('p', { class: 'confirm-msg pan-bulk-say',
        text: !sel.length ? 'Nothing matches that. Tick at least one of each.'
          : !change.length ? 'All ' + sel.length.toLocaleString() + ' of them '
            + 'are ' + labelName(to || null) + ' already.'
          : plural(change.length, 'event') + ' become'
            + (change.length === 1 ? 's ' : ' ') + labelName(to || null)
            + ': ' + mix + '.'
            + (sel.length > change.length
                ? ' ' + (sel.length - change.length).toLocaleString()
                  + ' already are.' : '')
            + ' One write, and Z puts every one of them back.' }));
      okBtn.textContent = change.length
        ? 'Label ' + change.length.toLocaleString() + ' ' + labelName(to || null)
        : 'Label them';
      okBtn.disabled = change.length ? null : 'disabled';
    };

    okBtn.onclick = async () => {
      const sel = picked();
      bulkQ.origins = [...origins]; bulkQ.from = [...from]; bulkQ.to = to;
      closeModal();
      await labelMany(sel, to || null);
    };

    showModal(el('div', { class: 'modal pan-bulk-modal' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Label many' }),
        el('span', { class: 'sub', text: set_.name || '' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      body,
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        okBtn,
      ]),
    ]));
    paint();
  }

  /* THE LIST: every event in the pool at once -- Checkup's List all, with
     where each one came from on it. By time, by decision or by origin;
     searchable; click one to go to it; and whatever is shown can be
     labelled in one go. How it was last looked at is kept for next time. */
  const listQ = { by: 'time', text: '', only: 'all', origins: null };

  function listAll() {
    if (!set_) return;
    const labs = ((kind && kind.labels) || []).filter((l) => !l.computed);
    const colorOf = (id) => (labelOf(id) || {}).color || null;
    if (!listQ.origins) listQ.origins = ['both', 'incisor', 'doppler', 'none'];
    const origins = new Set(listQ.origins);

    const sub = el('p', { class: 'sub' });
    const rowsHost = el('div', { class: 'cur-list pan-list' });
    const chips = el('div', { class: 'res-toolbar cur-list-chips' });
    const ochips = el('div', { class: 'res-toolbar cur-list-chips pan-list-o' });
    const count = el('span', { class: 'hint' });
    const bulk = el('div', { class: 'pan-list-bulk' });

    const gapWord = (e) => {
      if (e.origin !== 'both' || e.pair_t == null) return '';
      const d = (e.pair_t - e.start) * 1000;
      return KEEP_WORD[otherOf(stampOf(e))] + ' ' + (d >= 0 ? '+' : '−')
           + Math.abs(d).toFixed(1) + ' ms';
    };
    const fromWord = (e) => (e.origin === 'both'
      ? 'both, ' + KEEP_WORD[stampOf(e)] + '’s time'
      : e.origin ? ORIGIN_WORD[e.origin] + ' only' : 'origin not known');

    function matching() {
      const q = listQ.text.trim().toLowerCase();
      const words = q ? q.split(/\s+/) : [];
      const out = [];
      events().forEach((e, i) => {
        if (!origins.has(originKey(e))) return;
        if (listQ.only === 'left' && e.label) return;
        if (listQ.only !== 'all' && listQ.only !== 'left'
            && e.label !== listQ.only) return;
        if (words.length) {
          const hay = [clock(e.start), e.start.toFixed(3), labelName(e.label),
                       fromWord(e), e.origin === 'both' ? 'merged' : '',
                       e.by, e.merged_by, e.merged_at ? 'merged here' : '',
                       e.channel != null ? 'csc' + e.channel : '']
            .filter(Boolean).join(' ').toLowerCase();
          if (!words.every((w) => hay.indexOf(w) >= 0)) return;
        }
        out.push({ e, i });
      });
      return out;
    }

    function rowFor(rec) {
      const e = rec.e;
      return el('div', {
        class: 'cur-list-row pan-list-row' + (rec.i === index ? ' here' : '')
             + (e.label ? '' : ' undecided'),
        style: e.label ? '--cat:' + (colorOf(e.label) || 'var(--line)') : '',
        title: (e.by ? 'Decided by ' + e.by : 'Nobody has decided this one')
             + (e.merged_at ? '\nMerged here' + (e.merged_by ? ' by '
                + e.merged_by : '') : ''),
        onclick: () => {
          closeModal();
          if (!wanted(e)) { review = 'all'; origin = 'all'; }
          mark = null;
          goTo(rec.i);
        },
      }, [
        el('span', { class: 'cl-n', text: '#' + (rec.i + 1) }),
        el('span', { class: 'cl-t', text: clock(e.start) }),
        el('span', { class: 'pan-list-from' }, [originDot(e.origin),
          el('span', { text: fromWord(e) })]),
        el('span', { class: 'pan-list-gap', text: gapWord(e) }),
        el('span', { class: 'cl-lab', text: labelName(e.label) }),
        el('span', { class: 'cl-who', text: e.by || '' }),
        e.merged_at ? el('span', { class: 'cl-revs', text: 'merged here' }) : null,
        rec.i === index ? el('span', { class: 'pill sm', text: 'here' }) : null,
      ].filter(Boolean));
    }

    function paintChips() {
      const tally = {};
      for (const e of events()) {
        if (!origins.has(originKey(e))) continue;
        const k = e.label || '';
        tally[k] = (tally[k] || 0) + 1;
      }
      const nIn = events().filter((e) => origins.has(originKey(e))).length;
      chips.innerHTML = '';
      const chip = (id, label, n) => el('button', {
        class: 'pill' + (listQ.only === id ? ' active' : ''),
        disabled: (!n && id !== 'all' && listQ.only !== id) ? 'disabled' : null,
        text: label + ' (' + n.toLocaleString() + ')',
        onclick: () => { listQ.only = id; paintAll(); },
      });
      chips.appendChild(chip('all', 'All', nIn));
      chips.appendChild(chip('left', 'Undecided', tally[''] || 0));
      for (const l of labs) chips.appendChild(chip(l.id, l.name, tally[l.id] || 0));
      ochips.innerHTML = '';
      ochips.appendChild(el('span', { class: 'hint quiet', text: 'Found by' }));
      for (const [id, label, title] of ORIGINS) {
        const n = events().filter((e) => originKey(e) === id).length;
        if (id === 'none' && !n) continue;
        ochips.appendChild(el('button', {
          class: 'pill pan-o ' + id + (origins.has(id) ? ' active' : ''),
          title: title + '. Click to ' + (origins.has(id) ? 'leave them out'
                                                        : 'show them') + '.',
          'aria-pressed': origins.has(id) ? 'true' : 'false',
          onclick: () => {
            if (origins.has(id)) origins.delete(id); else origins.add(id);
            listQ.origins = [...origins];
            paintAll();
          },
        }, [ORIGIN_WORD[id] ? originDot(id) : null,
            el('span', { text: label + ' (' + n.toLocaleString() + ')' })]
          .filter(Boolean)));
      }
    }

    function paintRows(rows) {
      rowsHost.innerHTML = '';
      count.textContent = rows.length === events().length
        ? plural(rows.length, 'event')
        : rows.length.toLocaleString() + ' of ' + events().length.toLocaleString();
      if (!rows.length) {
        rowsHost.appendChild(el('div', { class: 'hint',
          text: 'Nothing matches that.' }));
        return;
      }
      const group = (title, colour, mine, two) => {
        rowsHost.appendChild(el('div', { class: 'cl-head' }, [
          two ? el('span', { class: 'pan-od both' })
              : el('span', { class: 'cl-dot',
                             style: 'background:' + (colour || 'var(--text-3)') }),
          el('strong', { text: title }),
          el('span', { class: 'count', text: mine.length.toLocaleString() }),
        ]));
        mine.forEach((r) => rowsHost.appendChild(rowFor(r)));
      };
      if (listQ.by === 'type') {
        // Undecided last: it is the work remaining, not a result.
        for (const id of labs.map((l) => l.id).concat([''])) {
          const mine = rows.filter((r) => (r.e.label || '') === id);
          if (mine.length) group(id ? labelName(id) : 'Undecided', colorOf(id), mine);
        }
        return;
      }
      if (listQ.by === 'origin') {
        for (const [id, label] of ORIGINS) {
          const mine = rows.filter((r) => originKey(r.e) === id);
          if (mine.length) {
            group(label, ORIGIN_WORD[id] && id !== 'both' ? oCol(id) : null,
                  mine, id === 'both');
          }
        }
        return;
      }
      /* By time, with a marker wherever the events thin out -- a
         half-minute with nothing in it is a fact about the recording. */
      let last = null;
      for (const r of rows) {
        if (last !== null && r.e.start - last > 30) {
          rowsHost.appendChild(el('div', { class: 'cl-gap',
            text: '… ' + Math.round(r.e.start - last) + ' s with no events …' }));
        }
        rowsHost.appendChild(rowFor(r));
        last = r.e.start;
      }
    }

    /* Everything shown, one label: the bulk action, scoped to exactly the
       rows the filters and the search left on screen. */
    function paintBulk(rows) {
      bulk.innerHTML = '';
      if (!rows.length) return;
      bulk.appendChild(el('span', { class: 'hint',
        text: 'Label ' + (rows.length === events().length ? 'all ' : 'the ')
            + rows.length.toLocaleString() + ' shown:' }));
      const go = async (id) => {
        const evs = rows.map((r) => r.e);
        const change = evs.filter((e) => (e.label || null) !== id);
        if (!change.length) {
          toast('They are all ' + labelName(id) + ' already.', null, 4000);
          return;
        }
        const ok = await BARRY.confirm(
          'Label ' + plural(change.length, 'event') + ' ' + labelName(id) + '?',
          el('p', { text: 'Every event the list is showing'
              + (evs.length > change.length ? ' that is not '
                 + labelName(id) + ' already' : '') + ' becomes '
              + labelName(id) + '. One write, and Z puts every one of them '
              + 'back.' }),
          'Label ' + change.length.toLocaleString());
        if (!ok) return;
        await labelMany(evs, id);
        if (set_) paintAll();
      };
      for (const l of labs) {
        bulk.appendChild(el('button', {
          class: 'cur-cat', style: '--cat:' + l.color,
          onclick: () => go(l.id) }, [el('span', { text: l.name })]));
      }
      bulk.appendChild(el('button', { class: 'cur-cat',
        title: 'Take the decision off them, so they are to do again',
        onclick: () => go(null) }, [el('span', { text: 'Undecided' })]));
    }

    function paintAll() {
      sub.textContent = plural(events().length, 'event') + '  ·  '
        + left().toLocaleString() + ' still undecided  ·  ' + (set_.name || '');
      paintChips();
      const rows = matching();
      paintRows(rows);
      paintBulk(rows);
    }

    // Its own buttons rather than ui.seg, which remembers the value it was
    // built with and would not answer a click back to it.
    const controls = el('div', { class: 'cur-list-bar' }, [
      el('div', { class: 'seg sm' }, [
        ['time', 'By time', 'In time order'],
        ['type', 'By decision', 'Grouped by what each was called'],
        ['origin', 'By origin', 'Grouped by which detector found it'],
      ].map(([id, label, title]) => el('button', {
        class: listQ.by === id ? 'active' : '', text: label, title,
        onclick: (ev) => {
          listQ.by = id;
          Array.from(ev.target.parentNode.children).forEach(
            (b) => b.classList.toggle('active', b === ev.target));
          paintAll();
        },
      }))),
      el('input', {
        type: 'search', class: 'cur-list-search', value: listQ.text,
        placeholder: 'Find a time, a decision, an origin, a name…',
        oninput: (e) => { listQ.text = e.target.value; paintAll(); },
      }),
      count,
    ]);

    showModal(el('div', { class: 'modal cur-list-modal pan-list-modal' }, [
      el('div', { class: 'mh' }, [
        el('h2', { text: 'Everything in this pool' }),
        sub,
      ]),
      controls, chips, ochips, rowsHost, bulk,
      el('div', { class: 'mf' }, [
        el('div', { style: 'flex:1' }),
        el('button', { class: 'btn', text: 'Close', onclick: closeModal }),
      ]),
    ]));
    paintAll();
    // Land on where you actually are, rather than at the top of a thousand.
    const here = rowsHost.querySelector('.cur-list-row.here');
    if (here && here.scrollIntoView) here.scrollIntoView({ block: 'center' });
  }

  /* ==================================================================
     The keyboard
     ================================================================== */
  const modalOpen = () => {
    const m = document.getElementById('bigModal');
    return !!m && !m.classList.contains('hidden');
  };

  function keys(e) {
    if (!set_) return;
    if (isTyping(e)) return;
    if (modalOpen()) return;
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
      m: () => merge('incisor'),
      d: () => merge('doppler'),
      l: listAll,
      escape: () => { if (mark) { mark = null; render(); drawStrips(); } else exit(); },
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
  function originDot(o) {
    return el('i', { class: 'pan-od ' + (o || 'none'),
                     title: o ? 'Found by ' + ORIGIN_WORD[o] : 'origin not known' });
  }

  function render() {
    if (!set_) return;
    let bar = $('#panBar');
    if (!bar) {
      bar = el('div', { id: 'panBar', class: 'cur-bar spot-bar pan-bar' });
      // In the middle of the one mode bar (core.js `BARRY.modeSlot`).
      BARRY.modeSlot().appendChild(bar);
      document.addEventListener('keydown', keys, true);
    }
    bar.innerHTML = '';
    const ev = current();
    const n = events().length;
    const at = events().slice(0, index + 1).filter(wanted).length;
    const pair = ev && ev.pair_t != null
      ? ((ev.pair_t - ev.start) * 1000) : null;

    bar.appendChild(el('div', { class: 'cur-where' }, [
      el('strong', { text: set_.name || 'Pooled spikes' }),
      el('span', { class: 'cur-sub', text: clock(ev && ev.start) }),
      ev ? el('span', { class: 'pan-from' }, [
        originDot(ev.origin),
        el('span', { text: ev.origin === 'both'
                           ? 'both found it, at ' + KEEP_WORD[stampOf(ev)] + '’s time'
                         : ev.origin ? ORIGIN_WORD[ev.origin] + ' only'
                         : 'origin not known' }),
      ]) : null,
      pair != null
        ? el('span', { class: 'cur-sub',
            title: 'Where the other detector put it',
            text: (ev.origin === 'both' ? KEEP_WORD[otherOf(stampOf(ev))] + ' '
                                        : 'other ')
                + (pair >= 0 ? '+' : '−') + Math.abs(pair).toFixed(1) + ' ms' })
        : null,
      ev && ev.merged_at
        ? BARRY.ui.chip('merged here' + (ev.merged_by ? ' by ' + ev.merged_by : ''),
                        { flag: true, title: 'Merged in Panning, '
                          + String(ev.merged_at).slice(0, 16).replace('T', ' ') })
        : null,
      ev && ev.channel != null
        ? el('span', { class: 'cur-sub', text: 'CSC' + ev.channel }) : null,
      el('span', { class: 'cur-count', text: at + ' / ' + nWanted() }),
      // Whether the work is in the bank -- the step page says the same.
      BARRY.setPicker ? BARRY.setPicker._bankChip({
        banked: banked ? Object.assign({}, banked,
                                       { changed: banked.changed || bankDirty })
                       : null,
        progress: { specified: events().filter((e) => e.label).length },
      }) : null,
      beatOthers.length
        ? BARRY.ui.chip(beatOthers.length + ' also here', { kind: 'warn' })
        : null,
    ].filter(Boolean)));

    const decided = events().filter((e) => e.label).length;
    bar.appendChild(el('div', { class: 'cur-prog' }, [
      el('i', { style: 'width:' + (n ? (100 * decided / n) : 0) + '%' }),
      el('span', { text: decided + ' decided · ' + left() + ' left' }),
    ]));

    const tally = {};
    for (const e of events()) if (e.label) tally[e.label] = (tally[e.label] || 0) + 1;
    const cats = el('div', { class: 'cur-cats' });
    for (const lab of (kind.labels || [])) {
      if (lab.computed) continue;
      const key = (lab.keys || [])[0];
      cats.appendChild(el('button', {
        class: 'cur-cat' + (ev && ev.label === lab.id ? ' on' : ''),
        style: '--cat:' + lab.color,
        'data-cat': lab.id,
        title: lab.name + (key ? '  [' + key + ']' : ''),
        onclick: () => assign(lab.id),
      }, [
        el('span', { text: lab.name }),
        key ? el('kbd', { text: String(key) }) : null,
        el('span', { class: 'cur-count', text: String(tally[lab.id] || 0) }),
      ].filter(Boolean)));
    }
    const b = partner();
    const gap = b && ev ? (b.start - ev.start) * 1000 : null;
    /* Two merges: to Incisor's time (M) and to Doppler's (D). Each says
       which of the two it would keep, and the one that cannot -- neither
       event carries Doppler's time -- says why rather than vanishing. */
    const mergeBtn = (want, key) => {
      const ok = !!b && canKeep(ev, b, want);
      const lead = ok ? leadOf(ev, b, want) : null;
      const word = KEEP_WORD[want];
      return el('button', {
        class: 'cur-cat pan-merge ' + want + (mark ? ' armed' : ''),
        disabled: ok ? null : 'disabled',
        'data-merge': want,
        title: !b ? 'Nothing next to this one'
          : !ok ? 'Neither this one nor the ' + (mark ? 'picked' : 'nearest')
                  + ' one carries Doppler’s time, so there is no Doppler stamp '
                  + 'to keep. Merge to Incisor instead.'
          : 'Make this and the ' + (mark ? 'picked' : 'nearest') + ' event '
            + '(' + ORIGIN_WORD[b.origin || 'incisor'] + '’s, '
            + (gap >= 0 ? gap.toFixed(1) + ' ms later'
                        : (-gap).toFixed(1) + ' ms earlier')
            + ') one, at ' + word + '’s time — ' + clock(lead.start)
            + '. The other time is kept beside it. Shift-click another on '
            + 'the strip to pick it.  [' + key + ']',
        onclick: () => merge(want),
      }, [
        el('i', { class: 'pan-od ' + want }),
        el('span', { text: 'Merge to ' + word }),
        el('kbd', { text: key }),
        want === 'incisor' && gap != null ? el('span', { class: 'cur-count',
          text: (mark ? 'picked ' : '') + (gap >= 0 ? '+' : '−')
              + Math.abs(gap).toFixed(1) + ' ms' })
          : null,
      ].filter(Boolean));
    };
    cats.appendChild(mergeBtn('incisor', 'M'));
    cats.appendChild(mergeBtn('doppler', 'D'));
    bar.appendChild(cats);

    bar.appendChild(el('div', { class: 'cur-nav' }, [
      el('button', { class: 'mini', text: '◀', title: 'Previous  [←]',
        onclick: () => step(-1) }),
      el('button', { class: 'mini', text: '▶', title: 'Next  [→]',
        onclick: () => step(1) }),
      el('button', { class: 'mini', text: 'Clear', title: 'Clear  [C]',
        disabled: (ev && ev.label) ? null : 'disabled', onclick: clearLabel }),
      el('button', { class: 'mini', text: '↶',
        title: 'Undo the last decision or merge  [Z]',
        disabled: history.length ? null : 'disabled', onclick: undo }),
      BARRY.ui.seg([
        ['left', 'Undecided', 'The ones nobody has decided yet'],
        ['flag', 'Flagged (' + flagged() + ')', 'The ones put aside'],
        ['all', 'All', 'Every event, decided or not'],
      ], review, (id) => {
        review = id;
        if (!wanted(current())) goTo(firstWanted());
        render();
      }),
      BARRY.ui.seg([
        ['all', 'Every origin (' + nOrigin('all') + ')', 'Whoever found it'],
        ['both', 'Merged (' + nOrigin('both') + ')',
         'The ones both detectors found'],
        ['incisor', 'Incisor only (' + nOrigin('incisor') + ')',
         'Found by Incisor and not by Doppler'],
        ['doppler', 'Doppler only (' + nOrigin('doppler') + ')',
         'Found by Doppler and not by Incisor'],
      ], origin, (id) => {
        origin = id;
        if (!wanted(current())) goTo(firstWanted());
        render(); drawStrips();
      }, { extra: 'pan-origin' }),
      el('span', { id: 'panSaving', class: 'cur-saving' }),
    ]));

    /* The bar's end (ui.modeEnd): List all, Label many and Auto-bank under
       More, the next step of The Confluence, and Bank -- then the shell's
       Simplify, ? and Leave, the last thing on the right. */
    bar.appendChild(BARRY.ui.modeEnd({
      more: [
        el('button', { class: 'btn ghost sm', text: 'List all\u2026',
          title: 'Every event in this pool, by time, decision or origin. Click '
               + 'one to go to it; label everything shown at once.  [L]',
          onclick: listAll }),
        el('button', { class: 'btn ghost sm', text: 'Label many\u2026',
          title: 'Give one label to every event of the kinds you pick \u2014 '
               + 'say, every merged and every Incisor-only one is a spike. One '
               + 'step of undo puts them all back.',
          onclick: () => bulkDialog() }),
        el('button', {
          class: 'mini spot-auto' + (autoOn() ? ' on' : ''),
          text: 'Auto-bank: ' + (autoOn() ? 'on' : 'off'),
          title: autoOn()
            ? 'The decisions and merges are banked as a new version without '
              + 'asking: when the last undecided event is decided, and when you '
              + 'leave with work the bank does not have yet. Click to turn it off.'
            : 'Off: nothing is banked until you press Bank the results. '
              + 'Click to turn it on.',
          onclick: () => {
            try { BARRY.prefs.set(AUTO_KEY, !autoOn()); } catch (e) { /* later */ }
            render();
          } }),
      ],
      next: {
        text: 'Next: Lock \u2014 line them up \u2192',
        title: 'Step 3 of The Confluence: Lock lines the spikes up on their '
             + 'peaks.',
        onclick: () => toTool('lock'),
      },
      bank: { text: 'Bank the results\u2026', onclick: bank,
              title: 'Write these decisions and merges as a new version of '
                   + 'the pool' },
    }));
    updateSaving();
    ensureStrips();
  }

  function toTool(id) {
    const tk = BARRY.views.toolkit;
    if (tk && tk.pick) tk.pick(id, 'confluence');
    setView('toolkit');
  }

  function bank() {
    if (!set_ || !BARRY.curate || !BARRY.curate.bankAt) return;
    const t = {};
    for (const e of events()) if (e.label) t[e.label] = (t[e.label] || 0) + 1;
    const gid = set_.gid;
    return settled().then(() => BARRY.curate.bankAt({
      gid: set_.gid, kind: set_.kind, name: set_.name,
      labels: (kind && kind.labels) || set_.labels || [],
      progress: { by_label: t, left: left() },
    })).then(() => refreshBanked(gid));
  }

  /* Banking without being asked (2026-10-19), as Spotter does: when the
     last undecided event is decided, and on leaving with work the bank does
     not have. The dialog's own route, so a bank that would hold nothing new
     writes nothing. On by default, off by the switch in the bar. */
  const AUTO_KEY = 'panning_autobank';
  function autoOn() {
    try { return BARRY.prefs.get(AUTO_KEY, true) !== false; }
    catch (e) { return true; }
  }

  async function quietBank(gid, why, k) {
    // Its own kind, passed in: on leaving it runs after the set is let go.
    const sk = k || setKind;
    await settled();
    let res;
    try {
      res = await apiPost(BARRY.ui.setUrl(gid, sk, 'bank'), {
        note: why,
        added_by: (BARRY.profile && BARRY.profile.who && BARRY.profile.who())
                  || undefined,
      });
    } catch (e) {
      toast('Could not bank automatically: ' + e.message
            + ' Bank the results by hand to keep them.', 'warn', 9000);
      return;
    }
    const it = (res.entries || [])[0] || {};
    if (it.replaced && !it.new_version) return;          // nothing new
    toast('Banked automatically as ' + BARRY.ui.versionLabel(it.version)
          + ': ' + (it.n || 0) + ' decided.', 'ok', 6000);
    await refreshBanked(gid);
    if (BARRY.views.toolkit && BARRY.views.toolkit.curationChanged) {
      BARRY.views.toolkit.curationChanged();
    }
    // The workbench, if it is the page on screen, shows the new version.
    if (BARRY.views.toolkit && BARRY.views.toolkit.refresh
        && BARRY.state.view === 'toolkit') {
      BARRY.views.toolkit.refresh();
    }
  }

  /* Every decision and merge on the server before the bank reads them, or
     the version is one short -- a last key pressed just before Bank. */
  async function settled() {
    for (let i = 0; i < 60 && saving > 0; i++) {
      await new Promise((r) => setTimeout(r, 100));
    }
  }

  /* What the bank holds of this set now, read back after banking rather
     than assumed: a bank that wrote nothing new says so in the chip too. */
  async function refreshBanked(gid) {
    if (!set_ || set_.gid !== gid) return;
    try {
      const got = await api(url(''));
      if (!set_ || set_.gid !== gid) return;
      banked = got.banked || null;
      bankDirty = false;
      render();
    } catch (e) { /* the chip keeps what it had */ }
  }

  const flagged = () => events().filter(
    (e) => e.label && flagIds().has(e.label)).length;

  function updateSaving() {
    const n = $('#panSaving');
    if (n) n.textContent = saving ? 'saving…' : '';
  }

  /* ==================================================================
     The strips under the panes
     ================================================================== */

  /* Two: the window you are looking at, laid out on two lanes so two events
     a few milliseconds apart are two things you can click; and the whole
     recording, for where you are. */
  function ensureStrips() {
    const bar = $('#panBar');
    if (!bar || !bar.parentNode) return;
    if (!$('#panWin')) {
      const w = el('canvas', { id: 'panWin', class: 'pan-win',
        title: 'Click an event to go to it. Shift-click another to pick it '
             + 'for a merge, then press M.',
        onclick: winClick });
      bar.parentNode.insertBefore(w, bar);
    }
    if (!$('#panAll')) {
      const a = el('canvas', { id: 'panAll', class: 'pan-all',
        onclick: allClick });
      bar.parentNode.insertBefore(a, $('#panWin'));
    }
    drawStrips();
  }

  function drawStrips() {
    drawWin();
    drawAll();
  }

  const WP = { l: 70, r: 10, t: 6, b: 14, lane: 20 };

  function winRange() {
    if (lastWin && lastWin.t1 > lastWin.t0) return lastWin;
    const ev = current();
    const t = ev ? ev.start : 0;
    return { t0: Math.max(0, t - span / 2), t1: Math.max(0, t - span / 2) + span };
  }

  function canvasFor(id, h) {
    const cv = $(id);
    if (!cv) return null;
    const w = Math.max(200, Math.round(cv.clientWidth
      || (cv.parentNode && cv.parentNode.clientWidth) || 600));
    const dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    cv.style.height = h + 'px';
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    return { cv, g, w, h };
  }

  /* One event on two lanes: Incisor's above, Doppler's below. An event both
     found is a tick in both lanes -- Incisor's at the time kept, Doppler's
     at its own, joined. */
  function tickAt(g, X, ev, yI, yD, lh, alpha, wide) {
    const ci = oCol('incisor'), cd = oCol('doppler');
    g.globalAlpha = alpha;
    g.lineWidth = wide ? 3 : 2;
    const line = (x, y, col) => {
      g.strokeStyle = col;
      g.beginPath(); g.moveTo(x, y + 2); g.lineTo(x, y + lh - 2); g.stroke();
    };
    const x = Math.round(X(ev.start)) + 0.5;
    if (ev.origin === 'both') {
      // Each detector's tick at its own time, whichever the event is filed
      // under (`stamp`); `x`, returned, is the time it is filed at.
      const xi = Math.round(X(timeBy(ev, 'incisor'))) + 0.5;
      const xd = Math.round(X(timeBy(ev, 'doppler'))) + 0.5;
      line(xi, yI, ci);
      line(xd, yD, cd);
      g.strokeStyle = tok('--text-3', '#888');
      g.lineWidth = 1;
      g.beginPath(); g.moveTo(xi, yI + lh - 2); g.lineTo(xd, yD + 2); g.stroke();
    } else if (ev.origin === 'doppler') {
      line(x, yD, cd);
    } else {
      line(x, yI, ci);
    }
    g.globalAlpha = 1;
    return x;
  }

  function drawWin() {
    const c = canvasFor('#panWin', WP.t + WP.lane * 2 + 4 + WP.b);
    if (!c || !set_) return;
    const { g, w, h } = c;
    const W = winRange();
    const plotW = Math.max(10, w - WP.l - WP.r);
    const X = (t) => WP.l + ((t - W.t0) / (W.t1 - W.t0)) * plotW;
    const yI = WP.t, yD = WP.t + WP.lane + 4, lh = WP.lane;
    // Lanes, and their names.
    g.fillStyle = tok('--bg-2', '#1b1f1d');
    g.fillRect(WP.l, yI, plotW, lh);
    g.fillRect(WP.l, yD, plotW, lh);
    g.font = '10px system-ui, sans-serif';
    g.textBaseline = 'middle';
    g.textAlign = 'right';
    g.fillStyle = oCol('incisor');
    g.fillText('Incisor', WP.l - 8, yI + lh / 2);
    g.fillStyle = oCol('doppler');
    g.fillText('Doppler', WP.l - 8, yD + lh / 2);
    const labs = {};
    for (const l of (kind.labels || [])) labs[l.id] = l.color;
    const evs = events();
    const cur = current();
    const now = performance.now();
    for (let i = 0; i < evs.length; i++) {
      const e = evs[i];
      const lo = Math.min(e.start, e.pair_t != null ? e.pair_t : e.start);
      const hi = Math.max(e.start, e.pair_t != null ? e.pair_t : e.start);
      if (hi < W.t0 || lo > W.t1) continue;
      const isNow = e === cur;
      const dim = !byOrigin(e) ? 0.25 : (e.label && !labs[e.label] ? 0.6 : 0.95);
      const x = tickAt(g, X, e, yI, yD, lh, dim, isNow);
      // The decision, as a cap in its colour above the lanes.
      if (e.label && labs[e.label]) {
        g.fillStyle = labs[e.label];
        g.fillRect(x - 3, yI - 4, 6, 3);
      }
      if (isNow) {
        g.strokeStyle = tok('--accent', '#E5A823');
        g.lineWidth = 1.5;
        g.strokeRect(x - 6.5, yI - 1.5, 13, lh * 2 + 7);
      }
      if (mark && e.id === mark) {
        g.strokeStyle = tok('--accent', '#E5A823');
        g.lineWidth = 1.2;
        g.setLineDash([3, 2]);
        g.strokeRect(x - 7.5, yI - 2.5, 15, lh * 2 + 9);
        g.setLineDash([]);
      }
    }
    // A merge being drawn: the one taken in slides onto the survivor.
    if (fuse) {
      const k = Math.min(1, (now - fuse.at) / FUSE_MS);
      if (k >= 1) fuse = null;
      else {
        const e = k * k * (3 - 2 * k);
        const x = X(fuse.from + (fuse.to - fuse.from) * e);
        const y = fuse.o === 'doppler' ? yD : yI;
        g.globalAlpha = 1 - 0.6 * e;
        g.strokeStyle = oCol(fuse.o);
        g.lineWidth = 3;
        g.beginPath(); g.moveTo(x, y + 2); g.lineTo(x, y + lh - 2); g.stroke();
        g.globalAlpha = 0.5 * (1 - e);
        g.strokeStyle = tok('--text', '#fff');
        g.lineWidth = 1;
        g.beginPath();
        g.arc(X(fuse.to), (yI + yD + lh) / 2, 4 + 10 * e, 0, Math.PI * 2);
        g.stroke();
        g.globalAlpha = 1;
      }
    }
    // The window's own clock.
    g.textBaseline = 'alphabetic';
    g.fillStyle = tok('--text-3', '#888');
    g.textAlign = 'left';
    g.fillText(clock(W.t0), WP.l, h - 2);
    g.textAlign = 'right';
    g.fillText(clock(W.t1), WP.l + plotW, h - 2);
    g.textAlign = 'center';
    g.fillText(Math.round((W.t1 - W.t0) * 1000) + ' ms shown', WP.l + plotW / 2, h - 2);
    g.textAlign = 'left';
  }

  function animateFuse() {
    if (!fuse) return;
    if (reduced()) { fuse = null; drawWin(); return; }
    const go = () => {
      drawWin();
      if (fuse) requestAnimationFrame(go);
    };
    requestAnimationFrame(go);
    setTimeout(() => { fuse = null; drawWin(); }, FUSE_MS + 60);
  }

  function hitWin(e) {
    const cv = $('#panWin');
    if (!cv) return null;
    const r = cv.getBoundingClientRect();
    const W = winRange();
    const plotW = Math.max(10, r.width - WP.l - WP.r);
    const px = e.clientX - r.left;
    const py = e.clientY - r.top;
    const inD = py > WP.t + WP.lane + 2;
    let best = null, bestD = 9;     // px
    for (const ev of events()) {
      const ts = ev.origin === 'both'
        ? [[timeBy(ev, 'incisor'), 'i'], [timeBy(ev, 'doppler'), 'd']]
        : [[ev.start, ev.origin !== 'doppler' ? 'i' : 'd']];
      for (const [t, lane] of ts) {
        const x = WP.l + ((t - W.t0) / (W.t1 - W.t0)) * plotW;
        const d = Math.abs(x - px) + ((lane === 'd') !== inD ? 4 : 0);
        if (d < bestD) { bestD = d; best = ev; }
      }
    }
    return best;
  }

  function winClick(e) {
    if (!set_) return;
    const ev = hitWin(e);
    if (!ev) return;
    if (e.shiftKey) {
      if (ev === current()) return;
      mark = mark === ev.id ? null : ev.id;
      render(); drawWin();
      return;
    }
    if (!wanted(ev)) { review = 'all'; origin = 'all'; }
    mark = null;
    goTo(events().indexOf(ev));
  }

  const AP = { l: 70, r: 10, t: 4, b: 4, lane: 9 };

  function drawAll() {
    const c = canvasFor('#panAll', AP.t + AP.lane * 2 + 2 + AP.b);
    if (!c || !set_ || !sess) return;
    const { g, w } = c;
    const dur = (sess.info || {}).duration_s || 1;
    const plotW = Math.max(10, w - AP.l - AP.r);
    const X = (t) => AP.l + (t / dur) * plotW;
    const yI = AP.t, yD = AP.t + AP.lane + 2;
    g.font = '9px system-ui, sans-serif';
    g.textBaseline = 'middle';
    g.textAlign = 'right';
    g.fillStyle = tok('--text-3', '#888');
    // On two lines, one per lane: on one it ran off the left edge.
    g.fillText('whole', AP.l - 8, yI + AP.lane / 2);
    g.fillText('recording', AP.l - 8, yD + AP.lane / 2);
    const ci = oCol('incisor'), cd = oCol('doppler');
    g.lineWidth = 1;
    for (const e of events()) {
      const x = Math.round(X(e.start)) + 0.5;
      g.globalAlpha = byOrigin(e) ? (e.label ? 0.9 : 0.5) : 0.12;
      if (e.origin !== 'doppler') {
        g.strokeStyle = ci;
        g.beginPath(); g.moveTo(x, yI); g.lineTo(x, yI + AP.lane); g.stroke();
      }
      if (e.origin !== 'incisor') {
        g.strokeStyle = cd;
        g.beginPath(); g.moveTo(x, yD); g.lineTo(x, yD + AP.lane); g.stroke();
      }
    }
    g.globalAlpha = 1;
    const cur = current();
    if (cur) {
      const x = Math.round(X(cur.start)) + 0.5;
      g.strokeStyle = tok('--accent', '#E5A823');
      g.lineWidth = 2;
      g.beginPath(); g.moveTo(x, 0); g.lineTo(x, yD + AP.lane + 2); g.stroke();
    }
    g.textAlign = 'left';
  }

  function allClick(e) {
    if (!set_ || !sess) return;
    const cv = $('#panAll');
    const r = cv.getBoundingClientRect();
    const plotW = Math.max(10, r.width - AP.l - AP.r);
    const dur = (sess.info || {}).duration_s || 1;
    const t = ((e.clientX - r.left) - AP.l) / plotW * dur;
    let best = -1, bestD = Infinity;
    events().forEach((ev, i) => {
      if (!byOrigin(ev)) return;
      const d = Math.abs(ev.start - t);
      if (d < bestD) { bestD = d; best = i; }
    });
    if (best >= 0) {
      if (!wanted(events()[best])) review = 'all';
      mark = null;
      goTo(best);
    }
  }

  /* ==================================================================
     Marks, presence, the receipt, where-you-were
     ================================================================== */
  function publishMarks(opts) {
    if (!sess || !set_) return;
    sess.curationMarks = {
      kind: set_.kind,
      index,
      at: (current() || {}).start,
      labels: (kind.labels || []).map((l) => ({ id: l.id, color: l.color,
                                                name: l.name })),
      events: events().map((e) => ({
        start: e.start, label: e.label || null,
        origin: e.origin || null,
        pair_t: e.pair_t != null ? e.pair_t : null,
        stamp: e.stamp || null,
      })),
      mark: mark,
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
        gid: set_.gid, kind: setKind, first: !!first, doing: 'panning',
        n_total: events().length,
        n_decided: events().filter((e) => e.label).length,
        n_this_visit: events().filter((e) => e.label).length - decidedAtEntry,
        at_index: index, at_time_s: (current() || {}).start,
      });
    } catch (e) { return; }
    beatOthers = res.others || [];
    if (sess) sess.curationOthers = beatOthers;
    for (const o of beatOthers) {
      const who = o.who || o.machine || 'somebody';
      if (toldAbout.has(who)) continue;
      toldAbout.add(who);
      toast(who + ' is in this pool too. Nothing is locked — this is so '
            + 'you do not collide by accident.', 'warn', 8000);
    }
    render();
  }

  const WHERE_KEY = 'panning_at';

  function rememberWhere() {
    if (!set_) return;
    const ev = current();
    let all = {};
    try { all = JSON.parse(BARRY.prefs.get(WHERE_KEY, '{}')) || {}; }
    catch (e) { all = {}; }
    all[set_.gid + ':' + setKind] = {
      review, origin, index, id: ev && ev.id, t: ev && ev.start, at: Date.now(),
    };
    const ks = Object.keys(all);
    if (ks.length > 60) {
      ks.sort((a, b) => (all[a].at || 0) - (all[b].at || 0));
      for (const k of ks.slice(0, ks.length - 60)) delete all[k];
    }
    BARRY.prefs.set(WHERE_KEY, JSON.stringify(all));
  }

  function recallWhere() {
    if (!set_) return null;
    let all = {};
    try { all = JSON.parse(BARRY.prefs.get(WHERE_KEY, '{}')) || {}; }
    catch (e) { return null; }
    const got = all[set_.gid + ':' + setKind];
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
    return { review: got.review || 'left', origin: got.origin || 'all',
             index: i, gone };
  }

  const RECEIPT_MIN = 8;

  async function receipt(gid, opts) {
    const quiet = !!(opts && opts.quiet);
    let got;
    try {
      got = await api(BARRY.ui.setUrl(gid, setKind, 'receipt'));
    } catch (e) { return; }
    const s = got.sitting || {};
    if (quiet && (s.n || 0) < RECEIPT_MIN) return;
    const labs = {};
    for (const l of (got.labels || [])) labs[l.id] = l;
    BARRY.confirm('That sitting',
      el('div', { class: 'rcpt' }, [
        el('div', { class: 'rcpt-big', text: (s.n || 0) + ' decided' }),
        el('div', { class: 'rcpt-sub',
          text: ((got.progress || {}).specified || 0) + ' of '
              + ((got.progress || {}).total || 0) + ' in this pool' }),
        el('div', { class: 'rcpt-labs' },
          Object.keys(s.by_label || {}).map((id) => el('div', {
            class: 'rcpt-lab' }, [
            el('i', { style: 'background:' + ((labs[id] || {}).color || '#888') }),
            el('span', { class: 'rl-name', text: (labs[id] || {}).name || id }),
            el('span', { class: 'rl-n', text: String(s.by_label[id]) }),
          ]))),
      ]), 'Close');
  }

  /* ==================================================================
     Drawing on the panes
     ================================================================== */

  /* Every pooled event in the window, in its detector's colour: the one
     being decided full height, the rest as ticks from the bottom, and an
     event both found drawn at Incisor's time with Doppler's own stamp
     beside it, joined by a bracket at the top. From the session, never
     from module state, so the aid window draws it too. */
  function draw(ctx, s, win, x0, plotW, y0, plotH, P) {
    const marks = s && s.curationMarks;
    if (!marks || BARRY.ui.kindBase(marks.kind) !== KIND) return;
    // The main window remembers what it is showing, for the window strip.
    if (set_ && s === sess) {
      const was = lastWin;
      if (!was || was.t0 !== win.t0 || was.t1 !== win.t1) {
        lastWin = { t0: win.t0, t1: win.t1 };
        requestAnimationFrame(drawWin);
      }
    }
    const span_ = win.t1 - win.t0;
    if (!(span_ > 0)) return;
    const X = (t) => x0 + ((t - win.t0) / span_) * plotW;
    const byId = {};
    for (const l of (marks.labels || [])) byId[l.id] = l;
    const evs = marks.events || [];
    // Whatever fade the caller set ("fade the marks" means these too), as a
    // multiplier on every alpha below -- each one is an assignment.
    const A = ctx.globalAlpha;
    ctx.save();
    ctx.lineCap = 'butt';
    for (let i = 0; i < evs.length; i++) {
      const e = evs[i];
      if (e.start < win.t0 - 0.01 || e.start > win.t1 + 0.01) continue;
      const isNow = i === marks.index;
      const x = Math.round(X(e.start)) + 0.5;
      const top = isNow ? y0 : y0 + plotH * 0.78;
      // The stamp it is filed under, in that detector's colour; the other
      // detector's time beside it, in the other's.
      const own = stampOf(e) || 'incisor';
      const colI = oCol(own);
      // A dark and a light line under the colour, so it reads on a CSD too.
      ctx.globalAlpha = 0.5 * A;
      ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(0,0,0,0.9)';
      ctx.beginPath(); ctx.moveTo(x - 1, top); ctx.lineTo(x - 1, y0 + plotH); ctx.stroke();
      ctx.strokeStyle = 'rgba(255,255,255,0.9)';
      ctx.beginPath(); ctx.moveTo(x + 1, top); ctx.lineTo(x + 1, y0 + plotH); ctx.stroke();
      ctx.globalAlpha = (isNow ? 1 : (e.label ? 0.9 : 0.7)) * A;
      ctx.strokeStyle = colI;
      ctx.lineWidth = isNow ? 2.5 : 1.6;
      ctx.setLineDash(!isNow && !e.label ? [4, 3] : []);
      ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, y0 + plotH); ctx.stroke();
      ctx.setLineDash([]);
      if (e.origin === 'both' && e.pair_t != null) {
        const xd = Math.round(X(e.pair_t)) + 0.5;
        ctx.strokeStyle = oCol(otherOf(own));
        ctx.lineWidth = isNow ? 2 : 1.2;
        ctx.setLineDash([2, 2]);
        ctx.beginPath(); ctx.moveTo(xd, top + (isNow ? 10 : 4)); ctx.lineTo(xd, y0 + plotH);
        ctx.stroke();
        ctx.setLineDash([]);
        // The bracket: these two are one event.
        ctx.globalAlpha = (isNow ? 0.9 : 0.6) * A;
        ctx.strokeStyle = tok('--text-2', '#aaa');
        ctx.lineWidth = 1;
        const yb = top + (isNow ? 6 : 2);
        ctx.beginPath(); ctx.moveTo(x, yb); ctx.lineTo(xd, yb); ctx.stroke();
      }
      if (isNow) {
        ctx.globalAlpha = A;
        const lab = e.label ? byId[e.label] : null;
        ctx.fillStyle = lab ? lab.color : tok('--accent', '#E5A823');
        ctx.beginPath();
        ctx.arc(x, y0 + 7, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.font = '11px system-ui, sans-serif';
        ctx.textAlign = 'left';
        const word = (e.origin === 'both'
          ? 'both, at ' + KEEP_WORD[own] + '’s' : e.origin === 'doppler'
          ? 'Doppler' : e.origin === 'incisor' ? 'Incisor' : '')
          + (lab ? ' · ' + lab.name : '');
        if (word) ctx.fillText(word, x + 7, y0 + 24);
      }
    }
    ctx.restore();
  }

  function rebind(next) {
    if (!next || !set_) return;
    sess = next;
    sess.curation = { kind: set_.kind, set: set_, index };
    useBand();
    publishMarks();
    lightChannel(current());
    render();
  }

  /* Put the current event back in the middle at whatever span the window
     is now on. Called by xplore's setWindow after a zoom, the way Checkup's
     is: a zoom from the pane's buttons, the wheel or the span field keeps
     the event in view, and is the span from then on. */
  function recentre() {
    if (!set_ || !sess) return;
    const shown = paneSpan();
    if (shown) setSpan(shown);
    goTo(index, true);
  }

  return {
    enter, exit, draw, rebind, recentre, receipt,
    step: (d) => step(d),
    goTo: (i) => goTo(i),
    assign: (id) => assign(id),
    merge, undo,
    clear: clearLabel,
    bank,
    // Many at once (2026-10-19): the list, Label many, and the write both
    // use -- `labelMany(ids, label)` takes event ids, for a harness.
    listAll, bulkDialog,
    labelMany: (ids, label) => {
      const want = new Set(ids || []);
      return labelMany(events().filter((e) => want.has(e.id)), label);
    },
    events: () => events().map((e) => ({ id: e.id, start: e.start,
                                         label: e.label || null,
                                         origin: e.origin || null,
                                         pair_t: e.pair_t != null ? e.pair_t : null,
                                         stamp: e.stamp || null })),
    get review() { return review; },
    get origin() { return origin; },
    get active() { return !!set_; },
    get state() {
      return set_ ? { gid: set_.gid, kind: setKind, index, mark,
                      total: events().length, left: left() } : null;
    },
    // For a harness: pick the second event of a merge, as a shift-click does.
    _mark: (id) => { mark = id; render(); drawWin(); },
    _keys: keys,
    _leadOf: leadOf,
    _strips: drawStrips,
    // For a harness: the span the mode will use, and what the pane shows.
    _span: () => ({ span, pane: paneSpan() }),
  };
})();

BARRY.modes.register('panning', BARRY.panning);
