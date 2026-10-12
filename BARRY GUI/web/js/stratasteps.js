/* ==========================================================================
   stratasteps.js -- StrataScope's steps: from painting labels to a method.

   strata.js is the rail: pick channels, name a layer. That stays, for the
   odd channel. This is the part that says where the lines should go and
   why:

     0  Theta Walk          paint when the animal was walking, by hand, over
                            a guide strip of theta/delta, probe agreement,
                            the finder's ghost bouts and a 4-12 Hz
                            spectrogram
     1  Crystallize CA1     so / sp / sr / slm and the fissure
     2  Find the hilus      the two granule layers, the hilus between
     3  GCL IML MML OML     the molecular layer in thirds (Method A), checked
                            by pathway-specific gamma (Method B, ICA)
     4  Sign off            checks, then a version that keeps how it was
                            decided

   Every proposal is ghost lines -- dashed, on the depth strip beside the
   rail, on the traces and in the evidence window -- that you drag and then
   Accept. Each line's anchor says which measurement placed it (the lead)
   and what the others say (votes, with how many channels they disagree
   by); clicking a vote makes it the lead.

   NO DENTATE SPIKES anywhere in here, on purpose: these labels are what the
   DS results get checked against (see backend/stratasteps.py).

   The numbers are backend/stratasteps.py, through /api/strata/<gid>/*. The
   decisions are the layer sheet's strata_* fields (backend/layers.py).
   ========================================================================== */
'use strict';

BARRY.strataSteps = (function () {
  const STEPS = [
    { id: '0', name: 'Theta Walk', title: 'Step 0 · Theta Walk',
      blurb: 'Paint when the animal was walking. Theta curves, gamma and ICA '
           + 'use these seconds; ripples use the rest, less a buffer.' },
    { id: '1', name: 'CA1', title: 'Step 1 · Crystallize CA1',
      blurb: 'The pyramidal layer from ripples, the fissure from theta, and '
           + 'the CA1 layers between them.' },
    { id: '2', name: 'Hilus', title: 'Step 2 · Find the hilus',
      blurb: 'The two granule layers from multiunit activity, and the hilus '
           + 'between them. No dentate spikes: these labels are what DS '
           + 'results get checked against.' },
    { id: '3', name: 'GCL · IML · MML · OML', title: 'Step 3 · Define GCL, '
           + 'IML, MML, OML',
      blurb: 'The molecular layer cut in thirds between the fissure and the '
           + 'granule layer (Method A), checked by where slow and fast gamma '
           + 'generators sit (Method B, ICA).' },
    { id: '4', name: 'Sign off', title: 'Step 4 · Sign off',
      blurb: 'The checks, then a version of the sheet that keeps the '
           + 'parameters, the confidence of every line and who signed it.' },
  ];

  /* The depth curves. Colours are theme tokens, read when drawn, so the
     strip follows the theme like everything else. */
  const CURVES = [
    { id: 'mua', name: 'MUA', tok: '--c1',
      why: 'Multiunit power, 300-6000 Hz, all the time. Peaks where cells '
         + 'are packed: the pyramidal and granule layers.' },
    { id: 'ripple', name: 'Ripple', tok: '--event',
      why: 'Ripple-band power, 120-180 Hz, still time. Largest at the '
         + 'pyramidal layer, where ripples are made.' },
    { id: 'theta', name: 'Theta', tok: '--c3',
      why: 'Theta power, 6-10 Hz, Theta Walk. Largest near the fissure, and '
         + 'often again in the dentate.' },
    { id: 'theta_phase', name: 'Phase', tok: '--c4',
      why: 'How early or late each channel’s theta is, against the '
         + 'reference channel (the stopwatch). Shifts by about half a cycle '
         + 'from sp to the fissure.' },
    { id: 'theta_coherence', name: 'Coherence', tok: '--c5',
      why: 'How closely each channel’s theta follows the reference '
         + 'channel. Drops where a layer boundary is crossed.' },
    { id: 'slow_gamma', name: 'Slow γ', tok: '--c2',
      why: 'Slow gamma, 25-45 Hz, Theta Walk. A stratum radiatum marker.' },
    { id: 'mid_gamma', name: 'Mid γ', tok: '--warn',
      why: 'Mid gamma, 60-100 Hz, Theta Walk. Marks slm and the dentate '
         + 'molecular layer.' },
  ];
  const CONF = ['sure', 'likely', 'guess'];
  const CONF_WHY = {
    sure: 'You checked this line against the evidence and would defend it.',
    likely: 'The evidence mostly agrees; you have not checked it closely.',
    guess: 'Placed by geometry or a weak signal. Treat labels next to it '
         + 'as uncertain.',
  };
  /* How a line is drawn says how sure it is, everywhere it is drawn. */
  const CONF_DASH = { sure: [], likely: [7, 4], guess: [2, 4] };

  /* What each step is about. Everything else is greyed out while it is
     open (2026-10-12: "way too many lines and colours at one time"):

       regions  the layers the step writes; boundaries of any other layer
                go grey, and channels outside what Accept would write are
                dimmed on the rail, the strip, the traces and the aid
                window
       lead     the curves the step's lines are placed by, drawn full
       votes    the curves that vote, drawn faint
     Every other curve is off until somebody turns it on. */
  const FOCUS = {
    0: { regions: [], lead: ['theta'], votes: [] },
    1: { regions: ['ca1_so', 'ca1_sp', 'ca1_rad', 'ca1_slm', 'ca1_sr'],
         lead: ['ripple', 'theta'], votes: ['mua', 'theta_phase'] },
    2: { regions: ['dg_gcl1', 'hil', 'dg_gcl2', 'dg', 'dg2'],
         lead: ['mua'], votes: ['theta'] },
    3: { regions: ['dg_oml1', 'dg_mml1', 'dg_iml1', 'dg_gcl1', 'hil',
                   'dg_gcl2', 'dg_iml2', 'dg_mml2', 'dg_oml2', 'dg', 'dg2',
                   'thal'],
         lead: ['mua', 'theta'], votes: [] },
    // Sign off: everything, every layer in colour and every curve.
    4: { regions: null, lead: ['mua', 'ripple', 'theta', 'theta_phase',
                               'theta_coherence', 'slow_gamma', 'mid_gamma'],
         votes: [] },
  };
  const STRIP_W = 150;

  let H = null;            // the host: hooks strata.js hands over on enter
  let status = null;       // whether this recording has been read
  let estimate = null;     // seconds a read would take here
  let jobId = null;        // a read or an ICA running
  let jobKind = null;
  let jobSnap = null;
  let open = null;         // which step is open, '0'..'4', or null
  let sug = null;          // the last /suggest answer
  let guide = null;        // the last /guide answer (Step 0)
  let ghost = null;        // {step, lines: [...]} -- the editable proposal
  let overrides = {};      // anchors moved by clicking a vote
  let shown = new Set(['mua', 'theta']);
  let checks = null;
  let ica = null;
  let busy = '';
  let more = false;        // the step's ▸ More
  let loadSeq = 0;
  let wheelDraft = { on: '', off: '', note: '' };
  let stripCanvas = null;
  let strip = { top: 0, height: 0, lane: 0, n: 0 };
  let drag = null;         // a line being dragged on the depth strip
  let paint = null;        // a bout being painted on the Step 0 strip
  let saveTimer = null;
  let rev = 0;

  /* ==================================================================
     In and out
     ================================================================== */
  async function enter(host) {
    H = host;
    status = null; sug = null; guide = null; ghost = null; overrides = {};
    checks = null; ica = null; open = null; jobId = null; busy = '';
    await refreshStatus();
    if (status && status.scanned && status.current) await load();
    H.render();
  }

  function leave() {
    if (saveTimer) { clearTimeout(saveTimer); flushStates(); }
    publish({ off: true });
    const body = document.getElementById('xfBody');
    if (body) {
      const d = body.querySelector('.ss-drawer');
      if (d) d.remove();
      body.classList.remove('ss-drawer-on');
    }
    H = null; status = null; sug = null; guide = null; ghost = null;
    stripCanvas = null; open = null;
  }

  const sheet = () => (H && H.sheet()) || null;
  const strata = () => ((sheet() || {}).strata) || {};
  const allChans = () => (H.allChannels ? H.allChannels() : H.channels());
  const body = (extra) => Object.assign({
    path: H.path(), channels: allChans().map((c) => c.number),
  }, extra || {});
  const url = (what) => '/api/strata/' + encodeURIComponent(H.gid) + '/' + what;

  async function refreshStatus() {
    try {
      const res = await apiPost(url('status'), body());
      status = res.status;
      estimate = res.estimate_s;
      status.probe = res.probe;
    } catch (e) {
      status = { scanned: false, error: e.message };
    }
  }

  /* Everything the steps show, in one request. */
  async function load(keepGhost) {
    if (!H) return;
    confirming = null;            // it listed changes for the old lines
    const mine = ++loadSeq;
    busy = 'Working out the depth curves and proposals…';
    H.render();
    try {
      const res = await apiPost(url('suggest'), body({ overrides }));
      if (mine !== loadSeq || !H) return;
      sug = res;
      if (!keepGhost || !ghost || ghost.step !== open) resetGhost();
      busy = '';
    } catch (e) {
      if (mine !== loadSeq) return;
      busy = '';
      toast('StrataScope could not work out the steps: ' + e.message,
            'err', 9000);
    }
    if (!H) return;
    H.render();
    drawStrip();
    H.redraw();
    publish();
  }

  function resetGhost() {
    if (!sug || !open || !sug.steps || !sug.steps[open]) { ghost = null; return; }
    const lines = (sug.steps[open].lines || []).map((ln) => Object.assign({}, ln));
    /* A line somebody already rated keeps its rating. */
    const conf = strata().confidence || {};
    for (const ln of lines) if (conf[ln.id]) ln.confidence = conf[ln.id];
    ghost = { step: open, lines };
  }

  /* ==================================================================
     Reading the recording
     ================================================================== */
  async function scan(force) {
    if (!H || jobId) return;
    try {
      const res = await apiPost(url('scan'), body({ force: !!force }));
      if (res.cached) {
        status = res.status;
        await load();
        return;
      }
      jobId = res.job.id; jobKind = 'scan'; jobSnap = res.job;
      estimate = res.estimate_s || estimate;
      H.render();
      poll();
    } catch (e) {
      toast('Could not start the read: ' + e.message, 'err', 9000);
    }
  }

  async function poll() {
    while (jobId && H) {
      await new Promise((r) => setTimeout(r, 1200));
      if (!jobId || !H) return;
      let snap;
      try {
        snap = (await api('/api/cfc/job/' + jobId)).job;
      } catch (e) { continue; }
      jobSnap = snap;
      if (snap.status === 'running') { renderJob(); continue; }
      const kind = jobKind;
      jobId = null; jobKind = null;
      if (snap.status !== 'done') {
        toast((kind === 'ica' ? 'ICA' : 'The read') + ' stopped: '
              + (snap.error || snap.status), 'err', 9000);
        H.render();
        return;
      }
      if (kind === 'scan') {
        await refreshStatus();
        await load();
        if (open === '0') await loadGuide();
      } else if (kind === 'ica') {
        await peekIca();
        await load(true);
      }
      return;
    }
  }

  function jobPct() {
    const st = (jobSnap && jobSnap.stages) || [];
    const s = st.find((x) => x.status === 'running') || st[0];
    if (!s || !s.of) return 0;
    return Math.round(100 * (s.done || 0) / s.of);
  }

  function renderJob() {
    const bar = document.querySelector('.ss-job i');
    const txt = document.querySelector('.ss-job span');
    if (bar) bar.style.width = jobPct() + '%';
    if (txt) txt.textContent = jobText();
  }

  function jobText() {
    const st = ((jobSnap && jobSnap.stages) || [])[0] || {};
    if (jobKind === 'ica') return 'Unmixing the gamma field — '
      + jobPct() + '%';
    return 'Reading every channel — ' + (st.done || 0) + ' of '
      + (st.of || '?') + ' done';
  }

  /* ==================================================================
     The bar: the step row, then whatever the open step needs
     ================================================================== */
  /* Is stamp a after stamp b? As times, not strings: the stamps come from
     the server (UTC, microseconds) and from this page (toISOString), and
     older sheets carry local "-0400" ones. */
  function later(a, b) {
    const ta = Date.parse(a), tb = Date.parse(String(b).replace(
      /([+-]\d\d)(\d\d)$/, '$1:$2'));
    const ua = isFinite(ta) ? ta : Date.parse(String(a).replace(
      /([+-]\d\d)(\d\d)$/, '$1:$2'));
    if (isFinite(ua) && isFinite(tb) && ua !== tb) return ua > tb;
    return String(a) > String(b);
  }

  function stepState(id) {
    const steps = strata().steps || {};
    const me = steps[id];
    if (!me || me.status !== 'done') return 'todo';
    // Something before it changed since it was accepted.
    for (const s of STEPS) {
      if (s.id >= id) break;
      const other = steps[s.id];
      if (other && other.at && me.at && later(other.at, me.at)) {
        return 'stale';
      }
    }
    return 'done';
  }

  function section() {
    const box = el('div', { class: 'ss', id: 'strataSteps' });
    if (!H) return box;
    /* One row, and only one, until Step 0 is open: the bar's height is the
       traces' height, and the rail's lanes are cut from the traces
       (web/_dev/stratacheck.html holds this). Whether the recording has
       been read, and the read's progress, sit in the same row. */
    box.appendChild(stepRow());
    if (status && status.scanned && status.current && jobKind !== 'scan'
        && open === '0') {
      box.appendChild(stepZero());
    }
    return box;
  }

  /* Steps 1-4 live in a drawer down the right of the traces, not in the
     bar under them. In the bar they took the height the traces need -- in a
     1000 px window the pane came down to a few pixels, the rail's lanes with
     it, and a dashed line could not be dragged because a channel was
     0.03 px tall. The drawer takes width instead, which the traces can
     spare; the lanes keep their height. */
  const DRAWER_W = 420;

  function drawer() {
    const body = document.getElementById('xfBody');
    if (!body) return;
    let d = body.querySelector('.ss-drawer');
    const want = !!(H && status && status.scanned && status.current
                    && open && open !== '0' && jobKind !== 'scan');
    if (!want) {
      if (d) d.remove();
      body.classList.remove('ss-drawer-on');
      return;
    }
    if (!d) {
      d = el('aside', { class: 'ss-drawer' });
      body.appendChild(d);
    }
    const keep = d.scrollTop;
    d.innerHTML = '';
    d.appendChild(open === '4' ? stepFour() : stepAnchors(open));
    d.scrollTop = keep;
    body.classList.add('ss-drawer-on');
    document.documentElement.style.setProperty('--ss-drawer-w',
                                               DRAWER_W + 'px');
  }

  function stepRow() {
    const row = el('div', { class: 'ss-row' });
    for (const s of STEPS) {
      const st = stepState(s.id);
      row.appendChild(el('button', {
        class: 'ss-step ' + st + (open === s.id ? ' on' : ''),
        title: s.blurb + (st === 'done' ? '\nDone.' : st === 'stale'
          ? '\nNeeds a look: an earlier step changed after this one was '
            + 'accepted.' : ''),
        disabled: (status && status.scanned && status.current) ? null
          : 'disabled',
        onclick: () => openStep(open === s.id ? null : s.id),
      }, [
        el('span', { class: 'ss-tick', text: st === 'done' ? '✓'
          : st === 'stale' ? '!' : s.id }),
        el('span', { text: s.name }),
      ]));
    }
    if (status && status.error) {
      row.appendChild(el('span', { class: 'ss-say err', text: status.error }));
    } else if (!status || !status.scanned || !status.current
               || jobKind === 'scan') {
      row.appendChild(readCard());
    } else if (busy) {
      row.appendChild(el('span', { class: 'ss-say', text: busy }));
    }
    if (status && status.scanned && status.current) {
      row.appendChild(el('button', {
        class: 'mini', text: 'Evidence window',
        title: 'The step’s evidence -- triggered averages, the phase '
             + 'and coherence, ICA -- in a second window that follows this '
             + 'one.',
        onclick: openAids,
      }));
    }
    return row;
  }

  function readCard() {
    const wrap = el('span', { class: 'ss-read' });
    if (jobKind === 'scan') {
      wrap.appendChild(el('div', { class: 'ss-job' }, [
        el('i', { style: 'width:' + jobPct() + '%' }),
        el('span', { text: jobText() }),
      ]));
      wrap.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Stop',
        onclick: () => apiPost('/api/cfc/job/' + jobId + '/cancel', {}),
      }));
      return wrap;
    }
    const mins = estimate ? Math.max(1, Math.round(estimate / 60)) : null;
    const stale = status && status.scanned && !status.current;
    wrap.appendChild(el('button', {
      class: 'btn sm', text: (stale ? 'Read it again' : 'Read the recording')
        + (mins ? ' · about ' + mins + ' min' : ''),
      title: (stale ? 'The files changed since this recording was last '
                      + 'read.\n' : '')
           + 'The steps need every channel read once: ripples, theta, gamma '
           + 'and multiunit power, second by second. After that every '
           + 'answer comes back at once.',
      onclick: () => scan(true),
    }));
    return wrap;
  }

  async function openStep(id) {
    open = id;
    confirming = null;
    icaPick = null;
    more = false;
    // Only what this step is decided from; the rest are a click away.
    const f = FOCUS[id];
    shown = new Set(f ? f.lead.concat(f.votes) : ['mua', 'theta']);
    resetGhost();
    if (id === '0' && !guide) await loadGuide();
    if (id === '4') await loadChecks();
    if (id === '3' && !ica) peekIca();
    H.render();
    drawStrip();
    H.redraw();
    publish();
  }

  /* ---------- Step 0: Theta Walk ---------- */
  async function loadGuide() {
    try {
      const res = await apiPost(url('guide'), body());
      guide = res;
    } catch (e) {
      toast('Could not draw the Theta Walk guide: ' + e.message, 'err', 8000);
    }
    if (H) H.render();
  }

  const walk = () => ((strata().states || {}).theta_walk || []);

  function fmtT(t) {
    const m = Math.floor(t / 60), s = Math.round(t - 60 * m);
    return m + ':' + String(s).padStart(2, '0');
  }

  function parseT(txt) {
    const v = String(txt || '').trim();
    if (!v) return null;
    const p = v.split(':').map(Number);
    if (p.some((x) => !isFinite(x))) return null;
    return p.length === 2 ? p[0] * 60 + p[1] : p[0];
  }

  function stepZero() {
    const box = el('div', { class: 'ss-zero' });
    const m = (sug && sug.masks) || (guide && guide.masks) || {};
    const secs = walk().reduce((a, b) => a + (b[1] - b[0]), 0);
    /* One line for what it is, what is painted and what to do next, so the
       strip -- the thing being worked on -- gets the height. */
    box.appendChild(el('div', { class: 'ss-zero-head' }, [
      el('strong', { text: STEPS[0].title }),
      el('span', { class: 'ss-say' + (walk().length ? '' : ' warn'),
                   text: walk().length
        ? walk().length + ' bout' + (walk().length === 1 ? '' : 's') + ', '
          + fmtT(secs) + ' of Theta Walk · ' + fmtT(m.still_s || 0)
          + ' still'
        : 'Nothing painted yet: theta will average the whole recording, '
          + 'dentate spikes and sharp waves included.' }),
      el('div', { style: 'flex:1' }),
      el('button', {
        class: 'btn ghost sm', text: 'Paint the finder’s bouts',
        title: 'Adds every ghost bout to Theta Walk. They are yours from '
             + 'then on: erase any you disagree with.',
        disabled: (guide && guide.guide && guide.guide.ghost.length) ? null
          : 'disabled',
        onclick: () => setWalk(merge(walk().concat(guide.guide.ghost))),
      }),
      el('button', {
        class: 'btn ghost sm', text: 'Clear',
        title: 'Clear every painted Theta Walk bout',
        disabled: walk().length ? null : 'disabled',
        onclick: () => setWalk([]),
      }),
      el('button', {
        class: 'btn sm', text: 'Done — on to CA1',
        onclick: async () => {
          await flushStates();
          await accept('0', {});
          openStep('1');
        },
      }),
    ]));
    const cv = el('canvas', {
      class: 'ss-tw', height: '128',
      title: 'Drag to paint Theta Walk; shift-drag to erase; a click moves '
           + 'the traces there.\nTop: spectrogram, 4-12 Hz. Middle: '
           + 'theta/delta, the dashed line is the finder’s threshold; '
           + 'hatched is where the finder would put bouts. Bottom: how much '
           + 'of the probe agrees on one theta frequency.',
    });
    box.appendChild(el('div', { class: 'ss-tw-wrap' }, [cv]));
    box.appendChild(wheelBox());
    /* Drawn once it is on the page, because it is sized from the page. A
       timer as well as a frame: whichever comes first (drawWalk is
       idempotent), and a frame alone never comes in a hidden tab. */
    setTimeout(() => drawWalk(cv), 0);
    requestAnimationFrame(() => drawWalk(cv));
    return box;
  }

  function wheelBox() {
    const list = strata().wheel || [];
    const box = el('div', { class: 'ss-wheel' }, [
      el('span', { class: 'ss-say', text: 'Drag to paint · shift-drag '
        + 'erases · click moves the traces' }),
      el('div', { style: 'flex:1' }),
      el('span', { class: 'section-label', text: 'Wheel times' }),
    ]);
    list.forEach((w, i) => box.appendChild(el('span', { class: 'ss-chip' }, [
      el('span', { text: fmtT(w.t0) + '–' + fmtT(w.t1)
                         + (w.note ? ' · ' + w.note : '') }),
      el('button', {
        class: 'mini', text: 'Paint', title: 'Paint this as Theta Walk',
        onclick: () => setWalk(merge(walk().concat([[w.t0, w.t1]]))),
      }),
      el('button', {
        class: 'mini', text: '×', title: 'Remove this wheel time',
        onclick: () => saveStrata({ wheel: list.filter((x, k) => k !== i) }),
      }),
    ])));
    const on = el('input', { class: 'ss-in', placeholder: 'on m:ss',
                             value: wheelDraft.on,
                             oninput: (e) => { wheelDraft.on = e.target.value; } });
    const off = el('input', { class: 'ss-in', placeholder: 'off m:ss',
                              value: wheelDraft.off,
                              oninput: (e) => { wheelDraft.off = e.target.value; } });
    const note = el('input', { class: 'ss-in wide', placeholder: 'note',
                               value: wheelDraft.note,
                               oninput: (e) => { wheelDraft.note = e.target.value; } });
    box.appendChild(on); box.appendChild(off); box.appendChild(note);
    box.appendChild(el('button', {
      class: 'mini', text: 'Add',
      onclick: () => {
        const a = parseT(wheelDraft.on), b = parseT(wheelDraft.off);
        if (a == null || b == null || b <= a) {
          toast('Type the wheel time as minutes:seconds, on before off.',
                'err', 6000);
          return;
        }
        wheelDraft = { on: '', off: '', note: '' };
        saveStrata({ wheel: list.concat([{ t0: a, t1: b,
                                           note: note.value || null }]) });
      },
    }));
    return box;
  }

  function merge(bouts) {
    const got = bouts.map((b) => [Math.min(b[0], b[1]), Math.max(b[0], b[1])])
      .filter((b) => b[1] - b[0] > 0.2).sort((a, b) => a[0] - b[0]);
    const out = [];
    for (const b of got) {
      const last = out[out.length - 1];
      if (last && b[0] <= last[1]) last[1] = Math.max(last[1], b[1]);
      else out.push(b.slice());
    }
    return out;
  }

  function subtract(bouts, cut) {
    const out = [];
    for (const b of bouts) {
      if (cut[1] <= b[0] || cut[0] >= b[1]) { out.push(b); continue; }
      if (cut[0] > b[0]) out.push([b[0], cut[0]]);
      if (cut[1] < b[1]) out.push([cut[1], b[1]]);
    }
    return out;
  }

  /* Painting is saved a moment after the last stroke, not per stroke. */
  function setWalk(bouts) {
    const sh = sheet();
    if (!sh) return;
    sh.strata = Object.assign({}, sh.strata || {});
    sh.strata.states = Object.assign({}, sh.strata.states || {},
                                     { theta_walk: merge(bouts) });
    H.render();
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(flushStates, 700);
  }

  async function flushStates() {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
    if (!H) return;
    const steps = {};
    /* Painting IS step 0's work, so a change to it re-stamps step 0 -- and
       that is what marks an already-accepted step 1, 2 or 3 as needing a
       look. */
    if ((strata().steps || {})['0']) {
      steps['0'] = Object.assign({}, strata().steps['0'],
                                 { at: new Date().toISOString() });
    }
    await saveStrata(Object.assign({ states: { theta_walk: walk() } },
                                   Object.keys(steps).length ? { steps } : {}),
                     true);
    await load(true);
  }

  async function saveStrata(patch, quiet) {
    try {
      const res = await apiPost(url('state'), { patch });
      if (H) H.adoptSheet(res.sheet);
    } catch (e) {
      toast('That did not save: ' + e.message, 'err', 8000);
    }
    if (H && !quiet) H.render();
  }

  /* The Theta Walk strip. */
  function drawWalk(cv) {
    if (!cv || !cv.isConnected || !guide || !guide.guide) return;
    const g = guide.guide;
    const dpr = window.devicePixelRatio || 1;
    const W = cv.clientWidth || 800, Hh = 128;
    cv.width = Math.round(W * dpr); cv.height = Math.round(Hh * dpr);
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, Hh);
    const end = g.end_s || (g.t.length ? g.t[g.t.length - 1] + 1 : 1);
    const X = (t) => (t / end) * W;
    const specH = 54, ratioTop = 58, ratioH = 46, agreeTop = 108, agreeH = 16;
    const draw = () => {
      ctx.clearRect(0, 0, W, Hh);
      if (img.complete && img.naturalWidth) {
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(img, 0, 0, W, specH);
      }
      // the ghost: the finder's bouts, hatched
      ctx.save();
      ctx.strokeStyle = BARRY.token('--text-3');
      ctx.lineWidth = 1;
      for (const b of g.ghost || []) {
        const x0 = X(b[0]), x1 = X(b[1]);
        ctx.beginPath();
        for (let x = x0; x < x1; x += 5) {
          ctx.moveTo(x, ratioTop + ratioH); ctx.lineTo(Math.min(x1, x + 5),
                                                      ratioTop);
        }
        ctx.globalAlpha = 0.45;
        ctx.stroke();
      }
      ctx.restore();
      // the painted bouts, solid, full height
      ctx.save();
      ctx.fillStyle = BARRY.token('--accent');
      ctx.globalAlpha = 0.28;
      for (const b of walk()) ctx.fillRect(X(b[0]), 0, Math.max(1, X(b[1]) - X(b[0])), Hh);
      ctx.globalAlpha = 1;
      ctx.fillStyle = BARRY.token('--accent');
      for (const b of walk()) ctx.fillRect(X(b[0]), Hh - 3, Math.max(1, X(b[1]) - X(b[0])), 3);
      ctx.restore();
      // wheel times, on top
      ctx.fillStyle = BARRY.token('--ok');
      for (const w of strata().wheel || []) {
        ctx.fillRect(X(w.t0), 0, Math.max(1, X(w.t1) - X(w.t0)), 3);
      }
      // theta/delta
      const r = g.ratio.filter((v) => v != null);
      if (r.length) {
        let lo = Math.min(...r), hi = Math.max(...r);
        if (hi <= lo) hi = lo + 1;
        const Y = (v) => ratioTop + ratioH - ((v - lo) / (hi - lo)) * ratioH;
        ctx.strokeStyle = BARRY.token('--c3');
        ctx.lineWidth = 1;
        ctx.beginPath();
        let pen = false;
        g.ratio.forEach((v, i) => {
          if (v == null) { pen = false; return; }
          const x = X(g.t[i] + 0.5), y = Y(v);
          if (pen) ctx.lineTo(x, y); else { ctx.moveTo(x, y); pen = true; }
        });
        ctx.stroke();
        ctx.setLineDash([4, 3]);
        ctx.strokeStyle = BARRY.token('--text-2');
        ctx.beginPath();
        ctx.moveTo(0, Y(g.threshold)); ctx.lineTo(W, Y(g.threshold));
        ctx.stroke();
        ctx.setLineDash([]);
      }
      // agreement, as a thin band: brighter = the probe agrees
      g.agreement.forEach((v, i) => {
        if (v == null) return;
        ctx.globalAlpha = Math.max(0.05, v);
        ctx.fillStyle = v >= g.agree_min ? BARRY.token('--ok')
                                         : BARRY.token('--text-3');
        ctx.fillRect(X(g.t[i]), agreeTop, Math.max(1, X(g.t[i] + 1) - X(g.t[i])),
                     agreeH);
      });
      ctx.globalAlpha = 1;
      // where the traces are
      const s = H && H.sess();
      if (s && isFinite(s.t0)) {
        ctx.strokeStyle = BARRY.token('--text');
        ctx.lineWidth = 1.5;
        ctx.strokeRect(X(s.t0), 0.5, Math.max(2, X(s.t0 + s.span) - X(s.t0)),
                       Hh - 1);
      }
      if (paint) {
        ctx.fillStyle = paint.erase ? BARRY.token('--err')
                                    : BARRY.token('--accent');
        ctx.globalAlpha = 0.35;
        const a = Math.min(paint.t0, paint.t1), b = Math.max(paint.t0, paint.t1);
        ctx.fillRect(X(a), 0, Math.max(1, X(b) - X(a)), Hh);
        ctx.globalAlpha = 1;
      }
    };
    const img = new Image();
    img.onload = draw;
    img.src = g.spec_png;
    draw();
    cv._draw = draw;
    const tAt = (e) => {
      const r = cv.getBoundingClientRect();
      return Math.max(0, Math.min(end, ((e.clientX - r.left) / r.width) * end));
    };
    cv.onmousedown = (e) => {
      e.preventDefault();
      paint = { t0: tAt(e), t1: tAt(e), erase: e.shiftKey || e.button === 2,
                x: e.clientX };
      const move = (ev) => { paint.t1 = tAt(ev); draw(); };
      const up = (ev) => {
        window.removeEventListener('mousemove', move);
        window.removeEventListener('mouseup', up);
        const p = paint;
        paint = null;
        if (Math.abs(ev.clientX - p.x) < 4) {
          // A click: move the traces there, half a window either side.
          const s = H.sess();
          const span = (s && s.span) || 10;
          BARRY.views.xplore.setWindow(0, Math.max(0, p.t0 - span / 2), span);
          setTimeout(draw, 300);
          return;
        }
        const cut = [Math.min(p.t0, p.t1), Math.max(p.t0, p.t1)];
        setWalk(p.erase ? subtract(walk(), cut) : walk().concat([cut]));
        requestAnimationFrame(() => {
          const c = document.querySelector('.ss-tw');
          if (c) drawWalk(c);
        });
      };
      window.addEventListener('mousemove', move);
      window.addEventListener('mouseup', up);
    };
    cv.oncontextmenu = (e) => e.preventDefault();
  }

  /* ---------- Steps 1-3: anchors, lines, Accept ---------- */
  const OVERRIDE_KEY = { sp: 'sp', fissure: 'fissure', sr_slm: 'sr_slm',
                         gcl1: 'gcl1', gcl2: 'gcl2' };

  function chName(row) {
    const ch = sug && sug.channels ? sug.channels[row] : null;
    return ch == null ? '—' : 'ch ' + ch;
  }

  /* The layers by the short names the strip has room for. "CA1", "DG" and
     "DG2" are the lab's placeholders for "in here, layer not decided" --
     stratum radiatum is ca1_rad. */
  const SHORT = {
    ca1_so: 'SO', ca1_sp: 'SP', ca1_rad: 'SR', ca1_slm: 'SLM', ca1_sr: 'CA1',
    dg_oml1: 'OML1', dg_mml1: 'MML1', dg_iml1: 'IML1', dg_gcl1: 'GCL1',
    hil: 'HIL', dg_gcl2: 'GCL2', dg_iml2: 'IML2', dg_mml2: 'MML2',
    dg_oml2: 'OML2',
  };

  function regionName(id) {
    if (!id) return 'below';
    const r = (H.regions() || []).find((x) => x.id === id);
    return r ? r.name : id;
  }

  function stepAnchors(id) {
    const st = STEPS[+id];
    const prop = sug && sug.steps ? sug.steps[id] : null;
    const box = el('div', { class: 'ss-anchors' });
    box.appendChild(el('div', { class: 'ss-zero-head' }, [
      el('strong', { text: st.title }),
      el('span', { class: 'ss-say', text: st.blurb }),
    ]));
    if (confirming && confirming.id === id) box.appendChild(confirmCard());
    box.appendChild(curveToggles());
    if (sug && sug.masks && sug.masks.theta_all_time && id !== '2') {
      box.appendChild(el('p', { class: 'ss-say warn', text: 'No Theta Walk '
        + 'is painted, so theta and gamma average the whole recording. '
        + 'Step 0 first gives cleaner curves.' }));
    }
    if (!prop) {
      box.appendChild(el('p', { class: 'ss-say', text: 'Nothing to propose '
        + 'yet.' }));
      return box;
    }
    for (const a of prop.anchors || []) box.appendChild(anchorRow(a));
    if (id === '1') box.appendChild(rippleRow());
    if (id === '3') box.appendChild(imlRow(prop));
    for (const n of prop.notes || []) {
      box.appendChild(el('p', { class: 'ss-say warn', text: n }));
    }
    if (id === '3') box.appendChild(icaRow(prop));

    const lines = (ghost && ghost.step === id) ? ghost.lines : [];
    const lbox = el('div', { class: 'ss-lines' });
    lines.forEach((ln) => {
      lbox.appendChild(el('div', { class: 'ss-line' }, [
        el('span', { class: 'ss-line-name', text: regionName(ln.above)
          + ' | ' + regionName(ln.below) }),
        el('span', { class: 'ss-line-at', text: ln.at == null ? 'not placed'
          : 'above ' + chName(ln.at) }),
        el('span', { class: 'ctl-seg', title: 'How sure you are of this '
          + 'line. Saved with the sheet when you accept, kept in the '
          + 'version when you sign off, and exported. It moves nothing.' },
        CONF.map((c) => el('button', {
          class: 'mini' + (ln.confidence === c ? ' on' : ''), text: c,
          title: c + ': ' + CONF_WHY[c] + '\nDrawn ' + (c === 'sure'
            ? 'solid' : c === 'likely' ? 'dashed' : 'dotted')
            + ' on the strip, the traces and the aid window.',
          onclick: () => { ln.confidence = c; H.render(); publish(); },
        }))),
      ]));
    });
    box.appendChild(lbox);
    box.appendChild(el('div', { class: 'ss-actions' }, [
      el('button', {
        class: 'mini', text: more ? '▾ Less' : '▸ More',
        onclick: () => { more = !more; H.render(); },
      }),
      el('button', {
        class: 'btn ghost sm', text: 'Back to the proposal',
        title: 'Put every line back where the evidence put it',
        onclick: () => { overrides = {}; load(); },
      }),
      el('div', { style: 'flex:1' }),
      el('span', { class: 'ss-say', text: 'Drag a dashed line on the strip '
        + 'beside the rail to move it.' }),
      el('button', {
        class: 'btn sm', text: 'Accept ' + st.title.split(' · ')[0],
        disabled: lines.some((l) => l.at != null) ? null : 'disabled',
        onclick: () => acceptLines(id),
      }),
    ]));
    if (more) {
      for (const a of prop.anchors || []) {
        box.appendChild(el('p', { class: 'ss-more' }, [
          el('strong', { text: a.name + '. ' }), a.why || '']));
      }
      box.appendChild(el('p', { class: 'ss-more', text: 'Click a vote to '
        + 'make it the lead: the lines that hang off that anchor move with '
        + 'it. Confidence starts at likely when the votes agree within two '
        + 'channels, guess when they do not.' }));
    }
    box.appendChild(paramsBox());
    return box;
  }

  /* The numbers the steps are worked out with, saved with the sheet (and
     frozen into its version at sign-off). Empty means the default. */
  const PARAMS = [
    ['spacing_um', 'Contact spacing (µm)', 'H3: 20 µm, as '
      + 'HippoCompass measures with'],
    ['species', 'Species', 'mouse or rat; sets the GCL default and '
      + 'whether the atlas checks apply'],
    ['gcl_half_um', 'GCL half-thickness (µm)', '30 mouse, 50 rat'],
    ['lower_ml_scale', 'Lower blade, × the upper', 'the lower '
      + 'molecular layer’s thickness against the upper’s'],
    ['sp_half_um', 'sp half-thickness (µm)', ''],
    ['still_buffer_s', 'Still: buffer around a walk (s)', ''],
    ['ref_channel', 'Reference channel', 'empty: CA1 pyramidal, wherever '
      + 'Step 1 puts it'],
    ['ripple_height_sd', 'Ripple peak (SD)', 'Toothy: 5'],
    ['ripple_edge_sd', 'Ripple edges (SD)', 'Toothy: 3'],
  ];
  let paramsOpen = false;
  let paramsDraft = {};

  function paramsBox() {
    const p = (sug && sug.params) || {};
    const box = el('div', { class: 'ss-params' });
    box.appendChild(el('button', {
      class: 'mini', text: (paramsOpen ? '▾' : '▸') + ' Parameters',
      onclick: () => { paramsOpen = !paramsOpen; paramsDraft = {}; H.render(); },
    }));
    if (!paramsOpen) return box;
    const grid = el('div', { class: 'ss-params-grid' });
    for (const [key, name, hint] of PARAMS) {
      const cur = key in paramsDraft ? paramsDraft[key] : p[key];
      const input = key === 'species'
        ? el('select', {
          class: 'ss-in wide',
          onchange: (e) => { paramsDraft[key] = e.target.value; },
        }, ['mouse', 'rat'].map((sp) => el('option', {
          value: sp, text: sp, selected: (cur || 'mouse') === sp ? 'selected'
            : null })))
        : el('input', {
          class: 'ss-in', value: cur == null ? '' : String(cur),
          placeholder: 'default',
          oninput: (e) => { paramsDraft[key] = e.target.value; },
        });
      grid.appendChild(el('label', { class: 'ss-param', title: hint }, [
        el('span', { text: name }), input]));
    }
    box.appendChild(grid);
    box.appendChild(el('div', { class: 'ss-actions' }, [
      el('button', {
        class: 'btn sm', text: 'Save and work it out again',
        onclick: async () => {
          const patch = {};
          for (const [key] of PARAMS) {
            if (!(key in paramsDraft)) continue;
            const v = String(paramsDraft[key]).trim();
            if (!v) { patch[key] = null; continue; }
            if (key === 'species') { patch[key] = v; continue; }
            const num = Number(v);
            if (!isFinite(num)) {
              toast(key.replace(/_/g, ' ') + ' has to be a number.', 'err',
                    6000);
              return;
            }
            patch[key] = num;
          }
          paramsDraft = {};
          await saveStrata({ params: patch }, true);
          await load();
        },
      }),
    ]));
    return box;
  }

  function anchorRow(a) {
    const key = OVERRIDE_KEY[a.key];
    const pick = (row) => {
      if (!key) return;
      overrides[key] = row;
      load();
    };
    return el('div', { class: 'ss-anchor' }, [
      el('span', { class: 'ss-anchor-name', text: a.name }),
      el('span', {
        class: 'ss-lead', title: 'The lead: what placed this.',
      }, [el('b', { text: chName(a.lead.row) }),
          el('span', { text: ' ' + a.lead.name })]),
      el('span', { class: 'ss-votes' }, (a.votes || []).map((v) =>
        el('button', {
          class: 'ss-vote' + (Math.abs(v.off || 0) <= 1 ? ' near'
            : Math.abs(v.off || 0) <= 3 ? '' : ' far'),
          title: v.name + ' — click to make it the lead',
          onclick: () => pick(v.row),
        }, [el('b', { text: chName(v.row) }),
            el('span', { text: ' ' + v.name + ' ' }),
            el('i', { text: v.off == null ? '' : (v.off > 0 ? '+' : '')
              + v.off })]))),
      el('span', { class: 'ss-conf ' + a.confidence, text: a.confidence }),
    ]);
  }

  /* Whether the molecular layer is cut in three (OML, MML, IML) or two
     (OML, then MML down to the granule layer -- the lab's own scheme). Saved
     with the sheet's parameters. */
  function imlRow(prop) {
    const on = prop.use_iml !== false;
    const set = async (v) => {
      if (v === on) return;
      await saveStrata({ params: { use_iml: v } }, true);
      await load();
    };
    const thal = (prop.below_lower || 'thal') === 'thal';
    const setBelow = async (v) => {
      if ((v === 'thal') === thal) return;
      await saveStrata({ params: { below_lower: v } }, true);
      await load();
    };
    return el('div', { class: 'ss-lines' }, [imlSwitch(), el('div', {
      class: 'ss-line' }, [
      el('span', { class: 'ss-line-name', text: 'Below the lower blade' }),
      el('span', { class: 'ctl-seg', title: 'The lower blade mirrors the '
        + 'upper one: from the hilus down the same distance as the fissure '
        + 'is above it (times "Lower blade" in Parameters). What is under '
        + 'that is thalamus, or can be left as it is.' }, [
        el('button', { class: 'mini' + (thal ? ' on' : ''), text: 'THAL',
                       onclick: () => setBelow('thal') }),
        el('button', { class: 'mini' + (thal ? '' : ' on'), text: 'leave as is',
                       onclick: () => setBelow('none') }),
      ]),
    ])]);

    function imlSwitch() {
    return el('div', { class: 'ss-line' }, [
      el('span', { class: 'ss-line-name', text: 'Inner molecular layer' }),
      el('span', { class: 'ctl-seg', title: 'Method A cuts the molecular '
        + 'layer in thirds. Without IML the inner third is part of the MML, '
        + 'as in the lab\u2019s own scheme; the OML line does not move.' }, [
        el('button', { class: 'mini' + (on ? ' on' : ''), text: 'its own (IML)',
                       onclick: () => set(true) }),
        el('button', { class: 'mini' + (on ? '' : ' on'), text: 'part of MML',
                       onclick: () => set(false) }),
      ]),
    ]);
    }
  }

  /* The ripples Step 1 leans on, and a way to keep them. They go into the
     Event Bank as a detector's output, type ripple, through the one bank
     dialog. Checkup has no ripple vocabulary yet (dentate spikes and IEDs
     only), so a banked set is a record of what the detector found until it
     does. */
  function rippleRow() {
    const r = sug && sug.ripples;
    const row = el('div', { class: 'ss-ica' });
    if (!r) return row;
    row.appendChild(el('span', { class: 'ss-say', text: r.n
      ? r.n + ' ripples in ' + fmtT(r.still_s || 0) + ' of still time on '
        + 'ch ' + r.channel + ' (' + r.rate_per_min + ' a minute), by '
        + 'Toothy\u2019s detector.'
      : (r.why || 'No ripples found in still time on ch ' + r.channel
         + '.') }));
    if (r.n) {
      row.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Bank the ripples\u2026',
        title: 'Put them in the Event Bank as a detector\u2019s output, '
             + 'with every parameter that found them.',
        onclick: bankRipples,
      }));
    }
    return row;
  }

  async function bankRipples() {
    let rip, row;
    try {
      rip = (await apiPost(url('ripples'), body({ channel: sug.ripples.channel,
                                                  overrides }))).ripples;
      row = (await api('/api/registry/' + encodeURIComponent(H.gid))).session
        || {};
    } catch (e) {
      toast('Could not read the ripples: ' + e.message, 'err', 8000);
      return;
    }
    const evs = rip.events || [];
    await BARRY.ui.bankDialog({
      kind: 'entry',
      title: 'Bank ' + evs.length + ' ripples',
      name: BARRY.bankName.suggest(row, 'Ripples ch ' + rip.channel),
      what: 'They go in as a detector\u2019s output, not as a curated set: '
          + 'nothing is decided. Checkup cannot vet ripples yet (it knows '
          + 'dentate spikes and IEDs), so for now this is the record of '
          + 'what the detector found.',
      where: 'Filed under ' + [row.project || 'Unfiled',
                               row.mouse != null ? 'm' + row.mouse : null,
                               row.session != null ? 's' + row.session : null]
        .filter(Boolean).join(' / ') + ' in the Event Bank.',
      facts: [
        'Still time only: the Theta Walk painted in Step 0, less '
          + (((sug.params || {}).still_buffer_s) || 2) + ' s either side.',
        'Every detection parameter goes with them: Toothy\u2019s '
          + 'get_swr_peaks, 120-180 Hz, 5 SD peaks, 3 SD edges.',
      ],
      okText: 'Bank them',
      onBank: async ({ name, note, who }) => {
        await apiPost('/api/bank/add', {
          gid: H.gid,
          project: row.project, mouse: row.mouse, session: row.session,
          session_key: row.key, session_loose_key: row.loose_key,
          session_label: row.label, duration_s: row.duration_s,
          type: 'ripple', type_name: 'Ripple',
          name, note: note || undefined,
          pipeline: 'StrataScope ripples (Toothy get_swr_peaks, still time)',
          added_by: who,
          session_path: H.path(),
          parameters: Object.assign({ channel: rip.channel,
                                      still_s: rip.still_s,
                                      theta_walk_bouts: walk().length },
                                    rip.params || {}),
          events: evs.map((e) => ({ start: e.t, end: e.end,
                                    channel: rip.channel,
                                    amplitude: e.amp })),
        });
        toast('Banked ' + evs.length + ' ripples.', 'ok');
        return true;
      },
    });
  }

  function icaRow(prop) {
    const row = el('div', { class: 'ss-ica' });
    if (jobKind === 'ica') {
      row.appendChild(el('div', { class: 'ss-job' }, [
        el('i', { style: 'width:' + jobPct() + '%' }),
        el('span', { text: jobText() }),
      ]));
      return row;
    }
    const chk = prop.ica_checks || [];
    const helpBtn = () => el('button', {
      class: 'ss-help' + (icaHelp ? ' on' : ''), text: '?',
      title: 'How Method B works',
      onclick: () => { icaHelp = !icaHelp; H.render(); },
    });
    if (!sug.ica_ready) {
      row.appendChild(el('span', { class: 'ss-say', text: 'Method B has not '
        + 'run on these Theta Walk seconds yet.' }));
      row.appendChild(helpBtn());
      row.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Run ICA (Method B)',
        title: 'Unmix the 25-200 Hz field into its generators. Uses the '
             + 'Theta Walk seconds (at least 30 s); refits on each half to '
             + 'see which components are stable. Takes a minute or two.',
        onclick: runIca,
      }));
      const box0 = el('div', { class: 'ss-ica-box' }, [row]);
      if (icaHelp) box0.appendChild(icaExplain());
      return box0;
    }
    row.appendChild(el('span', { class: 'section-label', text: 'Method B '
      + 'says' }));
    row.appendChild(helpBtn());
    for (const c of chk) {
      const on = icaPick && icaPick.region === c.region
        && icaPick.kind === c.kind;
      row.appendChild(el('button', {
        class: 'ss-chip ss-chip-btn' + (c.row == null ? ' dim'
          : c.agree ? ' ok' : ' warn') + (on ? ' picked' : ''),
        title: 'Click to see it against Method A\u2019s lines',
        onclick: () => {
          icaPick = on ? null : c;
          H.render();
          drawStrip();
          H.redraw();
        },
      }, [el('span', { text: (c.kind === 'slow' ? 'slow \u03b3 \u2192 '
        : 'fast \u03b3 \u2192 ') + regionName(c.region) + ': '
        + (c.row == null ? 'nothing reliable'
          : chName(c.row) + (c.agree ? ', agrees'
            : ', ' + Math.abs(c.off) + ' ch off')) })]));
    }
    const box = el('div', { class: 'ss-ica-box' }, [row]);
    if (icaPick) box.appendChild(icaCompare(icaPick));
    if (icaHelp) box.appendChild(icaExplain());
    return box;
  }

  let icaHelp = false;
  let icaPick = null;

  /* What one check means, in a sentence, and where it is on the strip and
     the traces (drawn while it is picked). */
  function icaCompare(c) {
    const lines = (ghost && ghost.lines) || [];
    const top = lines.find((l) => l.below === c.region);
    const bot = lines.find((l) => l.above === c.region);
    const span = (top && top.at != null)
      ? chName(top.at) + (bot && bot.at != null && bot.at - 1 > top.at
        ? '\u2013' + (sug.channels[bot.at - 1] != null
          ? sug.channels[bot.at - 1] : '') : '')
      : 'nowhere yet';
    const comp = (ica && ica.components || []).find((x) => x.index === c.component);
    const kind = c.kind === 'slow' ? 'slow-gamma (LEC-like, 25-60 Hz)'
                                   : 'fast-gamma (MEC-like, 60-180 Hz)';
    let say;
    if (c.row == null) {
      say = 'No ' + kind + ' component that came back in both halves of '
        + 'the walking has a sink inside ' + regionName(c.region)
        + ' (' + span + ') at least 30% as strong as its own strongest '
        + 'sink. So ICA found no generator it can vouch for in this layer: '
        + 'not evidence against Method A\u2019s line, just no evidence '
        + 'for it. Fast gamma is often too weak in mice for this.';
    } else {
      const dir = c.off > 0 ? 'deeper' : 'shallower';
      say = 'Component ' + c.component + (comp ? ' (' + comp.peak_hz
        + ' Hz, ' + (100 * comp.variance).toFixed(0) + '% of the gamma '
        + 'field, came back in both halves at ' + comp.stability + ')' : '')
        + ' sinks at ' + chName(c.row) + '. Method A puts '
        + regionName(c.region) + ' at ' + span + (c.agree
          ? ', so they agree.'
          : ', so ICA puts it ' + Math.abs(c.off) + ' channel'
            + (Math.abs(c.off) === 1 ? '' : 's') + ' ' + dir + '.')
        + ' On the strip: the component\u2019s CSD (its sink is the dip), '
        + 'the sink as a solid line, and the layer as a bracket.';
    }
    return el('p', { class: 'ss-more', text: say });
  }

  function icaExplain() {
    return el('div', { class: 'ss-more' }, [
      el('p', { text: 'Method B, in four steps.' }),
      el('p', { text: '1. The gamma-band field (25-200 Hz) recorded during '
        + 'Theta Walk is a mix of a few generators: groups of synapses '
        + 'firing together, each felt on every contact with a different '
        + 'strength. ICA (independent component analysis) unmixes them '
        + 'into about ten sources that are statistically independent of '
        + 'each other.' }),
      el('p', { text: '2. Each source has a loading -- how strongly it '
        + 'shows on each channel -- and a time course. The CSD of the '
        + 'loading has a sink where the generator\u2019s synapses are; '
        + 'that is the "where". The time course\u2019s spectrum says '
        + 'which frequency it carries; that is the "what".' }),
      el('p', { text: '3. In the dentate, slow gamma (25-60 Hz) comes from '
        + 'the lateral entorhinal cortex and ends in the outer molecular '
        + 'layer; fast gamma (60-180 Hz) from the medial entorhinal cortex, '
        + 'in the middle molecular layer. So a slow source should sink in '
        + 'OML, a fast one in MML -- an answer that never used Method A\u2019s '
        + 'thirds.' }),
      el('p', { text: '4. Every source is fitted again on the first and the '
        + 'second half of the walking. Only sources that come back in both '
        + '(their loadings correlate at 0.7 or more) are trusted. "Agrees" '
        + 'means a trusted source sinks inside the layer Method A drew; '
        + '"N ch off" means it sinks N channels outside it; "nothing '
        + 'reliable" means no trusted source sinks there.' }),
    ]);
  }

  async function runIca() {
    try {
      const res = await apiPost(url('ica'), body({ overrides }));
      if (res.cached) { ica = res.ica; await load(true); return; }
      jobId = res.job.id; jobKind = 'ica'; jobSnap = res.job;
      H.render();
      poll();
    } catch (e) {
      toast('ICA could not start: ' + e.message, 'err', 9000);
    }
  }

  async function peekIca() {
    try {
      const res = await apiPost(url('ica'), body({ peek: true, overrides }));
      if (res.ica) ica = res.ica;
    } catch (e) { /* the button says so */ }
  }

  /* Rows -> region from a stack of lines: a row takes the region below the
     last line at or above it. The same rule as stratasteps.labels_from_lines,
     so the sheet gets what the strip shows. */
  function labelsFromLines(lines, start, end) {
    const ls = lines.filter((l) => l.at != null).slice()
      .sort((a, b) => a.at - b.at);
    const out = {};
    for (let r = Math.max(0, start); r < end; r++) {
      let region;
      for (const l of ls) {
        if (l.at <= r) region = l.below;
        else { if (region === undefined) region = l.above; break; }
      }
      if (region) out[r] = region;
    }
    return out;
  }

  function stepSpan(id, lines) {
    const n = sug.channels.length;
    const at = (b) => { const l = lines.find((x) => x.below === b
                                             || (b === null && x.below == null));
                        return l ? l.at : null; };
    const atAbove = (a) => { const l = lines.find((x) => x.above === a);
                             return l ? l.at : null; };
    if (id === '1') return [0, at('dg_oml1') != null ? at('dg_oml1') : n];
    if (id === '2') return [atAbove('dg_gcl1') != null ? atAbove('dg_gcl1') : 0,
                            at('dg_gcl2') != null ? at('dg_gcl2') : n];
    const top = at('dg_oml1');
    const bot = lines.find((x) => x.below == null);
    return [top != null ? top : 0, bot ? bot.at : n];
  }

  async function acceptLines(id) {
    const lines = (ghost && ghost.lines) || [];
    const [a, b] = stepSpan(id, lines);
    const rows = labelsFromLines(lines, a, b);
    const labels = {};
    for (const r in rows) labels[sug.channels[r]] = rows[r];
    const confidence = {};
    for (const l of lines) if (l.id) confidence[l.id] = l.confidence;
    const anchors = {};
    const prop = sug.steps[id];
    const chOf = (row) => (row == null ? null : sug.channels[row]);
    if (id === '1') {
      const sp = (prop.anchors || []).find((x) => x.key === 'sp');
      const f = lines.find((l) => l.below === 'dg_oml1');
      if (sp) anchors.sp = chOf(sp.lead.row);
      if (f && f.at != null) anchors.fissure_at = chOf(f.at);
    } else if (id === '2') {
      for (const k of ['gcl1', 'gcl2']) {
        const x = (prop.anchors || []).find((y) => y.key === k);
        if (x && x.lead.row != null) anchors[k] = chOf(x.lead.row);
      }
    }
    /* Not written yet: first the drawer says, channel by channel, what
       this would change, and waits for Continue (2026-10-12). */
    confirming = { id, labels, confidence, anchors,
                   changes: changeRuns(labels) };
    H.render();
    const d = document.querySelector('.ss-drawer');
    if (d) d.scrollTop = 0;
  }

  let confirming = null;

  /* What Accept would do to the sheet, as runs of neighbouring channels
     going from the same label to the same label: "ch 6-9: CA1 -> CA1 SR". */
  function changeRuns(labels) {
    const cur = ((sheet() || {}).labels) || {};
    const runs = [];
    let same = 0;
    for (const ch of sug.channels) {
      if (!(ch in labels) && !(String(ch) in labels)) continue;
      const now = labels[ch] || labels[String(ch)] || null;
      const was = cur[String(ch)] || null;
      if (now === was) { same += 1; continue; }
      const last = runs[runs.length - 1];
      if (last && last.was === was && last.now === now
          && sug.channels.indexOf(last.to) === sug.channels.indexOf(ch) - 1) {
        last.to = ch;
        last.n += 1;
      } else {
        runs.push({ from: ch, to: ch, n: 1, was, now });
      }
    }
    return { runs, same };
  }

  function confirmCard() {
    const c = confirming;
    const ch = (r) => (r.from === r.to ? 'Ch ' + r.from
                                        : 'Ch ' + r.from + '\u2013' + r.to);
    const name = (id) => (id ? regionName(id) : 'unlabelled');
    const list = el('ul', { class: 'ss-changes' }, c.changes.runs.map((r) =>
      el('li', {}, [
        el('b', { text: ch(r) }),
        el('span', { class: 'was', text: name(r.was) }),
        el('span', { class: 'arrow', text: '\u2192' }),
        el('span', { class: 'now', text: name(r.now) }),
      ])));
    const total = c.changes.runs.reduce((a, r) => a + r.n, 0);
    return el('div', { class: 'ss-confirm' }, [
      el('strong', { text: total
        ? 'This will change ' + total + ' channel' + (total === 1 ? '' : 's')
          + ':'
        : 'No channel changes.' }),
      total ? list : el('p', { class: 'ss-say', text: 'Accepting records '
        + 'the step as done, with the confidence of each line.' }),
      c.changes.same ? el('p', { class: 'ss-say', text: c.changes.same
        + ' channel' + (c.changes.same === 1 ? '' : 's')
        + ' in the step already say what it proposes.' }) : null,
      el('div', { class: 'ss-actions' }, [
        el('button', {
          class: 'btn ghost sm', text: 'Back',
          onclick: () => { confirming = null; H.render(); },
        }),
        el('div', { style: 'flex:1' }),
        el('button', {
          class: 'btn sm', text: 'Continue',
          onclick: async () => {
            const k = confirming;
            confirming = null;
            await accept(k.id, k.labels, k.confidence, k.anchors);
            openStep(String(+k.id + 1));
          },
        }),
      ]),
    ].filter(Boolean));
  }

  /* What Accept would write in the open step: channel -> region. Drawn
     hatched on the traces and the CSD until it is accepted. */
  function proposedLabels() {
    if (!open || open === '0' || open === '4' || !sug || !ghost
        || ghost.step !== open) return null;
    const [a, b] = stepSpan(open, ghost.lines);
    const rows = labelsFromLines(ghost.lines, a, b);
    const out = new Map();
    for (const r in rows) out.set(sug.channels[r], rows[r]);
    return out;
  }

  async function accept(id, labels, confidence, anchors) {
    try {
      const res = await apiPost(url('accept'), {
        step: id, labels, confidence: confidence || null,
        anchors: anchors && Object.keys(anchors).length ? anchors : null,
        basis: { overrides, at: new Date().toISOString() },
      });
      H.adoptSheet(res.sheet);
      toast(STEPS[+id].title + ' accepted' + (Object.keys(labels || {}).length
        ? ': ' + Object.keys(labels).length + ' channels labelled.' : '.'),
            'ok');
    } catch (e) {
      toast('Not accepted: ' + e.message, 'err', 9000);
    }
  }

  /* ---------- Step 4: checks and sign off ---------- */
  async function loadChecks() {
    try {
      checks = (await apiPost(url('checks'), body())).checks;
    } catch (e) {
      checks = null;
      toast('The checks could not run: ' + e.message, 'err', 8000);
    }
  }

  function stepFour() {
    const box = el('div', { class: 'ss-four' });
    box.appendChild(el('div', { class: 'ss-zero-head' }, [
      el('strong', { text: STEPS[4].title }),
      el('span', { class: 'ss-say', text: STEPS[4].blurb }),
    ]));
    const list = el('ul', { class: 'ss-checks' });
    for (const c of checks || []) {
      list.appendChild(el('li', { class: c.ok ? 'ok' : 'warn' }, [
        el('span', { class: 'ss-tick', text: c.ok ? '✓' : '!' }),
        el('span', { text: c.text }),
      ]));
    }
    if (!checks) list.appendChild(el('li', { text: 'Working…' }));
    box.appendChild(list);
    const signed = strata().signed || {};
    box.appendChild(el('div', { class: 'ss-actions' }, [
      el('span', { class: 'ss-say', text: signed.at
        ? 'Last signed off by ' + (signed.by || 'somebody') + ', '
          + String(signed.at).slice(0, 16).replace('T', ' ') + ' (v'
          + signed.v + ').'
        : 'Not signed off yet. Warnings never block; they are kept with the '
          + 'version.' }),
      el('div', { style: 'flex:1' }),
      el('button', {
        class: 'btn ghost sm', text: 'Export JSON',
        onclick: () => window.open(url('export.json'), '_blank'),
      }),
      el('button', {
        class: 'btn sm', text: 'Sign off',
        onclick: signOff,
      }),
    ]));
    return box;
  }

  async function signOff() {
    try {
      const res = await apiPost(url('signoff'), body());
      H.adoptSheet(res.sheet);
      checks = res.checks;
      const warn = (res.checks || []).filter((c) => !c.ok).length;
      toast('Signed off' + (warn ? ', with ' + warn + ' warning'
        + (warn === 1 ? '' : 's') + ' kept beside it.' : '.'), 'ok', 7000);
    } catch (e) {
      toast('Not signed off: ' + e.message, 'err', 9000);
    }
    H.render();
  }

  /* The channels Accept would write in the open step, or null when every
     channel is in play (no step, or Step 4). Step 0 writes no labels, so
     every channel is out of it. */
  function affected() {
    if (!H || !open || open === '4') return null;
    if (open === '0') return new Set();
    if (!sug || !sug.channels || !ghost || ghost.step !== open) return null;
    const [a, b] = stepSpan(open, ghost.lines);
    return new Set(sug.channels.slice(Math.max(0, a), Math.max(0, b)));
  }

  function focusRegions() {
    const f = open ? FOCUS[open] : null;
    return f && f.regions ? new Set(f.regions) : null;
  }

  /* Profile rows (every channel, sheet order) against lanes (the channels
     the traces draw). A line above profile row r sits above the first
     drawn channel at or after r. */
  function laneOfRow(row, chans) {
    if (row == null || !sug || !sug.channels) return null;
    const pos = new Map(chans.map((c, i) => [c.number, i]));
    for (let r = Math.max(0, row); r < sug.channels.length; r++) {
      const i = pos.get(sug.channels[r]);
      if (i != null) return i;
    }
    return chans.length;
  }

  function rowOfLane(i, chans) {
    if (!sug || !sug.channels) return null;
    if (i >= chans.length) return sug.channels.length;
    const r = sug.channels.indexOf(chans[Math.max(0, i)].number);
    return r < 0 ? null : r;
  }

  /* ==================================================================
     The depth strip, beside the rail
     ================================================================== */
  function railStrip(rail) {
    if (!H) return;
    let cv = rail.querySelector('.ss-strip');
    if (!cv) {
      cv = el('canvas', { class: 'ss-strip' });
      rail.appendChild(cv);
      cv.addEventListener('mousedown', stripDown);
      cv.addEventListener('mousemove', stripHover);
      cv.addEventListener('mouseleave', () => { cv.style.cursor = ''; });
    }
    stripCanvas = cv;
  }

  /* Which curves the strip draws: the open step's, at the top of its
     drawer. They used to sit in the rail above the strip, where there is
     not always room -- on a short pane they covered the channel count. The
     step's own curves first, full or faint as the strip draws them; the
     others after a divider, off until clicked. */
  function curveToggles() {
    const f = open ? FOCUS[open] : null;
    const mine = f ? f.lead.concat(f.votes) : ['mua', 'theta'];
    const chip = (c) => el('button', {
      class: 'ss-curve' + (shown.has(c.id) ? ' on' : '')
           + (f && f.votes.includes(c.id) ? ' vote' : ''),
      style: '--cv:var(' + c.tok + ')',
      title: c.why + '\nClick to show or hide it on the strip.',
      onclick: () => {
        if (shown.has(c.id)) shown.delete(c.id); else shown.add(c.id);
        H.render();
      },
    }, [el('i'), el('span', { text: c.name })]);
    const own = CURVES.filter((c) => mine.includes(c.id));
    const rest = CURVES.filter((c) => !mine.includes(c.id));
    return el('div', { class: 'ss-legend-row' }, [
      el('span', { class: 'section-label', text: 'On the strip' }),
      ...own.map(chip),
      rest.length ? el('span', { class: 'ss-legend-gap', text: '\u00b7' }) : null,
      ...rest.map(chip),
    ].filter(Boolean));
  }

  function stripWidth() { return H ? STRIP_W : 0; }

  /* Called by strata.js's alignRail with the lanes' geometry. */
  function layout(top, height, n) {
    strip = { top, height, n, lane: height / Math.max(1, n) };
    if (!stripCanvas) return;
    stripCanvas.style.top = top + 'px';
    stripCanvas.style.height = height + 'px';
    stripCanvas.style.width = STRIP_W + 'px';
    drawStrip();
  }

  function norm(vals) {
    const v = vals.filter((x) => x != null && isFinite(x));
    if (!v.length) return vals.map(() => null);
    let lo = Math.min(...v), hi = Math.max(...v);
    if (hi <= lo) hi = lo + 1;
    return vals.map((x) => (x == null || !isFinite(x)) ? null
                                                       : (x - lo) / (hi - lo));
  }

  function profileRows() {
    /* The strip is drawn on the rail's channels; the profile carries its
       own channel order, which can be shorter (a channel not read). */
    const chans = H.channels();
    const p = sug && sug.profile;
    if (!p) return null;
    const idx = new Map(p.channels.map((c, i) => [c, i]));
    return chans.map((c) => (idx.has(c.number) ? idx.get(c.number) : null));
  }

  function drawStrip() {
    const cv = stripCanvas;
    if (!cv || !cv.isConnected || !H) return;
    const dpr = window.devicePixelRatio || 1;
    const W = STRIP_W, Hh = Math.max(1, strip.height);
    cv.width = Math.round(W * dpr); cv.height = Math.round(Hh * dpr);
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, Hh);
    const chans = H.channels();
    const n = chans.length || 1;
    const lane = Hh / n;
    const pad = 6;
    if (!sug || !sug.profile) {
      ctx.fillStyle = BARRY.token('--text-3');
      ctx.font = '10.5px system-ui, sans-serif';
      ctx.textAlign = 'center';
      const say = (status && status.scanned) ? 'working\u2026'
                                             : 'not read yet';
      ctx.fillText(say, W / 2, Math.min(Hh / 2, 40));
      return;
    }
    const map = profileRows();
    const curves = sug.profile.curves;
    const f = open ? FOCUS[open] : null;
    const lead = new Set(f ? f.lead : []);
    // faint lane grid every 4 channels
    ctx.fillStyle = BARRY.token('--line-soft');
    for (let i = 0; i < n; i += 4) ctx.fillRect(0, Math.round(i * lane), W, 1);
    for (const c of CURVES) {
      if (!shown.has(c.id) || !curves[c.id]) continue;
      const v = norm(map.map((k) => (k == null ? null : curves[c.id][k])));
      const strong = !f || lead.has(c.id);
      ctx.globalAlpha = strong ? 1 : 0.45;
      ctx.strokeStyle = BARRY.token(c.tok);
      ctx.lineWidth = strong ? 1.8 : 1;
      curve(ctx, v.map((x, i) => (x == null ? null
        : [pad + x * (W - 2 * pad), (i + 0.5) * lane])));
    }
    ctx.globalAlpha = 1;
    // A channel with no value (marked bad, or not read): a small cross at
    // the edge, so the dotted stretch above says why it is dotted.
    if (map) {
      const bad = new Set((sug.bad || []).map(Number));
      ctx.fillStyle = BARRY.token('--text-3');
      ctx.font = '9px system-ui, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      chans.forEach((c, i) => {
        if (bad.has(c.number) || map[i] == null) {
          ctx.fillText('\u00d7', 1, (i + 0.5) * lane);
        }
      });
    }
    // the reference channel: R
    if (sug.ref_channel != null) {
      const i = chans.findIndex((c) => c.number === sug.ref_channel);
      if (i >= 0) {
        ctx.fillStyle = BARRY.token('--c4');
        ctx.font = 'bold 9px system-ui, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText('R', 1, (i + 0.5) * lane);
      }
    }
    /* Out of the step: channels Accept would not write are veiled, so the
       part of the probe the step is about is the only part in colour. */
    const aff = affected();
    if (aff) {
      ctx.fillStyle = BARRY.token('--bg');
      ctx.globalAlpha = 0.72;
      chans.forEach((c, i) => {
        if (!aff.has(c.number)) {
          ctx.fillRect(0, Math.floor(i * lane), W, Math.ceil(lane) + 1);
        }
      });
      ctx.globalAlpha = 1;
    }
    // accepted boundaries: the step's own layers in colour, the rest grey
    const sh = sheet();
    const lab = (c) => (sh && sh.labels ? sh.labels[String(c.number)] : null);
    const regs = H.regions() || [];
    const fr = focusRegions();
    for (let i = 1; i < n; i++) {
      const a = lab(chans[i - 1]), b = lab(chans[i]);
      if (a === b) continue;
      const y = Math.round(i * lane) + 0.5;
      const mineA = !fr || fr.has(a), mineB = !fr || fr.has(b);
      if (!(mineA || mineB)) {
        ctx.globalAlpha = 0.5;
        ctx.strokeStyle = BARRY.token('--text-3');
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
        ctx.globalAlpha = 1;
        continue;
      }
      const reg = regs.find((r) => r.id === (mineB ? b : a));
      ctx.globalAlpha = 0.7;
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = reg ? reg.color : BARRY.token('--accent');
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    }
    // the open step's anchors: lead as a filled mark, votes as rings
    const prop = open && sug.steps ? sug.steps[open] : null;
    for (const an of (prop && prop.anchors) || []) {
      const at = (row) => {
        const i = laneOfRow(row, chans);
        return i == null || i >= n ? null : (i + 0.5) * lane;
      };
      const y = at(an.lead.row);
      if (y != null) {
        ctx.fillStyle = BARRY.token('--accent');
        ctx.beginPath();
        ctx.moveTo(W - 1, y); ctx.lineTo(W - 8, y - 4); ctx.lineTo(W - 8, y + 4);
        ctx.closePath(); ctx.fill();
      }
      for (const v of an.votes || []) {
        const yy = at(v.row);
        if (yy == null) continue;
        ctx.strokeStyle = BARRY.token('--text-2');
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(W - 13, yy, 2.6, 0, Math.PI * 2); ctx.stroke();
      }
    }
    // a picked ICA check: the component's CSD, its sink, and the layer
    if (icaPick && open === '3' && ica && ica.components) {
      const comp = ica.components.find((x) => x.index === icaPick.component);
      const col = BARRY.token(icaPick.kind === 'slow' ? '--c2' : '--warn');
      if (comp && comp.csd) {
        const idx = new Map((ica.channels || []).map((ch, k) => [ch, k]));
        const vals = chans.map((c) => {
          const k = idx.get(c.number);
          return k == null ? null : comp.csd[k];
        });
        const fin = vals.filter((x) => x != null);
        const lim = fin.length ? Math.max(...fin.map(Math.abs)) || 1 : 1;
        ctx.strokeStyle = col;
        ctx.lineWidth = 1.6;
        curve(ctx, vals.map((x, i) => (x == null ? null
          : [W / 2 + (x / lim) * (W / 2 - pad), (i + 0.5) * lane])));
      }
      const top = ghost && ghost.lines.find((l) => l.below === icaPick.region);
      const bot = ghost && ghost.lines.find((l) => l.above === icaPick.region);
      if (top && top.at != null) {
        const y0 = laneOfRow(top.at, chans) * lane;
        const y1 = (bot && bot.at != null ? laneOfRow(bot.at, chans) : n) * lane;
        const reg = (H.regions() || []).find((r) => r.id === icaPick.region);
        ctx.fillStyle = reg ? reg.color : col;
        ctx.fillRect(1, y0 + 1, 4, Math.max(2, y1 - y0 - 2));
      }
      if (icaPick.row != null) {
        const i = laneOfRow(icaPick.row, chans);
        if (i != null && i < n) {
          const y = (i + 0.5) * lane;
          ctx.strokeStyle = col;
          ctx.lineWidth = 2;
          ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
        }
      }
    }
    // the proposal's lines, dashed by how sure they are
    if (ghost && ghost.step === open) {
      ctx.font = '9.5px system-ui, sans-serif';
      ctx.textBaseline = 'bottom';
      ctx.textAlign = 'right';
      for (const ln of ghost.lines) {
        const i = laneOfRow(ln.at, chans);
        if (i == null) continue;
        const y = Math.round(i * lane) + 0.5;
        const hot = drag && drag.line === ln;
        ctx.setLineDash(CONF_DASH[ln.confidence] || CONF_DASH.likely);
        ctx.strokeStyle = BARRY.token(hot ? '--text' : '--accent');
        ctx.lineWidth = hot ? 2.5 : 1.8;
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
        ctx.setLineDash([]);
        const txt = shortName(ln.below || ln.above);
        const tw = ctx.measureText(txt).width;
        ctx.fillStyle = 'rgba(0,0,0,0.6)';
        ctx.fillRect(W - 16 - tw - 4, y - 11, tw + 6, 11);
        ctx.fillStyle = BARRY.token('--accent');
        ctx.fillText(txt, W - 16, y);
      }
    }
  }

  /* A curve through points, some missing. Solid where neighbours are both
     there; across a missing channel (a bad one, usually) a faint dotted
     bridge, so a curve does not stop dead and start again further down
     looking like two curves (2026-10-12, "weird gap"). */
  function curve(ctx, pts) {
    let run = [];
    let lastEnd = null;
    const flush = () => {
      if (run.length) {
        if (lastEnd && run.length) {
          ctx.save();
          ctx.setLineDash([2, 3]);
          ctx.globalAlpha *= 0.6;
          ctx.beginPath();
          ctx.moveTo(lastEnd[0], lastEnd[1]);
          ctx.lineTo(run[0][0], run[0][1]);
          ctx.stroke();
          ctx.restore();
        }
        ctx.beginPath();
        ctx.moveTo(run[0][0], run[0][1]);
        for (let k = 1; k < run.length; k++) ctx.lineTo(run[k][0], run[k][1]);
        ctx.stroke();
        lastEnd = run[run.length - 1];
      }
      run = [];
    };
    for (const p of pts) {
      if (p) run.push(p);
      else flush();
    }
    flush();
  }

  function shortName(id) {
    if (SHORT[id]) return SHORT[id];
    const r = (H.regions() || []).find((x) => x.id === id);
    return r ? r.name.replace(/^CA1 |^DG /, '') : (id || 'below');
  }

  function stripRowAt(e) {
    const r = stripCanvas.getBoundingClientRect();
    const y = e.clientY - r.top;
    const n = H.channels().length || 1;
    return { y, lane: r.height / n, n };
  }

  function nearestLine(e) {
    const { y, lane } = stripRowAt(e);
    let best = null;
    if (ghost && ghost.step === open) {
      const chans = H.channels();
      for (const ln of ghost.lines) {
        const i = laneOfRow(ln.at, chans);
        if (i == null) continue;
        const d = Math.abs(i * lane - y);
        if (d <= 6 && (!best || d < best.d)) best = { d, kind: 'ghost', line: ln };
      }
    }
    if (best) return best;
    // an accepted boundary
    const chans = H.channels();
    const sh = sheet();
    const lab = (c) => (sh && sh.labels ? sh.labels[String(c.number)] : null);
    for (let i = 1; i < chans.length; i++) {
      if (lab(chans[i - 1]) === lab(chans[i])) continue;
      const d = Math.abs(i * lane - y);
      if (d <= 5 && (!best || d < best.d)) {
        best = { d, kind: 'label', at: i, above: lab(chans[i - 1]),
                 below: lab(chans[i]) };
      }
    }
    return best;
  }

  function stripHover(e) {
    if (drag || !stripCanvas) return;
    stripCanvas.style.cursor = nearestLine(e) ? 'ns-resize' : '';
  }

  function stripDown(e) {
    const hit = nearestLine(e);
    if (!hit) return;
    e.preventDefault();
    drag = hit;
    if (hit.kind === 'ghost') drag.line = hit.line;
    const move = (ev) => {
      const { y, lane, n } = stripRowAt(ev);
      const row = Math.max(0, Math.min(n, Math.round(y / lane)));
      if (drag.kind === 'ghost') {
        // Lanes on screen, rows of the whole probe in the proposal.
        const at = rowOfLane(row, H.channels());
        if (at != null && drag.line.at !== at) {
          drag.line.at = at;
          drawStrip();
          H.redraw();
        }
      } else {
        drag.to = row;
        drawStrip();
      }
    };
    const up = async () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
      const d = drag;
      drag = null;
      if (d.kind === 'ghost') {
        confirming = null;
        H.render();
        publish();
        return;
      }
      if (d.to == null || d.to === d.at) { drawStrip(); return; }
      /* Moving an accepted boundary relabels the channels it passes -- all of
         them, in the sheet's order, including any the traces are not
         drawing just now. Relabelling only the drawn ones would leave every
         hidden channel in between on the old side of the line. */
      const lanes = H.channels();
      const all = allChans().map((c) => c.number);
      const idx = (laneI) => (laneI >= lanes.length ? all.length
        : all.indexOf(lanes[laneI].number));
      const from = idx(d.at), to = idx(d.to);
      const map = {};
      if (from >= 0 && to >= 0) {
        if (to > from) for (let i = from; i < to; i++) map[all[i]] = d.above;
        else for (let i = to; i < from; i++) map[all[i]] = d.below;
      }
      await H.setLabels(map);
      drawStrip();
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  }

  /* ==================================================================
     On the traces and rasters: the ghost lines
     ================================================================== */
  function drawGhost(ctx, chans, x0, plotW, y0, lane) {
    if (!ghost || ghost.step !== open || !sug || !chans || !chans.length) return;
    ctx.save();
    for (const ln of ghost.lines) {
      const i = laneOfRow(ln.at, chans);
      if (i == null) continue;
      const y = Math.round(y0 + i * lane) + 0.5;
      ctx.setLineDash(CONF_DASH[ln.confidence] || CONF_DASH.likely);
      ctx.globalAlpha = 0.85;
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 3.5;
      ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + plotW, y); ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = BARRY.token('--accent');
      ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + plotW, y); ctx.stroke();
    }
    // A picked ICA check: where its component sinks, solid, in its colour.
    if (icaPick && open === '3' && icaPick.row != null) {
      const i = laneOfRow(icaPick.row, chans);
      if (i != null && i < chans.length) {
        const y = Math.round(y0 + (i + 0.5) * lane) + 0.5;
        ctx.setLineDash([]);
        ctx.globalAlpha = 0.9;
        ctx.strokeStyle = BARRY.token(icaPick.kind === 'slow' ? '--c2' : '--warn');
        ctx.lineWidth = 2.5;
        ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + plotW, y); ctx.stroke();
        ctx.globalAlpha = 1;
        ctx.font = '10px system-ui, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'bottom';
        ctx.fillStyle = ctx.strokeStyle;
        ctx.fillText('ICA ' + icaPick.kind + ' \u03b3 sink', x0 + 6, y - 2);
      }
    }
    ctx.restore();
  }

  /* ==================================================================
     The evidence window
     ================================================================== */
  const linkChannel = () => 'strata-steps:' + (H ? H.gid : '');

  /* Coalesced: dragging a line publishes on every row it crosses, and only
     the newest picture is worth sending. */
  let sending = false;
  let pending = null;

  function publish(force) {
    if (!H && !(force && force.off)) return;
    rev += 1;
    const value = (force && force.off) ? { off: true } : {
      gid: H.gid, path: H.path(), step: open, rev,
      channels: allChans().map((c) => c.number),
      labels: (sheet() || {}).labels || {},
      regions: H.regions(),
      lines: ghost && ghost.step === open ? ghost.lines : [],
      affected: (() => { const a = affected(); return a ? Array.from(a) : null; })(),
      proposed: (() => { const m = proposedLabels(); return m ? Object.fromEntries(m) : null; })(),
      ica_pick: icaPick ? icaPick.component : null,
      ica_ready: !!(sug && sug.ica_ready),
      focus: focusRegions() ? Array.from(focusRegions()) : null,
      overrides,
      states_n: walk().length,
      theme: (BARRY.state || {}).theme,
    };
    send({ channel: linkChannel(), origin: 'strata-main', value });
  }

  async function send(msg) {
    if (sending) { pending = msg; return; }
    sending = true;
    try {
      await apiPost('/api/link', msg);
    } catch (e) { /* best effort, like the rest of the linking */
    } finally {
      sending = false;
      const next = pending;
      pending = null;
      if (next) send(next);
    }
  }

  /* The aid window is StrataScope's own (strata.js opens it on the way in);
     this brings it forward, or opens it again if it was closed. */
  function openAids() {
    if (!H) return;
    if (!H.focusAids()) H.openAids();
    setTimeout(publish, 600);
  }

  return {
    enter, leave, section, drawer, railStrip, layout, drawStrip, drawGhost,
    stripWidth, publish, openAids,
    // strata.js tells this when the sheet changed under it
    sheetChanged: () => { drawStrip(); publish(); },
    get open() { return open; },
    get active() { return !!H; },
    // For web/_dev/stratasteps.html
    _state: () => ({ status, open, sug, ghost, overrides, guide, checks,
                     drag: drag ? { kind: drag.kind, at: drag.line ? drag.line.at : drag.at } : null,
                     paint }),
    _openStep: openStep,
    proposedLabels,
    affected,
    focusRegions,
    _labelsFromLines: labelsFromLines,
  };
})();
