/* ==========================================================================
   drift.js -- Drift, step four of The Arc.

   A LEFT group and a RIGHT group of circuit artifacts (one recording each),
   each pooled -- recordings are the unit, weighted by precision,
   DerSimonian-Laird -- and the delta tested per cell with a
   Benjamini-Hochberg q per panel. backend/drift.py is the arithmetic,
   backend/driftrun.py makes one from the artifact store, and the result is
   filed as a Drift artifact that pins, and cites, the exact circuit versions
   it read.

   What this file owns

     the panel      two columns of members, a picker of every circuit (and
                    every older version of each), the pre-flight that says in
                    words what is incompatible and why -- with the explicit
                    "treat these as equivalent" choice when the cue pairing
                    is the only problem -- then where it runs, the cost, and
                    one primary, Compare.
     the renderer   `renderDrift(host, payload, meta)`: window x method, a
                    Left / Delta / Right switch, the matrix and the ring. ONE
                    function for the panel and for Results' viewer
                    (registered at the bottom), so a drift is drawn one way
                    wherever it is looked at.
     Use in Drift   an action on every circuit in Results, which lands that
                    exact version on the side you choose.

   The matrix is Coupling's (`BARRY.arc.shared`: crosshair, colour ramps,
   abbreviations) -- the same `.arc-mx` a circuit draws. The ring IS
   circuit.js's (`BARRY.circuit.ringInto`), fed deltas: same layout, same
   atlas colours, same downloads.

   Significance is marked, never starred: a cell whose q passes .05, .01 or
   .001 gets an outline one, two or three pixels thick (`data-sig` 1-3), and
   the ring draws the cells whose q passes the chosen threshold. A cell that
   could not be tested shows its delta and says why; a cell nobody could
   compute is blank with the reason; a grey region is grey. Absent is not
   negative.
   ========================================================================== */
'use strict';

BARRY.drift = (function () {
  const WINDOW_SAY = {
    pre: 'baseline', cue1: 'cue 1', cue2: 'cue 2', post: 'after cue 2',
    onset: 'cue 1 onset', switch: 'cue 1 → cue 2', offset: 'cue 2 offset',
  };
  const METHOD_NAME = {
    coherence: 'Coherence', raw_cc: 'Raw cross-correlation',
    amp_cc: 'Amplitude cross-correlation',
  };
  const KIND_SAY = { state: 'State', transition: 'Transition' };
  /* The three q levels a cell can pass, strictest first. */
  const SIG = [[0.001, 3, 'q < .001'], [0.01, 2, 'q < .01'], [0.05, 1, 'q < .05']];
  const K1_SAY = 'one recording — no between-recording spread can be estimated';

  const say = (w) => WINDOW_SAY[w] || w;
  const plural = (n, one, many) => n + ' ' + (n === 1 ? one : (many || one + 's'));
  const fmt = (v, d) => (v == null || !isFinite(v)) ? '—'
    : Number(v).toFixed(d == null ? 3 : d);
  const fmtP = (p) => p == null ? '—'
    : (p < 0.0001 ? Number(p).toExponential(1) : Number(p).toFixed(4));
  const short = (v) => {
    const s = Number(v).toFixed(2).replace(/^(-?)0\./, '$1.');
    return s === '-.00' ? '.00' : s;
  };
  const sigOf = (q) => {
    if (q == null) return 0;
    for (const [t, n] of SIG) if (q < t) return n;
    return 0;
  };
  const log = (what, data) => {
    try { if (BARRY.activity) BARRY.activity.log(what, data); } catch (e) { /* no-op */ }
  };
  const inToolkit = () => !!(BARRY.views && BARRY.views.toolkit
    && typeof BARRY.views.toolkit.tool === 'function'
    && BARRY.views.toolkit.tool() === 'drift');
  const shared = () => (BARRY.arc && BARRY.arc.shared) || null;
  function cellColour(v, diverging) {
    const s = shared();
    if (s && s.cellColour) return s.cellColour(v, diverging);
    return 'transparent';
  }
  function shortRegion(name) {
    const s = shared();
    if (s && s.shortRegion) return s.shortRegion(name);
    const bits = String(name).split(' ');
    return (bits[0] || '').charAt(0) + (bits[1] || name);
  }
  const nameOf = (m) => m.nickname || m.name || m.artifact_id || m.id;

  /* ==================================================================
     The panel's state. Held here, not in the DOM: the ToolKit paints a
     step twice on the way in (toolkit-renders-twice), and a member kept in
     a node would be lost on the second paint.
     ================================================================== */
  const st = {
    rows: null, rowsErr: null, rowsKey: null,
    find: '', rat: '', phase: '', cue: '', kind: 'state',
    left: [], right: [],
    labels: { left: 'Left', right: 'Right' },
    eq: [],                  // the recorded cue equivalence, [{from, to, by, at}]
    check: null, checkErr: null, checkKey: null,
    where: 'local', nickname: '',
    busy: false, job: null, jobStop: null,
    shown: null, shownErr: null,
    pickVer: {},             // artifact id -> the version id chosen in the picker
  };
  /* How a drift is being looked at, shared by every drift on screen. */
  const view = { side: 'delta', win: {}, method: 'coherence', edge: 'q',
                 q: 0.05, abs: {}, sideThr: {}, sel: null };

  /* ------------------------------------------------------------------
     Painting
     ------------------------------------------------------------------ */
  function paint(host) {
    host = host || document.getElementById('tkResult');
    if (!host) return;
    if (BARRY.circuit && BARRY.circuit.loadRegions) BARRY.circuit.loadRegions();
    host.appendChild(el('div', { class: 'arc-spark dr-panel' }, [
      el('div', { class: 'card dr-groups', id: 'drGroups' }),
      el('div', { class: 'card dr-pre', id: 'drPre' }),
      el('div', { class: 'card dr-pick', id: 'drPick' }),
      el('div', { id: 'drRun' }),
      el('div', { id: 'drShown' }),
    ]));
    render();
    if (st.rows === null && !st.rowsErr) loadRows();
    else if (st.rowsKey !== chosenKey()) loadRows();
  }

  function render() {
    renderGroups(); renderPre(); renderPick(); paintRun(); renderShown();
  }

  /* ------------------------------------------------------------------
     The circuits on offer. Asked again whenever the chosen set changes,
     because the server says which rows fit it.
     ------------------------------------------------------------------ */
  const chosenKey = () => st.left.concat(st.right)
    .map((m) => m.id + '@' + m.version_id).sort().join(',');
  let rowsAsk = null, rowsWant = null;
  function loadRows() {
    const key = chosenKey();
    rowsWant = key;
    if (rowsAsk) return rowsAsk;
    rowsAsk = (async () => {
      try {
        while (true) {
          const k = rowsWant;
          const got = await api('/api/arc/drift/circuits' + (k ? '?with='
                                + encodeURIComponent(k) : ''));
          if (k !== rowsWant) continue;
          st.rows = got.rows || [];
          st.rowsErr = null;
          st.rowsKey = k;
          break;
        }
      } catch (e) {
        st.rowsErr = e.message;
        if (!/older code/.test(e.message || '')) {
          reportClientError('drift.circuits', e.message, e.stack);
        }
      } finally {
        rowsAsk = null;
      }
      if (document.getElementById('drPick')) renderPick();
    })();
    return rowsAsk;
  }

  function rowOf(id) {
    return (st.rows || []).find((r) => r.artifact_id === id) || null;
  }

  /* ==================================================================
     The two groups
     ================================================================== */
  function memberOf(row, versionId) {
    const v = (row.versions || []).find((x) => x.version_id === versionId)
      || (row.versions || []).find((x) => x.current) || {};
    return {
      id: row.artifact_id, version_id: v.version_id || row.version_id,
      version: v.v != null ? v.v : row.version, digest: v.digest || row.digest,
      name: row.name, nickname: row.nickname,
      n_pairs: v.n_pairs != null ? v.n_pairs : row.n_pairs,
      cue_type: row.cue_type, cue_label: row.cue_label, kind: row.kind,
      gid: row.gid, group: row.group, current: !!v.current,
    };
  }

  function add(side, member) {
    if (side !== 'left' && side !== 'right') throw new Error('add(side, member)');
    const other = side === 'left' ? 'right' : 'left';
    const same = (m) => m.id === member.id && m.version_id === member.version_id;
    st[side] = st[side].filter((m) => m.id !== member.id);
    st[other] = st[other].filter((m) => !same(m));
    st[side].push(member);
    changed();
    return true;
  }

  function remove(side, id) {
    st[side] = st[side].filter((m) => m.id !== id);
    changed();
  }

  function move(from, id) {
    const to = from === 'left' ? 'right' : 'left';
    const m = st[from].find((x) => x.id === id);
    if (!m) return;
    st[from] = st[from].filter((x) => x.id !== id);
    st[to] = st[to].filter((x) => x.id !== id);
    st[to].push(m);
    changed();
  }

  /* Anything about the members moved: the pre-flight and the picker's
     compatibility are read again, and a result on screen describing some
     other set stays up but is no longer claimed to be this one. */
  function changed() {
    // An equivalence is kept only while both cue types are still present.
    const types = new Set(st.left.concat(st.right).map((m) => m.cue_type));
    st.eq = st.eq.filter((e) => types.has(e.from) && types.has(e.to));
    st.check = null; st.checkErr = null;
    if (!document.getElementById('drGroups')) return;
    renderGroups();
    askCheck();
    loadRows();
  }

  function renderGroups() {
    const box = document.getElementById('drGroups');
    if (!box) return;
    box.innerHTML = '';
    box.appendChild(el('div', { class: 'section-label', text: 'The two groups' }));
    box.appendChild(el('p', { class: 'hint', text: 'Each circuit is one '
      + 'recording. Each group is averaged with recordings as the unit, and '
      + 'Drift reports right minus left. Drag a circuit between the columns, '
      + 'or use its arrow.' }));
    box.appendChild(el('div', { class: 'dr-cols' },
      ['left', 'right'].map((s) => column(s))));
  }

  function column(side) {
    const list = st[side];
    const pairs = list.reduce((a, m) => a + (Number(m.n_pairs) || 0), 0);
    const col = el('div', { class: 'dr-col', 'data-side': side,
      ondragover: (e) => { e.preventDefault(); col.classList.add('drop'); },
      ondragleave: () => col.classList.remove('drop'),
      ondrop: (e) => {
        e.preventDefault(); col.classList.remove('drop');
        let d = null;
        try { d = JSON.parse(e.dataTransfer.getData('text/plain') || 'null'); } catch (x) { d = null; }
        if (!d || !d.id) return;
        if (d.from && d.from !== side) move(d.from, d.id);
        else if (!d.from) {
          const r = rowOf(d.id);
          if (r) add(side, memberOf(r, d.version_id));
        }
      },
    });
    const label = el('input', {
      type: 'text', class: 'dr-label', maxlength: '80', value: st.labels[side],
      'aria-label': 'Name of the ' + side + ' group',
      placeholder: side === 'left' ? 'Type a name, e.g. Precon1…'
                                   : 'Type a name, e.g. Precon4…',
      oninput: (e) => { st.labels[side] = e.target.value; },
      onchange: () => { renderPre(); },
    });
    col.appendChild(el('div', { class: 'dr-col-head' }, [
      el('span', { class: 'dr-side', text: side === 'left' ? 'Left' : 'Right' }),
      label,
    ]));
    col.appendChild(el('p', { class: 'hint dr-col-n', text: list.length
      ? plural(list.length, 'recording') + ' · ' + plural(pairs, 'cue pair')
      : 'no circuits yet' }));
    if (list.length === 1) {
      col.appendChild(el('p', { class: 'hint dr-k1', text: 'This group is '
        + K1_SAY + ': its SE describes that one recording, not a group.' }));
    }
    if (!list.length) {
      col.appendChild(el('div', { class: 'empty-state dr-empty' }, [
        el('p', { text: 'Add circuits from the list below, or drag one here.' }),
      ]));
      return col;
    }
    for (const m of list) col.appendChild(memberRow(side, m));
    return col;
  }

  function memberRow(side, m) {
    const other = side === 'left' ? 'right' : 'left';
    return el('div', {
      class: 'dr-mem', draggable: 'true', 'data-id': m.id, 'data-vid': m.version_id,
      ondragstart: (e) => {
        e.dataTransfer.setData('text/plain', JSON.stringify({ id: m.id, from: side }));
        e.dataTransfer.effectAllowed = 'move';
      },
    }, [
      el('div', { class: 'dr-mem-t' }, [
        el('strong', { text: nameOf(m) }),
        m.nickname ? el('span', { class: 'dr-mem-name', text: m.name }) : null,
        el('span', { class: 'dr-mem-v', text: [
          'v' + m.version + (m.current === false ? ' (an older version)' : ''),
          m.n_pairs != null ? plural(m.n_pairs, 'cue pair') : null,
          m.cue_label, m.kind,
        ].filter(Boolean).join(' · ') }),
      ].filter(Boolean)),
      el('div', { class: 'dr-mem-acts' }, [
        el('button', { class: 'mini', 'data-act': 'move',
          text: side === 'left' ? 'To the right →' : '← To the left',
          title: 'Move it to the ' + other + ' group',
          onclick: () => move(side, m.id) }),
        el('button', { class: 'mini', 'data-act': 'remove', text: 'Remove',
          title: 'Take it out of the comparison. The circuit itself is not touched.',
          onclick: () => remove(side, m.id) }),
      ]),
    ]);
  }

  /* ==================================================================
     The picker
     ================================================================== */
  function hay(r) {
    return [r.nickname, r.name, r.group, r.cue_label, r.cue_type, r.kind,
            r.session_label, r.gid, r.mouse != null ? 'r' + r.mouse : '']
      .join(' ').toLowerCase();
  }

  function shownRows() {
    const q = st.find.trim().toLowerCase();
    return (st.rows || []).filter((r) =>
      (!st.kind || r.kind === st.kind)
      && (!st.rat || String(r.mouse) === st.rat)
      && (!st.phase || (r.phase || '') + (r.phase_n == null ? '' : r.phase_n) === st.phase)
      && (!st.cue || r.cue_type === st.cue)
      && (!q || q.split(/\s+/).every((t) => hay(r).includes(t))));
  }

  function renderPick() {
    const box = document.getElementById('drPick');
    if (!box) return;
    box.innerHTML = '';
    box.appendChild(el('div', { class: 'section-label', text: 'Circuits' }));
    if (st.rowsErr) {
      box.appendChild(el('div', { class: 'empty-state dr-missing' }, [
        el('p', { text: /older code/.test(st.rowsErr)
          ? st.rowsErr + ' Restart Jarvis to pick up Drift.'
          : 'The circuits could not be read: ' + st.rowsErr }),
        el('button', { class: 'btn ghost sm', text: 'Read them again',
                       onclick: () => { st.rowsErr = null; renderPick(); loadRows(); } }),
      ]));
      return;
    }
    if (st.rows === null) {
      const hold = el('div', {});
      box.appendChild(hold);
      BARRY.skeleton.into(hold, 'row', 5);
      return;
    }
    if (!st.rows.length) {
      box.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'There are no circuits yet. Make some in Circuit, the '
                        + 'step before this one; each one you make is listed here.' }),
      ]));
      return;
    }
    const all = st.rows;
    const opts = (vals, first) => [el('option', { value: '', text: first })]
      .concat(vals.map(([v, t]) => el('option', { value: v, text: t })));
    const uniq = (xs) => Array.from(new Map(xs.map((x) => [x[0], x])).values())
      .sort((a, b) => String(a[1]).localeCompare(String(b[1]), undefined, { numeric: true }));
    const sel = (key, vals, first, label) => {
      const s = el('select', { class: 'dr-filter', 'data-filter': key, 'aria-label': label,
        onchange: (e) => { st[key] = e.target.value; renderPick(); } }, opts(vals, first));
      s.value = st[key];
      return s;
    };
    box.appendChild(el('div', { class: 'dr-filters' }, [
      BARRY.ui.searchField({
        value: st.find, placeholder: 'Type a rat, phase, cue or name…',
        oninput: (e) => { st.find = e.target.value; keepFocus(() => renderPick()); },
      }),
      el('div', { class: 'seg dr-kinds' }, ['state', 'transition'].map((k) => el('button', {
        class: st.kind === k ? 'active' : '', 'data-kind': k, text: KIND_SAY[k],
        onclick: () => { st.kind = k; renderPick(); },
      }))),
      sel('rat', uniq(all.filter((r) => r.mouse != null).map((r) => [String(r.mouse), 'r' + r.mouse])),
          'Every rat', 'Rat'),
      sel('phase', uniq(all.filter((r) => r.phase).map((r) => {
        const p = r.phase + (r.phase_n == null ? '' : r.phase_n); return [p, p];
      })), 'Every phase', 'Phase'),
      sel('cue', uniq(all.map((r) => [r.cue_type, r.cue_label || r.cue_type])),
          'Every cue pairing', 'Cue pairing'),
    ]));
    const rows = shownRows();
    box.appendChild(el('p', { class: 'hint dr-count', text: rows.length + ' of '
      + plural(all.length, 'circuit') + (rows.length < all.length
        ? ' — the filters above narrow it' : '') }));
    if (!rows.length) {
      box.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'Nothing matches. Clear the search or set the filters '
                        + 'back to every rat, phase and cue pairing.' }),
      ]));
      return;
    }
    const list = el('div', { class: 'dr-list' });
    let g = null;
    for (const r of rows) {
      if (r.group !== g) {
        g = r.group;
        list.appendChild(el('div', { class: 'art-group dr-group', text: g }));
      }
      list.appendChild(pickRow(r));
    }
    box.appendChild(list);
  }

  function sideOf(id) {
    if (st.left.some((m) => m.id === id)) return 'left';
    if (st.right.some((m) => m.id === id)) return 'right';
    return null;
  }

  function pickRow(r) {
    const on = sideOf(r.artifact_id);
    const vid = st.pickVer[r.artifact_id] || r.version_id;
    const vers = r.versions || [];
    const verSel = vers.length > 1 ? el('select', {
      class: 'dr-ver', 'aria-label': 'Which version',
      title: 'A drift pins the exact version it reads. The current one is first.',
      onchange: (e) => { st.pickVer[r.artifact_id] = e.target.value; },
    }, vers.map((v) => el('option', { value: v.version_id,
      text: 'v' + v.v + (v.current ? ' (current)' : '') + (v.n_pairs != null
        ? ' · ' + plural(v.n_pairs, 'pair') : '') + (v.here === false
        ? ' · not on this computer' : '') }))) : null;
    if (verSel) verSel.value = vid;
    const note = r.compatible === false
      ? el('span', { class: 'dr-row-why' + (r.cue_only ? ' cue' : ''),
                     text: (r.cue_only ? 'Another cue pairing: ' : 'Does not fit: ')
                           + r.why.join('; ') })
      : null;
    const addTo = (side) => () => add(side, memberOf(r, st.pickVer[r.artifact_id]
                                                      || r.version_id));
    return el('div', {
      class: 'dr-row' + (on ? ' on' : '') + (r.compatible === false ? ' off' : ''),
      'data-id': r.artifact_id, draggable: 'true',
      ondragstart: (e) => e.dataTransfer.setData('text/plain', JSON.stringify(
        { id: r.artifact_id, version_id: st.pickVer[r.artifact_id] || r.version_id })),
    }, [
      el('div', { class: 'dr-row-t' }, [
        el('strong', { text: r.nickname || r.name }),
        r.nickname ? el('span', { class: 'dr-row-name', text: r.name }) : null,
        el('span', { class: 'dr-row-v', text: [
          r.cue_label, r.kind, r.n_pairs != null ? plural(r.n_pairs, 'cue pair') : null,
          vers.length > 1 ? plural(vers.length, 'version') : 'v' + r.version,
          on ? 'in the ' + on + ' group' : null,
        ].filter(Boolean).join(' · ') }),
        note,
      ].filter(Boolean)),
      el('div', { class: 'dr-row-acts' }, [
        verSel,
        el('button', { class: 'mini', 'data-add': 'left', text: 'Add left',
                       title: 'Put this circuit in the left group', onclick: addTo('left') }),
        el('button', { class: 'mini', 'data-add': 'right', text: 'Add right',
                       title: 'Put this circuit in the right group', onclick: addTo('right') }),
      ].filter(Boolean)),
    ]);
  }

  /* ==================================================================
     The pre-flight: stated before anything is computed.
     ================================================================== */
  const bodyOf = () => ({
    left: st.left.map((m) => ({ id: m.id, version_id: m.version_id })),
    right: st.right.map((m) => ({ id: m.id, version_id: m.version_id })),
    cue_equivalence: st.eq.slice(),
  });
  let checkT = null, checkSeq = 0;
  function askCheck() {
    clearTimeout(checkT);
    if (!st.left.length || !st.right.length) { renderPre(); return; }
    renderPre();
    checkT = setTimeout(async () => {
      const seq = ++checkSeq;
      const key = JSON.stringify(bodyOf());
      try {
        const got = await apiPost('/api/arc/drift/check', bodyOf());
        if (seq !== checkSeq) return;
        st.check = got; st.checkErr = null; st.checkKey = key;
      } catch (e) {
        if (seq !== checkSeq) return;
        st.check = null; st.checkErr = e.message;
        if (!/older code/.test(e.message || '')) {
          reportClientError('drift.check', e.message, e.stack);
        }
      }
      renderPre();
    }, 160);
  }

  function renderPre() {
    const box = document.getElementById('drPre');
    if (!box) return;
    box.innerHTML = '';
    box.appendChild(el('div', { class: 'section-label', text: 'Before it runs' }));
    if (!st.left.length || !st.right.length) {
      box.appendChild(el('div', { class: 'empty-state dr-pre-empty' }, [
        el('p', { text: 'Put at least one circuit in each group to compare them. '
                        + 'Three or more per side is what lets the spread between '
                        + 'recordings be estimated.' }),
      ]));
      return;
    }
    if (st.checkErr) {
      box.appendChild(el('div', { class: 'empty-state dr-missing' }, [
        el('p', { text: /older code/.test(st.checkErr)
          ? st.checkErr + ' Restart Jarvis to pick up Drift.'
          : 'The check could not be made: ' + st.checkErr }),
      ]));
      return;
    }
    const c = st.check;
    if (!c) {
      box.appendChild(loader('Checking the two groups', 'kind, cue pairing, '
                             + 'windows, methods and parameters'));
      return;
    }
    if (c.compatible) {
      box.appendChild(el('p', { class: 'dr-verdict ok', text: 'These two groups can be '
        + 'compared: same kind, cue pairing, windows, methods and analysis parameters.' }));
    } else {
      box.appendChild(el('p', { class: 'dr-verdict bad', text: 'These two groups cannot '
        + 'be compared yet:' }));
      box.appendChild(el('ul', { class: 'dr-reasons' },
        (c.reasons || []).map((t) => el('li', { text: t }))));
    }
    if (c.cue_only || st.eq.length) box.appendChild(equivCard(c));
    for (const w of c.warn || []) {
      box.appendChild(el('p', { class: 'hint dr-warn', text: w }));
    }
    box.appendChild(whereTabs(c.cost || {}));
    box.appendChild(el('div', { class: 'cir-cost dr-cost' }, [
      el('strong', { text: (c.cost || {}).sentence || '' }),
    ]));
    box.appendChild(runBar(c));
  }

  /* The explicit choice. Offered only when the cue pairing is the ONLY
     thing standing between these groups; recorded on the result, with who
     and when, and shown there. Never made for anybody. */
  function equivCard(c) {
    const types = [];
    for (const r of c.cue_types || []) {
      if (!types.some((t) => t.cue_type === r.cue_type)) types.push(r);
    }
    const words = types.map((t) => t.cue_label).join(' and ');
    const on = st.eq.length > 0;
    const box = el('div', { class: 'dr-equiv' + (on ? ' on' : '') });
    box.appendChild(el('p', { class: 'dr-equiv-say', text: on
      ? 'You chose to treat ' + words + ' as the same cue type for this '
        + 'comparison. It is written into the result, with who and when, '
        + 'and shown on it.'
      : 'The only difference is the cue pairing: ' + words + '. The rats are '
        + 'counterbalanced, so whether those count as the same cue type is a '
        + 'scientific decision, and Jarvis does not make it for you.' }));
    const cb = el('input', { type: 'checkbox', class: 'dr-equiv-cb',
      onchange: (e) => {
        if (e.target.checked) {
          const at = new Date().toISOString().replace(/\.\d+Z$/, '+00:00');
          st.eq = (c.suggest || []).map((x) => ({ from: x.from, to: x.to, at: at }));
        } else {
          st.eq = [];
        }
        st.check = null;
        askCheck();
      } });
    cb.checked = on;
    box.appendChild(el('label', { class: 'toggle dr-equiv-t' }, [
      cb, el('span', { text: 'Treat ' + words + ' as the same cue type for this comparison' }),
    ]));
    return box;
  }

  function vaccOn() {
    return !!(BARRY.state && BARRY.state.vacc && BARRY.vacc
              && (BARRY.vacc.last || {}).configured);
  }

  /* Incisor's two tabs, as Circuit draws them. */
  function whereTabs(cost) {
    const on = vaccOn();
    const can = on && cost.vacc_can !== false;
    if (!can && st.where === 'vacc') st.where = 'local';
    const why = !on ? 'VACC Mode is off. Turn it on in the bar at the bottom left '
                      + 'to run this on the cluster.'
                    : (cost.vacc_why || 'The cluster cannot run this.');
    const mk = (id, label, sub, enabled, whyOff) => el('button', {
      class: 'inc-tab cir-where dr-where' + (st.where === id ? ' on' : '')
             + (enabled ? '' : ' locked'),
      'data-where': id, disabled: enabled ? null : 'disabled',
      title: enabled ? sub : whyOff,
      onclick: () => { st.where = id; renderPre(); },
    }, [el('strong', { text: label }),
        el('span', { text: enabled ? sub : (on ? 'the cluster cannot run this'
                                               : 'VACC Mode is off') })]);
    const bar = el('div', { class: 'inc-tabs cir-wheres' }, [
      mk('local', 'This computer', 'seconds, here', true, ''),
      mk('vacc', 'VACC', 'the same arithmetic, on the cluster', can, why),
    ]);
    return can ? bar : el('div', {}, [bar, el('p', { class: 'hint vacc-why cir-vacc-why',
                                                     text: why })]);
  }

  function runBar(c) {
    const busy = st.busy || !!(st.job && st.job.status === 'running');
    const nick = el('input', { type: 'text', class: 'dr-nick', maxlength: '160',
      value: st.nickname, placeholder: 'Type a name of your own for it…',
      'aria-label': 'Nickname for the drift',
      oninput: (e) => { st.nickname = e.target.value; } });
    return el('div', { class: 'head-actions dr-runbar' }, [
      nick,
      el('span', { class: 'hint', text: 'Filed as a Drift artifact that pins the '
        + 'exact circuit versions above. The same members again confirm it '
        + 'rather than adding a version.' }),
      el('div', { class: 'spacer' }),
      el('button', {
        class: 'btn dr-go', disabled: (busy || !c.compatible) ? 'disabled' : null,
        title: c.compatible ? null : 'Not until the two groups can be compared',
        text: busy ? 'Comparing…' : 'Compare', onclick: run,
      }),
    ]);
  }

  /* ==================================================================
     Running
     ================================================================== */
  async function run() {
    if (st.busy || !(st.check && st.check.compatible)) return;
    if (st.job && st.job.status === 'running') return;
    st.busy = true;
    renderPre();
    const body = Object.assign(bodyOf(), {
      labels: { left: (st.labels.left || '').trim() || 'Left',
                right: (st.labels.right || '').trim() || 'Right' },
      where: st.where,
    });
    if ((st.nickname || '').trim()) body.nickname = st.nickname.trim();
    try {
      const got = await apiPost('/api/arc/drift/run', body);
      st.job = { id: got.job, status: 'running', stages: [], where: body.where };
      log('arc.drift.run', { where: body.where, left: body.left.length,
                             right: body.right.length });
      if (body.where === 'vacc' && BARRY.vaccBusy) BARRY.vaccBusy.start();
      if (st.jobStop) st.jobStop();
      st.jobStop = follow(got.job, (job) => { st.job = Object.assign(job, { where: body.where }); paintRun(); },
                          (job) => landed(job, body.where));
    } catch (e) {
      if (!/older code/.test(e.message || '')) reportClientError('drift.run', e.message, e.stack);
      toast('The drift was not made: ' + e.message, 'err', 9000);
    } finally {
      st.busy = false;
      if (inToolkit()) { renderPre(); paintRun(); }
    }
  }

  function follow(id, tick, end) {
    let busy = false, dead = false, misses = 0;
    const t = setInterval(async () => {
      if (busy || dead) return;
      busy = true;
      try {
        const got = await api('/api/cfc/job/' + encodeURIComponent(id));
        misses = 0;
        const job = got.job || got;
        tick(job);
        if (['done', 'failed', 'canceled'].indexOf(job.status) >= 0) {
          dead = true; clearInterval(t);
          await end(job);
        }
      } catch (e) {
        misses += 1;
        if (misses >= 20) {
          dead = true; clearInterval(t);
          await end({ id: id, status: 'failed', error: 'Lost touch with the job: ' + e.message });
        }
      } finally {
        busy = false;
      }
    }, 700);
    return () => { dead = true; clearInterval(t); };
  }

  async function landed(job, where) {
    if (where === 'vacc' && BARRY.vaccBusy) BARRY.vaccBusy.stop();
    if (job.status === 'done') {
      try {
        const r = await api('/api/cfc/result/' + encodeURIComponent(job.id));
        const res = r.result || {};
        if (!res.payload) throw new Error('The job finished but returned no drift.');
        st.shown = { payload: res.payload, meta: {
          artifact_id: res.artifact_id, version: res.version, version_id: res.version_id,
          digest: res.digest, name: res.name, nickname: res.nickname,
          new_version: res.new_version } };
        st.shownErr = null;
        toast((res.new_version === false
               ? 'Same numbers as v' + res.version + ' — confirmed, no new version: '
               : 'Drift made, v' + res.version + ': ') + (res.nickname || res.name) + '.',
              'ok', 9000);
        log('arc.drift.landed', { artifact: res.artifact_id, version: res.version,
                                  new_version: res.new_version });
        if (BARRY.artifacts && BARRY.artifacts.reload) {
          try { BARRY.artifacts.reload(); } catch (e) { /* not shown */ }
        }
      } catch (e) {
        toast('The drift could not be read back: ' + e.message, 'err', 12000);
        reportClientError('drift.result', e.message, e.stack);
      }
    } else if (job.status === 'canceled') {
      toast('The drift was stopped. Nothing was filed.', 'warn', 7000);
    } else {
      toast('The drift failed: ' + (job.error || 'no reason was given.'), 'err', 12000);
    }
    st.job = null; st.jobStop = null;
    loadRows();
    if (inToolkit()) { renderPre(); paintRun(); renderShown(); }
  }

  async function cancel() {
    if (!st.job) return;
    try { await apiPost('/api/cfc/job/' + encodeURIComponent(st.job.id) + '/cancel', {}); }
    catch (e) { toast('Could not stop it: ' + e.message, 'err', 6000); }
  }

  const STAGE_WORDS = {
    'drift cells': 'Pool both groups and test every cell',
    'vacc stage': 'Send the code over', 'vacc queue': 'Waiting for the cluster',
    'vacc fetch': 'Bring the answer back',
  };
  const RANK = { 'vacc stage': -2, 'vacc queue': -1, 'vacc fetch': 10 };

  function paintRun() {
    const host = document.getElementById('drRun');
    if (!host) return;
    host.innerHTML = '';
    const job = st.job;
    if (!job) return;
    const stages = (job.stages || []).slice()
      .sort((a, b) => (RANK[a.name] || 0) - (RANK[b.name] || 0));
    const total = stages.reduce((s, x) => s + (x.of || 0), 0);
    const done = stages.reduce((s, x) => s + Math.min(x.done || 0, x.of || 0), 0);
    const pct = total ? Math.round(100 * done / total) : 0;
    host.appendChild(el('div', { class: 'card comod-run dr-run' }, [
      el('div', { class: 'comod-run-head' }, [
        el('strong', { text: job.where === 'vacc' ? 'Comparing, on the VACC'
                                                  : 'Comparing, on this computer' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost sm', text: 'Stop', onclick: cancel,
                       title: 'Stops it. Nothing is filed.' }),
      ]),
      el('div', { class: 'comod-stages' }, stages.map((s) => el('div', {
        class: 'comod-stage ' + (s.status || 'waiting') }, [
        el('span', { text: STAGE_WORDS[s.name] || s.name }),
        el('span', { class: 'hint', text: s.status === 'done'
          ? (s.seconds != null ? s.seconds.toFixed(1) + ' s' : 'done')
          : (s.of ? (s.done || 0) + ' of ' + s.of + ' ' + (s.unit || '') : s.status || '') }),
      ]))),
      el('div', { class: 'comod-total' }, [
        el('div', { class: 'comod-bar' }, [
          el('div', { class: 'comod-bar-fill', style: 'width:' + pct + '%' })]),
        el('span', { class: 'comod-eta', text: job.eta_s != null
          ? 'about ' + Math.max(1, Math.round(job.eta_s)) + ' s left' : '' }),
      ]),
      (job.log || []).length ? el('pre', { class: 'dop-log', text: job.log.join('\n') }) : null,
    ].filter(Boolean)));
  }

  function renderShown() {
    const host = document.getElementById('drShown');
    if (!host) return;
    host.innerHTML = '';
    if (!st.shown) return;
    const card = el('div', { class: 'card dr-shown' });
    const inner = el('div', { class: 'dr-host' });
    card.appendChild(inner);
    host.appendChild(card);
    renderDrift(inner, st.shown.payload, st.shown.meta);
  }

  /* ==================================================================
     The renderer -- one function for the panel and for Results.

     `meta`: { artifact_id, name, nickname, version, version_id, digest,
               new_version, inResults }
     ================================================================== */
  function keyOf(order, a, b) {
    return order.indexOf(a) < order.indexOf(b) ? a + '|' + b : b + '|' + a;
  }
  function membersAll(P) {
    return ((P.left || {}).members || []).length + ((P.right || {}).members || []).length;
  }
  /* A region grey in EVERY member has nothing anywhere; one grey in some is
     pooled over the others, and says so. */
  function fullGrey(P, region) {
    const d = (P.grey_detail || {})[region] || [];
    return d.length > 0 && d.length >= membersAll(P);
  }
  function greySay(P, region) {
    return ((P.grey_detail || {})[region] || [])
      .map((d) => d.side + ': ' + d.member + ' (' + d.why + ')').join('\n');
  }
  function panelOf(ctx) { return ((ctx.P.cells || {})[ctx.win] || {})[ctx.method] || {}; }
  function absentOf(ctx) { return ((ctx.P.absent || {})[ctx.win] || {})[ctx.method] || {}; }
  function maxAbsDelta(ctx) {
    let m = 0;
    for (const c of Object.values(panelOf(ctx))) {
      if (c && isFinite(c.delta)) m = Math.max(m, Math.abs(c.delta));
    }
    return m > 1e-12 ? m : 1;
  }
  function sideLine(P, side, c) {
    const s = c[side] || {};
    const lab = (P[side] || {}).label || side;
    return lab + ' (' + side + '): ' + (s.mean == null ? 'no value'
      : 'mean ' + fmt(s.mean, 4) + (s.se != null ? ' ± SE ' + fmt(s.se, 4) : ', no SE'))
      + ' (' + plural(s.k || 0, 'recording') + ', ' + plural(s.n || 0, 'pair') + ')'
      + (s.tau2 != null ? ', τ² ' + fmt(s.tau2, 5) : '')
      + (s.k === 1 ? ' — ' + K1_SAY : '')
      + (s.why ? ' — ' + s.why : '');
  }
  function cellTitle(ctx, a, b, c) {
    const P = ctx.P;
    const lines = [a + ' × ' + b, (METHOD_NAME[ctx.method] || ctx.method) + ' in ' + say(ctx.win),
                   sideLine(P, 'left', c), sideLine(P, 'right', c),
                   'Δ (right − left) ' + fmt(c.delta, 4)
                   + (c.se != null ? ', SE ' + fmt(c.se, 4) : '')
                   + (c.z != null ? ', z ' + fmt(c.z, 2) : '')
                   + ', p ' + fmtP(c.p) + ', q ' + fmtP(c.q)
                   + (c.testable ? '' : ' — not tested')];
    if ((c.warn || []).length) lines.push('', 'Warnings:', ...c.warn.map((w) => '• ' + w));
    lines.push('', 'Click for the recordings behind it.');
    return lines.join('\n');
  }

  function renderDrift(host, payload, meta) {
    meta = meta || {};
    const P = payload || {};
    host.innerHTML = '';
    host.classList.add('cir-view', 'dr-view');
    if (P.schema !== 'arc.drift/1' || !P.region_order || !P.cells) {
      host.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'This is not a drift payload (' + (P.schema || 'no schema')
                        + '), so there is nothing to draw. Download it as JSON from '
                        + 'Results to see what it holds.' }),
      ]));
      return null;
    }
    const kind = P.kind || 'state';
    let win = view.win[kind];
    if ((P.windows || []).indexOf(win) < 0) win = P.windows[0];
    let method = view.method;
    if ((P.methods || []).indexOf(method) < 0) method = P.methods[0];
    const ctx = { host: host, P: P, meta: meta, win: win, method: method,
                  side: view.side, sel: view.sel };
    host.__dr = ctx;
    host.appendChild(headBlock(ctx));
    host.appendChild(el('div', { class: 'arc-cp-controls cir-controls dr-controls' }, [
      el('div', { class: 'seg dr-wins' }, P.windows.map((w) => el('button', {
        class: w === ctx.win ? 'active' : '', 'data-win': w, text: say(w),
        onclick: () => { view.win[kind] = w; renderDrift(host, P, meta); } }))),
      el('div', { class: 'seg dr-methods' }, P.methods.map((m) => el('button', {
        class: m === ctx.method ? 'active' : '', 'data-method': m, text: METHOD_NAME[m] || m,
        onclick: () => { view.method = m; renderDrift(host, P, meta); } }))),
      el('div', { class: 'seg dr-sides' }, [['left', (P.left || {}).label || 'Left'],
                                            ['delta', 'Delta'],
                                            ['right', (P.right || {}).label || 'Right']]
        .map(([s, t]) => el('button', {
          class: s === ctx.side ? 'active' : '', 'data-side': s, text: t,
          title: s === 'delta' ? 'Right minus left, with its test'
                               : 'The ' + s + ' group’s pooled circuit',
          onclick: () => { view.side = s; renderDrift(host, P, meta); } }))),
    ]));
    const body = el('div', { class: 'cir-body dr-body' });
    const left = el('div', { class: 'cir-left' });
    const right = el('div', { class: 'cir-right' });
    body.appendChild(left); body.appendChild(right);
    host.appendChild(body);
    left.appendChild(matrixGrid(ctx));
    left.appendChild(matrixKey(ctx));
    ctx.ringBox = el('div', { class: 'cir-ring-box dr-ring-box' });
    right.appendChild(ctx.ringBox);
    paintRing(ctx);
    ctx.detail = el('div', { class: 'cir-detail dr-detail' });
    host.appendChild(ctx.detail);
    paintDetail(ctx);
    return ctx;
  }

  function memberLinks(P, side) {
    const g = P[side] || {};
    return el('div', { class: 'dr-side-mem', 'data-side': side }, [
      el('span', { class: 'dr-side-h', text: (g.label || side) + ' · '
        + plural((g.members || []).length, 'recording')
        + ((g.members || []).length === 1 ? ' — ' + K1_SAY : '') }),
      el('ul', { class: 'dr-refs' }, (g.members || []).map((m) => el('li', {}, [
        el('a', { href: '#', class: 'art-link dr-link', 'data-ref': m.artifact_id,
                  'data-vid': m.version_id || '', 'data-v': String(m.version),
                  title: 'Open exactly this circuit version in Results'
                         + (m.digest ? ' (digest ' + m.digest + ')' : ''),
                  text: (m.name || m.artifact_id) + ' · v' + m.version,
                  onclick: (e) => {
                    e.preventDefault();
                    if (BARRY.artifacts && BARRY.artifacts.open) {
                      BARRY.artifacts.open(m.artifact_id, m.version_id || m.version);
                    }
                  } }),
        el('span', { class: 'hint', text: m.n_pairs != null ? ' ' + plural(m.n_pairs, 'cue pair') : '' }),
      ]))),
    ]);
  }

  function headBlock(ctx) {
    const P = ctx.P, m = ctx.meta;
    const on = P.computed_on || {};
    const where = on.kind === 'vacc'
      ? 'computed on VACC' + (on.slurm_id ? ' (job ' + on.slurm_id + ')' : '')
      : on.kind === 'local' ? 'computed on this computer' + (on.machine ? ' (' + on.machine + ')' : '')
      : 'where it was computed is not recorded';
    const facts = [m.version != null ? 'v' + m.version : null,
                   m.digest ? 'digest ' + m.digest : null,
                   P.cue_label || P.cue_type, KIND_SAY[P.kind] || P.kind, where]
      .filter(Boolean);
    const kids = [el('div', { class: 'cir-titles' }, [
      el('strong', { class: 'cir-nick-t', text: m.nickname || m.name
        || ((P.left || {}).label + ' vs ' + (P.right || {}).label) }),
      m.nickname && m.name ? el('span', { class: 'cir-name-t', text: m.name }) : null,
      el('span', { class: 'cir-facts', text: facts.join(' · ') }),
      m.new_version === false ? el('span', { class: 'flagchip mat',
                                             text: 'confirmed — same numbers' }) : null,
    ].filter(Boolean))];
    kids.push(el('div', { class: 'dr-sides-mem' }, [memberLinks(P, 'left'), memberLinks(P, 'right')]));
    const notes = [];
    if ((P.cue_equivalence || []).length) {
      notes.push(el('p', { class: 'dr-note dr-eqnote', text: 'Cue pairings treated as '
        + 'the same cue type for this comparison: ' + (P.cue_equivalence || []).map((e) =>
          e.from + ' ≡ ' + e.to + ' (decided by ' + (e.by || 'nobody recorded')
          + (e.at ? ', ' + (BARRY.when ? BARRY.when(e.at, 'minute') : e.at) : '') + ')')
          .join('; ') + '. This was a choice, not a finding.' }));
    }
    for (const w of P.warn || []) notes.push(el('p', { class: 'dr-note warn', text: w }));
    for (const n of P.notes || []) notes.push(el('p', { class: 'dr-note', text: n }));
    notes.push(el('p', { class: 'hint dr-method', text: (P.method || '')
      + ((P.test || {}).label ? ' · test: ' + P.test.label : '') }));
    kids.push(el('div', { class: 'dr-notes' }, notes));
    return el('div', { class: 'cir-head dr-head' }, kids);
  }

  /* ---------------- the matrix ---------------- */
  function matrixGrid(ctx) {
    const P = ctx.P, order = P.region_order;
    const cells = panelOf(ctx), gone = absentOf(ctx);
    const delta = ctx.side === 'delta';
    const scale = maxAbsDelta(ctx);
    const diverging = delta || ctx.method !== 'coherence';
    const nodes = [el('div', { class: 'arc-mx-corner' })];
    const headOf = (name, kind, i) => {
      const full = fullGrey(P, name), part = !full && (P.grey || []).indexOf(name) >= 0;
      const n = el('div', {
        class: 'arc-mx-head ' + kind + (full ? ' grey' : '') + (part ? ' part' : ''),
        title: name + (full ? '\nGrey in every recording, so never computed:\n' + greySay(P, name)
          : part ? '\nGrey in some recordings, pooled over the others:\n' + greySay(P, name) : ''),
        text: shortRegion(name) });
      n.dataset[kind === 'row' ? 'r' : 'c'] = String(i);
      return n;
    };
    order.forEach((b, j) => nodes.push(headOf(b, 'col', j)));
    order.forEach((a, i) => {
      nodes.push(headOf(a, 'row', i));
      order.forEach((b, j) => {
        let node;
        if (a === b) {
          node = el('div', { class: 'arc-mx-cell self', 'data-state': 'self' });
        } else {
          const key = keyOf(order, a, b);
          const c = cells[key];
          const sv = c ? (delta ? c.delta : (c[ctx.side] || {}).mean) : null;
          if (!c || sv == null) {
            const why = gone[key] || (c ? 'the ' + ctx.side + ' group has no value here'
                                        : 'not in the payload');
            const grey = fullGrey(P, a) || fullGrey(P, b);
            node = el('div', {
              class: 'arc-mx-cell ' + (grey ? 'cir-grey' : 'cir-absent'),
              'data-state': grey ? 'grey' : 'absent', 'data-key': key,
              title: a + ' × ' + b + ' — no value. ' + why + '. Blank, not zero.' });
          } else {
            const q = c.q, sig = delta ? sigOf(q) : 0;
            node = el('div', {
              class: 'arc-mx-cell cir-val dr-val' + (c.testable ? '' : ' untested')
                     + ((c.warn || []).length ? ' warned' : '')
                     + (ctx.sel === key ? ' sel' : ''),
              'data-state': 'value', 'data-key': key,
              'data-sig': String(sig), 'data-q': q == null ? '' : String(q),
              'data-v': String(sv),
              style: 'background-color:' + cellColour(delta ? sv / scale : sv, diverging),
              title: cellTitle(ctx, a, b, c),
              onclick: () => select(ctx, key),
            }, [el('span', { class: 'cir-mx-v', text: short(sv) }),
                el('span', { class: 'cir-mx-n', text: delta
                  ? (c.testable ? '' : 'n/t')
                  : String((c[ctx.side] || {}).k || 0) })]);
          }
        }
        node.dataset.r = String(i);
        node.dataset.c = String(j);
        nodes.push(node);
      });
    });
    const grid = el('div', { class: 'arc-mx cir-mx dr-mx', 'data-side': ctx.side,
      style: 'grid-template-columns: 58px repeat(' + order.length + ', minmax(0, 1fr));' }, nodes);
    const s = shared();
    if (s && s.crosshair) s.crosshair(grid);
    return grid;
  }

  function tally(ctx) {
    const P = ctx.P, order = P.region_order, cells = panelOf(ctx);
    const out = { cells: 0, tested: 0, untested: 0, absent: 0, grey: 0, sig: [0, 0, 0, 0] };
    for (let i = 0; i < order.length; i++) {
      for (let j = i + 1; j < order.length; j++) {
        const a = order[i], b = order[j];
        const c = cells[keyOf(order, a, b)];
        if (!c) { if (fullGrey(P, a) || fullGrey(P, b)) out.grey += 1; else out.absent += 1; continue; }
        out.cells += 1;
        if (c.testable) { out.tested += 1; out.sig[sigOf(c.q)] += 1; } else out.untested += 1;
      }
    }
    return out;
  }

  function matrixKey(ctx) {
    const P = ctx.P, t = tally(ctx);
    const keys = [];
    if (ctx.side === 'delta') {
      const sc = maxAbsDelta(ctx);
      keys.push(el('span', { class: 'arc-mx-key dr-key-ramp', text: 'colour: Δ = '
        + ((P.right || {}).label || 'right') + ' − ' + ((P.left || {}).label || 'left')
        + ', ±' + fmt(sc, 3) + ' at full strength; the number in each cell is Δ' }));
      const s1 = t.sig[1] + t.sig[2] + t.sig[3], s2 = t.sig[2] + t.sig[3], s3 = t.sig[3];
      keys.push(el('span', { class: 'arc-mx-key dr-key-sig', text: 'outline: q < .05 thin ('
        + s1 + '), q < .01 thicker (' + s2 + '), q < .001 thickest (' + s3 + ') — of '
        + t.tested + ' tested; BH across this panel' }));
      if (t.untested) {
        keys.push(el('span', { class: 'arc-mx-key dr-key-nt', text: t.untested
          + ' shown but not tested (n/t): hover for why' }));
      }
    } else {
      keys.push(el('span', { class: 'arc-mx-key dr-key-ramp', text: 'the '
        + ((P[ctx.side] || {}).label || ctx.side) + ' group’s pooled mean; the small number '
        + 'is k, the recordings behind it' }));
    }
    if (t.absent) keys.push(el('span', { class: 'arc-mx-key cir-key-absent', text: t.absent
      + ' blank: no recording on a side had this cell (blank, not zero)' }));
    const greys = P.region_order.filter((n) => (P.grey || []).indexOf(n) >= 0);
    if (greys.length) {
      keys.push(el('span', { class: 'arc-mx-key blocked cir-key-grey',
        title: greys.map((n) => n + ':\n' + greySay(P, n)).join('\n\n'),
        text: 'grey: ' + greys.map((n) => n + (fullGrey(P, n) ? ' (every recording)'
                                                              : ' (some recordings)')).join(', ') }));
    }
    return el('div', { class: 'arc-mx-keys cir-keys dr-keys' }, keys);
  }

  /* ---------------- the ring: circuit.js's, fed this ---------------- */
  function ringP(P) {
    return {
      region_order: P.region_order,
      grey: P.region_order.filter((n) => fullGrey(P, n)),
      regions: P.region_order.map((n) => ({ region: n,
        status: fullGrey(P, n) ? 'grey' : 'ok',
        why: fullGrey(P, n) ? 'Grey in every recording: ' + greySay(P, n).replace(/\n/g, '; ') : '' })),
    };
  }

  function presentKeys(ctx) {
    const P = ctx.P;
    return Object.keys(panelOf(ctx)).filter((k) => {
      const [a, b] = k.split('|');
      return !fullGrey(P, a) && !fullGrey(P, b);
    });
  }

  function median(xs) {
    const v = xs.filter((x) => isFinite(x)).sort((a, b) => a - b);
    return v.length ? v[Math.floor((v.length - 1) / 2)] : 0;
  }

  /* Which cells the delta ring draws: the ones whose q passes the chosen
     level (the default, q < .05), or -- by choice, and said so -- every
     cell with |delta| at or above a slider value. Exported for the harness,
     which compares it with its own reading of the payload. */
  function deltaEdgeKeys(ctx, t) {
    const cells = panelOf(ctx);
    return presentKeys(ctx).filter((k) => {
      const c = cells[k];
      if (t.mode === 'q') return c.q != null && c.q < t.v;
      return isFinite(c.delta) && Math.abs(c.delta) >= t.v;
    });
  }

  function ringOpts(ctx) {
    const P = ctx.P, cells = panelOf(ctx);
    const delta = ctx.side === 'delta';
    const scale = maxAbsDelta(ctx);
    const fam = ctx.method + '|' + ctx.side;
    const thr = () => {
      if (delta && view.edge === 'q') return { mode: 'q', v: view.q, auto: false };
      if (delta) {
        if (view.abs[fam] != null) return { mode: 'abs', v: view.abs[fam], auto: false };
        return { mode: 'abs', auto: true, v: Math.floor(median(presentKeys(ctx)
          .map((k) => Math.abs(cells[k].delta))) * 1000) / 1000 };
      }
      if (view.sideThr[fam] != null) return { mode: 'side', v: view.sideThr[fam], auto: false };
      return { mode: 'side', auto: true, v: Math.floor(median(presentKeys(ctx)
        .map((k) => Math.abs((cells[k][ctx.side] || {}).mean))) * 100) / 100 };
    };
    const edgeOf = (k) => {
      const c = cells[k], [a, b] = k.split('|');
      const v = delta ? c.delta : (c[ctx.side] || {}).mean;
      return { key: k, a: a, b: b, v: v,
               c: { n: (c.left || {}).n + (c.right || {}).n, warn: (c.warn || []).length },
               mag: delta ? Math.min(1, Math.abs(v) / scale) : Math.min(1, Math.abs(v)),
               dash: c.testable ? null : '5 3',
               attrs: { 'data-q': c.q == null ? '' : String(c.q), 'data-sig': String(sigOf(c.q)) } };
    };
    return {
      win: ctx.win, method: ctx.method,
      diverging: delta || ctx.method !== 'coherence',
      thr: thr,
      edges: (rc, t) => {
        const keys = delta ? deltaEdgeKeys(ctx, t) : presentKeys(ctx).filter((k) => {
          const v = (cells[k][ctx.side] || {}).mean;
          return v != null && Math.abs(v) >= t.v;
        });
        return keys.map(edgeOf).sort((x, y) => Math.abs(x.v) - Math.abs(y.v));
      },
      total: () => presentKeys(ctx).length,
      title: (e) => cellTitle(ctx, e.a, e.b, cells[e.key]),
      read: (key) => {
        const c = cells[key], [a, b] = key.split('|');
        return a + ' × ' + b + ': Δ ' + fmt(c.delta, 4) + ', q ' + fmtP(c.q)
          + ' — ' + ((P.left || {}).label || 'left') + ' ' + fmt((c.left || {}).mean, 3)
          + ' (k ' + (c.left || {}).k + '), ' + ((P.right || {}).label || 'right') + ' '
          + fmt((c.right || {}).mean, 3) + ' (k ' + (c.right || {}).k + ')'
          + (c.testable ? '' : ' — not tested') + '.';
      },
      caption: (rc, t, edges, total) => (delta ? 'Δ ' : ((P[ctx.side] || {}).label || ctx.side) + ' · ')
        + (METHOD_NAME[ctx.method] || ctx.method) + ' · ' + say(ctx.win) + ' · '
        + (t.mode === 'q' ? 'q < ' + String(t.v).replace(/^0/, '')
                          : '|' + (delta ? 'Δ' : 'value') + '| ≥ ' + fmt(t.v, 3))
        + ' · ' + edges.length + ' of ' + total + ' edges',
      hint: delta ? 'Edges are coloured by the sign of Δ and thicker with |Δ|; '
        + 'dashed = shown but not tested. Hover for the numbers, click for the recordings.'
        : 'The pooled circuit of this group. Hover for the numbers, click for the recordings.',
      nodeNote: (region) => ((P.grey || []).indexOf(region) >= 0 && !fullGrey(P, region)
        ? '\nGrey in some recordings, pooled over the others:\n' + greySay(P, region) : ''),
      select: (key) => select(ctx, key),
      control: (rc, t, edges, total, repaint) => thrControl(ctx, t, edges, total, repaint, scale),
    };
  }

  function thrControl(ctx, t, edges, total, repaint, scale) {
    const delta = ctx.side === 'delta';
    const fam = ctx.method + '|' + ctx.side;
    const kids = [el('span', { class: 'section-label', text: 'Draw edges' })];
    if (delta) {
      kids.push(el('div', { class: 'seg dr-edge-mode' }, [
        ...SIG.slice().reverse().map(([lv, , word]) => el('button', {
          class: view.edge === 'q' && view.q === lv ? 'active' : '', 'data-q': String(lv),
          text: word, onclick: () => { view.edge = 'q'; view.q = lv; repaint(); } })),
        el('button', { class: view.edge === 'abs' ? 'active' : '', 'data-q': 'abs',
          text: '|Δ| ≥', title: 'Every cell whose delta is at least this big, '
                                          + 'tested or not',
          onclick: () => { view.edge = 'abs'; repaint(); } }),
      ]));
    }
    if (!delta || view.edge === 'abs') {
      const max = delta ? scale : 1;
      kids.push(el('input', { type: 'range', class: 'cir-thr dr-thr', min: '0',
        max: String(max), step: String(max / 100), value: String(t.v),
        'aria-label': 'Edge threshold',
        oninput: (e) => {
          const v = Number(e.target.value);
          if (delta) view.abs[fam] = v; else view.sideThr[fam] = v;
          repaint();
        } }));
      kids.push(el('span', { class: 'cir-thr-v', text: '|' + fmt(t.v, 3) + '|' }));
    }
    kids.push(el('span', { class: 'hint cir-thr-say dr-thr-say', text: edges.length + ' of '
      + total + ' drawn · ' + (t.mode === 'q'
        ? 'the cells whose q is below ' + String(t.v).replace(/^0/, '')
        : (t.auto ? 'the median, until you move it' : 'by size, not by test')) }));
    return el('div', { class: 'cir-thr-row dr-thr-row' }, kids);
  }

  function paintRing(ctx) {
    if (!ctx.ringBox) return;
    if (!(BARRY.circuit && BARRY.circuit.ringInto)) {
      ctx.ringBox.appendChild(el('p', { class: 'hint', text: 'The ring is drawn by '
        + 'Circuit, which has not loaded.' }));
      return;
    }
    ctx.ring = BARRY.circuit.ringInto(ctx.ringBox, ringP(ctx.P), ringOpts(ctx), {
      nickname: ctx.meta.nickname, name: (ctx.meta.name || 'drift') + ' ' + ctx.side });
  }

  /* ---------------- what a cell is made of ---------------- */
  function select(ctx, key) {
    ctx.sel = view.sel = (ctx.sel === key ? null : key);
    ctx.host.querySelectorAll('.dr-val.sel').forEach((n) => n.classList.remove('sel'));
    if (ctx.sel) {
      ctx.host.querySelectorAll('.dr-val').forEach((n) => {
        if (n.dataset.key === key) n.classList.add('sel');
      });
    }
    const svg = ctx.ringBox && ctx.ringBox.querySelector('svg');
    if (svg) svg.querySelectorAll('.cir-edge').forEach((n) => n.classList.toggle('sel', n.dataset.key === ctx.sel));
    paintDetail(ctx);
  }

  function paintDetail(ctx) {
    const box = ctx.detail;
    if (!box) return;
    box.innerHTML = '';
    const key = ctx.sel;
    const c = key ? panelOf(ctx)[key] : null;
    if (!c) {
      box.appendChild(el('p', { class: 'hint', text: key
        ? 'That region pair has no value in ' + say(ctx.win) + ': '
          + (absentOf(ctx)[key] || 'not in the payload') + '.'
        : 'Click a cell or an edge for the recordings behind both sides.' }));
      return;
    }
    const P = ctx.P;
    const [a, b] = key.split('|');
    const table = (side) => {
      const s = c[side] || {};
      return el('div', { class: 'dr-dside', 'data-side': side }, [
        el('strong', { text: ((P[side] || {}).label || side) + ': mean ' + fmt(s.mean, 4)
          + (s.se != null ? ' ± ' + fmt(s.se, 4) : '') + ' · k ' + (s.k || 0)
          + ' · n ' + (s.n || 0) + (s.tau2 != null ? ' · τ² ' + fmt(s.tau2, 5) : '') }),
        s.k === 1 ? el('p', { class: 'hint dr-k1', text: K1_SAY + '.' }) : null,
        el('table', { class: 'art-params dr-members' }, [el('tbody', {}, [
          el('tr', {}, ['recording', 'n', 'mean', 'SD', 'weight'].map((h) => el('th', { text: h }))),
        ].concat((s.members || []).map((mm) => el('tr', {}, [
          el('td', { text: mm.member }), el('td', { text: String(mm.n) }),
          el('td', { text: fmt(mm.mean, 4) }),
          el('td', { text: mm.sd == null ? 'none' : fmt(mm.sd, 4) + (mm.sd_borrowed ? ' (borrowed)' : '') }),
          el('td', { text: mm.weight == null ? '—' : (100 * mm.weight).toFixed(0) + '%' }),
        ]))).concat((s.missing || []).map((nm) => el('tr', { class: 'none' }, [
          el('td', { text: nm }), el('td', { text: 'no value for this cell', colspan: '4' }),
        ]))))]),
      ].filter(Boolean));
    };
    box.appendChild(el('div', { class: 'cir-detail-in dr-detail-in' }, [
      el('div', { class: 'cir-detail-head' }, [
        el('strong', { text: a + ' × ' + b }),
        el('span', { class: 'hint', text: (METHOD_NAME[ctx.method] || ctx.method) + ' in ' + say(ctx.win) }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', title: 'Close', onclick: () => select(ctx, key),
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('p', { class: 'cir-detail-say dr-detail-say', text: 'Δ ' + fmt(c.delta, 4)
        + (c.se != null ? ' · SE ' + fmt(c.se, 4) : '') + (c.z != null ? ' · z ' + fmt(c.z, 2) : '')
        + ' · p ' + fmtP(c.p) + ' · q ' + fmtP(c.q) + (c.testable ? '' : ' · not tested') }),
      el('div', { class: 'dr-dsides' }, [table('left'), table('right')]),
      (c.warn || []).length ? el('ul', { class: 'dr-cwarn' }, c.warn.map((w) => el('li', { text: w }))) : null,
    ].filter(Boolean)));
  }

  /* ==================================================================
     Results: the viewer, and "Use in Drift" on every circuit.
     ================================================================== */
  const VIEWER = {
    title: 'Drifts',
    icon: 'drift',
    summary: (rec) => {
      const n = (rec.current || {}).n_summary || {};
      const s = rec.subject || {};
      const bits = [];
      if (n.left_k != null) bits.push(n.left_k + ' v ' + n.right_k + ' recordings');
      if (n.tests != null) bits.push(n.tests + ' tests, ' + (n.q_lt_05 || 0) + ' at q < .05');
      if (n.equivalence) bits.push('cue equivalence recorded');
      if (s.window_kind) bits.push(s.window_kind);
      return bits.join(' · ');
    },
    render: (host, rec, payload, version) => {
      renderDrift(host, payload, {
        artifact_id: rec && rec.id, name: rec && rec.name, nickname: rec && rec.nickname,
        version: version ? version.v : null, version_id: version ? version.id : null,
        digest: version ? version.digest : null, inResults: true });
    },
  };

  /* "Use in Drift": which side, then the Drift step with it there. */
  function useInDrift(rec, ver) {
    if (!rec || rec.kind !== 'circuit') return;
    ver = ver || rec.current || {};
    const s = rec.subject || {};
    const member = {
      id: rec.id, version_id: ver.id, version: ver.v, digest: ver.digest,
      name: rec.name, nickname: rec.nickname,
      n_pairs: (ver.n_summary || {}).n_pairs, cue_type: s.cue_type,
      cue_label: s.cue_label || s.cue_type, kind: s.window_kind, gid: s.gid,
      current: !!(rec.current && rec.current.id === ver.id),
    };
    let side = 'left';
    const go = el('button', { class: 'btn', 'data-go': '1', text: 'Put it in the left group' });
    const seg = el('div', { class: 'seg dr-use-seg' }, ['left', 'right'].map((x) => el('button', {
      class: x === side ? 'active' : '', 'data-side': x, text: x === 'left' ? 'Left' : 'Right',
      onclick: (e) => {
        side = x;
        seg.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b.dataset.side === x));
        go.textContent = 'Put it in the ' + x + ' group';
      } })));
    go.addEventListener('click', () => {
      add(side, member);
      closeModal();
      toast(nameOf(member) + ' v' + member.version + ' is in the ' + side + ' group of Drift.', 'ok');
      log('arc.drift.use', { artifact: member.id, version: member.version, side: side });
      if (typeof setView === 'function') setView('toolkit');
      const tk = BARRY.views && BARRY.views.toolkit;
      if (tk && typeof tk.pick === 'function') tk.pick('drift');
    });
    showModal(el('div', { class: 'dr-use' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Use in Drift' }), el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: () => closeModal(),
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { text: '“' + nameOf(member) + '” v' + member.version
          + ' goes into one of the two groups Drift compares. This exact version is '
          + 'the one it will read.' }),
        el('div', { class: 'section-label', text: 'Which group' }),
        seg,
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: () => closeModal() }),
        go,
      ]),
    ]));
  }

  function registerResults() {
    if (!BARRY.artifacts || typeof BARRY.artifacts.register !== 'function') return false;
    try {
      BARRY.artifacts.register('drift', VIEWER);
      BARRY.artifacts.action('circuit', { id: 'use-in-drift', label: 'Use in Drift',
        title: 'Put this exact version into the left or right group of Drift',
        run: useInDrift });
    } catch (e) {
      reportClientError('drift.register', e.message, e.stack);
    }
    return true;
  }
  if (!registerResults()) {
    let tries = 0;
    const t = setInterval(() => { tries += 1; if (registerResults() || tries > 300) clearInterval(t); }, 200);
  }

  return {
    paint,
    render: renderDrift,
    add: (side, member) => add(side, member),
    addRow: (side, id, versionId) => {
      const r = rowOf(id);
      if (!r) return false;
      return add(side, memberOf(r, versionId || r.version_id));
    },
    remove, move,
    run,
    reload: () => loadRows(),
    useInDrift,
    /* The edge set the delta ring draws, for the harness. */
    _edgeKeys: (host) => {
      const ctx = host && host.__dr;
      if (!ctx) return null;
      const t = ringOpts(ctx).thr();
      return ctx.side === 'delta' ? deltaEdgeKeys(ctx, t) : null;
    },
    _view: view,
    _show: (payload, meta) => { st.shown = { payload: payload, meta: meta || {} }; renderShown(); return true; },
    _clear: () => { st.left = []; st.right = []; st.eq = []; st.check = null; st.shown = null;
                    st.nickname = ''; st.labels = { left: 'Left', right: 'Right' };
                    if (document.getElementById('drGroups')) render(); },
    setLabels: (l, r) => { st.labels = { left: l, right: r }; renderGroups(); },
    setWhere: (w) => { st.where = w; renderPre(); },
    get state() {
      return { left: st.left.slice(), right: st.right.slice(), labels: Object.assign({}, st.labels),
               eq: st.eq.slice(), check: st.check, checkErr: st.checkErr, where: st.where,
               job: st.job, shown: st.shown, rows: st.rows, rowsErr: st.rowsErr };
    },
  };
})();
window.barryDrift = BARRY.drift;
