/* ==========================================================================
   figure.js -- The figure builder: preview before you download.

   A layout is a grid of panels. You set the page size, drop panels into cells,
   retitle them, pick colormaps, fill in the metadata block, and see the real
   rendered figure before committing to a PNG/PDF/SVG.

   The preview is produced by the same matplotlib code that does the export, so
   what you see is exactly what you get -- not an approximation.
   ========================================================================== */
'use strict';

BARRY.figure = (function () {
  let XF = null;
  let sess = null;
  let layout = null;
  let selected = 0;
  let panelDefs = [];
  let colormaps = [];
  let pages = [];
  let rendering = false;
  let pendingRender = false;

  async function open(xfState, session) {
    XF = xfState;
    sess = session;

    if (!panelDefs.length) {
      try {
        const d = await api('/api/panels');
        panelDefs = d.panels || [];
        colormaps = d.colormaps || [];
        pages = d.pages || [];
      } catch (e) { /* fall back to defaults */ }
    }

    layout = buildInitialLayout();
    selected = 0;
    render();
    schedulePreview();
  }

  function buildInitialLayout() {
    const now = new Date();
    const sys = (BARRY.state.catalog && BARRY.state.catalog.system) || {};
    // Seed from what is already on screen, so the builder opens showing the
    // panes you were just looking at.
    const seeds = (XF.panes || []).filter((p) => p && XF.sessions[p.sessionId]
                                            && p.panel !== 'video' && p.panel !== 'tracking');
    const panels = (seeds.length ? seeds : [{ panel: 'traces', sessionId: sess.id }])
      .slice(0, 4).map((p, i) => ({
        panel: p.panel || 'traces',
        session_id: p.sessionId,
        title: labelFor(p.panel || 'traces'),
        row: i === 0 ? 0 : 1, col: i === 0 ? 0 : (i - 1) % 2,
        // 1x1 by default. A panel that silently claims two cells is
        // surprising, and there was no obvious way to give the span back.
        rowspan: 1, colspan: 1,
        cmap: p.cmap || 'jet',
        channel: p.channel,
        fmin: p.fmin, fmax: p.fmax,
      }));

    return {
      title: sess.identity.label || sess.info.name,
      subtitle: '',
      page: 'letter_landscape',
      width_in: 11, height_in: 8.5, dpi: 300,
      rows: Math.max(...panels.map((p) => p.row + p.rowspan), 1),
      cols: 2,
      t0: r6(sess.t0), t1: r6(sess.t0 + sess.span),
      highpass: sess.hp, lowpass: sess.lp, notch: sess.notch,
      cmap: 'jet', spacing_um: sess.spacing,
      channels: Array.from(sess.sel).sort((a, b) => a - b),
      bad_channels: Array.from(sess.bad),
      events: sess.events,
      gain: sess.gain,
      show_metadata: true,
      identity: sess.identity,
      session_label: sess.identity.label,
      metadata: {
        author: gitUser(),
        date: now.toLocaleString(),
        machine: sys.hostname || '',
        source_path: sess.path,
        notes: '',
      },
      panels,
    };
  }

  // Floating-point accumulation makes t0+span print as 2.19999999999; the
  // extra digits are noise, not precision.
  function r6(v) { return Math.round(v * 1e6) / 1e6; }

  function gitUser() {
    const sys = (BARRY.state.catalog && BARRY.state.catalog.system) || {};
    return sys.user || '';
  }

  function labelFor(id) {
    const d = panelDefs.find((p) => p.id === id);
    return d ? d.name : id;
  }

  /* ==================================================================
     Render the builder
     ================================================================== */
  function render() {
    const box = el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Figure builder' }),
        el('span', { class: 'sub', text: layout.panels.length + ' panel(s) · '
                     + layout.rows + '×' + layout.cols }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
                       onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'fig-layout' }, [
          leftColumn(), centerColumn(), rightColumn(),
        ]),
      ]),
      el('div', { class: 'mf' }, [
        el('span', { class: 'note', id: 'figNote',
                     style: 'font-size:11.5px;color:var(--text-3)' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost sm', text: 'Save layout',
                       onclick: saveLayout }),
        el('button', { class: 'btn ghost', text: 'Close', onclick: closeModal }),
        el('button', { class: 'btn ghost', text: 'SVG', onclick: () => download('svg') }),
        el('button', { class: 'btn ghost', text: 'PDF', onclick: () => download('pdf') }),
        el('button', { class: 'btn', text: 'PNG', onclick: () => download('png') }),
      ]),
    ]);
    showModal(box);
  }

  /* ---------- left: page + panels ---------- */
  function leftColumn() {
    const col = el('div', { class: 'fig-col' });

    col.appendChild(el('div', { class: 'section-label', style: 'margin-top:0', text: 'Page' }));
    col.appendChild(field('Preset', el('select', {
      onchange: (e) => {
        const p = pages.find((x) => x.id === e.target.value);
        layout.page = e.target.value;
        if (p) { layout.width_in = p.w; layout.height_in = p.h; }
        render(); schedulePreview();
      },
    }, pages.map((p) => el('option', {
      value: p.id, text: p.id.replace(/_/g, ' ') + '  (' + p.w + '×' + p.h + '")',
      selected: layout.page === p.id ? 'selected' : null,
    })))));

    col.appendChild(el('div', { style: 'display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px' }, [
      field('Width in', num(layout.width_in, 0.5, (v) => {
        layout.width_in = v; layout.page = ''; schedulePreview();
      })),
      field('Height in', num(layout.height_in, 0.5, (v) => {
        layout.height_in = v; layout.page = ''; schedulePreview();
      })),
      field('DPI', num(layout.dpi, 50, (v) => { layout.dpi = v; })),
    ]));

    col.appendChild(el('div', { style: 'display:grid;grid-template-columns:1fr 1fr;gap:8px' }, [
      field('Rows', num(layout.rows, 1, (v) => {
        layout.rows = Math.max(1, Math.min(6, v)); render(); schedulePreview();
      })),
      field('Cols', num(layout.cols, 1, (v) => {
        layout.cols = Math.max(1, Math.min(4, v)); render(); schedulePreview();
      })),
    ]));

    col.appendChild(el('div', { style: 'display:grid;grid-template-columns:1fr 1fr;gap:8px' }, [
      field('Row gap', num(layout.hspace != null ? layout.hspace : 0.45, 0.05, (v) => {
        layout.hspace = v; schedulePreview();
      })),
      field('Col gap', num(layout.wspace != null ? layout.wspace : 0.34, 0.05, (v) => {
        layout.wspace = v; schedulePreview();
      })),
    ]));

    /* grid map: click to place, drag across cells to span */
    col.appendChild(el('div', { class: 'section-label', text: 'Grid' }));
    col.appendChild(el('div', { class: 'grid-help',
      text: 'Click a cell to move the selected panel. Drag across cells to make '
          + 'it span them. Shift-click a second cell does the same.' }));

    const map = el('div', {
      class: 'grid-map',
      style: 'grid-template-columns:repeat(' + layout.cols + ',1fr)',
    });

    const cells = [];
    let dragFrom = null;

    const paint = (from, to) => {
      const r0 = Math.min(from[0], to[0]), r1 = Math.max(from[0], to[0]);
      const c0 = Math.min(from[1], to[1]), c1 = Math.max(from[1], to[1]);
      for (const cell of cells) {
        const inside = cell.r >= r0 && cell.r <= r1 && cell.c >= c0 && cell.c <= c1;
        cell.node.classList.toggle('span-preview', inside);
      }
    };

    const clearPaint = () => cells.forEach((x) => x.node.classList.remove('span-preview'));

    const applySpan = (from, to) => {
      const p = layout.panels[selected];
      if (!p) return;
      p.row = Math.min(from[0], to[0]);
      p.col = Math.min(from[1], to[1]);
      p.rowspan = Math.abs(to[0] - from[0]) + 1;
      p.colspan = Math.abs(to[1] - from[1]) + 1;
      clampPanel(p);
      render(); schedulePreview();
    };

    for (let r = 0; r < layout.rows; r++) {
      for (let c = 0; c < layout.cols; c++) {
        const rr = r, cc = c;
        const occupant = layout.panels.findIndex(
          (p) => rr >= p.row && rr < p.row + p.rowspan
              && cc >= p.col && cc < p.col + p.colspan);
        const node = el('div', {
          class: 'grid-cell' + (occupant >= 0 ? ' filled' : ''),
          title: occupant >= 0
            ? (layout.panels[occupant].title || labelFor(layout.panels[occupant].panel))
            : 'empty  (drag to span)',
          onmousedown: (e) => {
            e.preventDefault();
            if (!layout.panels[selected]) return;
            if (e.shiftKey) {
              const p = layout.panels[selected];
              applySpan([p.row, p.col], [rr, cc]);
              return;
            }
            dragFrom = [rr, cc];
            paint(dragFrom, dragFrom);
          },
          onmouseenter: () => { if (dragFrom) paint(dragFrom, [rr, cc]); },
          onmouseup: () => {
            if (!dragFrom) return;
            const from = dragFrom;
            dragFrom = null;
            clearPaint();
            applySpan(from, [rr, cc]);
          },
        }, [el('span', { text: occupant >= 0 ? String(occupant + 1) : '·' })]);
        cells.push({ r: rr, c: cc, node });
        map.appendChild(node);
      }
    }

    // A drag that ends outside the grid must not leave it stuck.
    map.addEventListener('mouseleave', () => {
      if (dragFrom) { dragFrom = null; clearPaint(); }
    });

    col.appendChild(map);

    /* panel list */
    col.appendChild(el('div', { class: 'section-label', text: 'Panels' }));
    layout.panels.forEach((p, i) => {
      col.appendChild(el('div', {
        class: 'panel-item' + (i === selected ? ' sel' : ''),
        onclick: () => { selected = i; render(); },
      }, [
        el('div', { class: 'pi-top' }, [
          el('span', { class: 'pi-name', text: (i + 1) + '. ' + (p.title || labelFor(p.panel)) }),
          el('span', { class: 'pi-pos', text: 'r' + p.row + 'c' + p.col
                       + (p.rowspan > 1 || p.colspan > 1 ? ' ' + p.rowspan + '×' + p.colspan : '') }),
          el('button', {
            class: 'badbtn', text: '×', title: 'Remove this panel',
            onclick: (e) => {
              e.stopPropagation();
              layout.panels.splice(i, 1);
              selected = Math.max(0, selected - 1);
              render(); schedulePreview();
            },
          }),
        ]),
        el('div', { class: 'pi-sub', text: labelFor(p.panel)
                    + (p.session_id && p.session_id !== sess.id
                       ? ' · ' + ((XF.sessions[p.session_id] || {}).identity || {}).label : '') }),
      ]));
    });

    col.appendChild(el('select', {
      style: 'margin-top:4px',
      onchange: (e) => {
        if (!e.target.value) return;
        addPanel(e.target.value);
        e.target.value = '';
      },
    }, [el('option', { value: '', text: '+ add a panel…' })].concat(
      panelDefs.map((d) => el('option', { value: d.id, text: d.name })))));

    return col;
  }

  function addPanel(kind) {
    const spot = firstFreeCell();
    const p = {
      panel: kind, session_id: sess.id, title: labelFor(kind),
      row: spot[0], col: spot[1], rowspan: 1, colspan: 1, cmap: 'jet',
    };
    if (kind === 'spectrogram' || kind === 'scalogram') {
      p.channel = sess.sel.size ? Math.min(...sess.sel) : 0;
      p.fmin = 20; p.fmax = 1000;
    }
    layout.panels.push(p);
    selected = layout.panels.length - 1;
    render(); schedulePreview();
  }

  function firstFreeCell() {
    for (let r = 0; r < layout.rows; r++) {
      for (let c = 0; c < layout.cols; c++) {
        const taken = layout.panels.some(
          (p) => r >= p.row && r < p.row + p.rowspan && c >= p.col && c < p.col + p.colspan);
        if (!taken) return [r, c];
      }
    }
    layout.rows = Math.min(6, layout.rows + 1);
    return [layout.rows - 1, 0];
  }

  function clampPanel(p) {
    p.row = Math.max(0, Math.min(p.row, layout.rows - 1));
    p.col = Math.max(0, Math.min(p.col, layout.cols - 1));
    p.rowspan = Math.max(1, Math.min(p.rowspan, layout.rows - p.row));
    p.colspan = Math.max(1, Math.min(p.colspan, layout.cols - p.col));
  }

  /* ---------- center: live preview ---------- */
  function centerColumn() {
    const col = el('div', { class: 'fig-col' });
    col.appendChild(el('div', { class: 'section-label', style: 'margin-top:0', text: 'Preview' }));
    const box = el('div', { class: 'fig-preview', id: 'figPreview' }, [
      el('div', { style: 'display:flex;align-items:center;gap:10px;color:var(--text-3)' }, [
        el('span', { class: 'spin' }), el('span', { text: 'Rendering…' }),
      ]),
    ]);
    col.appendChild(box);
    col.appendChild(el('div', { class: 'fb-stats', id: 'figProblems' }));
    return col;
  }

  /* ---------- right: selected panel + metadata ---------- */
  function rightColumn() {
    const col = el('div', { class: 'fig-col' });
    const p = layout.panels[selected];

    col.appendChild(el('div', { class: 'section-label', style: 'margin-top:0', text: 'Titles' }));
    col.appendChild(field('Figure title', text(layout.title, (v) => {
      layout.title = v; schedulePreview();
    })));
    col.appendChild(field('Subtitle', text(layout.subtitle, (v) => {
      layout.subtitle = v; schedulePreview();
    })));

    col.appendChild(el('div', { class: 'section-label', text: 'Time window' }));
    col.appendChild(el('div', { style: 'display:grid;grid-template-columns:1fr 1fr;gap:8px' }, [
      field('t0 (s)', num(layout.t0, 0.05, (v) => { layout.t0 = v; schedulePreview(); })),
      field('t1 (s)', num(layout.t1, 0.05, (v) => { layout.t1 = v; schedulePreview(); })),
    ]));
    col.appendChild(el('button', {
      class: 'btn ghost sm', text: 'Use current view',
      onclick: () => {
        layout.t0 = r6(sess.t0); layout.t1 = r6(sess.t0 + sess.span);
        layout.highpass = sess.hp; layout.lowpass = sess.lp; layout.notch = sess.notch;
        layout.channels = Array.from(sess.sel).sort((a, b) => a - b);
        layout.bad_channels = Array.from(sess.bad);
        layout.events = sess.events;
        render(); schedulePreview();
      },
    }));

    if (p) {
      col.appendChild(el('div', { class: 'section-label',
                                  text: 'Panel ' + (selected + 1) + ' — ' + labelFor(p.panel) }));
      col.appendChild(field('Panel title', text(p.title, (v) => {
        p.title = v; schedulePreview();
      })));
      col.appendChild(el('div', { style: 'display:grid;grid-template-columns:1fr 1fr;gap:8px' }, [
        field('Row span', num(p.rowspan || 1, 1, (v) => {
          p.rowspan = Math.max(1, v || 1); clampPanel(p); render(); schedulePreview();
        })),
        field('Col span', num(p.colspan || 1, 1, (v) => {
          p.colspan = Math.max(1, v || 1); clampPanel(p); render(); schedulePreview();
        })),
      ]));
      col.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Reset span to 1x1',
        onclick: () => {
          p.rowspan = 1; p.colspan = 1;
          render(); schedulePreview();
        },
      }));

      if (XF.order.length > 1) {
        col.appendChild(field('Session', el('select', {
          onchange: (e) => { p.session_id = e.target.value; schedulePreview(); },
        }, XF.order.map((id) => el('option', {
          value: id, text: XF.sessions[id].identity.label || XF.sessions[id].info.name,
          selected: (p.session_id || sess.id) === id ? 'selected' : null,
        })))));
      }

      if (p.panel === 'spectrogram' || p.panel === 'scalogram') {
        const s2 = XF.sessions[p.session_id] || sess;
        col.appendChild(field('Channel', el('select', {
          onchange: (e) => { p.channel = +e.target.value; schedulePreview(); },
        }, s2.info.channels.map((c) => el('option', {
          value: String(c.index), text: c.label,
          selected: String(p.channel) === String(c.index) ? 'selected' : null,
        })))));
        col.appendChild(el('div', { style: 'display:grid;grid-template-columns:1fr 1fr;gap:8px' }, [
          field('f min', num(p.fmin != null ? p.fmin : 20, 5, (v) => { p.fmin = v; schedulePreview(); })),
          field('f max', num(p.fmax != null ? p.fmax : 1000, 50, (v) => { p.fmax = v; schedulePreview(); })),
        ]));
      }

      if (p.panel !== 'traces') {
        col.appendChild(el('div', { class: 'section-label', text: 'Colormap' }));
        col.appendChild(cmapPicker(p.cmap || 'jet', (id) => {
          p.cmap = id; render(); schedulePreview();
        }));
      } else {
        col.appendChild(field('Gain', num(layout.gain || 1, 0.25, (v) => {
          layout.gain = v; schedulePreview();
        })));
      }
    }

    col.appendChild(el('div', { class: 'section-label', text: 'Metadata block' }));
    col.appendChild(el('label', { class: 'toggle' + (layout.show_metadata ? ' on' : '') }, [
      el('input', {
        type: 'checkbox', checked: layout.show_metadata ? 'checked' : null,
        onchange: (e) => { layout.show_metadata = e.target.checked; render(); schedulePreview(); },
      }),
      el('span', { text: 'Show provenance footer' }),
    ]));
    if (layout.show_metadata) {
      const m = layout.metadata;
      col.appendChild(field('Generated by', text(m.author, (v) => { m.author = v; schedulePreview(); })));
      col.appendChild(field('Date', text(m.date, (v) => { m.date = v; schedulePreview(); })));
      col.appendChild(field('Device', text(m.machine, (v) => { m.machine = v; schedulePreview(); })));
      // A textarea, not a single-line input: a rebuild writes several lines
      // of provenance in here, and they were invisible in a one-line field.
      col.appendChild(field('Notes', el('textarea', {
        rows: '4', value: m.notes || '', style: 'resize:vertical',
        oninput: debounceInput((e) => {
          m.notes = e.target.value; schedulePreview();
        }, 400),
      })));
      col.appendChild(el('div', { class: 'field' }, [
        el('label', { text: 'Source' }),
        el('span', { class: 'hint', style: 'word-break:break-all', text: m.source_path }),
      ]));
    }
    return col;
  }

  function cmapPicker(current, onpick) {
    const row = el('div', { class: 'cmap-row' });
    for (const c of colormaps) {
      const grad = 'linear-gradient(to right,' + (c.swatch || ['#888']).join(',') + ')';
      row.appendChild(el('button', {
        class: 'cmap-btn' + (c.id === current ? ' active' : ''),
        title: c.name + (c.note ? ' — ' + c.note : ''),
        onclick: () => onpick(c.id),
      }, [
        el('span', { class: 'grad', style: 'background:' + grad }),
        el('span', { class: 'nm', text: c.name }),
      ]));
    }
    return row;
  }

  /* ---------- small field helpers ---------- */
  function field(label, control, hint) {
    return el('div', { class: 'field' }, [
      el('label', { text: label }), control,
      hint ? el('span', { class: 'hint', text: hint }) : null,
    ]);
  }
  function num(value, step, onchange) {
    return el('input', {
      type: 'number', step: String(step), value: String(value ?? ''),
      onchange: (e) => onchange(parseFloat(e.target.value)),
    });
  }
  function text(value, onchange) {
    return el('input', {
      type: 'text', value: value || '',
      oninput: debounceInput((e) => onchange(e.target.value), 400),
    });
  }
  /* ==================================================================
     Preview + export
     ================================================================== */
  let previewTimer = null;
  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(doPreview, 350);
  }

  function sessionMap() {
    const out = {};
    const ids = new Set(layout.panels.map((p) => p.session_id || sess.id));
    ids.add(sess.id);
    for (const id of ids) {
      const s = XF.sessions[id];
      if (s) out[id] = { path: s.path, even_only: s.evenOnly, invert: s.invert };
    }
    out.default = { path: sess.path, even_only: sess.evenOnly, invert: sess.invert };
    return out;
  }

  async function doPreview() {
    if (rendering) { pendingRender = true; return; }
    rendering = true;
    const host = $('#figPreview');
    if (host) host.style.opacity = '0.55';
    try {
      const res = await apiPost('/api/figure/preview', {
        layout, sessions: sessionMap(), dpi: 110,
      });
      const box = $('#figPreview');
      if (box) {
        box.innerHTML = '';
        box.appendChild(el('img', { src: res.image, alt: 'figure preview' }));
        box.style.opacity = '1';
      }
      const pr = $('#figProblems');
      if (pr) {
        pr.innerHTML = '';
        (res.problems || []).forEach((p) => pr.appendChild(
          el('span', { class: 'stat-chip warn', style: 'white-space:normal', text: p })));
      }
    } catch (e) {
      const box = $('#figPreview');
      if (box) {
        box.innerHTML = '';
        box.style.opacity = '1';
        box.appendChild(el('div', { class: 'wiz-verdict low',
                                    style: 'max-width:520px', text: e.message }));
      }
    } finally {
      rendering = false;
      if (pendingRender) { pendingRender = false; schedulePreview(); }
    }
  }

  async function download(fmt) {
    const note = $('#figNote');
    if (note) note.textContent = 'Rendering ' + fmt.toUpperCase() + '…';
    try {
      const res = await fetch('/api/figure/export', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ layout, sessions: sessionMap(), format: fmt,
                               dpi: layout.dpi || 300 }),
      });
      if (!res.ok) {
        let msg = 'Export failed (' + res.status + ')';
        try { msg = (await res.json()).error || msg; } catch (e) { /* binary */ }
        throw new Error(msg);
      }
      const runId = res.headers.get('X-Barry-Run-Id');
      const problems = res.headers.get('X-Barry-Problems');
      const outRel = res.headers.get('X-Barry-Output');
      const outGit = res.headers.get('X-Barry-Github');
      const blob = await res.blob();
      const name = safeName(layout.title || 'figure') + '.' + fmt;
      const url = URL.createObjectURL(blob);
      const a = el('a', { href: url, download: name });
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);

      if (note) {
        note.textContent = 'Saved ' + name
          + (outRel ? '  ·  Results/' + outRel : '')
          + (runId ? '  ·  logged as ' + runId : '');
      }
      toast('Saved ' + name + (outRel ? ' to Results/' : ''), 'ok', 5000);
      BARRY.activity.log('figure.export', {
        format: fmt, name, run_id: runId, output: outRel, github: outGit,
        panels: layout.panels.map((x) => x.panel),
        t0: layout.t0, t1: layout.t1, page: layout.page,
        dpi: layout.dpi, cmap: layout.cmap,
      }, { identity: layout.identity || {} });
      if (problems) toast(problems, 'err', 8000);
      BARRY.refreshSync();
    } catch (e) {
      if (note) note.textContent = '';
      toast(e.message, 'err', 8000);
    }
  }

  function safeName(t) {
    return (String(t).replace(/[^\w \-.]+/g, '_').trim() || 'figure').slice(0, 80);
  }

  async function saveLayout() {
    const name = await askPath('Name this layout', 'e.g. "IED triptych"');
    if (!name) return;
    // Strip the events before cloning, not after: the clone is what would
    // choke on them, so deleting afterwards was too late to help.
    const body = JSON.parse(JSON.stringify(
      Object.assign({}, layout, { events: undefined })));
    delete body.events;          // events belong to a session, not a layout
    body.name = name;
    try {
      await apiPost('/api/presets/layouts', { preset: body });
      toast('Saved layout "' + name + '" to GUI_logs', 'ok');
      BARRY.refreshSync();
    } catch (e) { toast(e.message, 'err'); }
  }

  /* Reopen the builder on a recipe read back off a run record.

     The builder normally seeds itself from whatever is on screen. A rebuild
     is the opposite case: the layout is known and the screen has just been
     arranged to match it, so the recorded values win. Anything the record
     could not supply falls back to the freshly-seeded layout rather than to a
     hard-coded default, which is why buildInitialLayout still runs first. */
  async function reopen(xfState, session, recipe, plan) {
    XF = xfState;
    sess = session;

    if (!panelDefs.length) {
      try {
        const d = await api('/api/panels');
        panelDefs = d.panels || [];
        colormaps = d.colormaps || [];
        pages = d.pages || [];
      } catch (e) { /* fall back to defaults */ }
    }

    const seeded = buildInitialLayout();
    layout = Object.assign({}, seeded);

    // Only keys the record actually carried are taken from it: a recipe from
    // an older export has nulls where it never wrote anything down, and a
    // null page size is worse than the seeded one.
    for (const k of ['title', 'subtitle', 'page', 'width_in', 'height_in',
                     'dpi', 'rows', 'cols', 't0', 't1', 'highpass', 'lowpass',
                     'notch', 'cmap', 'spacing_um', 'channels',
                     'bad_channels', 'gain', 'show_metadata']) {
      if (recipe[k] !== undefined && recipe[k] !== null) layout[k] = recipe[k];
    }

    // Panels are re-pointed at the session that was just opened; the ids on
    // the record belong to a session that no longer exists.
    if ((recipe.panels || []).length) {
      layout.panels = recipe.panels.map((pn) => Object.assign({}, pn, {
        session_id: sess.id,
        title: pn.title || labelFor(pn.panel || 'traces'),
        rowspan: pn.rowspan || 1, colspan: pn.colspan || 1,
        row: pn.row || 0, col: pn.col || 0,
      }));
      layout.rows = Math.max(
        recipe.rows || 1,
        ...layout.panels.map((pn) => pn.row + pn.rowspan));
    }

    // Events come from the session, which the rebuild has already loaded.
    layout.events = sess.events;

    // The metadata block records who made the figure now, not who made the
    // original -- this is a new export. What it was rebuilt from goes in the
    // notes, where it is part of the figure rather than buried in a log.
    const run = (plan || {}).run || {};
    layout.metadata = Object.assign({}, seeded.metadata, {
      notes: [
        'Rebuilt from ' + (run.label || 'an earlier figure')
          + (run.provenance ? ' of ' + run.provenance.at : '')
          + (run.id ? ' (run ' + run.id + ')' : ''),
        (plan || {}).complete === false
          ? 'The original record predates full recipes, so the channel '
            + 'selection and gain come from this session rather than from '
            + 'the original.'
          : null,
        ((plan || {}).problems || []).length
          ? 'Differences: ' + plan.problems.join(' ')
          : null,
      ].filter(Boolean).join('\n'),
    });

    selected = 0;
    render();
    schedulePreview();

    const n = ((plan || {}).problems || []).length;
    toast(n ? 'Figure rebuilt with ' + n + ' difference'
              + (n === 1 ? '' : 's') + ' — see the notes field.'
            : 'Figure rebuilt exactly. Preview is rendering.',
          n ? null : 'ok', 7000);
  }

  return { open, reopen };
})();
