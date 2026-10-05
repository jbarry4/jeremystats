/* ==========================================================================
   driftmono.js -- the Monolith, from the Drift panel.

   Drift's third tab. Every coupling measure from 1 to 55 Hz, Precon1 ->
   Precon4, computed on the VACC (backend/monolith.py, backend/sweep.py)
   and viewed on its own page (web/monolith.html). Five steps, in order,
   each with its button, and one primary at a time -- whichever step comes
   next:

     Upload       the 48 folders to the cluster, Scratch or Temp (asked
                  every time, Scratch first); the size is said before
                  anything is sent, and pressing it again carries on
     Check        one listing of both places, file by file against the
                  copy here; and where the run's tasks are, once it exists
     Run          one slurm array; the cost said on the button
     Fetch        only when pressed: the answers come home and are pooled
     View         the Monolith page, and the artifact in Results

   It polls /api/arc/monolith/status every two seconds while Jarvis is
   uploading or fetching, and the cluster (one call) every two minutes while
   the run is going and the tab is on screen. It stops the moment its host
   leaves the page.
   ========================================================================== */
'use strict';

BARRY.driftMono = (function () {
  const POLL_MS = 2000;
  const CLUSTER_MS = 120000;
  const KIND_SAY = { state: 'state, 4 band chunks', trans_slow: 'slow transitions',
                     trans_fast: 'fast transitions', pac: 'PAC', rest: 'rest',
                     pac_rest: 'rest PAC', pac_trans: 'PAC at the transitions' };

  const ms = {
    host: null, status: null, err: null, asking: false, acting: false,
    timer: null, clusterTimer: null, key: null, dest: 'scratch', plan: null,
    planning: false, open: { days: false, tasks: false, facts: false },
  };

  const plural = (n, one, many) => Number(n).toLocaleString() + ' ' + (n === 1 ? one : (many || one + 's'));
  const log = (what, data) => {
    try { if (BARRY.activity) BARRY.activity.log(what, data); } catch (e) { /* no-op */ }
  };
  function bytes(n) {
    n = Number(n) || 0;
    if (n >= 1e12) return (n / 1e12).toFixed(2) + ' TB';
    if (n >= 1e9) return (n / 1e9).toFixed(n >= 1e10 ? 0 : 1) + ' GB';
    if (n >= 1e6) return (n / 1e6).toFixed(0) + ' MB';
    if (n >= 1e3) return (n / 1e3).toFixed(0) + ' KB';
    return n + ' B';
  }
  function sayS(s) {
    if (s == null || !isFinite(s)) return 'unknown';
    if (s < 90) return Math.max(1, Math.round(s)) + ' s';
    if (s < 5400) return Math.round(s / 60) + ' min';
    return (s / 3600).toFixed(1) + ' h';
  }
  function clock(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return String(iso);
    const today = new Date().toDateString() === d.toDateString();
    const hm = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return today ? hm : d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + hm;
  }
  const ago = (iso) => {
    const t = Date.parse(iso);
    return isNaN(t) ? '' : sayS((Date.now() - t) / 1000) + ' ago';
  };

  /* ------------------------------------------------------------------
     Reading where it is
     ------------------------------------------------------------------ */
  async function refresh() {
    if (ms.asking) return;
    ms.asking = true;
    try {
      ms.status = await api('/api/arc/monolith/status');
      ms.err = null;
      // Where to upload is asked every time, Scratch first: a plan worked
      // out last time for Temp does not choose for this time.
    } catch (e) {
      ms.err = e.message || String(e);
      ms.key = null;
    } finally {
      ms.asking = false;
    }
    draw();
    poll();
  }

  const working = (S) => !!(S && S.work && S.work.status === 'running');
  const runActive = (S) => !!(S && S.run && S.poll && S.poll.active);

  function poll() {
    const here = !!(ms.host && ms.host.isConnected);
    const busy = working(ms.status);
    if (busy && here && !ms.timer) {
      ms.timer = setInterval(() => {
        if (!ms.host || !ms.host.isConnected) { stop(); return; }
        refresh();
      }, POLL_MS);
    } else if ((!busy || !here) && ms.timer) {
      clearInterval(ms.timer);
      ms.timer = null;
    }
    const watch = runActive(ms.status) && here;
    if (watch && !ms.clusterTimer) {
      ms.clusterTimer = setInterval(() => {
        if (!ms.host || !ms.host.isConnected) { stop(); return; }
        if (document.hidden || ms.acting) return;
        act('/api/arc/monolith/check', { run_only: true }, 'check.auto');
      }, CLUSTER_MS);
    } else if (!watch && ms.clusterTimer) {
      clearInterval(ms.clusterTimer);
      ms.clusterTimer = null;
    }
  }
  function stop() {
    if (ms.timer) clearInterval(ms.timer);
    if (ms.clusterTimer) clearInterval(ms.clusterTimer);
    ms.timer = null;
    ms.clusterTimer = null;
  }

  /* ------------------------------------------------------------------
     Acting
     ------------------------------------------------------------------ */
  async function act(path, body, what, okSay) {
    if (ms.acting) return null;
    ms.acting = what;
    ms.key = null;
    draw();
    let got = null;
    try {
      got = await apiPost(path, body || {});
      if (got && got.status) ms.status = got.status;
      log('arc.monolith.' + what, body || {});
      if (okSay) toast(okSay, 'ok', 7000);
    } catch (e) {
      if (!/older code/.test(e.message || '') && !/^Stopped/.test(e.message || '')) {
        reportClientError('driftmono.' + what, e.message, e.stack);
      }
      toast(e.message, 'err', 12000);
    } finally {
      ms.acting = false;
    }
    await refresh();
    return got;
  }

  async function askPlan(dest) {
    if (ms.acting) return;              // one thing at a time; the plan in hand stays
    ms.dest = dest || ms.dest;
    ms.planning = true;
    ms.plan = null;
    draw();
    const got = await act('/api/arc/monolith/upload/plan', { dest: ms.dest }, 'upload.plan');
    ms.planning = false;
    if (got && got.plan) ms.plan = got.plan;
    draw();
  }
  const upload = () => act('/api/arc/monolith/upload', { dest: ms.dest, confirm: true }, 'upload',
    'Uploading to ' + destLabel(ms.dest) + '. Files already there are skipped; '
    + 'it carries on from where it stops.');
  const check = () => act('/api/arc/monolith/check', {}, 'check');
  const run = () => act('/api/arc/monolith/run', { confirm: true }, 'run',
    'Submitted. Check the VACC to see the tasks move.');
  /* A small run that adds what the built Monolith lacks (the delta band,
     PAC at the transitions); fetching it rebuilds the Monolith from both. */
  const addRun = (extra) => act('/api/arc/monolith/run', { confirm: true, extra }, 'run.add',
    'Submitted the addition. Check the VACC to see it move; fetching it rebuilds the Monolith with it.');
  /* The trajectory: Precon2 and Precon3 into what goes, then (after the
     upload and a check) a run of only them. */
  const extendIt = () => act('/api/arc/monolith/manifest/extend', { confirm: true }, 'extend',
    'Adding Precon2 and Precon3 to what goes. Upload next: it sends only what is not on the cluster yet.');
  const runTraj = () => act('/api/arc/monolith/run', { confirm: true, extra: { days: ['Precon2', 'Precon3'] } }, 'run.traj',
    'Submitted Precon2 and Precon3. Check the VACC to see them move; fetching rebuilds the Monolith with them.');
  const fetchIt = () => act('/api/arc/monolith/fetch', { confirm: true }, 'fetch',
    'Fetching the answers and building the Monolith.');
  const stopWork = () => act('/api/arc/monolith/stop', {}, 'stop');
  async function cancelRun() {
    const ok = await BARRY.confirm('Cancel the run on the VACC',
      'Every task of this run that has not finished is cancelled on the cluster. '
      + 'Answers already written are kept, and can still be fetched.', 'Cancel the run', true);
    if (ok) act('/api/arc/monolith/cancel', { confirm: true }, 'cancel', 'Cancelled on the cluster.');
  }
  function view() {
    log('arc.monolith.view', {});
    window.open('/monolith.html', '_blank', 'noopener');
  }
  function inResults() {
    const B = (ms.status || {}).built || {};
    if (BARRY.artifacts && BARRY.artifacts.open && B.artifact_id) {
      BARRY.artifacts.open(B.artifact_id, B.version);
    }
  }

  const destLabel = (id) => (((ms.status || {}).dests || []).find((d) => d.id === id) || {}).label
    || (id === 'temp' ? 'Temp' : 'Scratch');

  /* ------------------------------------------------------------------
     Which step is next
     ------------------------------------------------------------------ */
  function stepOf(S) {
    if (!S) return 'upload';
    if (S.built && S.run && S.built.rid === S.run.rid) return 'view';
    if (S.run) {
      if (runActive(S)) return 'check';
      const P = S.poll || {};
      if (P.tasks && (P.answered || []).length) return 'fetch';
      return 'check';
    }
    const C = S.check;
    if (C && C.can_run && C.manifest === ((S.manifest || {}).digest)) return 'run';
    const U = S.upload || {};
    if (U.status && /^done/.test(U.status) && !C) return 'check';
    return 'upload';
  }

  /* ------------------------------------------------------------------
     Painting
     ------------------------------------------------------------------ */
  function paint(host) {
    if (!host) return;
    ms.host = host;
    ms.key = null;
    draw();
    refresh();
  }

  function draw() {
    const host = ms.host;
    if (!host || !host.isConnected) return;
    const S = ms.status;
    const key = JSON.stringify([S, ms.err, ms.acting, ms.plan, ms.planning, ms.dest]);
    if (key === ms.key) return;
    ms.key = key;
    host.innerHTML = '';
    if (ms.err) {
      host.appendChild(el('div', { class: 'card dpc-card' }, [
        el('div', { class: 'empty-state dpc-empty' }, [
          el('strong', { text: 'Could not read where the Monolith is' }),
          el('p', { text: /older code|405|404/.test(ms.err)
            ? 'This Jarvis is running code from before this tab existed. Restart Jarvis, then open Drift again.'
            : ms.err + ' — check that Jarvis is running, then try again.' }),
          el('div', { class: 'head-actions' }, [
            el('button', { class: 'btn', text: 'Try again', onclick: () => refresh() })]),
        ]),
      ]));
      return;
    }
    if (!S) {
      host.appendChild(el('div', { class: 'card dpc-card' }, [
        loader('Reading where the Monolith is', 'the upload, the cluster, the run and what is built')]));
      return;
    }
    const next = stepOf(S);
    host.appendChild(aboutCard(S));
    if (S.vacc && S.vacc.configured === false) {
      host.appendChild(el('div', { class: 'card dpc-card' }, [el('p', { class: 'dpc-warn',
        text: 'No VACC account is set up on this computer. Set one up from the VACC panel; '
          + 'everything here goes through it.' })]));
    }
    host.appendChild(uploadCard(S, next));
    host.appendChild(checkCard(S, next));
    host.appendChild(runCard(S, next));
    host.appendChild(fetchCard(S, next));
    host.appendChild(viewCard(S, next));
  }

  function primary(on) { return 'btn' + (on ? ' dpc-go' : ' ghost'); }
  function off(extra) { return (ms.acting || extra) ? 'disabled' : null; }

  function stepHead(n, title, state, cls) {
    return el('div', { class: 'dpc-head dmo-step-head' }, [
      el('span', { class: 'dmo-n ' + (cls || ''), text: String(n) }),
      el('strong', { text: title }),
      state ? el('span', { class: 'hint', text: state }) : null,
    ]);
  }

  function fold(key, summary, body) {
    const d = el('details', { class: 'dpc-fold', open: ms.open[key] ? 'open' : null }, [
      el('summary', { text: summary }), body]);
    d.addEventListener('toggle', () => { ms.open[key] = d.open; });
    return d;
  }

  function bar(frac, label) {
    return el('div', { class: 'comod-total dmo-bar' }, [
      el('div', { class: 'comod-bar' }, [el('div', { class: 'comod-bar-fill',
        style: 'width:' + Math.round(100 * Math.max(0, Math.min(1, frac || 0))) + '%' })]),
      el('span', { class: 'comod-eta', text: label || '' }),
    ]);
  }

  /* ---- what it is ---- */
  function aboutCard(S) {
    const M = S.manifest;
    const rats = M ? M.rats.map((r) => 'r' + r).join(', ') : 'r3, r4, r6–r11';
    const card = el('div', { class: 'card dpc-card dmo-about' }, [
      el('div', { class: 'dpc-head' }, [el('strong', { text: 'The Monolith: every measure, 1–55 Hz' })]),
      el('p', { class: 'dpc-q', text: 'How does coupling between regions change from Precon1 to '
        + 'Precon4, at every frequency and by every measure? Each rat is compared with itself; the '
        + 'changes are pooled over rats exactly as the Precon drifts were. It runs on the VACC, '
        + 'and is read on one page: a circuit, a frequency slider, and the points of interest.' }),
    ]);
    const facts = el('table', { class: 'art-params dpc-facts' }, [el('tbody', {}, [
      row('Rats', rats + ' — each on both days, both cue pairings pooled blind to type'
        + (M && M.excluded ? '; left out: ' + Object.entries(M.excluded).map(([r, w]) => r + ' (' + w + ')').join('; ') : '')),
      row('Frequencies', 'a band on every whole hertz from 1 to 55, ±15% (never under ±0.5 Hz), '
        + 'cut at 55 Hz so none reaches the 60 Hz notch; theta, beta and low gamma kept as their own rows'),
      row('Windows', 'baseline, cue 1, cue 2 and after (10 s each); onset, switch and offset at '
        + '−3/+3 s for bands up to 12 Hz and −1/+2 s above'),
      row('Measures', 'coherence, imaginary coherence, raw and envelope cross-correlation (two '
        + 'cycles of lag), amplitude r at zero lag, orthogonalised envelope r, PLV, PPC, PLI, wPLI, '
        + 'debiased wPLI, Granger both ways and net; each region’s power; phase–amplitude coupling'),
      row('Layers', 'raw, and minus FP (each day’s cue value less its FP1 + FP2 rest value)'),
      row('Statistics', 'DerSimonian–Laird over rats, Hartung–Knapp t on k − 1 df, at least '
        + (S.min_rats || 5) + ' rats; p uncorrected, and said so wherever it is shown'),
      row('Points of interest', 'single entries with p < .05, most rats the same way first, '
        + 'then p; at most 3 per region pair'),
      row('Cluster', 'one task per rat-day × kind × band chunk, at most ' + (S.concurrency || 100)
        + ' at once'),
    ])]);
    card.appendChild(fold('facts', 'What exactly it does', facts));
    if (M && (M.notes || []).length) {
      card.appendChild(fold('notes', plural(M.notes.length, 'note') + ' on the recordings',
        el('ul', { class: 'dpc-fails' }, M.notes.map((n) => el('li', { text: n })))));
    }
    return card;
  }
  function row(k, v) { return el('tr', {}, [el('th', { text: k }), el('td', { text: v })]); }

  /* ---- 1. upload ---- */
  function uploadCard(S, next) {
    const W = S.work && S.work.what === 'upload' ? S.work : null;
    const U = S.upload || {};
    const M = S.manifest;
    const going = W && W.status === 'running';
    const state = going ? 'uploading to ' + destLabel((W.progress || {}).dest)
      : U.status ? U.status.replace(/^done/, 'done') + ' · ' + destLabel(U.dest)
        + (U.ended ? ' · ' + clock(U.ended) : '')
      : M ? plural(M.n_folders, 'folder') + ', ' + plural(M.n_files || 0, 'file') + ', ' + bytes(M.bytes)
        : '48 folders, as recorded';
    const card = el('div', { class: 'card dpc-card dmo-step', 'data-step': 'upload' }, [
      stepHead(1, 'Upload to the VACC', state, next === 'upload' ? 'next' : (U.status ? 'done' : '')),
    ]);
    const IR = S.interrupted;
    if (IR && IR.what === 'upload' && !going) {
      card.appendChild(el('p', { class: 'dpc-warn', text: 'The upload was cut short when Jarvis stopped ('
        + clock(IR.started) + '). Uploading again carries on: every file already there at its size is skipped.' }));
    }
    if (going) {
      const P = W.progress || {};
      const frac = P.bytes_total ? (P.bytes_done || 0) / P.bytes_total : 0;
      const left = P.rate ? ((P.bytes_total || 0) - (P.bytes_done || 0)) / P.rate : null;
      card.appendChild(el('p', { class: 'dmo-now', text: P.phase === 'listing'
        ? 'Listing what is already there…'
        : bytes(P.bytes_done) + ' of ' + bytes(P.bytes_total) + ' · ' + (P.folder || '')
          + (P.file ? ' · ' + P.file : '') }));
      card.appendChild(bar(frac, P.rate ? bytes(P.rate) + '/s · about ' + sayS(left) + ' left'
        : Math.round(100 * frac) + '%'));
      if ((P.failed || []).length) {
        card.appendChild(el('ul', { class: 'dpc-fails' }, P.failed.map((f) =>
          el('li', { text: f.folder + ': ' + f.why }))));
      }
      card.appendChild(el('div', { class: 'head-actions dpc-actions' }, [
        el('span', { class: 'hint', text: 'It keeps going if you leave this page. If Jarvis stops, '
          + 'uploading again carries on from where it was.' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: W.stopping ? 'Stopping…' : 'Stop the upload',
          disabled: off(W.stopping), onclick: stopWork }),
      ]));
      return card;
    }
    if (U.failed && U.failed.length) {
      card.appendChild(el('p', { class: 'dpc-warn', text: plural(U.failed.length, 'folder')
        + ' did not finish. Uploading again sends only what is missing.' }));
      card.appendChild(el('ul', { class: 'dpc-fails' }, U.failed.map((f) =>
        el('li', { text: f.folder + ': ' + f.why }))));
    }
    // Where to: asked every time, Scratch first.
    const dests = (S.dests && S.dests.length) ? S.dests
      : [{ id: 'scratch', label: 'Scratch' }, { id: 'temp', label: 'Temp' }];
    const chosen = dests.find((d) => d.id === ms.dest) || dests[0];
    card.appendChild(el('div', { class: 'dmo-where' }, [
      el('span', { class: 'dmo-k', text: 'Upload to' }),
      el('div', { class: 'seg', role: 'radiogroup' }, dests.map((d) => el('button', {
        class: d.id === ms.dest ? 'active' : '', role: 'radio', 'data-dest': d.id,
        'aria-checked': d.id === ms.dest ? 'true' : 'false', text: d.label,
        disabled: off(ms.planning), onclick: () => { if (d.id !== ms.dest) askPlan(d.id); } }))),
      el('span', { class: 'hint dmo-where-say', text: (chosen.say || '') + (chosen.root ? ' ' + chosen.root : '') }),
    ]));
    const P = ms.plan && ms.plan.dest === ms.dest ? ms.plan : null;
    if (ms.planning) {
      card.appendChild(loader('Working out what goes',
        'reading the 48 folders here (about 20 s the first time), then one listing of '
        + destLabel(ms.dest)));
    } else if (P) {
      const R = P.room || {};
      if (R.say) {
        card.appendChild(el('p', { class: R.fits === false ? 'dpc-warn dmo-room' : 'hint dmo-room', text: R.say
          + (R.fits === false ? ' Choose ' + destLabel(ms.dest === 'temp' ? 'scratch' : 'temp')
            + ', or free some space in ' + destLabel(ms.dest) + ' first.' : '') }));
      }
      card.appendChild(el('p', { class: 'dmo-cost', text: P.files
        ? bytes(P.bytes) + ' in ' + plural(P.files, 'file') + ' to send to ' + destLabel(ms.dest)
          + (P.skipped ? '; ' + plural(P.skipped, 'file') + ' already there' : '')
          + '. About ' + sayS(P.seconds) + ' at six streams (~80 MB/s, measured).'
        : 'Everything is already in ' + destLabel(ms.dest) + ' (' + plural(P.skipped, 'file') + ').' }));
      card.appendChild(planFold(P));
    }
    const isNext = next === 'upload';
    const bits = [];
    if (!P) {
      bits.push(el('button', { class: primary(isNext), 'data-go': 'upload.plan', disabled: off(ms.planning),
        text: 'Upload…', onclick: () => askPlan(ms.dest) }));
    } else if (P.files) {
      const full = (P.room || {}).fits === false;
      bits.push(el('button', { class: 'btn ghost', text: 'Work it out again', disabled: off(),
        onclick: () => askPlan(ms.dest) }));
      bits.push(el('button', { class: primary(isNext && !full), 'data-go': 'upload', disabled: off(full),
        title: full ? 'There is not enough room there for this upload.' : null,
        text: full ? 'Not enough room in ' + destLabel(ms.dest)
          : 'Upload ' + bytes(P.bytes) + ' to ' + destLabel(ms.dest), onclick: upload }));
    } else {
      bits.push(el('button', { class: 'btn ghost', text: 'Work it out again', disabled: off(),
        onclick: () => askPlan(ms.dest) }));
    }
    card.appendChild(el('div', { class: 'head-actions dpc-actions' }, [
      el('span', { class: 'hint', text: 'What Cheetah recorded goes — every CSC* file, the video (VT*), '
        + 'Events.nev and Cheetah’s logs — under the recordings’ own folder names, as project / rat / '
        + 'recording. Anything processed into the folders stays here'
        + (M && M.left_here ? (M.left_here.n ? ' (' + plural(M.left_here.n, 'file') + ', ' + bytes(M.left_here.bytes) + ')'
          : ' (none found in these folders)') : '')
        + '. The copy here is only read.' }),
      el('div', { class: 'spacer' }),
    ].concat(bits)));
    return card;
  }

  function planFold(P) {
    const t = el('table', { class: 'art-params dpc-t' }, [el('tbody', {}, [
      el('tr', {}, ['rat', 'day', 'folder', 'to send', 'already there'].map((h) => el('th', { text: h }))),
    ].concat((P.rows || []).map((r) => el('tr', {}, [
      el('td', { text: 'r' + r.rat }), el('td', { text: r.day }), el('td', { text: r.role }),
      el('td', { class: 'num', text: r.why ? r.why : r.n_send ? plural(r.n_send, 'file') + ', ' + bytes(r.bytes) : '—' }),
      el('td', { class: 'num', text: r.why ? '' : String(r.n_skip) }),
    ]))))]);
    return fold('plan', 'Folder by folder', el('div', { class: 'dpc-items' }, [t]));
  }

  /* ---- 2. check ---- */
  function checkCard(S, next) {
    const C = S.check;
    const R = S.run;
    const P = S.poll;
    const state = C ? 'checked ' + ago(C.at) + ' · ' + C.n_ready + ' of ' + C.n_folders
      + ' folders whole · ' + plural((C.ready_rats || []).length, 'rat') + ' ready' : 'not checked yet';
    const card = el('div', { class: 'card dpc-card dmo-step', 'data-step': 'check' }, [
      stepHead(2, 'Check the VACC', state, next === 'check' ? 'next' : (C && C.can_run ? 'done' : '')),
    ]);
    if (ms.acting === 'check' || ms.acting === 'check.auto') {
      card.appendChild(loader('Asking the VACC', R ? 'both places, and where the run’s tasks are'
        : 'one listing of every folder, in Scratch and in Temp'));
    }
    if (C) {
      card.appendChild(el('p', { class: C.can_run ? 'dmo-ok' : 'dpc-warn', text: C.can_run
        ? 'Detected: ' + plural((C.ready_rats || []).length, 'rat') + ' with both days whole on the cluster ('
          + (C.ready_rats || []).map((r) => 'r' + r).join(', ') + '). Ready to run.'
        : 'Not enough is there yet: ' + plural((C.ready_rats || []).length, 'rat') + ' with both days whole, and '
          + (S.min_rats || 5) + ' are needed. Upload, then check again.' }));
      card.appendChild(daysGrid(C));
    }
    if (R && P) card.appendChild(pollBlock(S));
    card.appendChild(el('div', { class: 'head-actions dpc-actions' }, [
      el('span', { class: 'hint', text: R ? 'Reads only. While the run goes it is asked again every two minutes this tab is open.'
        : 'Reads only: one listing of the cluster.' }),
      el('div', { class: 'spacer' }),
      el('button', { class: primary(next === 'check'), 'data-go': 'check', disabled: off(),
        text: 'Check VACC status', onclick: check }),
    ]));
    return card;
  }

  function daysGrid(C) {
    const days = C.days || [];
    const rats = [];
    for (const d of days) if (rats.indexOf(d.rat) < 0) rats.push(d.rat);
    const cell = (d) => el('td', { class: 'dmo-cell' }, (d ? d.folders : []).map((f) => {
      const at = f.at || {};
      const st = f.use ? 'complete' : (Object.values(at).some((x) => x.state === 'partial') ? 'partial' : 'missing');
      const best = f.use || Object.keys(at).find((k) => at[k].state === 'partial') || 'scratch';
      const x = at[best] || {};
      return el('span', { class: 'dmo-dot ' + st, title: f.role + ': ' + st
        + (f.use ? ' in ' + destLabel(f.use) : x.of ? ' — ' + x.have + ' of ' + x.of + ' files' : ''),
        text: f.role });
    }));
    const t = el('table', { class: 'art-params dpc-t dmo-days' }, [el('tbody', {}, [
      el('tr', {}, ['rat', 'Precon1', 'Precon4'].map((h) => el('th', { text: h }))),
    ].concat(rats.map((r) => el('tr', {}, [
      el('td', { text: 'r' + r }),
      cell(days.find((d) => d.rat === r && d.day === 'Precon1')),
      cell(days.find((d) => d.rat === r && d.day === 'Precon4')),
    ]))))]);
    return fold('days', 'Rat by rat', el('div', { class: 'dpc-items' }, [t]));
  }

  function pollBlock(S) {
    const P = S.poll || {};
    if (P.error) return el('p', { class: 'dpc-warn', text: 'The cluster did not answer about the run: ' + P.error });
    const T = P.tally || {};
    const n = P.n || 0;
    const box = el('div', { class: 'dmo-poll' }, [
      el('div', { class: 'section-label', text: 'The run · ' + plural(n, 'task') + ' · asked ' + ago(P.at) }),
      el('div', { class: 'dmo-tally' }, [
        ['done', T.done], ['running', T.running], ['queued', T.queued], ['failed', T.failed], ['unknown', T.unknown],
      ].filter(([, v]) => v).map(([k, v]) => el('span', { class: 'dmo-chip ' + k, text: v + ' ' + k }))),
      bar(n ? (T.done || 0) / n : 0, P.finished ? 'finished' : Math.round(100 * (n ? (T.done || 0) / n : 0)) + '% answered'),
    ]);
    const failed = (P.tasks || []).filter((t) => t.state === 'failed');
    if (failed.length) {
      box.appendChild(fold('tasks', plural(failed.length, 'task') + ' did not answer', el('ul', { class: 'dpc-fails' },
        failed.slice(0, 40).map((t) => el('li', {}, [
          el('span', { text: t.key + ': ' + (t.why || t.slurm || 'failed') }),
          t.log ? el('pre', { class: 'dop-log dmo-log', text: t.log }) : null,
        ])))));
    }
    return box;
  }

  /* ---- 3. run ---- */
  function runCard(S, next) {
    const R = S.run;
    const C = S.check;
    const plan = (C || {}).plan;
    const P = S.poll || {};
    const again = S.again || [];
    const state = R ? 'submitted ' + clock(R.submitted_at) + ' · array ' + R.arrays.map((a) => a.id).join(', ')
      : plan ? plural(plan.n_tasks, 'task') + ' ready to go' : 'after the check';
    const card = el('div', { class: 'card dpc-card dmo-step', 'data-step': 'run' }, [
      stepHead(3, 'Run the VACC job', state, next === 'run' ? 'next' : (R ? 'done' : '')),
    ]);
    const stale = (S.code_changed || []).length > 0;
    if (plan && !R) {
      card.appendChild(el('p', { class: 'dmo-cost', text: plural(plan.n_tasks, 'task') + ' ('
        + Object.entries(plan.by_kind || {}).map(([k, v]) => v + ' ' + (KIND_SAY[k] || k)).join(', ')
        + ') · about ' + sayS(plan.cpu_s) + ' of compute in all · at most ' + plan.concurrency
        + ' at once, so about ' + sayS(plan.wall_s) + ' once they start, plus the queue · partition '
        + plan.partition + ', ' + plan.time + ' and ' + plan.mem + ' a task.' }));
      card.appendChild(el('p', { class: 'hint', text: 'The rate is this computer’s, measured; the '
        + 'cluster’s cores are of the same order. The answers are written beside the data, and '
        + 'stay there until you fetch them.' }));
    }
    if (R) {
      card.appendChild(el('p', { class: 'hint', text: plural(R.tasks.length, 'task') + ', rats '
        + (R.ready_rats || []).map((r) => 'r' + r).join(', ') + ' · in ' + destLabel(R.dest) + ' at ' + R.rdir }));
    }
    if (stale) {
      card.appendChild(el('p', { class: 'dpc-warn', text: 'Restart Jarvis before running: it is running '
        + 'older code for ' + S.code_changed.join(', ') + ', and the cluster would be sent the new files.' }));
    }
    const bits = [];
    if (R && runActive(S)) {
      bits.push(el('button', { class: 'btn ghost danger', text: 'Cancel the run', disabled: off(),
        onclick: cancelRun }));
    } else if (R && again.length && again.length < R.tasks.length) {
      bits.push(el('button', { class: primary(next === 'check' || next === 'fetch'), 'data-go': 'run.again',
        disabled: off(stale), text: 'Run the ' + plural(again.length, 'unfinished task') + ' again',
        onclick: run }));
    } else if (!R) {
      bits.push(el('button', { class: primary(next === 'run'), 'data-go': 'run',
        disabled: off(stale || !(C && C.can_run)),
        title: !(C && C.can_run) ? 'Check the VACC first: the run goes only where the recordings are whole.' : null,
        text: plan ? 'Run ' + plural(plan.n_tasks, 'task') + ' on the VACC' : 'Run VACC job', onclick: run }));
    }
    if (bits.length) {
      card.appendChild(el('div', { class: 'head-actions dpc-actions' }, [
        el('span', { class: 'hint', text: R ? '' : 'Uses the lab’s cluster allocation. It keeps running if '
          + 'Jarvis or this computer stops; check again to pick it up.' }),
        el('div', { class: 'spacer' }),
      ].concat(bits)));
    }
    return card;
  }

  /* ---- 4. fetch ---- */
  function fetchCard(S, next) {
    const W = S.work && S.work.what === 'fetch' ? S.work : null;
    const F = S.fetch;
    const B = S.built;
    const R = S.run;
    const P = S.poll || {};
    const going = W && W.status === 'running';
    const state = going ? (W.progress.phase || 'working')
      : B && R && B.rid === R.rid ? 'built ' + clock(B.at)
      : F ? 'fetched ' + clock(F.at) : 'only when you press it';
    const card = el('div', { class: 'card dpc-card dmo-step', 'data-step': 'fetch' }, [
      stepHead(4, 'Fetch the results', state, next === 'fetch' ? 'next' : (B ? 'done' : '')),
    ]);
    if (going) {
      const G = W.progress || {};
      if (G.phase === 'fetching') {
        const frac = G.bytes_total ? (G.bytes_done || 0) / G.bytes_total : 0;
        card.appendChild(el('p', { class: 'dmo-now', text: 'Bringing the answers home: ' + bytes(G.bytes_done)
          + (G.bytes_total ? ' of about ' + bytes(G.bytes_total) : '') }));
        card.appendChild(bar(frac, Math.round(100 * frac) + '%'));
      } else {
        card.appendChild(loader(G.phase === 'filing' ? 'Filing the artifact' : 'Pooling over rats',
          G.step === 'assemble' ? 'putting each rat-day’s tasks together' + (G.item ? ' · ' + G.item : '')
          : G.step === 'pool' ? 'every entry of ' + (G.item || '') + ', both layers'
          : 'the points of interest, and the page’s files'));
      }
      card.appendChild(el('div', { class: 'head-actions dpc-actions' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: W.stopping ? 'Stopping…' : 'Stop', disabled: off(W.stopping),
          onclick: stopWork }),
      ]));
      return card;
    }
    if (W && W.status === 'failed') {
      card.appendChild(el('p', { class: 'dpc-warn', text: 'The last fetch stopped: ' + W.error }));
    }
    if (R) {
      const n = (P.answered || []).length;
      card.appendChild(el('p', { class: 'hint', text: n ? plural(n, 'task') + ' of ' + R.tasks.length
        + ' have answered' + (P.out_bytes ? ', about ' + bytes(P.out_bytes) + ' to bring home' : '') + '.'
        + (P.finished ? '' : ' Fetching now builds from what is there; fetch again when the rest have answered.')
        : 'Nothing has answered yet. Check the VACC to see where the run is.' }));
      card.appendChild(el('div', { class: 'head-actions dpc-actions' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: primary(next === 'fetch'), 'data-go': 'fetch', disabled: off(!n),
          text: (B && B.rid === R.rid ? 'Fetch and build again' : 'Fetch results and build the Monolith'),
          onclick: fetchIt }),
      ]));
    }
    return card;
  }

  /* ---- 5. view ---- */
  function viewCard(S, next) {
    const B = S.built;
    const card = el('div', { class: 'card dpc-card dmo-step', 'data-step': 'view' }, [
      stepHead(5, 'View the Monolith', B ? 'artifact ' + B.artifact_id + ' v' + B.version : 'once it is built',
        next === 'view' ? 'next' : ''),
    ]);
    if (B) {
      const c = (B.counts || {}).raw || {};
      const m = (B.counts || {}).minus_fp || {};
      card.appendChild(el('p', { class: 'dmo-cost', text: 'Raw: ' + (c.tested || 0).toLocaleString()
        + ' entries tested, ' + (c.p05 || 0).toLocaleString() + ' with p < .05 (about '
        + (c.chance_p05 || 0).toLocaleString() + ' by chance alone). Minus FP: '
        + (m.p05 || 0).toLocaleString() + ' of ' + (m.tested || 0).toLocaleString()
        + '. Every p is uncorrected.' }));
      if ((B.missing_tasks || []).length) {
        card.appendChild(el('p', { class: 'dpc-warn', text: plural(B.missing_tasks.length, 'task')
          + ' had not answered when it was built; their rat-days are thinner. Fetch again once they have.' }));
      }
      // What a small run can still add, and the button that runs it.
      const miss = S.missing || {};
      const says = [];
      if ((miss.bands || []).length) says.push((S.additions_say || {}).delta || 'the delta band');
      if (miss.pac_trans) says.push((S.additions_say || {}).pac_trans || 'PAC at the transitions');
      if (says.length && !(S.run && S.built && S.run.rid !== S.built.rid)) {
        const C = S.check;
        card.appendChild(el('div', { class: 'dmo-add', 'data-go': 'add' }, [
          el('p', { text: 'This Monolith was built without ' + says.join(' or ') + '. A small run measures only that, '
            + 'on the recordings already on the cluster, and fetching it rebuilds the Monolith from both runs — '
            + 'nothing already measured is measured again.' }),
          el('div', { class: 'head-actions dpc-actions' }, [
            el('span', { class: 'hint', text: C ? 'Uses the lab’s cluster allocation: a few minutes of compute a rat-day.'
              : 'Check the VACC first: the recordings have to be whole on the cluster still.' }),
            el('div', { class: 'spacer' }),
            el('button', { class: 'btn ghost', 'data-go': 'add', disabled: off(!C || (S.code_changed || []).length > 0),
              text: 'Add ' + says.join(' and '), onclick: () => addRun(miss) }),
          ]),
        ]));
      }
    }
    if (B) card.appendChild(trajBlock(S));
    card.appendChild(el('div', { class: 'head-actions dpc-actions' }, [
      el('span', { class: 'hint', text: B ? 'Opens in a new tab. The artifact is in Results too.' : '' }),
      el('div', { class: 'spacer' }),
      B ? el('button', { class: 'btn ghost', text: 'Open in Results', onclick: inResults }) : null,
      el('button', { class: primary(next === 'view'), 'data-go': 'view', disabled: B ? null : 'disabled',
        text: 'View Monolith Artifact', onclick: view }),
    ]));
    return card;
  }

  /* The trajectory: Precon2 and Precon3, measured as the two days are, for
     the page's "Across the four sessions" -- never in the change, never
     tested. Each step is the user's to press: add them to what goes,
     upload (step 1), check the VACC (step 2), run them, fetch (step 4). */
  function trajBlock(S) {
    const T = S.trajectory || {};
    const box = el('div', { class: 'dmo-add dmo-traj', 'data-go': 'traj' });
    const built = T.built || [];
    if (built.length === 2) {
      box.appendChild(el('p', { text: 'Precon2 and Precon3 are in this Monolith: the page shows every line across the four sessions.' }));
      return box;
    }
    const inMan = (T.in_manifest || []).length > 0;
    const ready = T.ready || [];
    const going = S.run && S.built && S.run.rid !== S.built.rid;
    box.appendChild(el('p', { text: 'The trajectory: Precon2 and Precon3, measured exactly as Precon1 and Precon4 are, to follow '
      + 'each line across the four sessions. They never enter the change and are not tested.' }));
    const C = S.check;
    let say, button;
    if (!inMan) {
      say = 'First, add them to what goes: worked out here from the bank, as the two days were (reads only; a minute or two).';
      button = el('button', { class: 'btn ghost', 'data-go': 'traj-add', disabled: off(!!S.work && S.work.status === 'running'),
        text: 'Add Precon2 and Precon3', onclick: extendIt });
    } else if (going) {
      say = 'A run is on the cluster. Check the VACC to follow it, then fetch.';
    } else if (!C || !T.checked_now || !ready.length) {
      say = 'They are in what goes. Upload (step 1) sends only what is not on the cluster yet; then Check the VACC (step 2).'
        + (C && T.checked_now ? ' None is whole on the cluster yet.' : '');
      button = el('button', { class: 'btn ghost', 'data-go': 'traj-run', disabled: 'disabled', text: 'Run Precon2 and Precon3' });
    } else {
      say = ready.length + ' rat-session' + (ready.length === 1 ? ' is' : 's are') + ' whole on the cluster. A run of only them '
        + 'uses the lab’s cluster allocation (about as long as the first run took for two days).';
      button = el('button', { class: 'btn ghost', 'data-go': 'traj-run', disabled: off((S.code_changed || []).length > 0),
        text: 'Run Precon2 and Precon3', onclick: runTraj });
    }
    box.appendChild(el('div', { class: 'head-actions dpc-actions' }, [
      el('span', { class: 'hint', text: say }), el('div', { class: 'spacer' }), button]));
    return box;
  }

  /* ---- Results: the monolith kind ---- */
  const VIEWER = {
    title: 'Monoliths',
    summary: (r) => {
      const s = (r.current || {}).n_summary || {};
      return s.tested ? s.tested.toLocaleString() + ' tested · ' + (s.p05 || 0).toLocaleString() + ' p < .05' : '';
    },
    render: (host, rec, payload) => {
      const c = ((payload || {}).counts || {}).raw || {};
      host.appendChild(el('div', { class: 'dmo-art' }, [
        el('p', { text: (payload || {}).name || rec.name }),
        el('p', { class: 'hint', text: (c.tested || 0).toLocaleString() + ' entries tested in the raw layer, '
          + (c.p05 || 0).toLocaleString() + ' with p < .05 (uncorrected). Built '
          + clock((payload || {}).built_at) + ' from run ' + ((payload || {}).rid || '') + '.' }),
        el('div', { class: 'head-actions' }, [
          el('button', { class: 'btn', text: 'Open the Monolith', onclick: view })]),
      ]));
    },
  };
  function registerResults() {
    if (!BARRY.artifacts || typeof BARRY.artifacts.register !== 'function') return false;
    try { BARRY.artifacts.register('monolith', VIEWER); } catch (e) {
      reportClientError('driftmono.register', e.message, e.stack);
    }
    return true;
  }
  if (!registerResults()) {
    let tries = 0;
    const t = setInterval(() => { tries += 1; if (registerResults() || tries > 300) clearInterval(t); }, 200);
  }

  return {
    paint, refresh,
    get state() { return { status: ms.status, err: ms.err, dest: ms.dest, plan: ms.plan,
                           polling: !!ms.timer, watching: !!ms.clusterTimer,
                           step: ms.status ? stepOf(ms.status) : null }; },
    _stepOf: stepOf,
  };
})();
