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
      grid.appendChild(phaseCard());
      grid.appendChild(methodB());
      if (!explainPosed) {
        explainPosed = true;
        setTimeout(() => explainer(true, Number(Q.get('explain')) || 0), 0);
      }
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
    const fisLine = stepLines().find((l) => l.below === 'dg_oml1');
    return el('div', { class: 'sa-verdict ' + (ok ? 'match' : 'off') }, [
      el('b', { text: ok ? '\u2713' : '\u2717' }),
      el('span', { text: 'CA1 SP to fissure : fissure to GCL1 is '
        + ratio.toFixed(1) + ' : 1. In mice it is about 2 : 1 (1.5-2.8; '
        + 'Paleologos et al. 2025). ' + (ok ? 'In range.'
          : 'Out of range: for 2 : 1 the fissure would sit above ch ' + ch
            + '.') }),
      ok ? null : moveBtn(fisLine, at21),
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
      const mv = ok ? null : lineToTakeIn('dg_mml1', best.r);
      c.appendChild(el('div', { class: 'sa-verdict ' + (ok ? 'match' : 'off') }, [
        el('b', { text: ok ? '\u2713' : '\u2717' }),
        el('span', { text: 'Strongest theta sink between the fissure and '
          + 'GCL1: ch ' + best.ch + ', ' + (ok ? 'in MML1, as expected.'
            : Math.abs(off) + ' ch ' + (off < 0 ? 'above' : 'below')
              + ' MML1 (' + layerAt(best.r) + ').') }),
        mv ? moveBtn(mv.line, mv.to) : null,
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
        + (ica.theta_all_time ? 'recording' : 'Theta Walk') + '. Three runs: '
        + '25-200 Hz, then 90-160 and 55-90 Hz on their own. Each: its CSD '
        + '(the dip is its sink), peak frequency, share of its run\u2019s '
        + 'band, and how well it came back in both halves.' }));
      const grid = el('div', { class: 'sa-ica' });
      for (const cm of (ica.components || []).slice(0, 24)) {
        const cv = el('canvas');
        grid.appendChild(el('div', { class: 'sa-comp ' + (cm.kind || '')
            + (state && state.ica_pick === cm.index ? ' picked' : '')
            + ((cm.stability || 0) < TRUST ? ' weak' : '') }, [
          el('div', {}, [el('b', { text: ((KIND[cm.kind] || {}).short || '?')
            + ' \u00b7 ' + cm.peak_hz + ' Hz' })]),
          el('div', { text: pct(cm.variance) + ' of '
            + (cm.band === 'fast' ? '90-160' : cm.band === 'mid' ? '55-90'
              : '25-200') + ' Hz \u00b7 '
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
    // Not checked (no IML to check mid gamma against) is not "can't tell".
    const card = el('div', { class: 'sa-exp ' + kind + ' '
                               + (noIml ? 'unchecked' : status) }, [
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
      const mv = cls === 'off' ? lineToTakeIn(c.region, c.row) : null;
      rows.appendChild(el('div', { class: 'sa-verdict ' + cls }, [
        el('b', { text: icon }), el('span', { text: text }),
        mv ? moveBtn(mv.line, mv.to) : null]));
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
          + cm.peak_hz + ' Hz source, ' + pct(cm.variance) + ' '
          + shareOf(cm) + ', came back in both halves of the walking.'
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
          + ' ' + shareOf(near) + '. ' + (ok
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

  /* What a component's share is a share of: its own run's band. */
  const shareOf = (cm) => (cm.band === 'fast' ? 'of the 90-160 Hz field'
    : cm.band === 'mid' ? 'of the 55-90 Hz field' : 'of the 25-200 Hz field');

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

  /* ======================================================================
     Theta phase x depth gamma maps (beta, 2026-10-12)
     ======================================================================
     For every channel, how strong each gamma is at each moment of CA1
     theta (backend/stratasteps.py phase_map). After Schomburg et al. 2014
     and Fernandez-Ruiz et al. 2021: each input to the dentate brings its
     own gamma at its own moment of theta, into its own band of the
     molecular layer, so going down the probe the hot spot moves -- and
     where it moves is a boundary. Two cycles are drawn, as the papers do,
     so a spot near 0/360 is not cut in half. */
  let pmap = null;
  let pmapFor = null;
  let pmapErr = null;
  let pmapBusy = false;
  let pmView = 'csd';              // 'csd' | 'lfp'
  let pmMaps = false;              // the maps themselves, folded
  let pmNorm = 'depth';            // 'depth' | 'map'
  // Where the papers put each gamma, CA1 theta, 0 = peak (Fernandez-Ruiz
  // et al. 2021, rats).
  const PM_PHASE = { slow: 47, mid: 284, fast: 168 };

  async function loadPhaseMap() {
    const key = [GID, JSON.stringify(state.overrides || {}), state.states_n || 0]
      .join('|');
    if (pmapBusy || pmapFor === key) return;
    pmapBusy = true;
    pmapErr = null;
    try {
      const r = await post('/api/strata/' + encodeURIComponent(GID) + '/phasemap',
                           { path, channels: state.channels,
                             overrides: state.overrides || {} });
      pmap = r.map;
    } catch (e) {
      pmapErr = e.message;
      pmap = null;
    }
    pmapFor = key;
    pmapBusy = false;
    if (state && state.step === '3') render();
  }

  function phaseCard() {
    const c = el('div', { class: 'sa-card sa-pm', style: 'grid-column: 1 / -1' }, [
      el('h3', { class: 'sa-pm-head' }, [
        el('span', { text: 'Theta phase \u00d7 depth: when each gamma comes, '
          + 'and where' }),
        el('span', { class: 'sa-beta', text: 'beta' }),
        el('button', { class: 'sa-q', text: '?', title: 'How to read this',
                       onclick: () => explainer(true) }),
      ]),
    ]);
    if (!pmap) {
      c.appendChild(el('p', { text: pmapErr ? 'Could not draw it: ' + pmapErr
        : 'Working it out \u2014 half a minute the first time, then it is '
          + 'kept.' }));
      if (!pmapErr) loadPhaseMap();
      return c;
    }
    /* What it says, line by line: where the line is now, where the phase
       map would put it, and a button to put it there. The pictures are a
       click away. */
    c.appendChild(el('p', { class: 'sa-pm-note', text: pmap.walk_s + ' s of '
      + (pmap.theta_all_time ? 'recording' : 'Theta Walk') + ' \u00b7 theta '
      + 'from ch ' + pmap.ref_channel + ' (CA1 SP)' }));
    const live = !!(state && state.step === '3' && state.lines
                    && state.lines.length && !Q.get('step'));
    const list = el('div', { class: 'sa-sugg-list' });
    const rows = pmSuggestions();
    if (!rows.length) {
      list.appendChild(el('p', { class: 'sa-exp-why', text: 'Nothing to say '
        + 'yet: Step 3 needs its lines first.' }));
    }
    for (const r of rows) {
      const ok = r.to == null || r.to === r.line.at;
      const ch = (row) => (row >= data.channels.length ? 'the end'
        : 'ch ' + data.channels[row]);
      list.appendChild(el('div', { class: 'sa-sugg ' + (r.unsure ? 'unsure'
                                     : ok ? 'match' : 'off') }, [
        el('b', { class: 'sa-sugg-name', text: r.name }),
        el('span', { class: 'sa-sugg-now', text: 'now above ' + ch(r.line.at) }),
        el('span', { class: 'sa-sugg-math', text: r.unsure
          ? '\u2013 the phase map can\u2019t tell'
          : ok ? '\u2713 the phase map agrees'
            : 'phase map: above ' + ch(r.to) }),
        ok ? null : el('button', {
          class: 'mini', text: 'Move',
          disabled: live ? null : 'disabled',
          title: live ? 'Move the ' + r.name + ' line to above ' + ch(r.to)
            + ' in the labelling window. It stays a proposal until you '
            + 'Accept.' : 'Open Step 3 in the labelling window to move lines '
            + 'from here.',
          onclick: () => sendMove(r.line, r.to),
        }),
        el('span', { class: 'sa-sugg-why', text: r.why }),
      ]));
    }
    c.appendChild(list);
    c.appendChild(el('button', {
      class: 'mini', style: 'margin-top:8px',
      text: (pmMaps ? '\u25be' : '\u25b8') + ' Show the maps',
      onclick: () => { pmMaps = !pmMaps; render(); },
    }));
    if (!pmMaps) return c;
    const seg = (opts, cur, set) => el('span', { class: 'ctl-seg' },
      opts.map(([v, t, why]) => el('button', {
        class: 'mini' + (cur === v ? ' on' : ''), text: t, title: why,
        onclick: () => { set(v); render(); } })));
    c.appendChild(el('div', { class: 'sa-pm-ctl' }, [
      seg([['csd', 'CSD', 'Gamma in the current source density: sharp in '
             + 'depth, where the synapses are.'],
           ['lfp', 'LFP', 'Gamma in the raw field: smoother, spread by '
             + 'volume conduction.']], pmView, (v) => { pmView = v; }),
      seg([['depth', 'Each depth', 'Each channel on its own scale: when in '
             + 'theta each channel\u2019s gamma comes, however weak. A '
             + 'channel with a different gain cannot take over the picture.'],
           ['map', 'Whole map', 'One colour scale for every channel: where '
             + 'the gamma is strongest. In the CSD a contact with a different '
             + 'gain shows as a stripe across every phase.']],
          pmNorm, (v) => { pmNorm = v; }),
      el('span', { class: 'sa-pm-note', text: '0\u00b0 is the peak of CA1 '
        + 'theta' }),
    ]));
    const row = el('div', { class: 'sa-pm-row' });
    for (const bd of pmap.bands || []) {
      const K = KIND[bd.id] || KIND.fast;
      const cv = el('canvas');
      row.appendChild(el('figure', { class: 'sa-pm-fig' }, [
        el('figcaption', {}, [
          el('i', { class: 'sa-swatch', style: 'background:' + tok(K.tok) }),
          el('b', { text: K.short.replace(/^./, (x) => x.toUpperCase()) + ' '
            + bd.lo + '-' + bd.hi + ' Hz' }),
          el('span', { text: ' \u2192 ' + K.want }),
        ]),
        cv,
      ]));
      requestAnimationFrame(() => pmPanel(cv, bd));
    }
    c.appendChild(row);
    return c;
  }

  /* The map's values for one band, normalised as asked: rows x bins. */
  function pmValues(bd) {
    const raw = (bd[pmView] || []).map((r) => r.map((v) => (v == null ? null : v)));
    if (pmNorm === 'depth') {
      return raw.map((r) => {
        const f = r.filter((v) => v != null);
        if (!f.length) return r;
        const lo = Math.min(...f), hi = Math.max(...f);
        return r.map((v) => (v == null ? null : hi > lo ? (v - lo) / (hi - lo) : 0));
      });
    }
    const all = [];
    raw.forEach((r) => r.forEach((v) => { if (v != null) all.push(v); }));
    all.sort((a, b) => a - b);
    const lo = all.length ? all[Math.floor(all.length * 0.02)] : 0;
    const hi = all.length ? all[Math.floor(all.length * 0.97)] : 1;
    return raw.map((r) => r.map((v) => (v == null ? null
      : Math.max(0, Math.min(1, (v - lo) / ((hi - lo) || 1))))));
  }

  /* Each channel's reading of one band: its preferred phase (the
     amplitude-weighted circular mean, above the channel's own floor) and
     how strongly theta locks it -- (max - min) / mean, which a contact's
     gain cancels out of. */
  const PM_LOCKED = 0.12;          // locked enough to have a phase
  function pmRows(bd) {
    const A = bd[pmView] || [];
    const deg = pmap.phase_deg;
    return A.map((row) => {
      const f = (row || []).filter((v) => v != null);
      if (f.length < deg.length) return null;
      const lo = Math.min(...f), hi = Math.max(...f);
      const mean = f.reduce((a, b) => a + b, 0) / f.length;
      let x = 0, y = 0;
      row.forEach((v, j) => {
        const w = v - lo, a = deg[j] * Math.PI / 180;
        x += w * Math.cos(a); y += w * Math.sin(a);
      });
      const phase = ((Math.atan2(y, x) * 180 / Math.PI) + 360) % 360;
      return { phase, lock: mean > 0 ? (hi - lo) / mean : 0 };
    });
  }
  const angDiff = (a, b) => Math.abs((((a - b) % 360) + 540) % 360 - 180);

  /* The most theta-locked channel in the upper molecular layer. */
  function pmPeak(bd, rows) {
    rows = rows || pmRows(bd);
    const rowOf = new Map(data.channels.map((ch, i) => [ch, i]));
    const top = (layerRows('dg_oml1') || [])[0];
    const g = layerRows('dg_gcl1');
    let best = null;
    pmap.channels.forEach((ch, k) => {
      const r = rowOf.get(ch);
      const q = rows[k];
      if (r == null || !q) return;
      if (top != null && g && (r < top || r >= g[0])) return;
      if (!best || q.lock > best.lock) best = { k, r, ch, phase: q.phase, lock: q.lock };
    });
    return best;
  }

  /* Going down from a little above the fissure to the granule layer, the
     biggest turn in preferred phase between neighbouring locked channels
     -- a picture of where one input's gamma hands over to the next. */
  function pmJump(bd, rows) {
    rows = rows || pmRows(bd);
    const rowOf = new Map(data.channels.map((ch, i) => [ch, i]));
    const top = (layerRows('dg_oml1') || [])[0];
    const g = layerRows('dg_gcl1');
    const lo = top != null ? Math.max(0, top - 8) : 0;
    const hi = g ? g[0] : data.channels.length;
    let best = null, prev = null;
    pmap.channels.forEach((ch, k) => {
      const r = rowOf.get(ch);
      const q = rows[k];
      if (r == null || r < lo || r >= hi || !q || q.lock < PM_LOCKED) return;
      if (prev) {
        const d = angDiff(q.phase, prev.q.phase);
        if (d >= 60 && (!best || d > best.d)) {
          best = { d, kAbove: prev.k, kBelow: k, chAbove: prev.ch, chBelow: ch,
                   rBelow: r, from: prev.q.phase, to: q.phase };
        }
      }
      prev = { k, ch, q };
    });
    return best;
  }

  /* The nearest of the step's lines to a row edge, by name. */
  function nearestLine(rEdge) {
    let best = null;
    for (const l of stepLines()) {
      if (l.at == null) continue;
      const d = Math.abs(l.at - rEdge);
      if (!best || d < best.d) best = { d, l };
    }
    return best;
  }

  /* The lines the phase map has something to say about:
       the fissure     where theta phase jumps going down (in mice the
                       sharpest jump is across the fissure: Lasztoczi &
                       Klausberger 2017)
       OML             takes in the channel slow gamma (LEC) is most
                       theta-locked on
       MML             takes in the channel fast gamma (MEC) is most
                       theta-locked on
       IML             mid gamma (commissural), when IML is its own layer
     Each: { name, line, to, why } -- `to` the row the line would sit
     above, or null when the line already agrees. */
  function pmSuggestions() {
    const ls = stepLines().filter((l) => l.at != null);
    if (!ls.length || !pmap) return [];
    const bands = Object.fromEntries((pmap.bands || []).map((b) => [b.id, b]));
    const ch = (row) => 'ch ' + data.channels[Math.min(row, data.channels.length - 1)];
    const out = [];
    const fis = ls.find((l) => l.below === 'dg_oml1');
    let jump = null;
    for (const id of ['slow', 'fast']) {
      const j = bands[id] && pmJump(bands[id]);
      if (j && (!jump || j.d > jump.d)) jump = Object.assign({ band: id }, j);
    }
    if (fis && jump) {
      out.push({ name: 'Fissure', line: fis, to: jump.rBelow,
                 why: KIND[jump.band].short + ' turns from '
                   + Math.round(jump.from) + '\u00b0 to ' + Math.round(jump.to)
                   + '\u00b0 between ' + 'ch ' + jump.chAbove + ' and ch '
                   + jump.chBelow + '.' });
    }
    // A layer should take in the channel its gamma is most locked on: pull
    // its top line up to it, or push its bottom line down past it.
    const layer = (id, band, name) => {
      const top = ls.find((l) => l.below === id);
      const bot = ls.find((l) => l.above === id);
      const b = bands[band] && pmPeak(bands[band]);
      if (!top || !b) return;
      const why = KIND[band].short + ' is most theta-locked at ch ' + b.ch
        + ' (' + Math.round(b.phase) + '\u00b0).';
      if (b.r < top.at) {
        out.push({ name: name + ' top', line: top, to: b.r, why });
      } else if (bot && b.r >= bot.at) {
        out.push({ name: name + ' bottom', line: bot, to: b.r + 1, why });
      } else {
        out.push({ name: name, line: top, to: null,
                   why: why.replace(/\.$/, '') + ', inside ' + name + '.' });
      }
    };
    const ps = bands.slow && pmPeak(bands.slow);
    const pf = bands.fast && pmPeak(bands.fast);
    const omlMml = ls.find((l) => l.above === 'dg_oml1' && l.below === 'dg_mml1');
    if (ps && pf && Math.abs(ps.r - pf.r) <= 1 && omlMml) {
      // In mice both lean to the trough and can lock on one channel; then
      // nothing here separates OML from MML.
      out.push({ name: 'OML1 | MML1', line: omlMml, to: null, unsure: true,
                 why: 'Slow and fast gamma are both most theta-locked at ch '
                   + ps.ch + (pf.ch !== ps.ch ? '/' + pf.ch : '') + ', so the '
                   + 'phase map cannot tell OML from MML here (common in '
                   + 'mice). Method A and B decide this line.' });
    } else {
      layer('dg_oml1', 'slow', 'OML1');
      layer('dg_mml1', 'fast', 'MML1');
    }
    if (ls.some((l) => l.below === 'dg_iml1')) layer('dg_iml1', 'mid', 'IML1');
    void ch;
    return out;
  }

  /* Move, wherever a verdict says where a line should be. Live only when
     the labelling window has Step 3 open (this page follows it); in a
     posed page it says why it cannot. */
  const canMove = () => !!(state && state.step === '3' && state.lines
                           && state.lines.length && !Q.get('step'));
  function moveBtn(line, to) {
    if (!line || to == null || to === line.at) return null;
    const live = canMove();
    const ch = to >= data.channels.length ? 'the end' : 'ch ' + data.channels[to];
    const nm = (LAYER[line.above] || line.above) + ' | '
      + (LAYER[line.below] || line.below || 'below');
    return el('button', {
      class: 'mini sa-move', text: 'Move',
      disabled: live ? null : 'disabled',
      title: live ? 'Move the ' + nm + ' line to above ' + ch + ' in the '
        + 'labelling window. It stays a proposal until you Accept.'
        : 'Open Step 3 in the labelling window to move lines from here.',
      onclick: () => sendMove(line, to),
    });
  }
  /* The line that would take row `row` into region `id`: its top line
     pulled up to the row, or its bottom line pushed down past it. */
  function lineToTakeIn(id, row) {
    const ls = stepLines();
    const top = ls.find((l) => l.below === id);
    const bot = ls.find((l) => l.above === id);
    if (top && top.at != null && row < top.at) return { line: top, to: row };
    if (bot && bot.at != null && row >= bot.at) return { line: bot, to: row + 1 };
    return null;
  }

  /* Ask the labelling window to move a line. It owns the lines; this page
     only follows them. Over the same link it publishes on, the other way. */
  async function sendMove(line, to) {
    try {
      await fetch('/api/link', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channel: 'strata-cmd:' + GID, origin: 'strata-aid',
                               value: { at: Date.now(), id: line.id || null,
                                        above: line.above, below: line.below,
                                        to } }) });
    } catch (e) { /* the labelling window says when a move lands */ }
  }

  function pmSummary(bd) {
    const K = KIND[bd.id] || KIND.fast;
    const rows = pmRows(bd);
    const b = pmPeak(bd, rows);
    const out = el('div', { class: 'sa-verdicts' });
    if (!b) {
      out.appendChild(el('p', { class: 'sa-exp-why', text: 'Nothing to read '
        + 'in the molecular layer yet.' }));
      return out;
    }
    const where = layerAt(b.r);
    const ok = where.indexOf(K.want) >= 0;
    const lit = PM_PHASE[bd.id];
    out.appendChild(el('div', { class: 'sa-verdict ' + (ok ? 'match' : 'off') }, [
      el('b', { text: ok ? '\u2713' : '\u2717' }),
      el('span', { text: 'Most theta-locked in the molecular layer: ch ' + b.ch
        + ' (' + where + '), at ' + Math.round(b.phase) + '\u00b0. Expected '
        + K.want + (lit != null ? ' (~' + lit + '\u00b0 in rats)' : '') + '.' }),
    ]));
    const j = pmJump(bd, rows);
    if (j) {
      const near = nearestLine(j.rBelow);
      out.appendChild(el('div', { class: 'sa-verdict none' }, [
        el('b', { text: '\u21c5' }),
        el('span', { text: 'Its phase turns from ' + Math.round(j.from)
          + '\u00b0 to ' + Math.round(j.to) + '\u00b0 between ch ' + j.chAbove
          + ' and ch ' + j.chBelow + (near ? (near.d === 0 ? ', right on'
            : ', ' + near.d + ' ch from') + ' the ' + (LAYER[near.l.above]
              || near.l.above) + '|' + (LAYER[near.l.below] || near.l.below)
            + ' line' : '') + '.' }),
      ]));
    }
    return out;
  }

  function pmPanel(cv, bd) {
    if (!cv.isConnected) return;
    const chans = pmap.channels;
    const n = chans.length, nb = pmap.phase_deg.length;
    const H = Math.max(240, Math.min(460, n * 7));
    const wave = 22;
    const { ctx, w } = prep(cv, H + wave + 20);
    const left = 26, right = 4, top = wave + 2;
    const pw = w - left - right, lane = H / n;
    const V = pmValues(bd);
    // two cycles
    const cols = nb * 2;
    const img = ctx.createImageData(cols, n);
    for (let i = 0; i < n; i++) {
      for (let x = 0; x < cols; x++) {
        const v = (V[i] || [])[x % nb];
        const o = (i * cols + x) * 4;
        if (v == null) { img.data[o + 3] = 0; continue; }
        const c = jet(v);
        img.data[o] = c[0]; img.data[o + 1] = c[1]; img.data[o + 2] = c[2];
        img.data[o + 3] = 255;
      }
    }
    const off = document.createElement('canvas');
    off.width = cols; off.height = n;
    off.getContext('2d').putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, left, top, pw, H);
    // theta, as a guide: 0 deg its peak
    const X = (deg) => left + pw * deg / 720;
    ctx.strokeStyle = tok('--c3'); ctx.lineWidth = 1.5;
    ctx.beginPath();
    for (let d = 0; d <= 720; d += 6) {
      const y = 2 + (wave - 6) * (0.5 - 0.5 * Math.cos(d * Math.PI / 180));
      if (d === 0) ctx.moveTo(X(d), y); else ctx.lineTo(X(d), y);
    }
    ctx.stroke();
    // where the papers put this gamma (rats), twice
    const lit = PM_PHASE[bd.id];
    if (lit != null) {
      ctx.fillStyle = tok((KIND[bd.id] || KIND.fast).tok);
      for (const d of [lit, lit + 360]) {
        ctx.beginPath();
        ctx.moveTo(X(d) - 4, 0); ctx.lineTo(X(d) + 4, 0); ctx.lineTo(X(d), 6);
        ctx.closePath(); ctx.fill();
      }
    }
    overlay(ctx, chans, left, pw, top, lane, true);
    axisChannels(ctx, chans, top, lane, left - 3);
    // each locked channel's preferred phase: the path the eye follows down
    const rows = pmRows(bd);
    ctx.fillStyle = '#fff';
    rows.forEach((q, k) => {
      if (!q || q.lock < PM_LOCKED) return;
      for (const d of [q.phase, q.phase + 360]) {
        ctx.globalAlpha = Math.min(1, 0.35 + q.lock);
        ctx.beginPath();
        ctx.arc(X(d), top + (k + 0.5) * lane, Math.max(1.6, Math.min(3, lane * 0.35)),
                0, Math.PI * 2);
        ctx.fill();
      }
    });
    ctx.globalAlpha = 1;
    const j = pmJump(bd, rows);
    if (j) {
      const y = Math.round(top + j.kBelow * lane) + 0.5;
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(left + pw, y); ctx.stroke();
      ctx.setLineDash([]);
      ctx.font = '600 10px system-ui, sans-serif';
      ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
      const txt = 'phase jump';
      const tw = ctx.measureText(txt).width;
      ctx.fillStyle = 'rgba(0,0,0,.6)';
      ctx.fillRect(left + 3, y - 13, tw + 6, 12);
      ctx.fillStyle = '#fff';
      ctx.fillText(txt, left + 6, y - 2);
    }
    const b = pmPeak(bd, rows);
    if (b) {
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5;
      for (const d of [b.phase, b.phase + 360]) {
        ctx.beginPath(); ctx.arc(X(d), top + (b.k + 0.5) * lane, 5.5, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
    ctx.fillStyle = tok('--text-3');
    ctx.font = '9.5px system-ui, sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (const d of [0, 180, 360, 540, 720]) {
      ctx.fillText(d + '\u00b0', Math.min(w - 12, Math.max(left + 8, X(d))),
                   top + H + 4);
    }
  }

  /* ---------- "?": how to read it, animated ---------- */
  const EXPLAIN = [
    { title: 'Theta has a clock',
      text: 'This is theta in CA1\u2019s pyramidal layer. Every moment gets a '
        + 'phase: 0\u00b0 at the peak, 180\u00b0 in the trough, 360\u00b0 at '
        + 'the next peak.' },
    { title: 'Gamma rides on theta',
      text: 'Gamma comes in short bursts on top of theta. Each input to the '
        + 'dentate brings its own, into its own band of the molecular layer: '
        + 'slow gamma from the lateral entorhinal cortex into the OML, fast '
        + 'from the medial entorhinal cortex into the MML, mid from the other '
        + 'hippocampus into the IML. Each tends to come at its own moment.' },
    { title: 'Pour it into a grid',
      text: 'For every channel, the strength of the gamma at each moment is '
        + 'dropped into the column for that phase. Over thousands of theta '
        + 'cycles a picture builds up: depth down, theta phase across.' },
    { title: 'Read the picture',
      text: 'A hot spot\u2019s row is the layer that gamma lives in; its column '
        + 'is when in theta it comes. The white dots follow each channel\u2019s '
        + 'favourite moment down the probe. Where they jump to another '
        + 'phase you are crossing from one input\u2019s territory into the '
        + 'next: that is a boundary, and the map marks the biggest jump.' },
    { title: 'Mice are not rats',
      text: 'The little triangles are where the papers put each gamma in rats '
        + '(slow ~47\u00b0, fast ~168\u00b0, mid ~284\u00b0; Fern\u00e1ndez-Ruiz '
        + 'et al. 2021). In mice the dentate\u2019s slow and fast gamma both '
        + 'lean to the trough, while gamma in CA1\u2019s lacunosum-moleculare '
        + 'comes near the peak (Laszt\u00f3czi & Klausberger 2017): there the '
        + 'sharpest jump is often the fissure itself. So in mice, read OML '
        + 'against MML from where each gamma is most locked, and a jump as a '
        + 'check on the fissure. Beta: a picture to look at, not a vote.' },
  ];
  let exScene = 0;
  let exAuto = true;
  let exRaf = null;
  let exT0 = 0;

  function explainer(on, scene) {
    let box = document.getElementById('saExplain');
    if (!on) {
      if (exRaf) cancelAnimationFrame(exRaf);
      exRaf = null;
      if (box) box.remove();
      return;
    }
    if (box) box.remove();
    exScene = 0; exAuto = true; exT0 = performance.now();
    const cv = el('canvas', { class: 'sa-ex-cv' });
    const title = el('h4', { class: 'sa-ex-title' });
    const text = el('p', { class: 'sa-ex-text' });
    const dots = el('div', { class: 'sa-ex-dots' });
    const go = (k) => {
      exScene = (k + EXPLAIN.length) % EXPLAIN.length;
      exT0 = performance.now();
      paintText();
    };
    const paintText = () => {
      title.textContent = (exScene + 1) + ' / ' + EXPLAIN.length + ' \u00b7 '
        + EXPLAIN[exScene].title;
      text.textContent = EXPLAIN[exScene].text;
      dots.innerHTML = '';
      EXPLAIN.forEach((_, k) => dots.appendChild(el('button', {
        class: 'sa-ex-dot' + (k === exScene ? ' on' : ''),
        title: EXPLAIN[k].title,
        onclick: () => { exAuto = false; go(k); } })));
    };
    box = el('div', { class: 'sa-explain', id: 'saExplain',
                      onclick: (e) => { if (e.target === box) explainer(false); } }, [
      el('div', { class: 'sa-ex-card' }, [
        el('button', { class: 'sa-ex-x', text: '\u00d7', title: 'Close',
                       onclick: () => explainer(false) }),
        title, cv, text,
        el('div', { class: 'sa-ex-nav' }, [
          el('button', { class: 'mini', text: '\u2190 Back',
                         onclick: () => { exAuto = false; go(exScene - 1); } }),
          dots,
          el('button', { class: 'mini', text: 'Next \u2192',
                         onclick: () => { exAuto = false; go(exScene + 1); } }),
        ]),
      ]),
    ]);
    document.body.appendChild(box);
    if (scene != null) { exAuto = false; exScene = scene % EXPLAIN.length; }
    paintText();
    const still = window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const frame = (now) => {
      if (!cv.isConnected) { exRaf = null; return; }
      const t = still ? 3.2 : (now - exT0) / 1000;
      if (exAuto && !still && t > 9) { go(exScene + 1); }
      drawScene(cv, exScene, t);
      exRaf = requestAnimationFrame(frame);
    };
    // One still frame at once (a hidden tab, or a headless page, may never
    // give a frame), then the animation.
    drawScene(cv, exScene, 3.2);
    exRaf = requestAnimationFrame(frame);
  }
  /* `?explain=N` opens the "?" at scene N once the step is drawn: a pose
     for a screenshot. */
  let explainPosed = Q.get('explain') == null;

  /* The scenes. t is seconds into the scene. */
  function drawScene(cv, k, t) {
    const { ctx, w } = prep(cv, 260);
    const h = 260;
    ctx.clearRect(0, 0, w, h);
    const C = { slow: tok('--c2'), mid: tok('--warn'), fast: tok('--c4'),
                theta: tok('--c3'), text: tok('--text'), dim: tok('--text-3'),
                line: tok('--line') };
    const ease = (x) => 1 - Math.pow(1 - Math.max(0, Math.min(1, x)), 3);
    const LAY = [['OML', 'slow', 47], ['MML', 'fast', 168], ['IML', 'mid', 284],
                 ['GCL', null, null]];
    // a theta wave across [x0, x1] at height y +- a, scrolling with t;
    // returns the phase (deg) at x
    const speed = 70;                      // degrees a second
    const phaseAt = (x, x0, span) => ((x - x0) / span) * 720 + t * speed;
    const thetaWave = (x0, x1, y, a) => {
      ctx.strokeStyle = C.theta; ctx.lineWidth = 2;
      ctx.beginPath();
      for (let x = x0; x <= x1; x += 2) {
        const d = phaseAt(x, x0, x1 - x0);
        const yy = y - a * Math.cos(d * Math.PI / 180);
        if (x === x0) ctx.moveTo(x, yy); else ctx.lineTo(x, yy);
      }
      ctx.stroke();
    };
    const label = (txt, x, y, col, align, size) => {
      ctx.fillStyle = col || C.text;
      ctx.font = (size || 11) + 'px system-ui, sans-serif';
      ctx.textAlign = align || 'left'; ctx.textBaseline = 'middle';
      ctx.fillText(txt, x, y);
    };
    // the pattern the grid ends up with: 1 near each layer's phase
    const hot = (li, deg) => {
      const pref = LAY[li][2];
      if (pref == null) return 0.05;
      const dd = Math.abs((((deg - pref) % 360) + 540) % 360 - 180);
      return Math.exp(-(dd * dd) / (2 * 45 * 45));
    };
    if (k === 0) {
      const x0 = 20, x1 = w - 196, y = 130;
      thetaWave(x0, x1, y, 60);
      const nowX = x0 + (x1 - x0) * 0.4;
      const d = phaseAt(nowX, x0, x1 - x0) % 360;
      ctx.strokeStyle = C.dim; ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(nowX, 40); ctx.lineTo(nowX, 220); ctx.stroke();
      ctx.setLineDash([]);
      const yy = y - 60 * Math.cos(d * Math.PI / 180);
      ctx.fillStyle = C.text;
      ctx.beginPath(); ctx.arc(nowX, yy, 6, 0, Math.PI * 2); ctx.fill();
      // the dial
      const cx = w - 80, cy = 130, R = 58;
      ctx.strokeStyle = C.line; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
      label('0\u00b0 peak', cx, cy - R - 12, C.dim, 'center', 10);
      label('180\u00b0 trough', cx, cy + R + 12, C.dim, 'center', 10);
      label('90\u00b0', cx + R + 14, cy, C.dim, 'center', 10);
      label('270\u00b0', cx - R - 16, cy, C.dim, 'center', 10);
      const a = (d - 90) * Math.PI / 180;
      ctx.strokeStyle = C.theta; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(cx, cy);
      ctx.lineTo(cx + R * 0.85 * Math.cos(a), cy + R * 0.85 * Math.sin(a));
      ctx.stroke();
      label(Math.round(d) + '\u00b0', cx, cy + 4, C.text, 'center', 13);
      return;
    }
    if (k === 1 || k === 2) {
      // a probe on the left, a lane per layer with its gamma riding theta
      const px = 28, laneTop = 54, laneH = 44;
      const x0 = 70, x1 = k === 1 ? w - 20 : w * 0.52;
      thetaWave(x0, x1, 26, 14);
      label('theta', x0 - 8, 26, C.theta, 'right', 10);
      ctx.fillStyle = C.line;
      ctx.fillRect(px - 5, laneTop - 6, 10, laneH * 4 + 12);
      LAY.forEach(([name, kind, pref], li) => {
        const yc = laneTop + li * laneH + laneH / 2;
        label(name, px + 12, yc - laneH / 2 + 8, kind ? C[kind] : C.dim, 'left', 10);
        if (!kind) {
          ctx.strokeStyle = C.dim; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(x0, yc); ctx.lineTo(x1, yc); ctx.stroke();
          return;
        }
        const f = kind === 'slow' ? 0.35 : kind === 'mid' ? 0.6 : 1.0;
        ctx.strokeStyle = C[kind]; ctx.lineWidth = 1.4;
        ctx.beginPath();
        for (let x = x0; x <= x1; x += 1) {
          const d = phaseAt(x, x0, x1 - x0);
          const env = hot(li, d);
          const yy = yc - (laneH * 0.42) * env * Math.sin(x * f + t * 9);
          if (x === x0) ctx.moveTo(x, yy); else ctx.lineTo(x, yy);
        }
        ctx.stroke();
      });
      if (k === 1) return;
      // the grid, filling up
      const gx = w * 0.58, gw = w - gx - 14, nb = 12;
      const cw = gw / nb;
      const fill = ease(t / 6);
      LAY.forEach((_, li) => {
        for (let j = 0; j < nb; j++) {
          const deg = (j + 0.5) * 30;
          const v = hot(li, deg) * fill;
          const c = jet(0.08 + 0.9 * v);
          ctx.fillStyle = 'rgb(' + c.map(Math.round).join(',') + ')';
          ctx.fillRect(gx + j * cw, laneTop + li * laneH, cw - 1, laneH - 1);
        }
      });
      label('0\u00b0', gx, laneTop + 4 * laneH + 10, C.dim, 'left', 9);
      label('360\u00b0', gx + gw, laneTop + 4 * laneH + 10, C.dim, 'right', 9);
      // drops flying from the lanes into their columns
      for (let q = 0; q < 10; q++) {
        const life = ((t * 0.9 + q * 0.37) % 1.6) / 1.6;
        const li = q % 3;
        const deg = (LAY[li][2] + (q * 23 % 60) - 30 + 360) % 360;
        const sx = x1, sy = laneTop + li * laneH + laneH / 2;
        const ex = gx + (deg / 30) * cw, ey = sy;
        const e = ease(life);
        ctx.globalAlpha = 1 - life;
        ctx.fillStyle = C[LAY[li][1]];
        ctx.beginPath();
        ctx.arc(sx + (ex - sx) * e, sy - Math.sin(e * Math.PI) * 26, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;
      }
      return;
    }
    // 3 and 4: the finished picture(s). rows: [name, colour, phase|null]
    const drawGrid = (gx, gy, gw, gh, rowsIn, caption) => {
      const rows = rowsIn || LAY.map(([n, kind, pref]) => [n, kind ? C[kind] : C.dim, pref]);
      const nb = 24, rh = gh / rows.length, cw = gw / nb;
      rows.forEach(([name, col, pref], li) => {
        for (let j = 0; j < nb; j++) {
          const deg = (j + 0.5) * 30;
          let v = 0.05;
          if (pref != null) {
            const dd = Math.abs((((deg - pref) % 360) + 540) % 360 - 180);
            v = Math.exp(-(dd * dd) / (2 * 45 * 45));
          }
          const pulse = 0.85 + 0.15 * Math.sin(t * 3 + li);
          const c = jet(0.08 + 0.9 * v * pulse);
          ctx.fillStyle = 'rgb(' + c.map(Math.round).join(',') + ')';
          ctx.fillRect(gx + j * cw, gy + li * rh, cw - 0.5, rh - 1);
        }
        if (pref != null) {
          ctx.fillStyle = '#fff';
          for (const d of [pref, pref + 360]) {
            ctx.beginPath();
            ctx.arc(gx + gw * d / 720, gy + li * rh + rh / 2, 3, 0, Math.PI * 2);
            ctx.fill();
          }
        }
        label(name, gx - 6, gy + li * rh + rh / 2, col, 'right', 10);
      });
      label('0\u00b0', gx, gy + gh + 9, C.dim, 'left', 9);
      label('360\u00b0', gx + gw / 2, gy + gh + 9, C.dim, 'center', 9);
      label('720\u00b0', gx + gw, gy + gh + 9, C.dim, 'right', 9);
      if (caption) label(caption, gx + gw / 2, gy - 10, C.text, 'center', 11);
      return rh;
    };
    if (k === 3) {
      const gx = 60, gy = 34, gw = w - 90, gh = 190;
      const rh = drawGrid(gx, gy, gw, gh, null, null);
      // the dots step from one phase to the next going down
      ctx.strokeStyle = 'rgba(255,255,255,.55)'; ctx.lineWidth = 1.5;
      ctx.beginPath();
      LAY.slice(0, 3).forEach(([, , pref], li) => {
        const x = gx + gw * pref / 720, yy = gy + li * rh + rh / 2;
        if (li === 0) ctx.moveTo(x, yy); else ctx.lineTo(x, yy);
      });
      ctx.stroke();
      // the boundary between OML and MML: dashed, drawn in as t runs
      const y = gy + rh;
      const len = gw * ease((t - 1) / 1.5);
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.setLineDash([6, 4]);
      ctx.beginPath(); ctx.moveTo(gx, y); ctx.lineTo(gx + len, y); ctx.stroke();
      ctx.setLineDash([]);
      if (t > 2.5) {
        ctx.globalAlpha = ease((t - 2.5) / 0.8);
        const txt = 'boundary: the hot spot changes phase here';
        ctx.font = '600 11px system-ui, sans-serif';
        const tw = ctx.measureText(txt).width;
        ctx.fillStyle = 'rgba(0,0,0,.72)';
        ctx.fillRect(gx + gw - tw - 12, y - 9, tw + 10, 18);
        label(txt, gx + gw - 7, y, '#fff', 'right', 11);
        ctx.globalAlpha = 1;
      }
      return;
    }
    // 4: rats vs mice
    const half = (w - 90) / 2;
    drawGrid(56, 40, half - 20, 170, [['SLM', C.theta, 350], ['OML', C.slow, 47],
                                      ['MML', C.fast, 168], ['GCL', C.dim, null]],
             'rats: each input its moment');
    const mx = 86 + half;
    const rh = drawGrid(mx, 40, half - 20, 170, [['SLM', C.theta, 350],
                                                 ['OML', C.slow, 175],
                                                 ['MML', C.fast, 185],
                                                 ['GCL', C.dim, null]],
                        'mice: the big jump is the fissure');
    const y = 40 + rh;
    const len = (half - 20) * ease((t - 0.8) / 1.2);
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.setLineDash([6, 4]);
    ctx.beginPath(); ctx.moveTo(mx, y); ctx.lineTo(mx + len, y); ctx.stroke();
    ctx.setLineDash([]);
  }

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && document.getElementById('saExplain')) explainer(false);
  });

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
