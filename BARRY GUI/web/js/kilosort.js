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
  let pane = 'setup';        // setup | run | phy
  /* Which interpreter to use. BARRY itself may be running on a Python torch
     does not build for -- 3.14, as it happens -- and every route here takes
     a `python` argument, so the fix is choosing one rather than installing
     anything. Null means "the one BARRY is running on". */
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
        const reg = await api('/api/registry');
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
  function render(host) {
    const node = host || document.getElementById('tkResult');
    if (!node) return;
    node.innerHTML = '';

    node.appendChild(el('div', { class: 'ks-head' }, [
      el('div', {}, [
        el('h2', { text: 'Kilosort' }),
        el('p', { class: 'hint', text: 'Spike sorting, and the setup that '
          + 'usually stands between you and it.' }),
      ]),
      el('div', { class: 'seg' }, [
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
    if (pane === 'setup') setupPane(node);
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
        : 'Each one below says what to type. You can also let BARRY run it.' }),
    ]));

    if ((env.interpreters || []).length > 1) node.appendChild(pythonPicker());
    if (env.switched) {
      node.appendChild(el('p', { class: 'hint',
        text: 'BARRY runs on a Python that torch does not build for, so this '
            + 'pane switched to Python ' + (env.python_version || '')
            + '. BARRY itself carries on unchanged — this only affects '
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
          + (i.current ? '  (BARRY runs on this)' : '')
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
          : 'BARRY can keep running on its own Python; this is only what the '
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
    node.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
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
        text: 'Pick a recording and BARRY will work out whether it can be '
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
    const path = (pick.here || [])[0];
    if (!path) {
      plan = null;
      toast('None of that recording’s paths are reachable here.', 'err');
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
          + 'It is a desktop window of its own — BARRY starts it and '
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
        const path = (r.here || [])[0];
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

  return { load, render };
}());
