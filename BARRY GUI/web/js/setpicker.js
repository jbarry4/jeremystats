/* ==========================================================================
   setpicker.js -- two pieces of the workbench Spotter and Panning share
   with Checkup (toolkit.js, `WB`).

   Spotter's step page was a list of the sets that existed and nothing else
   (reported 2026-10-19): a Doppler run banked on another machine, or banked
   here and never opened, could not be reached -- 53 runs banked, four
   reachable -- and a set finished and banked looked exactly like one half
   done. It is Checkup's workbench now, bench and shelf and all; these are
   the two things that workbench did not have:

     bankChip(set)   whether a set's work is in the Event Bank: "banked v3",
                     "changed since v3", "not banked yet". The server works
                     it out (app.py `_cur_banked`); this only says it.
     fresh(host, entries, cfg)
                     every banked run of the kind that no set has been
                     started from (/api/curation/startable), with a search,
                     newest first, each with Start.
   ========================================================================== */
'use strict';

BARRY.setPicker = (function () {
  const find = {};          // kind -> what is typed in the search box
  const showAll = {};       // kind -> imports as well as the tool's own runs

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
        { kind: pr.specified ? 'warn' : null, extra: 'sp-bank',
          title: pr.specified
            ? 'Every decision is saved, but none of it is in the Event Bank '
              + 'yet. Bank the results to make it a version others can read.'
            : 'Nothing has been decided yet.' });
    }
    const v = BARRY.ui.versionLabel(b.version);
    if (b.changed) {
      return BARRY.ui.chip('changed since ' + v,
        { kind: 'warn', extra: 'sp-bank',
          title: 'Banked as ' + v + ' ' + when(b.at)
               + (b.by ? ' by ' + b.by : '') + '. Decisions or merges made '
               + 'since are saved here but not in the bank yet.' });
    }
    return BARRY.ui.chip('banked ' + v,
      { kind: 'ok', extra: 'sp-bank',
        title: 'Everything decided is in the bank as ' + v + ' of “'
             + (b.name || 'this set') + '”, ' + when(b.at)
             + (b.by ? ' by ' + b.by : '') + '.' });
  }

  /* The banked runs no set has been started from. cfg:
       kind        'ied' | 'pooled'
       mine        { label, chip, test(pipeline) } -- the bundle's own runs
       otherLabel  what everything else is called
       noun        'discharges'
       enter(gid, entryId)  start a set from it and open it */
  function fresh(host, entries, cfg) {
    host.innerHTML = '';
    const all = (entries || []).filter((e) => !e.test);
    const isMine = (e) => cfg.mine.test(e.pipeline || '');
    const nMine = all.filter(isMine).length;
    const list = el('div', { class: 'sp-lists' });

    const paint = () => {
      list.innerHTML = '';
      const want = (find[cfg.kind] || '').trim().toLowerCase();
      const words = want ? want.split(/\s+/) : [];
      const pool = showAll[cfg.kind] ? all : all.filter(isMine);
      const rows = pool.filter((e) => {
        const h = hay([e.name, recOf(e), e.project, 'm' + e.mouse,
                       's' + e.session, e.by, e.pipeline, e.gid]);
        return words.every((w) => h.indexOf(w) >= 0);
      });
      /* Archived runs sink (2026-10-20): counted and listed apart, at the
         bottom behind one toggle -- kept, and not offered first. The
         server sends them last, flagged `archived`. */
      const isGone = (e) => !!e.archived;
      const livePool = pool.filter((e) => !isGone(e));
      const [live, gone] = BARRY.ui.splitArchived(rows, isGone);
      const count = host.querySelector('.sp-count');
      if (count) {
        count.textContent = live.length === livePool.length
          ? livePool.length + ' run' + (livePool.length === 1 ? '' : 's')
          : live.length + ' of ' + livePool.length;
      }
      if (!live.length) {
        list.appendChild(el('p', { class: 'hint quiet sp-none',
          text: livePool.length ? 'None of them match.'
            : 'Every banked run already has a set.' }));
      }
      for (const e of live) list.appendChild(row(e));
      const tail = BARRY.ui.archivedTail({
        key: 'sp-' + cfg.kind, items: gone, noun: ['run', 'runs'],
        render: (xs) => xs.map(row), onToggle: () => paint(),
      });
      if (tail) list.appendChild(tail);
    };

    const row = (e) => {
      const mine = isMine(e);
      return el('div', { class: 'sp-row fresh' + (e.archived ? ' is-archived' : '') }, [
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
          /* Shown, and not startable, with the reason on it (§6e): an
             archived run is kept for the record, not worked from. */
          e.archived ? el('button', { class: 'btn ghost sm', text: 'Archived',
            disabled: 'disabled',
            title: 'Archived in the Event Bank, so it is not started from. '
                 + 'Unarchive one of its versions there to work from it.' }) :
          el('button', { class: 'btn sm', text: 'Start…',
            title: e.set_name
              ? 'This recording already has a set, “' + e.set_name
                + '”. Starting from this run asks before replacing it.'
              : 'Make a set from this run and open it',
            onclick: (ev) => {
              const b = ev.currentTarget;
              b.disabled = true; b.textContent = 'Opening…';
              Promise.resolve(cfg.enter(e.gid, e.id)).finally(() => {
                if (b.isConnected) { b.disabled = false; b.textContent = 'Start…'; }
              });
            } }),
        ]),
      ]);
    };

    host.appendChild(el('div', { class: 'cur-filter sp-search' }, [
      BARRY.ui.searchField({
        placeholder: 'Type a mouse, session, project or name…',
        value: find[cfg.kind] || '',
        oninput: (ev) => {
          find[cfg.kind] = (ev && ev.target) ? ev.target.value : (ev || '');
          paint();
        },
      }),
    ]));
    host.appendChild(el('div', { class: 'res-toolbar cur-chips' }, [
      all.length > nMine ? BARRY.ui.seg([
        ['mine', cfg.mine.label + ' (' + nMine + ')',
         'Only the runs this bundle made'],
        ['all', 'Everything (' + all.length + ')',
         'Imports and older lists as well'],
      ], showAll[cfg.kind] ? 'all' : 'mine', (v) => {
        showAll[cfg.kind] = v === 'all';
        fresh(host, entries, cfg);
      }) : null,
      el('div', { class: 'spacer', style: 'flex:1' }),
      el('span', { class: 'hint sp-count' }),
    ].filter(Boolean)));
    host.appendChild(list);
    paint();
    return all.length - all.filter(isMine).length;
  }

  return { bankChip, fresh, _bankChip: bankChip };
})();
