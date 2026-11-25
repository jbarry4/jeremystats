/* ==========================================================================
   seahorse_schem.js -- the Seahorse schematics (BARRY.shSchem).

   Three drawings, each an SVG whose parts carry data-region / data-cell /
   data-conn / data-layer so the tab can light, hover and select them in
   step with the 3D and slice views:

     circuit(h)        the hippocampal formation, region to region. Long
                       edges are routed around the boxes, labels are placed
                       where they hit nothing.
     dentate(h)        the dentate (and CA3) laid out by layer, as in the
                       lab's P1 deck: every connection ends in the layer
                       where it synapses.
     cell(h, type)     one cell type: what feeds it (left, by the layer it
                       lands in) and where it leads (right).

   apply(svg, state)   classes for focus / hover / selection, the "you are
                       here" pin, the trail, and DS sink/source overlays.
   follow(svg, key)    eases the viewBox toward one part (the rail follows
                       you around).

   h: {kb, cellOf, regionOf, connOf, lamOf, verdictOf, select(sel), hover(sel|null), notes(type, key) -> n}
   ========================================================================== */
'use strict';

BARRY.shSchem = (function () {
  const NS = 'http://www.w3.org/2000/svg';
  function svg(tag, attrs, kids) {
    const n = document.createElementNS(NS, tag);
    for (const k in (attrs || {})) {
      const v = attrs[k];
      if (v == null || v === false) continue;
      if (k === 'text') n.textContent = v;
      else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    (kids || []).forEach((c) => c && n.appendChild(c));
    return n;
  }
  function defs() {
    const exc = 'color-mix(in srgb, var(--text) 55%, transparent)';
    return svg('defs', {}, [['exc', exc, 6], ['pp', exc, 3.4], ['inh', 'var(--err)', 6], ['lit', 'var(--accent)', 6]].map(([k, c, mw]) =>
      svg('marker', { id: 'shm-' + k, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: mw, markerHeight: mw, orient: 'auto-start-reverse' },
        [k === 'inh' ? svg('rect', { x: 3, y: 1, width: 4, height: 8, style: 'fill:' + c })
                     : svg('path', { d: 'M0,0 L10,5 L0,10 z', style: 'fill:' + c })])));
  }
  /* a part that hovers and selects */
  function part(h, sel, attrs, kids) {
    const g = svg('g', attrs, kids);
    g.addEventListener('click', (e) => { e.stopPropagation(); h.select(sel); });
    g.addEventListener('pointerenter', () => h.hover(sel));
    g.addEventListener('pointerleave', () => h.hover(null));
    // the keyboard reaches every part too: Tab to it (it lights like a hover), Enter or Space to select
    g.setAttribute('tabindex', '0');
    g.setAttribute('role', 'button');
    let kb = false;
    g.addEventListener('focus', () => {
      if (!g.getAttribute('aria-label')) g.setAttribute('aria-label', (g.textContent || sel.key).replace(/\s+/g, ' ').trim());
      kb = g.matches(':focus-visible');           // a click focuses too: only the keyboard lights it
      if (kb) h.hover(sel);
    });
    g.addEventListener('blur', () => { if (kb) h.hover(null); kb = false; });
    g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); h.select(sel); } });
    return g;
  }
  const verdictColor = (s) => ({ supported: 'var(--ok)', consistent: 'var(--accent)', weak: 'var(--warn)', 'not seen': 'var(--err)', error: 'var(--err)' }[s] || 'var(--text-3)');

  /* ----------------------------------------------------------------------
     The circuit
     ---------------------------------------------------------------------- */
  const POS = {
    ctx: [500, 44, 820], per: [170, 140], por: [390, 140],
    lec2: [122, 262], mec2: [122, 336], ec3: [122, 410], ec5: [122, 528],
    dg: [430, 300], ca3: [655, 300], ca2: [845, 212], ca1: [865, 418],
    sub: [655, 528], prepar: [430, 612], subc: [865, 612],
  };
  const BW = 188, BH = 52;
  const rect = (k) => { const p = POS[k]; const w = p[2] || BW; return { x: p[0] - w / 2, y: p[1] - BH / 2, w, h: BH, cx: p[0], cy: p[1] }; };
  /* Hand-routed edges (waypoints between the two boxes) for the ones that
     would otherwise cut through a box. */
  const ROUTE = {
    ec5_ctx: [[14, 528], [14, 44]],
    pp_ca3: [[262, 336], [300, 226], [600, 226]],
    pp_ca2: [[262, 336], [300, 186], [770, 186]],
    ta: [[262, 410], [330, 456], [780, 456]],
    ec3_sub: [[262, 410], [330, 470], [560, 500]],
    ca1_ec5: [[865, 470], [800, 570], [270, 570]],
    por_mec: [[390, 200], [262, 300]],
    pre_mec: [[300, 612], [262, 440]],
    back: [[600, 352], [490, 352]],
  };
  // drawn in the dentate view instead (same pair of boxes as a stronger edge)
  const CIRCUIT_SKIP = new Set(['pp_pv']);
  /* the names the circuit uses when it is drawn small (the rail's map): the hover card has the full name */
  const SHORT = { ctx: 'Neocortex', per: 'Perirhinal', por: 'Postrhinal', lec2: 'LEC II', mec2: 'MEC II', ec3: 'EC III', ec5: 'EC V–VI',
    dg: 'DG', ca3: 'CA3', ca2: 'CA2', ca1: 'CA1', sub: 'Subiculum', prepar: 'Pre/Para', subc: 'Fornix' };
  const LABELED = { lpp: 'lateral perforant path', mpp: 'medial perforant path', mf_ca3: 'mossy fibers', sc: 'Schaffer collaterals',
    ta: 'temporoammonic', rc: 'recurrent collaterals', sub_ec5: 'loop closes in deep EC', ec5_ctx: 'back to neocortex',
    sub_subc: 'fimbria-fornix', pp_ca3: 'EC II to CA3', back: 'back-projection' };

  function regionEnd(h, key) {
    if (POS[key]) return key;
    const c = h.cellOf(key);
    return c && POS[c.region] ? c.region : null;
  }
  function anchor(r, toward) {
    const dx = toward[0] - r.cx, dy = toward[1] - r.cy;
    if (!dx && !dy) return [r.cx, r.cy];
    const s = Math.min((r.w / 2) / Math.abs(dx || 1e-6), (r.h / 2) / Math.abs(dy || 1e-6));
    return [r.cx + dx * s, r.cy + dy * s];
  }
  /* a smooth path through points (rounded corners) */
  function smooth(pts) {
    if (pts.length === 2) return 'M' + pts[0].join(',') + ' L' + pts[1].join(',');
    let d = 'M' + pts[0].join(',');
    for (let i = 1; i < pts.length - 1; i++) {
      const a = pts[i - 1], b = pts[i], c = pts[i + 1];
      const r = Math.min(26, Math.hypot(b[0] - a[0], b[1] - a[1]) / 2, Math.hypot(c[0] - b[0], c[1] - b[1]) / 2);
      const u = norm([a[0] - b[0], a[1] - b[1]]), v = norm([c[0] - b[0], c[1] - b[1]]);
      const p1 = [b[0] + u[0] * r, b[1] + u[1] * r], p2 = [b[0] + v[0] * r, b[1] + v[1] * r];
      d += ' L' + p1.join(',') + ' Q' + b.join(',') + ' ' + p2.join(',');
    }
    return d + ' L' + pts[pts.length - 1].join(',');
  }
  const norm = (v) => { const l = Math.hypot(v[0], v[1]) || 1; return [v[0] / l, v[1] / l]; };
  function polyPoint(pts, t) {
    const seg = [];
    let L = 0;
    for (let i = 1; i < pts.length; i++) { const l = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); seg.push(l); L += l; }
    let s = t * L;
    for (let i = 1; i < pts.length; i++) {
      if (s <= seg[i - 1]) { const f = s / seg[i - 1]; return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f, Math.atan2(pts[i][1] - pts[i - 1][1], pts[i][0] - pts[i - 1][0])]; }
      s -= seg[i - 1];
    }
    const n = pts.length;
    return [pts[n - 1][0], pts[n - 1][1], 0];
  }
  const overlaps = (a, b) => !(a.x + a.w < b.x || b.x + b.w < a.x || a.y + a.h < b.y || b.y + b.h < a.y);

  function circuit(h) {
    const kb = h.kb;
    // a box as wide as its name needs at the rail's type size (never cut a name)
    for (const r of kb.regions) if (POS[r.key]) POS[r.key][2] = Math.max(POS[r.key][2] || BW, Math.ceil(r.label.length * 11.2 + 28));
    const out = svg('svg', { class: 'sh-svg', viewBox: '0 0 1000 660', preserveAspectRatio: 'xMidYMid meet', role: 'img',
      'aria-label': 'Circuit of the hippocampal formation' }, [defs()]);
    out.classList.add('sh-circuit');
    out._full = [0, 0, 1000, 660];
    out.appendChild(svg('rect', { class: 'ec-box', x: 18, y: 230, width: 210, height: 330, rx: 16 }));
    out.appendChild(svg('text', { class: 'ec-label', x: 122, y: 582, 'text-anchor': 'middle', text: 'ENTORHINAL CORTEX' }));
    const edges = svg('g', {}), boxes = svg('g', {}), labels = svg('g', { style: 'pointer-events:none' });
    out.append(edges, boxes, labels);
    const boxRects = Object.keys(POS).map((k) => Object.assign({ key: k }, rect(k)));
    const placed = [];
    const pairN = {};
    for (const c of kb.connections) {
      if (c.hidden || CIRCUIT_SKIP.has(c.key)) continue;
      const A = regionEnd(h, c.from), B = regionEnd(h, c.to);
      if (!A || !B) continue;
      if (A === B && c.key !== 'rc') continue;
      let pts, d, mid;
      if (A === B) {
        const r = rect(A);
        const x = r.x + r.w * 0.66, y = r.y;
        pts = null;
        d = `M${x - 18},${y} C${x - 42},${y - 64} ${x + 54},${y - 64} ${x + 22},${y - 2}`;
        mid = [x + 4, y - 50, 0];
      } else {
        const ra = rect(A), rb = rect(B);
        const way = ROUTE[c.key];
        if (way) {
          const p0 = anchor(ra, way[0]), p1 = anchor(rb, way[way.length - 1]);
          pts = [p0].concat(way).concat([p1]);
        } else {
          const pk = [A, B].sort().join('|');
          pairN[pk] = (pairN[pk] || 0) + 1;
          const off = (pairN[pk] - 1) * 12;
          const p0 = anchor(ra, [rb.cx, rb.cy]), p1 = anchor(rb, [ra.cx, ra.cy]);
          const dv = norm([p1[1] - p0[1], -(p1[0] - p0[0])]);
          pts = [[p0[0] + dv[0] * off, p0[1] + dv[1] * off], [p1[0] + dv[0] * off, p1[1] + dv[1] * off]];
        }
        d = smooth(pts);
        mid = polyPoint(pts, 0.5);
      }
      const v = h.verdictOf(c.key);
      // the two perforant paths are the lab's inputs: bold, in their cells' colours
      const pp = c.key === 'lpp' || c.key === 'mpp';
      const ppCol = pp ? (h.cellOf(c.key === 'lpp' ? 'fan' : 'stel') || {}).color : null;
      const g = part(h, { type: 'conn', key: c.key }, { class: 'edge ' + c.sign + (c.dash ? ' dash' : '') + (pp ? ' pp' : ''), 'data-conn': c.key }, [
        svg('path', { class: 'hit', d }),
        svg('path', { class: 'ln', d, 'marker-end': 'url(#shm-' + (pp ? 'pp' : c.sign) + ')', style: pp ? 'stroke:' + ppCol : null }),
        svg('circle', { class: 'badge', cx: mid[0], cy: mid[1], r: 4.2, style: 'fill:' + verdictColor(v.status) }),
        svg('title', { text: c.label + ' (' + (v.status || 'cited') + ')' }),
      ]);
      g._pts = pts;
      edges.appendChild(g);
      if (LABELED[c.key]) {
        // try spots along the edge, either side, until one is clear
        const text = LABELED[c.key];
        const w = text.length * 6.1 + 8, hh = 16;
        let best = null;
        const tries = pts ? [0.5, 0.35, 0.65, 0.25, 0.75, 0.42, 0.58] : [0.5];
        for (const t of tries) {
          const p = pts ? polyPoint(pts, t) : mid;
          for (const s of [-1, 1]) {
            const ox = pts ? -Math.sin(p[2]) * 14 * s : 0, oy = pts ? Math.cos(p[2]) * 14 * s : -10;
            const r = { x: p[0] + ox - w / 2, y: p[1] + oy - hh / 2, w, h: hh };
            if (r.x < 4 || r.x + r.w > 996 || r.y < 4 || r.y + r.h > 656) continue;
            if (boxRects.some((b) => overlaps(r, b)) || placed.some((q) => overlaps(r, q))) continue;
            best = r; break;
          }
          if (best) break;
        }
        if (best) {
          placed.push(best);
          labels.appendChild(svg('g', { class: 'edge-label', 'data-conn': c.key }, [
            svg('text', { class: 'elabel', x: best.x + best.w / 2, y: best.y + 12, 'text-anchor': 'middle', text }),
          ]));
        }
      }
    }
    for (const r of kb.regions) {
      if (!POS[r.key]) continue;
      const b = rect(r.key);
      const n = h.notes ? h.notes('region', r.key) : 0;
      const rc = h.regionColor ? h.regionColor(r.key) : null;
      boxes.appendChild(part(h, { type: 'region', key: r.key }, { class: 'box', 'data-region': r.key, style: rc ? '--rc:' + rc : null }, [
        svg('rect', { class: 'body', x: b.x, y: b.y, width: b.w, height: b.h, rx: 11 }),
        svg('rect', { class: 'bar', x: b.x + 7, y: b.y + 10, width: 4, height: b.h - 20, rx: 2 }),
        svg('text', { x: b.cx, y: b.cy - 3, 'text-anchor': 'middle', class: 'bt full', text: r.label }),
        svg('text', { x: b.cx + 4, y: b.cy + 5, 'text-anchor': 'middle', class: 'bt short', text: SHORT[r.key] || r.label }),
        svg('text', { class: 'sub', x: b.cx, y: b.cy + 15, 'text-anchor': 'middle', text: r.sub }),
        n ? svg('g', { class: 'note-badge' }, [svg('circle', { cx: b.x + b.w - 8, cy: b.y + 8, r: 7 }), svg('text', { x: b.x + b.w - 8, y: b.y + 11.5, 'text-anchor': 'middle', text: String(n) })]) : null,
      ]));
    }
    out.addEventListener('click', () => h.select(null));
    out._anchor = (sel) => {
      if (!sel) return null;
      const k = sel.type === 'region' ? sel.key : sel.type === 'cell' ? (h.cellOf(sel.key) || {}).region : sel.type === 'lamina' ? h.regionOfLayer(sel.key) : null;
      if (k && POS[k]) { const r = rect(k); return [r.cx, r.cy, r.w, r.h]; }
      return null;
    };
    return out;
  }

  /* ----------------------------------------------------------------------
     The hippocampus by layer: a textbook plate. The dentate's blades curve
     around the hilus as in a coronal section; the CA strip leaves the
     hilus (CA3c) and runs out through CA3, CA2 and CA1 to the subiculum,
     each field with its strata. Every connection ends in the layer where
     it synapses. Entorhinal inputs on the left.
     ---------------------------------------------------------------------- */
  const DG = { cx: 300, cy: 356, rings: [['hil', 0, 62], ['gcl', 62, 84], ['iml', 84, 106], ['mml', 106, 132], ['oml', 132, 158]], a0: 58, a1: 302 };
  // CA strip bands (y ranges) and fields (x ranges)
  const STRATA = { so: [298, 320], sp: [320, 340], slu: [340, 352], sr: [352, 390], slm: [390, 412] };
  const FIELDS = [['ca3', 340, 660, 'CA3'], ['ca2', 660, 716, 'CA2'], ['ca1', 716, 990, 'CA1'], ['sub', 990, 1112, 'Subiculum']];
  const rad = (d) => d * Math.PI / 180;
  const P = (r, th) => [DG.cx + r * Math.cos(rad(th)), DG.cy - r * Math.sin(rad(th))];
  function sector(r0, r1, t0, t1) {
    const a = P(r1, t0), b = P(r1, t1), c = P(r0, t1), d = P(r0, t0);
    const large = Math.abs(t1 - t0) > 180 ? 1 : 0;
    if (r0 <= 0) return `M${DG.cx},${DG.cy} L${a} A${r1},${r1} 0 ${large} 0 ${b} Z`;
    return `M${a} A${r1},${r1} 0 ${large} 0 ${b} L${c} A${r0},${r0} 0 ${large} 1 ${d} Z`;
  }
  function dentate(h) {
    const kb = h.kb, LC = kb.lamina_colors;
    const out = svg('svg', { class: 'sh-svg sh-plate', viewBox: '0 0 1200 680', preserveAspectRatio: 'xMidYMid meet', role: 'img',
      'aria-label': 'The hippocampus by layer: dentate gyrus, CA3, CA2, CA1 and subiculum' }, [defs()]);
    out._full = [0, 0, 1200, 680];
    const col = (k) => (h.cellOf(k) || {}).color || '#888';
    const L = {};      // anchor points per layer key, for _anchor and edges
    const bands = svg('g', { class: 'plate-bands' });
    out.appendChild(bands);
    // the layer names go on top of everything (added last), each with a halo in its own band's
    // color, so a fibre or a cell passing under a name never makes it hard to read
    const bandLabels = svg('g', { class: 'band-labels', style: 'pointer-events:none' });
    const band = (key, d, labelAt, label) => {
      bands.appendChild(part(h, { type: 'lamina', key }, { class: 'band', 'data-layer': key }, [
        svg('path', { d, style: 'fill:' + (LC[key] || '#999') }),
      ]));
      if (label) bandLabels.appendChild(svg('text', { class: 'blabel', 'data-layer': key, x: labelAt[0], y: labelAt[1] + 4, 'text-anchor': 'middle', text: label, style: 'stroke:' + (LC[key] || '#999') }));
    };
    // the dentate: hilus, then each ring as an upper (1) and lower (2) blade
    band('hil', sector(0, 62, DG.a0, DG.a1), P(40, 140), 'HIL');
    L.hil = P(34, 180);
    for (const [k, r0, r1] of DG.rings.slice(1)) {
      const rm = (r0 + r1) / 2;
      band(k + '1', sector(r0, r1, DG.a0, 180), P(rm, k === 'gcl' ? 160 : 65), k.toUpperCase() + '1');
      band(k + '2', sector(r0, r1, 180, DG.a1), P(rm, 295), k.toUpperCase() + '2');
      L[k + '1'] = P(rm, 150); L[k + '2'] = P(rm, 210);
    }
    // the CA strip, field by field
    for (const [f, x0, x1] of FIELDS) {
      if (f === 'sub') {
        band('sub', `M${x0},${STRATA.so[0]} L${x1 - 20},${STRATA.so[0]} Q${x1},${STRATA.so[0]} ${x1},${STRATA.so[0] + 20} L${x1},${STRATA.slm[1] - 20} Q${x1},${STRATA.slm[1]} ${x1 - 20},${STRATA.slm[1]} L${x0},${STRATA.slm[1]} Z`,
          [(x0 + x1) / 2, (STRATA.so[0] + STRATA.slm[1]) / 2], 'SUB');
        L.sub = [(x0 + x1) / 2, (STRATA.so[0] + STRATA.slm[1]) / 2];
        continue;
      }
      for (const [s, [y0, y1]] of Object.entries(STRATA)) {
        if (s === 'slu' && f !== 'ca3') continue;
        const ys0 = s === 'sr' && f !== 'ca3' ? STRATA.slu[0] : y0;
        const key = f + s;
        // CA3c starts inside the hilus: round its end
        const left = f === 'ca3' ? `M${x0 + 14},${ys0} L${x1},${ys0} L${x1},${y1} L${x0 + 14},${y1} Q${x0 - 4},${(ys0 + y1) / 2} ${x0 + 14},${ys0} Z` : `M${x0},${ys0} L${x1},${ys0} L${x1},${y1} L${x0},${y1} Z`;
        band(key, left, null, null);
        L[key] = [(x0 + x1) / 2, (ys0 + y1) / 2];
      }
    }
    // strata names once, at the right end of CA1 (and lucidum in CA3)
    const names = svg('g', { style: 'pointer-events:none' });
    out.appendChild(names);
    for (const [s, [y0, y1]] of Object.entries(STRATA)) {
      if (s === 'slu') continue;
      names.appendChild(svg('text', { class: 'blabel', x: 984, y: ((s === 'sr' ? STRATA.slu[0] : y0) + y1) / 2 + 4, 'text-anchor': 'end', text: s }));
    }
    names.appendChild(svg('text', { class: 'blabel', x: 654, y: (STRATA.slu[0] + STRATA.slu[1]) / 2 + 4, 'text-anchor': 'end', text: 'slu' }));
    // field names above the strip, clickable as regions
    for (const [f, x0, x1, label] of FIELDS) {
      out.appendChild(part(h, { type: 'region', key: f === 'sub' ? 'sub' : f }, { class: 'box fieldname', 'data-region': f === 'sub' ? 'sub' : f }, [
        svg('text', { class: 'bt', x: (x0 + x1) / 2, y: STRATA.so[0] - 14, 'text-anchor': 'middle', text: label })]));
    }
    out.appendChild(part(h, { type: 'region', key: 'dg' }, { class: 'box fieldname', 'data-region': 'dg' }, [
      svg('text', { class: 'bt', x: DG.cx - 20, y: DG.cy - 172, 'text-anchor': 'middle', text: 'Dentate gyrus' })]));
    out.appendChild(svg('text', { class: 'sub', x: 600, y: 664, 'text-anchor': 'middle', text: 'upper (suprapyramidal) blade = 1, lower (infrapyramidal) blade = 2' }));

    const conns = svg('g', {}), cells = svg('g', {}), tags = svg('g', { style: 'pointer-events:none' });
    out.append(conns, cells, tags);
    const glyph = (key, kids) => part(h, { type: 'cell', key }, { class: 'glyph', 'data-cell': key }, kids);
    const conn = (key, d, style, cls) => part(h, { type: 'conn', key }, { class: 'edge ' + ((h.connOf(key) || {}).sign || 'exc') + (cls ? ' ' + cls : ''), 'data-conn': key }, [
      svg('path', { class: 'hit', d }), svg('path', { class: 'ln', d, style: style || '', 'marker-end': 'url(#shm-' + (cls === 'pp' ? 'pp' : ((h.connOf(key) || {}).sign || 'exc')) + ')' })]);
    const tag = (x, y, text, anchor) => tags.appendChild(svg('text', { class: 'ctag', x, y, 'text-anchor': anchor || 'middle', text }));
    const arcPath = (r, t0, t1) => { const a = P(r, t0), b = P(r, t1); return `M${a} A${r},${r} 0 0 ${t1 > t0 ? 0 : 1} ${b}`; };
    const pyr = (x, y, c, s) => `M${x - 9 * s},${y - 7 * s} L${x + 9 * s},${y - 7 * s} L${x},${y + 11 * s} Z`;   // apex toward the apical dendrite (down)

    // entorhinal inputs
    const ecBox = (key, y, title, sub, color) => glyph(key, [
      svg('rect', { x: 18, y: y - 22, width: 150, height: 44, rx: 11, class: 'ecbox', style: 'stroke:' + color }),
      svg('text', { class: 'bt sm', x: 93, y: y - 3, 'text-anchor': 'middle', text: title }),
      svg('text', { class: 'sub', x: 93, y: y + 13, 'text-anchor': 'middle', text: sub })]);
    cells.appendChild(ecBox('fan', 70, 'LEC II', 'fan cells', col('fan')));
    cells.appendChild(ecBox('stel', 136, 'MEC II', 'stellate cells', col('stel')));
    out.appendChild(part(h, { type: 'region', key: 'ec3' }, { class: 'box', 'data-region': 'ec3' }, [
      svg('rect', { class: 'body', x: 18, y: 560, width: 150, height: 44, rx: 11 }), svg('text', { class: 'bt sm', x: 93, y: 579, 'text-anchor': 'middle', text: 'EC III' }),
      svg('text', { class: 'sub', x: 93, y: 595, 'text-anchor': 'middle', text: 'pyramidal cells' })]));
    out.appendChild(part(h, { type: 'region', key: 'ec5' }, { class: 'box', 'data-region': 'ec5' }, [
      svg('rect', { class: 'body', x: 18, y: 616, width: 150, height: 44, rx: 11 }), svg('text', { class: 'bt sm', x: 93, y: 635, 'text-anchor': 'middle', text: 'EC V-VI' }),
      svg('text', { class: 'sub', x: 93, y: 651, 'text-anchor': 'middle', text: 'deep layers' })]));
    // lateral perforant path -> OML, medial -> MML, both blades (the medial one bold and labelled)
    const into = (k, th) => P(k, th);
    const o1 = into(145, 150), o2 = into(145, 214), m1 = into(119, 160), m2 = into(119, 205);
    conns.appendChild(conn('lpp', `M168,70 C230,70 ${o1[0] - 40},${o1[1] - 70} ${o1[0]},${o1[1]}`, 'stroke:' + col('fan'), 'pp'));
    conns.appendChild(conn('lpp', `M160,92 C200,200 ${o2[0] - 120},${o2[1] - 10} ${o2[0]},${o2[1]}`, 'stroke:' + col('fan'), 'pp'));
    conns.appendChild(conn('mpp', `M168,136 C215,136 ${m1[0] - 50},${m1[1] - 30} ${m1[0]},${m1[1]}`, 'stroke:' + col('stel'), 'pp'));
    conns.appendChild(conn('mpp', `M150,158 C175,260 ${m2[0] - 80},${m2[1] - 20} ${m2[0]},${m2[1]}`, 'stroke:' + col('stel'), 'pp'));
    tags.appendChild(svg('text', { class: 'elabel strong', x: 196, y: 120, text: 'medial perforant path → MML' }));
    tags.appendChild(svg('text', { class: 'elabel', x: 186, y: 56, text: 'lateral perforant path → OML' }));
    // EC II -> CA3 slm, EC III -> CA1 slm (temporoammonic)
    conns.appendChild(conn('pp_ca3', `M168,148 C420,150 520,${STRATA.slm[0] - 20} 560,${(STRATA.slm[0] + STRATA.slm[1]) / 2}`, 'stroke:' + col('stel') + ';stroke-dasharray:2 5;opacity:.8'));
    conns.appendChild(conn('ta', `M168,582 C520,590 740,470 800,${(STRATA.slm[0] + STRATA.slm[1]) / 2 + 2}`, 'stroke-dasharray:7 5'));
    tags.appendChild(svg('text', { class: 'elabel', x: 470, y: 560, text: 'temporoammonic (EC III → CA1 slm)' }));

    // granule cells, upper and lower blade, dendrites fanning out through the molecular layer
    const gc = (th, up) => {
      const s = P(73, th), out1 = [-16, -6, 6, 16].map((dt) => P(156, th + dt));
      return [svg('path', { d: out1.map((p) => `M${s[0]},${s[1]} L${p[0]},${p[1]}`).join(' '), class: 'dend', style: 'stroke:' + col('gc') }),
        svg('circle', { cx: s[0], cy: s[1], r: 6.5, style: 'fill:' + col('gc') })];
    };
    const g1 = P(73, 118), g2 = P(73, 242);
    cells.appendChild(glyph('gc', gc(118).concat(gc(242))));
    tag(g1[0] + 2, g1[1] + 22, 'GC');
    // mossy fibre: from the granule cell through the hilus into CA3 lucidum, giant boutons
    const slu = (STRATA.slu[0] + STRATA.slu[1]) / 2;
    conns.appendChild(conn('mf_ca3', `M${g1[0]},${g1[1] + 6} C${g1[0] + 6},${DG.cy - 4} ${DG.cx + 30},${slu} ${DG.cx + 70},${slu} L${560},${slu}`, 'stroke:' + col('gc') + ';stroke-width:2.6', 'mf'));
    for (let x = 400; x <= 560; x += 40) cells.appendChild(svg('circle', { class: 'bouton', cx: x, cy: slu, r: 5, style: 'fill:' + col('gc') }));
    conns.appendChild(conn('mf_mc', `M${DG.cx + 10},${DG.cy - 2} C${DG.cx - 2},${DG.cy + 6} ${DG.cx - 16},${DG.cy + 8} ${DG.cx - 26},${DG.cy + 6}`, 'stroke:' + col('gc')));
    // mossy cell (hilus) -> IML of both blades, far away
    const mc = P(36, 190);
    cells.appendChild(glyph('mc', [svg('path', { d: `M${mc[0]},${mc[1]} l-16,-10 M${mc[0]},${mc[1]} l-14,12 M${mc[0]},${mc[1]} l14,-12`, class: 'dend', style: 'stroke:' + col('mc') }),
      svg('circle', { cx: mc[0], cy: mc[1], r: 9, style: 'fill:' + col('mc') })]));
    tag(mc[0] - 4, mc[1] + 24, 'MC');
    conns.appendChild(conn('mc_gc', `M${mc[0]},${mc[1] - 9} C${mc[0] - 4},${DG.cy - 60} ${P(95, 135)[0] + 10},${P(95, 135)[1] + 10} ${P(95, 135)[0]},${P(95, 135)[1]}`, 'stroke:' + col('mc')));
    conns.appendChild(conn('mc_gc', `M${mc[0]},${mc[1] + 9} C${mc[0] - 4},${DG.cy + 60} ${P(95, 228)[0] + 10},${P(95, 228)[1] - 10} ${P(95, 228)[0]},${P(95, 228)[1]}`, 'stroke:' + col('mc')));
    // HIPP (hilus) -> outer two-thirds
    const hp = P(30, 232);
    cells.appendChild(glyph('hipp', [svg('circle', { cx: hp[0], cy: hp[1], r: 8, style: 'fill:' + col('hipp') })]));
    tag(hp[0] + 22, hp[1] + 14, 'HIPP');
    conns.appendChild(conn('hipp_gc', `M${hp[0] - 6},${hp[1] + 4} C${hp[0] - 40},${DG.cy + 120} ${P(140, 250)[0]},${P(140, 250)[1] + 4} ${P(140, 262)[0]},${P(140, 262)[1]}`, ''));
    conns.appendChild(conn('hipp_gc', `M${hp[0] - 8},${hp[1] - 4} C${hp[0] - 70},${DG.cy - 30} ${P(140, 165)[0] - 10},${P(140, 165)[1] + 30} ${P(140, 160)[0]},${P(140, 160)[1]}`, ''));
    // PV+ basket and axo-axonic cells at the granule layer / hilus border
    const pv = P(62, 92), aa = P(62, 70);
    cells.appendChild(glyph('pvbc', [svg('circle', { cx: pv[0], cy: pv[1], r: 7.5, style: 'fill:' + col('pvbc') })]));
    cells.appendChild(glyph('aac', [svg('circle', { cx: aa[0], cy: aa[1], r: 7, style: 'fill:' + col('aac') })]));
    tag(pv[0] - 8, pv[1] - 14, 'PV+ BC', 'end');
    tag(aa[0] + 14, aa[1] - 10, 'AAC', 'start');
    conns.appendChild(conn('pv_gc', `M${pv[0] - 6},${pv[1] + 2} Q${(pv[0] + g1[0]) / 2},${pv[1] + 18} ${g1[0] + 8},${g1[1] + 2}`, ''));
    conns.appendChild(conn('aac_gc', `M${aa[0] - 6},${aa[1] + 4} Q${(aa[0] + g1[0]) / 2 + 10},${aa[1] + 34} ${g1[0] + 4},${g1[1] + 8}`, ''));
    // semilunar granule cell in the IML
    const sg = P(95, 140);
    cells.appendChild(glyph('sgc', [svg('ellipse', { cx: sg[0], cy: sg[1], rx: 9, ry: 5, style: 'fill:' + col('sgc') })]));
    tag(sg[0] - 14, sg[1] - 8, 'SGC', 'end');
    conns.appendChild(conn('sgc_hil', `M${sg[0] + 4},${sg[1] + 4} Q${DG.cx - 20},${DG.cy - 20} ${mc[0] + 6},${mc[1] - 8}`, 'stroke:' + col('sgc')));

    // CA3 pyramidal cell, its recurrents, its Schaffer collateral into CA1 radiatum, the back-projection
    const spY = (STRATA.sp[0] + STRATA.sp[1]) / 2;
    const c3 = [560, spY];
    cells.appendChild(glyph('ca3', [svg('path', { d: `M${c3[0]},${c3[1] + 10} L${c3[0]},${STRATA.slm[1] - 4} M${c3[0]},${c3[1] - 6} l-14,-16 M${c3[0]},${c3[1] - 6} l14,-16`, class: 'dend', style: 'stroke:' + col('ca3') }),
      svg('path', { d: pyr(c3[0], c3[1], col('ca3'), 1), style: 'fill:' + col('ca3') })]));
    tag(c3[0] + 14, STRATA.so[0] - 30, 'CA3 PC', 'start');
    conns.appendChild(conn('rc', `M${c3[0] + 6},${c3[1] - 6} C${c3[0] + 50},${STRATA.so[0] - 30} ${c3[0] + 70},${STRATA.so[0] - 6} ${c3[0] + 40},${(STRATA.sr[0] + STRATA.sr[1]) / 2}`, 'stroke:' + col('ca3')));
    const srY = (STRATA.sr[0] + STRATA.sr[1]) / 2;
    conns.appendChild(conn('sc', `M${c3[0] + 8},${c3[1] - 4} C${c3[0] + 120},${STRATA.so[0] - 40} 760,${srY - 8} 846,${srY}`, 'stroke:' + col('ca3') + ';stroke-width:2.4'));
    tags.appendChild(svg('text', { class: 'elabel', x: 690, y: STRATA.so[0] - 44, text: 'Schaffer collaterals' }));
    conns.appendChild(conn('back', `M${c3[0] - 6},${c3[1] + 4} C${c3[0] - 80},${DG.cy + 90} ${DG.cx + 40},${DG.cy + 70} ${mc[0] + 10},${mc[1] + 6}`, 'stroke:' + col('ca3') + ';stroke-dasharray:6 5'));
    // CA1 pyramidal cell and the O-LM cell
    const c1 = [870, spY];
    cells.appendChild(glyph('ca1', [svg('path', { d: `M${c1[0]},${c1[1] + 10} L${c1[0]},${STRATA.slm[1] - 2} M${c1[0]},${STRATA.slm[0] + 6} l-12,10 M${c1[0]},${STRATA.slm[0] + 6} l12,10 M${c1[0]},${c1[1] - 6} l-14,-16 M${c1[0]},${c1[1] - 6} l14,-16`, class: 'dend', style: 'stroke:' + col('ca1') }),
      svg('path', { d: pyr(c1[0], c1[1], col('ca1'), 1), style: 'fill:' + col('ca1') })]));
    tag(c1[0] + 16, STRATA.so[0] - 30, 'CA1 PC', 'start');
    const om = [944, (STRATA.so[0] + STRATA.so[1]) / 2];
    cells.appendChild(glyph('olm', [svg('path', { d: `M${om[0] - 18},${om[1]} L${om[0] + 18},${om[1]}`, class: 'dend', style: 'stroke:' + col('olm') }),
      svg('circle', { cx: om[0], cy: om[1], r: 7, style: 'fill:' + col('olm') })]));
    tag(om[0] + 4, STRATA.slm[1] + 22, 'O-LM');
    conns.appendChild(conn('ca1_olm', `M${c1[0] + 8},${c1[1] - 8} Q${(c1[0] + om[0]) / 2},${STRATA.so[0] - 4} ${om[0] - 8},${om[1]}`, 'stroke:' + col('ca1')));
    conns.appendChild(conn('olm_ca1', `M${om[0]},${om[1] + 7} C${om[0] + 8},${STRATA.sr[1]} ${c1[0] + 30},${STRATA.slm[0] + 4} ${c1[0] + 8},${(STRATA.slm[0] + STRATA.slm[1]) / 2}`, ''));
    // CA1 -> subiculum -> deep EC
    conns.appendChild(conn('ca1_sub', `M${c1[0] + 10},${c1[1] - 2} C${c1[0] + 60},${STRATA.so[0] - 22} 1000,${STRATA.so[0] - 22} 1040,${STRATA.so[0] + 18}`, 'stroke:' + col('ca1')));
    conns.appendChild(conn('sub_ec5', `M1050,${STRATA.slm[1]} C1050,600 400,640 168,638`, ''));
    tags.appendChild(svg('text', { class: 'elabel', x: 720, y: 628, text: 'the loop closes in deep EC' }));

    out.appendChild(bandLabels);
    out.addEventListener('click', () => h.select(null));
    out._anchor = (sel) => {
      if (!sel) return null;
      if (sel.type === 'lamina' && L[sel.key]) return [L[sel.key][0], L[sel.key][1], 40, 24];
      if (sel.type === 'region') {
        const f = FIELDS.find((x) => x[0] === sel.key);
        if (f) return [(f[1] + f[2]) / 2, (STRATA.so[0] + STRATA.slm[1]) / 2, f[2] - f[1], STRATA.slm[1] - STRATA.so[0]];
        if (sel.key === 'dg') return [DG.cx, DG.cy, 320, 320];
      }
      if (sel.type === 'cell') { const g = out.querySelector('[data-cell="' + sel.key + '"]'); if (g) { try { const b = g.getBBox(); return [b.x + b.width / 2, b.y + b.height / 2, b.width, b.height]; } catch (e) { return null; } } }
      return null;
    };
    return out;
  }

  /* ----------------------------------------------------------------------
     One cell: inputs by layer, outputs by target
     ---------------------------------------------------------------------- */
  function cell(h, type) {
    const kb = h.kb, c = h.cellOf(type);
    const out = svg('svg', { class: 'sh-svg', viewBox: '0 0 1000 660', preserveAspectRatio: 'xMidYMid meet', role: 'img',
      'aria-label': 'Inputs and outputs of the ' + (c ? c.label : type) }, [defs()]);
    out._full = [0, 0, 1000, 660];
    if (!c) return out;
    const ins = kb.connections.filter((x) => !x.hidden && (x.to === type || (x.kind === 'region' && x.to === c.region)));
    const outs = kb.connections.filter((x) => !x.hidden && (x.from === type || (x.kind === 'region' && x.from === c.region && !h.cellOf(x.to))));
    const name = (k) => (h.cellOf(k) || h.regionOf(k) || { label: k }).label;
    out.classList.add('sh-circuit');
    out.appendChild(svg('text', { class: 'bt', x: 500, y: 52, 'text-anchor': 'middle', text: c.label }));
    out.appendChild(svg('text', { class: 'sub', x: 500, y: 72, 'text-anchor': 'middle', text: 'what feeds it (left, by the layer it lands in) and where it leads (right)' }));
    // the cell, centre
    const cx = 500, cy = 340;
    out.appendChild(part(h, { type: 'cell', key: type }, { class: 'glyph', 'data-cell': type }, [
      svg('circle', { cx, cy, r: 26, style: 'fill:' + c.color }),
      svg('path', { d: `M${cx},${cy - 26} L${cx},${cy - 120} M${cx},${cy - 80} l-40,-40 M${cx},${cy - 80} l40,-40 M${cx},${cy + 26} l-30,60 M${cx},${cy + 26} l30,60`, style: 'stroke:' + c.color + ';stroke-width:3;fill:none' }),
      svg('text', { x: cx, y: cy + 5, 'text-anchor': 'middle', class: 'bt sm', style: 'fill:#fff', text: c.short }),
    ]));
    const row = (list, side) => {
      const n = list.length;
      const top = Math.max(110, cy - (n - 1) * 34);
      list.forEach((x, i) => {
        const y = top + i * 68 * Math.min(1, 7 / Math.max(1, n));
        const other = side === 'in' ? x.from : x.to;
        const bx = side === 'in' ? 40 : 700;
        const lay = (x.layer || []).map((k) => (h.lamOf(k) || { label: k }).label).join(', ');
        const v = h.verdictOf(x.key);
        const ex = side === 'in' ? [bx + 260, y] : [bx, y];
        const target = side === 'in' ? [cx - 30, cy - 20 + (i - n / 2) * 10] : [cx + 30, cy + (i - n / 2) * 10];
        const p0 = side === 'in' ? ex : target, p1 = side === 'in' ? target : ex;
        const d = `M${p0[0]},${p0[1]} C${(p0[0] + p1[0]) / 2},${p0[1]} ${(p0[0] + p1[0]) / 2},${p1[1]} ${p1[0]},${p1[1]}`;
        out.appendChild(part(h, { type: 'conn', key: x.key }, { class: 'edge ' + x.sign, 'data-conn': x.key }, [
          svg('path', { class: 'hit', d }), svg('path', { class: 'ln', d, 'marker-end': 'url(#shm-' + x.sign + ')' })]));
        out.appendChild(part(h, h.cellOf(other) ? { type: 'cell', key: other } : { type: 'region', key: other },
          { class: 'box', 'data-cell': h.cellOf(other) ? other : null, 'data-region': h.cellOf(other) ? null : other }, [
            svg('rect', { class: 'body', x: bx, y: y - 24, width: 260, height: 48, rx: 11 }),
            svg('circle', { cx: bx + 14, cy: y - 8, r: 4.5, style: 'fill:' + verdictColor(v.status) }),
            svg('text', { x: bx + 26, y: y - 4, class: 'bt sm full', text: name(other) }),
            svg('text', { x: bx + 26, y: y + 6, class: 'bt sm short', text: (h.cellOf(other) || {}).short || SHORT[other] || name(other) }),
            svg('text', { x: bx + 26, y: y + 14, class: 'sub', text: (x.label || '') + (lay ? ' · ' + lay : '') }),
          ]));
      });
    };
    row(ins, 'in');
    row(outs, 'out');
    if (!ins.length) out.appendChild(svg('text', { class: 'sub', x: 170, y: cy, 'text-anchor': 'middle', text: 'no inputs listed' }));
    if (!outs.length) out.appendChild(svg('text', { class: 'sub', x: 830, y: cy, 'text-anchor': 'middle', text: 'no outputs listed' }));
    out.addEventListener('click', () => h.select(null));
    out._anchor = () => null;          // one cell, whole: nothing to follow
    out.classList.add('sh-cellwiring');
    return out;
  }

  /* ----------------------------------------------------------------------
     State onto a drawing
     ---------------------------------------------------------------------- */
  /* st: {focus: {cells, regionKeys, conns, layers} | null, hover: sel | null, sel: sel | null,
          here: sel | null, trail: [sel...], ds: {sink, source} | null} */
  function apply(s, st) {
    if (!s) return;
    const f = st.focus;
    const on = f && (f.cells.size || f.regionKeys.size || f.conns.size || f.layers.size);
    s.querySelectorAll('.flow,.sinkrect,.here-pin,.trail').forEach((n) => n.remove());
    const isSel = (t, k) => st.sel && st.sel.type === t && st.sel.key === k;
    const isHov = (t, k) => st.hover && st.hover.type === t && st.hover.key === k;
    const hovCell = st.hover && st.hover.type === 'cell' ? st.hover.key : null;
    s.querySelectorAll('[data-region]').forEach((n) => {
      const k = n.dataset.region;
      const lit = on && f.regionKeys.has(k);
      n.classList.toggle('dim', !!on && !lit);
      n.classList.toggle('lit', !!lit);
      n.classList.toggle('sel', isSel('region', k));
      n.classList.toggle('hover', isHov('region', k) || (hovCell && st.cellRegion && st.cellRegion(hovCell) === k));
    });
    s.querySelectorAll('[data-cell]').forEach((n) => {
      const k = n.dataset.cell;
      n.classList.toggle('dim', !!on && f.cells.size > 0 && !f.cells.has(k));
      n.classList.toggle('sel', isSel('cell', k));
      n.classList.toggle('hover', isHov('cell', k));
    });
    s.querySelectorAll('[data-layer]').forEach((n) => {
      const k = n.dataset.layer;
      n.classList.toggle('dim', !!on && f.layers.size > 0 && !f.layers.has(k));
      n.classList.toggle('sel', isSel('lamina', k));
      n.classList.toggle('hover', isHov('lamina', k));
    });
    s.querySelectorAll('[data-conn]').forEach((n) => {
      const k = n.dataset.conn;
      const lit = on && f.conns.has(k);
      n.classList.toggle('dim', !!on && !lit);
      n.classList.toggle('lit', !!lit);
      n.classList.toggle('sel', isSel('conn', k));
      n.classList.toggle('hover', isHov('conn', k));
      if (lit && !n.classList.contains('edge-label')) {
        const p = n.querySelector('path.ln');
        if (p) n.appendChild(svg('path', { class: 'flow', d: p.getAttribute('d') }));
      }
    });
    if (st.ds) {
      s.querySelectorAll('[data-layer]').forEach((n) => {
        const k = n.dataset.layer;
        const r = n.querySelector('rect, path');
        if (!r) return;
        const sink = st.ds.sink.includes(k), src = st.ds.source.includes(k);
        if (!sink && !src) return;
        n.classList.remove('dim');
        const cls = 'sinkrect ' + (sink ? 'sink' : 'source');
        const over = r.tagName === 'path' ? svg('path', { class: cls, d: r.getAttribute('d') })
          : svg('rect', { class: cls, x: r.getAttribute('x'), y: r.getAttribute('y'), width: r.getAttribute('width'), height: r.getAttribute('height') });
        n.insertBefore(over, r.nextSibling);
      });
    }
    // where you are, and where you have been
    if (s._anchor) {
      const pins = svg('g', { style: 'pointer-events:none' });
      // where you have been: small dots along the top edge of each box, older = fainter
      const seen = new Map();
      (st.trail || []).slice(-6).forEach((t, i, arr) => {
        const a = s._anchor(t);
        if (!a) return;
        const key = a.join(',');
        const n = seen.get(key) || 0;
        seen.set(key, n + 1);
        pins.appendChild(svg('circle', { class: 'trail', cx: a[0] - a[2] / 2 + 14 + n * 14, cy: a[1] - a[3] / 2 - 9, r: 5, style: 'opacity:' + (0.25 + 0.55 * (i + 1) / arr.length) }));
      });
      // where you are: a pin on the box, and a ring that breathes
      const a = s._anchor(st.here);
      if (a) {
        const x = a[0] + a[2] / 2 - 10, y = a[1] - a[3] / 2;
        pins.appendChild(svg('g', { class: 'here-pin', transform: `translate(${x},${y})` }, [
          svg('circle', { class: 'here-ring', cx: 0, cy: -22, r: 13 }),
          svg('path', { d: 'M0,0 C-5,-9 -12,-14 -12,-22 a12,12 0 1 1 24,0 C12,-14 5,-9 0,0 Z', style: 'fill:var(--accent);stroke:var(--bg);stroke-width:2' }),
          svg('circle', { cx: 0, cy: -22, r: 4.5, style: 'fill:var(--bg)' }),
        ]));
      }
      s.appendChild(pins);
    }
  }

  /* Ease the viewBox toward a part (or back to the whole drawing). */
  function follow(s, sel, on) {
    if (!s || !s._full) return;
    const full = s._full;
    let want = full;
    const a = on && sel && s._anchor ? s._anchor(sel) : null;
    if (a) {
      // a slight lean toward where you are: never so far that a word is cut
      // (the view always holds everything drawn, with a small margin)
      try { const b = s.getBBox(); s._content = [b.x - 8, b.y - 8, b.width + 16, b.height + 16]; } catch (e) { s._content = full; }
      const c = s._content;
      const k = 0.92;
      const w = Math.max(full[2] * k, c[2]), hh = Math.max(full[3] * k, c[3]);
      let x = a[0] - w / 2, y = a[1] - hh / 2;
      x = Math.max(c[0] + c[2] - w, Math.min(c[0], x));
      y = Math.max(c[1] + c[3] - hh, Math.min(c[1], y));
      want = [x, y, w, hh];
    }
    const cur = (s.getAttribute('viewBox') || full.join(' ')).split(/\s+/).map(Number);
    if (cur.every((v, i) => Math.abs(v - want[i]) < 0.5)) return;
    if (s._vbAnim) cancelAnimationFrame(s._vbAnim);
    const t0 = performance.now(), dur = (BARRY.ui && BARRY.ui.reducedMotion && BARRY.ui.reducedMotion()) ? 0 : 600;
    const step = (now) => {
      const k = dur ? Math.min(1, (now - t0) / dur) : 1;
      const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      s.setAttribute('viewBox', cur.map((v, i) => (v + (want[i] - v) * e).toFixed(1)).join(' '));
      if (k < 1) s._vbAnim = requestAnimationFrame(step);
    };
    s._vbAnim = requestAnimationFrame(step);
  }

  /* Keep words about the same size on screen however big the drawing is
     drawn: --u is user units per screen pixel (clamped). */
  function fitText(s) {
    if (!s || !s.isConnected) return;
    const vb = (s.getAttribute('viewBox') || '0 0 1000 660').split(/\s+/).map(Number);
    const r = s.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const scale = Math.min(r.width / vb[2], r.height / vb[3]);
    s.style.setProperty('--u', Math.max(0.85, Math.min(2.4, 1 / scale)).toFixed(3));
    // drawn small (the rail), the plate keeps its names and drops the fine print
    s.classList.toggle('sh-tiny', scale < 0.62);
  }

  return { circuit, dentate, cell, apply, follow, fitText, svg };
})();
