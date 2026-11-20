/* ==========================================================================
   extraction_er2.js -- EXTRACTION ROOM 2.0, the Extraction Room's models tab
   (web/extraction.html; asked 2026-11-18).

   "Develop a neural network that will basically take in all the variety of
   parameters we have ... freezing the results at the most optimization, DS1,
   DS2, and DS3 ... see if you can develop any model that is reliably able to
   tell apart PTEN from CTL ... or guess the percentage ... Once we have that
   model ... crack it open to see what variables are actually responsible."

   On show (backend/er2routes.py and backend/er2run.py work out everything):
     the frozen inputs    each amber bundle: events, features by family, mice
     a new run            targets x views x models, here or on the VACC
     the runs             progress; slurm's word for VACC runs
     the leaderboard      per target: every model's held-out score against the
                          bar and against the nuisance-only baseline
     a model, opened      its held-out calls mouse by mouse; what carried it
     MOST IMPORTANT       per target, consolidated over the models that
                          reached the bar (or the three best)
   Its state (Q) lives here so it survives the room's re-renders; only this
   tab's element is ever redrawn.
   ========================================================================== */
'use strict';

(function () {
  const ROOM = (window.erRoom = window.erRoom || {});
  ROOM.ext = ROOM.ext || {};
  const K = () => (window.erRoom || {}).kit;

  const TARGET_WORD = {
    pten_vs_ctl: 'PTEN against control', ko_pct: 'Knockout % (a number)', low_vs_high: 'Low (under 10%) against high (15%+) knockout',
    ied3: 'Control / IED− / IED+', iedpos_vs_iedneg: 'IED+ against IED−',
  };
  const VIEW_WORD = {
    core: 'Waveform and depth measures + DS type', context: '+ event context (intervals, time, detector peak, theta)',
    filters: '+ the same measures under six other filters', before_after: '+ power before and after the DS',
    events_all: 'Every per-event feature', mouse: 'Per-mouse tables only (battery numbers)',
    everything: 'Everything, nuisance values included', nuisance: 'Nuisance only: placement, year, event count (baseline)',
  };
  const MODEL_WORD = {
    linear: 'Linear (L2)', lasso: 'Lasso (L1)', forest: 'Random forest', boosting: 'Gradient boosting', mlp: 'Small neural net (pooled)',
    deepsets: 'Set network (deep sets)', attention: 'Set network (attention)',
  };
  const SCORE_WORD = { binary: 'AUC', multiclass: 'macro AUC', regression: 'rank correlation' };

  const Q = { info: null, err: null, run: null, rid: null, open: null, task: null, sel: null, where: 'local', timer: null, root: null };

  const fmt = (v, d) => (v == null || !isFinite(v) ? '—' : Number(v).toFixed(d == null ? 2 : d));

  async function loadInfo() {
    try {
      Q.info = await K().api('/api/er2');
      Q.err = null;
      if (!Q.sel) {
        Q.sel = { targets: new Set(Q.info.targets), views: new Set(Q.info.views), models: new Set(Q.info.models) };
      }
      if (!Q.rid && Q.info.runs.length) Q.rid = Q.info.runs[0].rid;
    } catch (e) { Q.err = e.message; }
    fill();
    if (Q.rid) loadRun(Q.rid);
  }

  async function loadRun(rid) {
    try {
      const j = await K().api('/api/er2/run/' + rid);
      Q.run = j.run;
      Q.rid = rid;
      Q.err = null;
    } catch (e) { Q.err = e.message; }
    fill();
    clearTimeout(Q.timer);
    if (Q.run && Q.run.running_here) Q.timer = setTimeout(() => { if (document.getElementById('er2Root')) loadRun(rid); }, 5000);
  }

  async function act(url, body) {
    try {
      const j = await K().post(url, body || {});
      if (j.run) { Q.run = j.run; Q.rid = j.run.rid; }
      Q.err = null;
    } catch (e) { Q.err = e.message; }
    await loadInfo();
  }

  /* ---------- parts ---------- */
  function intro() {
    const el = K().el;
    return el('div', { class: 'card' }, [
      el('h3', { text: 'Extraction Room 2.0 · can a model tell the groups apart from the dentate spikes alone?' }),
      el('p', { class: 'lede', text: 'Every event of the Halo set, frozen with its winning classifier’s DS1 / DS2 / DS3 call, everything measured about it, '
        + 'and per-mouse tables. Models learn from each mouse’s whole cloud of events and make one call per mouse. A mouse is only ever '
        + 'called by models that never saw any of its events: PTEN against control leaves one control and one PTEN mouse out at a time; '
        + 'every other target leaves one mouse out.' }),
      el('p', { class: 'small muted', text: 'Read every score against two things on the table: the bar (AUC 0.80, or a rank correlation of 0.70 for the '
        + 'knockout %), and the nuisance-only baseline — the same kind of model given only where the probe sat, the year and the event count. '
        + 'With 16 mice a score is 16 calls, and the best of many models looks good by chance.' }),
    ]);
  }

  function bundles() {
    const { el } = K();
    const B = (Q.info && Q.info.bundles) || [];
    const kids = [el('h3', { text: 'The frozen inputs (amber)' })];
    if (!B.length) kids.push(el('p', { class: 'empty', text: 'No bundle yet. Freeze one from the battery folder below.' }));
    for (const b of B) {
      const fam = Object.entries(b.event_families).map(([k, v]) => k + ' ' + v).join(' · ');
      kids.push(el('p', {}, [el('b', { text: 'v' + b.version + '  ' }),
        el('span', { text: b.n_events + ' events of ' + b.n_mice + ' mice · ' + b.n_event_features + ' per-event features (' + fam + ') · '
          + b.n_mouse_features + ' per-mouse features · ' + b.classifier + ' · made ' + b.made })]));
    }
    const src = el('input', { type: 'text', class: 'numin', style: 'width: 100%; max-width: 640px', value: (Q.info && Q.info.source) || '',
      placeholder: 'The battery folder (holds data/ds_v6.pkl)' });
    const st = (Q.info && Q.info.amber) || {};
    kids.push(el('div', { class: 'acts-row' }, [src, el('button', { class: 'btn', text: st.state === 'running' ? 'Freezing…' : 'Freeze a new bundle',
      disabled: st.state === 'running', onclick: async () => { await act('/api/er2/amber', { source: src.value }); pollAmber(); } })]));
    if (st.error) kids.push(el('p', { class: 'err', text: st.error }));
    return el('div', { class: 'card' }, kids);
  }

  async function pollAmber() {
    try {
      const j = await K().api('/api/er2/amber/status');
      if (j.state === 'running') { setTimeout(pollAmber, 4000); return; }
    } catch (e) { /* shown by loadInfo */ }
    loadInfo();
  }

  function picker(title, key, words) {
    const { el } = K();
    const all = Q.info[key];
    return el('div', { class: 'ctl' }, [el('div', { class: 'lab', text: title }),
      el('div', { class: 'seg' }, all.map((x) => el('button', {
        'aria-pressed': String(Q.sel[key].has(x)), title: words[x] || x, text: words[x] || x,
        onclick: () => { if (Q.sel[key].has(x)) Q.sel[key].delete(x); else Q.sel[key].add(x); fill(); } })))]);
  }

  function newRun() {
    const { el } = K();
    if (!Q.info || !(Q.info.bundles || []).length) return el('div');
    const nets = new Set(['deepsets', 'attention']);
    let n = 0;
    for (const t of Q.sel.targets) for (const v of Q.sel.views) for (const m of Q.sel.models) if (!(nets.has(m) && (v === 'mouse' || v === 'nuisance'))) n++;
    const shuf = el('input', { type: 'number', class: 'numin', min: '0', max: '200', value: '0', style: 'width: 70px' });
    const note = el('input', { type: 'text', class: 'numin', placeholder: 'A note for this run (optional)', style: 'width: 320px' });
    return el('div', { class: 'card' }, [
      el('h3', { text: 'A new run' }),
      picker('Targets', 'targets', TARGET_WORD), picker('Inputs (views)', 'views', VIEW_WORD), picker('Models', 'models', MODEL_WORD),
      el('div', { class: 'ctl' }, [el('div', { class: 'lab', text: 'Where' }), el('div', { class: 'seg' }, [
        el('button', { 'aria-pressed': String(Q.where === 'local'), text: 'This computer', onclick: () => { Q.where = 'local'; fill(); } }),
        el('button', { 'aria-pressed': String(Q.where === 'vacc'), text: 'The VACC', onclick: () => { Q.where = 'vacc'; fill(); } })])]),
      el('div', { class: 'ctl' }, [el('div', { class: 'lab', text: 'Chance check' }), shuf,
        el('span', { class: 'small muted', text: ' times each model is re-run with the mouse labels shuffled (0 = off; shown, never used to pass a model)' })]),
      el('div', { class: 'acts-row' }, [note, el('button', { class: 'btn primary', text: 'Start ' + n + ' task' + (n === 1 ? '' : 's')
        + (Q.where === 'vacc' ? ' on the VACC' : ' here'), disabled: !n,
        onclick: () => act('/api/er2/run', { targets: [...Q.sel.targets], views: [...Q.sel.views], models: [...Q.sel.models], where: Q.where,
          n_shuffle: Number(shuf.value) || 0, note: note.value }) })]),
    ]);
  }

  function runsCard() {
    const { el } = K();
    const R = (Q.info && Q.info.runs) || [];
    if (!R.length) return el('div');
    const r = Q.run;
    const kids = [el('h3', { text: 'Runs' }), el('div', { class: 'seg' }, R.map((x) => el('button', {
      'aria-pressed': String(x.rid === Q.rid), text: x.rid + ' · ' + x.where + ' · ' + x.n + ' tasks' + (x.note ? ' · ' + x.note : ''),
      onclick: () => { Q.open = null; Q.task = null; loadRun(x.rid); } })))];
    if (r) {
      kids.push(el('p', {}, [el('b', { text: r.rid + ': ' }), el('span', { text: r.answered + ' of ' + r.n + ' tasks answered · ' + r.state
        + (r.where === 'vacc' ? ' · on the VACC' : ' · on this computer') + ' · amber v' + r.amber_version + ' · made ' + r.made })]));
      const acts = [];
      if (r.where === 'vacc') acts.push(el('button', { class: 'btn', text: 'Ask the VACC and bring answers home', onclick: () => act('/api/er2/run/' + r.rid + '/refresh') }));
      if (r.running_here) acts.push(el('button', { class: 'btn', text: 'Stop', onclick: () => act('/api/er2/run/' + r.rid + '/stop') }));
      if (r.where === 'local' && !r.running_here && r.answered < r.n) acts.push(el('button', { class: 'btn', text: 'Carry on here', onclick: () => act('/api/er2/run/' + r.rid + '/resume') }));
      if (r.where === 'vacc' && r.state !== 'cancelled' && r.answered < r.n) acts.push(el('button', { class: 'btn', text: 'Cancel on the VACC', onclick: () => act('/api/er2/run/' + r.rid + '/stop') }));
      if (acts.length) kids.push(el('div', { class: 'acts-row' }, acts));
      if (r.artifact) kids.push(el('p', { class: 'small muted', text: 'Filed as artifact ' + r.artifact.id + ' v' + r.artifact.version + ' (syncs to the lab).' }));
    }
    return el('div', { class: 'card' }, kids);
  }

  function leaderboardCard() {
    const { el } = K();
    const lb = Q.run && Q.run.leaderboard;
    if (!lb || !(lb.rows || []).length) return el('div');
    const kids = [el('h3', { text: 'The leaderboard (held-out mice only)' })];
    const byT = {};
    for (const row of lb.rows) (byT[row.target] = byT[row.target] || []).push(row);
    for (const [t, rows] of Object.entries(byT)) {
      const task = rows[0].task;
      const head = ['Inputs', 'Model', SCORE_WORD[task], task === 'regression' ? 'Mean abs. error (%)' : 'Calls right', 'Bar', 'Nuisance baseline',
        'Chance check P', 'What carried it most (family · feature)'];
      const trs = rows.map((x) => {
        const second = task === 'regression' ? x.score.mae : x.score.accuracy;
        const tr = el('tr', { class: x.passes ? 'stat hit' : '', style: 'cursor: pointer', onclick: () => openTask(x) }, [
          el('td', { text: VIEW_WORD[x.view] || x.view }), el('td', { text: MODEL_WORD[x.model] || x.model }),
          el('td', { class: 'num', text: fmt(x.main) }), el('td', { class: 'num', text: task === 'regression' ? fmt(second, 1) : Math.round(100 * second) + '%' }),
          el('td', { text: x.passes ? 'reached ' + fmt(x.bar) : 'below ' + fmt(x.bar) }),
          el('td', { class: 'num', text: x.view === 'nuisance' ? '(this is it)' : fmt(x.nuisance_baseline) }),
          el('td', { class: 'num', text: x.chance_p == null ? 'not run' : fmt(x.chance_p, 3) }),
          el('td', { class: 'small', text: (x.top_family || '—') + ' · ' + (x.top_feature || '—') })]);
        return tr;
      });
      kids.push(el('h4', { text: TARGET_WORD[t] || t }));
      kids.push(el('div', { class: 'tablewrap' }, [el('table', {}, [el('thead', {}, [el('tr', {}, head.map((h) => el('th', { text: h })))]),
        el('tbody', {}, trs)])]));
    }
    if ((lb.errors || []).length) kids.push(el('p', { class: 'err', text: lb.errors.length + ' task(s) failed: ' + lb.errors.map((e) => e.target + ' / ' + e.view + ' / ' + e.model + ': ' + e.error).join('; ') }));
    kids.push(el('p', { class: 'small muted', text: 'Click a row to open that model: its call for every held-out mouse and what carried it.' }));
    return el('div', { class: 'card' }, kids);
  }

  async function openTask(row) {
    const t = (Q.run.tasks || []).find((x) => x.target === row.target && x.view === row.view && x.model === row.model);
    if (!t) return;
    Q.open = t.i;
    try { Q.task = (await K().api('/api/er2/run/' + Q.rid + '/task/' + t.i)).result; } catch (e) { Q.err = e.message; }
    fill();
    const box = document.getElementById('er2Open');
    if (box) box.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function list(title, rows, val, word) {
    const { el } = K();
    if (!rows || !rows.length) return el('div');
    return el('div', { class: 'stat' }, [el('div', { class: 'stat-h', text: title }),
      el('ol', {}, rows.slice(0, 10).map((d) => el('li', { text: d.item + ' — ' + word + ' ' + fmt(d[val], 3) })))]);
  }

  function openCard() {
    const { el } = K();
    const r = Q.task;
    if (!r) return el('div', { id: 'er2Open' });
    const ex = r.explain || {};
    const kids = [el('h3', { text: 'Opened: ' + (TARGET_WORD[r.target] || r.target) + ' · ' + (VIEW_WORD[r.view] || r.view) + ' · ' + (MODEL_WORD[r.model] || r.model) }),
      el('p', { text: SCORE_WORD[r.task] + ' ' + fmt(r.score.main) + ' on held-out mice (' + r.n_folds + ' tests). '
        + (r.passes ? 'Reached the bar.' : 'Below the bar (' + fmt(r.bar) + ').') })];
    // the calls, one row per held-out mouse (a mouse held out several times shows its mean call)
    const per = {};
    for (const c of r.calls) {
      const v = Array.isArray(c.call) ? c.call : [c.call];
      const p = per[c.lab] = per[c.lab] || { truth: c.truth, sum: v.map(() => 0), n: 0 };
      v.forEach((x, i) => { p.sum[i] += x; });
      p.n += 1;
    }
    const cls = r.classes;
    const tr = Object.entries(per).map(([lab, p]) => {
      const m = p.sum.map((x) => x / p.n);
      let truth, call;
      if (r.task === 'regression') { truth = fmt(p.truth, 1) + '%'; call = fmt(m[0], 1) + '%'; }
      else if (r.task === 'binary') { truth = cls[p.truth]; call = (m[0] >= 0.5 ? cls[1] : cls[0]) + ' (' + fmt(m[0]) + ')'; }
      else { truth = cls[p.truth]; const k = m.indexOf(Math.max(...m)); call = cls[k] + ' (' + m.map((x) => fmt(x)).join(' / ') + ')'; }
      return el('tr', {}, [el('td', { text: lab }), el('td', { text: truth }), el('td', { text: call }), el('td', { class: 'num', text: String(p.n) })]);
    });
    kids.push(el('div', { class: 'tablewrap' }, [el('table', {}, [el('thead', {}, [el('tr', {}, ['Mouse', 'Truth', 'Held-out call', 'Times held out']
      .map((h) => el('th', { text: h })))]), el('tbody', {}, tr)])]));
    kids.push(el('div', { class: 'stats' }, [
      list('Permutation: families (score lost when scrambled)', ex.perm_family, 'drop', 'lost'),
      list('Permutation: features', ex.perm_feature, 'drop', 'lost'),
      list('Shapley: families (mean push per mouse)', ex.shap_family, 'mean_abs', 'push'),
      list('Shapley: features', (ex.shap_feature || []).filter((d) => d.item !== '(everything else)'), 'mean_abs', 'push'),
      list('Retrained without the family', ex.drop_family, 'drop', 'lost'),
      list('Attention: event features that go with the weight', ex.attention_feature, 'mean_rho', 'rank correlation'),
    ]));
    return el('div', { class: 'card', id: 'er2Open' }, kids);
  }

  function mostCard() {
    const { el } = K();
    const lb = Q.run && Q.run.leaderboard;
    const M = lb && lb.most_important;
    if (!M || !Object.keys(M).length) return el('div');
    const kids = [el('h3', { text: 'MOST IMPORTANT' }), el('p', { class: 'small muted', text: 'Per target, over the models that reached the bar '
      + '(or, when none did, the three best). Each method ranks its items; first place is worth 1 point, last 0; points are added over methods and '
      + 'models and divided by the number of models. "Methods" and "models" count how many put the item in their top ten (top three for families).' })];
    for (const [t, m] of Object.entries(M)) {
      kids.push(el('h4', { text: (TARGET_WORD[t] || t) + ' — ' + m.basis }));
      kids.push(el('div', { class: 'stats' }, [
        el('div', { class: 'stat' }, [el('div', { class: 'stat-h', text: 'Families' }), el('ol', {}, (m.families || []).slice(0, 8).map((d) =>
          el('li', { text: d.item + ' — ' + fmt(d.points) + ' points · ' + d.n_methods + ' methods · ' + d.n_models + ' models' })))]),
        el('div', { class: 'stat' }, [el('div', { class: 'stat-h', text: 'Features' }), el('ol', {}, (m.features || []).slice(0, 15).map((d) =>
          el('li', { text: d.item + ' — ' + fmt(d.points) + ' points · ' + d.n_methods + ' methods · ' + d.n_models + ' models' })))]),
        el('div', { class: 'stat' }, [el('div', { class: 'stat-h', text: 'Measures (statistics of one measure added together)' }),
          el('ol', {}, (m.measures || []).slice(0, 12).map((d) => el('li', { text: d.item + ' — ' + fmt(d.points) + ' points' })))]),
      ]));
    }
    return el('div', { class: 'card' }, kids);
  }

  function fill() {
    const root = document.getElementById('er2Root');
    if (!root || !K()) return;
    const { el } = K();
    root.innerHTML = '';
    root.appendChild(intro());
    if (Q.err) root.appendChild(el('p', { class: 'err', text: Q.err }));
    if (!Q.info) { root.appendChild(el('p', { class: 'empty', text: 'Opening Extraction Room 2.0…' })); return; }
    root.appendChild(bundles());
    root.appendChild(newRun());
    root.appendChild(runsCard());
    root.appendChild(leaderboardCard());
    root.appendChild(openCard());
    root.appendChild(mostCard());
  }

  function render() {
    const root = K().el('div', { id: 'er2Root' });
    Q.root = root;
    setTimeout(() => { if (!Q.info) loadInfo(); else fill(); }, 0);
    return root;
  }

  ROOM.ext.er2 = { render, state: () => Q, _load: loadInfo };
})();
