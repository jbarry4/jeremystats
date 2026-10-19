/* ==========================================================================
   setpicker.js -- the way into Spotter and Panning: which set, which run.

   Spotter's step page listed the curation SETS that existed and nothing
   else. A Doppler run banked on another machine, or banked here and never
   opened, was not on it -- 53 Doppler runs were banked and four could be
   reached -- and a set finished and banked looked exactly like one half
   done. Panning had the same list, and the same two faults. So both use
   this one:

     SEARCH          a mouse, session, project or name, over both groups.
     STARTED         every set of the kind: how far through it is, whether
                     its work is in the bank ("banked v3", "changed since
                     v3", "not banked yet"), whether it is on the bench --
                     and the three things to do with it: carry on, bank,
                     put it down.
     BANKED, NOT     every banked entry of the kind a set could be started
     STARTED         from and has not been (/api/curation/startable):
                     newest first, with who ran it and when.

   Sets and entries left behind by test harnesses are not shown, and the
   line under the list says how many were hidden rather than pretending
   they are not there -- the rule Eye's list follows.

   One renderer for both tools (constitution §6c). The tool says which
   kind, what its own runs are called, and how to open one.
   ========================================================================== */
'use strict';

BARRY.setPicker = (function () {
  const find = {};          // kind -> what is typed in its search box
  const showAll = {};       // kind -> also the entries that are not the tool's own

  const num = (n) => Number(n || 0).toLocaleString();
  const when = (at) => {
    if (!at) return '';
    const ms = Date.parse(String(at).replace(/([+-]\d\d)(\d\d)$/, '$1:$2'));
    if (!isFinite(ms)) return String(at).slice(0, 10);
    const d = (Date.now() - ms) / 1000;
    if (d < 90) return 'just now';
    if (d < 3600) return Math.round(d / 60) + ' min ago';
    if (d < 86400) return Math.round(d / 3600) + ' h ago';
    if (d < 86400 * 14) return Math.round(d / 86400) + ' d ago';
    return String(at).slice(0, 10);
  };
  const recOf = (r) => r.session_label
    || [r.project, r.mouse != null ? 'm' + r.mouse : null,
        r.session != null ? 's' + r.session : null].filter(Boolean).join(' ')
    || r.gid;
  const hay = (parts) => parts.filter((x) => x != null && x !== '')
    .join(' ').toLowerCase();

  /* What a set's bank chip says. */
  function bankChip(st) {
    const b = st.banked;
    const pr = st.progress || {};
    if (!b) {
      return BARRY.ui.chip(pr.specified ? 'not banked yet' : 'nothing to bank yet',
        { kind: pr.specified ? 'warn' : null,
          title: pr.specified
            ? 'Every decision is saved, but none of it is in the Event Bank '
              + 'yet. Bank the results to make it a version others can read.'
            : 'Nothing has been decided yet.' });
    }
    const v = BARRY.ui.versionLabel(b.version);
    if (b.changed) {
      return BARRY.ui.chip('changed since ' + v,
        { kind: 'warn',
          title: 'Banked as ' + v + ' ' + when(b.at)
               + (b.by ? ' by ' + b.by : '') + '. Decisions or merges made '
               + 'since are saved here but not in the bank yet.' });
    }
    return BARRY.ui.chip('banked ' + v,
      { kind: 'ok',
        title: 'Everything decided is in the bank as ' + v + ' of “'
             + (b.name || 'this set') + '”, ' + when(b.at)
             + (b.by ? ' by ' + b.by : '') + '.' });
  }

  /* Paint the picker into `box`. cfg:
       kind        'ied' | 'pooled'
       tool        the ToolKit tool this page belongs to ('spotter')
       mine        { id, label, test(pipeline) } -- the tool's own runs
       otherLabel  what everything else is called ('imported')
       enter(gid, entryId?)   open a set, or start one from an entry
       noun        'discharges' -- for the sentences
       empty       what to say when there is nothing at all */
  async function mount(box, cfg) {
    const alive = () => box.isConnected && BARRY.views.toolkit
      && BARRY.views.toolkit.tool() === cfg.tool;
    box.innerHTML = '';
    box.appendChild(el('div', { class: 'section-label', text: 'Which set' }));
    BARRY.skeleton.into(box, 'row', 3);
    let sets = [], fresh = [];
    try {
      const [a, b] = await Promise.all([
        api('/api/curation'),
        api('/api/curation/startable?kind=' + encodeURIComponent(cfg.kind)),
      ]);
      sets = (a.sets || []).filter((s) => s.kind === cfg.kind);
      fresh = b.entries || [];
    } catch (e) {
      if (!alive()) return;
      box.innerHTML = '';
      box.appendChild(el('div', { class: 'section-label', text: 'Which set' }));
      box.appendChild(el('div', { class: 'empty-state',
        text: 'Could not read the sets and the bank: ' + e.message }));
      return;
    }
    if (!alive()) return;

    const hidden = {
      test: sets.filter((s) => s.test).length + fresh.filter((e) => e.test).length,
      archived: sets.filter((s) => s.archived && !s.test).length,
    };
    sets = sets.filter((s) => !s.test && !s.archived);
    fresh = fresh.filter((e) => !e.test);
    const isMine = (e) => cfg.mine.test(e.pipeline || '');
    const nMine = fresh.filter(isMine).length;

    box.innerHTML = '';
    box.appendChild(el('div', { class: 'section-label', text: 'Which set' }));
    if (!sets.length && !fresh.length) {
      box.appendChild(el('div', { class: 'empty-state', text: cfg.empty }));
      return;
    }
    const search = BARRY.ui.searchField({
      placeholder: 'Type a mouse, session, project or name…',
      value: find[cfg.kind] || '',
      oninput: (e) => {
        find[cfg.kind] = (e && e.target) ? e.target.value : (e || '');
        paintLists();
      },
    });
    box.appendChild(el('div', { class: 'sp-search' }, [search]));
    const lists = el('div', { class: 'sp-lists' });
    box.appendChild(lists);
    if (hidden.test || hidden.archived) {
      box.appendChild(el('p', { class: 'hint quiet', text: [
        hidden.test ? hidden.test + ' left behind by test harnesses' : null,
        hidden.archived ? hidden.archived + ' archived' : null,
      ].filter(Boolean).join(' and ') + ' not shown.' }));
    }

    const refresh = () => mount(box, cfg);

    function paintLists() {
      lists.innerHTML = '';
      const want = (find[cfg.kind] || '').trim().toLowerCase();
      const hit = (h) => !want || want.split(/\s+/).every((w) => h.indexOf(w) >= 0);

      const shownSets = sets.filter((st) => hit(hay([
        st.name, st.session_label, (st.session || {}).label, st.gid,
        st.assignee, (st.session || {}).project,
      ])));
      const pool = showAll[cfg.kind] ? fresh : fresh.filter(isMine);
      const shownFresh = pool.filter((e) => hit(hay([
        e.name, recOf(e), e.project, 'm' + e.mouse, 's' + e.session, e.by,
        e.pipeline, e.gid,
      ])));

      lists.appendChild(el('div', { class: 'sp-group-hd' }, [
        el('strong', { text: 'Started' }),
        el('span', { class: 'hint quiet',
          text: want ? shownSets.length + ' of ' + sets.length : String(sets.length) }),
      ]));
      if (!shownSets.length) {
        lists.appendChild(el('p', { class: 'hint quiet sp-none',
          text: sets.length ? 'None of the started sets match.'
            : 'No set has been started yet. Start one from a run below.' }));
      }
      for (const st of shownSets) lists.appendChild(setRow(st));

      lists.appendChild(el('div', { class: 'sp-group-hd' }, [
        el('strong', { text: 'Banked, not started' }),
        el('span', { class: 'hint quiet',
          text: want ? shownFresh.length + ' of ' + pool.length : String(pool.length) }),
        el('span', { class: 'spacer' }),
        fresh.length > nMine ? BARRY.ui.seg([
          ['mine', cfg.mine.label + ' (' + nMine + ')', 'Only the runs this '
            + 'bundle made'],
          ['all', 'Everything (' + fresh.length + ')', 'Imports and older '
            + 'lists as well'],
        ], showAll[cfg.kind] ? 'all' : 'mine', (v) => {
          showAll[cfg.kind] = v === 'all';
          paintLists();
        }) : null,
      ].filter(Boolean)));
      if (!shownFresh.length) {
        lists.appendChild(el('p', { class: 'hint quiet sp-none',
          text: pool.length ? 'None of them match.'
            : 'Every banked run already has a set above.' }));
      }
      for (const e of shownFresh) lists.appendChild(freshRow(e));
    }

    function setRow(st) {
      const pr = st.progress || {};
      const done = pr.total > 0 && !pr.left;
      const recLabel = (st.session || {}).label || st.session_label || '';
      return el('div', { class: 'sp-row' + (done ? ' done' : '') }, [
        el('div', { class: 'sp-row-main' }, [
          el('strong', { text: st.name || recLabel || st.gid }),
          el('span', { class: 'sp-row-sub', text: [
            recLabel && recLabel !== st.name ? recLabel : null,
            (pr.specified || 0) + ' of ' + (pr.total || 0) + ' decided'
              + (done ? ' ✓' : ''),
          ].filter(Boolean).join(' · ') }),
        ]),
        el('div', { class: 'sp-row-chips' }, [
          bankChip(st),
          st.open ? BARRY.ui.chip('on the bench', { kind: 'ok' }) : null,
          st.assignee ? BARRY.ui.chip(st.assignee) : null,
        ].filter(Boolean)),
        el('div', { class: 'sp-row-acts' }, [
          el('button', { class: 'btn sm', text: done ? 'Look again…' : 'Carry on…',
            onclick: () => cfg.enter(st.gid) }),
          el('button', { class: 'btn ghost sm', text: 'Bank…',
            disabled: pr.specified ? null : 'disabled',
            title: pr.specified
              ? 'Write the decisions' + (cfg.kind === 'pooled' ? ' and merges' : '')
                + ' as a new version in the Event Bank. Not a save — '
                + 'everything is already saved.'
              : 'Nothing has been decided yet',
            onclick: async () => {
              if (!BARRY.curate || !BARRY.curate.bankAt) return;
              await BARRY.curate.bankAt({
                gid: st.gid, kind: st.kind, name: st.name,
                labels: st.labels || [],
                progress: { by_label: pr.by_label || {}, left: pr.left },
              });
              if (alive()) refresh();
            } }),
          st.open ? el('button', { class: 'btn ghost sm', text: 'Put it down',
            title: 'Off the bench. Nothing to save first — every decision '
                 + 'was written as it was made, and it is all still here.',
            onclick: async (ev) => {
              ev.target.disabled = true;
              try {
                await apiPost('/api/curation/' + encodeURIComponent(st.gid) + '/'
                              + encodeURIComponent(st.kind) + '/open',
                              { open: false });
                if (BARRY.views.toolkit && BARRY.views.toolkit.curationChanged) {
                  BARRY.views.toolkit.curationChanged();
                }
              } catch (e) {
                toast('Could not put it down: ' + e.message, 'err', 8000);
              }
              if (alive()) refresh();
            } }) : null,
        ].filter(Boolean)),
      ]);
    }

    function freshRow(e) {
      const mine = isMine(e);
      return el('div', { class: 'sp-row fresh' }, [
        el('div', { class: 'sp-row-main' }, [
          el('strong', { text: e.name || recOf(e) }),
          el('span', { class: 'sp-row-sub', text: [
            num(e.n) + ' ' + cfg.noun,
            BARRY.ui.versionLabel(e.tip),
            e.by ? 'by ' + e.by : null,
            when(e.at),
          ].filter(Boolean).join(' · ') }),
        ]),
        el('div', { class: 'sp-row-chips' }, [
          BARRY.ui.chip(mine ? cfg.mine.chip : cfg.otherLabel,
                        { flag: true, kind: mine ? 'ok' : null }),
          e.curated ? BARRY.ui.chip('decided before', { flag: true,
            title: 'This entry already carries decisions; a set started from '
                 + 'it keeps them.' }) : null,
        ].filter(Boolean)),
        el('div', { class: 'sp-row-acts' }, [
          el('button', { class: 'btn sm', text: 'Start…',
            title: e.set_name
              ? 'This recording already has a set, “' + e.set_name
                + '”. Starting from this run asks before replacing it.'
              : 'Make a set from this run and open it',
            onclick: () => cfg.enter(e.gid, e.id) }),
        ]),
      ]);
    }

    paintLists();
  }

  return { mount, _bankChip: bankChip };
})();
