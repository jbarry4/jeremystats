/* ==========================================================================
   eventbank.js -- the shared record of detected events.

   A detector's output normally ends up as an ets.mat beside the recording, on
   whichever drive it was run on. Six months later nobody can say which version
   of which script produced it. The bank is the answer: filed by project /
   mouse / session / type, and it will not take an entry that cannot say who
   added it, when, and what produced it.

   From here an entry goes back into Xplorefinder against a chosen recording.
   ========================================================================== */
'use strict';

BARRY.views.eventbank = (function () {
  let tree = [];
  let entries = [];
  let types = [];
  let meta = {};
  let query = '';
  let typeFilter = '';
  let projectFilter = '';
  let selected = null;        // the entry id shown in the detail pane

  /* Which kind of banked thing the view is showing.

     Layer sheets are the other output somebody cites, and they were only
     reachable from the ToolKit -- so "where is the recorded output for m11
     s10" had two answers depending on which output you meant. They are not
     bank entries, because a bank entry is a set of event TIMES and a layer
     sheet has none; they are the same view over a different list. */
  let kind = 'events';        // 'events' | 'layers'
  let sheets = [];            // layer sheets, when kind === 'layers'
  let sheetSel = null;        // the gid shown in the detail pane
  let sheetOne = null;        // that sheet, with its snapshots

  async function load() {
    // Nothing on screen yet means an empty panel for the length of the read.
    const bones = entries.length
      ? null : BARRY.skeleton.into($('#bankBody'), 'row', 7);
    /* Both lists, in parallel. The switch between them has to be instant --
       it is a switch, not a navigation -- and the sheets are a single small
       read. */
    const alsoSheets = api('/api/layers')
      .then((r) => { sheets = (r && r.sheets) || []; })
      .catch(() => { sheets = []; });
    try {
      const res = await api('/api/bank');
      tree = res.tree || [];
      entries = res.entries || [];
      types = res.types || [];
      meta = res;
    } catch (e) {
      toast('Could not read the event bank: ' + e.message, 'err');
      tree = []; entries = [];
    } finally {
      try { await alsoSheets; } catch (e) { /* the events still render */ }
      // In a finally, so a failed read does not leave the bones behind.
      if (bones) bones();
    }
    render();
  }

  const typeName = (id) => {
    const t = types.find((x) => x.id === id);
    return t ? t.name : (id || 'other');
  };

  function visible() {
    const q = query.trim().toLowerCase();
    return entries.filter((e) => {
      if (typeFilter && e.type !== typeFilter) return false;
      if (projectFilter && (e.project || 'Unfiled') !== projectFilter) return false;
      if (!q) return true;
      return [e.name, e.project, e.type, e.session_label, e.note,
              'm' + e.mouse, 's' + e.session,
              (e.source || {}).pipeline, (e.added || {}).by]
        .join(' ').toLowerCase().includes(q);
    });
  }

  /* ---------- rendering ---------- */
  function render() {
    const host = $('#bankBody');
    if (!host) return;
    host.innerHTML = '';

    const list = visible();
    const sub = $('#bankSub');
    if (sub && kind === 'layers') {
      const done = sheets.filter((x) => (x.progress || {}).labelled).length;
      sub.textContent = sheets.length
        ? sheets.length + ' layer sheet(s)  ·  ' + done + ' with labels  ·  '
          + sheets.reduce((n, x) => n + ((x.progress || {}).labelled || 0), 0)
          + ' channels labelled'
        : 'No layer sheets yet.';
    } else if (sub) {
      sub.textContent = entries.length
        ? list.length + ' of ' + entries.length + ' entr(ies)  ·  '
          + tree.length + ' project(s)  ·  '
          + entries.reduce((n, e) => n + (e.n || 0), 0) + ' events banked'
        : 'Nothing banked yet.';
    }

    host.appendChild(toolbar());

    if (kind === 'layers') { renderLayers(host); return; }

    if (!entries.length) {
      host.appendChild(el('div', { class: 'empty-state' }, [
        el('svg', { viewBox: '0 0 24 24',
          html: '<rect x="3" y="4" width="18" height="16" rx="2"/>'
              + '<path d="M3 9h18M8 4v16"/>' }),
        el('p', { text: 'The bank is empty. Open a recording in Xplorefinder, '
                      + 'load or detect some events, and use "Bank…" to '
                      + 'file them here — with who added them and what '
                      + 'produced them.' }),
      ]));
      return;
    }

    host.appendChild(el('div', { class: 'bank-split' }, [
      bankTree(list),
      detail(),
    ]));
  }

  function toolbar() {
    const bar = el('div', { class: 'res-toolbar' });

    /* Which kind of banked output. A switch rather than two views: the
       question "what has been recorded for this session" should have one
       place to ask it, even though the two answers have different shapes. */
    bar.appendChild(el('span', { class: 'ctl-seg bank-kind' }, [
      el('button', {
        class: 'mini' + (kind === 'events' ? ' on' : ''),
        text: 'Events', title: 'Banked event sets — times and labels',
        onclick: () => { kind = 'events'; render(); },
      }),
      el('button', {
        class: 'mini' + (kind === 'layers' ? ' on' : ''),
        text: 'Layers',
        title: 'StrataScope sheets — which layer each channel sits in',
        onclick: () => { kind = 'layers'; render(); },
      }),
    ]));

    bar.appendChild(el('div', { class: 'search-wrap inline' }, [
      el('svg', { viewBox: '0 0 20 20', class: 'search-icon',
        html: '<circle cx="9" cy="9" r="6"/><path d="m14 14 4 4"/>' }),
      el('input', {
        type: 'search', value: query,
        placeholder: 'Search project, mouse, session, type, pipeline, who…',
        oninput: debounceInput(
          (e) => { query = e.target.value; keepFocus(render); }, 140),
      }),
    ]));

    const projects = Array.from(new Set(entries.map((e) => e.project || 'Unfiled')));
    if (kind === 'events' && projects.length > 1) {
      bar.appendChild(el('select', {
        title: 'Filter by project',
        onchange: (e) => { projectFilter = e.target.value; render(); },
      }, [el('option', { value: '', text: 'All projects' })].concat(
        projects.sort().map((p) => el('option', {
          value: p, text: p, selected: projectFilter === p ? 'selected' : null,
        })))));
    }

    const used = Array.from(new Set(entries.map((e) => e.type)));
    if (kind === 'events' && used.length > 1) {
      bar.appendChild(el('select', {
        title: 'Filter by event type',
        onchange: (e) => { typeFilter = e.target.value; render(); },
      }, [el('option', { value: '', text: 'All types' })].concat(
        used.map((t) => el('option', {
          value: t, text: typeName(t),
          selected: typeFilter === t ? 'selected' : null,
        })))));
    }

    bar.appendChild(el('div', { style: 'flex:1' }));
    bar.appendChild(el('span', { class: 'hint', text: meta.root || '' }));
    return bar;
  }

  /* ==================================================================
     Layer sheets
     ================================================================== */
  function renderLayers(host) {
    const q = query.trim().toLowerCase();
    const list = sheets.filter(function (x) {
      if (!q) return true;
      const sess = x.session || {};
      return [x.session_label, x.gid, sess.project,
              'm' + sess.mouse, 's' + sess.session]
        .join(' ').toLowerCase().indexOf(q) >= 0;
    });

    if (!sheets.length) {
      host.appendChild(el('div', { class: 'empty-state' }, [
        el('svg', { viewBox: '0 0 24 24',
          html: '<rect x="3" y="4" width="18" height="16" rx="2"/>'
              + '<path d="M3 9h18M3 14h18"/>' }),
        el('p', { text: 'No layer sheets yet. Open a recording in the '
                      + 'ToolKit under StrataScope and label which layer '
                      + 'each channel sits in — the sheet is filed here.' }),
      ]));
      return;
    }

    host.appendChild(el('div', { class: 'bank-split' }, [
      layerList(list),
      layerDetail(),
    ]));
  }

  function layerList(list) {
    const box = el('div', { class: 'bank-tree' });
    /* Grouped the way the events side groups: project, then mouse. The
       sheets arrive sorted by how much is labelled, which is a useful order
       for seeing what is left and the wrong one for finding a given
       recording. */
    const byProject = new Map();
    list.forEach(function (x) {
      const proj = (x.session || {}).project || 'Unfiled';
      if (!byProject.has(proj)) byProject.set(proj, []);
      byProject.get(proj).push(x);
    });
    Array.from(byProject.keys()).sort().forEach(function (proj) {
      const rows = byProject.get(proj).slice().sort(function (a, b) {
        const am = (a.session || {}).mouse || 0;
        const bm = (b.session || {}).mouse || 0;
        if (am !== bm) return am - bm;
        return ((a.session || {}).session || 0) - ((b.session || {}).session || 0);
      });
      box.appendChild(el('div', { class: 'grp-head' }, [
        el('span', { text: proj }),
        el('span', { class: 'count', text: rows.length + ' sheet(s)' }),
      ]));
      rows.forEach(function (x) { box.appendChild(sheetRow(x)); });
    });
    return box;
  }

  function sheetRow(x) {
    const pr = x.progress || {};
    const done = pr.total && pr.left === 0;
    const nv = x.n_versions || (x.versions || []).length;
    return el('div', {
      class: 'bank-row' + (sheetSel === x.gid ? ' on' : ''),
      // So the selection can be moved without rebuilding the list, which
      // is what used to scroll it back to the top.
      'data-gid': x.gid,
      onclick: function () { selectSheet(x.gid); },
    }, [
      el('div', { class: 'bank-row-top' }, [
        el('strong', { text: x.session_label || x.gid }),
        el('span', { class: 'hk-chip', text: 'layers' }),
        el('div', { style: 'flex:1' }),
        el('span', { class: 'bank-n',
          text: (pr.labelled || 0) + ' / ' + (pr.total || 0)
              + (done ? '  ✓' : '') }),
      ]),
      el('div', { class: 'bank-row-sub' }, [
        /* How many passes there have been. This is the whole reason the
           sheets are here rather than only in the ToolKit: a sheet with a
           history is a thing that can be cited. */
        el('span', { text: nv
          ? nv + ' version' + (nv === 1 ? '' : 's')
          : 'no history yet' }),
        el('span', { text: '  ·  ' }),
        el('span', { text: ((x.updated || {}).by) || 'unknown' }),
      ]),
      el('div', { class: 'cur-prog small' }, [
        el('i', { style: 'width:' + (pr.percent || 0) + '%' }),
      ]),
    ]);
  }

  /* Move the selection without rebuilding the list.

     Calling `render()` here rebuilt the whole split, so the scroller was a
     brand new element and the browser started it at the top -- with
     sixty-seven sheets, clicking the one you had scrolled down to threw you
     back to the beginning. And it happened twice, once before the fetch and
     once after it.

     The events side has had this fix for a while and there is a note on
     `selectEntry` explaining it; this is the same thing for the sheets. */
  function paintSheetSelection(gid) {
    for (const row of document.querySelectorAll('#bankBody .bank-row')) {
      if (row.hasAttribute('data-gid')) row.classList.remove('on');
    }
    /* By its own gid rather than by position: the rows are grouped by
       project and then by mouse, so the nth row is not the nth sheet. */
    const row = document.querySelector(
      '#bankBody .bank-row[data-gid="' + String(gid).replace(/"/g, '') + '"]');
    if (row) row.classList.add('on');
  }

  function repaintSheet() {
    const box = document.querySelector('.bank-detail');
    if (!box || !box.parentNode) { render(); return false; }
    box.parentNode.replaceChild(layerDetail(), box);
    return true;
  }

  async function selectSheet(gid) {
    sheetSel = gid;
    sheetOne = null;
    paintSheetSelection(gid);
    if (!repaintSheet()) return;      // no split on screen yet; render did it
    try {
      /* The single-sheet read, because it is the only one carrying the
         snapshots -- the list leaves them out, and without them the history
         can say how many versions there are but not what any of them held. */
      const got = await api('/api/layers/' + encodeURIComponent(gid));
      sheetOne = got.sheet || null;
    } catch (e) {
      toast('Could not read that sheet: ' + e.message, 'err');
    }
    /* Still the sheet somebody is looking at? A second click while the
       first read was in flight would otherwise paint the older answer over
       the newer one. */
    if (sheetSel === gid) repaintSheet();
  }

  function layerDetail() {
    const box = el('div', { class: 'bank-detail' });
    if (!sheetSel) {
      box.appendChild(el('div', { class: 'hint',
        text: 'Pick a sheet to see its history and export it.' }));
      return box;
    }
    const x = sheets.filter(function (s2) { return s2.gid === sheetSel; })[0] || {};
    const pr = x.progress || {};

    box.appendChild(el('div', { class: 'mh' }, [
      el('h3', { text: x.session_label || sheetSel }),
      el('span', { class: 'sub',
                   text: (pr.labelled || 0) + ' of ' + (pr.total || 0)
                       + ' channels' }),
      el('div', { class: 'spacer' }),
      el('button', {
        class: 'btn ghost sm', text: 'Open in StrataScope',
        title: 'Label or correct this sheet',
        onclick: function () { BARRY.strata.enter(sheetSel); },
      }),
    ]));

    /* What it says now, as a run per layer rather than a row per channel:
       sixty-four rows reading "CA1" is the same fact eight times over, and
       where the boundaries fall is the thing worth seeing. */
    box.appendChild(el('div', { class: 'section-label', text: 'As it stands' }));
    box.appendChild(runsOf(x));

    box.appendChild(el('div', { class: 'sec-head' }, [
      el('div', { class: 'section-label', text: 'History' }),
      el('div', { style: 'flex:1' }),
      /* The same act as banking a curated set: a pass is finished, and what
         it said should still be readable after somebody starts the next. */
      el('button', {
        class: 'btn ghost sm', text: 'Snapshot this pass…',
        title: 'Freeze the sheet as it stands as the next version',
        onclick: function () { snapshotSheet(x); },
      }),
    ]));

    const vs = (sheetOne && sheetOne.versions) || x.versions || [];
    if (!vs.length) {
      box.appendChild(el('div', { class: 'hint',
        text: sheetOne
          ? 'No versions yet. Snapshot the pass to make one.'
          : 'Reading…' }));
      return box;
    }
    vs.slice().reverse().forEach(function (v) {
      const n = v.n != null ? v.n : Object.keys(v.snap || {}).length;
      box.appendChild(el('div', { class: 'ver-row' }, [
        el('div', { class: 'ver-top' }, [
          el('span', { class: 'ver-n', text: 'v' + v.v }),
          el('span', { class: 'ver-when',
            text: (v.at || '').replace('T', ' ').slice(0, 16) }),
          el('span', { class: 'ver-who', text: v.by || 'unknown' }),
          el('span', { class: 'ver-count', text: n + ' labelled' }),
          el('span', { class: 'ver-ops' }, [
            el('button', {
              class: 'linkish', text: 'CSV',
              title: 'Export this version as a CSV, as it was at this pass',
              onclick: function () {
                BARRY.download(
                  '/api/layers/' + encodeURIComponent(sheetSel)
                    + '/version-export', { v: v.v },
                  'layers-' + String(x.session_label || sheetSel)
                    .replace(/[^A-Za-z0-9.-]+/g, '_') + '-v' + v.v + '.csv');
              },
            }),
          ]),
        ]),
        v.note ? el('div', { class: 'ver-note', text: v.note }) : null,
      ].filter(Boolean)));
    });
    return box;
  }

  /* Contiguous stretches of the same layer, which is how a probe actually
     passes through them. */
  function runsOf(x) {
    const runs = [];
    const labels = x.labels || {};
    const names = {};
    (x.regions || []).forEach(function (r) { names[r.id] = r; });
    (x.channels || []).forEach(function (ch) {
      const id = labels[String(ch)] || null;
      const last = runs[runs.length - 1];
      if (last && last.id === id) last.to = ch;
      else runs.push({ id: id, from: ch, to: ch });
    });
    const box = el('div', { class: 'layer-runs' });
    runs.forEach(function (r) {
      const reg = names[r.id];
      box.appendChild(el('div', {
        class: 'layer-run' + (reg ? '' : ' none'),
        style: reg ? '--cat:' + reg.color : '',
      }, [
        el('span', { class: 'layer-run-ch',
          text: r.from === r.to ? String(r.from) : r.from + '–' + r.to }),
        el('span', { class: 'layer-run-name',
          text: reg ? reg.name : 'unlabelled',
          title: (reg && reg.note) ? reg.note : '' }),
        el('span', { class: 'layer-run-n', text: (r.to - r.from + 1) + ' ch' }),
      ]));
    });
    return box;
  }

  /* Freezing a pass. Its own modal rather than a generic prompt, matching
     editVersion above -- the note is the thing that makes a version worth
     having, and a one-line box says so better than a browser prompt. */
  function snapshotSheet(x) {
    const pr = x.progress || {};
    const wrap = el('div', { class: 'modal ver-edit' });
    const note = el('textarea', {
      class: 'ver-note-input', rows: '3',
      placeholder: 'e.g. checked against the CSD, moved the GCL up two',
    });
    wrap.appendChild(el('div', { class: 'modal-head' }, [
      el('h2', { text: 'Snapshot this layer sheet' }),
      el('p', { class: 'sub', text: x.session_label || x.gid }),
    ]));
    wrap.appendChild(el('p', { class: 'confirm-msg',
      text: 'It freezes the ' + (pr.labelled || 0) + ' label'
          + ((pr.labelled === 1) ? '' : 's')
          + ' as they stand as the next version, so a later correction does '
          + 'not overwrite what this pass said. Nothing on the sheet '
          + 'changes.' }));
    wrap.appendChild(el('div', { class: 'section-label', text: 'What this pass was' }));
    wrap.appendChild(note);
    wrap.appendChild(el('div', { class: 'modal-foot' }, [
      el('div', { style: 'flex:1' }),
      el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
      el('button', {
        class: 'btn', text: 'Snapshot',
        onclick: async function () {
          closeModal();
          try {
            const res = await apiPost('/api/layers/'
              + encodeURIComponent(x.gid) + '/snapshot',
              { note: (note.value || '').trim() || null });
            sheetOne = res.sheet || sheetOne;
            // The list carries the version count, so re-read it too.
            const got = await api('/api/layers');
            sheets = (got && got.sheets) || sheets;
            render();
            const made = ((sheetOne || {}).versions || []).slice(-1)[0] || {};
            toast('Snapshotted as v' + made.v, 'ok');
          } catch (e) {
            toast('Could not snapshot: ' + e.message, 'err');
          }
        },
      }),
    ]));
    showModal(wrap, { replace: true });
  }

  /* ---------- left: project / mouse / session ---------- */
  function bankTree(list) {
    const keep = new Set(list.map((e) => e.id));
    const box = el('div', { class: 'bank-tree' });

    for (const g of tree) {
      const mice = g.mice
        .map((m) => Object.assign({}, m, {
          sessions: m.sessions
            .map((s) => Object.assign({}, s, {
              entries: s.entries.filter((e) => keep.has(e.id)),
            }))
            .filter((s) => s.entries.length),
        }))
        .filter((m) => m.sessions.length);
      if (!mice.length) continue;

      const n = mice.reduce((a, m) => a + m.sessions.reduce(
        (b, s) => b + s.entries.length, 0), 0);
      box.appendChild(el('div', { class: 'grp-head' }, [
        el('span', { text: g.project }),
        el('span', { class: 'count', text: n + ' entr(ies)' }),
      ]));

      for (const m of mice) {
        box.appendChild(el('div', { class: 'bank-mouse' }, [
          el('strong', { text: m.mouse }),
        ]));
        for (const s of m.sessions) {
          box.appendChild(el('div', { class: 'bank-sess' }, [
            el('span', { class: 'sid', text: s.session }),
            el('span', { class: 'slab', text: s.label || '', title: s.label || '' }),
          ]));
          for (const e of s.entries) {
            box.appendChild(entryRow(e));
          }
        }
      }
    }
    return box;
  }

  function entryRow(e) {
    const added = e.added || {};
    const src = e.source || {};
    return el('div', {
      class: 'bank-row' + (selected === e.id ? ' active' : ''),
      // So a selection can find its own row without rebuilding the list.
      'data-id': e.id,
      title: 'Banked by ' + added.by + ' on ' + (added.at || '').slice(0, 16),
      onclick: () => selectEntry(e.id),
    }, [
      el('span', { class: 'bank-type', text: typeName(e.type) }),
      el('span', { class: 'bank-name', text: e.name }),
      el('span', { class: 'bank-n', text: e.n + '' }),
      el('span', { class: 'bank-src', text: baseName(src.pipeline || ''),
                   title: src.pipeline || '' }),
    ]);
  }

  /* ---------- right: one entry in full ---------- */
  /* How the decisions have moved, version by version.

     A re-curation is mostly a decision changing category -- fifty flags
     resolved into spikes, a handful of spikes turning out to be noise -- and
     that movement is the difference between two versions' counts. Shown as
     the difference rather than only the totals, because "-6 flag, +6 spike"
     is the sentence somebody is looking for and two columns of totals make
     you do the subtraction yourself. */
  function versionHistory(box, e) {
    const vs = (e.versions || []).slice();
    if (!vs.length) return;
    /* Which version is open, if any. Held outside so it survives the
       repaint that opening one causes. */
    if (openVersion && !vs.some((v) => v.v === openVersion)) {
      openVersion = null;
    }
    const names = e.label_names || {};
    const nameOf = (k) => names[k] || (k === 'unspecified' ? 'undecided' : k);

    const hidden = vs.filter((v) => v.archived);
    const shown = showArchived ? vs : vs.filter((v) => !v.archived);

    box.appendChild(el('div', { class: 'section-label ver-head' }, [
      el('span', { text: 'History  \u00b7  ' + shown.length + ' version'
                       + (shown.length === 1 ? '' : 's') }),
      hidden.length
        ? el('button', {
            class: 'linkish',
            text: showArchived
              ? 'hide ' + hidden.length + ' archived'
              : hidden.length + ' archived \u2014 show',
            onclick: () => { showArchived = !showArchived; repaint(); },
          })
        : null,
    ].filter(Boolean)));

    /* The lineage: every version at a glance, and a way into any of them.
       Reading a history means moving around in it. */
    const strip = el('div', { class: 'ver-strip' });
    shown.forEach((v) => {
      strip.appendChild(el('button', {
        class: 'ver-pip' + (openVersion === v.v ? ' on' : '')
             + (v.v === vs.length ? ' last' : ''),
        title: 'v' + v.v + '  ' + (v.by || '') + '  '
             + (v.note || 'no note'),
        text: 'v' + v.v,
        onclick: () => {
          openVersion = openVersion === v.v ? null : v.v;
          const host = box.parentNode;
          // Repaint just the entry, so the list on the left does not
          // scroll back to the top.
          const fresh = detail();
          if (host) host.replaceChild(fresh, box);
        },
      }));
    });
    box.appendChild(strip);

    const list = el('div', { class: 'ver-list' });
    for (let i = shown.length - 1; i >= 0; i--) {
      const v = shown[i], was = i > 0 ? shown[i - 1] : null;
      const counts = v.by_label || {};
      const wasCounts = (was && was.by_label) || {};
      const keys = Array.from(new Set(
        Object.keys(counts).concat(Object.keys(wasCounts))));
      keys.sort((a, b) => (counts[b] || 0) - (counts[a] || 0));

      const shifts = [];
      for (const k of keys) {
        const d = (counts[k] || 0) - (wasCounts[k] || 0);
        if (was && d !== 0) {
          shifts.push(el('span', {
            class: 'ver-shift ' + (d > 0 ? 'up' : 'down'),
            text: (d > 0 ? '+' : '\u2212') + Math.abs(d) + ' ' + nameOf(k),
          }));
        }
      }
      const dn = was ? (v.n || 0) - (was.n || 0) : 0;
      if (was && dn !== 0) {
        shifts.push(el('span', {
          class: 'ver-shift ' + (dn > 0 ? 'up' : 'down'),
          text: (dn > 0 ? '+' : '\u2212') + Math.abs(dn) + ' in total',
        }));
      }

      list.appendChild(el('div', {
        class: 'ver-row' + (i === shown.length - 1 ? ' latest' : '')
             + (v.archived ? ' archived' : ''),
      }, [
        el('div', { class: 'ver-top' }, [
          el('span', { class: 'ver-n', text: 'v' + v.v }),
          el('span', { class: 'ver-when',
                       text: (v.at || '').replace('T', ' ').slice(0, 16) }),
          el('span', { class: 'ver-who', text: v.by || 'unknown' }),
          el('span', { class: 'ver-count', text: (v.n || 0) + ' events' }),
          i === shown.length - 1 && !v.archived
            ? el('span', { class: 'pill sm', text: 'current' }) : null,
          v.archived ? el('span', { class: 'pill sm', text: 'archived' })
                     : null,
          el('span', { class: 'ver-ops' }, [
            /* Per version, not per entry.

               The entry already exported "the events as they stand now". A
               version is what they were at that pass, which is the thing a
               result cites: 416 candidates as somebody left them at v1 is a
               different set of numbers from 416 candidates today, and a
               figure made from one should not be described by the other. */
            el('button', {
              class: 'linkish', text: 'CSV',
              title: 'Export this version’s ' + (v.n || 0)
                   + ' events as a CSV, as they were at this pass',
              onclick: () => BARRY.download(
                '/api/bank/version-export', { id: e.id, v: v.v },
                'event-bank-'
                  + String(e.name || e.id).replace(/[^A-Za-z0-9.-]+/g, '_')
                  + '-v' + v.v + '.csv'),
            }),
            el('button', { class: 'linkish', text: 'Edit',
                           title: 'Change this version\u2019s note or give '
                                + 'it a name',
                           onclick: () => editVersion(e, v) }),
            el('button', {
              class: 'linkish',
              text: v.archived ? 'Unarchive' : 'Archive',
              title: v.archived
                ? 'Show it in the history again'
                : 'Fold it away. Nothing is lost and it can come back.',
              onclick: () => versionOp(e, v,
                                       v.archived ? 'unarchive' : 'archive'),
            }),
            el('button', { class: 'linkish danger', text: 'Delete',
                           title: 'Remove this version from the history',
                           onclick: () => deleteVersion(e, v) }),
          ]),
        ].filter(Boolean)),
        v.title ? el('div', { class: 'ver-title', text: v.title }) : null,
        v.note
          ? el('div', { class: 'ver-note', text: v.note })
          : el('div', { class: 'ver-note none', text: 'no note' }),
        (v.edits || []).length
          ? el('div', { class: 'ver-edited',
              text: 'note edited '
                  + (v.edits[v.edits.length - 1].at || '')
                      .replace('T', ' ').slice(0, 16)
                  + ' by ' + (v.edits[v.edits.length - 1].by || 'someone') })
          : null,
        el('div', { class: 'ver-mix' }, keys.filter((k) => counts[k]).map(
          (k) => el('span', { class: 'ver-chip',
                              text: nameOf(k) + ' ' + counts[k] }))),
        /* Which decisions changed, and to what. The totals cannot show
           this: two calls going one way and two coming back leaves every
           count identical while four decisions moved. */
        (was && v.moves && Object.keys(v.moves).length)
          ? el('div', { class: 'ver-shifts' },
               [el('span', { class: 'ver-since',
                             text: 'since v' + was.v + ':' })].concat(
                 Object.keys(v.moves)
                   .sort((a, b) => v.moves[b] - v.moves[a])
                   .map((k) => el('span', { class: 'ver-move',
                                            text: k + '  ×' + v.moves[k] }))
               ).concat(v.gained ? [el('span', { class: 'ver-shift up',
                          text: '+' + v.gained + ' new' })] : [])
                .concat(v.lost ? [el('span', { class: 'ver-shift down',
                          text: '−' + v.lost + ' gone' })] : []))
          : null,
        (was && shifts.length)
          ? el('div', { class: 'ver-shifts' },
               [el('span', { class: 'ver-since', text: 'totals:' })]
                 .concat(shifts))
          : null,
        (was && !shifts.length && !(v.moves
                                    && Object.keys(v.moves).length))
          ? el('div', { class: 'ver-shifts' }, [
              el('span', { class: 'ver-since none',
                           text: 'nothing moved since v' + was.v })])
          : null,
        /* Opening a version: what it held, and how it differs from
           whichever other version you pick -- not only the one before it,
           because "what has changed since the first pass" is the question
           three versions later. */
        openVersion === v.v ? versionDetail(e, vs, v) : null,
        (v.confirmed || []).length
          ? el('div', { class: 'ver-conf',
              text: 'banked again with no change '
                  + v.confirmed.length + ' time'
                  + (v.confirmed.length === 1 ? '' : 's')
                  + ' \u2014 last by ' + (v.confirmed[
                      v.confirmed.length - 1].by || 'someone') })
          : null,
      ].filter(Boolean)));
    }
    box.appendChild(list);
  }

  /* The version being looked at, if the reader has opened one. */
  let openVersion = null;
  /* Archived versions fold away rather than disappearing: a pass somebody
     would rather not look at is not the same as one that never happened. */
  let showArchived = false;

  /* Repaint just the entry, so the list on the left keeps its place. */
  /* Pick an entry without rebuilding the list.

     The row's click used to call render(), which empties #bankBody and
     builds it again -- including `.bank-tree`, the element that scrolls. So
     clicking anything below the fold jumped the list back to the top, and
     the entry you had just chosen was off screen. Only two things actually
     change when a selection moves: which row is marked, and what the detail
     pane shows. */
  function selectEntry(id) {
    selected = id;
    for (const row of document.querySelectorAll('#bankBody .bank-row')) {
      row.classList.remove('active');
    }
    const box = document.querySelector('.bank-detail');
    if (!box || !box.parentNode) { render(); return; }
    /* By its own id. Not by position in the visible list -- the rows are
       grouped project / mouse / session, so the nth row is not the nth
       entry and marking by index highlighted the wrong one. */
    const row = document.querySelector(
      '#bankBody .bank-row[data-id="' + String(id).replace(/"/g, '') + '"]');
    if (row) row.classList.add('active');
    box.parentNode.replaceChild(detail(), box);
  }

  function repaint() {
    const box = document.querySelector('.bank-detail');
    if (!box || !box.parentNode) { render(); return; }
    box.parentNode.replaceChild(detail(), box);
  }

  async function versionOp(e, v, action, body) {
    try {
      const res = await apiPost(
        '/api/bank/' + encodeURIComponent(e.id) + '/version/' + v.v,
        Object.assign({ action: action }, body || {}));
      /* In place rather than refetching everything, so the panel does not
         jump -- but the route answers without the snapshots, and dropping
         them would break the comparison until the next reload. */
      const snaps = {};
      (e.versions || []).forEach((x) => {
        if (x.snap) snaps[x.v] = x.snap;
      });
      e.versions = (res.versions || []).map(
        (x) => (snaps[x.v] ? Object.assign({}, x, { snap: snaps[x.v] }) : x));
      repaint();
      return res;
    } catch (err) { toast(err.message, 'err', 9000); return null; }
  }

  async function deleteVersion(e, v) {
    const isCurrent = v.v === Math.max.apply(
      null, (e.versions || []).map((x) => x.v || 0));
    const go = await BARRY.confirm(
      'Delete version ' + v.v + '?',
      'It goes from the history for good. The entry keeps its '
      + (e.n || 0) + ' events exactly as they are'
      + (isCurrent
          ? ' \u2014 and since this is the version that describes them, '
            + 'nothing left in the history will explain what the entry '
            + 'currently holds.'
          : '.')
      + ' Archive it instead if you only want it out of the way.',
      'Delete v' + v.v, true);
    if (!go) return;
    const res = await versionOp(e, v, 'delete');
    if (res) toast('Version ' + v.v + ' deleted.', 'ok');
  }

  function editVersion(e, v) {
    const wrap = el('div', { class: 'modal ver-edit' });
    wrap.appendChild(el('div', { class: 'modal-head' }, [
      el('h2', { text: 'Version ' + v.v }),
      el('p', { class: 'sub',
                text: (v.at || '').replace('T', ' ').slice(0, 16)
                    + '  \u00b7  ' + (v.by || 'unknown')
                    + '  \u00b7  ' + (v.n || 0) + ' events' }),
    ]));
    const title = el('input', {
      type: 'text', value: v.title || '',
      placeholder: 'A name for this pass (optional)',
    });
    const note = el('textarea', {
      class: 'ver-note-input', rows: '4', value: v.note || '',
      placeholder: 'What changed in this pass?',
    });
    wrap.appendChild(el('div', { class: 'section-label', text: 'Name' }));
    wrap.appendChild(title);
    wrap.appendChild(el('div', { class: 'section-label', text: 'Note' }));
    wrap.appendChild(note);
    wrap.appendChild(el('p', { class: 'hint',
      text: 'The counts are not editable \u2014 they are what was banked. '
          + 'An edited note records that it was edited.' }));
    wrap.appendChild(el('div', { class: 'modal-foot' }, [
      el('div', { style: 'flex:1' }),
      el('button', { class: 'btn ghost', text: 'Cancel',
                     onclick: closeModal }),
      el('button', {
        class: 'btn', text: 'Save',
        onclick: async () => {
          closeModal();
          const res = await versionOp(e, v, 'edit',
                                      { note: note.value, title: title.value });
          if (res) {
            toast(res.changed.length
              ? 'Version ' + v.v + ' updated.'
              : 'Nothing changed.', 'ok');
          }
        },
      }),
    ]));
    showModal(wrap);
    setTimeout(() => { try { note.focus(); } catch (err) {} }, 30);
  }

  async function restoreVersion(e, v) {
    const names = e.label_names || {};
    const mix = Object.keys(v.by_label || {})
      .sort((a, b) => v.by_label[b] - v.by_label[a])
      .map((k) => (names[k] || k) + ' ' + v.by_label[k]).join(', ');
    const go = await BARRY.confirm(
      'Put version ' + v.v + ' back?',
      'The live curation set becomes what it was at version ' + v.v
      + ': ' + mix + '. Nothing is deleted \u2014 whatever is there now '
      + 'stays in the history, and coming back to it is the same one '
      + 'click.',
      'Put v' + v.v + ' back', false);
    if (!go) return;
    try {
      const res = await apiPost(
        '/api/curation/' + encodeURIComponent(e.gid) + '/'
        + encodeURIComponent(e.type) + '/restore',
        { entry: e.id, version: v.v });
      toast(res.changed
        ? 'Put version ' + v.v + ' back: ' + res.changed
          + ' decision(s) changed, ' + res.unchanged + ' already matched.'
        : 'The set already matches version ' + v.v + '.', 'ok', 8000);
      load();
    } catch (err) { toast(err.message, 'err', 9000); }
  }

  /* One version, opened: its contents and a comparison with another. */
  function versionDetail(e, vs, v) {
    const names = e.label_names || {};
    const nameOf = (k) => names[k] || (k === 'unspecified' ? 'undecided' : k);
    const host = el('div', { class: 'ver-open' });

    if (!v.snap) {
      host.appendChild(el('p', { class: 'hint',
        text: 'This version is old enough that the candidate-by-candidate '
            + 'snapshot has been dropped \u2014 its counts and its note are '
            + 'kept, but it can no longer be compared candidate by '
            + 'candidate.' }));
      return host;
    }

    const others = vs.filter((o) => o.v !== v.v && o.snap);
    if (!others.length) {
      host.appendChild(el('p', { class: 'hint',
        text: 'Nothing else to compare it against yet.' }));
      return host;
    }
    /* Default to the version before, which is the usual question. */
    let against = others.filter((o) => o.v < v.v).pop() || others[0];

    const rows = el('div', { class: 'ver-diff' });
    const paint = () => {
      rows.innerHTML = '';
      const was = new Map((against.snap || []).map((p) => [
        Math.round(p[0] * 1e4), p[1]]));
      const out = [];
      for (const p of v.snap) {
        const key = Math.round(p[0] * 1e4);
        if (!was.has(key)) {
          out.push({ t: p[0], from: null, to: p[1] });
          continue;
        }
        const before = was.get(key);
        was.delete(key);
        if (before !== p[1]) out.push({ t: p[0], from: before, to: p[1] });
      }
      for (const [key, lab] of was) {
        out.push({ t: key / 1e4, from: lab, to: null });
      }
      out.sort((a, b) => a.t - b.t);

      rows.appendChild(el('div', { class: 'hint',
        text: out.length
          ? out.length + ' candidate' + (out.length === 1 ? '' : 's')
            + ' differ between v' + against.v + ' and v' + v.v
          : 'Nothing differs between v' + against.v + ' and v' + v.v + '.' }));
      const clock = (t) => {
        const m = Math.floor(t / 60), s = t - m * 60;
        return m + ':' + (s < 10 ? '0' : '') + s.toFixed(3);
      };
      for (const d of out.slice(0, 400)) {
        rows.appendChild(el('div', { class: 'vd-row' }, [
          el('span', { class: 'vd-t', text: clock(d.t) }),
          el('span', { class: 'vd-from',
                       text: d.from === null ? 'not in v' + against.v
                                             : nameOf(d.from) }),
          el('span', { class: 'vd-arrow', text: '\u2192' }),
          el('span', { class: 'vd-to',
                       text: d.to === null ? 'gone' : nameOf(d.to) }),
        ]));
      }
      if (out.length > 400) {
        rows.appendChild(el('div', { class: 'hint',
          text: 'and ' + (out.length - 400) + ' more. Export the CSV for '
              + 'the full list.' }));
      }
    };

    host.appendChild(el('div', { class: 'ver-open-bar' }, [
      el('strong', { text: 'v' + v.v }),
      /* A history you can read but not act on is half a history. */
      el('button', {
        class: 'btn ghost sm', text: 'Put this version back',
        title: 'Write these labels onto the live curation set. Nothing in '
             + 'the history is removed \u2014 the version you are on now '
             + 'stays, and going back to it is the same one click.',
        onclick: () => restoreVersion(e, v),
      }),
      el('span', { class: 'hint', text: 'compared with' }),
      el('select', {
        onchange: (ev) => {
          against = others.find((o) => String(o.v) === ev.target.value)
                 || against;
          paint();
        },
      }, others.map((o) => el('option', {
        value: String(o.v),
        text: 'v' + o.v + '  ' + (o.by || '') + '  '
            + (o.at || '').replace('T', ' ').slice(0, 16),
        selected: o.v === against.v ? 'selected' : null,
      }))),
    ]));
    host.appendChild(rows);
    paint();
    return host;
  }

  function detail() {
    const box = el('div', { class: 'bank-detail' });
    const e = entries.find((x) => x.id === selected);
    if (!e) {
      box.appendChild(el('div', { class: 'empty-state' }, [
        el('svg', { viewBox: '0 0 24 24',
          html: '<path d="M9 12h6m-6 4h6m-6-8h6M5 3h14a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/>' }),
        el('p', { text: 'Pick an entry to see where it came from, and to load '
                      + 'it onto a recording.' }),
      ]));
      return box;
    }

    const added = e.added || {};
    const src = e.source || {};

    box.appendChild(el('div', { class: 'detail-head' }, [
      el('div', {}, [
        el('h2', { text: e.name }),
        el('p', { class: 'detail-path',
                  text: (e.project || 'Unfiled') + '  ·  m' + e.mouse
                      + '  ·  s' + e.session
                      + (e.session_label ? '  ·  ' + e.session_label : '') }),
        el('div', { class: 'detail-tags' }, [
          el('span', { class: 'tag lang', text: typeName(e.type) }),
          el('span', { class: 'tag opt', text: e.n + ' events' }),
          e.note ? el('span', { class: 'tag opt', text: e.note }) : null,
        ]),
      ]),
      el('div', { class: 'head-actions' }, [
        el('button', { class: 'btn sm', text: 'Load onto a recording…',
                       onclick: () => importDialog(e) }),
        el('button', { class: 'btn ghost sm', text: 'Edit…',
                       onclick: () => editDialog(e) }),
      ]),
    ]));

    /* Provenance is the whole point of the bank, so it goes first and in
       full rather than behind a disclosure triangle. */
    box.appendChild(el('div', { class: 'section-label', text: 'Where this came from' }));
    const kv = el('dl', { class: 'kv' });
    const add = (k, v) => {
      if (v === null || v === undefined || v === '') return;
      kv.appendChild(el('dt', { text: k }));
      kv.appendChild(el('dd', { text: typeof v === 'object'
        ? JSON.stringify(v) : String(v) }));
    };
    add('Produced by', src.pipeline);
    add('Source file', src.file);
    add('Detector', src.detector);
    add('Run id', src.run_id);
    if (src.parameters && Object.keys(src.parameters).length) {
      add('Parameters', src.parameters);
    }
    add('Added by', added.by);
    add('Added at', (added.at || '').replace('T', ' '));
    add('On machine', added.machine);
    /* Not "v3 of 2": numbers are never reused, so once a version has been
       deleted the highest number and the count are different things and
       saying "of" makes one of them look wrong. */
    add('Version', e.version
        ? ('v' + e.version + '  ·  ' + (e.versions || []).length
           + ' in the history')
        : null);
    add('Times are', e.units);
    add('Session path', e.session_path);
    add('Entry id', e.id);
    box.appendChild(kv);
    versionHistory(box, e);

    if ((e.history || []).length) {
      box.appendChild(el('div', { class: 'section-label', text: 'Edited' }));
      box.appendChild(el('div', { class: 'source-box' }, [
        el('pre', { text: e.history.map((h) =>
          (h.at || '').replace('T', ' ') + '  ' + (h.by || '')
          + '  ' + (h.changed || []).join(', ')).join('\n') }),
      ]));
    }

    box.appendChild(el('div', { class: 'sec-head' }, [
      el('div', { class: 'section-label', text: 'Events' }),
      el('div', { class: 'spacer' }),
      el('button', { class: 'btn ghost sm', text: 'Export CSV',
        onclick: () => BARRY.download('/api/bank/export', { ids: [e.id] },
                                      'event-bank-' + e.id + '.csv') }),
      el('button', { class: 'btn ghost sm danger', text: 'Delete entry',
        onclick: () => removeEntry(e) }),
    ]));
    box.appendChild(el('div', { class: 'bank-events', id: 'bankEvents' },
                       [loader('Loading events')]));
    loadEvents(e.id);
    return box;
  }

  async function loadEvents(id) {
    let full;
    try { full = await api('/api/bank/' + encodeURIComponent(id)); }
    catch (err) { return; }
    /* The listing leaves the per-version snapshots out because they are
       large; this is the fetch that has them, so the history gets them
       here rather than making a second request for the same record. */
    const whole = (full && full.entry) || full;
    const row = entries.find((x) => x.id === id);
    if (row && whole && whole.versions) row.versions = whole.versions;
    const host = $('#bankEvents');
    if (!host || selected !== id) return;
    const evs = (full.entry || {}).events || [];
    host.innerHTML = '';
    const table = el('table', { class: 'preview-table' }, [
      el('thead', {}, [el('tr', {}, ['#', 'start', 'end', 'channel', 'amplitude']
        .map((h) => el('th', { text: h })))]),
      el('tbody', {}, evs.slice(0, 300).map((ev, i) => el('tr', {}, [
        el('td', { text: String(i + 1) }),
        el('td', { text: fmtTime(ev.start) }),
        el('td', { text: ev.end != null ? fmtTime(ev.end) : '' }),
        el('td', { text: ev.channel != null ? 'CSC' + ev.channel : '' }),
        el('td', { text: ev.amplitude != null
          ? Math.round(ev.amplitude) + ' uV' : '' }),
      ]))),
    ]);
    host.appendChild(el('div', { class: 'preview-wrap' }, [table]));
    if (evs.length > 300) {
      host.appendChild(el('div', { class: 'hint',
        text: 'Showing the first 300 of ' + evs.length + '. Export the CSV '
            + 'for all of them.' }));
    }
  }

  /* ======================================================================
     Loading an entry onto a recording

     Banked times are seconds from the start of that recording, so they only
     mean anything against the right one. This offers the sessions already
     open, flags whether each is actually the recording the entry was banked
     against, and can open the banked path directly if it is reachable.
     ====================================================================== */
  function importDialog(e) {
    const xf = BARRY.views.xplore.state;
    const open = xf.order.map((id) => xf.sessions[id]).filter(Boolean);

    const matchOf = (sess) => {
      const id = sess.identity || {};
      /* The permanent id first, the way the server matches. Checking
         session_key first meant a recording whose header start had
         moved by a second -- the exact case the gid exists to solve
         -- was reported as merely "same session", and the dialog then
         refused to preselect the one recording it was certain of. */
      if (e.gid && id.gid && id.gid === e.gid) return 'exact';
      if (e.session_key && id.key === e.session_key) return 'exact';
      if (e.mouse != null && id.mouse === e.mouse
          && e.session != null && id.session === e.session) return 'same session';
      if (e.mouse != null && id.mouse === e.mouse) return 'same mouse only';
      return 'different recording';
    };
    const rank = { 'exact': 0, 'same session': 1, 'same mouse only': 2,
                   'different recording': 3 };
    open.sort((a, b) => rank[matchOf(a)] - rank[matchOf(b)]);

    /* Pick the recording this belongs to, not whichever happens to be first.

       The dialog used to preselect open[0] no matter what it was, so with
       three unrelated recordings open it arrived pre-armed to drop dentate
       spikes from m11 s10 onto m1 s2 -- one click from silently wrong data.
       Nothing is chosen unless it actually matches by mouse and session. */
    const good = (m) => m === 'exact' || m === 'same session';
    const first = open.find((o) => good(matchOf(o)));
    let chosen = first ? first.id : null;

    /* Its own class, not 'bm-list tall'.

       That one lays a row out as a seven-column grid -- dot, time, name,
       detail, kind, kind, close -- because it is the marks table. These rows
       have three children, so the name was landing in a 74px column and
       being cut to "PTEN m1 s2 ...", while the four unused columns sat
       there as a long empty bar. Nothing needed truncating; the row was
       being measured against the wrong shape. */
    const list = el('div', { class: 'bm-list tall bank-targets' });
    const paint = () => {
      list.innerHTML = '';
      if (!open.length) {
        list.appendChild(el('div', { class: 'hint',
          text: 'No recordings are open. Open one in Xplorefinder first, or '
              + 'use the button below to open the one this was banked '
              + 'against.' }));
        return;
      }
      for (const sess of open) {
        const m = matchOf(sess);
        list.appendChild(el('label', {
          class: 'bm-row' + (chosen === sess.id ? ' on' : ''),
        }, [
          el('input', {
            type: 'radio', name: 'bankTarget',
            checked: chosen === sess.id ? 'checked' : null,
            onchange: () => { chosen = sess.id; paint(); },
          }),
          el('span', { class: 'mk-name',
                       text: sess.identity.label || sess.info.name }),
          el('span', { class: 'flagchip' + (m === 'exact' ? ' good'
                       : (m === 'different recording' ? ' bad' : '')), text: m }),
        ]));
      }
      const warn = document.getElementById('bankWarn');
      if (warn) {
        const sess = open.find((o) => o.id === chosen);
        const m = sess ? matchOf(sess) : null;
        if (!chosen) {
          warn.textContent = open.length
            ? 'None of the open recordings is the one these were banked '
              + 'against. Open that one, or pick a recording below on '
              + 'purpose — the times are seconds from the start of the '
              + 'banked recording and will land somewhere arbitrary on any '
              + 'other.'
            : '';
          warn.className = 'confirm-sub warn';
        } else if (!good(m)) {
          warn.textContent = 'That is ' + m + '. The times are seconds from '
            + 'the start of the banked recording, so on this one they will '
            + 'land somewhere arbitrary.';
          warn.className = 'confirm-sub warn';
        } else {
          warn.textContent = '';
          warn.className = 'confirm-sub';
        }
      }
    };
    paint();

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Load "' + e.name + '" onto a recording' }),
        el('span', { class: 'sub', text: e.n + ' ' + typeName(e.type)
                                       + ' event(s)' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        /* Which recording this belongs to, said by name.

           This used to lead with "these times are seconds from the start
           of X", which is true and is not the question being asked. What
           you need to know is which of the open recordings is the right
           one, and the answer is a name and a mouse, not a clock. */
        el('p', { class: 'confirm-msg',
          text: 'Banked against ' + (e.session_label
              || 'an unnamed recording')
              + (e.mouse != null
                  ? '  ·  mouse ' + e.mouse
                    + (e.session != null ? ', session ' + e.session : '')
                  : '') + '.' }),
        list,
        // Only when it needs saying, and only about the thing chosen.
        el('p', { class: 'confirm-sub', id: 'bankWarn' }),
      ]),
      el('div', { class: 'mf' }, [
        e.session_path ? el('button', {
          class: 'btn ghost sm',
          text: 'Open the banked recording',
          title: e.session_path,
          onclick: async () => {
            closeModal();
            setView('xplore');
            const sess = await BARRY.views.xplore.open(e.session_path);
            if (sess) applyTo(e, sess);
          },
        }) : null,
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        el('button', {
          class: 'btn', text: 'Load onto it',
          disabled: chosen ? null : 'disabled',
          onclick: async () => {
            const sess = xf.sessions[chosen];
            if (!sess) return;
            closeModal();
            setView('xplore');
            applyTo(e, sess);
          },
        }),
      ]),
    ]));
    // paint() ran before the modal was in the document, so the
    // warning line it writes into did not exist yet.
    paint();
  }

  async function applyTo(entry, sess) {
    let full;
    try { full = await api('/api/bank/' + encodeURIComponent(entry.id)); }
    catch (err) { toast(err.message, 'err'); return; }
    const evs = ((full.entry || {}).events || []).map((ev) => Object.assign(
      {}, ev, { label: entry.name || typeName(entry.type) }));
    if (!evs.length) { toast('That entry has no events.', 'err'); return; }

    BARRY.views.xplore.addBankedEvents(sess, evs, {
      name: entry.name, type: entry.type, entry_id: entry.id,
      pipeline: (entry.source || {}).pipeline,
      added_by: (entry.added || {}).by,
    });
    toast('Loaded ' + evs.length + ' event(s) from the bank onto '
          + (sess.identity.label || sess.info.name), 'ok', 6000);
  }

  /* ---------- editing and removing ---------- */
  function editDialog(e) {
    const f = {};
    const field = (key, label, value, hint) => {
      const input = el('input', { type: 'text', value: value == null ? '' : String(value) });
      f[key] = input;
      return el('div', { class: 'field' }, [
        el('label', { text: label }), input,
        hint ? el('span', { class: 'hint', text: hint }) : null,
      ]);
    };
    const typeSel = el('select', {}, types.map((t) => el('option', {
      value: t.id, text: t.name + (t.note ? '  — ' + t.note : ''),
      selected: e.type === t.id ? 'selected' : null,
    })));

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Edit entry' }),
        el('span', { class: 'sub', text: 'provenance cannot be edited' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        field('name', 'Name', e.name),
        field('project', 'Project', e.project),
        field('mouse', 'Mouse', e.mouse),
        field('session', 'Session', e.session),
        el('div', { class: 'field' }, [el('label', { text: 'Type' }), typeSel]),
        field('note', 'Note', e.note),
        el('p', { class: 'hint',
          text: 'Who added it, when, and what produced it are fixed — '
              + 'that is the part worth trusting.' }),
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel', onclick: closeModal }),
        el('button', {
          class: 'btn', text: 'Save',
          onclick: async () => {
            const num = (v) => (v === '' ? null : (isFinite(+v) ? +v : v));
            try {
              await apiPost('/api/bank/' + e.id + '/update', {
                name: f.name.value.trim() || e.name,
                project: f.project.value.trim() || 'Unfiled',
                mouse: num(f.mouse.value.trim()),
                session: num(f.session.value.trim()),
                type: typeSel.value,
                type_name: typeName(typeSel.value),
                note: f.note.value.trim(),
              });
              closeModal();
              await load();
              BARRY.refreshSync();
            } catch (err) { toast(err.message, 'err'); }
          },
        }),
      ]),
    ]));
  }

  async function removeEntry(e) {
    const ok = await BARRY.confirm(
      'Delete "' + e.name + '"?',
      'Removes ' + e.n + ' banked event(s) and the record of where they came '
      + 'from. The recording itself is untouched.',
      'Delete it', true);
    if (!ok) return;
    try {
      await apiPost('/api/bank/' + e.id + '/delete');
      selected = null;
      await load();
      BARRY.refreshSync();
      toast('Removed from the bank', 'ok');
    } catch (err) { toast(err.message, 'err'); }
  }

  function init() {
    $('#bankRefresh').addEventListener('click', load);
    $('#bankExport').addEventListener('click', () =>
      BARRY.download('/api/bank/export', {}, 'event-bank.csv'));
    $('#bankReveal').addEventListener('click', () => {
      if (meta.root) apiPost('/api/reveal', { path: meta.root }).catch(() => {});
    });
  }

  return {
    init,
    onShow: load,
    reload: load,
    /* For web/_dev/banklayers.html: which sheet the detail pane is showing.
       The harness needs it to ask the server for the same version the panel
       is offering, rather than assuming which sheet it landed on. */
    _sheetSel: () => sheetSel,
    types: () => types,
    /* Used by Xplorefinder's "Bank…" dialog so it offers the same list. */
    typeList: () => types,
    /* Open the "load onto a recording" chooser for a made-up entry. Only
       web/_dev/bankshot.html uses this, to photograph the dialog with
       recordings open that deliberately do not match. */
    debugImportDialog: (e) => importDialog(e),
  };
})();
