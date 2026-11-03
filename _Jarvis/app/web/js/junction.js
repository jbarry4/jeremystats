/* ==========================================================================
   junction.js -- Junction, step 1 of The Confluence: pool them.

   Incisor finds dentate spikes and Doppler finds interictal discharges, and
   on one recording some of what each finds is the other's. Junction takes
   one banked entry of each -- the newest version by default, any other
   through the version tree (constitution §6e) -- and pools them into one
   entry of type `pooled`: one list for Panning to sort, Lock to line up and
   Root Canal to tease apart.

   THE RULE is backend/confluence.py's, and the panel only states it: time
   only, any channel; within a window (5 ms unless you say otherwise); one
   to one, nearest first; a merged event keeps Incisor's time and holds
   Doppler's as `pair_t` -- or Doppler's, holding Incisor's, when that is
   chosen (2026-10-19). What somebody already called Garbage stays out.

   ALIGNED OR NOT, SAID OUTRIGHT (2026-10-19). Every input -- in the list,
   on each side, on each version, in Many -- carries an "aligned" or "not
   aligned" label: whether Braces (Incisor's) or Eye (Doppler's) has put
   its stamps on their peaks. Two detectors a few milliseconds apart about
   one event is what this step merges on, so whether those milliseconds are
   the detectors' or the peaks' is worth seeing before pooling.

   THE MERGE IS SHOWN, NOT ANNOUNCED. Asked for in so many words: "a cool
   animation, would be nice if we see the files flowing together". The two
   entries are drawn as files; their events leave them in time order and
   run to the junction, where the ones both detectors found fuse into one
   two-tone event and the rest run on in their own colour; the pool fills
   on the right and its counts run up as they arrive. The colours are the
   ones the ToolKit's stream, Panning and Root Canal use for Incisor's and
   Doppler's events. Under prefers-reduced-motion nothing moves: the stage
   is drawn as it ends.
   ========================================================================== */
'use strict';

BARRY.junction = (function () {
  const q = {
    mode: 'one',          // 'one' | 'many'
    gid: null,
    find: '',
    ds: null, dsV: null,  // the dentate-spike entry, and its version (null: newest)
    ied: null, iedV: null,
    win: 20,              // ms (the default since 2026-10-20; was 5)
    keep: 'incisor',      // whose time a merged event keeps
    sel: null,            // Many: the gids ticked (a Set), null until listed
    manyFind: '',         // Many: what is typed in its search
    manyV: {},            // Many: gid -> { ds, ied } version names chosen
    manyE: {},            // Many: gid -> { ds, ied } entry ids chosen
  };

  let recs = null;        // /api/confluence/recordings
  let recsErr = null;
  let defaultWin = 20;
  let plan = null;        // the preview for the inputs on screen
  let planErr = null;
  let planSig = null;
  let planning = false;
  let merging = false;
  let landed = null;      // { entry, stats, cached } after a merge
  let batch = null;       // { rows, at } after a bulk merge
  let stageStop = null;   // stops the stage's drawing loop

  const fx = () => BARRY.jarvisfx || window.JarvisFX || null;
  const sfx = (name, a) => {
    try { const f = fx(); if (f && !f.muted && f[name]) f[name](a); }
    catch (e) { /* a decoration never stops anything */ }
  };
  const reduced = () => !!(BARRY.ui.reducedMotion && BARRY.ui.reducedMotion());
  const tok = (n, d) => BARRY.token(n, d);
  const num = (n) => Number(n || 0).toLocaleString();
  const host = () => document.getElementById('tkResult');

  /* ==================================================================
     Reading
     ================================================================== */
  let recsAt = 0;
  async function load(force) {
    if (recs && !force) return;
    try {
      const got = await api('/api/confluence/recordings');
      recs = got.recordings || [];
      defaultWin = Number(got.window_ms) || 20;
      recsErr = null;
    } catch (e) {
      recs = [];
      recsErr = e.message;
    }
    recsAt = Date.now();
  }

  /* READ AGAIN ON EVERY VISIT (2026-10-30). The recordings were read once
     per page, so an Incisor or Doppler set banked after Junction was first
     opened -- here or on another computer -- was not offered until a
     restart. In the background; painted again only when the answer
     differs, and not while a merge or a batch is on screen. */
  let freshening = false;
  async function freshen() {
    if (freshening || !recs || Date.now() - recsAt < 4000) return;
    freshening = true;
    const was = JSON.stringify(recs);
    try { await load(true); } finally { freshening = false; }
    if (JSON.stringify(recs) === was || landed || batch) return;
    paint();
  }

  const recOf = (gid) => (recs || []).find((r) => r.gid === gid) || null;
  const nameOf = (r) => r.label || [r.project, r.mouse != null ? 'm' + r.mouse
    : null, r.session != null ? 's' + r.session : null].filter(Boolean)
    .join(' ') || r.gid;

  /* The inputs Many would use for a recording: the newest entry of each
     kind at its newest version. */
  /* The entries a recording pools from in Many at once: the ones chosen
     in its pop-up (2026-10-21: "the sets are locked in"), else the first
     the server offers on each side. */
  function defaultsFor(r) {
    const m = q.manyE[r.gid] || {};
    const pick = (list, id) => (id && (list || []).find((x) => x.id === id))
                               || (list || [])[0];
    return { ds: pick(r.ds, m.ds), ied: pick(r.ied, m.ied) };
  }

  /* Whether a pool from exactly these inputs is already banked. A pool from
     before the choice existed kept Incisor's time. */
  function pooledFrom(r, dsId, dsName, iedId, iedName, win) {
    return (r.pooled || []).find((p) => {
      const pr = p.params || {};
      return pr.ds_entry === dsId && String(pr.ds_version) === String(dsName)
        && pr.ied_entry === iedId && String(pr.ied_version) === String(iedName)
        && Number(pr.window_ms) === Number(win)
        && (pr.keep || 'incisor') === q.keep;
    }) || null;
  }

  /* ---------- aligned, or not ---------- */
  const ALIGNER = { ds: 'Braces', ied: 'Eye', pooled: 'Lock' };
  const ALIGN_STEP = { ds: 'The Dentist, step 3', ied: 'The Storm, step 3',
                       pooled: 'The Confluence, step 3' };
  const KEEP_WORD = { incisor: 'Incisor', doppler: 'Doppler' };

  /* Whether these stamps have been lined up: the entry as it stands when
     no version is chosen, else that version -- one an alignment wrote, or
     one on a line after one (the server's `aligned_names`). */
  function alignedAt(ent, vId) {
    if (!ent) return false;
    if (vId == null) return !!ent.aligned;
    const v = (vers[ent.id] || []).find((x) => x.id === vId);
    return !!(v && (ent.aligned_names || []).indexOf(v.name) >= 0);
  }

  /* The label itself. Both states are said -- "not aligned" is the fact
     somebody is deciding on, not the absence of one. */
  function alignChip(ent, vId, kind) {
    const on = alignedAt(ent, vId);
    const who = ALIGNER[kind] || 'An alignment';
    const when = ent && ent.aligned_at
      ? String(ent.aligned_at).slice(0, 10) : '';
    return BARRY.ui.chip(on ? '✓ aligned' : 'not aligned', {
      kind: on ? 'ok' : null, extra: 'jn-al' + (on ? ' on' : ''),
      title: on
        ? who + ' has put these stamps on their peaks'
          + (ent.aligned_v ? ' (v' + ent.aligned_v + ')' : '')
          + (ent.aligned_by ? ', ' + ent.aligned_by : '')
          + (when ? ', ' + when : '') + '.'
        : who + ' (' + (ALIGN_STEP[kind] || 'its step 3') + ') has not lined '
          + 'these stamps up. They can still be pooled; the gap between '
          + 'the two detectors then includes where each put its stamp.',
    });
  }

  /* The same, as a word inside a detector's tag in the list. */
  function alignWord(ent) {
    const on = !!(ent && ent.aligned);
    return el('span', { class: 'jn-al-w' + (on ? ' on' : ''),
                        text: on ? '✓ aligned' : 'not aligned' });
  }

  /* ==================================================================
     The panel
     ================================================================== */
  async function paint() {
    const h = host();
    if (!h || !BARRY.views.toolkit || BARRY.views.toolkit.tool() !== 'junction') return;
    if (stageStop) { stageStop(); stageStop = null; }
    h.style.opacity = '1';
    h.innerHTML = '';
    h.dataset.tool = 'junction';     // so ToolKit's refresh leaves it be
    h.appendChild(BARRY.ui.stepHeader({
      title: 'Junction',
      step: BARRY.ui.stepOf('junction'),
      blurb: 'Pool what Incisor and Doppler found on one recording. Events '
           + 'within a few milliseconds of each other are one event; the rest '
           + 'keep the detector that found them.',
    }));
    if (recs === null) {
      const box = el('div', { class: 'card' });
      BARRY.skeleton.into(box, 'row', 3);
      h.appendChild(box);
      await load();
      if (!q.sel) q.sel = new Set((recs || []).filter(
        (r) => !pooledDefault(r)).map((r) => r.gid));
      // Still the starting window (nobody has typed one): the server's.
      if (q.win === 20 && defaultWin !== 20) q.win = defaultWin;
      paint();
      return;
    }
    freshen();
    h.appendChild(modeCard());
    if (recsErr) {
      h.appendChild(el('div', { class: 'card' }, [el('div', {
        class: 'empty-state', text: 'Could not read the bank: ' + recsErr })]));
      return;
    }
    if (!recs.length) {
      h.appendChild(el('div', { class: 'card' }, [el('div', {
        class: 'empty-state',
        text: 'No recording has both yet. Junction pools a recording that '
            + 'has a banked Incisor entry (The Dentist, step 1) AND a banked '
            + 'Doppler entry (The Storm, step 1) — run whichever is missing '
            + 'and bank what it finds.' })]));
      return;
    }
    if (q.mode === 'many') { paintMany(h); return; }
    h.appendChild(pickCard());
    if (q.gid && recOf(q.gid)) {
      h.appendChild(inputsCard());
      h.appendChild(poolCard());
      requestPlan();
    }
  }

  function modeCard() {
    return el('div', { class: 'card jn-mode' }, [
      BARRY.ui.seg([
        ['one', 'One recording', 'Pool one recording, choosing the entries '
                                + 'and versions that go in'],
        ['many', 'Many at once', 'Pool many recordings in one go, each from '
                                + 'its newest entries'],
      ], q.mode, (m) => { q.mode = m; landed = null; batch = null; paint(); }),
      el('span', { class: 'hint quiet',
        text: recs ? recs.length + ' recording' + (recs.length === 1 ? ' has'
              : 's have') + ' both an Incisor and a Doppler entry.' : '' }),
    ]);
  }

  /* ---------- 1. which recording ---------- */
  function pickCard() {
    const box = el('div', { class: 'card' }, [
      el('div', { class: 'section-label', text: '1. Which recording' }),
      el('div', { class: 'jn-search' }, [BARRY.ui.searchField({
        placeholder: 'Type a mouse, session or project…',
        value: q.find,
        oninput: (e) => {
          q.find = (e && e.target) ? e.target.value : (e || '');
          const l = document.getElementById('jnList');
          if (l) l.replaceWith(recList());
        },
      })]),
      recList(),
    ]);
    return box;
  }

  function recList() {
    const want = (q.find || '').trim().toLowerCase();
    const rows = (recs || []).filter((r) => !want
      || [nameOf(r), r.project, 'm' + r.mouse, 's' + r.session]
        .join(' ').toLowerCase().indexOf(want) >= 0);
    const list = el('div', { id: 'jnList', class: 'jn-list' });
    if (!rows.length) {
      list.appendChild(el('div', { class: 'empty-state',
        text: 'Nothing here matches “' + q.find + '”.' }));
      return list;
    }
    /* Counts are of the live entries: an archived one is kept, and is not
       one more of anything to choose from (2026-10-20). */
    const liveOf = (xs) => (xs || []).filter((x) => !x.archived);
    for (const r of rows) {
      // The newest of each, which is what picking the row starts from.
      const pool = liveOf(r.pooled)[0];
      const nDs = liveOf(r.ds).length, nIed = liveOf(r.ied).length;
      const nPool = liveOf(r.pooled).length;
      list.appendChild(el('button', {
        class: 'jn-rec' + (q.gid === r.gid ? ' on' : ''),
        onclick: () => choose(r.gid),
      }, [
        el('strong', { text: nameOf(r) }),
        el('span', { class: 'jn-tag i',
          title: r.ds[0] && r.ds[0].aligned
            ? 'Braces has put the newest Incisor entry’s stamps on their peaks'
            : 'Braces has not lined up the newest Incisor entry' }, [
          el('span', { text: 'Incisor' + (nDs > 1 ? ' ×' + nDs : '') }),
          alignWord(r.ds[0]),
        ]),
        el('span', { class: 'jn-tag d',
          title: r.ied[0] && r.ied[0].aligned
            ? 'Eye has put the newest Doppler entry’s stamps on their peaks'
            : 'Eye has not lined up the newest Doppler entry' }, [
          el('span', { text: 'Doppler' + (nIed > 1 ? ' ×' + nIed : '') }),
          alignWord(r.ied[0]),
        ]),
        nPool
          ? BARRY.ui.chip(nPool === 1 ? 'pooled' : 'pooled ×' + nPool,
                          { flag: true, kind: 'ok' })
          : null,
        pool && pool.aligned
          ? BARRY.ui.chip('pool aligned', { flag: true, kind: 'ok',
              title: 'Lock has lined up the newest pool’s stamps' })
          : null,
      ].filter(Boolean)));
    }
    return list;
  }

  function choose(gid) {
    if (merging) return;
    const r = recOf(gid);
    q.gid = gid;
    q.ds = r && r.ds[0] ? r.ds[0].id : null;
    q.ied = r && r.ied[0] ? r.ied[0].id : null;
    q.dsV = null; q.iedV = null;
    plan = null; planSig = null; landed = null;
    vers = {};
    paint();
  }

  /* ---------- 2. what goes in ---------- */

  /* Each entry's versions, from the route every version picker reads. */
  let vers = {};          // entry id -> versions, once fetched

  function inputsCard() {
    const r = recOf(q.gid);
    const box = el('div', { class: 'card' }, [
      el('div', { class: 'section-label', text: '2. What goes in' }),
      el('div', { class: 'jn-inputs' }, [
        sideOf('ds', r.ds, 'Incisor', 'i'),
        sideOf('ied', r.ied, 'Doppler', 'd'),
      ]),
      BARRY.ui.field({
        label: 'Merge window (ms)',
        inline: true,
        hint: 'Events this close are one event: by time only, on any '
            + 'channel, each paired with at most one of the other '
            + 'detector’s, nearest first.',
        control: el('input', {
          type: 'number', class: 'num', min: 0.5, max: 100, step: 0.5,
          value: q.win, disabled: merging ? 'disabled' : null,
          onchange: (e) => {
            const v = Number(e.target.value);
            q.win = v > 0 && v <= 100 ? v : defaultWin;
            e.target.value = q.win;
            landed = null;
            requestPlan();
          },
        }),
      }),
      keepField(() => { landed = null; requestPlan(); }),
    ]);
    return box;
  }

  /* Whose time a merged event keeps. Incisor's by default -- a dentate-spike
     detector stamps the peak itself -- or Doppler's. The same pairs merge
     either way; the other detector's time is kept beside it. */
  function keepField(onChange) {
    const other = q.keep === 'incisor' ? 'Doppler' : 'Incisor';
    return BARRY.ui.field({
      label: 'Merged events keep',
      inline: true,
      extra: 'jn-keep',
      hint: 'A merged event is filed at ' + KEEP_WORD[q.keep] + '’s time, '
          + 'with its channel; ' + other + '’s time is kept beside it, so '
          + 'the gap can always be read back.',
      control: BARRY.ui.seg([
        ['incisor', 'Incisor’s time', 'The dentate-spike detector’s stamp, '
                                     + 'on the spike’s own peak'],
        ['doppler', 'Doppler’s time', 'The discharge detector’s stamp'],
      ], q.keep, (k) => {
        if (merging) return;
        q.keep = k;
        const f = document.querySelector('.jn-keep');
        if (f) f.replaceWith(keepField(onChange));
        onChange();
      }),
    });
  }

  function sideOf(kind, entries, who, cls) {
    const pickId = kind === 'ds' ? q.ds : q.ied;
    const ent = entries.find((x) => x.id === pickId) || entries[0];
    const side = el('div', { class: 'jn-side ' + cls }, [
      el('div', { class: 'jn-side-hd' }, [
        el('i', { class: 'jn-dot ' + cls }),
        el('strong', { text: who }),
        el('span', { class: 'hint quiet',
          text: kind === 'ds' ? 'dentate spikes' : 'interictal discharges' }),
        // Of what goes in: this entry, at the version chosen below.
        alignChip(ent, kind === 'ds' ? q.dsV : q.iedV, kind),
      ]),
    ]);
    if (entries.length > 1) {
      const row = (x) => el('button', {
        class: 'jn-ent' + (x.id === ent.id ? ' on' : '')
               + (x.archived ? ' is-archived' : ''),
        title: (x.pipeline || '') + (x.at ? ' · ' + x.at.slice(0, 10) : ''),
        onclick: () => {
          if (kind === 'ds') { q.ds = x.id; q.dsV = null; }
          else { q.ied = x.id; q.iedV = null; }
          landed = null; paint();
        },
      }, [el('span', { text: x.name || x.id }),
          /* Two entries on one recording often share a name -- a re-run
             of the same detector -- so each says how far it has got and
             when it was last worked on. */
          el('span', { class: 'hint quiet',
            text: BARRY.ui.versionLabel(x.tip) + ' · ' + num(x.n)
                + (x.at ? ' · ' + String(x.at).slice(0, 10) : '') }),
          alignWord(x)]);
      /* Archived entries sink below the live ones, behind one toggle
         (the user's rule, 2026-10-20): kept, not offered first. The
         server sends them last and flagged (`archived`). */
      const [liveEnts, goneEnts] = BARRY.ui.splitArchived(
        entries, (x) => !!x.archived);
      side.appendChild(el('div', { class: 'jn-ents' }, liveEnts.map(row)));
      const tail = BARRY.ui.archivedTail({
        key: 'jn-' + kind + '-' + (q.gid || ''), items: goneEnts,
        noun: ['entry', 'entries'],
        forceOpen: goneEnts.some((x) => x.id === ent.id),
        render: (xs) => el('div', { class: 'jn-ents' }, xs.map(row)),
        onToggle: () => paint(),
      });
      if (tail) side.appendChild(tail);
    } else {
      side.appendChild(el('div', { class: 'jn-ent-one' }, [
        el('span', { text: ent.name || ent.id }),
        el('span', { class: 'hint quiet', text: num(ent.n) + ' events' }),
      ]));
    }
    // The version tree, once this entry's versions are here.
    const vs = vers[ent.id];
    const slot = el('div', { class: 'jn-vers' });
    side.appendChild(slot);
    if (!vs) {
      slot.appendChild(el('div', { class: 'hint quiet',
        text: 'Reading its versions…' }));
      fetchVersions().then(() => {
        if (q.gid && vers[ent.id]) {
          const s2 = sideOf(kind, entries, who, cls);
          side.replaceWith(s2);
        }
      });
      return side;
    }
    if (vs.length < 2) {
      slot.appendChild(el('div', { class: 'hint quiet',
        text: 'One version, ' + BARRY.ui.versionLabel(vs[0] || ent.tip)
            + '.' }));
      return side;
    }
    const value = kind === 'ds' ? q.dsV : q.iedV;
    const onLine = new Set(ent.aligned_names || []);
    slot.appendChild(BARRY.ui.versionTree({
      producer: ent.pipeline, producerType: kind,
      versions: vs,
      idOf: (v) => v.id,
      value: value,
      unit: 'events',
      lead: { name: 'newest', text: num(ent.n) + ' events, as it stands'
                                  + (ent.aligned ? ' · aligned' : '') },
      disabled: (v) => (v.usable ? null : 'no snapshot of this version on '
                                          + 'this computer'),
      // The tree itself says "aligned" on the version an alignment wrote;
      // a pass after it carries the same stamps, and says so.
      state: (v) => (!v.aligned && onLine.has(v.name) ? ['stamps aligned'] : []),
      notes: (v) => {
        const bl = v.by_label || {};
        const ks = Object.keys(bl).sort((a, b) => bl[b] - bl[a]);
        return ks.map((k) => (k === 'unspecified' ? 'undecided' : k) + ' '
                       + bl[k]).join('  ·  ') || (num(v.n) + ' events');
      },
      onpick: (v) => {
        const id = v ? v.id : null;
        if (kind === 'ds') q.dsV = id; else q.iedV = id;
        landed = null;
        const s2 = sideOf(kind, entries, who, cls);
        side.replaceWith(s2);
        requestPlan();
      },
    }));
    return side;
  }

  let versFetching = null;
  function fetchVersions() {
    if (versFetching) return versFetching;
    const gid = q.gid;
    versFetching = api('/api/curation/for-recording/' + encodeURIComponent(gid))
      .then((got) => {
        for (const e of (got.entries || [])) vers[e.id] = e.versions || [];
      })
      .catch(() => {
        const r = recOf(gid);
        for (const e of [].concat(r ? r.ds : [], r ? r.ied : [])) {
          if (!vers[e.id]) vers[e.id] = [];
        }
      })
      .finally(() => { versFetching = null; });
    return versFetching;
  }

  /* ---------- 3. the pool ---------- */
  function body() {
    return { gid: q.gid, ds_entry: q.ds, ds_version: q.dsV,
             ied_entry: q.ied, ied_version: q.iedV, window_ms: q.win,
             keep: q.keep };
  }

  let planTimer = null;
  function requestPlan() {
    if (planTimer) clearTimeout(planTimer);
    planTimer = setTimeout(runPlan, 160);
  }

  async function runPlan() {
    planTimer = null;
    if (!q.gid || !q.ds || !q.ied) return;
    const sig = JSON.stringify(body());
    if (sig === planSig && plan) { drawStageIdle(); return; }
    planSig = sig;
    planning = true;
    paintPool();
    try {
      const got = await apiPost('/api/confluence/plan', body());
      if (planSig !== sig) return;          // superseded
      plan = got; planErr = null;
    } catch (e) {
      if (planSig !== sig) return;
      plan = null; planErr = e.message;
    } finally {
      if (planSig === sig) planning = false;
    }
    paintPool();
  }

  function poolCard() {
    return el('div', { class: 'card jn-pool', id: 'jnPool' }, poolKids());
  }

  function paintPool() {
    const box = document.getElementById('jnPool');
    if (!box || merging) return;
    box.innerHTML = '';
    for (const k of poolKids()) box.appendChild(k);
    requestAnimationFrame(drawStageIdle);
  }

  function poolKids() {
    const st = (plan && plan.stats) || null;
    const kids = [
      el('div', { class: 'section-label', text: '3. The pool' }),
      el('canvas', { id: 'jnStage', class: 'jn-stage' }),
    ];
    if (planErr) {
      kids.push(el('p', { class: 'warn-line', text: planErr }));
      return kids;
    }
    kids.push(countsRow(st, !!landed));
    const al = alignedLine();
    if (al) kids.push(al);
    const left = st ? [
      st.ds_left_out ? st.ds_left_out + ' of Incisor’s' : null,
      st.ied_left_out ? st.ied_left_out + ' of Doppler’s' : null,
    ].filter(Boolean) : [];
    if (left.length) {
      kids.push(el('p', { class: 'hint quiet',
        text: left.join(' and ') + ' already called Garbage stay out: '
            + 'somebody looked and said they are not events.' }));
    }
    if (plan && plan.already && !landed) {
      kids.push(el('p', { class: 'hint',
        text: 'Already pooled from exactly these inputs, as “'
            + (plan.already.name || plan.already.id) + '”. Merging '
            + 'again makes a second entry beside it.' }));
    }
    if (landed) {
      const e = landed.entry || {};
      kids.push(el('div', { class: 'jn-landed' }, [
        el('span', { text: (landed.cached ? 'Already banked as “'
                                          : 'Banked as “')
                         + (e.name || e.id) + '”.' }),
        el('span', { class: 'spacer' }),
        BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'Pan them',
          title: 'Sort the pool in Panning: spike, garbage or flag',
          onclick: () => panIt(q.gid, e.id) }),
      ]));
    } else {
      kids.push(el('div', { class: 'tk-actions' }, [
        el('span', { class: 'hint quiet',
          text: 'Nothing is written until you merge. The pool is a new bank '
              + 'entry; the two it came from are not changed.' }),
        el('span', { class: 'spacer' }),
        el('button', {
          class: 'btn', id: 'jnGo',
          text: plan && plan.already ? 'Merge again' : 'Merge them',
          disabled: (!plan || planning || merging) ? 'disabled' : null,
          onclick: () => merge(!!(plan && plan.already)),
        }),
      ]));
    }
    return kids;
  }

  /* What the pool is made from, aligned or not, in a sentence under the
     counts -- from the plan when there is one (the server's answer for the
     versions actually going in), else from what is chosen. */
  function alignedLine() {
    const r = recOf(q.gid);
    if (!r) return null;
    const pr = (plan && plan.params) || null;
    const ds = r.ds.find((x) => x.id === q.ds) || r.ds[0];
    const ied = r.ied.find((x) => x.id === q.ied) || r.ied[0];
    const a = pr && pr.ds_aligned != null ? !!pr.ds_aligned : alignedAt(ds, q.dsV);
    const b = pr && pr.ied_aligned != null ? !!pr.ied_aligned : alignedAt(ied, q.iedV);
    const chips = [
      BARRY.ui.chip('Incisor ' + (a ? '✓ aligned' : 'not aligned'),
                    { kind: a ? 'ok' : null, extra: 'jn-al i' + (a ? ' on' : '') }),
      BARRY.ui.chip('Doppler ' + (b ? '✓ aligned' : 'not aligned'),
                    { kind: b ? 'ok' : null, extra: 'jn-al d' + (b ? ' on' : '') }),
    ];
    const said = a && b
      ? 'Both inputs are aligned: every stamp is on its peak, so the gap '
        + 'between the two detectors is theirs.'
      : (!a && !b
        ? 'Neither input has been aligned (Braces for Incisor’s, Eye for '
          + 'Doppler’s), so a gap between the two is partly where each put '
          + 'its stamp. Pooling works either way.'
        : (a ? 'Doppler’s' : 'Incisor’s') + ' input is not aligned ('
          + (a ? 'Eye, The Storm' : 'Braces, The Dentist') + ', step 3), so '
          + 'a gap to it is partly where it put its stamp. Pooling works '
          + 'either way.');
    return el('div', { class: 'jn-aligned' }, [
      el('span', { class: 'section-label', text: 'Aligned' }),
      ...chips,
      el('span', { class: 'hint quiet', text: said }),
    ]);
  }

  /* The four numbers, in the order the eye reads the picture: what came in
     from each side, what fused, what the pool holds. */
  function countsRow(st, final) {
    const cell = (cls, label, v, id) => el('div', { class: 'jn-n ' + cls }, [
      el('b', { id: id || null, text: st ? num(v) : '—' }),
      el('span', { text: label }),
    ]);
    return el('div', { class: 'jn-counts' + (final ? ' final' : '') }, [
      cell('i', 'Incisor only', st && st.incisor_only, 'jnNi'),
      cell('b', 'both, merged', st && st.merged, 'jnNb'),
      cell('d', 'Doppler only', st && st.doppler_only, 'jnNd'),
      cell('t', 'in the pool', st && st.n, 'jnNt'),
      st ? el('div', { class: 'jn-n w' }, [
        el('b', { text: '±' + st.window_ms + ' ms' }),
        el('span', { text: st.dt_ms && st.dt_ms.length
          ? 'median gap ' + median(st.dt_ms).toFixed(2) + ' ms'
          : 'window' }),
      ]) : null,
    ].filter(Boolean));
  }

  function median(xs) {
    const s = xs.slice().sort((a, b) => a - b);
    if (!s.length) return 0;
    const m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }

  /* ==================================================================
     The stage
     ================================================================== */

  /* Where everything is, for a canvas of width w. */
  function geom(w) {
    const h = 200;
    const fw = Math.min(184, Math.max(122, w * 0.27)), fh = 62;
    const out = { w, h, fw, fh };
    out.I = { x: 10, y: 22, w: fw, h: fh };
    out.D = { x: 10, y: h - 22 - fh, w: fw, h: fh };
    out.P = { x: w - fw - 10, y: (h - fh) / 2, w: fw, h: fh };
    out.J = { x: Math.round(w * 0.6), y: h / 2 };
    return out;
  }

  // Points along each leg: cubic beziers from a file to the junction, and
  // the junction to the pool.
  function bez(p0, p1, p2, p3, t) {
    const u = 1 - t;
    return {
      x: u * u * u * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t * t * t * p3.x,
      y: u * u * u * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t * t * t * p3.y,
    };
  }
  function legs(G) {
    const a0 = { x: G.I.x + G.I.w, y: G.I.y + G.I.h / 2 };
    const b0 = { x: G.D.x + G.D.w, y: G.D.y + G.D.h / 2 };
    const mid = (G.J.x - a0.x) * 0.55;
    const end = { x: G.P.x, y: G.P.y + G.P.h / 2 };
    return {
      i: [a0, { x: a0.x + mid, y: a0.y }, { x: G.J.x - mid * 0.6, y: G.J.y - 3 },
          { x: G.J.x, y: G.J.y - 3 }],
      d: [b0, { x: b0.x + mid, y: b0.y }, { x: G.J.x - mid * 0.6, y: G.J.y + 3 },
          { x: G.J.x, y: G.J.y + 3 }],
      o: [{ x: G.J.x, y: G.J.y }, { x: G.J.x + (end.x - G.J.x) * 0.4, y: G.J.y },
          { x: end.x - (end.x - G.J.x) * 0.4, y: end.y }, end],
    };
  }

  function sizeStage() {
    const cv = document.getElementById('jnStage');
    if (!cv) return null;
    const w = Math.max(320, Math.round(cv.clientWidth
      || (cv.parentNode && cv.parentNode.clientWidth) || 640));
    const G = geom(w);
    const dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(G.h * dpr);
    cv.style.height = G.h + 'px';
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { cv, g, G };
  }

  /* Text that is never cut short: shrunk a little (to 9.5px), then broken
     onto a second line at the middle-most space, and only then shrunk
     further until both lines fit. Two readable lines beat one tiny one. */
  function fitLines(g, text, room, px, weight) {
    let pt = px;
    const font = (p) => (weight ? weight + ' ' : '') + p + 'px system-ui, sans-serif';
    const wide = (s) => g.measureText(s).width > room;
    g.font = font(pt);
    while (pt > 9.5 && wide(text)) { pt -= 0.5; g.font = font(pt); }
    if (!wide(text)) return { lines: [text], pt };
    const mid = text.length / 2;
    let best = -1;
    for (let j = 0; j < text.length; j++) {
      if (text[j] === ' ' && (best < 0 || Math.abs(j - mid) < Math.abs(best - mid))) best = j;
    }
    const lines = best < 0 ? [text] : [text.slice(0, best), text.slice(best + 1)];
    while (pt > 7 && lines.some(wide)) { pt -= 0.5; g.font = font(pt); }
    return { lines, pt };
  }

  function fileCard(g, box, colour, colour2, title, sub, count, glow) {
    const r = 8;
    g.save();
    if (glow) {
      g.shadowColor = colour;
      g.shadowBlur = 18 * glow;
    }
    g.fillStyle = tok('--bg-2', '#1b1f1d');
    g.strokeStyle = tok('--line', '#333');
    g.lineWidth = 1;
    g.beginPath();
    g.roundRect ? g.roundRect(box.x, box.y, box.w, box.h, r)
                : g.rect(box.x, box.y, box.w, box.h);
    g.fill();
    g.shadowBlur = 0;
    g.stroke();
    // The colour edge: one colour for a detector, two for the pool.
    g.fillStyle = colour;
    g.fillRect(box.x + 1, box.y + 6, 4, colour2 ? (box.h - 12) / 2 : box.h - 12);
    if (colour2) {
      g.fillStyle = colour2;
      g.fillRect(box.x + 1, box.y + box.h / 2, 4, (box.h - 12) / 2);
    }
    // A folded corner, so it reads as a file.
    g.fillStyle = tok('--bg-3', '#2a2f2c');
    g.beginPath();
    g.moveTo(box.x + box.w - 12, box.y);
    g.lineTo(box.x + box.w, box.y + 12);
    g.lineTo(box.x + box.w - 12, box.y + 12);
    g.closePath();
    g.fill();
    const room = box.w - 20;
    g.fillStyle = tok('--text', '#eee');
    g.textBaseline = 'alphabetic';
    g.textAlign = 'left';
    const t = fitLines(g, title, room, 12, '600');
    g.font = '600 ' + t.pt + 'px system-ui, sans-serif';
    g.fillText(t.lines[0], box.x + 12, box.y + 17);
    g.fillStyle = tok('--text-3', '#888');
    const s = fitLines(g, sub, room, 10);
    g.font = s.pt + 'px system-ui, sans-serif';
    s.lines.forEach((ln, k) => g.fillText(ln, box.x + 12, box.y + 30 + k * (s.pt + 1)));
    if (count != null) {
      g.fillStyle = tok('--text', '#eee');
      g.font = '600 13px system-ui, sans-serif';
      g.textAlign = 'right';
      g.fillText(count, box.x + box.w - 8, box.y + box.h - 8);
      g.textAlign = 'left';
    }
    g.restore();
  }

  function labelsFor() {
    const r = recOf(q.gid);
    if (!r) return null;
    const ds = r.ds.find((x) => x.id === q.ds) || r.ds[0];
    const ied = r.ied.find((x) => x.id === q.ied) || r.ied[0];
    const vName = (id, ent) => {
      const v = (vers[ent.id] || []).find((x) => x.id === id);
      return v ? BARRY.ui.versionLabel(v) : BARRY.ui.versionLabel(ent.tip);
    };
    const st = (plan && plan.stats) || {};
    return {
      i: { title: 'Incisor', sub: (ds.name || ds.id) + ' · ' + vName(q.dsV, ds),
           n: st.n_ds },
      d: { title: 'Doppler', sub: (ied.name || ied.id) + ' · ' + vName(q.iedV, ied),
           n: st.n_ied },
    };
  }

  /* The quiet state: the two files, the pool, and the stream between them
     flowing gently -- the same flow the ToolKit's rail draws. */
  function drawStageIdle() {
    if (merging) return;
    if (stageStop) { stageStop(); stageStop = null; }
    const s = sizeStage();
    if (!s) return;
    const L = labelsFor();
    if (!L) return;
    const st = (plan && plan.stats) || null;
    const ci = tok('--o-incisor', '#8ec5ff');
    const cd = tok('--o-doppler', '#f59fb4');
    const paintOnce = (phase) => {
      const { g, G } = s;
      g.clearRect(0, 0, G.w, G.h);
      const P = legs(G);
      bed(g, P, ci, cd, phase);
      fileCard(g, G.I, ci, null, L.i.title, L.i.sub,
               L.i.n != null ? num(L.i.n) : null);
      fileCard(g, G.D, cd, null, L.d.title, L.d.sub,
               L.d.n != null ? num(L.d.n) : null);
      fileCard(g, G.P, ci, cd, landed ? 'Pooled' : 'The pool',
               landed ? ((landed.entry || {}).name || 'banked')
                      : (planning ? 'working it out…'
                         : st ? '±' + st.window_ms + ' ms'
                                + (q.keep === 'doppler' ? ', Doppler’s time' : '')
                                + ', not yet banked'
                              : 'pick what goes in'),
               st ? num(st.n) : null, landed ? 0.6 : 0);
    };
    if (reduced()) { paintOnce(0); return; }
    let alive = true;
    const t0 = performance.now();
    const tick = (now) => {
      if (!alive || !s.cv.isConnected) return;
      paintOnce(((now - t0) / 2400) % 1);
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    stageStop = () => { alive = false; };
  }

  /* The river bed: the three legs, and dashes travelling along them. */
  function bed(g, P, ci, cd, phase) {
    const path = (pts) => {
      g.beginPath();
      g.moveTo(pts[0].x, pts[0].y);
      g.bezierCurveTo(pts[1].x, pts[1].y, pts[2].x, pts[2].y, pts[3].x, pts[3].y);
    };
    g.save();
    g.lineCap = 'round';
    for (const [pts, col] of [[P.i, ci], [P.d, cd]]) {
      g.globalAlpha = 0.22; g.strokeStyle = col; g.lineWidth = 6;
      path(pts); g.stroke();
      g.globalAlpha = 0.85; g.lineWidth = 1.6;
      g.setLineDash([2, 10]); g.lineDashOffset = -phase * 24;
      path(pts); g.stroke();
      g.setLineDash([]);
    }
    // After the junction: the two colours side by side, as a merged event is.
    const off = (pts, dy) => pts.map((p) => ({ x: p.x, y: p.y + dy }));
    for (const [dy, col] of [[-2, ci], [2, cd]]) {
      const pts = off(P.o, dy);
      g.globalAlpha = 0.22; g.strokeStyle = col; g.lineWidth = 4;
      path(pts); g.stroke();
      g.globalAlpha = 0.85; g.lineWidth = 1.4;
      g.setLineDash([2, 10]); g.lineDashOffset = -phase * 24;
      path(pts); g.stroke();
      g.setLineDash([]);
    }
    g.restore();
  }

  /* ==================================================================
     The merge
     ================================================================== */

  /* How long the picture takes, in ms. One table, so the sound and the
     counts cannot drift from it. */
  const T = { emit: 1700, toJ: 650, toP: 560, settle: 380 };
  const MAX_DOTS = 180;

  /* A fair sample of the pool's events for the picture: every kind in
     proportion, in time order, so a recording whose merges bunch at the
     start shows them bunching at the start. */
  function sample(evs) {
    if (evs.length <= MAX_DOTS) return evs.slice();
    const out = [];
    const step = evs.length / MAX_DOTS;
    for (let k = 0; k < MAX_DOTS; k++) out.push(evs[Math.floor(k * step)]);
    return out;
  }

  async function merge(force) {
    if (merging || !plan) return;
    merging = true;
    landed = null;
    const btn = document.getElementById('jnGo');
    if (btn) { btn.disabled = true; btn.textContent = 'Merging…'; }
    const send = apiPost('/api/confluence/merge',
                         Object.assign(body(), { force: !!force }))
      .then((r) => ({ ok: true, r }), (e) => ({ ok: false, e }));
    await play(plan, send);
    const got = await send;
    merging = false;
    if (!got.ok) {
      toast('That was not banked: ' + got.e.message, 'err', 10000);
      paintPool();
      return;
    }
    landed = got.r;
    sfx('land');
    BARRY.activity.log('junction.merge', {
      gid: q.gid, entry: (got.r.entry || {}).id,
      merged: (got.r.stats || {}).merged, cached: !!got.r.cached,
    });
    // The list knows about the new pool, for the chips and for Many.
    load(true).then(() => { if (q.mode === 'one') paintPool(); });
    paintPool();
  }

  /* Draw the merge, and resolve when it has been drawn. Timer-driven at the
     end as well as by frame, so a background tab -- or a harness under
     virtual time -- still finishes. */
  function play(pl, pending) {
    return new Promise((resolve) => {
      if (stageStop) { stageStop(); stageStop = null; }
      const s = sizeStage();
      const L = labelsFor();
      const st = pl.stats || {};
      if (!s || !L) { resolve(); return; }
      const ci = tok('--o-incisor', '#8ec5ff');
      const cd = tok('--o-doppler', '#f59fb4');
      const P = legs(s.G);
      const evs = sample(pl.events || []);
      const t0s = evs.length ? evs[0].t : 0;
      const span = Math.max(1e-6, (evs.length ? evs[evs.length - 1].t : 1) - t0s);
      const dots = evs.map((e) => ({
        o: e.o, at: ((e.t - t0s) / span) * T.emit,
      }));
      const inCat = { incisor: 0, both: 0, doppler: 0 };
      for (const d of dots) inCat[d.o] += 1;
      const arrived = { incisor: 0, both: 0, doppler: 0 };
      const total = T.emit + T.toJ + T.toP + T.settle;
      let fused = [];            // flashes at the junction
      let done = false;

      const counts = () => ({
        i: inCat.incisor ? Math.round(st.incisor_only * arrived.incisor / inCat.incisor) : 0,
        b: inCat.both ? Math.round(st.merged * arrived.both / inCat.both) : 0,
        d: inCat.doppler ? Math.round(st.doppler_only * arrived.doppler / inCat.doppler) : 0,
      });
      const setText = (id, v) => {
        const n = document.getElementById(id);
        if (n) n.textContent = num(v);
      };
      const showCounts = (c) => {
        setText('jnNi', c.i); setText('jnNb', c.b); setText('jnNd', c.d);
        setText('jnNt', c.i + c.b + c.d);
      };

      const frame = (ms) => {
        const { g, G } = s;
        g.clearRect(0, 0, G.w, G.h);
        bed(g, P, ci, cd, (ms / 2400) % 1);
        // What has left each file, so their counts run down as the pool's
        // run up.
        let leftI = 0, leftD = 0;
        for (const d of dots) {
          if (ms >= d.at) {
            if (d.o !== 'doppler') leftI += 1;
            if (d.o !== 'incisor') leftD += 1;
          }
        }
        const nI = inCat.incisor + inCat.both, nD = inCat.doppler + inCat.both;
        const remain = (n, gone, of) => (of ? Math.round(n * (1 - gone / of)) : n);
        fileCard(g, G.I, ci, null, L.i.title, L.i.sub,
                 num(remain(st.n_ds || 0, leftI, nI)));
        fileCard(g, G.D, cd, null, L.d.title, L.d.sub,
                 num(remain(st.n_ied || 0, leftD, nD)));
        arrived.incisor = 0; arrived.both = 0; arrived.doppler = 0;
        for (const d of dots) {
          const k = ms - d.at;
          if (k < 0) continue;
          if (k < T.toJ) {
            const f = k / T.toJ;
            const e = f * f * (3 - 2 * f);
            if (d.o !== 'doppler') dot(g, bez(...P.i, e), ci, null, 2.4);
            if (d.o !== 'incisor') dot(g, bez(...P.d, e), cd, null, 2.4);
          } else if (k < T.toJ + T.toP) {
            const f = (k - T.toJ) / T.toP;
            const p = bez(...P.o, f);
            if (d.o === 'both') {
              if (!d.flashed) { d.flashed = true; fused.push({ at: ms }); }
              dot(g, p, ci, cd, 3.6);
            } else {
              dot(g, { x: p.x, y: p.y + (d.o === 'incisor' ? -2 : 2) },
                  d.o === 'incisor' ? ci : cd, null, 2.4);
            }
          } else {
            arrived[d.o] += 1;
          }
        }
        // A fusion is a small ring opening at the junction.
        fused = fused.filter((f) => ms - f.at < 420);
        for (const f of fused) {
          const a = (ms - f.at) / 420;
          g.save();
          g.globalAlpha = 0.7 * (1 - a);
          g.strokeStyle = tok('--text', '#fff');
          g.lineWidth = 1.2;
          g.beginPath();
          g.arc(G.J.x, G.J.y, 4 + 14 * a, 0, Math.PI * 2);
          g.stroke();
          g.restore();
        }
        const c = counts();
        const glow = Math.min(1, (arrived.incisor + arrived.both + arrived.doppler)
                                 / Math.max(1, dots.length));
        fileCard(g, G.P, ci, cd, 'The pool', 'filling…',
                 num(c.i + c.b + c.d), 0.2 + 0.6 * glow);
        showCounts(c);
      };

      const finish = () => {
        if (done) return;
        done = true;
        showCounts({ i: st.incisor_only || 0, b: st.merged || 0,
                     d: st.doppler_only || 0 });
        resolve();
      };

      if (reduced() || !dots.length) {
        // Nothing moves: the stage as it ends, and the numbers as they are.
        showCounts({ i: st.incisor_only || 0, b: st.merged || 0,
                     d: st.doppler_only || 0 });
        pending.then(() => resolve());
        return;
      }
      sfx('charge', total / 1000);
      const start = performance.now();
      const loop = (now) => {
        if (done) return;
        const ms = now - start;
        frame(Math.min(ms, total));
        if (ms < total) requestAnimationFrame(loop);
        else finish();
      };
      requestAnimationFrame(loop);
      setTimeout(finish, total + 400);
    });
  }

  function dot(g, p, c1, c2, r) {
    g.beginPath();
    if (c2) {
      g.arc(p.x, p.y, r, Math.PI / 2, Math.PI * 1.5);
      g.closePath();
      g.fillStyle = c1;
      g.fill();
      g.beginPath();
      g.arc(p.x, p.y, r, -Math.PI / 2, Math.PI / 2);
      g.closePath();
      g.fillStyle = c2;
      g.fill();
      return;
    }
    g.arc(p.x, p.y, r, 0, Math.PI * 2);
    g.fillStyle = c1;
    g.fill();
  }

  /* Onto Panning's bench, not straight into Xplorefinder (2026-10-20:
     "pick a set and version into the workbench, inspect its details, then
     open Xplorefinder only if needed"). */
  function panIt(gid, entryId) {
    const tk = BARRY.views.toolkit;
    if (tk && tk.benchFrom) tk.benchFrom('panning', gid, entryId);
  }

  /* ==================================================================
     Many at once
     ================================================================== */
  /* The version each side pools from: the one chosen on its row, else
     the newest (the entry's tip). */
  const manyVer = (r, side) => {
    const d = defaultsFor(r)[side];
    const want = (q.manyV[r.gid] || {})[side];
    return want || (d && d.tip);
  };
  const pooledDefault = (r) => {
    const d = defaultsFor(r);
    return !!(d.ds && d.ied && pooledFrom(r, d.ds.id, manyVer(r, 'ds'),
                                          d.ied.id, manyVer(r, 'ied'), q.win));
  };
  /* The rows the search finds, in number order (m1, m3, m12). */
  const manyRows = () => BARRY.ui.natSort((recs || []).filter(
    (r) => BARRY.ui.searchMatch([nameOf(r), r.project, r.gid,
                                 ((defaultsFor(r).ds || {}).name),
                                 ((defaultsFor(r).ied || {}).name)],
                                q.manyFind, { mouse: r.mouse, session: r.session })),
    (r) => nameOf(r));
  const nAligned = (rows) => rows.filter(
    (r) => (r.ds[0] || {}).aligned && (r.ied[0] || {}).aligned).length;

  function paintMany(h) {
    if (!q.sel) q.sel = new Set();
    const all = recs || [];
    const rows = manyRows();
    const box = el('div', { class: 'card' }, [
      el('div', { class: 'section-label', text: 'Which recordings' }),
      el('p', { class: 'hint',
        text: 'Each is pooled from its newest Incisor entry and its newest '
            + 'Doppler entry, at the versions shown -- the newest, unless '
            + 'another is chosen on its row. To choose another entry, pool '
            + 'that recording on its own.' }),
    ]);
    /* A search, as every list of recordings has (2026-10-20): "m3s2",
       "M3S2" and "m3 s2" find the same recording. */
    const found = el('span', { class: 'hint jn-many-count' });
    const list = el('div', { class: 'jn-many', id: 'jnMany' });
    const fill = () => {
      const shown = manyRows();
      list.innerHTML = '';
      for (const r of shown) list.appendChild(manyRow(r));
      if (!shown.length) {
        list.appendChild(el('p', { class: 'hint quiet',
          text: all.length ? 'None of them match.' : 'Nothing to pool yet.' }));
      }
      found.textContent = shown.length === all.length
        ? all.length + ' recording' + (all.length === 1 ? '' : 's')
        : shown.length + ' of ' + all.length + ' shown';
    };
    box.appendChild(el('div', { class: 'cur-filter jn-many-find' }, [
      BARRY.ui.searchField({
        placeholder: 'Type a mouse, session, project or entry\u2026',
        value: q.manyFind,
        oninput: (ev) => {
          q.manyFind = (ev && ev.target) ? ev.target.value : (ev || '');
          fill();
        },
      }),
      found,
    ]));
    fill();
    box.appendChild(list);
    const n = all.filter((r) => q.sel.has(r.gid)).length;
    box.appendChild(BARRY.ui.field({
      label: 'Merge window (ms)', inline: true,
      control: el('input', { type: 'number', class: 'num', min: 0.5,
        max: 100, step: 0.5, value: q.win,
        disabled: merging ? 'disabled' : null,
        onchange: (e) => {
          const v = Number(e.target.value);
          q.win = v > 0 && v <= 100 ? v : defaultWin;
          batch = null; paint();
        } }),
    }));
    box.appendChild(keepField(() => { batch = null; paint(); }));
    box.appendChild(el('div', { class: 'tk-actions' }, [
      el('button', { class: 'btn ghost sm', text: 'All shown',
        title: 'Tick every recording the search shows',
        onclick: () => { for (const r of manyRows()) q.sel.add(r.gid); paint(); } }),
      el('button', { class: 'btn ghost sm', text: 'None',
        onclick: () => { q.sel.clear(); paint(); } }),
      el('button', { class: 'btn ghost sm', text: 'Not pooled yet',
        title: 'Only the recordings with no pool from their newest entries',
        onclick: () => {
          q.sel = new Set(manyRows().filter((r) => !pooledDefault(r))
                                    .map((r) => r.gid));
          paint();
        } }),
      el('button', { class: 'btn ghost sm',
        text: 'Both aligned (' + nAligned(rows) + ')',
        disabled: nAligned(rows) ? null : 'disabled',
        title: 'Only the recordings whose newest Incisor AND Doppler entries '
             + 'have both been aligned (Braces, Eye)',
        onclick: () => {
          q.sel = new Set(rows.filter((r) => (r.ds[0] || {}).aligned
                                             && (r.ied[0] || {}).aligned)
                              .map((r) => r.gid));
          paint();
        } }),
      el('span', { class: 'spacer' }),
      el('button', { class: 'btn', id: 'jnManyGo',
        text: n ? 'Merge ' + n + ' recording' + (n === 1 ? '' : 's')
                : 'Merge',
        disabled: (!n || merging) ? 'disabled' : null,
        onclick: mergeMany }),
    ]));
    h.appendChild(box);
    if (batch) h.appendChild(batchSummary());
  }

  function manyRow(r) {
    const d = defaultsFor(r);
    const done = pooledDefault(r);
    const res = batch && (batch.rows || []).find((x) => x.gid === r.gid);
    const row = el('div', { class: 'jn-mrow' + (res ? (res.ok ? ' ok' : ' bad') : ''),
                            'data-gid': r.gid }, [
      el('input', { type: 'checkbox', checked: q.sel.has(r.gid) ? 'checked' : null,
        disabled: merging ? 'disabled' : null,
        'aria-label': 'Pool ' + nameOf(r),
        onchange: (e) => {
          if (e.target.checked) q.sel.add(r.gid); else q.sel.delete(r.gid);
          const b = document.getElementById('jnManyGo');
          const n = (recs || []).filter((x) => q.sel.has(x.gid)).length;
          if (b) {
            b.textContent = n ? 'Merge ' + n + ' recording' + (n === 1 ? '' : 's')
                              : 'Merge';
            b.disabled = !n || merging;
          }
        } }),
      el('strong', { class: 'jn-mname', text: nameOf(r) }),
      el('span', { class: 'jn-mside i' }, [
        el('i', { class: 'jn-dot i' }),
        el('span', { text: (d.ds.name || d.ds.id) }),
        manyVerPick(r, 'ds'),
        alignWord(d.ds),
        el('b', { text: num(d.ds.n) }),
      ]),
      el('span', { class: 'jn-mside d' }, [
        el('i', { class: 'jn-dot d' }),
        el('span', { text: (d.ied.name || d.ied.id) }),
        manyVerPick(r, 'ied'),
        alignWord(d.ied),
        el('b', { text: num(d.ied.n) }),
      ]),
      el('canvas', { class: 'jn-mflow', width: 64, height: 26 }),
      el('span', { class: 'jn-mres' }, res ? resultBits(res, r)
        : [done ? BARRY.ui.chip('pooled already', { flag: true, kind: 'ok' })
                : el('span', { class: 'hint quiet', text: '' })]),
    ]);
    requestAnimationFrame(() => drawMini(row.querySelector('.jn-mflow'), res ? 1 : 0));
    return row;
  }

  /* Which set and version a side pools from: one button saying both --
     the set's name, its version, what made that version -- that opens the
     recording's pop-up (2026-10-21: "the sets are locked in... versions are
     so undescriptive... if it's by recording, pop up, see the sets and
     their versions"). */
  function manyVerPick(r, side) {
    const ent = defaultsFor(r)[side] || {};
    const vs = ent.versions || [];
    const cur = manyVer(r, side);
    const v = vs.find((x) => String(x.name) === String(cur)) || null;
    const others = ((side === 'ds' ? r.ds : r.ied) || []).length - 1;
    return el('button', {
      type: 'button', class: 'vbtn jn-mver',
      disabled: merging ? 'disabled' : null,
      title: 'The sets this recording has on each side and every version of '
           + 'them, as trees. Click to see them and choose.',
      onclick: () => manyPop(r, side),
    }, [
      el('strong', { class: 'vbtn-n', text: BARRY.ui.versionLabel(cur) }),
      v ? BARRY.ui.versionChip(v, ent.pipeline, side) : null,
      el('span', { class: 'vbtn-more',
        text: (vs.length > 1 ? vs.length + ' versions' : 'its only version')
            + (others > 0 ? ' · ' + others + ' other set'
                            + (others === 1 ? '' : 's') : '') }),
      el('span', { class: 'vbtn-caret', 'aria-hidden': 'true', text: '▾' }),
    ].filter(Boolean));
  }

  /* One recording's inputs, whole: every Incisor set and every Doppler set
     it has, each with its version tree. Choosing a set's version chooses
     the set and the version together; Done keeps it. */
  function manyPop(r, focus) {
    const card = (side, ent) => {
      const d = defaultsFor(r)[side] || {};
      const on = d.id === ent.id;
      const chosenV = on ? manyVer(r, side) : ent.tip;
      return el('div', { class: 'jn-ppop-set' + (on ? ' on' : '') }, [
        el('div', { class: 'jn-ppop-head' }, [
          el('strong', { text: ent.name || ent.id }),
          BARRY.ui.producerChip(ent.pipeline, side),
          alignWord(ent),
          on ? BARRY.ui.chip('pools from this', { flag: true, kind: 'ok' }) : null,
          ent.archived ? BARRY.ui.chip('archived', { flag: true }) : null,
        ].filter(Boolean)),
        BARRY.ui.versionTree({
          versions: ent.versions || [], value: on ? chosenV : null,
          idOf: (v) => v.name, notes: true, family: false,
          producer: ent.pipeline, producerType: side,
          onpick: (v) => {
            if (!v) return;
            (q.manyE[r.gid] = q.manyE[r.gid] || {})[side] = ent.id;
            (q.manyV[r.gid] = q.manyV[r.gid] || {})[side] =
              String(v.name) === String(ent.tip) ? null : v.name;
            batch = null;
            redraw();
          },
        }),
      ]);
    };
    const col = (side, label) => {
      // Archived sets last (the user's rule): kept, not offered first.
      const [liveE, goneE] = BARRY.ui.splitArchived(
        (side === 'ds' ? r.ds : r.ied) || [], (x) => !!x.archived);
      const ents = liveE.concat(goneE);
      return el('div', { class: 'jn-ppop-col' + (focus === side ? ' focus' : '') }, [
        el('div', { class: 'section-label', text: label }),
        ents.length ? null : el('p', { class: 'hint', text: 'None banked.' }),
      ].concat(ents.map((ent) => card(side, ent))).filter(Boolean));
    };
    const body = el('div', { class: 'jn-ppop' });
    function redraw() {
      body.innerHTML = '';
      body.appendChild(col('ds', 'Incisor’s dentate spikes'));
      body.appendChild(col('ied', 'Doppler’s IEDs'));
      requestAnimationFrame(() => body.querySelectorAll('.vtree')
        .forEach((t) => t.redraw && t.redraw()));
    }
    redraw();
    showModal(el('div', { class: 'vpop jn-ppop-wrap' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: nameOf(r) + ': what it pools from' }),
        el('div', { class: 'spacer' }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { class: 'hint', text: 'Every set this recording has on each '
          + 'side, with every version of it: who made it, when, what processed '
          + 'it and its note. Click a version to pool from that set at that '
          + 'version.' }),
        body,
      ]),
      BARRY.ui.modalFoot([], [BARRY.ui.button({ kind: 'primary', text: 'Done',
        onclick: () => { closeModal(); paint(); } })]),
    ]));
  }

  function resultBits(res, r) {
    if (!res.ok) return [el('span', { class: 'warn-line', text: res.error })];
    const st = res.stats || {};
    return [
      el('span', { class: 'jn-mnum', text: num((st.incisor_only || 0)
        + (st.merged || 0) + (st.doppler_only || 0)) }),
      el('span', { class: 'hint quiet',
        text: num(st.merged) + ' merged' + (res.cached ? ' · already banked' : '') }),
      BARRY.ui.button({ kind: 'mini', text: 'Pan',
        title: 'Sort this pool in Panning',
        onclick: () => panIt(r.gid, (res.entry || {}).id) }),
    ];
  }

  /* A row's own small junction: two strands into one, drawn still, and
     filled with a pulse when its result lands. */
  function drawMini(cv, f) {
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    cv.width = 64 * dpr; cv.height = 26 * dpr;
    cv.style.width = '64px'; cv.style.height = '26px';
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, 64, 26);
    const ci = tok('--o-incisor', '#8ec5ff');
    const cd = tok('--o-doppler', '#f59fb4');
    g.lineCap = 'round';
    const strand = (y0, col, dy) => {
      g.strokeStyle = col;
      g.globalAlpha = 0.35 + 0.65 * f;
      g.lineWidth = 1.6;
      g.beginPath();
      g.moveTo(2, y0);
      g.bezierCurveTo(18, y0, 22, 13 + dy, 34, 13 + dy);
      g.lineTo(62, 13 + dy);
      g.stroke();
    };
    strand(4, ci, -1.2);
    strand(22, cd, 1.2);
    g.globalAlpha = 1;
  }

  async function mergeMany() {
    if (merging) return;
    const rows = (recs || []).filter((r) => q.sel.has(r.gid));
    if (!rows.length) return;
    merging = true;
    batch = null;
    const b = document.getElementById('jnManyGo');
    if (b) { b.disabled = true; b.textContent = 'Merging…'; }
    const items = rows.map((r) => {
      const d = defaultsFor(r);
      const it = { gid: r.gid, ds_entry: d.ds.id, ied_entry: d.ied.id };
      // A version chosen on the row; the newest otherwise.
      const m = q.manyV[r.gid] || {};
      if (m.ds) it.ds_version = m.ds;
      if (m.ied) it.ied_version = m.ied;
      return it;
    });
    sfx('charge', Math.min(4, 0.9 + rows.length * 0.12));
    let got;
    try {
      got = await apiPost('/api/confluence/batch',
                          { items, window_ms: q.win, keep: q.keep });
    } catch (e) {
      merging = false;
      toast('The batch did not run: ' + e.message, 'err', 10000);
      paint();
      return;
    }
    batch = { rows: got.rows || [], at: Date.now() };
    // Each row lands in turn: its strands fill and its numbers run up.
    const step = reduced() ? 0 : 140;
    let k = 0;
    for (const res of batch.rows) {
      const r = recOf(res.gid);
      const rowEl = document.querySelector('.jn-mrow[data-gid="' + CSS.escape(res.gid) + '"]');
      if (!r || !rowEl) continue;
      const land = () => {
        rowEl.classList.add(res.ok ? 'ok' : 'bad');
        rowEl.classList.add('landing');
        const slot = rowEl.querySelector('.jn-mres');
        if (slot) {
          slot.innerHTML = '';
          for (const n of resultBits(res, r)) slot.appendChild(n);
          const big = slot.querySelector('.jn-mnum');
          if (big && res.ok) {
            const st = res.stats || {};
            BARRY.ui.countUp(big, (st.incisor_only || 0) + (st.merged || 0)
                                  + (st.doppler_only || 0), { ms: 520 });
          }
        }
        pulseMini(rowEl.querySelector('.jn-mflow'));
        if (res.ok && !res.cached) sfx('tick', k % 8);
      };
      if (step) setTimeout(land, k * step); else land();
      k += 1;
    }
    setTimeout(() => {
      merging = false;
      const made = batch.rows.filter((x) => x.ok && !x.cached).length;
      if (made) sfx('land');
      BARRY.activity.log('junction.batch', {
        n: batch.rows.length, made,
        failed: batch.rows.filter((x) => !x.ok).length,
      });
      load(true).then(() => { if (q.mode === 'many') paint(); });
    }, k * step + 600);
  }

  function pulseMini(cv) {
    if (!cv) return;
    if (reduced()) { drawMini(cv, 1); return; }
    const t0 = performance.now();
    const go = (now) => {
      const f = Math.min(1, (now - t0) / 420);
      drawMini(cv, f);
      if (f < 1 && cv.isConnected) requestAnimationFrame(go);
    };
    requestAnimationFrame(go);
    setTimeout(() => drawMini(cv, 1), 480);
  }

  function batchSummary() {
    const rows = batch.rows || [];
    const made = rows.filter((x) => x.ok && !x.cached).length;
    const had = rows.filter((x) => x.ok && x.cached).length;
    const bad = rows.filter((x) => !x.ok).length;
    return el('div', { class: 'card' }, [
      el('div', { class: 'section-label', text: 'What landed' }),
      BARRY.ui.chipRow([
        BARRY.ui.chip(made + ' pooled', { kind: made ? 'ok' : null }),
        had ? BARRY.ui.chip(had + ' already banked from the same inputs') : null,
        bad ? BARRY.ui.chip(bad + ' refused', { kind: 'warn' }) : null,
      ]),
      el('p', { class: 'hint quiet',
        text: 'Each pool is its own bank entry. Sort them in Panning — '
            + 'step 2 — from the Pan button on each row.' }),
    ]);
  }

  function onHide() {
    if (stageStop) { stageStop(); stageStop = null; }
  }

  return {
    paint, onHide,
    _state: () => q,
    _plan: () => plan,
    _landed: () => landed,
    _T: T,
    // For the harness: drop what was read so the next paint asks again.
    _reset: () => {
      onHide();
      recs = null; plan = null; planSig = null; landed = null; batch = null;
      vers = {}; merging = false; planning = false;
      q.gid = null; q.ds = null; q.ied = null; q.dsV = null; q.iedV = null;
      q.sel = null; q.mode = 'one'; q.win = 5; q.keep = 'incisor';
    },
  };
})();
