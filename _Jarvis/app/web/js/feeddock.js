/* ==========================================================================
   feeddock.js -- the dock at the bottom becomes the live feed of what the
   server is doing.

   It was "Output · idle · no runs yet · Stop Copy Clear", and nobody used
   it: it only ever showed the log of a pipeline run, and the pipeline is
   the least-used thing in the app. Meanwhile the questions people actually
   had -- is it doing anything? what is it waiting on? did that sync go? --
   had nowhere to be answered. The server now keeps a feed of what it is
   doing (backend: GET /api/feed, GET /api/feed/stream), and this shows it:

     - collapsed, one slim line: the newest thing, with its bar if it has
       one, in its level's colour;
     - open, a list, newest at the bottom, following along unless you have
       scrolled up to read;
     - tabs: Activity (this computer's server), VACC (the cluster lane, only
       while VACC Mode is on, and the one it opens on when it turns on), and
       Output -- the old job log, untouched, with its run picker, Stop, Copy
       and Clear (core.js LOG).

   A line with a key REPLACES the earlier line with that key, in place: the
   bar fills, and the line settles with a tick or a cross and how long it
   took. Nothing is rebuilt that has not changed (constitution §12).

   Transport: the stream (Server-Sent Events) while the window is visible,
   polling every 2 s when the stream fails (and trying the stream again),
   every 10 s while the window is hidden. A stream holds one of the six
   connections a browser opens to this server for as long as it is open, so
   a hidden window gives its connection back, and only one window of the
   whole browser streams at a time; the others poll every 5 s (see
   wantStream).

   An old server has no /api/feed. Then the dock is exactly what it was,
   and it looks again once a minute in case the server has been restarted
   onto new code. A /_dev/ harness frame never connects on its own (a 2 s
   poll would show up in every harness that counts requests); a test turns
   it on with `BARRY.feed._show(true)` and feeds it with `_ingest(lines)`.
   ========================================================================== */
'use strict';

BARRY.feed = (function () {
  const dock = document.getElementById('logDock');
  const latest = document.getElementById('feedLatest');
  const tabsBox = document.getElementById('feedTabs');
  const CAP = 500;
  const TAB_LANE = { activity: 'jarvis', vacc: 'vacc', output: 'jarvis' };
  const TAB_WORD = { activity: 'Activity', vacc: 'VACC', output: 'Output' };

  const lanes = {};
  for (const name of ['jarvis', 'vacc']) {
    const list = dock && dock.querySelector('.fd-list[data-lane="' + name + '"]');
    lanes[name] = { name, list, byKey: new Map(), newest: null, follow: true, empty: null };
    if (list) {
      list.addEventListener('scroll', () => {
        const L = lanes[name];
        L.follow = list.scrollTop + list.clientHeight >= list.scrollHeight - 30;
      }, { passive: true });
      emptyNote(lanes[name]);
    }
  }

  const keyed = new Map();     // key -> newest line with that key
  const seenIds = new Set();   // un-keyed lines already shown
  const ring = [];             // the last lines, for a stuck report
  let liveAt = 0;              // when an unfinished line last arrived
  let last = 0;                // highest server id seen
  let on = false;
  let tab = 'activity';
  let pn = 0;

  function emptyNote(L) {
    if (!L.list || L.empty) return;
    L.empty = el('p', { class: 'fd-empty', text: L.name === 'vacc'
      ? 'Nothing from the cluster yet. What it is doing for this computer shows here.'
      : 'Nothing yet. What the server is doing shows here as it happens.' });
    L.list.appendChild(L.empty);
  }

  /* ------------------------------------------------------------------------
     words
     ------------------------------------------------------------------------ */
  const p2 = (n) => (n < 10 ? '0' : '') + n;
  function hms(at) {
    const d = new Date((at || Date.now() / 1000) * 1000);
    return p2(d.getHours()) + ':' + p2(d.getMinutes()) + ':' + p2(d.getSeconds());
  }
  function took(ms) {
    if (ms === null || ms === undefined || !isFinite(ms)) return '';
    if (ms < 1000) return Math.round(ms) + ' ms';
    if (ms < 60000) return (ms / 1000).toFixed(1) + ' s';
    const s = Math.round(ms / 1000);
    return Math.floor(s / 60) + ' min ' + (s % 60) + ' s';
  }
  function progressOf(line) {
    const p = line.progress;
    if (!p || p.length < 2 || !(p[1] > 0)) return null;
    return { done: p[0], total: p[1], frac: Math.max(0, Math.min(1, p[0] / p[1])) };
  }
  const WORKISH = ['request', 'job', 'sync', 'vacc', 'warm'];
  function markOf(line) {
    if (!line.done) return '';                       // the live dot, drawn by CSS
    if (line.level === 'err') return '✕';
    if (line.level === 'warn') return '!';
    if (line.level === 'ok' || WORKISH.includes(line.kind)) return '✓';
    return '·';
  }
  function metaOf(line) {
    const p = progressOf(line);
    const bits = [];
    if (p && !line.done) bits.push(p.done.toLocaleString() + ' of ' + p.total.toLocaleString());
    if (line.ms !== null && line.ms !== undefined) bits.push(took(line.ms));
    return bits.join(' · ');
  }

  /* ------------------------------------------------------------------------
     lines
     ------------------------------------------------------------------------ */
  function norm(x) {
    const line = Object.assign({}, x);
    line.lane = line.lane === 'vacc' ? 'vacc' : 'jarvis';
    line.level = ['info', 'ok', 'warn', 'err'].includes(line.level) ? line.level : 'info';
    line.text = String(line.text == null ? '' : line.text);
    line.done = line.done === undefined ? true : !!line.done;
    if (!line.at) line.at = Date.now() / 1000;
    return line;
  }

  function makeLine(line) {
    const n = el('div', { class: 'fd-line' }, [
      el('time', { class: 'fd-t' }),
      el('span', { class: 'fd-mark', 'aria-hidden': 'true' }),
      el('div', { class: 'fd-main' }, [
        el('span', { class: 'fd-text' }),
        el('span', { class: 'fd-bar', 'aria-hidden': 'true' }, [el('i')]),
      ]),
      el('span', { class: 'fd-meta' }),
    ]);
    n._at0 = line.at;
    paintLine(n, line);
    return n;
  }

  /* Every part changes in place, so a progress tick costs four text writes
     and a width, never a node. */
  function paintLine(n, line) {
    const p = progressOf(line);
    const cls = 'fd-line lv-' + line.level + (line.done ? ' done' : ' live')
      + (p ? ' has-bar' : '');
    if (n.className !== cls) n.className = cls;
    if (line.key) n.dataset.key = line.key;
    const [t, mark, main, meta] = n.children;
    const when = hms(n._at0 || line.at);
    if (t.textContent !== when) t.textContent = when;
    const m = markOf(line);
    if (mark.textContent !== m) mark.textContent = m;
    if (main.firstChild.textContent !== line.text) main.firstChild.textContent = line.text;
    main.lastChild.firstChild.style.width = p ? (p.frac * 100).toFixed(1) + '%' : '0%';
    const mt = metaOf(line);
    if (meta.textContent !== mt) meta.textContent = mt;
  }

  function put(x) {
    const line = norm(x);
    if (typeof line.id === 'number') {
      if (line.id > last) last = line.id;
      if (!line.key) {
        if (seenIds.has(line.id)) return;
        seenIds.add(line.id);
        if (seenIds.size > 4000) seenIds.clear();
      }
    }
    if (line.key) {
      keyed.delete(line.key);
      keyed.set(line.key, line);
      if (keyed.size > 600) keyed.delete(keyed.keys().next().value);
    }
    ring.push(line);
    if (ring.length > 80) ring.splice(0, ring.length - 80);
    if (!line.done) liveAt = Date.now();

    const L = lanes[line.lane];
    L.newest = line;
    if (L.list) {
      const list = L.list;
      const follow = L.follow;
      let node = line.key ? L.byKey.get(line.key) : null;
      if (node && node.isConnected) {
        paintLine(node, line);
      } else {
        if (L.empty) { L.empty.remove(); L.empty = null; }
        node = makeLine(line);
        list.appendChild(node);
        if (line.key) L.byKey.set(line.key, node);
        while (list.childElementCount > CAP) {
          const old = list.firstElementChild;
          if (old.dataset.key && L.byKey.get(old.dataset.key) === old) {
            L.byKey.delete(old.dataset.key);
          }
          old.remove();
        }
      }
      if (follow) list.scrollTop = list.scrollHeight;
    }
    paintLatest();
  }

  /* Each line from the server is also announced on the document, so a part
     of the page that cares about one kind (js/syncchip.js: kind 'sync') can
     listen without the dock knowing it exists. Server ids are the boot's
     clock in ms (~1.8e12): only ever compared, never used as an index. */
  function ingest(lines) {
    for (const x of (lines || [])) {
      if (!x || typeof x !== 'object') continue;
      try { put(x); } catch (e) { /* one bad line */ }
      try { document.dispatchEvent(new CustomEvent('barry:feed', { detail: x })); }
      catch (e) { /* a listener's fault is its own */ }
    }
  }

  /* The slim line while the dock is folded: the newest line of the lane on
     the chosen tab (or the other lane, when that one is empty). Two lines of
     small text fit the strip; a longer one steps down a size rather than
     being clipped. */
  let latestParts = null;
  function paintLatest() {
    if (!latest) return;
    const lane = TAB_LANE[tab] || 'jarvis';
    const line = lanes[lane].newest || lanes.jarvis.newest || lanes.vacc.newest;
    if (!latestParts) {
      latestParts = {
        mark: el('span', { class: 'fd-mark', 'aria-hidden': 'true' }),
        text: el('span', { class: 'fd-text' }),
        bar: el('span', { class: 'fd-bar', 'aria-hidden': 'true' }, [el('i')]),
        meta: el('span', { class: 'fd-meta' }),
      };
      latest.append(latestParts.mark, latestParts.text, latestParts.bar, latestParts.meta);
    }
    if (!line) {
      latest.className = 'fd-latest quiet';
      latestParts.mark.textContent = '';
      latestParts.text.textContent = 'Nothing happening right now.';
      latestParts.meta.textContent = '';
      return;
    }
    const p = progressOf(line);
    latest.className = 'fd-latest lv-' + line.level + (line.done ? ' done' : ' live')
      + (p ? ' has-bar' : '');
    latestParts.mark.textContent = markOf(line);
    latestParts.text.textContent = line.text;
    latestParts.bar.firstChild.style.width = p ? (p.frac * 100).toFixed(1) + '%' : '0%';
    latestParts.meta.textContent = metaOf(line);
    if (dock.classList.contains('collapsed') && on) {
      latest.classList.remove('tight');
      if (latest.scrollHeight > latest.clientHeight + 1) latest.classList.add('tight');
    }
  }

  /* ------------------------------------------------------------------------
     the page's own words
     ------------------------------------------------------------------------ */
  /* BARRY.feed.say(text, {level, key, lane, progress, done, ms, kind}).
     With a key, saying it again updates that line; the key is the page's
     own (prefixed), so it can never collide with one of the server's. */
  function say(text, o) {
    const opt = o || {};
    const line = {
      id: null, at: Date.now() / 1000, lane: opt.lane, kind: opt.kind || 'info',
      level: opt.level || 'info', text,
      key: opt.key ? 'page:' + opt.key : 'page#' + (++pn),
      progress: opt.progress || null,
      done: opt.done !== undefined ? !!opt.done : !opt.progress,
      ms: opt.ms === undefined ? null : opt.ms,
    };
    put(line);
    return opt.key || null;
  }

  /* The server came back with a new boot id (solid.js decides). Its ids
     start again, and a key from before means nothing now, so the lists go
     on below a divider instead of updating lines above it. */
  function restarted() {
    last = 0;
    seenIds.clear();
    keyed.clear();
    for (const L of Object.values(lanes)) {
      L.byKey.clear();
      if (L.list && !L.empty) {
        L.list.appendChild(el('div', { class: 'fd-div', role: 'separator' }, [
          el('span', { text: 'Server restarted' }),
        ]));
        if (L.follow) L.list.scrollTop = L.list.scrollHeight;
      }
    }
    say('The server restarted. Anything it was running may have stopped.',
        { level: 'warn' });
  }

  /* ------------------------------------------------------------------------
     tabs, copy, clear
     ------------------------------------------------------------------------ */
  const vaccOn = () => document.documentElement.dataset.vacc === 'on';
  function setTab(t) {
    if (!TAB_WORD[t]) t = 'activity';
    if (t === 'vacc' && !vaccOn()) t = 'activity';
    tab = t;
    if (!dock) return;
    dock.dataset.tab = t;
    if (tabsBox) {
      for (const b of tabsBox.querySelectorAll('.fd-tab')) {
        const sel = b.dataset.tab === t;
        b.classList.toggle('on', sel);
        b.setAttribute('aria-selected', sel ? 'true' : 'false');
      }
    }
    const L = lanes[TAB_LANE[t]];
    if (t !== 'output' && L && L.list && L.follow) L.list.scrollTop = L.list.scrollHeight;
    paintLatest();
  }
  if (tabsBox) {
    tabsBox.addEventListener('click', (e) => {
      const b = e.target.closest('.fd-tab');
      if (b) setTab(b.dataset.tab);
    });
  }

  /* VACC Mode turning on opens the dock's VACC tab; turning off leaves it. */
  new MutationObserver(() => {
    if (vaccOn()) { if (tab !== 'output') setTab('vacc'); }
    else if (tab === 'vacc') setTab('activity');
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-vacc'] });

  function laneText(L) {
    return Array.from(L.list ? L.list.children : []).map((n) => {
      if (n.classList.contains('fd-div')) return '--- ' + n.textContent + ' ---';
      if (!n.classList.contains('fd-line')) return '';
      const [t, mark, main, meta] = n.children;
      return [t.textContent, mark.textContent || '…', main.firstChild.textContent,
              meta.textContent ? '(' + meta.textContent + ')' : '']
        .filter(Boolean).join('  ');
    }).filter(Boolean).join('\n');
  }

  /* Copy and Clear belong to whichever tab is showing. On Output they are
     the job log's own (core.js init) and this steps aside; on a feed tab it
     takes the click first, at the dock, before it reaches those handlers. */
  if (dock) {
    dock.addEventListener('click', async (e) => {
      const b = e.target.closest('#logCopy, #logClear');
      if (!b || !on || tab === 'output') return;
      e.stopPropagation();
      const L = lanes[TAB_LANE[tab]];
      if (b.id === 'logClear') {
        L.byKey.clear();
        if (L.list) L.list.textContent = '';
        L.empty = null;
        L.newest = null;
        emptyNote(L);
        paintLatest();
        return;
      }
      try {
        await navigator.clipboard.writeText(laneText(L));
        toast(TAB_WORD[tab] + ' copied', 'ok');
      } catch (err) { toast('Could not copy', 'err'); }
    }, true);
  }

  /* The strip is measured only while folded (it has no box otherwise), so
     folding measures it again. */
  if (dock) {
    let wasFolded = dock.classList.contains('collapsed');
    new MutationObserver(() => {
      const folded = dock.classList.contains('collapsed');
      if (folded !== wasFolded) { wasFolded = folded; if (folded) paintLatest(); }
    }).observe(dock, { attributes: true, attributeFilter: ['class'] });
  }

  function show(yes) {
    on = !!yes;
    if (!dock) return;
    if (on) dock.dataset.feed = 'on';
    else delete dock.dataset.feed;
    setTab(tab === 'activity' && vaccOn() ? 'vacc' : tab);
  }

  /* ------------------------------------------------------------------------
     transport
     ------------------------------------------------------------------------ */
  let es = null;
  let streaming = false;
  let pollT = null;
  let retryT = null;
  let probeT = null;
  let fails = 0;
  let wantFeed = !HARNESS_FRAME;

  function seenBoot(b) {
    if (!b) return;
    if (BARRY.solid && BARRY.solid.sawBoot) BARRY.solid.sawBoot(b);
  }

  /* Through fetch, never api(): a missing route here is an old server and
     must not raise the stale-server banner, and none of it is anybody's
     click. */
  async function getFeed() {
    let res;
    try {
      res = await fetch('/api/feed?since=' + last, {
        cache: 'no-store', headers: HARNESS_FRAME ? { 'X-Barry-Test': '1' } : {} });
    } catch (e) {
      fails += 1;
      if (fails >= 2 && BARRY.solid && BARRY.solid.suspect) BARRY.solid.suspect();
      return 'down';
    }
    fails = 0;
    if (res.status === 404 || res.status === 405) return 'missing';
    let d;
    try { d = await res.json(); } catch (e) { return 'missing'; }
    if (!d || d.ok === false) return 'down';
    seenBoot(d.boot);
    ingest(d.lines);
    if (typeof d.last === 'number' && d.last > last) last = d.last;
    return 'ok';
  }

  function later(fn, ms) {
    if (probeT) clearTimeout(probeT);
    probeT = setTimeout(() => { probeT = null; fn(); }, ms);
  }

  async function probe() {
    if (!wantFeed) return;
    const r = await getFeed();
    if (r === 'ok') {
      if (!on) show(true);
      connect();
    } else if (r === 'missing') {
      if (on) { show(false); disconnect(); }
      later(probe, 60000);
    } else {
      later(probe, 5000);
    }
  }

  /* One stream for the whole browser, not one per window. Pop-outs (the
     curation aid window, Xplore's, the comod window) load the whole app, and
     each used to keep its own stream open while visible: a curator with the
     main window and its aid side by side gave two of the six connections to
     streams, and with each window's three background slots the clicks queued
     behind long roll-ups again -- and solid's ping could time out in that
     queue and read as "server away".

     So the stream is held under a Web Lock (navigator.locks, shared by every
     window of this origin in this browser): the visible window that gets the
     lock streams, and every other window polls /api/feed, a short request
     that holds no connection between answers, every 5 s while another window
     streams. A window that is hidden, closed or crashed gives the lock back
     (the browser releases it with the window), and the next visible window
     waiting for it takes the stream over. A browser without Web Locks
     streams only from a window nobody opened (the main one), and pop-outs
     poll. */
  const LOCKS = typeof navigator !== 'undefined' && navigator.locks
    && typeof navigator.locks.request === 'function';
  let lockGive = null;     // resolves the lock this window holds
  let lockAsking = false;  // waiting behind another window's stream

  function giveBack() {
    if (lockGive) { const g = lockGive; lockGive = null; g(); }
  }

  function wantStream() {
    if (!LOCKS) {
      if (window.opener) startPoll();
      else openStream();
      return;
    }
    if (lockGive) { openStream(); return; }
    startPoll();
    if (lockAsking) return;
    lockAsking = true;
    try {
      navigator.locks.request('barry-feed-stream', () => new Promise((give) => {
        lockAsking = false;
        lockGive = give;
        if (!on || !wantFeed || document.hidden) { giveBack(); return; }
        stopPoll();
        openStream();
      })).catch(() => { lockAsking = false; });
    } catch (e) { lockAsking = false; }
  }

  function connect() {
    if (!on || !wantFeed) return;
    if (!document.hidden && typeof EventSource === 'function' && !HARNESS_FRAME) {
      wantStream();
    } else {
      startPoll();
    }
  }
  function disconnect() {
    closeStream();
    giveBack();
    stopPoll();
    if (retryT) { clearTimeout(retryT); retryT = null; }
  }

  function openStream() {
    closeStream();
    let s;
    try { s = new EventSource('/api/feed/stream?since=' + last); }
    catch (e) { startPoll(); return; }
    es = s;
    const parse = (t) => { try { return JSON.parse(t); } catch (e) { return null; } };
    s.addEventListener('hello', (e) => {
      if (es !== s) return;
      const d = parse(e.data);
      if (d) seenBoot(d.boot);
      streaming = true;
      stopPoll();
    });
    s.onmessage = (e) => {
      if (es !== s) return;
      const d = parse(e.data);
      if (d) ingest([d]);
    };
    /* EventSource would retry by itself, but a 404 closes it for good and a
       server that is away makes it retry every few seconds without a word.
       Closed here, polled instead, and the stream tried again in 15 s. */
    s.onerror = () => {
      if (es !== s) return;
      closeStream();
      startPoll();
      if (retryT) clearTimeout(retryT);
      retryT = setTimeout(() => {
        retryT = null;
        if (on && !document.hidden) connect();
      }, 15000);
    };
  }
  function closeStream() {
    if (es) { try { es.close(); } catch (e) { /* gone */ } }
    es = null;
    streaming = false;
  }

  /* 2 s while this window should be streaming and cannot, 5 s while another
     window has the stream (see wantStream), 10 s while hidden. */
  function pollGap() {
    if (document.hidden) return 10000;
    return (lockAsking || (!LOCKS && window.opener)) ? 5000 : 2000;
  }
  function startPoll() {
    if (pollT) return;
    const go = async () => {
      pollT = null;
      if (!on || streaming) return;
      const r = await getFeed();
      if (r === 'missing') { show(false); disconnect(); later(probe, 60000); return; }
      if (!on || streaming || pollT) return;
      pollT = setTimeout(go, pollGap());
    };
    pollT = setTimeout(go, pollGap());
  }
  function stopPoll() {
    if (pollT) clearTimeout(pollT);
    pollT = null;
  }

  document.addEventListener('visibilitychange', () => {
    if (!on || !wantFeed) return;
    if (document.hidden) { closeStream(); giveBack(); startPoll(); }
    else { stopPoll(); connect(); }
  });

  /* After the boot screen has had its connections, not during. */
  if (wantFeed) {
    const start = () => setTimeout(probe, 800);
    if (document.readyState === 'complete') start();
    else window.addEventListener('load', start, { once: true });
  }

  return {
    say,
    restarted,
    tab: (t) => { if (t) setTab(t); return tab; },
    lineFor: (key) => keyed.get(key) || null,
    recent: (n) => ring.slice(-(n || 20)).map((l) => ({
      at: l.at, lane: l.lane, kind: l.kind, level: l.level, text: l.text,
      key: l.key || null, progress: l.progress || null, done: l.done, ms: l.ms })),
    liveSince: (t) => liveAt >= t,
    get on() { return on; },
    get last() { return last; },
    /* solid.js, on getting the server back: connect again now rather than at
       the next retry. */
    _kick() {
      if (!wantFeed) return;
      if (on) { if (!es && !pollT) connect(); }
      else probe();
    },
    /* For web/_dev/solid.html. `_show(true)` puts the dock in feed mode
       without connecting; `_ingest` feeds it lines as the server would;
       `_start()` connects as the app does outside a harness. */
    _show: show,
    _ingest: ingest,
    _start() { wantFeed = true; probe(); },
    _stop() { wantFeed = false; disconnect(); if (probeT) clearTimeout(probeT); },
  };
}());
