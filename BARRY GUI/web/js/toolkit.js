/* ==========================================================================
   toolkit.js -- The jobs that are about the whole pile, not one recording.

   Everywhere else you are looking at a single session. These are the
   questions that span it: which channels have we thrown away, across this
   mouse, over this month, in this project.

   The first tool is the bad-channel export. It is deliberately more than a
   download button: you pick the scope, you see the rows and the counts before
   committing to anything, and the file that comes out carries a header saying
   what it was a list of and when it was taken -- because a CSV called
   "export.csv" in a downloads folder is not a record.
   ========================================================================== */
'use strict';

BARRY.views.toolkit = (function () {
  let scopes = null;      // what there is to choose from
  let preview = null;     // the last previewed rows
  let busy = false;

  // What is being asked for. Held here rather than read off the DOM so a
  // re-render cannot lose a half-filled form.
  const q = {
    tool: 'bad',
    scope: 'all',
    key: '', mouse: '', group: '',
    from: '', to: '',
    form: 'long',
    clean: false,
  };

  /* ==================================================================
     Loading
     ================================================================== */
  async function onShow() {
    render();
    if (!scopes) await loadScopes();
    refresh();
    // Who is in what, and keep it current while this view is open.
    startPresence();
  }

  async function loadScopes() {
    try {
      scopes = await api('/api/toolkit/scopes');
      // Fill in every scope's default up front, so the fields are never
      // empty by the time one of them is shown -- including the date range,
      // which otherwise opens as two blank boxes that look broken.
      const was = q.scope;
      for (const sc of ['session', 'mouse', 'group', 'range']) {
        q.scope = sc;
        seedScope();
      }
      q.scope = was;
    } catch (e) {
      toast('Could not read the session list: ' + e.message, 'err', 8000);
      scopes = { sessions: [], mice: [], groups: [] };
    }
    render();
  }

  /* A scope arrives with its first option already chosen. Otherwise picking
     "One mouse" asks the server about mouse (nothing), which it rightly
     refuses -- so the panel answered a deliberate click with an error. */
  function seedScope() {
    const s = scopes || {};
    if (q.scope === 'session' && !q.key && (s.sessions || []).length) {
      // Prefer one that actually has something marked: an empty session is a
      // confusing thing to land on in a bad-channel report.
      const withBad = (s.sessions || []).find((x) => x.n_bad > 0);
      q.key = (withBad || s.sessions[0]).key;
    }
    if (q.scope === 'mouse' && !q.mouse && (s.mice || []).length) {
      q.mouse = String(s.mice[0]);
    }
    if (q.scope === 'group' && !q.group && (s.groups || []).length) {
      q.group = s.groups[0];
    }
    if (q.scope === 'range') {
      if (!q.from && s.first_day) q.from = s.first_day;
      if (!q.to && s.last_day) q.to = s.last_day;
    }
  }

  function args() {
    const p = new URLSearchParams({ scope: q.scope, form: q.form });
    if (q.scope === 'session') p.set('key', q.key);
    if (q.scope === 'mouse') p.set('mouse', q.mouse);
    if (q.scope === 'group') p.set('group', q.group);
    if (q.scope === 'range') {
      if (q.from) p.set('from', q.from);
      if (q.to) p.set('to', q.to);
    }
    if (q.clean) p.set('clean', '1');
    return p.toString();
  }

  const refresh = debounce(async function refresh_() {
    if (q.tool === 'curate') { await loadCuration(); return; }
    if (q.tool === 'strata') { await loadStrata(); return; }
    /* Kilosort has nothing to do with bad channels.

       It used to fall through to the query below, which fetched the whole
       bad-channel table nobody had asked for and dimmed the pane to 0.55
       while it ran. renderResult then returned early for Kilosort, before
       the line that puts the opacity back -- so the pane stayed at 55% for
       good. That is the "everything is greyed out". */
    if (q.tool === 'kilosort') { renderResult(); return; }
    if (q.tool === 'snapshots') { renderResult(); return; }
    if (busy) return;
    busy = true;
    /* Which tool asked. A debounced request can land after you have clicked
       something else, and rendering its answer then replaces the pane you
       just opened -- which is the "it snaps back to another tool". */
    const asked = q.tool;
    const host = $('#tkResult');
    // Dimmed while re-querying, but only when there is already something to
    // dim; the first read shows the loader instead of a grey rectangle.
    if (host && preview) host.style.opacity = '0.55';
    else if (host) tkLoading('Bad channels',
                             ['reading every recording that has marks']);
    try {
      preview = await api('/api/toolkit/bad-channels?' + args());
      preview.error = null;
    } catch (e) {
      preview = { error: e.message, rows: [], columns: [], summary: {} };
    } finally {
      busy = false;
      if (asked !== q.tool) {
        // Superseded. Undim, and leave the current tool alone.
        if (host) host.style.opacity = '1';
      } else {
        renderResult();
      }
    }
  }, 220);

  /* ==================================================================
     The page
     ================================================================== */
  function render() {
    const host = $('#tkBody');
    if (!host) return;
    host.innerHTML = '';
    host.appendChild(el('div', { class: 'tk-layout' }, [
      el('div', { class: 'tk-tools' }, [
        el('div', { class: 'section-label', style: 'margin-top:0',
                    text: 'Tools' }),
        toolButton('bad', 'Bad channels',
                   'Export which channels were marked bad, by session, mouse, '
                   + 'project or date range.'),
        toolButton('curate', 'Event curation',
                   'Import candidate dentate spikes or IEDs, then go through '
                   + 'them one at a time and say what each one is.'),
        toolButton('strata', 'StrataScope',
                   'Say which anatomical layer each channel is in, against '
                   + 'the live rasters rather than a cropped screenshot.'),
        toolButton('kilosort', 'Kilosort',
                   'Check this machine can sort, run a sort against a '
                   + 'recording, then open it in Phy.'),
        toolButton('snapshots', 'Import sorted snapshots',
                   'Read a folder of dentate-spike images that were sorted '
                   + 'by dragging them into Dentate Spike / Garbage / Flag '
                   + 'folders, and turn it back into curation.'),
        el('p', { class: 'hint tk-soon',
          text: 'More tools will land here as they earn their place. This is '
              + 'the section for anything that spans many recordings at '
              + 'once.' }),
      ]),
      el('div', { class: 'tk-main', id: 'tkMain' },
         /* Which tools own the whole pane. The scope card below is the
            bad-channel query's, and means nothing to the others -- the
            snapshot importer was showing it and asking which recordings to
            scope a folder read to. */
         (q.tool === 'curate' || q.tool === 'strata'
          || q.tool === 'kilosort' || q.tool === 'snapshots')
           ? [el('div', { class: 'tk-result', id: 'tkResult' })]
           : [scopeCard(),
              el('div', { class: 'tk-result', id: 'tkResult' })]),
    ]));
    renderResult();
  }

  function toolButton(id, name, blurb) {
    return el('button', {
      class: 'tk-tool' + (q.tool === id ? ' on' : ''),
      onclick: () => {
        q.tool = id;
        // The Kilosort pane owns its own host; let it rebuild.
        const host = document.getElementById('tkResult');
        if (host) delete host.dataset.ks;
        render();
        refresh();
      },
    }, [
      el('strong', { text: name }),
      el('span', { text: blurb }),
    ]);
  }

  /* ---------- picking the scope ---------- */
  function scopeCard() {
    const box = el('div', { class: 'card tk-scope' });
    box.appendChild(el('div', { class: 'section-label', style: 'margin-top:0',
                                text: 'Which recordings' }));

    const total = (scopes && scopes.total) || 0;
    const choices = [
      ['all', 'Everything', total + ' recorded session'
        + (total === 1 ? '' : 's')],
      ['session', 'One session', 'pick it below'],
      ['mouse', 'One mouse', 'every session for that animal'],
      ['group', 'One project', 'every session in it'],
      ['range', 'A date range', 'by recording date'],
    ];
    box.appendChild(el('div', { class: 'tk-pills' }, choices.map(([id, name, sub]) =>
      el('button', {
        class: 'pill' + (q.scope === id ? ' active' : ''),
        title: sub,
        onclick: () => { q.scope = id; seedScope(); render(); refresh(); },
      }, [
        el('span', { text: name }),
        el('span', { class: 'tk-pill-sub', text: sub }),
      ]))));

    // Only the fields the chosen scope actually uses, so there is never a
    // date range sitting greyed out next to a session picker.
    const fields = el('div', { class: 'tk-fields' });
    if (q.scope === 'session') fields.appendChild(sessionPicker());
    if (q.scope === 'mouse') fields.appendChild(listPicker(
      'Mouse', (scopes && scopes.mice) || [], q.mouse,
      (v) => { q.mouse = v; refresh(); }, (m) => 'm' + m));
    if (q.scope === 'group') fields.appendChild(listPicker(
      'Project', (scopes && scopes.groups) || [], q.group,
      (v) => { q.group = v; refresh(); }));
    if (q.scope === 'range') {
      fields.appendChild(field('From', el('input', {
        type: 'date', value: q.from,
        min: (scopes || {}).first_day || null,
        max: (scopes || {}).last_day || null,
        onchange: (e) => { q.from = e.target.value; refresh(); },
      })));
      fields.appendChild(field('To', el('input', {
        type: 'date', value: q.to,
        min: (scopes || {}).first_day || null,
        max: (scopes || {}).last_day || null,
        onchange: (e) => { q.to = e.target.value; refresh(); },
      })));
      if (scopes && scopes.first_day) {
        fields.appendChild(el('p', { class: 'hint',
          text: 'Recordings on disk run ' + scopes.first_day + ' to '
              + scopes.last_day + '.' }));
      }
    }
    if (fields.childNodes.length) box.appendChild(fields);

    box.appendChild(el('div', { class: 'section-label', text: 'Shape' }));
    box.appendChild(el('div', { class: 'tk-pills flat' }, [
      el('button', {
        class: 'pill' + (q.form === 'long' ? ' active' : ''),
        title: 'One row per bad channel. Filters and pivots cleanly.',
        onclick: () => { q.form = 'long'; render(); refresh(); },
      }, [el('span', { text: 'One row per channel' })]),
      el('button', {
        class: 'pill' + (q.form === 'wide' ? ' active' : ''),
        title: 'One row per session, channels listed in a cell. Easier to read.',
        onclick: () => { q.form = 'wide'; render(); refresh(); },
      }, [el('span', { text: 'One row per session' })]),
    ]));
    box.appendChild(el('label', { class: 'toggle' + (q.clean ? ' on' : '') }, [
      el('input', {
        type: 'checkbox', checked: q.clean ? 'checked' : null,
        onchange: (e) => { q.clean = e.target.checked; refresh(); },
      }),
      el('span', { text: 'Include sessions with nothing marked' }),
    ]));
    box.appendChild(el('p', { class: 'hint',
      text: 'A zero row is the only way to tell a session that was checked '
          + 'and found clean from one nobody has looked at.' }));
    return box;
  }

  function sessionPicker() {
    const list = (scopes && scopes.sessions) || [];
    return field('Session', el('select', {
      onchange: (e) => { q.key = e.target.value; refresh(); },
    }, list.map((s) => el('option', {
      value: s.key,
      selected: q.key === s.key ? 'selected' : null,
      // The bad count in the label answers the question before it is asked.
      text: (s.label || s.key) + (s.n_bad ? '   (' + s.n_bad + ' bad)' : ''),
    }))));
  }

  function listPicker(label, values, current, onchange, fmt) {
    if (!values.length) {
      return el('p', { class: 'hint',
        text: 'No ' + label.toLowerCase() + ' has been recorded yet. Open a '
            + 'recording in Xplorefinder first.' });
    }
    return field(label, el('select', {
      onchange: (e) => onchange(e.target.value),
    }, values.map((v) => el('option', {
      value: String(v),
      selected: String(current) === String(v) ? 'selected' : null,
      text: fmt ? fmt(v) : String(v),
    }))));
  }

  function field(label, control) {
    return el('div', { class: 'field' }, [
      el('label', { text: label }), control,
    ]);
  }

  /* ---------- the rows, and what they add up to ---------- */
  /* ==================================================================
     Event curation

     A detector says where something might be; curation says what it actually
     was. Keeping those apart is the whole design: candidates arrive
     unspecified and stay that way until somebody looks at them.
     ================================================================== */
  let cur = null;
  /* Set by curation whenever a decision is made or a set is opened or put
     down. The tool reloads on its next showing instead of repainting a
     picture of how things were when it was last looked at. */
  let curStale = false;

  /* Show what it is waiting on while it waits.

     Two requests, and the registry is the slow one -- over a second on a
     network share. The pane used to say "Reading..." for both of them and
     look identical whether it was about to finish or had stalled. */
  function tkLoading(label, steps) {
    const host = $('#tkResult');
    if (!host) return null;
    host.style.opacity = '1';
    host.innerHTML = '';
    const l = stepLoader(label, steps);
    host.appendChild(el('div', { class: 'tk-loading' }, [l]));
    return l;
  }

  /* The load in flight, so several callers share one. The registry takes
     seconds on a network share -- nineteen of them in one report -- and
     without this, entering the tool, a stale flag and a refresh each
     started their own, and every copy was slower for the company. */
  let curLoading = null;

  function loadCuration() {
    if (curLoading) return curLoading;
    /* The stepped loader whenever this is actually fetching, not only on
       the very first visit. Coming back from curation the data IS being
       re-read -- that is the point of the stale flag -- and showing the old
       cards motionless for five seconds while it happens looked like the
       view had simply stopped. */
    const l = (q.tool === 'curate' && (!cur || curStale))
      ? tkLoading('Event curation', ['reading the curation sets',
                                     'reading the recording registry'])
      : null;
    curLoading = (async () => {
      try {
        const got = await api('/api/curation');
        if (l) l.step('reading the recording registry');
        got.registry = await api('/api/registry');
        cur = got;
        curStale = false;
      } catch (e) {
        cur = { error: e.message, sets: [], kinds: [] };
      } finally {
        curLoading = null;
      }
      renderCuration();
      return cur;
    })();
    return curLoading;
  }

  /* How the shelf is being looked at -- the shelf only, because the bench
     is not a query result and has no order to choose. Held here rather than
     read off the DOM so a re-render cannot lose a half-typed search. */
  const curQ = { text: '', sort: 'recent', show: 'all', shelf: false };

  const CUR_SORTS = [
    ['recent', 'Recently touched'],
    ['left', 'Most left to do'],
    ['flag', 'Most flagged'],
    ['name', 'Name'],
    ['mouse', 'Mouse and session'],
    ['size', 'Biggest'],
  ];

  /* "opened 2 hours ago", which is the fact, rather than a timestamp that
     has to be subtracted from today's date in your head.

     Date.parse is lenient about `-0400` but not required to accept it --
     the server writes strftime's %z, which has no colon -- so the offset is
     normalised first rather than left to the engine's goodwill. */
  function curWhen(iso) {
    if (!iso) return null;
    const fixed = String(iso).replace(/([+-]\d{2})(\d{2})$/, '$1:$2');
    const t = Date.parse(fixed);
    if (!isFinite(t)) return null;
    const mins = Math.round((Date.now() - t) / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + (mins === 1 ? ' minute ago' : ' minutes ago');
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return hrs + (hrs === 1 ? ' hour ago' : ' hours ago');
    const days = Math.round(hrs / 24);
    if (days < 14) return days + (days === 1 ? ' day ago' : ' days ago');
    return new Date(t).toLocaleDateString(undefined,
      { month: 'short', day: 'numeric' });
  }

  const curOpen = () => ((cur && cur.sets) || [])
    .filter((s) => s.open && !s.archived);

  /* The sets on the shelf that match what is being asked for. Everything
     not on the bench, which includes the finished ones -- being done is not
     a reason to be hidden, only a reason not to be in the way. */
  function curationRows() {
    const all = (cur && cur.sets) || [];
    const q = curQ.text.trim().toLowerCase();
    const words = q ? q.split(/\s+/) : [];
    const by = (st) => (st.progress || {}).by_label || {};

    let rows = all.filter((st) => {
      if (st.open) return false;
      const pr = st.progress || {};
      if (curQ.show === 'left' && !(pr.left > 0)) return false;
      if (curQ.show === 'flagged' && !(by(st).flag > 0)) return false;
      if (curQ.show === 'done' && !(pr.left === 0 && pr.total > 0)) return false;
      if (curQ.show === 'demo' && !String(st.gid || '').startsWith('demo-')) {
        return false;
      }
      /* Archived sessions are out of the way unless asked for. Archiving
         still means what it meant -- "I am done thinking about this at all"
         -- which is a stronger statement than closing it. */
      if (curQ.show === 'archived') {
        if (!st.archived) return false;
      } else if (st.archived) {
        return false;
      }
      if (!words.length) return true;
      const hay = [st.name, st.kind_name, st.kind, st.gid, st.assignee,
                   st.session && st.session.label,
                   st.session && st.session.project,
                   st.session && ('m' + st.session.mouse),
                   st.session && ('s' + st.session.session)]
        .filter(Boolean).join(' ').toLowerCase();
      return words.every((w) => hay.indexOf(w) >= 0);
    });

    const num = (v) => (isFinite(v) ? Number(v) : -1);
    const cmp = {
      left: (a, b) => ((b.progress || {}).left || 0)
                    - ((a.progress || {}).left || 0),
      flag: (a, b) => (by(b).flag || 0) - (by(a).flag || 0),
      name: (a, b) => String(a.name || '').localeCompare(String(b.name || '')),
      size: (a, b) => ((b.progress || {}).total || 0)
                    - ((a.progress || {}).total || 0),
      recent: (a, b) => String(b.opened_at || (b.updated || {}).at || '')
        .localeCompare(String(a.opened_at || (a.updated || {}).at || '')),
      mouse: (a, b) => {
        const sa = a.session || {}, sb = b.session || {};
        return (num(sa.mouse) - num(sb.mouse))
            || (num(sa.session) - num(sb.session))
            || String(a.name || '').localeCompare(String(b.name || ''));
      },
    }[curQ.sort] || (() => 0);
    return rows.slice().sort(cmp);
  }

  function renderCuration() {
    const host = $('#tkResult');
    if (!host) return;
    host.style.opacity = '1';
    host.innerHTML = '';
    if (!cur) {
      host.appendChild(el('div', { class: 'tk-loading' }, [
        stepLoader('Event curation', ['reading the curation sets',
                                      'reading the recording registry'])]));
      return;
    }

    const sets = cur.sets || [];
    const open = curOpen();

    host.appendChild(el('div', { class: 'tk-head' }, [
      el('div', {}, [
        el('h2', { text: 'Event curation' }),
        el('p', { class: 'sub',
          text: open.length
            ? 'What you have open. It stays here until you close it.'
            : 'Start a set from a banked entry, or pick one up below. It '
              + 'stays here until you close it.' }),
      ]),
      el('div', { class: 'spacer' }),
      open.length > 1 ? el('button', {
        class: 'btn ghost sm', text: 'Close all',
        title: 'Clear the bench. Nothing is archived, deleted or unbanked.',
        onclick: closeAllSets,
      }) : null,
      /* Not "Import candidates". Candidates live in the Event Bank, with
         the detector that found them and their version history; curation
         reads a version out of it. Importing them here made Event curation
         a second door into the same store, and implied a recording could
         have more than one set of a kind -- it cannot, so a second import
         merged into the first, added nothing and threw away the name. */
      /* Not a novelty. It is the only view of the decisions as a set
         rather than one at a time, which makes it the only place a
         detector producing mostly obvious garbage would show up. */
      el('button', {
        class: 'btn ghost sm', text: 'Hall of garbage',
        title: 'The candidates nobody had to think about — rejected fast, '
             + 'never flagged, never revisited. Useful for showing a new '
             + 'curator what garbage looks like.',
        onclick: showGarbageHall,
      }),
      el('button', { class: 'btn', text: 'New curation set…',
                     onclick: newCurationSet }),
    ].filter(Boolean)));

    if (!sets.length) {
      host.appendChild(el('div', { class: 'hint tk-empty',
        text: 'Nothing to curate yet. Start a set from something in the '
            + 'Event Bank — pick the recording, the entry and which '
            + 'version of it to work from. Version 0 is the detector\u2019s '
            + 'list with nothing decided yet.' }));
      return;
    }

    /* ---- the bench ---- */
    const bench = el('div', { class: 'cur-sets cur-bench', id: 'curBench' });
    if (open.length) {
      for (const st of open) bench.appendChild(curCard(st));
    } else {
      bench.appendChild(el('div', { class: 'cur-bench-empty' }, [
        el('p', { text: 'Nothing open.' }),
        el('p', { class: 'hint',
          text: 'Pick one up below and it stays on the bench until you put '
              + 'it down. Closing a set neither saves nor loses anything '
              + '— every decision was written the moment you made it.' }),
      ]));
    }
    host.appendChild(bench);

    /* ---- the shelf, folded away until wanted ---- */
    const nShelf = sets.filter((s) => !s.open && !s.archived).length;
    const shelf = el('div', { class: 'cur-shelf', id: 'curShelf' });
    host.appendChild(el('div', { class: 'cur-shelf-head' }, [
      el('button', {
        class: 'cur-shelf-toggle' + (curQ.shelf ? ' on' : ''),
        text: (curQ.shelf ? '▾  ' : '▸  ')
            + (open.length ? 'Pick up another set' : 'Pick up a set')
            + '  ·  ' + nShelf + ' put down',
        onclick: () => { curQ.shelf = !curQ.shelf; renderCuration(); },
      }),
    ]));
    if (curQ.shelf) host.appendChild(shelf);
    if (curQ.shelf) paintShelf();
  }

  /* One set on the bench. Two verbs on the face of it -- carry on, or put
     it down -- and everything administrative folded behind "More", because
     a row that offers you Delete reads as a record in a table rather than
     as work in progress. */
  /* ---------- who is in what, right now ----------

     Kept separate from the curation sets themselves because it is a
     different kind of fact: a set is a record and is still true tomorrow,
     presence is a claim about this minute. Ten seconds because a stale
     "nobody is here" is worse than showing nothing -- it looks
     authoritative, and somebody acts on it. */
  const PRESENCE_POLL = 10000;
  let presence = { sessions: [], machine: null, ttl_s: 150 };
  let presenceTimer = null;

  async function loadPresence(andRender) {
    try {
      const res = await api('/api/presence');
      if (!res || !res.ok) return;
      const before = JSON.stringify(presence.sessions || []);
      presence = res;
      // Only redraw when it actually changed: this runs every ten seconds
      // and the shelf is a few hundred nodes.
      if (andRender && JSON.stringify(res.sessions || []) !== before) {
        renderCuration();
      }
    } catch (e) { /* presence is a courtesy, never an interruption */ }
  }

  function startPresence() {
    if (presenceTimer) return;
    loadPresence(true);
    presenceTimer = setInterval(() => {
      // Only while the curation view is the one being looked at. Polling for
      // a panel nobody can see is just traffic.
      if (BARRY.state.view !== 'toolkit') return;
      loadPresence(true);
    }, PRESENCE_POLL);
  }

  /* Everyone active in a set, this machine included -- the card wants to
     show "you, on the rig" as much as anybody else. */
  function inSet(st) {
    return (presence.sessions || []).filter(
      (s) => s.active && s.gid === st.gid && (s.kind || 'ds') === st.kind);
  }

  /* Somebody who is not us. This is what gates opening. */
  function heldBy(st) {
    return inSet(st).filter((s) => !s.is_me)[0] || null;
  }

  function howLong(sec) {
    if (sec == null) return '';
    if (sec < 60) return 'just now';
    const m = Math.round(sec / 60);
    if (m < 60) return m + ' min ago';
    return Math.round(m / 60) + ' h ago';
  }

  /* The live line. Present only when somebody is in the set, so a quiet
     shelf stays quiet. */
  function presenceLine(st) {
    const here = inSet(st);
    if (!here.length) return null;
    return el('div', { class: 'cur-live' }, here.map((s) => {
      const n = (s.n_decided != null && s.n_total)
        ? s.n_decided + '/' + s.n_total : null;
      const bits = [];
      if (n) bits.push(n + ' decided');
      if (s.n_this_visit) bits.push('+' + s.n_this_visit + ' this sitting');
      if (s.at_index != null) bits.push('at #' + (s.at_index + 1));
      return el('span', {
        class: 'cur-live-who' + (s.is_me ? ' me' : ''),
        title: (s.person || 'Somebody') + ' on ' + (s.device || s.machine)
             + '\nlast heard from ' + howLong(s.age_s)
             + (s.is_me ? '\nThis is this machine.' : ''),
      }, [
        el('span', { class: 'cur-live-dot' }),
        el('b', { text: s.is_me ? 'You' : (s.person || s.device || 'Somebody') }),
        el('span', { text: ' on ' + (s.device || s.machine) }),
        bits.length ? el('span', { class: 'cur-live-n',
                                   text: '  ·  ' + bits.join('  ·  ') }) : null,
      ].filter(Boolean));
    }));
  }

  /* Opening a set somebody else is actively in.

     Advisory, and the override is right there. The ask was to stop two
     people curating the same file *accidentally* -- an accident is prevented
     by being told, and a hard block would also stop the deliberate case,
     which is legitimate and common: somebody left a set open on a rig and
     went home. A lock that gets in the way of the honest case is a lock
     people learn to route around.

     Taking it marks their session rather than deleting it, so their window
     finds out and says so, instead of carrying on writing decisions into a
     set it no longer holds. */
  async function enterSet(st) {
    const held = heldBy(st);
    if (!held) { BARRY.curate.enter(st.gid, st.kind); return; }

    const who = held.person || held.device || 'Somebody';
    const got = (held.n_decided != null && held.n_total)
      ? held.n_decided + ' of ' + held.n_total + ' decided'
      : 'in progress';
    const ok = await BARRY.confirm(
      who + ' is curating this set right now',
      who + ' has it open on ' + (held.device || held.machine)
      + ', last heard from ' + howLong(held.age_s) + ' — ' + got
      + (held.n_this_visit ? ', ' + held.n_this_visit + ' this sitting' : '')
      + '.\n\nIf you both work on it you will both be deciding the same '
      + 'candidates, and the merge will have to pick a winner. Nothing is '
      + 'lost either way, but one of you will have wasted the afternoon.'
      + '\n\nOpening it anyway tells their window that you have taken it, '
      + 'so they find out rather than carrying on.',
      'Take it anyway');
    if (!ok) return;

    try {
      await apiPost('/api/presence/take',
                    { gid: st.gid, kind: st.kind, machine: held.machine });
    } catch (e) { /* saying so is best effort; opening it is not */ }
    BARRY.curate.enter(st.gid, st.kind);
    loadPresence(true);
  }

  /* ==================================================================
     The hall of garbage
     ==================================================================
     The candidates nobody had to think about: rejected, decided in under a
     couple of seconds, never flagged, never revisited. Which makes it a
     teaching set -- the fastest way to explain what garbage looks like is
     forty examples that nobody hesitated over -- and a sanity check on the
     detector, since a detector producing this much obvious garbage is
     saying something about its threshold.

     The honest part is the caveat. Most of the decisions in this store were
     backfilled with one shared timestamp, so their gaps are not durations
     at all, and those are excluded and counted rather than quietly averaged
     in. A hall of fame built on made-up numbers would be worse than none.
     ================================================================== */
  let hall = null;

  async function showGarbageHall() {
    showModal(el('div', { class: 'gh-wrap' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Hall of garbage' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'hint', text: 'Reading every decision…' }),
      ]),
    ]));
    try {
      hall = await api('/api/curation/garbage-hall?limit=60');
    } catch (e) {
      hall = { failed: e.message };
    }
    drawHall();
  }

  function drawHall() {
    if (!hall) return;
    const rows = hall.hall || [];
    const body = el('div', { class: 'mb' });

    if (hall.failed) {
      body.appendChild(el('div', { class: 'hint',
        text: 'Could not read the decisions: ' + hall.failed }));
    } else {
      body.appendChild(el('p', { class: 'sub',
        text: 'Rejected in under ' + hall.quick_s + ' seconds, never '
            + 'flagged, never revisited. Sorted by how fast the call was.' }));

      /* Said before the list, not after it. If most of the store cannot be
         timed then the list is a sample of a corner of it, and somebody
         reading "5 qualify" out of nine thousand decisions deserves to know
         why before they conclude the detector is fine. */
      if (hall.unusable) {
        body.appendChild(el('div', { class: 'ecx-warn' }, [
          el('strong', { text: hall.unusable.toLocaleString()
                             + ' decisions could not be timed. ' }),
          el('span', { text: hall.why || 'They share one timestamp, so the '
            + 'gap between them is not how long anybody took. They are left '
            + 'out rather than guessed at.' }),
        ]));
      }

      if (!rows.length) {
        body.appendChild(el('div', { class: 'hint',
          text: 'Nothing qualifies yet. It fills up as people curate — '
              + 'every fast rejection lands here.' }));
      } else {
        const list = el('div', { class: 'gh-list' });
        rows.forEach((r, i) => {
          list.appendChild(el('div', { class: 'gh-row' }, [
            el('span', { class: 'gh-rank', text: '#' + (i + 1) }),
            el('span', { class: 'gh-took', text: r.took_s + 's' }),
            el('span', { class: 'gh-sess', text: r.session || r.gid }),
            el('span', { class: 'gh-at', text: fmtClock(r.start) }),
            el('span', { class: 'gh-by', text: r.by || '' }),
            /* Straight to the candidate, because "show me" is the next
               thought after "that was quick". */
            el('button', {
              class: 'linkish gh-go', text: 'look',
              title: 'Open that recording at that moment',
              onclick: () => { closeModal(); goToCandidate(r); },
            }),
          ]));
        });
        body.appendChild(list);
        body.appendChild(el('div', { class: 'hint gh-foot',
          text: rows.length >= hall.n
            ? (hall.n === 1 ? 'One qualifies.'
                            : 'All ' + hall.n + ' that qualify are shown.')
            : hall.n + ' qualify altogether; the fastest ' + rows.length
              + ' are shown.' }));
      }
    }

    showModal(el('div', { class: 'gh-wrap' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Hall of garbage' }),
        el('span', { class: 'sub',
          text: 'The candidates nobody had to think about' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
      body,
    ]), { replace: true });
  }

  function fmtClock(sec) {
    if (!isFinite(sec)) return '';
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m + ':' + (s < 10 ? '0' : '') + s.toFixed(1);
  }

  /* Open the recording it came from and put the window on it. Not curation
     mode -- looking at an example is not deciding it, and entering curation
     would take the set off whoever has it and reset their pass. */
  async function goToCandidate(r) {
    const sets = (cur && cur.sets) || [];
    const st = sets.find((x) => x.gid === r.gid && x.kind === r.kind);
    const label = (st && st.session && st.session.label) || r.session || r.gid;
    let info = st;
    if (!info) {
      try {
        info = await api('/api/curation/' + encodeURIComponent(r.gid) + '/'
                         + encodeURIComponent(r.kind));
      } catch (e) { info = null; }
    }
    const here = ((info && (info.session || {})).here) || [];
    if (!here.length) {
      toast('That recording is not reachable from this machine: ' + label,
            'warn', 7000);
      return;
    }
    setView('xplore');
    const sess = await BARRY.views.xplore.open(here[0]);
    if (!sess) return;
    /* A second either side, the same window curation uses -- enough to tell
       a deflection from an artifact on one wire, which is the whole point of
       looking at it. */
    BARRY.views.xplore.setWindow(0, Math.max(0, r.start - 0.5), 1.0);
  }

  function curCard(st) {
    const pr = st.progress || {};
    const done = pr.left === 0 && pr.total > 0;
    const reach = st.session && st.session.reachable;
    const who = st.assignee || null;
    const when = curWhen(st.opened_at);
    const key = st.gid + '/' + st.kind;

    const more = el('div', { class: 'cur-set-more',
                             hidden: curMore[key] ? null : 'hidden' }, [
      el('button', {
        class: 'btn ghost sm', text: 'Bank the results…',
        disabled: pr.specified ? null : 'disabled',
        title: pr.specified
          ? 'Publish the decided ones to the Event Bank as a new version. '
            + 'Not a save — the decisions are already saved.'
          : 'Nothing has been decided yet',
        onclick: () => bankSet(st),
      }),
      el('button', {
        class: 'btn ghost sm', text: 'Export CSV',
        onclick: () => window.open(
          '/api/curation/' + encodeURIComponent(st.gid) + '/'
          + encodeURIComponent(st.kind) + '/export', '_blank'),
      }),
      /* What the last sitting on it came to. Available whether or not the
         set is open, because the question "how long did that take" arrives
         after you have already left. */
      el('button', {
        class: 'btn ghost sm', text: 'Receipt',
        disabled: (pr.specified) ? null : 'disabled',
        title: pr.specified
          ? 'What the last sitting on this set came to, and how fast'
          : 'Nothing has been decided yet',
        onclick: () => BARRY.curate.receipt(st.gid, st.kind),
      }),
      el('button', {
        class: 'btn ghost sm', text: st.archived ? 'Unarchive' : 'Archive',
        title: st.archived
          ? 'Put it back on the shelf'
          : 'Files the set away: off the shelf as well as off the bench. '
            + 'Nothing is deleted — every candidate and every decision '
            + 'stays exactly as it is, and it can still be opened, curated '
            + 'and banked.',
        onclick: () => archiveSet(st, !st.archived),
      }),
      /* No Delete. It erased every machine's shard of the set -- the one
         irreversible thing in this view, sitting at the same weight as
         Export CSV. Archiving is what "get this out of my way" means, and
         it destroys nothing. */
    ]);

    return el('div', {
      class: 'cur-set' + (done ? ' done' : '') + (st.archived ? ' archived' : ''),
    }, [
      el('div', { class: 'cur-set-top' }, [
        el('strong', { text: st.name }),
        el('span', { class: 'hk-chip', text: st.kind_name }),
        el('span', { class: 'cur-set-sess',
                     text: (st.session || {}).label || st.gid }),
        el('div', { style: 'flex:1' }),
        el('span', { class: 'cur-set-n',
          text: pr.specified + ' / ' + pr.total
              + (done ? '  ✓' : '  ·  ' + pr.left + ' left') }),
      ]),
      /* Whose it is and when it was last picked up. Without a name on it,
         forty sets are forty identical rows and there is no way to tell
         "mine, this morning" from "somebody's, in June". */
      el('div', { class: 'cur-set-who' }, [
        el('button', {
          class: 'cur-who' + (who ? '' : ' none'),
          title: who ? 'Assigned to ' + who + ' — click to change'
                     : 'Nobody has this one. Click to put a name on it.',
          text: who || 'unassigned',
          onclick: () => assignSet(st),
        }),
        when ? el('span', { class: 'cur-set-when',
          text: 'opened ' + when
              + (st.opened_by && st.opened_by !== who
                  ? ' by ' + st.opened_by : '') }) : null,
      ].filter(Boolean)),
      /* Above the progress bar, because it is about right now and the bar
         is about the set. */
      presenceLine(st),
      el('div', { class: 'cur-prog small' }, [
        el('i', { style: 'width:' + (pr.percent || 0) + '%' }),
      ]),
      el('div', { class: 'cur-set-tally' },
         (st.labels || []).map((l) => el('span', {
           class: 'cur-tally', style: '--cat:' + l.color,
           text: l.name + '  ' + ((pr.by_label || {})[l.id] || 0),
         }))),
      el('div', { class: 'cur-set-acts' }, [
        el('button', {
          class: 'btn sm', text: pr.left ? 'Carry on…' : 'Look again…',
          disabled: reach ? null : 'disabled',
          title: reach
            ? 'Open the recording and step through the candidates'
            : 'This recording is not on a drive this machine can reach',
          onclick: () => enterSet(st),
        }),
        el('button', {
          class: 'btn ghost sm', text: 'Put it down',
          title: 'Off the bench. Nothing to save first — every decision '
               + 'was written as you made it, and it is all still here.',
          onclick: () => openSet(st, false),
        }),
        el('div', { style: 'flex:1' }),
        el('button', {
          class: 'btn ghost sm', text: curMore[key] ? 'Less' : 'More…',
          onclick: () => {
            curMore[key] = !curMore[key];
            renderCuration();
          },
        }),
      ]),
      more,
    ]);
  }

  /* Which cards have their administrative half showing. Outside the render
     so opening it survives the next repaint. */
  const curMore = {};

  /* The shelf: a picker, and the only place the list is a list. This is
     where searching and sorting belong -- you are looking something up. */
  function paintShelf() {
    const shelf = document.getElementById('curShelf');
    if (!shelf) return;
    shelf.innerHTML = '';
    const sets = (cur && cur.sets) || [];
    const down = sets.filter((s) => !s.open && !s.archived);
    const nLeft = down.filter((s) => ((s.progress || {}).left || 0) > 0).length;
    const nFlag = down.filter(
      (s) => (((s.progress || {}).by_label) || {}).flag > 0).length;
    const nDone = down.filter((s) => {
      const p = s.progress || {};
      return p.left === 0 && p.total > 0;
    }).length;
    const nDemo = down.filter(
      (s) => String(s.gid || '').startsWith('demo-')).length;
    const nArch = sets.filter((s) => s.archived).length;

    const search = el('input', {
      type: 'text', class: 'cur-search', value: curQ.text,
      placeholder: 'Search a name, a mouse, a session, a person…',
      oninput: (e) => { curQ.text = e.target.value; paintShelfList(); },
    });
    const chip = (id, label, n) => el('button', {
      class: 'pill' + (curQ.show === id ? ' active' : ''),
      disabled: (n === 0 && id !== 'all') ? 'disabled' : null,
      text: label + ' (' + n + ')',
      onclick: () => { curQ.show = id; paintShelf(); },
    });

    shelf.appendChild(el('div', { class: 'cur-filter' }, [
      search,
      el('select', {
        title: 'Order',
        onchange: (e) => { curQ.sort = e.target.value; paintShelfList(); },
      }, CUR_SORTS.map(([v, t]) => el('option', {
        value: v, text: t, selected: curQ.sort === v ? 'selected' : null }))),
    ]));
    shelf.appendChild(el('div', { class: 'res-toolbar cur-chips' }, [
      chip('all', 'All', down.length),
      chip('left', 'Unfinished', nLeft),
      chip('flagged', 'Has flagged', nFlag),
      chip('done', 'Done', nDone),
      nArch ? chip('archived', 'Archived', nArch) : null,
      nDemo ? chip('demo', 'Demo', nDemo) : null,
      el('div', { class: 'spacer', style: 'flex:1' }),
      el('span', { class: 'hint', id: 'curCount' }),
    ].filter(Boolean)));
    /* Named columns. A bare "416 ✓", a dash and "15 minutes ago"
       are three facts nobody can identify without being told which
       is which. */
    shelf.appendChild(el('div', { class: 'cur-shelf-cols' }, [
      el('span', { class: 'csr-name', text: 'Set' }),
      el('span', { class: 'csr-sess', text: 'Recording' }),
      el('span', { class: 'csr-n', text: 'Decided' }),
      el('span', { class: 'csr-who', text: 'Whose' }),
      el('span', { class: 'csr-when', text: 'Last touched' }),
      el('span', {}),
    ]));
    shelf.appendChild(el('div', { class: 'cur-shelf-list', id: 'curShelfList' }));
    paintShelfList();
  }

  /* Only the list, so typing in the search box does not rebuild the box
     being typed into and lose the caret. */
  function paintShelfList() {
    const list = document.getElementById('curShelfList');
    if (!list) return;
    list.innerHTML = '';
    const rows = curationRows();
    const total = ((cur && cur.sets) || []).filter(
      (s) => !s.open && !s.archived).length;
    const count = document.getElementById('curCount');
    if (count) {
      count.textContent = rows.length === total
        ? rows.length + ' set(s)'
        : rows.length + ' of ' + total;
    }
    if (!rows.length) {
      list.appendChild(el('div', { class: 'hint',
        text: 'Nothing matches that. Clear the search, or pick All.' }));
      return;
    }
    for (const st of rows) {
      const pr = st.progress || {};
      const done = pr.left === 0 && pr.total > 0;
      const reach = st.session && st.session.reachable;
      const when = curWhen(st.opened_at) || curWhen((st.updated || {}).at);
      list.appendChild(el('div', {
        class: 'cur-shelf-row' + (done ? ' done' : ''),
      }, [
        el('span', { class: 'csr-name', text: st.name }),
        el('span', { class: 'csr-sess',
                     text: (st.session || {}).label || st.gid }),
        el('span', { class: 'csr-n',
          text: done ? pr.total + ' ✓'
                     : pr.specified + ' / ' + pr.total }),
        el('span', { class: 'csr-who' + (st.assignee ? '' : ' none'),
                     text: st.assignee || '—' }),
        el('span', { class: 'csr-when', text: when || '' }),
        el('div', { class: 'csr-acts' }, [
        el('button', {
          class: 'btn ghost sm', text: 'Pick it up',
          title: 'Put it on the bench. Opening the recording is the '
               + 'next step, not this one — a set you cannot curate '
               + 'right now can still be claimed, named and exported.',
          onclick: () => openSet(st, true),
        }),
        el('button', {
          class: 'btn ghost sm icon-only',
          text: '\u2192', title: reach
            ? 'Pick it up and go straight to the recording'
            : 'This recording is not on a drive this machine can reach',
          disabled: reach ? null : 'disabled',
          /* Through openSet, so an archived set asks the same question
             here as the button beside it -- going straight to the
             recording is still picking it up. */
          onclick: async () => {
            if (st.archived) {
              await openSet(st, true);
              if (st.archived) return;      // the question was declined
            }
            BARRY.curate.enter(st.gid, st.kind);
          },
        }),
        ]),
      ]));
    }
  }

  /* Start a set from a banked entry's version.

     Three questions in order, because each one narrows the next: which
     recording, which of its banked entries, and which version of that
     entry. The version matters and used to be unaskable -- v0 is the
     detector's list with nothing decided, which is how a fresh pass begins,
     and a later version is how you carry on from where somebody left off. */
  async function newCurationSet() {
    /* Wait for the registry rather than reading whatever is cached.
       It is a seconds-long fetch on a network share, and reading it early
       gave an empty list -- which the code then reported as "no recordings
       are registered", to somebody with a recording open. */
    if (!(cur && cur.registry)) {
      toast('Reading the recording registry\u2026', null, 2500);
      await loadCuration();
    }
    const reg = ((cur || {}).registry || {}).tree || [];
    const rows = reg.flatMap((p) => p.mice.flatMap((m) => m.sessions));
    if (!rows.length) {
      /* Now it is safe to say which of the two it is. */
      toast((cur && cur.registry)
        ? 'The recording registry is empty \u2014 no recording has been '
          + 'opened on this machine yet. Open one in Xplorefinder and it '
          + 'will be registered.'
        : 'Could not read the recording registry'
          + ((cur || {}).error ? ': ' + cur.error : '.')
          + ' Nothing can be picked until it answers.', 'err', 9000);
      return;
    }

    /* Default to a recording that actually has something banked. The first
       reachable one is usually not that, and opening the wizard onto "there
       is nothing to work from here" makes it look broken when it is only
       pointed at the wrong session. */
    let banked = new Set();
    try {
      const b = await api('/api/bank');
      for (const e of (b.entries || [])) {
        if (e.gid && (e.type === 'ds' || e.type === 'ied')) banked.add(e.gid);
      }
    } catch (e) { /* the picker still works, it just starts somewhere else */ }
    let gid = (rows.find((r) => r.reachable && banked.has(r.gid))
               || rows.find((r) => banked.has(r.gid))
               || rows.find((r) => r.reachable) || rows[0] || {}).gid;
    let info = null;            // what is banked for the chosen recording
    let entry = null;
    let ver = null;

    const body = el('div', { class: 'mb' });
    const okBtn = el('button', { class: 'btn', text: 'Start on it',
                                 disabled: 'disabled' });

    const sessPick = BARRY.pickSession({
      rows,
      value: gid,
      placeholder: 'Which recording? Type a mouse, session or date\u2026',
      onpick: (r) => { gid = r.gid; entry = null; ver = null; load(); },
    });

    const load = async () => {
      info = null;
      paint();
      try {
        info = await api('/api/curation/for-recording/'
                         + encodeURIComponent(gid));
      } catch (e) {
        info = { entries: [], existing: [], error: e.message };
      }
      // One entry, one version worth having: choose it, so the common case
      // is two clicks rather than four.
      const es = info.entries || [];
      if (es.length === 1) {
        entry = es[0];
        const usable = (entry.versions || []).filter((v) => v.usable);
        if (usable.length === 1) ver = usable[0];
      }
      paint();
    };

    const paint = () => {
      body.innerHTML = '';
      body.appendChild(el('div', { class: 'field' }, [
        el('label', { text: 'Recording' }), sessPick]));

      if (!info) {
        body.appendChild(el('p', { class: 'hint',
          text: 'Reading what is banked for it\u2026' }));
        okBtn.disabled = 'disabled';
        return;
      }
      if (info.error) {
        body.appendChild(el('p', { class: 'confirm-sub warn',
                                   text: info.error }));
        okBtn.disabled = 'disabled';
        return;
      }

      /* What is already there, said before anything is chosen -- replacing
         a half-finished set is the one irreversible thing here. */
      for (const ex of (info.existing || [])) {
        const pr = ex.progress || {};
        body.appendChild(el('p', { class: 'confirm-sub warn',
          text: 'This recording already has a ' + (ex.kind_name || ex.kind)
              + ' set \u2014 ' + pr.specified + ' of ' + pr.total
              + ' decided'
              + (ex.assignee ? ', ' + ex.assignee + '\u2019s' : '')
              + (ex.archived ? ', archived' : '')
              + '. Starting a new one of that kind replaces it.' }));
      }

      const es = info.entries || [];
      if (!es.length) {
        body.appendChild(el('p', { class: 'confirm-msg',
          text: 'Nothing of a curatable kind is banked against this '
              + 'recording, so there are no times to work from. File the '
              + 'detector\u2019s output in the Event Bank first \u2014 that '
              + 'is where candidates live.' }));
        okBtn.disabled = 'disabled';
        return;
      }

      body.appendChild(el('div', { class: 'section-label',
                                   text: 'Which banked entry' }));
      const list = el('div', { class: 'bm-list' });
      for (const e of es) {
        list.appendChild(el('label', {
          class: 'bm-row' + (entry && entry.id === e.id ? ' on' : ''),
        }, [
          el('input', { type: 'radio', name: 'ncsEntry',
            checked: entry && entry.id === e.id ? 'checked' : null,
            onchange: () => {
              entry = e; ver = null;
              const usable = (e.versions || []).filter((v) => v.usable);
              if (usable.length === 1) ver = usable[0];
              paint();
            } }),
          el('span', { class: 'mk-name', text: e.name }),
          el('span', { class: 'flagchip', text: e.kind_name }),
          el('span', { class: 'person-what',
                       text: (e.n || 0) + ' events'
                           + (e.source ? '  \u00b7  ' + e.source : '') }),
        ]));
      }
      body.appendChild(list);

      if (!entry) { okBtn.disabled = 'disabled'; return; }

      body.appendChild(el('div', { class: 'section-label',
                                   text: 'Which version to work from' }));
      const names = entry.label_names || {};
      const nameOf = (k) => names[k] || (k === 'unspecified' ? 'undecided' : k);
      const vlist = el('div', { class: 'bm-list' });
      for (const v of (entry.versions || [])) {
        const mix = Object.keys(v.by_label || {})
          .sort((a, b) => v.by_label[b] - v.by_label[a])
          .map((k) => nameOf(k) + ' ' + v.by_label[k]).join('  \u00b7  ');
        vlist.appendChild(el('label', {
          class: 'bm-row' + (ver && ver.v === v.v ? ' on' : '')
               + (v.usable ? '' : ' off'),
        }, [
          el('input', { type: 'radio', name: 'ncsVer',
            disabled: v.usable ? null : 'disabled',
            checked: ver && ver.v === v.v ? 'checked' : null,
            onchange: () => { ver = v; paint(); } }),
          el('span', { class: 'ver-n', text: 'v' + v.v }),
          v.imported ? el('span', { class: 'flagchip',
                                    text: 'the detector' }) : null,
          el('span', { class: 'mk-name', text: mix || (v.n || 0) + ' events' }),
          el('span', { class: 'person-what',
            text: (v.by || 'unknown')
                + '  \u00b7  ' + (curWhen(v.at) || '')
                + (v.usable ? '' : '  \u00b7  no snapshot kept') }),
        ].filter(Boolean)));
      }
      body.appendChild(vlist);

      if (ver) {
        const decided = Object.keys(ver.by_label || {})
          .filter((k) => k !== 'unspecified')
          .reduce((n, k) => n + ver.by_label[k], 0);
        body.appendChild(el('p', { class: 'confirm-msg',
          text: 'The set will hold ' + (ver.n || 0) + ' candidate(s)'
              + (decided ? ', ' + decided + ' of them already decided as of '
                           + 'v' + ver.v + '.'
                         : ', none decided \u2014 a fresh pass.') }));
        if (ver.note) {
          body.appendChild(el('p', { class: 'hint', text: '\u201c'
                                     + ver.note + '\u201d' }));
        }
      }
      okBtn.disabled = ver ? null : 'disabled';
    };

    okBtn.onclick = async () => {
      if (!entry || !ver) return;
      const had = (info.existing || []).find((x) => x.kind === entry.kind);
      if (had) {
        const pr = had.progress || {};
        const ok = await BARRY.confirm(
          'Replace the existing ' + (had.kind_name || had.kind) + ' set?',
          'This recording already has one \u2014 "' + (had.name || '')
          + '", ' + pr.specified + ' of ' + pr.total + ' decided'
          + (had.assignee ? ', assigned to ' + had.assignee : '')
          + '. A recording has one set per kind, so starting from v' + ver.v
          + ' replaces it. The decisions in it are still in the bank if they '
          + 'were ever banked; anything never banked goes.',
          'Replace it with v' + ver.v, true);
        if (!ok) return;
      }
      okBtn.disabled = 'disabled';
      try {
        const res = await apiPost('/api/curation/from-bank', {
          gid, kind: entry.kind, entry: entry.id, version: ver.v,
          replace: true,
        });
        closeModal();
        const pr = res.progress || {};
        toast('Started "' + (res.set || {}).name + '" from v' + ver.v
              + ': ' + pr.total + ' candidate(s), ' + pr.left + ' to decide.'
              + (res.replaced ? ' The previous set was replaced.' : ''),
              'ok', 8000);
        await loadCuration();
        // Straight onto the bench, which is what "start working on it" means.
        openSet((cur.sets || []).find(
          (x) => x.gid === gid && x.kind === entry.kind) || {}, true);
      } catch (e) {
        toast(e.message, 'err', 9000);
        okBtn.disabled = null;
      }
    };

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'New curation set' }),
        el('span', { class: 'sub',
                     text: 'from a version of something already banked' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      body,
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel',
                       onclick: closeModal }),
        okBtn,
      ]),
    ]));
    load();
  }

  /* ---- the workbench verbs ---- */
  async function openSet(st, on, unarchive) {
    /* Archiving is a decision, so un-doing it is one too. Picking up an
       archived set used to un-archive it silently -- "archived it and could
       still just open it" was the report. */
    if (on && st.archived && !unarchive) {
      const ok = await BARRY.confirm(
        'Un-archive "' + (st.name || st.gid) + '"?',
        'It is archived, which is how a set is filed away. Putting it on '
        + 'the bench means taking it back out \u2014 a set cannot be both '
        + 'archived and in use, or it shows up in neither list.',
        'Un-archive and pick it up');
      if (!ok) return;
      return openSet(st, true, true);
    }

    /* On screen first. The round trip is seconds on a network share, and
       the answer is already known locally -- the decision was made by the
       click. Rolled back and said out loud if the write fails. */
    const was = { open: st.open, archived: st.archived,
                  opened_at: st.opened_at, closed_at: st.closed_at,
                  assignee: st.assignee };
    st.open = !!on;
    if (on) {
      st.opened_at = new Date().toISOString();
      st.archived = false;
      if (!st.assignee && BARRY.profile && BARRY.profile.who()) {
        st.assignee = BARRY.profile.who();
      }
    } else {
      st.closed_at = new Date().toISOString();
    }
    renderCuration();
    const pr = st.progress || {};
    if (on) {
      toast('On the bench' + (st.assignee ? ', assigned to '
            + st.assignee : '') + '. It stays there until you put it '
            + 'down.', 'ok', 4500);
    } else {
      toast('Put down. ' + (pr.specified || 0) + ' decision(s) are saved '
            + 'and it is on the shelf whenever you want it back.',
            'ok', 5000);
    }

    try {
      const res = await apiPost(
        '/api/curation/' + encodeURIComponent(st.gid) + '/'
        + encodeURIComponent(st.kind) + '/open',
        { open: !!on, unarchive: !!unarchive });
      // The server's answer is the truth; the guess above only had to be
      // fast. They agree in every ordinary case.
      if (res.set) { Object.assign(st, res.set); renderCuration(); }
    } catch (e) {
      Object.assign(st, was);
      renderCuration();
      toast('That did not save: ' + (e && e.message || e), 'err', 8000);
    }
  }

  async function closeAllSets() {
    const open = curOpen();
    const ok = await BARRY.confirm(
      'Clear the bench?',
      'This puts down ' + open.length + ' set(s). Nothing is archived, '
      + 'deleted or unbanked, and no decision is lost — they were all '
      + 'written as they were made. Each one goes back on the shelf.',
      'Put down ' + open.length + ' set(s)');
    if (!ok) return;
    try {
      const res = await apiPost('/api/curation/close-all', {});
      toast('Bench cleared — ' + res.n + ' set(s) put down.', 'ok', 5000);
      await loadCuration();
    } catch (e) { toast(e.message, 'err', 8000); }
  }

  /* Who has worked on this repo, cached for the session. Compiled by the
     server from the profiles, the decisions and the bank, so it is exactly
     the set of names already stamped on the data. */
  let roster = null;

  async function people(force) {
    if (roster && !force) return roster;
    try {
      roster = await api('/api/people');
    } catch (e) {
      roster = { people: [], not_people: [], me: null };
    }
    return roster;
  }

  /* Pick an owner from the people already here, rather than retyping a
     name. A free-text box is how one person becomes three -- "Rain",
     "rain" and "Rain " are three owners to any list that groups by name. */
  async function assignSet(st) {
    const r = await people();
    let chosen = st.assignee || null;
    const list = el('div', { class: 'bm-list tall person-list' });
    const fresh = el('input', {
      type: 'text', class: 'cur-search',
      placeholder: 'Somebody not listed yet\u2014 type a name',
    });

    const paint = () => {
      list.innerHTML = '';
      /* Archived people are not offered. Except the one who already has
         this set: hiding a current owner would leave a set assigned to a
         name that is nowhere on screen, and no way to hand it on. */
      const rows = (r.people || []).filter(
        (x) => !x.archived || x.name === st.assignee);
      const away = (r.people || []).filter(
        (x) => x.archived && x.name !== st.assignee).length;
      if (!rows.length) {
        list.appendChild(el('div', { class: 'hint',
          text: 'Nobody is on the roster yet. BARRY builds it from the '
              + 'names already stamped on decisions and bank entries, so '
              + 'it fills in as work happens \u2014 or type one below.' }));
      }
      /* Nobody is a real answer, and the only way to hand a set back. */
      list.appendChild(el('label', {
        class: 'bm-row' + (chosen === null ? ' on' : ''),
      }, [
        el('input', { type: 'radio', name: 'whose',
          checked: chosen === null ? 'checked' : null,
          onchange: () => { chosen = null; paint(); } }),
        el('span', { class: 'mk-name', text: 'Nobody' }),
        el('span', { class: 'flagchip', text: 'unassigned' }),
      ]));
      for (const p of rows) {
        const what = Object.keys(p.counts || {})
          .map((k) => p.counts[k] + ' ' + k).join('  \u00b7  ');
        list.appendChild(el('label', {
          class: 'bm-row' + (chosen === p.name ? ' on' : ''),
        }, [
          el('input', { type: 'radio', name: 'whose',
            checked: chosen === p.name ? 'checked' : null,
            onchange: () => { chosen = p.name; paint(); } }),
          el('span', { class: 'mk-name', text: p.name }),
          what ? el('span', { class: 'person-what', text: what }) : null,
          p.me ? el('span', { class: 'flagchip good', text: 'you' }) : null,
          p.archived
            ? el('span', { class: 'flagchip', text: 'archived' }) : null,
        ].filter(Boolean)));
      }
      /* Said, not silently dropped. A picker that is quietly shorter than
         the roster is a picker somebody will scroll looking for a name. */
      if (away) {
        list.appendChild(el('div', { class: 'hint',
          text: away + ' archived ' + (away === 1 ? 'person is' : 'people are')
              + ' not listed. They are still on every record they are on — '
              + 'un-archive them in Profile to offer them work again.' }));
      }
    };
    paint();

    const save = async (who) => {
      closeModal();
      try {
        const res = await apiPost(
          '/api/curation/' + encodeURIComponent(st.gid) + '/'
          + encodeURIComponent(st.kind) + '/assign', { who: who });
        if (res.set) Object.assign(st, res.set);
        renderCuration();
        toast(who ? 'Assigned to ' + who + '.' : 'Handed back \u2014 nobody '
              + 'has this one now.', 'ok', 4000);
      } catch (e) { toast(e.message, 'err', 8000); }
    };

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Who is working on this?' }),
        el('span', { class: 'sub', text: st.name || st.gid }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        list,
        el('div', { class: 'section-label', text: 'Or add somebody' }),
        el('div', { class: 'person-add' }, [
          fresh,
          el('button', {
            class: 'btn ghost sm', text: 'Add and assign',
            onclick: async () => {
              const name = (fresh.value || '').trim();
              if (!name) { toast('Type a name first.', 'err', 3000); return; }
              try {
                roster = await apiPost('/api/people/add', { name: name });
              } catch (e) { toast(e.message, 'err', 8000); return; }
              save(name);
            },
          }),
        ]),
        (r.not_people || []).length
          ? el('p', { class: 'hint',
              text: 'Not offered, because they are a record of where a '
                  + 'decision came from rather than somebody who can be '
                  + 'asked about it: '
                  + r.not_people.map((p) => p.name).join(', ') + '.' })
          : null,
      ].filter(Boolean)),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel',
                       onclick: closeModal }),
        el('button', { class: 'btn', text: 'Assign',
                       onclick: () => save(chosen) }),
      ]),
    ]));
  }

  async function archiveSet(st, on) {
    try {
      await apiPost('/api/curation/' + encodeURIComponent(st.gid) + '/'
                    + encodeURIComponent(st.kind) + '/archive',
                    { archived: on });
      // Change the list now rather than after a round trip.
      st.archived = on;
      // The whole panel, not just the list: the filter chips carry counts,
      // and archiving changes what those counts are counting.
      renderCuration();
      toast(on ? 'Archived. It is still there \u2014 the Archived filter '
                 + 'brings it back.'
               : 'Back in the list.', 'ok', 5000);
      loadCuration();
    } catch (e) { toast(e.message, 'err', 8000); }
  }


  /* Browse the bank and pick something, rather than being handed
     entries[0].

     Opens filtered to the kind being curated and searched for the recording
     picked above -- both clearable, because "show me what else is in here"
     is a reasonable thing to want and the old flow made it impossible.
     Resolves to the full entry, or null if cancelled. */


  async function bankSet(st) {
    const who = await askPath('Who is banking these?', 'your name or email',
                              BARRY.profile && BARRY.profile.who());
    if (!who) return;
    try {
      const res = await apiPost(
        '/api/curation/' + encodeURIComponent(st.gid) + '/'
        + encodeURIComponent(st.kind) + '/bank', { added_by: who });
      /* One entry for the whole set, with the mix in it. `x.label`
         was left over from the era of one entry per category and the
         route has never returned it, so this read
         "Banked 1 entry: undefined (416)". */
      const it = res.entries[0] || {};
      const names = it.label_names || {};
      const mix = Object.keys(it.by_label || {})
        .sort((a, b) => it.by_label[b] - it.by_label[a])
        .map((k) => (names[k] || k) + ' ' + it.by_label[k])
        .join(' \u00b7 ');
      toast('Banked as version ' + (it.version || 1) + ': '
            + (it.n || 0) + ' events \u2014 ' + mix, 'ok', 8000);
      BARRY.refreshSync();
    } catch (e) { toast(e.message, 'err', 8000); }
  }


  /* ==================================================================
     StrataScope
     ================================================================== */
  let strata = null;

  async function loadStrata() {
    const l = (q.tool === 'strata' && !strata)
      ? tkLoading('StrataScope', ['reading the layer sheets',
                                  'reading the recording registry'])
      : null;
    try {
      strata = await api('/api/layers');
      if (l) l.step('reading the recording registry');
      strata.registry = await api('/api/registry');
    } catch (e) {
      strata = { error: e.message, sheets: [], regions: [] };
    }
    renderStrata();
  }

  function renderStrata() {
    const host = $('#tkResult');
    if (!host) return;
    host.style.opacity = '1';
    host.innerHTML = '';
    if (!strata) {
      host.appendChild(el('div', { class: 'tk-loading' }, [
        stepLoader('StrataScope', ['reading the layer sheets',
                                   'reading the recording registry'])]));
      return;
    }

    const rows = ((strata.registry || {}).tree || [])
      .flatMap((p) => p.mice.flatMap((m) => m.sessions));
    // Same search field as the curation importer, for the same reason.
    let strataGid = (rows.find((r) => r.reachable) || rows[0] || {}).gid;
    const pick = BARRY.pickSession({
      rows, value: strataGid,
      placeholder: 'Which recording? Type a mouse, session or date…',
      onpick: (r) => { strataGid = r.gid; },
    });
    pick.id = 'strataPick';

    host.appendChild(el('div', { class: 'tk-head' }, [
      el('div', {}, [
        el('h2', { text: 'StrataScope' }),
        el('p', { class: 'sub',
          text: 'Which anatomical layer each channel is sitting in \u2014 '
              + 'labelled against the live voltage, CSD and theta rasters, so '
              + 'there is nothing to crop and the rows cannot drift off the '
              + 'channels.' }),
      ]),
      el('div', { class: 'spacer' }),
      pick,
      el('button', {
        class: 'btn', text: 'Open\u2026',
        disabled: rows.length ? null : 'disabled',
        onclick: () => {
          if (!strataGid) { toast('Pick a recording first.', 'err'); return; }
          BARRY.strata.enter(strataGid);
        },
      }),
    ]));

    const sheets = strata.sheets || [];
    if (!sheets.length) {
      host.appendChild(el('div', { class: 'hint tk-empty',
        text: 'No layer sheets yet. Pick a recording above and open it '
            + '\u2014 a sheet is made the first time.' }));
    } else {
      const list = el('div', { class: 'cur-sets' });
      for (const sh of sheets) {
        const pr = sh.progress || {};
        const reach = sh.session && sh.session.reachable;
        list.appendChild(el('div', {
          class: 'cur-set' + (pr.left === 0 && pr.total ? ' done' : ''),
        }, [
          el('div', { class: 'cur-set-top' }, [
            el('strong', { text: sh.session_label || sh.gid }),
            el('span', { class: 'hk-chip', text: 'layers' }),
            el('div', { style: 'flex:1' }),
            el('span', { class: 'cur-set-n',
              text: pr.labelled + ' / ' + pr.total + ' channels' }),
          ]),
          el('div', { class: 'cur-prog small' }, [
            el('i', { style: 'width:' + (pr.percent || 0) + '%' }),
          ]),
          el('div', { class: 'cur-set-tally' },
             (sh.regions || []).filter(
               (r) => (pr.by_region || {})[r.id]).map((r) => el('span', {
                 class: 'cur-tally', style: '--cat:' + r.color,
                 text: r.name + '  ' + pr.by_region[r.id],
               }))),
          el('div', { class: 'cur-set-acts' }, [
            el('button', {
              class: 'btn sm',
              text: pr.left ? 'Continue\u2026' : 'Review\u2026',
              disabled: reach ? null : 'disabled',
              onclick: () => BARRY.strata.enter(sh.gid),
            }),
            el('button', {
              class: 'btn ghost sm', text: 'Export CSV',
              onclick: () => window.open('/api/layers/'
                + encodeURIComponent(sh.gid) + '/export', '_blank'),
            }),
            el('button', {
              class: 'btn ghost sm danger', text: 'Delete',
              onclick: async () => {
                await apiPost('/api/layers/' + encodeURIComponent(sh.gid)
                              + '/delete', {});
                loadStrata();
              },
            }),
          ]),
        ]));
      }
      host.appendChild(list);
    }

    host.appendChild(el('div', { class: 'section-label', text: 'The layers' }));
    host.appendChild(el('div', { class: 'strata-legend' },
      (strata.regions || []).map((r) => el('span', {
        class: 'cur-tally', style: '--cat:' + r.color,
        title: r.note || '', text: r.name,
      }))));
  }

  /* ==================================================================
     Importing a folder of sorted snapshots
     ==================================================================
     Thousands of dentate spikes were sorted before BARRY existed, by
     dragging one PNG per candidate into a folder named after the decision.
     That work is real and nobody is redoing it, so this reads it back.

     Scan first, always. The images carry an event number but not a time, so
     the decisions are matched to banked candidates by position -- which is
     only safe when the counts agree exactly. The scan is where you see
     whether they do, per recording, before anything is written.
     ================================================================== */
  let snapRoot = '';
  let snapScan = null;
  let snapBusy = false;

  const VERDICT_NOTE = {
    ready: 'will import',
    empty: 'no snapshots in it',
    unparsed: 'cannot tell which recording',
    'no-bank': 'nothing banked to get times from',
    'count-mismatch': 'counts disagree',
    gappy: 'numbering has gaps',
    'no-gid': 'the banked entry has no recording id',
    unreadable: 'could not read the folder',
  };

  function renderSnapshots() {
    const host = $('#tkResult');
    if (!host) return;
    host.innerHTML = '';

    host.appendChild(el('div', { class: 'section-label',
                                 style: 'margin-top:0',
                                 text: 'The folder to read' }));
    const pathIn = el('input', {
      type: 'text', value: snapRoot, style: 'flex:1;min-width:0',
      placeholder: 'E:\\PTEN_DS_Curation\\Visualized_spikes_...',
      oninput: (e) => { snapRoot = e.target.value; },
    });
    host.appendChild(el('div', { class: 'row', style: 'gap:8px' }, [
      pathIn,
      el('button', { class: 'btn ghost sm', text: 'Browse\u2026',
        onclick: async () => {
          const d = await pickPath('folder', snapRoot);
          if (d) { snapRoot = d; renderSnapshots(); }
        } }),
      el('button', {
        class: 'btn', text: snapBusy ? 'Scanning\u2026' : 'Scan',
        disabled: snapBusy ? 'disabled' : null,
        onclick: async () => {
          if (!snapRoot.trim()) { toast('Point it at a folder first.', 'err'); return; }
          snapBusy = true; renderSnapshots();
          try {
            snapScan = await apiPost('/api/dsimport/scan', { root: snapRoot });
          } catch (e) {
            snapScan = null;
            toast(e.message, 'err', 9000);
          } finally { snapBusy = false; renderSnapshots(); }
        } }),
    ]));

    host.appendChild(el('p', { class: 'hint',
      text: 'Each recording is a folder of numbered snapshots with '
          + 'Dentate Spike / Garbage / Flag / Flag for Deep Review inside '
          + 'it. Scanning writes nothing \u2014 it reports what would '
          + 'happen, per recording, so you can check it before it does.' }));

    if (!snapScan) return;

    const sum = snapScan.summary || {};
    const ready = (snapScan.rows || []).filter((r) => r.verdict === 'ready');
    host.appendChild(el('div', { class: 'rb-verdict '
      + (ready.length ? 'ok' : 'missing') }, [
      el('div', { class: 'rb-verdict-top' }, [
        el('strong', { text: ready.length + ' of ' + (sum.folders || 0)
                           + ' folders ready to import' }),
      ]),
      el('p', { text: [
        sum.events_spike ? sum.events_spike + ' dentate spikes' : null,
        sum.events_garbage ? sum.events_garbage + ' garbage' : null,
        sum.events_flag ? sum.events_flag + ' flagged' : null,
        sum.events_review ? sum.events_review + ' for deep review' : null,
        sum.events_undecided ? sum.events_undecided + ' still undecided' : null,
      ].filter(Boolean).join('  \u00b7  ') }),
      sum.conflicts ? el('p', { class: 'warn-line',
        text: sum.conflicts + ' snapshot(s) were filed under two different '
            + 'decisions. Those come in flagged, with a note saying which '
            + 'two, so they get looked at rather than guessed.' }) : null,
    ]));

    const table = el('table', { class: 'tk-table' });
    table.appendChild(el('thead', {}, [el('tr', {}, [
      el('th', { text: 'Folder' }), el('th', { text: 'Recording' }),
      el('th', { text: 'Events' }), el('th', { text: 'How they were sorted' }),
      el('th', { text: '' }),
    ])]));
    const body = el('tbody');
    for (const r of (snapScan.rows || [])) {
      const t = r.tally || {};
      const bits = [['spike', 'spikes'], ['garbage', 'garbage'],
                    ['flag', 'flagged'], ['review', 'deep review'],
                    ['undecided', 'undecided']]
        .filter(([k]) => t[k]).map(([k, name]) => t[k] + ' ' + name);
      body.appendChild(el('tr', { class: r.verdict === 'ready' ? '' : 'dim' }, [
        el('td', { text: r.folder }),
        el('td', { text: r.session_label || '\u2014',
                   title: r.gid || '' }),
        el('td', { text: String(r.n_images == null ? '' : r.n_images) }),
        el('td', { text: bits.join(', ')
                       + (r.conflicts && r.conflicts.length
                          ? '   (' + r.conflicts.length + ' conflicting)' : '') }),
        el('td', {}, [el('span', {
          class: 'flagchip' + (r.verdict === 'ready' ? ' good' : ' bad'),
          text: VERDICT_NOTE[r.verdict] || r.verdict,
          title: r.reason || '',
        })]),
      ]));
    }
    table.appendChild(body);
    host.appendChild(el('div', { class: 'tk-table-wrap' }, [table]));

    if (!ready.length) return;
    host.appendChild(el('div', { class: 'row', style: 'gap:8px;margin-top:10px' }, [
      el('p', { class: 'hint', style: 'flex:1',
        text: 'Importing replaces any curation set those recordings already '
            + 'have, because this is the record of a sort that already '
            + 'happened rather than something to merge into a half-finished '
            + 'one.' }),
      el('button', {
        class: 'btn', text: 'Import ' + ready.length + ' recording(s)',
        disabled: snapBusy ? 'disabled' : null,
        onclick: async () => {
          snapBusy = true; renderSnapshots();
          try {
            const res = await apiPost('/api/dsimport/apply',
                                      { token: snapScan.token });
            const nEv = (res.imported || [])
              .reduce((a, x) => a + (x.n || 0), 0);
            toast('Imported ' + (res.imported || []).length + ' recording(s), '
                  + nEv + ' candidates. Open Event curation to review the '
                  + 'flagged ones.', 'ok', 9000);
            BARRY.activity.log('dsimport.apply',
                               { folders: (res.imported || []).length, n: nEv });
            await loadCuration();
          } catch (e) {
            toast(e.message, 'err', 10000);
          } finally { snapBusy = false; renderSnapshots(); }
        } }),
    ]));
  }

  function renderResult() {
    /* Undim first, whatever branch this takes. Every early return below used
       to skip the line that reset it. */
    const box = document.getElementById('tkResult');
    if (box) box.style.opacity = '1';
    if (q.tool === 'kilosort') {
      const host = document.getElementById('tkResult');
      if (host && !host.dataset.ks) {
        host.dataset.ks = '1';
        BARRY.kilosort.load(host);
      }
      return;
    }
    if (q.tool === 'curate') {
      // Reload rather than repaint when something has changed since this
      // was last read -- which is the whole of "why do I have to refresh".
      if (!cur || curStale) loadCuration();
      else renderCuration();
      return;
    }
    if (q.tool === 'strata') { renderStrata(); return; }
    if (q.tool === 'snapshots') { renderSnapshots(); return; }
    const host = $('#tkResult');
    if (!host) return;
    host.style.opacity = '1';
    host.innerHTML = '';

    if (!preview) {
      host.appendChild(el('div', { class: 'tk-loading' }, [
        stepLoader('Bad channels',
                   ['reading every recording that has marks'])]));
      return;
    }
    if (preview.error) {
      host.appendChild(el('div', { class: 'rb-verdict missing' }, [
        el('div', { class: 'rb-verdict-top' }, [
          el('span', { class: 'rb-dot missing' }),
          el('strong', { text: 'That scope does not work' }),
        ]),
        el('p', { style: 'margin:0;font-size:12px', text: preview.error }),
      ]));
      return;
    }

    const sm = preview.summary || {};
    host.appendChild(el('div', { class: 'tk-head' }, [
      el('div', {}, [
        el('h2', { text: 'Bad channels' }),
        el('p', { class: 'sub', text: preview.scope_label || '' }),
      ]),
      el('div', { class: 'spacer' }),
      el('button', {
        class: 'btn', text: 'Download CSV',
        disabled: preview.rows.length ? null : 'disabled',
        title: preview.rows.length
          ? 'Also filed under Results/ToolKit'
          : 'Nothing to export in this scope',
        onclick: download,
      }),
    ]));

    host.appendChild(el('div', { class: 'stat-row' }, [
      chip(sm.sessions + ' session' + (sm.sessions === 1 ? '' : 's'), 'good'),
      chip(sm.with_bad + ' with something marked',
           sm.with_bad ? 'warn' : null),
      chip(sm.clean + ' with nothing marked'),
      chip(sm.bad_total + ' bad channel'
           + (sm.bad_total === 1 ? '' : 's') + ' in total'),
      chip(sm.distinct_channels + ' distinct channel number'
           + (sm.distinct_channels === 1 ? '' : 's')),
      sm.first_day ? chip(sm.first_day + ' → ' + sm.last_day) : null,
    ].filter(Boolean)));

    // A channel that goes bad in several sessions is usually a wire, not a
    // recording -- which is a different problem, so it gets said out loud.
    const rep = sm.repeat_offenders || [];
    if (rep.length) {
      host.appendChild(el('div', { class: 'tk-repeat' }, [
        el('strong', { text: 'Bad more than once: ' }),
        el('span', { text: rep.map((r) => 'CSC ' + r.channel
                     + ' (' + r.sessions + ')').join(',  ') }),
        el('p', { class: 'hint', style: 'margin:4px 0 0',
          text: 'A channel that keeps coming up is worth checking at the '
              + 'headstage rather than in the analysis.' }),
      ]));
    }

    if (!preview.rows.length) {
      host.appendChild(el('div', { class: 'hint tk-empty',
        text: 'No bad channels are marked in ' + (preview.scope_label || 'this scope')
            + '. Mark them on the channel list in Xplorefinder and they will '
            + 'appear here.' }));
      return;
    }

    host.appendChild(table(preview.columns, preview.rows));
  }

  function chip(text, kind) {
    return el('span', { class: 'stat-chip' + (kind ? ' ' + kind : ''), text });
  }

  function table(cols, rows) {
    // Wide tables scroll inside their own box; the page must not.
    const wrap = el('div', { class: 'tk-tablewrap' });
    const t = el('table', { class: 'res-table tk-table' });
    t.appendChild(el('thead', {}, [el('tr', {}, cols.map((c) =>
      el('th', { text: c.replace(/_/g, ' ') })))]));
    const body = el('tbody');
    // A cap on what is drawn, not on what is exported: 4000 rows of DOM is
    // slow to build and nobody reads past the first screen anyway.
    const CAP = 500;
    for (const r of rows.slice(0, CAP)) {
      body.appendChild(el('tr', {}, cols.map((c) => el('td', {
        text: r[c] === null || r[c] === undefined ? '' : String(r[c]),
        title: c === 'path' ? String(r[c] || '') : null,
        class: c === 'channel' || c === 'bad_channels' ? 'tk-ch' : null,
      }))));
    }
    t.appendChild(body);
    wrap.appendChild(t);
    if (rows.length > CAP) {
      wrap.appendChild(el('p', { class: 'hint',
        text: 'Showing the first ' + CAP + ' of ' + rows.length
            + ' rows. The download has all of them.' }));
    }
    return wrap;
  }

  /* ---------- the download ---------- */
  async function download() {
    const url = '/api/toolkit/bad-channels/export?' + args();
    try {
      const res = await fetch(url);
      if (!res.ok) {
        let msg = 'HTTP ' + res.status;
        try { msg = (await res.json()).error || msg; } catch (e) { /* text */ }
        toast(msg, 'err', 8000);
        return;
      }
      const blob = await res.blob();
      const name = (res.headers.get('Content-Disposition') || '')
        .replace(/.*filename="?([^"]+)"?.*/, '$1') || 'bad-channels.csv';
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);

      const rel = res.headers.get('X-Barry-Output');
      toast((res.headers.get('X-Barry-Rows') || '?') + ' rows downloaded'
            + (rel ? ' — also filed at Results/' + rel : ''), 'ok', 7000);
      BARRY.activity.log('toolkit.bad_channels.export', {
        scope: q.scope, form: q.form, rows: res.headers.get('X-Barry-Rows'),
        run: res.headers.get('X-Barry-Run-Id'),
      });
      BARRY.refreshSync();
    } catch (e) {
      toast('Export failed: ' + e.message, 'err', 8000);
    }
  }

  function init() {
    const r = $('#tkRefresh');
    if (r) {
      r.addEventListener('click', async () => {
        scopes = null;
        await loadScopes();
        refresh();
      });
    }
  }

  return {
    init, onShow, refresh,
    /* For web/_dev/presence.html, which drives the real workbench rather
       than a copy: it needs to hand in a known set of sessions and ask what
       the bench makes of them. */
    _presence: (got) => { if (got) presence = got; renderCuration(); },
    _heldBy: (st) => heldBy(st),
    _loadPresence: (andRender) => loadPresence(andRender),
    /* Curation calls this when it changes something. Cheap on purpose: it
       marks the cache stale rather than refetching, because the tool is not
       on screen while somebody is curating and a fetch per keystroke is
       exactly the kind of thing that made the queue back up. */
    curationChanged: () => { curStale = true; },
    /* Drop what each pane has cached, so the loading path can be exercised
       on a second visit. Only web/_dev/tkload.html uses this. */
    debugForget: () => { preview = null; cur = null; strata = null; },
  };
})();
