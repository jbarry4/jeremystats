/* ==========================================================================
   misc.js -- the catch-all: loose scripts that fit no pipeline, plus the
   workbench utilities that keep the repo tidy.
   ========================================================================== */
'use strict';

BARRY.views.misc = (function () {

  function miscItems() {
    const cat = BARRY.state.catalog;
    if (!cat) return { loose: [], archived: [], notebooks: [] };
    const loose = cat.items.filter((i) => i.section === 'Misc' && !i.archived);
    const archived = cat.items.filter((i) => i.archived);
    const notebooks = cat.items.filter((i) => i.lang === 'notebook');
    return { loose, archived, notebooks };
  }

  function rowList(items, emptyText) {
    if (!items.length) {
      return el('div', { class: 'tree-empty', text: emptyText });
    }
    const box = el('div', { class: 'list-rows' });
    for (const it of items.slice(0, 300)) {
      box.appendChild(el('div', {
        class: 'list-row',
        title: it.rel,
        onclick: () => {
          setView('explorer');
          BARRY.views.explorer.select(it.rel);
        },
      }, [
        el('span', { class: 'lang-dot ' + it.lang }),
        el('span', { class: 'nm', text: it.name }),
        el('span', { class: 'pth', text: it.dir }),
      ]));
    }
    if (items.length > 300) {
      box.appendChild(el('div', {
        class: 'tree-empty',
        text: '…and ' + (items.length - 300) + ' more — use Explorer search.',
      }));
    }
    return box;
  }

  function render() {
    const host = $('#miscBody');
    host.innerHTML = '';
    const { loose, archived, notebooks } = miscItems();

    /* ---- utilities ---- */
    host.appendChild(el('div', { class: 'section-label', text: 'Workbench' }));
    const cards = el('div', { class: 'card-grid' });

    cards.appendChild(el('div', { class: 'card' }, [
      el('h3', { text: 'Re-index the repo' }),
      el('p', { text: 'Rescan every folder for new or renamed scripts. Run this after you add files.' }),
      el('div', { class: 'card-actions' }, [
        el('button', {
          class: 'btn sm', text: 'Re-index',
          onclick: async (e) => {
            e.target.disabled = true;
            try {
              const cat = await api('/api/catalog?refresh=1');
              BARRY.state.catalog = cat;
              render();
              if (BARRY.views.explorer.onShow) BARRY.views.explorer.onShow();
              toast('Indexed ' + cat.items.length + ' scripts', 'ok');
            } catch (err) { toast(err.message, 'err'); }
            e.target.disabled = false;
          },
        }),
      ]),
    ]));

    cards.appendChild(el('div', { class: 'card' }, [
      el('h3', { text: 'Clean temp run files' }),
      el('p', {
        text: 'Running a Python script with edited settings writes a short-lived copy ' +
              'beside the original. A crash can leave one behind — this sweeps them up.',
      }),
      el('div', { class: 'card-actions' }, [
        el('button', {
          class: 'btn ghost sm', text: 'Sweep now',
          onclick: async () => {
            try {
              const res = await apiPost('/api/cleanup');
              toast(res.removed ? 'Removed ' + res.removed + ' temp file(s)'
                                : 'Nothing to clean', 'ok');
            } catch (err) { toast(err.message, 'err'); }
          },
        }),
      ]),
    ]));

    cards.appendChild(el('div', { class: 'card' }, [
      el('h3', { text: 'Housekeeping' }),
      el('p', {
        text: 'Find __pycache__ folders, stray .pyc files, zero-byte exports '
            + 'and the largest files in the repo \u2014 then clear the '
            + 'clutter, with nothing else touched.',
      }),
      el('div', { class: 'card-actions' }, [
        el('button', { class: 'btn ghost sm', text: 'Scan\u2026',
                       onclick: housekeeping }),
      ]),
    ]));

    const cat = BARRY.state.catalog || {};
    cards.appendChild(el('div', { class: 'card' }, [
      el('h3', { text: 'Environment' }),
      el('p', {
        html: 'Python: <code>' + escapeHtml(shortPath(cat.python || '?')) + '</code><br>' +
              'MATLAB: <code>' + escapeHtml(cat.matlab ? shortPath(cat.matlab) : 'not found') + '</code><br>' +
              'Repo: <code>' + escapeHtml(shortPath(cat.repo || '?')) + '</code>',
      }),
      el('div', { class: 'card-actions' }, [
        el('button', {
          class: 'btn ghost sm', text: 'Open repo folder',
          onclick: () => apiPost('/api/reveal', { path: cat.repo }).catch(() => {}),
        }),
      ]),
    ]));

    host.appendChild(cards);

    /* ---- repo search ---- */
    host.appendChild(el('div', { class: 'section-label',
                                 text: 'Search the repo' }));
    host.appendChild(grepBlock());

    /* ---- scratch runner ---- */
    host.appendChild(el('div', { class: 'section-label',
                                 text: 'Scratch runner' }));
    host.appendChild(scratchBlock());

    /* ---- output gallery ---- */
    host.appendChild(el('div', { class: 'section-label', text: 'Output' }));
    const outHost = el('div', { id: 'outHost' }, [
      el('div', { class: 'tree-empty', text: 'Loading…' }),
    ]);
    host.appendChild(outHost);
    loadOutputs(outHost);

    /* ---- loose scripts ---- */
    host.appendChild(el('div', {
      class: 'section-label',
      text: 'Loose scripts — ' + loose.length + ' that belong to no project area',
    }));
    host.appendChild(rowList(loose, 'Nothing loose — every script sits in a project folder.'));

    /* ---- notebooks ---- */
    host.appendChild(el('div', {
      class: 'section-label',
      text: 'Notebooks — ' + notebooks.length + ' (indexed for reference)',
    }));
    host.appendChild(rowList(notebooks, 'No notebooks in the repo.'));

    /* ---- archives ---- */
    host.appendChild(el('div', {
      class: 'section-label',
      text: 'Archived / inactive — ' + archived.length,
    }));
    host.appendChild(rowList(archived, 'No archived scripts.'));
  }


  /* ======================================================================
     Feature 1 -- Repo search
     420 scripts, a lot of them near-duplicates of each other. "Where else do
     we compute the CSD?" is a question with a real answer, and grepping from
     a terminal loses the link back into the Explorer.
     ====================================================================== */
  let grepState = { pattern: '', regex: false, case: false, hits: null,
                    busy: false, info: '' };

  function grepBlock() {
    const box = el('div');
    const input = el('input', {
      type: 'search', value: grepState.pattern,
      placeholder: 'text or /regex/ to find in every .py, .m, .ipynb\u2026',
      onkeydown: (e) => { if (e.key === 'Enter') runGrep(input.value); },
    });

    box.appendChild(el('div', { class: 'grep-form' }, [
      el('div', { class: 'search-wrap inline' }, [
        el('svg', { class: 'search-icon', viewBox: '0 0 20 20',
                    html: '<circle cx="9" cy="9" r="6"/><path d="m14 14 4 4"/>' }),
        input,
      ]),
      el('label', { class: 'toggle sm' + (grepState.regex ? ' on' : '') }, [
        el('input', { type: 'checkbox', checked: grepState.regex ? 'checked' : null,
                      onchange: (e) => { grepState.regex = e.target.checked; } }),
        el('span', { text: 'regex' }),
      ]),
      el('label', { class: 'toggle sm' + (grepState.case ? ' on' : '') }, [
        el('input', { type: 'checkbox', checked: grepState.case ? 'checked' : null,
                      onchange: (e) => { grepState.case = e.target.checked; } }),
        el('span', { text: 'match case' }),
      ]),
      el('button', { class: 'btn sm', text: 'Search',
                     disabled: grepState.busy ? 'disabled' : null,
                     onclick: () => runGrep(input.value) }),
      grepState.info
        ? el('span', { class: 'hint', text: grepState.info })
        : null,
    ]));

    if (grepState.busy) {
      box.appendChild(loader('Searching', 'reading every script in the repo'));
      return box;
    }
    if (!grepState.hits) return box;
    if (!grepState.hits.length) {
      box.appendChild(el('div', { class: 'tree-empty', text: 'No matches.' }));
      return box;
    }

    const list = el('div', { class: 'grep-hits' });
    for (const h of grepState.hits) {
      list.appendChild(el('div', {
        class: 'grep-hit', title: h.rel + ':' + h.line,
        onclick: () => {
          setView('explorer');
          BARRY.views.explorer.select(h.rel);
        },
      }, [
        el('span', { class: 'f', text: h.rel }),
        el('span', { class: 'ln', text: String(h.line) }),
        el('span', { class: 'tx', text: h.text.trim() }),
      ]));
    }
    box.appendChild(list);
    return box;
  }

  async function runGrep(pattern) {
    grepState.pattern = (pattern || '').trim();
    if (!grepState.pattern) { toast('Type something to search for.', 'err'); return; }
    grepState.busy = true;
    grepState.hits = null;
    grepState.info = '';
    render();
    try {
      const res = await apiPost('/api/repo/grep', {
        pattern: grepState.pattern, regex: grepState.regex,
        case: grepState.case, limit: 400,
      });
      grepState.hits = res.hits || [];
      grepState.info = res.hits.length + ' hit(s) in ' + res.files
                     + ' file(s), ' + res.seconds + 's'
                     + (res.truncated ? ' (stopped early)' : '');
    } catch (e) {
      grepState.hits = [];
      grepState.info = e.message;
    }
    grepState.busy = false;
    render();
  }

  /* ======================================================================
     Feature 2 -- Scratch runner
     The "just check one thing" script. Runs as a normal job so its output
     lands in the log dock and its run is recorded like any other, with the
     repo and BARRY's own readers already importable.
     ====================================================================== */
  const SCRATCH_SEED = [
    '# nlx and csc are BARRY\'s own readers -- no MEX, no MATLAB needed.',
    'from backend import nlx',
    '',
    'folder = r"D:\\PTEN\\PTEN"',
    'print("files:", len(glob.glob(os.path.join(folder, "**", "*.ncs"),',
    '                             recursive=True)))',
  ].join('\n');

  let scratchState = { code: null, snippets: [], loaded: false };

  function scratchBlock() {
    const box = el('div', { class: 'scratch-wrap' });
    if (scratchState.code === null) {
      scratchState.code = BARRY.prefs.get('scratch_draft', SCRATCH_SEED);
    }
    if (!scratchState.loaded) loadSnippets();

    const area = el('textarea', {
      class: 'scratch-code', spellcheck: 'false',
      value: scratchState.code,
      oninput: (e) => {
        scratchState.code = e.target.value;
        // The draft survives a reload; nothing is more annoying than losing
        // the throwaway script you were halfway through.
        BARRY.prefs.set('scratch_draft', e.target.value);
      },
      onkeydown: (e) => {
        // A textarea would otherwise move focus out of the editor.
        if (e.key === 'Tab') {
          e.preventDefault();
          const t = e.target;
          const at = t.selectionStart;
          t.value = t.value.slice(0, at) + '    ' + t.value.slice(t.selectionEnd);
          t.selectionStart = t.selectionEnd = at + 4;
          scratchState.code = t.value;
        }
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
          e.preventDefault();
          runScratch();
        }
      },
    });
    box.appendChild(area);

    box.appendChild(el('div', { class: 'scratch-row' }, [
      el('button', { class: 'btn sm', text: 'Run  (ctrl+enter)',
                     onclick: runScratch }),
      el('button', { class: 'btn ghost sm', text: 'Save as\u2026',
                     onclick: saveSnippet }),
      el('button', {
        class: 'btn ghost sm', text: 'Reset',
        onclick: () => {
          scratchState.code = SCRATCH_SEED;
          BARRY.prefs.set('scratch_draft', SCRATCH_SEED);
          render();
        },
      }),
      el('span', { class: 'hint',
        text: 'The repo and BARRY\'s backend are on sys.path; os, sys, glob, '
            + 'json, math and numpy as np are already imported.' }),
    ]));

    if (scratchState.snippets.length) {
      box.appendChild(el('div', { class: 'coll-row' },
        scratchState.snippets.map((sn) => el('span', {
          class: 'coll-chip', title: sn.at,
          onclick: () => {
            scratchState.code = sn.code;
            BARRY.prefs.set('scratch_draft', sn.code);
            render();
          },
        }, [
          el('span', { text: sn.name }),
          el('span', {
            class: 'x', text: '\u00d7', title: 'Forget this snippet',
            onclick: async (e) => {
              e.stopPropagation();
              try {
                const res = await apiPost('/api/scratch/saved', { delete: sn.id });
                scratchState.snippets = res.snippets || [];
                render();
              } catch (err) { toast(err.message, 'err'); }
            },
          }),
        ]))));
    }
    return box;
  }

  async function loadSnippets() {
    scratchState.loaded = true;
    try {
      const res = await api('/api/scratch/saved');
      scratchState.snippets = res.snippets || [];
      if (scratchState.snippets.length) render();
    } catch (e) { /* nothing saved yet is the normal case */ }
  }

  async function saveSnippet() {
    const name = await askPath('Name this snippet', 'e.g. count ncs files');
    if (!name) return;
    try {
      const res = await apiPost('/api/scratch/saved',
                                { name, code: scratchState.code });
      scratchState.snippets = res.snippets || [];
      render();
      toast('Saved "' + name + '"', 'ok');
    } catch (e) { toast(e.message, 'err'); }
  }

  async function runScratch() {
    if (!String(scratchState.code || '').trim()) {
      toast('Nothing to run.', 'err');
      return;
    }
    try {
      const res = await apiPost('/api/scratch/run', { code: scratchState.code });
      LOG.attach(res.job.id, 'Scratch');
      toast('Running \u2014 output is in the dock below.', 'ok');
    } catch (e) { toast(e.message, 'err'); }
  }

  /* ======================================================================
     Feature 3 -- Housekeeping
     A repo with a hundred __pycache__ folders in it makes for a noisy git
     status and a slow scan. Deletion is deliberately narrow: only names that
     are unambiguously build clutter, only inside the repo, and only after
     the list has been shown.
     ====================================================================== */
  async function housekeeping() {
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [el('h3', { text: 'Housekeeping' })]),
      el('div', { class: 'mb' }, [loader('Scanning the repo', 'this takes a moment')]),
    ]));
    let d;
    try {
      d = await api('/api/housekeeping?big=25');
    } catch (e) {
      closeModal();
      toast(e.message, 'err');
      return;
    }

    const chosen = new Set((d.junk || []).map((j) => j.path));
    const emptyChosen = new Set();

    const listBox = (rows, picked, label) => {
      if (!rows.length) {
        return el('div', { class: 'hint', text: 'Nothing ' + label + '.' });
      }
      return el('div', { class: 'hk-list' }, rows.map((r) => el('div', {
        class: 'hk-row',
      }, [
        el('input', {
          type: 'checkbox', checked: picked.has(r.path) ? 'checked' : null,
          onchange: (e) => {
            if (e.target.checked) picked.add(r.path); else picked.delete(r.path);
          },
        }),
        el('span', { class: 'p', text: r.rel, title: r.path }),
        el('span', { class: 'b', text: fmtBytes(r.bytes) }),
      ])));
    };

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Housekeeping' }),
        el('span', { class: 'sub',
          text: fmtBytes(d.free_bytes) + ' free on this drive' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'hk-stats' }, [
          el('span', { class: 'stat-chip' + (d.junk_bytes ? ' warn' : ' good'),
            text: d.junk_count + ' clutter item(s), ' + fmtBytes(d.junk_bytes) }),
          el('span', { class: 'stat-chip',
            text: 'Output ' + fmtBytes(d.outputs_bytes) }),
          el('span', { class: 'stat-chip',
            text: 'GUI_logs ' + fmtBytes(d.logs_bytes) }),
          el('span', { class: 'stat-chip',
            text: d.big.length + ' file(s) over 25 MB' }),
        ]),

        el('div', { class: 'section-label',
          text: 'Build clutter \u2014 safe to remove, regenerated on demand' }),
        listBox(d.junk || [], chosen, 'to clean'),

        (d.empty || []).length ? el('div', { class: 'section-label',
          text: 'Zero-byte files in Output \u2014 exports that died mid-write' }) : null,
        (d.empty || []).length ? listBox(d.empty, emptyChosen, 'empty') : null,

        el('div', { class: 'section-label', text: 'Largest files' }),
        el('div', { class: 'hk-list' }, (d.big || []).map((r) => el('div', {
          class: 'hk-row',
        }, [
          el('span', {}),
          el('span', { class: 'p', text: r.rel, title: r.path }),
          el('span', { class: 'b', text: fmtBytes(r.bytes) }),
        ]))),
      ]),
      el('div', { class: 'mf' }, [
        el('span', { class: 'hint',
          text: 'Only __pycache__, .pyc/.pyo, .DS_Store, Thumbs.db and '
              + 'zero-byte Output files can be removed here.' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Close', onclick: closeModal }),
        el('button', {
          class: 'btn danger', text: 'Clean selected',
          onclick: async () => {
            const paths = Array.from(chosen).concat(Array.from(emptyChosen));
            if (!paths.length) { toast('Nothing ticked.', 'err'); return; }
            const ok = await BARRY.confirm(
              'Remove ' + paths.length + ' item(s)?',
              'They are deleted from disk. Python regenerates __pycache__ on '
              + 'its own, so this only costs a slightly slower first import.',
              'Clean them', true);
            if (!ok) return;
            try {
              const res = await apiPost('/api/housekeeping/clean', { paths });
              toast('Removed ' + res.removed.length + ' item(s), freed '
                    + fmtBytes(res.freed), 'ok', 6000);
              for (const f of (res.failed || [])) toast(f.error, 'err', 6000);
              closeModal();
            } catch (e) { toast(e.message, 'err'); }
          },
        }),
      ]),
    ]));
  }

  async function loadOutputs(host) {
    let data;
    try { data = await api('/api/outputs'); }
    catch (e) {
      host.innerHTML = '';
      host.appendChild(el('div', { class: 'stat-chip warn', text: e.message }));
      return;
    }

    host.innerHTML = '';
    const bar = el('div', { class: 'fb-stats', style: 'margin-bottom:10px' }, [
      el('span', { class: 'stat-chip', text: data.files.length + ' file(s)' }),
      el('code', { style: 'font-size:10.5px;color:var(--text-3)', text: data.dir }),
      el('button', {
        class: 'btn ghost sm', text: 'Open folder',
        onclick: () => apiPost('/api/reveal', { path: data.dir }).catch(() => {}),
      }),
      data.github ? el('button', {
        class: 'btn ghost sm', text: 'View on GitHub',
        title: data.github,
        onclick: () => window.open(data.github, '_blank'),
      }) : null,
      el('button', { class: 'btn ghost sm', text: 'Refresh',
                     onclick: () => loadOutputs(host) }),
    ]);
    host.appendChild(bar);

    if (!data.files.length) {
      host.appendChild(el('div', { class: 'tree-empty',
        text: 'Nothing exported yet. Figures saved from the figure builder land here.' }));
      return;
    }

    const grid = el('div', { class: 'out-grid' });
    for (const f of data.files) {
      const isImg = ['.png', '.jpg', '.jpeg', '.svg', '.gif'].includes(f.ext);
      const url = '/api/outputs/file?rel=' + encodeURIComponent(f.rel);
      grid.appendChild(el('div', { class: 'out-card' }, [
        el('div', { class: 'thumb' }, [
          isImg ? el('img', { src: url, alt: f.name, loading: 'lazy' })
                : el('span', { class: 'noimg',
                    text: (f.ext || '?').replace('.', '').toUpperCase() }),
        ]),
        el('div', { class: 'meta' }, [
          el('div', { class: 'nm', text: f.name }),
          el('div', { class: 'sub', text: fmtBytes(f.bytes) + '  ·  '
            + new Date(f.mtime * 1000).toLocaleString() }),
        ]),
        el('div', { class: 'acts' }, [
          el('button', { class: 'mini', text: 'Open',
                         onclick: () => window.open(url, '_blank') }),
          el('button', { class: 'mini', text: 'Reveal',
                         onclick: () => apiPost('/api/reveal', { path: f.path }).catch(() => {}) }),
          data.github ? el('button', {
            class: 'mini', text: 'GitHub',
            title: data.github + '/' + f.rel,
            onclick: () => window.open(data.github + '/' + f.rel, '_blank'),
          }) : null,
        ]),
      ]));
    }
    host.appendChild(grid);
  }

  function shortPath(p) {
    if (!p || p.length < 52) return p;
    return p.slice(0, 22) + '…' + p.slice(-26);
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  return {
    init: () => {},
    onShow: render,
    /* Entry points for the command palette. */
    focusGrep: () => {
      render();
      const box = $('#miscBody .grep-form input');
      if (box) { box.focus(); box.scrollIntoView({ block: 'center' }); }
    },
    focusScratch: () => {
      render();
      const box = $('#miscBody .scratch-code');
      if (box) { box.focus(); box.scrollIntoView({ block: 'center' }); }
    },
    housekeeping,
  };
})();
