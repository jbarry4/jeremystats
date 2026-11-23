/* ==========================================================================
   extraction_compare.js -- two dialogs over the Extraction Room's cards
   (2026-11-12), registered as window.erRoom.ext.compare = { splits, across }.

   COMPARE SPLITS ("add a compare splits button that will pop open the card
   and let us have 2, 3, 4 different ways of separating them (PCA no gap,
   PCA +gap, etc...) and play around with where to draw the line for each"):
   the four ways side by side, each a whole panel -- the Bite line first
   (the new round's default), then PCA no gap, PCA + gap and delta. Each has
   its own line to drag: the events change side at once, the server says
   what the classes are for that line (nothing is saved), and Use this keeps
   one, for everybody. One yardstick for all four: the separation index on
   the sinks' overlap (1 - between / the mean within).
   2026-11-13: five ways (delta middle added) in three rows -- both humps,
   the top hump alone, the bottom hump alone -- and a toggle that leaves
   the recording's low contacts out, as a look (nothing kept).

   COMPARE ACROSS SETS ("let us compare a recording with 2 different data
   sets so like compare m13s2 with the new specific 10% data set and the new
   5% larger data set"): this recording as two sets have it, side by side --
   each set's own split, calls and classes, on one colour scale and one
   depth-profile axis.

   Every CSD and depth profile here is drawn by the room's own kit
   (extraction.js), so a card in a dialog looks exactly like its card.
   ========================================================================== */
'use strict';

(function () {
  const room = window.erRoom;
  if (!room || !room.kit) return;            // the room's own page did not load
  const kit = room.kit;
  const S = kit.S;
  const el = kit.el;
  const tok = kit.tok;
  const fmt = kit.fmt;
  const sgn = kit.sgn;
  const T = (s) => document.createTextNode(s);

  /* FIVE WAYS, THREE ROWS (2026-11-13: "Add a Delta Middle ... instead of
     finding the greatest sink it just takes the middle of the hump. And for
     all the total 5 methods... add 2 rows where one basically just does it
     on the top hump, and one on the bottom hump"). Each method again on the
     recording's top hump alone and its bottom hump alone; the server's
     extraction.add_humps says how each is made on one hump. */
  const BASES = ['bite', 'pca', 'pca_gap', 'delta', 'delta_mid'];
  const ROWS = [
    { row: 'both', suffix: '', title: 'Both humps',
      says: 'Each way on the band’s whole sink, both humps.' },
    { row: 'top', suffix: '_top', title: 'The top hump only',
      says: 'Each way again on the top hump alone: the bottom hump plays no part in where the line goes.' },
    { row: 'bottom', suffix: '_bottom', title: 'The bottom hump only',
      says: 'Each way again on the bottom hump alone: the top hump plays no part in where the line goes.' },
  ];
  const METHODS = ROWS.flatMap((R) => BASES.map((b) => b + R.suffix));
  const baseOf = (m) => String(m || '').replace(/_(top|bottom)$/, '');
  const rowOf = (m) => { const k = /_(top|bottom)$/.exec(String(m || '')); return k ? k[1] : 'both'; };
  const isBite = (m) => baseOf(m) === 'bite';
  const is1D = (m) => baseOf(m) === 'delta' || baseOf(m) === 'delta_mid';
  const NAME_BOTH = { bite: 'Bite line', pca: 'PCA, no gap', pca_gap: 'PCA + gap', delta: 'delta only, no PCA',
                      delta_mid: 'delta middle, no PCA' };
  const NAME_HUMP = { bite: 'Bite line', pca: 'PCA', pca_gap: 'PCA + position', delta: 'delta, by position',
                      delta_mid: 'delta middle, by position' };
  const MNAME = {};
  for (const m of METHODS) {
    MNAME[m] = rowOf(m) === 'both' ? NAME_BOTH[baseOf(m)] : NAME_HUMP[baseOf(m)] + ' · ' + rowOf(m) + ' hump only';
  }
  const SAYS_BOTH = {
    bite: 'Every event in the order its sink overlaps the others’; the line splits that order. The new default.',
    pca: 'Each event’s place on PC1 (across) and PC2 (up). k-means splits them, or your line across PC1.',
    pca_gap: 'The same, with the sink gap in the PCA too. k-means splits them, or your line across PC1.',
    delta: 'Only how far apart each event’s two largest sinks are. k-means puts the line, or you do.',
    delta_mid: 'Only how far apart the middles of each event’s two humps are, not their deepest points: a hump’s '
      + 'middle is halfway between its edges at half its depth. k-means puts the line, or you do.',
  };
  function saysOf(m) {
    const h = rowOf(m), b = baseOf(m);
    if (h === 'both') return SAYS_BOTH[b];
    return {
      bite: 'The Bite line on the ' + h + ' hump’s sink alone: events in the order their ' + h + '-hump sinks overlap.',
      pca: 'X-ray’s PCA on the ' + h + ' hump’s contacts alone. k-means splits them, or your line across PC1.',
      pca_gap: 'The same, with where the ' + h + ' hump’s sink is strongest (a contact) in place of the gap.',
      delta: 'Only where the ' + h + ' hump’s sink is strongest, a contact: events sorted by it, k-means’ line between.',
      delta_mid: 'Only the ' + h + ' hump’s middle, a contact (halfway between its edges at half its depth): '
        + 'events sorted by it, k-means’ line between.',
    }[b];
  }
  const SEP = { yes: 'separable', weak: 'weak', no: 'not separable', too_few: 'too few to call' };

  /* ---------- the look, injected once ---------- */
  const STYLE = [
    '.erc-back { position: fixed; inset: 0; z-index: 1000; overflow-y: auto; overflow-x: hidden; overscroll-behavior: contain;',
    '  background: rgba(10, 12, 16, .46); padding: 24px 16px; }',
    '.erc-dlg { position: relative; max-width: 1760px; margin: 0 auto; background: var(--bg); color: var(--ink); min-width: 0;',
    '  border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px 18px; box-shadow: 0 20px 60px rgba(0, 0, 0, .3); }',
    '.erc-head { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 8px 16px; margin: 0 0 12px; }',
    '.erc-head-l { flex: 1 1 260px; min-width: 0; }',
    '.erc-title { font-size: 19px; line-height: 1.25; margin: 0 0 4px; overflow-wrap: anywhere; }',
    '.erc-title:focus { outline: none; }',
    '.erc-sub { margin: 0; max-width: 115ch; }',
    '.erc-status { margin: 6px 0 0; color: var(--ok); font-weight: 600; overflow-wrap: anywhere; }',
    '.erc-status.err { color: var(--bad); }',
    '.erc-status:empty { display: none; }',
    '.erc-foot { display: flex; justify-content: flex-end; margin: 14px 0 0; }',
    '.erc-panels { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 12px; align-items: start; }',
    '.erc-row { margin: 0 0 20px; }',
    '.erc-rowhead { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; margin: 0 0 8px; padding: 8px 0 0; border-top: 1px solid var(--line); }',
    '.erc-row:first-child .erc-rowhead { border-top: 0; padding-top: 0; }',
    '.erc-rowhead h3 { font-size: 16.5px; margin: 0; overflow-wrap: anywhere; }',
    '.erc-rowhead p { margin: 0; overflow-wrap: anywhere; }',
    '.erc-lowbar { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 6px 12px; margin: 0 0 14px; padding: 8px 10px;',
    '  border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }',
    '.erc-lowbar .btn[aria-pressed="true"] { background: var(--ink); color: var(--bg); border-color: var(--ink); font-weight: 600; }',
    '.erc-lowsay { flex: 1 1 320px; min-width: 0; margin: 0; overflow-wrap: anywhere; }',
    '.erc-hsi { color: var(--ink-2); }',
    '.erc-gridbox { margin: 0 0 14px; }',
    '.erc-gridhead { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 12px; margin: 0 0 6px; }',
    '.erc-gridhead p { margin: 0; }',
    '.erc-gridhead .btn[aria-pressed="true"] { background: var(--ink); color: var(--bg); border-color: var(--ink); }',
    '.erc-gridwrap { overflow-x: auto; }',
    '.erc-grid { border-collapse: separate; border-spacing: 6px; width: 100%; table-layout: fixed; min-width: 620px; }',
    '.erc-grid th { font-size: 12px; font-weight: 600; color: var(--ink-2); text-align: left; padding: 0 2px; overflow-wrap: anywhere; }',
    '.erc-grid thead th { text-align: center; }',
    '.erc-grid tbody th { width: 9.5em; }',
    '.erc-cell { padding: 0; }',
    '.erc-cell.none { text-align: center; }',
    '.erc-cellbtn { display: flex; flex-direction: column; align-items: center; gap: 1px; width: 100%; padding: 7px 4px; cursor: pointer;',
    '  font: inherit; font-size: 12px; color: var(--ink); background: var(--surface); border: 1px solid var(--line); border-radius: 8px;',
    '  font-variant-numeric: tabular-nums; transition: border-color .12s ease, box-shadow .12s ease, transform .12s ease; }',
    '.erc-cellbtn:hover { border-color: var(--ink-3); transform: translateY(-1px); }',
    '.erc-cellbtn[aria-pressed="true"] { border-color: var(--ink); box-shadow: 0 0 0 1px var(--ink); }',
    '.erc-cellbtn.inuse { box-shadow: inset 0 3px 0 var(--ok); }',
    '.erc-cellbtn.inuse[aria-pressed="true"] { box-shadow: inset 0 3px 0 var(--ok), 0 0 0 1px var(--ink); }',
    '.erc-cn { font-size: 13.5px; }',
    '.erc-cs { color: var(--ink-2); }',
    '.erc-cm { padding: 0 7px; border-radius: 999px; }',
    '.erc-cellbtn[data-word="clean"] .erc-cm { background: var(--st-yes); color: var(--st-yes-ink); }',
    '.erc-cellbtn[data-word="within"] .erc-cm { color: var(--warn); }',
    '.erc-cellbtn[data-word="mixed"] .erc-cm { background: var(--st-no); color: var(--st-no-ink); }',
    '.erc-row[hidden], .erc-panel[hidden] { display: none !important; }',
    '.erc-row.erc-solo .erc-rowhead { display: none; }',
    '.erc-row.erc-solo .erc-panels { grid-template-columns: minmax(0, 1fr); }',
    '.erc-row.erc-solo .erc-panel { display: block; columns: 360px 3; column-gap: 22px; }',
    '.erc-row.erc-solo .erc-panel > * { break-inside: avoid; margin-bottom: 6px; }',
    '.erc-row.erc-solo .erc-panel > .erc-ph { column-span: all; }',
    '.erc-mix { font-weight: 600; }',
    '.erc-mix[data-word="clean"] { color: var(--st-yes-ink); }',
    '.erc-mix[data-word="within"] { color: var(--warn); }',
    '.erc-mix[data-word="mixed"] { color: var(--st-no-ink); }',
    '.erc-mix:empty, .erc-lay:empty { display: none; }',
    '.erc-prob { height: 70px; cursor: ew-resize; touch-action: none; }',
    '.erc-n3 { font-weight: 600; }',
    '.erc-tlbox { margin: 0 0 12px; }',
    '.erc-tlbox .erc-rowhead { border-top: 0; padding-top: 0; }',
    '.erc-tl { height: 150px; touch-action: none; }',
    '.erc-twbar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; margin: 4px 0 0; }',
    '.erc-twbar .btn[hidden] { display: none; }',
    '.erc-tlsay { margin: 0; color: var(--ink-2); overflow-wrap: anywhere; }',
    '.erc-ipseg { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 4px; }',
    '.erc-ipseg .lab { font-size: 12px; color: var(--ink-2); margin-right: 2px; }',
    '.erc-ipseg .btn[aria-pressed="true"] { background: var(--ink); color: var(--bg); border-color: var(--ink); font-weight: 600; }',
    '.erc-ipdiff { flex: 1 1 100%; margin: 0; font-weight: 600; overflow-wrap: anywhere; }',
    '.erc-ipdiff:empty { display: none; }',
    '.erc-ip-in { width: 7.5em; font: inherit; font-size: 13px; padding: 3px 6px; border: 1px solid var(--line-2); border-radius: 5px;',
    '  background: var(--surface); color: var(--ink); }',
    '.erc-state[hidden], .erc-wait[hidden] { display: none; }',
    '.erc-hsi:empty { display: none; }',
    '.erc-panel, .erc-col { display: flex; flex-direction: column; gap: 6px; min-width: 0; background: var(--surface);',
    '  border: 1px solid var(--line); border-radius: var(--r, 8px); padding: 10px 12px 12px; }',
    '.erc-panel.inuse { border-color: color-mix(in srgb, var(--ok) 55%, var(--line)); box-shadow: inset 0 3px 0 var(--ok); }',
    '.erc-ph { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 8px; }',
    '.erc-ph h3, .erc-col h3 { font-size: 15.5px; margin: 0; overflow-wrap: anywhere; }',
    '.erc-panel p, .erc-col p { margin: 0; overflow-wrap: anywhere; }',
    '.erc-cv { display: block; width: 100%; border-radius: 6px; background: var(--surface-2); }',
    '.erc-line, .erc-sorted { cursor: ew-resize; touch-action: none; }',
    '.erc-line:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }',
    '.erc-raster { height: 170px; }',
    '.erc-scatter { height: 190px; }',
    '.erc-cost { height: 96px; cursor: pointer; touch-action: none; }',
    '.erc-csd { height: 150px; }',
    '.erc-prof { height: 210px; }',
    '.erc-cap { font-size: 12px; color: var(--ink-3); }',
    '.erc-dips { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; font-size: 12px; color: var(--ink-3); }',
    '.erc-dips .btn[aria-pressed="true"] { border-color: var(--ink); font-weight: 600; }',
    '.erc-n { font-size: 13.5px; font-variant-numeric: tabular-nums; }',
    '.erc-ds1 { color: var(--ds1); } .erc-ds2 { color: var(--ds2); }',
    '.erc-si { font-weight: 600; }',
    '.erc-verdict { color: var(--ink-2); }',
    '.erc-pics { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px; }',
    '.erc-stale { font-size: 12px; color: var(--warn); }',
    '.erc-peaks { font-size: 12px; color: var(--ink-2); }',
    '.erc-peaks:empty { display: none; }',
    '.erc-pk-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--peak, #d4206a); margin: 0 5px 1px 0; vertical-align: middle; }',
    '.erc-pst { font-size: 12px; color: var(--ink-3); }',
    '.erc-pst.err { color: var(--bad); }',
    '.erc-pst:empty { display: none; }',
    '.erc-acts { display: flex; flex-wrap: wrap; gap: 6px; margin: 2px 0 0; }',
    '.erc-cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr)); gap: 12px; align-items: start; }',
    '.erc-colhead { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }',
    '.erc-colhead .lab { font-size: 11.5px; color: var(--ink-3); text-transform: uppercase; letter-spacing: .04em; }',
    '.erc-chips { display: flex; flex-wrap: wrap; gap: 4px 6px; }',
    '.erc-chips .chip { white-space: normal; overflow-wrap: anywhere; }',
    '.erc-missing { padding: 14px 0; color: var(--warn); font-weight: 600; }',
    '.erc-across .erc-csd { height: 190px; }',
    '.erc-across .erc-prof { height: 260px; }',
    '.erc-diff { margin: 12px 0 0; padding: 8px 10px; border-radius: 6px; background: var(--surface); border: 1px solid var(--line);',
    '  overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }',
    '.erc-diff:empty { display: none; }',
    '@media (max-width: 520px) {',
    '  .erc-back { padding: 0; }',
    '  .erc-dlg { border-radius: 0; border-left: 0; border-right: 0; padding: 12px 16px 16px; min-height: 100%; }',
    '}',
  ].join('\n');
  if (!document.getElementById('erc-style')) {
    const st = document.createElement('style');
    st.id = 'erc-style';
    st.textContent = STYLE;
    document.head.appendChild(st);
  }

  /* ---------- small things ---------- */
  const fin = (v) => v != null && v !== '' && isFinite(v);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const cutText = (v) => (fin(v) ? String(Number(Number(v).toPrecision(3))) : '—');
  const plural = (n, w) => n + ' ' + w + (n === 1 ? '' : 's');
  const put = (node, s) => { if (node && node.textContent !== s) node.textContent = s; };
  const median = (a) => {
    if (!a.length) return null;
    const s = a.slice().sort((x, y) => x - y), h = s.length >> 1;
    return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2;
  };

  /* Where each event's sinks are strongest (2026-11-12: "the largest sink
     within the top blob and bottom blob"): the server's bumps.peaks, each
     kept bump's deepest contact, shallowest first, in event order. As raster
     rows, with the median row of the top and of the bottom one over the
     events that have both. Null without them. */
  const PEAKS = new WeakMap();
  function peaksOf(P) {
    const b = P.bite;
    if (!b) return null;
    if (PEAKS.has(b)) return PEAKS.get(b);
    let out = null;
    const raw = b.bumps && Array.isArray(b.bumps.peaks) ? b.bumps.peaks : null;
    const cs = (b.contacts || []).map(Number);
    if (raw && raw.length && cs.length) {
      const at = new Map(cs.map((c, j) => [c, j]));
      const ev = raw.map((row) => (Array.isArray(row) ? row.map((c) => at.get(Number(c))).filter((j) => j != null) : []));
      const two = ev.filter((r) => r.length >= 2);
      out = { ev, cs, top: median(two.map((r) => r[0])), bot: median(two.map((r) => r[r.length - 1])) };
    }
    PEAKS.set(b, out);
    return out;
  }
  /* A raster row (a median may fall between two) as its contact number. */
  function contactAt(pk, j) {
    if (!fin(j)) return '';
    const a = Math.floor(j), z = Math.ceil(j);
    const c = pk.cs[a] + (pk.cs[z] - pk.cs[a]) * (j - a);
    return Number.isInteger(c) ? String(c) : c.toFixed(1);
  }
  /* The words under the raster: the median strongest contact of each sink,
     overall and on each side of the line as it stands. */
  function peakWords(P) {
    const pk = peaksOf(P);
    if (!pk) return '';
    const by = { 0: [[], []], 1: [[], []], 2: [[], []] };
    pk.ev.forEach((r, e) => {
      if (r.length < 2) return;
      const s = shownT(P.D, P.types[e]);
      for (const k of (s === 1 || s === 2) ? [0, s] : [0]) { by[k][0].push(r[0]); by[k][1].push(r[r.length - 1]); }
    });
    if (!by[0][0].length) return 'Pink dots: where each event’s sink is strongest. No event here has two sinks.';
    const side = (k, h) => (by[k][h].length ? contactAt(pk, median(by[k][h])) : 'none');
    const one = (h) => 'median contact ' + side(0, h) + ' (DS1 ' + side(1, h) + ', DS2 ' + side(2, h) + ')';
    return 'Pink dots: where each event’s top and bottom sink is strongest. Top sink: ' + one(0)
      + '. Bottom sink: ' + one(1) + '. The pink ticks on the left mark the medians.';
  }
  const esc = (s) => (window.CSS && window.CSS.escape ? window.CSS.escape(String(s)) : String(s).replace(/["\\]/g, '\\$&'));

  /* The room's colours, read once per picture. */
  function pal() {
    return { ds1: tok('--ds1', '#2d6cdf'), ds2: tok('--ds2', '#d9791a'), s1: tok('--ds1-soft', 'rgba(45,108,223,.16)'),
             s2: tok('--ds2-soft', 'rgba(217,121,26,.16)'), ink: tok('--ink', '#17181b'), ink2: tok('--ink-2', '#464b53'),
             ink3: tok('--ink-3', '#70757e'), line: tok('--line', '#e3e1db'), line2: tok('--line-2', '#cfcdc6'),
             chip: tok('--chip', '#efede8'), peak: tok('--peak', '#d4206a'), bg: tok('--surface-2', '#f4f3ef'),
             ds3: tok('--ds3', '#1f9d5c'), unsure: tok('--unsure', '#8a8f98'),
             font: tok('--sans', 'sans-serif') };
  }
  const rgbMemo = new Map();
  let probe = null;
  function rgbOf(c) {
    if (rgbMemo.has(c)) return rgbMemo.get(c);
    const m = /^#([0-9a-f]{6})$/i.exec(c);
    let out;
    if (m) {
      const n = parseInt(m[1], 16);
      out = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    } else {
      if (!probe) { probe = document.createElement('canvas'); probe.width = 1; probe.height = 1; }
      const g = probe.getContext('2d');
      g.clearRect(0, 0, 1, 1);
      g.fillStyle = '#808080';
      g.fillStyle = c;
      g.fillRect(0, 0, 1, 1);
      const d = g.getImageData(0, 0, 1, 1).data;
      out = [d[0], d[1], d[2]];
    }
    rgbMemo.set(c, out);
    return out;
  }

  /* The room's state, for one synchronous draw: another set's swaps, or a
     scale the kit's pictures read from S (see the report: a clim argument
     on drawCsd would make this unnecessary). Always put back. */
  function withS(over, fn) {
    const was = {};
    for (const k of Object.keys(over)) { was[k] = S[k]; S[k] = over[k]; }
    try { return fn(); } finally { for (const k of Object.keys(was)) S[k] = was[k]; }
  }

  /* Words on a canvas: smaller until they fit, squeezed rather than cut. */
  function words(g, text, x, y, maxW, size, align, font) {
    let s = size || 10;
    g.font = s + 'px ' + font;
    while (s > 7 && g.measureText(text).width > maxW) { s -= 0.5; g.font = s + 'px ' + font; }
    g.textAlign = align || 'left';
    if (maxW > 0 && g.measureText(text).width > maxW) g.fillText(text, x, y, maxW);
    else g.fillText(text, x, y);
    g.textAlign = 'left';
  }

  /* The line and its handle, with where it is beside the handle. */
  function handle(g, C, cx, top, bottom, faded, text, w) {
    g.save();
    g.strokeStyle = C.ink;
    g.lineWidth = 1.5;
    g.globalAlpha = faded ? 0.55 : 1;
    if (faded) g.setLineDash([4, 3]);
    g.beginPath(); g.moveTo(cx, top); g.lineTo(cx, bottom); g.stroke();
    g.restore();
    g.fillStyle = C.ink;
    g.beginPath(); g.moveTo(cx - 6, top - 12); g.lineTo(cx + 6, top - 12); g.lineTo(cx, top - 2); g.closePath(); g.fill();
    if (!text) return;
    g.font = '10px ' + C.font;
    const tw = g.measureText(text).width;
    let x = cx + 9;
    if (x + tw > w - 2) x = cx - 9 - tw;
    if (x < 2) x = Math.max(2, w - 2 - tw);
    g.textAlign = 'left';
    g.fillText(text, x, top - 4, Math.max(10, w - 4));
  }

  /* Drag along a canvas: `on(px, phase)` with the pointer's x in the
     canvas; returning 'stop' on 'down' ends it there. */
  function drag(cv, on) {
    cv.addEventListener('pointerdown', (e) => {
      if (e.button) return;
      e.preventDefault();
      try { cv.focus({ preventScroll: true }); } catch (err) { /* not focusable */ }
      const at = (ev) => ev.clientX - cv.getBoundingClientRect().left;
      if (on(at(e), 'down') === 'stop') return;
      try { cv.setPointerCapture(e.pointerId); } catch (err) { /* a pointer the browser does not know */ }
      const move = (ev) => on(at(ev), 'move');
      const up = (ev) => {
        cv.removeEventListener('pointermove', move);
        cv.removeEventListener('pointerup', up);
        cv.removeEventListener('pointercancel', up);
        if (ev.type === 'pointerup') on(at(ev), 'up');
      };
      cv.addEventListener('pointermove', move);
      cv.addEventListener('pointerup', up);
      cv.addEventListener('pointercancel', up);
    });
  }

  /* ---------- the overlay: one at a time ---------- */
  let cur = null;
  let uid = 0;
  function overlay(kind, gid, title, sub) {
    closeCur();
    const id = 'erc-t' + (++uid);
    const o = { kind, gid, was: document.activeElement, draws: [], alive: true, onClose: null, ro: null,
                lock: [document.documentElement.style.overflow, document.body.style.overflow] };
    document.documentElement.style.overflow = 'hidden';
    document.body.style.overflow = 'hidden';
    const close = () => closeCur();
    o.title = el('h2', { id, class: 'erc-title', tabindex: '-1', text: title });
    o.sub = el('p', { class: 'erc-sub muted small', text: sub || '' });
    o.status = el('p', { class: 'erc-status small', role: 'status', 'aria-live': 'polite' });
    o.body = el('div', { class: 'erc-body' });
    o.dlg = el('div', { class: 'erc-dlg', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': id, 'data-gid': gid }, [
      el('div', { class: 'erc-head' }, [el('div', { class: 'erc-head-l' }, [o.title, o.sub, o.status]),
        el('button', { class: 'btn erc-close', type: 'button', text: 'Close', title: 'Close (Esc)', onclick: close })]),
      o.body,
      el('div', { class: 'erc-foot' }, [el('button', { class: 'btn erc-close-end', type: 'button', text: 'Close', onclick: close })]),
    ]);
    o.back = el('div', { class: 'erc-back erc-' + kind, id: 'erc-' + kind }, [o.dlg]);
    document.body.appendChild(o.back);
    if (window.ResizeObserver) {
      o.ro = new ResizeObserver(() => later());
      o.ro.observe(o.body);
    }
    cur = o;
    try { o.title.focus({ preventScroll: true }); } catch (e) { o.title.focus(); }
    return o;
  }

  function say(o, text, bad) {
    if (!o || !o.alive) return;
    o.status.textContent = text || '';
    o.status.classList.toggle('err', !!bad);
  }

  function closeCur() {
    const o = cur;
    if (!o) return;
    cur = null;
    o.alive = false;
    if (o.onClose) { try { o.onClose(); } catch (e) { /* closing anyway */ } }
    if (o.ro) o.ro.disconnect();
    o.back.remove();
    document.documentElement.style.overflow = o.lock[0];
    document.body.style.overflow = o.lock[1];
    // Back to where it was opened from; the card's button, if the room has
    // been drawn again since.
    let to = o.was && o.was.isConnected && o.was !== document.body ? o.was : null;
    if (!to) {
      const card = document.querySelector('#erGrid .rec[data-gid="' + esc(o.gid) + '"]');
      to = card && card.querySelector(o.kind === 'splits' ? '.er-compare' : '.er-across');
    }
    if (to && to.focus) to.focus();
  }

  document.addEventListener('keydown', (e) => {
    const o = cur;
    if (!o) return;
    if (e.key === 'Escape') { e.preventDefault(); closeCur(); return; }
    if (e.key !== 'Tab') return;
    // Tab stays inside the dialog.
    const fs = Array.from(o.dlg.querySelectorAll('button, select, input, [href], [tabindex]'))
      .filter((n) => n.tabIndex >= 0 && !n.disabled && n.getClientRects().length);
    if (!fs.length) return;
    const first = fs[0], last = fs[fs.length - 1], at = document.activeElement;
    if (e.shiftKey && (at === first || at === o.title || !o.dlg.contains(at))) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && (at === last || !o.dlg.contains(at))) { e.preventDefault(); first.focus(); }
  }, true);
  document.addEventListener('focusin', (e) => {
    if (cur && !cur.dlg.contains(e.target)) { try { cur.title.focus({ preventScroll: true }); } catch (err) { /* fine */ } }
  });

  /* Redrawn when the width changes, or the theme. */
  let drawT = null;
  function later() { clearTimeout(drawT); drawT = setTimeout(() => redraw(cur), 90); }
  function redraw(o) {
    if (!o || !o.alive) return;
    for (const f of o.draws) { try { f(); } catch (e) { /* a canvas that left */ } }
  }
  window.addEventListener('resize', later);
  try { window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', later); } catch (e) { /* older browsers */ }

  /* ======================================================================
     COMPARE SPLITS
     ====================================================================== */
  async function splits(r0) {
    if (!r0 || !S.art) return;
    const gid = r0.gid;
    const r = kit.recOf(gid) || r0;
    const D = { r, gid, aid: S.art.artifact_id, version: S.version, sv: null, saved: null, panels: [], busy: false,
                rowOf: [], low: false, interpOff: false, ipTry: null, ipLast: null, ipSaved: [], gen: 0, loading: false,
                states: new Map() };
    const o = overlay('splits', gid, r.session_label + ' · ' + (r.group || '?') + ' · ' + plural(r.n, 'event'),
      'Five ways of splitting its events into DS1 and DS2, side by side: first on both sink humps, then on the top hump '
      + 'alone and on the bottom hump alone. Move any line and its classes follow; nothing is kept until Use this, which '
      + 'keeps it for everybody. SI is one yardstick for all fifteen: how little DS1’s and DS2’s sinks overlap.'
      + (kit.flipped(r) ? ' DS1 and DS2 are swapped by hand on this recording, and named that way here.' : ''));
    o.D = D;
    D.o = o;
    // Low contacts (2026-11-13: "a toggle option to exclude the Low
    // contacts; just to see how it changes everything").
    D.lowBtn = el('button', { class: 'btn small erc-low', type: 'button', 'aria-pressed': 'false',
      text: 'Leave out low contacts', onclick: () => { if (!D.loading) { D.low = !D.low; D.ipDiffText = ''; loadSplits(D); } } });
    D.lowSay = el('p', { class: 'small erc-lowsay', 'aria-live': 'polite' });
    // Interpolation on and off (2026-11-13: "have an option to turn
    // interpulation on and off here and make sure all the figures here also
    // update"): the card's interpolated contacts, or the recording as read.
    // Off is a look; Keep it off puts them back on the card for good.
    // Two named states (2026-11-13: one button reading "Interpolate 38, 39"
    // was taken for the action, pressed, and so turned it OFF).
    // ipTo(off, set): the card's contacts (false), none (true), or a set
    // tried here (2026-11-13: "let me choose a set of channels my self").
    const ipTo = (off, set) => {
      if (D.loading) return;
      const same = (x, y) => (x || []).join() === (y || []).join();
      let t = set ? Array.from(new Set(set)).sort((x, y) => x - y) : null;
      if (t && !t.length) { t = null; off = true; }
      if (t && same(t, D.ipSaved)) { t = null; off = false; }
      if (!t && off && !(D.ipSaved || []).length) off = false;        // nothing saved: as recorded IS the card
      if (same(t, D.ipTry) && (t || D.interpOff === off)) return;
      D.ipWas = D.ipTry;
      D.ipTry = t;
      if (t) D.ipLast = t;
      D.interpOff = !t && off;
      D.ipSwitched = true;
      loadSplits(D);
    };
    const ipParse = (text) => {
      const out = [];
      for (const k of String(text || '').split(/[\s,;]+/).filter(Boolean)) {
        const m = /^(\d+)\s*[-–]\s*(\d+)$/.exec(k);
        if (m) { for (let c = Math.min(+m[1], +m[2]); c <= Math.max(+m[1], +m[2]); c++) out.push(c); }
        else if (/^\d+$/.test(k)) out.push(+k);
        else return null;
      }
      return out;
    };
    D.ipLab = el('span', { class: 'lab erc-ip-lab' });
    D.ipOn = el('button', { class: 'btn small erc-ip-on', type: 'button', text: 'Interpolated', onclick: () => ipTo(false) });
    D.ipOffB = el('button', { class: 'btn small erc-ip-off', type: 'button', text: 'As recorded', onclick: () => ipTo(true) });
    D.ipTryB = el('button', { class: 'btn small erc-ip-try', type: 'button', hidden: true, onclick: () => ipTo(false, D.ipLast) });
    D.ipBtn = el('span', { class: 'erc-ipseg', role: 'group', hidden: true }, [D.ipLab, D.ipOn, D.ipOffB, D.ipTryB]);
    D.ipIn = el('input', { class: 'erc-ip-in', type: 'text', placeholder: 'e.g. 37-39', 'aria-label': 'Contacts to try interpolating' });
    const tryNow = () => {
      const cs = ipParse(D.ipIn.value);
      if (!cs) { D.lowErr = 'Contacts are numbers, like 37, 38 or 37-39.'; paintLow(D); return; }
      ipTo(false, cs);
    };
    D.ipIn.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); tryNow(); } });
    D.ipGo = el('button', { class: 'btn small erc-ip-go', type: 'button', text: 'Show', onclick: tryNow });
    D.ipTryBox = el('span', { class: 'erc-ipseg erc-iptry' }, [el('span', { class: 'lab', text: 'Try interpolating:' }), D.ipIn, D.ipGo]);
    D.waitBox = el('p', { class: 'muted erc-wait' });
    D.ipKeep = el('button', { class: 'btn small erc-ip-keep', type: 'button', hidden: true, onclick: () => keepIpOff(D) });
    D.ipDiff = el('p', { class: 'small erc-ipdiff', 'aria-live': 'polite' });
    D.rowsBox = el('div', { class: 'erc-rows' });
    // The timeline (2026-11-13: "a line showing when all the DS spikes
    // happened. And then a theta power level in middle of the region we
    // highlighted on the same time course").
    D.tlCv = el('canvas', { class: 'erc-cv erc-tl', role: 'img', 'aria-label': 'When every event happened, and theta power' });
    D.tlSay = el('p', { class: 'small erc-tlsay', 'aria-live': 'polite',
      text: 'Reading theta over the whole recording (the first time, up to a minute)…' });
    o.body.appendChild(el('section', { class: 'erc-tlbox', 'aria-label': 'Timeline' }, [
      el('div', { class: 'erc-rowhead' }, [el('h3', { text: 'When they happened' }), D.tlSay]), D.tlCv,
      el('div', { class: 'erc-twbar' }, [
        el('span', { class: 'muted small', text: 'Drag the two knobs on the line to take only the events between them.' }),
        (D.twAll = el('button', { class: 'btn small erc-tw-all', type: 'button', text: 'Whole recording', hidden: true,
          onclick: () => twTo(D, false) })),
        (D.twCard = el('button', { class: 'btn small erc-tw-card', type: 'button', text: 'The card’s window', hidden: true,
          onclick: () => twTo(D, null) })),
        (D.twKeep = el('button', { class: 'btn small erc-tw-keep', type: 'button', hidden: true, onclick: () => keepTw(D) }))])]));
    drag(D.tlCv, (px, phase) => knob(D, px, phase));
    o.body.appendChild(el('div', { class: 'erc-lowbar' }, [D.lowBtn, D.ipBtn, D.ipTryBox, D.ipKeep, D.lowSay, D.ipDiff]));
    o.body.appendChild(D.waitBox);
    o.body.appendChild(D.rowsBox);
    o.onClose = () => { for (const P of D.panels) clearTimeout(P.timer); };
    const tl = () => { paintStrip(D); };
    tl.strip = true;
    o.draws.push(tl);
    kit.api('/api/extraction/' + encodeURIComponent(D.aid) + '/timeline?version=' + encodeURIComponent(D.version)
      + '&gid=' + encodeURIComponent(gid))
      .then((t) => { if (o.alive) { D.tl = t; paintStrip(D); } })
      .catch((e) => { if (o.alive) { D.tl = { error: e.message }; paintStrip(D); } });
    await loadSplits(D);
  }

  /* ---------- DS3, the trim and the mix-up (2026-11-13) ---------- */
  const pc = (v) => (v == null || !isFinite(v) ? '—' : Math.round(100 * v) + '%');
  const setMode = (D) => (D.sv && D.sv.mode) || { mode: 'plain', ds3_cut: 0.5, trim_cut: 0.8 };
  /* An event's class as the set's mode has it: the split's, DS3 laid over,
     or the unsure taken out -- the split's own while a moved line waits. */
  function modeTypes(P) {
    const L = P.layers, md = setMode(P.D).mode;
    const t = !L ? null : md === 'ds3' && !(L.ds3 || {}).why ? (L.ds3 || {}).types : md === 'trim' ? (L.trim || {}).types : null;
    return Array.isArray(t) && t.length === P.types.length ? t : P.types;
  }
  const MIXW = { clean: 'clean', within: 'within 10–15%', mixed: 'mixed' };
  function paintMix(P) {
    const L = P.layers;
    if (!L) { put(P.mix, P.pending ? 'Mix-up for this line: being worked out.' : ''); P.mix.dataset.word = ''; put(P.lay, ''); return; }
    const md = setMode(P.D).mode, m = L.mix || {};
    const one = (lab, x) => (x ? lab + ' ' + pc(x.est) + ' (' + pc(x.lo) + '–' + pc(x.hi) + ')' : lab + ' —');
    const cur = m[md] || m.plain;
    put(P.mix, 'Mix-up: ' + one('as split', m.plain) + ' · ' + one('DS3 out', m.ds3) + ' · ' + one('trimmed', m.trim)
      + (cur ? '. ' + (cur.word === 'clean' ? 'Clean (10% or under).' : cur.word === 'within'
        ? 'Within the 10–15% waveform-only classification accepts.' : 'Mixed (over 15%).') : '.'));
    P.mix.dataset.word = cur ? cur.word : '';
    const d3 = L.ds3 || {}, tr = L.trim || {};
    let s = '';
    if (md === 'ds3') {
      const u = d3.unscorable || {};
      s = d3.why ? 'No DS3 with this split: ' + d3.why
        : 'DS3: ' + ((d3.counts || {})['3'] || 0) + ' events with a relative-sink score within ±' + (+d3.cut).toFixed(2) + ' (OML contact '
          + d3.oml + ', MML ' + d3.mml + '); ' + (u.n || 0) + ' unscorable keep their class.'
          + (d3.near ? ' OML and MML are ' + d3.gap + ' apart: one sink seen twice.' : '') + ' Tarcsay et al. 2025.';
    } else if (md === 'trim') {
      s = tr.refused || (tr.unsure || 0) + ' unsure under ' + pc(tr.cut) + ': grey, out of DS1’s and DS2’s numbers.';
    } else if (tr.would != null) {
      s = 'With the set’s switches: DS3 would take ' + (d3.why ? 'none' : ((d3.counts || {})['3'] || 0)) + ', the trim '
        + (tr.refused ? 'is refused here' : (tr.would || 0)) + '.';
    }
    put(P.lay, s);
  }
  /* Every event's probability, and the cut-off. */
  function drawProb(cv, P) {
    const s = kit.sized(cv);
    if (!s) return;
    const { g, w, h } = s;
    const C = pal();
    const pm = ((P.layers || P.pre.layers || {}).trim || {}).p_max || [];
    const cut = P.probDrag != null ? P.probDrag : setMode(P.D).trim_cut;
    const L = 8, R = 8, Tp = 6, B = 16, pw = w - L - R, ph = h - Tp - B;
    if (pw < 30 || ph < 10) return;
    const NB = 25, bins = new Array(NB).fill(0);
    let n = 0;
    for (const v of pm) { if (!fin(v)) continue; bins[Math.min(NB - 1, Math.floor((+v - 0.5) / 0.5 * NB))]++; n++; }
    const top = Math.max(1, ...bins);
    const X = (v) => L + ((v - 0.5) / 0.5) * pw;
    for (let b = 0; b < NB; b++) {
      const v0 = 0.5 + (b / NB) * 0.5;
      g.fillStyle = v0 + 0.25 / NB < cut ? C.unsure : C.ink2;
      const bh = (bins[b] / top) * ph;
      g.fillRect(X(v0) + 0.5, Tp + ph - bh, pw / NB - 1, bh);
    }
    g.strokeStyle = C.ink;
    g.lineWidth = 1.5;
    g.beginPath(); g.moveTo(X(cut), Tp - 2); g.lineTo(X(cut), Tp + ph + 2); g.stroke();
    g.fillStyle = C.ink3;
    words(g, '50%', L, h - 3, 30, 10, 'left', C.font);
    words(g, '100% sure', L + pw, h - 3, 60, 10, 'right', C.font);
    let un = 0;
    for (const v of pm) if (fin(v) && +v < cut) un++;
    words(g, pc(cut) + ': ' + un + ' of ' + n + ' under', clamp(X(cut), L + 60, L + pw - 60), h - 3, 120, 10, 'center', C.font);
    cv.__map = (px) => clamp(0.5 + ((px - L) / pw) * 0.5, 0.5, 0.99);
  }
  /* The cut-off dragged: shown at once here; let go, it is the set's. */
  async function probCut(P, v, phase) {
    const D = P.D;
    P.probDrag = Math.round(v * 100) / 100;
    drawProb(P.probCv, P);
    if (phase !== 'up') return;
    const cut = P.probDrag;
    try {
      await kit.post('/api/extraction/mode', { room: S.room, folder: S.folder, trim_cut: cut });
    } catch (e) { P.probDrag = null; say(D.o, 'Not changed: ' + e.message, true); drawProb(P.probCv, P); return; }
    say(D.o, 'The set’s cut-off is ' + pc(cut) + ' now, for everybody.');
    dropStates(D);
    loadSplits(D);
    try { await kit.reloadCard(D.gid); } catch (e) { /* the room says so itself */ }
  }

  /* THE SCORE GRID (2026-11-13: "A 5x3 score grid, one panel open"): the
     fifteen splits at a glance -- counts, SI, mix-up -- and one full panel
     under it, the one picked. Open all shows the fifteen. */
  let openAllPref = false;
  function scoreGrid(D, st) {
    st.cells = {};
    const head = el('tr', {}, [el('th', {})].concat(BASES.map((b) => el('th', { scope: 'col', text: NAME_BOTH[b].replace(', no PCA', '') }))));
    const rows = ROWS.map((R) => el('tr', {}, [el('th', { scope: 'row', text: R.title })].concat(BASES.map((b) => {
      const m = b + R.suffix;
      const P = st.panels.find((x) => x.m === m);
      if (!P || !P.live) return el('td', { class: 'erc-cell none' }, [el('span', { class: 'muted', text: '—' })]);
      const btn = el('button', { class: 'erc-cellbtn', type: 'button', 'data-method': m, 'aria-pressed': 'false',
        title: 'Open ' + P.name, onclick: () => { D.open = m; applyOpen(D); redraw(D.o); } },
        [el('b', { class: 'erc-cn' }), el('span', { class: 'erc-cs' }), el('span', { class: 'erc-cm' })]);
      st.cells[m] = btn;
      P.cell = btn;
      return el('td', { class: 'erc-cell' }, [btn]);
    }))));
    const all = el('button', { class: 'btn small erc-openall', type: 'button', 'aria-pressed': String(openAllPref),
      text: 'Open all 15', onclick: () => { openAllPref = !openAllPref; applyOpen(D); redraw(D.o); } });
    st.allBtn = all;
    return el('div', { class: 'erc-gridbox' }, [
      el('div', { class: 'erc-gridhead' }, [el('p', { class: 'small muted', text: 'The fifteen splits: DS1/DS2 counts, SI, and the '
        + 'mix-up. Click one to open it below.' }), all]),
      el('div', { class: 'erc-gridwrap' }, [el('table', { class: 'erc-grid' }, [el('thead', {}, [head]), el('tbody', {}, rows)])])]);
  }
  function paintCell(P) {
    const c = P.cell;
    if (!c) return;
    let a = 0, b = 0;
    for (const t of P.types) { const s = shownT(P.D, t); if (s === 1) a++; else if (s === 2) b++; }
    put(c.children[0], a + '/' + b);
    put(c.children[1], P.scores && fin(P.scores.si) ? 'SI ' + fmt(+P.scores.si, 2) : 'SI —');
    const md = setMode(P.D).mode, mx = P.layers && P.layers.mix ? (P.layers.mix[md] || P.layers.mix.plain) : null;
    put(c.children[2], mx ? 'mix ' + pc(mx.est) : 'mix —');
    c.dataset.word = mx ? mx.word : '';
  }
  /* Which panels show: the one open, or all. */
  function applyOpen(D) {
    const st = D.states.get(stateKey(D));
    if (!st) return;
    const live = st.panels.filter((P) => P.live);
    if (!live.some((P) => P.m === D.open)) {
      const want = !look(D) && D.saved && D.saved.method ? D.saved.method : D.sv.own;
      D.open = (live.find((P) => P.m === want) || live[0] || {}).m;
    }
    for (const P of st.panels) P.node.hidden = !(openAllPref || P.m === D.open);
    for (const sec of st.box.querySelectorAll('.erc-row')) {
      const ps = sec.querySelectorAll('.erc-panel');
      sec.hidden = ps.length > 0 && Array.from(ps).every((n) => n.hidden);
      sec.classList.toggle('erc-solo', !openAllPref);
    }
    for (const [m, btn] of Object.entries(st.cells || {})) {
      btn.setAttribute('aria-pressed', String(m === D.open));
      const P = st.panels.find((x) => x.m === m);
      btn.classList.toggle('inuse', !!P && !look(D) && inUse(P));
    }
    if (st.allBtn) st.allBtn.setAttribute('aria-pressed', String(openAllPref));
    for (const P of live) if (!P.node.hidden) paint(P);
  }

  /* ---------- the time window's two knobs ---------- */
  const thTopY = (Tp, evH) => Tp + evH + 7;
  function paintTw(D) {
    const on = (D.sv && D.sv.twin) || null, saved = D.twSaved || null;
    D.twAll.hidden = !on;
    D.twCard.hidden = !(D.twTry != null && saved);
    D.twKeep.hidden = D.twTry == null;
    put(D.twKeep, D.twTry === false ? 'Save for good: the whole recording on the card'
      : on ? 'Save this window on the card: ' + (on[0] / 60).toFixed(1) + '–' + (on[1] / 60).toFixed(1) + ' min, for everybody' : '');
    put(D.twCard, saved ? 'The card’s window (' + (saved[0] / 60).toFixed(1) + '–' + (saved[1] / 60).toFixed(1) + ' min)' : '');
  }
  /* A window asked for: the card's (null), none (false), or [t0, t1]. */
  function twTo(D, v) {
    if (D.loading) return;
    const same = (x, y) => Array.isArray(x) && Array.isArray(y) && Math.abs(x[0] - y[0]) < 0.5 && Math.abs(x[1] - y[1]) < 0.5;
    const saved = D.twSaved || null;
    if (Array.isArray(v) && saved && same(v, saved)) v = null;
    if (v === false && !saved) v = null;                    // no window kept: the whole recording IS the card
    if (v === D.twTry || same(v, D.twTry)) { paintStrip(D); return; }
    D.twWas = D.twTry;
    D.twTry = v;
    D.twSwitched = true;
    D.ipDiffText = '';
    loadSplits(D);
  }
  function knob(D, px, phase) {
    const m = D.tlMap;
    if (!m || D.loading) return 'stop';
    const sec = clamp(((px - m.L) / m.pw) * m.dur, 0, m.dur);
    if (phase === 'down') {
      const d0 = Math.abs(px - (m.L + (m.tw[0] / m.dur) * m.pw)), d1 = Math.abs(px - (m.L + (m.tw[1] / m.dur) * m.pw));
      if (Math.min(d0, d1) > 14) return 'stop';
      D.twKnob = d0 <= d1 && !(d0 === d1 && sec > m.tw[0]) ? 0 : 1;
      D.twDrag = m.tw.slice();
    }
    if (!D.twDrag) return 'stop';
    const w = D.twDrag.slice();
    w[D.twKnob] = sec;
    if (w[1] - w[0] < Math.max(5, m.dur * 0.01)) return undefined;        // the knobs do not cross
    D.twDrag = w;
    if (phase === 'up') {
      const got = [Math.round(w[0]), Math.round(w[1])];
      D.twDrag = null;
      twTo(D, got[0] <= 0 && got[1] >= Math.floor(m.dur) ? false : got);
      return undefined;
    }
    paintStrip(D);
    return undefined;
  }
  async function keepTw(D) {
    const on = (D.sv && D.sv.twin) || null;
    const clear = D.twTry === false || !on;
    if (!window.confirm((clear ? 'Take the whole recording again' : 'Take only the events from ' + (on[0] / 60).toFixed(1) + ' to '
      + (on[1] / 60).toFixed(1) + ' min') + ' on ' + D.r.session_label + ', for everybody, in every set? A Bite line placed by hand '
      + 'on it goes back to its default.')) return;
    try {
      await kit.post('/api/extraction/twin', Object.assign({ artifact_id: D.aid, version: D.version, gid: D.gid },
        clear ? { clear: true } : { t0: on[0], t1: on[1] }));
    } catch (e) { say(D.o, 'Not changed: ' + e.message, true); return; }
    D.twTry = null;
    dropStates(D);
    say(D.o, clear ? 'The whole recording is taken again; the card behind shows it so.'
      : 'Only the events from ' + (on[0] / 60).toFixed(1) + ' to ' + (on[1] / 60).toFixed(1) + ' min are taken now; the card behind shows it so.');
    try { await kit.reloadCard(D.gid); } catch (e) { /* the room says so itself */ }
    const fresh = kit.recOf(D.gid);
    if (fresh) D.r = fresh;
    loadSplits(D);
  }

  /* ---------- the timeline over the panels ---------- */
  /* Its events are coloured by one split: the one in use, until a line is
     moved on another panel -- then that one. */
  function followed(D) {
    const live = D.panels.filter((P) => P.live);
    if (D.follow && live.includes(D.follow)) return D.follow;
    return live.find((P) => !look(D) && inUse(P)) || live[0] || null;
  }
  const perMin = (n, s) => (s > 0 ? (n / (s / 60)).toFixed(2) + ' a minute' : '—');
  function stripWords(D) {
    const t = D.tl;
    if (!t) return 'Reading theta over the whole recording (the first time, up to a minute)…';
    if (t.error) return 'The timeline is not available: ' + t.error;
    const P = followed(D);
    const all = (t.events || []).length, full = +t.duration_s || 0;
    const tw = (D.sv && D.sv.twin) || null;
    const n = tw ? (t.events || []).filter((s) => s >= tw[0] && s <= tw[1]).length : all;
    const dur = tw ? tw[1] - tw[0] : full;
    let a = 0, b = 0;
    let c3 = 0, c4 = 0;
    if (P) for (const ty of modeTypes(P)) { const s = shownT(D, ty); if (s === 1) a++; else if (s === 2) b++; else if (s === 3) c3++; else if (s === 4) c4++; }
    const len = (full ? 'The recording is ' + (full / 60).toFixed(1) + ' minutes long' : 'Its length is not known')
      + (tw ? '; only the events from ' + (tw[0] / 60).toFixed(1) + ' to ' + (tw[1] / 60).toFixed(1) + ' min are taken ('
        + (D.twTry != null ? 'a look: nothing is kept until the window is saved on the card' : 'the card’s window') + ')' : '');
    const th = t.theta ? ' Below them, theta (' + t.theta.band.join('–') + ' Hz) power on contact ' + t.theta.contact
      + ', the middle of the band, in ' + t.theta.bin_s + ' s bins.' : t.theta_why ? ' Theta could not be read: ' + t.theta_why + '.' : '';
    return len + '; ' + plural(n, 'event') + (dur ? ', ' + perMin(n, dur) : '') + '. As ' + (P ? P.name + ' splits them' : 'split')
      + (D.low ? ' (low contacts left out)' : '') + (D.ipTry ? ' (contacts ' + D.ipTry.join(', ') + ' interpolated, a look)'
        : D.interpOff && (D.ipSaved || []).length ? ' (without interpolation)' : '')
      + ': DS1 ' + a + (dur ? ' (' + perMin(a, dur) + ')' : '') + ', DS2 ' + b
      + (dur ? ' (' + perMin(b, dur) + ')' : '') + (c3 ? ', DS3 ' + c3 + (dur ? ' (' + perMin(c3, dur) + ')' : '') : '')
      + (c4 ? ', unsure ' + c4 : '') + '. Move a line on any panel and the ticks follow it.' + th;
  }
  function paintStrip(D) {
    put(D.tlSay, stripWords(D));
    if (D.twAll) paintTw(D);
    const s = kit.sized(D.tlCv);
    if (!s) return;
    const { g, w, h } = s;
    const C = pal();
    const t = D.tl;
    if (!t || t.error) return;
    const ev = (t.events || []).map(Number);
    const th = t.theta || null;
    const dur = +t.duration_s || (ev.length ? Math.max(...ev) : 0);
    const L = 44, R = 10, Tp = 6, B = 20;
    const pw = w - L - R;
    if (pw < 40 || !(dur > 0)) return;
    const evH = 26, gap = 8;
    const thTop = Tp + evH + gap, thH = h - thTop - B;
    const X = (sec) => L + clamp(sec / dur, 0, 1) * pw;
    // The window: the one being dragged, else the one the splits were made in.
    const twOn = (D.sv && D.sv.twin) || null;
    const twNow = D.twDrag || twOn || [0, dur];
    D.tlMap = { L, pw, dur, tw: twNow };
    // Each event's class is its place among the events INSIDE the window.
    const idx = [];
    let k = 0;
    for (const sec of ev) idx.push(!twOn || (sec >= twOn[0] && sec <= twOn[1]) ? k++ : -1);
    // The events: a tick each, DS1 above DS2 so both read when they crowd.
    const P = followed(D);
    const types = P ? modeTypes(P) : [];
    g.strokeStyle = C.line2;
    g.lineWidth = 1;
    g.strokeRect(L + 0.5, Tp + 0.5, pw - 1, evH - 1);
    for (const pass of [2, 1]) {
      g.strokeStyle = pass === 1 ? C.ds1 : C.ds2;
      g.globalAlpha = 0.85;
      g.lineWidth = Math.max(1, Math.min(2, pw / Math.max(1, ev.length) / 2));
      g.beginPath();
      ev.forEach((sec, i0) => {
        const i = idx[i0];
        if (i < 0) return;
        const sh = shownT(D, types[i]);
        if ((pass === 1 && sh !== 1) || (pass === 2 && sh === 1)) return;
        if (sh === 3 || sh === 4) return;            // drawn after, across both lanes
        const x = X(sec);
        const y0 = pass === 1 ? Tp + 2 : Tp + evH / 2, y1 = pass === 1 ? Tp + evH / 2 : Tp + evH - 2;
        g.moveTo(x, y0); g.lineTo(x, y1);
      });
      g.stroke();
    }
    for (const k of [4, 3]) {
      g.strokeStyle = k === 3 ? C.ds3 : C.unsure;
      g.beginPath();
      ev.forEach((sec, i0) => { const i = idx[i0]; if (i >= 0 && shownT(D, types[i]) === k) { const x = X(sec); g.moveTo(x, Tp + 7); g.lineTo(x, Tp + evH - 7); } });
      g.stroke();
    }
    // Events outside the window: grey, not in any split.
    g.strokeStyle = C.unsure;
    g.globalAlpha = 0.5;
    g.beginPath();
    ev.forEach((sec, i0) => { if (idx[i0] < 0) { const x = X(sec); g.moveTo(x, Tp + 8); g.lineTo(x, Tp + evH - 8); } });
    g.stroke();
    g.globalAlpha = 1;
    // Outside the window shaded down the whole strip, and the two knobs:
    // drawn last, over theta too.
    const overlay = () => {
    g.fillStyle = C.bg;
    g.globalAlpha = 0.72;
    if (twNow[0] > 0) g.fillRect(L, Tp, X(twNow[0]) - L, h - Tp - B);
    if (twNow[1] < dur) g.fillRect(X(twNow[1]), Tp, L + pw - X(twNow[1]), h - Tp - B);
    g.globalAlpha = 1;
    for (const sec of twNow) {
      const x = X(sec);
      g.strokeStyle = C.ink;
      g.lineWidth = 1.5;
      g.beginPath(); g.moveTo(x, Tp - 2); g.lineTo(x, h - B); g.stroke();
      g.fillStyle = C.ink;
      g.beginPath(); g.arc(x, Tp + evH / 2, 6, 0, 6.2832); g.fill();
      g.fillStyle = C.bg;
      g.beginPath(); g.arc(x, Tp + evH / 2, 2.5, 0, 6.2832); g.fill();
    }
    if (D.twDrag) {
      g.fillStyle = C.ink;
      words(g, (twNow[0] / 60).toFixed(1) + ' – ' + (twNow[1] / 60).toFixed(1) + ' min', clamp((X(twNow[0]) + X(twNow[1])) / 2, L + 50, L + pw - 50),
        thTopY(Tp, evH), 120, 10.5, 'center', C.font);
    }
    };
    g.globalAlpha = 1;
    g.fillStyle = C.ink3;
    words(g, 'DS1', L - 4, Tp + 11, L - 6, 10, 'right', C.font);
    words(g, 'DS2', L - 4, Tp + evH - 4, L - 6, 10, 'right', C.font);
    // Theta power on the same minutes.
    g.strokeStyle = C.line2;
    g.strokeRect(L + 0.5, thTop + 0.5, pw - 1, thH - 1);
    if (th && (th.power || []).length && thH > 12) {
      const ps = th.power.filter(fin).map(Number).sort((a, b) => a - b);
      const top = ps.length ? ps[Math.min(ps.length - 1, Math.floor(ps.length * 0.99))] : 1;
      const Y = (v) => thTop + thH - 2 - clamp(v / (top || 1), 0, 1) * (thH - 4);
      const bw = th.bin_s || 4;
      g.fillStyle = C.ink2;
      g.globalAlpha = 0.22;
      g.beginPath();
      let open = false;
      th.t.forEach((sec, i) => {
        const v = th.power[i];
        if (!fin(v)) { if (open) { g.lineTo(X(th.t[i - 1] + bw), thTop + thH - 2); g.closePath(); g.fill(); g.beginPath(); open = false; } return; }
        if (!open) { g.moveTo(X(sec), thTop + thH - 2); open = true; }
        g.lineTo(X(sec + bw / 2), Y(+v));
      });
      if (open) { g.lineTo(X(th.t[th.t.length - 1] + bw), thTop + thH - 2); g.closePath(); g.fill(); }
      g.globalAlpha = 1;
      g.strokeStyle = C.ink2;
      g.lineWidth = 1.2;
      g.beginPath();
      open = false;
      th.t.forEach((sec, i) => {
        const v = th.power[i];
        if (!fin(v)) { open = false; return; }
        if (open) g.lineTo(X(sec + bw / 2), Y(+v)); else { g.moveTo(X(sec + bw / 2), Y(+v)); open = true; }
      });
      g.stroke();
      g.fillStyle = C.ink3;
      words(g, 'theta', L - 4, thTop + 11, L - 6, 10, 'right', C.font);
      words(g, Number(top).toPrecision(2), L - 4, thTop + 21, L - 6, 9, 'right', C.font);
      words(g, '0', L - 4, thTop + thH - 3, L - 6, 9, 'right', C.font);
    } else {
      g.fillStyle = C.ink3;
      words(g, t.theta_why ? 'Theta could not be read here.' : 'Reading theta…', L + pw / 2, thTop + thH / 2 + 4,
        pw - 8, 10, 'center', C.font);
    }
    // Minutes along the bottom.
    const mins = dur / 60;
    const step = [1, 2, 5, 10, 15, 20, 30, 60].find((st) => mins / st <= Math.max(2, Math.floor(pw / 70))) || 60;
    g.fillStyle = C.ink3;
    for (let m = 0; m <= mins + 1e-9; m += step) {
      const x = X(m * 60);
      g.fillRect(x, h - B + 1, 1, 4);
      words(g, m + (m === 0 ? ' min' : ''), x, h - 4, 60, 10, m === 0 ? 'left' : 'center', C.font);
    }
    overlay();
  }

  /* The fifteen panels of one STATE -- low contacts in or out, and which
     contacts are interpolated (the card's, none, or a set tried here). Each
     state is asked for and built once and then kept, hidden, so flipping
     back to one already seen is instant: nothing is asked for or built
     again (2026-11-13: "have a quick/no need to rerender everytime filp"). */
  const ipSpec = (D) => (D.ipTry ? D.ipTry.join(',') : D.interpOff ? '0' : '');
  /* The time window (2026-11-13: "2 konbs that limits ... which DS spikes
     are included based on the time they appeared"): null is the card's own
     (or none), false is the whole recording, [t0, t1] one tried here. */
  const twSpec = (D) => (D.twTry === false ? '0' : Array.isArray(D.twTry) ? D.twTry.join(',') : '');
  const stateKey = (D) => (D.low ? 'low' : '') + '|' + ipSpec(D) + '|' + twSpec(D);
  function showState(D, st, prev) {
    const o = D.o;
    D.loading = false;
    D.waitBox.hidden = true;
    for (const x of D.states.values()) x.box.hidden = x !== st;
    D.sv = st.sv;
    D.rowOf = st.rowOf;
    D.panels = st.panels;
    D.ipSaved = st.sv.interp_saved || st.sv.interp || [];
    D.twSaved = st.sv.twin_saved || null;
    D.twSwitched = false;
    if (D.ipSwitched && prev && prev !== st.sv) D.ipDiffText = ipDiff(prev, st.sv);
    D.ipSwitched = false;
    if (!look(D) && !st.savedSet) {
      // What is kept for everybody, from the recording as the card has it
      // (a look keeps every line at its default).
      const ch = 'choice' in st.sv ? st.sv.choice : S.splits[D.gid];
      D.saved = ch && ch.method ? { method: ch.method, cut: fin(ch.cut) ? +ch.cut : null } : null;
      st.savedSet = true;
    }
    for (const P of D.panels) {
      if (!P.live) continue;
      paint(P);
      if (P.cut != null && P.pending) ask(P, true);
    }
    applyOpen(D);
    paintButtons(D);
    paintLow(D);
    paintStrip(D);
    requestAnimationFrame(() => redraw(o));
    setTimeout(() => redraw(o), 60);
  }
  async function loadSplits(D) {
    const o = D.o;
    const gen = ++D.gen;
    for (const P of D.panels) { clearTimeout(P.timer); P.seq++; }
    D.follow = null;
    const key = stateKey(D);
    const prev = D.sv;
    const had = D.states.get(key);
    if (had) { D.lowErr = null; showState(D, had, prev); return; }
    for (const x of D.states.values()) x.box.hidden = true;
    D.panels = [];
    D.loading = true;
    D.waitBox.hidden = false;
    D.waitBox.className = 'muted erc-wait';
    put(D.waitBox, D.low ? 'Finding the contacts that read low and fitting every split again without them (a few seconds).'
      : 'Working out its fifteen splits: the first time, its read is fitted again (a few seconds).');
    paintLow(D);
    let sv;
    try {
      sv = await kit.api('/api/extraction/' + encodeURIComponent(D.aid) + '/split?version='
        + encodeURIComponent(D.version) + '&gid=' + encodeURIComponent(D.gid) + (D.low ? '&low=1' : '')
        + (ipSpec(D) ? '&interp=' + encodeURIComponent(ipSpec(D)) : '')
        + (twSpec(D) ? '&twin=' + encodeURIComponent(twSpec(D)) : ''));
    } catch (e) {
      if (!o.alive || gen !== D.gen) return;
      D.loading = false;
      // Back to where it was: the switch that failed is undone, and said.
      if (D.twSwitched) {
        D.lowErr = 'That time window could not be used: ' + e.message;
        D.twTry = D.twWas === undefined ? null : D.twWas;
      } else if (D.ipTry) {
        D.lowErr = 'Those contacts could not be interpolated: ' + e.message;
        D.ipTry = D.ipWas || null;
        D.ipLast = D.ipTry;
      } else if (D.low) {
        D.low = false;
        D.lowErr = 'The low contacts could not be left out: ' + e.message;
      } else D.lowErr = 'Not available: ' + e.message;
      D.ipSwitched = false;
      D.twSwitched = false;
      const back = D.states.get(stateKey(D));
      if (back) { const msg = D.lowErr; showState(D, back, null); D.lowErr = msg; paintLow(D); return; }
      D.waitBox.className = 'err';
      put(D.waitBox, 'Not available: ' + e.message);
      paintLow(D);
      return;
    }
    if (!o.alive || gen !== D.gen) return;
    D.lowErr = null;
    const st = { key, sv, box: el('div', { class: 'erc-state', 'data-state': key }), panels: [], rowOf: [], savedSet: false };
    const bv = sv.bite;
    if (bv && Array.isArray(bv.order)) bv.order.forEach((e, i) => { st.rowOf[e] = i; });
    // Built with this state as the dialog's: a panel reads D.sv and D.rowOf.
    D.sv = sv;
    D.rowOf = st.rowOf;
    D.panels = st.panels;
    D.ipSaved = sv.interp_saved || sv.interp || [];
    if (!look(D)) {
      const ch = 'choice' in sv ? sv.choice : S.splits[D.gid];
      D.saved = ch && ch.method ? { method: ch.method, cut: fin(ch.cut) ? +ch.cut : null } : null;
      st.savedSet = true;
    }
    D.building = st;
    const hm = sv.humps;
    for (const R of ROWS) {
      const span = hm && R.row !== 'both' ? hm[R.row] : null;
      const head = el('div', { class: 'erc-rowhead' }, [el('h3', { text: R.title }),
        el('p', { class: 'muted small', text: R.says + (span ? ' Contacts ' + span[0] + '–' + span[1] + '.'
          : R.row === 'both' && hm ? ' The two humps part at contact ' + hm.at + '.' : '') })]);
      const sec = el('section', { class: 'erc-row', 'data-row': R.row, 'aria-label': R.title }, [head]);
      if (R.row !== 'both' && !hm) {
        sec.appendChild(el('p', { class: 'muted small erc-onehump', text: 'The average CSD has one sink hump in this '
          + 'band, so there is no top and bottom hump to take apart.' }));
        st.box.appendChild(sec);
        continue;
      }
      const grid = el('div', { class: 'erc-panels' });
      for (const b of BASES) {
        const P = panel(D, b + R.suffix);
        st.panels.push(P);
        grid.appendChild(P.node);
      }
      sec.appendChild(grid);
      st.box.appendChild(sec);
    }
    D.building = null;
    st.box.insertBefore(scoreGrid(D, st), st.box.firstChild);
    D.rowsBox.appendChild(st.box);
    D.states.set(key, st);
    // A handful kept: the oldest goes, with its pictures.
    while (D.states.size > 6) {
      const old = D.states.keys().next().value;
      const gone = D.states.get(old);
      D.states.delete(old);
      gone.box.remove();
      o.draws = o.draws.filter((f) => f.st !== gone);
    }
    showState(D, st, prev);
  }
  /* Every state forgotten: what the card keeps has changed. */
  function dropStates(D) {
    for (const st of D.states.values()) st.box.remove();
    D.states.clear();
    D.o.draws = D.o.draws.filter((f) => !f.panel);
    D.panels = [];
  }

  /* The toggle and what it did, in words. */
  function paintLow(D) {
    D.lowBtn.setAttribute('aria-pressed', String(!!D.low));
    D.lowBtn.disabled = !!D.loading;
    const lw = D.sv && D.sv.low;
    let s;
    if (D.lowErr) {
      s = D.lowErr;
    } else if (D.loading) {
      s = 'Working every split out again…';
    } else if (!D.low || !lw) {
      s = 'A look with this recording’s low contacts left out: a contact whose signal reads low against its '
        + 'neighbours’ is made again from the two contacts either side, and every split is worked out again. Nothing is kept.';
    } else {
      const cs = lw.contacts || [];
      const bad = (lw.bad || []).length ? ' Already marked bad, as always: ' + lw.bad.join(', ') + '.' : '';
      if (!cs.length) {
        s = 'No contact reads more than ' + lw.frac_pct + '% low on this recording, so nothing is left out: every split '
          + 'below is as it was.' + bad;
      } else {
        const out = cs.filter((c) => !c.in_band).map((c) => c.c);
        s = 'Left out: ' + cs.map((c) => 'contact ' + c.c + ' (reads ' + Math.abs(+c.off_pct).toFixed(1) + '% low)').join(', ')
          + (out.length ? '; ' + out.join(' and ') + (out.length === 1 ? ' is' : ' are') + ' outside this band' : '')
          + '. Each is made again from the two contacts either side (a cubic, so it puts no notch of its own there), '
          + 'and every split below is worked out again. A look only: Use this is off while this is on.' + bad;
      }
    }
    const ips = D.ipSaved || [];
    const cw = 'contact' + (ips.length > 1 ? 's ' : ' ') + ips.join(', ');
    const tr = D.ipTry, last = D.ipLast;
    D.ipBtn.hidden = !ips.length && !last;
    put(D.ipLab, ips.length ? 'Contact' + (ips.length > 1 ? 's ' : ' ') + ips.join(', ') + ':' : 'Showing:');
    D.ipOn.hidden = !ips.length;
    D.ipOn.setAttribute('aria-pressed', String(!tr && !D.interpOff && !!ips.length));
    D.ipOffB.setAttribute('aria-pressed', String(!tr && (D.interpOff || !ips.length)));
    D.ipTryB.hidden = !last;
    put(D.ipTryB, last ? 'Trying ' + last.join(', ') : '');
    D.ipTryB.setAttribute('aria-pressed', String(!!tr));
    D.ipOn.disabled = D.ipOffB.disabled = D.ipTryB.disabled = D.ipGo.disabled = !!D.loading;
    D.ipOn.title = 'Show every split with ' + cw + ' interpolated, as the card has them.';
    D.ipOffB.title = 'Show every split as recorded, nothing interpolated' + (ips.length ? ': a look, nothing kept.' : '.');
    D.ipTryB.title = 'Show every split with the set tried here interpolated: a look, nothing kept.';
    D.ipKeep.hidden = !((tr || (ips.length && D.interpOff)) && !D.loading);
    put(D.ipKeep, tr ? 'Save this set on the card: interpolate ' + tr.join(', ') + ' for everybody'
      : 'Save “as recorded” for good: stop interpolating ' + ips.join(', ') + ' for everybody');
    if (!D.loading && !D.lowErr) {
      if (tr) {
        s += ' Showing contact' + (tr.length > 1 ? 's ' : ' ') + tr.join(', ') + ' INTERPOLATED, a set tried here: every split '
          + 'below worked out again. A look only: Use this is off; the card ' + (ips.length ? 'keeps ' + ips.join(', ')
          + ' interpolated.' : 'interpolates none.');
      } else if (ips.length) {
        s += D.interpOff
          ? ' Showing ' + cw + ' AS RECORDED, not interpolated: every split below worked out again. A look only: Use this is '
            + 'off; the card keeps them interpolated.'
          : ' Showing ' + cw + ' INTERPOLATED, as the card has them. Press As recorded to see every split without.';
      }
    }
    put(D.lowSay, s);
    put(D.ipDiff, D.loading ? '' : D.ipDiffText || '');
  }

  /* What switching the interpolation changed: the notched events and every
     split whose counts moved -- so a small difference is said, not hunted
     for. Where the pictures differ is the rows at those contacts. */
  function ipDiff(a, b) {
    const nm = (sv) => { const c = sv.interp || [];
      return !c.length ? 'as recorded' : c.join() === (sv.interp_saved || []).join() ? 'interpolated'
        : 'contacts ' + c.join(', ') + ' interpolated'; };
    const was = nm(a);
    const parts = [];
    const cam = (sv) => ((sv.bite || {}).bumps || {}).camel;
    if (fin(cam(a)) && fin(cam(b)) && cam(a) !== cam(b)) parts.push('events with a notch in a hump ' + cam(a) + ' → ' + cam(b));
    for (const m of METHODS) {
      const x = ((a.pre || {})[m] || {}).counts, y = ((b.pre || {})[m] || {}).counts;
      if (!x || !y) continue;
      const fx = (x['1'] || 0) + '/' + (x['2'] || 0), fy = (y['1'] || 0) + '/' + (y['2'] || 0);
      if (fx !== fy) parts.push(MNAME[m] + ' ' + fx + ' → ' + fy);
    }
    const ips = Array.from(new Set((a.interp || []).concat(b.interp || [], b.interp_saved || []))).sort((x, y) => x - y).join(', ');
    return parts.length ? 'Changed from ' + was + ': ' + parts.join('; ') + '. In the pictures, look at the rows at contacts '
      + ips + '.' : 'Nothing moved from ' + was + ': every split has the same counts, and the pictures differ only at '
      + 'contacts ' + ips + '.';
  }

  /* Off for good: the card's contacts put back, for everybody. */
  async function keepIpOff(D) {
    const ips = (D.ipSaved || []).join(', ');
    const set = D.ipTry || [];
    if (!window.confirm((set.length ? 'Interpolate ' + set.join(', ') : 'Stop interpolating ' + ips) + ' on ' + D.r.session_label
      + ', for everybody, in every set? A Bite line placed by hand on it goes back to its default.')) return;
    try {
      await kit.post('/api/extraction/interp', { artifact_id: D.aid, version: D.version, gid: D.gid, contacts: set });
    } catch (e) { say(D.o, 'Not changed: ' + e.message, true); return; }
    D.interpOff = false;
    D.ipTry = null;
    D.ipLast = null;
    D.ipDiffText = '';
    dropStates(D);
    say(D.o, set.length ? 'Contacts ' + set.join(', ') + ' are interpolated on this recording now; the card behind shows it so.'
      : 'Contacts ' + ips + ' are no longer interpolated on this recording; the card behind shows it so. Type them '
      + 'under its band again to interpolate them.');
    try { await kit.reloadCard(D.gid); } catch (e) { /* the room says so itself */ }
    const fresh = kit.recOf(D.gid);
    if (fresh) D.r = fresh;
    loadSplits(D);
  }
  /* A look: low contacts left out, or interpolation off -- nothing kept. */
  const look = (D) => !!(D.low || D.ipTry || (D.interpOff && (D.ipSaved || []).length) || D.twTry != null);

  /* ---------- one panel: one way of splitting ---------- */
  function panel(D, m) {
    const sv = D.sv;
    const M = (sv.methods || {})[m];
    const row = rowOf(m);
    const name = (M && M.name) || MNAME[m];
    const node = el('section', { class: 'erc-panel', 'data-method': m, 'data-row': row, 'aria-label': name });
    node.appendChild(el('div', { class: 'erc-ph' }, [el('h3', { text: name }),
      m === sv.own ? el('span', { class: 'chip erc-own', text: sv.direct ? 'the default' : 'X-ray’s own' }) : null]));
    node.appendChild(el('p', { class: 'muted small', text: saysOf(m) }));
    if (!M || !Array.isArray(M.x) || !M.x.length) {
      node.appendChild(el('p', { class: 'muted small erc-none', text: 'Not worked out for this recording'
        + (M && M.why ? ': ' + M.why : '.') }));
      return { m, node, live: false };
    }
    // The sink raster is always the whole band's, in the main Bite line's
    // rows; a Bite line on one hump brings its own order, cost and sides.
    const main = sv.bite && !sv.bite.error && Array.isArray(sv.bite.raster) && Array.isArray(sv.bite.order) ? sv.bite : null;
    let bite = main;
    let biteErr = main ? null : sv.bite && sv.bite.error;
    if (isBite(m) && row !== 'both') {
      const br = (sv.bite_rows || {})[row];
      bite = main && br && !br.error && Array.isArray(br.order)
        ? Object.assign({}, main, br, { raster: main.raster, contacts: main.contacts, bumps: main.bumps }) : null;
      if (br && br.error) biteErr = br.error;
    }
    const P = { D, m, M, row, name, bite, node, live: true, pre: (sv.pre || {})[m] || {},
                cut: null, types: (M.types || []).slice(), classes: null, counts: null, scores: null,
                seq: 0, timer: null, sentAt: 0, pending: false, err: null, imgs: {} };
    P.classes = P.pre.classes || D.r.classes;
    P.counts = P.pre.counts || D.r.counts;
    P.scores = P.pre.scores || null;
    P.layers = P.pre.layers || null;
    if (isBite(m) && bite && !P.scores) P.scores = biteScores(P);
    // The line kept before, where it was kept (not in a look with the low
    // contacts left out: every line starts at its default there).
    const ch = look(D) ? null : D.saved;
    if (ch && ch.method === m && ch.cut != null) {
      const c = normCut(P, ch.cut);
      if (c != null) {
        P.cut = c;
        P.types = localTypes(P, c);
        if (D.r.split && D.r.split.method === m && !D.r.split.error) { P.classes = D.r.classes; P.counts = D.r.counts; }
        if (isBite(m) && bite) P.scores = Object.assign({}, P.scores, biteScores(P));
        P.pending = true;
      }
    }
    if (isBite(m) && !bite && biteErr) {
      node.appendChild(el('p', { class: 'err small', text: 'Its sink picture is not available: ' + biteErr }));
    }

    // The line: on the sink raster for the Bite line, on the plot for the rest.
    const onRaster = isBite(m) && !!bite;
    P.lineCv = el('canvas', { class: 'erc-cv erc-line ' + (onRaster ? 'erc-raster' : 'erc-scatter'), tabindex: '0', role: 'slider',
      'aria-label': 'The line for ' + name + ': drag it, or use the arrow keys' });
    node.appendChild(el('p', { class: 'erc-cap', text: onRaster
      ? 'Each column one event, in the order their ' + (row === 'both' ? '' : row + '-hump ') + 'sinks overlap; contacts '
        + 'down, darker where its sink sits' + (row === 'both' ? '' : ', the other hump dimmed')
        + '. Drag the line, or use the arrow keys.'
      : 'Each dot one event. Drag the line, or use the arrow keys.' }));
    node.appendChild(P.lineCv);
    // Where each sink is strongest, in words under whichever raster it has.
    const pkRow = () => (P.pk = el('p', { class: 'erc-peaks' }, [el('i', { class: 'erc-pk-dot', 'aria-hidden': 'true' }),
      (P.pkTxt = el('span'))]));
    if (onRaster && peaksOf(P)) node.appendChild(pkRow());
    if (onRaster && bite.sweep && Array.isArray(bite.sweep.ncut) && bite.sweep.ncut.length) {
      P.costCv = el('canvas', { class: 'erc-cv erc-cost' });
      node.appendChild(el('p', { class: 'erc-cap', text: 'What a line costs at each place: lower splits cleaner. '
        + 'The ticks are its dips; click one to put the line there. Shaded: a side too small for the default line.' }));
      node.appendChild(P.costCv);
      const cands = (bite.sweep.candidates || []).filter((c) => fin(c.k));
      if (cands.length) {
        P.dips = cands.map((c) => el('button', { class: 'btn small erc-dip', type: 'button', 'data-k': String(c.k), 'aria-pressed': 'false',
          text: 'after ' + c.k + ' · SI ' + fmt(c.si, 2),
          title: c.clears ? 'A dip in the cost: the line after event ' + c.k + ' of the order.'
            : 'A dip, but one side is smaller than the default line allows.',
          onclick: () => setCut(P, c.k - 0.5) }));
        node.appendChild(el('div', { class: 'erc-dips' }, [el('span', { text: 'Snap to a dip:' })].concat(P.dips)));
      }
    }
    if (!onRaster && bite) {
      P.sortCv = el('canvas', { class: 'erc-cv erc-raster erc-sorted' });
      node.appendChild(el('p', { class: 'erc-cap', text: 'The same sinks sorted by ' + axisWord(P)
        + ': each column one event, contacts down' + (row === 'both' ? '' : ', the other hump dimmed')
        + '. The line can be dragged here too.' }));
      node.appendChild(P.sortCv);
      if (peaksOf(P)) node.appendChild(pkRow());
    }

    // What the line gives.
    P.lw = el('p', { class: 'small erc-lw' });
    P.n1 = el('b', { class: 'erc-ds1' });
    P.n2 = el('b', { class: 'erc-ds2' });
    P.si = el('p', { class: 'small erc-si' });
    P.wb = el('p', { class: 'small muted erc-wb' });
    P.pst = el('p', { class: 'erc-pst', 'aria-live': 'polite' });
    node.appendChild(P.lw);
    P.n3 = el('span', { class: 'erc-n3' });
    node.appendChild(el('p', { class: 'erc-n' }, [P.n1, T(' · '), P.n2, P.n3]));
    node.appendChild(P.si);
    if (row !== 'both') {
      // The same split scored on the one hump it was made on.
      P.hsi = el('p', { class: 'small erc-hsi' });
      node.appendChild(P.hsi);
    }
    node.appendChild(P.wb);
    // The mix-up, three ways (the sanity check), what the set's mode did
    // here, and every event's probability with the cut-off.
    P.mix = el('p', { class: 'small erc-mix' });
    P.lay = el('p', { class: 'small muted erc-lay' });
    node.appendChild(P.mix);
    node.appendChild(P.lay);
    if (((P.pre.layers || {}).trim || {}).p_max) {
      P.probCv = el('canvas', { class: 'erc-cv erc-prob' });
      node.appendChild(el('p', { class: 'erc-cap', text: 'How sure the two-Gaussian fit is of each event (its more probable '
        + 'class). Left of the line is unsure. Drag the line to move the set’s cut-off.' }));
      node.appendChild(P.probCv);
      drag(P.probCv, (px, phase) => { const f = P.probCv.__map; if (f) probCut(P, f(px), phase); });
    }
    if (isBite(m)) {
      P.vd = el('p', { class: 'small erc-verdict' });
      node.appendChild(P.vd);
      const bm = (bite && bite.bumps) || {};
      const note = [];
      const hm = sv.humps;
      if (row !== 'both') {
        if (hm && hm[row]) note.push('Only the ' + row + ' hump’s sink counts here, contacts ' + hm[row][0] + '–' + hm[row][1] + '.');
      } else if (bm.sink === 'humps') {
        note.push('The sink is the recording’s two humps' + (fin(bm.hump_at) ? ', parted at contact ' + bm.hump_at : '')
          + ', each taken whole on every event.');
        if (bm.camel > 0) note.push(plural(bm.camel, 'event') + ' had a notch inside a hump; it stays one hump.');
        if (bm.short > 0) note.push(plural(bm.short, 'event') + ' had sink in one hump only.');
      } else {
        if (bm.short > 0) note.push(plural(bm.short, 'event') + ' had fewer than two sink bumps.');
        if (bm.third_big > 0) note.push(bm.third_big + ' had a third sink bump at least half the size of the second: a narrower band may follow DS1 and DS2 better.');
      }
      if (note.length) node.appendChild(el('p', { class: 'small muted erc-bumps', text: note.join(' ') }));
      if (m === 'bite' && !D.low && D.sv.stale && D.sv.stale.words) {
        node.appendChild(el('p', { class: 'small erc-stale', text: D.sv.stale.words
          + (D.sv.stale.by ? ' (It was placed by ' + D.sv.stale.by + '.)' : '') }));
      }
    }
    node.appendChild(P.pst);

    // Its classes, drawn as the cards draw them.
    P.csd = [el('canvas', { class: 'erc-cv erc-csd' }), el('canvas', { class: 'erc-cv erc-csd' })];
    P.capN = [el('span', { class: 'erc-cap-n' }), el('span', { class: 'erc-cap-n' })];
    node.appendChild(el('div', { class: 'erc-pics' }, [0, 1].map((k) => el('div', { class: 'pic' }, [
      el('div', { class: 'cap' }, [el('b', { class: k ? 'erc-ds2' : 'erc-ds1', text: 'DS' + (k + 1) }), P.capN[k]]), P.csd[k]]))));
    P.prof = el('canvas', { class: 'erc-cv erc-prof' });
    node.appendChild(el('div', { class: 'pic' }, [el('div', { class: 'cap' }, [
      el('span', { text: 'Depth profile at the box’s time, mean ± SEM' })]), P.prof]));

    P.use = el('button', { class: 'btn small primary erc-use', type: 'button', text: 'Use this', onclick: () => useThis(P) });
    P.back = el('button', { class: 'btn small erc-default', type: 'button', text: 'Back to its default line',
      title: isBite(m) ? 'The line where its cost is lowest.' : 'k-means’ own split.', onclick: () => setCut(P, null) });
    node.appendChild(el('div', { class: 'erc-acts' }, [P.use, P.back]));

    drag(P.lineCv, (px) => { const f = P.lineCv.__map; if (f) setCut(P, f(px)); });
    P.lineCv.addEventListener('keydown', (e) => keyLine(P, e));
    if (P.sortCv) drag(P.sortCv, (px) => { const f = P.sortCv.__map; if (f) setCut(P, f(px)); });
    if (P.costCv) {
      drag(P.costCv, (px, phase) => {
        const f = P.costCv.__map;
        if (!f) return undefined;
        if (phase === 'down') {
          const k = f.dipAt(px);
          if (k != null) { setCut(P, k - 0.5); return 'stop'; }
        }
        setCut(P, f.at(px));
        return undefined;
      });
    }
    const st = D.building;
    const f = () => { if ((st && st.box.hidden) || P.node.hidden) return; paintCanvases(P); paintPics(P); };
    f.panel = true;
    f.st = st;
    D.o.draws.push(f);
    return P;
  }

  const axisWord = (P) => (P.m === 'delta' ? 'the sink gap' : (P.M.axis || 'PC1'));
  /* Is the split a Bite line on one hump? Its local scores are that hump's. */
  const humpRow = (P) => P.row && P.row !== 'both';

  /* ---------- where a line is ---------- */
  /* Events with a sink: the Bite line can sit between any two of them. */
  function liveK(P) {
    const sw = P.bite && P.bite.sweep;
    if (sw && Array.isArray(sw.k) && sw.k.length) return sw.k.length + 1;
    if (P.bite && Array.isArray(P.bite.left_is) && P.bite.left_is.length) return P.bite.left_is.length + 1;
    return P.M.x.filter(fin).length;
  }
  /* The Bite line by place: between places k-1 and k is cut k - 0.5. */
  const kOf = (P, cut) => clamp(Math.ceil(+cut - 1e-9), 1, Math.max(1, liveK(P) - 1));
  const effCut = (P) => (P.cut != null ? P.cut : P.M.cut);

  function uniq(P) {
    if (!P._u) P._u = Array.from(new Set(P.M.x.filter(fin).map(Number))).sort((a, b) => a - b);
    return P._u;
  }
  function sortedCols(P) {
    if (!P._cols) {
      const xs = P.M.x;
      P._cols = xs.map((_, i) => i).sort((a, b) => {
        const fa = fin(xs[a]), fb = fin(xs[b]);
        if (fa !== fb) return fa ? -1 : 1;
        return fa ? (xs[a] - xs[b]) || (a - b) : a - b;
      });
      P._sx = P._cols.filter((i) => fin(xs[i])).map((i) => +xs[i]);
    }
    return P._cols;
  }
  function sortedAt(P) {
    sortedCols(P);
    const c = effCut(P);
    let q = 0;
    while (q < P._sx.length && P._sx[q] <= c) q++;
    return q;
  }

  /* A line asked for, as the panel keeps it: the Bite line on a place, the
     rest inside their events (one at least on each side); null when it is
     the method's own default. */
  function normCut(P, cut) {
    if (!fin(cut)) return null;
    if (isBite(P.m)) {
      const k = kOf(P, cut);
      return k === kOf(P, P.M.cut) ? null : k - 0.5;
    }
    let c = +cut;
    const u = uniq(P);
    if (u.length >= 2) c = clamp(c, (u[0] + u[1]) / 2, (u[u.length - 2] + u[u.length - 1]) / 2);
    return fin(P.M.cut) && Math.abs(c - P.M.cut) <= 1e-9 * Math.max(1, Math.abs(c)) ? null : c;
  }

  /* Each event's side at once, before the server says: for the Bite line
     from left_is (which class the left side is at each place); for the rest
     the right side is whichever class most of its events are now. An event
     with no place on the axis (no sink in that hump) is on the right, as
     the server puts it. */
  function localTypes(P, cut) {
    const xs = P.M.x;
    if (isBite(P.m) && P.bite && Array.isArray(P.bite.left_is) && P.bite.left_is.length) {
      const k = kOf(P, cut);
      const left = P.bite.left_is[k - 1] === 2 ? 2 : 1;
      return xs.map((x) => (fin(x) && x < k - 0.5 ? left : 3 - left));
    }
    const onRight = (x) => !fin(x) || x > cut;
    let r1 = 0, r2 = 0;
    xs.forEach((x, i) => { if (onRight(x)) { if (P.types[i] === 1) r1++; else r2++; } });
    const right = r1 >= r2 ? 1 : 2;
    return xs.map((x) => (onRight(x) ? right : 3 - right));
  }

  /* The server's verdict words, for the Bite line while it is being asked. */
  function verdictOf(si, small, n) {
    if (!fin(si)) return { word: 'none', say: 'No line: too few events.' };
    const out = si >= 0.5 ? { word: 'separate', say: 'DS1 and DS2 sinks barely overlap: two families.' }
      : si >= 0.2 ? { word: 'partial', say: 'DS1 and DS2 sinks overlap in part: a lean, not a gap.' }
        : { word: 'one family', say: 'The sinks are one family; any line here splits a blob.' };
    if (small != null && n && small < 0.05 * n) {
      out.say += ' The smaller side is ' + plural(small, 'event') + ': check they are dentate spikes.';
    }
    return out;
  }
  /* The Bite line's numbers at its place, from the sweep: at once. On one
     hump the sweep is that hump's overlap, so it is said as the hump's and
     the one yardstick (both humps) waits for the server. */
  function biteScores(P) {
    const sw = P.bite.sweep || {};
    const k = kOf(P, effCut(P)), i = k - 1;
    const left = (P.bite.left_is || [])[i] === 2 ? 2 : 1;
    const at = (a) => (Array.isArray(a) ? a[i] : null);
    const wl = at(sw.within_left), wr = at(sw.within_right), si = at(sw.si);
    let n1 = 0, n2 = 0;
    for (const t of P.types) { if (t === 1) n1++; else if (t === 2) n2++; }
    const own = { within1: left === 1 ? wl : wr, within2: left === 1 ? wr : wl, between: at(sw.between), si,
                  ncut: at(sw.ncut) };
    if (humpRow(P)) return { n1, n2, hump: Object.assign({ side: P.row }, own) };
    return Object.assign(own, { n1, n2, verdict: verdictOf(si, Math.min(n1, n2), P.types.length), local: true });
  }

  /* ---------- moving a line ---------- */
  function setCut(P, cut) {
    const c = cut == null ? null : normCut(P, cut);
    P.D.follow = P;
    if (c === P.cut) { paintStrip(P.D); return; }
    P.cut = c;
    P.err = null;
    if (c == null) {
      clearTimeout(P.timer);
      P.seq++;                                  // an answer on its way is for a line gone
      P.types = (P.M.types || []).slice();
      P.classes = P.pre.classes || P.D.r.classes;
      P.counts = P.pre.counts || P.D.r.counts;
      P.scores = P.pre.scores || (isBite(P.m) && P.bite ? biteScores(P) : null);
      P.layers = P.pre.layers || null;
      P.pending = false;
      paint(P);
      paintPics(P);
      return;
    }
    P.types = localTypes(P, c);
    if (isBite(P.m) && P.bite) P.scores = biteScores(P);
    P.layers = null;                            // this line's, when the server says
    P.pending = true;
    paint(P);
    ask(P);
  }

  /* The classes a line gives, from the server: at most every 350 ms while
     dragging, once more when it stops; only the newest answer is drawn. */
  function ask(P, now) {
    clearTimeout(P.timer);
    const go = async () => {
      P.timer = null;
      const D = P.D;
      if (P.cut == null || !D.o.alive) return;
      const seq = ++P.seq, cut = P.cut;
      P.sentAt = Date.now();
      let got;
      try {
        got = await kit.post('/api/extraction/split/preview', { artifact_id: D.aid, version: D.version, gid: D.gid,
          method: P.m, cut, low: !!D.low, interp: D.ipTry ? D.ipTry : !D.interpOff,
          twin: D.twTry == null ? undefined : D.twTry });
      } catch (e) {
        if (seq !== P.seq || !D.o.alive) return;
        P.err = e.message;
        P.pending = false;
        paintText(P);
        return;
      }
      if (seq !== P.seq || !D.o.alive) return;
      P.err = null;
      P.pending = false;
      if (Array.isArray(got.types) && got.types.length === P.M.x.length) P.types = got.types;
      if (got.classes) { P.classes = got.classes; P.counts = got.counts || P.counts; }
      // No score from the server: none said, rather than the last line's.
      P.scores = got.scores || (isBite(P.m) && P.bite ? biteScores(P) : null);
      P.layers = got.layers || null;
      paint(P);
      paintPics(P);
    };
    if (now || Date.now() - P.sentAt > 350) go();
    else P.timer = setTimeout(go, 140);
  }

  function keyLine(P, e) {
    const step = e.shiftKey ? 10 : 1;
    let dir = 0;
    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') dir = 1;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') dir = -1;
    else return;
    e.preventDefault();
    if (isBite(P.m)) { setCut(P, kOf(P, effCut(P)) + dir * step - 0.5); return; }
    const u = uniq(P);
    if (u.length < 2) return;
    const c = effCut(P);
    let q = 0;
    while (q < u.length && u[q] <= c) q++;
    q = clamp(q + dir * step, 1, u.length - 1);
    setCut(P, (u[q - 1] + u[q]) / 2);
  }

  /* ---------- saving ---------- */
  function inUse(P) {
    const D = P.D;
    const ch = D.saved && D.saved.method ? D.saved : { method: D.sv.own, cut: null };
    if (ch.method !== P.m) return false;
    const c = ch.cut == null ? null : normCut(P, ch.cut);
    return c == null ? P.cut == null : P.cut != null && Math.abs(P.cut - c) < 1e-9;
  }

  async function useThis(P) {
    const D = P.D;
    if (D.busy || look(D) || inUse(P)) return;
    // Its own method at its own line is the default: kept as none by hand.
    const method = P.m === D.sv.own && P.cut == null ? null : P.m;
    const cut = P.cut;
    D.busy = true;
    paintButtons(D);
    say(D.o, 'Keeping ' + P.name + ' for everybody.');
    try {
      const got = await kit.post('/api/extraction/split', { artifact_id: D.aid, version: D.version, gid: D.gid, method, cut });
      if ((got.stuck || []).length) throw new Error(got.stuck.join('; '));
      D.saved = method == null ? null : { method, cut };
      D.busy = false;
      paintButtons(D);
      paintStrip(D);
      say(D.o, 'Kept for everybody: ' + P.name + ', ' + lineShort(P) + '. The card behind shows it now.');
    } catch (e) {
      D.busy = false;
      paintButtons(D);
      say(D.o, 'Not kept: ' + e.message, true);
      return;
    }
    try { await kit.reloadCard(D.gid); } catch (e) { /* the room says so itself */ }
    const fresh = kit.recOf(D.gid);
    if (fresh) D.r = fresh;
  }

  /* ---------- words ---------- */
  function lineWords(P) {
    const M = P.M;
    if (isBite(P.m)) {
      const K = liveK(P), k = kOf(P, effCut(P)), n = M.x.length;
      const rest = n > K ? ' ' + plural(n - K, 'event') + ' with no sink sit' + (n - K === 1 ? 's' : '') + ' at the right end.' : '';
      return (P.cut == null ? 'Its default line' : 'Your line') + ': after ' + k + ' of ' + K + ' events.' + rest;
    }
    if (P.cut != null) return 'Your line at ' + cutText(P.cut) + ' on ' + (M.axis || 'the x axis') + '.';
    const none = M.x.filter((x) => !fin(x)).length;
    const rest = none ? ' ' + plural(none, 'event') + (P.row === 'both' ? ' with sink in one hump only '
      : ' with no sink in the ' + P.row + ' hump ') + (none === 1 ? 'goes' : 'go') + ' to the right side.' : '';
    return is1D(P.m) ? 'k-means’ own line, at ' + cutText(M.cut) + '.' + rest
      : 'k-means’ own split, which is not a line: drawn at ' + cutText(M.cut) + ', halfway between the two classes.';
  }
  function lineShort(P) {
    if (P.cut == null) return 'its default line';
    return isBite(P.m) ? 'a line after ' + kOf(P, P.cut) + ' events' : 'a line at ' + cutText(P.cut);
  }
  /* The split scored on the one hump it was made on. */
  function humpWords(P, sc, stale) {
    if (!humpRow(P)) return '';
    const h = sc && sc.hump;
    if (!h || !fin(h.si)) return stale ? 'On the ' + P.row + ' hump alone: being worked out.' : '';
    const si = +h.si;
    return 'On the ' + P.row + ' hump alone: SI ' + fmt(si, 2) + ', ' + (si >= 0.5 ? 'its sinks there overlap little.'
      : si >= 0.2 ? 'they overlap in part there.' : 'one family there too.');
  }
  function siWords(sc) {
    if (!sc || !fin(sc.si)) return 'No overlap score for this split.';
    const si = +sc.si;
    const w = (sc.verdict && sc.verdict.word) || (si >= 0.5 ? 'separate' : si >= 0.2 ? 'partial' : 'one family');
    return 'SI ' + fmt(si, 2) + ': ' + (w === 'separate' ? 'DS1 and DS2 sinks overlap little.'
      : w === 'partial' ? 'DS1 and DS2 sinks overlap in part.'
        : w === 'none' ? 'too few events on a side to say.'
          : 'DS1 and DS2 sinks overlap about as much as each overlaps itself: one family.');
  }
  function wbWords(D, sc) {
    if (!sc || (!fin(sc.within1) && !fin(sc.within2) && !fin(sc.between))) return '';
    const f = kit.flipped(D.r);
    return 'How much the sinks overlap: within DS1 ' + fmt(f ? sc.within2 : sc.within1, 2) + ', within DS2 '
      + fmt(f ? sc.within1 : sc.within2, 2) + ', between them ' + fmt(sc.between, 2) + '. SI is 1 − between ÷ the mean within.';
  }
  /* The server's 1 is shown as DS2 when the two are swapped by hand. */
  const shownT = (D, t) => (kit.flipped(D.r) && (t === 1 || t === 2) ? 3 - t : t);

  /* ---------- painting a panel, in place ---------- */
  function paint(P) {
    paintCanvases(P);
    paintText(P);
    if (P.D.tlCv && followed(P.D) === P) paintStrip(P.D);       // the timeline follows it
  }

  function paintText(P) {
    const D = P.D;
    let a = 0, b = 0;
    for (const t of P.types) { const s = shownT(D, t); if (s === 1) a++; else if (s === 2) b++; }
    put(P.n1, 'DS1 ' + a);
    put(P.n2, 'DS2 ' + b);
    const mt = modeTypes(P);
    if (mt !== P.types) {
      let x = 0, y = 0, z = 0, u = 0;
      for (const t of mt) { const s = shownT(D, t); if (s === 1) x++; else if (s === 2) y++; else if (s === 3) z++; else if (s === 4) u++; }
      put(P.n1, 'DS1 ' + x);
      put(P.n2, 'DS2 ' + y);
      put(P.n3, (z ? ' · DS3 ' + z : '') + (u ? ' · unsure ' + u : ''));
    } else put(P.n3, '');
    const lw = lineWords(P);
    put(P.lw, lw);
    P.lineCv.setAttribute('aria-valuetext', lw);
    if (isBite(P.m)) {
      P.lineCv.setAttribute('aria-valuemin', '1');
      P.lineCv.setAttribute('aria-valuemax', String(Math.max(1, liveK(P) - 1)));
      P.lineCv.setAttribute('aria-valuenow', String(kOf(P, effCut(P))));
    } else if (fin(effCut(P))) {
      P.lineCv.setAttribute('aria-valuenow', cutText(effCut(P)));
    }
    const sc = P.scores;
    const stale = P.pending && !(sc && sc.local);
    put(P.si, stale ? 'SI for this line: being worked out.' : siWords(sc));
    put(P.wb, stale ? '' : wbWords(D, sc));
    paintMix(P);
    paintCell(P);
    if (P.hsi) put(P.hsi, humpWords(P, sc, P.pending));
    if (P.vd) put(P.vd, stale ? '' : (sc && sc.verdict && sc.verdict.say) || '');
    if (P.pkTxt) put(P.pkTxt, peakWords(P));
    put(P.pst, P.err ? 'Not worked out for this line: ' + P.err : P.pending ? 'Working out its classes for this line.' : '');
    P.pst.classList.toggle('err', !!P.err);
    if (P.dips) {
      const k = kOf(P, effCut(P));
      for (const d of P.dips) d.setAttribute('aria-pressed', String(Number(d.dataset.k) === k));
    }
    P.back.disabled = P.cut == null;
    paintButtons(D);
  }

  function paintButtons(D) {
    for (const P of D.panels) {
      if (!P.live) continue;
      // With the low contacts left out it is a look: nothing is kept, and
      // nothing on it is the card's.
      const lk = look(D);
      const u = !lk && inUse(P);
      P.node.classList.toggle('inuse', u);
      put(P.use, u ? 'In use' : 'Use this');
      P.use.disabled = u || D.busy || lk;
      if (P.cell) P.cell.classList.toggle('inuse', u);
      P.use.classList.toggle('primary', !u && !lk);
      P.use.title = lk ? (D.low ? 'A look with the low contacts left out: turn that off to keep a split.'
        : 'A look with other contacts interpolated than the card has: go back to the card’s to keep a split.')
        : u ? 'The card shows this split now.'
          : 'Keep this split, at this line, for everybody: the card and the stats count it.';
    }
  }

  function paintCanvases(P) {
    if (P.probCv) drawProb(P.probCv, P);
    if (isBite(P.m) && P.bite) {
      drawRaster(P.lineCv, P, P.bite.order, kOf(P, effCut(P)), 'bite');
      if (P.costCv) drawCost(P.costCv, P);
    } else {
      drawScatter(P.lineCv, P);
      if (P.sortCv) drawRaster(P.sortCv, P, sortedCols(P), sortedAt(P), 'sorted');
    }
  }

  /* Its two classes' mean CSDs and the depth profile, by the room's kit, on
     a copy of the record with this line's classes. */
  function paintPics(P) {
    const D = P.D;
    const rec = Object.assign({}, D.r, { classes: P.classes || D.r.classes, counts: P.counts || D.r.counts });
    const cls = kit.shownClasses(rec);
    for (let k = 0; k < 2; k++) {
      const c = cls.find((x) => x.shown === k + 1);
      put(P.capN[k], c ? plural(c.n, 'event') + (kit.flipped(D.r) ? ' · X-ray’s DS' + c.c : '') : 'none');
      if (c) kit.drawCsd(P.csd[k], rec, c);
      else kit.sized(P.csd[k]);
    }
    kit.drawProfile(P.prof, rec);
  }

  /* ---------- the pictures of a line ---------- */
  /* The sink raster as an image: each column one event, contacts down, the
     ink's strength its sink there (each event scaled to its own peak).
     Made once per order and theme; the sides are tinted under it. */
  function rasterImg(P, cols, kind, ink) {
    const key = kind + '|' + ink + '|' + cols.length;
    const got = P.imgs[kind];
    if (got && got.key === key) return got.img;
    const rows = P.bite.raster, rowOf = P.D.rowOf;
    const nc = (P.bite.contacts || []).length, n = cols.length;
    const rgb = rgbOf(ink);
    const off = document.createElement('canvas');
    off.width = Math.max(1, n);
    off.height = Math.max(1, nc);
    const og = off.getContext('2d');
    const im = og.createImageData(off.width, off.height);
    for (let i = 0; i < n; i++) {
      const row = rows[rowOf[cols[i]]] || [];
      for (let j = 0; j < nc; j++) {
        const v = row[j];
        const a = fin(v) ? clamp(+v, 0, 1) : 0;
        const p = (j * off.width + i) * 4;
        im.data[p] = rgb[0]; im.data[p + 1] = rgb[1]; im.data[p + 2] = rgb[2];
        im.data[p + 3] = Math.round(235 * Math.pow(a, 0.8));
      }
    }
    og.putImageData(im, 0, 0);
    P.imgs[kind] = { key, img: off };
    return off;
  }

  function drawRaster(cv, P, cols, at, kind) {
    const s = kit.sized(cv);
    if (!s) return;
    const { g, w, h } = s;
    const C = pal();
    const cs = P.bite.contacts || [];
    const n = cols.length, nc = cs.length;
    const L = 30, R = 8, Tp = 18, B = 30;
    const pw = w - L - R, ph = h - Tp - B;
    if (!n || !nc || pw < 20 || ph < 20) return;
    const X = (q) => L + (q / n) * pw;
    const sh = (e) => shownT(P.D, P.types[e]);
    // Each side tinted under the sinks, and a band of its colour beneath.
    let i0 = 0;
    for (let i = 1; i <= n; i++) {
      if (i < n && sh(cols[i]) === sh(cols[i0])) continue;
      const one = sh(cols[i0]) === 1;
      const x0 = X(i0), x1 = X(i);
      g.fillStyle = one ? C.s1 : C.s2;
      g.fillRect(x0, Tp, x1 - x0, ph);
      g.fillStyle = one ? C.ds1 : C.ds2;
      g.fillRect(x0, Tp + ph + 3, x1 - x0, 5);
      i0 = i;
    }
    const img = rasterImg(P, cols, kind, C.ink);
    g.imageSmoothingEnabled = n > pw;
    g.drawImage(img, L, Tp, pw, ph);
    g.imageSmoothingEnabled = true;
    g.strokeStyle = C.line2;
    g.lineWidth = 1;
    g.strokeRect(L + 0.5, Tp + 0.5, pw - 1, ph - 1);
    // Where each sink is strongest: a dot on every event, and the median of
    // the top and of the bottom one ticked on the contact axis.
    const pk = peaksOf(P);
    const yRow = (j) => Tp + ((j + 0.5) / nc) * ph;
    const ticks = [];
    if (pk) {
      const r = clamp((pw / n) * 0.45, 0.9, 2.2);
      g.fillStyle = C.peak;
      g.globalAlpha = 0.85;
      for (let i = 0; i < n; i++) {
        const row = pk.ev[cols[i]];
        if (!row || !row.length) continue;
        const x = X(i + 0.5);
        for (const j of row) { g.beginPath(); g.arc(x, yRow(j), r, 0, 2 * Math.PI); g.fill(); }
      }
      g.globalAlpha = 1;
      for (const j of [pk.top, pk.bot]) {
        if (!fin(j)) continue;
        const y = yRow(j);
        g.fillRect(L - 5, y - 1, 5, 2);
        words(g, contactAt(pk, j), L - 7, y + 3.5, L - 8, 10, 'right', C.font);
        ticks.push(y);
      }
    }
    // Where the two humps part, dashed; on a one-hump row the other hump is
    // dimmed, since it plays no part in that line.
    const hm = P.D.sv && P.D.sv.humps;
    const jAt = hm ? cs.indexOf(hm.at) : -1;
    if (jAt > 0) {
      const yAt = Tp + (jAt / nc) * ph;
      if (P.row === 'top' || P.row === 'bottom') {
        g.save();
        g.globalAlpha = 0.66;
        g.fillStyle = C.bg;
        if (P.row === 'top') g.fillRect(L + 1, yAt, pw - 2, Tp + ph - 1 - yAt);
        else g.fillRect(L + 1, Tp + 1, pw - 2, yAt - Tp - 1);
        g.restore();
      }
      g.save();
      g.strokeStyle = C.ink2;
      g.lineWidth = 1;
      g.setLineDash([3, 3]);
      g.beginPath(); g.moveTo(L, yAt); g.lineTo(L + pw, yAt); g.stroke();
      g.restore();
    }
    // The ends of the axis, where a median's number does not sit on them.
    g.fillStyle = C.ink3;
    const clear = (y) => ticks.every((t) => Math.abs(t - y) >= 10);
    if (clear(Tp + 5)) words(g, String(cs[0]), L - 4, Tp + 9, L - 6, 10, 'right', C.font);
    if (clear(Tp + ph - 4)) words(g, String(cs[nc - 1]), L - 4, Tp + ph, L - 6, 10, 'right', C.font);
    handle(g, C, X(at), Tp, Tp + ph + 8, P.cut == null, kind === 'bite' ? 'after ' + at : '', w);
    g.fillStyle = C.ink3;
    words(g, kind === 'bite' ? plural(n, 'event') + ', in the order their ' + (humpRow(P) ? P.row + '-hump ' : '')
      + 'sinks overlap' : plural(n, 'event') + ', sorted by ' + axisWord(P), L + pw / 2, h - 6, pw, 10, 'center', C.font);
    // From a place on the picture back to a line.
    if (kind === 'bite') {
      const K = liveK(P);
      cv.__map = (px) => clamp(Math.round(((px - L) / pw) * n), 1, Math.max(1, K - 1)) - 0.5;
    } else {
      const sx = P._sx || [];
      cv.__map = sx.length < 2 ? null : (px) => {
        const q = clamp(Math.round(((px - L) / pw) * n), 1, sx.length - 1);
        return (sx[q - 1] + sx[q]) / 2;
      };
    }
  }

  /* Up and down on the plot: PC2 for a PCA; for delta, which has none,
     where each event's sink sits (the Bite line's on the same hump or
     humps: its centre of mass), else a spread. */
  function yOf(P) {
    if (P.Y) return P.Y;
    const M = P.M, n = M.x.length;
    const jit = (i) => ((i * 0.6180339887) % 1) - 0.5;
    const by = ((P.D.sv.methods || {})['bite' + (humpRow(P) ? '_' + P.row : '')] || {}).y;
    const where = humpRow(P) ? 'where its ' + P.row + '-hump sink sits (contact)' : 'where its sink sits (contact)';
    if ((baseOf(P.m) === 'pca' || baseOf(P.m) === 'pca_gap') && Array.isArray(M.y) && M.y.some(fin)) {
      P.Y = { ys: M.y, label: M.yaxis || 'PC2', down: false };
    } else if (Array.isArray(by) && by.length === n && by.filter(fin).length >= n / 2) {
      P.Y = { ys: by.map((v, i) => (fin(v) ? +v + jit(i) * 0.7 : null)), down: true,
              label: isBite(P.m) ? where : where + ', spread a little' };
    } else {
      P.Y = { ys: M.x.map((_, i) => jit(i)), label: 'height only spreads the dots', down: false };
    }
    return P.Y;
  }

  function drawScatter(cv, P) {
    const s = kit.sized(cv);
    if (!s) return;
    const { g, w, h } = s;
    const C = pal();
    const M = P.M, xs = M.x, n = xs.length;
    const Y = yOf(P);
    const L = 34, R = 10, Tp = 20, B = 26;
    const pw = w - L - R, ph = h - Tp - B;
    const fx = xs.filter(fin).map(Number);
    if (pw < 20 || ph < 20 || !fx.length) return;
    const cutAt = effCut(P);
    let x0 = Math.min(...fx), x1 = Math.max(...fx);
    if (fin(cutAt)) { x0 = Math.min(x0, cutAt); x1 = Math.max(x1, cutAt); }
    if (!(x1 > x0)) { x0 -= 1; x1 += 1; }
    const px = (x1 - x0) * 0.04;
    x0 -= px; x1 += px;
    const fy = Y.ys.filter(fin).map(Number);
    let y0 = fy.length ? Math.min(...fy) : 0, y1 = fy.length ? Math.max(...fy) : 1;
    if (!(y1 > y0)) { y0 -= 1; y1 += 1; }
    const py = (y1 - y0) * 0.06;
    y0 -= py; y1 += py;
    const X = (v) => L + ((v - x0) / (x1 - x0)) * pw;
    const Yp = (v) => Tp + (Y.down ? (v - y0) / (y1 - y0) : 1 - (v - y0) / (y1 - y0)) * ph;
    const cx = fin(cutAt) ? X(cutAt) : null;
    // Each side of the line, tinted by the class most of it is.
    if (cx != null) {
      let l1 = 0, l2 = 0, r1 = 0, r2 = 0;
      xs.forEach((x, i) => {
        if (!fin(x)) return;
        const t = shownT(P.D, P.types[i]);
        if (x > cutAt) { if (t === 1) r1++; else r2++; } else if (t === 1) l1++; else l2++;
      });
      g.fillStyle = l1 >= l2 ? C.s1 : C.s2;
      g.fillRect(L, Tp, Math.max(0, cx - L), ph);
      g.fillStyle = r1 >= r2 ? C.s1 : C.s2;
      g.fillRect(cx, Tp, Math.max(0, L + pw - cx), ph);
    }
    g.strokeStyle = C.line2;
    g.lineWidth = 1;
    g.strokeRect(L + 0.5, Tp + 0.5, pw - 1, ph - 1);
    const mts = modeTypes(P);
    for (const pass of [4, 3, 2, 1]) {
      g.fillStyle = pass === 1 ? C.ds1 : pass === 2 ? C.ds2 : pass === 3 ? C.ds3 : C.unsure;
      g.strokeStyle = g.fillStyle;
      for (let i = 0; i < n; i++) {
        if (!fin(xs[i]) || shownT(P.D, mts[i]) !== pass) continue;
        const has = fin(Y.ys[i]);
        g.beginPath();
        g.arc(X(+xs[i]), has ? Yp(+Y.ys[i]) : Tp + ph - 4, 3, 0, 6.2832);
        if (has) g.fill(); else g.stroke();          // no sink to place: hollow, along the floor
      }
    }
    g.fillStyle = C.ink3;
    words(g, P.m === 'delta' ? 'sink gap, 0 to 1' : (M.axis || 'x'), L + pw / 2, h - 8, pw, 10, 'center', C.font);
    const none = xs.filter((x) => !fin(x)).length;
    if (none) {
      // Events with no place on this axis are not on the plot: said.
      g.fillStyle = C.ink3;
      words(g, plural(none, 'event') + ' off the plot: no sink ' + (humpRow(P) ? 'in the ' + P.row + ' hump'
        : 'in one hump') + ', on the right side', L + 4, Tp + 11, pw - 8, 9.5, 'left', C.font);
    }
    g.save();
    g.translate(12, Tp + ph / 2);
    g.rotate(-Math.PI / 2);
    words(g, Y.label, 0, 0, ph, 10, 'center', C.font);
    g.restore();
    if (cx != null) {
      handle(g, C, cx, Tp, Tp + ph, P.cut == null,
        cutText(cutAt) + (P.cut != null ? '' : is1D(P.m) ? ' (k-means)' : ' (k-means, not a line)'), w);
    }
    cv.__map = (pxv) => x0 + ((clamp(pxv, L, L + pw) - L) / pw) * (x1 - x0);
  }

  /* The Bite line's cost at every place it could sit (its normalised cut),
     on the raster's own x, so the two line up. */
  function drawCost(cv, P) {
    const s = kit.sized(cv);
    if (!s) return;
    const { g, w, h } = s;
    const C = pal();
    const sw = P.bite.sweep;
    const ks = sw.k || [], ys = sw.ncut || [];
    const n = P.bite.order.length, K = liveK(P);
    const L = 30, R = 8, Tp = 8, B = 24;
    const pw = w - L - R, ph = h - Tp - B;
    const fy = ys.filter(fin).map(Number);
    if (pw < 20 || ph < 10 || !ks.length || !fy.length || !n) return;
    const X = (k) => L + (k / n) * pw;
    let lo = Math.min(...fy), hi = Math.max(...fy);
    if (!(hi > lo)) { lo -= 0.5; hi += 0.5; }
    const Yp = (v) => Tp + (1 - (v - lo) / (hi - lo)) * ph;
    // The ends the default line keeps away from: a side under the floor.
    // Past the last event with a sink, no line can sit at all.
    const fl = fin(sw.floor) ? +sw.floor : 0;
    g.fillStyle = C.chip;
    if (fl > 1) {
      g.fillRect(X(0), Tp, X(fl) - X(0), ph);
      g.fillRect(X(Math.max(0, K - fl)), Tp, X(K) - X(Math.max(0, K - fl)), ph);
    }
    if (n > K) g.fillRect(X(K), Tp, X(n) - X(K), ph);
    g.strokeStyle = C.line2;
    g.lineWidth = 1;
    g.strokeRect(L + 0.5, Tp + 0.5, pw - 1, ph - 1);
    g.strokeStyle = C.ink2;
    g.lineWidth = 1.4;
    g.beginPath();
    let on = false;
    ks.forEach((k, i) => {
      const v = ys[i];
      if (!fin(v)) { on = false; return; }
      if (on) g.lineTo(X(k), Yp(+v)); else { g.moveTo(X(k), Yp(+v)); on = true; }
    });
    g.stroke();
    g.lineWidth = 1;
    const cands = (sw.candidates || []).filter((c) => fin(c.k));
    for (const c of cands) {
      const x = X(c.k), y = Tp + ph + 2;
      g.beginPath(); g.moveTo(x, y); g.lineTo(x - 5, y + 8); g.lineTo(x + 5, y + 8); g.closePath();
      if (c.clears) { g.fillStyle = C.ink2; g.fill(); } else { g.strokeStyle = C.ink2; g.stroke(); }
    }
    const k = kOf(P, effCut(P));
    g.save();
    g.strokeStyle = C.ink;
    g.lineWidth = 1.5;
    g.globalAlpha = P.cut == null ? 0.55 : 1;
    if (P.cut == null) g.setLineDash([4, 3]);
    g.beginPath(); g.moveTo(X(k), Tp); g.lineTo(X(k), Tp + ph); g.stroke();
    g.restore();
    const v = ys[k - 1];
    if (fin(v)) { g.fillStyle = C.ink; g.beginPath(); g.arc(X(k), Yp(+v), 3.5, 0, 6.2832); g.fill(); }
    g.fillStyle = C.ink3;
    words(g, fmt(hi, 2), L - 4, Tp + 9, L - 6, 10, 'right', C.font);
    words(g, fmt(lo, 2), L - 4, Tp + ph, L - 6, 10, 'right', C.font);
    words(g, 'cost of a line at each place, lower is cleaner', L + pw / 2, h - 3, pw, 10, 'center', C.font);
    cv.__map = {
      at: (px) => clamp(Math.round(((px - L) / pw) * n), 1, Math.max(1, K - 1)) - 0.5,
      dipAt: (px) => {
        let best = null, bd = 9;
        for (const c of cands) { const d = Math.abs(X(c.k) - px); if (d < bd) { bd = d; best = c.k; } }
        return best;
      },
    };
  }

  /* ======================================================================
     COMPARE ACROSS SETS
     ====================================================================== */
  const keyOf = (s) => s.id + '@' + s.v;

  /* Every set in the room -- each X-ray Many folder extracted -- at its
     newest version; and the version on show, if it is not its set's newest. */
  function setsOf(rm, folders) {
    const by = new Map();
    for (const v of rm.versions || []) {
      const id = v.folder_id || (folders.find((f) => f.name === v.folder) || {}).id || v.folder || '?';
      const f = folders.find((x) => x.id === id);
      const had = by.get(id);
      if (!had || v.v > had.v) by.set(id, { id, name: (f && f.name) || v.folder || id, v: v.v, at: v.at, by: v.by, n: v.n });
    }
    const out = Array.from(by.values());
    if (S.folder && S.version != null) {
      const mine = out.find((x) => x.id === S.folder);
      const vv = (rm.versions || []).find((x) => x.v === S.version) || {};
      if (!mine) {
        out.push({ id: S.folder, name: ((S.pay || {}).source || {}).folder_name || S.folder, v: S.version,
                   at: vv.at, by: vv.by, n: vv.n, onShow: true });
      } else if (mine.v !== S.version) {
        out.push({ id: S.folder, name: mine.name, v: S.version, at: vv.at, by: vv.by, n: vv.n, onShow: true });
      } else {
        mine.onShow = true;
      }
    }
    return out.sort((a, b) => b.v - a.v);
  }

  async function across(r0) {
    if (!r0) return;
    const gid = r0.gid;
    const r = kit.recOf(gid) || r0;
    const o = overlay('across', gid, r.session_label + ' · ' + (r.group || '?') + ' · in two sets',
      'This recording as two sets have it, side by side: each set’s own split, calls and classes, drawn on one colour '
      + 'scale and one depth-profile axis so the two compare by eye.');
    const A = { o, r, gid, label: r.session_label, aid: null, sets: [], cols: [], cache: {} };
    o.A = A;
    o.body.appendChild(el('p', { class: 'muted erc-wait', text: 'Opening the sets.' }));
    let idx = null;
    try { idx = await kit.api('/api/extraction'); } catch (e) { idx = null; }
    if (!o.alive) return;
    const rooms = (idx && idx.rooms) || S.rooms || [];
    const folders = (idx && idx.folders) || S.folders || [];
    const rm = rooms.find((x) => x.room === S.room) || S.art || {};
    A.aid = rm.artifact_id || (S.art && S.art.artifact_id);
    A.sets = setsOf(rm, folders);
    o.body.innerHTML = '';
    if (!A.sets.length || !A.aid) {
      o.body.appendChild(el('p', { class: 'muted', text: 'Nothing has been extracted into this room yet.' }));
      return;
    }
    const left = A.sets.find((x) => x.onShow) || A.sets[0];
    const right = A.sets.filter((x) => x.id !== left.id).sort((a, b) => b.v - a.v)[0] || null;
    if (!right) {
      o.body.appendChild(el('p', { class: 'notice erc-one', text: 'Only one set is in this room so far: extract another '
        + 'X-ray Many folder to set this recording beside it.' }));
    }
    const grid = el('div', { class: 'erc-cols' });
    o.body.appendChild(grid);
    A.diff = el('p', { class: 'erc-diff small', 'aria-live': 'polite' });
    o.body.appendChild(A.diff);
    [left, right || left].forEach((s, i) => {
      const col = { i, set: s, data: null, err: null, loading: true, gen: 0, csd: [], prof: null,
                    node: el('section', { class: 'erc-col', 'data-col': String(i) }) };
      A.cols.push(col);
      grid.appendChild(col.node);
    });
    o.draws.push(() => drawAcross(A));
    await Promise.all(A.cols.map((col) => fill(A, col)));
  }

  /* A set's copy of the recording, with that set's own swaps and calls. The
     set on show is the room's own; another is asked once. */
  function setData(A, s) {
    if (s.id === S.folder && s.v === S.version && S.pay) {
      return Promise.resolve({ rec: kit.recOf(A.gid), flips: S.flips || {}, seps: S.seps || {} });
    }
    const k = String(s.v);
    if (!A.cache[k]) {
      A.cache[k] = kit.api('/api/extraction/' + encodeURIComponent(A.aid) + '?version=' + encodeURIComponent(s.v))
        .then((got) => ({ rec: (((got.payload || {}).recordings) || []).find((x) => x.gid === A.gid) || null,
                          flips: got.flips || {}, seps: got.seps || {} }))
        .catch((e) => { delete A.cache[k]; throw e; });
    }
    return A.cache[k];
  }

  async function fill(A, col) {
    const mine = ++col.gen;
    col.loading = true;
    col.err = null;
    col.data = null;
    renderCol(A, col);
    putDiff(A);
    try {
      const d = await setData(A, col.set);
      if (mine !== col.gen || !A.o.alive) return;
      col.data = d;
    } catch (e) {
      if (mine !== col.gen || !A.o.alive) return;
      col.err = e.message;
    }
    col.loading = false;
    renderCol(A, col);
    putDiff(A);
    requestAnimationFrame(() => drawAcross(A));
  }

  function splitSays(rec) {
    const sp = rec.split;
    if (sp && sp.method) {
      const line = sp.cut == null ? 'its default line'
        : isBite(sp.method) ? 'a line after ' + Math.ceil(+sp.cut - 1e-9) + ' events' : 'a line at ' + cutText(sp.cut);
      return 'Split: ' + (MNAME[sp.method] || sp.words || sp.method) + ', ' + line + (sp.by ? ' · by ' + sp.by : '')
        + (sp.error ? ' · not applied: ' + sp.error : '');
    }
    return rec.direct ? 'Split: Bite line, its default line' : 'Split: X-ray’s own';
  }

  /* One column, built again in place: only that column. */
  function renderCol(A, col) {
    const s = col.set;
    const node = col.node;
    node.innerHTML = '';
    col.csd = [];
    col.prof = null;
    const pick = kit.seg(A.sets.map((x) => [keyOf(x), x.name + ' · v' + x.v + (x.onShow ? ' · on show' : ''),
      (x.n != null ? plural(x.n, 'recording') : '') + (x.at ? ', extracted ' + new Date(x.at).toLocaleString() : '')]),
    keyOf(s), (key) => {
      const ns = A.sets.find((x) => keyOf(x) === key);
      if (ns && keyOf(ns) !== keyOf(col.set)) { col.set = ns; fill(A, col); }
    }, 'erc-pick-' + col.i);
    pick.classList.add('erc-pick');
    node.appendChild(el('div', { class: 'erc-colhead' }, [el('span', { class: 'lab', text: col.i ? 'Against' : 'Set' }), pick]));
    node.appendChild(el('h3', { text: '‘' + s.name + '’ · v' + s.v }));
    const when = [s.at ? 'extracted ' + new Date(s.at).toLocaleString() : null, s.by ? 'by ' + s.by : null,
                  s.n != null ? plural(s.n, 'recording') : null, s.onShow ? 'the set on show' : null].filter(Boolean).join(' · ');
    if (when) node.appendChild(el('p', { class: 'muted small', text: when.charAt(0).toUpperCase() + when.slice(1) + '.' }));
    if (col.loading) { node.appendChild(el('p', { class: 'muted small', text: 'Opening ‘' + s.name + '’ v' + s.v + '.' })); return; }
    if (col.err) { node.appendChild(el('p', { class: 'err small', text: 'Not opened: ' + col.err })); return; }
    const rec = col.data && col.data.rec;
    if (!rec) {
      node.appendChild(el('p', { class: 'erc-missing', text: '‘' + s.name + '’ v' + s.v + ' does not have ' + A.label + '.' }));
      return;
    }
    const flips = col.data.flips || {};
    const sep = withS({ seps: col.data.seps || {} }, () => kit.sepOf(rec));
    const cls = withS({ flips }, () => kit.shownClasses(rec));
    const flip = !!(flips[rec.gid] && flips[rec.gid].flip);
    const c1 = cls.find((c) => c.shown === 1), c2 = cls.find((c) => c.shown === 2);
    node.appendChild(el('div', { class: 'erc-chips' }, [
      el('span', { class: 'chip erc-events', text: plural(rec.n, 'event') }),
      el('span', { class: 'chip erc-split', text: splitSays(rec) }),
      el('span', { class: 'chip erc-sep ' + (sep.verdict || ''),
        text: (SEP[sep.verdict] || sep.verdict || 'no call') + (sep.byHand ? ' · by hand' : '') }),
      flip ? el('span', { class: 'chip swapped', text: 'DS1 ↔ DS2 swapped by hand' }) : null,
    ]));
    node.appendChild(el('p', { class: 'erc-n' }, [el('b', { class: 'erc-ds1', text: 'DS1 ' + (c1 ? c1.n : 0) }), T(' · '),
      el('b', { class: 'erc-ds2', text: 'DS2 ' + (c2 ? c2.n : 0) })]));
    col.csd = [el('canvas', { class: 'erc-cv erc-csd' }), el('canvas', { class: 'erc-cv erc-csd' })];
    node.appendChild(el('div', { class: 'erc-pics' }, [c1, c2].map((c, k) => el('div', { class: 'pic' }, [
      el('div', { class: 'cap' }, [el('b', { class: k ? 'erc-ds2' : 'erc-ds1', text: 'DS' + (k + 1) }),
        el('span', { text: c ? plural(c.n, 'event') : 'none' })]), col.csd[k]]))));
    col.prof = el('canvas', { class: 'erc-cv erc-prof' });
    node.appendChild(el('div', { class: 'pic' }, [el('div', { class: 'cap' }, [
      el('span', { text: 'Depth profile at the box’s time, mean ± SEM' })]), col.prof]));
    const sk = (c) => (c && c.sink ? c.name + ' sink ' + sgn(c.sink.value) + ' at CSC' + (c.sink.csc == null ? '—' : c.sink.csc) : null);
    node.appendChild(el('p', { class: 'small num erc-sinks', text: [sk(c1), sk(c2)].filter(Boolean).join(' · ') }));
  }

  /* Both columns on one scale: the CSD colour runs to the larger of the two
     records' own 99th percentiles, the profiles' axis spans both. The kit's
     pictures read the scale from S, so it is lent to them for the draw. */
  function drawAcross(A) {
    if (!A.o.alive) return;
    const recs = A.cols.map((c) => c.data && c.data.rec).filter(Boolean);
    if (!recs.length) return;
    let big = recs[0], top = -1;
    for (const r of recs) { const p = kit.p99([r]); if (p > top) { top = p; big = r; } }
    const key = A.gid + '|' + A.cols.map((c) => (c.data && c.data.rec ? c.set.v : '-')).join('|');
    for (const col of A.cols) {
      const rec = col.data && col.data.rec;
      if (!rec || !col.prof || !col.prof.isConnected) continue;
      const flips = col.data.flips || {};
      withS({ flips, scale: 'same', pay: { recordings: [big] }, version: 'erc-csd|' + key }, () => {
        const cls = kit.shownClasses(rec);
        [1, 2].forEach((sh, k) => {
          const c = cls.find((x) => x.shown === sh);
          if (c && col.csd[k]) kit.drawCsd(col.csd[k], rec, c);
        });
      });
      withS({ flips, scale: 'same', pay: { recordings: recs }, version: 'erc-prof|' + key }, () => kit.drawProfile(col.prof, rec));
    }
  }

  /* The differences, in a line under the two. */
  function putDiff(A) {
    const box = A.diff;
    if (!box) return;
    const [a, b] = A.cols;
    box.innerHTML = '';
    if (!a || !b || a.loading || b.loading) return;
    if (keyOf(a.set) === keyOf(b.set)) {
      box.appendChild(T('Both sides show the same set: pick another on either side.'));
      return;
    }
    const ra = a.data && a.data.rec, rb = b.data && b.data.rec;
    if (!ra || !rb) {
      const gone = [!ra ? a : null, !rb ? b : null].filter(Boolean).map((c) => '‘' + c.set.name + '’ v' + c.set.v);
      box.appendChild(T('Nothing to set side by side: ' + gone.join(' and ') + (gone.length === 1 ? ' does' : ' do')
        + ' not have this recording.'));
      return;
    }
    const ca = withS({ flips: a.data.flips || {} }, () => kit.shownClasses(ra));
    const cb = withS({ flips: b.data.flips || {} }, () => kit.shownClasses(rb));
    const one = (cls, sh) => cls.find((c) => c.shown === sh) || {};
    const na = '‘' + a.set.name + '’', nb = '‘' + b.set.name + '’';
    const d = (rb.n || 0) - (ra.n || 0);
    const kids = [T('The differences, ' + na + ' then ' + nb + '. Events: ' + ra.n + ' and ' + rb.n
      + (d ? ' (' + (d > 0 ? '+' : '−') + Math.abs(d) + ')' : ', the same'))];
    for (const sh of [1, 2]) {
      kids.push(T(' · '), el('b', { class: 'erc-ds' + sh, text: 'DS' + sh }),
        T(': ' + (one(ca, sh).n || 0) + ' and ' + (one(cb, sh).n || 0) + ' events'));
    }
    for (const sh of [1, 2]) {
      kids.push(T(' · '), el('b', { class: 'erc-ds' + sh, text: 'DS' + sh + ' sink' }),
        T(' ' + sgn((one(ca, sh).sink || {}).value) + ' and ' + sgn((one(cb, sh).sink || {}).value)));
    }
    const unit = (one(ca, 1).sink || {}).unit || (one(cb, 1).sink || {}).unit;
    kids.push(T((unit ? ' (sinks in ' + unit + ')' : '') + '.'));
    for (const k of kids) box.appendChild(k);
  }

  /* ---------- registered with the room ---------- */
  room.ext = room.ext || {};
  room.ext.compare = { splits, across, close: closeCur, _now: () => cur };
})();
