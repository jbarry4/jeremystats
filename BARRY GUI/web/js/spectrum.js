/* ==========================================================================
   spectrum.js -- power against frequency, for a whole recording.

   Braid's third window, after the panels and the comodulogram, and the one
   that answers the question the other two dance around. Theta is always
   there; every recording has something between 4 and 12 Hz. What varies is
   how MUCH, and against what else -- so the useful picture is not a band
   filtered out and drawn as a raster, it is the whole spectrum with the band
   marked on it, and a number beside the curve saying what fraction of the
   power sits inside it.

   Three things this is built around:

     * **Whole recordings first.** The spectrogram already shows a window
       changing over time. This one shows a session as a single shape. The
       time control exists so a window can be cut out of it afterwards, not
       because a window is the default.

     * **Many channels at once.** A rhythm that grows down a shank is a fact
       about the shank, and it is invisible one channel at a time. So the
       picker here is the one XploreFinder uses -- every 2, every 4, odd,
       even, good only -- and the lines are coloured by depth rather than by
       a categorical palette, because the order of the lines IS the finding.

     * **Log on both axes.** Neural power falls off as roughly 1/f, so on
       linear axes every recording is a spike at DC and a flat line, and
       theta is a bump three pixels tall. On log-log the 1/f slope is
       straight and a rhythm is a hill standing off it, which is the thing
       being looked for.

   The loading display is a real part of this, not a courtesy. A whole
   recording across sixteen channels is a billion samples and takes the better
   part of a minute, and a minute of spinner is indistinguishable from a
   minute of hung. So it says what it is doing, in units, with the numbers
   that make the wait make sense -- and it says what was done to the data
   before the transform, which is the difference between a plot and a claim.
   ========================================================================== */
'use strict';

BARRY.views.spectrum = (function () {
  /* What we are about to ask for. Held here rather than read off the DOM so
     a re-render cannot lose a half-filled form. */
  const q = {
    channels: [],       // indices, in shank order
    t0: 0, t1: 0,
    whole: true,        // the whole recording, whatever its length turns out
    /* 200 Hz. Above that is spike band and mains harmonics, and asking for
       it costs a factor of the sample rate in reading. Offered, because
       somebody looking at ripples wants 300. */
    fmax: 200,
    /* 8 s segments at 500 Hz is 0.125 Hz bins -- theta resolved into about
       sixty of them rather than one. Longer buys resolution and costs the
       number of segments there are to average over, which is the whole
       trade in Welch's method and is worth exposing. */
    segment_s: 8,
  };

  let ctx = null;        // the opener's live state
  let est = null;        // what a run would cost, before it is asked for
  let job = null;        // the run in flight
  let poll = null;
  let res = null;        // the finished spectrum
  let ranAs = null;      // the job it came out of, for the receipt
  let hidden = new Set();  // channels toggled off in the legend
  let hover = null;      // {hz, index} under the cursor
  let logY = true;
  let pickOpen = false;  // the channel list, folded away until wanted

  /* ==================================================================
     Talking to the window that opened us
     ================================================================== */
  /* `barryCfc`, not `BARRY.cfc`. `BARRY` is a `const` in core.js, which
     makes it a lexical binding and NOT a property of `window`, so
     `opener.BARRY` is undefined however completely the opener has loaded.
     Each side publishes the one handle the other needs as a real property.
     See the same note in comod.js, which learned it the hard way. */
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
    /* A different recording is a different question, not a moved window.
       Without this, opening another session in Braid left this window
       holding the first one's channel numbers and time span and quietly
       computing them against the new file. */
    const first = !ctx || ctx.path !== got.path;
    const swapped = ctx && ctx.path !== got.path;
    ctx = got;
    if (swapped) { res = null; hidden = new Set(); hover = null; }
    if (first) {
      /* Opening on the whole recording, because that is what this view is
         for. The window on screen is one sweep of a thirty-five minute
         session and its spectrum is a noisier version of the same shape. */
      q.t0 = 0;
      q.t1 = ctx.duration || ctx.t1 || 0;
      q.whole = true;
      q.channels = defaultChannels();
    }
    if (force) refreshEstimate();
    return true;
  }

  /* Whatever XploreFinder has selected, or the first good channel. Never all
     sixty-four by default: that is a minute of work nobody asked for, and a
     plot of sixty-four lines is not a first look at anything. */
  function defaultChannels() {
    const sel = (ctx.selection || []).slice().sort((a, b) => a - b);
    if (sel.length) return sel;
    const good = (ctx.channels || []).filter((c) => !c.bad);
    return good.length ? [good[0].index] : [0];
  }

  /* Called by Braid whenever the view moves. The window fields only follow
     it while `whole` is off -- a whole-recording plot has nothing to follow
     and re-estimating on every scroll would be noise. */
  function openerMoved() {
    const was = ctx && ctx.path;
    if (!pullContext()) return;
    // A swap has to redraw whatever `whole` says; only a moved window
    // inside the same recording is ignorable while showing all of it.
    if (job) return;
    if (was !== ctx.path || !q.whole) { refreshEstimate(); render(); }
  }

  /* ==================================================================
     Loading
     ================================================================== */
  function onShow() {
    if (!pullContext(true)) { render(); return; }
    render();
  }

  function body() {
    return {
      path: ctx.path,
      even_only: ctx.evenOnly,
      invert: ctx.invert,
      channels: q.channels,
      t0: q.whole ? 0 : q.t0,
      t1: q.whole ? (ctx.duration || 0) : q.t1,
      fmax: q.fmax,
      segment_s: q.segment_s,
    };
  }

  let estSeq = 0;
  async function refreshEstimate() {
    if (!ctx || !q.channels.length) { est = null; paintEstimate(); return; }
    const mine = ++estSeq;
    try {
      const got = await apiPost('/api/spectrum/estimate', body());
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
    if (!q.channels.length) {
      toast('Pick at least one channel.', 'warn');
      return;
    }
    let started;
    try {
      started = await apiPost('/api/spectrum/run', body());
    } catch (e) {
      toast(e.message, 'err', 9000);
      return;
    }
    if (started.cached) {
      // Already computed, this session. Straight to the picture: the whole
      // point of the cache is that comparing two windows means going back.
      res = started.result;
      ranAs = null;
      hidden = new Set();
      render();
      return;
    }
    job = started.job;
    render();
    watch();
  }

  function watch() {
    clearInterval(poll);
    /* 300 ms. A minute-long run is 200 requests and each answer is a dict
       lookup, and the slowest stage here moves several times a second. */
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
          const out = await api('/api/cfc/result/' + finished.id);
          res = out.result;
          ranAs = finished;
          hidden = new Set();
        } catch (e) {
          toast('The run finished but the result could not be read: '
                + e.message, 'err', 9000);
        }
      } else if (finished.status === 'failed') {
        toast(finished.error || 'The run failed.', 'err', 10000);
      }
      render();
    }, 300);
  }

  async function cancel() {
    if (!job) return;
    try { await apiPost('/api/cfc/job/' + job.id + '/cancel', {}); } catch (e) {}
  }

  /* ==================================================================
     Rendering
     ================================================================== */
  function render() {
    const host = document.getElementById('spectrumBody');
    if (!host) return;
    host.innerHTML = '';

    if (!ctx) {
      host.appendChild(el('div', { class: 'card' }, [
        el('p', { text: 'This window is opened from Braid, and it reads the '
                      + 'recording and the channels from it.' }),
        el('p', { class: 'hint',
          text: 'The window that opened this one has gone. Open Braid again '
              + 'from the Toolkit and press P.' }),
      ]));
      return;
    }

    host.appendChild(formCard());
    if (job) host.appendChild(stageCard());
    if (res) host.appendChild(plotCard());
  }

  /* ---------------- the form ---------------- */
  function formCard() {
    const box = el('div', { class: 'card comod-form' });
    box.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: 'What to measure' }));
    box.appendChild(el('p', { class: 'hint', style: 'margin:0 0 10px',
      text: (ctx.label || ctx.path) + '  ·  '
          + fmtDur(ctx.duration || 0) + ' at '
          + (ctx.fs || 0).toLocaleString() + ' Hz  ·  '
          + (ctx.channels || []).length + ' channels' }));

    box.appendChild(windowRow());
    box.appendChild(channelRow());
    if (pickOpen) box.appendChild(channelList());
    box.appendChild(bandRow());

    box.appendChild(el('div', { class: 'comod-go' }, [
      el('button', {
        class: 'btn', text: job ? 'Running…' : 'Compute the spectrum',
        disabled: job ? 'disabled' : null, onclick: run,
      }),
      el('span', { class: 'comod-est', id: 'psdEst' }),
    ]));
    setTimeout(paintEstimate, 0);
    return box;
  }

  /* ---- where in time ---- */
  function windowRow() {
    const viewSpan = (ctx.t1 || 0) - (ctx.t0 || 0);
    return el('div', { class: 'comod-row' }, [
      el('div', { class: 'psd-seg' }, [
        el('button', {
          class: 'btn ghost sm' + (q.whole ? ' on' : ''),
          text: 'Whole recording',
          title: 'Every second of it. This is what the view is for: a '
               + 'session as one shape.',
          onclick: () => { q.whole = true; refreshEstimate(); render(); },
        }),
        el('button', {
          class: 'btn ghost sm' + (q.whole ? '' : ' on'),
          text: 'A window',
          title: 'Cut a stretch out of it — a run down the track, a rest, '
               + 'the ten minutes before a seizure.',
          onclick: () => {
            if (q.whole && viewSpan > 0) { q.t0 = ctx.t0; q.t1 = ctx.t1; }
            q.whole = false; refreshEstimate(); render();
          },
        }),
      ]),
      q.whole ? el('span', { class: 'hint',
        text: fmtDur(ctx.duration || 0) + ', start to finish' }) : null,
      q.whole ? null : num('t0', 'From (s)', 'Start of the window',
                           { step: 0.5, min: 0 }),
      q.whole ? null : num('t1', 'To (s)', 'End of the window',
                           { step: 0.5, min: 0 }),
      q.whole || viewSpan <= 0 ? null : el('button', {
        class: 'btn ghost sm', text: 'Use the view',
        title: 'Put XploreFinder’s window in these fields: '
             + ctx.t0.toFixed(1) + '–' + ctx.t1.toFixed(1) + ' s.',
        onclick: () => { q.t0 = round2(ctx.t0); q.t1 = round2(ctx.t1);
                         refreshEstimate(); render(); },
      }),
    ].filter(Boolean));
  }

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
          refreshEstimate();
          render();
        },
      }),
    ]);
  }

  /* ---- which channels ----

     The same set of quick picks XploreFinder offers, and for the same
     reasons. `stride` walks the good channels rather than all of them, so a
     dead site does not silently shift the spacing of an "every 4"; `parity`
     is on the CSC number, because on this rig the probe sits on the even
     ones and "odd" is the reference set. */
  function stride(n) {
    const good = (ctx.channels || []).filter((c) => !c.bad);
    q.channels = good.filter((c, i) => i % n === 0).map((c) => c.index);
  }

  function parity(want) {
    q.channels = (ctx.channels || [])
      .filter((c) => (c.number % 2) === want).map((c) => c.index);
  }

  function quick(label, fn, title) {
    return el('button', {
      class: 'btn ghost sm', text: label, title: title,
      onclick: () => { fn(); refreshEstimate(); render(); },
    });
  }

  function channelRow() {
    const sel = q.channels.length;
    return el('div', { class: 'psd-picks' }, [
      el('button', {
        class: 'btn ghost sm', onclick: () => { pickOpen = !pickOpen; render(); },
        text: (pickOpen ? '▾ ' : '▸ ') + sel + ' channel'
              + (sel === 1 ? '' : 's') + ' selected',
        title: 'The list, one by one.',
      }),
      quick('All', () => {
        q.channels = (ctx.channels || []).map((c) => c.index);
      }, 'Every channel in the recording. On a 64-site probe over a whole '
       + 'session this is real work — the estimate below will say how much.'),
      quick('None', () => { q.channels = []; }),
      quick('Every 2', () => stride(2), 'Every second good channel.'),
      quick('Every 4', () => stride(4), 'Every fourth good channel — enough '
        + 'to see a gradient down the shank without sixty-four lines.'),
      quick('Every 8', () => stride(8)),
      quick('Every 16', () => stride(16)),
      quick('Odd', () => parity(1), 'Odd CSC numbers.'),
      quick('Even', () => parity(0), 'Even CSC numbers — the probe sits on '
        + 'these on this rig.'),
      quick('Good only', () => {
        q.channels = (ctx.channels || []).filter((c) => !c.bad)
          .map((c) => c.index);
      }, 'Everything not marked bad.'),
      (ctx.selection || []).length ? quick('Session selection', () => {
        q.channels = (ctx.selection || []).slice().sort((a, b) => a - b);
      }, 'Whatever XploreFinder has selected right now.') : null,
    ].filter(Boolean));
  }

  function channelList() {
    const chosen = new Set(q.channels);
    return el('div', { class: 'psd-chanlist' },
      (ctx.channels || []).map((c) => el('label', {
        class: 'psd-chan' + (c.bad ? ' bad' : ''),
        title: c.bad ? 'Marked bad. Included if you ask, and drawn dashed.'
                     : '',
      }, [
        el('input', {
          type: 'checkbox', checked: chosen.has(c.index) ? 'checked' : null,
          onchange: (e) => {
            if (e.target.checked) chosen.add(c.index); else chosen.delete(c.index);
            q.channels = Array.from(chosen).sort((a, b) => a - b);
            refreshEstimate();
            // The list itself is not rebuilt: a re-render on every tick
            // would lose the scroll position halfway down sixty-four rows.
            const b = document.querySelector('.psd-picks .btn');
            if (b) {
              b.textContent = (pickOpen ? '▾ ' : '▸ ') + q.channels.length
                + ' channel' + (q.channels.length === 1 ? '' : 's')
                + ' selected';
            }
          },
        }),
        el('span', { text: c.label }),
      ])));
  }

  /* ---- the band and the resolution ---- */
  function bandRow() {
    return el('div', { class: 'comod-row' }, [
      el('label', { class: 'comod-field',
        title: 'The top of the band worth computing. Everything above it is '
             + 'thrown away before the transform, which is what makes a '
             + 'whole recording tractable — so asking for more costs '
             + 'proportionally more reading.' }, [
        el('span', { text: 'Up to (Hz)' }),
        el('select', {
          onchange: (e) => { q.fmax = parseFloat(e.target.value);
                             refreshEstimate(); render(); },
        }, [50, 100, 200, 300, 500].map((v) => el('option', {
          value: v, text: v + ' Hz', selected: v === q.fmax ? 'selected' : null,
        }))),
      ]),
      el('label', { class: 'comod-field',
        title: 'Welch cuts the recording into segments and averages their '
             + 'periodograms. Longer segments resolve frequency more finely '
             + 'and there are fewer of them to average, so the curve is '
             + 'sharper and noisier. Shorter is smoother and blunter.' }, [
        el('span', { text: 'Segment (s)' }),
        el('select', {
          onchange: (e) => { q.segment_s = parseFloat(e.target.value);
                             refreshEstimate(); render(); },
        }, [2, 4, 8, 16, 32].map((v) => el('option', {
          value: v, text: v + ' s', selected: v === q.segment_s ? 'selected' : null,
        }))),
      ]),
      el('span', { class: 'hint', id: 'psdRes', style: 'align-self:flex-end' }),
    ]);
  }

  function paintEstimate() {
    const node = document.getElementById('psdEst');
    const resNode = document.getElementById('psdRes');
    if (resNode && est && est.plan) {
      const p = est.plan;
      resNode.textContent = p.resolution_hz.toFixed(3) + ' Hz bins, '
        + p.segments_per_channel.toLocaleString() + ' segments averaged';
    }
    if (!node) return;
    if (!q.channels.length) { node.textContent = 'No channels selected.'; return; }
    if (!est || !est.plan) { node.textContent = ''; return; }
    const p = est.plan;
    node.textContent = est.cached
      ? 'Already computed — this will be instant.'
      : (fmtDur(p.span_s) + ' × ' + p.n_channels + ' channel'
         + (p.n_channels === 1 ? '' : 's') + '  ·  '
         + Math.round(p.megasamples).toLocaleString() + ' million samples  ·  '
         + 'about ' + human(p.seconds)
         /* Which disk, when it is not this one. Worth a few words because
            the estimate is built from a rate measured on that disk, so a
            wait somebody can account for is a different wait from one they
            cannot. */
         + (p.network ? '  ·  over the network' : ''));
  }

  /* ---------------- the loading display ----------------

     Not a spinner. A whole recording across sixteen channels is the better
     part of a minute, and a minute of spinner is indistinguishable from a
     minute of hung. So: the stages, in their own units, with the numbers
     that make the wait make sense. */
  function stageCard() {
    const p = (est && est.plan) || {};
    const box = el('div', { class: 'card comod-run' });
    box.appendChild(el('div', { class: 'comod-run-head' }, [
      el('strong', { text: 'Computing the power spectrum' }),
      el('span', { class: 'hint', text: runSubtitle() }),
      el('div', { style: 'flex:1' }),
      el('button', { class: 'btn ghost sm', text: 'Cancel', onclick: cancel }),
    ]));
    box.appendChild(el('div', { class: 'comod-stages', id: 'psdStages' }));
    box.appendChild(el('div', { class: 'comod-total' }, [
      el('div', { class: 'comod-bar' }, [
        el('div', { class: 'comod-bar-fill', id: 'psdBarFill' }),
      ]),
      el('span', { class: 'comod-eta', id: 'psdEta' }),
    ]));
    /* Why it takes as long as it does, in the words that make the number
       reasonable rather than alarming. Somebody who knows a recording is a
       billion samples does not mind waiting forty seconds for it. */
    if (p.fs) {
      box.appendChild(el('p', { class: 'hint psd-why',
        text: 'Reading ' + fmtDur(p.span_s) + ' on ' + p.n_channels
            + ' channel' + (p.n_channels === 1 ? '' : 's') + ' at '
            + p.fs.toLocaleString() + ' Hz — '
            + Math.round(p.megasamples).toLocaleString() + ' million samples. '
            + (p.decimate > 1
                ? 'Each 120-second chunk is low-passed and decimated '
                  + p.decimate + '× to ' + Math.round(p.fs_used) + ' Hz as it '
                  + 'arrives, so the whole recording never has to be in '
                  + 'memory at once and the arithmetic is done on '
                  + Math.round(p.megasamples / p.decimate).toLocaleString()
                  + ' million samples instead. '
                : '')
            + 'The periodograms of '
            + p.segments_per_channel.toLocaleString() + ' segments per '
            + 'channel are then averaged, which is what makes the curve '
            + 'readable rather than noise.'
            + (p.network
                ? '  This one is on ' + p.volume + ' rather than a local '
                  + 'disk, which costs about half as much again in reading.'
                : '') }));
    }
    setTimeout(paintStages, 0);
    return box;
  }

  function runSubtitle() {
    const n = q.channels.length;
    return (q.whole ? 'whole recording'
                    : q.t0.toFixed(1) + '–' + q.t1.toFixed(1) + ' s')
         + '  ·  ' + n + ' channel' + (n === 1 ? '' : 's')
         + '  ·  1–' + q.fmax + ' Hz';
  }

  /* How much of the run each stage is. Reading is nearly all of it here --
     the transforms are interleaved with it to keep memory bounded, so the
     `spectrum` stage is a count of channels finished and not a phase with a
     duration of its own. A bar that gave it a third would sit at 66% and
     then jump. */
  const WEIGHT = { 'spectrum read': 40, spectrum: 1 };

  function paintStages() {
    const host = document.getElementById('psdStages');
    if (!host || !job) return;
    const stages = job.stages || [];
    const w = stages.map((s) => WEIGHT[s.name] || 1);
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

    const fill = document.getElementById('psdBarFill');
    if (fill) fill.style.width = (100 * done / total).toFixed(1) + '%';
    const eta = document.getElementById('psdEta');
    if (eta) {
      eta.textContent = job.eta_s != null
        ? 'about ' + human(job.eta_s) + ' left'
        : (job.status === 'running' ? 'working out how long this will take'
                                    : '');
    }
  }

  function stageLabel(s) {
    const p = (est && est.plan) || {};
    if (s.name === 'spectrum read') {
      return p.decimate > 1
        ? 'Read and decimate to ' + Math.round(p.fs_used) + ' Hz'
        : 'Read the recording';
    }
    if (s.name === 'spectrum') return 'Average the periodograms';
    return s.name;
  }

  /* ==================================================================
     The plot
     ================================================================== */
  function plotCard() {
    const box = el('div', { class: 'card' });
    box.appendChild(el('div', { class: 'comod-map-head' }, [
      el('strong', { text: 'Power spectral density' }),
      el('span', { class: 'hint', text: plotSubtitle() }),
      el('div', { style: 'flex:1' }),
      el('button', {
        class: 'btn ghost sm' + (logY ? ' on' : ''), text: 'Log power',
        title: 'Neural power falls off as roughly 1/f, so on a linear axis '
             + 'every recording is a spike at DC and a flat line. On log it '
             + 'is a straight slope with the rhythms standing off it.',
        onclick: () => { logY = !logY; render(); },
      }),
      el('button', {
        class: 'btn ghost sm', text: 'Copy the numbers',
        title: 'The whole table — frequency and one column per channel — as '
             + 'tab-separated text, for a paper figure or a t-test.',
        onclick: copyNumbers,
      }),
    ]));

    const wrap = el('div', { class: 'psd-canvas-wrap' }, [
      el('canvas', { class: 'psd-canvas', id: 'psdCanvas' }),
      el('div', { class: 'psd-readout', id: 'psdReadout' }),
    ]);
    box.appendChild(wrap);
    box.appendChild(legend());
    box.appendChild(bandTable());
    box.appendChild(samplingNote());
    setTimeout(() => { sizeCanvas(); draw(); paintReadout(); }, 0);
    return box;
  }

  function plotSubtitle() {
    const p = res.plan || {};
    return fmtDur(p.span_s || 0) + '  ·  ' + res.n_ok + ' channel'
         + (res.n_ok === 1 ? '' : 's') + '  ·  '
         + (p.resolution_hz || 0).toFixed(3) + ' Hz bins'
         + (ranAs ? '  ·  computed in ' + human(ranAs.elapsed) : '');
  }

  /* ---- colour ----

     A sequential ramp down the shank, not a categorical palette. These
     channels are in depth order and the question is almost always whether
     something changes with depth, so the colour has to carry that order. A
     rainbow of sixty-four distinguishable hues would carry nothing.

     Viridis, at eight stops, interpolated. Perceptually even and readable
     in greyscale, which the printed version will be. */
  const RAMP = [
    [68, 1, 84], [72, 40, 120], [62, 74, 137], [49, 104, 142],
    [38, 130, 142], [31, 158, 137], [53, 183, 121], [109, 205, 89],
    [180, 222, 44], [253, 231, 37],
  ];

  function colourAt(f) {
    const x = Math.max(0, Math.min(1, f)) * (RAMP.length - 1);
    const i = Math.min(RAMP.length - 2, Math.floor(x));
    const t = x - i;
    const a = RAMP[i], b = RAMP[i + 1];
    return 'rgb(' + Math.round(a[0] + (b[0] - a[0]) * t) + ','
                  + Math.round(a[1] + (b[1] - a[1]) * t) + ','
                  + Math.round(a[2] + (b[2] - a[2]) * t) + ')';
  }

  function drawn() {
    return (res.channels || [])
      .filter((c) => c.psd && !hidden.has(c.index));
  }

  function colourOf(row) {
    const all = res.channels || [];
    if (all.length < 2) return colourAt(0.5);
    const i = all.findIndex((c) => c.index === row.index);
    return colourAt(i / (all.length - 1));
  }

  function sizeCanvas() {
    const cv = document.getElementById('psdCanvas');
    if (!cv) return;
    const w = Math.max(320, cv.parentNode.clientWidth);
    const h = Math.max(260, Math.min(560, Math.round(w * 0.5)));
    const dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    cv.style.width = w + 'px';
    cv.style.height = h + 'px';
    cv.onmousemove = onHover;
    cv.onmouseleave = () => { hover = null; draw(); paintReadout(); };
  }

  const PAD = { l: 62, r: 14, t: 12, b: 34 };

  function axes() {
    const cv = document.getElementById('psdCanvas');
    // A resize or a hover can land after the card has been replaced.
    if (!cv || !res) return null;
    const dpr = window.devicePixelRatio || 1;
    const W = cv.width / dpr, H = cv.height / dpr;
    const rows = drawn();
    const f = res.freqs || [];
    const fLo = Math.max(0.5, f.length ? f[0] : 1);
    const fHi = f.length ? f[f.length - 1] : 200;

    let lo = Infinity, hi = -Infinity;
    for (const r of rows) {
      for (const v of r.psd) {
        if (v > 0 && v < lo) lo = v;
        if (v > hi) hi = v;
      }
    }
    if (!isFinite(lo) || !isFinite(hi) || hi <= 0) { lo = 1e-3; hi = 1; }
    /* Floor the bottom five decades below the peak. A recording with one
       dead sample decade would otherwise stretch the axis over twelve of
       them and flatten everything that matters into the top inch. */
    lo = Math.max(lo, hi / 1e5);

    const x = (hz) => PAD.l + (Math.log10(Math.max(hz, fLo)) - Math.log10(fLo))
      / (Math.log10(fHi) - Math.log10(fLo)) * (W - PAD.l - PAD.r);
    const y = logY
      ? (v) => PAD.t + (Math.log10(hi) - Math.log10(Math.max(v, lo)))
          / (Math.log10(hi) - Math.log10(lo)) * (H - PAD.t - PAD.b)
      : (v) => PAD.t + (hi - Math.max(v, 0)) / hi * (H - PAD.t - PAD.b);
    return { cv, dpr, W, H, rows, fLo, fHi, lo, hi, x, y };
  }

  function draw() {
    const cv = document.getElementById('psdCanvas');
    if (!cv || !res) return;
    const A = axes();
    if (!A) return;
    const g = cv.getContext('2d');
    g.setTransform(A.dpr, 0, 0, A.dpr, 0, 0);
    g.clearRect(0, 0, A.W, A.H);

    const ink = BARRY.token('--text', '#222');
    const faint = BARRY.token('--border', '#ddd');
    const dim = BARRY.token('--text-3', '#888');

    // ---- the bands, shaded, behind everything ----
    /* Theta filled, the rest ruled. The named bands are the reason somebody
       opened this, and a band you have to find by reading the axis is a
       band that is not marked. */
    for (const b of (res.bands || [])) {
      const x0 = A.x(Math.max(b.lo, A.fLo));
      const x1 = A.x(Math.min(b.hi, A.fHi));
      if (x1 <= x0) continue;
      if (b.name === 'theta') {
        g.fillStyle = 'rgba(255,196,0,0.13)';
        g.fillRect(x0, PAD.t, x1 - x0, A.H - PAD.t - PAD.b);
      }
      g.strokeStyle = faint;
      g.lineWidth = 1;
      g.beginPath();
      g.moveTo(Math.round(x0) + 0.5, PAD.t);
      g.lineTo(Math.round(x0) + 0.5, A.H - PAD.b);
      g.stroke();
      g.fillStyle = dim;
      g.font = '9.5px system-ui, sans-serif';
      g.fillText(b.name, x0 + 3, PAD.t + 10);
    }

    // ---- gridlines and ticks ----
    g.strokeStyle = faint;
    g.fillStyle = dim;
    g.font = '10px system-ui, sans-serif';
    for (const hz of [1, 2, 5, 10, 20, 50, 100, 200, 500]) {
      if (hz < A.fLo || hz > A.fHi) continue;
      const px = Math.round(A.x(hz)) + 0.5;
      g.beginPath();
      g.moveTo(px, PAD.t);
      g.lineTo(px, A.H - PAD.b);
      g.stroke();
      g.textAlign = 'center';
      g.fillText(String(hz), px, A.H - PAD.b + 13);
    }
    g.textAlign = 'center';
    g.fillText('Frequency (Hz)', PAD.l + (A.W - PAD.l - PAD.r) / 2,
               A.H - PAD.b + 27);

    g.textAlign = 'right';
    if (logY) {
      for (let e = Math.ceil(Math.log10(A.lo)); e <= Math.log10(A.hi); e += 1) {
        const py = Math.round(A.y(Math.pow(10, e))) + 0.5;
        g.beginPath();
        g.moveTo(PAD.l, py);
        g.lineTo(A.W - PAD.r, py);
        g.stroke();
        g.fillText('1e' + e, PAD.l - 6, py + 3);
      }
    } else {
      for (let i = 0; i <= 4; i += 1) {
        const v = A.hi * i / 4;
        const py = Math.round(A.y(v)) + 0.5;
        g.beginPath();
        g.moveTo(PAD.l, py);
        g.lineTo(A.W - PAD.r, py);
        g.stroke();
        g.fillText(v.toPrecision(2), PAD.l - 6, py + 3);
      }
    }
    g.save();
    g.translate(12, PAD.t + (A.H - PAD.t - PAD.b) / 2);
    g.rotate(-Math.PI / 2);
    g.textAlign = 'center';
    g.fillText('Power  (' + (res.units || '') + ')', 0, 0);
    g.restore();

    // ---- the curves ----
    for (const r of A.rows) {
      g.strokeStyle = colourOf(r);
      g.lineWidth = A.rows.length > 24 ? 1 : 1.4;
      // A channel somebody marked bad is drawn, because they asked for it,
      // and drawn dashed, because it is still marked bad.
      g.setLineDash(r.bad ? [3, 3] : []);
      g.beginPath();
      const f = res.freqs;
      for (let i = 0; i < f.length; i += 1) {
        const px = A.x(f[i]);
        const py = A.y(r.psd[i]);
        if (i === 0) g.moveTo(px, py); else g.lineTo(px, py);
      }
      g.stroke();
    }
    g.setLineDash([]);

    // ---- the crosshair ----
    if (hover) {
      const px = Math.round(A.x(hover.hz)) + 0.5;
      g.strokeStyle = ink;
      g.globalAlpha = 0.35;
      g.beginPath();
      g.moveTo(px, PAD.t);
      g.lineTo(px, A.H - PAD.b);
      g.stroke();
      g.globalAlpha = 1;
    }

    g.strokeStyle = faint;
    g.strokeRect(PAD.l + 0.5, PAD.t + 0.5,
                 A.W - PAD.l - PAD.r - 1, A.H - PAD.t - PAD.b - 1);
  }

  function onHover(e) {
    if (!res) return;
    const cv = e.currentTarget;
    const box = cv.getBoundingClientRect();
    const mx = e.clientX - box.left;
    const A = axes();
    if (!A) return;
    if (mx < PAD.l || mx > A.W - PAD.r) { hover = null; draw(); paintReadout(); return; }
    // Invert the log axis rather than searching: the bins are dense and the
    // arithmetic is exact.
    const t = (mx - PAD.l) / (A.W - PAD.l - PAD.r);
    const hz = Math.pow(10, Math.log10(A.fLo)
      + t * (Math.log10(A.fHi) - Math.log10(A.fLo)));
    const f = res.freqs;
    let i = 0;
    while (i < f.length - 1 && f[i + 1] < hz) i += 1;
    hover = { hz: f[i], i: i };
    draw();
    paintReadout();
  }

  function paintReadout() {
    const node = document.getElementById('psdReadout');
    if (!node) return;
    node.innerHTML = '';
    if (!hover) {
      node.appendChild(el('span', { class: 'hint',
        text: 'Hover the plot to read a frequency off it.' }));
      return;
    }
    const band = (res.bands || []).find(
      (b) => hover.hz >= b.lo && hover.hz < b.hi);
    node.appendChild(el('strong', { text: hover.hz.toFixed(2) + ' Hz' }));
    if (band) node.appendChild(el('span', { class: 'hint', text: band.name }));
    const rows = drawn().slice().sort(
      (a, b) => b.psd[hover.i] - a.psd[hover.i]);
    for (const r of rows.slice(0, 6)) {
      node.appendChild(el('span', { class: 'psd-read-ch' }, [
        el('i', { class: 'psd-dot', style: 'background:' + colourOf(r) }),
        el('span', { text: r.label + '  ' + r.psd[hover.i].toPrecision(3) }),
      ]));
    }
    if (rows.length > 6) {
      node.appendChild(el('span', { class: 'hint',
        text: '+' + (rows.length - 6) + ' more' }));
    }
  }

  /* ---- the legend, which is also the channel toggles ---- */
  function legend() {
    return el('div', { class: 'psd-legend' },
      (res.channels || []).map((r) => {
        if (!r.psd) {
          return el('span', { class: 'psd-leg bad', title: r.error || '',
                              text: r.label + ' — failed' });
        }
        const off = hidden.has(r.index);
        return el('button', {
          class: 'psd-leg' + (off ? ' off' : ''),
          title: 'Peak ' + (r.peak_hz || 0).toFixed(2) + ' Hz.  Theta is '
               + (100 * r.bands.theta.share).toFixed(1) + '% of the power '
               + 'in band.  Click to hide this line.',
          // `render` rebuilds the canvas and redraws it, so there is
          // nothing to draw here first.
          onclick: () => {
            if (off) hidden.delete(r.index); else hidden.add(r.index);
            render();
          },
        }, [
          el('i', { class: 'psd-dot', style: 'background:' + colourOf(r) }),
          el('span', { text: r.label }),
          el('span', { class: 'psd-leg-num',
            text: (r.bands.theta.peak_hz || 0).toFixed(1) + ' Hz · '
                + (100 * r.bands.theta.share).toFixed(0) + '%' }),
        ]);
      }));
  }

  /* ---- the numbers, because a peak read off a log plot is a guess ---- */
  function bandTable() {
    const bands = res.bands || [];
    const rows = (res.channels || []).filter((c) => c.psd);
    const box = el('div', { class: 'psd-table-wrap' });
    box.appendChild(el('div', { class: 'section-label',
      text: 'Power in band, as a share of 1–' + (res.plan || {}).fmax
          + ' Hz' }));
    const head = el('tr', {}, [el('th', { text: 'Channel' })]
      .concat(bands.map((b) => el('th', {
        text: b.name, title: b.lo + '–' + b.hi + ' Hz' })))
      /* The theta peak, not the overall one.
         Neural power falls off as roughly 1/f, so the biggest bin in
         1-200 Hz is near 1 Hz in every recording ever made and a column of
         it says nothing. Where theta sits varies between animals and within
         a session, which is the question. The overall peak is still in the
         cell's tooltip for anyone who wants it. */
      .concat([el('th', { text: 'theta peak',
                          title: 'Where the most power sits inside 4–12 Hz' })]));
    const body = rows.map((r) => el('tr', {
      class: hidden.has(r.index) ? 'off' : '',
    }, [el('td', {}, [
      el('i', { class: 'psd-dot', style: 'background:' + colourOf(r) }),
      el('span', { text: r.label }),
    ])].concat(bands.map((b) => {
      const v = r.bands[b.name] || {};
      /* Shaded by share, so the gradient down a shank is visible as a
         gradient rather than as thirty numbers to compare by eye. */
      const s = v.share || 0;
      return el('td', {
        style: 'background:rgba(255,196,0,' + (0.42 * Math.min(1, s * 3))
             + ')',
        title: (v.power || 0).toPrecision(4) + ' ' + (res.units || ''),
        text: (100 * s).toFixed(1) + '%',
      });
    })).concat([el('td', {
      title: 'The biggest bin over the whole band is at '
           + (r.peak_hz || 0).toFixed(2) + ' Hz — which is the 1/f slope, '
           + 'not a rhythm.',
      text: ((r.bands.theta || {}).peak_hz || 0).toFixed(2) + ' Hz',
    })])));
    box.appendChild(el('div', { class: 'psd-table-scroll' }, [
      el('table', { class: 'psd-table' }, [
        el('thead', {}, [head]), el('tbody', {}, body),
      ]),
    ]));
    return box;
  }

  /* ---- what was done to the data, in the answer rather than a docstring ---- */
  function samplingNote() {
    const box = el('div', { class: 'psd-note' });
    box.appendChild(el('div', { class: 'section-label',
                                text: 'What this was computed from' }));
    for (const step of (res.sampling || [])) {
      box.appendChild(el('p', { class: 'hint' }, [
        el('strong', { text: step.what + ': ' }),
        el('span', { text: step.note || step.why || '' }),
      ]));
    }
    return box;
  }

  function copyNumbers() {
    const rows = drawn();
    const head = ['hz'].concat(rows.map((r) => r.label)).join('\t');
    const lines = [head];
    for (let i = 0; i < res.freqs.length; i += 1) {
      lines.push([res.freqs[i].toFixed(4)]
        .concat(rows.map((r) => r.psd[i].toExponential(6))).join('\t'));
    }
    const text = lines.join('\n');
    navigator.clipboard.writeText(text).then(
      () => toast(res.freqs.length.toLocaleString() + ' rows × '
                  + rows.length + ' channels copied.', 'ok'),
      () => toast('The clipboard refused. Nothing was copied.', 'err'));
  }

  /* ================================================================== */
  function fmtDur(s) {
    s = Math.max(0, s || 0);
    if (s < 90) return s.toFixed(1) + ' s';
    const m = Math.floor(s / 60);
    return m + ' min ' + Math.round(s - m * 60) + ' s';
  }

  function human(s) {
    if (s == null) return '';
    if (s < 1) return 'a moment';
    if (s < 90) return Math.round(s) + ' s';
    return Math.round(s / 60) + ' min';
  }

  const round2 = (v) => Math.round((v || 0) * 100) / 100;

  window.addEventListener('resize', () => {
    if (res) { sizeCanvas(); draw(); }
  });

  return { onShow, openerMoved, render };
}());

/* What Braid calls when the view moves. A property on `window` for the same
   reason comod.js needs one -- except this handle is read by the OPENER,
   which cannot see this window's `BARRY` either. */
window.barrySpectrum = BARRY.views.spectrum;
