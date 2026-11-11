/* ==========================================================================
   extraction.js -- The Extraction Room (web/extraction.html), the sixth and
   last step of The Dentist (asked 2026-11-10).

   "A different tab open, like the Monolith. The first tab is the Dentate
   Spike: the CSD view and the depth profiles, toggleable between the mean
   sink and the mean source -- for the mean sink keep the delta. And the %KO
   for each PTEN mouse as a chip next to it, 0% for the controls."

   WHAT IS ON SHOW. One version of a room: X-ray Many's bundles of one
   folder, extracted (backend/extraction.py). Per recording, per class:
     the CSD      the class's mean CSD down the whole shank, -50 to +50 ms
                  around the stamp (5-100 Hz, 60 Hz notched);
     the profile  the class's depth profile at the box's time, mean and SEM;
     the sink     its strongest sink in the box, and the DELTA -- the
                  distance between its two largest sinks, per event, as
                  X-ray's delta method measures it;
     the source   its strongest source in the box.
   "Mean sink" and "mean source" switch what both pictures point at and
   which numbers are said. Nothing here computes a number the room was not
   given, except where to draw a mark.

   Stand-alone, like the Monolith's page: no app scripts, its own fetch, so
   it opens in its own tab and stays open while Jarvis does other things.
   ========================================================================== */
'use strict';

(function () {
  const TABS = [['dentate_spike', 'Dentate Spike']];
  const S = {
    room: 'dentate_spike', rooms: null, folders: [], ko: {},
    art: null, version: null, pay: null,
    mode: 'sink',          // 'sink' | 'source'
    show: 'both',          // 'both' | 'csd' | 'profile'
    /* One scale for every recording, so they compare (2026-11-10: "fix the
       x axis of the depth profiles globally, and the colour scale of the
       CSDs"); 'own' gives each recording its own. */
    scale: 'same',
    flips: {},             // gid -> {flip, at, by}: DS1 and DS2 swapped by hand
    seps: {},              // gid -> {verdict: 'yes'|'no', at, by}: separable, by hand
    onlySep: false,        // the measures from the separable recordings only
    // Does it differ?
    cmp: 'two',            // 'two' (CTL vs PTEN) | 'three' (CTL / Low / High) | 'ko'
    /* SUB-TABS (2026-11-10: "make all the tabs, sub tabs"): the recordings,
       Round I, the separation rate, Round II and the numbers, each its own. */
    sub: 'recordings',
    tests: 'usual',        // 'usual' (one test, picked by the residuals) | 'strict'
    folder: null,          // the set on show: the X-ray Many folder it was extracted from
    knownV: 0,             // the room's newest version when last asked
    r2: null, r2Err: null, r2Gen: 0,
    split: 10, minN: 5, skip: new Set(), stats: null, statsErr: null, statsGen: 0,
    busy: null, err: null, fetch: null,
  };
  const live = [];         // canvases to draw again when their width changes

  /* ---------- small things ---------- */
  function el(tag, attrs, kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'text') n.textContent = v;
      else if (k === 'class') n.className = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? '' : v);
    }
    for (const c of [].concat(kids || [])) if (c) n.appendChild(c);
    return n;
  }
  const tok = (name, fb) => (getComputedStyle(document.documentElement)
    .getPropertyValue(name) || fb || '').trim() || fb;
  const fmt = (v, d) => (v == null || !isFinite(v) ? '—' : Number(v).toFixed(d == null ? 3 : d));
  const sgn = (v, d) => (v == null || !isFinite(v) ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(d == null ? 3 : d));
  const koNow = (r) => (r.ko_now !== undefined ? r.ko_now : r.ko_pct);

  async function api(url, opt) {
    const f = S.fetch || window.fetch.bind(window);
    const r = await f(url, opt);
    let j = null;
    try { j = await r.json(); } catch (e) { /* below */ }
    if (!r.ok || !j || j.ok === false) throw new Error((j && j.error) || ('HTTP ' + r.status));
    return j;
  }
  const post = (u, b) => api(u, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                  body: JSON.stringify(b || {}) });

  /* ---------- loading ---------- */
  /* `version`, or the newest of `folder`'s set, or of the set on show,
     or the newest in the room. */
  async function load(version, folder) {
    S.err = null;
    try {
      const idx = await api('/api/extraction');
      S.rooms = idx.rooms || [];
      S.folders = idx.folders || [];
      S.ko = idx.ko || {};
      const room = S.rooms.find((r) => r.room === S.room) || {};
      S.art = room.artifact_id ? room : null;
      S.knownV = topOf(room);
      if (S.art) {
        let v = version;
        if (v == null) {
          const want = folder || S.folder;
          const mine = want ? (S.art.versions || []).filter((x) => setOf(x) === want) : [];
          v = mine.length ? Math.max(...mine.map((x) => x.v)) : S.art.version;
        }
        const got = await api('/api/extraction/' + encodeURIComponent(S.art.artifact_id)
                              + '?version=' + encodeURIComponent(v));
        S.pay = got.payload;
        S.version = got.version;
        S.flips = got.flips || {};
        S.seps = got.seps || {};
        S.folder = ((S.pay || {}).source || {}).folder || null;
        // Round II was of the version before: asked again when it is shown.
        S.r2 = null; S.r2Err = null;
      } else {
        S.pay = null; S.version = null;
      }
    } catch (e) {
      S.err = e.message;
    }
    render();
    if (S.pay) loadStats();
  }

  /* THE SETS (2026-11-11: "I ran the 10% DS stuff, but it's not showing up
     in the Extraction Room"). Each X-ray Many folder extracted is a set of
     its own -- its own versions, its own calls -- picked at the top; a
     folder with X-ray results not in the room yet says so, with the press
     that takes them. And the room notices a new extraction made elsewhere:
     the ToolKit says so the moment it extracts, and the room asks again
     whenever it is looked at. */
  const setOf = (v) => v.folder_id || ((S.folders.find((f) => f.name === v.folder) || {}).id);
  const topOf = (room) => Math.max(0, ...((room || {}).versions || []).map((v) => v.v || 0));
  let lastPoll = 0;
  async function poll(force) {
    if (S.busy || !S.rooms || (!force && Date.now() - lastPoll < 2500)) return;
    lastPoll = Date.now();
    let idx;
    try { idx = await api('/api/extraction'); } catch (e) { return; }
    const room = (idx.rooms || []).find((r) => r.room === S.room) || {};
    const top = topOf(room);
    if (top > S.knownV) {
      const v = (room.versions || []).find((x) => x.v === top) || {};
      S.note = 'Opened v' + top + ', ‘' + (v.folder || '?') + '’, extracted' + (v.at ? ' ' + new Date(v.at).toLocaleString() : '')
        + (v.by ? ' by ' + v.by : '') + ': the newest in the room.';
      await load(top);
      return;
    }
    S.folders = idx.folders || [];
    S.rooms = idx.rooms || [];
    const box = document.getElementById('erSource');
    if (box) box.replaceWith(sourceCard());
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
  window.addEventListener('focus', () => poll());
  try {
    const bc = new BroadcastChannel('barry-extraction');
    bc.onmessage = (e) => {
      const m = e.data || {};
      if (m.type !== 'extracted' || (m.room || 'dentate_spike') !== S.room || S.busy) return;
      S.note = 'Opened v' + m.version + ', just extracted' + (m.folder_name ? ' from ‘' + m.folder_name + '’' : '') + '.';
      load(m.version);
    };
  } catch (e) { /* no BroadcastChannel: the room still asks when looked at */ }

  /* Does it differ? Asked of the server, which applies the swaps and the
     %KO as they stand now: every metric is one number per recording. */
  async function loadStats() {
    if (!S.art) return;
    const mine = ++S.statsGen;
    try {
      const got = await post('/api/extraction/stats', {
        artifact_id: S.art.artifact_id, version: S.version, split: S.split,
        min_n: S.minN, skip: Array.from(S.skip), only_sep: S.onlySep });
      if (mine !== S.statsGen) return;
      S.stats = got; S.statsErr = null;
    } catch (e) {
      if (mine !== S.statsGen) return;
      S.statsErr = e.message;
    }
    putStats();
  }

  /* Round II: a wide, plain look (backend/extraction.py `round2`). */
  async function loadRound2() {
    if (!S.art) return;
    const mine = ++S.r2Gen;
    try {
      const got = await post('/api/extraction/round2', {
        artifact_id: S.art.artifact_id, version: S.version, split: S.split,
        skip: Array.from(S.skip) });
      if (mine !== S.r2Gen) return;
      S.r2 = got; S.r2Err = null;
    } catch (e) {
      if (mine !== S.r2Gen) return;
      S.r2Err = e.message;
    }
    putStats();
  }
  /* Everything the stats read has changed: ask both again. */
  function restat() { loadStats(); if (S.r2 || S.sub === 'round2') loadRound2(); }

  /* Which is DS1, by hand: the swap is shared, and the room shows and
     counts it at once; the extracted numbers are not touched. */
  async function setFlip(r, on) {
    try {
      const got = await post('/api/extraction/flip', { room: S.room, folder: S.folder, gid: r.gid, flip: !!on });
      S.flips = got.flips || {};
    } catch (e) { window.alert('Not swapped: ' + e.message); return; }
    render();
    restat();
  }

  const flipped = (r) => !!(S.flips[r.gid] && S.flips[r.gid].flip);

  /* SEPARABLE OR NOT, BY HAND (2026-11-10: "I meant swap the not separable
     / separable"): X-ray's two-vs-one test and its 10% rule are a rule; a
     person looking at the two CSDs is the judge. Shared, and counted. */
  function sepOf(r) {
    const o = S.seps[r.gid];
    if (o && (o.verdict === 'yes' || o.verdict === 'no')) {
      return { verdict: o.verdict, byHand: true, by: o.by, at: o.at };
    }
    return { verdict: (r.separation || {}).verdict, byHand: false };
  }
  async function setSep(r, verdict) {
    try {
      const got = await post('/api/extraction/sep', { room: S.room, folder: S.folder, gid: r.gid, verdict });
      S.seps = got.seps || {};
    } catch (e) { window.alert('Not saved: ' + e.message); return; }
    render();
    restat();
  }
  /* The classes as they are called: swapped, X-ray's DS1 is shown, drawn
     and counted as DS2. Copies. */
  function shownClasses(r) {
    const f = flipped(r);
    return (r.classes || []).map((c) => Object.assign({}, c, {
      shown: f && (c.c === 1 || c.c === 2) ? 3 - c.c : c.c,
      name: 'DS' + (f && (c.c === 1 || c.c === 2) ? 3 - c.c : c.c) }))
      .sort((a, b) => a.shown - b.shown);
  }
  const colOf = (c) => tok(c.shown === 1 ? '--ds1' : '--ds2');
  const softOf = (c) => tok(c.shown === 1 ? '--ds1-soft' : '--ds2-soft');

  async function extract(folder) {
    if (S.busy) return;
    S.busy = 'Extracting… each recording is refitted from its read, a few seconds each.';
    render();
    try {
      const got = await post('/api/extraction/extract', { room: S.room, folder });
      S.busy = null;
      S.note = 'Extracted ' + got.n + ' recording' + (got.n === 1 ? '' : 's') + ' as v' + got.version
        + ((got.left || []).length ? '; left out: ' + got.left.map((x) => x.session_label + ' (' + x.why + ')').join('; ') : '') + '.';
      await load(got.version);
    } catch (e) {
      S.busy = null;
      S.err = 'Not extracted: ' + e.message;
      render();
    }
  }

  async function setKo(r) {
    if (String(r.group || '').toUpperCase() === 'CTL') return;
    const was = koNow(r);
    const said = window.prompt('%KO for ' + r.mouse_key.replace(/^[^|]*\|/, '') + ' (0 to 100). '
                               + 'Shared with everybody; leave empty to clear it.', was == null ? '' : String(was));
    if (said === null) return;
    const pct = said.trim() === '' ? null : Number(said);
    if (pct !== null && !(isFinite(pct) && pct >= 0 && pct <= 100)) { window.alert('%KO is a number from 0 to 100.'); return; }
    try {
      const got = await post('/api/extraction/ko', { mouse_key: r.mouse_key, pct });
      S.ko = got.ko || S.ko;
      for (const x of (S.pay && S.pay.recordings) || []) {
        if (x.mouse_key === r.mouse_key) x.ko_now = pct;
      }
      render();
      restat();
    } catch (e) { window.alert('Not saved: ' + e.message); }
  }

  /* ---------- the page ---------- */
  function render() {
    const tabs = document.getElementById('erTabs');
    tabs.innerHTML = '';
    for (const [id, name] of TABS) {
      tabs.appendChild(el('button', { role: 'tab', 'aria-selected': String(id === S.room), text: name,
        onclick: () => { if (S.room !== id) { S.room = id; load(); } } }));
    }
    const body = document.getElementById('erBody');
    body.innerHTML = '';
    live.length = 0;
    if (S.err) body.appendChild(el('p', { class: 'err', text: S.err }));
    body.appendChild(sourceCard());
    if (!S.pay) {
      body.appendChild(el('p', { class: 'empty', text: S.rooms == null ? 'Opening the room…'
        : 'Nothing has been extracted into this room yet. Press Extract on an X-ray Many folder above.' }));
      return;
    }
    body.appendChild(subTabs());
    if (S.sub === 'recordings') {
      body.appendChild(controls());
      body.appendChild(legend());
      body.appendChild(stateKey());
      const grid = el('div', { class: 'grid', id: 'erGrid' });
      for (const r of S.pay.recordings || []) grid.appendChild(card(r));
      body.appendChild(grid);
    } else if (S.sub === 'stats') {
      body.appendChild(el('div', { id: 'erStats' }, [statsCard()]));
    } else if (S.sub === 'seprate') {
      body.appendChild(el('div', { id: 'erSepRate' }, [sepRateCard()]));
    } else if (S.sub === 'round2') {
      body.appendChild(el('div', { id: 'erRound2' }, [round2Card()]));
      if (!S.r2 && !S.r2Err) loadRound2();
    } else {
      body.appendChild(numbers());
    }
    requestAnimationFrame(drawAll);
    setTimeout(drawAll, 60);
  }

  const SUBS = [['recordings', 'Recordings'], ['stats', 'Round I · does it differ?'],
                ['seprate', 'Separation rate'], ['round2', 'Round II'], ['numbers', 'The numbers']];
  function subTabs() {
    return el('div', { class: 'subtabs', role: 'tablist', id: 'erSubs' }, SUBS.map(([id, name]) => el('button', {
      role: 'tab', 'aria-selected': String(id === S.sub), text: name, 'data-sub': id,
      onclick: () => { if (S.sub !== id) { S.sub = id; render(); } } })));
  }

  /* Only the stats parts, in place, when an answer arrives. */
  function putStats() {
    for (let i = live.length - 1; i >= 0; i--) if (live[i].stats) live.splice(i, 1);
    const put = (id, make) => {
      const box = document.getElementById(id);
      if (!box) return;
      box.innerHTML = '';
      box.appendChild(make());
    };
    put('erStats', statsCard);
    put('erSepRate', sepRateCard);
    put('erRound2', round2Card);
    requestAnimationFrame(drawAll);
    setTimeout(drawAll, 60);
  }

  function sourceCard() {
    const pay = S.pay;
    const src = (pay && pay.source) || {};
    const kids = [];
    const fs = S.folders.filter((f) => !f.archived && (f.bundles || f.in_room));
    const inRoom = fs.filter((f) => f.in_room);
    // The set on show, though its folder has since been archived or gone.
    if (pay && S.folder && !inRoom.some((f) => f.id === S.folder)) {
      inRoom.push({ id: S.folder, name: src.folder_name || S.folder, in_room: { v: S.version }, new: 0 });
    }
    const waiting = fs.filter((f) => !f.in_room && f.bundles);
    kids.push(el('div', { class: 'bar' }, [
      el('div', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Set' }),
        inRoom.length
          ? el('div', { class: 'seg', id: 'erSets' }, inRoom.map((f) => el('button', {
            'aria-pressed': String(f.id === S.folder), 'data-folder': f.id,
            text: f.name + ' · v' + f.in_room.v + (f.new ? ' · ' + f.new + ' new' : ''),
            title: 'X-ray Many’s ‘' + f.name + '’, extracted' + (f.in_room.at ? ' ' + new Date(f.in_room.at).toLocaleString() : '')
              + (f.in_room.by ? ' by ' + f.in_room.by : '') + '. Each set has its own versions and its own calls.',
            onclick: () => { if (f.id !== S.folder) { S.note = null; load(null, f.id); } } })))
          : el('span', { class: 'muted small', text: 'nothing extracted yet' })]),
    ].concat(waiting.map((f) => el('button', { class: 'btn primary er-take', 'data-folder': f.id, disabled: !!S.busy,
      text: 'Extract ‘' + f.name + '’ · ' + f.bundles + ' X-ray result' + (f.bundles === 1 ? '' : 's') + ', not in the room yet',
      title: 'The newest X-ray bundle of every recording in it, as a set of its own in this room.',
      onclick: () => extract(f.id) })))));
    if (pay) {
      kids.push(el('p', {}, [el('b', { text: 'Extracted from X-ray Many · ‘' + (src.folder_name || src.folder) + '’' }),
        el('span', { class: 'muted', text: ' · ' + (pay.recordings || []).length + ' recordings · events inside ‘'
          + ((src.workflow || {}).nickname || '') + '’ v' + ((src.workflow || {}).version || '') + ' · %KO: ' + (pay.ko_from || '') }) ]));
    }
    const cur = fs.find((f) => f.id === S.folder);
    if (cur && cur.new && pay) {
      kids.push(el('p', { class: 'notice', id: 'erNew' }, [
        el('span', { text: cur.new + ' X-ray result' + (cur.new === 1 ? '' : 's') + ' in ‘' + cur.name + '’ '
          + (cur.new === 1 ? 'is' : 'are') + ' newer than this set’s v' + cur.in_room.v + '. ' }),
        el('button', { class: 'btn small', text: 'Extract them', disabled: !!S.busy, onclick: () => extract(cur.id) })]));
    }
    const vs = ((S.art && S.art.versions) || []).filter((v) => setOf(v) === S.folder);
    kids.push(el('div', { class: 'bar' }, [
      vs.length ? el('div', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Version' }),
        el('select', { id: 'erVersion', onchange: (e) => load(Number(e.target.value)) },
          vs.slice().reverse().map((v) => el('option', { value: String(v.v), selected: v.v === S.version,
            text: 'v' + v.v + (v.n != null ? ' · ' + v.n + ' recordings' : '')
                  + (v.at ? ' · ' + new Date(v.at).toLocaleString() : '') + (v.by ? ' · ' + v.by : '') })))]) : null,
      pay ? el('button', { class: 'btn', id: 'erExtract', disabled: !!S.busy, text: 'Extract again',
        title: 'Takes the newest X-ray bundle of every recording in ‘' + (src.folder_name || '') + '’ into this set, as its '
               + 'next version. The versions before stay.',
        onclick: () => extract(S.folder) }) : null,
    ]));
    if (S.busy) kids.push(el('p', { class: 'muted small', text: S.busy }));
    if (S.note) kids.push(el('p', { class: 'small er-note', text: S.note }));
    if (pay && (pay.left_out || []).length) {
      kids.push(el('p', { class: 'small', text: 'Left out: ' + pay.left_out.map((x) => x.session_label + ' (' + x.why + ')').join('; ') + '.' }));
    }
    return el('div', { class: 'card', id: 'erSource' }, kids);
  }

  function seg(items, value, on, id) {
    return el('div', { class: 'seg', id }, items.map(([v, w, title]) => el('button', {
      'aria-pressed': String(v === value), text: w, title, onclick: () => on(v) })));
  }

  function controls() {
    return el('div', { class: 'card bar' }, [
      el('div', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Show the' }),
        seg([['sink', 'mean sink', 'Each class’s strongest sink in the box, and the delta: how far apart its two largest sinks are.'],
             ['source', 'mean source', 'Each class’s strongest source in the box.']],
            S.mode, (v) => { S.mode = v; render(); }, 'erMode')]),
      el('div', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Pictures' }),
        seg([['both', 'CSD and depth profile'], ['csd', 'CSD view'], ['profile', 'depth profiles']],
            S.show, (v) => { S.show = v; render(); }, 'erShow')]),
      el('div', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Scale' }),
        seg([['same', 'the same for every recording', 'One colour scale for every CSD and one x axis for every '
                + 'depth profile, so the recordings compare by eye.'],
             ['own', 'each its own', 'Each recording scaled to itself: its own shape is easier to read, the '
                + 'recordings are not comparable.']],
            S.scale, (v) => { S.scale = v; render(); }, 'erScale')]),
    ]);
  }

  function legend() {
    const sw = (c) => el('span', { class: 'sw', style: 'background:' + c });
    return el('div', { class: 'legend card' }, [
      el('span', {}, [sw(tok('--ds1')), document.createTextNode('DS1')]),
      el('span', {}, [sw(tok('--ds2')), document.createTextNode('DS2')]),
      el('span', { text: S.mode === 'sink'
        ? 'Mean sink: sinks in colour (blue), sources faded; the arrow is each class’s strongest sink in the box, '
          + 'the bracket its two largest sinks — the delta.'
        : 'Mean source: sources in colour (red), sinks faded; the arrow is each class’s strongest source in the box.' }),
      el('span', { text: 'The dashed lines are the box X-ray ran with: its depth band and its time.' }),
      el('span', { text: 'CSD in ' + (((S.pay || {}).recordings || [])[0] || {}).unit + '.' }),
    ]);
  }

  function koChip(r) {
    const ctl = String(r.group || '').toUpperCase() === 'CTL';
    const k = koNow(r);
    if (ctl) return el('span', { class: 'chip ko ctl', title: 'A control: 0% knocked out.', text: '0% KO' });
    if (k == null) {
      return el('span', { class: 'chip ko none', title: 'Not on the lab’s sheet. Click to set it.',
        text: '%KO not on the sheet', onclick: () => setKo(r) });
    }
    return el('span', { class: 'chip ko', text: (+k).toFixed(2).replace(/\.?0+$/, '') + '% KO',
      title: '%KO from the lab’s sheet (JB % hits)' + (r.ko_pct != null && r.ko_pct !== k
        ? '; it was ' + r.ko_pct + '% when extracted' : '') + '. Click to correct it, for everybody.',
      onclick: () => setKo(r) });
  }

  const SEP = { yes: 'separable', weak: 'weak', no: 'not separable', too_few: 'too few' };

  /* EACH CARD'S STATE, AT A GLANCE (2026-11-11: "make it super clear if
     something is left out of the stats, separable or not -- a light faint
     overlay on the card, and gray for left out"). Left out wins; then the
     call that counts: separable, not ("weak" is not), or too few to call. */
  function stateOf(r) {
    if (S.skip.has(r.gid)) return 'out';
    const v = sepOf(r).verdict;
    return v === 'yes' ? 'yes' : (v === 'no' || v === 'weak') ? 'no' : 'few';
  }
  const STATE = { yes: 'Separable', no: 'Not separable', few: 'Too few events to call · not in the separation rate',
                  out: 'Left out of the stats' };
  function stateKey() {
    const recs = (S.pay && S.pay.recordings) || [];
    const n = { yes: 0, no: 0, few: 0, out: 0 };
    for (const r of recs) n[stateOf(r)]++;
    const short = { yes: 'Separable', no: 'Not separable', few: 'Too few to call', out: 'Left out of the stats' };
    return el('div', { class: 'statekey card', id: 'erStateKey' }, [el('span', { class: 'lab', text: 'Cards' })]
      .concat(['yes', 'no', 'few', 'out'].map((k) => el('span', { class: 'k st-' + k, 'data-state': k }, [
        el('span', { class: 'sq' }), el('span', { text: short[k] + ' · ' + n[k] })]))));
  }

  function card(r) {
    const sep = r.separation || {};
    const sh = sepOf(r);
    const head = el('div', { class: 'rec-head' }, [
      el('h2', { text: r.session_label }),
      el('span', { class: 'chip', text: r.group || '?' }),
      koChip(r),
      r.ied != null && String(r.group).toUpperCase() !== 'CTL'
        ? el('span', { class: 'chip', text: r.ied ? 'IED' : 'no IED', title: 'From the lab’s sheet.' }) : null,
      el('span', { class: 'chip sepchip ' + (sh.verdict || '') + (sh.byHand ? ' byhand' : ''),
        text: (SEP[sh.verdict] || sh.verdict || '—') + (sh.byHand ? ' · by hand' : ''),
        title: (sh.byHand ? 'Called ' + SEP[sh.verdict] + ' by hand' + (sh.by ? ' by ' + sh.by : '')
                + (sh.at ? ' on ' + new Date(sh.at).toLocaleString() : '') + '. X-ray said ' + (SEP[sep.verdict] || sep.verdict)
                + '. ' : 'X-ray’s call. ')
               + 'Its test: ΔBIC ' + fmt(sep.dbic, 1) + ', the smaller class '
               + (sep.min_share != null ? Math.round(sep.min_share * 100) + '%' : '—') + ' of ' + (sep.n || r.n) + ' events.' }),
      el('span', { class: 'chip', text: r.n + ' events' }),
      flipped(r) ? el('span', { class: 'chip swapped', text: 'DS1 ↔ DS2 swapped by hand',
        title: 'X-ray called them the other way round; swapped' + (S.flips[r.gid].by ? ' by ' + S.flips[r.gid].by : '')
               + (S.flips[r.gid].at ? ' on ' + new Date(S.flips[r.gid].at).toLocaleString() : '') + '.' }) : null,
    ]);
    /* LET ME TOGGLE THE LABEL (2026-11-10: "because the math can be a bit
       off"): X-ray's naming rule is a rule, and a person who can see the
       two CSDs can see when it named them the wrong way round. */
    const acts = el('div', { class: 'acts' }, [
      el('button', { class: 'btn small er-sep',
        text: sh.verdict === 'yes' ? 'Call it not separable' : 'Call it separable',
        title: 'Your call over X-ray’s, for everybody: the stats below count it at once. X-ray’s own test is kept.',
        onclick: () => setSep(r, sh.verdict === 'yes' ? 'no' : 'yes') }),
      sh.byHand ? el('button', { class: 'btn small er-sep-back', text: 'Back to X-ray’s call',
        title: 'X-ray said ' + (SEP[sep.verdict] || sep.verdict) + '.', onclick: () => setSep(r, null) }) : null,
      el('button', { class: 'btn small er-flip', text: flipped(r) ? 'Put DS1 and DS2 back' : 'Swap DS1 ↔ DS2',
        title: flipped(r) ? 'Back to what X-ray called them.'
          : 'Call X-ray’s DS1 DS2 and its DS2 DS1, here and in the stats, for everybody. The extracted numbers are not changed.',
        onclick: () => setFlip(r, !flipped(r)) }),
      el('button', { class: 'btn small er-skip', text: S.skip.has(r.gid) ? 'Put back in the stats' : 'Leave out of the stats',
        title: 'For this look only: the stats below are worked out without it.',
        onclick: () => { if (S.skip.has(r.gid)) S.skip.delete(r.gid); else S.skip.add(r.gid); render(); restat(); } }),
    ]);
    const st = stateOf(r);
    const kids = [el('div', { class: 'state-tag' }, [el('span', { class: 'dot' }),
      el('span', { text: STATE[st] + (st !== 'out' && sh.byHand ? ' · your call' : '') })]), head, acts];
    if (S.show !== 'profile') {
      kids.push(el('div', { class: 'pics' }, shownClasses(r).map((c) => {
        const cv = el('canvas', { class: 'csd' });
        live.push(() => drawCsd(cv, r, c));
        return el('div', { class: 'pic' }, [
          el('div', { class: 'cap' }, [el('b', { text: c.name, style: 'color:' + colOf(c) }),
            el('span', { text: c.n + ' events' + (flipped(r) ? ' · X-ray’s DS' + c.c : '') })]), cv]);
      })));
    }
    if (S.show !== 'csd') {
      const cv = el('canvas', { class: 'prof' });
      live.push(() => drawProfile(cv, r));
      kids.push(el('div', { class: 'pic' }, [el('div', { class: 'cap' }, [
        el('span', { text: 'Depth profile at the box’s time, mean ± SEM' })]), cv]));
    }
    kids.push(values(r));
    return el('div', { class: 'card rec st-' + st, 'data-gid': r.gid, 'data-state': st }, kids);
  }

  function values(r) {
    const rows = [];
    for (const c of shownClasses(r)) {
      const label = el('b', { class: 'c' + c.shown, text: c.name });
      let words;
      if (S.mode === 'sink') {
        const s = c.sink || {}, d = c.delta || {};
        words = 'sink ' + sgn(s.value) + ' ± ' + fmt(s.sem) + ' at CSC' + (s.csc == null ? '—' : s.csc)
          + ' · Δ ' + fmt(d.contacts, 1) + ' ± ' + fmt(d.sem, 1) + ' contacts'
          + (d.um != null ? ' (' + fmt(d.um, 0) + ' ± ' + fmt(d.um_sem, 0) + ' µm)' : '');
      } else {
        const s = c.source || {};
        words = 'source ' + sgn(s.value) + ' ± ' + fmt(s.sem) + ' at CSC' + (s.csc == null ? '—' : s.csc);
      }
      rows.push(label, el('span', { class: 'num', text: words }));
    }
    return el('div', { class: 'vals' }, rows);
  }

  /* ---------- Does it differ? ----------
     (2026-11-10: "a chart / stat to see, after toggling, if there is a
     significant result: PTEN vs CTL, and then CTL, Low KO, High KO".) The
     server works every test out (backend/extraction.py `stats`), one number
     per recording, with the swaps and the %KO as they stand now. */
  const GROUPS = { two: ['CTL', 'PTEN'], three: ['CTL', 'Low KO', 'High KO'] };
  const GCOL = { CTL: '--g-ctl', PTEN: '--g-pten', 'Low KO': '--g-low', 'High KO': '--g-high' };
  const pw = (p) => (p == null ? '—' : p < 0.001 ? '< 0.001' : '= ' + String(Number((+p).toPrecision(2))));
  const sig = (p) => p != null && p < 0.05;

  /* THE USUAL TESTS, OR THE STRICT (2026-11-11: "are our stats a bit too
     strict? use something more common and forgiving for a low sample
     size"). Usual, the way most papers and Prism do it: one test per
     question, picked by whether the residuals look normal (Shapiro-Wilk) --
     Welch's t or Mann-Whitney; ANOVA with Tukey's pairs, or Kruskal-Wallis
     with Dunn's; Boschloo's exact test for a rate; nothing corrected across
     measures. Strict: both tests must agree, Fisher, and Round II's false
     discovery rate. backend/extraction.py works out both. */
  const TEST = { welch: 'Welch’s t-test', mwu: 'Mann–Whitney', anova: 'one-way ANOVA', kw: 'Kruskal–Wallis' };
  const POST = { tukey: 'Tukey', dunn: 'Dunn’s, Holm' };
  const usualOn = () => S.tests !== 'strict';

  /* THE DOSE (2026-11-11: "there's something wacky with the stats -- how is
     the first one significant? We want to show that it gets worse with PTEN
     KO"). Against %KO with the controls at 0% is mostly controls against
     PTEN: every control sits at one end, so a PTEN difference reads as a
     trend even when %KO predicts nothing among the PTEN mice. So against
     %KO asks among the PTEN mice alone, and says the other beside it. */
  const HIT = (v) => /^(differs|falls|rises)/.test(v);
  function doseWords(m) {
    const s = m.spearman || {}, d = m.dose || {};
    const verdict = d.p == null && s.p == null ? 'cannot tell'
      : sig(d.p) ? (d.rho < 0 ? 'falls as %KO rises' : 'rises with %KO')
      : sig(s.p) ? (s.rho < 0 ? 'lower in PTEN, no dose trend' : 'higher in PTEN, no dose trend')
      : 'no clear trend with %KO';
    const words = 'The dose, among the PTEN mice alone: Spearman ρ ' + (d.rho == null ? '—' : sgn(d.rho, 2)) + ' · p '
      + pw(d.p) + ' · n ' + (d.n || 0) + ' · all mice, the controls at 0%: ρ ' + (s.rho == null ? '—' : sgn(s.rho, 2))
      + ' · p ' + pw(s.p) + ' (mostly PTEN against controls)';
    return [verdict, words];
  }
  /* Who is left out, said wherever it changes the numbers. */
  function leftOut() {
    if (!S.skip.size) return null;
    const names = ((S.pay || {}).recordings || []).filter((r) => S.skip.has(r.gid)).map((r) => r.session_label);
    return el('p', { class: 'notice er-left', text: 'Left out of these stats: ' + names.join(', ') + '. Every number here '
      + 'is without ' + (names.length === 1 ? 'it' : 'them') + '; put them back on the Recordings tab.' });
  }
  const whyTest = (t) => (t.normal_p == null ? ''
    : t.test === 'welch' || t.test === 'anova'
      ? ' (the residuals look normal, Shapiro–Wilk p ' + pw(t.normal_p) + ')'
      : ' (the residuals are not normal, Shapiro–Wilk p ' + pw(t.normal_p) + ', so ranks)');

  function unitOf(m) {
    if (m.unit === 'um') return 'µm';
    if (m.unit === 'uV') return 'µV';
    if (m.unit === '/min' || m.unit === 'dB' || m.unit === 'ms') return m.unit === '/min' ? 'events per minute' : m.unit;
    if (m.unit === 'ratio') return '×';
    if (m.unit === 'share') return '';
    return (((S.pay || {}).recordings || [])[0] || {}).unit || '';
  }
  const showV = (m, v) => (v == null ? '—' : m.unit === 'share' ? Math.round(v * 100) + '%'
    : (m.unit === 'um' || m.unit === 'uV') ? fmt(v, 0)
    : (m.unit === '/min' || m.unit === 'dB' || m.unit === 'ms') ? fmt(v, 2)
    : fmt(v, m.unit === 'ratio' ? 2 : 3));

  function cmpControls() {
    return [
      el('div', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Compare' }),
        seg([['two', 'PTEN vs CTL'], ['three', 'CTL · Low KO · High KO'], ['ko', 'against %KO']],
            S.cmp, (v) => { S.cmp = v; putStats(); }, 'erCmp')]),
      el('div', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Tests' }),
        seg([['usual', 'the usual ones', 'One test per question, the way most papers (and Prism) do it, for small groups: '
                + 'Welch’s t-test, or Mann–Whitney when the residuals are not normal (Shapiro–Wilk); one-way ANOVA with '
                + 'Tukey’s pairs, or Kruskal–Wallis with Dunn’s; Boschloo’s exact test for a rate. Nothing corrected '
                + 'across measures.'],
             ['strict', 'strict', 'Both tests must agree (Welch and Mann–Whitney; ANOVA and Kruskal–Wallis), pairs by '
                + 'Mann–Whitney with Holm, Fisher’s exact test for a rate, and Round II’s false discovery rate.']],
            S.tests, (v) => { S.tests = v; putStats(); }, 'erTests')]),
      S.cmp === 'three' ? el('div', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Low KO is under' }),
        el('input', { type: 'number', id: 'erSplit', min: '0', max: '100', step: '0.5', value: String(S.split),
          class: 'numin', onchange: (e) => { const v = Number(e.target.value);
            if (isFinite(v)) { S.split = v; restat(); } } }), el('span', { class: 'small', text: '% KO' })]) : null,
    ];
  }

  function statsCard() {
    const st = S.stats;
    const kids = [
      el('div', { class: 'bar' }, [el('h2', { text: 'Round I · does it differ?' }),
        el('span', { class: 'muted small', text: 'One number per recording, and each recording is one mouse: a mouse '
          + 'with 700 events counts once, like one with 60. Worked out again after every swap and %KO correction.' })]),
      leftOut(),
      el('div', { class: 'bar' }, cmpControls().concat([
        el('div', { class: 'ctl' }, [el('span', { class: 'lab', text: 'A class needs at least' }),
          el('input', { type: 'number', id: 'erMinN', min: '1', max: '200', step: '1', value: String(S.minN),
            class: 'numin', onchange: (e) => { const v = Math.round(Number(e.target.value));
              if (isFinite(v) && v >= 1) { S.minN = v; loadStats(); } } }), el('span', { class: 'small', text: 'events' })]),
        el('div', { class: 'ctl' }, [el('span', { class: 'lab', text: 'Measures from' }),
          seg([[false, 'every recording'], [true, 'the separable ones only',
                'DS1 and DS2 only mean something where they separate: the measures from those alone. '
                + 'Whether they separate is still counted over every recording.']],
              S.onlySep, (v) => { S.onlySep = v; loadStats(); putStats(); }, 'erOnlySep')]),
      ]).filter(Boolean)),
    ].filter(Boolean);
    if (S.statsErr) kids.push(el('p', { class: 'err', text: 'Not worked out: ' + S.statsErr }));
    if (!st) { kids.push(el('p', { class: 'muted', text: 'Working it out…' })); return el('div', { class: 'card' }, kids); }
    const gr = st.groups || {};
    kids.push(el('p', { class: 'small', text: 'CTL ' + gr.CTL + ' · PTEN ' + gr.PTEN + ' (Low KO, under ' + st.split + '%: '
      + gr['Low KO'] + '; High KO: ' + gr['High KO'] + ')'
      + ((gr['no KO'] || []).length ? '. No %KO, so in PTEN but not in Low or High: ' + gr['no KO'].join(', ') : '')
      + ((st.skipped || []).length ? '. Left out by hand: ' + st.skipped.length : '')
      + '. A class with fewer than ' + st.min_n + ' events gives no number for its own measures.' }));
    const grid = el('div', { class: 'stats' });
    if (st.separability) grid.appendChild(sepPanel(st.separability));
    for (const m of st.metrics || []) grid.appendChild(statPanel(m));
    kids.push(grid);
    if (st.only_sep) {
      kids.push(el('p', { class: 'small', text: 'The measures above are from the recordings called separable only; '
        + 'whether a recording separates is counted over every one.' }));
    }
    kids.push(el('p', { class: 'muted small', text: usualOn()
      ? 'The usual tests: one per question, picked by whether the residuals (each value less its group’s mean) look normal '
        + 'by Shapiro–Wilk. Two groups: Welch’s t-test if they do, Mann–Whitney if not, and Hedges’ g (PTEN minus CTL, in pooled '
        + 'SDs). Three: first whether it rises or falls in order, CTL → Low KO → High KO (Jonckheere–Terpstra), then one-way '
        + 'ANOVA with Tukey’s pairs if they look normal, Kruskal–Wallis with Dunn’s pairs (Holm) if not. Against %KO: the dose, '
        + 'Spearman’s ρ among the PTEN mice alone; the one with the controls at 0% is beside it, but it mostly measures PTEN '
        + 'against controls. Nothing is corrected across the eight measures: with eight looks, one p under '
        + '0.05 by chance alone is not rare. With so few mice, read the dots as well as the p.'
      : 'Strict: two groups need Welch’s t and Mann–Whitney U both, with Hedges’ g (PTEN minus CTL, in pooled SDs). Three need '
        + 'one-way ANOVA and Kruskal–Wallis both, then each pair by Mann–Whitney, Holm-adjusted over the three pairs. Against '
        + '%KO: Spearman’s ρ among the PTEN mice alone (the dose). Nothing is corrected across the eight measures. With so few mice, read the '
        + 'dots as well as the p.' }));
    return el('div', { class: 'card', id: 'erStatsCard' }, kids);
  }

  /* WHICH SEPARATE: by group, with the calls made by hand. CTL vs PTEN by
     Fisher's exact test; CTL / Low KO / High KO by the exact
     Freeman-Halton test and each pair by Fisher (Holm); against %KO, the
     %KO of the separable against the rest. */
  function sepPanel(sp) {
    const frac = (t) => (t && t.n ? t.yes + ' of ' + t.n : '0 of 0');
    let verdict, words;
    if (S.cmp === 'two' && usualOn()) {
      const t = sp.two || {};
      verdict = t.boschloo_p == null ? 'cannot tell' : sig(t.boschloo_p) ? 'differs' : 'no clear difference';
      words = 'Separable: PTEN ' + frac(t.PTEN) + ', CTL ' + frac(t.CTL) + ' · Boschloo’s exact p ' + pw(t.boschloo_p)
        + ' (Fisher’s p ' + pw(t.fisher_p) + ')';
    } else if (S.cmp === 'three' && usualOn()) {
      const h = sp.three || {};
      verdict = h.trend_p == null ? 'cannot tell' : sig(h.trend_p) ? 'differs' : 'no clear difference';
      words = 'Separable: ' + GROUPS.three.map((g) => g + ' ' + frac(h[g])).join(' · ')
        + ' · trend, CTL → Low KO → High KO (Cochran–Armitage) p ' + pw(h.trend_p) + ' · pairs (Boschloo, Holm): '
        + (h.pairs || []).map((p) => p.a + '–' + p.b + ' p ' + pw(p.boschloo_holm_p)).join(', ');
    } else if (S.cmp === 'two') {
      const t = sp.two || {};
      verdict = t.fisher_p == null ? 'cannot tell' : sig(t.fisher_p) ? 'differs' : 'no clear difference';
      words = 'Separable: PTEN ' + frac(t.PTEN) + ', CTL ' + frac(t.CTL) + ' · Fisher’s exact p ' + pw(t.fisher_p);
    } else if (S.cmp === 'three') {
      const h = sp.three || {};
      verdict = h.exact_p == null ? 'cannot tell' : sig(h.exact_p) ? 'differs' : 'no clear difference';
      words = 'Separable: ' + GROUPS.three.map((g) => g + ' ' + frac(h[g])).join(' · ')
        + ' · exact (Freeman–Halton) p ' + pw(h.exact_p) + ' · pairs (Fisher, Holm): '
        + (h.pairs || []).map((p) => p.a + '–' + p.b + ' p ' + pw(p.holm_p)).join(', ');
    } else {
      const k = sp.ko || {}, lp = k.logit_pten || {};
      verdict = lp.p == null ? 'cannot tell' : sig(lp.p) ? (lp.or10 < 1 ? 'falls as %KO rises' : 'rises with %KO')
        : 'no clear trend with %KO';
      words = 'The dose, among PTEN alone: odds of separating × ' + (lp.or10 == null ? '—' : fmt(lp.or10, 2)) + ' per 10% KO, p '
        + pw(lp.p) + ' (n ' + (lp.n || 0) + ') · %KO of the separable: median ' + fmt((k.yes || {}).median, 1) + '% (n ' + ((k.yes || {}).n || 0)
        + ') vs the rest ' + fmt((k.no || {}).median, 1) + '% (n ' + ((k.no || {}).n || 0) + ') · Mann–Whitney p '
        + pw(k.mwu_p) + ' (controls at 0%)';
    }
    const notes = [];
    if ((sp.by_hand || []).length) notes.push('Called by hand: ' + sp.by_hand.join(', ') + '.');
    if ((sp.not_counted || []).length) notes.push('Too few events to say, so not counted: ' + sp.not_counted.join(', ') + '.');
    const cv = el('canvas', { class: 'stat-cv' });
    const f = () => drawSep(cv, sp);
    f.stats = true;
    live.push(f);
    cv.addEventListener('click', (e) => pickStat(cv, e));
    return el('div', { class: 'stat sep' + (HIT(verdict) ? ' hit' : '') }, [
      el('div', { class: 'stat-h' }, [el('b', { text: 'Separable' }),
        el('span', { class: 'chip verdict', text: verdict })]),
      el('span', { class: 'muted small', text: 'Whether DS1 and DS2 separate: X-ray’s call, or yours where you made one. '
        + '“Weak” counts as not separable.' }),
      cv,
      el('span', { class: 'small num', text: words }),
      notes.length ? el('span', { class: 'muted small', text: notes.join(' ') }) : null,
    ]);
  }

  /* A bar per group, as tall as the share separable, a dot per recording
     (filled: separable); against %KO, each recording's %KO, separable or
     not. */
  function drawSep(cv, sp) {
    const s = sized(cv);
    if (!s) return;
    const { g, w, h } = s;
    const L = 46, B = 26, T = 10, R = 10;
    const pw_ = w - L - R, ph = h - B - T;
    const vals = (sp.values || []).filter((v) => v.sep !== null && v.sep !== undefined);
    const pts = [];
    g.font = '10px ' + tok('--sans', 'sans-serif');
    const hash = (gid) => { let x = 7; for (const ch of String(gid)) x = (x * 31 + ch.charCodeAt(0)) % 1000; return x / 1000; };
    if (S.cmp === 'ko') {
      const kmax = Math.max(30, ...vals.map((v) => (String(v.group).toUpperCase() === 'CTL' ? 0 : v.ko || 0)));
      const Y = (k) => T + ph - (k / kmax) * ph;
      g.strokeStyle = tok('--line'); g.fillStyle = tok('--ink-3'); g.textAlign = 'right';
      for (const k of [0, 10, 20, 30].filter((x) => x <= kmax)) {
        g.beginPath(); g.moveTo(L, Y(k)); g.lineTo(L + pw_, Y(k)); g.stroke();
        g.fillText(k + '%', L - 4, Y(k) + 3);
      }
      g.textAlign = 'center';
      [[true, 'separable'], [false, 'not separable']].forEach(([yes, name], i) => {
        const cx = L + pw_ * (i + 0.5) / 2;
        const mine = vals.filter((v) => v.sep === yes);
        g.fillStyle = tok('--ink-2');
        g.fillText(name + ' · ' + mine.length, cx, h - 8);
        for (const v of mine) {
          const ctl = String(v.group).toUpperCase() === 'CTL';
          if (!ctl && v.ko == null) continue;
          const x = cx + (hash(v.gid) - 0.5) * 50, y = Y(ctl ? 0 : v.ko);
          g.fillStyle = tok(GCOL[ctl ? 'CTL' : (v.ko_group || 'PTEN')] || '--g-pten');
          g.beginPath(); g.arc(x, y, 4, 0, 6.2832); g.fill();
          pts.push({ x, y, v });
        }
      });
    } else {
      const names = GROUPS[S.cmp];
      const bw = pw_ / names.length;
      const Y = (f) => T + ph - f * ph;
      g.strokeStyle = tok('--line'); g.fillStyle = tok('--ink-3'); g.textAlign = 'right';
      for (const f of [0, 0.25, 0.5, 0.75, 1]) {
        g.beginPath(); g.moveTo(L, Y(f)); g.lineTo(L + pw_, Y(f)); g.stroke();
        g.fillText(Math.round(f * 100) + '%', L - 4, Y(f) + 3);
      }
      g.textAlign = 'center';
      names.forEach((name, i) => {
        const mine = vals.filter((v) => (S.cmp === 'two'
          ? (name === 'CTL') === (String(v.group).toUpperCase() === 'CTL') : v.ko_group === name));
        const cx = L + bw * (i + 0.5);
        const yes = mine.filter((v) => v.sep).length;
        const frac = mine.length ? yes / mine.length : 0;
        g.fillStyle = tok(GCOL[name]); g.globalAlpha = 0.25;
        g.fillRect(cx - bw * 0.3, Y(frac), bw * 0.6, Y(0) - Y(frac));
        g.globalAlpha = 1;
        g.fillStyle = tok('--ink-2');
        g.fillText(name + ' · ' + yes + ' of ' + mine.length, cx, h - 8);
        let ky = 0, kn = 0;
        for (const v of mine) {
          const x = cx + (hash(v.gid) - 0.5) * bw * 0.5;
          // Separable ones sit at the top of the bar, the rest on the floor.
          const k = v.sep ? ky++ : kn++;
          const y = Math.max(T + 4, (v.sep ? Y(frac) + 8 : Y(0) - 8) + (v.sep ? 1 : -1) * Math.floor(k / 4) * 9);
          g.strokeStyle = tok(GCOL[name]); g.fillStyle = tok(GCOL[name]); g.lineWidth = 1.5;
          g.beginPath(); g.arc(x, y, 4, 0, 6.2832);
          if (v.sep) g.fill(); else g.stroke();
          g.lineWidth = 1;
          pts.push({ x, y, v });
        }
      });
    }
    g.textAlign = 'left';
    cv.__pts = pts;
  }

  function statPanel(m) {
    let verdict, words;
    const u = m.usual || {};
    if (S.cmp === 'two' && usualOn() && u.two) {
      const t = m.two || {}, x = u.two;
      verdict = x.why || x.p == null ? 'cannot tell' : sig(x.p) ? 'differs' : 'no clear difference';
      words = 'PTEN ' + showV(m, (t.pten || {}).mean) + ' ± ' + showV(m, (t.pten || {}).sem) + ' (n ' + ((t.pten || {}).n || 0)
        + ') vs CTL ' + showV(m, (t.ctl || {}).mean) + ' ± ' + showV(m, (t.ctl || {}).sem) + ' (n ' + ((t.ctl || {}).n || 0) + ')'
        + (x.why ? ' · ' + x.why : ' · ' + TEST[x.test] + ' p ' + pw(x.p) + whyTest(x)
           + ' · g ' + (t.g == null ? '—' : sgn(t.g, 2)));
    } else if (S.cmp === 'three' && usualOn() && u.three) {
      const h = m.three || {}, x = u.three;
      // In order, CTL -> Low KO -> High KO, first: the dose, asked of groups.
      verdict = x.why || x.p == null ? 'cannot tell'
        : sig(x.jt_p) ? (x.jt_z < 0 ? 'falls CTL → Low → High' : 'rises CTL → Low → High')
        : sig(x.p) ? 'differs' : 'no clear difference';
      words = GROUPS.three.map((g) => g + ' ' + showV(m, (h[g] || {}).mean) + ' (n ' + ((h[g] || {}).n || 0) + ')').join(' · ')
        + (x.why ? ' · ' + x.why : ' · in order, CTL → Low KO → High KO (Jonckheere–Terpstra) p ' + pw(x.jt_p)
           + ' · ' + TEST[x.test] + ' p ' + pw(x.p) + whyTest(x)
           + ' · pairs (' + POST[x.post] + '): ' + (x.pairs || []).map((p) => p.a + '–' + p.b + ' p ' + pw(p.p)).join(', '));
    } else if (S.cmp === 'two') {
      const t = m.two || {};
      const n = [sig(t.welch_p), sig(t.mwu_p)].filter(Boolean).length;
      verdict = t.why ? 'cannot tell' : n === 2 ? 'differs' : n === 1 ? 'differs on one test of two' : 'no clear difference';
      words = 'PTEN ' + showV(m, (t.pten || {}).mean) + ' ± ' + showV(m, (t.pten || {}).sem) + ' (n ' + ((t.pten || {}).n || 0)
        + ') vs CTL ' + showV(m, (t.ctl || {}).mean) + ' ± ' + showV(m, (t.ctl || {}).sem) + ' (n ' + ((t.ctl || {}).n || 0) + ')'
        + (t.why ? ' · ' + t.why : ' · Welch p ' + pw(t.welch_p) + ' · Mann–Whitney p ' + pw(t.mwu_p)
           + ' · g ' + (t.g == null ? '—' : sgn(t.g, 2)));
    } else if (S.cmp === 'three') {
      const h = m.three || {};
      const n = [sig(h.anova_p), sig(h.kw_p)].filter(Boolean).length;
      verdict = h.why ? 'cannot tell' : n === 2 ? 'differs' : n === 1 ? 'differs on one test of two' : 'no clear difference';
      words = GROUPS.three.map((g) => g + ' ' + showV(m, (h[g] || {}).mean) + ' (n ' + ((h[g] || {}).n || 0) + ')').join(' · ')
        + (h.why ? ' · ' + h.why : ' · ANOVA p ' + pw(h.anova_p) + ' · Kruskal–Wallis p ' + pw(h.kw_p))
        + ' · pairs: ' + (h.pairs || []).map((p) => p.a + '–' + p.b + ' p ' + pw(p.holm_p)).join(', ');
    } else {
      [verdict, words] = doseWords(m);
    }
    const cv = el('canvas', { class: 'stat-cv' });
    const f = () => drawStat(cv, m);
    f.stats = true;
    live.push(f);
    cv.addEventListener('click', (e) => pickStat(cv, e));
    return el('div', { class: 'stat' + (HIT(verdict) ? ' hit' : '') }, [
      el('div', { class: 'stat-h' }, [el('b', { text: m.name }),
        el('span', { class: 'chip verdict', text: verdict })]),
      el('span', { class: 'muted small', text: m.words + (unitOf(m) ? ' In ' + unitOf(m) + '.' : '') }),
      cv,
      el('span', { class: 'small num', text: words }),
    ]);
  }

  function drawStat(cv, m) {
    const s = sized(cv);
    if (!s) return;
    const { g, w, h } = s;
    const L = 46, B = 26, T = 10, R = 10;
    const pw_ = w - L - R, ph = h - B - T;
    const vals = (m.values || []).filter((v) => v.value != null && isFinite(v.value));
    const pts = [];
    if (!vals.length) { cv.__pts = pts; return; }
    let lo = Math.min(...vals.map((v) => v.value)), hi = Math.max(...vals.map((v) => v.value));
    if (m.unit === 'ratio') { lo = Math.min(lo, 1); hi = Math.max(hi, 1); }
    if (hi === lo) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.1;
    // A count or a size never below zero: the padding does not take it there.
    lo = lo >= 0 && lo - pad < 0 ? 0 : lo - pad; hi += pad;
    // A share is 0% to 100%, never past either.
    if (m.unit === 'share') { lo = 0; hi = 1; }
    const Y = (v) => T + ph - ((v - lo) / (hi - lo)) * ph;
    g.strokeStyle = tok('--line'); g.lineWidth = 1;
    g.fillStyle = tok('--ink-3');
    g.font = '10px ' + tok('--sans', 'sans-serif');
    g.textAlign = 'right';
    for (let k = 0; k <= 4; k++) {
      const v = lo + ((hi - lo) * k) / 4;
      g.beginPath(); g.moveTo(L, Y(v)); g.lineTo(L + pw_, Y(v)); g.stroke();
      g.fillText(showV(m, v), L - 4, Y(v) + 3);
    }
    if (m.unit === 'ratio') {
      g.setLineDash([3, 3]); g.strokeStyle = tok('--ink-3');
      g.beginPath(); g.moveTo(L, Y(1)); g.lineTo(L + pw_, Y(1)); g.stroke(); g.setLineDash([]);
    }
    const hash = (gid) => { let x = 7; for (const ch of String(gid)) x = (x * 31 + ch.charCodeAt(0)) % 1000; return x / 1000; };
    if (S.cmp === 'ko') {
      const kmax = Math.max(30, ...vals.map((v) => (String(v.group).toUpperCase() === 'CTL' ? 0 : v.ko || 0)));
      const X = (k) => L + 8 + (k / kmax) * (pw_ - 16);
      g.textAlign = 'center';
      for (const k of [0, 10, 20, 30].filter((x) => x <= kmax)) g.fillText(k + '%', X(k), h - 10);
      g.fillText('% KO', L + pw_ / 2, h - 1);
      const fit = (m.dose || {}).fit;
      if (fit && fit.ko) {
        const at = (k) => Y(fit.intercept + fit.slope * k);
        // Inside the plot only: a line that would run below zero stops at the axis.
        g.save();
        g.beginPath(); g.rect(L, T, pw_, ph); g.clip();
        g.strokeStyle = tok('--g-pten'); g.lineWidth = 1.5; g.setLineDash([5, 4]);
        g.beginPath(); g.moveTo(X(fit.ko[0]), at(fit.ko[0])); g.lineTo(X(fit.ko[1]), at(fit.ko[1])); g.stroke();
        g.restore();
      }
      for (const v of vals) {
        const ctl = String(v.group).toUpperCase() === 'CTL';
        if (!ctl && v.ko == null) continue;
        const x = X(ctl ? 0 : v.ko) + (ctl ? (hash(v.gid) - 0.5) * 10 : 0), y = Y(v.value);
        g.fillStyle = tok(GCOL[ctl ? 'CTL' : (v.ko_group || 'PTEN')] || '--g-pten');
        g.beginPath(); g.arc(x, y, 4, 0, 6.2832); g.fill();
        pts.push({ x, y, v });
      }
    } else {
      const names = GROUPS[S.cmp];
      const bw = pw_ / names.length;
      g.textAlign = 'center';
      names.forEach((name, i) => {
        const mine = vals.filter((v) => (S.cmp === 'two'
          ? (name === 'CTL') === (String(v.group).toUpperCase() === 'CTL') : v.ko_group === name));
        const cx = L + bw * (i + 0.5);
        const col = tok(GCOL[name]);
        g.fillStyle = tok('--ink-2');
        g.fillText(name + ' · ' + mine.length, cx, h - 8);
        for (const v of mine) {
          const x = cx + (hash(v.gid) - 0.5) * Math.min(60, bw * 0.55), y = Y(v.value);
          g.fillStyle = col; g.globalAlpha = 0.85;
          g.beginPath(); g.arc(x, y, 4, 0, 6.2832); g.fill();
          g.globalAlpha = 1;
          pts.push({ x, y, v });
        }
        if (mine.length) {
          const xs = mine.map((v) => v.value);
          const mu = xs.reduce((a, b) => a + b, 0) / xs.length;
          const sd = xs.length > 1 ? Math.sqrt(xs.reduce((a, b) => a + (b - mu) ** 2, 0) / (xs.length - 1)) : 0;
          const se = xs.length > 1 ? sd / Math.sqrt(xs.length) : 0;
          g.strokeStyle = tok('--ink'); g.lineWidth = 2;
          g.beginPath(); g.moveTo(cx - 18, Y(mu)); g.lineTo(cx + 18, Y(mu)); g.stroke();
          g.lineWidth = 1.2;
          g.beginPath(); g.moveTo(cx, Y(mu - se)); g.lineTo(cx, Y(mu + se));
          g.moveTo(cx - 6, Y(mu - se)); g.lineTo(cx + 6, Y(mu - se));
          g.moveTo(cx - 6, Y(mu + se)); g.lineTo(cx + 6, Y(mu + se)); g.stroke();
          g.lineWidth = 1;
        }
      });
    }
    g.textAlign = 'left';
    cv.__pts = pts;
  }

  /* A dot is a recording: clicked, its card is brought into view. */
  function pickStat(cv, e) {
    const b = cv.getBoundingClientRect();
    const x = e.clientX - b.left, y = e.clientY - b.top;
    let best = null, bd = 100;
    for (const p of cv.__pts || []) {
      const d = (p.x - x) ** 2 + (p.y - y) ** 2;
      if (d < bd) { bd = d; best = p; }
    }
    if (!best) return;
    if (S.sub !== 'recordings') { S.sub = 'recordings'; render(); }
    const card = document.querySelector('#erGrid .rec[data-gid="' + best.v.gid + '"]');
    if (card) {
      card.scrollIntoView({ block: 'center', behavior: 'smooth' });
      card.classList.add('flash');
      setTimeout(() => card.classList.remove('flash'), 1600);
    }
  }

  /* ---------- the separation rate, on its own (2026-11-10: "have a stats
     test for separation rate") ----------
     Each group's rate with a Wilson 95% interval; CTL vs PTEN by Fisher's
     exact test; CTL / Low KO / High KO by the exact Freeman-Halton test,
     a Cochran-Armitage test for a trend in that order, and each pair by
     Fisher (Holm); against %KO, a logistic regression (odds per 10% KO).
     And the recordings, with their calls, to change one where it stands. */
  function sepRateCard() {
    const sp = S.stats && S.stats.separability;
    const kids = [el('div', { class: 'bar' }, [el('h2', { text: 'Separation rate' }),
      el('span', { class: 'muted small', text: 'How often DS1 and DS2 separate, by group: X-ray’s call, or yours '
        + 'where you made one. “Weak” counts as not separable; too few events is not counted.' })]),
      el('div', { class: 'bar' }, cmpControls().filter(Boolean)), leftOut()].filter(Boolean);
    if (S.statsErr) kids.push(el('p', { class: 'err', text: 'Not worked out: ' + S.statsErr }));
    if (!sp) { kids.push(el('p', { class: 'muted', text: 'Working it out…' })); return el('div', { class: 'card' }, kids); }
    const pc = (v) => (v == null ? '—' : Math.round(v * 100) + '%');
    const rate = (t) => (t && t.n ? pc(t.rate) + ' (' + t.yes + ' of ' + t.n + '; 95% CI '
      + (t.ci ? pc(t.ci[0]) + '–' + pc(t.ci[1]) : '—') + ')' : '—');
    let words, verdict;
    const trendWords = (h) => 'Cochran–Armitage trend, CTL → Low KO → High KO: p ' + pw(h.trend_p)
      + (h.trend_z != null ? ' (z ' + sgn(h.trend_z, 2) + (h.trend_z < 0 ? ', falling' : ', rising') + ')' : '');
    if (S.cmp === 'two' && usualOn()) {
      const t = sp.two || {};
      verdict = t.boschloo_p == null ? 'cannot tell' : sig(t.boschloo_p) ? 'differs' : 'no clear difference';
      words = ['PTEN ' + rate(t.PTEN), 'CTL ' + rate(t.CTL),
               'Boschloo’s exact test p ' + pw(t.boschloo_p) + ' (an exact test never less powerful than Fisher’s; Fisher’s '
               + 'p ' + pw(t.fisher_p) + ')'];
    } else if (S.cmp === 'three' && usualOn()) {
      const h = sp.three || {};
      verdict = h.trend_p == null ? 'cannot tell' : sig(h.trend_p) ? 'differs' : 'no clear difference';
      words = GROUPS.three.map((g) => g + ' ' + rate(h[g])).concat([trendWords(h),
        'pairs (Boschloo, Holm): ' + (h.pairs || []).map((p) => p.a + '–' + p.b + ' p ' + pw(p.boschloo_holm_p)).join(', '),
        'Freeman–Halton exact test, the strict one: p ' + pw(h.exact_p)]);
    } else if (S.cmp === 'two') {
      const t = sp.two || {};
      verdict = t.fisher_p == null ? 'cannot tell' : sig(t.fisher_p) ? 'differs' : 'no clear difference';
      words = ['PTEN ' + rate(t.PTEN), 'CTL ' + rate(t.CTL), 'Fisher’s exact test p ' + pw(t.fisher_p)];
    } else if (S.cmp === 'three') {
      const h = sp.three || {};
      verdict = h.exact_p == null ? 'cannot tell' : sig(h.exact_p) ? 'differs' : 'no clear difference';
      words = GROUPS.three.map((g) => g + ' ' + rate(h[g])).concat([
        'Freeman–Halton exact test p ' + pw(h.exact_p),
        trendWords(h),
        'pairs (Fisher, Holm): ' + (h.pairs || []).map((p) => p.a + '–' + p.b + ' p ' + pw(p.holm_p)).join(', ')]);
    } else {
      const k = sp.ko || {}, lg = k.logit || {}, lp = k.logit_pten || {};
      verdict = lp.p == null ? 'cannot tell' : sig(lp.p) ? (lp.or10 < 1 ? 'falls as %KO rises' : 'rises with %KO')
        : 'no clear trend with %KO';
      words = ['The dose, among PTEN alone: logistic regression, odds of separating × ' + (lp.or10 == null ? '—' : fmt(lp.or10, 2))
               + ' per 10% KO, p ' + pw(lp.p) + ' (n ' + (lp.n || 0) + ')' + (lp.why ? '; ' + lp.why : ''),
               'All mice, controls at 0%: odds of separating × ' + (lg.or10 == null ? '—' : fmt(lg.or10, 2))
               + ' per 10% KO, p ' + pw(lg.p) + ' (n ' + (lg.n || 0) + ')' + (lg.why ? '; ' + lg.why : ''),
               '%KO of the separable: median ' + fmt((k.yes || {}).median, 1) + '% vs the rest '
               + fmt((k.no || {}).median, 1) + '% · Mann–Whitney p ' + pw(k.mwu_p)];
    }
    const cv = el('canvas', { class: 'stat-cv big' });
    const f = () => drawRate(cv, sp);
    f.stats = true;
    live.push(f);
    cv.addEventListener('click', (e) => pickStat(cv, e));
    kids.push(el('div', { class: 'stat sep big' + (HIT(verdict) ? ' hit' : '') }, [
      el('div', { class: 'stat-h' }, [el('b', { text: 'Separation rate' }), el('span', { class: 'chip verdict', text: verdict })]),
      cv,
    ].concat(words.map((w) => el('span', { class: 'small num', text: w })))));
    const recs = (S.pay && S.pay.recordings) || [];
    kids.push(el('div', { class: 'tablewrap' }, [el('table', { id: 'erSepTable' }, [
      el('thead', {}, [el('tr', {}, ['recording', 'group', '%KO', 'X-ray said', 'called', ''].map((c) => el('th', { text: c })))]),
      el('tbody', {}, recs.map((r) => {
        const sh = sepOf(r);
        const xs = (r.separation || {}).verdict;
        return el('tr', { 'data-gid': r.gid, class: 'st-' + stateOf(r) }, [
          el('td', { text: r.session_label }), el('td', { text: r.group }),
          el('td', { class: 'num', text: String(r.group).toUpperCase() === 'CTL' ? '0' : (koNow(r) == null ? '—' : String(koNow(r))) }),
          el('td', { text: (SEP[xs] || xs || '—') + ' (ΔBIC ' + fmt((r.separation || {}).dbic, 1)
            + ((r.separation || {}).min_share != null ? ', smaller class ' + Math.round(r.separation.min_share * 100) + '%' : '')
            + ')' }),
          el('td', { text: (SEP[sh.verdict] || sh.verdict || '—') + (sh.byHand ? ' · by hand' : '') }),
          el('td', {}, [el('div', { class: 'acts' }, [
            el('button', { class: 'btn small er-sep', text: sh.verdict === 'yes' ? 'Call it not separable' : 'Call it separable',
              onclick: () => setSep(r, sh.verdict === 'yes' ? 'no' : 'yes') }),
            sh.byHand ? el('button', { class: 'btn small er-sep-back', text: 'Back to X-ray’s call',
              onclick: () => setSep(r, null) }) : null])]),
        ]);
      })),
    ])]));
    return el('div', { class: 'card', id: 'erSepRateCard' }, kids);
  }

  /* Each group's rate as a bar with its Wilson interval, a dot per mouse
     (filled: separable); against %KO, each mouse at its %KO, up if it
     separates and down if not. */
  function drawRate(cv, sp) {
    if (S.cmp === 'ko') { drawSep(cv, sp); return; }
    const s = sized(cv);
    if (!s) return;
    const { g, w, h } = s;
    const L = 46, B = 28, T = 12, R = 10;
    const pw_ = w - L - R, ph = h - B - T;
    const Y = (f) => T + ph - f * ph;
    const vals = (sp.values || []).filter((v) => v.sep !== null && v.sep !== undefined);
    const pts = [];
    g.font = '10.5px ' + tok('--sans', 'sans-serif');
    g.strokeStyle = tok('--line'); g.fillStyle = tok('--ink-3'); g.textAlign = 'right';
    for (const f of [0, 0.25, 0.5, 0.75, 1]) {
      g.beginPath(); g.moveTo(L, Y(f)); g.lineTo(L + pw_, Y(f)); g.stroke();
      g.fillText(Math.round(f * 100) + '%', L - 4, Y(f) + 3);
    }
    const names = GROUPS[S.cmp];
    const bw = pw_ / names.length;
    const src = S.cmp === 'two' ? sp.two : sp.three;
    g.textAlign = 'center';
    names.forEach((name, i) => {
      const t = (src || {})[name] || {};
      const cx = L + bw * (i + 0.5);
      const col = tok(GCOL[name]);
      if (t.n) {
        g.fillStyle = col; g.globalAlpha = 0.28;
        g.fillRect(cx - bw * 0.28, Y(t.rate || 0), bw * 0.56, Y(0) - Y(t.rate || 0));
        g.globalAlpha = 1;
        if (t.ci) {
          g.strokeStyle = tok('--ink'); g.lineWidth = 1.5;
          g.beginPath(); g.moveTo(cx, Y(t.ci[0])); g.lineTo(cx, Y(t.ci[1]));
          g.moveTo(cx - 8, Y(t.ci[0])); g.lineTo(cx + 8, Y(t.ci[0]));
          g.moveTo(cx - 8, Y(t.ci[1])); g.lineTo(cx + 8, Y(t.ci[1])); g.stroke();
          g.lineWidth = 1;
        }
      }
      g.fillStyle = tok('--ink-2');
      g.fillText(name + ' · ' + (t.yes || 0) + ' of ' + (t.n || 0) + (t.n ? ' · ' + Math.round((t.rate || 0) * 100) + '%' : ''),
                 cx, h - 9);
      const mine = vals.filter((v) => (S.cmp === 'two'
        ? (name === 'CTL') === (String(v.group).toUpperCase() === 'CTL') : v.ko_group === name));
      let ky = 0, kn = 0;
      for (const v of mine) {
        const k = v.sep ? ky++ : kn++;
        const x = cx + bw * 0.34 + (k % 3) * 9;
        const y = v.sep ? T + 8 + Math.floor(k / 3) * 9 : Y(0) - 8 - Math.floor(k / 3) * 9;
        g.strokeStyle = col; g.fillStyle = col; g.lineWidth = 1.5;
        g.beginPath(); g.arc(Math.min(x, L + pw_ - 5), y, 3.6, 0, 6.2832);
        if (v.sep) g.fill(); else g.stroke();
        g.lineWidth = 1;
        pts.push({ x: Math.min(x, L + pw_ - 5), y, v });
      }
    });
    g.textAlign = 'left';
    cv.__pts = pts;
  }

  /* ---------- Round II (2026-11-10: "try to find something straightforward
     that is significant") ----------
     A wide, plain look: simple measures per recording, each compared the
     way chosen, ranked by p, with the false discovery rate held across all
     of them (Benjamini-Hochberg q). A measure the q clears is a finding; one
     only the p clears is a lead, said as such. */
  function round2Card() {
    const r2 = S.r2;
    const U = usualOn();
    const kids = [el('div', { class: 'bar' }, [el('h2', { text: 'Round II · something plain' }),
      el('span', { class: 'muted small', text: U
        ? 'Simple measures of each recording — how often, how big, how many look like a control’s — each by its usual '
          + 'test, ranked by p. Under 0.05 is said as a difference. With this many looks, about one in 20 falls under 0.05 by '
          + 'luck alone, so each also carries its q, the false discovery rate across all of them (Benjamini–Hochberg), to read '
          + 'beside it.'
        : 'Simple measures of each recording — how often, how big, how many look like a control’s — each tested, ranked by '
          + 'p. With this many looks some p’s fall under 0.05 by luck alone, so each also carries its q: the false discovery '
          + 'rate across all of them (Benjamini–Hochberg). q under 0.05 is a finding; p under 0.05 with a larger q is a lead.' })]),
      el('div', { class: 'bar' }, cmpControls().filter(Boolean)), leftOut()].filter(Boolean);
    if (S.r2Err) kids.push(el('p', { class: 'err', text: 'Not worked out: ' + S.r2Err }));
    if (!r2) { kids.push(el('p', { class: 'muted', text: 'Working it out…' })); return el('div', { class: 'card' }, kids); }
    const way = S.cmp === 'two' ? 'two' : S.cmp === 'three' ? 'three' : 'ko';
    const pOf = U
      ? (m) => (way === 'ko' ? (m.dose || {}).p : ((m.usual || {})[way] || {}).p)
      : (m) => (way === 'two' ? m.two.mwu_p : way === 'three' ? m.three.kw_p : (m.dose || {}).p);
    const ms = (r2.metrics || []).slice().sort((a, b) => (pOf(a) == null ? 2 : pOf(a)) - (pOf(b) == null ? 2 : pOf(b)));
    if (U) return round2Usual(r2, kids, ms, way, pOf);
    const hits = ms.filter((m) => sig((m.q || {})[way]));
    const leads = ms.filter((m) => sig(pOf(m)) && !sig((m.q || {})[way]));
    kids.push(el('p', { class: 'r2-say', text: hits.length
      ? 'Found: ' + hits.map((m) => m.name + ' (p ' + pw(pOf(m)) + ', q ' + pw(m.q[way]) + ')').join('; ') + '.'
      : leads.length
        ? 'Nothing clears the false discovery rate. Leads, under 0.05 on their own: '
          + leads.map((m) => m.name + ' (p ' + pw(pOf(m)) + ', q ' + pw(m.q[way]) + ')').join('; ') + '.'
        : 'Nothing here, not even a lead: the smallest p is ' + pw(pOf(ms[0] || {})) + '.' }));
    const grid = el('div', { class: 'stats' });
    for (const m of ms) {
      const panel = statPanel(m);
      const q = (m.q || {})[way];
      const tag = sig(q) ? 'finding (q ' + pw(q) + ')' : sig(pOf(m)) ? 'lead (q ' + pw(q) + ')' : 'q ' + pw(q);
      panel.classList.toggle('hit', sig(q));
      panel.classList.toggle('lead', !sig(q) && sig(pOf(m)));
      const vd = panel.querySelector('.chip.verdict');
      if (vd && !sig(q) && sig(pOf(m))) vd.textContent += ' · p only';
      const hd = panel.querySelector('.stat-h');
      if (hd) hd.appendChild(el('span', { class: 'chip q' + (sig(q) ? ' holds' : ''), text: tag }));
      grid.appendChild(panel);
    }
    kids.push(grid);
    kids.push(el('p', { class: 'muted small', text: 'Ranked by ' + (way === 'two' ? 'Mann–Whitney' : way === 'three'
      ? 'Kruskal–Wallis' : 'Spearman (PTEN alone, the dose)') + ' p; q is Benjamini–Hochberg over these ' + ms.length + ' measures. “Looks like '
      + 'control DS” judges a control by a border drawn from the other controls only, so no mouse is graded by a box its '
      + 'own events drew. Each recording is one mouse; ' + r2.n + ' here.' }));
    return el('div', { class: 'card', id: 'erRound2Card' }, kids);
  }

  /* Round II with the usual tests: a measure under 0.05 differs, said with
     its test; q is beside it to read, not a gate. */
  function round2Usual(r2, kids, ms, way, pOf) {
    const testOf = (m) => (way === 'ko' ? 'Spearman, PTEN alone' : TEST[((m.usual || {})[way] || {}).test] || '');
    const qOf = (m) => ((m.q_usual || {})[way]);
    const hits = ms.filter((m) => sig(pOf(m)));
    kids.push(el('p', { class: 'r2-say', text: hits.length
      ? 'Under 0.05: ' + hits.map((m) => m.name + ' (' + testOf(m) + ' p ' + pw(pOf(m)) + ', q ' + pw(qOf(m)) + ')').join('; ')
        + '. ' + (hits.some((m) => sig(qOf(m))) ? 'Holding across all ' + ms.length + ': '
          + hits.filter((m) => sig(qOf(m))).map((m) => m.name).join(', ') + '.'
          : 'None holds across all ' + ms.length + ' (q under 0.05) — read them as differences in this set, to be confirmed.')
      : 'Nothing under 0.05: the smallest p is ' + pw(pOf(ms[0] || {})) + '.' }));
    const grid = el('div', { class: 'stats' });
    for (const m of ms) {
      const panel = statPanel(m);
      const q = qOf(m);
      panel.classList.toggle('hit', sig(pOf(m)));
      panel.classList.remove('lead');
      const hd = panel.querySelector('.stat-h');
      if (hd) hd.appendChild(el('span', { class: 'chip q' + (sig(q) ? ' holds' : ''),
        text: sig(q) ? 'holds across all ' + ms.length + ' (q ' + pw(q) + ')' : 'q ' + pw(q) }));
      grid.appendChild(panel);
    }
    kids.push(grid);
    kids.push(el('p', { class: 'muted small', text: 'Each measure by its usual test, picked by whether its residuals look normal '
      + '(Shapiro–Wilk): ' + (way === 'two' ? 'Welch’s t-test, or Mann–Whitney' : way === 'three'
        ? 'one-way ANOVA with Tukey’s pairs, or Kruskal–Wallis with Dunn’s, beside the trend in order (Jonckheere–Terpstra)'
        : 'against %KO, the dose: Spearman’s ρ among the PTEN mice alone') + '. Ranked by p; '
      + 'q is Benjamini–Hochberg over these ' + ms.length + ' measures, shown beside each, not required. “Looks like control DS” '
      + 'judges a control by a border drawn from the other controls only, so no mouse is graded by a box its own events drew. '
      + 'Each recording is one mouse; ' + r2.n + ' here.' }));
    return el('div', { class: 'card', id: 'erRound2Card' }, kids);
  }

  /* ---------- the numbers, all of them ---------- */
  function numbers() {
    const recs = (S.pay && S.pay.recordings) || [];
    const sink = S.mode === 'sink';
    const cols = ['recording', 'group', '%KO', 'events', 'DS1 n', 'DS2 n', 'separation']
      .concat(sink ? ['DS1 sink', 'DS2 sink', 'DS1 Δ contacts', 'DS2 Δ contacts', 'DS1 Δ µm', 'DS2 Δ µm']
                   : ['DS1 source', 'DS2 source', 'DS1 source CSC', 'DS2 source CSC']);
    // As they are called now: a swapped recording's DS1 is X-ray's DS2.
    const cls = (r, k) => shownClasses(r).find((c) => c.shown === k) || {};
    if (recs.some(flipped)) cols.push('swapped by hand');
    const rowOf = (r) => {
      const a = cls(r, 1), b = cls(r, 2);
      const sv = sepOf(r);
      const base = [r.session_label, r.group, String(r.group).toUpperCase() === 'CTL' ? 0 : koNow(r), r.n, a.n, b.n,
                    (SEP[sv.verdict] || '') + (sv.byHand ? ' (by hand)' : '')];
      if (recs.some(flipped)) {
        return base.concat(sink
          ? [(a.sink || {}).value, (b.sink || {}).value, (a.delta || {}).contacts, (b.delta || {}).contacts,
             (a.delta || {}).um, (b.delta || {}).um]
          : [(a.source || {}).value, (b.source || {}).value, (a.source || {}).csc, (b.source || {}).csc],
          [flipped(r) ? 'yes' : '']);
      }
      return base.concat(sink
        ? [(a.sink || {}).value, (b.sink || {}).value, (a.delta || {}).contacts, (b.delta || {}).contacts,
           (a.delta || {}).um, (b.delta || {}).um]
        : [(a.source || {}).value, (b.source || {}).value, (a.source || {}).csc, (b.source || {}).csc]);
    };
    const data = recs.map(rowOf);
    const csv = () => {
      const q = (v) => (v == null ? '' : /[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v));
      const text = [cols].concat(data).map((r) => r.map(q).join(',')).join('\n');
      const a = el('a', { href: URL.createObjectURL(new Blob([text], { type: 'text/csv' })),
        download: 'extraction_room_dentate_spike_v' + S.version + '_' + S.mode + '.csv' });
      document.body.appendChild(a); a.click(); a.remove();
    };
    return el('div', { class: 'card' }, [
      el('div', { class: 'bar' }, [el('h2', { text: 'The numbers · ' + (sink ? 'mean sink' : 'mean source') }),
        seg([['sink', 'mean sink'], ['source', 'mean source']], S.mode, (v) => { S.mode = v; render(); }, 'erModeN'),
        el('button', { class: 'btn', text: 'Download CSV', onclick: csv })]),
      el('div', { class: 'tablewrap' }, [el('table', { id: 'erTable' }, [
        el('thead', {}, [el('tr', {}, cols.map((c) => el('th', { text: c })))]),
        el('tbody', {}, data.map((row, i) => el('tr', { class: 'st-' + stateOf(recs[i]) }, row.map((v) => el('td', { class: typeof v === 'number' ? 'num' : null,
          text: v == null ? '—' : typeof v === 'number' ? String(+v.toFixed(4)) : String(v) }))))),
      ])]),
      el('p', { class: 'muted small', text: 'Sink and source in ' + ((recs[0] || {}).unit || '') + '; Δ is the mean over the class’s '
        + 'events of the distance between its two largest sinks, as X-ray’s delta method measures it.' }),
    ]);
  }

  /* ---------- drawing ---------- */
  function sized(cv) {
    if (!cv.isConnected) return null;
    const dpr = window.devicePixelRatio || 1;
    const w = cv.clientWidth, h = cv.clientHeight;
    if (!w || !h) return null;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    }
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    return { g, w, h };
  }
  function drawAll() { for (const f of live) { try { f(); } catch (e) { /* a canvas that left */ } } }

  /* THE SCALES. One for every recording when they are to be compared
     (2026-11-10): the CSD's colour runs to the 99th percentile of |CSD|
     over every recording and both classes; the profiles' x axis spans every
     recording's mean ± SEM. "Each its own" scales a recording to itself. */
  function p99(recs) {
    const vals = [];
    for (const r of recs) for (const c of r.classes || []) for (const row of c.csd || []) {
      for (const v of row) if (v != null && isFinite(v)) vals.push(Math.abs(v));
    }
    vals.sort((a, b) => a - b);
    return vals.length ? Math.max(1e-9, vals[Math.floor(0.99 * (vals.length - 1))]) : 1;
  }
  let scaleMemo = { key: null, clim: 1, x: null };
  function shared() {
    const recs = (S.pay && S.pay.recordings) || [];
    const key = S.version + '|' + recs.length;
    if (scaleMemo.key !== key) {
      scaleMemo = { key, clim: p99(recs), x: xRange(recs) };
    }
    return scaleMemo;
  }
  function climOf(r) {
    return S.scale === 'same' ? shared().clim : p99([r]);
  }
  function xRange(recs) {
    let lo = Infinity, hi = -Infinity;
    for (const r of recs) for (const c of r.classes || []) {
      const p = c.profile || {};
      (p.mean || []).forEach((v, j) => {
        if (v == null || !isFinite(v)) return;
        const e = (p.sem || [])[j] || 0;
        lo = Math.min(lo, v - e); hi = Math.max(hi, v + e);
      });
    }
    if (!isFinite(lo)) return null;
    const pad = (hi - lo) * 0.06 || 1;
    return [lo - pad, hi + pad];
  }

  function hexRgb(c) {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(c).trim());
    if (!m) return [128, 128, 128];
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  function drawCsd(cv, r, c) {
    const s = sized(cv);
    if (!s || !c.csd || !c.csd.length) return;
    const { g, w, h } = s;
    const L = 26, B = 16, T = 4, R = 4;
    const pw = w - L - R, ph = h - B - T;
    const nr = c.csd.length, nt = c.csd[0].length;
    const lim = climOf(r);
    const sink = hexRgb(tok('--sink')), src = hexRgb(tok('--source')), bg = hexRgb(tok('--surface-2'));
    const off = document.createElement('canvas');
    off.width = nt; off.height = nr;
    const og = off.getContext('2d');
    const im = og.createImageData(nt, nr);
    for (let i = 0; i < nr; i++) {
      for (let j = 0; j < nt; j++) {
        const v = c.csd[i][j];
        const k = (i * nt + j) * 4;
        let col = bg, a = 0;
        if (v != null && isFinite(v)) {
          // A gentle curve, so a sink half the size of the biggest still
          // reads as a sink rather than as a pale wash.
          a = Math.pow(Math.min(1, Math.abs(v) / lim), 0.6);
          const neg = v < 0;
          col = neg ? sink : src;
          // The one not asked about, faded rather than hidden.
          if ((S.mode === 'sink') !== neg) a *= 0.22;
        }
        im.data[k] = Math.round(bg[0] + (col[0] - bg[0]) * a);
        im.data[k + 1] = Math.round(bg[1] + (col[1] - bg[1]) * a);
        im.data[k + 2] = Math.round(bg[2] + (col[2] - bg[2]) * a);
        im.data[k + 3] = 255;
      }
    }
    og.putImageData(im, 0, 0);
    g.imageSmoothingEnabled = true;
    g.drawImage(off, L, T, pw, ph);
    const t = r.t_ms || [];
    const t0 = t[0], t1 = t[t.length - 1];
    const X = (ms) => L + ((ms - t0) / (t1 - t0)) * pw;
    const cs = r.contacts || [];
    const rowOf = (csc) => cs.indexOf(csc);
    const Y = (row) => T + ((row + 0.5) / nr) * ph;
    g.strokeStyle = tok('--line-2'); g.lineWidth = 1;
    g.strokeRect(L + 0.5, T + 0.5, pw - 1, ph - 1);
    // The box: its depth band and its time.
    const bx = r.box || {};
    g.setLineDash([4, 3]);
    g.strokeStyle = tok('--ink-2');
    if (bx.sel_lo != null && bx.sel_hi != null && rowOf(bx.sel_lo) >= 0 && rowOf(bx.sel_hi) >= 0) {
      const y0 = T + (rowOf(bx.sel_lo) / nr) * ph, y1 = T + ((rowOf(bx.sel_hi) + 1) / nr) * ph;
      g.beginPath(); g.moveTo(L, y0); g.lineTo(L + pw, y0); g.moveTo(L, y1); g.lineTo(L + pw, y1); g.stroke();
    }
    if (bx.t_lo_ms != null) {
      for (const ms of bx.t_lo_ms === bx.t_hi_ms ? [bx.t_lo_ms] : [bx.t_lo_ms, bx.t_hi_ms]) {
        g.beginPath(); g.moveTo(X(ms), T); g.lineTo(X(ms), T + ph); g.stroke();
      }
    }
    g.setLineDash([]);
    // Its mark: the strongest sink or source, an arrow at the left edge.
    const m = S.mode === 'sink' ? (c.sink || {}) : (c.source || {});
    if (m.csc != null && rowOf(m.csc) >= 0) {
      const y = Y(rowOf(m.csc));
      g.fillStyle = colOf(c);
      g.beginPath(); g.moveTo(L - 1, y); g.lineTo(L - 9, y - 5); g.lineTo(L - 9, y + 5); g.closePath(); g.fill();
    }
    g.fillStyle = tok('--ink-3');
    g.font = '10px ' + tok('--sans', 'sans-serif');
    g.textAlign = 'right';
    g.fillText(String(cs[0] != null ? cs[0] : 1), L - 10, T + 9);
    g.fillText(String(cs[cs.length - 1] != null ? cs[cs.length - 1] : nr), L - 10, T + ph);
    g.textAlign = 'center';
    g.fillText(fmt(t0, 0), L + 10, h - 3);
    g.fillText('0 ms', X(0), h - 3);
    g.fillText('+' + fmt(t1, 0), L + pw - 12, h - 3);
    g.textAlign = 'left';
  }

  /* The two largest sinks of a profile inside the box, at least `sep`
     contacts apart: where to draw the delta's bracket (the number said is
     the room's, the mean over events). */
  function twoSinks(cs, mu, lo, hi, sep) {
    const idx = [];
    for (let j = 1; j < mu.length - 1; j++) {
      if (mu[j] == null || cs[j] < lo || cs[j] > hi) continue;
      if (mu[j] < 0 && mu[j] <= (mu[j - 1] == null ? Infinity : mu[j - 1])
          && mu[j] <= (mu[j + 1] == null ? Infinity : mu[j + 1])) idx.push(j);
    }
    idx.sort((a, b) => mu[a] - mu[b]);
    const a = idx[0];
    if (a == null) return null;
    const b = idx.find((j) => Math.abs(j - a) >= sep);
    return b == null ? null : [Math.min(a, b), Math.max(a, b)];
  }

  function drawProfile(cv, r) {
    const s = sized(cv);
    if (!s) return;
    const { g, w, h } = s;
    const L = 30, B = 22, T = 8, R = 10;
    const pw = w - L - R, ph = h - B - T;
    const cs = r.contacts || [];
    const n = cs.length;
    // One x axis for every recording, or this one's own (S.scale).
    const xr = S.scale === 'same' ? shared().x : xRange([r]);
    if (!xr) return;
    const lo = xr[0], hi = xr[1];
    const X = (v) => L + ((v - lo) / (hi - lo)) * pw;
    const Y = (j) => T + ((j + 0.5) / n) * ph;
    const bx = r.box || {};
    // The box's depth band, shaded.
    const j0 = cs.indexOf(bx.sel_lo), j1 = cs.indexOf(bx.sel_hi);
    if (j0 >= 0 && j1 >= 0) {
      g.fillStyle = tok('--chip');
      g.fillRect(L, T + (j0 / n) * ph, pw, ((j1 - j0 + 1) / n) * ph);
    }
    g.strokeStyle = tok('--line-2'); g.lineWidth = 1;
    g.strokeRect(L + 0.5, T + 0.5, pw - 1, ph - 1);
    g.setLineDash([3, 3]);
    g.beginPath(); g.moveTo(X(0), T); g.lineTo(X(0), T + ph); g.stroke();
    g.setLineDash([]);
    for (const c of shownClasses(r)) {
      const p = c.profile || {};
      const mu = p.mean || [], se = p.sem || [];
      const col = colOf(c), soft = softOf(c);
      // SEM band.
      g.fillStyle = soft;
      g.beginPath();
      mu.forEach((v, j) => { if (v == null) return; const x = X(v - (se[j] || 0)); if (j) g.lineTo(x, Y(j)); else g.moveTo(x, Y(j)); });
      for (let j = mu.length - 1; j >= 0; j--) { if (mu[j] == null) continue; g.lineTo(X(mu[j] + (se[j] || 0)), Y(j)); }
      g.closePath(); g.fill();
      g.strokeStyle = col; g.lineWidth = 1.8;
      g.beginPath();
      mu.forEach((v, j) => { if (v == null) return; if (j) g.lineTo(X(v), Y(j)); else g.moveTo(X(v), Y(j)); });
      g.stroke();
      // The mark, and for a sink the delta's bracket.
      const m = S.mode === 'sink' ? (c.sink || {}) : (c.source || {});
      const jm = cs.indexOf(m.csc);
      if (jm >= 0 && mu[jm] != null) {
        g.fillStyle = col;
        g.beginPath(); g.arc(X(mu[jm]), Y(jm), 4.5, 0, 6.2832); g.fill();
      }
      if (S.mode === 'sink' && j0 >= 0 && j1 >= 0) {
        const pair = twoSinks(cs, mu, bx.sel_lo, bx.sel_hi, 5);
        if (pair) {
          const xb = L + 6 + (c.shown - 1) * 8;
          g.strokeStyle = col; g.lineWidth = 2;
          g.beginPath();
          g.moveTo(xb + 4, Y(pair[0])); g.lineTo(xb, Y(pair[0])); g.lineTo(xb, Y(pair[1])); g.lineTo(xb + 4, Y(pair[1]));
          g.stroke();
          g.lineWidth = 1;
        }
      }
    }
    g.fillStyle = tok('--ink-3');
    g.font = '10px ' + tok('--sans', 'sans-serif');
    g.textAlign = 'right';
    g.fillText(String(cs[0]), L - 4, T + 9);
    g.fillText(String(cs[n - 1]), L - 4, T + ph);
    g.textAlign = 'center';
    g.fillText(sgn(lo, 2), L + 14, h - 6);
    g.fillText('0', X(0), h - 6);
    g.fillText(sgn(hi, 2), L + pw - 14, h - 6);
    g.textAlign = 'left';
  }

  /* ---------- go ---------- */
  let resizeT = null;
  window.addEventListener('resize', () => { clearTimeout(resizeT); resizeT = setTimeout(drawAll, 120); });
  const qs = new URLSearchParams(location.search);
  const th = qs.get('theme');
  if (th === 'dark' || th === 'light') document.documentElement.setAttribute('data-theme', th);

  window.erRoom = {
    state: () => S,
    start: (fetchImpl) => { S.fetch = fetchImpl || null; return load(); },
    reload: (v) => load(v),
    _poll: () => poll(true),
    _drawAll: drawAll,
    _twoSinks: twoSinks,
    _range: (gid) => { const r = ((S.pay || {}).recordings || []).find((x) => x.gid === gid);
      return r ? { x: S.scale === 'same' ? shared().x : xRange([r]), clim: climOf(r) } : null; },
  };
  if (qs.get('harness') !== '1') load();
})();
