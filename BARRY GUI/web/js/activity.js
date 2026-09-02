/* ==========================================================================
   activity.js -- the audit trail.

   Every meaningful action gets recorded: which session was opened, which
   filter or colormap was chosen, which raster was switched to, which events
   were imported, what was downloaded, on which machine, by whom.

   Two things keep this from being a nuisance:

     * BATCHING. Entries queue in memory and flush every few seconds, so
       dragging a gain slider does not produce a hundred HTTP round trips.
     * COALESCING. Repeating the same action on the same session within a short
       window replaces the previous entry instead of appending, so scrubbing a
       time window logs where you ended up, not every frame on the way.
   ========================================================================== */
'use strict';

BARRY.activity = (function () {
  let queue = [];
  let timer = null;
  let enabled = true;

  const FLUSH_MS = 4000;
  const COALESCE_MS = 2500;
  // Actions where only the final value matters; anything else always appends.
  const COALESCE = new Set([
    'window.change', 'gain.change', 'filter.change', 'clim.change',
    'ylim.change', 'channels.change', 'colormap.change', 'spacing.change',
  ]);

  const history = [];

  function log(action, detail, session) {
    if (!enabled) return;
    const entry = {
      action,
      detail: detail || {},
      session: session ? briefSession(session) : undefined,
      view: BARRY.state.view,
      at: new Date().toISOString(),
      _t: Date.now(),
    };

    if (COALESCE.has(action)) {
      const key = action + '|' + ((entry.session || {}).key || '');
      for (let i = queue.length - 1; i >= 0; i--) {
        const q = queue[i];
        const qk = q.action + '|' + ((q.session || {}).key || '');
        if (qk === key && entry._t - q._t < COALESCE_MS) {
          queue[i] = entry;      // keep where they landed, not every step
          schedule();
          return;
        }
      }
    }

    queue.push(entry);
    if (queue.length > 200) queue.splice(0, queue.length - 200);
    // A second, separate ring that survives the flush. The queue is emptied
    // when it is sent, but a debug report needs the actions leading up to a
    // problem, which by then have already gone.
    history.push(entry);
    if (history.length > 300) history.splice(0, history.length - 300);
    schedule();
  }

  function briefSession(s) {
    // A session object, or an already-brief identity.
    const id = s.identity || s;
    return {
      key: id.key || null,
      loose_key: id.loose_key || null,
      label: id.label || s.name || null,
      mouse: id.mouse ?? null,
      session: id.session ?? null,
      path: id.path || s.path || null,
    };
  }

  function schedule() {
    if (timer) return;
    timer = setTimeout(flush, FLUSH_MS);
  }

  async function flush(sync) {
    clearTimeout(timer);
    timer = null;
    if (!queue.length) return;

    const batch = queue.map((e) => {
      const c = Object.assign({}, e);
      delete c._t;
      return c;
    });
    queue = [];

    const body = JSON.stringify({ entries: batch });
    if (sync && navigator.sendBeacon) {
      // On unload, fetch() is killed mid-flight; a beacon survives.
      navigator.sendBeacon('/api/activity', new Blob([body], { type: 'application/json' }));
      return;
    }
    try {
      await fetch('/api/activity', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body,
      });
    } catch (e) {
      // Never let the audit trail break the app; drop the batch and move on.
    }
  }

  function init() {
    window.addEventListener('beforeunload', () => flush(true));
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') flush(true);
    });
  }

  return {
    init, log, flush,
    setEnabled: (v) => { enabled = !!v; },
    pending: () => queue.length,
    /* What was done recently, for a debug report. Survives the flush. */
    recent: () => history.slice(),
  };
})();
