/* ==========================================================================
   eventbank.js -- the shared record of detected events.

   A detector's output normally ends up as an ets.mat beside the recording, on
   whichever drive it was run on. Six months later nobody can say which version
   of which script produced it. The bank is the answer: filed by project /
   mouse / session / type, and it will not take an entry that cannot say who
   added it, when, and what produced it.

   From here an entry goes back into Xplorefinder against a chosen recording.
   ========================================================================== */
'use strict';

BARRY.views.eventbank = (function () {
  let tree = [];
  let entries = [];
  let types = [];
  let meta = {};
  let query = '';
  let typeFilter = '';
  let projectFilter = '';
  let selected = null;        // the entry id shown in the detail pane

  async function load() {
    try {
      const res = await api('/api/bank');
      tree = res.tree || [];
      entries = res.entries || [];
      types = res.types || [];
      meta = res;
    } catch (e) {
      toast('Could not read the event bank: ' + e.message, 'err');
      tree = []; entries = [];
    }
    render();
  }

  const typeName = (id) => {
    const t = types.find((x) => x.id === id);
    return t ? t.name : (id || 'other');
  };

  function visible() {
    const q = query.trim().toLowerCase();
    return entries.filter((e) => {
      if (typeFilter && e.type !== typeFilter) return false;
      if (projectFilter && (e.project || 'Unfiled') !== projectFilter) return false;
      if (!q) return true;
      return [e.name, e.project, e.type, e.session_label, e.note,
              'm' + e.mouse, 's' + e.session,
              (e.source || {}).pipeline, (e.added || {}).by]
        .join(' ').toLowerCase().includes(q);
    });
  }

  /* ---------- rendering ---------- */
  function render() {
    const host = $('#bankBody');
    if (!host) return;
    host.innerHTML = '';

    const list = visible();
    const sub = $('#bankSub');
    if (sub) {
      sub.textContent = entries.length
        ? list.length + ' of ' + entries.length + ' entr(ies)  ·  '
          + tree.length + ' project(s)  ·  '
          + entries.reduce((n, e) => n + (e.n || 0), 0) + ' events banked'
        : 'Nothing banked yet.';
    }

    host.appendChild(toolbar());

    if (!entries.length) {
      host.appendChild(el('div', { class: 'empty-state' }, [
        el('svg', { viewBox: '0 0 24 24',
          html: '<rect x="3" y="4" width="18" height="16" rx="2"/>'
              + '<path d="M3 9h18M8 4v16"/>' }),
        el('p', { text: 'The bank is empty. Open a recording in Xplorefinder, '
                      + 'load or detect some events, and use "Bank…" to '
                      + 'file them here — with who added them and what '
                      + 'produced them.' }),
      ]));
      return;
    }

    host.appendChild(el('div', { class: 'bank-split' }, [
      bankTree(list),
      detail(),
    ]));
  }

  function toolbar() {
    const bar = el('div', { class: 'res-toolbar' });

    bar.appendChild(el('div', { class: 'search-wrap inline' }, [
      el('svg', { viewBox: '0 0 20 20', class: 'search-icon',
        html: '<circle cx="9" cy="9" r="6"/><path d="m14 14 4 4"/>' }),
      el('input', {
        type: 'search', value: query,
        placeholder: 'Search project, mouse, session, type, pipeline, who…',
        oninput: debounceInput((e) => { query = e.target.value; render(); }, 140),
      }),
    ]));

    const projects = Array.from(new Set(entries.map((e) => e.project || 'Unfiled')));
    if (projects.length > 1) {
      bar.appendChild(el('select', {
        title: 'Filter by project',
        onchange: (e) => { projectFilter = e.target.value; render(); },
      }, [el('option', { value: '', text: 'All projects' })].concat(
        projects.sort().map((p) => el('option', {
          value: p, text: p, selected: projectFilter === p ? 'selected' : null,
        })))));
    }

    const used = Array.from(new Set(entries.map((e) => e.type)));
    if (used.length > 1) {
      bar.appendChild(el('select', {
        title: 'Filter by event type',
        onchange: (e) => { typeFilter = e.target.value; render(); },
      }, [el('option', { value: '', text: 'All types' })].concat(
        used.map((t) => el('option', {
          value: t, text: typeName(t),
          selected: typeFilter === t ? 'selected' : null,
        })))));
    }

    bar.appendChild(el('div', { style: 'flex:1' }));
    bar.appendChild(el('span', { class: 'hint', text: meta.root || '' }));
    return bar;
  }

  /* ---------- left: project / mouse / session ---------- */
  function bankTree(list) {
    const keep = new Set(list.map((e) => e.id));
    const box = el('div', { class: 'bank-tree' });

    for (const g of tree) {
      const mice = g.mice
        .map((m) => Object.assign({}, m, {
          sessions: m.sessions
            .map((s) => Object.assign({}, s, {
              entries: s.entries.filter((e) => keep.has(e.id)),
            }))
            .filter((s) => s.entries.length),
        }))
        .filter((m) => m.sessions.length);
      if (!mice.length) continue;

      const n = mice.reduce((a, m) => a + m.sessions.reduce(
        (b, s) => b + s.entries.length, 0), 0);
      box.appendChild(el('div', { class: 'grp-head' }, [
        el('span', { text: g.project }),
        el('span', { class: 'count', text: n + ' entr(ies)' }),
      ]));

      for (const m of mice) {
        box.appendChild(el('div', { class: 'bank-mouse' }, [
          el('strong', { text: m.mouse }),
        ]));
        for (const s of m.sessions) {
          box.appendChild(el('div', { class: 'bank-sess' }, [
            el('span', { class: 'sid', text: s.session }),
            el('span', { class: 'slab', text: s.label || '', title: s.label || '' }),
          ]));
          for (const e of s.entries) {
            box.appendChild(entryRow(e));
          }
        }
      }
    }
    return box;
  }

  function entryRow(e) {
    const added = e.added || {};
    const src = e.source || {};
    return el('div', {
      class: 'bank-row' + (selected === e.id ? ' active' : ''),
      title: 'Banked by ' + added.by + ' on ' + (added.at || '').slice(0, 16),
      onclick: () => { selected = e.id; render(); },
    }, [
      el('span', { class: 'bank-type', text: typeName(e.type) }),
      el('span', { class: 'bank-name', text: e.name }),
      el('span', { class: 'bank-n', text: e.n + '' }),
      el('span', { class: 'bank-src', text: baseName(src.pipeline || ''),
                   title: src.pipeline || '' }),
    ]);
  }

  /* ---------- right: one entry in full ---------- */
  function detail() {
    const box = el('div', { class: 'bank-detail' });
    const e = entries.find((x) => x.id === selected);
    if (!e) {
      box.appendChild(el('div', { class: 'empty-state' }, [
        el('svg', { viewBox: '0 0 24 24',
          html: '<path d="M9 12h6m-6 4h6m-6-8h6M5 3h14a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/>' }),
        el('p', { text: 'Pick an entry to see where it came from, and to load '
                      + 'it onto a recording.' }),
      ]));
      return box;
    }

    const added = e.added || {};
    const src = e.source || {};

    box.appendChild(el('div', { class: 'detail-head' }, [
      el('div', {}, [
        el('h2', { text: e.name }),
        el('p', { class: 'detail-path',
                  text: (e.project || 'Unfiled') + '  ·  m' + e.mouse
                      + '  ·  s' + e.session
                      + (e.session_label ? '  ·  ' + e.session_label : '') }),
        el('div', { class: 'detail-tags' }, [
          el('span', { class: 'tag lang', text: typeName(e.type) }),
          el('span', { class: 'tag opt', text: e.n + ' events' }),
          e.note ? el('span', { class: 'tag opt', text: e.note }) : null,
        ]),
      ]),
      el('div', { class: 'head-actions' }, [
        el('button', { class: 'btn sm', text: 'Load onto a recording…',
                       onclick: () => importDialog(e) }),
        el('button', { class: 'btn ghost sm', text: 'Edit…',
                       onclick: () => editDialog(e) }),
      ]),
    ]));

    /* Provenance is the whole point of the bank, so it goes first and in
       full rather than behind a disclosure triangle. */
    box.appendChild(el('div', { class: 'section-label', text: 'Where this came from' }));
    const kv = el('dl', { class: 'kv' });
    const add = (k, v) => {
      if (v === null || v === undefined || v === '') return;
      kv.appendChild(el('dt', { text: k }));
      kv.appendChild(el('dd', { text: typeof v === 'object'
        ? JSON.stringify(v) : String(v) }));
    };
    add('Produced by', src.pipeline);
    add('Source file', src.file);
    add('Detector', src.detector);
    add('Run id', src.run_id);
    if (src.parameters && Object.keys(src.parameters).length) {
      add('Parameters', src.parameters);
    }
    add('Added by', added.by);
    add('Added at', (added.at || '').replace('T', ' '));
    add('On machine', added.machine);
    add('Times are', e.units);
    add('Session path', e.session_path);
    add('Entry id', e.id);
    box.appendChild(kv);

    if ((e.history || []).length) {
      box.appendChild(el('div', { class: 'section-label', text: 'Edited' }));
      box.appendChild(el('div', { class: 'source-box' }, [
        el('pre', { text: e.history.map((h) =>
          (h.at || '').replace('T', ' ') + '  ' + (h.by || '')
          + '  ' + (h.changed || []).join(', ')).join('\n') }),
      ]));
    }

    box.appendChild(el('div', { class: 'sec-head' }, [
      el('div', { class: 'section-label', text: 'Events' }),
      el('div', { class: 'spacer' }),
      el('button', { class: 'btn ghost sm', text: 'Export CSV',
        onclick: () => BARRY.download('/api/bank/export', { ids: [e.id] },
                                      'event-bank-' + e.id + '.csv') }),
      el('button', { class: 'btn ghost sm danger', text: 'Delete entry',
        onclick: () => removeEntry(e) }),
    ]));
    box.appendChild(el('div', { class: 'bank-events', id: 'bankEvents' },
                       [loader('Loading events')]));
    loadEvents(e.id);
    return box;
  }

  async function loadEvents(id) {
    let full;
    try { full = await api('/api/bank/' + encodeURIComponent(id)); }
    catch (err) { return; }
    const host = $('#bankEvents');
    if (!host || selected !== id) return;
    const evs = (full.entry || {}).events || [];
    host.innerHTML = '';
    const table = el('table', { class: 'preview-table' }, [
      el('thead', {}, [el('tr', {}, ['#', 'start', 'end', 'channel', 'amplitude']
        .map((h) => el('th', { text: h })))]),
      el('tbody', {}, evs.slice(0, 300).map((ev, i) => el('tr', {}, [
        el('td', { text: String(i + 1) }),
        el('td', { text: fmtTime(ev.start) }),
        el('td', { text: ev.end != null ? fmtTime(ev.end) : '' }),
        el('td', { text: ev.channel != null ? 'CSC' + ev.channel : '' }),
        el('td', { text: ev.amplitude != null
          ? Math.round(ev.amplitude) + ' uV' : '' }),
      ]))),
    ]);
    host.appendChild(el('div', { class: 'preview-wrap' }, [table]));
    if (evs.length > 300) {
      host.appendChild(el('div', { class: 'hint',
        text: 'Showing the first 300 of ' + evs.length + '. Export the CSV '
            + 'for all of them.' }));
    }
  }

  /* ======================================================================
     Loading an entry onto a recording

     Banked times are seconds from the start of that recording, so they only
     mean anything against the right one. This offers the sessions already
     open, flags whether each is actually the recording the entry was banked
     against, and can open the banked path directly if it is reachable.
     ====================================================================== */
  function importDialog(e) {
    const xf = BARRY.views.xplore.state;
    const open = xf.order.map((id) => xf.sessions[id]).filter(Boolean);

    const matchOf = (sess) => {
      const id = sess.identity || {};
      if (e.session_key && id.key === e.session_key) return 'exact';
      if (e.mouse != null && id.mouse === e.mouse
          && e.session != null && id.session === e.session) return 'same session';
      if (e.mouse != null && id.mouse === e.mouse) return 'same mouse only';
      return 'different recording';
    };
    const rank = { 'exact': 0, 'same session': 1, 'same mouse only': 2,
                   'different recording': 3 };
    open.sort((a, b) => rank[matchOf(a)] - rank[matchOf(b)]);

    let chosen = open.length ? open[0].id : null;

    const list = el('div', { class: 'bm-list tall' });
    const paint = () => {
      list.innerHTML = '';
      if (!open.length) {
        list.appendChild(el('div', { class: 'hint',
          text: 'No recordings are open. Open one in Xplorefinder first, or '
              + 'use the button below to open the one this was banked '
              + 'against.' }));
        return;
      }
      for (const sess of open) {
        const m = matchOf(sess);
        list.appendChild(el('label', {
          class: 'bm-row' + (chosen === sess.id ? ' on' : ''),
        }, [
          el('input', {
            type: 'radio', name: 'bankTarget',
            checked: chosen === sess.id ? 'checked' : null,
            onchange: () => { chosen = sess.id; paint(); },
          }),
          el('span', { class: 'mk-name',
                       text: sess.identity.label || sess.info.name }),
          el('span', { class: 'flagchip' + (m === 'exact' ? ' good'
                       : (m === 'different recording' ? ' bad' : '')), text: m }),
        ]));
      }
    };
    paint();

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Load "' + e.name + '" onto a recording' }),
        el('span', { class: 'sub', text: e.n + ' ' + typeName(e.type)
                                       + ' event(s)' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { class: 'confirm-msg',
          text: 'These times are seconds from the start of '
              + (e.session_label || 'the recording they were banked against')
              + ', so they only line up on that recording.' }),
        list,
      ]),
      el('div', { class: 'mf' }, [
        e.session_path ? el('button', {
          class: 'btn ghost sm',
          text: 'Open the banked recording',
          title: e.session_path,
          onclick: async () => {
            closeModal();
            setView('xplore');
            const sess = await BARRY.views.xplore.open(e.session_path);
            if (sess) applyTo(e, sess);
          },
        }) : null,
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        el('button', {
          class: 'btn', text: 'Load onto it',
          disabled: chosen ? null : 'disabled',
          onclick: async () => {
            const sess = xf.sessions[chosen];
            if (!sess) return;
            closeModal();
            setView('xplore');
            applyTo(e, sess);
          },
        }),
      ]),
    ]));
  }

  async function applyTo(entry, sess) {
    let full;
    try { full = await api('/api/bank/' + encodeURIComponent(entry.id)); }
    catch (err) { toast(err.message, 'err'); return; }
    const evs = ((full.entry || {}).events || []).map((ev) => Object.assign(
      {}, ev, { label: entry.name || typeName(entry.type) }));
    if (!evs.length) { toast('That entry has no events.', 'err'); return; }

    BARRY.views.xplore.addBankedEvents(sess, evs, {
      name: entry.name, type: entry.type, entry_id: entry.id,
      pipeline: (entry.source || {}).pipeline,
      added_by: (entry.added || {}).by,
    });
    toast('Loaded ' + evs.length + ' event(s) from the bank onto '
          + (sess.identity.label || sess.info.name), 'ok', 6000);
  }

  /* ---------- editing and removing ---------- */
  function editDialog(e) {
    const f = {};
    const field = (key, label, value, hint) => {
      const input = el('input', { type: 'text', value: value == null ? '' : String(value) });
      f[key] = input;
      return el('div', { class: 'field' }, [
        el('label', { text: label }), input,
        hint ? el('span', { class: 'hint', text: hint }) : null,
      ]);
    };
    const typeSel = el('select', {}, types.map((t) => el('option', {
      value: t.id, text: t.name + (t.note ? '  — ' + t.note : ''),
      selected: e.type === t.id ? 'selected' : null,
    })));

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Edit entry' }),
        el('span', { class: 'sub', text: 'provenance cannot be edited' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        field('name', 'Name', e.name),
        field('project', 'Project', e.project),
        field('mouse', 'Mouse', e.mouse),
        field('session', 'Session', e.session),
        el('div', { class: 'field' }, [el('label', { text: 'Type' }), typeSel]),
        field('note', 'Note', e.note),
        el('p', { class: 'hint',
          text: 'Who added it, when, and what produced it are fixed — '
              + 'that is the part worth trusting.' }),
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        el('button', {
          class: 'btn', text: 'Save',
          onclick: async () => {
            const num = (v) => (v === '' ? null : (isFinite(+v) ? +v : v));
            try {
              await apiPost('/api/bank/' + e.id + '/update', {
                name: f.name.value.trim() || e.name,
                project: f.project.value.trim() || 'Unfiled',
                mouse: num(f.mouse.value.trim()),
                session: num(f.session.value.trim()),
                type: typeSel.value,
                type_name: typeName(typeSel.value),
                note: f.note.value.trim(),
              });
              closeModal();
              await load();
              BARRY.refreshSync();
            } catch (err) { toast(err.message, 'err'); }
          },
        }),
      ]),
    ]));
  }

  async function removeEntry(e) {
    const ok = await BARRY.confirm(
      'Delete "' + e.name + '"?',
      'Removes ' + e.n + ' banked event(s) and the record of where they came '
      + 'from. The recording itself is untouched.',
      'Delete it', true);
    if (!ok) return;
    try {
      await apiPost('/api/bank/' + e.id + '/delete');
      selected = null;
      await load();
      BARRY.refreshSync();
      toast('Removed from the bank', 'ok');
    } catch (err) { toast(err.message, 'err'); }
  }

  function init() {
    $('#bankRefresh').addEventListener('click', load);
    $('#bankExport').addEventListener('click', () =>
      BARRY.download('/api/bank/export', {}, 'event-bank.csv'));
    $('#bankReveal').addEventListener('click', () => {
      if (meta.root) apiPost('/api/reveal', { path: meta.root }).catch(() => {});
    });
  }

  return {
    init,
    onShow: load,
    reload: load,
    types: () => types,
    /* Used by Xplorefinder's "Bank…" dialog so it offers the same list. */
    typeList: () => types,
  };
})();
