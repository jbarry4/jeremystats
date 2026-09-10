/* ==========================================================================
   cfcscope.js -- CFCScope: looking at rhythms and how they couple.

   The third mode, after DS curation and StrataScope, and the first that
   decides nothing. Nothing here is saved, nothing is claimed, no set goes on
   anybody's bench. It exists because the CFC pipeline in `Reviving CFC` can
   tell you whether a whole channel has phase-amplitude coupling, offline, in
   minutes -- and cannot tell you about the window you are looking at.

   Two things it unlocks:

     * Theta power that is band-resolved. The existing `theta` panel filters
       4-12 Hz in one go, which answers "how much theta" and cannot answer
       "which theta". This one is one narrow band per row, exactly as
       ThetaPower.m computes it, so a rhythm that moves from 7 Hz to 9 Hz
       during a session is visible as a thing that moved.

     * A comodulogram of a chosen window. Deliberate rather than automatic:
       it is two seconds of arithmetic without surrogates and half a minute
       with them, and something that expensive should be asked for by name.

   A mode rather than a panel because it takes over the pane layout and opens
   a companion window, exactly as StrataScope does -- and because the banner
   saying "nothing here is saved" is worth having on screen the whole time.
   ========================================================================== */
'use strict';

BARRY.cfc = (function () {
  let sess = null;
  let gid = null;
  let aidWin = null;      // the panels window
  let mapWin = null;      // the comodulogram window

  /* ==================================================================
     Entering and leaving
     ================================================================== */
  /* `gidOrPath` may be a registry gid, a path on disk, or nothing at all --
     nothing meaning "the recording already open", which is what somebody
     scrolling through a session and wanting a closer look actually wants. */
  async function enter(gidOrPath) {
    /* One mode at a time. Both of the others take over the panes, the
       keyboard and a second window, and entering one on top of another left
       two toolbars stacked and two key handlers fighting over the same
       presses. `active` on curate is a getter, not a method. */
    if (BARRY.curate && BARRY.curate.active) BARRY.curate.exit();
    if (BARRY.strata && BARRY.strata.exit) {
      try { BARRY.strata.exit(); } catch (e) { /* it may not be in */ }
    }
    if (sess) exit();                  // re-entering: start clean

    let path = gidOrPath || null;
    gid = null;
    if (path && !/[\\/:]/.test(path)) {
      // Looks like a gid rather than a path, so ask what it is.
      gid = path;
      path = null;
      try {
        const r = await api('/api/registry/' + encodeURIComponent(gid));
        path = ((r.session || {}).here || [])[0] || null;
      } catch (e) {
        toast('No such recording: ' + e.message, 'err', 8000);
        return false;
      }
      if (!path) {
        toast('None of that recording’s paths are reachable from this '
              + 'machine, so there is nothing to look at.', 'err', 9000);
        return false;
      }
    }
    if (!path) {
      const open = BARRY.views.xplore.current && BARRY.views.xplore.current();
      path = open && open.path;
    }
    if (!path) {
      toast('Open a recording first, or pick one from the Toolkit.',
            'warn', 6000);
      return false;
    }

    setView('xplore');
    sess = await BARRY.views.xplore.open(path);
    if (!sess) return false;

    setMode('cfc', exit);
    layout();
    bar();
    document.addEventListener('keydown', keys, true);
    BARRY.activity.log('cfc.enter', { path: path, gid: gid });
    return true;
  }

  function exit() {
    if (aidWin && !aidWin.closed) { try { aidWin.close(); } catch (e) {} }
    if (mapWin && !mapWin.closed) { try { mapWin.close(); } catch (e) {} }
    aidWin = null;
    mapWin = null;
    setMode(null);
    const b = document.getElementById('cfcBar');
    if (b) b.remove();
    document.documentElement.style.removeProperty('--bottom-bar');
    document.removeEventListener('keydown', keys, true);
    if (sess) BARRY.activity.log('cfc.leave', { path: sess.path });
    sess = null;
    gid = null;
    if (BARRY.views.xplore.refreshAll) BARRY.views.xplore.refreshAll();
  }

  /* The traces get this window; the derived panels get their own.

     Same arrangement StrataScope arrived at, and for the same reason: the
     thing being read -- the squiggle -- needs the width, and a band-power
     raster sharing a 2x2 with it gets a quarter of the screen for something
     whose whole point is a vertical axis seventeen rows tall. Two monitors
     and this is the layout people build by hand; one monitor and you
     alt-tab, which still beats four squares. */
  function layout() {
    BARRY.views.xplore.setPanes([{ panel: 'traces' }], { col: 1, row: 1 });
    openAids();
  }

  function openAids() {
    if (aidWin && !aidWin.closed) { try { aidWin.focus(); } catch (e) {} return; }
    aidWin = BARRY.views.xplore.popOutPanes(sess, [
      { panel: 'bandpower' },
      { panel: 'spectrogram', fmin: 1, fmax: 250 },
    ], {
      role: 'cfc', name: 'barry-cfc-aids', width: 720, height: 820,
      /* Headers and tabs folded away: both panes are the same recording and
         the labels would cost more of a short pane than they are worth. The
         control strips STAY -- unlike StrataScope's aids, these two have
         settings somebody is meant to change, and a band axis you cannot
         reach is the panel not doing its job. */
      chrome: 'notabs,noheads',
    });
  }

  /* ==================================================================
     The bar
     ================================================================== */
  function bar() {
    let b = document.getElementById('cfcBar');
    if (!b) {
      b = el('div', { class: 'cfc-bar', id: 'cfcBar' });
      const body = document.getElementById('xfBody');
      if (body) body.appendChild(b); else document.body.appendChild(b);
    }
    b.innerHTML = '';

    const chan = firstChannel();
    b.appendChild(el('div', { class: 'cfc-bar-row' }, [
      el('strong', { text: 'CFCScope' }),
      el('span', { class: 'hint',
        text: 'Band-resolved theta power and the spectrogram are in the '
            + 'second window.' }),
      el('button', {
        class: 'btn ghost sm',
        text: aidWin && !aidWin.closed ? 'Focus the panels'
                                       : 'Reopen the panels',
        title: 'The band power and spectrogram window',
        onclick: () => { openAids(); bar(); },
      }),
      el('div', { style: 'flex:1' }),
      el('span', { class: 'cfc-where', text: whereText(chan) }),
      el('button', {
        class: 'btn sm cfc-go',
        text: 'Comodulogram…',
        title: 'Phase-amplitude coupling across a grid of band pairs, for '
             + 'this window and this channel. Seconds without surrogates, '
             + 'half a minute with them — so it opens a window and asks '
             + 'before it runs anything.',
        onclick: openMap,
      }),
    ]));
    // The banner already says the mode; this says the part that is a promise.
    b.appendChild(el('p', { class: 'hint cfc-note',
      text: 'Nothing in this mode writes anything down. Move the window, '
          + 'change the channel, change the bands — no set is claimed '
          + 'and no decision is recorded.' }));

    /* Reserve the height of the bar for the toasts.

       They are fixed at bottom-right above this, which is exactly where
       `Comodulogram…` sits -- and entering the mode fires three of them
       ("Reopening…", "view restored", "Loaded 2 events"), so the button
       this bar exists to offer spent its first seconds underneath a stack
       of them. `exit()` already removed this variable; nothing ever set it.

       Measured, not assumed: the bar wraps to two rows on a narrow window,
       which is the same reason StrataScope measures its own. */
    const h = Math.ceil(b.getBoundingClientRect().height);
    if (h) document.documentElement.style.setProperty('--bottom-bar',
                                                      h + 'px');
  }

  function firstChannel() {
    if (!sess || !sess.sel || !sess.sel.size) return null;
    const i = Math.min.apply(null, Array.from(sess.sel));
    const ch = (sess.info.channels || [])[i];
    return ch ? { index: i, label: ch.label, number: ch.number } : null;
  }

  function whereText(chan) {
    if (!sess) return '';
    const t0 = sess.t0 || 0;
    const span = sess.span || 0;
    return (chan ? chan.label : 'no channel selected')
         + '  ·  ' + t0.toFixed(1) + '–' + (t0 + span).toFixed(1)
         + ' s  (' + span.toFixed(1) + ' s)';
  }

  /* Kept in step with the window without polling: xplore fires this whenever
     the window or the selection moves, and the bar is one line of text. */
  function refresh() {
    if (!sess) return;
    const where = document.querySelector('#cfcBar .cfc-where');
    if (where) where.textContent = whereText(firstChannel());
    /* Through the published handle: `BARRY` is a `const`, so
       `mapWin.BARRY` is undefined from out here. See comod.js. */
    if (mapWin && !mapWin.closed && mapWin.barryComod) {
      try { mapWin.barryComod.openerMoved(); } catch (e) { /* closing */ }
    }
  }

  function keys(e) {
    if (!sess) return;
    if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    // Just the one. A view-only mode with a page of shortcuts is a mode
    // pretending to be a tool.
    if (e.key === 'c' || e.key === 'C') {
      e.preventDefault();
      openMap();
    }
  }

  /* ==================================================================
     The comodulogram window
     ================================================================== */
  /* Its own window, not a dialog. You keep it open across several windows of
     the recording and stack the maps up to compare them, which a modal
     cannot do -- and comparing two maps is most of what the thing is for. */
  function openMap() {
    if (mapWin && !mapWin.closed) {
      try { mapWin.focus(); } catch (e) {}
      try { mapWin.barryComod.openerMoved(); } catch (e) {}
      return;
    }
    mapWin = window.open(location.origin + '/?role=comod#comod',
                         'barry-cfc-comod',
                         'width=1080,height=900,menubar=no,toolbar=no');
    if (!mapWin) {
      toast('The comodulogram window was blocked. Allow pop-ups for '
            + '127.0.0.1, then press C again.', 'err', 9000);
      return;
    }
    try { mapWin.focus(); } catch (e) { /* not important */ }
  }

  /* What the comodulogram window asks the opener for. One function so there
     is exactly one answer to "what is on screen", whoever is asking. */
  function context() {
    if (!sess) return null;
    const chan = firstChannel();
    return {
      path: sess.path,
      evenOnly: sess.evenOnly,
      invert: sess.invert,
      label: (sess.info && sess.info.label) || sess.path,
      t0: sess.t0,
      t1: sess.t0 + sess.span,
      channel: chan ? chan.index : 0,
      channelLabel: chan ? chan.label : null,
      channels: (sess.info.channels || []).map((c) => ({
        index: c.index, label: c.label, number: c.number,
        bad: sess.bad.has(c.number) || !!c.bad,
      })),
      highpass: sess.hp, lowpass: sess.lp, notch: sess.notch,
      duration: (sess.info && sess.info.duration_s) || 0,
      fs: (sess.info && sess.info.fs) || 0,
    };
  }

  return {
    enter, exit, refresh, context, openMap,
    get active() { return !!sess; },
  };
}());

/* What the comodulogram window reads to fill its form in. A property on
   `window` rather than `BARRY.cfc`, because `BARRY` is a `const` and so is
   invisible to any other window. */
window.barryCfc = BARRY.cfc;
