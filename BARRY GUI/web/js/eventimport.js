/* ==========================================================================
   eventimport.js -- The event/timestamp import wizard.

   Opens any detector output, shows what the server detected and WHY, lets you
   correct the mapping when the guess is wrong, previews the result against the
   recording, and saves the whole mapping as a reusable named preset.
   ========================================================================== */
'use strict';

BARRY.eventImport = (function () {
  let sess = null;
  let onDone = null;
  let info = null;         // server inspection result
  let mapping = null;      // current (editable) mapping
  let preview = null;      // last apply result
  let presets = [];

  const UNITS = [
    ['samples', 'Sample indices (ets, Toothy idx)'],
    ['seconds', 'Seconds'],
    ['ms', 'Milliseconds'],
    ['us', 'Microseconds'],
  ];

  async function open(session, done) {
    sess = session;
    onDone = done;
    info = null; mapping = null; preview = null;

    try {
      const res = await api('/api/presets/imports');
      presets = res.presets || [];
    } catch (e) { presets = []; }

    const path = await pickPath('file', sess.path);
    if (!path) return;
    await inspect(path);
  }

  async function inspect(path) {
    showModal(loadingBody('Reading ' + baseName(path) + '…'));
    try {
      info = await apiPost('/api/events/inspect', {
        path,
        fs: sess.info.fs,
        n_samples: Math.round((sess.info.duration_s || 0) * sess.info.fs),
        duration_s: sess.info.duration_s,
      });
      mapping = Object.assign({}, info.suggestion || {});
      // Carry the table shape forward so apply reads the file the same way.
      if (info.kind === 'table') {
        mapping.has_header = info.has_header;
        mapping.delimiter = info.delimiter;
      }
      if (info.kind === 'excel') mapping.sheet = info.sheet;
      render();
      if (mapping.format) applyPreview();
    } catch (e) {
      showModal(errorBody(e.message, path));
    }
  }

  /* ---------- rendering ---------- */
  function render() {
    const conf = (mapping && mapping.confidence) || 'none';
    const box = el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Import events' }),
        el('span', { class: 'sub', text: baseName(info.path) }),
        el('div', { class: 'spacer' }),
        presets.length ? el('select', {
          title: 'Apply a saved import preset',
          onchange: (e) => { applyPreset(e.target.value); e.target.value = ''; },
        }, [el('option', { value: '', text: 'preset…' })].concat(
          presets.map((p) => el('option', { value: p.id, text: p.name })))) : null,
        el('button', { class: 'close-x', html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
                       onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [
        verdict(conf),
        el('div', { class: 'wiz-grid' }, [
          el('div', {}, mappingFields()),
          el('div', {}, [
            el('div', { class: 'section-label', text: 'What is in the file' }),
            filePreview(),
            el('div', { class: 'section-label', text: 'Result' }),
            resultBox(),
          ]),
        ]),
      ]),
      el('div', { class: 'mf' }, [
        el('button', { class: 'btn ghost sm', text: 'Save as preset',
                       onclick: savePreset }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        el('button', {
          class: 'btn', text: preview ? 'Use ' + preview.n + ' events' : 'Preview first',
          disabled: preview && preview.n ? null : 'disabled',
          onclick: commit,
        }),
      ]),
    ]);
    showModal(box);
  }

  function verdict(conf) {
    const why = (mapping && mapping.why) || 'Could not work out the format.';
    const label = { high: 'Detected', medium: 'Best guess', low: 'Uncertain',
                    none: 'Not recognized' }[conf] || 'Guess';
    return el('div', { class: 'wiz-verdict ' + conf }, [
      el('strong', { text: label + (mapping && mapping.format ? ': ' + mapping.format : '') }),
      el('span', { text: why }),
    ]);
  }

  function mappingFields() {
    const out = [];
    const isArray = info.kind.startsWith('mat') || info.kind === 'npy';

    out.push(el('div', { class: 'section-label', text: 'Mapping' }));

    if (isArray) {
      const vars = info.variables || [];
      out.push(field('Variable', el('select', {
        onchange: (e) => { mapping.variable = e.target.value; applyPreview(); },
      }, vars.map((v) => el('option', {
        value: v.name, text: v.name + '  ' + JSON.stringify(v.shape),
        selected: mapping.variable === v.name ? 'selected' : null,
      })))));

      out.push(field('Start column (0-based)', numInput(mapping.start_col != null ? mapping.start_col : 0,
        (v) => { mapping.start_col = v; applyPreview(); })));
      out.push(field('End column (blank = none)', numInput(mapping.end_col,
        (v) => { mapping.end_col = (v === '' || v === null) ? null : v; applyPreview(); }, true)));

      const chVars = [{ name: '', label: '(none)' }].concat(
        vars.map((v) => ({ name: v.name, label: v.name })));
      out.push(field('Channel variable', el('select', {
        onchange: (e) => { mapping.channel_var = e.target.value || null; applyPreview(); },
      }, chVars.map((v) => el('option', {
        value: v.name, text: v.label,
        selected: (mapping.channel_var || '') === v.name ? 'selected' : null,
      }))), 'ech is an event x channel logical; the first participating channel is used.'));
    } else {
      const cols = (info.columns || []).map((c) => c.name);
      const colSelect = (key, label, allowNone, hint) =>
        out.push(field(label, el('select', {
          onchange: (e) => { mapping[key] = e.target.value || null; applyPreview(); },
        }, (allowNone ? [el('option', { value: '', text: '(none)' })] : []).concat(
          cols.map((c) => el('option', {
            value: c, text: c,
            selected: (mapping[key] || '') === c ? 'selected' : null,
          })))), hint));

      colSelect('start_col', 'Event time column', false);
      colSelect('end_col', 'End column', true);
      colSelect('channel_col', 'Channel column', true);
      colSelect('label_col', 'Label column', true);
      colSelect('valid_col', 'Keep-only column', true,
                'Rows are kept only where this column equals the value below.');
      if (mapping.valid_col) {
        out.push(field('Keep value', el('input', {
          type: 'text', value: String(mapping.valid_value != null ? mapping.valid_value : 1),
          onchange: (e) => { mapping.valid_value = e.target.value; applyPreview(); },
        })));
      }
    }

    out.push(field('Units', el('select', {
      onchange: (e) => { mapping.units = e.target.value; applyPreview(); },
    }, UNITS.map(([v, t]) => el('option', {
      value: v, text: t, selected: mapping.units === v ? 'selected' : null,
    }))), 'Sampling rate is ' + Math.round(sess.info.fs) + ' Hz; the recording is '
        + fmtTime(sess.info.duration_s) + ' long.'));

    return out;
  }

  function field(label, control, hint) {
    return el('div', { class: 'field' }, [
      el('label', { text: label }),
      control,
      hint ? el('span', { class: 'hint', text: hint }) : null,
    ]);
  }

  function numInput(value, onchange, allowBlank) {
    return el('input', {
      type: 'number', step: '1',
      value: value === null || value === undefined ? '' : String(value),
      onchange: (e) => {
        const raw = e.target.value.trim();
        if (raw === '' && allowBlank) return onchange('');
        onchange(parseInt(raw, 10) || 0);
      },
    });
  }

  function filePreview() {
    if (info.columns && info.columns.length) {
      const cols = info.columns.slice(0, 8);
      const rows = Math.min(6, Math.max(...cols.map((c) => (c.preview || []).length)));
      const table = el('table', { class: 'preview-table' }, [
        el('thead', {}, [el('tr', {}, cols.map((c) => el('th', { text: c.name })))]),
        el('tbody', {}, Array.from({ length: rows }, (_, r) =>
          el('tr', {}, cols.map((c) => el('td', { text: String((c.preview || [])[r] ?? '') }))))),
      ]);
      return el('div', { class: 'preview-wrap' }, [table]);
    }
    const vars = info.variables || [];
    return el('div', { class: 'preview-wrap' }, [
      el('table', { class: 'preview-table' }, [
        el('thead', {}, [el('tr', {}, [
          el('th', { text: 'variable' }), el('th', { text: 'shape' }),
          el('th', { text: 'dtype' }), el('th', { text: 'first values' })])]),
        el('tbody', {}, vars.map((v) => el('tr', {}, [
          el('td', { text: v.name }),
          el('td', { text: JSON.stringify(v.shape) }),
          el('td', { text: v.dtype }),
          el('td', { text: (v.preview || []).slice(0, 4).join(', ') }),
        ]))),
      ]),
    ]);
  }

  function resultBox() {
    if (!preview) {
      return el('div', { class: 'tree-empty', text: 'Adjust the mapping to preview.' });
    }
    const warn = (preview.warnings || []).map((w) =>
      el('div', { class: 'stat-chip warn', style: 'display:block;margin-top:6px;white-space:normal;line-height:1.5', text: w }));

    const first = preview.events.slice(0, 8);
    return el('div', {}, [
      el('div', { class: 'fb-stats', style: 'margin-bottom:8px' }, [
        el('span', { class: 'stat-chip good', text: preview.n + ' events' }),
        el('span', { class: 'stat-chip', text: 'read as ' + preview.units_used }),
        preview.span ? el('span', { class: 'stat-chip',
          text: fmtTime(preview.span[0]) + ' → ' + fmtTime(preview.span[1]) }) : null,
      ]),
      el('div', { class: 'preview-wrap' }, [
        el('table', { class: 'preview-table' }, [
          el('thead', {}, [el('tr', {}, [
            el('th', { text: '#' }), el('th', { text: 'start (s)' }),
            el('th', { text: 'end (s)' }), el('th', { text: 'channel' }),
            el('th', { text: 'label' })])]),
          el('tbody', {}, first.map((e, i) => el('tr', {}, [
            el('td', { text: String(i + 1) }),
            el('td', { text: e.start.toFixed(4) }),
            el('td', { text: e.end != null ? e.end.toFixed(4) : '—' }),
            el('td', { text: e.channel != null ? String(e.channel) : '—' }),
            el('td', { text: e.label || '—' }),
          ]))),
        ]),
      ]),
      ...warn,
    ]);
  }

  /* ---------- actions ---------- */
  let previewTimer = null;
  function applyPreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(doApplyPreview, 120);
  }

  async function doApplyPreview() {
    try {
      preview = await apiPost('/api/events/apply', {
        path: info.path, mapping, fs: sess.info.fs,
        n_samples: Math.round((sess.info.duration_s || 0) * sess.info.fs),
        duration_s: sess.info.duration_s,
      });
    } catch (e) {
      preview = null;
      render();
      toast(e.message, 'err', 7000);
      return;
    }
    render();
  }

  function applyPreset(id) {
    const p = presets.find((x) => x.id === id);
    if (!p) return;
    // Keep the file-shape fields discovered by inspection; take the rest.
    const keep = { has_header: mapping.has_header, delimiter: mapping.delimiter,
                   sheet: mapping.sheet };
    mapping = Object.assign({}, p, keep);
    delete mapping.id; delete mapping.name; delete mapping.saved;
    applyPreview();
    toast('Applied preset "' + p.name + '"', 'ok');
  }

  async function savePreset() {
    const name = await askPath('Name this import preset',
                               'e.g. "Toothy DS" or "Kleen ets"');
    if (!name) return;
    const body = Object.assign({}, mapping, { name });
    delete body.confidence; delete body.why;
    try {
      const res = await apiPost('/api/presets/imports', { preset: body });
      presets = res.presets || [];
      render();
      toast('Saved import preset "' + name + '" to GUI_logs', 'ok');
      BARRY.refreshSync();
    } catch (e) {
      toast(e.message, 'err');
    }
  }

  function commit() {
    if (!preview || !preview.n) return;
    closeModal();
    if (onDone) onDone(preview.events, {
      path: info.path, mapping,
      n: preview.n, units: preview.units_used,
    });
    toast('Loaded ' + preview.n + ' events from ' + baseName(info.path), 'ok');
  }

  /* ---------- modal plumbing ---------- */
  function loadingBody(text) {
    return el('div', {}, [
      el('div', { class: 'mh' }, [el('h3', { text: 'Import events' })]),
      el('div', { class: 'mb' }, [
        el('div', { style: 'display:flex;align-items:center;gap:12px;padding:22px' }, [
          el('span', { class: 'spin' }), el('span', { text }),
        ]),
      ]),
    ]);
  }

  function errorBody(msg, path) {
    return el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Could not read that file' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
                       onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { style: 'font-family:var(--mono);font-size:11px;color:var(--text-3)', text: path }),
        el('div', { class: 'wiz-verdict low' }, [el('span', { text: msg })]),
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn', text: 'Close', onclick: closeModal }),
      ]),
    ]);
  }

  return { open };
})();

/* Shared modal helpers used by the wizard and the figure builder. */
/* One modal slot, but layers.

   There is a single box, and showing a dialog used to wipe it. That is fine
   until a dialog opens another one -- the import wizard opening the bank
   browser, say. The wizard's nodes were destroyed, the code that opened the
   browser was still holding references into them, and when the browser
   handed its answer back that code wrote into elements no longer in the
   document. No error, no dialog, nothing imported.

   So a modal opened while one is up is a layer on top of it. Closing pops
   back to what was underneath; closing the last one hides the box. Nodes are
   moved rather than re-created, so listeners and references survive. */
const _modalStack = [];

function showModal(node) {
  const host = $('#bigModalBox');
  const shell = $('#bigModal');
  if (!shell.classList.contains('hidden') && host.firstChild) {
    const keep = document.createElement('div');
    while (host.firstChild) keep.appendChild(host.firstChild);
    _modalStack.push(keep);
  }
  host.innerHTML = '';
  host.appendChild(node);
  shell.classList.remove('hidden');
}

function closeModal() {
  const host = $('#bigModalBox');
  const shell = $('#bigModal');
  while (host.firstChild) host.removeChild(host.firstChild);
  const back = _modalStack.pop();
  if (back) {
    while (back.firstChild) host.appendChild(back.firstChild);
    shell.classList.remove('hidden');
    return;
  }
  shell.classList.add('hidden');
}

/* Dismiss everything, for the cases that really do mean "get all of this off
   my screen" -- leaving a view, or finishing a flow from inside a nested
   dialog. */
function closeAllModals() {
  _modalStack.length = 0;
  const host = $('#bigModalBox');
  while (host.firstChild) host.removeChild(host.firstChild);
  $('#bigModal').classList.add('hidden');
}
