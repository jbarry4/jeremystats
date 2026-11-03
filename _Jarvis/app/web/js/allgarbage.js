/* ==========================================================================
   All Garbage -- Checkup's secret (asked for 2026-10-09).

   A keyhole in the curation bar, too faint to notice unless you know. It
   asks for a PIN; the right one dims the room, opens the heavens -- rays,
   halos, a choir -- raises a golden pillar, and lowers an All Garbage button
   onto it. Pressing it once asks; pressing it again calls every candidate in
   the set Garbage (curate.js does the deciding, and `u` takes it back).

   The PIN is not in this file, only its SHA-256, so reading the source does
   not give it away. It is a door for fun, not a lock: anything it does, a
   person can already do one key at a time.

   The choir and the bells are made here with Web Audio -- oscillators
   through vowel formants and a synthetic hall -- so there is no sound file
   to ship. It starts on the key press that enters the PIN, which is the
   gesture a browser wants before it will play anything.
   ========================================================================== */
BARRY.allGarbage = (function () {
  const PIN_SHA256 =
    'c2eb7898bb6771503ffee5d0c722e5b561fe480edbc30141880a1cdf1e5b1cf6';
  const DIGITS = 6;

  let ctx = null;      // {count, decided, onAll}
  let audio = null;    // {ac, master, stop}

  const reduced = () => {
    try {
      return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) { return false; }
  };

  async function sha256(text) {
    const buf = await crypto.subtle.digest('SHA-256',
      new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf))
      .map((b) => b.toString(16).padStart(2, '0')).join('');
  }

  /* ---------- the keyhole ---------- */
  function keyhole(onClick) {
    return el('button', {
      class: 'ag-keyhole', 'aria-label': 'A keyhole',
      title: '', onclick: onClick,
      html: '<svg viewBox="0 0 12 16" aria-hidden="true">'
        + '<circle cx="6" cy="5.2" r="3.4"/>'
        + '<path d="M4.6 7.6 3.6 14h4.8L7.4 7.6"/></svg>',
    });
  }

  /* ---------- the PIN ---------- */
  function unlock(o) {
    ctx = Object.assign({}, o || {});
    const boxes = [];
    const msg = el('p', { class: 'ag-pin-msg', text: ' ' });
    const row = el('div', { class: 'ag-pin' });
    for (let i = 0; i < DIGITS; i++) {
      const b = el('input', {
        class: 'ag-digit', type: 'password', inputmode: 'numeric',
        maxlength: '1', autocomplete: 'off', 'aria-label': 'Digit ' + (i + 1),
      });
      b.addEventListener('input', () => {
        primeAudio();
        b.value = b.value.replace(/\D/g, '').slice(-1);
        if (b.value && i < DIGITS - 1) boxes[i + 1].focus();
        if (boxes.every((x) => x.value)) tryPin();
      });
      b.addEventListener('keydown', (e) => {
        if (e.key === 'Backspace' && !b.value && i > 0) {
          boxes[i - 1].value = '';
          boxes[i - 1].focus();
          e.preventDefault();
        }
        if (e.key === 'Escape') closeModal();
        e.stopPropagation();
      });
      b.addEventListener('paste', (e) => {
        const t = ((e.clipboardData || window.clipboardData)
                   .getData('text') || '').replace(/\D/g, '').slice(0, DIGITS);
        if (!t) return;
        e.preventDefault();
        t.split('').forEach((d, k) => { if (boxes[k]) boxes[k].value = d; });
        if (t.length === DIGITS) tryPin(); else boxes[t.length].focus();
      });
      boxes.push(b);
      row.appendChild(b);
    }

    async function tryPin() {
      const pin = boxes.map((x) => x.value).join('');
      let ok = false;
      try { ok = (await sha256(pin)) === PIN_SHA256; } catch (e) { ok = false; }
      if (ok) {
        // The key press that finished the PIN is the gesture that lets the
        // choir sing; the context is made here, before anything awaits.
        startAudio();
        closeModal();
        reveal();
        return;
      }
      row.classList.remove('ag-shake');
      void row.offsetWidth;
      row.classList.add('ag-shake');
      msg.textContent = 'Not that one.';
      boxes.forEach((x) => { x.value = ''; });
      boxes[0].focus();
    }

    showModal(el('div', { class: 'modal ag-pin-modal' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Enter the PIN' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [row, msg]),
    ]));
    setTimeout(() => boxes[0].focus(), 30);
  }

  /* ---------- the choir ---------- */
  /* WHY THERE WAS NO SOUND (2026-10-09). Two things, either enough on its
     own. Opening the heavens first shut any heavens already open -- and
     that meant stopping the choir it had started a line earlier. And the
     choir was quiet to begin with: three saws through narrow vowel filters
     keep a small share of their energy, and the levels were set as though
     they kept all of it -- about -36 dB. Measured now, not guessed: see
     `_measure` and the harness, which renders the whole score offline.

     A third thing, for browsers stricter than Chrome: the audio context is
     made on the first digit typed -- a key press, the gesture a browser
     wants -- and not after the PIN is checked, which awaits a hash first.

     "Aah": a vowel is a voice through a few resonances, so each note is a
     section of three slightly detuned saws through the formants of an open
     A, over a soft triangle for body, with a slow swell and a little
     vibrato, into a hall made of decaying noise and a compressor that keeps
     the chords from clipping. Then bells as the button lands. */
  let shared = null;          // the AudioContext, made on the first digit

  function primeAudio() {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    if (!shared || shared.state === 'closed') {
      try { shared = new AC(); } catch (e) { shared = null; return null; }
    }
    if (shared.state === 'suspended') shared.resume().catch(() => {});
    return shared;
  }

  /* The whole score, into `dest`, starting at `t0`. Separate from the
     context so the harness can render it offline and measure it. */
  function score(ac, dest, t0) {
    const len = Math.floor(ac.sampleRate * 3.2);
    const ir = ac.createBuffer(2, len, ac.sampleRate);
    for (let ch = 0; ch < 2; ch++) {
      const d = ir.getChannelData(ch);
      for (let i = 0; i < len; i++) {
        d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2.6);
      }
    }
    const hall = ac.createConvolver();
    hall.buffer = ir;
    const wet = ac.createGain();
    wet.gain.value = 0.5;
    const dry = ac.createGain();
    dry.gain.value = 0.8;
    hall.connect(wet);
    wet.connect(dest);
    dry.connect(dest);
    const bus = ac.createGain();
    bus.connect(hall);
    bus.connect(dry);

    // Vibrato, shared, so the section breathes together.
    const lfo = ac.createOscillator();
    lfo.frequency.value = 5.2;
    const lfoAmt = ac.createGain();
    lfoAmt.gain.value = 7;            // cents
    lfo.connect(lfoAmt);
    lfo.start(t0);
    lfo.stop(t0 + 10);

    const formants = [[800, 2.2, 5], [1150, 1.4, 6], [2900, 0.7, 8]];
    const hz = (midi) => 440 * Math.pow(2, (midi - 69) / 12);
    // C major, F over C, C major with the G on top.
    const chords = [
      [0.0, 2.0, [48, 55, 60, 64, 67]],
      [1.9, 2.1, [48, 53, 60, 65, 69]],
      [3.9, 5.2, [48, 55, 60, 64, 67, 72, 79]],
    ];
    for (const [at, dur, notes] of chords) {
      for (const m of notes) {
        const env = ac.createGain();
        const s0 = t0 + at;
        env.gain.setValueAtTime(0.0001, s0);
        env.gain.exponentialRampToValueAtTime(0.16, s0 + 0.9);
        env.gain.setValueAtTime(0.16, s0 + dur - 0.2);
        env.gain.exponentialRampToValueAtTime(0.0001, s0 + dur + 1.4);
        for (const [f, g, q] of formants) {
          const bp = ac.createBiquadFilter();
          bp.type = 'bandpass';
          bp.frequency.value = f;
          bp.Q.value = q;
          const fg = ac.createGain();
          fg.gain.value = g;
          bp.connect(fg);
          fg.connect(env);
          for (const det of [-9, 0, 8]) {
            const o = ac.createOscillator();
            o.type = 'sawtooth';
            o.frequency.value = hz(m);
            o.detune.value = det;
            lfoAmt.connect(o.detune);
            o.connect(bp);
            o.start(s0);
            o.stop(s0 + dur + 1.6);
          }
        }
        // Body under the vowel.
        const body = ac.createOscillator();
        body.type = 'triangle';
        body.frequency.value = hz(m);
        lfoAmt.connect(body.detune);
        const lp = ac.createBiquadFilter();
        lp.type = 'lowpass';
        lp.frequency.value = 1400;
        const bg = ac.createGain();
        bg.gain.value = 0.45;
        body.connect(lp);
        lp.connect(bg);
        bg.connect(env);
        body.start(s0);
        body.stop(s0 + dur + 1.6);
        env.connect(bus);
      }
    }

    // Bells, as the button settles on the pillar.
    [84, 88, 91, 96, 100].forEach((m, k) => {
      const s0 = t0 + 2.7 + k * 0.11;
      const g = ac.createGain();
      g.gain.setValueAtTime(0.0001, s0);
      g.gain.exponentialRampToValueAtTime(0.2, s0 + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, s0 + 2.4);
      for (const [mul, amp] of [[1, 1], [2.76, 0.35], [5.4, 0.12]]) {
        const o = ac.createOscillator();
        o.type = 'sine';
        o.frequency.value = hz(m) * mul;
        const og = ac.createGain();
        og.gain.value = amp;
        o.connect(og);
        og.connect(g);
        o.start(s0);
        o.stop(s0 + 2.5);
      }
      g.connect(bus);
    });
  }

  /* The master: a swell in, a long fade out, and a compressor so a seven-
     note chord and five bells at once do not clip. */
  function master(ac, t0) {
    const m = ac.createGain();
    m.gain.setValueAtTime(0.0001, t0);
    m.gain.exponentialRampToValueAtTime(0.85, t0 + 1.0);
    m.gain.setValueAtTime(0.85, t0 + 6.4);
    m.gain.exponentialRampToValueAtTime(0.0001, t0 + 9.6);
    const comp = ac.createDynamicsCompressor();
    comp.threshold.value = -16;
    comp.knee.value = 12;
    comp.ratio.value = 3.5;
    comp.attack.value = 0.01;
    comp.release.value = 0.25;
    m.connect(comp);
    comp.connect(ac.destination);
    return m;
  }

  function startAudio() {
    stopAudio();
    const ac = primeAudio();
    if (!ac) return;
    const t0 = ac.currentTime + 0.05;
    const m = master(ac, t0);
    score(ac, m, t0);
    audio = { ac, master: m };
  }

  function stopAudio() {
    if (!audio) return;
    const a = audio;
    audio = null;
    try {
      const now = a.ac.currentTime;
      a.master.gain.cancelScheduledValues(now);
      a.master.gain.setValueAtTime(Math.max(0.0001, a.master.gain.value), now);
      a.master.gain.exponentialRampToValueAtTime(0.0001, now + 0.4);
      // The context stays: closing it would make the next reveal ask for a
      // gesture all over again.
      setTimeout(() => { try { a.master.disconnect(); } catch (e) { /* gone */ } },
                 600);
    } catch (e) { /* nothing to stop */ }
  }

  /* For the harness: the whole score rendered offline, and how loud it is. */
  async function measure(seconds) {
    const OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    if (!OAC) return null;
    const sr = 22050;
    const oac = new OAC(2, Math.floor(sr * (seconds || 10)), sr);
    const m = master(oac, 0.05);
    score(oac, m, 0.05);
    const buf = await oac.startRendering();
    let peak = 0, sum = 0, n = 0, loudest = 0;
    const win = Math.floor(sr * 0.5);
    for (let ch = 0; ch < buf.numberOfChannels; ch++) {
      const d = buf.getChannelData(ch);
      let acc = 0;
      for (let i = 0; i < d.length; i++) {
        const v = d[i];
        if (Math.abs(v) > peak) peak = Math.abs(v);
        sum += v * v;
        n += 1;
        acc += v * v;
        if ((i + 1) % win === 0) {
          loudest = Math.max(loudest, Math.sqrt(acc / win));
          acc = 0;
        }
      }
    }
    return { peak: peak, rms: Math.sqrt(sum / n), loudest: loudest };
  }

  /* ---------- the heavens ---------- */
  function reveal() {
    removeHeavens();
    const n = (ctx && ctx.count) || 0;
    const sparks = el('div', { class: 'ag-sparks' });
    for (let i = 0; i < 28; i++) {
      sparks.appendChild(el('i', { style: '--x:' + Math.round(Math.random() * 100)
        + '%;--d:' + (3 + Math.random() * 5).toFixed(2) + 's;--w:'
        + (Math.random() * 6).toFixed(2) + 's;--s:'
        + (0.5 + Math.random()).toFixed(2) }));
    }
    let armed = false;
    const label = el('span', { class: 'ag-btn-text', text: 'All Garbage' });
    const sub = el('span', { class: 'ag-btn-sub',
      text: 'every one of ' + Number(n).toLocaleString() + ' candidates' });
    const btn = el('button', {
      class: 'ag-btn', id: 'agAllGarbage',
      onclick: async () => {
        if (!armed) {
          armed = true;
          btn.classList.add('armed');
          label.textContent = 'Truly? All Garbage';
          sub.textContent = (ctx && ctx.decided
            ? Number(ctx.decided).toLocaleString() + ' decisions already made '
              + 'will become Garbage too. '
            : '') + 'Press again; u takes it back.';
          return;
        }
        btn.disabled = true;
        btn.classList.add('ascend');
        let ok = false;
        try { ok = ctx && ctx.onAll ? await ctx.onAll() : false; }
        catch (e) { ok = false; }
        setTimeout(close, ok === false ? 0 : (reduced() ? 0 : 900));
      },
    }, [label, sub]);
    const ov = el('div', { class: 'ag-heaven' + (reduced() ? ' still' : ''),
                           id: 'agHeaven', role: 'dialog',
                           'aria-label': 'All Garbage' }, [
      el('div', { class: 'ag-rays' }),
      el('div', { class: 'ag-glow' }),
      sparks,
      el('div', { class: 'ag-stage' }, [
        el('div', { class: 'ag-descend' }, [
          el('div', { class: 'ag-halo' }),
          el('div', { class: 'ag-rings' }, [el('i'), el('i'), el('i')]),
          btn,
        ]),
        el('div', { class: 'ag-pillar' }, [
          el('div', { class: 'ag-capital' }),
          el('div', { class: 'ag-shaft' }),
          el('div', { class: 'ag-base' }),
        ]),
      ]),
      el('button', { class: 'ag-close', text: 'Close', title: 'Back to Checkup',
                     onclick: close }),
    ]);
    ov.addEventListener('click', (e) => { if (e.target === ov) close(); });
    document.body.appendChild(ov);
    // On the window, capturing: ahead of Checkup's own keys, which listen
    // on the document -- or Escape left curation as well as the heavens.
    window.addEventListener('keydown', onKey, true);
    // Focus lands on the button once it has landed, so Enter presses it.
    setTimeout(() => { if (btn.isConnected) btn.focus(); },
               reduced() ? 0 : 3000);
  }

  function onKey(e) {
    if (e.key === 'Escape') {
      e.preventDefault(); e.stopPropagation();
      close();
    } else if (document.getElementById('agHeaven')) {
      // Nothing behind the heavens hears the keyboard while they are open.
      if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Tab') {
        e.stopPropagation();
      }
    }
  }

  function removeHeavens() {
    window.removeEventListener('keydown', onKey, true);
    const ov = document.getElementById('agHeaven');
    if (ov) ov.remove();
  }

  function close() {
    stopAudio();
    removeHeavens();
  }

  return { keyhole: keyhole, unlock: unlock, close: close,
           playing: () => !!audio, _measure: measure };
})();
