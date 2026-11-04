/* ==========================================================================
   Tooth Fairy -- AI Beta's best model, sweeping Checkup sets.

   Two doors. Checkup's curation bar offers "Tooth Fairy…" for the set being
   curated; Checkup's header offers "Tooth Fairy batch…" for several sets at
   once. Both ask first -- which sets, and how many real spikes may go with
   the garbage -- then show the scanning screen while the sets are read: now
   and then it takes one real candidate and sweeps across every even channel
   of it. One set ends in a feed of every call and its summary; a batch ends
   in a table of every set, each kept or not on its own.

   Nothing is written until somebody accepts; accepting puts Tooth Fairy's
   calls on the candidates nobody has decided and banks every call as a
   version of the model's own, for the record and for training on edge
   cases.

   Backend: /api/toothfairy*, backend/toothfairy.py.

   PROSPECTOR is the same thing for Panning's pools (2026-11-04), made from
   the same `makeSweeper` -- see the bottom of this file, and
   /api/prospector*, backend/prospector.py.
   ========================================================================== */
/* MADE TWICE (2026-11-04). Prospector is Panning's model, and the user asked
   for it "in the same way tooth fairy is in check up": the same two doors,
   the same dialog, scanning screen, feed, summary and batch, over pooled
   sets and with its own three calls. Everything that differs is in `cfg`,
   at the bottom -- as Braces, Lock and Eye are one `makeBraces`. */
function makeSweeper(cfg) {
  const ORDER = cfg.order;
  const WORD = cfg.word;
  const NAME = cfg.name;
  const API = cfg.api;
  // Each one's own element ids ('tfOv', 'prOv'), so both can be open.
  const I = (n) => cfg.id + n;
  const SEC_PER_CANDIDATE = cfg.secPerCandidate;

  /* THE ICON (asked for 2026-10-09: "a cool icon for the tooth fairy in the
     Check up"). A molar with a fairy's two pairs of wings and a star over
     it, drawn in the current colour so it sits in any button, with the
     star in the accent. `.tf-icon.live` makes the star twinkle and the
     wings beat, for the dialog and the scanning screen; never on a button,
     where moving things pull the eye for no reason. */
  const TF_ICON = '<svg viewBox="0 0 32 32" aria-hidden="true" focusable="false">'
    + '<g class="tf-wings">'
    + '<path class="tf-wing" d="M11 12.5C7.5 11.5 4.2 8.6 4.6 5c3.6.2 6.4 3.1 7.3 6.2z"/>'
    + '<path class="tf-wing" d="M11 15.5c-2.8 1-5.6.6-6.6-1.6 2.4-1 4.9-.5 6.9.9z"/>'
    + '<path class="tf-wing" d="M21 12.5c3.5-1 6.8-3.9 6.4-7.5-3.6.2-6.4 3.1-7.3 6.2z"/>'
    + '<path class="tf-wing" d="M21 15.5c2.8 1 5.6.6 6.6-1.6-2.4-1-4.9-.5-6.9.9z"/>'
    + '</g>'
    + '<path class="tf-tooth" d="M12.2 10.2c1.3-.8 2.6-.5 3.8.3 1.2-.8 2.5-1.1 3.8-.3'
    + ' 1.6 1 1.8 3.3 1.1 5.4-.5 1.5-.8 2.8-.9 4.6-.2 1.8-.6 2.9-1.5 2.9-1 0-1.1-1.5'
    + '-1.4-2.9-.3-.9-.6-1.5-1.1-1.5s-.8.6-1.1 1.5c-.3 1.4-.4 2.9-1.4 2.9-.9 0-1.3'
    + '-1.1-1.5-2.9-.1-1.8-.4-3.1-.9-4.6-.7-2.1-.5-4.4 1.1-5.4z"/>'
    + '<path class="tf-star" d="M16 1.2l.9 2.4 2.4.9-2.4.9-.9 2.4-.9-2.4-2.4-.9 2.4-.9z"/>'
    + '<circle class="tf-dust" cx="26.6" cy="21.5" r=".9"/>'
    + '<circle class="tf-dust" cx="5.4" cy="20.5" r=".7"/>'
    + '<circle class="tf-dust" cx="24" cy="27" r=".6"/>'
    + '</svg>';
  const ICON = cfg.icon || TF_ICON;

  function icon(o) {
    const opt = o || {};
    return el('span', { class: 'tf-icon' + (cfg.iconClass ? ' ' + cfg.iconClass : '')
                               + (opt.live ? ' live' : '')
                               + (opt.big ? ' big' : ''),
                        html: ICON });
  }
  const STAGE = cfg.stages;

  let st = null;         // its status, from API
  let ctx = null;        // {gid, kind, name, n, decided, labels, onDone}
  let job = null;
  let pollT = null;
  let peekRev = -1;
  let queue = [];        // samples waiting to be scanned
  let scanning = false;
  let scanT = null;
  let result = null;
  let filter = null;     // which call the summary list shows
  let batch = null;      // {gids, names} while a batch is set up or running
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
    return BARRY.token(cfg.fallbackColor(lab));
  }

  /* ---------- asking ---------- */
  async function ready() {
    try {
      st = await api(API);
    } catch (e) {
      toast('Could not ask whether ' + NAME + ' is ready: ' + e.message, 'err',
            8000);
      return false;
    }
    if (!st.ready) {
      toast(st.why || NAME + ' is not ready.', 'warn', 9000);
      return false;
    }
    if (st.running) {
      toast(NAME + ' is already sweeping. One at a time.', 'warn', 6000);
      return false;
    }
    return true;
  }

  async function open(o) {
    ctx = Object.assign({}, o || {});
    batch = null;
    if (job) { showOverlay(); return; }
    if (await ready()) confirmDialog();
  }

  /* How many real spikes may go with the garbage, against how much garbage
     is left for a person. Every row is what that bar did on mice the model
     never saw. */
  function toleranceField(onPick) {
    const tols = st.tolerances || [];
    if (!tols.length) return null;
    if (!tols.some((x) => Math.abs(x.ds_loss - tol) < 1e-9)) {
      tol = st.default_tolerance || tols[Math.floor(tols.length / 2)].ds_loss;
    }
    const row = tols.find((x) => Math.abs(x.ds_loss - tol) < 1e-9);
    return BARRY.ui.field({
      label: 'Real spikes that may be called Garbage',
      control: BARRY.ui.seg(tols.map((x) => [x.ds_loss,
        pct(x.ds_loss, 0), 'Garbage cleaned automatically '
        + pct(x.garbage_cleaned) + ', candidates flagged '
        + pct(x.flagged)]), tol, (v) => { tol = v; onPick(); },
        { extra: 'tf-tols' }),
      hint: row ? 'On mice it never saw: ' + pct(row.garbage_cleaned)
        + ' of the garbage cleaned out automatically, '
        + pct(row.garbage_left) + ' left for a person to look at, '
        + pct(row.garbage_into_ds) + ' let into DS; '
        + pct(row.flagged) + ' of all candidates flagged.' : null,
    });
  }

  function modelLine() {
    return dl(NAME, 'Run ' + st.run_id + ' · '
      + ({ hgb: 'gradient-boosted trees', forest: 'random forest',
           blend: 'a blend of five sets of boosted trees',
           logistic: 'logistic regression' }[st.model] || st.model)
      + ' · ' + (st.families || []).length + ' kinds of input · trained on '
      + num(st.n_recordings) + ' recordings');
  }
  /* What its bar did on recordings it never saw, when it says. */
  function modelMore() {
    return cfg.modelMore ? cfg.modelMore(st, { dl, pct, num }) : [];
  }

  function dialogHead(title, sub) {
    return el('div', { class: 'mh tf-mh' }, [
      icon({ live: true, big: true }),
      el('h3', { text: title }),
      sub ? el('span', { class: 'sub', text: sub }) : null,
      el('div', { class: 'spacer' }),
      el('button', { class: 'close-x',
        html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
        onclick: closeModal }),
    ].filter(Boolean));
  }

  function confirmDialog(replace) {
    const mins = Math.max(1, Math.round((ctx.n || 0) * SEC_PER_CANDIDATE / 60));
    showModal(el('div', { class: 'modal tf-confirm' }, [
      dialogHead(NAME, ctx.name || ''),
      el('div', { class: 'mb' }, [
        el('p', { class: 'tf-lede', text: cfg.words.lede }),
        toleranceField(() => confirmDialog(true)),
        el('dl', { class: 'br-dl tf-dl' }, [
          dl(cfg.words.Things, num(ctx.n) + (ctx.decided
            ? ' — ' + num(ctx.decided) + ' already decided by a person, '
              + 'and ' + NAME + ' never changes those' : '')),
          modelLine(),
          ...modelMore(),
          dl('Time', 'about ' + mins + ' minute' + (mins === 1 ? '' : 's')
             + ' the first time; ' + cfg.words.aSet + ' swept before is quicker'),
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
      got = await apiPost(API + '/sweep', {
        gid: ctx.gid, kind: ctx.kind,
        ds_loss: (st.tolerances || []).length ? tol : null });
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
    if (batch) paintBatchProgress();
    if (job.preview_rev !== undefined && job.preview_rev !== peekRev) {
      peekRev = job.preview_rev;
      try {
        const pk = await api(API + '/sweep/' + job.id + '/peek');
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
      if (batch) batchSummary(); else verdictReel();
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
    let ov = document.getElementById(I('Ov'));
    if (!ov) {
      ov = el('div', { class: 'tf-ov', id: I('Ov') });
      document.body.appendChild(ov);
    }
    ov.innerHTML = '';
    ov.appendChild(el('div', { class: 'tf-panel' }, [
      el('div', { class: 'tf-top' }, [
        icon({ live: true, big: true }),
        el('span', { class: 'tf-mark', text: cfg.mark }),
        el('span', { class: 'tf-sep', text: '//' }),
        el('span', { class: 'tf-what', text: batch ? 'BATCH' : 'SWEEP' }),
        el('span', { class: 'tf-set', text: batch
          ? batch.gids.length + ' ' + cfg.words.sets : (ctx.name || '') }),
        el('div', { class: 'spacer' }),
        BARRY.ui.button({ size: 'sm', text: 'Stop', id: I('Stop'),
          title: 'Stop the sweep. Nothing has been written.', onclick: stop }),
      ]),
      el('div', { class: 'tf-scope' }, [
        el('canvas', { id: I('Scope') }),
        el('div', { class: 'tf-read', id: I('Read') }),
        el('div', { class: 'tf-stamp', id: I('Stamp') }),
      ]),
      el('div', { class: 'tf-stage' }, [
        el('span', { id: I('StageText'), text: 'Opening the recording…' }),
        el('span', { class: 'tf-eta', id: I('Eta'), text: '' }),
      ]),
      el('div', { class: 'br-bar tf-bar' }, [el('i', { id: I('Bar') })]),
      el('div', { class: 'tf-log', id: I('Log') }),
      el('div', { id: I('Summary') }),
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
    const ov = document.getElementById(I('Ov'));
    if (ov) ov.remove();
  }

  function paintStage() {
    const stages = (job && job.stages) || [];
    const now = stages.find((x) => x.status === 'running')
             || stages.find((x) => (x.done || 0) < (x.of || 0))
             || stages[stages.length - 1] || {};
    const t = document.getElementById(I('StageText'));
    if (t) {
      t.textContent = (STAGE[now.name] || 'Working')
        + ((now.of || 0) > 1 ? ' — ' + num(Math.min(now.done || 0, now.of))
           + ' of ' + num(now.of) + ' ' + (now.unit || '') : '');
    }
    let total = 0, spent = 0;
    for (const s of stages) {
      const w = /physio$/.test(s.name) ? 4 : /read$/.test(s.name) ? 1 : 0.2;
      if (s.of) { total += w; spent += w * Math.min(1, (s.done || 0) / s.of); }
      else if (s.status === 'done') { total += w; spent += w; }
      else total += w;
    }
    const bar = document.getElementById(I('Bar'));
    if (bar) bar.style.width = Math.round(total ? 100 * spent / total : 0) + '%';
    const eta = document.getElementById(I('Eta'));
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
    const c = document.getElementById(I('Scope'));
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
    const c = document.getElementById(I('Scope'));
    if (!c) return;
    const g = c.getContext('2d');
    grid(g, c.width, c.height);
    /* Until the first candidate is in, the line sweeps an empty grid: a
       still screen for the few seconds the recording takes to open read
       as a hang. */
    if (idleT) clearTimeout(idleT);
    let f = 0;
    const tickIdle = () => {
      const cc = document.getElementById(I('Scope'));
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
    const c = document.getElementById(I('Scope'));
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
    const read = document.getElementById(I('Read'));
    const stamp = document.getElementById(I('Stamp'));
    if (stamp) { stamp.textContent = ''; stamp.className = 'tf-stamp'; }
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
          stamp.className = 'tf-stamp';
          void stamp.offsetWidth;
          stamp.className = 'tf-stamp on hit';
          stamp.style.setProperty('--call', colorOf(s.label));
          const scope = document.querySelector('#' + I('Ov') + ' .tf-scope');
          if (scope) {
            scope.style.setProperty('--call', colorOf(s.label));
            scope.classList.remove('flash');
            void scope.offsetWidth;
            scope.classList.add('flash');
          }
        } else {
          stamp.textContent = 'measured';
          stamp.className = 'tf-stamp on dim';
          stamp.style.setProperty('--call', BARRY.token('--text-3'));
        }
      }
      logLine(s);
      scanT = setTimeout(() => scanNext(onEmpty), s.label ? 650 : 900);
    };
    frame();
  }

  function logLine(s) {
    const log = document.getElementById(I('Log'));
    /* Not while the feed is streaming every call: the feed is the list
       then, and a scan writing into it (and trimming it to six lines)
       scrambled its order. */
    if (!log || log.classList.contains('stream')
        || log.classList.contains('tf-sets')) return;
    log.prepend(el('div', { class: 'tf-logline' }, [
      el('span', { text: (s.t != null ? s.t.toFixed(3) : '?') + ' s' }),
      el('span', { text: s.label ? WORD[s.label] : 'scanned' ,
                   style: s.label ? 'color:' + colorOf(s.label) : null }),
      el('span', { text: s.p != null ? cfg.pWord + ' ' + s.p.toFixed(2) : '' }),
    ]));
    while (log.children.length > 6) log.lastChild.remove();
  }

  /* Every call, in time order, down the feed -- a few seconds however
     big the set -- while the scope scans the sampled candidates with their
     real verdicts. Then the summary. A Skip, because this is a flourish and
     the summary is the result. */
  function verdictReel() {
    paintStage();
    const t = document.getElementById(I('StageText'));
    if (t) t.textContent = 'Classified. Every call, in order…';
    const stopBtn = document.getElementById(I('Stop'));
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
    const log = document.getElementById(I('Log'));
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
    const log = document.getElementById(I('Log'));
    if (!log) return;
    log.appendChild(el('div', { class: 'tf-logline' }, [
      el('span', { text: r.start.toFixed(3) + ' s' }),
      el('span', { text: WORD[r.label] || r.label || 'not read',
                   style: 'color:' + colorOf(r.label) }),
      el('span', { text: r.p != null ? cfg.pWord + ' ' + r.p.toFixed(2) : 'unreadable' }),
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
    const ov = document.getElementById(I('Ov'));
    if (!ov || !result) return;
    const r = result;
    const host = document.getElementById(I('Summary'));
    const scope = ov.querySelector('.tf-scope');
    if (scope) scope.classList.add('done');
    const t = document.getElementById(I('StageText'));
    if (t) t.textContent = 'Done. ' + (r.model_name || NAME) + ' called '
      + num(r.n) + ' ' + cfg.words.things
      + (r.ds_loss ? ', with up to ' + pct(r.ds_loss, 0) + ' of real spikes '
         + 'allowed to be called Garbage.' : '.');
    const bar = document.getElementById(I('Bar'));
    if (bar) bar.style.width = '100%';
    const eta = document.getElementById(I('Eta'));
    if (eta) eta.textContent = r.cached ? 'read before, so only scored' : '';
    const stopBtn = document.getElementById(I('Stop'));
    if (stopBtn) stopBtn.remove();
    host.innerHTML = '';

    host.appendChild(el('div', { class: 'tf-tiles' }, ORDER.map((lab) => {
      const n = (r.counts || {})[lab] || 0;
      return el('button', {
        class: 'tf-tile' + (filter === lab ? ' on' : ''),
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
    if (r.channels_note) notes.push(r.channels_note);
    notes.push(...cfg.notes(r, { pct, num }));
    host.appendChild(el('div', { class: 'tf-notes' },
      notes.map((x) => el('p', { text: x }))));

    const rows = (r.rows || []).filter((x) => !filter || x.label === filter);
    host.appendChild(el('div', { class: 'br-scroll tf-list' }, [
      el('table', { class: 'br-tbl ai-tbl' }, [
        el('thead', {}, [el('tr', {}, ['Time', NAME, cfg.pWord,
          'A person said'].map((h) => el('th', { text: h })))]),
        el('tbody', {}, rows.map((x) => el('tr', {}, [
          el('td', { text: x.start.toFixed(3) + ' s' }),
          el('td', {}, [el('span', { class: 'tf-pill',
                                     style: '--call:' + colorOf(x.label),
                                     text: WORD[x.label] || x.label
                                           || 'not read' })]),
          el('td', { text: x.p == null ? '—' : x.p.toFixed(3) }),
          el('td', { text: x.human ? (cfg.humanWord(x.human, WORD) || x.human)
                           + (x.human_by ? ' (' + x.human_by + ')' : '')
                           : '' }),
        ]))),
      ])]));

    const undecided = (r.n || 0) - (r.already_decided || 0);
    host.appendChild(el('div', { class: 'tf-foot' }, [
      el('p', { class: 'hint', text: cfg.words.acceptHint(num(undecided)) }),
      el('div', { class: 'spacer' }),
      BARRY.ui.button({ text: 'Discard', title: 'Close. Nothing is kept.',
                        onclick: discard }),
      BARRY.ui.button({ kind: 'primary', text: 'Accept and review',
                        id: I('Accept'), onclick: accept }),
    ]));
  }

  async function accept() {
    const b = document.getElementById(I('Accept'));
    if (b) b.disabled = true;
    let res;
    try {
      res = await apiPost(API + '/sweep/' + job.id + '/accept', {});
    } catch (e) {
      if (b) b.disabled = false;
      toast('Could not keep ' + NAME + '’s calls: ' + e.message, 'err', 9000);
      return;
    }
    toast(NAME + '’s calls are on ' + num(res.applied) + ' '
          + cfg.words.things + ' and banked as v' + res.version + ' ('
          + NAME + '). The Flagged pass is next.', 'ok', 8000);
    job = null;
    result = null;
    closeOverlay();
    if (ctx && ctx.onDone) ctx.onDone(res);
  }

  /* Let go of what was swept and not kept: the server holds each sweep
     until it is accepted or let go. */
  function discard() {
    const sids = batch
      ? ((result && result.batch) || []).map((b) => b.sid).filter(Boolean)
      : (job ? [job.id] : []);
    if (sids.length) {
      apiPost(API + '/discard', { sids: sids }).catch(() => {});
    }
    job = null;
    result = null;
    batch = null;
    closeOverlay();
  }

  /* ==================================================================
     THE BATCH (asked for 2026-10-09: "add a Toothfairy batch option")
     ================================================================== */
  let batchSets = [];          // every DS set, for the chooser
  let batchPick = new Set();   // the sets chosen, as "gid/kind"

  async function openBatch(o) {
    ctx = Object.assign({}, o || {});
    if (job) { showOverlay(); return; }
    if (!(await ready())) return;
    let got;
    try {
      got = await api('/api/curation');
    } catch (e) {
      toast('Could not read the curation sets: ' + e.message, 'err', 8000);
      return;
    }
    batchSets = (got.sets || [])
      .filter((x) => BARRY.ui.kindBase(x.kind) === cfg.kind && !x.archived
                     && !x.test
                     && ((x.progress || {}).total || 0) > 0)
      .map((x) => ({
        gid: x.gid,
        kind: x.kind,
        // A set is one bank entry's since 2026-10-20, and a recording can
        // hold several: each is chosen by recording AND kind, and named
        // with its own name beside the recording's.
        key: x.gid + '/' + x.kind,
        name: (x.session_label || x.gid)
              + (x.entry && x.name ? ' · ' + x.name : ''),
        total: (x.progress || {}).total || 0,
        left: (x.progress || {}).left || 0,
        open: !!x.open,
      }))
      .sort((a, b) => (b.open - a.open) || (b.left - a.left)
                      || BARRY.ui.natCompare(a.name, b.name));
    // To start with: what is on the bench and still has something to decide.
    batchPick = new Set(batchSets.filter((x) => x.open && x.left > 0)
                                 .map((x) => x.key));
    batchDialog();
  }

  function batchDialog(replace) {
    const chosen = batchSets.filter((x) => batchPick.has(x.key));
    const n = chosen.reduce((a, x) => a + x.total, 0);
    const mins = Math.max(1, Math.round(n * SEC_PER_CANDIDATE / 60));
    const pickAll = (pred) => {
      batchPick = new Set(batchSets.filter(pred).map((x) => x.key));
      batchDialog(true);
    };
    const list = el('div', { class: 'tf-pick' }, batchSets.length
      ? batchSets.map((x) => el('label', {
          class: 'tf-pick-row' + (batchPick.has(x.key) ? ' on' : ''),
        }, [
          el('input', { type: 'checkbox', checked: batchPick.has(x.key),
            onchange: (ev) => {
              if (ev.target.checked) batchPick.add(x.key);
              else batchPick.delete(x.key);
              batchDialog(true);
            } }),
          el('span', { class: 'tf-pick-name', text: x.name }),
          x.open ? BARRY.ui.chip('on the bench', { flag: true }) : null,
          el('span', { class: 'tf-pick-n', text: num(x.total) + ' ' + cfg.words.things
            + (x.left ? ' · ' + num(x.left) + ' undecided' : ' · all decided') }),
        ].filter(Boolean)))
      : [el('p', { class: 'hint', text: cfg.words.noSets })]);
    showModal(el('div', { class: 'modal tf-confirm tf-batch' }, [
      dialogHead(NAME + ' batch', chosen.length
        ? chosen.length + ' of ' + batchSets.length + ' ' + cfg.words.sets : ''),
      el('div', { class: 'mb' }, [
        el('p', { class: 'tf-lede', text: cfg.words.batchLede }),
        toleranceField(() => batchDialog(true)),
        BARRY.ui.field({
          label: cfg.words.Sets,
          control: el('div', { class: 'tf-pick-wrap' }, [
            el('div', { class: 'ai-row' }, [
              BARRY.ui.button({ kind: 'mini', text: 'On the bench',
                title: 'The sets that are open, with something undecided.',
                onclick: () => pickAll((x) => x.open && x.left > 0) }),
              BARRY.ui.button({ kind: 'mini', text: 'Everything undecided',
                title: 'Every set with a candidate nobody has decided.',
                onclick: () => pickAll((x) => x.left > 0) }),
              BARRY.ui.button({ kind: 'mini', text: 'None',
                onclick: () => pickAll(() => false) }),
            ]),
            list,
          ]),
        }),
        el('dl', { class: 'br-dl tf-dl' }, [
          dl(cfg.words.Things, num(n) + ' in ' + chosen.length + ' '
             + (chosen.length === 1 ? cfg.words.set : cfg.words.sets)),
          modelLine(),
          ...modelMore(),
          dl('Time', 'about ' + mins + ' minute' + (mins === 1 ? '' : 's')
             + ' the first time; ' + cfg.words.sets + ' swept before are quicker'),
        ]),
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        BARRY.ui.button({ text: 'Cancel', onclick: closeModal }),
        BARRY.ui.button({ kind: 'primary', id: I('BatchGo'),
          text: chosen.length ? 'Sweep ' + chosen.length + ' '
                + (chosen.length === 1 ? cfg.words.set : cfg.words.sets)
                : 'Choose ' + cfg.words.aSet,
          disabled: !chosen.length,
          onclick: () => { closeModal(); startBatch(chosen); } }),
      ]),
    ].filter(Boolean)), replace ? { replace: true } : undefined);
  }

  async function startBatch(chosen) {
    let got;
    try {
      got = await apiPost(API + '/batch', {
        sets: chosen.map((x) => ({ gid: x.gid, kind: x.kind })),
        gids: chosen.map((x) => x.gid),
        ds_loss: (st.tolerances || []).length ? tol : null });
    } catch (e) {
      toast(e.message, 'err', 9000);
      return;
    }
    batch = { gids: chosen.map((x) => x.gid),
              names: Object.fromEntries(chosen.map((x) => [x.gid, x.name])) };
    job = got.job;
    result = null;
    queue = [];
    pool = [];
    phase = 'reading';
    peekRev = -1;
    showOverlay();
    paintBatchProgress();
    if (pollT) clearInterval(pollT);
    pollT = setInterval(tick, 800);
  }

  /* Which set is being read, and how every set is getting on. */
  function paintBatchProgress() {
    const log = document.getElementById(I('Log'));
    if (!log || !job) return;
    const ms = job.members || [];
    const at = ms.findIndex((m) => m.status === 'reading');
    const done = ms.filter((m) => m.status === 'done' || m.status === 'failed');
    const t = document.getElementById(I('StageText'));
    if (t && at >= 0) {
      t.textContent = 'Set ' + (at + 1) + ' of ' + ms.length + ' — '
        + ms[at].label + ' · ' + t.textContent;
    }
    const bar = document.getElementById(I('Bar'));
    if (bar && ms.length) {
      const part = parseFloat(bar.style.width) / 100 || 0;
      bar.style.width = Math.round(100 * (done.length + (at >= 0 ? part : 0))
                                   / ms.length) + '%';
    }
    log.classList.add('tf-sets');
    log.innerHTML = '';
    for (const m of ms) {
      log.appendChild(el('div', { class: 'tf-setline ' + m.status }, [
        el('span', { class: 'tf-setdot' }),
        el('span', { text: m.label }),
        el('span', { class: 'tf-setstate', text: {
          waiting: 'waiting', reading: 'sweeping…', done: 'swept',
          failed: 'could not be swept' }[m.status] || m.status }),
      ]));
    }
  }

  function batchSummary() {
    phase = 'summary';
    if (scanT) clearTimeout(scanT);
    if (idleT) clearTimeout(idleT);
    scanT = null;
    idleT = null;
    scanning = false;
    const ov = document.getElementById(I('Ov'));
    if (!ov || !result) return;
    const sets = result.batch || [];
    const ok = sets.filter((b) => b.sid);
    const keep = new Set(ok.filter((b) => b.undecided > 0).map((b) => b.sid));
    const scope = ov.querySelector('.tf-scope');
    if (scope) scope.remove();
    const log = document.getElementById(I('Log'));
    if (log) log.remove();
    const t = document.getElementById(I('StageText'));
    if (t) t.textContent = 'Done. ' + NAME + ' swept ' + ok.length + ' of '
      + sets.length + ' ' + cfg.words.sets
      + (result.ds_loss ? ', with up to ' + pct(result.ds_loss, 0)
         + ' of real spikes allowed to be called Garbage.' : '.');
    const bar = document.getElementById(I('Bar'));
    if (bar) bar.style.width = '100%';
    const stopBtn = document.getElementById(I('Stop'));
    if (stopBtn) stopBtn.remove();
    const host = document.getElementById(I('Summary'));
    const total = (k) => ok.reduce((a, b) => a + ((b.counts || {})[k] || 0), 0);
    host.innerHTML = '';
    host.appendChild(el('div', { class: 'tf-tiles' }, ORDER.map((lab) =>
      el('div', { class: 'tf-tile', style: '--call:' + colorOf(lab) }, [
        el('b', { text: num(total(lab)) }),
        el('span', { text: WORD[lab] }),
        el('i', { text: 'across ' + ok.length + ' ' + cfg.words.sets }),
      ]))));

    const go = BARRY.ui.button({ kind: 'primary', id: I('BatchAccept'),
      text: '', onclick: () => acceptBatch(Array.from(keep)) });
    const paintGo = () => {
      go.textContent = keep.size ? 'Accept ' + keep.size + ' '
        + (keep.size === 1 ? cfg.words.set : cfg.words.sets)
        : 'Choose ' + cfg.words.aSet + ' to keep';
      go.disabled = !keep.size;
    };
    paintGo();
    host.appendChild(el('div', { class: 'br-scroll tf-list' }, [
      el('table', { class: 'br-tbl ai-tbl tf-batch-tbl' }, [
        el('thead', {}, [el('tr', {}, ['Keep', cfg.words.Set]
          .concat(ORDER.map((lab) => cfg.short[lab]))
          .concat(['Agreed with a person', '']).map((h) =>
          el('th', { text: h })))]),
        el('tbody', {}, sets.map((b) => {
          const c = b.counts || {};
          const cell = (lab) => el('td', { class: 'tf-num' }, [
            el('span', { class: 'tf-pill', style: '--call:' + colorOf(lab),
                         text: num(c[lab] || 0) })]);
          return el('tr', { class: b.sid ? '' : 'tf-failed' }, [
            el('td', {}, b.sid ? [el('input', { type: 'checkbox',
              checked: keep.has(b.sid),
              title: b.undecided ? 'Put its calls on its ' + num(b.undecided)
                + ' undecided candidates' : 'Nothing is undecided here; '
                + 'keeping it only banks the calls',
              onchange: (ev) => {
                if (ev.target.checked) keep.add(b.sid); else keep.delete(b.sid);
                paintGo();
              } })] : []),
            el('td', { class: 'ai-wrap', text: b.name }),
          ].concat(b.sid ? ORDER.map(cell) : [el('td', { colspan: ORDER.length,
              class: 'tf-err', text: b.error || 'Could not be swept.' })])
           .concat([
            el('td', { text: cfg.agreed(b.agreement, { pct, num }) }),
            el('td', { class: 'hint', text: b.sid
              ? (b.undecided ? num(b.undecided) + ' undecided'
                             : 'all decided already')
                + (b.channels_note ? ' · read whole (probe in columns)' : '')
              : '' }),
          ]));
        })),
      ])]));
    host.appendChild(el('div', { class: 'tf-foot' }, [
      el('p', { class: 'hint', text: cfg.words.batchAcceptHint }),
      el('div', { class: 'spacer' }),
      BARRY.ui.button({ text: 'Discard all', onclick: discard }),
      go,
    ]));
  }

  async function acceptBatch(sids) {
    const b = document.getElementById(I('BatchAccept'));
    if (b) b.disabled = true;
    let res;
    try {
      res = await apiPost(API + '/accept', { sids: sids });
    } catch (e) {
      if (b) b.disabled = false;
      toast('Could not keep ' + NAME + '’s calls: ' + e.message, 'err', 9000);
      return;
    }
    const rows = res.results || [];
    const good = rows.filter((x) => x.status === 200);
    const applied = good.reduce((a, x) => a + (x.applied || 0), 0);
    const bad = rows.filter((x) => x.status !== 200);
    toast(NAME + '’s calls are on ' + num(applied) + ' ' + cfg.words.things
          + ' in ' + good.length + ' '
          + (good.length === 1 ? cfg.words.set : cfg.words.sets)
          + (bad.length ? '; ' + bad.length + ' could not be kept ('
             + (bad[0].error || '') + ')' : '') + '.',
          bad.length ? 'warn' : 'ok', 9000);
    // What was not kept is let go.
    const rest = ((result && result.batch) || []).map((x) => x.sid)
      .filter((sid) => sid && !sids.includes(sid));
    if (rest.length) apiPost(API + '/discard', { sids: rest }).catch(() => {});
    job = null;
    result = null;
    batch = null;
    closeOverlay();
    if (ctx && ctx.onDone) ctx.onDone(res);
  }

  return { open: open, openBatch: openBatch, icon: icon,
           running: () => !!job };
}

/* Tooth Fairy, sweeping Checkup's dentate spike sets -- as it always was. */
BARRY.toothFairy = makeSweeper({
  id: 'tf', name: 'Tooth Fairy', mark: 'TOOTH FAIRY', api: '/api/toothfairy',
  kind: 'ds',
  order: ['spike', 'review', 'flag', 'garbage'],
  word: {
    spike: 'DS', review: 'Flag for Deep Review', flag: 'Flag',
    garbage: 'Garbage',
  },
  short: { spike: 'DS', review: 'Deep review', flag: 'Flag',
           garbage: 'Garbage' },
  /* Measured on this machine, 2026-10-02, both reads, six stretches at a
     time: 0.19 s a candidate (451, network share), 0.36 (385) and 0.49
     (173, local disk -- small sets spread thin). Only for the sentence in
     the confirm dialog. */
  secPerCandidate: 0.4,
  stages: {
    'tf read': 'Reading each candidate’s shape',
    'tf physio': 'Reading the physiology around each one',
    'tf score': 'Scoring',
  },
  pWord: 'p(DS)',
  fallbackColor: (lab) => (lab === 'spike' ? '--ok'
                           : lab === 'garbage' ? '--err' : '--warn'),
  humanWord: (h, word) => word[h],
  agreed: (a, f) => (a && a.compared
    ? f.pct(a.agree / a.compared, 0) + ' of ' + f.num(a.compared) : '—'),
  notes: (r, f) => {
    const out = [];
    const ho = r.held_out || {};
    const share = (lab, of) => {
      const b = ho[lab];
      return b && b.n ? (of === 'ds' ? b.n_ds : b.n_garbage) / b.n : null;
    };
    if (ho.spike) {
      out.push('On mice it never saw, ' + f.pct(share('spike', 'ds'))
        + ' of what Tooth Fairy called DS really was, and '
        + f.pct(share('garbage', 'garbage')) + ' of what it called Garbage '
        + 'really was. Flag for Deep Review is the stretch just under its DS '
        + 'bar; Flag is everything between.');
    }
    if (r.agreement && r.agreement.compared) {
      out.push(f.num(r.already_decided) + ' of these were already decided '
        + 'by a person. Where both said DS or Garbage, Tooth Fairy agreed on '
        + f.pct(r.agreement.agree / r.agreement.compared) + '. Those '
        + 'decisions stay as they are.');
    }
    if (r.n_readable < r.n) {
      out.push(f.num(r.n - r.n_readable) + ' could not be read (too near '
        + 'either end of the recording, or in a gap) and are marked Flag.');
    }
    return out;
  },
  words: {
    lede: 'Tooth Fairy reads every candidate in this set — its shape, the '
        + 'shank around it, unit firing and the second either side — and '
        + 'calls each one DS, Flag for Deep Review, Flag or Garbage.',
    batchLede: 'Tooth Fairy sweeps each set you choose, one after another, '
             + 'and calls every candidate DS, Flag for Deep Review, Flag or '
             + 'Garbage. At the end you see every set and keep the ones you '
             + 'want; a person’s decisions are never changed.',
    things: 'candidates', Things: 'Candidates',
    set: 'set', sets: 'sets', aSet: 'a set', Set: 'Set', Sets: 'Sets',
    noSets: 'No dentate spike sets to sweep.',
    acceptHint: (n) => 'Accept and review puts Tooth Fairy’s calls on the '
      + n + ' candidates nobody has decided, and banks every call as a Tooth '
      + 'Fairy version of this set — kept for the record and for training '
      + 'on edge cases later. Then work through the flags.',
    batchAcceptHint: 'Keeping a set puts Tooth Fairy’s calls on its '
      + 'undecided candidates and banks every call as a Tooth Fairy version '
      + 'of it. Sets left unticked are let go; nothing is written to them.',
  },
});

/* PROSPECTOR, Panning's model (2026-11-04): Tooth Fairy's two doors over
   pooled sets -- "Prospector…" in Panning's bar for the pool open, and
   "Prospector batch…" on Panning's page for several. Its three calls:
   Spike, kept for the ones it is sure of, and two flags only it gives
   (curation.KINDS, `ai`). Never Garbage. backend/prospector.py.

   THE ICON: a prospector's pan with gold in it and a glint over it --
   "prospectors pan a river for what is worth keeping" (panning.js). The pan
   in the current colour, the gold and the glint in the accent; `.live`
   swirls the pan and the glint catches the light. */
const PR_ICON = '<svg viewBox="0 0 32 32" aria-hidden="true" focusable="false">'
  + '<g class="pr-panning">'
  + '<path class="pr-pan" d="M3.5 15.5c.6 6.2 6 10 12.5 10s11.9-3.8 12.5-10z"/>'
  + '<ellipse class="pr-rim" cx="16" cy="15.5" rx="12.5" ry="2.6"/>'
  + '<path class="pr-water" d="M7.5 19.2c1.6-.9 3.1.9 4.7 0s3.1.9 4.7 0'
  + ' 3.1.9 4.7 0 3.1.9 3.4.4"/>'
  + '<path class="pr-nugget" d="M11.2 21.2l1.5-1.3 1.9.4.4 1.5-1.6 1-1.9-.3z"/>'
  + '<path class="pr-nugget" d="M16.6 22.3l1.2-1.1 1.5.3.2 1.2-1.3.8-1.4-.2z"/>'
  + '<path class="pr-nugget" d="M20.2 20.1l1-.9 1.2.3.1 1-1.1.6-1.1-.2z"/>'
  + '</g>'
  + '<path class="pr-glint" d="M23.5 1.5l.9 2.4 2.4.9-2.4.9-.9 2.4-.9-2.4'
  + '-2.4-.9 2.4-.9z"/>'
  + '<circle class="pr-dust" cx="6.5" cy="8.5" r=".8"/>'
  + '<circle class="pr-dust" cx="28" cy="10" r=".6"/>'
  + '</svg>';

BARRY.prospector = makeSweeper({
  id: 'pr', name: 'Prospector', mark: 'PROSPECTOR', api: '/api/prospector',
  kind: 'pooled',
  icon: PR_ICON, iconClass: 'pr-icon',
  order: ['spike', 'likely_spike', 'likely_garbage'],
  word: {
    spike: 'Spike', likely_spike: 'Flag · likely spike',
    likely_garbage: 'Flag · likely garbage',
  },
  short: { spike: 'Spike', likely_spike: 'Likely spike',
           likely_garbage: 'Likely garbage' },
  // Both of Tooth Fairy's reads, which are what it costs; the same rate.
  secPerCandidate: 0.4,
  stages: {
    'pr read': 'Reading each event’s shape',
    'pr physio': 'Reading the physiology around each one',
    'pr score': 'Scoring',
  },
  pWord: 'p(spike)',
  fallbackColor: (lab) => (lab === 'spike' ? '--ok'
                           : lab === 'likely_garbage' ? '--err' : '--warn'),
  humanWord: (h, word) => ({ spike: 'Spike', garbage: 'Garbage',
                             flag: 'Flag' }[h] || word[h]),
  agreed: (a, f) => {
    const s = (a || {}).spike || {};
    return s.compared ? f.pct(s.agree / s.compared, 0) + ' of '
      + f.num(s.compared) + ' Spike' : '—';
  },
  /* The bar, and what it did on recordings it never saw, in the dialogs. */
  modelMore: (st, f) => {
    const h = st.held_out || {};
    const rows = [];
    if (st.t_spike != null) {
      rows.push(f.dl('Spike bar', 'a score of ' + Number(st.t_spike).toFixed(3)
        + ' or more — above ' + f.pct(st.target, 0) + ' of the garbage in '
        + 'the recordings it learned from'));
    }
    if (h.spike_called) {
      rows.push(f.dl('Tested', 'on recordings it never saw, that bar called '
        + f.num(h.spike_called) + ' events Spike: '
        + f.pct(h.spike_recall, 0) + ' of the real spikes, and '
        + f.num(h.garbage_into_spike) + ' garbage ('
        + f.pct(h.garbage_into_spike / h.spike_called) + ' of its calls)'));
    }
    return rows;
  },
  notes: (r, f) => {
    const out = [];
    const h = r.held_out || {};
    if (h.spike_called) {
      out.push('On recordings it never saw, its Spike bar called '
        + f.pct(h.spike_recall, 0) + ' of the real spikes Spike, and '
        + f.pct(h.garbage_into_spike / h.spike_called) + ' of its Spike '
        + 'calls were garbage. Under the bar, a score of '
        + Number((r.policy || {}).t_lean || 0.5).toFixed(1) + ' or more is '
        + 'Flag · likely spike, and the rest Flag · likely garbage: both '
        + 'want a person.');
    }
    const a = (r.agreement || {}).spike || {};
    if (r.already_decided) {
      out.push(f.num(r.already_decided) + ' of these were already decided '
        + 'by a person' + (a.compared ? '. Of those it called Spike, a '
          + 'person had said Spike for ' + f.pct(a.agree / a.compared) : '')
        + '. Those decisions stay as they are.');
    }
    const un = (r.counts || {}).unread || 0;
    if (un) {
      out.push(f.num(un) + ' could not be read (too near either end of the '
        + 'recording, or in a gap) and get no call.');
    }
    return out;
  },
  words: {
    lede: 'Prospector reads every event in this pool — its shape, the shank '
        + 'around it, unit firing and the second either side, as Tooth Fairy '
        + 'does, and which detector found it — and calls each one Spike, '
        + 'Flag · likely spike or Flag · likely garbage. It never calls '
        + 'Garbage: Spike is for the ones it is sure of, and the rest are '
        + 'left for you, leaning one way or the other.',
    batchLede: 'Prospector sweeps each pool you choose, one after another, '
             + 'and calls every event Spike, Flag · likely spike or Flag · '
             + 'likely garbage. At the end you see every pool and keep the '
             + 'ones you want; a person’s decisions are never changed.',
    things: 'events', Things: 'Events',
    set: 'pool', sets: 'pools', aSet: 'a pool', Set: 'Pool', Sets: 'Pools',
    noSets: 'No pooled sets to sweep.',
    acceptHint: (n) => 'Accept and review puts Prospector’s calls on the '
      + n + ' events no person has decided, and banks every call as a '
      + 'Prospector version of this pool — its first calls, kept to hold '
      + 'against what people decide. Then work through the flags.',
    batchAcceptHint: 'Keeping a pool puts Prospector’s calls on the events '
      + 'no person has decided and banks every call as a Prospector version '
      + 'of it. Pools left unticked are let go; nothing is written to them.',
  },
});
