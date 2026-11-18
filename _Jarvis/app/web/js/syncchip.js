/* syncchip.js -- on GitHub, in the shared database, both, or neither.

   A record leaves this computer by two roads. A `git push` takes it to
   GitHub, which is how a colleague's `git pull` gets it and the only road
   archives take. The background sync takes it to the shared database
   (Supabase), which is how another computer sees it within the minute. The
   older dot-and-word mark (syncstate.js) said only the second; "is my work
   safe, and can the others see it" is a question about both. So this chip
   carries two tiny marks, a branch for GitHub and a cylinder for the shared
   database, each lit or dim, and says which in plain words when hovered.

   One answer for the whole page, from /api/syncstate (backend/syncstate.py):
   two local git calls and the push cursor, never a fetch and never a request
   at Supabase. Asked every thirty seconds, and only while a chip is on a
   page somebody can see; asked at once when the feed reports a sync.

   Callers:
     BARRY.syncstate.chipFor(kind, id)  a chip for one record, kept current
                                        in place until it leaves the page.
         kind  curation | bank | sessions | runs | results | storyboards |
               presets | prefs | artifacts | braces | aibeta | layers
               | file (id is a path under the app folder or GUI_logs)
     BARRY.syncstate.get()              the shared answer (a promise).
     BARRY.ui.syncChip(state)           a bare chip for a state the caller
                                        already has: {git, cloud}. */
BARRY.syncstate = (function () {
  const EVERY_MS = 30000;
  let data = null;          // the last answer
  let index = null;         // {kind: Map(id -> "git|cloud")}
  let files = null;         // {path -> "changed" | "committed"}
  let busy = null;
  let timer = null;
  let feedHooked = false;
  const chips = new Set();

  /* ---------- the marks ---------- */
  // A branch: two commits and a merge. Generic on purpose -- no company's
  // logo, and it reads as "version history" to anybody who has used git.
  const GIT_SVG = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"'
    + ' stroke-width="1.6" stroke-linecap="round" aria-hidden="true">'
    + '<circle cx="4.5" cy="3.5" r="1.8"/><circle cx="4.5" cy="12.5" r="1.8"/>'
    + '<circle cx="11.5" cy="5.5" r="1.8"/><path d="M4.5 5.3v5.4"/>'
    + '<path d="M11.5 7.3c0 2.6-2.4 3-5.6 4"/></svg>';
  // A database: a cylinder.
  const DB_SVG = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"'
    + ' stroke-width="1.6" aria-hidden="true">'
    + '<ellipse cx="8" cy="3.8" rx="5" ry="2"/>'
    + '<path d="M3 3.8v8.4c0 1.1 2.2 2 5 2s5-.9 5-2V3.8"/>'
    + '<path d="M3 8c0 1.1 2.2 2 5 2s5-.9 5-2"/></svg>';

  /* ---------- words ---------- */
  /* The headline is one of four sentences, by which marks are lit. The
     second line says what "not yet" means for this record, because "not
     pushed" and "never goes there" are different promises. */
  function headline(gitUp, cloudUp) {
    if (gitUp && cloudUp) return 'Saved to GitHub and to the shared database';
    if (cloudUp) return 'In the shared database; not pushed to GitHub yet';
    if (gitUp) return 'Pushed to GitHub; waiting to reach the shared database';
    return 'Only on this computer so far';
  }

  const GIT_WORDS = {
    pushed: '',
    committed: 'Committed here; the next push to GitHub takes it.',
    changed: 'Changed since the last commit here; commit and push to put it '
           + 'on GitHub.',
    never: 'This kind of record does not go to GitHub.',
    unknown: 'Whether it is on GitHub is not known: git is not answering '
           + 'on this computer.',
  };
  const WHY_NEVER = {
    demo: 'A demo or test record. These stay on this computer on purpose.',
    'no recording': 'Its recording is not in the shared database, so it '
                  + 'stays on this computer.',
    'no table': 'The shared database has no place for this yet.',
  };

  function cloudWords(st, why) {
    const c = (data && data.cloud) || {};
    if (st === 'waiting') {
      return c.error
        ? 'Waiting to go up, and the last sync did not get through: '
          + 'the shared database is not answering. Nothing is lost; it is '
          + 'sent when it answers.'
        : 'It goes up to the shared database by itself within a minute.';
    }
    if (st === 'never') return WHY_NEVER[why] || 'This stays on this computer.';
    if (st === 'off') return 'This computer is not connected to the shared '
                           + 'database, so nothing here goes there.';
    if (st === 'unknown') return 'Not checked against the shared database '
                               + 'yet; the next sync does.';
    return '';
  }

  /* ---------- one chip ---------- */
  function markClass(road, st) {
    if (road === 'git') {
      return st === 'pushed' ? 'lit' : st === 'committed' ? 'going'
        : st === 'never' ? 'never' : '';
    }
    if (st === 'synced') return 'lit';
    if (st === 'waiting') {
      return data && data.cloud && data.cloud.error ? 'stuck' : 'going';
    }
    return st === 'never' || st === 'off' ? 'never' : '';
  }

  /* Paint `node` for `state` ({git, cloud, why}, or null: not heard yet).
     Only what changed is written, so a refresh that changes nothing touches
     nothing -- no flicker, no repaint of the row around it. */
  function paint(node, state) {
    const g = node.firstChild, d = node.lastChild;
    let cls, gc, dc, title;
    if (!state) {
      cls = 'sync-chip pending'; gc = ''; dc = '';
      title = 'Checking whether this is on GitHub and in the shared '
            + 'database.';
    } else {
      gc = markClass('git', state.git);
      dc = markClass('cloud', state.cloud);
      cls = 'sync-chip';
      const gitUp = state.git === 'pushed';
      const cloudUp = state.cloud === 'synced';
      title = [headline(gitUp, cloudUp),
               GIT_WORDS[state.git] || '',
               cloudWords(state.cloud, state.why)]
        .filter(Boolean).join('\n');
    }
    if (node.className !== cls) node.className = cls;
    if (g.className !== gc) g.className = gc;
    if (d.className !== dc) d.className = dc;
    if (node.title !== title) {
      node.title = title;
      node.setAttribute('aria-label', title.split('\n')[0]);
    }
  }

  function build(state) {
    const node = el('span', { class: 'sync-chip', role: 'img' }, [
      el('i', { html: GIT_SVG }),
      el('i', { html: DB_SVG }),
    ]);
    paint(node, state === undefined ? null : state);
    return node;
  }

  /* ---------- the shared answer ---------- */
  function ingest(d) {
    data = d;
    index = {};
    for (const kind in (d.kinds || {})) {
      const m = new Map();
      const groups = d.kinds[kind] || {};
      for (const pair in groups) {
        for (const id of groups[pair]) m.set(String(id), pair);
      }
      index[kind] = m;
    }
    files = {};
    for (const st of ['changed', 'committed']) {
      for (const p of ((d.files || {})[st] || [])) files[p] = st;
    }
  }

  /* A path as the answer names it: relative to the app folder, forward
     slashes. A GUI_logs-relative one ("curation/x@m.json") is accepted. */
  function normPath(p) {
    let s = String(p || '').replace(/\\/g, '/').replace(/^\.?\//, '');
    if (!/^(GUI_logs|Results)\//.test(s)) s = 'GUI_logs/' + s;
    return s;
  }

  /* The record a shard path belongs to, for the kinds whose file name is
     the id (or ends in it). The rest are answered for git alone. */
  function ownerOf(path) {
    const m = /^GUI_logs\/(.+)$/.exec(path);
    if (!m) return null;
    const parts = m[1].split('/');
    const stem = parts[parts.length - 1].replace(/\.json$/, '');
    const base = stem.split('@')[0];
    const top = parts[0];
    if (parts.length === 2) {
      if (top === 'event_bank') return ['bank', base.split('_').pop()];
      if (top === 'braces') return ['braces', base.split('_').pop()];
      if (['storyboards', 'presets', 'prefs', 'layers', 'curation']
          .includes(top)) return [top, base];
      return null;
    }
    if (top === 'runs' && parts.length === 3) return ['runs', stem];
    if (top === 'results' && parts[1] === 'curation') return ['results', base];
    if (top === 'aibeta' && parts[1] === 'runs') return ['aibeta', base];
    if (top === 'artifacts' && parts.length === 3) return ['artifacts', base];
    return null;
  }

  function stateOf(kind, id) {
    if (!data) return null;
    if (kind === 'file') {
      const p = normPath(id);
      const own = ownerOf(p);
      const rec = own ? stateOf(own[0], own[1]) : null;
      const gitDefault = data.git && data.git.ok
        ? (data.git.no_upstream ? 'committed' : 'pushed') : 'unknown';
      return {
        git: files[p] || gitDefault,
        cloud: rec ? rec.cloud : 'unknown',
        why: rec ? rec.why : null,
      };
    }
    const pair = index[kind] && index[kind].get(String(id));
    if (!pair) {
      /* Not in the answer: made since it was given. Here and not yet
         anywhere else is the honest reading until the next answer says. */
      return { git: 'changed',
               cloud: data.cloud && data.cloud.on ? 'waiting' : 'off' };
    }
    const cut = pair.indexOf('|');
    const st = { git: pair.slice(0, cut), cloud: pair.slice(cut + 1) };
    st.why = ((data.why || {})[kind] || {})[id] || null;
    return st;
  }

  function paintAll() {
    for (const node of Array.from(chips)) {
      if (!node.isConnected) {
        // Built and not placed yet is fine for a moment (ToolKit builds a
        // panel, then places it); built and thrown away is not.
        if (node._seen || Date.now() - node._born > 60000) {
          chips.delete(node);
          continue;
        }
      } else {
        node._seen = true;
      }
      paint(node, stateOf(node._kind, node._id));
    }
  }

  function anyShowing() {
    for (const node of chips) if (node.isConnected) return true;
    return false;
  }

  async function refresh(fresh) {
    if (busy) return busy.then(() => (fresh ? refresh(fresh) : data));
    busy = (async () => {
      try {
        // Background: nobody clicked for this, so it never takes a slot a
        // person's request is waiting on (core.js, BACKGROUND_PATHS).
        ingest(await api('/api/syncstate' + (fresh ? '?fresh=1' : ''),
                         { priority: 'background' }));
      } catch (e) {
        /* The server, not either road: keep what the chips say. */
      } finally {
        busy = null;
      }
      paintAll();
      hookFeed();
      schedule();
      return data;
    })();
    return busy;
  }

  /* Every thirty seconds, and only while a chip is on a visible page. A
     chip placed later starts the clock again (chipFor). */
  function schedule() {
    clearTimeout(timer);
    timer = null;
    if (document.hidden || !chips.size) return;
    timer = setTimeout(() => {
      if (anyShowing()) refresh();
      else schedule();
    }, EVERY_MS);
  }

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { clearTimeout(timer); timer = null; return; }
    if (anyShowing()) refresh();
  });

  /* A sync line in the feed means something just moved, so the chips ask
     at once rather than at the next tick. The feed is being built
     alongside this; listened for both ways it may arrive: a `barry:feed`
     event on the document, and BARRY.feed's own subscription if it has
     one. A line is anything with `kind`. */
  let lastPoke = 0;
  function onFeedLine(line) {
    const kind = line && (line.kind || (line.detail && line.detail.kind));
    if (kind !== 'sync' || !chips.size) return;
    const now = Date.now();
    if (now - lastPoke < 3000) return;      // a burst of lines is one ask
    lastPoke = now;
    refresh(true);
  }
  document.addEventListener('barry:feed', (e) => onFeedLine(e.detail));
  function hookFeed() {
    if (feedHooked || !BARRY.feed) return;
    const f = BARRY.feed;
    const sub = typeof f.subscribe === 'function' ? f.subscribe
      : typeof f.on === 'function' ? f.on
      : typeof f.listen === 'function' ? f.listen : null;
    if (!sub) return;
    try {
      // `on('line', fn)` and `subscribe(fn)` are both common shapes.
      if (sub.length >= 2) sub.call(f, 'line', onFeedLine);
      else sub.call(f, onFeedLine);
      feedHooked = true;
    } catch (e) { /* not this shape; the document event still works */ }
  }

  /* ---------- callers ---------- */
  function chipFor(kind, id) {
    const node = build(data ? stateOf(kind, id) : null);
    node._kind = kind;
    node._id = String(id == null ? '' : id);
    node._born = Date.now();
    node.dataset.syncKind = kind;
    node.dataset.syncId = node._id;
    chips.add(node);
    if (!data) refresh();
    else if (!timer) schedule();
    return node;
  }

  function get() {
    return data ? Promise.resolve(data) : refresh();
  }

  return { chipFor, get, refresh, stateOf, build, paint,
           get data() { return data; } };
})();

/* A bare chip for a state the caller already has, {git, cloud}. It is not
   kept current; chipFor is, and is what a list wants. */
BARRY.ui.syncChip = function syncChip(state) {
  return BARRY.syncstate.build(state || null);
};
