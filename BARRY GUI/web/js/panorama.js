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
      host.appendChild(setupCard());
      if (job) host.appendChild(runCard());
      if (res) {
        host.appendChild(holisticCard());
        host.appendChild(spectrumCard());
        host.appendChild(saveCard());
      }
    });
    drawAll();
  }

  function current() {
    if (!res) return null;
    const rows = res.channels || [];
    return rows[Math.min(shown, rows.length - 1)] || null;
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

    box.appendChild(channelRow());
    box.appendChild(rangeRow());
    box.appendChild(windowRow());
    box.appendChild(pictureRow());
    box.appendChild(costRow());
    return box;
  }

  function channelRow() {
    const wrap = el('div', { class: 'pn-row' });
    wrap.appendChild(el('label', { class: 'pn-lab', text: 'Channel' }));
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
    wrap.appendChild(num('t0', 'From', 1, 0, dur, 's'));
    wrap.appendChild(num('t1', 'to', 1, 0, dur, 's'));
    wrap.appendChild(el('span', { class: 'hint quiet',
      text: (q.t0 || q.t1)
        ? ('of ' + fmtDur(dur))
        : ('the whole recording, ' + fmtDur(dur)) }));
    wrap.appendChild(el('span', { class: 'pn-gap' }));
    wrap.appendChild(num('f_lo', 'Frequency', 1, 0.5, 2000, 'Hz'));
    wrap.appendChild(num('f_hi', 'to', 1, 1, 2000, 'Hz'));
    return wrap;
  }

  function windowRow() {
    const wrap = el('div', { class: 'pn-row' });
    wrap.appendChild(num('win_s', 'Window', 1, 1, 600, 's'));
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
    opts.appendChild(radio('peak', 'tallest fitted peak',
      'The rhythm the fit actually found. A window with none counts as '
      + '“no peak”, which is a finding rather than a gap.'));
    opts.appendChild(radio('flat', 'flattened argmax',
      'The highest bin once the aperiodic slope is removed. Always returns '
      + 'a number, so quiet windows vote too — usually near the bottom of '
      + 'the range.'));
    pane.appendChild(opts);

    const opts2 = el('div', { class: 'pn-opts' });
    opts2.appendChild(el('span', { class: 'pn-lab', text: 'Bins' }));
    opts2.appendChild(el('input', {
      class: 'inp sm pn-num', type: 'number', value: String(q.bins),
      'data-fk': 'bins',
      min: '4', max: '400', step: '4',
      oninput: (e) => {
        const v = parseInt(e.target.value, 10);
        if (v >= 4 && v <= 400) { q.bins = v; reset(); refreshEstimate(); }
      },
    }));
    for (const s of ['log', 'linear']) {
      opts2.appendChild(el('button', {
        class: 'pill' + (q.hist_scale === s ? ' active' : ''),
        text: s,
        onclick: () => { q.hist_scale = s; reset(); refreshEstimate(); paint(); },
      }));
    }
    pane.appendChild(opts2);

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
    get state() { return q; },
    get estimate() { return est; },
    get result() { return res; },
    get running() { return !!job; },
  };
}());

window.barryPanorama = BARRY.panorama;
