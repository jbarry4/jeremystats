/* ==========================================================================
   driftprecon.js -- the Precon1 -> Precon4 analysis, from the Drift panel.

   Drift's second tab. The analysis itself is tools/run_precon_drift.py
   (docs/the-arc-contracts.md section 7); Jarvis starts it as a child
   (backend/preconrun.py) and this tab draws what that child says:

     the cost      worked out first, reading only (about ten seconds), and
                   stated line by line before anything is offered to run --
                   the run route refuses any plan but the one on screen
     the run       its three stages, the item in flight, a bar that only
                   moves forward, the child's own words, and Stop -- which
                   stops BETWEEN items, so nothing is left half-filed
     what it filed the drifts, each opened here (the same renderer as
                   Compare) or in Results, and the report: the write-up,
                   the CSV and the figures

   One primary at a time, and it is whichever step comes next: Work out
   the cost, then Run the analysis (Carry on, when some is already filed),
   then Write the report. It sits at the end of the card it belongs to.

   It polls /api/arc/precon/status every two seconds while something is
   running, and stops polling the moment its host leaves the page.
   ========================================================================== */
'use strict';

BARRY.driftPrecon = (function () {
  const POLL_MS = 2000;
  const STAGES = [
    ['spark', 'Measure the transition windows and re-bank', 'recordings'],
    ['circuits', 'File the circuits, three bands a run', 'runs'],
    ['drifts', 'Pool each rat’s change and test it', 'drifts'],
  ];
  const KIND_SAY = { state: 'state', transition: 'transition', rest: 'rest (FP1+FP2)' };
  const BAND_SAY = { theta: 'Theta 4–12 Hz', beta: 'Beta 13–30 Hz', gamma_low: 'Low gamma 30–55 Hz' };
  const BAND_ORDER = ['theta', 'beta', 'gamma_low'];

  const ps = {
    host: null, status: null, err: null, asking: false, acting: false,
    timer: null, key: null, filed: null,
    open: { roles: false, items: false, log: true, failures: true, figs: true },
    logAtBottom: true,
  };

  const plural = (n, one, many) => n + ' ' + (n === 1 ? one : (many || one + 's'));
  const log = (what, data) => {
    try { if (BARRY.activity) BARRY.activity.log(what, data); } catch (e) { /* no-op */ }
  };
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
  const since = (iso) => {
    const t = Date.parse(iso);
    return isNaN(t) ? null : (Date.now() - t) / 1000;
  };

  /* ------------------------------------------------------------------
     Reading where it is
     ------------------------------------------------------------------ */
  async function refresh() {
    if (ps.asking) return;
    ps.asking = true;
    try {
      const S = await api('/api/arc/precon/status');
      if (ps.err) ps.key = null;
      ps.err = null;
      ps.status = S;
      noticeFiled(S);
    } catch (e) {
      // Said in the card, not sent on: a route that failed has logged its
      // own 500 (fail()), and a server that is gone cannot hear it.
      ps.err = e.message || String(e);
      ps.key = null;
    } finally {
      ps.asking = false;
    }
    draw();
    poll();
  }

  /* New artifacts filed since the last look: tell Results, which lists
     them without being reloaded. */
  function noticeFiled(S) {
    const R = S.runlog || {};
    const k = (R.circuits || 0) + ':' + (R.drifts || []).length;
    if (ps.filed !== null && ps.filed !== k) {
      try { window.dispatchEvent(new CustomEvent('barry:artifact')); } catch (e) { /* no-op */ }
    }
    ps.filed = k;
  }

  function poll() {
    const busy = !!(ps.status && (ps.status.busy
                                  || (ps.status.resume || {}).pending));
    const here = !!(ps.host && ps.host.isConnected);
    if (busy && here && !ps.timer) {
      ps.timer = setInterval(() => {
        if (!ps.host || !ps.host.isConnected) { stopPoll(); return; }
        refresh();
      }, POLL_MS);
    } else if ((!busy || !here) && ps.timer) {
      stopPoll();
    }
  }
  function stopPoll() {
    if (ps.timer) clearInterval(ps.timer);
    ps.timer = null;
  }

  /* ------------------------------------------------------------------
     Acting
     ------------------------------------------------------------------ */
  async function act(path, body, what, okSay) {
    if (ps.acting) return;
    ps.acting = true;
    ps.key = null;
    draw();
    try {
      const got = await apiPost(path, body || {});
      if (got.status) ps.status = Object.assign({}, ps.status || {}, got.status);
      log('arc.precon.' + what, body || {});
      if (okSay) toast(okSay, 'ok', 6000);
    } catch (e) {
      if (!/older code/.test(e.message || '')) reportClientError('driftprecon.' + what, e.message, e.stack);
      toast(e.message, 'err', 10000);
    } finally {
      ps.acting = false;
    }
    await refresh();
  }
  const workOut = () => act('/api/arc/precon/plan', {}, 'plan');
  const runIt = () => {
    const P = (ps.status || {}).plan || {};
    return act('/api/arc/precon/run', { plan_at: P.at }, 'run',
               'The analysis is running. Each artifact is in Results as it is filed.');
  };
  const stopSoft = () => act('/api/arc/precon/stop', {}, 'stop',
                             'It stops after the item in flight is filed.');
  const stopHard = () => act('/api/arc/precon/stop', { hard: true }, 'stop.hard');
  const report = () => act('/api/arc/precon/report', {}, 'report');
  const carryOn = () => act('/api/arc/precon/resume', {}, 'resume',
                            'Carrying on. Nothing already filed is done again.');
  const forget = () => act('/api/arc/precon/forget', {}, 'forget',
                           'It will not carry on, now or when Jarvis next starts.');

  /* ------------------------------------------------------------------
     What comes next
     ------------------------------------------------------------------ */
  function phaseOf(S) {
    const b = S.busy;
    if (b) return { plan: 'planning', run: 'running', report: 'reporting' }[b.what] || 'running';
    const R = S.resume || {};
    if (R.pending) return 'resuming';
    if (R.interrupted) return 'interrupted';
    const P = S.plan;
    if (P && P.fresh && P.dry_run) {
      const left = ((P.cost || {}).total_s || 0) >= 1;
      if (left || !filedDrifts(S).length) return 'planned';
    }
    if (filedDrifts(S).length) return 'ran';
    return 'unplanned';
  }
  const filedDrifts = (S) => ((S.runlog || {}).drifts || []).filter((d) => d.artifact_id);

  /* ------------------------------------------------------------------
     Painting
     ------------------------------------------------------------------ */
  function paint(host) {
    if (!host) return;
    ps.host = host;
    ps.key = null;
    draw();
    refresh();
  }

  function draw() {
    const host = ps.host;
    if (!host || !host.isConnected) return;
    const S = ps.status;
    // Redraw only when something changed: every two seconds would throw
    // away a scrolled log and a half-read table for nothing.
    const key = JSON.stringify([S && Object.assign({}, S, {
      busy: S.busy && Object.assign({}, S.busy, { elapsed_s: null }),
      plan: S.plan && Object.assign({}, S.plan, { age_s: null }) }),
      ps.err, ps.acting]);
    if (key === ps.key) { tickClock(); return; }
    ps.key = key;
    const logBox = host.querySelector('.dpc-log');
    if (logBox) ps.logAtBottom = logBox.scrollHeight - logBox.scrollTop - logBox.clientHeight < 24;
    host.innerHTML = '';
    if (ps.err) {
      host.appendChild(el('div', { class: 'card dpc-card' }, [
        el('div', { class: 'empty-state dpc-empty' }, [
          el('strong', { text: 'Could not read where the analysis is' }),
          el('p', { text: /older code/.test(ps.err)
            ? 'This Jarvis is running code from before this tab existed. Restart Jarvis, then open Drift again.'
            : ps.err + ' — check that Jarvis is running, then try again.' }),
          el('div', { class: 'head-actions' }, [
            el('button', { class: 'btn', text: 'Try again', onclick: () => refresh() })]),
        ]),
      ]));
      return;
    }
    if (!S) {
      host.appendChild(el('div', { class: 'card dpc-card' }, [
        loader('Reading where the analysis is', 'its plan, its run log and its report')]));
      return;
    }
    const phase = phaseOf(S);
    host.appendChild(aboutCard(S));
    host.appendChild(costCard(S, phase));
    const run = runCard(S);
    if (run) host.appendChild(run);
    const filed = filedCard(S, phase);
    if (filed) host.appendChild(filed);
    const box = host.querySelector('.dpc-log');
    if (box) {
      if (ps.logAtBottom) box.scrollTop = box.scrollHeight;
      box.addEventListener('scroll', () => {
        ps.logAtBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 24;
      });
    }
  }

  function tickClock() {
    const S = ps.status;
    const node = ps.host && ps.host.querySelector('[data-elapsed]');
    if (!node || !S || !S.busy) return;
    node.textContent = sayS(since(S.busy.started)) + ' so far';
  }

  /* A <details> that stays as the person left it across redraws. */
  function fold(key, summary, body, extra) {
    const d = el('details', { class: 'dpc-fold' + (extra ? ' ' + extra : ''),
                              open: ps.open[key] ? 'open' : null, 'data-fold': key }, [
      el('summary', { text: summary }), body]);
    d.addEventListener('toggle', () => { ps.open[key] = d.open; });
    return d;
  }

  /* ---- what it is ---- */
  function aboutCard(S) {
    const P = S.plan || {};
    const rats = (P.rats || [3, 4, 6, 7, 8, 9, 10, 11]).map((r) => 'r' + r).join(', ');
    const out = Object.entries(P.excluded || { r5: 'no Precon4 recording, and no histology row' })
      .map(([r, why]) => r + ' — ' + why).join('; ');
    const bands = (P.bands || [{ id: 'theta' }, { id: 'beta' }, { id: 'gamma_low' }])
      .map((b) => BAND_SAY[b.id] || b.say || b.id).join(' · ');
    const card = el('div', { class: 'card dpc-card dpc-about' }, [
      el('div', { class: 'dpc-head' }, [el('strong', { text: 'What changes from Precon1 to Precon4' })]),
      el('p', { class: 'dpc-q', text: 'How does coupling between regions change across '
        + 'preconditioning? Each rat is compared with itself, Precon4 minus Precon1, and the '
        + 'changes are pooled over rats (DerSimonian–Laird, Hartung–Knapp t on k−1 df, '
        + 'Benjamini–Hochberg per band across windows and methods).' }),
      el('table', { class: 'art-params dpc-facts' }, [el('tbody', {}, [
        row('Rats', rats + ' — each on both days, the SPC run'),
        row('Left out', out),
        row('Bands', bands + '; coherence averaged across the band'),
        row('Cue pairs', 'both, kept apart by role: the pair whose second cue is later '
            + 'followed by food in conditioning, and the other; read from each rat’s own '
            + 'Con TTLs'),
        row('Windows', 'state (baseline, cue 1, cue 2, after) and transition (onset, '
            + 'switch, offset; −1 s / +2 s), plus rest from FP1 and FP2'),
        row('Controls', 'cue − baseline, food pair − other pair, and the rest change'),
        row('Makes', (P.n_circuit_artifacts || 240) + ' circuits and '
            + ((P.drifts || []).length || 33) + ' drifts, each in Results the moment it is '
            + 'filed; then a write-up, a CSV of every drift cell, and figures'),
      ])]),
    ]);
    if ((P.roles || []).length) {
      card.appendChild(fold('roles', 'Which pair is the food pair, rat by rat',
        el('table', { class: 'art-params dpc-roles' }, [el('tbody', {}, [
          el('tr', {}, ['rat', 'food cue', 'food pair', 'other pair', 'followed by food in Con']
            .map((h) => el('th', { text: h }))),
        ].concat(P.roles.map((r) => el('tr', {}, [
          el('td', { text: 'r' + r.rat }), el('td', { text: r.food_cue }),
          el('td', { text: r.food_pair }), el('td', { text: (r.no_food_pairs || []).join(', ') }),
          el('td', { text: Object.keys(r.presented || {}).map((c) =>
            c + ' ' + ((r.followed || {})[c] || 0) + '/' + r.presented[c]).join(', ') }),
        ]))))])));
    }
    return card;
  }
  function row(k, v) {
    return el('tr', {}, [el('th', { text: k }), el('td', { text: v })]);
  }

  /* ---- the cost ---- */
  function costCard(S, phase) {
    const P = S.plan;
    const card = el('div', { class: 'card dpc-card dpc-cost' }, [
      el('div', { class: 'dpc-head' }, [el('strong', { text: 'The cost' }),
        P && P.at ? el('span', { class: 'hint', text: (P.dry_run ? 'worked out ' : 'the run’s own plan, ')
          + clock(P.at) + ' · ' + plural(P.requests || 0, 'request') + ' to Jarvis, reading only' }) : null]),
    ]);
    const lastPlan = (S.last || {}).plan;
    if (phase === 'planning' || (ps.acting && !S.busy && phase === 'unplanned')) {
      card.appendChild(loader('Working out the cost',
        'asking Jarvis for each of the 16 recordings’ plans — about ten seconds, and nothing is written'));
      return card;
    }
    if (!P) {
      card.appendChild(el('div', { class: 'empty-state dpc-empty' }, [
        el('strong', { text: 'Work out the cost first' }),
        el('p', { text: 'It asks Jarvis what each of the 16 recordings needs — about ten seconds, '
          + 'reading only — and says how long the whole analysis will take before anything runs.' }),
      ]));
    } else {
      if ((!P.fresh || !P.dry_run) && ['running', 'interrupted', 'resuming'].indexOf(phase) < 0) {
        card.appendChild(el('p', { class: 'dpc-warn', text: !P.dry_run
          ? 'This is the plan the last run wrote as it started. Work out the cost again to see what is left.'
          : ((P.server || {}).started_at !== S.server_started
            ? 'This was worked out by a Jarvis that has since restarted. Work it out again before running.'
            : 'This was worked out ' + sayS(P.age_s) + ' ago. Work it out again before running.') }));
      }
      card.appendChild(el('ul', { class: 'dpc-lines' }, ((P.cost || {}).lines || []).map((ln) =>
        el('li', { class: /^\s/.test(ln) ? 'sub' : null, text: ln.trim() }))));
      card.appendChild(itemsFold(P));
    }
    if (lastPlan && lastPlan.exit_code && lastPlan.exit_code !== 0 && S.log && S.log.what === 'plan') {
      card.appendChild(el('p', { class: 'dpc-warn', text: 'The last attempt to work out the cost was refused. What it said:' }));
      card.appendChild(el('pre', { class: 'dop-log dpc-plog', text: (S.log.lines || []).join('\n') }));
    }
    if ((S.code_changed || []).length) {
      card.appendChild(el('p', { class: 'dpc-warn', text: 'Restart Jarvis before running: it is running '
        + 'older code for ' + S.code_changed.join(', ') + ', and the run would use it.' }));
    }
    if (phase === 'unplanned' || phase === 'planned') card.appendChild(actions(S, phase));
    return card;
  }

  function itemsFold(P) {
    const circ = P.circuits || [];
    const body = el('div', { class: 'dpc-items' }, [
      el('div', { class: 'section-label', text: 'Spark · ' + plural((P.spark || []).length, 'recording') }),
      el('table', { class: 'art-params dpc-t' }, [el('tbody', {}, [
        el('tr', {}, ['rat', 'day', 'recording', 'state', 'note'].map((h) => el('th', { text: h }))),
      ].concat((P.spark || []).map((r) => el('tr', {}, [
        el('td', { text: 'r' + r.rat }), el('td', { text: r.day }), el('td', { text: r.gid }),
        el('td', { text: { todo: 'to check and re-bank', done: 'already measured', blocked: 'blocked' }[r.state] || r.state }),
        el('td', { text: r.why || (r.hand ? plural(r.hand, 'hand decision') + ' to carry' : '') }),
      ]))))]),
      el('div', { class: 'section-label', text: 'Circuits · ' + plural(circ.length, 'run') + ', '
        + plural(circ.length * ((P.bands || []).length || 3), 'artifact') }),
      el('table', { class: 'art-params dpc-t' }, [el('tbody', {}, [
        el('tr', {}, ['rat', 'day', 'kind', 'cue pair', 'role', 'to compute', 'time', 'how known']
          .map((h) => el('th', { text: h }))),
      ].concat(circ.map((c) => el('tr', {}, [
        el('td', { text: 'r' + c.rat }), el('td', { text: c.day }),
        el('td', { text: KIND_SAY[c.kind] || c.kind }),
        el('td', { text: c.kind === 'rest' ? '—' : c.cue_type }),
        el('td', { text: c.cue_role === 'food' ? 'food pair' : c.cue_role === 'no_food' ? 'other pair' : '—' }),
        el('td', { class: 'num', text: plural(c.units_todo || 0, c.kind === 'rest' ? 'epoch' : 'cue pair') }),
        el('td', { class: 'num', text: c.seconds ? sayS(c.seconds) : 'current' }),
        el('td', { text: c.plan }),
      ]))))]),
      el('div', { class: 'section-label', text: 'Drifts · ' + (P.drifts || []).length }),
      el('ul', { class: 'dpc-dlist' }, (P.drifts || []).map((d) => el('li', { text: d.nickname }))),
    ]);
    return fold('items', 'Item by item', body);
  }

  /* ---- the run ---- */
  function runCard(S) {
    const G = S.progress;
    const b = S.busy && S.busy.what === 'run' ? S.busy : null;
    const L = (S.last || {}).run;
    if (!G && !b && !L) return null;
    const P = S.plan || {};
    const stages = (G && G.stages) || {};
    const RS = S.resume || {};
    const cut = !b && (RS.interrupted || RS.pending);
    const title = b ? (b.stopping ? 'Stopping after this item' : 'Running')
      : cut ? (RS.pending ? 'Carrying on after an interruption' : 'Interrupted')
      : endedSay(L, G);
    const head = el('div', { class: 'dpc-head' }, [
      el('strong', { text: title }),
      el('span', { class: 'hint', text: b
        ? 'started ' + clock(b.started) + (b.orphan ? ' by a Jarvis since restarted' : '') + ' · '
        : (L && L.started ? clock(L.started) + (L.ended ? '–' + clock(L.ended) : '') : '') }),
      b ? el('span', { class: 'hint', 'data-elapsed': '1', text: sayS(since(b.started)) + ' so far' }) : null,
      el('div', { class: 'spacer' }),
      b && !b.stopping ? el('button', { class: 'btn ghost sm', text: 'Stop after this item',
        disabled: ps.acting ? 'disabled' : null, onclick: stopSoft,
        title: 'The item in flight finishes and is filed; running again picks up from the next.' }) : null,
      b && b.stopping ? el('button', { class: 'btn ghost sm danger', text: 'Stop now',
        disabled: ps.acting ? 'disabled' : null, onclick: stopHard,
        title: 'Ends it at once. A circuit it was waiting on still finishes in Jarvis and is filed.' }) : null,
    ]);
    const rows = STAGES.filter(([id]) => stages[id] || (P.stages || []).indexOf(id) >= 0)
      .map(([id, words, unit]) => {
        const s = stages[id];
        const n = s ? (s.done || 0) + (s.already || 0) + (s.failed || 0) : 0;
        const st = !s ? 'waiting' : (s.ended ? ((s.failed ? 'bad ' : '') + 'done') : (b ? 'on' : 'bad'));
        const secs = s && s.started ? ((s.ended ? Date.parse(s.ended) : (b ? Date.now() : Date.parse(s.started))) - Date.parse(s.started)) / 1000 : null;
        const bits = [];
        if (s && s.already) bits.push(s.already + ' already current');
        if (s && s.failed) bits.push(s.failed + ' did not complete');
        return el('div', { class: 'comod-stage dpc-stage ' + st, 'data-stage': id }, [
          el('span', { class: 'comod-tick', text: !s ? '·' : s.ended ? (s.failed ? '!' : '✓') : '›' }),
          el('span', {}, [words, bits.length ? el('span', { class: 'hint', text: ' — ' + bits.join(', ') }) : null]),
          el('span', { class: 'comod-stage-count', text: s ? n + ' of ' + s.of + ' ' + unit : '' }),
          el('div', { class: 'comod-mini' }, [el('div', { class: 'comod-mini-fill',
            style: 'width:' + (s && s.of ? Math.round(100 * Math.min(1, n / s.of)) : 0) + '%' })]),
          el('span', { class: 'comod-stage-time', text: secs != null && s ? sayS(secs) : '' }),
        ]);
      });
    const frac = overall(stages, P);
    const left = ((P.cost || {}).total_s || 0) * (1 - frac);
    const card = el('div', { class: 'card comod-run dpc-card dpc-run' }, [
      head,
      el('div', { class: 'comod-stages' }, rows),
      b && G && G.item ? el('p', { class: 'dpc-now', text: 'Now: ' + G.item.tag }) : null,
      el('div', { class: 'comod-total' }, [
        el('div', { class: 'comod-bar' }, [el('div', { class: 'comod-bar-fill',
          style: 'width:' + Math.round(100 * frac) + '%' })]),
        el('span', { class: 'comod-eta', text: b ? 'about ' + sayS(left) + ' left, by the plan'
          : Math.round(100 * frac) + '%' }),
      ]),
    ]);
    if (cut) card.insertBefore(interruptedBlock(S, left), card.children[1]);
    else if (!b && G && G.crashed) {
      card.insertBefore(el('p', { class: 'dpc-warn dpc-crashed', text: 'It stopped on an error it did '
        + 'not expect: ' + G.crashed.error + (G.crashed.item ? ' (at ' + G.crashed.item.tag + ')' : '')
        + '. What it said is below. Everything filed before it is kept; work out the cost to carry on.' }),
        card.children[1]);
    }
    else if (b && RS.resumes) {
      card.insertBefore(el('p', { class: 'hint dpc-carried', text: 'Carried on after '
        + plural(RS.resumes, 'interruption') + ' — first started ' + clock(RS.chain_started)
        + '. Nothing already filed was done again.' }), card.children[1]);
    }
    const fails = (G && G.failures) || [];
    if (!b && fails.length) {
      card.appendChild(fold('failures', plural(fails.length, 'item') + ' did not complete',
        el('ul', { class: 'dpc-fails' }, fails.slice(0, 60).map((f) =>
          el('li', { text: (f[0] || '') + ': ' + (f[1] || '') })))));
    }
    if (S.log && S.log.what === 'run' && (S.log.lines || []).length) {
      card.appendChild(fold('log', 'What it is saying', el('pre', { class: 'dop-log dpc-log',
        text: S.log.lines.join('\n') })));
    }
    return card;
  }

  /* What an interruption says, and what can be done about it. A carry-on
     is the same run: the cost is the one already agreed to, less what is
     filed -- so it is quoted from the run's own plan, not asked for again. */
  function interruptedBlock(S, left) {
    const RS = S.resume || {};
    const G = S.progress || {};
    const why = (G.interrupted || {}).why
      || 'Jarvis or this computer stopped while it ran, and nobody saw it end.';
    const where = (G.interrupted || {}).item || G.item;
    const box = el('div', { class: 'dpc-cut' }, [
      el('p', { class: 'dpc-cut-why', text: why }),
      where ? el('p', { class: 'hint', text: 'It had reached ' + where.tag
        + '. That item is done again, from its cache; everything filed before it is kept.' }) : null,
    ]);
    if (RS.pending) {
      box.appendChild(loader('Carrying on', 'waiting for the run left over from the Jarvis before '
        + 'to end, then starting it again'));
      return box;
    }
    box.appendChild(el('p', { class: RS.gave_up ? 'dpc-warn' : 'hint', text: RS.gave_up
      ? 'It stopped carrying on by itself: the last ' + RS.gave_up.stalls + ' tries filed '
        + 'nothing. Read what it said below, then carry it on by hand.'
      : 'It carries on by itself the next time Jarvis starts. Or carry it on now.' }));
    const stale = (S.code_changed || []).length > 0;
    box.appendChild(el('div', { class: 'head-actions dpc-actions' }, [
      stale ? el('span', { class: 'dpc-warn', text: 'Restart Jarvis first: it is running older code for '
        + S.code_changed.join(', ') + '. It carries on by itself as it starts.' }) : null,
      el('div', { class: 'spacer' }),
      el('button', { class: 'btn ghost', text: 'Don’t carry it on', 'data-go': 'forget',
        disabled: ps.acting ? 'disabled' : null, onclick: forget,
        title: 'Leaves what is filed as it is. It will not start again by itself.' }),
      el('button', { class: 'btn dpc-go', 'data-go': 'resume',
        disabled: (ps.acting || stale) ? 'disabled' : null, onclick: carryOn,
        text: 'Carry on now · about ' + sayS(left) + ' left' }),
    ]));
    return box;
  }

  function endedSay(L, G) {
    if (!L) return 'The last run';
    if (L.exit_code === 4) return 'Interrupted';
    if (L.lost) return 'Cut off — Jarvis stopped while it ran';
    if (L.killed) return 'Stopped at once';
    if (L.exit_code === 3 || (G && G.stopped)) return 'Stopped, as asked';
    if (L.exit_code === 0) return 'Finished';
    if (L.exit_code === 1) return 'Finished, with items that did not complete';
    if (L.exit_code === 2) return 'Refused before anything ran';
    if (L.exit_code === 5 || (G && G.crashed)) return 'Stopped by an error';
    return 'Ended (exit ' + L.exit_code + ')';
  }

  /* The share of the plan's time done: a stage counts in proportion to
     its items and weighs what the plan said it would take. */
  function overall(stages, P) {
    const c = P.cost || {};
    const w = { spark: c.spark_s || 0, circuits: c.circuit_s || 0, drifts: c.drift_s || 0 };
    let tot = 0, got = 0;
    for (const [id] of STAGES) {
      if ((P.stages || []).indexOf(id) < 0 && !stages[id]) continue;
      const W = Math.max(w[id], 1);
      tot += W;
      const s = stages[id];
      if (s && s.of) got += W * Math.min(1, ((s.done || 0) + (s.already || 0) + (s.failed || 0)) / s.of);
      else if (s && s.ended) got += W;
    }
    return tot ? got / tot : 0;
  }

  /* ---- what it filed, and the report ---- */
  function filedCard(S, phase) {
    const R = S.runlog;
    const rep = S.report || {};
    if (!R && !rep.page && phase !== 'reporting') return null;
    // In the plan's order: the run log is saved with sorted keys.
    const order = ((S.plan || {}).drifts || []).map((d) => d.key);
    const rank = (d) => { const i = order.indexOf(d.key); return i < 0 ? order.length : i; };
    const bandRank = (b) => { const i = BAND_ORDER.indexOf(b); return i < 0 ? BAND_ORDER.length : i; };
    const drifts = filedDrifts(S).slice().sort((a, b) => bandRank(a.band) - bandRank(b.band)
      || rank(a) - rank(b) || String(a.key).localeCompare(String(b.key)));
    const card = el('div', { class: 'card dpc-card dpc-filed' }, [
      el('div', { class: 'dpc-head' }, [el('strong', { text: 'What it has filed' }),
        R ? el('span', { class: 'hint', text: plural(R.circuits || 0, 'circuit') + ' · '
          + plural(drifts.length, 'drift') + (R.updated ? ' · last ' + clock(R.updated) : '') }) : null]),
    ]);
    if (drifts.length) {
      const bands = [];
      for (const d of drifts) if (bands.indexOf(d.band) < 0) bands.push(d.band);   // already in band order
      card.appendChild(el('div', { class: 'dpc-bands' }, bands.map((band) => el('div', { class: 'dpc-band' }, [
        el('div', { class: 'section-label', text: BAND_SAY[band] || band }),
        el('ul', { class: 'dpc-drifts' }, drifts.filter((d) => d.band === band).map((d) => el('li', {}, [
          el('a', { href: '#', class: 'art-link dpc-show', 'data-ref': d.artifact_id,
                    'data-vid': d.version_id || '',
                    title: (d.nickname || d.key) + ' · v' + d.version + ' — show it below',
                    text: shortNick(d) + ' · v' + d.version,
                    onclick: (e) => { e.preventDefault(); show(d); } }),
          el('button', { class: 'mini', text: 'Results', title: 'Open exactly this version in Results',
                         onclick: () => { if (BARRY.artifacts && BARRY.artifacts.open) BARRY.artifacts.open(d.artifact_id, d.version_id || d.version); } }),
        ]))),
      ]))));
    } else if (R) {
      card.appendChild(el('p', { class: 'hint', text: 'No drift yet: they come last, once every circuit is filed.' }));
    }
    // The report.
    const L = (S.last || {}).report;
    if (phase === 'reporting') {
      card.appendChild(loader('Writing the report', 'the write-up, a CSV of every drift cell, and a figure per drift'));
    } else if (rep.page || rep.csv) {
      card.appendChild(el('div', { class: 'section-label', text: 'The report · written ' + clock((rep.page || rep.csv).at) }));
      card.appendChild(el('div', { class: 'dpc-files' }, [
        rep.page ? el('a', { class: 'btn ghost sm', href: '/api/arc/precon/file/page', target: '_blank',
                             rel: 'noopener', text: 'Open the circuits page' }) : null,
        rep.csv ? el('a', { class: 'btn ghost sm', href: '/api/arc/precon/file/csv',
                            text: 'Download the CSV (' + Math.max(1, Math.round(rep.csv.bytes / 1024)) + ' KB)' }) : null,
        el('span', { class: 'hint', text: 'docs/' + (rep.page || rep.csv).name.replace(/\.(html|csv)$/, '') + '.html and .csv' }),
      ]));
      if ((rep.figures || []).length) {
        const stamp = encodeURIComponent((rep.page || rep.csv).at || '');
        card.appendChild(fold('figs', plural(rep.figures.length, 'figure'), el('div', { class: 'dpc-figs' },
          rep.figures.map((f) => el('a', { href: '/api/arc/precon/file/figure/' + encodeURIComponent(f),
            target: '_blank', rel: 'noopener', class: 'dpc-fig', title: f }, [
            el('img', { src: '/api/arc/precon/file/figure/' + encodeURIComponent(f) + '?t=' + stamp,
                        alt: f, loading: 'lazy' }),
            el('span', { text: f.replace(/\.(png|svg)$/i, '') }),
          ])))));
      }
    }
    if (L && L.exit_code && S.log && S.log.what === 'report') {
      card.appendChild(el('p', { class: 'dpc-warn', text: 'The report was refused. What it said:' }));
      card.appendChild(el('pre', { class: 'dop-log', text: (S.log.lines || []).join('\n') }));
    }
    if (phase === 'ran') card.appendChild(actions(S, phase));
    return card;
  }

  /* Under its band's heading a nickname need not say the band again:
     "Precon1→4 · theta · state · food pair" reads "state · food pair". */
  function shortNick(d) {
    const nick = d.nickname || d.key || '';
    const cut = nick.split(' · ');
    return cut.length > 2 && /^Precon1/.test(cut[0]) ? cut.slice(2).join(' · ') : nick;
  }

  async function show(d) {
    try {
      const got = await BARRY.artifacts.payload(d.artifact_id, d.version_id || d.version);
      if (!got.payload) throw new Error('it has no payload');
      if (BARRY.drift && BARRY.drift.show) {
        BARRY.drift.show(got.payload, { artifact_id: d.artifact_id, version: got.version,
          version_id: got.version_id, digest: got.digest, nickname: d.nickname });
        const at = document.getElementById('drShown');
        if (at && at.scrollIntoView) at.scrollIntoView({ block: 'start' });
      }
    } catch (e) {
      reportClientError('driftprecon.show', e.message, e.stack);
      toast('Could not open ' + (d.nickname || d.artifact_id) + ': ' + e.message, 'err', 9000);
    }
  }

  /* ---- the one primary: whichever step comes next ---- */
  function actions(S, phase) {
    const P = S.plan || {};
    const R = S.runlog || {};
    const stale = (S.code_changed || []).length > 0;
    const off = ps.acting || !!S.busy;
    const bits = [];
    let hint = '';
    if (phase === 'unplanned') {
      hint = R.circuits ? 'Some is already filed; the cost says what is left.' : '';
      bits.push(el('button', { class: 'btn dpc-go', 'data-go': 'plan', text: 'Work out the cost',
                               disabled: off ? 'disabled' : null, onclick: workOut }));
    } else if (phase === 'planned') {
      const total = (P.cost || {}).total_s;
      const carry = (R.circuits || 0) > 0 || filedDrifts(S).length > 0;
      hint = 'Runs here, one item after another, driving this Jarvis. Stage 1 re-files each '
        + 'recording\u2019s cue pairs with its transition windows measured (the same pairs, so the '
        + 'same bank version) and checks the bank kept it. Stop whenever you like: it stops between items, and running again carries on. '
        + 'If Jarvis or this computer stops, it carries on by itself the next time Jarvis '
        + 'starts; a refresh changes nothing.';
      bits.push(el('button', { class: 'btn ghost', text: 'Work out again',
                               disabled: off ? 'disabled' : null, onclick: workOut }));
      bits.push(el('button', { class: 'btn dpc-go', 'data-go': 'run',
        disabled: (off || stale || !P.fresh) ? 'disabled' : null,
        title: stale ? 'Restart Jarvis first: it is running older code.' : null,
        text: (carry ? 'Carry on' : 'Run the analysis') + ' · about ' + sayS(total), onclick: runIt }));
    } else if (phase === 'ran') {
      const rep = S.report || {};
      // The run log is the record, whichever way the run was started.
      const incomplete = (R.failures || []).length > 0 || !!R.stopped || !R.finished;
      hint = incomplete ? 'Some did not complete. Work out the cost to carry on, or write the report from what is filed.'
                        : 'Everything is filed.';
      bits.push(el('button', { class: 'btn ghost', text: 'Work out the cost',
                               disabled: off ? 'disabled' : null, onclick: workOut }));
      bits.push(el('button', { class: 'btn dpc-go', 'data-go': 'report',
        text: rep.page ? 'Write the report again' : 'Write the report',
        disabled: off ? 'disabled' : null, onclick: report }));
    }
    return el('div', { class: 'head-actions dpc-actions' }, [
      hint ? el('span', { class: 'hint', text: hint }) : null,
      el('div', { class: 'spacer' }),
    ].concat(bits));
  }

  /* A page loaded (or refreshed) while the analysis runs, or while it waits
     to carry on, says so once -- wherever the person lands. One local
     request per load. */
  let told = false;
  async function notice() {
    if (told) return;
    told = true;
    try {
      const S = await api('/api/arc/precon/status');
      const G = S.progress || {};
      const st = (G.stages || {})[G.stage] || null;
      const where = st ? ' — ' + G.stage + ' ' + ((st.done || 0) + (st.already || 0)
        + (st.failed || 0)) + ' of ' + st.of : '';
      if (S.busy && S.busy.what === 'run') {
        toast('The Precon1 → Precon4 analysis is running' + where
              + '. ToolKit → Drift shows where it is.', 'ok', 9000);
      } else if ((S.resume || {}).pending) {
        toast('The Precon1 → Precon4 analysis was interrupted and is carrying on by itself.', 'ok', 9000);
      } else if ((S.resume || {}).interrupted) {
        toast('The Precon1 → Precon4 analysis was interrupted' + where
              + '. ToolKit → Drift carries it on.', 'warn', 12000);
      }
    } catch (e) { /* an older Jarvis, or none: nothing to say */ }
  }
  // Not inside a frame: the harness pages load the app in one, against the
  // same GUI_logs, and a toast about the real run would land in their checks.
  if (window.top === window) setTimeout(notice, 2500);

  return {
    paint,
    refresh,
    _notice: () => { told = false; return notice(); },
    get state() { return { status: ps.status, err: ps.err, polling: !!ps.timer, phase: ps.status ? phaseOf(ps.status) : null }; },
    _phaseOf: phaseOf,
    _overall: overall,
  };
})();
