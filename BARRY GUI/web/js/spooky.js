/* spooky.js -- Halloween.

   A theme like the others for colour (app.css, `data-theme="halloween"`),
   plus a layer that only exists while it is on: cobwebs in two corners,
   spiders that crawl the edges of the window and let themselves down on
   silk, bats, a ghost, and a little yard at the foot of the rail with a
   moon, a jack-o'-lantern and a cauldron.

   And seven things to find, none of them hidden very hard:

     spider    squash one that is crawling          (click it)
     dangler   send a hanging spider back up        (click it)
     ghost     say boo back                          (click the ghost)
     pumpkin   trick or treat                        (click the pumpkin)
     moon      a witch crosses it                    (click the moon)
     cauldron  stir it                               (click the cauldron)
     boo       type "boo" anywhere that isn't a text box

   Typing "trick", "treat" or "spiders" does what it says, as well.

   The rules it keeps:
   - Built when the theme is chosen, and every node, timer, listener and
     animation removed when it is not. `sync(theme)` is called from
     applyTheme on every path, so a theme switch can never leave a spider
     behind.
   - The main window only. A pop-out (a `role` or `chrome` in its URL) is a
     second screen showing data and gets the palette, not the visitors.
   - Nothing intercepts a click it was not meant for: the layer is
     pointer-events none, and only the creatures and the yard take the
     pointer. The cobweb notices the mouse by position, without covering
     the buttons under it.
   - Nothing moves for prefers-reduced-motion, and nothing new is sent while
     the window is hidden.
   - What has been found is remembered on this machine (localStorage), and
     nowhere else: an Easter egg is not a preference worth syncing. */
BARRY.spooky = (function () {
  const THEME = 'halloween';
  const EGG_KEY = 'barry.spooky.eggs';
  const SQUISH_KEY = 'barry.spooky.squished';
  const HINT_KEY = 'barry.spooky.hinted';
  const EGGS = {
    spider: 'squashed a spider',
    dangler: 'sent a spider back up its thread',
    ghost: 'said boo back to the ghost',
    pumpkin: 'went trick-or-treating',
    moon: 'saw the witch cross the moon',
    cauldron: 'stirred the cauldron',
    boo: 'typed boo',
  };
  const N_EGGS = Object.keys(EGGS).length;
  const SVGNS = 'http://www.w3.org/2000/svg';

  let on = false;
  let layer = null;
  let yard = null;
  const timers = new Set();
  const live = new Set();        // { node, anims: [] }
  let typed = '';
  let webCool = 0;

  const reduced = () => {
    try { return matchMedia('(prefers-reduced-motion: reduce)').matches; }
    catch (e) { return false; }
  };
  const popout = () => {
    try {
      const q = new URLSearchParams(location.search);
      return q.has('role') || q.has('chrome');
    } catch (e) { return false; }
  };
  const rnd = (a, b) => a + Math.random() * (b - a);
  const pick = (xs) => xs[Math.floor(Math.random() * xs.length)];
  const W = () => window.innerWidth;
  const H = () => window.innerHeight;
  const railRight = () => {
    const r = document.getElementById('rail');
    return r ? r.getBoundingClientRect().right : 0;
  };

  /* ---------------------------------------------------------------- timers */
  function later(fn, ms) {
    const t = setTimeout(() => { timers.delete(t); if (on) fn(); }, ms);
    timers.add(t);
    return t;
  }

  /* A creature that is moving: its node and its animations, so `stop` can
     end all of them. Removed when its longest animation finishes -- and on
     a timer as well, because an animation's `finished` does not always
     resolve (a background tab, a test runner's virtual clock), and a sprite
     that never leaves is a leak. */
  function track(node, anims, ms) {
    const rec = { node, anims };
    live.add(rec);
    const done = () => {
      if (!live.has(rec)) return;
      live.delete(rec);
      for (const a of rec.anims) { try { a.cancel(); } catch (e) { /* gone */ } }
      node.remove();
    };
    rec.done = done;
    later(done, (ms || 0) + 600);
    for (const a of anims) {
      if (a && a.finished) a.finished.then(() => {
        if (rec.anims.every((x) => x.playState === 'finished')) done();
      }).catch(() => { /* cancelled */ });
    }
    return rec;
  }

  /* ----------------------------------------------------------------- svg */
  function svg(w, h, view, inner, cls) {
    const s = document.createElementNS(SVGNS, 'svg');
    s.setAttribute('viewBox', view);
    s.setAttribute('width', w);
    s.setAttribute('height', h);
    if (cls) s.setAttribute('class', cls);
    s.setAttribute('aria-hidden', 'true');
    s.innerHTML = inner;
    return s;
  }

  const SPIDER = ''
    + '<g class="legs-a">'
    + '<path class="leg" d="M12 11Q6 6 4 1"/><path class="leg" d="M18.5 13Q25 11 29 9"/>'
    + '<path class="leg" d="M11.5 15Q5 17 1 20"/><path class="leg" d="M18 17Q23 23 26 29"/>'
    + '</g><g class="legs-b">'
    + '<path class="leg" d="M18 11Q24 6 26 1"/><path class="leg" d="M11.5 13Q5 11 1 9"/>'
    + '<path class="leg" d="M18.5 15Q25 17 29 20"/><path class="leg" d="M12 17Q7 23 4 29"/>'
    + '</g>'
    + '<ellipse class="body" cx="15" cy="18.5" rx="5" ry="6.5"/>'
    + '<circle class="body" cx="15" cy="10.5" r="3.2"/>'
    + '<circle class="eye" cx="13.8" cy="9.6" r=".8"/>'
    + '<circle class="eye" cx="16.2" cy="9.6" r=".8"/>';

  function spiderNode() {
    const n = el('div', { class: 'spk-spider spk-hit', title: 'A spider' });
    n.appendChild(svg(30, 30, '0 0 30 30', SPIDER));
    return n;
  }

  /* A web in a corner: spokes from the corner, and a spiral that sags
     between them. Drawn rather than stored, so it is a few hundred bytes. */
  function webSvg(size) {
    const spokes = 7, rings = [0.18, 0.34, 0.5, 0.66, 0.82, 0.97];
    const pt = (r, i) => {
      const a = (Math.PI / 2) * (i / (spokes - 1));
      return [size - r * size * Math.cos(a), r * size * Math.sin(a)];
    };
    let d = '';
    for (let i = 0; i < spokes; i++) {
      const [x, y] = pt(1, i);
      d += 'M' + size + ' 0L' + x.toFixed(1) + ' ' + y.toFixed(1);
    }
    for (const r of rings) {
      for (let i = 0; i < spokes - 1; i++) {
        const [x1, y1] = pt(r, i), [x2, y2] = pt(r, i + 1);
        // Sag towards the corner, the way silk under its own weight does.
        const [mx, my] = pt(r * 0.86, i + 0.5);
        d += 'M' + x1.toFixed(1) + ' ' + y1.toFixed(1) + 'Q' + mx.toFixed(1)
          + ' ' + my.toFixed(1) + ' ' + x2.toFixed(1) + ' ' + y2.toFixed(1);
      }
    }
    return svg(size, size, '0 0 ' + size + ' ' + size,
               '<path d="' + d + '" fill="none" stroke="currentColor" '
               + 'stroke-width=".8" stroke-linecap="round"/>');
  }

  /* ---------------------------------------------------------- the bubble */
  function say(text, x, y, big, ms) {
    if (!layer) return null;
    const b = el('div', { class: 'spk-say' + (big ? ' big' : ''), text });
    layer.appendChild(b);
    const r = b.getBoundingClientRect();
    b.style.left = Math.max(8, Math.min(W() - r.width - 8, x - r.width / 2)) + 'px';
    b.style.top = Math.max(8, Math.min(H() - r.height - 8, y - r.height - 14)) + 'px';
    later(() => { b.classList.add('gone'); later(() => b.remove(), 350); },
          ms || 2600);
    return b;
  }

  /* ------------------------------------------------------------ the eggs */
  function eggs() {
    try { return new Set(JSON.parse(localStorage.getItem(EGG_KEY) || '[]')); }
    catch (e) { return new Set(); }
  }

  function found(id, x, y) {
    const got = eggs();
    if (got.has(id)) return false;
    got.add(id);
    try { localStorage.setItem(EGG_KEY, JSON.stringify(Array.from(got))); }
    catch (e) { /* private window: found for now, forgotten later */ }
    const n = got.size;
    later(() => {
      if (n >= N_EGGS) {
        say('You found all ' + N_EGGS + '! Happy Halloween 🎃',
            W() / 2, H() / 2, true, 5200);
        treat(40);
      } else {
        say('You ' + EGGS[id] + ' — ' + n + ' of ' + N_EGGS
            + ' spooky things found', x, y - 26, false, 3600);
      }
    }, 700);
    paintYardTitles();
    return true;
  }

  /* ------------------------------------------------------- the crawlers */
  /* A walk from one point to another with a stop or two on the way, and a
     twitch at each stop -- the hesitation is most of what makes it read as
     a spider rather than a sprite on a rail. */
  function crawlFrames(x0, y0, x1, y1, speed, scale) {
    const dx = x1 - x0, dy = y1 - y0;
    const dist = Math.hypot(dx, dy);
    const ang = Math.atan2(dy, dx) * 180 / Math.PI + 90;
    const tf = (x, y, a) => 'translate(' + x.toFixed(1) + 'px,' + y.toFixed(1)
                           + 'px) rotate(' + a.toFixed(1) + 'deg) scale(' + (scale || 1) + ')';
    const stops = [rnd(0.25, 0.45), rnd(0.6, 0.8)].filter(() => Math.random() < 0.8);
    const moveMs = dist / speed * 1000;
    const pauses = stops.map(() => rnd(500, 1400));
    const total = moveMs + pauses.reduce((a, b) => a + b, 0);
    const frames = [{ transform: tf(x0, y0, ang), offset: 0 }];
    let t = 0, from = 0;
    stops.forEach((f, i) => {
      t += (f - from) * moveMs;
      const x = x0 + dx * f, y = y0 + dy * f;
      frames.push({ transform: tf(x, y, ang), offset: t / total });
      const p = pauses[i];
      frames.push({ transform: tf(x, y, ang + rnd(-18, 18)),
                    offset: (t + p * 0.4) / total });
      t += p;
      frames.push({ transform: tf(x, y, ang), offset: t / total });
      from = f;
    });
    frames.push({ transform: tf(x1, y1, ang), offset: 1 });
    return { frames, total };
  }

  function crawl(route, opts) {
    if (!layer) return null;
    const o = opts || {};
    const w = W(), h = H(), rr = railRight();
    const routes = {
      top: () => (Math.random() < 0.5 ? [-30, 9, w + 30, 9] : [w + 30, 9, -30, 9]),
      right: () => [w - 9, -30, w - 9, h + 30],
      rail: () => [rr, h + 30, rr, -30],
      bottom: () => [w + 30, h - 9, rr - 30, h - 9],
    };
    const r = route || pick(Object.keys(routes));
    const [x0, y0, x1, y1] = (routes[r] || routes.top)();
    const node = spiderNode();
    layer.appendChild(node);
    const { frames, total } = crawlFrames(x0, y0, x1, y1, o.speed || rnd(55, 85),
                                          o.scale || 1);
    let anim = null;
    try {
      anim = node.animate(frames, { duration: total, easing: 'linear',
                                    fill: 'forwards' });
    } catch (e) {
      node.remove();
      return null;
    }
    const rec = track(node, [anim], total);
    // A hand coming near: it freezes, then bolts.
    let spooked = false;
    node.addEventListener('pointerenter', () => {
      if (spooked || !live.has(rec)) return;
      spooked = true;
      anim.pause();
      node.classList.add('still');
      later(() => {
        if (!live.has(rec)) return;
        node.classList.remove('still');
        anim.playbackRate = 3.5;
        anim.play();
      }, 380);
    });
    node.addEventListener('click', (e) => {
      e.stopPropagation();
      squish(rec, anim);
    });
    return rec;
  }

  function squish(rec, anim) {
    const node = rec.node;
    const box = node.getBoundingClientRect();
    const x = box.left + box.width / 2, y = box.top + box.height / 2;
    try { anim.pause(); anim.commitStyles(); anim.cancel(); } catch (e) { /* fine */ }
    node.style.transform = (node.style.transform || '') + ' scale(1.35,.18)';
    node.classList.add('squished', 'still');
    node.style.pointerEvents = 'none';
    const splat = el('div', { class: 'spk-splat' });
    splat.appendChild(svg(26, 26, '0 0 26 26',
      '<path fill="currentColor" d="M13 4c2 3 6 1 6 5s4 4 1 7-1 6-5 5-5 3-7 0'
      + '-6-1-4-5-3-4 0-7 3-4 6-1z"/>'));
    splat.style.left = x + 'px';
    splat.style.top = y + 'px';
    layer.appendChild(splat);
    later(() => splat.classList.add('gone'), 30);
    later(() => splat.remove(), 2000);
    later(() => rec.done && rec.done(), 1100);

    let n = 0;
    try {
      n = (parseInt(localStorage.getItem(SQUISH_KEY) || '0', 10) || 0) + 1;
      localStorage.setItem(SQUISH_KEY, String(n));
    } catch (e) { n = 1; }
    if (!found('spider', x, y)) {
      const quips = {
        5: 'Five. The spiders are talking about you.',
        13: 'Thirteen. Unlucky — for them.',
        31: 'Thirty-one. One for every day of October.',
        50: 'Fifty. They have unionised.',
      };
      say(quips[n] || pick(['Squish.', 'Splat!', 'Eek!', 'One fewer.',
                            'It had a family.', 'Crunch.']), x, y, false, 1600);
      if (n === 13) later(() => swarm(13, 'bottom'), 600);
    }
  }

  function swarm(k, route) {
    for (let i = 0; i < k; i++) {
      later(() => crawl(route || 'bottom', { scale: rnd(0.45, 0.7),
                                             speed: rnd(160, 260) }), i * 120);
    }
  }

  /* -------------------------------------------- a spider on its silk */
  function dangle(xAt) {
    if (!layer) return null;
    const rr = railRight();
    const x = xAt != null ? xAt : rnd(rr + 60, Math.max(rr + 61, W() - 90));
    const depth = Math.round(rnd(90, 230));
    const box = el('div', { class: 'spk-dangle' });
    box.style.left = x + 'px';
    const silk = el('div', { class: 'silk' });
    silk.style.height = depth + 'px';
    const sp = spiderNode();
    box.appendChild(silk);
    box.appendChild(sp);
    layer.appendChild(box);
    const at = (v) => ({ ty: 'translateY(' + v + 'px) rotate(180deg)',
                         sy: 'scaleY(' + (v / depth).toFixed(3) + ')' });
    const kf = [[0, 0], [0.3, depth], [0.42, depth - 10], [0.55, depth],
                [0.68, depth - 6], [0.8, depth], [1, 0]];
    const dur = rnd(6500, 9000);
    let a1, a2;
    try {
      a1 = sp.animate(kf.map(([o, v]) => ({ offset: o, transform: at(v).ty })),
                      { duration: dur, easing: 'ease-in-out', fill: 'forwards' });
      a2 = silk.animate(kf.map(([o, v]) => ({ offset: o, transform: at(v).sy })),
                        { duration: dur, easing: 'ease-in-out', fill: 'forwards' });
    } catch (e) {
      box.remove();
      return null;
    }
    const rec = track(box, [a1, a2], dur);
    sp.addEventListener('click', (e) => {
      e.stopPropagation();
      const r = sp.getBoundingClientRect();
      const t = Math.max(0, Math.min(1, (a1.currentTime || 0) / dur));
      // Zip back up from wherever it is, fast.
      for (const a of [a1, a2]) {
        a.pause();
        a.currentTime = dur * Math.max(t, 0.8);
        a.playbackRate = 6;
        a.play();
      }
      sp.style.pointerEvents = 'none';
      say(pick(['Nope!', 'Fine, I’m going.', 'Rude.', 'Wheee—']),
          r.left + r.width / 2, r.top, false, 1400);
      found('dangler', r.left + r.width / 2, r.top);
      later(() => rec.done && rec.done(), 1400);
    });
    return rec;
  }

  /* --------------------------------------------------------------- bats */
  const BAT = '<path class="wing" d="M17 9C13 3 7 2 1 5c4 0 5 3 4 6 3-2 6-1 7 1 1-2 3-3 5-3z"/>'
    + '<path class="wing" d="M17 9c4-6 10-7 16-4-4 0-5 3-4 6-3-2-6-1-7 1-1-2-3-3-5-3z"/>'
    + '<ellipse class="bat-body" cx="17" cy="10" rx="2.6" ry="3.6"/>'
    + '<circle class="bat-eye" cx="16.2" cy="9" r=".55"/>'
    + '<circle class="bat-eye" cx="17.8" cy="9" r=".55"/>';

  function bats(k) {
    if (!layer) return;
    const n = k || Math.round(rnd(2, 4));
    const ltr = Math.random() < 0.5;
    const rr = railRight();
    for (let i = 0; i < n; i++) {
      const node = el('div', { class: 'spk-bat' });
      node.appendChild(svg(44, 24, '0 0 34 18', BAT));
      layer.appendChild(node);
      const y0 = rnd(30, H() * 0.32);
      const x0 = ltr ? rr - 40 : W() + 40, x1 = ltr ? W() + 40 : rr - 40;
      const steps = 8, amp = rnd(10, 26), dur = rnd(5200, 7600);
      const frames = [];
      for (let s = 0; s <= steps; s++) {
        const f = s / steps;
        const x = x0 + (x1 - x0) * f;
        const y = y0 + Math.sin(f * Math.PI * 3 + i) * amp - f * rnd(0, 30);
        frames.push({ offset: f, transform: 'translate(' + x.toFixed(1) + 'px,'
                      + y.toFixed(1) + 'px) scale(' + (0.7 + i * 0.12).toFixed(2) + ')' });
      }
      let a;
      try {
        a = node.animate(frames, { duration: dur, delay: i * rnd(180, 420),
                                   easing: 'linear', fill: 'both' });
      } catch (e) { node.remove(); continue; }
      track(node, [a], dur + i * 420);
    }
  }

  /* -------------------------------------------------------------- ghost */
  const GHOST = '<path class="sheet" d="M23 3C12 3 6 12 6 23v28l6-5 5 6 6-6 6 6 5-6 6 5V23C40 12 34 3 23 3z"/>'
    + '<ellipse class="face" cx="17" cy="22" rx="3" ry="4"/>'
    + '<ellipse class="face" cx="29" cy="22" rx="3" ry="4"/>'
    + '<ellipse class="face" cx="23" cy="33" rx="3.5" ry="4.5"/>';

  function ghost(from) {
    if (!layer) return null;
    const rr = railRight();
    const node = el('div', { class: 'spk-ghost spk-hit', title: 'A ghost' });
    node.appendChild(svg(46, 56, '0 0 46 56', GHOST));
    layer.appendChild(node);
    const quick = from === 'boo';
    const x0 = quick ? W() / 2 : rnd(rr + 40, rr + 200);
    const y0 = H() + 50;
    const x1 = quick ? W() / 2 + rnd(-60, 60) : rnd(W() * 0.55, W() - 80);
    const y1 = quick ? H() * 0.55 : -70;
    const steps = 10, dur = quick ? 1400 : rnd(14000, 19000);
    const frames = [];
    for (let s = 0; s <= steps; s++) {
      const f = s / steps;
      const x = x0 + (x1 - x0) * f + (quick ? 0 : Math.sin(f * Math.PI * 4) * 30);
      const y = y0 + (y1 - y0) * (quick ? 1 - Math.pow(1 - f, 3) : f);
      frames.push({ offset: f, transform: 'translate(' + x.toFixed(1) + 'px,'
                    + y.toFixed(1) + 'px) rotate(' + (Math.sin(f * 9) * 6).toFixed(1)
                    + 'deg)' });
    }
    let a;
    try {
      a = node.animate(frames, { duration: dur, easing: quick ? 'linear' : 'ease-in-out',
                                 fill: 'forwards' });
    } catch (e) { node.remove(); return null; }
    const rec = track(node, [a], dur + (quick ? 2400 : 0));
    const boo = () => {
      const r = node.getBoundingClientRect();
      say('BOO!', r.left + r.width / 2, r.top, true, 1600);
      return r;
    };
    if (quick) {
      // Said once it has risen, and then it goes.
      later(() => {
        if (!live.has(rec)) return;
        boo();
        later(() => node.classList.add('gone'), 900);
        later(() => rec.done && rec.done(), 1400);
      }, dur);
    }
    node.addEventListener('click', (e) => {
      e.stopPropagation();
      const r = boo();
      try { a.pause(); a.commitStyles(); a.cancel(); } catch (err) { /* fine */ }
      node.style.pointerEvents = 'none';
      node.classList.add('gone');
      later(() => say(pick(['hee hee', 'eek!', 'you saw me?']),
                      r.left + r.width / 2, r.top + 30, false, 1500), 500);
      found('ghost', r.left + r.width / 2, r.top);
      later(() => rec.done && rec.done(), 900);
    });
    return rec;
  }

  /* -------------------------------------------------- trick, and treat */
  // Colours through `style`, not the fill attribute: an SVG presentation
  // attribute does not read var(), and a candy with no colour is black.
  const CANDY = [
    '<path style="fill:var(--accent)" d="M9 1 3 16h12z"/>'
    + '<path style="fill:var(--warn)" d="M9 1 6.4 7.8h5.2z"/>'
    + '<path style="fill:var(--text)" d="M3 16l1.4-3.6h9.2L15 16z"/>',
    '<rect x="5" y="6" width="8" height="6" rx="3" style="fill:var(--accent-2)"/>'
    + '<path style="fill:var(--accent-2)" d="M5 9 1 6v6zM13 9l4-3v6z"/>',
    '<circle cx="9" cy="9" r="5" style="fill:var(--ok)"/><path d="M9 4v10M4 9h10" '
    + 'style="stroke:var(--bg);stroke-width:1.2"/>',
  ];

  function treat(k) {
    if (!layer || reduced()) return;
    const rr = railRight();
    const n = k || 24;
    for (let i = 0; i < n; i++) {
      const node = el('div', { class: 'spk-candy' });
      node.appendChild(svg(18, 18, '0 0 18 18', pick(CANDY)));
      layer.appendChild(node);
      const x = rnd(rr + 20, W() - 20), dur = rnd(2200, 3600);
      const spin = rnd(-540, 540);
      let a;
      try {
        a = node.animate([
          { transform: 'translate(' + x + 'px,-30px) rotate(0deg)', opacity: 1 },
          { transform: 'translate(' + (x + rnd(-60, 60)) + 'px,' + (H() * 0.8)
                       + 'px) rotate(' + spin + 'deg)', opacity: 1, offset: 0.8 },
          { transform: 'translate(' + (x + rnd(-80, 80)) + 'px,' + (H() + 20)
                       + 'px) rotate(' + (spin * 1.2) + 'deg)', opacity: 0 },
        ], { duration: dur, delay: rnd(0, 700), easing: 'ease-in', fill: 'both' });
      } catch (e) { node.remove(); continue; }
      track(node, [a], dur + 700);
    }
  }

  function trick() {
    if (!layer) return;
    if (reduced()) return;
    swarm(9, Math.random() < 0.5 ? 'bottom' : 'top');
  }

  /* -------------------------------------------------------------- witch */
  const WITCH = '<path d="M2 26c10 1 22-1 34-2l26-2-26 5c-12 2-24 2-34-1z"/>'
    + '<path d="M28 23c-1-6 1-10 5-12l-2-9 7 8c4 1 6 5 5 10z"/>'
    + '<path d="M30 11l9-1 2 2-11 1z"/>';

  function witch() {
    if (!layer || reduced()) return;
    const node = el('div', { class: 'spk-witch' });
    node.appendChild(svg(64, 40, '0 0 64 40', WITCH));
    layer.appendChild(node);
    const rr = railRight(), y = rnd(40, H() * 0.25), dur = 4800;
    let a;
    try {
      a = node.animate([
        { transform: 'translate(' + (W() + 70) + 'px,' + (y + 40) + 'px) scaleX(-1)' },
        { transform: 'translate(' + ((W() + rr) / 2) + 'px,' + (y - 20) + 'px) scaleX(-1)' },
        { transform: 'translate(' + (rr - 80) + 'px,' + (y + 10) + 'px) scaleX(-1)' },
      ], { duration: dur, easing: 'ease-in-out', fill: 'forwards' });
    } catch (e) { node.remove(); return; }
    track(node, [a], dur);
  }

  /* --------------------------------------------------------------- yard */
  const MOON = '<circle class="disc" cx="14" cy="14" r="12"/>'
    + '<circle class="crater" cx="10" cy="11" r="2.4"/>'
    + '<circle class="crater" cx="17" cy="17" r="3"/>'
    + '<circle class="crater" cx="18" cy="8.5" r="1.4"/>';
  const PUMPKIN = '<path class="stem" d="M16 6c0-3 2-5 4-5l1 1c-2 1-3 2-3 4z"/>'
    + '<ellipse class="flesh" cx="11" cy="17.5" rx="8" ry="10"/>'
    + '<ellipse class="flesh" cx="23" cy="17.5" rx="8" ry="10"/>'
    + '<ellipse class="flesh" cx="17" cy="17" rx="8.5" ry="11"/>'
    + '<path class="glow" d="M10 14l3-3 3 3zM18 14l3-3 3 3zM9 20c2 3 5 4 8 4s6-1 8-4l-2 1-1-2-2 2-3-2-3 2-2-2-1 2z"/>';
  const CAULDRON = '<path class="pot" d="M3 9h24c0 9-5 15-12 15S3 18 3 9z"/>'
    + '<ellipse class="brew" cx="15" cy="9" rx="12" ry="2.6"/>'
    + '<path class="pot" d="M6 23l-2 3M24 23l2 3"/>'
    + '<circle class="bubble" cx="10" cy="6" r="1.6"/>'
    + '<circle class="bubble b2" cx="17" cy="5" r="2"/>'
    + '<circle class="bubble b3" cx="21" cy="7" r="1.3"/>';
  const BREWS = ['var(--ok)', 'var(--accent-2)', 'var(--accent)', 'var(--err)',
                 'var(--warn)'];
  const CHANT = ['Double, double', 'toil and trouble', 'Fire burn', 'and cauldron bubble',
                 'eye of newt…', '…and toe of frog'];
  let brew = 0, chant = 0, pumpkinTurn = 0;

  function yardButton(cls, label, inner, w, h, onClick) {
    const b = el('button', { class: cls, type: 'button', title: label,
                             'aria-label': label });
    b.appendChild(svg(w, h, '0 0 ' + w + ' ' + h, inner));
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      const r = b.getBoundingClientRect();
      onClick(r.left + r.width / 2, r.top, b);
    });
    return b;
  }

  function paintYardTitles() {
    if (!yard) return;
    const n = eggs().size;
    const tail = '  ·  ' + n + ' of ' + N_EGGS + ' spooky things found';
    const p = yard.querySelector('.spk-pumpkin');
    if (p) p.title = 'Trick or treat?' + tail;
  }

  function buildYard() {
    /* At the very foot of the rail, under the environment line. Not in the
       nav: that scrolls, and a yard below its fold is a yard nobody finds.
       On a short screen the environment line is hidden, which is the room
       this takes. */
    const host = document.querySelector('#rail .rail-foot');
    if (!host) return null;
    const y = el('div', { class: 'spk-yard' });
    y.appendChild(yardButton('spk-moon', 'The moon', MOON, 28, 28, (x, top) => {
      witch();
      found('moon', x, top);
    }));
    y.appendChild(yardButton('spk-pumpkin', 'Trick or treat?', PUMPKIN, 34, 30,
      (x, top) => {
        pumpkinTurn += 1;
        const isTreat = pumpkinTurn % 3 !== 0;
        say(isTreat ? 'Treat!' : 'Trick!', x, top, true, 1400);
        if (isTreat) treat(); else trick();
        found('pumpkin', x, top);
      }));
    y.appendChild(yardButton('spk-cauldron', 'A cauldron', CAULDRON, 30, 26,
      (x, top, b) => {
        brew = (brew + 1) % BREWS.length;
        b.style.setProperty('--brew', BREWS[brew]);
        say(CHANT[chant++ % CHANT.length], x, top, false, 1500);
        found('cauldron', x, top);
      }));
    host.appendChild(y);
    return y;
  }

  /* ---------------------------------------------------- typed words */
  function onKey(e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target;
    if (t && (t.isContentEditable
              || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || ''))) return;
    if (!e.key || e.key.length !== 1) return;
    typed = (typed + e.key.toLowerCase()).slice(-12);
    if (/boo$/.test(typed)) {
      typed = '';
      ghost('boo');
      found('boo', W() / 2, H() * 0.55);
    } else if (/treat$/.test(typed)) { typed = ''; treat(); }
    else if (/trick$/.test(typed)) { typed = ''; trick(); }
    else if (/spiders$/.test(typed)) { typed = ''; swarm(7, 'top'); }
  }

  /* The cobweb in the top corner notices the mouse by where it is, not by
     a box laid over the buttons there. */
  function onMove(e) {
    if (e.clientY > 40 || e.clientX < W() - 90) return;
    const now = Date.now();
    if (now < webCool) return;
    webCool = now + 9000;
    dangle(W() - rnd(30, 70));
  }

  /* -------------------------------------------------------- schedule */
  function every(kind, first, min, max) {
    const go = () => {
      if (!document.hidden && live.size < 6) {
        if (kind === 'crawl') crawl();
        else if (kind === 'dangle') dangle();
        else if (kind === 'bats') bats();
        else if (kind === 'ghost') ghost();
      }
      later(go, rnd(min, max));
    };
    later(go, first);
  }

  /* ---------------------------------------------------- on and off */
  function start(chosen) {
    if (on) return;
    on = true;
    layer = el('div', { id: 'spooky', 'aria-hidden': 'true' });
    const tr = el('div', { class: 'spk-web tr' });
    tr.appendChild(webSvg(104));
    const bl = el('div', { class: 'spk-web bl' });
    bl.appendChild(webSvg(84));
    // Its SVG is drawn for a top-right corner; turned over, it fits the
    // bottom-left one.
    bl.style.transform = 'scale(-1,-1)';
    layer.appendChild(tr);
    layer.appendChild(bl);
    document.body.appendChild(layer);
    yard = buildYard();
    paintYardTitles();
    document.addEventListener('keydown', onKey);
    if (!reduced()) {
      document.addEventListener('pointermove', onMove, { passive: true });
      every('crawl', rnd(4000, 7000), 22000, 50000);
      every('dangle', rnd(16000, 26000), 40000, 85000);
      every('bats', rnd(30000, 45000), 70000, 140000);
      every('ghost', rnd(60000, 90000), 120000, 240000);
    }
    let hinted = true;
    try { hinted = !!localStorage.getItem(HINT_KEY); } catch (e) { /* ignore */ }
    if (chosen && !hinted) {
      try { localStorage.setItem(HINT_KEY, '1'); } catch (e) { /* ignore */ }
      later(() => {
        const p = yard && yard.querySelector('.spk-pumpkin');
        const r = p ? p.getBoundingClientRect() : { left: 120, top: H() - 120, width: 0 };
        say('Happy Halloween! There are ' + N_EGGS + ' spooky things to find. '
            + 'Start with me.', r.left + r.width / 2 + 80, r.top, false, 7000);
      }, 900);
    }
  }

  function stop() {
    if (!on) return;
    on = false;
    for (const t of timers) clearTimeout(t);
    timers.clear();
    for (const rec of Array.from(live)) {
      for (const a of rec.anims) { try { a.cancel(); } catch (e) { /* gone */ } }
      rec.node.remove();
    }
    live.clear();
    document.removeEventListener('keydown', onKey);
    document.removeEventListener('pointermove', onMove);
    if (layer) layer.remove();
    if (yard) yard.remove();
    layer = null;
    yard = null;
    typed = '';
  }

  /* Called by applyTheme on every path into a theme. `chosen` is true when a
     person picked it, false when it was restored at boot or synced from
     another window -- the welcome is said once, to somebody choosing it. */
  function sync(theme, chosen) {
    if (theme === THEME && !popout()) start(!!chosen);
    else stop();
  }

  return {
    sync,
    // For the harness and for anyone curious in the console.
    spawn(kind, arg) {
      if (!on) return null;
      return ({ crawl, dangle, bats, ghost, treat, trick, witch, swarm })[kind](arg);
    },
    state() {
      return { on, live: live.size, timers: timers.size,
               eggs: Array.from(eggs()), of: N_EGGS };
    },
    EGGS,
  };
})();
