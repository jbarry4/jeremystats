/* ==========================================================================
   eye.js -- Eye, lining interictal discharges up. Step 3 of The Storm.

   The eye of the storm is its centre, and that is the whole job: a
   detector's stamp is somewhere inside the window it crossed a threshold
   in, and everything downstream -- an average waveform, a CSD, a
   spectrogram triggered on these times -- is only as sharp as the stamps
   are consistent.

   IT IS BRACES' ENGINE, POINTED AT IEDs
   Not a second aligner. `braces.propose` already takes `align_ids` as a
   parameter and `/api/braces/set/<id>/commit` already derives that set from
   `curation.KINDS[entry.type]`, so the hard part -- match as many stamps as
   possible, move them least in total, never let two cross -- is already
   about stamps rather than about dentate spikes. What this adds is the
   choice of WHAT to align to, and the comparison that makes it a choice
   rather than a default.

   THREE MEASURES, ALL COMPUTED
   X-ray computes every clustering method on every fit so they can be held
   against one another, and this does the same. CSD, voltage and slope
   disagree about an IED in a way they do not about a dentate spike: a
   discharge with a slow after-going wave has its largest excursion tens of
   milliseconds after its sharpest edge, and which of those you call "the
   event" is a decision somebody should make with the three histograms in
   front of them rather than by accepting whatever the default was.

   WHAT EACH MEASURE MEANS is not written here. It comes from
   `/api/braces/measures`, which serves `braces.MEASURES` -- the fact lives
   in the module that owns the subject.
   ========================================================================== */
'use strict';

BARRY.eye = (function () {
  const q = {
    entry: null,          // the bank entry being aligned
    from_version: null,   // which version supplies the stamps
    gid: null,
    window_ms: 100,
    measure: null,        // which one is being kept; null until you choose
    origin: null,         // 'doppler' | 'import' | 'all'
    // For `_dev/eye.html` only, which banks a throwaway set of its own
    // and has to be able to see it. Nothing in the panel turns it on.
    showTests: false,
    find: '',
  };

  let cands = null;       // banked IED sets that could be aligned
  let measures = null;    // from the module that owns the fact
  let runs = {};          // measure id -> { job, proposal, error }
  let running = false;
  let polls = [];

  const clock = (t) => (t == null ? '—' : Number(t).toFixed(3));

  /* The counts, in the names `braces.summarize` actually gives them.

     A proposal's summary carries `n`, `n_no_peak`, `n_moved`, `n_flagged`
     and `shift_median_ms` -- not `matched`, `flagged` or `median_shift_ms`,
     which is what this panel first read, and every one of which came back
     undefined and was drawn as a zero. Worked out in one place so the
     three cards, the best guess and the commit dialog cannot disagree. */
  function counts(p) {
    const s = (p && p.summary) || {};
    const n = s.n || 0;
    return {
      n,
      matched: Math.max(0, n - (s.n_no_peak || 0)),
      moved: s.n_moved || 0,
      flagged: s.n_flagged || 0,
      median: s.shift_median_ms,
    };
  }

  /* Which version to read the stamps from: the newest one this machine
     can actually open, by its `ref`. The number is not unique -- this bank
     holds histories numbered 0,1,2,3,4,3,4 -- and the tip is not always
     readable here. Null reads the entry's current events, which is the
     right answer when no version is marked. */
  function startFrom(c) {
    const v = (c.versions || []).find((x) => x.newest && x.usable);
    return v ? v.ref : null;
  }

  function paint() {
    if (!BARRY.views.toolkit || BARRY.views.toolkit.tool() !== 'eye') return;
    const host = document.getElementById('tkResult');
    if (!host) return;
    host.innerHTML = '';
    host.appendChild(BARRY.ui.stepHeader({
      title: 'Eye',
      step: 'step 3 of The Storm',
      blurb: 'Put every confirmed discharge on the same part of itself, so '
           + 'an average of them is of the event and not of the jitter.',
    }));
    host.appendChild(pickCard());
    if (q.entry) host.appendChild(settingsCard());
    if (Object.keys(runs).length) host.appendChild(compareCard());
    if (q.measure && (runs[q.measure] || {}).proposal) {
      host.appendChild(commitCard());
    }
    requestAnimationFrame(drawAll);
  }

  /* ------------------------------------------------------- which set */

  /* ---- which set --------------------------------------------------------

     The first version was a radio list of names, and every name in this
     bank is some variant of "IED spikes (hand-sorted)" -- fourteen rows
     that said nothing about which recording each one was on, a bare "· 2"
     that was a version number nobody could read as one, and three sets a
     harness had left behind mixed in with real work.

     So this answers the questions in the order somebody asks them:

       WHICH RECORDING -- grouped under it, because that is what you know
                          when you arrive, and the set name is not
       WHERE IT CAME FROM -- a Doppler run or an older import. The Storm's
                          own runs by default, since those are what this
                          bundle is for; the imports are one pill away
       WHAT IS IN IT   -- how many are confirmed, split by label
       WHICH VERSION   -- named the way the bank names it ("v2"), not a
                          bare number

     Harness leftovers are not shown, and the line under the list says how
     many were hidden rather than pretending they are not there. */
  const DOPPLER = 'Doppler (line length)';

  function originOf(c) {
    const who = ((c.added || {}).by || '') + ' ' + (c.name || '');
    if (/harness/i.test(who)) return 'test';
    if (c.pipeline === DOPPLER) return 'doppler';
    return 'import';
  }

  function versionWord(c) {
    const v = (c.versions || []).find((x) => x.newest && x.usable);
    const name = (v && v.name) || c.newest_usable_name || c.current_name;
    return name != null ? 'v' + String(name).replace(/^v/i, '') : null;
  }

  function recordingOf(c) {
    return c.session_label
      || [c.project, c.mouse != null ? 'm' + c.mouse : null,
          c.session != null ? 's' + c.session : null]
          .filter(Boolean).join(' ')
      || c.gid || 'Unfiled';
  }

  function tallyChips(c) {
    // Labels in the vocabulary's own order, the confirmed ones first.
    const order = ['Solid', 'solid', 'Sputter', 'sputter', 'Flag', 'flag',
                   'Garbage', 'garbage'];
    const bl = c.by_label || {};
    const keys = Object.keys(bl).sort((a, b) => {
      const ia = order.indexOf(a), ib = order.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
    return keys.filter((k) => bl[k]).map((k) => BARRY.ui.chip(
      k.charAt(0).toUpperCase() + k.slice(1) + ' ' + bl[k],
      { kind: /solid|sputter/i.test(k) ? 'good'
            : /flag/i.test(k) ? 'warn' : null }));
  }

  function pickCard() {
    const box = el('div', { class: 'card' }, [
      el('div', { class: 'section-label', text: '1. Which set' }),
    ]);
    if (cands === null) {
      load().then(paint);
      BARRY.skeleton.into(box, 'row', 3);
      return box;
    }

    const real = cands.filter((c) => originOf(c) !== 'test');
    const tests = cands.length - real.length;
    const nOf = (o) => real.filter((c) => originOf(c) === o).length;

    // Doppler's by default -- unless there are none yet, in which case
    // showing an empty list with the imports one click away would be a
    // screen that says "nothing" when it does not mean it.
    if (!q.origin) q.origin = nOf('doppler') ? 'doppler' : 'all';

    const pills = el('div', { class: 'eye-filter' }, [
      ['doppler', 'From Doppler'],
      ['import', 'Older imports'],
      ['all', 'Everything'],
    ].map(([id, label]) => {
      const n = id === 'all' ? real.length : nOf(id);
      return el('button', {
        class: 'pill' + (q.origin === id ? ' on' : '')
               + (n ? '' : ' dim'),
        text: label + ' (' + n + ')',
        onclick: () => { q.origin = id; paint(); },
      });
    }));
    box.appendChild(pills);

    const search = BARRY.ui.searchField
      ? BARRY.ui.searchField({
          placeholder: 'Type a mouse, session or set name\u2026',
          value: q.find || '',
          // An event or a value, depending on whether it was debounced.
          oninput: (e) => { q.find = (e && e.target) ? e.target.value : (e || ''); paintList(); },
        })
      : el('input', { type: 'search', class: 'sp-input',
          placeholder: 'Type a mouse, session or set name\u2026',
          value: q.find || '',
          oninput: (e) => { q.find = e.target.value; paintList(); } });
    box.appendChild(el('div', { class: 'eye-search' }, [search]));

    const host = el('div', { id: 'eyeList' });
    box.appendChild(host);
    if (tests) {
      box.appendChild(el('p', { class: 'hint quiet',
        text: tests + ' set' + (tests === 1 ? '' : 's')
            + ' left behind by test harnesses '
            + (tests === 1 ? 'is' : 'are') + ' not shown.' }));
    }
    // Filled after the card is in the page, so typing in the search box
    // repaints the list and never the box you are typing in.
    requestAnimationFrame(paintList);
    return box;
  }

  function paintList() {
    const host = document.getElementById('eyeList');
    if (!host || !cands) return;
    host.innerHTML = '';
    const want = (q.find || '').trim().toLowerCase();
    const rows = cands.filter((c) => {
      const o = originOf(c);
      if (o === 'test') return !!q.showTests;
      if (q.origin !== 'all' && o !== q.origin) return false;
      if (!want) return true;
      return [recordingOf(c), c.name, c.project, 'm' + c.mouse,
              's' + c.session].join(' ').toLowerCase().indexOf(want) >= 0;
    });

    if (!rows.length) {
      /* Says what fills it, per filter, rather than "nothing matches". */
      host.appendChild(el('div', { class: 'empty-state',
        text: want
          ? 'Nothing here matches \u201c' + q.find + '\u201d.'
          : q.origin === 'doppler'
            ? 'No Doppler run has been confirmed yet. Run Doppler, bank what '
              + 'it finds, and confirm them in Spotter \u2014 a raw detector '
              + 'list has nothing worth moving, because half of it is thrown '
              + 'away an hour later.'
            : 'Nothing confirmed of this kind.' }));
      return;
    }

    // Grouped by recording, recordings in the order their newest set was
    // made, so the one you just worked on is at the top.
    const groups = new Map();
    for (const c of rows) {
      const k = recordingOf(c);
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(c);
    }
    for (const [rec, list] of groups) {
      const g = el('div', { class: 'eye-group' }, [
        el('div', { class: 'eye-group-head' }, [
          el('strong', { text: rec }),
          el('span', { class: 'hint quiet',
            text: list.length + ' set' + (list.length === 1 ? '' : 's') }),
        ]),
      ]);
      for (const c of list) {
        const o = originOf(c);
        const on = q.entry === c.id;
        const vw = versionWord(c);
        g.appendChild(el('button', {
          class: 'eye-set' + (on ? ' on' : ''),
          title: 'Align ' + (c.name || 'this set') + ', reading its '
               + (vw || 'newest') + ' version',
          onclick: () => {
            q.entry = c.id; q.gid = c.gid;
            q.from_version = startFrom(c);
            runs = {}; q.measure = null;
            paint();
          },
        }, [
          el('div', { class: 'eye-set-top' }, [
            el('span', { class: 'eye-set-name', text: c.name || c.id }),
            BARRY.ui.chip(o === 'doppler' ? 'Doppler' : 'imported',
                          { flag: true, kind: o === 'doppler' ? 'ok' : null }),
            vw ? BARRY.ui.chip(vw, { flag: true }) : null,
            c.aligned ? BARRY.ui.chip('already aligned',
                                      { flag: true, kind: 'warn' }) : null,
          ].filter(Boolean)),
          el('div', { class: 'eye-set-bot' }, [
            el('span', { class: 'eye-set-n',
              text: c.n_good + ' confirmed of ' + c.n }),
            BARRY.ui.chipRow(tallyChips(c)),
          ]),
        ]));
      }
      host.appendChild(g);
    }
  }

  /* The band Eye aligns through, read from the `ied` filter preset -- the
     same place the backend reads it -- so the sentence under the window
     states the numbers actually used rather than a copy of them. */
  let iedBand = null;

  async function load() {
    try {
      const f = await api('/api/presets/filters');
      iedBand = ((f.presets || []).find((x) => x.id === 'ied')) || null;
    } catch (e) { iedBand = null; }
    try {
      const got = await api('/api/braces/candidates?type=ied');
      cands = got.sets || [];
    } catch (e) { cands = []; }
    try {
      const m = await api('/api/braces/measures');
      measures = m.measures || [];
    } catch (e) { measures = []; }
  }

  /* ------------------------------------------------------ 2. settings */

  function settingsCard() {
    const band = iedBand
      ? (iedBand.highpass + '\u2013' + iedBand.lowpass + ' Hz'
         + (iedBand.notch ? ', ' + iedBand.notch + ' Hz notched' : ''))
      : 'the IED filter preset';
    const box = el('div', { class: 'card' }, [
      el('div', { class: 'section-label', text: '2. How far it may look' }),
      BARRY.ui.field({
        label: 'Window (\u00b1 ms)',
        inline: true,
        hint: 'How far from its current position a stamp may be moved. Wide '
            + 'enough to find the event, narrow enough that it cannot find '
            + 'the next one \u2014 a discharge and the one after it are '
            + 'often only a few hundred milliseconds apart.',
        control: el('input', { type: 'number', class: 'num', min: 5,
          step: 10, value: q.window_ms,
          disabled: running ? 'disabled' : null,
          onchange: (e) => { q.window_ms = Number(e.target.value) || 100; } }),
      }),
      /* Said, because it is the difference between this and Braces. The
         dentate-spike band is 5-100 Hz, and an IED seen through it has
         lost the slow wave that is half of what it is. */
      el('p', { class: 'hint', style: 'max-width:80ch',
        text: 'Aligned through the IED filter (' + band + '), not the '
            + 'dentate-spike band. All three measures are computed on every '
            + 'run, so the choice is made with the answers in front of you '
            + 'rather than by accepting a default. Nothing is written until '
            + 'you commit one.' }),
    ]);
    if (running) {
      box.appendChild(waitCard());
    } else {
      box.appendChild(el('div', { class: 'tk-actions' }, [
        el('span', { class: 'spacer' }),
        el('button', { class: 'btn', text: 'Line them up', onclick: runAll }),
      ]));
    }
    return box;
  }

  /* ---- the wait ----------------------------------------------------------

     Three runs, one after another, each a real read of the recording -- so
     it is a `stepLoader` with the three measures as its stages, which is
     what the constitution says that component is for: named stages that
     each take real time. Under it, what the current run is doing in the
     job's own words, a bar, how long it has taken, and a way out.

     Only this block repaints on a poll. Repainting the whole panel every
     800 ms would redraw the finished histograms under it for nothing and
     restart the loader's animation each time. */
  let wait = null;          // { at, job, t0 }
  let stopAsked = false;

  const STAGE_WORDS = {
    'ds profile': 'reading the channels',
    'ds depth': 'finding where on the probe it is',
    'ds windows': 'reading the window around each stamp',
  };

  function waitCard() {
    const names = (measures || []).map((m) => m.name);
    const node = stepLoader('Lining them up', names);
    const at = wait ? wait.at : 0;
    const job = wait && wait.job;
    let line = names[at] || '';
    let frac = 0;
    if (job) {
      const st = (job.stages || []).find((x) => x.status === 'running')
        || (job.stages || []).filter((x) => x.status === 'done').pop();
      if (st) {
        line += ' \u00b7 ' + (STAGE_WORDS[st.name] || st.name);
        if (st.of > 1) {
          line += ' ' + (st.done || 0).toLocaleString() + ' / '
                + st.of.toLocaleString();
          frac = Math.min(1, (st.done || 0) / st.of);
        }
      }
    }
    for (let i = 0; i < at; i++) node.step(names[i] + ' done');
    node.step(line);

    const overall = names.length ? (at + frac) / names.length : 0;
    const secs = wait ? Math.round((Date.now() - wait.t0) / 1000) : 0;
    const eta = job && job.eta_s
      ? ' \u00b7 about ' + Math.max(1, Math.round(job.eta_s)) + ' s left on '
        + 'this one' : '';
    return el('div', { id: 'eyeWait', class: 'eye-wait' }, [
      node,
      el('div', { class: 'comod-total' }, [
        el('div', { class: 'comod-bar' }, [
          el('div', { class: 'comod-bar-fill',
                      style: 'width:' + (100 * overall).toFixed(1) + '%' }),
        ]),
        el('span', { class: 'comod-eta',
          text: (at + 1) + ' of ' + names.length + ' \u00b7 ' + secs + ' s'
              + eta }),
      ]),
      el('div', { class: 'tk-actions' }, [
        el('span', { class: 'hint quiet',
          text: 'Each measure reads the recording around every confirmed '
              + 'stamp. The ones already finished are drawn below as they '
              + 'land.' }),
        el('span', { class: 'spacer' }),
        el('button', { class: 'btn ghost',
          text: stopAsked ? 'Stopping\u2026' : 'Stop',
          disabled: stopAsked ? 'disabled' : null,
          onclick: stop }),
      ]),
    ]);
  }

  function updateWait() {
    const old = document.getElementById('eyeWait');
    if (old && running) old.replaceWith(waitCard());
  }

  async function stop() {
    stopAsked = true;
    updateWait();
    const id = wait && wait.job && wait.job.id;
    if (id) {
      try { await apiPost('/api/cfc/job/' + id + '/cancel', {}); }
      catch (e) { /* the poll will see it end either way */ }
    }
  }

  /* One run per measure. Sequential rather than three at once: each reads a
     whole channel of the recording, and three of those in parallel is three
     times the disk for the same wall clock on one spindle. */
  async function runAll() {
    if (running || !q.entry) return;
    running = true;
    stopAsked = false;
    runs = {}; q.measure = null;
    wait = { at: 0, job: null, t0: Date.now() };
    paint();
    const ms = measures || [];
    for (let i = 0; i < ms.length; i++) {
      if (stopAsked) break;
      const m = ms[i];
      wait = { at: i, job: null, t0: wait.t0 };
      runs[m.id] = { status: 'running' };
      updateWait();
      try {
        const started = await apiPost('/api/braces/run', {
          entry_id: q.entry,
          from_version: q.from_version,
          window_ms: q.window_ms,
          measure: m.id,
        });
        wait.job = started.job;
        const out = await waitFor(started.job.id, (job) => {
          wait.job = job;
          updateWait();
        });
        runs[m.id] = { status: 'done', proposal: out };
      } catch (e) {
        runs[m.id] = stopAsked ? { status: 'failed', error: 'Stopped.' }
                               : { status: 'failed', error: e.message };
      }
      // A finished one is drawn now, not after all three.
      paint();
    }
    running = false;
    wait = null;
    if (stopAsked) {
      toast('Stopped. The measures that finished are still here to compare.',
            null, 6000);
    }
    stopAsked = false;
    // The one that moved the stamps least in total, offered rather than
    // chosen: a smaller median move means the stamps were already near
    // what that measure calls the event, which is evidence and not a
    // verdict.
    q.measure = bestGuess();
    paint();
  }

  function waitFor(id, onTick) {
    return new Promise((resolve, reject) => {
      const t = setInterval(async () => {
        let got;
        try { got = await api('/api/cfc/job/' + id); }
        catch (e) { return; }
        if (onTick) { try { onTick(got.job); } catch (e) { /* drawing */ } }
        if (got.job.status === 'running') return;
        clearInterval(t);
        polls = polls.filter((x) => x !== t);
        if (got.job.status !== 'done') {
          reject(new Error(got.job.error || 'that run failed'));
          return;
        }
        try {
          const r = await api('/api/cfc/result/' + id);
          resolve(r.result);
        } catch (e) { reject(e); }
      }, 800);
      polls.push(t);
    });
  }

  function bestGuess() {
    let best = null, bestV = Infinity;
    for (const id of Object.keys(runs)) {
      const p = (runs[id] || {}).proposal;
      if (!p) continue;
      const s = counts(p);
      // Matched first, then moved least. A measure that finds a peak for
      // fewer stamps has not done better by moving the ones it found less.
      const miss = s.n - s.matched;
      const v = miss * 1000 + Math.abs(s.median || 0);
      if (v < bestV) { bestV = v; best = id; }
    }
    return best;
  }

  /* ------------------------------------------------- 3. the comparison */

  function compareCard() {
    const box = el('div', { class: 'card' }, [
      el('div', { class: 'section-label', text: '3. The three answers' }),
    ]);
    const grid = el('div', { class: 'eye-three' });
    for (const m of (measures || [])) {
      const r = runs[m.id] || {};
      const p = r.proposal || null;
      const s = counts(p);
      grid.appendChild(el('div', {
        class: 'eye-one' + (q.measure === m.id ? ' on' : ''),
        onclick: () => { if (p) { q.measure = m.id; paint(); } },
      }, [
        el('strong', { text: m.name }),
        r.status === 'running'
          ? el('div', { class: 'hint quiet', text: 'running…' })
          : null,
        r.status === 'failed'
          ? el('p', { class: 'warn-line', text: r.error }) : null,
        p ? BARRY.ui.chipRow([
          BARRY.ui.chip(s.matched + ' of ' + s.n + ' matched'),
          BARRY.ui.chip('median ' + clock(s.median) + ' ms'),
          (s.flagged ? BARRY.ui.chip(s.flagged + ' flagged',
                                     { kind: 'warn' }) : null),
        ].filter(Boolean)) : null,
        p ? el('canvas', { id: 'eyeHist_' + m.id, class: 'eye-hist' }) : null,
        el('p', { class: 'hint quiet', text: m.why }),
      ].filter(Boolean)));
    }
    box.appendChild(grid);
    if (q.measure) {
      box.appendChild(el('p', { class: 'hint',
        text: 'Keeping ' + nameOf(q.measure) + '. Click another to keep that '
            + 'one instead — nothing is written until you commit.' }));
    }
    return box;
  }

  const nameOf = (id) => ((measures || []).find((m) => m.id === id) || {})
    .name || id;

  /* The shift histogram leads, not the table.

     What you need to know first is whether the moves are a tight cloud
     around a small number -- stamps that were already nearly right, nudged
     -- or a spread with a tail, which is a measure finding a different
     event for some of them. A table of 1,450 rows cannot answer that and a
     histogram answers it at a glance. */
  function drawAll() {
    for (const m of (measures || [])) {
      const p = (runs[m.id] || {}).proposal;
      if (p) drawHist('eyeHist_' + m.id, p);
    }
  }

  function drawHist(id, p) {
    const cv = document.getElementById(id);
    if (!cv || !cv.parentNode) return;
    const w = Math.max(120, Math.round(cv.clientWidth
      || cv.parentNode.clientWidth || 220));
    const h = 92;
    const dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    cv.style.width = '100%';
    cv.style.height = h + 'px';
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);

    /* From the summary's own histogram, not from rows. The job's result
       carries no rows -- the run route pops them into the set, where the
       bench reads them -- so binning `p.rows` drew "nothing matched" under
       every measure. `summarize` bins the MOVED stamps across the window
       the run was actually made with, which may not be the number in the
       box now if somebody has changed it since. */
    const s = p.summary || {};
    const bins = (s.hist || []).slice();
    const nb = bins.length;
    if (!nb || !bins.some((v) => v > 0)) {
      g.fillStyle = BARRY.token('--text-3', '#888');
      g.font = '10px system-ui';
      g.textAlign = 'center';
      g.fillText('nothing moved', w / 2, h / 2);
      g.textAlign = 'left';
      return;
    }
    const lim = Math.abs(Number(s.hist_hi_ms) || s.window_ms || q.window_ms);
    const hi = Math.max(1, ...bins);
    const P = { l: 4, r: 4, t: 6, b: 14 };
    const plotW = w - P.l - P.r;
    const plotH = h - P.t - P.b;
    const bw = plotW / nb;
    g.fillStyle = BARRY.token('--accent', '#E5A823');
    bins.forEach((v, i) => {
      const bh = (v / hi) * plotH;
      g.fillRect(P.l + i * bw, P.t + plotH - bh, Math.max(1, bw - 1), bh);
    });
    // Zero, so "they barely moved" and "they all moved one way" look
    // different rather than both looking like a hump.
    const zx = P.l + plotW / 2;
    g.strokeStyle = BARRY.token('--text-3', '#888');
    g.setLineDash([2, 3]);
    g.beginPath(); g.moveTo(zx, P.t); g.lineTo(zx, P.t + plotH); g.stroke();
    g.setLineDash([]);
    g.fillStyle = BARRY.token('--text-3', '#888');
    g.font = '9px system-ui';
    g.textAlign = 'left';
    g.fillText('-' + lim + ' ms', P.l, h - 3);
    g.textAlign = 'right';
    g.fillText('+' + lim + ' ms', P.l + plotW, h - 3);
    g.textAlign = 'left';
  }

  /* ------------------------------------------------------ 4. committing */

  function commitCard() {
    const p = runs[q.measure].proposal;
    const s = counts(p);
    const box = el('div', { class: 'card' }, [
      el('div', { class: 'section-label', text: '4. Write it' }),
      el('p', { class: 'hint', style: 'max-width:80ch',
        text: 'Committing writes a new version of the entry with the moved '
            + 'times on it. Every stamp that moves carries where it came '
            + 'from, so the version history reads as a set of moves rather '
            + 'than as everything lost and everything gained — which '
            + 'is what it said before `from_t` existed, about a pass in '
            + 'which nothing was decided differently at all.' }),
      BARRY.ui.chipRow([
        BARRY.ui.chip(nameOf(q.measure)),
        BARRY.ui.chip(s.moved + ' would move'),
        BARRY.ui.chip('window ±' + q.window_ms + ' ms'),
        s.flagged ? BARRY.ui.chip(s.flagged + ' flagged for a look',
                                  { kind: 'warn' }) : null,
      ].filter(Boolean)),
      el('div', { class: 'tk-actions' }, [
        el('span', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Look at them first',
          title: 'Open the proposal on the bench, one at a time',
          onclick: () => openBench(p) }),
        el('button', { class: 'btn', text: 'Commit the moves',
          onclick: () => commit(p) }),
      ]),
    ]);
    return box;
  }

  function openBench(p) {
    // The bench is Braces' own, and it is the one that exists: a proposal
    // is a proposal whatever measure produced it.
    //
    // Braces exports it as `_open(set_id)`; there is no `openBench` on it,
    // so the first version of this always fell through to the toast. The
    // Braces view has to be the one on screen for its panel to draw into.
    if (BARRY.braces && BARRY.braces._open && p.set_id) {
      BARRY.views.toolkit.pick('braces');
      BARRY.braces._open(p.set_id);
      return;
    }
    toast('That proposal has no bench to open — commit it or run it '
          + 'again.', 'warn', 7000);
  }

  async function commit(p) {
    const s = counts(p);
    const ok = await BARRY.confirm(
      'Move ' + s.moved + ' stamps?',
      el('div', { class: 'fix-facts' }, [
        el('p', { text: 'Aligned on ' + nameOf(q.measure).toLowerCase()
            + ', within ±' + q.window_ms + ' ms. A new version of the '
            + 'entry is written; nothing is overwritten.' }),
        el('p', { text: 'Stamps that found no peak stay exactly where they '
            + 'are, which is not an error — it is the aligner '
            + 'declining to guess.' }),
      ]), 'Commit the moves');
    if (!ok) return;
    try {
      // Dry run first, always. The route defaults to it and the panel
      // should not be the thing that discovers a refusal.
      const dry = await apiPost('/api/braces/set/' + p.set_id + '/commit',
                                { apply: false });
      // A refusal arrives as `ok: false`, which apiPost throws on; what
      // comes back here is the report, under `report`. Nothing to do is
      // not a refusal -- every stamp already where this measure puts it.
      const rep = (dry && dry.report) || {};
      if (rep.nothing_to_do) {
        toast(rep.why || 'Every stamp is already where this measure puts '
              + 'it, so there is nothing to write.', 'ok', 8000);
        return;
      }
      const done = await apiPost('/api/braces/set/' + p.set_id + '/commit',
                                 { apply: true });
      const r = (done && done.report) || {};
      toast('Written as ' + (r.version_name || r.next_name
                             || rep.next_name || 'a new version') + '.',
            'ok', 8000);
      runs = {}; q.measure = null;
      cands = null;
      paint();
    } catch (e) {
      toast(e.message, 'err', 12000);
    }
  }

  /* A poll belongs to the view that started it. */
  function onHide() {
    for (const t of polls) clearInterval(t);
    polls = [];
  }

  return {
    paint, onHide,
    _state: () => q,
    _runs: () => runs,
    _best: bestGuess,
    _counts: counts,
    // For the harness: forget the list so the next paint asks again,
    // after it has banked a set of its own.
    _reset: () => {
      onHide();
      cands = null; measures = null; runs = {}; running = false;
      q.entry = null; q.gid = null; q.from_version = null; q.measure = null;
    },
  };
})();
