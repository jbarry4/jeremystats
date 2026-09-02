/* ==========================================================================
   storyboard.js -- assemble results into a narrated deck.

   A slide is a 16:9 canvas holding items placed in fractional coordinates, so
   the same deck renders identically on screen and in the exported PDF. Items
   are results from the catalog, pasted images, text boxes, shapes, highlights
   and freehand ink. Every slide carries notes, shown beneath the canvas and
   printed under the figure.

   Everything is stored as JSON in GUI_logs/storyboards, one file per deck, so
   decks merge through git like the rest of the state.

   Editing model: pick a tool, drag on the canvas. Items are moved and resized
   by dragging them or their handles. Nothing is committed to disk until you
   save, but a dirty deck is autosaved a few seconds after you stop editing so
   a closed tab does not lose work.
   ========================================================================== */
'use strict';

BARRY.views.storyboard = (function () {
  let decks = [];
  let deck = null;             // the open deck
  let slideIndex = 0;
  let tool = 'select';         // select | text | rect | ellipse | arrow | line | highlight | ink
  let selectedItem = null;
  let dirty = false;
  let saveTimer = null;
  let drag = null;
  let inkStroke = null;
  let results = [];
  let pending = [];            // results handed over from the Results view
  let guides = [];             // snap guides shown mid-drag
  let snap = true;

  /* Undo history.

     Every edit already funnels through markDirty(), so that is where the
     snapshot is taken -- one place rather than forty call sites, none of
     which can then be forgotten. What gets pushed is the state BEFORE the
     edit, kept in `shadow`, because by the time markDirty runs the change has
     already happened.

     Snapshots are whole-deck JSON. A deck is a few kilobytes; the alternative
     is a command log that has to describe every kind of edit, and would get
     one of them wrong. */
  const UNDO_LIMIT = 60;
  let undoStack = [];
  let redoStack = [];
  let shadow = null;

  const COLORS = ['#c0392b', '#FFB81C', '#154734', '#1f6feb', '#8250df',
                   '#0f766e', '#111827', '#ffffff'];

  /* ==================================================================
     Deck lifecycle
     ================================================================== */
  async function loadDecks() {
    try {
      const res = await api('/api/decks');
      decks = res.decks || [];
    } catch (e) { decks = []; }
  }

  function newDeck(title) {
    return {
      title: title || 'Untitled deck',
      slides: [blankSlide('Slide 1')],
    };
  }

  function blankSlide(title) {
    return { id: 's' + Math.random().toString(36).slice(2, 9),
             title: title || '', notes: '', items: [], show_notes: true };
  }

  async function openDeck(id) {
    resetHistory();
    try {
      const res = await api('/api/deck/' + encodeURIComponent(id));
      deck = res.deck;
      slideIndex = 0;
      selectedItem = null;
      dirty = false;
      render();
    } catch (e) { toast(e.message, 'err'); }
  }

  function snapshot() {
    return deck ? JSON.stringify({ title: deck.title, slides: deck.slides }) : null;
  }

  function resetHistory() {
    undoStack = [];
    redoStack = [];
    shadow = snapshot();
  }

  function restore(json, label) {
    const state = JSON.parse(json);
    deck.title = state.title;
    deck.slides = state.slides;
    slideIndex = Math.max(0, Math.min(slideIndex, deck.slides.length - 1));
    selectedItem = null;
    shadow = snapshot();
    dirty = true;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => save(true), 2500);
    render();
    BARRY.activity.log('deck.' + label,
                       { deck: deck.id, undo: undoStack.length,
                         redo: redoStack.length });
  }

  function undo() {
    if (!undoStack.length) { toast('Nothing to undo.', null, 1800); return; }
    redoStack.push(snapshot());
    restore(undoStack.pop(), 'undo');
    toast('Undone', null, 1400);
  }

  function redo() {
    if (!redoStack.length) { toast('Nothing to redo.', null, 1800); return; }
    undoStack.push(snapshot());
    restore(redoStack.pop(), 'redo');
    toast('Redone', null, 1400);
  }

  function markDirty(action, detail) {
    // Push what it looked like before this edit.
    if (shadow) {
      undoStack.push(shadow);
      if (undoStack.length > UNDO_LIMIT) undoStack.shift();
      redoStack = [];      // a new edit invalidates the redo branch
    }
    shadow = snapshot();
    if (action) {
      BARRY.activity.log('deck.' + action,
                         Object.assign({ deck: deck && deck.id }, detail || {}));
    }
    dirty = true;
    clearTimeout(saveTimer);
    // Autosave a few seconds after editing stops: losing a deck to a closed
    // tab would be far worse than an extra write.
    saveTimer = setTimeout(() => save(true), 2500);
    const badge = $('#sbDirty');
    if (badge) badge.classList.remove('hidden');
    const u = $('#sbUndo'), r = $('#sbRedo');
    if (u) u.disabled = !undoStack.length;
    if (r) r.disabled = !redoStack.length;
  }

  async function save(quiet) {
    if (!deck) return;
    clearTimeout(saveTimer);
    try {
      const res = await apiPost('/api/deck', { deck });
      deck.id = res.deck.id;
      deck.updated = res.deck.updated;
      dirty = false;
      const badge = $('#sbDirty');
      if (badge) badge.classList.add('hidden');
      await loadDecks();
      renderDeckBar();
      if (!quiet) toast('Saved "' + deck.title + '"', 'ok');
      BARRY.refreshSync();
    } catch (e) {
      toast('Could not save: ' + e.message, 'err', 8000);
    }
  }

  /* ==================================================================
     Handing results in from the Results view
     ================================================================== */
  function addResults(chosen) {
    pending = (chosen || []).slice();
    if (!deck) deck = newDeck('New deck');
    if (!pending.length) { render(); return; }
    render();
    askPlacement();
  }

  function askPlacement() {
    const n = pending.length;
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Add ' + n + ' result' + (n > 1 ? 's' : '') }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: () => { pending = []; closeModal(); } }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { style: 'font-size:12.5px;color:var(--text-2);line-height:1.6',
          text: n > 1
            ? 'One slide each keeps the narrative moving; a grid on one slide '
              + 'is better for a direct comparison.'
            : 'Put it on a new slide, or drop it onto the slide you are on.' }),
        el('div', { class: 'card-grid', style: 'margin-top:12px' }, [
          choice('One slide each', 'A new slide per result, titled from the result.',
                 () => { placeEachOnOwnSlide(); }),
          n > 1 ? choice('Grid on one slide', 'All of them tiled on a single new slide.',
                 () => { placeAllOnOneSlide(); }) : null,
          choice('On the current slide', 'Added to slide ' + (slideIndex + 1) + '.',
                 () => { placeOnCurrent(); }),
        ]),
      ]),
    ]));
  }

  function choice(title, body, fn) {
    return el('div', { class: 'card' }, [
      el('h3', { text: title }),
      el('p', { text: body }),
      el('div', { class: 'card-actions' }, [
        el('button', { class: 'btn sm', text: 'Do it',
          onclick: () => { closeModal(); fn(); } }),
      ]),
    ]);
  }

  function placeEachOnOwnSlide() {
    for (const r of pending) {
      const sl = blankSlide(r.title || r.name);
      sl.notes = r.notes || '';
      sl.items.push(resultItem(r, 0.08, 0.16, 0.84, 0.72));
      deck.slides.push(sl);
    }
    slideIndex = deck.slides.length - 1;
    pending = [];
    markDirty(); render();
  }

  function placeAllOnOneSlide() {
    const sl = blankSlide('Comparison');
    const n = pending.length;
    const cols = n <= 2 ? n : (n <= 4 ? 2 : 3);
    const rows = Math.ceil(n / cols);
    const pad = 0.03;
    const w = (1 - pad * (cols + 1)) / cols;
    const h = (0.82 - pad * (rows + 1)) / rows;
    pending.forEach((r, i) => {
      const c = i % cols, rw = Math.floor(i / cols);
      sl.items.push(resultItem(r,
        pad + c * (w + pad),
        0.14 + pad + rw * (h + pad), w, h));
    });
    deck.slides.push(sl);
    slideIndex = deck.slides.length - 1;
    pending = [];
    markDirty(); render();
  }

  function placeOnCurrent() {
    const sl = current();
    if (!sl) return placeEachOnOwnSlide();
    pending.forEach((r, i) => {
      sl.items.push(resultItem(r, 0.1 + i * 0.04, 0.2 + i * 0.04, 0.5, 0.45));
    });
    pending = [];
    markDirty(); render();
  }

  function resultItem(r, x, y, w, h) {
    return {
      id: 'i' + Math.random().toString(36).slice(2, 9),
      // rel and name travel with the item on purpose. The id is derived from
      // where the file sits relative to the repo, which is the same
      // everywhere -- but a deck saved before that was true, or one whose
      // file has been moved within Results, still finds its figure by path
      // or by name.
      type: 'result', result_id: r.id, rel: r.rel, name: r.name,
      x, y, w, h, z: 1, caption: '',
    };
  }

  /* Where to fetch a result item's image. */
  function resultSrc(it) {
    const q = new URLSearchParams();
    if (it.result_id) q.set('id', it.result_id);
    if (it.rel) q.set('rel', it.rel);
    if (it.name) q.set('name', it.name);
    return '/api/results/file?' + q.toString();
  }


  /* ======================================================================
     Feature 1 -- Slide layouts
     Placing four panels by dragging four boxes to roughly-equal sizes is
     fiddly and never quite lines up. A layout drops exact frames and fills
     them from the selected results in order.
     ====================================================================== */
  // Frames are fractions of the slide. 'title' frames get a text box.
  const LAYOUTS = [
    { id: 'title', name: 'Title', frames: [
      { kind: 'title', x: .1, y: .34, w: .8, h: .16, size: 40, align: 'center' },
      { kind: 'title', x: .1, y: .53, w: .8, h: .1, size: 18, align: 'center',
        text: 'subtitle' },
    ] },
    { id: 'section', name: 'Section', frames: [
      { kind: 'band', x: 0, y: .4, w: 1, h: .2 },
      { kind: 'title', x: .08, y: .45, w: .84, h: .12, size: 30,
        align: 'left', color: '#ffffff' },
    ] },
    { id: 'one', name: '1 panel', frames: [
      { kind: 'slot', x: .06, y: .17, w: .88, h: .74 },
    ] },
    { id: 'two-h', name: '2 across', frames: [
      { kind: 'slot', x: .04, y: .19, w: .45, h: .7 },
      { kind: 'slot', x: .51, y: .19, w: .45, h: .7 },
    ] },
    { id: 'two-v', name: '2 stacked', frames: [
      { kind: 'slot', x: .12, y: .16, w: .76, h: .37 },
      { kind: 'slot', x: .12, y: .56, w: .76, h: .37 },
    ] },
    { id: 'four', name: '4 up', frames: [
      { kind: 'slot', x: .04, y: .17, w: .45, h: .38 },
      { kind: 'slot', x: .51, y: .17, w: .45, h: .38 },
      { kind: 'slot', x: .04, y: .57, w: .45, h: .38 },
      { kind: 'slot', x: .51, y: .57, w: .45, h: .38 },
    ] },
    { id: 'big-left', name: 'Big + notes', frames: [
      { kind: 'slot', x: .04, y: .17, w: .6, h: .74 },
      { kind: 'title', x: .67, y: .19, w: .29, h: .6, size: 15, align: 'left',
        text: 'Notes beside the figure' },
    ] },
    { id: 'quote', name: 'Quote', frames: [
      { kind: 'title', x: .12, y: .3, w: .76, h: .3, size: 26, align: 'center',
        text: 'The one sentence this slide is for.' },
    ] },
  ];

  function layoutMini(lay) {
    const box = el('div', { class: 'layout-mini' });
    for (const f of lay.frames) {
      box.appendChild(el('i', {
        class: f.kind === 'slot' ? '' : 't',
        style: 'left:' + f.x * 100 + '%;top:' + f.y * 100 + '%;width:'
             + f.w * 100 + '%;height:' + f.h * 100 + '%;'
             + (f.kind === 'band' ? 'background:#154734;' : ''),
      }));
    }
    return box;
  }

  function openLayouts() {
    const chosen = pending.length ? pending : [];
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Slide layouts' }),
        el('span', { class: 'sub',
          text: chosen.length ? chosen.length + ' result(s) waiting to be placed'
                              : 'empty frames you can drop results into' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'layout-grid' }, LAYOUTS.map((lay) =>
          el('div', {
            class: 'layout-card', title: 'Apply "' + lay.name + '"',
            onclick: () => { closeModal(); applyLayout(lay, false); },
          }, [
            layoutMini(lay),
            el('div', { class: 'layout-name', text: lay.name }),
          ]))),
        el('p', { class: 'hint', style: 'margin-top:10px',
          text: 'Applying a layout to a slide that already has content adds '
              + 'the frames around it. Hold the new-slide option to start '
              + 'clean instead.' }),
      ]),
      el('div', { class: 'mf' }, [
        el('label', { class: 'toggle sm on' }, [
          el('input', { type: 'checkbox', id: 'sbLayoutNew' }),
          el('span', { text: 'onto a new slide' }),
        ]),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn', text: 'Close', onclick: closeModal }),
      ]),
    ]));
  }

  function applyLayout(lay, forceNew) {
    const onNew = forceNew
      || (($('#sbLayoutNew') && $('#sbLayoutNew').checked) || false);
    if (onNew) {
      deck.slides.splice(slideIndex + 1, 0,
                         blankSlide('Slide ' + (deck.slides.length + 1)));
      slideIndex += 1;
    }
    const sl = current();
    const queue = pending.slice();
    pending = [];

    for (const f of lay.frames) {
      if (f.kind === 'slot') {
        const r = queue.shift();
        if (r) {
          sl.items.push(resultItem(r, f.x, f.y, f.w, f.h));
        } else {
          // An empty frame is a visible target to drop something into later.
          sl.items.push({
            id: 'i' + Math.random().toString(36).slice(2, 9),
            type: 'shape', shape: 'rect', x: f.x, y: f.y, w: f.w, h: f.h,
            z: 1, color: '#b9cfc4', width: 1, filled: false, alpha: .9,
            placeholder: true,
          });
        }
      } else if (f.kind === 'band') {
        sl.items.push({
          id: 'i' + Math.random().toString(36).slice(2, 9),
          type: 'shape', shape: 'rect', x: f.x, y: f.y, w: f.w, h: f.h,
          z: 0, color: '#154734', width: 0, filled: true, alpha: 1,
        });
      } else {
        sl.items.push({
          id: 'i' + Math.random().toString(36).slice(2, 9),
          type: 'text', x: f.x, y: f.y, w: f.w, h: f.h, z: 5,
          text: f.text || (sl.title || 'Title'),
          size: f.size || 20, color: f.color || '#154734',
          align: f.align || 'left',
        });
      }
    }
    // Anything left over gets its own slide rather than being dropped.
    if (queue.length) {
      pending = queue;
      toast(queue.length + ' result(s) did not fit \u2014 they are still '
            + 'waiting. Apply another layout to place them.', null, 6000);
    }
    markDirty();
    render();
    BARRY.activity.log('deck.layout', { layout: lay.id, deck: deck.id });
  }

  /* ======================================================================
     Feature 2 -- Presenter mode
     The point of the notes field. Full screen, arrow keys, notes below,
     and the same fractional geometry the export uses, so what is on screen
     is what lands in the PDF.
     ====================================================================== */
  let presIndex = 0;

  /* Zoom state, in slide-box pixels.

     Held here rather than on the deck: it is how you are looking at a slide
     right now, not something about the slide, so it should not be saved and
     should not follow the deck to anyone else. */
  const PRES_MIN = 1;          // no zooming out past the slide -- nothing there
  const PRES_MAX = 8;
  let presZoom = 1;
  let presPan = { x: 0, y: 0 };
  let presDrag = null;

  function present(from) {
    presIndex = from || 0;
    presZoom = 1;
    presPan = { x: 0, y: 0 };
    let host = $('#presenter');
    if (!host) {
      host = el('div', { class: 'hidden', id: 'presenter' }, [
        el('div', { class: 'pres-stage' }, [
          el('div', { class: 'pres-slide', id: 'presSlide' }),
        ]),
        el('div', { class: 'pres-notes', id: 'presNotes' }),
        el('div', { class: 'pres-bar' }, [
          el('button', { class: 'btn ghost sm', text: '\u2039 Back',
                         onclick: () => presStep(-1) }),
          el('button', { class: 'btn ghost sm', text: 'Next \u203a',
                         onclick: () => presStep(1) }),
          el('span', { class: 'pres-count', id: 'presCount' }),
          el('div', { style: 'flex:1' }),
          el('div', { class: 'pres-zoom' }, [
            el('button', {
              class: 'btn ghost sm', text: '\u2212',
              title: 'Zoom out  (\u2212)', onclick: () => presScale(1 / 1.4),
            }),
            el('button', {
              class: 'btn ghost sm pres-zval', id: 'presZoom',
              title: 'Back to the whole slide  (0)',
              text: '100%', onclick: presZoomReset,
            }),
            el('button', {
              class: 'btn ghost sm', text: '+',
              title: 'Zoom in  (+)', onclick: () => presScale(1.4),
            }),
          ]),
          el('span', { class: 'pres-count', id: 'presHint',
            text: 'arrows to move  \u00b7  scroll to zoom  \u00b7  '
                + 'esc to leave  \u00b7  f for full screen' }),
          el('button', { class: 'btn ghost sm', text: 'Exit',
                         onclick: presExit }),
        ]),
      ]);
      document.body.appendChild(host);
      document.addEventListener('keydown', presKeys);

      const stage = host.querySelector('.pres-stage');

      /* Scroll to zoom, about the pointer.

         Plain wheel rather than ctrl+wheel: there is nothing else to scroll
         in a presentation, and reaching for a modifier mid-sentence is
         exactly the sort of thing that goes wrong in front of a room. */
      stage.addEventListener('wheel', (e) => {
        e.preventDefault();
        presScale(e.deltaY < 0 ? 1.18 : 1 / 1.18, e.clientX, e.clientY);
      }, { passive: false });

      // Drag to move around, once there is somewhere to move to.
      stage.addEventListener('mousedown', (e) => {
        if (presZoom <= 1) return;
        e.preventDefault();
        presDrag = { x: e.clientX, y: e.clientY,
                     px: presPan.x, py: presPan.y };
        stage.classList.add('dragging');
      });
      window.addEventListener('mousemove', (e) => {
        if (!presDrag) return;
        presPan.x = presDrag.px + (e.clientX - presDrag.x);
        presPan.y = presDrag.py + (e.clientY - presDrag.y);
        presApplyZoom();
      });
      window.addEventListener('mouseup', () => {
        if (!presDrag) return;
        presDrag = null;
        const st = $('#presenter .pres-stage');
        if (st) st.classList.remove('dragging');
      });

      // Double-click zooms in on what was double-clicked, which is the
      // gesture people try first.
      stage.addEventListener('dblclick', (e) => {
        if (presZoom >= PRES_MAX) presZoomReset();
        else presScale(2, e.clientX, e.clientY);
      });
    }
    host.classList.remove('hidden');
    presPaint();
    BARRY.activity.log('deck.present',
                       { deck: deck.id, slides: deck.slides.length });
  }

  function presStep(d) {
    presIndex = Math.max(0, Math.min(deck.slides.length - 1, presIndex + d));
    // A new slide comes up whole. Carrying a zoom across would land the next
    // slide showing a corner of itself for no reason anyone could see.
    presZoomReset();
    presPaint();
  }

  /* Multiply the zoom, keeping the point under (cx, cy) where it is.

     Without the anchor, zooming walks the slide off to one side and the
     thing you were looking at is the first thing to leave. */
  function presScale(factor, cx, cy) {
    const slide = $('#presSlide');
    if (!slide) return;
    const before = presZoom;
    const next = Math.max(PRES_MIN, Math.min(PRES_MAX, before * factor));
    if (next === before) return;

    if (cx !== undefined) {
      const r = slide.getBoundingClientRect();
      // Where the pointer is inside the untransformed slide box.
      const ox = (cx - r.left) / before;
      const oy = (cy - r.top) / before;
      presPan.x -= ox * (next - before);
      presPan.y -= oy * (next - before);
    }
    presZoom = next;
    presApplyZoom();
    BARRY.activity.log('deck.present.zoom',
                       { deck: deck && deck.id, slide: presIndex + 1,
                         zoom: Math.round(next * 100) });
  }

  function presZoomReset() {
    presZoom = 1;
    presPan = { x: 0, y: 0 };
    presApplyZoom();
  }

  function presApplyZoom() {
    const slide = $('#presSlide');
    if (!slide) return;

    // The slide is transformed from its own top-left, so the pan is clamped
    // against the scaled size: at 1x there is nowhere to go, and past that
    // an edge can reach the edge of the stage but not pass it.
    const w = slide.offsetWidth, h = slide.offsetHeight;
    const spare = (v, size) => {
      const room = size * (presZoom - 1);
      return Math.max(-room, Math.min(0, v));
    };
    presPan.x = spare(presPan.x, w);
    presPan.y = spare(presPan.y, h);

    slide.style.transform = 'translate(' + presPan.x + 'px,' + presPan.y
                          + 'px) scale(' + presZoom + ')';
    const label = $('#presZoom');
    if (label) label.textContent = Math.round(presZoom * 100) + '%';
    const stage = $('#presenter .pres-stage');
    if (stage) stage.classList.toggle('zoomed', presZoom > 1);
    const hint = $('#presHint');
    if (hint) {
      hint.textContent = presZoom > 1
        ? 'drag to move  \u00b7  0 for the whole slide  \u00b7  esc to leave'
        : 'arrows to move  \u00b7  scroll to zoom  \u00b7  '
          + 'esc to leave  \u00b7  f for full screen';
    }
  }

  function presExit() {
    presDrag = null;
    presZoomReset();
    const host = $('#presenter');
    if (host) host.classList.add('hidden');
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    // Leave the editor on whatever was last shown.
    slideIndex = presIndex;
    selectedItem = null;
    render();
  }

  function presKeys(e) {
    const host = $('#presenter');
    if (!host || host.classList.contains('hidden')) return;
    if (e.key === 'Escape') { e.preventDefault(); presExit(); }
    else if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') {
      e.preventDefault(); presStep(1);
    } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
      e.preventDefault(); presStep(-1);
    } else if (e.key === 'Home') { e.preventDefault(); presIndex = 0; presPaint(); }
    else if (e.key === 'End') {
      e.preventDefault(); presIndex = deck.slides.length - 1; presPaint();
    } else if (e.key.toLowerCase() === 'f') {
      e.preventDefault();
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
      else host.requestFullscreen().catch(() => {});
    } else if (e.key === '+' || e.key === '=') {
      e.preventDefault(); presScale(1.4);
    } else if (e.key === '-' || e.key === '_') {
      e.preventDefault(); presScale(1 / 1.4);
    } else if (e.key === '0') {
      e.preventDefault(); presZoomReset();
    } else if (presZoom > 1 && e.key === 'ArrowUp') {
      // Once zoomed in, the arrows move around the slide rather than off it.
      e.preventDefault(); presPan.y += 60; presApplyZoom();
    } else if (presZoom > 1 && e.key === 'ArrowDown') {
      e.preventDefault(); presPan.y -= 60; presApplyZoom();
    }
  }

  function presPaint() {
    const sl = deck.slides[presIndex];
    if (!sl) return;
    const stageEl = $('#presSlide');
    stageEl.innerHTML = '';
    stageEl.style.background = sl.background || '#fff';
    if (sl.title) {
      stageEl.appendChild(el('div', { class: 'sb-slide-heading', text: sl.title }));
    }
    // Reuse the editor's renderers, then strip anything interactive.
    for (const it of (sl.items || []).slice().sort((a, b) => (a.z || 1) - (b.z || 1))) {
      const node = itemNode(it);
      node.classList.remove('sel');
      node.onmousedown = null;
      node.style.pointerEvents = 'none';
      for (const h of Array.from(node.querySelectorAll('.sb-handle'))) h.remove();
      const body = node.querySelector('[contenteditable]');
      if (body) body.removeAttribute('contenteditable');
      stageEl.appendChild(node);
    }
    $('#presNotes').textContent = sl.notes || '';
    $('#presNotes').style.display = sl.notes ? '' : 'none';
    $('#presCount').textContent = (presIndex + 1) + ' / ' + deck.slides.length;
    // presPaint rewrites the slide's contents, not its transform -- but the
    // label and the cursor state have to be put back either way.
    presApplyZoom();
  }

  /* ======================================================================
     Feature 3 -- Align, distribute, order and snap
     Two figures that are two pixels out of line is the difference between a
     slide that looks made and one that looks thrown together.
     ====================================================================== */
  function alignBar() {
    if (!selectedItem) return null;
    const it = selectedItem;
    const sl = current();
    const btn = (label, title, fn) => el('button', {
      class: 'btn ghost sm', text: label, title,
      onclick: () => { fn(); markDirty(); render(); },
    });
    return el('div', {}, [
      el('div', { class: 'section-label', text: 'Align on the slide' }),
      el('div', { class: 'coll-row' }, [
        btn('\u2190', 'Flush left', () => { it.x = .04; }),
        btn('\u2194', 'Center horizontally', () => { it.x = (1 - it.w) / 2; }),
        btn('\u2192', 'Flush right', () => { it.x = .96 - it.w; }),
        btn('\u2191', 'Flush top', () => { it.y = .15; }),
        btn('\u2195', 'Center vertically', () => { it.y = (1 - it.h) / 2; }),
        btn('\u2193', 'Flush bottom', () => { it.y = .95 - it.h; }),
      ]),
      el('div', { class: 'coll-row', style: 'margin-top:5px' }, [
        btn('Fill', 'Fill the slide body', () => {
          it.x = .04; it.y = .15; it.w = .92; it.h = .8;
        }),
        btn('Front', 'Bring to front', () => {
          it.z = Math.max(...sl.items.map((x) => x.z || 1)) + 1;
        }),
        btn('Back', 'Send to back', () => {
          it.z = Math.min(...sl.items.map((x) => x.z || 1)) - 1;
        }),
        btn('Duplicate', 'Copy this item (ctrl+D)', () => duplicateItem()),
      ]),
      (sl.items || []).length > 1 ? el('div', {
        class: 'coll-row', style: 'margin-top:5px',
      }, [
        btn('Match width', 'Same width as the item below it in z-order',
            () => matchTo('w')),
        btn('Match height', 'Same height as the item below it in z-order',
            () => matchTo('h')),
        btn('Row', 'Space every item on this slide evenly across',
            () => distribute('x')),
        btn('Column', 'Space every item on this slide evenly down',
            () => distribute('y')),
      ]) : null,
      el('label', { class: 'toggle sm' + (snap ? ' on' : ''),
                    style: 'margin-top:7px' }, [
        el('input', {
          type: 'checkbox', checked: snap ? 'checked' : null,
          onchange: (e) => { snap = e.target.checked; },
        }),
        el('span', { text: 'snap to edges and centers' }),
      ]),
    ]);
  }

  function matchTo(key) {
    const sl = current();
    const others = sl.items.filter((x) => x.id !== selectedItem.id);
    if (!others.length) return;
    const ref = others.sort((a, b) => (b.z || 1) - (a.z || 1))[0];
    selectedItem[key] = ref[key];
  }

  function distribute(axis) {
    const sl = current();
    const list = (sl.items || []).filter((x) => x.type !== 'ink')
      .sort((a, b) => a[axis] - b[axis]);
    if (list.length < 2) return;
    const size = axis === 'x' ? 'w' : 'h';
    const first = list[0][axis];
    const last = list[list.length - 1][axis] + list[list.length - 1][size];
    const total = list.reduce((n, x) => n + x[size], 0);
    const gap = Math.max(0, (last - first - total) / (list.length - 1));
    let at = first;
    for (const x of list) { x[axis] = at; at += x[size] + gap; }
  }

  function duplicateItem() {
    if (!selectedItem) return;
    const copy = JSON.parse(JSON.stringify(selectedItem));
    copy.id = 'i' + Math.random().toString(36).slice(2, 9);
    copy.x = Math.min(.94, copy.x + .02);
    copy.y = Math.min(.94, copy.y + .02);
    copy.z = (copy.z || 1) + 1;
    current().items.push(copy);
    selectedItem = copy;
    markDirty();
    render();
  }

  /* Snapping: pull an edge or center to the slide's own lines, or to any
     other item's, but only within a few pixels so it never fights the hand. */
  const SNAP = 0.008;

  function snapValue(v, targets) {
    for (const t of targets) {
      if (Math.abs(v - t) < SNAP) return t;
    }
    return null;
  }

  function snapMove(it, x, y) {
    guides = [];
    if (!snap) return [x, y];
    const sl = current();
    const others = (sl.items || []).filter((o) => o.id !== it.id
                                                  && o.type !== 'ink');
    const xs = [.04, .5 - it.w / 2, .96 - it.w, 0, 1 - it.w];
    const ys = [.15, .5 - it.h / 2, .95 - it.h, 0, 1 - it.h];
    for (const o of others) {
      xs.push(o.x, o.x + o.w - it.w, o.x + o.w, o.x - it.w,
              o.x + (o.w - it.w) / 2);
      ys.push(o.y, o.y + o.h - it.h, o.y + o.h, o.y - it.h,
              o.y + (o.h - it.h) / 2);
    }
    const sx = snapValue(x, xs);
    const sy = snapValue(y, ys);
    if (sx !== null) guides.push({ dir: 'v', at: sx + it.w / 2 });
    if (sy !== null) guides.push({ dir: 'h', at: sy + it.h / 2 });
    return [sx === null ? x : sx, sy === null ? y : sy];
  }

  function drawGuides() {
    const canvas = $('#sbCanvas');
    if (!canvas) return;
    for (const g of Array.from(canvas.querySelectorAll('.sb-guide'))) g.remove();
    for (const g of guides) {
      canvas.appendChild(el('div', {
        class: 'sb-guide ' + g.dir,
        style: (g.dir === 'v' ? 'left:' : 'top:') + (g.at * 100) + '%',
      }));
    }
  }

  const current = () => (deck && deck.slides[slideIndex]) || null;

  /* ==================================================================
     Rendering
     ================================================================== */
  function render() {
    renderDeckBar();
    const host = $('#sbBody');
    host.innerHTML = '';

    if (!deck) {
      host.appendChild(gallery());
      return;
    }

    host.appendChild(el('div', { class: 'sb-layout' }, [
      slideRail(), stage(), inspector(),
    ]));
    drawSlide();
  }

  function renderDeckBar() {
    const bar = $('#sbBar');
    if (!bar) return;
    bar.innerHTML = '';
    if (!deck) return;

    bar.appendChild(el('input', {
      type: 'text', class: 'sb-title', value: deck.title,
      title: 'Deck title',
      onchange: (e) => { deck.title = e.target.value || 'Untitled deck'; markDirty(); },
    }));
    bar.appendChild(el('span', {
      class: 'stat-chip warn hidden', id: 'sbDirty', text: 'unsaved',
    }));
    bar.appendChild(el('div', { style: 'flex:1' }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', id: 'sbUndo', text: '\u21b6',
      title: 'Undo  (ctrl/cmd + Z)',
      disabled: undoStack.length ? null : 'disabled',
      onclick: undo,
    }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', id: 'sbRedo', text: '\u21b7',
      title: 'Redo  (ctrl/cmd + shift + Z)',
      disabled: redoStack.length ? null : 'disabled',
      onclick: redo,
    }));
    bar.appendChild(el('button', { class: 'btn ghost sm', text: 'All decks',
      onclick: () => { deck = null; render(); } }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Present',
      title: 'Full screen with speaker notes (F5)',
      onclick: () => present(slideIndex),
    }));
    bar.appendChild(el('button', { class: 'btn ghost sm', text: 'Export PDF',
      onclick: () => exportDeck('pdf') }));
    bar.appendChild(el('button', { class: 'btn ghost sm', text: 'Export PNG',
      onclick: () => exportDeck('png') }));
    bar.appendChild(el('button', { class: 'btn sm', text: 'Save',
      onclick: () => save(false) }));
    if (dirty) $('#sbDirty').classList.remove('hidden');
  }

  function gallery() {
    const wrap = el('div', { class: 'pad' });
    wrap.appendChild(el('div', { class: 'res-toolbar' }, [
      el('button', { class: 'btn', text: '+ New deck',
        onclick: async () => {
          const t = await askPath('Name this deck', 'e.g. "IED propagation, figure 3"');
          if (!t) return;
          deck = newDeck(t);
          markDirty(); render();
        } }),
      el('div', { style: 'flex:1' }),
      el('button', { class: 'btn ghost sm', text: 'Refresh',
        onclick: async () => { await loadDecks(); render(); } }),
    ]));

    if (!decks.length) {
      wrap.appendChild(el('div', { class: 'empty-state' }, [
        el('svg', { viewBox: '0 0 24 24',
          html: '<rect x="2" y="4" width="14" height="10" rx="1"/>'
              + '<rect x="6" y="16" width="16" height="4" rx="1"/>' }),
        el('p', { text: 'No decks yet. Make one here, or select results in the '
                      + 'Results view and send them over.' }),
      ]));
      return wrap;
    }

    const g = el('div', { class: 'res-grid' });
    for (const d of decks) {
      g.appendChild(el('div', { class: 'res-card' }, [
        el('div', { class: 'res-thumb', onclick: () => openDeck(d.id) }, [
          d.thumb
            ? el('img', { src: '/api/results/file?id=' + encodeURIComponent(d.thumb), alt: '' })
            : el('span', { class: 'noimg', text: d.slides + '' }),
        ]),
        el('div', { class: 'res-meta' }, [
          el('div', { class: 'res-title', text: d.title }),
          el('div', { class: 'res-sub', text: d.slides + ' slide(s)'
            + (d.author ? '  ·  ' + d.author : '') }),
          el('div', { class: 'res-sub',
            text: (d.updated || '').replace('T', ' ').slice(0, 16) }),
        ]),
        el('div', { class: 'res-acts' }, [
          el('button', { class: 'mini', text: 'Open', onclick: () => openDeck(d.id) }),
          el('button', { class: 'mini', text: 'Delete',
            onclick: async () => {
              if (!confirm('Delete "' + d.title + '"? This cannot be undone.')) return;
              await apiPost('/api/deck/' + encodeURIComponent(d.id) + '/delete');
              await loadDecks(); render();
              toast('Deleted "' + d.title + '"', 'ok');
            } }),
        ]),
      ]));
    }
    wrap.appendChild(g);
    return wrap;
  }

  /* ---------- left: slide rail ---------- */
  function slideRail() {
    const rail = el('div', { class: 'sb-rail' });
    rail.appendChild(el('div', { class: 'sb-rail-head' }, [
      el('strong', { text: 'Slides' }),
      el('span', { class: 'count', text: deck.slides.length + '' }),
    ]));

    const list = el('div', { class: 'sb-rail-list' });
    deck.slides.forEach((sl, i) => {
      list.appendChild(el('div', {
        class: 'sb-thumb' + (i === slideIndex ? ' active' : ''),
        draggable: 'true',
        title: sl.title || 'Slide ' + (i + 1),
        onclick: () => { slideIndex = i; selectedItem = null; render(); },
        ondragstart: (e) => e.dataTransfer.setData('text/sb-slide', String(i)),
        ondragover: (e) => e.preventDefault(),
        ondrop: (e) => {
          e.preventDefault();
          const from = parseInt(e.dataTransfer.getData('text/sb-slide'), 10);
          if (isNaN(from) || from === i) return;
          moveSlide(from, i);
        },
      }, [
        el('span', { class: 'sb-num', text: (i + 1) + '' }),
        el('div', { class: 'sb-mini' }, [miniature(sl)]),
        el('span', { class: 'sb-name', text: sl.title || 'Slide ' + (i + 1) }),
        /* Dragging works, but it is not discoverable and it is fiddly with a
           trackpad, so the same move is available as a button. */
        el('div', { class: 'sb-order' }, [
          el('button', {
            class: 'badbtn', text: '\u25b2', title: 'Move up',
            disabled: i === 0 ? 'disabled' : null,
            onclick: (e) => { e.stopPropagation(); moveSlide(i, i - 1); },
          }),
          el('button', {
            class: 'badbtn', text: '\u25bc', title: 'Move down',
            disabled: i === deck.slides.length - 1 ? 'disabled' : null,
            onclick: (e) => { e.stopPropagation(); moveSlide(i, i + 1); },
          }),
        ]),
        el('button', {
          class: 'badbtn', text: '✕', title: 'Delete this slide',
          onclick: (e) => {
            e.stopPropagation();
            if (deck.slides.length === 1) { toast('A deck needs at least one slide.', 'err'); return; }
            deck.slides.splice(i, 1);
            slideIndex = Math.max(0, Math.min(slideIndex, deck.slides.length - 1));
            markDirty(); render();
          },
        }),
      ]));
    });
    rail.appendChild(list);

    rail.appendChild(el('div', { class: 'sb-rail-foot' }, [
      el('button', { class: 'btn ghost sm', text: '+ Blank slide',
        onclick: () => {
          deck.slides.splice(slideIndex + 1, 0,
                             blankSlide('Slide ' + (deck.slides.length + 1)));
          slideIndex += 1;
          markDirty(); render();
        } }),
      el('button', { class: 'btn ghost sm', text: 'Duplicate',
        onclick: () => {
          const copy = JSON.parse(JSON.stringify(current()));
          copy.id = 's' + Math.random().toString(36).slice(2, 9);
          copy.title = (copy.title || 'Slide') + ' (copy)';
          deck.slides.splice(slideIndex + 1, 0, copy);
          slideIndex += 1;
          markDirty(); render();
        } }),
      el('button', { class: 'btn ghost sm', text: 'Layout\u2026',
        title: 'Apply a slide layout, or make a new slide from one',
        onclick: openLayouts }),
      el('button', { class: 'btn ghost sm', text: '+ From results',
        onclick: () => { setView('results'); } }),
    ]));
    return rail;
  }

  function moveSlide(from, to) {
    if (to < 0 || to >= deck.slides.length || from === to) return;
    const [moved] = deck.slides.splice(from, 1);
    deck.slides.splice(to, 0, moved);
    slideIndex = to;
    markDirty('slide.move', { from, to, title: moved.title });
    render();
  }

  /* A tiny static preview for the rail, so slides are recognizable. */
  function miniature(sl) {
    const box = el('div', { class: 'sb-mini-inner' });
    for (const it of (sl.items || []).slice(0, 12)) {
      const s = 'left:' + (it.x * 100) + '%;top:' + (it.y * 100) + '%;width:'
              + (it.w * 100) + '%;height:' + (it.h * 100) + '%;';
      if (it.type === 'result' && it.result_id) {
        box.appendChild(el('img', {
          class: 'sb-mini-item', style: s, src: resultSrc(it), alt: '',
        }));
      } else {
        box.appendChild(el('div', {
          class: 'sb-mini-item sb-mini-' + it.type,
          style: s + 'background:' + (it.color || 'var(--text-3)') + ';',
        }));
      }
    }
    return box;
  }

  /* ---------- center: the slide itself ---------- */
  function stage() {
    const wrap = el('div', { class: 'sb-stage' });
    wrap.appendChild(toolbar());

    const canvas = el('div', { class: 'sb-canvas', id: 'sbCanvas' });
    canvas.addEventListener('mousedown', onCanvasDown);
    // Move and up are on the window, so a drag that runs past the edge of the
    // slide still tracks and still finishes. They are bound once in init()
    // rather than here: stage() runs on every render, and re-registering the
    // handler each time meant one mouseup ran it N times -- and each run
    // called render(), which added another. Drawing got slower with every
    // stroke until it stopped responding.
    wrap.appendChild(el('div', { class: 'sb-canvas-wrap' }, [canvas]));

    const sl = current();
    wrap.appendChild(el('div', { class: 'sb-notes' }, [
      el('div', { class: 'sb-notes-head' }, [
        el('strong', { text: 'Notes' }),
        el('label', { class: 'toggle sm' + (sl.show_notes !== false ? ' on' : '') }, [
          el('input', {
            type: 'checkbox', checked: sl.show_notes !== false ? 'checked' : null,
            onchange: (e) => { sl.show_notes = e.target.checked; markDirty(); },
          }),
          el('span', { text: 'print with slide' }),
        ]),
      ]),
      el('textarea', {
        placeholder: 'What does this slide show? What should the reader take from it?',
        value: sl.notes || '',
        oninput: (e) => { sl.notes = e.target.value; markDirty(); },
      }),
    ]));
    return wrap;
  }

  function toolbar() {
    const tools = [
      ['select', '⬚', 'Select and move'],
      ['text', 'T', 'Text box'],
      ['rect', '▭', 'Rectangle'],
      ['ellipse', '◯', 'Ellipse'],
      ['arrow', '↗', 'Arrow'],
      ['line', '╱', 'Line'],
      ['highlight', '▨', 'Highlight'],
      ['ink', '✎', 'Freehand'],
    ];
    const bar = el('div', { class: 'sb-tools' });
    for (const [id, glyph, title] of tools) {
      bar.appendChild(el('button', {
        class: 'sb-tool' + (tool === id ? ' active' : ''),
        text: glyph, title,
        onclick: () => { tool = id; render(); },
      }));
    }

    bar.appendChild(el('div', { class: 'ctl-sep' }));
    const sw = el('div', { class: 'cmap-row', style: 'gap:3px' });
    for (const c of COLORS) {
      sw.appendChild(el('button', {
        class: 'ev-swatch' + (drawColor === c ? ' on' : ''),
        style: 'background:' + c, title: c,
        onclick: () => { drawColor = c; if (selectedItem) { selectedItem.color = c; markDirty(); drawSlide(); } render(); },
      }));
    }
    bar.appendChild(sw);

    bar.appendChild(el('div', { style: 'flex:1' }));
    bar.appendChild(el('input', {
      type: 'text', class: 'sb-slide-title', value: current().title || '',
      placeholder: 'Slide title',
      onchange: (e) => { current().title = e.target.value; markDirty(); render(); },
    }));
    return bar;
  }

  let drawColor = COLORS[0];

  function drawSlide() {
    const canvas = $('#sbCanvas');
    if (!canvas) return;
    canvas.innerHTML = '';
    const sl = current();
    if (!sl) return;
    canvas.style.background = sl.background || '#fff';

    const sorted = (sl.items || []).slice()
      .sort((a, b) => (a.z || 1) - (b.z || 1));

    for (const it of sorted) canvas.appendChild(itemNode(it));

    if (sl.title) {
      canvas.appendChild(el('div', { class: 'sb-slide-heading', text: sl.title }));
    }
  }

  const isLine = (it) => it.type === 'shape'
    && (it.shape === 'line' || it.shape === 'arrow');

  function itemNode(it) {
    // Decks saved before the spelling was made consistent used "colour".
    if (it.color === undefined && it.colour !== undefined) it.color = it.colour;
    const rot = Number(it.rot) || 0;
    const style = 'left:' + (it.x * 100) + '%;top:' + (it.y * 100) + '%;'
                + 'width:' + (it.w * 100) + '%;height:' + (it.h * 100) + '%;'
                + 'z-index:' + (it.z || 1) + ';'
                + (rot ? 'transform:rotate(' + rot + 'deg);' : '');
    const sel = selectedItem && selectedItem.id === it.id;
    const node = el('div', {
      class: 'sb-item sb-' + it.type + (sel ? ' sel' : ''),
      style,
      'data-id': it.id,
      onmousedown: (e) => {
        if (tool !== 'select') return;
        e.stopPropagation();
        selectedItem = it;
        const rect = $('#sbCanvas').getBoundingClientRect();
        // Where inside the item it was grabbed, so it does not jump to the
        // pointer on the first move.
        drag = { mode: 'move', it, rect,
                 gx: (e.clientX - rect.left) / rect.width - it.x,
                 gy: (e.clientY - rect.top) / rect.height - it.y };
        render();
      },
    });

    if (it.type === 'result' && (it.result_id || it.rel || it.name)) {
      node.appendChild(el('img', {
        src: resultSrc(it), alt: '', draggable: 'false',
        // A result that cannot be found says so, rather than leaving a blank
        // rectangle that looks like an empty slide.
        onerror: (e) => {
          e.target.remove();
          node.appendChild(el('div', { class: 'sb-missing' }, [
            el('strong', { text: 'Not in Results' }),
            el('span', { text: it.name || it.rel || it.result_id || '' }),
          ]));
        },
      }));
      if (it.caption) node.appendChild(el('div', { class: 'sb-cap', text: it.caption }));
    } else if (it.type === 'image' && it.src) {
      node.appendChild(el('img', { src: it.src, alt: '', draggable: 'false' }));
    } else if (it.type === 'text') {
      node.appendChild(el('div', {
        class: 'sb-textbody',
        contenteditable: 'true',
        style: 'font-size:' + (it.size || 14) + 'px;color:' + (it.color || '#12211b')
             + ';font-weight:' + (it.bold ? '700' : '400')
             + ';font-style:' + (it.italic ? 'italic' : 'normal')
             + ';text-align:' + (it.align || 'left') + ';',
        text: it.text || '',
        oninput: (e) => { it.text = e.target.innerText; markDirty(); },
        onmousedown: (e) => e.stopPropagation(),
      }));
    } else if (it.type === 'shape' || it.type === 'highlight') {
      node.appendChild(shapeSvg(it));
    } else if (it.type === 'ink') {
      node.appendChild(inkSvg(it));
    }

    if (sel && tool === 'select') {
      if (isLine(it)) {
        /* A line is grabbed by its ends, not by the corners of a box it
           happens to fit inside -- dragging a corner of a diagonal line is
           an indirect way to do a direct thing. */
        const [ax, ay, bx, by] = ends(it);
        const grip = (which, fx, fy) => el('span', {
          class: 'sb-handle sb-end',
          style: 'left:' + (fx * 100) + '%;top:' + (fy * 100) + '%;',
          title: which === 'a' ? 'Start (shift to snap the angle)'
                               : 'End (shift to snap the angle)',
          onmousedown: (e) => {
            e.stopPropagation();
            drag = { mode: 'end', which, it,
                     rect: $('#sbCanvas').getBoundingClientRect() };
          },
        });
        node.appendChild(grip('a', ax, ay));
        node.appendChild(grip('b', bx, by));
      } else {
        for (const corner of ['nw', 'ne', 'sw', 'se']) {
          node.appendChild(el('span', {
            class: 'sb-handle sb-h-' + corner,
            onmousedown: (e) => {
              e.stopPropagation();
              const rect = $('#sbCanvas').getBoundingClientRect();
              drag = { mode: 'resize', corner, it, rect,
                       x0: it.x, y0: it.y, w0: it.w, h0: it.h,
                       mx: e.clientX, my: e.clientY };
            },
          }));
        }
        // A line has its ends instead; rotating it would fight them.
        node.appendChild(el('span', {
          class: 'sb-rot', title: 'Drag to rotate (shift snaps to 15\u00b0)',
          onmousedown: (e) => {
            e.stopPropagation();
            drag = { mode: 'rotate', it,
                     rect: $('#sbCanvas').getBoundingClientRect() };
          },
        }));
      }
    }
    return node;
  }

  /* Where a line or arrow actually starts and ends, in its own box.
     0,0 is the box's top-left and 1,1 its bottom-right.

     Lines used to be drawn from the bottom-left corner to the top-right one,
     always, because only the bounding box was stored -- and a box has no
     direction. Dragging down-right and dragging up-left produced the same
     box, so they produced the same line. The endpoints are kept now, which
     is also what makes an arrowhead land on the end you finished at.

     Decks saved before this default to the old diagonal, so they look the
     way they did when they were saved. */
  function ends(it) {
    const a = it.a || [0, 1];
    const b = it.b || [1, 0];
    return [a[0], a[1], b[0], b[1]];
  }

  function shapeSvg(it) {
    const color = it.color || BARRY.token('--accent', '#FFB81C');
    const filled = it.filled || it.type === 'highlight';
    const alpha = it.alpha !== undefined ? it.alpha
      : (it.type === 'highlight' ? 0.32 : 1);
    const lw = it.width || 2;
    let inner;
    if (it.shape === 'ellipse') {
      inner = '<ellipse cx="50" cy="50" rx="48" ry="48" />';
    } else if (it.shape === 'line' || it.shape === 'arrow') {
      // The viewBox is 100x100 with preserveAspectRatio="none", so the box
      // is stretched to the item. Insetting by 2 keeps a thick stroke inside
      // the item instead of half of it hanging outside.
      const [ax, ay, bx, by] = ends(it).map((v) => 2 + v * 96);
      inner = arrowMarkup(it.shape, ax, ay, bx, by, color, lw);
    } else {
      inner = '<rect x="2" y="2" width="96" height="96" />';
    }
    return el('svg', {
      class: 'sb-shape', viewBox: '0 0 100 100', preserveAspectRatio: 'none',
      style: 'opacity:' + alpha,
      html: '<g fill="' + (filled && it.shape !== 'arrow' ? color : 'none')
          + '" stroke="'
          + (filled && it.shape !== 'arrow' ? 'none' : color)
          + '" stroke-width="' + lw + '" vector-effect="non-scaling-stroke">'
          + inner + '</g>',
    });
  }

  /* An arrowhead has to be built in the stretched 100x100 space, where a
     circle is an ellipse -- so the head is measured along the line in that
     space and the result is close enough at any sane aspect ratio. It is
     drawn as a filled triangle rather than an SVG marker because markers do
     not inherit vector-effect and came out hairline-thin. */
  function arrowMarkup(shape, ax, ay, bx, by, color, lw) {
    if (shape !== 'arrow') {
      return '<line x1="' + ax + '" y1="' + ay
           + '" x2="' + bx + '" y2="' + by + '" />';
    }
    const dx = bx - ax, dy = by - ay;
    const len = Math.hypot(dx, dy) || 1;
    const ux = dx / len, uy = dy / len;
    // Scale the head with the stroke, and cap it so a short arrow is still
    // an arrow rather than a solid wedge.
    const head = Math.min(len * 0.42, 9 + lw * 3.2);
    const half = head * 0.42;
    // The shaft stops short of the tip so the two do not overlap and show
    // through a translucent color.
    const sx = bx - ux * head * 0.92, sy = by - uy * head * 0.92;
    const px = -uy, py = ux;             // unit normal
    const pts = [
      bx + ',' + by,
      (bx - ux * head + px * half) + ',' + (by - uy * head + py * half),
      (bx - ux * head - px * half) + ',' + (by - uy * head - py * half),
    ].join(' ');
    return '<line x1="' + ax + '" y1="' + ay + '" x2="' + sx + '" y2="' + sy + '" />'
         + '<polygon points="' + pts + '" fill="' + color
         + '" stroke="none" />';
  }

  function inkSvg(it) {
    const paths = (it.strokes || []).map((st) =>
      '<polyline points="' + st.map((p) => (p[0] * 100) + ',' + (p[1] * 100)).join(' ')
      + '" />').join('');
    return el('svg', {
      class: 'sb-shape', viewBox: '0 0 100 100', preserveAspectRatio: 'none',
      html: '<g fill="none" stroke="' + (it.color || '#c0392b')
          + '" stroke-width="' + (it.width || 2)
          + '" stroke-linecap="round" stroke-linejoin="round"'
          + ' vector-effect="non-scaling-stroke">' + paths + '</g>',
    });
  }

  /* ---------- canvas interaction ---------- */
  function relPoint(e, rect) {
    return [clamp01((e.clientX - rect.left) / rect.width),
            clamp01((e.clientY - rect.top) / rect.height)];
  }
  const clamp01 = (v) => Math.max(0, Math.min(1, v));

  function onCanvasDown(e) {
    const canvas = $('#sbCanvas');
    const rect = canvas.getBoundingClientRect();
    const [x, y] = relPoint(e, rect);

    if (tool === 'select') { selectedItem = null; render(); return; }

    if (tool === 'ink') {
      inkStroke = { id: 'i' + Math.random().toString(36).slice(2, 9),
                    type: 'ink', x: 0, y: 0, w: 1, h: 1, z: 6,
                    color: drawColor, width: 2, strokes: [[[x, y]]] };
      current().items.push(inkStroke);
      drag = { mode: 'ink', rect };
      drawSlide();
      return;
    }

    if (tool === 'text') {
      const it = { id: 'i' + Math.random().toString(36).slice(2, 9),
                   type: 'text', x, y, w: 0.34, h: 0.12, z: 5,
                   text: 'Text', size: 20, color: drawColor, align: 'left' };
      current().items.push(it);
      selectedItem = it;
      // Text is the exception to a sticky tool: having placed a box you want
      // to type in it, not place another one.
      tool = 'select';
      markDirty();
      render();
      // Put the caret in the new box so it can be typed into straight away.
      const body = $('#sbCanvas .sb-item.sel .sb-textbody');
      if (body) {
        body.focus();
        const range = document.createRange();
        range.selectNodeContents(body);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
      }
      return;
    }

    // Shapes and highlights are drawn by dragging out a box.
    const shape = tool === 'highlight' ? 'rect' : tool;
    const it = {
      id: 'i' + Math.random().toString(36).slice(2, 9),
      type: tool === 'highlight' ? 'highlight' : 'shape',
      shape, x, y, w: 0.001, h: 0.001, z: tool === 'highlight' ? 2 : 3,
      color: drawColor, width: 2,
      filled: tool === 'highlight',
      alpha: tool === 'highlight' ? 0.32 : 1,
    };
    current().items.push(it);
    selectedItem = it;
    drag = { mode: 'draw', it, rect, x0: x, y0: y };
    drawSlide();
  }

  function onCanvasMove(e) {
    if (!drag) return;
    const rect = drag.rect;
    const [x, y] = relPoint(e, rect);

    if (drag.mode === 'ink' && inkStroke) {
      const last = inkStroke.strokes[inkStroke.strokes.length - 1];
      const prev = last[last.length - 1];
      // Thin the stroke: every mouse sample would bloat the JSON for no gain.
      if (Math.hypot(x - prev[0], y - prev[1]) > 0.004) last.push([x, y]);
      drawSlide();
      return;
    }
    if (drag.mode === 'draw') {
      const it = drag.it;
      it.x = Math.min(drag.x0, x);
      it.y = Math.min(drag.y0, y);
      it.w = Math.max(0.004, Math.abs(x - drag.x0));
      it.h = Math.max(0.004, Math.abs(y - drag.y0));
      if (it.shape === 'line' || it.shape === 'arrow') {
        // Which corners of that box the drag actually went between. This is
        // the whole difference between a line and a box with a line in it.
        it.a = [drag.x0 <= x ? 0 : 1, drag.y0 <= y ? 0 : 1];
        it.b = [drag.x0 <= x ? 1 : 0, drag.y0 <= y ? 1 : 0];
      }
      drawSlide();
      return;
    }
    if (drag.mode === 'end') {
      // Dragging one end of a line. The box is re-derived from the two
      // points so the item still has a sane bounding box to select and move.
      reshapeLine(drag.it, drag.which, x, y, e.shiftKey);
      drawSlide();
      return;
    }
    if (drag.mode === 'rotate') {
      const cx = drag.it.x + drag.it.w / 2;
      const cy = drag.it.y + drag.it.h / 2;
      // The canvas is wider than it is tall, and the item's coordinates are
      // fractions of each side, so the angle has to be measured in pixels or
      // it comes out skewed.
      const deg = Math.atan2((y - cy) * rect.height,
                             (x - cx) * rect.width) * 180 / Math.PI + 90;
      drag.it.rot = e.shiftKey ? Math.round(deg / 15) * 15
                               : Math.round(deg * 10) / 10;
      drawSlide();
      return;
    }
    if (drag.mode === 'move') {
      // Keep the whole item on the slide, not just its top-left corner.
      let nx = Math.max(0, Math.min(1 - drag.it.w, x - drag.gx));
      let ny = Math.max(0, Math.min(1 - drag.it.h, y - drag.gy));
      const snapped = snapMove(drag.it, nx, ny);
      drag.it.x = snapped[0];
      drag.it.y = snapped[1];
      drawSlide();
      drawGuides();
      return;
    }
    if (drag.mode === 'resize') {
      const dx = (e.clientX - drag.mx) / rect.width;
      const dy = (e.clientY - drag.my) / rect.height;
      const it = drag.it;
      if (drag.corner.includes('e')) it.w = Math.max(0.02, drag.w0 + dx);
      if (drag.corner.includes('s')) it.h = Math.max(0.02, drag.h0 + dy);
      if (drag.corner.includes('w')) {
        it.x = clamp01(drag.x0 + dx); it.w = Math.max(0.02, drag.w0 - dx);
      }
      if (drag.corner.includes('n')) {
        it.y = clamp01(drag.y0 + dy); it.h = Math.max(0.02, drag.h0 - dy);
      }
      drawSlide();
    }
  }

  /* Move one end of a line to (x, y), then rebuild the bounding box around
     both ends. Holding shift snaps the line to 15 degree steps, the way it
     does in every other drawing tool. */
  function reshapeLine(it, which, x, y, snapAngle) {
    const [ax, ay, bx, by] = ends(it);
    // Absolute positions of the two ends right now.
    let p = [it.x + ax * it.w, it.y + ay * it.h];
    let q = [it.x + bx * it.w, it.y + by * it.h];
    const anchor = which === 'a' ? q : p;
    let moved = [clamp01(x), clamp01(y)];

    if (snapAngle) {
      const rect = $('#sbCanvas').getBoundingClientRect();
      const dx = (moved[0] - anchor[0]) * rect.width;
      const dy = (moved[1] - anchor[1]) * rect.height;
      const len = Math.hypot(dx, dy);
      const step = Math.PI / 12;                       // 15 degrees
      const ang = Math.round(Math.atan2(dy, dx) / step) * step;
      moved = [clamp01(anchor[0] + Math.cos(ang) * len / rect.width),
               clamp01(anchor[1] + Math.sin(ang) * len / rect.height)];
    }

    if (which === 'a') p = moved; else q = moved;

    const nx = Math.min(p[0], q[0]), ny = Math.min(p[1], q[1]);
    const nw = Math.max(0.004, Math.abs(q[0] - p[0]));
    const nh = Math.max(0.004, Math.abs(q[1] - p[1]));
    it.x = nx; it.y = ny; it.w = nw; it.h = nh;
    it.a = [(p[0] - nx) / nw, (p[1] - ny) / nh];
    it.b = [(q[0] - nx) / nw, (q[1] - ny) / nh];
  }

  function onCanvasUp() {
    if (!drag) return;
    guides = [];
    if (drag.mode !== 'select') markDirty();
    // The tool stays selected. It used to snap back to Select after a single
    // shape, so drawing three arrows meant picking the arrow three times.
    // Escape, or clicking Select, puts it back.
    drag = null;
    inkStroke = null;
    render();
  }

  /* ---------- right: inspector ---------- */
  function inspector() {
    const col = el('div', { class: 'sb-inspector' });
    const it = selectedItem;
    if (it) col.appendChild(alignBar());

    if (!it) {
      col.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
        text: 'Slide' }));
      col.appendChild(field('Background', colorField(
        current().background || '#ffffff',
        (v) => { current().background = v; markDirty('slide.background',
                                                     { color: v }); drawSlide(); })));
      col.appendChild(el('div', { class: 'section-label', text: 'Add from results' }));
      col.appendChild(el('button', { class: 'btn ghost sm', text: 'Browse results →',
        onclick: () => setView('results') }));
      col.appendChild(el('div', { class: 'section-label', text: 'Paste an image' }));
      col.appendChild(el('p', { class: 'hint',
        style: 'font-size:11px;color:var(--text-3);line-height:1.5',
        text: 'Copy an image anywhere and press Ctrl+V with this slide open.' }));
      col.appendChild(el('div', { class: 'section-label', text: 'Tips' }));
      col.appendChild(el('p', { class: 'hint',
        style: 'font-size:11px;color:var(--text-3);line-height:1.6',
        text: 'Pick a tool then drag on the slide. Click an item to select '
            + 'it, drag its corners to resize or the grip above it to rotate '
            + '(shift snaps to 15\u00b0). A line or arrow is grabbed by its '
            + 'ends and points whichever way you drew it. Delete removes the '
            + 'selection. Drag slides in the rail to reorder.' }));
      return col;
    }

    col.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
      text: it.type === 'result' ? 'Result' : it.type }));

    if (it.type === 'text') {
      col.appendChild(field('Size', num(it.size || 20, 1,
        (v) => { it.size = Math.max(6, v); markDirty(); drawSlide(); })));
      col.appendChild(el('div', { class: 'ctl-group', style: 'margin-bottom:10px' }, [
        el('button', { class: 'mini' + (it.bold ? ' active' : ''), text: 'B',
          onclick: () => { it.bold = !it.bold; markDirty(); render(); } }),
        el('button', { class: 'mini' + (it.italic ? ' active' : ''), text: 'I',
          onclick: () => { it.italic = !it.italic; markDirty(); render(); } }),
        el('button', { class: 'mini', text: '⯇',
          onclick: () => { it.align = 'left'; markDirty(); drawSlide(); } }),
        el('button', { class: 'mini', text: '≡',
          onclick: () => { it.align = 'center'; markDirty(); drawSlide(); } }),
        el('button', { class: 'mini', text: '⯈',
          onclick: () => { it.align = 'right'; markDirty(); drawSlide(); } }),
      ]));
    }

    if (it.type === 'result') {
      col.appendChild(field('Caption', el('input', {
        type: 'text', value: it.caption || '',
        oninput: (e) => { it.caption = e.target.value; markDirty(); },
      })));
      col.appendChild(el('p', { class: 'hint',
        style: 'font-size:10.5px;color:var(--text-3)', text: it.name || '' }));
    }

    if (it.type === 'shape' || it.type === 'highlight' || it.type === 'ink') {
      col.appendChild(field('Line width', num(it.width || 2, 0.5,
        (v) => { it.width = Math.max(0.5, v); markDirty(); drawSlide(); })));
      col.appendChild(field('Opacity', num(it.alpha !== undefined ? it.alpha : 1, 0.05,
        (v) => { it.alpha = Math.max(0.05, Math.min(1, v)); markDirty(); drawSlide(); })));
      if (it.type === 'shape') {
        col.appendChild(el('label', { class: 'toggle' + (it.filled ? ' on' : '') }, [
          el('input', { type: 'checkbox', checked: it.filled ? 'checked' : null,
            onchange: (e) => { it.filled = e.target.checked; markDirty(); render(); } }),
          el('span', { text: 'Filled' }),
        ]));
      }
    }

    col.appendChild(el('div', { class: 'section-label', text: 'Color' }));
    const sw = el('div', { class: 'cmap-row', style: 'gap:4px' });
    for (const c of COLORS) {
      sw.appendChild(el('button', {
        class: 'ev-swatch' + (it.color === c ? ' on' : ''),
        style: 'background:' + c,
        title: c,
        onclick: () => { it.color = c; markDirty('item.color', { color: c });
                         render(); },
      }));
    }
    col.appendChild(sw);
    // The swatches cover the usual cases; the picker covers the case where a
    // figure already has a color in it that has to be matched.
    col.appendChild(colorField(
      it.color || BARRY.token('--accent', '#FFB81C'),
      (v) => { it.color = v; markDirty('item.color', { color: v }); render(); }));

    if (isLine(it)) {
      col.appendChild(el('div', { class: 'ctl-group',
                                  style: 'margin-bottom:10px' }, [
        el('button', {
          class: 'mini', text: 'Swap ends',
          title: 'Point it the other way',
          onclick: () => {
            const [ax, ay, bx, by] = ends(it);
            it.a = [bx, by]; it.b = [ax, ay];
            markDirty('shape.swap', { id: it.id }); drawSlide();
          },
        }),
        el('button', {
          class: 'mini', text: 'Flip across',
          title: 'Mirror it left to right',
          onclick: () => {
            const [ax, ay, bx, by] = ends(it);
            it.a = [1 - ax, ay]; it.b = [1 - bx, by];
            markDirty('shape.flip', { id: it.id }); drawSlide();
          },
        }),
      ]));
    } else {
      col.appendChild(field('Angle\u00b0', num(Number(it.rot) || 0, 5,
        (v) => {
          it.rot = ((v % 360) + 360) % 360;
          markDirty('item.rotate', { id: it.id, deg: it.rot });
          drawSlide();
        })));
    }

    col.appendChild(el('div', { class: 'section-label', text: 'Position' }));
    col.appendChild(el('div', { style: 'display:grid;grid-template-columns:1fr 1fr;gap:6px' }, [
      field('x', num(round3(it.x), 0.01, (v) => { it.x = v; markDirty(); drawSlide(); })),
      field('y', num(round3(it.y), 0.01, (v) => { it.y = v; markDirty(); drawSlide(); })),
      field('w', num(round3(it.w), 0.01, (v) => { it.w = v; markDirty(); drawSlide(); })),
      field('h', num(round3(it.h), 0.01, (v) => { it.h = v; markDirty(); drawSlide(); })),
    ]));

    col.appendChild(el('div', { class: 'ctl-group', style: 'margin-top:10px' }, [
      el('button', { class: 'mini', text: 'Front',
        onclick: () => { it.z = 9; markDirty(); drawSlide(); } }),
      el('button', { class: 'mini', text: 'Back',
        onclick: () => { it.z = 0; markDirty(); drawSlide(); } }),
      el('button', { class: 'mini', text: 'Duplicate',
        onclick: () => {
          const copy = JSON.parse(JSON.stringify(it));
          copy.id = 'i' + Math.random().toString(36).slice(2, 9);
          copy.x = clamp01(it.x + 0.03); copy.y = clamp01(it.y + 0.03);
          current().items.push(copy);
          selectedItem = copy; markDirty(); render();
        } }),
    ]));
    col.appendChild(el('button', {
      class: 'btn ghost sm danger', text: 'Delete item',
      style: 'margin-top:8px',
      onclick: () => removeSelected(),
    }));
    return col;
  }

  function removeSelected() {
    if (!selectedItem) return;
    const sl = current();
    sl.items = sl.items.filter((x) => x.id !== selectedItem.id);
    selectedItem = null;
    markDirty(); render();
  }

  /* A swatch you click, with the hex beside it for when the exact value
     matters. Typing a hex code to choose a color is a thing a person should
     never have to do, but reading one back is occasionally useful. */
  function colorField(value, onchange) {
    const hex = el('input', {
      type: 'text', class: 'color-hex', value,
      onchange: (e) => {
        const v = e.target.value.trim();
        if (/^#[0-9a-fA-F]{6}$/.test(v)) { swatch.value = v; onchange(v); }
        else e.target.value = swatch.value;
      },
    });
    const swatch = el('input', {
      type: 'color', class: 'color-swatch', value,
      oninput: (e) => { hex.value = e.target.value; },
      onchange: (e) => onchange(e.target.value),
    });
    return el('div', { class: 'color-field' }, [swatch, hex]);
  }

  function field(label, control) {
    return el('div', { class: 'field' }, [el('label', { text: label }), control]);
  }
  function num(value, step, onchange) {
    return el('input', {
      type: 'number', step: String(step), value: String(value),
      onchange: (e) => onchange(parseFloat(e.target.value)),
    });
  }
  const round3 = (v) => Math.round(v * 1000) / 1000;

  /* ---------- export ---------- */
  async function exportDeck(fmt) {
    if (!deck) return;
    if (dirty) await save(true);
    toast('Rendering ' + fmt.toUpperCase() + '…');
    try {
      const res = await fetch('/api/deck/export', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deck, format: fmt }),
      });
      if (!res.ok) {
        let msg = 'Export failed (' + res.status + ')';
        try { msg = (await res.json()).error || msg; } catch (e) { /* binary */ }
        throw new Error(msg);
      }
      const out = res.headers.get('X-Barry-Output');
      const blob = await res.blob();
      const name = (deck.title || 'storyboard').replace(/[^\w \-.]+/g, '_') + '.' + fmt;
      const url = URL.createObjectURL(blob);
      const a = el('a', { href: url, download: name });
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      toast('Saved ' + name + (out ? ' to Results/' : ''), 'ok', 5000);
      BARRY.activity.log('deck.export', { format: fmt, title: deck.title,
                                          slides: deck.slides.length });
      if (BARRY.views.results) BARRY.views.results.reload();
    } catch (e) {
      toast(e.message, 'err', 8000);
    }
  }

  /* ---------- init ---------- */
  function init() {
    window.addEventListener('mousemove', onCanvasMove);
    window.addEventListener('mouseup', onCanvasUp);

    document.addEventListener('keydown', (e) => {
      if (BARRY.state.view !== 'storyboard' || !deck) return;
      if (isTyping(e)) return;
      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault(); removeSelected();
      } else if (e.key === 'ArrowRight' && slideIndex < deck.slides.length - 1) {
        slideIndex += 1; selectedItem = null; render();
      } else if (e.key === 'ArrowLeft' && slideIndex > 0) {
        slideIndex -= 1; selectedItem = null; render();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        // The buttons in the deck bar have always worked; this was the half
        // that was missing, which is the half anyone actually reaches for.
        // Ctrl+Y is the Windows convention for redo, so it is accepted too.
        e.preventDefault();
        if (e.shiftKey) redo(); else undo();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
        e.preventDefault(); redo();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault(); save(false);
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') {
        e.preventDefault(); duplicateItem();
      } else if (e.key === 'F5') {
        e.preventDefault(); present(slideIndex);
      } else if (e.key === 'l' && !e.ctrlKey && !e.metaKey) {
        e.preventDefault(); openLayouts();
      } else if (e.key === 'Escape') {
        // The tool is sticky now, so there has to be a way back out of it.
        if (tool !== 'select') { tool = 'select'; render(); }
        else if (selectedItem) { selectedItem = null; render(); }
      }
    });

    // Paste an image straight onto the slide.
    document.addEventListener('paste', (e) => {
      if (BARRY.state.view !== 'storyboard' || !deck) return;
      const item = Array.from(e.clipboardData.items || [])
        .find((i) => i.type.startsWith('image/'));
      if (!item) return;
      const file = item.getAsFile();
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        current().items.push({
          id: 'i' + Math.random().toString(36).slice(2, 9),
          type: 'image', src: reader.result,
          x: 0.15, y: 0.2, w: 0.5, h: 0.5, z: 1,
        });
        markDirty(); render();
        toast('Pasted image onto slide ' + (slideIndex + 1), 'ok');
      };
      reader.readAsDataURL(file);
    });

    window.addEventListener('beforeunload', (e) => {
      if (dirty) { e.preventDefault(); e.returnValue = ''; }
    });
  }

  return {
    init,
    addResults,
    newDeck: async () => {
      const t = await askPath('Name this deck', 'e.g. "IED propagation"');
      if (!t) return;
      deck = newDeck(t);
      slideIndex = 0;
      await save(true);
      render();
    },
    present: () => { if (deck) present(slideIndex); },
    onShow: async () => { await loadDecks(); render(); },
  };
})();
