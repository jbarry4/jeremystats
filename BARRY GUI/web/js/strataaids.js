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
    const key = JSON.stringify([v.step, v.overrides, v.states_n, v.ica_ready,
                                (v.channels || []).length,
                                Object.keys(v.labels || {}).length]);
    if (v.step && v.step !== '0' && key !== fetchedFor) {
      fetchedFor = key;
      load();
      return;
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
      if (state.step === '3' || state.step === '4') {
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

  /* What the open step is about, from the labelling window's payload: the
     channels Accept would write (`affected`), the layers it writes
     (`focus`), and what it would write there (`proposed`). Everything else
     is drawn grey or veiled (2026-10-12). */
  const inStep = (ch) => !state || !state.affected
    || state.affected.indexOf(ch) >= 0;
  const inFocus = (id) => !state || !state.focus || state.focus.indexOf(id) >= 0;
  const DASH = { sure: [], likely: [7, 4], guess: [2, 4] };

  const hatchTiles = new Map();
  function hatch(ctx, color) {
    let tile = hatchTiles.get(color);
    if (!tile) {
      tile = document.createElement('canvas');
      tile.width = tile.height = 10;
      const g = tile.getContext('2d');
      g.strokeStyle = color; g.lineWidth = 2;
      g.beginPath();
      g.moveTo(-2, 12); g.lineTo(12, -2);
      g.moveTo(-2, 2); g.lineTo(2, -2);
      g.moveTo(8, 12); g.lineTo(12, 8);
      g.stroke();
      hatchTiles.set(color, tile);
    }
    return ctx.createPattern(tile, 'repeat');
  }

  /* The sheet's boundaries, the proposal (hatched) and its lines, over a
     panel whose rows are `chans` (channel numbers) laid from y0 with `lane`
     each. Outside the open step everything is veiled and grey. */
  function overlay(ctx, chans, x0, w, y0, lane, withNames) {
    const pos = new Map(chans.map((c, i) => [c, i]));
    const prop = (state && state.proposed) || null;
    if (prop) {
      for (let i = 0; i < chans.length; i++) {
        const id = prop[String(chans[i])];
        const r = id && (state.regions || []).find((x) => x.id === id);
        if (!r) continue;
        ctx.globalAlpha = 0.6;
        ctx.fillStyle = hatch(ctx, r.color);
        ctx.fillRect(x0, y0 + i * lane, w, Math.ceil(lane));
      }
      ctx.globalAlpha = 1;
    }
    if (state && state.affected) {
      ctx.globalAlpha = 0.55;
      ctx.fillStyle = tok('--bg');
      for (let i = 0; i < chans.length; i++) {
        if (!inStep(chans[i])) ctx.fillRect(x0, y0 + i * lane, w, Math.ceil(lane));
      }
      ctx.globalAlpha = 1;
    }
    for (let i = 1; i < chans.length; i++) {
      const a = regionOf(chans[i - 1]), b = regionOf(chans[i]);
      if ((a && a.id) === (b && b.id)) continue;
      const y = Math.round(y0 + i * lane) + 0.5;
      const on = (inStep(chans[i]) || inStep(chans[i - 1]))
        && (inFocus(a && a.id) || inFocus(b && b.id));
      if (!on) {
        ctx.globalAlpha = 0.45; ctx.strokeStyle = tok('--text-3'); ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + w, y); ctx.stroke();
        ctx.globalAlpha = 1;
        continue;
      }
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
        if (r && (j - i) * lane >= 12 && inStep(chans[i]) && inFocus(r.id)) {
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
    for (const ln of lines) {
      if (ln.at == null || !data) continue;
      // The first drawn row at or after the line's channel.
      let i = null;
      for (let r = ln.at; r < data.channels.length && i == null; r++) {
        if (pos.has(data.channels[r])) i = pos.get(data.channels[r]);
      }
      if (i == null) i = chans.length;
      const y = Math.round(y0 + i * lane) + 0.5;
      ctx.setLineDash(DASH[ln.confidence] || DASH.likely);
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
    ['slow_gamma', 'Slow \u03b3', '--c2'], ['mid_gamma', 'Mid \u03b3', '--warn'],
  ];
  /* The curves each step is decided from: the lead full, the votes faint.
     Same as the labelling window's strip (stratasteps.js FOCUS). */
  const FOCUS = {
    1: { lead: ['ripple', 'theta'], votes: ['mua', 'theta_phase'] },
    2: { lead: ['mua'], votes: ['theta'] },
    3: { lead: ['mua', 'theta'], votes: [] },
    // Sign off: everything.
    4: { lead: ['mua', 'ripple', 'theta', 'theta_phase', 'theta_coherence',
                'slow_gamma', 'mid_gamma'], votes: [] },
  };

  /* A curve through points, some missing: solid where neighbours are both
     there, a faint dotted bridge across a missing (bad) channel. */
  function curve(ctx, pts) {
    let run = [];
    let lastEnd = null;
    const flush = () => {
      if (run.length) {
        if (lastEnd) {
          ctx.save();
          ctx.setLineDash([2, 3]);
          ctx.globalAlpha *= 0.6;
          ctx.beginPath();
          ctx.moveTo(lastEnd[0], lastEnd[1]);
          ctx.lineTo(run[0][0], run[0][1]);
          ctx.stroke();
          ctx.restore();
        }
        ctx.beginPath();
        ctx.moveTo(run[0][0], run[0][1]);
        for (let k = 1; k < run.length; k++) ctx.lineTo(run[k][0], run[k][1]);
        ctx.stroke();
        lastEnd = run[run.length - 1];
      }
      run = [];
    };
    for (const p of pts) {
      if (p) run.push(p); else flush();
    }
    flush();
  }
  const stepCurves = () => {
    const f = FOCUS[(state && state.step) || 4] || FOCUS[4];
    return f.lead.concat(f.votes);
  };

  function curvesPanel(canvas, prof, which) {
    const chans = prof.channels;
    const H = Math.max(260, Math.min(620, chans.length * 8));
    const { ctx, w } = prep(canvas, H + 8);
    const left = 26, top = 4, pw = w - left - 6, lane = H / chans.length;
    const f = FOCUS[(state && state.step) || 4] || FOCUS[4];
    which = which || stepCurves();
    ctx.fillStyle = tok('--line-soft');
    for (let i = 0; i < chans.length; i += 4) ctx.fillRect(left, top + i * lane, pw, 1);
    for (const [id, , t] of CURVES) {
      if (!which.includes(id)) continue;
      const v = prof.curves[id] || [];
      const fin = v.filter((x) => x != null);
      if (!fin.length) continue;
      let lo = Math.min(...fin), hi = Math.max(...fin);
      if (hi <= lo) hi = lo + 1;
      const strong = f.lead.includes(id);
      ctx.globalAlpha = strong ? 1 : 0.45;
      ctx.strokeStyle = tok(t); ctx.lineWidth = strong ? 1.8 : 1;
      curve(ctx, v.map((x, i) => (x == null ? null
        : [left + 4 + (x - lo) / (hi - lo) * (pw - 8), top + (i + 0.5) * lane])));
    }
    ctx.globalAlpha = 1;
    overlay(ctx, chans, left, pw, top, lane, true);
    axisChannels(ctx, chans, top, lane, left - 3);
  }

  function legend(which) {
    which = which || stepCurves();
    return el('div', { class: 'sa-legend' }, CURVES.filter(
      ([id]) => which.includes(id)).map(([, name, t]) =>
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

  /* `legendWhich`: undefined for the step's own curves, null for none. */
  function card(title, blurb, build, legendWhich) {
    const cv = el('canvas');
    const c = el('div', { class: 'sa-card' }, [
      el('h3', { text: title }), blurb ? el('p', { text: blurb }) : null, cv,
      legendWhich === null ? null : legend(legendWhich),
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
           (cv) => heat(cv, tr.lfp, tr.t_ms, chans), null),
      card(what + ' — CSD', 'Sinks blue, sources red (the app’s '
           + 'CSD convention).', (cv) => heat(cv, tr.csd, tr.t_ms, chans), null),
    ];
  }

  /* Each step shows the few pictures its lines are read off; the rest are
     behind "More evidence", closed by default (2026-10-12: "only relevant
     information"). */
  let moreOpen = false;

  function render() {
    const body = $('#saBody');
    body.innerHTML = '';
    if (!data || !state) {
      body.appendChild(el('p', { class: 'sa-say', text: 'Working\u2026' }));
      return;
    }
    const prof = data.profile;
    const grid = el('div', { class: 'sa-grid' });
    const extra = [];
    const step = state.step;
    if (step === '1') {
      // sp: the sharp wave reverses there; sr: its sink; the fissure: the
      // theta-trough CSD changes sharply across it.
      trigCards(data.ripple_tr, 'Ripple-triggered').forEach((c) => grid.appendChild(c));
      trigCards(data.theta_tr, 'Theta-trough-triggered').slice(1)
        .forEach((c) => grid.appendChild(c));
      grid.appendChild(card('What Step 1 is placed by', 'Ripple and theta '
        + 'full; multiunit and phase faint. Hatched: what Accept would '
        + 'write.', (cv) => curvesPanel(cv, prof), undefined));
      extra.push(...trigCards(data.theta_tr, 'Theta-trough-triggered').slice(0, 1));
      extra.push(card('Theta coherence, channel by channel', 'Blocks are '
        + 'layers; their edges are boundaries.', (cv) => matrixPanel(cv, prof), null));
    } else if (step === '2') {
      grid.appendChild(card('What Step 2 is placed by', 'Multiunit full: it '
        + 'peaks in the granule layers. Theta faint: it dips where it '
        + 'reverses across them.', (cv) => curvesPanel(cv, prof), undefined));
      trigCards(data.theta_tr, 'Theta-trough-triggered').slice(1)
        .forEach((c) => grid.appendChild(c));
      extra.push(card('Theta coherence, channel by channel', null,
        (cv) => matrixPanel(cv, prof), null));
    } else if (step === '3') {
      grid.appendChild(methodA());
      grid.appendChild(thetaSink());
      grid.appendChild(methodB());
    } else if (step === '4') {
      // Sign off: everything, so the whole sheet can be read at once.
      const ul = el('ul', { class: 'sa-checks' });
      for (const c of data.checks || []) {
        ul.appendChild(el('li', { class: c.ok ? 'ok' : 'warn',
                                  text: (c.ok ? '\u2713 ' : '! ') + c.text }));
      }
      grid.appendChild(el('div', { class: 'sa-card' }, [
        el('h3', { text: 'Checks' }), ul]));
      grid.appendChild(card('The sheet, with every curve', null,
        (cv) => curvesPanel(cv, prof), undefined));
      trigCards(data.ripple_tr, 'Ripple-triggered').forEach((c) => grid.appendChild(c));
      trigCards(data.theta_tr, 'Theta-trough-triggered').forEach((c) => grid.appendChild(c));
      grid.appendChild(card('Theta coherence, channel by channel', null,
        (cv) => matrixPanel(cv, prof), null));
      if (ica) grid.appendChild(methodB());
    }
    body.appendChild(grid);
    if (extra.length) {
      body.appendChild(el('button', {
        class: 'mini', style: 'margin:12px 0 8px',
        text: (moreOpen ? '\u25be' : '\u25b8') + ' More evidence',
        onclick: () => { moreOpen = !moreOpen; render(); },
      }));
      if (moreOpen) {
        const g2 = el('div', { class: 'sa-grid' });
        extra.forEach((c) => g2.appendChild(c));
        body.appendChild(g2);
      }
    }
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
    const pr = proportion();
    if (pr) c.appendChild(pr);
    const cv = el('canvas');
    c.appendChild(cv);
    c.appendChild(legend(['mua', 'theta']));
    requestAnimationFrame(() => curvesPanel(cv, data.profile));
    return c;
  }

  /* Rows of a region on the sheet, else in a step's proposal. */
  function rowsOf(id, stepId) {
    const out = [];
    data.channels.forEach((ch, i) => {
      const r = regionOf(ch);
      if (r && r.id === id) out.push(i);
    });
    if (out.length) return out;
    const lines = (((data.steps || {})[stepId] || {}).lines) || [];
    const top = lines.find((l) => l.below === id);
    const bot = lines.find((l) => l.above === id);
    if (!top || top.at == null) return [];
    const end = bot && bot.at != null ? bot.at : top.at + 1;
    for (let i = top.at; i < end; i++) out.push(i);
    return out;
  }
  const mid = (rows) => (rows.length ? (rows[0] + rows[rows.length - 1]) / 2 : null);

  /* CA1 SP -> fissure : fissure -> granule layer. Paleologos et al. 2025
     (Front Behav Neurosci, mice, histology): about 2 : 1, from 1.5 at the
     lateral edge of the fissure to 2.8 at the medial border of the dorsal
     hippocampus. Independent of every curve here, so a check on the
     fissure, the line the thirds hang from. */
  function proportion() {
    const sp = mid(rowsOf('ca1_sp', '1'));
    const fis = (layerRows('dg_oml1') || [])[0];
    const g = layerRows('dg_gcl1');
    if (sp == null || fis == null || !g) return null;
    const gcl = (g[0] + g[1] - 1) / 2;
    const a = fis - 0.5 - sp, b = gcl - (fis - 0.5);
    if (a <= 0 || b <= 0) return null;
    const ratio = a / b;
    const ok = ratio >= 1.5 && ratio <= 2.8;
    // Where the fissure would sit for 2 : 1, between the same SP and GCL1.
    const at21 = Math.round(sp + (gcl - sp) * 2 / 3 + 0.5);
    const ch = data.channels[Math.max(0, Math.min(data.channels.length - 1, at21))];
    return el('div', { class: 'sa-verdict ' + (ok ? 'match' : 'off') }, [
      el('b', { text: ok ? '\u2713' : '\u2717' }),
      el('span', { text: 'CA1 SP to fissure : fissure to GCL1 is '
        + ratio.toFixed(1) + ' : 1. In mice it is about 2 : 1 (1.5-2.8; '
        + 'Paleologos et al. 2025). ' + (ok ? 'In range.'
          : 'Out of range: for 2 : 1 the fissure would sit above ch ' + ch
            + '.') }),
    ]);
  }

  /* Theta's sink in the dentate molecular layer. The perforant path drives
     theta there, so the theta-trough CSD has its strongest dentate sink in
     the molecular layer -- the medial path's, mid-molecular, is the
     largest (Paleologos et al. 2025: "the mid-molecular layer was
     identified by the strongest current sink below the LM layer"). A
     third look at the MML that uses neither the thirds nor gamma. */
  function thetaSink() {
    const tr = data.theta_tr;
    const c = el('div', { class: 'sa-card' }, [
      el('h3', { text: 'Theta\u2019s sink in the molecular layer' }),
    ]);
    const top = (layerRows('dg_oml1') || [])[0];
    const g = layerRows('dg_gcl1');
    if (!tr || !tr.csd || top == null || !g) {
      c.appendChild(el('p', { text: 'Needs the theta-trough average and '
        + 'Step 3\u2019s lines.' }));
      return c;
    }
    // tr rows are channels; find the deepest sink between fissure and GCL1.
    const rowOf = new Map(data.channels.map((ch, i) => [ch, i]));
    let best = null;
    tr.channels.forEach((ch, k) => {
      const r = rowOf.get(ch);
      if (r == null || r < top || r >= g[0]) return;
      const v = Math.min(...(tr.csd[k] || []).filter((x) => x != null));
      if (isFinite(v) && (!best || v < best.v)) best = { r, ch, v };
    });
    const mml = layerRows('dg_mml1');
    if (best && mml) {
      const ok = best.r >= mml[0] && best.r < mml[1];
      const off = best.r < mml[0] ? best.r - mml[0] : best.r - mml[1] + 1;
      c.appendChild(el('div', { class: 'sa-verdict ' + (ok ? 'match' : 'off') }, [
        el('b', { text: ok ? '\u2713' : '\u2717' }),
        el('span', { text: 'Strongest theta sink between the fissure and '
          + 'GCL1: ch ' + best.ch + ', ' + (ok ? 'in MML1, as expected.'
            : Math.abs(off) + ' ch ' + (off < 0 ? 'above' : 'below')
              + ' MML1 (' + layerAt(best.r) + ').') }),
      ]));
    }
    c.appendChild(el('p', { text: 'Theta-trough CSD, sinks blue. The '
      + 'perforant path drives dentate theta; its strongest sink is '
      + 'expected mid-molecular (MML). Uses neither the thirds nor gamma.' }));
    const cv = el('canvas');
    c.appendChild(cv);
    requestAnimationFrame(() => heat(cv, tr.csd, tr.t_ms, tr.channels));
    return c;
  }

  /* Method B, read as two questions, one per frequency (2026-10-12: "a
     lot of colours and lines... make it easier to spot what is relevant
     for each frequency, and say if it matches"):

       slow gamma -> does it sit in the OML?
       fast gamma -> does it sit in the MML?

     Each gets one card: a verdict per blade in words, and one picture --
     that frequency's component, its sink, and only the layer it should
     be in shaded. Every component is still there, folded, below. */
  let allComps = false;

  function methodB() {
    const c = el('div', { class: 'sa-card', style: 'grid-column: 1 / -1' }, [
      el('h3', { text: 'Method B \u2014 does the gamma sit where the layers say?' }),
    ]);
    if (!ica) {
      c.appendChild(el('p', { text: 'Not run on these Theta Walk seconds '
        + 'yet. Run it from Step 3 in the labelling window.' }));
      return c;
    }
    const s3 = ((data.steps || {})['3'] || {});
    const checks = s3.ica_checks || [];
    const pair = el('div', { class: 'sa-expect' });
    for (const kind of ['slow', 'mid', 'fast']) {
      pair.appendChild(expectCard(kind, checks.filter((x) => x.kind === kind),
                                  kind === 'mid' && s3.ml_scheme
                                    && s3.ml_scheme !== 'iml'));
    }
    c.appendChild(pair);
    c.appendChild(el('button', {
      class: 'mini', style: 'margin-top:8px',
      text: (allComps ? '\u25be' : '\u25b8') + ' Every component ('
        + (ica.components || []).length + ')',
      onclick: () => { allComps = !allComps; render(); },
    }));
    if (allComps) {
      c.appendChild(el('p', { text: ica.walk_s + ' s of '
        + (ica.theta_all_time ? 'recording' : 'Theta Walk') + ', 25-200 Hz. '
        + 'Each: its CSD (the dip is its sink), peak frequency, share of '
        + 'the gamma field, and how well it came back in both halves.' }));
      const grid = el('div', { class: 'sa-ica' });
      for (const cm of (ica.components || []).slice(0, 12)) {
        const cv = el('canvas');
        grid.appendChild(el('div', { class: 'sa-comp ' + (cm.kind || '')
            + (state && state.ica_pick === cm.index ? ' picked' : '')
            + ((cm.stability || 0) < TRUST ? ' weak' : '') }, [
          el('div', {}, [el('b', { text: ((KIND[cm.kind] || {}).short || '?')
            + ' \u00b7 ' + cm.peak_hz + ' Hz' })]),
          el('div', { text: pct(cm.variance) + ' \u00b7 '
            + ((cm.stability || 0) >= TRUST ? 'trusted' : 'not trusted')
            + ' \u00b7 sink ch ' + cm.sink_channel }),
          cv,
        ]));
        requestAnimationFrame(() => compPanel(cv, cm, ica.channels));
      }
      c.appendChild(grid);
    }
    return c;
  }

  const LAYER = { ca1_slm: 'CA1 SLM', dg_oml1: 'OML1', dg_mml1: 'MML1',
                  dg_iml1: 'IML1', dg_gcl1: 'GCL1', hil: 'HIL', dg_gcl2: 'GCL2',
                  dg_iml2: 'IML2', dg_mml2: 'MML2', dg_oml2: 'OML2',
                  thal: 'THAL' };
  const TRUST = 0.7;               // stability a source needs to count

  /* The dentate's three gamma inputs, each into its own third of the
     molecular layer (Fernandez-Ruiz et al. 2021, Science 372:eabf3119). A
     component is called by its peak: under 55 Hz slow, 55-90 mid, 90 and
     up fast (backend/stratasteps.py ICA_KINDS). */
  const KIND = {
    slow: { short: 'slow \u03b3', title: 'Slow gamma \u00b7 under 55 Hz',
            name: 'slow-gamma', want: 'OML', ids: ['dg_oml1', 'dg_oml2'],
            tok: '--c2',
            why: 'Lateral entorhinal input (30-50 Hz) ends in the outer '
              + 'third of the molecular layer, so it should sink in the OML.' },
    mid: { short: 'mid \u03b3', title: 'Mid gamma \u00b7 55-90 Hz',
           name: 'mid-gamma', want: 'IML', ids: ['dg_iml1', 'dg_iml2'],
           tok: '--warn',
           why: 'The commissural input from the other hippocampus (60-80 Hz) '
             + 'ends in the inner third, so it should sink in the IML.' },
    fast: { short: 'fast \u03b3', title: 'Fast gamma \u00b7 90 Hz and up',
            name: 'fast-gamma', want: 'MML', ids: ['dg_mml1', 'dg_mml2'],
            tok: '--c4',
            why: 'Medial entorhinal input (100-150 Hz) ends in the middle '
              + 'third, so it should sink in the MML.' },
  };

  function stepLines() {
    return (state && state.step === '3' && state.lines && state.lines.length)
      ? state.lines : ((((data.steps || {})['3']) || {}).lines || []);
  }

  /* Rows [from, to) the step's lines give a layer. */
  function layerRows(id) {
    const ls = stepLines();
    const top = ls.find((l) => l.below === id);
    const bot = ls.find((l) => l.above === id);
    if (!top || top.at == null) return null;
    return [top.at, bot && bot.at != null ? bot.at : data.channels.length];
  }

  /* The layer a row is in, as Step 3's lines draw it; outside them, the
     sheet's label. */
  function layerAt(row) {
    const ls = stepLines().filter((l) => l.at != null)
      .slice().sort((x, y) => x.at - y.at);
    let id = null;
    if (ls.length && row >= ls[0].at) {
      for (const l of ls) if (l.at <= row) id = l.below;
    }
    if (id) return LAYER[id] || id;
    const r = regionOf(data.channels[row]);
    if (r) return LAYER[r.id] || r.name;
    return ls.length && row < ls[0].at ? 'above the fissure'
                                       : 'below the lower blade';
  }

  const inLayer = (row) => {
    const w = layerAt(row);
    return /^(above|below) /.test(w) ? w : 'in ' + w;
  };

  /* One card per frequency, answering one question: does this gamma sink
     in the layer it should? A badge says it for the whole frequency, a
     line per blade says where, and the picture is the very source the
     lines are about, with a tick or cross where it dips. */
  function expectCard(kind, checks, noIml) {
    const K = KIND[kind];
    const want = K.want;
    const col = K.tok;
    const name = K.name;
    const got = checks.filter((c) => c.row != null);
    const status = got.some((c) => !c.agree) ? 'off'
      : got.length ? 'match' : 'none';
    const badge = status === 'off' ? '\u2717 Does not match'
      : status === 'match' ? (got.length < checks.length
        ? '\u2713 Matches where it can tell' : '\u2713 Matches')
        : '\u2013 Can\u2019t tell';
    const card = el('div', { class: 'sa-exp ' + kind + ' ' + status }, [
      el('h4', {}, [
        el('i', { class: 'sa-swatch', style: 'background:' + tok(col) }),
        el('span', { text: K.title }),
        el('span', { class: 'sa-badge ' + status, text: noIml
          ? '\u2013 Not checked' : badge }),
      ]),
      el('p', { class: 'sa-exp-why', text: K.why }),
    ]);
    if (noIml) {
      card.appendChild(el('p', { class: 'sa-exp-why', text: 'IML is not its '
        + 'own layer in this scheme, so there is nothing to check it '
        + 'against. Choose "its own (IML)" in Step 3 to see it.' }));
      return card;
    }
    const rows = el('div', { class: 'sa-verdicts' });
    for (const c of checks) {
      const blade = c.blade === 'upper' ? 'Upper blade' : 'Lower blade';
      const layer = LAYER[c.region] || c.region;
      let cls, icon, text;
      if (c.row == null) {
        cls = 'none'; icon = '\u2013';
        text = blade + ': can\u2019t tell \u2014 no trusted ' + name
          + ' source dips in this blade\u2019s molecular layer';
      } else if (c.agree) {
        cls = 'match'; icon = '\u2713';
        text = blade + ': sinks in ' + layer + ' (ch ' + data.channels[c.row] + ')';
      } else {
        cls = 'off'; icon = '\u2717';
        text = blade + ': sinks ' + Math.abs(c.off) + ' ch '
          + (c.off > 0 ? 'below ' : 'above ') + layer + ' (ch '
          + data.channels[c.row] + ', ' + inLayer(c.row) + ')';
      }
      rows.appendChild(el('div', { class: 'sa-verdict ' + cls }, [
        el('b', { text: icon }), el('span', { text: text })]));
    }
    if (!checks.length) {
      rows.appendChild(el('div', { class: 'sa-verdict none' }, [
        el('b', { text: '\u2013' }),
        el('span', { text: 'No molecular layer drawn yet to check.' })]));
    }
    card.appendChild(rows);

    const comps = (ica.components || []).filter((x) => x.kind === kind);
    const byIndex = new Map(comps.map((x) => [x.index, x]));
    const shown = [...new Set(got.map((c) => c.component))]
      .map((i) => byIndex.get(i)).filter(Boolean);
    // One picture per source the verdicts are about, side by side.
    const pics = el('div', { class: 'sa-pics' });
    for (const cm of shown) {
      const marks = got.filter((c) => c.component === cm.index);
      const cv = el('canvas');
      const elsewhere = cm.sink_row != null
        && !marks.some((m) => m.row === cm.sink_row);
      pics.appendChild(el('figure', { class: 'sa-pic' }, [cv,
        el('figcaption', { class: 'sa-exp-why', text: (shown.length > 1
          ? (marks.map((m) => (m.blade === 'upper' ? 'Upper' : 'Lower'))
            .join(' and ') + ' blade: the ') : 'The ')
          + cm.peak_hz + ' Hz source, ' + pct(cm.variance) + ' of the gamma '
          + 'field, came back in both halves of the walking.'
          + (elsewhere ? ' Its deepest dip is at ch ' + cm.sink_channel
            + ' (' + layerAt(cm.sink_row) + '); the mark is where it dips '
            + 'by the molecular layer.' : '') })]));
      requestAnimationFrame(() => expectPanel(cv, cm, kind, col, marks));
    }
    if (shown.length) card.appendChild(pics);

    if (status === 'none' || got.length < checks.length) {
      // Nothing it can vouch for on a blade: say what that means, and show
      // the nearest thing it did find and why it does not count.
      const trusted = comps.filter((x) => (x.stability || 0) >= TRUST)
        .sort((x, y) => y.variance - x.variance);
      const near = shown.length ? null
        : trusted[0] || comps.slice().sort((x, y) => y.variance - x.variance)[0];
      if (near) {
        const cv = el('canvas');
        card.appendChild(cv);
        const ok = (near.stability || 0) >= TRUST;
        card.appendChild(el('p', { class: 'sa-exp-why', text: 'Nearest thing '
          + 'it found: a ' + near.peak_hz + ' Hz source, ' + pct(near.variance)
          + ' of the gamma field. ' + (ok
            ? 'It came back in both halves, but ' + (near.sink_row != null
              ? 'it sinks at ch ' + near.sink_channel + ' ('
                + layerAt(near.sink_row) + ') and does not dip in the '
                + 'molecular layer' : 'it has no clear sink')
              + ', so it does not count.'
            : 'It came back only ' + Math.round(100 * (near.stability || 0))
              + '% alike when ICA was refit on each half of the walking '
              + '(it needs ' + Math.round(100 * TRUST) + '%), so it does '
              + 'not count.') }));
        requestAnimationFrame(() => expectPanel(cv, near, kind, col, []));
      } else if (!comps.length) {
        card.appendChild(el('p', { class: 'sa-exp-why', text: 'ICA found no '
          + name + ' source at all: none of the sources it pulled out peaks '
          + 'in that range.' }));
      }
      card.appendChild(el('p', { class: 'sa-mean', text: 'Can\u2019t tell '
        + 'means Method B has nothing to say about that blade\u2019s ' + want
        + ' line: no ' + name + ' source both came back when ICA was refit '
        + 'on each half of the walking and dips in that molecular layer. It '
        + 'neither confirms nor contradicts Method A, whose thirds stand on '
        + 'their own there.' + (kind !== 'slow' ? ' This gamma is small in '
          + 'mice, so this is common.' : '') + ' More Theta Walk seconds '
        + 'help.' }));
    }
    return card;
  }

  const pct = (v) => {
    const x = 100 * (v || 0);
    return (x >= 10 ? x.toFixed(0) : x.toFixed(1)) + '%';
  };

  /* One component against the layer it should be in: that layer shaded in
     the component's colour, the hilus thin and grey, the CSD of its
     loading as one curve, and a tick or cross where each verdict found
     it dipping (or, with no verdicts, a ring at its sink). */
  function expectPanel(cv, cm, kind, col, marks) {
    const chans = ica.channels;
    const H = Math.max(240, Math.min(420, chans.length * 6));
    const { ctx, w } = prep(cv, H + 6);
    const left = 26, top = 3, pw = w - left - 6, lane = H / chans.length;
    const want = KIND[kind].ids;
    ctx.font = '10px system-ui, sans-serif';
    for (const id of want) {
      const r = layerRows(id);
      if (!r) continue;
      ctx.fillStyle = tok(col);
      ctx.globalAlpha = 0.18;
      ctx.fillRect(left, top + r[0] * lane, pw, (r[1] - r[0]) * lane);
      ctx.globalAlpha = 1;
      ctx.textAlign = 'right'; ctx.textBaseline = 'top';
      ctx.fillText(LAYER[id], left + pw - 4, top + r[0] * lane + 2);
    }
    const hil = layerRows('hil');
    if (hil) {
      ctx.strokeStyle = tok('--text-3'); ctx.lineWidth = 1;
      for (const y of [hil[0], hil[1]]) {
        ctx.beginPath(); ctx.moveTo(left, top + y * lane); ctx.lineTo(left + pw, top + y * lane);
        ctx.stroke();
      }
      ctx.fillStyle = tok('--text-3');
      ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      ctx.fillText('HIL', left + pw - 4, top + (hil[0] + hil[1]) / 2 * lane);
    }
    ctx.strokeStyle = tok('--line'); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(left + pw / 2, top); ctx.lineTo(left + pw / 2, top + H);
    ctx.stroke();
    const vals = cm.csd || [];
    const fin = vals.filter((x) => x != null);
    const lim = fin.length ? Math.max(...fin.map(Math.abs)) || 1 : 1;
    const X = (row) => left + pw / 2 + (vals[row] / lim) * (pw / 2 - 6);
    const Y = (row) => top + (row + 0.5) * lane;
    ctx.strokeStyle = tok(col); ctx.lineWidth = 2;
    curve(ctx, vals.map((x, i) => (x == null ? null : [X(i), Y(i)])));
    ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.font = '600 11px system-ui, sans-serif';
    const pts = (marks && marks.length ? marks : [])
      .filter((m) => vals[m.row] != null);
    for (const m of pts) {
      const c = tok(m.agree ? '--ok' : '--err');
      ctx.fillStyle = c;
      ctx.beginPath(); ctx.arc(X(m.row), Y(m.row), 5, 0, Math.PI * 2); ctx.fill();
      ctx.fillText((m.agree ? '\u2713 ' : '\u2717 ') + 'ch ' + chans[m.row],
                   X(m.row) + 8, Y(m.row));
    }
    if (!pts.length && cm.sink_row != null && vals[cm.sink_row] != null) {
      ctx.strokeStyle = tok('--text-2'); ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(X(cm.sink_row), Y(cm.sink_row), 5, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = tok('--text-2');
      ctx.fillText('sink ch ' + cm.sink_channel, X(cm.sink_row) + 8, Y(cm.sink_row));
    }
    axisChannels(ctx, chans, top, lane, left - 3);
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
      curve(ctx, vals.map((x, i) => (x == null ? null
        : [w / 2 + (x / lim) * (w / 2 - 4), (i + 0.5) * lane])));
    };
    ctx.strokeStyle = tok('--line'); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(w / 2, 0); ctx.lineTo(w / 2, H); ctx.stroke();
    draw(cm.csd, tok((KIND[cm.kind] || KIND.fast).tok), 1.6);
    // The hilus only, thin and grey: enough to tell the blades apart.
    const hil = layerRows('hil');
    if (hil) {
      ctx.strokeStyle = tok('--text-3'); ctx.lineWidth = 1;
      for (const y of [hil[0], hil[1]]) {
        ctx.beginPath(); ctx.moveTo(0, y * lane); ctx.lineTo(w, y * lane); ctx.stroke();
      }
    }
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
