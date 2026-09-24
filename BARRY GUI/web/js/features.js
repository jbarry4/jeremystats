/* ==========================================================================
   features.js -- shared machinery for the second round of section features.

   Three things live here because more than one view needs them:
     * BARRY.prefs      one synced settings file, cached in memory
     * BARRY.palette    the Ctrl+K command palette
     * small helpers    check-lists, POST-to-download, confirm dialog
   ========================================================================== */
'use strict';

/* ==========================================================================
   Preferences -- favourites, smart collections, "where was I"
   Written to GUI_logs/preferences.json, so it travels with a git pull.
   ========================================================================== */
BARRY.prefs = (function () {
  let cache = {};
  let loaded = false;
  let pending = null;
  let timer = null;

  // One request, however many callers.
  //
  // `loaded` is only true once the answer is back, so two callers starting
  // before it lands both fetched. That is not hypothetical: radio.wire()
  // kicks this off at core.js:3150 without awaiting it, and BARRY.init
  // awaits it again a few lines later -- so every boot asked for /api/prefs
  // twice. Holding the promise rather than only the result is the whole fix.
  let inflight = null;

  async function load(force) {
    if (loaded && !force) return cache;
    if (inflight && !force) return inflight;
    inflight = (async () => {
      try {
        const d = await api('/api/prefs');
        cache = d.prefs || {};
        loaded = true;
      } catch (e) { cache = {}; } finally { inflight = null; }
      return cache;
    })();
    return inflight;
  }

  function get(key, fallback) {
    const v = cache[key];
    return v === undefined || v === null ? fallback : v;
  }

  /* Writes are coalesced: toggling six favourites in a row is one request. */
  function set(key, value) {
    cache[key] = value;
    pending = pending || {};
    pending[key] = value;
    if (timer) clearTimeout(timer);
    timer = setTimeout(flush, 350);
    return value;
  }

  async function flush() {
    if (timer) { clearTimeout(timer); timer = null; }
    if (!pending) return;
    const patch = pending;
    pending = null;
    try {
      const d = await apiPost('/api/prefs', { patch });
      cache = d.prefs || cache;
    } catch (e) {
      toast('Could not save preferences: ' + e.message, 'err');
    }
  }

  /* A list-valued preference used as a set -- favourites, pins, tags. */
  function toggleIn(key, value) {
    const list = (get(key, []) || []).slice();
    const i = list.indexOf(value);
    if (i >= 0) list.splice(i, 1); else list.push(value);
    set(key, list);
    return i < 0;
  }

  function has(key, value) {
    return (get(key, []) || []).indexOf(value) >= 0;
  }

  return { load, get, set, flush, toggleIn, has,
           all: () => cache };
})();

/* ==========================================================================
   Command palette -- Ctrl+K / Cmd+K from anywhere
   ========================================================================== */
BARRY.palette = (function () {
  let open = false;
  let rows = [];
  let cursor = 0;
  let box, input, list;

  /* A cheap subsequence score: characters in order, contiguous runs and
     matches right after a separator both count for more. It ranks
     "csccnv" above "process_csv_and_convert" for "cscconv" without needing
     a fuzzy-search library. */
  function score(needle, hay) {
    if (!needle) return 1;
    const n = needle.toLowerCase();
    const h = hay.toLowerCase();
    let hi = 0, pts = 0, run = 0;
    for (let i = 0; i < n.length; i++) {
      const c = n[i];
      const at = h.indexOf(c, hi);
      if (at < 0) return 0;
      run = at === hi && i > 0 ? run + 1 : 0;
      pts += 1 + run * 2;
      if (at === 0 || /[^a-z0-9]/.test(h[at - 1])) pts += 3;
      hi = at + 1;
    }
    // Prefer short haystacks so an exact script name beats a long path.
    return pts + Math.max(0, 24 - h.length) * 0.15;
  }

  function commands() {
    const out = [];
    const cat = BARRY.state.catalog || { items: [] };

    // Views.
    const views = [
      ['pipeline', 'Pipeline', 'Walk the IED stages'],
      ['explorer', 'Explorer', 'Run any script in the repo'],
      ['xplore', 'Xplorefinder 2.0', 'Look at traces'],
      ['sessions', 'Sessions', 'Scan a data root'],
      ['history', 'History', 'Every run and action'],
      ['errors', 'Errors', 'What failed, and why'],
      ['results', 'Results', 'Everything saved'],
      ['storyboard', 'Storyboard', 'Build a deck'],
      ['eventbank', 'Event Bank', 'Banked events by project, mouse and session'],
      ['toolkit', 'ToolKit', 'Jobs that span many recordings at once'],
      ['misc', 'Misc', 'Loose scripts and utilities'],
    ];
    for (const [id, name, sub] of views) {
      out.push({ kind: 'view', label: 'Go to ' + name, sub,
                 hay: 'go to ' + name + ' ' + sub,
                 run: () => setView(id) });
    }

    // Tours. One entry each, plus the menu, so someone who half-remembers
    // there was a walkthrough of figures can find it by typing "figure".
    if (BARRY.tour) {
      out.push({ kind: 'action', label: 'Show me around',
                 sub: 'the guided tours',
                 hay: 'show me around guide tour tutorial help walkthrough',
                 run: () => BARRY.tour.openMenu() });
      const done = BARRY.tour.doneSet();
      for (const m of BARRY.tour.list()) {
        out.push({
          kind: 'action',
          label: 'Tour: ' + m.name,
          sub: (done.has(m.id) ? 'done · ' : '')
             + m.steps.length + ' steps',
          hay: 'tour tutorial guide ' + m.name + ' ' + (m.blurb || ''),
          run: () => BARRY.tour.start(m.id),
        });
      }
    }

    // Actions.
    const acts = [
      ['Open a session in Xplorefinder', 'browse for a CSC folder',
       async () => { setView('xplore');
                     const p = await pickPath('folder');
                     if (p) BARRY.views.xplore.open(p); }],
      ['Scan a data root for sessions', 'discover recordings',
       () => { setView('sessions'); const i = $('#rootPath'); if (i) i.focus(); }],
      ['Figure builder', 'compose a multi-panel figure',
       () => { setView('xplore');
               const b = $('#xfFigure'); if (b) b.click(); }],
      ['New storyboard deck', 'start a fresh deck',
       () => { setView('storyboard');
               if (BARRY.views.storyboard.newDeck) BARRY.views.storyboard.newDeck(); }],
      ['Search the repo', 'grep every script',
       () => { setView('misc');
               if (BARRY.views.misc.focusGrep) BARRY.views.misc.focusGrep(); }],
      ['Scratch runner', 'run a snippet against the repo',
       () => { setView('misc');
               if (BARRY.views.misc.focusScratch) BARRY.views.misc.focusScratch(); }],
      ['Housekeeping', 'find reclaimable clutter',
       () => { setView('misc');
               if (BARRY.views.misc.housekeeping) BARRY.views.misc.housekeeping(); }],
      ['Re-index the repo', 'rescan for new scripts',
       async () => { await api('/api/catalog?refresh=1');
                     toast('Repo re-indexed', 'ok'); }],
      ['GUI_logs sync status', 'what is waiting to be committed',
       () => showSync()],
      ['Toggle light / dark', 'switch the theme',
       () => applyTheme(BARRY.state.theme === 'dark' ? 'light' : 'dark')],
      ['Toggle VACC Mode', 'light the interface up for the cluster',
       () => applyVacc(!BARRY.state.vacc)],
      ['VACC status', 'the cluster, the queue, and what it can already read',
       () => BARRY.vacc && BARRY.vacc.showVacc()],
      ['Export run history as CSV', 'every run, as a table',
       () => BARRY.download('/api/history/export', { what: 'runs' },
                            'run-history.csv')],
      ['Export activity log as CSV', 'every logged action',
       () => BARRY.download('/api/history/export', { what: 'activity' },
                            'activity.csv')],
    ];
    for (const [label, sub, run] of acts) {
      out.push({ kind: 'action', label, sub, hay: label + ' ' + sub, run });
    }

    // Favourite scripts float to the top of the script block.
    const favs = BARRY.prefs.get('fav_scripts', []) || [];
    for (const it of cat.items) {
      const fav = favs.indexOf(it.rel) >= 0;
      out.push({
        kind: 'script', label: it.name, sub: it.rel, fav,
        hay: it.name + ' ' + it.rel + ' ' + (it.section || ''),
        boost: fav ? 30 : 0,
        run: () => { setView('explorer'); BARRY.views.explorer.select(it.rel); },
      });
    }

    // Bookmarks the user named in the viewer.
    for (const bm of (BARRY.prefs.get('recent_bookmarks', []) || [])) {
      out.push({
        kind: 'bookmark', label: bm.name, sub: bm.session || '',
        hay: 'bookmark ' + bm.name + ' ' + (bm.session || ''),
        run: () => { setView('xplore');
                     if (BARRY.views.xplore.gotoBookmark)
                       BARRY.views.xplore.gotoBookmark(bm); },
      });
    }
    return out;
  }

  function build() {
    input = el('input', {
      type: 'text', id: 'palInput', autocomplete: 'off', spellcheck: 'false',
      placeholder: 'Jump to a view, run a script, do a thing…',
    });
    list = el('div', { class: 'pal-list' });
    box = el('div', { class: 'pal-backdrop hidden', id: 'palette' }, [
      el('div', { class: 'pal-box', onclick: (e) => e.stopPropagation() }, [
        el('div', { class: 'pal-input-wrap' }, [
          BARRY.ui.magnifier(),
          input,
          el('kbd', { class: 'pal-esc', text: 'esc' }),
        ]),
        list,
        el('div', { class: 'pal-foot' }, [
          el('span', { html: '<kbd>&uarr;</kbd><kbd>&darr;</kbd> move' }),
          el('span', { html: '<kbd>enter</kbd> run' }),
          el('span', { html: '<kbd>ctrl</kbd>+<kbd>k</kbd> anywhere' }),
        ]),
      ]),
    ]);
    box.addEventListener('click', hide);
    input.addEventListener('input', refresh);
    input.addEventListener('keydown', key);
    document.body.appendChild(box);
  }

  function refresh() {
    const q = input.value.trim();
    const all = commands();
    rows = all
      .map((c) => ({ c, s: score(q, c.hay) + (c.boost || 0) * (q ? 1 : 3) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 60)
      .map((x) => x.c);
    cursor = 0;
    paint();
  }

  function paint() {
    list.innerHTML = '';
    if (!rows.length) {
      list.appendChild(el('div', { class: 'pal-empty', text: 'Nothing matches.' }));
      return;
    }
    rows.forEach((r, i) => {
      list.appendChild(el('div', {
        class: 'pal-row' + (i === cursor ? ' on' : ''),
        onmouseenter: () => { cursor = i; paint(); },
        onclick: () => fire(r),
      }, [
        el('span', { class: 'pal-kind ' + r.kind, text: r.kind }),
        el('span', { class: 'pal-label', text: r.label }),
        r.fav ? el('span', { class: 'pal-fav', text: '★' }) : null,
        el('span', {
          class: 'pal-sub' + (r.kind === 'script' ? ' path' : ''),
          text: r.sub || '', title: r.sub || '',
        }),
      ]));
    });
    const on = list.querySelector('.pal-row.on');
    if (on) on.scrollIntoView({ block: 'nearest' });
  }

  function key(e) {
    if (e.key === 'Escape') { hide(); return; }
    if (e.key === 'ArrowDown' || (e.key === 'n' && e.ctrlKey)) {
      e.preventDefault(); cursor = Math.min(rows.length - 1, cursor + 1); paint();
    } else if (e.key === 'ArrowUp' || (e.key === 'p' && e.ctrlKey)) {
      e.preventDefault(); cursor = Math.max(0, cursor - 1); paint();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (rows[cursor]) fire(rows[cursor]);
    }
  }

  function fire(row) {
    hide();
    BARRY.activity.log('palette.run', { kind: row.kind, label: row.label });
    try { row.run(); }
    catch (err) { reportClientError('palette', err.message, err.stack); }
  }

  function show() {
    if (!box) build();
    open = true;
    box.classList.remove('hidden');
    input.value = '';
    refresh();
    setTimeout(() => input.focus(), 20);
  }

  function hide() {
    open = false;
    if (box) box.classList.add('hidden');
  }

  function toggle() { (open ? hide : show)(); }

  return { show, hide, toggle, isOpen: () => open };
})();

/* ==========================================================================
   Small shared helpers
   ========================================================================== */

/* POST a body and save the response as a file. Every "export CSV" button. */
BARRY.download = async function download(path, body, filename) {
  try {
    const res = await fetch(path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    if (!res.ok) {
      let msg = 'Export failed (' + res.status + ')';
      try { msg = (await res.json()).error || msg; } catch (e) { /* binary */ }
      throw new Error(msg);
    }
    const outRel = res.headers.get('X-Barry-Output');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = el('a', { href: url, download: filename || 'export' });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    toast('Saved ' + (filename || 'file') + (outRel ? ' to Results/' : ''), 'ok');
    if (outRel) BARRY.refreshSync();
    return outRel;
  } catch (e) {
    toast(e.message, 'err');
    return null;
  }
};

/* Save text the browser already has, with no round trip. */
BARRY.saveText = function saveText(filename, text, mime) {
  const blob = new Blob([text], { type: mime || 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = el('a', { href: url, download: filename });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
};

BARRY.copy = async function copy(text, what) {
  try {
    await navigator.clipboard.writeText(text);
    toast((what || 'Copied') + ' to the clipboard', 'ok');
    return true;
  } catch (e) {
    // Clipboard access can be blocked; fall back to a selectable box.
    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Copy this' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('textarea', { class: 'copy-fallback', text, readonly: 'readonly',
                         onclick: (e) => e.target.select() }),
      ]),
    ]));
    return false;
  }
};

/* Render a health / preflight report as colored rows. */
BARRY.checkList = function checkList(checks, opts) {
  const o = opts || {};
  return el('div', { class: 'check-list' + (o.compact ? ' compact' : '') },
    (checks || []).map((c) => el('div', { class: 'check-row ' + c.level }, [
      el('span', { class: 'check-dot' }),
      el('span', { class: 'check-name', text: c.name }),
      el('span', { class: 'check-msg', text: c.message }),
      /* A row may carry its own control -- the continuity check has a gap
         table behind it, and the evidence for a number belongs beside the
         number rather than in a second place to go looking. */
      o.extra ? (o.extra(c) || null) : null,
    ])));
};

/* A yes/no the user actually has to read, for anything destructive. */
/* `onOk` is optional, and it is the whole point of the fifth argument.
 *
 * Without it the dialog closes the instant you press the button and the
 * caller's work starts against an empty screen. Every destructive action in
 * the app goes through here -- twenty-three of them -- so that one line was
 * the single largest source of "I clicked it, nothing happened, and then a
 * second later it had". Forgetting a recording, archiving a device, deleting
 * files off disk: dialog gone, nothing, toast.
 *
 * Pass an async function instead and the dialog holds its ground: the button
 * says what it is doing and stops accepting clicks, and the box only closes
 * once the work is actually done. A failure keeps it open and prints the
 * reason where the question was, which is where the person is looking --
 * rather than closing anyway and firing a toast about it.
 */
BARRY.confirm = function confirmBox(title, message, okLabel, danger, onOk) {
  return new Promise((resolve) => {
    let busy = false;
    const label = okLabel || 'Do it';
    const why = el('p', { class: 'confirm-err hidden' });
    const okBtn = el('button', { class: 'btn' + (danger ? ' danger' : ''),
                                 text: label });

    // Cancelling is refused while the work is in flight. There is nothing to
    // cancel -- the request has gone -- and closing the box would only hide
    // whether it worked.
    const done = (v) => { if (busy) return; closeModal(); resolve(v); };

    const go = async () => {
      if (busy) return;
      if (typeof onOk !== 'function') { done(true); return; }
      busy = true;
      okBtn.disabled = 'disabled';
      okBtn.textContent = label + '…';
      why.classList.add('hidden');
      try {
        await onOk();
        busy = false;
        closeModal();
        resolve(true);
      } catch (e) {
        busy = false;
        okBtn.disabled = null;
        okBtn.textContent = label;
        why.textContent = (e && e.message) ? e.message : String(e);
        why.classList.remove('hidden');
      }
    };
    okBtn.addEventListener('click', go);

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: title }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: () => done(false),
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        typeof message === 'string'
          ? el('p', { class: 'confirm-msg', text: message })
          : message,
        why,
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel',
                       onclick: () => done(false) }),
        okBtn,
      ]),
    ]));
  });
};

/* ==========================================================================
   Naming a banked set

   A bank entry's name is the only part of it a person reads in a list, and
   the names in this archive are "Incisor CSC61", "m33s8", "dupes seed" and
   "DS candidates (ETS)". Every one of those made sense to whoever typed it
   and none of them says which animal, which session, or which day — so the
   Event Bank is a list of forty-five things you have to open to identify.

   One rule, here, because two callers need it and a second copy would drift:
   Incisor when it banks, and the Edit dialog when somebody fixes an old
   name. Both offer it; neither imposes it. A name somebody typed on purpose
   is never overwritten.
   ========================================================================== */
BARRY.bankName = (function () {
  /* The session, as somebody says it out loud. The registry's own label
     where there is one -- it already carries the project, the animal, the
     session and the date -- and built from the pieces where there is not,
     because an entry filed under "Unfiled / m / s" is exactly the one whose
     name most needs to say something. */
  function session(row) {
    const r = row || {};
    if (r.session_label) return String(r.session_label);
    if (r.label) return String(r.label);
    const bits = [];
    if (r.project) bits.push(r.project);
    if (r.mouse != null) bits.push('m' + r.mouse);
    if (r.session != null) bits.push('s' + r.session);
    if (r.date) bits.push(r.date);
    return bits.join(' ');
  }

  /* `<the session> · <what this set is>`. The session first, because that
     is what a list is sorted and scanned by; what made it second, because
     that is what tells two sets of the same recording apart. */
  function suggest(row, what) {
    const s = session(row);
    const w = (what || '').trim();
    if (!s) return w;
    if (!w) return s;
    // Already says it -- a curated set banked from a set somebody named
    // after the session should not become "m33s8 · m33s8".
    if (s.toLowerCase().indexOf(w.toLowerCase()) >= 0) return s;
    if (w.toLowerCase().indexOf(s.toLowerCase()) >= 0) return w;
    return s + '  ·  ' + w;
  }

  /* Whether a name is worth offering to replace: one that says nothing
     about which recording it belongs to. Used to decide if the suggestion
     button should draw attention to itself, never to rename anything on
     its own. */
  function vague(name, row) {
    const s = session(row);
    if (!s) return false;
    const n = String(name || '').toLowerCase();
    if (!n) return true;
    // It counts as specific if it carries the session, or the animal AND
    // the session number -- "M8s9feb8" says both without matching the
    // registry's spelling of either.
    if (n.indexOf(s.toLowerCase()) >= 0) return false;
    const r = row || {};
    if (r.mouse != null && r.session != null) {
      const m = String(r.mouse), ss = String(r.session);
      if (new RegExp('m[^0-9]?' + m + '\\b').test(n)
          && new RegExp('s[^0-9]?' + ss + '\\b').test(n)) return false;
    }
    return true;
  }

  return { session, suggest, vague };
}());

/* A labeled section header with an action on the right. Used a lot below. */
BARRY.sectionHead = function sectionHead(title, right) {
  return el('div', { class: 'sec-head' }, [
    el('div', { class: 'section-label', text: title }),
    el('div', { class: 'spacer' }),
  ].concat([].concat(right || [])));
};

/* ==========================================================================
   Global keys
   ========================================================================== */
document.addEventListener('keydown', (e) => {
  const typing = isTyping(e);

  // Ctrl/Cmd+K opens the palette even while typing -- that is the point.
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    BARRY.palette.toggle();
    return;
  }
  if (typing) return;

  // "?" shows the shortcut sheet.
  if (e.key === '?' || (e.key === '/' && e.shiftKey)) {
    e.preventDefault();
    BARRY.shortcuts();
  }
});

BARRY.shortcuts = function shortcuts() {
  const rows = [
    ['Anywhere', [
      ['ctrl / cmd + K', 'command palette'],
      ['?', 'this sheet'],
      ['1 … 9', 'switch section'],
      ['esc', 'close a dialog'],
    ]],
    ['Xplorefinder', [
      ['← →', 'pan by a quarter window'],
      ['shift + ← →', 'pan by a whole window'],
      ['+ / -', 'zoom in / out'],
      ['n / p', 'next / previous event'],
      ['b', 'bookmark this window'],
      ['m', 'measure tool'],
      ['g', 'grid lines on / off'],
      ['home / end', 'start / end of the recording'],
    ]],
    ['Storyboard', [
      ['ctrl + S', 'save the deck'],
      ['ctrl + D', 'duplicate the slide'],
      ['F5', 'present'],
      ['← →', 'previous / next slide'],
      ['delete', 'remove the selected item'],
      ['ctrl + V', 'paste an image'],
    ]],
    ['Results', [
      ['ctrl + A', 'select everything shown'],
      ['enter', 'open the highlighted result'],
    ]],
  ];
  showModal(el('div', {}, [
    el('div', { class: 'mh' }, [
      el('h3', { text: 'Keyboard shortcuts' }),
      el('div', { class: 'spacer' }),
      el('button', { class: 'close-x', onclick: closeModal,
        html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
    ]),
    el('div', { class: 'mb keys-grid' }, rows.map(([group, keys]) =>
      el('div', { class: 'keys-col' }, [
        el('div', { class: 'section-label', text: group }),
      ].concat(keys.map(([k, what]) => el('div', { class: 'keys-row' }, [
        el('kbd', { text: k }),
        el('span', { text: what }),
      ])))))),
  ]));
};
