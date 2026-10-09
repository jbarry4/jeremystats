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
  /* "Aah": a vowel is a voice through a few resonances, so each note is
     three slightly detuned saws -- a section, not a soloist -- through the
     three formants of an open A, with a slow swell and a little vibrato,
     into a hall made of decaying noise. Then bells when the button lands. */
  function startAudio() {
    stopAudio();
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    let ac;
    try { ac = new AC(); } catch (e) { return; }
    if (ac.state === 'suspended') ac.resume().catch(() => {});
    const t0 = ac.currentTime + 0.05;
    const master = ac.createGain();
    master.gain.value = 0.0001;
    master.gain.exponentialRampToValueAtTime(0.32, t0 + 1.2);
    master.gain.setValueAtTime(0.32, t0 + 6.2);
    master.gain.exponentialRampToValueAtTime(0.0001, t0 + 9.5);

    // The hall.
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
    wet.gain.value = 0.55;
    const dry = ac.createGain();
    dry.gain.value = 0.5;
    hall.connect(wet);
    wet.connect(master);
    dry.connect(master);
    master.connect(ac.destination);
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

    const formants = [[800, 1.0, 6], [1150, 0.5, 8], [2900, 0.25, 10]];
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
        env.gain.value = 0.0001;
        const s = t0 + at;
        env.gain.exponentialRampToValueAtTime(0.06, s + 0.9);
        env.gain.setValueAtTime(0.06, s + dur - 0.2);
        env.gain.exponentialRampToValueAtTime(0.0001, s + dur + 1.4);
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
            o.start(s);
            o.stop(s + dur + 1.6);
          }
        }
        env.connect(bus);
      }
    }

    // Bells, as the button settles on the pillar.
    const bells = [84, 88, 91, 96, 100];
    bells.forEach((m, k) => {
      const s = t0 + 2.7 + k * 0.11;
      const g = ac.createGain();
      g.gain.value = 0.0001;
      g.gain.exponentialRampToValueAtTime(0.09, s + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, s + 2.4);
      for (const [mul, amp] of [[1, 1], [2.76, 0.35], [5.4, 0.12]]) {
        const o = ac.createOscillator();
        o.type = 'sine';
        o.frequency.value = hz(m) * mul;
        const og = ac.createGain();
        og.gain.value = amp;
        o.connect(og);
        og.connect(g);
        o.start(s);
        o.stop(s + 2.5);
      }
      g.connect(bus);
    });

    audio = { ac, master };
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
      setTimeout(() => { try { a.ac.close(); } catch (e) { /* gone */ } }, 600);
    } catch (e) { /* nothing to stop */ }
  }

  /* ---------- the heavens ---------- */
  function reveal() {
    close();
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
    document.addEventListener('keydown', onKey, true);
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

  function close() {
    stopAudio();
    document.removeEventListener('keydown', onKey, true);
    const ov = document.getElementById('agHeaven');
    if (ov) ov.remove();
  }

  return { keyhole: keyhole, unlock: unlock, close: close };
})();
