/* ==========================================================================
   motion.js -- BARRY.motion: the moves every surface shares.

   The user's ask (2026-10-20): "I want the UI to feel more lively... lively
   fun animations, sort of what Junction has. But for every element." The
   primitives move by themselves (app.css, Look v2: a lift on hover, a squish
   on press, a segmented thumb that slides). This is the half a surface asks
   for by name, so that a list, a card or a number moves the same way
   wherever it is:

     enter(node, {i, from})    a part arriving: rises and fades in, staggered
     exit(node, then)          leaving: fades and shrinks, then `then()`
     stagger(nodes, from)      enter() down a list
     flip(container, mutate)   a list that re-sorts or filters: rows MOVE
                               to their new places instead of jumping
     land(card, {sound})       a result arriving: the edge lights once, and
                               at most one soft bell (jarvisfx)
     pulse(node)               new since you looked: a soft pulse until seen
     shake(node)               a refusal: one small shake
     pop(node)                 a chip, a count or a toggle confirming
     countUp(node, to, o)      a number that runs up (BARRY.ui.countUp)
     drawIn(ms, frame)         a picture that draws itself in: `frame(k)`
                               for k from 0 to 1, last frame on a timer
     ambient(node, kind)       life at rest, under a budget (see below)

   Three rules, from the constitution's §12, that every one of these keeps:
     * End on a timer as well as on the animation's own end: under the
       harness runner's virtual time an animation never reports finishing,
       and a background tab may not either.
     * Under reduced motion, show the final state at once.
     * Motion marks a moment. Nothing here runs on a poll or a redraw of
       something already on screen -- callers call it when something
       arrives, not on every paint.
   ========================================================================== */
'use strict';

BARRY.motion = (function () {
  const reduced = () => {
    try {
      return !!(window.matchMedia
                && window.matchMedia('(prefers-reduced-motion: reduce)').matches)
        || document.documentElement.dataset.motion === 'calm-still';
    } catch (e) { return false; }
  };
  const calm = () => document.documentElement.dataset.motion === 'calm';
  const pace = () => {
    const v = parseFloat(getComputedStyle(document.documentElement)
      .getPropertyValue('--motion-pace'));
    return isFinite(v) && v > 0 ? v : 1;
  };
  const fx = () => BARRY.jarvisfx || window.JarvisFX || null;

  /* Run a Web Animation and promise its end -- on a timer as well. */
  function run(node, frames, opts) {
    return new Promise((resolve) => {
      if (!node || !node.animate || reduced()) { resolve(); return; }
      const o = Object.assign({ duration: 240, easing: 'ease-out', fill: 'none' },
                              opts || {});
      o.duration *= pace();
      if (o.delay) o.delay *= pace();
      let anim = null;
      let over = false;
      const done = () => {
        if (over) return;
        over = true;
        try { if (anim) anim.finish(); } catch (e) { /* gone */ }
        resolve();
      };
      try { anim = node.animate(frames, o); anim.onfinish = done; }
      catch (e) { done(); return; }
      setTimeout(done, (o.duration + (o.delay || 0)) + 80);
    });
  }

  const EASE_OUT = 'cubic-bezier(.22, .61, .36, 1)';
  const SPRING = 'cubic-bezier(.2, 1.35, .4, 1)';

  function enter(node, o) {
    const opt = o || {};
    const from = opt.from || 'below';
    const start = from === 'scale' ? 'scale(.96)'
      : from === 'left' ? 'translateX(-10px)'
      : from === 'right' ? 'translateX(10px)' : 'translateY(8px)';
    return run(node, [{ opacity: 0, transform: start },
                      { opacity: 1, transform: 'none' }],
               { duration: 420, delay: Math.min(opt.i || 0, 8) * 45,
                 easing: from === 'scale' ? SPRING : EASE_OUT });
  }

  function exit(node, then) {
    return run(node, [{ opacity: 1, transform: 'none' },
                      { opacity: 0, transform: 'scale(.97)' }],
               { duration: 160, easing: 'ease-in', fill: 'forwards' })
      .then(() => { if (typeof then === 'function') then(); });
  }

  function stagger(nodes, from) {
    return Promise.all(Array.from(nodes || []).map((n, i) =>
      enter(n, { i, from })));
  }

  /* FLIP: remember where every child was, change the list, then animate
     each child from its old place to its new one. Children are matched by
     `data-key` (or `data-id`, `data-gid`). New ones enter; gone ones are
     simply gone, because the list has already moved on. */
  function flip(container, mutate) {
    if (!container || reduced()) { if (mutate) mutate(); return; }
    const keyOf = (n) => n.dataset && (n.dataset.key || n.dataset.id || n.dataset.gid);
    const before = new Map();
    for (const n of container.children) {
      const k = keyOf(n);
      if (k) before.set(k, n.getBoundingClientRect());
    }
    if (mutate) mutate();
    let i = 0;
    for (const n of container.children) {
      const k = keyOf(n);
      const was = k ? before.get(k) : null;
      if (!was) { enter(n, { i: i++ }); continue; }
      const now = n.getBoundingClientRect();
      const dx = was.left - now.left, dy = was.top - now.top;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue;
      run(n, [{ transform: 'translate(' + dx + 'px,' + dy + 'px)' },
              { transform: 'none' }], { duration: 320, easing: EASE_OUT });
    }
  }

  function land(card, o) {
    const opt = o || {};
    if (!card) return Promise.resolve();
    card.classList.remove('mo-land');
    void card.offsetWidth;             // restart, if it was landing already
    card.classList.add('mo-land');
    setTimeout(() => card.classList.remove('mo-land'), 1900 * pace() + 100);
    if (opt.sound) {
      try { const f = fx(); if (f && !f.muted && f.land) f.land(); }
      catch (e) { /* a sound never stops anything */ }
    }
    return Promise.resolve();
  }

  function pulse(node, on) {
    if (!node) return;
    node.classList.toggle('mo-pulse', on !== false);
  }

  function shake(node) {
    return run(node, [{ transform: 'translateX(0)' }, { transform: 'translateX(-5px)' },
                      { transform: 'translateX(4px)' }, { transform: 'translateX(-3px)' },
                      { transform: 'translateX(2px)' }, { transform: 'translateX(0)' }],
               { duration: 380, easing: 'ease-out' });
  }

  function pop(node) {
    return run(node, [{ transform: 'scale(1)' }, { transform: 'scale(1.08)' },
                      { transform: 'scale(1)' }], { duration: 260, easing: SPRING });
  }

  function countUp(node, to, o) {
    if (BARRY.ui && BARRY.ui.countUp) return BARRY.ui.countUp(node, to, o);
    if (node) node.textContent = Number(to).toLocaleString();
    return undefined;
  }

  /* A picture drawing itself in: `frame(k)` is called for k from 0 to 1 on
     animation frames, and once more with 1 on a timer, so the last frame is
     drawn even where frames never come (virtual time, a hidden tab). */
  function drawIn(ms, frame) {
    if (typeof frame !== 'function') return Promise.resolve();
    if (reduced()) { frame(1); return Promise.resolve(); }
    const total = (ms || 700) * pace();
    return new Promise((resolve) => {
      const t0 = performance.now();
      let over = false;
      const finish = () => {
        if (over) return;
        over = true;
        try { frame(1); } catch (e) { /* drawn as far as it got */ }
        resolve();
      };
      const step = (now) => {
        if (over) return;
        const k = Math.min(1, (now - t0) / total);
        try { frame(1 - Math.pow(1 - k, 3)); } catch (e) { finish(); return; }
        if (k < 1) requestAnimationFrame(step); else finish();
      };
      requestAnimationFrame(step);
      setTimeout(finish, total + 120);
    });
  }

  /* Life at rest, on a budget. An ambient loop is a CSS class (`mo-amb-*`)
     that only runs while its element is on screen, the window is visible,
     motion is not reduced and the Calm switch is off -- and at most a
     handful at once, so a long list of breathing dots does not become a
     page that never stops painting. */
  const MAX_AMBIENT = 6;
  const live = new Set();
  let io = null;
  function ambient(node, kind) {
    if (!node || !('IntersectionObserver' in window)) return;
    const cls = 'mo-amb-' + (kind || 'breathe');
    if (!io) {
      io = new IntersectionObserver((rows) => {
        for (const r of rows) {
          const n = r.target;
          const want = r.isIntersecting && !reduced() && !calm()
            && document.visibilityState === 'visible'
            && (live.has(n) || live.size < MAX_AMBIENT);
          n.classList.toggle(n.dataset.moAmb, want);
          if (want) live.add(n); else live.delete(n);
        }
      });
    }
    node.dataset.moAmb = cls;
    io.observe(node);
  }
  /* The segmented control's thumb slides from the old choice to the new.

     Every segmented control in the app, hand-written or `ui.seg`, so it
     is done once, here, by watching clicks: the old choice's place is
     noted, and a moment later -- after the app's own handler, and the
     repaint that usually REPLACES the control -- a thumb is laid under the
     new choice and slid in from the old place. A rebuilt control is found
     again by its labels and nearest position. No slide when nothing is
     found in time (a repaint waiting on the server): it just changes. */
  function segOf(sig, near) {
    let best = null, bestD = Infinity;
    for (const s of document.querySelectorAll('.seg, .track-switch')) {
      if (segSig(s) !== sig) continue;
      const r = s.getBoundingClientRect();
      const d = Math.abs(r.left - near.left) + Math.abs(r.top - near.top);
      if (d < bestD) { best = s; bestD = d; }
    }
    return bestD < 400 ? best : null;
  }
  function segSig(s) {
    return Array.from(s.children).filter((c) => c.tagName === 'BUTTON')
      .map((c) => (c.textContent || '').trim()).join('|');
  }
  function slideSeg(s, from) {
    const act = s.querySelector('button.active');
    if (!act || !s.isConnected) return;
    const box = s.getBoundingClientRect(), to = act.getBoundingClientRect();
    if (!to.width || Math.abs(from.left - to.left) < 2) return;
    const th = document.createElement('span');
    th.className = 'seg-thumb';
    th.style.left = (to.left - box.left) + 'px';
    th.style.top = (to.top - box.top) + 'px';
    th.style.width = to.width + 'px';
    th.style.height = to.height + 'px';
    s.classList.add('sliding');
    s.appendChild(th);
    run(th, [{ transform: 'translateX(' + (from.left - to.left) + 'px) scaleX('
                          + (from.width / to.width).toFixed(3) + ')' },
             { transform: 'none' }],
        { duration: 280, easing: 'cubic-bezier(.2, 1.15, .4, 1)' })
      .then(() => { s.classList.remove('sliding'); th.remove(); });
  }
  document.addEventListener('click', (e) => {
    if (reduced()) return;
    const b = e.target && e.target.closest
      && e.target.closest('.seg > button, .track-switch > button');
    if (!b || b.classList.contains('active') || b.disabled) return;
    const s = b.parentElement;
    const act = s.querySelector(':scope > button.active');
    if (!act) return;
    const sig = segSig(s), from = act.getBoundingClientRect();
    const near = s.getBoundingClientRect();
    setTimeout(() => {
      const t = s.isConnected && s.querySelector(':scope > button.active') !== act
        ? s : segOf(sig, near);
      if (t) slideSeg(t, from);
    }, 30);
  }, true);

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') {
      for (const n of live) n.classList.remove(n.dataset.moAmb);
      live.clear();
    }
  });

  return { enter, exit, stagger, flip, land, pulse, shake, pop, countUp,
           drawIn, ambient, reduced, run };
})();
