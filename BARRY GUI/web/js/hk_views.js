/* ==========================================================================
   hk_views.js -- Housekeeping's two ways of looking, and the mouse book.

   The tree is the right shape for "what do we have and where is it". It is
   the wrong shape for "which animals still need a genotype", because that
   question is about a column, and a tree has no columns. So there are two
   views over exactly the same records:

     Branches   nested, grouped by whatever you choose -- project by default,
                or any label anyone has put on a mouse. Grouping by genotype
                or cohort costs one dropdown, because the branch key is just
                an attribute lookup rather than a hard-coded level.

     Table      one row per recording (or per mouse), sortable, filterable,
                and copyable as TSV so it lands in Excel intact. This is the
                spreadsheet the lab was keeping by hand.

   And the labels themselves are free-form. A fixed set of columns is a guess
   about what the lab will want to record, and it is wrong within a month --
   someone needs "implant date", someone else needs "virus batch". So a new
   label is created by typing its name, it immediately becomes a grouping
   option, and nothing had to be declared anywhere first.
   ========================================================================== */
'use strict';

BARRY.hk = (function () {
  /* ==================================================================
     Reading the records
     ================================================================== */
  function flatten(data) {
    const out = [];
    for (const p of (data.tree || [])) {
      for (const m of p.mice) {
        for (const s of m.sessions) out.push(s);
      }
    }
    return out;
  }

  function attrsFor(data, s) {
    const byProject = (data.mice || {})[s.project] || {};
    return ((byProject[String(s.mouse)] || {}).attrs) || {};
  }

  /* Every label anyone has used, in a stable order: the suggested ones
     first so they are spelled the same way by everyone, then whatever the
     lab has invented since. */
  function attributes(data) {
    return (data.attributes || []).filter((a) => a.n || a.suggested);
  }

  function groupsOf(data, rows, groupBy) {
    /* One pass, producing [{key, label, mice:[{mouse, sessions}]}].

       Grouping by an attribute rather than by the project means a mouse with
       no value for it lands in "Not set" rather than vanishing -- which is
       the whole point, because "which ones have I not labelled yet" is the
       question you are usually asking. */
    const groups = new Map();
    for (const s of rows) {
      let key;
      if (groupBy === 'project') key = s.project || 'Unfiled';
      else if (groupBy === 'cohort') key = s.cohort || '—';
      else key = attrsFor(data, s)[groupBy] || null;
      const label = key === null ? 'Not set' : String(key);
      const gk = key === null ? '\u0000unset' : String(key);
      if (!groups.has(gk)) groups.set(gk, { key: gk, label, mice: new Map() });
      const g = groups.get(gk);
      /* A recording Jarvis could not get a mouse number out of still has
         to appear -- it is usually the one you were looking for. It gets a
         branch of its own that says so, rather than one labelled "mnull"
         that offers to label an animal that does not exist. */
      const mk = s.project + '/' + (s.mouse == null ? '?' : s.mouse);
      if (!g.mice.has(mk)) {
        g.mice.set(mk, {
          mouse: s.mouse == null ? null : s.mouse,
          name: s.mouse == null ? 'No mouse number' : 'm' + s.mouse,
          project: s.project, sessions: [],
        });
      }
      g.mice.get(mk).sessions.push(s);
    }
    const out = [...groups.values()].map((g) => ({
      key: g.key,
      label: g.label,
      // Unknown last: it is a loose end, not the first thing to read.
      mice: [...g.mice.values()].sort(
        (a, b) => (a.mouse == null) - (b.mouse == null)
                  || (a.mouse || 0) - (b.mouse || 0)),
    }));
    // "Not set" last: it is a to-do list, not a category.
    out.sort((a, b) => (a.key === '\u0000unset') - (b.key === '\u0000unset')
                    || a.label.localeCompare(b.label, undefined,
                                             { numeric: true }));
    return out;
  }

  /* ==================================================================
     The table
     ================================================================== */
  const SESSION_COLS = [
    { id: 'label', name: 'Recording', get: (s) => s.label || s.key || s.gid },
    { id: 'project', name: 'Project', get: (s) => s.project },
    { id: 'cohort', name: 'Cohort', get: (s) => s.cohort || '' },
    { id: 'mouse', name: 'Mouse', get: (s) => s.mouse, num: true },
    { id: 'session', name: 'Session', get: (s) => s.session, num: true },
    { id: 'date', name: 'Date', get: (s) => s.date || '' },
    { id: 'condition', name: 'Condition', get: (s) => s.condition || '' },
    { id: 'n_channels', name: 'Ch', get: (s) => s.n_channels, num: true },
    { id: 'duration', name: 'Length', get: (s) => s.duration_s, num: true,
      show: (v) => (v ? fmtDur(v) : '') },
    { id: 'bad', name: 'Bad channels', get: (s) => (s.bad_channels || []).join(' '),
      title: 'CSC numbers marked bad' },
    { id: 'layers', name: 'Layers', get: (s) => (s.has || {}).layers || 0,
      num: true },
    { id: 'banked', name: 'Banked', get: (s) => (s.has || {}).banked || 0,
      num: true },
    { id: 'figures', name: 'Figures', get: (s) => (s.has || {}).figures || 0,
      num: true },
    { id: 'paths', name: 'Paths', get: (s) => s.n_paths, num: true,
      title: 'How many places this recording has been seen' },
    { id: 'where', name: 'Where it is',
      get: (s) => ((s.here || [])[0] || (s.paths || [])[0] || ''),
      title: 'The full path -- reachable from here if there is one' },
    { id: 'machines', name: 'Seen by',
      get: (s) => Object.keys(s.seen || {}).join(', '),
      title: 'Which machines have laid eyes on it' },
    { id: 'gid', name: 'Permanent id', get: (s) => s.gid, mono: true },
  ];

  function mouseCols(data) {
    const cols = [
      { id: 'mouse', name: 'Mouse', get: (r) => r.mouse, num: true,
        show: (v) => (v == null ? '—' : String(v)) },
      { id: 'project', name: 'Project', get: (r) => r.project },
      { id: 'n', name: 'Recordings', get: (r) => r.sessions.length, num: true },
    ];
    for (const a of attributes(data)) {
      cols.push({ id: 'a:' + a.id, name: a.name, attr: a.id,
                  get: (r) => r.attrs[a.id] || '' });
    }
    cols.push({ id: 'dates', name: 'First seen',
                get: (r) => r.sessions.map((s) => s.date)
                  .filter(Boolean).sort()[0] || '' });
    return cols;
  }

  function miceRows(data, rows) {
    const by = new Map();
    for (const s of rows) {
      const k = s.project + '/' + s.mouse;
      if (!by.has(k)) {
        by.set(k, { mouse: s.mouse, project: s.project,
                    name: s.mouse == null ? 'No mouse number' : 'm' + s.mouse,
                    attrs: attrsFor(data, s), sessions: [] });
      }
      by.get(k).sessions.push(s);
    }
    return [...by.values()];
  }

  function sortRows(rows, cols, sort) {
    if (!sort || !sort.col) return rows;
    const col = cols.find((c) => c.id === sort.col);
    if (!col) return rows;
    const dir = sort.dir === 'desc' ? -1 : 1;
    return rows.slice().sort((a, b) => {
      const x = col.get(a);
      const y = col.get(b);
      if (col.num) return dir * ((Number(x) || 0) - (Number(y) || 0));
      return dir * String(x == null ? '' : x)
        .localeCompare(String(y == null ? '' : y), undefined,
                       { numeric: true });
    });
  }

  function table(opts) {
    const { cols, rows, sort, onsort, onclick, isSel, edit, wrap } = opts;
    const head = el('tr', {}, cols.map((c) => el('th', {
      class: (c.num ? 'num' : '') + (sort && sort.col === c.id ? ' sorted' : ''),
      title: c.title || 'Sort by ' + c.name,
      onclick: () => onsort(c.id),
    }, [
      el('span', { text: c.name }),
      sort && sort.col === c.id
        ? el('span', { class: 'hk-arrow',
                       text: sort.dir === 'desc' ? '▾' : '▴' })
        : null,
    ].filter(Boolean))));

    const body = el('tbody', {}, rows.map((r) => el('tr', {
      class: (isSel && isSel(r) ? 'sel' : '')
           + (r.reachable === false ? ' away' : ''),
      onclick: onclick ? () => onclick(r) : null,
    }, cols.map((c) => {
      const raw = c.get(r);
      const txt = c.show ? c.show(raw) : (raw == null ? '' : String(raw));
      return el('td', {
        class: (c.num ? 'num' : '') + (c.mono ? ' mono' : '')
             + (c.attr ? ' editable' : ''),
        title: c.attr ? 'Click to set ' + c.name : txt,
        onclick: c.attr && edit
          ? (e) => { e.stopPropagation(); edit(r, c.attr); }
          : null,
      }, [txt === '' && c.attr
          ? el('span', { class: 'hk-unset', text: '—' })
          : el('span', { text: txt })]);
    }))));

    return el('div', { class: 'hk-tablewrap' },
              [el('table', { class: 'hk-table' + (wrap ? ' wrap' : '') },
                  [el('thead', {}, [head]), body])]);
  }

  function toTSV(cols, rows) {
    const lines = [cols.map((c) => c.name).join('\t')];
    for (const r of rows) {
      lines.push(cols.map((c) => {
        const v = c.get(r);
        const t = c.show ? c.show(v) : (v == null ? '' : String(v));
        return t.replace(/[\t\r\n]+/g, ' ');
      }).join('\t'));
    }
    return lines.join('\n');
  }

  return {
    flatten, attrsFor, attributes, groupsOf,
    SESSION_COLS, mouseCols, miceRows, sortRows, table, toTSV,
  };
}());
