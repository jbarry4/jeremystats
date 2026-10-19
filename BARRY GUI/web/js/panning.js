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
   ========================================================================== */
'use strict';

BARRY.panning = (function () {
  const KIND = 'pooled';
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
  const url = (what) => '/api/curation/' + encodeURIComponent(set_.gid)
    + '/' + KIND + (what ? '/' + what : '');

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
  async function enter(gid, entryId, opts) {
    BARRY.modes.leaveAllBut('panning');
    if (set_) exit();
    if (entryId) {
      const made = await ensureSet(gid, entryId);
      if (!made) return false;
    }
    let data;
    try {
      data = await api('/api/curation/' + encodeURIComponent(gid) + '/' + KIND);
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

  /* A set from the pooled entry, unless there is one already from it. One
     set per (recording, kind): a set from a different pool is replaced
     only when somebody says so. */
  async function ensureSet(gid, entryId) {
    let existing = null;
    try {
      const got = await api('/api/curation/' + encodeURIComponent(gid) + '/' + KIND);
      existing = got.set || null;
    } catch (e) { /* no set is the ordinary case */ }
    if (existing) {
      const from = (existing.source || {}).bank_entry;
      if (!entryId || from === entryId) return true;
      const ok = await BARRY.confirm(
        'There is already a pooled set on this recording',
        el('div', { class: 'fix-facts' }, [
          el('p', { text: '"' + (existing.name || 'the existing set')
              + '" has ' + ((existing.progress || {}).specified || 0)
              + ' of ' + ((existing.progress || {}).total || 0)
              + ' decided. Starting from this pool instead replaces it.' }),
          el('p', { text: 'Its decisions are already banked as versions of '
              + 'the pool it came from, so they are not lost — but they '
              + 'will not be in front of you any more.' }),
        ]), 'Replace it', true);
      if (!ok) return true;
    }
    const pick = await chooseVersion(gid, entryId);
    if (pick === null) return false;
    try {
      await apiPost('/api/curation/from-bank', {
        gid, kind: KIND, entry: entryId, replace: true,
        version: pick && pick.id != null ? pick.id : (pick ? pick.v : 0),
      });
    } catch (e) {
      toast('Could not make a set from that pool: ' + e.message, 'err', 9000);
      return false;
    }
    return true;
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
    rememberWhere();
    try { BARRY.prefs.flush(); } catch (e) { /* the timer will get it */ }
    BARRY.activity.log('panning.leave', { gid: set_.gid, left: left() }, sess);
    if (beatTimer) { clearInterval(beatTimer); beatTimer = null; }
    apiPost('/api/presence/release', { gid: set_.gid, kind: KIND })
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
     the optimistic step and the write agree. */
  const hasI = (o) => o === 'incisor' || o === 'both';
  function leadOf(a, b) {
    if (hasI(b.origin) && !hasI(a.origin)) return b;
    if (hasI(a.origin) || a.start <= b.start) return a;
    return b;
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

  const KEEP = ['origin', 'pair_t', 'label', 'by', 'at', 'channel',
                'merged_by', 'merged_at'];
  const BACK = ['start', 'end', 'channel', 'amplitude', 'origin', 'pair_t',
                'label', 'by', 'at', 'note'];
  const pickOf = (e, keys) => {
    const out = {};
    for (const k of keys) if (e[k] !== undefined && e[k] !== null) out[k] = e[k];
    return out;
  };

  async function merge() {
    const a = current();
    const b = partner();
    if (!a || !b) {
      toast('There is nothing next to this one to merge it with.', null, 4000);
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
    const lead = leadOf(a, b);
    const other = lead === a ? b : a;
    const before = pickOf(lead, KEEP);
    const dropped = pickOf(other, BACK);
    const dropAt = events().indexOf(other);
    const fromX = other.start;

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
      const res = await apiPost(url('merge'), { keep: a.id, drop: b.id });
      if (res.event) Object.assign(lead, res.event);
      if (res.progress) set_._progress = res.progress;
      if (res.dropped && res.dropped !== other.id) {
        // The server chose otherwise; its answer is the truth.
        await reload();
      } else if (set_) {
        render();          // who merged it, as the server stamped it
      }
      BARRY.activity.log('panning.merge', { gid: set_.gid, kept: lead.id,
                                            gap_ms: +gap.toFixed(2) }, sess);
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
      m: merge,
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
      const body = $('#xfBody');
      if (body) body.appendChild(bar);
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
        el('span', { text: ev.origin === 'both' ? 'both found it'
                         : ev.origin ? ORIGIN_WORD[ev.origin] + ' only'
                         : 'origin not known' }),
      ]) : null,
      pair != null
        ? el('span', { class: 'cur-sub',
            title: 'Where the other detector put it',
            text: (ev.origin === 'both' ? 'Doppler ' : 'other ')
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
    cats.appendChild(el('button', {
      class: 'cur-cat pan-merge' + (mark ? ' armed' : ''),
      disabled: b ? null : 'disabled',
      title: b ? 'Make this and the ' + (mark ? 'picked' : 'nearest')
                 + ' event one: ' + ORIGIN_WORD[b.origin || 'incisor']
                 + '’s, ' + (gap >= 0 ? gap.toFixed(1) + ' ms later'
                                           : (-gap).toFixed(1) + ' ms earlier')
                 + '. Shift-click another on the strip to pick it.  [M]'
               : 'Nothing next to this one',
      onclick: merge,
    }, [
      el('span', { text: mark ? 'Merge with the picked one' : 'Merge with nearest' }),
      el('kbd', { text: 'M' }),
      gap != null ? el('span', { class: 'cur-count',
        text: (gap >= 0 ? '+' : '−') + Math.abs(gap).toFixed(1) + ' ms' })
        : null,
    ].filter(Boolean)));
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
      el('span', { class: 'spacer' }),
      el('button', { class: 'btn ghost sm', text: 'Bank the results…',
        title: 'Write these decisions and merges as a new version of the pool',
        onclick: bank }),
      el('button', { class: 'btn ghost sm', text: 'Line them up…',
        title: 'Take the spikes to Lock',
        onclick: () => toTool('lock') }),
      el('button', { class: 'btn ghost sm', text: 'Leave', onclick: exit }),
    ]));
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
      const xd = ev.pair_t != null ? Math.round(X(ev.pair_t)) + 0.5 : x;
      line(x, yI, ci);
      line(xd, yD, cd);
      g.strokeStyle = tok('--text-3', '#888');
      g.lineWidth = 1;
      g.beginPath(); g.moveTo(x, yI + lh - 2); g.lineTo(xd, yD + 2); g.stroke();
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
      const ts = [[ev.start, ev.origin !== 'doppler' ? 'i' : 'd']];
      if (ev.origin === 'both' && ev.pair_t != null) ts.push([ev.pair_t, 'd']);
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
        gid: set_.gid, kind: KIND, first: !!first, doing: 'panning',
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
    all[set_.gid + ':' + KIND] = {
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
    const got = all[set_.gid + ':' + KIND];
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
      got = await api('/api/curation/' + encodeURIComponent(gid) + '/' + KIND
                      + '/receipt');
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
    if (!marks || marks.kind !== KIND) return;
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
      const colI = e.origin === 'doppler' ? oCol('doppler') : oCol('incisor');
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
        ctx.strokeStyle = oCol('doppler');
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
        const word = (e.origin === 'both' ? 'both' : e.origin === 'doppler'
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

  /* ==================================================================
     The step page in ToolKit
     ================================================================== */

  /* The way in: pools being sorted, and every pool banked that nobody has
     started on -- setpicker.js, the same list Spotter uses. */
  function paintStep() {
    const h = document.getElementById('tkResult');
    if (!h) return;
    h.style.opacity = '1';
    h.innerHTML = '';
    h.dataset.tool = 'panning';      // so ToolKit's refresh leaves it be
    h.appendChild(BARRY.ui.stepHeader({
      title: 'Panning',
      step: BARRY.ui.stepOf('panning'),
      blurb: 'Sort a pool one event at a time: spike, garbage or flag. '
           + 'Every event shows which detector found it, and two that are '
           + 'one event can be merged.',
    }));
    const box = el('div', { class: 'card' });
    h.appendChild(box);
    BARRY.setPicker.mount(box, {
      kind: KIND, tool: 'panning', noun: 'events',
      mine: { id: 'junction', label: 'From Junction', chip: 'Junction',
              test: (p) => /^The Confluence/.test(p) },
      otherLabel: 'other',
      empty: 'Nothing pooled yet. Pool a recording in Junction — step 1 '
           + '— and it is here to sort.',
      enter: (gid, entryId) => enter(gid, entryId),
    });
  }

  return {
    enter, exit, draw, rebind, recentre, receipt, paintStep,
    step: (d) => step(d),
    goTo: (i) => goTo(i),
    assign: (id) => assign(id),
    merge, undo,
    clear: clearLabel,
    bank,
    events: () => events().map((e) => ({ id: e.id, start: e.start,
                                         label: e.label || null,
                                         origin: e.origin || null,
                                         pair_t: e.pair_t != null ? e.pair_t : null })),
    get review() { return review; },
    get origin() { return origin; },
    get active() { return !!set_; },
    get state() {
      return set_ ? { gid: set_.gid, kind: KIND, index, mark,
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
