/* ==========================================================================
   lite.js -- Jarvis Light: the same Jarvis, cheaper to draw.

   For a slower computer (2026-10-21). A speed setting, NOT a colour scheme:
   UVM Light is the colour theme; this changes no colour token at all, and
   web/_dev/lite.html checks that token by token in every theme. What it
   does, while it is on:

     1. Motion stops. Every `@media (prefers-reduced-motion: reduce)` rule in
        the page is switched on, so the hand-written stop each animated part
        already has (constitution section 4) is what is drawn: final states,
        no movement. Switched on by adding `all` to the rule's media list --
        "(prefers-reduced-motion: reduce), all" matches everywhere -- and
        taken off again by removing it. Nothing is copied, so a stop written
        next month is honoured too.
     2. Scripts are told the same thing. `matchMedia` answers a reduced-
        motion question with "yes" while Light is on, so BARRY.ui.reducedMotion,
        BARRY.motion, the start menu, VACC's power-up and board, Tooth Fairy,
        the tour and every other module that asks takes its still path --
        without one of them being edited.
     3. Plots draw at 1x. `devicePixelRatio` reads 1, so every canvas sizes
        its backing store for one pixel per CSS pixel. On a laptop at 150 %
        that is 2.25 times fewer pixels to fill on every pan; text on a plot
        is a little softer. Each canvas picks it up on its next draw.
     4. `data-lite="on"` on the root, for the CSS that flattens the rest
        (app.css, "Jarvis Light"): no glass blur, no elevation shadows, no
        transitions.

   It never hides a control, a label or a result -- only how they are drawn.

   Remembered for this computer, like Compact: localStorage so the first
   paint is right (index.html reads it before anything draws), and `lite`
   in the preferences, which store.py keeps per machine (PREFS_LOCAL).
   `?lite=on|off` in the address wins and is not remembered. A frame inside
   a /_dev/ page starts OFF unless its address says otherwise, so the
   hundred-odd harnesses keep measuring the app they were written against
   whatever this computer has chosen.

   `suspend()` lifts all of it for a moment somebody asked for -- the Jarvis
   reveal, which plays in full even in Light.
   ========================================================================== */
(function () {
  'use strict';
  if (typeof document === 'undefined') return;

  const B = (typeof BARRY !== 'undefined') ? BARRY : null;
  const KEY = 'barry.lite';
  const ROOT = document.documentElement;
  const REDUCE = /prefers-reduced-motion\s*:\s*reduce/i;

  const state = { on: false, held: 0, active: false };

  /* ------------------------------------------------------------------------
     Where the choice comes from
     ------------------------------------------------------------------------ */
  function urlSays() {
    try {
      const q = new URLSearchParams(location.search).get('lite');
      if (q === 'on' || q === '1') return true;
      if (q === 'off' || q === '0') return false;
    } catch (e) { /* no address to read */ }
    return null;
  }
  // A frame a harness drives: off unless the harness's address says so.
  function inHarness() {
    try {
      return window.top !== window
        && /\/_dev\//.test(window.parent.location.pathname);
    } catch (e) { return false; }
  }
  const pinned = () => urlSays() !== null || inHarness();

  function stored() {
    try { return localStorage.getItem(KEY) === 'on'; } catch (e) { return false; }
  }

  /* ------------------------------------------------------------------------
     1. The reduced-motion stops
     ------------------------------------------------------------------------ */
  let flipped = [];
  function eachMotionRule(rules, fn) {
    for (const r of Array.from(rules || [])) {
      try {
        if (r.media && REDUCE.test(r.media.mediaText || '')) fn(r);
        // Grouping rules (@supports, @layer, @media) can hold more.
        if (r.cssRules && r.cssRules.length) eachMotionRule(r.cssRules, fn);
      } catch (e) { /* one odd rule never stops the rest */ }
    }
  }
  function flipOn() {
    if (flipped.length) return;
    for (const sheet of Array.from(document.styleSheets)) {
      let rules = null;
      try { rules = sheet.cssRules; } catch (e) { continue; }  // another origin
      eachMotionRule(rules, (r) => {
        const list = Array.from(r.media);
        if (list.indexOf('all') >= 0) return;
        r.media.appendMedium('all');
        flipped.push(r);
      });
    }
  }
  function flipOff() {
    for (const r of flipped) {
      try { r.media.deleteMedium('all'); } catch (e) { /* gone */ }
    }
    flipped = [];
  }

  /* ------------------------------------------------------------------------
     2. matchMedia
     ------------------------------------------------------------------------ */
  const realMM = window.matchMedia ? window.matchMedia.bind(window) : null;
  let wrapper = null;
  function osReducedMotion() {
    try { return !!(realMM && realMM('(prefers-reduced-motion: reduce)').matches); }
    catch (e) { return false; }
  }
  function wrapOn() {
    if (wrapper || !realMM) return;
    wrapper = function matchMedia(q) {
      // A real MediaQueryList either way, so listeners and `.media` work.
      return REDUCE.test(String(q)) ? realMM(String(q) + ', all') : realMM(q);
    };
    window.matchMedia = wrapper;
  }
  function wrapOff() {
    // Only if it is still ours: a harness's stub put in after us stays.
    if (wrapper && window.matchMedia === wrapper) window.matchMedia = realMM;
    wrapper = null;
  }

  /* ------------------------------------------------------------------------
     3. devicePixelRatio
     ------------------------------------------------------------------------ */
  const ownDpr = Object.getOwnPropertyDescriptor(window, 'devicePixelRatio');
  let dprShadowed = false;
  function dprOn() {
    if (dprShadowed) return;
    try {
      Object.defineProperty(window, 'devicePixelRatio', {
        configurable: true, enumerable: true,
        get: () => 1, set: () => { /* read-only while Light is on */ },
      });
      dprShadowed = true;
    } catch (e) { /* the browser would not let it be shadowed: full sharpness */ }
  }
  function dprOff() {
    if (!dprShadowed) return;
    try {
      if (ownDpr) Object.defineProperty(window, 'devicePixelRatio', ownDpr);
      else delete window.devicePixelRatio;
    } catch (e) { /* stays at 1 until reload */ }
    dprShadowed = false;
  }
  function realDpr() {
    if (!dprShadowed) return window.devicePixelRatio || 1;
    try {
      const d = ownDpr || Object.getOwnPropertyDescriptor(
        Object.getPrototypeOf(window), 'devicePixelRatio');
      return (d && d.get ? d.get.call(window) : 1) || 1;
    } catch (e) { return 1; }
  }

  /* ------------------------------------------------------------------------
     Putting it on the page
     ------------------------------------------------------------------------ */
  /* `quiet`: the page is not told. At load, because nothing that would
     listen exists yet and each part asks for itself as it arrives; and for
     a suspend, because the reveal is the only thing on screen and VACC's
     board or Halloween's visitors popping up behind it for five seconds
     would be the opposite of the point. */
  function apply(quiet) {
    const want = state.on && state.held === 0;
    const changed = want !== state.active;
    state.active = want;
    if (want) {
      ROOT.dataset.lite = 'on';
      flipOn(); wrapOn(); dprOn();
    } else {
      // "held": chosen, and stood aside for a moment -- full drawing.
      if (state.on) ROOT.dataset.lite = 'held';
      else delete ROOT.dataset.lite;
      flipOff(); wrapOff(); dprOff();
    }
    if (changed && !quiet) after();
  }

  /* What reads the motion question once and keeps the answer: VACC's board
     (built or removed when the mode is applied), Halloween's visitors
     (started or stopped with the theme), and every canvas holding pixels
     drawn at the old ratio. Each guarded: on the way up most of them do not
     exist yet, and they ask for themselves when they arrive. */
  function after() {
    if (!B || !B.state) return;
    try { if (B.vaccfx && B.vaccfx.circuit) B.vaccfx.circuit(!!B.state.vacc); }
    catch (e) { /* decoration */ }
    try { if (B.spooky && B.spooky.sync) B.spooky.sync(B.state.theme, false); }
    catch (e) { /* decoration */ }
    try {
      if (typeof repaintThemedSurfaces === 'function' && B.state.catalog) {
        repaintThemedSurfaces();
      }
    } catch (e) { /* drawn again on its next paint */ }
    // Canvases redraw on a size change; to them this is one.
    try { window.dispatchEvent(new Event('resize')); } catch (e) { /* fine */ }
  }

  function remember(on) {
    try { localStorage.setItem(KEY, on ? 'on' : ''); } catch (e) { /* private */ }
    try { if (B && B.prefs) B.prefs.set('lite', on ? 'on' : 'off'); }
    catch (e) { /* prefs not up yet; localStorage has it */ }
  }

  function set(on, opts) {
    opts = opts || {};
    on = !!on;
    if (opts.remember !== false) remember(on);
    if (on === state.on) { apply(); return; }
    state.on = on;
    apply();
  }

  function toggle() {
    const on = !state.on;
    set(on);
    if (B && B.activity && B.activity.log) {
      try { B.activity.log('lite.mode', { on }); } catch (e) { /* not ready */ }
    }
    return on;
  }

  /* After the preferences have loaded: this machine's choice may know better
     than this browser's localStorage. Never when the address said. */
  function reconcile() {
    if (pinned() || !B || !B.prefs) return;
    const p = B.prefs.get('lite', null);
    if (p !== 'on' && p !== 'off') return;
    const want = p === 'on';
    if (want !== state.on) set(want, { remember: false });
    try { localStorage.setItem(KEY, want ? 'on' : ''); } catch (e) { /* private */ }
  }

  // Another window of this app changed it: follow, quietly.
  window.addEventListener('storage', (e) => {
    if (e.key !== KEY || pinned()) return;
    const on = e.newValue === 'on';
    if (on !== state.on) set(on, { remember: false });
  });

  /* Everything off for a moment somebody asked for. Counted, so two at once
     do not end each other early; `release` is safe to call twice. */
  function suspend() {
    state.held += 1;
    apply(true);
    let done = false;
    return function release() {
      if (done) return;
      done = true;
      state.held = Math.max(0, state.held - 1);
      apply(true);
    };
  }

  /* The switch in the theme picker. Two lines, because "Jarvis Light" beside
     a list of colour themes would read as one more of them. */
  function pickerRow() {
    const mk = (tag, cls, text) => {
      const n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text) n.textContent = text;
      return n;
    };
    const b = mk('button', 'theme-opt lite-opt' + (state.on ? ' on' : ''));
    b.type = 'button';
    b.setAttribute('role', 'switch');
    b.setAttribute('aria-checked', String(state.on));
    b.title = 'For a slower computer: motion stops, glass and shadows go, '
            + 'and plots draw at 1x. Colours stay as they are. For this '
            + 'computer only.';
    const words = mk('span', 'lite-words');
    words.append(mk('span', 'lite-name', 'Jarvis Light'),
                 mk('span', 'lite-sub', 'Less motion and effects, for slower computers'));
    b.append(mk('span', 'jv-pill'), words);
    b.addEventListener('click', () => {
      toggle();
      b.classList.toggle('on', state.on);
      b.setAttribute('aria-checked', String(state.on));
    });
    return b;
  }

  const api = {
    on: () => state.on,
    active: () => state.active,
    set, toggle, reconcile, suspend, pickerRow, osReducedMotion,
    realDpr,
  };
  if (B) B.lite = api; else window.JarvisLite = api;

  // Before anything else draws. index.html has already set the attribute
  // from localStorage for the first paint; this puts the rest in place.
  const first = urlSays();
  state.on = first !== null ? first : (inHarness() ? false : stored());
  apply(true);
})();
