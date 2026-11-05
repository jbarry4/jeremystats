/* ==========================================================================
   chipforge.js -- a new category arriving.

   Spotter can add a category to the IED vocabulary ("Polyspike"), and it is
   then a category of every set, on every recording. Something that large
   should not just appear in a toolbar, so it ARRIVES: the chip turns in
   the middle of the screen, is struck by four discharges -- drawn as
   interictal discharges, a sharp spike and its slow wave, in the chip's own
   colour -- steadies, and flies down into its place in the bar, where it
   rings once, softly, and says it is ready.

   In the reveal's manner (jarvis.js, jarvisfx.js): unhurried, one
   instrument, a swell, a music-box note per strike, a two-note bell to
   land. Nothing buzzes or flashes white. About four seconds; a click or
   Escape goes straight to the end. Under reduced motion none of it plays:
   the chip is in the bar with its ring and its word, and the bell rings.

   Every stage is started by a timer, never by an animation event: under the
   harness runner's virtual time `finish` and `animationend` never fire, and
   a ceremony that waited for one would never end (GUI-CONSTITUTION §12).

       BARRY.chipForge.ask({ labels, create })   -> the label, or null
         the dialog: name, colour, IED or not, then a confirm
       BARRY.chipForge.play({ label, target, onLand })
         label    { name, color, keys }
         target   () => the element it lands on, asked for at flight time
                  -- a toolbar that has re-rendered meanwhile still works
         onLand   (el) => called once, with the element it landed on
   ========================================================================== */
'use strict';

BARRY.chipForge = (function () {
  const SVG = 'http://www.w3.org/2000/svg';
  const fx = () => (typeof BARRY !== 'undefined' && BARRY.jarvisfx)
                   || window.JarvisFX || null;
  /* Through the reveal's own instrument, so its one mute silences this. */
  const sfx = (name, a) => {
    try { const f = fx(); if (f && !f.muted && f[name]) f[name](a); }
    catch (e) { /* a decoration never stops anything */ }
  };
  const reduced = () => !!(BARRY.ui && BARRY.ui.reducedMotion
                           && BARRY.ui.reducedMotion());

  /* When each thing happens, in ms from the start. One table, so the
     picture and the sound cannot drift apart. */
  const T = {
    spin: 0,            // the chip appears, turning
    strikes: [1150, 1550, 1950, 2350],
    draw: 240,          // a discharge takes this long to reach the chip
    settle: 2800,
    fly: 3250,
    flyFor: 680,
    land: 3950,
  };

  let live = null;      // the ceremony on screen, if any

  /* An interictal discharge as a path along +x, from the outer radius in
     to the chip: a little baseline, the sharp spike, its overshoot, the
     slow wave, and in. Jittered, so no two strikes are the same line. */
  function dischargePath(rIn, rOut, h) {
    const L = rOut - rIn;
    const at = (f) => rOut - f * L;
    const j = (s) => (Math.random() - 0.5) * s;
    const pts = [
      [0, 0], [0.12, j(0.10)], [0.22, j(0.12)], [0.33, -0.10 + j(0.06)],
      [0.40, j(0.04)], [0.455, -1.0 + j(0.08)], [0.51, 0.55 + j(0.06)],
      [0.57, 0.08], [0.66, 0.36 + j(0.06)], [0.76, 0.30], [0.86, 0.08],
      [0.94, j(0.06)], [1, 0],
    ];
    return pts.map((p, i) => (i ? 'L' : 'M') + at(p[0]).toFixed(1) + ' '
                              + (p[1] * h).toFixed(1)).join(' ');
  }

  function strike(svg, cx, cy, rIn, rOut, angle) {
    const g = document.createElementNS(SVG, 'g');
    g.setAttribute('transform', 'translate(' + cx + ' ' + cy + ') rotate('
                                + angle + ')');
    const d = dischargePath(rIn, rOut, Math.max(10, (rOut - rIn) * 0.16));
    for (const cls of ['cf-bolt-glow', 'cf-bolt']) {
      const p = document.createElementNS(SVG, 'path');
      p.setAttribute('d', d);
      p.setAttribute('class', cls);
      g.appendChild(p);
    }
    svg.appendChild(g);
    // Drawn from its outer end inward: dash the whole length, then run it out.
    for (const p of g.querySelectorAll('path')) {
      let len = 600;
      try { len = Math.ceil(p.getTotalLength()); } catch (e) { /* layout */ }
      p.style.strokeDasharray = len;
      p.style.strokeDashoffset = len;
      p.style.setProperty('--len', len);
    }
    requestAnimationFrame(() => g.classList.add('go'));
    setTimeout(() => g.classList.add('out'), T.draw + 60);
    setTimeout(() => g.remove(), T.draw + 900);
  }

  function play(o) {
    const opt = o || {};
    const label = opt.label || {};
    const key = (label.keys || [])[0];
    let landed = false;
    let stage = null;
    const timers = [];
    const at = (ms, fn) => timers.push(setTimeout(fn, ms));

    const land = () => {
      if (landed) return;
      landed = true;
      timers.forEach(clearTimeout);
      document.removeEventListener('keydown', onKey, true);
      if (stage) stage.remove();
      if (live === me) live = null;
      const el_ = typeof opt.target === 'function' ? opt.target() : null;
      if (el_) ready(el_, key);
      sfx('select');
      try { if (opt.onLand) opt.onLand(el_); } catch (e) { /* caller's */ }
    };
    const me = { land };
    if (live) live.land();
    live = me;

    if (reduced()) { land(); return me; }

    /* ---- the stage ---- */
    stage = el('div', { class: 'cf-stage', role: 'presentation',
                        title: 'Click to skip' });
    stage.style.setProperty('--cat', label.color || 'var(--accent)');
    const svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('class', 'cf-bolts');
    const hold = el('div', { class: 'cf-hold' }, [
      el('div', { class: 'cf-ring' }),
      el('div', { class: 'cf-chip' }, [
        el('span', { class: 'cf-name', text: label.name || 'New category' }),
        key ? el('kbd', { text: String(key) }) : null,
      ].filter(Boolean)),
    ]);
    const caption = el('div', { class: 'cf-caption',
      text: (label.name || 'A new category') + (key ? ' · key ' + key : '')
          + ' · in every IED set' });
    stage.appendChild(el('div', { class: 'cf-scrim' }));
    stage.appendChild(svg);
    stage.appendChild(hold);
    stage.appendChild(caption);
    document.body.appendChild(stage);
    stage.addEventListener('click', land);
    function onKey(e) {
      if ((e.key || '') === 'Escape' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault(); e.stopPropagation(); land();
      }
    }
    document.addEventListener('keydown', onKey, true);

    const W = window.innerWidth, H = window.innerHeight;
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    const cx = W / 2, cy = H / 2;

    /* ---- the turn ---- */
    requestAnimationFrame(() => stage.classList.add('in'));
    at(T.spin + 30, () => { hold.classList.add('spin'); sfx('charge', 1.7); });
    at(600, () => caption.classList.add('in'));

    /* ---- the strikes ---- */
    const angles = [205, 330, 150, 25].map((a) => a + (Math.random() - 0.5) * 24);
    T.strikes.forEach((t, i) => {
      at(t, () => {
        const r = hold.getBoundingClientRect();
        const rIn = Math.max(r.width, r.height) * 0.52;
        const rOut = Math.min(W, H) * 0.46;
        strike(svg, cx, cy, rIn, Math.max(rIn + 120, rOut), angles[i]);
      });
      at(t + T.draw, () => {
        hold.classList.remove('struck');
        void hold.offsetWidth;            // restart the flash
        hold.classList.add('struck');
        sfx('tick', i);
      });
    });

    /* ---- steady, then down into the bar ---- */
    at(T.settle, () => { hold.classList.remove('struck'); hold.classList.add('steady'); });
    at(T.fly, () => {
      caption.classList.remove('in');
      stage.classList.add('leaving');
      const to = typeof opt.target === 'function' ? opt.target() : null;
      if (!to || typeof hold.animate !== 'function') return;
      const a = hold.getBoundingClientRect();
      const b = to.getBoundingClientRect();
      if (!b.width) return;
      const dx = (b.left + b.width / 2) - (a.left + a.width / 2);
      const dy = (b.top + b.height / 2) - (a.top + a.height / 2);
      const s = Math.max(0.2, Math.min(1, b.height / Math.max(1, a.height)));
      try {
        hold.animate([
          { transform: 'translate(0, 0) scale(1)' },
          { transform: 'translate(' + dx + 'px, ' + dy + 'px) scale(' + s + ')' },
        ], { duration: T.flyFor, easing: 'cubic-bezier(.7, 0, .25, 1)',
             fill: 'forwards' });
      } catch (e) { /* no flight; it still lands */ }
    });
    at(T.land, land);
    return me;
  }

  /* ==================================================================
     Naming it: the dialog
     ================================================================== */

  /* A choice offered, not a style: categories are told apart by these,
     and a colour another category already wears is offered disabled, with
     whose it is. `<input type=color>` beside them takes anything else. */
  const SWATCHES = ['#7b3fa0', '#e11d48', '#0ea5e9', '#14b8a6', '#f97316',
                    '#84cc16', '#a855f7', '#eab308', '#ec4899', '#64748b'];

  function nextKey(labels) {
    const taken = new Set();
    for (const l of (labels || [])) {
      for (const k of (l.keys || [])) taken.add(String(k).toLowerCase());
    }
    return ['5', '6', '7', '8', '9', '0'].find((k) => !taken.has(k)) || null;
  }

  /* Name, colour, IED or not -- then a second step that says exactly what
     confirming will do, because it cannot be taken back from here.
     Resolves to the label `create` made, or null if called off.

       ask({ labels, create })
         labels   the vocabulary now, for the next key and the taken names
         create   ({ name, color, good }) => Promise<label>; a rejection is
                  shown in the dialog, which stays open */
  function ask(o) {
    const opt = o || {};
    const labels = opt.labels || [];
    return new Promise((resolve) => {
      let settled = false;
      const finish = (v) => { if (settled) return; settled = true;
                              closeModal(); resolve(v); };
      const usedBy = {};
      for (const l of labels) usedBy[String(l.color || '').toLowerCase()] = l.name;
      const st = { name: '', good: true, step: 1, busy: false,
                   color: SWATCHES.find((c) => !usedBy[c]) || SWATCHES[0] };
      const key = nextKey(labels);
      const box = el('div', { class: 'cf-dialog' });
      const err = el('p', { class: 'cf-err hidden' });
      const say = (m) => { err.textContent = m || '';
                           err.classList.toggle('hidden', !m); };
      const chip = (text) => el('span', { class: 'cur-cat',
                                          style: '--cat:' + st.color }, [
        el('span', { text: text }), key ? el('kbd', { text: key }) : null,
      ].filter(Boolean));
      const preview = el('div', { class: 'cf-preview' });
      const paintPreview = () => {
        preview.innerHTML = '';
        preview.appendChild(el('span', { class: 'hint quiet', text: 'In the bar:' }));
        preview.appendChild(chip(st.name.trim() || 'Its name'));
        preview.appendChild(el('span', { class: 'hint quiet',
          text: key ? 'on key ' + key : 'no key left, so a button only' }));
      };
      const taken = (name) => labels.find(
        (l) => String(l.name || '').trim().toLowerCase() === name.toLowerCase());

      const head = (title) => el('div', { class: 'mh' }, [
        el('h3', { text: title }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', 'aria-label': 'Close',
          onclick: () => { if (!st.busy) finish(null); },
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]);

      function stepOne() {
        const name = el('input', {
          type: 'text', maxlength: '32', value: st.name, 'data-fk': 'cf-name',
          placeholder: 'Polyspike', 'aria-label': 'Its name',
          oninput: (e) => { st.name = e.target.value; say(''); paintPreview(); },
          onkeydown: (e) => { if (e.key === 'Enter') { e.preventDefault(); next(); } },
        });
        const swatches = el('div', { class: 'cf-swatches' });
        const paintSwatches = () => {
          swatches.innerHTML = '';
          for (const c of SWATCHES) {
            const who = usedBy[c];
            swatches.appendChild(el('button', {
              class: 'cf-swatch' + (st.color === c ? ' on' : ''),
              style: '--sw:' + c,
              title: who ? who + ' already wears this colour' : c,
              'aria-label': who ? who + '’s colour' : 'Colour ' + c,
              disabled: who ? 'disabled' : null,
              onclick: () => { st.color = c; paintSwatches(); paintPreview(); },
            }));
          }
          swatches.appendChild(el('input', {
            type: 'color', class: 'cf-own', value: st.color,
            title: 'Any colour', 'aria-label': 'Any colour',
            oninput: (e) => {
              st.color = String(e.target.value).toLowerCase();
              paintPreview();
              for (const b of swatches.querySelectorAll('.cf-swatch')) {
                b.classList.toggle('on', false);
              }
            },
          }));
        };
        paintSwatches();
        const kindSeg = el('div', {});
        const paintSeg = () => {
          kindSeg.innerHTML = '';
          kindSeg.appendChild(BARRY.ui.seg([
            ['good', 'An IED', 'Counted as a confirmed discharge, and taken on '
                               + 'to Eye with Solid and Sputter'],
            ['not', 'Not an IED', 'Set aside, like Garbage'],
          ], st.good ? 'good' : 'not', (v) => { st.good = v === 'good'; paintSeg(); }));
        };
        paintSeg();
        paintPreview();
        setTimeout(() => name.focus(), 30);
        return el('div', {}, [
          head('A new category'),
          el('div', { class: 'mb' }, [
            el('p', { class: 'confirm-msg', text: 'A category for every IED '
                + 'set, on every recording, beside Solid, Sputter, Garbage '
                + 'and Flag.' }),
            BARRY.ui.field({ label: 'Its name', control: name }),
            BARRY.ui.field({ label: 'Its colour', control: swatches }),
            BARRY.ui.field({ label: 'What it is', control: kindSeg }),
            preview,
            err,
          ]),
          el('div', { class: 'mf' }, [
            el('div', { class: 'spacer' }),
            el('button', { class: 'btn ghost', text: 'Cancel',
                           onclick: () => finish(null) }),
            el('button', { class: 'btn', text: 'Next', onclick: next }),
          ]),
        ]);
      }

      function next() {
        const n = (st.name || '').trim().replace(/\s+/g, ' ');
        if (!n) { say('It needs a name.'); return; }
        const t = taken(n);
        if (t) { say('There is already a category called ' + t.name + '.'); return; }
        st.name = n;
        st.step = 2;
        draw();
      }

      function stepTwo() {
        const ok = el('button', { class: 'btn', text: 'Confirm' });
        const back = el('button', { class: 'btn ghost', text: 'Back',
          onclick: () => { if (!st.busy) { st.step = 1; draw(); } } });
        ok.addEventListener('click', async () => {
          if (st.busy) return;
          st.busy = true;
          ok.disabled = true; back.disabled = true;
          ok.textContent = 'Confirm…';
          let lab;
          try {
            lab = await opt.create({ name: st.name, color: st.color,
                                     good: st.good });
          } catch (e) {
            st.busy = false;
            ok.disabled = false; back.disabled = false;
            ok.textContent = 'Confirm';
            say((e && e.message) || String(e));
            return;
          }
          st.busy = false;
          finish(lab || null);
        });
        setTimeout(() => ok.focus(), 30);
        return el('div', {}, [
          head('Make it a category everywhere?'),
          el('div', { class: 'mb' }, [
            el('div', { class: 'cf-big' }, [chip(st.name)]),
            el('p', { class: 'confirm-msg', text: '“' + st.name + '” becomes '
                + 'a category of every IED set, on every recording and on '
                + 'every computer the lab’s records reach'
                + (key ? ', on key ' + key : '') + ', '
                + (st.good ? 'counted as an IED.' : 'not counted as an IED.') }),
            el('p', { class: 'hint quiet', text: 'It is added for good. It '
                + 'cannot be renamed or removed from here, because a '
                + 'candidate labelled with it has to go on meaning what it '
                + 'meant.' }),
            err,
          ]),
          el('div', { class: 'mf' }, [
            back,
            el('div', { class: 'spacer' }),
            el('button', { class: 'btn ghost', text: 'Cancel',
              onclick: () => { if (!st.busy) finish(null); } }),
            ok,
          ]),
        ]);
      }

      function draw() {
        box.innerHTML = '';
        say('');
        box.appendChild(st.step === 1 ? stepOne() : stepTwo());
      }
      draw();
      showModal(box);
    });
  }

  /* In the bar: a ring that spreads once in the chip's colour, and the
     word, which fades on its own. */
  function ready(el_, key) {
    el_.classList.remove('cf-arriving');
    el_.classList.remove('cf-landed');
    void el_.offsetWidth;
    el_.classList.add('cf-landed');
    const tag = el('span', { class: 'cf-ready',
      text: 'Ready' + (key ? ' · key ' + key : '') });
    el_.appendChild(tag);
    setTimeout(() => { tag.classList.add('out'); }, 2600);
    setTimeout(() => { tag.remove(); el_.classList.remove('cf-landed'); }, 3400);
  }

  return {
    ask,
    play,
    get active() { return !!live; },
    skip: () => { if (live) live.land(); },
    // For a harness: the timings, so it can wait the right length.
    _T: T,
  };
})();
