/* chickenscratch.js -- Chicken Scratch (BETA), web/chickenscratch.html.

   One page per mouse: what every source says about it, the story a reader
   pieced together (when one has been written), and the places the sources
   disagree. Every attribute, disagreement and fact can be marked right,
   wrong or unsure, or given a note; those go to POST /api/chickenscratch/note
   and are what the next pass is built on. Nothing here edits a source.

   A standalone page: it does not load the app's core.js, so it has its own
   small fetch and element helpers. */
(function () {
  'use strict';

  const S = { mice: [], key: null, filter: 'focus', q: '', cur: null, open: {} };
  const TYPE_WORDS = {
    tail_snip: 'Tail snip', injection: 'Injection', behavior: 'Behavior',
    surgery_headplate: 'Headplate / surgery', probe_implant: 'Probe', surgery_other: 'Other procedure',
    recording_session: 'Recording', drug: 'Drug', seizure: 'Seizure', health: 'Health',
    death: 'End', perfusion: 'Perfusion', histology: 'Histology', brain_bank: 'Brain bank',
    calendar: 'Calendar', shipment: 'Shipment', exclusion: 'Exclusion', census: 'Cage card seen',
    note: 'Note', analysis: 'Analysis', genotype: 'Genotype', sex: 'Sex', dob: 'Date of birth',
    cage: 'Cage', role: 'Role', alive: 'Alive', parents: 'Parents', identity: 'Identity',
    group: 'Group',
  };
  const ATTR_ORDER = ['cohort', 'sex', 'dob', 'YH', 'SST', 'PV', 'cage', 'parents', 'role', 'alive'];
  const ATTR_WORDS = { cohort: 'Cohort', sex: 'Sex', dob: 'Born', cage: 'Cage', parents: 'Parents',
                       role: 'Role', alive: 'Alive' };

  function h(tag, attrs, kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'text') e.textContent = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const c of [].concat(kids || [])) if (c != null) e.append(c);
    return e;
  }
  async function get(url) {
    const r = await fetch(url);
    const j = await r.json();
    if (!r.ok || j.ok === false) throw new Error(j.error || r.statusText);
    return j;
  }
  async function post(url, body) {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                 body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok || j.ok === false) throw new Error(j.error || r.statusText);
    return j;
  }
  const typeWord = (t) => TYPE_WORDS[t] || t;
  const label = (key) => key.replace(/^KCNT1:/, 'KCNT1 ').replace(/^PTEN:/, 'PTEN ');
  const when = (t) => new Date(t * 1000).toLocaleString();

  /* ---- the list ---------------------------------------------------------- */
  const FILTERS = [
    ['focus', 'Focus (DS sheet)'], ['KCNT1', 'KCNT1'], ['PTEN', 'PTEN'],
    ['conflicts', 'Has disagreements'], ['noted', 'Has my notes'], ['all', 'All'],
  ];

  function chips() {
    const box = document.getElementById('csChips');
    box.innerHTML = '';
    for (const [id, words] of FILTERS) {
      box.append(h('button', { class: 'cs-chip', 'aria-pressed': String(S.filter === id),
                               text: words, onclick: () => { S.filter = id; chips(); list(); } }));
    }
  }

  function shown() {
    const q = S.q.trim().toLowerCase();
    return S.mice.filter((m) => {
      if (S.filter === 'focus' && !m.focus) return false;
      if ((S.filter === 'KCNT1' || S.filter === 'PTEN') && m.project !== S.filter) return false;
      if (S.filter === 'conflicts' && !m.n_conflicts) return false;
      if (S.filter === 'noted' && !m.n_notes) return false;
      if (!q) return true;
      return [m.key, m.cohort, m.genes, m.sex, m.dob].join(' ').toLowerCase().includes(q)
        || m.key.toLowerCase().replace(/^\w+:/, '').replace(/^m/, '') === q.replace(/^m/, '');
    });
  }

  function list() {
    const nav = document.getElementById('csList');
    nav.innerHTML = '';
    let group = null;
    const ms = shown();
    if (!ms.length) nav.append(h('div', { class: 'cs-empty', text: 'No mouse matches.' }));
    for (const m of ms) {
      const g = (m.focus ? 'Focus · ' : '') + m.project + (m.key.includes('other animal') ? ' · other animals' : '');
      if (g !== group) { nav.append(h('div', { class: 'cs-group', text: g })); group = g; }
      const meta = [m.sex, m.genes, m.dob && ('born ' + m.dob), m.cohort,
                    m.last && (typeWord(m.last.type) + ' ' + m.last.date)].filter(Boolean).join(' · ');
      nav.append(h('div', {
        class: 'cs-mouse', role: 'button', tabindex: '0', 'aria-selected': String(m.key === S.key),
        onclick: () => open(m.key),
        onkeydown: (e) => { if (e.key === 'Enter') open(m.key); },
      }, [
        h('span', { class: 'id', text: label(m.key) }),
        h('span', { class: 'cs-badges' }, [
          m.story ? h('span', { class: 'cs-badge ok', text: 'story', title: 'A reader has written this mouse up' }) : null,
          m.n_conflicts ? h('span', { class: 'cs-badge warn', text: m.n_conflicts + ' ≠',
                                      title: m.n_conflicts + ' places the sources disagree' }) : null,
          m.n_notes ? h('span', { class: 'cs-badge note', text: m.n_notes + ' ✎', title: 'Notes left' }) : null,
        ]),
        h('span', { class: 'meta', text: meta || (m.n_facts + ' facts') }),
      ]));
    }
  }

  /* ---- one mouse ------------------------------------------------------- */
  async function open(key) {
    S.key = key;
    S.open = {};
    try { history.replaceState(null, '', '#' + encodeURIComponent(key)); } catch (e) { /* file: */ }
    list();
    const pane = document.getElementById('csPane');
    pane.innerHTML = '';
    pane.append(h('div', { class: 'cs-empty', text: 'Gathering ' + label(key) + '…' }));
    try {
      S.cur = await get('/api/chickenscratch/mouse?key=' + encodeURIComponent(key));
    } catch (e) {
      pane.innerHTML = '';
      pane.append(h('div', { class: 'cs-empty', text: e.message }));
      return;
    }
    paint();
  }

  function acts(target) {
    // target: {attr?, value?, fact?, conflict?}; returns the verdict buttons and a note box.
    const box = h('div', {});
    const say = async (verdict, text) => {
      try {
        await post('/api/chickenscratch/note', Object.assign({ key: S.key, verdict, text: text || '' }, target));
        const m = S.mice.find((x) => x.key === S.key);
        if (m) m.n_notes += 1;
        S.cur = await get('/api/chickenscratch/mouse?key=' + encodeURIComponent(S.key));
        paint();
        list();
      } catch (e) { alert(e.message); }
    };
    const ta = h('textarea', { placeholder: 'What is actually true, or what happened? (goes to the next pass)' });
    const noteRow = h('div', { class: 'cs-note-box', hidden: true }, [
      ta, h('button', { class: 'btn sm', text: 'Save note', onclick: () => {
        if (ta.value.trim()) say('note', ta.value.trim());
      } })]);
    box.append(h('span', { class: 'cs-acts' }, [
      h('button', { text: '✓ right', title: 'This is correct', onclick: () => say('confirm') }),
      h('button', { text: '✗ wrong', title: 'This is wrong', onclick: () => { noteRow.hidden = false; ta.focus(); say('wrong'); } }),
      h('button', { text: '? unsure', onclick: () => say('unsure') }),
      h('button', { text: '✎ note', onclick: () => { noteRow.hidden = !noteRow.hidden; if (!noteRow.hidden) ta.focus(); } }),
    ]), noteRow);
    return box;
  }

  function verdicts(match) {
    const ns = (S.cur.notes || []).filter(match);
    if (!ns.length) return null;
    return h('div', { class: 'cs-notes' }, ns.map((n) => h('div', { class: 'n' }, [
      h('strong', { text: { confirm: '✓ right', wrong: '✗ wrong', unsure: '? unsure', note: '✎' }[n.verdict] + ' ' }),
      n.text ? h('span', { text: n.text + ' ' }) : null,
      h('small', { text: '— ' + (n.by || 'someone') + ', ' + (n.at || '').slice(0, 16).replace('T', ' ') }),
    ])));
  }

  function paint() {
    const pane = document.getElementById('csPane');
    const { dossier: d, facts, story } = S.cur;
    const byId = Object.fromEntries(facts.map((f) => [f.id, f]));
    pane.innerHTML = '';
    pane.append(h('h2', { text: label(d.key) }));
    const sub = [d.focus ? 'On the Dentate Spike sheet' + (d.focus_sessions && d.focus_sessions.filter(Boolean).length
      ? ' (sessions ' + d.focus_sessions.filter(Boolean).join(', ') + ')' : ' (no session listed)') : 'Not on the Dentate Spike sheet',
      d.n_facts + ' facts from ' + d.sources.length + ' sources'];
    if (d.raw_ids && d.raw_ids.length) sub.push('written as ' + d.raw_ids.slice(0, 8).join(', '));
    pane.append(h('div', { class: 'cs-sub', text: sub.join(' · ') }));

    /* the story */
    pane.append(h('h3', { text: 'The story so far' }));
    if (story) pane.append(storyBox(story));
    else pane.append(h('div', { class: 'cs-story cs-sub', text:
      'Not written up yet. Below is everything the sources say, folded by date; the written story comes in the next pass, built on your marks and notes.' }));

    /* identity */
    pane.append(h('h3', { text: 'Who this mouse is' }));
    const attrs = d.attrs || {};
    const grid = h('div', { class: 'cs-attrs' });
    const names = ATTR_ORDER.filter((a) => attrs[a]).concat(Object.keys(attrs).filter((a) => !ATTR_ORDER.includes(a)));
    if (!names.length) grid.append(h('span', { class: 'cs-sub', text: 'No source states sex, birth date or genotype.' }));
    for (const a of names) {
      const v = attrs[a];
      const vals = v.values || [];
      const cell = h('div', { class: 'v' });
      if (vals.length > 1 && !v.agreed) cell.append(h('span', { class: 'cs-dispute', text: 'disputed' }));
      for (const x of vals.slice(0, 6)) {
        cell.append(h('span', { class: 'cs-val', title: x.sources.join('\n') }, [
          h('span', { text: x.value }), h('small', { text: '×' + x.sources.length }),
        ]));
      }
      cell.append(acts({ attr: a, value: v.agreed || (vals[0] && vals[0].value) }));
      const said = verdicts((n) => n.attr === a);
      if (said) cell.append(said);
      grid.append(h('div', { class: 'k', text: ATTR_WORDS[a] || a }), cell);
    }
    pane.append(grid);

    /* disagreements */
    pane.append(h('h3', { text: 'Where the sources disagree (' + d.conflicts.length + ')' }));
    if (!d.conflicts.length) pane.append(h('div', { class: 'cs-sub', text: 'None found by the cross-check.' }));
    d.conflicts.forEach((c, i) => {
      const cid = c.kind + ':' + c.what;
      const box = h('div', { class: 'cs-conf' }, [h('div', { class: 't', text: c.text })]);
      box.append(acts({ conflict: cid }));
      const said = verdicts((n) => n.conflict === cid);
      if (said) box.append(said);
      pane.append(box);
    });

    /* the timeline */
    pane.append(h('h3', { text: 'Timeline (' + d.timeline.length + ' dated rows)' }));
    const hideCensus = h('label', { class: 'cs-sub' }, [
      h('input', { type: 'checkbox', checked: S.open.census ? true : null,
                   onchange: (e) => { S.open.census = e.target.checked; paint(); } }),
      ' show every cage-card census and calendar entry',
    ]);
    pane.append(hideCensus);
    for (const r of d.timeline) {
      if (!S.open.census && (r.type === 'census' || r.type === 'calendar')) continue;
      const rid = 'r' + r.date + r.type + r.what + (r.session || '');
      const row = h('div', { class: 'cs-row' }, [
        h('span', { class: 'd', text: r.date }),
        h('span', { class: 'ty', text: typeWord(r.type) }),
        h('span', {}, [
          h('a', { href: '#', text: (r.type === 'recording_session' ? 'session ' + (r.session || '?') :
                                      r.what && r.what !== r.type ? r.what : typeWord(r.type))
                                    + (S.open[rid] ? ' ▾' : ' ▸'),
                   onclick: (e) => { e.preventDefault(); S.open[rid] = !S.open[rid]; paint(); } }),
        ]),
        h('span', { class: 'srcs', text: r.sources.length + ' source' + (r.sources.length > 1 ? 's' : '')
                                         + ': ' + r.sources.join(' · ') }),
      ]);
      if (S.open[rid]) row.append(h('div', { class: 'cs-facts' }, r.facts.map((id) => byId[id]).filter(Boolean).map(factBox)));
      pane.append(row);
    }

    /* everything without a date */
    const undated = facts.filter((f) => !f.date && !['sex', 'dob', 'genotype', 'cage', 'role', 'alive'].includes(f.type));
    pane.append(h('h3', { text: 'Notes and facts without a date (' + undated.length + ')' }));
    const showU = !!S.open.undated;
    pane.append(h('a', { href: '#', text: showU ? 'Hide' : 'Show them', onclick: (e) => {
      e.preventDefault(); S.open.undated = !showU; paint(); } }));
    if (showU) pane.append(h('div', {}, undated.map(factBox)));

    /* the mouse's own note */
    pane.append(h('h3', { text: 'Notes on ' + label(d.key) }));
    const all = verdicts((n) => !n.attr && !n.conflict && !n.fact);
    if (all) pane.append(all);
    const ta = h('textarea', { placeholder: 'Anything about this mouse the sources get wrong or never wrote down.' });
    pane.append(h('div', { class: 'cs-note-box' }, [ta, h('button', { class: 'btn sm', text: 'Save note', onclick: async () => {
      if (!ta.value.trim()) return;
      try {
        await post('/api/chickenscratch/note', { key: S.key, verdict: 'note', text: ta.value.trim() });
        S.cur = await get('/api/chickenscratch/mouse?key=' + encodeURIComponent(S.key));
        const m = S.mice.find((x) => x.key === S.key); if (m) m.n_notes += 1;
        paint(); list();
      } catch (e) { alert(e.message); }
    } })]));

    pane.append(h('h3', { text: 'Sources' }));
    pane.append(h('div', { class: 'cs-sub' }, d.sources.map(([s, n]) => h('div', { text: n + ' × ' + s }))));
  }

  function factBox(f) {
    const box = h('div', { class: 'cs-fact' }, [
      h('div', {}, [
        h('strong', { text: typeWord(f.type) }),
        f.date ? h('span', { text: ' · ' + f.date + (f.time ? ' ' + f.time : '') }) : null,
        f.date_raw && f.date_raw !== f.date ? h('span', { class: 'cs-sub', text: ' (written "' + f.date_raw + '")' }) : null,
        f.session ? h('span', { text: ' · session ' + f.session }) : null,
        f.who ? h('span', { text: ' · ' + f.who }) : null,
        h('span', { class: 'cs-sub', text: ' · ' + (f.conf || '') }),
      ]),
      f.value ? h('div', { text: f.value }) : null,
      f.detail ? h('div', { class: 'det', text: f.detail }) : null,
      f.flags && f.flags.length ? h('div', { class: 'flags', text: '⚑ ' + f.flags.join(' · ') }) : null,
      h('div', { class: 'src' }, [
        f.link ? h('a', { href: f.link, target: '_blank', rel: 'noopener', text: f.source }) : h('span', { text: f.source }),
        f.locator ? h('span', { text: ' — ' + f.locator }) : null,
      ]),
    ]);
    if (f.images && f.images.length) {
      box.append(h('div', { class: 'cs-thumbs' }, f.images.slice(0, 12).map((p) =>
        h('img', { src: '/api/chickenscratch/image?path=' + encodeURIComponent(p), loading: 'lazy',
                   alt: 'scanned page', onclick: () => viewer(p) }))));
    }
    box.append(acts({ fact: f.id }));
    const said = verdicts((n) => n.fact === f.id);
    if (said) box.append(said);
    return box;
  }

  function viewer(p) {
    const v = h('div', { class: 'cs-viewer', onclick: () => v.remove() }, [
      h('img', { src: '/api/chickenscratch/image?path=' + encodeURIComponent(p), alt: 'scanned page' })]);
    document.body.append(v);
  }

  function storyBox(st) {
    const box = h('div', { class: 'cs-story' });
    if (st.summary) for (const p of String(st.summary).split(/\n\n+/)) box.append(h('p', { text: p }));
    const listOf = (title, items, fmt) => {
      if (!items || !items.length) return;
      box.append(h('strong', { text: title }));
      box.append(h('ul', {}, items.map((x) => h('li', { text: fmt ? fmt(x) : String(x) }))));
    };
    listOf('Timeline', st.timeline, (x) => [x.date, x.what, x.confidence && '(' + x.confidence + ')']
      .filter(Boolean).join(' — '));
    listOf('Flags and cautions', st.cautions);
    listOf('Open questions', st.open_questions);
    if (st.by) box.append(h('div', { class: 'cs-sub', text: 'Written ' + (st.at || '') + ' by ' + st.by }));
    return box;
  }

  /* ---- the Quest ----------------------------------------------------------

     The disagreements, one card at a time (2026-11-09: "a fun gamified UI
     to handle all the conflicts, and not give the person information
     overload"). A card is a question with a few answers; the sources sit
     under each answer in a line, the evidence stays folded until asked
     for. An answer is a note with a 'choice' (the card's id is the conflict
     id Browse uses, so it shows there too). Skip only moves the card to
     the back of this session's stack. Keys: 1-4 answer, N not sure,
     S skip, E something else, V evidence. */
  const LEVEL_EMOJI = { Egg: '🥚', Hatchling: '🐣', Chick: '🐤', Pullet: '🐥', Hen: '🐔',
                        Rooster: '🐓', 'Coop Boss': '👑', 'Chicken Whisperer': '🪶' };
  const KIND_WORDS = { order: 'after the end', session: 'which day', dates: 'which day',
                       disagree: 'which is right' };
  const Q = { cards: [], seen: new Set(), stats: null, scope: 'focus', streak: 0, ev: false,
              other: false, busy: false, loaded: false };

  async function questLoad() {
    try {
      const got = await get('/api/chickenscratch/quest?limit=30&scope=' + Q.scope);
      Q.stats = got;
      for (const c of got.cards || []) {
        const id = c.key + '|' + c.id;
        if (!Q.seen.has(id)) { Q.seen.add(id); Q.cards.push(c); }
      }
    } catch (e) {
      Q.stats = { error: e.message };
    }
    Q.loaded = true;
  }

  function hud() {
    const st = Q.stats || {};
    const me = st.me || {};
    const total = st.total || 0;
    const done = st.done || 0;
    const nxt = me.next_level;
    return h('div', {}, [
      h('div', { class: 'q-hud' }, [
        h('span', { class: 'q-level', title: nxt ? (nxt.at - (me.points || 0)) + ' points to ' + nxt.name : 'Top level' }, [
          h('span', { class: 'egg', text: LEVEL_EMOJI[me.level] || '🥚' }), h('span', { text: me.level || 'Egg' })]),
        h('span', { class: 'q-pts', text: (me.points || 0) + ' pts' }),
        h('span', { class: 'q-streak' + (Q.streak >= 3 ? ' hot' : ''),
                    text: Q.streak ? '🔥 ' + Q.streak + ' in a row' : '' }),
        h('span', { class: 'q-scope' }, [['focus', 'DS sheet mice'], ['all', 'Every mouse']].map(([v, w]) =>
          h('button', { class: 'cs-chip', 'aria-pressed': String(Q.scope === v), text: w, onclick: async () => {
            if (Q.scope === v) return;
            Q.scope = v; Q.cards = []; Q.seen = new Set(); Q.loaded = false; quest();
            await questLoad(); quest();
          } }))),
      ]),
      h('div', { class: 'q-bar' }, [h('i', { style: 'width:' + (total ? (100 * done / total).toFixed(1) : 0) + '%' })]),
      h('div', { class: 'q-progress', text: done + ' of ' + total + ' disagreements settled · '
        + (st.mice_cleared || 0) + ' of ' + (st.mice_total || 0) + ' mice cleared' }),
    ]);
  }

  function quest() {
    const root = document.getElementById('csQuest');
    root.innerHTML = '';
    const wrap = h('div', { class: 'q-wrap' });
    root.append(wrap);
    if (!Q.loaded) { wrap.append(h('div', { class: 'cs-empty', text: 'Shuffling the deck…' })); return; }
    if (Q.stats && Q.stats.error) { wrap.append(h('div', { class: 'cs-empty', text: Q.stats.error })); return; }
    wrap.append(hud());
    const c = Q.cards[0];
    if (!c) {
      wrap.append(h('div', { class: 'q-done' }, [
        h('div', { class: 'big', text: '🐔' }),
        h('h2', { text: 'The coop is quiet.' }),
        h('p', { class: 'cs-sub', text: Q.scope === 'focus'
          ? 'Every disagreement about the DS sheet mice has an answer. "Every mouse" has more.'
          : 'Every disagreement has an answer. Thank you.' }),
      ]));
      return;
    }
    wrap.append(card(c));
  }

  function card(c) {
    Q.other = false;
    const box = h('div', { class: 'q-card enter' });
    box.append(h('div', {}, [
      h('button', { class: 'q-mouse', text: label(c.key), title: 'Open this mouse in Browse',
                    onclick: () => { mode('browse'); open(c.key); } }),
      h('span', { class: 'q-kind', text: KIND_WORDS[c.kind] || c.kind }),
    ]));
    box.append(h('div', { class: 'q-question', text: c.question }));
    if (c.subtitle) box.append(h('div', { class: 'q-subtitle', text: c.subtitle }));
    const opts = h('div', { class: 'q-opts' });
    c.options.forEach((o, i) => {
      const said = o.sources && o.sources.length
        ? (o.sources.length === 1 ? 'Said by ' : o.sources.length + ' sources: ') + o.sources.join(', ')
        : '';
      opts.append(h('button', { class: 'q-opt', onclick: (e) => answer(c, 'confirm', o, e.currentTarget) }, [
        h('span', { class: 'k', text: String(i + 1) }),
        h('span', { class: 'l', text: o.label }),
        said ? h('span', { class: 's', text: said }) : null,
      ]));
    });
    box.append(opts);
    const evBox = h('div', { class: 'q-ev', hidden: !Q.ev });
    for (const e of c.evidence || []) {
      evBox.append(h('div', { class: 'e' }, [
        h('b', { text: e.source + (e.date ? ' · ' + e.date : '') }),
        e.where ? h('span', { class: 'cs-sub', text: ' — ' + e.where }) : null,
        e.text ? h('p', { text: e.text }) : null,
        e.image ? h('img', { src: '/api/chickenscratch/image?path=' + encodeURIComponent(e.image),
                             alt: 'the page this comes from', loading: 'lazy', onclick: () => viewer(e.image) }) : null,
      ]));
    }
    const ta = h('textarea', { placeholder: 'What is actually true? A sentence is plenty.' });
    const other = h('div', { class: 'q-else', hidden: true }, [ta, h('button', { class: 'btn sm', text: 'Save',
      onclick: () => { if (ta.value.trim()) answer(c, 'note', { value: null, label: ta.value.trim() }); } })]);
    box.append(h('div', { class: 'q-side' }, [
      h('button', { text: '🤷 Not sure', onclick: () => answer(c, 'unsure', null) }),
      h('button', { text: '⏭ Skip', onclick: () => skip() }),
      h('button', { text: '✎ Something else', onclick: () => {
        other.hidden = !other.hidden; Q.other = !other.hidden; if (!other.hidden) ta.focus(); } }),
      (c.evidence || []).length ? h('button', { text: Q.ev ? '▾ Hide evidence' : '▸ Show evidence',
        onclick: (e) => { Q.ev = !Q.ev; evBox.hidden = !Q.ev;
                          e.currentTarget.textContent = Q.ev ? '▾ Hide evidence' : '▸ Show evidence'; } }) : null,
      h('span', { class: 'q-keys', text: '1–' + c.options.length + ' answer · N not sure · S skip · E else · V evidence' }),
    ]), other, evBox);
    return box;
  }

  function skip() {
    if (Q.busy || !Q.cards.length) return;
    Q.cards.push(Q.cards.shift());
    Q.streak = 0;
    quest();
  }

  async function answer(c, verdict, o, btn) {
    if (Q.busy) return;
    Q.busy = true;
    if (btn) btn.classList.add('picked');
    try {
      await post('/api/chickenscratch/note', {
        key: c.key, verdict, conflict: c.id, via: 'quest',
        choice: o ? o.value : null,
        text: o ? (verdict === 'note' ? o.label : 'Chose: ' + o.label) : 'Not sure',
      });
    } catch (e) {
      Q.busy = false;
      alert(e.message);
      return;
    }
    const before = Q.stats && Q.stats.me ? Q.stats.me.level : null;
    const mouseLeft = Q.cards.filter((x) => x.key === c.key).length - 1;
    Q.cards.shift();
    Q.streak = verdict === 'unsure' ? 0 : Q.streak + 1;
    const cardEl = document.querySelector('.q-card');
    if (cardEl) cardEl.append(h('span', { class: 'q-plus', text: '+10' }));
    if (btn) feathers(btn);
    await new Promise((r) => setTimeout(r, 380));
    // Fresh numbers, and the next few cards if the stack runs low; cards
    // already in hand (a skipped one included) keep their place.
    await questLoad();
    Q.busy = false;
    quest();
    const after = Q.stats && Q.stats.me ? Q.stats.me.level : null;
    if (before && after && before !== after) toast((LEVEL_EMOJI[after] || '') + ' Level up: you are a ' + after + '!');
    else if (mouseLeft === 0 && !Q.cards.some((x) => x.key === c.key)) toast('🎉 ' + label(c.key) + ' cleared');
    else if (Q.streak && Q.streak % 10 === 0) toast('🔥 ' + Q.streak + ' in a row');
  }

  function feathers(from) {
    if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const r = from.getBoundingClientRect();
    for (let i = 0; i < 9; i++) {
      const f = h('span', { class: 'q-feather', text: i % 3 ? '🪶' : '✨' });
      const a = (i / 9) * Math.PI * 2;
      f.style.left = (r.left + r.width / 2) + 'px';
      f.style.top = (r.top + r.height / 2) + 'px';
      f.style.setProperty('--dx', Math.round(Math.cos(a) * (60 + 30 * (i % 3))) + 'px');
      f.style.setProperty('--dy', Math.round(Math.sin(a) * (50 + 20 * (i % 2)) - 30) + 'px');
      f.style.setProperty('--r', (i * 40) + 'deg');
      document.body.append(f);
      setTimeout(() => f.remove(), 1200);
    }
  }

  function toast(text) {
    const t = h('div', { class: 'q-toast', text });
    document.body.append(t);
    setTimeout(() => t.remove(), 2600);
  }

  document.addEventListener('keydown', (e) => {
    if (S.mode !== 'quest' || e.target.closest('textarea, input') || e.ctrlKey || e.metaKey || e.altKey) return;
    const c = Q.cards[0];
    if (!c) return;
    const n = parseInt(e.key, 10);
    if (n >= 1 && n <= c.options.length) {
      e.preventDefault();
      const btn = document.querySelectorAll('.q-opt')[n - 1];
      answer(c, 'confirm', c.options[n - 1], btn);
    } else if (e.key === 'n' || e.key === 'N') { e.preventDefault(); answer(c, 'unsure', null); }
    else if (e.key === 's' || e.key === 'S') { e.preventDefault(); skip(); }
    else if (e.key === 'e' || e.key === 'E') {
      e.preventDefault();
      const b = [...document.querySelectorAll('.q-side button')].find((x) => /Something else/.test(x.textContent));
      if (b) b.click();
    } else if (e.key === 'v' || e.key === 'V') {
      e.preventDefault();
      const b = [...document.querySelectorAll('.q-side button')].find((x) => /evidence/.test(x.textContent));
      if (b) b.click();
    }
  });

  function mode(m) {
    S.mode = m;
    document.body.classList.toggle('questing', m === 'quest');
    document.getElementById('csQuest').hidden = m !== 'quest';
    document.getElementById('csBrowse').hidden = m === 'quest';
    document.getElementById('csModeQuest').setAttribute('aria-selected', String(m === 'quest'));
    document.getElementById('csModeBrowse').setAttribute('aria-selected', String(m !== 'quest'));
    if (m === 'quest' && !Q.loaded) { quest(); questLoad().then(quest); }
  }

  /* ---- start --------------------------------------------------------- */
  async function start() {
    document.getElementById('csModeQuest').addEventListener('click', () => mode('quest'));
    document.getElementById('csModeBrowse').addEventListener('click', () => mode('browse'));
    const wantKey = decodeURIComponent((location.hash || '').slice(1));
    mode(wantKey ? 'browse' : 'quest');
    chips();
    document.getElementById('csSearch').addEventListener('input', (e) => { S.q = e.target.value; list(); });
    let idx;
    try { idx = await get('/api/chickenscratch/index'); } catch (e) {
      document.getElementById('csStats').textContent = e.message; return;
    }
    if (!idx.ready) {
      document.getElementById('csStats').textContent = 'Nothing gathered on this machine yet (tools/chickenscratch).';
      return;
    }
    S.mice = idx.mice;
    const focus = S.mice.filter((m) => m.focus).length;
    document.getElementById('csStats').textContent = S.mice.length + ' mice (' + focus + ' on the Dentate Spike sheet) · '
      + idx.n_facts.toLocaleString() + ' facts from ' + idx.n_sources + ' sources · gathered ' + when(idx.built);
    list();
    const want = decodeURIComponent((location.hash || '').slice(1));
    if (want && S.mice.some((m) => m.key === want)) open(want);
  }
  start();
}());
