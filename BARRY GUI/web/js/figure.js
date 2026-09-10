/* ==========================================================================
   figure.js -- The figure builder: preview before you download.

   A layout is a grid of panels. You set the page size, drop panels into cells,
   retitle them, pick colormaps, fill in the metadata block, and see the real
   rendered figure before committing to a PNG/PDF/SVG.

   The preview is produced by the same matplotlib code that does the export, so
   what you see is exactly what you get -- not an approximation.
   ========================================================================== */
'use strict';

BARRY.figure = (function () {
  let XF = null;
  let sess = null;
  let layout = null;
  let selected = 0;
  let panelDefs = [];
  let colormaps = [];
  let pages = [];
  let rendering = false;
  let pendingRender = false;

  /* Undo.

     Hooked in one place. Every mutation in here ends in a redraw, so the
     redraw is where the change is noticed: if the layout no longer matches
     the last snapshot, the snapshot becomes an undo step. That way dragging
     a panel, adding a column, removing a row and editing a title are all
     undoable without any of them having to remember to say so.

     `events` is left out of the snapshot. It is the detector's list carried
     through to the renderer, nothing here edits it, and a set of several
     hundred would be copied on every keystroke for no reason. */
  const UNDO_MAX = 60;
  let undoStack = [];
  let redoStack = [];
  let current = null;       // the layout as of the last snapshot
  let restoring = false;    // so restoring does not record itself
  let keysOn = false;

  async function open(xfState, session) {
    XF = xfState;
    sess = session;

    if (!panelDefs.length) {
      try {
        const d = await api('/api/panels');
        panelDefs = d.panels || [];
        colormaps = d.colormaps || [];
        pages = d.pages || [];
      } catch (e) { /* fall back to defaults */ }
    }

    layout = buildInitialLayout();
    selected = 0;
    render();
    schedulePreview();
  }

  function buildInitialLayout() {
    const now = new Date();
    const sys = (BARRY.state.catalog && BARRY.state.catalog.system) || {};
    /* Everything on screen, where it is on screen.

       This claimed to seed from the panes and then discarded the
       arrangement: four at most, the first alone on the top row and the rest
       beneath it, whatever the layout actually was. A six-pane probe view
       arrived as four panels in the wrong places and had to be rebuilt by
       hand -- which is most of the work the builder exists to save.

       The pane grid's shape is fixed per count (1 across, 2 across, 2x2,
       and 3x2 for a probe), so the slot index maps straight onto a row and
       a column. Video and tracking panes are left out because they are not
       something a figure can hold. */
    const slots = (XF.panes || [])
      .map((p, i) => ({ p, i }))
      .filter(({ p }) => p && XF.sessions[p.sessionId]
                         && p.panel !== 'video' && p.panel !== 'tracking');

    const PANE_COLS = { 1: 1, 2: 2, 4: 2, 6: 3 };
    const cols = PANE_COLS[XF.nPanes] || Math.min(2, Math.max(1, slots.length));

    /* Is what is on screen a probe laid out across the panes?

       `colTag` is on a pane because `layoutProbe` put a probe column in it,
       so a pane set carrying one per pane is a probe view however it got
       there -- which is a better question than "is the mode H10", because
       the mode can be right while the panes have moved on. */
    const probeSlots = slots.filter(({ p }) => p.colTag && p.channels);
    const isProbeView = probeSlots.length === slots.length
      && slots.length >= 2
      && new Set(slots.map(({ p }) => p.panel || 'traces')).size === 1
      && new Set(slots.map(({ p }) => p.sessionId)).size === 1;

    const panels = (isProbeView
      /* One panel for the whole probe.
         Six cells was six pictures that cannot be read against each other:
         separate colour scales, separate depth axes, and a grid the user
         then has to rebuild by hand. The panel subdivides itself in the
         renderer -- back shank's columns, a gap, front shank's -- so it
         stays 1x1 here, movable and spannable like any other. */
      ? [{
          panel: slots[0].p.panel || 'traces',
          session_id: slots[0].p.sessionId,
          probe: (XF.sessions[slots[0].p.sessionId] || {}).probe || 'h10d',
          probe_view: true,
          title: labelFor(slots[0].p.panel || 'traces') + ' \u00b7 all '
            + slots.length + ' columns',
          row: 0, col: 0, rowspan: 1, colspan: 1,
          cmap: slots[0].p.cmap || 'jet',
          fmin: slots[0].p.fmin, fmax: slots[0].p.fmax,
          /* The pinned scale travels with it. Pinning six columns to one
             range on screen and printing six auto-scaled ones would be the
             same bug in a different room.

             A pin lives on the recording when it was set from the master
             strip and on the pane when it was set in that pane, so both are
             asked -- reading only the pane missed every pin that was made
             the usual way. */
          clim: slots[0].p.clim
            || (XF.sessions[slots[0].p.sessionId] || {}).clim,
          ylim: slots[0].p.ylim
            != null ? slots[0].p.ylim
              : (XF.sessions[slots[0].p.sessionId] || {}).ylim,
        }]
      : (slots.length
        ? slots.map(({ p, i }) => ({
            panel: p.panel || 'traces',
            session_id: p.sessionId,
            title: labelFor(p.panel || 'traces')
              + (p.colLabel ? ' \u00b7 ' + p.colLabel : ''),
            row: Math.floor(i / cols), col: i % cols,
            // 1x1 by default. A panel that silently claims two cells is
            // surprising, and there was no obvious way to give the span back.
            rowspan: 1, colspan: 1,
            cmap: p.cmap || 'jet',
            channel: p.channel,
            /* What this pane is actually showing. Dropped until now, so a
               pane holding one probe column printed as the whole
               selection -- and six such panes printed as six identical
               views of the same 64 channels. */
            channels: p.channels ? Array.from(p.channels) : undefined,
            clim: p.clim || (XF.sessions[p.sessionId] || {}).clim,
            ylim: p.ylim != null
              ? p.ylim : (XF.sessions[p.sessionId] || {}).ylim,
            /* Everything a time-frequency panel needs, taken from the
               request the pane itself would send. Asked for as "if a
               spectogram is already open, emulate that with the filters,
               channels selected, etc." -- and the channel list, the mode,
               the band and the display crop were all being dropped, so a
               figure of a six-channel stack came out as one channel. */
            ...tfFrom(i),
          }))
        : [{ panel: 'traces', session_id: sess.id,
             title: labelFor('traces'), row: 0, col: 0,
             rowspan: 1, colspan: 1, cmap: 'jet' }]));

    return {
      title: sess.identity.label || sess.info.name,
      subtitle: '',
      page: 'letter_landscape',
      width_in: 11, height_in: 8.5, dpi: 300,
      /* Big enough for what is actually there, and no bigger.
         `cols` above maps a pane slot onto a column; it is not a floor. A
         four-pane layout with one pane filled opened as a 1x2 grid holding
         one panel -- an empty cell nobody asked for, because the screen had
         room for one rather than because the figure wants one. */
      rows: Math.max(...panels.map((p) => p.row + p.rowspan), 1),
      cols: Math.max(...panels.map((p) => p.col + p.colspan), 1),
      t0: r6(sess.t0), t1: r6(sess.t0 + sess.span),
      highpass: sess.hp, lowpass: sess.lp, notch: sess.notch,
      cmap: 'jet', spacing_um: sess.spacing,
      channels: Array.from(sess.sel).sort((a, b) => a - b),
      bad_channels: Array.from(sess.bad),
      events: sess.events,
      gain: sess.gain,
      show_metadata: true,
      identity: sess.identity,
      session_label: sess.identity.label,
      metadata: {
        author: gitUser(),
        date: now.toLocaleString(),
        machine: sys.hostname || '',
        source_path: sess.path,
        notes: '',
      },
      panels,
    };
  }

  /* Which columns of the probe this panel draws, and in what order.

     Collapsing the six panes into one panel answered "make it a single 1x1
     for the entire 6 pane view" and took the other half of the request with
     it -- "remove certain windows and arrange certain windows in certain
     order". This is that half. A shank that broke mid-experiment is three
     columns of noise beside three of data sharing one colour scale, so
     dropping it makes the rest readable, not just tidier. */
  function probeColumns(p) {
    const def = (XF.probes || []).find(
      (x) => x.id === (p.probe || 'h10d'));
    const all = (def && def.columns) || [];
    if (!all.length) return el('div');

    /* The probe's own order, which is what an absent `probe_columns`
       means. Back shank left-to-right, then front: the order the renderer
       lays them out in, so the chips read like the picture. */
    const rank = { back: 0, front: 1 };
    const order = all.slice().sort(
      (a, b) => (rank[a.shank] - rank[b.shank])
        || ((a.x_um || 0) - (b.x_um || 0)));
    const ids = order.map((c) => c.id);
    const chosen = (p.probe_columns && p.probe_columns.length)
      ? p.probe_columns.slice() : ids.slice();

    const commit = (next) => {
      /* Back to "all of them" rather than a list that happens to hold all
         of them: the renderer's fallback is the probe's order, and a
         panel that has been put back should be indistinguishable from one
         that was never changed. */
      const same = next.length === ids.length
        && next.every((id, i) => id === ids[i]);
      if (same) delete p.probe_columns;
      else p.probe_columns = next;
      render(); schedulePreview();
    };

    const box = el('div', { class: 'probe-cols' });
    /* Shown in the chosen order, then whatever was dropped, faint, so
       bringing one back does not mean remembering it existed. */
    const rest = ids.filter((id) => chosen.indexOf(id) < 0);
    const rows = chosen.map((id) => ({ id, on: true }))
      .concat(rest.map((id) => ({ id, on: false })));

    for (const row of rows) {
      const c = all.find((x) => x.id === row.id) || {};
      const at = chosen.indexOf(row.id);
      box.appendChild(el('div', {
        class: 'pc-chip' + (row.on ? '' : ' off'),
        draggable: row.on ? 'true' : null,
        title: (row.on
          ? 'Drawn ' + (at + 1) + ' of ' + chosen.length
            + '. Click to drop it; drag it onto another to reorder.'
          : 'Not drawn. Click to bring it back.')
          + '\n' + (c.label || ''),
        ondragstart: (e) => {
          e.dataTransfer.setData('text/plain', 'pc:' + row.id);
          e.dataTransfer.effectAllowed = 'move';
        },
        ondragover: (e) => { e.preventDefault(); },
        ondrop: (e) => {
          e.preventDefault();
          const got = e.dataTransfer.getData('text/plain') || '';
          if (!got.startsWith('pc:')) return;
          const from = got.slice(3);
          if (from === row.id) return;
          const next = chosen.filter((x) => x !== from);
          const to = next.indexOf(row.id);
          next.splice(to < 0 ? next.length : to, 0, from);
          commit(next);
        },
        onclick: () => {
          if (row.on) {
            /* The last one cannot be dropped: a panel drawing no columns
               is not a picture of anything, and the fallback would
               silently redraw all six instead. */
            if (chosen.length <= 1) {
              toast('A probe panel has to draw at least one column. Drop a '
                    + 'different one first, or change the panel type.',
                    null, 5000);
              return;
            }
            commit(chosen.filter((x) => x !== row.id));
          } else {
            commit(chosen.concat([row.id]));
          }
        },
      }, [
        el('span', { class: 'pc-id', text: row.id }),
        el('span', { class: 'pc-what',
          text: (c.column || '') + ' \u00b7 ' + (c.shank || '') }),
        el('span', { class: 'pc-csc', text: cscRun(c) }),
      ]));
    }

    /* The way back. Clicking the faint chips one at a time appends them,
       so six columns in the order you happened to click them is not the
       probe's order -- and the renderer's "all of them" fallback IS that
       order. Without this the way back was a page reload. */
    const reset = p.probe_columns ? el('button', {
      class: 'linkish fb-clear', text: 'Back to probe order',
      title: 'All ' + ids.length + ' columns, laid out as they sit on the '
           + 'probe: ' + ids.join(', '),
      onclick: () => commit(ids.slice()),
    }) : null;

    return el('div', {}, [
      el('div', { class: 'section-label', style: 'margin-top:6px',
                  text: 'Probe columns' }),
      el('p', { class: 'hint',
        text: chosen.length === ids.length
          ? 'All ' + ids.length + ' columns, in probe order. Click one to '
            + 'drop it; drag one onto another to reorder.'
          : chosen.length + ' of ' + ids.length + ' columns: '
            + chosen.join(', ') + '. Click a faint one to bring it back.' }),
      box,
      reset,
    ].filter(Boolean));
  }

  /* The channel numbers in a column, as a run. Same rule as the grid cells
     and the same rule the renderer prints under each column head. */
  function cscRun(c) {
    const got = (c && c.csc) || [];
    if (!got.length) return '';
    return 'CSC ' + ranges(got);
  }

  /* Which channels a time-frequency panel runs on, and how they combine.

     A single dropdown was the whole control, while the viewer has had
     multi-channel panels for a while -- so a figure of what was on screen
     silently became one channel of it. The list and the mode are the same
     two questions the viewer asks, in the same words. */
  function tfChannels(p, sess) {
    const all = ((sess || {}).info || {}).channels || [];
    const chosen = (p.tf_channels && p.tf_channels.length)
      ? p.tf_channels.map(Number)
      : (p.channel != null ? [Number(p.channel)] : []);

    const commit = (next) => {
      p.tf_channels = next;
      /* One channel is not a mode. `mean` of one channel is that channel,
         and `stack` of one is a one-row stack -- the server calls it
         "single" either way, so the control is only offered when there is
         something to combine. */
      if (next.length > 1 && !p.tf_mode) p.tf_mode = 'stack';
      // Kept in step so anything reading the old single field still agrees.
      p.channel = next.length ? next[0] : undefined;
      render(); schedulePreview();
    };

    const list = el('select', {
      multiple: 'multiple', size: String(Math.min(8, Math.max(4, all.length))),
      class: 'tf-chans',
      onchange: (e) => commit(Array.from(e.target.selectedOptions)
        .map((o) => Number(o.value))),
    }, all.map((c) => el('option', {
      value: String(c.index),
      text: c.label + (c.bad ? '  (bad)' : ''),
      selected: chosen.indexOf(Number(c.index)) >= 0 ? 'selected' : null,
    })));

    const bits = [
      el('div', { class: 'section-label', style: 'margin-top:6px',
                  text: 'Channels for this panel' }),
      el('p', { class: 'hint',
        text: chosen.length > 1
          ? chosen.length + ' channels, combined by the mode below.'
          : (chosen.length === 1
              ? 'One channel. Pick more to average or stack them.'
              : 'None picked \u2014 the panel will use the first selected '
                + 'channel of the recording.') }),
      list,
    ];

    if (chosen.length > 1) {
      bits.push(field('How to combine them', el('select', {
        onchange: (e) => { p.tf_mode = e.target.value; schedulePreview(); },
      }, [
        el('option', { value: 'stack', text: 'Stack \u2014 a band per channel',
          selected: (p.tf_mode || 'stack') === 'stack' ? 'selected' : null }),
        el('option', { value: 'mean',
          text: 'Mean \u2014 one map, averaged',
          selected: p.tf_mode === 'mean' ? 'selected' : null }),
      ])));
    }

    /* And the way back to whatever the viewer has, which is what "emulate
       the spectrogram that is already open" means once you have edited the
       panel and want it back. */
    const from = tfPaneFor(p);
    if (from >= 0) {
      bits.push(el('button', {
        class: 'btn ghost sm', text: 'Match the viewer',
        title: 'Take the channels, the mode, the band and the display crop '
             + 'from the ' + (p.panel) + ' pane on screen',
        onclick: () => {
          Object.assign(p, tfFrom(from));
          render(); schedulePreview();
        },
      }));
    }
    return el('div', {}, bits);
  }

  /* A pane on screen showing the same kind of panel for the same recording,
     so "match the viewer" knows which one it means. */
  function tfPaneFor(p) {
    const panes = XF.panes || [];
    for (let i = 0; i < panes.length; i += 1) {
      const q = panes[i];
      if (!q) continue;
      if (q.panel !== p.panel) continue;
      if (p.session_id && q.sessionId !== p.session_id) continue;
      return i;
    }
    return -1;
  }

  function snap() {
    if (!layout) return null;
    const out = {};
    for (const k of Object.keys(layout)) {
      if (k === 'events') continue;
      out[k] = layout[k];
    }
    try { return JSON.stringify(out); } catch (e) { return null; }
  }

  /* Put a snapshot back, in place.

     Mutated rather than reassigned: `layout()` hands the live object out and
     the render closures hold it, so swapping it for a new one would leave
     half the builder editing an orphan. */
  function restore(json) {
    if (!json) return;
    let got;
    try { got = JSON.parse(json); } catch (e) { return; }
    const events = layout.events;
    for (const k of Object.keys(layout)) {
      if (k !== 'events') delete layout[k];
    }
    Object.assign(layout, got);
    if (events !== undefined) layout.events = events;
    if (selected >= (layout.panels || []).length) {
      selected = Math.max(0, (layout.panels || []).length - 1);
    }
  }

  /* Called from the redraw. Anything that changed the layout since the last
     look becomes a step. */
  function noteChange() {
    if (!layout) return;
    const now = snap();
    if (current === null) { current = now; return; }
    if (restoring || now === current) return;
    undoStack.push(current);
    if (undoStack.length > UNDO_MAX) undoStack.shift();
    // A fresh change abandons whatever was ahead, the way every editor does.
    redoStack = [];
    current = now;
  }

  function undo() {
    if (!undoStack.length) { toast('Nothing to undo.', null, 2000); return; }
    const back = undoStack.pop();
    redoStack.push(snap());
    restoring = true;
    try {
      restore(back);
      current = snap();
      render();
      schedulePreview();
    } finally { restoring = false; }
  }

  function redo() {
    if (!redoStack.length) { toast('Nothing to redo.', null, 2000); return; }
    const fwd = redoStack.pop();
    undoStack.push(snap());
    restoring = true;
    try {
      restore(fwd);
      current = snap();
      render();
      schedulePreview();
    } finally { restoring = false; }
  }

  /* Ctrl/Cmd+Z while the builder is up. Guarded by isTyping, because inside
     a text field Ctrl+Z means the text -- taking that over would make the
     title box impossible to correct. */
  function keys(e) {
    if (!layout) return;
    if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'z') return;
    if (isTyping(e)) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.shiftKey) redo(); else undo();
  }

  function wireKeys(on) {
    if (on === keysOn) return;
    keysOn = on;
    if (on) document.addEventListener('keydown', keys, true);
    else document.removeEventListener('keydown', keys, true);
  }

  /* Every way out of the builder. The close button and Close both used
     closeModal directly, which left the key handler attached to a dialog
     that was no longer on screen. */
  function shut() {
    wireKeys(false);
    undoStack = [];
    redoStack = [];
    current = null;
    closeModal();
  }

  // Floating-point accumulation makes t0+span print as 2.19999999999; the
  // extra digits are noise, not precision.
  function r6(v) { return Math.round(v * 1e6) / 1e6; }

  /* [1,2,3,7,9,10] -> "1-3, 7, 9-10", and an even run -> "2-29/3".

     A probe column is every third channel, so the run-of-consecutive form
     alone would print eleven numbers where three characters would do. */
  function ranges(nums) {
    const got = Array.from(new Set(nums.map(Number)))
      .filter((n) => Number.isFinite(n)).sort((a, b) => a - b);
    if (!got.length) return '';
    if (got.length > 2) {
      const step = got[1] - got[0];
      let even = step > 0;
      for (let i = 1; i < got.length; i += 1) {
        if (got[i] - got[i - 1] !== step) { even = false; break; }
      }
      if (even) {
        return step === 1 ? got[0] + '-' + got[got.length - 1]
                          : got[0] + '-' + got[got.length - 1] + '/' + step;
      }
    }
    const out = [];
    let run = [got[0]];
    for (const n of got.slice(1)) {
      if (n === run[run.length - 1] + 1) { run.push(n); continue; }
      out.push(run); run = [n];
    }
    out.push(run);
    return out.map((r) => (r.length > 1 ? r[0] + '-' + r[r.length - 1]
                                        : String(r[0]))).join(', ');
  }

  /* Which channels this panel draws, said as channel NUMBERS.

     A panel carries indices, because that is what the renderer takes, and a
     cell labelled "1" tells you nothing about which of six columns it is.
     This is the answer to "clearly indicate which window is which". */
  /* The time-frequency half of a pane's request, or nothing.

     Read from `BARRY.views.xplore.panelSpec`, which is what the pane asks
     the server for -- so the figure is made of the same fields, resolved the
     same way, including a band that is locked to the recording rather than
     set on the pane. */
  function tfFrom(index) {
    const view = BARRY.views.xplore;
    if (!view || !view.panelSpec) return {};
    let spec = null;
    try { spec = view.panelSpec(index); } catch (e) { spec = null; }
    if (!spec || !spec.tf_channels) return {};
    const out = {
      tf_channels: Array.from(spec.tf_channels),
      tf_mode: spec.tf_mode,
      fmin: spec.fmin, fmax: spec.fmax,
    };
    for (const k of ['fview_min', 'fview_max', 'stft_mode']) {
      if (spec[k] != null) out[k] = spec[k];
    }
    return out;
  }

  function chanNote(p) {
    if (!p) return '';
    if (p.probe_view) return 'whole probe';
    const sess = XF.sessions[p.session_id];
    const all = ((sess || {}).info || {}).channels || [];
    const idx = p.channels;
    if (!idx || !idx.length || !all.length) return '';
    if (idx.length >= all.length) return 'all ' + all.length + ' ch';
    const nums = idx.map((i) => (all[i] || {}).number)
      .filter((n) => n !== undefined);
    if (!nums.length) return '';
    return 'CSC ' + ranges(nums);
  }

  function gitUser() {
    const sys = (BARRY.state.catalog && BARRY.state.catalog.system) || {};
    return sys.user || '';
  }

  function labelFor(id) {
    const d = panelDefs.find((p) => p.id === id);
    return d ? d.name : id;
  }

  /* ==================================================================
     Render the builder
     ================================================================== */
  function render() {
    noteChange();
    const box = el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Figure builder' }),
        el('span', { class: 'sub', text: layout.panels.length + ' panel(s) · '
                     + layout.rows + '×' + layout.cols }),
        el('div', { class: 'spacer' }),
        el('button', {
          class: 'btn ghost sm', text: '\u21b6 Undo',
          title: undoStack.length
            ? 'Undo the last change (Ctrl+Z) \u2014 ' + undoStack.length
              + ' step(s) back'
            : 'Nothing to undo yet',
          disabled: undoStack.length ? null : 'disabled',
          onclick: undo,
        }),
        el('button', {
          class: 'btn ghost sm', text: '\u21b7',
          title: redoStack.length
            ? 'Redo (Ctrl+Shift+Z) \u2014 ' + redoStack.length + ' step(s)'
            : 'Nothing to redo',
          disabled: redoStack.length ? null : 'disabled',
          onclick: redo,
        }),
        el('button', { class: 'close-x', html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
                       title: 'Close the builder',
                       onclick: shut }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'fig-layout' }, [
          leftColumn(), centerColumn(), rightColumn(),
        ]),
      ]),
      el('div', { class: 'mf' }, [
        el('span', { class: 'note', id: 'figNote',
                     style: 'font-size:11.5px;color:var(--text-3)' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost sm', text: 'Save layout',
                       onclick: saveLayout }),
        el('button', { class: 'btn ghost', text: 'Close', onclick: shut }),
        el('button', { class: 'btn ghost', text: 'SVG', onclick: () => download('svg') }),
        el('button', { class: 'btn ghost', text: 'PDF', onclick: () => download('pdf') }),
        el('button', { class: 'btn', text: 'PNG', onclick: () => download('png') }),
      ]),
    ]);
    /* Replacing, not stacking. This is the same dialog redrawn -- and it is
       redrawn on every panel change and every grid click, so stacking put a
       copy of the builder behind it each time and the close button became a
       back button that needed one press per change. */
    showModal(box, { replace: true });
    wireKeys(true);
  }

  /* ---------- left: page + panels ---------- */
  function leftColumn() {
    const col = el('div', { class: 'fig-col' });

    col.appendChild(el('div', { class: 'section-label', style: 'margin-top:0', text: 'Page' }));
    col.appendChild(field('Preset', el('select', {
      onchange: (e) => {
        const p = pages.find((x) => x.id === e.target.value);
        layout.page = e.target.value;
        if (p) { layout.width_in = p.w; layout.height_in = p.h; }
        render(); schedulePreview();
      },
    }, pages.map((p) => el('option', {
      value: p.id, text: p.id.replace(/_/g, ' ') + '  (' + p.w + '×' + p.h + '")',
      selected: layout.page === p.id ? 'selected' : null,
    })))));

    /* Read, not typed. The page size follows the preset above -- a second
       way to set it is a second thing that can disagree with it -- and the
       rows and columns are a shape, changed in the grid itself where you
       can see what you are doing. */
    col.appendChild(el('div', { style: 'display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px' }, [
      readout('Width in', layout.width_in + '"'),
      readout('Height in', layout.height_in + '"'),
      field('DPI', num(layout.dpi, 50, (v) => { layout.dpi = v; })),
    ]));

    col.appendChild(el('div', { style: 'display:grid;grid-template-columns:1fr 1fr;gap:8px' }, [
      readout('Rows', String(layout.rows), 'Added in the grid below'),
      readout('Cols', String(layout.cols), 'Added in the grid below'),
    ]));

    col.appendChild(el('div', { style: 'display:grid;grid-template-columns:1fr 1fr;gap:8px' }, [
      field('Row gap', num(layout.hspace != null ? layout.hspace : 0.45, 0.05, (v) => {
        layout.hspace = v; schedulePreview();
      })),
      field('Col gap', num(layout.wspace != null ? layout.wspace : 0.34, 0.05, (v) => {
        layout.wspace = v; schedulePreview();
      })),
    ]));

    /* The grid, built by hand.

       `+` on an edge adds a row or a column; `x` on one removes it. A panel
       is dragged out of the palette below into the cell it should occupy,
       and dragging a filled cell moves that panel. Nothing here is typed. */
    col.appendChild(el('div', { class: 'section-label', text: 'Grid' }));
    col.appendChild(el('div', { class: 'grid-help',
      text: 'Drag a panel from below into a cell, or drag a filled cell to '
          + 'move it. Drag a panel\u2019s edge or corner to make it span more '
          + 'cells. Drag it onto the bin to take it out. + on an edge adds a '
          + 'row or a column.' }));

    const wrap = el('div', { class: 'grid-wrap' });

    /* Column headers: one per column, each able to remove itself. Their
       widths track the grid's own columns so an `x` stays over the column
       it removes -- no extra track, because the `+` is no longer up here. */
    const heads = el('div', {
      class: 'grid-heads',
      style: 'grid-template-columns:repeat(' + layout.cols + ',1fr)',
    });
    for (let c = 0; c < layout.cols; c++) {
      const cc = c;
      heads.appendChild(el('div', { class: 'grid-head' }, [
        el('span', { class: 'gh-n', text: 'c' + cc }),
        layout.cols > 1 ? el('button', {
          class: 'gh-x', text: '\u00d7',
          title: 'Remove column ' + cc
               + (colPanels(cc).length
                   ? ' \u2014 ' + colPanels(cc).length + ' panel(s) in it go'
                   : ''),
          onclick: (e) => { e.stopPropagation(); removeCol(cc); },
        }) : null,
      ].filter(Boolean)));
    }
    wrap.appendChild(heads);

    const map = el('div', {
      class: 'grid-map',
      style: 'grid-template-columns:repeat(' + layout.cols + ',1fr)',
    });

    const cells = [];

    const paint = (from, to) => {
      const r0 = Math.min(from[0], to[0]), r1 = Math.max(from[0], to[0]);
      const c0 = Math.min(from[1], to[1]), c1 = Math.max(from[1], to[1]);
      for (const cell of cells) {
        const inside = cell.r >= r0 && cell.r <= r1 && cell.c >= c0 && cell.c <= c1;
        cell.node.classList.toggle('span-preview', inside);
      }
    };
    const clearPaint = () =>
      cells.forEach((x) => x.node.classList.remove('span-preview'));

    const applySpan = (from, to) => {
      const p = layout.panels[selected];
      if (!p) return;
      p.row = Math.min(from[0], to[0]);
      p.col = Math.min(from[1], to[1]);
      p.rowspan = Math.abs(to[0] - from[0]) + 1;
      p.colspan = Math.abs(to[1] - from[1]) + 1;
      clampPanel(p);
      render(); schedulePreview();
    };

    for (let r = 0; r < layout.rows; r++) {
      for (let c = 0; c < layout.cols; c++) {
        const rr = r, cc = c;
        const occupant = layout.panels.findIndex(
          (p) => rr >= p.row && rr < p.row + p.rowspan
              && cc >= p.col && cc < p.col + p.colspan);
        const node = el('div', {
          class: 'grid-cell' + (occupant >= 0 ? ' filled' : '')
               + (occupant === selected ? ' sel' : ''),
          draggable: occupant >= 0 ? 'true' : null,
          title: occupant >= 0
            ? (layout.panels[occupant].title
               || labelFor(layout.panels[occupant].panel))
              + '  \u2014 drag to move it'
            : 'Empty \u2014 drop a panel here',
          /* Moving a panel: the cell itself is the handle. */
          ondragstart: (e) => {
            if (occupant < 0) return;
            selected = occupant;
            e.dataTransfer.setData('text/plain', 'move:' + occupant);
            e.dataTransfer.effectAllowed = 'move';
          },
          ondragover: (e) => {
            e.preventDefault();
            node.classList.add('drop-over');
          },
          ondragleave: () => node.classList.remove('drop-over'),
          ondrop: (e) => {
            e.preventDefault();
            node.classList.remove('drop-over');
            const got = (e.dataTransfer.getData('text/plain') || '');
            if (got.startsWith('move:')) {
              const at = +got.slice(5);
              const p = layout.panels[at];
              if (!p) return;
              p.row = rr; p.col = cc;
              clampPanel(p);
              selected = at;
              render(); schedulePreview();
            } else if (got.startsWith('add:')) {
              addPanel(got.slice(4), rr, cc);
            }
          },
          /* Spanning stays on shift-click: it is the only way to make a
             panel wider than a cell, and it is not "adding" anything.
             Holding shift shows what it would take, so the gesture is
             discoverable rather than something you have to be told. */
          onmouseenter: (e) => {
            const p = layout.panels[selected];
            if (!e.shiftKey || !p) return;
            paint([p.row, p.col], [rr, cc]);
          },
          onmouseleave: () => clearPaint(),
          onmousedown: (e) => {
            if (!e.shiftKey || !layout.panels[selected]) return;
            e.preventDefault();
            clearPaint();
            const p = layout.panels[selected];
            applySpan([p.row, p.col], [rr, cc]);
          },
          onclick: () => {
            if (occupant >= 0 && occupant !== selected) {
              selected = occupant; render();
            }
          },
        }, [
          el('span', { class: 'gc-n',
            text: occupant >= 0 ? String(occupant + 1) : '' }),
          /* Which panel this is, in the terms that distinguish it from its
             neighbours: the channels it draws. An index distinguishes
             nothing when all six panels are one probe. */
          occupant >= 0 && chanNote(layout.panels[occupant])
            ? el('span', { class: 'gc-ch',
                text: chanNote(layout.panels[occupant]) })
            : null,
        ].filter(Boolean));
        node.dataset.r = String(rr);
        node.dataset.c = String(cc);
        /* Handles on the panel's own outside edges, so "hover on the edge
           and drag" reaches for something that is there. Only on the cell
           at the panel's bottom-right extent: a handle in the middle of a
           spanned panel would be resizing from nowhere. */
        if (occupant >= 0) {
          const pn = layout.panels[occupant];
          const atRight = cc === pn.col + pn.colspan - 1;
          const atFoot = rr === pn.row + pn.rowspan - 1;
          if (atRight) node.appendChild(grip(occupant, 'e'));
          if (atFoot) node.appendChild(grip(occupant, 's'));
          if (atRight && atFoot) node.appendChild(grip(occupant, 'se'));
        }
        cells.push({ r: rr, c: cc, node });
        map.appendChild(node);
      }
    }

    /* Dragging an edge.

       The pointer is tracked against whatever cell is under it rather than
       against a delta in pixels, because the thing being chosen is a cell
       and a pixel count would have to be converted back into one anyway --
       badly, at the edges. */
    function grip(which, side) {
      return el('div', {
        class: 'gc-grip ' + side,
        title: side === 's' ? 'Drag down to span more rows'
          : (side === 'e' ? 'Drag across to span more columns'
                          : 'Drag to span rows and columns'),
        onpointerdown: (e) => {
          e.preventDefault();
          e.stopPropagation();
          const p = layout.panels[which];
          if (!p) return;
          selected = which;
          const from = [p.row, p.col];
          let to = [p.row + p.rowspan - 1, p.col + p.colspan - 1];
          const at = (ev) => {
            const el2 = document.elementFromPoint(ev.clientX, ev.clientY);
            const cell = el2 && el2.closest && el2.closest('.grid-cell');
            if (cell && cell.dataset.r !== undefined) {
              return [+cell.dataset.r, +cell.dataset.c];
            }
            /* Nothing under the pointer, so the nearest cell instead.

               Measured: dragging the bottom edge of a panel did nothing at
               all, because the row below was scrolled past the bottom of
               the dialog and the point resolved to the backdrop. Giving up
               is the wrong answer -- a drag heading down is heading for the
               row below whether or not it is on screen -- and this also
               covers the gaps between cells and a drag that strays out of
               the grid entirely. */
            let best = null;
            let near = Infinity;
            for (const c of cells) {
              const b = c.node.getBoundingClientRect();
              const dx = Math.max(b.left - ev.clientX, 0,
                                  ev.clientX - b.right);
              const dy = Math.max(b.top - ev.clientY, 0,
                                  ev.clientY - b.bottom);
              const d = dx * dx + dy * dy;
              if (d < near) { near = d; best = [c.r, c.c]; }
            }
            return best;
          };
          const move = (ev) => {
            const got = at(ev);
            if (!got) return;
            /* An edge handle moves one axis. Dragging the bottom edge
               sideways should not silently widen the panel too. */
            to = [side === 'e' ? to[0] : Math.max(from[0], got[0]),
                  side === 's' ? to[1] : Math.max(from[1], got[1])];
            paint(from, to);
          };
          const up = (ev) => {
            window.removeEventListener('pointermove', move);
            window.removeEventListener('pointerup', up);
            clearPaint();
            move(ev);
            clearPaint();
            applySpan(from, to);
          };
          window.addEventListener('pointermove', move);
          window.addEventListener('pointerup', up);
        },
      });
    }

    // Leaving the grid clears any span preview the shift key was showing.
    map.addEventListener('mouseleave', clearPaint);

    wrap.appendChild(map);

    /* Row handles down the right, so an `x` sits beside the row it takes. */
    const rowsCol = el('div', {
      class: 'grid-rows',
      style: 'grid-template-rows:repeat(' + layout.rows + ',1fr)',
    });
    for (let r = 0; r < layout.rows; r++) {
      const rr = r;
      rowsCol.appendChild(el('div', { class: 'grid-rowh' }, [
        layout.rows > 1 ? el('button', {
          class: 'gh-x', text: '\u00d7',
          title: 'Remove row ' + rr
               + (rowPanels(rr).length
                   ? ' \u2014 ' + rowPanels(rr).length + ' panel(s) in it go'
                   : ''),
          onclick: (e) => { e.stopPropagation(); removeRow(rr); },
        }) : null,
      ].filter(Boolean)));
    }
    wrap.appendChild(rowsCol);

    /* Add a column: on the right edge, the full height of the cells, so it
       reads as "another one goes here". It used to sit in the header row,
       which put it above the row handles -- floating in the top corner,
       beside nothing, pointing at nothing. */
    wrap.appendChild(el('button', {
      class: 'grid-add col',
      text: '+', title: 'Add a column',
      disabled: layout.cols >= 4 ? 'disabled' : null,
      onclick: () => {
        layout.cols = Math.min(4, layout.cols + 1);
        render(); schedulePreview();
      },
    }));

    wrap.appendChild(el('button', {
      class: 'grid-add row',
      text: '+', title: 'Add a row',
      disabled: layout.rows >= 6 ? 'disabled' : null,
      onclick: () => {
        layout.rows = Math.min(6, layout.rows + 1);
        render(); schedulePreview();
      },
    }));

    col.appendChild(wrap);

    /* Somewhere to drag a panel you are finished with.

       Removal was an x in the list below, which is fine and stays -- but
       moving, adding and spanning are all drags, and a gesture that works
       for three of the four things you do to a panel should work for the
       fourth. */
    col.appendChild(el('div', {
      class: 'grid-bin',
      text: 'Drag a panel here to take it out',
      ondragover: (e) => {
        if (!(e.dataTransfer.types || []).length) return;
        e.preventDefault();
        e.currentTarget.classList.add('over');
      },
      ondragleave: (e) => e.currentTarget.classList.remove('over'),
      ondrop: (e) => {
        e.preventDefault();
        e.currentTarget.classList.remove('over');
        const got = e.dataTransfer.getData('text/plain') || '';
        if (!got.startsWith('move:')) return;
        const at = +got.slice(5);
        if (!layout.panels[at]) return;
        const gone = layout.panels[at].title
          || labelFor(layout.panels[at].panel);
        layout.panels.splice(at, 1);
        if (selected >= layout.panels.length) {
          selected = Math.max(0, layout.panels.length - 1);
        }
        render(); schedulePreview();
        toast('Took out ' + gone + '. Undo puts it back.', null, 4000);
      },
    }));

    /* panel list */
    col.appendChild(el('div', { class: 'section-label', text: 'Panels' }));
    layout.panels.forEach((p, i) => {
      col.appendChild(el('div', {
        class: 'panel-item' + (i === selected ? ' sel' : ''),
        onclick: () => { selected = i; render(); },
      }, [
        el('div', { class: 'pi-top' }, [
          el('span', { class: 'pi-name',
            text: (i + 1) + '. ' + (p.title || labelFor(p.panel))
              + (chanNote(p) ? '  \u00b7  ' + chanNote(p) : '') }),
          el('span', { class: 'pi-pos', text: 'r' + p.row + 'c' + p.col
                       + (p.rowspan > 1 || p.colspan > 1 ? ' ' + p.rowspan + '×' + p.colspan : '') }),
          el('button', {
            class: 'badbtn', text: '×', title: 'Remove this panel',
            onclick: (e) => {
              e.stopPropagation();
              layout.panels.splice(i, 1);
              selected = Math.max(0, selected - 1);
              render(); schedulePreview();
            },
          }),
        ]),
        el('div', { class: 'pi-sub', text: labelFor(p.panel)
                    + (p.session_id && p.session_id !== sess.id
                       ? ' · ' + ((XF.sessions[p.session_id] || {}).identity || {}).label : '') }),
      ]));
    });

    /* The palette. Dragged into a cell rather than chosen from a list: a
       dropdown put the panel in the first free cell, so you found out where
       it had gone afterwards and moved it. */
    col.appendChild(el('div', { class: 'section-label', text: 'Drag one in' }));
    col.appendChild(el('div', { class: 'fig-palette' },
      panelDefs.map((d) => el('div', {
        class: 'fig-chip', draggable: 'true', title: d.name
          + ' \u2014 drag it into a cell above',
        text: d.name,
        ondragstart: (e) => {
          e.dataTransfer.setData('text/plain', 'add:' + d.id);
          e.dataTransfer.effectAllowed = 'copy';
        },
      }))));

    return col;
  }

  function addPanel(kind, row, col) {
    // Where it was dropped, if it was dropped. `firstFreeCell` is only the
    // fallback now -- a panel that lands somewhere you did not point at is
    // the thing dragging it was meant to fix.
    const spot = (row != null && col != null)
      ? [row, col] : firstFreeCell();
    const p = {
      panel: kind, session_id: sess.id, title: labelFor(kind),
      row: spot[0], col: spot[1], rowspan: 1, colspan: 1, cmap: 'jet',
    };
    if (kind === 'spectrogram' || kind === 'scalogram') {
      p.channel = sess.sel.size ? Math.min(...sess.sel) : 0;
      p.fmin = 20; p.fmax = 1000;
    }
    layout.panels.push(p);
    selected = layout.panels.length - 1;
    render(); schedulePreview();
  }

  function firstFreeCell() {
    for (let r = 0; r < layout.rows; r++) {
      for (let c = 0; c < layout.cols; c++) {
        const taken = layout.panels.some(
          (p) => r >= p.row && r < p.row + p.rowspan && c >= p.col && c < p.col + p.colspan);
        if (!taken) return [r, c];
      }
    }
    layout.rows = Math.min(6, layout.rows + 1);
    return [layout.rows - 1, 0];
  }

  /* Which panels a row or a column actually holds, so the `x` can say what
     removing it costs before it is clicked. */
  function colPanels(c) {
    return layout.panels.filter((p) => c >= p.col && c < p.col + p.colspan);
  }

  function rowPanels(r) {
    return layout.panels.filter((p) => r >= p.row && r < p.row + p.rowspan);
  }

  /* Removing a column is not decrementing a number.

     A panel sitting only in it has nowhere to go and is removed. A panel
     spanning it loses a column of span. Everything to its right shifts
     left. Skipping any of those quietly relocates somebody's figure, which
     is worse than refusing. */
  function removeCol(c) {
    const keep = [];
    for (const p of layout.panels) {
      const inside = c >= p.col && c < p.col + p.colspan;
      if (inside && p.colspan === 1) continue;          // it was only there
      if (inside) p.colspan -= 1;                        // it spanned it
      if (p.col > c) p.col -= 1;                         // it was to the right
      keep.push(p);
    }
    layout.panels = keep;
    layout.cols = Math.max(1, layout.cols - 1);
    if (selected >= layout.panels.length) {
      selected = Math.max(0, layout.panels.length - 1);
    }
    layout.panels.forEach(clampPanel);
    render(); schedulePreview();
  }

  function removeRow(r) {
    const keep = [];
    for (const p of layout.panels) {
      const inside = r >= p.row && r < p.row + p.rowspan;
      if (inside && p.rowspan === 1) continue;
      if (inside) p.rowspan -= 1;
      if (p.row > r) p.row -= 1;
      keep.push(p);
    }
    layout.panels = keep;
    layout.rows = Math.max(1, layout.rows - 1);
    if (selected >= layout.panels.length) {
      selected = Math.max(0, layout.panels.length - 1);
    }
    layout.panels.forEach(clampPanel);
    render(); schedulePreview();
  }

  function clampPanel(p) {
    p.row = Math.max(0, Math.min(p.row, layout.rows - 1));
    p.col = Math.max(0, Math.min(p.col, layout.cols - 1));
    p.rowspan = Math.max(1, Math.min(p.rowspan, layout.rows - p.row));
    p.colspan = Math.max(1, Math.min(p.colspan, layout.cols - p.col));
  }

  /* ---------- center: live preview ---------- */
  function centerColumn() {
    const col = el('div', { class: 'fig-col' });
    col.appendChild(el('div', { class: 'section-label', style: 'margin-top:0', text: 'Preview' }));
    const box = el('div', { class: 'fig-preview', id: 'figPreview' }, [
      el('div', { style: 'display:flex;align-items:center;gap:10px;color:var(--text-3)' }, [
        el('span', { class: 'spin' }), el('span', { text: 'Rendering…' }),
      ]),
    ]);
    col.appendChild(box);
    col.appendChild(el('div', { class: 'fb-stats', id: 'figProblems' }));
    return col;
  }

  /* ---------- right: selected panel + metadata ---------- */
  function rightColumn() {
    const col = el('div', { class: 'fig-col' });
    const p = layout.panels[selected];

    col.appendChild(el('div', { class: 'section-label', style: 'margin-top:0', text: 'Titles' }));
    col.appendChild(field('Figure title', text(layout.title, (v) => {
      layout.title = v; schedulePreview();
    })));
    col.appendChild(field('Subtitle', text(layout.subtitle, (v) => {
      layout.subtitle = v; schedulePreview();
    })));

    col.appendChild(el('div', { class: 'section-label', text: 'Time window' }));
    col.appendChild(el('div', { style: 'display:grid;grid-template-columns:1fr 1fr;gap:8px' }, [
      field('t0 (s)', num(layout.t0, 0.05, (v) => { layout.t0 = v; schedulePreview(); })),
      field('t1 (s)', num(layout.t1, 0.05, (v) => { layout.t1 = v; schedulePreview(); })),
    ]));
    col.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Use current view',
      onclick: () => {
        layout.t0 = r6(sess.t0); layout.t1 = r6(sess.t0 + sess.span);
        layout.highpass = sess.hp; layout.lowpass = sess.lp; layout.notch = sess.notch;
        layout.channels = Array.from(sess.sel).sort((a, b) => a - b);
        layout.bad_channels = Array.from(sess.bad);
        layout.events = sess.events;
        render(); schedulePreview();
      },
    }));

    if (p) {
      col.appendChild(el('div', { class: 'section-label',
                                  text: 'Panel ' + (selected + 1) + ' — ' + labelFor(p.panel) }));
      col.appendChild(field('Panel title', text(p.title, (v) => {
        p.title = v; schedulePreview();
      })));
      col.appendChild(el('div', { style: 'display:grid;grid-template-columns:1fr 1fr;gap:8px' }, [
        field('Row span', num(p.rowspan || 1, 1, (v) => {
          p.rowspan = Math.max(1, v || 1); clampPanel(p); render(); schedulePreview();
        })),
        field('Col span', num(p.colspan || 1, 1, (v) => {
          p.colspan = Math.max(1, v || 1); clampPanel(p); render(); schedulePreview();
        })),
      ]));
      col.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Reset span to 1x1',
        onclick: () => {
          p.rowspan = 1; p.colspan = 1;
          render(); schedulePreview();
        },
      }));

      if (p.probe_view) col.appendChild(probeColumns(p));

      if (XF.order.length > 1) {
        col.appendChild(field('Session', el('select', {
          onchange: (e) => { p.session_id = e.target.value; schedulePreview(); },
        }, XF.order.map((id) => el('option', {
          value: id, text: XF.sessions[id].identity.label || XF.sessions[id].info.name,
          selected: (p.session_id || sess.id) === id ? 'selected' : null,
        })))));
      }

      if (p.panel === 'spectrogram' || p.panel === 'scalogram') {
        const s2 = XF.sessions[p.session_id] || sess;
        col.appendChild(tfChannels(p, s2));
        col.appendChild(el('div', { style: 'display:grid;grid-template-columns:1fr 1fr;gap:8px' }, [
          field('f min', num(p.fmin != null ? p.fmin : 20, 5, (v) => { p.fmin = v; schedulePreview(); })),
          field('f max', num(p.fmax != null ? p.fmax : 1000, 50, (v) => { p.fmax = v; schedulePreview(); })),
        ]));
      }

      if (p.panel !== 'traces') {
        col.appendChild(el('div', { class: 'section-label', text: 'Colormap' }));
        col.appendChild(cmapPicker(p.cmap || 'jet', (id) => {
          p.cmap = id; render(); schedulePreview();
        }));
      } else {
        col.appendChild(field('Gain', num(layout.gain || 1, 0.25, (v) => {
          layout.gain = v; schedulePreview();
        })));
      }
    }

    col.appendChild(el('div', { class: 'section-label', text: 'Metadata block' }));
    col.appendChild(el('label', { class: 'toggle' + (layout.show_metadata ? ' on' : '') }, [
      el('input', {
        type: 'checkbox', checked: layout.show_metadata ? 'checked' : null,
        onchange: (e) => { layout.show_metadata = e.target.checked; render(); schedulePreview(); },
      }),
      el('span', { text: 'Show provenance footer' }),
    ]));
    if (layout.show_metadata) {
      const m = layout.metadata;
      col.appendChild(field('Generated by', text(m.author, (v) => { m.author = v; schedulePreview(); })));
      col.appendChild(field('Date', text(m.date, (v) => { m.date = v; schedulePreview(); })));
      col.appendChild(field('Device', text(m.machine, (v) => { m.machine = v; schedulePreview(); })));
      // A textarea, not a single-line input: a rebuild writes several lines
      // of provenance in here, and they were invisible in a one-line field.
      col.appendChild(field('Notes', el('textarea', {
        rows: '4', value: m.notes || '', style: 'resize:vertical',
        oninput: debounceInput((e) => {
          m.notes = e.target.value; schedulePreview();
        }, 400),
      })));
      col.appendChild(el('div', { class: 'field' }, [
        el('label', { text: 'Source' }),
        el('span', { class: 'hint', style: 'word-break:break-all', text: m.source_path }),
      ]));
    }
    return col;
  }

  function cmapPicker(current, onpick) {
    const row = el('div', { class: 'cmap-row' });
    for (const c of colormaps) {
      const grad = 'linear-gradient(to right,' + (c.swatch || ['#888']).join(',') + ')';
      row.appendChild(el('button', {
        class: 'cmap-btn' + (c.id === current ? ' active' : ''),
        title: c.name + (c.note ? ' — ' + c.note : ''),
        onclick: () => onpick(c.id),
      }, [
        el('span', { class: 'grad', style: 'background:' + grad }),
        el('span', { class: 'nm', text: c.name }),
      ]));
    }
    return row;
  }

  /* ---------- small field helpers ---------- */
  /* A number the builder decides, shown so it can be checked and not typed
     into. It reads as a field so the column does not go lumpy, but it is
     text: an input somebody cannot change is worse than a value, because it
     looks like it should work. */
  function readout(label, value, hint) {
    return el('div', { class: 'field' }, [
      el('label', { text: label }),
      el('div', { class: 'fig-readout', text: value }),
      hint ? el('span', { class: 'hint', text: hint }) : null,
    ].filter(Boolean));
  }

  function field(label, control, hint) {
    return el('div', { class: 'field' }, [
      el('label', { text: label }), control,
      hint ? el('span', { class: 'hint', text: hint }) : null,
    ]);
  }
  function num(value, step, onchange) {
    return el('input', {
      type: 'number', step: String(step), value: String(value ?? ''),
      onchange: (e) => onchange(parseFloat(e.target.value)),
    });
  }
  function text(value, onchange) {
    return el('input', {
      type: 'text', value: value || '',
      oninput: debounceInput((e) => onchange(e.target.value), 400),
    });
  }
  /* ==================================================================
     Preview + export
     ================================================================== */
  let previewTimer = null;
  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(doPreview, 350);
  }

  function sessionMap() {
    const out = {};
    const ids = new Set(layout.panels.map((p) => p.session_id || sess.id));
    ids.add(sess.id);
    for (const id of ids) {
      const s = XF.sessions[id];
      if (s) out[id] = { path: s.path, even_only: s.evenOnly, invert: s.invert };
    }
    out.default = { path: sess.path, even_only: sess.evenOnly, invert: sess.invert };
    return out;
  }

  async function doPreview() {
    if (rendering) { pendingRender = true; return; }
    rendering = true;
    const host = $('#figPreview');
    if (host) host.style.opacity = '0.55';
    try {
      const res = await apiPost('/api/figure/preview', {
        layout, sessions: sessionMap(), dpi: 110,
      });
      const box = $('#figPreview');
      if (box) {
        box.innerHTML = '';
        box.appendChild(el('img', { src: res.image, alt: 'figure preview' }));
        box.style.opacity = '1';
      }
      const pr = $('#figProblems');
      if (pr) {
        pr.innerHTML = '';
        (res.problems || []).forEach((p) => pr.appendChild(
          el('span', { class: 'stat-chip warn', style: 'white-space:normal', text: p })));
      }
    } catch (e) {
      const box = $('#figPreview');
      if (box) {
        box.innerHTML = '';
        box.style.opacity = '1';
        box.appendChild(el('div', { class: 'wiz-verdict low',
                                    style: 'max-width:520px', text: e.message }));
      }
    } finally {
      rendering = false;
      if (pendingRender) { pendingRender = false; schedulePreview(); }
    }
  }

  async function download(fmt) {
    const note = $('#figNote');
    if (note) note.textContent = 'Rendering ' + fmt.toUpperCase() + '…';
    try {
      const res = await fetch('/api/figure/export', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ layout, sessions: sessionMap(), format: fmt,
                               dpi: layout.dpi || 300 }),
      });
      if (!res.ok) {
        let msg = 'Export failed (' + res.status + ')';
        try { msg = (await res.json()).error || msg; } catch (e) { /* binary */ }
        throw new Error(msg);
      }
      const runId = res.headers.get('X-Barry-Run-Id');
      const problems = res.headers.get('X-Barry-Problems');
      const outRel = res.headers.get('X-Barry-Output');
      const outGit = res.headers.get('X-Barry-Github');
      const blob = await res.blob();
      const name = safeName(layout.title || 'figure') + '.' + fmt;
      const url = URL.createObjectURL(blob);
      const a = el('a', { href: url, download: name });
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);

      if (note) {
        note.textContent = 'Saved ' + name
          + (outRel ? '  ·  Results/' + outRel : '')
          + (runId ? '  ·  logged as ' + runId : '');
      }
      toast('Saved ' + name + (outRel ? ' to Results/' : ''), 'ok', 5000);
      BARRY.activity.log('figure.export', {
        format: fmt, name, run_id: runId, output: outRel, github: outGit,
        panels: layout.panels.map((x) => x.panel),
        t0: layout.t0, t1: layout.t1, page: layout.page,
        dpi: layout.dpi, cmap: layout.cmap,
      }, { identity: layout.identity || {} });
      if (problems) toast(problems, 'err', 8000);
      BARRY.refreshSync();
    } catch (e) {
      if (note) note.textContent = '';
      toast(e.message, 'err', 8000);
    }
  }

  function safeName(t) {
    return (String(t).replace(/[^\w \-.]+/g, '_').trim() || 'figure').slice(0, 80);
  }

  async function saveLayout() {
    const name = await askPath('Name this layout', 'e.g. "IED triptych"');
    if (!name) return;
    // Strip the events before cloning, not after: the clone is what would
    // choke on them, so deleting afterwards was too late to help.
    const body = JSON.parse(JSON.stringify(
      Object.assign({}, layout, { events: undefined })));
    delete body.events;          // events belong to a session, not a layout
    body.name = name;
    try {
      await apiPost('/api/presets/layouts', { preset: body });
      toast('Saved layout "' + name + '" to GUI_logs', 'ok');
      BARRY.refreshSync();
    } catch (e) { toast(e.message, 'err'); }
  }

  /* Reopen the builder on a recipe read back off a run record.

     The builder normally seeds itself from whatever is on screen. A rebuild
     is the opposite case: the layout is known and the screen has just been
     arranged to match it, so the recorded values win. Anything the record
     could not supply falls back to the freshly-seeded layout rather than to a
     hard-coded default, which is why buildInitialLayout still runs first. */
  async function reopen(xfState, session, recipe, plan) {
    XF = xfState;
    sess = session;

    if (!panelDefs.length) {
      try {
        const d = await api('/api/panels');
        panelDefs = d.panels || [];
        colormaps = d.colormaps || [];
        pages = d.pages || [];
      } catch (e) { /* fall back to defaults */ }
    }

    const seeded = buildInitialLayout();
    layout = Object.assign({}, seeded);

    // Only keys the record actually carried are taken from it: a recipe from
    // an older export has nulls where it never wrote anything down, and a
    // null page size is worse than the seeded one.
    for (const k of ['title', 'subtitle', 'page', 'width_in', 'height_in',
                     'dpi', 'rows', 'cols', 't0', 't1', 'highpass', 'lowpass',
                     'notch', 'cmap', 'spacing_um', 'channels',
                     'bad_channels', 'gain', 'show_metadata']) {
      if (recipe[k] !== undefined && recipe[k] !== null) layout[k] = recipe[k];
    }

    // Panels are re-pointed at the session that was just opened; the ids on
    // the record belong to a session that no longer exists.
    if ((recipe.panels || []).length) {
      layout.panels = recipe.panels.map((pn) => Object.assign({}, pn, {
        session_id: sess.id,
        title: pn.title || labelFor(pn.panel || 'traces'),
        rowspan: pn.rowspan || 1, colspan: pn.colspan || 1,
        row: pn.row || 0, col: pn.col || 0,
      }));
      layout.rows = Math.max(
        recipe.rows || 1,
        ...layout.panels.map((pn) => pn.row + pn.rowspan));
    }

    // Events come from the session, which the rebuild has already loaded.
    layout.events = sess.events;

    // The metadata block records who made the figure now, not who made the
    // original -- this is a new export. What it was rebuilt from goes in the
    // notes, where it is part of the figure rather than buried in a log.
    const run = (plan || {}).run || {};
    layout.metadata = Object.assign({}, seeded.metadata, {
      notes: [
        'Rebuilt from ' + (run.label || 'an earlier figure')
          + (run.provenance ? ' of ' + run.provenance.at : '')
          + (run.id ? ' (run ' + run.id + ')' : ''),
        (plan || {}).complete === false
          ? 'The original record predates full recipes, so the channel '
            + 'selection and gain come from this session rather than from '
            + 'the original.'
          : null,
        ((plan || {}).problems || []).length
          ? 'Differences: ' + plan.problems.join(' ')
          : null,
      ].filter(Boolean).join('\n'),
    });

    selected = 0;
    render();
    schedulePreview();

    const n = ((plan || {}).problems || []).length;
    toast(n ? 'Figure rebuilt with ' + n + ' difference'
              + (n === 1 ? '' : 's') + ' — see the notes field.'
            : 'Figure rebuilt exactly. Preview is rendering.',
          n ? null : 'ok', 7000);
  }

  /* `layout` so the layout can be checked from outside without
     reimplementing the seeding rules -- web/_dev/figgrid.html reads it to
     confirm the builder opened on what was actually on screen. Returned as
     the live object rather than a copy: a harness that reads a snapshot
     cannot tell whether a drop changed anything. */
  /* `redraw` because a layout can be changed from outside -- a harness
     setting up a known grid, a recipe applied after the dialog is already
     open -- and nothing was rendering it. `layout()` handed out the live
     object, so it was possible to change the figure and see the old one. */
  return { open, reopen, layout: () => layout,
           redraw: () => { render(); schedulePreview(); } };
})();
