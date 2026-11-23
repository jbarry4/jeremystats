/* ==========================================================================
   kilosort.js -- Getting Kilosort running, running it, and then Phy.

   Kilosort is not hard to run. It is hard to *start* running: the first
   attempt fails for one of about eight reasons, and the error almost never
   says which. No CUDA build of torch. A probe file that describes a different
   probe. A binary written with the wrong channel count, which does not error
   at all -- it sorts happily and puts every unit in the wrong place. Bad
   channels given as CSC numbers when Kilosort counts rows from zero.

   Every one of those is checkable before anything runs, so this checks them
   before anything runs. The three panes are the three questions in order:

     Set up    can this machine do it at all, and if not, exactly what to type
     Run       what would happen to this recording, resolved against disk
     Phy       look at what it decided, and change your mind

   It does not hide the commands. Each pane shows what it is about to execute
   and there is a terminal button in the corner, because the moment a wrapper
   is in the way the right answer is a prompt in the right directory rather
   than a worse version of one.
   ========================================================================== */
'use strict';

BARRY.kilosort = (function () {
  let env = null;            // /api/kilosort/check
  let plan = null;           // /api/kilosort/plan for the chosen recording
  let sessions = [];
  let pick = null;           // the chosen recording row
  let probe = null;
  let settings = null;
  let invert = true;
  /* Cells first (PROJECT EVOLVE phase 7, 2026-11-21): reading the sorts
     already made is what this tool is for now; making new ones comes later. */
  let pane = 'cells';        // cells | setup | run | phy
  /* Which interpreter to use. Jarvis itself may be running on a Python torch
     does not build for -- 3.14, as it happens -- and every route here takes
     a `python` argument, so the fix is choosing one rather than installing
     anything. Null means "the one Jarvis is running on". */
  let python = null;
  let job = null;            // the running sort or install
  let phyGuide = null;
  let chosenRun = null;      // which results folder Phy would open
  let busy = false;

  /* ==================================================================
     Loading
     ================================================================== */
  async function load(host) {
    host.innerHTML = '';
    host.appendChild(el('p', { class: 'hint', text: 'Looking at what this '
      + 'machine has…' }));
    try {
      env = await api('/api/kilosort/check'
                      + (python ? '?python=' + encodeURIComponent(python) : ''));
      // First look: if this Python cannot run torch and another one here
      // can, start from the one that works rather than from the failure.
      if (python === null && env.python_ok === false && env.suggest_python) {
        python = env.suggest_python;
        env = await api('/api/kilosort/check?python='
                        + encodeURIComponent(python));
        env.switched = true;
      }
    } catch (e) {
      env = { rows: [], ready: false, error: e.message };
    }
    if (!probe) {
      // Prefer the described one: a probe file with a comment saying which
      // probe it is has been checked by a person.
      const withNote = (env.probes || []).filter((p) => p.note && p.kind === 'prb');
      probe = (withNote[0] || (env.probes || [])[0] || {}).path || null;
    }
    if (!settings) settings = ((env.settings || [])[0] || {}).path || null;
    if (!sessions.length) {
      try {
        // The shared copy (web/js/data.js), read only here.
        const reg = await BARRY.data.get('/api/registry', { maxAge: 60000 });
        sessions = BARRY.hk.flatten(reg).filter((s) => s.reachable);
      } catch (e) { sessions = []; }
    }
    // Nothing to run against yet means Set up is the only useful pane.
    if (!env.ready && pane === 'run') pane = 'setup';
    render(host);
  }

  /* ==================================================================
     The page
     ================================================================== */
  /* The host it was last drawn into: a repaint after a fetch (the Cells'
     lists) lands where the pane is, not wherever #tkResult happens to be. */
  let lastHost = null;
  function render(host) {
    const node = host || (lastHost && lastHost.isConnected ? lastHost : null)
      || document.getElementById('tkResult');
    if (!node) return;
    lastHost = node;
    node.innerHTML = '';

    node.appendChild(el('div', { class: 'ks-head' }, [
      el('div', {}, [
        el('h2', { text: 'Kilosort' }),
        el('p', { class: 'hint', text: 'Spike sorting, and the setup that '
          + 'usually stands between you and it.' }),
      ]),
      el('div', { class: 'seg' }, [
        segBtn('cells', 'Cells'),
        segBtn('setup', 'Set up'),
        segBtn('run', 'Run'),
        segBtn('phy', 'Phy'),
      ]),
      el('button', {
        class: 'btn ghost sm', text: 'Terminal here',
        title: 'A command prompt in the folder this pane is about, for when '
             + 'you would rather just type it',
        onclick: () => terminal(),
      }),
    ]));

    if (env && env.error) {
      node.appendChild(el('div', { class: 'ks-bad',
        text: 'Could not check this machine: ' + env.error }));
    }
    if (pane === 'cells') cellsPane(node);
    else if (pane === 'setup') setupPane(node);
    else if (pane === 'run') runPane(node);
    else phyPane(node);

    if (job) node.appendChild(jobBox());
  }

  function segBtn(id, label) {
    return el('button', {
      class: pane === id ? 'active' : '', text: label,
      onclick: () => { pane = id; render(); if (id === 'phy') loadGuide(); },
    });
  }

  /* ==================================================================
     Cells (PROJECT EVOLVE phase 7, 2026-11-21)

     The sorts the lab has made, read back -- a soft launch: read first,
     run later. Each recording sorted here is a row; a recording's cells
     are the curated ones (Isabella's export, or Phy's labels once
     somebody curates there), kept as CURATION VERSIONS that can be
     compared cell by cell, and banked as one Cell entry.

     The strip at the top is the whole pipeline for the recording chosen,
     each step lit by what exists on disk or in Jarvis.
     ================================================================== */
  const CS = { sorts: null, curated: 0, gid: null, d: null, version: null,
               cmp: null, busy: null, err: null, filter: '' };
  const VIEWED_KEY = 'barry.cells.viewed';
  const viewed = () => {
    try { return JSON.parse(localStorage.getItem(VIEWED_KEY) || '[]'); }
    catch (e) { return []; }
  };

  async function loadSorts(force) {
    CS.err = null;
    try {
      const got = await api('/api/cells/sorts' + (force ? '?force=1' : ''));
      CS.sorts = got.sorts || [];
      CS.curated = got.curated || 0;
    } catch (e) {
      CS.sorts = [];
      CS.err = e.message;
    }
    render();
  }

  async function openRec(gid, version) {
    CS.gid = gid;
    CS.cmp = null;
    CS.busy = 'Reading what this recording has…';
    render();
    try {
      CS.d = await api('/api/cells/' + encodeURIComponent(gid)
                       + (version ? '?version=' + version : ''));
      CS.version = CS.d.version;
    } catch (e) {
      CS.d = { ok: false, error: e.message, gid };
    }
    CS.busy = null;
    render();
  }

  async function readSource(kind) {
    const gid = CS.gid;
    CS.busy = kind === 'export' ? 'Reading Isabella’s export…'
                                : 'Reading Phy’s labels…';
    render();
    try {
      const got = await apiPost('/api/cells/' + encodeURIComponent(gid) + '/read',
                                { source: kind });
      toast('Read ' + got.cells + ' cells into curation v' + got.version
            + (got.exact === got.cells ? ', every one exactly a cluster of the sort.'
               : '.'), 'ok', 7000);
    } catch (e) {
      toast(e.message, 'err', 9000);
    }
    CS.busy = null;
    await openRec(gid);
    loadSorts(true);
  }

  /* Every curated recording not read yet, one after another. Reading makes
     a curation version; nothing is banked. */
  async function readAll() {
    const todo = (CS.sorts || []).filter((r) => r.export_n && !r.curation);
    if (!todo.length) { toast('Every export here has been read.', 'ok'); return; }
    for (let i = 0; i < todo.length; i++) {
      CS.busy = 'Reading ' + (i + 1) + ' of ' + todo.length + ': '
        + (todo[i].label || todo[i].gid);
      render();
      try {
        await apiPost('/api/cells/' + encodeURIComponent(todo[i].gid) + '/read',
                      { source: 'export' });
      } catch (e) {
        toast((todo[i].label || todo[i].gid) + ': ' + e.message, 'err', 9000);
      }
    }
    CS.busy = null;
    await loadSorts(true);
    toast('Read ' + todo.length + ' exports into curation versions. Nothing '
          + 'was banked.', 'ok', 7000);
  }

  function bankOne() {
    const d = CS.d || {};
    const cur = d.curation || {};
    const v = CS.version;
    const vrow = (cur.versions || []).find((x) => x.v === v) || {};
    return BARRY.ui.bankDialog({
      kind: 'entry',
      title: 'Bank the cells of ' + (d.label || d.gid),
      name: 'Cells · ' + (d.label || d.gid),
      what: 'One Cell entry for this recording’s sort.',
      facts: [
        (d.cells || []).length + ' cells from curation v' + v
          + (vrow.source ? ' (' + vrow.source + ')' : '') + ', of the sort '
          + ((d.run || {}).name || '') + '.',
        'One row per cell, its first to its last spike, with its CSC, layer '
          + 'and spike count. The spikes stay in the sort folder.',
        d.entry ? 'Continues ‘' + d.entry.name + '’, banked before.'
                : 'A new entry.',
      ],
      onBank: async ({ name, note }) => {
        const got = await apiPost('/api/cells/' + encodeURIComponent(d.gid)
                                  + '/bank', { version: v, name, note });
        toast((got.new ? 'Banked: ' : 'Banked again: ') + '‘' + got.name
              + '’, ' + got.n + ' cells.', 'ok', 7000);
      },
    }).then((done) => { if (done) { openRec(d.gid, v); loadSorts(true); } });
  }

  /* Every recording read and not banked, each as its own Cell entry, after
     one confirmation that says how many. */
  async function bankAll() {
    const todo = (CS.sorts || []).filter((r) => r.curation && !r.entry);
    if (!todo.length) {
      toast('Every recording read here has been banked.', 'ok');
      return;
    }
    const yes = await BARRY.confirm('Bank ' + todo.length + ' recordings’ cells',
      el('div', {}, [
        el('p', { text: 'Each recording read and not yet banked becomes one '
          + 'Cell entry, from its newest curation version: '
          + todo.map((r) => r.label || r.gid).join(', ') + '.' }),
        el('p', { class: 'hint', text: 'Banked under your name, as a Cell '
          + 'entry each. Nothing else changes.' }),
      ]), 'Bank ' + todo.length);
    if (!yes) return;
    let ok = 0;
    for (let i = 0; i < todo.length; i++) {
      CS.busy = 'Banking ' + (i + 1) + ' of ' + todo.length;
      render();
      try {
        await apiPost('/api/cells/' + encodeURIComponent(todo[i].gid) + '/bank', {});
        ok += 1;
      } catch (e) {
        toast((todo[i].label || todo[i].gid) + ': ' + e.message, 'err', 9000);
      }
    }
    CS.busy = null;
    await loadSorts(true);
    toast('Banked ' + ok + ' Cell entries.', 'ok', 7000);
  }

  async function compare(a, b) {
    CS.busy = 'Comparing v' + a + ' with v' + b + '…';
    render();
    try {
      CS.cmp = await api('/api/cells/' + encodeURIComponent(CS.gid)
                         + '/diff?a=' + a + '&b=' + b);
    } catch (e) {
      CS.cmp = { error: e.message };
    }
    CS.busy = null;
    render();
  }

  /* The pipeline for one recording, each step lit by what exists. */
  function stepsStrip(row, d) {
    const r = row || {};
    const dd = d || {};
    const seen = viewed().indexOf(r.gid) >= 0;
    const steps = [
      ['Binary', 'CSC_Raw.dat · perpl_NLX2Binary.m', !!r.binary],
      ['Sorted', 'Kilosort 4 · kilosort_automation.py', !!r.run],
      ['Curated', r.phy_edited ? 'Phy · cluster_group.tsv' : 'Phy, or by hand',
       !!(r.export_n || r.phy_edited)],
      ['Exported', 'timestamps\\<cell>.mat', !!r.export_n],
      ['Banked', r.entry ? r.entry.name : 'a Cell entry', !!r.entry],
      ['Viewed', 'Cells in Xplorefinder', seen],
    ];
    const firstOff = steps.findIndex((s) => !s[2]);
    return el('div', { class: 'ks-steps' }, steps.map((s, i) => el('div', {
      class: 'wf-stage ks-step' + (s[2] ? ' on' : '') + (i === firstOff ? ' next' : ''),
      title: s[2] ? 'Done' : (i === firstOff ? 'The next step' : 'Not yet'),
    }, [
      el('span', { class: 'wf-stage-n', text: (i + 1) + '  ' + s[0] }),
      el('span', { class: 'wf-stage-l', text: s[1] }),
      el('span', { class: 'ks-step-state', text: s[2] ? 'done'
                   : i === firstOff ? 'next' : 'not yet' }),
    ])).concat(dd.ok === false ? [] : []));
  }

  function sortRow(r) {
    const on = r.gid === CS.gid;
    const said = r.export_n
      ? r.export_n + ' curated' + (r.curation ? ' · read v' + r.curation.version : ' · not read')
        + (r.entry ? ' · banked' : '')
      : 'sorted, not curated';
    return el('button', {
      type: 'button', class: 'ks-cell-rec' + (on ? ' on' : '')
        + (r.export_n ? '' : ' uncurated'),
      'data-gid': r.gid,
      onclick: () => openRec(r.gid),
    }, [
      el('strong', { text: r.label || r.gid }),
      el('span', { class: 'hint', text: said }),
    ]);
  }

  function cellCard(c, d) {
    return BARRY.ui.workbenchCard({
      title: 'Cell ' + c.id,
      gid: d.gid, kind: 'cell-' + c.id,
      chips: [
        el('span', { class: 'flagchip', text: 'CSC ' + c.csc }),
        c.layer_name ? el('span', { class: 'flagchip ks-layer', text: c.layer_name })
                     : el('span', { class: 'flagchip ks-layer none', text: 'no layer said' }),
      ],
      count: Number(c.n).toLocaleString() + ' spikes',
      owner: { name: null },
      when: c.rate_hz != null ? c.rate_hz.toFixed(2) + ' Hz' : null,
      tally: [el('span', { class: 'hint', text: c.depth_um + ' µm on the probe · '
        + (c.first_s != null ? c.first_s.toFixed(1) + '–' + c.last_s.toFixed(1)
           + ' s' : '') })],
      actions: [
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Open in Xplorefinder',
          onclick: () => BARRY.cells.enter(d.gid, { cell: c.id, version: CS.version }) }),
      ],
      extra: 'ks-cellcard',
    });
  }

  function diffBlock(cmp, names) {
    if (cmp.error) {
      return el('p', { class: 'hint warn-line', text: 'Could not compare: ' + cmp.error });
    }
    const words = { kept: 'kept', changed: 'changed', merged: 'merged', split: 'split',
                    removed: 'removed', added: 'added' };
    const cs = cmp.counts || {};
    const ids = (xs) => xs.map((x) => 'Cell ' + x).join(' + ') || '—';
    return el('div', { class: 'ks-diff' }, [
      el('p', { class: 'hint', text: 'v' + cmp.a + ' (' + (cmp.a_source || '?') + ') against v'
        + cmp.b + ' (' + (cmp.b_source || '?') + '), cell by cell through the spikes '
        + 'they share: ' + Object.keys(words).filter((k) => cs[k])
          .map((k) => cs[k] + ' ' + words[k]).join(' · ') + '.' }),
      el('div', { class: 'ks-diff-rows' }, (cmp.rows || []).map((r) => el('div', {
        class: 'ks-diff-row ' + r.kind }, [
        el('span', { class: 'ks-diff-kind', text: words[r.kind] }),
        el('span', { text: ids(r.a) + '  →  ' + ids(r.b) }),
        el('span', { class: 'hint', text: r.shared.toLocaleString() + ' spikes shared'
          + (r.n_a ? ' of ' + r.n_a.toLocaleString() : '')
          + (r.n_b ? ' / ' + r.n_b.toLocaleString() : '') }),
      ]))),
    ]);
  }

  function cellsMain(node) {
    const row = (CS.sorts || []).find((r) => r.gid === CS.gid);
    const d = CS.d;
    if (!row || !d) {
      node.appendChild(stepsStrip({}, null));
      node.appendChild(el('p', { class: 'hint', text: 'Pick a recording on the left. '
        + 'Its steps light up for what it has.' }));
      return;
    }
    node.appendChild(el('div', { class: 'ks-cells-head' }, [
      el('div', {}, [
        el('h3', { text: row.label || row.gid }),
        el('p', { class: 'hint', text: (d.path || row.path) + ' · '
          + ((d.run || {}).name || row.run)
          + (d.twin ? ' · its inverted twin ' + d.twin.name + ' is not read' : '') }),
      ]),
      el('div', { class: 'spacer' }),
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Open in Phy',
        disabled: !(d.run && d.run.path),
        onclick: () => openPhy(d.run.path) }),
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Open in Xplorefinder',
        disabled: !(d.cells || []).length,
        onclick: () => BARRY.cells.enter(d.gid, { version: CS.version }) }),
      BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'Bank…',
        disabled: !(d.cells || []).length,
        title: (d.cells || []).length ? null : 'Read a curation first.',
        onclick: bankOne }),
    ]));
    node.appendChild(stepsStrip(row, d));
    if (d.ok === false) {
      node.appendChild(el('p', { class: 'hint warn-line', text: d.error }));
      return;
    }
    if (d.polarity) {
      node.appendChild(el('p', { class: 'hint' + (d.polarity.ok ? '' : ' warn-line')
        + ' ks-polarity', text: 'Polarity: ' + d.polarity.words }));
    }

    // Where a curation can be read from.
    node.appendChild(el('div', { class: 'section-label', text: 'Curations on disk' }));
    if (!(d.sources || []).length) {
      node.appendChild(el('p', { class: 'hint', text: 'Sorted, never curated: no '
        + 'export beside it and Phy has not written its labels. Nothing to bank.' }));
    }
    node.appendChild(el('div', { class: 'ks-sources' }, (d.sources || []).map((s) =>
      el('div', { class: 'ks-source' }, [
        el('strong', { text: s.name }),
        el('span', { class: 'hint', text: (s.n != null ? s.n + ' cells · ' : '')
          + (s.at || '') + ' · ' + s.path }),
        el('div', { class: 'spacer' }),
        BARRY.ui.button({ kind: (d.curation ? 'ghost' : 'primary'), size: 'sm',
          text: d.curation ? 'Read again' : 'Read it',
          title: 'Read it into a curation version. The same cells read again '
               + 'confirm the version rather than make another.',
          onclick: () => readSource(s.kind) }),
      ]))));

    // The versions, and comparing two.
    const cur = d.curation;
    if (cur) {
      const vs = (cur.versions || []).map((v) => Object.assign({}, v, {
        note: [v.source, v.note].filter(Boolean).join(' · ') }));
      node.appendChild(el('div', { class: 'section-label', text: 'Curation versions' }));
      node.appendChild(el('div', { class: 'ks-vers' }, [
        el('span', { class: 'hint', text: 'Showing' }),
        BARRY.ui.versionButton({
          versions: vs, idOf: (v) => v.v, value: CS.version, unit: 'cells',
          producer: false, family: { artifact: cur.artifact_id },
          heading: 'Which curation of ' + (row.label || row.gid),
          sub: 'Every source read that changed which cells exist is a version.',
          onpick: (v) => { if (v) openRec(CS.gid, v.v); },
        }),
        vs.length > 1 ? el('span', { class: 'hint', text: 'compared with' }) : null,
        vs.length > 1 ? BARRY.ui.versionButton({
          versions: vs.filter((v) => v.v !== CS.version), idOf: (v) => v.v,
          value: null, unit: 'cells', producer: false,
          lead: { name: 'Compare…' },
          family: { artifact: cur.artifact_id },
          heading: 'Compare v' + CS.version + ' with which curation',
          onpick: (v) => { if (v) compare(v.v, CS.version); },
        }) : null,
      ].filter(Boolean)));
      if (CS.cmp) node.appendChild(diffBlock(CS.cmp));
    }

    const cells = d.cells || [];
    if (cells.length) {
      node.appendChild(el('div', { class: 'section-label', text: cells.length
        + ' cells in v' + CS.version + (d.source ? ' · ' + d.source.name : '') }));
      node.appendChild(el('div', { class: 'ks-cellgrid' },
        cells.map((c) => cellCard(c, d))));
    }
  }

  function cellsPane(node) {
    if (CS.sorts === null) {
      node.appendChild(el('p', { class: 'hint', text: 'Looking for sorts beside every '
        + 'recording on this computer…' }));
      loadSorts(false);
      return;
    }
    node.appendChild(el('p', { class: 'hint', text: 'The sorts already made, read '
      + 'back. Cells are the curated units (Isabella’s export, or Phy’s labels), '
      + 'kept as curation versions and banked as one Cell entry a recording. '
      + 'Jarvis reads the non-inverted run.' }));
    if (CS.err) node.appendChild(el('p', { class: 'hint warn-line', text: CS.err }));
    if (CS.busy) node.appendChild(el('p', { class: 'hint ks-busy', text: CS.busy }));
    const sorts = CS.sorts || [];
    const toRead = sorts.filter((r) => r.export_n && !r.curation).length;
    const toBank = sorts.filter((r) => r.curation && !r.entry).length;
    const q = CS.filter.trim().toLowerCase();
    const shown = q ? sorts.filter((r) => String(r.label || r.gid).toLowerCase()
      .indexOf(q) >= 0) : sorts;
    const find = el('input', { type: 'search', class: 'ks-cells-find',
      placeholder: 'Find a recording…', value: CS.filter,
      oninput: (e) => {
        CS.filter = e.target.value;
        const list = document.querySelector('.ks-cells-list .ks-cell-recs');
        if (!list) return;
        const qq = CS.filter.trim().toLowerCase();
        list.querySelectorAll('.ks-cell-rec').forEach((b) => {
          b.classList.toggle('hidden', !!qq && b.textContent.toLowerCase().indexOf(qq) < 0);
        });
      } });
    node.appendChild(el('div', { class: 'ks-cells' }, [
      el('div', { class: 'ks-cells-list' }, [
        el('div', { class: 'ks-cells-sum' }, [
          el('strong', { text: sorts.length + ' sorted · ' + CS.curated + ' curated' }),
          el('div', { class: 'spacer' }),
          BARRY.ui.button({ kind: 'mini', text: 'Look again',
                            onclick: () => loadSorts(true) }),
        ]),
        el('div', { class: 'ks-cells-batch' }, [
          BARRY.ui.button({ kind: 'ghost', size: 'sm',
            text: 'Read every export' + (toRead ? ' (' + toRead + ')' : ''),
            disabled: !toRead || !!CS.busy, onclick: readAll }),
          BARRY.ui.button({ kind: 'ghost', size: 'sm',
            text: 'Bank every read…' + (toBank ? ' (' + toBank + ')' : ''),
            disabled: !toBank || !!CS.busy, onclick: bankAll }),
        ]),
        find,
        el('div', { class: 'ks-cell-recs' }, shown.map(sortRow)),
      ]),
      (() => { const m = el('div', { class: 'ks-cells-main' }); cellsMain(m); return m; })(),
    ]));
  }

  /* ==================================================================
     Set up
     ================================================================== */
  function setupPane(node) {
    const rows = (env && env.rows) || [];
    const missing = rows.filter((r) => !r.ok && r.severity !== 'advice');

    node.appendChild(el('div', {
      class: 'ks-verdict ' + (env && env.ready ? 'good' : 'bad'),
    }, [
      el('strong', { text: env && env.ready
        ? 'This machine can run Kilosort.'
        : missing.length + ' thing' + (missing.length === 1 ? '' : 's')
          + ' still missing.' }),
      el('span', { text: env && env.ready
        ? 'Everything it needs imports in ' + (env.python || 'this Python')
          + '.'
        : 'Each one below says what to type. You can also let Jarvis run it.' }),
    ]));

    if ((env.interpreters || []).length > 1) node.appendChild(pythonPicker());
    if (env.switched) {
      node.appendChild(el('p', { class: 'hint',
        text: 'Jarvis runs on a Python that torch does not build for, so this '
            + 'pane switched to Python ' + (env.python_version || '')
            + '. Jarvis itself carries on unchanged — this only affects '
            + 'what the sort runs on.' }));
    }

    const list = el('div', { class: 'ks-reqs' });
    for (const r of rows) {
      const advice = r.severity === 'advice';
      list.appendChild(el('div', {
        class: 'ks-req' + (r.ok ? ' ok' : (advice ? ' warn' : ' bad')),
      }, [
        el('span', { class: 'ks-dot' }),
        el('div', { class: 'ks-req-body' }, [
          el('div', { class: 'ks-req-top' }, [
            el('strong', { text: r.name }),
            el('code', { text: r.detail || '' }),
          ]),
          el('p', { class: 'hint', text: r.why }),
          (!r.ok && r.fix)
            ? el('div', { class: 'ks-fix' }, [
                el('pre', { text: r.fix }),
                installable(r.id)
                  ? el('button', {
                      class: 'btn sm',
                      text: 'Run it',
                      disabled: busy ? 'disabled' : null,
                      onclick: () => install(r.id),
                    })
                  : null,
                el('button', {
                  class: 'btn ghost sm', text: 'Copy',
                  onclick: () => copy(r.fix),
                }),
              ].filter(Boolean))
            : null,
        ].filter(Boolean)),
      ]));
    }
    node.appendChild(list);

    // The GPU line is worth spelling out: it is the difference between a
    // coffee break and an afternoon, and it is the one people miss.
    const cuda = rows.find((r) => r.id === 'cuda');
    if (cuda && !cuda.ok && rows.find((r) => r.id === 'torch' && r.ok)) {
      node.appendChild(el('div', { class: 'ks-note' }, [
        el('strong', { text: 'torch is installed but cannot see a GPU.' }),
        el('p', { text: 'That is almost always the CPU-only build. It will '
          + 'still sort, but a session that takes twenty minutes on a GPU '
          + 'takes several hours. Uninstall torch first, then install the '
          + 'CUDA build — pip will not swap them for you.' }),
        el('pre', { text: 'pip uninstall torch\n'
          + 'pip install torch --index-url '
          + 'https://download.pytorch.org/whl/cu121' }),
      ]));
    }

    node.appendChild(el('div', { class: 'section-label',
                                 text: 'Everything at once' }));
    node.appendChild(el('div', { class: 'ks-fix' }, [
      el('pre', { text: (env && env.install_all) || '' }),
      el('button', { class: 'btn ghost sm', text: 'Copy',
                     onclick: () => copy(env.install_all) }),
    ]));

    node.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Check again',
      style: 'margin-top:12px',
      onclick: () => load(document.getElementById('tkResult')),
    }));
  }

  /* Every Python on the machine, with the ones torch cannot build for
     marked as such. This is the difference between "Run failed with exit
     code 1" and "that version has no torch; here are three that do". */
  function pythonPicker() {
    const opts = (env.interpreters || []).map((i) => el('option', {
      value: i.path,
      text: 'Python ' + (i.version || '?')
          + (i.usable ? '' : '  \u2014 no torch for this one')
          + (i.current ? '  (Jarvis runs on this)' : '')
          + '   ' + i.path,
    }));
    const sel = el('select', {
      class: 'ks-python',
      onchange: async (e) => {
        python = e.target.value || null;
        plan = null;
        await load(document.getElementById('tkResult'));
      },
    }, opts);
    if (python) sel.value = python;
    const chosen = (env.interpreters || []).find((i) => i.path === sel.value)
                   || {};
    return el('div', { class: 'ks-pypick' }, [
      el('label', { text: 'Run Kilosort with' }),
      sel,
      el('p', { class: 'hint',
        text: chosen.usable === false
          ? 'torch publishes no build for that version, so installing it '
            + 'fails with "from versions: none" \u2014 which reads like a '
            + 'network problem and is not one.'
          : 'Jarvis can keep running on its own Python; this is only what the '
            + 'sort runs on.' }),
    ]);
  }

  function installable(id) {
    return ['torch', 'kilosort', 'phy'].includes(id);
  }

  async function install(what) {
    busy = true;
    render();
    try {
      const res = await apiPost('/api/kilosort/install',
                                { what, python });
      job = { id: res.job, label: 'pip install ' + what, lines: [],
              command: res.command };
      watch();
    } catch (e) {
      toast(e.message, 'err', 8000);
    } finally {
      busy = false;
      render();
    }
  }

  /* ==================================================================
     Run
     ================================================================== */
  function runPane(node) {
    node.appendChild(el('div', { class: 'section-label',
                                 text: 'Which recording' }));
    node.appendChild(BARRY.pickSession({
      rows: sessions,
      value: pick && pick.gid,
      placeholder: 'Type a mouse, session or date…',
      onpick: (r) => { pick = r; replan(); },
    }));
    if (!sessions.length) {
      node.appendChild(el('p', { class: 'hint',
        text: 'No registered recording is reachable from this machine. Scan '
            + 'the drive first.' }));
      return;
    }

    // ---- probe and settings -------------------------------------------
    const probes = (env && env.probes) || [];
    const setts = (env && env.settings) || [];
    node.appendChild(el('div', { class: 'ks-choices' }, [
      el('label', {}, [
        el('span', { text: 'Probe' }),
        select(probes.map((p) => ({
          value: p.path,
          text: p.name + (p.channels ? '  (' + p.channels + ' ch)' : '')
              + (p.note ? '  — ' + p.note.slice(0, 44) : ''),
        })), probe, (v) => { probe = v; replan(); }),
      ]),
      el('label', {}, [
        el('span', { text: 'Settings' }),
        select(setts.map((s) => ({
          value: s.path,
          text: s.name + '  (' + s.n_chan_bin + ' ch, ' + s.fs + ' Hz, '
              + 'Th ' + s.Th_universal + '/' + s.Th_learned + ')',
        })), settings, (v) => { settings = v; replan(); }),
      ]),
      el('label', { class: 'ks-check' }, [
        el('input', {
          type: 'checkbox', checked: invert ? 'checked' : null,
          onchange: (e) => { invert = e.target.checked; replan(); },
        }),
        el('span', { text: 'Invert the signal' }),
      ]),
    ]));

    if (!pick) {
      node.appendChild(el('p', { class: 'hint',
        text: 'Pick a recording and Jarvis will work out whether it can be '
            + 'sorted before anything runs.' }));
      return;
    }
    if (!plan) {
      node.appendChild(el('p', { class: 'hint', text: 'Working it out…' }));
      return;
    }

    // ---- what would happen ---------------------------------------------
    node.appendChild(el('div', {
      class: 'ks-verdict ' + (plan.ready ? 'good' : 'bad'),
    }, [
      el('strong', { text: plan.ready
        ? 'Ready to sort.'
        : plan.problems.length + ' thing'
          + (plan.problems.length === 1 ? '' : 's') + ' in the way.' }),
      el('span', { text: plan.ready
        ? 'Nothing below disagrees with anything else.'
        : 'Every one of these would otherwise show up as a crash, or worse, '
          + 'as a sort that looked fine.' }),
    ]));

    for (const p of (plan.problems || [])) {
      node.appendChild(el('div', { class: 'ks-problem' }, [
        el('strong', { text: p.what }),
        el('p', { text: p.why }),
      ]));
    }

    node.appendChild(el('div', { class: 'ks-facts' }, [
      fact('Binary', plan.binary || 'not found',
           plan.binary_bytes ? fmtBytes(plan.binary_bytes) : ''),
      fact('Channels', plan.n_chan_bin || '?',
           plan.probe_channels
             ? 'probe describes ' + plan.probe_channels : ''),
      fact('Sampling', plan.fs ? plan.fs + ' Hz' : '?',
           plan.duration_s ? fmtDur(plan.duration_s) : ''),
      fact('Bad channels',
           plan.bad_csc.length ? 'CSC ' + plan.bad_csc.join(', ') : 'none',
           plan.bad_channels.length
             ? '→ Kilosort ' + plan.bad_channels.join(', ') : ''),
      fact('Results go to', plan.results_dir
        ? baseName(plan.results_dir) : '?', ''),
    ]));

    if (plan.bad_csc.length) {
      node.appendChild(el('p', { class: 'hint',
        text: 'Those came from what you marked bad on this recording. '
            + 'Kilosort counts binary rows from zero while the files are '
            + 'CSC1 upwards, so each number goes down by one — which is '
            + 'the off-by-one that quietly excludes the wrong channel when '
            + 'it is done by hand.' }));
    }

    // ---- the script, before it runs -------------------------------------
    const seen = { open: false };
    const scriptBox = el('pre', { class: 'ks-script hidden',
                                  text: plan.script || '' });
    node.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Show the script this will run',
      onclick: (e) => {
        seen.open = !seen.open;
        scriptBox.classList.toggle('hidden', !seen.open);
        e.target.textContent = seen.open
          ? 'Hide the script' : 'Show the script this will run';
      },
    }));
    node.appendChild(scriptBox);

    node.appendChild(el('div', { class: 'ks-actions' }, [
      el('button', {
        class: 'btn', text: 'Sort it',
        disabled: (!plan.ready || busy || (job && job.running))
          ? 'disabled' : null,
        onclick: () => run(false),
      }),
      (!plan.ready && plan.problems.length
        && plan.problems.every((x) => /already here/.test(x.what)))
        ? el('button', {
            class: 'btn ghost', text: 'Sort it anyway',
            title: 'Runs into the existing folder',
            onclick: () => run(true),
          })
        : null,
      el('button', {
        class: 'btn ghost', text: 'Open the folder',
        onclick: () => apiPost('/api/reveal',
                               { path: plan.session_path }).catch(() => {}),
      }),
    ].filter(Boolean)));

    // ---- what has already been sorted here -------------------------------
    if ((plan.existing || []).length) {
      node.appendChild(el('div', { class: 'section-label',
                                   text: 'Already sorted here' }));
      node.appendChild(el('div', { class: 'ks-runs' },
        plan.existing.map((r) => el('div', { class: 'ks-run' }, [
          el('div', {}, [
            el('strong', { text: r.name }),
            el('span', { class: 'hint',
              text: (r.at || '') + (r.clusters != null
                ? '  · ' + r.clusters + ' clusters' : '')
                + (r.done ? '' : '  · no params.py, so it did not finish') }),
          ]),
          r.done
            ? el('button', {
                class: 'btn sm', text: 'Open in Phy',
                onclick: () => openPhy(r.path),
              })
            : null,
        ].filter(Boolean)))));
    }
  }

  async function replan() {
    if (!pick) return;
    const got = BARRY.vacc.reachFor(pick, 'kilosort');
    const path = got.path;
    if (!path) {
      plan = null;
      toast(got.why || 'None of that recording’s paths are reachable here.',
            'err');
      render();
      return;
    }
    plan = null;
    render();
    try {
      plan = await apiPost('/api/kilosort/plan', {
        session_path: path, probe, settings, invert, python,
      });
    } catch (e) {
      plan = { ready: false, problems: [{ what: 'Could not plan the run.',
                                          why: e.message }] };
    }
    render();
  }

  async function run(anyway) {
    busy = true;
    render();
    try {
      const res = await apiPost('/api/kilosort/run', {
        session_path: plan.session_path, probe, settings, invert, anyway,
        python,
      });
      job = { id: res.job, label: 'Kilosort', lines: [], running: true,
              command: res.script, results: res.results_dir };
      toast('Sorting. This takes a while — the log is below and it keeps '
            + 'running if you go somewhere else.', 'ok', 8000);
      watch();
    } catch (e) {
      toast(e.message, 'err', 9000);
    } finally {
      busy = false;
      render();
    }
  }

  /* ==================================================================
     Phy
     ================================================================== */
  async function loadGuide() {
    if (phyGuide) return;
    try { phyGuide = await api('/api/phy/guide'); } catch (e) { phyGuide = null; }
    render();
  }

  function phyPane(node) {
    const phyReq = ((env && env.rows) || []).find((r) => r.id === 'phy');
    if (phyReq && !phyReq.ok) {
      node.appendChild(el('div', { class: 'ks-verdict bad' }, [
        el('strong', { text: 'Phy is not installed.' }),
        el('span', { text: phyReq.detail || '' }),
      ]));
      node.appendChild(el('div', { class: 'ks-fix' }, [
        el('pre', { text: phyReq.fix }),
        el('button', { class: 'btn sm', text: 'Run it',
                       onclick: () => install('phy') }),
      ]));
    }

    node.appendChild(el('p', { class: 'hint',
      text: 'Phy opens what Kilosort decided and lets you disagree with it. '
          + 'It is a desktop window of its own — Jarvis starts it and '
          + 'gets out of the way. What you save there lands beside the sort '
          + 'as cluster_group.tsv.' }));

    node.appendChild(el('div', { class: 'section-label',
                                 text: 'Which sort' }));
    node.appendChild(BARRY.pickSession({
      rows: sessions,
      value: pick && pick.gid,
      placeholder: 'Pick the recording first…',
      onpick: async (r) => {
        pick = r;
        chosenRun = null;
        const path = BARRY.vacc.reachFor(r, 'kilosort').path;
        try {
          const res = await api('/api/kilosort/runs?path='
                                + encodeURIComponent(path || ''));
          plan = Object.assign(plan || {}, { existing: res.runs,
                                             session_path: path });
        } catch (e) { /* the list just stays empty */ }
        render();
      },
    }));

    const runs = (plan && plan.existing) || [];
    if (pick && !runs.length) {
      node.appendChild(el('p', { class: 'hint',
        text: 'Nothing has been sorted in that folder yet.' }));
    }
    if (runs.length) {
      node.appendChild(el('div', { class: 'ks-runs' },
        runs.map((r) => el('div', {
          class: 'ks-run' + (chosenRun === r.path ? ' sel' : '')
               + (r.done ? '' : ' away'),
        }, [
          el('div', {}, [
            el('strong', { text: r.name }),
            el('span', { class: 'hint',
              text: (r.at || '') + (r.clusters != null
                ? '  · ' + r.clusters + ' clusters' : '')
                + (r.done ? '' : '  · unfinished, no params.py') }),
          ]),
          el('button', {
            class: 'btn sm', text: 'Open in Phy',
            disabled: r.done ? null : 'disabled',
            onclick: () => openPhy(r.path),
          }),
        ]))));
    }

    // ---- the primer -----------------------------------------------------
    if (phyGuide) {
      node.appendChild(el('div', { class: 'section-label',
                                   text: 'What to look at' }));
      node.appendChild(el('div', { class: 'ks-views' },
        (phyGuide.views || []).map(([name, why]) =>
          el('div', { class: 'ks-view' }, [
            el('strong', { text: name }),
            el('p', { text: why }),
          ]))));

      node.appendChild(el('div', { class: 'section-label',
                                   text: 'The keys worth knowing' }));
      node.appendChild(el('div', { class: 'ks-keys' },
        (phyGuide.keys || []).map(([group, pairs]) =>
          el('div', { class: 'ks-keygroup' }, [
            el('h4', { text: group }),
            el('dl', {}, pairs.flatMap(([k, what]) => [
              el('dt', {}, [el('kbd', { text: k })]),
              el('dd', { text: what }),
            ])),
          ]))));

      node.appendChild(el('p', { class: 'hint',
        text: 'The one rule worth carrying in: a cluster with no refractory '
            + 'gap in its own autocorrelogram is not one cell, however good '
            + 'the waveform looks.' }));
    }
  }

  async function openPhy(results) {
    chosenRun = results;
    render();
    try {
      const res = await apiPost('/api/phy/open',
                                { results_dir: results, python });
      job = { id: res.job, label: 'Phy', lines: [], running: true,
              command: res.command };
      toast('Phy is starting. It opens its own window — give it a '
            + 'moment.', 'ok', 7000);
      watch();
    } catch (e) {
      toast(e.message, 'err', 9000);
    }
  }

  /* ==================================================================
     Watching a job
     ================================================================== */
  function jobBox() {
    return el('div', { class: 'ks-job' }, [
      el('div', { class: 'ks-job-head' }, [
        el('strong', { text: job.label }),
        el('code', { text: job.command || '' }),
        job.running
          ? el('button', {
              class: 'btn ghost sm', text: 'Stop',
              onclick: () => apiPost('/api/job/' + job.id + '/cancel', {})
                .catch(() => {}),
            })
          : el('button', {
              class: 'btn ghost sm', text: 'Clear',
              onclick: () => { job = null; render(); },
            }),
      ]),
      el('pre', { class: 'ks-log', text: (job.lines || []).join('\n') }),
      (!job.running && job.results)
        ? el('button', { class: 'btn sm', text: 'Open it in Phy',
                         onclick: () => openPhy(job.results) })
        : null,
    ].filter(Boolean));
  }

  /* A sort is an hour of output. Polling from a cursor and keeping the tail
     means the page stays responsive and the log stays readable -- the whole
     of it is on disk in the results folder either way. */
  async function watch() {
    if (!job) return;
    let since = 0;
    for (;;) {
      let snap;
      try {
        const res = await api('/api/job/' + job.id + '?since=' + since);
        snap = res.job || {};
      } catch (e) { break; }
      if (!job) return;
      for (const line of (snap.lines || [])) {
        job.lines.push(line.text != null ? line.text : String(line));
      }
      if (job.lines.length > 400) job.lines.splice(0, job.lines.length - 400);
      since = snap.seq != null ? snap.seq : since;
      job.running = snap.status === 'running';
      const log = document.querySelector('.ks-log');
      if (log) { log.textContent = job.lines.join('\n');
                 log.scrollTop = log.scrollHeight; }
      if (!job.running) {
        render();
        // A finished install changes the answer to "can this machine run it".
        if (/install/.test(job.label)) {
          await load(document.getElementById('tkResult'));
        }
        break;
      }
      await new Promise((r) => setTimeout(r, 900));
    }
  }

  /* ================================================================== */
  function terminal() {
    const path = (plan && (chosenRun || plan.results_dir
                           || plan.session_path)) || null;
    apiPost('/api/kilosort/terminal', { path })
      .then(() => toast('Opened a prompt in ' + (path ? baseName(path)
                                                      : 'the repo') + '.',
                        'ok'))
      .catch((e) => toast(e.message, 'err', 7000));
  }

  function select(options, value, onchange) {
    const s = el('select', {
      onchange: (e) => onchange(e.target.value),
    }, options.map((o) => el('option', { value: o.value, text: o.text })));
    if (value) s.value = value;
    return s;
  }

  function fact(k, v, extra) {
    return el('div', { class: 'ks-fact' }, [
      el('span', { class: 'k', text: k }),
      el('span', { class: 'v', text: String(v), title: String(v) }),
      extra ? el('span', { class: 'x', text: extra }) : null,
    ].filter(Boolean));
  }

  function copy(text) {
    navigator.clipboard.writeText(text).then(
      () => toast('Copied.', 'ok'),
      () => toast('The browser would not let me use the clipboard.', 'err'));
  }

  return { load, render,
    /* For _dev/cells.html and BARRY.cells: open the Cells pane on one. */
    openCells: (gid) => { pane = 'cells'; render(); if (gid) openRec(gid); },
    _cells: () => CS };
}());
