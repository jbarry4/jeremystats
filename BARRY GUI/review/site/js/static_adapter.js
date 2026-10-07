/* ==========================================================================
   static_adapter.js -- the review site's copy of the Monolith, fed from its
   own files.

   In Jarvis the Monolith page asks /api/arc/monolith for everything. Here
   it asks this instead (window.MONO_STATIC, read by js/monolith.js the way
   the harness's MONO_FIXTURE is), which answers from:

     data/summary.json, data/damage.json, data/events.json
     data/<array>.f32z            the pooled arrays and Progress's session
                                  files, gzipped
     data/ahead/<kind>/<key>.json what tools/export_review.py asked Jarvis
                                  ahead of time: the review's leads down to
                                  their rats, presentations and some traces,
                                  and the within-region PAC

   There is no live link to the cluster (2026-10-06): what was not copied
   says it opens in Jarvis. Nothing here writes: the buttons that split,
   run or add say so. Load order: before js/monolith.js.
   ========================================================================== */
'use strict';

(function () {
  const signIn = () => { location.href = '/login.html?next=' + encodeURIComponent(location.pathname + location.search + location.hash); };

  async function file(path) {
    const r = await fetch(path, { cache: 'no-cache' });
    if (r.status === 401) { signIn(); throw new Error('Sign in first.'); }
    if (!r.ok) throw new Error(path + ' is not in this review copy (HTTP ' + r.status + ').');
    return r.json();
  }
  // Gzipped bytes, or the plain bytes if something on the way already
  // opened them.
  async function gunzip(buf) {
    const u = new Uint8Array(buf);
    if (!(u.length > 2 && u[0] === 0x1f && u[1] === 0x8b)) return buf;
    const ds = new DecompressionStream('gzip');
    return new Response(new Blob([u]).stream().pipeThrough(ds)).arrayBuffer();
  }
  /* The name a request was copied ahead under: FNV-1a of its path, as
     tools/export_review.py works it out. */
  function keyOf(path) {
    let h = 0x811c9dc5;
    for (const b of new TextEncoder().encode(path)) { h ^= b; h = Math.imul(h, 0x01000193) >>> 0; }
    return h.toString(16).padStart(8, '0');
  }
  async function ahead(kind, path) {
    const r = await fetch('data/ahead/' + kind + '/' + keyOf(path) + '.json', { cache: 'no-cache' });
    if (r.status === 401) { signIn(); throw new Error('Sign in first.'); }
    if (r.ok) return Object.assign(await r.json(), { ahead: true });
    throw new Error(kind === 'leaf'
      ? 'This presentation’s traces were not copied into the review: they open in Jarvis, which reads them from the cluster.'
      : 'In this review copy, a line opens down to its rats and presentations when it is one of the review’s leads; '
        + 'any other line opens that far in Jarvis.');
  }
  function sameParams(path, params) {
    const q = new URLSearchParams(path.split('?')[1] || '');
    for (const [k, v] of q) if (params && params[k] != null && String(params[k]) !== v && Number(params[k]) !== Number(v)) return false;
    return true;
  }

  window.MONO_STATIC = {
    review: true,
    async json(path) {
      if (path === '/data/summary') return file('data/summary.json');
      if (path === '/damage') return file('data/damage.json');
      if (path === '/data/physical') return file('data/physical.json');
      if (path === '/status') return { ok: true, work: null };
      if (path.indexOf('/entry?') === 0) return ahead('entry', path);
      if (path.indexOf('/leaf?') === 0) return ahead('leaf', path);
      if (path.indexOf('/pacself?') === 0) return ahead('pacself', path);
      if (path.indexOf('/events/example?') === 0) {
        throw new Error('One event’s traces are read from the original recordings, so they open in Jarvis only.');
      }
      if (path === '/events' || path.indexOf('/events?') === 0) {
        const ev = await file('data/events.json');
        if (!sameParams(path, ev.params)) {
          throw new Error('Only the default settings were copied into this review; other settings are run in Jarvis.');
        }
        return ev;
      }
      throw new Error('Not in this review copy: ' + path);
    },
    async array(name, shape) {
      const want = shape.reduce((a, b) => a * b, 1) * 4;
      const r = await fetch('data/' + name + '.f32z');
      if (r.status === 401) { signIn(); throw new Error('Sign in first.'); }
      if (!r.ok) throw new Error(name + ' did not fit in this review copy: it opens in Jarvis.');
      const buf = await gunzip(await r.arrayBuffer());
      if (buf.byteLength !== want) throw new Error(name + ' is ' + buf.byteLength + ' bytes; its shape says ' + want + '.');
      return new Float32Array(buf);
    },
    async post() {
      throw new Error('This is the review copy: splitting, running and adding to the Monolith are done in Jarvis.');
    },
  };

  // Say what this is, at the top of the page, and the way back.
  document.addEventListener('monolith:ready', () => {
    const app = document.getElementById('app');
    if (!app || document.getElementById('reviewbar')) return;
    const bar = document.createElement('p');
    bar.id = 'reviewbar';
    bar.className = 'reviewbar';
    const a = document.createElement('a');
    a.href = 'index.html';
    a.textContent = '← The review';
    bar.appendChild(a);
    bar.appendChild(document.createTextNode(' · The review copy of the Monolith: read only. Every p is uncorrected.'));
    app.insertBefore(bar, app.firstChild);
  });
})();
