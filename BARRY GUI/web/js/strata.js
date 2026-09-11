/* ==========================================================================
   strata.js -- StrataScope: saying which layer each channel is in.

   The standalone version worked on four exported PNGs. You uploaded a voltage
   raster, a CSD, a multiunit plot and a theta plot, cropped each one down to
   the heatmap, and then trusted that 64 evenly spaced rows landed on the
   right channels.

   The crop is the whole problem. It is per-image, it has to be redone every
   time anyone re-exports, and when it is slightly off every label is off by a
   fraction of a channel with nothing on screen to say so.

   Here the panels are drawn from the recording, so Jarvis already knows which
   lane is channel 14. There is nothing to crop and nothing to drift. And
   because it is not a snapshot, you can filter, change the window, or zoom
   into the theta while you decide -- which is what you actually want when a
   boundary is ambiguous.

   The rail is aligned to the raster's lanes by measurement, not by assuming
   even spacing: the pane reports where each lane is, and the rail follows.
   ========================================================================== */
'use strict';

BARRY.strata = (function () {
  let sheet = null;      // the layer sheet as the server has it
  let regions = [];      // the vocabulary
  let sess = null;
  let gid = null;
  let brush = null;      // the region a drag paints, when one is armed
  let hover = -1;
  let saving = 0;

  /* Which channels are picked out, by CSC number.

     The rail used to ask for the mouse to be precise twice: land on a
     four-pixel row, then read a dropdown that covered the thing being
     labelled. Selecting first and labelling second needs precision once,
     and the second half can be a keystroke. */
  let picked = new Set();
  let anchor = null;     // for shift-click, the other end of the range

  /* How strongly the layer wash is drawn over the rasters. The bands are
     there to show where a boundary fell, and at some point they are in the
     way of the data that decides where it should have fallen -- so this is
     the reader's to set, not a constant. */
  const WASHES = [
    { id: 'off', name: 'Off', alpha: 0, why: 'No wash at all' },
    { id: 'faint', name: 'Faint', alpha: 0.10,
      why: 'Just enough to see the boundary' },
    { id: 'clear', name: 'Clear', alpha: 0.22,
      why: 'Readable without hiding the trace' },
    { id: 'solid', name: 'Solid', alpha: 0.42,
      why: 'For checking the layout at a glance' },
  ];
  let wash = 'faint';

  function washAlpha() {
    const w = WASHES.find((x) => x.id === wash);
    return w ? w.alpha : 0.10;
  }

  /* ==================================================================
     Entering and leaving
     ================================================================== */
  async function enter(gidIn) {
    /* One mode at a time.

       Both modes take over the panes, the keyboard and the aid window, and
       both leave a toolbar behind. Entering one on top of the other left two
       toolbars stacked, two sets of key handlers fighting over the same
       presses, and an aid window belonging to whichever got there first. */
    // `active` is a getter, not a method -- calling it throws.
    if (BARRY.curate && BARRY.curate.active) BARRY.curate.exit();
    if (sheet) exit();                 // re-entering: start clean
    gid = gidIn;
    let info;
    try {
      info = await api('/api/layers/' + encodeURIComponent(gid));
    } catch (e) {
      info = null;
    }

    let sessRow = info && info.session;
    if (!sessRow) {
      try {
        const r = await api('/api/registry/' + encodeURIComponent(gid));
        sessRow = r.session;
      } catch (e) {
        toast('No such recording: ' + e.message, 'err', 8000);
        return false;
      }
    }
    const path = (sessRow.here || [])[0];
    if (!path) {
      toast('None of this recording’s paths are reachable from this '
            + 'machine, so there is nothing to look at.', 'err', 9000);
      return false;
    }

    setView('xplore');
    sess = await BARRY.views.xplore.open(path);
    if (!sess) return false;

    // The channel order as it is right now: even-only and missing files both
    // change it, so it is sent on every visit rather than trusted from the
    // first one.
    const channels = sess.info.channels.map((c) => c.number);
    let started;
    try {
      started = await apiPost('/api/layers/' + encodeURIComponent(gid)
                              + '/start', { channels });
    } catch (e) {
      toast('Could not open the layer sheet: ' + e.message, 'err', 8000);
      return false;
    }
    sheet = started.sheet;
    regions = sheet.regions || [];

    /* Opening it is what puts it on the bench, the same as event curation.
       Nothing else does: a sheet that exists because a scan made one is not
       work in progress, it is a row. */
    apiPost('/api/layers/' + encodeURIComponent(gid) + '/open', { on: true })
      .then((res) => { if (res && res.sheet) sheet.assignee = res.sheet.assignee; })
      .catch((e) => {
        /* An archived sheet is not put on the bench by being labelled --
           that would un-archive it as a side effect of looking at it, which
           is the thing archiving is meant to survive. Labelling still
           works and still saves. */
        if (/archived/i.test((e && e.message) || '')) {
          toast('This sheet is archived, so it is not on the bench. '
                + 'Labelling it still works and still saves; take it out of '
                + 'the archive from the ToolKit if you want it back in the '
                + 'list.', null, 8000);
        }
      });

    // Said in the shell, not just in a toolbar: a mode you can be in
    // without noticing is one you make mistakes in.
    setMode('strata', exit);
    layout();
    sess.strata = { gid, labels: sheet.labels, regions };
    render();
    // The panes settle a frame or two after the layout change, and the rail
    // is measured off them.
    requestAnimationFrame(() => setTimeout(alignRail, 260));
    window.addEventListener('resize', alignRail);

    BARRY.activity.log('strata.enter', {
      gid, channels: channels.length,
      labelled: (sheet.progress || {}).labelled,
    }, sess);
    return true;
  }

  function exit() {
    if (!sheet) return;
    BARRY.activity.log('strata.leave', {
      gid, labelled: (sheet.progress || {}).labelled,
    }, sess);
    if (sess) delete sess.strata;
    if (aidWin && !aidWin.closed) { try { aidWin.close(); } catch (e) {} }
    aidWin = null;
    setMode(null);
    sheet = null; sess = null; gid = null; brush = null;
    const rail = $('#strataRail');
    if (rail) rail.remove();
    const bar = $('#strataBar');
    if (bar) bar.remove();
    const body = $('#xfBody');
    if (body) body.classList.remove('strata-on');
    document.documentElement.style.removeProperty('--rail-w');
    document.documentElement.style.removeProperty('--bottom-bar');
    window.removeEventListener('resize', alignRail);
    document.removeEventListener('keydown', keys, true);
    if (BARRY.views.xplore.refreshAll) BARRY.views.xplore.refreshAll();
  }

  /* The traces get the window; the aids get a window of their own.

     They used to share a 2x2, which meant the squiggles -- the thing a layer
     boundary is actually read off -- had a quarter of the screen and the
     channel rail had to compress to match. So: this window is traces, and
     the four aids move to a second window that follows it. Two monitors and
     you have the layout everyone was building by hand; one monitor and you
     alt-tab, which is still better than four squares. */
  let aidWin = null;

  function layout() {
    BARRY.views.xplore.setPanes([{ panel: 'traces' }], { col: 0.5, row: 0.5 });
    openAids();
  }

  function openAids() {
    // Reuse the window if it is still up: re-entering the mode should focus
    // the aids, not litter the desktop with copies.
    if (aidWin && !aidWin.closed) { try { aidWin.focus(); } catch (e) {} return; }
    const every8 = (sess.info.channels || [])
      .filter((c, i) => i % 8 === 0).map((c) => c.index);
    aidWin = BARRY.views.xplore.popOutPanes(sess, [
      { panel: 'csd' },
      { panel: 'theta' },
      { panel: 'voltage' },
      { panel: 'spectrogram', tfChannels: every8, tfMode: 'stack',
        fmin: 1, fmax: 250 },
    ], { role: 'aids', name: 'barry-strata-aids', width: 720, height: 1000,
         // Folded on arrival. These four are for glancing at: the headers,
         // control strips and channel lists cost more of a short pane than
         // they are worth, and every one of them has a sliver to bring it
         // back if you want it.
         chrome: 'notabs,noheads,nostrip,nochannels' });
  }

  /* ==================================================================
     The rail
     ================================================================== */
  /* Held out here rather than inside rail(), because painting a channel
     re-renders the rail -- so a flag scoped to the render was thrown away by
     the first stroke of the drag it was meant to be tracking, and the
     mouseup that cleared it was clearing a closure nobody was reading. One
     flag, one listener, both outliving the rows. */
  let painting = false;
  window.addEventListener('mouseup', () => { painting = false; });

  const channels = () => (sess && sess.info.channels) || [];
  const labelOf = (num) => (sheet && sheet.labels[String(num)]) || null;
  const regionOf = (id) => regions.find((r) => r.id === id) || null;

  function render() {
    if (!sheet) return;
    bar();
    rail();
    if (BARRY.views.xplore.redraw) BARRY.views.xplore.redraw();
  }

  function bar() {
    let b = $('#strataBar');
    if (!b) {
      b = el('div', { class: 'strata-bar', id: 'strataBar' });
      const body = $('#xfBody');
      if (body) body.appendChild(b); else document.body.appendChild(b);
      document.addEventListener('keydown', keys, true);
    }
    b.innerHTML = '';

    /* Two rows. Everything but the brushes on the first, so thirteen layers
       wrapping cannot push Leave off the bottom of the window -- which is
       what it was doing on anything narrower than about 1200px. */
    const top = el('div', { class: 'strata-bar-top' });
    b.appendChild(top);

    const pr = sheet.progress || {};
    top.appendChild(el('div', { class: 'cur-where' }, [
      el('strong', { text: 'StrataScope' }),
      el('span', { class: 'cur-sub',
                   text: sheet.session_label || gid }),
      el('span', { class: 'cur-count',
                   text: pr.labelled + ' / ' + pr.total + ' channels' }),
    ]));

    top.appendChild(el('div', { class: 'cur-prog' }, [
      el('i', { style: 'width:' + (pr.percent || 0) + '%' }),
      el('span', { text: (pr.left || 0) + ' left' }),
    ]));

    /* A brush, because a shank passes through a layer for a run of channels
       and clicking a dropdown per channel is sixty-four dropdowns. Pick a
       layer, then click or drag down the rail. */
    const brushes = el('div', { class: 'strata-brushes' });
    /* What the layer buttons do depends on whether anything is selected,
       and the bar says which it is rather than leaving it to be discovered.
       With a selection they label it; without one they arm a brush to
       paint with. */
    brushes.appendChild(el('span', {
      class: 'strata-mode',
      text: picked.size
        ? picked.size + ' selected — pick a layer'
        : (brush ? 'drag the rail to paint' : 'click a channel, or pick a layer to paint with'),
    }));
    regions.forEach((r, i) => {
      brushes.appendChild(el('button', {
        class: 'strata-brush' + (brush === r.id ? ' on' : '')
             + (picked.size ? ' arm' : ''),
        style: '--cat:' + r.color,
        title: (picked.size
                 ? 'Label the ' + picked.size + ' selected channel'
                   + (picked.size === 1 ? '' : 's') + ' ' + r.name
                 : 'Paint with ' + r.name)
             + (r.note ? ' — ' + r.note : '')
             + (i < 9 ? '   (' + (i + 1) + ')' : ''),
        onclick: async () => {
          if (await labelPicked(r.id)) return;
          brush = brush === r.id ? null : r.id;
          render();
        },
      }, [
        i < 9 ? el('kbd', { text: String(i + 1) }) : null,
        el('span', { text: r.name }),
      ].filter(Boolean)));
    });
    /* Taking a label off is as much a decision as putting one on, and it
       had no button at all -- only ctrl-drag, which nothing said. */
    brushes.appendChild(el('button', {
      class: 'strata-brush clearone',
      title: picked.size
        ? 'Unlabel the ' + picked.size + ' selected channel'
          + (picked.size === 1 ? '' : 's') + '   (0)'
        : 'Select channels first',
      disabled: picked.size ? null : 'disabled',
      onclick: () => labelPicked(null),
    }, [el('kbd', { text: '0' }), el('span', { text: 'Unlabel' })]));
    b.appendChild(brushes);

    top.appendChild(el('div', { class: 'cur-nav' }, [
      el('button', {
        class: 'mini', text: '⤓ Fill down',
        title: 'Give every unlabelled channel the label of the one above it',
        onclick: fillDown,
      }),
      el('button', {
        class: 'mini', text: 'Clear', onclick: clearAll,
      }),
      /* How strong the layer wash is over the rasters.
         The bands show where a boundary fell; past a point they are in the
         way of the data that decides where it should have fallen. That is a
         judgement per recording and per moment, so it is a control rather
         than a constant. */
      el('span', { class: 'strata-wash' }, [
        el('span', { class: 'strata-wash-label', text: 'Overlay' }),
        el('span', { class: 'ctl-seg' }, WASHES.map((w) => el('button', {
          class: 'mini' + (wash === w.id ? ' on' : ''),
          text: w.name, title: w.why,
          onclick: () => {
            wash = w.id;
            render();
            if (BARRY.views.xplore.refreshAll) BARRY.views.xplore.refreshAll();
          },
        }))),
      ]),
      el('span', { class: 'cur-saving', id: 'strataSaving', text: '' }),
      el('div', { style: 'flex:1' }),
      el('button', {
        class: 'btn ghost sm', text: 'Export CSV',
        onclick: () => window.open('/api/layers/' + encodeURIComponent(gid)
                                   + '/export', '_blank'),
      }),
      el('button', { class: 'btn ghost sm', text: 'Leave', onclick: exit }),
    ]));
  }

  /* One row per channel, sitting exactly on the raster's lane for it.

     The lane geometry comes from the pane rather than from an assumption of
     even spacing -- the whole reason this beats labelling a PNG is that the
     alignment is measured, not guessed. */
  /* ---------- selecting channels ----------

     Click picks one. Shift-click takes everything between it and the last
     one clicked. Ctrl-click adds or removes a single row without disturbing
     the rest. Dragging extends, which is how a run of twelve channels gets
     picked without twelve clicks.

     Nothing here writes: selecting is asking a question, and the answer is
     given separately by naming a layer. That separation is the whole point
     -- it is why the mouse only has to be accurate once. */
  function selectAt(i, e) {
    const chans = channels();
    const c = chans[i];
    if (!c) return;
    if (e && e.shiftKey && anchor != null) {
      const lo = Math.min(anchor, i), hi = Math.max(anchor, i);
      picked = new Set();
      for (let k = lo; k <= hi; k++) picked.add(chans[k].number);
    } else if (e && (e.ctrlKey || e.metaKey)) {
      if (picked.has(c.number)) picked.delete(c.number);
      else picked.add(c.number);
      anchor = i;
    } else {
      // A plain click on the only selected row clears it, so there is a way
      // out that is not "click somewhere harmless".
      const only = picked.size === 1 && picked.has(c.number);
      picked = only ? new Set() : new Set([c.number]);
      anchor = only ? null : i;
    }
    render();
  }

  function extendTo(i) {
    if (anchor == null) return;
    const chans = channels();
    const lo = Math.min(anchor, i), hi = Math.max(anchor, i);
    picked = new Set();
    for (let k = lo; k <= hi; k++) picked.add(chans[k].number);
    render();
  }

  /* Give every selected channel a layer. This is what a tag click and a
     number key both end up calling. */
  async function labelPicked(regionId) {
    if (!picked.size) return false;
    const nums = Array.from(picked);
    for (const n of nums) await paint(n, regionId);
    /* The selection stays. Labelling a run and then finding one channel
       wrong is the common case, and clearing it would mean picking the
       whole run again to fix one. */
    render();
    return true;
  }

  function rail() {
    let r = $('#strataRail');
    const host = $('#paneGrid');
    if (!host) return;
    if (!r) {
      r = el('div', { class: 'strata-rail', id: 'strataRail' });
      host.parentNode.insertBefore(r, host);
      // The body has to become a positioning context and give the grid room;
      // the rail is laid over the left edge rather than woven into the flex
      // column, which would put it above the panes rather than beside them.
      const body = $('#xfBody');
      if (body) body.classList.add('strata-on');
    }
    r.innerHTML = '';

    /* Which channel the cursor is on, said out loud. At 64 channels three
       quarters of the rows have no number of their own, and "which one am I
       about to paint" is the question the rail has to be able to answer. */
    r.appendChild(el('div', { class: 'strata-head' }, [
      el('span', { text: 'Layer' }),
      el('span', { class: 'strata-at', id: 'strataAt', text: '' }),
      el('span', { class: 'strata-n', text: channels().length + ' ch' }),
    ]));
    const idle = brush ? 'drag to paint' : 'pick a layer below';
    const readout = (t) => {
      const at = $('#strataAt');
      if (at) at.textContent = t || idle;
    };
    readout(null);

    const list = el('div', { class: 'strata-rows' });
    channels().forEach((c, i) => {
      const id = labelOf(c.number);
      const reg = regionOf(id);
      const row = el('div', {
        class: 'strata-row' + (id ? ' has' : '') + (hover === i ? ' hl' : '')
             + (picked.has(c.number) ? ' picked' : ''),
        style: reg ? '--cat:' + reg.color : '',
        // The row shrinks with the lane, so at 64 channels the tooltip is
        // where the layer name actually lives.
        title: c.label + (reg ? '  —  ' + reg.name : '  —  unlabelled')
             + '\nClick to select · shift-click for a range · then a layer '
             + 'below, or its number',
        onmouseenter: () => {
          hover = i;
          readout(c.label + (reg ? '  \u2014  ' + reg.name : ''));
          // Dragging still paints when a layer is armed, for anybody who
          // has got used to it -- but it is no longer the only way in.
          if (painting && brush) paint(c.number, brush);
          else if (painting) extendTo(i);
        },
        onmousedown: (e) => {
          e.preventDefault();
          painting = true;
          if (brush && !e.shiftKey) { paint(c.number, e.ctrlKey ? null : brush); return; }
          selectAt(i, e);
        },
      }, [
        el('span', { class: 'strata-num', text: String(c.number) }),
        el('span', { class: 'strata-sw' }),
        el('span', { class: 'strata-name', text: reg ? reg.name : '—' }),
      ]);
      list.appendChild(row);
    });
    list.addEventListener('mouseleave', () => readout(null));

    /* The runs. Appended last on purpose: the packed rules thin the numbers
       with :nth-child, so anything inserted before the rows would shift
       which ones show. */
    list.appendChild(runLabels());
    r.appendChild(list);
    alignRail();
  }

  /* One label per contiguous stretch of the same layer.

     Positioned in lane units so alignRail's --lane keeps it honest without
     this having to know any pixels. A run too short for a word simply shows
     nothing -- the colour band is still there saying where the boundary
     is. */
  function runLabels() {
    const box = el('div', { class: 'strata-spans' });
    const chans = channels();
    let i = 0;
    while (i < chans.length) {
      const id = labelOf(chans[i].number);
      let j = i + 1;
      while (j < chans.length && labelOf(chans[j].number) === id) j += 1;
      const reg = regionOf(id);
      const n = j - i;
      box.appendChild(el('div', {
        class: 'strata-span' + (reg ? '' : ' none'),
        style: 'top: calc(var(--lane, 14px) * ' + i + ');'
             + 'height: calc(var(--lane, 14px) * ' + n + ');'
             + (reg ? '--cat:' + reg.color + ';' : ''),
        title: (reg ? reg.name : 'unlabelled')
             + '  \u2014  ' + n + ' channel' + (n === 1 ? '' : 's') + ', '
             + chans[i].label + ' to ' + chans[j - 1].label,
      }, [
        el('b', { text: reg ? reg.name : 'unlabelled' }),
        n > 1 ? el('i', { text: '\u00d7' + n }) : null,
      ].filter(Boolean)));
      i = j;
    }
    return box;
  }

  /* Put the rail's rows on the raster's lanes.

     Measured from the pane's own canvas box, so it stays right when the pane
     is resized, the chrome is hidden, or the window changes -- none of which
     a cropped PNG could survive. */
  function alignRail() {
    const r = $('#strataRail');
    const canvas = document.querySelector(
      '#paneGrid .pane .pane-canvas-host');
    if (!r || !canvas) return;
    const rows = r.querySelector('.strata-rows');
    if (!rows) return;
    /* Stop the rail above the bar. Both are in #xfBody, the rail absolutely
       positioned and the bar a flex child at the bottom -- a rail running to
       bottom:0 covers the bar's left edge, which is where the brushes live.
       Measured rather than assumed, because the bar wraps to two rows on a
       narrow window. */
    const barEl = $('#strataBar');
    const barH = barEl ? Math.ceil(barEl.getBoundingClientRect().height) : 0;
    r.style.bottom = barH + 'px';
    /* Toasts sit bottom-right at z-index 60; without this one covers Export
       CSV whenever anything is saved. */
    document.documentElement.style.setProperty('--bottom-bar', barH + 'px');

    const box = canvas.getBoundingClientRect();
    const railBox = r.getBoundingClientRect();
    // The raster's plot area, as drawPane lays it out.
    const padTop = 8, padBottom = 22;
    const top = box.top - railBox.top + padTop;
    const height = Math.max(1, box.height - padTop - padBottom);
    rows.style.top = top + 'px';
    rows.style.height = height + 'px';
    const n = channels().length || 1;
    const lane = height / n;
    rows.style.setProperty('--lane', lane + 'px');

    /* How much room each row actually got, said out loud so the CSS can
       react to it.

       At 32 channels a lane is around 18px and a row can carry a number, a
       swatch and a dropdown. At 64 it is nine, and all three were still
       being drawn -- 64 dropdowns six pixels tall, numbers overlapping
       their neighbours. The rail became unreadable exactly when the shank
       had the most to say.

       tight   the dropdown goes; painting with a brush is the way to
               label anyway, and the swatch widens into a band so the
               layers read as continuous colour
       packed  the numbers thin to every fourth, keeping their space so
               nothing shifts */
    rows.classList.toggle('tight', lane < 17);
    rows.classList.toggle('packed', lane < 12);
    rows.classList.toggle('very-packed', lane < 8.5);

    /* Wider once the rows stop carrying their own names, because that is
       when the run labels appear and they need somewhere to be. The panes
       track the same variable, so nothing overlaps. */
    document.documentElement.style.setProperty(
      '--rail-w', lane < 17 ? '158px' : '122px');

    /* A run shorter than a line of text drops its text. Half a clipped word
       reads as damage; the colour band is still saying where the boundary
       is, and the head readout names whatever the cursor is on. */
    rows.querySelectorAll('.strata-span').forEach((s) => {
      s.classList.toggle('tiny', s.getBoundingClientRect().height < 11);
    });
  }

  /* ==================================================================
     Changing
     ================================================================== */
  async function paint(channel, region) {
    if (!sheet) return;
    const key = String(channel);
    const was = sheet.labels[key] || null;
    if (was === region) return;
    if (region) sheet.labels[key] = region; else delete sheet.labels[key];
    recount();
    render();

    saving += 1;
    updateSaving();
    try {
      const res = await apiPost('/api/layers/' + encodeURIComponent(gid)
                                + '/set', { channel, region });
      sheet = res.sheet;
    } catch (e) {
      if (was) sheet.labels[key] = was; else delete sheet.labels[key];
      toast('That did not save: ' + e.message, 'err', 8000);
      render();
    } finally {
      saving -= 1;
      updateSaving();
    }
  }

  function recount() {
    const total = channels().length;
    const done = channels().filter((c) => labelOf(c.number)).length;
    sheet.progress = {
      total, labelled: done, left: total - done,
      percent: total ? Math.round(1000 * done / total) / 10 : 0,
    };
  }

  async function fillDown() {
    try {
      const res = await apiPost('/api/layers/' + encodeURIComponent(gid)
                                + '/fill',
                                { channels: channels().map((c) => c.number) });
      sheet = res.sheet;
      if (sess) sess.strata.labels = sheet.labels;
      toast('Filled ' + res.filled + ' channel(s) downward.', 'ok');
      render();
    } catch (e) { toast(e.message, 'err', 7000); }
  }

  async function clearAll() {
    try {
      const res = await apiPost('/api/layers/' + encodeURIComponent(gid)
                                + '/clear', {});
      sheet = res.sheet;
      if (sess) sess.strata.labels = sheet.labels;
      render();
    } catch (e) { toast(e.message, 'err'); }
  }

  function updateSaving() {
    const n = $('#strataSaving');
    if (n) n.textContent = saving ? 'saving…' : '';
  }

  function keys(e) {
    if (!sheet || isTyping(e)) return;
    const k = e.key;
    if (k === 'Escape') {
      e.preventDefault();
      // A selection first: leaving the whole mode because somebody wanted
      // to drop a selection is a big answer to a small question.
      if (picked.size) { picked = new Set(); anchor = null; render(); return; }
      exit();
      return;
    }
    if (k === '0' && picked.size) { e.preventDefault(); labelPicked(null); return; }
    if (k === 'a' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      picked = new Set(channels().map((c) => c.number));
      anchor = 0;
      render();
      return;
    }
    const i = parseInt(k, 10);
    if (i >= 1 && i <= 9 && regions[i - 1]) {
      e.preventDefault();
      /* With a selection the number labels it; without one it arms the
         brush, which is what the number always did. The same key doing the
         obvious thing in both states is worth more than two keys each
         doing one. */
      if (picked.size) { labelPicked(regions[i - 1].id); return; }
      brush = brush === regions[i - 1].id ? null : regions[i - 1].id;
      render();
    }
  }

  /* ==================================================================
     The overlay on the rasters
     ================================================================== */
  function draw(ctx, s, win, x0, plotW, y0, plotH, P, panelRes) {
    if (!s || !sheet) return;
    /* `s.strata` is how the aid window knows there is a sheet to draw: it is
       a separate page with its own session objects and no module state.

       In THIS window the module already knows, and gating on the flag alone
       was fragile -- entering StrataScope reopens the recording, and a
       reopen can hand back a different session object from the one the flag
       was set on. The overlay then drew nowhere at all, which is not a
       subtle failure and took a canvas count to notice. So: the flag, or
       the recording being the one under the sheet. */
    const mine = s.identity && s.identity.gid === gid;
    if (!s.strata && !mine) return;
    let chans = channels();
    if (!chans.length) return;

    /* An image panel says which rows it actually drew.

       The traces show every selected channel in order, so lanes and
       channels line up one to one. A raster does not: CSD drops the first
       and last, and a probe-column pane shows a subset. Laying the sheet's
       channel order over those rows would put every band one or two
       channels off -- which is worse than no overlay, because it looks
       right. So when the panel reports its rows, they are what is used. */
    if (panelRes && Array.isArray(panelRes.rows) && panelRes.rows.length) {
      const byNum = new Map(chans.map((c) => [c.number, c]));
      const got = [];
      for (const r of panelRes.rows) {
        const c = byNum.get(r.number);
        got.push(c || { number: r.number });
      }
      chans = got;
    }
    const lane = plotH / chans.length;

    const alpha = washAlpha();
    ctx.save();
    if (alpha > 0) {
      ctx.globalAlpha = alpha;
      for (let i = 0; i < chans.length; i++) {
        const reg = regionOf(labelOf(chans[i].number));
        if (!reg) continue;
        ctx.fillStyle = reg.color;
        ctx.fillRect(x0, y0 + i * lane, plotW, Math.ceil(lane));
      }
    }

    /* The selection, on the data rather than only on the rail.

       Which channels are about to be labelled is the question the raster
       can answer and the rail cannot: the rail says "rows 30 to 41", the
       raster says whether those rows are the ones where the signal
       changes. Drawn whatever the wash is set to -- turning the layers down
       is not a reason to stop showing what you are pointing at. */
    if (picked.size) {
      ctx.globalAlpha = 1;
      ctx.strokeStyle = P.accent || '#4bc7f0';
      ctx.lineWidth = 1;
      for (let i = 0; i < chans.length; i++) {
        if (!picked.has(chans[i].number)) continue;
        const top = y0 + i * lane;
        ctx.globalAlpha = 0.14;
        ctx.fillStyle = P.accent || '#4bc7f0';
        ctx.fillRect(x0, top, plotW, Math.ceil(lane));
        // A tick at the edge, because at 64 channels a lane is a few pixels
        // and a wash that thin is easy to miss.
        ctx.globalAlpha = 0.95;
        ctx.fillRect(x0, top, 3, Math.max(1, Math.ceil(lane)));
      }
    }

    // A firm line where the layer changes: that boundary is the thing being
    // decided, and a wash of colour alone does not show exactly where it fell.
    // The boundary line stays unless the wash is off entirely: it is the
    // thing being decided, and it costs almost no ink.
    ctx.globalAlpha = alpha > 0 ? 0.85 : 0;
    ctx.lineWidth = 1;
    let prev = null;
    for (let i = 0; i < chans.length; i++) {
      const id = labelOf(chans[i].number);
      if (prev !== null && id !== prev) {
        const reg = regionOf(id) || regionOf(prev);
        ctx.strokeStyle = reg ? reg.color : P.accent;
        ctx.beginPath();
        ctx.moveTo(x0, Math.round(y0 + i * lane) + 0.5);
        ctx.lineTo(x0 + plotW, Math.round(y0 + i * lane) + 0.5);
        ctx.stroke();
      }
      prev = id;
    }
    ctx.restore();
  }

  return {
    enter, exit, draw, alignRail,
    // Same reason as curate.js: a reopen replaces the session object.
    rebind: (next) => {
      if (!next || !sheet) return;
      sess = next;
      sess.strata = { gid, labels: sheet.labels, regions };
      render();
      requestAnimationFrame(() => setTimeout(alignRail, 200));
    },
    get active() { return !!sheet; },
    get state() {
      return sheet ? { gid, labels: sheet.labels, channels: channels(),
                       progress: sheet.progress, brush } : null;
    },
  };
})();
