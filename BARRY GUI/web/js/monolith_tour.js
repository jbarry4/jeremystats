/* ==========================================================================
   monolith_tour.js -- the Monolith's guided tour.

   For a lab member who knows the rats, regions and cues but not this
   analysis. It walks the page's top lead from the counts and the circuit,
   through the ghost (pooled -> rats -> a rat's days -> a day's cue pairs),
   down to that cue pair's recording and how each number was made.

   It runs on Jarvis's own tour engine (js/tour.js), so it looks and behaves
   like Jarvis's tours: the screen dims except for the real thing, and on a
   step that says "click", either you click it or Next clicks it for you.
   This page is not Jarvis, so the few globals the engine expects are given
   here when they are missing; inside Jarvis nothing is replaced.

   It starts by itself on a first visit (remembered in this browser), and
   the "Take the tour" button at the top starts it again.

   Every step sets up what it needs (`before`), so Back works and a reader
   who clicked something other than the suggestion is followed, not fought:
   if they opened another rat or day, the tour carries on with theirs.

   Load order: after monolith.js, BEFORE tour.js (the engine reads these
   globals as it loads).
   ========================================================================== */
'use strict';

/* ---- what tour.js expects of Jarvis ---------------------------------- */
(function (g) {
  if (typeof g.BARRY === 'undefined') g.BARRY = { activity: { log() {} }, state: { view: null } };
  if (!g.BARRY.activity) g.BARRY.activity = { log() {} };
  if (!g.BARRY.state) g.BARRY.state = { view: null };
  if (typeof g.$ === 'undefined') g.$ = (sel, root) => (root || document).querySelector(sel);
  if (typeof g.isTyping === 'undefined') {
    g.isTyping = (e) => {
      const t = e && e.target;
      return !!(t && typeof t.matches === 'function' && t.matches('input, textarea, select, [contenteditable]'));
    };
  }
  if (typeof g.setView === 'undefined') g.setView = () => {};
  if (typeof g.toast === 'undefined') g.toast = (msg) => { try { console.warn(msg); } catch (e) { /* none */ } };
  // The engine's menu is never opened here (the module has onFinish).
  if (typeof g.showModal === 'undefined') g.showModal = () => {};
  if (typeof g.closeModal === 'undefined') g.closeModal = () => {};
  if (typeof g.el === 'undefined') {
    const SVG = new Set(['svg', 'path', 'g', 'circle', 'line', 'rect', 'polygon', 'text']);
    g.el = (tag, attrs, kids) => {
      const svg = SVG.has(tag);
      const n = svg ? document.createElementNS('http://www.w3.org/2000/svg', tag) : document.createElement(tag);
      for (const k in (attrs || {})) {
        const v = attrs[k];
        if (v === null || v === undefined || v === false) continue;
        if (k === 'class') n.setAttribute('class', v);
        else if (k === 'text') n.textContent = v;
        else if (k === 'html') n.innerHTML = v;
        else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2).toLowerCase(), v);
        else n.setAttribute(k, v);
      }
      for (const c of [].concat(kids || [])) {
        if (c === null || c === undefined || c === false) continue;
        n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
      }
      return n;
    };
  }
})(window);

window.MONO_TOUR = (function () {
  const SEEN = 'barry.monolith.tour.seen';
  const M = () => window.MONO;
  const S = () => M().data.S;
  const q = (sel) => document.querySelector(sel);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function until(fn, ms) {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
      try { if (fn()) return true; } catch (e) { /* not yet */ }
      await sleep(60);
    }
    try { return !!fn(); } catch (e) { return false; }
  }
  const sig = (v) => (v == null || !isFinite(v) ? '—' : Math.abs(v) >= 1 ? v.toFixed(2) : Math.abs(v) >= 0.01 ? v.toFixed(3) : v.toPrecision(2));
  const signed = (v) => (v == null || !isFinite(v) ? '—' : (v >= 0 ? '+' : '−') + sig(Math.abs(v)));
  const pSay = (p) => (p == null || !isFinite(p) ? '—' : p < 0.001 ? p.toExponential(1) : p.toFixed(3).replace(/^0/, ''));
  const num = (n) => (n == null ? '—' : Number(n).toLocaleString());

  /* The lead the tour follows, and what the reader has opened on the way. */
  const T = { rat: null, day: 'Precon4', unit: null };
  function lead() { return (M().topOf ? M().topOf(M().state.layer) : ((S().top || {})[M().state.layer] || []))[0] || null; }
  function leadSay(t) {
    const s = S();
    const w = s.windows.find((x) => x.id === t.w) || {};
    const b = s.bands.find((x) => x.id === t.band) || {};
    const m = s.methods.find((x) => x.id === t.m) || {};
    return t.a + ' – ' + t.b + ', ' + (w.label || t.w) + ', ' + (b.named ? b.label : (b.hz || '') + ' Hz') + ', ' + (m.label || t.m);
  }

  /* ---- setting each step up -------------------------------------------- */
  // The page opens on what was kept; the rest of the tour is on the Monolith.
  function onTab(id) { if (M().state.tab !== id && M().showTab) M().showTab(id); }
  function closeAll() {
    onTab('main');
    if (M().leaf.open) M().closeLeaf();
    if (M().ghost.pair != null) M().closeGhost(true);
    if (window.MONO_HELP) window.MONO_HELP.close();
  }
  function onLead() {
    const t = lead();
    const st = M().state;
    if (t && !(st.sel === t.pair && st.win === t.w && st.band === t.band && st.method === t.m)) M().go(t);
  }
  /* The ghost of the lead, `depth` levels down: 1 the pooled edge, 2 its
     rats, 3 one rat's days, 4 one day's cue pairs. What the reader opened
     is kept when it is that deep; otherwise the tour's own choice. */
  async function ghostAt(depth) {
    onTab('main');
    if (M().leaf.open) M().closeLeaf();
    const t = lead();
    // A click the reader (or Next) just made may still be animating.
    await until(() => M().ghost.lifted && M().ghost.detail && M().ghost.stack.length >= depth, 1600);
    if (M().ghost.pair !== t.pair || !M().ghost.lifted) {
      onLead();
      await M().openGhost(t.pair);
    }
    await until(() => M().ghost.detail, 15000);
    const g = M().ghost;
    if (g.stack.length > depth) M().ghostTo(depth);
    if (depth >= 2 && M().ghost.stack.length < 2) M().push({ lv: 'rats' });
    if (depth >= 3) {
      const s3 = M().ghost.stack[2];
      if (s3 && s3.lv === 'days') T.rat = s3.rat;
      else { if (T.rat == null) T.rat = pickRat(); M().ghostTo(2); M().push({ lv: 'days', rat: T.rat }); }
    }
    if (depth >= 4) {
      const s4 = M().ghost.stack[3];
      if (s4 && s4.lv === 'units' && s4.rat === T.rat) T.day = s4.day;
      else { M().ghostTo(3); M().push({ lv: 'units', rat: T.rat, day: T.day }); }
    }
    await until(() => q('#ghostsvg path.garc'), 3000);
    // Let the lines finish growing into place, so the ring is drawn round
    // where they end up rather than where they started.
    await sleep(650);
  }
  /* A rat that went the pooled way, the most weighted of them. */
  function pickRat() {
    const d = M().ghost.detail || {};
    const est = (d.pooled || {}).est;
    const rats = (d.rats || []).filter((r) => r.delta != null);
    const same = rats.filter((r) => est == null || (r.delta >= 0) === (est >= 0));
    const pool = same.length ? same : rats;
    pool.sort((a, b) => (b.weight || 0) - (a.weight || 0));
    return pool.length ? pool[0].rat : null;
  }
  function ratOf(rat) { return ((M().ghost.detail || {}).rats || []).find((r) => r.rat === rat) || null; }
  function pickUnit() {
    const r = ratOf(T.rat);
    const day = r && (r.days || {})[T.day];
    const u = day && (day.units || []).find((x) => x.v != null);
    return u ? u.id : null;
  }
  async function leafOpen() {
    onTab('main');
    const L = M().leaf;
    if (L.open) { T.rat = L.rat; T.day = L.day; T.unit = L.unit; }
    else {
      await ghostAt(4);
      if (!T.unit) T.unit = pickUnit();
      if (T.unit) M().openLeaf(T.rat, T.day, T.unit);
    }
  }
  const leafReady = () => M().leaf.open && (M().leaf.data || M().leaf.err);

  /* ---- the steps ---------------------------------------------------------
     Each `before` is called by the engine as the step's own method, so it
     writes the step's words (`this.body`) from what is on screen now. */
  function steps() {
    const t = lead();
    const head = [
      {
        id: 'welcome', title: 'The Monolith, in two minutes',
        before: async function () { closeAll(); window.scrollTo(0, 0); },
        body: 'Every way of measuring how two regions move together, at every frequency from 1 to 55 Hz, '
          + 'compared between Precon1 and Precon4 in each rat and then pooled over the rats. This tour follows '
          + 'one real result from the overview down to the recording it came from.',
        note: 'Escape leaves at any point. “Take the tour”, at the top of the page, brings it back.',
      },
      {
        id: 'kept', target: '#damage', title: 'Before any result: what was kept',
        before: async function () {
          if (M().leaf.open) M().closeLeaf();
          if (M().ghost.pair != null) M().closeGhost(true);
          if (window.MONO_HELP) window.MONO_HELP.close();
          onTab('cov');
          await until(() => q('#damage h2'), 3000);
          const d = M().damage;
          const W = d && d.whole;
          const enough = d && d.pairs ? d.pairs.filter((x) => x.enough).length : null;
          this.body = (W ? 'Of ' + num(W.cue.total) + ' presentations (cue pairs), ' + num(W.cue.kept) + ' kept every region, '
            + num(W.cue.partial) + ' lost a region somewhere and ' + num(W.cue.lost) + ' were lost entirely. ' : '')
            + 'Losses are split by cause: clipping (the signal at the rail) against probe placement (histology). '
            + (enough != null ? enough + ' of ' + d.pairs.length + ' region pairs have enough rats to be compared at all; the '
              + 'matrix at the bottom shows which.' : '');
        },
        body: '',
        note: 'Anything left out can still be opened and looked at, marked as not used.',
      },
      {
        id: 'counts', target: '#verdict', title: 'First: how much of this is chance',
        before: async function () {
          closeAll();
          const c = (S().counts || {})[M().state.layer] || {};
          this.body = 'The Monolith ran ' + num(c.tested) + ' tests. ' + num(c.p05) + ' came out p < .05, and chance '
            + 'alone would give about ' + num(c.chance_p05) + '. So most of what passes is noise, and the job here is '
            + 'finding what holds up.';
        },
        body: '',
        note: 'Every p on this page is uncorrected, on purpose: the Monolith is for finding leads, not for proving them.',
      },
      {
        id: 'circuit', target: '#circsvg', title: 'One line is one pair of regions',
        before: async function () { closeAll(); },
        body: 'Each dot is a region; each line is a pair whose coupling changed from Precon1 to Precon4. Red is '
          + 'stronger on Precon4, blue weaker, and a thicker line is a bigger change. A ringed dot’s own power '
          + 'changed too; a grey one had no usable wires in enough rats. For Granger, a direction measure, the '
          + 'lines are arrows.',
      },
      {
        id: 'view', target: '#controls', title: 'What you are looking at',
        before: async function () {
          closeAll();
          this.body = 'The circuit shows one view at a time: a window (one of the 4 states — pre-baseline, cue 1, '
            + 'cue 2, post-baseline — or one of the 3 transitions between them), a frequency, and a measure. Line '
            + 'thickness is the size of the change, not its p; the p of every line is in the list under the circuit. '
            + 'The view now is written above the circuit: “'
            + (q('#ctitle') ? q('#ctitle').textContent : '') + '”. The slider at the bottom of this panel sets how '
            + 'strict to be: left shows everything tested, right only the strongest.';
        },
        body: '',
        note: 'Every ? beside a control says what it is, with a strong and a no-effect example.',
      },
    ];
    if (!t) {
      return head.concat([{
        id: 'end', target: '#monoTour', title: 'That is the page',
        body: 'This Monolith has no points of interest to walk through yet. When it does, this tour follows the '
          + 'first one down to its recording.',
      }]);
    }
    return head.concat([
      {
        id: 'leads', target: '#toplist > li', action: 'click', title: 'The leads, best first',
        before: async function () {
          closeAll();
          this.body = 'Of everything tested, these are the entries most worth a look: most rats changing the same '
            + 'way first, then the smallest p. The first is ' + leadSay(t) + ', with ' + t.same + ' of ' + t.k
            + ' rats the same way.';
        },
        body: '', doText: 'Click the first lead to bring it into view.',
      },
      {
        id: 'edge', target: '#circsvg path.edge.sel', action: 'click', title: 'Open it up',
        before: async function () {
          if (M().leaf.open) M().closeLeaf();
          if (M().ghost.pair != null) M().closeGhost(true);
          onLead();
          await until(() => q('#circsvg path.edge.sel'), 3000);
        },
        body: 'The lead is now the highlighted line. Clicking any line lifts it out of the circuit, so you can see '
          + 'what it is made of.',
        doText: 'Click the highlighted line.',
      },
      {
        id: 'pooled', target: '#ghostsvg path.garc', action: 'click', title: 'One line is every rat at once', pad: 14,
        before: async function () {
          await ghostAt(1);
          const P = (M().ghost.detail || {}).pooled || {};
          this.body = 'This is the pooled change: each rat’s own Precon4 − Precon1, combined, with more weight on '
            + 'the rats measured more precisely. Here it is ' + signed(P.est) + ', p ' + pSay(P.p) + '.';
        },
        body: '', doText: 'Click the line to split it into its rats.', afterClick: 700,
      },
      {
        id: 'forest', target: '#gstats', title: 'Each rat on its own',
        before: async function () { await ghostAt(2); await until(() => q('#gstats svg.mfig'), 3000); },
        body: 'Now there is one line per rat. Under the circuit, the same as a forest plot: a square per rat (bigger '
          + 'carries more weight), its 95% interval, and the pooled change as the diamond. Squares all on one side '
          + 'of zero mean the rats agree; squares on both sides mean the pooled number hides a split.',
      },
      {
        id: 'rat', action: 'click', title: 'One rat',
        target: () => q('#ghostsvg path.garc[data-key="r' + T.rat + '"]'),
        before: async function () {
          await ghostAt(2);
          T.rat = pickRat();
          const r = ratOf(T.rat) || {};
          this.body = 'Pick a rat to see where its change came from. r' + T.rat + ' went from ' + sig(r.left)
            + ' on Precon1 to ' + sig(r.right) + ' on Precon4 (' + signed(r.delta) + ').';
          this.doText = 'Click r' + T.rat + '.';
        },
        body: '', afterClick: 700,
      },
      {
        id: 'day', action: 'click', title: 'Its two days',
        target: () => q('#ghostsvg path.garc[data-key="' + T.day + '"]'),
        before: async function () {
          await ghostAt(3);
          T.day = 'Precon4';
          this.body = 'r' + T.rat + '’s two days. Each day’s number is the mean over that day’s cue pairs, both '
            + 'pairings. Under the circuit, each cue pair is a dot, with the mean and its standard error: a '
            + 'spread-out day is a less certain day.';
          this.doText = 'Click ' + T.day + '.';
        },
        body: '', afterClick: 700,
      },
      {
        id: 'unit', action: 'click', title: 'Every cue pair',
        target: () => q('#ghostsvg path.garc[data-key="' + T.unit + '"]'),
        before: async function () {
          await ghostAt(4);
          T.unit = pickUnit();
          this.body = 'One line per cue pair of r' + T.rat + ' on ' + T.day + '. A dashed line had no value: hover '
            + 'it and it says why (usually a clipped or missing wire).';
          this.doText = 'Click ' + (T.unit || 'a cue pair') + ' to see the recording.';
        },
        body: '', afterClick: 500,
      },
      {
        id: 'traces', title: 'The recording itself', required: false,
        target: () => q('#leaf .lsec') || q('#leaf .warn') || q('#leaf'),
        before: async function () {
          await leafOpen();
          await until(leafReady, 90000);
          const L = M().leaf;
          this.body = !L.open
            ? 'No cue pair of this rat and day could be opened, so there is no recording to show here.'
            : L.err
              ? 'This recording is no longer on the VACC (Temp is cleared from time to time), so its traces cannot '
                + 'be shown here. Uploading it again brings them back; the numbers on the page are unaffected.'
              : 'This is r' + L.rat + '’s cue pair ' + L.unit + ' on ' + L.day + ' as recorded, read from the VACC '
                + 'copy: both regions, 10 s either side, its windows marked. The shaded stretch is the one this '
                + 'number came from. Below it, the same stretch four ways: raw, filtered to the band, its envelope '
                + '(how loud), and the phase difference between the two regions.';
        },
        body: '',
      },
      {
        id: 'made', title: 'How the number was made',
        target: () => q('#leaf .lcard.sel') || q('#leaf'),
        before: async function () {
          await leafOpen();
          await until(leafReady, 90000);
          const L = M().leaf;
          this.body = (L.data && L.data.explain)
            ? 'Each measure is drawn the way it is computed, the one you were viewing first. The number stored by '
              + 'the cluster sits beside the one recomputed here from these traces, and they should match. Scroll '
              + 'down for the others, and for phase–amplitude coupling.'
            : 'With the recording in place, each measure is drawn here the way it is computed, with the stored '
              + 'number beside the one recomputed from the traces.';
        },
        body: '', note: 'The ? on each card explains that measure, with a strong and a no-effect example.',
      },
      {
        id: 'end', target: '#monoTour', title: 'That is the whole loop',
        before: async function () { if (M().leaf.open) M().closeLeaf(); if (window.MONO_HELP) window.MONO_HELP.close(); },
        body: 'Circuit → a lead → its rats → a rat’s days → a day’s cue pairs → the recording. Any line, at any '
          + 'level, opens the same way. The ? marks explain everything on the page, the Guide (linked under the '
          + 'counts) has them all in one place, and this button runs the tour again.',
      },
    ]);
  }
  let STEPS = [];

  function start() {
    if (typeof BARRY === 'undefined' || !BARRY.tour || !M() || !M().ready) return false;
    try { localStorage.setItem(SEEN, new Date().toISOString()); } catch (e) { /* this browser forgets */ }
    T.rat = null; T.day = 'Precon4'; T.unit = null;
    STEPS = steps();
    BARRY.tour.register({ id: 'monolith', name: 'The Monolith', blurb: 'One lead, from the circuit to the recording.',
                          steps: STEPS, onFinish: () => {} });
    BARRY.tour.start('monolith');
    return true;
  }

  /* The first visit: once the page has drawn, if this browser has never
     seen the tour. A browser that cannot remember is not shown it
     uninvited every time; the button still works there. */
  function firstVisit() {
    let seen = null;
    try { seen = localStorage.getItem(SEEN); } catch (e) { return; }
    if (seen) return;
    setTimeout(start, 400);
  }
  document.addEventListener('monolith:ready', firstVisit);
  if (M() && M().ready) firstVisit();

  return { start, get steps() { return STEPS.slice(); }, get chosen() { return Object.assign({}, T); }, SEEN };
})();
