/* ==========================================================================
   housekeeping.js -- Every recording Jarvis has ever met, in one tree.

   The Sessions view answers "what is on this drive". This answers the other
   question: what does the lab have, where has each recording been seen, and
   what work is attached to it.

   The distinction that matters is the global id. A recording's derived key
   (mouse + session + header time) is good at recognising the same recording
   across machines and is exactly the wrong thing to hang years of work off,
   because it is derived -- re-read a header, fix a folder name, and it
   changes. The gid is minted once and never recomputed, so bad channels,
   layer labels and curated events stay attached to the recording rather than
   to a string that happened to describe it.

   Everything here is manual override territory: guessing a project from a
   folder name is right most of the time and wrong in exactly the cases
   somebody needs to fix by hand.
   ========================================================================== */
'use strict';

BARRY.views.housekeeping = (function () {
  let data = null;
  let open = {};             // which branches are expanded
  let selected = null;       // gid of the row being inspected
  let query = '';
  let onlyHere = false;      // hide recordings this machine cannot reach

  /* Two filters that are not yes-or-no, and are not groupings either.

     Grouping by project already existed and is a different thing: it
     decides what the branches MEAN, and every recording is still in the
     tree somewhere. Filtering decides which are in it at all, and "PTEN
     and KCNT1 but not the urethane work" is an ordinary thing to want when
     the urethane project shares mouse numbers with KCNT1.

     Channels is a comparison rather than a value, because the question
     people actually have is "which of these are the dual implants", and
     that is `more than 64`. Asking for exactly 128 gets the ordinary ones
     and silently misses the six whose CSCn_0001.ncs continuation files put
     the count at 190 or 192 -- which are precisely the ones worth looking
     at. */
  const projOnly = new Set();
  let chanFilter = { op: '', n: 64 };
  const CHAN_OPS = [['gt', 'more than'], ['lt', 'fewer than'],
                    ['eq', 'exactly']];

  /* Two views over the same records, and one control that changes what the
     branches mean. Grouping is by project until you say otherwise; every
     label anyone has put on a mouse is also a grouping, which is what makes
     "show me the DKO animals" a dropdown rather than a feature request. */
  /* Which catalogue this is drawing.

     There are two places that want the same tree: "Everything Jarvis
     knows", and "Everything VACC knows" -- which is the same catalogue
     narrowed to the recordings the cluster can actually read. Narrowed, not
     a different list: the whole point of the VACC view is to find a
     recording the way you find any other, by project and mouse, rather than
     by walking the cluster's directories and recognising a folder name.

     One module rather than two, because a second copy of a project/mouse/
     session tree is a second copy to keep in step. The expansion state and
     the selection are deliberately shared: it is one catalogue, and a
     recording you opened in one view is the one you were looking at.

     Only one scope is ever on screen -- the mode switch hides the other --
     so the ids below cannot collide. */
  const SCOPES = {
    jarvis: { host: '#hkBody', detail: 'hkDetail' },
    vacc: { host: '#vaccCatalogue', detail: 'vaccDetail' },
  };
  let scope = 'jarvis';

  let view = 'branches';     // 'branches' | 'table'
  let groupBy = 'project';
  let tableOf = 'sessions';  // 'sessions' | 'mice'
  let sort = { col: null, dir: 'asc' };
  let mouseSel = null;       // {project, mouse} being labelled
  let wrapCells = false;     // show long cell values in full, not clipped

  /* Which recordings a scan has actually found since the app started.

     A recording Jarvis remembers and a recording Jarvis has just laid eyes on
     are different facts, and the list should not pretend otherwise. So the
     view opens with everything faint -- "this is what I remember" -- and a
     scan brings back whatever it finds. What stays faint after a scan of the
     drive you expected it on is the interesting part.

     Deliberately per-run rather than persisted: the whole point is that it
     reflects a check made now, not one made last Tuesday. */
  const confirmed = new Set();
  let scanned = false;       // has any scan run in this app session
  let onlyFound = false;

  /* Called by the Sessions view when a scan finishes.

     Reloads rather than just repainting: a scan registers everything it
     walked past, so the tree now has recordings in it that were not there a
     moment ago -- and re-rendering stale data would brighten nothing and
     show none of them. */
  async function confirm(gids, root) {
    let n = 0;
    for (const g of (gids || [])) {
      if (g && !confirmed.has(g)) { confirmed.add(g); n += 1; }
    }
    scanned = true;
    BARRY.activity.log('registry.confirmed',
                       { root, n, total: confirmed.size });
    await load();
    return n;
  }

  async function load(backfill) {
    try {
      data = await api('/api/registry' + (backfill ? '?backfill=1' : ''));
    } catch (e) {
      toast('Could not read the registry: ' + e.message, 'err', 8000);
      data = { tree: [], projects: [], total: 0 };
    }
    /* A branch Jarvis has not seen before starts open.

       Only doing this on the first load meant a scan that discovered six new
       mice added six collapsed branches -- so the recordings it had just
       found were invisible, and the count in the toolbar disagreed with the
       list underneath it. Anything already collapsed by hand stays
       collapsed; only genuinely new branches default to open. */
    openNewBranches();
    render();
  }

  /* A branch Jarvis has not seen before starts open, whichever grouping is
     showing. Anything collapsed by hand stays collapsed. */
  function openNewBranches() {
    if (!data) return;
    for (const g of BARRY.hk.groupsOf(data, BARRY.hk.flatten(data), groupBy)) {
      const gk = 'g:' + groupBy + ':' + g.key;
      if (!(gk in open)) open[gk] = true;
      for (const m of g.mice) {
        const mk = gk + '/' + m.mouse;
        if (!(mk in open)) open[mk] = true;
      }
    }
  }

  async function onShow() {
    // "Everything Jarvis knows" is this view's own scope. Reset it, or
    // coming back from the cluster view shows the catalogue still narrowed
    // to what VACC can read, in the panel that promises everything.
    scope = 'jarvis';
    render();
    // Backfill on the first look, so records written before the registry
    // existed arrive with a gid rather than appearing over weeks.
    await load(!data);
  }

  /* ==================================================================
     The tree
     ================================================================== */
  /* Can the cluster read this one.

     Two states draw and two do not, and the two that do not are different
     from each other: `local-only` is an established no, `unknown` is that
     nobody has asked. Both are excluded here, because this view's whole
     claim is "VACC can reach these" and a recording nobody has established
     an answer for is not one of them. That is the same rule the VACC chip
     on a session card follows -- absent is not negative, and it is not
     affirmative either. */
  function onVacc(s) {
    if (!BARRY.vacc || !s.gid) return false;
    const got = BARRY.vacc.of(s);
    const st = got && got.state;
    return st === 'native' || st === 'staged';
  }

  function chanOk(s) {
    if (!chanFilter.op) return true;
    const n = Number(s.n_channels);
    /* A recording nobody has read a header for has no channel count, and a
       missing number is not a small number -- it is in NEITHER side of the
       comparison. Reading absence as zero is the mistake `canOpen` in
       sessions.js carries a comment about, and here it would quietly file
       164 unread recordings under "fewer than 64". */
    if (!Number.isFinite(n) || n <= 0) return false;
    const want = Number(chanFilter.n) || 0;
    if (chanFilter.op === 'gt') return n > want;
    if (chanFilter.op === 'lt') return n < want;
    return n === want;
  }

  function matches(s) {
    if (scope === 'vacc' && !onVacc(s)) return false;
    if (projOnly.size && !projOnly.has(s.project || 'Unfiled')) return false;
    if (!chanOk(s)) return false;
    if (onlyFound && !confirmed.has(s.gid)) return false;
    if (onlyHere && !s.reachable) return false;
    if (!query) return true;
    const hay = [s.label, s.gid, s.key, s.project, 'm' + s.mouse,
                 's' + s.session, s.date, (s.paths || []).join(' ')]
      .join(' ').toLowerCase();
    return query.toLowerCase().split(/\s+/).every((t) => hay.includes(t));
  }

  function render() {
    const host = $(SCOPES[scope].host);
    if (!host) return;
    host.innerHTML = '';

    if (!data) {
      host.appendChild(el('div', { class: 'tk-loading' }, [
        stepLoader('Housekeeping', ['reading what is known about '
                                    + 'every mouse'])]));
      return;
    }

    host.appendChild(toolbar());
    if (!scanned) {
      host.appendChild(el('p', { class: 'hint hk-remembered-note',
        text: 'Everything below is what Jarvis remembers. Scan a drive and '
            + 'whatever it finds will brighten — so what stays faint is '
            + 'what is not where you expected it.' }));
    }

    const rows = BARRY.hk.flatten(data).filter(matches);
    const left = view === 'table' ? tableView(rows) : branchView(rows);

    if (!rows.length) {
      left.appendChild(el('div', { class: 'hint hk-empty',
        text: data.total
          ? 'Nothing matches that. ' + data.total + ' recording'
            + (data.total === 1 ? ' is' : 's are') + ' registered.'
          : 'No recordings registered yet. Open one in Xplorefinder and it '
            + 'will be given a permanent id and appear here.' }));
    }

    host.appendChild(el('div', {
      class: 'hk-layout' + (view === 'table' ? ' wide' : ''),
    }, [
      left,
      el('div', { class: 'hk-detail', id: SCOPES[scope].detail }),
    ]));
    renderDetail();
  }

  /* ==================================================================
     Branches -- grouped by whatever you picked
     ================================================================== */
  function branchView(rows) {
    const tree = el('div', { class: 'hk-tree' });
    for (const g of BARRY.hk.groupsOf(data, rows, groupBy)) {
      const n = g.mice.reduce((a, m) => a + m.sessions.length, 0);
      const gk = 'g:' + groupBy + ':' + g.key;
      tree.appendChild(branch(gk, 'project', g.label,
        g.mice.length + ' mice · ' + n + ' session'
        + (n === 1 ? '' : 's')));
      if (!open[gk]) continue;

      for (const m of g.mice) {
        const mk = gk + '/' + m.mouse;
        tree.appendChild(mouseBranch(mk, m));
        if (!open[mk]) continue;
        for (const sess of m.sessions) tree.appendChild(sessionRow(sess));
      }
    }
    return tree;
  }

  /* A mouse branch carries its labels, so the tree answers "what is this
     animal" without anyone having to open a panel -- and clicking one is how
     you change it. */
  function mouseBranch(key, m) {
    const isOpen = !!open[key];
    // No mouse number means there is no animal to hang labels off. Say so,
    // rather than offering a button that quietly does nothing.
    const known = m.mouse != null;
    const attrs = known ? BARRY.hk.attrsFor(data, m.sessions[0]) : {};
    const chips = BARRY.hk.attributes(data)
      .filter((a) => attrs[a.id])
      .map((a) => el('span', { class: 'hk-label', title: a.name,
                               text: attrs[a.id] }));
    const isSel = mouseSel && mouseSel.project === m.project
                  && String(mouseSel.mouse) === String(m.mouse);
    return el('div', {
      class: 'hk-branch hk-mouse' + (isSel ? ' sel' : ''),
      style: 'padding-left:18px',
      onclick: () => { open[key] = !isOpen; render(); },
    }, [
      el('span', { class: 'hk-caret' + (isOpen ? ' open' : ''), text: '▸' }),
      el('strong', { class: known ? '' : 'hk-unset',
                     text: m.name || ('m' + m.mouse) }),
      el('span', { class: 'hk-sub',
                   text: m.sessions.length + ' session'
                       + (m.sessions.length === 1 ? '' : 's') }),
      el('div', { class: 'hk-labels' }, chips),
      known
        ? el('button', {
            class: 'hk-tag',
            title: chips.length ? 'Change what this mouse is labelled'
                                : 'Label this mouse',
            text: chips.length ? 'edit' : '+ label',
            onclick: (e) => {
              e.stopPropagation();
              mouseSel = { project: m.project, mouse: m.mouse };
              selected = null;
              render();
            },
          })
        : el('span', {
            class: 'hk-sub',
            title: 'Jarvis could not read a mouse number out of the folder '
                 + 'name, so there is no animal to hang labels off. Rename '
                 + 'the folder, or set this recording\u2019s label by hand.',
            text: 'nothing to label',
          }),
    ]);
  }

  /* ==================================================================
     Table -- the same records with columns, because some questions are
     about a column and a tree has none
     ================================================================== */
  function tableView(rows) {
    const wrap = el('div', { class: 'hk-tablecol' });
    if (tableOf === 'mice') {
      const cols = BARRY.hk.mouseCols(data);
      const mrows = BARRY.hk.sortRows(
        BARRY.hk.miceRows(data, rows), cols, sort);
      wrap.appendChild(BARRY.hk.table({
        cols, rows: mrows, sort, onsort: resort, wrap: wrapCells,
        isSel: (r) => mouseSel && mouseSel.project === r.project
                      && String(mouseSel.mouse) === String(r.mouse),
        onclick: (r) => {
          if (r.mouse == null) {
            toast('That row is the recordings with no mouse number, so '
                  + 'there is no animal to label.', 'err', 6000);
            return;
          }
          mouseSel = { project: r.project, mouse: r.mouse };
          selected = null;
          render();
        },
        // Clicking a label cell edits that one label in place, which is how
        // you fill a column down a spreadsheet.
        edit: (r, attr) => quickSet(r, attr),
      }));
      wrap.appendChild(el('div', { class: 'hint',
        text: mrows.length + ' mice. Click a label to set it, or a row to '
            + 'edit all of them.' }));
    } else {
      const cols = BARRY.hk.SESSION_COLS;
      const srows = BARRY.hk.sortRows(rows, cols, sort);
      wrap.appendChild(BARRY.hk.table({
        cols, rows: srows, sort, onsort: resort, wrap: wrapCells,
        isSel: (r) => selected === r.gid,
        onclick: (r) => { selected = r.gid; mouseSel = null; render(); },
      }));
      wrap.appendChild(el('div', { class: 'hint',
        text: srows.length + ' recording' + (srows.length === 1 ? '' : 's')
            + '. Click a column heading to sort, a row to inspect it.' }));
    }
    return wrap;
  }

  /* Which projects are in the list, plus the lab's own whether or not any
     are on screen -- so the choice does not appear and disappear as the
     list is narrowed by something else, which makes a control look broken
     at exactly the moment somebody is using it. */
  function projectsAvailable() {
    const seen = new Set(BARRY.hk.flatten(data).map((s) => s.project
                                                       || 'Unfiled'));
    for (const p of (data.known_projects || [])) seen.add(p);
    for (const p of projOnly) seen.add(p);
    return Array.from(seen).sort((a, b) => {
      if (a === 'Unfiled') return 1;
      if (b === 'Unfiled') return -1;
      return a.localeCompare(b);
    });
  }

  /* A set, not a radio. Grouping already answers "one project at a time";
     this answers "these two and not that one", which grouping cannot. */
  function projectPicker() {
    const names = projectsAvailable();
    const on = projOnly.size;
    const btn = el('button', {
      class: 'btn ghost sm' + (on ? ' on' : ''),
      /* A stable handle. The LABEL changes to say what is on -- "PTEN"
         rather than "Project" -- which is the right thing for a person and
         useless for anything looking the control up by its name. */
      'data-filter': 'project',
      title: 'Show only certain projects. Nothing ticked means all of them.',
      text: on
        ? (on === 1 ? Array.from(projOnly)[0] : on + ' projects')
        : 'Project',
      onclick: (e) => openPopover(e.currentTarget, () => {
        const box = el('div', { class: 'ctl-pop-body' });
        const g = el('div', { class: 'ctl-pop-group' }, [
          el('div', { class: 'ctl-pop-title', text: 'Project' }),
        ]);
        const all = BARRY.hk.flatten(data);
        for (const p of names) {
          const n = all.filter((s) => (s.project || 'Unfiled') === p).length;
          g.appendChild(el('label', {
            class: 'ctl-pop-opt' + (projOnly.has(p) ? ' on' : ''),
            'data-project': p,
          }, [
            el('input', { type: 'checkbox',
              checked: projOnly.has(p) ? 'checked' : null,
              onchange: () => {
                if (projOnly.has(p)) projOnly.delete(p);
                else projOnly.add(p);
                render();
              } }),
            el('span', { text: p }),
            el('span', { class: 'ctl-pop-n', text: String(n) }),
          ]));
        }
        box.appendChild(g);
        if (projOnly.size) {
          box.appendChild(el('button', {
            class: 'linkish fb-clear', text: 'All projects',
            onclick: () => { projOnly.clear(); render(); },
          }));
        }
        return box;
      }),
    });
    return btn;
  }

  function channelPicker() {
    const word = (CHAN_OPS.find((o) => o[0] === chanFilter.op) || [])[1];
    return el('button', {
      class: 'btn ghost sm' + (chanFilter.op ? ' on' : ''),
      'data-filter': 'channels',
      title: 'Narrow by how many channels a recording has. "More than 64" '
           + 'is the dual-implant recordings.',
      text: word ? word + ' ' + chanFilter.n + ' ch' : 'Channels',
      onclick: (e) => openPopover(e.currentTarget, () => {
        const box = el('div', { class: 'ctl-pop-body' });
        const g = el('div', { class: 'ctl-pop-group' }, [
          el('div', { class: 'ctl-pop-title', text: 'Channels' }),
        ]);
        const row = el('div', { class: 'ctl-pop-row' });
        const sel = el('select', {
          onchange: (e2) => { chanFilter.op = e2.target.value; render(); },
        }, [el('option', { value: '', text: 'any number of' })].concat(
          CHAN_OPS.map(([id, w]) => el('option', {
            value: id, text: w,
            selected: chanFilter.op === id ? 'selected' : null,
          }))));
        row.appendChild(sel);
        row.appendChild(el('input', {
          type: 'number', min: '1', max: '1024', step: '1',
          class: 'ctl-pop-num', value: String(chanFilter.n),
          disabled: chanFilter.op ? null : 'disabled',
          onchange: (e2) => {
            chanFilter.n = Math.max(1, parseInt(e2.target.value, 10) || 1);
            render();
          },
        }));
        row.appendChild(el('span', { class: 'ctl-pop-unit', text: 'channels' }));
        g.appendChild(row);
        g.appendChild(el('p', { class: 'hint',
          text: 'A recording nobody has read a header for has no channel '
              + 'count, and a missing number is not a small one — '
              + 'those are in neither side of the comparison.' }));
        box.appendChild(g);
        return box;
      }),
    });
  }

  function resort(col) {
    sort = (sort.col === col)
      ? { col, dir: sort.dir === 'asc' ? 'desc' : 'asc' }
      : { col, dir: 'asc' };
    render();
  }

  function copyTable() {
    const rows = BARRY.hk.flatten(data).filter(matches);
    const cols = tableOf === 'mice'
      ? BARRY.hk.mouseCols(data) : BARRY.hk.SESSION_COLS;
    const body = tableOf === 'mice' ? BARRY.hk.miceRows(data, rows) : rows;
    const text = BARRY.hk.toTSV(cols, BARRY.hk.sortRows(body, cols, sort));
    navigator.clipboard.writeText(text).then(
      () => toast('Copied ' + body.length + ' row'
                  + (body.length === 1 ? '' : 's')
                  + ' — paste straight into a spreadsheet.', 'ok'),
      () => toast('The browser would not let me use the clipboard.', 'err'));
  }

  function toolbar() {
    const bar = el('div', { class: 'hk-bar' });

    bar.appendChild(el('div', { class: 'seg' }, [
      el('button', {
        class: view === 'branches' ? 'active' : '', text: 'Branches',
        title: 'Nested by whatever you group on',
        onclick: () => { view = 'branches'; render(); },
      }),
      el('button', {
        class: view === 'table' ? 'active' : '', text: 'Table',
        title: 'The same records with columns, sortable and copyable',
        onclick: () => { view = 'table'; render(); },
      }),
    ]));

    bar.appendChild(el('label', {
      class: 'toggle' + (wrapCells ? ' on' : ''),
      title: 'Show long values -- paths especially -- in full instead of '
           + 'cutting them off',
    }, [
      el('input', {
        type: 'checkbox', checked: wrapCells ? 'checked' : null,
        onchange: (e) => { wrapCells = e.target.checked; render(); },
      }),
      el('span', { text: 'Full values' }),
    ]));

    if (view === 'branches') {
      const opts = [
        el('option', { value: 'project', text: 'Project' }),
        el('option', { value: 'cohort', text: 'Cohort' }),
      ];
      for (const a of BARRY.hk.attributes(data)) {
        opts.push(el('option', {
          value: a.id,
          text: a.name + (a.n ? '  (' + a.n + ')' : ''),
        }));
      }
      const sel = el('select', {
        class: 'hk-groupby', title: 'What the top-level branches mean',
        onchange: (e) => { groupBy = e.target.value; openNewBranches(); render(); },
      }, opts);
      sel.value = groupBy;
      bar.appendChild(el('label', { class: 'hk-inline' }, [
        el('span', { text: 'Group by' }), sel,
      ]));
    } else {
      bar.appendChild(el('div', { class: 'seg' }, [
        el('button', {
          class: tableOf === 'sessions' ? 'active' : '', text: 'Recordings',
          onclick: () => { tableOf = 'sessions'; sort = { col: null, dir: 'asc' }; render(); },
        }),
        el('button', {
          class: tableOf === 'mice' ? 'active' : '', text: 'Mice',
          onclick: () => { tableOf = 'mice'; sort = { col: null, dir: 'asc' }; render(); },
        }),
      ]));
      bar.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Copy',
        title: 'Copy what is showing as tab-separated text, ready to paste '
             + 'into a spreadsheet',
        onclick: copyTable,
      }));
    }

    bar.appendChild(projectPicker());
    bar.appendChild(channelPicker());

    bar.appendChild(el('input', {
      type: 'search', class: 'hk-search',
      placeholder: 'Filter by mouse, project, date, id or path…',
      value: query,
      oninput: debounceInput(
        (e) => { query = e.target.value; keepFocus(render); }, 140),
    }));
    bar.appendChild(el('label', { class: 'toggle' + (onlyHere ? ' on' : '') }, [
      el('input', {
        type: 'checkbox', checked: onlyHere ? 'checked' : null,
        onchange: (e) => { onlyHere = e.target.checked; render(); },
      }),
      el('span', { text: 'Only what this machine can reach' }),
    ]));
    bar.appendChild(el('label', {
      class: 'toggle' + (onlyFound ? ' on' : ''),
      title: 'Only the ones a scan has found in this session',
    }, [
      el('input', {
        type: 'checkbox', checked: onlyFound ? 'checked' : null,
        onchange: (e) => { onlyFound = e.target.checked; render(); },
      }),
      el('span', { text: 'Only found this session' }),
    ]));
    bar.appendChild(el('div', { class: 'spacer' }));
    /* The count has to describe what this view is showing.

       In the cluster scope it said "587 registered" beside a tree of 109,
       which is the whole catalogue's number in a panel that promises only
       what VACC can read -- and reads as "this is showing everything",
       which was the complaint. */
    if (scope === 'vacc') {
      const all = BARRY.hk.flatten(data);
      const reach = all.filter(onVacc).length;
      bar.appendChild(el('span', {
        class: 'stat-chip',
        title: 'Of ' + all.length + ' recordings Jarvis knows about, this '
             + 'many are on a share the cluster mounts or already copied '
             + 'to its scratch. The rest are not hidden by a filter you '
             + 'can turn off — they are not there.',
        text: reach + ' on VACC, of ' + all.length,
      }));
    } else {
      bar.appendChild(el('span', { class: 'stat-chip',
        text: (data.total || 0) + ' registered' }));
    }
    bar.appendChild(el('span', {
      class: 'stat-chip' + (confirmed.size ? ' good' : ''),
      title: scanned
        ? 'Confirmed by a scan since this window opened'
        : 'Nothing has been scanned yet this session, so everything below is '
          + 'what Jarvis remembers rather than what it has just seen',
      text: confirmed.size + ' found this session',
    }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Scan a drive…',
      title: 'Walk a folder and confirm what is actually there. Everything it '
           + 'finds is registered, whether or not anyone opens it.',
      onclick: () => {
        if (BARRY.views.sessions && BARRY.views.sessions.setMode) {
          BARRY.views.sessions.setMode('scan');
        }
        const i = $('#rootPath');
        if (i) i.focus();
      },
    }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Expand all',
      onclick: () => {
        for (const g of BARRY.hk.groupsOf(data, BARRY.hk.flatten(data),
                                          groupBy)) {
          const gk = 'g:' + groupBy + ':' + g.key;
          open[gk] = true;
          for (const m of g.mice) open[gk + '/' + m.mouse] = true;
        }
        render();
      },
    }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Collapse',
      onclick: () => { open = {}; render(); },
    }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Check the recordings\u2026',
      title: 'Re-read every reachable folder and say which ones are not '
           + 'really recordings',
      onclick: runAudit,
    }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Refresh', onclick: () => load(true),
    }));
    return bar;
  }

  /* Re-check what is already registered against what is on disk.

     The assessment arrived after most of these records did, so the folders a
     scan would refuse today are already in the tree. Seven of them are 64
     files of header and no data. This finds them and offers to retire them
     -- retire, not delete: the record stays so anything pointing at its id
     still resolves, and nothing on the recording drive is touched. */
  async function runAudit() {
    // loader() builds the element; showing it is the caller's job.
    const wait = loader('Re-reading every reachable folder…',
                        'One header per channel, so this takes a moment.');
    const waitHost = $('#hkBody');
    if (waitHost) waitHost.appendChild(wait);
    let res;
    try {
      res = await api('/api/registry/audit');
    } catch (e) {
      toast(e.message, 'err', 8000);
      return;
    } finally {
      if (wait && wait.remove) wait.remove();
    }
    const rows = res.rows || [];
    if (!rows.length) {
      toast('Checked ' + res.checked + ' reachable recording'
            + (res.checked === 1 ? '' : 's') + ' \u2014 every one of them has '
            + 'data in it.'
            + (res.unreachable ? '  (' + res.unreachable + ' are on drives '
               + 'this machine cannot reach, so they were not checked.)' : ''),
            'ok', 9000);
      return;
    }
    const picked = new Set(rows.filter(
      (r) => r.quality.verdict === 'empty').map((r) => r.gid));
    const list = el('div', { class: 'held-list' }, rows.map((r) => el('div', {
      class: 'held-row',
    }, [
      el('label', { class: 'toggle' }, [
        el('input', {
          type: 'checkbox',
          checked: picked.has(r.gid) ? 'checked' : null,
          onchange: (e) => {
            if (e.target.checked) picked.add(r.gid); else picked.delete(r.gid);
          },
        }),
        el('span', { text: '' }),
      ]),
      el('div', { style: 'min-width:0' }, [
        el('strong', { text: r.label || r.gid }),
        el('code', { class: 'held-path', text: r.path }),
        ...(r.quality.reasons || []).map(
          (x) => el('p', { class: 'hint', text: x })),
        attachedNote(r.attached),
      ].filter(Boolean)),
      el('span', { class: 'flagchip bad', text: r.quality.verdict }),
    ])));

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: rows.length + ' recording(s) worth a look' }),
        el('span', { class: 'sub',
          text: res.checked + ' checked'
              + (res.unreachable ? ', ' + res.unreachable + ' unreachable'
                                 : '') }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/>'
              + '</svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { class: 'hint',
          text: 'Retiring one keeps the record and its permanent id \u2014 so '
              + 'anything already pointing at it still resolves \u2014 and '
              + 'takes it out of the tree. Nothing on the recording drive is '
              + 'touched.' }),
        list,
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Leave them',
                       onclick: closeModal }),
        el('button', {
          class: 'btn', text: 'Retire the ticked ones',
          onclick: async () => {
            const gids = [...picked];
            if (!gids.length) { toast('Nothing ticked.', 'err'); return; }
            try {
              const out = await apiPost('/api/registry/retire',
                { gids, reason: 'no data in the folder' });
              toast('Retired ' + (out.retired || []).length + '.', 'ok');
              closeModal();
              await load(true);
            } catch (e) { toast(e.message, 'err', 8000); }
          },
        }),
      ]),
    ]));
  }

  /* A recording with curated events or figures hanging off it is not
     something to retire on a size check alone -- say so. */
  function attachedNote(attached) {
    const live = Object.entries(attached || {}).filter(([, v]) => v);
    if (!live.length) return null;
    return el('p', { class: 'hint bad',
      text: 'Careful: this one has ' + live.map(
        ([k, v]) => v + ' ' + k.replace(/_/g, ' ')).join(', ')
        + ' attached.' });
  }

  function branch(key, kind, name, sub, depth) {
    const isOpen = !!open[key];
    return el('div', {
      class: 'hk-branch hk-' + kind, style: depth ? 'padding-left:18px' : null,
      onclick: () => { open[key] = !isOpen; render(); },
    }, [
      el('span', { class: 'hk-caret' + (isOpen ? ' open' : ''), text: '▸' }),
      el('strong', { text: name }),
      el('span', { class: 'hk-sub', text: sub }),
    ]);
  }

  function sessionRow(s) {
    const has = s.has || {};
    const chips = [];
    const chip = (n, label, cls) => {
      if (!n) return;
      chips.push(el('span', { class: 'hk-chip ' + (cls || ''),
                              text: n + ' ' + label }));
    };
    chip(has.bad_channels, 'bad', 'warn');
    chip(has.figures, 'fig');
    chip(has.decks, 'deck');
    chip(has.banked, 'banked');
    chip(has.spike_sets, 'spike');
    chip(has.layers, 'layer');
    chip(has.ds, 'DS');

    return el('div', {
      class: 'hk-row' + (selected === s.gid ? ' sel' : '')
           + (s.reachable ? '' : ' away')
           // Faint until a scan has actually found it in this run.
           + (confirmed.has(s.gid) ? ' found' : ' remembered'),
      onclick: () => { selected = s.gid; render(); },
    }, [
      el('span', {
        class: 'hk-dot' + (confirmed.has(s.gid) ? ' seen'
                           : (s.reachable ? ' on' : '')),
        title: confirmed.has(s.gid)
          ? 'Found by a scan just now'
          : (s.reachable
             ? 'A path is reachable, but no scan has confirmed it this session'
             : 'Registered, but not mounted here'),
      }),
      el('span', { class: 'hk-name', text: s.label || s.key || s.gid }),
      el('code', { class: 'hk-gid', text: s.gid, title: 'Permanent id' }),
      el('span', { class: 'hk-paths',
                   text: s.n_paths + ' path' + (s.n_paths === 1 ? '' : 's'),
                   title: (s.paths || []).join('\n') }),
      /* What kind of recording this is, and whether anybody has agreed.
         On the row rather than behind a click, because it decides how a
         CSD is computed -- and because a queue of seventy unconfirmed dual
         implants is only workable if you can see which they are. */
      BARRY.hk.probeChip(s, {
        small: true,
        onclick: (row, _st, ev) => BARRY.hk.setProbeMenu(
          ev.currentTarget, row, () => load()),
      }),
      el('div', { class: 'hk-chips' }, chips),
    ]);
  }

  /* ==================================================================
     One recording, in full
     ================================================================== */
  function find(gid) {
    for (const p of (data.tree || [])) {
      for (const m of p.mice) {
        for (const s of m.sessions) if (s.gid === gid) return s;
      }
    }
    return null;
  }

  function renderDetail() {
    const host = document.getElementById(SCOPES[scope].detail);
    if (!host) return;
    host.innerHTML = '';
    if (mouseSel) { renderMouse(host); return; }
    const s = selected && find(selected);
    if (!s) {
      host.appendChild(el('p', { class: 'hint',
        text: 'Pick a recording to see its permanent id, every path it has '
            + 'been opened from, and everything attached to it. Pick a mouse '
            + 'to label it.' }));
      return;
    }

    host.appendChild(el('div', { class: 'hk-dhead' }, [
      el('h3', { text: s.label || s.key }),
      el('code', { class: 'hk-gid big', text: s.gid }),
    ]));

    host.appendChild(el('p', { class: 'hint',
      text: 'That id was minted the first time Jarvis met this recording and '
          + 'never changes. Everything attached to it — bad channels, layer '
          + 'labels, curated events — follows the recording rather than the '
          + 'folder it happens to sit in.' }));

    /* The built-in example is in the tree but is not a registry record, so
       every by-gid write answers "No session demo-...". Saying so beats
       offering controls that fail: a new user's first click here is quite
       likely to be the example, and what they would learn is that the
       controls do not work. */
    const isDemo = /^demo-/.test(String(s.gid || ''));
    if (isDemo) {
      host.appendChild(el('p', { class: 'hint hk-demo-note',
        text: 'This is the built-in example, not a recording on a drive. It '
            + 'is here so there is something to look at before you scan '
            + 'anything, and it is not in the registry — so it cannot be '
            + 'filed under a project, annotated, merged or split. '
            + 'Everything else on this page is real: open it and it '
            + 'behaves like a recording.' }));
    }

    // ---- identity -------------------------------------------------------
    host.appendChild(el('div', { class: 'section-label', text: 'Identity' }));
    host.appendChild(el('div', { class: 'hk-facts' }, [
      fact('Derived key', s.key || '—'),
      fact('Mouse', s.mouse == null ? '—' : 'm' + s.mouse),
      fact('Session', s.session == null ? '—' : 's' + s.session),
      fact('Recorded', s.start || '—'),
      fact('First seen', (s.created || {}).at || '—'),
      fact('Last touched', (s.updated || {}).at || '—'),
      fact('Last found', (s.last_seen || {}).at || 'never by a scan'),
      fact('Channels', s.n_channels || '—'),
    ]));

    // ---- project --------------------------------------------------------
    // Not for the example: `patch` would 404 and the picker would sit there
    // showing a value it had not managed to change.
    if (!isDemo) {
    host.appendChild(el('div', { class: 'section-label', text: 'Project' }));
    const known = (data.known_projects || []).slice();
    for (const p of (data.projects || [])) {
      if (!known.includes(p)) known.push(p);
    }
    host.appendChild(el('div', { class: 'hk-proj' }, [
      el('select', {
        onchange: (e) => patch(s.gid, { project: e.target.value }),
      }, known.concat(['Unfiled']).filter((v, i, a) => a.indexOf(v) === i)
        .map((p) => el('option', {
          value: p, text: p, selected: s.project === p ? 'selected' : null,
        }))),
      el('button', {
        class: 'btn ghost sm', text: 'New project…',
        onclick: async () => {
          const name = await askPath('Name the project', 'e.g. SCN2A');
          if (name) patch(s.gid, { project: name });
        },
      }),
      el('span', { class: 'hint',
        text: s.project_source === 'manual'
          ? 'Set by hand — a later guess will not override it.'
          : 'Guessed from the path. Changing it here makes it permanent.' }),
    ]));
    /* The flag, spelled out, at the one place it can be answered.

       Both readings get stated because both are true somewhere in this
       lab's data: `D:\KCNT1\urethane\...` is the project, and
       `M15_s3_baseline_urethane` is the drug and that recording is PTEN.
       Whichever way you set it, setting it is the answer -- the picker
       above writes `manual` and the flag stops asking. */
    for (const f of (s.project_flags || [])) {
      host.appendChild(el('div', { class: 'hk-proj-flag' }, [
        el('span', { class: 'flagchip bad', text: 'worth a look' }),
        el('div', { style: 'min-width:0' }, [
          el('span', { class: 'hint',
            text: 'A path says “' + f.word + '”. That usually means '
                + f.suggests + ', and this is filed under ' + f.filed
                + ' — but the same word names an anaesthetic in some PTEN '
                + 'folders, so it is a hint and not a verdict.' }),
          el('code', { text: f.path }),
        ]),
      ]));
    }
    }

    // ---- probe ----------------------------------------------------------
    if (!isDemo) host.appendChild(probeSection(s));

    // ---- paths ----------------------------------------------------------
    host.appendChild(el('div', { class: 'section-label',
      text: 'Where it has been seen  (' + s.n_paths + ')' }));
    host.appendChild(el('p', { class: 'hint',
      text: 'Every absolute path this recording has been opened from, on any '
          + 'machine. A path that is not reachable here is not an error — it '
          + 'is someone else’s drive.' }));
    const list = el('div', { class: 'hk-paths-list' });
    for (const p of (s.paths || [])) {
      const here = (s.here || []).includes(p);
      // Which machines have actually laid eyes on this path. Two mounts of
      // one recording look identical once a path is truncated, and knowing
      // it was the rig rather than the laptop is usually the whole question.
      const saw = Object.entries(s.seen || {})
        .filter(([, v]) => v && v.path === p)
        .map(([m]) => m);
      list.appendChild(el('div', { class: 'hk-path' + (here ? ' here' : '') }, [
        el('span', { class: 'hk-dot' + (here ? ' on' : '') }),
        el('div', { style: 'min-width:0' }, [
          el('code', { text: p }),
          el('span', { class: 'hk-seen',
            text: (saw.length ? 'seen by ' + saw.join(', ')
                              : 'no machine has reported seeing this path')
                + (here ? '  \u00b7  reachable from here' : '') }),
        ]),
        el('div', { class: 'hk-btns' }, [
          el('button', {
            class: 'mini', text: 'Copy', title: 'Copy the full path',
            onclick: () => navigator.clipboard.writeText(p).then(
              () => toast('Copied.', 'ok'),
              () => toast('The browser would not let me use the clipboard.',
                          'err')),
          }),
          here ? el('button', {
            class: 'mini', text: 'Open',
            onclick: () => { setView('xplore'); BARRY.views.xplore.open(p); },
          }) : null,
          isDemo ? null : el('button', {
            class: 'mini', text: 'Split off',
            title: 'This path is a different recording that was folded in '
                 + 'here by a loose match. Give it its own record.',
            onclick: () => split(s.gid, p),
          }),
          el('button', {
            class: 'mini', text: '\u2715', title: 'Forget this path',
            onclick: () => patch(s.gid, { forget_path: p }),
          }),
        ].filter(Boolean)),
      ]));
    }
    host.appendChild(list);
    host.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Add a path…',
      title: 'For a recording whose folder was renamed, so the derived key no '
           + 'longer matches',
      onclick: async () => {
        const p = await pickPath('folder');
        if (p) patch(s.gid, { add_path: p });
      },
    }));

    // ---- what is attached ----------------------------------------------
    host.appendChild(el('div', { class: 'section-label', text: 'Attached' }));
    const has = s.has || {};
    const links = el('div', { class: 'hk-links' });
    const link = (n, label, go) => {
      links.appendChild(el('button', {
        class: 'hk-link' + (n ? '' : ' none'),
        disabled: n ? null : 'disabled',
        onclick: go,
      }, [
        el('strong', { text: String(n || 0) }),
        el('span', { text: label }),
      ]));
    };
    link(has.bad_channels, 'bad channels', () => {
      setView('toolkit');
      if (BARRY.views.toolkit && BARRY.views.toolkit.refresh) {
        BARRY.views.toolkit.refresh();
      }
    });
    link(has.figures, 'figures', () => {
      setView('results');
      if (BARRY.views.results.search) BARRY.views.results.search(s.label || '');
    });
    link(has.decks, 'decks', () => setView('storyboard'));
    link(has.banked, 'banked events', () => setView('eventbank'));
    link(has.spike_sets, 'spike sets', () => openIt(s));
    link(has.layers, 'layer labels', () => openIt(s));
    link(has.ds, 'curated events', () => openIt(s));
    host.appendChild(links);

    // ---- notes and edge cases -------------------------------------------
    // The example takes none of these either: a note, a merge, a split and
    // a forget are all writes against a registry record, and it is not one.
    if (isDemo) return;

    host.appendChild(el('div', { class: 'section-label', text: 'Note' }));
    host.appendChild(el('textarea', {
      rows: '3', class: 'hk-note', value: s.note || '',
      placeholder: 'Anything the folder name does not say.',
      onchange: (e) => patch(s.gid, { note: e.target.value }),
    }));

    host.appendChild(el('div', { class: 'section-label', text: 'Edge cases' }));
    host.appendChild(el('div', { class: 'hk-merge' }, [
      el('button', {
        class: 'btn ghost sm danger', text: 'Forget this recording',
        title: 'Drop what Jarvis remembers about it. The recording itself is '
             + 'untouched, and opening or scanning it again starts fresh.',
        onclick: async () => {
          /* The application's own dialog, not the browser's. This was
             the last `window.confirm` in the codebase: it looks like a
             different program, it cannot lay out more than a sentence
             legibly, and of all the controls to be terse in, the one
             that destroys a record's history is the wrong choice. */
          const ok = await BARRY.confirm(
            'Forget ' + (s.label || s.gid) + '?',
            'Its bad channels, notes, project and the paths Jarvis has '
            + 'seen it at go with it, and it stays gone: a tombstone is '
            + 'written so a colleague\u2019s registry cannot push it back '
            + 'and the next scan of that drive will not re-register it. '
            + 'That is the point \u2014 a scratch copy that creeps back on '
            + 'every scan has not been forgotten.\n\nThe recording on '
            + 'disk is untouched. Bringing it back is a deliberate act, '
            + 'not something a scan does for you.',
            'Forget it');
          if (!ok) return;
          try {
            await apiPost('/api/registry/' + encodeURIComponent(s.gid)
                          + '/forget', {});
            selected = null;
            await load();
          } catch (e) { toast(e.message, 'err', 7000); }
        },
      }),
      el('button', {
        class: 'btn ghost sm', text: 'Merge another record into this one…',
        title: 'For a recording that was met twice through different mounts '
             + 'and ended up with two records',
        onclick: () => mergeInto(s),
      }),
      s.merged_in && s.merged_in.length
        ? el('span', { class: 'hint',
            text: 'Absorbed ' + s.merged_in.length + ' other record'
                + (s.merged_in.length === 1 ? '' : 's') + '.' })
        : null,
      s.split_from
        ? el('span', { class: 'hint', text: 'Split off from ' + s.split_from })
        : null,
    ].filter(Boolean)));
  }

  /* ==================================================================
     Labelling a mouse

     Attributes are free-form on purpose: any name works, and a new one shows
     up as a grouping and as a column the moment it is saved. The suggested
     ones are offered first only so that everybody spells "genotype" the same
     way.
     ================================================================== */
  function renderMouse(host) {
    const rows = BARRY.hk.flatten(data).filter(
      (x) => x.project === mouseSel.project
             && String(x.mouse) === String(mouseSel.mouse));
    const attrs = rows.length ? BARRY.hk.attrsFor(data, rows[0]) : {};
    const known = BARRY.hk.attributes(data);
    const draft = Object.assign({}, attrs);

    host.appendChild(el('div', { class: 'hk-dhead' }, [
      el('h3', { text: 'm' + mouseSel.mouse }),
      el('span', { class: 'hk-sub', text: mouseSel.project }),
      el('button', {
        class: 'btn ghost sm', text: 'Close',
        onclick: () => { mouseSel = null; render(); },
      }),
    ]));
    host.appendChild(el('p', { class: 'hint',
      text: rows.length + ' recording' + (rows.length === 1 ? '' : 's')
          + ' from this animal. What you set here belongs to the mouse, not '
          + 'to any one recording \u2014 so it stays true whichever session '
          + 'you are looking at, and the tree can branch on it.' }));

    const list = el('div', { class: 'hk-attrs' });
    const addRow = (a) => {
      const input = el('input', {
        type: 'text', value: draft[a.id] || '', placeholder: a.note || '',
        list: (a.common && a.common.length) ? 'hkv-' + a.id : null,
        oninput: (e) => { draft[a.id] = e.target.value; },
      });
      const seen = (a.values || []).map((v) => v[0]);
      const choices = Array.from(new Set([].concat(a.common || [], seen)));
      list.appendChild(el('div', { class: 'hk-attr' }, [
        el('label', { text: a.name, title: a.id }),
        input,
        choices.length
          ? el('datalist', { id: 'hkv-' + a.id },
               choices.map((v) => el('option', { value: v })))
          : null,
        el('button', {
          class: 'hk-x', text: '\u00d7', title: 'Clear this label',
          onclick: () => { draft[a.id] = ''; input.value = ''; },
        }),
      ].filter(Boolean)));
    };
    known.forEach(addRow);
    Object.keys(attrs).forEach((k) => {
      if (!known.some((a) => a.id === k)) {
        addRow({ id: k, name: k.replace(/_/g, ' '), common: [], values: [] });
      }
    });
    host.appendChild(list);

    // ---- a label nobody has used yet ------------------------------------
    const newName = el('input', { type: 'text',
      placeholder: 'e.g. implant date, virus batch, cage' });
    const newVal = el('input', { type: 'text', placeholder: 'value' });
    host.appendChild(el('div', { class: 'section-label',
                                 text: 'A new kind of label' }));
    host.appendChild(el('div', { class: 'hk-attr new' }, [
      newName, newVal,
      el('button', {
        class: 'btn ghost sm', text: 'Add',
        onclick: () => {
          const name = newName.value.trim();
          if (!name) { toast('Give the label a name first.', 'err'); return; }
          draft[name] = newVal.value;
          save(draft);
        },
      }),
    ]));

    const others = Array.from(new Set(BARRY.hk.flatten(data)
      .filter((x) => x.project === mouseSel.project)
      .map((x) => x.mouse)))
      .filter((m) => String(m) !== String(mouseSel.mouse));

    host.appendChild(el('div', { class: 'hk-actions' }, [
      el('button', { class: 'btn', text: 'Save',
                     onclick: () => save(draft) }),
      others.length
        ? el('button', {
            class: 'btn ghost', text: 'Save to several\u2026',
            title: 'Give the same labels to more than one animal at once',
            onclick: () => saveMany(draft, others),
          })
        : null,
    ].filter(Boolean)));
  }

  async function save(attrs) {
    try {
      await apiPost('/api/mice/set', {
        project: mouseSel.project, mouse: mouseSel.mouse, attrs,
      });
      toast('Saved.', 'ok');
      await load();
    } catch (e) { toast(e.message, 'err', 7000); }
  }

  /* One label on one mouse at a time is fine for six animals and unbearable
     for sixty, which is exactly why the lab was using a spreadsheet. */
  function saveMany(attrs, others) {
    const picked = new Set([String(mouseSel.mouse)]);
    const filled = {};
    Object.keys(attrs).forEach((k) => {
      if (String(attrs[k] || '').trim()) filled[k] = attrs[k];
    });
    const boxes = others.map((m) => el('label', { class: 'toggle' }, [
      el('input', {
        type: 'checkbox',
        onchange: (e) => {
          if (e.target.checked) picked.add(String(m));
          else picked.delete(String(m));
        },
      }),
      el('span', { text: 'm' + m }),
    ]));
    showModal(el('div', {}, [
      el('h3', { text: 'Give these labels to other animals' }),
      el('p', { class: 'hint',
        text: Object.keys(filled).map((k) => k + ' = ' + filled[k]).join(', ')
            || 'Nothing is filled in, so this would clear their labels.' }),
      el('div', { class: 'hk-pick' }, boxes),
      el('div', { class: 'row' }, [
        el('button', { class: 'btn', text: 'Apply', onclick: async () => {
          const targets = Array.from(picked).map((m) => ({
            project: mouseSel.project, mouse: Number(m),
          }));
          try {
            await apiPost('/api/mice/set', { targets, attrs: filled });
            toast('Labelled ' + targets.length + ' animal'
                  + (targets.length === 1 ? '' : 's') + '.', 'ok');
            closeModal();
            await load();
          } catch (e) { toast(e.message, 'err', 7000); }
        } }),
        el('button', { class: 'btn ghost', text: 'Cancel',
                       onclick: () => closeModal() }),
      ]),
    ]));
  }

  /* One cell of the table. Filling a column down is the actual job, so this
     is deliberately the shortest path there is: click, type, enter. */
  function quickSet(row, attr) {
    const a = BARRY.hk.attributes(data).find((x) => x.id === attr) || {};
    const seen = (a.values || []).map((v) => v[0]);
    const choices = Array.from(new Set([].concat(a.common || [], seen)));
    const input = el('input', { type: 'text', value: row.attrs[attr] || '',
                                list: choices.length ? 'hkq' : null });
    const go = async () => {
      try {
        await apiPost('/api/mice/set', {
          project: row.project, mouse: row.mouse,
          attrs: { [attr]: input.value },
        });
        closeModal();
        await load();
      } catch (e) { toast(e.message, 'err', 7000); }
    };
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
    showModal(el('div', {}, [
      el('h3', { text: (a.name || attr) + ' for m' + row.mouse }),
      el('div', { class: 'row' }, [
        input,
        choices.length
          ? el('datalist', { id: 'hkq' },
               choices.map((v) => el('option', { value: v })))
          : null,
        el('button', { class: 'btn', text: 'Set', onclick: go }),
      ].filter(Boolean)),
      el('p', { class: 'hint', text: 'Leave it empty to clear the label.' }),
    ]));
    setTimeout(() => { input.focus(); input.select(); }, 30);
  }

  function fact(k, v) {
    return el('div', { class: 'hk-fact' }, [
      el('span', { class: 'k', text: k }),
      el('span', { class: 'v', text: String(v), title: String(v) }),
    ]);
  }

  function openIt(s) {
    const p = (s.here || [])[0];
    if (!p) {
      toast('None of this recording’s paths are reachable from this '
            + 'machine.', 'err', 6000);
      return;
    }
    setView('xplore');
    BARRY.views.xplore.open(p);
  }

  /* ==================================================================
     Changes
     ================================================================== */
  /* ==================================================================
     Which probe went into the animal
     ==================================================================
     Here rather than in Xplorefinder, because it is a fact about the
     recording and not about whoever has it open. It used to live in the
     Xplorefinder session's view state, which meant it lasted as long as
     that window and travelled to nobody -- so Incisor, a colleague's
     machine and the next open could each believe something different about
     the same animal.

     It is load-bearing. The template decides how the array is divided into
     lines of contacts, and a CSD is only meaningful down one line. On a
     dual implant the wrong template runs the second spatial derivative
     across the gap at channel 64, subtracting cortex from hippocampus. The
     number that comes out is not a current sink, and nothing about it looks
     wrong.

     "Nobody has said" is kept distinct from "somebody said H3" -- the same
     distinction `banks_for` draws by leaving a region blank. A blank that
     is visibly blank can be filled in; a guess that looks like a fact
     cannot be found again. */
  let PROBES = null;

  function probeSection(s) {
    const box = el('div', {});
    box.appendChild(el('div', { class: 'section-label', text: 'Probe' }));
    if (!PROBES) {
      api('/api/probes').then((d) => {
        PROBES = d.probes || [];
        renderDetail();
      }).catch(() => { PROBES = []; });
      box.appendChild(el('p', { class: 'hint quiet', text: 'Reading the '
                                + 'probe templates…' }));
      return box;
    }
    if (!PROBES.length) {
      box.appendChild(el('p', { class: 'hint quiet',
        text: 'No probe templates are available from this server.' }));
      return box;
    }

    const now = s.probe || '';
    const guess = s.probe_suggested || 'h3';
    const nch = s.n_channels || null;
    const sel = el('select', {
      onchange: (e) => setProbe(s.gid, e.target.value),
    });
    sel.appendChild(el('option', {
      value: '', selected: now ? null : 'selected',
      text: 'Nobody has said'
          + (guess ? '  ·  reads as ' + nameOf(guess) : ''),
    }));
    for (const p of PROBES) {
      /* Every template is offered, including ones the channel count does
         not support -- a recording whose continuation files inflate the
         count to 192 is still a dual implant, and refusing the choice
         because the arithmetic disagrees would make the only recordings
         that need correcting the only ones that cannot be. The mismatch is
         said out loud below instead. */
      sel.appendChild(el('option', {
        value: p.id, title: p.note || '',
        selected: now === p.id ? 'selected' : null,
        text: p.name + ((p.n_columns || 1) > 1
          ? '  ·  ' + p.n_columns + ' columns' : ''),
      }));
    }

    box.appendChild(el('div', { class: 'hk-proj' }, [
      sel,
      el('span', { class: 'hint',
        text: now
          ? (s.probe_source === 'manual'
             ? 'Set by hand. Every view of this recording reads it — '
               + 'Xplorefinder lays the panes out by it and Incisor scans '
               + 'by it.'
             : 'Carried over from a window where it was set.')
          : 'Not set. Everything that needs a line of contacts will treat '
            + 'this as a single array, which is right for most recordings '
            + 'and wrong for a dual implant.' }),
    ]));

    const def = PROBES.find((p) => p.id === (now || guess));
    if (def && (def.columns || []).length) {
      const rows = el('div', { class: 'hk-probe-cols' });
      for (const c of def.columns) {
        const first = c.csc[0], lastN = c.csc[c.csc.length - 1];
        rows.appendChild(el('div', { class: 'hk-probe-col' }, [
          el('span', { class: 'pane-col-tag shank-' + (c.shank || 'back'),
                       text: c.id }),
          el('span', { text: c.label || c.id }),
          el('code', { text: 'CSC ' + first + '–' + lastN
                           + '  ·  ' + c.n + ' contacts' }),
        ]));
      }
      box.appendChild(rows);
      box.appendChild(el('p', { class: 'hint',
        text: (now ? 'These are' : 'If that were set it would be')
            + ' ' + def.columns.length + ' separate lines of contacts, one '
            + 'pane each in Xplorefinder, and a CSD is computed down each '
            + 'one on its own.' }));
    }

    /* The channel count and the template disagreeing is worth saying, and
       worth saying as a question rather than as an error: the recordings
       whose CSC files are doubled by a restarted acquisition report 192 or
       256 and really are dual implants. */
    const want = def && def.expects_channels;
    if (now && want && nch && want !== nch) {
      box.appendChild(el('p', { class: 'warn-line',
        text: 'This template expects ' + want + ' channels and the '
            + 'recording reports ' + nch + '. That is worth a look — though '
            + 'a recording whose channels are split across CSCn.ncs and '
            + 'CSCn_0001.ncs counts every file, so the number can be high '
            + 'for a reason that has nothing to do with the probe.' }));
    }
    return box;
  }

  function nameOf(id) {
    const p = (PROBES || []).find((x) => x.id === id);
    return p ? p.name : id;
  }

  async function setProbe(gid, probe) {
    try {
      const res = await apiPost(
        '/api/registry/' + encodeURIComponent(gid) + '/probe', { probe });
      /* Setting a template with named regions fills in any blank channel
         bank, because picking "hippocampus + M2" IS saying which bank is
         which -- and making somebody enter the same fact twice is how the
         two come to disagree. Said out loud, since it changed something the
         person did not click on. */
      const named = (res.channel_banks || [])
        .filter((b) => (b.said_via || '').indexOf('probe:') === 0);
      if (named.length) {
        toast('Also labelled ' + named.map((b) => b.region).join(' and ')
              + ' from that template.', 'ok', 6000);
      }
      await load();
      BARRY.refreshSync();
    } catch (e) { toast(e.message, 'err', 7000); }
  }

  async function patch(gid, body) {
    try {
      await apiPost('/api/registry/' + encodeURIComponent(gid) + '/patch', body);
      await load();
      BARRY.refreshSync();
    } catch (e) { toast(e.message, 'err', 7000); }
  }

  async function split(gid, path) {
    // No confirmation dialog: the server refuses the only dangerous case
    // (splitting off the last path, which would empty the record), and a
    // split is undone by merging the two back together.
    try {
      const res = await apiPost('/api/registry/split', { gid, path });
      toast('Split off as ' + (res.session || {}).gid, 'ok', 6000);
      await load();
    } catch (e) { toast(e.message, 'err', 8000); }
  }

  async function mergeInto(keep) {
    const others = [];
    for (const p of (data.tree || [])) {
      for (const m of p.mice) {
        for (const s of m.sessions) if (s.gid !== keep.gid) others.push(s);
      }
    }
    if (!others.length) {
      toast('There is nothing else to merge.', null, 4000);
      return;
    }
    const pick = el('select', {}, others.map((s) => el('option', {
      value: s.gid, text: (s.label || s.key) + '   [' + s.gid + ']',
    })));
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Merge into ' + (keep.label || keep.key) }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { class: 'confirm-msg',
          text: 'The record you pick will hand over its paths, its bad '
              + 'channels and its note, then be retired — it stays on disk '
              + 'as a pointer here, so anything still referring to its id can '
              + 'follow it. Nothing is deleted.' }),
        el('div', { class: 'field' }, [
          el('label', { text: 'Record to absorb' }), pick,
        ]),
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        el('button', {
          class: 'btn', text: 'Merge',
          onclick: async () => {
            try {
              await apiPost('/api/registry/merge',
                            { keep: keep.gid, drop: pick.value });
              closeModal();
              toast('Merged.', 'ok');
              await load();
            } catch (e) { toast(e.message, 'err', 8000); }
          },
        }),
      ]),
    ]));
  }

  function init() {
    const b = $('#hkRefresh');
    if (b) b.addEventListener('click', () => load(true));
  }

  /* Open one recording's detail from somewhere else in the app.

     The project picker lives here and nowhere else, so a flag raised on a
     Sessions card has to be able to point at it. Loads first if this view
     has never been shown -- `selected` means nothing against no data, and
     rendering it would show an empty panel for a recording that exists. */
  async function inspect(gid) {
    if (!gid) return;
    if (!data) await load(false);
    selected = gid;
    render();
    const det = document.getElementById(SCOPES[scope].detail);
    if (det && det.scrollIntoView) det.scrollIntoView({ block: 'nearest' });
  }

  /* Draw one of the two catalogues.

     Called by the Sessions view when the mode switch moves, because that is
     what owns the panels. Loads on first use rather than at startup: a
     cluster view nobody opens should not cost a registry read. */
  async function catalogue(which) {
    scope = SCOPES[which] ? which : 'jarvis';
    if (!data) { await load(false); return; }
    render();
  }

  return { init, onShow, confirm, inspect, catalogue,
           get scope() { return scope; },
           reload: () => load(true),
           get confirmed() { return Array.from(confirmed); } };
})();
