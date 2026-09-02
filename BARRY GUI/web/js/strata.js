/* ==========================================================================
   strata.js -- StrataScope: saying which layer each channel is in.

   The standalone version worked on four exported PNGs. You uploaded a voltage
   raster, a CSD, a multiunit plot and a theta plot, cropped each one down to
   the heatmap, and then trusted that 64 evenly spaced rows landed on the
   right channels.

   The crop is the whole problem. It is per-image, it has to be redone every
   time anyone re-exports, and when it is slightly off every label is off by a
   fraction of a channel with nothing on screen to say so.

   Here the panels are drawn from the recording, so BARRY already knows which
   lane is channel 14. There is nothing to crop and nothing to drift. And
   because it is not a snapshot, you can filter, change the window, or zoom
   into the theta while you decide -- which is what you actually want when a
   boundary is ambiguous.

   The rail is aligned to the raster's lanes by measurement, not by assuming
   even spacing: the pane reports where each lane is, and the rail follows.
   ========================================================================== */
'use strict';

BARRY.strata = (function () {
  let sheet = null;      // the layer sheet as the server has it
  let regions = [];      // the vocabulary
  let sess = null;
  let gid = null;
  let brush = null;      // the region a click paints, or null to pick per-row
  let hover = -1;
  let saving = 0;

  /* ==================================================================
     Entering and leaving
     ================================================================== */
  async function enter(gidIn) {
    gid = gidIn;
    let info;
    try {
      info = await api('/api/layers/' + encodeURIComponent(gid));
    } catch (e) {
      info = null;
    }

    let sessRow = info && info.session;
    if (!sessRow) {
      try {
        const r = await api('/api/registry/' + encodeURIComponent(gid));
        sessRow = r.session;
      } catch (e) {
        toast('No such recording: ' + e.message, 'err', 8000);
        return false;
      }
    }
    const path = (sessRow.here || [])[0];
    if (!path) {
      toast('None of this recording’s paths are reachable from this '
            + 'machine, so there is nothing to look at.', 'err', 9000);
      return false;
    }

    setView('xplore');
    sess = await BARRY.views.xplore.open(path);
    if (!sess) return false;

    // The channel order as it is right now: even-only and missing files both
    // change it, so it is sent on every visit rather than trusted from the
    // first one.
    const channels = sess.info.channels.map((c) => c.number);
    let started;
    try {
      started = await apiPost('/api/layers/' + encodeURIComponent(gid)
                              + '/start', { channels });
    } catch (e) {
      toast('Could not open the layer sheet: ' + e.message, 'err', 8000);
      return false;
    }
    sheet = started.sheet;
    regions = sheet.regions || [];

    layout();
    sess.strata = { gid, labels: sheet.labels, regions };
    render();
    // The panes settle a frame or two after the layout change, and the rail
    // is measured off them.
    requestAnimationFrame(() => setTimeout(alignRail, 260));
    window.addEventListener('resize', alignRail);

    BARRY.activity.log('strata.enter', {
      gid, channels: channels.length,
      labelled: (sheet.progress || {}).labelled,
    }, sess);
    return true;
  }

  function exit() {
    if (!sheet) return;
    BARRY.activity.log('strata.leave', {
      gid, labelled: (sheet.progress || {}).labelled,
    }, sess);
    if (sess) delete sess.strata;
    sheet = null; sess = null; gid = null; brush = null;
    const rail = $('#strataRail');
    if (rail) rail.remove();
    const bar = $('#strataBar');
    if (bar) bar.remove();
    const body = $('#xfBody');
    if (body) body.classList.remove('strata-on');
    window.removeEventListener('resize', alignRail);
    document.removeEventListener('keydown', keys, true);
    if (BARRY.views.xplore.refreshAll) BARRY.views.xplore.refreshAll();
  }

  /* The four views the standalone version made you export and upload. Live,
     and already aligned. */
  function layout() {
    BARRY.views.xplore.setPanes([
      { panel: 'voltage' },
      { panel: 'csd' },
      { panel: 'theta' },
      { panel: 'traces' },
    ], { col: 0.5, row: 0.5 });
  }

  /* ==================================================================
     The rail
     ================================================================== */
  const channels = () => (sess && sess.info.channels) || [];
  const labelOf = (num) => (sheet && sheet.labels[String(num)]) || null;
  const regionOf = (id) => regions.find((r) => r.id === id) || null;

  function render() {
    if (!sheet) return;
    bar();
    rail();
    if (BARRY.views.xplore.redraw) BARRY.views.xplore.redraw();
  }

  function bar() {
    let b = $('#strataBar');
    if (!b) {
      b = el('div', { class: 'strata-bar', id: 'strataBar' });
      const body = $('#xfBody');
      if (body) body.appendChild(b); else document.body.appendChild(b);
      document.addEventListener('keydown', keys, true);
    }
    b.innerHTML = '';

    const pr = sheet.progress || {};
    b.appendChild(el('div', { class: 'cur-where' }, [
      el('strong', { text: 'StrataScope' }),
      el('span', { class: 'cur-sub',
                   text: sheet.session_label || gid }),
      el('span', { class: 'cur-count',
                   text: pr.labelled + ' / ' + pr.total + ' channels' }),
    ]));

    b.appendChild(el('div', { class: 'cur-prog' }, [
      el('i', { style: 'width:' + (pr.percent || 0) + '%' }),
      el('span', { text: (pr.left || 0) + ' left' }),
    ]));

    /* A brush, because a shank passes through a layer for a run of channels
       and clicking a dropdown per channel is sixty-four dropdowns. Pick a
       layer, then click or drag down the rail. */
    const brushes = el('div', { class: 'strata-brushes' });
    brushes.appendChild(el('button', {
      class: 'strata-brush' + (brush === null ? ' on' : ''),
      title: 'No brush — each row keeps its own picker',
      onclick: () => { brush = null; render(); },
    }, [el('span', { text: 'Pick' })]));
    regions.forEach((r, i) => {
      brushes.appendChild(el('button', {
        class: 'strata-brush' + (brush === r.id ? ' on' : ''),
        style: '--cat:' + r.color,
        title: r.name + (r.note ? ' — ' + r.note : '')
             + (i < 9 ? '   (' + (i + 1) + ')' : ''),
        onclick: () => { brush = brush === r.id ? null : r.id; render(); },
      }, [
        i < 9 ? el('kbd', { text: String(i + 1) }) : null,
        el('span', { text: r.name }),
      ].filter(Boolean)));
    });
    b.appendChild(brushes);

    b.appendChild(el('div', { class: 'cur-nav' }, [
      el('button', {
        class: 'mini', text: '⤓ Fill down',
        title: 'Give every unlabelled channel the label of the one above it',
        onclick: fillDown,
      }),
      el('button', {
        class: 'mini', text: 'Clear', onclick: clearAll,
      }),
      el('span', { class: 'cur-saving', id: 'strataSaving', text: '' }),
      el('div', { style: 'flex:1' }),
      el('button', {
        class: 'btn ghost sm', text: 'Export CSV',
        onclick: () => window.open('/api/layers/' + encodeURIComponent(gid)
                                   + '/export', '_blank'),
      }),
      el('button', { class: 'btn ghost sm', text: 'Leave', onclick: exit }),
    ]));
  }

  /* One row per channel, sitting exactly on the raster's lane for it.

     The lane geometry comes from the pane rather than from an assumption of
     even spacing -- the whole reason this beats labelling a PNG is that the
     alignment is measured, not guessed. */
  function rail() {
    let r = $('#strataRail');
    const host = $('#paneGrid');
    if (!host) return;
    if (!r) {
      r = el('div', { class: 'strata-rail', id: 'strataRail' });
      host.parentNode.insertBefore(r, host);
      // The body has to become a positioning context and give the grid room;
      // the rail is laid over the left edge rather than woven into the flex
      // column, which would put it above the panes rather than beside them.
      const body = $('#xfBody');
      if (body) body.classList.add('strata-on');
    }
    r.innerHTML = '';

    r.appendChild(el('div', { class: 'strata-head' }, [
      el('span', { text: 'Layer' }),
      el('span', { class: 'strata-n', text: channels().length + ' ch' }),
    ]));

    const list = el('div', { class: 'strata-rows' });
    let painting = false;
    channels().forEach((c, i) => {
      const id = labelOf(c.number);
      const reg = regionOf(id);
      const row = el('div', {
        class: 'strata-row' + (id ? ' has' : '') + (hover === i ? ' hl' : ''),
        style: reg ? '--cat:' + reg.color : '',
        onmouseenter: () => {
          hover = i;
          if (painting && brush) paint(c.number, brush);
        },
        onmousedown: (e) => {
          if (!brush) return;
          e.preventDefault();
          painting = true;
          paint(c.number, e.shiftKey ? null : brush);
        },
      }, [
        el('span', { class: 'strata-num', text: String(c.number) }),
        el('span', { class: 'strata-sw' }),
        brush
          ? el('span', { class: 'strata-name',
                         text: reg ? reg.name : '—' })
          : el('select', {
              onchange: (e) => paint(c.number, e.target.value || null),
            }, [el('option', { value: '', text: '—' })].concat(
              regions.map((rg) => el('option', {
                value: rg.id, text: rg.name,
                selected: id === rg.id ? 'selected' : null,
              })))),
      ]);
      list.appendChild(row);
    });
    window.addEventListener('mouseup', () => { painting = false; },
                            { once: true });
    r.appendChild(list);
    alignRail();
  }

  /* Put the rail's rows on the raster's lanes.

     Measured from the pane's own canvas box, so it stays right when the pane
     is resized, the chrome is hidden, or the window changes -- none of which
     a cropped PNG could survive. */
  function alignRail() {
    const r = $('#strataRail');
    const canvas = document.querySelector(
      '#paneGrid .pane .pane-canvas-host');
    if (!r || !canvas) return;
    const rows = r.querySelector('.strata-rows');
    if (!rows) return;
    const box = canvas.getBoundingClientRect();
    const railBox = r.getBoundingClientRect();
    // The raster's plot area, as drawPane lays it out.
    const padTop = 8, padBottom = 22;
    const top = box.top - railBox.top + padTop;
    const height = Math.max(1, box.height - padTop - padBottom);
    rows.style.top = top + 'px';
    rows.style.height = height + 'px';
    const n = channels().length || 1;
    rows.style.setProperty('--lane', (height / n) + 'px');
  }

  /* ==================================================================
     Changing
     ================================================================== */
  async function paint(channel, region) {
    if (!sheet) return;
    const key = String(channel);
    const was = sheet.labels[key] || null;
    if (was === region) return;
    if (region) sheet.labels[key] = region; else delete sheet.labels[key];
    recount();
    render();

    saving += 1;
    updateSaving();
    try {
      const res = await apiPost('/api/layers/' + encodeURIComponent(gid)
                                + '/set', { channel, region });
      sheet = res.sheet;
    } catch (e) {
      if (was) sheet.labels[key] = was; else delete sheet.labels[key];
      toast('That did not save: ' + e.message, 'err', 8000);
      render();
    } finally {
      saving -= 1;
      updateSaving();
    }
  }

  function recount() {
    const total = channels().length;
    const done = channels().filter((c) => labelOf(c.number)).length;
    sheet.progress = {
      total, labelled: done, left: total - done,
      percent: total ? Math.round(1000 * done / total) / 10 : 0,
    };
  }

  async function fillDown() {
    try {
      const res = await apiPost('/api/layers/' + encodeURIComponent(gid)
                                + '/fill',
                                { channels: channels().map((c) => c.number) });
      sheet = res.sheet;
      if (sess) sess.strata.labels = sheet.labels;
      toast('Filled ' + res.filled + ' channel(s) downward.', 'ok');
      render();
    } catch (e) { toast(e.message, 'err', 7000); }
  }

  async function clearAll() {
    try {
      const res = await apiPost('/api/layers/' + encodeURIComponent(gid)
                                + '/clear', {});
      sheet = res.sheet;
      if (sess) sess.strata.labels = sheet.labels;
      render();
    } catch (e) { toast(e.message, 'err'); }
  }

  function updateSaving() {
    const n = $('#strataSaving');
    if (n) n.textContent = saving ? 'saving…' : '';
  }

  function keys(e) {
    if (!sheet || isTyping(e)) return;
    const k = e.key;
    if (k === 'Escape') { e.preventDefault(); exit(); return; }
    const i = parseInt(k, 10);
    if (i >= 1 && i <= 9 && regions[i - 1]) {
      e.preventDefault();
      brush = brush === regions[i - 1].id ? null : regions[i - 1].id;
      render();
    }
  }

  /* ==================================================================
     The overlay on the rasters
     ================================================================== */
  function draw(ctx, s, win, x0, plotW, y0, plotH, P) {
    if (!s || !s.strata || !sheet) return;
    const chans = channels();
    if (!chans.length) return;
    const lane = plotH / chans.length;

    ctx.save();
    ctx.globalAlpha = 0.16;
    for (let i = 0; i < chans.length; i++) {
      const reg = regionOf(labelOf(chans[i].number));
      if (!reg) continue;
      ctx.fillStyle = reg.color;
      ctx.fillRect(x0, y0 + i * lane, plotW, Math.ceil(lane));
    }

    // A firm line where the layer changes: that boundary is the thing being
    // decided, and a wash of colour alone does not show exactly where it fell.
    ctx.globalAlpha = 0.85;
    ctx.lineWidth = 1;
    let prev = null;
    for (let i = 0; i < chans.length; i++) {
      const id = labelOf(chans[i].number);
      if (prev !== null && id !== prev) {
        const reg = regionOf(id) || regionOf(prev);
        ctx.strokeStyle = reg ? reg.color : P.accent;
        ctx.beginPath();
        ctx.moveTo(x0, Math.round(y0 + i * lane) + 0.5);
        ctx.lineTo(x0 + plotW, Math.round(y0 + i * lane) + 0.5);
        ctx.stroke();
      }
      prev = id;
    }
    ctx.restore();
  }

  return {
    enter, exit, draw, alignRail,
    get active() { return !!sheet; },
    get state() {
      return sheet ? { gid, labels: sheet.labels,
                       progress: sheet.progress, brush } : null;
    },
  };
})();
