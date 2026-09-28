/* ==========================================================================
   horizon.js -- every channel of the probe, by depth, across the session.

   Step one of The Lookout. Panorama answers "which frequency was in charge"
   for one channel; this asks it of all of them and stacks the answers by
   depth, so the same picture carries time across and the shank down.

   WHAT IS DRAWN WHERE, AND WHY IT IS SPLIT THAT WAY

   The map arrives as a PNG and everything else arrives as numbers, which is
   the split Panorama makes and for the same reason. The map is sixty-four
   rows by a few hundred columns with a per-pixel opacity on it; encoding
   that array server-side is pixel-exact and small, and there is nothing a
   canvas could do with it that the image does not already do. The agreement
   strip and the depth profile are read off by eye and rescaled, so they come
   as numbers and are drawn here.

   Axes are never baked into the image. They go on a canvas laid over it, so
   they stay crisp, follow the theme, and do not end up in an export.

   THE COLOUR BAR IS STEPPED, AND THAT IS THE POINT

   Twelve swatches of one Hz each, because a reader can NAME a frequency
   from a swatch when there are twelve and can only say "warmer" when it is
   a smooth ramp. Theta is bracketed on the bar rather than being the whole
   bar -- see the module docstring in backend/horizon.py for why the range
   is 2-14 and not 4-12.
   ========================================================================== */
BARRY.horizon = (function () {

  /* Every setting, in one place and never read back off the DOM -- a
     redraw must not be able to lose what somebody typed. */
  const q = {
    gid: null, path: null, label: null,
    channels: [],            // empty means every good channel
    t0: null, t1: null,
    f_lo: 2, f_hi: 14,
    fit_lo: 2, fit_hi: 100,
    sub_s: 2, win_s: 8, step_s: 1, every: 5,
    fidelity: 'survey',
    bin_hz: 1,
    cmap: 'viridis',
    colour_mode: 'absolute',
  };

  let info = null;         // what /for-recording said
  let est = null;          // what /estimate said
  let out = null;          // the finished result
  let job = null;          // the running job
  let preview = null;      // the picture as it arrives
  let busy = false;
  let watching = false;
  let err = null;
  let estSeq = 0;
  let infoSeq = 0;

  function body() {
    return {
      path: q.path,
      channels: q.channels.length ? q.channels : null,
      t0: q.t0, t1: q.t1,
      f_lo: q.f_lo, f_hi: q.f_hi,
      fit_lo: q.fit_lo, fit_hi: q.fit_hi,
      sub_s: q.sub_s, win_s: q.win_s, step_s: q.step_s, every: q.every,
      fidelity: q.fidelity, bin_hz: q.bin_hz,
      cmap: q.cmap, colour_mode: q.colour_mode,
    };
  }

  function reset() {
    out = null; job = null; preview = null; err = null; est = null;
  }

  /* ---------------------------------------------------------------- data */

  const refreshEstimate = debounce(async function refreshEstimate_() {
    if (!q.path) { est = null; paint(); return; }
    const mine = ++estSeq;
    let got;
    try { got = await apiPost('/api/horizon/estimate', body()); }
    catch (e) { got = { error: e.message }; }
    if (mine !== estSeq) return;          // a later edit superseded this
    est = got;
    paint();
  }, 250);

  async function loadInfo(gid) {
    const mine = ++infoSeq;
    info = null;
    paint();
    let got;
    try {
      got = await api('/api/horizon/for-recording/' + encodeURIComponent(gid));
    } catch (e) {
      got = { error: e.message };
    }
    if (mine !== infoSeq) return;
    info = got;
    paint();
  }

  /* ---------------------------------------------------------------- paint */

  function paint() {
    /* Fails closed. Every async path above can land after somebody has moved
       to another tool, and painting into #tkResult then would put this
       panel inside whatever is there now. */
    if (!BARRY.views.toolkit || BARRY.views.toolkit.tool() !== 'horizon') return;
    const host = document.getElementById('tkResult');
    if (!host) return;
    host.innerHTML = '';
    host.appendChild(BARRY.ui.stepHeader({
      title: 'Horizon',
      step: (BARRY.views.toolkit.stepOf
             && BARRY.views.toolkit.stepOf('horizon')) || null,
      blurb: 'Which frequency was in charge, on every channel, all the way '
           + 'down the probe and all the way through the session.',
    }));
    host.appendChild(pickCard());
    if (q.path && info && !info.blocked) {
      host.appendChild(settingsCard());
      host.appendChild(runCard());
    }
    if (busy || job) {
      host.appendChild(waitCard());
      /* Come back to a run that is still going and start watching it again.
         The poll stops itself when this is not the tool on screen (see
         `watch`), so without this, leaving and returning would leave a
         finished job sitting unread behind a loader. */
      if (job && !watching) watch();
    }
    if (out) {
      host.appendChild(mapCard());
      host.appendChild(saveCard());
    }
    if (!q.path) host.appendChild(emptyCard());
    requestAnimationFrame(drawAll);
  }

  /* ---- which recording --------------------------------------------------

     The New curation set wizard's shape, because it is the one that gets
     this right: pick a recording and it says what is already true of it
     before anything else is chosen. Here that is how many channels there
     are, how many are marked bad, which probe template applies and whether
     anybody confirmed it, and whether there is a layer sheet to name the
     bands with. All of it is knowable before a run and useless after one. */
  function pickCard() {
    const box = el('div', { class: 'card hz-pick' });
    const rows = (BARRY.views.toolkit && BARRY.views.toolkit.registryRows)
      ? BARRY.views.toolkit.registryRows() : [];
    box.appendChild(BARRY.ui.field({
      label: 'Recording',
      control: BARRY.pickSession({
        rows, value: q.gid,
        placeholder: 'Which recording? Type a mouse, session or date…',
        onpick: (r) => {
          q.gid = r.gid;
          q.path = (r.here || [])[0] || null;
          q.label = r.label || r.key || null;
          q.channels = [];
          q.t0 = null; q.t1 = null;
          reset();
          if (q.gid) loadInfo(q.gid);
          refreshEstimate();
          paint();
        },
      }),
    }));
    if (!q.gid) return box;

    if (!info) {
      box.appendChild(el('div', { class: 'tk-loading' }, [
        loader('Reading what is already known about it')]));
      return box;
    }
    if (info.error) {
      box.appendChild(el('p', { class: 'confirm-sub warn', text: info.error }));
      return box;
    }
    if (info.blocked) {
      box.appendChild(el('p', { class: 'confirm-sub warn', text: info.blocked }));
      return box;
    }

    const chips = [
      BARRY.ui.chip(info.n_usable + ' of ' + info.n_channels + ' channels',
                    { kind: info.n_usable ? 'ok' : 'err',
                      title: info.n_bad
                        ? (info.n_bad + ' marked bad: CSC '
                           + (info.bad || []).join(', '))
                        : 'None marked bad' }),
    ];
    const pr = info.probe || {};
    chips.push(BARRY.ui.chip(
      pr.short || '?',
      { kind: pr.state === 'confirmed' ? 'ok'
              : (pr.state === 'detected' ? 'warn' : null),
        title: pr.why || '' }));
    if ((info.panes || []).length > 1) {
      chips.push(BARRY.ui.chip((info.panes || []).length + ' stacks',
                               { kind: 'warn',
                                 title: 'This probe is drawn as one pane per '
                                      + 'column, because consecutive channel '
                                      + 'numbers are not adjacent depths on '
                                      + 'it.' }));
    }
    const ly = info.layers || {};
    chips.push(BARRY.ui.chip(ly.have ? (ly.n_labelled + ' labelled')
                                     : 'no layer sheet',
                             { kind: ly.have ? 'ok' : null,
                               title: ly.note || '' }));
    box.appendChild(BARRY.ui.chipRow(chips));

    /* The probe is the one that can silently be wrong, so it says so in a
       sentence rather than only in a chip's title. A detected template is
       USED -- a dual implant drawn as one stack is worse than one drawn as
       two and marked unconfirmed -- but it is never presented as a fact. */
    if (pr.state !== 'confirmed') {
      box.appendChild(el('p', { class: 'hint', text:
        (pr.state === 'detected'
          ? 'The probe is a guess: ' : 'The probe is not known: ')
        + (pr.why || '')
        + ' The depth axis will be channel order, which is right for a '
        + 'linear array and wrong for an interleaved one. Confirm it on the '
        + 'recording to be sure.' }));
    }
    if (!ly.have) {
      box.appendChild(el('p', { class: 'hint', text: ly.note || '' }));
    }
    return box;
  }

  function emptyCard() {
    return el('div', { class: 'card' }, [
      el('div', { class: 'empty-state' }, [
        el('strong', { text: 'Pick a recording' }),
        el('p', { class: 'hint', text:
          'Horizon reads every channel that is not marked bad, works out '
          + 'which frequency was on top in each window of each one, and '
          + 'stacks them by depth. Vertical stripes mean the whole column '
          + 'agrees; horizontal bands mean the layers do not.' }),
      ]),
    ]);
  }

  /* ---- what to ask it --------------------------------------------------- */

  function num(value, on, o) {
    const opt = o || {};
    return el('input', {
      type: 'number', class: 'mini', value: String(value),
      min: opt.min, max: opt.max, step: opt.step || 'any',
      onchange: (e) => {
        const v = parseFloat(e.target.value);
        if (!isNaN(v)) { on(v); reset(); refreshEstimate(); paint(); }
      },
    });
  }

  function settingsCard() {
    const box = el('div', { class: 'card hz-set' });

    box.appendChild(BARRY.ui.field({
      label: 'Band',
      inline: true,
      control: el('div', { class: 'ctl-seg' }, [
        num(q.f_lo, (v) => { q.f_lo = v; }, { min: 0.5, max: 200 }),
        el('span', { class: 'hint', text: 'to' }),
        num(q.f_hi, (v) => { q.f_hi = v; }, { min: 1, max: 400 }),
        el('span', { class: 'hint', text: 'Hz' }),
      ]),
      hint: 'The band the map is coloured by. 2-14 rather than 4-12 so the '
          + 'shoulders are visible: a hard theta window makes every cell '
          + 'report a theta even where there is none. Theta is bracketed on '
          + 'the bar.',
    }));

    box.appendChild(BARRY.ui.field({
      label: 'Colour bar step',
      inline: true,
      control: BARRY.ui.seg(
        [[0.5, '0.5 Hz'], [1, '1 Hz'], [2, '2 Hz']], q.bin_hz,
        (v) => { q.bin_hz = v; recolour(); }),
      hint: 'Stepped rather than smooth, because a dozen swatches can be '
          + 'named and a continuous ramp can only be called warmer. The '
          + 'transform resolves 0.5 Hz, so 1 Hz is inside what was measured.',
    }));

    box.appendChild(BARRY.ui.field({
      label: 'Colour',
      inline: true,
      control: el('div', { class: 'ctl-seg' }, [
        el('select', {
          class: 'mini',
          onchange: (e) => { q.cmap = e.target.value; recolour(); },
        }, ((est && est.colormaps) || []).map((c) => el('option', {
          value: c.id, text: c.name, title: c.note,
          selected: c.id === q.cmap ? 'selected' : null,
        }))),
        BARRY.ui.seg([['absolute', 'Absolute'], ['relative', 'vs median']],
                     q.colour_mode,
                     (v) => { q.colour_mode = v; recolour(); }),
      ]),
      hint: 'Not Jet by default: a rainbow invents edges in smooth data, and '
          + 'this is a tool for reading whether a band is there. '
          + '"vs median" centres on this recording’s own usual, which '
          + 'is what makes a drift through the session legible.',
    }));

    box.appendChild(BARRY.ui.field({
      label: 'Fidelity',
      inline: true,
      control: BARRY.ui.seg(
        [['survey', 'Survey'], ['full', 'Full']], q.fidelity,
        (v) => { q.fidelity = v; reset(); refreshEstimate(); paint(); }),
      hint: q.fidelity === 'survey'
        ? 'One aperiodic fit per channel, on its mean spectrum, then the '
          + 'argmax of every flattened column. Minutes.'
        : 'The real per-window fit, the same one Panorama uses — it can '
          + 'say a window had no peak at all. Hours: the fit costs about '
          + 'forty-five times what reading does.',
    }));

    box.appendChild(BARRY.ui.field({
      label: 'Keep one column in',
      inline: true,
      control: num(q.every, (v) => { q.every = Math.max(1, Math.round(v)); },
                   { min: 1, max: 60, step: 1 }),
      hint: 'The cost lever, and a display argument: more columns than the '
          + 'map has pixels is not more information. The columns kept are '
          + 'exactly the ones Panorama would have computed at those times.',
    }));
    return box;
  }

  /* ---- cost, then the one thing this does ------------------------------- */

  function runCard() {
    const box = el('div', { class: 'card hz-run' });
    if (est && est.error) {
      box.appendChild(el('p', { class: 'hint bad', text: est.error }));
      return box;
    }
    if (!est) {
      box.appendChild(el('div', { class: 'tk-loading' }, [
        loader('Working out what it would cost')]));
      return box;
    }
    const p = est.plan || {};
    box.appendChild(BARRY.ui.chipRow([
      BARRY.ui.chip(p.n_channels + ' channels'),
      BARRY.ui.chip(p.n_windows + ' columns, one every ' + p.column_s + ' s'),
      BARRY.ui.chip(secs(est.seconds), { kind: est.seconds > 900 ? 'warn' : null,
                                         title: 'read ' + secs(est.read_s)
                                              + ', fit ' + secs(est.fit_s) }),
      est.cached ? BARRY.ui.chip('already run', { kind: 'ok' }) : null,
    ].filter(Boolean)));

    const notes = el('ul', { class: 'hint hz-notes' },
      (est.notes || []).map((n) => el('li', { text: n })));
    box.appendChild(notes);

    if (err) box.appendChild(el('p', { class: 'hint bad', text: err }));

    /* One primary, last, naming what it will do. */
    box.appendChild(BARRY.ui.actions([
      BARRY.ui.button({
        kind: 'primary',
        text: est.cached ? 'Show it again'
                         : 'Read ' + p.n_channels + ' channels',
        disabled: busy ? true : null,
        onclick: run,
      }),
    ]));
    return box;
  }

  function secs(v) {
    if (v === null || v === undefined) return '—';
    if (v < 90) return Math.round(v) + ' s';
    if (v < 5400) return (v / 60).toFixed(v < 600 ? 1 : 0) + ' min';
    return (v / 3600).toFixed(1) + ' h';
  }

  async function run() {
    if (busy) return;
    busy = true; err = null; out = null; preview = null;
    paint();
    let got;
    try { got = await apiPost('/api/horizon/run', body()); }
    catch (e) { busy = false; err = e.message; paint(); return; }
    if (got.cached && got.result) {
      busy = false; out = got.result; job = null; paint(); return;
    }
    job = got.job || null;
    paint();
    watch();
  }

  async function watch() {
    if (!job || watching) return;
    watching = true;
    const id = job.id;
    let rev = -1;
    try {
    for (;;) {
      await new Promise((r) => setTimeout(r, 400));
      if (!job || job.id !== id) return;         // superseded or cancelled
      /* Stop when this is not the tool on screen.
         ToolKit's own onHide stops what ToolKit started, and core only
         calls onHide on the VIEW -- a tool's is never reached -- so a poll
         started here and not stopped here runs for the rest of the
         session, fetching every 400 ms into a panel nobody is looking at.
         The job itself carries on server-side; `paint` picks the watch back
         up if somebody returns while it is still going. */
      if (!BARRY.views.toolkit || BARRY.views.toolkit.tool() !== 'horizon') {
        return;
      }
      let snap;
      try { snap = await api('/api/cfc/job/' + id); }
      catch (e) { busy = false; err = e.message; job = null; paint(); return; }
      const j = snap.job || snap;
      job = j;
      /* The picture rides its own route: the poll carries an integer, and
         the image is fetched only when that integer changes. */
      if (j.preview_rev !== undefined && j.preview_rev !== rev) {
        rev = j.preview_rev;
        try {
          const pv = await api('/api/cfc/job/' + id + '/preview');
          if (pv && pv.preview) { preview = pv.preview; paint(); }
        } catch (e) { /* the picture is optional */ }
      } else {
        paint();
      }
      if (j.status === 'done') {
        try {
          const res = await api('/api/cfc/result/' + id);
          out = res.result || res;
        } catch (e) { err = e.message; }
        busy = false; job = null; preview = null; paint(); return;
      }
      if (j.status === 'error' || j.status === 'cancelled') {
        busy = false; err = j.error || 'It stopped.'; job = null; paint();
        return;
      }
    }
    } finally { watching = false; }
  }

  function waitCard() {
    const box = el('div', { class: 'card hz-wait' });
    const j = job || {};
    const done = (j.steps || []).find((s) => s.id === 'horizon rows');
    box.appendChild(stepLoader('Horizon', (j.steps || []).map(
      (s) => s.label || s.id)));
    if (done && done.total) {
      box.appendChild(el('p', { class: 'hint', text:
        done.done + ' of ' + done.total + ' channels' }));
    }
    if (preview) {
      /* The map as it arrives, in interlaced order: every eighth row, then
         every fourth, then the rest. So the whole depth extent is on screen
         coarsely after an eighth of the work, and a run that is obviously
         wrong can be stopped then rather than at the end. */
      box.appendChild(el('p', { class: 'hint', text:
        'Every eighth channel first, then every fourth — so the shape '
        + 'of the map is readable long before it is finished.' }));
      box.appendChild(el('img', { class: 'hz-preview', src: preview,
                                  alt: 'the map, filling in' }));
    }
    box.appendChild(BARRY.ui.actions([
      BARRY.ui.button({
        kind: 'ghost', text: 'Stop',
        onclick: async () => {
          if (!job) return;
          try { await apiPost('/api/cfc/job/' + job.id + '/cancel', {}); }
          catch (e) { /* it is stopping either way */ }
        },
      }),
    ]));
    return box;
  }

  /* ---- the map ---------------------------------------------------------- */

  async function recolour() {
    if (!out) { paint(); return; }
    try {
      const got = await apiPost('/api/horizon/recolor', body());
      if (got && got.map) { out.map = got.map; out.plan = got.plan || out.plan; }
    } catch (e) {
      /* The arrays behind it are held in the server's process, so this can
         legitimately fail after a restart. Say so rather than silently
         leaving the old colours on a control that has moved. */
      err = e.message;
    }
    paint();
  }

  function mapCard() {
    const box = el('div', { class: 'card hz-map' });
    const m = out.map || {};
    const p = out.plan || {};

    box.appendChild(BARRY.ui.chipRow([
      BARRY.ui.chip(out.fidelity === 'full' ? 'full fit' : 'survey',
                    { kind: out.fidelity === 'full' ? 'ok' : null,
                      title: (out.engine || {}).note
                           || 'Per-window fits, the same fitter Panorama '
                            + 'uses.' }),
      BARRY.ui.chip('column agreement '
                    + pct(out.column_agreement),
                    { kind: agreeKind(out.column_agreement),
                      title: 'How often the channels named the same '
                           + 'frequency. High means one rhythm down the '
                           + 'whole column.' }),
      out.n_reused ? BARRY.ui.chip(out.n_reused + ' reused', { kind: 'ok' })
                   : null,
    ].filter(Boolean)));

    /* The picture, with its axes on a canvas over it rather than baked in. */
    const stack = el('div', { class: 'hz-stack' }, [
      el('img', { id: 'hzImg', class: 'hz-img', src: m.png,
                  alt: 'dominant frequency by depth and time' }),
      el('canvas', { id: 'hzAxes', class: 'hz-axes' }),
    ]);
    box.appendChild(el('div', { class: 'hz-with-bar' }, [
      stack,
      el('canvas', { id: 'hzBar', class: 'hz-bar' }),
    ]));

    box.appendChild(el('p', { class: 'hint', text:
      'Hue is which frequency won. Opacity is how clearly it won — a '
      + 'cell whose runner-up was nearly as tall fades out, so the layers '
      + 'actually carrying a rhythm are the ones that glow.' }));

    box.appendChild(el('div', { class: 'section-label',
                                text: 'How much the column agreed' }));
    box.appendChild(el('canvas', { id: 'hzAgree', class: 'hz-agree' }));
    box.appendChild(el('p', { class: 'hint', text:
      'Theta is globally coherent, so at any instant the column should '
      + 'agree. Where it does not, either the fits are bad or the channels '
      + 'are not all in one structure.' }));
    return box;
  }

  function pct(v) {
    return (v === null || v === undefined) ? '—'
      : Math.round(v * 100) + '%';
  }
  function agreeKind(v) {
    if (v === null || v === undefined) return null;
    return v >= 0.8 ? 'ok' : (v >= 0.5 ? 'warn' : 'err');
  }

  /* ---- drawing ---------------------------------------------------------- */

  function ink() {
    return {
      text: BARRY.token('--text', '#222'),
      dim: BARRY.token('--text-3', '#888'),
      faint: BARRY.token('--border', '#ddd'),
      accent: BARRY.token('--accent', '#FFB81C'),
    };
  }

  function sizeCanvas(id, h) {
    const cv = document.getElementById(id);
    if (!cv || !cv.parentNode) return null;
    const w = Math.max(120, Math.round(
      cv.clientWidth || cv.getBoundingClientRect().width
      || cv.parentNode.clientWidth));
    const dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    cv.style.height = h + 'px';
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    return { g, W: w, H: h };
  }

  function drawAll() {
    if (!out) return;
    drawAxes();
    drawBar();
    drawAgree();
  }

  function drawAxes() {
    const img = document.getElementById('hzImg');
    if (!img) return;
    const h = Math.max(120, img.clientHeight || 260);
    const c = sizeCanvas('hzAxes', h);
    if (!c) return;
    const { g, W, H } = c;
    const k = ink();
    const p = out.plan || {};
    const t0 = p.t0 || 0, t1 = p.t1 || 1;

    g.font = '10px system-ui, sans-serif';
    g.textBaseline = 'top';
    g.strokeStyle = k.faint;
    g.fillStyle = k.dim;
    g.lineWidth = 1;

    /* Time, along the bottom. Round numbers of minutes where the recording
       is long enough for that to be the unit somebody thinks in. */
    const span = Math.max(1e-6, t1 - t0);
    const stepS = niceStep(span / 6);
    for (let t = Math.ceil(t0 / stepS) * stepS; t <= t1; t += stepS) {
      const x = Math.round(((t - t0) / span) * W) + 0.5;
      g.beginPath(); g.moveTo(x, H - 6); g.lineTo(x, H); g.stroke();
      g.textAlign = 'center';
      g.fillText(span > 600 ? (t / 60).toFixed(0) + 'm' : t.toFixed(0) + 's',
                 x, H - 18);
    }

    /* Where one pane ends and the next begins. A continuous picture across
       a break would invite exactly the depth reading the split prevents. */
    const rows = (out.rows || []).length || 1;
    g.strokeStyle = k.text;
    g.lineWidth = 1.5;
    for (const pane of (out.panes || []).slice(1)) {
      const y = Math.round((pane.row0 / rows) * H) + 0.5;
      g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke();
      g.fillStyle = k.text;
      g.textAlign = 'left';
      g.fillText(pane.label || '', 4, y + 3);
    }
  }

  function niceStep(raw) {
    const pow = Math.pow(10, Math.floor(Math.log10(Math.max(raw, 1e-9))));
    const n = raw / pow;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * pow;
  }

  /* The colour bar, stepped exactly the way the map is, with theta
     bracketed on it rather than being the whole of it.

     The swatches come from the server, computed from the colormap and the
     colour limits the picture was actually drawn with. Rebuilding the ramp
     here would be a second place that knows what 8 Hz looks like, and the
     two would drift the first time either changed -- §6c. */
  function drawBar() {
    const img = document.getElementById('hzImg');
    const h = Math.max(120, (img && img.clientHeight) || 260);
    const c = sizeCanvas('hzBar', h);
    if (!c) return;
    const { g, W, H } = c;
    const k = ink();
    const m = out.map || {};
    const lo = m.f_lo || 2, hi = m.f_hi || 14;
    const sw = m.swatches || [];
    if (!sw.length) return;
    const step = m.bin_hz || 1;
    const bw = Math.min(18, W * 0.45);
    const Y = (f) => H - ((f - lo) / (hi - lo)) * H;

    for (const s of sw) {
      const y0 = Y(s.hz - step / 2), y1 = Y(s.hz + step / 2);
      g.fillStyle = s.css;
      g.fillRect(0, y1, bw, y0 - y1);
    }
    g.strokeStyle = k.faint;
    g.lineWidth = 1;
    g.strokeRect(0.5, 0.5, bw, H - 1);

    g.font = '10px system-ui, sans-serif';
    g.fillStyle = k.dim;
    g.textAlign = 'left';
    g.textBaseline = 'middle';
    const tick = Math.max(2, Math.round(2 / step) * step);
    for (let f = lo; f <= hi + 1e-9; f += tick) {
      g.fillText(String(Math.round(f)), bw + 4, Y(f));
    }

    /* Theta, bracketed -- the band of interest inside a wider range, rather
       than the range itself. */
    const th = (out.plan || {}).theta || [4, 12];
    const ty0 = Y(th[0]), ty1 = Y(th[1]);
    g.strokeStyle = k.text;
    g.lineWidth = 1.5;
    g.beginPath();
    g.moveTo(bw + 26, ty0); g.lineTo(bw + 30, ty0);
    g.lineTo(bw + 30, ty1); g.lineTo(bw + 26, ty1);
    g.stroke();
    g.save();
    g.translate(bw + 42, (ty0 + ty1) / 2);
    g.rotate(-Math.PI / 2);
    g.fillStyle = k.text;
    g.textAlign = 'center';
    g.fillText('theta', 0, 0);
    g.restore();
  }

  function drawAgree() {
    const c = sizeCanvas('hzAgree', 74);
    if (!c) return;
    const { g, W, H } = c;
    const k = ink();
    const t = out.times || [];
    const a = out.agreement || [];
    const n = Math.min(t.length, a.length);
    if (!n) return;
    const p = out.plan || {};
    const t0 = p.t0 || 0, t1 = p.t1 || 1;
    const span = Math.max(1e-6, t1 - t0);
    const X = (v) => ((v - t0) / span) * W;
    const Y = (v) => H - 6 - v * (H - 14);

    g.strokeStyle = k.faint;
    g.lineWidth = 1;
    for (const lv of [0.5, 1]) {
      const y = Math.round(Y(lv)) + 0.5;
      g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke();
    }

    g.beginPath();
    let open = false;
    for (let i = 0; i < n; i++) {
      if (a[i] === null || a[i] === undefined) { open = false; continue; }
      const x = X(t[i]), y = Y(a[i]);
      if (!open) { g.moveTo(x, y); open = true; } else { g.lineTo(x, y); }
    }
    g.strokeStyle = k.text;
    g.lineWidth = 1.4;
    g.stroke();

    g.font = '10px system-ui, sans-serif';
    g.fillStyle = k.dim;
    g.textAlign = 'left';
    g.textBaseline = 'top';
    g.fillText('all agree', 2, Y(1) - 11);
    g.fillText('half', 2, Y(0.5) - 11);
  }

  /* ---- keeping it ------------------------------------------------------- */

  function saveCard() {
    const box = el('div', { class: 'card hz-save' });
    box.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: 'Keep it' }));
    box.appendChild(el('p', { class: 'hint', text:
      'The figure, one row per channel, one row per window, and every '
      + 'setting that produced them — into Results/Horizon.' }));
    const msg = el('p', { class: 'hint' });
    box.appendChild(BARRY.ui.actions([
      BARRY.ui.button({
        kind: 'primary', text: 'Save into Results',
        onclick: async (e) => {
          const b = e.target;
          b.disabled = 'disabled';
          try {
            const got = await apiPost('/api/horizon/save', body());
            msg.textContent = 'Wrote ' + (got.files || []).length
                            + ' files into ' + got.folder + '.';
            if ((got.errors || []).length) {
              msg.textContent += ' ' + got.errors.join('; ');
            }
          } catch (x) {
            msg.textContent = x.message;
            msg.classList.add('bad');
          }
          b.disabled = null;
        },
      }),
    ]));
    box.appendChild(msg);
    return box;
  }

  /* ---- the module ------------------------------------------------------- */

  return {
    paint,
    /* A deep link lands on a recording rather than on an empty picker. */
    open(gid) {
      if (!gid || gid === q.gid) return;
      q.gid = gid;
      const rows = (BARRY.views.toolkit && BARRY.views.toolkit.registryRows)
        ? BARRY.views.toolkit.registryRows() : [];
      const r = rows.find((x) => x.gid === gid);
      if (r) {
        q.path = (r.here || [])[0] || null;
        q.label = r.label || r.key || null;
      }
      reset();
      loadInfo(gid);
      refreshEstimate();
    },
    /* Leaving stops the poll. Without this a run watched once keeps a
       400 ms fetch going for the rest of the session. */
    onHide() { job = null; busy = false; watching = false; },
    _state: () => JSON.parse(JSON.stringify(q)),
  };
})();
