/* ==========================================================================
   monolith_events.js -- the Monolith's fourth tab: events first.

   The Monolith asks what changed in fixed windows. This asks it the other
   way round (the lab meeting, 2026-10-02): find large positive deflections
   in the dorsal hippocampus wherever they fall in the cue session (P300-
   like), then show when they happen against the cues and which other
   regions moved with them. Descriptive, rat by rat; pooled as means and
   counts, never tested.

   The work is backend/monoevents.py, run in Jarvis from the local
   originals; this page sets it off, follows it, and draws what it found.
   Load order: after monolith.js.
   ========================================================================== */
'use strict';

window.MONO_EVENTS = (function () {
  const M = () => window.MONO;
  const G = () => window.MONO_FIGS;
  const KEY = 'barry.monolith.events';
  const NS = 'http://www.w3.org/2000/svg';
  const E = { p: null, rep: null, err: null, loading: false, work: null, runErr: null,
              day: 'Precon1', ex: null, exErr: null, exAt: null, seq: 0, exSeq: 0 };
  const el = (...a) => M().el(...a);
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  function sv(tag, attrs, text) {
    const n = document.createElementNS(NS, tag);
    for (const k in (attrs || {})) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  const num = (v, d) => (v == null || !isFinite(v) ? '—' : Number(v).toFixed(d == null ? 2 : d));
  const SAY = { region: 'Region', low: 'Band, low edge (Hz)', high: 'Band, high edge (Hz)', z: 'Threshold (robust z)',
                zmax: 'Ceiling: above this is an artifact (z)', min_ms: 'Narrowest (ms, at half height)',
                max_ms: 'Widest (ms, at half height)', refractory_ms: 'At least this long after the last (ms)' };
  const WIN = ['pre', 'cue1', 'cue2', 'post', 'iti'];

  function recall() {
    try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { return null; }
  }
  function remember() {
    try { localStorage.setItem(KEY, JSON.stringify(E.p)); } catch (e) { /* per viewer only */ }
  }
  const query = (p) => Object.keys(p || {}).map((k) => k + '=' + encodeURIComponent(p[k])).join('&');

  async function load() {
    const seq = ++E.seq;
    E.loading = true;
    render();
    try {
      const got = await M().getJSON('/events' + (E.p ? '?' + query(E.p) : ''));
      if (seq !== E.seq) return;
      E.rep = got;
      E.p = Object.assign({}, got.params);
      E.err = null;
    } catch (e) {
      if (seq !== E.seq) return;
      E.err = e.message;
    }
    E.loading = false;
    render();
  }
  function show() {
    if (!E.p) E.p = recall();
    if (!E.rep || E.err) load();
    else render();
  }
  async function run() {
    E.runErr = null;
    try {
      const got = await M().postJSON('/events', Object.assign({}, E.p, { confirm: true }));
      E.work = (got.work || {}).progress || {};
      render();
      follow();
    } catch (e) {
      E.runErr = e.message;
      render();
    }
  }
  async function stop() {
    try { await M().postJSON('/stop', {}); } catch (e) { /* the poll says */ }
  }
  /* Follow the work until it ends, then read the report again. */
  async function follow() {
    for (;;) {
      let w = null;
      try { w = ((await M().getJSON('/status')) || {}).work; } catch (e) { break; }
      if (!w || w.what !== 'events' || w.status !== 'running') {
        E.work = null;
        if (w && w.what === 'events' && w.status === 'failed') E.runErr = w.error || 'it failed';
        break;
      }
      E.work = w.progress || {};
      render();
      await new Promise((r) => setTimeout(r, 1500));
    }
    load();
  }

  /* ---------------- the pictures ---------------- */
  // Events a minute against time from cue 1, each session a line, the
  // windows behind.
  function psthFig(rep) {
    const W = 640, H = 220, m = { l: 44, r: 10, t: 22, b: 30 };
    const s = sv('svg', { viewBox: '0 0 ' + W + ' ' + H, class: 'mfig evpsth', width: '100%', style: 'max-width:' + W + 'px',
                          role: 'img', 'aria-label': 'Events a minute against time from cue 1' });
    const days = Object.keys(rep.pooled || {});
    const P0 = (rep.pooled[days[0]] || {}).psth || { from: -10, to: 30, bin: 1 };
    const x0 = P0.from, x1 = P0.to;
    let ymax = 1e-9;
    for (const d of days) {
      const P = rep.pooled[d].psth;
      (P.mean || []).forEach((v, i) => { if (v != null) ymax = Math.max(ymax, v + ((P.se || [])[i] || 0)); });
    }
    const X = (t) => m.l + (t - x0) / (x1 - x0) * (W - m.l - m.r);
    const Y = (v) => H - m.b - v / ymax * (H - m.t - m.b);
    // The windows, as the presentations had them (cue 1 and cue 2 about ten seconds each).
    const bands = [['pre', -10, 0, 'Pre-baseline'], ['cue1', 0, 10, 'Cue 1'], ['cue2', 10, 20, 'Cue 2'], ['post', 20, 30, 'Post-baseline']];
    bands.forEach(([id, a, b, name], i) => {
      s.appendChild(sv('rect', { x: X(a), y: m.t, width: X(b) - X(a), height: H - m.t - m.b,
        fill: i % 2 ? css('--chip') : css('--surface-2'), 'data-win': id }));
      s.appendChild(sv('text', { x: (X(a) + X(b)) / 2, y: m.t - 7, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-2') }, name));
    });
    for (let v = 0; v <= ymax; v += niceStep(ymax)) {
      s.appendChild(sv('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: css('--line'), 'stroke-width': 0.6 }));
      s.appendChild(sv('text', { x: m.l - 4, y: Y(v) + 3, 'text-anchor': 'end', 'font-size': 9.5, fill: css('--ink-3') }, String(+v.toFixed(2))));
    }
    for (let t = x0; t <= x1; t += 5) {
      s.appendChild(sv('text', { x: X(t), y: H - m.b + 13, 'text-anchor': 'middle', 'font-size': 9.5, fill: css('--ink-3') }, String(t)));
    }
    s.appendChild(sv('text', { x: (m.l + W - m.r) / 2, y: H - 3, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-3') }, 's from cue 1'));
    s.appendChild(sv('text', { x: 2, y: 12, 'font-size': 10, fill: css('--ink-3') }, 'events / min'));
    const col = { Precon1: css('--ink-3'), Precon4: css('--up') };
    for (const d of days) {
      const P = rep.pooled[d].psth;
      const mid = (P.mean || []).map((_v, i) => P.from + (i + 0.5) * P.bin);
      // SE band, then the mean.
      let up = '', dn = '';
      mid.forEach((t, i) => {
        const v = P.mean[i], e = (P.se || [])[i] || 0;
        if (v == null) return;
        up += (up ? 'L' : 'M') + X(t).toFixed(1) + ',' + Y(v + e).toFixed(1);
        dn = 'L' + X(t).toFixed(1) + ',' + Y(Math.max(0, v - e)).toFixed(1) + dn;
      });
      if (up) s.appendChild(sv('path', { d: up + dn + 'Z', fill: col[d] || css('--ink'), 'fill-opacity': 0.15, stroke: 'none' }));
      let path = '';
      mid.forEach((t, i) => { const v = P.mean[i]; if (v != null) path += (path ? 'L' : 'M') + X(t).toFixed(1) + ',' + Y(v).toFixed(1); });
      s.appendChild(sv('path', { d: path, fill: 'none', stroke: col[d] || css('--ink'), 'stroke-width': 2, 'data-day': d }));
    }
    return s;
  }
  function niceStep(v) {
    const raw = v / 4, p = Math.pow(10, Math.floor(Math.log10(raw)));
    return [1, 2, 5, 10].map((k) => k * p).find((k) => k >= raw) || raw;
  }
  // One region's event-locked average (solid) against random times (dashed).
  function erpFig(r, name, fs, half, ylim) {
    const W = 200, H = 96, m = { l: 6, r: 6, t: 16, b: 14 };
    const s = sv('svg', { viewBox: '0 0 ' + W + ' ' + H, class: 'mfig everp', width: '100%', style: 'max-width:' + W + 'px',
                          role: 'img', 'aria-label': name + ': event-locked average', 'data-region': name });
    s.appendChild(sv('text', { x: m.l, y: 11, 'font-size': 10, fill: css('--ink'), 'font-weight': 600 }, name.replace(/^Left /, 'L ').replace(/^Right /, 'R ')));
    if (!r || !r.erp) {
      s.appendChild(sv('text', { x: W / 2, y: H / 2 + 4, 'text-anchor': 'middle', 'font-size': 9.5, fill: css('--ink-3') },
        r && r.rats === 0 ? 'no rat has it' : 'not measured'));
      return s;
    }
    const n = r.erp.length;
    const X = (i) => m.l + i / (n - 1) * (W - m.l - m.r);
    const Y = (v) => m.t + (H - m.t - m.b) / 2 - v / ylim * (H - m.t - m.b) / 2;
    s.appendChild(sv('line', { x1: X((n - 1) / 2), x2: X((n - 1) / 2), y1: m.t, y2: H - m.b, stroke: css('--line-2'), 'stroke-dasharray': '2 3' }));
    s.appendChild(sv('line', { x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0), stroke: css('--line'), 'stroke-width': 0.6 }));
    const line = (ys, attrs) => {
      let d = '';
      ys.forEach((v, i) => { if (v != null) d += (d ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(Math.max(-ylim, Math.min(ylim, v))).toFixed(1); });
      s.appendChild(sv('path', Object.assign({ d, fill: 'none' }, attrs)));
    };
    if (r.random) line(r.random, { stroke: css('--ink-3'), 'stroke-width': 1, 'stroke-dasharray': '3 3', class: 'rand' });
    line(r.erp, { stroke: css('--up'), 'stroke-width': 1.6, class: 'erp' });
    s.appendChild(sv('text', { x: m.l, y: H - 3, 'font-size': 9, fill: css('--ink-3') }, '−' + half + ' s'));
    s.appendChild(sv('text', { x: W - m.r, y: H - 3, 'text-anchor': 'end', 'font-size': 9, fill: css('--ink-3') }, '+' + half + ' s'));
    return s;
  }

  /* ---------------- the page ---------------- */
  function settings(rep) {
    const p = E.p || (rep && rep.params) || {};
    const regions = (rep && rep.regions) || ['Right DHC', 'Left DHC'];
    const box = el('div', { class: 'evctl', id: 'evctl' });
    const inputs = {};
    for (const k of Object.keys(SAY)) {
      let input;
      if (k === 'region') {
        input = el('select', { id: 'ev-region' }, regions.map((n) => el('option', { value: n, text: n, selected: n === p.region ? 'selected' : null })));
      } else {
        input = el('input', { type: 'number', id: 'ev-' + k, value: p[k] != null ? String(p[k]) : '', step: k === 'low' ? '0.1' : 'any' });
      }
      inputs[k] = input;
      box.appendChild(el('label', { class: 'evset' }, [el('span', { class: 'small', text: SAY[k] }), input]));
    }
    const read = () => {
      const q = {};
      for (const k of Object.keys(SAY)) q[k] = k === 'region' ? inputs[k].value : Number(inputs[k].value);
      return q;
    };
    box.appendChild(el('div', { class: 'hrow evbtns' }, [
      el('button', { type: 'button', class: 'more-btn', id: 'ev-apply', text: 'Use these settings',
                     onclick: () => { E.p = read(); remember(); load(); } }),
      el('button', { type: 'button', class: 'linkish', id: 'ev-defaults', text: 'Back to the defaults',
                     onclick: () => { E.p = Object.assign({}, (rep || {}).defaults || {}); remember(); load(); } })]));
    return box;
  }

  function render() {
    const host = document.getElementById('evpane');
    if (!host || !M()) return;
    host.innerHTML = '';
    const rep = E.rep;
    const card = el('div', { class: 'card evwrap', id: 'events' });
    host.appendChild(card);
    card.appendChild(el('div', { class: 'hrow' }, [el('h2', { text: 'Events first: hippocampal P300-like events' }), M().qh('events')]));
    card.appendChild(el('p', { class: 'lede', text: 'Turned the other way round: instead of asking what changed in fixed windows, find the '
      + 'large positive deflections in the dorsal hippocampus wherever they fall in the cue session, then ask when they '
      + 'happen against the cues and which other regions moved with them. Descriptive: each rat is compared with random '
      + 'times in its own session; across rats there are only means and counts, no test.' }));
    card.appendChild(el('details', { class: 'evsettings', open: !rep || rep.todo ? 'open' : null }, [
      el('summary', { text: 'Settings' + (rep ? ': ' + rep.params.region + ', ' + rep.params.low + '–' + rep.params.high + ' Hz, z ≥ '
        + rep.params.z + ', ' + rep.params.min_ms + '–' + rep.params.max_ms + ' ms wide' : '') }),
      settings(rep)]));
    if (E.err) { card.appendChild(el('p', { class: 'warn', text: 'Could not read the events: ' + E.err })); return; }
    if (!rep) { card.appendChild(el('p', { class: 'loading', text: 'Reading what is done…' })); return; }
    const total = rep.days.length, done = total - rep.todo;
    const st = el('div', { class: 'evstatus', id: 'evstatus' });
    st.appendChild(el('p', {}, [el('strong', { text: done + ' of ' + total + ' rat-sessions done' }), ' for these settings.']));
    if (E.work) {
      const w = E.work;
      st.appendChild(el('p', { class: 'small', id: 'evprogress', text: 'Finding them: ' + (w.of ? (w.i + 1) + ' of ' + w.of + ' · ' : '') + (w.item || 'starting') }));
      st.appendChild(el('button', { type: 'button', class: 'lbtn', id: 'ev-stop', text: 'Stop', onclick: stop }));
    } else if (rep.todo) {
      const min = Math.max(1, Math.round(rep.estimate_s / 60));
      st.appendChild(el('button', { type: 'button', class: 'more-btn', id: 'ev-run',
        text: 'Find the events in the other ' + rep.todo + ' (about ' + min + ' min)', onclick: run }));
      st.appendChild(el('p', { class: 'small muted', text: 'Runs here, in Jarvis: reads each cue session’s wires from the original '
        + 'recordings on this computer (read only) — whole sessions are too much to page from the VACC copy.' }));
    }
    if (E.runErr) st.appendChild(el('p', { class: 'warn', text: E.runErr }));
    card.appendChild(st);
    if (!done) return;

    // 1. When they happen.
    const sec1 = el('div', { class: 'evsec', id: 'evtiming' }, [el('h3', { text: 'When they happen' })]);
    sec1.appendChild(el('p', { class: 'small muted', text: 'Events a minute, from 10 s before cue 1 to 30 s after it, every presentation '
      + 'stacked; each session the mean over rats, its standard error shaded. Precon1 grey, Precon4 red.' }));
    sec1.appendChild(psthFig(rep));
    const days = Object.keys(rep.pooled || {});
    const tb = el('table', { class: 'linetable evrates' }, [el('thead', {}, [el('tr', {}, [el('th', { text: 'Window' })]
      .concat(days.map((d) => el('th', { text: d + ' (events / min, ' + rep.pooled[d].rats + ' rats)' }))))])]);
    const body = el('tbody');
    for (const w of WIN) {
      body.appendChild(el('tr', { 'data-win': w }, [el('td', { text: rep.window_say[w] })].concat(days.map((d) => {
        const r = rep.pooled[d].rate_per_min[w] || {};
        return el('td', { class: 'num', text: num(r.mean) + (r.se != null ? ' ± ' + num(r.se) : '') });
      }))));
    }
    tb.appendChild(body);
    sec1.appendChild(tb);
    card.appendChild(sec1);

    // 2. Which regions moved with them.
    if (!days.includes(E.day)) E.day = days[0];
    const P = rep.pooled[E.day];
    const sec2 = el('div', { class: 'evsec', id: 'evcoord' }, [el('div', { class: 'hrow' }, [el('h3', { text: 'Which regions moved with them' }),
      el('div', { class: 'seg', role: 'group' }, days.map((d) => el('button', { type: 'button', 'data-id': d, 'aria-pressed': String(d === E.day), text: d,
        onclick: () => { E.day = d; render(); } })))])]);
    sec2.appendChild(el('p', { class: 'small muted', text: 'Each region’s wire, ±' + rep.snip_s + ' s around each event, band-passed as the '
      + 'detection was, averaged over the events (red) and over twice as many random times in the same session (dashed). Size: '
      + 'how much bigger its average is within ±250 ms than averages of random times are (z, mean over rats, and how many rats '
      + 'beat random times at p < .05). Phase: how much more consistent its 4–12 Hz phase against the hippocampus is at the '
      + 'events than at random times.' }));
    const names = rep.regions;
    const measured = names.filter((n) => (P.regions[n] || {}).rats);
    const busy = measured.filter((n) => n !== rep.params.region && (P.regions[n].size_rats || 0) >= Math.ceil(P.rats / 2));
    if (measured.length > 3 && busy.length >= 0.75 * (measured.length - 1)) {
      sec2.appendChild(el('p', { class: 'warn', id: 'evglobal', text: 'These events show up in almost every region (' + busy.length + ' of '
        + (measured.length - 1) + ' others, in most rats). Something every wire shares — the reference, movement, chewing — makes '
        + 'that pattern too; open a few events below before reading them as hippocampal.' }));
    }
    let ylim = 1e-9;
    for (const n of names) for (const v of ((P.regions[n] || {}).erp || [])) if (v != null) ylim = Math.max(ylim, Math.abs(v));
    sec2.appendChild(el('div', { class: 'evgrid', id: 'evgrid' }, names.map((n) => erpFig(P.regions[n], n, rep.out_fs, rep.snip_s, ylim))));
    const ct = el('table', { class: 'linetable evtable', id: 'evregions' }, [el('thead', {}, [el('tr', {},
      ['Region', 'Rats', 'Size z', 'Rats beating random (size)', 'Phase z', 'Rats beating random (phase)'].map((t) => el('th', { text: t })))])]);
    const cb = el('tbody');
    for (const n of names) {
      const r = P.regions[n] || {};
      cb.appendChild(el('tr', { 'data-region': n }, r.rats ? [
        el('td', { text: n + (n === rep.params.region ? ' (the events’ own)' : '') }), el('td', { class: 'num', text: String(r.rats) }),
        el('td', { class: 'num', text: num(r.z_size, 1) }), el('td', { class: 'num', text: r.size_rats + ' of ' + r.rats }),
        el('td', { class: 'num', text: n === rep.params.region ? '—' : num(r.z_plv, 1) }),
        el('td', { class: 'num', text: n === rep.params.region ? '—' : r.plv_rats + ' of ' + r.plv_of })]
        : [el('td', { text: n }), el('td', { class: 'muted', colspan: '5', text: 'no rat has a usable wire here' })]));
    }
    ct.appendChild(cb);
    sec2.appendChild(ct);
    card.appendChild(sec2);

    // 3. Rat by rat.
    const sec3 = el('div', { class: 'evsec', id: 'evrats' }, [el('h3', { text: 'Rat by rat' })]);
    const rt = el('table', { class: 'linetable' }, [el('thead', {}, [el('tr', {}, ['Rat', 'Session', 'Wire', 'Events', 'Usable', 'Cue 1', 'Cue 2', 'Between', 'Example']
      .map((t) => el('th', { text: t })))])]);
    const rb = el('tbody');
    for (const d of rep.days) {
      if (!d.done) { rb.appendChild(el('tr', {}, [el('td', { text: 'r' + d.rat }), el('td', { text: d.day }), el('td', { colspan: '7', class: 'muted', text: 'not done yet' })])); continue; }
      if (d.why) { rb.appendChild(el('tr', {}, [el('td', { text: 'r' + d.rat }), el('td', { text: d.day }), el('td', { colspan: '7', class: 'muted', text: d.why })])); continue; }
      const rate = d.timing.rate_per_min;
      rb.appendChild(el('tr', { 'data-rat': String(d.rat), 'data-day': d.day }, [
        el('td', { text: 'r' + d.rat }), el('td', { text: d.day }), el('td', { text: 'CSC' + d.wire }),
        el('td', { class: 'num', text: String(d.n_events) }), el('td', { class: 'num', text: num(d.usable_s / 60, 0) + ' min' }),
        el('td', { class: 'num', text: num(rate.cue1) }), el('td', { class: 'num', text: num(rate.cue2) }), el('td', { class: 'num', text: num(rate.iti) }),
        el('td', {}, d.n_events ? [el('button', { type: 'button', class: 'linkish', text: 'Open one', onclick: () => openExample(d.rat, d.day, 0) })] : [])]));
    }
    rt.appendChild(rb);
    sec3.appendChild(el('div', { class: 'dtwrap' }, [rt]));
    sec3.appendChild(el('p', { class: 'small muted', text: 'Rates are events a minute in each window over the session’s presentations, and '
      + 'between them. Usable: the session time away from the rail.' }));
    card.appendChild(sec3);

    // 4. One event, every region.
    const sec4 = el('div', { class: 'evsec', id: 'evexample' }, [el('h3', { text: 'One event, every region' })]);
    if (!E.exAt) sec4.appendChild(el('p', { class: 'small muted', text: 'Open one from the table above to see every region’s trace around it.' }));
    else {
      const d = rep.days.find((x) => x.rat === E.exAt.rat && x.day === E.exAt.day) || { events: [] };
      const evs = d.events || [];
      const i = E.exAt.i;
      const ev = evs[i] || {};
      sec4.appendChild(el('div', { class: 'hrow' }, [
        el('button', { type: 'button', class: 'lbtn', text: '←', disabled: i <= 0 ? 'disabled' : null, onclick: () => openExample(E.exAt.rat, E.exAt.day, i - 1) }),
        el('span', { class: 'small', id: 'evexsay', text: 'r' + E.exAt.rat + ' · ' + E.exAt.day + ' · event ' + (i + 1) + ' of ' + evs.length + ' · '
          + num(ev.t, 1) + ' s, z ' + num(ev.z, 1) + ', ' + num(ev.width_ms, 0) + ' ms wide · ' + (rep.window_say[ev.where] || '')
          + (ev.rel != null ? ' (' + num(ev.rel, 2) + ' s from cue 1)' : '') }),
        el('button', { type: 'button', class: 'lbtn', text: '→', disabled: i >= evs.length - 1 ? 'disabled' : null, onclick: () => openExample(E.exAt.rat, E.exAt.day, i + 1) })]));
      if (E.exErr) sec4.appendChild(el('p', { class: 'warn', text: E.exErr }));
      else if (!E.ex) sec4.appendChild(el('p', { class: 'loading', text: 'Reading every region around it…' }));
      else {
        const X = E.ex;
        const rows = X.rows.filter((r) => r.band);
        const n = rows.length ? rows[0].band.length : 0;
        const t = Array.from({ length: n }, (_v, k) => -X.half + k / X.out_fs);
        const series = rows.map((r, k) => ({ y: r.band, short: r.region.replace(/^Left /, 'L ').replace(/^Right /, 'R '),
          label: r.region + ' · CSC' + r.wire, color: r.region === rep.params.region ? css('--up') : css('--ink'), zero: true }));
        if (series.length) sec4.appendChild(G().traces(t, series, { w: 760, rowH: 40, marks: [{ name: 'event', t0: 0, t1: 0 }], label: 'every region around the event' }));
        const gone = X.rows.filter((r) => !r.band);
        if (gone.length) sec4.appendChild(el('p', { class: 'small muted', text: 'Not drawn: ' + gone.map((r) => r.region + ' (' + r.why + ')').join(', ') + '.' }));
      }
    }
    card.appendChild(sec4);
  }

  async function openExample(rat, day, i) {
    E.exAt = { rat, day, i };
    E.ex = null; E.exErr = null;
    render();
    const seq = ++E.exSeq;
    try {
      const got = await M().getJSON('/events/example?rat=' + rat + '&day=' + encodeURIComponent(day) + '&i=' + i + '&' + query(E.p));
      if (seq !== E.exSeq) return;
      E.ex = got;
    } catch (e) {
      if (seq !== E.exSeq) return;
      E.exErr = e.message;
    }
    render();
    const n = document.getElementById('evexample');
    if (n && n.scrollIntoView) n.scrollIntoView({ block: 'nearest' });
  }

  return { show, load, render, openExample, get state() { return E; } };
})();
