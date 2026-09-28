/* ==========================================================================
   circuit.js -- Circuit, step three of The Arc.

   A circuit is ONE recording x ONE cue type x ONE analysis kind (state or
   transition): every cue pair of that type run through Coupling, and each
   region pair's values kept side by side with their n, mean and SD. It is
   filed as an artifact (backend/artifacts.py), which is what Drift reads.
   Nothing in here tests anything: a circuit is means with n, and the
   statistics live in Drift (arc_contracts.md section 0).

   What this file owns

     the panel      pick a banked recording, its ACTUAL cue pairing (the rats
                    are counterbalanced, so the pairings are the recording's
                    own and are never assumed), state or transition, then the
                    plan -- parameters, probe sanity, pairs, cost, where it
                    runs -- then the run, then the circuit.
     the batch      many recordings x cue types, planned before it is spent,
                    rows landing one by one, each viewable before the rest.
     the renderer   `renderCircuit(host, payload, meta)`: the matrix and the
                    ring. ONE function, used by the panel AND by Results'
                    artifact viewer (registered at the bottom), so a circuit
                    is drawn one way wherever it is looked at (section 6c).

   The matrix is Coupling's (`BARRY.arc.shared`: the crosshair, the colour
   ramps, the abbreviations), so the two read as one family. The ring is
   the cluster's network figure (`15 Connectivity Matrix/network_lib.py`):
   twelve nodes at 30 degree steps starting 15 degrees right of top, right
   hemisphere down the right side, left mirrored -- drawn as inline SVG so it
   scales, stays crisp and can be downloaded.

   Colours of the regions are an atlas, not a theme: they come from
   `/api/probes` (`probes.DEWEY_REGION_COLORS`), the one place they are
   written down. Everything else is a theme token.
   ========================================================================== */
'use strict';

BARRY.circuit = (function () {
  /* ------------------------------------------------------------------
     Words
     ------------------------------------------------------------------ */
  // arc_contracts.md section 1. Spelled out here because the payload
  // carries window KEYS and a person reads words.
  const WINDOW_SAY = {
    pre: 'baseline', cue1: 'cue 1', cue2: 'cue 2', post: 'after cue 2',
    onset: 'cue 1 onset', switch: 'cue 1 \u2192 cue 2', offset: 'cue 2 offset',
  };
  const METHODS = [
    ['coherence', 'Coherence', 'magnitude-squared, read at the summary frequency'],
    ['raw_cc', 'Raw cross-correlation', 'peak r within the lag window'],
    ['amp_cc', 'Amplitude cross-correlation',
     'theta envelope, peak r within the lag window'],
  ];
  const METHOD_NAME = {};
  METHODS.forEach(([id, name]) => { METHOD_NAME[id] = name; });
  const KIND_SAY = { state: 'State', transition: 'Transition' };
  const VERDICT_WORD = {
    intended: 'in target', uncertain: 'maybe', relocated: 'elsewhere',
    missed: 'missed', unscored: 'not scored',
  };

  const say = (w) => WINDOW_SAY[w] || w;
  const plural = (n, one, many) => n + ' ' + (n === 1 ? one : (many || one + 's'));
  const fmt = (v, d) => (v == null || !isFinite(v)) ? '\u2014'
    : Number(v).toFixed(d == null ? 3 : d);
  /* Two decimals without the leading zero, as Coupling's cells do. */
  const short = (v) => Number(v).toFixed(2).replace(/^(-?)0\./, '$1.');
  const secs = (s) => {
    const n = Math.max(1, Math.round(Number(s) || 0));
    return n < 90 ? n + ' s' : Math.round(n / 60) + ' min';
  };
  const log = (what, data) => {
    try { if (BARRY.activity) BARRY.activity.log(what, data); } catch (e) { /* no-op */ }
  };
  const inToolkit = () => !!(BARRY.views && BARRY.views.toolkit
    && typeof BARRY.views.toolkit.tool === 'function'
    && BARRY.views.toolkit.tool() === 'circuit');

  /* Coupling's matrix pieces, read at call time: arc.js loads first, and a
     page that has no arc.js (a pop-out) still gets a working fallback that
     is the same arithmetic. */
  function shared() {
    return (BARRY.arc && BARRY.arc.shared) || null;
  }
  function withAlpha(colour, a) {
    const s = shared();
    if (s && s.withAlpha) return s.withAlpha(colour, a);
    const m = /^#([0-9a-f]{6})$/i.exec(String(colour || '').trim());
    if (!m) return colour;
    const n = parseInt(m[1], 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ','
           + (n & 255) + ',' + a.toFixed(3) + ')';
  }
  function cellColour(v, diverging) {
    const s = shared();
    if (s && s.cellColour) return s.cellColour(v, diverging);
    if (diverging) {
      const t = Math.max(-1, Math.min(1, v));
      return withAlpha(BARRY.token(t >= 0 ? '--err' : '--accent'),
                       Math.min(0.85, Math.abs(t)));
    }
    return withAlpha(BARRY.token('--ok'), Math.min(0.85, Math.max(0, v)));
  }
  /* The ramp's hue for an edge; its strength goes into the opacity, the
     same two tokens the matrix cells use. */
  function edgeHue(v, diverging) {
    if (!diverging) return BARRY.token('--ok');
    return BARRY.token(v >= 0 ? '--err' : '--accent');
  }
  function shortRegion(name) {
    const s = shared();
    if (s && s.shortRegion) return s.shortRegion(name);
    const bits = String(name).split(' ');
    return (bits[0] || '').charAt(0) + (bits[1] || name);
  }

  /* ------------------------------------------------------------------
     The regions' own colours and full names, from the one place they are
     written down (probes.DEWEY_REGIONS / DEWEY_REGION_COLORS via
     /api/probes). Asked once per page; every ring drawn before it lands is
     redrawn when it does.
     ------------------------------------------------------------------ */
  let regionMeta = null;       // { "Left POR": {color, name, abbr, hemisphere} }
  let regionErr = null;
  let regionAsk = null;
  const live = [];             // rendered circuit contexts, for repaints

  function loadRegions() {
    if (regionMeta || regionAsk) return regionAsk;
    regionAsk = api('/api/probes').then((d) => {
      const p = (d.probes || []).find((x) => x.id === 'dewey32');
      const out = {};
      for (const r of ((p && p.regions) || [])) {
        out[r.region] = { color: r.color, name: r.name, abbr: r.abbr,
                          hemisphere: r.hemisphere };
      }
      regionMeta = out;
      redrawLive();
    }).catch((e) => {
      regionErr = e.message;
      reportClientError('circuit.regions', e.message, e.stack);
      redrawLive();
    });
    return regionAsk;
  }

  function metaOf(region) {
    const m = (regionMeta || {})[region];
    if (m) return m;
    const bits = String(region).split(' ');
    return { color: null, name: null, abbr: bits.slice(1).join(' ') || region,
             hemisphere: bits[0] || '' };
  }

  function redrawLive() {
    for (let i = live.length - 1; i >= 0; i--) {
      const c = live[i];
      if (!c.host.isConnected) { live.splice(i, 1); continue; }
      paintRing(c);
    }
  }

  /* ==================================================================
     The panel's state. Held here rather than on the DOM: the ToolKit
     rebuilds the panel after it is shown (toolkit-renders-twice), and a
     choice kept in a node is a choice lost on the second render.
     ================================================================== */
  const st = {
    mode: 'one',             // 'one' | 'many'
    rows: null, rowsErr: null,
    gid: null, cue: null, kind: 'state',
    plan: null, planKey: null,
    params: null, paramErr: null,
    where: 'local',
    nickname: '',
    open: { params: false, probes: true, pairs: false },
    busy: false,             // the run request is in flight
    job: null, jobGid: null, jobCue: null, jobKind: null, jobStop: null,
    jobOpen: {},             // pair id -> its disclosure is open
    shown: null,             // { payload, meta } -- the circuit on screen
    shownErr: null,
  };

  /* How a circuit is being looked at, shared by every circuit on screen so
     switching recordings does not reset the window somebody was reading.
     Per kind for the window, because the two kinds have different ones. */
  const pref = { win: {}, method: 'coherence', thr: {}, sel: null };

  /* ------------------------------------------------------------------
     Painting
     ------------------------------------------------------------------ */
  function paint(host) {
    host = host || document.getElementById('tkResult');
    if (!host) return;
    loadRegions();
    host.appendChild(modeCard());
    if (st.mode === 'many') {
      host.appendChild(el('div', { class: 'arc-batch-host', id: 'cirBatch' }));
    } else {
      host.appendChild(el('div', { class: 'arc-spark cir-panel' }, [
        el('div', { class: 'arc-pick', id: 'cirPick' }),
        el('div', { class: 'arc-read', id: 'cirMain' }),
      ]));
    }
    if (st.rows === null && !st.rowsErr) {
      const target = document.getElementById(st.mode === 'many' ? 'cirBatch'
                                                                : 'cirPick');
      if (target) BARRY.skeleton.into(target, 'row', 8);
      loadRows().then(render);
      if (st.mode === 'one') renderMain();
      return;
    }
    render();
  }

  function render() {
    renderPick(); renderMain(); renderBatch();
  }

  /* One request at a time: the ToolKit paints this step twice on the way
     in, and two identical reads of the recordings would be the result. */
  let rowsAsk = null;
  function loadRows() {
    if (rowsAsk) return rowsAsk;
    rowsAsk = (async () => {
      try {
        const got = await api('/api/arc/circuit/recordings');
        st.rows = got.rows || [];
        st.rowsErr = null;
        adoptRunning(got.running || []);
      } catch (e) {
        st.rowsErr = e.message;
        if (!/older code/.test(e.message || '')) {
          reportClientError('circuit.recordings', e.message, e.stack);
        }
      } finally {
        rowsAsk = null;
      }
    })();
    return rowsAsk;
  }

  /* A run this page did not start -- the page was reloaded, or another
     window started it -- is picked up from the recordings route's
     `running` list and followed like one it did. */
  function adoptRunning(list) {
    for (const r of list) {
      if (r.batch) {
        if (bulk.job) continue;
        bulk.job = { id: r.job, status: 'running', members: null };
        bulk.where = r.where || bulk.where;
        bulk.kind = r.kind || bulk.kind;
        bulk.stop = follow(r.job, (job) => { bulk.job = job; paintBatchJob(); },
                           (job) => batchLanded(job));
        continue;
      }
      if (st.job) continue;
      st.job = { id: r.job, status: 'running', stages: [], members: null };
      st.jobGid = r.gid; st.jobCue = r.cue_type; st.jobKind = r.kind;
      st.jobOpen = {};
      if (!st.gid) { st.gid = r.gid; st.cue = r.cue_type; st.kind = r.kind || 'state'; }
      st.jobStop = follow(r.job, (job) => { st.job = job; paintRun(); },
                          (job) => landed(job, r.gid, r.cue_type, r.kind, r.where));
    }
  }

  function modeCard() {
    return el('div', { class: 'card arc-mode' }, [
      BARRY.ui.seg([
        ['one', 'One recording at a time'],
        ['many', 'Many recordings at once'],
      ], st.mode, (v) => {
        st.mode = v;
        repaintStep();
      }),
      el('span', { class: 'hint', text: st.mode === 'many'
        ? 'Plans every recording and cue type you tick, says what is already '
          + 'made and what cannot be, then makes the rest one by one. Each '
          + 'lands as a circuit you can open before the batch finishes.'
        : 'Pick a recording, its cue pairing and the kind of analysis, read '
          + 'what will be computed, then make the circuit.' }),
    ]);
  }

  /* Through the Arc, so the step header is drawn by the module that owns
     the steps. */
  function repaintStep() {
    if (BARRY.arc && typeof BARRY.arc.paint === 'function' && inToolkit()) {
      BARRY.arc.paint();
      return;
    }
    const host = document.getElementById('tkResult');
    if (host) { host.innerHTML = ''; paint(host); }
  }

  /* The honest answer when the route is not there yet, or failed. It says
     what the page asked for and what to do, because "nothing here" reads
     as the tool being broken. */
  function routeMissing(message, what) {
    return el('div', { class: 'empty-state cir-missing' }, [
      el('p', { text: what }),
      el('p', { class: 'hint', text: message }),
      el('p', { class: 'hint', text: /older code/.test(message || '')
        ? 'Restart Jarvis once the Circuit routes are in the running code. '
          + 'Circuits that were already made can still be opened in Results '
          + '\u2192 Artifacts.'
        : 'Try again in a moment; if it keeps failing, the Errors view has '
          + 'the detail.' }),
    ]);
  }

  /* ---------------- the recordings ---------------- */

  function pickable(r) {
    return !!(r.banked && (r.reachable || r.vacc));
  }

  function rowWhy(r) {
    if (!r.banked) {
      return 'Spark has not filed this recording\u2019s cue pairs yet, so '
             + 'there is nothing to make a circuit from.';
    }
    if (!r.reachable && !r.vacc) {
      return 'None of this recording\u2019s paths are reachable from this '
             + 'machine, and the cluster does not hold it either.';
    }
    if (!r.reachable) {
      return r.label + ' \u2014 not on a drive this computer can reach, but '
             + 'the cluster holds it, so it can be run on VACC.';
    }
    return r.label;
  }

  function renderPick() {
    const host = document.getElementById('cirPick');
    if (!host) return;
    host.innerHTML = '';
    host.appendChild(el('div', { class: 'section-label',
                                 text: 'Banked recordings' }));
    if (st.rowsErr) {
      host.appendChild(routeMissing(st.rowsErr,
        'The list of recordings a circuit can be made from could not be '
        + 'read.'));
      return;
    }
    if (st.rows === null) { BARRY.skeleton.into(host, 'row', 8); return; }
    if (!st.rows.length) {
      host.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'No DEWEY recording has banked cue pairs yet. File '
                        + 'one in Spark, step 1, and it appears here.' }),
      ]));
      return;
    }
    host.appendChild(el('p', { class: 'hint',
      text: 'A circuit reads the cue pairs Spark filed. A recording that is '
            + 'not filed, or that neither this computer nor the cluster can '
            + 'read, is listed and cannot be picked.' }));
    const list = el('div', { class: 'arc-rows' });
    for (const r of st.rows) {
      const ok = pickable(r);
      const n = (r.circuits || []).length;
      list.appendChild(el('button', {
        class: 'arc-row cir-row' + (st.gid === r.gid ? ' on' : '')
               + (ok ? '' : ' off'),
        disabled: ok ? null : 'disabled',
        'data-gid': r.gid,
        title: rowWhy(r),
        onclick: () => pick(r.gid),
      }, [
        el('strong', { text: 'J' + r.mouse }),
        el('span', { class: 'arc-row-s',
                     text: (r.phase || '') + (r.phase_n || '') }),
        el('span', { class: 'arc-row-d', text: r.date || '' }),
        r.banked
          ? el('span', { class: 'flagchip' + (n ? ' mat' : ''),
                         title: n ? (r.circuits || []).map((c) =>
                           (c.nickname || c.name) + ' (v' + c.version + ')')
                           .join('\n') : 'No circuit made yet',
                         text: n ? plural(n, 'circuit') : r.n_pairs + ' pairs' })
          : el('span', { class: 'arc-row-n', text: 'not filed' }),
      ]));
    }
    host.appendChild(list);
  }

  function rowOf(gid) {
    return (st.rows || []).find((r) => r.gid === gid) || null;
  }

  /* Changing the recording resets everything downstream of it (section
     6e): the cue type, the plan, the circuit on screen. The parameters are
     kept, as Coupling keeps them -- they are a choice about the analysis,
     not about the rat. */
  function pick(gid) {
    const r = rowOf(gid);
    st.gid = gid;
    st.plan = null; st.planKey = null; st.paramErr = null;
    st.shown = null; st.shownErr = null; pref.sel = null;
    const cues = (r && r.cue_types) || [];
    st.cue = cues.length ? cues[0].cue_type : null;
    st.kind = 'state';
    const have = findCircuit(r, st.cue, st.kind);
    st.nickname = (have && have.nickname) || '';
    renderPick(); renderMain();
    loadPlan();
  }

  function findCircuit(r, cue, kind) {
    return ((r && r.circuits) || []).find(
      (c) => c.cue_type === cue && c.kind === kind) || null;
  }

  function choose(cue, kind) {
    if (cue != null) st.cue = cue;
    if (kind != null) st.kind = kind;
    st.plan = null; st.planKey = null; st.paramErr = null;
    const have = findCircuit(rowOf(st.gid), st.cue, st.kind);
    st.nickname = (have && have.nickname) || '';
    renderMain();
    loadPlan();
  }

  async function loadPlan() {
    const r = rowOf(st.gid);
    if (!r || !st.cue) return;
    if (st.kind === 'transition' && !r.transition_measured) return;
    const key = st.gid + '|' + st.cue + '|' + st.kind;
    st.planKey = key;
    const seq = (st.planSeq = (st.planSeq || 0) + 1);
    /* Asked WITH the parameters on screen, so "already computed" and the
       cost describe the run that the button would make, not the defaults.
       A replan whose parameters are refused keeps the plan it had and puts
       the server's sentence where the fields are. */
    const replan = !!(st.plan && !st.plan.error && st.planFor === key);
    let plan;
    try {
      plan = await apiPost('/api/arc/circuit/' + encodeURIComponent(st.gid)
        + '/plan', { cue_type: st.cue, kind: st.kind,
                     params: st.params ? Object.assign({}, st.params) : null });
    } catch (e) {
      plan = { error: e.message };
      if (!/older code|run the transition check|has to be|outside|not a number|not one of/i
            .test(e.message || '')) {
        reportClientError('circuit.plan', e.message, e.stack);
      }
    }
    if (st.planKey !== key || st.planSeq !== seq) return;
    if (plan.error && replan) {
      st.paramErr = plan.error;
      st.open.params = true;
      renderMain();
      return;
    }
    st.plan = plan;
    st.planFor = key;
    if (!plan.error) {
      // One value per field on screen: the defaults, then the recording's
      // own measured lengths, then whatever somebody has already set.
      const def = defaultsOf(plan);
      const now = st.params || {};
      st.params = {};
      for (const s of (plan.params || [])) {
        st.params[s.id] = (s.id in now && !s.fixed) ? now[s.id] : def[s.id];
      }
      st.paramErr = null;
    }
    if (!plan.error && plan.artifact && !st.nickname) {
      st.nickname = plan.artifact.nickname || '';
    }
    renderMain();
  }

  function defaultsOf(plan) {
    const out = {};
    for (const s of ((plan && plan.params) || [])) {
      const d = (plan.defaults || {})[s.id];
      out[s.id] = d !== undefined ? d
        : (s.default !== undefined ? s.default : (plan.run_params || {})[s.id]);
    }
    return out;
  }

  /* A changed field asks for the plan again, after the typing stops. */
  let replanT = null;
  function replanSoon() {
    clearTimeout(replanT);
    replanT = setTimeout(loadPlan, 400);
  }

  /* ---------------- the right-hand side ---------------- */

  function renderMain() {
    const host = document.getElementById('cirMain');
    if (!host) return;
    host.innerHTML = '';
    if (!st.gid) {
      if (st.shown) { host.appendChild(shownCard()); return; }
      host.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'Pick a banked recording on the left to make its '
                        + 'circuit, or to open one already made.' }),
      ]));
      return;
    }
    const r = rowOf(st.gid);
    if (!r) {
      host.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'That recording is not in the list any more. Pick '
                        + 'another.' }),
      ]));
      return;
    }
    host.appendChild(chooseCard(r));
    const running = !!(st.job && st.jobGid === st.gid);
    if (running) {
      host.appendChild(runCard());
    } else {
      host.appendChild(planCard(r));
    }
    if (st.shown || st.shownErr) host.appendChild(shownCard());
    // Coming back to a run: draw what the last poll said, now.
    if (running) paintRun();
  }

  /* What to make: the recording's own pairings, and the kind. */
  function chooseCard(r) {
    const cues = r.cue_types || [];
    const card = el('div', { class: 'card cir-choose' }, [
      el('div', { class: 'section-label', text: r.label || r.gid }),
    ]);
    if (!cues.length) {
      card.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'No banked cue pair of this recording has a cue '
                        + 'pairing Circuit knows. Re-read it in Spark and '
                        + 'check the pulses were paired.' }),
      ]));
      return card;
    }
    card.appendChild(BARRY.ui.field({
      label: 'Cue pairing',
      control: el('div', { class: 'seg cir-cues' }, cues.map((c) => el('button', {
        class: st.cue === c.cue_type ? 'active' : '',
        'data-cue': c.cue_type,
        title: c.n_pairs + ' cue pairs of ' + c.cue_label + ' in this '
               + 'recording',
        onclick: () => { if (st.cue !== c.cue_type) choose(c.cue_type, null); },
      }, [
        el('span', { text: c.cue_label }),
        el('span', { class: 'cir-cue-n', text: '\u00d7' + c.n_pairs }),
      ]))),
      hint: 'This recording\u2019s own pairings. The rats are '
            + 'counterbalanced, so which cue opens onto which differs from '
            + 'rat to rat, and one circuit is one pairing \u2014 never '
            + 'pooled.',
    }));
    const tm = !!r.transition_measured;
    card.appendChild(BARRY.ui.field({
      label: 'Kind',
      control: el('div', { class: 'seg cir-kinds' }, ['state', 'transition']
        .map((k) => el('button', {
          class: st.kind === k ? 'active' : '',
          'data-kind': k,
          disabled: (k === 'transition' && !tm) ? 'disabled' : null,
          title: k === 'state'
            ? 'Four 10 s windows per cue pair: baseline, cue 1, cue 2, after '
              + 'cue 2.'
            : (tm ? 'Three windows around the boundaries: cue 1 onset, cue 1 '
                    + '\u2192 cue 2, cue 2 offset.'
                  : 'Transition clipping has not been measured on this '
                    + 'recording. Run the transition check in Spark first.'),
          text: KIND_SAY[k],
          onclick: () => { if (st.kind !== k) choose(null, k); },
        }))),
      hint: tm
        ? (st.kind === 'state'
          ? 'State: four windows per cue pair \u2014 baseline, cue 1, cue 2, '
            + 'after cue 2.'
          : 'Transition: three windows around the boundaries \u2014 cue 1 '
            + 'onset, cue 1 \u2192 cue 2, cue 2 offset.')
        : 'Transition is not offered: nobody has measured transition '
          + 'clipping on this recording, and not measured is not the same as '
          + 'clean. Run the transition check in Spark to open it.',
    }));
    const have = r.circuits || [];
    if (have.length) {
      card.appendChild(el('div', { class: 'section-label',
                                   text: 'Circuits already made' }));
      card.appendChild(el('div', { class: 'cir-haves' }, have.map((c) => el('button', {
        class: 'cir-have' + (st.shown && st.shown.meta
          && st.shown.meta.artifact_id === c.artifact_id ? ' on' : ''),
        'data-artifact': c.artifact_id,
        title: 'Open this circuit here',
        onclick: () => openArtifact(c.artifact_id, c.version_id || null, c),
      }, [
        el('strong', { text: c.nickname || c.name }),
        c.nickname ? el('span', { class: 'cir-have-name', text: c.name }) : null,
        el('span', { class: 'cir-have-v',
                     text: 'v' + c.version + ' \u00b7 ' + (KIND_SAY[c.kind] || c.kind) }),
      ].filter(Boolean)))));
    }
    return card;
  }

  /* ================================================================
     Before running
     ================================================================ */
  function planCard(r) {
    const card = el('div', { class: 'card cir-plan' }, [
      el('div', { class: 'section-label', text: 'Before it runs' }),
    ]);
    if (st.kind === 'transition' && !r.transition_measured) {
      card.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'Run the transition check in Spark first. A '
                        + 'transition circuit needs the clipping measured in '
                        + 'the three boundary windows.' }),
      ]));
      return card;
    }
    const p = st.plan;
    if (!p) {
      card.appendChild(loader('Reading the plan',
        'the pairs, the histology, what is already computed and the cost'));
      return card;
    }
    if (p.error) {
      card.appendChild(/older code/.test(p.error)
        ? routeMissing(p.error, 'The plan for this circuit could not be '
                               + 'read, so nothing can be run from here yet.')
        : el('p', { class: 'arc-ov-refused', text: p.error }));
      return card;
    }
    card.appendChild(el('div', { class: 'arc-ov' }, [
      ovSection('params', 'Parameters', paramSummary(), paramBody),
      ovSection('probes', 'Probe sanity', probeSummary(), probeBody),
      ovSection('pairs', 'Cue pairs', pairSummary(), pairBody),
    ]));
    card.appendChild(whereTabs(p.cost || {}));
    card.appendChild(costLine(p));
    card.appendChild(BARRY.ui.field({
      label: 'Nickname',
      control: el('input', {
        type: 'text', class: 'cir-nick', maxlength: '160',
        value: st.nickname || '',
        placeholder: 'Type a name of your own for it\u2026',
        oninput: (e) => { st.nickname = e.target.value; },
      }),
      hint: 'Optional. Shown above the automatic name, which stays: '
            + (p.artifact ? p.artifact.name
                          : 'it is made from the recording, the cue pairing '
                            + 'and the kind') + '.',
    }));
    card.appendChild(runBar(p));
    return card;
  }

  function ovSection(key, title, summary, body) {
    const d = el('details', { class: 'arc-ov-sec arc-ov-sec-' + key
                                     + ' cir-ov-' + key });
    if (st.open[key]) d.setAttribute('open', '');
    d.appendChild(el('summary', {}, [
      el('strong', { text: title }),
      el('span', { class: 'arc-ov-sum', text: summary }),
    ]));
    let built = false;
    const build = () => {
      if (built) return;
      built = true;
      d.appendChild(el('div', { class: 'arc-ov-body' }, [body()]));
    };
    if (st.open[key]) build();
    d.addEventListener('toggle', () => {
      st.open[key] = d.open;
      if (d.open) build();
    });
    return d;
  }

  /* ---- parameters: Coupling's fields, Coupling's refusal display ---- */
  function paramChanged(id) {
    const def = defaultsOf(st.plan)[id];
    return String(def) !== String((st.params || {})[id]);
  }

  function paramSummary() {
    const p = st.params || {};
    const specs = (st.plan && st.plan.params) || [];
    const n = specs.filter((x) => !x.fixed && paramChanged(x.id)).length;
    const bits = [];
    if (p.low != null && p.high != null) bits.push(p.low + '\u2013' + p.high + ' Hz');
    if (p.summary_hz != null) bits.push('coherence at ' + p.summary_hz + ' Hz');
    if (p.max_lag_ms != null) bits.push('\u00b1' + p.max_lag_ms + ' ms');
    if ('notch_hz' in p) bits.push(p.notch_hz ? p.notch_hz + ' Hz notch' : 'no notch');
    if (st.kind === 'transition') {
      if (p.before_s != null) bits.push(p.before_s + ' s before');
      if (p.after_s != null) bits.push(p.after_s + ' s after');
    } else if (p.pad_s != null) {
      bits.push(p.pad_s + ' s baseline');
    }
    return (bits.join(' \u00b7 ') || 'the defaults')
      + (n ? '  \u00b7  ' + n + ' changed from the default' : '')
      + (st.paramErr ? '  \u00b7  refused' : '');
  }

  function paramBody() {
    const specs = (st.plan && st.plan.params) || [];
    const grid = el('div', { class: 'arc-ov-params' },
                    specs.map((s) => paramField(s)));
    const kids = [grid];
    if (st.paramErr) {
      kids.unshift(el('p', { class: 'arc-ov-refused', text: st.paramErr }));
    }
    kids.push(el('div', { class: 'head-actions' }, [
      el('span', { class: 'hint',
        text: 'Checked on the server when you run, and refused rather than '
              + 'adjusted. One set of parameters makes one circuit; a pair '
              + 'computed at other corners is computed again, not reused.' }),
      el('div', { class: 'spacer' }),
      el('button', {
        class: 'btn ghost sm', text: 'Back to the defaults',
        disabled: specs.some((x) => !x.fixed && paramChanged(x.id))
          ? null : 'disabled',
        onclick: () => {
          st.params = defaultsOf(st.plan);
          st.paramErr = null;
          renderMain();
          replanSoon();
        },
      }),
    ]));
    return el('div', {}, kids);
  }

  function paramField(spec) {
    const val = (st.params || {})[spec.id];
    let control;
    if (spec.fixed) {
      control = el('div', { class: 'arc-ov-fixed',
        text: String(val) + (spec.unit ? ' ' + spec.unit : '') });
    } else if (spec.choices) {
      control = el('select', {
        'data-param': spec.id,
        onchange: (e) => {
          const v = e.target.value;
          st.params[spec.id] = v === 'off' ? null : Number(v);
          st.paramErr = null;
          renderMain();
          replanSoon();
        },
      }, spec.choices.map((c) => {
        const o = el('option', { value: c == null ? 'off' : String(c),
                                 text: c == null ? 'off' : c + ' ' + (spec.unit || '') });
        if ((c == null && val == null) || Number(c) === Number(val)) o.selected = true;
        return o;
      }));
    } else {
      control = el('div', { class: 'arc-ov-num' }, [
        el('input', {
          type: 'number', value: String(val), 'data-param': spec.id,
          min: spec.min != null ? String(spec.min) : null,
          max: spec.max != null ? String(spec.max) : null,
          step: spec.step != null ? String(spec.step) : null,
          // On change, not on input: repainting under the caret loses it.
          onchange: (e) => {
            const v = Number(e.target.value);
            st.params[spec.id] = isFinite(v) ? v : e.target.value;
            st.paramErr = null;
            renderMain();
            replanSoon();
          },
        }),
        el('span', { class: 'arc-ov-unit', text: spec.unit || '' }),
      ]);
    }
    const changed = paramChanged(spec.id) && !spec.fixed;
    return BARRY.ui.field({
      label: spec.name + (changed ? '  \u00b7  changed' : ''),
      control: control,
      hint: (spec.say || '')
        + (spec.min != null && spec.max != null && !spec.fixed
           ? '  ' + spec.min + ' to ' + spec.max + ' ' + (spec.unit || '') + '.'
           : ''),
      extra: 'arc-ov-field' + (spec.fixed ? ' fixed' : '')
             + (changed ? ' changed' : ''),
    });
  }

  /* ---- probe sanity ---- */
  function greyList() {
    /* `grey` is regions and why. Either shape is read -- a list of names
       with the reasons on `probe`, or a list of {region, why} -- because the
       contract says "regions + why" and a reader that only knew one would
       say "nothing grey" about the other. */
    const g = (st.plan && st.plan.grey) || [];
    return g.map((x) => (typeof x === 'string')
      ? { region: x, why: whyOf(x) }
      : { region: x.region || x.name, why: x.why || whyOf(x.region || x.name) });
  }
  function whyOf(region) {
    const p = ((st.plan && st.plan.probe) || []).find((x) => x.intended === region);
    return p ? p.why : '';
  }

  function probeSummary() {
    const probe = (st.plan && st.plan.probe) || [];
    const grey = greyList();
    if (!probe.length && !grey.length) return 'no histology for this rat';
    const n = probe.length || 12;
    const bits = [(n - grey.length) + ' of ' + n + ' will be computed'];
    if (grey.length) {
      bits.push(grey.length + ' grey: ' + grey.map((g) => g.region).join(', '));
    }
    return bits.join(' \u00b7 ');
  }

  function probeBody() {
    const probe = (st.plan && st.plan.probe) || [];
    const grey = {};
    greyList().forEach((g) => { grey[g.region] = g.why; });
    const rows = probe.map((p) => el('div', {
      class: 'arc-pr ' + p.verdict + (grey[p.intended] != null ? ' cir-grey' : ''),
      title: grey[p.intended] || p.why || '',
    }, [
      el('span', { class: 'arc-pr-v ' + p.verdict,
                   text: VERDICT_WORD[p.verdict] || p.verdict }),
      el('div', { class: 'arc-pr-name' }, [
        el('strong', { text: p.actual || p.intended }),
        p.actual && p.actual !== p.intended
          ? el('span', { class: 'arc-pr-aim', text: 'aimed at ' + p.intended })
          : null,
        p.channels
          ? el('span', { class: 'arc-pr-ch', text: 'CSC ' + p.channels.join(', ') })
          : null,
      ].filter(Boolean)),
      el('span', { class: 'cir-pr-out',
                   text: grey[p.intended] != null ? 'grey, not computed'
                                                  : 'computed' }),
    ]));
    // A grey region with no probe record at all is still said.
    for (const g of greyList()) {
      if (probe.some((p) => p.intended === g.region)) continue;
      rows.push(el('div', { class: 'arc-pr unscored cir-grey', title: g.why }, [
        el('span', { class: 'arc-pr-v unscored', text: 'not scored' }),
        el('div', { class: 'arc-pr-name' }, [el('strong', { text: g.region })]),
        el('span', { class: 'cir-pr-out', text: 'grey, not computed' }),
      ]));
    }
    return el('div', {}, [
      el('div', { class: 'arc-pr-list' }, rows),
      el('p', { class: 'hint',
        text: 'A circuit is stricter than Coupling: a probe histology marks '
              + 'relocated, missed or not scored is grey and is not computed '
              + 'at all, so its row and column stay grey and it has no edges '
              + 'on the ring. Hover a row for the reason. Heavy clipping only '
              + 'warns \u2014 a region usable in even one cue pair is kept, '
              + 'with the count shown.' }),
    ]);
  }

  /* ---- the pairs ---- */
  function pairSummary() {
    const p = st.plan || {};
    const n = p.n_pairs != null ? p.n_pairs : (p.pairs || []).length;
    const c = p.n_cached != null ? p.n_cached
      : (p.pairs || []).filter((x) => x.cached).length;
    return plural(n, 'cue pair') + ' of ' + (p.cue_label || st.cue)
      + ' \u00b7 ' + c + ' already computed';
  }

  function pairBody() {
    const pairs = (st.plan && st.plan.pairs) || [];
    const changed = ((st.plan && st.plan.params) || [])
      .some((x) => !x.fixed && paramChanged(x.id));
    return el('div', {}, [
      el('div', { class: 'cir-pairs' }, pairs.map((x) => el('span', {
        class: 'cir-pair' + (x.cached ? ' cached' : ''),
        'data-pair': String(x.pair_id),
        title: (x.label || '') + (x.opener_t != null
          ? ' at ' + Number(x.opener_t).toFixed(1) + ' s' : '')
          + (x.cached ? '\nAlready computed, so it is read, not run.'
                      : '\nWill be computed.'),
      }, [
        el('strong', { text: String(x.pair_id) }),
        el('span', { text: x.opener_t != null
          ? Number(x.opener_t).toFixed(0) + ' s' : '' }),
        x.cached ? el('span', { class: 'cir-pair-c', text: 'cached' }) : null,
      ].filter(Boolean)))),
      el('p', { class: 'hint', text: 'A pair marked cached was computed '
        + 'before at the parameters above' + (changed ? ' (not the defaults)' : '')
        + ' and is read back rather than run again. Change a parameter and '
        + 'the plan is read again for it.' }),
    ]);
  }

  /* ---- where it runs: Incisor's two tabs ---- */
  function vaccOn() {
    return !!(BARRY.state && BARRY.state.vacc && BARRY.vacc
              && (BARRY.vacc.last || {}).configured);
  }

  function whereTabs(cost, forBatch) {
    const on = vaccOn();
    const can = forBatch ? on : (on && cost.vacc_can !== false);
    // Absent is not negative: only a plan that SAYS this computer cannot
    // read the recording closes the local tab.
    const here = forBatch || cost.local_can !== false;
    const cur = forBatch ? bulk.where : st.where;
    if (!can && cur === 'vacc') {
      if (forBatch) bulk.where = 'local'; else st.where = 'local';
    }
    if (!here && can && cur === 'local') st.where = 'vacc';
    const now = forBatch ? bulk.where : st.where;
    const vaccWhy = !on
      ? 'VACC Mode is off. Turn it on in the bar at the bottom left to run '
        + 'this on the cluster.'
      : (cost.vacc_why || 'The cluster cannot run this one.');
    const mk = (id, label, sub, enabled, why) => el('button', {
      class: 'inc-tab cir-where' + (now === id ? ' on' : '')
             + (enabled ? '' : ' locked'),
      'data-where': id,
      disabled: enabled ? null : 'disabled',
      title: enabled ? sub : why,
      onclick: () => {
        if (forBatch) { bulk.where = id; bulk.plan = null; renderBatch(); askBatchPlan(); }
        else { st.where = id; renderMain(); }
      },
    }, [
      el('strong', { text: label }),
      el('span', { text: enabled ? sub : (id === 'local'
        ? 'this computer cannot read it'
        : (on ? 'the cluster cannot run this' : 'VACC Mode is off')) }),
    ]);
    const hereWhy = cost.local_why || 'This computer cannot read the recording.';
    const bar = el('div', { class: 'inc-tabs cir-wheres' }, [
      mk('local', 'This computer', forBatch ? 'one after another, here'
                                            : 'reads the files from here',
         here, hereWhy),
      mk('vacc', 'VACC', forBatch ? 'many at once, on the cluster'
                                  : 'reads the cluster\u2019s copy there',
         can, vaccWhy),
    ]);
    const notes = [];
    if (!here) notes.push(hereWhy);
    if (!can) notes.push(vaccWhy);
    if (notes.length) {
      return el('div', {}, [bar].concat(notes.map((t) => el('p', {
        class: 'hint vacc-why cir-vacc-why', text: t }))));
    }
    return bar;
  }

  /* Cost, before it is spent: the server's sentence, then here against
     there, as Incisor says it. */
  function costLine(p) {
    const c = p.cost || {};
    // The server's sentence already says both figures; the numbers are
    // only spelled out here when it did not send one.
    const bits = [];
    if (!c.sentence && c.local_s != null) bits.push('about ' + secs(c.local_s) + ' here');
    if (!c.sentence && c.vacc_s != null) bits.push('about ' + secs(c.vacc_s) + ' on VACC');
    return el('div', { class: 'cir-cost' }, [
      el('strong', { text: c.sentence || pairSummary() }),
      bits.length ? el('span', { class: 'hint', text: bits.join(' \u00b7 ')
        + (st.where === 'vacc' ? ' \u2014 the queue is the cluster\u2019s '
                                 + 'and is not in this number.' : '.') })
                  : null,
    ].filter(Boolean));
  }

  function runBar(p) {
    const busy = st.busy || !!(st.job && st.job.status === 'running');
    return el('div', { class: 'head-actions cir-runbar' }, [
      p.artifact
        ? el('button', {
            class: 'btn ghost sm',
            text: 'Open v' + p.artifact.version,
            title: 'Look at the circuit already made for this pairing and '
                   + 'kind, without running anything.',
            onclick: () => openArtifact(p.artifact.artifact_id,
                                        p.artifact.version_id || null, p.artifact),
          })
        : null,
      el('span', { class: 'hint', text: p.artifact
        ? (p.artifact.current
          ? 'v' + p.artifact.version + ' was made at exactly these settings. '
            + 'Making it again confirms it if the numbers agree, and adds a '
            + 'version if they do not.'
          : 'This pairing and kind already has a circuit, v'
            + p.artifact.version + ', made at other settings. Making it '
            + 'again adds a version; the old one is kept.')
        : 'Nothing is made until you press it. The circuit is filed as an '
          + 'artifact, which Results lists and Drift reads.' }),
      el('div', { class: 'spacer' }),
      el('button', {
        class: 'btn cir-go', disabled: busy ? 'disabled' : null,
        text: busy ? 'Making the circuit\u2026' : 'Make the circuit',
        onclick: run,
      }),
    ].filter(Boolean));
  }

  /* ================================================================
     Running
     ================================================================ */
  async function run() {
    if (st.busy || !st.gid || !st.cue) return;
    if (st.job && st.job.status === 'running') return;
    st.busy = true; st.paramErr = null;
    renderMain();
    const gid = st.gid, cue = st.cue, kind = st.kind;
    const body = { cue_type: cue, kind: kind,
                   params: Object.assign({}, st.params || {}),
                   where: st.where };
    if ((st.nickname || '').trim()) body.nickname = st.nickname.trim();
    try {
      const got = await apiPost('/api/arc/circuit/' + encodeURIComponent(gid)
                                + '/run', body);
      st.job = { id: got.job, status: 'running', stages: [], members: null };
      st.jobGid = gid; st.jobCue = cue; st.jobKind = kind; st.jobOpen = {};
      log('arc.circuit.run', { gid: gid, cue_type: cue, kind: kind, where: body.where });
      if (body.where === 'vacc' && BARRY.vaccBusy) BARRY.vaccBusy.start();
      if (st.jobStop) st.jobStop();
      st.jobStop = follow(got.job, (job) => {
        st.job = job;
        paintRun();
      }, (job) => landed(job, gid, cue, kind, body.where));
    } catch (e) {
      if (/has to be|outside|not a number|not one of|never been checked|refused/i
            .test(e.message || '')) {
        st.paramErr = e.message;
        st.open.params = true;
      } else if (!/older code/.test(e.message || '')) {
        reportClientError('circuit.run', e.message, e.stack);
      }
      toast('The circuit was not made: ' + e.message, 'err', 9000);
    } finally {
      st.busy = false;
      if (inToolkit()) renderMain();
    }
  }

  /* Follows a cfc job. The poll belongs to the module, not the view: you
     can leave, and it keeps going and toasts when it lands. A poll that
     errors is retried; twenty in a row is a lost job and is said so. */
  function follow(id, tick, end) {
    let busy = false, dead = false, misses = 0;
    const t = setInterval(async () => {
      if (busy || dead) return;
      busy = true;
      try {
        const got = await api('/api/cfc/job/' + encodeURIComponent(id));
        misses = 0;
        const job = got.job || got;
        tick(job);
        if (['done', 'failed', 'canceled'].indexOf(job.status) >= 0) {
          dead = true; clearInterval(t);
          await end(job);
        }
      } catch (e) {
        misses += 1;
        if (misses >= 20) {
          dead = true; clearInterval(t);
          await end({ id: id, status: 'failed',
                      error: 'Lost touch with the job: ' + e.message });
        }
      } finally {
        busy = false;
      }
    }, 900);
    return () => { dead = true; clearInterval(t); };
  }

  async function landed(job, gid, cue, kind, where) {
    if (where === 'vacc' && BARRY.vaccBusy) BARRY.vaccBusy.stop();
    const label = (rowOf(gid) || {}).label || gid;
    if (job.status === 'done') {
      try {
        const r = await api('/api/cfc/result/' + encodeURIComponent(job.id));
        const res = (r && r.result && (r.result.payload || r.result.artifact_id))
          ? r.result : r;
        if (!res || !res.payload) throw new Error('The job finished but '
          + 'returned no circuit.');
        const meta = {
          artifact_id: res.artifact_id, version: res.version,
          version_id: res.version_id, digest: res.digest,
          name: res.name, nickname: res.nickname, new_version: res.new_version,
          computed_on: res.computed_on || res.payload.computed_on,
        };
        if (st.gid === gid) { st.shown = { payload: res.payload, meta: meta }; st.shownErr = null; }
        toast((res.new_version === false
               ? 'Same numbers as v' + res.version + ' \u2014 confirmed, no new '
                 + 'version: '
               : 'Circuit made, v' + res.version + ': ')
              + (res.nickname || res.name || label) + '.', 'ok', 9000);
        log('arc.circuit.landed', { gid: gid, cue_type: cue, kind: kind,
                                    artifact: res.artifact_id,
                                    version: res.version,
                                    new_version: res.new_version });
        if (BARRY.artifacts && BARRY.artifacts.reload) {
          try { BARRY.artifacts.reload(); } catch (e) { /* not shown */ }
        }
      } catch (e) {
        toast('The circuit could not be read back: ' + e.message, 'err', 12000);
        reportClientError('circuit.result', e.message, e.stack);
      }
    } else if (job.status === 'canceled') {
      toast('The circuit run was stopped. Pairs that had landed are kept '
            + 'in the cache.', 'warn', 7000);
    } else {
      toast('The circuit for ' + label + ' failed: '
            + (job.error || 'no reason was given.'), 'err', 12000);
    }
    st.job = null; st.jobStop = null;
    await loadRows();
    if (st.gid === gid) { st.plan = null; loadPlan(); }
    if (inToolkit()) { renderPick(); renderMain(); }
  }

  async function cancel() {
    if (!st.job) return;
    try { await apiPost('/api/cfc/job/' + encodeURIComponent(st.job.id)
                        + '/cancel', {}); }
    catch (e) { toast('Could not stop it: ' + e.message, 'err', 6000); }
  }

  /* The stage words for the cluster's stages are Doppler's. The circuit's
     own stages are named by the backend; an unknown one is shown by its
     own name rather than hidden. */
  const STAGE_WORDS = {
    'vacc stage': 'Send the code over',
    'vacc queue': 'Waiting for the cluster',
    'vacc fetch': 'Bring the answer back',
  };
  const FIRST = ['vacc stage', 'vacc queue'];
  const LAST = ['vacc fetch'];

  const MEMBER_SAY = {
    waiting: 'waiting', pending: 'waiting', queued: 'waiting',
    running: 'computing', done: 'done', cached: 'read from the cache',
    failed: 'failed', skipped: 'skipped',
  };

  function runCard() {
    return el('div', { class: 'card comod-run cir-run' }, [
      el('div', { class: 'comod-run-head' }, [
        el('strong', { text: st.jobKind === 'transition'
          ? 'Making the transition circuit' : 'Making the circuit' }),
        el('span', { class: 'hint', text: (rowOf(st.jobGid) || {}).label || '' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost sm', text: 'Stop',
                       title: 'Stops the run. Pairs that have landed stay '
                              + 'cached, so running again does not redo them.',
                       onclick: cancel }),
      ]),
      el('div', { id: 'cirStages', class: 'comod-stages' }),
      el('div', { class: 'comod-total' }, [
        el('div', { class: 'comod-bar' }, [
          el('div', { id: 'cirBarFill', class: 'comod-bar-fill' })]),
        el('span', { id: 'cirEta', class: 'comod-eta' }),
      ]),
      el('pre', { id: 'cirLog', class: 'dop-log', style: 'display:none' }),
      el('div', { class: 'section-label', text: 'Cue pairs, as they land' }),
      el('div', { id: 'cirMembers', class: 'cir-members' }),
      el('div', { id: 'cirPartial', class: 'cir-partial' }),
      el('p', { class: 'hint quiet',
        text: 'You can leave this view. The run belongs to Jarvis, not to '
              + 'this page: come back to Circuit and it is still here, and a '
              + 'toast says when it lands.' }),
    ]);
  }

  function paintRun() {
    const job = st.job;
    if (!job) return;
    const host = document.getElementById('cirStages');
    if (!host) return;
    host.innerHTML = '';
    const stages = (job.stages || []).slice();
    const rank = (n) => FIRST.indexOf(n) >= 0 ? FIRST.indexOf(n) - 10
      : (LAST.indexOf(n) >= 0 ? 100 : 0);
    stages.sort((a, b) => rank(a.name) - rank(b.name));
    const qs = stages.find((s) => s.name === 'vacc queue');
    const nodeBusy = stages.some((s) => FIRST.indexOf(s.name) < 0
      && LAST.indexOf(s.name) < 0 && s.status === 'running') && !!qs;
    const onNode = nodeBusy || (!!qs && qs.status !== 'done' && qs.done >= 1);
    const queued = !!qs && qs.status !== 'done' && !(qs.done >= 1) && !nodeBusy;
    let total = 0, done = 0;
    for (const s of stages) {
      const w = s.name === 'vacc queue' ? 20 : (s.of > 1 ? 10 : 2);
      total += w;
      const frac = s.of ? Math.min(1, (s.done || 0) / s.of) : 0;
      done += w * (s.status === 'done' ? 1 : frac);
      const running = s.status === 'running';
      host.appendChild(el('div', {
        class: 'comod-stage' + (running ? ' on' : '')
               + (s.status === 'done' ? ' done' : '')
               + (s.status === 'failed' ? ' bad' : ''),
      }, [
        el('span', { class: 'comod-tick', text: s.status === 'done' ? '\u2713'
          : running ? '\u25b8' : s.status === 'failed' ? '\u2717' : '' }),
        el('span', { class: 'comod-stage-name', text: s.name === 'vacc queue'
          ? (onNode ? 'Running on a cluster node'
                    : 'Waiting in the cluster\u2019s queue')
          : (STAGE_WORDS[s.name] || s.name) }),
        el('span', { class: 'comod-stage-count', text: s.of > 1
          ? (s.status === 'waiting' ? '\u2013' : (s.done || 0)) + ' / ' + s.of
            + ' ' + (s.unit || '') : '' }),
        running && s.of > 1 ? el('div', { class: 'comod-mini' }, [
          el('div', { class: 'comod-mini-fill',
                      style: 'width:' + (frac * 100).toFixed(1) + '%' })]) : null,
        el('span', { class: 'comod-stage-time',
                     text: s.seconds != null ? Number(s.seconds).toFixed(1) + ' s' : '' }),
      ].filter(Boolean)));
    }
    const fill = document.getElementById('cirBarFill');
    const members = job.members || [];
    const landedN = members.filter((m) => m.status === 'done' || m.cached
                                         || m.status === 'cached').length;
    const frac = total ? done / total
      : (members.length ? landedN / members.length : 0);
    if (fill) fill.style.width = (100 * frac).toFixed(1) + '%';
    const eta = document.getElementById('cirEta');
    if (eta) {
      const since = secs(job.elapsed || 0);
      eta.textContent = queued
        ? 'queued for ' + since + ' \u2014 the cluster decides when it starts'
        : onNode ? 'running on the cluster, ' + since + ' so far'
        : (job.eta_s ? 'about ' + secs(job.eta_s) + ' left' : since + ' so far');
    }
    const logBox = document.getElementById('cirLog');
    if (logBox) {
      const lines = job.log || [];
      logBox.textContent = lines.join('\n');
      logBox.style.display = lines.length ? '' : 'none';
    }
    paintMembers(members);
    paintPartial(job);
  }

  /* One row per cue pair, each openable the moment it lands. */
  function paintMembers(members) {
    const box = document.getElementById('cirMembers');
    if (!box) return;
    box.innerHTML = '';
    if (!members.length) {
      box.appendChild(el('p', { class: 'hint',
        text: 'The pairs are listed here once the job has declared them.' }));
      return;
    }
    const partial = st.job && st.job.partial;
    for (const m of members) {
      const status = m.cached && m.status === 'done' ? 'cached' : (m.status || 'waiting');
      const landedRow = status === 'done' || status === 'cached';
      const facts = [
        ['state', (MEMBER_SAY[status] || status)
          + (m.error ? ': ' + m.error : '')],
        ['step', m.step || '\u2014'],
        ['time', m.seconds != null ? Number(m.seconds).toFixed(1) + ' s' : '\u2014'],
        ['cache', m.cached ? 'read back, not recomputed' : 'computed on this run'],
      ];
      const pid = pairIdOf(m);
      if (partial && pid != null) facts.push(['values', partialSay(partial, pid)]);
      const head = [
        el('span', { class: 'cir-m-id', text: m.label || ('cue pair ' + m.id) }),
        el('span', { class: 'cir-m-st ' + status,
                     text: (MEMBER_SAY[status] || status)
                           + (status === 'failed' && m.error ? ': ' + m.error : '') }),
      ];
      if (!landedRow) {
        box.appendChild(el('div', { class: 'cir-m ' + status,
                                    'data-member': String(m.id) }, head));
        continue;
      }
      const grid = el('div', { class: 'arc-batch-facts' });
      for (const [k, v] of facts) {
        grid.appendChild(el('span', { class: 'arc-batch-fact-k', text: k }));
        grid.appendChild(el('span', { class: 'arc-batch-fact-v', text: v }));
      }
      box.appendChild(el('details', {
        class: 'cir-m ' + status, 'data-member': String(m.id),
        open: st.jobOpen[m.id] ? 'open' : null,
        ontoggle: (e) => {
          if (e.target.open) st.jobOpen[m.id] = true;
          else delete st.jobOpen[m.id];
        },
      }, [el('summary', {}, head), grid]));
    }
  }

  function pairIdOf(m) {
    if (m.pair_id != null) return m.pair_id;
    const n = Number(m.id);
    return isFinite(n) ? n : null;
  }

  function partialSay(partial, pid) {
    const w = pref.win[partial.kind] || (partial.windows || [])[0];
    const cells = ((partial.cells || {})[w] || {})[pref.method] || {};
    const vs = [];
    for (const k in cells) {
      const hit = (cells[k].values || []).find((x) => x.pair_id === pid);
      if (hit) vs.push(hit.v);
    }
    if (!vs.length) return 'no region pair usable in ' + say(w);
    return vs.length + ' region pairs in ' + say(w) + ', '
      + METHOD_NAME[pref.method].toLowerCase() + ' '
      + fmt(Math.min.apply(null, vs), 2) + ' to ' + fmt(Math.max.apply(null, vs), 2);
  }

  /* The matrix so far -- only if the job exposes one. The route contract
     guarantees the member rows; a partial payload is extra, so its absence
     is said rather than guessed around. */
  function paintPartial(job) {
    const box = document.getElementById('cirPartial');
    if (!box) return;
    const p = job.partial;
    if (p && p.cells && p.region_order) {
      if (box.__cirRev === job.rev) return;
      box.__cirRev = job.rev;
      box.innerHTML = '';
      box.appendChild(el('div', { class: 'section-label',
        text: 'The matrix so far \u00b7 ' + (p.n_pairs || 0) + ' of '
              + ((job.members || []).length || '?') + ' cue pairs' }));
      const inner = el('div');
      box.appendChild(inner);
      renderCircuit(inner, p, { partial: true, compact: true });
      return;
    }
    if (box.__cirSaid) return;
    box.__cirSaid = true;
    box.innerHTML = '';
    box.appendChild(el('p', { class: 'hint',
      text: 'The matrix is drawn when the last pair lands \u2014 this job '
            + 'reports each pair\u2019s progress but not its values.' }));
  }

  /* ================================================================
     A circuit on screen in the panel
     ================================================================ */
  async function openArtifact(id, v, meta) {
    st.shownErr = null;
    st.shown = { payload: null, meta: Object.assign({ artifact_id: id }, meta || {}) };
    renderMain();
    try {
      const got = (BARRY.artifacts && BARRY.artifacts.payload)
        ? await BARRY.artifacts.payload(id, v)
        : await api('/api/artifacts/' + encodeURIComponent(id) + '/payload'
                    + (v == null ? '' : '?v=' + encodeURIComponent(v)));
      if (!st.shown || st.shown.meta.artifact_id !== id) return;
      st.shown.payload = got.payload;
      st.shown.meta.version = got.version;
      st.shown.meta.version_id = got.version_id || st.shown.meta.version_id;
      st.shown.meta.digest = got.digest;
    } catch (e) {
      /* Not a fault to report: a payload that has not reached this machine
         answers 404 with a sentence saying so, and the sentence is the
         answer. Shown as it is. */
      st.shown = null;
      st.shownErr = e.message;
    }
    renderMain();
  }

  function shownCard() {
    const card = el('div', { class: 'card cir-shown' });
    if (st.shownErr) {
      card.appendChild(/older code/.test(st.shownErr)
        ? routeMissing(st.shownErr, 'That circuit could not be read.')
        : el('div', { class: 'empty-state' }, [
            el('p', { text: st.shownErr }),
            el('p', { class: 'hint', text: 'Results → Artifacts lists '
              + 'every version and says which machine holds each one.' }),
          ]));
      return card;
    }
    if (!st.shown.payload) {
      card.appendChild(loader('Reading the circuit',
                              'its payload, from the artifact store'));
      return card;
    }
    const inner = el('div', { class: 'cir-host' });
    card.appendChild(inner);
    renderCircuit(inner, st.shown.payload, st.shown.meta);
    return card;
  }

  /* ==================================================================
     The renderer -- the matrix and the ring, one function for the panel
     and for Results.

     `meta`: { artifact_id, name, nickname, version, digest, new_version,
               computed_on, inResults, partial, compact }
     ================================================================== */
  function renderCircuit(host, payload, meta) {
    meta = meta || {};
    const P = payload || {};
    host.innerHTML = '';
    host.classList.add('cir-view');
    if (!P.region_order || !P.windows || !P.cells) {
      host.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'This is not a circuit payload (' + (P.schema || 'no '
                        + 'schema') + '), so there is nothing to draw. '
                        + 'Download it as JSON from Results to see what it '
                        + 'holds.' }),
      ]));
      return null;
    }
    const kind = P.kind || 'state';
    let win = pref.win[kind];
    if (P.windows.indexOf(win) < 0) win = P.windows[0];
    let method = pref.method;
    if ((P.methods || []).indexOf(method) < 0) method = (P.methods || [])[0];
    const ctx = { host: host, P: P, meta: meta, win: win, method: method,
                  sel: pref.sel, hover: null };
    host.__cir = ctx;
    if (live.indexOf(ctx) < 0) {
      for (let i = live.length - 1; i >= 0; i--) {
        if (live[i].host === host || !live[i].host.isConnected) live.splice(i, 1);
      }
      live.push(ctx);
    }

    if (!meta.compact) host.appendChild(headBlock(ctx));
    host.appendChild(el('div', { class: 'arc-cp-controls cir-controls' }, [
      el('div', { class: 'seg cir-wins' }, P.windows.map((w) => el('button', {
        class: w === ctx.win ? 'active' : '', 'data-win': w, text: say(w),
        onclick: () => { pref.win[kind] = w; renderCircuit(host, P, meta); },
      }))),
      el('div', { class: 'seg cir-methods' }, (P.methods || []).map((m) => el('button', {
        class: m === ctx.method ? 'active' : '', 'data-method': m,
        title: (METHODS.find((x) => x[0] === m) || [])[2] || '',
        text: METHOD_NAME[m] || m,
        onclick: () => { pref.method = m; renderCircuit(host, P, meta); },
      }))),
    ]));
    const body = el('div', { class: 'cir-body' + (meta.compact ? ' compact' : '') });
    const left = el('div', { class: 'cir-left' });
    const right = el('div', { class: 'cir-right' });
    body.appendChild(left);
    if (!meta.compact) body.appendChild(right);
    host.appendChild(body);

    left.appendChild(matrixGrid(ctx));
    left.appendChild(matrixKey(ctx));
    if (!meta.compact) {
      ctx.ringBox = el('div', { class: 'cir-ring-box' });
      right.appendChild(ctx.ringBox);
      paintRing(ctx);
      ctx.detail = el('div', { class: 'cir-detail' });
      host.appendChild(ctx.detail);
      paintDetail(ctx);
    }
    return ctx;
  }

  function headBlock(ctx) {
    const m = ctx.meta, P = ctx.P;
    const title = m.nickname || m.name || P.source && P.source.session_label || 'Circuit';
    const on = P.computed_on || m.computed_on || {};
    const where = on.kind === 'vacc'
      ? 'made on VACC' + (on.slurm_id ? ' (job ' + on.slurm_id + ')' : '')
      : on.kind === 'local' ? 'made on this computer'
      : (on.kind ? 'made on ' + on.kind : 'where it was made is not recorded');
    const facts = [
      m.version != null ? 'v' + m.version : null,
      m.digest ? 'digest ' + m.digest : null,
      P.cue_label || P.cue_type,
      KIND_SAY[P.kind] || P.kind,
      plural(P.n_pairs || 0, 'cue pair'),
      where,
    ].filter(Boolean);
    const kids = [
      el('div', { class: 'cir-titles' }, [
        el('strong', { class: 'cir-nick-t', text: title }),
        m.nickname && m.name ? el('span', { class: 'cir-name-t', text: m.name }) : null,
        el('span', { class: 'cir-facts', text: facts.join(' \u00b7 ') }),
        m.new_version === false
          ? el('span', { class: 'flagchip mat', text: 'confirmed \u2014 same numbers' })
          : null,
      ].filter(Boolean)),
    ];
    if (m.artifact_id && !m.inResults) {
      const input = el('input', {
        type: 'text', class: 'cir-nick-edit', maxlength: '160',
        value: m.nickname || '',
        placeholder: 'Type a name of your own for it\u2026',
        onkeydown: (e) => { if (e.key === 'Enter') saveNick(); },
      });
      const saveNick = async () => {
        try {
          await apiPost('/api/artifacts/' + encodeURIComponent(m.artifact_id)
                        + '/nickname', { nickname: input.value });
          m.nickname = input.value.trim() || null;
          toast(m.nickname ? 'Nickname saved.' : 'Nickname cleared.', 'ok');
          await loadRows();
          if (inToolkit()) { renderPick(); }
          renderCircuit(ctx.host, ctx.P, m);
        } catch (e) {
          toast('The nickname was not saved: ' + e.message, 'err', 8000);
          reportClientError('circuit.nickname', e.message, e.stack);
        }
      };
      kids.push(el('div', { class: 'head-actions cir-headacts' }, [
        input,
        el('button', { class: 'btn ghost sm', text: 'Save nickname',
                       title: 'Shown above the automatic name everywhere. '
                              + 'Empty goes back to the automatic name.',
                       onclick: saveNick }),
        el('button', { class: 'btn ghost sm', text: 'Open in Results',
                       title: 'Versions, where each came from, what cites '
                              + 'it, and the payload as JSON.',
                       onclick: () => {
                         if (BARRY.artifacts && BARRY.artifacts.open) {
                           BARRY.artifacts.open(m.artifact_id, m.version_id || null);
                         }
                       } }),
      ]));
    }
    return el('div', { class: 'cir-head' }, kids);
  }

  function cellsOf(ctx) {
    return ((ctx.P.cells || {})[ctx.win] || {})[ctx.method] || {};
  }
  function keyOf(P, a, b) {
    const o = P.region_order;
    return o.indexOf(a) < o.indexOf(b) ? a + '|' + b : b + '|' + a;
  }
  function regionRec(P, name) {
    return (P.regions || []).find((r) => r.region === name) || null;
  }
  function isGrey(P, name) {
    if ((P.grey || []).indexOf(name) >= 0) return true;
    const r = regionRec(P, name);
    return !!(r && r.status === 'grey');
  }
  function greyWhy(P, name) {
    const r = regionRec(P, name);
    return (r && r.why) || 'Not computed in this circuit.';
  }
  function usableSay(ctx, name) {
    const u = ((ctx.P.region_usable || {})[ctx.win] || {})[name];
    return u ? 'usable in ' + u.usable + ' of ' + u.of + ' cue pairs in '
               + say(ctx.win) : '';
  }
  function pairLabel(P, pid) {
    const p = (P.pairs || []).find((x) => x.pair_id === pid);
    return p ? 'cue pair ' + pid + (p.opener_t != null
      ? ' at ' + Number(p.opener_t).toFixed(1) + ' s' : '') : 'cue pair ' + pid;
  }
  function cellTitle(ctx, a, b, c) {
    const P = ctx.P;
    return a + ' \u00d7 ' + b + '\n' + (METHOD_NAME[ctx.method] || ctx.method)
      + ' in ' + say(ctx.win) + '\nmean ' + fmt(c.mean, 4)
      + (c.sd != null ? ', SD ' + fmt(c.sd, 4) : ', no SD (one value)')
      + '\nn = ' + c.n + ' of ' + (c.of != null ? c.of : P.n_pairs) + ' cue pairs'
      + (c.warn ? '\n' + c.warn : '')
      + '\n\n' + (c.values || []).map((x) => pairLabel(P, x.pair_id) + ': '
                                            + fmt(x.v, 4)).join('\n')
      + '\n\nClick for the values behind it.';
  }

  /* ---------------- the matrix ---------------- */
  function matrixGrid(ctx) {
    const P = ctx.P, order = P.region_order;
    const cells = cellsOf(ctx);
    const diverging = ctx.method !== 'coherence';
    const nodes = [el('div', { class: 'arc-mx-corner' })];
    const headOf = (name, kind, i) => {
      const grey = isGrey(P, name);
      const rec = regionRec(P, name);
      const m = metaOf(name);
      const full = (m.hemisphere && m.name) ? m.hemisphere + ' ' + m.name.toLowerCase() : name;
      const n = el('div', {
        class: 'arc-mx-head ' + kind + (grey ? ' grey' : '')
               + (rec && rec.histology === 'uncertain' ? ' unsure' : ''),
        title: full + (full !== name ? ' (' + name + ')' : '') + '\n'
               + (grey ? 'Grey, not computed. ' + greyWhy(P, name)
                       : usableSay(ctx, name)
                         + (rec && rec.why ? '\n' + rec.why : '')),
        text: shortRegion(name),
      });
      n.dataset[kind === 'row' ? 'r' : 'c'] = String(i);
      return n;
    };
    order.forEach((b, j) => nodes.push(headOf(b, 'col', j)));
    order.forEach((a, i) => {
      nodes.push(headOf(a, 'row', i));
      order.forEach((b, j) => {
        let node;
        if (a === b) {
          node = el('div', { class: 'arc-mx-cell self', 'data-state': 'self' });
        } else if (isGrey(P, a) || isGrey(P, b)) {
          const why = [isGrey(P, a) ? a + ': ' + greyWhy(P, a) : null,
                       isGrey(P, b) ? b + ': ' + greyWhy(P, b) : null]
            .filter(Boolean).join('\n\n');
          node = el('div', { class: 'arc-mx-cell cir-grey', 'data-state': 'grey',
                             title: a + ' \u00d7 ' + b + ' \u2014 grey, not '
                                    + 'computed.\n\n' + why });
        } else {
          const key = keyOf(P, a, b);
          const c = cells[key];
          if (!c) {
            node = el('div', {
              class: 'arc-mx-cell cir-absent', 'data-state': 'absent',
              'data-key': key,
              title: a + ' \u00d7 ' + b + ' \u2014 no value. No cue pair had '
                     + 'both regions usable in ' + say(ctx.win) + '. Blank, '
                     + 'not zero.',
            });
          } else {
            const v = Number(c.mean);
            node = el('div', {
              class: 'arc-mx-cell cir-val' + (c.warn ? ' warn' : '')
                     + (ctx.sel === key ? ' sel' : ''),
              'data-state': 'value', 'data-key': key,
              'data-n': String(c.n),
              style: 'background-color:' + cellColour(v, diverging),
              title: cellTitle(ctx, a, b, c),
              onclick: () => select(ctx, key),
            }, [
              el('span', { class: 'cir-mx-v', text: short(v) }),
              el('span', { class: 'cir-mx-n', text: String(c.n) }),
            ]);
          }
        }
        node.dataset.r = String(i);
        node.dataset.c = String(j);
        nodes.push(node);
      });
    });
    const grid = el('div', {
      class: 'arc-mx cir-mx',
      style: 'grid-template-columns: 58px repeat(' + order.length
             + ', minmax(0, 1fr));',
    }, nodes);
    const s = shared();
    if (s && s.crosshair) s.crosshair(grid);
    return grid;
  }

  function counts(ctx) {
    const P = ctx.P, order = P.region_order;
    const cells = cellsOf(ctx);
    let present = 0, warn = 0, absent = 0, grey = 0;
    for (let i = 0; i < order.length; i++) {
      for (let j = i + 1; j < order.length; j++) {
        const a = order[i], b = order[j];
        if (isGrey(P, a) || isGrey(P, b)) { grey += 1; continue; }
        const c = cells[keyOf(P, a, b)];
        if (!c) { absent += 1; continue; }
        present += 1;
        if (c.warn) warn += 1;
      }
    }
    return { present: present, warn: warn, absent: absent, grey: grey };
  }

  function matrixKey(ctx) {
    const P = ctx.P, k = counts(ctx);
    const diverging = ctx.method !== 'coherence';
    const greyNames = P.region_order.filter((n) => isGrey(P, n));
    const out = [
      el('span', { class: 'arc-mx-key cir-key-val',
        title: diverging
          ? 'Red is a positive correlation and the accent colour a negative '
            + 'one; the stronger the colour, the larger |r|.'
          : 'Coherence runs 0 to 1; the stronger the colour, the higher.',
        text: k.present + ' region pairs with a value \u00b7 the small number '
              + 'is n, the cue pairs behind the mean' }),
    ];
    if (k.warn) {
      out.push(el('span', { class: 'arc-mx-key warn cir-key-warn',
        text: k.warn + ' usable in fewer than half the cue pairs \u2014 kept, '
              + 'and marked' }));
    }
    if (k.absent) {
      out.push(el('span', { class: 'arc-mx-key cir-key-absent',
        text: k.absent + ' blank: no cue pair had both regions usable in '
              + say(ctx.win) + ' (blank, not zero)' }));
    }
    if (greyNames.length) {
      out.push(el('span', { class: 'arc-mx-key blocked cir-key-grey',
        title: greyNames.map((n) => n + ': ' + greyWhy(P, n)).join('\n\n'),
        text: 'grey, not computed: ' + greyNames.map((n) => {
          const r = regionRec(P, n);
          return n + (r ? ' (' + (VERDICT_WORD[r.histology] || r.histology) + ')' : '');
        }).join(', ') }));
    }
    return el('div', { class: 'arc-mx-keys cir-keys' }, out);
  }

  /* ---------------- the ring ----------------

     The cluster's layout, measured from network_lib.node_positions: node i
     of the network order sits at 15 + 30 i degrees clockwise from the top,
     so Right ACC and Left ACC flank the top, the right hemisphere runs down
     the right side and the left mirrors it. The same order the matrix
     uses, so row i of the matrix is node i of the ring. */
  const RING = { w: 540, h: 470, cx: 270, cy: 232, r: 150, node: 21, lab: 36 };

  function ringXY(i) {
    const th = (15 + 30 * i) * Math.PI / 180;
    return { x: RING.cx + RING.r * Math.sin(th), y: RING.cy - RING.r * Math.cos(th),
             sin: Math.sin(th), cos: Math.cos(th) };
  }

  function thrOf(ctx) {
    const fam = ctx.method;
    if (pref.thr[fam] != null) return { v: pref.thr[fam], auto: false };
    // The median |mean| of this panel, until somebody moves the slider:
    // half the edges, which is "not all 66" without a number nobody chose.
    const vs = Object.values(cellsOf(ctx)).map((c) => Math.abs(Number(c.mean)))
      .filter((v) => isFinite(v)).sort((a, b) => a - b);
    if (!vs.length) return { v: 0, auto: true };
    const med = vs[Math.floor((vs.length - 1) / 2)];
    return { v: Math.floor(med * 100) / 100, auto: true };
  }

  function edgesOf(ctx, thr) {
    const P = ctx.P, cells = cellsOf(ctx), out = [];
    for (const key in cells) {
      const [a, b] = key.split('|');
      if (isGrey(P, a) || isGrey(P, b)) continue;
      const c = cells[key];
      const v = Number(c.mean);
      if (!isFinite(v) || Math.abs(v) < thr) continue;
      out.push({ key: key, a: a, b: b, c: c, v: v });
    }
    out.sort((x, y) => Math.abs(x.v) - Math.abs(y.v));
    return out;
  }

  /* The node's label ink: whichever of the theme's two extremes, --bg and
     --text, is the far side of the atlas colour it sits on. */
  function contrastInk(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '').trim());
    const a = BARRY.token('--bg'), b = BARRY.token('--text');
    const lum = (h) => {
      const mm = /^#?([0-9a-f]{6})$/i.exec(String(h || '').trim());
      if (!mm) return 0.5;
      const n = parseInt(mm[1], 16);
      return (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255)
              + 0.114 * (n & 255)) / 255;
    };
    if (!m) return b;
    const want = lum(hex) > 0.6 ? 'dark' : 'light';
    const la = lum(a), lb = lum(b);
    const darkInk = la < lb ? a : b, lightInk = la < lb ? b : a;
    return want === 'dark' ? darkInk : lightInk;
  }

  function paintRing(ctx) {
    const box = ctx.ringBox;
    if (!box) return;
    box.innerHTML = '';
    const P = ctx.P, order = P.region_order;
    /* `ctx.ring` is Drift's (see `ringInto`): it supplies the edges, the
       threshold control and the words, and everything else -- the layout,
       the nodes and their atlas colours, hover, download -- is this one
       function, so a delta ring and a circuit ring cannot come apart. */
    const R = ctx.ring || null;
    const t = R ? R.thr(ctx) : thrOf(ctx);
    const diverging = R ? !!R.diverging : ctx.method !== 'coherence';
    const edges = R ? R.edges(ctx, t) : edgesOf(ctx, t.v);
    const total = R ? R.total(ctx) : counts(ctx).present;
    const tok = (n) => BARRY.token(n);
    const font = tok('--sans');

    const svg = el('svg', {
      class: 'cir-ring', viewBox: '0 0 ' + RING.w + ' ' + RING.h,
      width: String(RING.w), height: String(RING.h), role: 'img',
      'font-family': font,
      'aria-label': 'Network ring: ' + edges.length + ' of ' + total
                    + ' region pairs drawn, ' + (METHOD_NAME[ctx.method] || '')
                    + ' in ' + say(ctx.win),
      'data-threshold': String(t.v),
    });
    svg.appendChild(el('rect', { class: 'cir-ring-bg', x: '0', y: '0',
                                 width: String(RING.w), height: String(RING.h),
                                 fill: tok('--bg') }));
    const gE = el('g', { class: 'cir-edges' });
    const pos = {};
    order.forEach((n, i) => { pos[n] = ringXY(i); });
    for (const e of edges) {
      const mag = e.mag != null ? e.mag : Math.min(1, Math.abs(e.v));
      const A = pos[e.a], B = pos[e.b];
      const g = el('g', { class: 'cir-edge-g', 'data-key': e.key });
      g.appendChild(el('line', Object.assign({
        class: 'cir-edge' + (ctx.sel === e.key ? ' sel' : ''),
        'data-key': e.key, 'data-v': String(e.v), 'data-n': String(e.c.n),
        x1: A.x.toFixed(2), y1: A.y.toFixed(2), x2: B.x.toFixed(2), y2: B.y.toFixed(2),
        stroke: edgeHue(e.v, diverging),
        'stroke-width': (0.8 + 4.4 * mag).toFixed(2),
        'stroke-opacity': Math.min(1, 0.22 + 0.66 * mag).toFixed(3),
        'stroke-linecap': 'round',
        'stroke-dasharray': e.dash !== undefined ? e.dash : (e.c.warn ? '5 3' : null),
      }, e.attrs || {})));
      g.appendChild(el('line', {
        class: 'cir-hit', 'data-key': e.key,
        x1: A.x.toFixed(2), y1: A.y.toFixed(2), x2: B.x.toFixed(2), y2: B.y.toFixed(2),
        stroke: tok('--text'), 'stroke-opacity': '0', 'stroke-width': '10',
      }, [el('title', { text: R ? R.title(e) : cellTitle(ctx, e.a, e.b, e.c) })]));
      gE.appendChild(g);
    }
    svg.appendChild(gE);

    const gN = el('g', { class: 'cir-nodes' });
    order.forEach((name, i) => {
      const p = pos[name];
      const grey = isGrey(P, name);
      const m = metaOf(name);
      const rec = regionRec(P, name);
      const fill = grey ? tok('--bg-3') : (m.color || tok('--text-3'));
      const ink = grey ? tok('--text-3') : contrastInk(m.color);
      const full = (m.hemisphere && m.name)
        ? m.hemisphere + ' ' + m.name.toLowerCase() : name;
      const deg = edges.filter((e) => e.a === name || e.b === name).length;
      const g = el('g', { class: 'cir-node' + (grey ? ' grey' : ''),
                          'data-region': name, 'data-i': String(i) });
      g.appendChild(el('title', { text: full + ' (' + name + ')'
        + (rec && rec.label && rec.label !== name ? '\nHistology: ' + rec.label : '')
        + '\n' + (grey ? 'Grey, not computed. ' + greyWhy(P, name)
                       : usableSay(ctx, name) + '\n' + deg + ' edges drawn at '
                         + 'this threshold')
        + (R && R.nodeNote ? R.nodeNote(name) : '') }));
      g.appendChild(el('circle', {
        class: 'cir-node-c', cx: p.x.toFixed(2), cy: p.y.toFixed(2),
        r: String(RING.node), fill: fill,
        stroke: grey ? tok('--line') : tok('--text-3'),
        'stroke-width': grey ? '1.2' : '1',
        'stroke-dasharray': grey ? '3 2' : null,
      }));
      g.appendChild(el('text', {
        class: 'cir-node-t', x: p.x.toFixed(2), y: (p.y + 4).toFixed(2),
        'text-anchor': 'middle', 'font-size': '11', 'font-weight': '700',
        fill: ink, text: m.abbr || name,
      }));
      const lx = RING.cx + (RING.r + RING.lab) * p.sin;
      const ly = RING.cy - (RING.r + RING.lab) * p.cos;
      g.appendChild(el('text', {
        class: 'cir-node-l', x: lx.toFixed(2), y: (ly + 4).toFixed(2),
        'text-anchor': p.sin > 0.2 ? 'start' : (p.sin < -0.2 ? 'end' : 'middle'),
        'font-size': '11.5', fill: grey ? tok('--text-3') : tok('--text-2'),
        'font-style': grey ? 'italic' : null,
        text: name + (grey ? ' \u00b7 grey' : ''),
      }));
      gN.appendChild(g);
    });
    svg.appendChild(gN);
    svg.appendChild(el('text', {
      class: 'cir-ring-cap', x: String(RING.cx), y: String(RING.h - 10),
      'text-anchor': 'middle', 'font-size': '11', fill: tok('--text-3'),
      text: R ? R.caption(ctx, t, edges, total)
        : (METHOD_NAME[ctx.method] || ctx.method) + ' \u00b7 ' + say(ctx.win)
            + ' \u00b7 |value| \u2265 ' + t.v.toFixed(2) + ' \u00b7 '
            + edges.length + ' of ' + total + ' edges',
    }));

    // Hover: the edge or node under the pointer, said under the ring.
    const read = el('p', { class: 'hint cir-read',
      text: R && R.hint ? R.hint
        : 'Hover an edge or a node for its value, n and the cue pairs '
            + 'behind it; click an edge for the values.' });
    svg.addEventListener('mouseover', (ev) => {
      const hit = ev.target.closest('[data-key]');
      const node = ev.target.closest('[data-region]');
      svg.classList.remove('focus');
      svg.querySelectorAll('.on').forEach((x) => x.classList.remove('on'));
      if (hit && R) {
        read.textContent = R.read(hit.dataset.key);
      } else if (hit) {
        const c = cellsOf(ctx)[hit.dataset.key];
        const [a, b] = hit.dataset.key.split('|');
        read.textContent = a + ' \u00d7 ' + b + ': mean ' + fmt(c.mean, 3)
          + (c.sd != null ? ' (SD ' + fmt(c.sd, 3) + ')' : '') + ', n = ' + c.n
          + ' of ' + (c.of != null ? c.of : P.n_pairs)
          + (c.warn ? ' \u2014 ' + c.warn : '') + '. Cue pairs '
          + (c.values || []).map((x) => x.pair_id).join(', ') + '.';
      } else if (node) {
        const name = node.dataset.region;
        svg.classList.add('focus');
        svg.querySelectorAll('.cir-edge-g').forEach((g) => {
          const [a, b] = g.dataset.key.split('|');
          if (a === name || b === name) g.classList.add('on');
        });
        const m = metaOf(name);
        read.textContent = ((m.hemisphere && m.name)
          ? m.hemisphere + ' ' + m.name.toLowerCase() + ' (' + name + ')' : name)
          + ': ' + (isGrey(P, name) ? 'grey, not computed. ' + greyWhy(P, name)
                    : usableSay(ctx, name) + '; ' + svg.querySelectorAll(
                        '.cir-edge-g.on').length + ' edges drawn.');
      }
    });
    svg.addEventListener('mouseleave', () => {
      svg.classList.remove('focus');
      svg.querySelectorAll('.on').forEach((x) => x.classList.remove('on'));
    });
    svg.addEventListener('click', (ev) => {
      const hit = ev.target.closest('[data-key]');
      if (hit && R && R.select) R.select(hit.dataset.key);
      else if (hit) select(ctx, hit.dataset.key);
    });

    if (R) {
      box.appendChild(R.control(ctx, t, edges, total, () => paintRingOnly(ctx)));
      box.appendChild(svg);
      box.appendChild(read);
      box.appendChild(el('div', { class: 'head-actions cir-dl' }, [
        regionErr ? el('span', { class: 'hint',
          text: 'The region colours could not be read (' + regionErr + '), so '
                + 'the nodes are drawn in one colour.' }) : null,
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost sm', text: 'Download SVG',
                       onclick: () => downloadSVG(ctx, svg) }),
        el('button', { class: 'btn ghost sm', text: 'Download PNG',
                       onclick: () => downloadPNG(ctx, svg) }),
      ].filter(Boolean)));
      ctx.svg = svg;
      return;
    }

    const slider = el('input', {
      type: 'range', class: 'cir-thr', min: '0', max: '1', step: '0.01',
      value: String(t.v),
      'aria-label': 'Edge threshold',
      oninput: (e) => {
        pref.thr[ctx.method] = Number(e.target.value);
        paintRingOnly(ctx);
      },
    });
    box.appendChild(el('div', { class: 'cir-thr-row' }, [
      el('span', { class: 'section-label', text: 'Draw edges at or above' }),
      slider,
      el('span', { class: 'cir-thr-v', text: '|' + t.v.toFixed(2) + '|' }),
      el('span', { class: 'hint cir-thr-say', text: edges.length + ' of '
        + total + ' drawn' + (t.auto ? ' \u00b7 the median, until you move it'
                                     : '') }),
      !t.auto ? el('button', { class: 'btn ghost sm', text: 'Median',
        title: 'Back to the median of this panel',
        onclick: () => { delete pref.thr[ctx.method]; paintRingOnly(ctx); } }) : null,
    ].filter(Boolean)));
    box.appendChild(svg);
    box.appendChild(read);
    box.appendChild(el('div', { class: 'head-actions cir-dl' }, [
      regionErr ? el('span', { class: 'hint',
        text: 'The region colours could not be read (' + regionErr + '), so '
              + 'the nodes are drawn in one colour.' }) : null,
      el('div', { class: 'spacer' }),
      el('button', { class: 'btn ghost sm', text: 'Download SVG',
                     onclick: () => downloadSVG(ctx, svg) }),
      el('button', { class: 'btn ghost sm', text: 'Download PNG',
                     onclick: () => downloadPNG(ctx, svg) }),
    ].filter(Boolean)));
    ctx.svg = svg;
  }

  /* Drift draws its rings (the delta, and each side's pooled circuit) with
     this module's `paintRing`, handing in `ring` = { diverging, thr(ctx),
     edges(ctx, t) -> [{key, a, b, c, v, mag?, dash?, attrs?}], total(ctx),
     title(e), read(key), caption(ctx, t, edges, total), control(ctx, t,
     edges, total, repaint), select?(key), nodeNote?(region), hint? }.
     `P` needs region_order, grey and regions. Returns the context;
     `ctx.repaint()` redraws the ring alone. Registered with the region
     colours' late repaint like every circuit ring. */
  function ringInto(box, P, ring, meta) {
    const ctx = { host: box, ringBox: box, P: P, meta: meta || {}, ring: ring,
                  win: ring.win, method: ring.method, sel: null, hover: null };
    for (let i = live.length - 1; i >= 0; i--) {
      if (live[i].host === box || !live[i].host.isConnected) live.splice(i, 1);
    }
    live.push(ctx);
    loadRegions();
    paintRing(ctx);
    ctx.repaint = () => paintRingOnly(ctx);
    return ctx;
  }

  /* The slider repaints the ring and nothing else, and keeps its focus:
     rebuilding the input under a drag ends the drag. */
  function paintRingOnly(ctx) {
    const had = document.activeElement
      && document.activeElement.classList.contains('cir-thr');
    paintRing(ctx);
    if (had) {
      const s = ctx.ringBox.querySelector('.cir-thr');
      if (s) s.focus({ preventScroll: true });
    }
  }

  function fileBase(ctx) {
    const m = ctx.meta, P = ctx.P;
    return String(m.nickname || m.name || (P.source || {}).session_label || 'circuit')
      .replace(/[^\w .\-]+/g, '_').trim().slice(0, 90)
      + ' ' + ctx.win + ' ' + ctx.method;
  }

  function svgText(svg) {
    const s = new XMLSerializer().serializeToString(svg);
    return s.indexOf('xmlns=') >= 0 ? s
      : s.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"');
  }

  function save(blob, name) {
    const a = el('a', { href: URL.createObjectURL(blob), download: name });
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
  }

  function downloadSVG(ctx, svg) {
    save(new Blob([svgText(svg)], { type: 'image/svg+xml' }), fileBase(ctx) + '.svg');
  }

  function downloadPNG(ctx, svg) {
    const img = new Image();
    img.onload = () => {
      const k = 3;
      const c = document.createElement('canvas');
      c.width = RING.w * k; c.height = RING.h * k;
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      c.toBlob((b) => {
        if (b) save(b, fileBase(ctx) + '.png');
        else toast('The PNG could not be made in this browser; the SVG can.', 'warn');
      }, 'image/png');
    };
    img.onerror = () => toast('The PNG could not be made in this browser; '
                              + 'the SVG can.', 'warn');
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgText(svg));
  }

  /* ---------------- what a cell is made of ---------------- */
  function select(ctx, key) {
    ctx.sel = pref.sel = (ctx.sel === key ? null : key);
    ctx.host.querySelectorAll('.cir-val.sel').forEach((n) => n.classList.remove('sel'));
    if (ctx.sel) {
      ctx.host.querySelectorAll('.cir-val[data-key="' + cssEsc(key) + '"]')
        .forEach((n) => n.classList.add('sel'));
    }
    if (ctx.svg) {
      ctx.svg.querySelectorAll('.cir-edge').forEach((n) => {
        n.classList.toggle('sel', n.dataset.key === ctx.sel);
      });
    }
    paintDetail(ctx);
  }

  function cssEsc(v) {
    return (window.CSS && CSS.escape) ? CSS.escape(String(v))
      : String(v).replace(/["\\]/g, '\\$&');
  }

  function paintDetail(ctx) {
    const box = ctx.detail;
    if (!box) return;
    box.innerHTML = '';
    const key = ctx.sel;
    const c = key ? cellsOf(ctx)[key] : null;
    if (!c) {
      box.appendChild(el('p', { class: 'hint',
        text: key ? 'That region pair has no value in ' + say(ctx.win)
                    + ' for this method.'
                  : 'Click a cell or an edge to see the cue pairs its mean is '
                    + 'made of.' }));
      return;
    }
    const P = ctx.P;
    const [a, b] = key.split('|');
    const byPid = {};
    (c.values || []).forEach((x) => { byPid[x.pair_id] = x.v; });
    const vs = (c.values || []).map((x) => x.v);
    let lo = Math.min.apply(null, vs.concat([c.mean]));
    let hi = Math.max.apply(null, vs.concat([c.mean]));
    if (ctx.method !== 'coherence') { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
    if (hi - lo < 1e-9) { lo -= 0.05; hi += 0.05; }
    const W = 420, H = 34, pad = 12;
    const X = (v) => pad + (W - 2 * pad) * (v - lo) / (hi - lo);
    const strip = el('svg', { class: 'cir-strip', viewBox: '0 0 ' + W + ' ' + H,
                              role: 'img', 'aria-label': 'The values behind the mean' });
    strip.appendChild(el('line', { class: 'cir-strip-axis', x1: String(pad), x2: String(W - pad),
                                   y1: String(H / 2), y2: String(H / 2) }));
    if (lo < 0 && hi > 0) {
      strip.appendChild(el('line', { class: 'cir-strip-zero', x1: X(0).toFixed(1),
                                     x2: X(0).toFixed(1), y1: '6', y2: String(H - 6) }));
    }
    strip.appendChild(el('line', { class: 'cir-strip-mean', x1: X(c.mean).toFixed(1),
                                   x2: X(c.mean).toFixed(1), y1: '3', y2: String(H - 3) },
                         [el('title', { text: 'mean ' + fmt(c.mean, 4) })]));
    for (const x of (c.values || [])) {
      strip.appendChild(el('circle', { class: 'cir-strip-dot', cx: X(x.v).toFixed(1),
                                       cy: String(H / 2), r: '4' },
        [el('title', { text: pairLabel(P, x.pair_id) + ': ' + fmt(x.v, 4) })]));
    }
    const rows = (P.pairs || []).map((p) => {
      const has = Object.prototype.hasOwnProperty.call(byPid, p.pair_id);
      return el('div', { class: 'cir-dv' + (has ? '' : ' none'),
                         'data-pair': String(p.pair_id) }, [
        el('span', { class: 'cir-dv-id', text: 'pair ' + p.pair_id }),
        el('span', { class: 'cir-dv-t', text: p.opener_t != null
          ? Number(p.opener_t).toFixed(1) + ' s' : '' }),
        el('span', { class: 'cir-dv-v', text: has ? fmt(byPid[p.pair_id], 4)
          : 'not usable in ' + say(ctx.win) }),
      ]);
    });
    box.appendChild(el('div', { class: 'cir-detail-in' }, [
      el('div', { class: 'cir-detail-head' }, [
        el('strong', { text: a + ' \u00d7 ' + b }),
        el('span', { class: 'hint', text: (METHOD_NAME[ctx.method] || ctx.method)
          + ' in ' + say(ctx.win) }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', title: 'Close',
          onclick: () => select(ctx, key),
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('p', { class: 'cir-detail-say', text: 'mean ' + fmt(c.mean, 4)
        + (c.sd != null ? ' \u00b7 SD ' + fmt(c.sd, 4) : ' \u00b7 no SD from one value')
        + ' \u00b7 n = ' + c.n + ' of ' + (c.of != null ? c.of : P.n_pairs)
        + ' cue pairs' + (c.warn ? ' \u00b7 ' + c.warn : '') }),
      strip,
      el('div', { class: 'cir-dvs' }, rows),
      el('p', { class: 'hint', text: 'No test is made inside a circuit: these '
        + 'are the values, and the mean and SD are made from them. A pair '
        + 'with no value had no usable wire in one of the two regions in '
        + 'this window. The statistics live in Drift.' }),
    ]));
  }

  /* ==================================================================
     Many at once -- Spark's batch shape, for circuits.
     ================================================================== */
  const bulk = {
    want: {}, cues: 'all', kind: 'state', where: 'local',
    plan: null, planErr: null, planSeq: 0, planT: null,
    job: null, stop: null, open: {}, shown: {},
  };

  function batchRows() {
    return (st.rows || []).filter((r) => r.banked);
  }

  function renderBatch() {
    const host = document.getElementById('cirBatch');
    if (!host) return;
    host.innerHTML = '';
    const card = el('div', { class: 'card arc-batch cir-batch' }, [
      el('div', { class: 'section-label', text: 'Make many circuits' }),
    ]);
    host.appendChild(card);
    if (st.rowsErr) {
      card.appendChild(routeMissing(st.rowsErr,
        'The list of recordings a circuit can be made from could not be read.'));
      return;
    }
    if (st.rows === null) {
      const bones = el('div', { class: 'arc-batch-rows' });
      card.appendChild(bones);
      BARRY.skeleton.into(bones, 'row', 8);
      return;
    }
    const rows = batchRows();
    if (!rows.length) {
      card.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'No DEWEY recording has banked cue pairs yet. File '
                        + 'some in Spark, step 1, first.' }),
      ]));
      return;
    }
    const running = !!bulk.job;
    card.appendChild(el('div', { class: 'cir-batch-opts' }, [
      BARRY.ui.field({
        label: 'Kind',
        control: el('div', { class: 'seg cir-bkinds' }, ['state', 'transition'].map((k) =>
          el('button', {
            class: bulk.kind === k ? 'active' : '', 'data-kind': k,
            disabled: running ? 'disabled' : null, text: KIND_SAY[k],
            onclick: () => { bulk.kind = k; bulk.plan = null; renderBatch(); askBatchPlan(); },
          }))),
        hint: bulk.kind === 'transition'
          ? 'A recording whose transition clipping nobody has measured is '
            + 'blocked, and the plan says so.'
          : 'Four windows per cue pair.',
      }),
      BARRY.ui.field({
        label: 'Cue pairings',
        control: cueChooser(rows, running),
        hint: 'Each recording\u2019s own pairings, one circuit each. They '
              + 'are never pooled.',
      }),
    ]));
    card.appendChild(whereTabs({}, true));
    card.appendChild(batchPlanLine());
    card.appendChild(batchBar(rows));
    const tbl = el('div', { class: 'arc-batch-rows cir-batch-rows' });
    for (const r of rows) tbl.appendChild(batchRow(r));
    card.appendChild(tbl);
    if (bulk.job) { card.appendChild(batchJobCard()); paintBatchJob(); }
  }

  function cueChooser(rows, running) {
    const all = {};
    for (const r of rows) {
      if (!bulk.want[r.gid]) continue;
      for (const c of (r.cue_types || [])) all[c.cue_type] = c.cue_label;
    }
    const ids = Object.keys(all).sort();
    const isAll = bulk.cues === 'all';
    const box = el('div', { class: 'cir-cuepick' }, [
      el('button', {
        class: 'pill' + (isAll ? ' active' : ''),
        disabled: running ? 'disabled' : null,
        text: 'Every pairing each one has',
        onclick: () => { bulk.cues = 'all'; bulk.plan = null; renderBatch(); askBatchPlan(); },
      }),
    ]);
    for (const id of ids) {
      const on = !isAll && bulk.cues.indexOf(id) >= 0;
      box.appendChild(el('button', {
        class: 'pill' + (on ? ' active' : ''), 'data-cue': id,
        disabled: running ? 'disabled' : null, text: all[id],
        onclick: () => {
          let list = isAll ? [] : bulk.cues.slice();
          list = on ? list.filter((x) => x !== id) : list.concat([id]);
          bulk.cues = list.length ? list : 'all';
          bulk.plan = null; renderBatch(); askBatchPlan();
        },
      }));
    }
    if (!ids.length) {
      box.appendChild(el('span', { class: 'hint',
                                   text: 'Tick a recording to see its pairings.' }));
    }
    return box;
  }

  function batchWant() {
    return batchRows().filter((r) => bulk.want[r.gid]).map((r) => r.gid);
  }

  function askBatchPlan() {
    clearTimeout(bulk.planT);
    const gids = batchWant();
    if (!gids.length) { bulk.plan = null; bulk.planErr = null; paintBatchHead(); return; }
    bulk.planT = setTimeout(async () => {
      const seq = ++bulk.planSeq;
      try {
        const got = await apiPost('/api/arc/circuit/batch/plan', {
          gids: gids, cue_types: bulk.cues, kind: bulk.kind,
          params: Object.assign({}, st.params || {}), where: bulk.where,
        });
        if (seq !== bulk.planSeq) return;
        bulk.plan = got; bulk.planErr = null;
      } catch (e) {
        if (seq !== bulk.planSeq) return;
        bulk.plan = null; bulk.planErr = e.message;
        if (!/older code/.test(e.message || '')) {
          reportClientError('circuit.batch.plan', e.message, e.stack);
        }
      }
      paintBatchHead();
      paintBatchRows();
    }, 350);
  }

  /* Cost, before it is spent: to do, already done at these parameters,
     blocked and why, and the total time -- the server's plan, stated. */
  function batchPlanLine() {
    const n = batchWant().length;
    const box = el('div', { class: 'arc-batch-cost cir-bplan' });
    if (!n) {
      box.appendChild(el('strong', { text: 'Nothing is ticked yet' }));
      box.appendChild(el('p', { class: 'hint arc-batch-say',
        text: 'Tick the recordings to make circuits for. Nothing runs until '
              + 'you press the button, and what it will cost appears here '
              + 'first.' }));
      return box;
    }
    if (bulk.planErr) {
      box.appendChild(/older code/.test(bulk.planErr)
        ? routeMissing(bulk.planErr, 'The batch could not be planned, so '
                                     + 'nothing can be run from here yet.')
        : el('p', { class: 'arc-ov-refused', text: bulk.planErr }));
      return box;
    }
    const p = bulk.plan;
    if (!p) {
      box.appendChild(loader('Planning the batch',
        plural(n, 'recording') + ': what is done, what is blocked, what it costs'));
      return box;
    }
    const todo = p.todo || [], already = p.already || [], blocked = p.blocked || [];
    box.appendChild(el('strong', { text: p.sentence
      || (todo.length + ' to make, about ' + secs(p.total_s)) }));
    box.appendChild(el('div', { class: 'cir-bplan-grid' }, [
      el('span', { class: 'cir-bp-k', text: 'to make' }),
      el('span', { class: 'cir-bp-v', text: todo.length
        ? plural(todo.length, 'circuit') + ', about ' + secs(p.total_s || 0)
          + (bulk.where === 'vacc' ? ' of computing, plus the queue' : ' here')
        : 'nothing' }),
      el('span', { class: 'cir-bp-k', text: 'already made' }),
      el('span', { class: 'cir-bp-v', text: already.length
        ? plural(already.length, 'circuit') + ' at these parameters, skipped'
        : 'none at these parameters' }),
      el('span', { class: 'cir-bp-k', text: 'blocked' }),
      el('span', { class: 'cir-bp-v', text: blocked.length
        ? blocked.map((b) => labelOf(b.gid) + ' \u2014 ' + b.why).join('; ')
        : 'none' }),
    ]));
    box.appendChild(el('p', { class: 'hint arc-batch-say',
      text: 'One set of parameters for the whole batch: '
            + (st.params ? 'the ones set in One recording at a time.'
                         : 'the defaults.')
            + ' Each circuit is filed the moment it lands and can be opened '
            + 'below while the rest are still running.' }));
    return box;
  }

  function labelOf(gid) {
    const r = rowOf(gid);
    return r ? 'J' + r.mouse + ' ' + (r.phase || '') + (r.phase_n || '') : gid;
  }

  function batchBar(rows) {
    const running = !!bulk.job;
    const fresh = rows.filter((r) => !(r.circuits || []).some((c) => c.kind === bulk.kind));
    const todo = bulk.plan ? (bulk.plan.todo || []).length : 0;
    const bar = el('div', { class: 'arc-batch-bar cir-bbar' }, [
      el('button', { class: 'btn ghost sm', disabled: running ? 'disabled' : null,
        text: 'Every banked recording',
        onclick: () => { rows.forEach((r) => { bulk.want[r.gid] = true; });
                         bulk.plan = null; renderBatch(); askBatchPlan(); } }),
      el('button', { class: 'btn ghost sm', disabled: running ? 'disabled' : null,
        text: 'Clear',
        onclick: () => { bulk.want = {}; bulk.plan = null; renderBatch(); } }),
      el('button', { class: 'btn ghost sm',
        disabled: (running || !fresh.length) ? 'disabled' : null,
        text: 'Only the ' + fresh.length + ' with no ' + bulk.kind + ' circuit',
        onclick: () => { fresh.forEach((r) => { bulk.want[r.gid] = true; });
                         bulk.plan = null; renderBatch(); askBatchPlan(); } }),
      el('span', { class: 'hint arc-batch-count',
                   text: batchWant().length + ' of ' + rows.length + ' ticked' }),
      el('div', { class: 'spacer' }),
    ]);
    if (running) {
      bar.appendChild(el('button', { class: 'btn ghost sm', text: 'Stop',
        title: 'Stops the batch. Circuits that have landed are filed and stay.',
        onclick: async () => {
          try { await apiPost('/api/cfc/job/' + encodeURIComponent(bulk.job.id)
                              + '/cancel', {}); }
          catch (e) { toast('Could not stop it: ' + e.message, 'err', 6000); }
        } }));
    } else {
      bar.appendChild(el('button', { class: 'btn cir-bgo',
        disabled: todo ? null : 'disabled',
        title: todo ? '' : (batchWant().length ? 'Nothing in the plan is left to make.'
                                              : 'Tick a recording first.'),
        text: 'Make ' + plural(todo, 'circuit')
              + (bulk.where === 'vacc' ? ' on VACC' : ''),
        onclick: runBatch }));
    }
    return bar;
  }

  function planFor(gid) {
    const p = bulk.plan;
    if (!p) return null;
    return {
      todo: (p.todo || []).filter((x) => x.gid === gid),
      already: (p.already || []).filter((x) => x.gid === gid),
      blocked: (p.blocked || []).filter((x) => x.gid === gid),
    };
  }

  function batchRow(r) {
    const running = !!bulk.job;
    const pf = planFor(r.gid);
    let status = '';
    if (bulk.want[r.gid] && pf) {
      const bits = [];
      if (pf.todo.length) bits.push(pf.todo.length + ' to make');
      if (pf.already.length) bits.push(pf.already.length + ' already made');
      if (pf.blocked.length) bits.push('blocked: ' + pf.blocked.map((b) => b.why).join('; '));
      status = bits.join(' \u00b7 ');
    }
    return el('div', {
      class: 'arc-batch-row cir-brow' + (bulk.want[r.gid] ? ' on' : '')
             + (pf && pf.blocked.length && !pf.todo.length ? ' skipped' : ''),
      'data-gid': r.gid,
    }, [
      el('input', { type: 'checkbox', disabled: running ? 'disabled' : null,
        checked: bulk.want[r.gid] ? 'checked' : null, title: r.label,
        onchange: (e) => {
          if (e.target.checked) bulk.want[r.gid] = true; else delete bulk.want[r.gid];
          bulk.plan = null;
          paintBatchHead();
          const row = e.target.closest('.cir-brow');
          if (row) row.classList.toggle('on', !!bulk.want[r.gid]);
          askBatchPlan();
        } }),
      el('span', { class: 'nm', text: 'J' + r.mouse }),
      el('span', { class: 'ss', text: (r.phase || '') + (r.phase_n || '') }),
      el('span', { class: 'dt', text: r.date || '' }),
      el('span', { class: 'bk', text: plural((r.circuits || []).length, 'circuit'),
        title: (r.circuits || []).map((c) => (c.nickname || c.name)
                                        + ' (v' + c.version + ')').join('\n') }),
      el('span', { class: 'st', text: status || (r.cue_types || []).map(
        (c) => c.cue_label + ' \u00d7' + c.n_pairs).join(' \u00b7 ') }),
    ]);
  }

  function paintBatchHead() {
    const card = document.querySelector('#cirBatch .cir-batch');
    if (!card) return;
    const swap = (sel, node) => {
      const was = card.querySelector(sel);
      if (was) card.replaceChild(node, was);
    };
    swap('.cir-bplan', batchPlanLine());
    swap('.cir-bbar', batchBar(batchRows()));
    const opts = card.querySelector('.cir-cuepick');
    if (opts) opts.parentNode.replaceChild(cueChooser(batchRows(), !!bulk.job), opts);
  }

  /* The rows, rebuilt one at a time so the scroll and the ticks stay. */
  function paintBatchRows() {
    for (const r of batchRows()) {
      const row = document.querySelector('.cir-brow[data-gid="' + cssEsc(r.gid) + '"]');
      if (row && row.parentNode) row.parentNode.replaceChild(batchRow(r), row);
    }
  }

  async function runBatch() {
    if (bulk.job) return;
    const gids = batchWant();
    if (!gids.length || !bulk.plan || !(bulk.plan.todo || []).length) return;
    try {
      const got = await apiPost('/api/arc/circuit/batch/run', {
        gids: gids, cue_types: bulk.cues, kind: bulk.kind,
        params: Object.assign({}, st.params || {}), where: bulk.where,
      });
      bulk.job = { id: got.job, status: 'running', members: null };
      bulk.open = {}; bulk.shown = {};
      log('arc.circuit.batch', { n: gids.length, kind: bulk.kind, where: bulk.where,
                                 todo: (bulk.plan.todo || []).length });
      if (bulk.where === 'vacc' && BARRY.vaccBusy) BARRY.vaccBusy.start();
      renderBatch();
      bulk.stop = follow(got.job, (job) => {
        bulk.job = job;
        paintBatchJob();
      }, batchLanded);
    } catch (e) {
      if (!/older code/.test(e.message || '')) {
        reportClientError('circuit.batch.run', e.message, e.stack);
      }
      toast('The batch did not start: ' + e.message, 'err', 9000);
    }
  }

  async function batchLanded(job) {
        if (bulk.where === 'vacc' && BARRY.vaccBusy) BARRY.vaccBusy.stop();
        const ms = job.members || [];
        const ok = ms.filter((m) => m.status === 'done').length;
        const bad = ms.filter((m) => m.status === 'failed').length;
        toast(job.status === 'done'
              ? ok + ' of ' + ms.length + ' circuits made'
                + (bad ? ', ' + bad + ' failed' : '') + '.'
              : job.status === 'canceled'
                ? 'The batch was stopped; ' + ok + ' circuits landed and are filed.'
                : 'The batch failed: ' + (job.error || 'no reason was given.'),
              job.status === 'done' && !bad ? 'ok' : (job.status === 'failed' ? 'err' : 'warn'),
              9000);
        bulk.last = job;
        bulk.job = null; bulk.stop = null;
        await loadRows();
        bulk.plan = null;
        if (st.mode === 'many') { renderBatch(); askBatchPlan(); }
        if (BARRY.artifacts && BARRY.artifacts.reload) {
          try { BARRY.artifacts.reload(); } catch (e) { /* not shown */ }
        }
  }

  function batchJobCard() {
    return el('div', { class: 'card comod-run cir-bjob' }, [
      el('div', { class: 'comod-run-head' }, [
        el('strong', { text: 'Making the circuits' }),
        el('span', { id: 'cirBEta', class: 'comod-eta' }),
      ]),
      el('div', { class: 'comod-total' }, [
        el('div', { class: 'comod-bar' }, [
          el('div', { id: 'cirBFill', class: 'comod-bar-fill' })]),
      ]),
      el('div', { id: 'cirBMembers', class: 'cir-members' }),
      el('p', { class: 'hint quiet', text: 'You can leave this view. Each '
        + 'circuit is filed as it lands, and a toast says when the batch is '
        + 'done.' }),
    ]);
  }

  function memberKey(m) {
    if (m.gid && m.cue_type) return m.gid + '|' + m.cue_type;
    return String(m.id);
  }

  function paintBatchJob() {
    const job = bulk.job;
    const box = document.getElementById('cirBMembers');
    if (!job || !box) return;
    const ms = job.members || [];
    const landedN = ms.filter((m) => ['done', 'failed', 'skipped'].indexOf(m.status) >= 0).length;
    const fill = document.getElementById('cirBFill');
    // A bar that never goes backwards: members only ever land.
    if (fill) fill.style.width = (ms.length ? 100 * landedN / ms.length : 0).toFixed(1) + '%';
    const eta = document.getElementById('cirBEta');
    if (eta) eta.textContent = landedN + ' of ' + ms.length + ' landed \u00b7 '
      + secs(job.elapsed || 0) + ' so far';
    for (const m of ms) {
      const k = memberKey(m);
      let row = box.querySelector('[data-member="' + cssEsc(k) + '"]');
      const status = m.status || 'waiting';
      const sig = status + '|' + (m.step || '') + '|' + (m.error || '');
      if (row && row.__sig === sig) continue;
      const fresh = memberRow(m, k, status);
      fresh.__sig = sig;
      if (row) box.replaceChild(fresh, row); else box.appendChild(fresh);
    }
  }

  function memberRow(m, k, status) {
    const head = [
      el('span', { class: 'cir-m-id', text: m.label || (m.gid ? labelOf(m.gid)
        + (m.cue_type ? ' \u00b7 ' + m.cue_type : '') : k) }),
      el('span', { class: 'cir-m-st ' + status, text: (MEMBER_SAY[status] || status)
        + (m.step && status !== 'waiting' && status !== 'pending' ? ' \u00b7 ' + m.step : '')
        + (status === 'running' && m.of ? ' \u00b7 ' + (m.done || 0) + ' of ' + m.of + ' pairs' : '')
        + (m.error ? ': ' + m.error : '') }),
    ];
    if (status !== 'done') {
      return el('div', { class: 'cir-m ' + status, 'data-member': k }, head);
    }
    const inner = el('div', { class: 'cir-m-view' });
    const d = el('details', {
      class: 'cir-m ' + status, 'data-member': k,
      open: bulk.open[k] ? 'open' : null,
    }, [el('summary', {}, head), inner]);
    const fill = () => {
      if (inner.__filled) return;
      inner.__filled = true;
      inner.appendChild(loader('Reading the circuit', 'from the artifact store'));
      memberPayload(m).then((got) => {
        inner.innerHTML = '';
        if (!got) {
          inner.appendChild(el('p', { class: 'hint',
            text: 'It landed, but the circuit could not be found among the '
                  + 'artifacts yet. Open it from Results once the list '
                  + 'refreshes.' }));
          return;
        }
        renderCircuit(inner, got.payload, got.meta);
      }).catch((e) => {
        inner.innerHTML = '';
        inner.appendChild(el('p', { class: 'hint', text: e.message }));
      });
    };
    d.addEventListener('toggle', () => {
      if (d.open) { bulk.open[k] = true; fill(); } else delete bulk.open[k];
    });
    if (bulk.open[k]) fill();
    return d;
  }

  /* A landed batch member's circuit: by its artifact id when the member
     row carries one, otherwise found by subject among the recording's
     circuits (the row is scalars only, so it may not). */
  async function memberPayload(m) {
    let id = m.artifact_id || null;
    // The batch's member id is "<gid>|<cue type>".
    const [gid, cue] = m.gid ? [m.gid, m.cue_type] : String(m.id || '').split('|');
    if (!id && gid && BARRY.artifacts && BARRY.artifacts.list) {
      const list = await BARRY.artifacts.list({ kind: 'circuit', gid: gid });
      const hit = list.find((a) => (a.subject || {}).cue_type === cue
                                && (a.subject || {}).window_kind === bulk.kind);
      id = hit && hit.id;
    }
    if (!id) return null;
    const got = await BARRY.artifacts.payload(id, m.version_id || null);
    return { payload: got.payload,
             meta: { artifact_id: id, version: got.version, digest: got.digest,
                     version_id: got.version_id,
                     name: m.name || m.label, nickname: m.nickname } };
  }

  /* ==================================================================
     Results' viewer. The SAME renderer the panel uses. Registered now if
     the registry is here (artifacts.js loads first), and the moment it
     appears if it is not.
     ================================================================== */
  const VIEWER = {
    title: 'Circuits',
    icon: 'circuit',
    summary: (rec) => {
      const cur = rec.current || {};
      const n = cur.n_summary || {};
      const s = rec.subject || {};
      const bits = [];
      if (n.n_pairs != null) bits.push(plural(n.n_pairs, 'cue pair'));
      else if (s.cue_type) bits.push(s.cue_type);
      if (n.n_grey) bits.push(n.n_grey + ' grey');
      if (n.n_cells != null) {
        bits.push(n.n_cells + ' cells' + (n.n_warn ? ', ' + n.n_warn + ' warn' : ''));
      }
      if (s.window_kind) bits.push(s.window_kind);
      return bits.join(' \u00b7 ');
    },
    render: (host, rec, payload, version) => {
      loadRegions();
      renderCircuit(host, payload, {
        artifact_id: rec && rec.id, name: rec && rec.name,
        nickname: rec && rec.nickname,
        version: version ? version.v : null, version_id: version ? version.id : null,
        digest: version ? version.digest : null, inResults: true,
      });
    },
  };

  function registerViewer() {
    if (!BARRY.artifacts || typeof BARRY.artifacts.register !== 'function') {
      return false;
    }
    try {
      BARRY.artifacts.register('circuit', VIEWER);
    } catch (e) {
      reportClientError('circuit.register', e.message, e.stack);
    }
    return true;
  }
  if (!registerViewer()) {
    let tries = 0;
    const t = setInterval(() => {
      tries += 1;
      if (registerViewer() || tries > 300) clearInterval(t);
    }, 200);
  }

  return {
    paint,
    render: renderCircuit,
    ring: RING,
    /* For Drift (web/js/drift.js): the same ring, fed a delta. */
    ringInto: ringInto,
    loadRegions: loadRegions,
    metaOf: (region) => metaOf(region),
    pick: pick,
    choose: choose,
    run: run,
    /* A recorded payload, drawn into the panel as if it had just been
       opened, for `web/_dev/circuit.html` when the routes are not there.
       Kept in the panel's state, so the ToolKit's second render keeps it. */
    _show: (payload, meta) => {
      st.gid = null;
      st.shown = { payload: payload, meta: meta || {} };
      st.shownErr = null;
      renderMain();
      return !!document.getElementById('cirMain');
    },
    _pref: pref,
    get state() {
      return { mode: st.mode, gid: st.gid, cue: st.cue, kind: st.kind,
               where: st.where, plan: st.plan, params: Object.assign({}, st.params || {}),
               paramErr: st.paramErr, job: st.job, shown: st.shown,
               rowsErr: st.rowsErr, rows: st.rows };
    },
    get regions() { return regionMeta; },
    batch: {
      get plan() { return bulk.plan; },
      get job() { return bulk.job; },
      want: (gid, on) => {
        if (on === false) delete bulk.want[gid]; else bulk.want[gid] = true;
        bulk.plan = null; renderBatch(); askBatchPlan();
      },
      run: runBatch,
    },
    viewer: VIEWER,
  };
})();

window.barryCircuit = BARRY.circuit;
