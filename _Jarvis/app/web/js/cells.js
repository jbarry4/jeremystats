/* ==========================================================================
   cells.js -- Cells: a recording's curated units, in Xplorefinder.

   PROJECT EVOLVE phase 7 (2026-11-21). An add-on, like Braid: it looks and
   decides nothing. The traces get this window, with every curated cell's
   spikes ticked on its own contact, coloured by the layer the layer sheet
   says that contact is in; the cells themselves get a second window of
   cards -- the mean waveform on the contacts around it, its ISIs, its
   autocorrelogram, its rate and amplitude through the recording, and its
   firing around each label of a banked set (DS, P-spike, Twilight Zone...).

   ← → step from cell to cell. Bank the cells… makes (or continues) the
   recording's Cell entry from the curation version on show.

   Data: /api/cells/* (backend/cellroutes.py). The cards window is the app
   at /?role=cells#cells, reading this window's `window.barryCells`.
   ========================================================================== */
'use strict';

BARRY.cells = (function () {
  let sess = null;
  let gid = null;
  let d = null;            // /api/cells/<gid>
  let version = null;
  let at = 0;              // which cell, an index into d.cells
  let only = false;        // ticks for this cell only
  let sets = null;         // banked sets with events here
  let setId = null;        // the one whose firing the cards show
  let aidWin = null;
  let overlay = null;
  let win = null;          // the spikes in the window on show
  let winKey = null;
  let winTimer = null;

  const VIEWED_KEY = 'barry.cells.viewed';

  /* ==================================================================
     Entering and leaving
     ================================================================== */
  async function enter(gidIn, o) {
    const opt = o || {};
    BARRY.modes.leaveAllBut('cells');
    if (sess) exit();
    gid = gidIn;
    let path = null;
    try {
      const r = await api('/api/registry/' + encodeURIComponent(gid));
      const got = BARRY.vacc.reachFor(Object.assign({ gid }, r.session || {}), 'cells');
      path = got.path;
      if (!path) {
        toast(got.why || 'That recording is not on this computer.', 'err', 9000);
        return false;
      }
    } catch (e) {
      toast('No such recording: ' + e.message, 'err', 8000);
      return false;
    }
    try {
      d = await api('/api/cells/' + encodeURIComponent(gid)
                    + (opt.version ? '?version=' + opt.version : ''));
    } catch (e) {
      toast('Its cells could not be read: ' + e.message, 'err', 9000);
      return false;
    }
    if (!(d.cells || []).length) {
      toast('Nothing has been read for this recording yet: read its export in '
            + 'Kilosort › Cells first.', 'warn', 9000);
      return false;
    }
    version = d.version;
    at = Math.max(0, (d.cells || []).findIndex((c) => c.id === opt.cell));
    setView('xplore');
    sess = await BARRY.views.xplore.open(path);
    if (!sess) return false;
    setMode('cells', exit);
    layout();
    bar();
    mountOverlay();
    document.addEventListener('keydown', keys, true);
    try {
      const seen = JSON.parse(localStorage.getItem(VIEWED_KEY) || '[]');
      if (seen.indexOf(gid) < 0) {
        seen.push(gid);
        localStorage.setItem(VIEWED_KEY, JSON.stringify(seen.slice(-500)));
      }
    } catch (e) { /* a convenience */ }
    BARRY.activity.log('cells.enter', { gid, version, cells: d.cells.length });
    loadSets();
    goTo(at);
    return true;
  }

  function exit() {
    if (aidWin && !aidWin.closed) { try { aidWin.close(); } catch (e) {} }
    aidWin = null;
    if (BARRY.supportPanels) BARRY.supportPanels.restoreMain();
    setMode(null);
    const b = document.getElementById('cellsBar');
    if (b) b.remove();
    document.documentElement.style.removeProperty('--bottom-bar');
    document.removeEventListener('keydown', keys, true);
    window.removeEventListener('resize', drawOverlay);
    window.removeEventListener('scroll', drawOverlay, true);
    if (overlay) { overlay.remove(); overlay = null; }
    if (sess) BARRY.activity.log('cells.leave', { gid });
    sess = null; d = null; win = null; winKey = null; sets = null;
    if (BARRY.views.xplore.refreshAll) BARRY.views.xplore.refreshAll();
  }

  function layout() {
    const mp = BARRY.supportPanels
      ? BARRY.supportPanels.applyMain('cells', [{ panel: 'traces' }], sess,
                                      { col: 1, row: 1 })
      : (BARRY.views.xplore.setPanes([{ panel: 'traces' }], { col: 1, row: 1 }), null);
    if (mp && mp.span && sess) {
      BARRY.views.xplore.setWindow(sess,
        Math.max(0, sess.t0 + sess.span / 2 - mp.span / 2), mp.span);
    }
    openAids();
  }

  function openAids() {
    if (aidWin && !aidWin.closed) { try { aidWin.focus(); } catch (e) {} return; }
    aidWin = window.open(location.origin + '/?role=cells#cells', 'barry-cells',
                         'width=760,height=900,menubar=no,toolbar=no');
    if (!aidWin) {
      toast('The cards window was blocked. Allow pop-ups for 127.0.0.1, then '
            + 'press Reopen the cards.', 'err', 9000);
    }
  }

  /* ==================================================================
     Which cell
     ================================================================== */
  const cells = () => (d && d.cells) || [];
  const cur = () => cells()[at] || null;

  function goTo(i) {
    const cs = cells();
    if (!cs.length) return;
    at = (i + cs.length) % cs.length;
    bar();
    drawOverlay();
    tellAid();
  }

  function keys(e) {
    if (!sess) return;
    if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    if (e.key === 'ArrowRight' || e.key === 'n') { e.preventDefault(); e.stopPropagation(); goTo(at + 1); }
    else if (e.key === 'ArrowLeft' || e.key === 'p') { e.preventDefault(); e.stopPropagation(); goTo(at - 1); }
  }

  async function loadSets() {
    try {
      sets = (await api('/api/cells/' + encodeURIComponent(gid) + '/bundles')).sets || [];
    } catch (e) { sets = []; }
    if (!setId) {
      // An Ambiguous run's bundle first: it holds every label.
      const first = sets.find((s) => s.bundle && (s.labels || []).some((l) => l.id === 'twilight'))
        || sets.find((s) => s.bundle) || sets[0];
      setId = first ? first.id : null;
    }
    bar();
    tellAid();
  }

  /* ==================================================================
     The bar
     ================================================================== */
  function bar() {
    if (!sess) return;
    let b = document.getElementById('cellsBar');
    if (!b) {
      b = el('div', { class: 'cfc-bar cells-bar', id: 'cellsBar' });
      BARRY.modeSlot().appendChild(b);
    }
    const c = cur() || {};
    const n = cells().length;
    const setSel = el('select', { class: 'cells-set',
      title: 'The banked set whose events the firing cards line up on',
      onchange: (e) => { setId = e.target.value || null; tellAid(); } },
      [el('option', { value: '', text: sets === null ? 'Reading the sets…'
                                         : 'No set: no firing card' })]
        .concat((sets || []).map((s) => el('option', { value: s.id,
          text: s.name + (s.bundle ? ' (bundle)' : '') }))));
    setSel.value = setId || '';
    b.replaceChildren(el('div', { class: 'cfc-bar-row' }, [
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: '←',
                        title: 'The cell before (← or p)', onclick: () => goTo(at - 1) }),
      el('strong', { class: 'cells-which', text: 'Cell ' + c.id + '  ·  '
        + (at + 1) + ' of ' + n }),
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: '→',
                        title: 'The next cell (→ or n)', onclick: () => goTo(at + 1) }),
      el('span', { class: 'cells-where', text: 'CSC ' + c.csc
        + (c.layer_name ? ' · ' + c.layer_name : ' · no layer said')
        + (c.rate_hz != null ? ' · ' + c.rate_hz.toFixed(2) + ' Hz' : '')
        + ' · ' + Number(c.n || 0).toLocaleString() + ' spikes · curation v' + version }),
      el('div', { style: 'flex:1' }),
      el('span', { class: 'hint', text: 'Firing around' }),
      setSel,
      BARRY.ui.button({ kind: 'ghost', size: 'sm',
        text: aidWin && !aidWin.closed ? 'Focus the cards' : 'Reopen the cards',
        onclick: () => { openAids(); bar(); } }),
      BARRY.ui.modeEnd({
        more: [
          BARRY.ui.field({ label: 'Ticks', inline: true, control: BARRY.ui.seg([
            [false, 'Every cell', 'Every curated cell’s spikes, on its own contact'],
            [true, 'This cell', 'Only the cell on show']], only,
            (v) => { only = v; bar(); drawOverlay(); }) }),
          el('p', { class: 'hint', text: 'Each tick is one spike, on the contact '
            + 'where the cell is biggest, colored by that contact’s layer. '
            + 'Nothing here writes anything down.' }),
        ],
        bank: { text: 'Bank the cells…',
                title: 'One Cell entry for this recording, from curation v' + version,
                onclick: bankCells },
      }),
    ]));
    const whole = document.getElementById('modeBar') || b;
    const h = Math.ceil(whole.getBoundingClientRect().height);
    if (h) document.documentElement.style.setProperty('--bottom-bar', h + 'px');
  }

  function bankCells() {
    return BARRY.ui.bankDialog({
      kind: 'entry',
      title: 'Bank the cells of ' + (d.label || gid),
      name: 'Cells · ' + (d.label || gid),
      facts: [cells().length + ' cells from curation v' + version + '.',
              'One row per cell, its first to its last spike. The spikes stay '
              + 'in the sort folder.',
              d.entry ? 'Continues ‘' + d.entry.name + '’.' : 'A new entry.'],
      onBank: async ({ name, note }) => {
        const got = await apiPost('/api/cells/' + encodeURIComponent(gid) + '/bank',
                                  { version, name, note });
        toast('Banked: ‘' + got.name + '’, ' + got.n + ' cells.', 'ok', 7000);
      },
    });
  }

  /* ==================================================================
     The ticks over the traces
     ================================================================== */
  function mountOverlay() {
    if (overlay) overlay.remove();
    overlay = el('canvas', { class: 'cells-overlay', 'aria-hidden': 'true' });
    document.body.appendChild(overlay);
    window.addEventListener('resize', drawOverlay);
    window.addEventListener('scroll', drawOverlay, true);
  }

  /* Told by Xplorefinder whenever the window moves (xplore.js setWindow). */
  function refresh() {
    if (!sess) return;
    clearTimeout(winTimer);
    winTimer = setTimeout(fetchWindow, 120);
    drawOverlay();
  }

  async function fetchWindow() {
    if (!sess) return;
    const t0 = sess.t0 || 0, t1 = t0 + (sess.span || 0);
    const key = gid + '|' + version + '|' + t0.toFixed(3) + '|' + t1.toFixed(3);
    if (key === winKey) return;
    winKey = key;
    try {
      const got = await api('/api/cells/' + encodeURIComponent(gid) + '/window?t0='
                            + t0 + '&t1=' + t1 + '&version=' + version);
      if (key !== winKey) return;
      win = got;
      drawOverlay();
    } catch (e) { /* the ticks just stay as they were */ }
  }

  function drawOverlay() {
    if (!overlay || !sess) return;
    const X = BARRY.views.xplore;
    const dpr = window.devicePixelRatio || 1;
    const W = window.innerWidth, H = window.innerHeight;
    overlay.width = Math.round(W * dpr);
    overlay.height = Math.round(H * dpr);
    overlay.style.width = W + 'px';
    overlay.style.height = H + 'px';
    const ctx = overlay.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    if (!win || !X.laneRows) return;
    const lanes = X.laneRows(0);
    if (!lanes || !lanes.numbers || !lanes.numbers.length) return;
    const t0 = sess.t0 || 0, span = sess.span || 0;
    const a = X.clientAtTime(t0, 0), b = X.clientAtTime(t0 + span, 0);
    if (!a || !b || !(span > 0)) return;
    const laneH = lanes.height / lanes.numbers.length;
    const pick = cur();
    const ink = getComputedStyle(document.documentElement)
      .getPropertyValue('--mode-cells').trim() || '#8fd3ff';
    for (const c of win.cells || []) {
      const mine = pick && c.id === pick.id;
      if (only && !mine) continue;
      /* Its own contact, or -- when that one is not shown (the even ones
         only, say) -- the nearest one that is. */
      let i = lanes.numbers.indexOf(c.csc);
      if (i < 0) {
        let best = Infinity;
        lanes.numbers.forEach((n, k) => {
          const dd = Math.abs(Number(n) - Number(c.csc));
          if (dd < best) { best = dd; i = k; }
        });
        if (best > 2) continue;
      }
      const y = lanes.top + (i + 0.5) * laneH;
      const h = Math.max(4, Math.min(laneH * (mine ? 0.9 : 0.6), 26));
      ctx.strokeStyle = c.layer_color || ink;
      ctx.globalAlpha = mine ? 0.95 : 0.45;
      ctx.lineWidth = mine ? 2 : 1;
      ctx.beginPath();
      for (const t of c.t || []) {
        const x = a.x + (t - t0) / span * (b.x - a.x);
        ctx.moveTo(x, y - h / 2);
        ctx.lineTo(x, y + h / 2);
      }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  /* ==================================================================
     The cards window
     ================================================================== */
  function tellAid() {
    if (aidWin && !aidWin.closed && aidWin.barryCellsAid) {
      try { aidWin.barryCellsAid.openerMoved(); } catch (e) { /* closing */ }
    }
  }

  /* What the cards window asks for: one answer to "what is on show". */
  function context() {
    if (!d) return null;
    return {
      gid, label: d.label, version, cell: cur(), cells: cells(),
      set: setId, sets: sets || [], invert: sess ? sess.invert !== false : true,
      polarity: d.polarity || null,
    };
  }

  return {
    enter, exit, refresh, context, goTo,
    get active() { return !!sess; },
    _state: () => ({ gid, version, at, only, setId, win, cells: cells().length }),
  };
}());

window.barryCells = BARRY.cells;
BARRY.modes.register('cells', BARRY.cells);

/* ==========================================================================
   The cards window (/?role=cells#cells): one card each for the cell on
   show -- waveform, ISI, autocorrelogram, rate, amplitude, firing around
   the set picked in Xplorefinder's bar. Drawn on canvases from numbers.
   ========================================================================== */
BARRY.views.cells = (function () {
  let ctx = null;
  let shownKey = null;
  let cellData = null;
  let peth = null;

  function opener() {
    try {
      const o = window.opener;
      if (o && !o.closed && o.barryCells && o.barryCells.context) return o;
    } catch (e) { /* gone */ }
    return null;
  }

  function onShow() { openerMoved(); }

  async function openerMoved() {
    const o = opener();
    const host = document.getElementById('cellsBody');
    if (!host) return;
    if (!o) {
      host.replaceChildren(el('p', { class: 'hint', text: 'Open this from '
        + 'Xplorefinder: Kilosort › Cells › Open in Xplorefinder.' }));
      return;
    }
    try { ctx = o.barryCells.context(); } catch (e) { ctx = null; }
    if (!ctx || !ctx.cell) return;
    const key = ctx.gid + '|' + ctx.version + '|' + ctx.cell.id;
    const pkey = key + '|' + (ctx.set || '');
    if (key !== shownKey) {
      shownKey = key;
      cellData = null;
      peth = null;
      paint();
      try {
        cellData = await api('/api/cells/' + encodeURIComponent(ctx.gid) + '/cell/'
                             + ctx.cell.id + '?version=' + ctx.version
                             + '&invert=' + (ctx.invert ? 1 : 0));
      } catch (e) { cellData = { error: e.message }; }
      if (shownKey !== key) return;
      paint();
    }
    if (ctx.set && (!peth || peth.key !== pkey)) {
      peth = { key: pkey, loading: true };
      paint();
      try {
        const got = await apiPost('/api/cells/' + encodeURIComponent(ctx.gid) + '/peth',
          { version: ctx.version, entry_id: ctx.set, cells: [ctx.cell.id] });
        if (peth.key !== pkey) return;
        peth = Object.assign({ key: pkey }, got);
      } catch (e) { peth = { key: pkey, error: e.message }; }
      paint();
    } else if (!ctx.set && peth) {
      peth = null;
      paint();
    }
  }

  const css = (name, fb) => getComputedStyle(document.documentElement)
    .getPropertyValue(name).trim() || fb;

  function canvasCard(title, sub, drawFn, h) {
    const cv = el('canvas', { class: 'cells-cv' });
    const card = el('div', { class: 'card cells-card' }, [
      el('div', { class: 'section-label', text: title }),
      sub ? el('p', { class: 'hint cells-sub', text: sub }) : null,
      cv,
    ].filter(Boolean));
    requestAnimationFrame(() => {
      const w = Math.max(200, cv.clientWidth || 320);
      const hh = h || 150;
      const dpr = window.devicePixelRatio || 1;
      cv.width = Math.round(w * dpr); cv.height = Math.round(hh * dpr);
      cv.style.height = hh + 'px';
      const g = cv.getContext('2d');
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      drawFn(g, w, hh);
    });
    return card;
  }

  function axes(g, w, h, pad) {
    g.strokeStyle = css('--line', '#444');
    g.lineWidth = 1;
    g.beginPath();
    g.moveTo(pad.l, pad.t); g.lineTo(pad.l, h - pad.b); g.lineTo(w - pad.r, h - pad.b);
    g.stroke();
  }
  function text(g, s, x, y, align) {
    g.fillStyle = css('--text-3', '#999');
    g.font = '11px ' + (css('--mono', 'monospace'));
    g.textAlign = align || 'left';
    g.fillText(s, x, y);
  }
  function bars(g, w, h, vals, opt) {
    const pad = { l: 34, r: 8, t: 8, b: 20 };
    axes(g, w, h, pad);
    const max = Math.max(1, ...vals);
    const bw = (w - pad.l - pad.r) / Math.max(1, vals.length);
    g.fillStyle = opt.ink;
    vals.forEach((v, i) => {
      const bh = (h - pad.t - pad.b) * v / max;
      g.fillRect(pad.l + i * bw, h - pad.b - bh, Math.max(1, bw - 0.5), bh);
    });
    text(g, String(max.toLocaleString()), pad.l - 4, pad.t + 8, 'right');
    text(g, opt.left, pad.l, h - 5, 'left');
    text(g, opt.right, w - pad.r, h - 5, 'right');
    if (opt.mid) text(g, opt.mid, pad.l + (w - pad.l - pad.r) / 2, h - 5, 'center');
  }
  function line(g, w, h, xs, ys, opt) {
    const pad = { l: 40, r: 8, t: 8, b: 20 };
    axes(g, w, h, pad);
    if (!xs.length) return;
    const x0 = xs[0], x1 = xs[xs.length - 1] || 1;
    const ymax = Math.max(...ys, 1e-9), ymin = opt.zero ? 0 : Math.min(...ys);
    const X = (x) => pad.l + (x - x0) / ((x1 - x0) || 1) * (w - pad.l - pad.r);
    const Y = (y) => h - pad.b - (y - ymin) / ((ymax - ymin) || 1) * (h - pad.t - pad.b);
    g.strokeStyle = opt.ink; g.lineWidth = 1.4;
    if (opt.dots) {
      g.fillStyle = opt.ink; g.globalAlpha = 0.5;
      xs.forEach((x, i) => g.fillRect(X(x) - 1, Y(ys[i]) - 1, 2, 2));
      g.globalAlpha = 1;
    } else {
      g.beginPath();
      xs.forEach((x, i) => (i ? g.lineTo(X(x), Y(ys[i])) : g.moveTo(X(x), Y(ys[i]))));
      g.stroke();
    }
    text(g, opt.top || ymax.toFixed(1), pad.l - 4, pad.t + 8, 'right');
    text(g, opt.left || '', pad.l, h - 5, 'left');
    text(g, opt.right || '', w - pad.r, h - 5, 'right');
  }

  function waveCard(wf) {
    const sub = wf ? 'Mean of ' + wf.n + ' spikes, high-passed at 300 Hz, on the '
      + wf.channels.length + ' contacts around it (best one bold) · trough '
      + wf.trough_uv + ' µV · drawn as Xplorefinder draws the traces'
      : 'The binary is not on this computer.';
    return canvasCard('Waveform', sub, (g, w, h) => {
      if (!wf) return;
      const chs = wf.channels;
      const rowH = (h - 16) / chs.length;
      const all = chs.flatMap((c) => c.uv);
      const amp = Math.max(1, Math.max(...all.map(Math.abs)));
      const ink = css('--mode-cells', '#8fd3ff');
      chs.forEach((c, k) => {
        const mid = 8 + (k + 0.5) * rowH;
        g.strokeStyle = c.best ? ink : css('--text-3', '#999');
        g.lineWidth = c.best ? 2 : 1;
        g.beginPath();
        c.uv.forEach((v, i) => {
          const x = 60 + i / (c.uv.length - 1) * (w - 70);
          const y = mid - v / amp * rowH * 1.6;
          if (i) g.lineTo(x, y); else g.moveTo(x, y);
        });
        g.stroke();
        text(g, 'CSC ' + c.csc, 52, mid + 4, 'right');
      });
      text(g, '−' + (wf.ms[wf.ms.length - 1]).toFixed(1) + ' ms', 60, h - 2, 'left');
      text(g, '+' + (wf.ms[wf.ms.length - 1]).toFixed(1) + ' ms', w - 10, h - 2, 'right');
    }, 260);
  }

  function pethCards() {
    if (!ctx || !ctx.set) {
      return [el('p', { class: 'hint', text: 'Pick a banked set in Xplorefinder’s '
        + 'bar (Firing around) to line this cell’s spikes up on its events.' })];
    }
    if (!peth || peth.loading) {
      return [el('p', { class: 'hint', text: 'Lining the spikes up on the set’s events…' })];
    }
    if (peth.error) return [el('p', { class: 'hint warn-line', text: peth.error })];
    const mine = (peth.cells || {})[String(ctx.cell.id)] || {};
    const labs = peth.labels || [];
    if (!labs.length) {
      return [el('p', { class: 'hint', text: '‘' + ((peth.entry || {}).name || '')
        + '’ has no events on this recording.' })];
    }
    const inkOf = (id) => (id === 'ds' || id === 'spike' ? css('--call-ds', '#4bc7f0')
      : id === 'pspike' || id === 'solid' ? css('--call-p', '#ff8a7a')
      : id === 'twilight' ? css('--call-amb', '#c08cf0') : css('--text-2', '#bbb'));
    return labs.map((lab) => {
      const p = mine[lab.id];
      if (!p) return null;
      const sub = lab.n + ' events · ±' + (peth.half_s * 1000) + ' ms in '
        + (peth.bin_s * 1000) + ' ms bins · rate before them ' + p.baseline_hz
        + ' Hz · first ' + p.raster.length + ' events as rows';
      return canvasCard('Firing around ' + lab.label, sub, (g, w, h) => {
        const half = peth.half_s;
        const pad = { l: 40, r: 8 };
        const rH = 90;
        const rows = p.raster;
        const X = (t) => pad.l + (t + half) / (2 * half) * (w - pad.l - pad.r);
        g.fillStyle = inkOf(lab.id);
        rows.forEach((r, i) => {
          const y = 4 + i * (rH - 8) / Math.max(1, rows.length);
          r.forEach((t) => g.fillRect(X(t), y, 1.2, Math.max(1, (rH - 8) / Math.max(1, rows.length) - 0.5)));
        });
        g.strokeStyle = css('--text-3', '#999');
        g.setLineDash([3, 3]);
        g.beginPath(); g.moveTo(X(0), 0); g.lineTo(X(0), h); g.stroke();
        g.setLineDash([]);
        const hz = p.hz;
        const max = Math.max(1, ...hz);
        const bw = (w - pad.l - pad.r) / hz.length;
        const top = rH + 6, bot = h - 20;
        hz.forEach((v, i) => {
          const bh = (bot - top) * v / max;
          g.fillRect(pad.l + i * bw, bot - bh, Math.max(1, bw - 0.5), bh);
        });
        text(g, max.toFixed(0) + ' Hz', pad.l - 4, top + 8, 'right');
        text(g, '−' + half * 1000 + ' ms', pad.l, h - 5, 'left');
        text(g, 'the event', X(0), h - 5, 'center');
        text(g, '+' + half * 1000 + ' ms', w - pad.r, h - 5, 'right');
      }, 230);
    }).filter(Boolean);
  }

  function paint() {
    const host = document.getElementById('cellsBody');
    if (!host || !ctx) return;
    const c = ctx.cell;
    const head = el('div', { class: 'cells-head' }, [
      el('h2', { text: 'Cell ' + c.id }),
      el('p', { class: 'hint', text: (ctx.label || ctx.gid) + ' · CSC ' + c.csc
        + (c.layer_name ? ' · ' + c.layer_name : ' · no layer said') + ' · '
        + c.depth_um + ' µm · ' + Number(c.n).toLocaleString() + ' spikes'
        + (c.rate_hz != null ? ' · ' + c.rate_hz.toFixed(2) + ' Hz' : '')
        + ' · curation v' + ctx.version }),
      ctx.polarity ? el('p', { class: 'hint' + (ctx.polarity.ok ? '' : ' warn-line'),
                                text: ctx.polarity.words }) : null,
    ].filter(Boolean));
    if (!cellData) {
      host.replaceChildren(head, el('p', { class: 'hint', text: 'Reading the cell…' }));
      return;
    }
    if (cellData.error) {
      host.replaceChildren(head, el('p', { class: 'hint warn-line', text: cellData.error }));
      return;
    }
    const cd = cellData;
    const ink = css('--mode-cells', '#8fd3ff');
    const isi = cd.isi || {};
    const acg = cd.acg || {};
    const grid = el('div', { class: 'cells-grid' }, [
      waveCard(cd.waveform),
      canvasCard('Intervals between spikes',
        (isi.refractory != null ? (isi.refractory * 100).toFixed(2) + '% under '
          + isi.refractory_ms + ' ms' : '') + ' · 0.5 ms bins',
        (g, w, h) => bars(g, w, h, isi.counts || [], { ink, left: '0', right: '50 ms',
                                                       mid: '25' })),
      canvasCard('Autocorrelogram', '1 ms bins, ±50 ms' + (acg.of && acg.n
        && acg.of < acg.n ? ' · counted on ' + acg.of.toLocaleString() + ' of '
        + acg.n.toLocaleString() + ' spikes' : ''),
        (g, w, h) => bars(g, w, h, acg.counts || [], { ink, left: '−50 ms',
                                                       right: '+50 ms', mid: '0' })),
      canvasCard('Rate through the recording', (cd.rate || {}).bin_s + ' s bins',
        (g, w, h) => line(g, w, h, (cd.rate || {}).t || [], (cd.rate || {}).hz || [],
          { ink, zero: true, left: '0 s', right: Math.round(cd.duration_s || 0) + ' s',
            top: Math.max(...((cd.rate || {}).hz || [0])).toFixed(1) + ' Hz' })),
      canvasCard('Amplitude through the recording', 'Kilosort’s amplitude per spike',
        (g, w, h) => line(g, w, h, (cd.amplitude || {}).t || [], (cd.amplitude || {}).a || [],
          { ink, dots: true, left: '0 s', right: Math.round(cd.duration_s || 0) + ' s' })),
    ].concat(pethCards()));
    host.replaceChildren(head, grid);
  }

  return { onShow, openerMoved, paint };
}());

window.barryCellsAid = BARRY.views.cells;
