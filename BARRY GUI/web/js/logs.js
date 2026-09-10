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

  /* Whose history is being shown.

     The log has always been detailed -- ninety-five distinct actions, and
     `session.open` carries the path, the channel count and what was
     restored. What it could not answer was "who loaded that recording last
     and what did they do to it", because the view read this machine's own
     day files and nothing else, so the answer was only available if it
     happened to be you. */
  let who = 'mine';            // 'mine' | 'everyone'
  let scopeNote = null;        // set when 'everyone' was asked for and failed
  let actFilter = '';          // a kind of work: curation, bank, figure...

  async function load() {
    try {
      const res = await api('/api/history?limit=400');
      runs = res.runs || [];
    } catch (e) {
      toast('Could not read history: ' + e.message, 'err');
      runs = [];
    }
    try {
      const q = ['limit=1200', 'scope=' + who];
      if (actFilter) q.push('action=' + encodeURIComponent(actFilter));
      const res = await api('/api/activity?' + q.join('&'));
      activity = res.activity || [];
      /* Said out loud when the shared log was asked for and this machine's
         came back instead. "Nobody else did anything" and "I could not find
         out what anybody else did" are different answers, and an unlabelled
         list of your own actions looks like the first. */
      scopeNote = (who === 'everyone' && res.scope !== 'everyone')
        ? (res.scope_error || 'the shared log could not be read')
        : null;
    } catch (e) {
      activity = [];
      scopeNote = who === 'everyone' ? e.message : null;
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

  /* Whose log, and which kind of work. Two controls rather than a search
     box: "show me what happened to this recording" and "show me what Rain
     did" are the two questions actually asked of a history, and neither is
     a substring match. */
  function whoBar() {
    const kinds = ['', 'session', 'curation', 'bank', 'layers', 'figure',
                   'run', 'events', 'bookmark'];
    return el('div', { class: 'res-toolbar hist-who-bar' }, [
      el('span', { class: 'ctl-seg' }, [
        el('button', {
          class: 'mini' + (who === 'mine' ? ' on' : ''),
          text: 'This machine',
          title: 'The log on this computer',
          onclick: () => { who = 'mine'; load(); },
        }),
        el('button', {
          class: 'mini' + (who === 'everyone' ? ' on' : ''),
          text: 'Everyone',
          title: 'The shared log, from every machine that syncs',
          onclick: () => { who = 'everyone'; load(); },
        }),
      ]),
      el('select', {
        title: 'A kind of work',
        onchange: (e) => { actFilter = e.target.value; load(); },
      }, kinds.map((k) => el('option', {
        value: k, text: k ? k : 'All kinds',
        selected: actFilter === k ? 'selected' : null,
      }))),
      el('div', { style: 'flex:1' }),
      el('span', { class: 'hint',
        text: 'Every action BARRY records, with what it was done to.' }),
    ]);
  }

  /* The most useful few words out of a detail blob.

     The whole thing is in the tooltip and in the detail pane; on the row it
     competes with the action name, and an action name pushed off the row
     tells you nothing. Which recording, or which file, is nearly always the
     part worth having. */
  function rowGist(a) {
    const d = a.detail || {};
    const sess = (a.session || {});
    if (sess.label) return sess.label;
    if (d.path) return String(d.path).split(/[\/]/).slice(-2).join('/');
    if (d.file) return String(d.file);
    if (d.name) return String(d.name);
    if (d.gid) return String(d.gid);
    if (d.entry) return 'entry ' + d.entry;
    if (d.deck) return String(d.deck);
    return '';
  }

  /* ==================================================================
     What changed since you last looked
     ==================================================================
     The activity log could always answer this and nothing asked it. The
     mark is per machine and only moves when somebody presses the button --
     a digest that clears itself on render cannot be read twice, and the
     first read is usually the one where you get interrupted.
     ================================================================== */
  let digest = null;
  let digestOpen = true;

  async function loadDigest() {
    try {
      digest = await api('/api/digest');
    } catch (e) {
      digest = { failed: e.message };
    }
    renderList();
  }

  function digestCard() {
    if (!digest) { loadDigest(); return null; }
    if (digest.failed || digest.configured === false) return null;
    /* Nothing to say is worth saying once, quietly, rather than with an
       empty panel that looks like a failure to load. */
    if (!digest.n && !digest.errors) {
      return el('div', { class: 'digest quiet' }, [
        el('span', { text: 'Nobody else has done anything since '
                         + when(digest.since) + '.' }),
      ]);
    }
    const box = el('div', { class: 'digest' + (digestOpen ? '' : ' shut') });
    box.appendChild(el('div', { class: 'digest-head' }, [
      el('strong', { text: 'Since you last looked' }),
      el('span', { class: 'digest-when', text: when(digest.since) }),
      el('div', { style: 'flex:1' }),
      el('button', {
        class: 'linkish', text: digestOpen ? 'hide' : 'show',
        onclick: () => { digestOpen = !digestOpen; renderList(); },
      }),
      /* Marking it read is deliberate and separate. */
      el('button', {
        class: 'btn ghost sm', text: 'Mark as seen',
        title: 'Moves the mark to now. Nothing else changes.',
        onclick: async () => {
          try {
            await apiPost('/api/digest/seen', {});
            digest = null;
            loadDigest();
            toast('Caught up.', 'ok');
          } catch (e) { toast(e.message, 'err'); }
        },
      }),
    ]));
    if (!digestOpen) return box;

    const body = el('div', { class: 'digest-body' });
    body.appendChild(el('div', { class: 'digest-line' }, [
      el('strong', { text: Number(digest.n).toLocaleString() }),
      el('span', { text: ' action' + (digest.n === 1 ? '' : 's') + ' by ' }),
      el('span', { text: (digest.by_person || [])
        .map((x) => x.who + ' (' + x.n.toLocaleString() + ')').join(', ')
        || 'nobody' }),
      digest.errors
        ? el('span', { class: 'digest-err',
                       text: '  ·  ' + digest.errors + ' error'
                           + (digest.errors === 1 ? '' : 's') })
        : null,
    ].filter(Boolean)));
    /* The headline is a real count; the breakdown is computed from as much
       of it as one page holds. When those differ the card has to say so --
       "2,018 actions by Rain (999)" is two numbers that plainly do not add
       up, and a reader can only conclude that one of them is wrong. */
    if (digest.partial) {
      body.appendChild(el('div', { class: 'digest-partial',
        text: 'The names above account for '
            + Number(digest.counted).toLocaleString() + ' of those — the '
            + 'most recent page. The total is exact; the split is what fits '
            + 'in one read.' }));
    }

    if ((digest.by_kind || []).length) {
      body.appendChild(el('div', { class: 'digest-kinds' },
        digest.by_kind.slice(0, 8).map((k) => el('span', {
          class: 'flagchip sm', text: k.kind + ' ' + k.n,
        }))));
    }
    /* Which recordings, because that is the part somebody acts on -- "Rain
       has been in m5 s7" is a reason to go and look. */
    if ((digest.sessions || []).length) {
      body.appendChild(el('div', { class: 'section-label',
                                   text: 'Recordings touched' }));
      for (const s of digest.sessions) {
        body.appendChild(el('div', { class: 'digest-sess' }, [
          el('span', { class: 'ds-key', text: s.key }),
          el('span', { class: 'ds-who', text: s.who.join(', ') }),
          el('span', { class: 'ds-n', text: s.n + ' action(s)' }),
        ]));
      }
    }
    box.appendChild(body);
    return box;
  }

  function when(iso) {
    const t = Date.parse(iso);
    if (!isFinite(t)) return String(iso || '');
    const secs = (Date.now() - t) / 1000;
    if (secs < 90) return 'a moment ago';
    if (secs < 5400) return Math.round(secs / 60) + ' minutes ago';
    if (secs < 172800) return Math.round(secs / 3600) + ' hours ago';
    return Math.round(secs / 86400) + ' days ago';
  }

  function renderList() {
    renderTimeline();
    const host = $('#histList');
    host.innerHTML = '';

    /* On arrival, above everything. "What has everybody else been doing"
       is the question somebody opens this view with, and it used to take
       reading four hundred rows to answer.

       Its own host, outside the list: it is a summary of the view, and it
       has to survive the list being re-rendered by a filter keystroke
       without being rebuilt each time. */
    const dgHost = $('#histDigest');
    if (dgHost) {
      const dg = digestCard();
      dgHost.innerHTML = '';
      if (dg) dgHost.appendChild(dg);
      dgHost.hidden = !dg;
    }

    if (mode === 'activity') {
      host.appendChild(whoBar());
      const list = visibleActivity();
      $('#histSub').textContent = list.length + ' of ' + activity.length
        + ' logged action(s)'
        + (who === 'everyone' ? '  ·  everyone' : '  ·  this machine');
      if (scopeNote) {
        host.appendChild(el('div', { class: 'ecx-warn',
          text: 'Showing this machine only: ' + scopeNote
              + '. Somebody else’s actions would be missing.' }));
      }
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
          /* Who and where, when the list is the whole lab's. Left out on
             this machine's own log, where the answer is always the same and
             the column would be a stripe of one repeated name. */
          who === 'everyone'
            ? el('span', { class: 'hist-who',
                           text: a.user || a.machine || '' }) : null,
          /* The one thing worth reading off the row rather than opening
             it: which recording. */
          el('span', { class: 'hist-what', text: rowGist(a) }),
          el('span', { class: 'tm',
            title: BARRY.whenRaw(a.at),
            text: BARRY.when(a.at, 'stamp') }),
        ].filter(Boolean)));
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
        el('span', { class: 'tm', title: BARRY.whenRaw(at),
                     text: BARRY.when(at, 'stamp') }),
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
        el('p', { class: 'detail-path', title: BARRY.whenRaw(a.at),
                  text: BARRY.when(a.at, 'second')
                      + (a.at ? '   (recorded as ' + a.at + ')' : '') }),
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

  /* Which error is open, and what was happening around it.

     Keyed by error id rather than held as one value: the list can have
     several open at once, and collapsing one to read another would make
     comparing two failures a matter of memory. */
  const ctxOpen = new Set();
  const ctxData = {};        // error id -> the window, once fetched

  /* The machines that sync here. Read on demand rather than polled: this is
     a table somebody looks at, not a status light. */
  let devices = null;
  let devicesAt = 0;
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
      /* The redundancy copy, where somebody can actually look at it. A
         backup nobody can inspect is a backup nobody trusts. */
      el('button', {
        class: 'pill' + (mode === 'backup' ? ' active' : ''),
        text: 'JSON backup',
        title: 'The JSON shards on disk \u2014 the redundancy copy behind '
             + 'the shared database',
        onclick: () => { mode = 'backup'; render(); loadBackup(); },
      }),
    ]));

    if (mode === 'backup') { renderBackup(host); return; }
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
        /* The header is the handle. An error is worth reading in the
           context of what somebody was doing, and that context is one
           request away -- so opening it should not need a second control
           to find. */
        el('div', {
          class: 'ec-top ec-click' + (ctxOpen.has(e.id) ? ' open' : ''),
          title: 'What was happening in the five minutes before this',
          onclick: () => toggleContext(e),
        }, [
          el('span', { class: 'ec-caret',
                       text: ctxOpen.has(e.id) ? '\u25be' : '\u25b8' }),
          el('span', { class: 'ec-where', text: e.where || 'unknown' }),
          el('span', { class: 'flagchip', text: e.id }),
          e.machine ? el('span', { class: 'flagchip', text: e.machine }) : null,
          el('span', { class: 'ec-when', title: BARRY.whenRaw(e.at),
                       text: BARRY.when(e.at, 'second') }),
        ].filter(Boolean)),
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
      if (ctxOpen.has(e.id)) card.appendChild(contextPanel(e));
      host.appendChild(card);
    }
  }

  /* ======================================================================
     Errors, features 1-3 -- grouping, triage and a bundle
     The same failure logged forty times is one problem, not forty. Groups
     fold on a signature that ignores paths, timestamps and numbers; marking
     one resolved clears every past repeat and any future one that matches.
     ====================================================================== */
  /* ==================================================================
     Which device
     ==================================================================
     Shared by Errors and the Debug trace, because "the rig" is one thought
     and having to pick it twice is two.
     ================================================================== */
  let devPick = '';            // '' = all of them
  let devFeed = null;          // the chosen machine's feed, when Debug wants it
  let devFeedFor = null;

  function deviceBar(kind) {
    const known = (devices && devices.devices) || [];
    /* Every machine the errors mention, plus every machine that syncs. A
       machine can have errors on record and have stopped syncing, and it
       would drop off a list built only from the device table. */
    /* Archived computers are not offered. Their rows stay in the log and
       stay readable by picking them in the panel; they just do not clutter
       a chooser for ever. */
    const live = known.filter((d) => !d.archived);
    /* Keyed on the machine id, not the name, because the groups are -- and
       because the name is not an identity: one computer here has filed
       errors under five different labels and two computers have shared
       one. Comparing a name to an id matched nothing, which would have
       filtered the whole list away. */
    const seen = new Set(live.map((d) => d.id).filter(Boolean));
    const labels = {};
    for (const d of live) {
      if (d.id) labels[d.id] = d.label || d.hostname || d.id;
    }
    /* A computer that has errors on record and has stopped syncing is not
       in the device table, so its id comes off the groups. Its label comes
       off the group too -- the table is the only other place one lives. */
    for (const g of groups) {
      if (!g.machine) continue;
      seen.add(g.machine);
      if (!labels[g.machine]) {
        labels[g.machine] = g.machine_label || g.machine;
      }
    }
    /* Sorted by what is on screen. Sorting shard ids puts
       "barrylab-d8e8" before "desktop-..." for reasons nobody can see. */
    const names = Array.from(seen).sort(
      (a, b) => String(labels[a] || a).localeCompare(String(labels[b] || b)));
    if (!devices) loadDevices();

    const online = (id) => {
      const d = live.find((x) => x.id === id);
      return d ? d.online : null;
    };
    /* "Bluebarry (DESKTOP-4H65AI7)" on the chip too, or the picker and the
       panel disagree about what the machines are called. */
    const shown = (id) => labels[id] || id;
    return el('div', { class: 'res-toolbar dev-bar' }, [
      /* A button, not a label. "Which computers are there and what are
         they called" is the question this word raises, so it is the thing
         that answers it. */
      el('button', {
        class: 'dev-bar-label as-button',
        title: 'Name this computer, archive the ones that have gone, and '
             + 'see which names in the log belong to which machine',
        onclick: () => deviceManager(),
      }, [
        el('span', { text: 'Device' }),
        el('span', { class: 'dev-bar-caret', text: '\u2699' }),
      ]),
      el('span', { class: 'ctl-seg' }, [
        el('button', {
          class: 'mini' + (devPick ? '' : ' on'),
          text: 'All', title: 'Every machine',
          onclick: () => { devPick = ''; render(); },
        }),
      ].concat(names.map((name) => el('button', {
        class: 'mini' + (devPick === name ? ' on' : ''),
        title: name + (online(name) === null ? ''
                       : online(name) ? ' — syncing now'
                                      : ' — nothing pushed for over 5 minutes'),
        onclick: () => { devPick = name; render(); },
      }, [
        el('span', { class: 'dev-dot'
                            + (online(name) ? ' on' : '')
                            + (online(name) === null ? ' unknown' : '') }),
        el('span', { text: shown(name) }),
      ])))),
      el('div', { style: 'flex:1' }),
      kind === 'debug' && devPick
        ? el('span', { class: 'hint',
            text: 'Its actions and errors, from the shared log. The request '
                + 'trail is per-machine and stays where it was made.' })
        : null,
    ].filter(Boolean));
  }

  async function loadDevFeed(machine) {
    devFeedFor = machine;
    devFeed = null;
    render();
    try {
      devFeed = await api('/api/devices/feed?limit=140&machine='
                          + encodeURIComponent(machine));
    } catch (e) {
      devFeed = { failed: e.message };
    }
    render();
  }

  /* One machine's recent life, newest first. Errors and actions in one
     column rather than two, because the useful shape is "these four things
     happened and then it broke". */
  function devFeedPanel() {
    if (devFeedFor !== devPick) { loadDevFeed(devPick); }
    const box = el('div', { class: 'dev-feed' });
    if (!devFeed) {
      box.appendChild(el('div', { class: 'hint', text: 'Reading…' }));
      return box;
    }
    if (devFeed.failed) {
      box.appendChild(el('div', { class: 'hint',
        text: 'Could not read that machine: ' + devFeed.failed }));
      return box;
    }
    const rows = devFeed.feed || [];
    if (!rows.length) {
      box.appendChild(el('div', { class: 'hint',
        text: 'Nothing from ' + devPick + ' in the shared log yet. It may '
            + 'not have synced since it was last used.' }));
      return box;
    }
    for (const r of rows) {
      box.appendChild(el('div', {
        class: 'dev-feed-row' + (r.kind === 'error' ? ' err' : ''),
        title: typeof r.detail === 'object'
          ? JSON.stringify(r.detail, null, 1) : String(r.detail || ''),
      }, [
        el('span', { class: 'dfr-at', title: BARRY.whenRaw(r.at),
                     text: BARRY.when(r.at, 'stamp') }),
        el('span', { class: 'dfr-kind',
                     text: r.kind === 'error' ? '!' : '·' }),
        el('span', { class: 'dfr-what', text: r.what || '' }),
        el('span', { class: 'dfr-detail',
          text: typeof r.detail === 'object'
            ? shortDetail(r.detail) : String(r.detail || '').slice(0, 90) }),
      ]));
    }
    return box;
  }

  /* ==================================================================
     What was happening when it broke
     ================================================================== */
  async function toggleContext(e) {
    if (ctxOpen.has(e.id)) {
      ctxOpen.delete(e.id);
      render();
      return;
    }
    ctxOpen.add(e.id);
    render();
    if (ctxData[e.id]) return;      // already fetched; the panel has it
    try {
      ctxData[e.id] = await apiPost('/api/errors/context',
                                    { at: e.at, machine: e.machine });
    } catch (err) {
      ctxData[e.id] = { failed: err.message };
    }
    render();
  }

  function contextPanel(e) {
    const got = ctxData[e.id];
    const box = el('div', { class: 'ec-context' });
    if (!got) {
      box.appendChild(el('div', { class: 'hint', text: 'Reading the log…' }));
      return box;
    }
    if (got.failed) {
      box.appendChild(el('div', { class: 'hint',
        text: 'Could not read the log: ' + got.failed }));
      return box;
    }

    const acts = got.actions || [];
    box.appendChild(el('div', { class: 'ecx-head' }, [
      el('span', { class: 'section-label',
        text: 'The ' + Math.round((got.before_s || 300) / 60)
            + ' minutes before, and ' + (got.after_s || 60) + 's after' }),
      el('div', { style: 'flex:1' }),
      el('span', { class: 'hint',
        text: acts.length + ' action' + (acts.length === 1 ? '' : 's')
            + (got.machine ? '  ·  ' + got.machine : '') }),
    ]));

    /* Said out loud when the cloud could not be reached, because "nothing
       was happening" and "I could not find out what was happening" look
       identical in an empty list and only one of them means anything. */
    if (got.cloud_error) {
      box.appendChild(el('div', { class: 'ecx-warn',
        text: 'Only this machine’s own log: the shared copy could not '
            + 'be read (' + got.cloud_error + '). Another machine’s '
            + 'actions would be missing.' }));
    }

    if (!acts.length) {
      box.appendChild(el('div', { class: 'hint',
        text: got.cloud_error
          ? 'Nothing in this machine’s log for that window.'
          : 'Nothing was logged in that window — which usually means '
            + 'the failure happened before anybody touched anything, or on '
            + 'a machine whose log has not synced yet.' }));
      return box;
    }

    const errAt = String(e.at || '');
    const rows = el('div', { class: 'ecx-rows' });
    let markPlaced = false;
    for (const a of acts) {
      /* The error itself, in its place in the sequence. Without it the list
         is a set of actions with no indication which side of the failure
         each one is on -- which is the only thing the list is for. */
      if (!markPlaced && String(a.at || '') >= errAt) {
        rows.appendChild(errMarker(e));
        markPlaced = true;
      }
      rows.appendChild(el('div', { class: 'ecx-row' }, [
        el('span', { class: 'ecx-at', text: String(a.at || '').slice(11, 19) }),
        el('span', { class: 'ecx-action', text: a.action || '' }),
        a.view ? el('span', { class: 'flagchip sm', text: a.view }) : null,
        el('span', { class: 'ecx-detail',
          text: a.detail ? shortDetail(a.detail) : '' }),
      ].filter(Boolean)));
    }
    if (!markPlaced) rows.appendChild(errMarker(e));
    box.appendChild(rows);

    /* Other failures in the same window. One fault often arrives as six,
       and the first of them is the one worth reading. */
    const others = (got.errors || []).filter((x) => String(x.at) !== errAt);
    if (others.length) {
      box.appendChild(el('div', { class: 'section-label',
        text: others.length + ' other error'
            + (others.length === 1 ? '' : 's') + ' in the same window' }));
      for (const o of others) {
        box.appendChild(el('div', { class: 'ecx-row other' }, [
          el('span', { class: 'ecx-at', text: String(o.at || '').slice(11, 19) }),
          el('span', { class: 'ecx-action', text: o.where || '' }),
          el('span', { class: 'ecx-detail', text: (o.message || '').slice(0, 90) }),
        ]));
      }
    }
    return box;
  }

  function errMarker(e) {
    return el('div', { class: 'ecx-row here' }, [
      el('span', { class: 'ecx-at', text: String(e.at || '').slice(11, 19) }),
      el('span', { class: 'ecx-action', text: '◀ ' + (e.where || 'error') }),
      el('span', { class: 'ecx-detail', text: (e.message || '').slice(0, 90) }),
    ]);
  }

  /* A detail blob as one short line. The whole object is in the debug
     report; here it competes for width with the action name, and an action
     name that gets pushed off the row tells you nothing at all. */
  function shortDetail(d) {
    if (d === null || d === undefined) return '';
    if (typeof d !== 'object') return String(d).slice(0, 70);
    const bits = [];
    for (const [k, v] of Object.entries(d)) {
      if (v === null || v === undefined || v === '') continue;
      const txt = typeof v === 'object'
        ? (Array.isArray(v) ? v.length + ' items' : '{…}')
        : String(v);
      bits.push(k + '=' + txt.slice(0, 24));
      if (bits.length >= 4) break;
    }
    return bits.join('  ');
  }

  /* ==================================================================
     Which machines sync here, and whether they still do
     ==================================================================
     `machines.last_seen` has been a heartbeat all along -- the sync loop
     stamps it on every push -- and nothing read it. So "is the rig still
     sending its logs" was a question you answered by walking down the
     corridor.

     Online and sending are deliberately separate columns. A machine can be
     reachable and have stopped logging, and that is the more interesting
     failure of the two.
     ================================================================== */
  async function loadDevices(force) {
    if (devices && !force && Date.now() - devicesAt < 20000) return;
    try {
      devices = await api('/api/devices');
      devicesAt = Date.now();
    } catch (e) {
      devices = { failed: e.message };
    }
    render();
  }

  function devicePanel() {
    const box = el('div', { class: 'dev-panel' });
    box.appendChild(el('div', { class: 'sec-head' }, [
      el('div', { class: 'section-label', text: 'Devices' }),
      el('div', { style: 'flex:1' }),
      el('button', {
        class: 'btn ghost sm', text: 'Refresh',
        onclick: () => loadDevices(true),
      }),
    ]));

    if (!devices) {
      loadDevices();
      box.appendChild(el('div', { class: 'hint', text: 'Asking…' }));
      return box;
    }
    if (devices.failed) {
      box.appendChild(el('div', { class: 'hint',
        text: 'Could not read the device list: ' + devices.failed }));
      return box;
    }
    if (!devices.configured) {
      box.appendChild(el('div', { class: 'hint',
        text: 'No cloud configured, so there is nothing to compare against '
            + '— this machine is the only one BARRY can see.' }));
      return box;
    }

    const all = devices.devices || [];
    if (!all.length) {
      box.appendChild(el('div', { class: 'hint',
        text: 'No machines have synced yet.' }));
      return box;
    }
    const list = all.filter((d) => !d.archived || showRetired);
    const retired = all.filter((d) => d.archived).length;
    for (const d of list) {
      box.appendChild(el('div', {
        class: 'dev-row' + (d.is_me ? ' me' : '')
               + (d.archived ? ' archived' : ''),
      }, [
        el('span', { class: 'dev-dot' + (d.online ? ' on' : ''),
          title: d.online ? 'Pushed within the last five minutes'
                          : 'Nothing pushed for over five minutes' }),
        /* The friendly name with the computer's own name after it. Two of
           these machines have friendly names differing by the case of one
           letter and are different computers; one has two names and is one
           computer. The bracket is what tells them apart. */
        el('strong', { class: 'dev-host', text: d.label || d.hostname || d.id,
          title: 'Known to BARRY as ' + d.id }),
        d.is_me ? el('span', { class: 'flagchip sm', text: 'this one' }) : null,
        /* The names it used to answer to, so old log rows are accounted
           for rather than looking like a fourth machine. */
        (d.also_known_as || []).length
          ? el('span', { class: 'dev-aka',
              title: 'Rows in the shared log under this machine\u2019s '
                   + 'older names are counted here',
              text: 'also ' + d.also_known_as.join(', ') }) : null,
        d.archived
          ? el('span', { class: 'flagchip sm', text: 'archived' }) : null,
        el('span', { class: 'dev-user', text: d.user || '' }),
        el('div', { style: 'flex:1' }),
        /* Two facts, not one. "Seen" is the sync; "sending" is whether it
           has anything to say. A machine that is up and silent is the case
           worth noticing. */
        el('span', { class: 'dev-col',
          title: 'When it last pushed anything',
          text: d.age_s == null ? 'never' : ago(d.age_s) }),
        el('span', { class: 'dev-col',
          title: 'Actions in the most recent slice of the shared log',
          text: d.recent_actions + ' actions' }),
        el('span', { class: 'dev-col' + (d.recent_errors ? ' warn' : ''),
          title: 'Errors in the most recent slice',
          text: d.recent_errors + ' errors' }),
        /* Retiring a computer. Same promise as archiving a person: it
           wrote every row it wrote and none of that changes -- it just
           stops cluttering the pickers. Not offered for this machine,
           where it would only confuse. */
        d.is_me ? null : el('button', {
          class: 'dev-arch' + (d.archived ? ' on' : ''),
          title: d.archived
            ? d.label + ' is archived. Click to bring it back.'
            : 'Archive ' + d.label + ': off the device lists. Everything it '
              + 'recorded stays on record and stays counted.',
          text: d.archived ? '\u21ba' : '\u25f4',
          onclick: () => archiveDevice(d, !d.archived),
        }),
      ].filter(Boolean)));
    }
    if (retired) {
      box.appendChild(el('button', {
        class: 'prof-arch-toggle' + (showRetired ? ' on' : ''),
        text: (showRetired ? '\u25be  ' : '\u25b8  ')
              + retired + ' archived',
        onclick: () => { showRetired = !showRetired; render(); },
      }));
    }
    /* Names in the log that no machine answers to. Reported rather than
       folded in: the only safe way to claim one is an id, and matching by
       shape would have merged two people's computers. */
    if ((devices.unclaimed_names || []).length) {
      box.appendChild(el('div', { class: 'hint dev-unclaimed' }, [
        el('strong', { text: 'Also in the log: ' }),
        el('span', { text: devices.unclaimed_names.join(', ')
          + ' \u2014 ' + (devices.unclaimed_names.length === 1
            ? 'a name no machine in the table answers to. It is an older '
              + 'name for one of these computers, or one that never '
              + 'registered.'
            : 'names no machine in the table answers to. They are older '
              + 'names for these computers, or machines that never '
              + 'registered.')
          + ' Nothing is guessed: a machine is only claimed by its id.' }),
      ]));
    }
    box.appendChild(el('p', { class: 'hint',
      text: 'Online means it pushed within five minutes. The sync loop '
          + 'pushes at least once a minute, so a machine quiet for longer '
          + 'has either been closed or has stopped syncing. The name in '
          + 'brackets is what the computer calls itself \u2014 two of these '
          + 'friendly names differ by one letter and are different '
          + 'machines.' }));
    return box;
  }

  let showRetired = false;

  /* Managing the computers.

     Reached from the word DEVICE. Everything here is about machines and
     nothing about people -- the two used to share a record, and that is
     precisely how one computer came to file errors under five different
     names while two computers were both set to the same one. */
  async function deviceManager() {
    let mine = null;
    try {
      mine = (await api('/api/device')).device;
    } catch (e) {
      mine = null;
    }
    await loadDevices(true);
    drawDeviceManager(mine);
  }

  function drawDeviceManager(mine) {
    const all = (devices && devices.devices) || [];
    const body = el('div', { class: 'mb dev-mgr' });

    /* This computer first, with the box that names it. */
    if (mine) {
      const box = el('input', {
        type: 'text', class: 'dev-name-in', value: mine.named ? mine.name : '',
        placeholder: mine.real || 'this computer',
      });
      const say = el('div', { class: 'hint' });
      const paintSay = () => {
        say.textContent = mine.named
          ? 'Named here. Its own name is ' + mine.real + '.'
          : 'Not named yet, so BARRY uses the name the computer reports: '
            + mine.real + '.';
      };
      paintSay();
      body.appendChild(el('div', { class: 'dev-mgr-me' }, [
        el('div', { class: 'section-label', text: 'This computer' }),
        el('div', { class: 'dev-mgr-row' }, [
          box,
          el('button', {
            class: 'btn sm', text: 'Save name',
            onclick: async () => {
              try {
                const res = await apiPost('/api/device', { name: box.value });
                mine = res.device;
                paintSay();
                await loadDevices(true);
                toast('This computer is now called ' + mine.name + '. '
                      + 'Nothing about who it credits work to has changed.',
                      'ok', 6000);
                drawDeviceManager(mine);
              } catch (e) { toast(e.message, 'err', 8000); }
            },
          }),
        ]),
        say,
        el('p', { class: 'hint',
          text: 'This is what gets stamped on every error, action and run '
              + 'from this computer. It belongs to the computer, not to '
              + 'you \u2014 switching who BARRY credits work to leaves it '
              + 'alone.' }),
        mine.adopted_from_profile
          ? el('p', { class: 'hint',
              text: 'Carried over from the profile, where it used to live: '
                  + mine.adopted_from_profile }) : null,
        el('p', { class: 'hint dev-mgr-id',
          text: 'Identity: ' + mine.id + '  \u2014 derived from the '
              + 'hostname and the network address, and what BARRY actually '
              + 'compares. The name above is only for reading.' }),
      ].filter(Boolean)));
    }

    /* Everybody else. */
    const others = all.filter((d) => !d.is_me);
    body.appendChild(el('div', { class: 'section-label',
      text: others.length ? 'Other computers' : 'No other computers yet' }));
    for (const d of others) {
      body.appendChild(el('div', {
        class: 'dev-mgr-other' + (d.archived ? ' archived' : ''),
      }, [
        el('span', { class: 'dev-dot' + (d.online ? ' on' : '') }),
        el('strong', { text: d.label || d.hostname || d.id }),
        (d.also_known_as || []).length
          ? el('span', { class: 'dev-aka',
              text: 'also ' + d.also_known_as.join(', ') }) : null,
        el('span', { class: 'dev-user', text: d.user || '' }),
        el('div', { style: 'flex:1' }),
        el('span', { class: 'dev-col', text: d.age_s == null
          ? 'never synced' : ago(d.age_s) }),
        el('button', {
          class: 'btn ghost sm',
          text: d.archived ? 'Bring back' : 'Archive',
          title: d.archived
            ? 'Put it back on the lists'
            : 'Take it off the device lists. Everything it recorded stays '
              + 'on record and stays counted.',
          onclick: () => archiveDevice(d, !d.archived)
            .then(() => deviceManager()),
        }),
      ].filter(Boolean)));
    }

    /* The two things the data says that nothing used to show. */
    const unclaimed = (devices && devices.unclaimed_names) || [];
    const ambiguous = (devices && devices.ambiguous_labels) || [];
    if (unclaimed.length) {
      body.appendChild(el('div', { class: 'hint dev-unclaimed' }, [
        el('strong', { text: 'Names in the log with no machine: ' }),
        el('span', { text: unclaimed.join(', ')
          + ' \u2014 older names for these computers, or machines that '
          + 'never registered. Nothing is guessed: a machine is only '
          + 'claimed by its identity.' }),
      ]));
    }
    if (ambiguous.length) {
      body.appendChild(el('div', { class: 'ecx-warn' }, [
        el('strong', { text: 'More than one computer answers to: ' }),
        el('span', { text: ambiguous.join(', ')
          + '. Their rows cannot be told apart by name, which is why the '
          + 'real hostname is shown in brackets. Rename one of them above '
          + 'to clear it.' }),
      ]));
    }

    showModal(el('div', { class: 'dev-mgr-wrap' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Computers' }),
        el('span', { class: 'sub',
          text: 'what they are called, and which have gone' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      body,
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn', text: 'Done', onclick: closeModal }),
      ]),
    ]), { replace: true });
  }

  async function archiveDevice(d, yes) {
    if (yes) {
      const ok = await BARRY.confirm(
        'Archive ' + d.label + '?',
        'It stays on every action and error it recorded, and those stay '
        + 'counted. Archiving only takes it off the device lists.'
        + '\n\nIt applies everywhere, not just here.',
        'Archive');
      if (!ok) return;
    }
    try {
      const res = await apiPost('/api/devices/archive',
                                { id: d.id, archived: !!yes });
      if (res && res.run) {
        toast('The shared database needs supabase/' + res.run
              + ' run first.', 'err', 9000);
        return false;
      }
      await loadDevices(true);
      toast(yes ? d.label + ' archived.' : d.label + ' is back.', 'ok');
      return true;
    } catch (e) {
      toast('Could not archive ' + d.label + ': ' + e.message, 'err', 8000);
      return false;
    }
  }

  /* ======================================================================
     The JSON backup

     Supabase is the primary route. These files are the redundancy: what
     survives an unreachable database, what holds the version snapshots that
     are too big to send, and what a fresh clone of the repository arrives
     with. Read-only -- this is the copy of record and the interface has no
     business editing it.
     ====================================================================== */
  let backup = null;
  let backupOpen = {};
  let shardShown = null;

  async function loadBackup(force) {
    if (backup && !force) { render(); return; }
    try {
      backup = await api('/api/backup/json');
    } catch (e) {
      backup = { failed: e.message };
    }
    render();
  }

  function kb(n) {
    if (n == null) return '';
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / 1048576).toFixed(1) + ' MB';
  }

  function renderBackup(host) {
    if (!backup) { loadBackup(); }
    host.appendChild(el('div', { class: 'res-toolbar' }, [
      el('span', { class: 'hint',
        text: backup && backup.role ? backup.role : 'Reading the shards\u2026' }),
      el('div', { style: 'flex:1' }),
      el('button', {
        class: 'btn ghost sm', text: 'Refresh',
        onclick: () => loadBackup(true),
      }),
    ]));

    if (!backup) {
      host.appendChild(el('div', { class: 'hint', text: 'Reading\u2026' }));
      return;
    }
    if (backup.failed) {
      host.appendChild(el('div', { class: 'hint',
        text: 'Could not read the shards: ' + backup.failed }));
      return;
    }

    host.appendChild(el('div', { class: 'fb-stats' }, [
      el('span', { class: 'stat-chip',
                   text: backup.files + ' file(s)' }),
      el('span', { class: 'stat-chip', text: kb(backup.bytes) }),
      el('span', { class: 'stat-chip',
                   text: (backup.folders || []).length + ' folder(s)' }),
      el('span', { class: 'stat-chip', title: backup.root,
                   text: 'on disk' }),
    ]));

    for (const g of (backup.folders || [])) {
      const open = !!backupOpen[g.folder];
      host.appendChild(el('button', {
        class: 'bk-folder' + (open ? ' on' : ''),
        onclick: () => { backupOpen[g.folder] = !open; render(); },
      }, [
        el('span', { class: 'bk-caret', text: open ? '\u25be' : '\u25b8' }),
        el('strong', { text: g.folder }),
        g.what ? el('span', { class: 'bk-what', text: g.what }) : null,
        el('div', { style: 'flex:1' }),
        /* How many machines have written into it. A folder with one is a
           folder only this computer contributes to. */
        g.machines.length
          ? el('span', { class: 'bk-col',
                         text: g.machines.length + ' machine(s)' }) : null,
        el('span', { class: 'bk-col', text: g.n + ' file(s)' }),
        el('span', { class: 'bk-col', text: kb(g.bytes) }),
      ].filter(Boolean)));

      if (!open) continue;
      const list = el('div', { class: 'bk-files' });
      /* Bounded: `sessions` alone is 785 files, and a wall of them is not
         a view of anything. The rest are a click away in the folder. */
      const shown = g.files.slice(0, 60);
      for (const f of shown) {
        list.appendChild(el('button', {
          class: 'bk-file' + (shardShown
                              && shardShown.folder === g.folder
                              && shardShown.name === f.name ? ' on' : ''),
          onclick: () => openShard(g.folder, f.name),
        }, [
          el('span', { class: 'bk-name', text: f.base }),
          el('span', { class: 'bk-machine' + (f.mine ? ' mine' : ''),
                       text: f.machine || '\u2014' }),
          el('div', { style: 'flex:1' }),
          el('span', { class: 'bk-col', text: kb(f.bytes) }),
          el('span', { class: 'bk-col', title: BARRY.whenRaw(f.at),
                       text: BARRY.when(f.at, 'stamp') }),
        ]));
      }
      if (g.files.length > shown.length) {
        list.appendChild(el('div', { class: 'hint',
          text: 'and ' + (g.files.length - shown.length) + ' more, newest '
              + 'first \u2014 open the folder on disk to see them all.' }));
      }
      host.appendChild(list);
    }

    if (shardShown) host.appendChild(shardPanel());
  }

  async function openShard(folder, name) {
    shardShown = { folder: name ? folder : null, name: name, text: null };
    render();
    try {
      const got = await api('/api/backup/json/'
                            + encodeURIComponent(folder) + '/'
                            + encodeURIComponent(name));
      shardShown = Object.assign({ folder: folder, name: name }, got);
    } catch (e) {
      shardShown = { folder: folder, name: name, failed: e.message };
    }
    render();
  }

  function shardPanel() {
    const sh = shardShown;
    const box = el('div', { class: 'bk-view' });
    box.appendChild(el('div', { class: 'sec-head' }, [
      el('div', { class: 'section-label',
                  text: sh.folder + ' / ' + sh.name }),
      el('div', { style: 'flex:1' }),
      sh.bytes != null
        ? el('span', { class: 'hint', text: kb(sh.bytes) }) : null,
      el('button', {
        class: 'btn ghost sm', text: 'Close',
        onclick: () => { shardShown = null; render(); },
      }),
    ].filter(Boolean)));
    if (sh.failed) {
      box.appendChild(el('div', { class: 'hint',
        text: 'Could not read it: ' + sh.failed }));
      return box;
    }
    if (sh.text == null) {
      box.appendChild(el('div', { class: 'hint', text: 'Reading\u2026' }));
      return box;
    }
    if (sh.clipped) {
      box.appendChild(el('div', { class: 'ecx-warn',
        text: 'Shown from the start and cut off \u2014 this file is larger '
            + 'than the viewer will load. Nothing is missing from the file '
            + 'itself; open it on disk to see the rest.' }));
    }
    box.appendChild(el('pre', { class: 'bk-json', text: sh.text }));
    return box;
  }

  function ago(sec) {
    if (sec == null) return 'never';
    if (sec < 90) return Math.round(sec) + 's ago';
    if (sec < 5400) return Math.round(sec / 60) + ' min ago';
    if (sec < 172800) return Math.round(sec / 3600) + ' h ago';
    return Math.round(sec / 86400) + ' days ago';
  }

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

    host.appendChild(deviceBar('debug'));
    /* Another machine's feed instead of this one's request trail.

       The trail is this process's own and is not collected from anywhere
       else -- which is right: nobody debugs by reading somebody else's HTTP
       log. What a remote machine publishes is its actions and its errors,
       and that is what this shows. */
    if (devPick && devPick !== ((devices || {}).machine)) {
      host.appendChild(devFeedPanel());
      return;
    }

    /* Which machines are syncing, above this session's own trace.

       The trace itself is per-process and in memory -- it is what THIS
       browser and THIS server did, and syncing raw request trails between
       machines would be a great deal of volume for very little: nobody
       debugs by reading somebody else's HTTP log. What is worth knowing
       across machines is whether each one is still reporting at all, which
       is what the table above answers. */
    host.appendChild(devicePanel());

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
    host.appendChild(deviceBar('errors'));
    const list = groups.filter((g) => !(hideResolved && g.resolved))
      .filter((g) => !devPick
                     || g.machine === devPick
                     || (g.machines || []).indexOf(devPick) >= 0);
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
      // Keyed on `key`, not `signature`: groups are per machine now, and
      // two machines' rows share a signature. Opening one would have opened
      // both.
      const gkey = g.key || g.signature;
      const open = openGroups.has(gkey);
      const card = el('div', {
        class: 'err-group' + (g.resolved ? ' resolved' : ''),
      });
      card.appendChild(el('div', {
        class: 'err-ghead',
        onclick: () => {
          if (open) openGroups.delete(gkey);
          else openGroups.add(gkey);
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
                       + (g.resolved_at ? BARRY.when(g.resolved_at, 'minute')
                                        : '?')
                       + ', and has happened again since',
                })
              : null,
            el('span', { text: g.message || '(no message)' }),
          ].filter(Boolean)),
          el('div', { class: 'err-gwhere',
                      text: (g.where || 'unknown')
                            + (g.machines.length > 1 ? '  \u00b7  also as '
                               + g.machines.join(', ') : '') }),
        ]),
        el('span', { class: 'err-gwhere',
                     title: BARRY.whenRaw(g.last),
                     text: BARRY.when(g.last, 'minute') }),
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
                title: BARRY.whenRaw(g.first),
                text: 'first seen ' + BARRY.when(g.first, 'minute') }),
        ]));

        for (const rec of g.records) {
          body.appendChild(el('div', { class: 'err-occ',
            title: BARRY.whenRaw(rec.at),
            text: BARRY.when(rec.at, 'second')
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
      /* Scoped to the machine the group is for, when it is for one.
         "Fixed on the rig" and "fixed" are different claims, and the old
         call could only make the second -- so closing a fault you had
         only fixed in one place hid it everywhere. */
      await apiPost('/api/errors/resolve',
                    { signature: g.signature, machine: g.machine || null,
                      resolved: on, note });
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
