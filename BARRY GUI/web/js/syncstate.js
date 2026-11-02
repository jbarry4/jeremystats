/* syncstate.js -- has this reached the shared database?

   One answer for the whole page, from /api/cloud/items (backend/syncitems.py),
   and a small mark any list can put beside a record: a bank entry, a
   curation set, a layer sheet, an artifact. The marks update themselves when
   the answer changes, so a list does not have to be redrawn to say that what
   it shows has gone up.

   The answer comes from this machine's push cursor and costs no request at
   Supabase -- egress there is counted in requests (constitution §11) -- so
   it can be asked often. Every twenty seconds, or every five while something
   is waiting to go, and not at all while the window is hidden.

   The rail chip is drawn from the same answer. It replaced "Sync now": the
   background sync already pushes a change within seconds of it being made,
   so a button that did the same thing by hand mostly reported the database
   being briefly unreachable, in a toast, as though the click had failed. */
BARRY.syncState = (function () {
  let data = null;
  let busy = null;
  let timer = null;
  const marks = new Set();

  /* What each state is called on a mark, and what its title says. Short on
     the mark, because it sits in a row beside a name and a count. */
  const WORDS = {
    synced: ['shared', 'In the shared database: colleagues on other '
                     + 'computers see this.'],
    waiting: ['sending', 'Changed here since the last push. It goes up by '
                       + 'itself within a minute.'],
    stuck: ['not sent', ''],
    local: ['this computer', ''],
    unknown: ['not checked', 'Jarvis has not asked the shared database '
                           + 'about this yet. It does on the next push.'],
    off: ['not shared', 'This computer is not connected to the shared '
                      + 'database, so nothing here leaves it.'],
  };

  const LOCAL_WHY = {
    demo: 'A demo or harness record. These are never shared, on purpose.',
    'no recording': 'Its recording is not in the shared database, so it '
                  + 'cannot be filed there. It stays on this computer.',
  };

  /* The last failure, in a sentence somebody can act on. The raw text is
     PostgREST or Cloudflare's, and a 522 is three lines of JSON that all
     mean "the database did not answer". */
  function failure() {
    const last = (data && data.last) || {};
    if (last.ok !== false) return null;
    if (last.blocked_note) return last.blocked_note;
    const err = String(last.error || '');
    if (/\b52[0-4]\b/.test(err) || /timed out|Timeout|Gateway/i.test(err)) {
      return 'The shared database is not answering right now (' +
        ((err.match(/\b5\d\d\b/) || [''])[0] || 'no reply')
        + '). Nothing is lost: it is kept here and sent when it answers. '
        + 'Jarvis keeps trying by itself.';
    }
    return 'The last sync failed: ' + err;
  }

  function stateOf(kind, id) {
    if (!data) return null;
    if (!data.on) return { state: 'off' };
    const it = ((data.items || {})[kind] || {})[id];
    /* Not in the answer yet: made since it was given. That is waiting. */
    const st = it || { state: 'waiting' };
    if (st.state === 'waiting' && failure()) {
      return Object.assign({}, st, { state: 'stuck' });
    }
    return st;
  }

  function paint(node) {
    const st = stateOf(node.dataset.syncKind, node.dataset.syncId);
    if (!st) {
      node.className = 'sync-mark unknown';
      node.textContent = '';
      node.title = '';
      return;
    }
    const w = WORDS[st.state] || WORDS.unknown;
    node.className = 'sync-mark ' + st.state;
    node.textContent = w[0];
    node.title = st.state === 'stuck' ? failure()
      : st.state === 'local' ? (LOCAL_WHY[st.why] || 'Kept on this computer.')
      : w[1];
  }

  /* A mark for one record, kept up to date until it leaves the page. */
  function mark(kind, id) {
    const node = el('span', { class: 'sync-mark' });
    node.dataset.syncKind = kind;
    node.dataset.syncId = String(id || '');
    node._born = Date.now();
    paint(node);
    marks.add(node);
    if (!data) refresh();
    else schedule();
    return node;
  }

  function paintAll() {
    for (const node of Array.from(marks)) {
      if (!node.isConnected) {
        // Built and not yet placed is fine for a moment; built and thrown
        // away is not, whether or not it was ever on the page.
        if (node._seen || Date.now() - node._born > 60000) {
          marks.delete(node);
          continue;
        }
      } else {
        node._seen = true;
      }
      paint(node);
    }
    paintRail();
  }

  /* The rail chip: the whole store in two words, and the git state of
     GUI_logs, which it used to show alone, in its title. */
  function paintRail() {
    const btn = document.getElementById('syncBtn');
    const label = document.getElementById('syncLabel');
    if (!btn || !label) return;
    const git = (BARRY.sync && BARRY.sync.git) || {};
    const gitLine = !git.ok ? ''
      : git.dirty ? git.dirty + ' uncommitted file(s) in GUI_logs.'
      : 'GUI_logs has no uncommitted changes.';
    let text = 'Sync', cls = '', why = '';
    if (data && !data.on) {
      text = 'Not shared';
      why = WORDS.off[1];
    } else if (data) {
      const bad = failure();
      const n = data.waiting || 0;
      if (bad && n) {
        text = n + ' not sent'; cls = 'bad'; why = bad;
      } else if (bad) {
        text = 'Database away'; cls = 'warn'; why = bad;
      } else if (n) {
        text = n + ' sending'; cls = 'busy';
        why = n + ' change(s) made here go up within a minute.';
      } else {
        text = 'All shared'; cls = 'ok';
        why = 'Everything made here is in the shared database.';
      }
    }
    label.textContent = text;
    btn.classList.toggle('sync-ok', cls === 'ok');
    btn.classList.toggle('sync-warn', cls === 'warn');
    btn.classList.toggle('sync-bad', cls === 'bad');
    btn.classList.toggle('sync-busy', cls === 'busy');
    btn.title = [why, gitLine, 'Click for what is synced, and how.']
      .filter(Boolean).join('\n');
  }

  async function refresh() {
    // Asked while an answer is on its way: that answer may predate what
    // the caller wants to see, so ask again once it lands.
    if (busy) return busy.then(() => refresh());
    busy = (async () => {
      try {
        data = await api('/api/cloud/items');
      } catch (e) {
        /* The server, not the cloud: say nothing new. */
      } finally {
        busy = null;
      }
      paintAll();
      schedule();
    })();
    return busy;
  }

  function schedule() {
    clearTimeout(timer);
    if (document.hidden) return;              // picked up on visibilitychange
    const hurry = data && (data.waiting || 0) > 0;
    timer = setTimeout(refresh, hurry ? 5000 : 20000);
  }

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) refresh();
    else clearTimeout(timer);
  });

  return { mark, refresh, stateOf, paintRail, get data() { return data; } };
})();
