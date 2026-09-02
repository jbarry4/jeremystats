/* ==========================================================================
   pipeline.js -- the folder-driven IED pipeline view.

   Two tracks: SESSION (one recording folder) and COHORT (a parent of many).
   Each stage reports readiness against the chosen folder, so the order is
   visible rather than remembered.
   ========================================================================== */
'use strict';

BARRY.views.pipeline = (function () {
  let tracks = null;
  let track = 'session';
  const folders = { session: '', cohort: '' };
  const optionValues = {};          // stageKey -> {name: value}
  let checks = [];
  let runningKey = null;
  let queue = [];                   // remaining stage keys for "Run all"
  let batch = null;                 // active multi-folder batch
  let batchPoll = null;
  let presets = [];                 // saved parameter sets, synced

  const DROP_COPY = {
    session: {
      title: 'Drop a recording folder here',
      hint: 'the session directory that holds CSC*.ncs',
      placeholder: 'C:\\data\\Animal\\2023-08-01_12-11-26',
    },
    cohort: {
      title: 'Drop a parent folder here',
      hint: 'the folder that contains many processed session folders',
      placeholder: 'C:\\data\\PTEN',
    },
  };

  function stages() {
    return (tracks && tracks[track]) || [];
  }

  function checkFor(key) {
    return checks.find((c) => c.key === key) || { ready: false, done: false, missing: [] };
  }

  /* ---------- folder selection ---------- */
  async function setFolder(path) {
    if (!path) return;
    folders[track] = path;
    // Coming back to a half-finished pipeline is the normal case, so the
    // folder per track is remembered across restarts.
    BARRY.prefs.set('pipeline_folders', Object.assign(
      {}, BARRY.prefs.get('pipeline_folders', {}), { [track]: path }));
    await recheck();
  }

  async function recheck() {
    const folder = folders[track];
    const bar = $('#pipeFolderBar');
    if (!folder) {
      bar.classList.add('hidden');
      checks = [];
      render();
      return;
    }

    let data;
    try {
      data = await apiPost('/api/pipeline/check', { folder, track });
    } catch (e) {
      toast(e.message, 'err');
      return;
    }

    checks = data.stages || [];
    const info = data.info || {};
    bar.classList.remove('hidden');
    $('#pipeFolderPath').textContent = folder;
    $('#pipeFolderPath').title = folder;

    const stats = $('#pipeFolderStats');
    stats.innerHTML = '';
    if (info.ok) {
      const chips = [];
      if (info.n_ncs) chips.push(['good', info.n_ncs + ' CSC .ncs']);
      if (info.mats && info.mats.length) chips.push(['good', info.mats.length + ' .mat']);
      if (info.n_dirs) chips.push(['', info.n_dirs + ' folders']);
      chips.push(['', info.n_files + ' files']);
      if (info.bytes) chips.push(['', fmtBytes(info.bytes)]);
      if (!info.n_ncs && !(info.mats || []).length && track === 'session') {
        chips.push(['warn', 'no CSC data found']);
      }
      for (const [cls, text] of chips) {
        stats.appendChild(el('span', { class: 'stat-chip ' + cls, text }));
      }
    } else {
      stats.appendChild(el('span', { class: 'stat-chip warn', text: info.error || 'unreadable' }));
    }
    render();
  }

  /* ---------- rendering ---------- */
  function render() {
    const host = $('#stageList');
    host.innerHTML = '';
    const list = stages();
    if (!list.length) return;

    const folder = folders[track];
    const needsMatlab = list.some((s) => s.lang === 'matlab');
    const hasMatlab = BARRY.state.catalog && BARRY.state.catalog.matlab;

    const bar = el('div', { class: 'track-actions' }, [
      el('button', {
        class: 'btn', id: 'runAll',
        disabled: (!folder || runningKey) ? 'disabled' : null,
        onclick: runAll,
        text: runningKey ? 'Running…' : 'Run all stages',
      }),
      el('button', {
        class: 'btn ghost', disabled: runningKey ? null : 'disabled',
        onclick: stopAll, text: 'Stop',
      }),
      el('button', {
        class: 'btn ghost', onclick: () => preflight(),
        disabled: folder ? null : 'disabled',
        title: 'Check everything that could make a stage fail, before it runs',
        text: 'Preflight',
      }),
      el('button', {
        class: 'btn ghost', onclick: openBatch,
        title: 'Run these stages across many session folders',
        text: 'Batch…',
      }),
      el('button', {
        class: 'btn ghost', onclick: openPresets,
        title: 'Named parameter sets, shared through GUI_logs',
        text: 'Presets' + (presets.length ? ' (' + presets.length + ')' : ''),
      }),
      el('span', {
        class: 'hint',
        text: track === 'session'
          ? 'Each stage writes back into the session folder.'
          : 'Aggregates across every session under the parent folder.',
      }),
    ]);
    host.appendChild(bar);

    if (batch) host.appendChild(batchCard());

    if (needsMatlab && !hasMatlab) {
      host.appendChild(el('div', {
        class: 'stat-chip warn',
        text: 'MATLAB was not found — MATLAB stages cannot run on this machine.',
      }));
    }

    for (const s of list) host.appendChild(stageCard(s));
  }

  function stageCard(s) {
    const chk = checkFor(s.key);
    const isRunning = runningKey === s.key;
    const cls = ['stage'];
    if (isRunning) cls.push('running');
    else if (chk.done) cls.push('done');
    else if (!chk.ready) cls.push('blocked');

    const tags = [];
    if (isRunning) tags.push(el('span', { class: 'tag ready', text: 'running' }));
    else if (chk.done) tags.push(el('span', { class: 'tag done', text: 'output present' }));
    else if (chk.ready) tags.push(el('span', { class: 'tag ready', text: 'ready' }));
    else tags.push(el('span', { class: 'tag blocked', text: 'needs input' }));
    if (s.optional) tags.push(el('span', { class: 'tag opt', text: 'optional' }));
    tags.push(el('span', { class: 'tag lang', text: s.lang }));

    const meta = [];
    if (chk.found && chk.found.length) {
      meta.push(el('span', { text: 'found: ' + chk.found.join(', ') }));
    }
    if (chk.missing && chk.missing.length) {
      meta.push(el('span', { class: 'miss', text: 'missing: ' + chk.missing.join(', ') }));
    }
    meta.push(el('span', { text: s.script }));

    const main = el('div', { class: 'stage-main' }, [
      el('div', { class: 'stage-title' },
        [el('strong', { text: s.title })].concat(tags)),
      el('p', { class: 'stage-summary', text: s.summary }),
      el('div', { class: 'stage-meta' }, meta),
    ]);

    const opts = (s.options || []).concat(s.positional_extra || []);
    if (opts.length) {
      const box = el('div', { class: 'stage-opts' });
      for (const o of opts) {
        const stored = (optionValues[s.key] || {})[o.name];
        box.appendChild(el('div', { class: 'opt-field' }, [
          el('label', { text: o.name, title: o.hint || '' }),
          el('input', {
            type: 'text',
            value: stored !== undefined ? stored : o.value,
            title: o.hint || '',
            oninput: (e) => {
              optionValues[s.key] = optionValues[s.key] || {};
              optionValues[s.key][o.name] = e.target.value;
            },
          }),
        ]));
      }
      main.appendChild(box);
    }

    const canRun = !!folders[track] && !runningKey &&
      (s.lang !== 'matlab' || (BARRY.state.catalog && BARRY.state.catalog.matlab));

    const actions = el('div', { class: 'stage-actions' }, [
      el('button', {
        class: chk.ready ? 'btn' : 'btn ghost',
        disabled: canRun ? null : 'disabled',
        onclick: () => runStage(s.key),
        text: chk.done ? 'Re-run' : 'Run',
      }),
      el('button', {
        class: 'btn ghost sm',
        onclick: () => preflight(s.key, true),
        disabled: folders[track] ? null : 'disabled',
        title: 'Check this stage can actually run here',
        text: 'Check',
      }),
      el('button', {
        class: 'btn ghost sm',
        onclick: () => openInExplorer(s.script),
        text: 'View code',
      }),
    ]);

    return el('div', { class: cls.join(' ') }, [
      el('div', { class: 'stage-num', text: String(s.n) }),
      main,
      actions,
    ]);
  }

  function openInExplorer(rel) {
    setView('explorer');
    if (BARRY.views.explorer.select) BARRY.views.explorer.select(rel);
  }


  /* ======================================================================
     Feature 1 -- Preflight
     A stage failing ten minutes in because MATLAB is missing, the disk is
     full or a channel file is truncated is the single most common way this
     pipeline wastes an afternoon. This asks all of those questions first.
     ====================================================================== */
  async function preflight(key, thenRun) {
    const folder = folders[track];
    if (!folder) { toast('Pick a folder first.', 'err'); return false; }

    const body = el('div', { class: 'mb' }, [loader('Checking', folder)]);
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Preflight' }),
        el('span', { class: 'sub', text: key || (track + ' track') }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      body,
      el('div', { class: 'mf', id: 'pfFoot' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Close', onclick: closeModal }),
      ]),
    ]));

    let res;
    try {
      res = await apiPost('/api/pipeline/preflight', { folder, track, key });
    } catch (e) {
      body.innerHTML = '';
      body.appendChild(el('p', { class: 'confirm-msg', text: e.message }));
      return false;
    }

    body.innerHTML = '';
    body.appendChild(el('div', { class: 'pf-summary' }, [
      el('span', {
        class: 'stat-chip ' + (res.level === 'ok' ? 'good'
                               : (res.level === 'bad' ? 'warn' : 'warn')),
        text: res.level === 'ok' ? 'all clear'
              : (res.level === 'bad' ? 'blocking problem' : 'warnings only'),
      }),
      el('span', { class: 'hint', text: res.can_run
        ? 'Nothing here stops the run.'
        : 'Fix the red rows before running.' }),
    ]));
    body.appendChild(BARRY.checkList(res.checks));
    BARRY.activity.log('pipeline.preflight',
                       { folder, track, key, level: res.level });

    const foot = $('#pfFoot');
    if (thenRun && res.can_run) {
      foot.insertBefore(el('button', {
        class: 'btn', text: 'Run anyway',
        onclick: () => { closeModal(); runStage(key, true); },
      }), foot.lastChild);
    }
    return res.can_run;
  }

  /* ======================================================================
     Feature 2 -- Batch across folders
     The cohort track aggregates; this is the other half, running the same
     per-session stage over every recording under a parent, one at a time so
     MATLAB is never asked to run twice at once.
     ====================================================================== */
  async function openBatch() {
    const list = stages();
    const chosen = new Set(list.filter((x) => !x.optional).map((x) => x.key));
    let picked = [];

    const folderBox = el('div', { class: 'batch-list' });
    const stageBox = el('div', { class: 'filter-row' }, list.map((s) =>
      el('button', {
        class: 'pill' + (chosen.has(s.key) ? ' active' : ''),
        text: s.title,
        onclick: (e) => {
          if (chosen.has(s.key)) chosen.delete(s.key); else chosen.add(s.key);
          e.target.classList.toggle('active', chosen.has(s.key));
        },
      })));

    function paintFolders() {
      folderBox.innerHTML = '';
      if (!picked.length) {
        folderBox.appendChild(el('div', { class: 'hint',
          text: 'No folders yet. Add a parent folder to expand its sessions, '
              + 'or pull in whatever is selected in the Sessions view.' }));
        return;
      }
      picked.forEach((f, i) => folderBox.appendChild(
        el('div', { class: 'batch-row queued' }, [
          el('span', { class: 'st', text: String(i + 1) }),
          el('span', { class: 'nm', text: f, title: f }),
          el('span', {}),
          el('button', { class: 'badbtn', text: 'remove',
                         onclick: () => { picked.splice(i, 1); paintFolders(); } }),
        ])));
    }

    async function addParent() {
      const root = await pickPath('folder', folders[track]);
      if (!root) return;
      // Reuse the discovery scanner: it already knows what a session is.
      folderBox.innerHTML = '';
      folderBox.appendChild(loader('Looking for sessions', root));
      try {
        const start = await apiPost('/api/discover/start',
                                    { root, max_depth: 6, read_headers: false });
        let done = false, tries = 0;
        while (!done && tries++ < 600) {
          const st = await api('/api/discover/' + start.job.id + '?sessions=1');
          done = st.job.status !== 'running';
          if (done) {
            for (const sx of (st.sessions || [])) {
              if (picked.indexOf(sx.path) < 0) picked.push(sx.path);
            }
          } else {
            await new Promise((r) => setTimeout(r, 400));
          }
        }
      } catch (e) { toast(e.message, 'err'); }
      paintFolders();
    }

    function addFromSessions() {
      const sel = (BARRY.views.sessions.picked && BARRY.views.sessions.picked()) || [];
      if (!sel.length) {
        toast('Nothing selected in Sessions. Tick some there first.', 'err');
        return;
      }
      for (const p of sel) if (picked.indexOf(p) < 0) picked.push(p);
      paintFolders();
    }

    paintFolders();
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Batch run' }),
        el('span', { class: 'sub', text: 'one folder at a time, in order' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'section-label', text: 'Stages' }),
        stageBox,
        el('div', { class: 'sec-head' }, [
          el('div', { class: 'section-label', text: 'Folders' }),
          el('div', { class: 'spacer' }),
          el('button', { class: 'btn ghost sm', text: 'Add a parent folder…',
                         onclick: addParent }),
          el('button', { class: 'btn ghost sm', text: 'From Sessions selection',
                         onclick: addFromSessions }),
        ]),
        folderBox,
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        el('button', {
          class: 'btn', text: 'Start batch',
          onclick: async () => {
            if (!picked.length) { toast('Add some folders first.', 'err'); return; }
            if (!chosen.size) { toast('Pick at least one stage.', 'err'); return; }
            closeModal();
            try {
              const res = await apiPost('/api/pipeline/batch', {
                folders: picked, keys: Array.from(chosen), track,
                options: optionValues[Array.from(chosen)[0]] || {},
              });
              batch = res.batch;
              render();
              pollBatch();
              LOG.expand();
            } catch (e) { toast(e.message, 'err'); }
          },
        }),
      ]),
    ]));
  }

  function batchCard() {
    const pct = batch.total ? Math.round(100 * batch.finished / batch.total) : 0;
    return el('div', { class: 'stage', style: 'display:block' }, [
      el('div', { class: 'sec-head' }, [
        el('div', { class: 'section-label',
                    text: 'Batch — ' + batch.finished + ' of ' + batch.total
                          + ' done' }),
        el('div', { class: 'spacer' }),
        batch.running
          ? el('button', { class: 'btn ghost sm', text: 'Stop batch',
                           onclick: stopBatch })
          : el('button', { class: 'btn ghost sm', text: 'Dismiss',
                           onclick: () => { batch = null; render(); } }),
      ]),
      el('div', { class: 'batch-bar' }, [el('i', { style: 'width:' + pct + '%' })]),
      el('div', { class: 'batch-list' }, (batch.items || []).map((it) =>
        el('div', { class: 'batch-row ' + it.status }, [
          el('span', { class: 'st', text: it.status }),
          el('span', { class: 'nm', text: it.label + '  ·  ' + it.key,
                       title: it.folder }),
          el('span', { class: 'b',
                       text: it.seconds ? fmtDur(it.seconds) : '' }),
          it.job
            ? el('button', { class: 'badbtn', text: 'log',
                             onclick: () => LOG.show(it.job) })
            : el('span', { class: 'hint', text: it.error || '' }),
        ]))),
    ]);
  }

  function pollBatch() {
    if (batchPoll) clearInterval(batchPoll);
    batchPoll = setInterval(async () => {
      if (!batch) { clearInterval(batchPoll); batchPoll = null; return; }
      try {
        const res = await api('/api/pipeline/batch/' + batch.id);
        batch = res.batch;
        render();
        if (!batch.running) {
          clearInterval(batchPoll); batchPoll = null;
          const bad = (batch.items || []).filter((i) => i.status === 'failed');
          toast('Batch finished — ' + batch.total + ' item(s)'
                + (bad.length ? ', ' + bad.length + ' failed' : ''),
                bad.length ? 'err' : 'ok', 7000);
          recheck();
        }
      } catch (e) {
        clearInterval(batchPoll); batchPoll = null;
      }
    }, 1500);
  }

  async function stopBatch() {
    if (!batch) return;
    try {
      const res = await apiPost('/api/pipeline/batch/' + batch.id + '/cancel');
      batch = res.batch;
      render();
    } catch (e) { toast(e.message, 'err'); }
  }

  /* ======================================================================
     Feature 3 -- Parameter presets
     Stage options are module-level constants in the repo scripts, so the
     values people actually use live nowhere. Named sets fix that, and they
     ride along in GUI_logs like every other preset.
     ====================================================================== */
  async function loadPresets() {
    try {
      const d = await api('/api/presets/layouts');
      presets = (d.presets || []).filter((x) => x.kind === 'pipeline');
    } catch (e) { presets = []; }
  }

  function currentOptions() {
    const out = {};
    for (const s of stages()) {
      const vals = optionValues[s.key];
      if (vals && Object.keys(vals).length) out[s.key] = Object.assign({}, vals);
    }
    return out;
  }

  function applyPreset(pre) {
    for (const k in (pre.options || {})) {
      optionValues[k] = Object.assign({}, pre.options[k]);
    }
    render();
    toast('Applied "' + pre.name + '"', 'ok');
    BARRY.activity.log('pipeline.preset.apply',
                       { name: pre.name, track: pre.track });
  }

  async function savePreset() {
    const opts = currentOptions();
    if (!Object.keys(opts).length) {
      toast('Change some stage options first — there is nothing to save.', 'err');
      return;
    }
    const name = await askPath('Name this parameter set',
                               'e.g. PTEN defaults, 40 uV threshold');
    if (!name) return;
    try {
      await apiPost('/api/presets/layouts', {
        preset: { kind: 'pipeline', name, track, options: opts,
                  note: Object.keys(opts).length + ' stage(s)' },
      });
      await loadPresets();
      render();
      openPresets();
      toast('Saved "' + name + '"', 'ok');
    } catch (e) { toast(e.message, 'err'); }
  }

  function openPresets() {
    const list = el('div', { class: 'batch-list' });
    function paint() {
      list.innerHTML = '';
      if (!presets.length) {
        list.appendChild(el('div', { class: 'hint',
          text: 'No parameter sets yet. Adjust the stage options below, then '
              + 'save them here so the next person gets the same numbers.' }));
        return;
      }
      for (const pre of presets) {
        list.appendChild(el('div', { class: 'batch-row done' }, [
          el('span', { class: 'st', text: pre.track || 'session' }),
          el('span', { class: 'nm', text: pre.name,
                       title: JSON.stringify(pre.options || {}, null, 1) }),
          el('span', { class: 'b',
                       text: Object.keys(pre.options || {}).length + ' stage' }),
          el('div', {}, [
            el('button', { class: 'btn ghost sm', text: 'Apply',
                           onclick: () => { applyPreset(pre); closeModal(); } }),
            el('button', { class: 'badbtn', text: 'delete',
              onclick: async () => {
                try {
                  await api('/api/presets/layouts',
                            { method: 'DELETE',
                              body: JSON.stringify({ id: pre.id }) });
                  await loadPresets(); paint(); render();
                } catch (e) { toast(e.message, 'err'); }
              } }),
          ]),
        ]));
      }
    }
    paint();
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Parameter presets' }),
        el('span', { class: 'sub', text: 'shared through GUI_logs' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [list]),
      el('div', { class: 'mf' }, [
        el('button', { class: 'btn ghost sm', text: 'Save current options…',
                       onclick: savePreset }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn', text: 'Close', onclick: closeModal }),
      ]),
    ]));
  }

  /* ---------- running ---------- */
  async function runStage(key, skipCheck) {
    const s = stages().find((x) => x.key === key);
    if (!s) return;
    const folder = folders[track];
    if (s.arg_folder && !folder) { toast('Pick a folder first.', 'err'); return; }
    void skipCheck;

    runningKey = key;
    render();
    try {
      const res = await apiPost('/api/pipeline/run', {
        key, folder, track, options: optionValues[key] || {},
      });
      LOG.attach(res.job.id, s.title);
    } catch (e) {
      runningKey = null;
      queue = [];
      render();
      toast(e.message, 'err');
    }
  }

  function runAll() {
    const list = stages().filter(
      (s) => !s.optional &&
             (s.lang !== 'matlab' || (BARRY.state.catalog && BARRY.state.catalog.matlab)));
    if (!list.length) { toast('Nothing runnable in this track.', 'err'); return; }
    queue = list.map((s) => s.key);
    const next = queue.shift();
    if (next) runStage(next);
  }

  function stopAll() {
    queue = [];
    if (BARRY.state.job) apiPost('/api/job/' + BARRY.state.job + '/cancel').catch(() => {});
  }

  /* Called by the log dock when a job reaches a terminal state. */
  function onJobEnd(job) {
    if (!job.meta || !job.meta.stage) return;
    if (job.meta.stage !== runningKey) return;
    runningKey = null;

    if (job.status !== 'done') {
      if (queue.length) {
        queue = [];
        toast('Stopped the run — "' + job.label + '" did not finish cleanly.', 'err');
      }
      recheck();
      return;
    }
    const next = queue.shift();
    recheck().then(() => { if (next) runStage(next); });
  }

  /* ---------- init ---------- */
  function init() {
    wireDropzone($('#pipeDrop'), setFolder);

    $('#pipeBrowse').addEventListener('click', async () => {
      const p = await pickPath('folder', folders[track]);
      if (p) setFolder(p);
    });
    $('#pipePaste').addEventListener('click', async () => {
      const p = await askPath('Paste the folder path', DROP_COPY[track].placeholder);
      if (p) setFolder(p);
    });
    $('#pipeRecheck').addEventListener('click', recheck);
    $('#pipeClear').addEventListener('click', () => {
      folders[track] = '';
      recheck();
    });
    $('#pipeReveal').addEventListener('click', () => {
      if (folders[track]) apiPost('/api/reveal', { path: folders[track] }).catch(() => {});
    });

    $$('#trackSwitch button').forEach((b) =>
      b.addEventListener('click', () => {
        track = b.dataset.track;
        $$('#trackSwitch button').forEach((x) => x.classList.toggle('active', x === b));
        const copy = DROP_COPY[track];
        $('#pipeDropTitle').textContent = copy.title;
        $('#pipeDropHint').textContent = copy.hint;
        recheck();
      }));

    api('/api/pipeline').then(async (data) => {
      tracks = data.tracks;
      await loadPresets();
      // Pick up where the last session left off.
      const saved = BARRY.prefs.get('pipeline_folders', {}) || {};
      Object.assign(folders, saved);
      render();
      if (folders[track]) recheck();
    }).catch((e) => toast('Could not load the pipeline: ' + e.message, 'err'));
  }

  return {
    init, onJobEnd, setFolder, preflight,
    onShow: () => { if (folders[track]) recheck(); },
  };
})();
