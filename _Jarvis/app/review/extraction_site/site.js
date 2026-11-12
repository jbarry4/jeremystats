/* ==========================================================================
   site.js -- The Extraction Room's results, as a site of their own (asked
   2026-11-11). Assembled by tools/export_extraction.py from
   review/extraction_site with the room's data; edit those, not the copy.

   Two steps before anything is shown: the password (middleware.js, the
   same gate as Joe's site with its own cookie), then the acknowledgement on
   this page -- three boxes ticked and NOT FINAL typed -- asked once per
   browser tab. The data is only fetched after it.

   What is shown is the room as Rain and Shahriar left it: each set's newest
   extraction, the usual tests, Low KO under 10%, the separable calls made
   by hand counted. The sentences are worked out here from the numbers, so a
   rebuilt site says what its own numbers say. A p under 0.05 is a lead;
   only a q under 0.05 (Round II, across all its measures) holds.
   ========================================================================== */
'use strict';

(function () {
  const ACK = 'er_ack_v1';
  const S = {
    idx: null, sets: {}, set: null, err: null,
    tab: 'summary', mode: 'sink', way: 'two', grp: 'all',
  };
  const live = [];          // canvases to draw again when their width changes
  let clipN = 0;

  /* ---------- small things ---------- */
  function el(tag, attrs, kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'text') n.textContent = v;
      else if (k === 'class') n.className = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? '' : v);
    }
    for (const c of [].concat(kids || [])) if (c) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    return n;
  }
  function sv(tag, attrs, kids) {
    const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'text') n.textContent = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const c of [].concat(kids || [])) if (c) n.appendChild(c);
    return n;
  }
  const tok = (name, fb) => (getComputedStyle(document.documentElement).getPropertyValue(name) || fb || '').trim() || fb;
  const fmt = (v, d) => (v == null || !isFinite(v) ? '—' : Number(v).toFixed(d == null ? 3 : d));
  const sgn = (v, d) => (v == null || !isFinite(v) ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(Number(v)).toFixed(d == null ? 3 : d));
  const pw = (p) => (p == null ? '—' : p < 0.001 ? '< 0.001' : '= ' + String(Number((+p).toPrecision(2))));
  const sig = (p) => p != null && p < 0.05;
  const pc = (v) => (v == null ? '—' : Math.round(v * 100) + '%');
  const isCtl = (g) => String(g || '').toUpperCase() === 'CTL';
  const plural = (n, one, many) => n + ' ' + (n === 1 ? one : (many || one + 's'));
  const day = (at) => { try { return new Date(at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }); } catch (e) { return at || ''; } };
  const koText = (k) => (k == null ? '—' : String(+(+k).toFixed(2)) + '%');
  const D = () => S.sets[S.set];

  const GROUPS = { two: ['CTL', 'PTEN'], three: ['CTL', 'Low KO', 'High KO'] };
  const GCOL = { CTL: '--g-ctl', PTEN: '--g-pten', 'Low KO': '--g-low', 'High KO': '--g-high' };
  const TEST = { welch: 'Welch’s t-test', mwu: 'Mann–Whitney', anova: 'one-way ANOVA', kw: 'Kruskal–Wallis' };
  const POST = { tukey: 'Tukey', dunn: 'Dunn’s, Holm' };
  const WAYS = [['two', 'PTEN vs CTL'], ['three', 'CTL · Low KO · High KO'], ['ko', 'Against %KO, PTEN only']];
  const groupOf = (v, way) => (way === 'two' ? (isCtl(v.group) ? 'CTL' : 'PTEN') : isCtl(v.group) ? 'CTL' : v.ko_group);

  function unitOf(m) {
    if (m.unit === 'um') return 'µm';
    if (m.unit === 'uV') return 'µV';
    if (m.unit === '/min') return 'events per minute';
    if (m.unit === 'dB' || m.unit === 'ms') return m.unit;
    if (m.unit === 'ratio') return '×';
    if (m.unit === 'share') return '';
    return ((D().recordings || [])[0] || {}).unit || '';
  }
  const showV = (m, v) => (v == null || !isFinite(v) ? '—' : m.unit === 'share' ? Math.round(v * 100) + '%'
    : (m.unit === 'um' || m.unit === 'uV') ? fmt(v, 0)
    : (m.unit === '/min' || m.unit === 'dB' || m.unit === 'ms' || m.unit === 'ratio') ? fmt(v, 2)
    : fmt(v, 3));

  /* ---------- the acknowledgement ---------- */
  function acked() { try { return sessionStorage.getItem(ACK) === '1'; } catch (e) { return false; } }
  function setupAck() {
    const form = document.getElementById('ackForm');
    const boxes = Array.from(form.querySelectorAll('input[type=checkbox]'));
    const typed = document.getElementById('ackType');
    const go = document.getElementById('ackGo');
    const left = document.getElementById('ackLeft');
    const said = () => typed.value.trim().replace(/\s+/g, ' ').toUpperCase() === 'NOT FINAL';
    function check() {
      const n = boxes.filter((b) => !b.checked).length;
      const ok = !n && said();
      go.disabled = !ok;
      typed.classList.toggle('said', said());
      const todo = [n ? plural(n, 'box', 'boxes') + ' to tick' : null, said() ? null : 'NOT FINAL to type'].filter(Boolean);
      left.textContent = ok ? 'Thank you.' : 'Still ' + todo.join(' and ') + '.';
    }
    form.addEventListener('input', check);
    form.addEventListener('change', check);
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      check();
      if (go.disabled) return;
      try { sessionStorage.setItem(ACK, '1'); } catch (err) { /* asked again next time */ }
      openResults();
    });
    check();
  }

  /* ---------- loading ---------- */
  async function getJson(url) {
    const r = await fetch(url, { credentials: 'same-origin', cache: 'no-cache' });
    if (r.status === 401 || (r.redirected && /login\.html/.test(r.url))) {
      location.href = '/login.html?next=' + encodeURIComponent(location.pathname);
      throw new Error('Signed out.');
    }
    if (!r.ok) throw new Error('HTTP ' + r.status + ' for ' + url);
    return r.json();
  }
  function readHash() {
    const h = new URLSearchParams(location.hash.slice(1));
    if (h.get('tab')) S.tab = h.get('tab');
    if (h.get('set')) S.set = h.get('set');
  }
  function writeHash() {
    try { history.replaceState(null, '', '#tab=' + encodeURIComponent(S.tab) + '&set=' + encodeURIComponent(S.set)); } catch (e) { /* fine */ }
  }
  async function openResults() {
    document.getElementById('ack').hidden = true;
    const box = document.getElementById('results');
    box.hidden = false;
    box.replaceChildren(el('p', { class: 'empty', text: 'Opening the results…' }));
    window.scrollTo(0, 0);
    try {
      S.idx = await getJson('data/index.json');
      const got = await Promise.all(S.idx.sets.map((s) => getJson('data/' + s.file)));
      got.forEach((d) => { S.sets[d.id] = d; });
      readHash();
      if (!S.sets[S.set]) S.set = S.idx.default;
      if (!TABS.some((t) => t[0] === S.tab)) S.tab = 'summary';
    } catch (e) {
      S.err = e.message;
    }
    render();
  }

  /* ---------- the page ---------- */
  const TABS = [['summary', 'Summary'], ['recordings', 'Recordings'], ['separation', 'Separation rate'],
                ['round1', 'Round I · shape'], ['round2', 'Round II · plain measures'], ['numbers', 'The numbers'],
                ['methods', 'How it was done']];

  function seg(items, value, on) {
    return el('div', { class: 'seg', role: 'group' }, items.map(([v, label, title]) =>
      el('button', { type: 'button', 'aria-pressed': String(v === value), title, text: label, onclick: () => on(v) })));
  }

  function render() {
    live.length = 0;
    const box = document.getElementById('results');
    if (S.err) { box.replaceChildren(el('p', { class: 'err', text: 'The results did not open: ' + S.err })); return; }
    writeHash();
    const body = { summary, recordings, separation, round1: () => roundTab(1), round2: () => roundTab(2),
                   numbers, methods }[S.tab] || summary;
    box.replaceChildren(intro(), tabs(), body(), foot());
    requestAnimationFrame(drawAll);
  }
  function go(tab) { S.tab = tab; render(); window.scrollTo({ top: document.querySelector('.tabs').offsetTop - 60, behavior: 'smooth' }); }

  function intro() {
    const d = D();
    const n = d.stats.groups || {};
    return el('section', { class: 'intro' }, [
      el('h1', { text: 'Dentate spikes in PTEN mice' }),
      el('p', { class: 'lede', text: 'What X-ray split into DS1 and DS2 on each recording, and whether anything differs between '
        + 'controls and PTEN knockouts. ' + plural(d.recordings.length, 'recording') + ', one per mouse: ' + (n.CTL || 0)
        + ' controls and ' + (n.PTEN || 0) + ' PTEN (' + (n['Low KO'] || 0) + ' Low KO, ' + (n['High KO'] || 0) + ' High KO).' }),
      el('div', { class: 'setbar' }, [
        el('span', { class: 'lab', text: 'Set' }),
        seg(S.idx.sets.map((s) => [s.id, s.name]), S.set, (v) => { S.set = v; render(); }),
        el('span', { class: 'small muted', text: 'v' + d.v + ' of the room · extracted ' + day(d.at) + (d.by ? ' by ' + d.by : '') }),
      ]),
      el('p', { class: 'small muted setnote', text: setNote() }),
    ]);
  }
  function setNote() {
    const names = S.idx.sets.map((s) => S.sets[s.id]).filter(Boolean);
    const gr = names.filter((d) => d.grace != null).map((d) => '“' + d.name + '” leaves ' + Math.round(d.grace * 100) + '%');
    return 'The sets are the same mice. They differ in how closely an event must look like a control’s dentate spike to count: '
      + 'a border is drawn around the controls’ DS and pulled in until a share of their own events falls outside'
      + (gr.length ? ' — ' + gr.join(', ') : '') + '. The bigger the share left out, the stricter the set.';
  }
  function tabs() {
    return el('div', { class: 'tabs', role: 'tablist' }, TABS.map(([k, label]) =>
      el('button', { type: 'button', role: 'tab', 'aria-selected': String(S.tab === k), text: label, onclick: () => go(k) })));
  }
  function foot() {
    const d = D();
    return el('p', { class: 'foot small muted', text: 'Preliminary. Rain and Shahriar are still fine-tuning things; nothing here '
      + 'is a final result. Built ' + day(S.idx.built) + ' from Jarvis’s Extraction Room: “' + d.name + '”, v' + d.v
      + ', extracted ' + day(d.at) + '. Barry lab, University of Vermont.' });
  }

  /* ---------- the verdicts (the room's "usual tests") ---------- */
  function verdict(m, way) {
    const u = m.usual || {};
    if (way === 'two') {
      const x = u.two || {};
      return x.why || x.p == null ? 'cannot tell' : sig(x.p) ? 'differs' : 'no clear difference';
    }
    if (way === 'three') {
      const x = u.three || {};
      if (x.why || x.p == null) return 'cannot tell';
      if (sig(x.jt_p)) return (x.jt_z < 0 ? 'falls' : 'rises') + ' CTL → Low → High';
      return sig(x.p) ? 'differs' : 'no clear difference';
    }
    const d = m.dose || {}, s = m.spearman || {};
    if (d.p == null && s.p == null) return 'cannot tell';
    if (sig(d.p)) return d.rho < 0 ? 'falls as %KO rises' : 'rises with %KO';
    if (sig(s.p)) return (s.rho < 0 ? 'lower' : 'higher') + ' in PTEN, no dose trend';
    return 'no trend with %KO';
  }
  const HIT = (v) => /^(differs|falls|rises)/.test(v);
  function pOf(m, way) {
    const u = m.usual || {};
    if (way === 'two') return (u.two || {}).p;
    if (way === 'three') { const x = u.three || {}; const ps = [x.p, x.jt_p].filter((p) => p != null); return ps.length ? Math.min(...ps) : null; }
    return (m.dose || {}).p;
  }
  const qOf = (m, way) => ((m.q_usual || {})[way === 'ko' ? 'ko' : way]);
  const whyTest = (t) => (t.normal_p == null ? ''
    : t.test === 'welch' || t.test === 'anova' ? ' (residuals look normal, Shapiro–Wilk p ' + pw(t.normal_p) + ')'
      : ' (residuals not normal, Shapiro–Wilk p ' + pw(t.normal_p) + ', so ranks)');
  function detail(m, way) {
    const u = m.usual || {};
    if (way === 'two') {
      const t = m.two || {}, x = u.two || {};
      return 'PTEN ' + showV(m, (t.pten || {}).mean) + ' ± ' + showV(m, (t.pten || {}).sem) + ' (n ' + ((t.pten || {}).n || 0)
        + ') vs CTL ' + showV(m, (t.ctl || {}).mean) + ' ± ' + showV(m, (t.ctl || {}).sem) + ' (n ' + ((t.ctl || {}).n || 0) + '), mean ± SEM'
        + (x.why ? ' · ' + x.why : ' · ' + TEST[x.test] + ' p ' + pw(x.p) + whyTest(x) + ' · Hedges’ g ' + sgn(t.g, 2));
    }
    if (way === 'three') {
      const h = m.three || {}, x = u.three || {};
      return GROUPS.three.map((g) => g + ' ' + showV(m, (h[g] || {}).mean) + ' (n ' + ((h[g] || {}).n || 0) + ')').join(' · ')
        + (x.why ? ' · ' + x.why : ' · in order, CTL → Low KO → High KO (Jonckheere–Terpstra) p ' + pw(x.jt_p)
           + ' · ' + TEST[x.test] + ' p ' + pw(x.p) + whyTest(x)
           + ' · pairs (' + POST[x.post] + '): ' + (x.pairs || []).map((p) => p.a + '–' + p.b + ' p ' + pw(p.p)).join(', '));
    }
    const d = m.dose || {}, s = m.spearman || {};
    return 'The dose, among the PTEN mice alone: Spearman ρ ' + sgn(d.rho, 2) + ' · p ' + pw(d.p) + ' · n ' + (d.n || 0)
      + '. All mice, the controls at 0%: ρ ' + sgn(s.rho, 2) + ' · p ' + pw(s.p) + ' (mostly PTEN against controls).';
  }

  /* Everything a measure says under 0.05, every way at once: the summary's
     leads. */
  function signals(m) {
    const u = m.usual || {}, t2 = m.two || {}, out = [];
    const two = u.two || {}, three = u.three || {}, d = m.dose || {};
    if (!two.why && sig(two.p)) {
      const med = two.test === 'mwu';
      const a = (t2.pten || {})[med ? 'median' : 'mean'], b = (t2.ctl || {})[med ? 'median' : 'mean'];
      out.push({ way: 'two', p: two.p, q: (m.q_usual || {}).two,
        text: (a < b ? 'Lower' : 'Higher') + ' in PTEN than in controls: ' + showV(m, a) + ' against ' + showV(m, b)
          + ' (' + (med ? 'medians' : 'means') + '; ' + TEST[two.test] + ' p ' + pw(two.p) + ').' });
    }
    if (!three.why && sig(three.jt_p)) {
      out.push({ way: 'order', p: three.jt_p,
        text: (three.jt_z < 0 ? 'Falls' : 'Rises') + ' in order, CTL → Low KO → High KO (Jonckheere–Terpstra p ' + pw(three.jt_p) + ').' });
    }
    if (!three.why && sig(three.p)) {
      const pairs = (three.pairs || []).filter((p) => sig(p.p)).map((p) => p.a + ' vs ' + p.b + ', p ' + pw(p.p));
      out.push({ way: 'three', p: three.p, q: (m.q_usual || {}).three,
        text: 'Differs across CTL, Low KO and High KO (' + TEST[three.test] + ' p ' + pw(three.p) + ')'
          + (pairs.length ? '; the pair' + (pairs.length > 1 ? 's' : '') + ' that differ' + (pairs.length > 1 ? '' : 's') + ': '
             + pairs.join('; ') + '.' : '; no single pair differs on its own (' + POST[three.post] + ').') });
    }
    if (sig(d.p)) {
      out.push({ way: 'dose', p: d.p, q: (m.q_usual || {}).ko,
        text: (d.rho < 0 ? 'Falls' : 'Rises') + ' as %KO rises, among the PTEN mice (Spearman ρ ' + sgn(d.rho, 2) + ', p ' + pw(d.p) + ').' });
    }
    return out;
  }
  const minP = (sg) => Math.min(...sg.map((s) => s.p));

  /* ---------- plots ---------- */
  function swarm(items, cx, r, maxW) {
    const placed = [];
    for (const it of items.slice().sort((a, b) => a.y - b.y)) {
      let off = 0;
      for (let k = 0; k < 60; k++) {
        const o = (k % 2 ? 1 : -1) * Math.ceil(k / 2) * r * 1.05;
        if (Math.abs(o) > maxW) continue;
        if (placed.every((p) => (p.x - (cx + o)) ** 2 + (p.y - it.y) ** 2 >= (2 * r + 0.4) ** 2)) { off = o; break; }
      }
      it.x = cx + off;
      placed.push(it);
    }
    return items;
  }
  function dotTitle(v, m) {
    return v.label + ' · ' + (isCtl(v.group) ? 'control' : (v.ko_group || 'PTEN') + ', ' + koText(v.ko) + ' KO')
      + (m ? ' · ' + showV(m, v.value) + (unitOf(m) && unitOf(m) !== '×' ? ' ' + unitOf(m) : '') : '');
  }
  /* Round steps (1, 2, 2.5 or 5 of a power of ten), so an axis reads 0, 5,
     10, 15 rather than 4.63, 8.01, 11.40. */
  function niceTicks(lo, hi, n) {
    const raw = (hi - lo) / (n || 4);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((f) => f * mag).find((s) => s >= raw * 0.999);
    const a = Math.floor(lo / step + 1e-9) * step, b = Math.ceil(hi / step - 1e-9) * step;
    const ticks = [];
    for (let v = a; v <= b + step * 1e-6; v += step) ticks.push(+v.toPrecision(10));
    const dec = (String(+step.toPrecision(6)).split('.')[1] || '').length;
    return { lo: a, hi: b, ticks, text: (v) => (Math.abs(v) < step * 1e-6 ? '0' : v.toFixed(dec)) };
  }
  function axisY(root, ticks, text, Y, L, R0, W) {
    for (const v of ticks) {
      root.appendChild(sv('line', { class: 'grid', x1: L, x2: W - R0, y1: Y(v), y2: Y(v) }));
      root.appendChild(sv('text', { x: L - 6, y: Y(v) + 3.5, 'text-anchor': 'end', text: text(v) }));
    }
  }
  const unitLabel = (m) => (m.unit === '/min' ? 'per minute' : unitOf(m) === '×' ? '' : unitOf(m));
  const wordsOf = (m) => String(m.words || '').replace(/ -- /g, ' — ');
  function watermark(root, W, R0, T) {
    root.appendChild(sv('text', { class: 'wm', x: W - R0, y: T - 5, 'text-anchor': 'end', text: 'PRELIMINARY' }));
  }

  /* One dot per mouse, by group (or against %KO), with each group's mean
     and SEM -- the room's picture, drawn as SVG so it stays sharp. */
  function dotPlot(m, way) {
    const W = 400, H = way === 'ko' ? 242 : 232, L = 52, R0 = 12, T = 24, B = way === 'ko' ? 44 : 32;
    const pw_ = W - L - R0, ph = H - T - B;
    const vals = (m.values || []).filter((v) => v.value != null && isFinite(v.value));
    const root = sv('svg', { class: 'plot', viewBox: '0 0 ' + W + ' ' + H, role: 'img',
      'aria-label': m.name + ', one dot per mouse' });
    watermark(root, W, R0, T - 4);
    const u = unitLabel(m);
    if (u) root.appendChild(sv('text', { x: 4, y: T - 9, text: u }));
    if (!vals.length) {
      root.appendChild(sv('text', { x: W / 2, y: H / 2, 'text-anchor': 'middle', text: 'No values' }));
      return root;
    }
    let lo = Math.min(...vals.map((v) => v.value)), hi = Math.max(...vals.map((v) => v.value));
    if (m.unit === 'ratio') { lo = Math.min(lo, 1); hi = Math.max(hi, 1); }
    if (hi === lo) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.1;
    lo = lo >= 0 && lo - pad < 0 ? 0 : lo - pad; hi += pad;
    let ticks, text;
    if (m.unit === 'share') {
      lo = 0; hi = 1; ticks = [0, 0.25, 0.5, 0.75, 1]; text = pc;
    } else {
      const nt = niceTicks(lo, hi, 4);
      lo = nt.lo; hi = nt.hi; ticks = nt.ticks; text = nt.text;
    }
    const Y = (v) => T + ph - ((v - lo) / (hi - lo)) * ph;
    axisY(root, ticks, text, Y, L, R0, W);
    if (m.unit === 'ratio') root.appendChild(sv('line', { class: 'ref', x1: L, x2: W - R0, y1: Y(1), y2: Y(1) }));
    const r = 4.6;
    const dot = (it, col, hollow) => sv('circle', { class: 'dot' + (hollow ? ' hollow' : ''), cx: it.x, cy: it.y, r,
      style: hollow ? 'stroke:var(' + col + ')' : 'fill:var(' + col + ')', 'data-gid': it.v.gid,
      onclick: () => openRec(it.v.gid) }, [sv('title', { text: dotTitle(it.v, m) })]);
    if (way === 'ko') {
      const split = D().stats.split;
      const kmax = Math.max(30, ...vals.filter((v) => !isCtl(v.group)).map((v) => v.ko || 0));
      const X = (k) => L + 14 + (k / kmax) * (pw_ - 22);
      for (const k of [0, 10, 20, 30].filter((x) => x <= kmax)) {
        root.appendChild(sv('text', { x: X(k), y: T + ph + 15, 'text-anchor': 'middle', text: k + '%' }));
      }
      root.appendChild(sv('line', { class: 'split', x1: X(split), x2: X(split), y1: T, y2: T + ph }));
      root.appendChild(sv('text', { class: 'lab', x: L + pw_ / 2, y: H - 6, 'text-anchor': 'middle', text: '% KO (controls at 0, faded)' }));
      const fit = (m.dose || {}).fit;
      if (fit && fit.ko) {
        const id = 'clip' + (++clipN);
        root.appendChild(sv('clipPath', { id }, [sv('rect', { x: L, y: T, width: pw_, height: ph })]));
        root.appendChild(sv('line', { class: 'fit', 'clip-path': 'url(#' + id + ')', style: 'stroke:var(--g-pten)',
          x1: X(fit.ko[0]), x2: X(fit.ko[1]), y1: Y(fit.intercept + fit.slope * fit.ko[0]), y2: Y(fit.intercept + fit.slope * fit.ko[1]) }));
      }
      const ctl = swarm(vals.filter((v) => isCtl(v.group)).map((v) => ({ v, y: Y(v.value) })), X(0), r, 10);
      for (const it of ctl) { const c = dot(it, '--g-ctl'); c.setAttribute('opacity', '0.45'); root.appendChild(c); }
      for (const v of vals.filter((x) => !isCtl(x.group) && x.ko != null)) {
        root.appendChild(dot({ v, x: X(v.ko), y: Y(v.value) }, GCOL[v.ko_group] || '--g-pten'));
      }
      return root;
    }
    const names = GROUPS[way];
    const bw = pw_ / names.length;
    names.forEach((name, i) => {
      const mine = vals.filter((v) => groupOf(v, way) === name);
      const cx = L + bw * (i + 0.5);
      root.appendChild(sv('text', { class: 'lab', x: cx, y: H - 10, 'text-anchor': 'middle', text: name + ' · n ' + mine.length }));
      if (mine.length) {
        const xs = mine.map((v) => v.value);
        const mu = xs.reduce((a, b) => a + b, 0) / xs.length;
        const se = xs.length > 1 ? Math.sqrt(xs.reduce((a, b) => a + (b - mu) ** 2, 0) / (xs.length - 1)) / Math.sqrt(xs.length) : 0;
        const mx = cx + Math.min(46, bw * 0.34);
        root.appendChild(sv('line', { class: 'mean', x1: mx - 9, x2: mx + 9, y1: Y(mu), y2: Y(mu) }));
        if (se) {
          root.appendChild(sv('path', { class: 'err', fill: 'none',
            d: 'M' + mx + ' ' + Y(mu - se) + 'V' + Y(mu + se) + 'M' + (mx - 4) + ' ' + Y(mu - se) + 'h8M' + (mx - 4) + ' ' + Y(mu + se) + 'h8' }));
        }
      }
      const items = swarm(mine.map((v) => ({ v, y: Y(v.value) })), cx - Math.min(10, bw * 0.06), r, Math.min(34, bw * 0.26));
      for (const it of items) root.appendChild(dot(it, way === 'two' && name === 'PTEN' ? '--g-pten' : GCOL[name]));
    });
    return root;
  }

  /* Each group's share separable, with its Wilson 95% interval; under it a
     dot per mouse, filled if it separates. */
  function rateChart(sp, way) {
    const W = 400, H = 250, L = 44, R0 = 12, T = 18, B = 52;
    const pw_ = W - L - R0, ph = H - T - B;
    const Y = (f) => T + ph - f * ph;
    const root = sv('svg', { class: 'plot', viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': 'Share of mice where DS1 and DS2 separate, by group' });
    watermark(root, W, R0, T);
    for (const f of [0, 0.25, 0.5, 0.75, 1]) {
      root.appendChild(sv('line', { class: 'grid', x1: L, x2: W - R0, y1: Y(f), y2: Y(f) }));
      root.appendChild(sv('text', { x: L - 6, y: Y(f) + 3.5, 'text-anchor': 'end', text: Math.round(f * 100) + '%' }));
    }
    const names = GROUPS[way];
    const bw = pw_ / names.length;
    const src = (way === 'two' ? sp.two : sp.three) || {};
    const vals = (sp.values || []).filter((v) => v.sep === true || v.sep === false);
    names.forEach((name, i) => {
      const t = src[name] || {};
      const cx = L + bw * (i + 0.5);
      const col = name === 'PTEN' ? '--g-pten' : GCOL[name];
      if (t.n) {
        const w = Math.min(70, bw * 0.5);
        root.appendChild(sv('rect', { x: cx - w / 2, y: Y(t.rate || 0), width: w, height: Y(0) - Y(t.rate || 0), rx: 3,
          style: 'fill:var(' + col + ');fill-opacity:.32' }));
        root.appendChild(sv('line', { x1: cx - w / 2, x2: cx + w / 2, y1: Y(t.rate || 0), y2: Y(t.rate || 0), style: 'stroke:var(' + col + ');stroke-width:2.5' }));
        if (t.ci) {
          root.appendChild(sv('path', { class: 'err', fill: 'none',
            d: 'M' + cx + ' ' + Y(t.ci[0]) + 'V' + Y(t.ci[1]) + 'M' + (cx - 6) + ' ' + Y(t.ci[0]) + 'h12M' + (cx - 6) + ' ' + Y(t.ci[1]) + 'h12' }));
        }
        root.appendChild(sv('text', { class: 'lab', x: cx + w / 2 + 4, y: Y(t.rate || 0) + 4, text: pc(t.rate) }));
      }
      root.appendChild(sv('text', { class: 'lab', x: cx, y: T + ph + 16, 'text-anchor': 'middle', text: name + ' · ' + (t.yes || 0) + ' of ' + (t.n || 0) }));
      const mine = vals.filter((v) => groupOf(v, way) === name).sort((a, b) => (b.sep ? 1 : 0) - (a.sep ? 1 : 0));
      const step = 11, x0 = cx - ((mine.length - 1) * step) / 2;
      mine.forEach((v, k) => {
        root.appendChild(sv('circle', { class: 'dot' + (v.sep ? '' : ' hollow'), cx: x0 + k * step, cy: T + ph + 32, r: 4.3,
          style: v.sep ? 'fill:var(' + col + ')' : 'stroke:var(' + col + ')', onclick: () => openRec(v.gid) },
        [sv('title', { text: dotTitle(v) + ' · ' + (v.sep ? 'separable' : 'not separable') + (v.by_hand ? ' (called by hand)' : '') })]));
      });
    });
    return root;
  }

  /* ---------- Summary ---------- */
  function summary() {
    const d = D(), st = d.stats, r2 = d.round2, sp = st.separability || {};
    const wrap = el('div', {});
    // The three headlines.
    const t = sp.two || {}, h = sp.three || {};
    const sepHit = sig(t.boschloo_p);
    const r1 = st.metrics.map((m) => ({ m, sg: signals(m) })).filter((x) => x.sg.length);
    const r2l = r2.metrics.map((m) => ({ m, sg: signals(m) })).filter((x) => x.sg.length);
    const holds = r2l.filter((x) => x.sg.some((s) => sig(s.q)));
    const qmin = Math.min(...r2.metrics.flatMap((m) => ['two', 'three', 'ko'].map((w) => (m.q_usual || {})[w]).filter((q) => q != null)));
    const smallest = (ms) => {
      let best = null;
      for (const m of ms) for (const w of ['two', 'three', 'ko']) {
        const p = pOf(m, w);
        if (p != null && (!best || p < best.p)) best = { p, m, w };
      }
      return best ? ' The smallest p is ' + pw(best.p).replace('= ', '') + ' (' + best.m.name + ', ' + WAYS.find((x) => x[0] === best.w)[1] + ').' : '';
    };
    wrap.appendChild(el('div', { class: 'heads' }, [
      el('div', { class: 'card head' + (sepHit ? ' lead' : '') }, [
        el('div', { class: 'eyebrow', text: 'Separation rate' }),
        el('div', { class: 'big' }, [pc((t.CTL || {}).rate), el('small', { text: ' of controls · ' }),
          pc((t.PTEN || {}).rate), el('small', { text: ' of PTEN' })]),
        el('p', { text: 'DS1 and DS2 separate in ' + ((t.CTL || {}).yes || 0) + ' of ' + ((t.CTL || {}).n || 0) + ' controls and '
          + ((t.PTEN || {}).yes || 0) + ' of ' + ((t.PTEN || {}).n || 0) + ' PTEN mice. In order, CTL → Low KO → High KO: '
          + GROUPS.three.map((g) => pc((h[g] || {}).rate)).join(', ') + ' (trend p ' + pw(h.trend_p) + ').' }),
        el('span', { class: 'grow' }),
        el('div', { class: 'verdict-line' }, [
          el('span', { class: 'chip verdict ' + (sepHit ? 'tone-lead' : 'tone-none'),
            text: (sepHit ? 'differs' : 'no clear difference') + ' · Boschloo p ' + pw(t.boschloo_p) }),
          el('button', { type: 'button', class: 'link', text: 'The calls, mouse by mouse', onclick: () => go('separation') })]),
      ]),
      el('div', { class: 'card head' + (r1.length ? ' lead' : '') }, [
        el('div', { class: 'eyebrow', text: 'Round I · the shape of DS1 and DS2' }),
        el('div', { class: 'big' }, [String(r1.length), el('small', { text: ' of ' + st.metrics.length + ' measures differ' })]),
        el('p', { text: (r1.length
          ? 'Under 0.05 on its own: ' + r1.map((x) => x.m.name).join(', ') + '. Nothing is corrected across the '
            + st.metrics.length + ' measures.'
          : 'Sinks, sources, the distance between the two sinks and the share that are DS1: none differs between the groups, '
            + 'nor follows %KO.') + smallest(st.metrics) }),
        el('span', { class: 'grow' }),
        el('div', { class: 'verdict-line' }, [
          el('span', { class: 'chip verdict ' + (r1.length ? 'tone-lead' : 'tone-none'), text: r1.length ? 'leads only' : 'no difference' }),
          el('button', { type: 'button', class: 'link', text: 'Every measure', onclick: () => go('round1') })]),
      ]),
      el('div', { class: 'card head' + (r2l.length && !holds.length ? ' lead' : '') }, [
        el('div', { class: 'eyebrow', text: 'Round II · plain measures' }),
        el('div', { class: 'big' }, [String(r2l.length), el('small', { text: ' of ' + r2.metrics.length + ' show a lead' })]),
        el('p', { text: r2l.length
          ? 'Under 0.05 one way or another: ' + r2l.map((x) => x.m.name).join(', ') + '. '
            + (holds.length ? 'Holding across all ' + r2.metrics.length + ' measures (q under 0.05): ' + holds.map((x) => x.m.name).join(', ') + '.'
              : 'None holds once all ' + r2.metrics.length + ' are counted together (the smallest q is ' + fmt(qmin, 2) + ').')
          : 'Nothing under 0.05.' + smallest(r2.metrics) }),
        el('span', { class: 'grow' }),
        el('div', { class: 'verdict-line' }, [
          el('span', { class: 'chip verdict ' + (holds.length ? 'tone-hold' : r2l.length ? 'tone-lead' : 'tone-none'),
            text: holds.length ? 'holds after correction' : r2l.length ? 'leads, not findings' : 'no difference' }),
          el('button', { type: 'button', class: 'link', text: 'Every measure', onclick: () => go('round2') })]),
      ]),
    ]));

    // The leads, each with its picture.
    const leads = r2l.map((x) => Object.assign(x, { round: 2, of: r2.metrics.length }))
      .concat(r1.map((x) => Object.assign(x, { round: 1, of: st.metrics.length })))
      .sort((a, b) => minP(a.sg) - minP(b.sg));
    const sec = el('section', { class: 'section' }, [
      el('h2', { text: leads.length ? 'Leads worth a second look' : 'No leads in this set' }),
      el('p', { class: 'muted', text: leads.length
        ? 'Each is under 0.05 on at least one test, with the mice it rests on. A lead is a place to look harder, not a result: '
          + 'with this many measures, some cross 0.05 by luck alone. Click a dot to see that mouse’s recording.'
        : 'Nothing is under 0.05 on any of the usual tests.' }),
    ]);
    const others = S.idx.sets.filter((s) => s.id !== S.set).map((s) => S.sets[s.id]).filter(Boolean);
    const list = el('div', { class: 'stats', style: 'grid-template-columns:minmax(0,1fr)' });
    for (const x of leads) list.appendChild(leadCard(x, others));
    if (leads.length) sec.appendChild(list);
    wrap.appendChild(sec);

    wrap.appendChild(el('section', { class: 'section' }, [el('h2', { text: 'Read with care' }), care(leads)]));
    wrap.appendChild(el('section', { class: 'section' }, [el('h2', { text: 'Who is in it' }), cohort()]));
    return wrap;
  }

  function leadCard(x, others) {
    const m = x.m;
    const qs = x.sg.filter((s) => s.q != null);
    const hold = qs.some((s) => sig(s.q));
    const d = m.dose || {};
    const lines = x.sg.map((s) => el('li', { text: s.text }));
    const notes = [];
    if (x.round === 2) {
      notes.push(hold ? 'Holds across all ' + x.of + ' plain measures (q ' + pw(Math.min(...qs.map((s) => s.q))) + ').'
        : 'Not significant once all ' + x.of + ' plain measures are counted together'
          + (qs.length ? ' (q ' + pw(Math.min(...qs.map((s) => s.q))).replace('= ', '') + ')' : '') + '.');
    } else {
      notes.push('Nothing is corrected across the ' + x.of + ' shape measures.');
    }
    if (!x.sg.some((s) => s.way === 'dose') && d.p != null) {
      notes.push('Among the PTEN mice alone it does not follow %KO (Spearman ρ ' + sgn(d.rho, 2) + ', p ' + pw(d.p) + ').');
    }
    // The same measure in the other set(s): does the lead hold there too?
    for (const o of others) {
      const om = ((x.round === 2 ? o.round2 : o.stats).metrics || []).find((y) => y.key === m.key);
      if (!om) continue;
      const osg = signals(om);
      notes.push(osg.length ? 'Also under 0.05 in “' + o.name + '” (p ' + pw(minP(osg)).replace('= ', '') + ').'
        : 'Not under 0.05 in “' + o.name + '”.');
    }
    const h = m.three || {};
    const way = x.sg.some((s) => s.way === 'two') && !x.sg.some((s) => s.way === 'three' || s.way === 'order') ? 'two'
      : x.sg.some((s) => s.way === 'dose') && x.sg.length === 1 ? 'ko' : 'three';
    return el('div', { class: 'stat lead-card ' + (hold ? 'hold' : 'lead') }, [
      el('div', { class: 'says' }, [
        el('div', { class: 'stat-h' }, [el('h3', { text: m.name }),
          el('span', { class: 'chip verdict ' + (hold ? 'tone-hold' : 'tone-lead'), text: (x.round === 2 ? 'Round II' : 'Round I') + (hold ? ' · holds' : ' · lead') })]),
        el('span', { class: 'small muted', text: wordsOf(m) + (unitOf(m) && unitOf(m) !== '×' ? ' In ' + unitOf(m) + '.' : '') }),
        el('ul', {}, lines),
        el('span', { class: 'small num', text: 'Group means: ' + GROUPS.three.map((g) => g + ' ' + showV(m, (h[g] || {}).mean)).join(' · ')
          + ' · PTEN ' + showV(m, ((m.two || {}).pten || {}).mean) }),
        el('span', { class: 'small muted', text: notes.join(' ') }),
      ]),
      el('div', {}, [dotPlot(m, way), el('div', { class: 'small muted', style: 'text-align:center', text: WAYS.find((w) => w[0] === way)[1] })]),
    ]);
  }

  function care(leads) {
    const d = D(), st = d.stats, gr = st.groups || {};
    const items = [];
    items.push(plural(d.recordings.length, 'mouse', 'mice') + ', one recording each: ' + (gr.CTL || 0) + ' controls, ' + (gr['Low KO'] || 0)
      + ' Low KO and ' + (gr['High KO'] || 0) + ' High KO. With groups this small one mouse can move a p a long way; read the dots, not just the p.');
    items.push('A p under 0.05 here is a lead. Round II looks at ' + d.round2.metrics.length + ' measures three ways, so a few cross 0.05 by luck alone; '
      + 'its q (Benjamini–Hochberg) says what holds across all of them. Round I corrects nothing across its ' + st.metrics.length + '.');
    const dose = d.round2.metrics.concat(st.metrics).filter((m) => sig((m.dose || {}).p));
    items.push(dose.length ? 'Among the PTEN mice alone, ' + dose.map((m) => m.name).join(', ') + ' follow' + (dose.length === 1 ? 's' : '') + ' %KO.'
      : 'Among the PTEN mice alone, no measure follows %KO. Where PTEN differs from controls, that is a group difference, not a dose effect.');
    const kos = d.recordings.filter((r) => !isCtl(r.group) && r.ko != null).map((r) => r.ko).sort((a, b) => a - b);
    let gap = null;
    for (let i = 1; i < kos.length; i++) if (!gap || kos[i] - kos[i - 1] > gap[1] - gap[0]) gap = [kos[i - 1], kos[i]];
    if (gap && gap[1] - gap[0] >= 8) {
      items.push('No PTEN mouse has a %KO between ' + koText(gap[0]) + ' and ' + koText(gap[1]) + ', so “Low” and “High” KO are two clusters, '
        + 'and the middle of the range is not sampled.');
    }
    const hand = d.recordings.filter((r) => (r.call || {}).by_hand).length;
    if (hand) {
      items.push(plural(hand, 'separable call') + ' of ' + d.recordings.length + ' ' + (hand === 1 ? 'was' : 'were') + ' made by hand, where a '
        + 'person looking at the CSDs disagreed with X-ray’s test. They are counted as called.');
    }
    if ((d.left_out || []).length) {
      items.push('Left out when extracted: ' + d.left_out.map((x) => x.label + ' (' + x.why + ')').join('; ') + '.');
    }
    return el('ul', { class: 'care' }, items.map((t) => el('li', { text: t })));
  }

  function cohort() {
    const d = D(), split = d.stats.split;
    const pten = d.recordings.filter((r) => !isCtl(r.group)).sort((a, b) => (a.ko == null ? 999 : a.ko) - (b.ko == null ? 999 : b.ko));
    const ctl = d.recordings.filter((r) => isCtl(r.group));
    const gr = d.stats.groups || {};
    const kmax = Math.max(30, ...pten.map((r) => r.ko || 0));
    const rows = [];
    let crossed = false;
    pten.forEach((r) => {
      if (!crossed && r.ko != null && r.ko >= split) {
        crossed = true;
        const below = pten.filter((x) => x.ko != null && x.ko < split);
        if (below.length) {
          rows.push(el('div', { class: 'gap', text: 'Low KO is under ' + split + '% · nothing between ' + koText(below[below.length - 1].ko) + ' and ' + koText(r.ko) }));
        }
      }
      const col = GCOL[r.ko_group] || '--g-pten';
      const st = stateOf(r);
      rows.push(el('span', { class: 'm', text: r.mouse }));
      rows.push(el('div', { class: 'track', title: r.label }, [
        el('div', { class: 'fill', style: 'width:' + ((r.ko || 0) / kmax * 100) + '%;background:var(' + col + ')' }),
        el('div', { class: 'tick', style: 'left:' + (split / kmax * 100) + '%' }),
      ]));
      rows.push(el('span', { class: 'v', text: koText(r.ko) + ' · ' + (st === 'yes' ? 'separable' : st === 'no' ? 'not separable' : 'too few to call') }));
    });
    return el('div', { class: 'cohort' }, [
      el('div', {}, [
        el('div', { class: 'tally' }, [
          el('div', { class: 't' }, [el('b', { text: String(ctl.length) }), el('span', {}, [el('i', { class: 'sw', style: 'background:var(--g-ctl)' }), 'controls, 0% KO'])]),
          el('div', { class: 't' }, [el('b', { text: String(gr['Low KO'] || 0) }), el('span', {}, [el('i', { class: 'sw', style: 'background:var(--g-low)' }), 'Low KO, under ' + split + '%'])]),
          el('div', { class: 't' }, [el('b', { text: String(gr['High KO'] || 0) }), el('span', {}, [el('i', { class: 'sw', style: 'background:var(--g-high)' }), 'High KO, ' + split + '% or more'])]),
        ]),
        el('p', { class: 'small muted', style: 'margin-top:10px', text: '%KO is from the lab’s sheet (“JB % hits”); a control is 0% by rule. '
          + 'Controls: ' + ctl.map((r) => r.mouse).join(', ') + '.' }),
      ]),
      el('div', {}, [el('div', { class: 'small muted', style: 'margin-bottom:6px', text: 'Each PTEN mouse’s %KO, the dashed line at ' + split + '%' }),
        el('div', { class: 'kos' }, rows)]),
    ]);
  }

  /* ---------- Recordings ---------- */
  function stateOf(r) {
    const v = (r.call || {}).verdict;
    return v === 'yes' ? 'yes' : (v === 'no' || v === 'weak') ? 'no' : 'few';
  }
  const STATE = { yes: 'Separable', no: 'Not separable', few: 'Too few events to call' };
  const SAID = { yes: 'separable', weak: 'weak', no: 'not separable', too_few: 'too few' };
  function shownClasses(r) {
    const f = !!r.flipped;
    return (r.classes || []).map((c) => Object.assign({}, c, {
      shown: f && (c.c === 1 || c.c === 2) ? 3 - c.c : c.c,
      name: 'DS' + (f && (c.c === 1 || c.c === 2) ? 3 - c.c : c.c) })).sort((a, b) => a.shown - b.shown);
  }
  const colOf = (c) => tok(c.shown === 1 ? '--ds1' : '--ds2');
  const softOf = (c) => tok(c.shown === 1 ? '--ds1-soft' : '--ds2-soft');

  function recordings() {
    const d = D();
    const counts = { all: d.recordings.length, CTL: 0, 'Low KO': 0, 'High KO': 0 };
    for (const r of d.recordings) if (counts[r.ko_group] != null) counts[r.ko_group]++;
    const shown = d.recordings.filter((r) => S.grp === 'all' || r.ko_group === S.grp);
    const n = { yes: 0, no: 0, few: 0 };
    for (const r of d.recordings) n[stateOf(r)]++;
    return el('div', {}, [
      el('div', { class: 'bar' }, [
        el('div', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Show' }),
          seg([['sink', 'Mean sink'], ['source', 'Mean source']], S.mode, (v) => { S.mode = v; render(); })]),
        el('div', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Mice' }),
          seg([['all', 'All ' + counts.all], ['CTL', 'CTL ' + counts.CTL], ['Low KO', 'Low KO ' + counts['Low KO']], ['High KO', 'High KO ' + counts['High KO']]],
              S.grp, (v) => { S.grp = v; render(); })]),
      ]),
      el('div', { class: 'legend' }, [
        el('span', {}, [el('i', { class: 'line', style: 'background:var(--ds1)' }), 'DS1']),
        el('span', {}, [el('i', { class: 'line', style: 'background:var(--ds2)' }), 'DS2']),
        el('span', { text: S.mode === 'sink'
          ? 'Mean sink: sinks in blue, sources faded. The arrow is each class’s strongest sink in the box; the bracket its two largest sinks (the delta).'
          : 'Mean source: sources in red, sinks faded. The arrow is each class’s strongest source in the box.' }),
        el('span', { text: 'Dashed lines: the box X-ray used, a depth band and a time. One colour scale for every recording, so they compare.' }),
        el('span', { text: 'Cards: green separable (' + n.yes + '), red not (' + n.no + '), amber too few to call (' + n.few + ').' }),
      ]),
      el('div', { class: 'grid' }, shown.map(card)),
    ]);
  }

  function card(r) {
    const st = stateOf(r), call = r.call || {}, xs = r.xray || {};
    const ctl = isCtl(r.group);
    const head = el('div', { class: 'rec-head' }, [
      el('div', { class: 'who' }, [el('h3', { text: r.mouse + ' · ' + (ctl ? 'control' : r.ko_group || 'PTEN') }),
        el('span', { class: 'small muted', text: r.label })]),
      el('span', { class: 'chip ko', text: ctl ? '0% KO' : koText(r.ko) + ' KO' }),
      el('span', { class: 'chip', text: r.n + ' events' }),
      !ctl && r.ied != null ? el('span', { class: 'chip', title: 'From the lab’s sheet.', text: r.ied ? 'P-spikes' : 'no P-spikes' }) : null,
      r.flipped ? el('span', { class: 'chip swapped', text: 'DS1 ↔ DS2 swapped by hand' }) : null,
    ]);
    const tag = el('div', { class: 'state-tag', title: (call.by_hand ? 'Called ' + SAID[call.verdict] + ' by hand' + (call.by ? ' by ' + call.by : '')
      + '. X-ray said ' + (SAID[xs.verdict] || xs.verdict) + '. ' : 'X-ray’s call. ')
      + 'Its test: ΔBIC ' + fmt(xs.dbic, 1) + ', the smaller class ' + (xs.min_share != null ? Math.round(xs.min_share * 100) + '%' : '—') + ' of the events.' },
    [el('span', { class: 'dot' }), el('span', { text: STATE[st] + (call.by_hand ? ' · called by hand' : '') })]);
    const kids = [tag, head];
    kids.push(el('div', { class: 'pics' }, shownClasses(r).map((c) => {
      const cv = el('canvas', { class: 'csd' });
      live.push(() => drawCsd(cv, r, c));
      return el('div', { class: 'pic' }, [el('div', { class: 'cap' }, [el('b', { text: c.name, style: 'color:' + colOf(c) }),
        el('span', { text: c.n + ' events' })]), cv]);
    })));
    const pv = el('canvas', { class: 'prof' });
    live.push(() => drawProfile(pv, r));
    kids.push(el('div', { class: 'pic' }, [el('div', { class: 'cap' }, [el('span', { text: 'Depth profile at the box’s time, mean ± SEM' })]), pv]));
    kids.push(values(r));
    return el('div', { class: 'card rec st-' + st, id: 'rec-' + r.gid }, kids);
  }

  function values(r) {
    const rows = [];
    for (const c of shownClasses(r)) {
      let words;
      if (S.mode === 'sink') {
        const s = c.sink || {}, dl = c.delta || {};
        words = 'sink ' + sgn(s.value) + ' ± ' + fmt(s.sem) + ' at CSC' + (s.csc == null ? '—' : s.csc)
          + ' · Δ ' + fmt(dl.contacts, 1) + ' ± ' + fmt(dl.sem, 1) + ' contacts' + (dl.um != null ? ' (' + fmt(dl.um, 0) + ' ± ' + fmt(dl.um_sem, 0) + ' µm)' : '');
      } else {
        const s = c.source || {};
        words = 'source ' + sgn(s.value) + ' ± ' + fmt(s.sem) + ' at CSC' + (s.csc == null ? '—' : s.csc);
      }
      rows.push(el('b', { class: 'c' + c.shown, text: c.name }), el('span', { class: 'num', text: words }));
    }
    return el('div', { class: 'vals' }, rows);
  }

  function openRec(gid) {
    S.tab = 'recordings'; S.grp = 'all';
    render();
    const c = document.getElementById('rec-' + gid);
    if (!c) return;
    c.scrollIntoView({ block: 'center', behavior: 'smooth' });
    c.classList.add('flash');
    setTimeout(() => c.classList.remove('flash'), 1800);
  }

  /* ---------- Separation rate ---------- */
  function separation() {
    const d = D(), sp = d.stats.separability || {};
    const t = sp.two || {}, h = sp.three || {}, k = sp.ko || {}, lp = k.logit_pten || {};
    const rate = (x) => (x && x.n ? pc(x.rate) + ' (' + x.yes + ' of ' + x.n + '; 95% CI ' + (x.ci ? pc(x.ci[0]) + '–' + pc(x.ci[1]) : '—') + ')' : '—');
    const panel = (title, chart, lines, hit) => el('div', { class: 'stat' + (hit ? ' lead' : '') }, [
      el('div', { class: 'stat-h' }, [el('h3', { text: title }),
        el('span', { class: 'chip verdict ' + (hit ? 'tone-lead' : 'tone-none'), text: hit ? 'differs' : 'no clear difference' })]),
      chart].concat(lines.map((w) => el('span', { class: 'small num', text: w }))));
    const notes = [];
    if ((sp.by_hand || []).length) notes.push('Called by hand: ' + sp.by_hand.join(', ') + '.');
    if ((sp.not_counted || []).length) notes.push('Too few events to call, so not counted: ' + sp.not_counted.join(', ') + '.');
    const recs = d.recordings;
    return el('div', {}, [
      el('p', { class: 'muted', style: 'max-width:95ch', text: 'How often DS1 and DS2 come apart, by group. X-ray calls a recording separable when a '
        + 'two-class fit beats a one-class fit (ΔBIC) and the smaller class holds at least 10% of the events; where a person looking at the '
        + 'CSDs disagreed, their call is the one counted. “Weak” counts as not separable. Bars are the share, with a 95% interval; a dot is a '
        + 'mouse, filled if it separates.' }),
      el('div', { class: 'stats' }, [
        panel('PTEN vs CTL', rateChart(sp, 'two'), ['CTL ' + rate(t.CTL), 'PTEN ' + rate(t.PTEN),
          'Boschloo’s exact test p ' + pw(t.boschloo_p) + ' (Fisher’s p ' + pw(t.fisher_p) + ')'], sig(t.boschloo_p)),
        panel('CTL · Low KO · High KO', rateChart(sp, 'three'), GROUPS.three.map((g) => g + ' ' + rate(h[g])).concat([
          'In order (Cochran–Armitage trend) p ' + pw(h.trend_p) + (h.trend_z != null ? ', ' + (h.trend_z < 0 ? 'falling' : 'rising') : ''),
          'Pairs (Boschloo, Holm): ' + (h.pairs || []).map((p) => p.a + '–' + p.b + ' p ' + pw(p.boschloo_holm_p)).join(', ')]), sig(h.trend_p)),
      ]),
      el('p', { class: 'small', style: 'margin-top:12px', text: 'Against %KO, among PTEN alone: the odds of separating × ' + fmt(lp.or10, 2)
        + ' per 10% KO, p ' + pw(lp.p) + ' (logistic regression, n ' + (lp.n || 0) + ').' }),
      notes.length ? el('p', { class: 'small muted', text: notes.join(' ') }) : null,
      el('h2', { text: 'Mouse by mouse', style: 'margin-top:22px' }),
      el('div', { class: 'tablewrap' }, [el('table', {}, [
        el('thead', {}, [el('tr', {}, ['Mouse', 'Recording', 'Group', '%KO', 'Events', 'X-ray said', 'Counted as'].map((c) => el('th', { text: c })))]),
        el('tbody', {}, recs.map((r) => {
          const xs = r.xray || {}, call = r.call || {};
          return el('tr', { class: 'st-' + stateOf(r) }, [
            el('td', {}, [el('button', { type: 'button', class: 'link', text: r.mouse, onclick: () => openRec(r.gid) })]),
            el('td', { text: r.label }), el('td', { text: isCtl(r.group) ? 'CTL' : r.ko_group || 'PTEN' }),
            el('td', { class: 'num', text: koText(r.ko) }), el('td', { class: 'num', text: String(r.n) }),
            el('td', { text: (SAID[xs.verdict] || xs.verdict || '—') + ' (ΔBIC ' + fmt(xs.dbic, 1)
              + (xs.min_share != null ? ', smaller class ' + Math.round(xs.min_share * 100) + '%' : '') + ')' }),
            el('td', { text: STATE[stateOf(r)] + (call.by_hand ? ' · by hand' : '') }),
          ]);
        })),
      ])]),
    ]);
  }

  /* ---------- Round I and Round II ---------- */
  function roundTab(n) {
    const d = D(), R = n === 1 ? d.stats : d.round2;
    const way = S.way;
    const ms = R.metrics.slice();
    if (n === 2) ms.sort((a, b) => (pOf(a, way) == null ? 2 : pOf(a, way)) - (pOf(b, way) == null ? 2 : pOf(b, way)));
    const hits = ms.filter((m) => HIT(verdict(m, way)));
    const holds = n === 2 ? hits.filter((m) => sig(qOf(m, way))) : [];
    const best = ms.slice().sort((a, b) => (pOf(a, way) == null ? 2 : pOf(a, way)) - (pOf(b, way) == null ? 2 : pOf(b, way)))[0];
    const say = hits.length
      ? 'Under 0.05: ' + hits.map((m) => m.name + ' (p ' + pw(pOf(m, way)).replace('= ', '') + (n === 2 ? ', q ' + fmt(qOf(m, way), 2) : '') + ')').join('; ') + '. '
        + (n === 2 ? (holds.length ? 'Holding across all ' + ms.length + ': ' + holds.map((m) => m.name).join(', ') + '.'
          : 'None holds across all ' + ms.length + ' (q under 0.05): read them as leads.') : 'Nothing is corrected across the ' + ms.length + '.')
      : 'Nothing under 0.05' + (best && pOf(best, way) != null ? ': the smallest p is ' + pw(pOf(best, way)).replace('= ', '') + ' (' + best.name + ').' : '.');
    const grid = el('div', { class: 'stats' });
    for (const m of ms) grid.appendChild(statPanel(m, way, n === 2 ? ms.length : 0));
    return el('div', {}, [
      el('p', { class: 'muted', style: 'max-width:95ch', text: n === 1
        ? 'The shape of DS1 and DS2 on each recording — how deep each sink goes, how high each source, how far apart the two sinks sit, and '
          + 'the share that are DS1 — compared between the groups. One number per mouse: a mouse with 700 events counts once, like one with 60. '
          + 'A class with fewer than ' + d.stats.min_n + ' events gives no number for its own measures.'
        : 'Simple measures of each recording — how often, how big, how many look like a control’s — each by its usual test, ranked by p. '
          + 'With ' + ms.length + ' measures, about one in 20 falls under 0.05 by luck alone, so each carries its q, the false discovery '
          + 'rate across all of them (Benjamini–Hochberg).' }),
      el('div', { class: 'bar' }, [el('div', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Compare' }),
        seg(WAYS, way, (v) => { S.way = v; render(); })])]),
      el('p', { class: 'say', text: say }),
      grid,
      el('p', { class: 'small muted', style: 'margin-top:12px;max-width:110ch', text: testWords(way) }),
    ]);
  }
  function testWords(way) {
    return way === 'two'
      ? 'Each measure by its usual test, picked by whether its residuals look normal (Shapiro–Wilk): Welch’s t-test if they do, Mann–Whitney if '
        + 'not, with Hedges’ g (PTEN minus CTL, in pooled SDs). Black bar and whisker: the group’s mean ± SEM.'
      : way === 'three'
        ? 'First whether it rises or falls in order, CTL → Low KO → High KO (Jonckheere–Terpstra); then one-way ANOVA with Tukey’s pairs if the '
          + 'residuals look normal, Kruskal–Wallis with Dunn’s pairs (Holm) if not. Black bar and whisker: the group’s mean ± SEM.'
        : 'The dose: Spearman’s ρ among the PTEN mice alone, the dashed line its straight fit. The controls sit at 0%, faded; a test that includes '
          + 'them mostly measures PTEN against controls, so it is given beside, not instead.';
  }
  function statPanel(m, way, nAll) {
    const v = verdict(m, way);
    const q = nAll ? qOf(m, way) : null;
    const hold = nAll && HIT(v) && sig(q);
    const chips = [el('span', { class: 'chip verdict ' + (hold ? 'tone-hold' : HIT(v) ? 'tone-lead' : 'tone-none'), text: v })];
    if (nAll) chips.push(el('span', { class: 'chip q' + (sig(q) ? ' holds' : ''), title: 'The false discovery rate across all ' + nAll + ' measures (Benjamini–Hochberg).',
      text: q == null ? 'q —' : sig(q) ? 'holds · q ' + pw(q).replace('= ', '') : 'q ' + fmt(q, 2) }));
    return el('div', { class: 'stat' + (hold ? ' hold' : HIT(v) ? ' lead' : '') }, [
      el('div', { class: 'stat-h' }, [el('h3', { text: m.name }), el('div', { class: 'chips' }, chips)]),
      el('span', { class: 'small muted', text: wordsOf(m) + (unitOf(m) && unitOf(m) !== '×' ? ' In ' + unitOf(m) + '.' : '') }),
      dotPlot(m, way),
      el('span', { class: 'small num', text: detail(m, way) }),
    ]);
  }

  /* ---------- The numbers ---------- */
  function numbers() {
    const d = D();
    const r2 = d.round2.metrics;
    const r2v = {};
    for (const m of r2) for (const v of m.values || []) (r2v[v.gid] = r2v[v.gid] || {})[m.key] = v.value;
    const cols = [['Mouse'], ['Recording'], ['Group'], ['%KO', 1], ['Events', 1], ['DS1 n', 1], ['DS2 n', 1], ['Separable'],
      ['DS1 sink', 1], ['DS2 sink', 1], ['DS1 Δ µm', 1], ['DS2 Δ µm', 1], ['DS1 source', 1], ['DS2 source', 1]]
      .concat(r2.map((m) => [m.name + (m.unit === 'share' ? ' (%)' : unitOf(m) ? ' (' + (m.unit === '/min' ? '/min' : unitOf(m)) + ')' : ''), 1]));
    const rows = d.recordings.map((r) => {
      const cs = shownClasses(r);
      const a = cs.find((c) => c.shown === 1) || {}, b = cs.find((c) => c.shown === 2) || {};
      return { r, cells: [r.mouse, r.label, isCtl(r.group) ? 'CTL' : r.ko_group || 'PTEN', r.ko, r.n, a.n, b.n,
        STATE[stateOf(r)] + ((r.call || {}).by_hand ? ' (by hand)' : ''),
        (a.sink || {}).value, (b.sink || {}).value, (a.delta || {}).um, (b.delta || {}).um, (a.source || {}).value, (b.source || {}).value]
        .concat(r2.map((m) => { const v = (r2v[r.gid] || {})[m.key]; return v == null ? null : m.unit === 'share' ? v * 100 : v; })) };
    });
    const show = (v) => (v == null ? '—' : typeof v === 'number' ? String(+v.toPrecision(4)) : String(v));
    const csv = () => {
      const q = (v) => (v == null ? '' : /[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v));
      const text = [cols.map((c) => c[0])].concat(rows.map((x) => x.cells)).map((row) => row.map(q).join(',')).join('\n');
      const a = el('a', { href: URL.createObjectURL(new Blob(['﻿' + text], { type: 'text/csv' })),
        download: 'extraction_room_PRELIMINARY_' + String(d.name).replace(/[^A-Za-z0-9]+/g, '_') + '_v' + d.v + '.csv' });
      document.body.appendChild(a); a.click(); a.remove();
    };
    return el('div', {}, [
      el('div', { class: 'bar' }, [el('p', { class: 'muted', style: 'margin:0;max-width:90ch', text: 'Every number per mouse, as extracted. '
        + 'Sink and source in ' + ((d.recordings[0] || {}).unit || '') + '; Δ is the mean distance between a class’s two largest sinks. '
        + 'A class with fewer than ' + d.stats.min_n + ' events is shown here but not counted in Round I.' }),
        el('button', { type: 'button', class: 'btn', text: 'Download CSV (preliminary)', onclick: csv })]),
      el('div', { class: 'tablewrap' }, [el('table', { class: 'wide' }, [
        el('thead', {}, [el('tr', {}, cols.map((c) => el('th', { class: c[1] ? 'num' : null, text: c[0] })))]),
        el('tbody', {}, rows.map((x) => el('tr', { class: 'st-' + stateOf(x.r) }, x.cells.map((v, i) =>
          i === 0 ? el('td', {}, [el('button', { type: 'button', class: 'link', text: v, onclick: () => openRec(x.r.gid) })])
            : el('td', { class: cols[i][1] ? 'num' : null, text: show(v) }))))),
      ])]),
    ]);
  }

  /* ---------- How it was done ---------- */
  function methods() {
    const d = D(), gr = d.grace != null ? Math.round(d.grace * 100) + '%' : 'a set share';
    const dl = (ms) => el('dl', {}, ms.flatMap((m) => [el('dt', { text: m.name }), el('dd', { text: wordsOf(m) })]));
    return el('div', { class: 'prose' }, [
      el('p', { class: 'lede', text: 'In brief, from recording to test. Everything here is still being tuned.' }),
      el('h2', { text: 'The mice' }),
      el('p', { text: 'One recording per mouse: ' + d.stats.groups.CTL + ' controls and ' + d.stats.groups.PTEN + ' PTEN knockouts. '
        + 'Every test is across mice, never across events, so a mouse with many events counts once, like one with few. %KO is from the '
        + 'lab’s sheet (“JB % hits”); a control is 0%. Low KO is under ' + d.stats.split + '%, High KO ' + d.stats.split + '% or more.' }),
      el('h2', { text: 'Which events count as dentate spikes' }),
      el('p', { text: 'Events were detected on each recording and measured: amplitude, half-width and 500–1000 Hz power. A border was drawn '
        + 'around the controls’ dentate spikes in those measures and pulled in until ' + gr + ' of the controls’ own events fell outside. '
        + 'An event inside the border is a verified DS (“' + d.name + '”). The other set on this site differs only in that share.' }),
      el('h2', { text: 'DS1 and DS2' }),
      el('p', { text: 'On each recording, X-ray split the verified DS into two classes by the shape of their current source density (CSD) '
        + 'down the shank, inside a box — a depth band and a time — set by hand on that recording’s average CSD. It calls them separable '
        + 'when a two-class fit beats a one-class fit (ΔBIC) and the smaller class holds at least 10% of the events. Where a person looking '
        + 'at the two CSDs disagreed, their call replaces X-ray’s; the Recordings tab says which.' }),
      el('h2', { text: 'Round I · the shape of DS1 and DS2' }),
      dl(d.stats.metrics),
      el('h2', { text: 'Round II · plain measures' }),
      dl(d.round2.metrics),
      el('h2', { text: 'The tests' }),
      el('ul', {}, [
        el('li', { text: 'Two groups: Welch’s t-test, or Mann–Whitney when the residuals are not normal (Shapiro–Wilk), with Hedges’ g.' }),
        el('li', { text: 'Three groups: Jonckheere–Terpstra for a trend in order, CTL → Low KO → High KO; one-way ANOVA with Tukey’s pairs, '
          + 'or Kruskal–Wallis with Dunn’s pairs (Holm).' }),
        el('li', { text: 'Against %KO: Spearman’s ρ among the PTEN mice alone.' }),
        el('li', { text: 'Separation rate: Boschloo’s exact test (Fisher’s beside it); Cochran–Armitage for the trend; logistic regression on %KO.' }),
        el('li', { text: 'Round II’s q: Benjamini–Hochberg across its ' + d.round2.metrics.length + ' measures, for each way of comparing. '
          + 'Round I is not corrected across its ' + d.stats.metrics.length + '.' }),
        el('li', { text: '“Looks like control DS” judges a control by a border drawn from the other controls only, so no mouse is graded by a box '
          + 'its own events drew.' }),
      ]),
      el('h2', { text: 'Where this comes from' }),
      el('p', { text: 'Jarvis’s Extraction Room, the last step of The Dentist: “' + d.name + '”, v' + d.v + ' of the room, extracted ' + day(d.at)
        + (d.by ? ' by ' + d.by : '') + ' from the workflow “' + (d.workflow || '—') + '”. This site was built ' + day(S.idx.built) + '.' }),
    ]);
  }

  /* ---------- drawing the CSDs and the profiles (the room's) ---------- */
  function sized(cv) {
    if (!cv.isConnected) return null;
    const dpr = window.devicePixelRatio || 1;
    const w = cv.clientWidth, h = cv.clientHeight;
    if (!w || !h) return null;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    return { g, w, h };
  }
  function drawAll() { for (const f of live) { try { f(); } catch (e) { /* a canvas that left */ } } }

  const scales = {};
  function shared() {
    if (scales[S.set]) return scales[S.set];
    const recs = D().recordings;
    const vals = [];
    let lo = Infinity, hi = -Infinity;
    for (const r of recs) for (const c of r.classes || []) {
      for (const row of c.csd || []) for (const v of row) if (v != null && isFinite(v)) vals.push(Math.abs(v));
      const p = c.profile || {};
      (p.mean || []).forEach((v, j) => { if (v == null || !isFinite(v)) return; const e = (p.sem || [])[j] || 0; lo = Math.min(lo, v - e); hi = Math.max(hi, v + e); });
    }
    vals.sort((a, b) => a - b);
    const pad = (hi - lo) * 0.06 || 1;
    scales[S.set] = { clim: vals.length ? Math.max(1e-9, vals[Math.floor(0.99 * (vals.length - 1))]) : 1,
                      x: isFinite(lo) ? [lo - pad, hi + pad] : null };
    return scales[S.set];
  }
  function hexRgb(c) {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(c).trim());
    if (!m) return [128, 128, 128];
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  function drawCsd(cv, r, c) {
    const s = sized(cv);
    if (!s || !c.csd || !c.csd.length) return;
    const { g, w, h } = s;
    const L = 26, B = 16, T = 4, R0 = 4;
    const pw_ = w - L - R0, ph = h - B - T;
    const nr = c.csd.length, nt = c.csd[0].length;
    const lim = shared().clim;
    const sink = hexRgb(tok('--sink')), src = hexRgb(tok('--source')), bg = hexRgb(tok('--surface-2'));
    const off = document.createElement('canvas');
    off.width = nt; off.height = nr;
    const og = off.getContext('2d');
    const im = og.createImageData(nt, nr);
    for (let i = 0; i < nr; i++) {
      for (let j = 0; j < nt; j++) {
        const v = c.csd[i][j];
        const k = (i * nt + j) * 4;
        let col = bg, a = 0;
        if (v != null && isFinite(v)) {
          a = Math.pow(Math.min(1, Math.abs(v) / lim), 0.6);
          const neg = v < 0;
          col = neg ? sink : src;
          if ((S.mode === 'sink') !== neg) a *= 0.22;
        }
        im.data[k] = Math.round(bg[0] + (col[0] - bg[0]) * a);
        im.data[k + 1] = Math.round(bg[1] + (col[1] - bg[1]) * a);
        im.data[k + 2] = Math.round(bg[2] + (col[2] - bg[2]) * a);
        im.data[k + 3] = 255;
      }
    }
    og.putImageData(im, 0, 0);
    g.imageSmoothingEnabled = true;
    g.drawImage(off, L, T, pw_, ph);
    const t = r.t_ms || [];
    const t0 = t[0], t1 = t[t.length - 1];
    const X = (ms) => L + ((ms - t0) / (t1 - t0)) * pw_;
    const cs = r.contacts || [];
    const rowOf = (csc) => cs.indexOf(csc);
    const Y = (row) => T + ((row + 0.5) / nr) * ph;
    g.strokeStyle = tok('--line-2'); g.lineWidth = 1;
    g.strokeRect(L + 0.5, T + 0.5, pw_ - 1, ph - 1);
    const bx = r.box || {};
    g.setLineDash([4, 3]);
    g.strokeStyle = tok('--ink-2');
    if (bx.sel_lo != null && bx.sel_hi != null && rowOf(bx.sel_lo) >= 0 && rowOf(bx.sel_hi) >= 0) {
      const y0 = T + (rowOf(bx.sel_lo) / nr) * ph, y1 = T + ((rowOf(bx.sel_hi) + 1) / nr) * ph;
      g.beginPath(); g.moveTo(L, y0); g.lineTo(L + pw_, y0); g.moveTo(L, y1); g.lineTo(L + pw_, y1); g.stroke();
    }
    if (bx.t_lo_ms != null) {
      for (const ms of bx.t_lo_ms === bx.t_hi_ms ? [bx.t_lo_ms] : [bx.t_lo_ms, bx.t_hi_ms]) {
        g.beginPath(); g.moveTo(X(ms), T); g.lineTo(X(ms), T + ph); g.stroke();
      }
    }
    g.setLineDash([]);
    const m = S.mode === 'sink' ? (c.sink || {}) : (c.source || {});
    if (m.csc != null && rowOf(m.csc) >= 0) {
      const y = Y(rowOf(m.csc));
      g.fillStyle = colOf(c);
      g.beginPath(); g.moveTo(L - 1, y); g.lineTo(L - 9, y - 5); g.lineTo(L - 9, y + 5); g.closePath(); g.fill();
    }
    g.fillStyle = tok('--ink-3');
    g.font = '10px ' + tok('--sans', 'sans-serif');
    g.textAlign = 'right';
    g.fillText(String(cs[0] != null ? cs[0] : 1), L - 10, T + 9);
    g.fillText(String(cs[cs.length - 1] != null ? cs[cs.length - 1] : nr), L - 10, T + ph);
    g.textAlign = 'center';
    g.fillText(fmt(t0, 0), L + 10, h - 3);
    g.fillText('0 ms', X(0), h - 3);
    g.fillText('+' + fmt(t1, 0), L + pw_ - 12, h - 3);
    g.textAlign = 'left';
  }

  /* The two largest sinks of a profile inside the box, at least `sep`
     contacts apart: where to draw the delta's bracket. */
  function twoSinks(cs, mu, lo, hi, sep) {
    const idx = [];
    for (let j = 1; j < mu.length - 1; j++) {
      if (mu[j] == null || cs[j] < lo || cs[j] > hi) continue;
      if (mu[j] < 0 && mu[j] <= (mu[j - 1] == null ? Infinity : mu[j - 1]) && mu[j] <= (mu[j + 1] == null ? Infinity : mu[j + 1])) idx.push(j);
    }
    idx.sort((a, b) => mu[a] - mu[b]);
    const a = idx[0];
    if (a == null) return null;
    const b = idx.find((j) => Math.abs(j - a) >= sep);
    return b == null ? null : [Math.min(a, b), Math.max(a, b)];
  }

  function drawProfile(cv, r) {
    const s = sized(cv);
    if (!s) return;
    const { g, w, h } = s;
    const L = 30, B = 22, T = 8, R0 = 10;
    const pw_ = w - L - R0, ph = h - B - T;
    const cs = r.contacts || [];
    const n = cs.length;
    const xr = shared().x;
    if (!xr) return;
    const lo = xr[0], hi = xr[1];
    const X = (v) => L + ((v - lo) / (hi - lo)) * pw_;
    const Y = (j) => T + ((j + 0.5) / n) * ph;
    const bx = r.box || {};
    const j0 = cs.indexOf(bx.sel_lo), j1 = cs.indexOf(bx.sel_hi);
    if (j0 >= 0 && j1 >= 0) { g.fillStyle = tok('--chip'); g.fillRect(L, T + (j0 / n) * ph, pw_, ((j1 - j0 + 1) / n) * ph); }
    g.strokeStyle = tok('--line-2'); g.lineWidth = 1;
    g.strokeRect(L + 0.5, T + 0.5, pw_ - 1, ph - 1);
    g.setLineDash([3, 3]);
    g.beginPath(); g.moveTo(X(0), T); g.lineTo(X(0), T + ph); g.stroke();
    g.setLineDash([]);
    for (const c of shownClasses(r)) {
      const p = c.profile || {};
      const mu = p.mean || [], se = p.sem || [];
      const col = colOf(c), soft = softOf(c);
      g.fillStyle = soft;
      g.beginPath();
      mu.forEach((v, j) => { if (v == null) return; const x = X(v - (se[j] || 0)); if (j) g.lineTo(x, Y(j)); else g.moveTo(x, Y(j)); });
      for (let j = mu.length - 1; j >= 0; j--) { if (mu[j] == null) continue; g.lineTo(X(mu[j] + (se[j] || 0)), Y(j)); }
      g.closePath(); g.fill();
      g.strokeStyle = col; g.lineWidth = 1.8;
      g.beginPath();
      mu.forEach((v, j) => { if (v == null) return; if (j) g.lineTo(X(v), Y(j)); else g.moveTo(X(v), Y(j)); });
      g.stroke();
      const m = S.mode === 'sink' ? (c.sink || {}) : (c.source || {});
      const jm = cs.indexOf(m.csc);
      if (jm >= 0 && mu[jm] != null) { g.fillStyle = col; g.beginPath(); g.arc(X(mu[jm]), Y(jm), 4.5, 0, 6.2832); g.fill(); }
      if (S.mode === 'sink' && j0 >= 0 && j1 >= 0) {
        const pair = twoSinks(cs, mu, bx.sel_lo, bx.sel_hi, 5);
        if (pair) {
          const xb = L + 6 + (c.shown - 1) * 8;
          g.strokeStyle = col; g.lineWidth = 2;
          g.beginPath();
          g.moveTo(xb + 4, Y(pair[0])); g.lineTo(xb, Y(pair[0])); g.lineTo(xb, Y(pair[1])); g.lineTo(xb + 4, Y(pair[1]));
          g.stroke();
          g.lineWidth = 1;
        }
      }
    }
    g.fillStyle = tok('--ink-3');
    g.font = '10px ' + tok('--sans', 'sans-serif');
    g.textAlign = 'right';
    g.fillText(String(cs[0]), L - 4, T + 9);
    g.fillText(String(cs[n - 1]), L - 4, T + ph);
    g.textAlign = 'center';
    g.fillText(sgn(lo, 2), L + 16, h - 6);
    g.fillText('0', X(0), h - 6);
    g.fillText(sgn(hi, 2), L + pw_ - 16, h - 6);
    g.textAlign = 'left';
  }

  /* ---------- go ---------- */
  let resizeT = null;
  window.addEventListener('resize', () => { clearTimeout(resizeT); resizeT = setTimeout(drawAll, 120); });
  // A link to a tab or set opened on a page already showing: follow it.
  window.addEventListener('hashchange', () => {
    if (!S.idx) return;
    const was = S.tab + '|' + S.set;
    readHash();
    if (!S.sets[S.set]) S.set = S.idx.default;
    if (!TABS.some((t) => t[0] === S.tab)) S.tab = 'summary';
    if (S.tab + '|' + S.set !== was) render();
  });
  try {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => drawAll());
  } catch (e) { /* an old browser: the canvases keep their colours until a resize */ }
  const th = new URLSearchParams(location.search).get('theme');
  if (th === 'dark' || th === 'light') document.documentElement.setAttribute('data-theme', th);
  document.getElementById('out').addEventListener('click', async () => {
    try { await fetch('/api/logout', { method: 'POST' }); } catch (e) { /* signed out either way below */ }
    try { sessionStorage.removeItem(ACK); } catch (e) { /* fine */ }
    location.href = '/login.html';
  });
  setupAck();
  if (acked()) openResults();
  else document.getElementById('ack').hidden = false;

  window.erSite = { state: () => S, open: openResults, render };
})();
