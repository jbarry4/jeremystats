/* ==========================================================================
   panorama.js -- Panorama, the whole recording at once.

   THREE STEPS, AND THEY STAY ON SCREEN TOGETHER

     1. Holistic    the spectrogram end to end, beside a histogram of which
                    frequency was dominant and how often
     2. Power       the whole-recording spectrum over the same range
     3. Save        the figure and the numbers, into Results/

   Step 2 does not need a second run. Averaging the spectrogram's columns IS
   the whole-recording Welch spectrum, so it arrives with step 1 and is drawn
   from the same numbers -- see the note at the top of backend/panorama.py.
   Nothing is replaced as the steps arrive: the point of the layout is that
   the picture you were looking at is still there when the next one lands.

   WHAT IS DRAWN WHERE, AND WHY
   The spectrogram comes back as a PNG. It is two thousand columns by four
   hundred bins, which is megabytes as numbers and a picture either way --
   and the server can colour it through the same Jet the rest of the lab's
   figures use. The histogram and the spectrum come back as NUMBERS and are
   drawn here on a canvas, because those two get rescaled, switched between
   log and linear and read off by eye, and all of that is free on a canvas
   and a round trip on an image.
   ========================================================================== */
'use strict';

BARRY.panorama = (function () {
  /* What is being asked for. Held here, not read off the DOM, so a redraw
     cannot lose a half-filled form. */
  const q = {
    gid: null,
    path: null,
    label: null,
    channels: [],
    t0: null,
    t1: null,
    f_lo: 2,
    f_hi: 200,
    sub_s: 2,
    win_s: 8,
    step_s: 1,
    bins: 48,
    hist_scale: 'log',
    cmap: 'jet',
    scale: 'log10',
  };

  let est = null;          // what a run would cost, and the channel list
  let job = null;          // the run in flight
  let poll = null;
  let previewPng = null;   // the picture so far, while it runs
  let previewRev = -1;
  let res = null;          // the finished run
  let ranAs = null;        // the job that produced `res`
  let shown = 0;           // which channel the cards are showing
  let counting = 'peak';   // 'peak' | 'flat' -- which dominant-frequency rule
  let saving = false;
  let saved = null;

  /* 'one' or 'many'. The same question, asked of one recording or of
     forty; the form is nearly the same and the answer is not, so they
     are two modes of one tool rather than two tools. */
  let mode = 'one';
  let sets = null;           // the list, as the server has it
  let curSet = null;         // the one open, with its tree
  let regions = [];
  let bulkJob = null;
  let bulkPoll = null;
  let bulkEst = null;
  let openRow = null;        // gid whose detail is showing
  let rowRes = null;         // that row's numbers
  let building = null;       // the new-set form, while it is open
  let conv = null;           // the pooled histograms
  let convSaving = false;
  let convSaved = null;
  const convOpts = {
    grouping: 'auto', attr: 'group',
    /* The tallest fitted peak, and one vote per recording. Both
       defaults are arguments, not conveniences -- see the note above
       `converge` in panoramaset.py. */
    dominant: 'peak', weight: 'session', spread: 'sem',
  };

  const NAMED = [
    ['delta', 1, 4], ['theta', 4, 12], ['beta', 13, 30],
    ['low gamma', 30, 60], ['high gamma', 60, 120],
  ];

  /* ==================================================================
     Talking to the server
     ================================================================== */
  function body(extra) {
    return Object.assign({
      path: q.path,
      channels: q.channels.length ? q.channels : null,
      t0: q.t0, t1: q.t1,
      f_lo: q.f_lo, f_hi: q.f_hi,
      sub_s: q.sub_s, win_s: q.win_s, step_s: q.step_s,
      bins: q.bins, hist_scale: q.hist_scale,
      cmap: q.cmap, scale: q.scale,
    }, extra || {});
  }

  let estSeq = 0;
  const refreshEstimate = debounce(async function refreshEstimate_() {
    if (!q.path) { est = null; paint(); return; }
    const mine = ++estSeq;
    let got;
    try {
      got = await apiPost('/api/panorama/estimate', body());
    } catch (e) {
      got = { error: e.message };
    }
    if (mine !== estSeq) return;      // a later edit has superseded this
    est = got;
    if (got && got.session && !q.channels.length) {
      const good = (got.session.channels || []).filter((c) => !c.bad);
      const first = good[0] || (got.session.channels || [])[0];
      if (first) q.channels = [first.index];
    }
    paint();
  }, 250);

  /* `force` recomputes instead of taking the held answer. The same settings
     give the same numbers, so the cache is the right default -- pressing Run
     again on an unchanged form should come straight back rather than spend
     four minutes proving it. Forcing is for the dev harness, which has to be
     able to watch a real run happen, and for anyone who suspects what is
     held no longer matches the recording on disk. */
  async function run(force) {
    if (!q.path || job) return;
    if (!q.channels.length) {
      toast('Pick a channel first.', 'warn');
      return;
    }
    let started;
    try {
      started = await apiPost('/api/panorama/run',
                              body(force ? { force: true } : null));
    } catch (e) {
      toast(e.message, 'err', 10000);
      return;
    }
    if (started.cached) { adopt(started.result, null); paint(); return; }
    job = started.job;
    previewPng = null;
    previewRev = -1;
    paint();
    watch();
  }

  function watch() {
    clearInterval(poll);
    /* 400 ms. The fit reports every sixty-four windows, which is about four
       seconds, and the read every chunk -- so polling faster buys nothing
       but requests. */
    poll = setInterval(async () => {
      if (!job) { clearInterval(poll); return; }
      let got;
      try { got = await api('/api/cfc/job/' + job.id); } catch (e) { return; }
      job = got.job;
      paintStages();
      // The picture is fetched only when its number changes, so a run with
      // nothing new to show costs one small poll.
      if (job.preview_rev && job.preview_rev !== previewRev) {
        previewRev = job.preview_rev;
        fetchPreview(job.id);
      }
      if (job.status === 'running') return;
      clearInterval(poll);
      const done = job; job = null;
      if (done.status === 'done') {
        try {
          adopt((await api('/api/cfc/result/' + done.id)).result, done);
        } catch (e) {
          toast('The run finished but its result could not be read: '
                + e.message, 'err', 10000);
        }
      } else if (done.status === 'failed') {
        toast(done.error || 'The run failed.', 'err', 12000);
      } else if (done.status === 'canceled') {
        toast('Stopped.', 'ok');
      }
      previewPng = null;
      paint();
    }, 400);
  }

  async function fetchPreview(id) {
    try {
      const got = await api('/api/cfc/job/' + id + '/preview');
      if (got && got.png) {
        previewPng = got.png;
        const img = document.getElementById('pnPreviewImg');
        if (img) img.src = previewPng;
        else paint();
      }
    } catch (e) { /* a dropped preview is not a failed run */ }
  }

  async function cancel() {
    if (!job) return;
    try { await apiPost('/api/cfc/job/' + job.id + '/cancel', {}); }
    catch (e) { /* it is already gone */ }
  }

  function adopt(out, doneJob) {
    res = out;
    ranAs = doneJob;
    saved = null;
    shown = 0;
  }

  /* The same run, drawn differently.

     Colormap and log power change the encoding of a picture that has
     already been computed, so they go to `/api/panorama/recolor` and the
     graph never leaves the screen. Both used to call `reset()`, which
     discarded the result and left an empty panel.

     If the cache has let the run go -- it holds a handful -- that is said,
     and the existing picture stays up rather than being replaced by
     nothing. */
  let recolouring = 0;
  async function recolour() {
    if (!res) { paint(); return; }
    const mine = ++recolouring;
    paint();                       // the checkbox reflects the new state now
    let got;
    try {
      got = await apiPost('/api/panorama/recolor', body());
    } catch (e) {
      toast('The picture could not be redrawn: ' + e.message
            + ' — run it again to change the colours.', 'err', 9000);
      return;
    }
    if (mine !== recolouring) return;   // a later toggle has superseded this
    const by = {};
    for (const c of (got.channels || [])) by[c.index] = c.spectrogram;
    for (const c of (res.channels || [])) {
      if (by[c.index]) c.spectrogram = by[c.index];
    }
    // The saved PNG is of the old colours; it is no longer what is shown.
    previewPng = null;
    paint();
  }


  /* The same numbers, counted differently.

     A histogram is a count of the per-window dominant frequencies, and
     those are already in the result -- so the bin count and log-or-linear
     bins are presentation, exactly as the colormap is. Both used to call
     `reset()`, and log/linear taking the whole Holistic view off the screen
     is what got this noticed.

     The server re-cuts it in place, so a Save afterwards writes the bins
     that are actually on screen rather than the ones the run happened to
     start with. */
  let rebinning = 0;
  async function rebin() {
    if (!res) { paint(); return; }
    const mine = ++rebinning;
    paint();                       // the pills show the new choice at once
    let got;
    try {
      got = await apiPost('/api/panorama/rebin', body());
    } catch (e) {
      toast('The histogram could not be re-counted: ' + e.message
            + ' \u2014 run it again to change the bins.', 'err', 9000);
      return;
    }
    if (mine !== rebinning) return;   // a later click has superseded this
    const by = {};
    for (const c of (got.channels || [])) by[c.index] = c;
    for (const c of (res.channels || [])) {
      if (by[c.index]) {
        c.hist = by[c.index].hist;
        c.modal_hz = by[c.index].modal_hz;
      }
    }
    if (res.plan) {
      res.plan.bins = q.bins;
      res.plan.hist_scale = q.hist_scale;
    }
    paint();
  }

  /* A bin count is typed, so it arrives a digit at a time -- 4, then 48,
     then 480. Only the number somebody stopped on is worth counting. */
  const rebinSoon = debounce(() => rebin(), 300);

  function reset() {
    res = null; ranAs = null; saved = null; shown = 0;
    previewPng = null;
    clearInterval(poll);
    job = null;
  }

  /* ==================================================================
     The panel
     ================================================================== */
  /* What had focus, and where the caret was, across a rebuild.

     `paint` replaces the whole panel, so an input being typed into is
     destroyed mid-keystroke; without this the caret lands on the body and
     the next letter is read as a keyboard shortcut. */
  function keepFocus(host, fn) {
    const active = document.activeElement;
    const key = (active && host.contains(active))
      ? active.getAttribute('data-fk') : null;
    let from = null;
    let to = null;
    if (key) {
      // A number input refuses a selection in some browsers; the value is
      // still restored, only the caret position is lost.
      try { from = active.selectionStart; to = active.selectionEnd; }
      catch (e) { from = null; }
    }
    fn();
    if (!key) return;
    const back = host.querySelector('[data-fk="' + key + '"]');
    if (!back) return;
    try {
      back.focus({ preventScroll: true });
      if (from != null) back.setSelectionRange(from, to);
    } catch (e) { /* best effort; the value is already right */ }
  }

  function paint() {
    const host = document.getElementById('tkResult');
    if (!host) return;
    /* Fails CLOSED -- not knowing which tool is open is a reason not to
       draw. The permissive form painted this panel over another tool on any
       page holding an older toolkit.js. */
    const tk = BARRY.views.toolkit;
    if (!tk || typeof tk.tool !== 'function' || tk.tool() !== 'panorama') {
      return;
    }
    keepFocus(host, () => {
      host.style.opacity = '1';
      host.innerHTML = '';
      host.appendChild(modeBar());
      if (mode === 'many') {
        paintBulk(host);
        return;
      }
      host.appendChild(setupCard());
      if (job) host.appendChild(runCard());
      if (res) {
        host.appendChild(holisticCard());
        host.appendChild(spectrumCard());
        host.appendChild(saveCard());
      }
    });
    /* Outside keepFocus, and after: the canvases have to be in the
       document before anything is drawn on them, and `current()` is
       mode-aware so this serves the tree's open row too. */
    drawAll();
  }

  function current() {
    /* The one-recording result, or the stored record of whichever tree
       row is open -- so one set of drawing code serves both modes. */
    if (mode === 'many') return openRow ? fromStored(rowRes) : null;
    if (!res) return null;
    const rows = res.channels || [];
    return rows[Math.min(shown, rows.length - 1)] || null;
  }


  /* ==================================================================
     What each control actually does

     Written out because the defaults are choices, and a number that comes
     out of a choice nobody understood is a number nobody can defend. Each
     opens under its own row rather than as a tooltip, so it can be read
     without holding the mouse still.
     ================================================================== */
  const INFO = {
    channel:
      'Which electrode to analyse. CSC14 is a different depth in every '
      + 'animal, so for comparing recordings the channel matters as much as '
      + 'the settings. "Every good channel" runs them all and skips any '
      + 'marked bad \u2014 a bad channel is a stripe of noise that makes the '
      + 'colour scale useless for the rest.',
    time:
      'Which stretch of the recording. Left empty it takes the whole thing, '
      + 'which is what this tool is for. Narrow it when you want one '
      + 'behavioural epoch rather than the session.',
    freq:
      'The band everything below is computed over. 2 Hz because a 2-second '
      + 'transform has nothing to say below it, and 200 Hz because that is '
      + 'where the Spectrum view stops too, so the two can be compared. '
      + 'Narrowing it makes the dominant frequency a much sharper question: '
      + 'over a wide range a 1/f spectrum has several broad bumps of similar '
      + 'height and the tallest is often close to arbitrary.',
    window:
      'Window is how much recording each column of the spectrogram averages '
      + 'over. FFT is the transform length inside it, and sets the frequency '
      + 'resolution \u2014 1/FFT Hz, so 2 s gives 0.5 Hz bins. Step is how '
      + 'often a column is made, and therefore how often the histogram gets '
      + 'a vote. Each column is an average of several overlapping FFTs '
      + 'rather than one: fitting single transforms gave a median R\u00b2 of '
      + '0.45, which is a fit to noise.',
    colours:
      'How the spectrogram is painted. Jet is the lab standard and matches '
      + 'the figures already in the repository; the perceptually uniform '
      + 'maps are better for anything new. "Log power" compresses the '
      + 'enormous range between low and high frequencies so both are '
      + 'visible at once. Neither changes a number \u2014 changing them '
      + 're-paints the picture without re-reading the recording.',
    counting:
      'Two ways to say which frequency was dominant in a window, and they '
      + 'answer different questions. "Tallest fitted peak" is the rhythm the '
      + 'fit actually found, and a window with no rhythm counts as no peak '
      + '\u2014 which is a finding, and is why the no-peak count is reported '
      + 'beside the histogram. "Flattened argmax" removes the 1/f slope and '
      + 'takes the highest remaining bin, so it always returns a number and '
      + 'quiet windows vote too, usually near the bottom of the range.',
    bins:
      'How the dominant frequencies are cut up for counting. Log-spaced by '
      + 'default because the range spans two decades: on linear bins theta '
      + 'is squeezed into three of them and the top of the range becomes a '
      + 'forest of thin spikes. Changing this re-counts numbers already '
      + 'computed \u2014 it does not re-read the recording.',
  };

  let openInfo = null;

  function infoBtn(key) {
    return el('button', {
      class: 'pn-i' + (openInfo === key ? ' on' : ''),
      title: 'what this does',
      'aria-label': 'what this does',
      text: 'i',
      onclick: (e) => {
        e.stopPropagation();
        openInfo = (openInfo === key) ? null : key;
        paint();
      },
    });
  }

  /* The row and its explanation as one block, so the note lands under the
     control it is about rather than at the bottom of the card. */
  function withInfo(key, row) {
    if (openInfo !== key) return row;
    return el('div', { class: 'pn-with-info' }, [
      row,
      el('p', { class: 'pn-info', text: INFO[key] }),
    ]);
  }

  /* ---------- 1. the form ---------- */
  function setupCard() {
    const box = el('div', { class: 'card pn-setup' });
    box.appendChild(el('div', { class: 'section-label',
                                style: 'margin-top:0',
                                text: 'Which recording' }));
    const rows = (BARRY.views.toolkit && BARRY.views.toolkit.registryRows)
      ? BARRY.views.toolkit.registryRows() : [];
    box.appendChild(BARRY.pickSession({
      rows, value: q.gid,
      placeholder: 'Type a mouse, session or date…',
      onpick: (r) => {
        q.gid = r.gid;
        q.path = (r.here || [])[0] || null;
        q.label = r.label || r.key || null;
        q.channels = [];
        q.t0 = null; q.t1 = null;
        reset();
        refreshEstimate();
        paint();
      },
    }));
    if (q.path) box.appendChild(el('p', { class: 'hint quiet', text: q.path }));
    if (!q.path) {
      box.appendChild(el('p', { class: 'hint', text:
        'Panorama reads the whole recording: the spectrogram end to end, '
        + 'which frequency was dominant and how often, and the power '
        + 'spectrum over the range you ask for.' }));
      return box;
    }
    if (est && est.error) {
      box.appendChild(el('p', { class: 'hint bad', text: est.error }));
      return box;
    }
    if (!est) {
      box.appendChild(el('div', { class: 'tk-loading' }, [
        stepLoader('Panorama', ['reading the recording'])]));
      return box;
    }

    box.appendChild(withInfo('channel', channelRow()));
    box.appendChild(withInfo('time', rangeRow()));
    box.appendChild(withInfo('freq', freqRow()));
    box.appendChild(withInfo('window', windowRow()));
    box.appendChild(withInfo('colours', pictureRow()));
    box.appendChild(costRow());
    return box;
  }

  function channelRow() {
    const wrap = el('div', { class: 'pn-row' });
    wrap.appendChild(el('label', { class: 'pn-lab', text: 'Channel' }));
    wrap.appendChild(infoBtn('channel'));
    const chans = ((est.session || {}).channels) || [];
    const sel = el('select', {
      class: 'inp sm',
      onchange: (e) => {
        q.channels = [parseInt(e.target.value, 10)];
        refreshEstimate();
      },
    });
    for (const c of chans) {
      sel.appendChild(el('option', {
        value: String(c.index),
        selected: q.channels[0] === c.index,
        text: (c.label || ('CSC' + c.number)) + (c.bad ? '  (marked bad)' : ''),
      }));
    }
    wrap.appendChild(sel);
    const many = q.channels.length > 1;
    wrap.appendChild(el('label', { class: 'pn-check' }, [
      el('input', {
        type: 'checkbox', checked: many,
        onchange: (e) => {
          if (e.target.checked) {
            // Every channel that is not marked bad. A bad channel in a
            // whole-recording picture is a stripe of noise that makes the
            // colour scale useless for the rest.
            q.channels = chans.filter((c) => !c.bad).map((c) => c.index);
          } else {
            q.channels = q.channels.slice(0, 1);
          }
          refreshEstimate();
          paint();
        },
      }),
      el('span', { text: 'every good channel' }),
    ]));
    if (many) {
      wrap.appendChild(el('span', { class: 'hint quiet',
        text: q.channels.length + ' channels — this multiplies the time' }));
    }
    return wrap;
  }

  function num(key, label, step, min, max, suffix) {
    const wrap = el('span', { class: 'pn-field' });
    wrap.appendChild(el('label', { class: 'pn-lab', text: label }));
    wrap.appendChild(el('input', {
      class: 'inp sm pn-num', type: 'number',
      // So a repaint can put the caret back. See `keepFocus`.
      'data-fk': 'num:' + key,
      value: q[key] === null ? '' : String(q[key]),
      step: String(step), min: String(min), max: String(max),
      oninput: (e) => {
        const v = e.target.value.trim();
        q[key] = v === '' ? null : parseFloat(v);
        reset();
        refreshEstimate();
      },
    }));
    if (suffix) wrap.appendChild(el('span', { class: 'pn-suffix', text: suffix }));
    return wrap;
  }

  function rangeRow() {
    const dur = (est.session || {}).duration_s || 0;
    const wrap = el('div', { class: 'pn-row' });
    wrap.appendChild(el('span', { class: 'pn-lab', text: 'Time' }));
    wrap.appendChild(infoBtn('time'));
    wrap.appendChild(num('t0', 'from', 1, 0, dur, 's'));
    wrap.appendChild(num('t1', 'to', 1, 0, dur, 's'));
    wrap.appendChild(el('span', { class: 'hint quiet',
      text: (q.t0 || q.t1)
        ? ('of ' + fmtDur(dur))
        : ('the whole recording, ' + fmtDur(dur)) }));
    return wrap;
  }

  function freqRow() {
    const wrap = el('div', { class: 'pn-row' });
    wrap.appendChild(el('span', { class: 'pn-lab', text: 'Frequency' }));
    wrap.appendChild(infoBtn('freq'));
    wrap.appendChild(num('f_lo', 'from', 1, 0.5, 2000, 'Hz'));
    wrap.appendChild(num('f_hi', 'to', 1, 1, 2000, 'Hz'));
    return wrap;
  }

  function windowRow() {
    const wrap = el('div', { class: 'pn-row' });
    wrap.appendChild(el('span', { class: 'pn-lab', text: 'Windows' }));
    wrap.appendChild(infoBtn('window'));
    wrap.appendChild(num('win_s', 'length', 1, 1, 600, 's'));
    wrap.appendChild(num('sub_s', 'FFT', 0.5, 0.25, 60, 's'));
    wrap.appendChild(num('step_s', 'Step', 0.5, 0.05, 60, 's'));
    const p = est.plan || {};
    wrap.appendChild(el('span', { class: 'hint quiet',
      text: (p.resolution_hz ? p.resolution_hz.toFixed(3) + ' Hz bins' : '')
          + (p.n_avg ? ' · ' + p.n_avg + ' averaged per column' : '') }));
    return wrap;
  }

  function pictureRow() {
    const wrap = el('div', { class: 'pn-row' });
    wrap.appendChild(el('label', { class: 'pn-lab', text: 'Colours' }));
    wrap.appendChild(infoBtn('colours'));
    /* The name in the option, the note beside it.

       A <select> is as wide as its widest option, and "Jet — lab standard,
       matches existing figures" made this control 454px: ninety-one pixels
       wider than the pane, which then scrolled sideways. The note is not
       dropped and not shortened -- it moves next to the control, where it
       is still readable and costs the row nothing. */
    const noteEl = el('span', { class: 'hint quiet pn-cmap-note' });
    const setNote = () => {
      const got = (est.colormaps || []).find((c) => c.id === q.cmap);
      noteEl.textContent = (got && got.note) || '';
    };
    const sel = el('select', {
      class: 'inp sm pn-pick',
      onchange: (e) => {
        q.cmap = e.target.value;
        setNote();
        // A drawing choice, not a measurement: recolour rather than throw
        // the computed spectrogram away.
        recolour();
      },
    });
    for (const c of (est.colormaps || [])) {
      sel.appendChild(el('option', {
        value: c.id, selected: q.cmap === c.id, text: c.name,
      }));
    }
    setNote();
    wrap.appendChild(sel);
    wrap.appendChild(noteEl);
    wrap.appendChild(el('label', { class: 'pn-check' }, [
      el('input', {
        type: 'checkbox', checked: q.scale !== 'linear',
        onchange: (e) => {
          q.scale = e.target.checked ? 'log10' : 'linear';
          recolour();
        },
      }),
      el('span', { text: 'log power' }),
    ]));
    return wrap;
  }

  function costRow() {
    const wrap = el('div', { class: 'pn-cost' });
    const p = est.plan || {};
    wrap.appendChild(el('div', { class: 'pn-notes' },
      (est.notes || []).map((n) => el('span', { class: 'pn-note', text: n }))));
    const line = el('div', { class: 'pn-cost-line' });
    line.appendChild(el('strong', {
      text: est.cached ? 'Already computed — it will come straight back'
                       : ('about ' + fmtSecs(est.seconds)) }));
    if (!est.cached && est.seconds > 20) {
      line.appendChild(el('span', { class: 'hint quiet',
        text: 'reading ' + fmtSecs(est.read_s) + ', fitting '
            + fmtSecs(est.fit_s) + ' — you can watch it and stop it' }));
    }
    line.appendChild(el('button', {
      class: 'btn', disabled: !!job,
      text: job ? 'Running…' : (res ? 'Run again' : 'Run'),
      // Wrapped, not passed by name: the click event would arrive as
      // `force` and every press would recompute.
      onclick: () => run(),
    }));
    wrap.appendChild(line);
    if (est.engine && !est.engine.available) {
      wrap.appendChild(el('p', { class: 'hint bad', text:
        'The per-window fits need the `fooof` package, which is not '
        + 'installed here. Run: pip install -r requirements.txt' }));
    }
    return wrap;
  }

  /* ---------- the waiting screen ---------- */
  function runCard() {
    const box = el('div', { class: 'card pn-running' });
    box.appendChild(el('div', { class: 'section-label',
                                style: 'margin-top:0',
                                text: 'Reading the recording' }));
    box.appendChild(el('div', { class: 'pn-preview' }, [
      el('img', {
        id: 'pnPreviewImg', class: 'pn-preview-img',
        src: previewPng || TRANSPARENT,
        alt: 'the spectrogram as it is computed',
      }),
      el('div', { class: 'pn-preview-cap' }, [
        el('span', { text: previewPng
          ? 'The spectrogram so far — it fills in as the recording is read.'
          : 'The picture starts as soon as the first minutes are in.' }),
      ]),
    ]));
    box.appendChild(el('div', { class: 'comod-stages', id: 'pnStages' }));
    box.appendChild(el('div', { class: 'pn-run-foot' }, [
      el('span', { class: 'hint quiet', id: 'pnEta' }),
      el('button', { class: 'btn ghost sm', text: 'Stop', onclick: cancel }),
    ]));
    return box;
  }

  const TRANSPARENT =
    'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

  const STAGE_NAMES = {
    'spectrum read': 'Read the recording and decimate it',
    'panorama windows': 'Fit every window',
    'panorama pool': 'Pool the recordings',
  };

  function paintStages() {
    const host = document.getElementById('pnStages');
    if (!host || !job) return;
    host.innerHTML = '';
    for (const s of (job.stages || [])) {
      const running = s.status === 'running';
      const frac = s.of ? Math.min(s.done / s.of, 1) : 0;
      host.appendChild(el('div', {
        class: 'comod-stage' + (running ? ' on' : '')
               + (s.status === 'done' ? ' done' : '')
               + (s.status === 'failed' ? ' bad' : ''),
      }, [
        el('span', { class: 'comod-tick',
          text: s.status === 'done' ? '✓' : running ? '▸'
            : s.status === 'failed' ? '✗' : '' }),
        el('span', { class: 'comod-stage-name',
          text: STAGE_NAMES[s.name] || s.name }),
        el('span', { class: 'comod-stage-count',
          text: s.of > 1 ? ((s.status === 'waiting' ? '–'
            : s.done.toLocaleString()) + ' / ' + s.of.toLocaleString()
            + ' ' + s.unit) : '' }),
        running && s.of > 1
          ? el('div', { class: 'comod-mini' }, [
              el('div', { class: 'comod-mini-fill',
                          style: 'width:' + (frac * 100).toFixed(1) + '%' }),
            ])
          : null,
      ]));
    }
    const eta = document.getElementById('pnEta');
    if (eta) {
      eta.textContent = job.eta_s
        ? ('about ' + fmtSecs(job.eta_s) + ' left — ' + fmtSecs(job.elapsed)
           + ' so far')
        : (fmtSecs(job.elapsed) + ' so far');
    }
  }

  /* ---------- step 1 ---------- */
  function holisticCard() {
    const ch = current();
    const box = el('div', { class: 'card pn-step' });
    box.appendChild(stepHead('1', 'Holistic',
      'The whole recording, and which frequency was on top.'));
    if (!ch || ch.error) {
      box.appendChild(el('p', { class: 'hint bad',
        text: (ch && ch.error) || 'Nothing came back for that channel.' }));
      return box;
    }
    if ((res.channels || []).length > 1) box.appendChild(channelPager());

    const grid = el('div', { class: 'pn-grid' });
    grid.appendChild(spectrogramPane(ch));
    grid.appendChild(histogramPane(ch));
    box.appendChild(grid);
    return box;
  }

  function channelPager() {
    const wrap = el('div', { class: 'pn-pager' });
    (res.channels || []).forEach((c, i) => {
      wrap.appendChild(el('button', {
        class: 'pill' + (i === shown ? ' active' : ''),
        text: c.label || ('CSC' + c.number),
        onclick: () => { shown = i; paint(); },
      }));
    });
    return wrap;
  }

  function spectrogramPane(ch) {
    const sg = ch.spectrogram || {};
    const pane = el('div', { class: 'pn-pane' });
    pane.appendChild(el('div', { class: 'pn-pane-head' }, [
      el('strong', { text: 'Spectrogram' }),
      el('span', { class: 'hint quiet',
        text: fmtDur(sg.t1 - sg.t0) + ' · ' + sg.n_cols + ' columns · '
            + sg.f_lo.toFixed(1) + '–' + sg.f_hi.toFixed(0) + ' Hz, log' }),
    ]));
    pane.appendChild(el('div', { class: 'pn-sg' }, [
      el('img', { class: 'pn-sg-img', src: sg.png, alt: 'spectrogram' }),
      el('canvas', { class: 'pn-sg-axes', id: 'pnSgAxes' }),
    ]));
    const g = ch.gaps || {};
    if (g.n) {
      pane.appendChild(el('p', { class: 'hint warn',
        text: g.n + ' gap' + (g.n === 1 ? '' : 's') + ' in this recording, '
            + g.seconds.toFixed(3) + ' s never written — drawn as holes, and '
            + 'left out of everything below. The time axis is the '
            + 'recording’s own.' }));
    }
    return pane;
  }

  function histogramPane(ch) {
    const h = ch.hist || {};
    const pane = el('div', { class: 'pn-pane' });
    pane.appendChild(el('div', { class: 'pn-pane-head' }, [
      el('strong', { text: 'Dominant frequency' }),
      el('span', { class: 'hint quiet',
        text: 'by occurrence, ' + h.bins + ' ' + h.scale + ' bins' }),
    ]));
    pane.appendChild(el('canvas', { class: 'pn-canvas', id: 'pnHist' }));

    const opts = el('div', { class: 'pn-opts' });
    opts.appendChild(el('span', { class: 'pn-lab', text: 'Count by' }));
    opts.appendChild(infoBtn('counting'));
    opts.appendChild(radio('peak', 'tallest fitted peak',
      'The rhythm the fit actually found. A window with none counts as '
      + '“no peak”, which is a finding rather than a gap.'));
    opts.appendChild(radio('flat', 'flattened argmax',
      'The highest bin once the aperiodic slope is removed. Always returns '
      + 'a number, so quiet windows vote too — usually near the bottom of '
      + 'the range.'));
    pane.appendChild(opts);
    if (openInfo === 'counting') {
      pane.appendChild(el('p', { class: 'pn-info', text: INFO.counting }));
    }

    const opts2 = el('div', { class: 'pn-opts' });
    opts2.appendChild(el('span', { class: 'pn-lab', text: 'Bins' }));
    opts2.appendChild(infoBtn('bins'));
    opts2.appendChild(el('input', {
      class: 'inp sm pn-num', type: 'number', value: String(q.bins),
      'data-fk': 'bins',
      min: '4', max: '400', step: '4',
      oninput: (e) => {
        const v = parseInt(e.target.value, 10);
        if (v >= 4 && v <= 400) {
          q.bins = v;
          if (res) rebinSoon(); else refreshEstimate();
        }
      },
    }));
    for (const s of ['log', 'linear']) {
      opts2.appendChild(el('button', {
        class: 'pill' + (q.hist_scale === s ? ' active' : ''),
        text: s,
        onclick: () => {
          q.hist_scale = s;
          // The reported one: this used to take the view with it.
          if (res) rebin(); else { refreshEstimate(); paint(); }
        },
      }));
    }
    pane.appendChild(opts2);
    if (openInfo === 'bins') {
      pane.appendChild(el('p', { class: 'pn-info', text: INFO.bins }));
    }

    const pct = h.n_windows ? (100 * h.n_nopeak / h.n_windows) : 0;
    pane.appendChild(el('p', { class: 'hint' + (pct > 40 ? ' warn' : ''),
      text: h.n_nopeak.toLocaleString() + ' of ' + h.n_windows.toLocaleString()
          + ' windows had no peak (' + pct.toFixed(1) + '%)'
          + (h.n_rejected ? ', and ' + h.n_rejected + ' could not be '
             + 'measured at all' : '') }));
    return pane;
  }

  function radio(id, label, why) {
    return el('label', { class: 'pn-check', title: why }, [
      el('input', {
        type: 'radio', name: 'pnCount', checked: counting === id,
        onchange: () => { counting = id; drawAll(); },
      }),
      el('span', { text: label }),
    ]);
  }

  /* ---------- step 2 ---------- */
  function spectrumCard() {
    const ch = current();
    const box = el('div', { class: 'card pn-step' });
    box.appendChild(stepHead('2', 'Power spectrum',
      'The same read, collapsed over time.'));
    if (!ch || ch.error) return box;
    const p = res.plan || {};
    box.appendChild(el('div', { class: 'pn-pane-head' }, [
      el('span', { class: 'hint quiet',
        text: p.f_lo + '–' + p.f_hi + ' Hz in steps of '
            + p.resolution_hz.toFixed(3) + ' Hz · '
            + (ch.hist ? ch.hist.n_windows.toLocaleString() : '?')
            + ' segments averaged · ' + res.units }),
    ]));
    box.appendChild(el('canvas', { class: 'pn-canvas pn-psd', id: 'pnPsd' }));
    const f = ch.fit || {};
    const bits = [];
    if (f.exponent !== undefined && f.exponent !== null) {
      bits.push('aperiodic exponent ' + f.exponent.toFixed(2));
    }
    if (f.r_squared !== undefined && f.r_squared !== null) {
      bits.push('R² ' + f.r_squared.toFixed(3));
    }
    if (ch.line_at && ch.line_at.length) {
      bits.push(ch.line_at.join(', ') + ' Hz bridged');
    }
    if (bits.length) {
      box.appendChild(el('p', { class: 'hint quiet', text: bits.join(' · ') }));
    }
    return box;
  }

  /* ---------- step 3 ---------- */
  function saveCard() {
    const box = el('div', { class: 'card pn-step' });
    box.appendChild(stepHead('3', 'Save',
      'Into Results/, where the rest of the lab can find it.'));
    if (saved) {
      box.appendChild(el('p', { class: 'hint ok',
        text: 'Saved ' + saved.files.length + ' file'
            + (saved.files.length === 1 ? '' : 's') + ' to ' + saved.folder }));
      box.appendChild(el('div', { class: 'pn-saved' },
        saved.files.map((f) => el('code', { text: f }))));
      box.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Show me in Results',
        onclick: () => { setView('results'); },
      }));
      return box;
    }
    const nameBox = el('input', {
      class: 'inp', id: 'pnName', type: 'text',
      value: defaultName(),
      placeholder: 'what to call it',
    });
    box.appendChild(el('div', { class: 'pn-row' }, [
      el('label', { class: 'pn-lab', text: 'Name' }), nameBox,
      el('button', {
        class: 'btn', disabled: saving,
        text: saving ? 'Saving…' : 'Save to Results',
        onclick: () => save(nameBox.value),
      }),
    ]));
    box.appendChild(el('p', { class: 'hint quiet', text:
      'A figure, the spectrum and the histogram as CSV, the per-window '
      + 'table, and a JSON of every setting that produced them — including '
      + 'which fitter, so the numbers are never ambiguous.' }));
    return box;
  }

  function defaultName() {
    const ch = current() || {};
    return [q.label || 'recording', ch.label || '', 'panorama']
      .filter(Boolean).join(' ');
  }

  async function save(name) {
    if (saving || !res) return;
    saving = true; paint();
    try {
      const got = await apiPost('/api/panorama/save',
                                body({ name: name, counting: counting }));
      saved = got;
      toast('Saved to Results.', 'ok');
    } catch (e) {
      toast(e.message, 'err', 10000);
    } finally {
      saving = false;
      paint();
    }
  }

  function stepHead(n, title, sub) {
    return el('div', { class: 'pn-step-head' }, [
      el('span', { class: 'pn-step-n', text: n }),
      el('strong', { text: title }),
      el('span', { class: 'hint quiet', text: sub }),
    ]);
  }

  /* ==================================================================
     Drawing the two that are numbers
     ================================================================== */
  /* Size from the canvas's OWN laid-out width, not its parent's.

     `parentNode.clientWidth` includes the card's padding, so every canvas
     came out about thirty pixels wider than the box it sits in and pushed
     the whole tool pane sideways -- 91px of horizontal overflow at a narrow
     width, measured. CSS gives it `width:100%`; this reads back what that
     actually came to and sizes the backing store to match. */
  function sizeCanvas(id, ratio, minH, maxH) {
    const cv = document.getElementById(id);
    if (!cv || !cv.parentNode) return null;
    cv.style.width = '100%';
    cv.style.height = 'auto';
    const w = Math.max(200, Math.round(
      cv.clientWidth || cv.getBoundingClientRect().width
      || cv.parentNode.clientWidth));
    const h = Math.max(minH, Math.min(maxH, Math.round(w * ratio)));
    const dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    cv.style.height = h + 'px';
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    return { g, W: w, H: h };
  }

  function ink() {
    return {
      text: BARRY.token('--text', '#222'),
      dim: BARRY.token('--text-3', '#888'),
      faint: BARRY.token('--border', '#ddd'),
      accent: BARRY.token('--accent', '#FFB81C'),
      good: BARRY.token('--ok', '#2e7d32'),
    };
  }

  function drawAll() {
    drawHistogram();
    drawPsd();
    drawSgAxes();
  }

  function drawHistogram() {
    const ch = current();
    if (!ch || !ch.hist) return;
    const c = sizeCanvas('pnHist', 0.62, 200, 340);
    if (!c) return;
    const { g, W, H } = c;
    const k = ink();
    const h = ch.hist;
    const counts = counting === 'flat' ? h.flat : h.peak;
    const edges = h.edges;
    const logx = h.scale === 'log';
    const L = 46, R = 10, T = 12, B = 30;
    const x0 = edges[0], x1 = edges[edges.length - 1];
    const sx = (v) => {
      const a = logx ? Math.log10(v) : v;
      const lo = logx ? Math.log10(x0) : x0;
      const hi = logx ? Math.log10(x1) : x1;
      return L + (a - lo) / (hi - lo) * (W - L - R);
    };
    const top = Math.max(1, Math.max.apply(null, counts));
    const sy = (v) => H - B - (v / top) * (H - T - B);

    // Named bands behind the bars, so a peak can be read without counting
    // gridlines across to the axis.
    g.font = '10px system-ui, sans-serif';
    for (const [name, lo, hi] of NAMED) {
      if (hi < x0 || lo > x1) continue;
      const a = sx(Math.max(lo, x0));
      const b = sx(Math.min(hi, x1));
      g.fillStyle = k.faint;
      g.globalAlpha = 0.25;
      g.fillRect(a, T, Math.max(0, b - a), H - T - B);
      g.globalAlpha = 1;
      if (b - a > 26) {
        g.fillStyle = k.dim;
        g.textAlign = 'center';
        g.fillText(name, (a + b) / 2, T + 10);
      }
    }

    g.fillStyle = k.accent;
    for (let i = 0; i < counts.length; i += 1) {
      if (!counts[i]) continue;
      const a = sx(edges[i]);
      const b = sx(edges[i + 1]);
      g.fillRect(a, sy(counts[i]), Math.max(1, b - a - 0.6),
                 H - B - sy(counts[i]));
    }

    g.strokeStyle = k.faint;
    g.beginPath(); g.moveTo(L, T); g.lineTo(L, H - B); g.lineTo(W - R, H - B);
    g.stroke();

    g.fillStyle = k.dim;
    g.textAlign = 'center';
    const ticks = logx ? [2, 5, 10, 20, 50, 100, 200] : niceTicks(x0, x1, 6);
    for (const t of ticks) {
      if (t < x0 || t > x1) continue;
      g.fillText(String(t), sx(t), H - B + 14);
    }
    g.textAlign = 'right';
    g.fillText(String(top), L - 6, T + 8);
    g.fillText('0', L - 6, H - B);
    g.save();
    g.translate(11, (H - B + T) / 2);
    g.rotate(-Math.PI / 2);
    g.textAlign = 'center';
    g.fillText('windows', 0, 0);
    g.restore();
    g.textAlign = 'center';
    g.fillText('Hz', (W + L) / 2, H - 4);
  }

  function drawPsd() {
    const ch = current();
    if (!ch || !ch.psd) return;
    const c = sizeCanvas('pnPsd', 0.42, 220, 420);
    if (!c) return;
    const { g, W, H } = c;
    const k = ink();
    const f = ch.freqs;
    const p = ch.psd;
    const L = 58, R = 12, T = 12, B = 32;

    const good = [];
    for (let i = 0; i < f.length; i += 1) {
      if (p[i] !== null && p[i] > 0 && f[i] > 0) good.push(i);
    }
    if (good.length < 2) return;
    const fx = good.map((i) => Math.log10(f[i]));
    const py = good.map((i) => Math.log10(p[i]));
    const xlo = Math.min.apply(null, fx), xhi = Math.max.apply(null, fx);
    let ylo = Math.min.apply(null, py), yhi = Math.max.apply(null, py);
    const padY = (yhi - ylo) * 0.06 || 1;
    ylo -= padY; yhi += padY;
    const sx = (v) => L + (v - xlo) / (xhi - xlo) * (W - L - R);
    const sy = (v) => H - B - (v - ylo) / (yhi - ylo) * (H - T - B);

    for (const [name, lo, hi] of NAMED) {
      const a = sx(Math.log10(Math.max(lo, Math.pow(10, xlo))));
      const b = sx(Math.log10(Math.min(hi, Math.pow(10, xhi))));
      if (!(b > a)) continue;
      g.fillStyle = k.faint; g.globalAlpha = 0.22;
      g.fillRect(a, T, b - a, H - T - B);
      g.globalAlpha = 1;
    }

    // The fitted aperiodic slope, so the curve can be read against what the
    // fit thought was background rather than by eye.
    const fit = ch.fit || {};
    if (fit.offset !== undefined && fit.exponent !== undefined
        && fit.offset !== null && fit.exponent !== null) {
      g.strokeStyle = k.dim;
      g.setLineDash([4, 3]);
      g.beginPath();
      for (let i = 0; i < fx.length; i += 1) {
        const knee = fit.knee || 0;
        const v = fit.offset - Math.log10(knee + Math.pow(10, fx[i] * fit.exponent));
        const y = sy(v);
        if (i === 0) g.moveTo(sx(fx[i]), y); else g.lineTo(sx(fx[i]), y);
      }
      g.stroke();
      g.setLineDash([]);
    }

    g.strokeStyle = k.accent;
    g.lineWidth = 1.5;
    g.beginPath();
    for (let i = 0; i < fx.length; i += 1) {
      const x = sx(fx[i]), y = sy(py[i]);
      if (i === 0) g.moveTo(x, y); else g.lineTo(x, y);
    }
    g.stroke();
    g.lineWidth = 1;

    g.strokeStyle = k.faint;
    g.beginPath(); g.moveTo(L, T); g.lineTo(L, H - B); g.lineTo(W - R, H - B);
    g.stroke();

    g.fillStyle = k.dim;
    g.font = '10px system-ui, sans-serif';
    g.textAlign = 'center';
    for (const t of [1, 2, 5, 10, 20, 50, 100, 200, 500]) {
      const lv = Math.log10(t);
      if (lv < xlo || lv > xhi) continue;
      g.fillText(String(t), sx(lv), H - B + 14);
    }
    g.textAlign = 'right';
    for (let e = Math.ceil(ylo); e <= Math.floor(yhi); e += 1) {
      g.fillText('1e' + e, L - 6, sy(e) + 3);
    }
    g.textAlign = 'center';
    g.fillText('Hz', (W + L) / 2, H - 4);
    g.save();
    g.translate(13, (H - B + T) / 2);
    g.rotate(-Math.PI / 2);
    g.fillText('µV²/Hz', 0, 0);
    g.restore();
  }

  /* The spectrogram's axes, drawn over the image rather than baked into it,
     so the picture stays pixel-exact and re-colouring does not mean
     re-rendering text. */
  function drawSgAxes() {
    const ch = current();
    if (!ch || !ch.spectrogram) return;
    const cv = document.getElementById('pnSgAxes');
    const img = cv && cv.parentNode.querySelector('.pn-sg-img');
    if (!cv || !img) return;
    // The image's own rect, so the rules land on the pixels they name.
    const r = img.getBoundingClientRect();
    const w = Math.round(r.width) || img.clientWidth;
    const h = Math.round(r.height) || img.clientHeight || 220;
    if (!w || !h) { setTimeout(drawSgAxes, 60); return; }
    const dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    cv.style.width = w + 'px';
    cv.style.height = h + 'px';
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);

    const sg = ch.spectrogram;
    const k = ink();
    g.font = '10px system-ui, sans-serif';
    g.fillStyle = k.text;
    g.strokeStyle = 'rgba(255,255,255,0.35)';

    // Frequency rules, on the log axis the image was built with.
    const lo = Math.log10(sg.f_lo), hi = Math.log10(sg.f_hi);
    for (const f of [4, 12, 30, 60, 120]) {
      const lv = Math.log10(f);
      if (lv < lo || lv > hi) continue;
      const y = h - (lv - lo) / (hi - lo) * h;
      g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke();
      g.fillText(f + ' Hz', 3, y - 2);
    }
    // Time rules.
    const span = sg.t1 - sg.t0;
    const every = niceStep(span, 6);
    for (let t = Math.ceil(sg.t0 / every) * every; t <= sg.t1; t += every) {
      const x = (t - sg.t0) / span * w;
      g.beginPath(); g.moveTo(x, h - 12); g.lineTo(x, h); g.stroke();
      g.textAlign = 'center';
      g.fillText(fmtClock(t), x, h - 14);
    }
  }

  /* ==================================================================
     Small helpers
     ================================================================== */
  function niceStep(span, want) {
    const raw = span / Math.max(1, want);
    const pow = Math.pow(10, Math.floor(Math.log10(raw)));
    for (const m of [1, 2, 5, 10]) {
      if (raw <= m * pow) return m * pow;
    }
    return 10 * pow;
  }

  function niceTicks(a, b, want) {
    const step = niceStep(b - a, want);
    const out = [];
    for (let v = Math.ceil(a / step) * step; v <= b; v += step) out.push(v);
    return out;
  }

  function fmtSecs(s) {
    if (!s && s !== 0) return '—';
    if (s < 60) return Math.round(s) + ' s';
    const m = Math.floor(s / 60);
    const r = Math.round(s - m * 60);
    return m + ' m' + (r ? ' ' + r + ' s' : '');
  }

  function fmtDur(s) {
    if (!s && s !== 0) return '—';
    const m = Math.floor(s / 60);
    const r = Math.round(s - m * 60);
    if (m < 60) return m + ' min' + (r ? ' ' + r + ' s' : '');
    return Math.floor(m / 60) + ' h ' + (m % 60) + ' min';
  }

  function fmtClock(s) {
    const m = Math.floor(s / 60);
    const r = Math.floor(s - m * 60);
    return m + ':' + (r < 10 ? '0' : '') + r;
  }

  window.addEventListener('resize', () => { if (res) drawAll(); });


  /* ==================================================================
     Many recordings at once

     A set is a question and the recordings to ask it of. The question is
     frozen when the set is made -- changing the frequency range makes a new
     set rather than quietly mixing two answers in one histogram -- so this
     form is about WHICH recordings and WHICH channel, and the parameters
     are settled once.
     ================================================================== */
  function modeBar() {
    const wrap = el('div', { class: 'pn-modes' });
    for (const [id, name, sub_] of [
      ['one', 'One recording', 'the whole session, end to end'],
      ['many', 'Many at once', 'a set, and where each one got to'],
    ]) {
      wrap.appendChild(el('button', {
        class: 'pill' + (mode === id ? ' active' : ''),
        onclick: () => {
          if (mode === id) return;
          mode = id;
          if (id === 'many' && !sets) loadSets();
          paint();
        },
      }, [
        el('span', { text: name }),
        el('span', { class: 'tk-pill-sub', text: sub_ }),
      ]));
    }
    return wrap;
  }

  async function loadSets() {
    try {
      const got = await api('/api/panorama/sets');
      sets = got.sets || [];
      regions = got.regions || [];
    } catch (e) {
      sets = [];
      toast(e.message, 'err', 9000);
    }
    paint();
  }

  async function openSet(id) {
    try {
      const got = await api('/api/panorama/sets/' + encodeURIComponent(id));
      curSet = got.set;
      regions = got.regions || regions;
      openRow = null;
      rowRes = null;
      bulkEst = null;
      conv = null;
      convSaved = null;
      refreshBulkEstimate();
      loadConverge();
    } catch (e) {
      toast(e.message, 'err', 9000);
    }
    paint();
  }

  function paintBulk(host) {
    if (!sets) {
      host.appendChild(el('div', { class: 'tk-loading' }, [
        stepLoader('Panorama', ['reading the sets'])]));
      return;
    }
    if (building) { host.appendChild(buildCard()); return; }
    if (!curSet) { host.appendChild(setListCard()); return; }
    host.appendChild(setHeadCard());
    if (bulkJob) host.appendChild(bulkRunCard());
    host.appendChild(treeCard());
    if (openRow) host.appendChild(rowCard());
    host.appendChild(convergeCard());
    drawSparks();
    drawConverge();
  }

  /* ---------- the list ---------- */
  function setListCard() {
    const box = el('div', { class: 'card' });
    box.appendChild(el('div', { class: 'pn-row', style: 'margin-top:0' }, [
      el('div', { class: 'section-label', style: 'margin:0',
                  text: 'Sets' }),
      el('button', {
        class: 'btn', text: 'New set',
        onclick: () => { building = newBuild(); paint(); },
      }),
    ]));
    if (!sets.length) {
      box.appendChild(el('p', { class: 'hint', text:
        'A set asks one question of many recordings and keeps every answer, '
        + 'so the histograms can be pooled afterwards. Nothing is recomputed '
        + 'twice: a recording already answered under the same settings is '
        + 'reused, which is what makes stopping and resuming free.' }));
      return box;
    }
    const list = el('div', { class: 'pn-sets' });
    for (const s of sets) {
      const done = (s.counts || {}).done || 0;
      list.appendChild(el('button', {
        class: 'pn-set', onclick: () => openSet(s.set_id),
      }, [
        el('strong', { text: s.name }),
        el('span', { class: 'hint quiet',
          text: s.n_members + ' recording' + (s.n_members === 1 ? '' : 's')
              + ' · ' + done + ' done · ' + s.params.f_lo + '–'
              + s.params.f_hi + ' Hz' }),
        el('span', { class: 'pn-set-when', text: BARRY.when
          ? BARRY.when((s.updated || {}).at) : '' }),
      ]));
    }
    box.appendChild(list);
    return box;
  }

  /* ---------- making one ---------- */
  function newBuild() {
    return {
      name: '', region: 'hil', fallback: '', picked: new Set(),
      f_lo: q.f_lo, f_hi: q.f_hi, win_s: q.win_s, sub_s: q.sub_s,
      step_s: q.step_s, bins: q.bins, hist_scale: q.hist_scale,
      t0: q.t0, t1: q.t1, filter: '',
    };
  }

  function buildCard() {
    const b = building;
    const box = el('div', { class: 'card pn-setup' });
    box.appendChild(el('div', { class: 'pn-row', style: 'margin-top:0' }, [
      el('div', { class: 'section-label', style: 'margin:0',
                  text: 'A new set' }),
      el('button', { class: 'btn ghost sm', text: 'Cancel',
                     onclick: () => { building = null; paint(); } }),
    ]));

    box.appendChild(el('div', { class: 'pn-row' }, [
      el('label', { class: 'pn-lab', text: 'Called' }),
      el('input', {
        class: 'inp', type: 'text', value: b.name,
        placeholder: 'PTEN vs littermate, 2-200 Hz',
        oninput: (e) => { b.name = e.target.value; },
      }),
    ]));

    /* The question, frozen once the set exists. Said here rather than
       discovered later. */
    const qrow = el('div', { class: 'pn-row' });
    for (const [k, lab, step, lo, hi, suf] of [
      ['f_lo', 'Frequency', 1, 0.5, 2000, 'Hz'],
      ['f_hi', 'to', 1, 1, 2000, 'Hz'],
      ['win_s', 'Window', 1, 1, 600, 's'],
      ['step_s', 'Step', 0.5, 0.05, 60, 's'],
    ]) {
      qrow.appendChild(el('span', { class: 'pn-field' }, [
        el('label', { class: 'pn-lab', text: lab }),
        el('input', {
          class: 'inp sm pn-num', type: 'number', value: String(b[k]),
          step: String(step), min: String(lo), max: String(hi),
          oninput: (e) => { b[k] = parseFloat(e.target.value); },
        }),
        el('span', { class: 'pn-suffix', text: suf }),
      ]));
    }
    box.appendChild(qrow);
    box.appendChild(el('p', { class: 'hint quiet', text:
      'These are fixed once the set is made. Two recordings measured over '
      + 'different ranges cannot be pooled, and nothing in the file would '
      + 'say so \u2014 so changing them later makes a new set instead.' }));

    /* Which channel. The whole point of a rule is that CSC14 is a different
       depth in every animal. */
    const crow = el('div', { class: 'pn-row' });
    crow.appendChild(el('label', { class: 'pn-lab', text: 'Channel from' }));
    const sel = el('select', {
      class: 'inp sm pn-pick',
      onchange: (e) => { b.region = e.target.value; },
    });
    sel.appendChild(el('option', { value: '', text: 'no rule',
                                   selected: !b.region }));
    for (const r of regions) {
      sel.appendChild(el('option', {
        value: r.id, selected: b.region === r.id,
        text: r.name + (r.note ? ' — ' + r.note : ''),
      }));
    }
    crow.appendChild(sel);
    crow.appendChild(el('span', { class: 'pn-field' }, [
      el('label', { class: 'pn-lab', text: 'else CSC' }),
      el('input', {
        class: 'inp sm pn-num', type: 'number', value: String(b.fallback),
        min: '1', placeholder: 'none',
        oninput: (e) => { b.fallback = e.target.value; },
      }),
    ]));
    box.appendChild(crow);
    box.appendChild(el('p', { class: 'hint quiet', text:
      'The layer sheet says which channel is which in that animal. Without '
      + 'one, a recording is left needing labelling rather than analysed on '
      + 'whatever channel came first \u2014 unless you name a fallback, and '
      + 'those rows say they were a fallback.' }));

    box.appendChild(pickList(b));

    box.appendChild(el('div', { class: 'pn-cost-line' }, [
      el('strong', { text: b.picked.size + ' recording'
        + (b.picked.size === 1 ? '' : 's') + ' chosen' }),
      el('button', {
        class: 'btn', disabled: (!b.picked.size || b.busy) ? 'disabled' : null,
        text: b.busy ? 'Making the set…' : 'Make the set',
        onclick: createSet,
      }),
    ]));
    return box;
  }

  function pickList(b) {
    const wrap = el('div', { class: 'pn-picklist' });
    const rows = (BARRY.views.toolkit && BARRY.views.toolkit.registryRows)
      ? BARRY.views.toolkit.registryRows() : [];
    wrap.appendChild(el('div', { class: 'pn-row' }, [
      el('label', { class: 'pn-lab', text: 'Recordings' }),
      el('input', {
        class: 'inp', type: 'search', value: b.filter,
        placeholder: 'mouse, session, project or date…',
        oninput: (e) => { b.filter = e.target.value; repaintPicks(b); },
      }),
      el('button', {
        class: 'btn ghost sm', text: 'All shown',
        onclick: () => {
          for (const r of matching(b, rows)) b.picked.add(r.gid);
          paint();
        },
      }),
      el('button', {
        class: 'btn ghost sm', text: 'None',
        onclick: () => { b.picked.clear(); paint(); },
      }),
    ]));
    const list = el('div', { class: 'pn-picks', id: 'pnPicks' });
    wrap.appendChild(list);
    fillPicks(list, b, rows);
    return wrap;
  }

  function matching(b, rows) {
    const t = (b.filter || '').trim().toLowerCase();
    const hay = (r) => [r.label, r.key, r.project, r.cohort, r.date,
                        'm' + r.mouse, 's' + r.session]
      .filter(Boolean).join(' ').toLowerCase();
    const got = t ? rows.filter((r) => t.split(/\s+/)
      .every((w) => hay(r).indexOf(w) >= 0)) : rows;
    /* Only what this machine can open. A set of recordings nobody here can
       read is a set that fails one row at a time, forty times. */
    return got.filter((r) => r.reachable !== false);
  }

  function repaintPicks(b) {
    const list = document.getElementById('pnPicks');
    if (!list) return;
    const rows = (BARRY.views.toolkit && BARRY.views.toolkit.registryRows)
      ? BARRY.views.toolkit.registryRows() : [];
    fillPicks(list, b, rows);
  }

  function fillPicks(list, b, rows) {
    list.innerHTML = '';
    const got = matching(b, rows);
    const CAP = 200;
    for (const r of got.slice(0, CAP)) {
      const on = b.picked.has(r.gid);
      list.appendChild(el('button', {
        class: 'pn-pick-row' + (on ? ' on' : ''),
        onclick: (e) => {
          if (on) b.picked.delete(r.gid); else b.picked.add(r.gid);
          e.currentTarget.classList.toggle('on');
          const n = document.querySelector('.pn-cost-line strong');
          if (n) {
            n.textContent = b.picked.size + ' recording'
              + (b.picked.size === 1 ? '' : 's') + ' chosen';
          }
          const btn = document.querySelector('.pn-cost-line .btn');
          if (btn) btn.disabled = !b.picked.size;
        },
      }, [
        el('span', { class: 'pn-tick', text: on ? '✓' : '' }),
        el('span', { text: r.label || r.key }),
        el('span', { class: 'hint quiet', text: r.project || '' }),
      ]));
    }
    if (got.length > CAP) {
      list.appendChild(el('p', { class: 'hint quiet',
        text: CAP + ' of ' + got.length + ' shown — narrow the search' }));
    }
    if (!got.length) {
      list.appendChild(el('p', { class: 'hint',
        text: 'Nothing here matches, or nothing matching is mounted on this '
            + 'machine.' }));
    }
  }

  async function createSet() {
    const b = building;
    if (!b || !b.picked.size) return;
    /* Creating a set writes a record naming every recording in it, and the
       button sat there looking unpressed while that happened. `b.busy` is
       read by the Create button in paint(), so the press registers. */
    if (b.busy) return;
    b.busy = true;
    paint();
    let got;
    try {
      got = await apiPost('/api/panorama/sets', {
        name: b.name, gids: Array.from(b.picked),
        region: b.region || null,
        fallback_channel: b.fallback === '' ? null : parseInt(b.fallback, 10),
        f_lo: b.f_lo, f_hi: b.f_hi, win_s: b.win_s, sub_s: b.sub_s,
        step_s: b.step_s, bins: b.bins, hist_scale: b.hist_scale,
        t0: b.t0, t1: b.t1,
      });
    } catch (e) {
      b.busy = false;
      paint();
      toast(e.message, 'err', 10000);
      return;
    }
    building = null;
    curSet = got.set;
    sets = null;
    loadSets();
    refreshBulkEstimate();
    paint();
  }

  /* ---------- an open set ---------- */
  function setHeadCard() {
    const s = curSet;
    const box = el('div', { class: 'card' });
    box.appendChild(el('div', { class: 'pn-row', style: 'margin-top:0' }, [
      el('button', { class: 'btn ghost sm', text: '← Sets',
                     onclick: () => { curSet = null; stopBulk(); paint(); } }),
      el('div', { class: 'section-label', style: 'margin:0',
                  text: s.name }),
    ]));
    const p = s.params || {};
    box.appendChild(el('div', { class: 'pn-notes' }, [
      el('span', { class: 'pn-note', text: p.f_lo + '–' + p.f_hi + ' Hz' }),
      el('span', { class: 'pn-note',
                   text: p.win_s + ' s windows every ' + p.step_s + ' s' }),
      el('span', { class: 'pn-note', text: p.bins + ' ' + p.hist_scale
                                           + ' bins' }),
      el('span', { class: 'pn-note', text: 'question ' + s.params_hash }),
    ]));

    const counts = {};
    for (const m of s.members) {
      counts[m.status] = (counts[m.status] || 0) + 1;
    }
    const bits = Object.keys(counts).sort()
      .map((k) => counts[k] + ' ' + k).join(' · ');
    const line = el('div', { class: 'pn-cost-line' });
    line.appendChild(el('span', { class: 'hint quiet', text: bits }));
    if (bulkEst && bulkEst.todo) {
      line.appendChild(el('strong', {
        text: bulkEst.todo + ' to do, about '
            + fmtSecs(bulkEst.plan.seconds) }));
    } else if (bulkEst) {
      line.appendChild(el('strong', { text: 'nothing left to do' }));
    }
    const needs = s.members.filter((m) => m.channel === null
                                          || m.channel === undefined);
    if (needs.length) {
      line.appendChild(el('span', { class: 'hint warn',
        text: needs.length + ' need a channel' }));
    }
    line.appendChild(el('button', {
      class: 'btn', disabled: !!bulkJob || (bulkEst && !bulkEst.todo),
      text: bulkJob ? 'Running…'
        : (counts.done ? 'Run the rest' : 'Run'),
      onclick: () => runSet(),
    }));
    box.appendChild(line);
    return box;
  }

  async function refreshBulkEstimate() {
    if (!curSet) return;
    try {
      bulkEst = await apiPost('/api/panorama/sets/' + curSet.set_id
                              + '/estimate', {});
    } catch (e) {
      bulkEst = null;
    }
    paint();
  }

  async function runSet(force) {
    if (!curSet || bulkJob) return;
    let started;
    try {
      started = await apiPost('/api/panorama/sets/' + curSet.set_id + '/run',
                              force ? { force: true } : {});
    } catch (e) {
      toast(e.message, 'err', 10000);
      return;
    }
    if (started.nothing) {
      toast('Every recording in this set has already been answered.', 'ok');
      return;
    }
    bulkJob = started.job;
    paint();
    watchBulk();
  }

  function watchBulk() {
    clearInterval(bulkPoll);
    bulkPoll = setInterval(async () => {
      if (!bulkJob) { clearInterval(bulkPoll); return; }
      let got;
      try { got = await api('/api/cfc/job/' + bulkJob.id); } catch (e) { return; }
      bulkJob = got.job;
      paintBulkRun();
      if (bulkJob.status === 'running') return;
      clearInterval(bulkPoll);
      const done = bulkJob;
      bulkJob = null;
      if (done.status === 'failed') {
        toast(done.error || 'The run failed.', 'err', 12000);
      } else if (done.status === 'canceled') {
        toast('Stopped. What finished is kept — press Run to carry on.',
              'ok', 8000);
      }
      openSet(curSet.set_id);
      refreshBulkEstimate();
    }, 500);
  }

  function stopBulk() {
    clearInterval(bulkPoll);
    bulkJob = null;
  }

  async function cancelBulk() {
    if (!bulkJob) return;
    try { await apiPost('/api/cfc/job/' + bulkJob.id + '/cancel', {}); }
    catch (e) { /* already gone */ }
  }

  function bulkRunCard() {
    const box = el('div', { class: 'card pn-running' });
    box.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: 'Working through the set' }));
    box.appendChild(el('div', { class: 'comod-stages', id: 'pnBulkStages' }));
    box.appendChild(el('div', { class: 'pn-run-foot' }, [
      el('span', { class: 'hint quiet', id: 'pnBulkEta' }),
      el('button', { class: 'btn ghost sm', text: 'Stop',
                     onclick: cancelBulk }),
    ]));
    return box;
  }

  function paintBulkRun() {
    const host = document.getElementById('pnBulkStages');
    if (host && bulkJob) {
      host.innerHTML = '';
      for (const s of (bulkJob.stages || [])) {
        const frac = s.of ? Math.min(s.done / s.of, 1) : 0;
        host.appendChild(el('div', {
          class: 'comod-stage' + (s.status === 'running' ? ' on' : '')
                 + (s.status === 'done' ? ' done' : ''),
        }, [
          el('span', { class: 'comod-tick',
                       text: s.status === 'done' ? '✓' : '▸' }),
          el('span', { class: 'comod-stage-name',
                       text: 'Read and fit every recording' }),
          el('span', { class: 'comod-stage-count',
            text: s.done.toLocaleString() + ' / ' + s.of.toLocaleString()
                + ' s of recording' }),
          el('div', { class: 'comod-mini' }, [
            el('div', { class: 'comod-mini-fill',
                        style: 'width:' + (frac * 100).toFixed(1) + '%' }),
          ]),
        ]));
      }
    }
    const eta = document.getElementById('pnBulkEta');
    if (eta && bulkJob) {
      eta.textContent = bulkJob.eta_s
        ? ('about ' + fmtSecs(bulkJob.eta_s) + ' left — '
           + fmtSecs(bulkJob.elapsed) + ' so far')
        : (fmtSecs(bulkJob.elapsed) + ' so far');
    }
    // The rows, from the job's own per-recording channel.
    for (const m of ((bulkJob || {}).members || [])) {
      const row = document.querySelector('.pn-tree-row[data-gid="' + m.id + '"]');
      if (!row) continue;
      row.className = 'pn-tree-row ' + (m.status || 'waiting');
      const st = row.querySelector('.pn-tree-step');
      if (st) {
        st.textContent = m.error ? m.error
          : (m.step ? m.step + (m.of ? ' ' + Math.round(100 * m.done / m.of)
                                       + '%' : '')
                    : (m.status || ''));
      }
    }
  }

  /* ---------- the tree ---------- */
  function treeCard() {
    const box = el('div', { class: 'card' });
    box.appendChild(el('div', { class: 'pn-row', style: 'margin-top:0' }, [
      el('div', { class: 'section-label', style: 'margin:0',
                  text: 'The recordings' }),
      el('span', { class: 'hint quiet',
                   text: 'click one to see what it found' }),
    ]));
    const head = el('div', { class: 'pn-tree-head' }, [
      el('span', { text: '' }),
      el('span', { text: 'recording' }),
      el('span', { text: 'channel' }),
      el('span', { text: 'dominant' }),
      el('span', { text: 'exponent' }),
      el('span', { text: 'R²' }),
      el('span', { text: 'no peak' }),
      el('span', { text: 'shape' }),
      el('span', { text: '' }),
    ]);
    box.appendChild(head);

    const byProject = {};
    for (const m of curSet.members) {
      const p = m.project || projectOf(m) || '—';
      (byProject[p] = byProject[p] || []).push(m);
    }
    for (const p of Object.keys(byProject).sort()) {
      if (Object.keys(byProject).length > 1) {
        box.appendChild(el('div', { class: 'pn-tree-group', text: p }));
      }
      for (const m of byProject[p]) box.appendChild(treeRow(m));
    }
    return box;
  }

  function projectOf(m) {
    const rows = (BARRY.views.toolkit && BARRY.views.toolkit.registryRows)
      ? BARRY.views.toolkit.registryRows() : [];
    const hit = rows.find((r) => r.gid === m.id);
    return hit ? hit.project : null;
  }

  function treeRow(m) {
    const warn = [];
    if (m.gap_n) warn.push(m.gap_n + ' gap' + (m.gap_n === 1 ? '' : 's'));
    if (m.bad_channel) warn.push('channel marked bad');
    if (m.r2 !== undefined && m.r2 !== null && m.r2 < 0.8) {
      warn.push('fit R² ' + m.r2.toFixed(2));
    }
    if (m.blocked_why) warn.push(m.blocked_why);
    const row = el('div', {
      class: 'pn-tree-row ' + (m.status || 'waiting'),
      'data-gid': m.id,
      /* The close-call rate hangs here rather than on a warning chip. Over
         a wide range it is high for almost every real recording -- 84% on
         the one this was measured against -- so as a per-row warning it
         would mark everything and mean nothing. Where it changes how the
         picture is read is the convergence panel, and it is said there. */
      title: (m.close_call === undefined || m.close_call === null) ? null
        : ('the dominant peak only just won in '
           + (100 * m.close_call).toFixed(0) + '% of windows'),
      onclick: () => showRow(m.id),
    }, [
      el('span', { class: 'pn-dot' }),
      el('span', { class: 'pn-tree-name' }, [
        el('span', { text: m.label || m.id }),
        el('span', { class: 'pn-tree-step',
                     text: m.error || m.blocked_why || m.status || '' }),
      ]),
      el('span', { class: 'pn-tree-ch' }, [
        el('span', { text: m.channel === null || m.channel === undefined
          ? '—' : ('CSC' + m.channel) }),
        el('span', { class: 'pn-from', text: m.channel_from || '' }),
      ]),
      el('span', { text: m.modal_hz ? m.modal_hz.toFixed(2) + ' Hz' : '' }),
      el('span', { text: (m.exponent === undefined || m.exponent === null)
        ? '' : m.exponent.toFixed(2) }),
      el('span', { text: (m.r2 === undefined || m.r2 === null)
        ? '' : m.r2.toFixed(3) }),
      el('span', { text: m.n_windows
        ? (100 * (m.n_nopeak || 0) / m.n_windows).toFixed(0) + '%' : '' }),
      el('canvas', { class: 'pn-spark', 'data-gid': m.id }),
      el('span', { class: 'pn-warn', text: warn.join(' · ') }),
    ]);
    return row;
  }

  /* The sparkline is the histogram this recording found, drawn small. The
     cohort takes shape while the run is still going, which is the whole
     reason it is here rather than in the detail pane. */
  function drawSparks() {
    if (!curSet) return;
    const edges = curSet.edges;
    for (const m of curSet.members) {
      const cv = document.querySelector('.pn-spark[data-gid="' + m.id + '"]');
      if (!cv || !m.spark || !m.spark.length) continue;
      const w = 84, h = 22;
      const dpr = window.devicePixelRatio || 1;
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
      cv.style.width = w + 'px';
      cv.style.height = h + 'px';
      const g = cv.getContext('2d');
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      const top = Math.max.apply(null, m.spark) || 1;
      g.fillStyle = BARRY.token('--accent', '#FFB81C');
      const n = m.spark.length;
      for (let i = 0; i < n; i += 1) {
        if (!m.spark[i]) continue;
        const x = (i / n) * w;
        const bw = Math.max(1, w / n);
        const bh = (m.spark[i] / top) * (h - 2);
        g.fillRect(x, h - bh, bw, bh);
      }
      if (edges) cv.title = 'peak near ' + (m.modal_hz || 0).toFixed(1) + ' Hz';
    }
  }


  /* ==================================================================
     Converging

     The reason a set exists. Every recording's dominant-frequency
     histogram, pooled into one curve per group.

     Two defaults here are arguments rather than conveniences, and both are
     spelled out in panoramaset.py: one vote per RECORDING, because the
     sampling unit is the animal and windows inside a recording are
     correlated; and a denominator of windows that HAVE a peak, because a
     genotype that abolishes a rhythm has to show up as an absence rather
     than as a slightly shorter curve.
     ================================================================== */
  const GROUP_COLORS = ['#154734', '#d1495b', '#30638e', '#8a6fbf',
                        '#a86a00', '#3f6b35', '#7c7c7c'];

  let convSeq = 0;
  async function loadConverge() {
    if (!curSet) { conv = null; return; }
    const mine = ++convSeq;
    let got;
    try {
      got = await apiPost('/api/panorama/sets/' + curSet.set_id + '/converge',
                          convOpts);
    } catch (e) {
      got = null;
    }
    if (mine !== convSeq) return;
    conv = got ? got.converged : null;
    paint();
  }

  function convergeCard() {
    const box = el('div', { class: 'card pn-step' });
    box.appendChild(stepHead('\u25c9', 'Converged',
      'every recording\u2019s histogram, pooled by group'));

    const done = (curSet.members || [])
      .filter((m) => m.status === 'done').length;
    if (done < 1) {
      box.appendChild(el('p', { class: 'hint', text:
        'Nothing has been run yet. The pooled picture appears as soon as '
        + 'the first recording finishes, and fills in as the rest land.' }));
      return box;
    }
    box.appendChild(convControls());
    if (!conv) {
      box.appendChild(el('div', { class: 'tk-loading' }, [
        stepLoader('Panorama', ['pooling the histograms'])]));
      return box;
    }
    box.appendChild(el('div', { class: 'pn-conv' }, [
      el('canvas', { class: 'pn-canvas pn-conv-main', id: 'pnConv' }),
      el('div', { class: 'pn-conv-strips' }, [
        el('canvas', { class: 'pn-canvas', id: 'pnStripHz' }),
        el('canvas', { class: 'pn-canvas', id: 'pnStripNo' }),
      ]),
    ]));
    box.appendChild(convLegend());
    box.appendChild(convNotes());
    box.appendChild(convSaveRow());
    return box;
  }

  function convControls() {
    const wrap = el('div', { class: 'pn-row' });

    wrap.appendChild(el('label', { class: 'pn-lab', text: 'Group by' }));
    const sel = el('select', {
      class: 'inp sm pn-pick',
      onchange: (e) => {
        const v = e.target.value;
        if (v.indexOf('attr:') === 0) {
          convOpts.grouping = 'auto';
          convOpts.attr = v.slice(5);
        } else {
          convOpts.grouping = v;
        }
        conv = null;
        loadConverge();
        paint();
      },
    });
    for (const a of (conv && conv.attributes) || [{ id: 'group',
                                                    name: 'Group' }]) {
      sel.appendChild(el('option', {
        value: 'attr:' + a.id,
        selected: convOpts.grouping === 'auto' && convOpts.attr === a.id,
        text: a.name + (a.n ? ' (' + a.n + ' mice)' : ''),
      }));
    }
    wrap.appendChild(sel);

    wrap.appendChild(el('span', { class: 'pn-gap' }));
    wrap.appendChild(el('label', { class: 'pn-lab', text: 'Dominant' }));
    for (const [id, name, why] of [
      ['peak', 'tallest peak', 'The rhythm the fit found. A window with '
        + 'none counts as no peak, and that is plotted in its own right.'],
      ['flat', 'flattened argmax', 'Always returns a number, so quiet '
        + 'windows vote too \u2014 usually near the bottom of the range.'],
    ]) {
      wrap.appendChild(el('button', {
        class: 'pill' + (convOpts.dominant === id ? ' active' : ''),
        title: why, text: name,
        onclick: () => {
          convOpts.dominant = id; conv = null; loadConverge(); paint();
        },
      }));
    }

    wrap.appendChild(el('span', { class: 'pn-gap' }));
    wrap.appendChild(el('label', { class: 'pn-lab', text: 'Weight' }));
    for (const [id, name, why] of [
      ['session', 'per recording', 'One vote each. The sampling unit is the '
        + 'recording, and windows inside one are not independent.'],
      ['window', 'by length', 'Pooled counts, so a longer recording counts '
        + 'for more. Occasionally the question; never the default.'],
    ]) {
      wrap.appendChild(el('button', {
        class: 'pill' + (convOpts.weight === id ? ' active' : ''),
        title: why, text: name,
        onclick: () => {
          convOpts.weight = id; conv = null; loadConverge(); paint();
        },
      }));
    }

    if (convOpts.weight === 'session') {
      wrap.appendChild(el('span', { class: 'pn-gap' }));
      for (const [id, name, why] of [
        ['sem', '\u00b1SEM', 'Across recordings.'],
        ['iqr', 'median + IQR', 'Densities are right-skewed, so an SEM band '
          + 'can cross zero in the tails.'],
      ]) {
        wrap.appendChild(el('button', {
          class: 'pill' + (convOpts.spread === id ? ' active' : ''),
          title: why, text: name,
          onclick: () => { convOpts.spread = id; paint(); },
        }));
      }
    }
    return wrap;
  }

  function convLegend() {
    const wrap = el('div', { class: 'pn-conv-key' });
    (conv.groups || []).forEach((g, i) => {
      const nm = (conv.names || {})[g.id] || g.id;
      wrap.appendChild(el('span', { class: 'pn-key' }, [
        el('i', { style: 'background:' + GROUP_COLORS[i % GROUP_COLORS.length] }),
        el('span', { text: nm + ' (n=' + g.n + ')' }),
        g.nopeak_mean === null || g.nopeak_mean === undefined
          ? null
          : el('span', { class: 'hint quiet',
              text: (100 * g.nopeak_mean).toFixed(0) + '% no peak' }),
      ]));
    });
    return wrap;
  }

  /* What the picture is NOT showing, said out loud. Six recordings short
     with nothing to say so is how they vanish from a figure. */
  function convNotes() {
    const bits = [];
    if ((conv.not_run || []).length) {
      bits.push(conv.not_run.length + ' not run yet');
    }
    if ((conv.no_windows || []).length) {
      bits.push(conv.no_windows.length + ' had no analysable windows and are '
        + 'left out rather than counted as zero');
    }
    if ((conv.in_several_groups || []).length) {
      bits.push(conv.in_several_groups.length + ' are in more than one group '
        + 'on this axis \u2014 pick a facet, or they count twice');
    }
    const ung = (conv.groups || []).find((g) => g.id === '__ungrouped__');
    if (ung) bits.push(ung.n + ' have no group and are shown apart');

    const box = el('div');
    if (bits.length) {
      box.appendChild(el('p', { class: 'hint warn', text: bits.join(' · ') }));
    }
    /* How often "the tallest peak" was a coin toss. Not a fault in the
       data: over a wide range a 1/f spectrum has several broad bumps of
       similar height, and which one wins is then arbitrary. It belongs
       here, where somebody is about to read a group difference off the
       curve. */
    if (conv.close_call_frac !== undefined && conv.close_call_frac !== null
        && conv.dominant === 'peak') {
      const pct = 100 * conv.close_call_frac;
      box.appendChild(el('p', { class: 'hint' + (pct > 50 ? ' warn' : ''),
        text: 'The dominant peak won by less than a fifth in '
            + pct.toFixed(0) + '% of windows. Over a wide range that is '
            + 'usual — a 1/f spectrum has several broad bumps of '
            + 'similar height, and which is tallest is then close to '
            + 'arbitrary. Narrowing the frequency range, or reading this '
            + 'beside the no-peak panel, is worth doing before calling a '
            + 'difference real.' }));
    }
    return box;
  }

  function convSaveRow() {
    const wrap = el('div', { class: 'pn-cost-line' });
    if (convSaved) {
      wrap.appendChild(el('span', { class: 'hint ok',
        text: 'Saved ' + convSaved.files.length + ' files to '
            + convSaved.folder }));
      wrap.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Show me in Results',
        onclick: () => setView('results'),
      }));
      return wrap;
    }
    wrap.appendChild(el('span', { class: 'hint quiet', text:
      'the figure, one row per recording, and every histogram long-form' }));
    wrap.appendChild(el('button', {
      class: 'btn', disabled: convSaving,
      text: convSaving ? 'Saving…' : 'Save the convergence',
      onclick: saveConverge,
    }));
    return wrap;
  }

  async function saveConverge() {
    if (convSaving || !curSet) return;
    convSaving = true; paint();
    try {
      convSaved = await apiPost('/api/panorama/sets/' + curSet.set_id
                                + '/save', convOpts);
      toast('Saved to Results.', 'ok');
    } catch (e) {
      toast(e.message, 'err', 10000);
    } finally {
      convSaving = false;
      paint();
    }
  }

  /* ---------- drawing it ---------- */
  function drawConverge() {
    if (!conv) return;
    drawConvMain();
    drawStrip('pnStripHz', 'modal_hz', 'dominant frequency (Hz)', 1);
    drawStrip('pnStripNo', 'nopeak_frac', 'windows with no peak (%)', 100);
  }

  function drawConvMain() {
    const c = sizeCanvas('pnConv', 0.52, 240, 420);
    if (!c) return;
    const { g, W, H } = c;
    const k = ink();
    const x = conv.centres || [];
    if (x.length < 2) return;
    const L = 58, R = 12, T = 12, B = 34;

    let top = 0;
    for (const grp of conv.groups || []) {
      for (let i = 0; i < grp.mean.length; i += 1) {
        top = Math.max(top, grp.mean[i] + (grp.sem[i] || 0));
      }
    }
    for (const s of conv.sessions || []) {
      for (const v of s.density) top = Math.max(top, v);
    }
    top = top || 1;

    const lx = x.map((v) => Math.log10(v));
    const xlo = lx[0], xhi = lx[lx.length - 1];
    const sx = (v) => L + (v - xlo) / (xhi - xlo) * (W - L - R);
    const sy = (v) => H - B - (v / top) * (H - T - B);

    // Named bands behind, so a peak can be placed without counting across.
    g.font = '10px system-ui, sans-serif';
    for (const [name, lo, hi] of NAMED) {
      const a = sx(Math.log10(Math.max(lo, x[0])));
      const b = sx(Math.log10(Math.min(hi, x[x.length - 1])));
      if (!(b > a)) continue;
      g.fillStyle = k.faint; g.globalAlpha = 0.22;
      g.fillRect(a, T, b - a, H - T - B);
      g.globalAlpha = 1;
      if (b - a > 30) {
        g.fillStyle = k.dim; g.textAlign = 'center';
        g.fillText(name, (a + b) / 2, T + 10);
      }
    }

    const colorOf = {};
    (conv.groups || []).forEach((grp, i) => {
      colorOf[grp.id] = GROUP_COLORS[i % GROUP_COLORS.length];
    });

    // The individual recordings, behind the means.
    g.lineWidth = 1;
    for (const s of conv.sessions || []) {
      const gid = (s.groups || [])[0] || '__ungrouped__';
      g.strokeStyle = colorOf[gid] || k.dim;
      g.globalAlpha = 0.28;
      g.beginPath();
      s.density.forEach((v, i) => {
        const px = sx(lx[i]), py = sy(v);
        if (i === 0) g.moveTo(px, py); else g.lineTo(px, py);
      });
      g.stroke();
      g.globalAlpha = 1;
    }

    for (const grp of conv.groups || []) {
      const col = colorOf[grp.id];
      const mid = convOpts.spread === 'iqr' ? grp.median : grp.mean;
      const lo = convOpts.spread === 'iqr'
        ? grp.q1 : grp.mean.map((v, i) => v - (grp.sem[i] || 0));
      const hi = convOpts.spread === 'iqr'
        ? grp.q3 : grp.mean.map((v, i) => v + (grp.sem[i] || 0));
      const anySpread = hi.some((v, i) => v > lo[i]);
      if (anySpread) {
        g.fillStyle = col; g.globalAlpha = 0.16;
        g.beginPath();
        hi.forEach((v, i) => {
          const px = sx(lx[i]), py = sy(Math.max(0, v));
          if (i === 0) g.moveTo(px, py); else g.lineTo(px, py);
        });
        for (let i = lo.length - 1; i >= 0; i -= 1) {
          g.lineTo(sx(lx[i]), sy(Math.max(0, lo[i])));
        }
        g.closePath(); g.fill();
        g.globalAlpha = 1;
      }
      g.strokeStyle = col; g.lineWidth = 2;
      g.beginPath();
      mid.forEach((v, i) => {
        const px = sx(lx[i]), py = sy(v);
        if (i === 0) g.moveTo(px, py); else g.lineTo(px, py);
      });
      g.stroke();
      g.lineWidth = 1;
    }

    g.strokeStyle = k.faint;
    g.beginPath(); g.moveTo(L, T); g.lineTo(L, H - B); g.lineTo(W - R, H - B);
    g.stroke();
    g.fillStyle = k.dim; g.textAlign = 'center';
    for (const t of [2, 4, 8, 12, 20, 30, 60, 120, 200]) {
      const lv = Math.log10(t);
      if (lv < xlo || lv > xhi) continue;
      g.fillText(String(t), sx(lv), H - B + 14);
    }
    g.fillText('dominant frequency (Hz)', (W + L) / 2, H - 4);
    g.textAlign = 'right';
    g.fillText(top.toPrecision(2), L - 6, T + 8);
    g.fillText('0', L - 6, H - B);
    g.save();
    g.translate(12, (H - B + T) / 2);
    g.rotate(-Math.PI / 2);
    g.textAlign = 'center';
    g.fillText('per analysed window, per Hz', 0, 0);
    g.restore();
  }

  /* One dot per recording. This, not the pooled curve, is what a test gets
     run on -- so it is drawn beside it rather than somewhere else. */
  function drawStrip(id, field, ylabel, scale) {
    const c = sizeCanvas(id, 0.72, 150, 240);
    if (!c) return;
    const { g, W, H } = c;
    const k = ink();
    const L = 44, R = 8, T = 10, B = 30;
    const groups = (conv.groups || []).filter((grp) => grp.id);
    if (!groups.length) return;

    const byGroup = groups.map((grp) => {
      const rows = (conv.sessions || []).filter(
        (s) => ((s.groups || [])[0] || '__ungrouped__') === grp.id);
      return rows.map((s) => s[field]).filter((v) => v !== null
                                                  && v !== undefined)
        .map((v) => v * scale);
    });
    let top = 0, bot = Infinity;
    for (const vals of byGroup) {
      for (const v of vals) { top = Math.max(top, v); bot = Math.min(bot, v); }
    }
    if (!isFinite(bot)) return;
    const pad = (top - bot) * 0.12 || Math.max(1, top * 0.1);
    top += pad; bot = Math.max(0, bot - pad);
    const sy = (v) => H - B - (v - bot) / ((top - bot) || 1) * (H - T - B);
    const cx = (i) => L + (i + 0.5) / groups.length * (W - L - R);

    g.font = '10px system-ui, sans-serif';
    groups.forEach((grp, i) => {
      const col = GROUP_COLORS[i % GROUP_COLORS.length];
      const vals = byGroup[i];
      const half = (W - L - R) / groups.length * 0.18;
      g.fillStyle = col;
      vals.forEach((v, j) => {
        // Spread on x so two recordings at the same value are two dots.
        const jitter = ((j % 5) - 2) / 2 * half * 0.7;
        g.beginPath();
        g.arc(cx(i) + jitter, sy(v), 3, 0, Math.PI * 2);
        g.fill();
      });
      if (vals.length) {
        const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
        g.strokeStyle = col; g.lineWidth = 2;
        g.beginPath();
        g.moveTo(cx(i) - half, sy(mean));
        g.lineTo(cx(i) + half, sy(mean));
        g.stroke();
        g.lineWidth = 1;
      }
      g.fillStyle = k.dim; g.textAlign = 'center';
      const nm = (conv.names || {})[grp.id] || 'ungrouped';
      g.fillText(nm.length > 12 ? nm.slice(0, 12) : nm, cx(i), H - B + 13);
      g.fillText('n=' + vals.length, cx(i), H - B + 24);
    });

    g.strokeStyle = k.faint;
    g.beginPath(); g.moveTo(L, T); g.lineTo(L, H - B); g.lineTo(W - R, H - B);
    g.stroke();
    g.fillStyle = k.dim; g.textAlign = 'right';
    g.fillText(top.toPrecision(3), L - 5, T + 8);
    g.fillText(bot.toPrecision(3), L - 5, H - B);
    g.save();
    g.translate(11, (H - B + T) / 2);
    g.rotate(-Math.PI / 2);
    g.textAlign = 'center';
    g.fillText(ylabel, 0, 0);
    g.restore();
  }

  /* ---------- one row's answer ---------- */
  async function showRow(gid) {
    if (openRow === gid) { openRow = null; rowRes = null; paint(); return; }
    openRow = gid;
    rowRes = null;
    paint();
    try {
      const got = await api('/api/panorama/sets/' + curSet.set_id
                            + '/result/' + encodeURIComponent(gid));
      rowRes = got.result;
    } catch (e) {
      rowRes = { error: e.message };
    }
    paint();
  }

  /* A stored record, shaped like the payload the one-recording panes draw.
     The picture comes from the cache by URL rather than riding in the
     record -- see the note at the top of panoramaset.py. */
  function fromStored(r) {
    if (!r || r.error) return null;
    const img = Object.assign({}, r.image || {});
    img.png = '/api/panorama/sets/' + curSet.set_id + '/spectrogram/'
            + encodeURIComponent(r.gid) + '.png';
    return {
      index: r.channel, label: r.channel_label, number: r.channel_number,
      bad: r.bad_channel, gaps: r.gaps, spectrogram: img,
      freqs: r.freqs, psd: r.psd, fit: r.fit, line_at: r.line_at,
      hist: {
        edges: r.edges, peak: r.counts_peak, flat: r.counts_flat,
        scale: r.hist_scale, bins: (r.edges || []).length - 1,
        n_windows: r.n_windows, n_used: r.n_used,
        n_nopeak: r.n_nopeak, n_rejected: r.n_rejected,
      },
      modal_hz: r.modal_hz, median_hz: r.median_hz,
    };
  }

  function rowCard() {
    const box = el('div', { class: 'card pn-step' });
    const m = (curSet.members || []).find((x) => x.id === openRow) || {};
    box.appendChild(el('div', { class: 'pn-step-head' }, [
      el('strong', { text: m.label || openRow }),
      el('span', { class: 'hint quiet',
                   text: m.channel ? 'CSC' + m.channel + ' · '
                                     + (m.channel_from || '') : '' }),
      el('button', { class: 'btn ghost sm', text: 'Close',
                     onclick: () => { openRow = null; rowRes = null; paint(); } }),
    ]));
    if (!rowRes) {
      box.appendChild(el('div', { class: 'tk-loading' }, [
        stepLoader('Panorama', ['reading what it found'])]));
      return box;
    }
    if (rowRes.error) {
      box.appendChild(el('p', { class: 'hint bad', text: rowRes.error }));
      return box;
    }
    const stored = fromStored(rowRes);
    if (!stored) return box;
    const grid = el('div', { class: 'pn-grid' });
    grid.appendChild(spectrogramPane(stored));
    grid.appendChild(histogramPane(stored));
    box.appendChild(grid);
    box.appendChild(el('canvas', { class: 'pn-canvas pn-psd', id: 'pnPsd' }));
    return box;
  }

  /* Point it at a recording without going through the picker.

     For the dev harness, which has to establish its own starting state
     rather than assume one, and for anything that later wants to hand a
     recording straight to this tool the way Incisor takes one. */
  function openRecording(path, opts) {
    const o = opts || {};
    q.path = path || null;
    q.gid = o.gid || null;
    q.label = o.label || null;
    q.channels = o.channels || [];
    q.t0 = (o.t0 === undefined ? null : o.t0);
    q.t1 = (o.t1 === undefined ? null : o.t1);
    reset();
    refreshEstimate();
    paint();
  }

  return {
    paint,
    run,
    reset,
    openRecording,
    setMode: (m) => { mode = m; if (m === 'many' && !sets) loadSets();
                      paint(); },
    get mode() { return mode; },
    get sets() { return sets; },
    get set() { return curSet; },
    openSet,
    runSet,
    get bulkJob() { return bulkJob; },
    startBuild: () => { building = newBuild(); paint(); return building; },
    get building() { return building; },
    createSet,
    showRow,
    loadConverge,
    get converged() { return conv; },
    get convOpts() { return convOpts; },
    saveConverge,
    get state() { return q; },
    get estimate() { return est; },
    get result() { return res; },
    get running() { return !!job; },
  };
}());

window.barryPanorama = BARRY.panorama;
