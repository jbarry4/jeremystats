/* ==========================================================================
   tour.js -- Guided tours: the engine.

   A new person in front of BARRY has the same problem as a new person in
   front of any instrument: everything is visible and nothing is obvious.
   Documentation answers "what does this do" for someone who already knows
   what to look at. A tour answers "what should I look at", which is the
   earlier question.

   How it works: the screen dims except for one thing, a box beside it says
   what that thing is, and either you press Next or -- when the step is worth
   doing rather than reading -- you click the thing itself and the tour moves
   on. Steps can switch views, open a recording, or set state up first, so a
   tour can show a real spectrogram rather than describing one.

   Three deliberate choices:

   The hole is a real hole. The dim is a box-shadow on a frame around the
   target, not an overlay on top of it, so the target is drawn by the
   application at full contrast and is genuinely clickable.

   Clicks are blocked everywhere except where the step says. Four panels
   around the hole, and a fifth over it on read-only steps. A tour that lets
   you wander off mid-step is a tour that desyncs from its own script.

   Nothing is faked. Every step points at the real control and, where it
   says to click, the real click happens. There is no mock interface to fall
   out of date.

   The content lives in tourmodules.js. This file knows nothing about BARRY's
   features, only how to point at them.
   ========================================================================== */
'use strict';

BARRY.tour = (function () {
  const MODULES = [];          // filled by tourmodules.js
  const DONE_KEY = 'barry.tour.done';

  let active = null;           // { module, index }
  let nodes = null;            // the overlay elements
  let watching = null;         // ResizeObserver / interval keeping the hole put
  let onTargetClick = null;
  /* True while Next is performing a step, so a double press cannot fire the
     same click twice or race the animation. */
  let advancing = false;

  /* ==================================================================
     Registration
     ================================================================== */
  function register(mod) {
    // Later registration of the same id replaces the earlier one, so a
    // module can be edited and reloaded without duplicating.
    const at = MODULES.findIndex((m) => m.id === mod.id);
    if (at >= 0) MODULES[at] = mod; else MODULES.push(mod);
  }

  function list() { return MODULES.slice(); }

  /* Which modules have been finished, on this machine.

     localStorage rather than GUI_logs: "I have seen the tour" is a fact
     about this person at this desk, not about the project, and it has no
     business syncing to everyone else through git. */
  function doneSet() {
    try {
      return new Set(JSON.parse(localStorage.getItem(DONE_KEY) || '[]'));
    } catch (e) { return new Set(); }
  }

  function markDone(id) {
    try {
      const d = doneSet();
      d.add(id);
      localStorage.setItem(DONE_KEY, JSON.stringify(Array.from(d)));
    } catch (e) { /* private window: the tour still works, it just forgets */ }
  }

  function resetProgress() {
    try { localStorage.removeItem(DONE_KEY); } catch (e) { /* ignore */ }
  }

  /* ==================================================================
     Running one
     ================================================================== */
  async function start(id) {
    const mod = MODULES.find((m) => m.id === id);
    if (!mod) { toast('No tour called "' + id + '".', 'err'); return; }
    if (active) stop(true);

    active = { module: mod, index: 0 };
    build();
    BARRY.activity.log('tour.start', { module: mod.id, steps: mod.steps.length });
    await show(0);
  }

  function stop(quiet) {
    if (!active) return;
    const { module, index } = active;
    teardown();
    active = null;
    if (!quiet) {
      BARRY.activity.log('tour.stop',
                         { module: module.id, at: index + 1,
                           of: module.steps.length });
    }
  }

  /* Move a cursor to the target and press it, visibly.

     Without this, Next just makes the screen change -- and on a step that
     opens a whole view that reads as the tour losing its place. The pointer
     is the explanation: it travels to the thing, presses it, and the change
     becomes something you watched happen.

     Clicks immediately instead if the element is off screen or the reader
     has asked for reduced motion; an animation nobody sees is not worth
     waiting for. */
  async function pressIt(target) {
    const done = () => {
      try { target.click(); } catch (e) { /* it may have gone */ }
    };
    const box = target.getBoundingClientRect();
    const still = window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (still || !box.width || !box.height) { done(); return; }

    const cur = el('div', { class: 'tour-cursor' }, [
      el('svg', {
        viewBox: '0 0 24 24',
        html: '<path d="M5 2l14 9-6 1.5L16 20l-3 1-3-7.5-5 3z"/>',
      }),
    ]);
    // Starts at the Guide box, so it reads as the tour reaching out.
    const panel = document.getElementById('tourBox');
    const from = panel ? panel.getBoundingClientRect()
      : { left: window.innerWidth / 2, top: window.innerHeight / 2,
          width: 0, height: 0 };
    cur.style.left = (from.left + from.width / 2) + 'px';
    cur.style.top = (from.top + 24) + 'px';
    document.body.appendChild(cur);

    /* The click has to happen even if the animation does not.

       This waited on requestAnimationFrame, which does not fire in a
       background tab or under a fast-forwarded clock -- so Next appended a
       cursor and then hung for ever, which is a worse bug than the one it
       was added to fix. A plain timer cannot stall, and the finally means
       the step happens whatever goes wrong in between. */
    try {
      await new Promise((r) => setTimeout(r, 20));
      cur.style.left = (box.left + box.width / 2) + 'px';
      cur.style.top = (box.top + box.height / 2) + 'px';
      await new Promise((r) => setTimeout(r, 520));
      cur.classList.add('press');
      await new Promise((r) => setTimeout(r, 170));
    } finally {
      done();
      setTimeout(() => cur.remove(), 220);
    }
  }

  async function step(delta) {
    if (!active) return;
    const next = active.index + delta;
    if (next < 0) return;
    if (next >= active.module.steps.length) { finish(); return; }
    active.index = next;
    await show(next);
  }

  function finish() {
    if (!active) return;
    const mod = active.module;
    markDone(mod.id);
    BARRY.activity.log('tour.finish', { module: mod.id });
    teardown();
    active = null;
    // Straight into the menu, so the obvious next thing is the next module.
    openMenu(mod.id);
  }

  /* ==================================================================
     One step
     ================================================================== */
  async function show(i) {
    /* Every await below is a chance for the tour to have been left --
       escape, the close button, or another module starting. `gone()` is
       checked after each one rather than trusting that `active` is still
       there, which is how this used to throw "Cannot read properties of
       null (reading 'module')" at whoever pressed escape while a step was
       still setting itself up. */
    const mine = active;
    const gone = () => active !== mine;

    const st = active.module.steps[i];
    if (!st) { finish(); return; }

    // While a step is setting up, the box says so rather than pointing at
    // something that is not there yet.
    setBusy(true);

    try {
      if (st.view && BARRY.state.view !== st.view) {
        setView(st.view);
        await sleep(220);
        if (gone()) return;
      }
      if (st.before) { await st.before(); if (gone()) return; }
      if (st.wait) {
        const ok = await until(
          () => (typeof st.wait === 'function' ? st.wait() : !!$(st.wait)),
          st.timeout || 15000);
        if (gone()) return;
        if (!ok && st.required !== false) {
          // Say what did not appear rather than pointing at nothing.
          setBusy(false);
          paint(st, null, 'This step needs something that is not on screen: '
                + (typeof st.wait === 'string' ? st.wait : 'a prerequisite')
                + '. You can skip ahead.');
          return;
        }
      }
    } catch (e) {
      if (gone()) return;
      setBusy(false);
      // A step whose setup failed says so and lets you carry on, rather than
      // ending the tour. A machine with nothing scanned yet hits this on the
      // steps that need a recording, and that is a fine reason to skip one
      // step -- not to refuse the whole walkthrough.
      paint(st, null, 'This step could not set itself up: ' + e.message);
      return;
    }

    if (gone()) return;
    setBusy(false);
    const target = resolve(st.target);
    if (target && target.scrollIntoView) {
      target.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      await sleep(140);
      if (gone()) return;
    }
    paint(st, target);
    watch(st, target);

    BARRY.activity.log('tour.step',
                       { module: mine.module.id, step: i + 1,
                         id: st.id || null });
  }

  function resolve(target) {
    if (!target) return null;
    try {
      if (typeof target === 'function') return target();
      return $(target);
    } catch (e) { return null; }
  }

  /* ==================================================================
     The overlay
     ================================================================== */
  function build() {
    const host = el('div', { class: 'tour', id: 'tour' }, [
      // Four blockers around the hole, and a fifth over it when the step is
      // read-only. Precise, and they never darken anything twice.
      el('div', { class: 'tour-block', id: 'tourBlockT' }),
      el('div', { class: 'tour-block', id: 'tourBlockR' }),
      el('div', { class: 'tour-block', id: 'tourBlockB' }),
      el('div', { class: 'tour-block', id: 'tourBlockL' }),
      el('div', { class: 'tour-block hidden', id: 'tourBlockC' }),
      el('div', { class: 'tour-hole', id: 'tourHole' }),
      el('div', { class: 'tour-box', id: 'tourBox' }),
    ]);
    document.body.appendChild(host);
    document.addEventListener('keydown', keys, true);
    window.addEventListener('resize', reposition);
    // Scrolling anywhere can move the target, and scroll does not bubble.
    document.addEventListener('scroll', reposition, true);
    nodes = { host };
  }

  function teardown() {
    if (watching) { clearInterval(watching); watching = null; }
    detachTargetClick();
    document.removeEventListener('keydown', keys, true);
    window.removeEventListener('resize', reposition);
    document.removeEventListener('scroll', reposition, true);
    const host = $('#tour');
    if (host) host.remove();
    nodes = null;
  }

  function keys(e) {
    if (!active) return;
    if (isTyping(e)) return;
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); stop(); }
    else if (e.key === 'ArrowRight' || e.key === 'Enter') {
      e.preventDefault(); e.stopPropagation(); step(1);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault(); e.stopPropagation(); step(-1);
    }
  }

  function setBusy(on) {
    const box = $('#tourBox');
    if (box) box.classList.toggle('busy', !!on);
    const hole = $('#tourHole');
    if (on && hole) hole.classList.add('hidden');
  }

  /* Put the hole over the target and the box beside it. */
  function paint(st, target, problem) {
    const box = $('#tourBox');
    const hole = $('#tourHole');
    // A timer or a late await can land here after the overlay has gone.
    if (!box || !active || !st) return;

    const mod = active.module;
    const i = active.index;
    const last = i === mod.steps.length - 1;
    const clickToGo = st.action === 'click' && target && !problem;

    box.innerHTML = '';
    box.appendChild(el('div', { class: 'tour-head' }, [
      el('span', { class: 'tour-mod', text: mod.name }),
      el('span', { class: 'tour-of',
                   text: (i + 1) + ' of ' + mod.steps.length }),
      el('button', {
        class: 'close-x', title: 'Leave the tour  (esc)',
        html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
        onclick: () => stop(),
      }),
    ]));
    box.appendChild(el('div', { class: 'tour-bar' }, [
      el('i', { style: 'width:' + ((i + 1) / mod.steps.length * 100) + '%' }),
    ]));
    box.appendChild(el('h4', { text: st.title || '' }));
    if (st.body) box.appendChild(el('p', { class: 'tour-body', text: st.body }));
    if (st.note) box.appendChild(el('p', { class: 'tour-note', text: st.note }));
    if (problem) {
      box.appendChild(el('p', { class: 'tour-problem', text: problem }));
    }
    if (clickToGo) {
      /* No longer an instruction -- Next does it. Kept as a description of
         what is about to happen, so the screen changing is expected. */
      box.appendChild(el('p', { class: 'tour-do',
        text: (st.doText
          ? st.doText.replace(/^Click /, 'Next will click ')
                     .replace(/^Open /, 'Next will open ')
          : 'Next will click it for you.') }));
    }

    /* One way forward.

       There used to be three -- "Skip this", "Next anyway", and clicking the
       thing yourself -- and two of them left the tour pointing at a screen
       that had not changed. Now Next performs the step if it has one, and
       there is nothing to get out of step with. */
    const nextBtn = el('button', {
      class: 'btn primary sm',
      text: last ? 'Finish' : 'Next',
      onclick: async () => {
        if (advancing) return;
        if (clickToGo && target) {
          advancing = true;
          nextBtn.disabled = 'disabled';
          try {
            await pressIt(target);
          } finally {
            advancing = false;
          }
          // The click may well have advanced the tour by itself, via the
          // listener that watches for it. Only move on if it did not.
          if (active && active.index === i) step(1);
          return;
        }
        /* Guarded on the plain path too. Two quick presses used to advance
           two steps and skip one, which is easy to do with a trackpad and
           impossible to notice you have done. The button is rebuilt on the
           next render, so disabling it here costs nothing. */
        advancing = true;
        nextBtn.disabled = 'disabled';
        try {
          step(1);
        } finally {
          // Cleared on a timer rather than immediately: the render that
          // replaces this button happens inside step().
          setTimeout(() => { advancing = false; }, 250);
        }
      },
    });

    box.appendChild(el('div', { class: 'tour-foot' }, [
      el('button', {
        class: 'btn ghost sm', text: 'Back',
        disabled: i === 0 ? 'disabled' : null,
        onclick: () => step(-1),
      }),
      el('div', { style: 'flex:1' }),
      nextBtn,
    ]));

    // ---- geometry -------------------------------------------------------
    const pad = st.pad === undefined ? 6 : st.pad;
    let r = null;
    if (target) {
      const b = target.getBoundingClientRect();
      if (b.width > 0 && b.height > 0) {
        r = { left: b.left - pad, top: b.top - pad,
              width: b.width + pad * 2, height: b.height + pad * 2 };
      }
    }

    if (r) {
      hole.classList.remove('hidden');
      hole.style.left = r.left + 'px';
      hole.style.top = r.top + 'px';
      hole.style.width = r.width + 'px';
      hole.style.height = r.height + 'px';
      hole.classList.toggle('clickable', !!clickToGo);
      blockers(r, !clickToGo);
    } else {
      // No target: dim the whole screen and centre the box. Used by the
      // opening and closing steps, which are about the app rather than a
      // control.
      hole.classList.add('hidden');
      blockers(null, true);
    }

    place(box, r, st.placement);

    detachTargetClick();
    if (clickToGo) attachTargetClick(target, st);
  }

  /* The four panels, sized from the hole. */
  function blockers(r, coverHole) {
    const T = $('#tourBlockT'), R = $('#tourBlockR');
    const B = $('#tourBlockB'), L = $('#tourBlockL'), C = $('#tourBlockC');
    if (!T) return;
    const W = window.innerWidth, H = window.innerHeight;
    const box = r || { left: 0, top: 0, width: 0, height: 0 };
    const set = (n, x, y, w, h) => {
      n.style.left = Math.max(0, x) + 'px';
      n.style.top = Math.max(0, y) + 'px';
      n.style.width = Math.max(0, w) + 'px';
      n.style.height = Math.max(0, h) + 'px';
    };
    if (!r) {
      set(T, 0, 0, W, H);
      for (const n of [R, B, L]) set(n, 0, 0, 0, 0);
    } else {
      set(T, 0, 0, W, box.top);
      set(B, 0, box.top + box.height, W, H - box.top - box.height);
      set(L, 0, box.top, box.left, box.height);
      set(R, box.left + box.width, box.top,
          W - box.left - box.width, box.height);
    }
    C.classList.toggle('hidden', !coverHole);
    if (coverHole) set(C, box.left, box.top, box.width, box.height);
  }

  /* Beside the target if there is room, else wherever there is. */
  function place(box, r, prefer) {
    box.style.visibility = 'hidden';
    box.style.left = '0px';
    box.style.top = '0px';
    const bw = box.offsetWidth, bh = box.offsetHeight;
    const W = window.innerWidth, H = window.innerHeight;
    const M = 14;

    if (!r) {
      box.style.left = Math.round((W - bw) / 2) + 'px';
      box.style.top = Math.round((H - bh) / 2) + 'px';
      box.dataset.arrow = 'none';
      box.style.visibility = 'visible';
      return;
    }

    const room = {
      bottom: H - (r.top + r.height) - M,
      top: r.top - M,
      right: W - (r.left + r.width) - M,
      left: r.left - M,
    };
    const order = [prefer, 'bottom', 'top', 'right', 'left'].filter(Boolean);
    let side = order.find((s) => room[s] >= (s === 'top' || s === 'bottom'
                                            ? bh : bw));
    if (!side) {
      // Nothing fits beside it, so sit over the largest gap.
      side = Object.keys(room).sort((a, b) => room[b] - room[a])[0];
    }

    let x, y;
    if (side === 'bottom' || side === 'top') {
      x = r.left + r.width / 2 - bw / 2;
      y = side === 'bottom' ? r.top + r.height + M : r.top - bh - M;
    } else {
      x = side === 'right' ? r.left + r.width + M : r.left - bw - M;
      y = r.top + r.height / 2 - bh / 2;
    }
    box.style.left = Math.round(Math.max(M, Math.min(x, W - bw - M))) + 'px';
    box.style.top = Math.round(Math.max(M, Math.min(y, H - bh - M))) + 'px';
    box.dataset.arrow = side;
    box.style.visibility = 'visible';
  }

  /* The target can move: a pane redraws, a list loads, a panel wraps. Rather
     than hope it does not, re-measure on a slow tick while the step is up. */
  function watch(st, target) {
    if (watching) { clearInterval(watching); watching = null; }
    if (!target) return;
    let last = '';
    watching = setInterval(() => {
      // The tour can end between ticks; stop rather than keep measuring a
      // node nobody is pointing at any more.
      if (!active) { clearInterval(watching); watching = null; return; }
      const b = target.getBoundingClientRect();
      const key = [b.left, b.top, b.width, b.height].map(Math.round).join();
      if (key !== last) { last = key; reposition(); }
    }, 260);
  }

  function reposition() {
    if (!active) return;
    const st = active.module.steps[active.index];
    paint(st, resolve(st.target));
  }

  /* A click-to-continue step listens on the target itself, in the capture
     phase, so it hears the click even if the app stops it later. */
  function attachTargetClick(target, st) {
    onTargetClick = {
      target,
      fn: () => {
        // Let the application handle it first, then move on.
        setTimeout(() => {
          if (!active) return;
          detachTargetClick();
          step(1);
        }, st.afterClick === undefined ? 420 : st.afterClick);
      },
    };
    target.addEventListener('click', onTargetClick.fn, true);
  }

  function detachTargetClick() {
    if (!onTargetClick) return;
    try {
      onTargetClick.target.removeEventListener('click', onTargetClick.fn, true);
    } catch (e) { /* gone from the DOM already */ }
    onTargetClick = null;
  }

  /* ==================================================================
     The menu
     ================================================================== */
  function openMenu(justFinished) {
    const done = doneSet();
    const rows = MODULES.map((m) => {
      const isDone = done.has(m.id);
      return el('button', {
        class: 'tour-card' + (isDone ? ' done' : '')
             + (m.id === justFinished ? ' just' : ''),
        onclick: () => { closeModal(); start(m.id); },
      }, [
        el('span', { class: 'tour-card-mark', text: isDone ? '✓' : '' }),
        el('div', { class: 'tour-card-text' }, [
          el('strong', { text: m.name }),
          el('span', { text: m.blurb || '' }),
        ]),
        el('span', { class: 'tour-card-len',
                     text: m.steps.length + ' steps' }),
      ]);
    });

    const nDone = MODULES.filter((m) => done.has(m.id)).length;

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Show me around' }),
        el('span', { class: 'sub',
          text: nDone
            ? nDone + ' of ' + MODULES.length + ' done'
            : 'Pick one. Nothing is a lecture — the tour points at the '
              + 'real thing and lets you click it.' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [
        justFinished
          ? el('div', { class: 'tour-well' }, [
              el('strong', { text: 'That one is done.' }),
              el('span', { text: ' Next one along, if you want it.' }),
            ])
          : null,
        el('div', { class: 'tour-cards' }, rows),
        el('p', { class: 'hint tour-menu-note',
          text: 'Escape leaves a tour at any point, and it picks up from the '
              + 'start next time. Arrow keys step through it.' }),
      ].filter(Boolean)),
      el('div', { class: 'mf' }, [
        el('span', { class: 'hint',
          text: nDone ? 'Progress is remembered on this computer only.' : '' }),
        el('div', { class: 'spacer' }),
        nDone
          ? el('button', {
              class: 'btn ghost sm', text: 'Forget my progress',
              onclick: () => { resetProgress(); closeModal(); openMenu(); },
            })
          : null,
        el('button', { class: 'btn ghost', text: 'Close', onclick: closeModal }),
      ].filter(Boolean)),
    ]));
  }

  /* ==================================================================
     Wiring
     ================================================================== */
  function init() {
    const btn = $('#tourBtn');
    if (btn) btn.addEventListener('click', () => openMenu());
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function until(fn, ms) {
    const t0 = Date.now();
    while (Date.now() - t0 < (ms || 8000)) {
      try { if (fn()) return true; } catch (e) { /* not ready */ }
      await sleep(90);
    }
    return false;
  }

  return {
    init, register, list, start, stop, step, openMenu,
    resetProgress, doneSet,
    // For the harnesses: where the tour currently is.
    get state() {
      return active
        ? { module: active.module.id, index: active.index,
            steps: active.module.steps.length }
        : null;
    },
  };
})();
