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
    return svg('defs', {}, [['exc', 'var(--text-2)'], ['inh', 'var(--err)'], ['lit', 'var(--accent)']].map(([k, c]) =>
      svg('marker', { id: 'shm-' + k, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' },
        [k === 'inh' ? svg('rect', { x: 3, y: 1, width: 4, height: 8, style: 'fill:' + c })
                     : svg('path', { d: 'M0,0 L10,5 L0,10 z', style: 'fill:' + c })])));
  }
  /* a part that hovers and selects */
  function part(h, sel, attrs, kids) {
    const g = svg('g', attrs, kids);
    g.addEventListener('click', (e) => { e.stopPropagation(); h.select(sel); });
    g.addEventListener('pointerenter', () => h.hover(sel));
    g.addEventListener('pointerleave', () => h.hover(null));
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
    out._full = [0, 0, 1000, 660];
    out.appendChild(svg('rect', { class: 'ec-box', x: 18, y: 230, width: 210, height: 330, rx: 10 }));
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
      const g = part(h, { type: 'conn', key: c.key }, { class: 'edge ' + c.sign + (c.dash ? ' dash' : ''), 'data-conn': c.key }, [
        svg('path', { class: 'hit', d }),
        svg('path', { class: 'ln', d, 'marker-end': 'url(#shm-' + c.sign + ')' }),
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
      boxes.appendChild(part(h, { type: 'region', key: r.key }, { class: 'box', 'data-region': r.key }, [
        svg('rect', { x: b.x, y: b.y, width: b.w, height: b.h, rx: 8 }),
        svg('text', { x: b.cx, y: b.cy - 3, 'text-anchor': 'middle', class: 'bt', text: r.label }),
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
     The dentate, by layer
     ---------------------------------------------------------------------- */
  const DG_BANDS = [['oml1', 44], ['mml1', 44], ['iml1', 34], ['gcl1', 36], ['hil', 96], ['gcl2', 36], ['iml2', 34], ['mml2', 44], ['oml2', 44]];
  const CA3_BANDS = [['ca3slm', 56], ['ca3sr', 92], ['ca3slu', 40], ['ca3sp', 40], ['ca3so', 70]];
  function dentate(h) {
    const kb = h.kb, LC = kb.lamina_colors;
    const out = svg('svg', { class: 'sh-svg', viewBox: '0 0 1000 660', preserveAspectRatio: 'xMidYMid meet', role: 'img',
      'aria-label': 'Dentate gyrus microcircuit by layer' }, [defs()]);
    out._full = [0, 0, 1000, 660];
    const X0 = 236, X1 = 700, CX0 = 772, CX1 = 986;
    const Y = {};
    let y = 92;
    const bands = svg('g', {});
    out.appendChild(bands);
    for (const [k, hh] of DG_BANDS) {
      Y[k] = [y, y + hh];
      const lab = (h.lamOf(k) || { label: k.toUpperCase() }).label;
      bands.appendChild(part(h, { type: 'lamina', key: k }, { class: 'band', 'data-layer': k }, [
        svg('rect', { x: X0, y, width: X1 - X0, height: hh, style: 'fill:' + LC[k] + ';opacity:0.3' }),
        svg('text', { class: 'blabel', x: X0 - 8, y: y + hh / 2 + 4, 'text-anchor': 'end', text: lab }),
      ]));
      y += hh;
    }
    let y3 = 150;
    for (const [k, hh] of CA3_BANDS) {
      Y[k] = [y3, y3 + hh];
      const lab = (h.lamOf(k) || { label: k }).label.replace('CA3 ', '');
      bands.appendChild(part(h, { type: 'lamina', key: k }, { class: 'band', 'data-layer': k }, [
        svg('rect', { x: CX0, y: y3, width: CX1 - CX0, height: hh, style: 'fill:' + LC[k] + ';opacity:0.3' }),
        svg('text', { class: 'blabel', x: CX1 - 6, y: y3 + 14, 'text-anchor': 'end', text: lab }),
      ]));
      y3 += hh;
    }
    out.appendChild(svg('text', { class: 'bt', x: (X0 + X1) / 2, y: 74, 'text-anchor': 'middle', text: 'Dentate gyrus' }));
    out.appendChild(svg('text', { class: 'bt', x: (CX0 + CX1) / 2, y: 134, 'text-anchor': 'middle', text: 'CA3' }));
    out.appendChild(svg('text', { class: 'sub', x: (X0 + X1) / 2, y: 616, 'text-anchor': 'middle', text: 'upper (suprapyramidal) blade above the hilus, lower (infrapyramidal) blade below' }));
    const mid = (k) => (Y[k][0] + Y[k][1]) / 2;
    const col = (k) => (h.cellOf(k) || {}).color || '#888';
    const glyph = (key, kids) => part(h, { type: 'cell', key }, { class: 'glyph', 'data-cell': key }, kids);
    const conn = (key, d, extra) => part(h, { type: 'conn', key }, { class: 'edge ' + ((h.connOf(key) || {}).sign || 'exc'), 'data-conn': key }, [
      svg('path', { class: 'hit', d }), svg('path', { class: 'ln', d, style: extra || '' })]);
    const conns = svg('g', {}), cells = svg('g', {}), tags = svg('g', { style: 'pointer-events:none' });
    out.append(conns, cells, tags);
    const tag = (x, y2, text, anchor) => tags.appendChild(svg('text', { class: 'ctag', x, y: y2, 'text-anchor': anchor || 'start', text }));
    // entorhinal inputs
    const ecL = [86, 36], ecM = [86, 640 - 22];
    cells.appendChild(glyph('fan', [svg('rect', { x: 16, y: ecL[1] - 22, width: 140, height: 42, rx: 7, style: 'fill:var(--bg-2);stroke:' + col('fan') + ';stroke-width:2' }),
      svg('text', { x: 86, y: ecL[1] - 3, 'text-anchor': 'middle', class: 'bt sm', text: 'LEC II' }),
      svg('text', { class: 'sub', x: 86, y: ecL[1] + 13, 'text-anchor': 'middle', text: 'fan cells' })]));
    cells.appendChild(glyph('stel', [svg('rect', { x: 16, y: ecM[1] - 22, width: 140, height: 42, rx: 7, style: 'fill:var(--bg-2);stroke:' + col('stel') + ';stroke-width:2' }),
      svg('text', { x: 86, y: ecM[1] - 3, 'text-anchor': 'middle', class: 'bt sm', text: 'MEC II' }),
      svg('text', { class: 'sub', x: 86, y: ecM[1] + 13, 'text-anchor': 'middle', text: 'stellate cells' })]));
    const lppS = 'stroke:' + col('fan'), mppS = 'stroke:' + col('stel');
    conns.appendChild(conn('lpp', `M156,${ecL[1]} C200,${ecL[1]} 200,${mid('oml1')} ${X0},${mid('oml1')} L${X1 - 10},${mid('oml1')}`, lppS));
    conns.appendChild(conn('lpp', `M100,${ecL[1] + 20} C110,240 160,${mid('oml2')} ${X0},${mid('oml2')} L${X1 - 10},${mid('oml2')}`, lppS));
    conns.appendChild(conn('mpp', `M156,${ecM[1]} C200,${ecM[1]} 200,${mid('mml2')} ${X0},${mid('mml2')} L${X1 - 10},${mid('mml2')}`, mppS));
    conns.appendChild(conn('mpp', `M72,${ecM[1] - 20} C62,420 160,${mid('mml1')} ${X0},${mid('mml1')} L${X1 - 10},${mid('mml1')}`, mppS));
    // granule cells, both blades
    const gcU = [300, mid('gcl1')], gcL = [300, mid('gcl2')];
    const fan = (x, y0, yTip) => [-36, -12, 12, 36].map((dx) => `M${x},${y0} L${x + dx},${yTip}`).join(' ');
    cells.appendChild(glyph('gc', [
      svg('path', { d: fan(gcU[0], gcU[1] - 8, Y.oml1[0] + 4), style: 'stroke:' + col('gc') + ';stroke-width:2;fill:none' }),
      svg('path', { d: `M${gcU[0] - 9},${gcU[1] + 6} L${gcU[0] + 9},${gcU[1] + 6} L${gcU[0]},${gcU[1] - 10} z`, style: 'fill:' + col('gc') }),
      svg('path', { d: fan(gcL[0], gcL[1] + 8, Y.oml2[1] - 4), style: 'stroke:' + col('gc') + ';stroke-width:2;fill:none' }),
      svg('path', { d: `M${gcL[0] - 9},${gcL[1] - 6} L${gcL[0] + 9},${gcL[1] - 6} L${gcL[0]},${gcL[1] + 10} z`, style: 'fill:' + col('gc') }),
    ]));
    tag(gcU[0] + 14, gcU[1] + 4, 'GC');
    // mossy fiber: GC -> hilar collaterals -> CA3 stratum lucidum
    const mfY = mid('hil') - 22;
    conns.appendChild(conn('mf_ca3', `M${gcU[0]},${gcU[1] + 8} C${gcU[0] + 10},${mfY} ${gcU[0] + 40},${mfY} 540,${mfY} C690,${mfY} 720,${mid('ca3slu')} ${CX0},${mid('ca3slu')} L${CX0 + 120},${mid('ca3slu')}`,
      'stroke:' + col('gc') + ';stroke-width:2.6'));
    for (let x = CX0 + 22; x <= CX0 + 120; x += 32) cells.appendChild(svg('circle', { class: 'bouton', cx: x, cy: mid('ca3slu'), r: 5.5, style: 'fill:' + col('gc') }));
    conns.appendChild(conn('mf_mc', `M372,${mfY} C380,${mfY + 18} 392,${mid('hil') + 6} 404,${mid('hil') + 8}`, 'stroke:' + col('gc')));
    conns.appendChild(conn('mf_int', `M486,${mfY} C492,${mfY + 12} 500,${mid('hil') + 10} 508,${mid('hil') + 14}`, 'stroke:' + col('gc')));
    // mossy cell -> IML of both blades
    const mc = [412, mid('hil') + 20];
    conns.appendChild(conn('mc_gc', `M${mc[0]},${mc[1] - 8} C${mc[0] + 10},${mid('iml1')} ${mc[0] + 30},${mid('iml1')} 452,${mid('iml1')} L${X1 - 40},${mid('iml1')}`, 'stroke:' + col('mc')));
    conns.appendChild(conn('mc_gc', `M${mc[0]},${mc[1] + 8} C${mc[0] + 10},${mid('iml2')} ${mc[0] + 30},${mid('iml2')} 452,${mid('iml2')} L${X1 - 40},${mid('iml2')}`, 'stroke:' + col('mc')));
    cells.appendChild(glyph('mc', [
      svg('path', { d: `M${mc[0]},${mc[1]} l-28,-14 M${mc[0]},${mc[1]} l-30,16 M${mc[0]},${mc[1]} l26,-18 M${mc[0]},${mc[1]} l28,14`, style: 'stroke:' + col('mc') + ';stroke-width:3;fill:none' }),
      svg('circle', { cx: mc[0], cy: mc[1], r: 10, style: 'fill:' + col('mc') }),
    ]));
    tag(mc[0], mc[1] + 30, 'MC', 'middle');
    // HIPP: hilus -> OML/MML of both blades
    const hp = [516, mid('hil') + 24];
    conns.appendChild(conn('hipp_gc', `M${hp[0]},${hp[1] - 9} C${hp[0] + 6},${Y.mml1[0]} ${hp[0] + 20},${mid('oml1') + 10} 548,${mid('oml1') + 9} L${X1 - 22},${mid('oml1') + 9}`));
    conns.appendChild(conn('hipp_gc', `M${hp[0]},${hp[1] + 9} C${hp[0] + 6},${Y.mml2[1]} ${hp[0] + 20},${mid('oml2') - 10} 548,${mid('oml2') - 9} L${X1 - 22},${mid('oml2') - 9}`));
    cells.appendChild(glyph('hipp', [svg('circle', { cx: hp[0], cy: hp[1], r: 9, style: 'fill:' + col('hipp') }),
      svg('path', { d: `M${hp[0]},${hp[1]} l-24,8 M${hp[0]},${hp[1]} l22,10`, style: 'stroke:' + col('hipp') + ';stroke-width:2' })]));
    tag(hp[0], hp[1] + 30, 'HIPP', 'middle');
    // PV+ basket and axo-axonic at the granule layer / hilus border
    const pv = [586, Y.gcl1[1] + 8];
    conns.appendChild(conn('pv_gc', `M${pv[0]},${pv[1]} C${pv[0] - 30},${mid('gcl1') + 2} ${gcU[0] + 60},${mid('gcl1')} ${gcU[0] + 12},${mid('gcl1')}`));
    conns.appendChild(conn('pp_pv', `M${X0},${mid('mml1') + 6} C430,${mid('mml1') + 6} ${pv[0] - 6},${mid('mml1') + 14} ${pv[0]},${Y.iml1[1]}`, 'stroke:' + col('stel') + ';stroke-dasharray:3 4'));
    conns.appendChild(conn('gc_pv', `M${gcU[0] + 30},${mfY} C490,${mfY - 4} ${pv[0] - 10},${pv[1] + 20} ${pv[0]},${pv[1] + 8}`, 'stroke:' + col('gc') + ';stroke-dasharray:3 4'));
    cells.appendChild(glyph('pvbc', [svg('path', { d: `M${pv[0]},${pv[1]} l-10,-36 M${pv[0]},${pv[1]} l12,-40 M${pv[0]},${pv[1]} l4,30`, style: 'stroke:' + col('pvbc') + ';stroke-width:2' }),
      svg('circle', { cx: pv[0], cy: pv[1], r: 9, style: 'fill:' + col('pvbc') })]));
    tag(pv[0] - 4, pv[1] + 46, 'PV+ BC', 'middle');
    const aa = [662, Y.gcl1[1] + 10];
    conns.appendChild(conn('aac_gc', `M${aa[0]},${aa[1]} C${aa[0] - 40},${Y.gcl1[1] + 16} ${gcU[0] + 40},${Y.gcl1[1] + 12} ${gcU[0] + 4},${Y.gcl1[1] + 2}`));
    cells.appendChild(glyph('aac', [svg('path', { d: `M${aa[0]},${aa[1]} l-6,-44 M${aa[0]},${aa[1]} l10,-46`, style: 'stroke:' + col('aac') + ';stroke-width:2' }),
      svg('circle', { cx: aa[0], cy: aa[1], r: 8, style: 'fill:' + col('aac') })]));
    tag(aa[0] + 4, aa[1] + 28, 'AAC', 'middle');
    // semilunar granule cell in the IML
    const sg = [452, mid('iml1')];
    conns.appendChild(conn('sgc_hil', `M${sg[0]},${sg[1] + 6} C${sg[0] - 6},${mid('hil') - 34} ${sg[0] - 28},${mid('hil') + 6} ${mc[0] + 12},${mc[1] - 6}`, 'stroke:' + col('sgc')));
    cells.appendChild(glyph('sgc', [svg('path', { d: [-52, -18, 20, 54].map((dx) => `M${sg[0]},${sg[1]} L${sg[0] + dx},${Y.oml1[0] + 5}`).join(' '), style: 'stroke:' + col('sgc') + ';stroke-width:2;fill:none' }),
      svg('ellipse', { cx: sg[0], cy: sg[1], rx: 11, ry: 6, style: 'fill:' + col('sgc') })]));
    tag(sg[0] + 16, sg[1] + 4, 'SGC');
    // CA3 pyramidal cell
    const c3 = [904, mid('ca3sp')];
    cells.appendChild(glyph('ca3', [svg('path', { d: `M${c3[0]},${c3[1] - 8} L${c3[0]},${Y.ca3slm[0] + 6} M${c3[0]},${mid('ca3sr')} l-30,-30 M${c3[0]},${mid('ca3sr')} l26,-34 M${c3[0]},${c3[1] + 8} l-22,40 M${c3[0]},${c3[1] + 8} l20,44`, style: 'stroke:' + col('ca3') + ';stroke-width:2.2;fill:none' }),
      svg('path', { d: `M${c3[0] - 11},${c3[1] + 8} L${c3[0] + 11},${c3[1] + 8} L${c3[0]},${c3[1] - 12} z`, style: 'fill:' + col('ca3') })]));
    tag(c3[0] - 16, c3[1] + 4, 'CA3 PC', 'end');
    conns.appendChild(conn('back', `M${c3[0] - 4},${c3[1] + 10} C${c3[0] - 60},${Y.ca3so[1] + 40} 610,${mid('hil') + 64} ${mc[0] + 14},${mc[1] + 8}`, 'stroke:' + col('ca3') + ';stroke-dasharray:6 5'));
    conns.appendChild(conn('rc', `M${c3[0] + 6},${c3[1] + 10} C${c3[0] + 70},${Y.ca3so[1]} ${c3[0] + 76},${mid('ca3sr')} ${c3[0] + 26},${mid('ca3sr')}`, 'stroke:' + col('ca3')));
    out.addEventListener('click', () => h.select(null));
    out._bandY = Y;
    out._anchor = (sel) => {
      if (!sel) return null;
      if (sel.type === 'lamina' && Y[sel.key]) { const yy = Y[sel.key]; return [sel.key.startsWith('ca3') ? (CX0 + CX1) / 2 : (X0 + X1) / 2, (yy[0] + yy[1]) / 2, 300, yy[1] - yy[0]]; }
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
            svg('rect', { x: bx, y: y - 24, width: 260, height: 48, rx: 8 }),
            svg('circle', { cx: bx + 14, cy: y - 8, r: 4.5, style: 'fill:' + verdictColor(v.status) }),
            svg('text', { x: bx + 26, y: y - 4, class: 'bt sm', text: name(other) }),
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
        const r = n.querySelector('rect');
        if (!r) return;
        const sink = st.ds.sink.includes(k), src = st.ds.source.includes(k);
        if (!sink && !src) return;
        n.classList.remove('dim');
        n.insertBefore(svg('rect', { class: 'sinkrect ' + (sink ? 'sink' : 'source'), x: r.getAttribute('x'), y: r.getAttribute('y'),
          width: r.getAttribute('width'), height: r.getAttribute('height') }), r.nextSibling);
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
      const k = 0.86;
      const w = full[2] * k, hh = full[3] * k;
      let x = a[0] - w / 2, y = a[1] - hh / 2;
      x = Math.max(full[0], Math.min(full[0] + full[2] - w, x));
      y = Math.max(full[1], Math.min(full[1] + full[3] - hh, y));
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

  return { circuit, dentate, cell, apply, follow, svg };
})();
