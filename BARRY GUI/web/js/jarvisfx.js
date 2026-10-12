/* ==========================================================================
   jarvisfx.js -- the sounds of the reveal, made on the spot.

   Nothing is loaded: every sound is synthesised with Web Audio when it is
   played, so there is no file to be missing, no request to fail and nothing
   in the repository but this. The palette is the lab's own -- the crackle of
   a neuron on an audio monitor as it fires faster and faster, then one
   spike, the boom it makes, and the name typing itself in.

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

  let ctx = null, master = null, comp = null, noiseBuf = null;
  let muted = false;
  try { muted = localStorage.getItem(KEY) === 'off'; } catch (e) { /* default: on */ }

  function ac() {
    if (muted) return null;
    try {
      if (!ctx) {
        const C = window.AudioContext || window.webkitAudioContext;
        if (!C) return null;
        ctx = new C();
        master = ctx.createGain();
        master.gain.value = 0.6;
        // A limiter on the way out, so a boom and a chord landing together
        // never clip on a laptop speaker turned all the way up.
        comp = ctx.createDynamicsCompressor();
        comp.threshold.value = -16;
        comp.knee.value = 12;
        comp.ratio.value = 6;
        comp.attack.value = 0.003;
        comp.release.value = 0.2;
        master.connect(comp);
        comp.connect(ctx.destination);
        const n = ctx.sampleRate;
        noiseBuf = ctx.createBuffer(1, n, n);
        const d = noiseBuf.getChannelData(0);
        for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
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
    try { fn(c, c.currentTime + 0.01); } catch (e) { /* silence */ }
  }

  function env(g, t, peak, attack, hold, release) {
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(Math.max(peak, 0.0002), t + attack);
    g.gain.setValueAtTime(Math.max(peak, 0.0002), t + attack + hold);
    g.gain.exponentialRampToValueAtTime(0.0001, t + attack + hold + release);
  }
  function osc(c, type, f, t, dur, peak, attack, release, dest) {
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = type;
    o.frequency.setValueAtTime(f, t);
    env(g, t, peak, attack || 0.005, Math.max(0, dur - (attack || 0.005)), release || 0.08);
    o.connect(g);
    g.connect(dest || master);
    o.start(t);
    o.stop(t + dur + (release || 0.08) + 0.05);
    return o;
  }
  function noise(c, t, dur, peak, filterType, f, q, dest) {
    const s = c.createBufferSource();
    s.buffer = noiseBuf;
    s.loop = true;
    const fl = c.createBiquadFilter();
    fl.type = filterType || 'bandpass';
    fl.frequency.setValueAtTime(f || 2000, t);
    fl.Q.value = q || 1;
    const g = c.createGain();
    env(g, t, peak, 0.002, Math.max(0, dur - 0.002), 0.03);
    s.connect(fl); fl.connect(g); g.connect(dest || master);
    s.start(t, Math.random() * 0.5);
    s.stop(t + dur + 0.1);
    return { src: s, filter: fl, gain: g };
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
       mid-charge must not keep crackling under the chord. Done by swapping
       in a fresh output and letting the old one fade, since a scheduled
       Web Audio node cannot be found again to be cancelled. */
    hush() {
      try {
        if (!ctx || !master) return;
        const old = master;
        old.gain.setTargetAtTime(0, ctx.currentTime, 0.03);
        setTimeout(() => { try { old.disconnect(); } catch (e) { /* gone */ } }, 400);
        master = ctx.createGain();
        master.gain.value = 0.6;
        master.connect(comp);
      } catch (e) { /* silence */ }
    },

    /* The charge: a low hum whose filter opens, under the crackle of a
       neuron on an audio monitor firing faster and faster -- three pops a
       second at the start, sixty by the end. */
    charge(dur) {
      play((c, t) => {
        const out = c.createGain();
        out.gain.value = 1;
        out.connect(master);
        const lp = c.createBiquadFilter();
        lp.type = 'lowpass';
        lp.frequency.setValueAtTime(140, t);
        lp.frequency.exponentialRampToValueAtTime(1600, t + dur);
        lp.Q.value = 6;
        lp.connect(out);
        const hum = c.createGain();
        hum.gain.setValueAtTime(0.0001, t);
        hum.gain.exponentialRampToValueAtTime(0.16, t + dur * 0.85);
        hum.gain.exponentialRampToValueAtTime(0.0001, t + dur + 0.08);
        hum.connect(lp);
        [[55, 'sawtooth'], [55.4, 'sawtooth'], [110, 'triangle']].forEach(([f, ty]) => {
          const o = c.createOscillator();
          o.type = ty;
          o.frequency.setValueAtTime(f, t);
          o.frequency.exponentialRampToValueAtTime(f * 1.5, t + dur);
          o.connect(hum);
          o.start(t);
          o.stop(t + dur + 0.2);
        });
        // The crackle: pops on an accelerating clock.
        let at = 0;
        while (at < dur) {
          const p = at / dur;
          const rate = 3 * Math.pow(20, p);          // 3/s -> 60/s
          const pk = 0.10 + 0.22 * p * Math.random();
          noise(c, t + at, 0.004 + Math.random() * 0.003, pk, 'bandpass',
                1800 + Math.random() * 2600, 0.9, out);
          at += (0.6 + Math.random() * 0.8) / rate;
        }
      });
    },

    /* The spike: a zap falling from 2.4 kHz, the boom under it, and the
       shockwave of filtered noise. */
    fire() {
      play((c, t) => {
        const z = c.createOscillator();
        const zg = c.createGain();
        z.type = 'sawtooth';
        z.frequency.setValueAtTime(2400, t);
        z.frequency.exponentialRampToValueAtTime(90, t + 0.2);
        env(zg, t, 0.22, 0.002, 0.02, 0.24);
        const zf = c.createBiquadFilter();
        zf.type = 'lowpass'; zf.frequency.value = 5000;
        z.connect(zf); zf.connect(zg); zg.connect(master);
        z.start(t); z.stop(t + 0.4);

        const b = c.createOscillator();
        const bg = c.createGain();
        b.type = 'sine';
        b.frequency.setValueAtTime(92, t);
        b.frequency.exponentialRampToValueAtTime(30, t + 1.1);
        env(bg, t, 0.85, 0.004, 0.08, 1.3);
        b.connect(bg); bg.connect(master);
        b.start(t); b.stop(t + 1.6);

        const s = noise(c, t, 0.9, 0.32, 'lowpass', 2400, 0.7);
        s.filter.frequency.exponentialRampToValueAtTime(160, t + 0.9);
        // A bright tail, the sparkle on top of the spike.
        [2637, 3520, 4186].forEach((f, i) =>
          osc(c, 'sine', f, t + 0.06 + i * 0.05, 0.02, 0.035, 0.003, 0.5));
      });
    },

    // One per letter as the name locks in: a soft blip, a step higher each.
    tick(i) {
      play((c, t) => {
        osc(c, 'square', 700 + 110 * (i || 0), t, 0.018, 0.035, 0.002, 0.05);
        noise(c, t, 0.006, 0.05, 'highpass', 5000, 0.7);
      });
    },
    // The scrambling under it: a dry, quiet chatter.
    chatter(dur) {
      play((c, t) => {
        for (let a = 0; a < dur; a += 0.045) {
          osc(c, 'square', 1800 + Math.random() * 1600, t + a, 0.008, 0.012, 0.001, 0.02);
        }
      });
    },

    /* The name has arrived: a warm A major ninth that blooms and fades,
       and three bells over it. */
    chord() {
      play((c, t) => {
        const lp = c.createBiquadFilter();
        lp.type = 'lowpass'; lp.frequency.value = 2600;
        const g = c.createGain();
        g.gain.value = 1;
        lp.connect(g); g.connect(master);
        [110, 220, 277.18, 329.63, 415.3, 493.88].forEach((f, i) => {
          ['sine', 'triangle'].forEach((ty, k) => {
            const o = c.createOscillator();
            const og = c.createGain();
            o.type = ty;
            o.frequency.value = f;
            o.detune.value = k ? 6 : -6;
            env(og, t + i * 0.03, i === 0 ? 0.09 : 0.045, 0.7, 0.6, 3.2);
            o.connect(og); og.connect(lp);
            o.start(t + i * 0.03); o.stop(t + 5);
          });
        });
        [1318.5, 1760, 2217.5].forEach((f, i) =>
          osc(c, 'sine', f, t + 0.35 + i * 0.16, 0.02, 0.05, 0.004, 1.4));
      });
    },

    hover() {
      play((c, t) => osc(c, 'sine', 1900, t, 0.012, 0.018, 0.002, 0.05));
    },
    select() {
      play((c, t) => {
        osc(c, 'sine', 880, t, 0.02, 0.09, 0.003, 0.35);
        osc(c, 'sine', 1318.5, t + 0.08, 0.02, 0.08, 0.003, 0.5);
        const s = noise(c, t, 0.35, 0.05, 'bandpass', 600, 0.8);
        s.filter.frequency.exponentialRampToValueAtTime(4000, t + 0.35);
      });
    },
    // Air moving: for the mark flying home and panels sliding in.
    whoosh(dur) {
      play((c, t) => {
        dur = dur || 0.6;
        const s = c.createBufferSource();
        s.buffer = noiseBuf; s.loop = true;
        const f = c.createBiquadFilter();
        f.type = 'bandpass'; f.Q.value = 1.2;
        f.frequency.setValueAtTime(350, t);
        f.frequency.exponentialRampToValueAtTime(2800, t + dur * 0.55);
        f.frequency.exponentialRampToValueAtTime(700, t + dur);
        const g = c.createGain();
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.16, t + dur * 0.5);
        g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
        s.connect(f); f.connect(g); g.connect(master);
        s.start(t); s.stop(t + dur + 0.05);
      });
    },
    // The badge landing in the rail.
    land() {
      play((c, t) => {
        const b = c.createOscillator();
        const g = c.createGain();
        b.type = 'sine';
        b.frequency.setValueAtTime(140, t);
        b.frequency.exponentialRampToValueAtTime(60, t + 0.25);
        env(g, t, 0.35, 0.003, 0.02, 0.35);
        b.connect(g); g.connect(master);
        b.start(t); b.stop(t + 0.5);
        osc(c, 'sine', 1760, t + 0.04, 0.02, 0.04, 0.003, 0.6);
      });
    },
    // A dentate spike found by the live detector: a round, low "tock".
    pop(big) {
      play((c, t) => {
        const o = c.createOscillator();
        const g = c.createGain();
        o.type = 'sine';
        o.frequency.setValueAtTime(big ? 260 : 330, t);
        o.frequency.exponentialRampToValueAtTime(big ? 70 : 110, t + 0.09);
        env(g, t, 0.16, 0.002, 0.01, 0.12);
        o.connect(g); g.connect(master);
        o.start(t); o.stop(t + 0.3);
        noise(c, t, 0.004, 0.06, 'bandpass', 3200, 1);
      });
    },
    // An IED found by the live detector: a short electric crack.
    zap() {
      play((c, t) => {
        const o = c.createOscillator();
        const g = c.createGain();
        const f = c.createBiquadFilter();
        o.type = 'sawtooth';
        o.frequency.setValueAtTime(900, t);
        o.frequency.exponentialRampToValueAtTime(140, t + 0.14);
        f.type = 'bandpass'; f.frequency.value = 1400; f.Q.value = 0.8;
        env(g, t, 0.09, 0.002, 0.02, 0.12);
        o.connect(f); f.connect(g); g.connect(master);
        o.start(t); o.stop(t + 0.3);
        noise(c, t, 0.012, 0.09, 'highpass', 3000, 0.7);
      });
    },
    // Opening the card about Paul: one soft bell, nothing more.
    bell() {
      play((c, t) => {
        osc(c, 'sine', 659.25, t, 0.02, 0.06, 0.004, 2.2);
        osc(c, 'sine', 987.77, t + 0.12, 0.02, 0.035, 0.004, 2.0);
      });
    },
  };

  if (B) B.jarvisfx = fx; else window.JarvisFX = fx;
})();
