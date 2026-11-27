/* Virtual time for filming: once __vt.start() is called, the page's clocks
   (performance.now, Date.now, requestAnimationFrame, setTimeout, setInterval)
   stop following the wall clock and move only when the film steps them, one
   frame at a time. Before that everything runs as usual (loading, setup). */
(() => {
  if (window.__vt) return;
  const real = {
    now: performance.now.bind(performance), dateNow: Date.now.bind(Date),
    raf: window.requestAnimationFrame.bind(window), caf: window.cancelAnimationFrame.bind(window),
    st: window.setTimeout.bind(window), ct: window.clearTimeout.bind(window),
    si: window.setInterval.bind(window), ci: window.clearInterval.bind(window),
  };
  const V = window.__vt = { on: false, t: 0, dateBase: 0, rafQ: new Map(), rafId: 1e7, timers: new Map(), tid: 1e7, real, errors: [] };
  performance.now = () => (V.on ? V.t : real.now());
  Date.now = () => (V.on ? Math.round(V.dateBase + V.t) : real.dateNow());
  window.requestAnimationFrame = (cb) => {
    if (V.on) { const id = ++V.rafId; V.rafQ.set(id, cb); return id; }
    return real.raf((ts) => cb(V.on ? V.t : ts));
  };
  window.cancelAnimationFrame = (id) => { if (V.rafQ.has(id)) V.rafQ.delete(id); else real.caf(id); };
  window.setTimeout = (fn, ms, ...args) => {
    if (!V.on) return real.st(fn, ms, ...args);
    const id = ++V.tid;
    V.timers.set(id, { due: V.t + Math.max(0, +ms || 0), fn, args, every: 0 });
    return id;
  };
  window.clearTimeout = (id) => { if (V.timers.has(id)) V.timers.delete(id); else real.ct(id); };
  window.setInterval = (fn, ms, ...args) => {
    if (!V.on) return real.si(fn, ms, ...args);
    const id = ++V.tid, every = Math.max(4, +ms || 0);
    V.timers.set(id, { due: V.t + every, fn, args, every });
    return id;
  };
  window.clearInterval = (id) => { if (V.timers.has(id)) V.timers.delete(id); else real.ci(id); };
  const run = (fn, args) => { try { if (typeof fn === 'function') fn(...(args || [])); } catch (e) { V.errors.push(String(e && e.stack || e).slice(0, 400)); } };
  V.start = () => { if (V.on) return V.t; V.t = real.now(); V.dateBase = real.dateNow() - V.t; V.on = true; return V.t; };
  V.stop = () => { V.on = false; const q = V.rafQ; V.rafQ = new Map(); q.forEach((cb) => real.raf((ts) => cb(ts))); };
  /* move the clock on by ms: timers fire in order, each at its own time */
  V.advance = (ms) => {
    const end = V.t + ms;
    for (let guard = 0; guard < 10000; guard++) {
      let best = null, bid = 0;
      for (const [id, tm] of V.timers) if (tm.due <= end && (!best || tm.due < best.due)) { best = tm; bid = id; }
      if (!best) break;
      V.t = Math.max(V.t, best.due);
      if (best.every) best.due += best.every; else V.timers.delete(bid);
      run(best.fn, best.args);
    }
    V.t = end;
  };
  /* one animation frame at the current time */
  V.frame = () => {
    const q = V.rafQ;
    V.rafQ = new Map();
    q.forEach((cb) => run(cb, [V.t]));
    return q.size;
  };
  /* let promises settle: a real task boundary or two */
  V.settle = (n) => new Promise((res) => { let k = n || 2; const go = () => (--k > 0 ? real.st(go, 0) : res()); real.st(go, 0); });
})();
