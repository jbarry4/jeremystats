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

    // One second either way. A dentate spike is a few tens of
    // milliseconds and what you need around it is enough context to tell it
    // from an artifact -- 0.6 s was tight enough that a spike near the edge
    // of the window had nothing on one side of it.
    span = (opts && opts.span) || 1.0;
    index = 0;
    history = [];
    /* Open on a pass that has something in it.

       An imported sort arrives with every candidate already decided, so the
       undecided pass is empty and the mode would open on a blank screen --
       which is exactly the case this was built for: "a lot of them have been
       sorted and we just need to review the flagged items". */
    review = 'left';

    setMode('curate', exit);
    layout();
    // Hand the candidates to the session so the trace can draw them.
    sess.curation = { kind: set_.kind, set: set_, index: 0 };
    publishMarks();
    if (!events().some((e) => !e.label)) {
      review = events().some((e) => e.label === 'flag') ? 'flag' : 'all';
    }
    goTo(firstWanted(), true);
    render();

    BARRY.activity.log('curation.enter', {
      gid, kind: set_.kind, n: (set_.events || []).length,
      left: left(),
    }, sess);
    return true;
  }

  function exit() {
    if (!set_) return;
    BARRY.activity.log('curation.leave', {
      gid: set_.gid, kind: set_.kind, left: left(),
    }, sess);
    if (sess) { delete sess.curation; delete sess.curationMarks; }
    // Tell the other windows the mode is over, or they keep drawing marks
    // for a set nobody is deciding any more.
    if (sess && BARRY.views.xplore.publishCuration) {
      BARRY.views.xplore.publishCuration(sess, null);
    }
    if (aidWin && !aidWin.closed) { try { aidWin.close(); } catch (e) {} }
    aidWin = null;
    setMode(null);
    set_ = null; kind = null; sess = null; history = [];
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
  const wanted = (ev) => {
    if (!ev) return false;
    if (review === 'all') return true;
    if (review === 'flag') return ev.label === 'flag';
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

  function publishMarks() {
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

  function goTo(i, quiet) {
    const n = events().length;
    if (!n) return;
    index = Math.max(0, Math.min(n - 1, i));
    const ev = current();
    if (sess.curation) sess.curation.index = index;
    publishMarks();
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
    history.push({ id: ev.id, from: was });
    markRev += 1;
    lastChange = { index, label: labelId };
    publishMarks();          // that mark's colour just changed
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
    } catch (e) {
      ev.label = was;
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
    } catch (e) { toast(e.message, 'err'); }
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
      el('button', { class: 'mini', text: '↶', title: 'Undo  (u)',
                     disabled: history.length ? null : 'disabled',
                     onclick: undo }),
      /* Which pass you are making. Flagged is the one that was missing:
         Flag is already a label in both vocabularies, and marking one used
         to mean never finding it again without walking the whole set. */
      el('div', { class: 'ctl' }, [
        el('label', { text: 'Review' }),
        el('div', { class: 'seg sm', id: 'curReview' }, [
          ['left', 'Undecided', 'The ones with no decision yet'],
          ['flag', 'Flagged', 'Only the ones marked Flag \u2014 the second '
                            + 'pass over the ones that needed a longer look'],
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
                ? 'Nothing is flagged yet \u2014 press f on a candidate that '
                  + 'needs another look.'
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
          text: label + (id === 'flag'
            ? ' (' + events().filter((e) => e.label === 'flag').length + ')'
            : ''),
        }))),
      ]),
      el('div', { class: 'ctl' }, [
        el('label', { text: 'Window s' }),
        el('input', {
          type: 'number', step: '0.1', value: String(span),
          style: 'width:56px',
          onchange: (e) => {
            span = Math.max(0.05, parseFloat(e.target.value) || 1);
            goTo(index);
          },
        }),
      ]),
      el('span', { class: 'cur-saving', id: 'curSaving', text: '' }),
      el('div', { style: 'flex:1' }),
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

  function keys(e) {
    if (!set_) return;
    if (isTyping(e)) return;
    const k = e.key.toLowerCase();

    /* Navigation is checked first, and wins.

       The server strips reserved keys out of every vocabulary, so this should
       never actually matter -- but "should never" is how `p` ended up meaning
       both "previous" and "sputter", and the key that moves you has to be the
       one thing that always moves you. */
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

  async function bank() {
    const who = await askPath('Who is banking these?',
                              'your name or email');
    if (!who) return;
    try {
      const res = await apiPost(
        '/api/curation/' + encodeURIComponent(set_.gid) + '/'
        + encodeURIComponent(set_.kind) + '/bank',
        { added_by: who });
      toast('Banked ' + res.entries.length + ' entr'
            + (res.entries.length === 1 ? 'y' : 'ies') + ': '
            + res.entries.map((x) => x.label + ' (' + x.n + ')').join(', '),
            'ok', 8000);
      BARRY.refreshSync();
    } catch (e) { toast(e.message, 'err', 8000); }
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
    enter, exit, draw,
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
    get state() {
      return set_ ? { gid: set_.gid, kind: set_.kind, index,
                      total: events().length, left: left() } : null;
    },
  };
})();
