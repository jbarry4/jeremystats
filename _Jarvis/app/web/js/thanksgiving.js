/* thanksgiving.js -- Thanksgiving. Absurdly.

   A theme like the others for colour (app.css, `data-theme="thanksgiving"`),
   plus a layer that only exists while it is on. Asked for on 2026-11-02 as
   "so over the top it's not even funny -- like 20 features, easter eggs,
   things that just get in your way". So:

   Always there
     1  the palette: roast, pumpkin, cranberry, gold and sage
     2  a buffalo-plaid tablecloth along the top of the window
     3  a garland of leaves strung under it, swaying
     4  a plaid seam down the edge of the rail
     5  a pilgrim hat on the Jarvis mark
     6  a drumstick for a mouse pointer
     7  every toast signs off with a turkey, a pie or a gobble
     8  the harvest table at the foot of the rail: a cornucopia, a pie and a
        gravy boat, the days to Thanksgiving, and what Jarvis is thankful for
   Coming and going
     9  leaves falling, all the time
    10  a leaf pile that grows along the bottom of the window
    11  Sir Gobbles, the turkey, strutting along the bottom
    12  a parade balloon drifting over everything
    13  a can of cranberry sauce that plops into the corner and jiggles
    14  a wishbone, waiting to be pulled
   In your way (each one a click to be rid of, none of them ever presses
   anything for you)
    15  Sir Gobbles lands on a button and sits on it
    16  Uncle Dave slides in from the right with an opinion
    17  "Seconds?" -- a card asking whether you want more
    18  food coma: after lunch the whole window yawns
   Easter eggs (14, remembered on this machine)
    19  crunch a falling leaf; rake the pile (wave the mouse along it)
    20  make Sir Gobbles gobble; shoo him off a button
    21  tip the cornucopia; eat the last slice of pie; spill the gravy
    22  hear Uncle Dave out; pull the wishbone; poke the cranberry sauce
    23  type "gobble", "pie" or "thanks" anywhere that is not a text box
    24  the Konami code starts the parade
    25  all fourteen: the finale
   And
    26  it is the default for everyone in November. The first time Jarvis
        opens on a machine this November it switches to this theme, once
        (`season`). Any theme picked by hand after that sticks. On December 1
        a machine that never picked anything goes back to the theme it had.

   The rules spooky.js keeps, kept here:
   - Built when the theme is on, and every node, timer, listener and
     animation removed when it is not. `sync` is called from applyTheme on
     every path, and from Jarvis Light.
   - The main window only. A pop-out gets the palette, not the visitors.
   - Nothing presses anything. The layer is pointer-events none; only the
     things you are meant to poke take the pointer. Something that sits on
     a button takes the click itself, and the button never hears it.
   - Under every toast (60) and every dialog (70).
   - Nothing moves for prefers-reduced-motion, nothing new is sent while the
     window is hidden, and Jarvis Light sends none of it.
   - A frame a web/_dev harness drives gets the layer but none of the
     schedule and no November switch: a turkey sitting on the button a
     harness is about to press would be a very confusing failure. A harness
     calls `spawn` for what it wants to see.
   - What has been found is remembered on this machine (localStorage), and
     nowhere else. */
BARRY.thanksgiving = (function () {
  const THEME = 'thanksgiving';
  const EGG_KEY = 'barry.gobble.eggs';
  const HINT_KEY = 'barry.gobble.hinted';
  const SEASON_KEY = 'barry.gobble.season';
  const EGGS = {
    leaf: 'crunched a falling leaf',
    rake: 'raked the leaf pile',
    turkey: 'made Sir Gobbles gobble',
    shoo: 'shooed Sir Gobbles off a button',
    cornucopia: 'tipped over the cornucopia',
    pie: 'ate the last slice of pie',
    gravy: 'spilled the gravy',
    uncle: 'heard Uncle Dave out',
    wishbone: 'pulled the wishbone',
    cranberry: 'poked the cranberry sauce',
    gobble: 'typed gobble',
    piefly: 'took a pie to the face',
    thanks: 'said thanks',
    parade: 'started the parade',
  };
  const N_EGGS = Object.keys(EGGS).length;
  const SVGNS = 'http://www.w3.org/2000/svg';
  const KONAMI = ['arrowup', 'arrowup', 'arrowdown', 'arrowdown', 'arrowleft',
                  'arrowright', 'arrowleft', 'arrowright', 'b', 'a'];

  let on = false;
  let layer = null;
  let yard = null;
  let pile = null;
  let garland = null;
  let seam = null;
  let railWatch = null;
  const timers = new Set();
  const live = new Set();        // { node, anims, kind }
  let typed = '';
  let keys = [];
  let lastInput = 0;
  let pileN = 0;
  let rakeTrail = [];
  let pieLeft = 6;
  let sitting = null;
  let secondsCard = null;
  let uncleCard = null;
  let tickTimer = null;

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
  const harness = () => typeof HARNESS_FRAME !== 'undefined' && HARNESS_FRAME;
  const rnd = (a, b) => a + Math.random() * (b - a);
  const pick = (xs) => xs[Math.floor(Math.random() * xs.length)];
  const W = () => window.innerWidth;
  const H = () => window.innerHeight;
  const railRight = () => {
    const r = document.getElementById('rail');
    return r ? Math.max(0, r.getBoundingClientRect().right) : 0;
  };
  const floor = () => H() - 6;

  /* ---------------------------------------------------------------- timers */
  function later(fn, ms) {
    const t = setTimeout(() => { timers.delete(t); if (on) fn(); }, ms);
    timers.add(t);
    return t;
  }

  /* A visitor that is moving: its node and its animations, so `stop` can
     end all of them. Removed when its animations finish, and on a timer as
     well, because `finished` does not always resolve (a background tab, a
     test runner's virtual clock). `landed` runs only when it got where it
     was going -- a leaf that is crunched on the way down is not in the
     pile. */
  function track(node, anims, ms, kind, landed) {
    const rec = { node, anims, kind: kind || 'thing' };
    live.add(rec);
    const done = (natural) => {
      if (!live.has(rec)) return;
      live.delete(rec);
      for (const a of rec.anims) { try { a.cancel(); } catch (e) { /* gone */ } }
      node.remove();
      if (natural && landed) { try { landed(); } catch (e) { /* decoration */ } }
    };
    rec.done = done;
    later(() => done(true), (ms || 0) + 600);
    for (const a of anims) {
      if (a && a.finished) a.finished.then(() => {
        if (rec.anims.every((x) => x.playState === 'finished')) done(true);
      }).catch(() => { /* cancelled */ });
    }
    return rec;
  }
  const count = (kind) => Array.from(live).filter((r) => r.kind === kind).length;

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

  // Colours through `style`: an SVG presentation attribute does not read var().
  const LEAVES = [
    'M12 1.5l1.8 3.6 2.6-1.1-.6 3.9 3.6-.4-2.3 3 3 1.9-4.2 1.2.9 3.5-3.6-1.7'
    + '-1.2 4.1-1.2-4.1-3.6 1.7.9-3.5-4.2-1.2 3-1.9-2.3-3 3.6.4-.6-3.9 2.6 1.1z',
    'M12 2c2 1 1 3 3 3s2 2 1 3 2 2 1 4-2 1-2 3 1 3-1 4-2 1-2 2-2-1-2-2-2-1-1-4'
    + '-2-1-2-3 1-2 1-4 0-2 1-3 3-3 1-2 3-3z',
    'M12 2C6 6 5 14 12 21c7-7 6-15 0-19z',
  ];
  const FILLS = ['var(--gb-l1)', 'var(--gb-l2)', 'var(--gb-l3)', 'var(--gb-l4)'];
  function leafSvg(size, shape, fill) {
    return svg(size, size, '0 0 24 24',
      '<path style="fill:' + (fill || pick(FILLS)) + '" d="' + (shape || pick(LEAVES)) + '"/>'
      + '<path class="vein" d="M12 22.5V7"/>');
  }

  /* Sir Gobbles, facing right. The tail is two rings of feathers fanned
     about one point behind the body, so `fan` can spread them. */
  const TURKEY = (function () {
    let tail = '';
    [[-70, 2], [-35, 1], [0, 3], [35, 1], [70, 2]].forEach(([a, c]) => {
      tail += '<ellipse cx="24" cy="11" rx="7" ry="15" transform="rotate(' + a
        + ' 24 30)" style="fill:var(--gb-l' + c + ')"/>';
    });
    [-50, -16, 16, 50].forEach((a) => {
      tail += '<ellipse cx="24" cy="17" rx="5" ry="10" transform="rotate(' + a
        + ' 24 30)" style="fill:var(--gb-l4)"/>';
    });
    return '<g class="tail">' + tail + '</g>'
      + '<g class="legs"><path class="leg" d="M25 45l-1 7m0 0l-3 1.4m3-1.4l1.6 1.6"/>'
      + '<path class="leg" d="M32 45l1 7m0 0l-2 1.6m2-1.6l3 1"/></g>'
      + '<ellipse class="body" cx="28" cy="35" rx="14" ry="12"/>'
      + '<path class="wing" d="M19 33c5-5 14-5 17 1-5 5-12 5-17-1z"/>'
      + '<path class="neck" d="M38 32c3-4 4-9 5-14"/>'
      + '<circle class="head" cx="45" cy="16" r="5"/>'
      + '<path class="beak" d="M49.6 15.2l4.6 1.6-4.4 1.4z"/>'
      + '<path class="wattle" d="M48.5 18.5c1.5 2.5 1.2 6-1 7.2-1.6-1.6-1.5-4.4 1-7.2z"/>'
      + '<circle class="eye" cx="46.3" cy="14.6" r="1.1"/>'
      + '<circle class="glint" cx="46.6" cy="14.2" r=".35"/>';
  }());

  function turkeyNode(cls, title) {
    const n = el('div', { class: 'gb-turkey gb-hit' + (cls ? ' ' + cls : ''),
                          title: title || 'Sir Gobbles' });
    n.appendChild(svg(64, 56, '0 0 64 56', TURKEY));
    return n;
  }

  /* ---------------------------------------------------------- the bubble */
  function say(text, x, y, big, ms) {
    if (!layer) return null;
    const b = el('div', { class: 'gb-say' + (big ? ' big' : ''), text });
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
      if (n >= N_EGGS) finale();
      else {
        say('You ' + EGGS[id] + ' — ' + n + ' of ' + N_EGGS
            + ' Thanksgiving things found', x, y - 26, false, 3600);
      }
    }, 700);
    paintYardTitles();
    return true;
  }

  function finale() {
    say('You found all ' + N_EGGS + '! Happy Thanksgiving 🦃🥧🍂',
        W() / 2, H() / 2, true, 6500);
    leafStorm(48);
    later(() => parade(false), 1200);
    later(() => stampede(7), 2600);
  }

  /* --------------------------------------------------------- 9. leaves */
  function leaf(opts) {
    if (!layer) return null;
    const o = opts || {};
    const n = el('div', { class: 'gb-leaf gb-hit', title: 'A leaf' });
    const size = Math.round(rnd(16, 28));
    n.appendChild(leafSvg(size));
    layer.appendChild(n);
    const rr = railRight();
    const x0 = o.x != null ? o.x : rnd(rr + 10, W() - 10);
    const y0 = o.y != null ? o.y : -30;
    const drift = rnd(-160, 160), amp = rnd(18, 46), ph = rnd(0, 6);
    const y1 = floor() - rnd(0, 10);
    const dur = o.dur || rnd(8000, 14000);
    const spin = rnd(-420, 420);
    const frames = [];
    for (let s = 0; s <= 10; s++) {
      const f = s / 10;
      const x = x0 + drift * f + Math.sin(f * Math.PI * 3 + ph) * amp;
      const y = y0 + (y1 - y0) * f;
      frames.push({ offset: f, transform: 'translate(' + x.toFixed(1) + 'px,'
                    + y.toFixed(1) + 'px) rotate(' + (spin * f).toFixed(0) + 'deg)' });
    }
    let a;
    try {
      a = n.animate(frames, { duration: dur, easing: 'linear', fill: 'forwards' });
    } catch (e) { n.remove(); return null; }
    const rec = track(n, [a], dur, 'leaf', () => addToPile(1));
    n.addEventListener('click', (e) => {
      e.stopPropagation();
      const r = n.getBoundingClientRect();
      const x = r.left + r.width / 2, y = r.top + r.height / 2;
      crumbs(x, y);
      rec.done(false);
      say(pick(['Crunch.', 'CRUNCH.', 'Satisfying.', '*crisp*', 'Autumn!']),
          x, y, false, 1300);
      found('leaf', x, y);
    });
    return rec;
  }

  function crumbs(x, y) {
    for (let i = 0; i < 7; i++) {
      const c = el('div', { class: 'gb-crumb' });
      c.style.background = pick(FILLS);
      layer.appendChild(c);
      const ang = rnd(0, Math.PI * 2), d = rnd(18, 46);
      let a;
      try {
        a = c.animate([
          { transform: 'translate(' + x + 'px,' + y + 'px)', opacity: 1 },
          { transform: 'translate(' + (x + Math.cos(ang) * d) + 'px,'
                       + (y + Math.sin(ang) * d + 30) + 'px) rotate(200deg)', opacity: 0 },
        ], { duration: 700, easing: 'ease-out', fill: 'forwards' });
      } catch (e) { c.remove(); continue; }
      track(c, [a], 700, 'crumb');
    }
  }

  function leafStorm(k) {
    for (let i = 0; i < k; i++) later(() => leaf({ dur: rnd(4200, 7000) }), i * 70);
  }

  /* ------------------------------------------------------ 10. the pile */
  const pileH = () => Math.round(Math.min(30, 2 + pileN * 0.8));

  function placePile() {
    if (!pile) return;
    pile.style.left = railRight() + 'px';
    pile.style.height = pileH() + 'px';
  }

  function addToPile(k) {
    if (!pile) return;
    for (let i = 0; i < (k || 1); i++) {
      pileN += 1;
      if (pile.childElementCount >= 80) continue;
      const l = el('div', { class: 'gb-pl' });
      l.appendChild(leafSvg(Math.round(rnd(11, 17))));
      l.style.left = rnd(0, 98).toFixed(1) + '%';
      l.style.bottom = Math.round(rnd(-5, Math.max(0, pileH() - 9))) + 'px';
      l.style.transform = 'rotate(' + Math.round(rnd(0, 360)) + 'deg)';
      pile.appendChild(l);
    }
    placePile();
  }

  function rake() {
    if (!pile || !pileN) return;
    const bits = Array.from(pile.children);
    const pr = pile.getBoundingClientRect();
    for (const b of bits) {
      const r = b.getBoundingClientRect();
      const fly = el('div', { class: 'gb-pl flying' });
      fly.appendChild(b.firstChild);
      layer.appendChild(fly);
      const x = r.left, y = r.top;
      let a;
      try {
        a = fly.animate([
          { transform: 'translate(' + x + 'px,' + y + 'px)' },
          { transform: 'translate(' + (x + rnd(-120, 120)) + 'px,' + (y - rnd(60, 220))
                       + 'px) rotate(' + rnd(-300, 300) + 'deg)', opacity: 1, offset: 0.6 },
          { transform: 'translate(' + (x + rnd(-200, 200)) + 'px,' + (H() + 20)
                       + 'px) rotate(' + rnd(-500, 500) + 'deg)', opacity: 0 },
        ], { duration: rnd(1100, 1800), easing: 'ease-out', fill: 'forwards' });
      } catch (e) { fly.remove(); continue; }
      track(fly, [a], 1800, 'crumb');
    }
    pile.innerHTML = '';
    pileN = 0;
    placePile();
    say(pick(['Raked!', 'Neat and tidy.', 'They will be back.']),
        pr.left + pr.width / 2, pr.top, false, 1600);
    found('rake', pr.left + pr.width / 2, pr.top);
  }

  /* --------------------------------------------------- 11. Sir Gobbles */
  function strut(opts) {
    if (!layer) return null;
    const o = opts || {};
    const n = turkeyNode(o.small ? 'small' : '');
    layer.appendChild(n);
    const ltr = o.ltr != null ? o.ltr : Math.random() < 0.5;
    const rr = railRight();
    const y = floor() - pileH() - 22 - (o.lane || 0);
    const x0 = ltr ? rr - 70 : W() + 70, x1 = ltr ? W() + 70 : rr - 70;
    const sc = o.scale || 1, flip = ltr ? sc : -sc;
    const tf = (x, extra) => 'translate(' + x.toFixed(1) + 'px,' + y.toFixed(1)
      + 'px) scale(' + flip + ',' + sc + ')' + (extra || '');
    const speed = o.speed || rnd(70, 110);
    const move = Math.abs(x1 - x0) / speed * 1000;
    const look = o.fast ? 0 : rnd(900, 1800);
    const dur = move + look;
    const mid = x0 + (x1 - x0) * rnd(0.35, 0.65);
    const fMid = (Math.abs(mid - x0) / speed * 1000) / dur;
    const frames = o.fast
      ? [{ offset: 0, transform: tf(x0) }, { offset: 1, transform: tf(x1) }]
      : [{ offset: 0, transform: tf(x0) },
         { offset: fMid, transform: tf(mid) },
         { offset: fMid + look / dur * 0.5, transform: tf(mid, ' rotate(-4deg)') },
         { offset: fMid + look / dur, transform: tf(mid) },
         { offset: 1, transform: tf(x1) }];
    let a;
    try {
      a = n.animate(frames, { duration: dur, easing: 'linear', fill: 'forwards' });
    } catch (e) { n.remove(); return null; }
    const rec = track(n, [a], dur, 'turkey');
    let gobbled = false;
    n.addEventListener('click', (e) => {
      e.stopPropagation();
      if (gobbled) return;
      gobbled = true;
      const r = n.getBoundingClientRect();
      const x = r.left + r.width / 2;
      a.pause();
      n.classList.add('fan');
      say(pick(['GOBBLE GOBBLE!', 'Gobble?!', 'GOBBLE.', 'gobble gobble gobble']),
          x, r.top, true, 1500);
      feather(x, r.top + 20);
      found('turkey', x, r.top);
      later(() => {
        if (!live.has(rec)) return;
        n.classList.remove('fan');
        a.playbackRate = 3;
        a.play();
      }, 1000);
    });
    return rec;
  }

  function stampede(k) {
    for (let i = 0; i < (k || 9); i++) {
      later(() => strut({ fast: true, ltr: true, speed: rnd(320, 520),
                          scale: rnd(0.5, 0.8), lane: rnd(0, 26), small: true }),
            i * rnd(90, 200));
    }
  }

  function feather(x, y) {
    const f = el('div', { class: 'gb-feather' });
    f.appendChild(svg(12, 30, '0 0 12 30',
      '<path style="fill:' + pick(FILLS) + '" d="M6 1c4 6 5 16 0 28-5-12-4-22 0-28z"/>'
      + '<path class="quill" d="M6 4v26"/>'));
    layer.appendChild(f);
    const frames = [];
    for (let s = 0; s <= 8; s++) {
      const p = s / 8;
      frames.push({ offset: p, transform: 'translate(' + (x + Math.sin(p * 9) * 26).toFixed(1)
                    + 'px,' + (y + (floor() - y) * p).toFixed(1) + 'px) rotate('
                    + (Math.sin(p * 9) * 40).toFixed(0) + 'deg)' });
    }
    let a;
    try { a = f.animate(frames, { duration: 3200, easing: 'linear', fill: 'forwards' }); }
    catch (e) { f.remove(); return; }
    track(f, [a], 3200, 'crumb');
  }

  /* ----------------------------------- 15. Sir Gobbles sits on a button */
  function seatFor() {
    const rr = railRight();
    const ok = (b) => {
      if (b.closest('#rail, #gobble, .modal-backdrop, .theme-pop, #toasts')) return false;
      const r = b.getBoundingClientRect();
      if (r.width < 36 || r.height < 18 || r.top < 50 || r.bottom > H() - 50
          || r.left < rr + 10 || r.right > W() - 10) return false;
      const at = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return !!at && (at === b || b.contains(at));
    };
    const all = Array.from(document.querySelectorAll('#app button, #app [role="button"]'))
      .filter(ok);
    return all.length ? pick(all) : null;
  }

  function perch(target) {
    if (sitting && !live.has(sitting)) sitting = null;
    if (!layer || sitting) return null;
    const b = target || seatFor();
    if (!b) return null;
    const r = b.getBoundingClientRect();
    const n = turkeyNode('perched', 'Sir Gobbles is sitting on this. Click to shoo.');
    layer.appendChild(n);
    const x = r.left + r.width / 2, y = r.top + r.height / 2 - 8;
    const at = (px, py, s) => 'translate(' + px.toFixed(1) + 'px,' + py.toFixed(1)
      + 'px) scale(' + s + ',1)';
    let a;
    try {
      a = n.animate([{ transform: at(W() + 80, -70, -1) },
                     { transform: at(x, y, -1) }],
                    { duration: reduced() ? 1 : 1500, easing: 'cubic-bezier(.2,.7,.3,1)',
                      fill: 'forwards' });
    } catch (e) { n.remove(); return null; }
    // Not tracked by the landing, which finishes in a second and a half:
    // he stays until shooed or bored.
    const rec = track(n, [], 20000, 'perch');
    rec.anims.push(a);
    sitting = rec;
    n.classList.add('flap');
    later(() => {
      n.classList.remove('flap');
      // Landed, whatever the animation clock says: in a background tab it
      // can still be on its way, and a turkey hovering beside the button
      // is not sitting on it.
      try { a.finish(); } catch (e) { /* already there */ }
      if (live.has(rec)) {
        say(pick(['Is this seat taken?', 'Mine now.', 'This button is closed for the holiday.',
                  'You wanted to press this? Gobble.', 'Warm. Nice.']), x, y - 18, false, 2600);
      }
    }, 1500);
    const go = (shooed) => {
      if (!live.has(rec)) return;
      const box = n.getBoundingClientRect();
      try { a.commitStyles(); } catch (e) { /* fine */ }
      a.cancel();
      n.classList.add('flap');
      n.style.pointerEvents = 'none';
      let b2;
      try {
        b2 = n.animate([{ transform: at(box.left + box.width / 2, box.top + box.height / 2, 1) },
                        { transform: at(railRight() - 60, -90, 1) }],
                       { duration: 900, easing: 'ease-in', fill: 'forwards' });
        rec.anims.push(b2);
      } catch (e) { /* it just goes */ }
      if (shooed) {
        say(pick(['Fine! FINE.', 'Gobble!! (rude)', 'I was keeping it warm.']),
            box.left + box.width / 2, box.top, false, 1500);
        found('shoo', box.left + box.width / 2, box.top);
      }
      later(() => { rec.done(false); if (sitting === rec) sitting = null; }, 950);
    };
    n.addEventListener('click', (e) => { e.stopPropagation(); e.preventDefault(); go(true); });
    later(() => go(false), 9500);
    return rec;
  }

  /* -------------------------------------------------- 12. the balloon */
  function balloon(opts) {
    if (!layer) return null;
    const o = opts || {};
    const n = el('div', { class: 'gb-balloon' });
    n.appendChild(svg(190, 200, '0 0 64 68', TURKEY
      + '<path class="rope" d="M22 47l-6 21M28 47v21M34 47l6 21"/>'));
    if (o.banner) {
      n.appendChild(el('div', { class: 'gb-banner', text: 'HAPPY THANKSGIVING' }));
    }
    layer.appendChild(n);
    const rr = railRight();
    const y = o.y != null ? o.y : rnd(30, H() * 0.3);
    const x0 = W() + 40, x1 = rr - 260;
    const dur = o.dur || rnd(16000, 22000);
    const frames = [];
    for (let s = 0; s <= 8; s++) {
      const f = s / 8;
      frames.push({ offset: f, transform: 'translate(' + (x0 + (x1 - x0) * f).toFixed(1)
                    + 'px,' + (y + Math.sin(f * Math.PI * 2) * 18).toFixed(1) + 'px) rotate('
                    + (Math.sin(f * Math.PI * 3) * 4).toFixed(1) + 'deg) scaleX(-1)' });
    }
    let a;
    try {
      a = n.animate(frames, { duration: dur, delay: o.delay || 0, easing: 'linear',
                              fill: 'both' });
    } catch (e) { n.remove(); return null; }
    return track(n, [a], dur + (o.delay || 0), 'balloon');
  }

  function parade(egg) {
    if (!layer || reduced()) return;
    const y = rnd(40, H() * 0.18);
    balloon({ y, dur: 15000 });
    balloon({ y: y + 30, dur: 15000, delay: 2600, banner: true });
    balloon({ y: y + 10, dur: 15000, delay: 5200 });
    later(() => stampede(5), 3000);
    if (egg) {
      say('🎺 The parade! 🎺', W() / 2, H() * 0.4, true, 3000);
      found('parade', W() / 2, H() * 0.4);
    }
  }

  /* ------------------------------------------ 13. the cranberry sauce */
  const CRAN = '<ellipse class="cran" cx="17" cy="35" rx="14" ry="3.5"/>'
    + '<rect class="cran" x="3" y="6" width="28" height="29"/>'
    + '<ellipse class="cran-top" cx="17" cy="6" rx="14" ry="3.5"/>'
    + '<path class="ridge" d="M3 13c5 2 23 2 28 0M3 20c5 2 23 2 28 0M3 27c5 2 23 2 28 0"/>'
    + '<path class="shine" d="M8 9v22"/>';

  function cranberry() {
    if (!layer || count('cran')) return null;
    const n = el('div', { class: 'gb-cran gb-hit', title: 'Cranberry sauce, can-shaped' });
    const inner = el('div', { class: 'jiggle' });
    inner.appendChild(svg(34, 40, '0 0 34 40', CRAN));
    n.appendChild(inner);
    layer.appendChild(n);
    const x = W() - rnd(90, 260), y = floor() - pileH() - 40;
    let a;
    try {
      a = n.animate([
        { transform: 'translate(' + x + 'px,-60px)' },
        { transform: 'translate(' + x + 'px,' + y + 'px)', offset: 0.7 },
        { transform: 'translate(' + x + 'px,' + (y - 14) + 'px)', offset: 0.82 },
        { transform: 'translate(' + x + 'px,' + y + 'px)' },
      ], { duration: 1100, easing: 'ease-in', fill: 'forwards' });
    } catch (e) { n.remove(); return null; }
    const rec = track(n, [], 26000, 'cran');
    rec.anims.push(a);
    later(() => say('*plop*', x + 17, y, false, 1100), 800);
    n.addEventListener('click', (e) => {
      e.stopPropagation();
      inner.classList.remove('hard');
      void inner.offsetWidth;
      inner.classList.add('hard');
      const r = n.getBoundingClientRect();
      say(pick(['Schlorp.', 'It kept the shape of the can.', 'Ridges intact.',
                'Jellied, not whole-berry. Fight me.']), r.left + 17, r.top, false, 1600);
      found('cranberry', r.left + 17, r.top);
    });
    return rec;
  }

  /* ---------------------------------------------- 14. the wishbone */
  function wishbone() {
    if (!layer || count('wish')) return null;
    const n = el('div', { class: 'gb-wish gb-hit', title: 'A wishbone. Pull it?' });
    n.appendChild(svg(30, 34, '0 0 30 34',
      '<g class="half l"><path d="M15 30C11 22 6 12 5 4"/><circle cx="5" cy="3.5" r="2.6"/></g>'
      + '<g class="half r"><path d="M15 30c4-8 9-18 10-26"/><circle cx="25" cy="3.5" r="2.6"/></g>'));
    layer.appendChild(n);
    const rr = railRight();
    const x = rnd(rr + 60, W() - 60), y = rnd(H() * 0.3, H() * 0.7);
    n.style.left = x + 'px';
    n.style.top = y + 'px';
    const rec = track(n, [], 15000, 'wish');
    let pulled = false;
    n.addEventListener('click', (e) => {
      e.stopPropagation();
      if (pulled) return;
      pulled = true;
      n.classList.add('snap');
      const big = Math.random() < 0.5;
      say(big ? 'You got the big half! Your next p-value will be < 0.05.'
              : 'Small half. Reviewer 2 it is.', x, y, true, 3400);
      found('wishbone', x, y);
      later(() => rec.done(false), 1400);
    });
    return rec;
  }

  /* ---------------------------------------------- 16. Uncle Dave */
  const OPINIONS = [
    'In my day we sorted spikes by hand. Uphill. Both ways.',
    'You know what this data needs? More channels.',
    'p < 0.05 is a state of mind.',
    'Back when I was a postdoc, MATLAB was just MAT.',
    'Kids these days and their thirty kilohertz.',
    'That’s not noise, that’s 60 Hz. I can hear it from here.',
    'Pass the gravy. And the error bars.',
    'I read a paper once. Didn’t care for it.',
    'Why is the turkey sitting on your button?',
    'Reviewer 2 is my cousin, you know.',
    'Have you tried turning the mouse off and on again? The rodent, I mean.',
    'Dentate spikes are just hippocampus hiccups. Look it up.',
    'You call that a sample size?',
    'When I was your age we filtered with a capacitor and hope.',
    'Is the cloud the one with the rain in it?',
    'I could have done this in Excel.',
  ];

  function uncle() {
    if (uncleCard && !uncleCard.isConnected) uncleCard = null;
    if (!layer || uncleCard) return null;
    const said = el('div', { class: 'gb-uncle-say', text: pick(OPINIONS) });
    const c = el('div', { class: 'gb-uncle gb-hit', title: 'Uncle Dave has thoughts. Click.' }, [
      el('div', { class: 'gb-uncle-face', text: '🧔' }),
      el('div', { class: 'gb-uncle-text' }, [
        el('div', { class: 'gb-uncle-name', text: 'Uncle Dave' }), said]),
    ]);
    layer.appendChild(c);
    uncleCard = c;
    let a;
    try {
      a = c.animate([{ transform: 'translateX(110%)' }, { transform: 'translateX(0)' }],
                    { duration: reduced() ? 1 : 520, easing: 'cubic-bezier(.2,.8,.3,1.15)',
                      fill: 'forwards' });
    } catch (e) { c.remove(); uncleCard = null; return null; }
    const rec = track(c, [], 30000, 'uncle');
    rec.anims.push(a);
    const leave = () => {
      if (!live.has(rec)) return;
      let b;
      try {
        b = c.animate([{ transform: 'translateX(0)' }, { transform: 'translateX(115%)' }],
                      { duration: 420, easing: 'ease-in', fill: 'forwards' });
        rec.anims.push(b);
      } catch (e) { /* gone anyway */ }
      later(() => { rec.done(false); if (uncleCard === c) uncleCard = null; }, 440);
    };
    let heard = false;
    c.addEventListener('click', (e) => {
      e.stopPropagation();
      if (heard) { leave(); return; }
      heard = true;
      said.textContent = pick(OPINIONS.filter((t) => t !== said.textContent))
        + ' Anyway.';
      const r = c.getBoundingClientRect();
      found('uncle', r.left + r.width / 2, r.top);
      later(leave, 3800);
    });
    later(leave, 12000);
    return rec;
  }

  /* ---------------------------------------------- 17. Seconds? */
  function seconds() {
    if (!layer || secondsCard) return null;
    const ask = pick([['Seconds?', 'There’s more pie. There is always more pie.'],
                      ['Thirds?', 'Nobody is counting. (Sir Gobbles is counting.)'],
                      ['Room for dessert?', 'Pumpkin, pecan, or apple. Or all three.'],
                      ['More stuffing?', 'It has been fourteen minutes since your last stuffing.']]);
    const close = (line) => {
      if (!secondsCard) return;
      const r = secondsCard.getBoundingClientRect();
      secondsCard.remove();
      secondsCard = null;
      if (line) say(line, r.left + r.width / 2, r.top + 10, false, 1600);
    };
    const btn = (text, kind, fn) => (BARRY.ui && BARRY.ui.button
      ? BARRY.ui.button({ kind, size: 'sm', text, onclick: fn })
      : el('button', { type: 'button', text, onclick: fn }));
    const c = el('div', { class: 'gb-seconds', role: 'dialog', 'aria-label': ask[0] }, [
      el('div', { class: 'gb-sec-title', text: '🥧 ' + ask[0] }),
      el('div', { class: 'gb-sec-text', text: ask[1] }),
      el('div', { class: 'gb-sec-btns' }, [
        btn('Yes please', 'primary', () => {
          const r = c.getBoundingClientRect();
          close('Good choice.');
          spill(r.left + r.width / 2, r.top);
        }),
        btn('I’m stuffed', 'ghost', () => close('Suit yourself.')),
      ]),
    ]);
    layer.appendChild(c);
    secondsCard = c;
    later(() => { if (secondsCard === c) close(null); }, 20000);
    return c;
  }

  /* ---------------------------------------------- 18. food coma */
  function coma(force) {
    if (!layer) return null;
    const now = new Date();
    const h = now.getHours() + now.getMinutes() / 60;
    if (!force && !(h >= 12.5 && h < 14.5)) return null;
    const v = el('div', { class: 'gb-coma' });
    layer.appendChild(v);
    let a;
    try {
      a = v.animate([{ opacity: 0 }, { opacity: 1, offset: 0.35 }, { opacity: 1, offset: 0.6 },
                     { opacity: 0 }], { duration: 3400, easing: 'ease-in-out', fill: 'forwards' });
    } catch (e) { v.remove(); return null; }
    later(() => say('*yawn* … food coma', W() / 2, H() * 0.45, false, 2000), 700);
    return track(v, [a], 3400, 'coma');
  }

  /* ---------------------------------------------- the harvest table */
  function spill(x, y) {
    if (!layer) return;
    const FOOD = ['🌽', '🍎', '🍇', '🎃', '🥕', '🍐', '🥖', '🍠', '🌰', '🧈'];
    const k = reduced() ? 0 : 16;
    for (let i = 0; i < k; i++) {
      const f = el('div', { class: 'gb-food', text: pick(FOOD) });
      layer.appendChild(f);
      const x1 = x + rnd(60, Math.max(80, W() - x - 40));
      const top = y - rnd(80, 220);
      const end = floor() - pileH() - 12;
      let a;
      try {
        a = f.animate([
          { transform: 'translate(' + x + 'px,' + y + 'px) rotate(0)', opacity: 1 },
          { transform: 'translate(' + ((x + x1) / 2) + 'px,' + top + 'px) rotate(180deg)',
            offset: 0.35 },
          { transform: 'translate(' + x1 + 'px,' + end + 'px) rotate(360deg)', offset: 0.7 },
          { transform: 'translate(' + (x1 + 30) + 'px,' + (end - 14) + 'px) rotate(400deg)',
            offset: 0.8 },
          { transform: 'translate(' + (x1 + 50) + 'px,' + end + 'px) rotate(430deg)',
            opacity: 1, offset: 0.9 },
          { transform: 'translate(' + (x1 + 50) + 'px,' + end + 'px) rotate(430deg)',
            opacity: 0 },
        ], { duration: rnd(2400, 3400), delay: i * 60, easing: 'ease-out', fill: 'both' });
      } catch (e) { f.remove(); continue; }
      track(f, [a], 3400 + i * 60, 'crumb');
    }
  }

  function gravy() {
    if (!layer) return;
    const rr = railRight();
    const x = rnd(rr + 40, W() - 40);
    const g = el('div', { class: 'gb-gravy' });
    g.style.left = x + 'px';
    layer.appendChild(g);
    const len = H() * rnd(0.45, 0.95);
    let a;
    try {
      a = g.animate([
        { height: '0px', opacity: 1 },
        { height: len + 'px', opacity: 1, offset: 0.55 },
        { height: len + 'px', opacity: 1, offset: 0.85 },
        { height: len + 'px', opacity: 0 },
      ], { duration: 9000, easing: 'ease-in', fill: 'forwards' });
    } catch (e) { g.remove(); return; }
    track(g, [a], 9000, 'gravy');
  }

  function pieInner(left) {
    let d = '';
    const R = 12.5;
    for (let i = 0; i < 6; i++) {
      const a0 = (-90 + i * 60) * Math.PI / 180, a1 = (-90 + (i + 1) * 60) * Math.PI / 180;
      d += '<path class="' + (i < left ? 'slice' : 'gone') + '" d="M0 0L'
        + (R * Math.cos(a0)).toFixed(2) + ' ' + (R * Math.sin(a0)).toFixed(2) + 'A' + R + ' ' + R
        + ' 0 0 1 ' + (R * Math.cos(a1)).toFixed(2) + ' ' + (R * Math.sin(a1)).toFixed(2) + 'Z"/>';
    }
    return '<g transform="translate(17 12) scale(1 .62)"><circle class="tin" r="16"/>'
      + '<circle class="crust" r="14.6"/>' + d + '</g>';
  }

  function eatPie(x, top, b) {
    if (pieLeft <= 0) {
      say('There is no pie. Only crumbs.', x, top, false, 1600);
      return;
    }
    pieLeft -= 1;
    const s = b.querySelector('svg');
    if (s) s.innerHTML = pieInner(pieLeft);
    crumbs(x, top + 8);
    if (pieLeft === 0) {
      say('Someone ate ALL the pie.', x, top, true, 2400);
      found('pie', x, top);
      later(() => {
        pieLeft = 6;
        const s2 = yard && yard.querySelector('.gb-pie svg');
        if (s2) s2.innerHTML = pieInner(pieLeft);
        const p = yard && yard.querySelector('.gb-pie');
        if (p) {
          const r = p.getBoundingClientRect();
          say('Fresh pie!', r.left + r.width / 2, r.top, false, 1800);
        }
      }, 30000);
    } else {
      say(pick(['Mmm, pumpkin.', 'Just a sliver.', 'The diet starts Monday.',
                'One more, for science.', 'Is that whipped cream?', 'Pecan? Bold.']),
          x, top, false, 1300);
    }
  }

  const HORN = '<path class="horn" d="M38 8C28 1 12 2 4 12c-2 3-3 6-2 9 1-4 4-7 8-8 8-2 18 0 27 6 2-4 2-8 1-11z"/>'
    + '<path class="ridge" d="M10 6c2 4 3 8 2 12M17 4c2 4 3 9 2 13M24 4c2 4 2 9 1 14M31 6c1 4 1 8 0 12"/>'
    + '<circle cx="35" cy="18" r="3.4" style="fill:var(--gb-l2)"/>'
    + '<circle cx="31" cy="21" r="2.8" style="fill:var(--accent-2)"/>'
    + '<ellipse cx="37" cy="23" rx="4" ry="2.4" style="fill:var(--gb-l3)"/>'
    + '<circle cx="33" cy="25" r="2.6" style="fill:var(--gb-l1)"/>';
  const GRAVY = '<path class="boat" d="M3 10h19c4 0 7-3 9-6-1 6-4 13-12 13H11C6 17 3 14 3 10z"/>'
    + '<path class="handle" d="M4 11C0 11 0 6 4 6"/>'
    + '<ellipse class="gravy-top" cx="13" cy="10" rx="9.5" ry="1.8"/>'
    + '<path class="foot" d="M9 17l-1 3h10l-1-3"/>';

  function yardButton(cls, label, inner, w, h, onClick) {
    const b = el('button', { class: cls, type: 'button', title: label, 'aria-label': label });
    b.appendChild(svg(w, h, '0 0 ' + w + ' ' + h, inner));
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      const r = b.getBoundingClientRect();
      onClick(r.left + r.width / 2, r.top, b);
    });
    return b;
  }

  /* The day itself: the fourth Thursday of November. */
  function turkeyDay(y) {
    const first = new Date(y, 10, 1).getDay();
    return new Date(y, 10, 1 + ((4 - first + 7) % 7) + 21);
  }

  function countdown(now) {
    const t = now || new Date();
    const today = new Date(t.getFullYear(), t.getMonth(), t.getDate());
    const d = Math.round((turkeyDay(t.getFullYear()) - today) / 86400000);
    if (d > 1) return d + ' days to Thanksgiving';
    if (d === 1) return 'Thanksgiving is TOMORROW';
    if (d === 0) return 'It’s Thanksgiving! 🦃';
    if (t.getMonth() === 10) return 'Leftovers, day ' + (-d);
    return 'Thanksgiving is over. The turkey lives on.';
  }

  const THANKFUL = [
    '60 Hz notch filters', 'the VACC, when it is up', 'clean dentate spikes',
    'whoever wrote the channel map down', 'error bars that do not overlap',
    'a recording with no clock breaks', 'coffee', 'the undo button', 'scipy',
    'raw data that loads on the first try', 'mice (the furry kind)',
    'mice (the clicky kind)', 'git, grudgingly', 'Supabase, mostly',
    'a p-value that stayed put', 'reviewer 1', 'pie', 'more pie',
    'the fifth spoonful of stuffing', 'Toothy', 'Ctrl+Z', 'naps',
  ];

  function paintYardTitles() {
    if (!yard) return;
    const n = eggs().size;
    const tail = '  ·  ' + n + ' of ' + N_EGGS + ' Thanksgiving things found';
    const p = yard.querySelector('.gb-pie');
    if (p) p.title = 'Pie. Have a slice.' + tail;
    const c = yard.querySelector('.gb-count');
    if (c) c.textContent = '🦃 ' + countdown();
  }

  function tick() {
    if (!yard) return;
    const t = yard.querySelector('.gb-tick');
    if (t) t.textContent = 'Thankful for: ' + pick(THANKFUL);
  }

  function buildYard() {
    const host = document.querySelector('#rail .rail-foot');
    if (!host) return null;
    const y = el('div', { class: 'gb-yard' });
    const row = el('div', { class: 'gb-yard-row' });
    row.appendChild(yardButton('gb-horn', 'A cornucopia', HORN, 40, 28, (x, top) => {
      spill(x, top);
      say(pick(['Harvest!', 'Abundance!', 'Mind the grapes.']), x, top, false, 1300);
      found('cornucopia', x, top);
    }));
    row.appendChild(yardButton('gb-pie', 'Pie. Have a slice.', pieInner(pieLeft), 34, 24,
      (x, top, b) => eatPie(x, top, b)));
    row.appendChild(yardButton('gb-gravy-boat', 'The gravy boat', GRAVY, 32, 22, (x, top) => {
      gravy();
      say(pick(['Glug glug glug.', 'Oops.', 'That was the good gravy.']), x, top, false, 1400);
      found('gravy', x, top);
    }));
    y.appendChild(row);
    y.appendChild(el('div', { class: 'gb-count' }));
    y.appendChild(el('div', { class: 'gb-tick' }));
    host.appendChild(y);
    return y;
  }

  /* ---------------------------------------------- the garland and seam */
  function buildGarland() {
    const rr = railRight();
    const w = Math.max(100, W() - rr);
    const g = el('div', { class: 'gb-garland' });
    g.style.left = rr + 'px';
    g.style.width = w + 'px';
    const span = 170, n = Math.max(1, Math.round(w / span));
    let d = '';
    for (let i = 0; i < n; i++) {
      const x0 = i * w / n, x1 = (i + 1) * w / n;
      d += 'M' + x0.toFixed(1) + ' 4Q' + ((x0 + x1) / 2).toFixed(1) + ' 26 '
        + x1.toFixed(1) + ' 4';
    }
    g.appendChild(svg(w, 30, '0 0 ' + w + ' 30',
      '<path class="string" d="' + d + '"/>'));
    // Leaves hung along each swag, where the string is at that x.
    for (let i = 0; i < n; i++) {
      const x0 = i * w / n, x1 = (i + 1) * w / n;
      for (const f of [0.18, 0.38, 0.5, 0.62, 0.82]) {
        const x = x0 + (x1 - x0) * f;
        const u = f, yy = (1 - u) * (1 - u) * 4 + 2 * (1 - u) * u * 26 + u * u * 4;
        const lf = el('div', { class: 'gb-gl' });
        lf.style.left = (x - 9).toFixed(1) + 'px';
        lf.style.top = (yy - 2).toFixed(1) + 'px';
        lf.style.animationDelay = (-rnd(0, 3)).toFixed(2) + 's';
        lf.appendChild(leafSvg(18));
        g.appendChild(lf);
      }
    }
    return g;
  }

  function relayout() {
    if (!layer) return;
    if (garland) garland.remove();
    garland = buildGarland();
    layer.appendChild(garland);
    if (seam) seam.style.left = Math.max(0, railRight() - 3) + 'px';
    placePile();
  }

  /* ---------------------------------------------- the big words */
  function pieFace() {
    if (!layer) return;
    const p = el('div', { class: 'gb-pieface', text: '🥧' });
    layer.appendChild(p);
    const cx = W() / 2, cy = H() / 2;
    let a;
    try {
      a = p.animate([
        { transform: 'translate(' + (W() - 60) + 'px,' + (H() - 60) + 'px) scale(.4) rotate(0)' },
        { transform: 'translate(' + cx + 'px,' + cy + 'px) scale(3.2) rotate(540deg)' },
      ], { duration: reduced() ? 1 : 650, easing: 'ease-in', fill: 'forwards' });
    } catch (e) { p.remove(); return; }
    track(p, [a], 700, 'crumb');
    later(() => {
      const s = el('div', { class: 'gb-splat' });
      s.appendChild(svg(320, 260, '0 0 320 260',
        '<path d="M160 20c30 0 40 30 70 20s50 20 40 50 30 40 10 70-10 50-50 50-40 30-70 20'
        + '-40 20-60-10-50-10-40-50-40-40 0-60 30-60 20-50 50-50 40-40 70-30z"/>'
        + '<path d="M120 200v40M180 210v30M220 190v25" class="drip"/>'));
      s.style.left = (cx - 160) + 'px';
      s.style.top = (cy - 130) + 'px';
      layer.appendChild(s);
      let b;
      try {
        b = s.animate([{ opacity: 0, transform: 'scale(.6)' },
                       { opacity: 0.94, transform: 'scale(1)', offset: 0.08 },
                       { opacity: 0.94, transform: 'scale(1) translateY(8px)', offset: 0.75 },
                       { opacity: 0, transform: 'scale(1) translateY(30px)' }],
                      { duration: 3200, easing: 'ease-out', fill: 'forwards' });
      } catch (e) { s.remove(); return; }
      track(s, [b], 3200, 'crumb');
      say('SPLAT.', cx, cy - 120, true, 1500);
    }, 650);
  }

  function thanksBurst() {
    if (!layer) return;
    const cx = W() / 2, cy = H() / 2;
    for (let i = 0; i < 26; i++) {
      const n = el('div', { class: 'gb-pl flying' });
      n.appendChild(leafSvg(Math.round(rnd(14, 24))));
      layer.appendChild(n);
      const ang = rnd(0, Math.PI * 2), d = rnd(120, 380);
      let a;
      try {
        a = n.animate([
          { transform: 'translate(' + cx + 'px,' + cy + 'px) scale(.2)', opacity: 1 },
          { transform: 'translate(' + (cx + Math.cos(ang) * d) + 'px,' + (cy + Math.sin(ang) * d)
                       + 'px) rotate(' + rnd(-400, 400) + 'deg) scale(1)', opacity: 1, offset: 0.6 },
          { transform: 'translate(' + (cx + Math.cos(ang) * d * 1.1) + 'px,'
                       + (cy + Math.sin(ang) * d + 160) + 'px) rotate(' + rnd(-600, 600)
                       + 'deg)', opacity: 0 },
        ], { duration: rnd(1600, 2400), easing: 'ease-out', fill: 'forwards' });
      } catch (e) { n.remove(); continue; }
      track(n, [a], 2400, 'crumb');
    }
    say('Thankful for: ' + pick(THANKFUL) + '. And you.', cx, cy, true, 3200);
  }

  /* ---------------------------------------------------- typed words */
  function onKey(e) {
    if (e.key === 'Escape' && secondsCard) {
      const r = secondsCard.getBoundingClientRect();
      secondsCard.remove();
      secondsCard = null;
      say('Suit yourself.', r.left + r.width / 2, r.top + 10, false, 1400);
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target;
    if (t && (t.isContentEditable
              || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || ''))) return;
    if (!e.key) return;
    lastInput = Date.now();
    keys = keys.concat([e.key.toLowerCase()]).slice(-KONAMI.length);
    if (keys.join(',') === KONAMI.join(',')) {
      keys = [];
      parade(true);
      return;
    }
    if (e.key.length !== 1) return;
    typed = (typed + e.key.toLowerCase()).slice(-12);
    if (/gobble$/.test(typed)) {
      typed = '';
      stampede(9);
      say('GOBBLE GOBBLE GOBBLE', W() / 2, H() * 0.5, true, 2000);
      found('gobble', W() / 2, H() * 0.5);
    } else if (/thanks$/.test(typed)) {
      typed = '';
      thanksBurst();
      found('thanks', W() / 2, H() / 2);
    } else if (/pie$/.test(typed)) {
      typed = '';
      pieFace();
      found('piefly', W() / 2, H() / 2);
    }
  }

  function onMove(e) {
    if (!pile || pileN < 6) return;
    if (e.clientY < H() - pileH() - 30 || e.clientX < railRight()) {
      rakeTrail = [];
      return;
    }
    const now = performance.now();
    rakeTrail.push([now, e.clientX]);
    rakeTrail = rakeTrail.filter(([t]) => now - t < 800);
    let dist = 0;
    for (let i = 1; i < rakeTrail.length; i++) {
      dist += Math.abs(rakeTrail[i][1] - rakeTrail[i - 1][1]);
    }
    if (dist > 700) { rakeTrail = []; rake(); }
  }

  function onDown() { lastInput = Date.now(); }

  /* -------------------------------------------------------- schedule */
  const SPAWN = {
    leaf: () => { if (count('leaf') < 12) leaf(); },
    turkey: () => { if (!count('turkey')) strut(); },
    perch: () => {
      // Not while somebody is in the middle of something, and not in a
      // dialog: a turkey that lands under a pressing finger is a misclick.
      if (Date.now() - lastInput > 2500 && !document.querySelector('.modal-backdrop')) perch();
    },
    balloon: () => { if (!count('balloon')) balloon(); },
    cranberry, wishbone, uncle, seconds,
    coma: () => coma(false),
  };

  function every(kind, first, min, max) {
    const go = () => {
      if (!document.hidden) { try { SPAWN[kind](); } catch (e) { /* decoration */ } }
      later(go, rnd(min, max));
    };
    later(go, first);
  }

  function schedule() {
    every('leaf', rnd(500, 1500), 1200, 3400);
    every('turkey', rnd(8000, 15000), 45000, 100000);
    every('perch', rnd(90000, 150000), 240000, 480000);
    every('balloon', rnd(120000, 200000), 600000, 1100000);
    every('cranberry', rnd(150000, 260000), 480000, 900000);
    every('wishbone', rnd(100000, 200000), 420000, 780000);
    every('uncle', rnd(60000, 120000), 540000, 960000);
    every('seconds', rnd(600000, 900000), 1500000, 2700000);
    every('coma', rnd(240000, 420000), 480000, 840000);
  }

  /* ---------------------------------------------------- on and off */
  function start(chosen) {
    if (on) return;
    on = true;
    document.documentElement.classList.add('gb-on');
    layer = el('div', { id: 'gobble', 'aria-hidden': 'true' });
    layer.appendChild(el('div', { class: 'gb-cloth' }));
    seam = el('div', { class: 'gb-seam' });
    layer.appendChild(seam);
    pile = el('div', { class: 'gb-pile' });
    layer.appendChild(pile);
    document.body.appendChild(layer);
    yard = buildYard();
    relayout();
    paintYardTitles();
    tick();
    tickTimer = setInterval(() => { if (on) { tick(); paintYardTitles(); } }, 9000);
    try {
      const rail = document.getElementById('rail');
      if (rail && window.ResizeObserver) {
        railWatch = new ResizeObserver(() => relayout());
        railWatch.observe(rail);
      }
    } catch (e) { /* the window's resize still does it */ }
    window.addEventListener('resize', relayout);
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onDown, { passive: true, capture: true });
    if (!reduced()) {
      document.addEventListener('pointermove', onMove, { passive: true });
      if (!harness()) {
        // A few leaves already on the ground: it has been autumn for a while.
        addToPile(10);
        schedule();
      }
    }
    let hinted = true;
    try { hinted = !!localStorage.getItem(HINT_KEY); } catch (e) { /* ignore */ }
    if (chosen && !hinted && !harness()) {
      try { localStorage.setItem(HINT_KEY, '1'); } catch (e) { /* ignore */ }
      later(() => {
        const p = yard && yard.querySelector('.gb-pie');
        const r = p ? p.getBoundingClientRect() : { left: 120, top: H() - 120, width: 0 };
        say('Happy Thanksgiving! There are ' + N_EGGS + ' things to find. '
            + 'Start with the pie.', r.left + r.width / 2 + 90, r.top, false, 8000);
      }, 900);
    }
  }

  function stop() {
    if (!on) return;
    on = false;
    for (const t of timers) clearTimeout(t);
    timers.clear();
    if (tickTimer) clearInterval(tickTimer);
    tickTimer = null;
    for (const rec of Array.from(live)) {
      for (const a of rec.anims) { try { a.cancel(); } catch (e) { /* gone */ } }
      rec.node.remove();
    }
    live.clear();
    if (railWatch) { try { railWatch.disconnect(); } catch (e) { /* gone */ } }
    railWatch = null;
    window.removeEventListener('resize', relayout);
    document.removeEventListener('keydown', onKey);
    document.removeEventListener('pointermove', onMove);
    document.removeEventListener('pointerdown', onDown, { capture: true });
    if (layer) layer.remove();
    if (yard) yard.remove();
    document.documentElement.classList.remove('gb-on');
    layer = yard = pile = garland = seam = null;
    sitting = secondsCard = uncleCard = null;
    typed = '';
    keys = [];
    pileN = 0;
    pieLeft = 6;
  }

  /* Called by applyTheme on every path into a theme. `chosen` is a person
     picking it in the picker. A pick of any theme, this one or another,
     after the November switch is what the person wants, and December 1
     leaves it alone. */
  function sync(theme, chosen) {
    if (chosen) {
      const st = seasonState();
      if (st && !st.chosen) saveSeason(Object.assign({}, st, { chosen: true }));
    }
    const lite = BARRY.lite && BARRY.lite.on();
    if (theme === THEME && !popout() && !lite) start(!!chosen);
    else stop();
  }

  /* ---------------------------------------------- 26. November */
  /* Kept in two places: this browser, and the preferences under this
     machine's name, so a cleared browser does not switch a second time and
     December finds what to put back. */
  function host() {
    return ((BARRY.state.catalog || {}).system || {}).hostname || null;
  }

  function seasonState() {
    try {
      const h = host();
      const all = BARRY.prefs && BARRY.prefs.get ? (BARRY.prefs.get('gobble', {}) || {}) : {};
      if (h && all[h]) return all[h];
    } catch (e) { /* preferences not in yet */ }
    try { return JSON.parse(localStorage.getItem(SEASON_KEY) || 'null'); }
    catch (e) { return null; }
  }

  function saveSeason(st) {
    try { localStorage.setItem(SEASON_KEY, JSON.stringify(st)); } catch (e) { /* private */ }
    try {
      const h = host();
      if (h && BARRY.prefs && BARRY.prefs.set) {
        const all = Object.assign({}, BARRY.prefs.get('gobble', {}) || {});
        all[h] = st;
        BARRY.prefs.set('gobble', all);
      }
    } catch (e) { /* this browser has it */ }
  }

  /* What to do, given the date, the season record and the theme on now.
     Pure, so a harness can ask it about any day. */
  function plan(now, st, theme) {
    const y = now.getFullYear();
    if (now.getMonth() === 10) {
      if (st && st.year === y) return { act: null };
      return { act: 'switch', save: { year: y, from: theme, chosen: false } };
    }
    if (st && !st.chosen && !st.restored && (now.getFullYear() > st.year
                                             || now.getMonth() > 10)) {
      return { act: theme === THEME && st.from && st.from !== THEME ? 'restore' : null,
               save: Object.assign({}, st, { restored: true }) };
    }
    return { act: null };
  }

  function season(now) {
    if (harness() || popout()) return null;
    try { if (new URLSearchParams(location.search).get('theme')) return null; }
    catch (e) { /* no address */ }
    const p = plan(now || new Date(), seasonState(), BARRY.state.theme);
    if (p.save) saveSeason(p.save);
    if (p.act === 'switch' && BARRY.state.theme !== THEME) {
      applyTheme(THEME, true, false);
      setTimeout(() => {
        // No name in it: on a machine where the name is still hidden, a
        // toast that says it gives the reveal away (js/jarvis.js).
        toast('Happy Thanksgiving! Everything has dressed up for November. To turn '
              + 'it off, pick any other theme at the bottom of the rail. It also '
              + 'leaves by itself on December 1.', null, 16000);
        try { localStorage.setItem(HINT_KEY, '1'); } catch (e) { /* ignore */ }
        if (on) {
          const pie = yard && yard.querySelector('.gb-pie');
          const r = pie ? pie.getBoundingClientRect() : { left: 120, top: H() - 120, width: 0 };
          say('There are ' + N_EGGS + ' Thanksgiving things to find. Start with the pie.',
              r.left + r.width / 2 + 90, r.top, false, 9000);
        }
      }, 1200);
    } else if (p.act === 'restore') {
      applyTheme(p.save.from, true, false);
      setTimeout(() => toast('The turkey has gone home. Your theme is back.', null, 9000), 800);
    }
    return p.act;
  }

  return {
    sync,
    season,
    // For the harness and for anyone curious in the console.
    spawn(kind, arg) {
      if (!on) return null;
      return ({ leaf, strut, stampede, perch, balloon, parade, cranberry, wishbone,
                uncle, seconds, coma: () => coma(true), spill: () => spill(W() / 2, H() / 2),
                gravy, pieFace, thanksBurst, rake, addToPile, leafStorm })[kind](arg);
    },
    state() {
      return { on, live: live.size, timers: timers.size, pile: pileN, pie: pieLeft,
               sitting: !!sitting, seconds: !!secondsCard, uncle: !!uncleCard,
               eggs: Array.from(eggs()), of: N_EGGS };
    },
    _plan: plan,
    _countdown: countdown,
    EGGS,
  };
})();
