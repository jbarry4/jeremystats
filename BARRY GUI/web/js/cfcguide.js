/* ==========================================================================
   cfcguide.js -- what the band axis and the comodulogram are actually doing.

   Opened by the little (i) beside the line the band-power panel prints about
   its own bandwidth, and from CFCScope. Twelve chapters, from "a recording is
   a voltage over time" to "here is what you may and may not claim".

   Every chapter computes. There are no pictures in this file: one synthetic
   recording is built from the sliders at the top and carried all the way
   through -- spectrum, filter, envelope, phase, band raster, comodulogram,
   surrogates -- so a reader who moves the coupling slider in chapter 7 sees
   chapter 9's map change for the same reason. A guide made of screenshots
   cannot be interrogated, and every number in here is one the reader can
   push on.

   The arithmetic is the real arithmetic, with one deliberate substitution:
   bands here are cut in the frequency domain with a raised cosine of width
   `f / cycles`, where the panel uses eegfilt's FIR of `3 * fix(fs / f1)`
   taps. Both say the same thing -- a filter that watches for N cycles cannot
   resolve better than f/N -- and the frequency-domain version puts that
   division on screen where it can be seen. Where the exact FIR numbers
   matter, chapter 6 prints the ones measured off the real filter.
   ========================================================================== */
'use strict';

BARRY.cfcGuide = (function () {
  /* ==================================================================
     The recording everything else is about
     ================================================================== */
  /* 13.6 s at 600 Hz. Both numbers are chosen, not idle: 600 Hz leaves room
     for a 160 Hz amplitude band with its skirts, and 13.6 s is over the 40
     cycles of 4 Hz that chapter 10 says a modulation index needs -- so the
     guide is not quietly demonstrating its own warning. */
  const FS = 600;
  const N = 8192;

  const sig = {
    ftheta: 8,        // Hz, the slow rhythm
    drift: 0,         // Hz, how far it slides across the window
    fgamma: 80,       // Hz, the fast rhythm
    coupling: 0.7,    // 0 = none, 1 = the fast rhythm switches fully off
    noise: 0.35,      // relative to the theta amplitude
    cycles: 3,        // filter length, in cycles of the band's low edge
  };

  let chapter = 0;
  let host = null;          // the modal body, while it is open
  const cache = {};         // signal and spectra, invalidated by any slider

  /* ---------------- a deterministic noise source ----------------
     Seeded, so moving a slider and moving it back gives the same picture
     back. `Math.random` made every redraw a different recording and made it
     impossible to see what a slider had actually done. */
  function noiseAt(i) {
    let x = (i * 1103515245 + 12345) & 0x7fffffff;
    x ^= x >> 13; x = (x * 1274126177) & 0x7fffffff; x ^= x >> 16;
    return (x / 0x3fffffff) - 1;      // about -1 .. 1
  }

  function build() {
    if (cache.x) return cache;
    const x = new Float64Array(N);
    const theta = new Float64Array(N);
    const env = new Float64Array(N);
    const phase = new Float64Array(N);

    /* The slow rhythm's phase is integrated rather than computed from t, so
       the drifting case stays continuous. Writing sin(2*pi*f(t)*t) instead
       is the classic chirp mistake: it doubles the sweep and puts a jump
       wherever f changes. */
    let ph = -Math.PI / 2;
    for (let i = 0; i < N; i++) {
      const frac = i / (N - 1);
      const f = sig.ftheta + sig.drift * frac;
      ph += 2 * Math.PI * f / FS;
      phase[i] = ph;
      theta[i] = Math.sin(ph);

      /* Phase-amplitude coupling, built the way it is defined: the fast
         rhythm's ENVELOPE is a function of the slow rhythm's PHASE. At
         coupling 0 the envelope is flat and the two are strangers; at 1 the
         fast rhythm is silent for half of every slow cycle. */
      const m = sig.coupling;
      const shape = (1 - Math.cos(ph)) / 2;         // 0 at the trough
      env[i] = (1 - m) + m * shape;
      x[i] = theta[i]
           + 0.35 * env[i] * Math.sin(2 * Math.PI * sig.fgamma * i / FS)
           + sig.noise * noiseAt(i);
    }
    cache.x = x;
    cache.theta = theta;
    cache.env = env;
    cache.phase = phase;
    cache.spec = fftOf(x);
    cache.bands = {};
    return cache;
  }

  function invalidate() {
    cache.x = null;
    cache.spec = null;
    cache.bands = null;
    cache.comod = null;
  }

  /* ==================================================================
     Arithmetic
     ================================================================== */
  /* Iterative radix-2. Written out rather than pulled in because the guide
     is about what the numbers do, and a dependency that cannot be read is a
     worse teacher than twenty lines. */
  function fft(re, im, inverse) {
    const n = re.length;
    for (let i = 1, j = 0; i < n; i++) {
      let bit = n >> 1;
      for (; j & bit; bit >>= 1) j ^= bit;
      j ^= bit;
      if (i < j) {
        let t = re[i]; re[i] = re[j]; re[j] = t;
        t = im[i]; im[i] = im[j]; im[j] = t;
      }
    }
    for (let len = 2; len <= n; len <<= 1) {
      const ang = (inverse ? 2 : -2) * Math.PI / len;
      const wr = Math.cos(ang), wi = Math.sin(ang);
      for (let i = 0; i < n; i += len) {
        let cr = 1, ci = 0;
        for (let k = 0; k < len / 2; k++) {
          const ur = re[i + k], ui = im[i + k];
          const vr = re[i + k + len / 2] * cr - im[i + k + len / 2] * ci;
          const vi = re[i + k + len / 2] * ci + im[i + k + len / 2] * cr;
          re[i + k] = ur + vr; im[i + k] = ui + vi;
          re[i + k + len / 2] = ur - vr; im[i + k + len / 2] = ui - vi;
          const nr = cr * wr - ci * wi;
          ci = cr * wi + ci * wr; cr = nr;
        }
      }
    }
    if (inverse) for (let i = 0; i < n; i++) { re[i] /= n; im[i] /= n; }
  }

  function fftOf(x) {
    const re = Float64Array.from(x), im = new Float64Array(x.length);
    fft(re, im, false);
    return { re, im };
  }

  /* The band, and the analytic signal of it, in one step.

     Two things happen here and both are worth naming. The mask keeps a band
     of width `f / cycles` -- that division IS the bandwidth story. And only
     the positive frequencies are kept, doubled, which is the Hilbert
     transform: what comes back is complex, its magnitude is the envelope and
     its argument is the phase. Filtering and "getting the phase" are not two
     operations here; they never were. */
  function bandOf(f, cycles) {
    const key = f.toFixed(3) + '/' + cycles;
    const b = build();
    if (b.bands[key]) return b.bands[key];

    const w = Math.max(f / cycles, 0.25);
    const lo = Math.max(f - w / 2, 0.05), hi = f + w / 2;
    const taper = w / 2;                    // raised cosine on each side
    const re = new Float64Array(N), im = new Float64Array(N);
    const df = FS / N;
    for (let k = 1; k < N / 2; k++) {
      const fk = k * df;
      let g = 0;
      if (fk >= lo && fk <= hi) g = 1;
      else if (fk > lo - taper && fk < lo) g = 0.5 * (1 - Math.cos(
        Math.PI * (fk - (lo - taper)) / taper));
      else if (fk > hi && fk < hi + taper) g = 0.5 * (1 + Math.cos(
        Math.PI * (fk - hi) / taper));
      if (!g) continue;
      re[k] = 2 * g * b.spec.re[k];
      im[k] = 2 * g * b.spec.im[k];
    }
    fft(re, im, true);

    const amp = new Float64Array(N), pha = new Float64Array(N);
    for (let i = 0; i < N; i++) {
      amp[i] = Math.hypot(re[i], im[i]);
      pha[i] = Math.atan2(im[i], re[i]);
    }
    const got = { f, w, amp, pha, wave: re };
    b.bands[key] = got;
    return got;
  }

  const NBINS = 18;

  /* Tort's modulation index, which is the one the pipeline computes.

     Bin the fast rhythm's amplitude by the slow rhythm's phase, normalise
     the bins so they sum to one, and ask how far that is from flat --
     Kullback-Leibler divergence against the uniform distribution, divided by
     log(18) so a perfectly concentrated one comes out at 1.

     Flat means "the fast rhythm is the same size whatever the slow rhythm is
     doing", which is exactly no coupling. */
  function histogram(pha, amp, skip) {
    const sum = new Float64Array(NBINS), n = new Float64Array(NBINS);
    const edge = (2 * Math.PI) / NBINS;
    const s = skip || 0;
    for (let i = s; i < N - s; i++) {
      let b = Math.floor((pha[i] + Math.PI) / edge);
      if (b < 0) b = 0; else if (b >= NBINS) b = NBINS - 1;
      sum[b] += amp[i]; n[b] += 1;
    }
    const mean = new Float64Array(NBINS);
    for (let b = 0; b < NBINS; b++) mean[b] = n[b] ? sum[b] / n[b] : 0;
    return mean;
  }

  function miOf(mean) {
    let tot = 0;
    for (let b = 0; b < NBINS; b++) tot += mean[b];
    if (!(tot > 0)) return 0;
    let h = 0;
    for (let b = 0; b < NBINS; b++) {
      const p = mean[b] / tot;
      if (p > 0) h -= p * Math.log(p);
    }
    return (Math.log(NBINS) - h) / Math.log(NBINS);
  }

  /* The edge the filter itself ruins. `filtfilt` runs the thing both ways,
     so the first and last filter-length of every band is ringing rather
     than signal -- and a modulation index that includes it is measuring the
     filter. Dropped here as the panels drop it. */
  const skipFor = (f) => Math.min(Math.round(FS * sig.cycles / Math.max(f, 1)),
                                  Math.floor(N / 4));

  function mi(slowF, fastF) {
    const s = bandOf(slowF, sig.cycles);
    const fst = bandOf(fastF, sig.cycles);
    return miOf(histogram(s.pha, fst.amp, skipFor(slowF)));
  }

  /* ==================================================================
     Drawing
     ================================================================== */
  const tok = (n, fb) => BARRY.token(n, fb);

  function surface(w, h, cls) {
    const cv = el('canvas', { class: 'cfcg-cv' + (cls ? ' ' + cls : '') });
    cv.style.width = '100%';
    cv.style.height = h + 'px';
    cv._paint = null;
    return cv;
  }

  function ctxOf(cv, hFallback) {
    const dpr = window.devicePixelRatio || 1;
    const r = cv.getBoundingClientRect();
    const w = Math.max(r.width || 640, 240);
    const h = Math.max(r.height || hFallback || 160, 80);
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    return { g, w, h };
  }

  /* A line plot with room for labels, used by most of the chapters. */
  function plotFrame(g, w, h, opts) {
    const o = opts || {};
    const pad = { l: o.left || 44, r: 10, t: 8, b: o.bottom || 22 };
    g.strokeStyle = tok('--line', '#334');
    g.lineWidth = 1;
    g.beginPath();
    g.moveTo(pad.l, pad.t); g.lineTo(pad.l, h - pad.b);
    g.lineTo(w - pad.r, h - pad.b); g.stroke();
    g.fillStyle = tok('--text-3', '#889');
    g.font = '10px ui-monospace, Consolas, monospace';
    if (o.xlabel) {
      g.textAlign = 'center';
      g.fillText(o.xlabel, pad.l + (w - pad.l - pad.r) / 2, h - 5);
    }
    if (o.ylabel) {
      g.save();
      g.translate(11, pad.t + (h - pad.t - pad.b) / 2);
      g.rotate(-Math.PI / 2);
      g.textAlign = 'center';
      g.fillText(o.ylabel, 0, 0);
      g.restore();
    }
    return pad;
  }

  function drawSeries(g, pad, w, h, data, from, to, colour, opts) {
    const o = opts || {};
    let lo = o.min, hi = o.max;
    if (lo === undefined || hi === undefined) {
      lo = Infinity; hi = -Infinity;
      for (let i = from; i < to; i++) {
        if (data[i] < lo) lo = data[i];
        if (data[i] > hi) hi = data[i];
      }
      if (!(hi > lo)) { hi = lo + 1; }
    }
    const pw = w - pad.l - pad.r, phh = h - pad.t - pad.b;
    const xs = (i) => pad.l + ((i - from) / (to - from - 1)) * pw;
    const ys = (v) => pad.t + phh - ((v - lo) / (hi - lo)) * phh;
    g.strokeStyle = colour;
    g.lineWidth = o.width || 1.2;
    g.beginPath();
    const step = Math.max(1, Math.floor((to - from) / (pw * 2)));
    for (let i = from; i < to; i += step) {
      const x = xs(i), y = ys(data[i]);
      if (i === from) g.moveTo(x, y); else g.lineTo(x, y);
    }
    g.stroke();
    return { xs, ys, lo, hi };
  }

  /* ==================================================================
     Controls
     ================================================================== */
  function range(label, key, lo, hi, step, fmt, note) {
    const out = el('span', { class: 'cfcg-val',
                             text: fmt(sig[key]) });
    const input = el('input', {
      type: 'range', min: String(lo), max: String(hi), step: String(step),
      value: String(sig[key]),
      oninput: (e) => {
        sig[key] = parseFloat(e.target.value);
        out.textContent = fmt(sig[key]);
        invalidate();
        repaint();
      },
    });
    return el('label', { class: 'cfcg-slider', title: note || '' }, [
      el('span', { class: 'cfcg-slabel', text: label }),
      input, out,
    ]);
  }

  /* The sliders that belong to the recording itself, offered in every
     chapter that draws it. The reader should not have to go back to
     chapter 1 to find out what coupling looks like. */
  function signalBar(which) {
    const bits = {
      ftheta: () => range('Slow rhythm', 'ftheta', 3, 13, 0.5,
                          (v) => v.toFixed(1) + ' Hz',
                          'The theta-band rhythm this recording is built '
                          + 'around.'),
      drift: () => range('It drifts by', 'drift', -4, 4, 0.5,
                         (v) => (v > 0 ? '+' : '') + v.toFixed(1) + ' Hz',
                         'How far the slow rhythm slides between the start '
                         + 'of the window and the end. This is the thing '
                         + 'the band-resolved panel exists to show.'),
      fgamma: () => range('Fast rhythm', 'fgamma', 30, 160, 5,
                          (v) => v.toFixed(0) + ' Hz',
                          'The high-frequency rhythm whose size may or may '
                          + 'not follow the slow one.'),
      coupling: () => range('Coupling', 'coupling', 0, 1, 0.05,
                            (v) => (v * 100).toFixed(0) + '%',
                            'How much of the fast rhythm switches off away '
                            + 'from the slow rhythm’s preferred phase. '
                            + '0% is two rhythms that ignore each other.'),
      noise: () => range('Noise', 'noise', 0, 1.5, 0.05,
                         (v) => v.toFixed(2),
                         'White noise, relative to the slow rhythm’s '
                         + 'amplitude.'),
      cycles: () => range('Filter length', 'cycles', 2, 24, 1,
                          (v) => v.toFixed(0) + ' cycles',
                          'How many cycles of its own low edge each filter '
                          + 'watches for. BARRY’s eegfilt uses 3. This '
                          + 'is the number chapter 6 is about.'),
    };
    return el('div', { class: 'cfcg-bar' },
              (which || []).map((k) => bits[k]()));
  }

  function para(text) { return el('p', { class: 'cfcg-p', text }); }
  function small(text) { return el('p', { class: 'cfcg-sm', text }); }
  function label(text) { return el('div', { class: 'section-label', text }); }

  function figure(cv, caption) {
    return el('div', { class: 'cfcg-fig' },
              [cv, caption ? el('p', { class: 'cfcg-cap', text: caption })
                           : null].filter(Boolean));
  }

  /* ==================================================================
     The chapters
     ================================================================== */
  const CHAPTERS = [
    {
      id: 'trace',
      title: 'A recording is a voltage',
      build: (h) => {
        h.appendChild(para(
          'One electrode in the hippocampus, sampled ' + FS + ' times a '
          + 'second. Every panel in BARRY starts from this and nothing '
          + 'else: a number per sample, in microvolts, and the only thing '
          + 'that has happened so far is that a wire was in a brain.'));
        h.appendChild(para(
          'This recording is synthetic, and everything below is computed '
          + 'from it live. That is on purpose — you can move the '
          + 'sliders and watch every later chapter change, which is not '
          + 'something a real recording lets you do. It holds a slow '
          + 'rhythm, a fast one, and noise.'));
        h.appendChild(signalBar(['ftheta', 'fgamma', 'coupling', 'noise']));

        const cv = surface(0, 190);
        h.appendChild(figure(cv,
          'Two seconds of it. The slow wave is easy to see. The fast one is '
          + 'in there too — it is the fuzz on the slow wave, and it is '
          + 'not something the eye can measure.'));
        cv._paint = () => {
          const { g, w, h: hh } = ctxOf(cv, 190);
          const b = build();
          const pad = plotFrame(g, w, hh,
                                { xlabel: 'seconds', ylabel: 'µV' });
          const to = Math.min(N, Math.round(FS * 2));
          drawSeries(g, pad, w, hh, b.x, 0, to,
                     tok('--text', '#eee'), { width: 1 });
          g.fillStyle = tok('--text-3', '#889');
          g.textAlign = 'left';
          g.fillText('0', pad.l, hh - 10);
          g.textAlign = 'right';
          g.fillText('2', w - 10, hh - 10);
        };

        h.appendChild(small(
          'Turn the noise up and the fast rhythm disappears from view '
          + 'entirely. It is still there, and the next two chapters find it '
          + 'without looking.'));
      },
    },

    {
      id: 'freq',
      title: 'What "8 Hz" means',
      build: (h) => {
        h.appendChild(para(
          'A rhythm at 8 Hz goes round eight times a second, so one cycle '
          + 'takes an eighth of a second. That is the whole of it. Theta is '
          + 'a name for the rhythms between about 4 and 12 Hz; gamma for '
          + 'the ones between about 30 and 150.'));
        h.appendChild(para(
          'Any recording can be written as a sum of rhythms, and asking '
          + 'how big each one is gives the spectrum. The two peaks below '
          + 'are the two rhythms this recording was built from — found, '
          + 'not assumed. Move a slider and watch its peak move.'));
        h.appendChild(signalBar(['ftheta', 'fgamma', 'noise']));

        const cv = surface(0, 210);
        h.appendChild(figure(cv,
          'Power against frequency, log vertical. The floor is the noise: '
          + 'it is in every frequency at once, which is what "white" means.'));
        cv._paint = () => {
          const { g, w, h: hh } = ctxOf(cv, 210);
          const b = build();
          const df = FS / N;
          const top = Math.min(Math.round(200 / df), N / 2 - 1);
          const p = new Float64Array(top);
          for (let k = 1; k < top; k++) {
            p[k] = Math.log10(1e-9 + (b.spec.re[k] * b.spec.re[k]
                                      + b.spec.im[k] * b.spec.im[k])
                              / (N * N));
          }
          const pad = plotFrame(g, w, hh, { xlabel: 'Hz',
                                            ylabel: 'log power' });
          drawSeries(g, pad, w, hh, p, 1, top,
                     tok('--accent', '#FFB81C'), { width: 1 });
          g.fillStyle = tok('--text-3', '#889');
          g.font = '10px ui-monospace, Consolas, monospace';
          for (const f of [0, 50, 100, 150, 200]) {
            const x = pad.l + (f / (top * df))
                            * (w - pad.l - pad.r);
            g.textAlign = 'center';
            g.fillText(String(f), x, hh - 10);
          }
        };
      },
    },

    {
      id: 'filter',
      title: 'Asking how much of one rhythm there is',
      build: (h) => {
        h.appendChild(para(
          'To measure one rhythm you throw the others away. That is a '
          + 'filter: keep a band of frequencies, discard the rest. What '
          + 'comes back is the recording as it would look if only that band '
          + 'existed.'));
        h.appendChild(para(
          'A filter cannot do this instantly. It has to watch the signal '
          + 'for long enough to tell one frequency from a nearby one, and '
          + '"long enough" is counted in cycles of the rhythm it is looking '
          + 'for. BARRY’s filter watches for three. That single choice '
          + 'is responsible for the line you clicked to get here, and '
          + 'chapter 6 is about it.'));
        h.appendChild(signalBar(['ftheta', 'noise', 'cycles']));

        const cv = surface(0, 230);
        h.appendChild(figure(cv,
          'Top: the recording. Bottom: only the slow band, at the width the '
          + 'filter length allows.'));
        cv._paint = () => {
          const { g, w, h: hh } = ctxOf(cv, 230);
          const b = build();
          const band = bandOf(sig.ftheta, sig.cycles);
          const to = Math.min(N, Math.round(FS * 2));
          const half = hh / 2;

          let pad = plotFrame(g, w, half, { bottom: 8, ylabel: 'raw' });
          drawSeries(g, pad, w, half, b.x, 0, to,
                     tok('--text-3', '#889'), { width: 1 });

          g.save();
          g.translate(0, half);
          pad = plotFrame(g, w, half, { xlabel: 'seconds',
                                        ylabel: 'filtered' });
          drawSeries(g, pad, w, half, band.wave, 0, to,
                     tok('--accent', '#FFB81C'), { width: 1.4 });
          g.restore();
        };

        const note = el('p', { class: 'cfcg-sm' });
        h.appendChild(note);
        note._paint = () => {
          const w = sig.ftheta / sig.cycles;
          note.textContent =
            'At ' + sig.ftheta.toFixed(1) + ' Hz with a '
            + sig.cycles + '-cycle filter, the band is about '
            + w.toFixed(2) + ' Hz wide and the filter is '
            + (sig.cycles / sig.ftheta).toFixed(2) + ' s long. '
            + 'Those two numbers are the same fact.';
        };
      },
    },

    {
      id: 'phase',
      title: 'Amplitude and phase',
      build: (h) => {
        h.appendChild(para(
          'Once you have one band, there are two separate questions you can '
          + 'ask about it at every instant: how big is it, and where in its '
          + 'cycle is it.'));
        h.appendChild(para(
          'How big is the amplitude, or envelope — the outline the '
          + 'wave would have if you traced its peaks. Where in its cycle is '
          + 'the phase, which runs from −π at one trough round to '
          + '+π at the next. Both come out of the same operation, and '
          + 'together they are all coupling is made of: the phase of the '
          + 'slow rhythm, and the amplitude of the fast one.'));
        h.appendChild(signalBar(['ftheta', 'fgamma', 'coupling']));

        const cv = surface(0, 250);
        h.appendChild(figure(cv,
          'Top: the slow band, with its phase underneath as a colour strip '
          + '— one full sweep per cycle. Bottom: the fast band, with '
          + 'its envelope drawn over it.'));
        cv._paint = () => {
          const { g, w, h: hh } = ctxOf(cv, 250);
          const slow = bandOf(sig.ftheta, sig.cycles);
          const fast = bandOf(sig.fgamma, Math.max(sig.cycles, 6));
          const to = Math.min(N, Math.round(FS * 1.5));
          const half = hh / 2;

          let pad = plotFrame(g, w, half - 16, { bottom: 6, ylabel: 'slow' });
          drawSeries(g, pad, w, half - 16, slow.wave, 0, to,
                     tok('--accent', '#FFB81C'), { width: 1.4 });

          /* The phase, as a strip rather than a sawtooth. A sawtooth of
             phase is read as a signal that jumps, which is exactly what
             phase does not do -- it is an angle, and the jump is the seam
             where the drawing wraps. */
          const pw = w - pad.l - pad.r;
          const y0 = half - 14;
          for (let px = 0; px < pw; px++) {
            const i = Math.round((px / pw) * (to - 1));
            const frac = (slow.pha[i] + Math.PI) / (2 * Math.PI);
            const c = Math.round(60 + 195 * (1 - Math.abs(frac - 0.5) * 2));
            g.fillStyle = 'rgb(' + c + ',' + Math.round(c * 0.55) + ',180)';
            g.fillRect(pad.l + px, y0, 1, 10);
          }
          g.fillStyle = tok('--text-3', '#889');
          g.font = '10px ui-monospace, Consolas, monospace';
          g.textAlign = 'left';
          g.fillText('phase', 4, y0 + 9);

          g.save();
          g.translate(0, half + 4);
          pad = plotFrame(g, w, half - 4, { xlabel: 'seconds',
                                            ylabel: 'fast' });
          const amp = fast.amp;
          let peak = 0;
          for (let i = 0; i < to; i++) if (amp[i] > peak) peak = amp[i];
          drawSeries(g, pad, w, half - 4, fast.wave, 0, to,
                     tok('--text-3', '#889'),
                     { width: 1, min: -peak, max: peak });
          drawSeries(g, pad, w, half - 4, amp, 0, to,
                     tok('--ok', '#5cc98d'),
                     { width: 1.6, min: -peak, max: peak });
          g.restore();
        };

        h.appendChild(small(
          'With coupling above zero the green envelope rises and falls once '
          + 'per slow cycle, in step with the colour strip. That is the '
          + 'whole phenomenon. Everything after this is how to put a number '
          + 'on it.'));
      },
    },

    {
      id: 'which',
      title: 'Which theta, not how much',
      build: (h) => {
        h.appendChild(para(
          'The ordinary theta panel filters 4–12 Hz in one go and draws '
          + 'the result. That answers how much theta there is. It cannot '
          + 'answer which theta — and when a rhythm slides from 7 Hz to '
          + '9 Hz during a recording, which is the question being asked.'));
        h.appendChild(para(
          'So the band-resolved panel runs one narrow filter per row and '
          + 'stacks them: frequency up the side, time along the bottom, '
          + 'brightness for power. Set the drift below and watch the bright '
          + 'stripe travel.'));
        h.appendChild(signalBar(['ftheta', 'drift', 'noise', 'cycles']));

        const cv = surface(0, 260);
        h.appendChild(figure(cv,
          'The band raster, computed here exactly as the panel computes it: '
          + 'the mean squared envelope of each band, in 0.5 Hz steps from 4 '
          + 'to 12 Hz.'));
        cv._paint = () => {
          const { g, w, h: hh } = ctxOf(cv, 260);
          const rows = [];
          for (let f = 4; f <= 12.001; f += 0.5) rows.push(Math.round(f * 2) / 2);
          const pad = plotFrame(g, w, hh, { xlabel: 'seconds',
                                            ylabel: 'Hz', left: 40 });
          const pw = w - pad.l - pad.r, ph = hh - pad.t - pad.b;
          const cols = Math.max(40, Math.min(240, Math.floor(pw)));
          const grid = [];
          let top = 0;
          for (const f of rows) {
            const band = bandOf(f, sig.cycles);
            const line = new Float64Array(cols);
            const per = Math.floor(N / cols);
            for (let c = 0; c < cols; c++) {
              let s = 0;
              for (let i = c * per; i < (c + 1) * per; i++) {
                s += band.amp[i] * band.amp[i];
              }
              line[c] = s / per;
              if (line[c] > top) top = line[c];
            }
            grid.push(line);
          }
          const cw = pw / cols, chh = ph / rows.length;
          for (let r = 0; r < rows.length; r++) {
            for (let c = 0; c < cols; c++) {
              const v = top > 0 ? grid[r][c] / top : 0;
              const s = Math.pow(v, 0.45);
              g.fillStyle = 'rgb(' + Math.round(20 + 235 * s) + ','
                          + Math.round(24 + 160 * s) + ','
                          + Math.round(40 + 20 * s) + ')';
              g.fillRect(pad.l + c * cw,
                         pad.t + ph - (r + 1) * chh,
                         Math.ceil(cw) + 0.5, Math.ceil(chh) + 0.5);
            }
          }
          g.fillStyle = tok('--text-3', '#889');
          g.font = '10px ui-monospace, Consolas, monospace';
          g.textAlign = 'right';
          for (const f of [4, 6, 8, 10, 12]) {
            const y = pad.t + ph - ((f - 4) / 8) * ph;
            g.fillText(String(f), pad.l - 5, y + 3);
          }
        };

        h.appendChild(small(
          'Notice how thick the stripe is even with the drift at zero. That '
          + 'is not the rhythm being vague. It is the next chapter.'));
      },
    },

    {
      id: 'width',
      title: 'Why 0.5 Hz is not 0.5 Hz',
      build: (h) => {
        h.appendChild(para(
          'This is the chapter behind the line the panel prints. You asked '
          + 'for bands 0.5 Hz apart and 0.5 Hz wide. What you got was bands '
          + '0.5 Hz apart and between 1.14 and 3.42 Hz wide.'));
        h.appendChild(para(
          'The reason is in chapter 3. The filter’s length is set by '
          + 'the low edge of the band and nothing else: eegfilt uses '
          + '3 × fix(fs / f₁) taps, which is three cycles of that '
          + 'edge, however narrow a band you asked for. A filter that '
          + 'watches for three cycles lasts 3/f seconds, and a filter that '
          + 'lasts T seconds cannot separate frequencies closer than about '
          + '1/T. Put those together and the narrowest band available at f '
          + 'is about f/3 — and the 0.5 you typed never enters the '
          + 'arithmetic at all.'));

        const tbl = el('table', { class: 'cfcg-tbl' });
        tbl.appendChild(el('thead', {}, [el('tr', {}, [
          el('th', { text: 'band' }), el('th', { text: 'asked' }),
          el('th', { text: 'measured' }), el('th', { text: 'f/3' }),
          el('th', { text: 'overlap' }),
        ])]));
        const body = el('tbody', {});
        /* Measured off the real FIR, at 3 kHz, by reading the half-power
           width of the filter eegfilt actually designs. Printed rather than
           recomputed here because these are the numbers the panel shows. */
        for (const [f, got] of [[4, 1.14], [6, 1.71], [8, 2.28],
                                [10, 2.85], [12, 3.42]]) {
          body.appendChild(el('tr', {}, [
            el('td', { text: f + ' Hz' }),
            el('td', { text: '0.5' }),
            el('td', { class: 'strong', text: got.toFixed(2) }),
            el('td', { text: (f / 3).toFixed(2) }),
            el('td', { text: (got / 0.5).toFixed(1) + '×' }),
          ]));
        }
        tbl.appendChild(body);
        h.appendChild(tbl);
        h.appendChild(small(
          'Measured off the filter BARRY designs, at 3 kHz. The f/3 column '
          + 'is the rule of thumb; the filter does slightly better than it '
          + 'because firls is handed 15% ramps rather than a brick wall.'));

        h.appendChild(label('What overlap costs'));
        h.appendChild(para(
          'A band 2.28 Hz wide, stepped by 0.5 Hz, shares most of its '
          + 'signal with its neighbours — four and a half rows are '
          + 'looking at the same frequencies. Add up step ÷ width '
          + 'across the axis and the seventeen rows carry about four '
          + 'independent numbers. Not seventeen.'));

        const cv = surface(0, 220);
        h.appendChild(figure(cv,
          'Every row of the panel, drawn as what it actually covers. Move '
          + 'the filter length and watch the bars narrow — and read '
          + 'the cost underneath.'));
        cv._paint = () => {
          const { g, w, h: hh } = ctxOf(cv, 220);
          const pad = plotFrame(g, w, hh, { xlabel: 'Hz covered',
                                            ylabel: 'row', left: 40 });
          const pw = w - pad.l - pad.r, ph = hh - pad.t - pad.b;
          const rows = [];
          for (let f = 4; f <= 12.001; f += 0.5) rows.push(f);
          const xs = (f) => pad.l + ((f - 2) / 14) * pw;
          const bh = Math.max(2, ph / rows.length - 1.5);
          rows.forEach((f, i) => {
            const bw = f / sig.cycles;
            const y = pad.t + ph - (i + 1) * (ph / rows.length);
            g.fillStyle = tok('--accent-soft', 'rgba(255,184,28,.15)');
            g.fillRect(xs(f - bw / 2), y, xs(f + bw / 2) - xs(f - bw / 2), bh);
            g.strokeStyle = tok('--accent-line', 'rgba(255,184,28,.45)');
            g.lineWidth = 1;
            g.strokeRect(xs(f - bw / 2), y,
                         xs(f + bw / 2) - xs(f - bw / 2), bh);
            g.fillStyle = tok('--text', '#eee');
            g.fillRect(xs(f) - 0.5, y, 1, bh);
          });
          g.fillStyle = tok('--text-3', '#889');
          g.font = '10px ui-monospace, Consolas, monospace';
          g.textAlign = 'center';
          for (const f of [2, 4, 6, 8, 10, 12, 14, 16]) {
            g.fillText(String(f), xs(f), hh - 8);
          }
        };

        const cost = el('div', { class: 'cfcg-cost' });
        h.appendChild(cost);
        cost._paint = () => {
          cost.innerHTML = '';
          /* Capped at the number of rows.
             
             The sum of step/width is the right count while the bands are
             wider than the step, which is the case this chapter is about.
             Once they are NARROWER than the step it keeps climbing and
             claimed 28.4 independent numbers across 17 rows -- which is
             not a thing. Seventeen rows can carry seventeen numbers at
             most; past that the axis is undersampling the spectrum rather
             than oversampling it. */
          let rows = 0, indep = 0;
          for (let f = 4; f <= 12.001; f += 0.5) {
            rows += 1;
            indep += 0.5 / (f / sig.cycles);
          }
          const over = indep > rows;
          indep = Math.min(indep, rows);
          const lowW = 4 / sig.cycles, hiW = 12 / sig.cycles;
          const secs = sig.cycles / 4;
          cost.appendChild(el('div', { class: 'cfcg-costrow' }, [
            el('span', { class: 'cfcg-big',
                         text: over ? String(rows) : indep.toFixed(1) }),
            el('span', { text: over
              ? 'independent numbers — all 17 rows, and now the bands '
                + 'are narrower than the 0.5 Hz step, so the axis is '
                + 'stepping over spectrum it never looks at'
              : 'independent numbers across 17 rows' }),
          ]));
          cost.appendChild(el('div', { class: 'cfcg-costrow' }, [
            el('span', { class: 'cfcg-big',
                         text: lowW.toFixed(2) + '–' + hiW.toFixed(2) }),
            el('span', { text: 'Hz wide, from the bottom of the axis to the '
                               + 'top' }),
          ]));
          cost.appendChild(el('div', { class: 'cfcg-costrow' }, [
            el('span', { class: 'cfcg-big', text: secs.toFixed(2) + ' s' }),
            el('span', { text: 'of recording inside each filter at 4 Hz '
                               + '— the price of narrowing them' }),
          ]));
        };

        h.appendChild(label('The trade you cannot escape'));
        h.appendChild(para(
          'Drag the filter length up to 24 cycles. The bands become genuinely '
          + 'narrow and the independent count approaches seventeen — and '
          + 'the filter now holds six seconds of recording at 4 Hz, so '
          + 'anything that happens faster than that is smeared away. Go back '
          + 'to chapter 5 with 24 cycles set and watch the drifting stripe '
          + 'lose its slope.'));
        h.appendChild(para(
          'Three cycles is eegfilt’s choice and your pipeline '
          + 'inherited it. It buys time resolution and pays in frequency '
          + 'resolution, which is the right way round for "where is theta '
          + 'right now" — but it has to be said out loud, which is '
          + 'what that line on the panel is for.'));
        h.appendChild(signalBar(['cycles']));

        h.appendChild(label('So what may you say'));
        const dl = el('dl', { class: 'cfcg-dl' });
        [['Not a peak to ±0.25 Hz',
          'The rows are 0.5 Hz apart but the uncertainty is the width: '
          + 'about 1.1 Hz at the bottom of theta, 3.4 Hz at the top.'],
         ['Not seventeen comparisons',
          'Counting significant bands, or correcting for seventeen tests, '
          + 'treats overlapping rows as independent. The real count is '
          + 'about four.'],
         ['Not two rhythms',
          'Two bright neighbouring rows are one measurement smeared, not '
          + 'two rhythms. At 8 Hz nothing closer than about 2.3 Hz apart '
          + 'can be resolved.'],
         ['Not a width comparison',
          'The top of the axis is three times coarser than the bottom, so a '
          + 'sharp 11 Hz rhythm draws a broader stripe than an equally '
          + 'sharp 5 Hz one. Widths are not comparable across the axis.'],
         ['But yes, movement',
          'A rhythm sliding from 7 Hz to 9 Hz moves the stripe by about one '
          + 'bandwidth, and that reads clearly. Tracking a peak over time is '
          + 'a different question from resolving two peaks at one time, and '
          + 'this panel is good at the first.'],
        ].forEach(([t, d]) => {
          dl.appendChild(el('dt', { text: t }));
          dl.appendChild(el('dd', { text: d }));
        });
        h.appendChild(dl);
      },
    },

    {
      id: 'coupling',
      title: 'Coupling: phase drives amplitude',
      build: (h) => {
        h.appendChild(para(
          'Phase-amplitude coupling is one claim: the fast rhythm is bigger '
          + 'at some phases of the slow rhythm than at others. Nothing more '
          + 'than that.'));
        h.appendChild(para(
          'You already have both halves — the slow phase and the fast '
          + 'envelope, from chapter 4. So sort every sample by the slow '
          + 'phase it happened at, and average the fast envelope within each '
          + 'of eighteen bins. If the fast rhythm does not care, the bins '
          + 'come out flat. If it does, they come out humped, and the top of '
          + 'the hump is the phase it prefers.'));
        h.appendChild(signalBar(['coupling', 'ftheta', 'fgamma', 'noise']));

        const cv = surface(0, 250);
        h.appendChild(figure(cv,
          'The eighteen bins. Drag coupling to 0 and they flatten; the '
          + 'residual bumpiness at 0 is noise, and chapter 10 is about not '
          + 'being fooled by it.'));
        cv._paint = () => {
          const { g, w, h: hh } = ctxOf(cv, 250);
          const slow = bandOf(sig.ftheta, sig.cycles);
          const fast = bandOf(sig.fgamma, Math.max(sig.cycles, 6));
          const mean = histogram(slow.pha, fast.amp, skipFor(sig.ftheta));
          const pad = plotFrame(g, w, hh, {
            xlabel: 'phase of the slow rhythm', ylabel: 'mean fast amplitude',
            left: 52 });
          const pw = w - pad.l - pad.r, ph = hh - pad.t - pad.b;
          let top = 0;
          for (const v of mean) if (v > top) top = v;
          const bw = pw / (NBINS * 2);
          /* Two cycles side by side. One cycle of a circular quantity read
             as a bar chart invites the eye to see a beginning and an end
             where there is only a seam. */
          for (let rep = 0; rep < 2; rep++) {
            for (let b = 0; b < NBINS; b++) {
              const v = top > 0 ? mean[b] / top : 0;
              const x = pad.l + (rep * NBINS + b) * bw;
              g.fillStyle = rep
                ? tok('--accent-soft', 'rgba(255,184,28,.15)')
                : tok('--accent', '#FFB81C');
              g.fillRect(x + 1, pad.t + ph - v * ph, bw - 2, v * ph);
            }
          }
          /* Where flat would be. Without it, a hump is just a shape. */
          let tot = 0;
          for (const v of mean) tot += v;
          const flat = top > 0 ? (tot / NBINS) / top : 0;
          g.strokeStyle = tok('--text-3', '#889');
          g.setLineDash([4, 3]);
          g.beginPath();
          g.moveTo(pad.l, pad.t + ph - flat * ph);
          g.lineTo(w - pad.r, pad.t + ph - flat * ph);
          g.stroke();
          g.setLineDash([]);
          g.fillStyle = tok('--text-3', '#889');
          g.font = '10px ui-monospace, Consolas, monospace';
          g.textAlign = 'left';
          g.fillText('flat = no coupling', pad.l + 4,
                     pad.t + ph - flat * ph - 4);
          g.textAlign = 'center';
          ['−π', '0', 'π', '0', 'π'].forEach((t, i) => {
            g.fillText(t, pad.l + (i / 4) * pw, hh - 8);
          });
        };
      },
    },

    {
      id: 'mi',
      title: 'One number: the modulation index',
      build: (h) => {
        h.appendChild(para(
          'A shape is hard to compare, so the eighteen bins are reduced to '
          + 'one number — how far from flat they are. Normalise the '
          + 'bins so they sum to one, measure the difference from a '
          + 'perfectly flat distribution, and divide by log 18 so the answer '
          + 'lands between 0 and 1. That is Tort’s modulation index, '
          + 'and it is what every cell of a comodulogram holds.'));
        h.appendChild(para(
          'The numbers are small. A modulation index of 0.01 is a real, '
          + 'ordinary effect; 0.1 is enormous. This is why the panels print '
          + 'five decimal places and why an autoscaled colour bar is so '
          + 'dangerous — chapter 9.'));
        h.appendChild(signalBar(['coupling', 'noise']));

        const read = el('div', { class: 'cfcg-cost' });
        h.appendChild(read);
        const cv = surface(0, 170);
        h.appendChild(figure(cv,
          'Modulation index against coupling, computed across the whole '
          + 'range with everything else held where you left it. The dot is '
          + 'where the slider is.'));
        read._paint = () => {
          read.innerHTML = '';
          const v = mi(sig.ftheta, sig.fgamma);
          read.appendChild(el('div', { class: 'cfcg-costrow' }, [
            el('span', { class: 'cfcg-big', text: v.toFixed(5) }),
            el('span', { text: 'modulation index at ' + sig.ftheta.toFixed(1)
                               + ' Hz × ' + sig.fgamma.toFixed(0)
                               + ' Hz' }),
          ]));
        };
        cv._paint = () => {
          const { g, w, h: hh } = ctxOf(cv, 170);
          const keep = sig.coupling;
          const xs = [], ys = [];
          for (let c = 0; c <= 1.0001; c += 0.1) {
            sig.coupling = c;
            invalidate();
            xs.push(c);
            ys.push(mi(sig.ftheta, sig.fgamma));
          }
          sig.coupling = keep;
          invalidate();
          const pad = plotFrame(g, w, hh, { xlabel: 'coupling',
                                            ylabel: 'MI', left: 58 });
          const pw = w - pad.l - pad.r, ph = hh - pad.t - pad.b;
          let top = 0;
          for (const v of ys) if (v > top) top = v;
          top = top || 1;
          g.strokeStyle = tok('--accent', '#FFB81C');
          g.lineWidth = 1.6;
          g.beginPath();
          ys.forEach((v, i) => {
            const x = pad.l + xs[i] * pw, y = pad.t + ph - (v / top) * ph;
            if (!i) g.moveTo(x, y); else g.lineTo(x, y);
          });
          g.stroke();
          const cx = pad.l + keep * pw;
          const cy = pad.t + ph - (mi(sig.ftheta, sig.fgamma) / top) * ph;
          g.fillStyle = tok('--ok', '#5cc98d');
          g.beginPath(); g.arc(cx, cy, 4, 0, 2 * Math.PI); g.fill();
          g.fillStyle = tok('--text-3', '#889');
          g.font = '10px ui-monospace, Consolas, monospace';
          g.textAlign = 'right';
          g.fillText(top.toFixed(4), pad.l - 5, pad.t + 8);
          g.fillText('0', pad.l - 5, pad.t + ph + 3);
          g.textAlign = 'center';
          g.fillText('0', pad.l, hh - 8);
          g.fillText('100%', w - pad.r, hh - 8);
        };

        h.appendChild(small(
          'The curve does not start at zero. With no coupling at all the '
          + 'index is still a small positive number, because eighteen bins '
          + 'of noisy averages are never exactly flat. That floor is what '
          + 'surrogates are for.'));
      },
    },

    {
      id: 'comod',
      title: 'The comodulogram',
      build: (h) => {
        h.appendChild(para(
          'So far one slow band and one fast band. But you do not know which '
          + 'pair to look at — that is the finding, not the input. So do '
          + 'it for every pair: a slow band along the bottom, a fast band up '
          + 'the side, and the modulation index of each pair as a colour. '
          + 'That map is the comodulogram.'));
        h.appendChild(para(
          'Nothing new happens here. Every cell is chapter 8 run once. The '
          + 'grid below is live — it is ' + '13 × 15 = 195'
          + ' modulation indices, recomputed as you drag.'));
        h.appendChild(signalBar(['ftheta', 'fgamma', 'coupling', 'noise']));

        const cmap = { mode: 'seq', lock: false, top: null };
        const cv = surface(0, 340);
        const readout = el('p', { class: 'cfcg-cap',
                                  text: 'Hover a cell to read it.' });

        h.appendChild(el('div', { class: 'cfcg-bar' }, [
          el('button', { class: 'mini on', text: 'Sequential',
            title: 'One hue, dark to light. The only kind that reads as '
                 + '"nothing here" when there is nothing here.',
            onclick: (e) => {
              cmap.mode = 'seq';
              e.target.classList.add('on');
              e.target.nextSibling.classList.remove('on');
              cv._paint();
            } }),
          el('button', { class: 'mini', text: 'Rainbow',
            title: 'What the explainer’s fig11 is about: a rainbow '
                 + 'invents edges in smooth data.',
            onclick: (e) => {
              cmap.mode = 'jet';
              e.target.classList.add('on');
              e.target.previousSibling.classList.remove('on');
              cv._paint();
            } }),
          el('span', { class: 'cfcg-gap' }),
          el('button', { class: 'mini', text: 'Lock the scale',
            title: 'Hold the colour scale where it is, so a second map can '
                 + 'be compared with this one.',
            onclick: (e) => {
              cmap.lock = !cmap.lock;
              e.target.classList.toggle('on', cmap.lock);
              e.target.textContent = cmap.lock ? 'Scale locked'
                                               : 'Lock the scale';
              cv._paint();
            } }),
        ]));
        h.appendChild(figure(cv, null));
        h.appendChild(readout);

        const SLOW = [], FAST = [];
        for (let f = 2; f <= 14.001; f += 1) SLOW.push(f);
        for (let f = 20; f <= 160.001; f += 10) FAST.push(f);

        function grid() {
          const b = build();
          if (b.comod) return b.comod;
          const m = [];
          let top = 0, peak = null;
          for (let j = 0; j < SLOW.length; j++) {
            m.push([]);
            for (let i = 0; i < FAST.length; i++) {
              const v = mi(SLOW[j], FAST[i]);
              m[j].push(v);
              if (v > top) { top = v; peak = [SLOW[j], FAST[i]]; }
            }
          }
          b.comod = { m, top, peak };
          return b.comod;
        }

        function colour(frac) {
          const f = Math.max(0, Math.min(1, frac));
          if (cmap.mode === 'jet') {
            /* Deliberately the bad one, so the chapter can show what it
               does rather than assert it. */
            const r = Math.max(0, Math.min(1, 1.5 - Math.abs(4 * f - 3)));
            const g2 = Math.max(0, Math.min(1, 1.5 - Math.abs(4 * f - 2)));
            const b2 = Math.max(0, Math.min(1, 1.5 - Math.abs(4 * f - 1)));
            return 'rgb(' + Math.round(r * 255) + ',' + Math.round(g2 * 255)
                 + ',' + Math.round(b2 * 255) + ')';
          }
          const s = Math.pow(f, 0.8);
          return 'rgb(' + Math.round(12 + 243 * s) + ','
               + Math.round(20 + 164 * s) + ','
               + Math.round(35 + 8 * s) + ')';
        }

        let geom = null;
        cv._paint = () => {
          const { g, w, h: hh } = ctxOf(cv, 340);
          const r = grid();
          if (cmap.lock && cmap.top == null) cmap.top = r.top;
          if (!cmap.lock) cmap.top = null;
          const top = cmap.lock ? cmap.top : r.top;
          const pad = plotFrame(g, w, hh, {
            xlabel: 'phase band — the slow rhythm (Hz)',
            ylabel: 'amplitude band (Hz)', left: 46 });
          const pw = w - pad.l - pad.r, ph = hh - pad.t - pad.b;
          const cw = pw / SLOW.length, chh = ph / FAST.length;
          for (let j = 0; j < SLOW.length; j++) {
            for (let i = 0; i < FAST.length; i++) {
              g.fillStyle = colour(top > 0 ? r.m[j][i] / top : 0);
              g.fillRect(pad.l + j * cw, pad.t + ph - (i + 1) * chh,
                         Math.ceil(cw) + 0.5, Math.ceil(chh) + 0.5);
            }
          }
          geom = { pad, cw, ch: chh, ph };
          g.fillStyle = tok('--text-3', '#889');
          g.font = '10px ui-monospace, Consolas, monospace';
          g.textAlign = 'center';
          SLOW.forEach((f, j) => {
            if (f % 2 === 0) g.fillText(String(f), pad.l + (j + 0.5) * cw,
                                        hh - 8);
          });
          g.textAlign = 'right';
          FAST.forEach((f, i) => {
            if (f % 40 === 0) {
              g.fillText(String(f), pad.l - 5,
                         pad.t + ph - (i + 0.5) * chh + 3);
            }
          });
          readout.textContent = 'Largest modulation index on this map: '
            + r.top.toFixed(5) + ' at ' + r.peak[0] + ' Hz phase × '
            + r.peak[1] + ' Hz amplitude'
            + (cmap.lock ? '   ·  colour scale locked at '
                           + cmap.top.toFixed(5) : '');
        };

        cv.addEventListener('mousemove', (e) => {
          if (!geom) return;
          const r = cv.getBoundingClientRect();
          const x = e.clientX - r.left, y = e.clientY - r.top;
          const j = Math.floor((x - geom.pad.l) / geom.cw);
          const i = Math.floor((geom.pad.t + geom.ph - y) / geom.ch);
          const got = grid();
          if (j < 0 || j >= SLOW.length || i < 0 || i >= FAST.length) return;
          readout.textContent = SLOW[j] + ' Hz phase × ' + FAST[i]
            + ' Hz amplitude   —   MI ' + got.m[j][i].toFixed(5)
            + '   (' + (100 * got.m[j][i] / (got.top || 1)).toFixed(0)
            + '% of this map’s largest)';
        });

        h.appendChild(label('The colour is part of the measurement'));
        h.appendChild(para(
          'Set coupling to 0 and look at the map. With a sequential scale it '
          + 'reads as an empty map, which is the truth. Press Rainbow and '
          + 'the same numbers grow structure — bands and edges that are '
          + 'nothing but the colour scheme’s own boundaries laid over '
          + 'noise. Nothing in the data changed.'));
        h.appendChild(para(
          'The second trap is the scale. Every map here is drawn against its '
          + 'own maximum, so a map of pure noise fills the full colour range '
          + 'exactly as a map of real coupling does. That is why the largest '
          + 'value is always printed, and why comparing two maps means '
          + 'locking the scale first.'));
      },
    },

    {
      id: 'surrogate',
      title: 'Is it real? surrogates',
      build: (h) => {
        h.appendChild(para(
          'A modulation index is never zero, so "greater than zero" proves '
          + 'nothing. The question is whether it is bigger than the same '
          + 'arithmetic would give on data with the coupling deliberately '
          + 'broken.'));
        h.appendChild(para(
          'So: keep the slow phase, keep the fast envelope, and slide one of '
          + 'them in time by a random amount. Every rhythm, every amplitude '
          + 'distribution and all the noise survive; only the alignment '
          + 'between them is destroyed. Recompute the index. Do it fifty '
          + 'times and you have the distribution of answers that "no '
          + 'coupling" produces for this recording. Where your real value '
          + 'sits in that spread is the result.'));
        h.appendChild(signalBar(['coupling', 'noise']));

        const read = el('div', { class: 'cfcg-cost' });
        const cv = surface(0, 200);
        h.appendChild(read);
        h.appendChild(figure(cv,
          'Fifty surrogates as a histogram, with the real value marked. If '
          + 'the mark is inside the crowd, there is nothing to report.'));

        function surrogates() {
          const slow = bandOf(sig.ftheta, sig.cycles);
          const fast = bandOf(sig.fgamma, Math.max(sig.cycles, 6));
          const skip = skipFor(sig.ftheta);
          const real = miOf(histogram(slow.pha, fast.amp, skip));
          const shifted = new Float64Array(N);
          const out = [];
          for (let s = 0; s < 50; s++) {
            /* A whole-signal circular shift, which is the surrogate the
               pipeline uses: it breaks the timing relationship and leaves
               everything else exactly as it was. */
            const off = Math.floor(((s * 2654435761) % N) * 0.999) % N;
            for (let i = 0; i < N; i++) shifted[i] = fast.amp[(i + off) % N];
            out.push(miOf(histogram(slow.pha, shifted, skip)));
          }
          const mean = out.reduce((a, b) => a + b, 0) / out.length;
          const sd = Math.sqrt(out.reduce(
            (a, b) => a + (b - mean) * (b - mean), 0) / out.length) || 1e-12;
          const over = out.filter((v) => v >= real).length;
          return { real, out, mean, sd, z: (real - mean) / sd,
                   p: (over + 1) / (out.length + 1) };
        }

        read._paint = () => {
          read.innerHTML = '';
          const r = surrogates();
          read.appendChild(el('div', { class: 'cfcg-costrow' }, [
            el('span', { class: 'cfcg-big', text: r.real.toFixed(5) }),
            el('span', { text: 'the real modulation index' }),
          ]));
          read.appendChild(el('div', { class: 'cfcg-costrow' }, [
            el('span', { class: 'cfcg-big', text: r.mean.toFixed(5) }),
            el('span', { text: 'what broken coupling gives, on average' }),
          ]));
          read.appendChild(el('div', { class: 'cfcg-costrow' }, [
            el('span', { class: 'cfcg-big', text: 'z ' + r.z.toFixed(1) }),
            el('span', { text: 'standard deviations above that — and '
                               + 'p ≤ ' + r.p.toFixed(3) + ', the '
                               + 'smallest 50 surrogates can report' }),
          ]));
          cv._paint();
        };

        cv._paint = () => {
          const { g, w, h: hh } = ctxOf(cv, 200);
          const r = surrogates();
          const pad = plotFrame(g, w, hh, { xlabel: 'modulation index',
                                            ylabel: 'surrogates', left: 46 });
          const pw = w - pad.l - pad.r, ph = hh - pad.t - pad.b;
          const lo = Math.min(r.mean - 4 * r.sd, r.real) * 0.98;
          const hi = Math.max(r.real, r.mean + 4 * r.sd) * 1.02;
          const bins = 24, counts = new Array(bins).fill(0);
          for (const v of r.out) {
            let b = Math.floor(((v - lo) / (hi - lo)) * bins);
            b = Math.max(0, Math.min(bins - 1, b));
            counts[b] += 1;
          }
          const top = Math.max.apply(null, counts) || 1;
          const bw = pw / bins;
          for (let b = 0; b < bins; b++) {
            const v = counts[b] / top;
            g.fillStyle = tok('--text-3', '#889');
            g.fillRect(pad.l + b * bw + 1, pad.t + ph - v * ph,
                       bw - 2, v * ph);
          }
          const rx = pad.l + ((r.real - lo) / (hi - lo)) * pw;
          g.strokeStyle = tok('--accent', '#FFB81C');
          g.lineWidth = 2;
          g.beginPath();
          g.moveTo(rx, pad.t); g.lineTo(rx, pad.t + ph); g.stroke();
          g.fillStyle = tok('--accent', '#FFB81C');
          g.font = '10px ui-monospace, Consolas, monospace';
          g.textAlign = rx > pad.l + pw * 0.7 ? 'right' : 'left';
          g.fillText('the real one', rx + (rx > pad.l + pw * 0.7 ? -4 : 4),
                     pad.t + 10);
        };

        h.appendChild(label('Two things to know before you quote a z'));
        h.appendChild(para(
          'The null here is over-dispersed: measured on this pipeline its '
          + 'standard deviation is about 1.4 rather than 1, and it does not '
          + 'shrink as you add surrogates. So a nominal z of 3 behaves like '
          + 'about 2.2, and the comodulogram window says so next to the '
          + 'surrogate count rather than letting you read the number as a '
          + 'normal z-score.'));
        h.appendChild(para(
          'And the smallest p that n surrogates can report is 1/(n+1). '
          + 'Fifty surrogates cannot produce a p below 0.02 no matter how '
          + 'strong the coupling is — if you need a smaller number you '
          + 'need more surrogates, and they cost about half a minute per '
          + 'map.'));
      },
    },

    {
      id: 'controls',
      title: 'The controls, mapped',
      build: (h) => {
        h.appendChild(para(
          'Everything above is now a field somewhere in BARRY. This is which '
          + 'one.'));
        const dl = el('dl', { class: 'cfcg-dl' });
        [['Panel → 4–12 /0.5',
          'The band axis of the band-resolved panel: from 4 Hz to 12 Hz in '
          + '0.5 Hz steps. Chapter 5 is what it draws; chapter 6 is why the '
          + 'rows are wider than 0.5.'],
         ['CFCScope → Comodulogram…',
          'Opens the window chapter 9 is about. It is a separate window on '
          + 'purpose: you keep it up while you move around the recording and '
          + 'stack maps as you go, because comparing two of them is most of '
          + 'what the thing is for.'],
         ['Phase 4–12 /0.5',
          'The horizontal axis of the map — which slow bands to try. '
          + 'The step is 0.5 and, as chapter 6 says, the bands are wider '
          + 'than that and overlap.'],
         ['Amplitude 20–200 /5, 10 Hz wide',
          'The vertical axis. Note that the width (10) is deliberately '
          + 'larger than the step (5), so these bands overlap by half. That '
          + 'is the newFCSE convention, not an oversight — and the '
          + 'realised width is far larger again: a nominal 10 Hz band at '
          + '200 Hz comes out about 57 Hz wide.'],
         ['Channel',
          'One channel, never an average. Coupling is a property of a '
          + 'signal; the average of two signals has its own phase and its '
          + 'own envelope, belonging to neither.'],
         ['From / To, and "Following the view"',
          'The window chapter 7 bins. The fields track XploreFinder until '
          + 'you type in one.'],
         ['Test it against a null',
          'Chapter 10. Off by default because it is seconds without and '
          + 'about half a minute with.'],
         ['The line before Generate',
          'Cells, modulation indices and an estimated time, measured from '
          + 'what this machine did on its last run rather than from a '
          + 'table.'],
        ].forEach(([t, d]) => {
          dl.appendChild(el('dt', { text: t }));
          dl.appendChild(el('dd', { text: d }));
        });
        h.appendChild(dl);
      },
    },

    {
      id: 'pitfalls',
      title: 'What not to claim',
      build: (h) => {
        h.appendChild(para(
          'The arithmetic will produce a number for any input. These are the '
          + 'ways it produces one that means nothing.'));
        const dl = el('dl', { class: 'cfcg-dl' });
        [['A window shorter than about forty slow cycles',
          'The eighteen phase bins have to fill up. Under roughly forty '
          + 'cycles of the slowest phase band the map is mostly noise, and '
          + 'the comodulogram window warns you before it runs. At 4 Hz that '
          + 'is ten seconds.'],
         ['A peak read to the step of the axis',
          'Chapter 6. The uncertainty is the realised width, not the step.'],
         ['Rows or cells treated as independent',
          'They overlap, by construction on the amplitude axis and by '
          + 'filter length everywhere. Seventeen theta rows carry about '
          + 'four independent numbers.'],
         ['An autoscaled colour bar',
          'A map of pure noise fills the colour range just as a map of real '
          + 'coupling does. Read the printed maximum, and lock the scale '
          + 'before comparing two maps.'],
         ['A rainbow colour map',
          'It invents edges in smooth data. Try it in chapter 9 with '
          + 'coupling at zero.'],
         ['A z-score read as a normal one',
          'The null is over-dispersed here: SD about 1.4, so a nominal 3 '
          + 'behaves like 2.2.'],
         ['A bad channel',
          'A dead or saturated channel has a phase and an envelope like '
          + 'anything else, and will happily produce a modulation index. '
          + 'Mark it bad first — the channel list in the pane’s Ch '
          + 'menu does it.'],
         ['Coupling as a direction',
          'This measures that the fast rhythm’s size tracks the slow '
          + 'rhythm’s phase. It does not say the slow rhythm caused '
          + 'it, and a shared third input would look the same.'],
        ].forEach(([t, d]) => {
          dl.appendChild(el('dt', { text: t }));
          dl.appendChild(el('dd', { text: d }));
        });
        h.appendChild(dl);
        h.appendChild(small(
          'Nothing in CFCScope or this guide writes anything down. Move the '
          + 'window, change the bands, change your mind: no set is claimed '
          + 'and no decision is recorded.'));
      },
    },
  ];

  /* ==================================================================
     The shell
     ================================================================== */
  function repaint() {
    if (!host) return;
    /* Every element that drew itself gets asked again, in the order it was
       added. Cheaper than rebuilding the chapter, and it keeps scroll
       position and slider focus -- dragging a slider that rebuilds its own
       parent loses the pointer after one pixel. */
    const walk = (node) => {
      if (node._paint) { try { node._paint(); } catch (e) { /* keep going */ } }
      for (const c of node.children || []) walk(c);
    };
    walk(host);
  }

  function show(i) {
    chapter = Math.max(0, Math.min(CHAPTERS.length - 1, i));
    const ch = CHAPTERS[chapter];
    host.innerHTML = '';
    host.appendChild(el('h3', { class: 'cfcg-h',
                                text: (chapter + 1) + '. ' + ch.title }));
    ch.build(host);
    host.scrollTop = 0;
    /* Twice, a frame apart: the canvases have no width until they are in
       the document, and a canvas sized from a zero-width rect draws
       nothing. */
    repaint();
    requestAnimationFrame(repaint);
    const nav = document.getElementById('cfcgNav');
    if (nav) {
      Array.from(nav.children).forEach((b, j) =>
        b.classList.toggle('on', j === chapter));
    }
    const foot = document.getElementById('cfcgWhere');
    if (foot) {
      foot.textContent = 'Chapter ' + (chapter + 1) + ' of '
                       + CHAPTERS.length;
    }
  }

  function open(id) {
    const wrap = el('div', { class: 'modal big cfcg' });

    wrap.appendChild(el('div', { class: 'mh' }, [
      el('h3', { text: 'What these panels are doing' }),
      el('span', { class: 'sub',
                   text: 'theta power, coupling, and the comodulogram '
                       + '— from the beginning' }),
      el('span', { class: 'spacer' }),
      el('button', { class: 'btn ghost sm', text: 'Close',
                     onclick: () => { host = null; closeModal(); } }),
    ]));

    wrap.appendChild(el('div', { class: 'cfcg-nav', id: 'cfcgNav' },
      CHAPTERS.map((c, i) => el('button', {
        class: 'mini', text: (i + 1) + '. ' + c.title,
        onclick: () => show(i),
      }))));

    host = el('div', { class: 'mb cfcg-body' });
    wrap.appendChild(host);

    wrap.appendChild(el('div', { class: 'mf' }, [
      el('span', { class: 'hint', id: 'cfcgWhere' }),
      el('span', { class: 'spacer' }),
      el('button', { class: 'btn ghost sm', text: '← Back',
                     onclick: () => show(chapter - 1) }),
      el('button', { class: 'btn sm', text: 'Next →',
                     onclick: () => show(chapter + 1) }),
    ]));

    showModal(wrap);
    const at = id ? CHAPTERS.findIndex((c) => c.id === id) : 0;
    show(at < 0 ? 0 : at);
    if (BARRY.activity) {
      BARRY.activity.log('cfcguide.open', { chapter: id || 'trace' });
    }
  }

  /* `repaint` is exported for the same reason `applyTheme` already calls
     `xplore.refreshAll()`: every canvas in here takes its colours from the
     CSS tokens, so a theme change has to repaint them by hand. There is no
     theme event in this application to listen for. */
  return { open, repaint, chapters: () => CHAPTERS.map((c) => c.id) };
})();
