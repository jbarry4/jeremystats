/* ==========================================================================
   strataaids.js -- StrataScope's aid window (web/strata-aids.html).

   A second window that follows the labelling window. With no step open it
   is the four live panes it always was -- CSD, theta CSD, voltage and a
   spectrogram stack, an XploreFinder instance in a frame -- because those
   are what a boundary is read off when labelling by hand. With a step open
   it swaps to that step's evidence:

     Step 1   ripple- and theta-trough-triggered LFP and CSD, the depth
              curves, the theta coherence matrix
     Step 2   the theta-trough CSD, the curves with multiunit and theta
              first, the coherence matrix
     Step 3   Method A drawn to scale, and Method B's components
     Step 4   the checks

   Every picture carries the sheet's boundaries (solid, in the layer's
   colour) and the step's proposed lines (dashed), from the same payload the
   labelling window publishes, so dragging a line there moves it here.

   Standalone on purpose: this page loads no Jarvis module, so nothing in it
   can start a sync loop, a presence beat or a second copy of the app's
   state. It reads /api/link and /api/strata/<gid>/*, and that is all.
   ========================================================================== */
'use strict';

(function () {
  const Q = new URLSearchParams(location.search);
  const GID = Q.get('gid');
  let path = Q.get('path');
  const CHANNEL = 'strata-steps:' + GID;

  try {
    const th = Q.get('theme') || localStorage.getItem('barry.theme');
    if (th) document.documentElement.dataset.theme = th;
  } catch (e) { /* private window */ }

  const $ = (s) => document.querySelector(s);
  const tok = (name, fb) => getComputedStyle(document.documentElement)
    .getPropertyValue(name).trim() || fb || '#888';

  function el(tag, attrs, kids) {
    const n = document.createElement(tag);
    for (const k in (attrs || {})) {
      const v = attrs[k];
      if (v == null || v === false) continue;
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const c of [].concat(kids || [])) {
      if (c == null || c === false) continue;
      n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    }
    return n;
  }

  async function post(url, body) {
    const r = await fetch(url, { method: 'POST',
                                 headers: { 'Content-Type': 'application/json' },
                                 body: JSON.stringify(body || {}) });
    const j = await r.json().catch(() => ({ ok: false, error: 'HTTP ' + r.status }));
    if (!j.ok) throw new Error(j.error || ('HTTP ' + r.status));
    return j;
  }

  /* ---------- the live panes, in a frame ---------- */
  const live = $('#saLive');
  const liveUrl = Q.get('live');
  if (liveUrl) live.src = liveUrl;
  function fitLive() {
    const h = $('#saHead').getBoundingClientRect().height;
    live.style.top = h + 'px';
    live.style.height = (window.innerHeight - h) + 'px';
  }
  window.addEventListener('resize', fitLive);
  fitLive();

  let forceLive = false;
  $('#saToggle').addEventListener('click', () => {
    forceLive = !forceLive;
    show();
  });

  /* ---------- following the labelling window ---------- */
  let state = null;          // the latest payload
  let data = null;           // the latest /suggest answer
  let ica = null;
  let fetchedFor = '';
  let since = 0;

  /* A held poll, as every linked window does. `?poll=short` asks without
     waiting, for a headless screenshot: a request held open stops a
     virtual clock, and the page never reaches its budget. */
  const SHORT_POLL = Q.get('poll') === 'short';

  async function listen() {
    for (;;) {
      try {
        if (SHORT_POLL) await new Promise((res) => setTimeout(res, 700));
        const r = await fetch('/api/link?' + (SHORT_POLL ? '' : 'wait=25&')
                              + 'since=' + since);
        const j = await r.json();
        if (j.reset) since = 0;
        since = Math.max(since, j.version || 0);
        const slot = (j.channels || {})[CHANNEL];
        if (slot && slot.value) adopt(slot.value);
      } catch (e) {
        await new Promise((res) => setTimeout(res, 2000));
      }
    }
  }

  function adopt(v) {
    if (v.off) {
      state = null;
      $('#saSub').textContent = 'StrataScope was closed in the labelling '
        + 'window.';
      show();
      return;
    }
    state = v;
    if (v.path) path = v.path;
    const key = JSON.stringify([v.step, v.overrides, v.states_n,
                                (v.channels || []).length,
                                Object.keys(v.labels || {}).length]);
    if (v.step && v.step !== '0' && key !== fetchedFor) {
      fetchedFor = key;
      load();
    }
    show();
  }

  async function load() {
    if (!state) return;
    $('#saSub').textContent = 'working…';
    try {
      data = await post('/api/strata/' + encodeURIComponent(GID) + '/suggest',
                        { path, channels: state.channels,
                          overrides: state.overrides || {} });
      if (state.step === '3') {
        const r = await post('/api/strata/' + encodeURIComponent(GID) + '/ica',
                             { path, channels: state.channels, peek: true,
                               overrides: state.overrides || {} });
        ica = r.ica;
      }
      if (state.step === '4') {
        data.checks = (await post('/api/strata/' + encodeURIComponent(GID)
                                  + '/checks', { path,
                                                 channels: state.channels })).checks;
      }
    } catch (e) {
      $('#saSub').textContent = 'Could not load the evidence.';
      const b = $('#saBody');
      b.innerHTML = '';
      b.appendChild(el('p', { class: 'sa-say', text: e.message }));
      data = null;
      return;
    }
    show();
  }

  const STEP_NAMES = { 0: 'Step 0 · Theta Walk', 1: 'Step 1 · '
    + 'Crystallize CA1', 2: 'Step 2 · Find the hilus', 3: 'Step 3 · '
    + 'GCL, IML, MML, OML', 4: 'Step 4 · Sign off' };

  function show() {
    const stepsMode = !!(state && state.step && state.step !== '0'
                         && !forceLive);
    document.body.classList.toggle('steps', stepsMode);
    $('#saToggle').textContent = stepsMode ? 'Live panes'
      : (state && state.step && state.step !== '0' ? 'Back to the evidence'
                                                   : 'Live panes');
    $('#saToggle').disabled = !(state && state.step && state.step !== '0');
    $('#saTitle').textContent = state && state.step
      ? STEP_NAMES[state.step] : 'StrataScope';
    if (state && (!state.step || state.step === '0')) {
      $('#saSub').textContent = 'Live panes. Open a step in the labelling '
        + 'window to see its evidence here.';
    } else if (data && state) {
      const m = data.masks || {};
      $('#saSub').textContent = (m.theta_all_time
        ? 'No Theta Walk painted: theta averages the whole recording'
        : Math.round(m.walk_s || 0) + ' s Theta Walk')
        + ' · ' + Math.round(m.still_s || 0) + ' s still · '
        + 'reference ch ' + data.ref_channel;
    }
    fitLive();
    if (stepsMode) render();
  }

  /* ---------- drawing ---------- */
  function jet(v) {
    // v in 0..1
    const r = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * v - 3)));
    const g = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * v - 2)));
    const b = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * v - 1)));
    return [r * 255, g * 255, b * 255];
  }

  function regionOf(ch) {
    const id = state && state.labels ? state.labels[String(ch)] : null;
    return id ? (state.regions || []).find((r) => r.id === id) || null : null;
  }

  /* The sheet's boundaries and the proposal's lines, over a panel whose
     rows are `chans` (channel numbers) laid from y0 with `lane` each. */
  function overlay(ctx, chans, x0, w, y0, lane, withNames) {
    const pos = new Map(chans.map((c, i) => [c, i]));
    for (let i = 1; i < chans.length; i++) {
      const a = regionOf(chans[i - 1]), b = regionOf(chans[i]);
      if ((a && a.id) === (b && b.id)) continue;
      const y = Math.round(y0 + i * lane) + 0.5;
      ctx.globalAlpha = 0.7; ctx.strokeStyle = '#000'; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + w, y); ctx.stroke();
      ctx.globalAlpha = 1; ctx.strokeStyle = (b || a).color; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + w, y); ctx.stroke();
    }
    if (withNames) {
      ctx.font = '10px system-ui, sans-serif';
      ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      let i = 0;
      while (i < chans.length) {
        const r = regionOf(chans[i]);
        let j = i + 1;
        while (j < chans.length && regionOf(chans[j]) === r) j++;
        if (r && (j - i) * lane >= 12) {
          const y = y0 + (i + j) / 2 * lane;
          const t = r.name;
          const tw = ctx.measureText(t).width;
          ctx.fillStyle = 'rgba(0,0,0,.65)';
          ctx.fillRect(x0 + w - tw - 8, y - 7, tw + 6, 14);
          ctx.fillStyle = r.color;
          ctx.fillText(t, x0 + w - 4, y);
        }
        i = j;
      }
    }
    const lines = (state && state.lines) || [];
    ctx.setLineDash([6, 4]);
    for (const ln of lines) {
      if (ln.at == null || !data) continue;
      const ch = data.channels[ln.at];
      let i = pos.get(ch);
      if (i == null) {
        if (ln.at >= data.channels.length) i = chans.length; else continue;
      }
      const y = Math.round(y0 + i * lane) + 0.5;
      ctx.globalAlpha = 0.85; ctx.strokeStyle = '#000'; ctx.lineWidth = 3.5;
      ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + w, y); ctx.stroke();
      ctx.globalAlpha = 1; ctx.strokeStyle = tok('--accent'); ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + w, y); ctx.stroke();
    }
    ctx.setLineDash([]);
  }

  function prep(canvas, h) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 320;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    canvas.style.height = h + 'px';
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, w, h };
  }

  function axisChannels(ctx, chans, y0, lane, x) {
    ctx.fillStyle = tok('--text-3');
    ctx.font = '9px system-ui, sans-serif';
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    const step = lane >= 10 ? 2 : lane >= 5 ? 4 : 8;
    chans.forEach((c, i) => {
      if (i % step) return;
      ctx.fillText(String(c), x, y0 + (i + 0.5) * lane);
    });
  }

  function heat(canvas, mat, tms, chans, opts) {
    const H = Math.max(260, Math.min(620, chans.length * 8));
    const { ctx, w } = prep(canvas, H + 22);
    const left = 26, right = 4, top = 4;
    const pw = w - left - right, lane = H / chans.length;
    const flat = [];
    mat.forEach((r) => r.forEach((v) => { if (v != null) flat.push(Math.abs(v)); }));
    flat.sort((a, b) => a - b);
    const lim = flat.length ? flat[Math.floor(flat.length * 0.99)] || 1 : 1;
    const img = ctx.createImageData(Math.max(1, Math.round(pw)), chans.length);
    const T = tms.length;
    for (let i = 0; i < chans.length; i++) {
      for (let x = 0; x < img.width; x++) {
        const v = mat[i][Math.min(T - 1, Math.floor(x / img.width * T))];
        const o = (i * img.width + x) * 4;
        if (v == null) { img.data[o + 3] = 0; continue; }
        const c = jet(Math.max(0, Math.min(1, 0.5 + 0.5 * v / lim)));
        img.data[o] = c[0]; img.data[o + 1] = c[1]; img.data[o + 2] = c[2];
        img.data[o + 3] = 255;
      }
    }
    const off = document.createElement('canvas');
    off.width = img.width; off.height = img.height;
    off.getContext('2d').putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, left, top, pw, H);
    // t = 0
    const x0 = left + pw * (0 - tms[0]) / (tms[T - 1] - tms[0]);
    ctx.strokeStyle = 'rgba(255,255,255,.6)'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x0, top); ctx.lineTo(x0, top + H); ctx.stroke();
    overlay(ctx, chans, left, pw, top, lane, true);
    axisChannels(ctx, chans, top, lane, left - 3);
    ctx.fillStyle = tok('--text-3');
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    ctx.font = '9.5px system-ui, sans-serif';
    for (const t of [tms[0], 0, tms[T - 1]]) {
      const x = left + pw * (t - tms[0]) / (tms[T - 1] - tms[0]);
      ctx.fillText(Math.round(t) + ' ms', x, top + H + 4);
    }
  }

  const CURVES = [
    ['mua', 'MUA', '--c1'], ['ripple', 'Ripple', '--event'],
    ['theta', 'Theta', '--c3'], ['theta_phase', 'Phase', '--c4'],
    ['theta_coherence', 'Coherence', '--c5'],
    ['slow_gamma', 'Slow γ', '--c2'], ['mid_gamma', 'Mid γ', '--warn'],
  ];

  function curvesPanel(canvas, prof, which) {
    const chans = prof.channels;
    const H = Math.max(260, Math.min(620, chans.length * 8));
    const { ctx, w } = prep(canvas, H + 8);
    const left = 26, top = 4, pw = w - left - 6, lane = H / chans.length;
    ctx.fillStyle = tok('--line-soft');
    for (let i = 0; i < chans.length; i += 4) ctx.fillRect(left, top + i * lane, pw, 1);
    for (const [id, , t] of CURVES) {
      if (which && !which.includes(id)) continue;
      const v = prof.curves[id] || [];
      const fin = v.filter((x) => x != null);
      if (!fin.length) continue;
      let lo = Math.min(...fin), hi = Math.max(...fin);
      if (hi <= lo) hi = lo + 1;
      ctx.strokeStyle = tok(t); ctx.lineWidth = 1.5;
      ctx.beginPath();
      let pen = false;
      v.forEach((x, i) => {
        if (x == null) { pen = false; return; }
        const px = left + 4 + (x - lo) / (hi - lo) * (pw - 8);
        const py = top + (i + 0.5) * lane;
        if (pen) ctx.lineTo(px, py); else { ctx.moveTo(px, py); pen = true; }
      });
      ctx.stroke();
    }
    overlay(ctx, chans, left, pw, top, lane, true);
    axisChannels(ctx, chans, top, lane, left - 3);
  }

  function legend(which) {
    return el('div', { class: 'sa-legend' }, CURVES.filter(
      ([id]) => !which || which.includes(id)).map(([, name, t]) =>
      el('span', {}, [el('i', { style: 'background:var(' + t + ')' }), name])));
  }

  function matrixPanel(canvas, prof) {
    const chans = prof.channels;
    const n = chans.length;
    const size = Math.max(260, Math.min(560, n * 7));
    const { ctx, w } = prep(canvas, size + 8);
    const left = 26, top = 4, side = Math.min(size, w - left - 6);
    const cell = side / n;
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        const v = (prof.coherence[i] || [])[j];
        if (v == null) continue;
        const c = jet(Math.max(0, Math.min(1, v)));
        ctx.fillStyle = 'rgb(' + c.map(Math.round).join(',') + ')';
        ctx.fillRect(left + j * cell, top + i * cell, Math.ceil(cell), Math.ceil(cell));
      }
    }
    overlay(ctx, chans, left, side, top, cell, false);
    axisChannels(ctx, chans, top, cell, left - 3);
  }

  function card(title, blurb, build, legendWhich) {
    const cv = el('canvas');
    const c = el('div', { class: 'sa-card' }, [
      el('h3', { text: title }), blurb ? el('p', { text: blurb }) : null, cv,
      legendWhich !== undefined ? legend(legendWhich) : null,
    ]);
    requestAnimationFrame(() => build(cv));
    return c;
  }

  function trigCards(tr, what) {
    if (!tr) {
      return [el('div', { class: 'sa-card' }, [el('h3', { text: what }),
        el('p', { text: 'Nothing to average yet.' })])];
    }
    const chans = tr.channels;
    const n = tr.n + (tr.n_total > tr.n ? ' of ' + tr.n_total : '');
    return [
      card(what + ' — LFP', 'Average of every channel around ' + n
           + ' events on ch ' + tr.channel + '.',
           (cv) => heat(cv, tr.lfp, tr.t_ms, chans)),
      card(what + ' — CSD', 'Sinks blue, sources red (the app’s '
           + 'CSD convention).', (cv) => heat(cv, tr.csd, tr.t_ms, chans)),
    ];
  }

  function render() {
    const body = $('#saBody');
    body.innerHTML = '';
    if (!data || !state) {
      body.appendChild(el('p', { class: 'sa-say', text: 'Working…' }));
      return;
    }
    const prof = data.profile;
    const grid = el('div', { class: 'sa-grid' });
    const step = state.step;
    if (step === '1') {
      trigCards(data.ripple_tr, 'Ripple-triggered').forEach((c) => grid.appendChild(c));
      trigCards(data.theta_tr, 'Theta-trough-triggered').forEach((c) => grid.appendChild(c));
      grid.appendChild(card('Depth curves', 'Each curve scaled to its own '
        + 'range. Phase and coherence are against the reference channel.',
        (cv) => curvesPanel(cv, prof), null));
      grid.appendChild(card('Theta coherence, channel by channel', 'Blocks '
        + 'are layers; their edges are boundaries.',
        (cv) => matrixPanel(cv, prof)));
    } else if (step === '2') {
      grid.appendChild(card('Multiunit, theta and slow gamma', 'The granule '
        + 'layers: multiunit peaks, and theta dips where it reverses.',
        (cv) => curvesPanel(cv, prof, ['mua', 'theta', 'slow_gamma']),
        ['mua', 'theta', 'slow_gamma']));
      trigCards(data.theta_tr, 'Theta-trough-triggered').slice(1)
        .forEach((c) => grid.appendChild(c));
      grid.appendChild(card('Theta coherence, channel by channel', null,
        (cv) => matrixPanel(cv, prof)));
      grid.appendChild(card('Every depth curve', null,
        (cv) => curvesPanel(cv, prof), null));
    } else if (step === '3') {
      grid.appendChild(methodA());
      grid.appendChild(methodB());
    } else if (step === '4') {
      const ul = el('ul', { class: 'sa-checks' });
      for (const c of data.checks || []) {
        ul.appendChild(el('li', { class: c.ok ? 'ok' : 'warn',
                                  text: (c.ok ? '✓ ' : '! ') + c.text }));
      }
      grid.appendChild(el('div', { class: 'sa-card' }, [
        el('h3', { text: 'Checks' }), ul]));
      grid.appendChild(card('The sheet, with every curve', null,
        (cv) => curvesPanel(cv, prof), null));
    }
    body.appendChild(grid);
  }

  function methodA() {
    const s3 = (data.steps || {})['3'] || {};
    const c = el('div', { class: 'sa-card' }, [
      el('h3', { text: 'Method A — the molecular layer in thirds' }),
      el('p', { text: s3.upper_ml_um
        ? 'Upper molecular layer ' + s3.upper_ml_um + ' µm, so each '
          + 'third is ' + s3.third_um + ' µm. GCL half-thickness '
          + s3.gcl_half_um + ' µm; the lower blade is assumed '
          + s3.lower_ml_scale + '× as thick.'
        : (s3.notes || ['Needs Steps 1 and 2.']).join(' ') }),
    ]);
    const cv = el('canvas');
    c.appendChild(cv);
    c.appendChild(legend(['mua', 'theta']));
    requestAnimationFrame(() => curvesPanel(cv, data.profile, ['mua', 'theta']));
    return c;
  }

  function methodB() {
    const c = el('div', { class: 'sa-card', style: 'grid-column: 1 / -1' }, [
      el('h3', { text: 'Method B — pathway-specific gamma (ICA)' }),
    ]);
    if (!ica) {
      c.appendChild(el('p', { text: 'Not run on these Theta Walk seconds '
        + 'yet. Run it from Step 3 in the labelling window.' }));
      return c;
    }
    c.appendChild(el('p', { text: ica.walk_s + ' s of '
      + (ica.theta_all_time ? 'recording (no Theta Walk painted)'
                            : 'Theta Walk') + ', 25-200 Hz. Each card: '
      + 'the loading (grey) and its CSD (colour, sink = leftmost), peak '
      + 'frequency, share of variance, and whether it came back in both '
      + 'halves of the walking.' }));
    const grid = el('div', { class: 'sa-ica' });
    for (const cm of (ica.components || []).slice(0, 10)) {
      const cv = el('canvas');
      grid.appendChild(el('div', { class: 'sa-comp ' + (cm.kind || '') }, [
        el('div', {}, [el('b', { text: (cm.kind === 'slow' ? 'slow γ'
          : cm.kind === 'fast' ? 'fast γ' : '?') + ' · '
          + cm.peak_hz + ' Hz' })]),
        el('div', { text: 'var ' + (100 * cm.variance).toFixed(1) + '% · '
          + 'stable ' + (cm.stability == null ? '?' : cm.stability) }),
        el('div', { text: 'sink ch ' + cm.sink_channel
          + (cm.theta_phase_deg == null ? ''
            : ' · theta ' + Math.round(cm.theta_phase_deg) + '°') }),
        cv,
      ]));
      requestAnimationFrame(() => compPanel(cv, cm, ica.channels));
    }
    c.appendChild(grid);
    return c;
  }

  function compPanel(cv, cm, chans) {
    const H = 220;
    const { ctx, w } = prep(cv, H);
    const lane = H / chans.length;
    const draw = (vals, color, width) => {
      const fin = vals.filter((x) => x != null);
      if (!fin.length) return;
      const lim = Math.max(...fin.map(Math.abs)) || 1;
      ctx.strokeStyle = color; ctx.lineWidth = width;
      ctx.beginPath();
      let pen = false;
      vals.forEach((x, i) => {
        if (x == null) { pen = false; return; }
        const px = w / 2 + (x / lim) * (w / 2 - 4), py = (i + 0.5) * lane;
        if (pen) ctx.lineTo(px, py); else { ctx.moveTo(px, py); pen = true; }
      });
      ctx.stroke();
    };
    ctx.strokeStyle = tok('--line'); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(w / 2, 0); ctx.lineTo(w / 2, H); ctx.stroke();
    draw(cm.loading, tok('--text-3'), 1);
    draw(cm.csd, cm.kind === 'slow' ? tok('--c2') : tok('--warn'), 1.6);
    overlay(ctx, chans, 0, w, 0, lane, false);
  }

  window.addEventListener('resize', () => { if (document.body.classList.contains('steps')) render(); });
  /* `?step=1` (with gid and path) opens a step on its own, without a
     labelling window to follow: a pose for a screenshot, or a second look
     at a sheet. It reads the sheet once and does not listen. */
  async function pose(step) {
    try {
      const r = await fetch('/api/layers/' + encodeURIComponent(GID));
      const j = await r.json();
      const sh = (j && j.sheet) || {};
      adopt({ gid: GID, path, step, channels: sh.channels || null,
              labels: sh.labels || {}, regions: sh.regions || [],
              lines: [], overrides: {}, states_n: 0 });
    } catch (e) {
      $('#saSub').textContent = 'Could not read the sheet: ' + e.message;
    }
  }

  if (Q.get('step')) pose(Q.get('step'));
  else listen();
  show();
})();
