/* ==========================================================================
   toolkit.js -- The jobs that are about the whole pile, not one recording.

   Everywhere else you are looking at a single session. These are the
   questions that span it: which channels have we thrown away, across this
   mouse, over this month, in this project.

   The first tool is the bad-channel export. It is deliberately more than a
   download button: you pick the scope, you see the rows and the counts before
   committing to anything, and the file that comes out carries a header saying
   what it was a list of and when it was taken -- because a CSV called
   "export.csv" in a downloads folder is not a record.
   ========================================================================== */
'use strict';

BARRY.views.toolkit = (function () {
  let scopes = null;      // what there is to choose from
  let preview = null;     // the last previewed rows
  let busy = false;

  // What is being asked for. Held here rather than read off the DOM so a
  // re-render cannot lose a half-filled form.
  const q = {
    tool: 'bad',
    scope: 'all',
    key: '', mouse: '', group: '',
    from: '', to: '',
    form: 'long',
    clean: false,
  };

  /* ==================================================================
     Loading
     ================================================================== */
  async function onShow() {
    render();
    if (!scopes) await loadScopes();
    refresh();
  }

  async function loadScopes() {
    try {
      scopes = await api('/api/toolkit/scopes');
      // Fill in every scope's default up front, so the fields are never
      // empty by the time one of them is shown -- including the date range,
      // which otherwise opens as two blank boxes that look broken.
      const was = q.scope;
      for (const sc of ['session', 'mouse', 'group', 'range']) {
        q.scope = sc;
        seedScope();
      }
      q.scope = was;
    } catch (e) {
      toast('Could not read the session list: ' + e.message, 'err', 8000);
      scopes = { sessions: [], mice: [], groups: [] };
    }
    render();
  }

  /* A scope arrives with its first option already chosen. Otherwise picking
     "One mouse" asks the server about mouse (nothing), which it rightly
     refuses -- so the panel answered a deliberate click with an error. */
  function seedScope() {
    const s = scopes || {};
    if (q.scope === 'session' && !q.key && (s.sessions || []).length) {
      // Prefer one that actually has something marked: an empty session is a
      // confusing thing to land on in a bad-channel report.
      const withBad = (s.sessions || []).find((x) => x.n_bad > 0);
      q.key = (withBad || s.sessions[0]).key;
    }
    if (q.scope === 'mouse' && !q.mouse && (s.mice || []).length) {
      q.mouse = String(s.mice[0]);
    }
    if (q.scope === 'group' && !q.group && (s.groups || []).length) {
      q.group = s.groups[0];
    }
    if (q.scope === 'range') {
      if (!q.from && s.first_day) q.from = s.first_day;
      if (!q.to && s.last_day) q.to = s.last_day;
    }
  }

  function args() {
    const p = new URLSearchParams({ scope: q.scope, form: q.form });
    if (q.scope === 'session') p.set('key', q.key);
    if (q.scope === 'mouse') p.set('mouse', q.mouse);
    if (q.scope === 'group') p.set('group', q.group);
    if (q.scope === 'range') {
      if (q.from) p.set('from', q.from);
      if (q.to) p.set('to', q.to);
    }
    if (q.clean) p.set('clean', '1');
    return p.toString();
  }

  const refresh = debounce(async function refresh_() {
    if (q.tool === 'curate') { await loadCuration(); return; }
    if (q.tool === 'strata') { await loadStrata(); return; }
    if (busy) return;
    busy = true;
    const host = $('#tkResult');
    if (host) host.style.opacity = '0.55';
    try {
      preview = await api('/api/toolkit/bad-channels?' + args());
      preview.error = null;
    } catch (e) {
      preview = { error: e.message, rows: [], columns: [], summary: {} };
    } finally {
      busy = false;
      renderResult();
    }
  }, 220);

  /* ==================================================================
     The page
     ================================================================== */
  function render() {
    const host = $('#tkBody');
    if (!host) return;
    host.innerHTML = '';
    host.appendChild(el('div', { class: 'tk-layout' }, [
      el('div', { class: 'tk-tools' }, [
        el('div', { class: 'section-label', style: 'margin-top:0',
                    text: 'Tools' }),
        toolButton('bad', 'Bad channels',
                   'Export which channels were marked bad, by session, mouse, '
                   + 'project or date range.'),
        toolButton('curate', 'Event curation',
                   'Import candidate dentate spikes or IEDs, then go through '
                   + 'them one at a time and say what each one is.'),
        toolButton('strata', 'StrataScope',
                   'Say which anatomical layer each channel is in, against '
                   + 'the live rasters rather than a cropped screenshot.'),
        el('p', { class: 'hint tk-soon',
          text: 'More tools will land here as they earn their place. This is '
              + 'the section for anything that spans many recordings at '
              + 'once.' }),
      ]),
      el('div', { class: 'tk-main', id: 'tkMain' },
         (q.tool === 'curate' || q.tool === 'strata')
           ? [el('div', { class: 'tk-result', id: 'tkResult' })]
           : [scopeCard(),
              el('div', { class: 'tk-result', id: 'tkResult' })]),
    ]));
    renderResult();
  }

  function toolButton(id, name, blurb) {
    return el('button', {
      class: 'tk-tool' + (q.tool === id ? ' on' : ''),
      onclick: () => { q.tool = id; render(); refresh(); },
    }, [
      el('strong', { text: name }),
      el('span', { text: blurb }),
    ]);
  }

  /* ---------- picking the scope ---------- */
  function scopeCard() {
    const box = el('div', { class: 'card tk-scope' });
    box.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: 'Which recordings' }));

    const total = (scopes && scopes.total) || 0;
    const choices = [
      ['all', 'Everything', total + ' recorded session'
        + (total === 1 ? '' : 's')],
      ['session', 'One session', 'pick it below'],
      ['mouse', 'One mouse', 'every session for that animal'],
      ['group', 'One project', 'every session in it'],
      ['range', 'A date range', 'by recording date'],
    ];
    box.appendChild(el('div', { class: 'tk-pills' }, choices.map(([id, name, sub]) =>
      el('button', {
        class: 'pill' + (q.scope === id ? ' active' : ''),
        title: sub,
        onclick: () => { q.scope = id; seedScope(); render(); refresh(); },
      }, [
        el('span', { text: name }),
        el('span', { class: 'tk-pill-sub', text: sub }),
      ]))));

    // Only the fields the chosen scope actually uses, so there is never a
    // date range sitting greyed out next to a session picker.
    const fields = el('div', { class: 'tk-fields' });
    if (q.scope === 'session') fields.appendChild(sessionPicker());
    if (q.scope === 'mouse') fields.appendChild(listPicker(
      'Mouse', (scopes && scopes.mice) || [], q.mouse,
      (v) => { q.mouse = v; refresh(); }, (m) => 'm' + m));
    if (q.scope === 'group') fields.appendChild(listPicker(
      'Project', (scopes && scopes.groups) || [], q.group,
      (v) => { q.group = v; refresh(); }));
    if (q.scope === 'range') {
      fields.appendChild(field('From', el('input', {
        type: 'date', value: q.from,
        min: (scopes || {}).first_day || null,
        max: (scopes || {}).last_day || null,
        onchange: (e) => { q.from = e.target.value; refresh(); },
      })));
      fields.appendChild(field('To', el('input', {
        type: 'date', value: q.to,
        min: (scopes || {}).first_day || null,
        max: (scopes || {}).last_day || null,
        onchange: (e) => { q.to = e.target.value; refresh(); },
      })));
      if (scopes && scopes.first_day) {
        fields.appendChild(el('p', { class: 'hint',
          text: 'Recordings on disk run ' + scopes.first_day + ' to '
              + scopes.last_day + '.' }));
      }
    }
    if (fields.childNodes.length) box.appendChild(fields);

    box.appendChild(el('div', { class: 'section-label', text: 'Shape' }));
    box.appendChild(el('div', { class: 'tk-pills flat' }, [
      el('button', {
        class: 'pill' + (q.form === 'long' ? ' active' : ''),
        title: 'One row per bad channel. Filters and pivots cleanly.',
        onclick: () => { q.form = 'long'; render(); refresh(); },
      }, [el('span', { text: 'One row per channel' })]),
      el('button', {
        class: 'pill' + (q.form === 'wide' ? ' active' : ''),
        title: 'One row per session, channels listed in a cell. Easier to read.',
        onclick: () => { q.form = 'wide'; render(); refresh(); },
      }, [el('span', { text: 'One row per session' })]),
    ]));
    box.appendChild(el('label', { class: 'toggle' + (q.clean ? ' on' : '') }, [
      el('input', {
        type: 'checkbox', checked: q.clean ? 'checked' : null,
        onchange: (e) => { q.clean = e.target.checked; refresh(); },
      }),
      el('span', { text: 'Include sessions with nothing marked' }),
    ]));
    box.appendChild(el('p', { class: 'hint',
      text: 'A zero row is the only way to tell a session that was checked '
          + 'and found clean from one nobody has looked at.' }));
    return box;
  }

  function sessionPicker() {
    const list = (scopes && scopes.sessions) || [];
    return field('Session', el('select', {
      onchange: (e) => { q.key = e.target.value; refresh(); },
    }, list.map((s) => el('option', {
      value: s.key,
      selected: q.key === s.key ? 'selected' : null,
      // The bad count in the label answers the question before it is asked.
      text: (s.label || s.key) + (s.n_bad ? '   (' + s.n_bad + ' bad)' : ''),
    }))));
  }

  function listPicker(label, values, current, onchange, fmt) {
    if (!values.length) {
      return el('p', { class: 'hint',
        text: 'No ' + label.toLowerCase() + ' has been recorded yet. Open a '
            + 'recording in Xplorefinder first.' });
    }
    return field(label, el('select', {
      onchange: (e) => onchange(e.target.value),
    }, values.map((v) => el('option', {
      value: String(v),
      selected: String(current) === String(v) ? 'selected' : null,
      text: fmt ? fmt(v) : String(v),
    }))));
  }

  function field(label, control) {
    return el('div', { class: 'field' }, [
      el('label', { text: label }), control,
    ]);
  }

  /* ---------- the rows, and what they add up to ---------- */
  /* ==================================================================
     Event curation

     A detector says where something might be; curation says what it actually
     was. Keeping those apart is the whole design: candidates arrive
     unspecified and stay that way until somebody looks at them.
     ================================================================== */
  let cur = null;

  async function loadCuration() {
    try {
      cur = await api('/api/curation');
      cur.registry = await api('/api/registry');
    } catch (e) {
      cur = { error: e.message, sets: [], kinds: [] };
    }
    renderCuration();
  }

  function renderCuration() {
    const host = $('#tkResult');
    if (!host) return;
    host.style.opacity = '1';
    host.innerHTML = '';
    if (!cur) {
      host.appendChild(el('div', { class: 'hint', text: 'Reading\u2026' }));
      return;
    }

    host.appendChild(el('div', { class: 'tk-head' }, [
      el('div', {}, [
        el('h2', { text: 'Event curation' }),
        el('p', { class: 'sub',
          text: 'Import a list of candidate times, then go through them one '
              + 'at a time in the recording and say what each one is.' }),
      ]),
      el('div', { class: 'spacer' }),
      el('button', { class: 'btn', text: 'Import candidates\u2026',
                     onclick: importCandidates }),
    ]));

    const sets = cur.sets || [];
    if (!sets.length) {
      host.appendChild(el('div', { class: 'hint tk-empty',
        text: 'Nothing to curate yet. Import a list of candidate times '
            + '\u2014 from the Event Bank or from a file \u2014 and it '
            + 'will appear here. Every candidate arrives unspecified.' }));
      return;
    }

    const list = el('div', { class: 'cur-sets' });
    for (const st of sets) {
      const pr = st.progress || {};
      const done = pr.left === 0 && pr.total > 0;
      const reach = st.session && st.session.reachable;
      list.appendChild(el('div', { class: 'cur-set' + (done ? ' done' : '') }, [
        el('div', { class: 'cur-set-top' }, [
          el('strong', { text: st.name }),
          el('span', { class: 'hk-chip', text: st.kind_name }),
          el('span', { class: 'cur-set-sess',
                       text: (st.session || {}).label || st.gid }),
          el('div', { style: 'flex:1' }),
          el('span', { class: 'cur-set-n',
            text: pr.specified + ' / ' + pr.total
                + (done ? '  \u2713' : '  \u00b7  ' + pr.left + ' left') }),
        ]),
        el('div', { class: 'cur-prog small' }, [
          el('i', { style: 'width:' + (pr.percent || 0) + '%' }),
        ]),
        el('div', { class: 'cur-set-tally' },
           (st.labels || []).map((l) => el('span', {
             class: 'cur-tally', style: '--cat:' + l.color,
             text: l.name + '  ' + ((pr.by_label || {})[l.id] || 0),
           }))),
        el('div', { class: 'cur-set-acts' }, [
          el('button', {
            class: 'btn sm', text: pr.left ? 'Curate\u2026' : 'Review\u2026',
            disabled: reach ? null : 'disabled',
            title: reach
              ? 'Open the recording and step through the candidates'
              : 'This recording is not on a drive this machine can reach',
            onclick: () => BARRY.curate.enter(st.gid, st.kind),
          }),
          el('button', {
            class: 'btn ghost sm', text: 'Bank the results\u2026',
            disabled: pr.specified ? null : 'disabled',
            title: pr.specified
              ? 'Send the decided ones to the Event Bank, one entry per '
                + 'category'
              : 'Nothing has been decided yet',
            onclick: () => bankSet(st),
          }),
          el('button', {
            class: 'btn ghost sm', text: 'Export CSV',
            onclick: () => window.open(
              '/api/curation/' + encodeURIComponent(st.gid) + '/'
              + encodeURIComponent(st.kind) + '/export', '_blank'),
          }),
          el('button', {
            class: 'btn ghost sm danger', text: 'Delete',
            onclick: async () => {
              await apiPost('/api/curation/' + encodeURIComponent(st.gid)
                            + '/' + encodeURIComponent(st.kind) + '/delete',
                            {});
              loadCuration();
            },
          }),
        ]),
      ]));
    }
    host.appendChild(list);
  }

  async function bankSet(st) {
    const who = await askPath('Who is banking these?', 'your name or email');
    if (!who) return;
    try {
      const res = await apiPost(
        '/api/curation/' + encodeURIComponent(st.gid) + '/'
        + encodeURIComponent(st.kind) + '/bank', { added_by: who });
      toast('Banked ' + res.entries.length + ' entr'
            + (res.entries.length === 1 ? 'y' : 'ies') + ': '
            + res.entries.map((x) => x.label + ' (' + x.n + ')').join(', '),
            'ok', 8000);
      BARRY.refreshSync();
    } catch (e) { toast(e.message, 'err', 8000); }
  }

  /* Where candidates come from. Both sources end at the same place: a list
     of times, none of them decided. */
  async function importCandidates() {
    const reg = (cur.registry || {}).tree || [];
    const rows = reg.flatMap((p) => p.mice.flatMap((m) => m.sessions));
    if (!rows.length) {
      toast('No recordings are registered yet. Open one in Xplorefinder '
            + 'first.', 'err', 7000);
      return;
    }

    const sessSel = el('select', {}, rows.map((s) => el('option', {
      value: s.gid,
      text: (s.label || s.key) + (s.reachable ? '' : '   (not on this machine)'),
    })));
    const kindSel = el('select', {}, (cur.kinds || []).map((k) =>
      el('option', { value: k.id, text: k.name })));
    const nameIn = el('input', { type: 'text',
                                 placeholder: 'e.g. LL detector pass 1' });

    let staged = [];
    let from = null;
    const note = el('p', { class: 'hint', text: 'Nothing picked yet.' });
    const stage = (evs, what) => {
      staged = (evs || []).filter(
        (e) => typeof (e && e.start !== undefined ? e.start : e) === 'number');
      from = what;
      note.textContent = staged.length
        ? staged.length + ' candidate(s) from ' + what
          + ' \u2014 all of them unspecified until curated.'
        : 'That source had no usable times in it.';
    };

    const src = el('div', { class: 'choice-grid' }, [
      el('button', { class: 'choice', onclick: async () => {
        const s = rows.find((r) => r.gid === sessSel.value);
        try {
          const res = await apiPost('/api/bank/for-session', {
            identity: { key: s.key, loose_key: s.loose_key, mouse: s.mouse,
                        session: s.session, start: s.start },
          });
          const list = res.entries || [];
          if (!list.length) { stage([], 'the bank (nothing banked)'); return; }
          const full = await api('/api/bank/'
                                 + encodeURIComponent(list[0].id));
          stage((full.entry || {}).events || [],
                'the bank: ' + list[0].name);
        } catch (e) { toast(e.message, 'err', 7000); }
      } }, [
        el('strong', { text: 'From the Event Bank' }),
        el('span', { text: 'whatever is banked against this recording' }),
      ]),
      el('button', { class: 'choice', onclick: async () => {
        const path = await pickPath('file', '');
        if (!path) return;
        try {
          const info = await apiPost('/api/events/inspect', { path });
          stage(info.events || info.preview || [], baseName(path));
        } catch (e) { toast(e.message, 'err', 8000); }
      } }, [
        el('strong', { text: 'From a file' }),
        el('span', { text: 'a CSV, .mat or .nev of times' }),
      ]),
    ]);

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Import candidates' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { class: 'confirm-msg',
          text: 'Every candidate arrives unspecified. That is the point: the '
              + 'import records that a detector thought something was here, '
              + 'not that it was right.' }),
        el('div', { class: 'wiz-grid' }, [
          el('div', { class: 'field' }, [
            el('label', { text: 'Recording' }), sessSel]),
          el('div', { class: 'field' }, [
            el('label', { text: 'What kind' }), kindSel]),
        ]),
        el('div', { class: 'field' }, [
          el('label', { text: 'Call this set' }), nameIn]),
        el('div', { class: 'section-label', text: 'Where from' }),
        src,
        note,
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel',
                       onclick: closeModal }),
        el('button', { class: 'btn primary', text: 'Import', onclick: async () => {
          if (!staged.length) {
            toast('Pick a source with some times in it first.', 'err');
            return;
          }
          try {
            const res = await apiPost('/api/curation/create', {
              gid: sessSel.value, kind: kindSel.value,
              name: nameIn.value.trim() || null,
              events: staged,
              source: { from },
            });
            closeModal();
            toast('Imported ' + res.added + ' candidate(s).', 'ok', 6000);
            loadCuration();
            BARRY.refreshSync();
          } catch (e) { toast(e.message, 'err', 8000); }
        } }),
      ]),
    ]));
  }

  /* ==================================================================
     StrataScope
     ================================================================== */
  let strata = null;

  async function loadStrata() {
    try {
      strata = await api('/api/layers');
      strata.registry = await api('/api/registry');
    } catch (e) {
      strata = { error: e.message, sheets: [], regions: [] };
    }
    renderStrata();
  }

  function renderStrata() {
    const host = $('#tkResult');
    if (!host) return;
    host.style.opacity = '1';
    host.innerHTML = '';
    if (!strata) {
      host.appendChild(el('div', { class: 'hint', text: 'Reading\u2026' }));
      return;
    }

    const rows = ((strata.registry || {}).tree || [])
      .flatMap((p) => p.mice.flatMap((m) => m.sessions));
    const pick = el('select', { id: 'strataPick' }, rows.map((s) => el('option', {
      value: s.gid,
      text: (s.label || s.key) + (s.reachable ? '' : '   (not on this machine)'),
      disabled: s.reachable ? null : 'disabled',
    })));

    host.appendChild(el('div', { class: 'tk-head' }, [
      el('div', {}, [
        el('h2', { text: 'StrataScope' }),
        el('p', { class: 'sub',
          text: 'Which anatomical layer each channel is sitting in \u2014 '
              + 'labelled against the live voltage, CSD and theta rasters, so '
              + 'there is nothing to crop and the rows cannot drift off the '
              + 'channels.' }),
      ]),
      el('div', { class: 'spacer' }),
      pick,
      el('button', {
        class: 'btn', text: 'Open\u2026',
        disabled: rows.length ? null : 'disabled',
        onclick: () => BARRY.strata.enter(pick.value),
      }),
    ]));

    const sheets = strata.sheets || [];
    if (!sheets.length) {
      host.appendChild(el('div', { class: 'hint tk-empty',
        text: 'No layer sheets yet. Pick a recording above and open it '
            + '\u2014 a sheet is made the first time.' }));
    } else {
      const list = el('div', { class: 'cur-sets' });
      for (const sh of sheets) {
        const pr = sh.progress || {};
        const reach = sh.session && sh.session.reachable;
        list.appendChild(el('div', {
          class: 'cur-set' + (pr.left === 0 && pr.total ? ' done' : ''),
        }, [
          el('div', { class: 'cur-set-top' }, [
            el('strong', { text: sh.session_label || sh.gid }),
            el('span', { class: 'hk-chip', text: 'layers' }),
            el('div', { style: 'flex:1' }),
            el('span', { class: 'cur-set-n',
              text: pr.labelled + ' / ' + pr.total + ' channels' }),
          ]),
          el('div', { class: 'cur-prog small' }, [
            el('i', { style: 'width:' + (pr.percent || 0) + '%' }),
          ]),
          el('div', { class: 'cur-set-tally' },
             (sh.regions || []).filter(
               (r) => (pr.by_region || {})[r.id]).map((r) => el('span', {
                 class: 'cur-tally', style: '--cat:' + r.color,
                 text: r.name + '  ' + pr.by_region[r.id],
               }))),
          el('div', { class: 'cur-set-acts' }, [
            el('button', {
              class: 'btn sm',
              text: pr.left ? 'Continue\u2026' : 'Review\u2026',
              disabled: reach ? null : 'disabled',
              onclick: () => BARRY.strata.enter(sh.gid),
            }),
            el('button', {
              class: 'btn ghost sm', text: 'Export CSV',
              onclick: () => window.open('/api/layers/'
                + encodeURIComponent(sh.gid) + '/export', '_blank'),
            }),
            el('button', {
              class: 'btn ghost sm danger', text: 'Delete',
              onclick: async () => {
                await apiPost('/api/layers/' + encodeURIComponent(sh.gid)
                              + '/delete', {});
                loadStrata();
              },
            }),
          ]),
        ]));
      }
      host.appendChild(list);
    }

    host.appendChild(el('div', { class: 'section-label', text: 'The layers' }));
    host.appendChild(el('div', { class: 'strata-legend' },
      (strata.regions || []).map((r) => el('span', {
        class: 'cur-tally', style: '--cat:' + r.color,
        title: r.note || '', text: r.name,
      }))));
  }

  function renderResult() {
    if (q.tool === 'curate') { renderCuration(); return; }
    if (q.tool === 'strata') { renderStrata(); return; }
    const host = $('#tkResult');
    if (!host) return;
    host.style.opacity = '1';
    host.innerHTML = '';

    if (!preview) {
      host.appendChild(el('div', { class: 'hint', text: 'Reading…' }));
      return;
    }
    if (preview.error) {
      host.appendChild(el('div', { class: 'rb-verdict missing' }, [
        el('div', { class: 'rb-verdict-top' }, [
          el('span', { class: 'rb-dot missing' }),
          el('strong', { text: 'That scope does not work' }),
        ]),
        el('p', { style: 'margin:0;font-size:12px', text: preview.error }),
      ]));
      return;
    }

    const sm = preview.summary || {};
    host.appendChild(el('div', { class: 'tk-head' }, [
      el('div', {}, [
        el('h2', { text: 'Bad channels' }),
        el('p', { class: 'sub', text: preview.scope_label || '' }),
      ]),
      el('div', { class: 'spacer' }),
      el('button', {
        class: 'btn', text: 'Download CSV',
        disabled: preview.rows.length ? null : 'disabled',
        title: preview.rows.length
          ? 'Also filed under Results/ToolKit'
          : 'Nothing to export in this scope',
        onclick: download,
      }),
    ]));

    host.appendChild(el('div', { class: 'stat-row' }, [
      chip(sm.sessions + ' session' + (sm.sessions === 1 ? '' : 's'), 'good'),
      chip(sm.with_bad + ' with something marked',
           sm.with_bad ? 'warn' : null),
      chip(sm.clean + ' with nothing marked'),
      chip(sm.bad_total + ' bad channel'
           + (sm.bad_total === 1 ? '' : 's') + ' in total'),
      chip(sm.distinct_channels + ' distinct channel number'
           + (sm.distinct_channels === 1 ? '' : 's')),
      sm.first_day ? chip(sm.first_day + ' → ' + sm.last_day) : null,
    ].filter(Boolean)));

    // A channel that goes bad in several sessions is usually a wire, not a
    // recording -- which is a different problem, so it gets said out loud.
    const rep = sm.repeat_offenders || [];
    if (rep.length) {
      host.appendChild(el('div', { class: 'tk-repeat' }, [
        el('strong', { text: 'Bad more than once: ' }),
        el('span', { text: rep.map((r) => 'CSC ' + r.channel
                     + ' (' + r.sessions + ')').join(',  ') }),
        el('p', { class: 'hint', style: 'margin:4px 0 0',
          text: 'A channel that keeps coming up is worth checking at the '
              + 'headstage rather than in the analysis.' }),
      ]));
    }

    if (!preview.rows.length) {
      host.appendChild(el('div', { class: 'hint tk-empty',
        text: 'No bad channels are marked in ' + (preview.scope_label || 'this scope')
            + '. Mark them on the channel list in Xplorefinder and they will '
            + 'appear here.' }));
      return;
    }

    host.appendChild(table(preview.columns, preview.rows));
  }

  function chip(text, kind) {
    return el('span', { class: 'stat-chip' + (kind ? ' ' + kind : ''), text });
  }

  function table(cols, rows) {
    // Wide tables scroll inside their own box; the page must not.
    const wrap = el('div', { class: 'tk-tablewrap' });
    const t = el('table', { class: 'res-table tk-table' });
    t.appendChild(el('thead', {}, [el('tr', {}, cols.map((c) =>
      el('th', { text: c.replace(/_/g, ' ') })))]));
    const body = el('tbody');
    // A cap on what is drawn, not on what is exported: 4000 rows of DOM is
    // slow to build and nobody reads past the first screen anyway.
    const CAP = 500;
    for (const r of rows.slice(0, CAP)) {
      body.appendChild(el('tr', {}, cols.map((c) => el('td', {
        text: r[c] === null || r[c] === undefined ? '' : String(r[c]),
        title: c === 'path' ? String(r[c] || '') : null,
        class: c === 'channel' || c === 'bad_channels' ? 'tk-ch' : null,
      }))));
    }
    t.appendChild(body);
    wrap.appendChild(t);
    if (rows.length > CAP) {
      wrap.appendChild(el('p', { class: 'hint',
        text: 'Showing the first ' + CAP + ' of ' + rows.length
            + ' rows. The download has all of them.' }));
    }
    return wrap;
  }

  /* ---------- the download ---------- */
  async function download() {
    const url = '/api/toolkit/bad-channels/export?' + args();
    try {
      const res = await fetch(url);
      if (!res.ok) {
        let msg = 'HTTP ' + res.status;
        try { msg = (await res.json()).error || msg; } catch (e) { /* text */ }
        toast(msg, 'err', 8000);
        return;
      }
      const blob = await res.blob();
      const name = (res.headers.get('Content-Disposition') || '')
        .replace(/.*filename="?([^"]+)"?.*/, '$1') || 'bad-channels.csv';
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);

      const rel = res.headers.get('X-Barry-Output');
      toast((res.headers.get('X-Barry-Rows') || '?') + ' rows downloaded'
            + (rel ? ' — also filed at Results/' + rel : ''), 'ok', 7000);
      BARRY.activity.log('toolkit.bad_channels.export', {
        scope: q.scope, form: q.form, rows: res.headers.get('X-Barry-Rows'),
        run: res.headers.get('X-Barry-Run-Id'),
      });
      BARRY.refreshSync();
    } catch (e) {
      toast('Export failed: ' + e.message, 'err', 8000);
    }
  }

  function init() {
    const r = $('#tkRefresh');
    if (r) {
      r.addEventListener('click', async () => {
        scopes = null;
        await loadScopes();
        refresh();
      });
    }
  }

  return { init, onShow, refresh };
})();
