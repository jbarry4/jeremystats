/* ==========================================================================
   monolith_joefigs.js -- the Monolith page's ninth tab: Joe's figures.

   Publication figures, in Nature's format, for what tab 8 found
   (Shahriar, 2026-10-21): broad first, then zooming in. Each result that
   changed gets its connectome (Precon1, Precon4 and the change; the
   increases, the decreases and both), each graph against its own
   within-session permutation null; then each follow-up that changed gets
   a figure of its own. backend/joefigs.py draws them with matplotlib (SVG,
   PDF, 600 dpi PNG); this page shows them with their legends, the files
   to download, and a Methods button that explains each one in words and
   with something to play with.
   ========================================================================== */
'use strict';

// window.MONO_FIGS is the figure library (js/monolith_figs.js); this is
// tab 9's own.
window.MONO_JOEFIGS = (function () {
  const M = () => window.MONO;
  const X = () => window.MONO_EXPLAIN;
  const NS = 'http://www.w3.org/2000/svg';
  // nullPick: which null each connectome shows, by figure id ('rats', the
  // main one, or 'trials'); a toggle on its card (2026-10-22).
  // hide: the groups (comparison|band) the filter grid has switched off.
  const HIDE_KEY = 'barry.joefigs.hide';
  const hideLoad = () => { try { return new Set(JSON.parse(localStorage.getItem(HIDE_KEY) || '[]')); } catch (e) { return new Set(); } };
  const P = { data: null, err: null, loading: false, seq: 0, making: false, makeNote: '', makeErr: null, open: new Set(), hide: hideLoad(),
              nullPick: {} };
  const $ = (id) => document.getElementById(id);
  const el = (...a) => M().el(...a);
  function sv(tag, attrs, text) {
    const n = document.createElementNS(NS, tag);
    for (const k in (attrs || {})) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || '#888';
  const reduced = () => { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } };
  const wait = (ms) => new Promise((r) => setTimeout(r, reduced() ? 0 : ms));
  const FILE = (name, save) => (window.MONO_STATIC ? 'data/joefigs/' + name
    : '/api/arc/monolith/joefigs/file/' + encodeURIComponent(name) + (save ? '?download=1' : ''));
  // The figures' own colours (backend/joefigs.py), so the animations match them.
  const C = { up: '#E66101', down: '#5E3C99', p1: '#8C8C8C', p4: '#1A1A1A', nul: '#D4D4D4' };
  const pSay = (p) => (p == null ? 'P = n/a' : p < 0.001 ? 'P < 0.001' : 'P = ' + p.toFixed(3));
  const stars = (p) => (p == null || p >= 0.05 ? '' : p < 0.001 ? '***' : p < 0.01 ? '**' : '*');
  const fmtN = (n) => Number(n).toLocaleString('en-US');

  function section(id, title, help, kids) {
    return el('div', { class: 'card', id }, [el('div', { class: 'hrow' }, [el('h2', { text: title }), help ? M().qh(help) : null])].concat(kids));
  }

  /* ---------------- data ---------------- */
  async function load() {
    const seq = ++P.seq;
    P.loading = true;
    render();
    try {
      const got = await M().getJSON('/data/joefigs');
      if (seq !== P.seq) return;
      P.data = got;
      P.err = null;
    } catch (e) {
      if (seq !== P.seq) return;
      P.data = null;
      P.err = e.message;
    }
    P.loading = false;
    render();
  }
  // onVacc: read the PAC profiles from the VACC's copies of the recordings
  // first (the data drive need not be connected), then draw.
  // mode: undefined (draw here), true (PAC on the VACC first) or 'fp' (the
  // FP comparison's fake trials measured on the VACC first).
  async function make(mode) {
    if (P.making) return;
    P.making = mode === 'fp' ? 'fp' : mode ? 'vacc' : 'here'; P.makeErr = null; P.makeNote = '';
    render();
    try {
      await M().runHere('/joefigs', mode === 'fp' ? { confirm: true, fp_vacc: true } : mode ? { confirm: true, vacc: true } : { confirm: true }, (note) => {
        P.makeNote = note;
        const b = mode === 'fp' ? $('figsfp') : mode ? ($('figsvacc') || $('figsvaccagain')) : $('figsmake');
        if (b) b.textContent = (mode === 'fp' ? 'Measuring FP on the VACC: ' : mode ? 'Reading on the VACC: ' : 'Drawing: ') + note;
      });
    } catch (e) {
      P.makeErr = /404|not found/i.test(e.message) ? 'Jarvis is running older code without this button: restart it, then press it again.'
        : 'It could not be done: ' + e.message;
    }
    P.making = false;
    load();
  }

  /* ---------------- the methods: words, and something to play with ---------------- */
  // Each figure names the methods behind it; each method is explained once,
  // in plain words first, then how the code does it and with what.
  const METHODS = {
    connectome: {
      title: 'The connectome',
      what: 'Each region is a dot on a ring, in the same order as the Monolith’s circuit: the right hemisphere down the right side, the left back up the left. Each pair of regions tested is a line between its dots. The line’s width is how much the pair’s coherence changed from the first window to the second, averaged over the rats; orange is an increase and purple a decrease. A ring of increases, one of decreases and one of both are drawn for Precon1, for Precon4, and for the change between them.',
      code: 'backend/joefigs.py, connectome(): for every session (a rat on a day), the mean over its trials of each window’s coherence, pair by pair (numpy.nanmean, so a trial that lost a wire to clipping is left out of that pair only); the change, second window minus first; the mean of those changes over the rats. The statistic of a ring is the sum of its edges: of the positive ones, of the negative ones, or of all. Drawn with matplotlib (a quadratic Bézier per edge).',
      means: 'A ring full of thick orange lines on Precon4 but not on Precon1 says the cue raised coherence across many pairs at once by Precon4. The sum is a single number for the whole network, so it can be significant when no single pair is.',
      toy: 'connectome',
    },
    ratflip: {
      title: 'Flipping each rat\u2019s sign (the main test)',
      what: 'The question tab 8\u2019s light answers is whether the rats changed together, so the rat is the unit. If nothing changed, each rat\u2019s change would be as likely to point up as down. So every one of the ways of flipping the sign of each rat\u2019s change is tried \u2014 with 8 rats, each up or down, 2\u2078 = 256 of them, the real one among them \u2014 and the ring\u2019s statistic computed for each. The share at least as extreme as the real one is its P.',
      code: 'backend/joefigs.py, rat_signs() and connectome(): itertools.product((+1, \u22121), repeat=rats) lists every sign pattern (sampled past 14 rats); each rat\u2019s per-pair change, multiplied by its sign, averaged over the rats (numpy.nanmean, so a rat without a pair is left out of that pair only), and summed into the ring\u2019s statistic; exact_p(): the share of patterns at least as extreme (no +1: the real one is already counted). Increases one-sided upward, decreases downward, both two-sided. Nothing is corrected.',
      means: 'With 8 rats the P comes in steps of 1/256 (0.004), and the smallest a two-sided P can be is 2/256, because flipping every rat gives the mirror image. This is the same unit as the mixed model behind tab 8\u2019s light, so the two agree when they should. The within-session shuffle, the other choice on the card, asks a different question: whether the change is bigger than trial-to-trial noise inside the sessions.',
      toy: 'ratflip',
    },
    fpnull: {
      title: 'FP intervals: the same change, with no cues',
      what: 'FP1 and FP2 are the same rats on the same days, recorded with no cues. A fake cue onset is put every 10 s of them, and round each the trial’s own windows (the baselines, cue 1, cue 2) are measured exactly as a real trial’s are. To make one fake data set, every session gets as many fake trials as it had real ones, drawn at random, each with its two windows in random order (with no cue, either can stand for it) and losing the windows the matching real trial lost to clipping, and the ring (or the follow-up’s change) is made from them exactly as the real one is. 10,000 such sets show what the rats’ coherence does between random moments when nothing happens; the real value’s rank among them is its P.',
      code: 'backend/joe.py, fp_pool_part(): the fake onsets (fp_onsets, every FP_POOL_STEP s, the windows at least 10 s from the recording’s ends), clipping measured with spark.clipping_windows, the wires and signals from coupling._signals_for_windows, every measure from measure(), as for a trial; run on the VACC’s copies of FP1 and FP2 (fp_pool_vacc_work). backend/joefigs.py, fp_per_rat(): each session’s fake trials drawn with replacement (numpy.random.default_rng, seeded), each in random order and masked with the real session’s own lost windows, the mean of the second windows minus the mean of the first, per rat and day; then the ring sums or the follow-up statistic, and perm_p() with its +1.',
      means: 'It asks whether the change at the cues is bigger than what happens between random moments of the same rats with no cues: a stricter yardstick than flipping signs, because it carries the brain’s own slow drift and moment-to-moment swings. FP was recorded before and after the cued session, so a slow change in state across the day also lands in it.',
      toy: 'fpnull',
    },
    permutation: {
      title: 'The within-session shuffle',
      what: 'If the cue did nothing, a trial’s baseline and cue windows would be interchangeable. So, inside each session, each trial’s two windows are swapped or left alone at random, which flips the sign of that trial’s change; the statistic is computed again; and that is done 10,000 times. The real value’s place among those 10,000 is its rank, and the share of shuffles at least as extreme (plus one, the real arrangement) is its P.',
      code: 'backend/joefigs.py, make_flips() and per_rat_changes(): numpy.random.default_rng with a fixed seed (20261021), 10,000 random true/false swaps per session, each trial swapped as a whole (every pair together, so the pairs keep their correlation); the means and changes recomputed for all 10,000 at once (numpy, vectorised); perm_p(): P = (1 + shuffles at least as extreme) / (10,000 + 1). Increases are one-sided upward, decreases downward, everything else two-sided. Nothing is corrected.',
      means: 'A rank near the top (or bottom) of the shuffles means the real change is bigger than trial-to-trial noise inside the same sessions produces. * P < 0.05, ** P < 0.01, *** P < 0.001.',
      toy: 'permutation',
    },
    coherence: {
      title: 'Coherence (Dickson 2022)',
      what: 'Coherence asks whether two regions’ rhythms keep a steady phase relationship. Cut both signals into overlapping pieces; in each piece, at each frequency, find the phase difference between them. If that difference is the same piece after piece, coherence is near 1; if it wanders, near 0.',
      code: 'backend/joe.py, _measure(): a 59–61 Hz Butterworth band-stop (scipy.signal.butter, order 1, run forwards and backwards with filtfilt); then numpy FFTs of hanning(1024) pieces with 512 overlap and 2,048 points, as MATLAB’s mscohere does in Jeremy’s code: coherence = |Sxy|² / (Sxx · Syy); averaged over the gamma bins, 30–90 Hz without 59–61 Hz.',
      means: 'Coherence counts any steady phase relationship, including one at zero lag, which a single source picked up by both wires (volume conduction) also makes. That is why the follow-ups ask PLI and imaginary coherence.',
      toy: 'phasor-coh',
    },
    pli: {
      title: 'Phase lag index (PLI)',
      what: 'PLI keeps only the direction of the phase difference: is one region ahead of the other more often than behind? A difference of exactly zero (or 180°), which volume conduction makes, counts for nothing.',
      code: 'backend/joe.py: each region filtered to the band and turned into its analytic signal (backend/sweep.py, analytic(): a zero-phase band-pass and scipy.signal.hilbert); the cross product of the two; PLI = |mean of the sign of its imaginary part| over the window.',
      means: 'A PLI that rises says the two regions settled into a consistent lead or lag, which a shared source at zero lag cannot fake.',
      toy: 'phasor-pli',
    },
    icoh: {
      title: 'Imaginary coherence',
      what: 'Coherency is the mean phase-difference arrow; its imaginary part is how far that arrow points off the zero-lag line. Coupling at exactly zero lag lies on that line and contributes nothing.',
      code: 'backend/joe.py: from the same Welch cross-spectrum as the circuits’ coherence (1 s Hann pieces, half overlapping), coherency = Sxy / √(Sxx · Syy); imaginary coherence = |mean over the band of its imaginary part|.',
      means: 'A rise in imaginary coherence is a rise in coupling with a time lag, so it is not volume conduction.',
      toy: 'phasor-icoh',
    },
    granger: {
      title: 'Granger causality',
      what: 'Does the past of region A help predict region B beyond B’s own past? If it does, A “Granger-causes” B. Asked both ways, it gives a direction.',
      code: 'backend/joe.py with backend/sweep.py: the signals down to 250 Hz, cut into 1 s pieces; their cross-spectral matrix; Wilson’s spectral factorisation (sweep.wilson) into a transfer function and noise covariance; spectral Granger causality both ways (sweep.granger), averaged over the band.',
      means: 'An arrow’s Granger value that grows from Precon1 to Precon4 says that region’s past predicts the other’s gamma better by then: information flowing that way, in the statistical sense (not proof of a connection).',
      toy: 'granger',
    },
    xcorr: {
      title: 'Amplitude cross-correlation',
      what: 'Take each region’s gamma loudness over time (its envelope). Slide one envelope past the other and correlate them at each shift. The best correlation is the peak; the shift where it happens is the lag, and a negative lag means the pair’s first region leads.',
      code: 'backend/joe.py, xcorr_lags(): the envelopes (|analytic signal|, sweep.analytic), mean removed; their correlation at every lag within ±100 ms through the FFT (numpy.fft, zero-padded so it is linear, not circular), normalised as MATLAB’s xcorr(x, y, ’coeff’); the peak and its lag (Adhikari et al. 2010, the lab’s Dickson method).',
      means: 'A higher peak says the two regions’ gamma bursts rise and fall together more; a lag that shifts says which one moves first has changed.',
      toy: 'xcorr',
    },
    pac: {
      title: 'Phase–amplitude coupling (PAC)',
      what: 'Is gamma louder at one part of the theta cycle than at others? Take theta’s phase in one region and gamma’s loudness in another (or the same); in each of 18 slices of the theta cycle, the mean gamma loudness. If gamma does not care about theta, the 18 bars are flat. The modulation index measures how far from flat they are. It is never a line graph: the figure shows each rat’s index as dots, and, where the recordings were read, the loudness around the cycle as rose plots and the comodulogram’s change.',
      code: 'backend/joe.py: theta phase (5–12 Hz) and gamma amplitude (30–90 Hz) from sweep.analytic; the mean amplitude in 18 phase bins, normalised to sum to 1; Tort’s modulation index = (log 18 − entropy) / log 18. backend/joefigs.py, pac_profiles(): the same profile and a comodulogram (phase 4–12 Hz in 2 Hz bands × amplitude 30–90 Hz in 10 Hz bands) from the recordings, through the very wires tab 8 chose.',
      means: 'A modulation index that rises says gamma is more tightly locked to theta’s cycle by Precon4; the roses show at which phase.',
      toy: 'pac',
    },
    follow: {
      title: 'A follow-up',
      what: 'For a result that changed, each pair that moved most was measured again with other measures, in the same windows and band. Each rat gives four values (Precon1 and Precon4, each window) and one change, (Precon4 second − first) − (Precon1 second − first). A one-sample t-test asks whether those changes average away from zero.',
      code: 'backend/joe.py, follow_test(): the per-rat values (numpy), t = mean / (s.d. / √n), P from scipy.stats.t, two-sided; the within-session shuffle beside it (backend/joefigs.py, follow_null()). Uncorrected, and the pair itself does not survive correction across all pairs: these are leads.',
      means: 'Read the dots, not only the P: most rats moving the same way is what makes a lead worth following.',
      toy: null,
    },
  };

  // The toys. Each draws into `host` and returns { play } when it moves.
  const TOYS = {
    permutation: (host, f) => permToy(host, f),
    ratflip: (host, f) => ratToy(host, f),
    fpnull: (host, f) => fpToy(host, f),
    connectome: (host, f) => connToy(host, f),
    'phasor-coh': (host) => phasorToy(host, 'coh'),
    'phasor-pli': (host) => phasorToy(host, 'pli'),
    'phasor-icoh': (host) => phasorToy(host, 'icoh'),
    granger: (host) => grangerToy(host),
    xcorr: (host) => xcorrToy(host),
    pac: (host) => (X() && X().pacToy ? X().pacToy(host, { k: 0.6 }) : null),
  };
  function player(host, steps, draw) {
    // Back / Play / Next over a list of step names; draw(k, quick) sets step k.
    let k = 0, run = 0;
    const cap = el('p', { class: 'xcap' });
    const chips = el('div', { class: 'xsteps' }, steps.map((s, i) => el('button', { type: 'button', class: 'xstep', text: s.name,
      onclick: () => { run++; go(i, true); } })));
    async function go(i, quick) {
      k = i;
      host.dataset.step = String(i);
      cap.textContent = steps[i].say;
      Array.from(chips.children).forEach((c, j) => c.setAttribute('aria-pressed', String(j === i)));
      await draw(i, quick || reduced());
    }
    async function play() {
      const tk = ++run;
      for (let i = 0; i < steps.length; i++) {
        if (tk !== run) return;
        await go(i, false);
        await wait(1300);
      }
    }
    const ctl = el('div', { class: 'xctl' }, [el('button', { type: 'button', class: 'xbtn', text: '▶ Play', onclick: () => play() }), chips]);
    go(0, true);
    return { play, cap, ctl, to: (i) => { run++; return go(i, true); }, get step() { return k; } };
  }

  // The within-session shuffle: one session's trials, swapped at random, a
  // null building up, and the real value landing in it (the figure's own
  // null when it has one).
  function permToy(host, f) {
    host.innerHTML = '';
    const VW = 360, VH = 230;
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', class: 'mfig fgperm', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': 'One session’s trials swapped at random, and the shuffles’ distribution' });
    const T = 8, base = [], cue = [];
    let seed = 7;
    const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    for (let t = 0; t < T; t++) { const b = 0.35 + 0.2 * rnd(); base.push(b); cue.push(b + 0.03 + 0.08 * (rnd() - 0.3)); }
    const g = sv('g', {});
    svg.appendChild(g);
    svg.appendChild(sv('text', { x: 8, y: 14, 'font-size': 11, fill: css('--ink-3') }, 'one session: each trial’s baseline and cue'));
    const bars = [];
    for (let t = 0; t < T; t++) {
      const x = 14 + t * 42;
      const rb = sv('rect', { x, width: 14, fill: C.p1, class: 'fgbase' });
      const rc = sv('rect', { x: x + 16, width: 14, fill: C.up, class: 'fgcue' });
      g.appendChild(rb); g.appendChild(rc);
      bars.push([rb, rc]);
    }
    const Y = (v) => 110 - v * 140;
    const setBars = (sw) => bars.forEach(([rb, rc], t) => {
      const [b, c] = sw[t] ? [cue[t], base[t]] : [base[t], cue[t]];
      rb.setAttribute('y', Y(b).toFixed(1)); rb.setAttribute('height', (110 - Y(b)).toFixed(1));
      rc.setAttribute('y', Y(c).toFixed(1)); rc.setAttribute('height', (110 - Y(c)).toFixed(1));
    });
    svg.appendChild(sv('line', { x1: 8, x2: VW - 8, y1: 110, y2: 110, stroke: css('--line-2') }));
    const out = sv('text', { x: 8, y: 128, 'font-size': 11, fill: css('--ink') }, '');
    svg.appendChild(out);
    // the null below
    const HB = 214, HT = 150;
    svg.appendChild(sv('line', { x1: 8, x2: VW - 8, y1: HB, y2: HB, stroke: css('--line-2') }));
    const hist = sv('g', { class: 'fghist' });
    svg.appendChild(hist);
    const real = sv('line', { y1: HT - 6, y2: HB, stroke: css('--ink'), 'stroke-width': 2, opacity: 0 });
    svg.appendChild(real);
    const say = sv('text', { x: VW - 8, y: HT - 10, 'text-anchor': 'end', 'font-size': 11, fill: css('--ink') }, '');
    svg.appendChild(say);
    const nul = f && f.null ? f.null : null;
    const lo = nul ? Math.min(nul.edges[0], f.obs) : -0.05, hi = nul ? Math.max(nul.edges[nul.edges.length - 1], f.obs) : 0.05;
    const HX = (v) => 8 + (v - lo) / ((hi - lo) || 1) * (VW - 16);
    const mean = (sw) => sw.reduce((s, x, t) => s + (x ? base[t] - cue[t] : cue[t] - base[t]), 0) / T;
    const counts = new Array(30).fill(0);
    const drawHist = (cs) => {
      hist.innerHTML = '';
      const mx = Math.max(1, ...cs);
      cs.forEach((c, i) => {
        const x0 = 8 + i * (VW - 16) / cs.length;
        const h = (HB - HT) * c / mx;
        hist.appendChild(sv('rect', { x: x0.toFixed(1), y: (HB - h).toFixed(1), width: ((VW - 16) / cs.length - 0.6).toFixed(1), height: h.toFixed(1), fill: C.nul }));
      });
    };
    const steps = [
      { name: 'One session', say: 'Each trial has a baseline (grey) and a cue (orange) value. Their mean change is the session’s change.' },
      { name: 'Swap at random', say: 'If the cue did nothing, each trial’s two windows could be swapped. Swap a random half: the change is recomputed.' },
      { name: '10,000 times', say: 'Do that 10,000 times, in every session at once: the changes the shuffles give pile up into a distribution.' },
      { name: 'Where it lands', say: 'The real value lands among them: its rank, and P, the share of shuffles at least as extreme.' },
    ];
    const pl = player(host, steps, async (k, quick) => {
      real.setAttribute('opacity', 0); say.textContent = '';
      if (k === 0) { setBars(new Array(T).fill(false)); out.textContent = 'session change: ' + mean(new Array(T).fill(false)).toFixed(3); drawHist(new Array(30).fill(0)); }
      if (k === 1) {
        for (let i = 0; i < (quick ? 1 : 4); i++) {
          const sw = Array.from({ length: T }, () => rnd() < 0.5);
          setBars(sw); out.textContent = 'shuffled change: ' + mean(sw).toFixed(3);
          await wait(450);
        }
      }
      if (k >= 2) {
        if (nul) { drawHist(nul.counts); } else {
          counts.fill(0);
          for (let i = 0; i < 400; i++) { const sw = Array.from({ length: T }, () => rnd() < 0.5); const m = mean(sw);
            counts[Math.max(0, Math.min(29, Math.floor((m + 0.05) / 0.1 * 30)))]++; }
          drawHist(counts);
        }
        out.textContent = nul ? 'the figure’s own 10,000 shuffles' : '400 shuffles of this one session';
      }
      if (k === 3 && f) {
        const x = HX(f.obs);
        real.setAttribute('x1', x.toFixed(1)); real.setAttribute('x2', x.toFixed(1));
        if (!quick) await X().tween(400, (t) => real.setAttribute('opacity', t.toFixed(2)), 'out'); else real.setAttribute('opacity', 1);
        say.textContent = 'rank ' + fmtN(f.rank) + ' of ' + fmtN(f.n) + ', ' + pSay(f.p) + (stars(f.p) ? ' ' + stars(f.p) : '');
      }
    });
    host.appendChild(el('div', { class: 'xplayer fgtoy', 'data-toy': 'permutation' }, [svg, pl.cap, pl.ctl]));
    return pl;
  }

  // The rat-level test: each rat's change, its sign flipped every way.
  // The rats are made up; the null it lands in is the figure's own.
  function ratToy(host, f) {
    host.innerHTML = '';
    const VW = 360, VH = 230;
    const N = f && f.n ? f.n : 256;
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', class: 'mfig fgrat', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': 'Each rat’s change with its sign flipped every way, and the distribution that gives' });
    const ch = [0.042, 0.031, 0.055, -0.012, 0.026, 0.038, 0.019, 0.047];
    const R = ch.length;
    svg.appendChild(sv('text', { x: 8, y: 14, 'font-size': 11, fill: css('--ink-3') }, 'each rat’s change (made up): their mean is the ring’s'));
    const Z = 66, K = 600;
    svg.appendChild(sv('line', { x1: 8, x2: VW - 8, y1: Z, y2: Z, stroke: css('--line-2') }));
    const bars = ch.map((_v, r) => {
      const b = sv('rect', { x: 18 + r * 42, width: 22, class: 'fgratbar' });
      svg.appendChild(b);
      svg.appendChild(sv('text', { x: 29 + r * 42, y: 116, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, 'rat ' + (r + 1)));
      return b;
    });
    const setBars = (sg) => bars.forEach((b, r) => {
      const v = ch[r] * sg[r];
      b.setAttribute('y', (v >= 0 ? Z - v * K : Z).toFixed(1));
      b.setAttribute('height', Math.abs(v * K).toFixed(1));
      b.setAttribute('fill', v >= 0 ? C.up : C.down);
    });
    const out = sv('text', { x: 8, y: 134, 'font-size': 11, fill: css('--ink') }, '');
    svg.appendChild(out);
    const HB = 214, HT = 150;
    svg.appendChild(sv('line', { x1: 8, x2: VW - 8, y1: HB, y2: HB, stroke: css('--line-2') }));
    const hist = sv('g', { class: 'fghist' });
    svg.appendChild(hist);
    const real = sv('line', { y1: HT - 6, y2: HB, stroke: css('--ink'), 'stroke-width': 2, opacity: 0 });
    svg.appendChild(real);
    const say = sv('text', { x: VW - 8, y: HT - 10, 'text-anchor': 'end', 'font-size': 11, fill: css('--ink') }, '');
    svg.appendChild(say);
    const nul = f && f.null ? f.null : null;
    const lo = nul ? Math.min(nul.edges[0], f.obs) : -0.05, hi = nul ? Math.max(nul.edges[nul.edges.length - 1], f.obs) : 0.05;
    const HX = (v) => 8 + (v - lo) / ((hi - lo) || 1) * (VW - 16);
    const mean = (sg) => ch.reduce((a, v, r) => a + v * sg[r], 0) / R;
    const sgn = (v) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(3);
    const drawHist = (cs) => {
      hist.innerHTML = '';
      const mx = Math.max(1, ...cs);
      cs.forEach((c, i) => {
        const x0 = 8 + i * (VW - 16) / cs.length;
        const h = (HB - HT) * c / mx;
        hist.appendChild(sv('rect', { x: x0.toFixed(1), y: (HB - h).toFixed(1), width: ((VW - 16) / cs.length - 0.6).toFixed(1), height: h.toFixed(1), fill: C.nul }));
      });
    };
    // Every one of the toy's own 2^8 patterns, for when the figure has no null.
    const own = () => {
      const cs = new Array(30).fill(0);
      for (let m = 0; m < (1 << R); m++) {
        const v = mean(ch.map((_x, r) => ((m >> r) & 1 ? -1 : 1)));
        cs[Math.max(0, Math.min(29, Math.floor((v + 0.05) / 0.1 * 30)))]++;
      }
      return cs;
    };
    const steps = [
      { name: 'Each rat', say: 'Each rat has its own change, up (orange) or down (purple). Their mean is what the ring shows.' },
      { name: 'Flip some', say: 'If nothing changed, each rat’s change was as likely to point the other way. Flip some rats’ signs and take the mean again.' },
      { name: 'Every way', say: 'With 8 rats, each up or down, there are 2⁸ = 256 ways to flip them, the real one among them. Every one is tried, and their values pile up.' },
      { name: 'Where it lands', say: 'The real value lands among them: its rank, and P, the share of the ' + fmtN(N) + ' at least as extreme.' },
    ];
    let seed = 11;
    const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    const pl = player(host, steps, async (k, quick) => {
      real.setAttribute('opacity', 0); say.textContent = '';
      if (k === 0) { const one = ch.map(() => 1); setBars(one); out.textContent = 'mean over the rats: ' + sgn(mean(one)); drawHist(new Array(30).fill(0)); }
      if (k === 1) {
        for (let i = 0; i < (quick ? 1 : 4); i++) {
          const sg = ch.map(() => (rnd() < 0.5 ? -1 : 1));
          setBars(sg); out.textContent = 'flipped: ' + sg.filter((x) => x < 0).length + ' rats, mean ' + sgn(mean(sg));
          await wait(450);
        }
      }
      if (k >= 2) {
        setBars(ch.map(() => 1));
        drawHist(nul ? nul.counts : own());
        out.textContent = nul ? 'the figure’s own ' + fmtN(N) + ' sign patterns' : 'all 256 sign patterns of these rats';
      }
      if (k === 3 && f) {
        const x = HX(f.obs);
        real.setAttribute('x1', x.toFixed(1)); real.setAttribute('x2', x.toFixed(1));
        if (!quick) await X().tween(400, (t) => real.setAttribute('opacity', t.toFixed(2)), 'out'); else real.setAttribute('opacity', 1);
        say.textContent = 'rank ' + fmtN(f.rank) + ' of ' + fmtN(f.n) + ', ' + pSay(f.p) + (stars(f.p) ? ' ' + stars(f.p) : '');
      }
    });
    host.appendChild(el('div', { class: 'xplayer fgtoy', 'data-toy': 'ratflip' }, [svg, pl.cap, pl.ctl]));
    return pl;
  }

  // The FP comparison: fake trials at random moments of FP1 and FP2 (no
  // cues), measured as trials are. The null it lands in is the figure's own.
  function fpToy(host, f) {
    host.innerHTML = '';
    const VW = 360, VH = 230;
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', class: 'mfig fgfptoy', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': 'Fake trials at random moments of FP1 and FP2, and the distribution they give' });
    const recs = [{ name: 'FP1', x0: 40, x1: 190 }, { name: 'FP2', x0: 200, x1: 350 }];
    const Y0 = 34, BH = 14;
    for (const r of recs) {
      svg.appendChild(sv('rect', { x: r.x0, y: Y0, width: r.x1 - r.x0, height: BH, fill: '#E6E6E6' }));
      svg.appendChild(sv('text', { x: r.x0, y: Y0 - 5, 'font-size': 10, fill: css('--ink-3') }, r.name + ', no cues'));
    }
    const fake = sv('g', {});
    svg.appendChild(fake);
    const out = sv('text', { x: 8, y: 84, 'font-size': 11, fill: css('--ink') }, '');
    svg.appendChild(out);
    const sub = sv('text', { x: 8, y: 100, 'font-size': 10, fill: css('--ink-3') }, '');
    svg.appendChild(sub);
    const HB = 214, HT = 150;
    svg.appendChild(sv('line', { x1: 8, x2: VW - 8, y1: HB, y2: HB, stroke: css('--line-2') }));
    const hist = sv('g', { class: 'fghist' });
    svg.appendChild(hist);
    const real = sv('line', { y1: HT - 6, y2: HB, stroke: css('--ink'), 'stroke-width': 2, opacity: 0 });
    svg.appendChild(real);
    const say = sv('text', { x: VW - 8, y: HT - 10, 'text-anchor': 'end', 'font-size': 11, fill: css('--ink') }, '');
    svg.appendChild(say);
    const nul = f && f.null ? f.null : null;
    const lo = nul ? Math.min(nul.edges[0], f.obs) : -0.05, hi = nul ? Math.max(nul.edges[nul.edges.length - 1], f.obs) : 0.05;
    const HX = (v) => 8 + (v - lo) / ((hi - lo) || 1) * (VW - 16);
    const drawHist = (cs) => {
      hist.innerHTML = '';
      const mx = Math.max(1, ...cs);
      cs.forEach((c, i) => {
        const x0 = 8 + i * (VW - 16) / cs.length;
        const h = (HB - HT) * c / mx;
        hist.appendChild(sv('rect', { x: x0.toFixed(1), y: (HB - h).toFixed(1), width: ((VW - 16) / cs.length - 0.6).toFixed(1), height: h.toFixed(1), fill: '#0072B2', opacity: 0.55 }));
      });
    };
    let seed = 5;
    const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    const drop = (n) => {
      fake.innerHTML = '';
      const got = [];
      for (let i = 0; i < n; i++) {
        const r = recs[rnd() < 0.5 ? 0 : 1];
        const x = r.x0 + 12 + rnd() * (r.x1 - r.x0 - 24);
        fake.appendChild(sv('rect', { x: (x - 10).toFixed(1), y: Y0, width: 10, height: BH, fill: '#9A9A9A', class: 'fgfakebase' }));
        fake.appendChild(sv('rect', { x: x.toFixed(1), y: Y0, width: 10, height: BH, fill: '#E66101', class: 'fgfakecue' }));
        got.push(0.02 * (rnd() - 0.5));
      }
      return got;
    };
    const steps = [
      { name: 'FP', say: 'FP1 and FP2 are the same rats on the same days, with no cues.' },
      { name: 'A fake trial', say: 'Pretend a cue started at a random moment: the trial’s own windows round it, measured as a real trial is. Its “change” is pure chance.' },
      { name: 'A set', say: 'Each session gets as many fake trials as it had real ones; the set’s ring (or change) is made exactly as the real one is.' },
      { name: '10,000 sets', say: 'Do that 10,000 times: what the same rats’ coherence does without cues piles up into a distribution.' },
      { name: 'Where it lands', say: 'The real value lands among them: its rank, and P, the share of sets at least as extreme.' },
    ];
    const pl = player(host, steps, async (k, quick) => {
      real.setAttribute('opacity', 0); say.textContent = '';
      if (k === 0) { fake.innerHTML = ''; out.textContent = ''; sub.textContent = ''; drawHist(new Array(30).fill(0)); }
      if (k === 1) {
        for (let i = 0; i < (quick ? 1 : 3); i++) {
          const g = drop(1);
          out.textContent = 'fake trial: change ' + (g[0] >= 0 ? '+' : '−') + Math.abs(g[0]).toFixed(3);
          sub.textContent = 'grey: its baseline; orange: its “cue”';
          await wait(500);
        }
      }
      if (k === 2) {
        const g = drop(12);
        const m = g.reduce((a, b) => a + b, 0) / g.length;
        out.textContent = 'one set: 12 fake trials, mean change ' + (m >= 0 ? '+' : '−') + Math.abs(m).toFixed(3);
        sub.textContent = '';
      }
      if (k >= 3) {
        drawHist(nul ? nul.counts : new Array(30).fill(0).map((_c, i) => Math.round(100 * Math.exp(-((i - 14.5) ** 2) / 30))));
        out.textContent = nul ? 'the figure’s own ' + fmtN(f.n - 1) + ' FP sets' : '10,000 FP sets';
      }
      if (k === 4 && f) {
        const x = HX(f.obs);
        real.setAttribute('x1', x.toFixed(1)); real.setAttribute('x2', x.toFixed(1));
        if (!quick) await X().tween(400, (t) => real.setAttribute('opacity', t.toFixed(2)), 'out'); else real.setAttribute('opacity', 1);
        say.textContent = 'rank ' + fmtN(f.rank) + ' of ' + fmtN(f.n) + ', ' + pSay(f.p) + (stars(f.p) ? ' ' + stars(f.p) : '');
      }
    });
    host.appendChild(el('div', { class: 'xplayer fgtoy', 'data-toy': 'fpnull' }, [svg, pl.cap, pl.ctl]));
    return pl;
  }

  // The connectome's statistic: the figure's own edges, split and summed.
  function connToy(host, fig) {
    host.innerHTML = '';
    const st = (fig && fig.stats) || {};
    const regions = (P.data && P.data.regions) || [];
    // The ring small enough that its right-hand names stop short of the sums.
    const VW = 360, VH = 260, CX = 130, CY = 128, RR = 80;
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', class: 'mfig fgconn', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': 'The connectome’s edges, split into increases and decreases and summed' });
    const pos = regions.map((_r, i) => { const a = -Math.PI / 2 + (i + 0.5) * 2 * Math.PI / regions.length; return [CX + RR * Math.cos(a), CY + RR * Math.sin(a)]; });
    svg.appendChild(sv('circle', { cx: CX, cy: CY, r: RR, fill: 'none', stroke: css('--line'), 'stroke-width': 1 }));
    const eg = sv('g', {});
    svg.appendChild(eg);
    pos.forEach(([x, y], i) => {
      svg.appendChild(sv('circle', { cx: x, cy: y, r: 4, fill: '#fff', stroke: '#1A1A1A', 'stroke-width': 1 }));
      svg.appendChild(sv('text', { x: CX + (x - CX) * 1.22, y: CY + (y - CY) * 1.18 + 3, 'font-size': 9, 'text-anchor': x > CX + 8 ? 'start' : x < CX - 8 ? 'end' : 'middle',
                                   fill: css('--ink-2') }, regions[i]));
    });
    const sums = sv('g', {});
    svg.appendChild(sums);
    const pairIdx = (name) => { const [a, b] = name.split(' – '); return [regions.indexOf(a), regions.indexOf(b)]; };
    const row = (key) => ((st.edges || {})[key] || []).map((v, i) => [pairIdx((st.pairs || [])[i] || ''), v]).filter(([ij, v]) => v != null && ij[0] >= 0 && ij[1] >= 0);
    const draw = (key, kind) => {
      eg.innerHTML = '';
      const es = row(key);
      const mx = Math.max(1e-9, ...es.map(([, v]) => Math.abs(v)));
      for (const [[i, j], v] of es.sort((a, b) => Math.abs(a[1]) - Math.abs(b[1]))) {
        if ((kind === 'pos' && v <= 0) || (kind === 'neg' && v >= 0)) continue;
        const [x0, y0] = pos[i], [x1, y1] = pos[j];
        const qx = CX + ((x0 + x1) / 2 - CX) * 0.35, qy = CY + ((y0 + y1) / 2 - CY) * 0.35;
        eg.appendChild(sv('path', { d: 'M' + x0 + ',' + y0 + ' Q' + qx + ',' + qy + ' ' + x1 + ',' + y1, fill: 'none',
          stroke: v > 0 ? C.up : C.down, 'stroke-width': (0.5 + 3.5 * Math.abs(v) / mx).toFixed(2), 'stroke-opacity': 0.9, class: 'fgedge' }));
      }
      return es;
    };
    const bar = (es) => {
      sums.innerHTML = '';
      const pos_ = es.reduce((s, [, v]) => s + Math.max(0, v), 0), neg = es.reduce((s, [, v]) => s + Math.min(0, v), 0);
      const mx = Math.max(1e-9, pos_, -neg, Math.abs(pos_ + neg));
      const X0 = 262, W0 = 90;
      [['increases', pos_, C.up], ['decreases', neg, C.down], ['both', pos_ + neg, css('--ink')]].forEach(([t, v, col], k) => {
        const y = 70 + k * 46;
        sums.appendChild(sv('text', { x: X0, y: y - 6, 'font-size': 10, fill: css('--ink-2') }, t));
        sums.appendChild(sv('rect', { x: X0, y, width: Math.max(1, W0 * Math.abs(v) / mx).toFixed(1), height: 10, fill: col }));
        sums.appendChild(sv('text', { x: X0, y: y + 22, 'font-size': 10, fill: css('--ink') }, (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(3)));
      });
    };
    const steps = [
      { name: 'Precon1', say: 'Precon1: each line is a pair, its width the mean change in coherence from the first window to the second; orange up, purple down.' },
      { name: 'Precon4', say: 'Precon4: the same pairs, the same windows.' },
      { name: 'The change', say: 'Precon4 − Precon1: how much more each pair changed by Precon4.' },
      { name: 'Summed', say: 'Each ring becomes one number: the sum of its increases, of its decreases, or of both. That number is what the shuffles test.' },
    ];
    const pl = player(host, steps, async (k) => {
      sums.innerHTML = '';
      const key = k === 0 ? 'Precon1' : k === 1 ? 'Precon4' : 'delta';
      const es = draw(key, 'net');
      if (k === 3) bar(es);
    });
    host.appendChild(el('div', { class: 'xplayer fgtoy', 'data-toy': 'connectome' }, [svg, pl.cap, pl.ctl]));
    return pl;
  }

  // Phase-difference arrows on a circle: coherence is the mean arrow's
  // length; PLI how lopsided they are about the zero-lag line; imaginary
  // coherence the mean arrow's height off that line.
  function phasorToy(host, mode) {
    host.innerHTML = '';
    const VW = 360, VH = 220, CX = 110, CY = 112, RR = 86;
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', class: 'mfig fgphasor', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': 'Each piece’s phase difference as an arrow, and their mean' });
    svg.appendChild(sv('circle', { cx: CX, cy: CY, r: RR, fill: 'none', stroke: css('--line'), 'stroke-width': 1 }));
    svg.appendChild(sv('line', { x1: CX - RR - 8, x2: CX + RR + 8, y1: CY, y2: CY, stroke: css('--line-2'), 'stroke-dasharray': '3 2' }));
    svg.appendChild(sv('text', { x: CX + RR + 10, y: CY + 4, 'font-size': 9, fill: css('--ink-3') }, 'zero lag'));
    const ag = sv('g', {});
    svg.appendChild(ag);
    const mean = sv('line', { x1: CX, y1: CY, stroke: C.up, 'stroke-width': 3.5, 'stroke-linecap': 'round' });
    svg.appendChild(mean);
    const out = sv('text', { x: 222, y: 60, 'font-size': 12, fill: css('--ink'), 'font-weight': 600 }, '');
    const out2 = sv('text', { x: 222, y: 80, 'font-size': 10, fill: css('--ink-2') }, '');
    svg.appendChild(out); svg.appendChild(out2);
    let seed = 11;
    const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    const set = (center, spread, n) => Array.from({ length: n }, () => center + spread * (rnd() - 0.5) * 2);
    const draw = (angles) => {
      ag.innerHTML = '';
      let sx = 0, sy = 0, sgn = 0;
      for (const a of angles) {
        const x = CX + RR * 0.92 * Math.cos(a), y = CY - RR * 0.92 * Math.sin(a);
        ag.appendChild(sv('line', { x1: CX, y1: CY, x2: x.toFixed(1), y2: y.toFixed(1), stroke: C.p1, 'stroke-width': 1, 'stroke-opacity': 0.7 }));
        sx += Math.cos(a); sy += Math.sin(a); sgn += Math.sign(Math.sin(a));
      }
      const n = angles.length;
      const mx = sx / n, my = sy / n;
      mean.setAttribute('x2', (CX + RR * mx).toFixed(1));
      mean.setAttribute('y2', (CY - RR * my).toFixed(1));
      const coh = Math.hypot(mx, my), ic = Math.abs(my), pli = Math.abs(sgn / n);
      if (mode === 'coh') { out.textContent = 'coherence ≈ ' + coh.toFixed(2); out2.textContent = 'the mean arrow’s length'; }
      if (mode === 'icoh') { out.textContent = 'imaginary ≈ ' + ic.toFixed(2); out2.textContent = 'the mean arrow’s height off zero lag'; }
      if (mode === 'pli') { out.textContent = 'PLI ≈ ' + pli.toFixed(2); out2.textContent = 'how many more point up than down'; }
    };
    const steps = [
      { name: 'Wandering', say: 'Piece after piece, the phase difference wanders all around the circle: the arrows cancel and every measure is near 0.' },
      { name: 'Locked, with a lag', say: 'The phase difference holds near 60°: the mean arrow is long (coherence), points off the zero-lag line (imaginary coherence) and almost all arrows point up (PLI).' },
      { name: 'Locked at zero', say: 'One source seen by both wires locks the difference at 0°: coherence is high, but the arrows lie on the zero-lag line, so imaginary coherence and PLI stay near 0.' },
    ];
    const sets = [set(0, Math.PI, 40), set(Math.PI / 3, 0.5, 40), set(0, 0.12, 40)];
    const pl = player(host, steps, async (k) => { draw(sets[k]); });
    host.appendChild(el('div', { class: 'xplayer fgtoy', 'data-toy': 'phasor-' + mode }, [svg, pl.cap, pl.ctl]));
    return pl;
  }

  // Granger: predicting B from its own past, then with A's past too.
  function grangerToy(host) {
    host.innerHTML = '';
    const VW = 360, VH = 200;
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', class: 'mfig fggranger', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': 'Predicting one signal from its own past, and from the other’s past too' });
    const N = 120;
    let seed = 5;
    const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647 - 0.5; };
    const a = [], b = [];
    for (let i = 0; i < N; i++) { a.push((i ? 0.6 * a[i - 1] : 0) + rnd()); b.push((i > 2 ? 0.3 * b[i - 1] + 0.8 * a[i - 3] : 0) + 0.4 * rnd()); }
    const X0 = 20, XW = 320;
    const path = (v, y0, sc) => v.map((x, i) => (i ? 'L' : 'M') + (X0 + i * XW / N).toFixed(1) + ',' + (y0 - x * sc).toFixed(1)).join(' ');
    svg.appendChild(sv('text', { x: 4, y: 18, 'font-size': 10, fill: css('--ink-3') }, 'A'));
    svg.appendChild(sv('text', { x: 4, y: 88, 'font-size': 10, fill: css('--ink-3') }, 'B'));
    svg.appendChild(sv('path', { d: path(a, 30, 18), fill: 'none', stroke: C.p1, 'stroke-width': 1.2 }));
    svg.appendChild(sv('path', { d: path(b, 100, 18), fill: 'none', stroke: C.p4, 'stroke-width': 1.2 }));
    const pred = sv('path', { fill: 'none', stroke: C.up, 'stroke-width': 1.2, 'stroke-dasharray': '3 2' });
    svg.appendChild(pred);
    const errBar = sv('rect', { x: X0, y: 160, height: 12, fill: C.down });
    svg.appendChild(errBar);
    const out = sv('text', { x: X0, y: 154, 'font-size': 10, fill: css('--ink') }, '');
    svg.appendChild(out);
    const own = b.map((_x, i) => (i ? 0.3 * b[i - 1] : 0));
    const both = b.map((_x, i) => (i > 2 ? 0.3 * b[i - 1] + 0.8 * a[i - 3] : 0));
    const err = (p) => b.reduce((s, x, i) => s + (x - p[i]) ** 2, 0) / N;
    const e1 = err(own), e2 = err(both);
    const steps = [
      { name: 'Own past', say: 'Predict B from its own past alone (dashed): the misses are large.' },
      { name: 'With A’s past', say: 'Add A’s past: the prediction tracks B far better, because B echoes A three samples later.' },
      { name: 'Granger', say: 'Granger causality A → B is the log of how much the error shrank: ln(' + e1.toFixed(2) + ' / ' + e2.toFixed(2) + ') = ' + Math.log(e1 / e2).toFixed(2) + '. Asked the other way, B → A, it stays near 0.' },
    ];
    const pl = player(host, steps, async (k) => {
      const p = k === 0 ? own : both;
      pred.setAttribute('d', path(p, 100, 18));
      const e = k === 0 ? e1 : e2;
      errBar.setAttribute('width', Math.max(1, 200 * e / e1).toFixed(1));
      out.textContent = k === 2 ? 'Granger A → B = ' + Math.log(e1 / e2).toFixed(2) : 'prediction error ' + e.toFixed(2);
    });
    host.appendChild(el('div', { class: 'xplayer fgtoy', 'data-toy': 'granger' }, [svg, pl.cap, pl.ctl]));
    return pl;
  }

  // Amplitude cross-correlation: one envelope slid past the other.
  function xcorrToy(host) {
    host.innerHTML = '';
    const VW = 360, VH = 220, N = 160, LAG = 9;
    const svg = sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', class: 'mfig fgxcorr', role: 'img', style: 'max-width:' + VW + 'px',
                            'aria-label': 'Two gamma envelopes, one slid past the other, and their correlation at each shift' });
    let seed = 3;
    const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    const base = [];
    for (let i = 0; i < N + 40; i++) base.push(0.5 + 0.45 * Math.sin(i / 7) * Math.sin(i / 23) + 0.15 * rnd());
    const a = base.slice(20, 20 + N), b = base.slice(20 - LAG, 20 - LAG + N);
    const X0 = 16, XW = 328;
    const pth = (v, y0, dx) => v.map((x, i) => (i ? 'L' : 'M') + (X0 + (i + dx) * XW / N).toFixed(1) + ',' + (y0 - x * 40).toFixed(1)).join(' ');
    svg.appendChild(sv('path', { d: pth(a, 60, 0), fill: 'none', stroke: C.p1, 'stroke-width': 1.3 }));
    const bp = sv('path', { fill: 'none', stroke: C.up, 'stroke-width': 1.3 });
    svg.appendChild(bp);
    svg.appendChild(sv('text', { x: X0, y: 12, 'font-size': 10, fill: css('--ink-3') }, 'first region’s envelope (grey), second’s (orange)'));
    const corr = (s) => { let n = 0, sa = 0, sb = 0, sab = 0, saa = 0, sbb = 0;
      for (let i = 0; i < N; i++) { const j = i + s; if (j < 0 || j >= N) continue; n++; sa += a[i]; sb += b[j]; }
      const ma = sa / n, mb = sb / n;
      for (let i = 0; i < N; i++) { const j = i + s; if (j < 0 || j >= N) continue; sab += (a[i] - ma) * (b[j] - mb); saa += (a[i] - ma) ** 2; sbb += (b[j] - mb) ** 2; }
      return sab / Math.sqrt(saa * sbb); };
    const lags = []; for (let s = -20; s <= 20; s++) lags.push([s, corr(s)]);
    const CX0 = 40, CW = 280, CB = 200, CT = 120;
    const cx = (s) => CX0 + (s + 20) / 40 * CW, cy = (r) => CB - Math.max(0, r) * (CB - CT);
    svg.appendChild(sv('line', { x1: CX0, x2: CX0 + CW, y1: CB, y2: CB, stroke: css('--line-2') }));
    svg.appendChild(sv('line', { x1: cx(0), x2: cx(0), y1: CT - 4, y2: CB, stroke: css('--line-2'), 'stroke-dasharray': '2 2' }));
    svg.appendChild(sv('text', { x: cx(0), y: CB + 12, 'font-size': 9, 'text-anchor': 'middle', fill: css('--ink-3') }, '0'));
    const cpath = sv('path', { fill: 'none', stroke: css('--ink'), 'stroke-width': 1.4 });
    svg.appendChild(cpath);
    const dot = sv('circle', { r: 4, fill: C.up });
    svg.appendChild(dot);
    const out = sv('text', { x: CX0 + CW, y: CT - 6, 'text-anchor': 'end', 'font-size': 10, fill: css('--ink') }, '');
    svg.appendChild(out);
    const best = lags.reduce((m, x) => (x[1] > m[1] ? x : m), lags[0]);
    const steps = [
      { name: 'Two envelopes', say: 'The gamma loudness of each region over time; the second follows the first a little later.' },
      { name: 'Slide', say: 'Slide the second past the first and correlate them at every shift, within ±100 ms.' },
      { name: 'Peak and lag', say: 'The best correlation is the peak; its shift is the lag. Here the first region leads, so the lag is negative.' },
    ];
    const pl = player(host, steps, async (k, quick) => {
      if (k === 0) { bp.setAttribute('d', pth(b, 60, 0)); cpath.setAttribute('d', ''); dot.setAttribute('opacity', 0); out.textContent = ''; }
      if (k >= 1) {
        const upto = k === 1 && !quick ? lags.length : lags.length;
        for (let i = 1; i <= upto; i++) {
          const s = lags[i - 1][0];
          bp.setAttribute('d', pth(b, 60, -s));
          cpath.setAttribute('d', lags.slice(0, i).map(([l, r], j) => (j ? 'L' : 'M') + cx(l).toFixed(1) + ',' + cy(r).toFixed(1)).join(' '));
          if (k === 1 && !quick) await wait(40);
        }
      }
      if (k === 2) {
        bp.setAttribute('d', pth(b, 60, -best[0]));
        dot.setAttribute('cx', cx(best[0]).toFixed(1)); dot.setAttribute('cy', cy(best[1]).toFixed(1)); dot.setAttribute('opacity', 1);
        out.textContent = 'peak r = ' + best[1].toFixed(2) + ' at lag ' + (-LAG) + ' samples';
      }
    });
    host.appendChild(el('div', { class: 'xplayer fgtoy', 'data-toy': 'xcorr' }, [svg, pl.cap, pl.ctl]));
    return pl;
  }

  function methodsPanel(f) {
    const box = el('div', { class: 'fgmethods', id: 'fgm-' + f.id.replace('.', '_') });
    for (const key of f.methods || []) {
      const m = METHODS[key];
      if (!m) continue;
      const sec = el('div', { class: 'fgmethod', 'data-method': key }, [
        el('h4', { text: m.title }),
        el('p', { class: 'small', text: m.what }),
        el('p', { class: 'small fgcode' }, [el('b', { text: 'How the code does it. ' }), m.code]),
        el('p', { class: 'small' }, [el('b', { text: 'What it means. ' }), m.means]),
      ]);
      if (m.toy && TOYS[m.toy]) {
        const host = el('div', { class: 'fgtoyhost' });
        sec.appendChild(host);
        // The permutation toy plays the figure's own null where there is one.
        let feed = null;
        if (key === 'permutation' || key === 'ratflip' || key === 'fpnull') {
          if (f.kind === 'connectome') {
            const g = (f.stats.graphs || []).find((x) => x.row === 'delta' && x.kind === 'pos') || (f.stats.graphs || [])[0];
            feed = g ? { null: g.null, obs: g.stat, rank: g.rank, n: g.n, p: g.p } : null;
          } else {
            const k = (f.keys || [])[0];
            const nl = k ? (key === 'fpnull' ? (f.stats.nulls_fp || {})[k] : (f.stats.nulls || {})[k]) : null;
            feed = nl ? { null: nl.null, obs: nl.obs, rank: nl.rank, n: nl.n, p: nl.p } : null;
          }
        }
        const piece = TOYS[m.toy](host, key === 'connectome' ? f : feed);
        if (piece && piece.play) X().playOnce('fg-' + f.id + '-' + key, host, piece);
      }
      box.appendChild(sec);
    }
    return box;
  }

  /* ---------------- the figures ---------------- */
  // A follow-up measure's name, with its pair's regions (as the figure says it).
  function measureSay(k, f) {
    const a = f.a, b = f.b;
    return { pli: 'PLI', icoh: 'Imaginary coherence', gc_ab: 'Granger ' + a + ' → ' + b, gc_ba: 'Granger ' + b + ' → ' + a,
             xlag: 'Amplitude lag', xpeak: 'Amplitude cross-correlation peak', pac_ab: 'PAC ' + a + ' θ → ' + b + ' γ',
             pac_ba: 'PAC ' + b + ' θ → ' + a + ' γ', pac_aa: 'PAC within ' + a, pac_bb: 'PAC within ' + b }[k] || k;
  }
  /* A connectome as its picked null shows it: the main one (the rats'
     sign flips, what lit tab 8's light) or `alt` (the trials swapped
     within each session). Everything else about the figure is shared. */
  function viewOf(f0) {
    const pick = P.nullPick[f0.id];
    const a = f0.kind === 'connectome' && pick && pick !== f0.null ? (f0.alts || []).find((x) => x.null === pick) : null;
    if (!a) return f0;
    return Object.assign({}, f0, { files: a.files, legend: a.legend, methods: a.methods || f0.methods,
                                   null: a.null, null_say: a.null_say, null_why: a.null_why,
                                   stats: Object.assign({}, f0.stats, a.stats) });
  }

  function figCard(f0, into) {
    const f = viewOf(f0);
    const label = f.kind === 'schematic' ? 'Supplementary Figure ' + f.no : 'Figure ' + f.no;
    const card = into || el('div', { class: 'card fgcard', id: 'fig-' + f.id.replace('.', '_'), 'data-fig': f.id, 'data-kind': f.kind,
                                      'data-group': f0.group ? f0.group.key : '' });
    if (!into && f0.group && P.hide.has(f0.group.key)) card.hidden = true;
    card.innerHTML = '';
    card.appendChild(el('div', { class: 'hrow' }, [el('h3', {}, [el('span', { class: 'fgno', text: label + ' | ' }), f.legend.title])]));
    /* Which null the rings are tested against (2026-10-22: "a flip-flop
       option between these two, and make what got the light green the
       main one"). */
    if (f0.kind === 'connectome' && (f0.alts || []).length) {
      const pick = f0.alts.some((x) => x.null === P.nullPick[f0.id]) ? P.nullPick[f0.id] : f0.null;
      const sayOf = (id, say) => (id === 'rats' ? say + ' (the light\u2019s test)' : say);
      const opt = (id, text, why) => el('button', { type: 'button', class: pick === id ? 'active' : null, 'data-null': id,
        'aria-pressed': String(pick === id), title: why, text,
        onclick: () => { if (pick !== id) { P.nullPick[f0.id] = id; figCard(f0, card); } } });
      card.appendChild(el('div', { class: 'hrow fgnull' }, [
        el('span', { class: 'small muted', text: 'Tested against' }),
        el('div', { class: 'seg', role: 'group', 'aria-label': 'Which null the rings are tested against' }, [
          opt(f0.null, sayOf(f0.null, f0.null_say || f0.null), f0.null_why || ''),
        ].concat(f0.alts.map((a) => opt(a.null, sayOf(a.null, a.null_say), a.null_why || '')))),
      ]));
    }
    card.appendChild(el('div', { class: 'fgimg' }, [el('img', { src: FILE(f.files.svg), alt: f.legend.title, loading: 'lazy', class: 'fgsvg' })]));
    // The numbers that matter, said once more under the picture.
    const chips = el('div', { class: 'fgstats' });
    if (f.kind === 'schematic') {
      const st = f.stats || {};
      for (const [k, say] of [['effect1', 'Precon1 cue effect'], ['effect4', 'Precon4 cue effect'], ['change', 'change in cue effect']]) {
        if (st[k] != null) chips.appendChild(el('span', { class: 'fgchip', 'data-key': k, text: say + ': ' + (st[k] >= 0 ? '+' : '\u2212') + Math.abs(st[k]).toFixed(3) }));
      }
    } else if (f.kind === 'connectome') {
      for (const g of f.stats.graphs) {
        chips.appendChild(el('span', { class: 'fgchip' + (g.p < 0.05 ? ' sig' : ''), 'data-row': g.row, 'data-kind': g.kind,
          text: g.row_say + ' · ' + g.kind_say.toLowerCase() + ': ' + pSay(g.p) + (stars(g.p) ? ' ' + stars(g.p) : '') + ' (rank ' + fmtN(g.rank)
            + (g.n ? ' of ' + fmtN(g.n) : '') + ')' }));
      }
    } else {
      // FP, P, T (2026-10-23): FP intervals, then the shuffle, then the t-test.
      for (const k of f.keys) {
        const ms = f.stats.measures[k] || {}, nl = f.stats.nulls[k] || {};
        const nf = (f.stats.nulls_fp || {})[k];
        if (nf) {
          chips.appendChild(el('span', { class: 'fgchip fgfp' + (nf.p < 0.05 ? ' sig' : ''), 'data-key': k + '-fp',
            text: measureSay(k, f) + ' \u00b7 FP intervals: ' + pSay(nf.p) + (stars(nf.p) ? ' ' + stars(nf.p) : '') + ' (rank ' + fmtN(nf.rank) + ' of ' + fmtN(nf.n) + ')' }));
        }
        chips.appendChild(el('span', { class: 'fgchip' + (nl.p < 0.05 ? ' sig' : ''), 'data-key': k + '-perm',
          text: (nf ? '' : measureSay(k, f) + ' \u00b7 ') + 'shuffles: ' + pSay(nl.p) + (stars(nl.p) ? ' ' + stars(nl.p) : '') + ' (rank ' + fmtN(nl.rank) + ' of ' + fmtN(nl.n) + ')' }));
        chips.appendChild(el('span', { class: 'fgchip' + (ms.p < 0.05 ? ' sig' : ''), 'data-key': k,
          text: 't-test: t(' + ms.df + ') = ' + (ms.t != null ? ms.t.toFixed(2) : '—') + ', ' + pSay(ms.p) + (stars(ms.p) ? ' ' + stars(ms.p) : '') }));
      }
    }
    card.appendChild(chips);
    card.appendChild(el('p', { class: 'small fglegend' }, [el('b', { text: 'Fig. ' + f.no + ' | ' + f.legend.title + ' ' }), f.legend.body]));
    if ((f.pac_missing || []).length) {
      card.appendChild(el('p', { class: 'small warn fgpacnote', text: 'The phase–amplitude roses and comodulogram for this PAC need the recordings, which were not readable when this was drawn. Read them on the VACC ('
        + (P.data && P.data.recordings_read ? 'the link at the foot of the page' : 'the button at the top') + '), or connect the data drive and press Draw again.' }));
    }
    const tools = el('div', { class: 'hrow fgtools' }, [
      el('a', { class: 'more-btn', href: FILE(f.files.pdf, true), download: f.files.pdf, text: 'PDF' }),
      el('a', { class: 'more-btn', href: FILE(f.files.svg, true), download: f.files.svg, text: 'SVG' }),
      el('a', { class: 'more-btn', href: FILE(f.files.png, true), download: f.files.png, text: 'PNG, 600 dpi' }),
      f0.files.xlsx ? el('a', { class: 'more-btn fgprism', href: FILE(f0.files.xlsx, true), download: f0.files.xlsx,
                                title: 'The numbers behind the panels, a sheet a table, laid out for GraphPad Prism', text: 'Prism data (.xlsx)' }) : null,
      f0.files.pzfx ? el('a', { class: 'more-btn fgprism', href: FILE(f0.files.pzfx, true), download: f0.files.pzfx,
                                title: 'The same tables as a Prism file: opens in Prism with the data tables filled', text: 'Prism file (.pzfx)' }) : null,
    ]);
    const mbtn = el('button', { type: 'button', class: 'more-btn fgmbtn', 'aria-expanded': String(P.open.has(f.id)), text: 'Methods?',
                                hidden: (f.methods || []).length ? null : 'hidden' });
    tools.appendChild(mbtn);
    card.appendChild(tools);
    const mhost = el('div', { class: 'fgmhost' });
    card.appendChild(mhost);
    const openIt = () => {
      mhost.innerHTML = '';
      if (P.open.has(f.id)) mhost.appendChild(methodsPanel(f));
      mbtn.setAttribute('aria-expanded', String(P.open.has(f.id)));
      mbtn.textContent = P.open.has(f.id) ? 'Methods ▴' : 'Methods?';
    };
    mbtn.addEventListener('click', () => { if (P.open.has(f.id)) P.open.delete(f.id); else P.open.add(f.id); openIt(); });
    openIt();
    return card;
  }

  // Where the PAC roses were read, and the proof that it was the same wire
  // of the same recording: every trial's modulation index against tab 8's.
  function readLine(D) {
    const c = D.pac_check, v = D.vacc_run || {};
    if (!c && D.recordings_where !== 'vacc') return null;
    const within = (x) => (x < 1e-9 ? 'a billionth' : x < 1e-6 ? 'a millionth' : Number(x).toPrecision(2));
    return el('p', { class: 'small muted', id: 'figsread', text: 'The PAC roses and comodulograms were read '
      + (D.recordings_where === 'vacc' ? 'on the VACC, from its copies of the recordings' + (v.slurm_id ? ' (job ' + v.slurm_id + (v.at ? ', ' + v.at.replace('T', ' ').slice(0, 16) : '') + ')' : '') : 'here, from the recordings')
      + (c ? (c.ok ? '. Every trial’s modulation index read there matched tab 8’s own to within ' + within(c.worst) + ' (' + fmtN(c.compared) + ' trials and windows), so it is the same wire of the same recording.'
              : c.matched ? '. Every trial read there matched tab 8’s own to within ' + within(c.worst) + ' (' + fmtN(c.compared) + ' trials and windows), but '
                + fmtN(c.only_tab) + ' that tab 8 measured were not read (the notes below say why), so the roses average fewer of them.'
              : '. Not every trial’s modulation index read there matched tab 8’s (largest difference ' + Number(c.worst).toPrecision(2) + '; ' + (c.only_tab + c.only_read) + ' trials in one only): draw tab 8 again before trusting the roses.')
           : '.') });
  }

  // The FP comparison: how much FP it was made from, or a button to make it.
  function fpLine(D) {
    const fp = D.fp || {};
    if (fp.read) {
      return el('p', { class: 'small muted', id: 'figsfpread', text: 'FP comparison: ' + fmtN(fp.fake_trials) + ' fake trials (a fake cue every '
        + fp.step_s + ' s of FP1 and FP2) from ' + fp.rat_days + ' of the ' + fp.of + ' rat-days; on every ring as a third test, and beside every follow-up’s shuffles.' });
    }
    return el('div', { class: 'small warn', id: 'figsfpnone' }, [
      el('p', { text: 'The FP comparison (each result against random moments of FP1 and FP2, with no cues) needs the FP recordings measured as fake trials.' }),
      window.MONO_STATIC ? null : el('button', { type: 'button', class: 'more-btn', id: 'figsfp', disabled: P.making ? 'disabled' : null,
        text: P.making === 'fp' ? 'Measuring FP on the VACC: ' + (P.makeNote || 'starting') : 'Measure them on the VACC (about 15 minutes)', onclick: () => make('fp') })]);
  }

  function intro() {
    const D = P.data;
    const conn = D.figures.filter((f) => f.kind === 'connectome');
    const fol = D.figures.filter((f) => f.kind === 'follow');
    const sig = conn.reduce((n, f) => n + f.stats.graphs.filter((g) => g.p < 0.05).length, 0);
    const toc = el('ol', { class: 'fgtoc', id: 'figstoc' }, D.figures.map((f) => el('li', { class: f.kind === 'follow' ? 'fgsub' : 'fgtop',
      'data-group': f.group ? f.group.key : '', hidden: f.group && P.hide.has(f.group.key) ? 'hidden' : null }, [
      el('a', { href: '#fig-' + f.id.replace('.', '_'), text: (f.kind === 'schematic' ? 'Supplementary Figure ' : 'Figure ') + f.no + ': '
        + (f.kind === 'follow' ? f.pair + ', ' + (f.legend.title.split(': ').pop()).replace(/\.$/, '') : f.legend.title),
                onclick: (e) => { e.preventDefault(); const c = $('fig-' + f.id.replace('.', '_')); if (c) c.scrollIntoView({ block: 'start', behavior: 'smooth' }); } })])));
    return section('figsintro', '9 · Joe’s figures', 'figs', [
      el('p', { class: 'takeaway', id: 'figssay', text: conn.length + ' connectome' + (conn.length === 1 ? '' : 's') + ' (comparisons '
        + Array.from(new Set(conn.map((f) => f.comparison))).join(', ') + ', in ' + Array.from(new Set(conn.map((f) => f.band))).join(' and ')
        + '; ' + sig + ' of ' + (conn.length * 9) + ' graphs beyond their ' + (conn[0] && conn[0].null === 'fp' ? 'FP sets' : 'shuffles') + '), then '
        + fol.length + ' follow-up figure' + (fol.length === 1 ? '' : 's') + ', grouped by window and band, the strongest first. Each is ready for Nature: Arial, 5–8 pt, 183 mm wide, vector, with its numbers for Prism.' }),
      fpLine(D),
      D.recordings_read ? readLine(D) : el('div', { class: 'small warn', id: 'figsrec' }, [
        el('p', { text: 'The recordings could not be read when these were drawn, so the PAC figures show each rat’s modulation index but not yet the phase–amplitude roses or comodulograms. Every recording has a copy on the VACC: read them there, or connect the data drive and press Draw again.' }),
        window.MONO_STATIC ? null : el('button', { type: 'button', class: 'more-btn', id: 'figsvacc', disabled: P.making ? 'disabled' : null,
          text: P.making === 'vacc' ? 'Reading on the VACC: ' + (P.makeNote || 'starting') : 'Read them on the VACC (about 2 minutes)', onclick: () => make(true) }),
        P.makeErr ? el('p', { text: P.makeErr }) : null]),
      toc,
      el('p', { class: 'small muted', text: 'Drawn ' + (D.at || '') + ' from tab 8’s numbers of ' + (D.from || '') + '; ' + fmtN(D.n_perm) + ' within-session shuffles per graph (seed ' + D.seed + ').' }),
    ]);
  }

  function render() {
    const pane = $('figspane');
    if (!pane) return;
    pane.innerHTML = '';
    if (P.loading && !P.data) { pane.appendChild(el('p', { class: 'loading', text: 'Reading tab 9…' })); return; }
    if (!P.data) {
      pane.appendChild(section('figsmissing', '9 · Joe’s figures', 'figs', [
        el('p', { class: 'takeaway', text: 'Publication figures for what tab 8 found. Not drawn yet.' }),
        P.err && !/not been drawn/i.test(P.err) ? el('p', { class: 'small warn', id: 'figserr', text: 'It could not be read: ' + P.err }) : null,
        el('p', { class: 'small', text: 'Drawn here from tab 8’s own numbers in about a minute; the PAC roses read the recordings too, if the data drive is connected.' }),
        window.MONO_STATIC ? el('p', { class: 'small muted', text: 'Not in this copy: it opens in Jarvis.' })
          : el('button', { type: 'button', class: 'more-btn', id: 'figsmake', disabled: P.making ? 'disabled' : null,
                           text: P.making ? 'Drawing: ' + (P.makeNote || 'starting') : 'Draw the figures', onclick: () => make() }),
        P.makeErr ? el('p', { class: 'small warn', text: P.makeErr }) : null,
      ]));
      return;
    }
    pane.appendChild(intro());
    const body = el('div', { class: 'fgbody' });
    const main = el('div', { class: 'fgmain' });
    let lastGroup = null;
    for (const f of P.data.figures) {
      const gk = f.group ? f.group.key : null;
      if (gk && gk !== lastGroup) {
        const g = f.group;
        main.appendChild(el('h3', { class: 'fggroup', 'data-group': gk, hidden: P.hide.has(gk) ? 'hidden' : null,
          text: g.no + ' \u00b7 ' + g.title + ' \u00b7 ' + g.band + (g.gated ? '' : '  (tab 8\u2019s light did not pass: rings only)') }));
      }
      lastGroup = gk;
      main.appendChild(figCard(f));
    }
    body.appendChild(main);
    body.appendChild(filterGrid());
    pane.appendChild(body);
    if ((P.data.notes || []).length) {
      pane.appendChild(el('div', { class: 'card', id: 'figsnotes' }, [X().more('notes from drawing (' + P.data.notes.length + ')', (body) => {
        body.appendChild(el('ul', { class: 'small' }, P.data.notes.slice(0, 200).map((n) => el('li', { text: n }))));
        return null;
      }, { key: 'figs-notes' })]));
    }
    if (!window.MONO_STATIC) {
      pane.appendChild(el('p', { class: 'small muted' }, ['Drawn ' + (P.data.at || '') + '. ',
        el('button', { type: 'button', class: 'linkish', id: 'figsmake', disabled: P.making ? 'disabled' : null,
                       text: P.making === 'here' ? 'Drawing: ' + (P.makeNote || 'starting') : 'Draw again', onclick: () => make() }),
        P.data.recordings_read ? el('span', { text: ' · ' }) : null,
        P.data.recordings_read ? el('button', { type: 'button', class: 'linkish', id: 'figsvaccagain', disabled: P.making ? 'disabled' : null,
                       text: P.making === 'vacc' ? 'Reading on the VACC: ' + (P.makeNote || 'starting') : 'read the PAC on the VACC and draw again', onclick: () => make(true) }) : null,
        P.makeErr && P.data.recordings_read ? el('span', { class: 'warn', id: 'figsmakeerr', text: ' ' + P.makeErr }) : null]));
    }
  }
  /* The filter on the right (2026-10-23): a block a window x band; a
     click shows or hides that group's figures, nothing redrawn. */
  function filterGrid() {
    const D = P.data;
    const groups = D.groups || [];
    const nos = Array.from(new Set(groups.map((g) => g.no)));
    const bands = Array.from(new Set(groups.map((g) => g.band)));
    const count = (gk) => D.figures.filter((f) => f.group && f.group.key === gk).length;
    const strong = (gk) => D.figures.some((f) => f.group && f.group.key === gk && ((f.kind === 'connectome' && f.passes && f.passes[f.null])
      || (f.kind === 'follow' && f.passes && f.passes.n === 3)));
    const apply = () => {
      for (const x of $('figspane').querySelectorAll('[data-group]')) {
        if (x.classList.contains('fgblock')) continue;
        const gk = x.dataset.group;
        if (gk) x.hidden = P.hide.has(gk);
      }
      try { localStorage.setItem(HIDE_KEY, JSON.stringify(Array.from(P.hide))); } catch (e) { /* a private window */ }
    };
    const block = (g) => {
      if (!g) return el('span', { class: 'fgblock none' });
      const b = el('button', { type: 'button', class: 'fgblock' + (P.hide.has(g.key) ? '' : ' on') + (strong(g.key) ? ' strong' : ''), 'data-group': g.key,
        'aria-pressed': String(!P.hide.has(g.key)), title: g.no + ' \u00b7 ' + g.title + ', ' + g.band + ': ' + count(g.key) + ' figure' + (count(g.key) === 1 ? '' : 's')
          + (strong(g.key) ? '; something passes every test' : ''),
        text: String(count(g.key)) });
      b.addEventListener('click', () => {
        if (P.hide.has(g.key)) P.hide.delete(g.key); else P.hide.add(g.key);
        b.classList.toggle('on', !P.hide.has(g.key));
        b.setAttribute('aria-pressed', String(!P.hide.has(g.key)));
        apply();
      });
      return b;
    };
    const grid = el('div', { class: 'fggrid', style: 'grid-template-columns: auto repeat(' + bands.length + ', 1fr)' }, [el('span', {})]
      .concat(bands.map((b) => el('span', { class: 'fgghead', text: b })))
      .concat(nos.flatMap((no) => [el('span', { class: 'fgrow', title: (groups.find((g) => g.no === no) || {}).title || '', text: String(no) })]
        .concat(bands.map((b) => block(groups.find((g) => g.no === no && g.band === b)))))));
    return el('aside', { class: 'fgfilter', id: 'figsfilter', 'aria-label': 'Which groups of figures to show' }, [
      el('div', { class: 'fgfhead', text: 'Show' }), grid,
      el('p', { class: 'small muted', text: 'Rows: comparison 1 (baseline \u2192 both cues), 2 (baseline \u2192 cue 1), 5 (cue 1 \u2192 cue 2). A number is its figures; a ring round it, something there passes every test.' }),
    ]);
  }
  function show() {
    if (!P.data && !P.loading) load(); else render();
  }
  return {
    show, render, load, make, METHODS, permToy, connToy, phasorToy, grangerToy, xcorrToy,
    get state() { return { data: P.data, err: P.err, making: P.making, open: Array.from(P.open) }; },
  };
})();
