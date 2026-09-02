/* ==========================================================================
   explorer.js -- browse and run any single script in the repo.

   The repo's Python scripts have no CLI: their top-level constants are the
   interface. We surface those as form fields and only send back the ones the
   user actually edited, so an untouched script runs byte-for-byte as-is.
   ========================================================================== */
'use strict';

BARRY.views.explorer = (function () {
  let current = null;           // {rel, lang, params, ...}
  let edits = {};               // name -> value (only what changed)
  let filterLang = 'all';
  let query = '';
  let showSource = false;
  let sourceQuery = '';
  let presets = [];                 // per-script parameter sets, synced
  const openSections = new Set(['IED Pipeline']);
  const PSEUDO = ['\u2605 Favourites', 'Recent'];

  /* ---------- tree ---------- */
  function items() {
    const cat = BARRY.state.catalog;
    if (!cat) return [];
    const q = query.trim().toLowerCase();
    return cat.items.filter((it) => {
      if (filterLang !== 'all' && it.lang !== filterLang) return false;
      if (!q) return true;
      return it.rel.toLowerCase().includes(q) || it.name.toLowerCase().includes(q);
    });
  }

  /* ======================================================================
     Feature 1 -- Favourites and recents
     420 indexed scripts means the six people actually use are buried. Both
     lists live in preferences, so they follow the person, not the machine.
     ====================================================================== */
  function favs() { return BARRY.prefs.get('fav_scripts', []) || []; }
  function recents() { return BARRY.prefs.get('recent_scripts', []) || []; }

  function toggleFav(rel) {
    const added = BARRY.prefs.toggleIn('fav_scripts', rel);
    BARRY.activity.log('script.favourite', { rel, on: added });
    renderTree();
  }

  function noteRecent(rel) {
    const list = recents().filter((r) => r !== rel);
    list.unshift(rel);
    BARRY.prefs.set('recent_scripts', list.slice(0, 12));
  }

  function renderTree() {
    const host = $('#scriptTree');
    host.innerHTML = '';
    const list = items();

    $('#explorerSub').textContent =
      list.length + ' of ' + (BARRY.state.catalog ? BARRY.state.catalog.items.length : 0) +
      ' scripts' + (query ? ' matching "' + query + '"' : '');

    if (!list.length) {
      host.appendChild(el('div', { class: 'tree-empty', text: 'Nothing matches that search.' }));
      return;
    }

    const bySection = new Map();
    for (const it of list) {
      if (!bySection.has(it.section)) bySection.set(it.section, []);
      bySection.get(it.section).push(it);
    }

    // Keep IED first and Misc last, matching the sidebar's mental model.
    const names = Array.from(bySection.keys()).sort((a, b) => {
      const rank = (n) => (n === 'IED Pipeline' ? 0 : n === 'Misc' ? 2 : 1);
      return rank(a) - rank(b) || a.localeCompare(b);
    });

    // Favourites and recents ride above the real sections. They are views
    // onto the same items, so a search filters them too.
    const byRel = new Map(list.map((it) => [it.rel, it]));
    const favItems = favs().map((r) => byRel.get(r)).filter(Boolean);
    const recItems = recents().map((r) => byRel.get(r))
                              .filter((it) => it && favs().indexOf(it.rel) < 0);
    if (favItems.length) { bySection.set(PSEUDO[0], favItems); names.unshift(PSEUDO[0]); }
    if (recItems.length) { bySection.set(PSEUDO[1], recItems); names.splice(favItems.length ? 1 : 0, 0, PSEUDO[1]); }
    openSections.add(PSEUDO[0]);

    // A search should reveal its hits rather than make the user expand folders.
    const forceOpen = !!query;

    for (const name of names) {
      const group = bySection.get(name);
      const open = forceOpen || openSections.has(name);
      const section = el('div', { class: 'tree-section' + (open ? ' open' : '') });

      section.appendChild(el('button', {
        class: 'tree-head',
        onclick: () => {
          if (openSections.has(name)) openSections.delete(name);
          else openSections.add(name);
          renderTree();
        },
      }, [
        el('span', { class: 'caret', html: '<svg viewBox="0 0 20 20"><path d="m8 5 5 5-5 5"/></svg>' }),
        el('span', { text: name }),
        el('span', { class: 'count', text: String(group.length) }),
      ]));

      const box = el('div', { class: 'tree-items' });
      for (const it of group) {
        const on = favs().indexOf(it.rel) >= 0;
        box.appendChild(el('div', {
          class: 'tree-item' + (current && current.rel === it.rel ? ' active' : ''),
          title: it.rel,
          onclick: (e) => { if (!e.target.closest('.tree-fav')) select(it.rel); },
        }, [
          el('span', { class: 'lang-dot ' + it.lang }),
          el('span', { class: 'nm', text: it.name }),
          it.archived ? el('span', { class: 'arch', text: 'archive' }) : null,
          el('button', {
            class: 'tree-fav' + (on ? ' on' : ''), text: on ? '\u2605' : '\u2606',
            title: on ? 'Remove from favourites' : 'Add to favourites',
            onclick: (e) => { e.stopPropagation(); toggleFav(it.rel); },
          }),
        ]));
      }
      section.appendChild(box);
      host.appendChild(section);
    }
  }

  /* ---------- detail ---------- */
  async function select(rel) {
    edits = {};
    showSource = false;
    let data;
    try {
      data = await api('/api/script?source=1&rel=' + encodeURIComponent(rel));
    } catch (e) {
      toast(e.message, 'err');
      return;
    }
    current = data;
    noteRecent(rel);
    await loadPresets(rel);
    renderTree();
    renderDetail();
  }

  function renderDetail() {
    const host = $('#scriptDetail');
    host.innerHTML = '';
    if (!current) return;

    const it = current.item || {};
    const runnable = current.lang === 'python' || current.lang === 'matlab';
    const matlabMissing = current.lang === 'matlab' &&
      !(BARRY.state.catalog && BARRY.state.catalog.matlab);

    host.appendChild(el('div', { class: 'detail-head' }, [
      el('div', {}, [
        el('h2', { text: it.name || baseName(current.rel) }),
        el('p', { class: 'detail-path', text: current.rel }),
        el('div', { class: 'detail-tags' }, [
          el('span', { class: 'tag lang', text: current.lang }),
          it.section ? el('span', { class: 'tag opt', text: it.section }) : null,
          it.archived ? el('span', { class: 'tag blocked', text: 'archived' }) : null,
          it.size ? el('span', { class: 'tag opt', text: fmtBytes(it.size) }) : null,
        ]),
      ]),
      el('div', { class: 'head-actions' }, [
        el('button', {
          class: 'btn ghost sm', text: 'Reveal',
          onclick: () => apiPost('/api/reveal', { path: current.abspath }).catch(() => {}),
        }),
        el('button', {
          class: 'btn ghost sm',
          text: showSource ? 'Hide source' : 'View source',
          onclick: () => { showSource = !showSource; renderDetail(); },
        }),
        el('button', {
          class: 'btn ghost sm', text: 'Copy command',
          title: 'The exact command line that reproduces this run outside BARRY',
          onclick: () => BARRY.copy(runCommand(), 'Command'),
        }),
        el('button', {
          class: 'tree-fav' + (favs().indexOf(current.rel) >= 0 ? ' on' : ''),
          text: favs().indexOf(current.rel) >= 0 ? '\u2605' : '\u2606',
          title: 'Favourite',
          style: 'font-size:15px;padding:0 6px',
          onclick: () => { toggleFav(current.rel); renderDetail(); },
        }),
      ]),
    ]));

    const desc = (current.description || '').trim();
    host.appendChild(el('div', {
      class: 'desc-box' + (desc ? '' : ' none'),
      text: desc || 'This script carries no header comment or docstring.',
    }));

    const extra = current.extra || {};
    if (extra.parse_error) {
      host.appendChild(el('div', {
        class: 'stat-chip warn',
        text: 'Python could not parse this file (' + extra.parse_error + '), so its ' +
              'settings cannot be edited here. It can still be run as-is.',
      }));
    }

    /* -- parameters -- */
    const params = current.params || [];
    if (params.length) {
      host.appendChild(el('div', {
        class: 'section-label',
        text: current.lang === 'matlab' ? 'Function arguments' : 'Settings (top-level constants)',
      }));

      host.appendChild(presetRow());
      const grid = el('div', { class: 'param-grid' });
      for (const p of params) grid.appendChild(paramField(p));
      host.appendChild(grid);
    } else if (runnable) {
      host.appendChild(el('div', {
        class: 'section-label',
        text: current.lang === 'matlab' ? 'Takes no arguments' : 'No editable settings found',
      }));
    }

    /* -- run bar -- */
    const bar = el('div', { class: 'run-bar' });
    if (runnable) {
      bar.appendChild(el('button', {
        class: 'btn', text: 'Run script',
        disabled: matlabMissing ? 'disabled' : null,
        onclick: run,
      }));
    }
    if (Object.keys(edits).length) {
      bar.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Reset changes',
        onclick: () => { edits = {}; renderDetail(); },
      }));
      bar.appendChild(el('span', {
        class: 'note',
        text: Object.keys(edits).length + ' setting(s) overridden — the original file is not modified.',
      }));
    } else if (current.lang === 'python' && params.length) {
      bar.appendChild(el('span', {
        class: 'note', text: 'Runs exactly as written unless you change something above.',
      }));
    }
    if (matlabMissing) {
      bar.appendChild(el('span', { class: 'note', text: 'MATLAB was not found on this machine.' }));
    }
    if (current.lang === 'notebook') {
      bar.appendChild(el('span', {
        class: 'note',
        text: 'Notebooks are indexed for reference; open them in Jupyter or VS Code to run.',
      }));
    }
    host.appendChild(bar);

    /* -- extras -- */
    if (extra.functions && extra.functions.length) {
      host.appendChild(el('div', { class: 'section-label', text: 'Functions' }));
      host.appendChild(el('div', { class: 'detail-tags' },
        extra.functions.map((f) => el('span', { class: 'tag opt', text: f }))));
    }
    if (extra.imports && extra.imports.length) {
      host.appendChild(el('div', { class: 'section-label', text: 'Imports' }));
      host.appendChild(el('div', { class: 'detail-tags' },
        extra.imports.map((f) => el('span', { class: 'tag opt', text: f }))));
    }

    if (showSource) host.appendChild(sourceBlock());
  }

  /* ======================================================================
     Feature 2 -- Searchable source, with the line numbers people quote
     ====================================================================== */
  function sourceBlock() {
    const src = current.source || '';
    const lines = src.split(/\r?\n/);
    const q = sourceQuery.trim().toLowerCase();
    const hits = q ? lines.reduce((n, ln, i) =>
      (ln.toLowerCase().includes(q) ? n.concat(i + 1) : n), []) : [];

    const pre = el('pre', { class: 'src-lines' });
    lines.forEach((ln, i) => {
      const n = i + 1;
      const hit = q && ln.toLowerCase().includes(q);
      pre.appendChild(el('span', {
        class: 'src-line' + (hit ? ' hit' : ''),
        id: 'srcL' + n,
        text: String(n).padStart(4, ' ') + '  ' + ln + '\n',
      }));
    });

    return el('div', {}, [
      el('div', { class: 'sec-head' }, [
        el('div', { class: 'section-label',
                    text: 'Source \u00b7 ' + lines.length + ' lines' }),
        el('div', { class: 'spacer' }),
        el('div', { class: 'search-wrap inline', style: 'max-width:260px' }, [
          el('svg', { class: 'search-icon', viewBox: '0 0 20 20',
                      html: '<circle cx="9" cy="9" r="6"/><path d="m14 14 4 4"/>' }),
          el('input', {
            type: 'search', placeholder: 'Find in this file\u2026',
            value: sourceQuery,
            oninput: (e) => {
              sourceQuery = e.target.value;
              renderDetail();
              const first = $('.src-line.hit');
              if (first) first.scrollIntoView({ block: 'center' });
            },
          }),
        ]),
        el('span', { class: 'hint',
                     text: q ? hits.length + ' line(s)' : '' }),
      ]),
      el('div', { class: 'source-box tall' }, [pre]),
    ]);
  }

  /* ======================================================================
     Feature 3 -- Per-script parameter presets and a copyable command
     The override machinery writes a temp sibling copy, so a saved preset is
     the only record of which numbers were used. Named sets make that record
     shareable, and the command line makes the run reproducible without the
     GUI at all.
     ====================================================================== */
  async function loadPresets(rel) {
    try {
      const d = await api('/api/presets/layouts');
      presets = (d.presets || []).filter(
        (x) => x.kind === 'script' && x.rel === rel);
    } catch (e) { presets = []; }
  }

  function presetRow() {
    const chips = presets.map((pre) => el('span', {
      class: 'coll-chip', title: JSON.stringify(pre.edits || {}, null, 1),
      onclick: () => {
        edits = Object.assign({}, pre.edits || {});
        renderDetail();
        toast('Applied "' + pre.name + '"', 'ok');
        BARRY.activity.log('script.preset.apply',
                           { rel: current.rel, name: pre.name });
      },
    }, [
      el('span', { text: pre.name }),
      el('span', {
        class: 'x', text: '\u00d7', title: 'Delete this preset',
        onclick: async (e) => {
          e.stopPropagation();
          try {
            await api('/api/presets/layouts', {
              method: 'DELETE', body: JSON.stringify({ id: pre.id }),
            });
            await loadPresets(current.rel);
            renderDetail();
          } catch (err) { toast(err.message, 'err'); }
        },
      }),
    ]));

    chips.push(el('button', {
      class: 'btn ghost sm',
      text: 'Save these settings\u2026',
      disabled: Object.keys(edits).length ? null : 'disabled',
      title: Object.keys(edits).length
        ? 'Name this set of overrides' : 'Change a setting first',
      onclick: async () => {
        const name = await askPath('Name this settings preset',
                                   'e.g. 40 uV, 3 ms refractory');
        if (!name) return;
        try {
          await apiPost('/api/presets/layouts', {
            preset: { kind: 'script', rel: current.rel, name,
                      edits: Object.assign({}, edits),
                      note: Object.keys(edits).length + ' override(s)' },
          });
          await loadPresets(current.rel);
          renderDetail();
          toast('Saved "' + name + '"', 'ok');
        } catch (e) { toast(e.message, 'err'); }
      },
    }));

    return el('div', { class: 'coll-row', style: 'margin-bottom:9px' }, chips);
  }

  /* The command BARRY itself would run, spelled out. For Python with edits
     it names the constants to change, since the real run uses a temp copy. */
  function runCommand() {
    if (!current) return '';
    const cat = BARRY.state.catalog || {};
    const abs = current.abspath || current.rel;
    const changed = Object.keys(edits);
    if (current.lang === 'matlab') {
      const args = (current.params || []).map((p) => {
        const v = Object.prototype.hasOwnProperty.call(edits, p.name)
          ? edits[p.name] : p.value;
        return typeof v === 'string' && !/^[-\d.]+$/.test(v)
          ? "'" + String(v).replace(/'/g, "''") + "'" : String(v);
      }).join(', ');
      const fn = baseName(current.rel).replace(/\.m$/i, '');
      return '"' + (cat.matlab || 'matlab') + '" -batch "cd(\''
             + abs.replace(/[\\/][^\\/]+$/, '') + "'); " + fn
             + (args ? '(' + args + ')' : '') + '"';
    }
    let cmd = '"' + (cat.python || 'python') + '" -u "' + abs + '"';
    if (changed.length) {
      cmd += '\n\n# BARRY overrides these top-level constants in a temp copy;\n'
           + '# to reproduce by hand, edit them in the file first:\n'
           + changed.map((k) => '#   ' + k + ' = '
                                + JSON.stringify(edits[k])).join('\n');
    }
    return cmd;
  }

  function paramField(p) {
    const changed = Object.prototype.hasOwnProperty.call(edits, p.name);
    const value = changed ? edits[p.name] : p.value;

    const row = el('div', { class: 'param-row' });

    if (p.type === 'bool') {
      const on = String(value).toLowerCase() === 'true' || value === true;
      row.appendChild(el('label', { class: 'toggle' + (on ? ' on' : '') }, [
        el('input', {
          type: 'checkbox', checked: on ? 'checked' : null,
          onchange: (e) => { edits[p.name] = e.target.checked; renderDetail(); },
        }),
        el('span', { text: on ? 'true' : 'false' }),
      ]));
    } else {
      const input = el('input', {
        type: 'text',
        value: value === null || value === undefined ? '' :
               (typeof value === 'object' ? JSON.stringify(value) : String(value)),
        oninput: (e) => {
          edits[p.name] = e.target.value;
          const box = e.target.closest('.param');
          if (box) box.classList.add('changed');
        },
      });
      row.appendChild(input);
      if (p.is_path) {
        row.appendChild(el('button', {
          class: 'browse-mini', text: '…', title: 'Browse for a path',
          onclick: async () => {
            const looksLikeFile = /\.\w{1,6}$/.test(String(value || ''));
            const picked = await pickPath(looksLikeFile ? 'file' : 'folder', '');
            if (picked) { edits[p.name] = picked; renderDetail(); }
          },
        }));
      }
    }

    return el('div', { class: 'param' + (changed ? ' changed' : '') }, [
      el('div', { class: 'param-top' }, [
        el('span', { class: 'pname', text: p.name }),
        el('span', { class: 'ptype', text: p.type }),
        p.required ? el('span', { class: 'req', text: 'required' }) : null,
        p.namevalue ? el('span', { class: 'ptype', text: 'name/value' }) : null,
      ]),
      row,
      p.comment ? el('div', { class: 'pcomment', text: p.comment }) : null,
    ]);
  }

  /* ---------- run ---------- */
  async function run() {
    if (!current) return;
    const params = (current.params || []).map((p) => {
      const changed = Object.prototype.hasOwnProperty.call(edits, p.name);
      return Object.assign({}, p, {
        value: changed ? edits[p.name] : p.value,
        changed,
      });
    });

    // A MATLAB function with a blank required argument would just error out.
    if (current.lang === 'matlab') {
      const blank = params.filter(
        (p) => p.required && !p.namevalue && String(p.value || '').trim() === '');
      if (blank.length) {
        toast('Fill in: ' + blank.map((p) => p.name).join(', '), 'err');
        return;
      }
    }

    try {
      const res = await apiPost('/api/run', {
        rel: current.rel, lang: current.lang, params, extra: current.extra || {},
      });
      LOG.attach(res.job.id, current.item ? current.item.name : baseName(current.rel));
    } catch (e) {
      toast(e.message, 'err');
    }
  }

  /* ---------- init ---------- */
  function init() {
    let debounce = null;
    $('#scriptSearch').addEventListener('input', (e) => {
      query = e.target.value;
      clearTimeout(debounce);
      debounce = setTimeout(renderTree, 110);
    });

    $$('#langFilter .pill').forEach((b) =>
      b.addEventListener('click', () => {
        filterLang = b.dataset.lang;
        $$('#langFilter .pill').forEach((x) => x.classList.toggle('active', x === b));
        renderTree();
      }));

    $('#reindex').addEventListener('click', async () => {
      try {
        const cat = await api('/api/catalog?refresh=1');
        BARRY.state.catalog = cat;
        renderTree();
        toast('Re-indexed ' + cat.items.length + ' scripts', 'ok');
      } catch (e) { toast(e.message, 'err'); }
    });

    renderTree();
  }

  return {
    init,
    select,
    onShow: renderTree,
    favourites: favs,
  };
})();
