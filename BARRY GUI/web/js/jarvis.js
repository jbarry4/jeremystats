/* ==========================================================================
   jarvis.js -- the name, the mark, and the switch that hides both.

   Three jobs, kept together because they are one fact: whether this
   machine is showing the name.

   1. The mark. A power symbol whose stroke is a dentate spike: the ring is
      broken at the top and the spike fires up through the gap. It reads as
      "on" at 16 px, which is what a tab icon is, and as what this
      application is for at 256. `markSvg` draws it for every surface -- the
      rail badge, the tab icon, the reveal and the desktop icon
      (tools/make_icons.py renders it from this file) -- so they cannot
      drift apart.

   2. Hiding. "Jarvis" is written into a few hundred strings across thirty
      modules. Threading a flag through every one would be thirty changes
      that each go stale the next time somebody writes a sentence. Instead,
      while the name is hidden the page is read as it is drawn: every text
      node and tooltip that says Jarvis is rewritten as it arrives (one
      MutationObserver), and the original is kept so it can be put back.
      While the name is shown -- the default -- none of that runs at all,
      so the normal case costs nothing.

   3. The reveal. Switching the name back on is the moment the switch
      exists for, so it plays: the dormant badge powers up, the spike fires,
      the name decodes, every "the workbench" on the page turns back into
      Jarvis in a wave, and the mark flies home to the rail. About two and
      a half seconds; a click or a key skips it; reduced motion gets the end
      state at once.

   The choice is per machine, like the theme: localStorage so the first
   paint is already right (index.html reads it before anything draws), and
   a map keyed by hostname in the shared preferences so start.py can keep
   the name out of the terminal too.
   ========================================================================== */
(function () {
  'use strict';
  if (typeof document === 'undefined') return;

  const B = (typeof BARRY !== 'undefined') ? BARRY : null;
  const KEY = 'barry.jarvis';          // 'off' while hidden; anything else is shown
  const NAME = 'Jarvis';
  const STAND_IN = 'Workbench';        // what the brand says while hidden
  const ATTRS = ['title', 'placeholder', 'aria-label', 'alt'];
  const SKIP = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'NOSCRIPT']);
  const ROOT = document.documentElement;

  const state = { shown: true, stage: null };

  /* ------------------------------------------------------------------------
     Colour, read off the theme
     ------------------------------------------------------------------------ */
  function rgb(c) {
    c = String(c || '').trim();
    let m = /^#([0-9a-f]{3})$/i.exec(c);
    if (m) return m[1].split('').map((h) => parseInt(h + h, 16));
    m = /^#([0-9a-f]{6})/i.exec(c);
    if (m) return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16));
    m = /rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/i.exec(c);
    if (m) return [+m[1], +m[2], +m[3]];
    return null;
  }
  function hex(v) {
    return '#' + v.map((n) => Math.max(0, Math.min(255, Math.round(n)))
      .toString(16).padStart(2, '0')).join('');
  }
  function lum(c) {
    const v = rgb(c);
    if (!v) return 0.5;
    const l = v.map((n) => {
      n /= 255;
      return n <= 0.03928 ? n / 12.92 : Math.pow((n + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2];
  }
  function mix(a, b, t) {
    const x = rgb(a), y = rgb(b);
    if (!x || !y) return a;
    return hex(x.map((n, i) => n + (y[i] - n) * t));
  }
  function token(name, fallback) {
    if (B && B.token) return B.token(name, fallback);
    const v = getComputedStyle(ROOT).getPropertyValue(name).trim();
    return v || fallback;
  }

  /* The badge is a dark ground with a bright stroke in every theme, because
     the glow is the point and a dark glow is a shadow. Of the theme's
     accent pair, whichever is darker is the ground: on UVM Dark that is
     gold on deep green, on UVM Light white on green, on Phosphor green on
     black. */
  function colours() {
    const a = token('--accent', '#FFB81C');
    const on = token('--on-accent', '#14231b');
    const light = lum(a) >= lum(on);
    const ink = light ? a : on;
    return {
      ground: light ? on : a,
      ink: ink,
      spark: mix(ink, '#ffffff', 0.62),
      dim: token('--bg-3', '#15291f'),
      line: token('--text-3', '#6f8c7d'),
    };
  }
  /* The desktop icon's colours: UVM green and gold, whatever theme the
     person who regenerates it happens to be using. */
  const UVM = { ground: '#154734', ink: '#FFB81C', spark: '#fff1c9',
                dim: '#15291f', line: '#6f8c7d' };

  /* ------------------------------------------------------------------------
     The mark
     ------------------------------------------------------------------------ */
  const R2 = (n) => Math.round(n * 100) / 100;
  const CX = 16, CY = 17.6, RING = 9.4;
  function at(r, deg) {
    const t = deg * Math.PI / 180;
    return R2(CX + r * Math.cos(t)) + ' ' + R2(CY + r * Math.sin(t));
  }
  // Broken at the top, 66 degrees of it, which is where the spike goes.
  const RING_D = 'M' + at(RING, -57) + ' A' + RING + ' ' + RING + ' 0 1 1 '
               + at(RING, 237);
  // Rest, a small dip, one sharp spike up through the gap, its after-wave,
  // rest. The same waveform the boot scope draws.
  const TRACE_D = 'M9.2 19.4 H12.9 L13.9 20.9 L16 3.6 L18.3 22.2 L19.8 17.5'
                + ' L21.1 19.4 H22.8';
  const FLAT_D = 'M9.2 19.4 H22.8';
  const PEAK = [16, 3.6];
  // The instrument's dial, for sizes with room for it: a tick every 15
  // degrees, a longer one every 90, none across the gap.
  const TICKS_D = (function () {
    let d = '';
    for (let i = 0; i < 24; i++) {
      const a = i * 15;
      if (a > 240 && a < 300) continue;
      d += 'M' + at(12.2, a) + ' L' + at(i % 6 === 0 ? 13.8 : 13.0, a) + ' ';
    }
    return d.trim();
  })();

  let uid = 0;

  /* One badge, as SVG text.

     `detail` is the size it will be seen at, because a mark drawn for 256 px
     turns to mud at 16:
       'full'  the dial, a wide glow       -- the reveal, the desktop icon
       'mid'   a tight glow                -- the rail
       'tiny'  heavier strokes, no glow    -- the tab
     `opts.dormant` is the badge with the name hidden: a flat line on a
     plain tile, nothing firing. `opts.stage` is both at once for the reveal
     to power up: the plain tile between the live ground and the strokes,
     the flatline on top. `opts.file` is the static .svg, which carries its
     own small-size rules so a 16 px tab gets the tiny cut. */
  function markSvg(c, detail, opts) {
    opts = opts || {};
    c = c || colours();
    const id = 'jm' + (++uid);
    const full = detail === 'full', tiny = detail === 'tiny';
    const head = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"'
      + (opts.cls ? ' class="' + opts.cls + '"' : '') + '>';
    const line = (d, w, cls, extra) => '<path class="' + cls + '" d="' + d
      + '" fill="none" stroke="' + c.ink + '" stroke-width="' + w
      + '" stroke-linecap="round" stroke-linejoin="round"' + (extra || '') + '/>';
    const tile = '<rect width="32" height="32" rx="8" fill="'
        + c.dim + '" stroke="none"/>'
      + '<rect x=".5" y=".5" width="31" height="31" rx="7.5" fill="none" stroke="'
        + c.line + '" stroke-opacity=".3" stroke-width="1"/>';
    const flat = '<path class="jm-flat" d="' + FLAT_D + '" fill="none" stroke="'
      + c.line + '" stroke-width="2.2" stroke-linecap="round"/>';
    if (opts.dormant) return head + tile + flat + '</svg>';

    const style = opts.file
      ? '<style>@media (max-width: 40px) { .jm-ticks, .jm-glow { display: none } '
        + '.jm-ring { stroke-width: 2.7px } .jm-trace { stroke-width: 2.8px } '
        + '.jm-spark { r: 1.5px } } '
        + 'svg.small .jm-ticks, svg.small .jm-glow { display: none } '
        + 'svg.small .jm-ring { stroke-width: 2.7px } '
        + 'svg.small .jm-trace { stroke-width: 2.8px } '
        + 'svg.small .jm-spark { r: 1.5px }</style>'
      : '';
    const len = ' pathLength="100"';
    return head + style
      + '<defs>'
      + '<radialGradient id="' + id + 'v" cx="16" cy="13" r="22" gradientUnits="userSpaceOnUse">'
      + '<stop offset=".35" stop-color="#000" stop-opacity="0"/>'
      + '<stop offset="1" stop-color="#000" stop-opacity=".42"/></radialGradient>'
      + '<linearGradient id="' + id + 's" x1="0" y1="0" x2="0" y2="1">'
      + '<stop offset="0" stop-color="#fff" stop-opacity=".14"/>'
      + '<stop offset=".38" stop-color="#fff" stop-opacity="0"/></linearGradient>'
      + '<radialGradient id="' + id + 'c" cx="' + CX + '" cy="' + CY + '" r="10.5" gradientUnits="userSpaceOnUse">'
      + '<stop offset="0" stop-color="' + c.ink + '" stop-opacity=".32"/>'
      + '<stop offset="1" stop-color="' + c.ink + '" stop-opacity="0"/></radialGradient>'
      + (tiny ? '' : '<filter id="' + id + 'g" x="-40%" y="-40%" width="180%" height="180%">'
         + '<feGaussianBlur stdDeviation="' + (full ? 1.15 : 0.6) + '"/></filter>')
      + '</defs>'
      + '<rect width="32" height="32" rx="8" fill="' + c.ground + '" stroke="none"/>'
      + '<rect width="32" height="32" rx="8" fill="url(#' + id + 'v)" stroke="none"/>'
      + '<rect width="32" height="32" rx="8" fill="url(#' + id + 's)" stroke="none"/>'
      // For the reveal: the plain tile over the live ground and under the
      // strokes, so the ring can be seen drawing while the tile warms up.
      + (opts.stage ? '<g class="jm-dormant">' + tile + '</g>' : '')
      + '<circle class="jm-core" cx="' + CX + '" cy="' + CY + '" r="10.5" fill="url(#' + id + 'c)" stroke="none"/>'
      + (full ? line(TICKS_D, 0.55, 'jm-ticks', ' stroke-opacity=".5"') : '')
      + (tiny ? '' : '<g class="jm-glow" filter="url(#' + id + 'g)" opacity="' + (full ? 0.9 : 0.55) + '">'
         + line(RING_D, 2.4, 'jm-ring', len) + line(TRACE_D, 2.5, 'jm-trace', len) + '</g>')
      + line(RING_D, tiny ? 2.7 : 2.3, 'jm-ring', len)
      + line(TRACE_D, tiny ? 2.8 : 2.4, 'jm-trace', len)
      + '<circle class="jm-spark" cx="' + PEAK[0] + '" cy="' + PEAK[1] + '" r="'
        + (tiny ? 1.5 : 1.3) + '" fill="' + c.spark + '" stroke="none"/>'
      // And the flatline it fires out of, on top until the spike draws.
      + (opts.stage ? flat : '')
      + '</svg>';
  }

  /* ------------------------------------------------------------------------
     The words
     ------------------------------------------------------------------------ */
  const DETERMINER = /^(?:this|that|a|an|the|every|any|each|another|your|our|my|older|newer|same|running)$/i;

  /* What a sentence says with the name taken out.

     "Restart Jarvis" -> "Restart the workbench", "This Jarvis is running
     older code" -> "This workbench is running older code", "Jarvis's
     eegfilt" -> "The workbench's eegfilt", and the name on its own -- a
     label, the tab title, "Jarvis 2026.10.12.1" -- becomes the stand-in.
     Only the capitalised name: a lower-case `jarvis` is a file or a key
     (jarvis.ico, scope 'jarvis') and is left exactly alone. */
  function neutral(s) {
    if (typeof s !== 'string'
        || (s.indexOf(NAME) < 0 && s.indexOf('JARVIS') < 0)) return s;
    s = s.replace(/JARVIS/g, STAND_IN.toUpperCase());
    if (s.trim() === NAME) return s.replace(NAME, STAND_IN);
    return s.replace(/Jarvis(['’]s)?\b/g, (m, poss, i, all) => {
      const before = all.slice(0, i);
      const after = all.slice(i + m.length);
      poss = poss || '';
      // The name as a label at the head of a line: "Jarvis 2026.10.12.1",
      // "Jarvis — error: ...".
      if (!poss && /^\s*$/.test(before)
          && /^(?:\s+\d|\s+[—–-]\s|:\s)/.test(after)) return STAND_IN;
      // After a determiner, which already supplies the article.
      const prev = /([A-Za-z]+)\s+$/.exec(before);
      if (prev && DETERMINER.test(prev[1])) return 'workbench' + poss;
      const opens = /(?:^|[.!?…]["”’)]?\s+|\n\s*)["“‘(]?$/.test(before);
      return (opens ? 'The workbench' : 'the workbench') + poss;
    });
  }

  /* ------------------------------------------------------------------------
     Hiding: rewrite what says Jarvis, and remember what it said
     ------------------------------------------------------------------------ */
  const texts = new Map();   // Text -> [original, shown]
  const attrs = new Map();   // Element -> { attribute: [original, shown] }
  const ATTR_SEL = ATTRS.map((a) => '[' + a + '*="' + NAME + '"],[' + a + '*="JARVIS"]').join(',');
  const says = (s) => !!s && (s.indexOf(NAME) >= 0 || s.indexOf('JARVIS') >= 0);

  function kept(node) {
    const p = node.parentNode;
    if (!p || p.nodeType !== 1) return false;
    if (SKIP.has(p.nodeName)) return true;
    if (p.isContentEditable) return true;
    return !!(p.closest && p.closest('[data-jarvis-keep]'));
  }
  function fixText(node) {
    const d = node.data;
    if (!says(d) || kept(node)) return;
    const out = neutral(d);
    if (out === d) return;
    texts.set(node, [d, out]);
    node.data = out;
  }
  function fixAttr(elm, name) {
    const v = elm.getAttribute && elm.getAttribute(name);
    if (!says(v) || (elm.closest && elm.closest('[data-jarvis-keep]'))) return;
    const out = neutral(v);
    if (out === v) return;
    let rec = attrs.get(elm);
    if (!rec) attrs.set(elm, rec = {});
    rec[name] = [v, out];
    elm.setAttribute(name, out);
  }
  function sweep(node) {
    if (!node) return;
    if (node.nodeType === 3) { fixText(node); return; }
    if (node.nodeType !== 1 && node.nodeType !== 11) return;
    // Most insertions have nothing to do with the name, and asking the
    // engine for the subtree's text is one native call.
    if (says(node.textContent)) {
      const w = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
      const found = [];
      let n;
      while ((n = w.nextNode())) if (says(n.data)) found.push(n);
      found.forEach(fixText);
    }
    if (node.nodeType === 1) ATTRS.forEach((a) => fixAttr(node, a));
    if (node.querySelectorAll) {
      node.querySelectorAll(ATTR_SEL).forEach((e) => ATTRS.forEach((a) => fixAttr(e, a)));
    }
  }

  let watcher = null;
  function watch() {
    if (watcher || typeof MutationObserver === 'undefined') return;
    // A microtask after each change, which is before the next paint: the
    // name is never on screen for a frame.
    watcher = new MutationObserver((recs) => {
      for (const r of recs) {
        if (r.type === 'childList') r.addedNodes.forEach(sweep);
        else if (r.type === 'characterData') fixText(r.target);
        else if (r.type === 'attributes') fixAttr(r.target, r.attributeName);
      }
    });
    watcher.observe(ROOT, { subtree: true, childList: true, characterData: true,
                            attributes: true, attributeFilter: ATTRS });
  }
  function unwatch() {
    if (watcher) { watcher.disconnect(); watcher = null; }
  }

  /* Put back everything that was rewritten, provided nobody has rewritten
     it since -- whatever it says now is newer than what was taken out.
     Detached nodes are restored too: a panel built while the name was
     hidden and attached again later must not come back saying "the
     workbench". Returns the restored nodes that are on the page, for the
     reveal to animate. */
  function restoreAll() {
    const live = [];
    texts.forEach((pair, node) => {
      if (node.data !== pair[1]) return;
      node.data = pair[0];
      if (node.isConnected) live.push(node);
    });
    texts.clear();
    attrs.forEach((rec, elm) => {
      for (const name of Object.keys(rec)) {
        if (elm.getAttribute(name) === rec[name][1]) elm.setAttribute(name, rec[name][0]);
      }
    });
    attrs.clear();
    return live;
  }

  /* alert / confirm / prompt draw outside the page, where no observer can
     see them. Wrapped while hidden; the wrapper wraps whatever is there at
     that moment, so a harness's stub survives being hidden and shown. */
  let dialogs = null;
  function wrapDialogs(on) {
    if (on && !dialogs) {
      dialogs = { alert: window.alert, confirm: window.confirm, prompt: window.prompt };
      const wrap = (fn) => function (msg) {
        const args = Array.prototype.slice.call(arguments);
        if (typeof msg === 'string') args[0] = neutral(msg);
        return fn.apply(window, args);
      };
      window.alert = wrap(dialogs.alert);
      window.confirm = wrap(dialogs.confirm);
      window.prompt = wrap(dialogs.prompt);
      dialogs.mine = { alert: window.alert, confirm: window.confirm, prompt: window.prompt };
    } else if (!on && dialogs) {
      for (const k of ['alert', 'confirm', 'prompt']) {
        if (window[k] === dialogs.mine[k]) window[k] = dialogs[k];
      }
      dialogs = null;
    }
  }

  /* ------------------------------------------------------------------------
     Painting the two badges that are always on screen
     ------------------------------------------------------------------------ */
  function faviconSvg(c) {
    return state.shown ? markSvg(c, 'tiny') : markSvg(c, 'tiny', { dormant: true });
  }
  function paint() {
    const c = colours();
    document.querySelectorAll('.brand-mark').forEach((host) => {
      host.innerHTML = state.shown ? markSvg(c, 'mid') : markSvg(c, 'mid', { dormant: true });
    });
    // Only a page that already wears the mark: a standalone page with an
    // icon of its own keeps it.
    let link = document.querySelector('link[rel="icon"]');
    if (!link) {
      if (!B) return;
      link = document.createElement('link');
      link.rel = 'icon';
      document.head.appendChild(link);
    }
    link.type = 'image/svg+xml';
    link.href = 'data:image/svg+xml,' + encodeURIComponent(faviconSvg(c));
  }

  function controls() {
    const chip = document.getElementById('jarvisActivate');
    if (chip) chip.classList.toggle('hidden', state.shown);
    // The badge in the rail says who Jarvis is, while there is a name to
    // say it about.
    document.querySelectorAll('#rail .brand-mark').forEach((m) => {
      if (state.shown) {
        m.setAttribute('role', 'button');
        m.setAttribute('tabindex', '0');
        m.setAttribute('title', 'Who is ' + NAME + '?');
        m.removeAttribute('aria-hidden');
      } else {
        m.removeAttribute('role');
        m.removeAttribute('tabindex');
        m.removeAttribute('title');
        m.setAttribute('aria-hidden', 'true');
      }
    });
  }

  function hide() {
    finishStage();
    if (waveStop) { try { waveStop(); } catch (e) { /* done */ } waveStop = null; }
    state.shown = false;
    ROOT.dataset.jarvis = 'off';
    wrapDialogs(true);
    sweep(ROOT);
    watch();
    paint();
    controls();
  }
  function show() {
    state.shown = true;
    delete ROOT.dataset.jarvis;
    unwatch();
    wrapDialogs(false);
    const live = restoreAll();
    paint();
    controls();
    return live;
  }

  /* ------------------------------------------------------------------------
     The reveal
     ------------------------------------------------------------------------ */
  // The script's half of the timings; app.css has the other half. Both are
  // multiplied by `--jv-pace` (1 unless somebody sets it), read once per
  // reveal. The build takes about five seconds and then HOLDS: the name
  // stays up, with the four ways on, until somebody picks one.
  const T = { charge: 450, fire: 2600, word: 3000, name: 3150, greet: 4400, choose: 5000 };
  function pace() {
    const v = parseFloat(getComputedStyle(ROOT).getPropertyValue('--jv-pace'));
    return v > 0 ? v : 1;
  }
  const GLYPHS_UP = 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789';
  const GLYPHS_LO = 'abcdefghjkmnpqrstuvwxyz0123456789';
  const scramble = (ch) => {
    const set = ch === ch.toLowerCase() ? GLYPHS_LO : GLYPHS_UP;
    return set[(Math.random() * set.length) | 0];
  };
  // The sounds (js/jarvisfx.js). Never able to throw into the reveal.
  const sfx = (name, arg) => {
    try {
      const f = (B && B.jarvisfx) || window.JarvisFX;
      if (f && f[name]) f[name](arg);
    } catch (e) { /* silence */ }
  };
  const shows = () => (B && B.jarvisshow) || window.JarvisShow || null;

  function canAnimate() {
    try {
      if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
    } catch (e) { /* no matchMedia: animate */ }
    const body = document.body;
    if (!body || body.classList.contains('solo-window') || body.classList.contains('aid-window')) return false;
    return !!document.querySelector('#rail');
  }

  function node(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text) n.textContent = text;
    return n;
  }

  function greeting() {
    const h = new Date().getHours();
    if (h < 5) return 'Still up?';
    if (h < 12) return 'Good morning.';
    if (h < 18) return 'Good afternoon.';
    return 'Good evening.';
  }

  /* Every name on screen decodes in place: the letters cycle through noise
     and lock in from the left, in a wave that leaves `origin` first. Only
     `replaceData` on the six letters, so the node is the same node
     throughout and nothing holding it notices. */
  const HL = typeof Highlight !== 'undefined' && window.CSS && CSS.highlights;
  function decodeWave(nodes, origin, k) {
    const vw = window.innerWidth, vh = window.innerHeight;
    const items = [];
    for (const n of nodes.slice(0, 400)) {
      const spots = [];
      const re = /Jarvis|JARVIS/g;
      let m;
      while ((m = re.exec(n.data))) spots.push(m.index);
      if (!spots.length) continue;
      let r = null;
      try {
        const rg = document.createRange();
        rg.selectNodeContents(n);
        r = rg.getBoundingClientRect();
      } catch (e) { /* not measurable: not animated */ }
      if (!r || !r.width || r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) continue;
      const dx = r.left + r.width / 2 - origin.x, dy = r.top + r.height / 2 - origin.y;
      items.push({ n, spots, word: spots.map((s) => n.data.slice(s, s + 6)),
                   delay: k * Math.min(620, Math.sqrt(dx * dx + dy * dy) / 2.4) });
    }
    if (!items.length) return null;
    const DUR = 460 * k, GLOW = 700 * k;
    const t0 = performance.now();
    let raf = 0, stopped = false;
    const ranges = (pick) => {
      if (!HL) return;
      const hl = new Highlight();
      for (const it of items) {
        if (!pick(it)) continue;
        for (const s of it.spots) {
          try {
            const rg = document.createRange();
            rg.setStart(it.n, s); rg.setEnd(it.n, s + 6);
            hl.add(rg);
          } catch (e) { /* the node changed under us */ }
        }
      }
      return hl;
    };
    const put = (it, lock) => {
      it.spots.forEach((s, i) => {
        const w = it.word[i];
        let out = w.slice(0, lock);
        for (let j = lock; j < 6; j++) out += scramble(w[j]);
        try { if (it.n.data.slice(s, s + 6) !== out) it.n.replaceData(s, 6, out); } catch (e) { /* gone */ }
      });
    };
    // Everything starts as noise, so the wave is noise resolving rather
    // than the name appearing and then being scrambled.
    items.forEach((it) => put(it, 0));
    function frame(now) {
      if (stopped) return;
      let busy = false;
      for (const it of items) {
        if (it.done) continue;
        const p = (now - t0 - it.delay) / DUR;
        if (p >= 1) { put(it, 6); it.done = true; it.at = now; continue; }
        busy = true;
        put(it, Math.max(0, Math.floor(p * 6)));
      }
      if (HL) {
        CSS.highlights.set('jarvis-reveal', ranges((it) => !it.done));
        CSS.highlights.set('jarvis-glow', ranges((it) => it.done && now - it.at < GLOW));
      }
      const glowing = items.some((it) => it.done && now - it.at < GLOW);
      if (busy || glowing) raf = requestAnimationFrame(frame);
      else stop();
    }
    function stop() {
      if (stopped) return;
      stopped = true;
      cancelAnimationFrame(raf);
      items.forEach((it) => put(it, 6));
      if (HL) { CSS.highlights.delete('jarvis-reveal'); CSS.highlights.delete('jarvis-glow'); }
    }
    raf = requestAnimationFrame(frame);
    // A timer as well as the frames: a background tab or a virtual clock
    // stops frames, and the names must not be left as noise.
    setTimeout(stop, 700 * k + DUR + GLOW + 400);
    return stop;
  }
  // The names on the page, outside the reveal's own overlays.
  function namesOnPage() {
    const out = [];
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      if (!/Jarvis|JARVIS/.test(n.data)) continue;
      const p = n.parentNode;
      if (!p || (p.closest && p.closest('#jarvisReveal, #jarvisShow, #jarvisAbout, script, style'))) continue;
      out.push(n);
    }
    return out;
  }
  let waveStop = null;

  function decodeWord(letters, k) {
    const word = NAME.toUpperCase();
    const t0 = performance.now();
    const STEP = 150 * k, SPIN = 420 * k;
    const id = setInterval(() => {
      const t = performance.now() - t0;
      let all = true;
      letters.forEach((sp, i) => {
        const lockAt = SPIN + i * STEP;
        if (t >= lockAt) {
          if (sp.textContent !== word[i] || !sp.classList.contains('lit')) {
            sp.textContent = word[i];
            sp.classList.add('lit');
            sfx('tick', i);
          }
        } else {
          all = false;
          sp.textContent = scramble(word[i]);
        }
      });
      if (all) clearInterval(id);
    }, 45);
    return () => {
      clearInterval(id);
      letters.forEach((sp, i) => { sp.textContent = word[i]; sp.classList.add('lit'); });
    };
  }

  /* The four ways on, once the name is up. The icons are drawn in the rail's
     own line style. */
  const CHOICES = [
    { k: 'home', title: 'Go to home page', line: 'The workbench, ready to use',
      icon: '<path d="M4 11.5 12 4.5l8 7"/><path d="M6.5 10v9.5h11V10"/><path d="M10 19.5v-5h4v5"/>' },
    { k: 'ds', title: 'Analyze Dentate Spikes', line: 'Catch them live, depth by depth',
      icon: '<path d="M2 15.5h5l1.2 1.6L10.6 3.5l2.5 14 1.6-3.6 1.5 1.6H22"/>' },
    { k: 'mono', title: 'Open Monolith', line: 'How twelve brain regions talk',
      icon: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="3.5" r="1.7"/>'
          + '<circle cx="19.4" cy="16.3" r="1.7"/><circle cx="4.6" cy="16.3" r="1.7"/>'
          + '<path d="M12 5.2q1.5 7.5 6 9.7M6 15.5q5.5-1.5 6-10.3"/>' },
    { k: 'ied', title: 'Detect IEDs', line: 'Find the sharp spikes of epilepsy',
      icon: '<path d="M2 13h4l1.8-3 2.2 9 3-15.5 2.2 11.5 1.8-4H22"/>' },
  ];

  function playReveal() {
    finishStage();
    const c = colours();
    const k = pace();
    const railMark = document.querySelector('#rail .brand-mark');
    const box = node('div', 'jv-reveal');
    box.id = 'jarvisReveal';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-label', NAME);
    // Its own lettering is the name, on purpose, even mid-hide.
    box.setAttribute('data-jarvis-keep', '');
    const scrim = node('div', 'jv-scrim');
    const corner = node('div', 'jv-corner');
    const S = shows();
    if (S && S.soundButton) { try { corner.append(S.soundButton('jv-snd')); } catch (e) { /* none */ } }
    const stageEl = node('div', 'jv-stage');
    const big = node('div', 'jv-big');
    big.innerHTML = markSvg(c, 'full', { stage: true });
    const word = node('div', 'jv-word');
    const letters = NAME.toUpperCase().split('').map((ch) => {
      const sp = node('span', null, ch);
      word.appendChild(sp);
      return sp;
    });
    const sub = node('div', 'jv-sub', greeting());
    const who = node('button', 'jv-who', 'Who is ' + NAME + '?');
    who.type = 'button';
    who.addEventListener('click', () => { const s2 = shows(); if (s2) s2.about(); });
    const choices = node('div', 'jv-choices');
    CHOICES.forEach((ch, i) => {
      const b = node('button', 'jv-go');
      b.type = 'button';
      b.dataset.k = ch.k;
      b.style.setProperty('--i', String(i));
      const ic = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      ic.setAttribute('viewBox', '0 0 24 24');
      ic.setAttribute('aria-hidden', 'true');
      ic.innerHTML = ch.icon;
      b.append(ic, node('strong', null, ch.title), node('span', null, ch.line));
      b.addEventListener('click', () => choose(ch.k));
      b.addEventListener('pointerenter', () => { if (st.held) sfx('hover'); });
      choices.append(b);
    });
    stageEl.append(node('div', 'jv-burst'), node('div', 'jv-wave'), node('div', 'jv-wave two'),
                   big, word, sub, who, choices);
    box.append(scrim, corner, stageEl);
    document.body.appendChild(box);
    if (railMark) railMark.classList.add('jv-await');

    const st = { box, big, railMark, letters, k, timers: [], stops: [], shown: false,
                 held: false, leaving: false };
    state.stage = st;
    const later = (ms, fn) => st.timers.push(setTimeout(() => {
      try { fn(); } catch (e) { finishStage(); }
    }, ms * k));

    sfx('unlock');
    // Next frame, so the starting state has been painted and the
    // animations have something to animate from.
    requestAnimationFrame(() => box.classList.add('go'));
    later(30, () => box.classList.add('go'));
    later(T.charge, () => sfx('charge', (T.fire - T.charge) * k / 1000));
    later(T.fire, () => sfx('fire'));
    later(T.word, () => {
      sfx('chatter', (420 + 5 * 150) * k / 1000);
      st.stops.push(decodeWord(letters, k));
    });
    later(T.name, () => {
      st.shown = true;
      show();
      if (railMark) railMark.classList.add('jv-await');
    });
    later(T.greet, () => sfx('chord'));
    later(T.choose, () => hold());

    // Anything pressed while it builds skips to the choices -- never past
    // them, so nobody leaves the moment by accident. On the next tick, so
    // the click that started this is not also the click that skips it.
    st.skip = (e) => {
      if (st.held) return;
      if (e && e.type === 'keydown' && ['Shift', 'Control', 'Alt', 'Meta'].indexOf(e.key) >= 0) return;
      if (e && e.target && e.target.closest && e.target.closest('.jv-corner')) return;
      if (e) { e.preventDefault(); e.stopPropagation(); }
      toHold(true);
    };
    later(0, () => {
      window.addEventListener('pointerdown', st.skip, true);
      window.addEventListener('keydown', st.skip, true);
    });
  }

  /* Holding: the name up, the four ways on, and nothing more happening
     until somebody chooses. 1-4 choose from the keyboard; Escape is home. */
  function hold() {
    const st = state.stage;
    if (!st || st.held) return;
    st.held = true;
    window.removeEventListener('pointerdown', st.skip, true);
    window.removeEventListener('keydown', st.skip, true);
    st.box.classList.add('hold');
    st.keys = (e) => {
      const S = shows();
      if (!state.stage || st.leaving) return;
      if (document.getElementById('jarvisAbout') || document.getElementById('jarvisLight')) return;
      if (S && S.isOpen && S.isOpen()) return;
      const i = '1234'.indexOf(e.key);
      if (i >= 0) { e.preventDefault(); choose(CHOICES[i].k); }
      else if (e.key === 'Escape') { e.preventDefault(); goHome(); }
    };
    document.addEventListener('keydown', st.keys, true);
    const first = st.box.querySelector('.jv-go');
    try { if (first) first.focus({ preventScroll: true }); } catch (e) { /* fine */ }
  }

  // The build cut short: everything to its final state at once.
  function toHold(skipped) {
    const st = state.stage;
    if (!st || st.held) return;
    st.timers.forEach(clearTimeout);
    st.timers = [];
    st.box.classList.add('go', 'done');
    if (!st.shown) { st.shown = true; show(); }
    if (st.railMark) st.railMark.classList.add('jv-await');
    st.stops.forEach((f) => { try { f(); } catch (e) { /* decoration */ } });
    st.stops = [];
    st.letters.forEach((sp, i) => { sp.textContent = NAME.toUpperCase()[i]; sp.classList.add('lit'); });
    if (skipped) { sfx('hush'); sfx('chord'); }
    hold();
  }

  function choose(key) {
    const st = state.stage;
    if (!st || st.leaving) return;
    if (!st.held) toHold(true);
    sfx('select');
    if (key === 'home') { goHome(); return; }
    const S = shows();
    if (!S) { goHome(); return; }
    st.box.classList.add('away');
    try {
      S.open(key, {
        back: () => {
          if (state.stage !== st) return;
          st.box.classList.remove('away');
          const b = st.box.querySelector('.jv-go[data-k="' + key + '"]');
          try { if (b) b.focus({ preventScroll: true }); } catch (e) { /* fine */ }
        },
        home: () => goHome(),
      });
    } catch (e) {
      st.box.classList.remove('away');
    }
  }

  /* Home: the mark flies to the rail, the overlay lifts on the home page,
     and the names on it decode in a wave out of the badge. */
  function goHome() {
    const st = state.stage;
    if (!st || st.leaving) return;
    st.leaving = true;
    if (!st.held) toHold(false);
    const S = shows();
    try { if (S && S.isOpen && S.isOpen()) S.close(); } catch (e) { /* gone */ }
    st.box.classList.remove('away');
    try {
      if (typeof setView === 'function' && B && B.state && B.state.view !== 'pipeline') setView('pipeline');
    } catch (e) { /* stay where it is */ }
    sfx('whoosh', 0.75 * st.k);
    const to = st.railMark && st.railMark.getBoundingClientRect();
    const from = st.big.getBoundingClientRect();
    st.box.classList.add('fly');
    if (to && to.width && from.width) {
      const dx = (to.left + to.width / 2) - (from.left + from.width / 2);
      const dy = (to.top + to.height / 2) - (from.top + from.height / 2);
      st.big.style.transform = 'translate(' + dx + 'px,' + dy + 'px) scale('
        + (to.width / from.width) + ')';
    } else {
      st.big.style.opacity = '0';
    }
    st.timers.push(setTimeout(() => {
      sfx('land');
      finishStage(true);
      const m = document.querySelector('#rail .brand-mark');
      const r = m && m.getBoundingClientRect();
      if (waveStop) { try { waveStop(); } catch (e) { /* done */ } }
      waveStop = decodeWave(namesOnPage(),
                            r && r.width ? { x: r.left + r.width / 2, y: r.top + r.height / 2 }
                                         : { x: 0, y: 0 }, 1);
    }, 640 * st.k));
  }

  /* The end of the reveal, however it ends: home, cut short by hiding the
     name again, or a new one starting. Every path lands in the same place --
     name shown, overlays gone, rail badge back -- and timers rather than
     `animationend` decide it, because animations stall in a background tab
     and under the harness runner's virtual clock. */
  function finishStage(landed) {
    const st = state.stage;
    if (!st) return;
    state.stage = null;
    st.timers.forEach(clearTimeout);
    window.removeEventListener('pointerdown', st.skip, true);
    window.removeEventListener('keydown', st.skip, true);
    if (st.keys) document.removeEventListener('keydown', st.keys, true);
    const S = shows();
    try { if (S && S.isOpen && S.isOpen()) S.close(); } catch (e) { /* gone */ }
    if (!st.shown) show();
    st.stops.forEach((f) => { try { f(); } catch (e) { /* decoration */ } });
    if (st.box.parentNode) st.box.parentNode.removeChild(st.box);
    const mark = document.querySelector('#rail .brand-mark');
    if (mark) {
      mark.classList.remove('jv-await');
      if (landed) {
        mark.classList.add('jv-landed');
        setTimeout(() => mark.classList.remove('jv-landed'), 900);
      }
    }
  }

  /* The whole thing again, for a rehearsal or for somebody who missed it:
     hidden without remembering it, then revealed. */
  function replay() {
    if (state.stage || !canAnimate()) return false;
    if (state.shown) hide();
    playReveal();
    return true;
  }

  /* ------------------------------------------------------------------------
     The switch
     ------------------------------------------------------------------------ */
  function hostname() {
    return B && B.state && B.state.catalog && B.state.catalog.system
      ? B.state.catalog.system.hostname : null;
  }
  function remember(on) {
    try { localStorage.setItem(KEY, on ? 'on' : 'off'); } catch (e) { /* private window */ }
    const host = hostname();
    if (host && B && B.prefs) {
      // Keyed by hostname, merged per key (PREFS_SPEC in store.py): the rig
      // hiding the name must not hide it on the laptop.
      const all = Object.assign({}, B.prefs.get('jarvis', {}) || {});
      all[host] = on;
      B.prefs.set('jarvis', all);
    }
  }
  function forThisMachine() {
    const host = hostname();
    const byHost = (B && B.prefs && B.prefs.get('jarvis', {})) || {};
    if (host && Object.prototype.hasOwnProperty.call(byHost, host)) return byHost[host] !== false;
    try { return localStorage.getItem(KEY) !== 'off'; } catch (e) { return true; }
  }

  /* `reveal` only from a person's own click: boot, the preferences
     reconcile and another window changing its mind all arrive here too, and
     a fanfare on any of those would be a fanfare every morning. */
  function set(on, opts) {
    opts = opts || {};
    on = !!on;
    if (opts.remember !== false) remember(on);
    if (on === state.shown && !state.stage) { paint(); controls(); return; }
    if (!on) { hide(); return; }
    if (state.stage) return;                       // already on its way
    if (opts.reveal && canAnimate()) playReveal();
    else show();
  }
  function toggle() {
    const on = !state.shown;
    set(on, { reveal: on });
    if (B && B.activity && B.activity.log) {
      try { B.activity.log('jarvis.name', { shown: on }); } catch (e) { /* not ready */ }
    }
  }

  /* The row in the theme picker. Says what it does without saying the
     name, because while the name is hidden the row is still on screen. */
  function pickerRow(close) {
    const b = node('button', 'theme-opt jv-opt' + (state.shown ? ' on' : ''));
    b.type = 'button';
    b.setAttribute('role', 'switch');
    b.setAttribute('aria-checked', String(state.shown));
    b.title = state.shown
      ? 'Take the name and logo off everything, until switched back on'
      : 'Bring the name and logo back, with the reveal';
    b.append(node('span', 'jv-pill'),
             node('span', null, state.shown ? 'Name and logo' : 'Name and logo hidden'));
    b.addEventListener('click', () => {
      if (close) close();
      toggle();
    });
    return b;
  }

  function wire() {
    const chip = document.getElementById('jarvisActivate');
    if (chip && !chip.dataset.wired) {
      chip.dataset.wired = '1';
      chip.addEventListener('click', () => { if (!state.shown) toggle(); });
    }
    const mark = document.querySelector('#rail .brand-mark');
    if (mark && !mark.dataset.wired) {
      mark.dataset.wired = '1';
      const go = () => { const S = shows(); if (S && state.shown && !state.stage) S.about(); };
      mark.addEventListener('click', go);
      mark.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); }
      });
    }
    controls();
  }

  function reconcile() {
    const mine = forThisMachine();
    if (mine !== state.shown) set(mine, { remember: false });
  }

  // Another window of this app changed it: follow, quietly.
  window.addEventListener('storage', (e) => {
    if (e.key !== KEY) return;
    const on = e.newValue !== 'off';
    if (on !== state.shown) set(on, { remember: false });
  });

  const api = {
    NAME, STAND_IN,
    shown: () => state.shown,
    set, toggle, reconcile, wire, paint, neutral, markSvg, colours,
    pickerRow, UVM,
    revealing: () => !!state.stage,
    holding: () => !!(state.stage && state.stage.held),
    skip: () => finishStage(),
    toHold: () => toHold(false),
    choose, home: () => goHome(), replay,
    about: () => { const S = shows(); if (S && state.shown) S.about(); },
  };
  if (B) B.jarvis = api; else window.JarvisName = api;

  // Before anything else draws: hidden on this machine means hidden from
  // the first frame the scripts control (index.html has already handled
  // the ones before that).
  let start = true;
  try { start = localStorage.getItem(KEY) !== 'off'; } catch (e) { /* default */ }
  if (!start) hide();
  else { delete ROOT.dataset.jarvis; paint(); }
})();
