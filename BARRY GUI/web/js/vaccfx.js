/* ==========================================================================
   vaccfx.js -- the circuitry: a surge that crosses the interface, and a
   layer that stays lit under the cursor.

   Two effects that look related and are built on opposite principles.

     SURGE   one shot, on the way on. A wave leaves the button and lights
             each part of the interface as it reaches it. Costly for about
             a second and then gone.

     CIRCUIT while the mode is on. Faint traces across the chrome, brighter
             where the pointer is, with a ripple where it clicks.

   Three rules hold for both, and they are the reason this is its own file
   rather than another hundred lines in core.js.

   1. OPACITY AND TRANSFORM ONLY, for anything that moves every frame.
      Xplorefinder redraws its canvases on every pan frame. An animated
      `box-shadow`, `filter`, `width` or `background-position` forces a
      repaint of everything behind it -- so a decoration that follows the
      mouse would cost a repaint of the whole window at pointer rate, which
      is exactly the budget somebody dragging a trace is already spending.
      The glow is a pre-painted sprite moved with `translate3d`; the page
      underneath is never repainted.

   2. NOTHING ANIMATES AT REST. `web/_dev/vaccquiet.html` walks every
      element and both its pseudo-elements and asserts that no CSS
      animation is running while no job is live -- because a permanent
      luminance lift in peripheral vision is how a feature gets switched
      off and never switched on again. So the circuit layer has no
      `animation` at all: it is moved by pointer events, which stop when
      the pointer does. The click ripple is an animation, and it is added
      and removed within the second.

   3. CHROME ONLY, NEVER CONTENT. Traces have to look identical at 2 am and
      9 am or two screenshots cannot be compared, and this application
      exports figures. Every layer here is `pointer-events: none`, sits
      over the page, and is removed when the mode goes off.
   ========================================================================== */
'use strict';

BARRY.vaccfx = (function () {
  let layer = null;          // the persistent circuit layer, when on
  let glow = null;           // the sprite that follows the pointer
  let inner = null;          // the artwork inside it, held still
  let redraw = null;         // re-runs the drawing, on resize
  let raf = 0;
  let rafAt = 0;
  let want = { x: -9999, y: -9999 };
  let have = { x: -9999, y: -9999 };
  let wired = false;

  function reduced() {
    return !!(window.matchMedia
              && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function optedOut() {
    return document.body.classList.contains('solo-window')
        || document.body.classList.contains('aid-window');
  }

  /* ==================================================================
     The circuit that stays
     ================================================================== */
  function circuit(on) {
    if (!on || reduced() || optedOut()) {
      if (layer) { layer.remove(); layer = null; glow = null; inner = null; }
      if (raf) { cancelAnimationFrame(raf); raf = 0; }
      return;
    }
    if (layer) return;

    /* Built when the browser has a spare moment, never on the way in.

       The board is a few hundred vector paths and drawing it is one paint.
       One paint is nothing -- unless it lands during boot, when every view
       is rendering, or during the power-up, when the compositor is already
       busy. So the DOM goes up immediately and empty, and the artwork
       arrives on the next idle callback. Nobody sees the difference: the
       traces are at 7% opacity and the power-up is covering the screen.

       `requestIdleCallback` where there is one, a timer where there is not.
       Either way the mode is on and usable before this runs. */
    const draw = () => {
      if (!layer) return;                 // turned off again while waiting
      const art = traces(window.innerWidth, window.innerHeight);
      const a = layer.querySelector('.vcx-traces');
      const b = layer.querySelector('.vcx-glow-in');
      if (a) a.innerHTML = art;
      if (b) b.innerHTML = art;
    };
    redraw = draw;
    layer = el('div', { id: 'vaccCircuit' }, [
      el('div', { class: 'vcx-traces' }),
      /* The same artwork again, inside the sprite. The same string parsed
         twice, so the lit patch reveals the very traces that are faintly
         there rather than a second, differently-routed set sliding over
         them. */
      el('div', { class: 'vcx-glow' }, [
        el('div', { class: 'vcx-glow-in' }),
      ]),
    ]);
    document.body.appendChild(layer);
    if (window.requestIdleCallback) {
      requestIdleCallback(draw, { timeout: 2000 });
    } else {
      setTimeout(draw, 350);
    }
    glow = layer.querySelector('.vcx-glow');
    inner = layer.querySelector('.vcx-glow-in');
    place();
    wire();
  }

  /* One listener for the life of the page, not one per toggle.

     Attached once and then gated on whether the layer exists, because
     add/removeEventListener pairs across a toggle are how a page ends up
     with four copies of the same handler -- and `leak.html` counts window
     listeners across pane rebuilds for exactly that reason. */
  function wire() {
    if (wired) return;
    wired = true;
    window.addEventListener('pointermove', (e) => {
      if (!glow) return;
      stats.moves += 1;
      moveTo(e.clientX, e.clientY);
    }, { passive: true });

    /* Leaving the window parks the glow rather than leaving it stuck
       wherever the pointer crossed the edge. */
    window.addEventListener('pointerleave', () => {
      if (!glow) return;
      want.x = -9999; want.y = -9999;
      schedule();
    }, { passive: true });

    window.addEventListener('pointerdown', (e) => {
      if (!layer) return;
      ripple(e.clientX, e.clientY);
    }, { passive: true, capture: true });

    /* The board is drawn to fit the window, so a resize needs a new one --
       but a drag-resize fires this continuously, and redrawing a few
       hundred paths per frame is exactly the cost this whole design is
       avoiding. Debounced hard, and still on idle. */
    let rt = 0;
    window.addEventListener('resize', () => {
      if (!layer) return;
      clearTimeout(rt);
      rt = setTimeout(() => {
        if (!layer || !redraw) return;
        if (window.requestIdleCallback) {
          requestIdleCallback(redraw, { timeout: 2000 });
        } else { redraw(); }
      }, 400);
    }, { passive: true });
  }

  /* Coalesced to one write per frame.

     A pointer reports at up to 1000 Hz on some devices and the screen
     redraws at 60. Writing the transform on every event is up to sixteen
     writes nobody sees, each one invalidating the compositor's idea of
     where the sprite is. */
  function schedule() {
    const now = (window.performance && performance.now)
      ? performance.now() : Date.now();
    if (raf) {
      /* A frame is pending. Normally it arrives in sixteen milliseconds and
         there is nothing to do -- that is the coalescing this exists for.

         But `requestAnimationFrame` is starved wherever the page is not
         painting: a background tab, a minimised window, the headless
         browser the harness runs in. This used to return unconditionally,
         so a callback that never came left `raf` set for ever and every
         later move was dropped. The glow stopped following the pointer and
         nothing said why. Measured in the harness: 29 moves, one frame.

         So a frame that has not arrived in a quarter of a second is given
         up on. One extra write per 250 ms in that case, none in the normal
         one. */
      if ((now - rafAt) < 250) return;
      try { cancelAnimationFrame(raf); } catch (e) { /* already gone */ }
      raf = 0;
      place();
      return;
    }
    rafAt = now;
    raf = requestAnimationFrame(() => {
      raf = 0;
      stats.frames += 1;
      if (want.x === have.x && want.y === have.y) return;
      place();
    });
  }

  /* Move the lit patch. Exported because the harness has to be able to
     drive it without synthesising a pointer, and because a real pointer is
     the one input a headless browser cannot produce convincingly. */
  function moveTo(x, y) {
    want.x = x;
    want.y = y;
    schedule();
  }

  function place() {
    if (!glow) return;
    stats.places += 1;
    have.x = want.x;
    have.y = want.y;
    /* `translate3d`, not `left`/`top`. The first is a compositor move and
       repaints nothing; the second is a layout change and repaints the
       layer and everything it overlaps, at pointer rate. */
    const x = Math.round(want.x), y = Math.round(want.y);
    glow.style.transform =
      'translate3d(' + x + 'px,' + y + 'px,0) translate(-50%,-50%)';
    /* And the artwork inside it counter-moves, so it stays registered to
       the page. Without this the traces would slide along with the cursor
       and read as a texture being dragged rather than as the wiring under
       the interface being lit.

       Two transform writes a frame instead of one, and both are composited
       -- which is the whole reason it is done this way rather than by
       moving a mask, which would repaint. */
    if (inner) {
      inner.style.transform =
        'translate3d(' + (HALF - x) + 'px,' + (HALF - y) + 'px,0)';
    }
  }

  /* A click sends a ring out along the traces. Transient by construction:
     it is an animation, and rule 2 says nothing may be animating once the
     interface is at rest, so it removes itself. */
  function ripple(x, y) {
    if (!layer || reduced()) return;
    const r = el('div', { class: 'vcx-ripple' });
    r.style.left = x + 'px';
    r.style.top = y + 'px';
    layer.appendChild(r);
    let gone = false;
    const drop = () => { if (gone) return; gone = true; r.remove(); };
    r.addEventListener('animationend', drop);
    // `animationend` does not fire in a background tab.
    setTimeout(drop, 1200);
  }

  /* ==================================================================
     The surge that crosses
     ==================================================================
     A wave leaves the button and lights each part of the interface as it
     reaches it. The propagation is real rather than staged: every target
     is delayed by its own distance from the origin divided by a speed, so
     the order is whatever the layout actually is and stays right when the
     window is resized or the rail is collapsed.

     Drawn in the overlay at each element's rectangle rather than by
     styling the elements themselves. Putting a class on a live button to
     flash it would animate its background -- a repaint, per element, which
     is rule 1 -- and would fight whatever that component already does with
     `::before` and `::after`. A halo around the rect reads as the part
     lighting up and touches nothing. */
  /* ==================================================================
     Drawing the board
     ==================================================================
     What separates a circuit from a grid, in four properties:

       traces RUN and STOP     a lattice has no ends; a trace starts at a
                               pad, goes somewhere and terminates.
       corners are CHAMFERED   PCB routing turns 45 degrees, twice, rather
                               than square. This is the single strongest
                               visual signature of a board.
       spacing is IRREGULAR    a few runs bundled close, then nothing for
                               two hundred pixels. A board is mostly empty.
       ends carry PADS         a trace that stops in mid-air reads as a
                               mistake; one that stops at a circle reads as
                               a connection.

     Drawn deterministically from a seeded generator, so the board is the
     same every time the mode comes on in a given window size. A pattern
     that reshuffles itself on every toggle reads as noise rather than as a
     thing that is there.
  */
  const HALF = 230;                    // half the sprite, for the counter-move
  const PITCH = 26;                    // routing pitch
  const CHAMFER = 7;                   // how far the 45-degree corner cuts

  function rng(seed) {
    let t = seed >>> 0;
    return () => {
      t += 0x6D2B79F5;
      let r = Math.imul(t ^ (t >>> 15), 1 | t);
      r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
      return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
    };
  }

  /* One trace: a few segments, axis-aligned, with the corners cut.

     The chamfer is what makes it a board. A square corner reads as a table
     border; the two 45-degree cuts read as copper. */
  function route(x, y, rand) {
    const pts = [[x, y]];
    let dir = rand() < 0.5 ? 0 : 1;          // 0 horizontal, 1 vertical
    const segs = 2 + Math.floor(rand() * 4);
    for (let i = 0; i < segs; i++) {
      const len = (1 + Math.floor(rand() * 5)) * PITCH;
      const sign = rand() < 0.5 ? -1 : 1;
      const [px, py] = pts[pts.length - 1];
      pts.push(dir ? [px, py + len * sign] : [px + len * sign, py]);
      dir = 1 - dir;
    }
    // Chamfer every interior corner.
    let d = 'M' + pts[0][0] + ' ' + pts[0][1];
    for (let i = 1; i < pts.length - 1; i++) {
      const [ax, ay] = pts[i - 1], [bx, by] = pts[i], [cx, cy] = pts[i + 1];
      const inX = Math.sign(bx - ax), inY = Math.sign(by - ay);
      const outX = Math.sign(cx - bx), outY = Math.sign(cy - by);
      /* The cut is bounded by the LENGTH of each segment, not by both of
         its components -- and on an axis-aligned segment one component is
         always zero, so taking the minimum of all four made every chamfer
         exactly 0 and every corner square. The board looked like a grid
         at the joints, which is the one thing it must not do. */
      const inLen = Math.max(Math.abs(bx - ax), Math.abs(by - ay));
      const outLen = Math.max(Math.abs(cx - bx), Math.abs(cy - by));
      const c = Math.min(CHAMFER, inLen / 2, outLen / 2);
      d += ' L' + (bx - inX * c) + ' ' + (by - inY * c);
      d += ' L' + (bx + outX * c) + ' ' + (by + outY * c);
    }
    const last = pts[pts.length - 1];
    d += ' L' + last[0] + ' ' + last[1];
    return { d, ends: [pts[0], last] };
  }

  function traces(w, h) {
    const rand = rng(((w & 0xffff) << 16) ^ (h & 0xffff) ^ 0x9e37);
    const paths = [], pads = [];
    /* Density from area rather than a fixed count, so a large monitor is
       not sparse and a laptop is not a thicket. */
    const n = Math.max(10, Math.min(34, Math.round((w * h) / 62000)));
    for (let i = 0; i < n; i++) {
      const x = Math.round((rand() * w) / PITCH) * PITCH;
      const y = Math.round((rand() * h) / PITCH) * PITCH;
      const t = route(x, y, rand);
      paths.push(t.d);
      pads.push(t.ends[0], t.ends[1]);
      /* A bus: two or three more running alongside, which is what a board
         looks like where a chip fans out. */
      /* A bus: a couple more running alongside, which is what a board
         looks like where a chip fans out. Kept to two, because every path
         here is painted twice -- once faint, once inside the lit patch --
         and the whole point of the design is that the one paint is cheap.
         `probeCost` in the harness holds the ceiling. */
      if (rand() < 0.3) {
        const k = 1 + Math.floor(rand() * 2);
        for (let j = 1; j <= k; j++) {
          const off = j * 5;
          const t2 = route(x + off, y + off, rand);
          paths.push(t2.d);
        }
      }
    }
    const body = paths
      .map((d) => '<path d="' + d + '"/>').join('')
      + pads.map((pt) => '<circle cx="' + pt[0] + '" cy="' + pt[1]
                       + '" r="2.4"/>').join('');
    /* `currentColor` is the whole reason this is inline and not a data
       URI: a data URI cannot read a CSS variable, so its colour would be
       written down once and be wrong in nine themes out of ten. */
    return '<svg class="vcx-svg" width="' + w + '" height="' + h
      + '" viewBox="0 0 ' + w + ' ' + h + '" aria-hidden="true">'
      + '<g fill="currentColor" stroke="currentColor" stroke-width="1.15" '
      + 'fill-opacity="0" stroke-linejoin="round" stroke-linecap="round">'
      + body.replace(/<circle/g, '<circle fill-opacity="1" stroke="none"')
      + '</g></svg>';
  }

  const TARGETS = [
    '#rail .nav-item',
    '#rail .rail-foot > *',
    '.view-head',
    '.pane-ctl',
    '.card',
    '.btn',
  ].join(',');

  //: Pixels a second the wave travels. Slow enough to read as a sweep,
  //: fast enough that the far corner is not still waiting when the burst
  //: has finished.
  const SPEED = 2600;
  //: Nothing past this is worth lighting: a long scrolled page can hold
  //: hundreds of cards, and a hundred halos is a hundred elements for the
  //: compositor to hold for a second.
  const MAX_NODES = 40;

  function surge(origin) {
    if (reduced() || optedOut()) return null;
    const host = el('div', { id: 'vaccSurge' });
    document.body.appendChild(host);

    const ox = (origin && origin.x) || 0;
    const oy = (origin && origin.y) || 0;
    const vw = window.innerWidth, vh = window.innerHeight;

    const nodes = [];
    document.querySelectorAll(TARGETS).forEach((n) => {
      const r = n.getBoundingClientRect();
      if (!r.width || !r.height) return;              // not on screen
      if (r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) return;
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const d = Math.hypot(cx - ox, cy - oy);
      nodes.push({ r, d });
    });
    nodes.sort((a, b) => a.d - b.d);

    for (const it of nodes.slice(0, MAX_NODES)) {
      const h = el('div', { class: 'vcx-node' });
      h.style.left = it.r.left + 'px';
      h.style.top = it.r.top + 'px';
      h.style.width = it.r.width + 'px';
      h.style.height = it.r.height + 'px';
      h.style.animationDelay = Math.round((it.d / SPEED) * 1000) + 'ms';
      host.appendChild(h);
    }

    /* The wave itself: one ring, sized to reach the far corner, so the
       halos light up as it passes rather than to a timer that happens to
       look about right. */
    const reach = Math.max(
      Math.hypot(ox, oy), Math.hypot(vw - ox, oy),
      Math.hypot(ox, vh - oy), Math.hypot(vw - ox, vh - oy));
    const wave = el('div', { class: 'vcx-wave' });
    wave.style.left = ox + 'px';
    wave.style.top = oy + 'px';
    wave.style.setProperty('--reach', (reach / 11) + '');
    wave.style.animationDuration = Math.round((reach / SPEED) * 1000) + 'ms';
    host.appendChild(wave);

    const total = 900 + (reach / SPEED) * 1000;
    setTimeout(() => host.remove(), total + 600);
    return host;
  }

  /* A seam for the harness, and for anybody wondering whether the thing
     that is meant to follow the pointer is actually hearing about it.
     Counters only -- no behaviour hangs off them. */
  const stats = { moves: 0, frames: 0, places: 0 };

  return { circuit, surge, ripple, moveTo,
           get node() { return layer; },
           get wired() { return wired; },
           get stats() { return Object.assign({}, stats); } };
})();
