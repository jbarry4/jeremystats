/* ==========================================================================
   solid.js -- a click that feels like a click.

   Written 2026-11-03 for "a click to feel like a click ... like we are on
   SOLID HARD GROUND". What the person described was never one bug. It was
   the space between pressing something and the page admitting it had heard:

     - a fast click left no trace at all, because `:active` lasts as long as
       the mouse button is down and a quick press is over before the next
       frame is painted;
     - a button whose request took twelve seconds looked exactly like a
       button that had done nothing, so it was pressed again, and the second
       press queued a second copy of the work;
     - a server that had gone away (restarted, crashed, the laptop asleep)
       turned every press into a red toast, and whatever had been typed was
       lost with the request that carried it;
     - a list that was never going to arrive spun forever and nobody heard
       about it, so the daily triage never saw it either.

   So this file does five things, all of them page-side. The server half
   (backend/feed.py: the request lines, /api/ping, /api/restart) is written
   against the same contract and may not be there yet; everything here
   degrades to the old behaviour when a route is missing.

     1. The press.     A class on pointerdown, held for at least 110 ms, so
                       the press is drawn even when the click is quicker
                       than a frame.
     2. The busy control. A click remembers the control for the rest of its
                       task; api() calls started in that task belong to it.
                       It goes busy at once, gets a spinner on its corner
                       after 300 ms, says in words what the server is doing
                       after 3 s, and offers Stop after 20 s. A second click
                       on it while it is busy is swallowed.
     3. Offline.       A fetch that throws (nothing answered at all, not a
                       4xx or 5xx) puts the page into a calm reconnecting
                       state: reads the person asked for wait, writes they
                       make while it is away are held in order and sent
                       when the server is back, and the promise the caller
                       is holding resolves with the real answer. A write
                       that was already on its way when the server went is
                       never sent again (it may have been done), and a poll
                       nobody is waiting on fails at once, as it always did.
     4. Stuck.         A frozen page, a request over 30 s, or a spinner over
                       30 s with nothing moving says so in the feed, and is
                       filed once (per thing, per ten minutes) where the
                       daily error triage reads.
     5. Continuity.    The stale-server banner can restart the server, and a
                       reload puts each view's main list back where it was.

   A /_dev/ harness frame gets only the press (1) unless a test turns the rest
   on with `BARRY.solid._arm({...})`: the swallowed second click would break
   every harness that presses a chip twice, and an offline mode or a stuck
   report would turn a test's own stubbed failures into the lab's errors.
   ========================================================================== */
'use strict';

BARRY.solid = (function () {
  const arm = {
    busy: !HARNESS_FRAME,
    guard: !HARNESS_FRAME,
    offline: !HARNESS_FRAME,
    stuck: !HARNESS_FRAME,
    scroll: !HARNESS_FRAME,
  };

  /* ------------------------------------------------------------------------
     small words
     ------------------------------------------------------------------------ */
  function secs(ms) {
    const s = Math.max(0, Math.round(ms / 1000));
    if (s < 60) return s + ' s';
    return Math.floor(s / 60) + ' min ' + (s % 60) + ' s';
  }
  function num(n) {
    return (typeof n === 'number' && isFinite(n)) ? n.toLocaleString() : String(n);
  }
  function progressWords(line) {
    const p = line && line.progress;
    if (!p || p.length < 2 || !p[1]) return '';
    return ', ' + num(p[0]) + ' of ' + num(p[1]);
  }
  function viewName(v) {
    const n = v && document.querySelector('.nav-item[data-view="' + v + '"] span');
    const name = n ? n.textContent.trim() : (v || '');
    return name ? 'The ' + name + ' view' : 'This page';
  }
  function labelOf(c) {
    const words = (c.getAttribute('aria-label') || c.textContent || c.title || '')
      .replace(/\s+/g, ' ').trim();
    return words || 'that button';
  }
  function say(text, o) {
    try { if (BARRY.feed) BARRY.feed.say(text, o); } catch (e) { /* the feed is extra */ }
  }
  function feedLine(key) {
    try { return BARRY.feed ? BARRY.feed.lineFor(key) : null; } catch (e) { return null; }
  }
  /* A fetch of our own, never through api(): nothing here may be counted,
     attributed to a click, held while offline, or reported as a stale route
     (a missing /api/ping is an old server, not a fault). */
  function raw(path, init) {
    const o = Object.assign({ cache: 'no-store' }, init || {});
    if (HARNESS_FRAME) o.headers = Object.assign({}, o.headers, { 'X-Barry-Test': '1' });
    return fetch(path, o);
  }

  /* ------------------------------------------------------------------------
     1. The press
     ------------------------------------------------------------------------
     app.css already squishes `.btn:active`, and that is the look; this only
     makes it last long enough to be seen. A press shorter than a frame used
     to be drawn as nothing at all, which is the "did it hear me?" that
     starts a second click. */
  const PRESSABLE = 'button, .btn, .nav-item, [role="button"], .chip-btn';
  const HOLD_MS = 110;
  document.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    const t = e.target;
    const n = t && t.closest ? t.closest(PRESSABLE) : null;
    if (!n || n.disabled || n.getAttribute('aria-disabled') === 'true') return;
    n.classList.add('is-pressed');
    const t0 = performance.now();
    const up = () => {
      document.removeEventListener('pointerup', up, true);
      document.removeEventListener('pointercancel', up, true);
      const left = Math.max(0, HOLD_MS - (performance.now() - t0));
      setTimeout(() => n.classList.remove('is-pressed'), left);
    };
    document.addEventListener('pointerup', up, true);
    document.addEventListener('pointercancel', up, true);
  }, true);

  /* ------------------------------------------------------------------------
     2. The busy control
     ------------------------------------------------------------------------
     Which control a request belongs to is decided by WHEN it starts, not by
     anybody passing it along: 300 call sites of api() would each have needed
     a new argument, and the one that was forgotten would be the one that
     mattered. A click remembers its control until the task it ran in is
     over (setTimeout 0), and promise continuations run before that, so a
     handler that awaits something already settled still counts.

     A request that finishes hands the control on to its caller's next step
     the same way, so `await api(a); await api(b)` keeps one button busy from
     the first request to the end of the second instead of flickering
     between them. A step that waits on a timer first is a poll, not the
     click, and is let go. */
  const CONTROL = 'button, .btn, .nav-item, [role="button"], .chip-btn';
  let cur = null;
  let curTimer = null;
  function setCurrent(c) {
    cur = c;
    if (curTimer) clearTimeout(curTimer);
    curTimer = setTimeout(() => { cur = null; curTimer = null; }, 0);
  }
  function controlOf(t) {
    const n = t && t.closest ? t.closest(CONTROL) : null;
    if (!n || n.closest('[data-solid="off"], .solid-bubble, .solid-offline')) return null;
    return n;
  }
  /* Stop and Cancel must always be pressable: they are what you press
     BECAUSE something is busy. */
  /* Nor is moving about ever refused: a rail item still loading its view is
     busy, and going back to it from another view must still go. */
  function allowRepeat(c) {
    if (c.hasAttribute('data-allow-repeat')) return true;
    if (c.matches('.nav-item, [role="tab"]')) return true;
    const words = ((c.getAttribute('aria-label') || '') + ' ' + (c.textContent || ''))
      .trim();
    return /^(stop|cancel|abort)\b/i.test(words) || /cancel|stop/i.test(c.id || '');
  }

  const flights = new Map();   // request id -> flight
  const busy = new Map();      // control -> its record
  const TAB = Math.random().toString(16).slice(2, 6);
  let seq = 0;
  let lastMove = 0;            // a foreground request started or ended

  /* Whether a request was started by a PERSON, decided the same way as the
     control: by the task it starts in. A click anywhere (a list row is not
     a control and is still a person), a key, a change, a submit, a drop or
     the back button marks the rest of its task, and a request that ends
     hands the mark on to its caller's next step (end). A request started by
     a timer -- a poll, a beat, a debounced save -- is nobody's, and only a
     person's request is ever held while the server is away (finding of
     2026-11-03): a setInterval poll held instead of failed piled up one
     held copy per tick, thousands an hour, and they all went at once to a
     server that had only just started again. */
  let personNow = false;
  let personT = null;
  function setPerson() {
    personNow = true;
    if (personT) clearTimeout(personT);
    personT = setTimeout(() => { personNow = false; personT = null; }, 0);
  }
  ['keydown', 'change', 'submit', 'drop'].forEach((ev) =>
    document.addEventListener(ev, setPerson, true));
  window.addEventListener('popstate', setPerson, true);

  document.addEventListener('click', (e) => {
    const c = controlOf(e.target);
    if (!c) { setPerson(); return; }
    const rec = busy.get(c);
    if (rec && arm.guard && !allowRepeat(c)) {
      /* The second press of an impatient person. Swallowed, and answered:
         the spinner shows now rather than at 300 ms, because the second
         press is the proof that the first one looked like nothing. */
      e.preventDefault();
      e.stopImmediatePropagation();
      rec.nudged = true;
      paint(rec, Date.now());
      return;
    }
    setPerson();
    if (arm.busy) setCurrent(c);
  }, true);

  function attach(c, f) {
    let rec = busy.get(c);
    if (!rec) {
      rec = { c, flights: new Set(), jobs: new Set(), t0: Date.now(),
              spin: null, bubble: null, offerAt: 20000, nudged: false,
              hadAria: c.getAttribute('aria-busy') };
      busy.set(c, rec);
      c.classList.add('is-busy');
      c.setAttribute('aria-busy', 'true');
    }
    rec.flights.add(f);
    ticking();
  }
  function release(c) {
    const rec = busy.get(c);
    if (!rec) return;
    busy.delete(c);
    c.classList.remove('is-busy');
    if (rec.hadAria === null) c.removeAttribute('aria-busy');
    else c.setAttribute('aria-busy', rec.hadAria);
    if (rec.spin) rec.spin.remove();
    if (rec.bubble) rec.bubble.remove();
  }

  /* Called by api() in core.js as each request starts. Never throws: a fault
     in here must cost the feel, not the request. */
  function begin(route, opts, bg) {
    try {
      const id = TAB + '-' + (++seq);
      const ctl = typeof AbortController === 'function' ? new AbortController() : null;
      const theirs = opts && opts.signal;
      if (ctl && theirs) {
        if (theirs.aborted) ctl.abort();
        else theirs.addEventListener('abort', () => ctl.abort(), { once: true });
      }
      const f = { id, route, method: ((opts && opts.method) || 'GET').toUpperCase(),
                  t0: Date.now(), bg: !!bg, ctl, control: null, stopped: false,
                  view: BARRY.state.view };
      if (!bg) lastMove = Date.now();
      if (!bg && arm.busy && cur && cur.isConnected) {
        f.control = cur;
        attach(cur, f);
      }
      f.person = !bg && !!(f.control || personNow);
      flights.set(id, f);
      return { id, signal: ctl ? ctl.signal : theirs, f };
    } catch (e) { return null; }
  }

  function end(tok, out) {
    try {
      const f = tok.f;
      flights.delete(f.id);
      if (!f.bg) lastMove = Date.now();
      if (offline.on && out !== undefined) tryNow();
      if (f.person) setPerson();
      const c = f.control;
      const rec = c && busy.get(c);
      if (!rec) return;
      rec.flights.delete(f);
      const job = out && ((out.job && out.job.id) || out.job_id);
      if (job) rec.jobs.add(String(job));
      setCurrent(c);
      if (!rec.flights.size) {
        setTimeout(() => { if (!rec.flights.size) release(c); }, 0);
      }
    } catch (e) { /* see begin */ }
  }

  function wasStopped(id) {
    const f = id && flights.get(id);
    return !!(f && f.stopped);
  }

  /* What apiCall says about a request Stop aborted. Aborting only stops the
     browser waiting: a write that had reached the server is still carried
     out there, so "it was stopped" would send the person to press it again
     and do it twice (two bank versions, two runs). A read has nothing to
     undo, so it may say plainly that it stopped. Starts with "Stopped"
     either way, which driftmono.js tests for. */
  function stopWords(id) {
    const f = id && flights.get(id);
    if (f && f.stopped && f.method !== 'GET') {
      return 'Stopped waiting: you pressed Stop, but the server may still finish this. '
        + 'Check whether it was done before doing it again.';
    }
    return 'Stopped: you pressed Stop, so the request was aborted.';
  }

  /* One timer for every busy control, and only while there is one. */
  let tickT = null;
  function ticking() {
    if (tickT) return;
    tickT = setInterval(() => {
      if (!busy.size) { clearInterval(tickT); tickT = null; return; }
      const now = Date.now();
      for (const rec of busy.values()) paint(rec, now);
    }, 250);
  }

  function inOverlay(c) {
    return !!c.closest('.modal-backdrop, .modal, [role="dialog"], .popover, [id$="Pop"]');
  }

  /* The spinner and the bubble live at the end of <body>, positioned over
     the control, never inside it. Inside, they would change its width and
     its text, a `sections` rebuild would take them with it, and every
     harness that reads a button's children would read them too. */
  function paint(rec, now) {
    const c = rec.c;
    if (!c.isConnected) { release(c); return; }
    const age = now - rec.t0;
    const r = c.getBoundingClientRect();
    const shown = r.width > 0 && r.height > 0;
    const hi = inOverlay(c);
    if (age >= 300 || rec.nudged) {
      if (!rec.spin) {
        rec.spin = el('div', { class: 'solid-spin', 'aria-hidden': 'true' });
        document.body.appendChild(rec.spin);
      }
      rec.spin.classList.toggle('hi', hi);
      rec.spin.hidden = !shown;
      // On the control's top-right corner, like a badge, so it never sits
      // over the words.
      rec.spin.style.left = Math.round(Math.min(innerWidth - 16, r.right - 9)) + 'px';
      rec.spin.style.top = Math.round(Math.max(2, r.top - 5)) + 'px';
    }
    if (age >= 3000) bubble(rec, age, r, shown, hi);
  }

  function bubble(rec, age, r, shown, hi) {
    if (!rec.bubble) {
      const sayN = el('p', { class: 'sb-say' });
      const acts = el('div', { class: 'sb-acts', hidden: 'hidden' }, [
        el('button', { class: 'btn sm', text: 'Stop', 'data-allow-repeat': '',
                       onclick: () => stop(rec) }),
        el('button', { class: 'btn ghost sm', text: 'Keep waiting', 'data-allow-repeat': '',
                       onclick: () => {
                         rec.offerAt = (Date.now() - rec.t0) + 60000;
                         acts.hidden = true;
                       } }),
      ]);
      rec.bubble = el('div', { class: 'solid-bubble', role: 'status' }, [sayN, acts]);
      rec.bubble._say = sayN;
      rec.bubble._acts = acts;
      rec.bubble._stop = acts.firstChild;
      document.body.appendChild(rec.bubble);
    }
    const b = rec.bubble;
    b.classList.toggle('hi', hi);
    b.hidden = !shown;
    /* On a write that has gone to the server the button can only stop the
       waiting, not the work, and says so (see stop). */
    const stopText = sentWrite(rec) ? 'Stop waiting' : 'Stop';
    if (b._stop && b._stop.textContent !== stopText) b._stop.textContent = stopText;
    const text = bubbleWords(rec) + ' · ' + secs(age);
    if (b._say.textContent !== text) b._say.textContent = text;
    if (age >= rec.offerAt) b._acts.hidden = false;
    if (!shown) return;
    // Beside a rail item, under anything else, above it when there is no
    // room below. Clamped inside the window; the text wraps, never clips.
    const w = b.offsetWidth;
    const h = b.offsetHeight;
    let left;
    let top;
    if (rec.c.closest('#rail')) {
      left = r.right + 8;
      top = r.top;
    } else {
      left = r.left;
      top = r.bottom + 6;
      if (top + h > innerHeight - 8) top = r.top - h - 6;
    }
    left = Math.max(16, Math.min(left, innerWidth - w - 16));
    top = Math.max(8, Math.min(top, innerHeight - h - 8));
    b.style.left = Math.round(left) + 'px';
    b.style.top = Math.round(top) + 'px';
  }

  function bubbleWords(rec) {
    if (offline.on) return 'Waiting for the server to come back.';
    let line = null;
    for (const f of rec.flights) {
      const l = feedLine('req:' + f.id);
      if (l && (!line || (l.at || 0) >= (line.at || 0))) line = l;
    }
    if (line) return line.text + progressWords(line);
    return 'Still waiting for the server to answer.';
  }

  /* A write of this control's that has left the page: not one still held
     here waiting for the server, which Stop really does take back. */
  function sentWrite(rec) {
    for (const f of rec.flights) {
      if (f.method !== 'GET' && !held.some((i) => i.f === f)) return true;
    }
    return false;
  }

  /* Stop aborts the browser's side. For a read, or a write still held here,
     that is the whole of it. A write the server has already been sent goes
     on there whatever the browser does (only a job id it answered with can
     be cancelled, and the request that starts a job has not answered yet),
     so the words say the waiting stopped and the change may still be made,
     never that it was undone: told "stopped", people pressed it again and
     got the work twice. */
  function stop(rec) {
    const label = labelOf(rec.c);
    const unsure = sentWrite(rec);
    for (const f of rec.flights) {
      f.stopped = true;
      if (f.ctl) f.ctl.abort();
    }
    for (const id of rec.jobs) {
      raw('/api/job/' + encodeURIComponent(id) + '/cancel',
          { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
        .catch(() => {});
    }
    const after = secs(Date.now() - rec.t0);
    say(unsure
      ? 'Stopped waiting for "' + label + '" after ' + after + '. The server may still '
        + 'finish it, so check whether it was done before doing it again.'
      : 'Stopped "' + label + '" after ' + after + '.',
        { level: 'warn' });
    release(rec.c);
  }

  /* ------------------------------------------------------------------------
     3. Offline
     ------------------------------------------------------------------------
     Only a fetch that THROWS counts: nothing answered at all. A 500 is the
     server answering, and goes back to its caller as before.

     The first throw is checked with one ping before anything is held. When
     the server answers that ping it is up, and only this one connection
     dropped -- maybe halfway through being answered. A read is simply asked
     again. When the ping fails too, the server is away, and from then on the
     reads a person asked for wait.

     A write whose own fetch threw is never held or sent again, whatever the
     ping says: it left the page, and the server may have done it before it
     went (a bank commit that had already been written, then a crash). Sent
     again on the next server it would be done twice. Its caller is told in
     a sentence to check and do it again if it is not there. Only a write
     the person makes once the page already KNOWS the server is away is
     held, and it is held before it is sent (inLine), so it is sent exactly
     once, by flush.

     While any write is held or being sent again, every new write the person
     makes joins the end of the same line instead of going straight out.
     Otherwise a change made in the seconds after the server came back
     (offline.on stays true until the next ping) went first, and the older
     held one was sent on top of it: "keep" on screen, "garbage" on the
     server.

     Requests nobody is waiting on -- polls, beats, anything a timer started
     -- are never held. They fail at once, as they did before any of this,
     and a ping is sent to find out whether to show the banner. */
  const offline = { on: false, since: 0, tries: 0, nextAt: 0, timer: null,
                    banner: null, backT: null, flushing: false };
  const held = [];
  const DELAYS = [500, 1000, 2000, 4000, 5000];

  async function ping(ms) {
    const ctl = typeof AbortController === 'function' ? new AbortController() : null;
    const t = ctl ? setTimeout(() => ctl.abort(), ms || 3000) : null;
    try {
      const res = await raw('/api/ping', ctl ? { signal: ctl.signal } : {});
      let boot = null;
      if (res.ok) {
        try { const d = await res.json(); boot = (d && d.boot) || null; }
        catch (e) { /* an answer is an answer */ }
      }
      // Any answer, a 404 included, means somebody is there.
      return { up: true, boot };
    } catch (e) {
      return { up: false, boot: null };
    } finally {
      if (t) clearTimeout(t);
    }
  }

  function abortError() {
    const e = new Error('Stopped: the request was aborted before it was sent.');
    e.name = 'AbortError';
    return e;
  }

  /* apiCall's catch hands every thrown fetch here. `err` is what it would
     have thrown; `resend()` asks again once, and throws `err.unreachable`
     rather than coming back here when the server is still away. */
  async function unreachable(path, opts, err, resend) {
    if (!arm.offline) throw err;
    const method = ((opts && opts.method) || 'GET').toUpperCase();
    const f = (opts && opts.reqId && flights.get(opts.reqId)) || null;
    if (!f || !f.person) {
      // Nobody is waiting on it: fail now, as before, and let a ping decide
      // whether the banner should go up.
      suspect();
      err.unreachable = true;
      throw err;
    }
    if (method !== 'GET') {
      suspect();
      throw maybeDone();
    }
    if (!offline.on) {
      const p = await ping(1500);
      if (p.up) {
        sawBoot(p.boot);
        try { return await resend(); } catch (e) {
          if (!e.unreachable) throw e;
        }
      }
      goOffline();
    }
    return hold(path, method, opts, resend, f);
  }

  function maybeDone() {
    return new Error('The server stopped answering while this was being sent, so it '
                     + 'may or may not have been done. Check, then do it again if it '
                     + 'is not there.');
  }

  /* Called by apiCall just before its fetch, for a request that is not a
     resend. Returns a promise when the request must wait its turn instead
     of going out now: a write the person makes while the server is known to
     be away, or while earlier writes are still held or being sent. Null
     means send it now. */
  function inLine(path, opts, resend) {
    try {
      if (!arm.offline) return null;
      const method = ((opts && opts.method) || 'GET').toUpperCase();
      if (method === 'GET') return null;
      const f = (opts && opts.reqId && flights.get(opts.reqId)) || null;
      if (!f) return null;
      /* A write a timer made (a debounced save) is not held while the
         server is away -- nobody is waiting on it, and it fails as it always
         did. But while the server is up and older held writes are still
         going out, it queues behind them like a person's: sent straight
         away, it would land first and the older held write on top of it. */
      if (!f.person && offline.on) return null;
      const waiting = offline.on || offline.flushing
        || held.some((i) => i.method !== 'GET');
      if (!waiting) return null;
      const p = hold(path, method, opts, resend, f);
      if (!offline.on) flush();
      return p;
    } catch (e) { return null; }
  }

  function hold(path, method, opts, resend, f) {
    return new Promise((resolve, reject) => {
      const sig = opts && opts.signal;
      const item = { path, method, resend, resolve, reject, f: f || null, sig: sig || null };
      if (sig) {
        if (sig.aborted) { reject(abortError()); return; }
        /* Only while it is still held here is it truly not sent. Once flush
           has taken it, its own fetch is aborted too, and the answer that
           gives (core.js, stopWords) is the one that says what happened. */
        sig.addEventListener('abort', () => {
          const i = held.indexOf(item);
          if (i < 0) return;
          held.splice(i, 1);
          banner();
          reject(abortError());
        }, { once: true });
      }
      held.push(item);
      banner();
    });
  }

  function goOffline() {
    if (offline.on) { banner(); return; }
    offline.on = true;
    offline.since = Date.now();
    offline.tries = 0;
    if (offline.backT) { clearTimeout(offline.backT); offline.backT = null; }
    BARRY.debug.note('warn', 'offline: the server stopped answering');
    schedule();
    banner();
  }

  function schedule() {
    if (offline.timer) clearTimeout(offline.timer);
    const wait = DELAYS[Math.min(offline.tries, DELAYS.length - 1)];
    offline.nextAt = Date.now() + wait;
    offline.timer = setTimeout(attempt, wait);
  }

  async function attempt() {
    offline.timer = null;
    if (!offline.on) return;
    offline.tries += 1;
    banner();
    const p = await ping(3000);
    if (!offline.on) return;
    if (p.up) back(p.boot);
    else schedule();
  }

  function tryNow() {
    if (!offline.on) return;
    if (offline.timer) clearTimeout(offline.timer);
    offline.timer = null;
    attempt();
  }

  function back(boot) {
    const away = Date.now() - offline.since;
    offline.on = false;
    if (offline.timer) { clearTimeout(offline.timer); offline.timer = null; }
    const restarted = sawBoot(boot);
    if (!restarted) {
      say('Back in touch with the server after ' + secs(away) + '.', { level: 'ok' });
    }
    banner();
    flush();
    try { if (BARRY.feed && BARRY.feed._kick) BARRY.feed._kick(); } catch (e) { /* extra */ }
  }

  /* Reads go together; writes go one at a time in the order they were made,
     each waiting for the one before. Each write is taken off the front of
     the line only as it is sent, so the rest stay held (and Stop on one of
     them still takes it back), and writes made meanwhile join the end of
     the same line (inLine). It goes on until the line is empty or the
     server is away again; a call while one is running returns, because the
     running one will reach anything added, and anything left once it ends
     with the server up is sent by another pass rather than left waiting for
     a reconnect that will never come. */
  async function flush() {
    if (offline.flushing) return;
    offline.flushing = true;
    try {
      while (!offline.on && held.length) {
        for (let i = 0; i < held.length;) {
          if (held[i].method === 'GET') run(held.splice(i, 1)[0]);
          else i++;
        }
        const k = held.findIndex((i) => i.method !== 'GET');
        if (k < 0) break;
        await run(held.splice(k, 1)[0]);
      }
    } finally {
      offline.flushing = false;
      banner();
      if (!offline.on && held.length) setTimeout(flush, 0);
    }
  }

  /* A held read that finds the server gone again is held again. A held
     write that does is not: it was sent, and may have been done, so it is
     answered like any write whose fetch threw (maybeDone), and the writes
     behind it, never sent, wait for the server. */
  async function run(item) {
    if (item.sig && item.sig.aborted) { item.reject(abortError()); return; }
    try {
      item.resolve(await item.resend());
    } catch (e) {
      if (e && e.unreachable) {
        if (item.method === 'GET') held.push(item);
        else item.reject(maybeDone());
        goOffline();
        return;
      }
      item.reject(e);
    }
  }

  /* Calm on purpose: amber edge, no red, no toast. The server going away is
     a wait, not a failure, and nothing the person did is lost. */
  let bannerTick = null;
  function banner() {
    let b = offline.banner;
    const writes = held.filter((i) => i.method !== 'GET').length;
    if (offline.on) {
      if (!b || !b.isConnected) {
        b = offline.banner = el('div', { class: 'solid-offline', role: 'status' }, [
          el('span', { class: 'so-dot', 'aria-hidden': 'true' }),
          el('strong', { class: 'so-head' }),
          el('span', { class: 'so-tries' }),
          el('span', { class: 'so-held' }),
          el('button', { class: 'btn ghost sm', text: 'Try now', 'data-allow-repeat': '',
                         onclick: () => tryNow() }),
        ]);
        document.body.appendChild(b);
      }
      b.classList.remove('back');
      const tryBtn = b.querySelector('button');
      if (tryBtn) tryBtn.hidden = false;
      const left =Math.max(0, Math.ceil((offline.nextAt - Date.now()) / 1000));
      b.querySelector('.so-head').textContent = 'Reconnecting…';
      b.querySelector('.so-tries').textContent = offline.timer
        ? 'tried ' + offline.tries + (offline.tries === 1 ? ' time' : ' times')
          + ', next try in ' + left + ' s'
        : 'trying now';
      b.querySelector('.so-held').textContent = writes
        ? writes + (writes === 1 ? ' change' : ' changes') + ' waiting to be sent'
        : 'Anything you do meanwhile is sent once it is back.';
      if (!bannerTick) bannerTick = setInterval(banner, 500);
      return;
    }
    if (bannerTick) { clearInterval(bannerTick); bannerTick = null; }
    if (!b || !b.isConnected || b.classList.contains('back')) return;
    b.classList.add('back');
    b.querySelector('.so-head').textContent = 'Back';
    b.querySelector('.so-tries').textContent = '';
    b.querySelector('.so-held').textContent = writes
      ? 'sending ' + writes + (writes === 1 ? ' change' : ' changes') + '…' : '';
    const btn = b.querySelector('button');
    if (btn) btn.hidden = true;
    offline.backT = setTimeout(() => {
      offline.backT = null;
      if (!offline.on && b.isConnected) b.remove();
      if (offline.banner === b) offline.banner = null;
    }, 1600);
  }

  /* The feed's poll failing twice is the same news, heard sooner. So is a
     poll or a write failing (unreachable). One ping at a time, however many
     pollers fail together. */
  let suspecting = false;
  async function suspect() {
    if (!arm.offline || offline.on || suspecting) return;
    suspecting = true;
    try {
      const p = await ping(1500);
      if (!p.up) goOffline();
      else sawBoot(p.boot);
    } finally {
      suspecting = false;
    }
  }

  /* One judge of "the server restarted", whoever saw the new id first: the
     ping, the feed's hello or a feed answer. Returns whether it changed. */
  let boot = null;
  function sawBoot(b) {
    if (!b) return false;
    if (boot && b !== boot) {
      boot = b;
      try { if (BARRY.feed && BARRY.feed.restarted) BARRY.feed.restarted(); }
      catch (e) { /* extra */ }
      return true;
    }
    boot = b;
    return false;
  }

  /* ------------------------------------------------------------------------
     4. Stuck
     ------------------------------------------------------------------------
     Three kinds, each said in the feed in words and filed once per thing per
     ten minutes as `client.error` with where = 'stuck', the record the daily
     triage reads. Filed directly rather than through reportClientError: that
     one puts a red box across the top of the page and an "Interface error"
     toast up, which is right for an exception and wrong for "this list is
     slow", and the feed line already said it calmly. The record it writes is
     the same shape.

     A spinner counts only when nothing is moving: no foreground request
     started or ended, and no unfinished feed line arrived, in the last 10 s.
     A Panorama run shows a loader for minutes while it polls its job, and
     that is not stuck; a loader with nothing at all going on behind it is. */
  const told = new Map();
  function once(thing) {
    const t = told.get(thing);
    if (t && Date.now() - t < 10 * 60 * 1000) return false;
    told.set(thing, Date.now());
    return true;
  }
  function stuck(thing, words, ctx) {
    if (!arm.stuck || !once(thing)) return;
    say(words, { level: 'warn' });
    try { BARRY.debug.note('warn', 'stuck: ' + words); } catch (e) { /* early */ }
    let lines = [];
    try { lines = BARRY.feed ? BARRY.feed.recent(20) : []; } catch (e) { /* none */ }
    const view = BARRY.state.view || null;
    const detail = JSON.stringify(Object.assign({ view, lines }, ctx || {}));
    raw('/api/activity', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entries: [{
        action: 'client.error',
        detail: { where: 'stuck', message: words, detail: detail.slice(0, 4000) },
        view,
      }] }),
    }).catch(() => {});
  }

  const SPINNERS = '.spin, .loader, .loading, .plot-loading, .step-loader, [aria-busy="true"]';
  const spinSince = new Map();
  function describe(n) {
    return n.tagName.toLowerCase()
      + (n.id ? '#' + n.id : '')
      + Array.from(n.classList).slice(0, 3).map((c) => '.' + c).join('');
  }
  function liveFeed(since) {
    try { return !!(BARRY.feed && BARRY.feed.liveSince(since)); } catch (e) { return false; }
  }

  function scan() {
    if (!arm.stuck || document.hidden) return;
    const now = Date.now();
    for (const f of flights.values()) {
      if (f.bg) continue;
      const ms = now - f.t0;
      if (ms < 30000) continue;
      const l = feedLine('req:' + f.id);
      const words = viewName(f.view) + ' has been waiting ' + secs(ms)
        + ' for the server' + (offline.on ? ', which is not answering at all'
          : l ? '; the server says: ' + l.text + progressWords(l)
            : ', and the server has said nothing about what it is doing') + '.';
      stuck('req:' + f.view + ':' + f.route, words,
            { kind: 'request', route: f.route, method: f.method, ms });
    }
    const moving = now - lastMove < 10000 || liveFeed(now - 10000);
    const seen = new Set();
    for (const n of document.querySelectorAll(SPINNERS)) {
      if (n.classList.contains('is-busy')
          || n.closest('#logDock, #boot, .solid-bubble, .solid-offline')) continue;
      if (!n.getClientRects().length) continue;
      seen.add(n);
      if (!spinSince.has(n)) spinSince.set(n, now);
      const ms = now - spinSince.get(n);
      if (ms < 30000 || moving || offline.on) continue;
      const v = BARRY.state.view;
      const l = lastLiveLine();
      const words = viewName(v) + ' has been showing that it is loading for '
        + secs(ms) + ' with nothing happening behind it'
        + (l ? '; the server last said: ' + l.text + progressWords(l) : '') + '.';
      stuck('spin:' + v + ':' + describe(n), words,
            { kind: 'spinner', what: describe(n), ms, route: null });
    }
    for (const n of Array.from(spinSince.keys())) if (!seen.has(n)) spinSince.delete(n);
  }
  function lastLiveLine() {
    try {
      const r = BARRY.feed ? BARRY.feed.recent(20) : [];
      for (let i = r.length - 1; i >= 0; i--) if (r[i].lane !== 'vacc') return r[i];
    } catch (e) { /* none */ }
    return null;
  }
  setInterval(scan, 5000);

  /* A long task is the page itself frozen: no click is drawn, nothing
     scrolls. Over a second is worth a word. */
  try {
    if (typeof PerformanceObserver === 'function') {
      new PerformanceObserver((list) => {
        for (const e of list.getEntries()) {
          if (e.duration <= 1000) continue;
          const v = BARRY.state.view;
          const vn = viewName(v);
          stuck('long:' + v,
                'The page froze for ' + (e.duration / 1000).toFixed(1) + ' s'
                + (vn === 'This page' ? '' : ' in ' + vn.replace(/^The /, 'the ')) + '.',
                { kind: 'longtask', ms: Math.round(e.duration), route: null });
        }
      }).observe({ entryTypes: ['longtask'] });
    }
  } catch (e) { /* not in this browser */ }

  /* ------------------------------------------------------------------------
     5a. Restart, from the stale-server banner
     ------------------------------------------------------------------------
     The banner used to end in "close the window and run Start again", which
     is three steps and a hunt for a console window. The server can restart
     itself when its launcher started it (POST /api/restart); when it cannot
     it says so, and the banner says how. Either way the page waits for a
     server with a new boot id and reloads itself onto it, and the view
     comes back from the address. */
  function restartControl() {
    const sayN = el('span', { class: 'solid-restart-say' });
    const btn = el('button', { class: 'btn sm', text: 'Restart now', 'data-allow-repeat': '' });
    btn.addEventListener('click', () => restart(btn, sayN));
    return el('span', { class: 'solid-restart' }, [btn, sayN]);
  }

  async function post(path, body) {
    let res;
    try {
      res = await raw(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify(body || {}) });
    } catch (e) { return { down: true }; }
    if (res.status === 404 || res.status === 405) return { missing: true };
    try { return { data: await res.json() }; } catch (e) { return { missing: true }; }
  }

  let restarting = false;
  async function restart(btn, sayN) {
    if (restarting) return;
    restarting = true;
    btn.disabled = true;
    const tell = (t) => { sayN.textContent = t; };
    tell('Asking the server to restart…');
    const before = (await ping(2000)).boot || boot;
    let r = await post('/api/restart', { force: false });
    const d = r.data || {};
    if (d.ok === false && d.running && d.running.length) {
      const yes = BARRY.confirm
        ? await BARRY.confirm('Restart and stop what is running?',
            'These will stop: ' + d.running.join(', ') + '.', 'Restart anyway', true)
        : window.confirm('These will stop: ' + d.running.join(', ') + '. Restart anyway?');
      if (!yes) {
        tell('');
        btn.disabled = false;
        restarting = false;
        return;
      }
      r = await post('/api/restart', { force: true });
    }
    const d2 = r.data || {};
    if (r.missing) {
      tell('This server is too old to restart itself. Close its window and start '
           + 'it again; this page reloads by itself once it is back.');
    } else if (d2.ok === false && d2.manual) {
      tell((d2.error ? d2.error + ' ' : 'It was not started by the launcher, so it '
            + 'cannot restart itself. ') + 'Close its window and start it again; this '
            + 'page reloads by itself once it is back.');
    } else if (d2.ok === false && !r.down) {
      tell(d2.error || 'The server would not restart.');
      btn.disabled = false;
      restarting = false;
      return;
    } else {
      tell('Restarting…');
    }
    watch(before, tell, !r.missing && !(d2.ok === false), btn);
  }

  /* Waits for the new server. With no boot id to compare (an old server
     without /api/ping), it waits to see it go and come back instead. */
  async function watch(before, tell, saidYes, btnOf) {
    const t0 = Date.now();
    let wentAway = false;
    for (let i = 0; ; i++) {
      await new Promise((r) => setTimeout(r, DELAYS[Math.min(i, DELAYS.length - 1)]));
      const p = await ping(3000);
      if (!p.up) { wentAway = true; continue; }
      const fresh = p.boot ? (p.boot !== before) : wentAway;
      if (fresh) {
        /* Anything written while it was away goes first, however long that
           takes. This used to give up after 10 s and reload anyway, and the
           reload threw away every change still held -- the ones the banner
           had promised would be sent. A held read is not waited for: the
           reloaded page asks for it again. Each held write is either sent
           or answered once the server is up (flush never holds one twice),
           so this ends; if the server goes away again it waits for it. */
        for (;;) {
          const n = held.filter((i) => i.method !== 'GET').length;
          if (!n && !offline.flushing) break;
          /* Hurry the reconnect only when its next try is a while off: every
             250 ms against a server that has dropped again is four refused
             pings a second, which the backoff exists to prevent. */
          if (offline.on && offline.timer
              && (offline.nextAt || 0) - Date.now() > 1000) tryNow();
          tell(n ? 'Sending ' + n + (n === 1 ? ' change' : ' changes')
                   + ' you made while it was away, then reloading…'
                 : 'Sending the last change you made while it was away, then reloading…');
          await new Promise((r) => setTimeout(r, 250));
        }
        try { saveScroll(); } catch (e) { /* best effort */ }
        location.reload();
        return;
      }
      const s = Date.now() - t0;
      if (s > 10 * 60 * 1000) {
        // Nobody restarted it. Stop asking, and let the button be pressed again.
        tell('Still the same server after ten minutes. Press Restart now to try again.');
        restarting = false;
        if (btnOf) btnOf.disabled = false;
        return;
      }
      if (saidYes) tell('Restarting… ' + secs(s));
      if (s > 60000 && saidYes) {
        tell('Not back after a minute. If its window closed, start it again; '
             + 'this page reloads by itself once it answers.');
        saidYes = false;
      }
    }
  }

  /* ------------------------------------------------------------------------
     5b. Where you were, after a reload
     ------------------------------------------------------------------------
     Best effort and small: each view's main scroller (one at least 40% of
     the view's height, so a dropdown's list does not count) is remembered
     by a selector path from its view, in this tab's sessionStorage. After a
     reload, a view shown in the first 30 s is put back once it has painted
     enough to scroll that far. Touching the wheel or the keys first means
     the person has moved on, and they are not fought. */
  const SKEY = 'barry.solid.scroll';
  let marks = {};
  try { marks = JSON.parse(sessionStorage.getItem(SKEY) || '{}') || {}; }
  catch (e) { marks = {}; }
  let reloaded = false;
  try {
    const nav = performance.getEntriesByType('navigation')[0];
    reloaded = !!(nav && nav.type === 'reload');
  } catch (e) { /* older browser: no restore */ }
  let pending = (reloaded && arm.scroll) ? Object.assign({}, marks) : {};

  function pathOf(n, root) {
    const parts = [];
    for (; n && n !== root; n = n.parentElement) {
      if (n.id) { parts.unshift('#' + CSS.escape(n.id)); return parts.join(' > '); }
      const cls = Array.from(n.classList)
        .filter((c) => !/^(is-|ui-|mo-|active$|on$|open$|hidden$)/.test(c))
        .slice(0, 2).map((c) => '.' + CSS.escape(c)).join('');
      parts.unshift(n.tagName.toLowerCase() + cls);
    }
    return ':scope > ' + parts.join(' > ');
  }
  function saveScroll() {
    try { sessionStorage.setItem(SKEY, JSON.stringify(marks)); } catch (e) { /* private */ }
  }
  let saveT = null;
  document.addEventListener('scroll', (e) => {
    if (!arm.scroll) return;
    const t = e.target;
    if (!t || t.nodeType !== 1) return;
    const view = t.closest('.view.active');
    if (!view || !view.id || t.clientHeight < view.clientHeight * 0.4) return;
    marks[view.id.replace(/^view-/, '')] = { path: pathOf(t, view), top: Math.round(t.scrollTop) };
    if (saveT) clearTimeout(saveT);
    saveT = setTimeout(saveScroll, 400);
  }, { capture: true, passive: true });
  window.addEventListener('pagehide', saveScroll);
  ['wheel', 'keydown', 'touchstart'].forEach((ev) => document.addEventListener(ev, () => {
    const v = BARRY.state.view;
    if (v && pending[v]) delete pending[v];
  }, { capture: true, passive: true }));

  if (Object.keys(pending).length) {
    const t0 = Date.now();
    const rt = setInterval(() => {
      if (Date.now() - t0 > 30000 || !Object.keys(pending).length) {
        clearInterval(rt);
        pending = {};
        return;
      }
      const v = BARRY.state.view;
      const m = pending[v];
      const root = m && document.getElementById('view-' + v);
      if (!root || !root.classList.contains('active')) return;
      let n = null;
      try { n = root.querySelector(m.path); } catch (e) { delete pending[v]; return; }
      if (!n) return;
      if (n.scrollHeight - n.clientHeight >= m.top - 2) {
        n.scrollTop = m.top;
        delete pending[v];
      }
    }, 250);
  }

  return {
    begin, end, wasStopped, stopWords, unreachable, inLine, suspect, sawBoot,
    restartControl,
    get boot() { return boot; },
    get offline() { return offline.on; },
    /* For web/_dev/solid.html, which runs in a harness frame where all of
       this starts off. `_arm({busy, guard, offline, stuck, scroll})`. */
    _arm(o) { Object.assign(arm, o || {}); return Object.assign({}, arm); },
    /* `_offline(true)` arms the offline mode in a harness frame, so the next
       thrown fetch enters it; false disarms it and, if it is in, tries at
       once so held requests are not left waiting on a test's stub. */
    _offline(on) {
      arm.offline = !!on;
      if (!on && offline.on) tryNow();
      return offline.on;
    },
    _state() {
      return { offline: offline.on, tries: offline.tries, held: held.length,
               busy: busy.size, flights: flights.size, boot };
    },
  };
}());
