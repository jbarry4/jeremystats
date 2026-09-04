/* ==========================================================================
   results.js -- the Results catalog.

   Everything BARRY saves is listed here automatically: figures from the
   builder, single-window exports, and any image or table a pipeline stage
   drops into a session folder. Nothing has to be filed by hand -- the catalog
   is rebuilt by scanning, so a colleague's committed figure shows up after a
   pull.

   From here a result can be tagged, starred, previewed at full size, revealed
   on disk, or dropped straight onto a storyboard slide.
   ========================================================================== */
'use strict';

BARRY.views.results = (function () {
  let items = [];
  let facets = { tags: [], sessions: [] };
  let meta = {};
  let query = '';
  let typeFilter = '';
  let tagFilter = '';
  let sessionFilter = '';
  let starredOnly = false;
  let selected = new Set();
  let view = 'grid';          // 'grid' | 'list' | 'compare'
  let sortBy = 'created';     // 'created' | 'title' | 'session' | 'bytes'
  let collections = [];       // saved searches, synced through preferences

  /* Folders, which are not the same thing as tags and not the same thing as
     collections. A tag is something a result is about and it can have five;
     a collection is a saved search, so its contents change when the results
     do; a folder is where a result lives, and it lives in one.

     Filing is BARRY's, not the disk's: the files stay where the run wrote
     them, because a run record points at a path and moving the file behind
     it would break the rebuild of every figure made before the move. */
  let folders = [];
  let unfiled = 0;
  let folderFilter = '';      // '' = everything, '~unfiled' = never filed

  async function load(refresh) {
    const q = new URLSearchParams();
    if (refresh) q.set('refresh', '1');
    try {
      const res = await api('/api/results?' + q.toString());
      items = res.results || [];
      facets = { tags: res.tags || [], sessions: res.sessions || [] };
      meta = res;
      const tree = await api('/api/results/folders');
      folders = tree.folders || [];
      unfiled = tree.unfiled || 0;
    } catch (e) {
      toast('Could not read the catalog: ' + e.message, 'err');
      items = [];
    }
    collections = BARRY.prefs.get('result_collections', []) || [];
    render();
  }

  /* ---------- filtering ---------- */
  function visible() {
    const q = query.trim().toLowerCase();
    return items.filter((r) => {
      if (typeFilter && r.type !== typeFilter) return false;
      if (tagFilter && !(r.tags || []).includes(tagFilter)) return false;
      if (folderFilter) {
        // The real directory under Results/. Filing moves the file, so what
        // this filters on is what you would see in Explorer.
        const f = (r.folder || '').trim();
        if (folderFilter === '~unfiled') {
          if (f) return false;
        } else if (!(f === folderFilter
                     || f.startsWith(folderFilter + '/'))) {
          // A folder means it and everything under it. Clicking "Figure 3"
          // and seeing nothing because it all sits in "Figure 3/Panels" is
          // not an answer.
          return false;
        }
      }
      if (sessionFilter && r.session_key !== sessionFilter) return false;
      if (starredOnly && !r.starred) return false;
      if (!q) return true;
      const hay = [r.title, r.name, r.session_label, r.author, r.notes,
                   r.script, r.machine, (r.tags || []).join(' ')]
                   .join(' ').toLowerCase();
      return hay.includes(q);
    }).sort(sorter);
  }

  function sorter(a, b) {
    switch (sortBy) {
      case 'title':
        return String(a.title || a.name).localeCompare(String(b.title || b.name));
      case 'session':
        return String(a.session_label || '').localeCompare(
                 String(b.session_label || ''))
               || String(b.created || '').localeCompare(String(a.created || ''));
      case 'bytes':
        return (b.bytes || 0) - (a.bytes || 0);
      default:
        return String(b.created || '').localeCompare(String(a.created || ''));
    }
  }

  const fileUrl = (r, dl) =>
    '/api/results/file?id=' + encodeURIComponent(r.id) + (dl ? '&download=1' : '');

  /* ---------- rendering ---------- */
  function render() {
    const host = $('#resultsBody');
    host.innerHTML = '';
    const list = visible();

    $('#resultsSub').textContent = list.length + ' of ' + items.length
      + ' result(s)' + (meta.outputs_dir ? '  ·  ' + meta.outputs_dir : '');

    host.appendChild(toolbar(list));
    host.appendChild(folderRow());
    const coll = collectionRow();
    if (coll) host.appendChild(coll);
    if (selected.size) host.appendChild(bulkBar(list));

    if (!items.length) {
      host.appendChild(el('div', { class: 'empty-state' }, [
        el('svg', { viewBox: '0 0 24 24',
          html: '<rect x="3" y="3" width="18" height="18" rx="2"/>'
              + '<path d="M3 15l4-4 3 3 4-5 7 7"/><circle cx="8.5" cy="8.5" r="1.5"/>' }),
        el('p', { text: 'Nothing here yet. Everything the GUI saves — figures, '
                      + 'deck exports, manifests — is cataloged here '
                      + 'automatically, and lives in the Results folder in '
                      + 'the repo.' }),
      ]));
      return;
    }
    if (!list.length) {
      host.appendChild(el('div', { class: 'tree-empty', text: 'Nothing matches those filters.' }));
      return;
    }

    host.appendChild(view === 'compare' ? compareGrid(list)
                     : (view === 'grid' ? grid(list) : table(list)));
  }

  /* ======================================================================
     Feature 1 -- Compare mode
     Two figures from different sessions, or the same figure before and after
     a filter change, side by side at full width. The comparison people
     otherwise make by opening two image viewers.
     ====================================================================== */
  function compareGrid(list) {
    const chosen = selected.size
      ? list.filter((r) => selected.has(r.id))
      : list.slice(0, 4);
    if (!chosen.length) {
      return el('div', { class: 'tree-empty',
        text: 'Select two or more results to compare them.' });
    }
    return el('div', { class: 'cmp-grid' }, chosen.map((r) =>
      el('div', { class: 'cmp-cell' }, [
        el('div', { class: 'im', onclick: () => preview(r) }, [
          r.type === 'image'
            ? el('img', { src: fileUrl(r), alt: '', loading: 'lazy' })
            : el('span', { class: 'noimg',
                text: (r.ext || '').replace('.', '').toUpperCase() || 'FILE' }),
        ]),
        el('div', { class: 'cap' }, [
          el('b', { text: r.title || r.name }),
          el('span', { text: [r.session_label, r.author,
                              (r.created || '').slice(0, 10)]
                              .filter(Boolean).join('  ·  ') }),
          r.notes ? el('div', { style: 'margin-top:4px;color:var(--text-3)',
                                text: r.notes }) : null,
        ]),
      ])));
  }

  /* ======================================================================
     Feature 2 -- Bulk actions
     Tagging thirty figures one dialog at a time is why nobody tags figures.
     ====================================================================== */
  function bulkBar(list) {
    const chosen = () => items.filter((r) => selected.has(r.id));
    return el('div', { class: 'bulk-bar' }, [
      el('span', { class: 'n', text: selected.size + ' selected' }),
      el('button', {
        class: 'btn sm', text: 'Add to storyboard →',
        onclick: () => {
          const pick = chosen();
          selected.clear();
          setView('storyboard');
          BARRY.views.storyboard.addResults(pick);
        },
      }),
      el('button', {
        class: 'btn ghost sm', text: 'Compare',
        onclick: () => { view = 'compare'; render(); },
      }),
      el('button', {
        class: 'btn ghost sm', text: 'Tag all…',
        onclick: bulkTag,
      }),
      moveMenu(),
      el('button', {
        class: 'btn ghost sm', text: 'Star all',
        onclick: () => bulk({ starred: true }),
      }),
      el('button', {
        class: 'btn ghost sm', text: 'Unstar all',
        onclick: () => bulk({ starred: false }),
      }),
      el('button', {
        class: 'btn ghost sm', text: 'Export manifest',
        onclick: () => {
          BARRY.download('/api/results/manifest',
                         { ids: Array.from(selected) },
                         'results-manifest.csv');
        },
      }),
      el('button', {
        class: 'btn ghost sm danger', text: 'Delete…',
        onclick: bulkDelete,
      }),
      el('div', { style: 'flex:1' }),
      el('button', {
        class: 'btn ghost sm', text: 'Select all shown',
        onclick: () => { for (const r of list) selected.add(r.id); render(); },
      }),
      el('button', {
        class: 'btn ghost sm', text: 'Clear',
        onclick: () => { selected.clear(); render(); },
      }),
    ]);
  }

  async function bulk(patch) {
    const ids = Array.from(selected);
    if (!ids.length) return;
    try {
      const res = await apiPost('/api/results/bulk',
                                Object.assign({ ids }, patch));
      toast('Updated ' + res.touched + ' result(s)', 'ok');
      await load(true);
    } catch (e) { toast(e.message, 'err'); }
  }

  function bulkTag() {
    const add = el('input', { type: 'text',
      placeholder: 'comma separated, e.g. figure 3, KCNT1' });
    const remove = el('input', { type: 'text',
      placeholder: 'tags to take off these results' });
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Tag ' + selected.size + ' result(s)' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'field' }, [el('label', { text: 'Add tags' }), add]),
        el('div', { class: 'field' }, [
          el('label', { text: 'Remove tags' }), remove,
        ]),
        facets.tags.length
          ? el('div', { class: 'coll-row' }, facets.tags.map(([t]) =>
              el('span', { class: 'coll-chip', text: t,
                onclick: () => {
                  add.value = add.value ? add.value + ', ' + t : t;
                } })))
          : null,
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        el('button', {
          class: 'btn', text: 'Apply',
          onclick: () => {
            const split = (v) => v.split(',').map((x) => x.trim()).filter(Boolean);
            closeModal();
            bulk({ add_tags: split(add.value), remove_tags: split(remove.value) });
          },
        }),
      ]),
    ]));
  }


  /* ==================================================================
     Folders

     These are real directories under Results/, not labels. Moving a result
     into one moves the file, so what this shows and what you see when you
     open the folder are the same thing -- which is the point, because most
     of the time people are looking for a figure outside BARRY.

     Shown as a row of chips rather than a side tree: the depth is rarely
     more than two and a permanent rail would cost width the thumbnails
     want. Nesting reads from the indent marker rather than from position.
     ================================================================== */
  function folderRow() {
    const bar = el('div', { class: 'res-folders' });
    const chip = (id, label, n, extra) => el('button', {
      class: 'folder-chip' + (folderFilter === id ? ' on' : '')
           + (extra || ''),
      onclick: () => {
        folderFilter = folderFilter === id ? '' : id;
        render();
      },
    }, [
      el('span', { text: label }),
      n != null ? el('span', { class: 'n', text: String(n) }) : null,
    ].filter(Boolean));

    bar.appendChild(el('span', { class: 'res-folders-label', text: 'Folders' }));
    bar.appendChild(chip('', 'All', items.length));
    for (const f of folders) {
      bar.appendChild(chip(
        f.path,
        (f.depth ? '\u00b7 '.repeat(f.depth) : '') + f.name,
        f.n || 0));
    }
    if (unfiled) bar.appendChild(chip('~unfiled', 'Unfiled', unfiled, ' dim'));

    bar.appendChild(el('div', { class: 'spacer' }));
    if (folderFilter && folderFilter !== '~unfiled') {
      bar.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Rename\u2026',
        title: 'Renames this folder and everything under it',
        onclick: () => renameFolder(folderFilter),
      }));
    }
    bar.appendChild(el('button', {
      class: 'btn ghost sm', text: 'New folder\u2026',
      title: 'Make a folder by filing something into it',
      onclick: () => newFolder(),
    }));
    return bar;
  }

  async function newFolder() {
    const name = await askPath('Name the folder',
                               'Figure 3, or Figure 3/Panels for a subfolder');
    if (!name) return;
    try {
      // A real directory, made whether or not anything goes in it yet --
      // which is how people work: you make "Figure 3", then decide.
      const res = await apiPost('/api/results/folders/new', { name });
      folders = res.folders || folders;
      if (selected.size) await moveTo(res.folder);
      else { toast('Made Results/' + res.folder + '.', 'ok'); await load(); }
    } catch (e) { toast(e.message, 'err', 8000); }
  }

  async function moveTo(folder) {
    const ids = [...selected];
    try {
      const res = await apiPost('/api/results/bulk', { ids, folder });
      folders = res.folders || folders;
      const n = res.moved != null ? res.moved : res.touched;
      toast('Moved ' + n + ' file' + (n === 1 ? '' : 's')
            + (folder ? ' into Results/' + folder : ' back to the top of '
               + 'Results') + '.', 'ok');
      for (const f of (res.failed || [])) toast(f, 'err', 8000);
      BARRY.activity.log('result.folder.move', { n: res.touched, folder });
      selected.clear();
      await load();
    } catch (e) { toast(e.message, 'err', 8000); }
  }

  async function renameFolder(from) {
    const to = await askPath('Rename "' + from + '" to', from);
    if (!to || to === from) return;
    try {
      const res = await apiPost('/api/results/folders/rename', { from, to });
      toast('Renamed, and moved ' + res.touched + ' result'
            + (res.touched === 1 ? '' : 's') + '.', 'ok');
      folderFilter = to;
      await load();
    } catch (e) { toast(e.message, 'err', 8000); }
  }

  /* The move menu in the bulk bar: existing folders, plus somewhere new. */
  function moveMenu() {
    const sel = el('select', {
      class: 'res-move',
      onchange: async (e) => {
        const v = e.target.value;
        e.target.selectedIndex = 0;
        if (v === '__new') {
          const name = await askPath('Name the folder',
                                     'Figure 3, or Figure 3/Panels');
          if (name) await moveTo(name);
        } else if (v === '__none') {
          await moveTo('');
        } else if (v) {
          await moveTo(v);
        }
      },
    }, [
      el('option', { value: '', text: 'Move to\u2026' }),
      ...folders.map((f) => el('option', {
        value: f.path,
        text: (f.depth ? '\u00a0\u00a0'.repeat(f.depth) : '') + f.name,
      })),
      el('option', { value: '__new', text: 'A new folder\u2026' }),
      el('option', { value: '__none', text: 'Out of any folder' }),
    ]);
    return sel;
  }

  async function bulkDelete() {
    const chosen = items.filter((r) => selected.has(r.id));
    const out = (meta.outputs_dir || '').toLowerCase();
    const inside = chosen.filter(
      (r) => String(r.path || '').toLowerCase().startsWith(out));
    const outside = chosen.length - inside.length;

    const ok = await BARRY.confirm(
      'Delete ' + inside.length + ' file(s)?',
      el('div', {}, [
        el('p', { class: 'confirm-msg',
          text: 'These files are removed from disk. This cannot be undone.' }),
        outside ? el('p', { class: 'confirm-msg',
          text: outside + ' of the selected result(s) live outside the Output '
              + 'folder and will be left alone \u2014 BARRY only deletes what '
              + 'it filed itself.' }) : null,
        el('div', { class: 'source-box' }, [
          el('pre', { text: inside.map((r) => r.name).join('\n') || '(nothing)' }),
        ]),
      ]),
      'Delete them', true);
    if (!ok || !inside.length) return;

    try {
      const res = await apiPost('/api/results/delete',
                                { ids: inside.map((r) => r.id) });
      selected.clear();
      toast('Deleted ' + res.removed.length + ' file(s)', 'ok');
      for (const f of (res.refused || [])) toast(f.error, 'err', 7000);
      await load(true);
    } catch (e) { toast(e.message, 'err'); }
  }

  /* ======================================================================
     Feature 3 -- Smart collections
     A named filter set. "Figure 3 candidates" is a search, not a folder, so
     a newly exported figure joins it on its own.
     ====================================================================== */
  function currentFilter() {
    return { query, typeFilter, tagFilter, sessionFilter, starredOnly, sortBy };
  }

  function collectionRow() {
    const cur = JSON.stringify(currentFilter());
    const chips = collections.map((c) => el('span', {
      class: 'coll-chip' + (JSON.stringify(c.filter) === cur ? ' on' : ''),
      title: describeFilter(c.filter),
      onclick: () => applyCollection(c),
    }, [
      el('span', { text: c.name }),
      el('span', {
        class: 'x', text: '\u00d7', title: 'Forget this collection',
        onclick: (e) => {
          e.stopPropagation();
          collections = collections.filter((x) => x.id !== c.id);
          BARRY.prefs.set('result_collections', collections);
          render();
        },
      }),
    ]));

    const dirty = query || typeFilter || tagFilter || sessionFilter || starredOnly;
    chips.push(el('button', {
      class: 'btn ghost sm', text: 'Save this search…',
      disabled: dirty ? null : 'disabled',
      title: dirty ? 'Name the current filters'
                   : 'Set some filters first',
      onclick: async () => {
        const name = await askPath('Name this collection',
                                   'e.g. Figure 3 candidates');
        if (!name) return;
        collections = collections.concat([{
          id: 'c' + Date.now().toString(36),
          name, filter: currentFilter(),
        }]);
        BARRY.prefs.set('result_collections', collections);
        render();
        toast('Saved "' + name + '"', 'ok');
        BARRY.activity.log('result.collection.save', { name });
      },
    }));
    if (dirty) {
      chips.push(el('button', {
        class: 'btn ghost sm', text: 'Clear filters',
        onclick: () => {
          query = ''; typeFilter = ''; tagFilter = '';
          sessionFilter = ''; starredOnly = false;
          render();
        },
      }));
    }
    /* With no saved collections and no filters set, this row held one
       disabled button and 11px of margin -- a whole bar of chrome above the
       figures that could not be used for anything. It appears when there is
       something in it. */
    if (!collections.length && !dirty) return null;
    return el('div', { class: 'coll-row', style: 'margin-bottom:7px' }, chips);
  }

  function applyCollection(c) {
    const f = c.filter || {};
    query = f.query || '';
    typeFilter = f.typeFilter || '';
    tagFilter = f.tagFilter || '';
    sessionFilter = f.sessionFilter || '';
    starredOnly = !!f.starredOnly;
    sortBy = f.sortBy || 'created';
    render();
    BARRY.activity.log('result.collection.apply', { name: c.name });
  }

  function describeFilter(f) {
    const bits = [];
    if (f.query) bits.push('"' + f.query + '"');
    if (f.typeFilter) bits.push(f.typeFilter);
    if (f.tagFilter) bits.push('tag: ' + f.tagFilter);
    if (f.sessionFilter) bits.push('one session');
    if (f.starredOnly) bits.push('starred');
    return bits.join(', ') || 'everything';
  }

  function toolbar(list) {
    const bar = el('div', { class: 'res-toolbar' });

    bar.appendChild(el('div', { class: 'search-wrap inline' }, [
      el('svg', { viewBox: '0 0 20 20', class: 'search-icon',
        html: '<circle cx="9" cy="9" r="6"/><path d="m14 14 4 4"/>' }),
      el('input', {
        type: 'search', value: query,
        placeholder: 'Search titles, tags, sessions, notes…',
        oninput: debounceInput(
          (e) => { query = e.target.value; keepFocus(render); }, 140),
      }),
    ]));

    const pills = el('div', { class: 'filter-row' });
    const pill = (label, active, fn) => el('button', {
      class: 'pill' + (active ? ' active' : ''), text: label, onclick: fn,
    });
    pills.appendChild(pill('All', !typeFilter, () => { typeFilter = ''; render(); }));
    for (const [t, label] of [['image', 'Images'], ['pdf', 'PDFs'], ['table', 'Tables']]) {
      pills.appendChild(pill(label, typeFilter === t,
        () => { typeFilter = typeFilter === t ? '' : t; render(); }));
    }
    pills.appendChild(pill('★ Starred', starredOnly,
      () => { starredOnly = !starredOnly; render(); }));
    bar.appendChild(pills);

    if (facets.sessions.length) {
      bar.appendChild(el('select', {
        title: 'Filter by session',
        onchange: (e) => { sessionFilter = e.target.value; render(); },
      }, [el('option', { value: '', text: 'All sessions' })].concat(
        facets.sessions.map(([key, label]) => el('option', {
          value: key, text: label, selected: sessionFilter === key ? 'selected' : null,
        })))));
    }

    if (facets.tags.length) {
      bar.appendChild(el('select', {
        title: 'Filter by tag',
        onchange: (e) => { tagFilter = e.target.value; render(); },
      }, [el('option', { value: '', text: 'All tags' })].concat(
        facets.tags.map(([t, n]) => el('option', {
          value: t, text: t + ' (' + n + ')',
          selected: tagFilter === t ? 'selected' : null,
        })))));
    }

    bar.appendChild(el('div', { style: 'flex:1' }));

    bar.appendChild(el('select', {
      title: 'Sort order',
      onchange: (e) => { sortBy = e.target.value; render(); },
    }, [['created', 'Newest first'], ['title', 'By title'],
        ['session', 'By session'], ['bytes', 'Largest first']]
      .map(([v, t]) => el('option', {
        value: v, text: t, selected: sortBy === v ? 'selected' : null,
      }))));

    bar.appendChild(el('div', { class: 'seg' }, [
      el('button', { class: view === 'grid' ? 'active' : '', text: 'Grid',
                     onclick: () => { view = 'grid'; render(); } }),
      el('button', { class: view === 'list' ? 'active' : '', text: 'List',
                     onclick: () => { view = 'list'; render(); } }),
      el('button', { class: view === 'compare' ? 'active' : '', text: 'Compare',
                     title: 'Show the selected results side by side',
                     onclick: () => { view = 'compare'; render(); } }),
    ]));
    return bar;
  }

  function grid(list) {
    const g = el('div', { class: 'res-grid' });
    for (const r of list) g.appendChild(card(r));
    return g;
  }

  function card(r) {
    const isSel = selected.has(r.id);
    return el('div', { class: 'res-card' + (isSel ? ' sel' : '') }, [
      el('button', {
        class: 'res-pick' + (isSel ? ' on' : ''),
        text: isSel ? '✓' : '+',
        title: isSel ? 'Remove from selection' : 'Select for a storyboard',
        onclick: () => {
          if (isSel) selected.delete(r.id); else selected.add(r.id);
          render();
        },
      }),
      el('button', {
        class: 'res-star' + (r.starred ? ' on' : ''),
        text: r.starred ? '★' : '☆',
        title: r.starred ? 'Unstar' : 'Star this result',
        onclick: () => curate(r, { starred: !r.starred }),
      }),
      el('div', {
        class: 'res-thumb', title: 'Open full size',
        onclick: () => preview(r),
      }, [
        r.type === 'image'
          ? el('img', { src: fileUrl(r), alt: '', loading: 'lazy' })
          : el('span', { class: 'noimg',
              text: (r.ext || '').replace('.', '').toUpperCase() || 'FILE' }),
      ]),
      el('div', { class: 'res-meta' }, [
        el('div', { class: 'res-title', text: r.title || r.name, title: r.path }),
        el('div', { class: 'res-sub', text: [
          r.session_label, r.author, fmtBytes(r.bytes),
        ].filter(Boolean).join('  ·  ') }),
        el('div', { class: 'res-sub', text: (r.created || '').replace('T', ' ').slice(0, 16) }),
        (r.tags || []).length ? el('div', { class: 'res-tags' },
          r.tags.map((t) => el('span', {
            class: 'flagchip', text: t,
            onclick: () => { tagFilter = t; render(); },
          }))) : null,
      ]),
      el('div', { class: 'res-acts' }, [
        el('button', { class: 'mini', text: 'Open', onclick: () => preview(r) }),
        rebuildBtn(r),
        el('button', { class: 'mini', text: 'Tag', onclick: () => editTags(r) }),
        el('button', { class: 'mini', text: 'Reveal',
          onclick: () => apiPost('/api/results/reveal', { id: r.id }).catch(() => {}) }),
        r.session_path ? el('button', {
          class: 'mini', text: 'Session',
          title: 'Open the recording this came from',
          onclick: () => { setView('xplore'); BARRY.views.xplore.open(r.session_path); },
        }) : null,
        r.run_id ? el('button', {
          class: 'mini', text: 'Run',
          title: 'Show the run that produced this: ' + r.run_id,
          onclick: () => { setView('history'); BARRY.views.history.reload(); },
        }) : null,
      ]),
    ]);
  }

  /* A figure exported by the GUI carries the run that made it, and that run
     carries enough to make it again. Anything else in Results -- a plot from
     a script, a file dropped in by hand -- has no recipe, so it gets no
     button rather than a button that cannot work. */
  function rebuildBtn(r) {
    if (!r.run_id || r.kind !== 'figure' || !BARRY.figrebuild) return null;
    return el('button', {
      class: 'mini', text: 'Rebuild',
      title: 'Check what this figure needs, then walk through remaking it',
      onclick: (e) => { e.stopPropagation(); BARRY.figrebuild.start(r.run_id); },
    });
  }

  function table(list) {
    const rows = list.map((r) => el('tr', {}, [
      el('td', {}, [el('button', {
        class: 'res-pick' + (selected.has(r.id) ? ' on' : ''),
        style: 'position:static',
        text: selected.has(r.id) ? '\u2713' : '+',
        title: 'Select',
        onclick: () => {
          if (selected.has(r.id)) selected.delete(r.id); else selected.add(r.id);
          render();
        },
      })]),
      el('td', {}, [el('button', {
        class: 'res-star' + (r.starred ? ' on' : ''),
        style: 'position:static',
        text: r.starred ? '\u2605' : '\u2606',
        onclick: () => curate(r, { starred: !r.starred }),
      })]),
      el('td', { class: 'nm' }, [el('a', {
        href: '#', text: r.title || r.name,
        onclick: (e) => { e.preventDefault(); preview(r); },
      })]),
      el('td', { text: r.type }),
      el('td', { text: r.session_label || '' }),
      el('td', { text: r.author || '' }),
      el('td', { text: (r.created || '').replace('T', ' ').slice(0, 16) }),
      el('td', { text: fmtBytes(r.bytes) }),
      el('td', { text: (r.tags || []).join(', ') }),
    ]));
    return el('div', { class: 'res-table-wrap' }, [
      el('table', { class: 'res-table' }, [
        el('thead', {}, [el('tr', {}, ['', '', 'Title', 'Type', 'Session', 'By',
                                       'Created', 'Size', 'Tags']
          .map((h) => el('th', { text: h })))]),
        el('tbody', {}, rows),
      ]),
    ]);
  }

  /* ---------- actions ---------- */
  async function curate(r, patch) {
    Object.assign(r, patch);
    render();
    try {
      await apiPost('/api/results/curate', Object.assign({ id: r.id }, patch));
      BARRY.refreshSync();
    } catch (e) {
      toast(e.message, 'err');
    }
  }

  function editTags(r) {
    const tagInput = el('input', {
      type: 'text', value: (r.tags || []).join(', '),
      placeholder: 'comma separated, e.g. figure 2, CNO, propagation',
    });
    const titleInput = el('input', { type: 'text', value: r.title || r.name });
    const notesArea = el('textarea', { rows: '4', value: r.notes || '',
      placeholder: 'What does this show? Why does it matter?' });

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Describe this result' }),
        el('span', { class: 'sub', text: r.name }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'field' }, [el('label', { text: 'Title' }), titleInput]),
        el('div', { class: 'field' }, [
          el('label', { text: 'Tags' }), tagInput,
          el('span', { class: 'hint', text: 'Tags become filters in this view.' }),
        ]),
        el('div', { class: 'field' }, [el('label', { text: 'Notes' }), notesArea]),
        el('div', { class: 'section-label', text: 'Provenance' }),
        provenance(r),
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        el('button', {
          class: 'btn', text: 'Save',
          onclick: () => {
            const tags = tagInput.value.split(',').map((t) => t.trim()).filter(Boolean);
            closeModal();
            curate(r, { title: titleInput.value.trim() || r.name,
                        tags, notes: notesArea.value });
          },
        }),
      ]),
    ]));
  }

  function provenance(r) {
    const kv = el('dl', { class: 'kv' });
    const add = (k, v) => {
      if (v === null || v === undefined || v === '') return;
      kv.appendChild(el('dt', { text: k }));
      kv.appendChild(el('dd', { text: typeof v === 'object' ? JSON.stringify(v) : String(v) }));
    };
    add('File', r.path);
    add('Kind', r.kind);
    add('Made by', r.author);
    add('Machine', r.machine);
    add('Created', r.created);
    add('Session', r.session_label);
    add('Run id', r.run_id);
    if (r.parameters && Object.keys(r.parameters).length) {
      add('Parameters', r.parameters);
    }
    if ((r.panels || []).length) {
      add('Panels', r.panels.map((p) => p.panel).join(', '));
    }
    return kv;
  }

  function preview(r) {
    const body = r.type === 'image'
      ? el('img', { src: fileUrl(r), alt: '', class: 'res-full' })
      : (r.type === 'pdf'
          ? el('iframe', { src: fileUrl(r), class: 'res-frame' })
          : el('div', { class: 'tree-empty',
              text: 'No inline preview for ' + r.ext + '. Open or reveal it instead.' }));

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: r.title || r.name }),
        el('span', { class: 'sub', text: [r.session_label, r.author].filter(Boolean).join('  ·  ') }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
      el('div', { class: 'mb res-preview' }, [body]),
      el('div', { class: 'mf' }, [
        el('button', { class: 'btn ghost sm', text: 'Tag / describe',
          onclick: () => { closeModal(); editTags(r); } }),
        el('button', { class: 'btn ghost sm', text: 'Reveal',
          onclick: () => apiPost('/api/results/reveal', { id: r.id }).catch(() => {}) }),
        el('button', { class: 'btn ghost sm', text: 'Download',
          onclick: () => window.open(fileUrl(r, true), '_blank') }),
        r.run_id && r.kind === 'figure' && BARRY.figrebuild
          ? el('button', {
              class: 'btn ghost sm', text: 'Rebuild…',
              title: 'Check what this figure needs, then walk through '
                   + 'remaking it',
              onclick: () => { closeModal(); BARRY.figrebuild.start(r.run_id); },
            })
          : null,
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn', text: 'Add to storyboard',
          onclick: () => {
            closeModal();
            setView('storyboard');
            BARRY.views.storyboard.addResults([r]);
          } }),
      ]),
    ]));
  }

  /* ---------- init ---------- */
  function init() {
    $('#resRefresh').addEventListener('click', () => load(true));
    $('#resOpenDir').addEventListener('click', () => {
      if (meta.outputs_dir) apiPost('/api/reveal', { path: meta.outputs_dir }).catch(() => {});
    });
    $('#resGithub').addEventListener('click', () => {
      if (meta.github) window.open(meta.github, '_blank');
      else toast('No GitHub remote is configured for this repo.', 'err');
    });
    $('#resManifest').addEventListener('click', () => {
      BARRY.download('/api/results/manifest',
                     { ids: Array.from(selected) }, 'results-manifest.csv');
    });

    document.addEventListener('keydown', (e) => {
      if (BARRY.state.view !== 'results') return;
      if (isTyping(e)) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
        e.preventDefault();
        for (const r of visible()) selected.add(r.id);
        render();
      } else if (e.key === 'Escape' && selected.size) {
        selected.clear();
        render();
      }
    });
  }

  return {
    init,
    onShow: () => load(false),
    reload: () => load(true),
    all: () => items,
    urlFor: fileUrl,
    /* Jump here with a search already applied -- used by History's
       "show in Results". */
    search: (q) => { query = q || ''; view = 'grid'; render(); },
  };
})();
