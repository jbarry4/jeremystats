'use strict';

/* ==========================================================================
   stash.js -- the last answer a view drew, kept in this browser.

   So a view can draw at once from what it showed last time, and then swap
   in the live answer when it lands, instead of showing nothing until the
   whole of it has arrived. The Sessions catalogue is the reason: its answer
   is cached on the server too (warmcache.py), but that cache is stamped
   with the code version, so the first open after every update rebuilt it
   live -- about four seconds, longer while the rest of start-up competed --
   and this lab updates several times a day.

   IndexedDB, not localStorage: the catalogue is two megabytes and
   localStorage is five in all, synchronous, and strings only.

   A convenience for this browser only (constitution section 10): nothing
   here is the truth, everything drawn from it is marked as last time's,
   and every failure -- private mode, a blocked database, a full disk --
   is "nothing stashed", never an error. `get` gives up after `wait`
   milliseconds, so a slow database can never delay the live answer.
   ========================================================================== */
BARRY.stash = (function () {
  const DB = 'jarvis-stash';
  const STORE = 'answers';
  let opening = null;

  function db() {
    if (opening) return opening;
    opening = new Promise((resolve) => {
      try {
        const req = indexedDB.open(DB, 1);
        req.onupgradeneeded = () => req.result.createObjectStore(STORE);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => resolve(null);
        req.onblocked = () => resolve(null);
      } catch (e) { resolve(null); }
    });
    return opening;
  }

  /* {at, value} or null. Never waits longer than `wait` ms. */
  function get(key, wait) {
    const timeout = new Promise((r) => setTimeout(() => r(null), wait || 400));
    const read = db().then((d) => new Promise((resolve) => {
      if (!d) { resolve(null); return; }
      try {
        const req = d.transaction(STORE, 'readonly').objectStore(STORE).get(key);
        req.onsuccess = () => resolve(req.result || null);
        req.onerror = () => resolve(null);
      } catch (e) { resolve(null); }
    }));
    return Promise.race([read, timeout]);
  }

  /* Kept a moment after it is asked, so writing two megabytes is never in
     the way of drawing them. */
  function put(key, value) {
    setTimeout(() => {
      db().then((d) => {
        if (!d) return;
        try {
          d.transaction(STORE, 'readwrite').objectStore(STORE)
            .put({ at: Date.now(), value }, key);
        } catch (e) { /* not kept; next time draws live, as before */ }
      });
    }, 1500);
  }

  /* "4 min ago", for the line that says a list is last time's. */
  function ago(at) {
    const s = Math.max(0, (Date.now() - (at || 0)) / 1000);
    if (s < 90) return 'a moment ago';
    if (s < 3600) return Math.round(s / 60) + ' min ago';
    if (s < 86400) return Math.round(s / 3600) + ' h ago';
    return Math.round(s / 86400) + ' d ago';
  }

  /* Drop one answer, so the next open draws live -- for a harness that
     means to see the cold open (web/_dev/motion.html). */
  function forget(key) {
    return db().then((d) => new Promise((resolve) => {
      if (!d) { resolve(); return; }
      try {
        const tx = d.transaction(STORE, 'readwrite');
        tx.objectStore(STORE).delete(key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      } catch (e) { resolve(); }
    }));
  }

  return { get, put, ago, forget };
})();
