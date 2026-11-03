'use strict';

/* ==========================================================================
   data.js -- BARRY.data: one copy of every list, shared, last time's first.

   Measured 2026-10-21 (tools/perf_baseline.py): the recordings list was
   fetched by five views on their own -- Sessions, ToolKit, Kilosort, the
   tour, Housekeeping -- each holding its own copy of a two-megabyte answer;
   the Event Bank by three. Opening Sessions in a fresh browser showed
   nothing for 4.3 s and then all 520 cards at once.

   Three things, for any GET whose answer is a list or a roll-up:

     ONE COPY.    `get(url)` hands every caller the same answer, and a
                  request already on its way is shared rather than repeated.
     LAST TIME'S  The answer is kept in this browser (IndexedDB, through
     FIRST.       BARRY.stash) and `watch(url, cb)` hears it at once on the
                  next visit -- marked `{stale: true}` -- then hears the live
                  one when it lands. A view draws twice, the second time
                  changing only what changed (BARRY.ui.sections).
     CHEAP WHEN   The server sends an ETag (a hash of the body) and the page
     UNCHANGED.   sends it back; an unchanged list is a 304 with no body, so
                  nothing is parsed and nothing redrawn. The tag of the last
                  live answer is kept in localStorage, which can be read at
                  once, so even the first request after a restart can be a
                  304 answered out of the stash.

   And one thing for the heavy per-item answers: `stream(url, body, onItem)`
   reads newline-delimited JSON as it arrives (backend/streamjson.py), so a
   strip or a list fills in instead of appearing whole.

   Nothing here is the truth. Every failure -- a private window, a blocked
   database, a full disk -- is "nothing kept", and the live answer is always
   asked for. A write anywhere under /api/<thing> marks every kept answer
   under /api/<thing> as needing a fresh look (`invalidate`), because a 304
   costs almost nothing and a wrong list costs a great deal.
   ========================================================================== */
BARRY.data = (function () {
  const mem = new Map();        // url -> { value, at, etag, live }
  const flying = new Map();     // url -> Promise of the live value
  const watchers = new Map();   // url -> Set(cb)
  const TAG = 'barry.etag:';

  const stashKey = (url) => 'data:' + url;
  const family = (url) => {
    const p = String(url).split('?')[0].split('/').filter(Boolean);
    return '/' + p.slice(0, 2).join('/');      // "/api/bank"
  };
  function savedTag(url) {
    try { return localStorage.getItem(TAG + url) || null; } catch (e) { return null; }
  }
  function saveTag(url, tag) {
    try {
      if (tag) localStorage.setItem(TAG + url, tag);
      else localStorage.removeItem(TAG + url);
    } catch (e) { /* private window: the next start is a full read */ }
  }

  function emit(url, value, meta) {
    const set = watchers.get(url);
    if (!set) return;
    for (const cb of Array.from(set)) {
      try { cb(value, meta); }
      catch (e) {
        if (typeof reportClientError === 'function') {
          reportClientError('data.watch:' + url, e.message, e.stack);
        }
      }
    }
  }

  /* The live answer, revalidated when there is something to revalidate
     against. Resolves with the value; a 304 resolves with what was kept. */
  async function live(url, prior, opts) {
    const meta = {};
    const etag = (prior && prior.etag) || (!prior && savedTag(url)) || null;
    let got = await api(url, { etag, meta, priority: opts.priority });
    if (meta.notModified) {
      if (prior && prior.value !== undefined) return { value: prior.value, etag };
      // A 304 for something only the stash holds: read it, however long
      // that takes, because the server has just said it is current.
      const was = await BARRY.stash.get(stashKey(url), 3000);
      if (was && was.value && was.value.body !== undefined) {
        return { value: was.value.body, etag };
      }
      // Kept tag, nothing kept to go with it: ask again, in full.
      saveTag(url, null);
      got = await api(url, { meta, priority: opts.priority });
    }
    return { value: got, etag: meta.etag || null };
  }

  /* The answer at `url`.

     opts.maxAge   ms an answer already in hand is good for without asking
                   again (default 0: always revalidate -- cheap with a 304)
     opts.fresh    ask again even if one is in flight or young
     opts.priority 'background' for anything nobody is waiting on
     opts.stash    false to never draw last time's (default true) */
  function get(url, opts) {
    opts = opts || {};
    const have = mem.get(url);
    if (have && have.live && !opts.fresh
        && opts.maxAge && Date.now() - have.at < opts.maxAge) {
      return Promise.resolve(have.value);
    }
    if (flying.has(url) && !opts.fresh) return flying.get(url);

    const p = (async () => {
      let liveDone = false;
      const asking = live(url, have, opts).finally(() => { liveDone = true; });
      // Last time's, while this one comes -- only if nothing is on hand.
      if (!have && opts.stash !== false) {
        BARRY.stash.get(stashKey(url), 400).then((was) => {
          if (liveDone || mem.has(url) || !was || !was.value) return;
          if (was.value.body === undefined) return;
          mem.set(url, { value: was.value.body, at: was.at || 0,
                         etag: was.value.etag || null, live: false });
          emit(url, was.value.body, { stale: true, at: was.at || 0 });
        });
      }
      const res = await asking;
      const before = mem.get(url);
      const same = !!(before && before.etag && res.etag
                      && before.etag === res.etag && before.live);
      mem.set(url, { value: res.value, at: Date.now(), etag: res.etag, live: true });
      saveTag(url, res.etag);
      if (!same) {
        BARRY.stash.put(stashKey(url), { etag: res.etag, body: res.value });
      }
      emit(url, res.value, { stale: false, same });
      return res.value;
    })();
    flying.set(url, p);
    const clear = () => { if (flying.get(url) === p) flying.delete(url); };
    p.then(clear, clear);
    return p;
  }

  /* Hear every answer for `url`: last time's at once (stale), each live one
     after. Calls back with what is already in hand straight away. */
  function watch(url, cb) {
    if (!watchers.has(url)) watchers.set(url, new Set());
    watchers.get(url).add(cb);
    const have = mem.get(url);
    if (have) {
      try { cb(have.value, { stale: !have.live, at: have.at, held: true }); }
      catch (e) { /* the caller's problem; reported on the next emit */ }
    }
    return () => {
      const set = watchers.get(url);
      if (set) set.delete(cb);
    };
  }

  const peek = (url) => {
    const h = mem.get(url);
    return h ? { value: h.value, at: h.at, stale: !h.live } : null;
  };

  /* What is already known about `url` without asking the server: the copy
     in hand, or last time's from this browser. {value, at, live} or null,
     never slower than `wait` ms. For a view that draws last time's list
     while `get` fetches this time's. */
  async function stale(url, wait) {
    const h = mem.get(url);
    if (h) return { value: h.value, at: h.at, live: h.live };
    const was = await BARRY.stash.get(stashKey(url), wait || 400);
    if (!was || !was.value || was.value.body === undefined) return null;
    return { value: was.value.body, at: was.at || 0, live: false };
  }

  /* Something under this family changed: the next `get` asks again, and an
     answer somebody is watching is asked for now. */
  function invalidate(path) {
    const fam = family(path);
    for (const [url, h] of mem) {
      if (family(url) !== fam) continue;
      h.at = 0;
      if (watchers.has(url) && watchers.get(url).size) {
        get(url, { fresh: true, priority: 'background' }).catch(() => {});
      }
    }
  }

  /* A streamed answer (backend/streamjson.py): `onItem(item, i)` for each
     line as it lands. Resolves with {head, tail, n}; rejects with the error
     line's message, keeping what arrived on `err.partial`. */
  async function stream(url, body, onItem, opts) {
    opts = opts || {};
    const init = {
      method: body === undefined || body === null ? 'GET' : 'POST',
      headers: { 'Content-Type': 'application/json',
                 'Accept': 'application/x-ndjson' },
      signal: opts.signal,
    };
    if (init.method === 'POST') init.body = JSON.stringify(body);
    const sep = url.indexOf('?') >= 0 ? '&' : '?';
    const res = await fetch(url + sep + 'stream=1', init);
    if (!res.ok) {
      let msg = 'Request failed (' + res.status + ')';
      try { const j = await res.json(); if (j && j.error) msg = j.error; }
      catch (e) { /* not JSON */ }
      throw new Error(msg);
    }
    let head = null, tail = null, n = 0, err = null;
    const take = (line) => {
      if (!line) return;
      let o;
      try { o = JSON.parse(line); } catch (e) { return; }
      if (o.head !== undefined) {
        head = o.head;
        if (opts.onHead) opts.onHead(head);
      } else if (o.item !== undefined) {
        onItem(o.item, n);
        n += 1;
      } else if (o.done) {
        tail = o;
      } else if (o.error) {
        err = o;
      }
    };
    if (res.body && res.body.getReader && typeof TextDecoder !== 'undefined') {
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let at;
        while ((at = buf.indexOf('\n')) >= 0) {
          take(buf.slice(0, at));
          buf = buf.slice(at + 1);
        }
      }
      take(buf + dec.decode());
    } else {
      (await res.text()).split('\n').forEach(take);
    }
    if (err) {
      const e = new Error(err.error || 'The answer stopped part-way.');
      e.partial = n;
      throw e;
    }
    return { head, tail, n };
  }

  /* Everything kept about `url` -- in memory, in this browser, and the tag
     -- so the next `get` is a cold read. For a harness that means to see a
     cold open (web/_dev/motion.html), and for nothing else. */
  function forget(url) {
    mem.delete(url);
    saveTag(url, null);
    return BARRY.stash.forget(stashKey(url));
  }

  /* Last time's lists, into memory before anybody asks.

     Measured 2026-10-22 on a 4x-slowed CPU: the browser's store took longer
     than the 300-400 ms a view will wait for it, so the Event Bank drew its
     skeleton for 2.8 s on a second start although last time's list was
     sitting in the store. Read them once, when the page is first idle, and
     the views find them in memory -- `stale` then answers at once. Only the
     lists every session opens; each is a read of one stored value, and the
     live answer still replaces it. */
  const HYDRATE = ['/api/registry', '/api/bank', '/api/toolkit/scopes',
                   '/api/vacc/knows', '/api/people'];
  function hydrate() {
    for (const url of HYDRATE) {
      if (mem.has(url)) continue;
      BARRY.stash.get(stashKey(url), 10000).then((was) => {
        if (mem.has(url) || !was || !was.value || was.value.body === undefined) return;
        mem.set(url, { value: was.value.body, at: was.at || 0,
                       etag: was.value.etag || null, live: false });
      }).catch(() => { /* nothing kept */ });
    }
  }
  try {
    // The main window -- or a frame whose address asks (`?hydrate=1`, for
    // _dev/perf.html, which measures the page as a person meets it).
    // Other harness frames start cold, as their checks expect.
    if (window.top === window || /[?&]hydrate=1(?:&|$)/.test(location.search)) {
      const later = window.requestIdleCallback
        ? (fn) => window.requestIdleCallback(fn, { timeout: 1500 })
        : (fn) => setTimeout(fn, 200);
      later(hydrate);
    }
  } catch (e) { /* a frame of another origin: nothing kept here anyway */ }

  /* The two answers views kept by hand before this existed ('registry',
     'vacc-knows'). Kept here now, under their address; the old copies are
     two and a half megabytes nobody reads, so they go -- later, when the
     page is quiet, not on the way up. */
  setTimeout(() => {
    try { BARRY.stash.forget('registry'); BARRY.stash.forget('vacc-knows'); }
    catch (e) { /* nothing kept */ }
  }, 20000);

  return { get, watch, peek, stale, invalidate, stream, family, forget };
})();
