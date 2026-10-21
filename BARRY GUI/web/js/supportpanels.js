/* ==========================================================================
   supportpanels.js -- which support panels each add-on pops up, how each
   one starts, and how they are arranged (2026-10-20, granular 2026-10-21).

   "In the profile have a section called support panel preferences, where
   people can choose what support panels they'd like to have pop up in what
   arrangement for each Xplorefinder add-on."  And then: "super granular...
   select the width/height as percentages... a final mini popout that lets
   you drag things. Allow duplicate modes, e.g. 3 voltage traces. Then for
   each allow to choose default span, gain, channels selected, filter, and
   for the spectrogram/scalogram their presets."

   Every add-on that opens a second window of panels -- Checkup, Spotter,
   Panning, StrataScope, Braid -- asks `plan(mode, defaults, sess)` for what
   to open instead of hard-coding it. With nothing chosen, the add-on's own
   defaults stand, exactly as before. A choice is kept in preferences
   (`support_panels`), per add-on:

     open      whether the window opens at all
     panels    up to eight, in reading order, the same kind more than once
               if wanted; each with its own channels, filter, band, colours
               and (traces) gain, any of them left "as the add-on sets it"
     shape     a named arrangement (xplore.js layoutOf knows each), or
     layout    rows in percent of the window's height, each with its panels'
               widths in percent of the row: drawn in the arrangement editor
     span      seconds the window shows; empty follows the main window

   Span is the window's, not a panel's: every panel in one window reads one
   recording on one clock, so they cannot each show a different stretch.

     plan(mode, defaults, sess)  { specs, shape, layout, span } to open, or
                                 null (turned off). A chosen panel that is
                                 one of `defaults` keeps the add-on's own
                                 settings for whatever was left unchosen.
     opts(plan)                  the popOutPanes options that carry it.
     section()                   the Profile's "Support panel preferences".
   ========================================================================== */
'use strict';

BARRY.supportPanels = (function () {
  const KEY = 'support_panels';
  const MAX = 8;

  /* The add-ons with a support window, their defaults as the add-ons
     themselves open them, and the shape those defaults had. */
  const ADDONS = [
    { mode: 'curate', name: 'Checkup', panels: ['csd'], shape: null },
    { mode: 'spotter', name: 'Spotter',
      panels: ['csd', 'voltage', 'spectrogram'], shape: 'cols' },
    { mode: 'panning', name: 'Panning',
      panels: ['csd', 'voltage', 'spectrogram'], shape: 'cols' },
    { mode: 'strata', name: 'StrataScope',
      panels: ['csd', 'theta', 'voltage', 'spectrogram'], shape: 'linked' },
    { mode: 'cfc', name: 'Braid', panels: ['bandpower', 'spectrogram'],
      shape: 'cols' },
  ];

  /* The panels a support window can show: Xplorefinder's own list when it
     has loaded, else the ones the add-ons use. */
  const FALLBACK = [
    { id: 'traces', name: 'Voltage traces' },
    { id: 'csd', name: 'CSD' }, { id: 'theta', name: 'Theta' },
    { id: 'voltage', name: 'Voltage raster' },
    { id: 'spectrogram', name: 'Spectrogram' },
    { id: 'scalogram', name: 'Scalogram' },
    { id: 'bandpower', name: 'Band power' },
  ];
  const xf = () => {
    const xp = BARRY.views && BARRY.views.xplore;
    return (xp && xp.state) || {};
  };
  function catalog() {
    const defs = xf().panelDefs || [];
    return defs.length ? defs.map((d) => ({ id: d.id, name: d.name }))
                       : FALLBACK;
  }
  const nameOf = (id) => (catalog().find((p) => p.id === id)
                          || FALLBACK.find((p) => p.id === id) || {}).name || id;
  const isTF = (id) => id === 'spectrogram' || id === 'scalogram';

  /* ---------- the choices a panel has ---------- */

  const CHANNELS = [
    ['default', 'As the add-on sets them'],
    ['all', 'Every channel'],
    ['even', 'Even-numbered'], ['odd', 'Odd-numbered'],
    ['every4', 'Every 4th'], ['every8', 'Every 8th'],
    ['first16', 'First 16'], ['first32', 'First 32'], ['first64', 'First 64'],
    ['custom', 'These channels…'],
  ];
  /* [id, label, hp, lp]: a band-pass in Hz, 0 meaning that edge is open. */
  const FILTERS = [
    ['window', 'The window’s filter'],
    ['raw', 'None (raw)', 0, 0],
    ['lfp', 'LFP 1–300 Hz', 1, 300],
    ['theta', 'Theta 4–12 Hz', 4, 12],
    ['gamma', 'Gamma 30–80 Hz', 30, 80],
    ['ripple', 'Ripple 150–250 Hz', 150, 250],
    ['spikes', 'Spikes 300–6000 Hz', 300, 6000],
    ['custom', 'Custom…'],
  ];
  /* [id, label, fmin, fmax] for a spectrogram or scalogram. */
  const BANDS = [
    ['default', 'As the add-on sets it'],
    ['b1_250', '1–250 Hz', 1, 250],
    ['b1_50', '1–50 Hz (slow)', 1, 50],
    ['b4_100', '4–100 Hz (theta to gamma)', 4, 100],
    ['b100_300', '100–300 Hz (ripples)', 100, 300],
    ['b20_1000', '20–1000 Hz', 20, 1000],
    ['custom', 'Custom…'],
  ];
  const TFMODES = [['default', 'As the add-on sets it'],
                   ['stack', 'Stacked, one per channel'],
                   ['mean', 'Averaged into one']];
  const CMAP_FALLBACK = ['jet', 'viridis', 'magma', 'inferno', 'gray']
    .map((id) => ({ id, name: id }));
  const cmaps = () => {
    const got = xf().colormaps || [];
    return got.length ? got : CMAP_FALLBACK;
  };
  /* The filter presets saved in Xplorefinder (GUI_logs), offered beside the
     built-in ones as `p:<id or name>`. */
  const savedFilters = () => ((xf().presets || {}).filters || [])
    .map((p) => ['p:' + (p.id || p.name), p.name + '  (saved)',
                 +p.highpass || 0, +p.lowpass || 0, +p.notch || 0]);

  /* "1-16, 33, 40-48" -> the channel numbers it names. */
  function parseList(text) {
    const out = new Set();
    for (const part of String(text || '').split(/[\s,;]+/)) {
      const m = /^(\d+)(?:\s*[-–]\s*(\d+))?$/.exec(part);
      if (!m) continue;
      const a = +m[1], b = m[2] != null ? +m[2] : a;
      for (let k = Math.min(a, b); k <= Math.max(a, b) && out.size < 2048; k++) {
        out.add(k);
      }
    }
    return out;
  }

  /* Positions in the recording's channel list, or null for "as it was". */
  function positions(e, chs) {
    const how = e.channels || 'default';
    if (how === 'default' || !chs.length) return null;
    const num = (c, i) => (c && c.number != null ? +c.number : i + 1);
    let idx = chs.map((c, i) => i);
    if (how === 'even') idx = idx.filter((i) => num(chs[i], i) % 2 === 0);
    else if (how === 'odd') idx = idx.filter((i) => num(chs[i], i) % 2 === 1);
    else if (how === 'every4') idx = idx.filter((i) => i % 4 === 0);
    else if (how === 'every8') idx = idx.filter((i) => i % 8 === 0);
    else if (/^first\d+$/.test(how)) idx = idx.slice(0, +how.slice(5));
    else if (how === 'custom') {
      const want = parseList(e.chText);
      idx = idx.filter((i) => want.has(num(chs[i], i)));
    }
    return idx.length ? idx : null;
  }

  function filterOf(e) {
    const how = e.filter || 'window';
    if (how === 'window') return null;
    const notch = e.notch ? 60 : 0;
    if (how === 'custom') {
      return { hp: Math.max(0, +e.hp || 0), lp: Math.max(0, +e.lp || 0), notch };
    }
    const row = FILTERS.concat(savedFilters()).find((f) => f[0] === how);
    if (!row) return null;
    return { hp: row[2] || 0, lp: row[3] || 0,
             notch: notch || (row[4] || 0) };
  }

  function bandOf(e) {
    const how = e.band || 'default';
    if (how === 'default') return null;
    if (how === 'custom') {
      const lo = +e.fmin, hi = +e.fmax;
      return (lo >= 0 && hi > lo) ? [lo, hi] : null;
    }
    const row = BANDS.find((b) => b[0] === how);
    return row && row.length > 2 ? [row[2], row[3]] : null;
  }

  /* ---------- arrangements ---------- */

  /* How n panes can be arranged by name (xplore.js layoutOf knows each). */
  function shapesFor(n) {
    if (n === 2) return [['cols', 'Side by side'], ['rows', 'Stacked']];
    if (n === 3) {
      return [['cols', 'Three across'], ['rows', 'Stacked'],
              ['top1', 'One large on top'], ['top2', 'One large below']];
    }
    if (n === 4) {
      return [['linked', 'Two by two'], ['rows', 'Stacked'],
              ['cols', 'Four across']];
    }
    return [];
  }

  /* Whole percentages that sum to exactly 100. */
  function even100(k) {
    const base = Math.floor(100 / k);
    return Array.from({ length: k }, (x, i) => (i < 100 - base * k ? base + 1 : base));
  }
  function to100(vals) {
    const v = vals.map((x) => Math.max(1, +x || 1));
    const sum = v.reduce((a, b) => a + b, 0);
    const out = v.map((x) => Math.round((x / sum) * 100));
    out[out.length - 1] += 100 - out.reduce((a, b) => a + b, 0);
    return out;
  }
  function gridLayout(n) {
    const per = n <= 1 ? 1 : (n <= 4 ? 2 : Math.ceil(Math.sqrt(n)));
    const rows = [];
    for (let i = 0; i < n; i += per) rows.push(Math.min(per, n - i));
    const hs = even100(rows.length);
    return { rows: rows.map((k, r) => ({ h: hs[r], cols: even100(k) })) };
  }
  /* The named shape, written out as rows, so the editor starts from what
     the window would have opened with. */
  function shapeLayout(shape, n) {
    const row = (k, h) => ({ h, cols: even100(k) });
    if (n <= 1) return { rows: [row(1, 100)] };
    if (shape === 'cols') return { rows: [row(n, 100)] };
    if (shape === 'rows') {
      const hs = even100(n);
      return { rows: hs.map((h) => row(1, h)) };
    }
    if (shape === 'top1' && n === 3) return { rows: [row(1, 50), row(2, 50)] };
    if (shape === 'top2' && n === 3) return { rows: [row(2, 50), row(1, 50)] };
    return gridLayout(n);
  }
  const countOf = (lay) => (lay && Array.isArray(lay.rows))
    ? lay.rows.reduce((k, r) => k + ((r && r.cols) || []).length, 0) : 0;
  function fitLayout(lay, n) {
    if (!lay || countOf(lay) !== n) return null;
    return { rows: lay.rows.map((r) => ({ h: +r.h || 1,
                                          cols: r.cols.map((w) => +w || 1) })) };
  }
  const layoutWords = (lay) => {
    if (!lay) return '';
    const rs = lay.rows;
    return rs.length + (rs.length === 1 ? ' row' : ' rows') + ': '
      + rs.map((r) => r.h + '% high'
               + (r.cols.length > 1 ? ' (' + r.cols.join(' / ') + '% wide)' : ''))
          .join(', ');
  };

  /* Rows of slots, each slot carrying its panel: the one model the editor
     and the list share, so a panel moved between rows takes its settings. */
  function toRows(panels, layout) {
    const lay = layout || gridLayout(panels.length);
    let k = 0;
    return lay.rows.map((r) => ({
      h: r.h, cols: r.cols.map((w) => ({ w, e: panels[k++] })),
    }));
  }
  function fromRows(rows) {
    const live = rows.filter((r) => r.cols.length);
    const hs = to100(live.map((r) => r.h));
    return {
      panels: live.flatMap((r) => r.cols.map((c) => c.e)),
      layout: { rows: live.map((r, i) => ({ h: hs[i],
                                            cols: to100(r.cols.map((c) => c.w)) })) },
    };
  }

  /* ---------- what is kept ---------- */

  function all() {
    try {
      const got = BARRY.prefs.get(KEY, {});
      return (got && typeof got === 'object') ? got : {};
    } catch (e) { return {}; }
  }

  function addon(mode) { return ADDONS.find((a) => a.mode === mode) || null; }

  /* A panel as kept: an old choice was just its id. */
  const entry = (p) => (typeof p === 'string' ? { panel: p }
                        : Object.assign({}, p || {}));

  /* What this person chose for an add-on, filled in from its defaults. */
  function choice(mode) {
    const a = addon(mode) || { panels: [], shape: null };
    const c = all()[mode] || {};
    const panels = (Array.isArray(c.panels) && c.panels.length
      ? c.panels : a.panels).slice(0, MAX).map(entry)
      .filter((e) => e.panel);
    const shapes = shapesFor(panels.length).map((s) => s[0]);
    return {
      open: c.open !== false,
      panels,
      shape: shapes.includes(c.shape) ? c.shape
        : (shapes.includes(a.shape) ? a.shape : (shapes[0] || null)),
      layout: fitLayout(c.layout, panels.length),
      span: +c.span > 0 ? +c.span : null,
      custom: !!all()[mode],
    };
  }

  function save(mode, c) {
    const every = Object.assign({}, all());
    if (c === null) delete every[mode];
    else {
      every[mode] = { open: c.open, panels: c.panels, shape: c.shape,
                      layout: c.layout || null, span: c.span || null };
    }
    try { BARRY.prefs.set(KEY, every); } catch (e) { /* this session only */ }
  }

  /* One panel's spec, as setPanes takes it: the add-on's own spec for that
     kind of panel underneath, then whatever this person chose on top. */
  function specFor(e, base, chs) {
    const sp = JSON.parse(JSON.stringify(base
      || (isTF(e.panel) ? { panel: e.panel, fmin: 1, fmax: 250 }
                        : { panel: e.panel })));
    sp.panel = e.panel;
    const pos = positions(e, chs);
    if (pos) {
      if (isTF(e.panel)) {
        sp.tfChannels = pos.map((i) => (chs[i] && chs[i].index != null
                                         ? chs[i].index : i));
        if (pos.length > 1 && !sp.tfMode) sp.tfMode = 'stack';
      } else {
        sp.channels = pos;
      }
    }
    const f = filterOf(e);
    if (f) sp.filt = f;
    if (isTF(e.panel)) {
      const b = bandOf(e);
      if (b) { sp.fmin = b[0]; sp.fmax = b[1]; }
      if (e.tfMode && e.tfMode !== 'default') sp.tfMode = e.tfMode;
    }
    if (e.cmap && e.cmap !== 'default' && e.panel !== 'traces') sp.cmap = e.cmap;
    if (e.panel === 'traces' && +e.gain > 0 && +e.gain !== 1) sp.gain = +e.gain;
    return sp;
  }

  function plan(mode, defaults, sess) {
    const c = choice(mode);
    if (!c.open) return null;
    const byId = {};
    for (const d of defaults || []) if (d && !byId[d.panel]) byId[d.panel] = d;
    const chs = (sess && sess.info && sess.info.channels) || [];
    const specs = c.panels.map((e) => specFor(e, byId[e.panel], chs));
    if (!specs.length) return null;
    const layout = c.layout || (specs.length > 4 ? gridLayout(specs.length) : null);
    return { specs, shape: c.shape, layout, span: c.span };
  }

  /* The options popOutPanes carries this in (xplore.js paneUrl). The band
     lock comes off when a panel asks for its own band, or the window would
     draw every spectrogram at the recording's one band and ignore it. */
  function opts(p) {
    const o = {};
    if (!p) return o;
    if (p.shape) o.shape = p.shape;
    if (p.layout) o.layout = p.layout;
    if (p.span) o.span = p.span;
    if ((p.specs || []).some((s) => isTF(s.panel) && s.fmin != null)) {
      o.flock = 'off';
    }
    return o;
  }

  /* ---------- the arrangement editor: the mini window you drag ---------- */

  /* The window, drawn small: drag the line between two rows to share the
     height between them, the line between two panels to share a row's
     width, or a panel onto another to swap them. Every size is also a
     number you can type. Nothing is kept until Save. */
  function drawEditor(a, c, onSave) {
    let rows = toRows(c.panels, c.layout || shapeLayout(c.shape, c.panels.length));
    const canvas = el('div', { class: 'spl-canvas' });
    const words = el('p', { class: 'hint spl-words' });

    const pctIn = (val, title, onSet, cls) => el('input', {
      type: 'number', class: 'spl-pct ' + cls, min: '5', max: '95', step: '1',
      value: String(val), title,
      onchange: (ev) => onSet(Math.max(5, Math.min(95, +ev.target.value || 0))),
    });

    /* Give one of a group its value, the rest the remainder in their
       existing proportions. */
    function setShare(list, i, v, key) {
      const others = list.filter((x, j) => j !== i);
      const rest = others.reduce((s, x) => s + x[key], 0) || 1;
      const left = 100 - v;
      list[i][key] = v;
      others.forEach((x) => { x[key] = Math.max(5, (x[key] / rest) * left); });
      const fixed = to100(list.map((x) => x[key]));
      list.forEach((x, j) => { x[key] = fixed[j]; });
    }

    function moveRow(r, k, dir) {
      const slot = rows[r].cols.splice(k, 1)[0];
      if (rows[r].cols.length) {
        const ws = to100(rows[r].cols.map((x) => x.w));
        rows[r].cols.forEach((x, j) => { x.w = ws[j]; });
      }
      let to = r + dir;
      if (to < 0) { rows.unshift({ h: 100 / (rows.length + 1), cols: [] }); to = 0; r += 1; }
      else if (to >= rows.length) rows.push({ h: 100 / (rows.length + 1), cols: [] });
      const n = rows[to].cols.length + 1;
      rows[to].cols.forEach((x) => { x.w = x.w * (n - 1) / n; });
      rows[to].cols.push(Object.assign(slot, { w: 100 / n }));
      rows = rows.filter((x) => x.cols.length);
      const hs = to100(rows.map((x) => x.h));
      rows.forEach((x, j) => { x.h = hs[j]; });
      paint();
    }

    /* A divider being dragged: the two neighbours share what they had. */
    function dragBar(ev, list, i, key, axisPx) {
      ev.preventDefault();
      const bar = ev.currentTarget;
      try { bar.setPointerCapture(ev.pointerId); } catch (e) { /* not a live pointer */ }
      const start = axisPx(ev), a0 = list[i][key], b0 = list[i + 1][key];
      const box = canvas.getBoundingClientRect();
      const full = key === 'h' ? box.height : bar.parentNode.getBoundingClientRect().width;
      const move = (m) => {
        const d = ((axisPx(m) - start) / (full || 1)) * 100;
        const av = Math.max(5, Math.min(a0 + b0 - 5, a0 + d));
        list[i][key] = Math.round(av);
        list[i + 1][key] = Math.round(a0 + b0 - av);
        sizeOnly();
      };
      const up = () => {
        bar.removeEventListener('pointermove', move);
        bar.removeEventListener('pointerup', up);
        bar.removeEventListener('pointercancel', up);
        bar.classList.remove('dragging');
        paint();
      };
      bar.classList.add('dragging');
      bar.addEventListener('pointermove', move);
      bar.addEventListener('pointerup', up);
      bar.addEventListener('pointercancel', up);
    }

    /* A panel picked up: dropped on another, the two swap places. */
    function dragSlot(ev, r, k) {
      if (ev.target.closest('input, button')) return;
      const node = ev.currentTarget;
      const x0 = ev.clientX, y0 = ev.clientY;
      let moving = false, over = null;
      try { node.setPointerCapture(ev.pointerId); } catch (e) { /* not a live pointer */ }
      const move = (m) => {
        if (!moving && Math.hypot(m.clientX - x0, m.clientY - y0) < 6) return;
        moving = true;
        node.classList.add('lifted');
        node.style.transform = 'translate(' + (m.clientX - x0) + 'px,'
                             + (m.clientY - y0) + 'px)';
        node.style.pointerEvents = 'none';
        const hit = document.elementFromPoint(m.clientX, m.clientY);
        node.style.pointerEvents = '';
        const t = hit && hit.closest('.spl-slot');
        if (over && over !== t) over.classList.remove('target');
        over = (t && t !== node) ? t : null;
        if (over) over.classList.add('target');
      };
      const up = () => {
        node.removeEventListener('pointermove', move);
        node.removeEventListener('pointerup', up);
        node.removeEventListener('pointercancel', up);
        node.classList.remove('lifted');
        node.style.transform = '';
        if (moving && over) {
          const r2 = +over.dataset.r, k2 = +over.dataset.k;
          const t = rows[r].cols[k].e;
          rows[r].cols[k].e = rows[r2].cols[k2].e;
          rows[r2].cols[k2].e = t;
        }
        paint();
      };
      node.addEventListener('pointermove', move);
      node.addEventListener('pointerup', up);
      node.addEventListener('pointercancel', up);
    }

    /* While a divider moves, only the sizes and their numbers change. */
    function sizeOnly() {
      canvas.querySelectorAll('.spl-row').forEach((rn, r) => {
        rn.style.flexGrow = String(rows[r].h);
        rn.querySelectorAll('.spl-slot').forEach((sn, k) => {
          sn.style.flexGrow = String(rows[r].cols[k].w);
          const w = sn.querySelector('.spl-w'), h = sn.querySelector('.spl-h');
          if (w) w.value = String(Math.round(rows[r].cols[k].w));
          if (h) h.value = String(Math.round(rows[r].h));
        });
      });
      words.textContent = layoutWords(fromRows(rows).layout);
    }

    function paint() {
      canvas.innerHTML = '';
      let n = 0;
      rows.forEach((row, r) => {
        if (r > 0) {
          canvas.appendChild(el('div', {
            class: 'spl-hbar', title: 'Drag to share the height between these rows',
            onpointerdown: (ev) => dragBar(ev, rows, r - 1, 'h', (m) => m.clientY),
          }));
        }
        const rn = el('div', { class: 'spl-row' });
        rn.style.flexGrow = String(row.h);
        row.cols.forEach((slot, k) => {
          if (k > 0) {
            rn.appendChild(el('div', {
              class: 'spl-vbar', title: 'Drag to share the width between these panels',
              onpointerdown: (ev) => dragBar(ev, row.cols, k - 1, 'w', (m) => m.clientX),
            }));
          }
          n += 1;
          const sn = el('div', {
            class: 'spl-slot', 'data-r': String(r), 'data-k': String(k),
            title: 'Drag onto another panel to swap them',
            onpointerdown: (ev) => dragSlot(ev, r, k),
          }, [
            el('strong', { class: 'spl-name', text: n + '. ' + nameOf(slot.e.panel) }),
            el('div', { class: 'spl-sizes' }, [
              el('label', {}, [el('span', { text: 'W' }),
                pctIn(Math.round(slot.w), 'Width, percent of its row', (v) => {
                  setShare(row.cols, k, v, 'w'); paint();
                }, 'spl-w'), el('span', { text: '%' })]),
              el('label', {}, [el('span', { text: 'H' }),
                pctIn(Math.round(row.h), 'Height of its row, percent of the window',
                      (v) => { setShare(rows, r, v, 'h'); paint(); }, 'spl-h'),
                el('span', { text: '%' })]),
            ]),
            el('div', { class: 'spl-moves' }, [
              el('button', { class: 'mini', text: '↑ row', type: 'button',
                title: 'Into the row above (a new row if this is the top one)',
                onclick: () => moveRow(r, k, -1) }),
              el('button', { class: 'mini', text: '↓ row', type: 'button',
                title: 'Into the row below (a new row if this is the bottom one)',
                onclick: () => moveRow(r, k, 1) }),
            ]),
          ]);
          sn.style.flexGrow = String(slot.w);
          rn.appendChild(sn);
        });
        canvas.appendChild(rn);
      });
      words.textContent = layoutWords(fromRows(rows).layout);
    }

    const quick = (label, title, make) => el('button', {
      class: 'mini', type: 'button', text: label, title,
      onclick: () => {
        const panels = fromRows(rows).panels;
        rows = toRows(panels, make(panels.length));
        paint();
      },
    });

    paint();
    showModal(el('div', { class: 'spl' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Arrange ' + a.name + '’s window' }),
        el('div', { class: 'spacer' }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { class: 'hint', text: 'Drag the line between two rows, or '
          + 'between two panels, to resize them; drag a panel onto another to '
          + 'swap them. Each size is a percentage you can also type: widths '
          + 'of their row, heights of the window.' }),
        el('div', { class: 'spl-quick' }, [
          quick('One row', 'Every panel side by side', (n) => shapeLayout('cols', n)),
          quick('One column', 'Every panel stacked', (n) => shapeLayout('rows', n)),
          quick('Grid', 'As square as the count allows', (n) => gridLayout(n)),
        ]),
        canvas,
        words,
      ]),
      BARRY.ui.modalFoot([
        c.layout ? BARRY.ui.button({ kind: 'ghost', text: 'Use a named arrangement',
          title: 'Forget the drawn sizes; the window opens in the arrangement '
               + 'picked in the list',
          onclick: () => { closeModal(); onSave(null); } }) : null,
      ], [
        BARRY.ui.button({ kind: 'ghost', text: 'Cancel', onclick: () => closeModal() }),
        BARRY.ui.button({ kind: 'primary', text: 'Save the arrangement',
          extra: 'spl-save',
          onclick: () => { closeModal(); onSave(fromRows(rows)); } }),
      ]),
    ]));
  }

  /* ---------- the Profile's section ---------- */

  const sel = (opts2, value, title, onPick) => el('select', {
    class: 'spp-sel', title,
    onchange: (ev) => onPick(ev.target.value),
  }, opts2.map(([v, label]) => el('option', {
    value: v, text: label, selected: v === value ? 'selected' : null,
  })));
  const num = (value, title, onSet, o) => el('input', Object.assign({
    type: 'number', class: 'spp-num', value: value == null ? '' : String(value),
    title, onchange: (ev) => onSet(ev.target.value === '' ? null : +ev.target.value),
  }, o || {}));
  const fld = (label, kids) => el('label', { class: 'spp-f' },
    [el('span', { class: 'spp-fl', text: label })].concat(kids.filter(Boolean)));

  function row(a, host) {
    const c = choice(a.mode);
    /* Kept, and the list drawn again (a structural change). */
    const set = (patch) => {
      const next = Object.assign({}, c, patch);
      const shapes = shapesFor(next.panels.length).map((s) => s[0]);
      if (!shapes.includes(next.shape)) next.shape = shapes[0] || null;
      if (next.layout && countOf(next.layout) !== next.panels.length) next.layout = null;
      save(a.mode, next);
      paint(host);
    };
    /* A field changed: kept, the list left as it is so typing is not lost. */
    const keepField = (i, patch, redraw) => {
      const panels = c.panels.map((e, j) => (j === i ? Object.assign({}, e, patch) : e));
      c.panels = panels;
      save(a.mode, Object.assign({}, c, { panels }));
      if (redraw) paint(host);
    };
    /* Panels added, copied or removed keep a drawn arrangement in step. */
    const withRows = (fn) => {
      if (!c.layout) return null;
      const rs = toRows(c.panels, c.layout);
      fn(rs);
      return fromRows(rs);
    };
    const addPanel = (id) => {
      const e = { panel: id };
      const r = withRows((rs) => {
        const last = rs[rs.length - 1], n = last.cols.length + 1;
        last.cols.forEach((x) => { x.w = x.w * (n - 1) / n; });
        last.cols.push({ w: 100 / n, e });
      });
      set(r || { panels: c.panels.concat([e]) });
    };
    const copyPanel = (i) => {
      const e = JSON.parse(JSON.stringify(c.panels[i]));
      let k = 0;
      const r = withRows((rs) => {
        for (const rr of rs) {
          for (let j = 0; j < rr.cols.length; j++, k++) {
            if (k === i) {
              const n = rr.cols.length + 1;
              rr.cols.forEach((x) => { x.w = x.w * (n - 1) / n; });
              rr.cols.splice(j + 1, 0, { w: 100 / n, e });
              return;
            }
          }
        }
      });
      const p = c.panels.slice();
      p.splice(i + 1, 0, e);
      set(r || { panels: p });
    };
    const dropPanel = (i) => {
      let k = 0;
      const r = withRows((rs) => {
        for (const rr of rs) {
          for (let j = 0; j < rr.cols.length; j++, k++) {
            if (k === i) { rr.cols.splice(j, 1); return; }
          }
        }
      });
      set(r || { panels: c.panels.filter((x, j) => j !== i) });
    };
    const swap = (i, j) => {
      const p = c.panels.slice();
      [p[i], p[j]] = [p[j], p[i]];
      set({ panels: p });
    };

    const panelCard = (e, i) => {
      const tf = isTF(e.panel);
      const fil = e.filter || 'window';
      const filters = FILTERS.slice(0, -1).concat(savedFilters(), [FILTERS[FILTERS.length - 1]]);
      return el('div', { class: 'spp-panel' }, [
        el('div', { class: 'spp-ph' }, [
          el('span', { class: 'spp-n', text: String(i + 1) }),
          sel(catalog().map((p) => [p.id, p.name]), e.panel, 'What this panel shows',
              (v) => keepField(i, { panel: v }, true)),
          el('div', { class: 'spacer' }),
          c.panels.length < MAX ? el('button', { class: 'mini', type: 'button',
            text: 'Copy', title: 'Another ' + nameOf(e.panel) + ' with these settings, '
              + 'right after this one', onclick: () => copyPanel(i) }) : null,
          i > 0 ? el('button', { class: 'mini', type: 'button', text: '↑',
            title: 'Earlier in the window', onclick: () => swap(i, i - 1) }) : null,
          i < c.panels.length - 1 ? el('button', { class: 'mini', type: 'button',
            text: '↓', title: 'Later in the window', onclick: () => swap(i, i + 1) }) : null,
          c.panels.length > 1 ? el('button', { class: 'mini', type: 'button', text: '×',
            title: 'Take this ' + nameOf(e.panel) + ' out of the window',
            onclick: () => dropPanel(i) }) : null,
        ].filter(Boolean)),
        el('div', { class: 'spp-pf' }, [
          fld('Channels', [
            sel(CHANNELS, e.channels || 'default', 'Which channels it opens on',
                (v) => keepField(i, { channels: v }, true)),
            e.channels === 'custom' ? el('input', {
              type: 'text', class: 'spp-text', value: e.chText || '',
              placeholder: 'e.g. 1-16, 33', title: 'Channel numbers, ranges allowed',
              onchange: (ev) => keepField(i, { chText: ev.target.value }) }) : null,
          ]),
          fld('Filter', [
            sel(filters, fil, 'The band-pass this panel reads with; the window’s '
                + 'filter is the main window’s',
                (v) => keepField(i, { filter: v }, true)),
            fil === 'custom' ? num(e.hp, 'High-pass, Hz (0 = open)',
              (v) => keepField(i, { hp: v }), { min: '0', step: '0.5', placeholder: 'HP' }) : null,
            fil === 'custom' ? num(e.lp, 'Low-pass, Hz (0 = open)',
              (v) => keepField(i, { lp: v }), { min: '0', step: '1', placeholder: 'LP' }) : null,
            fil !== 'window' ? el('span', { class: 'spp-check' }, [
              el('input', { type: 'checkbox', checked: e.notch ? 'checked' : null,
                title: 'Take out 60 Hz mains',
                onchange: (ev) => keepField(i, { notch: ev.target.checked }) }),
              el('span', { text: '60 Hz notch' }),
            ]) : null,
          ]),
          tf ? fld('Band', [
            sel(BANDS, e.band || 'default', 'The frequencies it computes',
                (v) => keepField(i, { band: v }, true)),
            e.band === 'custom' ? num(e.fmin, 'Lowest frequency, Hz',
              (v) => keepField(i, { fmin: v }), { min: '0', step: '1', placeholder: 'from' }) : null,
            e.band === 'custom' ? num(e.fmax, 'Highest frequency, Hz',
              (v) => keepField(i, { fmax: v }), { min: '1', step: '1', placeholder: 'to' }) : null,
          ]) : null,
          tf ? fld('Several channels', [
            sel(TFMODES, e.tfMode || 'default', 'One picture per channel, or their average',
                (v) => keepField(i, { tfMode: v })),
          ]) : null,
          e.panel !== 'traces' ? fld('Colours', [
            sel([['default', 'As the add-on sets them']]
                  .concat(cmaps().map((m) => [m.id, m.name])),
                e.cmap || 'default', 'The colour map',
                (v) => keepField(i, { cmap: v })),
          ]) : null,
          e.panel === 'traces' ? fld('Gain', [
            num(e.gain != null ? e.gain : 1, 'Times the window’s gain; 1 is the same',
                (v) => keepField(i, { gain: v }), { min: '0.05', step: '0.25' }),
            el('span', { class: 'spp-unit', text: '×' }),
          ]) : null,
        ].filter(Boolean)),
      ]);
    };

    const n = c.panels.length;
    const shapes = shapesFor(n);
    const addable = catalog();
    return el('div', { class: 'spp-row' + (c.open ? '' : ' off') }, [
      el('div', { class: 'spp-head' }, [
        el('strong', { text: a.name }),
        BARRY.ui.seg([['on', 'Opens'], ['off', 'Does not open']],
          c.open ? 'on' : 'off', (v) => set({ open: v === 'on' })),
        el('div', { class: 'spacer' }),
        c.custom ? el('button', { class: 'linkish', type: 'button',
          text: 'Back to its defaults',
          onclick: () => { save(a.mode, null); paint(host); } }) : null,
      ].filter(Boolean)),
      c.open ? el('div', { class: 'spp-panels' }, c.panels.map(panelCard)) : null,
      c.open ? el('div', { class: 'spp-tools' }, [
        n < MAX ? el('select', {
          class: 'spp-add', title: 'Add a panel to this window (up to ' + MAX
            + '; the same kind more than once is fine)',
          onchange: (ev) => { if (ev.target.value) addPanel(ev.target.value); },
        }, [el('option', { value: '', text: '+ Add a panel' })]
          .concat(addable.map((p) => el('option', { value: p.id, text: p.name }))))
          : null,
        fld('Span', [
          num(c.span, 'Seconds the window shows. Empty: it follows the main window',
              (v) => { c.span = v > 0 ? v : null;
                       save(a.mode, Object.assign({}, c)); },
              { min: '0.05', step: '0.5', placeholder: 'follows' }),
          el('span', { class: 'spp-unit', text: 's' }),
        ]),
      ].filter(Boolean)) : null,
      c.open ? el('div', { class: 'spp-tools spp-arr' }, [
        el('span', { class: 'spp-fl', text: 'Arrangement' }),
        c.layout
          ? el('span', { class: 'spp-drawn', text: 'Drawn — ' + layoutWords(c.layout) })
          : (shapes.length > 1 ? BARRY.ui.seg(shapes, c.shape,
              (v) => set({ shape: v, layout: null }), { extra: 'sm' })
            : el('span', { class: 'hint', text: n > 4 ? 'A grid, unless you draw one'
                                                      : 'The whole window' })),
        el('button', { class: 'btn sm spp-draw', type: 'button',
          text: c.layout ? 'Edit the drawing…' : 'Draw it…',
          title: 'A small copy of the window: drag the sizes, type percentages, '
               + 'move panels between rows',
          onclick: () => drawEditor(a, c, (got) => {
            if (got) set({ panels: got.panels, layout: got.layout });
            else set({ layout: null });
          }) }),
      ]) : null,
    ].filter(Boolean));
  }

  function paint(host) {
    host.innerHTML = '';
    for (const a of ADDONS) host.appendChild(row(a, host));
  }

  function section() {
    const list = el('div', { class: 'spp-list' });
    const wrap = el('details', { class: 'spp' }, [
      el('summary', { class: 'section-label', text: 'Support panel preferences' }),
      el('p', { class: 'hint', text: 'The second window each add-on opens: '
          + 'whether it opens, which panels it holds (up to ' + MAX + ', the same '
          + 'kind more than once if you like), how each one starts -- channels, '
          + 'filter, band and colours -- and how they are arranged, to the '
          + 'percent. Saved as you change it; it applies the next time the '
          + 'add-on opens.' }),
      list,
    ]);
    paint(list);
    return wrap;
  }

  return { plan, opts, choice, section, ADDONS,
           _test: { positions, filterOf, bandOf, parseList, toRows, fromRows,
                    shapeLayout, gridLayout, specFor } };
})();
