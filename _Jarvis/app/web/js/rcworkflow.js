/* rcworkflow.js -- Root Canal's Workflow tab (2026-11-05).

   "Create a Workflow tab in Root Canal: 1. Verified dentate spikes,
   2. Verified P-spikes, 3. Ambiguous -- Define border, Apply border,
   Extract spikes. I want to be able to see the 3D graphs of each stage.
   Workflows can be constructed and archived. Their results go to the bank,
   viewable and easily reconstructed, and every event can be traced back to
   the recording's waveforms."

   One module, painted by Root Canal when its view bar says Workflow
   (rootcanal.js, `paint_`). The server does every number
   (backend/rcworkflow.py, the /api/rootcanal/workflow* routes); this draws
   them:

     the pipeline strip   three stage cards per workflow, each a small
                          picture, its counts and its state
     the stage in 3D      rotatable, with the border's box (and the other
                          border's, for Ambiguous), every dot pickable
     beside it            the three 2D views with the cut-offs, how far each
                          event is from the box, the grace sweep, the flow
                          from mice to classes, every mouse on its own, the
                          class averages and the conflicts
     the picked event     its three numbers against the cut-offs, its
                          history, its waveform and CSD, and Xplorefinder
     the lineage          every version, what each run moved, rebuild

   Nothing here banks or saves without a press that says it will. */
'use strict';

BARRY.rcWorkflow = (function () {
  const ARCH_KEY = 'rootcanal_workflow_archive';
  const KIND_WORDS = {
    ds: 'Verified dentate spikes', pspike: 'Verified P-spikes',
    ambiguous: 'Ambiguous', pca: 'Pooled PCA',
  };
  const KIND_ORDER = ['ds', 'pspike', 'ambiguous', 'pca'];
  const STAGES = [['define', 'Define border'], ['apply', 'Apply border'],
                  ['extract', 'Extract']];
  /* POOLED PCA (2026-11-06: "pool PTEN Baseline and CTL Baseline into a
     single pool, run a PCA and show us the 2D PCA graph ... every dot
     clickable ... the 3D view on the side"). Its strip has three pictures
     of its own, and it banks nothing, like Ambiguous. */
  const PCA_STAGES = [['pool', 'Pool'], ['pca', 'PCA'], ['calls', 'Calls']];
  const stagesOf = (kind) => (kind === 'pca' ? PCA_STAGES : STAGES);
  const viewOnly = (kind) => kind === 'ambiguous' || kind === 'pca';
  const PCA_COLOURS = [['pool', 'the one pool’s call'],
                       ['own', 'each pool’s own call'],
                       ['verified', 'the verified borders'],
                       ['mouse', 'mouse'], ['recording', 'recording']];
  // The other kinds' Colour by (2026-11-06).
  const WF_COLOURS = [['call', 'the call'], ['mouse', 'mouse'],
                      ['recording', 'recording']];
  // Column name, event key, words, unit.
  const AX = [['amp', 'amp_uV', 'max amplitude', 'µV'],
              ['hf', 'hf_db', 'HF power', 'dB'],
              ['hw', 'hw_ms', 'half-width', 'ms']];
  const GRACES = [[0, 'none'], [0.01, '1%'], [0.05, '5%']];
  /* BORDER SHAPES (2026-11-11: "box borders, snap to point minimum borders,
     and something more curvy / ice cream scoopy in the middle"): the box,
     the scoop (an ellipsoid fitted robustly) and the snap (the convex
     hull). backend/rcborder.py draws them; this draws what it drew. */
  const SHAPES = [['box', 'Box'], ['ellipsoid', 'Scoop'], ['hull', 'Snap']];
  const SHAPE_WORD = { box: 'Box', ellipsoid: 'Scoop', hull: 'Snap' };
  /* THE SCOOP IS RETIRED (2026-11-12: "retire and archive all the scoop
     stuff... like the data and the option in the workflow"). Its runs were
     archived, not deleted, and still draw when shown; it is no longer
     offered for a new border, and the server refuses one. */
  const RETIRED = { ellipsoid: 'The scoop was retired on 2026-11-12. Pick the box or the snap.' };
  const SHAPES_OFFERED = SHAPES.filter(([k]) => !RETIRED[k]);
  const FOLDER_KEY = 'rootcanal_workflow_in';
  const FOLDER_OPEN_KEY = 'barry.rcworkflow.folders';

  const W = {
    list: null, listErr: null, loading: false,
    sources: null, sourcesErr: null,
    data: {},            // artifact id -> {version, payload, lines, stale}
    openId: null, openVersion: null, stage: 'apply',
    builder: null, prep: null, preview: null,
    showArchived: false,
    // `at`: the frame's point at the 3D canvas's middle, in its -1..1 units
    // (moved by shift+drag, zoomed toward by the wheel); `key`: whose view.
    view: { yaw: -0.65, pitch: 0.42, zoom: 1, at: [0, 0, 0], key: null },
    picked: null,        // {which: 'src'|'tgt', n}
    ev: null,            // the picked event's traces: {busy, data, err}
    avg: null,           // {label, busy, data, err}
    ambShow: 'all', ambPick: new Set(), ambType: 'ied',
    pcaColour: 'pool',   // which call colours a Pooled PCA's dots, or 'mouse' / 'recording'
    pcaShow: 'all',      // 'all', or the number of the one pool on show
    wfColour: 'call',    // the other kinds' dots: 'call', 'mouse' or 'recording'
    builderArch: false,  // the builder offers archived pools too
    busy: null,
  };
  let H = null;          // what Root Canal lends: render, openPool, path
  let root = null;

  const tok = (n, f) => BARRY.token(n, f);
  const fmt = (v, d) => (v == null || !isFinite(v) ? '—'
    : Math.abs(v) >= 100 ? Math.round(v).toLocaleString()
    : Number(v).toFixed(d == null ? 1 : d));
  const pct = (v) => (v == null ? '—' : (100 * v).toFixed(v < 0.1 ? 1 : 0) + '%');
  const graceWords = (g) => (Number(g) === 0 ? 'none'
    : +(100 * Number(g)).toFixed(2) + '%');

  /* ==================================================================
     Archive (a shared preference, like the borders' -- rootcanal.js)
     ================================================================== */
  function archived() {
    try { return (BARRY.prefs && BARRY.prefs.get(ARCH_KEY, {})) || {}; }
    catch (e) { return {}; }
  }

  async function setArchived(row, on) {
    // Just this workflow (2026-11-06): the whole map was this page's copy
    // from boot, and sending it un-archived a colleague's newer ones.
    BARRY.prefs.mergeKey(ARCH_KEY, row.artifact_id,
                         on ? { at: new Date().toISOString() } : null);
    /* And what it banked, with it (decided 2026-11-05): archived, never
       deleted, and put back the same way. */
    const ids = new Set();
    const d = W.data[row.artifact_id];
    for (const ln of (d && d.lines) || []) {
      if (ln.bank && ln.bank.entry_id) ids.add(ln.bank.entry_id);
    }
    if (row.bank && row.bank.entry_id) ids.add(row.bank.entry_id);
    let n = 0;
    for (const id of ids) {
      try {
        await apiPost('/api/bank/' + encodeURIComponent(id) + '/archive',
                      { archived: !!on });
        n += 1;
      } catch (e) {
        toast('The workflow was ' + (on ? 'archived' : 'put back')
              + ' but its bank entry ' + id + ' was not: ' + e.message,
              'warn', 9000);
      }
    }
    toast((on ? 'Archived ‘' : 'Put back ‘') + (row.nickname || row.name) + '’'
          + (n ? ', and the ' + n + ' bank entr' + (n === 1 ? 'y' : 'ies')
                 + ' it made' : '') + '.', 'ok', 6000);
    BARRY.activity.log('rootcanal.workflow_archive',
                       { artifact: row.artifact_id, archived: !!on });
    refresh();
  }

  /* ARCHIVED POOLS LEAVE THE BUILDER (2026-11-06): a saved pool archived in
     Pooled -- or filed in a folder that is archived -- is not offered here
     either, unless it is the one already picked. The same shared
     preferences Pooled keeps (rootcanal.js, ARCHIVED POOLS):
       rootcanal_pool_archive  {pool id: {at, by}}
       rootcanal_pool_folders  {folder id: {..., archived}}
       rootcanal_pool_in       {pool id: folder id}; unfiled is 'prelim' */
  const POOL_ARCH_KEY = 'rootcanal_pool_archive';
  function prefOf(k) {
    try { return (BARRY.prefs && BARRY.prefs.get(k, {})) || {}; }
    catch (e) { return {}; }
  }
  /* '' when it is on show; else why not: 'archived', or 'folder'. */
  function poolShelved(id) {
    if (prefOf(POOL_ARCH_KEY)[id]) return 'archived';
    const inm = prefOf('rootcanal_pool_in');
    const fid = Object.prototype.hasOwnProperty.call(inm, id) ? inm[id] : 'prelim';
    const f = fid ? prefOf('rootcanal_pool_folders')[fid] : null;
    return f && f.archived && !f.gone ? 'folder' : '';
  }
  const shelvedWords = (why) => (why === 'archived' ? ' · archived'
    : why === 'folder' ? ' · in an archived folder' : '');

  function putBackPool(p) {
    // Just this pool (2026-11-06), not the map from boot -- see
    // BARRY.prefs.mergeKey.
    BARRY.prefs.mergeKey(POOL_ARCH_KEY, p.artifact_id, null);
    toast('Put back ‘' + p.nickname + '’.', 'ok', 5000);
    BARRY.activity.log('rootcanal.pool_archive', { artifact: p.artifact_id,
                                                   archived: false });
    refresh();
  }

  /* ==================================================================
     Loading
     ================================================================== */
  async function loadList() {
    if (W.loading) return;
    W.loading = true;
    try {
      const got = await api('/api/rootcanal/workflows');
      W.list = got.workflows || [];
      W.listErr = null;
    } catch (e) {
      W.list = W.list || [];
      W.listErr = e.message;
    }
    W.loading = false;
    refresh();
    // Each workflow's newest version, for its strip's pictures.
    for (const r of W.list || []) {
      if (r.ran && !(W.data[r.artifact_id]
                     && W.data[r.artifact_id].version === r.version)) {
        loadOne(r.artifact_id, null, true);
      }
    }
  }

  async function loadSources() {
    if (W.sources) return W.sources;
    try {
      W.sources = await api('/api/rootcanal/workflow/sources');
      W.sourcesErr = null;
    } catch (e) {
      W.sourcesErr = e.message;
      W.sources = { pools: [], sets: [] };
    }
    return W.sources;
  }

  async function loadOne(id, version, quiet) {
    try {
      const got = await api('/api/rootcanal/workflow/' + encodeURIComponent(id)
                            + (version != null ? '?version=' + version : ''));
      W.data[id] = { version: (got.artifact || {}).version,
                     shown: version != null ? version : (got.shown || null),
                     newer: version != null ? null : (got.newer_definition || null),
                     payload: got.payload || {}, lines: got.lines || [],
                     stale: got.stale || [] };
    } catch (e) {
      if (!quiet) toast('That workflow could not be opened: ' + e.message,
                        'err', 9000);
      return null;
    }
    refresh();
    return W.data[id];
  }

  /* The run on show: a preview, or the open workflow's chosen version. */
  function shownRun() {
    return haloView(shownBase());
  }
  /* The run as saved, before the Halo on the page re-sorts it. */
  function shownBase() {
    if (W.preview) return W.preview.run;
    const d = W.openId && W.data[W.openId];
    return d && d.payload ? d.payload.run : null;
  }
  function shownDef() {
    if (W.preview) return W.preview.definition;
    const d = W.openId && W.data[W.openId];
    return d && d.payload ? d.payload.definition : null;
  }

  /* ==================================================================
     Events, out of a run's columns
     ================================================================== */
  function pointsOf(col) {
    if (!col) return [];
    const out = [];
    const n = (col.t || []).length;
    for (let j = 0; j < n; j++) {
      out.push({
        n: j, amp: col.amp[j], hf: col.hf[j], hw: col.hw[j],
        cls: col.cls[j], g: col.g[j], m: col.m[j], i: col.i[j],
        t: col.t[j], mouse: (col.mouse || [])[j],
        gid: (col.gids || [])[col.g[j]] || null,
        da: col.d_a ? col.d_a[j] : null, db: col.d_b ? col.d_b[j] : null,
        // A Pooled PCA's: the scores, which pool, its own pool's call, and
        // where the verified borders put it.
        pc: col.pc ? col.pc[j] : null, src: col.src ? col.src[j] : null,
        own: col.own ? col.own[j] : null, ver: col.ver ? col.ver[j] : null,
      });
    }
    return out;
  }

  const finite = (v) => v != null && isFinite(v);
  const measured = (p) => finite(p.amp) && finite(p.hf) && finite(p.hw);

  /* One frame for every picture of a run: every axis spans the same values
     in every stage, so a box does not seem to move when the stage does.
     EVERY BORDER WHOLE (2026-11-12: "the borders in the 2D graph get cut
     off"): the dots set the frame, from their 0.5% to their 99.5%, and it
     then grows to hold every border of `kind`, solid and dashed alike; a
     border's own events can reach past the target's. A grown copy of a
     border (`halo`) never widens it: the pictures clip that instead. With
     no `kind`, the dots alone. */
  function borderExtents(run, kind) {
    const ext = {};
    const take = (i, v) => {
      if (!finite(v)) return;
      const c = AX[i][0];
      const e = ext[c] || (ext[c] = [v, v]);
      if (v < e[0]) e[0] = v;
      if (v > e[1]) e[1] = v;
    };
    let boxes = [];
    // A border that cannot be read leaves the dots' frame, not no picture.
    try { boxes = boxesOf(run, kind) || []; } catch (e) { boxes = []; }
    for (const b of boxes) {
      if (!b || b.halo) continue;
      const sh = b.shape;
      if (sh && sh.kind === 'hull') {
        for (const v of sh.vertices || []) for (let i = 0; i < 3; i++) take(i, v && v[i]);
      } else if (sh && sh.kind === 'ellipsoid' && sh.center) {
        for (let i = 0; i < 3; i++) {
          const r = sh.M && sh.M[i] ? Math.sqrt(Math.max(0, sh.M[i][i]))
            : Math.sqrt((sh.axes || []).reduce((s, a) => s + (a && finite(a[i]) ? a[i] * a[i] : 0), 0));
          take(i, sh.center[i] - r);
          take(i, sh.center[i] + r);
        }
      }
      AX.forEach(([c], i) => { take(i, (b.lo || {})[c]); take(i, (b.hi || {})[c]); });
    }
    return ext;
  }

  function rangesOf(run, kind) {
    const all = pointsOf(run.cols).concat(pointsOf(run.src_cols));
    const ext = kind ? borderExtents(run, kind) : {};
    const out = {};
    for (const [c] of AX) {
      const v = all.map((p) => p[c]).filter(finite).sort((a, b) => a - b);
      const e = ext[c];
      if (!v.length && !e) { out[c] = [0, 1]; continue; }
      const q = (f) => v[Math.min(v.length - 1, Math.max(0, Math.floor(f * (v.length - 1))))];
      let lo = v.length ? q(0.005) : e[0], hi = v.length ? q(0.995) : e[1];
      if (e) { lo = Math.min(lo, e[0]); hi = Math.max(hi, e[1]); }
      if (hi <= lo) { lo -= 1; hi += 1; }
      const pad = (hi - lo) * 0.06;
      out[c] = [lo - pad, hi + pad];
    }
    return out;
  }

  /* The boxes of a run: [{lo, hi (by column), colour, dashed, label}]. */
  function boxesOf(run, kind) {
    const out = [];
    const add = (border, grace, colour, words) => {
      if (!border) return;
      const lv = (border.levels || []).find(
        (l) => Math.abs(Number(l.grace) - Number(grace)) < 1e-9);
      const st = border.strict || {};
      const mk = (src) => {
        const lo = {}, hi = {};
        for (const [c, k] of AX) { lo[c] = (src[k] || {}).lo; hi[c] = (src[k] || {}).hi; }
        return { lo, hi };
      };
      // A scoop or a snap is its shape; `lo`/`hi` are then its extent.
      const shape = border.shape && border.shape !== 'box' ? border.shape : null;
      const name = shape ? words + ' ' + SHAPE_WORD[shape].toLowerCase() : words + ' border';
      if (lv) out.push(Object.assign(mk(lv.edges || {}), { colour, dashed: false,
        shape: shape ? lv.shape || null : null, label: name + ', grace ' + graceWords(grace) }));
      if (Number(grace) > 0) {
        const lv0 = shape ? (border.levels || []).find((l) => Number(l.grace) === 0) : null;
        out.push(Object.assign(mk(lv0 ? lv0.edges || {} : st), { colour, dashed: true,
          shape: lv0 ? lv0.shape || null : null, label: name + ' at no grace' }));
      }
    };
    if (kind === 'pca') {
      // Its boxes only when its dots are coloured by them.
      if (pcaMode(run) !== 'verified') return out;
    }
    if (kind === 'ambiguous' || kind === 'pca') {
      const b = run.borders || {};
      add(b.ds && b.ds.border, b.ds && b.ds.grace, tok('--call-ds'), 'DS');
      add(b.pspike && b.pspike.border, b.pspike && b.pspike.grace,
          tok('--call-p'), 'P-spike');
      // THE HALOS (2026-11-12): each solid border grown `reach` times about
      // the centre its gauge is measured from, dotted. Never part of the
      // frame (borderExtents skips `halo`), so a wide one is clipped.
      const H0 = kind === 'ambiguous' && run.halo;
      if (H0 && H0.centres) {
        const R = Number(H0.reach);
        for (const [side, words] of [['ds', 'DS'], ['pspike', 'P-spike']]) {
          const solid = out.find((x) => !x.dashed && x.label.indexOf(words + ' ') === 0);
          const c = H0.centres[side];
          if (!solid || !c) continue;
          const grow = (v, k) => c[k] + R * (v - c[k]);
          const lo = {}, hi = {};
          AX.forEach(([col], k) => { lo[col] = grow(solid.lo[col], k); hi[col] = grow(solid.hi[col], k); });
          let shape = null;
          if (solid.shape && solid.shape.kind === 'hull') {
            shape = Object.assign({}, solid.shape, {
              vertices: (solid.shape.vertices || []).map((v) => v.map((x, k) => grow(x, k))) });
          } else if (solid.shape && solid.shape.kind === 'ellipsoid') {
            shape = Object.assign({}, solid.shape, {
              M: solid.shape.M.map((row) => row.map((x) => x * R * R)),
              axes: solid.shape.axes.map((a) => a.map((x) => x * R)) });
          }
          out.push({ lo, hi, colour: solid.colour, dashed: true, dash: [2, 4], halo: true,
                     shape, label: words + ' halo: its border grown ' + R + '× about its centre' });
        }
      }
    } else {
      add(run.border, run.grace, kind === 'ds' ? tok('--call-ds') : tok('--call-p'),
          kind === 'ds' ? 'DS' : 'P-spike');
    }
    return out;
  }

  /* AMBIGUOUS IS PURPLE (2026-11-06: "use purple for the ambiguous ones,
     not that ugly brown"). Inside both borders the full purple, outside
     both its paler shade; the two calls keep their blue and red. */
  function colourOf(kind, cls, which) {
    const DS = tok('--call-ds'), P = tok('--call-p');
    if (kind === 'ambiguous' || kind === 'pca') {
      return cls === 'ds' ? DS : (cls === 'pspike' || cls === 'ied') ? P
        : cls === 'both' ? tok('--call-amb') : cls === 'neither' ? tok('--call-amb-2')
        // THE HALO (2026-11-12): captured, the side's colour paled toward
        // the ground; the extended zone, the paler purple; beyond both
        // halos, grey.
        : cls === 'halo_ds' ? paler(DS) : cls === 'halo_pspike' ? paler(P)
        : cls === 'halo_amb' ? tok('--call-amb-2')
        : tok('--text-3');
    }
    const grp = kind === 'ds' ? DS : P;
    if (cls === 'inside') return grp;
    if (cls === 'outside') return which === 'src' ? tok('--warn') : tok('--text-3');
    // A source event missing a number is not the grace's (2026-11-06).
    if (cls === 'partial') return tok('--text-3');
    return tok('--text-3');
  }

  /* 'partial' (2026-11-06): a border's own event missing one of the three
     numbers. The grace's count is of measured events only, so it is said
     apart from what the grace left out. */
  const CLASS_WORDS = {
    inside: 'inside the border', outside: 'outside the border',
    ds: 'inside the DS border only', pspike: 'inside the P-spike border only',
    both: 'inside both borders', neither: 'outside both borders',
    partial: 'missing a number: not judged by the grace',
    null: 'not measured',
    halo_ds: 'outside both, captured by the DS halo',
    halo_pspike: 'outside both, captured by the P-spike halo',
    halo_amb: 'outside both, in the extended Twilight Zone',
    halo_far: 'outside both, beyond both halos',
  };

  /* ==================================================================
     THE HALO (2026-11-12: "capture outside both ... some of them clearly
     fall on the P-spike side, and some clearly on the DS side ... and have
     ones that once again fall on the extended ambiguous zone"). An option
     of an Ambiguous run's Apply stage. Each event carries its gauge against
     each border (ga: DS, gb: P-spike): how far out it is in that border's
     own size, 1 on the border, 2 twice as far from its centre as the
     border reaches. Of the events outside both:
       captured     within a halo (gauge <= reach) and `margin` times
                    nearer that border than the other;
       extended     within a halo, near both: still ambiguous;
       far out      beyond both halos.
     The same rule as rcworkflow.halo_class; a saved halo is the server's.
     Tried here live, on a copy of the run; saved as the next version.
     ================================================================== */
  const HALO_DEFAULT = { reach: 2, margin: 1.5 };
  const HALO_WORDS = { halo_ds: 'captured DS', halo_pspike: 'captured P-spike',
                       halo_amb: 'extended Twilight Zone', halo_far: 'far out' };
  const AMB_KEPT = new Set(['both', 'neither', 'halo_amb', 'halo_far']);
  function haloClass(c, ga, gb, R, M) {
    if (c !== 'neither' || !finite(ga) || !finite(gb)) return c;
    if (ga <= R && gb >= M * ga) return 'halo_ds';
    if (gb <= R && ga >= M * gb) return 'halo_pspike';
    if (Math.min(ga, gb) <= R) return 'halo_amb';
    return 'halo_far';
  }
  /* The classes an Ambiguous run is told in, with its halo or without. */
  const ambClasses = (run) => (run && run.halo
    ? ['ds', 'halo_ds', 'pspike', 'halo_pspike', 'both', 'halo_amb', 'halo_far']
    : ['ds', 'pspike', 'both', 'neither']);
  const ambKept = (run) => (run && run.halo ? ['both', 'halo_amb', 'halo_far']
    : ['both', 'neither']);

  /* A colour paled toward the ground: a canvas reads any CSS colour back
     as #rrggbb, so a theme's var() or name works too. */
  const PALE = new Map();
  function paler(c, f) {
    const k = c + '|' + (f || 0.5) + '|' + tok('--bg');
    if (PALE.has(k)) return PALE.get(k);
    const g = document.createElement('canvas').getContext('2d');
    const rgb = (x) => {
      g.fillStyle = '#000'; g.fillStyle = x;
      const s = String(g.fillStyle);
      if (s[0] === '#') return [1, 3, 5].map((i) => parseInt(s.slice(i, i + 2), 16));
      const m = s.match(/[\d.]+/g) || [0, 0, 0];
      return m.slice(0, 3).map(Number);
    };
    const a = rgb(c), b = rgb(tok('--bg', '#ffffff')), t = f || 0.5;
    const out = 'rgb(' + a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(',') + ')';
    PALE.set(k, out);
    return out;
  }

  /* The Halo's state, for the run on show: on or off, its reach and
     margin, and the gauges of a run saved before runs kept them. */
  function haloState(base) {
    if (!W.halo || W.halo.base !== base) {
      const h = (base && base.halo) || null;
      W.halo = { base, on: !!h, reach: h ? Number(h.reach) : HALO_DEFAULT.reach,
                 margin: h ? Number(h.margin) : HALO_DEFAULT.margin,
                 got: W.halo && W.halo.got && W.halo.gotFor === base ? W.halo.got : null,
                 gotFor: W.halo && W.halo.gotFor === base ? base : null,
                 busy: false, err: null, view: null };
    }
    return W.halo;
  }
  function haloGauges(base) {
    const c = base.cols || {};
    if (c.ga && c.gb && base.halo_centres) {
      return { ga: c.ga, gb: c.gb, centres: base.halo_centres };
    }
    const H0 = W.halo;
    return H0 && H0.gotFor === base ? H0.got : null;
  }
  /* The run as the Halo would leave it: a copy, its classes re-sorted. A
     saved halo turned off shows the classes from before it. */
  function haloView(base) {
    if (!base || !base.borders || !base.cols || base.pools) return base;
    const S = haloState(base);
    const col = base.cols;
    const plain = col.cls_plain || col.cls;
    const gg = S.on ? haloGauges(base) : null;
    const key = S.on && gg ? S.reach + '|' + S.margin : (S.on ? 'wait' : 'off');
    if (S.view && S.view.key === key) return S.view.run;
    let run;
    if (S.on && gg) {
      const cls = plain.map((c, j) => haloClass(c, gg.ga[j], gg.gb[j], S.reach, S.margin));
      const counts = {};
      for (const c of cls) counts[String(c)] = (counts[String(c)] || 0) + 1;
      const saved = base.halo && Number(base.halo.reach) === S.reach
        && Number(base.halo.margin) === S.margin;
      run = Object.assign({}, base, {
        cols: Object.assign({}, col, { cls, ga: gg.ga, gb: gg.gb }),
        counts,
        halo: { reach: S.reach, margin: S.margin, centres: gg.centres,
                saved: !!saved, words: saved ? base.halo.words : null } });
    } else if (!S.on && col.cls_plain) {
      const counts = {};
      for (const c of plain) counts[String(c)] = (counts[String(c)] || 0) + 1;
      run = Object.assign({}, base, { cols: Object.assign({}, col, { cls: plain }),
                                      counts, halo: null });
    } else if (S.on && base.halo) {
      // A saved halo whose gauges are on their way: its own classes.
      run = Object.assign({}, base, { cols: Object.assign({}, col, {
        cls: col.cls.map((c) => (c === 'neither' ? 'halo_far' : c)) }) });
    } else {
      run = base;
    }
    S.view = { key, run };
    return run;
  }
  async function haloFetch(base) {
    const S = haloState(base);
    if (haloGauges(base) || S.busy || W.preview || !W.openId) return;
    S.busy = true;
    try {
      const d = W.data[W.openId] || {};
      const v = d.shown || d.version;
      const got = await api('/api/rootcanal/workflow/' + encodeURIComponent(W.openId)
                            + '/halo' + (v != null ? '?version=' + v : ''));
      S.got = { ga: got.ga, gb: got.gb, centres: got.centres };
      S.gotFor = base;
      S.view = null;
    } catch (e) {
      S.err = e.message;
    }
    S.busy = false;
    refresh();
  }
  async function haloSave(view) {
    const d = W.data[W.openId] || {};
    const v = d.shown || d.version;
    const S = W.halo;
    const words = view.halo ? 'reach ' + S.reach + '×, margin ' + S.margin + '×' : 'off';
    const note = window.prompt('A note for this version (the halo, ' + words
      + ', is said in it already):', '');
    if (note === null) return;
    W.busy = 'Saving the halo';
    refresh();
    try {
      const out = await apiPost('/api/rootcanal/workflow/' + encodeURIComponent(W.openId)
        + '/halo', view.halo ? { version: v, reach: S.reach, margin: S.margin, note }
        : { version: v, off: true, note });
      toast('Saved as v' + out.version + ': ' + (view.halo ? 'the halo applied.'
        : 'the halo taken off.'), 'ok', 6000);
      W.busy = null;
      await loadList();
      await loadOne(W.openId, out.version);
    } catch (e) {
      W.busy = null;
      toast('The halo could not be saved: ' + e.message, 'err', 9000);
      refresh();
    }
  }
  /* The Apply stage's Halo card: on or off, reach and margin, what each
     setting does to the events outside both, and Save. */
  function haloCard(base, run) {
    const S = haloState(base);
    if (S.on && !haloGauges(base) && !S.busy && !S.err) haloFetch(base);
    const c = run.counts || {};
    const n = (k) => (c[k] || 0).toLocaleString();
    const outside = ['neither', 'halo_ds', 'halo_pspike', 'halo_amb', 'halo_far']
      .reduce((s, k) => s + (c[k] || 0), 0);
    // While a slider moves only its number and the counts change in place
    // (rebuilding the card mid-drag would drop the drag); the pictures
    // follow when it is let go.
    const slider = (key, label, min, max, step, words) => el('label', { class: 'wf-halo-sl' }, [
      el('span', { class: 'wf-b-l', text: label }),
      el('input', { type: 'range', min, max, step, value: S[key],
        class: 'wf-halo-' + key, disabled: S.on ? null : 'disabled',
        oninput: (e) => {
          S[key] = Number(e.target.value); S.view = null;
          const out = e.target.parentNode.querySelector('b');
          if (out) out.textContent = S[key] + '×';
          const v = haloView(base), cc = v.counts || {};
          const card = e.target.closest('.wf-halo');
          for (const b of card ? card.querySelectorAll('.wf-halo-counts b[data-k]') : []) {
            b.textContent = (cc[b.dataset.k] || 0).toLocaleString();
          }
        },
        onchange: () => refresh() }),
      el('b', { text: S[key] + '×' }),
      el('span', { class: 'hint', text: words })]);
    const saved = base.halo;
    const same = saved && S.on && Number(saved.reach) === S.reach
      && Number(saved.margin) === S.margin;
    const dirty = S.on ? !same : !!saved;
    return el('div', { class: 'card wf-halo' + (S.on ? ' on' : '') }, [
      el('div', { class: 'wf-halo-head' }, [
        el('strong', { text: 'Halo' }),
        el('span', { class: 'hint', text: 'Capture the events outside both borders '
          + 'that clearly lean one way.' }),
        BARRY.ui.seg([['off', 'Off'], ['on', 'On']], S.on ? 'on' : 'off',
          (v) => { S.on = v === 'on'; S.view = null; refresh(); }, { extra: 'wf-halo-seg' }),
        saved ? BARRY.ui.chip('this version: halo ' + saved.reach + '× / ' + saved.margin + '×')
          : null,
      ].filter(Boolean)),
      el('p', { class: 'hint', text: 'Each border is grown into a dotted halo about its '
        + 'own centre. An event outside both goes to a side when it is inside that '
        + 'side’s halo and clearly nearer that border than the other, each measured in '
        + 'its own border’s size. Inside a halo but near both, it is in the extended '
        + 'Twilight Zone; beyond both halos, it is far out. Inside a border, or both, '
        + 'is left as it was.' }),
      el('div', { class: 'wf-halo-sls' }, [
        slider('reach', 'Reach', 1.1, 4, 0.1, 'how far out a halo goes, in its '
          + 'border’s size (2× = twice as far from the centre as the border reaches)'),
        slider('margin', 'Margin', 1, 3, 0.05, 'how many times nearer one border '
          + 'than the other an event must be to be captured'),
      ]),
      S.on && S.busy ? loader('Measuring each event against both borders') : null,
      S.err ? el('p', { class: 'hint wf-warn', text: 'The gauges could not be read: ' + S.err }) : null,
      S.on && run.halo ? el('div', { class: 'wf-halo-counts' }, [
        el('span', { text: 'Of ' + outside.toLocaleString() + ' outside both:' }),
        ...['halo_ds', 'halo_pspike', 'halo_amb', 'halo_far'].map((k) =>
          el('span', { class: 'wf-lg' }, [
            el('i', { class: 'wf-lg-dot', style: 'background:' + colourOf('ambiguous', k) }),
            el('span', { text: HALO_WORDS[k] }), el('b', { text: n(k), 'data-k': k })])),
      ]) : null,
      !W.preview ? el('div', { class: 'wf-halo-foot' }, [
        BARRY.ui.button({ kind: dirty ? 'primary' : 'ghost', size: 'sm', extra: 'wf-halo-save',
          text: S.on ? 'Save with this halo' : 'Save without the halo',
          disabled: !dirty || (S.on && !run.halo) || !!W.busy ? 'disabled' : null,
          title: 'The run with the halo applied, as this workflow’s next version, '
                 + 'saying so in its note.',
          onclick: () => haloSave(run) }),
        el('span', { class: 'hint', text: dirty ? 'Saving makes the next version; this one '
          + 'stays as it is.' : (saved ? 'Saved with this halo.' : 'Turn it on to try it.') }),
        // By label (2026-11-19): DS, P-spike, Twilight Zone, outside both,
        // each with what its halo captured -- picked in the bank dialog.
        saved && !dirty ? BARRY.ui.button({ kind: 'ghost', size: 'sm', extra: 'wf-halo-bank',
          text: 'Bank by label…', disabled: W.busy ? 'disabled' : null,
          title: 'Pick which labels go to the Event Bank: one is a plain entry of '
                 + 'its type, two or more one Root Canal bundle.',
          onclick: () => bankLabels('ambiguous', base) }) : null,
      ].filter(Boolean)) : el('p', { class: 'hint', text: 'Save the workflow first; the '
        + 'halo is tried on a saved run.' }),
    ].filter(Boolean));
  }
  /* ==================================================================
     BANK BY LABEL (PROJECT EVOLVE phase 1, 2026-11-19: keep every kind
     of spike, and the purple ones are the Twilight Zone). A run's events
     fall in the labels rcworkflow.BANK_LABELS names; a person ticks which
     go to the Bank. ONE label is a plain entry of its type -- for DS and
     P-spike exactly what a run has always banked, so every reader takes
     it. TWO OR MORE are one Root Canal bundle: every event says its label,
     the class it came from and whether the Halo captured it. A Verified
     run's labels are inside and outside its one border.
     ================================================================== */
  const BANK_LABELS = {
    ambiguous: [['ds', 'DS', ['ds', 'halo_ds']],
                ['pspike', 'P-spike', ['pspike', 'halo_pspike']],
                ['twilight', 'Twilight Zone', ['both', 'halo_amb']],
                ['outside', 'Outside both borders', ['neither']]],
    ds: [['ds', 'DS', ['inside']], ['outside', 'Outside the DS border', ['outside']]],
    pspike: [['pspike', 'P-spike', ['inside']],
             ['outside', 'Outside the P-spike border', ['outside']]],
  };
  const PLAIN_TYPE = { ds: 'Dentate spike', pspike: 'P-spike' };
  const labelColour = (id) => (id === 'ds' ? tok('--call-ds') : id === 'pspike'
    ? tok('--call-p') : id === 'twilight' ? tok('--call-amb') : tok('--text-3'));
  /* {id: {label, n, halo}} of a run's classes. */
  function labelCounts(kind, cls) {
    const out = {};
    for (const [id, label, classes] of BANK_LABELS[kind] || []) {
      const want = new Set(classes);
      let n = 0, h = 0;
      for (const c of cls || []) {
        if (!want.has(c)) continue;
        n += 1;
        if (String(c).indexOf('halo_') === 0) h += 1;
      }
      out[id] = { label, n, halo: h };
    }
    return out;
  }
  /* The labels as pills, and a line saying what Bank would make of the
     ones pressed. A press changes that pill and the line, nothing else.
     `onChange` hears the labels picked. */
  function labelPicker(kind, cls, initial, onChange) {
    const counts = labelCounts(kind, cls);
    const order = (BANK_LABELS[kind] || []).map(([id]) => id);
    const on = new Set((initial || []).filter((id) => counts[id] && counts[id].n));
    const say = el('p', { class: 'hint wf-bank-say' });
    const picked = () => order.filter((id) => on.has(id));
    const tell = () => {
      const ids = picked();
      const n = ids.reduce((s, id) => s + counts[id].n, 0);
      say.classList.toggle('wf-warn', !ids.length);
      say.textContent = !ids.length ? 'Pick at least one label.'
        : ids.length === 1
          ? n.toLocaleString() + ' events as one plain entry of type '
            + (PLAIN_TYPE[ids[0]] || counts[ids[0]].label) + (PLAIN_TYPE[ids[0]]
              ? ', which every ' + (ids[0] === 'ds' ? 'DS' : 'P-spike') + ' tool reads.'
              : '.')
          : n.toLocaleString() + ' events as ONE Root Canal bundle: each says its '
            + 'label, the class it came from and whether the Halo captured it. X-ray '
            + 'and the Extraction Room do not read bundles yet; bank one label for them.';
      if (onChange) onChange(ids);
    };
    const pills = order.map((id) => {
      const c = counts[id];
      const b = el('button', {
        type: 'button', class: 'pill wf-bank-l' + (on.has(id) ? ' active' : ''),
        'data-label': id, 'aria-pressed': on.has(id) ? 'true' : 'false',
        disabled: c.n ? null : 'disabled',
        title: c.n ? null : 'None of this run’s events are ' + c.label + '.',
        onclick: () => {
          if (on.has(id)) on.delete(id); else on.add(id);
          b.classList.toggle('active', on.has(id));
          b.setAttribute('aria-pressed', on.has(id) ? 'true' : 'false');
          tell();
        } }, [
        el('i', { class: 'wf-lg-dot', style: 'background:' + labelColour(id) }),
        el('span', { text: c.label }),
        el('b', { text: c.n.toLocaleString() }),
        c.halo ? el('span', { class: 'wf-bank-halo',
          text: c.halo.toLocaleString() + ' by the Halo' }) : null,
      ].filter(Boolean));
      return b;
    });
    tell();
    return {
      // The dialog's own field, as Name and Note are.
      node: BARRY.ui.field({ label: 'Labels', extra: 'wf-bank-pick',
        control: el('div', {}, [el('div', { class: 'wf-bank-labels' }, pills), say]) }),
      picked,
    };
  }
  /* The dialog's Name follows the labels until it is typed in. */
  function nameFollows(node, make) {
    let auto = null;
    return (ids) => {
      const box = node && node.closest && node.closest('.bank-dlg')
        && node.closest('.bank-dlg').querySelector('.bank-dlg-name');
      const next = ids.length ? make(ids) : null;
      if (box && next && (auto === null || box.value === auto)) box.value = next;
      if (next) auto = next;
    };
  }
  const labelWords = (kind, ids) => ids.map((id) => ((BANK_LABELS[kind] || [])
    .find(([k]) => k === id) || [])[1]).join(' + ');

  /* A saved run into the Bank by the labels ticked. `base` is the saved
     run of the version on show -- never a Halo being tried. */
  async function bankLabels(kind, base) {
    const d = W.data[W.openId] || {};
    const v = d.shown || d.version;
    const row = (W.list || []).find((r) => r.artifact_id === W.openId) || {};
    const nick = row.nickname || row.name || '';
    const h = base && base.halo;
    let follow = () => {};
    const pick = labelPicker(kind, ((base || {}).cols || {}).cls,
      [kind === 'ambiguous' ? 'ds' : kind], (ids) => follow(ids));
    const make = (ids) => labelWords(kind, ids) + ' · ' + nick + ' v' + v;
    follow = nameFollows(pick.node, make);
    await BARRY.ui.bankDialog({
      title: 'Bank ‘' + nick + '’ v' + v + ' by label',
      name: make(pick.picked()),
      what: 'Banks the events of the labels pressed below as ONE Event Bank entry for '
        + 'the whole pool.',
      extra: pick.node,
      facts: [
        h ? 'Halo on this version: reach ' + h.reach + '×, margin ' + h.margin + '×. “By '
            + 'the Halo” counts the events outside both that it put in a label.'
          : (kind === 'ambiguous' ? 'No Halo on this version.' : null),
        'Pipeline “Root Canal workflow”: a border’s call' + (h ? ' and a halo’s' : '')
          + ', not a person’s, so not marked curated.',
        'Each event says which recording and set it came from; the entry names this '
          + 'workflow version and its borders.',
        'An event missing a number is in no label, and is not banked.',
      ].filter(Boolean),
      okText: 'Bank',
      onBank: async (b) => {
        const ids = pick.picked();
        if (!ids.length) throw new Error('Pick at least one label.');
        const out = await apiPost('/api/rootcanal/workflow/' + encodeURIComponent(W.openId)
          + '/bank', { version: v, labels: ids, name: b.name, note: b.note });
        toast('Banked ' + out.n.toLocaleString() + ' events as ‘' + (out.name || b.name)
          + '’' + (out.bundle ? ', a Root Canal bundle.' : '.'), 'ok', 8000);
        BARRY.activity.log('rootcanal.workflow_bank', { artifact: W.openId, version: v,
                                                        labels: ids, entry: out.entry_id });
      },
    });
  }

  /* On the Extract stage of an Ambiguous run: what each label holds, and
     the button that banks them. */
  function labelBankCard(row, base) {
    const c = labelCounts('ambiguous', ((base || {}).cols || {}).cls);
    return el('div', { class: 'wf-bankcard' }, [
      el('strong', { text: 'To the Bank, by label' }),
      el('div', { class: 'wf-key' }, BANK_LABELS.ambiguous.map(([id, w]) =>
        el('span', { class: 'wf-lg' }, [
          el('i', { class: 'wf-lg-dot', style: 'background:' + labelColour(id) }),
          el('span', { text: w }), el('b', { text: (c[id].n || 0).toLocaleString() }),
          c[id].halo ? el('span', { class: 'hint',
            text: '(' + c[id].halo.toLocaleString() + ' by the Halo)' }) : null,
        ].filter(Boolean)))),
      el('span', { class: 'hint', text: 'Press the labels you want in the bank dialog: '
        + 'one is a plain entry of its type; two or more make one Root Canal bundle. The '
        + 'table below still banks events picked by hand.' }),
      el('div', { class: 'wf-bankcard-btns' }, [
        BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'Bank by label…',
          extra: 'wf-bank-labels-go',
          disabled: W.preview || W.busy || !base ? 'disabled' : null,
          title: W.preview ? 'Save and run the workflow first.' : null,
          onclick: () => bankLabels('ambiguous', base) }),
      ]),
    ]);
  }

  /* A Pooled PCA's dot, by the call chosen to colour it: the one pool's
     ('ds' / 'ied'), each pool's own, or the verified borders' classes. */
  function pcaMode(run) {
    return W.pcaColour === 'verified' && !(run && run.cols && run.cols.ver)
      ? 'pool' : W.pcaColour;
  }
  function pcaCls(run, p) {
    const m = pcaMode(run);
    return m === 'own' ? p.own : m === 'verified' ? p.ver : p.cls;
  }
  const dotCls = (run, kind, p) => (kind === 'pca' ? pcaCls(run, p) : p.cls);
  const PCA_WORDS = { ds: 'DS', ied: 'P-spike', pspike: 'P-spike',
    both: 'Twilight Zone: inside both borders', neither: 'outside both borders',
    null: 'not measured', undefined: 'not measured' };

  /* COLOUR BY MOUSE OR RECORDING (2026-11-06: "add to the PCA and any other
     grid view an option to visualize by mouse/recording. And have the
     colors change on the grids.") One colour per mouse, or per recording,
     on every picture of the run -- the 3D, the flat views, the PCA, each
     mouse's card, the calls' bars -- and the legend names each one with its
     colour and how many.

     The theme's --c1..--c5 are five, and a run has eighteen mice, so the
     hues are worked out: round the wheel by the golden angle, which keeps
     any two near each other in the list far apart in hue however many
     there are, at three lightnesses taken in turn -- one set for a light
     ground, one for a dark -- so the few hues that do come round close
     again (the 8th and 13th after one) differ in lightness. A colour
     belongs to its mouse or recording, by its place in the run's list
     sorted by name, so it is the same in every picture and every stage. */
  const CAT_MODES = ['mouse', 'recording'];
  let catMemo = { run: null, mode: null, dark: null, info: null };

  const natural = (a, b) => (BARRY.ui && BARRY.ui.natCompare
    ? BARRY.ui.natCompare(String(a), String(b))
    : String(a).localeCompare(String(b), undefined, { numeric: true }));

  function catMode(run, kind) {
    const m = kind === 'pca' ? pcaMode(run) : W.wfColour;
    return CAT_MODES.indexOf(m) >= 0 ? m : null;
  }

  const catKeyOf = (mode, p) => (mode === 'mouse' ? String(p.mouse || '?')
    : String(p.gid || ('#' + p.g)));

  /* Whether the page's ground is dark: its --bg, read back through a canvas
     (which writes any colour as #rrggbb), by its luminance. */
  function groundIsDark() {
    const g = groundIsDark.g
      || (groundIsDark.g = document.createElement('canvas').getContext('2d'));
    g.fillStyle = '#ffffff';
    g.fillStyle = tok('--bg', '#ffffff');
    const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i.exec(String(g.fillStyle));
    if (!m) return false;
    const [r, gg, b] = m.slice(1, 4).map((h) => parseInt(h, 16));
    return 0.2126 * r + 0.7152 * gg + 0.0722 * b < 128;
  }

  /* A colour of OKLCH -- lightness as the eye sees it, so a yellow and a
     blue at one L are one lightness -- in sRGB, its chroma brought in until
     it fits; null if it will not fit at `floor` or more. */
  function oklchRgb(L, C, hDeg, floor) {
    const h = hDeg * Math.PI / 180;
    for (let c = C; c >= floor; c -= 0.004) {
      const a = c * Math.cos(h), b = c * Math.sin(h);
      const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
      const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
      const s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
      const lin = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
                   -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
                   -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s];
      if (lin.every((v) => v >= -1e-4 && v <= 1 + 1e-4)) {
        return lin.map((v) => {
          const x = Math.min(1, Math.max(0, v));
          return Math.round(255 * (x <= 0.0031308 ? 12.92 * x
                                                   : 1.055 * x ** (1 / 2.4) - 0.055));
        });
      }
    }
    return null;
  }

  /* Checked with the dataviz validator for 18 (2026-11-06): inside the
     lightness band, chroma at least 0.10, every neighbour at least ΔE 20
     apart to the eye and at least 3:1 against the ground, light and dark;
     colour-blind separation 7 (the 6-8 band), which is why each one is
     also named, with its count, in the legend. A hue that cannot be that
     colourful at its lightness (the teals) is taken a little lighter. */
  const CAT_TIERS = { light: [0.52, 0.62, 0.45], dark: [0.54, 0.66, 0.60] };
  const CAT_BAND = { light: [0.45, 0.66], dark: [0.49, 0.67] };
  function catColour(i, dark) {
    const h = (28 + i * 137.508) % 360;
    const L0 = CAT_TIERS[dark ? 'dark' : 'light'][i % 3];
    const band = CAT_BAND[dark ? 'dark' : 'light'];
    let rgb = null;
    for (const dL of [0, 0.04, 0.08, 0.12, 0.16, -0.04]) {
      const L = L0 + dL;
      if (L < band[0] || L > band[1]) continue;
      rgb = oklchRgb(L, 0.16, h, 0.102);
      if (rgb) break;
    }
    rgb = rgb || oklchRgb(L0, 0.16, h, 0) || [128, 128, 128];
    return 'rgb(' + rgb.join(', ') + ')';
  }

  /* The run's mice or recordings, sorted by name, each with its colour and
     what it is called: a mouse by its key ('PTEN|m13' says PTEN m13), a
     recording by its member's session label. Its events and its border's
     own (the define stage) both, so a colour never moves between stages. */
  function catInfo(run, mode) {
    const dark = groundIsDark();
    if (catMemo.run === run && catMemo.mode === mode && catMemo.dark === dark) {
      return catMemo.info;
    }
    const label = new Map();
    const take = (col, mem) => {
      for (const p of pointsOf(col)) {
        const k = catKeyOf(mode, p);
        if (label.has(k)) continue;
        label.set(k, mode === 'mouse' ? String(p.mouse || 'no mouse').replace(/\|/g, ' ')
          : (mem[p.m] || {}).session_label || p.gid || 'recording ' + (p.g + 1));
      }
    };
    take(run.cols, run.members || []);
    take(run.src_cols, run.src_members || run.members || []);
    const keys = Array.from(label.keys()).sort((a, b) =>
      natural(label.get(a), label.get(b)));
    const at = new Map(keys.map((k, i) => [k, i]));
    const cols = keys.map((k, i) => catColour(i, dark));
    const none = tok('--text-3');
    const info = { mode, keys, label, at,
                   colour: (k) => (at.has(k) ? cols[at.get(k)] : none) };
    catMemo = { run, mode, dark, info };
    return info;
  }

  /* How a picture paints a dot: by its mouse or recording when one of those
     is chosen, else by its class, as it always was. Worked out once per
     picture, not once per dot. */
  function painter(run, kind, which) {
    const mode = catMode(run, kind);
    if (mode) {
      const C = catInfo(run, mode);
      return (p) => C.colour(catKeyOf(mode, p));
    }
    const memo = new Map();
    return (p) => {
      const c = dotCls(run, kind, p);
      if (!memo.has(c)) memo.set(c, colourOf(kind, c, which));
      return memo.get(c);
    };
  }

  /* The legend's line of them: each with its colour, its name and how many
     of the dots on show are its -- wrapped, never cut. */
  function catDots(run, mode, pts) {
    const C = catInfo(run, mode);
    const n = new Map();
    for (const p of pts) {
      const k = catKeyOf(mode, p);
      n.set(k, (n.get(k) || 0) + 1);
    }
    const tot = pts.length || 1;
    return C.keys.filter((k) => n.get(k)).map((k) => el('span', {
      class: 'wf-lg wf-lg-cat', 'data-cat': k }, [
      el('i', { class: 'wf-lg-dot', style: 'background:' + C.colour(k) }),
      el('span', { text: C.label.get(k) }),
      el('b', { text: n.get(k).toLocaleString() + ' · ' + pct(n.get(k) / tot) })]));
  }

  const catHead = (mode) => (mode === 'mouse' ? 'Mice' : 'Recordings');

  /* The one pool on show in a Pooled PCA, or 'all'. A pool number this run
     does not have is 'all' (2026-11-06): W.pcaShow outlived the workflow it
     was picked on, and every dot faded and none could be clicked. */
  function pcaShowOf(run) {
    const k = Number(W.pcaShow);
    return W.pcaShow === 'all' || !(k >= 0 && k < ((run && run.pools) || []).length)
      ? 'all' : String(k);
  }

  /* What a stage shows: which events, and whether each is drawn. `whole`:
     a strip's thumbnail, which never takes Show's one pool (2026-11-06). */
  function stageSet(run, kind, stage, whole) {
    if (kind === 'pca') {
      const sh = whole ? 'all' : pcaShowOf(run);
      const only = sh === 'all' ? null : Number(sh);
      return { which: 'tgt', pts: pointsOf(run.cols),
               keep: only == null ? () => true : (p) => p.src === only };
    }
    if (stage === 'define' && kind !== 'ambiguous') {
      return { which: 'src', pts: pointsOf(run.src_cols), keep: () => true };
    }
    const pts = pointsOf(run.cols);
    if (stage === 'extract') {
      const keep = kind === 'ambiguous'
        ? (p) => AMB_KEPT.has(p.cls)
        : (p) => p.cls === 'inside';
      return { which: 'tgt', pts, keep };
    }
    return { which: 'tgt', pts, keep: () => true };
  }

  /* THE PANELS FOLLOW THE STAGE (2026-11-06: "the stage switch redraws the
     3D and the three 2D views, but the panels below do not change at
     all"). What Grace, How far, Where they went, Every mouse and Averages
     are about, at the stage on show:
       define   the border's own events -- its source pool, or the
                hand-sorted sets -- inside it or left outside by the grace;
       apply    every target event, by the border;
       extract  only what is extracted: inside, or for Ambiguous inside
                both and outside both; the rest greyed or left out.
     Ambiguous has no events of its own to draw a border from (it borrows
     two), so its Define is the target's, and says so. A Pooled PCA has no
     stages and is not asked. */
  const isKept = (kind) => (kind === 'ambiguous'
    ? (p) => AMB_KEPT.has(p.cls)
    : (p) => p.cls === 'inside');

  function panelSet(run, kind, stage) {
    const own = stage === 'define' && kind !== 'ambiguous';
    const pts = pointsOf(own ? run.src_cols : run.cols);
    const kept = stage === 'extract' ? isKept(kind) : null;
    return { own, which: own ? 'src' : 'tgt', pts, kept,
             mem: (own ? run.src_members : run.members) || [],
             shown: kept ? pts.filter(kept) : pts };
  }

  /* Which events a panel is showing, in words, with how many. */
  function stageWords(run, kind, stage) {
    const S = panelSet(run, kind, stage);
    const def = shownDef() || {};
    const nm = (o) => (o && o.nickname
      ? o.nickname + (o.version != null ? ' v' + o.version : '') : '');
    const n = (x) => x.toLocaleString();
    if (S.own) {
      const s = def.source || {};
      const ne = (s.entries || []).length;
      return 'the border’s own ' + n(S.pts.length) + ' events ('
        + (s.type === 'sets' || s.entries
          ? ne + ' hand-sorted set' + (ne === 1 ? '' : 's') : nm(s) || 'its source') + ')';
    }
    if (stage === 'extract') {
      return 'the ' + n(S.shown.length) + (kind === 'ambiguous' ? ' in the Twilight Zone or outside both'
        : ' extracted') + ', of the target’s ' + n(S.pts.length);
    }
    const t = nm(run.target || def.target);
    const tw = 'the target’s ' + n(S.pts.length) + ' events' + (t ? ' (' + t + ')' : '');
    if (stage !== 'define') return tw;
    const b = run.borders || {};
    const wf = (k) => ((b[k] || {}).workflow || {}).nickname;
    return tw + '. Ambiguous has no events of its own to draw a border from: it '
      + 'borrows ' + (wf('ds') && wf('pspike') ? 'the borders of ‘' + wf('ds') + '’ and ‘'
        + wf('pspike') + '’' : 'the DS and P-spike workflows’ borders')
      + ', whose own events are on those workflows’ Define stages';
  }

  /* ==================================================================
     Canvases
     ================================================================== */
  function sized(cv, h) {
    if (!cv || !cv.isConnected) return null;
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(60, cv.clientWidth || cv.parentNode.clientWidth || 300);
    const hh = h || cv.clientHeight || 200;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(hh * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(hh * dpr);
    }
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, hh);
    return { g, w, h: hh };
  }

  const FONT = (px, bold) => (bold ? '600 ' : '') + px + 'px '
    + (tok('--font-ui', 'system-ui') || 'system-ui');

  /* Ticks at round numbers, written the way Root Canal writes them. */
  function niceTicks(lo, hi, n) {
    const span = hi - lo;
    if (!(span > 0)) return [lo];
    const raw = span / Math.max(1, n || 4);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const st = [1, 2, 2.5, 5, 10].map((m) => m * mag)
      .find((s) => span / s <= (n || 4) + 0.5) || mag * 10;
    const out = [];
    for (let v = Math.ceil(lo / st) * st; v <= hi + st * 1e-9; v += st) {
      out.push(Math.abs(v) < st * 1e-9 ? 0 : v);
    }
    return out;
  }
  const tickText = (v) => {
    const a = Math.abs(v);
    if (a >= 1000) return (v / 1000).toFixed(a >= 10000 ? 0 : 1) + 'k';
    if (a >= 10 || a === 0) return String(Math.round(v));
    return String(Math.round(v * 10) / 10);
  };

  /* A plotting frame: the box, faint grid lines at the ticks, numbers on
     both axes, and the axis names. Returns the maps from values to pixels. */
  function axes2d(g, w, h, xr, yr, xl, yl, o) {
    const opt = o || {};
    const L = opt.L != null ? opt.L : 46, B = opt.B != null ? opt.B : 34;
    const T = opt.T != null ? opt.T : 8, R = opt.R != null ? opt.R : 10;
    const X = (v) => L + ((v - xr[0]) / (xr[1] - xr[0])) * (w - L - R);
    const Y = (v) => h - B - ((v - yr[0]) / (yr[1] - yr[0])) * (h - B - T);
    g.font = FONT(10);
    g.lineWidth = 1;
    for (const t of niceTicks(xr[0], xr[1], Math.max(2, Math.floor((w - L - R) / 70)))) {
      g.strokeStyle = tok('--line-soft', tok('--line'));
      g.beginPath(); g.moveTo(X(t), T); g.lineTo(X(t), h - B); g.stroke();
      g.fillStyle = tok('--text-3');
      g.textAlign = 'center';
      g.fillText((opt.xfmt || tickText)(t), X(t), h - B + 13);
    }
    if (!opt.noY) {
      for (const t of niceTicks(yr[0], yr[1], Math.max(2, Math.floor((h - B - T) / 34)))) {
        g.strokeStyle = tok('--line-soft', tok('--line'));
        g.beginPath(); g.moveTo(L, Y(t)); g.lineTo(w - R, Y(t)); g.stroke();
        g.fillStyle = tok('--text-3');
        g.textAlign = 'right';
        g.fillText((opt.yfmt || tickText)(t), L - 5, Y(t) + 3);
      }
    }
    g.strokeStyle = tok('--line');
    g.strokeRect(L, T, w - L - R, h - B - T);
    g.fillStyle = tok('--text-2');
    g.font = FONT(10.5);
    g.textAlign = 'center';
    if (xl) g.fillText(xl, (L + w - R) / 2, h - 6);
    if (yl) {
      g.save();
      g.translate(11, (T + h - B) / 2);
      g.rotate(-Math.PI / 2);
      g.fillText(yl, 0, 0);
      g.restore();
    }
    g.textAlign = 'left';
    return { X, Y, L, B, T, R };
  }

  /* The 3D view: amplitude across, HF up, half-width into the screen.

     THE FRAME IS THE AXES, NOT A BORDER (2026-11-05: "what is the other
     faint box?"). It spans what is on show, from the lowest value to the
     highest on each axis, and carries their tick values along its front
     edges; the borders are the coloured boxes inside it. */
  function project(u, view, s, cx, cy) {
    const cyw = Math.cos(view.yaw), syw = Math.sin(view.yaw);
    const cp = Math.cos(view.pitch), sp = Math.sin(view.pitch);
    const x = u[0] * cyw - u[2] * syw;
    const z = u[0] * syw + u[2] * cyw;
    const y = u[1] * cp - z * sp;
    const d = u[1] * sp + z * cp;
    return [cx + x * s, cy - y * s, d];
  }

  function norm(v, r) {
    return ((v - r[0]) / (r[1] - r[0])) * 2 - 1;
  }

  function draw3d(cv, run, kind, stage, opt) {
    const o = opt || {};
    // At the canvas's own CSS height (2026-11-06): Pooled PCA's side 3D is
    // 446px, and a 420px bitmap stretched to it put every click ~6% off.
    const s0 = sized(cv, o.h || cv.clientHeight || 420);
    if (!s0) return;
    const { g, w, h } = s0;
    const view = o.view || W.view;
    const R = o.ranges || rangesOf(run, kind);
    // A narrow one (Pooled PCA's, beside its 2D) a little smaller, so its
    // axis names have room around it.
    const scale = Math.min(w * 0.8, h) * (o.small ? 0.36 : w < 560 ? 0.27 : 0.31)
      * (view.zoom || 1);
    const cx = w / 2, cy = h / 2 + (o.small ? 4 : 0);
    // ZOOMED AND MOVED (2026-11-12): `at` is the frame's point drawn at the
    // canvas's middle, so turning turns about what is being looked at. A
    // thumbnail's own view has none: the frame's middle.
    const at = Array.isArray(view.at) && view.at.length === 3 ? view.at : null;
    const P = at ? (a, b, c) => project([a - at[0], b - at[1], c - at[2]], view, scale, cx, cy)
                 : (a, b, c) => project([a, b, c], view, scale, cx, cy);
    // What wire3d zooms and moves by: this drawing's own numbers.
    cv.__view3 = { w, h, s: scale, cx, cy };
    const depth = (a, b, c) => P(a, b, c)[2];
    // Which edges face the viewer: the ticks go on those.
    const zf = depth(0, -1, 1) > depth(0, -1, -1) ? 1 : -1;      // front, along amp
    const xf = depth(1, -1, 0) > depth(-1, -1, 0) ? 1 : -1;      // front, along hw
    // The frame, with its back edges fainter than its front ones.
    g.lineWidth = 1;
    for (const a of [-1, 1]) for (const b of [-1, 1]) {
      for (const [p0, p1] of [[[-1, a, b], [1, a, b]], [[a, -1, b], [a, 1, b]],
                              [[a, b, -1], [a, b, 1]]]) {
        const front = (p0[2] === zf || p1[2] === zf) && (p0[0] === xf || p1[0] === xf);
        g.strokeStyle = tok('--line');
        g.globalAlpha = front ? 0.9 : 0.45;
        line(g, P(...p0), P(...p1));
      }
    }
    g.globalAlpha = 1;
    if (!o.small) {
      // A floor grid at the amplitude and half-width ticks.
      g.strokeStyle = tok('--line-soft', tok('--line'));
      g.globalAlpha = 0.5;
      for (const t of niceTicks(R.amp[0], R.amp[1], 5)) {
        const u = norm(t, R.amp);
        if (Math.abs(u) < 0.999) line(g, P(u, -1, -1), P(u, -1, 1));
      }
      for (const t of niceTicks(R.hw[0], R.hw[1], 5)) {
        const u = norm(t, R.hw);
        if (Math.abs(u) < 0.999) line(g, P(-1, -1, u), P(1, -1, u));
      }
      g.globalAlpha = 1;
      // Tick values on the three front edges, and the axis names beyond them.
      g.font = FONT(10);
      g.fillStyle = tok('--text-3');
      const tickAlong = (ticks, at, off) => {
        for (const t of ticks) {
          const q = at(t);
          if (!q) continue;
          g.fillText(tickText(t), q[0] + off[0], q[1] + off[1]);
        }
      };
      const ampEdge = (t) => { const u = norm(t, R.amp);
        return Math.abs(u) <= 1.001 ? P(u, -1, zf) : null; };
      const hwEdge = (t) => { const u = norm(t, R.hw);
        return Math.abs(u) <= 1.001 ? P(xf, -1, u) : null; };
      const hfEdge = (t) => { const u = norm(t, R.hf);
        return Math.abs(u) <= 1.001 ? P(-xf, u, zf) : null; };
      g.textAlign = 'center';
      tickAlong(niceTicks(R.amp[0], R.amp[1], 5), ampEdge, [0, 15]);
      tickAlong(niceTicks(R.hw[0], R.hw[1], 4), hwEdge, [0, 15]);
      const hfLeft = P(-xf, 0, zf)[0] < P(0, 0, 0)[0];
      g.textAlign = hfLeft ? 'right' : 'left';
      tickAlong(niceTicks(R.hf[0], R.hf[1], 4), hfEdge, [hfLeft ? -6 : 6, 3]);
      g.font = FONT(11, true);
      g.fillStyle = tok('--text-2');
      g.textAlign = 'center';
      const a0 = P(0, -1, zf), h0 = P(xf, -1, 0), f0 = P(-xf, 1, zf);
      const out = (q, dx, dy) => [q[0] + dx, q[1] + dy];
      const am = out(a0, 0, 32), hm = out(h0, 0, 32);
      // Zoomed in, an axis whose edge has left the canvas loses its name,
      // rather than having it pinned to the canvas's edge over the dots.
      const onCv = (q) => q[0] > -80 && q[0] < w + 80 && q[1] > -80 && q[1] < h + 80;
      if (onCv(am)) fitText(g, 'max amplitude · µV', am[0], am[1], w, h);
      if (onCv(hm)) fitText(g, 'half-width · ms', hm[0], hm[1], w, h);
      g.textAlign = hfLeft ? 'right' : 'left';
      if (onCv(f0)) fitText(g, 'HF power · dB', f0[0] + (hfLeft ? -6 : 6), f0[1] - 10, w, h);
      g.textAlign = 'left';
    }
    // The borders.
    for (const b of boxesOf(run, kind)) drawBox(g, b, R, P, o.small);
    // A Pooled PCA's first two components, as lines through the pool's
    // mean, two standard deviations each way: where its PCA's axes point.
    const pc = run.pca;
    if (kind === 'pca' && pc && !o.small) {
      const raw = (ax, s) => pc.mean[ax] + s * pc.sd[ax];
      for (let k = 0; k < 2; k++) {
        const c = pc.components[k];
        const end = (s) => P(norm(raw(0, s * c[0]), R.amp), norm(raw(1, s * c[1]), R.hf),
                             norm(raw(2, s * c[2]), R.hw));
        const a = end(-2), b = end(2);
        g.strokeStyle = tok('--text');
        g.lineWidth = 1.6;
        g.globalAlpha = 0.85;
        line(g, a, b, k ? [6, 4] : []);
        g.globalAlpha = 1;
        g.fillStyle = tok('--text');
        g.font = FONT(11, true);
        g.textAlign = 'center';
        fitText(g, 'PC' + (k + 1), b[0] + (b[0] >= a[0] ? 12 : -12), b[1] - 6, w, h);
        g.textAlign = 'left';
      }
      g.lineWidth = 1;
    }
    // The dots: the context first, the stage's own on top, far ones first,
    // nearer ones a little larger and brighter -- the depth cue Root Canal's
    // own space uses. A strip's thumbnail shows every pool, whatever Show
    // picked on the open one (2026-11-06).
    const set = stageSet(run, kind, stage, o.small);
    const shown = [];
    for (const p of set.pts) {
      if (!measured(p)) continue;
      const q = P(norm(p.amp, R.amp), norm(p.hf, R.hf), norm(p.hw, R.hw));
      shown.push({ p, q, keep: set.keep(p) });
    }
    shown.sort((a, b) => (a.keep - b.keep) || (a.q[2] - b.q[2]));
    let dlo = Infinity, dhi = -Infinity;
    for (const x of shown) { dlo = Math.min(dlo, x.q[2]); dhi = Math.max(dhi, x.q[2]); }
    const near = (d) => (dhi > dlo ? (d - dlo) / (dhi - dlo) : 1);
    // The picked ring only on the stage on show, never on a strip's thumbnails.
    const pick = !o.small && W.picked && W.picked.which === set.which ? W.picked.n : null;
    const paint = painter(run, kind, set.which);
    for (const x of shown) {
      const nr = near(x.q[2]);
      const r = o.small ? 1.2 : 1.8 + 1.4 * nr;
      g.globalAlpha = x.keep ? 0.45 + 0.5 * nr : 0.1;
      g.fillStyle = paint(x.p);
      g.beginPath();
      g.arc(x.q[0], x.q[1], r, 0, 6.2832);
      g.fill();
    }
    g.globalAlpha = 1;
    if (pick != null) {
      const x = shown.find((z) => z.p.n === pick);
      if (x) {
        g.strokeStyle = tok('--text');
        g.lineWidth = 2;
        g.beginPath();
        g.arc(x.q[0], x.q[1], 7, 0, 6.2832);
        g.stroke();
        g.lineWidth = 1;
      }
    }
    cv.__pick = { which: set.which, pts: shown.filter((x) => x.keep) };
  }

  /* Text kept whole inside the canvas: moved in from an edge, never cut
     off by it, whatever its alignment. */
  function fitText(g, text, x, y, w, h) {
    const tw = g.measureText(text).width;
    const al = g.textAlign;
    const left = al === 'center' ? x - tw / 2 : al === 'right' || al === 'end' ? x - tw : x;
    const shift = Math.max(4 - left, Math.min(0, (w - 4) - (left + tw)));
    g.fillText(text, x + shift, Math.max(12, Math.min((h || Infinity) - 4, y)));
  }

  /* Text in lines no wider than `room` at the font set, broken between
     words, and inside a word only when the word alone is wider: all of it,
     never cut (2026-11-06). */
  function wrapText(g, text, room) {
    const lines = [];
    let cur = '';
    for (const word of String(text).split(' ')) {
      const next = cur ? cur + ' ' + word : word;
      if (!cur || g.measureText(next).width <= room) {
        cur = next;
      } else {
        lines.push(cur);
        cur = word;
      }
      while (g.measureText(cur).width > room && cur.length > 1) {
        let k = cur.length - 1;
        while (k > 1 && g.measureText(cur.slice(0, k)).width > room) k -= 1;
        lines.push(cur.slice(0, k));
        cur = cur.slice(k);
      }
    }
    if (cur) lines.push(cur);
    return lines;
  }

  function line(g, a, b, dash) {
    g.setLineDash(dash || []);
    g.beginPath();
    g.moveTo(a[0], a[1]);
    g.lineTo(b[0], b[1]);
    g.stroke();
    g.setLineDash([]);
  }

  /* A point in the three numbers' own units, onto the canvas. */
  const P3 = (P, R, v) => P(norm(v[0], R.amp), norm(v[1], R.hf), norm(v[2], R.hw));

  /* THE SCOOP in 3D: the three ellipses through its principal axes, and two
     rings across it; THE SNAP: every edge of its faces. */
  function drawShape(g, b, R, P, small) {
    const sh = b.shape;
    g.strokeStyle = b.colour;
    g.lineWidth = b.dashed ? 1 : (small ? 1.1 : 1.5);
    const dash = b.dash || (b.dashed ? [5, 4] : []);
    if (sh.kind === 'ellipsoid') {
      const c = sh.center, A = sh.axes;
      const at = (u, v, w) => [0, 1, 2].map((k) => c[k] + u * A[0][k] + v * A[1][k] + w * A[2][k]);
      const ring = (f) => {
        let prev = null;
        for (let i = 0; i <= 48; i++) {
          const q = P3(P, R, f((i / 48) * 6.2832));
          if (prev) line(g, prev, q, dash);
          prev = q;
        }
      };
      ring((t) => at(Math.cos(t), Math.sin(t), 0));
      ring((t) => at(Math.cos(t), 0, Math.sin(t)));
      ring((t) => at(0, Math.cos(t), Math.sin(t)));
      if (!b.dashed && !small) {
        g.globalAlpha = 0.5;
        for (const z of [-0.6, 0.6]) {
          const r = Math.sqrt(1 - z * z);
          ring((t) => at(r * Math.cos(t), r * Math.sin(t), z));
        }
        g.globalAlpha = 1;
      }
      return;
    }
    const V = (sh.vertices || []).map((v) => P3(P, R, v));
    const seen = new Set();
    g.globalAlpha = b.dashed ? 0.8 : 0.75;
    for (const f of sh.faces || []) {
      for (let k = 0; k < 3; k++) {
        const a = f[k], z = f[(k + 1) % 3];
        const key = a < z ? a + ':' + z : z + ':' + a;
        if (seen.has(key) || !V[a] || !V[z]) continue;
        seen.add(key);
        line(g, V[a], V[z], dash);
      }
    }
    g.globalAlpha = 1;
  }

  /* THE SCOOP OR THE SNAP SEEN ALONG ONE AXIS, in a 2D view: an ellipse
     (its shadow on the two axes) or the outline of its corners. */
  function shape2d(g, b, ix, iy, X, Y) {
    const sh = b.shape;
    const pts = [];
    if (sh.kind === 'ellipsoid') {
      const M = sh.M, c = sh.center;
      const a = M[ix][ix], bb = M[ix][iy], d = M[iy][iy];
      if (!(a > 0)) return;
      const l11 = Math.sqrt(a), l21 = bb / l11, l22 = Math.sqrt(Math.max(d - l21 * l21, 0));
      for (let i = 0; i <= 64; i++) {
        const t = (i / 64) * 6.2832, u = Math.cos(t), v = Math.sin(t);
        pts.push([X(c[ix] + l11 * u), Y(c[iy] + l21 * u + l22 * v)]);
      }
    } else {
      const q = (sh.vertices || []).map((v) => [X(v[ix]), Y(v[iy])]).filter((p) => p.every(isFinite))
        .sort((p, r) => p[0] - r[0] || p[1] - r[1]);
      const cross = (o, a, z) => (a[0] - o[0]) * (z[1] - o[1]) - (a[1] - o[1]) * (z[0] - o[0]);
      const lower = [], upper = [];
      for (const p of q) {
        while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
        lower.push(p);
      }
      for (const p of q.slice().reverse()) {
        while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
        upper.push(p);
      }
      pts.push(...lower.slice(0, -1), ...upper.slice(0, -1));
      if (pts.length) pts.push(pts[0]);
    }
    if (pts.length < 2) return;
    g.beginPath();
    g.moveTo(pts[0][0], pts[0][1]);
    for (const p of pts.slice(1)) g.lineTo(p[0], p[1]);
    g.stroke();
  }

  function drawBox(g, b, R, P, small) {
    if (b.shape) { drawShape(g, b, R, P, small); return; }
    const lo = [norm(b.lo.amp, R.amp), norm(b.lo.hf, R.hf), norm(b.lo.hw, R.hw)];
    const hi = [norm(b.hi.amp, R.amp), norm(b.hi.hf, R.hf), norm(b.hi.hw, R.hw)];
    if (lo.concat(hi).some((v) => !isFinite(v))) return;
    const c = (i, j, k) => P(i ? hi[0] : lo[0], j ? hi[1] : lo[1], k ? hi[2] : lo[2]);
    g.strokeStyle = b.colour;
    g.lineWidth = b.dashed ? 1 : (small ? 1.3 : 2);
    const dash = b.dash || (b.dashed ? [5, 4] : []);
    // A faint fill on the solid box's floor, so it reads as a volume.
    if (!b.dashed && !small) {
      g.fillStyle = b.colour;
      g.globalAlpha = 0.06;
      g.beginPath();
      const f = [c(0, 0, 0), c(1, 0, 0), c(1, 0, 1), c(0, 0, 1)];
      g.moveTo(f[0][0], f[0][1]);
      for (const q of f.slice(1)) g.lineTo(q[0], q[1]);
      g.closePath();
      g.fill();
      g.globalAlpha = 1;
    }
    for (const a of [0, 1]) for (const d of [0, 1]) {
      line(g, c(0, a, d), c(1, a, d), dash);
      line(g, c(a, 0, d), c(a, 1, d), dash);
      line(g, c(a, d, 0), c(a, d, 1), dash);
    }
  }

  /* A 2D view of two axes, with the boxes' edges on it. */
  function draw2d(cv, run, kind, stage, xa, ya, opt) {
    const o = opt || {};
    const s0 = sized(cv, o.h || 190);
    if (!s0) return;
    const { g, w, h } = s0;
    const R = o.ranges || rangesOf(run, kind);
    const wx = AX.find((a) => a[0] === xa), wy = AX.find((a) => a[0] === ya);
    let X, Y, box;
    if (o.small) {
      const L = 3, B = 3, T = 3, Rr = 3;
      X = (v) => L + ((v - R[xa][0]) / (R[xa][1] - R[xa][0])) * (w - L - Rr);
      Y = (v) => h - B - ((v - R[ya][0]) / (R[ya][1] - R[ya][0])) * (h - B - T);
      g.strokeStyle = tok('--line');
      g.strokeRect(L, T, w - L - Rr, h - B - T);
      box = [L, T, w - L - Rr, h - B - T];
    } else {
      const F = axes2d(g, w, h, R[xa], R[ya], wx[2] + ' · ' + wx[3],
                       wy[2] + ' · ' + wy[3], { L: 44, B: 32 });
      X = F.X; Y = F.Y;
      box = [F.L, F.T, w - F.L - F.R, h - F.B - F.T];
    }
    // Nothing past the plot (2026-11-12): a dot beyond the frame, or a
    // border's grown copy, is cut at its edge, never drawn over the axes.
    g.save();
    g.beginPath();
    g.rect(box[0], box[1], box[2], box[3]);
    g.clip();
    const inBox = (q) => q[0] >= box[0] && q[0] <= box[0] + box[2]
      && q[1] >= box[1] && q[1] <= box[1] + box[3];
    const set = stageSet(run, kind, stage);
    const pts = (o.only ? set.pts.filter(o.only) : set.pts).filter(measured);
    const r = o.small ? 1 : 1.6;
    const paint = painter(run, kind, set.which);
    for (const keepPass of [false, true]) {
      for (const p of pts) {
        const k = set.keep(p);
        if (k !== keepPass) continue;
        g.globalAlpha = k ? 0.8 : 0.1;
        g.fillStyle = paint(p);
        g.beginPath();
        g.arc(X(p[xa]), Y(p[ya]), r, 0, 6.2832);
        g.fill();
      }
    }
    g.globalAlpha = 1;
    for (const b of boxesOf(run, kind)) {
      g.strokeStyle = b.colour;
      g.lineWidth = b.dashed ? 1 : (o.small ? 1.2 : 1.8);
      g.setLineDash(b.dash || (b.dashed ? [5, 4] : []));
      if (b.shape) {
        shape2d(g, b, AX.findIndex((a) => a[0] === xa), AX.findIndex((a) => a[0] === ya), X, Y);
        g.setLineDash([]);
        continue;
      }
      const x0 = X(b.lo[xa]), x1 = X(b.hi[xa]), y0 = Y(b.hi[ya]), y1 = Y(b.lo[ya]);
      if (![x0, x1, y0, y1].every(isFinite)) { g.setLineDash([]); continue; }
      g.strokeRect(x0, y0, x1 - x0, y1 - y0);
      g.setLineDash([]);
    }
    if (W.picked && W.picked.which === set.which && !o.small) {
      const p = pts.find((z) => z.n === W.picked.n);
      if (p) {
        g.strokeStyle = tok('--text');
        g.lineWidth = 2;
        g.beginPath(); g.arc(X(p[xa]), Y(p[ya]), 6, 0, 6.2832); g.stroke();
        g.lineWidth = 1;
      }
    }
    g.restore();
    // Only a dot on show can be picked: one cut off is not under the pointer.
    if (!o.small) cv.__pick = { which: set.which, pts: pts.filter((p) => set.keep(p))
      .map((p) => ({ p, q: [X(p[xa]), Y(p[ya])] })).filter((z) => inBox(z.q)) };
  }

  /* ---------- Pooled PCA ---------- */
  function pcaRanges(run) {
    const pts = pointsOf(run.cols).filter((p) => p.pc);
    const out = [];
    for (let k = 0; k < 3; k++) {
      const v = pts.map((p) => p.pc[k]).filter(finite).sort((a, b) => a - b);
      if (!v.length) { out.push([-1, 1]); continue; }
      const q = (f) => v[Math.min(v.length - 1, Math.max(0, Math.floor(f * (v.length - 1))))];
      let lo = q(0.002), hi = q(0.998);
      if (hi <= lo) { lo -= 1; hi += 1; }
      const pad = (hi - lo) * 0.06;
      out.push([lo - pad, hi + pad]);
    }
    return out;
  }
  const pcWords = (run, k) => 'PC' + (k + 1) + ' · '
    + pct((((run.pca || {}).explained) || [])[k]) + ' of the variance';
  const AX_SHORT = { amp_uV: 'amp', hf_db: 'HF', hw_ms: 'half-width' };

  /* The 2D PCA: PC1 across, PC2 up, every dot coloured by the call chosen.
     Drawn in a fixed shuffled order, so neither call sits on top of the
     other by being drawn last. The three numbers' loadings are the arrows
     from the middle (where each one pulls), and each call's centre is a
     cross. */
  function drawPca(cv, run, opt) {
    const o = opt || {};
    const s0 = sized(cv, o.h || 470);
    if (!s0) return;
    const { g, w, h } = s0;
    const R = pcaRanges(run);
    let X, Y;
    if (o.small) {
      const L = 3, B = 3, T = 3, Rr = 3;
      X = (v) => L + ((v - R[0][0]) / (R[0][1] - R[0][0])) * (w - L - Rr);
      Y = (v) => h - B - ((v - R[1][0]) / (R[1][1] - R[1][0])) * (h - B - T);
      g.strokeStyle = tok('--line');
      g.strokeRect(L, T, w - L - Rr, h - B - T);
    } else {
      const F = axes2d(g, w, h, R[0], R[1], pcWords(run, 0), pcWords(run, 1),
                       { L: 44, B: 34 });
      X = F.X; Y = F.Y;
      g.strokeStyle = tok('--line');
      line(g, [X(0), F.T], [X(0), h - F.B], [2, 3]);
      line(g, [F.L, Y(0)], [w - F.R, Y(0)], [2, 3]);
    }
    const set = stageSet(run, 'pca', 'pca', o.small);   // a thumbnail: every pool
    const pts = set.pts.filter((p) => p.pc && finite(p.pc[0]) && finite(p.pc[1]));
    const N = pts.length || 1;
    const order = pts.slice().sort((a, b) => ((a.n * 7919) % N) - ((b.n * 7919) % N));
    const r = o.small ? 1.1 : 2.4;
    const paint = painter(run, 'pca', 'tgt');
    for (const keepPass of [false, true]) {
      for (const p of order) {
        const k = set.keep(p);
        if (k !== keepPass) continue;
        g.globalAlpha = k ? (o.small ? 0.7 : 0.78) : 0.07;
        g.fillStyle = paint(p);
        g.beginPath();
        g.arc(X(p.pc[0]), Y(p.pc[1]), r, 0, 6.2832);
        g.fill();
      }
    }
    g.globalAlpha = 1;
    if (o.small) return;
    // Each call's centre -- or each mouse's, or recording's -- among the
    // dots on show.
    const cm = catMode(run, 'pca');
    const C = cm ? catInfo(run, cm) : null;
    const sums = {};
    for (const p of pts) {
      if (!set.keep(p)) continue;
      const c = cm ? catKeyOf(cm, p) : pcaCls(run, p);
      if (c == null) continue;
      const s = sums[c] || (sums[c] = [0, 0, 0]);
      s[0] += p.pc[0]; s[1] += p.pc[1]; s[2] += 1;
    }
    for (const [c, s] of Object.entries(sums)) {
      const x = X(s[0] / s[2]), y = Y(s[1] / s[2]);
      g.lineWidth = 5;
      g.strokeStyle = tok('--bg');
      line(g, [x - 9, y], [x + 9, y]); line(g, [x, y - 9], [x, y + 9]);
      g.lineWidth = 2.5;
      g.strokeStyle = C ? C.colour(c) : colourOf('pca', c, 'tgt');
      line(g, [x - 9, y], [x + 9, y]); line(g, [x, y - 9], [x, y + 9]);
    }
    g.lineWidth = 1;
    // Where each of the three numbers pulls, on these two components.
    const pc = run.pca;
    if (pc && pc.components) {
      const x0 = X(0), y0 = Y(0);
      const reach = 0.42 * Math.min(Math.abs(X(R[0][1]) - x0), Math.abs(x0 - X(R[0][0])),
                                    Math.abs(Y(R[1][1]) - y0), Math.abs(y0 - Y(R[1][0])));
      g.font = FONT(10.5, true);
      (pc.axes || []).forEach((ax, a) => {
        const dx = pc.components[0][a], dy = pc.components[1][a];
        const x1 = x0 + dx * reach, y1 = y0 - dy * reach;
        g.strokeStyle = tok('--text');
        g.globalAlpha = 0.8;
        g.lineWidth = 1.6;
        line(g, [x0, y0], [x1, y1]);
        const ang = Math.atan2(y1 - y0, x1 - x0);
        g.beginPath();
        g.moveTo(x1, y1);
        g.lineTo(x1 - 7 * Math.cos(ang - 0.4), y1 - 7 * Math.sin(ang - 0.4));
        g.lineTo(x1 - 7 * Math.cos(ang + 0.4), y1 - 7 * Math.sin(ang + 0.4));
        g.closePath();
        g.fillStyle = tok('--text');
        g.fill();
        g.globalAlpha = 1;
        g.textAlign = Math.cos(ang) >= 0 ? 'left' : 'right';
        const lx = x1 + 6 * Math.cos(ang), ly = y1 + 6 * Math.sin(ang) + 4;
        // On a ground of its own, so it reads over the dots.
        g.lineWidth = 3.5;
        g.lineJoin = 'round';
        g.strokeStyle = tok('--bg-2');
        g.strokeText(AX_SHORT[ax] || ax, lx, ly);
        g.fillText(AX_SHORT[ax] || ax, lx, ly);
      });
      g.textAlign = 'left';
      g.lineWidth = 1;
    }
    if (W.picked && W.picked.which === 'tgt') {
      const p = pts.find((z) => z.n === W.picked.n);
      if (p) {
        g.strokeStyle = tok('--text');
        g.lineWidth = 2;
        g.beginPath(); g.arc(X(p.pc[0]), Y(p.pc[1]), 7, 0, 6.2832); g.stroke();
        g.lineWidth = 1;
      }
    }
    // Every dot on show is pickable: the faded ones are the pool not on show.
    cv.__pick = { which: 'tgt', pts: pts.filter((p) => set.keep(p))
      .map((p) => ({ p, q: [X(p.pc[0]), Y(p.pc[1])] })) };
  }

  /* Each pool's events by their call, as one bar each. */
  function drawCalls(cv, run, opt) {
    const o = opt || {};
    const s0 = sized(cv, o.h || 92);
    if (!s0) return;
    const { g, w, h } = s0;
    const pools = run.pools || [];
    const pts = pointsOf(run.cols);
    // By mouse or recording, each pool's bar is its mice's, or recordings'.
    const cm = catMode(run, 'pca');
    const C = cm ? catInfo(run, cm) : null;
    const order = C ? C.keys
      : pcaMode(run) === 'verified' ? ['ds', 'pspike', 'both', 'neither', null]
                                     : ['ds', 'ied', null];
    const which = C ? (p) => catKeyOf(cm, p)
                    : (p) => (pcaCls(run, p) == null ? null : pcaCls(run, p));
    const rowH = (h - 4) / Math.max(1, pools.length);
    const bh = Math.max(6, Math.min(24, rowH - 20));
    // What it wrote and how wide, for the harness: canvas text is not in the page.
    cv.__labels = [];
    pools.forEach((pl, i) => {
      const mine = pts.filter((p) => p.src === i);
      /* The pool's name whole (2026-11-06): a long nickname ran off the
         thumbnail's edge. Smaller first, down to 8px; then onto a second
         line, its height taken from the row's bar. */
      const label = pl.nickname + ' · ' + mine.length.toLocaleString();
      const room = w - 8;
      let fs = 10.5;
      g.font = FONT(fs, true);
      while (fs > 8 && g.measureText(label).width > room) {
        fs -= 0.5;
        g.font = FONT(fs, true);
      }
      const lines = g.measureText(label).width > room ? wrapText(g, label, room) : [label];
      const lh = fs + 1.5, more = (lines.length - 1) * lh;
      const r0 = 4 + i * rowH;
      g.fillStyle = tok('--text');
      g.textAlign = 'left';
      lines.forEach((t, k) => g.fillText(t, 4, r0 + 10 + k * lh));
      cv.__labels.push({ lines, px: fs, room,
                         widest: Math.max(...lines.map((t) => g.measureText(t).width)) });
      const y = r0 + 14 + more;
      const bhi = more ? Math.max(3, Math.min(bh, rowH - 20 - more)) : bh;
      let x = 4;
      for (const c of order) {
        const n = mine.filter((p) => which(p) === c).length;
        const ww = mine.length ? (n / mine.length) * (w - 8) : 0;
        g.fillStyle = C ? C.colour(c) : colourOf('pca', c, 'tgt');
        g.globalAlpha = 0.85;
        g.fillRect(x, y, ww, bhi);
        x += ww;
      }
      g.globalAlpha = 1;
    });
  }

  const shapeOfRun = (run) => !!(run && ((run.shape && run.shape !== 'box')
    || Object.values(run.borders || {}).some((b) => b && b.border && b.border.shape
                                                     && b.border.shape !== 'box')));

  /* How far every event is from the box on one axis, in box widths:
     below 0 inside (how deep), above 0 outside (how far out). */
  function drawDist(cv, run, kind, axisIx, which, stage) {
    const s0 = sized(cv, 150);
    if (!s0) return;
    const { g, w, h } = s0;
    const key = which === 'b' ? 'db' : 'da';
    // The stage's events: the border's own in Define, only the extracted
    // in Extract (2026-11-06).
    const pts = panelSet(run, kind, stage || 'apply').shown
      .filter((p) => p[key] && finite(p[key][axisIx]));
    cv.__n = pts.length;
    const lo = -1, hi = 1.5, nb = 50;
    const bins = new Array(nb).fill(0);
    for (const p of pts) {
      const v = Math.max(lo, Math.min(hi - 1e-9, p[key][axisIx]));
      bins[Math.floor(((v - lo) / (hi - lo)) * nb)] += 1;
    }
    const top = Math.max(1, ...bins);
    const F = axes2d(g, w, h, [lo, hi], [0, top * 1.08],
                     AX[axisIx][2] + (shapeOfRun(run) ? ': distance from the border’s extent, in widths'
                                      : ': distance from the box, in box widths'),
                     'events', { L: 40, B: 32, T: 18,
                                 xfmt: (v) => (v > 0 ? '+' : '') + v });
    const col = which === 'b' || kind === 'pspike' ? tok('--call-p') : tok('--call-ds');
    for (let b = 0; b < nb; b++) {
      const v0 = lo + (b / nb) * (hi - lo), v1 = lo + ((b + 1) / nb) * (hi - lo);
      const x0 = F.X(v0), x1 = F.X(v1), y = F.Y(bins[b]);
      g.fillStyle = (v0 + v1) / 2 <= 0 ? col : tok('--text-3');
      g.globalAlpha = (v0 + v1) / 2 <= 0 ? 0.9 : 0.75;
      g.fillRect(x0 + 0.5, y, Math.max(1, x1 - x0 - 1), F.Y(0) - y);
    }
    g.globalAlpha = 1;
    g.strokeStyle = tok('--text');
    line(g, [F.X(0), F.T - 2], [F.X(0), h - F.B], [3, 3]);
    g.font = FONT(10, true);
    g.fillStyle = tok('--text-2');
    g.textAlign = 'right';
    g.fillText('inside ←', F.X(0) - 5, F.T - 5);
    g.textAlign = 'left';
    g.fillText('→ outside', F.X(0) + 5, F.T - 5);
    const nIn = pts.filter((p) => p[key][axisIx] <= 0).length;
    g.textAlign = 'right';
    g.font = FONT(10);
    g.fillText(nIn.toLocaleString() + ' in · ' + (pts.length - nIn).toLocaleString()
               + ' out on this axis', w - 12, F.T + 12);
    g.textAlign = 'left';
  }

  /* The grace sweep: how many of the target land inside, and how much of
     the border's own events the box leaves out, at every grace -- two
     y-axes, each in its own colour, the chosen grace marked and said. */
  function drawSweep(cv, run, kind, stage) {
    const s0 = sized(cv, 210);
    if (!s0) return;
    const { g, w, h } = s0;
    const sw = run.sweep || [];
    if (!sw.length) return;
    /* By the stage (2026-11-06): Define is about the border's own events,
       so the curve of how many of them it leaves out is the strong one;
       Extract is about what is kept, so the target's curve is, and the
       count kept at this run's grace is said. Apply draws both alike. */
    const wOwn = stage === 'define' ? 3.4 : stage === 'extract' ? 1.2 : 2.2;
    const wTgt = stage === 'extract' ? 3.4 : stage === 'define' ? 1.2 : 2.2;
    const aOwn = stage === 'extract' ? 0.4 : 1, aTgt = stage === 'define' ? 0.4 : 1;
    const nmax = Math.max(1, ...sw.map((s) => s.target_inside));
    const omax = Math.max(0.1, ...sw.map((s) => s.source_outside));
    const grp = kind === 'ds' ? tok('--call-ds') : tok('--call-p');
    const F = axes2d(g, w, h, [0, 0.1], [0, nmax * 1.08], 'grace',
                     'target events inside', { L: 48, R: 44, B: 32, T: 10,
                       xfmt: (v) => +(v * 100).toFixed(0) + '%' });
    const Y2 = (v) => h - F.B - (v / (omax * 1.08)) * (h - F.B - F.T);
    // The right-hand axis: the share of the border's own events left out.
    g.font = FONT(10);
    g.fillStyle = tok('--warn');
    g.textAlign = 'left';
    for (const t of niceTicks(0, omax * 1.08, 4)) {
      g.fillText(+(t * 100).toFixed(1) + '%', w - F.R + 5, Y2(t) + 3);
    }
    const path = (ys, colour, lw, alpha) => {
      g.strokeStyle = colour;
      g.lineWidth = lw;
      g.globalAlpha = alpha;
      g.beginPath();
      sw.forEach((s, k) => { const x = F.X(s.grace), y = ys(s);
                             if (k) g.lineTo(x, y); else g.moveTo(x, y); });
      g.stroke();
      g.lineWidth = 1;
      g.globalAlpha = 1;
    };
    path((s) => F.Y(s.target_inside), grp, wTgt, aTgt);
    path((s) => Y2(s.source_outside), tok('--warn'), wOwn, aOwn);
    const at = sw.reduce((a, s) => (Math.abs(s.grace - run.grace) < Math.abs(a.grace - run.grace)
                                    ? s : a), sw[0]);
    g.strokeStyle = tok('--text');
    line(g, [F.X(run.grace), F.T], [F.X(run.grace), h - F.B], [3, 3]);
    for (const [y, c, r] of [[F.Y(at.target_inside), grp, stage === 'extract' ? 6 : 4],
                             [Y2(at.source_outside), tok('--warn'), stage === 'define' ? 6 : 4]]) {
      g.fillStyle = c;
      g.beginPath(); g.arc(F.X(run.grace), y, r, 0, 6.2832); g.fill();
    }
    g.font = FONT(10.5, true);
    g.fillStyle = tok('--text');
    // Over its measured events only, as the sweep's share is (2026-11-06):
    // one missing a number is not the grace's, and read "3 of 39" by 2.7%.
    const own = pointsOf(run.src_cols).filter(measured);
    const nOut = own.filter((p) => p.cls === 'outside').length;
    const label = 'grace ' + graceWords(run.grace) + ': ' + (stage === 'define'
      ? pct(at.source_outside) + ' of its own left out (' + nOut.toLocaleString() + ' of '
        + own.length.toLocaleString() + ')'
      : stage === 'extract'
        ? (run.kept != null ? run.kept : at.target_inside).toLocaleString() + ' extracted'
        : at.target_inside.toLocaleString() + ' inside · ' + pct(at.source_outside)
          + ' of its own left out');
    cv.__label = label;
    const lx = Math.min(w - F.R - 6 - g.measureText(label).width,
                        Math.max(F.L + 6, F.X(run.grace) + 8));
    g.fillText(label, lx, F.T + 14);
    g.save();
    g.translate(w - 8, (F.T + h - F.B) / 2);
    g.rotate(Math.PI / 2);
    g.textAlign = 'center';
    g.font = FONT(10.5);
    g.fillStyle = tok('--warn');
    g.fillText('its own events left out', 0, 0);
    g.restore();
  }

  /* From mice to classes: a band per mouse and class, as wide as how many
     of its events went that way.

     BY THE STAGE (2026-11-06). Define: each mouse of the border's own
     events, to inside it or left outside by the grace -- counted here from
     the source's columns, since the server's `by_mouse` is the target's.
     Apply: every target event, by the border. Extract: the same bands, with
     what is not extracted greyed and said. A Pooled PCA has no stages. */
  function flowOf(run, kind, stage) {
    if (kind === 'pca' || !stage) {
      return { rows: run.by_mouse || [],
               classes: kind === 'ambiguous' ? ambClasses(run)
                 : kind === 'pca' ? ['ds', 'ied'] : ['inside', 'outside'],
               dim: new Set(), words: (c) => shortClass(c, kind),
               colour: (c) => colourOf(kind, c, 'tgt') };
    }
    const S = panelSet(run, kind, stage);
    const classes = kind === 'ambiguous' ? ambClasses(run)
                                         : ['inside', 'outside'];
    // Its own events missing a number: their own band, only when there are
    // any (2026-11-06), never "left outside by the grace".
    if (S.own && S.pts.some((p) => p.cls === 'partial')) classes.push('partial');
    const by = new Map();
    for (const p of S.pts) {
      const k = String(p.mouse || '?');
      const r = by.get(k) || { key: k, n: 0 };
      r.n += 1;
      r[p.cls] = (r[p.cls] || 0) + 1;
      by.set(k, r);
    }
    const rows = Array.from(by.values()).sort((a, b) => natural(a.key, b.key));
    const dim = new Set(stage !== 'extract' ? []
      : kind === 'ambiguous' ? ['ds', 'pspike'] : ['outside']);
    const words = (c) => (S.own ? (c === 'inside' ? 'inside'
      : c === 'partial' ? CLASS_WORDS.partial : 'left outside by the grace')
      : stage !== 'extract' ? shortClass(c, kind)
      : kind === 'ambiguous' ? shortClass(c, kind) + (dim.has(c) ? ': not extracted' : ': extracted')
      : c === 'inside' ? 'extracted' : 'not extracted');
    const colour = (c) => (dim.has(c) ? tok('--text-3')
      : colourOf(kind, c, S.own ? 'src' : 'tgt'));
    return { rows, classes, dim, words, colour };
  }

  function drawFlow(cv, run, kind, stage) {
    const Fl = flowOf(run, kind, stage);
    const rows = Fl.rows;
    const classes = Fl.classes;
    const s0 = sized(cv, Math.max(160, 22 * rows.length + 30));
    if (!s0) return;
    const { g, w, h } = s0;
    const total = rows.reduce((a, r) => a + (r.n || 0), 0) || 1;
    const ctot = {};
    for (const c of classes) ctot[c] = rows.reduce((a, r) => a + (r[c] || 0), 0);
    const rightText = (c) => Fl.words(c) + ' · ' + ctot[c].toLocaleString();
    // The class column as wide as its longest label: whole, never cut.
    g.font = FONT(10);
    const rw = Math.max(110, ...classes.map((c) => g.measureText(rightText(c)).width));
    const T = 26, B = 10, gap = 4;
    const span = h - T - B;
    const lx0 = 110, lx1 = 122;
    const rx1 = Math.max(lx1 + 60, w - rw - 8), rx0 = rx1 - 12;
    const usable = (n, k) => span - gap * (k - 1);
    let y = T;
    const left = rows.map((r) => {
      const hh = (r.n / total) * usable(total, rows.length);
      const o = { r, y0: y, y1: y + hh, at: y };
      y += hh + gap;
      return o;
    });
    y = T;
    const right = {};
    for (const c of classes) {
      const hh = (ctot[c] / total) * usable(total, classes.length);
      right[c] = { y0: y, y1: y + hh, at: y };
      y += hh + gap;
    }
    const scale = usable(total, rows.length) / total;
    const rscale = usable(total, classes.length) / total;
    for (const L of left) {
      for (const c of classes) {
        const n = L.r[c] || 0;
        if (!n) continue;
        const a0 = L.at, a1 = L.at + n * scale;
        const b0 = right[c].at, b1 = right[c].at + n * rscale;
        L.at = a1;
        right[c].at = b1;
        g.globalAlpha = Fl.dim.has(c) ? 0.12 : 0.32;
        g.fillStyle = Fl.colour(c);
        g.beginPath();
        g.moveTo(lx1, a0);
        g.bezierCurveTo((lx1 + rx0) / 2, a0, (lx1 + rx0) / 2, b0, rx0, b0);
        g.lineTo(rx0, b1);
        g.bezierCurveTo((lx1 + rx0) / 2, b1, (lx1 + rx0) / 2, a1, lx1, a1);
        g.closePath();
        g.fill();
      }
    }
    g.globalAlpha = 1;
    g.font = FONT(10.5, true);
    g.fillStyle = tok('--text-2');
    g.textAlign = 'right';
    g.fillText('mouse · events', lx1, 14);
    g.textAlign = 'left';
    g.fillText('where they went · events', rx0, 14);
    g.font = FONT(10);
    // Coloured by mouse, each mouse's bar is its colour.
    const Cm = catMode(run, kind) === 'mouse' ? catInfo(run, 'mouse') : null;
    const lefts = [];
    for (const L of left) {
      g.fillStyle = Cm ? Cm.colour(String(L.r.key)) : tok('--text-2');
      g.fillRect(lx0, L.y0, lx1 - lx0, Math.max(1, L.y1 - L.y0));
      g.textAlign = 'right';
      g.fillStyle = tok('--text');
      const lt = String(L.r.key).replace(/^[^|]*\|/, '') + ' · ' + L.r.n;
      lefts.push(lt);
      g.fillText(lt, lx0 - 4, (L.y0 + L.y1) / 2 + 3);
    }
    const rights = [];
    for (const c of classes) {
      const R = right[c];
      g.fillStyle = Fl.colour(c);
      g.globalAlpha = Fl.dim.has(c) ? 0.5 : 1;
      g.fillRect(rx0, R.y0, rx1 - rx0, Math.max(1, R.y1 - R.y0));
      g.globalAlpha = 1;
      g.textAlign = 'left';
      g.fillStyle = Fl.dim.has(c) ? tok('--text-3') : tok('--text');
      rights.push(rightText(c));
      g.fillText(rightText(c), rx1 + 4, (R.y0 + R.y1) / 2 + 3);
    }
    // What it says, for the harness: the canvas's text is not in the page.
    cv.__labels = { left: lefts, right: rights };
  }

  const shortClass = (c, kind) => (kind === 'pca' ? PCA_WORDS[c] : null)
    || ({ inside: 'inside', outside: 'outside', ds: 'DS only', pspike: 'P-spike only',
          both: 'both', neither: 'neither',
          partial: 'missing a number: not judged by the grace' })[c] || HALO_WORDS[c] || c;

  /* ==================================================================
     Picking a dot
     ================================================================== */
  function pickAt(cv, x, y) {
    const pk = cv.__pick;
    if (!pk) return;
    let best = null, bd = 9 * 9;
    for (const z of pk.pts) {
      const dx = z.q[0] - x, dy = z.q[1] - y;
      const d = dx * dx + dy * dy;
      if (d < bd) { bd = d; best = z; }
    }
    if (!best) return;
    W.picked = { which: pk.which, n: best.p.n };
    W.ev = null;
    W.avg = null;
    refresh();
    // Its four pictures at once, as Root Canal's own click panel does.
    const run = shownRun();
    const p = run && pickedPoint(run);
    const mem = run && ((W.picked.which === 'src' ? run.src_members : run.members) || []);
    const m = p && mem ? mem[p.m] || {} : {};
    if (p && m.event_body) loadEvent(m, p);
    // EVERY DOT IN XPLOREFINDER (2026-11-06): once its window is open, it
    // follows each dot picked, to that dot's own recording and time.
    if (p && xOpen()) openX(p);
  }

  /* Moves the 3D picture by (dx, dy) screen pixels at `s` pixels to the
     frame's unit: `at`, the point at the canvas's middle, slides along the
     screen's own two directions at the view's turn. */
  function shift3d(dx, dy, s) {
    if (!(s > 0) || !isFinite(dx) || !isFinite(dy)) return;
    const v = W.view;
    const cyw = Math.cos(v.yaw), syw = Math.sin(v.yaw);
    const cp = Math.cos(v.pitch), sp = Math.sin(v.pitch);
    const ex = [cyw, 0, -syw], ey = [-syw * sp, cp, -cyw * sp];
    const at = Array.isArray(v.at) && v.at.length === 3 ? v.at : [0, 0, 0];
    v.at = at.map((a, i) => Math.max(-3, Math.min(3, a - (dx / s) * ex[i] + (dy / s) * ey[i])));
  }

  const ZOOM3D = [0.4, 20];
  let tap3d = null;      // the last plain click on a 3D canvas: {t, x, y}

  /* Turned by dragging, on the canvas's own pointer: nothing is left
     listening on the window when the canvas is rebuilt.
     ZOOM WHERE YOU POINT (2026-11-12: "on the 3D graph you can only zoom
     into the center and not a specific region"): the wheel zooms about the
     point under the pointer, which stays where it is; shift+drag, or a drag
     with the right or middle button, moves the picture; a double-click
     puts the zoom and the move back. A plain drag still turns it, and a
     click that does not move still picks a dot. */
  function wire3d(cv, run, kind, stage) {
    // Another workflow opened: its own frame, not zoomed into the last one's.
    const key = (W.preview ? 'preview' : String(W.openId)) + '|' + kind;
    if (W.view.key !== key) { W.view.key = key; W.view.zoom = 1; W.view.at = [0, 0, 0]; }
    const home = () => {
      W.view.zoom = 1;
      W.view.at = [0, 0, 0];
      draw3d(cv, run, kind, stage);
    };
    let drag = null;
    cv.addEventListener('contextmenu', (e) => e.preventDefault());
    // No scrolling by the middle button over the picture: it moves it.
    cv.addEventListener('mousedown', (e) => { if (e.button === 1) e.preventDefault(); });
    cv.addEventListener('pointerdown', (e) => {
      if (e.button === 1) e.preventDefault();
      const move = e.shiftKey || e.button === 1 || e.button === 2;
      drag = { x: e.clientX, y: e.clientY, lx: e.clientX, ly: e.clientY,
               yaw: W.view.yaw, pitch: W.view.pitch, move, button: e.button, moved: false };
      if (move) cv.style.cursor = 'move';
      try { cv.setPointerCapture(e.pointerId); } catch (err) { /* fine */ }
    });
    cv.addEventListener('pointermove', (e) => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
      if (drag.move) {
        const v = cv.__view3;
        if (v) shift3d(e.clientX - drag.lx, e.clientY - drag.ly, v.s);
        drag.lx = e.clientX;
        drag.ly = e.clientY;
      } else {
        W.view.yaw = drag.yaw + dx * 0.008;
        W.view.pitch = Math.max(-1.45, Math.min(1.45, drag.pitch + dy * 0.008));
      }
      draw3d(cv, run, kind, stage);
    });
    const end = () => { drag = null; cv.style.cursor = ''; };
    cv.addEventListener('pointercancel', end);
    cv.addEventListener('pointerup', (e) => {
      if (!drag) return;
      const was = drag;
      end();
      if (was.moved || was.button !== 0) return;
      // A second click where the first was, soon after: a double-click,
      // seen here too, as the first may have picked a dot and so rebuilt
      // the canvas the browser's own double-click would go to.
      const now = Date.now(), t = tap3d;
      tap3d = { t: now, x: e.clientX, y: e.clientY };
      if (t && now - t.t < 450 && Math.abs(e.clientX - t.x) + Math.abs(e.clientY - t.y) < 8) {
        tap3d = null;
        home();
        return;
      }
      const b = cv.getBoundingClientRect();
      pickAt(cv, e.clientX - b.left, e.clientY - b.top);
    });
    cv.addEventListener('dblclick', (e) => { e.preventDefault(); home(); });
    cv.addEventListener('wheel', (e) => {
      e.preventDefault();
      const d = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaMode === 2 ? e.deltaY * 400 : e.deltaY;
      if (!d) return;
      const z0 = W.view.zoom || 1;
      const z1 = Math.max(ZOOM3D[0], Math.min(ZOOM3D[1],
        z0 * Math.exp(-Math.max(-120, Math.min(120, d)) * 0.0018)));
      if (z1 === z0) return;
      W.view.zoom = z1;
      // The point under the pointer stays put: everything else moves away
      // from it (in) or toward it (out) by the zoom's change.
      const v = cv.__view3;
      if (v) {
        const b = cv.getBoundingClientRect();
        const f = z1 / z0;
        shift3d((e.clientX - b.left - v.cx) * (1 - f), (e.clientY - b.top - v.cy) * (1 - f), v.s * f);
      }
      draw3d(cv, run, kind, stage);
    }, { passive: false });
  }

  function wire2d(cv) {
    cv.addEventListener('click', (e) => {
      const b = cv.getBoundingClientRect();
      pickAt(cv, e.clientX - b.left, e.clientY - b.top);
    });
  }

  /* ==================================================================
     The page
     ================================================================== */
  function node(helpers) {
    H = helpers || H;
    if (W.list === null && !W.loading) loadList();
    root = build();
    return root;
  }

  /* Only this tab's part of the page is rebuilt: the rest of Root Canal,
     and the ToolKit's feed, are left as they are. */
  function refresh() {
    if (root && root.isConnected) {
      const fresh = build();
      root.replaceWith(fresh);
      root = fresh;
      drawSoon();
    } else if (H && H.render) {
      H.render();
    }
  }

  /* The open workflow's big pictures, drawn again at their new size when the
     window changes width: a canvas only stretched would put every dot's
     click somewhere other than the dot. */
  let live = [];
  let resizeT = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeT);
    resizeT = setTimeout(() => {
      if (!root || !root.isConnected) return;
      for (const f of live) { try { f(); } catch (e) { /* a canvas that left */ } }
    }, 120);
  });

  let drawQueue = [];
  function drawAll() {
    const q = drawQueue;
    drawQueue = [];
    for (const f of q) { try { f(); } catch (e) { /* a canvas that left */ } }
  }
  const later = (f) => { drawQueue.push(f); };
  /* On the next frame, or a timer if no frame comes: a background tab, or
     the harness's virtual clock, can hold frames back as long as it likes. */
  function drawSoon() {
    requestAnimationFrame(drawAll);
    setTimeout(drawAll, 40);
  }

  /* A part that cannot be drawn says so, rather than leaving the last one
     on show as though nothing had happened. */
  function build() {
    try {
      return build_();
    } catch (e) {
      try { reportClientError('rootcanal.workflow.build', e.message, String(e && e.stack)); }
      catch (err) { /* not important */ }
      return el('div', { class: 'card wf-err-card' }, [
        el('p', { class: 'hint wf-err', text: 'The Workflow tab could not be drawn: '
          + e.message }),
      ]);
    }
  }

  function build_() {
    drawQueue = [];
    live = [];
    const box = el('div', { class: 'wf' }, [
      head(),
      W.builder ? builderCard() : null,
      W.listErr ? el('p', { class: 'hint wf-err', text: 'The workflows could not '
        + 'be listed: ' + W.listErr }) : null,
      W.list === null ? el('div', { class: 'card' }, [loader('Reading the workflows')])
                      : listCards(),
      W.preview || W.openId ? detail() : null,
    ].filter(Boolean));
    drawSoon();
    return box;
  }

  function head() {
    const arch = archived();
    const nArch = (W.list || []).filter((r) => arch[r.artifact_id]).length;
    return el('div', { class: 'card wf-head' }, [
      el('div', { class: 'wf-head-row' }, [
        el('strong', { text: 'Workflows' }),
        el('span', { class: 'hint', text: 'Define a border, apply it to a pool, '
          + 'extract what is inside. Every run is a version, pinned to the '
          + 'versions it read; what it extracts goes to the Bank as one entry.' }),
      ]),
      el('div', { class: 'wf-head-row' }, [
        BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'New workflow',
          extra: 'wf-new', onclick: () => openBuilder(null) }),
        nArch ? BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: (W.showArchived ? 'Hide' : 'Show') + ' archived · ' + nArch,
          extra: 'wf-show-arch',
          onclick: () => { W.showArchived = !W.showArchived; refresh(); } }) : null,
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Refresh',
          onclick: () => { W.list = null; W.sources = null; loadList(); } }),
      ].filter(Boolean)),
    ]);
  }

  /* ---------- the list: a strip per workflow ---------- */
  function listCards() {
    const arch = archived();
    const rows = (W.list || []).filter((r) => W.showArchived || !arch[r.artifact_id]);
    if (!rows.length) {
      return el('div', { class: 'card wf-empty' }, [
        el('p', { text: 'No workflows yet. Press New workflow: Verified dentate '
          + 'spikes first (its border is drawn around the controls), then '
          + 'Verified P-spikes (around the hand-sorted ones), then Ambiguous, '
          + 'which borrows both borders.' }),
      ]);
    }
    rows.sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind)
              || String(a.nickname).localeCompare(String(b.nickname)));
    /* IN FOLDERS (2026-11-11: "create a folder structure for the
       Workflows"): each workflow in the folder it was saved in, or the one
       it was moved to here (a shared preference); folders inside folders,
       each opened or closed as this viewer left it. Folders first, then the
       unfiled ones. */
    const tree = { kids: new Map(), rows: [] };
    for (const r of rows) {
      let at = tree;
      for (const part of folderOf(r)) {
        if (!at.kids.has(part)) at.kids.set(part, { kids: new Map(), rows: [] });
        at = at.kids.get(part);
      }
      at.rows.push(r);
    }
    const nat = (a, b) => (BARRY.ui && BARRY.ui.natCompare ? BARRY.ui.natCompare(a, b)
      : String(a).localeCompare(String(b), undefined, { numeric: true }));
    const count = (n) => n.rows.length + Array.from(n.kids.values()).reduce((a, k) => a + count(k), 0);
    const holds = (n, id) => n.rows.some((r) => r.artifact_id === id)
      || Array.from(n.kids.values()).some((k) => holds(k, id));
    const folder = (name, n, path) => {
      const key = path.join('/');
      const open = folderOpen().has(key) || (W.openId && holds(n, W.openId));
      const d = el('details', { class: 'wf-folder', 'data-folder': key, open: open || null }, [
        el('summary', {}, [el('span', { class: 'wf-folder-name', text: name }),
          el('span', { class: 'hint', text: count(n) + ' workflow' + (count(n) === 1 ? '' : 's') })]),
        el('div', { class: 'wf-folder-body' }, [
          ...Array.from(n.kids.keys()).sort(nat).map((k) => folder(k, n.kids.get(k), path.concat(k))),
          ...n.rows.map((r) => strip(r, !!arch[r.artifact_id])),
        ]),
      ]);
      d.addEventListener('toggle', () => { setFolderOpen(key, d.open); });
      return d;
    };
    return el('div', { class: 'wf-list' }, [
      ...Array.from(tree.kids.keys()).sort(nat).map((k) => folder(k, tree.kids.get(k), [k])),
      ...tree.rows.map((r) => strip(r, !!arch[r.artifact_id])),
    ]);
  }

  function folderOf(r) {
    const moved = prefOf(FOLDER_KEY)[r.artifact_id];
    if (typeof moved === 'string') return moved.split('/').map((x) => x.trim()).filter(Boolean);
    return Array.isArray(r.folder) ? r.folder : [];
  }
  function folderOpen() {
    if (!W.folderOpen) {
      W.folderOpen = new Set();
      try { JSON.parse(localStorage.getItem(FOLDER_OPEN_KEY) || '[]').forEach((k) => W.folderOpen.add(k)); }
      catch (e) { /* none */ }
    }
    return W.folderOpen;
  }
  function setFolderOpen(key, on) {
    const s = folderOpen();
    if (on) s.add(key); else s.delete(key);
    try { localStorage.setItem(FOLDER_OPEN_KEY, JSON.stringify(Array.from(s))); } catch (e) { /* fine */ }
  }
  /* Move a workflow to another folder, for everybody: "Snap/10%", or empty
     for none. Its saved folder is kept underneath. */
  function moveTo(r) {
    const now = folderOf(r).join('/');
    const got = window.prompt('Move ‘' + (r.nickname || r.name) + '’ to which folder? '
      + 'Folders inside folders with a slash (Snap/10%); empty for none.', now);
    if (got == null || got.trim() === now) return;
    BARRY.prefs.mergeKey(FOLDER_KEY, r.artifact_id, got.trim());
    refresh();
  }

  function strip(r, isArch) {
    const d = W.data[r.artifact_id];
    const run = d && d.payload && d.payload.run;
    const open = W.openId === r.artifact_id && !W.preview;
    const kind = r.kind;
    const stale = r.stale || [];
    return el('div', { class: 'card wf-strip' + (open ? ' on' : '')
                       + (isArch ? ' archived' : ''),
                       'data-wf': r.artifact_id }, [
      el('div', { class: 'wf-strip-head' }, [
        el('span', { class: 'wf-kind wf-kind-' + kind, text: KIND_WORDS[kind] || kind }),
        el('strong', { class: 'wf-name', text: r.nickname || r.name }),
        r.shape && (kind === 'ds' || kind === 'pspike')
          ? BARRY.ui.chip(SHAPE_WORD[r.shape] || r.shape, { extra: 'wf-shape' }) : null,
        BARRY.ui.chip('v' + r.version),
        r.sync && BARRY.ui.syncChip ? BARRY.ui.syncChip(r.sync) : null,
        isArch ? BARRY.ui.chip('archived', { kind: 'warn' }) : null,
        r.ran ? null : BARRY.ui.chip('not run yet'),
        r.defined_since ? BARRY.ui.chip('v' + r.defined_since + ' saved since, not run yet',
          { kind: 'warn', title: 'The pictures are v' + r.run_version + '’s run. Run it to use '
                                  + 'the newer definition.' }) : null,
        stale.length ? BARRY.ui.chip('out of date', { kind: 'warn',
          title: stale.map((s) => s.what + ' ‘' + s.nickname + '’: pinned at '
                 + s.pinned + ', newest ' + s.newest).join('\n') }) : null,
        (r.mismatch || []).length ? BARRY.ui.chip('measured differently',
          { kind: 'warn', title: r.mismatch.join('\n') }) : null,
      ].filter(Boolean)),
      el('div', { class: 'wf-stages' }, stagesOf(kind).map(([id, words]) =>
        stageCard(r, run, kind, id, words))),
      el('div', { class: 'wf-strip-foot' }, [
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Move…', extra: 'wf-move',
          title: 'Move it to another folder, for everybody', onclick: () => moveTo(r) }),
        BARRY.ui.button({ kind: open ? 'primary' : 'ghost', size: 'sm',
          text: open ? 'Open below' : 'Open', extra: 'wf-open',
          onclick: () => openWorkflow(r.artifact_id) }),
        viewOnly(kind)
          ? BARRY.ui.button({ kind: 'primary', size: 'sm',
              text: r.ran ? 'Run again' : 'Run', extra: 'wf-run',
              title: kind === 'pca'
                ? 'Make the pools one pool, cluster it, and draw its PCA. '
                  + 'Nothing is banked.'
                : 'Apply both borders to the target. Nothing is banked: tick '
                  + 'the events you want, then Bank the ticked.',
              onclick: () => runWorkflow(r, !!stale.length) })
          : BARRY.ui.button({ kind: 'primary', size: 'sm',
              text: 'Run and bank…', extra: 'wf-run-bank',
              title: 'Define the border, apply it, and bank every event inside it '
                     + 'as one Event Bank entry. A dialog says exactly what will '
                     + 'be written first.'
                     + (kind === 'pspike' ? ' The hand-sorted sets are made ready '
                        + 'first, by themselves.' : ''),
              onclick: () => runWorkflow(r, !!stale.length, { bank: true }) }),
        viewOnly(kind) ? null : BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: 'Run without banking', extra: 'wf-run',
          title: 'Define and apply, and keep the run as a version, with nothing '
                 + 'written to the Bank.',
          onclick: () => runWorkflow(r, !!stale.length, { bank: false }) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Edit',
          onclick: () => openBuilder(r) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: isArch ? 'Put back' : 'Archive', extra: 'wf-archive',
          title: 'Archived workflows leave the list for everyone, once it '
                 + 'syncs, and so do the bank entries they made. Nothing is '
                 + 'deleted; put it back from Show archived.',
          onclick: () => setArchived(r, !isArch) }),
      ].filter(Boolean)),
      viewOnly(kind) ? null : bankLine(r),
    ].filter(Boolean));
  }

  /* EXTRACT, AND WHERE IT GOES: on the Extract stage, the one place a
     person looks to bank -- what is banked, and the button that banks. */
  function bankCard(row, run, kind) {
    const word = kind === 'ds' ? 'dentate spikes' : 'P-spikes';
    if (W.preview) {
      return el('div', { class: 'wf-bankcard' }, [
        el('strong', { text: (run.kept || 0).toLocaleString() + ' verified ' + word
                             + ' would be banked' }),
        el('span', { text: 'This is a preview. Save the workflow, then press Run '
                     + 'and bank on its strip: a dialog says exactly what goes to '
                     + 'the Event Bank before anything does.' }),
        BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'Save this workflow',
          onclick: () => saveBuilder() }),
      ]);
    }
    const b = row.bank;
    const shownV = (W.data[row.artifact_id] || {}).shown;
    const thisRun = run.bank && run.bank.entry_id;
    return el('div', { class: 'wf-bankcard' + (thisRun ? ' done' : '') }, [
      el('strong', { text: thisRun
        ? 'This run is banked: ' + (run.bank.n || run.kept || 0).toLocaleString()
          + ' verified ' + word
        : (run.kept || 0).toLocaleString() + ' verified ' + word + ' extracted — '
          + 'not banked by this run' }),
      bankLine(row),
      el('div', { class: 'wf-bankcard-btns' }, [
        BARRY.ui.button({ kind: 'primary', size: 'sm',
          text: b && b.entry_id ? 'Run and bank again…' : 'Run and bank…',
          extra: 'wf-run-bank',
          title: 'Runs the workflow as it is defined and banks what is inside the '
                 + 'border. A dialog says exactly what is written first.',
          onclick: () => runWorkflow(row, !!(row.stale || []).length, { bank: true }) }),
        shownV && shownV !== row.version ? el('span', { class: 'hint', text:
          'You are looking at v' + shownV + '; the newest is v' + row.version + '.' })
          : null,
      ].filter(Boolean)),
    ]);
  }

  /* What this workflow has in the Bank, said plainly, with a door to it. */
  function bankLine(r) {
    const b = r.bank;
    if (!b || !b.entry_id) {
      return el('div', { class: 'wf-bankline none' }, [
        el('strong', { text: 'Not banked yet.' }),
        el('span', { text: 'Press Run and bank to put its extracted events in '
                     + 'the Event Bank, as one entry.' }),
      ]);
    }
    return el('div', { class: 'wf-bankline' }, [
      el('strong', { text: 'Banked' }),
      el('span', { text: (b.n || 0).toLocaleString() + ' events in ‘'
                   + (b.name || b.entry_id) + '’' + (b.version ? ', v' + b.version : '')
                   + (b.recordings ? ', from ' + b.recordings + ' recordings' : '')
                   + (r.bank_current === false ? ' — by an earlier run; the newest '
                      + 'run was not banked' : '') + '.' }),
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Open in the Event Bank',
        extra: 'wf-open-bank',
        onclick: () => (BARRY.views.eventbank && BARRY.views.eventbank.openEntry
          ? BARRY.views.eventbank.openEntry(b.entry_id) : null) }),
    ]);
  }

  function stageCard(r, run, kind, id, words) {
    const cv = el('canvas', { class: 'wf-thumb' });
    if (run && kind === 'pca') {
      later(() => (id === 'pool' ? draw3d(cv, run, kind, id, { small: true, h: 92,
        view: { yaw: -0.65, pitch: 0.42, zoom: 1 } })
        : id === 'pca' ? drawPca(cv, run, { small: true, h: 92 })
        : drawCalls(cv, run, { small: true, h: 92 })));
    } else if (run) {
      later(() => draw3d(cv, run, kind, id, { small: true, h: 92,
        view: { yaw: -0.65, pitch: 0.42, zoom: 1 } }));
    }
    const def = (W.data[r.artifact_id] || {}).payload || {};
    const dd = def.definition || r.definition || {};
    let line1 = '', line2 = '';
    if (kind === 'pca') {
      const pools = dd.pools || [];
      const c = (run && run.counts) || {};
      const ex = ((run && run.pca) || {}).explained || [];
      if (id === 'pool') {
        line1 = pools.length + ' pools made one';
        line2 = pools.map((p) => p.nickname + ' v' + p.version).join(' + ');
      } else if (id === 'pca') {
        line1 = run ? 'PC1 ' + pct(ex[0]) + ' · PC2 ' + pct(ex[1]) + ' of the variance'
                    : 'PCA of amplitude, HF power and half-width';
        line2 = run ? ((run.pca || {}).n || 0).toLocaleString() + ' events' : 'not run yet';
      } else {
        line1 = run ? 'DS ' + (c.ds || 0).toLocaleString() + ' · P-spike '
          + (c.ied || 0).toLocaleString() : 'The one pool’s calls';
        line2 = run ? 'called in the one pool' : 'not run yet';
      }
    } else if (id === 'define') {
      if (kind === 'ambiguous') {
        line1 = 'Both borders';
        line2 = ['ds', 'pspike'].map((k) => ((dd.uses || {})[k] || {}).nickname)
          .filter(Boolean).join(' + ');
      } else {
        const src = dd.source || {};
        line1 = (kind === 'ds' ? 'Around DS · ' : 'Around P-spikes · ')
                + 'grace ' + graceWords(dd.grace);
        line2 = src.type === 'sets' ? (src.entries || []).length + ' hand-sorted sets'
                                    : (src.nickname || '') + (src.version ? ' v' + src.version : '');
      }
    } else if (id === 'apply') {
      const t = dd.target || (run && run.target) || {};
      line1 = 'To ' + (t.nickname || 'the target') + (t.version ? ' v' + t.version : '');
      line2 = run ? Object.entries(run.counts || {}).map(([c, n]) => shortClass(c)
        + ' ' + n).join(' · ') : 'not run yet';
    } else {
      line1 = kind === 'ambiguous' ? 'Shown, for you to choose' : 'To the Bank';
      line2 = run ? (run.kept || 0).toLocaleString() + ' of ' + (run.n || 0).toLocaleString()
        + (kind === 'ambiguous' ? ' Twilight Zone or outside both' : ' extracted') : '—';
    }
    return el('button', { class: 'wf-stage', type: 'button',
      title: 'Open this stage in 3D',
      onclick: () => { W.stage = id; openWorkflow(r.artifact_id); } }, [
      el('span', { class: 'wf-stage-n', text: words }),
      /* NOT RUN, SAID (2026-11-05: "no visual -- what happened?"). A stage
         has a picture only once a run has made one; until then the space
         says why it is empty and what fills it. */
      run ? cv : el('span', { class: 'wf-thumb wf-thumb-empty', text: id === 'define'
        ? (kind === 'pspike' ? 'No picture yet: this workflow has not run. Run '
           + 'and bank makes the hand-sorted sets ready, then draws the border.'
           : 'No picture yet: this workflow has not run.')
        : 'No picture until it runs.' }),
      el('span', { class: 'wf-stage-l', text: line1 }),
      el('span', { class: 'hint wf-stage-l', text: line2 }),
    ]);
  }

  async function openWorkflow(id) {
    W.preview = null;
    // Show's one pool belongs to the workflow it was picked on (2026-11-06).
    if (W.openId !== id) W.pcaShow = 'all';
    W.openId = id;
    W.picked = null; W.ev = null; W.avg = null;
    const kind = ((W.list || []).find((r) => r.artifact_id === id) || {}).kind;
    if (!stagesOf(kind).some(([s]) => s === W.stage)) {
      W.stage = kind === 'pca' ? 'pca' : 'apply';
    }
    const d = W.data[id];
    refresh();
    if (!d) await loadOne(id, null);
    else refresh();
    const n = root && root.querySelector('.wf-detail');
    if (n && n.scrollIntoView) n.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  /* RUN, AND BANK ONLY WHEN ASKED (2026-11-05: "make the banking more
     explicit, not sure what to hit to bank").

     A P-spike workflow's hand-sorted sets are made ready first, by
     themselves ("have it do this part automatically"): put on the
     recording's clock, aligned and read here, each one only if it needs it.
     Then, to bank, the run is previewed and a dialog says exactly what will
     be written -- how many events, from how many recordings, into which
     entry, new or its next version -- under a name that can be changed.
     Nothing is written until its button, which says it banks, is pressed. */
  async function runWorkflow(r, fresh, opt) {
    const o = opt || {};
    if (W.busy) return;
    const nick = r.nickname || r.name;
    const dd = (((W.data[r.artifact_id] || {}).payload) || {}).definition
               || r.definition || {};
    let pinFresh = !!fresh;
    if (r.kind === 'pspike') {
      const ents = ((dd.source || {}).entries || []).map((e) => e.entry_id);
      W.busy = 'Making the hand-sorted sets ready';
      refresh();
      const ready = await prepareSets(ents, dd.target, (t) => { W.busy = t; refresh(); });
      if (ready.changed) pinFresh = true;   // the sets have new versions now
      if (ready.fails.length) {
        W.busy = null;
        toast('Not run: ' + ready.fails.length + ' hand-sorted set(s) could '
              + 'not be made ready — ' + ready.fails.join('; '), 'err', 20000);
        refresh();
        return;
      }
    }
    const bank = !viewOnly(r.kind) && o.bank !== false;
    const go = async (extra) => {
      W.busy = 'Running ‘' + nick + '’';
      refresh();
      let got;
      try {
        got = await apiPost('/api/rootcanal/workflow/'
                            + encodeURIComponent(r.artifact_id) + '/run',
                            Object.assign({ refresh: pinFresh, bank,
                                            refresh_sets: r.kind === 'pspike' }, extra || {}));
      } catch (e) {
        W.busy = null;
        refresh();
        throw e;
      }
      W.busy = null;
      const run = got.run || {};
      const b = run.bank;
      toast('‘' + nick + '’ v' + got.version + ': ' + (r.kind === 'pca'
        ? (run.n || 0).toLocaleString() + ' events from ' + (run.pools || []).length
          + ' pools made one pool — ' + ((run.counts || {}).ds || 0).toLocaleString()
          + ' DS, ' + ((run.counts || {}).ied || 0).toLocaleString() + ' P-spikes — and '
          + 'its PCA drawn. Nothing was banked.'
        : (run.kept || 0).toLocaleString()
            + ' of ' + (run.n || 0).toLocaleString()
            + (r.kind === 'ambiguous' ? ' events are in the Twilight Zone or outside both; '
               + 'nothing was banked — press Bank by label… on its Extract stage, '
               + 'or tick the ones you want and press Bank the ticked.'
               : ' events inside the border. ' + (b ? 'Banked as '
                 + (b.new ? 'a new entry' : 'v' + (b.version || '?') + ' of')
                 + ' ‘' + (b.name || b.entry_id) + '’.'
                 : 'Nothing was banked.'))
            + (run.diff && run.diff.n ? ' ' + run.diff.n + ' changed class since '
               + 'the last run.' : '')), 'ok', 12000);
      BARRY.activity.log('rootcanal.workflow_run', { artifact: r.artifact_id,
                                                     version: got.version, banked: !!b });
      delete W.data[r.artifact_id];
      W.openId = r.artifact_id;
      W.stage = r.kind === 'pca' ? 'pca' : 'extract';
      // A new run may have fewer pools than the one Show picked from.
      W.pcaShow = 'all';
      W.list = null;
      await loadList();
      await loadOne(r.artifact_id, null);
      return got;
    };
    if (!bank) {
      try { await go(); } catch (e) {
        W.busy = null;
        toast('It did not run: ' + e.message, 'err', 14000);
        refresh();
      }
      return;
    }
    // What would be banked, exactly, before anything is.
    W.busy = 'Working out what would be banked';
    refresh();
    let pv;
    try {
      const body = Object.assign({}, dd);
      // A P-spike workflow measures its sets as prepared: their newest aligned versions.
      if (body.source && body.source.type === 'sets') {
        body.source = { entries: body.source.entries.map((e) => ({ entry_id: e.entry_id })) };
      }
      if (pinFresh) {
        for (const k of ['target', 'source']) {
          if (body[k] && body[k].type !== 'sets') body[k] = Object.assign({}, body[k], { version: null });
        }
        if (body.source && body.source.type === 'sets') {
          body.source = { entries: body.source.entries.map((e) => ({ entry_id: e.entry_id })) };
        }
      }
      pv = await apiPost('/api/rootcanal/workflow/preview', body);
    } catch (e) {
      W.busy = null;
      toast('It did not run: ' + e.message, 'err', 16000);
      refresh();
      return;
    }
    W.busy = null;
    refresh();
    const run = pv.run || {};
    const kept = run.kept || 0;
    const prior = r.bank && r.bank.entry_id ? r.bank : null;
    const word = r.kind === 'ds' ? 'dentate spikes' : 'P-spikes';
    const def = pv.definition || dd;
    const src = def.source || {};
    // BY LABEL (2026-11-19): inside the border, as always, and what it
    // leaves outside, if that is wanted too.
    const pick = labelPicker(r.kind, (run.cols || {}).cls, [r.kind]);
    await BARRY.ui.bankDialog({
      title: 'Run ‘' + nick + '’ and bank',
      name: (prior && prior.name) || (KIND_WORDS[r.kind] + ' · ' + nick),
      what: 'This draws the border around ' + (src.type === 'sets'
        ? (src.entries || []).length + ' hand-sorted sets' : '‘' + src.nickname
          + '’ v' + src.version) + ' at grace ' + graceWords(def.grace)
        + ', applies it to ‘' + ((def.target || {}).nickname || '') + '’ v'
        + ((def.target || {}).version || '') + ' (' + kept.toLocaleString() + ' of '
        + (run.n || 0).toLocaleString() + ' events inside), and banks the labels '
        + 'pressed below as ONE Event Bank entry.',
      extra: pick.node,
      facts: [
        prior ? (r.kind === 'ds' ? 'DS' : 'P-spike') + ' alone continues ‘'
                + (prior.name || prior.entry_id) + '’ (entry ' + prior.entry_id + ') as '
                + 'its next version; the version before stays. A bundle is an entry of '
                + 'its own, continued by the next bundle.'
              : 'Banked as a NEW entry.',
        'Each event says which recording and set it came from.',
        'Pipeline “Root Canal workflow”: a border’s call, not a person’s, so not '
          + 'marked curated.',
        'The workflow keeps this run as its next version, and its border as a '
          + 'Root Canal border.',
      ],
      okText: 'Run and bank',
      onBank: async (b) => {
        const ids = pick.picked();
        if (!ids.length) throw new Error('Pick at least one label.');
        await go({ bank_name: b.name, bank_note: b.note, bank_labels: ids });
      },
    });
  }

  /* The hand-sorted sets, each made ready to be measured -- on the
     recording's own clock, aligned (Eye), read here -- doing only what each
     one needs. `say` hears every step. Returns the sets as they now stand,
     what could not be done, and whether anything was written. */
  async function checkSets(entries, target) {
    const got = await apiPost('/api/rootcanal/workflow/prepare', {
      entries, target: { artifact_id: (target || {}).artifact_id,
                         version: (target || {}).version } });
    return got.sets || [];
  }

  async function prepareSets(entries, target, say) {
    const fails = [];
    let changed = false;
    const tell = say || (() => {});
    let sets;
    try { sets = await checkSets(entries, target); }
    catch (e) { return { sets: [], fails: ['checking the sets — ' + e.message], changed }; }
    // 1. Onto the recording's own clock.
    for (const x of sets.filter((v) => v.clock && v.clock.retime)) {
      tell('Retiming ' + x.session_label + ' onto the recording’s clock');
      try {
        await apiPost('/api/session/retime', { path: x.path, entry_id: x.entry_id,
                                               gid: x.gid, kind: 'ied', apply: true });
        changed = true;
      } catch (e) { fails.push(x.session_label + ': retime — ' + e.message); }
    }
    if (changed) sets = await checkSets(entries, target);
    // 2. Aligned, in Eye's way, and committed as each lands.
    const need = sets.filter((v) => !v.aligned && !(v.clock && v.clock.retime));
    if (need.length) {
      tell('Aligning ' + need.length + ' hand-sorted set' + (need.length === 1 ? '' : 's')
           + ' in Eye');
      try {
        const got = await apiPost('/api/braces/batch', {
          entries: need.map((v) => ({ id: v.entry_id })), tool: 'eye' });
        const j = await waitJob((got.job || {}).id, (t) => tell('Aligning in Eye' + t));
        for (const m of j.members || []) {
          if (!m.set_id) { if (m.error) fails.push(m.label + ': align — ' + m.error); continue; }
          try {
            await apiPost('/api/braces/set/' + encodeURIComponent(m.set_id) + '/commit',
                          { apply: true });
            changed = true;
          } catch (e) { fails.push(m.label + ': commit — ' + e.message); }
        }
      } catch (e) { fails.push('align — ' + e.message); }
      sets = await checkSets(entries, target);
    }
    // 3. Read here.
    for (const x of sets.filter((v) => v.aligned && !v.read)) {
      tell('Reading ' + x.session_label);
      try {
        const got = await apiPost('/api/rootcanal/read', { entry_id: x.entry_id,
                                                           from_version: x.aligned_ref });
        if (got.job) {
          const j = await waitJob(got.job.id, (t) => tell('Reading ' + x.session_label + t));
          if (j.status !== 'done') fails.push(x.session_label + ': read — '
                                              + (j.error || j.status));
        }
      } catch (e) { fails.push(x.session_label + ': read — ' + e.message); }
    }
    sets = await checkSets(entries, target);
    for (const x of sets) {
      if (!x.aligned && !fails.some((f) => f.indexOf(x.session_label) === 0)) {
        fails.push(x.session_label + ': still not aligned');
      } else if (x.aligned && !x.read && !fails.some((f) => f.indexOf(x.session_label) === 0)) {
        fails.push(x.session_label + ': still not read here' + (x.read_why ? ' (' + x.read_why + ')' : ''));
      }
    }
    return { sets, fails, changed };
  }

  /* ==================================================================
     The open workflow (or a preview)
     ================================================================== */
  function detail() {
    const run = shownRun();
    const def = shownDef() || {};
    const kind = def.kind;
    const d = W.openId && W.data[W.openId];
    const row = (W.list || []).find((r) => r.artifact_id === W.openId) || {};
    if (!run) {
      return el('div', { class: 'card wf-detail' }, [
        el('div', { class: 'wf-detail-head' }, [
          el('strong', { text: W.preview ? 'Preview' : (row.nickname || '') }),
          BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Close',
            onclick: () => { W.openId = null; W.preview = null; refresh(); } }),
        ]),
        d ? el('p', { class: 'hint', text: 'Defined, not run yet. Press Run on '
                      + 'its strip.' }) : loader('Opening the workflow'),
        d ? lineage(row, d) : null,
      ].filter(Boolean));
    }
    if (kind === 'pca') return pcaDetail(run, d, row);
    const shownV = d && (d.shown || d.version);
    const stages = STAGES.filter(([id]) => !(kind === 'ambiguous' && id === 'define'
                                            && false));
    const big = el('canvas', { class: 'wf-3d' });
    const st = W.stage;
    later(() => { draw3d(big, run, kind, st); });
    wire3d(big, run, kind, st);
    live.push(() => draw3d(big, run, kind, st));
    const R = rangesOf(run, kind);
    const flats = [['amp', 'hf'], ['hf', 'hw'], ['amp', 'hw']].map(([xa, ya]) => {
      const cv = el('canvas', { class: 'wf-2d' });
      later(() => draw2d(cv, run, kind, st, xa, ya, { ranges: R }));
      live.push(() => draw2d(cv, run, kind, st, xa, ya, { ranges: R }));
      wire2d(cv);
      return cv;
    });
    return el('div', { class: 'card wf-detail' }, [
      el('div', { class: 'wf-detail-head' }, [
        el('span', { class: 'wf-kind wf-kind-' + kind, text: KIND_WORDS[kind] }),
        el('strong', { text: W.preview ? 'Preview · nothing saved'
                       : (row.nickname || '') + ' · v' + shownV }),
        W.busy ? BARRY.ui.chip(W.busy) : null,
        BARRY.ui.seg(stages.map(([id, w]) => [id, w,
          id === 'define' ? 'What the border is drawn from, and the box.'
          : id === 'apply' ? 'The target, every event by the border.'
          : 'What comes out.']), W.stage,
          // An average is of one stage's events: it goes with the stage.
          (v) => { W.stage = v; W.picked = null; W.ev = null; W.avg = null; refresh(); },
          { extra: 'wf-stage-seg' }),
        W.preview ? BARRY.ui.button({ kind: 'primary', size: 'sm',
          text: 'Save this workflow', onclick: () => saveBuilder() }) : null,
        H && H.openPool && !W.preview ? BARRY.ui.button({ kind: 'ghost', size: 'sm',
          text: 'Open in Pooled', extra: 'wf-to-pooled',
          title: 'The same picture in Pooled, with the border applied: its '
                 + 'click panel, averages, lasso and Xplorefinder.',
          onclick: () => toPooled(run, kind) }) : null,
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Close',
          onclick: () => { W.openId = null; W.preview = null; refresh(); } }),
      ].filter(Boolean)),
      // Colour by (2026-11-06): the call, as always, or each mouse or
      // recording in a colour of its own, on every picture below.
      el('div', { class: 'wf-detail-head' }, [
        el('span', { class: 'wf-b-l wf-pca-l', text: 'Colour by' }),
        BARRY.ui.seg(WF_COLOURS.map(([m, w]) => [m, w,
          m === 'call' ? 'Inside or outside the border, in the call’s colours.'
          : 'Each ' + m + ' in a colour of its own; the boxes say where the '
            + 'border is.']), W.wfColour,
          (v) => { W.wfColour = v; refresh(); }, { extra: 'wf-wf-colour' }),
      ]),
      el('p', { class: 'hint wf-rule', text: ruleWords(run, kind) }),
      (run.mismatch || []).length ? el('p', { class: 'hint wf-warn',
        text: 'Measured differently: ' + run.mismatch.join('; ') + '.' }) : null,
      d && d.newer && !W.preview ? el('p', { class: 'hint wf-warn', text: 'Showing v'
        + d.shown + ', the newest run. v' + d.newer + ' changed the definition and has '
        + 'not run yet: run it to see what it gives.' }) : null,
      d && (d.stale || []).length && !W.preview ? el('p', { class: 'hint wf-warn',
        text: 'Out of date: ' + d.stale.map((s) => s.what + ' ‘' + s.nickname
          + '’ is at ' + s.newest + ', this pins ' + s.pinned).join('; ')
          + '. Run with the newest inputs to make the next version from them.' })
        : null,
      legend(run, kind, W.stage),
      // THE HALO (2026-11-12), on the Apply stage of an Ambiguous run.
      kind === 'ambiguous' && W.stage === 'apply' ? haloCard(shownBase(), run) : null,
      W.stage === 'extract' && kind !== 'ambiguous' ? bankCard(row, run, kind) : null,
      W.stage === 'extract' && kind === 'ambiguous' ? labelBankCard(row, shownBase()) : null,
      el('div', { class: 'wf-views' }, [
        el('div', { class: 'wf-3d-wrap' }, [big,
          el('span', { class: 'hint', text: 'Drag to turn it. Scroll to zoom in on '
                       + 'the spot under the pointer; shift+drag or right-drag to move '
                       + 'it; double-click to put it back. Click a dot to look at it.' })]),
        el('div', { class: 'wf-2d-col' }, flats),
      ]),
      inspector(run, kind),
      /* Every panel follows the stage on show (2026-11-06), and says which
         events it is showing. */
      el('div', { class: 'wf-panels', 'data-stage': st }, [
        kind !== 'ambiguous' ? panel('Grace', 'What a different grace would '
          + 'have done, before choosing one. The dashed line is this run’s.',
          el('div', {}, [
            el('div', { class: 'wf-key' }, [
              el('span', { class: 'wf-lg' + (st === 'define' ? ' wf-lg-dim' : '') }, [
                el('i', { class: 'wf-lg-line',
                  style: 'background:' + (kind === 'ds' ? tok('--call-ds') : tok('--call-p')) }),
                el('span', { text: 'target events inside the box (left axis)' })]),
              el('span', { class: 'wf-lg' + (st === 'extract' ? ' wf-lg-dim' : '') }, [
                el('i', { class: 'wf-lg-line', style: 'background:' + tok('--warn') }),
                el('span', { text: 'the border’s own events it leaves out (right axis)' })]),
            ]),
            (() => { const cv = el('canvas', { class: 'wf-sweep' });
                     later(() => drawSweep(cv, run, kind, st)); return cv; })(),
          ]), st === 'define'
            ? 'Showing ' + stageWords(run, kind, st) + ': the strong curve is how many '
              + 'of them the box leaves out at each grace.'
            : st === 'extract'
              ? 'Showing ' + stageWords(run, kind, st) + ': the strong curve is how many '
                + 'the box keeps at each grace, and this run’s is marked.'
              : 'Showing ' + stageWords(run, kind, st) + ', and the border’s own '
                + pointsOf(run.src_cols).length.toLocaleString() + ': both curves.') : null,
        panel('How far from the border', 'On each axis, each event’s distance '
          + 'from the box’s edge, in box widths: 0 is the edge, −1 the far side of '
          + 'the box, +0.5 half a box beyond it. Coloured: inside.',
          distPanel(run, kind, st), 'Showing ' + stageWords(run, kind, st) + '.'),
        panel('Where they went', 'Each mouse’s events, left, to where the border '
          + 'put them, right; each band as wide as how many.' + (st === 'extract'
            ? ' What is not extracted is greyed.' : ''), (() => {
            const cv = el('canvas', { class: 'wf-flow' });
            later(() => drawFlow(cv, run, kind, st)); return cv; })(),
          'Showing ' + stageWords(run, kind, st) + '.'),
        kind === 'ambiguous' ? panel('Conflicts', 'Events inside both borders '
          + 'are the Twilight Zone (decided 2026-11-05), drawn purple.',
          venn(run)) : null,
        panel('Every mouse', 'Each mouse on its own: amplitude across, HF up, '
          + 'the border’s box drawn in; under it how many '
          + (st === 'extract' ? 'were extracted, the rest faded.'
             : st === 'define' && kind !== 'ambiguous' ? 'of its own are inside the box.'
             : 'came out of how many.'),
          perMouse(run, kind, R, st), 'Showing ' + stageWords(run, kind, st) + '.'),
        panel('Averages', 'The four pictures averaged over a class, from every '
          + 'recording whose read is on this machine.', averages(run, kind, st),
          'Showing ' + stageWords(run, kind, st) + '.'),
      ].filter(Boolean)),
      kind === 'ambiguous' && W.stage !== 'define' ? ambTable(run) : null,
      d ? lineage(row, d) : null,
    ].filter(Boolean));
  }

  /* ---------- a Pooled PCA, open: the 2D PCA, the 3D beside it ---------- */
  function pcaDetail(run, d, row) {
    const shownV = d && (d.shown || d.version);
    const pools = run.pools || [];
    const big = el('canvas', { class: 'wf-pca' });
    later(() => drawPca(big, run));
    wire2d(big);
    const side = el('canvas', { class: 'wf-3d wf-3d-side' });
    later(() => draw3d(side, run, 'pca', 'pca'));
    wire3d(side, run, 'pca', 'pca');
    live.push(() => drawPca(big, run), () => draw3d(side, run, 'pca', 'pca'));
    const modes = PCA_COLOURS.filter(([m]) => m !== 'verified' || (run.cols && run.cols.ver));
    const gmm = run.gmm || {};
    return el('div', { class: 'card wf-detail' }, [
      el('div', { class: 'wf-detail-head' }, [
        el('span', { class: 'wf-kind wf-kind-pca', text: KIND_WORDS.pca }),
        el('strong', { text: W.preview ? 'Preview · nothing saved'
                       : (row.nickname || '') + ' · v' + shownV }),
        W.busy ? BARRY.ui.chip(W.busy) : null,
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Close',
          onclick: () => { W.openId = null; W.preview = null; refresh(); } }),
      ].filter(Boolean)),
      el('div', { class: 'wf-detail-head' }, [
        el('span', { class: 'wf-b-l wf-pca-l', text: 'Colour by' }),
        BARRY.ui.seg(modes.map(([m, w]) => [m, w]), pcaMode(run),
          (v) => { W.pcaColour = v; refresh(); }, { extra: 'wf-pca-colour' }),
        el('span', { class: 'wf-b-l wf-pca-l', text: 'Show' }),
        BARRY.ui.seg([['all', 'every pool']].concat(pools.map((p, i) => [String(i), p.nickname])),
          pcaShowOf(run), (v) => { W.pcaShow = v; W.picked = null; W.ev = null; refresh(); },
          { extra: 'wf-pca-show' }),
      ]),
      el('p', { class: 'hint wf-rule', text: pcaRule(run) }),
      (run.overlap || []).length ? el('p', { class: 'hint wf-warn', text: run.overlap.length
        + ' recording' + (run.overlap.length === 1 ? ' is' : 's are') + ' in more than one '
        + 'of the pools, and pooled once: ' + run.overlap.join(', ') + '.' }) : null,
      d && d.newer && !W.preview ? el('p', { class: 'hint wf-warn', text: 'Showing v'
        + d.shown + ', the newest run. v' + d.newer + ' changed the definition and has '
        + 'not run yet: run it to see what it gives.' }) : null,
      d && (d.stale || []).length && !W.preview ? el('p', { class: 'hint wf-warn',
        text: 'Out of date: ' + d.stale.map((s) => s.what + ' ‘' + s.nickname
          + '’ is at ' + s.newest + ', this pins ' + s.pinned).join('; ')
          + '. Run again to make the next version from the newest.' }) : null,
      pcaLegend(run),
      el('div', { class: 'wf-views wf-views-pca' }, [
        el('div', { class: 'wf-3d-wrap' }, [big,
          el('span', { class: 'hint', text: 'Click any dot to look at it. Open in '
            + 'Xplorefinder shows it in its recording; while that window is open, '
            + 'every dot you click moves it there.' })]),
        el('div', { class: 'wf-3d-wrap' }, [
          el('strong', { class: 'wf-side-h', text: 'The same events in 3D' }), side,
          el('span', { class: 'hint', text: 'Amplitude, HF power and half-width as '
            + 'measured, coloured the same. The two lines are PC1 (solid) and PC2 '
            + '(dashed). Drag to turn it. Scroll to zoom in on the spot under the '
            + 'pointer; shift+drag or right-drag to move it; double-click to put it '
            + 'back. Click a dot to look at it.' })]),
      ]),
      inspector(run, 'pca'),
      el('div', { class: 'wf-panels' }, [
        panel('What each component is', 'How much of the spread each component '
          + 'holds, and how strongly each of the three numbers counts in it: '
          + '+1 or −1 is all of it, 0 none.', loadings(run)),
        panel('Each pool', 'Every pool’s events by what Colour by chose above: '
          + 'a call, or its mice or recordings.',
          el('div', {}, [byPool(run),
            gmm.verdict ? el('details', { class: 'wf-diff-box' }, [
              el('summary', { text: 'Is the one pool two groups? '
                + (gmm.support || '') }),
              el('p', { class: 'hint', text: gmm.verdict })]) : null].filter(Boolean))),
        panel('Where they went', 'Each mouse’s events, left, to the one pool’s '
          + 'call, right; each band as wide as how many.', (() => {
            const cv = el('canvas', { class: 'wf-flow' });
            later(() => drawFlow(cv, run, 'pca')); return cv; })()),
        panel('Every mouse', 'Each mouse on its own: amplitude across, HF up, '
          + 'coloured as chosen above.', perMouse(run, 'pca', rangesOf(run, 'pca'))),
      ]),
      d ? lineage(row, d) : null,
    ].filter(Boolean));
  }

  function pcaRule(run) {
    const pools = run.pools || [];
    const pc = run.pca || {};
    const ex = pc.explained || [];
    return pools.map((p) => '‘' + p.nickname + '’ v' + p.version + ' ('
      + (p.n || 0).toLocaleString() + ' events, ' + p.members + ' recordings)')
      .join(' and ') + ' made one pool of ' + (run.n || 0).toLocaleString()
      + ' events and clustered again, the way Pooled clusters a pool. '
      + (run.pool_rule || '') + ' The PCA is of the three numbers, each z-scored '
      + 'over the one pool: PC1 holds ' + pct(ex[0]) + ' of the spread, PC2 '
      + pct(ex[1]) + ', PC3 ' + pct(ex[2])
      + (pc.n_missing ? '; ' + pc.n_missing + ' event' + (pc.n_missing === 1 ? ' is' : 's are')
         + ' missing a number and not in it' : '') + '.';
  }

  /* The calls on show, with how many of each, and every other mark. */
  function pcaLegend(run) {
    const set = stageSet(run, 'pca', 'pca');
    const shown = set.pts.filter((p) => set.keep(p));
    const n = {};
    for (const p of shown) { const c = pcaCls(run, p); n[c] = (n[c] || 0) + 1; }
    const tot = shown.length || 1;
    const dot = (c, text) => el('span', { class: 'wf-lg' }, [
      el('i', { class: 'wf-lg-dot', style: 'background:' + colourOf('pca', c, 'tgt') }),
      el('span', { text }),
      el('b', { text: (n[c] || 0).toLocaleString() + ' · ' + pct((n[c] || 0) / tot) })]);
    const mode = pcaMode(run);
    const cm = catMode(run, 'pca');
    // By mouse or recording: each one, with how many of the dots drawn are
    // its (an unmeasured event is not drawn, so not counted).
    const dots = cm ? catDots(run, cm, shown.filter((p) => p.pc && finite(p.pc[0])
                                                    && finite(p.pc[1])))
      : mode === 'verified'
      ? [dot('ds', 'inside the DS border only'), dot('pspike', 'inside the P-spike border only'),
         dot('both', 'Twilight Zone: inside both'), dot('neither', 'outside both')]
      : [dot('ds', 'DS'), dot('ied', 'P-spike')];
    if (!cm && (n.null || n.undefined)) dots.push(dot(null, 'not measured, so not drawn'));
    const marks = [
      el('span', { class: 'wf-lg' }, [el('span', { class: 'wf-lg-cross', text: '+' }),
        el('span', { text: cm ? 'each ' + cm + '’s centre' : 'each call’s centre' })]),
      el('span', { class: 'wf-lg' }, [el('span', { class: 'wf-lg-arrow', text: '→' }),
        el('span', { text: 'where amplitude, HF power and half-width pull on PC1 and PC2' })]),
    ];
    const boxes = boxesOf(run, 'pca').map((b) => el('span', { class: 'wf-lg' }, [
      el('i', { class: 'wf-lg-box' + (b.dashed ? ' dashed' : ''),
                style: 'border-color:' + b.colour }),
      el('span', { text: b.label + ' (3D view)' })]));
    return el('div', { class: 'wf-legend' }, [
      el('div', { class: 'wf-legend-row' }, [el('span', { class: 'wf-lg-h',
        text: cm ? catHead(cm) : 'Dots' })].concat(dots)),
      el('div', { class: 'wf-legend-row' }, [el('span', { class: 'wf-lg-h', text: 'Marks' })]
        .concat(marks, boxes)),
      pcaShowOf(run) !== 'all' ? el('div', { class: 'wf-legend-row' }, [
        el('span', { class: 'wf-lg-h', text: 'Faded' }),
        el('span', { class: 'hint', text: 'the other pool' + ((run.pools || []).length > 2
          ? 's' : '') + ', not on show' })]) : null,
    ].filter(Boolean));
  }

  function loadings(run) {
    const pc = run.pca || {};
    const axes = pc.axes || [];
    const word = { amp_uV: 'amplitude', hf_db: 'HF power', hw_ms: 'half-width' };
    return el('table', { class: 'wf-cut' }, [
      el('tr', {}, [el('th', { text: '' }), el('th', { text: 'of the spread' })]
        .concat(axes.map((a) => el('th', { text: word[a] || a })),
                [el('th', { text: 'in words' })])),
      ...(pc.components || []).map((c, k) => el('tr', {}, [
        el('th', { text: 'PC' + (k + 1) }),
        el('td', { text: pct((pc.explained || [])[k]) }),
        ...c.map((v) => el('td', { text: (v > 0 ? '+' : '') + v.toFixed(2) })),
        el('td', { text: 'higher with ' + axes.map((a, i) => [a, c[i]])
          .filter(([, v]) => Math.abs(v) >= 0.3)
          .map(([a, v]) => (v > 0 ? 'more ' : 'less ') + (word[a] || a)).join(', ') }),
      ])),
    ]);
  }

  function byPool(run) {
    const pts = pointsOf(run.cols);
    const mode = pcaMode(run);
    const cm = catMode(run, 'pca');
    if (cm) {
      // By mouse or recording: each pool's, in their colours, with how many.
      return el('table', { class: 'wf-cut wf-bypool-cat' }, [
        el('tr', {}, [el('th', { text: 'pool' }), el('th', { text: 'events' }),
                      el('th', { text: cm === 'mouse' ? 'its mice' : 'its recordings' })]),
        ...(run.pools || []).map((pl, i) => {
          const mine = pts.filter((p) => p.src === i);
          return el('tr', {}, [el('th', { text: pl.nickname }),
            el('td', { text: mine.length.toLocaleString() }),
            el('td', {}, [el('div', { class: 'wf-legend-row' }, catDots(run, cm, mine))])]);
        }),
      ]);
    }
    const cs = mode === 'verified' ? ['ds', 'pspike', 'both', 'neither'] : ['ds', 'ied'];
    const head = { ds: mode === 'verified' ? 'DS only' : 'DS',
                   ied: 'P-spike', pspike: 'P-spike only', both: 'both', neither: 'neither' };
    return el('table', { class: 'wf-cut' }, [
      el('tr', {}, [el('th', { text: 'pool' }), el('th', { text: 'events' })]
        .concat(cs.map((c) => el('th', {}, [el('i', { class: 'wf-th-dot',
          style: 'background:' + colourOf('pca', c, 'tgt') }), head[c]])))),
      ...(run.pools || []).map((pl, i) => {
        const mine = pts.filter((p) => p.src === i);
        return el('tr', {}, [el('th', { text: pl.nickname }),
          el('td', { text: mine.length.toLocaleString() }),
          ...cs.map((c) => {
            const k = mine.filter((p) => pcaCls(run, p) === c).length;
            return el('td', { text: k.toLocaleString() + ' · '
              + pct(mine.length ? k / mine.length : null) });
          })]);
      }),
    ]);
  }

  function ruleWords(run, kind) {
    if (kind === 'ambiguous') {
      const b = run.borders || {};
      return 'DS border from ‘' + (((b.ds || {}).workflow) || {}).nickname
        + '’ at grace ' + graceWords((b.ds || {}).grace) + ', P-spike border from ‘'
        + (((b.pspike || {}).workflow) || {}).nickname + '’ at grace '
        + graceWords((b.pspike || {}).grace) + '. Inside both is the Twilight Zone; '
        + 'outside both is said apart.' + (run.halo ? ' Halo: reach ' + run.halo.reach + '×, margin '
          + run.halo.margin + '×' + (run.halo.saved === false ? ', being tried, not saved.'
            : ', saved with this version.') : '');
    }
    return run.rule || '';
  }

  /* EVERY MARK ON THE PICTURES, NAMED (2026-11-05: "blue solid is the
     border with grace, dashed with no grace, and what is the faint box?").
     The dots with how many of each, every box drawn, and the frame. */
  function legend(run, kind, stage) {
    const set = stageSet(run, kind, stage);
    const n = {};
    for (const p of set.pts) n[p.cls] = (n[p.cls] || 0) + 1;
    const tot = set.pts.length || 1;
    const cnt = (c) => (n[c] || 0).toLocaleString() + ' · ' + pct((n[c] || 0) / tot);
    // By mouse or recording the dots wear those colours, so the classes
    // are said with their counts and no colour of their own.
    const cm = catMode(run, kind);
    const dot = (colour, text, c) => el('span', { class: 'wf-lg' }, [
      cm ? null : el('i', { class: 'wf-lg-dot', style: 'background:' + colour }),
      el('span', { text }), c != null ? el('b', { text: cnt(c) }) : null].filter(Boolean));
    const box = (colour, dashed, text) => el('span', { class: 'wf-lg' }, [
      el('i', { class: 'wf-lg-box' + (dashed === 'dotted' ? ' dotted' : dashed ? ' dashed' : ''),
                style: 'border-color:' + colour }), el('span', { text })]);
    const dots = [];
    if (kind === 'ambiguous' && run.halo) {
      const A = (c) => colourOf('ambiguous', c);
      dots.push(dot(A('ds'), 'DS border only', 'ds'),
                dot(A('halo_ds'), 'outside both, captured by the DS halo', 'halo_ds'),
                dot(A('pspike'), 'P-spike border only', 'pspike'),
                dot(A('halo_pspike'), 'outside both, captured by the P-spike halo',
                    'halo_pspike'),
                dot(A('both'), 'inside both: Twilight Zone', 'both'),
                dot(A('halo_amb'), 'outside both, near both halos: extended Twilight Zone',
                    'halo_amb'),
                dot(A('halo_far'), 'outside both, beyond both halos: far out', 'halo_far'));
    } else if (kind === 'ambiguous') {
      dots.push(dot(tok('--call-ds'), 'DS border only', 'ds'),
                dot(tok('--call-p'), 'P-spike border only', 'pspike'),
                dot(tok('--call-amb'), 'inside both: Twilight Zone', 'both'),
                dot(tok('--call-amb-2'), 'outside both', 'neither'));
    } else {
      const grp = kind === 'ds' ? tok('--call-ds') : tok('--call-p');
      const w = kind === 'ds' ? 'DS' : 'P-spike';
      if (stage === 'define') {
        dots.push(dot(grp, 'the border’s own ' + w + ' events, inside it', 'inside'),
                  dot(tok('--warn'), 'its own, left outside by the grace', 'outside'));
        // Missing a number: said apart, only when there are any (2026-11-06).
        if (n.partial) {
          dots.push(dot(colourOf(kind, 'partial', 'src'), 'its own, '
            + CLASS_WORDS.partial + ' (not drawn)', 'partial'));
        }
      } else {
        dots.push(dot(grp, 'inside: verified ' + w, 'inside'),
                  dot(tok('--text-3'), 'outside the border', 'outside'));
      }
    }
    const boxes = boxesOf(run, kind).map((b) => box(b.colour, b.halo ? 'dotted' : b.dashed,
      b.halo || !b.dashed ? b.label
        : b.label + (b.shape ? ' (the widest it gets)' : ' (the widest the box gets)')));
    boxes.push(box(tok('--line'), false, 'frame: the axes, lowest to highest value on show'));
    return el('div', { class: 'wf-legend' }, [
      cm ? el('div', { class: 'wf-legend-row' }, [el('span', { class: 'wf-lg-h',
        text: catHead(cm) })].concat(catDots(run, cm, set.pts.filter(measured)))) : null,
      el('div', { class: 'wf-legend-row' }, [el('span', { class: 'wf-lg-h',
        text: cm ? 'Classes' : 'Dots' })].concat(dots)),
      el('div', { class: 'wf-legend-row' }, [el('span', { class: 'wf-lg-h', text: 'Boxes' })]
        .concat(boxes)),
      stage === 'extract' ? el('div', { class: 'wf-legend-row' }, [
        el('span', { class: 'wf-lg-h', text: 'Faded' }),
        el('span', { class: 'hint', text: kind === 'ambiguous'
          ? 'not undecided: they are inside exactly one border'
          : 'not extracted: outside the border' })]) : null,
    ].filter(Boolean));
  }

  /* `what`: which events it is showing, said on a line of its own
     (2026-11-06: the panels follow the stage). */
  function panel(title, words, body, what) {
    return el('div', { class: 'wf-panel' }, [
      el('strong', { text: title }),
      el('span', { class: 'hint', text: words }),
      what ? el('span', { class: 'wf-panel-what', text: what }) : null,
      body,
    ].filter(Boolean));
  }

  function distPanel(run, kind, stage) {
    const out = [];
    for (const which of kind === 'ambiguous' ? ['a', 'b'] : ['a']) {
      if (kind === 'ambiguous') {
        out.push(el('span', { class: 'hint', text: which === 'a'
          ? 'From the DS border' : 'From the P-spike border' }));
      }
      for (let a = 0; a < 3; a++) {
        const cv = el('canvas', { class: 'wf-dist' });
        later(() => drawDist(cv, run, kind, a, which, stage));
        out.push(cv);
      }
    }
    return el('div', { class: 'wf-dist-grid' }, out);
  }

  function venn(run) {
    const c = run.counts || {};
    const n = (k) => (c[k] || 0).toLocaleString();
    return el('div', { class: 'wf-venn' }, [
      el('div', { class: 'wf-venn-c ds' }, [el('span', { text: 'DS only' }),
                                            el('strong', { text: n('ds') })]),
      el('div', { class: 'wf-venn-c both' }, [el('span', { text: 'both' }),
                                              el('strong', { text: n('both') })]),
      el('div', { class: 'wf-venn-c p' }, [el('span', { text: 'P-spike only' }),
                                           el('strong', { text: n('pspike') })]),
      run.halo
        ? el('span', { class: 'hint wf-venn-halo', text: 'Outside both, with the halo: '
            + n('halo_ds') + ' captured by DS, ' + n('halo_pspike') + ' captured by P-spike, '
            + n('halo_amb') + ' extended Twilight Zone, ' + n('halo_far') + ' far out.' })
        : el('span', { class: 'hint', text: 'Outside both: ' + n('neither') + '.' }),
    ]);
  }

  /* Each mouse on its own, at the stage on show (2026-11-06): the border's
     own events in Define, "N inside of M"; every target event in Apply; in
     Extract the rest faded, "N extracted of M". A Pooled PCA has no stage. */
  function perMouse(run, kind, R, stage) {
    const st = kind === 'pca' ? 'apply' : (stage || 'apply');
    const S = kind === 'pca' ? { pts: pointsOf(run.cols), own: false }
                             : panelSet(run, kind, st);
    const pts = S.pts;
    const mice = Array.from(new Set(pts.map((p) => p.mouse))).filter(Boolean)
      .sort((a, b) => (BARRY.ui.natCompare ? BARRY.ui.natCompare(a, b)
                       : String(a).localeCompare(String(b))));
    const rows = run.by_mouse || [];
    const keptOf = isKept(kind);
    // Coloured by mouse, each card says its colour beside its name.
    const Cm = catMode(run, kind) === 'mouse' ? catInfo(run, 'mouse') : null;
    const cards = mice.map((mk) => {
      const cv = el('canvas', { class: 'wf-mouse-cv' });
      later(() => draw2d(cv, run, kind, st, 'amp', 'hf',
                         { small: true, h: 80, ranges: R,
                           only: (p) => p.mouse === mk }));
      const r = rows.find((x) => x.key === mk) || {};
      const mine = pts.filter((p) => p.mouse === mk);
      const kept = mine.filter(keptOf).length;
      const said = kind === 'pca'
        ? (r.ds || 0) + ' DS · ' + (r.ied || 0) + ' P-spike'
        : kept + (st === 'extract' ? ' extracted of '
                  : S.own ? ' inside of ' : kind === 'ambiguous' ? ' undecided of '
                  : ' inside of ') + mine.length
          + (S.own ? ', its own' : '') + ' · ' + pct(mine.length ? kept / mine.length : null);
      return el('div', { class: 'wf-mouse' }, [
        Cm ? el('strong', { class: 'wf-lg' }, [
          el('i', { class: 'wf-lg-dot', style: 'background:' + Cm.colour(String(mk)) }),
          el('span', { text: String(mk).replace(/^[^|]*\|/, '') })])
          : el('strong', { text: String(mk).replace(/^[^|]*\|/, '') }),
        cv,
        el('span', { class: 'hint wf-mouse-n', text: said }),
      ]);
    });
    return el('div', { class: 'wf-mice' }, cards);
  }

  /* ---------- the class averages ---------- */
  /* By the stage (2026-11-06). Define: a DS workflow's own events are a
     saved pool, so they average over it; a P-spike workflow's are
     hand-sorted sets, which have no saved pool to average from. Apply:
     every class of the target. Extract: only what is extracted. */
  function averages(run, kind, stage) {
    const st = stage || 'apply';
    const own = st === 'define' && kind !== 'ambiguous';
    const src = (shownDef() || {}).source || {};
    if (own && (src.type === 'sets' || src.entries || !src.artifact_id)) {
      return el('div', {}, [el('p', { class: 'hint wf-avg-none', text:
        'The border’s own events here are hand-sorted sets, which have no saved '
        + 'pool to average from. Apply and Extract average the target’s.' })]);
    }
    const classes = st === 'extract'
      ? (kind === 'ambiguous' ? ambKept(run) : ['inside'])
      : kind === 'ambiguous' ? ambClasses(run) : ['inside', 'outside'];
    const word = (c) => (st === 'extract' && kind !== 'ambiguous' ? 'extracted'
      : own && c === 'outside' ? 'left outside' : shortClass(c));
    const kids = [el('div', { class: 'wf-avg-btns' }, classes.map((c) =>
      BARRY.ui.button({ kind: 'mini', text: 'Average ' + (own ? 'its own, ' : '') + word(c),
        extra: 'wf-avg-go',
        onclick: () => average(run, kind, c, own ? 'src' : 'tgt', word(c)) })))];
    const A = W.avg;
    if (A) {
      kids.push(el('span', { class: 'hint', text: A.busy ? 'Averaging ' + A.label + '…'
        : A.err ? 'Not averaged: ' + A.err
        : A.label + ': ' + (A.data.n || '?') + ' events'
          + (A.data.n_away ? ', ' + A.data.n_away + ' read elsewhere and not '
             + 'counted' : '') + '. Its four pictures are below the 3D view, '
          + 'where a picked event’s are.' }));
    }
    return el('div', {}, kids);
  }

  async function average(run, kind, cls, which, words) {
    const own = which === 'src';
    const pts = pointsOf(own ? run.src_cols : run.cols).filter((p) => p.cls === cls);
    const mem = (own ? run.src_members : run.members) || [];
    const events = pts.map((p) => [(mem[p.m] || {}).key, p.i])
      .filter((x) => x[0] != null && x[1] != null);
    if (!events.length) { toast('Nothing in that class to average.', null, 5000); return; }
    const label = (own ? 'its own, ' : '') + (words || shortClass(cls)) + ' · '
      + events.length + ' events';
    const mine = W.avg = { label, busy: true };
    refresh();
    // Over the pool the events are from: the source's in Define.
    const t = own ? ((shownDef() || {}).source || {}) : (run.target || {});
    let got;
    try {
      const data = await apiPost('/api/rootcanal/pool/group', {
        members: mem.map((m) => ({ key: m.key })),
        measure: run.measure || null, band: null, k: 2,
        saved: { artifact_id: t.artifact_id, version: t.version },
        events, label,
      });
      got = { label, data };
    } catch (e) {
      got = { label, err: e.message };
    }
    // Only if it is still the one asked for: the stage changed, or another
    // average was asked, and this one landed late.
    if (W.avg !== mine) return;
    W.avg = got;
    refresh();
  }

  /* ---------- the picked event ---------- */
  function pickedPoint(run) {
    if (!W.picked) return null;
    const col = W.picked.which === 'src' ? run.src_cols : run.cols;
    return pointsOf(col)[W.picked.n] || null;
  }

  function inspector(run, kind) {
    const p = pickedPoint(run);
    // An average on show takes the pictures' place, as in Root Canal.
    if (W.avg) {
      return el('div', { class: 'wf-insp' }, [
        el('div', { class: 'wf-insp-head' }, [
          el('strong', { text: 'Average · ' + W.avg.label }),
          W.avg.data && W.avg.data.n_away ? el('span', { class: 'hint', text:
            W.avg.data.n_away + ' read on another machine, not counted' }) : null,
          BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Close',
            onclick: () => { W.avg = null; refresh(); } }),
        ].filter(Boolean)),
        pictures(W.avg.busy ? { busy: true } : W.avg.err ? { err: W.avg.err }
                 : { data: W.avg.data }, null, {}, true),
      ]);
    }
    if (!p) {
      return el('div', { class: 'wf-insp wf-insp-empty' }, [el('span', {
        class: 'hint', text: 'Click a dot in any picture to see its three numbers '
          + 'against the cut-offs, where it came from, and its waveform.' })]);
    }
    const mem = (W.picked.which === 'src' ? run.src_members : run.members) || [];
    const m = mem[p.m] || {};
    const boxes = boxesOf(run, kind).filter((b) => !b.dashed);
    const dist = (W.picked.which === 'src' || kind !== 'ambiguous') ? [p.da]
                                                                   : [p.da, p.db];
    const rowsT = AX.map(([c, k, w, u], ai) => el('tr', {}, [
      el('th', { text: w }),
      el('td', { text: fmt(p[c], 1) + ' ' + u }),
      ...boxes.map((b, bi) => {
        const lo = b.lo[c], hi = b.hi[c];
        const d = (dist[bi] || [])[ai];
        /* By the server's distance, worked on the full numbers (2026-11-06):
           the column's are rounded (amp to 2 places, HF and half-width to
           3), and the edges are a kept event's exact values, so an event ON
           the edge read "outside (0.00 box widths in)". With no distance,
           the column against the edges, give or take half its rounding. */
        const tol = c === 'amp' ? 0.005 : 0.0005;
        const inside = finite(d) ? d <= 0
          : p[c] != null && p[c] >= lo - tol && p[c] <= hi + tol;
        if (b.shape) {
          // A scoop's or a snap's numbers per axis are its extent, not a rule.
          return el('td', { class: 'wf-extent', text: 'extent ' + fmt(lo, 1) + ' – ' + fmt(hi, 1) });
        }
        return el('td', { class: inside ? 'wf-in' : 'wf-out', text: fmt(lo, 1) + ' – '
          + fmt(hi, 1) + (inside ? ' · inside' : ' · outside')
          + (d != null ? ' (' + (d <= 0 ? (-d).toFixed(2) + ' box widths in'
                                         : d.toFixed(2) + ' box widths out') + ')' : '') });
      }),
    ]));
    if (boxes.some((b) => b.shape)) {
      // Inside a scoop or a snap is the shape's own test, which the class says.
      const c = p.cls;
      const inOf = (bi) => (kind === 'ambiguous' && W.picked.which !== 'src'
        ? (bi === 0 ? c === 'both' || c === 'ds' : c === 'both' || c === 'pspike')
        : c === 'inside');
      rowsT.push(el('tr', {}, [el('th', { text: 'In the border' }), el('td', { text: '' }),
        ...boxes.map((b, bi) => el('td', { class: inOf(bi) ? 'wf-in' : 'wf-out',
          text: (inOf(bi) ? 'inside the ' : 'outside the ') + (b.shape ? SHAPE_WORD[b.shape.kind === 'hull'
            ? 'hull' : 'ellipsoid'].toLowerCase() : 'box') }))]));
    }
    if (kind === 'pca') {
      for (let k = 0; k < 3; k++) {
        rowsT.push(el('tr', {}, [el('th', { text: 'PC' + (k + 1) }),
          el('td', { text: p.pc ? fmt(p.pc[k], 2) : '—' }),
          ...boxes.map(() => el('td', { text: '' }))]));
      }
    }
    const def = shownDef() || {};
    const d = W.openId && W.data[W.openId];
    const row = (W.list || []).find((r) => r.artifact_id === W.openId) || {};
    const hist = [];
    hist.push('Recording: ' + (m.session_label || p.gid || '?') + ', at '
              + fmt(p.t, 3) + ' s.');
    if (m.entry_id) {
      hist.push('Set: bank entry ' + m.entry_id + (m.from_version != null
        ? ', version ' + m.from_version : ', as it stood') + '. '
        + (W.picked.which === 'src' && def.kind === 'pspike'
          ? 'Hand-sorted, retimed and aligned before it was read.'
          : 'Found by Incisor, checked in Checkup and aligned in Braces before '
            + 'Root Canal read it.'));
    }
    const pl = W.picked.which === 'src' ? def.source : (run.target || def.target);
    if (kind === 'pca') {
      const mine = (run.pools || [])[p.src] || {};
      const others = (run.pools || []).filter((x, i) => i !== p.src)
        .map((x) => '‘' + x.nickname + '’').join(' and ');
      hist.push('Pooled in ‘' + mine.nickname + '’ v' + mine.version + ', which called it '
        + (PCA_WORDS[p.own] || 'nothing') + '.');
      hist.push('Made one pool with ' + (others || 'nothing else') + ' and clustered '
        + 'again: called ' + (PCA_WORDS[p.cls] || 'nothing') + '.');
      if (p.ver !== null && p.ver !== undefined) {
        const b = run.borders || {};
        hist.push('Under the verified borders (‘' + ((b.ds || {}).workflow || {}).nickname
          + '’, ‘' + ((b.pspike || {}).workflow || {}).nickname + '’): '
          + (CLASS_WORDS[p.ver] || p.ver) + (p.ver === 'both' || p.ver === 'neither'
            ? (p.ver === 'both' ? ', so the Twilight Zone' : ', so undecided') : '') + '.');
      }
      if (p.pc) hist.push('In the PCA: PC1 ' + fmt(p.pc[0], 2) + ', PC2 ' + fmt(p.pc[1], 2)
        + ' (each number z-scored over the one pool).');
    } else if (pl && pl.nickname) {
      hist.push((W.picked.which === 'src' ? 'Border drawn from '
        : 'Pooled in ') + '‘' + pl.nickname + '’' + (pl.version ? ' v' + pl.version : '') + '.');
    }
    if (run.border_ref) hist.push('Border ‘' + run.border_ref.nickname + '’ v'
      + run.border_ref.version + ', at grace ' + graceWords(run.grace) + '.');
    if (!W.preview && row.nickname && kind !== 'pca') hist.push('Classified by the workflow ‘'
      + row.nickname + '’ v' + (d && (d.shown || d.version)) + ': '
      + CLASS_WORDS[p.cls] + '.');
    if (run.bank && p.cls === 'inside') hist.push('Banked in entry '
      + run.bank.entry_id + '.');
    const E = W.ev;
    const kids = [
      el('div', { class: 'wf-insp-head' }, [
        el('span', { class: 'swatch-dot', style: 'background:'
                     + colourOf(kind, dotCls(run, kind, p), W.picked.which) }),
        el('strong', { text: kind === 'pca' ? PCA_WORDS[pcaCls(run, p)]
                       : (CLASS_WORDS[p.cls] || 'not measured') }),
        el('span', { class: 'hint', text: (m.session_label || p.gid || '') + ' · '
          + fmt(p.t, 3) + ' s' }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Read its traces again',
          extra: 'wf-ev-go', disabled: !m.event_body,
          title: m.event_body ? 'Its four pictures, from its own read.'
                 : 'Its read is not on this machine.',
          onclick: () => loadEvent(m, p) }),
        BARRY.ui.button({ kind: kind === 'pca' ? 'primary' : 'ghost', size: 'sm',
          text: 'Open in Xplorefinder', extra: 'wf-xplore',
          title: 'The recording at this event, in its own window. While that '
                 + 'window is open, every dot you click moves it to that dot.',
          onclick: () => openX(p) }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Close',
          onclick: () => { W.picked = null; W.ev = null; refresh(); } }),
      ]),
      el('div', { class: 'wf-insp-top' }, [
        el('table', { class: 'wf-cut' }, [
          el('tr', {}, [el('th', { text: '' }), el('th', { text: 'this event' }),
            ...boxes.map((b) => el('th', {}, [el('i', { class: 'wf-th-sw',
              style: 'border-color:' + b.colour }), b.label]))]),
          ...rowsT,
        ]),
        el('div', { class: 'wf-insp-hist' }, [
          el('strong', { text: 'Where it came from' }),
          el('ol', { class: 'wf-hist' }, hist.map((t) => el('li', { text: t }))),
        ]),
      ]),
    ];
    kids.push(pictures(E, m.event_body ? null
      : 'Its read is not on this machine' + (m.read_on ? ' (it was read on '
        + m.read_on + ')' : '') + ', so its numbers are here and its traces '
        + 'are not.', { cls: p.cls === 'pspike' ? 'ied' : p.cls === 'inside'
          ? ((shownDef() || {}).kind === 'pspike' ? 'ied' : 'ds') : p.cls }));
    return el('div', { class: 'wf-insp' }, kids);
  }

  /* Root Canal's own four pictures -- max-amp contact, spectrum, every
     contact, CSD -- drawn by Root Canal (rootcanal.js, `drawEvent`), for an
     event or for an average. */
  function pictures(E, away, e, average) {
    if (!H || !H.eventGrid) return null;
    const words = away ? away : !E ? null : E.busy ? (average ? 'Averaging…'
      : 'Reading its traces…') : E.err ? (average ? 'Not averaged: '
      : 'No traces: ') + E.err : null;
    const d = E && E.data ? E.data : (E && E.err ? { ok: false, error: E.err } : null);
    const grid = H.eventGrid(d, { average: !!average });
    later(() => H.drawEvent(d, e || {}));
    return el('div', { class: 'wf-pics' }, [
      words ? el('p', { class: 'hint' + (E && E.err ? ' wf-warn' : ''), text: words }) : null,
      grid,
    ].filter(Boolean));
  }

  async function loadEvent(m, p) {
    if (!m.event_body) return;
    W.ev = { busy: true };
    refresh();
    try {
      const data = await apiPost('/api/rootcanal/event',
                                 Object.assign({}, m.event_body, { i: p.i }));
      W.ev = { data };
    } catch (e) {
      W.ev = { err: e.message };
    }
    refresh();
  }

  /* The recording window this tab opened, so a pick can move it. It shares
     Root Canal's window name: one recording window, whichever opened it. */
  let xWin = null;
  function xOpen() {
    try { return !!(xWin && !xWin.closed); } catch (e) { return false; }
  }

  async function openX(p) {
    const path = H && H.recordingPath ? await H.recordingPath(p.gid) : null;
    if (!path) {
      toast('That event’s recording is not reachable from this machine, so '
            + 'the recording window cannot show it.', 'err', 9000);
      return;
    }
    const run = shownRun() || {};
    const ms = run.measure || {};
    const args = new URLSearchParams({
      csc: path,
      panes: JSON.stringify([{ panel: 'traces' }, { panel: 'csd' }]),
      t0: Math.max(0, p.t - 0.25).toFixed(4), span: '0.5',
      hp: String(ms.lo_hz != null ? ms.lo_hz : 5),
      lp: String(ms.hi_hz != null ? ms.hi_hz : 100),
      notch: ms.mains_out ? '60' : '0',
      chrome: 'notabs,noheads', role: 'rootcanal',
      theme: (BARRY.state && BARRY.state.theme) || 'dark',
    });
    const url = location.origin + '/?' + args.toString() + '#xplore';
    if (xOpen()) {
      try { xWin.location.href = url; } catch (e) { xWin = null; }
    }
    if (!xOpen()) {
      xWin = window.open(url, 'barry-rootcanal-traces',
                         'width=1180,height=900,menubar=no,toolbar=no');
    }
    if (!xWin) toast('The recording window was blocked. Allow pop-ups for this '
                     + 'page, then press it again.', 'err', 9000);
    BARRY.activity.log('rootcanal.workflow_xplore', { gid: p.gid, t: p.t });
  }

  async function toPooled(run, kind) {
    const t = run.target || {};
    const b = kind === 'ambiguous' ? null : run.border_ref;
    if (W.stage === 'define' && kind === 'ds') {
      const s = (shownDef() || {}).source || {};
      return H.openPool({ artifact_id: s.artifact_id, version: s.version },
                        b ? { artifact_id: b.artifact_id, version: b.version,
                              grace: run.grace } : null);
    }
    if (W.stage === 'define' && kind === 'pspike') {
      toast('The hand-sorted sets are not a saved pool, so this stage has no '
            + 'Pooled picture; the target does.', null, 7000);
    }
    return H.openPool({ artifact_id: t.artifact_id, version: t.version },
                      b ? { artifact_id: b.artifact_id, version: b.version,
                            grace: run.grace } : null);
  }

  /* ---------- the ambiguous ones, to choose from ---------- */
  function ambTable(run) {
    // A choice the other way of telling them has no class for shows all.
    const show = (run.halo ? W.ambShow === 'neither'
      : (W.ambShow === 'halo_amb' || W.ambShow === 'halo_far')) ? 'all' : W.ambShow;
    const pts = pointsOf(run.cols).filter((p) => (show === 'all'
      ? AMB_KEPT.has(p.cls) : p.cls === show));
    const mem = run.members || [];
    const picks = W.ambPick;
    const MAX = 400;
    const shown = pts.slice(0, MAX);
    return el('div', { class: 'card wf-amb' }, [
      el('div', { class: 'wf-amb-head' }, [
        el('strong', { text: 'The Twilight Zone and outside both, to choose from' }),
        BARRY.ui.seg(run.halo
          ? [['all', 'all'], ['halo_amb', 'extended Twilight Zone'], ['halo_far', 'far out'],
             ['both', 'inside both']]
          : [['all', 'all'], ['neither', 'outside both'], ['both', 'inside both']],
        show, (v) => { W.ambShow = v; refresh(); }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Tick all shown',
          onclick: () => { shown.forEach((p) => picks.add(p.n)); refresh(); } }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Untick all',
          onclick: () => { picks.clear(); refresh(); } }),
        el('span', { class: 'hint', text: picks.size + ' ticked' }),
        BARRY.ui.seg([['ied', 'as P-spikes'], ['ds', 'as DS'], ['other', 'as Twilight Zone']],
                     W.ambType, (v) => { W.ambType = v; refresh(); }),
        BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'Bank the ticked',
          disabled: !picks.size || !!W.preview,
          title: W.preview ? 'Save and run the workflow first.' : null,
          onclick: () => bankPicked() }),
      ]),
      pts.length > MAX ? el('span', { class: 'hint', text: 'Showing the first '
        + MAX + ' of ' + pts.length + '; narrow it with the switch above.' }) : null,
      el('table', { class: 'wf-amb-tab' }, [
        el('tr', {}, ['', 'recording', 't · s', 'amp · µV', 'HF · dB', 'hw · ms', 'why']
          .map((t) => el('th', { text: t }))),
        ...shown.map((p) => el('tr', {
          class: W.picked && W.picked.which === 'tgt' && W.picked.n === p.n ? 'on' : '',
          onclick: (e) => {
            if (e.target && e.target.tagName === 'INPUT') return;
            W.picked = { which: 'tgt', n: p.n }; W.ev = null; refresh();
          } }, [
          el('td', {}, [el('input', { type: 'checkbox',
            checked: picks.has(p.n) ? 'checked' : null,
            onchange: (e) => { if (e.target.checked) picks.add(p.n);
                               else picks.delete(p.n);
                               refresh(); } })]),
          el('td', { text: (mem[p.m] || {}).session_label || p.gid || '?' }),
          el('td', { text: fmt(p.t, 3) }),
          el('td', { text: fmt(p.amp, 0) }),
          el('td', { text: fmt(p.hf, 1) }),
          el('td', { text: fmt(p.hw, 1) }),
          el('td', { text: CLASS_WORDS[p.cls] }),
        ])),
      ]),
    ].filter(Boolean));
  }

  async function bankPicked() {
    const id = W.openId;
    const d = W.data[id];
    if (!id || !d) return;
    const typeWord = { ied: 'P-spikes', ds: 'dentate spikes', other: 'Twilight Zone' }[W.ambType];
    const ok = await BARRY.ui.bankDialog({
      title: 'Bank ' + W.ambPick.size + ' picked events as ' + typeWord,
      name: 'Picked ' + typeWord + ' · ' + ((W.list || []).find((r) => r.artifact_id === id) || {}).nickname,
      onBank: async (o) => {
        const got = await apiPost('/api/rootcanal/workflow/' + encodeURIComponent(id)
                                  + '/bank', { version: d.shown || d.version,
                                               picks: Array.from(W.ambPick),
                                               type: W.ambType, name: o.name });
        toast(got.n + ' events banked as one entry (' + got.entry_id + ').',
              'ok', 8000);
        W.ambPick.clear();
      },
    });
    if (ok) refresh();
  }

  /* ---------- the lineage ---------- */
  function lineage(row, d) {
    const lines = (d.lines || []).slice().reverse();
    const shown = d.shown || d.version;
    return el('div', { class: 'wf-lineage' }, [
      el('strong', { text: 'Versions' }),
      el('span', { class: 'hint', text: 'Every definition and every run, newest '
        + 'first. A run pins the exact versions it read, and says what moved '
        + 'since the run before it.' }),
      el('div', { class: 'wf-lines' }, lines.map((ln) => el('div', {
        class: 'wf-line' + (ln.version === shown ? ' on' : '') }, [
        el('strong', { text: 'v' + ln.version }),
        el('span', { text: !ln.here ? 'on another machine, not synced here yet'
          : ln.ran ? 'run' + (ln.by ? ' by ' + ln.by : '') + (ln.at ? ', '
            + new Date(ln.at).toLocaleString() : '') : 'defined' }),
        ln.ran ? el('span', { class: 'hint', text: (ln.kept || 0).toLocaleString()
          + (ln.definition && ln.definition.kind === 'pca' ? ' called' : ' kept')
          + (ln.grace != null ? ' · grace ' + graceWords(ln.grace) : '')
          + ' · ' + defWords(ln.definition) }) : el('span', { class: 'hint',
          text: defWords(ln.definition) }),
        ln.diff ? el('span', { class: 'hint wf-diff', text: ln.diff.n
          ? ln.diff.n + ' changed since the run before: ' + Object.entries(
            ln.diff.moves || {}).map(([k, n]) => k + ' ' + n).join(', ')
          : 'nothing changed since the run before' }) : null,
        ln.bank ? el('span', { class: 'hint', text: 'bank entry ' + ln.bank.entry_id }) : null,
        ln.border_ref ? el('span', { class: 'hint', text: 'border ‘'
          + ln.border_ref.nickname + '’ v' + ln.border_ref.version }) : null,
        ln.here && ln.ran && ln.version !== shown ? BARRY.ui.button({ kind: 'mini',
          text: 'Show this version', onclick: async () => {
            W.picked = null; await loadOne(row.artifact_id, ln.version); } }) : null,
        ln.here && ln.definition ? BARRY.ui.button({ kind: 'mini',
          text: 'Rebuild from here', title: 'Make this version’s definition the '
            + 'newest, with the same pinned inputs, and run it again.',
          onclick: () => rebuild(row, ln) }) : null,
      ].filter(Boolean)))),
      shownDiff(d),
    ]);
  }

  function defWords(dd) {
    if (!dd) return '';
    if (dd.kind === 'pca') {
      return (dd.pools || []).map((p) => '‘' + p.nickname + '’ v' + p.version).join(' + ')
        + ' as one pool' + (dd.uses ? ', coloured also by ' + ['ds', 'pspike']
          .map((k) => '‘' + (dd.uses[k] || {}).nickname + '’ v' + (dd.uses[k] || {}).version)
          .join(' + ') : '');
    }
    if (dd.kind === 'ambiguous') {
      return ['ds', 'pspike'].map((k) => ((dd.uses || {})[k] || {}))
        .map((u) => '‘' + u.nickname + '’ v' + u.version).join(' + ');
    }
    const s = dd.source || {};
    return (s.type === 'sets' ? (s.entries || []).length + ' hand-sorted sets'
            : '‘' + s.nickname + '’ v' + s.version) + ' → ‘'
           + ((dd.target || {}).nickname || '') + '’ v' + ((dd.target || {}).version || '');
  }

  function shownDiff(d) {
    const run = d.payload && d.payload.run;
    const df = run && run.diff;
    if (!df || !df.n) return null;
    return el('details', { class: 'wf-diff-box' }, [
      el('summary', { text: 'What changed class since the run before: '
                      + df.n + ' events' }),
      el('table', { class: 'wf-amb-tab' }, [
        el('tr', {}, ['recording', 't · s', 'was', 'now'].map((t) => el('th', { text: t }))),
        ...(df.examples || []).map((x) => {
          const m = (run.members || []).find((mm) => mm.gid === x.gid) || {};
          return el('tr', {}, [el('td', { text: m.session_label || x.gid }),
            el('td', { text: fmt(x.t, 3) }),
            el('td', { text: CLASS_WORDS[x.was] || x.was }),
            el('td', { text: CLASS_WORDS[x.now] || x.now })]);
        }),
      ]),
    ]);
  }

  async function rebuild(row, ln) {
    const dd = ln.definition || {};
    try {
      await apiPost('/api/rootcanal/workflow/save', Object.assign({}, dd, {
        artifact_id: row.artifact_id, nickname: row.nickname }));
    } catch (e) {
      toast('Not rebuilt: ' + e.message, 'err', 9000);
      return;
    }
    W.list = null;
    await loadList();
    const r = (W.list || []).find((x) => x.artifact_id === row.artifact_id);
    if (r) await runWorkflow(r, false);
  }

  /* ==================================================================
     Building one
     ================================================================== */
  async function openBuilder(row) {
    const src = await loadSources();
    // A new one's picks come from the pools on show, never an archived one.
    const pools = (src.pools || []).filter((p) => !poolShelved(p.artifact_id));
    // By name, or else its newest "… v2" (2026-11-06: the first ones were
    // archived for "CTL Baseline v2" and "PTEN Baseline v2").
    const vOf = (p, n) => { const m = String(p.nickname || '').slice(n.length).match(/^ v(\d+)$/);
                            return m ? Number(m[1]) : null; };
    const byNick = (n) => ((pools.find((p) => p.nickname === n)
      || pools.filter((p) => vOf(p, n) != null && String(p.nickname).indexOf(n) === 0)
        .sort((a, b) => vOf(b, n) - vOf(a, n))[0]) || {}).artifact_id;
    const dd = (row && ((W.data[row.artifact_id] || {}).payload || {}).definition)
               || (row && row.definition) || {};
    const kind = dd.kind || 'ds';
    W.builder = {
      artifact_id: row ? row.artifact_id : null,
      nickname: row ? row.nickname : '',
      kind,
      grace: dd.grace != null ? dd.grace : 0.05,
      custom: '',
      shape: dd.shape || 'box',
      folder: (dd.folder || (row ? folderOf(row) : [])).join('/'),
      // The pools in "PTEN Panning Complete" first (2026-11-06).
      source: (dd.source || {}).artifact_id || byNick('CTL Baseline')
        || byNick('PTEN CTL Baseline Full Incisor')
        || ((pools.find((p) => p.all_ds) || {}).artifact_id) || null,
      target: (dd.target || {}).artifact_id || byNick('PTEN Baseline')
        || byNick('PTEN ALL PTEN Baseline Full Incisor') || null,
      pools: new Set(dd.pools ? dd.pools.map((p) => p.artifact_id)
        : [byNick('PTEN Baseline'), byNick('CTL Baseline')].filter(Boolean)),
      pcaUses: dd.kind === 'pca' ? !!dd.uses : true,
      sets: new Set(((dd.source || {}).entries || []).map((e) => e.entry_id)
                    .concat(dd.source && dd.source.entries ? []
                            : (src.sets || []).filter((s) => s.hand_sorted)
                              .map((s) => s.entry_id))),
      uses: { ds: ((dd.uses || {}).ds || {}).artifact_id || null,
              pspike: ((dd.uses || {}).pspike || {}).artifact_id || null },
      /* WHICH VERSION of each input (2026-11-12). An edit keeps what the
         definition pinned; a new one, or a different pick, takes the newest
         (null). */
      sourceV: (dd.source || {}).version || null,
      targetV: (dd.target || {}).version || null,
      poolV: new Map((dd.pools || []).filter((p) => p.version)
        .map((p) => [p.artifact_id, p.version])),
      usesV: { ds: ((dd.uses || {}).ds || {}).version || null,
               pspike: ((dd.uses || {}).pspike || {}).version || null },
      // What the definition pinned, said in the tree.
      pinned: row ? {
        source: refOf(dd.source),
        target: refOf(dd.target),
        pools: new Map((dd.pools || []).map((p) => [p.artifact_id, p.version])),
        uses: { ds: refOf((dd.uses || {}).ds), pspike: refOf((dd.uses || {}).pspike) },
      } : null,
      /* An Ambiguous workflow's own target (2026-11-12: "We get to choose
         p-spike border, ds border... but not where to apply it to"). Until
         one is picked it is the DS workflow's. */
      ambTargetSet: kind === 'ambiguous' && !!(dd.target || {}).artifact_id,
    };
    if (!W.builder.uses.ds) {
      const r = (W.list || []).find((x) => x.kind === 'ds' && x.ran);
      W.builder.uses.ds = r ? r.artifact_id : null;
    }
    if (!W.builder.uses.pspike) {
      const r = (W.list || []).find((x) => x.kind === 'pspike' && x.ran);
      W.builder.uses.pspike = r ? r.artifact_id : null;
    }
    W.prep = null;
    refresh();
  }

  /* An input as the server takes it: the id and the version its button
     shows -- the one picked, else the newest (a pool) or the last run (a
     workflow). With none, the server pins the newest itself. */
  const pinRef = (aid, v) => (v != null ? { artifact_id: aid, version: Number(v) }
                                        : { artifact_id: aid });
  const poolRef = (aid, v) => pinRef(aid, v != null ? v : (poolOf(aid) || {}).version);
  const targetRef = () => poolRef(W.builder.target, W.builder.targetV);
  const runRef = (B, k) => pinRef(B.uses[k], B.usesV[k] != null ? B.usesV[k]
    : ((W.list || []).find((x) => x.artifact_id === B.uses[k]) || {}).run_version);
  const usesRef = (B) => ({ ds: runRef(B, 'ds'), pspike: runRef(B, 'pspike') });
  const refOf = (r) => (r && r.artifact_id ? { id: r.artifact_id, v: r.version || null } : null);

  /* Where an Ambiguous workflow is applied: its own pick, else the DS
     workflow's target, as that workflow pins it. */
  function ambTarget(B) {
    if (B.ambTargetSet) return { id: B.target, v: B.targetV };
    const r = (W.list || []).find((x) => x.artifact_id === B.uses.ds);
    const t = r && (r.definition || {}).target;
    return t ? { id: t.artifact_id, v: t.version || null } : { id: null, v: null };
  }

  function builderBody() {
    const B = W.builder;
    const body = { kind: B.kind, nickname: B.nickname,
                   folder: String(B.folder || '').split('/').map((x) => x.trim()).filter(Boolean) };
    if (B.kind === 'pca') {
      body.pools = Array.from(B.pools).map((id) => poolRef(id, B.poolV.get(id)));
      if (B.pcaUses && B.uses.ds && B.uses.pspike) body.uses = usesRef(B);
    } else if (B.kind !== 'ambiguous') {
      const g = B.custom !== '' && isFinite(Number(B.custom))
        ? Number(B.custom) / 100 : B.grace;
      body.grace = g;
      body.shape = B.shape || 'box';
      body.target = targetRef();
      if (B.kind === 'ds') body.source = poolRef(B.source, B.sourceV);
      else body.source = { entries: Array.from(B.sets).map((id) => ({ entry_id: id })) };
    } else {
      body.uses = usesRef(B);
      const t = ambTarget(B);
      if (t.id) body.target = poolRef(t.id, t.v);
    }
    return body;
  }

  /* WHICH VERSION OF AN INPUT (2026-11-12: "No version select here. Use the
     same git like branching select thing"). Beside the pick of WHICH pool or
     workflow, the button every other version choice is (ui.versionButton):
     the version chosen, and the whole tree in a pop-up. The workflow is
     pinned to it; a newer version saved later is flagged on the workflow's
     strip and never taken by itself. */
  const NOT_HERE = 'Saved on another computer; it has not reached this one yet.';
  const plural = (n, one, many) => n + ' ' + (n === 1 ? one : many);

  function pinButton(o) {
    const vs = (o.versions || []).map((v) => ({
      v: v.v, at: v.at, by: v.by, here: v.here, raw: v,
      n: o.count(v),
      note: [v.nickname ? '‘' + v.nickname + '’' : null, v.note].filter(Boolean)
        .join(' · ') || null,
    }));
    if (!vs.length) return null;
    const newest = Math.max.apply(null, vs.map((v) => v.v || 0));
    const cur = o.value != null ? Number(o.value) : null;
    const btn = BARRY.ui.versionButton({
      versions: vs, idOf: (v) => v.v, value: cur, unit: o.unit, producer: false,
      disabled: (v) => (v.here === false ? NOT_HERE : (o.why ? o.why(v.raw) : null)),
      state: (v) => (o.pinned != null && v.v === Number(o.pinned)
        ? ['what it is pinned to now'] : []),
      line: o.line ? (v) => o.line(v.raw) : null,
      heading: o.heading, sub: o.sub,
      onpick: (v) => { if (v) { o.onpick(v.v); refresh(); } },
    });
    btn.classList.add('wf-vbtn');
    if (o.extra) btn.classList.add(o.extra);
    // Inside a pool's label (Pooled PCA), a press must not tick its box.
    btn.addEventListener('click', (e) => e.preventDefault());
    if (cur == null || cur >= newest) return btn;
    return el('span', { class: 'wf-pin' }, [btn,
      el('span', { class: 'hint wf-newer', text: 'v' + newest + ' is newer' })]);
  }

  const poolOf = (aid) => ((W.sources || {}).pools || []).find((p) => p.artifact_id === aid);
  // A pool from an older server has no list: its newest is all there is.
  const poolVersions = (p) => ((p.versions || []).length ? p.versions
    : p.version ? [{ v: p.version, events: p.events, members: p.members,
                     mice: p.mice, here: true }] : []);

  function poolPin(aid, value, onpick, pinned, extra) {
    const p = poolOf(aid);
    if (!p) return null;
    return pinButton({
      versions: poolVersions(p), value: value != null ? value : p.version,
      unit: 'events', count: (v) => v.events, pinned, onpick, extra,
      line: (v) => [v.members != null ? plural(v.members, 'recording', 'recordings') : null,
                    v.mice != null ? plural(v.mice, 'mouse', 'mice') : null]
        .filter(Boolean).join(' · ') || null,
      heading: 'Which version of ‘' + (p.nickname || aid) + '’',
      sub: 'The workflow reads the version chosen here, and stays pinned to it. '
         + 'A newer version saved later is flagged on the workflow’s strip, and '
         + 'never used by itself.',
    });
  }

  /* ==================================================================
     CHOOSING AN INPUT (2026-11-12: "I dont like that I have to click from
     a drop down. Have it say select Pool and then shows all pools and then
     click on that to see the versions... try to model it after other
     version selection GUIs throughout the UI"; "what it applies to is
     options for the Pooled tab").

     Add a set's shape (toolkit.js newSetDialog): one button that says what
     is chosen, or "Select pool". Pressed, a pop-up lists everything there is
     to choose from as rows, grouped by the folders they are filed in -- the
     Pooled tab's folders for a pool, the Workflow tab's for a workflow --
     with the archived ones in a drawer and a box to find one by name.
     Picking a row draws its whole version tree beneath it; "Use this
     version" takes the version lit there.
     ================================================================== */
  const has = (m, k) => Object.prototype.hasOwnProperty.call(m, k);

  /* The Pooled tab's folder a pool is in (rootcanal.js `folderOf`): where
     it was put, else -- saved before folders -- Preliminary analysis. */
  function poolFolderName(id) {
    const inm = prefOf('rootcanal_pool_in');
    const fs = prefOf('rootcanal_pool_folders');
    const fid = has(inm, id) ? inm[id] : 'prelim';
    if (!fid) return '';
    const f = fs[fid];
    if (f && !f.gone) return f.name || 'Untitled folder';
    return fid === 'prelim' && !f ? 'Preliminary analysis' : '';
  }

  const POOL_PICK = {
    nouns: ['pool', 'pools'], unit: 'events', empty: 'Select pool',
    count: (v) => v.events,
    line: (v) => [v.members != null ? plural(v.members, 'recording', 'recordings') : null,
                  v.mice != null ? plural(v.mice, 'mouse', 'mice') : null]
      .filter(Boolean).join(' · ') || null,
    why: () => null,
    items: () => ((W.sources || {}).pools || []).map((p) => {
      const vs = poolVersions(p);
      return {
        id: p.artifact_id, name: p.nickname || p.artifact_id,
        group: poolFolderName(p.artifact_id), shelved: poolShelved(p.artifact_id),
        versions: vs, dflt: p.version,
        what: [p.events != null ? Number(p.events).toLocaleString() + ' events' : null,
               p.members != null ? plural(p.members, 'recording', 'recordings') : null,
               p.mice != null ? plural(p.mice, 'mouse', 'mice') : null,
               plural(vs.length, 'version', 'versions'),
               p.all_ds ? 'every event taken as DS' : null].filter(Boolean).join(' · '),
      };
    }),
  };

  const wfPick = (k) => ({
    nouns: ['workflow', 'workflows'], unit: 'kept', empty: 'Select workflow',
    count: (v) => (v.ran ? v.kept : null),
    line: (v) => (v.ran ? 'a run' + (v.grace != null ? ', grace ' + graceWords(v.grace) : '')
                        : 'defined, not run'),
    why: (v) => (v.ran ? null : 'A definition saved and not run: it holds no border to lend.'),
    items: () => (W.list || []).filter((r) => r.kind === k).map((r) => {
      const vs = (r.versions || []).length ? r.versions
        : r.run_version ? [{ v: r.run_version, ran: true, kept: r.kept, here: true }] : [];
      return {
        id: r.artifact_id, name: r.nickname || r.name,
        group: folderOf(r).join(' › '), shelved: archived()[r.artifact_id] ? 'archived' : '',
        versions: vs, dflt: r.run_version || null,
        what: [r.ran ? 'last run v' + r.run_version : 'not run yet',
               r.kept != null ? Number(r.kept).toLocaleString() + ' kept' : null,
               r.grace != null ? 'grace ' + graceWords(r.grace) : null,
               r.shape ? SHAPE_WORD[r.shape] || r.shape : null,
               plural(vs.length, 'version', 'versions')].filter(Boolean).join(' · '),
      };
    }),
  });

  /* The button: what is chosen and its version, or "Select pool". */
  function inputControl(o) {
    const P = o.pick;
    const it = o.id ? P.items().find((x) => x.id === o.id) : null;
    const v = it ? (o.v != null ? Number(o.v) : it.dflt) : null;
    const ver = it ? it.versions.find((x) => Number(x.v) === v) : null;
    const newest = it && it.versions.length
      ? Math.max.apply(null, it.versions.map((x) => Number(x.v) || 0)) : null;
    const n = ver ? P.count(ver) : null;
    const btn = el('button', {
      type: 'button', class: 'vbtn wf-in' + (o.extra ? ' ' + o.extra : ''),
      'aria-haspopup': 'dialog', 'data-id': it ? it.id : '',
      'data-v': it && v != null ? String(v) : '',
      title: 'Every ' + P.nouns[0] + ' there is, and every version of the one '
             + 'picked. Click to choose.',
      onclick: () => inputDialog(Object.assign({}, o, { item: it, v })),
    }, it ? [
      el('span', { class: 'wf-in-name', text: it.name }),
      el('strong', { class: 'vbtn-n', text: v != null ? 'v' + v : 'no run yet' }),
      n != null ? el('span', { class: 'vbtn-c',
                               text: Number(n).toLocaleString() + ' ' + P.unit }) : null,
      it.shelved ? el('span', { class: 'vbtn-c', text: shelvedWords(it.shelved).slice(3) }) : null,
      el('span', { class: 'vbtn-caret', 'aria-hidden': 'true', text: '▾' }),
    ].filter(Boolean) : [
      el('strong', { class: 'wf-in-empty', text: P.empty }),
      el('span', { class: 'vbtn-caret', 'aria-hidden': 'true', text: '▾' }),
    ]);
    if (v == null || newest == null || v >= newest) return btn;
    return el('span', { class: 'wf-pin' }, [btn,
      el('span', { class: 'hint wf-newer', text: 'v' + newest + ' is newer' })]);
  }

  function inputDialog(o) {
    const P = o.pick;
    const items = P.items();
    const noun = P.nouns[0];
    let cur = o.item ? items.find((x) => x.id === o.item.id) || null : null;
    let ver = cur ? o.v : null;
    let q = '';
    const listBox = el('div', { class: 'bm-list wf-pick-list' });
    const verBox = el('div', { class: 'wf-pick-vers' });
    const say = el('p', { class: 'confirm-msg wf-pick-say' });
    const okBtn = el('button', { class: 'btn wf-pick-ok', text: 'Use this version',
                                 disabled: 'disabled' });
    const find = el('input', { type: 'search', class: 'wf-pick-find',
      placeholder: 'Find a ' + noun + ' by its name or folder…',
      oninput: (e) => { q = e.target.value; paintList(); } });

    const rowOf = (it) => el('label', {
      class: 'bm-row wf-pick-row' + (cur && cur.id === it.id ? ' on' : '')
             + (it.shelved ? ' is-archived' : ''),
      'data-id': it.id,
    }, [
      el('input', { type: 'radio', name: 'wfPick',
        checked: cur && cur.id === it.id ? 'checked' : null,
        onchange: () => choose(it) }),
      el('span', { class: 'mk-name', text: it.name }),
      it.shelved ? BARRY.ui.chip(shelvedWords(it.shelved).slice(3), { flag: true }) : null,
      el('span', { class: 'person-what', text: it.what }),
    ].filter(Boolean));

    // Folders by name, the unfiled last; the rows in each in number order.
    const grouped = (xs) => {
      const byG = new Map();
      for (const it of xs) {
        if (!byG.has(it.group)) byG.set(it.group, []);
        byG.get(it.group).push(it);
      }
      const names = Array.from(byG.keys()).sort((a, b) => (!a ? 1 : !b ? -1 : natural(a, b)));
      return names.map((g) => el('div', { class: 'wf-pick-group', 'data-group': g }, [
        el('div', { class: 'wf-pick-folder', text: g || 'Not in a folder' }),
      ].concat(byG.get(g).sort((a, b) => natural(a.name, b.name)).map(rowOf))));
    };

    function paintList() {
      listBox.innerHTML = '';
      const hit = items.filter((it) => BARRY.ui.searchMatch([it.name, it.group], q));
      const [live, gone] = BARRY.ui.splitArchived(hit, (it) => !!it.shelved);
      grouped(live).forEach((n) => listBox.appendChild(n));
      const tail = BARRY.ui.archivedTail({
        key: 'wf-pick-' + noun, items: gone, noun: P.nouns,
        render: (xs) => grouped(xs), onToggle: () => paintList(),
        forceOpen: !!(cur && gone.includes(cur)),
      });
      if (tail) listBox.appendChild(tail);
      if (!hit.length) {
        listBox.appendChild(el('p', { class: 'hint', text: q
          ? 'No ' + P.nouns[1] + ' match ‘' + q + '’.'
          : 'There are no ' + P.nouns[1] + ' to choose from yet.' }));
      }
    }

    function choose(it) {
      cur = it;
      ver = it.dflt != null ? Number(it.dflt) : null;
      if (o.item && o.item.id === it.id && o.v != null) ver = Number(o.v);
      listBox.querySelectorAll('.wf-pick-row').forEach((r) => {
        r.classList.toggle('on', r.dataset.id === it.id);
      });
      paintVers();
    }

    function sayIt() {
      const vv = cur && ver != null ? cur.versions.find((x) => Number(x.v) === Number(ver)) : null;
      if (!cur) {
        say.textContent = 'Pick a ' + noun + ' to see its versions.';
      } else if (!vv) {
        say.textContent = 'Pick one of its versions.';
      } else {
        const n = P.count(vv);
        say.textContent = '‘' + cur.name + '’ v' + vv.v
          + (n != null ? ', ' + Number(n).toLocaleString() + ' ' + P.unit : '')
          + (P.line(vv) ? ', ' + P.line(vv) : '') + '.';
      }
      const why = vv ? (vv.here === false ? NOT_HERE : P.why(vv)) : 'nothing chosen';
      okBtn.disabled = why ? 'disabled' : null;
    }

    function paintVers() {
      verBox.innerHTML = '';
      if (!cur) { sayIt(); return; }
      // The label is set in capitals; the name is not, so it is read as written.
      verBox.appendChild(el('div', { class: 'section-label', text: 'Versions' }));
      verBox.appendChild(el('div', { class: 'wf-pick-of', text: cur.name }));
      const pin = o.pinned && o.pinned.id === cur.id ? Number(o.pinned.v) : null;
      const tree = BARRY.ui.versionTree({
        versions: cur.versions.map((v) => ({
          v: v.v, at: v.at, by: v.by, here: v.here, raw: v, n: P.count(v),
          note: [v.nickname ? '‘' + v.nickname + '’' : null, v.note]
            .filter(Boolean).join(' · ') || null })),
        idOf: (v) => v.v, value: ver, unit: P.unit, producer: false, notes: true,
        disabled: (v) => (v.here === false ? NOT_HERE : P.why(v.raw)),
        state: (v) => (pin != null && Number(v.v) === pin ? ['what it is pinned to now'] : []),
        line: (v) => P.line(v.raw),
        onpick: (v) => { ver = v ? Number(v.v) : null; sayIt(); },
      });
      verBox.appendChild(el('div', { class: 'ncs-vers' }, [tree]));
      requestAnimationFrame(() => { if (tree.redraw) tree.redraw(); });
      sayIt();
    }

    okBtn.onclick = () => {
      if (!cur || ver == null) return;
      closeModal();
      o.onpick(cur.id, Number(ver));
      refresh();
    };
    paintList();
    paintVers();
    showModal(el('div', { class: 'ncs-modal wf-pick-dlg' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: o.title }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal, title: 'Close',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb ncs' }, [
        o.sub ? el('p', { class: 'hint wf-pick-sub', text: o.sub }) : null,
        // Which one on the left, its versions on the right; one above the
        // other on a narrow window.
        el('div', { class: 'wf-pick-cols' }, [
          el('div', { class: 'wf-pick-left' }, [
            el('div', { class: 'section-label',
                        text: P.nouns[1][0].toUpperCase() + P.nouns[1].slice(1) }),
            find, listBox,
          ]),
          el('div', { class: 'wf-pick-right' }, [verBox, say]),
        ]),
      ]),
      BARRY.ui.modalFoot(null, [
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        okBtn,
      ]),
    ]));
    const on = listBox.querySelector('.wf-pick-row.on');
    if (on && on.scrollIntoView) on.scrollIntoView({ block: 'nearest' });
  }

  function builderCard() {
    const B = W.builder;
    const S = W.sources || { pools: [], sets: [] };
    // An archived pool is left out of Pooled PCA's list unless it is picked
    // already, or Show archived is on -- then it says so. (The pickers keep
    // theirs in a drawer of their own.)
    const nShelved = (S.pools || []).filter((p) => poolShelved(p.artifact_id)).length;
    const offered = (keep) => (S.pools || []).filter((p) => W.builderArch
      || !poolShelved(p.artifact_id) || keep(p.artifact_id));
    // Which pool, and which of its versions: one button, one pop-up
    // (2026-11-12).
    const PIN = B.pinned || {};
    const poolIn = (slot, title, sub) => {
      const amb = slot === 'target' && B.kind === 'ambiguous';
      const at = amb ? ambTarget(B)
        : slot === 'source' ? { id: B.source, v: B.sourceV } : { id: B.target, v: B.targetV };
      return inputControl({
        pick: POOL_PICK, id: at.id, v: at.v, extra: 'wf-in-' + slot,
        pinned: PIN[slot] || null, title, sub,
        onpick: (id, v) => {
          if (slot === 'source') { B.source = id; B.sourceV = v; return; }
          B.target = id; B.targetV = v; W.prep = null;
          if (amb) B.ambTargetSet = true;
        },
      });
    };
    const archBtn = nShelved || W.builderArch ? BARRY.ui.button({ kind: 'ghost',
      size: 'sm', extra: 'wf-b-arch',
      text: (W.builderArch ? 'Hide' : 'Show') + ' archived pools · ' + nShelved,
      title: 'Pools archived in Pooled, or in a folder archived there, are not '
             + 'offered unless shown.',
      onclick: () => { W.builderArch = !W.builderArch; refresh(); } }) : null;
    // Which workflow, and which of its runs.
    const wfOpts = (k) => inputControl({
      pick: wfPick(k), id: B.uses[k], v: B.usesV[k], extra: 'wf-in-' + k,
      pinned: (PIN.uses || {})[k] || null,
      title: k === 'ds' ? 'The DS border: which workflow, which run'
                        : 'The P-spike border: which workflow, which run',
      sub: 'Its border is the one this workflow borrows. Only a version that '
         + 'holds a run has a border.',
      onpick: (id, v) => { B.uses[k] = id; B.usesV[k] = v; },
    });
    const rows = [
      el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'Which' }),
        BARRY.ui.seg(KIND_ORDER.map((k) => [k, KIND_WORDS[k]]), B.kind,
                     (v) => { B.kind = v; W.prep = null; refresh(); }),
      ]),
      el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'Name' }),
        el('input', { type: 'text', class: 'wf-name-in', value: B.nickname,
          placeholder: 'e.g. ' + KIND_WORDS[B.kind] + ' · PTEN baseline',
          oninput: (e) => { B.nickname = e.target.value; } }),
      ]),
      el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'Folder' }),
        el('input', { type: 'text', class: 'wf-folder-in', value: B.folder || '',
          placeholder: 'e.g. Snap/10% (empty for none)',
          oninput: (e) => { B.folder = e.target.value; } }),
      ]),
    ];
    if (B.kind === 'pca' && archBtn) {
      rows.push(el('div', { class: 'wf-b-row' }, [archBtn]));
    }
    if (B.kind === 'ds') {
      rows.push(el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'Border around DS, from' }),
        poolIn('source', 'The pool the DS border is drawn around',
               'A pool from the Pooled tab, and which of its versions. Every '
               + 'event in it is taken as a dentate spike: the controls.'),
        el('span', { class: 'hint', text: 'Every event of this pool is taken as a '
          + 'dentate spike: the controls.' }),
      ]));
    }
    if (B.kind === 'pspike') {
      rows.push(el('div', { class: 'wf-b-row wf-b-col' }, [
        el('span', { class: 'wf-b-l', text: 'Border around P-spikes, from' }),
        el('div', { class: 'wf-sets' }, (S.sets || []).map((s) => el('label', {
          class: 'wf-set' }, [
          el('input', { type: 'checkbox', checked: B.sets.has(s.entry_id) ? 'checked' : null,
            onchange: (e) => { if (e.target.checked) B.sets.add(s.entry_id);
                               else B.sets.delete(s.entry_id); W.prep = null; refresh(); } }),
          el('span', { text: s.session_label + ' · ' + s.n + ' · ' + s.name }),
          s.aligned ? BARRY.ui.chip('aligned ' + s.aligned_name, { kind: 'ok' })
                    : BARRY.ui.chip('not aligned'),
        ]))),
        prepCard(),
      ]));
    }
    if (B.kind === 'pca') {
      rows.push(el('div', { class: 'wf-b-row wf-b-col' }, [
        el('span', { class: 'wf-b-l', text: 'Pools to make one pool of' }),
        el('div', { class: 'wf-sets wf-pools' }, offered((id) => B.pools.has(id)).map((p) => {
          const why = poolShelved(p.artifact_id);
          return el('label', { class: 'wf-set' + (why ? ' archived' : ''),
                               'data-pool': p.artifact_id }, [
            el('input', { type: 'checkbox', checked: B.pools.has(p.artifact_id) ? 'checked' : null,
              onchange: (e) => { if (e.target.checked) B.pools.add(p.artifact_id);
                                 else B.pools.delete(p.artifact_id); refresh(); } }),
            el('span', { text: p.nickname + shelvedWords(why) }),
            // A button in a label does not tick its box.
            poolPin(p.artifact_id, B.poolV.get(p.artifact_id),
                    (v) => { B.poolV.set(p.artifact_id, v); },
                    B.pinned ? B.pinned.pools.get(p.artifact_id) : null),
            why === 'archived' ? BARRY.ui.button({ kind: 'mini', text: 'Put back',
              extra: 'wf-pool-unarchive',
              title: 'Back in the saved pools, everyone’s, once it syncs.',
              onclick: (e) => { e.preventDefault(); putBackPool(p); } }) : null,
          ].filter(Boolean));
        })),
        el('span', { class: 'hint', text: B.pools.size + ' picked. Their events are '
          + 'clustered again as one pool, and the PCA is drawn from all of them.' }),
      ]));
      rows.push(el('div', { class: 'wf-b-row' }, [
        el('label', { class: 'wf-set' }, [
          el('input', { type: 'checkbox', checked: B.pcaUses ? 'checked' : null,
            onchange: (e) => { B.pcaUses = e.target.checked; refresh(); } }),
          el('span', { text: 'Also colour by the verified borders, from' })]),
        B.pcaUses ? wfOpts('ds') : null,
        B.pcaUses ? wfOpts('pspike') : null,
      ].filter(Boolean)));
    } else if (B.kind !== 'ambiguous') {
      rows.push(el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'Applied to' }),
        poolIn('target', 'The pool the border is applied to',
               'A pool from the Pooled tab, and which of its versions. What is '
               + 'inside the border is what the workflow extracts.'),
      ]));
      rows.push(el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'Grace' }),
        BARRY.ui.seg(GRACES.map(([g, w]) => [String(g), w]),
                     B.custom !== '' ? '' : String(B.grace),
                     (v) => { B.grace = Number(v); B.custom = ''; refresh(); }),
        el('input', { type: 'number', class: 'wf-custom', min: '0', max: '50',
          step: '0.5', value: B.custom, placeholder: 'custom %',
          oninput: (e) => { B.custom = e.target.value; } }),
        el('span', { class: 'hint', text: 'The share of the border’s own events '
          + 'the box may leave out.' }),
      ]));
      rows.push(el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'Shape' }),
        BARRY.ui.seg(SHAPES_OFFERED, B.shape || 'box', (v) => { B.shape = v; refresh(); }, { extra: 'wf-b-shape' }),
        el('span', { class: 'hint' + (RETIRED[B.shape] ? ' wf-retired' : ''),
          text: RETIRED[B.shape]
          ? RETIRED[B.shape]
          : B.shape === 'hull'
            ? 'The snap: the tightest border with no dents, its corners the outermost events; the grace peels them off one at a time.'
            : 'The box: on each axis, the range of the events.' }),
      ]));
    } else {
      rows.push(el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'DS border from' }), wfOpts('ds')]));
      rows.push(el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'P-spike border from' }), wfOpts('pspike')]));
      rows.push(el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'wf-b-l', text: 'Applied to' }),
        poolIn('target', 'The pool both borders are applied to',
               'A pool from the Pooled tab, and which of its versions. Until '
               + 'you pick one, it is the DS workflow’s own target.'),
        B.ambTargetSet ? null : el('span', { class: 'hint wf-amb-default',
          text: 'The DS workflow’s own target, until you pick another.' }),
      ].filter(Boolean)));
      rows.push(el('p', { class: 'hint', text: 'Inside both borders is the '
        + 'Twilight Zone. Every event is shown; Bank by label… on the Extract stage '
        + 'banks the labels you pick.' }));
    }
    rows.push(el('div', { class: 'wf-b-row' }, [
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Preview',
        extra: 'wf-preview', title: 'Everything a run would find, with nothing '
          + 'saved.', onclick: () => previewBuilder() }),
      BARRY.ui.button({ kind: 'primary', size: 'sm',
        text: B.artifact_id ? 'Save as the next version' : 'Save',
        extra: 'wf-save', onclick: () => saveBuilder() }),
      BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Cancel',
        onclick: () => { W.builder = null; W.preview = null; W.prep = null; refresh(); } }),
      W.busy ? BARRY.ui.chip(W.busy) : null,
    ].filter(Boolean)));
    return el('div', { class: 'card wf-builder' }, [
      el('strong', { text: B.artifact_id ? 'Edit ‘' + B.nickname + '’' : 'New workflow' }),
    ].concat(rows));
  }

  /* A POOL NOT YET PICKED (2026-11-13). The builder's own defaults are found
     by name ("PTEN Baseline", "CTL Baseline"), and the pools on show are
     named otherwise now ("PTEN Baseline v2 (Optimized parameters)"), so a
     new one can open on "Select pool". Saved like that, the server said
     "There is no saved pool None to use as the target" and filed it as a
     fault (11-12). Said here, by the button's own words, and nothing sent. */
  function missingPool(B) {
    if (B.kind !== 'ds' && B.kind !== 'pspike') return null;
    if (B.kind === 'ds' && !B.source) {
      return { which: 'source', say: 'Pick the pool the DS border is drawn around first.' };
    }
    if (!B.target) return { which: 'target', say: 'Pick the pool it is applied to first.' };
    return null;
  }

  function sayMissingPool(B) {
    const miss = missingPool(B);
    if (!miss) return false;
    toast(miss.say, 'warn', 6000);
    const b = root && root.querySelector('.wf-builder .wf-in-' + miss.which);
    if (b) b.focus();
    return true;
  }

  async function previewBuilder() {
    if (W.busy) return;
    if (W.builder && sayMissingPool(W.builder)) return;
    W.busy = 'Previewing';
    refresh();
    try {
      const got = await apiPost('/api/rootcanal/workflow/preview', builderBody());
      W.preview = { definition: got.definition, run: got.run };
      W.openId = null;
      W.stage = 'apply';
      W.picked = null;
    } catch (e) {
      toast('No preview: ' + e.message, 'err', 14000);
    }
    W.busy = null;
    refresh();
  }

  async function saveBuilder() {
    const B = W.builder;
    if (!B) return;
    if (!String(B.nickname || '').trim()) {
      toast('Give it a name first.', 'warn', 6000);
      const n = root && root.querySelector('.wf-name-in');
      if (n) n.focus();
      return;
    }
    if (sayMissingPool(B)) return;
    let got;
    try {
      got = await apiPost('/api/rootcanal/workflow/save',
                          Object.assign(builderBody(), { artifact_id: B.artifact_id }));
    } catch (e) {
      toast('Not saved: ' + e.message, 'err', 12000);
      return;
    }
    toast('Saved ‘' + got.nickname + '’ v' + got.version + '. Press Run on its '
          + 'strip to define, apply and extract.', 'ok', 8000);
    // Only this builder: another opened while the save was on its way stays.
    if (W.builder === B) {
      W.builder = null;
      W.prep = null;
    }
    W.preview = null;
    W.openId = got.artifact_id;
    W.list = null;
    await loadList();
    await loadOne(got.artifact_id, null);
  }

  /* ---------- the hand-sorted sets, made ready ---------- */
  function prepCard() {
    const P = W.prep;
    const kids = [
      el('div', { class: 'wf-b-row' }, [
        el('span', { class: 'hint', text: 'Each set has to be on the recording’s '
          + 'own clock, aligned (Eye), and read here, measured the way the '
          + 'target was, before a border can be drawn around it.' }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Check the sets',
          extra: 'wf-prep-check', onclick: () => checkPrep() }),
        P && P.sets && P.sets.some((s) => s.clock && s.clock.retime || !s.aligned || !s.read)
          ? BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'Prepare all',
              extra: 'wf-prep-go', disabled: !!(P && P.running),
              title: 'Retime what needs it, align what is not aligned (Eye, '
                     + 'committed as it lands), then read each one here.',
              onclick: () => prepareAll() }) : null,
      ].filter(Boolean)),
    ];
    if (P && P.err) kids.push(el('p', { class: 'hint wf-err', text: P.err }));
    if (P && P.say) kids.push(el('p', { class: 'hint', text: P.say }));
    if (P && P.sets) {
      kids.push(el('table', { class: 'wf-prep' }, [
        el('tr', {}, ['set', 'clock', 'aligned', 'read here'].map((t) => el('th', { text: t }))),
        ...P.sets.map((s) => el('tr', {}, [
          el('td', { text: (s.session_label || s.entry_id) + ' · ' + (s.n || 0) }),
          el('td', { class: s.clock && s.clock.retime ? 'wf-out' : 'wf-in',
                     text: s.clock && s.clock.retime ? 'needs retiming'
                       : 'on the recording’s clock',
                     title: (s.clock || {}).why || '' }),
          el('td', { class: s.aligned ? 'wf-in' : 'wf-out',
                     text: s.aligned ? s.aligned_name : 'not yet' }),
          el('td', { class: s.read ? 'wf-in' : 'wf-out',
                     text: s.read ? 'yes' : 'not yet', title: s.read_why || '' }),
        ])),
      ]));
    }
    return el('div', { class: 'wf-prep-card' }, kids);
  }

  async function checkPrep() {
    const B = W.builder;
    W.prep = Object.assign({}, W.prep, { say: 'Checking the sets…', err: null });
    refresh();
    try {
      W.prep = { sets: await checkSets(Array.from(B.sets), targetRef()),
                 say: null };
    } catch (e) {
      W.prep = { err: e.message };
    }
    refresh();
  }

  async function waitJob(id, say) {
    for (let k = 0; k < 3600; k++) {
      let j;
      try { j = (await api('/api/cfc/job/' + encodeURIComponent(id))).job || {}; }
      catch (e) { return { status: 'error', error: e.message }; }
      if (j.status && j.status !== 'running' && j.status !== 'queued') return j;
      const st = (j.stages || [])[0] || {};
      if (say) say(st.of ? ' — ' + (st.done || 0) + ' of ' + st.of : '');
      await new Promise((r) => setTimeout(r, 1500));
    }
    return { status: 'error', error: 'it took too long' };
  }

  async function prepareAll() {
    const B = W.builder;
    W.prep = Object.assign({}, W.prep || {}, { running: true, err: null });
    refresh();
    const got = await prepareSets(Array.from(B.sets), targetRef(),
      (t) => { if (W.prep) { W.prep.say = t + '…'; refresh(); } });
    W.sources = null;
    await loadSources();
    W.prep = { sets: got.sets, running: false,
               say: got.fails.length ? 'Not everything is ready: ' + got.fails.join('; ')
                 : 'Every set is ready: on its clock, aligned and read here.' };
    refresh();
  }

  function reset() {
    W.list = null; W.data = {}; W.openId = null; W.preview = null;
    W.builder = null; W.prep = null; W.sources = null; W.picked = null;
    W.ev = null; W.avg = null; W.ambPick = new Set();
  }

  return {
    node, reset,
    // For the harness.
    _state: () => W,
    _draw: () => drawAll(),
    _pointsOf: pointsOf,
    _rangesOf: rangesOf,
    _boxesOf: boxesOf,
    _shownRun: () => shownRun(),
    _haloClass: haloClass,
    _pcWords: pcWords,
  };
})();
