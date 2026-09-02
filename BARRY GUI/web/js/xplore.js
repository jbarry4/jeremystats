/* ==========================================================================
   xplore.js -- Xplorefinder 2.0

   Several sessions open at once (tabs), shown through 1, 2 or 4 panes.

   View state lives on the SESSION, not the pane, so two panes onto the same
   recording -- traces above, CSD below -- share one time window for free.
   "Link time" extends that sharing across different sessions, which is what
   you want when comparing baseline against CNO.

   A pane renders one of: stacked traces (canvas, vector), an analysis raster
   (server-rendered image), the session video, or position tracking.
   ========================================================================== */
'use strict';

BARRY.views.xplore = (function () {

  const XF = {
    sessions: {},        // id -> session state
    order: [],           // tab order
    active: null,
    panes: [],           // [{sessionId, panel, channel, cmap, ...}]
    nPanes: 1,
    // What is put away. Kept on the workspace rather than per pane: hiding
    // the channel column on one pane and not the other looks like a bug.
    chrome: { channels: true, strip: true, heads: true, tabs: true },
    // Pane sizes, as fractions of the grid. null means "share it evenly",
    // which is what a fresh layout should do.
    split: { col: null, row: null },
    zoomed: null,               // index of the pane filling the workspace
    linkMode: 'session',   // 'none' | 'session' | 'all'
    focused: 0,
    presets: { filters: [], imports: [] },
    panelDefs: [],
    colormaps: [],
    seq: 0,
    measure: false,          // measure tool armed
    placing: false,          // waiting for a click to place a bookmark
  };

  const DEFAULT_PANEL = 'traces';

  /* ==================================================================
     Session lifecycle
     ================================================================== */
  async function openSession(path, opts) {
    if (!path) return null;
    opts = opts || {};

    if (opts.replace) {
      // A re-read of the same recording: drop the old entry so we do not end
      // up with two tabs for one session.
      delete XF.sessions[opts.replace];
      XF.order = XF.order.filter((x) => x !== opts.replace);
    }

    const existing = XF.order.find((id) => XF.sessions[id].path === path);
    if (existing && !opts.duplicate) {
      XF.active = existing;
      render();
      return XF.sessions[existing];
    }

    let info;
    try {
      info = await apiPost('/api/csc/open', {
        path, even_only: opts.evenOnly !== false, invert: opts.invert !== false,
      });
    } catch (e) {
      toast(e.message, 'err', 8000);
      return null;
    }

    const id = 's' + (++XF.seq);
    const dur = info.duration_s || 10;
    const sess = {
      id, path, info,
      identity: info.identity || {},
      stored: info.stored || null,
      media: info.media || { videos: [], tracking: [] },
      sel: new Set(info.channels.map((c) => c.index)),
      bad: new Set((info.bad_channels || []).map(Number)),
      events: [], eventsMeta: null,
      t0: 0, span: Math.min(10, Math.max(0.05, dur)),
      gain: 1, hp: 0, lp: 0, notch: 0,
      normalize: 'shared',
      evenOnly: opts.evenOnly !== false,
      invert: opts.invert !== false,
      spacing: 50,
      win: null, reqId: 0,
      ylim: null,              // pinned trace amplitude (uV), null = auto
      clim: null,              // pinned raster color scale, null = auto
      bookmarks: (info.bookmarks || []),
      spikeSets: (info.spike_sets || []),
      spikeDraft: null,        // detected but not yet committed
      nev: info.nev || [],
      overview: null,          // whole-recording amplitude profile
      overviewReq: false,
      color: BARRY.hues(XF.order.length),
    };

    // Everything is saved by default, so a reopened session comes back the way
    // it was left rather than at defaults.
    const vs = info.view_state || {};
    for (const k of ['gain', 'hp', 'lp', 'notch', 'normalize', 'spacing',
                     'ylim', 'clim', 't0', 'span']) {
      if (vs[k] !== undefined && vs[k] !== null) sess[k] = vs[k];
    }
    if (Array.isArray(vs.channels) && vs.channels.length) {
      sess.sel = new Set(vs.channels.filter((i) => i < info.channels.length));
    }
    XF.sessions[id] = sess;
    XF.order.push(id);
    XF.active = id;

    // First session fills pane 0; later ones take the next free pane if the
    // layout has room, so opening a second session in 2-up just works.
    if (!XF.panes.length) {
      XF.panes = [{ sessionId: id, panel: DEFAULT_PANEL }];
    } else {
      const free = XF.panes.findIndex((p) => !p || !p.sessionId);
      if (free >= 0) XF.panes[free] = { sessionId: id, panel: DEFAULT_PANEL };
      else if (XF.panes.length < XF.nPanes) XF.panes.push({ sessionId: id, panel: DEFAULT_PANEL });
      else XF.panes[XF.focused] = { sessionId: id, panel: DEFAULT_PANEL };
    }

    $('#xfDrop').classList.add('hidden');
    $('#paneGrid').classList.remove('hidden');

    const notes = [];
    if (sess.bad.size) notes.push(sess.bad.size + ' bad channel(s)');
    if (Object.keys(info.view_state || {}).length) notes.push('view restored');
    toast('Opened ' + (sess.identity.label || info.name)
          + (notes.length ? ' · ' + notes.join(' · ') : ''), 'ok');

    BARRY.activity.log('session.open', {
      path, channels: info.channels.length, fs: info.fs,
      duration_s: info.duration_s, restored: notes,
    }, sess);

    render();
    refreshAll();
    autoImportNev(sess);
    return sess;
  }

  /* Session tab colors come from BARRY.hues, which reads the theme, so a
     single open recording is marked in the current accent rather than always
     in the UVM gold. */

  /* Colors for event classes. Fixed on purpose, unlike the theme ramp: these
     are drawn over a jet raster and are saved with the session, so a class
     must not change color when the theme does. Chosen to stay apart from each
     other and from the trace, which rules out anything too blue or too green
     in the middle of the ramp. */
  const EVENT_COLORS = [
    '#FF6B6B', '#FFB81C', '#4DD4C4', '#8ec5ff', '#c9a6ff',
    '#f59fb4', '#9ee37d', '#ffd08a', '#ff9de2', '#7fd4ff',
  ];

  /* An "event class" groups events that share a label -- TTL 1, "solid",
     a Toothy DS, a manual mark -- so they can be named, colored, hidden and
     counted as a set. The mapping lives on the session and is saved with it. */
  function eventClasses(sess) {
    if (!sess._eventClasses) sess._eventClasses = {};
    return sess._eventClasses;
  }

  function classKeyOf(ev) {
    return String((ev && ev.label) || 'event');
  }

  function ensureClasses(sess) {
    const classes = eventClasses(sess);
    let next = Object.keys(classes).length;
    for (const ev of (sess.events || [])) {
      const key = classKeyOf(ev);
      if (!classes[key]) {
        classes[key] = {
          key,
          name: key,
          color: EVENT_COLORS[next % EVENT_COLORS.length],
          visible: true,
        };
        next += 1;
      }
    }
    // Keep a live count so the manager can show how many of each there are.
    for (const c of Object.values(classes)) c.n = 0;
    for (const ev of (sess.events || [])) {
      const c = classes[classKeyOf(ev)];
      if (c) c.n += 1;
    }
    return classes;
  }

  /* The session is passed in rather than hung off the event.

      Events used to carry a `_sess` back-pointer so this could find their
      class. That made every event part of a reference cycle
      (session -> events -> event -> session), and JSON.stringify refuses to
      walk a cycle -- so the moment a recording had any events loaded, saving
      a figure layout and previewing a figure both died with "Converting
      circular structure to JSON". Every caller already knows the session. */
  function eventColor(sess, ev, P) {
    const cls = sess ? eventClasses(sess)[classKeyOf(ev)] : null;
    return (cls && cls.color) || (P ? P.event : '#FF6B6B');
  }

  function eventVisible(sess, ev) {
    const cls = eventClasses(sess)[classKeyOf(ev)];
    return !cls || cls.visible !== false;
  }

  function closeSession(id) {
    delete XF.sessions[id];
    XF.order = XF.order.filter((x) => x !== id);
    // Tear the pane down before dropping the reference, or renderPanes has
    // nothing left to tear down and its listeners outlive the session.
    XF.panes.forEach((p, i) => {
      if (p && p.sessionId === id) { disposePane(i); XF.panes[i] = null; }
    });
    if (XF.active === id) XF.active = XF.order[0] || null;
    if (!XF.order.length) {
      for (let i = 0; i < XF.panes.length; i++) disposePane(i);
      XF.panes = [];
      $('#xfDrop').classList.remove('hidden');
      $('#paneGrid').classList.add('hidden');
    }
    render();
  }

  const active = () => XF.sessions[XF.active] || null;
  const sessionOf = (pane) => (pane && XF.sessions[pane.sessionId]) || null;

  /* ==================================================================
     Pane assignment -- drag a tab onto a pane, or clear a pane
     ================================================================== */
  function assignPane(index, sessionId, panel) {
    const prev = XF.panes[index];
    XF.panes[index] = {
      sessionId,
      // Keep whatever view the pane was showing, so dropping a second
      // recording into a CSD pane gives you its CSD, not traces again.
      panel: panel || (prev && prev.panel) || DEFAULT_PANEL,
      cmap: prev && prev.cmap,
      fmin: prev && prev.fmin, fmax: prev && prev.fmax,
      tfMode: prev && prev.tfMode,
    };
    XF.focused = index;
    XF.active = sessionId;
    BARRY.activity.log('pane.assign', {
      pane: index, panel: XF.panes[index].panel,
    }, XF.sessions[sessionId]);
    render();
    refreshPane(index);
  }

  function clearPane(index) {
    disposePane(index);
    const pane = XF.panes[index];
    const sess = sessionOf(pane);
    XF.panes[index] = null;
    if (sess) {
      BARRY.activity.log('pane.clear', { pane: index }, sess);
    }
    render();
  }

  function makeDropTarget(node, index) {
    const stop = (e) => { e.preventDefault(); e.stopPropagation(); };
    node.addEventListener('dragover', (e) => {
      if (!Array.from(e.dataTransfer.types).includes('text/barry-session')) return;
      stop(e);
      e.dataTransfer.dropEffect = 'copy';
      node.classList.add('pane-drop');
    });
    node.addEventListener('dragleave', (e) => {
      if (e.target === node) node.classList.remove('pane-drop');
    });
    node.addEventListener('drop', (e) => {
      const sid = e.dataTransfer.getData('text/barry-session');
      node.classList.remove('pane-drop');
      if (!sid || !XF.sessions[sid]) return;
      stop(e);
      assignPane(index, sid);
    });
  }

  /* ==================================================================
     Rendering
     ================================================================== */
  function render() {
    renderTabs();
    renderPanes();
  }

  function renderTabs() {
    const host = $('#xfTabs');
    host.innerHTML = '';
    for (const id of XF.order) {
      const s = XF.sessions[id];
      host.appendChild(el('div', {
        class: 'xf-tab' + (id === XF.active ? ' active' : ''),
        title: s.path + '\n\nDrag onto a pane to show it there.',
        draggable: 'true',
        ondragstart: (e) => {
          e.dataTransfer.setData('text/barry-session', id);
          e.dataTransfer.effectAllowed = 'copy';
          document.body.classList.add('dragging-session');
        },
        ondragend: () => document.body.classList.remove('dragging-session'),
        onclick: () => { XF.active = id; render(); },
      }, [
        el('span', { class: 'dot', style: 'background:' + s.color }),
        el('span', { class: 'nm', text: s.identity.label || s.info.name }),
        el('span', {
          class: 'x', text: '×', title: 'Close',
          onclick: (e) => { e.stopPropagation(); closeSession(id); },
        }),
      ]));
    }
  }

  /* Every pane registers its window-level listeners and observers here, and
     they are all torn down before the pane is rebuilt.

     This matters more than it looks. Nearly every interaction rebuilds the
     panes -- changing panel, pinning a scale, adding a session, toggling the
     measure tool -- and each trace pane hangs two mousemove/mouseup handlers
     and a ResizeObserver off the window. Without teardown those accumulate on
     detached nodes and keep running on every mouse move, so the viewer gets
     progressively heavier the longer it is open. */
  function disposePane(index) {
    const pane = XF.panes[index];
    if (!pane) return;
    for (const off of (pane._teardown || [])) {
      try { off(); } catch (e) { /* a dead node is fine to ignore */ }
    }
    pane._teardown = [];
    pane._canvas = pane._overlay = pane._readout = null;
    pane._loading = pane._mini = pane._img = pane._grid = null;
    pane._hud = pane._ghost = pane._inputLine = null;
  }

  function onPane(pane, target, type, fn, opts) {
    target.addEventListener(type, fn, opts);
    (pane._teardown = pane._teardown || [])
      .push(() => target.removeEventListener(type, fn, opts));
  }

  function renderPanes() {
    const grid = $('#paneGrid');
    grid.className = 'pane-grid panes-' + XF.nPanes
                   + (XF.zoomed != null ? ' zoomed' : '');
    applySplit(grid);
    for (let i = 0; i < XF.panes.length; i++) disposePane(i);
    grid.innerHTML = '';

    while (XF.panes.length < XF.nPanes) XF.panes.push(null);
    XF.panes.length = Math.max(XF.nPanes, 1);

    for (let i = 0; i < XF.nPanes; i++) {
      // One pane filling the workspace is just the others not being built.
      // Simpler than a CSS overlay, and the hidden panes stop fetching.
      if (XF.zoomed != null && i !== XF.zoomed) continue;
      grid.appendChild(buildPane(i));
    }
    if (XF.zoomed == null) addSplitters(grid);

    // Rebuilding the panes can change their height (the control strip wraps
    // differently), and a canvas keeps whatever size it was last drawn at. So
    // redraw once the new layout has actually settled, or the traces end up
    // stretched relative to everything positioned in DOM pixels.
    requestAnimationFrame(() => {
      for (let i = 0; i < XF.nPanes; i++) redrawGeometry(i);
    });
  }

  function buildPane(index) {
    const pane = XF.panes[index];
    const sess = sessionOf(pane);

    if (!sess) {
      const empty = el('div', { class: 'pane empty' }, [
        el('div', { style: 'text-align:center' }, [
          el('div', { text: XF.order.length ? 'Empty pane — drag a tab here'
                                            : 'Empty pane' }),
          el('div', { style: 'margin-top:8px;display:flex;gap:6px;justify-content:center' },
            (XF.order.length
              ? XF.order.slice(0, 4).map((sid) => el('button', {
                  class: 'btn ghost sm',
                  text: XF.sessions[sid].identity.label || XF.sessions[sid].info.name,
                  onclick: () => assignPane(index, sid),
                }))
              : [el('button', { class: 'btn ghost sm', text: 'Open a session…',
                                onclick: pickFolder })])),
        ]),
      ]);
      makeDropTarget(empty, index);
      return empty;
    }

    const box = el('div', {
      class: 'pane' + (index === XF.focused ? ' focused' : ''),
      onmousedown: () => { XF.focused = index; XF.active = pane.sessionId; renderTabs(); },
    });
    makeDropTarget(box, index);

    box.appendChild(paneHead(index, pane, sess));
    const strip = paneControls(index, pane, sess);
    box.appendChild(strip);
    wireStripScroll(strip);

    // Trace panes carry their channel list inside the plot; raster panes keep
    // the side column, where exact per-lane alignment does not apply.
    const sideCol = isChannelPanel(pane.panel) && pane.panel !== 'traces';
    const main = el('div', { class: 'pane-main' + (sideCol ? '' : ' no-channels') });
    if (sideCol) main.appendChild(paneChannels(index, sess));
    main.appendChild(panePlot(index, pane, sess));
    box.appendChild(main);
    return box;
  }

  /* The grid's own proportions. Dragging a splitter writes a fraction here
     and nothing else changes -- the panes are still grid children, so the
     canvases resize through the ResizeObserver that is already watching. */
  function applySplit(grid) {
    const c = XF.split.col, r = XF.split.row;
    if (XF.zoomed != null || XF.nPanes === 1) {
      grid.style.gridTemplateColumns = '';
      grid.style.gridTemplateRows = '';
      return;
    }
    const pct = (f) => (f * 100).toFixed(3) + '%';
    if (XF.nPanes >= 2) {
      grid.style.gridTemplateColumns = c
        ? pct(c) + ' ' + pct(1 - c) : '';
    }
    if (XF.nPanes === 4) {
      grid.style.gridTemplateRows = r ? pct(r) + ' ' + pct(1 - r) : '';
    }
    // The divider has to follow the split it controls. Written as custom
    // properties so the CSS owns the hit-area geometry and this owns only
    // where the line is.
    grid.style.setProperty('--split-col', pct(c == null ? 0.5 : c));
    grid.style.setProperty('--split-row', pct(r == null ? 0.5 : r));
  }

  /* Draggable dividers, laid over the gaps between panes.

     They are absolutely positioned rather than being grid items: a grid item
     would have to be woven into the pane order, and every index in this file
     assumes grid.children[i] is pane i. */
  function addSplitters(grid) {
    if (XF.nPanes < 2) return;
    const drag = (kind) => (e) => {
      e.preventDefault();
      const r = grid.getBoundingClientRect();
      const move = (ev) => {
        const f = kind === 'col'
          ? (ev.clientX - r.left) / r.width
          : (ev.clientY - r.top) / r.height;
        // Never let a pane be dragged away to nothing -- a 0px pane cannot
        // be grabbed back.
        XF.split[kind] = Math.max(0.15, Math.min(0.85, f));
        applySplit(grid);
      };
      const up = () => {
        window.removeEventListener('mousemove', move);
        window.removeEventListener('mouseup', up);
        document.body.classList.remove('splitting');
        for (let i = 0; i < XF.nPanes; i++) redrawGeometry(i);
        BARRY.activity.log('panes.resize', { [kind]: XF.split[kind] });
      };
      window.addEventListener('mousemove', move);
      window.addEventListener('mouseup', up);
      document.body.classList.add('splitting');
    };

    grid.appendChild(el('div', {
      class: 'pane-split col', title: 'Drag to resize \u00b7 double-click to even up',
      onmousedown: drag('col'),
      ondblclick: () => { XF.split.col = null; applySplit(grid);
                          for (let i = 0; i < XF.nPanes; i++) redrawGeometry(i); },
    }));
    if (XF.nPanes === 4) {
      grid.appendChild(el('div', {
        class: 'pane-split row', title: 'Drag to resize \u00b7 double-click to even up',
        onmousedown: drag('row'),
        ondblclick: () => { XF.split.row = null; applySplit(grid);
                            for (let i = 0; i < XF.nPanes; i++) redrawGeometry(i); },
      }));
    }
  }

  /* One pane fills the workspace, and comes back. */
  function zoomPane(index) {
    XF.zoomed = XF.zoomed === index ? null : index;
    BARRY.activity.log('panes.zoom',
                       { pane: index, on: XF.zoomed != null });
    render();
    refreshAll();
  }

  /* Put a piece of chrome away, or bring it back. */
  function toggleChrome(what) {
    XF.chrome[what] = !XF.chrome[what];
    BARRY.activity.log('panes.chrome', { what, on: XF.chrome[what] });
    applyChrome();
    render();
    // The plot got bigger or smaller, so the canvases have to be remeasured.
    requestAnimationFrame(() => {
      for (let i = 0; i < XF.nPanes; i++) redrawGeometry(i);
    });
  }

  function applyChrome() {
    const v = document.getElementById('view-xplore');
    if (!v) return;
    for (const k of ['channels', 'strip', 'heads', 'tabs']) {
      v.classList.toggle('hide-' + k, !XF.chrome[k]);
    }
  }

  /* Real full screen, for the pane and for a popped-out window.

     A popped-out pane is its own browser window, and the thing people want
     from one is the whole monitor with nothing else on it. That needs the
     Fullscreen API rather than a CSS class -- a maximised browser window
     still has its own chrome above the page. */
  async function goFullscreen(node) {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
        return false;
      }
      await (node || document.documentElement).requestFullscreen();
      return true;
    } catch (e) {
      toast('This browser would not go full screen: ' + e.message, 'err', 6000);
      return false;
    }
  }

  /* What can be put away, and how to say it. */
  const CHROME_BITS = [
    ['channels', 'Channel list',
     'The column of channel names beside a raster'],
    ['strip', 'Control strip',
     'The window, scale and menu row above each pane'],
    ['heads', 'Pane headers',
     'The name, panel picker and pane buttons'],
    ['tabs', 'Session tabs',
     'The row of open recordings at the top'],
  ];

  function viewMenu() {
    const box = el('div', { class: 'ctl-pop-body' });
    box.appendChild(el('div', { class: 'ctl-pop-title', text: 'Show' }));
    for (const [key, name, why] of CHROME_BITS) {
      box.appendChild(el('label', {
        class: 'toggle' + (XF.chrome[key] ? ' on' : ''), title: why,
      }, [
        el('input', {
          type: 'checkbox', checked: XF.chrome[key] ? 'checked' : null,
          onchange: () => { toggleChrome(key); },
        }),
        el('span', { text: name }),
      ]));
    }
    box.appendChild(el('p', { class: 'ctl-pop-note',
      text: 'Hiding a piece of chrome gives its space to the data. Nothing '
          + 'is lost — tick it back on here.' }));

    box.appendChild(el('div', { class: 'ctl-pop-title', text: 'Space' }));
    box.appendChild(el('div', { class: 'ctl-pop-row' }, [
      el('button', {
        class: 'mini', text: 'Hide it all',
        title: 'Everything off at once, for a screenshot or a talk',
        onclick: () => {
          for (const [k] of CHROME_BITS) XF.chrome[k] = false;
          applyChrome(); render();
          requestAnimationFrame(() => {
            for (let i = 0; i < XF.nPanes; i++) redrawGeometry(i);
          });
        },
      }),
      el('button', {
        class: 'mini', text: 'Bring it back',
        onclick: () => {
          for (const [k] of CHROME_BITS) XF.chrome[k] = true;
          applyChrome(); render();
          requestAnimationFrame(() => {
            for (let i = 0; i < XF.nPanes; i++) redrawGeometry(i);
          });
        },
      }),
      el('button', {
        class: 'mini', text: 'Even up the panes',
        title: 'Undo any resizing of the splitters',
        onclick: () => {
          XF.split = { col: null, row: null };
          render();
          requestAnimationFrame(() => {
            for (let i = 0; i < XF.nPanes; i++) redrawGeometry(i);
          });
        },
      }),
      el('button', {
        class: 'mini', text: 'Full screen',
        title: 'The whole monitor, nothing else on it',
        onclick: () => goFullscreen(document.getElementById('view-xplore')),
      }),
    ]));
    return box;
  }

  function isChannelPanel(panel) {
    return ['traces', 'voltage', 'csd', 'theta'].includes(panel);
  }

  function paneHead(index, pane, sess) {
    const panelOpts = XF.panelDefs.length ? XF.panelDefs
      : [{ id: 'traces', name: 'Voltage traces' }];

    const extras = [];
    if (sess.media.videos && sess.media.videos.length) {
      extras.push({ id: 'video', name: 'Video' });
    }
    if (sess.media.tracking && sess.media.tracking.length) {
      extras.push({ id: 'tracking', name: 'Position tracking' });
    }

    return el('div', { class: 'pane-head' }, [
      el('span', { class: 'dot', style: 'width:7px;height:7px;border-radius:50%;background:' + sess.color }),
      el('span', { class: 'pane-name', text: sess.identity.label || sess.info.name,
                   title: sess.path }),
      el('span', { class: 'pane-meta',
                   text: Math.round(sess.info.fs) + ' Hz · ' + sess.info.channels.length + ' ch' }),
      el('div', { class: 'spacer' }),
      el('select', {
        title: 'What this pane shows',
        onchange: (e) => {
          const prev = pane.panel;
          pane.panel = e.target.value;
          BARRY.activity.log('panel.change', { from: prev, to: pane.panel,
                                               pane: index }, sess);
          render(); refreshPane(index);
        },
      }, panelOpts.concat(extras).map((p) =>
        el('option', { value: p.id, text: p.name,
                       selected: pane.panel === p.id ? 'selected' : null }))),
      eventNav(index, pane, sess),
      el('button', {
        class: 'mini' + (XF.measure ? ' active' : ''), text: '\u2194',
        title: 'Measure tool (m) \u2014 drag across the trace to read '
             + '\u0394t and \u0394amplitude',
        onclick: (e) => { e.stopPropagation(); setMeasure(!XF.measure); },
      }),
      el('button', {
        class: 'mini' + (XF.zoomed === index ? ' active' : ''),
        text: XF.zoomed === index ? '\u2921' : '\u2922',
        title: XF.zoomed === index
          ? 'Back to the other panes'
          : 'Fill the workspace with this pane',
        onclick: (e) => { e.stopPropagation(); zoomPane(index); },
      }),
      el('button', {
        class: 'mini', text: '\u26f6',
        title: 'Full screen \u2014 the whole monitor, nothing else on it',
        onclick: (e) => {
          e.stopPropagation();
          const box = $('#paneGrid').children[
            XF.zoomed != null ? 0 : index];
          goFullscreen(box || document.getElementById('view-xplore'));
        },
      }),
      el('button', {
        class: 'mini', text: '⇱',
        title: 'Pop this pane out into its own window '
             + '(shift-click for full screen)',
        onclick: (e) => {
          e.stopPropagation();
          popOut(pane, sess, { full: e.shiftKey, chrome: 'notabs' });
        },
      }),
      el('button', {
        class: 'mini pane-x', text: '✕',
        title: 'Remove this session from the pane (its tab stays open)',
        onclick: (e) => { e.stopPropagation(); clearPane(index); },
      }),
    ]);
  }


  /* ======================================================================
     Feature 1 -- Event navigator
     Scrolling a ten-minute recording looking for the next discharge is the
     job this replaces. n / p step through whatever is currently visible
     (so the class filters apply), centring the window on each mark.
     ====================================================================== */
  function navEvents(sess) {
    const out = [];
    for (const ev of (sess.events || [])) {
      if (eventVisible(sess, ev)) out.push({ t: ev.start, what: ev.label || 'event' });
    }
    for (const st of (sess.spikeSets || [])) {
      for (const ev of (st.events || [])) {
        out.push({ t: ev.start, what: st.name || 'spikes' });
      }
    }
    for (const bm of (sess.bookmarks || [])) {
      out.push({ t: bm.t, what: bm.name || 'bookmark' });
    }
    out.sort((a, b) => a.t - b.t);
    return out;
  }

  function stepEvent(index, dir) {
    const pane = XF.panes[index];
    const sess = sessionOf(pane);
    if (!sess) return;
    const list = navEvents(sess);
    if (!list.length) {
      toast('No events, spikes or bookmarks in this session yet.', 'err', 3000);
      return;
    }
    const w = winOf(pane, sess);
    const center = w.t0 + w.span / 2;
    // A hair of slack, or repeated presses stick on the same mark.
    const eps = Math.max(1e-4, w.span * 1e-3);
    let target = null;
    if (dir > 0) target = list.find((e) => e.t > center + eps);
    else for (const e of list) if (e.t < center - eps) target = e;

    if (!target) {
      toast(dir > 0 ? 'That was the last one.' : 'That was the first one.',
            null, 2000);
      return;
    }
    setWindow(index, target.t - w.span / 2, w.span);
    BARRY.activity.log('event.navigate',
                       { dir: dir > 0 ? 'next' : 'prev', t: round(target.t, 4),
                         what: target.what }, sess);
    toast(target.what + ' at ' + fmtTime(target.t), null, 1600);
  }

  function eventNav(index, pane, sess) {
    const n = navEvents(sess).length;
    return el('div', { class: 'ev-nav' }, [
      el('button', {
        class: 'mini', text: '\u2039',
        title: 'Previous event / spike / bookmark (p)',
        disabled: n ? null : 'disabled',
        onclick: (e) => { e.stopPropagation(); stepEvent(index, -1); },
      }),
      el('span', { class: 'cnt', text: String(n),
                   title: n + ' navigable mark(s) in this session' }),
      el('button', {
        class: 'mini', text: '\u203a',
        title: 'Next event / spike / bookmark (n)',
        disabled: n ? null : 'disabled',
        onclick: (e) => { e.stopPropagation(); stepEvent(index, 1); },
      }),
    ]);
  }

  /* ======================================================================
     Feature 2 -- Measure tool
     Drag across a trace pane and it reports the span in ms, the equivalent
     rate in Hz, and the amplitude difference between the endpoints on the
     channel under the cursor. Numbers people otherwise get by holding a
     ruler against the screen.
     ====================================================================== */
  function setMeasure(on) {
    XF.measure = !!on;
    render();
    toast(XF.measure
      ? 'Measure tool on \u2014 drag across a trace. Press m to turn it off.'
      : 'Measure tool off.', null, 2600);
    BARRY.activity.log('measure.toggle', { on: XF.measure });
  }

  function measureHud(pane) {
    if (!pane._hud) {
      const host = pane._canvas && pane._canvas.parentNode;
      if (!host) return null;
      pane._hud = el('div', { class: 'measure-hud' });
      host.appendChild(pane._hud);
    }
    return pane._hud;
  }

  function clearHud(pane) {
    if (pane._hud) { pane._hud.remove(); pane._hud = null; }
  }

  /* One channel's amplitude, read off the envelope already in hand. */
  function valueAt(win, laneIdx, frac) {
    if (!win || !win.series || !win.series.length) return null;
    const ser = win.series[clamp(laneIdx, 0, win.series.length - 1)];
    const j = clamp(Math.round(frac * (win.n_points - 1)), 0, win.n_points - 1);
    const lo = ser.min[j], hi = ser.max[j];
    return (lo === null || hi === null) ? null : (lo + hi) / 2;
  }

  function drawMeasure(index, pane, m) {
    const c = pane._canvas;
    if (!c || !m) return;
    const ctx = c.getContext('2d');
    const P = palette();
    const h = c.clientHeight;
    const y0 = padTopOf(index);
    ctx.save();
    ctx.globalAlpha = .12;
    ctx.fillStyle = P.accent;
    ctx.fillRect(Math.min(m.x0, m.x1), y0, Math.abs(m.x1 - m.x0), h - PAD.b - y0);
    ctx.globalAlpha = 1;
    ctx.strokeStyle = P.accent;
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    for (const x of [m.x0, m.x1]) {
      ctx.beginPath();
      ctx.moveTo(Math.round(x) + .5, y0);
      ctx.lineTo(Math.round(x) + .5, h - PAD.b);
      ctx.stroke();
    }
    ctx.restore();
  }

  function wireMeasure(index, pane, sess, canvas) {
    let m = null;
    const geom = () => {
      const rect = canvas.getBoundingClientRect();
      const y0 = padTopOf(index);
      return { rect, padL: PAD_TRACES_L, y0,
               plotW: Math.max(1, rect.width - PAD_TRACES_L - PAD.r),
               plotH: Math.max(1, rect.height - y0 - PAD.b) };
    };

    const paint = () => {
      drawPane(index);
      if (m) drawMeasure(index, pane, m);
    };

    const down = (e) => {
      if (!XF.measure || e.button !== 0) return false;
      const g = geom();
      const x = e.clientX - g.rect.left, y = e.clientY - g.rect.top;
      if (x < g.padL || y < g.y0) return false;
      const win = pane._win || sess.win;
      const lane = (win && win.series && win.series.length)
        ? g.plotH / win.series.length : g.plotH;
      m = { x0: x, x1: x, lane: Math.floor((y - g.y0) / lane) };
      paint();
      return true;
    };

    const move = (e) => {
      if (!m) return;
      const g = geom();
      m.x1 = clamp(e.clientX - g.rect.left, g.padL, g.padL + g.plotW);
      const win = pane._win || sess.win;
      const f0 = (m.x0 - g.padL) / g.plotW;
      const f1 = (m.x1 - g.padL) / g.plotW;
      const w = winOf(pane, sess);
      const t0 = w.t0 + f0 * w.span;
      const t1 = w.t0 + f1 * w.span;
      const dt = Math.abs(t1 - t0);
      const v0 = valueAt(win, m.lane, f0);
      const v1 = valueAt(win, m.lane, f1);
      const label = (win && win.series && win.series[m.lane])
        ? win.series[m.lane].label : '';
      const units = (win && win.units) || 'uV';

      const hud = measureHud(pane);
      if (hud) {
        hud.textContent =
          '\u0394t   ' + (dt < 1 ? (dt * 1000).toFixed(1) + ' ms'
                                : dt.toFixed(3) + ' s') + '\n'
          + '     ' + (dt > 0 ? (1 / dt).toFixed(2) + ' Hz' : '\u2014') + '\n'
          + (v0 === null || v1 === null ? ''
             : '\u0394' + label + ' ' + sig(v1 - v0) + ' ' + units + '\n')
          + fmtTime(Math.min(t0, t1)) + ' \u2192 ' + fmtTime(Math.max(t0, t1));
        hud.style.left = Math.min(m.x0, m.x1) + 'px';
        hud.style.top = (g.y0 + 4) + 'px';
      }
      paint();
    };

    const up = () => {
      if (!m) return;
      const g = geom();
      const w = winOf(pane, sess);
      const dt = Math.abs((m.x1 - m.x0) / g.plotW) * w.span;
      const win = pane._win || sess.win;
      if (dt > 0) {
        BARRY.activity.log('measure.read', {
          dt: round(dt, 5), hz: round(1 / dt, 3),
          channel: (win && win.series && win.series[m.lane])
            ? win.series[m.lane].label : null,
        }, sess);
      }
      m = null;
      // The readout stays put until the next click, so the number can be
      // written down without holding the mouse still.
      paint();
    };

    canvas.addEventListener('mousedown', (e) => {
      if (down(e)) { e.stopPropagation(); e.preventDefault(); }
      else if (!XF.measure) clearHud(pane);
    }, true);
    onPane(pane, window, 'mousemove', move);
    onPane(pane, window, 'mouseup', up);
    (pane._teardown = pane._teardown || []).push(() => clearHud(pane));
  }

  /* ======================================================================
     Feature 3 -- Amplitude profile on the overview strip
     The strip already carries events and bookmarks. Painting the
     recording's own envelope behind them turns a position indicator into a
     map: a seizure, a cable knock or a flat stretch shows at a glance.
     ====================================================================== */
  async function loadOverview(sess) {
    if (sess.overview || sess.overviewReq) return;
    sess.overviewReq = true;
    try {
      const res = await apiPost('/api/csc/overview', {
        path: sess.path, even_only: sess.evenOnly, invert: sess.invert,
        channel: firstSel(sess), bins: 700,
      });
      if (res.ok) sess.overview = res;
    } catch (e) {
      sess.overview = null;   // a slow share must not look like a failure
    }
    sess.overviewReq = false;
    refreshSession(sess);
  }

  /* ======================================================================
     The scale control

     This was a button that opened a popover, with the value it controlled
     shown separately -- so the number you wanted to change and the control
     that changed it were in different places. Now the readout is the control:
     a slider for getting there quickly and a number for saying exactly, side
     by side in the strip with everything else.

     The slider is logarithmic. Amplitudes here run from a few microvolts to a
     few thousand, and a linear slider spends nine tenths of its travel in a
     range nobody uses.
     ====================================================================== */
  const SCALE_MIN = 1, SCALE_MAX = 20000;

  const scaleToSlider = (v) => Math.round(1000
    * (Math.log(clamp(v, SCALE_MIN, SCALE_MAX) / SCALE_MIN))
    / Math.log(SCALE_MAX / SCALE_MIN));
  const sliderToScale = (n) =>
    SCALE_MIN * Math.pow(SCALE_MAX / SCALE_MIN, clamp(n, 0, 1000) / 1000);

  function scaleControl(index, pane, sess) {
    const isTraces = pane.panel === 'traces';
    const data = isTraces ? (pane._win || sess.win) : pane._panelData;

    if (!isTraces && !isImagePanel(pane.panel)) {
      return el('span');           // video and tracking have no scale
    }

    const auto = isTraces ? (data && data.robust_auto)
                          : (data && data.clim_auto);
    const pinned = isTraces ? (sess.ylim != null)
                            : !!(pane.clim || sess.clim);

    // One magnitude drives both: for traces it is the half-lane amplitude,
    // for a raster the symmetric color limit.
    let magnitude;
    if (isTraces) {
      magnitude = sess.ylim != null ? sess.ylim : (auto || 100);
    } else {
      const cur = pane.clim || sess.clim || auto || [-1, 1];
      magnitude = Math.max(Math.abs(cur[0]), Math.abs(cur[1])) || 1;
    }

    const units = isTraces ? 'uV' : ((data && data.units) || '');

    /* `commit` is false while the slider is being dragged and true when it is
       let go or a number is typed.

       Nothing rebuilds the control strip mid-drag. It used to, once per input
       event, which replaced the very slider under the pointer -- the drag
       died, and two rebuilds racing each other threw NotFoundError from
       replaceChild. A drag now only repaints. */
    const baseClim = pane.clim || sess.clim || auto || [-1, 1];

    const apply = (v, commit) => {
      const m = Math.abs(v);
      if (!isFinite(m) || m <= 0) return;

      if (isTraces) {
        sess.ylim = m;
        // Drawn from data already in hand, so this is immediate.
        drawPane(index);
        if (commit) {
          BARRY.activity.log('ylim.change', { ylim: m }, sess);
          queueSaveState(sess);
          publishLink(sess.t0, sess.span, sess);
          refreshControls(index);
        }
        return;
      }

      // A raster's colors are mapped server-side, so this one does need a
      // new image -- but only after the drag settles, not per pixel.
      // Measured from the scale at the start of the drag, so dragging back
      // and forth lands where the pointer says rather than compounding.
      const peak = Math.max(Math.abs(baseClim[0]), Math.abs(baseClim[1])) || 1;
      const k = m / peak;
      pane.clim = [round(baseClim[0] * k, 6), round(baseClim[1] * k, 6)];
      clearTimeout(pane._climTimer);
      pane._climTimer = setTimeout(() => refreshPane(index), commit ? 0 : 220);
      if (commit) {
        BARRY.activity.log('clim.change',
                           { clim: pane.clim, panel: pane.panel }, sess);
        refreshControls(index);
      }
    };

    const slider = el('input', {
      type: 'range', min: '0', max: '1000', step: '1',
      class: 'scale-slider',
      value: String(scaleToSlider(magnitude)),
      title: 'Drag for the scale, or type an exact value',
      oninput: (e) => {
        const v = sliderToScale(+e.target.value);
        const box = e.target.parentNode.querySelector('.scale-num');
        if (box) box.value = String(round(v, v < 10 ? 3 : 1));
        apply(v, false);
      },
      onchange: (e) => apply(sliderToScale(+e.target.value), true),
    });

    const num_ = el('input', {
      type: 'number', class: 'scale-num', step: 'any',
      value: String(round(magnitude, magnitude < 10 ? 3 : 1)),
      title: 'Exact scale' + (units ? ' in ' + units : ''),
      onchange: (e) => {
        const v = Math.abs(parseFloat(e.target.value));
        if (!isFinite(v) || v <= 0) { refreshControls(index); return; }
        slider.value = String(scaleToSlider(v));
        apply(v, true);
      },
      onkeydown: (e) => { if (e.key === 'Enter') e.target.blur(); },
    });

    return el('div', { class: 'ctl scale-ctl' }, [
      el('label', {
        text: isTraces ? '\u00b1 ' + units : 'Color',
        title: auto
          ? (isTraces
             ? 'Auto is ' + sig(auto) + ' ' + units
               + ' \u2014 the 99.5th percentile of this window'
             : 'Auto is [' + sig(auto[0]) + ', ' + sig(auto[1]) + ']')
          : 'Derived from each window',
      }),
      el('div', { class: 'ctl-group' }, [
        slider,
        num_,
        el('button', {
          class: 'mini' + (pinned ? '' : ' active'),
          text: pinned ? 'pinned' : 'auto',
          title: pinned
            ? 'Pinned \u2014 click to go back to per-window scaling'
            : 'Scaling to each window. Move the slider to pin it.',
          onclick: () => {
            if (isTraces) {
              sess.ylim = pinned ? null : Math.abs(magnitude);
              BARRY.activity.log('ylim.change', { ylim: sess.ylim }, sess);
              queueSaveState(sess);
              refreshSession(sess);
            } else {
              if (pinned) { pane.clim = null; sess.clim = null; }
              else { pane.clim = [-Math.abs(magnitude), Math.abs(magnitude)]; }
              BARRY.activity.log('clim.change',
                                 { clim: pane.clim, panel: pane.panel }, sess);
              refreshPane(index);
            }
            refreshControls(index);
          },
        }),
        isTraces ? null : el('button', {
          class: 'mini', text: 'edit\u2026',
          title: 'Set the two limits independently',
          onclick: (e) => { e.stopPropagation(); toggleScalePop(index, pane, sess); },
        }),
      ]),
    ]);
  }

  /* ======================================================================
     Frequency view

     Distinct from f min / f max on purpose. Those set the band the transform
     is computed over: change them and the wavelet family, the frequency
     spacing and therefore the numbers all change. This crops what is drawn
     out of what was already computed -- the same analysis, the same values,
     a narrower view -- so you can look hard at 4-12 Hz without the result
     depending on the fact that you did.
     ====================================================================== */
  const FREQ_BANDS = [
    ['delta', 1, 4], ['theta', 4, 12], ['beta', 12, 30],
    ['gamma', 30, 100], ['ripple', 100, 250], ['all', null, null],
  ];

  function freqViewControl(index, pane, sess) {
    const res = pane._panelData || {};

    // Whether the vertical axis is frequency or channels is decided by the
    // pane's own settings, not by the last render. Reading it from the render
    // made the control one edit behind: you changed the band, the control was
    // rebuilt from the PREVIOUS response, and it grayed itself out.
    const tfN = (pane.tfChannels && pane.tfChannels.length)
      ? pane.tfChannels.length : 1;
    const mode = pane.tfMode || (tfN > 1 ? 'stack' : 'mean');
    const stacked = tfN > 1 && mode === 'stack';

    const computed = res.freqs_computed
      || [pane.fmin != null ? pane.fmin : 20, pane.fmax != null ? pane.fmax : 1000];

    // Rebuilding the strip here would replace the inputs while they are being
    // used: tabbing from one to the other fired the new field's onchange as
    // focus landed, which asked for another render, which rebuilt again --
    // one edit turning into a burst of identical requests. Only the panel is
    // refreshed; the control updates its own bits in place.
    const set = (lo, hi) => {
      if (pane.fviewMin === lo && pane.fviewMax === hi) return;
      pane.fviewMin = lo;
      pane.fviewMax = hi;
      BARRY.activity.log('freq.view',
                         { fmin: lo, fmax: hi, panel: pane.panel }, sess);
      refreshPane(index);
      syncFullButton();
    };

    const lo = el('input', {
      type: 'number', step: 'any', style: 'width:54px',
      value: pane.fviewMin != null ? String(pane.fviewMin) : '',
      placeholder: String(round(computed[0], 2)),
      title: 'Show from this frequency. Blank = from the bottom.',
      onchange: (e) => {
        const v = parseFloat(e.target.value);
        set(isFinite(v) ? v : null, pane.fviewMax);
      },
    });
    const hi = el('input', {
      type: 'number', step: 'any', style: 'width:58px',
      value: pane.fviewMax != null ? String(pane.fviewMax) : '',
      placeholder: String(round(computed[1], 2)),
      title: 'Show up to this frequency. Blank = to the top.',
      onchange: (e) => {
        const v = parseFloat(e.target.value);
        set(pane.fviewMin, isFinite(v) ? v : null);
      },
    });

    const fullBtn = el('button', {
      class: 'mini', text: 'full',
      title: 'Show the whole computed range again',
      onclick: () => { lo.value = ''; hi.value = ''; set(null, null); },
    });
    const syncFullButton = () => {
      const on = pane.fviewMin != null || pane.fviewMax != null;
      fullBtn.classList.toggle('hidden', !on);
    };
    syncFullButton();

    return el('div', { class: 'ctl freq-view' + (stacked ? ' off' : '') }, [
      el('label', {
        text: stacked ? 'Show Hz \u2014 stacked' : 'Show Hz',
        title: stacked
          ? 'This panel stacks one spectrogram per channel, so its vertical '
            + 'axis is channels, not frequency \u2014 there is '
            + 'nothing to crop. Set Combine to Average to get a frequency '
            + 'axis back.'
          : 'Crops the picture to this band. The transform is still computed '
            + 'over f min to f max \u2014 the numbers do not change.',
      }),
      el('div', { class: 'ctl-group' }, [
        lo,
        el('span', { class: 'hint', text: '\u2013' }),
        hi,
        el('select', {
          title: 'Common bands',
          onchange: (e) => {
            const b = FREQ_BANDS.find((x) => x[0] === e.target.value);
            if (b) set(b[1], b[2]);
          },
        }, [el('option', { value: '', text: 'band\u2026' })].concat(
          FREQ_BANDS.map(([name, a, b]) => el('option', {
            value: name,
            text: name + (a ? '  ' + a + '\u2013' + b : ''),
            selected: (pane.fviewMin === a && pane.fviewMax === b)
              ? 'selected' : null,
          })))),
        fullBtn,
      ]),
    ]);
  }

  /* ---------- pinned y-axis / color scale ---------- */
  function toggleScalePop(index, pane, sess) {
    const host = $('#paneGrid').children[index];
    if (!host) return;
    const existing = host.querySelector('.scale-pop');
    if (existing) { existing.remove(); return; }

    const isTraces = pane.panel === 'traces';
    const data = isTraces ? sess.win : pane._panelData;
    const auto = isTraces
      ? (data && data.robust_auto)
      : (data && data.clim_auto);

    const pop = el('div', { class: 'scale-pop' });
    pop.addEventListener('mousedown', (e) => e.stopPropagation());

    if (isTraces) {
      const cur = sess.ylim != null ? sess.ylim : (auto || 1);
      const input = el('input', { type: 'number', step: '10', value: String(round(cur, 3)) });
      pop.appendChild(el('h4', { text: 'Trace amplitude (µV)' }));
      pop.appendChild(el('div', {}, [
        el('label', { text: '± half-lane amplitude' }), input,
      ]));
      pop.appendChild(el('div', { class: 'acts' }, [
        el('button', {
          class: 'btn sm', text: 'Pin',
          onclick: () => {
            sess.ylim = Math.abs(parseFloat(input.value)) || null;
            BARRY.activity.log('ylim.change', { ylim: sess.ylim }, sess);
            queueSaveState(sess); pop.remove(); render(); refreshSession(sess);
          },
        }),
        el('button', {
          class: 'btn ghost sm', text: 'Auto',
          onclick: () => {
            sess.ylim = null;
            BARRY.activity.log('ylim.change', { ylim: null }, sess);
            queueSaveState(sess); pop.remove(); render(); refreshSession(sess);
          },
        }),
      ]));
      pop.appendChild(el('div', { class: 'hint',
        text: 'Auto uses the 99.5th percentile of this window, so amplitude '
              + 'changes as you scroll. Pinning keeps it comparable.'
              + (auto ? '  Auto here is ' + sig(auto) + ' µV.' : '') }));
    } else {
      const cur = pane.clim || sess.clim || auto || [-1, 1];
      const lo = el('input', { type: 'number', step: 'any', value: String(round(cur[0], 4)) });
      const hi = el('input', { type: 'number', step: 'any', value: String(round(cur[1], 4)) });
      pop.appendChild(el('h4', { text: 'Color scale'
        + (data && data.units ? ' (' + data.units + ')' : '') }));
      pop.appendChild(el('div', { class: 'row' }, [
        el('div', {}, [el('label', { text: 'min' }), lo]),
        el('div', {}, [el('label', { text: 'max' }), hi]),
      ]));
      pop.appendChild(el('div', { class: 'acts' }, [
        el('button', {
          class: 'btn sm', text: 'Pin',
          onclick: () => {
            const a = parseFloat(lo.value), b = parseFloat(hi.value);
            if (!isFinite(a) || !isFinite(b) || b <= a) {
              toast('Max must be greater than min.', 'err'); return;
            }
            pane.clim = [a, b];
            BARRY.activity.log('clim.change', { clim: pane.clim,
                                                panel: pane.panel }, sess);
            pop.remove(); render(); refreshPane(index);
          },
        }),
        el('button', {
          class: 'btn ghost sm', text: 'Auto',
          onclick: () => {
            pane.clim = null; sess.clim = null;
            BARRY.activity.log('clim.change', { clim: null,
                                                panel: pane.panel }, sess);
            pop.remove(); render(); refreshPane(index);
          },
        }),
        el('button', {
          class: 'btn ghost sm', text: 'Symmetric',
          title: 'Center the scale on zero using the larger limit',
          onclick: () => {
            const m = Math.max(Math.abs(parseFloat(lo.value) || 0),
                               Math.abs(parseFloat(hi.value) || 0)) || 1;
            lo.value = String(-m); hi.value = String(m);
          },
        }),
      ]));
      pop.appendChild(el('div', { class: 'hint',
        text: auto ? 'Auto is [' + sig(auto[0]) + ', ' + sig(auto[1])
                     + '] from the 99.5th percentile of this window.'
                   : 'Auto derives limits from each window.' }));
    }

    host.style.position = 'relative';
    host.appendChild(pop);
  }

  function popOut(pane, sess, opts) {
    const q = new URLSearchParams({
      csc: sess.path, t0: sess.t0.toFixed(4), span: sess.span.toFixed(4),
      panel: pane.panel, hp: sess.hp, lp: sess.lp, notch: sess.notch,
      theme: BARRY.state.theme,
      // Carry the scope across, or the new window would not be listening.
      link: XF.linkMode,
      // A pop-out is a second screen: it opens with the tab bar put away,
      // because there is only one recording in it.
      chrome: (opts && opts.chrome) || 'notabs',
    });
    if (opts && opts.full) q.set('full', '1');
    const w = window.open(location.origin + '/?' + q.toString() + '#xplore',
                          '_blank',
                          'width=1400,height=900,menubar=no,toolbar=no');
    if (!w) {
      toast('The pop-out was blocked. Allow pop-ups for 127.0.0.1 and try '
            + 'again.', 'err', 8000);
    }
    return w;
  }

  /* ==================================================================
     The pane control strip.

     Everything used to sit on one row: three window fields, seven move
     buttons, the scale, gain, three filter fields, a preset picker, the
     panel's own settings, the colormap, channel presets, read options,
     marks, spikes and two session buttons. That came to about 2500px inside
     a 900px pane, so most of it lived off the right-hand edge behind a
     scrollbar nobody thought to drag.

     What is on the strip now is what you touch while looking at the trace:
     the window, the scale, the gain. Everything else is behind a button that
     carries its own current value -- "Filter 1-70 Hz +60" rather than three
     empty-looking number boxes. Nothing is hidden; the settings are one click
     away and the strip still states them.
     ================================================================== */

  /* One popover at a time, so opening a second closes the first. */
  let openMenu = null;

  function closeMenu() {
    if (!openMenu) return;
    if (openMenu.button) openMenu.button.classList.remove('active');
    openMenu.node.remove();
    document.removeEventListener('mousedown', openMenu.away, true);
    document.removeEventListener('keydown', openMenu.esc, true);
    window.removeEventListener('resize', closeMenu);
    openMenu = null;
  }

  /* A button that opens a panel of controls.

     `build` runs on every open, so the panel reflects the session as it is
     now rather than as it was when the strip was drawn.

     The popover is fixed-positioned and parented to <body>, not to the strip:
     the strip is an overflow:auto scroller, so a child popover would be
     clipped by it and would slide away from its own button. */
  function menu(index, name, value, title, build) {
    const btn = el('button', {
      class: 'mini ctl-menu', title: title || '',
      'data-menu': name, 'data-pane': String(index),
      onclick: (e) => {
        e.stopPropagation();
        const wasMine = openMenu && openMenu.button === btn;
        closeMenu();
        if (wasMine) return;              // a second click closes it

        const node = el('div', { class: 'ctl-pop' }, [build()]);
        document.body.appendChild(node);
        btn.classList.add('active');

        const r = btn.getBoundingClientRect();
        const w = node.offsetWidth;
        node.style.left = Math.max(8, Math.min(
          r.left, window.innerWidth - w - 8)) + 'px';
        // Flip above the button when there is no room below it.
        const h = node.offsetHeight;
        node.style.top = (r.bottom + 6 + h > window.innerHeight && r.top > h + 12)
          ? (r.top - h - 6) + 'px'
          : (r.bottom + 6) + 'px';

        const away = (ev) => {
          if (!node.contains(ev.target) && !btn.contains(ev.target)) closeMenu();
        };
        const esc = (ev) => { if (ev.key === 'Escape') closeMenu(); };
        openMenu = { node, button: btn, away, esc };
        setTimeout(() => {
          document.addEventListener('mousedown', away, true);
          document.addEventListener('keydown', esc, true);
          window.addEventListener('resize', closeMenu);
        }, 0);
      },
    }, [
      el('span', { class: 'ctl-menu-label', text: name }),
      el('span', { class: 'ctl-menu-value', text: value || '' }),
      el('span', { class: 'ctl-menu-caret', text: '▾' }),
    ]);
    return el('div', { class: 'ctl' }, [btn]);
  }

  /* Update just the value on a menu button.

     The obvious thing is to call refreshControls() after changing a setting,
     which rebuilds the strip -- and that detaches the very button the open
     popover belongs to, leaving the popover floating with no owner and a
     second click on the new button opening a duplicate. Writing the one text
     node instead keeps the strip and the popover intact. */
  function relabelMenu(index, name, value) {
    const grid = $('#paneGrid');
    if (!grid) return;
    const box = grid.children[index];
    if (!box) return;
    const node = box.querySelector(
      '.ctl-menu[data-menu="' + name + '"] .ctl-menu-value');
    if (node) node.textContent = value || '';
  }

  function popRow(title, children) {
    const kids = children.filter(Boolean);
    if (!kids.length) return null;
    return el('div', { class: 'ctl-pop-group' }, [
      title ? el('div', { class: 'ctl-pop-title', text: title }) : null,
      el('div', { class: 'ctl-pop-row' }, kids),
    ].filter(Boolean));
  }

  function popBody(children) {
    return el('div', { class: 'ctl-pop-body' }, children.filter(Boolean));
  }

  const trimNum = (v) => String(Math.round(Number(v) * 100) / 100);

  /* How the filters read on the button: short enough for a strip, complete
     enough that nobody has to open it to check. */
  function filterWord(sess) {
    const bits = [];
    if (sess.hp && sess.lp) {
      bits.push(trimNum(sess.hp) + '–' + trimNum(sess.lp) + ' Hz');
    } else if (sess.lp) bits.push('≤' + trimNum(sess.lp) + ' Hz');
    else if (sess.hp) bits.push('≥' + trimNum(sess.hp) + ' Hz');
    if (sess.notch) bits.push('+' + trimNum(sess.notch));
    return bits.length ? bits.join(' ') : 'off';
  }

  function ctlNum(label, value, step, onchange, title, width) {
    return el('div', { class: 'ctl' }, [
      el('label', { text: label, title: title || '' }),
      el('input', {
        type: 'number', value: String(value), step: String(step),
        title: title || '', style: width ? 'width:' + width : null,
        onchange: (e) => onchange(parseFloat(e.target.value)),
      }),
    ]);
  }

  /* ---------- per-pane controls ---------- */
  function paneControls(index, pane, sess) {
    const host = el('div', { class: 'pane-ctl' });
    const dur = sess.info.duration_s || 0;
    const num = ctlNum;
    const W = winOf(pane, sess);

    host.appendChild(num('Start s', round(W.t0, 4), 0.1, (v) => {
      setWindow(index, isFinite(v) ? v : 0, W.span);
    }, 'Left edge of the window, in seconds'));

    host.appendChild(num('Span s', round(W.span, 4), 0.1, (v) => {
      setWindow(index, W.t0, isFinite(v) ? v : 10);
    }, 'Width of the visible window, in seconds'));

    host.appendChild(el('div', { class: 'ctl' }, [
      el('label', { text: 'Move' }),
      el('div', { class: 'ctl-group' }, [
        el('button', { class: 'mini', text: '◀',
                       title: 'Back half a window',
                       onclick: () => pan(index, -0.5) }),
        el('button', { class: 'mini', text: '▶',
                       title: 'Forward half a window',
                       onclick: () => pan(index, 0.5) }),
        el('button', { class: 'mini', text: '−', title: 'Zoom out',
                       onclick: () => zoom(index, 1.6) }),
        el('button', { class: 'mini', text: '+', title: 'Zoom in',
                       onclick: () => zoom(index, 1 / 1.6) }),
        // Jump-to-start and jump-to-end used to sit here too. They are
        // one-click shortcuts for something Fit and the minimap already do,
        // and two more buttons cost more strip than they were worth, so they
        // moved into More.
        el('button', { class: 'mini', text: 'Fit', title: 'Whole recording',
                       onclick: () => setWindow(index, 0, dur || 10) }),
      ]),
    ]));

    host.appendChild(scaleControl(index, pane, sess));

    if (pane.panel === 'traces') {
      host.appendChild(el('div', { class: 'ctl' }, [
        el('label', { text: 'Gain' }),
        el('div', { class: 'ctl-group' }, [
          el('button', { class: 'mini', text: '−',
                         onclick: () => { sess.gain = clamp(sess.gain / 1.5, .02, 200); drawPane(index); refreshControls(index); } }),
          el('input', {
            type: 'number', value: String(round(sess.gain, 3)), step: '0.1', style: 'width:56px',
            onchange: (e) => { sess.gain = clamp(parseFloat(e.target.value) || 1, .02, 200); drawPane(index); },
          }),
          el('button', { class: 'mini', text: '+',
                         onclick: () => { sess.gain = clamp(sess.gain * 1.5, .02, 200); drawPane(index); refreshControls(index); } }),
        ]),
      ]));
    }

    host.appendChild(el('div', { class: 'ctl-sep' }));

    host.appendChild(menu(index, 'Filter', filterWord(sess),
      'High-pass, low-pass and notch, plus saved presets',
      () => filterPop(index, sess)));

    if (panelHasOptions(pane)) {
      host.appendChild(menu(index, 'Panel', panelWord(pane, sess),
        'Settings for this panel type', () => panelPop(index, pane, sess)));
    }

    if (pane.panel === 'traces') {
      host.appendChild(menu(index, 'Ch',
        sess.sel.size + '/' + sess.info.channels.length,
        'Which channels are drawn', () => channelPop(index, sess)));
    }

    host.appendChild(el('div', { class: 'ctl-sep' }));

    const marks = markCounts(sess);
    host.appendChild(menu(index, 'Marks',
      marks.total ? String(marks.total) : 'none',
      marks.total
        ? [marks.bookmark + ' bookmark(s)', marks.event + ' event(s)',
           marks.spike + ' spike(s)',
           marks.draft ? marks.draft + ' draft' : null]
          .filter(Boolean).join(', ')
        : 'Bookmarks, events and spikes appear here',
      () => marksPop(index, sess)));

    host.appendChild(el('div', { class: 'ctl-spacer' }));

    host.appendChild(menu(index, 'More', null,
      'Events, spikes, read options, and this recording on disk',
      () => morePop(index, pane, sess)));

    return host;
  }

  /* ---------- what the menu buttons open ---------- */

  function filterPop(index, sess) {
    const bump = (via) => {
      BARRY.activity.log('filter.change', {
        highpass: sess.hp, lowpass: sess.lp, notch: sess.notch, via,
      }, sess);
      queueSaveState(sess);
      refreshSession(sess);
      relabelMenu(index, 'Filter', filterWord(sess));
      publishLink(sess.t0, sess.span, sess);
    };
    return popBody([
      popRow('Corners, Hz  (0 = off)', [
        ctlNum('High-pass', sess.hp, 0.5, (v) => {
          sess.hp = Math.max(0, isFinite(v) ? v : 0); bump('manual');
        }, 'Everything below this is removed', '68px'),
        ctlNum('Low-pass', sess.lp, 5, (v) => {
          sess.lp = Math.max(0, isFinite(v) ? v : 0); bump('manual');
        }, 'Everything above this is removed', '68px'),
        ctlNum('Notch', sess.notch, 10, (v) => {
          sess.notch = Math.max(0, isFinite(v) ? v : 0); bump('manual');
        }, 'Mains hum, usually 60 Hz here', '68px'),
      ]),
      popRow('Presets', [
        el('select', {
          onchange: (e) => {
            const pr = XF.presets.filters.find((x) => x.id === e.target.value);
            if (pr) {
              sess.hp = +pr.highpass || 0;
              sess.lp = +pr.lowpass || 0;
              sess.notch = +pr.notch || 0;
              bump(pr.name);
              closeMenu();
            }
            e.target.value = '';
          },
        }, [el('option', { value: '', text: 'apply…' })].concat(
          XF.presets.filters.map((pr) => el('option', {
            value: pr.id,
            text: (pr.label || pr.name) + (pr.builtin ? '' : ' *'),
            title: pr.note || '',
          })))),
        el('button', {
          class: 'mini', text: 'Save these…',
          title: 'Save the current corners as a named preset',
          onclick: () => { closeMenu(); saveFilterPreset(sess); },
        }),
        el('button', {
          class: 'mini', text: 'Clear',
          title: 'Turn every filter off',
          onclick: () => {
            sess.hp = 0; sess.lp = 0; sess.notch = 0;
            bump('cleared');
            closeMenu();
          },
        }),
      ]),
    ]);
  }

  function panelHasOptions(pane) {
    return pane.panel === 'csd' || pane.panel === 'spectrogram'
        || pane.panel === 'scalogram' || isImagePanel(pane.panel);
  }

  /* The button's own label: the setting most likely to be wrong. */
  function panelWord(pane, sess) {
    if (pane.panel === 'spectrogram' || pane.panel === 'scalogram') {
      const n = (pane.tfChannels && pane.tfChannels.length) || 1;
      const band = trimNum(pane.fmin != null ? pane.fmin : 20) + '–'
                 + trimNum(pane.fmax != null ? pane.fmax : 1000);
      return n > 1 ? n + ' ch  ' + band : band;
    }
    if (pane.panel === 'csd') return trimNum(sess.spacing) + ' µm';
    return pane.cmap || 'jet';
  }

  function panelPop(index, pane, sess) {
    const rows = [];

    if (pane.panel === 'csd') {
      rows.push(popRow('Geometry', [
        ctlNum('Spacing µm', sess.spacing, 5, (v) => {
          sess.spacing = Math.max(1, isFinite(v) ? v : 50);
          refreshPane(index);
          relabelMenu(index, 'Panel', panelWord(pane, sess));
        }, 'Electrode spacing for the CSD second derivative', '72px'),
      ]));
    }

    if (pane.panel === 'spectrogram' || pane.panel === 'scalogram') {
      const multi = !!(pane.tfChannels && pane.tfChannels.length > 1);
      rows.push(popRow('Channels', [
        multi
          ? el('button', {
              class: 'mini', text: pane.tfChannels.length + ' selected',
              title: pane.tfChannels
                .map((i) => (sess.info.channels[i] || {}).label).join(', '),
              onclick: () => { closeMenu(); openTfPicker(index, pane, sess); },
            })
          : el('select', {
              onchange: (e) => {
                pane.channel = +e.target.value;
                pane.tfChannels = [pane.channel];
                BARRY.activity.log('channels.change',
                  { panel: pane.panel, channel: pane.channel }, sess);
                refreshPane(index);
                relabelMenu(index, 'Panel', panelWord(pane, sess));
              },
            }, sess.info.channels.map((c) => el('option', {
              value: String(c.index), text: c.label,
              selected: String(pane.channel != null ? pane.channel : firstSel(sess))
                        === String(c.index) ? 'selected' : null,
            }))),
        el('button', {
          class: 'mini', text: multi ? 'edit…' : 'pick several…',
          title: 'Use several channels for this panel',
          onclick: () => { closeMenu(); openTfPicker(index, pane, sess); },
        }),
        el('div', { class: 'ctl' }, [
          el('label', { text: 'Combine' }),
          el('select', {
            disabled: multi ? null : 'disabled',
            title: multi
              ? 'Average the channels, or stack one spectrogram per channel'
              : 'Only matters with more than one channel',
            onchange: (e) => {
              pane.tfMode = e.target.value;
              BARRY.activity.log('channels.change',
                { panel: pane.panel, mode: pane.tfMode }, sess);
              refreshPane(index);
              relabelMenu(index, 'Panel', panelWord(pane, sess));
            },
          }, [
            el('option', { value: 'stack', text: 'Stack per channel',
              selected: (pane.tfMode || 'stack') === 'stack' ? 'selected' : null }),
            el('option', { value: 'mean', text: 'Average channels',
              selected: pane.tfMode === 'mean' ? 'selected' : null }),
          ]),
        ]),
      ]));

      rows.push(popRow('Analyzed frequency range, Hz', [
        ctlNum('f min', pane.fmin != null ? pane.fmin : 20, 5, (v) => {
          pane.fmin = Math.max(0.1, v || 20);
          refreshPane(index);
          relabelMenu(index, 'Panel', panelWord(pane, sess));
        }, 'Lowest frequency the transform is COMPUTED over, Hz. '
         + 'Changing this changes the analysis.', '64px'),
        ctlNum('f max', pane.fmax != null ? pane.fmax : 1000, 50, (v) => {
          pane.fmax = Math.max(1, v || 1000);
          refreshPane(index);
          relabelMenu(index, 'Panel', panelWord(pane, sess));
        }, 'Highest frequency the transform is COMPUTED over, Hz. '
         + 'Changing this changes the analysis.', '64px'),
      ]));

      rows.push(popRow(null, [freqViewControl(index, pane, sess)]));
    }

    if (isImagePanel(pane.panel)) {
      rows.push(popRow('Colormap', [
        el('select', {
          onchange: (e) => {
            pane.cmap = e.target.value;
            BARRY.activity.log('colormap.change',
                               { cmap: pane.cmap, panel: pane.panel }, sess);
            refreshPane(index);
            relabelMenu(index, 'Panel', panelWord(pane, sess));
          },
        }, XF.colormaps.map((c) => el('option', {
          value: c.id, text: c.name, title: c.note || '',
          selected: (pane.cmap || 'jet') === c.id ? 'selected' : null,
        }))),
      ]));
    }

    return popBody(rows);
  }

  function channelPop(index, sess) {
    return popBody([
      popRow(sess.sel.size + ' of ' + sess.info.channels.length + ' drawn', [
        el('div', { class: 'ctl-group' },
          [['all', 'All'], ['none', 'None'], ['even', 'Even'],
           ['odd', 'Odd'], ['invert', 'Flip'], ['good', 'Good']].map(
            ([k, label]) => el('button', {
              class: 'mini', text: label,
              title: k === 'good' ? 'Only channels not marked bad' : '',
              onclick: () => {
                quickSelect(sess, k);
                BARRY.activity.log('channels.change',
                  { preset: k, n: sess.sel.size }, sess);
                closeMenu();
                render(); refreshSession(sess);
                queueSaveState(sess);
                publishLink(sess.t0, sess.span, sess);
              },
            }))),
      ]),
      el('p', { class: 'ctl-pop-note',
        text: 'Individual channels are toggled on the list beside the '
            + 'trace; a bad channel is marked there too.' }),
    ]);
  }

  function marksPop(index, sess) {
    const marks = markCounts(sess);
    return popBody([
      popRow(marks.total
        ? [marks.bookmark + ' bookmark(s)', marks.event + ' event(s)',
           marks.spike + ' spike(s)',
           marks.draft ? marks.draft + ' draft' : null]
          .filter(Boolean).join(' · ')
        : 'No marks on this recording yet', [
        el('button', {
          class: 'mini', text: 'Browse…',
          title: 'Every mark on this recording — click one to jump there',
          onclick: () => { closeMenu(); openMarks(index, sess); },
        }),
        el('button', {
          class: 'mini' + (XF.placing ? ' active' : ''),
          text: XF.placing ? 'click a spot' : 'Add a bookmark',
          title: 'Arm placement, then click the exact spot you want',
          onclick: () => { closeMenu(); setPlacing(!XF.placing); },
        }),
      ]),
    ]);
  }

  function morePop(index, pane, sess) {
    const rows = [];

    rows.push(popRow(sess.events.length
      ? 'Events \u2014 ' + sess.events.length + ' loaded'
      : 'Events \u2014 none loaded', [
      el('button', {
        class: 'mini', text: 'Classes\u2026',
        title: 'Names, colors and visibility for each kind of event',
        onclick: () => { closeMenu(); openEvents(index, sess); },
      }),
      el('button', {
        class: 'mini', text: 'Import\u2026',
        title: 'Bring events in, from the Event Bank or from a file',
        onclick: () => { closeMenu(); chooseImport(index, sess); },
      }),
      el('button', {
        class: 'mini', text: 'Export\u2026',
        title: 'Send events out, to the Event Bank or to a file',
        onclick: () => { closeMenu(); chooseExport(index, sess); },
      }),
    ]));

    rows.push(popRow(sess.spikeDraft
      ? 'Spikes \u2014 ' + sess.spikeDraft.events.length + ' in a draft'
      : (sess.spikeSets.length
         ? 'Spikes \u2014 ' + sess.spikeSets.length + ' set(s)'
         : 'Spikes \u2014 none detected yet'), [
      el('button', {
        class: 'mini' + (sess.spikeDraft ? ' draft-chip' : ''),
        text: 'Threshold detector\u2026',
        title: 'Threshold spike labeling',
        onclick: () => { closeMenu(); openSpikes(index, sess); },
      }),
    ]));

    // Neuralynx polarity is inverted by lab convention, and the probe sits on
    // the even channels -- but both need to be switchable.
    if (sess.info.source === 'ncs') {
      rows.push(popRow('Read as', [
        el('label', {
          class: 'toggle sm' + (sess.invert ? ' on' : ''),
          title: 'Lab convention: raw Neuralynx polarity is flipped',
        }, [
          el('input', {
            type: 'checkbox', checked: sess.invert ? 'checked' : null,
            onchange: (e) => {
              sess.invert = e.target.checked;
              BARRY.activity.log('read.invert', { invert: sess.invert }, sess);
              closeMenu();
              reopenSameView(sess);
            },
          }),
          el('span', { text: 'Invert polarity' }),
        ]),
        el('label', {
          class: 'toggle sm' + (sess.evenOnly ? ' on' : ''),
          title: 'Probe channels are the even CSC numbers',
        }, [
          el('input', {
            type: 'checkbox', checked: sess.evenOnly ? 'checked' : null,
            onchange: (e) => {
              sess.evenOnly = e.target.checked;
              BARRY.activity.log('read.evenOnly',
                                 { evenOnly: sess.evenOnly }, sess);
              closeMenu();
              reopenSameView(sess);
            },
          }),
          el('span', { text: 'Even channels only' }),
        ]),
      ]));
      rows.push(el('p', { class: 'ctl-pop-note',
        text: 'Either of these reopens the recording, because both change '
            + 'what gets read off disk.' }));
    }

    rows.push(popRow('Jump', [
      el('button', {
        class: 'mini', text: '⏮  To the start',
        onclick: () => {
          const span = winOf(pane, sess).span;
          closeMenu();
          setWindow(index, 0, span);
        },
      }),
      el('button', {
        class: 'mini', text: '⏭  To the end',
        onclick: () => {
          const span = winOf(pane, sess).span;
          closeMenu();
          setWindow(index, Math.max(0, (sess.info.duration_s || 0) - span),
                    span);
        },
      }),
    ]));

    rows.push(popRow('This recording', [
      el('button', {
        class: 'mini', text: 'Show in folder',
        onclick: () => {
          closeMenu();
          apiPost('/api/reveal', { path: sess.path }).catch(() => {});
        },
      }),
      el('button', {
        class: 'mini', text: 'Figure builder…',
        title: 'Open the figure builder with this session',
        onclick: () => { closeMenu(); BARRY.figure.open(XF, sess); },
      }),
    ]));

    return popBody(rows);
  }

  function openTfPicker(index, pane, sess) {
    const chosen = new Set(
      (pane.tfChannels && pane.tfChannels.length)
        ? pane.tfChannels
        : [pane.channel != null ? pane.channel : firstSel(sess)]);

    const build = () => {
      const list = el('div', {
        style: 'display:grid;grid-template-columns:repeat(auto-fill,minmax(88px,1fr));'
             + 'gap:4px;max-height:340px;overflow-y:auto',
      });
      for (const c of sess.info.channels) {
        const bad = sess.bad.has(c.number) || c.bad;
        list.appendChild(el('label', {
          class: 'ch-row' + (bad ? ' marked-bad' : ''),
          style: 'padding:3px 6px',
        }, [
          el('input', {
            type: 'checkbox', checked: chosen.has(c.index) ? 'checked' : null,
            onchange: (e) => {
              if (e.target.checked) chosen.add(c.index); else chosen.delete(c.index);
              count.textContent = chosen.size + ' selected';
            },
          }),
          el('span', { text: c.label }),
        ]));
      }
      return list;
    };

    /* Every Nth electrode down the shank, skipping ones marked bad so a dead
       channel does not silently shift the spacing. */
    const stride = (n) => {
      chosen.clear();
      const good = sess.info.channels.filter(
        (c) => !sess.bad.has(c.number) && !c.bad);
      good.forEach((c, i) => { if (i % n === 0) chosen.add(c.index); });
    };

    /* Parity of the CSC number itself -- on this rig the probe sits on the
       even channels, so "odd" is usually the reference set. */
    const parity = (want) => {
      chosen.clear();
      sess.info.channels.forEach((c) => {
        if (c.number % 2 === want) chosen.add(c.index);
      });
    };

    const count = el('span', { class: 'stat-chip', text: chosen.size + ' selected' });
    let listNode = build();

    const quick = (label, fn) => el('button', {
      class: 'mini', text: label,
      onclick: () => {
        fn();
        const fresh = build();
        listNode.replaceWith(fresh);
        listNode = fresh;
        count.textContent = chosen.size + ' selected';
      },
    });

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Channels for this ' + pane.panel }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'fb-stats', style: 'margin-bottom:10px' }, [
          count,
          quick('All', () => sess.info.channels.forEach((c) => chosen.add(c.index))),
          quick('None', () => chosen.clear()),
          quick('Every 2', () => stride(2)),
          quick('Every 4', () => stride(4)),
          quick('Every 8', () => stride(8)),
          quick('Odd', () => parity(1)),
          quick('Even', () => parity(0)),
          quick('Session selection', () => {
            chosen.clear(); sess.sel.forEach((i) => chosen.add(i));
          }),
          quick('Good only', () => {
            chosen.clear();
            sess.info.channels.forEach((c) => {
              if (!sess.bad.has(c.number) && !c.bad) chosen.add(c.index);
            });
          }),
        ]),
        listNode,
        el('p', { style: 'margin-top:10px;font-size:11.5px;color:var(--text-3);line-height:1.6',
          text: 'Average pools power across the chosen channels, which pulls a weak '
              + 'rhythm out of the noise. Stack draws one spectrogram per channel, so '
              + 'laminar differences stay visible.' }),
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        el('button', {
          class: 'btn', text: 'Use these',
          onclick: () => {
            const arr = Array.from(chosen).sort((a, b) => a - b);
            if (!arr.length) { toast('Pick at least one channel.', 'err'); return; }
            pane.tfChannels = arr;
            pane.channel = arr[0];
            // Choosing several channels means "show me these", so stack them.
            // Averaging is a deliberate choice, not a default.
            if (arr.length > 1 && !pane.tfMode) pane.tfMode = 'stack';
            BARRY.activity.log('channels.change', {
              panel: pane.panel, n: arr.length, mode: pane.tfMode || 'mean',
            }, sess);
            closeModal(); render(); refreshPane(index);
          },
        }),
      ]),
    ]));
  }

  /* ---------- bookmarks ---------- */
  /* ======================================================================
     Placing a bookmark

     "+ add" used to drop the bookmark in the middle of the window, which is
     almost never where the thing you wanted to mark actually is. Now it arms
     placement: a faint line follows the pointer with the time it would land
     on, and a click puts it there. Escape backs out.
     ====================================================================== */
  function setPlacing(on) {
    XF.placing = !!on;
    if (!XF.placing) {
      for (const pane of XF.panes) if (pane) clearGhost(pane);
    }
    render();
    if (XF.placing) {
      toast('Click where the bookmark goes. Escape to cancel.', null, 4000);
    }
  }

  /* Where in the window a pointer x lands, for either kind of pane. A trace
     pane reserves a left gutter for the channel rows; an image pane does not. */
  function timeAtPointer(pane, sess, host, clientX) {
    const rect = host.getBoundingClientRect();
    const isTrace = pane.panel === 'traces';
    const left = isTrace ? PAD_TRACES_L : 0;
    const right = isTrace ? PAD.r : 0;
    const plotW = Math.max(1, rect.width - left - right);
    const frac = clamp((clientX - rect.left - left) / plotW, 0, 1);
    const w = winOf(pane, sess);
    return { t: w.t0 + frac * w.span, x: left + frac * plotW, inside:
             clientX - rect.left >= left && clientX - rect.left <= left + plotW };
  }

  function showGhost(pane, host, x, t) {
    if (!pane._ghost) {
      pane._ghost = el('div', { class: 'bm-ghost' },
                       [el('span', { class: 'lbl' })]);
      host.appendChild(pane._ghost);
    }
    pane._ghost.style.left = x + 'px';
    pane._ghost.querySelector('.lbl').textContent = fmtTime(t);
  }

  function clearGhost(pane) {
    if (pane && pane._ghost) { pane._ghost.remove(); pane._ghost = null; }
  }

  /* Wired for both pane types; `host` is whichever element holds the plot. */
  function wirePlacement(index, pane, sess, host) {
    const move = (e) => {
      if (!XF.placing) { clearGhost(pane); return; }
      const g = timeAtPointer(pane, sess, host, e.clientX);
      if (!g.inside) { clearGhost(pane); return; }
      showGhost(pane, host, g.x, g.t);
    };
    const down = (e) => {
      if (!XF.placing || e.button !== 0) return;
      const g = timeAtPointer(pane, sess, host, e.clientX);
      if (!g.inside) return;
      e.preventDefault();
      e.stopPropagation();
      clearGhost(pane);
      XF.placing = false;
      render();
      addBookmark(index, sess, g.t);
    };
    host.addEventListener('mousemove', move);
    host.addEventListener('mousedown', down, true);
    host.addEventListener('mouseleave', () => clearGhost(pane));
    (pane._teardown = pane._teardown || []).push(() => {
      host.removeEventListener('mousemove', move);
      host.removeEventListener('mousedown', down, true);
      clearGhost(pane);
    });
  }

  async function addBookmark(index, sess, tOverride, nameOverride) {
    const pane = XF.panes[index];
    const w = winOf(pane, sess);
    const t = tOverride != null ? tOverride : w.t0 + w.span / 2;
    const name = nameOverride || await askPath(
      'Name this bookmark', 'e.g. "first clean IED" or "CNO onset"');
    if (!name) return;

    if (!sess.identity || (sess.identity.mouse == null && !sess.identity.key)) {
      sess.bookmarks.push({ id: 'local' + Date.now(), t, name, local: true });
      render();
      toast('Bookmarked locally -- this recording has no detectable id, so it '
            + 'cannot be saved across machines.', 'err', 7000);
      return;
    }
    try {
      const res = await apiPost('/api/session/bookmarks', {
        identity: sess.identity,
        bookmark: { t, name, span: w.span },
      });
      sess.bookmarks = res.bookmarks || [];
      BARRY.activity.log('bookmark.add', { name, t: round(t, 4) }, sess);
      render();
      refreshSession(sess);
      toast('Bookmarked "' + name + '" at ' + fmtTime(t), 'ok');
      BARRY.refreshSync();
    } catch (e) {
      toast(e.message, 'err');
    }
  }

  /* ======================================================================
     Marks -- bookmarks, events and spikes in one list

     These are three different things with one thing in common: each is a time
     in this recording worth going back to. Keeping them in separate panels
     meant knowing which kind you were looking for before you could look for
     it. Click any row to jump there.
     ====================================================================== */
  const MARK_KINDS = {
    bookmark: { label: 'Bookmarks', chip: 'bookmark' },
    event: { label: 'Events', chip: 'event' },
    spike: { label: 'Spikes', chip: 'spike' },
    draft: { label: 'Draft spikes', chip: 'draft' },
  };

  /* Every navigable time in the session, newest scheme first, sorted by time.
     `ref` is the underlying object so a row can act on it. */
  function allMarks(sess) {
    const P = palette();
    const out = [];

    for (const bm of (sess.bookmarks || [])) {
      out.push({
        kind: 'bookmark', t: bm.t, span: bm.span || null,
        name: bm.name || 'bookmark',
        detail: bm.local ? 'not saved -- this recording has no detectable id' : '',
        color: P.accent, ref: bm,
      });
    }

    const classes = eventClasses(sess);
    for (const ev of (sess.events || [])) {
      const key = classKeyOf(ev);
      const cls = classes[key] || {};
      out.push({
        kind: 'event', t: ev.start,
        span: ev.end && ev.end > ev.start ? (ev.end - ev.start) * 3 : null,
        name: cls.name || key,
        detail: (ev.end && ev.end > ev.start
                 ? ((ev.end - ev.start) * 1000).toFixed(1) + ' ms' : '')
                + (ev.channel != null ? '  CSC' + ev.channel : ''),
        color: eventColor(sess, ev, P),
        hidden: !eventVisible(sess, ev),
        ref: ev,
      });
    }

    for (const st of (sess.spikeSets || [])) {
      for (const ev of (st.events || [])) {
        out.push({
          kind: 'spike', t: ev.start, span: null,
          name: st.name || 'spikes',
          detail: (ev.channel != null ? 'CSC' + ev.channel : '')
                  + (ev.amplitude != null
                     ? '  ' + Math.round(ev.amplitude) + ' uV' : '')
                  + (ev.n_channels > 1 ? '  x' + ev.n_channels + ' ch' : ''),
          color: P.accent, ref: ev, set: st,
        });
      }
    }

    if (sess.spikeDraft) {
      for (const ev of (sess.spikeDraft.events || [])) {
        out.push({
          kind: 'draft', t: ev.start, span: null, name: 'uncommitted',
          detail: (ev.channel != null ? 'CSC' + ev.channel : '')
                  + (ev.amplitude != null
                     ? '  ' + Math.round(ev.amplitude) + ' uV' : ''),
          color: P.warn, ref: ev,
        });
      }
    }

    out.sort((a, b) => a.t - b.t);
    return out;
  }

  function markCounts(sess) {
    const c = { bookmark: 0, event: 0, spike: 0, draft: 0, total: 0 };
    for (const m of allMarks(sess)) { c[m.kind] += 1; c.total += 1; }
    return c;
  }

  /* How far to zoom when jumping to a mark. A bookmark remembers the window
     it was made at; anything else keeps the window you are already using, so
     jumping does not silently change your scale. */
  function gotoMark(index, sess, m) {
    const w = winOf(XF.panes[index], sess);
    const span = m.span || w.span;
    setWindow(index, m.t - span / 2, span);
    BARRY.activity.log('mark.goto',
                       { kind: m.kind, name: m.name, t: round(m.t, 4) }, sess);
  }

  let markFilter = 'all';
  let markQuery = '';

  function openMarks(index, sess) {
    const MAX_ROWS = 400;

    const body = el('div');
    const draw = () => {
      body.innerHTML = '';
      const all = allMarks(sess);
      const counts = markCounts(sess);
      const q = markQuery.trim().toLowerCase();

      const list = all.filter((m) => {
        if (markFilter !== 'all' && m.kind !== markFilter) return false;
        if (!q) return true;
        return (m.name + ' ' + m.detail + ' ' + fmtTime(m.t))
          .toLowerCase().includes(q);
      });

      // ---- filters ----
      const pills = el('div', { class: 'filter-row' });
      const pill = (key, label, n) => el('button', {
        class: 'pill' + (markFilter === key ? ' active' : ''),
        text: label + (n != null ? ' (' + n + ')' : ''),
        disabled: n === 0 ? 'disabled' : null,
        onclick: () => { markFilter = key; draw(); },
      });
      pills.appendChild(pill('all', 'All', counts.total));
      pills.appendChild(pill('bookmark', 'Bookmarks', counts.bookmark));
      pills.appendChild(pill('event', 'Events', counts.event));
      pills.appendChild(pill('spike', 'Spikes', counts.spike));
      if (counts.draft) pills.appendChild(pill('draft', 'Draft', counts.draft));
      body.appendChild(pills);

      body.appendChild(el('div', { class: 'search-wrap inline',
                                   style: 'margin:8px 0' }, [
        el('svg', { class: 'search-icon', viewBox: '0 0 20 20',
                    html: '<circle cx="9" cy="9" r="6"/><path d="m14 14 4 4"/>' }),
        el('input', {
          type: 'search', value: markQuery,
          placeholder: 'Filter by name, channel or time\u2026',
          oninput: (e) => { markQuery = e.target.value; draw(); },
        }),
      ]));

      // ---- rows ----
      const rows = el('div', { class: 'bm-list tall' });
      if (!list.length) {
        rows.appendChild(el('div', { class: 'tree-empty', text: all.length
          ? 'Nothing matches that filter.'
          : 'No bookmarks, events or spikes in this session yet.' }));
      }

      for (const m of list.slice(0, MAX_ROWS)) {
        rows.appendChild(el('div', {
          class: 'bm-row' + (m.hidden ? ' dim' : ''),
          title: 'Jump to ' + fmtTime(m.t),
          onclick: () => { gotoMark(index, sess, m); closeModal(); },
        }, [
          el('span', { class: 'mk-dot', style: 'background:' + m.color }),
          el('span', { class: 't', text: fmtTime(m.t) }),
          el('span', { class: 'mk-name', text: m.name }),
          el('span', { class: 'mk-detail', text: m.detail || '' }),
          m.hidden ? el('span', { class: 'flagchip', text: 'hidden' }) : null,
          el('span', { class: 'mk-kind', text: m.kind }),
          m.kind === 'bookmark'
            ? el('span', {
                class: 'x', text: '✕', title: 'Delete this bookmark',
                onclick: (e) => { e.stopPropagation(); dropBookmark(index, sess, m.ref); },
              })
            : el('span', { class: 'x', style: 'visibility:hidden', text: '✕' }),
        ]));
      }

      if (list.length > MAX_ROWS) {
        rows.appendChild(el('div', { class: 'hint', style: 'padding:6px 8px',
          text: 'Showing the first ' + MAX_ROWS + ' of ' + list.length
              + '. Narrow it with the filter above, or step through with '
              + 'n / p in the viewer.' }));
      }
      body.appendChild(rows);
    };

    draw();
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Marks' }),
        el('span', { class: 'sub',
                     text: sess.identity.label || sess.info.name }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [body]),
      el('div', { class: 'mf' }, [
        el('button', { class: 'btn ghost sm', text: 'Bookmark current window',
          onclick: () => { closeModal(); addBookmark(index, sess); } }),
        el('span', { class: 'hint',
          text: 'Click a row to jump there. n / p step through them in the '
              + 'viewer.' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn', text: 'Close', onclick: closeModal }),
      ]),
    ]));
  }

  async function dropBookmark(index, sess, bm) {
    if (bm.local) {
      sess.bookmarks = sess.bookmarks.filter((x) => x.id !== bm.id);
    } else {
      try {
        const res = await api('/api/session/bookmarks', {
          method: 'DELETE',
          body: JSON.stringify({ identity: sess.identity, id: bm.id }),
        });
        sess.bookmarks = res.bookmarks || [];
      } catch (err) { toast(err.message, 'err'); return; }
    }
    BARRY.activity.log('bookmark.delete', { name: bm.name }, sess);
    render();
    refreshSession(sess);
    openMarks(index, sess);
  }

  /* ======================================================================
     The event bank

     Banking is the point at which a set of event times stops being a file on
     somebody's drive and becomes a record. So the dialog insists on the two
     things that make it one: who is adding it, and what produced it. Neither
     is guessable, and an entry that cannot answer them is not evidence.
     ====================================================================== */
  function bankableSets(sess) {
    const out = [];
    if ((sess.events || []).length) {
      // Split by class, so "TTL 1" and a detector's output do not get banked
      // as one undifferentiated pile.
      const classes = ensureClasses(sess);
      const byKey = {};
      for (const ev of sess.events) {
        const k = classKeyOf(ev);
        (byKey[k] = byKey[k] || []).push(ev);
      }
      for (const [k, list] of Object.entries(byKey)) {
        const cls = classes[k] || {};
        out.push({
          key: 'events:' + k,
          label: (cls.name || k) + '  (' + list.length + ' loaded events)',
          events: list,
          suggestName: cls.name || k,
          pipeline: (sess.eventsMeta && sess.eventsMeta.file)
            || (list[0] && list[0].source) || '',
        });
      }
    }
    for (const st of (sess.spikeSets || [])) {
      out.push({
        key: 'spikes:' + st.id,
        label: st.name + '  (' + (st.events || []).length + ' committed spikes)',
        events: st.events || [],
        suggestName: st.name,
        pipeline: 'BARRY threshold detector',
        parameters: st.params || {},
        detector: 'threshold',
      });
    }
    if (sess.spikeDraft && (sess.spikeDraft.events || []).length) {
      out.push({
        key: 'draft',
        label: 'Uncommitted draft  (' + sess.spikeDraft.events.length + ')',
        events: sess.spikeDraft.events,
        suggestName: 'threshold draft',
        pipeline: 'BARRY threshold detector',
        parameters: sess.spikeDraft.params || {},
        detector: 'threshold',
        draft: true,
      });
    }
    return out;
  }

  /* ======================================================================
     Banking

     Several sets can be banked in one action, and each becomes its own entry
     -- an IED run and a ripple run share a recording but not a type or a
     source, and merging them would lose both.

     What they DO share is the filing and the provenance, so those are asked
     once. The two required facts have no default: an entry that cannot say
     who added it and what produced it is not evidence.
     ====================================================================== */
  async function openBank(index, sess, sets) {
    sets = (sets || []).filter((x) => (x.events || []).length);
    if (!sets.length) {
      toast('Nothing to bank.', 'err');
      return;
    }

    let types = [];
    let me = '';
    try {
      const d = await api('/api/bank');
      types = d.types || [];
      me = d.user || '';
    } catch (e) { /* the dialog still works without the menu */ }

    const id = sess.identity || {};
    const typeOptions = types.length ? types
      : [{ id: 'other', name: 'Other', note: '' }];

    // Shared filing.
    const projIn = el('input', { type: 'text', value: id.group || '',
                                 placeholder: 'e.g. PTEN, KCNT1' });
    const mouseIn = el('input', { type: 'text',
      value: id.mouse != null ? String(id.mouse) : '' });
    const sessIn = el('input', { type: 'text',
      value: id.session != null ? String(id.session) : '' });
    const whoIn = el('input', { type: 'text', value: me });
    const noteIn = el('input', { type: 'text', placeholder: 'optional' });

    /* Per set: its own name, type and source, pre-filled from where it came
       from but editable, because only a person knows which script version
       actually produced it. */
    const rows = sets.map((st) => {
      const guessType = st.type
        || (st.detector === 'threshold' ? 'spike' : 'other');
      const name = el('input', { type: 'text', value: st.name || '' });
      const pipeline = el('input', {
        type: 'text', value: st.pipeline || '',
        placeholder: 'script, detector or file this came from',
      });
      const type = el('select', {}, typeOptions.map((t) => el('option', {
        value: t.id, text: t.name,
        selected: t.id === guessType ? 'selected' : null,
      })));
      return { st, name, pipeline, type };
    });

    const field = (label, control, hint) => el('div', { class: 'field' }, [
      el('label', { text: label }), control,
      hint ? el('span', { class: 'hint', text: hint }) : null,
    ]);

    const table = el('div', { class: 'bank-rows' }, rows.map((r) => el('div', {
      class: 'bank-entry-row',
    }, [
      el('span', { class: 'stat-chip good', text: r.st.events.length + '' }),
      el('div', { class: 'field' }, [el('label', { text: 'Name' }), r.name]),
      el('div', { class: 'field' }, [el('label', { text: 'Type' }), r.type]),
      el('div', { class: 'field wide' }, [
        el('label', { text: 'Produced by' }), r.pipeline,
      ]),
      r.st.draft ? el('span', { class: 'flagchip bad', text: 'uncommitted' })
                 : null,
    ])));

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: sets.length > 1
          ? 'Bank ' + sets.length + ' sets' : 'Bank these events' }),
        el('span', { class: 'sub', text: id.label || sess.info.name }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'section-label', text: 'Filed under' }),
        el('div', { class: 'bank-filing' }, [
          field('Project', projIn),
          field('Mouse', mouseIn),
          field('Session', sessIn),
          field('Added by', whoIn, 'From your git config.'),
        ]),
        field('Note', noteIn),
        el('div', { class: 'section-label',
                    text: sets.length > 1 ? 'One entry per set' : 'This set' }),
        table,
        el('p', { class: 'hint',
          text: 'Times are stored as seconds from the start of this '
              + 'recording. Who added it, when, and what produced it are kept '
              + 'with the entry and cannot be edited afterwards.' }),
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        el('button', {
          class: 'btn',
          text: sets.length > 1 ? 'Bank all ' + sets.length : 'Bank it',
          onclick: async (e) => {
            const btn = e.target;
            const missing = rows.filter((r) => !r.pipeline.value.trim());
            if (missing.length) {
              toast('Say what produced ' + (missing.length > 1
                    ? missing.length + ' of these sets' : '"'
                    + (missing[0].name.value || 'that set') + '"') + '.',
                    'err', 7000);
              missing[0].pipeline.focus();
              return;
            }
            if (!whoIn.value.trim()) {
              toast('Say who is adding these.', 'err');
              whoIn.focus();
              return;
            }

            btn.disabled = true;
            const num = (v) => (v.trim() === '' ? null
              : (isFinite(+v.trim()) ? +v.trim() : v.trim()));
            const done = [];
            const failed = [];
            for (const r of rows) {
              try {
                const res = await apiPost('/api/bank/add', {
                  project: projIn.value.trim(),
                  mouse: num(mouseIn.value),
                  session: num(sessIn.value),
                  session_key: id.key, session_loose_key: id.loose_key,
                  session_label: id.label || sess.info.name,
                  session_path: sess.path,
                  recording_start: id.start,
                  duration_s: sess.info.duration_s,
                  type: r.type.value,
                  type_name: (r.type.selectedOptions[0] || {}).text,
                  name: r.name.value.trim() || r.st.name,
                  note: noteIn.value.trim(),
                  pipeline: r.pipeline.value.trim(),
                  added_by: whoIn.value.trim(),
                  parameters: r.st.parameters || {},
                  detector: r.st.detector,
                  source_file: (sess.eventsMeta || {}).file,
                  events: r.st.events.map((ev) => ({
                    start: ev.start, end: ev.end,
                    channel: ev.channel, amplitude: ev.amplitude,
                  })),
                });
                done.push(res.entry);
              } catch (err) {
                failed.push({ name: r.name.value, error: err.message });
              }
            }

            closeModal();
            if (done.length) {
              const n = done.reduce((a, x) => a + x.n, 0);
              toast('Banked ' + n + ' event(s) as ' + done.length
                    + ' entr(ies) under ' + done[0].project + ' m'
                    + done[0].mouse + ' s' + done[0].session, 'ok', 7000);
              BARRY.activity.log('bank.add',
                                 { entries: done.length, n }, sess);
              BARRY.refreshSync();
              if (BARRY.views.eventbank.reload) BARRY.views.eventbank.reload();
            }
            for (const f of failed) {
              toast('"' + f.name + '" was not banked: ' + f.error, 'err', 9000);
            }
          },
        }),
      ]),
    ]));
  }
  /* A two-way chooser, drawn the same for import and export so the pair
     reads as a pair. */
  function chooserModal(title, sub, options, footer) {
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: title }),
        el('span', { class: 'sub', text: sub }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'choice-grid' }, options.map((o) => el('button', {
          class: 'choice' + (o.disabled ? ' off' : ''),
          disabled: o.disabled ? 'disabled' : null,
          onclick: () => { closeModal(); o.run(); },
        }, [
          el('span', { class: 'choice-icon', html: o.icon }),
          el('strong', { text: o.title }),
          el('span', { class: 'choice-note', text: o.note }),
        ]))),
      ]),
      footer ? el('div', { class: 'mf' }, footer) : null,
    ]));
  }

  const ICON_BANK = '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" '
    + 'height="14" rx="2"/><path d="M3 10h18M9 5v14M15 5v14"/></svg>';
  const ICON_FILE = '<svg viewBox="0 0 24 24"><path d="M14 3H7a1 1 0 0 0-1 '
    + '1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7z"/><path d="M14 3v4h4"/></svg>';

  function chooseImport(index, sess) {
    chooserModal(
      'Import events', sess.identity.label || sess.info.name,
      [
        { title: 'From the Event Bank', icon: ICON_BANK,
          note: 'Events already banked against this recording, by anyone.',
          run: () => fromBank(index, sess) },
        { title: 'From a file', icon: ICON_FILE,
          note: 'An ets.mat, a detector\u0027s .csv or .xlsx, a Toothy '
              + 'table \u2014 the format and units are worked out for you.',
          run: () => BARRY.eventImport.open(sess, (evts, meta) => {
            addEvents(sess, evts, meta);
          }) },
      ]);
  }

  function chooseExport(index, sess) {
    const sets = bankableSets(sess);
    chooserModal(
      'Export events', sets.length
        ? sets.reduce((n, x) => n + x.events.length, 0) + ' event(s) available'
        : 'nothing loaded yet',
      [
        { title: 'To the Event Bank', icon: ICON_BANK,
          disabled: !sets.length,
          note: 'Filed by project, mouse and session, with who added them '
              + 'and what produced them. Shared through the repo.',
          run: () => reviewThenExport(index, sess, 'bank') },
        { title: 'To a file', icon: ICON_FILE,
          disabled: !sets.length,
          note: 'A CSV of the event times on this machine. Nothing is '
              + 'recorded about where it came from.',
          run: () => reviewThenExport(index, sess, 'file') },
      ],
      sets.length ? null : [
        el('span', { class: 'hint',
          text: 'Import or detect some events first.' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn', text: 'Close', onclick: closeModal }),
      ]);
  }

  /* ======================================================================
     Review before it leaves

     Exporting the wrong marks is easy and invisible afterwards, so the list
     is shown with everything ticked and anything can be dropped before it
     goes. The same step serves the bank and a file.
     ====================================================================== */
  /* ======================================================================
     Choosing what to export

     A dropdown that picks one set at a time cannot answer "the IEDs and the
     ripples, but not the artifacts", which is the normal request. So this is
     a tree: kind -> set -> individual event, with tri-state parents, and a
     selection that spans as many branches as you like.
     ====================================================================== */
  function eventTree(sess) {
    const groups = [];
    const classes = ensureClasses(sess);

    const evByClass = {};
    for (const ev of (sess.events || [])) {
      const k = classKeyOf(ev);
      (evByClass[k] = evByClass[k] || []).push(ev);
    }
    const classKeys = Object.keys(evByClass);
    if (classKeys.length) {
      groups.push({
        key: 'events', label: 'Loaded events', kind: 'event',
        sets: classKeys.map((k) => ({
          key: 'events:' + k,
          name: (classes[k] || {}).name || k,
          type: 'other',
          pipeline: (sess.eventsMeta && sess.eventsMeta.file) || '',
          color: (classes[k] || {}).color,
          events: evByClass[k],
        })),
      });
    }

    if ((sess.spikeSets || []).length) {
      groups.push({
        key: 'spikes', label: 'Committed spike sets', kind: 'spike',
        sets: sess.spikeSets.map((st) => ({
          key: 'spikes:' + st.id,
          name: st.name || 'spikes',
          type: 'spike',
          pipeline: 'BARRY threshold detector',
          parameters: st.params || {},
          detector: 'threshold',
          events: st.events || [],
        })),
      });
    }

    if (sess.spikeDraft && (sess.spikeDraft.events || []).length) {
      groups.push({
        key: 'draft', label: 'Uncommitted draft', kind: 'draft',
        sets: [{
          key: 'draft',
          name: 'threshold draft',
          type: 'spike',
          pipeline: 'BARRY threshold detector',
          parameters: sess.spikeDraft.params || {},
          detector: 'threshold',
          draft: true,
          events: sess.spikeDraft.events,
        }],
      });
    }
    return groups;
  }

  function reviewThenExport(index, sess, dest) {
    const groups = eventTree(sess);
    if (!groups.length) { toast('Nothing to export.', 'err'); return; }

    // Selection is per event: "<set key>#<index>". Sets and groups are
    // derived from it, so a parent is never out of step with its children.
    const picked = new Set();
    const open = new Set(groups.map((g) => g.key));
    const openSets = new Set();
    for (const g of groups) {
      for (const st of g.sets) {
        st.events.forEach((_, i) => picked.add(st.key + '#' + i));
      }
    }
    if (groups[0] && groups[0].sets[0]) openSets.add(groups[0].sets[0].key);

    const setCount = (st) =>
      st.events.reduce((n, _, i) => n + (picked.has(st.key + '#' + i) ? 1 : 0), 0);
    const groupCount = (g) => g.sets.reduce((n, st) => n + setCount(st), 0);
    const groupTotal = (g) => g.sets.reduce((n, st) => n + st.events.length, 0);
    const total = () => groups.reduce((n, g) => n + groupCount(g), 0);
    const grandTotal = groups.reduce((n, g) => n + groupTotal(g), 0);

    const setSet = (st, on) => st.events.forEach((_, i) => {
      if (on) picked.add(st.key + '#' + i); else picked.delete(st.key + '#' + i);
    });
    const setGroup = (g, on) => g.sets.forEach((st) => setSet(st, on));

    /* A checkbox that can also say "some of these". */
    const triBox = (checked, some, onchange) => {
      const box = el('input', { type: 'checkbox', onchange });
      box.checked = checked;
      box.indeterminate = !checked && some;
      return box;
    };

    const body = el('div');
    const summary = el('span', { class: 'stat-chip good' });

    const draw = () => {
      body.innerHTML = '';
      summary.textContent = total() + ' of ' + grandTotal + ' selected, across '
        + groups.reduce((n, g) => n + g.sets.filter((st) => setCount(st)).length, 0)
        + ' set(s)';

      const tree = el('div', { class: 'ev-tree' });
      for (const g of groups) {
        const n = groupCount(g), all = groupTotal(g);
        const isOpen = open.has(g.key);
        tree.appendChild(el('div', { class: 'ev-node group' }, [
          el('button', {
            class: 'ev-twist' + (isOpen ? ' open' : ''),
            title: isOpen ? 'Collapse' : 'Expand',
            html: '<svg viewBox="0 0 20 20"><path d="m8 5 5 5-5 5"/></svg>',
            onclick: () => { if (isOpen) open.delete(g.key); else open.add(g.key);
                             draw(); },
          }),
          triBox(n === all && all > 0, n > 0,
                 (e) => { setGroup(g, e.target.checked); draw(); }),
          el('span', { class: 'ev-label', text: g.label }),
          el('span', { class: 'ev-count', text: n + ' / ' + all }),
        ]));
        if (!isOpen) continue;

        for (const st of g.sets) {
          const sn = setCount(st), sall = st.events.length;
          const sOpen = openSets.has(st.key);
          tree.appendChild(el('div', { class: 'ev-node set' }, [
            el('button', {
              class: 'ev-twist' + (sOpen ? ' open' : ''),
              html: '<svg viewBox="0 0 20 20"><path d="m8 5 5 5-5 5"/></svg>',
              onclick: () => { if (sOpen) openSets.delete(st.key);
                               else openSets.add(st.key); draw(); },
            }),
            triBox(sn === sall && sall > 0, sn > 0,
                   (e) => { setSet(st, e.target.checked); draw(); }),
            st.color ? el('span', { class: 'mk-dot',
                                    style: 'background:' + st.color }) : null,
            el('span', { class: 'ev-label', text: st.name }),
            st.draft ? el('span', { class: 'flagchip bad', text: 'draft' }) : null,
            el('span', { class: 'ev-src', text: st.pipeline || '',
                         title: st.pipeline || '' }),
            el('span', { class: 'ev-count', text: sn + ' / ' + sall }),
          ]));
          if (!sOpen) continue;

          // Long sets are not worth drawing a row each; the set-level box is
          // the useful control there.
          const cap = 200;
          st.events.slice(0, cap).forEach((ev, i) => {
            const id = st.key + '#' + i;
            tree.appendChild(el('label', { class: 'ev-node leaf' }, [
              el('span', { class: 'ev-twist' }),
              triBox(picked.has(id), false, (e) => {
                if (e.target.checked) picked.add(id); else picked.delete(id);
                draw();
              }),
              el('span', { class: 't', text: fmtTime(ev.start) }),
              el('span', { class: 'ev-detail', text:
                (ev.end != null ? ((ev.end - ev.start) * 1000).toFixed(1) + ' ms  ' : '')
                + (ev.channel != null ? 'CSC' + ev.channel + '  ' : '')
                + (ev.amplitude != null ? Math.round(ev.amplitude) + ' uV' : '') }),
              el('button', {
                class: 'mini', text: 'go',
                onclick: (e) => {
                  e.preventDefault(); e.stopPropagation();
                  const w = winOf(XF.panes[index], sess);
                  setWindow(index, ev.start - w.span / 2, w.span);
                },
              }),
            ]));
          });
          if (sall > cap) {
            tree.appendChild(el('div', { class: 'ev-node leaf hint',
              text: 'and ' + (sall - cap) + ' more \u2014 use the set '
                  + 'checkbox above to take or leave all of them' }));
          }
        }
      }
      body.appendChild(tree);
    };
    draw();

    const inWindow = () => {
      const w = winOf(XF.panes[index], sess);
      picked.clear();
      for (const g of groups) {
        for (const st of g.sets) {
          st.events.forEach((ev, i) => {
            if (ev.start >= w.t0 && ev.start <= w.t0 + w.span) {
              picked.add(st.key + '#' + i);
            }
          });
        }
      }
      draw();
    };

    /* What was chosen, grouped back into the sets it came from -- so banking
       makes one entry per set rather than one undifferentiated pile. */
    const chosenSets = () => {
      const out = [];
      for (const g of groups) {
        for (const st of g.sets) {
          const evs = st.events.filter((_, i) => picked.has(st.key + '#' + i));
          if (evs.length) out.push(Object.assign({}, st, { events: evs }));
        }
      }
      return out;
    };

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: dest === 'bank' ? 'Bank events' : 'Export events' }),
        el('span', { class: 'sub', text: sess.identity.label || sess.info.name }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'res-toolbar' }, [
          summary,
          el('div', { style: 'flex:1' }),
          el('button', { class: 'btn ghost sm', text: 'All',
            onclick: () => { groups.forEach((g) => setGroup(g, true)); draw(); } }),
          el('button', { class: 'btn ghost sm', text: 'None',
            onclick: () => { picked.clear(); draw(); } }),
          el('button', { class: 'btn ghost sm', text: 'Only this window',
            title: 'Keep just the events inside the view on screen',
            onclick: inWindow }),
          el('button', { class: 'btn ghost sm', text: 'Expand all',
            onclick: () => {
              groups.forEach((g) => { open.add(g.key);
                g.sets.forEach((st) => openSets.add(st.key)); });
              draw();
            } }),
          el('button', { class: 'btn ghost sm', text: 'Collapse',
            onclick: () => { openSets.clear(); draw(); } }),
        ]),
        body,
      ]),
      el('div', { class: 'mf' }, [
        el('span', { class: 'hint', text: dest === 'bank'
          ? 'Each set becomes its own bank entry, so their types and sources '
            + 'stay separate.'
          : 'One CSV, with a column saying which set each event came from.' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        el('button', {
          class: 'btn',
          text: dest === 'bank' ? 'Continue\u2026' : 'Download CSV',
          onclick: () => {
            const sets = chosenSets();
            if (!sets.length) { toast('Nothing selected.', 'err'); return; }
            closeModal();
            if (dest === 'bank') openBank(index, sess, sets);
            else exportEventsFile(sess, sets);
          },
        }),
      ]),
    ]));
  }
  /* A plain CSV, on this machine. Nothing is recorded about where it came
     from -- which is the difference between this and banking it. */
  function exportEventsFile(sess, sets) {
    const id = sess.identity || {};
    const head = ['start_s', 'end_s', 'channel', 'amplitude_uv', 'set',
                  'produced_by', 'session', 'mouse', 'session_no', 'recording'];
    const rows = [];
    for (const st of sets) {
      for (const ev of st.events) {
        rows.push([
          ev.start,
          ev.end != null ? ev.end : '',
          ev.channel != null ? ev.channel : '',
          ev.amplitude != null ? ev.amplitude : '',
          st.name || '',
          st.pipeline || '',
          id.label || sess.info.name,
          id.mouse != null ? id.mouse : '',
          id.session != null ? id.session : '',
          sess.path,
        ]);
      }
    }
    const esc = (v) => {
      const t = String(v);
      return /[",\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t;
    };
    const csv = [head.join(',')]
      .concat(rows.map((r) => r.map(esc).join(','))).join('\n');
    const name = 'events_' + (id.label || sess.info.name)
      .replace(/[^\w.-]+/g, '_') + '.csv';
    BARRY.saveText(name, csv, 'text/csv;charset=utf-8');
    toast('Exported ' + rows.length + ' event(s) from ' + sets.length
          + ' set(s)', 'ok');
    BARRY.activity.log('events.export_file',
                       { n: rows.length, sets: sets.map((x) => x.name) }, sess);
  }

  async function fromBank(index, sess) {
    let res;
    try {
      res = await apiPost('/api/bank/for-session', { identity: sess.identity });
    } catch (e) { toast(e.message, 'err'); return; }

    const list = res.entries || [];
    if (!list.length) {
      toast('Nothing banked against this recording yet.', null, 4000);
      return;
    }

    const rows = el('div', { class: 'bm-list tall' });
    for (const en of list) {
      const src = en.source || {}, added = en.added || {};
      rows.appendChild(el('div', {
        class: 'bm-row',
        title: 'From ' + (src.pipeline || 'unknown') + ', banked by '
             + (added.by || '?'),
        onclick: async () => {
          closeModal();
          let full;
          try { full = await api('/api/bank/' + encodeURIComponent(en.id)); }
          catch (e) { toast(e.message, 'err'); return; }
          const evs = ((full.entry || {}).events || []).map(
            (ev) => Object.assign({}, ev, { label: en.name }));
          addBankedEvents(sess, evs, {
            name: en.name, type: en.type, entry_id: en.id,
            pipeline: src.pipeline, added_by: added.by,
          });
          toast('Loaded ' + evs.length + ' event(s) from the bank', 'ok');
        },
      }, [
        el('span', { class: 'flagchip' + (en.match === 'exact' ? ' good'
                     : (en.match === 'weak' ? ' bad' : '')), text: en.match }),
        el('span', { class: 'mk-name', text: en.name }),
        el('span', { class: 'mk-detail',
                     text: en.n + ' \u00b7 ' + (src.pipeline || '') }),
        el('span', { class: 'mk-kind', text: en.type }),
      ]));
    }

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Load from the bank' }),
        el('span', { class: 'sub',
                     text: sess.identity.label || sess.info.name }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { class: 'confirm-msg',
          text: 'Matched on the session identity, so an entry banked on '
              + 'another machine still turns up here. "exact" means the '
              + 'recording start time matches too.' }),
        rows,
      ]),
      el('div', { class: 'mf' }, [
        el('button', { class: 'btn ghost sm', text: 'Open the Event Bank',
          onclick: () => { closeModal(); setView('eventbank'); } }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn', text: 'Close', onclick: closeModal }),
      ]),
    ]));
  }

  /* Events arriving from the bank. Kept distinct from a file import so the
     class carries the entry's name, and so the provenance travels with it. */
  function addBankedEvents(sess, evts, info) {
    addEvents(sess, evts, { file: 'bank: ' + (info.name || 'entry'),
                            units: 'seconds', bank: info });
    const classes = ensureClasses(sess);
    const key = classKeyOf(evts[0] || {});
    if (classes[key]) {
      classes[key].name = info.name || classes[key].name;
      classes[key].bank = info;
      saveEventClasses(sess);
    }
    render();
    refreshSession(sess);
  }

  /* Put a committed spike set onto the trace as events.

     Detected spikes used to be a parallel world: a committed set drew its own
     ticks and counted under Marks, but never entered the event system -- so
     the marks browser read "Events (2)" beside "Spikes (1522)", and none of
     the things you can do to an event (name the class, color it, hide it,
     step through it, send it to the bank as events) could touch a spike.
     Finding 1458 marks and then having no way to work with them is the gap.

     This copies rather than moves. A spike set is the record of a detector
     run and should not evaporate because someone wanted to recolor it; the
     events are a working copy. Running it twice replaces the earlier copy
     instead of doubling it. */
  function spikesToEvents(sess, set_) {
    const evs = (set_.events || []).map((e) => Object.assign({}, e, {
      label: set_.name,
      source: 'spikes',
      spike_set: set_.id,
    }));
    if (!evs.length) {
      toast('That set has no marks in it.', 'err');
      return 0;
    }
    const had = sess.events.length;
    sess.events = sess.events.filter((e) => e.spike_set !== set_.id);
    const replaced = had - sess.events.length;

    addEvents(sess, evs, {
      file: 'spikes: ' + set_.name,
      units: 'seconds',
      spike_set: set_.id,
      n: evs.length,
    });
    BARRY.activity.log('spikes.to_events',
                       { set: set_.name, n: evs.length, replaced }, sess);
    toast(evs.length + ' mark(s) from "' + set_.name + '" are now events'
          + (replaced ? ' (replacing the earlier copy)' : '')
          + ' — name and color them under Events.', 'ok', 7000);
    return evs.length;
  }

  /* ---------- event classes ---------- */
  function addEvents(sess, evts, meta) {
    // Imports accumulate rather than replace: a session often has TTLs from
    // the .nev plus a detector's output, and both are worth seeing at once.
    const tag = meta && meta.path ? baseName(meta.path) : 'import';
    for (const e of evts) {
      if (!e.label) e.label = tag;
    }
    sess.events = sess.events.concat(evts).sort((a, b) => a.start - b.start);
    sess.eventsMeta = meta;
    ensureClasses(sess);
    restoreEventClasses(sess);
    saveEventClasses(sess);
    BARRY.activity.log('events.import', {
      file: tag, n: evts.length, total: sess.events.length,
      units: meta && meta.units,
    }, sess);
    render(); refreshSession(sess);
  }

  function restoreEventClasses(sess) {
    // Names and colors are session data, so they come back with the session.
    const stored = (sess.stored && sess.stored.event_classes) || {};
    const classes = eventClasses(sess);
    for (const [key, saved] of Object.entries(stored)) {
      // Sessions saved before the spelling was made consistent used "colour".
      if (saved && saved.color === undefined && saved.colour !== undefined) {
        saved.color = saved.colour;
      }
      if (!classes[key]) continue;
      if (saved.name) classes[key].name = saved.name;
      if (saved.color) classes[key].color = saved.color;
      if (saved.visible !== undefined) classes[key].visible = saved.visible;
    }
  }

  async function saveEventClasses(sess) {
    if (!sess.identity || (sess.identity.mouse == null && !sess.identity.key)) return;
    const out = {};
    for (const [key, c] of Object.entries(eventClasses(sess))) {
      out[key] = { name: c.name, color: c.color, visible: c.visible !== false };
    }
    try {
      await apiPost('/api/session/events', {
        identity: sess.identity, event_classes: out,
      });
      BARRY.refreshSync();
    } catch (e) { /* non-fatal */ }
  }

  function openEvents(index, sess) {
    const classes = ensureClasses(sess);
    restoreEventClasses(sess);
    const keys = Object.keys(classes).sort(
      (a, b) => (classes[b].n || 0) - (classes[a].n || 0));

    const rows = el('div', { class: 'bm-list' });
    if (!keys.length) {
      rows.appendChild(el('div', { class: 'tree-empty',
        text: 'No events loaded. Use Import to bring some in.' }));
    }

    for (const key of keys) {
      const c = classes[key];
      const swatches = el('div', { class: 'cmap-row', style: 'gap:3px' });
      for (const col of EVENT_COLORS) {
        swatches.appendChild(el('button', {
          class: 'ev-swatch' + (c.color === col ? ' on' : ''),
          style: 'background:' + col, title: col,
          onclick: () => {
            c.color = col;
            saveEventClasses(sess);
            refreshSession(sess);
            openEvents(index, sess);
          },
        }));
      }

      rows.appendChild(el('div', { class: 'ev-row' }, [
        el('label', { class: 'toggle sm' + (c.visible !== false ? ' on' : '') }, [
          el('input', {
            type: 'checkbox', checked: c.visible !== false ? 'checked' : null,
            title: 'Show this class',
            onchange: (e) => {
              c.visible = e.target.checked;
              saveEventClasses(sess);
              refreshSession(sess);
              BARRY.activity.log('events.visibility',
                { cls: c.name, visible: c.visible }, sess);
            },
          }),
          el('span', { text: '' }),
        ]),
        el('span', { class: 'ev-dot', style: 'background:' + c.color }),
        el('input', {
          type: 'text', class: 'ev-name', value: c.name,
          title: 'Name for this class of events',
          onchange: (e) => {
            c.name = e.target.value || key;
            saveEventClasses(sess);
            BARRY.activity.log('events.rename', { key, name: c.name }, sess);
          },
        }),
        el('span', { class: 'stat-chip', text: (c.n || 0) + '' }),
        swatches,
        el('button', {
          class: 'mini', text: '\u2691',
          title: 'Bookmark the first event of this class',
          onclick: () => {
            const first = sess.events.find((e) => classKeyOf(e) === key);
            if (first) { closeModal(); addBookmark(index, sess, first.start, c.name); }
          },
        }),
        el('span', { class: 'ev-src', text: key === c.name ? '' : key }),
      ]));
    }

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Events' }),
        el('span', { class: 'sub',
          text: sess.events.length + ' mark(s) in ' + keys.length + ' class(es)' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [
        rows,
        el('p', { style: 'margin-top:12px;font-size:11.5px;color:var(--text-3);line-height:1.6',
          text: 'Names, colors and visibility are saved with the session and '
              + 'travel through GUI_logs, so everyone sees the same scheme.' }),
      ]),
      el('div', { class: 'mf' }, [
        el('button', { class: 'btn ghost sm', text: 'Import more\u2026',
          onclick: () => BARRY.eventImport.open(sess, (evts, meta) => {
            addEvents(sess, evts, meta); openEvents(index, sess);
          }) }),
        el('button', { class: 'btn ghost sm', text: 'Clear all',
          onclick: () => {
            sess.events = []; sess.eventsMeta = null; sess._eventClasses = {};
            BARRY.activity.log('events.clear', {}, sess);
            closeModal(); render(); refreshSession(sess);
          } }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn', text: 'Done', onclick: closeModal }),
      ]),
    ]));
  }

  /* Switching between a relative and an absolute threshold has to bring the
     number with it, or the box still says "4" and now means four microvolts. */
  function setThresholdMode(P, mode) {
    if (P.threshold_mode === mode) return;
    const wasUv = P.threshold_mode === 'uv';
    P.threshold_mode = mode;
    if (mode === 'uv' && !wasUv) {
      P.threshold = 100;      // a sane starting amplitude for LFP
    } else if (mode === 'sd' && wasUv) {
      P.threshold = 4;
    }
    const sess = active();
    if (sess) openSpikes(XF.focused, sess);   // redraw with the new units
  }

  /* ---------- threshold spike labeling ---------- */
  function openSpikes(index, sess) {
    const pane = XF.panes[index];
    const w = winOf(pane, sess);
    const P = sess.spikeParams || {
      threshold: 4, threshold_mode: 'sd', polarity: 'neg',
      refractory_ms: 1, merge_channels: true, merge_ms: 2, whole: false,
    };
    sess.spikeParams = P;

    const num = (label, key, step, hint) => el('div', { class: 'field' }, [
      el('label', { text: label }),
      el('input', {
        type: 'number', step: String(step), value: String(P[key]),
        onchange: (e) => { P[key] = parseFloat(e.target.value); },
      }),
      hint ? el('span', { class: 'hint', text: hint }) : null,
    ]);

    const status = el('div', { class: 'fb-stats' });
    const perCh = el('div', { class: 'preview-wrap hidden' });

    const showDraft = (res) => {
      status.innerHTML = '';
      status.appendChild(el('span', { class: 'stat-chip draft-chip',
        text: res.n + ' draft mark(s)' }));
      status.appendChild(el('span', { class: 'stat-chip',
        text: fmtTime(res.t0) + ' \u2192 ' + fmtTime(res.t1) }));
      // Detection runs on the window, channels and filters that are on
      // screen. That is the right default and also the thing most likely to
      // be forgotten, so it is stated with the result rather than implied.
      if (res.input) {
        status.appendChild(el('div', { class: 'ran-on', text: 'ran on  ' + res.input }));
      }
      perCh.classList.remove('hidden');
      perCh.innerHTML = '';
      perCh.appendChild(el('table', { class: 'preview-table' }, [
        el('thead', {}, [el('tr', {}, [
          el('th', { text: 'channel' }), el('th', { text: 'threshold (uV)' }),
          el('th', { text: 'SD (uV)' }), el('th', { text: 'n' })])]),
        el('tbody', {}, (res.per_channel || []).map((c) => el('tr', {}, [
          el('td', { text: c.label }), el('td', { text: String(c.threshold_uv) }),
          el('td', { text: String(c.sd_uv) }), el('td', { text: String(c.n) }),
        ]))),
      ]));
    };

    const run = async () => {
      status.innerHTML = '';
      status.appendChild(el('span', { class: 'stat-chip', text: 'detecting\u2026' }));
      const t0 = P.whole ? 0 : w.t0;
      const t1 = P.whole ? (sess.info.duration_s || w.t0 + w.span) : w.t0 + w.span;
      try {
        const res = await apiPost('/api/spikes/detect', {
          path: sess.path, even_only: sess.evenOnly, invert: sess.invert,
          t0, t1, channels: Array.from(sess.sel).sort((a, b) => a - b),
          bad_channels: Array.from(sess.bad),
          highpass: sess.hp, lowpass: sess.lp, notch: sess.notch,
          threshold: P.threshold, threshold_mode: P.threshold_mode,
          polarity: P.polarity, refractory_ms: P.refractory_ms,
          merge_channels: P.merge_channels, merge_ms: P.merge_ms,
          max_span_s: 900,
        });
        sess.spikeDraft = res;
        showDraft(res);
        render(); refreshSession(sess);
        BARRY.activity.log('spikes.detect', {
          n: res.n, threshold: P.threshold, mode: P.threshold_mode,
          polarity: P.polarity, t0, t1,
        }, sess);
      } catch (e) {
        status.innerHTML = '';
        status.appendChild(el('span', { class: 'stat-chip warn', text: e.message }));
      }
    };

    const commit = async () => {
      if (!sess.spikeDraft || !sess.spikeDraft.n) {
        toast('Detect something first.', 'err'); return;
      }
      const name = await askPath('Name this spike set',
                                 'e.g. "IED 4SD neg" or "units CSC14"');
      if (!name) return;
      try {
        const res = await apiPost('/api/spikes/commit', {
          identity: sess.identity, name,
          events: sess.spikeDraft.events, params: sess.spikeDraft.params,
          t0: sess.spikeDraft.t0, t1: sess.spikeDraft.t1,
        });
        sess.spikeSets = res.sets || [];
        sess.spikeDraft = null;
        BARRY.activity.log('spikes.commit',
          { name, n: (res.set || {}).n }, sess);

        // Committing used to stop here, which left the marks visible but
        // untouchable: not events, so not nameable, colorable, or
        // exportable as events. Putting them on the trace is what people
        // meant by committing them, so it happens now and says so.
        const saved = (res.sets || []).find((x) => x.name === name)
                   || res.set || null;
        const n = saved ? spikesToEvents(sess, saved) : 0;

        closeModal(); render(); refreshSession(sess);
        if (!n) {
          toast('Committed "' + name + '" \u2014 marks are now solid', 'ok');
        }
        BARRY.refreshSync();
      } catch (e) { toast(e.message, 'err', 7000); }
    };

    const setList = el('div', { class: 'bm-list' });
    for (const st of sess.spikeSets) {
      const onTrace = sess.events.some((e) => e.spike_set === st.id);
      setList.appendChild(el('div', { class: 'bm-row' }, [
        el('span', { class: 'stat-chip committed-chip', text: st.n + '' }),
        el('span', { text: st.name }),
        el('span', { class: 't', text: (st.params || {}).threshold != null
          ? st.params.threshold + (st.params.threshold_mode === 'sd' ? ' SD' : ' uV') : '' }),
        el('button', {
          class: 'mini' + (onTrace ? ' active' : ''),
          text: onTrace ? 'on the trace' : 'Add to events',
          title: onTrace
            ? 'Already on the trace as events — click to refresh the copy'
            : 'Copy these marks onto the trace as events, so they can be '
              + 'named, colored, hidden, stepped through and exported like '
              + 'any other event',
          onclick: (e) => {
            e.stopPropagation();
            spikesToEvents(sess, st);
            render(); refreshSession(sess); openSpikes(index, sess);
          },
        }),
        el('span', {
          class: 'x', text: '\u2715', title: 'Delete this set',
          onclick: async () => {
            try {
              const res = await apiPost('/api/spikes/delete',
                { identity: sess.identity, id: st.id });
              sess.spikeSets = res.sets || [];
              BARRY.activity.log('spikes.delete', { name: st.name }, sess);
              render(); refreshSession(sess); openSpikes(index, sess);
            } catch (e) { toast(e.message, 'err'); }
          },
        }),
      ]));
    }

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Threshold spike labeling' }),
        el('span', { class: 'sub', text: sess.identity.label || sess.info.name }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'wiz-grid' }, [
          el('div', {}, [
            el('div', { class: 'section-label', style: 'margin-top:0', text: 'Detector' }),
            el('div', { class: 'field' }, [
              el('label', { text: 'How to set the threshold' }),
              el('div', { class: 'seg', id: 'thrMode' }, [
                el('button', {
                  class: P.threshold_mode === 'uv' ? '' : 'active',
                  text: 'Relative (\u00d7 SD)',
                  title: 'A multiple of each channel\u0027s own noise level. '
                       + 'Adapts to channels of different quality.',
                  onclick: () => setThresholdMode(P, 'sd'),
                }),
                el('button', {
                  class: P.threshold_mode === 'uv' ? 'active' : '',
                  text: 'Amplitude (\u00b5V)',
                  title: 'A plain voltage. The same bar on every channel, '
                       + 'and the number means what it says.',
                  onclick: () => setThresholdMode(P, 'uv'),
                }),
              ]),
            ]),
            num('Threshold', 'threshold',
                P.threshold_mode === 'uv' ? 5 : 0.5,
                P.threshold_mode === 'uv'
                  ? 'Microvolts. A crossing of this amplitude counts, on every '
                    + 'channel alike.'
                  : 'Multiples of a robust SD, computed per channel from the '
                    + 'median absolute deviation \u2014 so one big artifact '
                    + 'cannot raise the bar above every real event.'),
            el('div', { class: 'field' }, [
              el('label', { text: 'Polarity' }),
              el('select', { onchange: (e) => { P.polarity = e.target.value; } }, [
                el('option', { value: 'neg', text: 'Negative-going',
                  selected: P.polarity === 'neg' ? 'selected' : null }),
                el('option', { value: 'pos', text: 'Positive-going',
                  selected: P.polarity === 'pos' ? 'selected' : null }),
                el('option', { value: 'abs', text: 'Either',
                  selected: P.polarity === 'abs' ? 'selected' : null }),
              ]),
            ]),
            num('Refractory (ms)', 'refractory_ms', 0.5,
                'Minimum gap between marks on one channel.'),
            el('label', { class: 'toggle' + (P.merge_channels ? ' on' : '') }, [
              el('input', {
                type: 'checkbox', checked: P.merge_channels ? 'checked' : null,
                onchange: (e) => { P.merge_channels = e.target.checked; },
              }),
              el('span', { text: 'Merge simultaneous channels into one event' }),
            ]),
            num('Merge window (ms)', 'merge_ms', 0.5, null),
            el('label', { class: 'toggle' + (P.whole ? ' on' : ''),
                          style: 'margin-top:8px' }, [
              el('input', {
                type: 'checkbox', checked: P.whole ? 'checked' : null,
                onchange: (e) => { P.whole = e.target.checked; },
              }),
              el('span', { text: 'Whole recording (not just this window)' }),
            ]),
            el('div', { class: 'hint', style: 'margin-top:8px;font-size:11px;color:var(--text-3)',
              text: 'Detection uses the filters currently applied to the pane '
                  + '(HP ' + sess.hp + ' / LP ' + sess.lp + ' / notch ' + sess.notch + ').' }),
          ]),
          el('div', {}, [
            el('div', { class: 'section-label', style: 'margin-top:0', text: 'Result' }),
            status,
            perCh,
            el('div', { class: 'section-label', text: 'Committed sets' }),
            setList.childNodes.length ? setList
              : el('div', { class: 'tree-empty', text: 'Nothing committed yet.' }),
            el('p', { style: 'font-size:11.5px;color:var(--text-3);line-height:1.6',
              text: 'Draft marks are drawn faint and dashed. Committing saves them '
                  + 'to GUI_logs and they become solid.' }),
          ]),
        ]),
      ]),
      el('div', { class: 'mf' }, [
        el('button', { class: 'btn ghost', text: 'Detect', onclick: run }),
        sess.spikeDraft ? el('button', {
          class: 'btn ghost sm', text: 'Discard draft',
          onclick: () => {
            sess.spikeDraft = null;
            closeModal(); render(); refreshSession(sess);
          },
        }) : null,
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Close', onclick: closeModal }),
        el('button', { class: 'btn', text: 'Commit draft', onclick: commit }),
      ]),
    ]));

    if (sess.spikeDraft) showDraft(sess.spikeDraft);
  }

  function labelForPanel(id) {
    const d = XF.panelDefs.find((p) => p.id === id);
    if (d) return d.name;
    return ({ video: 'Video', tracking: 'Position tracking' })[id] || id;
  }

  /* Re-read a session after a read option changed, without losing your place.

     Invert and even-only change how the file is decoded, so the session has to
     be reopened -- but throwing away the window, gain and filters every time
     someone toggles polarity would be unusable. */
  async function reopenSameView(sess) {
    const keep = {
      t0: sess.t0, span: sess.span, gain: sess.gain,
      hp: sess.hp, lp: sess.lp, notch: sess.notch,
      ylim: sess.ylim, normalize: sess.normalize,
      events: sess.events, eventsMeta: sess.eventsMeta,
      bookmarks: sess.bookmarks, spikeSets: sess.spikeSets,
      spikeDraft: sess.spikeDraft,
    };
    const panes = XF.panes.map((p) => (p && p.sessionId === sess.id) ? p : null);
    const reopened = await openSession(sess.path, {
      evenOnly: sess.evenOnly, invert: sess.invert, replace: sess.id,
    });
    if (!reopened) return;
    Object.assign(reopened, keep);
    panes.forEach((p, i) => { if (p) XF.panes[i] = { ...p, sessionId: reopened.id }; });
    render();
    refreshAll();
  }

  const isImagePanel = (p) => ['voltage', 'csd', 'theta', 'spectrogram', 'scalogram'].includes(p);
  const firstSel = (sess) => (sess.sel.size ? Math.min(...sess.sel) : 0);

  /* ---------- channel list with bad marking ---------- */
  function paneChannels(index, sess) {
    const host = el('div', { class: 'pane-chans' });
    // Fixed-height header: its height is a contract with the canvas (see
    // CH_HEADER_H), so the rows below it line up with the trace lanes.
    const top = el('div', { class: 'ch-top' });
    host.appendChild(top);
    top.appendChild(el('div', { class: 'ch-head' }, [
      el('strong', { text: 'Channels' }),
      el('span', { text: sess.sel.size + '/' + sess.info.channels.length }),
    ]));

    const quick = el('div', { class: 'ch-quick' });
    for (const [k, label] of [['all', 'All'], ['none', 'None'], ['even', 'Even'],
                              ['odd', 'Odd'], ['invert', 'Flip'], ['good', 'Good']]) {
      quick.appendChild(el('button', {
        class: 'mini', text: label,
        title: k === 'good' ? 'Select only channels not marked bad' : '',
        onclick: () => { quickSelect(sess, k); render(); refreshSession(sess); },
      }));
    }
    top.appendChild(quick);

    const list = el('div', { class: 'ch-list' });
    for (const c of sess.info.channels) {
      const isBad = sess.bad.has(c.number) || c.bad;
      list.appendChild(el('label', {
        class: 'ch-row' + (sess.sel.has(c.index) ? '' : ' off') + (isBad ? ' marked-bad' : ''),
        'data-num': String(c.number),
        title: c.label + (isBad ? '  (marked bad)' : ''),
      }, [
        el('input', {
          type: 'checkbox', checked: sess.sel.has(c.index) ? 'checked' : null,
          onchange: (e) => {
            if (e.target.checked) sess.sel.add(c.index); else sess.sel.delete(c.index);
            render(); refreshSession(sess);
            queueSaveState(sess);
            publishLink(sess.t0, sess.span, sess);
          },
        }),
        el('span', { text: c.label }),
        el('button', {
          class: 'badbtn', text: isBad ? 'BAD' : 'ok',
          title: isBad ? 'Marked bad — click to clear' : 'Mark this channel bad',
          onclick: (e) => { e.preventDefault(); e.stopPropagation(); toggleBad(sess, c.number); },
        }),
      ]));
    }
    if (sess.identity && sess.identity.mouse == null) {
      top.appendChild(el('div', {
        class: 'ch-note',
        title: 'Rename the folder to include m<N> and s<N> to make these stick.',
        text: 'No mouse/session id — marks stay local',
      }));
    }
    host.appendChild(list);
    return host;
  }

  function quickSelect(sess, kind) {
    const all = sess.info.channels;
    if (kind === 'all') all.forEach((c) => sess.sel.add(c.index));
    else if (kind === 'none') sess.sel.clear();
    else if (kind === 'invert') all.forEach((c) => sess.sel.has(c.index) ? sess.sel.delete(c.index) : sess.sel.add(c.index));
    else if (kind === 'good') {
      sess.sel.clear();
      all.forEach((c) => { if (!sess.bad.has(c.number) && !c.bad) sess.sel.add(c.index); });
    } else {
      const want = kind === 'even' ? 0 : 1;
      sess.sel.clear();
      all.forEach((c) => { if (c.number % 2 === want) sess.sel.add(c.index); });
    }
  }

  async function toggleBad(sess, number) {
    if (sess.bad.has(number)) sess.bad.delete(number); else sess.bad.add(number);
    render();
    refreshSession(sess);

    if (!sess.identity || sess.identity.mouse == null) {
      toast('Marked locally — this recording has no detectable mouse/session id, '
            + 'so it cannot be saved across machines.', 'err', 7000);
      return;
    }
    try {
      await apiPost('/api/session/bad', {
        identity: sess.identity,
        bad_channels: Array.from(sess.bad),
      });
      BARRY.refreshSync();
    } catch (e) {
      toast('Could not save bad channels: ' + e.message, 'err', 7000);
    }
  }

  /* ---------- the plot area ---------- */
  function panePlot(index, pane, sess) {
    const host = el('div', { class: 'pane-plot' });

    if (pane.panel === 'video') {
      host.appendChild(buildVideo(sess));
      return host;
    }
    if (pane.panel === 'tracking') {
      const c = el('canvas', { class: 'track-canvas' });
      host.appendChild(el('div', { class: 'pane-canvas-host' }, [c]));
      pane._track = c;
      loadTracking(index, pane, sess);
      return host;
    }

    if (pane.panel === 'traces') {
      const canvas = el('canvas');
      const readout = el('div', { class: 'cursor-readout pane-readout' });
      const loading = el('div', { class: 'plot-loading' },
                          [loader('Voltage traces', 'reading channels')]);
      const overlay = el('div', { class: 'ch-overlay' });
      const cHost = el('div', { class: 'pane-canvas-host' },
                       [canvas, overlay, readout, loading]);
      host.appendChild(cHost);
      pane._canvas = canvas; pane._readout = readout; pane._loading = loading;
      pane._overlay = overlay;
      watchResize(cHost, index);
      wireTraceCanvas(index, pane, sess, canvas, readout);
      wirePlacement(index, pane, sess, cHost);
    } else {
      // No alt text and hidden until loaded: an <img> with no src renders the
      // browser's broken-image glyph, which reads as an error, not a wait.
      const img = el('img', { alt: '', class: 'hidden' });
      const gridCv = el('canvas', { class: 'raster-grid' });
      img.addEventListener('load', () => {
        img.classList.remove('hidden');
        // Draw the rules here, not when the data arrives: until the image is
        // laid out the overlay has no size to draw into. This is why the grid
        // never appeared -- it was only ever drawn on a resize or a pane
        // rebuild, moments when the panel data was usually not there yet.
        drawRasterGrid(pane, pane._panelData);
      });
      const loading = el('div', { class: 'plot-loading' },
                          [loader(labelForPanel(pane.panel), 'rendering')]);
      const readout = el('div', { class: 'cursor-readout pane-readout' });
      const iHost = el('div', { class: 'pane-img-host' }, [img, gridCv, readout, loading]);
      pane._grid = gridCv;
      host.appendChild(iHost);
      pane._img = img; pane._loading = loading; pane._readout = readout;
      wireImagePane(index, pane, sess, iHost);
      wirePlacement(index, pane, sess, iHost);
      watchResize(iHost, index);
    }

    const mini = el('canvas');
    host.appendChild(el('div', { class: 'pane-timebar' }, [mini]));
    pane._mini = mini;
    wireMini(index, pane, sess, mini);
    return host;
  }

  /* ==================================================================
     Data fetching
     ================================================================== */
  function refreshAll() {
    for (let i = 0; i < XF.nPanes; i++) refreshPane(i);
  }

  function refreshSession(sess) {
    XF.panes.forEach((p, i) => { if (p && p.sessionId === sess.id) refreshPane(i); });
  }

  /* A horizontal strip that a vertical wheel cannot reach is a strip whose
     right-hand end nobody finds. */
  function wireStripScroll(strip) {
    strip.addEventListener('wheel', (e) => {
      if (e.deltaY === 0 || e.shiftKey) return;
      if (strip.scrollWidth <= strip.clientWidth) return;
      e.preventDefault();
      strip.scrollLeft += e.deltaY;
    }, { passive: false });
  }

  function refreshControls(index) {
    // A popover is anchored to a button on this strip, so it cannot outlive
    // the rebuild.
    closeMenu();
    // Cheap: rebuild just this pane's control strip.
    const grid = $('#paneGrid');
    const box = grid.children[index];
    if (!box || !box.classList.contains('pane')) return;
    const pane = XF.panes[index], sess = sessionOf(pane);
    if (!sess) return;
    // Guarded: a rebuild triggered while an earlier one was still in flight
    // could find the node it meant to replace already gone, and replaceChild
    // throws NotFoundError for that. Nothing here is worth an exception.
    const old = box.querySelector('.pane-ctl');
    if (!old || !old.isConnected || old.parentNode !== box) return;
    const strip = paneControls(index, pane, sess);
    const left = old.scrollLeft;
    old.replaceWith(strip);
    wireStripScroll(strip);
    strip.scrollLeft = left;      // stay where the user had scrolled to

    // Swapping the strip can change its height, which restretches the canvas
    // underneath it. Redraw once the new height is in effect or the traces
    // drift away from everything positioned in DOM pixels.
    requestAnimationFrame(() => redrawGeometry(index));
  }

  /* Re-fit and repaint a pane at its current size, without re-fetching. */
  function redrawGeometry(index) {
    const pane = XF.panes[index];
    const sess = sessionOf(pane);
    if (!pane || !sess) return;
    if (pane.panel === 'traces') {
      if (pane._win || sess.win) drawPane(index);
      drawMini(index, pane, sess);
    } else if (pane._panelData) {
      drawRasterGrid(pane, pane._panelData);
    }
  }

  const debouncers = {};
  function refreshPane(index) {
    clearTimeout(debouncers[index]);
    debouncers[index] = setTimeout(() => doRefreshPane(index), 80);
  }

  async function doRefreshPane(index) {
    const pane = XF.panes[index];
    const sess = sessionOf(pane);
    if (!pane || !sess) return;

    if (pane.panel === 'video') { syncVideo(pane, sess); return; }
    if (pane.panel === 'tracking') { drawTracking(index, pane, sess); return; }

    if (pane.panel === 'traces') {
      await fetchTraces(index, pane, sess);
    } else {
      await fetchImagePanel(index, pane, sess);
    }
    drawMini(index, pane, sess);
  }

  async function fetchTraces(index, pane, sess) {
    if (!sess.sel.size) { sess.win = null; drawPane(index); return; }
    // Per-PANE request id. A per-session counter made two panes onto the same
    // recording cancel one another, so whichever asked second was the only one
    // that ever rendered.
    const id = (pane._req = (pane._req || 0) + 1);
    if (pane._loading) pane._loading.classList.remove('hidden');
    const px = Math.max(200, Math.floor((pane._canvas ? pane._canvas.clientWidth : 900) - 70));
    try {
      const win = await apiPost('/api/csc/window', {
        path: sess.path, even_only: sess.evenOnly, invert: sess.invert,
        t0: sess.t0, t1: sess.t0 + sess.span,
        channels: Array.from(sess.sel).sort((a, b) => a - b),
        px, highpass: sess.hp, lowpass: sess.lp, notch: sess.notch,
        mode: 'voltage', spacing_um: sess.spacing,
        bad_channels: Array.from(sess.bad),
        ylim: sess.ylim,
      });
      if (id !== pane._req) return;
      sess.win = win;
      pane._win = win;
      showPanelInput(pane, {
        input: [fmtTime(win.t0) + '\u2013' + fmtTime(win.t1)
                + ' (' + round(win.t1 - win.t0, 2) + ' s)',
                win.series.length + ' ch',
                filterWords(sess),
                sess.bad.size ? sess.bad.size + ' bad marked' : null,
                sess.invert ? 'inverted' : null,
                sess.evenOnly ? 'even only' : null,
               ].filter(Boolean).join('  \u00b7  '),
      });
      // Drawing is separated from fetching so a render fault is reported as
      // one, instead of being mistaken for a failed request.
      try {
        drawPane(index);
      } catch (err) {
        reportClientError('drawPane', err.message, err.stack);
      }
    } catch (e) {
      if (id === pane._req) toast(e.message, 'err');
    } finally {
      if (pane._loading) pane._loading.classList.add('hidden');
    }
  }

  async function fetchImagePanel(index, pane, sess) {
    if (!sess.sel.size && isChannelPanel(pane.panel)) return;
    const id = (pane._req = (pane._req || 0) + 1);
    if (pane._loading) pane._loading.classList.remove('hidden');
    try {
      const spec = {
        path: sess.path, even_only: sess.evenOnly, invert: sess.invert,
        panel: pane.panel, t0: sess.t0, t1: sess.t0 + sess.span,
        channels: Array.from(sess.sel).sort((a, b) => a - b),
        highpass: sess.hp, lowpass: sess.lp, notch: sess.notch,
        cmap: pane.cmap || 'jet', spacing_um: sess.spacing,
        bad_channels: Array.from(sess.bad),
        max_cols: 1800,
        clim: pane.clim || sess.clim || null,
      };
      if (pane.panel === 'spectrogram' || pane.panel === 'scalogram') {
        // Multi-channel: an explicit list wins, else the pane's single
        // channel, else whatever is selected in the session.
        spec.tf_channels = (pane.tfChannels && pane.tfChannels.length)
          ? pane.tfChannels
          : [pane.channel != null ? pane.channel : firstSel(sess)];
        spec.tf_mode = pane.tfMode
          || (spec.tf_channels.length > 1 ? 'stack' : 'mean');
        spec.fmin = pane.fmin != null ? pane.fmin : 20;
        spec.fmax = pane.fmax != null ? pane.fmax : 1000;
        // Display crop, applied after the transform -- see freqViewControl.
        if (pane.fviewMin != null) spec.fview_min = pane.fviewMin;
        if (pane.fviewMax != null) spec.fview_max = pane.fviewMax;
      }
      const res = await apiPost('/api/panel', spec);
      if (id !== pane._req) return;
      pane._panelData = res;
      if (pane._img) pane._img.src = res.image;
      showPanelInfo(pane, res);
      // The load handler covers the normal path; this covers a cached image
      // whose load event fired before the data was assigned.
      drawRasterGrid(pane, res);
    } catch (e) {
      if (id === pane._req) {
        if (pane._img) pane._img.removeAttribute('src');
        showPanelError(pane, e.message);
      }
    } finally {
      if (pane._loading) pane._loading.classList.add('hidden');
    }
  }

  /* Thin time and channel rules over a raster.

     The panel image is pixel data with no axes of its own, so the ruler is an
     overlay canvas -- which also keeps it crisp when the pane is resized. */
  function drawRasterGrid(pane, res) {
    const c = pane._grid;
    res = res || pane._panelData;
    if (!c || !res || !res.extent) return;
    sizePaneCanvas(c);
    const ctx = c.getContext('2d');
    const P = palette();
    const dpr = window.devicePixelRatio || 1;
    const w = c.width / dpr, h = c.height / dpr;
    ctx.clearRect(0, 0, w, h);
    if (pane.grid === false) return;

    const t0 = res.extent[0], t1 = res.extent[1];
    const span = t1 - t0;
    if (!(span > 0)) return;

    const rows = res.rows || [];
    const labelW = rows.length ? 52 : 0;

    /* Guidelines, not a grid.

       A single pale line disappears into the warm end of jet, which is what
       made these invisible on a CSD; a heavy dark halo under a bright line
       reads as a cage over the data, which is what they were before that. The
       middle is a pair of hairlines, one dark and one light, sitting side by
       side: against any background one of the two has contrast, and together
       they are still only two pixels of low-alpha ink. */
    const rule = (x0, y0, x1, y1, dark, light) => {
      ctx.strokeStyle = 'rgba(0,0,0,' + dark + ')';
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
      ctx.strokeStyle = 'rgba(255,255,255,' + light + ')';
      const dx = x0 === x1 ? 1 : 0, dy = y0 === y1 ? 1 : 0;
      ctx.beginPath();
      ctx.moveTo(x0 + dx, y0 + dy); ctx.lineTo(x1 + dx, y1 + dy); ctx.stroke();
    };

    const ticks = niceTicks(t0, t1, Math.max(3, Math.floor(w / 120)));
    ctx.font = '9px ' + MONO;
    ctx.textAlign = 'center';
    ctx.lineWidth = 1;
    for (const t of ticks) {
      const x = Math.round(((t - t0) / span) * w) + 0.5;
      rule(x, 0, x, h - 14, 0.22, 0.30);

      const lbl = fmtTick(t, span);
      const tw = ctx.measureText(lbl).width;
      ctx.fillStyle = 'rgba(0,0,0,0.6)';
      ctx.fillRect(x - tw / 2 - 3, h - 13, tw + 6, 12);
      ctx.fillStyle = 'rgba(255,255,255,0.92)';
      ctx.fillText(lbl, x, h - 4);
    }

    /* Channel rules and labels. Without them a stacked raster is an anonymous
       block of color -- you cannot tell which band is which electrode. */
    if (rows.length > 1) {
      const lane = h / rows.length;
      const compact = lane < 13;
      ctx.textAlign = 'left';
      ctx.lineWidth = 1;
      for (let i = 0; i < rows.length; i++) {
        const yTop = Math.round(i * lane) + 0.5;
        if (i > 0) {
          // Every fourth boundary a touch stronger, so rows can be counted
          // without every one of them competing with the data.
          const major = !(i % 4);
          rule(0, yTop, w, yTop, major ? 0.24 : 0.15, major ? 0.34 : 0.21);
        }
        // Label every lane when there is room, then every second or fourth
        // as they tighten -- a label on every one of 64 rows is a wall of
        // text over the data.
        const every = lane >= 16 ? 1 : (lane >= 9 ? 2 : 4);
        if (i % every) continue;
        const r = rows[i];
        const text = r.label + (r.bad ? ' (bad)' : '');
        const ty = i * lane + Math.min(lane - 3, 11);
        const tw = ctx.measureText(text).width;
        ctx.fillStyle = 'rgba(0,0,0,0.45)';
        ctx.fillRect(2, ty - 9, tw + 6, 11);
        ctx.fillStyle = r.bad ? '#ffcf8a' : 'rgba(255,255,255,0.82)';
        ctx.fillText(text, 5, ty);
      }
    } else if (res.log_freq || (res.freqs && res.freqs.length === 2)) {
      // A single time-frequency panel: mark decades / a few frequencies.
      const [f0, f1] = res.freqs;
      if (f0 > 0 && f1 > f0) {
        ctx.textAlign = 'left';
        const marks = niceLogTicks(f0, f1);
        for (const f of marks) {
          const frac = res.log_freq
            ? (Math.log10(f / f0) / Math.log10(f1 / f0))
            : ((f - f0) / (f1 - f0));
          const y = Math.round((1 - frac) * h) + 0.5;
          ctx.lineWidth = 1;
          rule(0, y, w, y, 0.20, 0.28);
          const lbl = f >= 1000 ? (f / 1000) + 'k' : String(f);
          const tw = ctx.measureText(lbl).width;
          ctx.fillStyle = 'rgba(0,0,0,0.6)';
          ctx.fillRect(2, y - 10, tw + 6, 11);
          ctx.fillStyle = '#fff';
          ctx.fillText(lbl, 5, y - 1);
        }
      }
    }

    drawOverlayMarks(ctx, pane, res, w, h, t0, span, P);
  }

  /* 1-2-5 ticks on a log frequency axis. */
  function niceLogTicks(f0, f1) {
    const out = [];
    for (let d = Math.floor(Math.log10(f0)); d <= Math.ceil(Math.log10(f1)); d++) {
      for (const m of [1, 2, 5]) {
        const f = m * Math.pow(10, d);
        if (f >= f0 && f <= f1) out.push(f);
      }
    }
    return out;
  }

  /* Events, bookmarks and spike marks over a raster, so an image panel carries
     the same annotations the traces do. */
  function drawOverlayMarks(ctx, pane, res, w, h, t0, span, P) {
    const sess = sessionOf(pane);
    if (!sess) return;
    const X = (t) => Math.round(((t - t0) / span) * w) + 0.5;

    ctx.save();
    for (const ev of (sess.events || [])) {
      if (ev.start < t0 || ev.start > t0 + span) continue;
      if (!eventVisible(sess, ev)) continue;
      ctx.strokeStyle = eventColor(sess, ev, P);
      ctx.globalAlpha = 0.75;
      ctx.lineWidth = 1.2;
      ctx.setLineDash([4, 3]);
      const x = X(ev.start);
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
    }
    ctx.setLineDash([]);

    for (const st of (sess.spikeSets || [])) {
      ctx.strokeStyle = P.accent; ctx.globalAlpha = 0.8; ctx.lineWidth = 1.2;
      for (const ev of (st.events || [])) {
        if (ev.start < t0 || ev.start > t0 + span) continue;
        const x = X(ev.start);
        ctx.beginPath(); ctx.moveTo(x, h - Math.min(22, h * 0.16));
        ctx.lineTo(x, h); ctx.stroke();
      }
    }
    if (sess.spikeDraft) {
      ctx.strokeStyle = P.warn; ctx.globalAlpha = 0.45; ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      for (const ev of (sess.spikeDraft.events || [])) {
        if (ev.start < t0 || ev.start > t0 + span) continue;
        const x = X(ev.start);
        ctx.beginPath(); ctx.moveTo(x, h - Math.min(22, h * 0.16));
        ctx.lineTo(x, h); ctx.stroke();
      }
      ctx.setLineDash([]);
    }

    for (const bm of (sess.bookmarks || [])) {
      if (bm.t < t0 || bm.t > t0 + span) continue;
      const x = X(bm.t);
      ctx.strokeStyle = P.accent; ctx.globalAlpha = 0.9; ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
      ctx.fillStyle = P.accent;
      ctx.beginPath();
      ctx.moveTo(x, 1); ctx.lineTo(x + 7, 5); ctx.lineTo(x, 9);
      ctx.closePath(); ctx.fill();
    }
    ctx.restore();
  }

  function showPanelInfo(pane, res) {
    if (!pane._readout) return;
    const bits = [res.units];
    if (res.clim) bits.push('[' + sig(res.clim[0]) + ', ' + sig(res.clim[1]) + ']');
    if (res.channel) {
      bits.unshift(res.channel.label);
    } else if ((res.channels_used || []).length) {
      const used = res.channels_used;
      bits.unshift(used.length + ' ch (' + res.tf_mode + '): '
        + used.slice(0, 6).map((c) => c.label).join(', ')
        + (used.length > 6 ? '…' : ''));
    }
    pane._readout.textContent = bits.join('  ');
    pane._readout.classList.add('on');

    // What this analysis actually ran on. Panels follow the window, the
    // channel selection and the filters that are on screen, which is the
    // right default -- but it means the same panel says different things ten
    // seconds apart, so it should carry the question with its answer.
    showPanelInput(pane, res);
  }

  function showPanelInput(pane, res) {
    const host = pane._canvas ? pane._canvas.parentNode
                              : (pane._img && pane._img.parentNode);
    if (!host) return;
    let n = pane._inputLine;
    if (!n) {
      n = pane._inputLine = el('div', { class: 'panel-input' });
      host.appendChild(n);
    }
    let text = res.input || '';
    if (res.freq_cropped && res.freqs && res.freqs_computed) {
      text += '  \u00b7  showing ' + sig(res.freqs[0]) + '\u2013'
            + sig(res.freqs[1]) + ' Hz of ' + sig(res.freqs_computed[0])
            + '\u2013' + sig(res.freqs_computed[1]) + ' computed';
    }
    n.textContent = text;
    n.classList.toggle('hidden', !text);
  }

  /* The filter band in words, matching how the server describes it. */
  function filterWords(sess) {
    const hp = sess.hp || 0, lp = sess.lp || 0, nt = sess.notch || 0;
    let band;
    if (hp && lp) band = hp + '\u2013' + lp + ' Hz';
    else if (hp) band = '>' + hp + ' Hz';
    else if (lp) band = '<' + lp + ' Hz';
    else band = 'unfiltered';
    return band + (nt ? ' +' + nt + 'Hz notch' : '');
  }

  function showPanelError(pane, msg) {
    if (!pane._readout) return;
    pane._readout.textContent = msg.slice(0, 140);
    pane._readout.classList.add('on');
    pane._readout.style.color = 'var(--err)';
    pane._readout.style.maxWidth = '70%';
    pane._readout.style.whiteSpace = 'normal';
  }

  /* ==================================================================
     Time window control
     ================================================================== */
  function clampWin(sess, t0, span) {
    const dur = sess.info.duration_s || 0;
    const sp = clamp(span, 0.001, Math.max(0.002, dur || 1e9));
    return [clamp(t0, 0, Math.max(0, dur - sp)), sp];
  }

  /* The window a pane is actually showing.

     Independent mode gives each pane its own; otherwise the window lives on
     the session, which is why two panes onto one recording stay in step
     without any extra machinery. */
  function winOf(pane, sess) {
    if (XF.linkMode === 'none' && pane && pane.t0 != null) {
      return { t0: pane.t0, span: pane.span };
    }
    return { t0: sess.t0, span: sess.span };
  }

  function setWindow(index, t0, span, fromRemote) {
    const pane = typeof index === 'number' ? XF.panes[index] : null;
    const sess = pane ? sessionOf(pane) : index;   // allow a session directly
    if (!sess) return;

    if (XF.linkMode === 'none' && pane) {
      [pane.t0, pane.span] = clampWin(sess, t0, span);
      // Mirror onto the session so it is what gets saved and restored.
      sess.t0 = pane.t0; sess.span = pane.span;
      refreshPane(XF.panes.indexOf(pane));
      refreshControls(XF.panes.indexOf(pane));
    } else if (XF.linkMode === 'all') {
      for (const id of XF.order) {
        const o = XF.sessions[id];
        [o.t0, o.span] = clampWin(o, t0, span);
      }
      XF.panes.forEach((p) => { if (p) { p.t0 = null; p.span = null; } });
      refreshAll();
      XF.panes.forEach((p, i) => refreshControls(i));
      if (!fromRemote) publishLink(t0, span, sess);
    } else {
      [sess.t0, sess.span] = clampWin(sess, t0, span);
      XF.panes.forEach((p, i) => {
        if (p && p.sessionId === sess.id) { p.t0 = null; p.span = null; }
      });
      refreshSession(sess);
      XF.panes.forEach((p, i) => {
        if (p && p.sessionId === sess.id) refreshControls(i);
      });
      // The other half of a within-session pair may be in another window.
      if (!fromRemote) publishLink(sess.t0, sess.span, sess);
    }
    BARRY.activity.log('window.change',
      { t0: round(t0, 4), span: round(span, 4), scope: XF.linkMode }, sess);
    queueSaveState(sess);
  }

  function pan(index, frac) {
    const pane = XF.panes[index], sess = sessionOf(pane);
    if (!sess) return;
    const w = winOf(pane, sess);
    setWindow(index, w.t0 + w.span * frac, w.span);
  }

  function zoom(index, factor, anchorFrac) {
    const pane = XF.panes[index], sess = sessionOf(pane);
    if (!sess) return;
    const w = winOf(pane, sess);
    const a = anchorFrac === undefined ? 0.5 : anchorFrac;
    const anchorT = w.t0 + w.span * a;
    const span = clamp(w.span * factor, 0.001,
                       Math.max(0.002, sess.info.duration_s || 1e9));
    setWindow(index, anchorT - span * a, span);
  }

  /* ---------- cross-window "Link time" ---------- */
  const LINK_ID = 'w' + Math.random().toString(36).slice(2, 9);
  let linkSeen = 0;
  let linkPoll = null;
  let linkSending = false;

  /* Which shared slot a session's time window travels on.

     Keyed on the session identity rather than the path, so the same recording
     opened from a different mount still lands on the same channel. */
  function linkChannel(sess) {
    if (XF.linkMode === 'all') return 'time';
    const id = sess && sess.identity ? sess.identity : {};
    return 'time:' + (id.key || id.loose_key || (sess && sess.path) || 'unknown');
  }

  async function publishLink(t0, span, sess) {
    if (XF.linkMode === 'none' || linkSending) return;
    linkSending = true;
    try {
      const res = await apiPost('/api/link', {
        channel: linkChannel(sess), origin: LINK_ID,
        value: {
          t0, span, mode: XF.linkMode,
          gain: sess.gain, hp: sess.hp, lp: sess.lp, notch: sess.notch,
          ylim: sess.ylim, normalize: sess.normalize,
          // Which channels are shown is part of the view, so a linked pane in
          // another window should be looking at the same ones.
          channels: Array.from(sess.sel).sort((a, b) => a - b),
          bad: Array.from(sess.bad).sort((a, b) => a - b),
        },
      });
      // Record our own version so the poller does not echo it back at us.
      if (res.slot) linkSeen = Math.max(linkSeen, res.slot.version);
    } catch (e) {
      /* linking is best-effort */
    } finally {
      linkSending = false;
    }
  }

  function applyRemote(sess, v) {
    const dur = sess.info.duration_s || 0;
    sess.span = clamp(v.span, 0.001, Math.max(0.002, dur || 1e9));
    sess.t0 = clamp(v.t0, 0, Math.max(0, dur - sess.span));

    // Gain, filters and a pinned axis are session properties too, so a linked
    // pane in another window should match on all of them, not just the window.
    if (isFinite(v.gain) && v.gain > 0) sess.gain = v.gain;
    if (isFinite(v.hp)) sess.hp = v.hp;
    if (isFinite(v.lp)) sess.lp = v.lp;
    if (isFinite(v.notch)) sess.notch = v.notch;
    if (v.normalize) sess.normalize = v.normalize;
    sess.ylim = (v.ylim === null || v.ylim === undefined) ? null : v.ylim;

    if (Array.isArray(v.channels)) {
      const n = sess.info.channels.length;
      sess.sel = new Set(v.channels.filter((i) => i >= 0 && i < n));
    }
    if (Array.isArray(v.bad)) sess.bad = new Set(v.bad.map(Number));

    // A remote change is a session-level move, so per-pane overrides go.
    XF.panes.forEach((p) => {
      if (p && p.sessionId === sess.id) { p.t0 = null; p.span = null; }
    });
  }

  async function pollLink() {
    if (XF.linkMode === 'none' || !XF.order.length) return;
    let data;
    try { data = await api('/api/link?since=' + linkSeen); } catch (e) { return; }
    linkSeen = Math.max(linkSeen, data.version || 0);
    const channels = data.channels || {};

    let touched = false;

    if (XF.linkMode === 'all') {
      const slot = channels.time;
      if (slot && slot.origin !== LINK_ID && slot.value) {
        const v = slot.value;
        if (isFinite(v.t0) && isFinite(v.span)) {
          for (const id of XF.order) applyRemote(XF.sessions[id], v);
          touched = true;
        }
      }
    } else {
      // Within-session: each open recording listens on its own channel.
      for (const id of XF.order) {
        const sess = XF.sessions[id];
        const slot = channels[linkChannel(sess)];
        if (!slot || slot.origin === LINK_ID || !slot.value) continue;
        const v = slot.value;
        if (!isFinite(v.t0) || !isFinite(v.span)) continue;
        applyRemote(sess, v);
        touched = true;
      }
    }

    if (!touched) return;
    refreshAll();
    XF.panes.forEach((p, i) => refreshControls(i));
  }

  /* Three scopes, because "linked" means two different things:
       none     every pane scrolls on its own
       session  panes showing the SAME recording move together -- including
                panes that have been popped out into their own window
       all      every pane moves together, across recordings and windows */
  function setLink(mode) {
    XF.linkMode = ['none', 'session', 'all'].includes(mode) ? mode : 'session';
    $('#xfLinkWrap').classList.toggle('on', XF.linkMode !== 'none');
    const sel = $('#xfLinkMode');
    if (sel && sel.value !== XF.linkMode) sel.value = XF.linkMode;

    clearInterval(linkPoll);
    linkPoll = null;

    if (XF.linkMode === 'none') {
      // Seed each pane from its session so nothing jumps on the switch.
      XF.panes.forEach((p) => {
        const o = sessionOf(p);
        if (p && o) { p.t0 = o.t0; p.span = o.span; }
      });
      render();
    } else {
      // Both linked scopes need the poll: a popped-out window is the only way
      // the other half of a "within session" pair can hear about a change.
      linkPoll = setInterval(pollLink, 400);
      const s = active();
      if (s) setWindow(XF.focused, s.t0, s.span);
    }
    try { localStorage.setItem('barry.linkMode', XF.linkMode); } catch (e) { /* ignore */ }
    BARRY.activity.log('link.scope', { scope: XF.linkMode });
  }

  /* ---------- everything is saved by default ---------- */
  const saveTimers = {};
  function queueSaveState(sess) {
    clearTimeout(saveTimers[sess.id]);
    saveTimers[sess.id] = setTimeout(() => saveState(sess), 1200);
  }

  async function saveState(sess) {
    if (!sess.identity || (sess.identity.mouse == null && !sess.identity.key)) return;
    try {
      await apiPost('/api/session/state', {
        identity: sess.identity,
        state: {
          t0: sess.t0, span: sess.span, gain: sess.gain,
          hp: sess.hp, lp: sess.lp, notch: sess.notch,
          normalize: sess.normalize, spacing: sess.spacing,
          ylim: sess.ylim, clim: sess.clim,
          channels: Array.from(sess.sel).sort((a, b) => a - b),
        },
      });
    } catch (e) { /* non-fatal */ }
  }

  /* ---------- native Neuralynx event files ---------- */
  async function autoImportNev(sess) {
    if (!sess.nev || !sess.nev.length || sess.events.length) return;
    const file = sess.nev[0];
    try {
      const res = await apiPost('/api/events/nev', {
        path: file.path, session_path: sess.path,
      });
      if (!res.n) return;
      sess.events = res.events;
      sess.eventsMeta = { path: file.path, n: res.n, source: 'nev',
                          relative_to: res.relative_to, labels: res.labels };
      ensureClasses(sess);
      restoreEventClasses(sess);
      render();
      refreshSession(sess);
      const rel = res.relative_to === 'recording' ? '' :
        ' (times relative to the first event -- no CSC clock available)';
      toast('Loaded ' + res.n + ' events from ' + file.name + rel, 'ok', 5000);
      BARRY.activity.log('events.import', {
        file: file.name, n: res.n, source: 'nev',
        relative_to: res.relative_to, auto: true,
      }, sess);
    } catch (e) {
      toast('Could not read ' + file.name + ': ' + e.message, 'err', 7000);
    }
  }


  /* ==================================================================
     Canvas drawing (traces)
     ================================================================== */
  // Trace panes reserve a wider left gutter: the channel checkboxes live
  // inside it, right next to the trace each one controls.
  const PAD = { l: 58, r: 12, t: 8, b: 24 };
  const PAD_TRACES_L = 112;

  /* Height of the channel-column header, fixed in CSS as .ch-top.

     This used to be measured from the DOM, but positioning the rows changes
     that same layout -- so each draw measured a slightly different header and
     the lanes and checkboxes never converged. A constant shared by the CSS and
     the canvas removes the feedback entirely. */
  const CH_HEADER_H = 104;

  function padTopOf(index) {
    const grid = $('#paneGrid');
    const box = grid && grid.children[index];
    if (!box || !box.querySelector('.ch-list')) return PAD.t;
    return CH_HEADER_H;
  }

  function palette() {
    const cs = getComputedStyle(document.documentElement);
    const get = (n, fb) => (cs.getPropertyValue(n) || fb).trim();
    return {
      bg: get('--bg', '#0a1310'), grid: get('--line-soft', '#1a3227'),
      text: get('--text-2', '#a3bdb0'), dim: get('--text-3', '#6f8c7d'),
      trace: get('--trace', '#7FE3B0'), warn: get('--warn', '#ED8B33'),
      event: get('--event', '#FF8A7A'), accent: get('--accent', '#FFB81C'),
    };
  }

  function sizePaneCanvas(c) {
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    // Measure the CANVAS, not its parent. With height:100% inside a flex item
    // the two can disagree, and drawing against one while positioning DOM
    // against the other is what pulled the channel rows off their lanes.
    const r = c.getBoundingClientRect();
    const w = Math.round(r.width), h = Math.round(r.height);
    if (!w || !h) return;
    c.width = Math.max(1, Math.round(w * dpr));
    c.height = Math.max(1, Math.round(h * dpr));
    c.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  /* Redraw when a pane changes size.

     A canvas keeps the bitmap it was drawn at; CSS then stretches it to fit
     the new box, so the traces silently scale while everything laid out in DOM
     pixels does not. That mismatch is what pulled the channel rows off their
     lanes whenever the control strip re-wrapped. */
  function watchResize(node, index) {
    if (!window.ResizeObserver) return;
    const pane = XF.panes[index];
    if (!pane) return;
    let timer = null;
    const ro = new ResizeObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const p = XF.panes[index];
        if (!p || !p._canvas) return;      // pane was torn down
        if (p.panel === 'traces') {
          drawPane(index);
          drawMini(index, p, sessionOf(p));
        } else if (p._panelData) {
          drawRasterGrid(p, p._panelData);
        }
      }, 60);
    });
    ro.observe(node);
    (pane._teardown = pane._teardown || []).push(() => {
      clearTimeout(timer);
      ro.disconnect();
    });
  }

  function drawPane(index) {
    const pane = XF.panes[index], sess = sessionOf(pane);
    if (!pane || !sess || pane.panel !== 'traces' || !pane._canvas) return;
    const canvas = pane._canvas;
    sizePaneCanvas(canvas);
    const ctx = canvas.getContext('2d');
    const P = palette();
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.width / dpr, h = canvas.height / dpr;

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = P.bg; ctx.fillRect(0, 0, w, h);

    const win = pane._win || sess.win;
    if (!win || !win.series || !win.series.length) {
      ctx.fillStyle = P.dim; ctx.font = '12px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(sess.sel.size ? 'Loading…' : 'No channels selected.', w / 2, h / 2);
      return;
    }

    const padTop = PAD.t;
    const padL = PAD_TRACES_L;
    const plotW = w - padL - PAD.r, plotH = h - padTop - PAD.b;
    const n = win.series.length, lane = plotH / n;

    // Remember the lane geometry so the channel checkboxes can be lined up
    // with the traces they control.
    pane._geom = { top: padTop, padBottom: PAD.b, lane, n,
                   labels: win.series.map((x) => x.number) };
    pane._padTop = padTop;
    try {
      alignChannelRows(index);
    } catch (err) {
      // Lining the checkboxes up is cosmetic; it must never stop the traces.
      reportClientError('alignChannelRows', err.message, err.stack);
    }

    const ticks = niceTicks(win.t0, win.t1, Math.max(2, Math.floor(plotW / 100)));
    ctx.strokeStyle = P.grid; ctx.lineWidth = 1;
    ctx.font = '9px ' + MONO; ctx.fillStyle = P.dim; ctx.textAlign = 'center';
    for (const t of ticks) {
      const x = padL + ((t - win.t0) / (win.t1 - win.t0)) * plotW;
      ctx.beginPath(); ctx.moveTo(Math.round(x) + .5, padTop);
      ctx.lineTo(Math.round(x) + .5, padTop + plotH); ctx.stroke();
      ctx.fillText(fmtTick(t, win.t1 - win.t0), x, h - 8);
    }

    drawEventMarks(ctx, sess, win, padL, plotW, padTop, plotH, P);
    drawSpikeMarks(ctx, sess, win, padL, plotW, padTop, plotH, P);
    drawBookmarkMarks(ctx, sess, win, padL, plotW, padTop, plotH, P);
    // Curation draws last, over everything, because while you are curating
    // it is the only thing you are looking at.
    if (BARRY.curate && BARRY.curate.draw) {
      BARRY.curate.draw(ctx, sess, win, padL, plotW, padTop, plotH, P);
    }
    if (BARRY.strata && BARRY.strata.draw) {
      BARRY.strata.draw(ctx, sess, win, padL, plotW, padTop, plotH, P);
    }

    // A pinned amplitude is applied here rather than fetched. The server
    // echoes ylim back as robust_max, but the envelope it returns does not
    // depend on it -- so honouring it locally makes the amplitude slider
    // instant instead of one request per pixel of drag.
    const shared = (sess.ylim != null ? sess.ylim : win.robust_max) || 1;
    const npts = win.n_points, dx = npts > 1 ? plotW / (npts - 1) : plotW;
    ctx.textAlign = 'right';

    for (let i = 0; i < n; i++) {
      const s = win.series[i];
      const mid = padTop + lane * (i + .5);
      const scale = sess.normalize === 'per' ? (localMax(s) || 1) : shared;
      const k = (lane * .44) * sess.gain / scale;
      const isBad = s.bad || sess.bad.has(s.number);
      const color = isBad ? P.warn : P.trace;

      ctx.strokeStyle = P.grid; ctx.globalAlpha = .45;
      ctx.beginPath(); ctx.moveTo(padL, Math.round(mid) + .5);
      ctx.lineTo(padL + plotW, Math.round(mid) + .5); ctx.stroke();
      ctx.globalAlpha = 1;

      ctx.fillStyle = color;
      ctx.beginPath();
      let started = false;
      for (let j = 0; j < npts; j++) {
        const v = s.max[j]; if (v === null) continue;
        const x = padL + j * dx, y = clampY(mid - v * k, padTop, padTop + plotH);
        if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
      }
      for (let j = npts - 1; j >= 0; j--) {
        const v = s.min[j]; if (v === null) continue;
        ctx.lineTo(padL + j * dx, clampY(mid - v * k, padTop, padTop + plotH));
      }
      if (started) { ctx.closePath(); ctx.fill(); }

      // Zoomed in, the envelope collapses below a pixel; the midline keeps the
      // trace visible at every scale.
      ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.lineJoin = 'round';
      ctx.beginPath(); started = false;
      for (let j = 0; j < npts; j++) {
        const lo = s.min[j], hi = s.max[j];
        if (lo === null || hi === null) { started = false; continue; }
        const x = padL + j * dx, y = clampY(mid - (lo + hi) * .5 * k, padTop, padTop + plotH);
        if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
  }

  function drawEventMarks(ctx, sess, win, x0, plotW, y0, plotH, P) {
    if (!sess.events.length) return;
    const span = win.t1 - win.t0;
    let shown = 0;
    for (const ev of sess.events) {
      const s = ev.start;
      if (s < win.t0 || s > win.t1) continue;
      if (!eventVisible(sess, ev)) continue;
      const color = eventColor(sess, ev, P);
      const x = x0 + ((s - win.t0) / span) * plotW;
      if (ev.end && ev.end > s) {
        const xe = x0 + ((Math.min(ev.end, win.t1) - win.t0) / span) * plotW;
        ctx.fillStyle = color; ctx.globalAlpha = .14;
        ctx.fillRect(x, y0, Math.max(1, xe - x), plotH);
        ctx.globalAlpha = 1;
      }
      ctx.strokeStyle = color; ctx.globalAlpha = .6;
      ctx.setLineDash([4, 3]);
      ctx.beginPath(); ctx.moveTo(Math.round(x) + .5, y0);
      ctx.lineTo(Math.round(x) + .5, y0 + plotH); ctx.stroke();
      ctx.setLineDash([]); ctx.globalAlpha = 1;
      if (++shown > 900) break;
    }
  }

  /* Line each channel row up with its trace.

     A plain scrolling list drifts out of step with the canvas as soon as the
     lane height stops matching the row height, which is what made the
     checkboxes and the traces disagree. So the rows are positioned from the
     canvas geometry instead of being laid out independently. */
  /* Channel rows, placed on their traces.

     Positions come straight from the lane geometry the canvas just used, in
     the canvas host's own coordinate space -- so a row is on its trace by
     construction rather than by two layouts happening to agree. */
  function alignChannelRows(index) {
    const pane = XF.panes[index];
    const host = pane && pane._overlay;
    if (!pane || !host || !pane._geom) return;

    const { labels, top, padBottom } = pane._geom;
    const sess = sessionOf(pane);
    if (!sess) return;

    const byNumber = new Map(sess.info.channels.map((c) => [c.number, c]));
    const rows = labels.map((num) => byNumber.get(num)).filter(Boolean);
    if (!rows.length) { host.innerHTML = ''; return; }

    // The rows are a grid of equal fractions inside the same top and bottom
    // insets the canvas draws with, rather than a list of absolute pixel
    // offsets. Absolute offsets were computed once per draw and went stale the
    // moment the pane changed height -- the canvas restretched, the rows did
    // not, and the labels drifted a lane or two off their traces by the
    // bottom of a 32-channel session. As a grid the browser keeps them
    // proportional for free, so they track a resize even between redraws.
    host.style.width = (PAD_TRACES_L - 6) + 'px';
    host.style.paddingTop = top + 'px';
    host.style.paddingBottom = padBottom + 'px';
    // minmax(0, 1fr), not 1fr: a bare 1fr keeps an automatic minimum of the
    // row's own content height, so 32 rows of 18px refused to fit into 549px
    // of plot and each one sat 0.85 px lower than its trace -- a 27 px drift
    // by the bottom channel. A zero floor lets them divide the space.
    host.style.gridTemplateRows =
      'repeat(' + rows.length + ', minmax(0, 1fr))';

    const lane = pane._geom.lane;
    const compact = lane < 15;            // no room for a checkbox in the lane

    host.innerHTML = '';
    for (const c of rows) {
      const isBad = sess.bad.has(c.number) || c.bad;
      host.appendChild(el('label', {
        class: 'ch-lane' + (isBad ? ' marked-bad' : '') + (compact ? ' compact' : ''),
        title: c.label + (isBad ? '  (marked bad)' : ''),
      }, [
        el('input', {
          type: 'checkbox', checked: 'checked',
          title: 'Hide this channel',
          onchange: () => {
            sess.sel.delete(c.index);
            render(); refreshSession(sess);
            BARRY.activity.log('channels.change',
              { hidden: c.label, n: sess.sel.size }, sess);
            queueSaveState(sess);
            publishLink(sess.t0, sess.span, sess);
          },
        }),
        el('span', { class: 'nm', text: c.label }),
        compact ? null : el('button', {
          class: 'badbtn', text: isBad ? 'BAD' : 'ok',
          title: isBad ? 'Marked bad -- click to clear' : 'Mark this channel bad',
          onclick: (e) => {
            e.preventDefault(); e.stopPropagation();
            toggleBad(sess, c.number);
          },
        }),
      ]));
    }
  }

  /* Threshold-detector marks.

     A draft is faint and dashed; committing makes the marks solid. That
     difference is the point -- you can see at a glance whether what is on
     screen has been saved. */
  function drawSpikeMarks(ctx, sess, win, x0, plotW, y0, plotH, P) {
    const span = win.t1 - win.t0;
    const draw = (events, committed) => {
      ctx.save();
      ctx.strokeStyle = committed ? P.accent : P.warn;
      ctx.globalAlpha = committed ? 0.85 : 0.4;
      ctx.lineWidth = committed ? 1.4 : 1;
      if (!committed) ctx.setLineDash([3, 3]);
      const tick = Math.min(26, plotH * 0.18);
      let shown = 0;
      for (const ev of events) {
        const t = ev.start;
        if (t < win.t0 || t > win.t1) continue;
        const x = Math.round(x0 + ((t - win.t0) / span) * plotW) + 0.5;
        ctx.beginPath();
        ctx.moveTo(x, y0 + plotH - tick);
        ctx.lineTo(x, y0 + plotH);
        ctx.stroke();
        if (++shown > 900) break;
      }
      ctx.restore();
    };
    for (const st of (sess.spikeSets || [])) draw(st.events || [], true);
    if (sess.spikeDraft) draw(sess.spikeDraft.events || [], false);
  }

  function drawBookmarkMarks(ctx, sess, win, x0, plotW, y0, plotH, P) {
    if (!sess.bookmarks || !sess.bookmarks.length) return;
    const span = win.t1 - win.t0;
    ctx.save();
    ctx.font = '9px ' + MONO;
    for (const bm of sess.bookmarks) {
      if (bm.t < win.t0 || bm.t > win.t1) continue;
      const x = Math.round(x0 + ((bm.t - win.t0) / span) * plotW) + 0.5;
      ctx.strokeStyle = P.accent;
      ctx.globalAlpha = 0.7;
      ctx.beginPath();
      ctx.moveTo(x, y0); ctx.lineTo(x, y0 + plotH);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillStyle = P.accent;
      const label = ' ⚑ ' + bm.name;
      const flip = (x + ctx.measureText(label).width + 4) > (x0 + plotW);
      ctx.textAlign = flip ? 'right' : 'left';
      ctx.fillText(label, flip ? x - 2 : x + 2, y0 + 9);
    }
    ctx.restore();
  }

  function localMax(s) {
    let m = 0;
    for (let j = 0; j < s.max.length; j++) {
      if (s.max[j] !== null) m = Math.max(m, Math.abs(s.max[j]));
      if (s.min[j] !== null) m = Math.max(m, Math.abs(s.min[j]));
    }
    return m;
  }

  /* ---------- minimap ---------- */
  function drawMini(index, pane, sess) {
    const c = pane._mini;
    if (!c) return;
    sizePaneCanvas(c);
    const ctx = c.getContext('2d');
    const P = palette();
    const w = c.clientWidth, h = c.clientHeight;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = P.bg; ctx.fillRect(0, 0, w, h);

    const dur = sess.info.duration_s || 1;

    // The recording's own amplitude, behind everything else.
    const ov = sess.overview;
    if (ov && ov.rms && ov.rms.length) {
      const top = 3, bot = h - 13;
      const mid = (top + bot) / 2, halfH = (bot - top) / 2;
      let peak = 0;
      for (const v of ov.hi) peak = Math.max(peak, Math.abs(v));
      for (const v of ov.lo) peak = Math.max(peak, Math.abs(v));
      if (peak > 0) {
        const bw = w / ov.bins;
        ctx.fillStyle = P.grid || P.dim;
        ctx.globalAlpha = .5;
        for (let i = 0; i < ov.bins; i++) {
          const a = (ov.hi[i] / peak) * halfH;
          const b = (ov.lo[i] / peak) * halfH;
          ctx.fillRect(i * bw, mid - a, Math.max(1, bw), Math.max(1, a - b));
        }
        // RMS on top, so loud stretches read even at this size.
        let rpeak = 0;
        for (const v of ov.rms) rpeak = Math.max(rpeak, v);
        if (rpeak > 0) {
          ctx.globalAlpha = .8;
          ctx.strokeStyle = P.dim;
          ctx.lineWidth = 1;
          ctx.beginPath();
          for (let i = 0; i < ov.bins; i++) {
            const y = bot - (ov.rms[i] / rpeak) * (bot - top) * .92;
            if (i === 0) ctx.moveTo(0, y); else ctx.lineTo(i * bw, y);
          }
          ctx.stroke();
        }
        ctx.globalAlpha = 1;
      }
    } else {
      loadOverview(sess);
    }

    if (sess.events.length) {
      ctx.globalAlpha = .6;
      for (const ev of sess.events) {
        if (!eventVisible(sess, ev)) continue;
        ctx.fillStyle = eventColor(sess, ev, P);
        ctx.fillRect((ev.start / dur) * w, 4, 1, h - 15);
      }
      ctx.globalAlpha = 1;
    }

    // Committed sets, drafts and bookmarks belong on the overview strip too --
    // that is where you go looking for the next thing to inspect.
    for (const st of (sess.spikeSets || [])) {
      ctx.fillStyle = P.accent; ctx.globalAlpha = 0.5;
      for (const ev of (st.events || [])) ctx.fillRect((ev.start / dur) * w, h - 12, 1, 7);
      ctx.globalAlpha = 1;
    }
    if (sess.spikeDraft) {
      ctx.fillStyle = P.warn; ctx.globalAlpha = 0.45;
      for (const ev of (sess.spikeDraft.events || [])) {
        ctx.fillRect((ev.start / dur) * w, h - 12, 1, 7);
      }
      ctx.globalAlpha = 1;
    }
    for (const bm of (sess.bookmarks || [])) {
      const bx = (bm.t / dur) * w;
      ctx.fillStyle = P.accent;
      ctx.beginPath();
      ctx.moveTo(bx, 2); ctx.lineTo(bx + 4, 6); ctx.lineTo(bx, 10);
      ctx.closePath(); ctx.fill();
    }

    const wnow = winOf(pane, sess);
    const x0 = (wnow.t0 / dur) * w, x1 = ((wnow.t0 + wnow.span) / dur) * w;
    ctx.fillStyle = P.accent; ctx.globalAlpha = .2;
    ctx.fillRect(x0, 3, Math.max(2, x1 - x0), h - 13);
    ctx.globalAlpha = 1;
    ctx.strokeStyle = P.accent; ctx.lineWidth = 1;
    ctx.strokeRect(Math.round(x0) + .5, 3.5, Math.max(2, x1 - x0), h - 14);

    ctx.fillStyle = P.dim; ctx.font = '8px ' + MONO;
    ctx.textAlign = 'left'; ctx.fillText('0', 3, h - 3);
    ctx.textAlign = 'right'; ctx.fillText(fmtTime(dur), w - 3, h - 3);
    ctx.textAlign = 'center';
    ctx.fillText(fmtTime(sess.t0) + ' → ' + fmtTime(sess.t0 + sess.span)
                 + (sess.events.length ? '  ·  ' + sess.events.length + ' events' : '')
                 + (ov && ov.channel ? '  ·  ' + ov.channel.label : ''),
                 w / 2, h - 3);
  }

  /* ==================================================================
     Interaction
     ================================================================== */
  function wireTraceCanvas(index, pane, sess, canvas, readout) {
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const frac = clamp((e.clientX - rect.left - PAD_TRACES_L) /
                         Math.max(1, rect.width - PAD_TRACES_L - PAD.r), 0, 1);
      if (e.shiftKey) {
        sess.gain = clamp(sess.gain * (e.deltaY < 0 ? 1.18 : 1 / 1.18), .02, 200);
        drawPane(index); refreshControls(index);
      } else {
        zoom(index, e.deltaY > 0 ? 1.22 : 1 / 1.22, frac);
      }
    }, { passive: false });

    let drag = null;
    canvas.addEventListener('mousedown', (e) => {
      XF.focused = index; XF.active = pane.sessionId;
      if (e.altKey) { addEventAt(sess, canvas, e); return; }
      if (XF.measure || XF.placing) return;   // another handler owns this drag
      const w0 = winOf(pane, sess);
      drag = { x: e.clientX, t0: w0.t0, span: w0.span };
      canvas.style.cursor = 'grabbing';
    });
    const move = (e) => {
      if (drag) {
        const rect = canvas.getBoundingClientRect();
        const plotW = Math.max(1, rect.width - PAD_TRACES_L - PAD.r);
        setWindow(index, drag.t0 - ((e.clientX - drag.x) / plotW) * drag.span,
                  drag.span);
        return;
      }
      hoverTraces(pane, sess, canvas, readout, e);
    };
    const up = () => { if (drag) { drag = null; canvas.style.cursor = 'crosshair'; } };
    onPane(pane, window, 'mousemove', move);
    onPane(pane, window, 'mouseup', up);
    canvas.addEventListener('mouseleave', () => readout.classList.remove('on'));
    // Registered last, in the capture phase, so a measure drag can swallow
    // the event before the pan handler above sees it.
    wireMeasure(index, pane, sess, canvas);
  }

  function addEventAt(sess, canvas, e) {
    const rect = canvas.getBoundingClientRect();
    const plotW = rect.width - PAD_TRACES_L - PAD.r;
    const frac = clamp((e.clientX - rect.left - PAD_TRACES_L) / plotW, 0, 1);
    const t = sess.t0 + frac * sess.span;
    sess.events.push({ start: t, label: 'manual' });
    sess.events.sort((a, b) => a.start - b.start);
    ensureClasses(sess);
    saveEventClasses(sess);
    BARRY.activity.log('events.mark', { t: round(t, 4) }, sess);
    render(); refreshSession(sess);
    toast('Marked an event at ' + fmtTime(t) + ' (alt-click)', 'ok', 2200);
  }

  function hoverTraces(pane, sess, canvas, readout, e) {
    const win = pane._win || sess.win;
    if (!win || !win.series.length) { readout.classList.remove('on'); return; }
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left, y = e.clientY - rect.top;
    const padTop = PAD.t;
    const padL = PAD_TRACES_L;
    const plotW = rect.width - padL - PAD.r, plotH = rect.height - padTop - PAD.b;
    if (x < padL || x > padL + plotW || y < padTop || y > padTop + plotH) {
      readout.classList.remove('on'); return;
    }
    const frac = (x - padL) / plotW;
    const t = win.t0 + frac * (win.t1 - win.t0);
    const lane = plotH / win.series.length;
    const idx = clamp(Math.floor((y - padTop) / lane), 0, win.series.length - 1);
    const s = win.series[idx];
    const j = clamp(Math.round(frac * (win.n_points - 1)), 0, win.n_points - 1);
    const lo = s.min[j], hi = s.max[j];
    const v = (lo === null || hi === null) ? null : (lo + hi) / 2;
    readout.textContent = s.label + '  ' + fmtTime(t) + '  '
      + (v === null ? '—' : sig(v) + ' ' + win.units);
    readout.classList.add('on');
  }

  function wireImagePane(index, pane, sess, host) {
    host.addEventListener('wheel', (e) => {
      e.preventDefault();
      const rect = host.getBoundingClientRect();
      const frac = clamp((e.clientX - rect.left) / rect.width, 0, 1);
      zoom(index, e.deltaY > 0 ? 1.22 : 1 / 1.22, frac);
    }, { passive: false });

    let drag = null;
    host.addEventListener('mousedown', (e) => {
      XF.focused = index; XF.active = pane.sessionId;
      if (XF.placing) return;              // the placement handler owns it
      const w0 = winOf(pane, sess);
      drag = { x: e.clientX, t0: w0.t0, span: w0.span };
      host.style.cursor = 'grabbing';
    });
    const move = (e) => {
      if (!drag) return;
      const rect = host.getBoundingClientRect();
      setWindow(index, drag.t0 - ((e.clientX - drag.x) / rect.width) * drag.span,
                drag.span);
    };
    const up = () => { if (drag) { drag = null; host.style.cursor = ''; } };
    onPane(pane, window, 'mousemove', move);
    onPane(pane, window, 'mouseup', up);
  }

  function wireMini(index, pane, sess, mini) {
    const jump = (e) => {
      const rect = mini.getBoundingClientRect();
      const frac = clamp((e.clientX - rect.left) / rect.width, 0, 1);
      const w = winOf(pane, sess);
      setWindow(index, frac * (sess.info.duration_s || 0) - w.span / 2, w.span);
    };
    mini.addEventListener('mousedown', (e) => {
      jump(e);
      const mv = (ev) => jump(ev);
      const up = () => {
        window.removeEventListener('mousemove', mv);
        window.removeEventListener('mouseup', up);
      };
      window.addEventListener('mousemove', mv);
      window.addEventListener('mouseup', up);
    });
    setTimeout(() => drawMini(index, pane, sess), 30);
  }

  /* ==================================================================
     Video + tracking panes
     ================================================================== */
  function buildVideo(sess) {
    const box = el('div', { class: 'video-box' });
    const vids = sess.media.videos || [];
    if (!vids.length) {
      box.appendChild(el('div', { class: 'video-msg',
        text: 'No video file beside this recording.' }));
      return box;
    }
    if (!sess._video) sess._video = vids[0];
    if (sess._videoOffset === undefined) sess._videoOffset = 0;

    // Neuralynx writes MPEG-1, which no browser decodes, so those files have
    // to go through ffmpeg. Saying so here beats a spinner that never stops.
    const needsFfmpeg = vids.some((x) => !x.native);
    const haveFfmpeg = !!(BARRY.state.catalog && BARRY.state.catalog.ffmpeg);
    if (needsFfmpeg && !haveFfmpeg) {
      box.appendChild(el('div', { class: 'video-msg' }, [
        el('strong', { text: 'This video needs ffmpeg' }),
        el('p', { text: vids[0].name + ' is MPEG-1, which browsers cannot play. '
                      + 'BARRY transcodes a few seconds at a time, but ffmpeg '
                      + 'was not found on this machine.' }),
        el('p', { text: 'Run the setup script, or install ffmpeg and restart '
                      + 'BARRY. Everything else works without it.' }),
      ]));
      return box;
    }

    const v = el('video', { controls: 'controls', preload: 'metadata' });
    const status = el('div', { class: 'video-status hidden' });
    sess._videoEl = v;
    sess._videoStatus = status;

    // A failed clip request returns JSON with a 400, which the element reports
    // only as a generic error. Read the body and show what actually happened,
    // rather than leaving it loading forever.
    v.addEventListener('error', async () => {
      const url = v.currentSrc || v.src;
      if (!url) return;
      let msg = 'The browser could not play this clip.';
      try {
        const res = await fetch(url);
        if (!res.ok) {
          const data = await res.json();
          msg = data.error || msg;
        }
      } catch (e) { /* keep the generic message */ }
      videoStatus(sess, msg, 'err');
    });
    v.addEventListener('loadeddata', () => videoStatus(sess, ''));

    const bar = el('div', { class: 'vbar' }, [
      el('select', {
        onchange: (e) => {
          sess._video = vids.find((x) => x.path === e.target.value) || vids[0];
          syncVideoNow(sess, true);
        },
      }, vids.map((x) => el('option', {
        value: x.path, text: x.name + ' (' + fmtBytes(x.bytes) + ')',
        selected: sess._video.path === x.path ? 'selected' : null,
      }))),
      el('span', { text: 'offset' }),
      el('input', {
        type: 'number', step: '0.1', value: String(sess._videoOffset),
        style: 'width:64px;padding:2px 5px;border-radius:4px;border:1px solid var(--line);background:var(--bg);color:var(--text);font-family:var(--mono);font-size:10px',
        title: 'Seconds to shift video time relative to recording time',
        onchange: (e) => { sess._videoOffset = parseFloat(e.target.value) || 0; syncVideoNow(sess, true); },
      }),
      el('span', { text: 's' }),
      el('div', { style: 'flex:1' }),
      el('button', { class: 'mini', text: 'Sync to cursor',
                     onclick: () => syncVideoNow(sess, true) }),
    ]);

    box.appendChild(v);
    box.appendChild(status);
    box.appendChild(bar);
    syncVideoNow(sess, true);
    return box;
  }

  function videoStatus(sess, text, kind) {
    const n = sess._videoStatus;
    if (!n) return;
    n.textContent = text || '';
    n.className = 'video-status' + (text ? '' : ' hidden') + (kind ? ' ' + kind : '');
  }

  function syncVideo(pane, sess) { syncVideoNow(sess, false); }

  /* Fetching a transcoded clip costs an ffmpeg run, so it is worth only doing
     when it is actually needed. */
  function syncVideoNow(sess, force) {
    const v = sess._videoEl, f = sess._video;
    if (!v || !f) return;

    if (f.native) {
      // Playable directly: load once and just seek.
      const url = '/api/video/clip?path=' + encodeURIComponent(f.path);
      if (v.dataset.src !== url) { v.dataset.src = url; v.src = url; }
      const seek = () => {
        try { v.currentTime = Math.max(0, sess.t0 + sess._videoOffset); }
        catch (e) { /* not seekable yet */ }
      };
      if (v.readyState >= 1) seek();
      else v.addEventListener('loadedmetadata', seek, { once: true });
      return;
    }

    const clipLen = Math.min(Math.max(sess.span * 3, 4), 60);
    const want = sess.t0 + sess._videoOffset;

    // Already covered. Every pan used to change the cache key and start
    // another transcode, so dragging the window queued a pile of multi-second
    // ffmpeg runs that each replaced the last -- the video appeared to load
    // forever. If the cursor is still inside the clip on screen, just seek
    // within it: no request at all.
    const have = sess._videoClip;
    if (!force && have && have.path === f.path
        && want >= have.start + 0.15 && want <= have.end - 0.15) {
      try { v.currentTime = Math.max(0, want - have.start); } catch (e) { /* not ready */ }
      return;
    }

    // Coalesce: a drag emits a refresh per frame, and only the last one
    // matters. Requests are also serialized, so ffmpeg is never asked for two
    // clips at once.
    clearTimeout(sess._videoTimer);
    sess._videoTimer = setTimeout(() => {
      const start = Math.max(0, want - clipLen * 0.25);
      const url = '/api/video/clip?' + new URLSearchParams({
        path: f.path, t0: (sess.t0 - clipLen * 0.25).toFixed(3),
        duration: clipLen.toFixed(1),
        offset: sess._videoOffset, width: 640,
      }).toString();
      if (v.dataset.src === url && !force) return;
      v.dataset.src = url;
      sess._videoClip = { path: f.path, start, end: start + clipLen };
      videoStatus(sess, 'Transcoding ' + clipLen.toFixed(0)
                        + ' s around ' + fmtTime(sess.t0) + '\u2026');
      v.src = url;
    }, force ? 0 : 450);
  }

  async function loadTracking(index, pane, sess) {
    const tf = (sess.media.tracking || [])[0];
    if (!tf) return;
    if (sess._tracking) { drawTracking(index, pane, sess); return; }
    try {
      sess._tracking = await apiPost('/api/video/tracking', { path: tf.path });
      drawTracking(index, pane, sess);
    } catch (e) {
      toast('Tracking: ' + e.message, 'err');
    }
  }

  function drawTracking(index, pane, sess) {
    const c = pane._track, tr = sess._tracking;
    if (!c || !tr) return;
    sizePaneCanvas(c);
    const ctx = c.getContext('2d');
    const P = palette();
    const w = c.clientWidth, h = c.clientHeight;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = P.bg; ctx.fillRect(0, 0, w, h);

    const bx = tr.bounds.x, by = tr.bounds.y;
    const pad = 18;
    const sx = (w - pad * 2) / Math.max(1, bx[1] - bx[0]);
    const sy = (h - pad * 2) / Math.max(1, by[1] - by[0]);
    const sc = Math.min(sx, sy);
    const X = (v) => pad + (v - bx[0]) * sc;
    const Y = (v) => pad + (v - by[0]) * sc;

    // Whole path, faint.
    ctx.strokeStyle = P.grid; ctx.lineWidth = 1;
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < tr.t.length; i++) {
      if (tr.x[i] === null) { started = false; continue; }
      const px = X(tr.x[i]), py = Y(tr.y[i]);
      if (!started) { ctx.moveTo(px, py); started = true; } else ctx.lineTo(px, py);
    }
    ctx.stroke();

    // The current window, bright, with the cursor position as a dot.
    ctx.strokeStyle = P.accent; ctx.lineWidth = 1.8;
    ctx.beginPath(); started = false;
    let cur = null;
    for (let i = 0; i < tr.t.length; i++) {
      const t = tr.t[i];
      if (t < sess.t0 || t > sess.t0 + sess.span) continue;
      if (tr.x[i] === null) { started = false; continue; }
      const px = X(tr.x[i]), py = Y(tr.y[i]);
      if (!started) { ctx.moveTo(px, py); started = true; } else ctx.lineTo(px, py);
      cur = [px, py];
    }
    ctx.stroke();
    if (cur) {
      ctx.fillStyle = P.accent;
      ctx.beginPath(); ctx.arc(cur[0], cur[1], 4.5, 0, Math.PI * 2); ctx.fill();
    }

    ctx.fillStyle = P.dim; ctx.font = '9px ' + MONO; ctx.textAlign = 'left';
    ctx.fillText(tr.name + '  ' + tr.n + ' pts  ' + tr.fps + ' fps  '
                 + Math.round(tr.lost_frac * 100) + '% lost', 8, h - 7);
  }

  /* ==================================================================
     Filter presets
     ================================================================== */
  async function loadPresets() {
    try {
      const f = await api('/api/presets/filters');
      XF.presets.filters = f.presets || [];
    } catch (e) { /* non-fatal */ }
  }

  async function saveFilterPreset(sess) {
    const name = await askPath('Name this filter preset',
                               'e.g. "IED tight" or "Ripple 150-250"');
    if (!name) return;
    try {
      const res = await apiPost('/api/presets/filters', {
        preset: {
          name, highpass: sess.hp, lowpass: sess.lp, notch: sess.notch,
          note: 'HP ' + sess.hp + ' / LP ' + sess.lp + ' / notch ' + sess.notch,
        },
      });
      XF.presets.filters = res.presets || [];
      XF.panes.forEach((p, i) => refreshControls(i));
      toast('Saved preset "' + name + '" to GUI_logs', 'ok');
      BARRY.refreshSync();
    } catch (e) {
      toast(e.message, 'err');
    }
  }

  /* ==================================================================
     Helpers
     ================================================================== */
  const MONO = 'ui-monospace, Consolas, monospace';
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const clampY = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
  const round = (v, n) => Math.round(v * Math.pow(10, n)) / Math.pow(10, n);

  function sig(v) {
    if (v === null || !isFinite(v)) return '—';
    const a = Math.abs(v);
    if (a === 0) return '0';
    if (a >= 1000 || a < 0.01) return v.toExponential(2);
    return v.toFixed(a < 1 ? 3 : a < 100 ? 2 : 1);
  }

  function niceTicks(a, b, want) {
    const span = b - a;
    if (!(span > 0)) return [a];
    const raw = span / Math.max(1, want);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
    const out = [];
    for (let t = Math.ceil(a / step) * step; t <= b + 1e-12; t += step) out.push(t);
    return out;
  }

  function fmtTick(t, span) {
    if (span < 0.02) return (t * 1000).toFixed(1) + 'ms';
    if (span < 2) return t.toFixed(3) + 's';
    if (span < 120) return t.toFixed(2) + 's';
    return fmtTime(t);
  }

  async function pickFolder() {
    const p = await pickPath('folder', '');
    if (p) openSession(p);
  }

  /* ==================================================================
     Init
     ================================================================== */
  function init() {
    wireDropzone($('#xfDrop'), openSession);
    $('#xfPickFolder').addEventListener('click', pickFolder);
    $('#xfAddSession').addEventListener('click', pickFolder);
    $('#xfPickFile').addEventListener('click', async () => {
      const p = await pickPath('file', '');
      if (p) openSession(p);
    });
    $('#xfGoSessions').addEventListener('click', () => setView('sessions'));

    // The View menu reuses the strip's popover, so there is one way a menu
    // behaves in this section rather than two.
    $('#xfView').addEventListener('click', (e) => {
      e.stopPropagation();
      const btn = e.currentTarget;
      const wasMine = openMenu && openMenu.button === btn;
      closeMenu();
      if (wasMine) return;
      const node = el('div', { class: 'ctl-pop' }, [viewMenu()]);
      document.body.appendChild(node);
      btn.classList.add('active');
      const r = btn.getBoundingClientRect();
      node.style.left = Math.max(8, Math.min(
        r.right - node.offsetWidth, window.innerWidth - node.offsetWidth - 8))
        + 'px';
      node.style.top = (r.bottom + 6) + 'px';
      const away = (evt) => {
        if (!node.contains(evt.target) && !btn.contains(evt.target)) closeMenu();
      };
      const esc = (evt) => { if (evt.key === 'Escape') closeMenu(); };
      openMenu = { node, button: btn, away, esc };
      setTimeout(() => {
        document.addEventListener('mousedown', away, true);
        document.addEventListener('keydown', esc, true);
        window.addEventListener('resize', closeMenu);
      }, 0);
    });
    $('#xfFigure').addEventListener('click', () => {
      if (!XF.order.length) { toast('Open a session first.', 'err'); return; }
      BARRY.figure.open(XF, active());
    });

    $$('#xfLayoutSeg button').forEach((b) =>
      b.addEventListener('click', () => {
        XF.nPanes = +b.dataset.panes;
        $$('#xfLayoutSeg button').forEach((x) => x.classList.toggle('active', x === b));
        // Fill new panes with the sessions already open.
        for (let i = 0; i < XF.nPanes; i++) {
          if (!XF.panes[i] && XF.order[i]) {
            XF.panes[i] = { sessionId: XF.order[i], panel: DEFAULT_PANEL };
          }
        }
        render();
        refreshAll();
      }));

    $('#xfLinkMode').addEventListener('change', (e) => setLink(e.target.value));

    document.addEventListener('keydown', (e) => {
      if (BARRY.state.view !== 'xplore') return;
      if (isTyping(e)) return;
      const s = active();
      if (!s) return;
      const fi = XF.focused;
      const gainBy = (f) => {
        s.gain = clamp(s.gain * f, .02, 200);
        refreshAll();
        XF.panes.forEach((_p, i) => refreshControls(i));
      };
      const map = {
        ArrowLeft: () => pan(fi, e.shiftKey ? -1 : -0.25),
        ArrowRight: () => pan(fi, e.shiftKey ? 1 : 0.25),
        ArrowUp: () => gainBy(1.3),
        ArrowDown: () => gainBy(1 / 1.3),
        '-': () => zoom(fi, 1.5), '_': () => zoom(fi, 1.5),
        '=': () => zoom(fi, 1 / 1.5), '+': () => zoom(fi, 1 / 1.5),
        // Navigation and tools, so the common moves need no mouse at all.
        n: () => stepEvent(fi, 1),
        p: () => stepEvent(fi, -1),
        m: () => setMeasure(!XF.measure),
        b: () => addBookmark(fi, s),
        Home: () => setWindow(fi, 0, winOf(XF.panes[fi], s).span),
        End: () => {
          const w = winOf(XF.panes[fi], s);
          setWindow(fi, (s.info.duration_s || 0) - w.span, w.span);
        },
        Escape: () => {
          if (XF.placing) setPlacing(false);
          else if (XF.measure) setMeasure(false);
        },
      };
      if (map[e.key]) { e.preventDefault(); map[e.key](); }
    });

    window.addEventListener('resize', debounce(() => {
      if (XF.order.length) refreshAll();
    }, 180));

    let savedMode = new URLSearchParams(location.search).get('link');
    if (!savedMode) {
      try { savedMode = localStorage.getItem('barry.linkMode'); } catch (e) { /* ignore */ }
    }
    setLink(savedMode || 'session');

    /* A pop-out arrives with instructions.

       `chrome` says what to put away -- a pop-out is a second screen showing
       one recording, so the tab bar is pointless in it by default. `full`
       asks for the whole monitor, which a browser will only grant off the
       back of a gesture, so it waits for the first click rather than being
       refused on load. */
    const params = new URLSearchParams(location.search);
    const chrome = params.get('chrome');
    if (chrome) {
      const off = chrome === 'none'
        ? ['channels', 'strip', 'heads', 'tabs']
        : chrome.split(',').map((k) => k.replace(/^no/, ''));
      for (const k of off) {
        if (k in XF.chrome) XF.chrome[k] = false;
      }
    }
    applyChrome();
    if (params.get('full')) {
      const once = () => {
        document.removeEventListener('click', once);
        goFullscreen(document.getElementById('view-xplore'));
      };
      document.addEventListener('click', once);
      toast('Click anywhere to go full screen.', null, 8000);
    }

    loadPresets();
    api('/api/panels').then((d) => {
      XF.panelDefs = d.panels || [];
      XF.colormaps = d.colormaps || [];
      if (XF.order.length) render();
    }).catch(() => {});
  }

  /* Put every open session on screen if the layout can hold them.

     Called after a multi-select open, so picking three recordings in the
     Sessions view lands you on a filled 4-up grid instead of one pane and two
     idle tabs. */
  function fillPanes() {
    if (XF.order.length > 1 && XF.nPanes === 1) {
      XF.nPanes = XF.order.length >= 3 ? 4 : 2;
      $$('#xfLayoutSeg button').forEach((b) =>
        b.classList.toggle('active', +b.dataset.panes === XF.nPanes));
    }
    for (let i = 0; i < XF.nPanes; i++) {
      if (!XF.panes[i] && XF.order[i]) {
        XF.panes[i] = { sessionId: XF.order[i], panel: DEFAULT_PANEL };
      }
    }
    render();
    refreshAll();
  }

  return {
    init,
    open: openSession,
    addBankedEvents,
    fillPanes,
    state: XF,
    refreshAll,
    render,
    setWindow,
    // Repaint what is already loaded. Curation redraws its overlay on every
    // keystroke; going back to the server for the same samples would make
    // the fastest part of the job the slowest.
    redraw: (index) => {
      if (index === undefined) {
        for (let i = 0; i < XF.nPanes; i++) drawPane(i);
      } else drawPane(index);
    },
    // Curation mode needs to arrange the panes for its own job, and to move
    // the window to each candidate. Exposed rather than reimplemented, so
    // there is one function that knows how a pane is built.
    setPanes: (specs, split) => {
      XF.nPanes = Math.max(1, Math.min(4, specs.length));
      XF.panes = specs.slice(0, XF.nPanes).map((p) => Object.assign(
        { sessionId: XF.active }, p));
      // Applied before the render that reads it, or the first paint uses the
      // old proportions and then jumps.
      if (split) XF.split = split;
      $$('#xfLayoutSeg button').forEach(
        (b) => b.classList.toggle('active', +b.dataset.panes === XF.nPanes));
      render();
      refreshAll();
    },
    onShow: () => { if (XF.order.length) { render(); refreshAll(); } },
  };
})();
