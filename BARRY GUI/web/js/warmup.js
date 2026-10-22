'use strict';

/* ==========================================================================
   warmup.js -- BARRY.warmup: what the start screen gets ready, and who is
   working.

   The user's ask (2026-10-21): a start screen that "caches everything" while
   you wait, "with a cool loading screen and various prompts", and a login.
   So from the moment the preferences are in, Jarvis asks for everything it
   will want -- one step at a time, at background priority so nothing the
   person clicks ever waits behind it -- and the start screen shows each step
   tick off with what it found:

     Recordings, Event Bank, ToolKit choices, VACC catalogue, people,
     patch notes      every list, into its kept copy (web/js/data.js): the
                      view that wants it draws at once, now and next time
     Your last        opened on the server and its overview strip read, so
     recording        opening it again is immediate (/api/warmup/last)
     Analysis         the libraries the tools need, imported now rather than
     engines          by the first tool run (/api/warmup/engines)
     Recent           each recently opened recording's overview strip, kept
     recordings       on disk (/api/warmup/overviews) -- carries on after
                      the screen has gone

   Continue -- or any key -- goes straight in at any point; the warming goes
   on behind, and a quiet line in the rail says how far it has got until it
   is done (`railLine`).

   Who's working: asked on the start screen only when nobody is set on this
   computer, or the last answer is more than eight hours old -- a shared rig
   changes hands between sessions, a desk computer does not. Otherwise one
   line says who it is, with a way to change it.

   Never in a frame (every harness drives the app in one), a pop-out, an aid
   window or under automation -- unless the address says `?warm=1`.
   ========================================================================== */
BARRY.warmup = (function () {
  const WHO_AT = 'barry.who_at';
  const WHO_STALE_MS = 8 * 3600 * 1000;
  const bg = { priority: 'background' };
  const steps = [];
  const listeners = new Set();
  let started = false;
  let finished = false;

  function wanted() {
    let q = null;
    try { q = new URLSearchParams(location.search).get('warm'); } catch (e) { q = null; }
    if (q === '1' || q === 'on') return true;
    if (q === '0' || q === 'off') return false;
    try { if (window.top !== window) return false; } catch (e) { return false; }
    if (navigator.webdriver) return false;
    const b = document.body;
    if (b && (b.classList.contains('solo-window') || b.classList.contains('aid-window'))) {
      return false;
    }
    return true;
  }

  const n = (x) => Number(x || 0).toLocaleString();
  const plural = (k, one, many) => n(k) + ' ' + (Number(k) === 1 ? one : many);

  /* The steps, in the order they are worth having. Each answers with the
     words that go beside its tick, or null to say it does not apply here. */
  const PLAN = [
    ['recordings', 'Recordings', async () => {
      const r = await BARRY.data.get('/api/registry', bg);
      return plural(r.total != null ? r.total : (r.tree || []).length,
                    'recording', 'recordings');
    }],
    ['bank', 'Event Bank', async () => {
      const r = await BARRY.data.get('/api/bank', bg);
      return plural((r.entries || []).length, 'entry', 'entries');
    }],
    ['toolkit', 'ToolKit choices', async () => {
      const r = await BARRY.data.get('/api/toolkit/scopes', bg);
      return plural((r.sessions || []).length, 'recording', 'recordings')
        + ' to pick from';
    }],
    ['vacc', 'VACC catalogue', async () => {
      // Not set up on this computer: nothing to warm.
      const st = BARRY.vacc && BARRY.vacc.status ? await BARRY.vacc.status() : null;
      if (!st || !st.configured) return null;
      const r = await BARRY.data.get('/api/vacc/knows', bg);
      return plural(Object.keys(r.knows || {}).length, 'recording', 'recordings')
        + ' it can reach';
    }],
    ['people', 'People', async () => {
      const r = await BARRY.data.get('/api/people', bg);
      return plural((r.people || []).length, 'person', 'people');
    }],
    ['notes', 'Patch notes', async () => {
      const r = await BARRY.data.get('/api/notes', bg);
      return r.version ? 'version ' + r.version : 'read';
    }],
    ['last', 'Your last recording', async () => {
      const r = await api('/api/warmup/last', { method: 'POST', body: '{}',
                                                priority: 'background' });
      if (!r || !r.path) return null;
      if (r.here === false) return 'not on this computer right now';
      if (!r.opened) return 'could not be opened';
      return (r.name || 'open') + (r.overview ? ', strip read' : '');
    }],
    ['engines', 'Analysis engines', async (report) => {
      let ok = 0, of = 0;
      await BARRY.data.stream('/api/warmup/engines', null, (it) => {
        if (!it.missing) ok += 1;
        report(ok + ' of ' + (of || '…') + ' ready');
      }, { onHead: (h) => { of = h.of || 0; } });
      return ok + ' of ' + of + ' ready';
    }],
    ['overviews', 'Recent recordings', async (report) => {
      const s = await api('/api/warmup/overviews', {
        method: 'POST', body: JSON.stringify({ limit: 30 }), priority: 'background' });
      if (!s || !s.of) return s && s.recordings === 0 ? null : 'nothing to do';
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        let g = null;
        try { g = await api('/api/warmup/overviews', bg); } catch (e) { g = null; }
        if (!g) break;
        report(g.done + ' of ' + g.of + ' strips kept');
        if (!g.running) return g.kept + ' of ' + g.of + ' strips kept';
      }
      return 'stopped';
    }],
  ];

  function emit() {
    for (const cb of Array.from(listeners)) {
      try { cb(state()); } catch (e) { /* a listener's own problem */ }
    }
  }

  function state() {
    return {
      started, finished,
      steps: steps.map((s) => ({ id: s.id, label: s.label, state: s.state,
                                 note: s.note })),
      done: steps.filter((s) => s.state === 'done' || s.state === 'skip'
                        || s.state === 'fail').length,
      of: steps.length,
    };
  }

  /* One step after another, never two: everything here is background work,
     and the point is to be out of the way of the person, not quick. */
  async function start() {
    if (started) return state();
    started = true;
    PLAN.forEach(([id, label]) => steps.push({ id, label, state: 'wait', note: '' }));
    emit();
    // No start screen to show it on (turned off, or a deep link): the rail
    // says it from the beginning instead.
    try {
      if (!(BARRY.startMenu && BARRY.startMenu.wanted())) railLine();
    } catch (e) { /* a courtesy */ }
    for (let i = 0; i < PLAN.length; i++) {
      const s = steps[i];
      s.state = 'run';
      emit();
      try {
        const note = await PLAN[i][2]((words) => { s.note = words; emit(); });
        if (note === null) { s.state = 'skip'; s.note = 'not needed here'; }
        else { s.state = 'done'; s.note = note || ''; }
      } catch (e) {
        s.state = 'fail';
        s.note = 'will be read when it is wanted';
      }
      emit();
    }
    finished = true;
    emit();
    railLine();
    return state();
  }

  function on(cb) { listeners.add(cb); return () => listeners.delete(cb); }

  /* ---------------------------------------------------------- the panel */
  /* "Getting ready": one row per step, a tick when it is done, the words
     beside it. Drawn into the start screen by startmenu.js. */
  function panel() {
    const box = el('div', { class: 'wu-panel', 'aria-live': 'polite' });
    const head = el('div', { class: 'wu-head' }, [
      el('span', { class: 'wu-title', text: 'Getting ready' }),
      el('span', { class: 'wu-count' }),
    ]);
    const list = el('div', { class: 'wu-list' });
    box.append(head, list);
    const rows = {};
    const paint = (st) => {
      head.querySelector('.wu-count').textContent = st.finished
        ? 'all set' : st.done + ' of ' + st.of;
      for (const s of st.steps) {
        let row = rows[s.id];
        if (!row) {
          row = el('div', { class: 'wu-row', 'data-step': s.id }, [
            el('span', { class: 'wu-mark', 'aria-hidden': 'true' }),
            el('span', { class: 'wu-label', text: s.label }),
            el('span', { class: 'wu-note' }),
          ]);
          rows[s.id] = row;
          list.appendChild(row);
        }
        row.dataset.state = s.state;
        const note = row.querySelector('.wu-note');
        if (note.textContent !== (s.note || '')) note.textContent = s.note || '';
      }
    };
    paint(state());
    const off = on(paint);
    box._off = off;
    return box;
  }

  /* The quiet line in the rail while the warming carries on after the
     start screen has gone. Gone when it is done. */
  let railNode = null;
  let railOff = null;
  function railLine() {
    if (finished) {
      if (railOff) { railOff(); railOff = null; }
      if (railNode) { railNode.remove(); railNode = null; }
      return;
    }
    if (railNode || !started) return;
    const after = document.getElementById('whoChip');
    if (!after || !after.parentNode) return;
    railNode = el('div', { class: 'wu-rail', title: 'Jarvis is getting the '
      + 'lists and recordings you are likely to want ready, in the background.' });
    after.parentNode.insertBefore(railNode, after.nextSibling);
    const paint = (st) => {
      if (st.finished) { railLine(); return; }
      const cur = st.steps.find((s) => s.state === 'run');
      railNode.textContent = 'Getting ready · ' + st.done + ' of ' + st.of
        + (cur ? ' · ' + cur.label.toLowerCase() : '');
    };
    paint(state());
    railOff = on(paint);
  }

  /* ---------------------------------------------------------- who */
  function whoAt() {
    try { return Number(localStorage.getItem(WHO_AT) || 0); } catch (e) { return 0; }
  }
  function markWho() {
    try { localStorage.setItem(WHO_AT, String(Date.now())); } catch (e) { /* fine */ }
  }
  /* Ask, or just say? Ask when nobody is set here, or when the answer is
     older than eight hours. */
  function needsWho() {
    const prof = BARRY.profile && BARRY.profile.get && BARRY.profile.get();
    const name = BARRY.profile && BARRY.profile.who && BARRY.profile.who();
    if (!prof || !name) return true;
    return Date.now() - whoAt() > WHO_STALE_MS;
  }

  /* People in the order somebody at this computer is likely to be: whoever
     has worked on it, then everybody else by how much they have done. The
     AI sorters are names on decisions, not people at a keyboard. */
  function likely(roster) {
    const host = ((BARRY.state.catalog || {}).system || {}).hostname || '';
    const prof = (BARRY.profile && BARRY.profile.get && BARRY.profile.get()) || {};
    const here = [host, prof.device, prof.device_name, prof.machine]
      .filter(Boolean).map((s) => String(s).toLowerCase());
    /* A person somebody has described -- a role, an email, a profile, or
       added by hand -- and not one of the names harnesses and imports
       stamp on their own records. */
    const described = (p) => !!(p.role || p.email
      || (p.sources || []).some((s) => s === 'profile' || s === 'added by hand'));
    const people = ((roster && roster.people) || [])
      .filter((p) => p && p.name && p.is_person !== false && described(p)
              && !/\(AI\)|harness|@test\b|^import_/i.test(p.name));
    const local = (p) => (p.machines || []).some((m) => here.indexOf(
      String(m).toLowerCase()) >= 0);
    return people.sort((a, b) => (local(b) - local(a))
      || ((b.total || 0) - (a.total || 0))
      || String(a.name).localeCompare(String(b.name)));
  }

  async function useAs(person) {
    const patch = { name: person.name };
    if (person.email) patch.email = person.email;
    if (person.role) patch.role = person.role;
    if (person.initials) patch.initials = person.initials;
    await apiPost('/api/profile', patch);
    if (BARRY.profile && BARRY.profile.load) await BARRY.profile.load();
    markWho();
    try { BARRY.activity.log('profile.who', { from: 'start' }); } catch (e) { /* fine */ }
  }

  /* The block on the start screen: the picker, or the one line. */
  function whoBlock() {
    const box = el('div', { class: 'wu-who' });
    const name = BARRY.profile && BARRY.profile.who && BARRY.profile.who();
    const line = () => {
      box.textContent = '';
      const nm = BARRY.profile.who();
      box.append(
        el('span', { class: 'wu-who-line', text: nm ? 'Working as ' + nm : 'Nobody set' }),
        el('button', { class: 'linkish wu-who-change', type: 'button', text: 'change',
          onclick: () => picker() }));
    };
    const picker = async () => {
      box.textContent = '';
      box.append(el('div', { class: 'wu-who-q', text: 'Who’s working?' }));
      const grid = el('div', { class: 'wu-who-grid', role: 'listbox' });
      box.appendChild(grid);
      let roster = null;
      try { roster = await BARRY.data.get('/api/people', bg); } catch (e) { roster = null; }
      const people = likely(roster).slice(0, 6);
      const current = BARRY.profile.who();
      for (const p of people) {
        grid.appendChild(el('button', {
          class: 'wu-person' + (p.name === current ? ' on' : ''), type: 'button',
          onclick: async (ev) => {
            ev.currentTarget.disabled = true;
            try { await useAs(p); line(); }
            catch (e) { toast('Could not set who is working: ' + e.message, 'err'); picker(); }
          },
        }, [
          el('span', { class: 'wu-initials', text: p.initials
            || String(p.name).split(/\s+/).map((w) => w[0]).join('').slice(0, 2) }),
          el('span', { class: 'wu-pname', text: p.name }),
          el('span', { class: 'wu-prole', text: p.role || '' }),
        ]));
      }
      grid.appendChild(el('button', {
        class: 'wu-person wu-other', type: 'button',
        onclick: () => { if (BARRY.profile && BARRY.profile.open) BARRY.profile.open(); },
      }, [el('span', { class: 'wu-pname', text: 'Someone else…' })]));
      if (current) {
        grid.appendChild(el('button', {
          class: 'wu-person wu-keep', type: 'button',
          onclick: () => { markWho(); line(); },
        }, [el('span', { class: 'wu-pname', text: 'Still ' + current })]));
      }
    };
    if (!name || needsWho()) picker(); else line();
    return box;
  }

  /* ---------------------------------------------------------- prompts */
  /* The line that changes under the menu while things get ready: what is
     worth knowing, in the house's words. The latest patch note leads. */
  const TIPS = [
    'Esc leaves any mode; the Leave button is always the last on the right.',
    'Ctrl+K finds any view, tool, script or action by name.',
    'The number keys switch views: 1 is Pipeline, 3 is Xplorefinder, 4 Sessions.',
    'Simplify, in a mode’s bar, hides everything but the traces.',
    'A slower computer? Jarvis Light, in Settings, keeps it quick.',
    'Compact, in Settings, fits more on a small screen.',
    'Guide, at the foot of the rail, walks through any part of Jarvis.',
    'Every list draws at once from last time, then updates in place.',
  ];
  function prompts() {
    const box = el('div', { class: 'wu-tip', 'aria-live': 'polite' });
    const lines = TIPS.slice();
    let noted = false;
    let i = 0;
    const show = () => {
      if (!box.isConnected && i > 0) { clearInterval(t); return; }
      // The newest patch note, as soon as the warming has read the notes.
      if (!noted) {
        const kept = BARRY.data.peek('/api/notes');
        const newest = kept && kept.value && (kept.value.entries || [])[0];
        if (newest && newest.title) {
          noted = true;
          lines.splice(i % lines.length, 0, 'New in '
            + (newest.version || 'this version') + ': ' + newest.title);
        }
      }
      box.textContent = lines[i % lines.length];
      box.classList.remove('wu-tip-in');
      void box.offsetWidth;
      box.classList.add('wu-tip-in');
      i += 1;
    };
    show();
    const t = setInterval(show, 6000);
    return box;
  }

  return { wanted, start, state, on, panel, railLine, whoBlock, prompts,
           needsWho, likely };
})();
