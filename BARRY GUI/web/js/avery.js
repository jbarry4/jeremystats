/* ==========================================================================
   Avery -- AI Beta's model, sweeping a set from Checkup.

   Checkup's bar offers "Avery sweep…". It asks first, then shows a
   scanning screen while the set is read: now and then it takes one real
   candidate, sweeps across its waveform and reads it out, and once the
   scores are in it plays a short reel of real verdicts before the summary.
   The summary lists every candidate as DS, Flag for Deep Review, Flag or
   Garbage. Nothing is written until somebody accepts it; accepting puts
   Avery's calls on the candidates nobody has decided and banks every call
   as an Avery version, for the record and for training on edge cases.

   Backend: /api/avery*, backend/avery.py.
   ========================================================================== */
BARRY.avery = (function () {
  const ORDER = ['spike', 'review', 'flag', 'garbage'];
  const WORD = {
    spike: 'DS', review: 'Flag for Deep Review', flag: 'Flag',
    garbage: 'Garbage',
  };
  /* Measured on this machine, 2026-10-02, both reads, six stretches at a
     time: 0.19 s a candidate (451, network share), 0.36 (385) and 0.49
     (173, local disk -- small sets spread thin). Only for the sentence in
     the confirm dialog. */
  const SEC_PER_CANDIDATE = 0.4;
  const STAGE = {
    'avery read': 'Reading each candidate’s shape',
    'avery physio': 'Reading the physiology around each one',
    'avery score': 'Scoring',
  };

  let st = null;         // /api/avery
  let ctx = null;        // {gid, kind, name, n, decided, labels, onDone}
  let job = null;
  let pollT = null;
  let peekRev = -1;
  let queue = [];        // samples waiting to be scanned
  let scanning = false;
  let scanT = null;
  let result = null;
  let filter = null;     // which call the summary list shows

  const reduced = () => {
    try {
      return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) { return false; }
  };
  const pct = (x, dp) => (x === null || x === undefined || !isFinite(x))
    ? '—' : (100 * x).toFixed(dp === undefined ? 1 : dp) + '%';
  const num = (x) => Number(x || 0).toLocaleString();

  function colorOf(lab) {
    const fromSet = ((result && result.label_colors) || {})[lab]
      || ((ctx && ctx.colors) || {})[lab];
    if (fromSet) return fromSet;
    return BARRY.token(lab === 'spike' ? '--ok'
                       : lab === 'garbage' ? '--err' : '--warn');
  }

  /* ---------- asking ---------- */
  async function open(o) {
    ctx = Object.assign({}, o || {});
    if (job) { showOverlay(); return; }
    try {
      st = await api('/api/avery');
    } catch (e) {
      toast('Could not ask whether Avery is ready: ' + e.message, 'err', 8000);
      return;
    }
    if (!st.ready) {
      toast(st.why || 'Avery is not ready.', 'warn', 9000);
      return;
    }
    if (st.running) {
      toast('Avery is already sweeping a set. One at a time.', 'warn', 6000);
      return;
    }
    confirmDialog();
  }

  function confirmDialog() {
    const mins = Math.max(1, Math.round((ctx.n || 0) * SEC_PER_CANDIDATE / 60));
    const fam = (st.families || []).length;
    showModal(el('div', { class: 'modal avery-confirm' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Avery Sweep' }),
        el('span', { class: 'sub', text: ctx.name || '' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { class: 'avery-lede', text:
          'Avery reads every candidate in this set — its shape, the shank '
          + 'around it, unit firing and the second either side — and calls '
          + 'each one DS, Flag for Deep Review, Flag or Garbage.' }),
        el('dl', { class: 'br-dl avery-dl' }, [
          dl('Candidates', num(ctx.n) + (ctx.decided
            ? ' — ' + num(ctx.decided) + ' already decided by a person, '
              + 'and Avery never changes those' : '')),
          dl('Model', 'Run ' + st.run_id + ' · random forest · '
             + fam + ' kinds of input · trained on '
             + num(st.n_recordings) + ' recordings'),
          dl('Shown on mice it never saw', 'caught '
             + pct(st.garbage_caught) + ' of the garbage while flagging '
             + pct(st.ds_flagged) + ' of real spikes for a person'),
          dl('Time', 'about ' + mins + ' minute' + (mins === 1 ? '' : 's')
             + ' the first time; a set swept before is quicker'),
        ]),
        el('p', { class: 'hint', text:
          'Nothing is written while it sweeps. At the end you see every '
          + 'call, and decide whether to keep them.' }),
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        BARRY.ui.button({ text: 'Cancel', onclick: closeModal }),
        BARRY.ui.button({ kind: 'primary', text: 'Start the sweep',
                          onclick: () => { closeModal(); start(); } }),
      ]),
    ]));
  }

  function dl(term, def) {
    return el('div', {}, [el('dt', { text: term }), el('dd', { text: def })]);
  }

  /* ---------- running ---------- */
  async function start() {
    let got;
    try {
      got = await apiPost('/api/avery/sweep', { gid: ctx.gid, kind: ctx.kind });
    } catch (e) {
      toast(e.message, 'err', 9000);
      return;
    }
    job = got.job;
    result = null;
    queue = [];
    peekRev = -1;
    showOverlay();
    if (pollT) clearInterval(pollT);
    pollT = setInterval(tick, 800);
  }

  async function tick() {
    if (!job) return;
    let got;
    try { got = await api('/api/cfc/job/' + job.id); } catch (e) { return; }
    job = got.job;
    paintStage();
    if (job.preview_rev !== undefined && job.preview_rev !== peekRev) {
      peekRev = job.preview_rev;
      try {
        const pk = await api('/api/avery/sweep/' + job.id + '/peek');
        const s = (pk.peek && pk.peek.samples) || [];
        if (s.length) {
          queue = s.slice();
          if (!scanning) scanNext();
        }
      } catch (e) { /* the screen carries on without them */ }
    }
    if (job.status === 'running') return;
    clearInterval(pollT);
    pollT = null;
    if (job.status === 'done') {
      try {
        result = (await api('/api/cfc/result/' + job.id)).result;
      } catch (e) {
        toast('The sweep finished but its result could not be read: '
              + e.message, 'err', 9000);
        closeOverlay();
        job = null;
        return;
      }
      verdictReel();
    } else {
      if (job.status !== 'canceled') {
        toast(job.error || 'The sweep did not finish.', 'err', 9000);
      }
      job = null;
      closeOverlay();
    }
  }

  async function stop() {
    if (!job) { closeOverlay(); return; }
    try { await apiPost('/api/cfc/job/' + job.id + '/cancel', {}); } catch (e) {}
  }

  /* ---------- the screen ---------- */
  function showOverlay() {
    let ov = document.getElementById('averyOv');
    if (!ov) {
      ov = el('div', { class: 'avery-ov', id: 'averyOv' });
      document.body.appendChild(ov);
    }
    ov.innerHTML = '';
    ov.appendChild(el('div', { class: 'avery-panel' }, [
      el('div', { class: 'avery-top' }, [
        el('span', { class: 'avery-mark', text: 'AVERY' }),
        el('span', { class: 'avery-sep', text: '//' }),
        el('span', { class: 'avery-what', text: 'SWEEP' }),
        el('span', { class: 'avery-set', text: ctx.name || '' }),
        el('div', { class: 'spacer' }),
        BARRY.ui.button({ size: 'sm', text: 'Stop', id: 'averyStop',
          title: 'Stop the sweep. Nothing has been written.', onclick: stop }),
      ]),
      el('div', { class: 'avery-scope' }, [
        el('canvas', { id: 'averyScope' }),
        el('div', { class: 'avery-read', id: 'averyRead' }),
        el('div', { class: 'avery-stamp', id: 'averyStamp' }),
      ]),
      el('div', { class: 'avery-stage' }, [
        el('span', { id: 'averyStageText', text: 'Opening the recording…' }),
        el('span', { class: 'avery-eta', id: 'averyEta', text: '' }),
      ]),
      el('div', { class: 'br-bar avery-bar' }, [el('i', { id: 'averyBar' })]),
      el('div', { class: 'avery-log', id: 'averyLog' }),
      el('div', { id: 'averySummary' }),
    ]));
    sizeScope();
    drawIdle();
  }

  function closeOverlay() {
    if (scanT) clearTimeout(scanT);
    scanT = null;
    scanning = false;
    const ov = document.getElementById('averyOv');
    if (ov) ov.remove();
  }

  function paintStage() {
    const stages = (job && job.stages) || [];
    const now = stages.find((x) => x.status === 'running')
             || stages.find((x) => (x.done || 0) < (x.of || 0))
             || stages[stages.length - 1] || {};
    const t = document.getElementById('averyStageText');
    if (t) {
      t.textContent = (STAGE[now.name] || 'Working')
        + ((now.of || 0) > 1 ? ' — ' + num(Math.min(now.done || 0, now.of))
           + ' of ' + num(now.of) + ' ' + (now.unit || '') : '');
    }
    let total = 0, spent = 0;
    for (const s of stages) {
      const w = s.name === 'avery physio' ? 4 : s.name === 'avery read' ? 1 : 0.2;
      if (s.of) { total += w; spent += w * Math.min(1, (s.done || 0) / s.of); }
      else if (s.status === 'done') { total += w; spent += w; }
      else total += w;
    }
    const bar = document.getElementById('averyBar');
    if (bar) bar.style.width = Math.round(total ? 100 * spent / total : 0) + '%';
    const eta = document.getElementById('averyEta');
    if (eta) {
      eta.textContent = [
        job && job.eta_s ? 'about ' + Math.max(1, Math.round(job.eta_s / 60))
          + ' min left' : '',
        job && job.elapsed > 4 ? Math.round(job.elapsed) + ' s' : '',
      ].filter(Boolean).join('  ·  ');
    }
  }

  /* ---------- the scope ---------- */
  function sizeScope() {
    const c = document.getElementById('averyScope');
    if (!c) return null;
    const r = c.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    c.width = Math.max(300, Math.round((r.width || 640) * dpr));
    c.height = Math.max(120, Math.round((r.height || 220) * dpr));
    return c;
  }

  function grid(g, w, h) {
    g.fillStyle = BARRY.token('--bg-2');
    g.fillRect(0, 0, w, h);
    g.strokeStyle = BARRY.token('--line-soft');
    g.lineWidth = 1;
    for (let x = 0; x <= 10; x++) {
      g.beginPath(); g.moveTo(x * w / 10, 0); g.lineTo(x * w / 10, h); g.stroke();
    }
    for (let y = 0; y <= 4; y++) {
      g.beginPath(); g.moveTo(0, y * h / 4); g.lineTo(w, y * h / 4); g.stroke();
    }
    g.strokeStyle = BARRY.token('--line');
    g.beginPath(); g.moveTo(w / 2, 0); g.lineTo(w / 2, h); g.stroke();
  }

  function drawIdle() {
    const c = document.getElementById('averyScope');
    if (!c) return;
    const g = c.getContext('2d');
    grid(g, c.width, c.height);
  }

  /* One candidate, swept left to right: its 5-100 Hz trace on the channel
     where it is largest (accent), the shank's CSD under it (muted), and a
     scan line revealing both. `frac` is how far the line has got. */
  function drawSample(s, frac) {
    const c = document.getElementById('averyScope');
    if (!c) return;
    const g = c.getContext('2d');
    const w = c.width, h = c.height;
    grid(g, w, h);
    const lines = [
      [s.csd || [], BARRY.token('--text-3'), 0.62],
      [s.wave || [], BARRY.token('--accent'), 0.42],
    ];
    for (const [ys, col, amp] of lines) {
      if (!ys.length) continue;
      let lo = Infinity, hi = -Infinity;
      for (const v of ys) { if (v < lo) lo = v; if (v > hi) hi = v; }
      const span = (hi - lo) || 1;
      const upto = Math.max(1, Math.floor(ys.length * frac));
      g.strokeStyle = col;
      g.lineWidth = Math.max(1.5, w / 400);
      g.beginPath();
      for (let k = 0; k < upto; k++) {
        const x = (k / (ys.length - 1)) * w;
        const y = h / 2 - ((ys[k] - lo) / span - 0.5) * h * amp;
        if (k) g.lineTo(x, y); else g.moveTo(x, y);
      }
      g.stroke();
    }
    if (frac < 1) {
      const x = frac * w;
      g.fillStyle = BARRY.token('--accent-soft');
      g.fillRect(Math.max(0, x - w * 0.04), 0, w * 0.04, h);
      g.strokeStyle = BARRY.token('--accent');
      g.lineWidth = Math.max(1, w / 600);
      g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke();
    }
  }

  function readouts(s) {
    const r = s.readouts || {};
    const bits = [
      ['t', s.t != null ? s.t.toFixed(3) + ' s' : null],
      ['amp', r.amp_uv != null ? Math.round(r.amp_uv) + ' µV' : null],
      ['half-width', r.half_width_ms != null ? r.half_width_ms.toFixed(1) + ' ms' : null],
      ['rise', r.rise_ms != null ? r.rise_ms.toFixed(0) + ' ms' : null],
      ['CSD peak', r.csd_peak != null ? r.csd_peak.toFixed(2) + '×' : null],
      ['common mode', r.common_mode != null ? r.common_mode.toFixed(2) : null],
      ['unit firing', r.mua != null ? (r.mua >= 0 ? '+' : '') + r.mua.toFixed(2) : null],
      ['likeness', r.likeness != null ? r.likeness.toFixed(2) : null],
    ].filter((x) => x[1] !== null);
    return bits;
  }

  /* Scan the next queued sample. Timer-driven, not animation-event
     driven: a background tab and a headless run both stop reporting the
     end of an animation, and a screen waiting on that never moves on. */
  function scanNext(onEmpty) {
    if (!queue.length) {
      scanning = false;
      if (onEmpty) onEmpty();
      return;
    }
    scanning = true;
    const s = queue.shift();
    const read = document.getElementById('averyRead');
    const stamp = document.getElementById('averyStamp');
    if (stamp) { stamp.textContent = ''; stamp.className = 'avery-stamp'; }
    if (read) read.innerHTML = '';
    const bits = readouts(s);
    const steps = reduced() ? 1 : 26;
    let k = 0;
    const frame = () => {
      k += 1;
      const frac = Math.min(1, k / steps);
      drawSample(s, frac);
      if (read) {
        const shown = Math.ceil(bits.length * frac);
        read.innerHTML = '';
        for (const [a, b] of bits.slice(0, shown)) {
          read.appendChild(el('div', {}, [el('span', { text: a }),
                                          el('b', { text: b })]));
        }
      }
      if (frac < 1) { scanT = setTimeout(frame, 30); return; }
      if (stamp) {
        if (s.label) {
          stamp.textContent = WORD[s.label] + (s.p != null
            ? '  ' + s.p.toFixed(2) : '');
          stamp.className = 'avery-stamp on';
          stamp.style.setProperty('--call', colorOf(s.label));
        } else {
          stamp.textContent = 'measured';
          stamp.className = 'avery-stamp on dim';
          stamp.style.setProperty('--call', BARRY.token('--text-3'));
        }
      }
      logLine(s);
      scanT = setTimeout(() => scanNext(onEmpty), s.label ? 700 : 1100);
    };
    frame();
  }

  function logLine(s) {
    const log = document.getElementById('averyLog');
    if (!log) return;
    log.prepend(el('div', { class: 'avery-logline' }, [
      el('span', { text: (s.t != null ? s.t.toFixed(3) : '?') + ' s' }),
      el('span', { text: s.label ? WORD[s.label] : 'scanned' ,
                   style: s.label ? 'color:' + colorOf(s.label) : null }),
      el('span', { text: s.p != null ? 'p(DS) ' + s.p.toFixed(2) : '' }),
    ]));
    while (log.children.length > 6) log.lastChild.remove();
  }

  /* The real verdicts on the sampled candidates, in time order, then the
     summary. A Skip, because it is a flourish and not the result. */
  function verdictReel() {
    paintStage();
    const t = document.getElementById('averyStageText');
    if (t) t.textContent = 'Classified. Showing a few of the calls…';
    const stopBtn = document.getElementById('averyStop');
    if (stopBtn) {
      stopBtn.textContent = 'Skip to the summary';
      stopBtn.onclick = () => { queue = []; if (scanT) clearTimeout(scanT); summary(); };
    }
    if (scanT) clearTimeout(scanT);
    queue = ((result && result.samples) || []).slice();
    scanNext(summary);
  }

  /* ---------- the summary ---------- */
  function summary() {
    if (scanT) clearTimeout(scanT);
    scanT = null;
    scanning = false;
    const ov = document.getElementById('averyOv');
    if (!ov || !result) return;
    const r = result;
    const host = document.getElementById('averySummary');
    const scope = ov.querySelector('.avery-scope');
    if (scope) scope.classList.add('done');
    const t = document.getElementById('averyStageText');
    if (t) t.textContent = 'Done. Avery called ' + num(r.n) + ' candidates.';
    const bar = document.getElementById('averyBar');
    if (bar) bar.style.width = '100%';
    const eta = document.getElementById('averyEta');
    if (eta) eta.textContent = r.cached ? 'read before, so only scored' : '';
    const stopBtn = document.getElementById('averyStop');
    if (stopBtn) stopBtn.remove();
    host.innerHTML = '';

    host.appendChild(el('div', { class: 'avery-tiles' }, ORDER.map((lab) => {
      const n = (r.counts || {})[lab] || 0;
      return el('button', {
        class: 'avery-tile' + (filter === lab ? ' on' : ''),
        style: '--call:' + colorOf(lab),
        title: 'Show only these below',
        onclick: () => { filter = filter === lab ? null : lab; summary(); },
      }, [
        el('b', { text: num(n) }),
        el('span', { text: WORD[lab] }),
        el('i', { text: pct(n / Math.max(1, r.n), 0) }),
      ]);
    })));

    const notes = [];
    const ho = r.held_out || {};
    const share = (lab, of) => {
      const b = ho[lab];
      return b && b.n ? (of === 'ds' ? b.n_ds : b.n_garbage) / b.n : null;
    };
    if (ho.spike) {
      notes.push('On mice it never saw, ' + pct(share('spike', 'ds'))
        + ' of what Avery called DS really was, and '
        + pct(share('garbage', 'garbage')) + ' of what it called Garbage '
        + 'really was. Flag for Deep Review is the stretch just under its DS '
        + 'bar; Flag is everything between.');
    }
    if (r.agreement && r.agreement.compared) {
      notes.push(num(r.already_decided) + ' of these were already decided '
        + 'by a person. Where both said DS or Garbage, Avery agreed on '
        + pct(r.agreement.agree / r.agreement.compared) + '. Those '
        + 'decisions stay as they are.');
    }
    if (r.n_readable < r.n) {
      notes.push(num(r.n - r.n_readable) + ' could not be read (too near '
        + 'either end of the recording, or in a gap) and are marked Flag.');
    }
    host.appendChild(el('div', { class: 'avery-notes' },
      notes.map((x) => el('p', { text: x }))));

    const rows = (r.rows || []).filter((x) => !filter || x.label === filter);
    host.appendChild(el('div', { class: 'br-scroll avery-list' }, [
      el('table', { class: 'br-tbl ai-tbl' }, [
        el('thead', {}, [el('tr', {}, ['Time', 'Avery', 'p(DS)',
          'A person said'].map((h) => el('th', { text: h })))]),
        el('tbody', {}, rows.map((x) => el('tr', {}, [
          el('td', { text: x.start.toFixed(3) + ' s' }),
          el('td', {}, [el('span', { class: 'avery-pill',
                                     style: '--call:' + colorOf(x.label),
                                     text: WORD[x.label] || x.label })]),
          el('td', { text: x.p == null ? '—' : x.p.toFixed(3) }),
          el('td', { text: x.human ? (WORD[x.human] || x.human)
                           + (x.human_by ? ' (' + x.human_by + ')' : '')
                           : '' }),
        ]))),
      ])]));

    const undecided = (r.n || 0) - (r.already_decided || 0);
    host.appendChild(el('div', { class: 'avery-foot' }, [
      el('p', { class: 'hint', text:
        'Accept and review puts Avery’s calls on the ' + num(undecided)
        + ' candidates nobody has decided, and banks every call as an Avery '
        + 'version of this set — kept for the record and for training on '
        + 'edge cases later. Then work through the flags.' }),
      el('div', { class: 'spacer' }),
      BARRY.ui.button({ text: 'Discard', title: 'Close. Nothing is kept.',
                        onclick: () => { job = null; result = null; closeOverlay(); } }),
      BARRY.ui.button({ kind: 'primary', text: 'Accept and review',
                        id: 'averyAccept', onclick: accept }),
    ]));
  }

  async function accept() {
    const b = document.getElementById('averyAccept');
    if (b) b.disabled = true;
    let res;
    try {
      res = await apiPost('/api/avery/sweep/' + job.id + '/accept', {});
    } catch (e) {
      if (b) b.disabled = false;
      toast('Could not keep Avery’s calls: ' + e.message, 'err', 9000);
      return;
    }
    toast('Avery’s calls are on ' + num(res.applied) + ' candidates and '
          + 'banked as v' + res.version + ' (Avery). The Flagged pass is '
          + 'next.', 'ok', 8000);
    job = null;
    result = null;
    closeOverlay();
    if (ctx && ctx.onDone) ctx.onDone(res);
  }

  return { open: open, running: () => !!job };
})();
