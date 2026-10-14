/* ==========================================================================
   jarvisshow.js -- where the reveal's choices go, and who Jarvis is.

   Three destinations -- dentate spikes, the Monolith, IEDs -- built to be
   shown to people, not to be worked in. Each is a live picture and a
   gallery:

   - The live picture is a SIMULATED signal, made here, frame by frame, and
     labelled as simulated on the page. It reads nothing, fetches nothing
     and needs no recording on any drive, so it cannot be slow and cannot
     fail the way a real read can. It is built to look like the real thing
     -- the detector does what the lab's detector does -- but it is not a
     result and never says it is.
   - The gallery is the lab's real figures, prerendered into
     `img/showcase/` (Results/ and the Monolith page, 2026-10-12). An image
     that is missing hides its card; nothing else depends on it.

   And the card about Paul Jarvis, the person the application is named for.

   Every frame is drawn inside a try: if a drawing throws, that picture
   stops and the rest of the page carries on. A demo must not crash.
   ========================================================================== */
(function () {
  'use strict';
  if (typeof document === 'undefined') return;
  const B = (typeof BARRY !== 'undefined') ? BARRY : null;
  const fx = () => (B && B.jarvisfx) || window.JarvisFX || null;
  const sfx = (name, a) => { try { const f = fx(); if (f && f[name]) f[name](a); } catch (e) { /* silence */ } };
  const tok = (n, f) => {
    try {
      if (B && B.token) return B.token(n, f);
      return getComputedStyle(document.documentElement).getPropertyValue(n).trim() || f;
    } catch (e) { return f; }
  };

  function h(tag, cls, text, attrs) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text) n.textContent = text;
    if (attrs) for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }
  const svgIcon = (d) => {
    const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    s.setAttribute('viewBox', '0 0 24 24');
    s.setAttribute('aria-hidden', 'true');
    s.innerHTML = d;
    return s;
  };

  /* ------------------------------------------------------------------------
     What each destination says, and the real figures it shows
     ------------------------------------------------------------------------ */
  const SHOWS = {
    ds: {
      tab: 'Dentate spikes',
      title: 'Analyze dentate spikes',
      lede: 'Dentate spikes are brief, large waves from the dentate gyrus, part of '
        + 'the hippocampus, the brain’s memory centre. Below, a detector catches '
        + 'each one as the recording sweeps past, and builds up what an average spike '
        + 'looks like at every depth along the probe.',
      figs: [
        ['ds-space.webp', 'Dentate spikes, sorted by shape',
         'Every dot is one dentate spike from PTEN m22 s3, placed by how tall it is, '
         + 'how wide it is, and how much fast activity rides on it. Root Canal sorts '
         + 'the spikes into kinds in this space.'],
        ['ds-csd.webp', 'Voltage and current along the probe',
         'PTEN m11 s10: ten seconds on 32 channels. Voltage on the left; on the right, '
         + 'current source density, which shows where current flows in and out at each depth.'],
        ['ds-flat.webp', 'The same spikes, three flat views',
         'Height against width, height against fast activity, and width against fast activity.'],
      ],
    },
    mono: {
      tab: 'Monolith',
      title: 'The Monolith',
      lede: 'Every way of measuring how two brain regions move together, at every '
        + 'frequency from 1 to 55 Hz, compared between Precon1 and Precon4 in each rat '
        + 'and pooled over eight rats. Twelve regions sit on a ring; a line lights up '
        + 'where two of them changed together.',
      link: true,
      figs: [
        ['mono-circuit.webp', 'The circuit',
         'The real Monolith at 15 Hz, offset window, measured by PPC. Red: two regions '
         + 'moved together more on Precon4 than on Precon1. Blue: less.'],
        ['mono-freq.webp', 'Across frequencies',
         'One pair of regions at every frequency from 1 to 55 Hz. The bars count how '
         + 'many region pairs pass at each frequency.'],
        ['mono-pac.webp', 'Who shapes whom',
         'Phase–amplitude coupling: a slow rhythm in one region shaping a fast one '
         + 'in another. Arrows run from the slow rhythm to the fast one.'],
        ['mono-rats.webp', 'Rat by rat',
         'The top result, one line per rat: how much each changed from Precon1 to Precon4. '
         + 'Thicker means a steadier rat.'],
      ],
    },
    ied: {
      tab: 'IEDs',
      title: 'Detect IEDs',
      lede: 'IEDs, interictal epileptiform discharges, are sharp spikes between '
        + 'seizures and one of the signatures of epilepsy. Jarvis finds them with a '
        + 'line-length detector: when the trace suddenly travels much further than '
        + 'usual, something sharp just happened.',
      figs: [
        ['ied-kcnt1.webp', 'One recording, three ways',
         'KCNT1 m1609: ten seconds on 64 channels. The sharp events near 22 s show up in '
         + 'the voltage, the spectrogram and the current source density at once.'],
        ['ied-raster.webp', 'Every channel at once',
         'm34 s5: each channel as a row of colour, then as a line. The tall event near '
         + '6.7 s runs down the whole probe.'],
        ['ied-bursts.webp', 'Bursts in time and frequency',
         'Fifty seconds of three channels. The bright stripes in the spectrogram line up '
         + 'with the bursts in the traces below.'],
        ['ied-scalogram.webp', 'Rhythms, moment by moment',
         'm34 s5: a scalogram, which shows which rhythms are strong at each instant, over '
         + 'the voltage on every channel.'],
        ['ied-panorama.webp', 'A whole recording at a glance',
         'KCNT1 m306: three minutes of one channel, its power spectrum, and which rhythm '
         + 'dominates each second.'],
      ],
    },
  };

  /* ------------------------------------------------------------------------
     Shared canvas plumbing
     ------------------------------------------------------------------------ */
  function randn() {
    let u = 0, v = 0;
    while (!u) u = Math.random();
    while (!v) v = Math.random();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }
  const gauss = (x, m, s) => Math.exp(-0.5 * ((x - m) / s) * ((x - m) / s));
  const expRand = (mean) => -Math.log(1 - Math.random()) * mean;
  function jet(v) {           // v in [-1, 1] -> the lab's own figures' map
    const x = Math.max(0, Math.min(1, (v + 1) / 2));
    const r = Math.max(0, Math.min(1, 1.5 - Math.abs(4 * x - 3)));
    const g = Math.max(0, Math.min(1, 1.5 - Math.abs(4 * x - 2)));
    const b = Math.max(0, Math.min(1, 1.5 - Math.abs(4 * x - 1)));
    return 'rgb(' + (r * 255 | 0) + ',' + (g * 255 | 0) + ',' + (b * 255 | 0) + ')';
  }
  function alpha(col, a) {
    const m = /^#([0-9a-f]{6})/i.exec(String(col).trim());
    if (!m) return col;
    const n = parseInt(m[1], 16);
    return 'rgba(' + (n >> 16) + ',' + (n >> 8 & 255) + ',' + (n & 255) + ',' + a + ')';
  }

  /* A canvas that keeps itself sized to its box and calls `draw` every
     frame while it is on screen. Returns a stop function. Any throw stops
     this canvas and nothing else. */
  function animate(canvas, step) {
    let raf = 0, last = performance.now(), dead = false, W = 0, H = 0;
    const ctx = canvas.getContext('2d');
    function fit() {
      const r = canvas.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = Math.max(1, Math.round(r.width)), hh = Math.max(1, Math.round(r.height));
      if (w !== W || hh !== H) {
        W = w; H = hh;
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(hh * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        return true;
      }
      return false;
    }
    function frame(now) {
      if (dead) return;
      try {
        const resized = fit();
        const dt = Math.min(0.1, (now - last) / 1000);
        last = now;
        if (!document.hidden) step(ctx, W, H, dt, resized);
      } catch (e) {
        dead = true;
        return;
      }
      raf = requestAnimationFrame(frame);
    }
    // The first frame now rather than on the next paint: the picture is
    // never an empty box, even for a moment.
    frame(performance.now());
    return () => { dead = true; cancelAnimationFrame(raf); };
  }

  function label(ctx, text, x, y, col, size, align, weight) {
    ctx.font = (weight || 500) + ' ' + (size || 11) + 'px ' + (tok('--sans', 'system-ui') || 'system-ui');
    ctx.fillStyle = col;
    ctx.textAlign = align || 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, x, y);
  }

  /* ------------------------------------------------------------------------
     Live picture 1: a dentate spike detector on a simulated probe
     ------------------------------------------------------------------------ */
  function dsLive(canvas, stats) {
    const NCH = 14, WIN = 2.4;
    const LAYERS = [[0, 3, 'CA1'], [4, 5, 'fissure'], [6, 8, 'molecular'], [9, 9, 'granule'], [10, 13, 'hilus']];
    // How big a spike is at each depth: up in the hilus, reversed in the
    // molecular layer -- higher for DS1, lower for DS2.
    const prof = [1, 2].map((ty) => {
      const p = [];
      for (let c = 0; c < NCH; c++) {
        p.push(1.0 * gauss(c, 11.6, 1.9) - 0.6 * gauss(c, ty === 1 ? 6.2 : 7.8, 1.15));
      }
      return p;
    });
    const wave = (s) => gauss(s, 0, 0.0075) - 0.16 * gauss(s, 0.03, 0.014);
    const SNIP = 61, HALF = 30;
    const col = { text: tok('--text-3', '#6f8c7d'), accent: tok('--accent', '#FFB81C'),
                  line: tok('--line', '#24382e'), soft: tok('--text-2', '#a9bdb3') };
    let cols = 0, sr = 0, buf = [], head = 0, t = 0, nextEv = 0;
    const noiseS = new Float32Array(NCH);
    let common = 0, theta = 0;
    const live = [];           // events still being drawn into the buffer
    const marks = [];          // detected, for the bands on the traces
    const snips = [];          // hilus waveforms of the last few
    const mean = Array.from({ length: NCH }, () => new Float32Array(SNIP));
    let n = 0, n1 = 0, n2 = 0, simT = 0, lastStats = 0;

    function reset(w) {
      cols = Math.max(60, Math.floor(w));
      sr = cols / WIN;
      buf = Array.from({ length: NCH }, () => new Float32Array(cols));
      head = 0;
      nextEv = t + sr * 0.6;
      // One sweep drawn before anything is shown, so the screen opens on a
      // full probe rather than an empty one -- and nothing it held is
      // counted.
      for (let i = 0; i < cols; i++) step1(true);
      live.length = 0;
      nextEv = t + sr * 0.5;
    }
    function step1(quiet) {
      if (t >= nextEv) {
        const ty = Math.random() < 0.42 ? 1 : 2;
        live.push({ t0: t + 8, ty, amp: 0.8 + Math.random() * 0.6, x: (head + 8) % cols, done: false });
        nextEv = t + sr * (0.28 + expRand(0.75));
      }
      common = 0.96 * common + 0.12 * randn();
      theta += 2 * Math.PI * 7.6 / sr;
      for (let c = 0; c < NCH; c++) {
        noiseS[c] = 0.9 * noiseS[c] + 0.09 * randn();
        let v = noiseS[c] + 0.35 * common
              + (0.28 + 0.22 * gauss(c, 4.5, 2.2)) * Math.sin(theta + (c < 3 ? Math.PI : 0));
        for (const e of live) {
          const s = (t - e.t0) / sr;
          if (s > -0.05 && s < 0.08) v += 2.4 * e.amp * prof[e.ty - 1][c] * wave(s);
        }
        buf[c][head] = v;
      }
      for (const e of live) {
        if (!e.done && t >= e.t0 + 2) {
          e.done = true;
          if (quiet) continue;
          n += 1;
          if (e.ty === 1) n1 += 1; else n2 += 1;
          marks.push({ x: e.x, ty: e.ty, at: simT });
          const sn = new Float32Array(SNIP);
          for (let i = 0; i < SNIP; i++) {
            const s = (i - HALF) / sr;
            for (let c = 0; c < NCH; c++) {
              const v = 2.4 * e.amp * prof[e.ty - 1][c] * wave(s);
              mean[c][i] += (v + 0.02 * randn() - mean[c][i]) / n;
              if (c === 11) sn[i] = v + 0.15 * randn();
            }
          }
          snips.push(sn);
          if (snips.length > 28) snips.shift();
          sfx('pop', e.ty === 2);
        }
      }
      while (live.length && live[0].done && t > live[0].t0 + sr * 0.1) live.shift();
      head = (head + 1) % cols;
      t += 1;
    }

    return animate(canvas, (ctx, W, H, dt, resized) => {
      const TW = Math.floor(W * 0.64);
      if (resized || !cols) reset(TW - 60);
      const steps = Math.min(40, Math.round(dt * sr));
      for (let i = 0; i < steps; i++) step1();
      simT += dt;
      ctx.clearRect(0, 0, W, H);

      // The probe: one trace per channel, swept like a scope.
      const x0 = 60, top = 18, lane = (H - top - 8) / NCH, GAP = 14;
      LAYERS.forEach(([a, b, name], i) => {
        const y1 = top + a * lane, y2 = top + (b + 1) * lane;
        if (i % 2) { ctx.fillStyle = alpha(col.line, 0.35); ctx.fillRect(0, y1, x0 - 6, y2 - y1); }
        label(ctx, name, 6, (y1 + y2) / 2, col.text, 10);
      });
      for (const m of marks) {
        const ahead = (m.x - head + cols) % cols;
        if (ahead < GAP + 2 && simT - m.at > 0.2) m.gone = true;
      }
      for (let i = marks.length - 1; i >= 0; i--) if (marks[i].gone) marks.splice(i, 1);
      for (const m of marks) {
        const a = Math.max(0.12, 0.5 - (simT - m.at) * 0.25);
        ctx.fillStyle = alpha(col.accent, a * 0.35);
        ctx.fillRect(x0 + m.x - 7, top - 4, 14, H - top);
        label(ctx, 'DS' + m.ty, x0 + m.x, top - 9, alpha(col.accent, Math.min(1, a * 2)), 10, 'center', 700);
      }
      ctx.lineWidth = 1.1;
      ctx.lineJoin = 'round';
      for (let c = 0; c < NCH; c++) {
        const y0 = top + (c + 0.5) * lane, k = lane * 0.34;
        ctx.strokeStyle = c >= 9 ? alpha(col.soft, 0.95) : alpha(col.soft, 0.7);
        ctx.beginPath();
        let pen = false;
        for (let x = 0; x < cols; x++) {
          const ahead = (x - head + cols) % cols;
          if (ahead < GAP) { pen = false; continue; }
          const y = y0 - buf[c][x] * k;
          if (pen) ctx.lineTo(x0 + x, y); else { ctx.moveTo(x0 + x, y); pen = true; }
        }
        ctx.stroke();
      }
      // The recording head.
      ctx.strokeStyle = col.accent;
      ctx.lineWidth = 2;
      ctx.shadowColor = col.accent;
      ctx.shadowBlur = 10;
      ctx.beginPath();
      ctx.moveTo(x0 + head, top - 2); ctx.lineTo(x0 + head, H - 6);
      ctx.stroke();
      ctx.shadowBlur = 0;

      // The average spike, from every one caught so far.
      const RX = TW + 22, RW = W - RX - 8, RH = (H - 30) / 2;
      label(ctx, 'Average dentate spike · hilus · n = ' + n, RX, 8, col.soft, 11, 'left', 600);
      let peak = 0.5;
      for (const sn of snips) for (let i = 0; i < SNIP; i++) peak = Math.max(peak, Math.abs(sn[i]));
      const sy = (v) => 22 + RH * 0.62 - (v / peak) * RH * 0.55;
      const sx = (i) => RX + (i / (SNIP - 1)) * RW;
      ctx.lineWidth = 1;
      ctx.strokeStyle = alpha(col.accent, 0.18);
      for (const sn of snips) {
        ctx.beginPath();
        for (let i = 0; i < SNIP; i++) { if (i) ctx.lineTo(sx(i), sy(sn[i])); else ctx.moveTo(sx(i), sy(sn[i])); }
        ctx.stroke();
      }
      if (n) {
        ctx.lineWidth = 2.6;
        ctx.strokeStyle = col.accent;
        ctx.shadowColor = col.accent; ctx.shadowBlur = 8;
        ctx.beginPath();
        for (let i = 0; i < SNIP; i++) { const y = sy(mean[11][i]); if (i) ctx.lineTo(sx(i), y); else ctx.moveTo(sx(i), y); }
        ctx.stroke();
        ctx.shadowBlur = 0;
      }
      // Its current source density: the fingerprint of the spike by depth.
      const CY = 22 + RH + 22;
      label(ctx, 'Where the current flows, by depth', RX, CY - 9, col.soft, 11, 'left', 600);
      if (n) {
        // Smoothed across depth first, as the lab's own CSD is: a second
        // difference of raw channels is mostly the noise between them.
        const sm = mean.map((row, c) => row.map((v, i) =>
          0.25 * mean[Math.max(0, c - 1)][i] + 0.5 * v + 0.25 * mean[Math.min(NCH - 1, c + 1)][i]));
        let mx = 1e-6;
        const csd = [];
        for (let c = 1; c < NCH - 1; c++) {
          const row = new Float32Array(SNIP);
          for (let i = 0; i < SNIP; i++) {
            row[i] = -(sm[c - 1][i] - 2 * sm[c][i] + sm[c + 1][i]);
            mx = Math.max(mx, Math.abs(row[i]));
          }
          csd.push(row);
        }
        const ch = (H - CY - 6) / csd.length, cw = RW / SNIP;
        for (let r = 0; r < csd.length; r++) {
          for (let i = 0; i < SNIP; i++) {
            ctx.fillStyle = jet(csd[r][i] / mx);
            ctx.fillRect(RX + i * cw, CY + r * ch, cw + 0.6, ch + 0.6);
          }
        }
      } else {
        label(ctx, 'waiting for the first spike…', RX, CY + 30, col.text, 11);
      }

      if (simT - lastStats > 0.25) {
        lastStats = simT;
        stats([['Dentate spikes found', String(n)],
               ['DS1 · DS2', n1 + ' · ' + n2],
               ['Rate', (n / Math.max(1, simT)).toFixed(2) + ' per second'],
               ['Probe', NCH + ' channels, ' + WIN + ' s on screen']]);
      }
    });
  }

  /* ------------------------------------------------------------------------
     Live picture 2: a line-length IED detector on a simulated recording
     ------------------------------------------------------------------------ */
  function iedLive(canvas, stats) {
    const NCH = 6, WIN = 5, FOCUS = 2;
    const col = { text: tok('--text-3', '#6f8c7d'), accent: tok('--accent', '#FFB81C'),
                  hit: tok('--err', '#e5534b'), soft: tok('--text-2', '#a9bdb3'),
                  line: tok('--line', '#24382e') };
    let cols = 0, sr = 0, buf = [], ll = null, thrBuf = null, head = 0, t = 0, nextEv = 0;
    const ns = new Float32Array(NCH);
    let alphaPh = 0, prev = 0, sum = 0, base = 0.08, lastHit = -1e9;
    let ring = null, ri = 0;
    const live = [], marks = [], hits = [];
    let n = 0, simT = 0, lastStats = 0;
    const perCh = new Array(NCH).fill(0);

    function reset(w) {
      cols = Math.max(60, Math.floor(w));
      sr = cols / WIN;
      buf = Array.from({ length: NCH }, () => new Float32Array(cols));
      ll = new Float32Array(cols);
      thrBuf = new Float32Array(cols);
      ring = new Float32Array(Math.max(4, Math.round(sr * 0.04)));
      ri = 0; sum = 0; head = 0;
      nextEv = t + sr * 0.8;
      for (let i = 0; i < cols; i++) step1(true);
      live.length = 0;
      // Refractory from here, but not a detection here.
      lastHit = t - 1;
      nextEv = t + sr * 0.6;
    }
    // A spike and the slow wave after it, arriving a little later on the
    // channels further from where it starts.
    const shape = (s) => 1.0 * gauss(s, 0, 0.011) - 0.34 * gauss(s, 0.085, 0.05);
    function step1(quiet) {
      if (t >= nextEv) {
        const amp = 3.2 + Math.random() * 2.2;
        live.push({ t0: t + 6, amp });
        if (Math.random() < 0.25) live.push({ t0: t + 6 + Math.round(sr * (0.18 + Math.random() * 0.12)), amp: amp * 0.8 });
        nextEv = t + sr * (0.7 + expRand(1.1));
      }
      alphaPh += 2 * Math.PI * 9 / sr;
      for (let c = 0; c < NCH; c++) {
        ns[c] = 0.93 * ns[c] + 0.11 * randn();
        let v = ns[c] + 0.12 * Math.sin(alphaPh + c * 0.4);
        for (const e of live) {
          const d = Math.abs(c - FOCUS) * 0.005;
          const s = (t - e.t0) / sr - d;
          if (s > -0.05 && s < 0.25) v += e.amp * (0.35 + 0.65 * gauss(c, FOCUS, 1.7)) * shape(s);
        }
        buf[c][head] = v;
      }
      // Line length on the channel nearest the start: how far the trace
      // travelled over the last 40 ms.
      const x = buf[FOCUS][head];
      const step = Math.abs(x - prev);
      prev = x;
      sum += step - ring[ri];
      ring[ri] = step;
      ri = (ri + 1) % ring.length;
      const L = sum / ring.length;
      const thr = base * 3.4;
      if (L < thr) base = 0.996 * base + 0.004 * L;
      ll[head] = L;
      thrBuf[head] = thr;
      if (L > thr && t - lastHit > sr * 0.22) {
        lastHit = t;
      }
      if (!quiet && lastHit === t) {
        n += 1;
        marks.push({ x: head, at: simT });
        const chans = [];
        for (let c = 0; c < NCH; c++) if (gauss(c, FOCUS, 1.7) > 0.3) { chans.push(c); perCh[c] += 1; }
        hits.push({ at: simT, chans });
        sfx('zap');
      }
      while (live.length && t > live[0].t0 + sr * 0.4) live.shift();
      head = (head + 1) % cols;
      t += 1;
    }

    return animate(canvas, (ctx, W, H, dt, resized) => {
      const x0 = 46, TW = W - x0 - 10;
      if (resized || !cols) reset(TW);
      const steps = Math.min(40, Math.round(dt * sr));
      for (let i = 0; i < steps; i++) step1();
      simT += dt;
      ctx.clearRect(0, 0, W, H);
      const GAP = 14, top = 10, TH = H * 0.56, lane = (TH - top) / NCH;
      const LLy = TH + 22, LLh = H * 0.17, RY = LLy + LLh + 26, RHh = H - RY - 4;

      for (let i = marks.length - 1; i >= 0; i--) {
        const ahead = (marks[i].x - head + cols) % cols;
        if (ahead < GAP + 2 && simT - marks[i].at > 0.2) marks.splice(i, 1);
      }
      for (const m of marks) {
        const a = Math.max(0.15, 0.6 - (simT - m.at) * 0.2);
        ctx.fillStyle = alpha(col.hit, a * 0.3);
        ctx.fillRect(x0 + m.x - 9, top - 4, 18, LLy + LLh - top + 4);
        label(ctx, 'IED', x0 + m.x + 12, top + 4, alpha(col.hit, Math.min(1, a * 1.8)), 10, 'left', 700);
      }
      ctx.lineWidth = 1.2;
      for (let c = 0; c < NCH; c++) {
        const y0 = top + (c + 0.5) * lane, k = lane * 0.22;
        label(ctx, 'ch ' + (c + 1), 4, y0, col.text, 10);
        ctx.strokeStyle = c === FOCUS ? alpha(col.soft, 1) : alpha(col.soft, 0.72);
        ctx.beginPath();
        let pen = false;
        for (let x = 0; x < cols; x++) {
          if ((x - head + cols) % cols < GAP) { pen = false; continue; }
          const y = y0 - buf[c][x] * k;
          if (pen) ctx.lineTo(x0 + x, y); else { ctx.moveTo(x0 + x, y); pen = true; }
        }
        ctx.stroke();
      }
      // The feature and its threshold.
      label(ctx, 'Line length · ch ' + (FOCUS + 1), x0, LLy - 10, col.soft, 11, 'left', 600);
      let top2 = 0.3;
      for (let x = 0; x < cols; x++) top2 = Math.max(top2, ll[x], thrBuf[x] * 1.4);
      const ly = (v) => LLy + LLh - (v / top2) * LLh;
      ctx.fillStyle = alpha(col.accent, 0.28);
      ctx.strokeStyle = col.accent;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      let pen = false, startX = 0;
      for (let x = 0; x <= cols; x++) {
        const gap = x === cols || (x - head + cols) % cols < GAP;
        if (gap) {
          if (pen) { ctx.lineTo(x0 + x - 1, LLy + LLh); ctx.lineTo(x0 + startX, LLy + LLh); ctx.closePath(); }
          pen = false;
          continue;
        }
        if (!pen) { ctx.moveTo(x0 + x, LLy + LLh); startX = x; pen = true; }
        ctx.lineTo(x0 + x, ly(ll[x]));
      }
      ctx.fill();
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = col.hit;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      pen = false;
      for (let x = 0; x < cols; x++) {
        if ((x - head + cols) % cols < GAP) { pen = false; continue; }
        const y = ly(thrBuf[x]);
        if (pen) ctx.lineTo(x0 + x, y); else { ctx.moveTo(x0 + x, y); pen = true; }
      }
      ctx.stroke();
      ctx.setLineDash([]);
      label(ctx, 'threshold', x0 + TW - 2, ly(base * 3.4) - 8, col.hit, 10, 'right');
      // The head.
      ctx.strokeStyle = col.accent;
      ctx.lineWidth = 2;
      ctx.shadowColor = col.accent; ctx.shadowBlur = 10;
      ctx.beginPath(); ctx.moveTo(x0 + head, top - 2); ctx.lineTo(x0 + head, LLy + LLh); ctx.stroke();
      ctx.shadowBlur = 0;
      // Every detection of the last minute, by channel.
      label(ctx, 'Detections, the last 60 s', x0, RY - 10, col.soft, 11, 'left', 600);
      const rl = RHh / NCH;
      ctx.strokeStyle = alpha(col.line, 0.9);
      ctx.lineWidth = 1;
      ctx.strokeRect(x0, RY, TW, RHh);
      for (let i = hits.length - 1; i >= 0; i--) {
        const age = simT - hits[i].at;
        if (age > 60) { hits.splice(i, 1); continue; }
        const x = x0 + TW - (age / 60) * TW;
        for (const c of hits[i].chans) {
          ctx.fillStyle = age < 0.6 ? col.hit : alpha(col.hit, 0.75);
          ctx.beginPath();
          ctx.arc(x, RY + (c + 0.5) * rl, age < 0.6 ? 4 : 2.6, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      if (simT - lastStats > 0.25) {
        lastStats = simT;
        let busiest = 0;
        perCh.forEach((v, i) => { if (v > perCh[busiest]) busiest = i; });
        stats([['IEDs detected', String(n)],
               ['Per minute', simT < 15 ? 'counting…' : (n / simT * 60).toFixed(0)],
               ['Threshold', '3.4 × the usual line length'],
               ['Busiest channel', n ? 'ch ' + (busiest + 1) : '—']]);
      }
    });
  }

  /* ------------------------------------------------------------------------
     Live picture 3: a Monolith circuit, swept from 1 to 55 Hz
     ------------------------------------------------------------------------ */
  function monoLive(canvas, stats) {
    // The real page's ring, in its order: left side up the left, right
    // side down the right, ACC at the top.
    const REG = ['Left ACC', 'Right ACC', 'Right OFC', 'Right DHC', 'Right RSC', 'Right PER',
                 'Right POR-SUB', 'Left POR-SUB', 'Left PER', 'Left RSC', 'Left DHC', 'Left OFC'];
    const N = REG.length;
    const ang = REG.map((_, i) => (-105 + i * 30) * Math.PI / 180);
    const MEASURES = ['Coherence', 'PPC', 'wPLI', 'Envelope correlation', 'Imaginary coherence'];
    // Stronger on Precon4 red, weaker blue: the Monolith's own legend.
    const RED = '#d6453d', BLUE = '#2f6fd8';
    const col = { text: tok('--text-2', '#a9bdb3'), dim: tok('--text-3', '#6f8c7d'),
                  line: tok('--line', '#24382e'), accent: tok('--accent', '#FFB81C') };
    const SWEEP = 15;
    let mi = 0, phase = 0, model = null, best = null;
    function makeModel() {
      const pairs = [];
      for (let i = 0; i < N; i++) {
        for (let j = i + 1; j < N; j++) {
          const bumps = [];
          const k = Math.random() < 0.35 ? 2 : (Math.random() < 0.7 ? 1 : 0);
          for (let b = 0; b < k; b++) {
            bumps.push([2 + Math.random() * 50, 2.5 + Math.random() * 6, randn() * 0.9]);
          }
          pairs.push({ i, j, bumps });
        }
      }
      const nodes = REG.map(() => [[2 + Math.random() * 50, 4 + Math.random() * 8, randn() * 0.8]]);
      return { pairs, nodes };
    }
    const val = (bumps, f) => bumps.reduce((s, b) => s + b[2] * gauss(f, b[0], b[1]), 0);
    model = makeModel();

    return animate(canvas, (ctx, W, H, dt) => {
      phase += dt / SWEEP;
      if (phase >= 1) { phase = 0; mi = (mi + 1) % MEASURES.length; model = makeModel(); best = null; }
      const f = 1 + 54 * Math.min(1, phase / 0.92);
      ctx.clearRect(0, 0, W, H);
      const cx = W / 2, cy = (H - 44) / 2 + 6, R = Math.min(cx - 120, cy - 26);
      const pos = ang.map((a) => [cx + R * Math.cos(a), cy + R * Math.sin(a)]);
      ctx.strokeStyle = alpha(col.line, 0.9);
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
      let changed = 0, top = null;
      const vis = [];
      for (const p of model.pairs) {
        const v = val(p.bumps, f);
        if (Math.abs(v) < 0.42) continue;
        changed += 1;
        vis.push([p, v]);
        if (!top || Math.abs(v) > Math.abs(top[1])) top = [p, v];
      }
      vis.sort((a, b) => Math.abs(a[1]) - Math.abs(b[1]));
      for (const [p, v] of vis) {
        const [x1, y1] = pos[p.i], [x2, y2] = pos[p.j];
        const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
        const qx = mx + (cx - mx) * 0.55, qy = my + (cy - my) * 0.55;
        const a = Math.min(1, (Math.abs(v) - 0.42) * 1.6 + 0.25);
        ctx.strokeStyle = alpha(v > 0 ? RED : BLUE, a);
        ctx.lineWidth = 1.2 + 4.5 * Math.min(1, Math.abs(v));
        ctx.shadowColor = v > 0 ? RED : BLUE;
        ctx.shadowBlur = top && p === top[0] ? 16 : 0;
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.quadraticCurveTo(qx, qy, x2, y2); ctx.stroke();
      }
      ctx.shadowBlur = 0;
      for (let i = 0; i < N; i++) {
        const v = val(model.nodes[i], f);
        const [x, y] = pos[i];
        ctx.fillStyle = Math.abs(v) < 0.2 ? tok('--bg-3', '#15291f')
                      : alpha(v > 0 ? RED : BLUE, Math.min(1, 0.35 + Math.abs(v)));
        ctx.strokeStyle = col.text;
        ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        const right = Math.cos(ang[i]) >= -0.01;
        label(ctx, REG[i], x + (right ? 14 : -14), y, col.text, 11, right ? 'left' : 'right');
      }
      let topText = '—';
      if (top && Math.abs(top[1]) > 0.9) {
        const [p, v] = top;
        const key = p.i + '-' + p.j;
        if (!best || best.key !== key) { best = { key, at: phase }; sfx('tick', 3); }
        topText = REG[p.i] + ' – ' + REG[p.j] + ', ' + (v > 0 ? 'stronger' : 'weaker');
      }
      // The frequency, as the slider on the real page has it.
      const by = H - 26, bx0 = 30, bx1 = W - 30;
      ctx.strokeStyle = alpha(col.dim, 0.8);
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(bx0, by); ctx.lineTo(bx1, by); ctx.stroke();
      [1, 12, 25, 40, 55].forEach((hz) => {
        const x = bx0 + (hz - 1) / 54 * (bx1 - bx0);
        label(ctx, hz + ' Hz', x, by + 14, col.dim, 10, 'center');
      });
      const tx = bx0 + (f - 1) / 54 * (bx1 - bx0);
      ctx.fillStyle = col.accent;
      ctx.shadowColor = col.accent; ctx.shadowBlur = 10;
      ctx.beginPath(); ctx.arc(tx, by, 7, 0, Math.PI * 2); ctx.fill();
      ctx.shadowBlur = 0;
      label(ctx, Math.round(f) + ' Hz', tx, by - 15, col.accent, 12, 'center', 700);
      stats([['Frequency', Math.round(f) + ' Hz'],
             ['Measure', MEASURES[mi]],
             ['Region pairs changed', changed + ' of ' + (N * (N - 1) / 2)],
             ['Top result', topText],
             ['Compared', 'Precon4 − Precon1']]);
    });
  }

  const LIVE = { ds: dsLive, mono: monoLive, ied: iedLive };

  /* ------------------------------------------------------------------------
     The showcase itself
     ------------------------------------------------------------------------ */
  let show = null;

  function close() {
    if (!show) return;
    const s = show;
    show = null;
    try { if (s.stop) s.stop(); } catch (e) { /* already stopped */ }
    document.removeEventListener('keydown', s.keys, true);
    s.box.classList.add('leaving');
    setTimeout(() => { if (s.box.parentNode) s.box.parentNode.removeChild(s.box); }, 260);
  }

  function render(key) {
    const s = show;
    if (!s) return;
    const spec = SHOWS[key] || SHOWS.ds;
    s.key = key;
    try { if (s.stop) s.stop(); } catch (e) { /* fine */ }
    s.stop = null;
    s.tabs.forEach((b) => b.classList.toggle('on', b.dataset.k === key));
    const body = s.body;
    body.textContent = '';
    body.scrollTop = 0;

    const hero = h('section', 'jx-hero');
    hero.append(h('h2', null, spec.title), h('p', 'jx-lede', spec.lede));
    const grid = h('div', 'jx-live');
    const cv = h('canvas', 'jx-canvas');
    const aside = h('aside', 'jx-stats');
    const statRows = h('dl');
    aside.append(statRows, h('div', 'jx-sim', 'Simulated signal, made live in your browser. The real figures are below.'));
    grid.append(cv, aside);
    hero.append(grid);
    body.append(hero);

    let lastHTML = '';
    const stats = (rows) => {
      const html = rows.map((r) => r[0] + '\u0000' + r[1]).join('\u0001');
      if (html === lastHTML) return;
      lastHTML = html;
      statRows.textContent = '';
      rows.forEach(([k, v]) => { statRows.append(h('dt', null, k), h('dd', null, v)); });
    };
    try { s.stop = LIVE[key](cv, stats); } catch (e) { s.stop = null; }

    const gal = h('section', 'jx-gallery');
    gal.append(h('h3', null, 'From the lab’s own recordings'));
    const cards = h('div', 'jx-cards');
    spec.figs.forEach(([file, title, text]) => {
      const card = h('button', 'jx-fig', null, { type: 'button' });
      const img = h('img', null, null, { src: 'img/showcase/' + file, alt: title, loading: 'lazy' });
      img.addEventListener('error', () => { card.style.display = 'none'; });
      card.append(img, h('strong', null, title), h('span', null, text));
      card.addEventListener('click', () => { sfx('select'); lightbox('img/showcase/' + file, title, text); });
      card.addEventListener('pointerenter', () => sfx('hover'));
      cards.append(card);
    });
    gal.append(cards);
    if (spec.link) {
      const a = h('button', 'jx-ext', 'Open the full Monolith page ↗', { type: 'button' });
      a.title = 'The real, interactive page, in a new tab. It takes a few seconds to load.';
      a.addEventListener('click', () => { try { window.open('monolith.html', '_blank'); } catch (e) { /* blocked */ } });
      gal.append(a);
    }
    body.append(gal);
  }

  /* Open a destination. `opts.back` returns to the reveal's choices,
     `opts.home` leaves for the application. */
  function open(key, opts) {
    opts = opts || {};
    if (show) { render(key); return; }
    const box = h('div', 'jx-show', null, { role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Jarvis' });
    box.id = 'jarvisShow';
    const head = h('header', 'jx-head');
    const mark = h('span', 'jx-mark');
    try { if (B && B.jarvis) mark.innerHTML = B.jarvis.markSvg(B.jarvis.colours(), 'mid'); } catch (e) { /* no mark */ }
    const name = h('span', 'jx-name', 'Jarvis');
    const tabs = Object.keys(SHOWS).map((k) => {
      const b = h('button', 'jx-tab', SHOWS[k].tab, { type: 'button' });
      b.dataset.k = k;
      b.addEventListener('click', () => { if (show && show.key !== k) { sfx('select'); render(k); } });
      b.addEventListener('pointerenter', () => sfx('hover'));
      return b;
    });
    const tabBox = h('nav', 'jx-tabs');
    tabs.forEach((b) => tabBox.append(b));
    const who = h('button', 'jx-who', 'Who is Jarvis?', { type: 'button' });
    who.addEventListener('click', () => about());
    const snd = soundButton('jx-snd');
    const back = h('button', 'jx-btn ghost', '← Back', { type: 'button' });
    back.addEventListener('click', () => { sfx('whoosh', 0.4); close(); if (opts.back) opts.back(); });
    const home = h('button', 'jx-btn', 'Go to the workbench', { type: 'button' });
    home.addEventListener('click', () => { close(); if (opts.home) opts.home(); });
    head.append(mark, name, tabBox, h('span', 'jx-spacer'), who, snd, back, home);
    const body = h('main', 'jx-body');
    box.append(head, body);
    document.body.appendChild(box);
    const keys = (e) => {
      if (document.getElementById('jarvisAbout') || document.getElementById('jarvisLight')) return;
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); back.click(); }
    };
    document.addEventListener('keydown', keys, true);
    show = { box, body, tabs, keys, key: null, stop: null };
    requestAnimationFrame(() => box.classList.add('in'));
    render(key);
  }

  function soundButton(cls) {
    const b = h('button', cls, null, { type: 'button' });
    const paint = () => {
      const f = fx();
      const off = !f || f.muted;
      b.textContent = off ? 'Sound off' : 'Sound on';
      b.classList.toggle('off', off);
      b.setAttribute('aria-pressed', String(!off));
    };
    b.addEventListener('click', () => {
      const f = fx();
      if (f) { f.setMuted(!f.muted); if (!f.muted) f.select(); }
      paint();
    });
    paint();
    return b;
  }

  /* A figure, as big as the window allows. */
  function lightbox(src, title, text) {
    const old = document.getElementById('jarvisLight');
    if (old) old.remove();
    const box = h('div', 'jx-light', null, { role: 'dialog', 'aria-modal': 'true', 'aria-label': title });
    box.id = 'jarvisLight';
    const img = h('img', null, null, { src, alt: title });
    const cap = h('div', 'jx-light-cap');
    cap.append(h('strong', null, title), h('span', null, text));
    box.append(img, cap);
    const shut = () => { document.removeEventListener('keydown', esc, true); box.remove(); };
    const esc = (e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); shut(); } };
    box.addEventListener('click', shut);
    document.addEventListener('keydown', esc, true);
    document.body.appendChild(box);
  }

  /* ------------------------------------------------------------------------
     Who is Jarvis?
     ------------------------------------------------------------------------ */
  const MEMORIAL = 'https://go.uvm.edu/pjarvis';
  function about() {
    if (document.getElementById('jarvisAbout')) return;
    sfx('bell');
    const back = h('div', 'jx-about-back');
    back.id = 'jarvisAbout';
    const card = h('section', 'jx-about', null, { role: 'dialog', 'aria-modal': 'true',
                                                    'aria-labelledby': 'jarvisAboutTitle' });
    const photo = h('figure', 'jx-photo');
    const img = h('img', null, null, { src: 'img/showcase/paul-jarvis.jpg', alt: 'Dr. Paul Jarvis' });
    img.addEventListener('error', () => { photo.style.display = 'none'; });
    photo.append(img);
    const text = h('div', 'jx-about-text');
    const title = h('h2', null, 'Who is Jarvis?');
    title.id = 'jarvisAboutTitle';
    text.append(
      h('p', 'jx-about-kicker', 'In memory of'),
      h('p', 'jx-about-name', 'Dr. Paul Jarvis'),
      h('p', 'jx-about-years', '1987 – 2021'),
      title,
      h('p', null, 'This workbench is named for Paul. He was from Barton, Vermont, studied '
        + 'biology and mathematics at Saint Michael’s College, and earned his medical '
        + 'degree here at UVM’s Larner College of Medicine in 2014.'),
      h('p', null, 'He went on to train as a neurologist, and was in his second year of '
        + 'residency in New York when he died suddenly in January 2021, at 33.'),
      h('p', null, 'He was a runner and an Eagle Scout, he kept up with his friends over '
        + 'online games, and most of all he loved being with his family.'),
      h('p', null, 'Everything Jarvis does is a way of listening to the brain’s '
        + 'electrical life — the field Paul set out to care for.'));
    const gift = h('a', 'jx-gift', null, { href: MEMORIAL, target: '_blank', rel: 'noopener' });
    gift.append(h('span', null, 'His family asked that gifts in his memory support '
      + 'epilepsy research at the Larner College of Medicine.'),
      h('strong', null, 'go.uvm.edu/pjarvis ↗'));
    text.append(gift);
    const shutBtn = h('button', 'jx-btn ghost jx-about-close', 'Close', { type: 'button' });
    text.append(shutBtn);
    card.append(photo, text);
    back.append(card);
    const shut = () => { document.removeEventListener('keydown', esc, true); back.classList.add('leaving');
                         setTimeout(() => back.remove(), 240); };
    const esc = (e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); shut(); } };
    shutBtn.addEventListener('click', shut);
    back.addEventListener('click', (e) => { if (e.target === back) shut(); });
    document.addEventListener('keydown', esc, true);
    document.body.appendChild(back);
    requestAnimationFrame(() => back.classList.add('in'));
    try { shutBtn.focus({ preventScroll: true }); } catch (e) { /* fine */ }
  }

  const api = { open, close, about, isOpen: () => !!show, SHOWS, soundButton, icon: svgIcon };
  if (B) B.jarvisshow = api; else window.JarvisShow = api;
})();
