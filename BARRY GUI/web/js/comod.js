/* ==========================================================================
   comod.js -- the comodulogram window.

   Opened by CFCScope, in a window of its own rather than as a dialog. You
   keep it up while moving the window around the recording and stack the maps
   as you go, because comparing two of them is most of what the thing is for
   and a modal cannot be compared with anything.

   Three parts, in the order they happen:

     1. A form that fills itself in from whatever XploreFinder is showing,
        and says what the run will cost before you commit to it.
     2. A stage list, which is the loading display. Not a spinner: seven
        named steps, each counting in its own unit, weighted by what they
        actually cost. It stays on screen afterwards as a receipt of where
        the time went.
     3. The map, drawn on a canvas from the numbers rather than shown as a
        picture, so rescaling, recolouring and reading a cell cost nothing.

   The colour rules are not decoration. `fig11_colour_lies.py` in the CFC
   explainer shows the same no-coupling recording three ways, and only the
   sequential, fixed-scale one reads as "there is nothing here". A rainbow
   invents edges in smooth data and per-figure autoscaling makes noise look
   like signal, so: sequential by default, the maximum always printed, and
   Lock scale so two maps in this window can actually be compared.
   ========================================================================== */
'use strict';

BARRY.views.comod = (function () {
  /* What we are about to ask for. Held here rather than read off the DOM so
     a re-render cannot lose a half-filled form. */
  const q = {
    channel: null,
    t0: 0, t1: 0,
    /* Step and bandwidth are different numbers and the amplitude axis is
       where that bites. params.m is `fastVec = 20:5:200` with `fastBW = 10`:
       bands 10 Hz wide, stepped by 5, so they OVERLAP by half -- that is the
       newFCSE convention, not an oversight. Defaulting the width to the step
       made 5 Hz bands, which put the centres on 22.5, 27.5 ... instead of
       25, 30 ... and quietly reported a different grid from the one the lab
       has been running for years.

       The phase axis happens to be contiguous (0.5 step, 0.5 wide), which is
       why the mistake only showed up in the amplitude readout. */
    slow_lo: 4, slow_hi: 12, slow_step: 0.5, slow_bw: 0.5,
    fast_lo: 20, fast_hi: 200, fast_step: 5, fast_bw: 10,
    nsurr: 0, surrN: 50,
    cmap: 'seqblue',
  };

  let ctx = null;         // the opener's live state
  let est = null;         // what the run is likely to cost
  let job = null;         // the run in flight
  let poll = null;
  let maps = [];          // finished maps, newest first
  let shown = 0;          // which one is on the canvas
  let lockScale = false;
  let lockedMax = null;
  let hover = null;
  let follow = true;      // keep the window fields on the opener's window
  /* The colormaps, fetched here rather than borrowed from Xplorefinder.

     The first version read the colormap list off Xplorefinder's own module
     state. That state is a `const` inside xplore.js's IIFE, so it is not a
     property of anything and the read was always undefined -- the guard
     meant no crash, just a picker quietly offering two hardcoded entries
     instead of the thirteen the server has, and a colour ramp built from an
     eight-stop approximation of the real one. This is a separate window; it
     asks the server itself. */
  let cmaps = [];

  /* name, phase lo/hi/step/bw, amplitude lo/hi/step/bw, why. */
  const GRIDS = [
    ['Theta (beta run)', 4, 12, 0.5, 0.5, 20, 200, 5, 10,
     'The params.m grid: theta phase against 20-200 Hz amplitude, 10 Hz '
     + 'bands stepped by 5. 629 cells.'],
    ['Full lab sweep', 1, 26, 0.5, 0.5, 20, 200, 5, 10,
     'What newFCSE.m ran: 1-26 Hz phase. 51 x 37 = 1887 cells, three times '
     + 'the wait.'],
    ['Quick look', 4, 12, 1, 1, 20, 160, 10, 10,
     'Coarse, for deciding whether a window is worth the full grid.'],
  ];

  /* ==================================================================
     Talking to the window that opened us
     ================================================================== */
  /* `barryCfc`, not `BARRY.cfc`.

     `BARRY` is declared `const` at the top of core.js, which makes it a
     lexical binding in the script's global scope and NOT a property of
     `window`. So `window.opener.BARRY` is undefined from here however
     completely the opener has loaded, and the first version of this
     silently decided there was no opener every single time and rendered
     the "open this from CFCScope" fallback for ever.

     Each side therefore publishes the one handle the other needs as a real
     property. `BARRY.cfc` is still the name inside its own window. */
  function opener() {
    try {
      const o = window.opener;
      if (!o || o.closed) return null;
      if (o.barryCfc && o.barryCfc.context) return o;
    } catch (e) { /* closed, or gone to another origin */ }
    return null;
  }

  function pullContext(force) {
    const o = opener();
    if (!o) return false;
    let got = null;
    try { got = o.barryCfc.context(); } catch (e) { got = null; }
    if (!got) return false;
    const first = !ctx;
    ctx = got;
    if (first || force || follow) {
      q.t0 = round2(ctx.t0);
      q.t1 = round2(ctx.t1);
      if (first || q.channel == null) q.channel = ctx.channel;
    }
    return true;
  }

  /* Called by CFCScope whenever the window or the channel moves. */
  function openerMoved() {
    if (!pullContext()) return;
    if (follow) { refreshEstimate(); render(); }
  }

  const round2 = (v) => Math.round((v || 0) * 100) / 100;

  /* ==================================================================
     Loading
     ================================================================== */
  function onShow() {
    loadColormaps();
    if (!pullContext(true)) {
      render();
      return;
    }
    refreshEstimate();
    render();
  }

  async function loadColormaps() {
    if (cmaps.length) return;
    try {
      const got = await api('/api/panels');
      cmaps = got.colormaps || [];
      // The swatch is what the canvas paints with, so a late arrival has to
      // repaint rather than wait for the next interaction.
      if (cmaps.length && maps.length) render();
    } catch (e) { /* the fallback ramps below cover it */ }
  }

  function body() {
    return {
      path: ctx.path, even_only: ctx.evenOnly, invert: ctx.invert,
      channel: q.channel, t0: q.t0, t1: q.t1,
      slow_lo: q.slow_lo, slow_hi: q.slow_hi, slow_step: q.slow_step,
      slow_bw: q.slow_bw || q.slow_step,
      fast_lo: q.fast_lo, fast_hi: q.fast_hi, fast_step: q.fast_step,
      fast_bw: q.fast_bw || q.fast_step,
      nsurr: q.nsurr, cmap: q.cmap,
      highpass: ctx.highpass, lowpass: ctx.lowpass, notch: ctx.notch,
    };
  }

  let estSeq = 0;
  async function refreshEstimate() {
    if (!ctx) return;
    const mine = ++estSeq;
    try {
      const got = await apiPost('/api/cfc/estimate', body());
      if (mine !== estSeq) return;      // a later edit has superseded this
      est = got;
    } catch (e) {
      est = null;
    }
    paintEstimate();
  }

  /* ==================================================================
     Running it
     ================================================================== */
  async function run() {
    if (!ctx || job) return;
    let started;
    try {
      started = await apiPost('/api/cfc/comodulogram', body());
    } catch (e) {
      toast(e.message, 'err', 9000);
      return;
    }
    if (started.cached) {
      // Already made, this session. Straight to the picture.
      addMap(started.result, true);
      render();
      return;
    }
    job = started.job;
    render();
    watch();
  }

  function watch() {
    clearInterval(poll);
    /* 250 ms. Fast enough that a stage which takes half a second is seen to
       happen, slow enough that a thirty-second run is 120 requests and not
       a thousand. The server's answer is a dict lookup. */
    poll = setInterval(async () => {
      if (!job) { clearInterval(poll); return; }
      let got;
      try {
        got = await api('/api/cfc/job/' + job.id);
      } catch (e) {
        return;                     // a dropped poll is not a failed run
      }
      job = got.job;
      paintStages();
      if (job.status === 'running') return;
      clearInterval(poll);
      const finished = job;
      job = null;
      if (finished.status === 'done') {
        try {
          const res = await api('/api/cfc/result/' + finished.id);
          addMap(res.result, false, finished);
        } catch (e) {
          toast('The run finished but the result could not be read: '
                + e.message, 'err', 9000);
        }
      } else if (finished.status === 'failed') {
        toast(finished.error || 'The run failed.', 'err', 10000);
      }
      render();
    }, 250);
  }

  async function cancel() {
    if (!job) return;
    try { await apiPost('/api/cfc/job/' + job.id + '/cancel', {}); } catch (e) {}
  }

  function addMap(res, cached, ranAs) {
    maps.unshift({
      res: res,
      at: new Date(),
      cached: !!cached,
      stages: ranAs ? ranAs.stages : null,
      elapsed: ranAs ? ranAs.elapsed : null,
    });
    maps = maps.slice(0, 8);          // eight is more than anyone compares
    shown = 0;
    if (lockScale && lockedMax == null) lockedMax = res.max;
  }

  /* ==================================================================
     Rendering
     ================================================================== */
  function render() {
    const host = document.getElementById('comodBody');
    if (!host) return;
    host.innerHTML = '';

    if (!ctx) {
      host.appendChild(el('div', { class: 'card' }, [
        el('p', { text: 'This window is opened from CFCScope, and it reads '
                      + 'the recording and the window from it.' }),
        el('p', { class: 'hint',
          text: 'The window that opened this one has gone. Open CFCScope '
              + 'again from the Toolkit and press C.' }),
      ]));
      return;
    }

    host.appendChild(formCard());
    if (job) host.appendChild(stageCard());
    if (maps.length) host.appendChild(mapCard());
  }

  /* ---------------- the form ---------------- */
  function num(key, label, title, opts) {
    const o = opts || {};
    return el('label', { class: 'comod-field', title: title }, [
      el('span', { text: label }),
      el('input', {
        type: 'number', value: q[key], min: o.min, max: o.max, step: o.step,
        onchange: (e) => {
          const v = parseFloat(e.target.value);
          if (!isFinite(v)) { e.target.value = q[key]; return; }
          q[key] = v;
          if (key === 't0' || key === 't1') follow = false;
          refreshEstimate();
          render();
        },
      }),
    ]);
  }

  function formCard() {
    const box = el('div', { class: 'card comod-form' });
    const span = q.t1 - q.t0;
    const cycles = span * (q.slow_lo + (q.slow_bw || q.slow_step) / 2);

    box.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: 'What to measure' }));

    // ---- where ----
    box.appendChild(el('div', { class: 'comod-row' }, [
      el('label', { class: 'comod-field', title: 'One channel. Coupling is a '
                    + 'property of a signal, not of an average of signals.' }, [
        el('span', { text: 'Channel' }),
        el('select', {
          onchange: (e) => { q.channel = parseInt(e.target.value, 10);
                             follow = false; refreshEstimate(); render(); },
        }, (ctx.channels || []).map((c) => el('option', {
          value: c.index, text: c.label + (c.bad ? '  (bad)' : ''),
          selected: c.index === q.channel ? 'selected' : null,
        }))),
      ]),
      num('t0', 'From (s)', 'Start of the window', { step: 0.1, min: 0 }),
      num('t1', 'To (s)', 'End of the window', { step: 0.1, min: 0 }),
      el('button', {
        class: 'btn ghost sm' + (follow ? ' on' : ''),
        text: follow ? 'Following the view' : 'Use the current window',
        title: follow
          ? 'These fields track XploreFinder. Type in one to stop.'
          : 'Put XploreFinder’s window and channel back in these fields, '
            + 'and follow it again.',
        onclick: () => { follow = true; pullContext(true);
                         refreshEstimate(); render(); },
      }),
    ]));

    // Short windows are the commonest way to get a map full of nothing.
    if (cycles < 40) {
      box.appendChild(el('p', { class: 'hint warn',
        text: 'That is about ' + Math.round(cycles) + ' cycles of the slowest '
            + 'phase band. A modulation index needs the slow rhythm to go '
            + 'round enough times to fill eighteen phase bins; under about '
            + 'forty cycles the map is mostly noise. '
            + Math.ceil(40 / Math.max(q.slow_lo, 0.5)) + ' s would do it.' }));
    }

    // ---- the grid ----
    box.appendChild(el('div', { class: 'section-label', text: 'The grid' }));
    box.appendChild(el('div', { class: 'comod-row' },
      GRIDS.map(([name, sl, sh, ss, sb, fl, fh, fp, fb, why]) => el('button', {
        class: 'pill' + (q.slow_lo === sl && q.slow_hi === sh
                         && q.slow_step === ss && q.fast_lo === fl
                         && q.fast_hi === fh && q.fast_step === fp
                         && q.fast_bw === fb ? ' active' : ''),
        text: name, title: why,
        onclick: () => {
          Object.assign(q, { slow_lo: sl, slow_hi: sh, slow_step: ss,
                             slow_bw: sb, fast_lo: fl, fast_hi: fh,
                             fast_step: fp, fast_bw: fb });
          refreshEstimate(); render();
        },
      }))));

    box.appendChild(el('div', { class: 'comod-row' }, [
      el('span', { class: 'comod-axis', text: 'Phase' }),
      num('slow_lo', 'from', 'Lowest phase band', { step: 0.5, min: 0.5 }),
      num('slow_hi', 'to', 'Highest phase band', { step: 0.5, min: 1 }),
      num('slow_step', 'step', 'Spacing of the phase bands', { step: 0.1, min: 0.1 }),
      num('slow_bw', 'width', 'How wide each band is. Equal to the step means '
          + 'they tile; wider means they overlap.', { step: 0.1, min: 0.1 }),
      el('span', { class: 'hint', text: axisNote('slow') }),
    ]));
    box.appendChild(el('div', { class: 'comod-row' }, [
      el('span', { class: 'comod-axis', text: 'Amplitude' }),
      num('fast_lo', 'from', 'Lowest amplitude band', { step: 5, min: 5 }),
      num('fast_hi', 'to', 'Highest amplitude band', { step: 5, min: 10 }),
      num('fast_step', 'step', 'Spacing of the amplitude bands', { step: 1, min: 1 }),
      num('fast_bw', 'width', 'How wide each band is. newFCSE.m uses 10 Hz '
          + 'bands stepped by 5, so they overlap by half.', { step: 1, min: 1 }),
      el('span', { class: 'hint', text: axisNote('fast') }),
    ]));

    /* The thing a comodulogram axis never says about itself.

       eegfilt sets its order from the LOW cutoff, so what comes out is about
       0.30 * that wide however narrow the band asked for. A row labelled
       200 Hz is a 60 Hz slice of the spectrum. Somebody reading a peak off
       the amplitude axis to a nominal 10 Hz is reading six times more
       precision than exists. */
    box.appendChild(el('p', { class: 'hint comod-truth',
      text: 'Band edges are nominal. eegfilt designs its filter from the '
          + 'lower cutoff, so every band comes out about 0.30 × that wide — '
          + 'the ' + q.fast_hi + ' Hz amplitude row is roughly '
          + Math.round(0.3 * q.fast_hi) + ' Hz of spectrum, not '
          + q.fast_step + '. The map shows the measured widths once it has '
          + 'run.' }));

    // ---- surrogates ----
    box.appendChild(el('div', { class: 'section-label', text: 'Significance' }));
    box.appendChild(el('div', { class: 'comod-row' }, [
      el('label', { class: 'comod-check' }, [
        el('input', {
          type: 'checkbox', checked: q.nsurr ? 'checked' : null,
          onchange: (e) => {
            q.nsurr = e.target.checked ? q.surrN : 0;
            refreshEstimate(); render();
          },
        }),
        el('span', { text: 'Test it against a null' }),
      ]),
      q.nsurr ? el('label', { class: 'comod-field' }, [
        el('span', { text: 'surrogates' }),
        el('select', {
          onchange: (e) => { q.surrN = parseInt(e.target.value, 10);
                             q.nsurr = q.surrN; refreshEstimate(); render(); },
        }, [20, 50, 100, 200].map((n) => el('option', {
          value: n, text: String(n),
          title: 'The smallest p this can report is 1/' + (n + 1) + ' = '
               + (1 / (n + 1)).toFixed(3),
          selected: n === q.surrN ? 'selected' : null,
        }))),
      ]) : null,
      el('div', { style: 'flex:1' }),
      el('span', { class: 'comod-est', id: 'comodEst' }),
    ].filter(Boolean)));

    if (q.nsurr) {
      box.appendChild(el('p', { class: 'hint',
        text: 'Each cell is compared with ' + q.nsurr + ' versions of itself '
            + 'with the timing destroyed and everything else kept, and the '
            + 'map reports the permutation p. Not z: the beta run measured '
            + 'the null to be over-dispersed (SD 1.4, and it does not shrink '
            + 'with more surrogates), so a nominal z of 3 behaves like 2.2. '
            + 'The smallest p ' + q.nsurr + ' surrogates can report is '
            + (1 / (q.nsurr + 1)).toFixed(3) + '.' }));
    }

    box.appendChild(el('div', { class: 'comod-row comod-go' }, [
      el('button', {
        class: 'btn', text: job ? 'Running…' : 'Generate',
        disabled: job ? 'disabled' : null,
        onclick: run,
      }),
      est && est.cached ? el('span', { class: 'hint',
        text: 'Already computed — this will come straight back.' }) : null,
    ].filter(Boolean)));

    return box;
  }

  function axisNote(which) {
    const lo = q[which + '_lo'], hi = q[which + '_hi'], st = q[which + '_step'];
    const n = Math.max(Math.round((hi - lo) / st) + 1, 1);
    return n + ' band' + (n === 1 ? '' : 's');
  }

  function paintEstimate() {
    const box = document.getElementById('comodEst');
    if (!box) return;
    if (!est) { box.textContent = ''; return; }
    box.textContent = est.cells + ' cells'
      + (q.nsurr ? '  ·  ' + est.surrogate_runs.toLocaleString()
                   + ' modulation indices' : '')
      + '  ·  about ' + human(est.seconds);
    box.title = 'Estimated from what this machine measured on its last run, '
              + 'not from a table.';
  }

  function human(s) {
    if (s == null) return '';
    if (s < 1) return 'a moment';
    if (s < 60) return Math.round(s) + ' s';
    const m = Math.floor(s / 60);
    return m + ' min ' + Math.round(s - m * 60) + ' s';
  }

  /* ---------------- the stage list: the loading display ----------------

     Four rules, each of which is a way of not lying:

       * Every stage counts in its own unit. "23 / 37 bands" reads; "62%"
         hides that the next stage is 31,450 things and this one is 37.
       * The overall bar is weighted by measured cost, not by stage count.
         On a 100-surrogate run the surrogates are seven eighths of the work,
         so seven equal steps would sit at 71% with nearly everything left.
       * No estimate until there is something to estimate from, and then
         "about 19 s left" rather than a countdown that implies it knows.
       * Cancel is live throughout, and lands inside a tenth of a second.

     It stays on screen when the run finishes, with the times filled in, so
     what you watched becomes the receipt for where the time went.
     -------------------------------------------------------------------- */
  function stageCard() {
    const box = el('div', { class: 'card comod-run' });
    box.appendChild(el('div', { class: 'comod-run-head' }, [
      el('strong', { text: 'Generating comodulogram' }),
      el('span', { class: 'hint', text: runSubtitle() }),
      el('div', { style: 'flex:1' }),
      el('button', { class: 'btn ghost sm', text: 'Cancel', onclick: cancel }),
    ]));
    box.appendChild(el('div', { class: 'comod-stages', id: 'comodStages' }));
    box.appendChild(el('div', { class: 'comod-total' }, [
      el('div', { class: 'comod-bar' }, [
        el('div', { class: 'comod-bar-fill', id: 'comodBarFill' }),
      ]),
      el('span', { class: 'comod-eta', id: 'comodEta' }),
    ]));
    setTimeout(paintStages, 0);
    return box;
  }

  function runSubtitle() {
    const ch = (ctx.channels || []).find((c) => c.index === q.channel);
    const nS = Math.round((q.slow_hi - q.slow_lo) / q.slow_step) + 1;
    const nF = Math.round((q.fast_hi - q.fast_lo) / q.fast_step) + 1;
    return (ch ? ch.label : 'channel ' + q.channel)
         + '  ·  ' + q.t0.toFixed(1) + '–' + q.t1.toFixed(1) + ' s'
         + '  ·  ' + nS + ' × ' + nF
         + (q.nsurr ? '  ·  ' + q.nsurr + ' surrogates' : '');
  }

  /* How much of the whole run each stage is, by what it cost last time.
     Falls back to equal shares only when nothing has been measured. */
  function weights(stages) {
    const spent = stages.map((s) => s.seconds).filter((v) => v != null);
    const rate = {};
    for (const s of stages) if (s.seconds != null && s.of) rate[s.name] = s.seconds / s.of;
    // A stage still to run is costed from this run's own finished stages
    // where possible, otherwise from a rough shape: surrogates dominate.
    const ROUGH = { read: 0.5, decimate: 0.3, 'slow bank': 1.5,
                    'fast bank': 1.5, 'modulation index': 0.4,
                    surrogates: 20, draw: 0.3 };
    return stages.map((s) => {
      if (s.seconds != null) return s.seconds;
      if (rate[s.name]) return rate[s.name] * s.of;
      if (s.name === 'surrogates' && spent.length) {
        // Scale the rough guess by how this machine is doing on the bands.
        return ROUGH.surrogates * (s.of / 850);
      }
      return ROUGH[s.name] || 1;
    });
  }

  function paintStages() {
    const host = document.getElementById('comodStages');
    if (!host || !job) return;
    const stages = job.stages || [];
    const w = weights(stages);
    const total = w.reduce((a, b) => a + b, 0) || 1;
    let done = 0;

    host.innerHTML = '';
    stages.forEach((s, i) => {
      const running = s.status === 'running';
      const frac = s.of ? Math.min(s.done / s.of, 1) : 0;
      done += w[i] * (s.status === 'done' ? 1 : frac);

      host.appendChild(el('div', {
        class: 'comod-stage' + (running ? ' on' : '')
               + (s.status === 'done' ? ' done' : '')
               + (s.status === 'failed' ? ' bad' : ''),
      }, [
        el('span', { class: 'comod-tick',
          text: s.status === 'done' ? '✓'
                : running ? '▸'
                : s.status === 'failed' ? '✗' : '' }),
        el('span', { class: 'comod-stage-name', text: stageLabel(s) }),
        el('span', { class: 'comod-stage-count',
          // The denominator is always there, even before the stage starts:
          // knowing what is coming is half of knowing how long it will take.
          text: s.of > 1
            ? ((s.status === 'waiting' ? '–' : s.done.toLocaleString())
               + ' / ' + s.of.toLocaleString() + ' ' + s.unit)
            : '' }),
        running && s.of > 1
          ? el('div', { class: 'comod-mini' }, [
              el('div', { class: 'comod-mini-fill',
                          style: 'width:' + (frac * 100).toFixed(1) + '%' }),
            ])
          : null,
        el('span', { class: 'comod-stage-time',
          text: s.seconds != null ? s.seconds.toFixed(2) + ' s' : '' }),
      ].filter(Boolean)));
    });

    const fill = document.getElementById('comodBarFill');
    if (fill) fill.style.width = (100 * done / total).toFixed(1) + '%';
    const eta = document.getElementById('comodEta');
    if (eta) {
      eta.textContent = job.eta_s != null
        ? 'about ' + human(job.eta_s) + ' left'
        : (job.status === 'running' ? 'working out how long this will take'
                                    : '');
    }
  }

  function stageLabel(s) {
    const map = {
      'read': 'Read the window',
      'decimate': 'Decimate, anti-aliased',
      'slow bank': 'Phase bank  ' + q.slow_lo + '–'
                   + (q.slow_hi + (q.slow_bw || q.slow_step)) + ' Hz',
      'fast bank': 'Amplitude bank  ' + q.fast_lo + '–'
                   + (q.fast_hi + (q.fast_bw || q.fast_step)) + ' Hz',
      'modulation index': 'Modulation index',
      'surrogates': 'Surrogates ×' + q.nsurr,
      'draw': 'Draw',
    };
    return map[s.name] || s.name;
  }

  /* ---------------- the map ---------------- */
  function mapCard() {
    const m = maps[shown];
    const r = m.res;
    const box = el('div', { class: 'card comod-map' });

    box.appendChild(el('div', { class: 'comod-map-head' }, [
      el('strong', { text: 'Peak ' + r.peak.mi.toFixed(5) + ' at '
                         + r.peak.slow.toFixed(2) + ' Hz phase / '
                         + Math.round(r.peak.fast) + ' Hz amplitude' }),
      el('div', { style: 'flex:1' }),
      el('label', { class: 'comod-check',
        title: 'Hold the colour scale across every map in this window. Two '
             + 'maps drawn to their own maxima cannot be compared, and that '
             + 'is the commonest way a comodulogram misleads.' }, [
        el('input', {
          type: 'checkbox', checked: lockScale ? 'checked' : null,
          onchange: (e) => {
            lockScale = e.target.checked;
            lockedMax = lockScale ? Math.max.apply(null, maps.map((x) => x.res.max))
                                  : null;
            render();
          },
        }),
        el('span', { text: 'Lock scale' }),
      ]),
      el('select', {
        title: 'Sequential by default. A rainbow invents edges in smooth '
             + 'data, and a comodulogram is smooth data.',
        onchange: (e) => { q.cmap = e.target.value; render(); },
      }, colormapList().map((c) => el('option', {
        value: c.id, text: c.name, selected: c.id === q.cmap ? 'selected' : null,
      }))),
    ]));

    box.appendChild(el('div', { class: 'comod-canvas-wrap' }, [
      el('canvas', { class: 'comod-canvas', id: 'comodCanvas' }),
      el('div', { class: 'comod-readout', id: 'comodReadout' }),
    ]));

    box.appendChild(caption(m));

    if (maps.length > 1) {
      box.appendChild(el('div', { class: 'comod-strip' },
        maps.map((x, i) => el('button', {
          class: 'mini' + (i === shown ? ' on' : ''),
          title: x.res.t0.toFixed(1) + '–' + x.res.t1.toFixed(1) + ' s, '
               + x.res.channel.label + ', peak ' + x.res.max.toFixed(5),
          text: x.res.channel.label + ' ' + x.res.t0.toFixed(0) + 's',
          onclick: () => { shown = i; render(); },
        }))));
    }

    setTimeout(() => paintMap(m), 0);
    return box;
  }

  function colormapList() {
    // Until /api/panels has answered, the two that matter.
    return cmaps.length ? cmaps
      : [{ id: 'seqblue', name: 'Sequential blue' }, { id: 'jet', name: 'Jet' }];
  }

  function caption(m) {
    const r = m.res;
    const sw = r.slow.realised_bw, fw = r.fast.realised_bw;
    const bits = [
      r.channel.label,
      r.t0.toFixed(1) + '–' + r.t1.toFixed(1) + ' s (' + r.span.toFixed(1) + ' s, '
        + r.cycles + ' slow cycles)',
      r.slow.centers.length + ' × ' + r.fast.centers.length + ' cells',
      Math.round(r.fs_native) + '→' + Math.round(r.fs_used)
        + ' Hz anti-aliased',
      'phase bands ' + Math.min.apply(null, sw).toFixed(2) + '–'
        + Math.max.apply(null, sw).toFixed(2) + ' Hz wide',
      'amplitude bands ' + Math.min.apply(null, fw).toFixed(1) + '–'
        + Math.max.apply(null, fw).toFixed(1) + ' Hz wide',
      r.nsurr ? r.nsurr + ' surrogates, seed ' + r.seed : 'no null',
    ];
    const out = [el('p', { class: 'hint comod-caption', text: bits.join('  ·  ') })];

    // The number fig11 exists to make you look at.
    out.push(el('p', { class: 'hint',
      text: 'Largest modulation index on this map: ' + r.max.toFixed(5)
          + (lockScale && lockedMax != null && lockedMax !== r.max
             ? '  (drawn to ' + lockedMax.toFixed(5) + ', locked)' : '') }));

    if (r.nsurr) {
      const surprising = r.n_significant > r.expected_by_chance * 1.5;
      out.push(el('p', { class: 'hint' + (surprising ? '' : ' warn'),
        text: r.n_significant + ' of ' + r.n_cells + ' cells at p ≤ 0.05. '
            + 'Chance alone would give about ' + r.expected_by_chance + '. '
            + (surprising
               ? 'The outlined cells are the ones below 0.05.'
               : 'That is what an empty map looks like — read the outlines '
                 + 'with that in mind.') }));
    }
    if (m.stages) {
      out.push(el('p', { class: 'hint',
        text: 'Took ' + m.elapsed + ' s: '
            + m.stages.filter((s) => s.seconds > 0.05)
                .map((s) => s.name + ' ' + s.seconds.toFixed(1) + 's')
                .join(', ') + '.' }));
    }
    return el('div', {}, out);
  }

  /* Drawn from the numbers, not shown as the server's PNG.

     629 floats is less than the picture of them, and once the browser has
     them, changing the scale or the colormap or reading a cell under the
     cursor costs nothing and asks nothing. Given that the whole hazard here
     is a scale nobody questioned, making the scale free to change is the
     point. Cells are drawn as cells: 17 x 37 is what was measured, and
     contourf's smooth blobs imply a resolution the 0.5 Hz phase axis (whose
     filters are 1-3.5 Hz wide) does not have. */
  const PAD = { l: 58, r: 16, t: 12, b: 44 };

  function paintMap(m) {
    const cv = document.getElementById('comodCanvas');
    if (!cv) return;
    const r = m.res;
    const dpr = window.devicePixelRatio || 1;
    const rect = cv.getBoundingClientRect();
    const w = Math.max(rect.width, 320), h = Math.max(rect.height, 240);
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);

    const cs = getComputedStyle(document.documentElement);
    const pick = (n, fb) => (cs.getPropertyValue(n) || fb).trim();
    const ink = pick('--text-2', '#555');
    const line = pick('--line', '#ccc');

    g.clearRect(0, 0, w, h);

    const nS = r.slow.centers.length, nF = r.fast.centers.length;
    const plotW = w - PAD.l - PAD.r, plotH = h - PAD.t - PAD.b;
    const cw = plotW / nS, ch = plotH / nF;
    const top = (lockScale && lockedMax != null) ? lockedMax : r.max;
    const ramp = rampFor(q.cmap);

    for (let j = 0; j < nS; j++) {
      for (let i = 0; i < nF; i++) {
        const v = r.mi[j][i];
        g.fillStyle = colorOf(ramp, top > 0 ? v / top : 0);
        // Amplitude up the side, low at the bottom -- the orientation every
        // comodulogram in this repo is drawn in.
        g.fillRect(PAD.l + j * cw, PAD.t + (nF - 1 - i) * ch,
                   Math.ceil(cw) + 0.5, Math.ceil(ch) + 0.5);
      }
    }

    // Cells the null says are unusual. Outlined rather than filled: the
    // colour is already carrying the magnitude, and hiding it behind a
    // significance mask throws away the thing being tested.
    if (r.p) {
      g.strokeStyle = pick('--text', '#111');
      g.lineWidth = 1;
      for (let j = 0; j < nS; j++) {
        for (let i = 0; i < nF; i++) {
          if (r.p[j][i] <= 0.05) {
            g.strokeRect(PAD.l + j * cw + 0.5,
                         PAD.t + (nF - 1 - i) * ch + 0.5,
                         cw - 1, ch - 1);
          }
        }
      }
    }

    // Axes.
    g.strokeStyle = line;
    g.lineWidth = 1;
    g.strokeRect(PAD.l + 0.5, PAD.t + 0.5, plotW - 1, plotH - 1);
    g.fillStyle = ink;
    g.font = '10.5px ui-monospace, Consolas, monospace';
    g.textAlign = 'center';
    g.textBaseline = 'top';
    /* Two decimals when the centres are quarters. A 0.5 Hz grid puts them
       on 4.25, 5.25, 6.25, and rounding those to one place printed
       "4.3, 5.3, 6.3" -- which reads as a rounding artefact rather than as
       the band centres they are. */
    const quarters = r.slow.centers.some((v) => Math.abs(v * 10 % 1) > 1e-6);
    for (let j = 0; j < nS; j += Math.ceil(nS / 9)) {
      g.fillText(r.slow.centers[j].toFixed(quarters ? 2 : 1),
                 PAD.l + (j + 0.5) * cw, PAD.t + plotH + 6);
    }
    g.textAlign = 'right';
    g.textBaseline = 'middle';
    for (let i = 0; i < nF; i += Math.ceil(nF / 8)) {
      g.fillText(String(Math.round(r.fast.centers[i])), PAD.l - 7,
                 PAD.t + (nF - 1 - i + 0.5) * ch);
    }
    g.textAlign = 'center';
    g.textBaseline = 'bottom';
    g.fillText('phase frequency (Hz)', PAD.l + plotW / 2, h - 4);
    g.save();
    g.translate(11, PAD.t + plotH / 2);
    g.rotate(-Math.PI / 2);
    g.fillText('amplitude frequency (Hz)', 0, 0);
    g.restore();

    if (hover) markHover(g, r, cw, ch, nF);

    cv.onmousemove = (e) => {
      const b = cv.getBoundingClientRect();
      const j = Math.floor((e.clientX - b.left - PAD.l) / cw);
      const i = nF - 1 - Math.floor((e.clientY - b.top - PAD.t) / ch);
      hover = (j >= 0 && j < nS && i >= 0 && i < nF) ? { j, i } : null;
      paintMap(m);
      readout(r);
    };
    cv.onmouseleave = () => { hover = null; paintMap(m); readout(r); };
  }

  function markHover(g, r, cw, ch, nF) {
    g.strokeStyle = '#fff';
    g.lineWidth = 2;
    g.strokeRect(PAD.l + hover.j * cw, PAD.t + (nF - 1 - hover.i) * ch, cw, ch);
    g.strokeStyle = '#000';
    g.lineWidth = 1;
    g.strokeRect(PAD.l + hover.j * cw - 1, PAD.t + (nF - 1 - hover.i) * ch - 1,
                 cw + 2, ch + 2);
  }

  function readout(r) {
    const box = document.getElementById('comodReadout');
    if (!box) return;
    if (!hover) {
      box.textContent = 'Hover a cell for its numbers.';
      return;
    }
    const { j, i } = hover;
    const bits = [
      r.slow.centers[j].toFixed(2) + ' Hz phase '
        + '(' + r.slow.realised_bw[j].toFixed(2) + ' Hz wide)',
      Math.round(r.fast.centers[i]) + ' Hz amplitude '
        + '(' + r.fast.realised_bw[i].toFixed(1) + ' Hz wide)',
      'MI ' + r.mi[j][i].toFixed(5),
    ];
    if (r.p) {
      bits.push('p ' + (r.p[j][i] <= r.p_floor
        ? '≤ ' + r.p_floor.toFixed(3) : r.p[j][i].toFixed(3)));
    }
    box.textContent = bits.join('   ·   ');
  }

  /* A colour ramp, from the server's swatch where there is one so the canvas
     and the exported PNG of the same map agree. */
  const FALLBACK = {
    seqblue: ['#fcfcfb', '#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5',
              '#256abf', '#184f95', '#0d366b'],
    jet: ['#00007f', '#0000ff', '#007fff', '#00ffff', '#7fff7f',
          '#ffff00', '#ff7f00', '#ff0000', '#7f0000'],
  };

  /* The sequential ramp was designed against the explainer's paper-white
     figure surface, where "near zero" being almost white is right: the empty
     part of the map disappears into the page. Dropped unchanged onto this
     app's dark theme it does the opposite -- a map with little coupling in
     it is a bright white slab, which reads as a hole rather than as nothing,
     and inverts the one thing a sequential ramp is for (more ink = more).

     So in a dark theme the same single hue is walked the other way, from the
     pane's own background up to the brightest blue. Light theme keeps the
     published ramp exactly, because that is the one the figures use.

     Only the single-hue maps are treated this way. Flipping `jet` would make
     it a different colormap, and somebody choosing jet is choosing the thing
     the old figures were drawn in. */
  function isDark() {
    const bg = getComputedStyle(document.documentElement)
      .getPropertyValue('--bg') || '';
    const m = bg.trim().match(/^#([0-9a-f]{6})$/i);
    if (!m) return true;                 // this app is dark by default
    const v = parseInt(m[1], 16);
    // Rec. 601 luma, which is close enough to decide light from dark.
    return (0.299 * ((v >> 16) & 255) + 0.587 * ((v >> 8) & 255)
            + 0.114 * (v & 255)) < 128;
  }

  function rampFor(id) {
    const got = cmaps.find((c) => c.id === id);
    let ramp = (got && got.swatch && got.swatch.length)
      ? got.swatch : (FALLBACK[id] || FALLBACK.seqblue);
    if (id === 'seqblue' && isDark()) {
      const bg = (getComputedStyle(document.documentElement)
        .getPropertyValue('--bg') || '#0a1310').trim();
      // Reversed, and the empty end replaced by the surface it sits on, so
      // "no coupling here" looks like the background rather than like paint.
      ramp = [bg].concat(ramp.slice().reverse().slice(1));
    }
    return ramp;
  }

  function colorOf(ramp, frac) {
    if (!isFinite(frac)) return ramp[0];
    const f = Math.max(0, Math.min(1, frac)) * (ramp.length - 1);
    const i = Math.floor(f);
    const t = f - i;
    const a = hex(ramp[i]), b = hex(ramp[Math.min(i + 1, ramp.length - 1)]);
    return 'rgb(' + Math.round(a[0] + (b[0] - a[0]) * t) + ','
                  + Math.round(a[1] + (b[1] - a[1]) * t) + ','
                  + Math.round(a[2] + (b[2] - a[2]) * t) + ')';
  }

  function hex(s) {
    const v = parseInt(String(s).replace('#', ''), 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  }

  return { onShow, render, openerMoved, run,
           get maps() { return maps; } };
}());

/* The handle CFCScope calls into when the window moves. A property, because
   the module object itself is reached through a `const` that no other window
   can see. See `opener()` above for the whole story. */
window.barryComod = BARRY.views.comod;
