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
    /* Kilosort has nothing to do with bad channels.

       It used to fall through to the query below, which fetched the whole
       bad-channel table nobody had asked for and dimmed the pane to 0.55
       while it ran. renderResult then returned early for Kilosort, before
       the line that puts the opacity back -- so the pane stayed at 55% for
       good. That is the "everything is greyed out". */
    if (q.tool === 'kilosort') { renderResult(); return; }
    if (q.tool === 'snapshots') { renderResult(); return; }
    if (busy) return;
    busy = true;
    /* Which tool asked. A debounced request can land after you have clicked
       something else, and rendering its answer then replaces the pane you
       just opened -- which is the "it snaps back to another tool". */
    const asked = q.tool;
    const host = $('#tkResult');
    // Dimmed while re-querying, but only when there is already something to
    // dim; the first read shows the loader instead of a grey rectangle.
    if (host && preview) host.style.opacity = '0.55';
    else if (host) tkLoading('Bad channels',
                             ['reading every recording that has marks']);
    try {
      preview = await api('/api/toolkit/bad-channels?' + args());
      preview.error = null;
    } catch (e) {
      preview = { error: e.message, rows: [], columns: [], summary: {} };
    } finally {
      busy = false;
      if (asked !== q.tool) {
        // Superseded. Undim, and leave the current tool alone.
        if (host) host.style.opacity = '1';
      } else {
        renderResult();
      }
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
        toolButton('kilosort', 'Kilosort',
                   'Check this machine can sort, run a sort against a '
                   + 'recording, then open it in Phy.'),
        toolButton('snapshots', 'Import sorted snapshots',
                   'Read a folder of dentate-spike images that were sorted '
                   + 'by dragging them into Dentate Spike / Garbage / Flag '
                   + 'folders, and turn it back into curation.'),
        el('p', { class: 'hint tk-soon',
          text: 'More tools will land here as they earn their place. This is '
              + 'the section for anything that spans many recordings at '
              + 'once.' }),
      ]),
      el('div', { class: 'tk-main', id: 'tkMain' },
         /* Which tools own the whole pane. The scope card below is the
            bad-channel query's, and means nothing to the others -- the
            snapshot importer was showing it and asking which recordings to
            scope a folder read to. */
         (q.tool === 'curate' || q.tool === 'strata'
          || q.tool === 'kilosort' || q.tool === 'snapshots')
           ? [el('div', { class: 'tk-result', id: 'tkResult' })]
           : [scopeCard(),
              el('div', { class: 'tk-result', id: 'tkResult' })]),
    ]));
    renderResult();
  }

  function toolButton(id, name, blurb) {
    return el('button', {
      class: 'tk-tool' + (q.tool === id ? ' on' : ''),
      onclick: () => {
        q.tool = id;
        // The Kilosort pane owns its own host; let it rebuild.
        const host = document.getElementById('tkResult');
        if (host) delete host.dataset.ks;
        render();
        refresh();
      },
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

  /* Show what it is waiting on while it waits.

     Two requests, and the registry is the slow one -- over a second on a
     network share. The pane used to say "Reading..." for both of them and
     look identical whether it was about to finish or had stalled. */
  function tkLoading(label, steps) {
    const host = $('#tkResult');
    if (!host) return null;
    host.style.opacity = '1';
    host.innerHTML = '';
    const l = stepLoader(label, steps);
    host.appendChild(el('div', { class: 'tk-loading' }, [l]));
    return l;
  }

  async function loadCuration() {
    const l = (q.tool === 'curate' && !cur)
      ? tkLoading('Event curation', ['reading the curation sets',
                                     'reading the recording registry'])
      : null;
    try {
      cur = await api('/api/curation');
      if (l) l.step('reading the recording registry');
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
      host.appendChild(el('div', { class: 'tk-loading' }, [
        stepLoader('Event curation', ['reading the curation sets',
                                      'reading the recording registry'])]));
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

  /* Browse the bank and pick something, rather than being handed
     entries[0].

     Opens filtered to the kind being curated and searched for the recording
     picked above -- both clearable, because "show me what else is in here"
     is a reasonable thing to want and the old flow made it impossible.
     Resolves to the full entry, or null if cancelled. */
  /* The bank's own vocabulary, borrowed rather than duplicated -- it is
     loaded from the server and this module has no copy of it. */
  const bankTypes = () => {
    const eb = BARRY.views.eventbank;
    return (eb && eb.typeList && eb.typeList()) || [];
  };
  const bankTypeName = (id) => {
    const t = bankTypes().find((x) => x.id === id || x === id);
    return (t && (t.name || t)) || id || 'event';
  };

  function bankMatch(entry, sess) {
    if (!sess) return 'unknown';
    if (entry.session_key && sess.key && entry.session_key === sess.key) {
      return 'exact';
    }
    if (entry.mouse != null && entry.mouse === sess.mouse
        && entry.session != null && entry.session === sess.session) {
      return 'same session';
    }
    if (entry.mouse != null && entry.mouse === sess.mouse) {
      return 'same mouse only';
    }
    return 'different recording';
  }

  async function pickFromBank(sess, wantKind) {
    let all = [];
    try {
      const res = await api('/api/bank');
      all = res.entries || [];
    } catch (e) {
      toast('Could not read the bank: ' + e.message, 'err', 8000);
      return null;
    }
    if (!all.length) {
      toast('The Event Bank is empty.', 'err', 5000);
      return null;
    }

    /* Prefilled, not restricted. The search starts on this recording and the
       type on what you are curating, and either can be cleared. */
    let query = [sess.mouse != null ? 'm' + sess.mouse : '',
                 sess.session != null ? 's' + sess.session : '']
      .filter(Boolean).join(' ');
    let typeFilter = wantKind || '';
    let chosen = null;
    let widened = '';

    const rank = { 'exact': 0, 'same session': 1, 'same mouse only': 2,
                   'different recording': 3, 'unknown': 4 };

    const matching = () => {
      const q = query.trim().toLowerCase();
      const words = q ? q.split(/\s+/) : [];
      return all.filter((e) => {
        if (typeFilter && e.type !== typeFilter) return false;
        if (!words.length) return true;
        const hay = [e.name, e.session_label, e.project,
                     e.mouse != null ? 'm' + e.mouse : '',
                     e.session != null ? 's' + e.session : '',
                     e.type, e.added_by].filter(Boolean).join(' ').toLowerCase();
        return words.every((w) => hay.indexOf(w) >= 0);
      }).sort((a, b) => (rank[bankMatch(a, sess)] - rank[bankMatch(b, sess)])
                     || String(a.name).localeCompare(String(b.name)));
    };

    /* Opening on an empty list is a bad answer to "what is in the bank".

       The filters start narrow on purpose -- this recording, this kind --
       but a recording with nothing banked against it would then show
       nothing at all, which reads as a broken dialog rather than as an
       honest "none for this one". So if the narrow view is empty the search
       is dropped, and if that is still empty the type goes too, with a line
       saying what happened. */
    const narrow = matching().length;
    if (!narrow && query) {
      query = '';
      widened = 'Nothing banked against this recording'
              + (typeFilter ? ' for that type' : '') + ', so this is '
              + (typeFilter ? 'every entry of that type.' : 'the whole bank.');
    }
    if (!matching().length && typeFilter) {
      typeFilter = '';
      widened = 'Nothing in the bank matched this recording or that type, '
              + 'so this is everything.';
    }

    return new Promise((resolve) => {
      let done = false;
      const finish = (v) => { if (!done) { done = true; closeModal(); resolve(v); } };

      const list = el('div', { class: 'bm-list tall bank-targets' });
      const note = el('p', { class: 'confirm-sub' });
      const count = el('span', { class: 'hint' });
      const okBtn = el('button', {
        class: 'btn', text: 'Use this set', disabled: 'disabled',
        onclick: async () => {
          if (!chosen) return;
          try {
            const full = await api('/api/bank/' + encodeURIComponent(chosen.id));
            const entry = full.entry || {};
            finish({ name: chosen.name, events: entry.events || [] });
          } catch (e) {
            toast('Could not read that entry: ' + e.message, 'err', 8000);
          }
        },
      });

      const paint = () => {
        const rows2 = matching();
        list.innerHTML = '';
        count.textContent = rows2.length + ' of ' + all.length + ' entries';
        if (!rows2.length) {
          list.appendChild(el('div', { class: 'hint',
            text: 'Nothing in the bank matches that. Clear the search or the '
                + 'type to see everything.' }));
        }
        for (const e of rows2) {
          const m = bankMatch(e, sess);
          list.appendChild(el('label', {
            class: 'bm-row' + (chosen && chosen.id === e.id ? ' on' : ''),
          }, [
            el('input', {
              type: 'radio', name: 'bankPick',
              checked: chosen && chosen.id === e.id ? 'checked' : null,
              onchange: () => { chosen = e; paint(); },
            }),
            el('span', { class: 'mk-name',
                         text: e.name + '  \u00b7  ' + (e.session_label || '?')
                             + '  \u00b7  ' + (e.n || 0) + ' event(s)' }),
            el('span', { class: 'flagchip', text: bankTypeName(e.type) }),
            el('span', { class: 'flagchip' + (m === 'exact' ? ' good'
                         : (m === 'different recording' ? ' bad' : '')),
                         text: m }),
          ]));
        }
        okBtn.disabled = chosen ? null : 'disabled';
        if (!chosen) {
          note.textContent = '';
          note.className = 'confirm-sub';
        } else {
          const m = bankMatch(chosen, sess);
          if (m === 'exact' || m === 'same session') {
            note.textContent = chosen.n + ' candidate(s) from '
              + (chosen.session_label || 'that entry') + '.';
            note.className = 'confirm-sub';
          } else {
            note.textContent = 'That set is ' + m + ' \u2014 banked against '
              + (chosen.session_label || 'another recording')
              + '. Its times are seconds from the start of that one, so on '
              + 'this recording they will land somewhere arbitrary.';
            note.className = 'confirm-sub warn';
          }
        }
      };

      const search = el('input', {
        type: 'text', value: query, placeholder: 'Search name, mouse, session…',
        oninput: (e) => { query = e.target.value; paint(); },
      });
      const types = el('select', {
        onchange: (e) => { typeFilter = e.target.value; paint(); },
      }, [el('option', { value: '', text: 'Every type' })].concat(
        bankTypes().map((t) => el('option', {
          value: t.id || t, text: t.name || t,
          selected: (t.id || t) === typeFilter ? 'selected' : null,
        }))));

      showModal(el('div', {}, [
        el('div', { class: 'mh' }, [
          el('h3', { text: 'Import from the Event Bank' }),
          el('span', { class: 'sub', text: 'onto '
            + (sess.label || ('m' + sess.mouse + ' s' + sess.session)) }),
          el('div', { class: 'spacer' }),
          el('button', { class: 'close-x', onclick: () => finish(null),
            html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
        ]),
        el('div', { class: 'mb' }, [
          el('div', { class: 'bank-filter' }, [search, types, count]),
          widened ? el('p', { class: 'confirm-sub', text: widened }) : null,
          list,
          note,
        ]),
        el('div', { class: 'mf' }, [
          el('button', { class: 'btn ghost sm', text: 'Show everything',
            title: 'Clear the search and the type filter',
            onclick: () => { query = ''; typeFilter = '';
                             search.value = ''; types.value = ''; paint(); } }),
          el('div', { class: 'spacer' }),
          el('button', { class: 'btn ghost', text: 'Cancel',
                         onclick: () => finish(null) }),
          okBtn,
        ]),
      ]));
      paint();
    });
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

    // A search field, not a dropdown: there are hundreds of recordings now.
    let pickedGid = (rows.find((r) => r.reachable) || rows[0] || {}).gid;
    const sessPick = BARRY.pickSession({
      rows,
      value: pickedGid,
      placeholder: 'Which recording? Type a mouse, session or date\u2026',
      onpick: (r) => { pickedGid = r.gid; },
    });
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
        const s = rows.find((r) => r.gid === pickedGid);
        if (!s) { toast('Pick a recording first.', 'err'); return; }
        const picked = await pickFromBank(s, kindSel.value);
        if (!picked) return;
        stage(picked.events || [], 'the bank: ' + picked.name);
      } }, [
        el('strong', { text: 'From the Event Bank\u2026' }),
        el('span', { text: 'browse what is banked, this recording first' }),
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
            el('label', { text: 'Recording' }), sessPick]),
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
              gid: pickedGid, kind: kindSel.value,
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
    const l = (q.tool === 'strata' && !strata)
      ? tkLoading('StrataScope', ['reading the layer sheets',
                                  'reading the recording registry'])
      : null;
    try {
      strata = await api('/api/layers');
      if (l) l.step('reading the recording registry');
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
      host.appendChild(el('div', { class: 'tk-loading' }, [
        stepLoader('StrataScope', ['reading the layer sheets',
                                   'reading the recording registry'])]));
      return;
    }

    const rows = ((strata.registry || {}).tree || [])
      .flatMap((p) => p.mice.flatMap((m) => m.sessions));
    // Same search field as the curation importer, for the same reason.
    let strataGid = (rows.find((r) => r.reachable) || rows[0] || {}).gid;
    const pick = BARRY.pickSession({
      rows, value: strataGid,
      placeholder: 'Which recording? Type a mouse, session or date…',
      onpick: (r) => { strataGid = r.gid; },
    });
    pick.id = 'strataPick';

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
        onclick: () => {
          if (!strataGid) { toast('Pick a recording first.', 'err'); return; }
          BARRY.strata.enter(strataGid);
        },
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

  /* ==================================================================
     Importing a folder of sorted snapshots
     ==================================================================
     Thousands of dentate spikes were sorted before BARRY existed, by
     dragging one PNG per candidate into a folder named after the decision.
     That work is real and nobody is redoing it, so this reads it back.

     Scan first, always. The images carry an event number but not a time, so
     the decisions are matched to banked candidates by position -- which is
     only safe when the counts agree exactly. The scan is where you see
     whether they do, per recording, before anything is written.
     ================================================================== */
  let snapRoot = '';
  let snapScan = null;
  let snapBusy = false;

  const VERDICT_NOTE = {
    ready: 'will import',
    empty: 'no snapshots in it',
    unparsed: 'cannot tell which recording',
    'no-bank': 'nothing banked to get times from',
    'count-mismatch': 'counts disagree',
    gappy: 'numbering has gaps',
    'no-gid': 'the banked entry has no recording id',
    unreadable: 'could not read the folder',
  };

  function renderSnapshots() {
    const host = $('#tkResult');
    if (!host) return;
    host.innerHTML = '';

    host.appendChild(el('div', { class: 'section-label',
                                 style: 'margin-top:0',
                                 text: 'The folder to read' }));
    const pathIn = el('input', {
      type: 'text', value: snapRoot, style: 'flex:1;min-width:0',
      placeholder: 'E:\\PTEN_DS_Curation\\Visualized_spikes_...',
      oninput: (e) => { snapRoot = e.target.value; },
    });
    host.appendChild(el('div', { class: 'row', style: 'gap:8px' }, [
      pathIn,
      el('button', { class: 'btn ghost sm', text: 'Browse\u2026',
        onclick: async () => {
          const d = await pickPath('folder', snapRoot);
          if (d) { snapRoot = d; renderSnapshots(); }
        } }),
      el('button', {
        class: 'btn', text: snapBusy ? 'Scanning\u2026' : 'Scan',
        disabled: snapBusy ? 'disabled' : null,
        onclick: async () => {
          if (!snapRoot.trim()) { toast('Point it at a folder first.', 'err'); return; }
          snapBusy = true; renderSnapshots();
          try {
            snapScan = await apiPost('/api/dsimport/scan', { root: snapRoot });
          } catch (e) {
            snapScan = null;
            toast(e.message, 'err', 9000);
          } finally { snapBusy = false; renderSnapshots(); }
        } }),
    ]));

    host.appendChild(el('p', { class: 'hint',
      text: 'Each recording is a folder of numbered snapshots with '
          + 'Dentate Spike / Garbage / Flag / Flag for Deep Review inside '
          + 'it. Scanning writes nothing \u2014 it reports what would '
          + 'happen, per recording, so you can check it before it does.' }));

    if (!snapScan) return;

    const sum = snapScan.summary || {};
    const ready = (snapScan.rows || []).filter((r) => r.verdict === 'ready');
    host.appendChild(el('div', { class: 'rb-verdict '
      + (ready.length ? 'ok' : 'missing') }, [
      el('div', { class: 'rb-verdict-top' }, [
        el('strong', { text: ready.length + ' of ' + (sum.folders || 0)
                           + ' folders ready to import' }),
      ]),
      el('p', { text: [
        sum.events_spike ? sum.events_spike + ' dentate spikes' : null,
        sum.events_garbage ? sum.events_garbage + ' garbage' : null,
        sum.events_flag ? sum.events_flag + ' flagged' : null,
        sum.events_review ? sum.events_review + ' for deep review' : null,
        sum.events_undecided ? sum.events_undecided + ' still undecided' : null,
      ].filter(Boolean).join('  \u00b7  ') }),
      sum.conflicts ? el('p', { class: 'warn-line',
        text: sum.conflicts + ' snapshot(s) were filed under two different '
            + 'decisions. Those come in flagged, with a note saying which '
            + 'two, so they get looked at rather than guessed.' }) : null,
    ]));

    const table = el('table', { class: 'tk-table' });
    table.appendChild(el('thead', {}, [el('tr', {}, [
      el('th', { text: 'Folder' }), el('th', { text: 'Recording' }),
      el('th', { text: 'Events' }), el('th', { text: 'How they were sorted' }),
      el('th', { text: '' }),
    ])]));
    const body = el('tbody');
    for (const r of (snapScan.rows || [])) {
      const t = r.tally || {};
      const bits = [['spike', 'spikes'], ['garbage', 'garbage'],
                    ['flag', 'flagged'], ['review', 'deep review'],
                    ['undecided', 'undecided']]
        .filter(([k]) => t[k]).map(([k, name]) => t[k] + ' ' + name);
      body.appendChild(el('tr', { class: r.verdict === 'ready' ? '' : 'dim' }, [
        el('td', { text: r.folder }),
        el('td', { text: r.session_label || '\u2014',
                   title: r.gid || '' }),
        el('td', { text: String(r.n_images == null ? '' : r.n_images) }),
        el('td', { text: bits.join(', ')
                       + (r.conflicts && r.conflicts.length
                          ? '   (' + r.conflicts.length + ' conflicting)' : '') }),
        el('td', {}, [el('span', {
          class: 'flagchip' + (r.verdict === 'ready' ? ' good' : ' bad'),
          text: VERDICT_NOTE[r.verdict] || r.verdict,
          title: r.reason || '',
        })]),
      ]));
    }
    table.appendChild(body);
    host.appendChild(el('div', { class: 'tk-table-wrap' }, [table]));

    if (!ready.length) return;
    host.appendChild(el('div', { class: 'row', style: 'gap:8px;margin-top:10px' }, [
      el('p', { class: 'hint', style: 'flex:1',
        text: 'Importing replaces any curation set those recordings already '
            + 'have, because this is the record of a sort that already '
            + 'happened rather than something to merge into a half-finished '
            + 'one.' }),
      el('button', {
        class: 'btn', text: 'Import ' + ready.length + ' recording(s)',
        disabled: snapBusy ? 'disabled' : null,
        onclick: async () => {
          snapBusy = true; renderSnapshots();
          try {
            const res = await apiPost('/api/dsimport/apply',
                                      { token: snapScan.token });
            const nEv = (res.imported || [])
              .reduce((a, x) => a + (x.n || 0), 0);
            toast('Imported ' + (res.imported || []).length + ' recording(s), '
                  + nEv + ' candidates. Open Event curation to review the '
                  + 'flagged ones.', 'ok', 9000);
            BARRY.activity.log('dsimport.apply',
                               { folders: (res.imported || []).length, n: nEv });
            await loadCuration();
          } catch (e) {
            toast(e.message, 'err', 10000);
          } finally { snapBusy = false; renderSnapshots(); }
        } }),
    ]));
  }

  function renderResult() {
    /* Undim first, whatever branch this takes. Every early return below used
       to skip the line that reset it. */
    const box = document.getElementById('tkResult');
    if (box) box.style.opacity = '1';
    if (q.tool === 'kilosort') {
      const host = document.getElementById('tkResult');
      if (host && !host.dataset.ks) {
        host.dataset.ks = '1';
        BARRY.kilosort.load(host);
      }
      return;
    }
    if (q.tool === 'curate') { renderCuration(); return; }
    if (q.tool === 'strata') { renderStrata(); return; }
    if (q.tool === 'snapshots') { renderSnapshots(); return; }
    const host = $('#tkResult');
    if (!host) return;
    host.style.opacity = '1';
    host.innerHTML = '';

    if (!preview) {
      host.appendChild(el('div', { class: 'tk-loading' }, [
        stepLoader('Bad channels',
                   ['reading every recording that has marks'])]));
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

  return {
    init, onShow, refresh,
    /* Drop what each pane has cached, so the loading path can be exercised
       on a second visit. Only web/_dev/tkload.html uses this. */
    debugForget: () => { preview = null; cur = null; strata = null; },
  };
})();
