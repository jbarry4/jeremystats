/* ==========================================================================
   jarvisfx.js -- the sounds of the reveal, made on the spot.

   Nothing is loaded: every sound is synthesised with Web Audio when it is
   played, so there is no file to be missing, no request to fail and nothing
   in the repository but this.

   The reveal is a tribute -- the application is named in memory of
   Dr. Paul Jarvis -- so the sounds are meant to be dignified rather than
   exciting: a slow swell, a struck bell when the spike fires, a quiet
   music-box line as the name forms, and a warm open chord when it is
   whole. Everything is in A major and goes through a soft hall, so it rings
   rather than pops. Nothing buzzes, zaps or booms.

   Every call is safe to make at any time. With no AudioContext, with sound
   switched off, or with anything throwing inside, a call simply makes no
   sound. A decoration must never be what stops the reveal.

   The context is created on the first call, which in practice is the click
   that starts the reveal -- browsers only let a page make sound after a
   person has pressed something, and that press is exactly when this is
   needed.
   ========================================================================== */
(function () {
  'use strict';
  if (typeof window === 'undefined') return;
  const B = (typeof BARRY !== 'undefined') ? BARRY : null;
  const KEY = 'barry.jarvis.sound';           // 'off' when muted

  let ctx = null, master = null, comp = null, hall = null;
  let muted = false;
  try { muted = localStorage.getItem(KEY) === 'off'; } catch (e) { /* default: on */ }

  // A major, the one key everything is in.
  const A2 = 110, E3 = 164.81, A3 = 220, CS4 = 277.18, E4 = 329.63, FS4 = 369.99,
        A4 = 440, B4 = 493.88, CS5 = 554.37, E5 = 659.25, FS5 = 739.99, A5 = 880;

  /* The room. A synthesised impulse response -- two seconds and a half of
     decaying noise, a little different on each side -- gives every sound a
     hall to ring in, which is most of what makes a sine wave sound like an
     instrument rather than a test tone. */
  function makeHall(c) {
    const len = Math.round(c.sampleRate * 2.6);
    const ir = c.createBuffer(2, len, c.sampleRate);
    for (let ch = 0; ch < 2; ch++) {
      const d = ir.getChannelData(ch);
      for (let i = 0; i < len; i++) {
        const t = i / len;
        d[i] = (Math.random() * 2 - 1) * Math.pow(1 - t, 3.2) * (i < 40 ? i / 40 : 1);
      }
    }
    const conv = c.createConvolver();
    conv.buffer = ir;
    const wet = c.createGain();
    wet.gain.value = 0.34;
    conv.connect(wet);
    wet.connect(comp);
    return conv;
  }
  function makeMaster(c) {
    const m = c.createGain();
    m.gain.value = 0.5;
    m.connect(comp);            // dry
    if (hall) m.connect(hall);  // and into the room
    return m;
  }

  function ac() {
    if (muted) return null;
    try {
      if (!ctx) {
        const C = window.AudioContext || window.webkitAudioContext;
        if (!C) return null;
        ctx = new C();
        // A gentle limiter on the way out: a chord and a bell landing
        // together must never clip on a laptop speaker turned up.
        comp = ctx.createDynamicsCompressor();
        comp.threshold.value = -18;
        comp.knee.value = 14;
        comp.ratio.value = 4;
        comp.attack.value = 0.01;
        comp.release.value = 0.3;
        comp.connect(ctx.destination);
        try { hall = makeHall(ctx); } catch (e) { hall = null; }
        master = makeMaster(ctx);
      }
      if (ctx.state === 'suspended') ctx.resume();
      return ctx;
    } catch (e) {
      return null;
    }
  }
  // Every sound goes through here: no context, no sound, no exception.
  function play(fn) {
    const c = ac();
    if (!c) return;
    try { fn(c, c.currentTime + 0.02); } catch (e) { /* silence */ }
  }

  /* One sine partial with a soft attack and an exponential fade. */
  function partial(c, f, t, peak, attack, decay, dest, type) {
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = type || 'sine';
    o.frequency.setValueAtTime(f, t);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(peak, t + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t + attack + decay);
    o.connect(g);
    g.connect(dest || master);
    o.start(t);
    o.stop(t + attack + decay + 0.1);
  }

  /* A struck bell: a few partials in a bell's proportions, the high ones
     dying first. `soft` takes the edge off for the quieter moments. */
  function bellAt(c, f, t, peak, length, soft) {
    const parts = soft
      ? [[1, 1, 1], [2, 0.32, 0.6], [3.01, 0.12, 0.38]]
      : [[0.5, 0.45, 1.25], [1, 1, 1], [1.5, 0.18, 0.7], [2, 0.4, 0.62],
         [2.76, 0.16, 0.42], [4.07, 0.07, 0.26]];
    for (const [ratio, amp, life] of parts) {
      partial(c, f * ratio, t, peak * amp, soft ? 0.012 : 0.004, length * life);
    }
  }

  /* A music-box note: a pure tone and a faint octave, short and clear. */
  function chime(c, f, t, peak) {
    partial(c, f, t, peak, 0.006, 1.3);
    partial(c, f * 2, t, peak * 0.18, 0.004, 0.5);
  }

  /* A soft, wooden note -- for the detectors in the destinations. */
  function marimba(c, f, t, peak) {
    partial(c, f, t, peak, 0.004, 0.55);
    partial(c, f * 4, t, peak * 0.12, 0.002, 0.12);
  }

  const fx = {
    get muted() { return muted; },
    setMuted(m) {
      muted = !!m;
      try { localStorage.setItem(KEY, muted ? 'off' : 'on'); } catch (e) { /* private */ }
      if (muted && ctx) { try { ctx.suspend(); } catch (e) { /* fine */ } }
      if (!muted) ac();
    },
    // Called from the click that starts things, so the browser allows sound.
    unlock() { ac(); },
    /* Everything already scheduled, faded out at once: the reveal skipped
       mid-swell must not keep swelling under the chord. Done by swapping in
       a fresh output and letting the old one fade, since a scheduled Web
       Audio node cannot be found again to be cancelled. */
    hush() {
      try {
        if (!ctx || !master) return;
        const old = master;
        old.gain.setTargetAtTime(0, ctx.currentTime, 0.08);
        setTimeout(() => { try { old.disconnect(); } catch (e) { /* gone */ } }, 900);
        master = makeMaster(ctx);
      } catch (e) { /* silence */ }
    },

    /* The swell, while the ring draws: an open fifth, low and quiet, its
       filter opening slowly, with a faint high shimmer coming in over it.
       It does not stop when the spike fires; it settles under the bell. */
    charge(dur) {
      play((c, t) => {
        const lp = c.createBiquadFilter();
        lp.type = 'lowpass';
        lp.frequency.setValueAtTime(260, t);
        lp.frequency.exponentialRampToValueAtTime(1400, t + dur);
        lp.Q.value = 0.7;
        const g = c.createGain();
        g.gain.setValueAtTime(0.0001, t);
        g.gain.linearRampToValueAtTime(0.11, t + dur);
        g.gain.setTargetAtTime(0.0001, t + dur + 0.6, 0.9);
        lp.connect(g);
        g.connect(master);
        [[A2, -4], [A2, 4], [E3, -3], [E3, 3], [A3, 0]].forEach(([f, cents]) => {
          const o = c.createOscillator();
          o.type = 'triangle';
          o.frequency.value = f;
          o.detune.value = cents;
          o.connect(lp);
          o.start(t);
          o.stop(t + dur + 6);
        });
        // The shimmer: two high sines with a slow tremolo, very quiet.
        [E5, A5].forEach((f, i) => {
          const o = c.createOscillator();
          const og = c.createGain();
          const lfo = c.createOscillator();
          const depth = c.createGain();
          o.frequency.value = f;
          og.gain.setValueAtTime(0.0001, t);
          og.gain.linearRampToValueAtTime(0.012, t + dur * (0.7 + 0.2 * i));
          og.gain.setTargetAtTime(0.0001, t + dur + 0.3, 0.6);
          lfo.frequency.value = 4.5 + i;
          depth.gain.value = 0.006;
          lfo.connect(depth);
          depth.connect(og.gain);
          o.connect(og);
          og.connect(master);
          o.start(t); lfo.start(t);
          o.stop(t + dur + 4); lfo.stop(t + dur + 4);
        });
      });
    },

    /* The spike fires: one bell, struck once, on A, with the A below it. */
    fire() {
      play((c, t) => {
        bellAt(c, A3, t, 0.16, 5.5);
        partial(c, A2, t, 0.09, 0.02, 4.0);
      });
    },

    // The name forming: one music-box note per letter, up the scale.
    tick(i) {
      const notes = [A4, B4, CS5, E5, FS5, A5];
      play((c, t) => chime(c, notes[Math.max(0, Math.min(notes.length - 1, i | 0))], t, 0.05));
    },
    // The letters cycling is a picture, not a sound: kept as a call so
    // nothing that makes it has to change, and silent.
    chatter() { /* silence on purpose */ },

    /* The name is whole: a warm, open A major chord with the ninth in it,
       swelling slowly and fading over several seconds. */
    chord() {
      play((c, t) => {
        const lp = c.createBiquadFilter();
        lp.type = 'lowpass';
        lp.frequency.value = 1900;
        lp.connect(master);
        [A2, E3, A3, CS4, E4, B4].forEach((f, i) => {
          [-5, 5].forEach((cents, k) => {
            const o = c.createOscillator();
            const g = c.createGain();
            o.type = k ? 'triangle' : 'sine';
            o.frequency.value = f;
            o.detune.value = cents;
            const at = t + i * 0.07;
            const peak = (i === 0 ? 0.05 : 0.03) * (k ? 0.6 : 1);
            g.gain.setValueAtTime(0.0001, at);
            g.gain.linearRampToValueAtTime(peak, at + 1.1);
            g.gain.setValueAtTime(peak, at + 1.8);
            g.gain.exponentialRampToValueAtTime(0.0001, at + 6.5);
            o.connect(g);
            g.connect(lp);
            o.start(at);
            o.stop(at + 6.7);
          });
        });
      });
    },

    // Barely there: a pointer over a choice.
    hover() {
      play((c, t) => partial(c, A5, t, 0.008, 0.01, 0.18));
    },
    // A choice made: two soft bell notes, a fourth apart.
    select() {
      play((c, t) => {
        bellAt(c, E5, t, 0.035, 1.8, true);
        bellAt(c, A5, t + 0.12, 0.03, 2.2, true);
      });
    },
    /* Moving on -- the badge flying home, a page going back: a quiet
       falling arpeggio rather than a rush of air. */
    whoosh(dur) {
      play((c, t) => {
        const step = Math.max(0.08, Math.min(0.16, (dur || 0.6) / 5));
        [E5, CS5, A4].forEach((f, i) => chime(c, f, t + i * step, 0.03));
      });
    },
    // The badge settling in the rail: a low bell, soft.
    land() {
      play((c, t) => bellAt(c, A3, t, 0.08, 3.2, true));
    },
    // A dentate spike found by the live detector: a soft wooden note from
    // the pentatonic scale, so a run of them is a quiet melody.
    pop(big) {
      const scale = big ? [A3, CS4, E4] : [FS4, A4, CS5];
      play((c, t) => marimba(c, scale[(Math.random() * scale.length) | 0], t, 0.05));
    },
    // An IED found by the live detector: low and muted, never an alarm.
    zap() {
      play((c, t) => marimba(c, E3, t, 0.06));
    },
    // Opening the card about Paul: one bell, and time for it to ring.
    bell() {
      play((c, t) => {
        bellAt(c, E4, t, 0.06, 4.5, true);
        partial(c, A3, t + 0.02, 0.025, 0.4, 3.5);
      });
    },
  };

  if (B) B.jarvisfx = fx; else window.JarvisFX = fx;
})();
