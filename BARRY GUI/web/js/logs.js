/* ==========================================================================
   logs.js -- The History and Errors viewers.

   Both read the pooled GUI_logs store. History answers "what did we run, with
   which settings, against which session"; Errors answers "what broke and
   where", with the full traceback kept.
   ========================================================================== */
'use strict';

/* ---------------------------------------------------------------- History */
BARRY.views.history = (function () {
  let runs = [];
  let activity = [];
  let selected = null;
  let query = '';
  let statusFilter = '';
  let mode = 'runs';           // 'runs' | 'activity'
  let showTimeline = true;

  async function load() {
    try {
      const res = await api('/api/history?limit=400');
      runs = res.runs || [];
    } catch (e) {
      toast('Could not read history: ' + e.message, 'err');
      runs = [];
    }
    try {
      const res = await api('/api/activity?limit=800');
      activity = res.activity || [];
    } catch (e) {
      activity = [];
    }
    renderList();
  }

  /* ======================================================================
     Feature 1 -- Activity timeline
     "Big brother" logging is only useful if you can see the shape of it. One
     stacked bar per day, colored by what kind of thing happened; clicking a
     day filters the list to it.
     ====================================================================== */
  /* Which actions fall in which band. Colors are read from the theme at draw
     time rather than written in here, so the chart is not stuck in UVM gold
     when the interface is pink. */
  const TL_KINDS = [
    ['figure', 'figures & exports', '--c1', /^(figure|deck|result)/],
    ['view',   'viewing & filters', '--c2', /^(panel|filter|channel|measure|view|session\.open|event\.navigate)/],
    ['events', 'events & spikes',   '--c3', /^(events?|spikes?|bookmark)/],
    ['run',    'script runs',       '--c4', /^(run|pipeline|scratch)/],
    ['other',  'everything else',   '--c5', /./],
  ];

  const TL_CLASSES = () => TL_KINDS.map(
    ([key, label, tok, rx]) => [key, label, BARRY.token(tok), rx]);

  function classOf(action) {
    for (const [key, , , rx] of TL_KINDS) {
      if (rx.test(String(action || ''))) return key;
    }
    return 'other';
  }

  function timelineData() {
    const byDay = new Map();
    const bump = (at, cls) => {
      const d = String(at || '').slice(0, 10);
      if (!d) return;
      if (!byDay.has(d)) byDay.set(d, {});
      const b = byDay.get(d);
      b[cls] = (b[cls] || 0) + 1;
    };
    for (const a of activity) bump(a.at, classOf(a.action));
    for (const r of runs) bump((r.provenance || {}).at, 'run');

    const days = Array.from(byDay.keys()).sort().slice(-45);
    return { days, byDay,
             max: Math.max(1, ...days.map((d) => Object.values(byDay.get(d))
                                                       .reduce((x, y) => x + y, 0))) };
  }

  function renderTimeline() {
    const host = $('#histTimeline');
    if (!host) return;
    host.innerHTML = '';
    host.classList.toggle('hidden', !showTimeline);
    if (!showTimeline) return;

    const d = timelineData();
    if (!d.days.length) {
      host.appendChild(el('div', { class: 'hint',
        text: 'Nothing logged yet \u2014 the timeline fills in as you work.' }));
      return;
    }

    const canvas = el('canvas', { class: 'tl-canvas' });
    host.appendChild(canvas);
    host.appendChild(el('div', { class: 'tl-legend' },
      TL_CLASSES().map(([key, label, color]) => el('span', {}, [
        el('i', { style: 'background:' + color }),
        el('span', { text: label }),
      ])).concat([
        el('span', { class: 'spacer' }),
        el('span', { text: 'busiest day: ' + d.max + ' entries' }),
      ])));

    // Painted after layout, so clientWidth is real.
    requestAnimationFrame(() => {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth || 600, h = canvas.clientHeight || 92;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const cs = getComputedStyle(document.documentElement);
      const dim = cs.getPropertyValue('--text-3').trim() || '#6f8c7d';
      const gap = 2;
      const bw = Math.max(3, (w - 34) / d.days.length - gap);
      const base = h - 16;

      ctx.strokeStyle = cs.getPropertyValue('--line-soft').trim() || '#1a3227';
      ctx.beginPath(); ctx.moveTo(30, base + .5); ctx.lineTo(w, base + .5);
      ctx.stroke();

      ctx.fillStyle = dim;
      ctx.font = '9px ui-monospace, Consolas, monospace';
      ctx.textAlign = 'right';
      ctx.fillText(String(d.max), 26, 12);
      ctx.fillText('0', 26, base);

      d.days.forEach((day_, i) => {
        const bucket = d.byDay.get(day_) || {};
        const x = 30 + i * (bw + gap);
        let y = base;
        for (const [key, , color] of TL_CLASSES()) {
          const n = bucket[key] || 0;
          if (!n) continue;
          const bh = (n / d.max) * (base - 14);
          ctx.fillStyle = color;
          ctx.fillRect(x, y - bh, bw, bh);
          y -= bh;
        }
      });

      // Only the ends and the middle get a label, or they collide.
      ctx.textAlign = 'left';
      ctx.fillStyle = dim;
      ctx.fillText(d.days[0].slice(5), 30, h - 4);
      if (d.days.length > 3) {
        ctx.textAlign = 'right';
        ctx.fillText(d.days[d.days.length - 1].slice(5), w - 2, h - 4);
      }

      canvas.onclick = (e) => {
        const rect = canvas.getBoundingClientRect();
        const i = Math.floor((e.clientX - rect.left - 30) / (bw + gap));
        const day_ = d.days[i];
        if (!day_) return;
        query = day_;
        $('#histSearch').value = day_;
        renderList();
        toast('Filtered to ' + day_, null, 2200);
      };
      canvas.title = 'Click a bar to filter the list to that day';
    });
  }

  function visible() {
    const q = query.trim().toLowerCase();
    return runs.filter((r) => {
      if (statusFilter === 'figure') { if (r.kind !== 'figure') return false; }
      else if (statusFilter && r.status !== statusFilter) return false;
      if (!q) return true;
      const hay = [r.script, r.label, (r.session || {}).label,
                   (r.provenance || {}).at, (r.provenance || {}).user,
                   (r.provenance || {}).machine,
                   JSON.stringify(r.parameters || {})].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }

  function visibleActivity() {
    const q = query.trim().toLowerCase();
    return activity.filter((a) => {
      if (!q) return true;
      return [a.action, a.at, a.user, a.machine, a.view,
              (a.session || {}).label, JSON.stringify(a.detail || {})]
        .join(' ').toLowerCase().includes(q);
    });
  }

  function renderList() {
    renderTimeline();
    const host = $('#histList');
    host.innerHTML = '';

    if (mode === 'activity') {
      const list = visibleActivity();
      $('#histSub').textContent = list.length + ' of ' + activity.length
        + ' logged action(s)';
      if (!list.length) {
        host.appendChild(el('div', { class: 'tree-empty',
          text: activity.length ? 'Nothing matches that filter.'
                                : 'No actions logged yet.' }));
        return;
      }
      for (const a of list) {
        host.appendChild(el('button', {
          class: 'hist-row',
          title: JSON.stringify(a.detail || {}, null, 1),
          onclick: () => renderActivityDetail(a),
        }, [
          el('span', { class: 'st ' + actionClass(a.action) }),
          el('span', { class: 'nm', text: a.action }),
          el('span', { class: 'tm',
            text: (a.at || '').slice(5, 16).replace('T', ' ') }),
        ]));
      }
      return;
    }

    const list = visible();
    $('#histSub').textContent = list.length + ' of ' + runs.length
      + ' run(s) recorded in GUI_logs';

    if (!list.length) {
      host.appendChild(el('div', { class: 'tree-empty',
        text: runs.length ? 'Nothing matches that filter.'
                          : 'No runs recorded yet. Run a script or export a figure.' }));
      return;
    }

    for (const r of list) {
      const at = (r.provenance || {}).at || '';
      host.appendChild(el('button', {
        class: 'hist-row' + (selected === r.id ? ' active' : ''),
        title: r.script || r.label,
        onclick: () => { selected = r.id; renderList(); renderDetail(r); },
      }, [
        el('span', { class: 'st ' + (r.kind === 'figure' ? 'figure' : (r.status || '')) }),
        el('span', { class: 'nm', text: r.label || r.script || '(run)' }),
        el('span', { class: 'tm', text: at ? at.slice(5, 16).replace('T', ' ') : '' }),
      ]));
    }
  }

  function actionClass(action) {
    const a = String(action || '');
    if (a.startsWith('spikes') || a.startsWith('bookmark')) return 'figure';
    if (a.startsWith('figure') || a.startsWith('session.open')) return 'done';
    if (a.startsWith('events')) return 'running';
    return 'canceled';
  }

  function renderActivityDetail(a) {
    const host = $('#histDetail');
    host.innerHTML = '';
    host.appendChild(el('div', { class: 'detail-head' }, [
      el('div', {}, [
        el('h2', { text: a.action }),
        el('p', { class: 'detail-path', text: (a.at || '').replace('T', ' ') }),
      ]),
    ]));

    const kv = el('dl', { class: 'kv' });
    const add = (k, v) => {
      if (v === null || v === undefined || v === '') return;
      kv.appendChild(el('dt', { text: k }));
      kv.appendChild(el('dd', {
        text: typeof v === 'object' ? JSON.stringify(v) : String(v) }));
    };
    add('By', a.user);
    add('Machine', (a.machine || '') + (a.os ? ' · ' + a.os : ''));
    add('View', a.view);
    add('Session', (a.session || {}).label);
    add('Session key', (a.session || {}).key);
    host.appendChild(el('div', { class: 'section-label', text: 'Where' }));
    host.appendChild(kv);

    const d = a.detail || {};
    if (Object.keys(d).length) {
      host.appendChild(el('div', { class: 'section-label', text: 'What' }));
      const dk = el('dl', { class: 'kv' });
      for (const [k, v] of Object.entries(d)) {
        dk.appendChild(el('dt', { text: k }));
        dk.appendChild(el('dd', {
          text: typeof v === 'object' ? JSON.stringify(v) : String(v) }));
      }
      host.appendChild(dk);
    }
  }

  function renderDetail(r) {
    const host = $('#histDetail');
    host.innerHTML = '';
    const prov = r.provenance || {};
    const sess = r.session || {};

    host.appendChild(el('div', { class: 'detail-head' }, [
      el('div', {}, [
        el('h2', { text: r.label || r.script || 'run' }),
        el('p', { class: 'detail-path', text: r.script || '' }),
        el('div', { class: 'detail-tags' }, [
          el('span', { class: 'tag ' + (r.status === 'done' ? 'done'
                        : r.status === 'failed' ? 'blocked' : 'opt'), text: r.status || '?' }),
          el('span', { class: 'tag lang', text: r.kind || 'script' }),
          r.lang ? el('span', { class: 'tag lang', text: r.lang }) : null,
          r.duration_s != null ? el('span', { class: 'tag opt',
            text: fmtDur(r.duration_s) }) : null,
        ]),
      ]),
      el('div', { class: 'head-actions' }, [
        sess.path ? el('button', {
          class: 'btn ghost sm', text: 'Open session',
          onclick: () => { setView('xplore'); BARRY.views.xplore.open(sess.path); },
        }) : null,
        replayButton(r),
        el('button', {
          class: 'btn ghost sm', text: 'Copy id',
          onclick: () => BARRY.copy(r.id, 'Run id'),
        }),
        el('button', {
          class: 'btn ghost sm', text: 'Copy as JSON',
          title: 'The whole record, for a bug report or a methods note',
          onclick: () => BARRY.copy(JSON.stringify(r, null, 2), 'Run record'),
        }),
      ]),
    ]));

    const kv = el('dl', { class: 'kv' });
    const add = (k, v) => {
      if (v === null || v === undefined || v === '') return;
      kv.appendChild(el('dt', { text: k }));
      kv.appendChild(el('dd', { text: String(v) }));
    };
    add('Run id', r.id);
    add('When', prov.at);
    add('By', prov.user);
    add('Machine', prov.machine + (prov.os ? ' · ' + prov.os : ''));
    add('Session', sess.label);
    add('Session key', sess.key);
    add('Session path', sess.path);
    add('Exit code', r.returncode);
    add('Stage', r.stage);
    add('Format', r.format);
    host.appendChild(el('div', { class: 'section-label', text: 'Provenance' }));
    host.appendChild(kv);

    const params = r.parameters || {};
    if (Object.keys(params).length) {
      host.appendChild(el('div', { class: 'section-label', text: 'Parameters' }));
      const pk = el('dl', { class: 'kv' });
      for (const [k, v] of Object.entries(params)) {
        pk.appendChild(el('dt', { text: k }));
        pk.appendChild(el('dd', { text: typeof v === 'object' ? JSON.stringify(v) : String(v) }));
      }
      host.appendChild(pk);
    }

    if ((r.overrides || []).length) {
      host.appendChild(el('div', { class: 'section-label', text: 'Overridden constants' }));
      host.appendChild(el('div', { class: 'detail-tags' },
        r.overrides.map((o) => el('span', { class: 'tag opt', text: o }))));
    }

    if ((r.panels || []).length) {
      host.appendChild(el('div', { class: 'section-label', text: 'Figure panels' }));
      host.appendChild(el('div', { class: 'detail-tags' },
        r.panels.map((p) => el('span', { class: 'tag opt',
          text: (p.title || p.panel) + ' (r' + p.row + 'c' + p.col + ')' }))));
    }

    if ((r.command || []).length) {
      host.appendChild(el('div', { class: 'section-label', text: 'Command' }));
      host.appendChild(el('div', { class: 'source-box' }, [
        el('pre', { text: (r.command || []).join(' ') + '\n\ncwd: ' + (r.cwd || '') }),
      ]));
    }

    if ((r.output_tail || []).length) {
      host.appendChild(el('div', { class: 'section-label', text: 'Output (tail)' }));
      host.appendChild(el('div', { class: 'source-box' }, [
        el('pre', { text: r.output_tail.join('\n') }),
      ]));
    }

    if ((r.output || {}).rel) {
      host.appendChild(el('div', { class: 'section-label', text: 'Saved output' }));
      host.appendChild(el('div', { class: 'coll-row' }, [
        el('button', {
          class: 'btn ghost sm', text: 'Show in Results',
          onclick: () => {
            setView('results');
            if (BARRY.views.results.search) {
              BARRY.views.results.search(baseName(r.output.rel));
            }
          },
        }),
        r.output.github ? el('a', { class: 'btn ghost sm', href: r.output.github,
                                    target: '_blank', text: 'View on GitHub' }) : null,
      ]));
    }
  }

  /* ======================================================================
     Feature 2 -- Replay a run
     A history entry already holds the script, the language and every
     parameter. Replay drops those back into the Explorer or the pipeline so
     the same thing can be run again without retyping the numbers.
     ====================================================================== */
  function replayButton(r) {
    // A figure has a recipe, so it gets the real thing: an audit of what it
    // needs and a visible walk through rebuilding it. Replay only ever put
    // the window and filters back, which is a fraction of a figure.
    if (r.kind === 'figure' && BARRY.figrebuild) {
      return el('button', {
        class: 'btn ghost sm', text: 'Rebuild\u2026',
        title: 'Check what this figure needs, then walk through remaking it',
        onclick: () => BARRY.figrebuild.start(r.id),
      });
    }
    const canScript = r.kind === 'script' && r.script;
    const canStage = r.kind === 'pipeline' && r.stage;
    if (!canScript && !canStage) return null;
    return el('button', {
      class: 'btn ghost sm', text: 'Replay\u2026',
      title: 'Set this run up again with the same parameters',
      onclick: () => replay(r),
    });
  }

  async function replay(r) {
    BARRY.activity.log('history.replay', { run: r.id, kind: r.kind });
    if (r.kind === 'pipeline' && (r.parameters || {}).folder) {
      setView('pipeline');
      await BARRY.views.pipeline.setFolder(r.parameters.folder);
      toast('Pipeline pointed at ' + baseName(r.parameters.folder)
            + ' \u2014 stage "' + r.stage + '" is ready to run.', 'ok', 6000);
      return;
    }
    if (r.kind === 'figure') {
      // One path for figures, so a rebuild started from the command palette
      // gets the same audit as one started from the button.
      if (BARRY.figrebuild) { BARRY.figrebuild.start(r.id); return; }
      if (!(r.session || {}).path) return;
      setView('xplore');
      const sess = await BARRY.views.xplore.open(r.session.path);
      if (!sess) return;
      const pr = r.parameters || {};
      if (pr.t0 != null) sess.t0 = pr.t0;
      if (pr.t1 != null && pr.t0 != null) sess.span = pr.t1 - pr.t0;
      for (const k of ['hp', 'lp', 'notch']) {
        if (pr[k] != null) sess[k] = pr[k];
      }
      BARRY.views.xplore.onShow();
      toast('Reopened at the same window and filters. '
            + 'Open the figure builder to rebuild it.', 'ok', 6000);
      return;
    }
    if (r.script) {
      setView('explorer');
      await BARRY.views.explorer.select(r.script);
      toast('Loaded ' + baseName(r.script)
            + (Object.keys(r.parameters || {}).length
               ? ' \u2014 its logged parameters are listed in the detail above.'
               : ''), 'ok', 6000);
    }
  }

  function init() {
    let deb = null;
    $('#histSearch').addEventListener('input', (e) => {
      query = e.target.value;
      clearTimeout(deb); deb = setTimeout(renderList, 120);
    });
    $$('#histStatusFilter .pill').forEach((b) =>
      b.addEventListener('click', () => {
        if (b.dataset.mode) {
          mode = b.dataset.mode;
        } else {
          mode = 'runs';
          statusFilter = b.dataset.status;
        }
        $$('#histStatusFilter .pill').forEach((x) => x.classList.toggle('active', x === b));
        renderList();
      }));
    $('#histRefresh').addEventListener('click', load);
    $('#histReveal').addEventListener('click', () => {
      const dir = BARRY.state.catalog && BARRY.state.catalog.logs_dir;
      if (dir) apiPost('/api/reveal', { path: dir }).catch(() => {});
    });
    /* Feature 3 -- take the log with you. */
    $('#histExport').addEventListener('click', () => {
      const what = mode === 'activity' ? 'activity' : 'runs';
      BARRY.download('/api/history/export', { what },
                     what === 'activity' ? 'activity.csv' : 'run-history.csv');
      BARRY.activity.log('history.export', { what });
    });
    $('#histTimelineToggle').addEventListener('click', (e) => {
      showTimeline = !showTimeline;
      e.target.classList.toggle('active', showTimeline);
      renderTimeline();
    });
  }

  return { init, onShow: load, reload: load };
})();


/* ---------------------------------------------------------------- Errors */
BARRY.views.errors = (function () {
  let errors = [];
  let groups = [];
  let days = [];
  let day = '';
  let grouped = true;
  let mode = 'errors';        // 'errors' | 'debug' | 'feedback'
  let reports = [];           // what has been filed
  let kinds = [];
  let showState = 'open';     // which reports the list shows
  let draft = null;           // the form, while it is open
  let trace = [];
  let traceFailedOnly = false;
  let hideResolved = true;
  const openGroups = new Set();

  async function load() {
    try {
      const res = await api('/api/errors?limit=300' + (day ? '&day=' + day : ''));
      errors = res.errors || [];
      days = res.days || [];
    } catch (e) {
      errors = [];
      toast('Could not read the error log: ' + e.message, 'err');
    }
    try {
      const res = await api('/api/errors/grouped?limit=600'
                            + (day ? '&day=' + day : ''));
      groups = res.groups || [];
    } catch (e) { groups = []; }
    try {
      const res = await api('/api/debug/trace?limit=400'
                            + (traceFailedOnly ? '&failed=1' : ''));
      trace = res.trace || [];
    } catch (e) { trace = []; }
    renderDays();
    render();
    // The badge counts what still needs attention, not the whole archive:
    // a number that never goes down stops being read.
    const open = groups.filter((g) => !g.resolved)
                       .reduce((n, g) => n + g.count, 0);
    BARRY.setErrorCount(grouped ? open : errors.length);
  }

  function renderDays() {
    const sel = $('#errDay');
    const cur = day;
    sel.innerHTML = '';
    sel.appendChild(el('option', { value: '', text: 'All days' }));
    for (const d of days) {
      sel.appendChild(el('option', { value: d, text: d, selected: d === cur ? 'selected' : null }));
    }
  }

  /* ==================================================================
     Feedback: bugs, features, suggestions
     ==================================================================
     "In the errors have a suggest improvement, report bug, add feature
     section... who wants, and ability to attach screenshots!"

     Here rather than in an issue tracker because the moment you notice
     something is the moment you are looking at it, and by the time anyone
     has switched to a browser and found the repo the detail is gone. Reports
     are one file each under GUI_logs/feedback, sharded by machine, so two
     people filing on two computers never touch the same file.
     ================================================================== */
  const openReports = () =>
    reports.filter((r) => (r.state || 'open') === 'open').length;

  const KIND_ICON = { bug: '\u26a0', feature: '\u2726', improvement: '\u25b3' };

  async function loadFeedback() {
    try {
      const res = await api('/api/feedback');
      reports = res.reports || [];
      kinds = res.kinds || [];
      if (mode === 'feedback') render();
    } catch (e) { /* the tab says so below */ }
  }

  /* A blank report. `context` is what the client knows and the server
     cannot: which view was up, what was open, how big the window is. */
  function blankDraft(kind) {
    const xf = (BARRY.views.xplore && BARRY.views.xplore.state) || {};
    const sess = xf.sessions && xf.active ? xf.sessions[xf.active] : null;
    return {
      kind: kind || 'bug',
      title: '', detail: '', wants: '',
      shots: [],
      context: {
        view: BARRY.state && BARRY.state.view,
        recording: sess ? (sess.identity && sess.identity.label) : null,
        path: sess ? sess.path : null,
        panels: (xf.panes || []).filter(Boolean).map((p) => p.panel),
        window: sess ? { t0: sess.t0, span: sess.span } : null,
        screen: window.innerWidth + 'x' + window.innerHeight,
        agent: navigator.userAgent,
      },
    };
  }

  /* Turn a File or a clipboard item into a data URI, shrunk if it is huge.
     A 4K screenshot is several megabytes and none of that detail survives
     being looked at in a panel, so anything over 1600px wide is scaled. */
  function readShot(file) {
    return new Promise((resolve) => {
      if (!file || !/^image\//.test(file.type)) { resolve(null); return; }
      const fr = new FileReader();
      fr.onload = () => {
        const img = new Image();
        img.onload = () => {
          const max = 1600;
          if (img.width <= max) { resolve({ data: fr.result, caption: '' }); return; }
          const sc = max / img.width;
          const c = document.createElement('canvas');
          c.width = Math.round(img.width * sc);
          c.height = Math.round(img.height * sc);
          c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
          resolve({ data: c.toDataURL('image/png'), caption: '' });
        };
        img.onerror = () => resolve({ data: fr.result, caption: '' });
        img.src = fr.result;
      };
      fr.onerror = () => resolve(null);
      fr.readAsDataURL(file);
    });
  }

  async function addShots(files) {
    for (const f of Array.from(files || [])) {
      if (draft.shots.length >= 8) {
        toast('Eight screenshots is the limit for one report.', null, 4000);
        break;
      }
      const shot = await readShot(f);
      if (shot) draft.shots.push(shot);
    }
    render();
  }

  function renderFeedback(host) {
    if (!draft) {
      host.appendChild(el('div', { class: 'res-toolbar' },
        kinds.concat(kinds.length ? [] : [
          { id: 'bug', name: 'Something is broken' },
          { id: 'feature', name: 'Something is missing' },
          { id: 'improvement', name: 'Something could be better' },
        ]).map((k) => el('button', {
          class: 'btn',
          text: (KIND_ICON[k.id] || '') + '  ' + k.name,
          onclick: () => { draft = blankDraft(k.id); render(); },
        })).concat([
          el('div', { class: 'spacer', style: 'flex:1' }),
          el('select', {
            class: 'mini-select',
            onchange: (e) => { showState = e.target.value; render(); },
          }, [['open', 'Open'], ['', 'Everything'], ['done', 'Done'],
              ['planned', 'Planned'], ['declined', 'Declined']]
            .map(([v, t]) => el('option', {
              value: v, text: t,
              selected: showState === v ? 'selected' : null }))),
        ])));
      renderReportList(host);
      return;
    }
    renderForm(host);
  }

  function renderForm(host) {
    const box = el('div', { class: 'fb-form' });
    const kindName = (kinds.find((k) => k.id === draft.kind) || {}).name
                     || draft.kind;
    box.appendChild(el('div', { class: 'fb-head' }, [
      el('strong', { text: (KIND_ICON[draft.kind] || '') + '  ' + kindName }),
      el('div', { class: 'spacer', style: 'flex:1' }),
      el('button', { class: 'btn ghost sm', text: 'Cancel',
                     onclick: () => { draft = null; render(); } }),
    ]));

    const field = (label, hint, node) => el('div', { class: 'field' }, [
      el('label', { text: label }),
      node,
      hint ? el('span', { class: 'hint', text: hint }) : null,
    ]);

    box.appendChild(field('In one line', null, el('input', {
      type: 'text', value: draft.title,
      placeholder: draft.kind === 'bug'
        ? 'e.g. the CSD goes blank after folding the control strip'
        : 'e.g. let me review only the flagged candidates',
      oninput: (e) => { draft.title = e.target.value; syncSend(); },
    })));

    box.appendChild(field(
      draft.kind === 'bug' ? 'What happened, and what you expected'
                           : 'What you are trying to do',
      draft.kind === 'bug'
        ? 'What you did, what happened, what should have happened. The steps '
          + 'matter more than the description.'
        : 'The job it would help with, not the button you imagine. That way '
          + 'it can be solved a better way than the one you had in mind.',
      el('textarea', {
        rows: '6', value: draft.detail,
        oninput: (e) => { draft.detail = e.target.value; },
      })));

    box.appendChild(field('Who wants this', 'So it can be asked about later.',
      el('input', {
        type: 'text', value: draft.wants,
        placeholder: 'your name, or whoever asked for it',
        oninput: (e) => { draft.wants = e.target.value; },
      })));

    /* Screenshots. Paste is the one that matters: Win+Shift+S then Ctrl+V
       is the whole interaction, and nobody has to save a file first. */
    const drop = el('div', {
      class: 'fb-drop', tabindex: '0',
      title: 'Paste a screenshot, drop an image here, or click to pick one',
      onclick: () => {
        const inp = el('input', { type: 'file', accept: 'image/*',
                                  multiple: 'multiple' });
        inp.addEventListener('change', () => addShots(inp.files));
        inp.click();
      },
      ondragover: (e) => { e.preventDefault();
                           drop.classList.add('over'); },
      ondragleave: () => drop.classList.remove('over'),
      ondrop: (e) => {
        e.preventDefault(); drop.classList.remove('over');
        addShots(e.dataTransfer.files);
      },
      onpaste: (e) => {
        const items = (e.clipboardData || {}).items || [];
        const files = [];
        for (const it of items) {
          if (it.kind === 'file') files.push(it.getAsFile());
        }
        if (files.length) { e.preventDefault(); addShots(files); }
      },
    }, [
      el('strong', { text: 'Screenshots' }),
      el('span', { text: 'Click here and press Ctrl+V, or drop an image in. '
                       + 'Win+Shift+S takes the shot.' }),
    ]);
    box.appendChild(drop);

    if (draft.shots.length) {
      box.appendChild(el('div', { class: 'fb-shots' },
        draft.shots.map((sh, i) => el('div', { class: 'fb-shot' }, [
          el('img', { src: sh.data, alt: '' }),
          el('input', {
            type: 'text', placeholder: 'what this shows (optional)',
            value: sh.caption,
            oninput: (e) => { sh.caption = e.target.value; },
          }),
          el('button', {
            class: 'badbtn danger', text: '\u2715', title: 'Remove',
            onclick: () => { draft.shots.splice(i, 1); render(); },
          }),
        ]))));
    }

    /* What is being sent with it, shown rather than described. Somebody
       filing a report is entitled to know what leaves their machine. */
    box.appendChild(el('details', { class: 'fb-context' }, [
      el('summary', { text: 'Also sent: which view, which recording, the '
                          + 'pane layout and the window size' }),
      el('pre', { text: JSON.stringify(draft.context, null, 1) }),
    ]));

    const send = el('button', {
      class: 'btn', text: 'Send it', disabled: 'disabled',
      onclick: async () => {
        send.disabled = 'disabled';
        try {
          await apiPost('/api/feedback', {
            kind: draft.kind, title: draft.title, detail: draft.detail,
            wants: draft.wants, context: draft.context,
            screenshots: draft.shots,
          });
          toast('Filed. Thank you \u2014 it is in GUI_logs/feedback.',
                'ok', 6000);
          draft = null;
          await loadFeedback();
          render();
        } catch (e) {
          toast('Could not file that: ' + e.message, 'err', 8000);
          send.disabled = null;
        }
      },
    });
    function syncSend() { send.disabled = draft.title.trim() ? null : 'disabled'; }
    syncSend();
    box.appendChild(el('div', { class: 'fb-actions' }, [
      el('span', { class: 'hint',
                   text: draft.shots.length
                     ? draft.shots.length + ' screenshot(s) attached' : '' }),
      el('div', { class: 'spacer', style: 'flex:1' }),
      send,
    ]));

    host.appendChild(box);
    // So Ctrl+V works without hunting for where to click first.
    setTimeout(() => drop.focus(), 0);
  }

  function renderReportList(host) {
    const rows = reports.filter((r) => !showState
                                    || (r.state || 'open') === showState);
    if (!rows.length) {
      host.appendChild(el('div', { class: 'empty' }, [
        el('p', { text: reports.length
          ? 'Nothing ' + showState + '.'
          : 'Nothing has been reported yet.' }),
        el('p', { class: 'hint', text: 'Anything that made you say "that is '
          + 'annoying" is worth one of these. It takes about twenty seconds '
          + 'and a screenshot.' }),
      ]));
      return;
    }
    const list = el('div', { class: 'fb-list' });
    for (const r of rows) {
      list.appendChild(el('div', { class: 'fb-item fb-' + r.kind }, [
        el('div', { class: 'fb-item-head' }, [
          el('span', { class: 'fb-kind', text: KIND_ICON[r.kind] || '' }),
          el('strong', { text: r.title }),
          el('div', { class: 'spacer', style: 'flex:1' }),
          el('span', { class: 'flagchip'
            + (r.state === 'done' ? ' good' : ''), text: r.state || 'open' }),
        ]),
        el('div', { class: 'fb-meta',
          text: [r.at, r.by, r.wants ? 'wanted by ' + r.wants : null,
                 (r.context || {}).view ? 'in ' + r.context.view : null]
            .filter(Boolean).join('  \u00b7  ') }),
        r.detail ? el('p', { class: 'fb-detail', text: r.detail }) : null,
        (r.screenshots || []).length
          ? el('div', { class: 'fb-shots small' },
              r.screenshots.map((sh) => el('a', {
                href: '/api/feedback/shot/' + encodeURIComponent(sh.file),
                target: '_blank', title: sh.caption || 'open full size',
              }, [el('img', {
                src: '/api/feedback/shot/' + encodeURIComponent(sh.file),
                alt: sh.caption || '' })])))
          : null,
        el('div', { class: 'fb-item-actions' },
          ['open', 'planned', 'done', 'declined'].map((st) => el('button', {
            class: 'mini' + ((r.state || 'open') === st ? ' active' : ''),
            text: st,
            onclick: async () => {
              try {
                await apiPost('/api/feedback/' + encodeURIComponent(r.id),
                              { state: st });
                await loadFeedback();
              } catch (e) { toast(e.message, 'err', 6000); }
            },
          }))),
      ]));
    }
    host.appendChild(list);
  }

  function render() {
    const host = $('#errBody');
    host.innerHTML = '';
    const open = groups.filter((g) => !g.resolved);
    $('#errSub').textContent = errors.length
      ? errors.length + ' error(s)' + (day ? ' on ' + day : ' recorded')
        + ' \u00b7 ' + groups.length + ' distinct, ' + open.length + ' unresolved'
        + ' \u00b7 ' + days.length + ' day(s) on record'
      : (day ? 'Nothing on ' + day + '.'
             : 'Nothing has failed \u2014 the log is clean.');

    host.appendChild(el('div', { class: 'res-toolbar' }, [
      el('button', {
        class: 'pill' + (mode === 'errors' ? ' active' : ''),
        text: 'Errors' + (errors.length ? ' (' + errors.length + ')' : ''),
        onclick: () => { mode = 'errors'; render(); },
      }),
      el('button', {
        class: 'pill' + (mode === 'debug' ? ' active' : ''),
        text: 'Debug trace' + (trace.length ? ' (' + trace.length + ')' : ''),
        title: 'Every command the interface sent, whether or not it failed',
        onclick: () => { mode = 'debug'; render(); },
      }),
      el('button', {
        class: 'pill' + (mode === 'feedback' ? ' active' : ''),
        text: 'Feedback'
            + (openReports() ? ' (' + openReports() + ')' : ''),
        title: 'Report a bug, ask for a feature, or suggest an improvement '
             + '\u2014 with screenshots',
        onclick: () => { mode = 'feedback'; render(); loadFeedback(); },
      }),
    ]));

    if (mode === 'debug') { renderDebug(host); return; }
    if (mode === 'feedback') { renderFeedback(host); return; }

    if (errors.length) {
      host.appendChild(el('div', { class: 'res-toolbar' }, [
        el('button', {
          class: 'pill' + (grouped ? ' active' : ''), text: 'Grouped',
          title: 'Fold identical failures together',
          onclick: () => { grouped = true; render(); },
        }),
        el('button', {
          class: 'pill' + (grouped ? '' : ' active'), text: 'Every entry',
          onclick: () => { grouped = false; render(); },
        }),
        el('button', {
          class: 'pill' + (hideResolved ? ' active' : ''), text: 'Hide resolved',
          onclick: () => { hideResolved = !hideResolved; render(); },
        }),
        el('div', { class: 'spacer', style: 'flex:1' }),
        el('span', { class: 'hint',
          title: 'GUI_logs/errors/<date>.jsonl, one line per error',
          text: 'Kept forever \u2014 resolving marks, never deletes.' }),
        el('button', {
          class: 'btn ghost sm', text: 'Open the log folder',
          onclick: () => {
            const dir = BARRY.state.catalog && BARRY.state.catalog.logs_dir;
            if (dir) apiPost('/api/reveal', { path: dir + '/errors' }).catch(() => {});
          },
        }),
        el('button', {
          class: 'btn ghost sm', text: 'Copy diagnostic bundle',
          title: 'Machine, versions and the last few tracebacks, as one block '
               + 'of text to paste into a message',
          onclick: async () => {
            try {
              const res = await apiPost('/api/errors/bundle', {});
              await BARRY.copy(res.text, 'Diagnostic bundle');
            } catch (e) { toast(e.message, 'err'); }
          },
        }),
      ]));
    }

    if (grouped && errors.length) { renderGroups(host); return; }

    if (!errors.length) {
      host.appendChild(el('div', { class: 'empty-state' }, [
        el('svg', { viewBox: '0 0 24 24', html: '<circle cx="12" cy="12" r="9"/><path d="m8.5 12.5 2.5 2.5 4.5-5"/>' }),
        el('p', { text: 'No errors logged. Anything that fails anywhere in BARRY lands here with its full traceback.' }),
      ]));
      return;
    }

    for (const e of errors) {
      const card = el('div', { class: 'err-card' }, [
        el('div', { class: 'ec-top' }, [
          el('span', { class: 'ec-where', text: e.where || 'unknown' }),
          el('span', { class: 'flagchip', text: e.id }),
          e.machine ? el('span', { class: 'flagchip', text: e.machine }) : null,
          el('span', { class: 'ec-when', text: (e.at || '').replace('T', ' ').slice(0, 19) }),
        ]),
        el('p', { class: 'ec-msg', text: e.message || '' }),
      ]);

      const ctx = e.context || {};
      if (Object.keys(ctx).length) {
        card.appendChild(el('div', { class: 'ec-ctx',
          text: Object.entries(ctx).map(([k, v]) =>
            k + '=' + (typeof v === 'object' ? JSON.stringify(v) : v)).join('   ') }));
      }
      if (e.detail) {
        card.appendChild(el('details', {}, [
          el('summary', { text: 'Traceback' }),
          el('pre', { text: e.detail }),
        ]));
      }
      host.appendChild(card);
    }
  }

  /* ======================================================================
     Errors, features 1-3 -- grouping, triage and a bundle
     The same failure logged forty times is one problem, not forty. Groups
     fold on a signature that ignores paths, timestamps and numbers; marking
     one resolved clears every past repeat and any future one that matches.
     ====================================================================== */
  /* ======================================================================
     Debug trace

     A bug that raises nothing leaves no error to look at, but it does leave a
     sequence of commands. This shows that sequence -- what the browser sent,
     what the server did with it, how long it took and what came back -- and
     wraps it up as one block of text to hand over.
     ====================================================================== */
  function renderDebug(host) {
    const client = BARRY.debug.requests();
    const con = BARRY.debug.console();

    host.appendChild(el('div', { class: 'res-toolbar' }, [
      el('span', { class: 'hint',
        text: 'Every request this session made, newest first. '
            + 'Nothing here leaves the machine until you copy it.' }),
      el('div', { style: 'flex:1' }),
      el('label', { class: 'toggle sm' + (traceFailedOnly ? ' on' : '') }, [
        el('input', {
          type: 'checkbox', checked: traceFailedOnly ? 'checked' : null,
          onchange: (e) => { traceFailedOnly = e.target.checked; load(); },
        }),
        el('span', { text: 'failures only' }),
      ]),
      el('button', { class: 'btn sm', text: 'Copy debug report',
                     onclick: debugReport }),
      el('button', {
        class: 'btn ghost sm', text: 'Clear',
        onclick: async () => {
          try { await apiPost('/api/debug/clear'); } catch (e) { /* fine */ }
          BARRY.debug.clear();
          load();
        },
      }),
    ]));

    if (!trace.length && !client.length) {
      host.appendChild(el('div', { class: 'tree-empty',
        text: 'Nothing traced yet. Use the interface, then come back \u2014 '
            + 'every command lands here.' }));
      return;
    }

    if (con.length) {
      host.appendChild(el('div', { class: 'section-label',
        text: 'Browser console \u2014 ' + con.length + ' entr(ies)' }));
      const cbox = el('div', { class: 'trace-list' });
      for (const c of con.slice(-40).reverse()) {
        cbox.appendChild(el('div', { class: 'trace-row ' + c.level }, [
          el('span', { class: 'tt', text: c.at }),
          el('span', { class: 'tm', text: c.level }),
          el('span', { class: 'tp', text: c.text, title: c.text }),
        ]));
      }
      host.appendChild(cbox);
    }

    host.appendChild(el('div', { class: 'section-label',
      text: 'Requests \u2014 ' + trace.length + ' on the server, '
          + client.length + ' seen by the browser' }));

    // Matched on method + path in order, so each row shows both sides where
    // they line up and stands alone where they do not.
    const rows = el('div', { class: 'trace-list tall' });
    const seen = new Map();
    for (const c of client) {
      const k = c.method + ' ' + c.path;
      if (!seen.has(k)) seen.set(k, []);
      seen.get(k).push(c);
    }
    // Newest first: what just happened is what you came here to look at, and
    // scrolling to the bottom of four hundred rows to find it is not a
    // reasonable thing to ask.
    for (const t of trace.slice().reverse()) {
      const k = t.method + ' ' + t.path;
      const mate = (seen.get(k) || []).shift();
      const bad = (t.status || 0) >= 400;
      const detail = t.query || (t.body ? JSON.stringify(t.body) : '');
      rows.appendChild(el('div', {
        class: 'trace-row' + (bad ? ' err' : ''),
        title: detail,
      }, [
        el('span', { class: 'tt', text: t.at }),
        el('span', { class: 'tm', text: t.method }),
        el('span', { class: 'tp', text: t.path }),
        el('span', { class: 'ts', text: String(t.status) }),
        el('span', { class: 'td', text: t.ms != null ? t.ms + ' ms' : '' }),
        el('span', { class: 'tq', text: detail.slice(0, 160) }),
        mate && mate.error
          ? el('span', { class: 'flagchip bad', text: mate.error.slice(0, 40) })
          : null,
      ]));
    }

    // Requests the server never saw are the most interesting rows of all.
    for (const list of seen.values()) {
      for (const c of list) {
        if (c.status && c.status < 400 && !c.error) continue;
        rows.appendChild(el('div', { class: 'trace-row err' }, [
          el('span', { class: 'tt', text: c.at }),
          el('span', { class: 'tm', text: c.method }),
          el('span', { class: 'tp', text: c.path }),
          el('span', { class: 'ts', text: String(c.status || 'no reply') }),
          el('span', { class: 'td', text: c.ms + ' ms' }),
          el('span', { class: 'tq', text: c.error || '' }),
          el('span', { class: 'flagchip bad', text: 'browser only' }),
        ]));
      }
    }
    host.appendChild(rows);
  }

  async function debugReport() {
    const note = await askPath(
      'What were you doing when it went wrong? (optional)',
      'e.g. "clicked Detect on m10 s4, nothing happened"');
    const xf = BARRY.views.xplore && BARRY.views.xplore.state;
    const sess = xf && xf.sessions[xf.active];
    try {
      const res = await apiPost('/api/debug/report', {
        note: note || '',
        view: BARRY.state.view,
        session: sess ? (sess.identity.label || sess.path) : null,
        requests: BARRY.debug.requests(),
        console: BARRY.debug.console(),
        actions: BARRY.activity.recent ? BARRY.activity.recent() : [],
      });
      await BARRY.copy(res.text, 'Debug report');
      if (res.saved) {
        toast('Also saved to Results/' + res.saved, 'ok', 6000);
        BARRY.refreshSync();
      }
    } catch (e) { toast(e.message, 'err'); }
  }

  function renderGroups(host) {
    const list = groups.filter((g) => !(hideResolved && g.resolved));
    if (!list.length) {
      host.appendChild(el('div', { class: 'empty-state' }, [
        el('svg', { viewBox: '0 0 24 24',
          html: '<circle cx="12" cy="12" r="9"/><path d="m8.5 12.5 2.5 2.5 4.5-5"/>' }),
        el('p', { text: hideResolved && groups.length
          ? 'Everything logged has been marked resolved.'
          : 'No errors logged.' }),
      ]));
      return;
    }

    for (const g of list) {
      const open = openGroups.has(g.signature);
      const card = el('div', {
        class: 'err-group' + (g.resolved ? ' resolved' : ''),
      });
      card.appendChild(el('div', {
        class: 'err-ghead',
        onclick: () => {
          if (open) openGroups.delete(g.signature);
          else openGroups.add(g.signature);
          render();
        },
      }, [
        el('span', { class: 'err-count',
                     title: g.resolved ? 'Resolved \u2014 still on record'
                                       : 'Not yet resolved',
                     text: (g.resolved ? '\u2713 ' : '') + g.count
                           + (g.count > 1 ? '\u00d7' : '') }),
        el('div', {}, [
          el('div', { class: 'err-gmsg' }, [
            // A bug that was marked fixed and has come back is the most
            // interesting row on this page, so it says so rather than
            // looking like an ordinary open one.
            g.reopened
              ? el('span', {
                  class: 'err-reopened', text: 'came back',
                  title: 'Marked resolved on '
                       + (g.resolved_at || '?').replace('T', ' ').slice(0, 16)
                       + ', and has happened again since',
                })
              : null,
            el('span', { text: g.message || '(no message)' }),
          ].filter(Boolean)),
          el('div', { class: 'err-gwhere',
                      text: (g.where || 'unknown')
                            + (g.machines.length ? '  \u00b7  '
                               + g.machines.join(', ') : '') }),
        ]),
        el('span', { class: 'err-gwhere',
                     text: (g.last || '').replace('T', ' ').slice(0, 16) }),
        el('span', { class: 'caret', style: open ? 'transform:rotate(90deg)' : '',
          html: '<svg viewBox="0 0 20 20"><path d="m8 5 5 5-5 5"/></svg>' }),
      ]));

      if (open) {
        const body = el('div', { class: 'err-gbody' });
        body.appendChild(el('div', { class: 'coll-row',
                                     style: 'margin:9px 0' }, [
          el('button', {
            class: 'btn ghost sm',
            text: g.resolved ? 'Reopen' : 'Mark resolved',
            onclick: (e) => { e.stopPropagation(); resolve(g, !g.resolved); },
          }),
          el('button', {
            class: 'btn ghost sm', text: 'Copy bundle for this',
            onclick: async (e) => {
              e.stopPropagation();
              try {
                const res = await apiPost('/api/errors/bundle',
                                          { signature: g.signature });
                await BARRY.copy(res.text, 'Diagnostic bundle');
              } catch (err) { toast(err.message, 'err'); }
            },
          }),
          g.resolved_by
            ? el('span', { class: 'hint',
                text: 'resolved by ' + g.resolved_by
                      + (g.resolved_note ? ' \u2014 ' + g.resolved_note : '') })
            : el('span', { class: 'hint',
                text: 'first seen ' + (g.first || '').slice(0, 16).replace('T', ' ') }),
        ]));

        for (const rec of g.records) {
          body.appendChild(el('div', { class: 'err-occ',
            text: (rec.at || '').replace('T', ' ').slice(0, 19)
                  + '   ' + (rec.machine || '') + '   ' + rec.id }));
        }
        const first = g.records[0] || {};
        if (Object.keys(first.context || {}).length) {
          body.appendChild(el('div', { class: 'ec-ctx',
            text: Object.entries(first.context).map(([k, v]) =>
              k + '=' + (typeof v === 'object' ? JSON.stringify(v) : v))
              .join('   ') }));
        }
        if (first.detail) {
          body.appendChild(el('details', { open: 'open' }, [
            el('summary', { text: 'Traceback (most recent occurrence)' }),
            el('pre', { text: first.detail }),
          ]));
        }
        card.appendChild(body);
      }
      host.appendChild(card);
    }
  }

  async function resolve(g, on) {
    let note = '';
    if (on) {
      note = await askPath('What fixed it? (optional)',
                           'e.g. remounted D:, installed scipy');
      if (note === null) note = '';
    }
    try {
      await apiPost('/api/errors/resolve',
                    { signature: g.signature, resolved: on, note });
      await load();
      toast(on ? 'Marked resolved' : 'Reopened', 'ok');
    } catch (e) { toast(e.message, 'err'); }
  }

  function init() {
    $('#errRefresh').addEventListener('click', load);
    $('#errDay').addEventListener('change', (e) => { day = e.target.value; load(); });
    $('#errTest').addEventListener('click', async () => {
      try { await apiPost('/api/errors/test'); await load(); toast('Wrote a test entry', 'ok'); }
      catch (e) { toast(e.message, 'err'); }
    });
  }

  return {
    init,
    // Both, so the Feedback tab can show its count without being opened.
    onShow: () => { load(); loadFeedback(); },
    reload: load,
  };
})();
