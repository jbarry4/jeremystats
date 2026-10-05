/* ==========================================================================
   Avery -- AI Beta's model, sweeping a set from Checkup.

   Checkup's bar offers "Avery sweep…". It asks first -- which model
   (Avery, Avery+, Avery Garbage Dystrophy+, whichever are ready) and how
   many real spikes may go with the garbage -- then shows a scanning screen
   while the set is read: now and then it takes one real candidate and
   sweeps across every even channel of it, and once the scores are in the
   feed runs through every call in time order while a few more are scanned,
   then the summary.
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
  let model = null;      // 'avery', 'avery_plus' or 'avery_gd'
  let streamT = null;
  let tol = null;        // share of real spikes that may be called Garbage
  let pool = [];         // the candidates scanned, round and round, while reading
  let phase = 'reading'; // 'reading', then 'reel' once the calls are in
  let reelDone = false, streamDone = false;
  let idleT = null;

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
    const models = st.models || { avery: st };
    const ready = ['avery_gd', 'avery_plus', 'avery']
      .filter((k) => (models[k] || {}).ready);
    if (!ready.length) {
      toast(st.why || 'Avery is not ready.', 'warn', 9000);
      return;
    }
    if (!model || !ready.includes(model)) model = ready[0];
    if (st.running) {
      toast('Avery is already sweeping a set. One at a time.', 'warn', 6000);
      return;
    }
    confirmDialog();
  }

  function confirmDialog(replace) {
    const mins = Math.max(1, Math.round((ctx.n || 0) * SEC_PER_CANDIDATE / 60));
    const models = st.models || { avery: st };
    const m = models[model] || st;
    const fam = (m.families || []).length;
    const tols = m.tolerances || [];
    if (tols.length && !tols.some((x) => Math.abs(x.ds_loss - tol) < 1e-9)) {
      tol = m.default_tolerance || tols[Math.floor(tols.length / 2)].ds_loss;
    }
    const row = tols.find((x) => Math.abs(x.ds_loss - tol) < 1e-9);
    const choices = [['avery', 'Avery', 'Flags what it is unsure of; calls '
                      + 'Garbage only when it is nearly certain.'],
                     ['avery_plus', 'Avery+', 'Aligns every candidate the way '
                      + 'Braces does and looks again at the 30 ms around the '
                      + 'peak; calls more of the garbage Garbage.'],
                     ['avery_gd', 'Avery Garbage Dystrophy+', 'Built to leave '
                      + 'you the least garbage to sift through: catches as '
                      + 'much of it as it can at the share of real spikes '
                      + 'you allow.']]
      .filter(([k]) => (models[k] || {}).ready);
    const plain = (k) => k === 'avery_gd'
      ? 'Built to leave a person the least garbage to sift through. Choose '
        + 'how many real spikes may go with the garbage; the more, the less '
        + 'is left in Flag.'
      : k === 'avery_plus'
      ? 'Trades a few real spikes for calling most garbage Garbage, so less '
        + 'of it is left in Flag for a person to sift through.'
      : 'Garbage is called only where nine in ten held-out calls were '
        + 'right; the rest of the garbage lands in Flag.';
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
        choices.length > 1 ? BARRY.ui.field({
          label: 'Model',
          control: BARRY.ui.seg(choices, model, (v) => {
            model = v; confirmDialog(true);
          }, { extra: 'avery-models' }),
          hint: plain(model),
        }) : null,
        /* How much garbage a person is left to sift through, against how
           many real spikes may go with the garbage. Every row is what that
           bar did on mice the model never saw. */
        tols.length ? BARRY.ui.field({
          label: 'Real spikes that may be called Garbage',
          control: BARRY.ui.seg(tols.map((x) => [x.ds_loss,
            pct(x.ds_loss, 0), 'Garbage cleaned automatically '
            + pct(x.garbage_cleaned) + ', candidates flagged '
            + pct(x.flagged)]), tol, (v) => { tol = v; confirmDialog(true); },
            { extra: 'avery-tols' }),
          hint: row ? 'On mice it never saw: ' + pct(row.garbage_cleaned)
            + ' of the garbage cleaned out automatically, '
            + pct(row.garbage_left) + ' left for a person to look at, '
            + pct(row.garbage_into_ds) + ' let into DS; '
            + pct(row.flagged) + ' of all candidates flagged.' : null,
        }) : null,
        el('dl', { class: 'br-dl avery-dl' }, [
          dl('Candidates', num(ctx.n) + (ctx.decided
            ? ' — ' + num(ctx.decided) + ' already decided by a person, '
              + 'and Avery never changes those' : '')),
          dl(m.name || 'Model', 'Run ' + m.run_id + ' · '
             + ({ hgb: 'gradient-boosted trees', forest: 'random forest',
                  blend: 'a blend of five sets of boosted trees',
                  logistic: 'logistic regression' }[m.model] || m.model)
             + ' · '
             + fam + ' kinds of input · trained on '
             + num(m.n_recordings) + ' recordings'),
          row ? null : dl('On mice it never saw', 'kept '
             + pct(1 - (m.garbage_into_ds || 0), 1) + ' of the garbage out '
             + 'of DS; called ' + pct(m.garbage_called_garbage)
             + ' of it Garbage and ' + pct(m.ds_called_garbage)
             + ' of real spikes Garbage; flagged '
             + pct(m.flagged_share) + ' of candidates for a person'),
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
    ].filter(Boolean)), replace ? { replace: true } : undefined);
  }

  function dl(term, def) {
    return el('div', {}, [el('dt', { text: term }), el('dd', { text: def })]);
  }

  /* ---------- running ---------- */
  async function start() {
    let got;
    try {
      const m = (st.models || {})[model] || {};
      got = await apiPost('/api/avery/sweep', {
        gid: ctx.gid, kind: ctx.kind, model: model,
        ds_loss: (m.tolerances || []).length ? tol : null });
    } catch (e) {
      toast(e.message, 'err', 9000);
      return;
    }
    job = got.job;
    result = null;
    queue = [];
    pool = [];
    phase = 'reading';
    reelDone = false;
    streamDone = false;
    peekRev = -1;
    showOverlay();
    if (pollT) clearInterval(pollT);
    pollT = setInterval(tick, 800);
  }

  /* One at a time. While the server is busy reading, a poll can take
     longer than the 800 ms between them; overlapping polls each saw the
     job finish and each started the finale, and two reels fighting over
     one scope read as a freeze. */
  let ticking = false;
  async function tick() {
    if (!job || ticking) return;
    ticking = true;
    try { await tickOnce(); } finally { ticking = false; }
  }

  async function tickOnce() {
    let got;
    try { got = await api('/api/cfc/job/' + job.id); } catch (e) { return; }
    if (!job) return;
    job = got.job;
    paintStage();
    if (job.preview_rev !== undefined && job.preview_rev !== peekRev) {
      peekRev = job.preview_rev;
      try {
        const pk = await api('/api/avery/sweep/' + job.id + '/peek');
        const s = (pk.peek && pk.peek.samples) || [];
        if (s.length && phase === 'reading') {
          pool = s.slice();
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
        el('span', { class: 'avery-mark',
                     text: model === 'avery_gd' ? 'AVERY GARBAGE DYSTROPHY+'
                       : model === 'avery_plus' ? 'AVERY+' : 'AVERY' }),
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
    if (idleT) clearTimeout(idleT);
    idleT = null;
    if (scanT) clearTimeout(scanT);
    if (streamT) clearTimeout(streamT);
    streamT = null;
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
    /* Until the first candidate is in, the line sweeps an empty grid: a
       still screen for the few seconds the recording takes to open read
       as a hang. */
    if (idleT) clearTimeout(idleT);
    let f = 0;
    const tickIdle = () => {
      const cc = document.getElementById('averyScope');
      if (!cc || scanning || phase !== 'reading') { idleT = null; return; }
      f = (f + 0.02) % 1;
      const gg = cc.getContext('2d');
      grid(gg, cc.width, cc.height);
      sweepLine(gg, cc.width, cc.height, f);
      idleT = setTimeout(tickIdle, 40);
    };
    if (!reduced()) idleT = setTimeout(tickIdle, 40);
  }

  /* One candidate, swept left to right: its 5-100 Hz trace on the channel
     where it is largest (accent), the shank's CSD under it (muted), and a
     scan line revealing both. `frac` is how far the line has got. */
  function drawSample(s, frac, tint) {
    const c = document.getElementById('averyScope');
    if (!c) return;
    const g = c.getContext('2d');
    const w = c.width, h = c.height;
    grid(g, w, h);
    const chans = s.channels || [];
    if (chans.length) {
      /* Every even channel, top of the probe at the top, one lane each,
         all on one scale so a large channel looks large. The channel the
         event is biggest on is drawn in the accent. */
      let big = 0, bigRow = 0;
      chans.forEach((row, k) => {
        for (const v of row) {
          if (Math.abs(v) > big) { big = Math.abs(v); bigRow = k; }
        }
      });
      big = big || 1;
      const lane = h / (chans.length + 1);
      const upto = Math.max(1, Math.floor(chans[0].length * frac));
      const muted = BARRY.token('--text-3');
      const hot = BARRY.token('--accent');
      chans.forEach((row, k) => {
        const y0 = lane * (k + 1);
        g.strokeStyle = tint || (k === bigRow ? hot : muted);
        g.lineWidth = k === bigRow ? Math.max(1.5, w / 500) : Math.max(1, w / 900);
        g.beginPath();
        for (let q = 0; q < upto; q++) {
          const x = (q / (row.length - 1)) * w;
          const y = y0 - (row[q] / big) * lane * 2.2;
          if (q) g.lineTo(x, y); else g.moveTo(x, y);
        }
        g.stroke();
      });
      sweepLine(g, w, h, frac);
      return;
    }
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
    sweepLine(g, w, h, frac);
  }

  function sweepLine(g, w, h, frac) {
    if (frac >= 1) return;
    const x = frac * w;
    g.fillStyle = BARRY.token('--accent-soft');
    g.fillRect(Math.max(0, x - w * 0.04), 0, w * 0.04, h);
    g.strokeStyle = BARRY.token('--accent');
    g.lineWidth = Math.max(1, w / 600);
    g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke();
  }

  function readouts(s) {
    const r = s.readouts || {};
    const bits = [
      ['t', s.t != null ? s.t.toFixed(3) + ' s' : null],
      ['peak', r.peak_uv != null ? Math.round(r.peak_uv) + ' µV' : null],
      ['biggest on', r.best_ch != null ? 'CSC ' + r.best_ch : null],
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
    /* While the set is still being read, round and round the same
       candidates -- an empty scope for a minute reads as a hang. */
    if (!queue.length && phase === 'reading' && pool.length) {
      queue = pool.slice();
    }
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
    const steps = reduced() ? 1 : 22;
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
          /* The call: the lanes take its colour and the stamp lands. */
          drawSample(s, 1, colorOf(s.label));
          stamp.textContent = WORD[s.label] + (s.p != null
            ? '  ' + s.p.toFixed(2) : '');
          stamp.className = 'avery-stamp';
          void stamp.offsetWidth;
          stamp.className = 'avery-stamp on hit';
          stamp.style.setProperty('--call', colorOf(s.label));
          const scope = document.querySelector('#averyOv .avery-scope');
          if (scope) {
            scope.style.setProperty('--call', colorOf(s.label));
            scope.classList.remove('flash');
            void scope.offsetWidth;
            scope.classList.add('flash');
          }
        } else {
          stamp.textContent = 'measured';
          stamp.className = 'avery-stamp on dim';
          stamp.style.setProperty('--call', BARRY.token('--text-3'));
        }
      }
      logLine(s);
      scanT = setTimeout(() => scanNext(onEmpty), s.label ? 650 : 900);
    };
    frame();
  }

  function logLine(s) {
    const log = document.getElementById('averyLog');
    /* Not while the feed is streaming every call: the feed is the list
       then, and a scan writing into it (and trimming it to six lines)
       scrambled its order. */
    if (!log || log.classList.contains('stream')) return;
    log.prepend(el('div', { class: 'avery-logline' }, [
      el('span', { text: (s.t != null ? s.t.toFixed(3) : '?') + ' s' }),
      el('span', { text: s.label ? WORD[s.label] : 'scanned' ,
                   style: s.label ? 'color:' + colorOf(s.label) : null }),
      el('span', { text: s.p != null ? 'p(DS) ' + s.p.toFixed(2) : '' }),
    ]));
    while (log.children.length > 6) log.lastChild.remove();
  }

  /* Every call, in time order, down the feed -- a few seconds however
     big the set -- while the scope scans the sampled candidates with their
     real verdicts. Then the summary. A Skip, because this is a flourish and
     the summary is the result. */
  function verdictReel() {
    paintStage();
    const t = document.getElementById('averyStageText');
    if (t) t.textContent = 'Classified. Every call, in order…';
    const stopBtn = document.getElementById('averyStop');
    if (stopBtn) {
      stopBtn.textContent = 'Skip to the summary';
      stopBtn.onclick = () => summary();
    }
    if (scanT) clearTimeout(scanT);
    phase = 'reel';
    reelDone = false;
    streamDone = false;
    queue = ((result && result.samples) || []).slice();
    const reelMs = Math.max(4000, queue.length * 1350);
    scanNext(() => { reelDone = true; maybeSummary(); });
    const log = document.getElementById('averyLog');
    if (log) { log.innerHTML = ''; log.classList.add('stream'); }
    const rows = ((result && result.rows) || []).slice()
      .sort((a, b) => a.start - b.start);
    /* Paced to finish with the reel, so the calls and the scans end
       together rather than one waiting on the other. */
    const total = reduced() ? 1500 : Math.min(20000, reelMs);
    const tickMs = 40;
    const per = Math.max(1, Math.ceil(rows.length / (total / tickMs)));
    let at = 0;
    const step = () => {
      for (let k = 0; k < per && at < rows.length; k++, at++) feedLine(rows[at]);
      if (t) t.textContent = 'Classified. Every call, in order — '
        + num(at) + ' of ' + num(rows.length);
      if (at < rows.length) { streamT = setTimeout(step, tickMs); return; }
      streamDone = true;
      maybeSummary();
    };
    step();
  }

  function maybeSummary() {
    if (reelDone && streamDone && phase === 'reel') {
      phase = 'summary';
      streamT = setTimeout(summary, 900);
    }
  }

  function feedLine(r) {
    const log = document.getElementById('averyLog');
    if (!log) return;
    log.appendChild(el('div', { class: 'avery-logline' }, [
      el('span', { text: r.start.toFixed(3) + ' s' }),
      el('span', { text: WORD[r.label] || r.label,
                   style: 'color:' + colorOf(r.label) }),
      el('span', { text: r.p != null ? 'p(DS) ' + r.p.toFixed(2) : 'unreadable' }),
    ]));
    log.scrollTop = log.scrollHeight;
  }

  /* ---------- the summary ---------- */
  function summary() {
    phase = 'summary';
    if (scanT) clearTimeout(scanT);
    if (streamT) clearTimeout(streamT);
    streamT = null;
    queue = [];
    scanT = null;
    scanning = false;
    const ov = document.getElementById('averyOv');
    if (!ov || !result) return;
    const r = result;
    const host = document.getElementById('averySummary');
    const scope = ov.querySelector('.avery-scope');
    if (scope) scope.classList.add('done');
    const t = document.getElementById('averyStageText');
    if (t) t.textContent = 'Done. ' + (r.model_name || 'Avery') + ' called '
      + num(r.n) + ' candidates'
      + (r.ds_loss ? ', with up to ' + pct(r.ds_loss, 0) + ' of real spikes '
         + 'allowed to be called Garbage.' : '.');
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
