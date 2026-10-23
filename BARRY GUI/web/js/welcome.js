'use strict';

/* ==========================================================================
   welcome.js -- the first time Jarvis opens on a computer.

   The user's ask (2026-10-23): "modernize the set up process ... have a nice
   welcome screen". Signing in to the VACC was under Profile, and the two
   buttons that find every recording ("Find everything on VACC", "Find
   everything on netfiles") were in Sessions' VACC pad -- both work, both are
   hard to find on a computer that has never been set up. They stay where
   they are. This is the guided way through them, once:

       Welcome      what is about to happen, and why
       1  You       name, email, role, initials -- or pick yourself, if you
                    have worked in Jarvis on another computer
       2  VACC      NetID and password, then a real connection to prove it
       3  Recordings  look on the VACC and on netfiles, add what was found
       Done         straight into Jarvis

   When: the boot overlay becomes this, instead of the start menu, while
   nobody has said who they are on this computer (`/api/profile` `set` is
   false). The name is what every record is stamped with, so it is the one
   step that cannot be skipped; the VACC and the recordings say "Skip for
   now", because Jarvis runs without a cluster (onboard.py's ruling).
   "Not now" at the foot leaves, and the welcome is back next time until a
   name is given.

   Also on demand: the start menu's "Set up this computer", and
   `BARRY.welcome.open()`, in an overlay of its own.

   Never in a frame (every harness drives the app in one), a pop-out, an aid
   window or under automation, and not with ?welcome=0 or ?menu=0.
   ?welcome=1 shows it whatever the profile says.
   ========================================================================== */
BARRY.welcome = (function () {
  const WHO_AT = 'barry.who_at';           // warmup.js: when who was last said
  let live = null;                         // the panel on screen, or null

  function param(k) {
    try { return new URLSearchParams(location.search).get(k); }
    catch (e) { return null; }
  }
  function frameOk() {
    try { if (window.top !== window) return false; } catch (e) { return false; }
    if (navigator.webdriver) return false;
    const b = document.body;
    if (b && (b.classList.contains('solo-window')
              || b.classList.contains('aid-window'))) return false;
    if (param('welcome') === '0' || param('menu') === '0') return false;
    return true;
  }
  const forced = () => param('welcome') === '1';

  const fx = () => BARRY.jarvisfx || window.JarvisFX || null;
  const sfx = (name, a) => {
    try { const f = fx(); if (f && !f.muted && f[name]) f[name](a); }
    catch (e) { /* a sound never stops anything */ }
  };
  const log = (action, detail) => {
    try { BARRY.activity.log(action, detail || {}); } catch (e) { /* fine */ }
  };
  const initialsOf = (name) => String(name || '').trim().split(/\s+/)
    .filter(Boolean).map((w) => w[0].toUpperCase()).join('').slice(0, 3);

  /* ------------------------------------------------------------ the console */
  /* What is happening, as it happens (2026-10-23: "not just a static loading
     screen ... an informative letting you know what's happening bar loading
     sort of thing ... rapid fire spit out tons of text").

     The server says each thing the VACC work does into a live feed
     (backend/livefeed.py, `/api/vacc/feed`): every key tried, every field
     the cluster answers with, every folder a walk of scratch or netfiles
     finds, every recording added. This polls it four times a second and
     prints what arrives a few lines a frame, so a burst of four hundred
     folders streams past rather than appearing at once. Above the text, a
     bar per task: against a count where one is known (a walk runs against
     the last walk of the same place, and says "~" because it is a guess),
     a moving stripe where none is.

     Nothing is invented to look busy. When the cluster goes quiet the foot
     says how long it has been quiet. The page adds its own lines only for
     what it did itself, and for the results it has in hand.

     `show(task)`: which tasks' lines and bars belong on this console.
     `onDone(task)`: called once when a task it shows finishes. */
  const SPIN = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏';
  function terminal(opts) {
    const o = opts || {};
    const show = o.show || (() => true);
    const bars = el('div', { class: 'wl-bars' });
    const screen = el('div', { class: 'wl-term', role: 'log', 'aria-live': 'off',
                               tabindex: '0', 'aria-label': 'What is happening' });
    const foot = el('div', { class: 'wl-term-foot' });
    const node = el('div', { class: 'wl-console' }, [bars, screen, foot]);
    const still = () => !!(BARRY.ui && BARRY.ui.reducedMotion && BARRY.ui.reducedMotion());
    const queue = [];
    const barRows = {};
    const finished = new Set();
    let since = -1, on = false, timer = null, raf = null, spin = 0;
    let offset = 0, t0 = Date.now() / 1000, lastLine = Date.now(), printed = 0;
    let feedless = false, running = [];

    function local(text, kind) {
      queue.push({ text, kind: kind || 'me', t: Date.now() / 1000 });
      kick();
    }
    function line(l) {
      const age = Math.max(0, (l.t || Date.now() / 1000) - t0);
      const row = el('div', { class: 'wl-ln', 'data-kind': l.kind || '' }, [
        el('span', { class: 'wl-ts', text: '+' + age.toFixed(2).padStart(6, ' ') }),
        el('span', { class: 'wl-tx', text: l.text }),
      ]);
      const atEnd = screen.scrollHeight - screen.scrollTop - screen.clientHeight < 40;
      screen.appendChild(row);
      printed += 1;
      while (screen.childNodes.length > 500) screen.removeChild(screen.firstChild);
      if (atEnd) screen.scrollTop = screen.scrollHeight;
      lastLine = Date.now();
    }
    function drip() {
      raf = null;
      if (!queue.length) return;
      // All of it within about a fifth of a second, and at least one a frame.
      const k = still() ? queue.length : Math.max(1, Math.ceil(queue.length / 12));
      queue.splice(0, k).forEach(line);
      paintFoot();
      if (queue.length) raf = requestAnimationFrame(drip);
    }
    function kick() { if (!raf) raf = requestAnimationFrame(drip); }

    const secs = (s) => (s < 60 ? Math.round(s) + ' s'
      : Math.floor(s / 60) + ' min ' + String(Math.round(s % 60)).padStart(2, '0') + ' s');
    function paintBars(tasks) {
      const mine = (tasks || []).filter((t) => show(t.name)
        && (t.state === 'run' || (t.ended || 0) * 1000 > (t0 * 1000 - 1000)));
      running = mine.filter((t) => t.state === 'run');
      for (const t of mine) {
        let r = barRows[t.name];
        if (!r) {
          r = {
            box: el('div', { class: 'wl-barrow' }),
            label: el('span', { class: 'wl-bar-label' }),
            count: el('span', { class: 'wl-bar-count' }),
            fill: el('span', { class: 'wl-bar-fill' }),
          };
          r.box.append(el('div', { class: 'wl-bar-head' }, [r.label, r.count]),
                       el('div', { class: 'wl-bar' }, [r.fill]));
          barRows[t.name] = r;
          bars.appendChild(r.box);
        }
        const of = t.of || 0;
        const done = t.done || 0;
        const known = of > 0;
        r.box.dataset.state = t.state;
        r.box.dataset.known = known ? '1' : '';
        r.label.textContent = t.label || t.name;
        const pct = t.state === 'done' ? 100
          : known ? Math.min(97, (100 * done) / of) : 0;
        r.fill.style.width = (t.state === 'done' || known) ? pct.toFixed(1) + '%' : '';
        r.count.textContent = (t.state === 'fail' ? 'stopped · '
          : t.state === 'done' ? 'done · ' : '')
          + (known ? done.toLocaleString() + ' of ' + (t.estimate ? '~' : '')
                     + of.toLocaleString() + (t.estimate ? ' (last time)' : '')
            : done ? done.toLocaleString() + ' so far' : '')
          + (t.age_s != null && t.state === 'run' ? (done || known ? ' · ' : '') + secs(t.age_s) : '');
        if (t.state !== 'run' && !finished.has(t.name)) {
          finished.add(t.name);
          if (o.onDone) { try { o.onDone(t.name, t.state); } catch (e) { /* its own */ } }
        }
        if (t.state === 'run') finished.delete(t.name);
      }
    }
    function paintFoot() {
      spin = (spin + 1) % SPIN.length;
      const quiet = (Date.now() - lastLine) / 1000;
      const busy = running.length > 0;
      foot.textContent = '';
      foot.append(
        el('span', { class: 'wl-spin' + (busy ? ' on' : ''),
                     text: busy ? SPIN[spin] : '●' }),
        el('span', { text: feedless
          ? 'live detail starts once Jarvis has been restarted'
          : busy ? (quiet > 2 ? 'working — the cluster has been quiet for ' + secs(quiet)
                              : 'live')
            : 'idle' }),
        el('span', { class: 'wl-term-n', text: printed.toLocaleString() + ' line'
          + (printed === 1 ? '' : 's') }));
    }

    async function poll() {
      timer = null;
      if (!on) return;
      let got = null;
      try {
        got = await api('/api/vacc/feed?since=' + since, { priority: 'high' });
      } catch (e) {
        // An older server has no feed: say so once, keep the page's own lines.
        if (!feedless) { feedless = true; paintFoot(); }
        if (on) timer = setTimeout(poll, 4000);
        return;
      }
      feedless = false;
      if (since < 0) {
        offset = (got.now || Date.now() / 1000) - Date.now() / 1000;
        t0 = (got.now || Date.now() / 1000);
      } else {
        for (const l of (got.lines || [])) {
          if (show(l.task)) queue.push(l);
        }
        if (got.skipped) {
          queue.push({ text: got.skipped.toLocaleString() + ' more lines went past too '
            + 'fast to show', kind: 'dim', t: got.now });
        }
      }
      since = got.next != null ? got.next : since;
      paintBars(got.tasks);
      if (queue.length) kick(); else paintFoot();
      if (on) timer = setTimeout(poll, 250);
    }

    function start() {
      if (on) return;
      on = true;
      paintFoot();
      poll();
    }
    function stop() {
      on = false;
      clearTimeout(timer);
      timer = null;
    }
    return { node, start, stop, local, get offset() { return offset; } };
  }

  /* ------------------------------------------------------------ the steps */
  const STEPS = [
    ['you', 'You'],
    ['vacc', 'VACC'],
    ['find', 'Recordings'],
  ];

  /* Build the whole thing into `host`. `done(how)` is called once, when it
     is over: 'finished', or 'later' when somebody chose Not now. */
  function build(host, done, opts) {
    const o = opts || {};
    const st = {
      at: 'hello',
      did: { you: null, vacc: null, find: null },   // 'done' | 'skipped'
      roster: null,
      picked: null,
      signin: null,          // /api/vacc/signin/state
      vstatus: null,         // /api/vacc/status or /check
      found: null,           // /api/vacc/found
      busy: false,
      added: null,
    };
    let pollTimer = null;
    let closed = false;

    const word = document.documentElement.dataset.jarvis === 'off'
      ? 'Workbench' : 'Jarvis';
    const panel = el('div', { class: 'wl-panel', role: 'dialog',
                              'aria-label': 'Welcome to ' + word });
    const rail = el('ol', { class: 'wl-rail', 'aria-label': 'Steps' });
    const body = el('div', { class: 'wl-body' });
    const foot = el('div', { class: 'wl-foot' });
    panel.append(rail, body, foot);
    host.appendChild(panel);

    function close(how) {
      if (closed) return;
      closed = true;
      clearTimeout(pollTimer);
      if (st.term) { st.term.stop(); st.term = null; }
      window.removeEventListener('keydown', onKey, true);
      live = null;
      log('welcome.close', { how, did: st.did });
      done(how);
    }

    function onKey(e) {
      if (closed) return;
      if (e.key === 'Escape' && o.escape) { e.preventDefault(); close('later'); return; }
      if (e.key === 'Enter' && st.at === 'hello') { e.preventDefault(); go('you'); }
    }
    window.addEventListener('keydown', onKey, true);

    function go(step) {
      st.at = step;
      clearTimeout(pollTimer);
      if (st.term) { st.term.stop(); st.term = null; }
      sfx('select');
      paint();
    }

    function paintRail() {
      rail.textContent = '';
      rail.hidden = st.at === 'hello';
      STEPS.forEach(([id, label], i) => {
        const state = st.at === id ? 'on'
          : st.did[id] === 'done' ? 'done'
            : st.did[id] === 'skipped' ? 'skipped' : 'wait';
        rail.appendChild(el('li', { class: 'wl-step', 'data-state': state,
                                    'aria-current': st.at === id ? 'step' : null }, [
          el('span', { class: 'wl-dot', text: state === 'done' ? '✓' : String(i + 1) }),
          el('span', { class: 'wl-step-name', text: label }),
        ]));
      });
    }

    function paintFoot() {
      foot.textContent = '';
      if (st.at === 'done') return;
      foot.appendChild(el('button', {
        class: 'linkish wl-later', type: 'button',
        text: o.escape ? 'Close' : 'Not now — I will set this up later',
        title: o.escape ? null
          : 'Jarvis opens as it is. Until a name is given this computer '
            + 'credits work to itself, and this screen comes back next time.',
        onclick: () => close('later'),
      }));
    }

    function paint() {
      if (closed) return;
      paintRail();
      paintFoot();
      body.textContent = '';
      const page = ({ hello, you, vacc, find, done: finished })[st.at]();
      page.classList.add('wl-page');
      body.appendChild(page);
      const first = page.querySelector('[data-autofocus]');
      if (first) setTimeout(() => { try { first.focus(); } catch (e) { /* fine */ } }, 30);
    }

    const head = (title, sub) => el('div', { class: 'wl-head' }, [
      el('h2', { class: 'wl-title', text: title }),
      sub ? el('p', { class: 'wl-sub', text: sub }) : null,
    ]);
    const msgLine = () => el('p', { class: 'wl-msg', 'aria-live': 'polite' });
    const say = (node, text, kind) => {
      node.textContent = text || '';
      node.dataset.kind = kind || '';
    };
    const row = (children) => el('div', { class: 'wl-actions' }, children);
    const primary = (text, onclick, extra) => el('button', Object.assign({
      class: 'btn wl-go', type: 'button', text, onclick }, extra || {}));
    const ghost = (text, onclick, extra) => el('button', Object.assign({
      class: 'btn ghost', type: 'button', text, onclick }, extra || {}));

    /* ---------------------------------------------------------- welcome */
    function hello() {
      const mark = el('div', { class: 'wl-mark', 'aria-hidden': 'true' });
      try {
        if (BARRY.jarvis && BARRY.jarvis.markSvg) {
          mark.innerHTML = BARRY.jarvis.markSvg(null, 'full');
        }
      } catch (e) { /* a welcome without its mark is still a welcome */ }
      const item = (n, title, why) => el('li', { class: 'wl-plan-item' }, [
        el('span', { class: 'wl-dot', text: String(n) }),
        el('span', { class: 'wl-plan-text' }, [
          el('strong', { text: title }), el('span', { text: why }),
        ]),
      ]);
      return el('div', { class: 'wl-hello' }, [
        mark,
        el('h1', { class: 'wl-big', text: 'Welcome to ' + word }),
        el('p', { class: 'wl-sub', text: o.escape
          ? 'The three steps a new computer is walked through, again. Each one '
            + 'starts from how things stand now.'
          : 'This computer is new to ' + word + '. Three steps and you are in.' }),
        el('ol', { class: 'wl-plan' }, [
          item(1, 'You', 'Your name goes on every decision, figure and run you make.'),
          item(2, 'Your VACC account', 'So tools can run on the cluster and read netfiles.'),
          item(3, 'Your recordings', 'Jarvis looks on the VACC and on netfiles and adds what it finds.'),
        ]),
        row([primary('Start', () => go('you'), { 'data-autofocus': '1' })]),
        el('p', { class: 'wl-hint', text: 'About five minutes. Nothing is copied '
          + 'and nothing on the cluster changes.' }),
      ]);
    }

    /* ---------------------------------------------------------- 1  you */
    function you() {
      const prof = (BARRY.profile && BARRY.profile.get && BARRY.profile.get()) || {};
      const roles = (BARRY.profile && BARRY.profile.roles) ? BARRY.profile.roles() : [];
      const f = {
        name: el('input', { type: 'text', autocomplete: 'name', spellcheck: 'false',
                            value: prof.name || '', 'data-autofocus': '1',
                            placeholder: 'First and last name' }),
        email: el('input', { type: 'email', autocomplete: 'email', spellcheck: 'false',
                             value: prof.email || '', placeholder: 'netid@uvm.edu' }),
        role: el('select', {}),
        initials: el('input', { type: 'text', spellcheck: 'false', maxlength: '4',
                                value: prof.initials || '', placeholder: 'AB' }),
      };
      const roleNow = prof.role || '';
      const roleOpts = roles.slice();
      if (roleNow && !roleOpts.some((r) => r.toLowerCase() === roleNow.toLowerCase())) {
        roleOpts.push(roleNow);
      }
      f.role.appendChild(el('option', { value: '', text: 'Choose…' }));
      roleOpts.forEach((r) => f.role.appendChild(el('option', {
        value: r, text: r, selected: r === roleNow ? 'selected' : null })));
      // Initials follow the name until somebody types their own.
      let ownInitials = !!prof.initials;
      f.initials.addEventListener('input', () => { ownInitials = !!f.initials.value.trim(); });
      f.name.addEventListener('input', () => {
        if (!ownInitials) f.initials.value = initialsOf(f.name.value);
        if (st.picked && f.name.value.trim() !== st.picked.name) unpick();
      });

      const field = (label, input, hint) => el('label', { class: 'wl-field' }, [
        el('span', { class: 'wl-label', text: label }), input,
        hint ? el('span', { class: 'wl-hint', text: hint }) : null,
      ]);

      const grid = el('div', { class: 'wl-people', role: 'listbox' });
      const known = el('div', { class: 'wl-known' }, [
        el('div', { class: 'wl-label', text: 'Already worked in ' + word + ' somewhere else?' }),
        el('p', { class: 'wl-hint', text: 'Pick yourself and your details come with you, '
          + 'so your work here and there is credited to one name.' }),
        grid,
      ]);
      known.hidden = true;

      function unpick() {
        st.picked = null;
        grid.querySelectorAll('.wl-person').forEach((b) => {
          b.classList.remove('on'); b.setAttribute('aria-selected', 'false');
        });
      }
      function pick(p, btn) {
        unpick();
        st.picked = p;
        btn.classList.add('on'); btn.setAttribute('aria-selected', 'true');
        f.name.value = p.name || '';
        f.email.value = p.email || '';
        if (p.role) {
          if (!Array.from(f.role.options).some((x) => x.value === p.role)) {
            f.role.appendChild(el('option', { value: p.role, text: p.role }));
          }
          f.role.value = p.role;
        }
        f.initials.value = p.initials || initialsOf(p.name);
        ownInitials = !!p.initials;
        sfx('hover');
      }
      function paintPeople(roster) {
        const W = BARRY.warmup;
        const people = (W && W.likely ? W.likely(roster) : ((roster || {}).people || []))
          .filter((p) => !p.archived).slice(0, 8);
        grid.textContent = '';
        for (const p of people) {
          const btn = el('button', { class: 'wl-person', type: 'button', role: 'option',
                                     'aria-selected': 'false' }, [
            el('span', { class: 'wl-initials', text: p.initials || initialsOf(p.name) }),
            el('span', { class: 'wl-pname', text: p.name }),
            el('span', { class: 'wl-prole', text: p.role || p.email || '' }),
          ]);
          btn.addEventListener('click', () => pick(p, btn));
          grid.appendChild(btn);
          if (prof.name && p.name === prof.name) { btn.classList.add('on'); st.picked = p; }
        }
        known.hidden = !people.length;
      }
      if (st.roster) paintPeople(st.roster);
      else {
        const get = BARRY.data ? BARRY.data.get('/api/people') : api('/api/people');
        Promise.resolve(get).then((r) => { st.roster = r; paintPeople(r); })
          .catch(() => { /* nobody to offer: the form is enough */ });
      }

      const msg = msgLine();
      async function save() {
        const name = f.name.value.trim();
        if (!name) {
          say(msg, 'Your name is needed — it is what goes on your work.', 'warn');
          f.name.focus();
          return;
        }
        const patch = {
          name,
          email: f.email.value.trim(),
          role: f.role.value,
          initials: f.initials.value.trim() || initialsOf(name),
        };
        go_.disabled = true;
        say(msg, 'Saving…');
        try {
          await apiPost('/api/profile', patch);
          if (BARRY.profile && BARRY.profile.load) await BARRY.profile.load();
          try { localStorage.setItem(WHO_AT, String(Date.now())); } catch (e) { /* fine */ }
          st.did.you = 'done';
          log('welcome.profile', { picked: !!st.picked });
          go('vacc');
        } catch (e) {
          say(msg, 'Could not save: ' + e.message, 'warn');
          go_.disabled = false;
        }
      }
      const go_ = primary('Continue', save);
      [f.name, f.email, f.initials].forEach((x) => x.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); save(); }
      }));

      return el('div', {}, [
        head('Who are you?', 'Said once, on this computer. Everything you do here is '
          + 'credited to it.'),
        known,
        el('div', { class: 'wl-form' }, [
          field('Your name', f.name, 'What appears under a figure and against every decision.'),
          field('Email', f.email, 'So a decision can be asked about later.'),
          el('div', { class: 'wl-pair' }, [
            field('Role', f.role),
            field('Initials', f.initials, 'Where there is no room for a full name.'),
          ]),
        ]),
        msg,
        row([go_]),
      ]);
    }

    /* ---------------------------------------------------------- 2  VACC */
    function vacc() {
      const box = el('div', {});
      box.appendChild(head('Your VACC account',
        'The cluster runs the heavy tools and reads the lab’s netfiles share. '
        + 'Sign in once and this computer remembers it.'));
      const inner = el('div', { class: 'wl-vacc' });
      box.appendChild(inner);
      // Outside `inner`, which is redrawn: the console keeps its lines.
      const term = terminal({ show: (t) => !t || t === 'signin' || t === 'probe' });
      box.appendChild(term.node);
      st.term = term;
      term.start();
      const skip = ghost('Skip for now', () => { st.did.vacc = 'skipped'; go('find'); },
        { title: 'Jarvis works without it. Sign in later from your profile, '
               + 'under VACC account.' });
      const next = primary('Continue', () => go('find'));
      const actions = row([skip, next]);
      box.appendChild(actions);

      const connected = () => !!(st.vstatus && st.vstatus.configured && st.vstatus.available);
      const paintActions = () => {
        next.hidden = !connected();
        skip.hidden = connected();
      };

      function stateLine(text, kind) {
        return el('p', { class: 'wl-state', 'data-kind': kind || '', text });
      }

      async function confirm(line) {
        say(line, 'Connecting to the cluster…', 'busy');
        line.dataset.kind = 'busy';
        term.local('Confirm connection: one real connection to the cluster, now');
        try {
          st.vstatus = await apiPost('/api/vacc/check', {});
        } catch (e) {
          st.vstatus = { configured: true, available: false, why: e.message };
        }
        term.local(st.vstatus.available
          ? 'connected as ' + (st.vstatus.netid || '?') + ' — this step is done'
          : 'not connected: ' + (st.vstatus.why || 'no answer'),
        st.vstatus.available ? 'ok' : 'warn');
        if (st.vstatus.available) {
          st.did.vacc = 'done';
          sfx('select');
          log('welcome.vacc', { netid: st.vstatus.netid });
          try {
            if (BARRY.vacc && BARRY.vacc.status) await BARRY.vacc.status(true);
            if (!BARRY.state.vacc && typeof applyVacc === 'function') applyVacc(true);
          } catch (e) { /* the switch is a courtesy */ }
        }
        draw();
      }

      function form(netidGuess) {
        const netid = el('input', { type: 'text', spellcheck: 'false', autocomplete: 'username',
                                    placeholder: 'netid', value: netidGuess || '',
                                    'data-autofocus': netidGuess ? null : '1' });
        const pw = el('input', { type: 'password', autocomplete: 'current-password',
                                 placeholder: 'UVM password',
                                 'data-autofocus': netidGuess ? '1' : null });
        const msg = msgLine();
        let busy = false;
        const go_ = primary('Sign in', async () => {
          if (busy) return;
          const id = netid.value.trim();
          if (!id) { say(msg, 'Your NetID is the part of your UVM email before the @.', 'warn'); netid.focus(); return; }
          busy = true; go_.disabled = true; go_.textContent = 'Signing in…';
          term.local('Sign in as ' + id + (pw.value ? ', with a password to install a key'
                                                   : ', with the keys this computer has'));
          say(msg, pw.value
            ? 'Installing a key on the cluster. If Duo sends a push to your phone, approve it.'
            : 'Trying the keys this computer already has…', 'busy');
          try {
            const res = await apiPost('/api/vacc/signin', { netid: id, password: pw.value || '' });
            log('vacc.signin', { netid: res.netid, made_key: !!res.made_key, from: 'welcome' });
            st.signin = Object.assign({}, st.signin || {}, { configured: true, netid: res.netid });
            st.vstatus = { configured: true, netid: res.netid };
            pw.value = '';
            draw(true);
          } catch (e) {
            say(msg, e.message, 'warn');
            term.local(e.message, 'warn');
            if (/password is needed once/i.test(e.message || '')) pw.focus();
          } finally {
            pw.value = '';
            busy = false; go_.disabled = false; go_.textContent = 'Sign in';
          }
        });
        [netid, pw].forEach((x) => x.addEventListener('keydown', (e) => {
          if (e.key !== 'Enter') return;
          e.preventDefault();
          if (x === netid && !pw.value) pw.focus(); else go_.click();
        }));
        return el('div', { class: 'wl-form' }, [
          el('label', { class: 'wl-field' }, [
            el('span', { class: 'wl-label', text: 'NetID' }), netid,
            el('span', { class: 'wl-hint', text: 'The part of your UVM email in front of the @.' }),
          ]),
          el('label', { class: 'wl-field' }, [
            el('span', { class: 'wl-label', text: 'Password' }), pw,
            el('span', { class: 'wl-hint', text: 'Used once, to put a key on the cluster, then '
              + 'dropped: not written down, not kept, sent only to the VACC. Leave it empty if '
              + 'this computer already reaches your account.' }),
          ]),
          msg,
          row([go_]),
        ]);
      }

      /* `justSignedIn`: confirm straight away -- signing in already proved
         the key once, and the real connection is what this step promises. */
      function draw(justSignedIn) {
        inner.textContent = '';
        const s = st.signin || {};
        if (s.error) {
          inner.appendChild(stateLine('Could not read this computer’s VACC set-up: ' + s.error, 'warn'));
        } else if (s.have_ssh === false) {
          inner.appendChild(stateLine('There is no ssh client on this computer, so it cannot '
            + 'reach the cluster. On Windows it is “OpenSSH Client”, under Settings › '
            + 'Optional features. Skip this for now and sign in afterwards.', 'warn'));
        } else if (s.configured) {
          const v = st.vstatus || {};
          const line = stateLine('', '');
          inner.appendChild(el('div', { class: 'wl-signed' }, [
            el('span', { class: 'wl-initials', text: '✓' }),
            el('span', {}, [
              el('strong', { text: 'Signed in as ' + (v.netid || s.netid) }),
              el('span', { class: 'wl-hint', text: ' on ' + (s.host || v.host || 'login.vacc.uvm.edu') }),
            ]),
          ]));
          inner.appendChild(line);
          if (v.available) {
            say(line, 'Connected. The cluster answered just now'
              + (v.partition ? ' — jobs go to ' + v.partition : '') + '.', 'ok');
          } else if (v.why) {
            say(line, 'Not connected: ' + v.why, 'warn');
          } else {
            say(line, 'Not checked yet.', '');
          }
          inner.appendChild(row([
            ghost(v.available ? 'Check again' : 'Confirm connection', () => confirm(line),
                  { 'data-autofocus': v.available ? null : '1' }),
            el('button', { class: 'linkish', type: 'button', text: 'Sign in as someone else',
              onclick: () => {
                inner.textContent = '';
                inner.appendChild(form(''));
                paintActions();
              } }),
          ]));
          if (justSignedIn) confirm(line);
        } else {
          const email = String(((BARRY.profile && BARRY.profile.get && BARRY.profile.get()) || {}).email || '');
          const guess = /@uvm\.edu$/i.test(email) ? email.split('@')[0] : '';
          inner.appendChild(form(guess));
        }
        paintActions();
        const af = inner.querySelector('[data-autofocus]');
        if (af) setTimeout(() => { try { af.focus(); } catch (e) { /* fine */ } }, 30);
      }

      if (st.signin) draw();
      else {
        inner.appendChild(stateLine('Looking at this computer…', 'busy'));
        Promise.all([
          api('/api/vacc/signin/state').catch((e) => ({ error: e.message })),
          api('/api/vacc/status').catch(() => null),
        ]).then(([s, v]) => {
          st.signin = s;
          st.vstatus = v;
          // What this computer has, before anything connects.
          if (s && !s.error) {
            term.local('ssh client on this computer: ' + (s.have_ssh ? 'yes' : 'no'),
                       s.have_ssh ? 'ok' : 'warn');
            const keys = (s.other_keys || []).length + (s.have_key ? 1 : 0);
            term.local(keys + ' ssh key' + (keys === 1 ? '' : 's') + ' here'
              + (s.key_path ? ', in use: ' + s.key_path : ''), 'dim');
            term.local(s.configured ? 'signed in already as ' + s.netid + ' on ' + s.host
                                    : 'not signed in to the VACC on this computer yet',
                       s.configured ? 'ok' : '');
            if (v && v.checked_at) {
              term.local('last answer from the cluster: '
                + (v.available ? 'up' : 'down' + (v.why ? ' (' + v.why + ')' : ''))
                + ', ' + Math.max(0, Math.round(Date.now() / 1000 - v.checked_at)) + ' s ago',
              v.available ? 'dim' : 'warn');
            }
          }
          if (!closed && st.at === 'vacc') draw();
        });
      }
      paintActions();
      return box;
    }

    /* ---------------------------------------------------------- 3  find */
    function find() {
      const box = el('div', {});
      box.appendChild(head('Your recordings',
        'Jarvis looks through the cluster and the lab’s netfiles share and matches '
        + 'every recording it finds to the catalogue. Nothing is copied and nothing '
        + 'is added until you say so.'));
      // Where to look, then the console, then what was found: the console
      // sits between the buttons that start a walk and the counts it moves.
      const inner = el('div', { class: 'wl-find' });
      const rest = el('div', { class: 'wl-find' });
      box.appendChild(inner);
      /* Every folder each walk finds, as it finds it, and every recording
         added. A walk finishing reads the result at once rather than at the
         next five-second look. */
      const term = terminal({
        show: (t) => !t || /^walk:/.test(t) || t === 'add',
        onDone: (t) => { if (/^walk:/.test(t) && !closed && st.at === 'find') read(false); },
      });
      box.appendChild(term.node);
      box.appendChild(rest);
      st.term = term;
      term.start();
      const told = new Set();
      /* The result, said line by line once it is in hand: where it looked,
         the count, then every recording new to Jarvis, every one that needs
         a person, every folder that names nobody. */
      function tell(f) {
        if (!f || !f.ok || f.walking) return;
        const key = f.digest || JSON.stringify([f.n_new, f.n_matched, f.n_refused]);
        if (told.has(key)) return;
        told.add(key);
        for (const r of (f.roots || [])) {
          term.local((r.kind === 'netfiles' ? 'netfiles  ' : 'VACC  ') + r.root + '  ·  '
            + (r.age_s == null ? 'not looked through yet'
              : (r.n || 0).toLocaleString() + ' recordings, looked through ' + ago(r.age_s)), 'dim');
        }
        term.local('matched against the catalogue: ' + n(f.n_matched) + ' already in '
          + word + ', ' + n(f.n_new) + ' new, ' + n(f.n_refused) + ' need a person, '
          + n(f.n_unidentifiable) + ' name no mouse and session', 'hot');
        for (const r of (f.new || [])) {
          term.local('new      ' + (r.label || r.key) + '  ' + (r.where || '')
            + (r.copies > 1 ? '  · ' + r.copies + ' copies' : ''), 'ok');
        }
        if (f.n_new > (f.new || []).length) {
          term.local('… and ' + n(f.n_new - f.new.length) + ' more new', 'ok');
        }
        for (const r of (f.refused || [])) {
          term.local('ask      ' + r.path + '  — ' + r.why, 'warn');
        }
        for (const r of (f.unidentifiable || [])) term.local('no name  ' + r.path, 'dim');
      }
      const skip = ghost('Skip for now', () => { st.did.find = st.did.find || 'skipped'; go('done'); },
        { title: 'Later: Sessions › VACC has the same two buttons.' });
      const next = primary('Continue', () => { st.did.find = 'done'; go('done'); });
      box.appendChild(row([skip, next]));

      const signedIn = () => !!((st.vstatus && st.vstatus.configured)
                                || (st.signin && st.signin.configured));
      const n = (x) => Number(x || 0).toLocaleString();
      const ago = (s) => (s == null ? 'never'
        : s < 90 ? 'just now' : s < 5400 ? Math.round(s / 60) + ' min ago'
          : s < 129600 ? Math.round(s / 3600) + ' h ago' : Math.round(s / 86400) + ' days ago');

      async function read(look) {
        if (look) {
          term.local(look === 'netfiles'
            ? 'Find everything on netfiles: the cluster walks the lab’s share (minutes)'
            : 'Find everything on VACC: scratch, the uploads and temp (seconds)');
        }
        try {
          st.found = look ? await apiPost('/api/vacc/found/look', { which: look })
                          : await api('/api/vacc/found');
        } catch (e) {
          st.found = { ok: false, error: e.message };
        }
        if (closed || st.at !== 'find') return;
        if (st.found && st.found.note) term.local(st.found.note, 'warn');
        if (st.found && !st.found.ok) term.local(st.found.error || 'could not read it', 'warn');
        for (const r of ((st.found && st.found.started) || [])) {
          term.local('asked for a walk of ' + r, 'dim');
        }
        tell(st.found);
        draw();
        clearTimeout(pollTimer);
        if (st.found && st.found.walking) {
          pollTimer = setTimeout(() => { if (!closed && st.at === 'find') read(false); }, 5000);
        }
      }

      async function add(btn, line) {
        const f = st.found || {};
        if (!f.n_new || st.busy) return;
        st.busy = true; btn.disabled = true; btn.textContent = 'Adding…';
        term.local('Add ' + n(f.n_new) + ' recordings found: each gets a permanent id', 'hot');
        try {
          const got = await apiPost('/api/vacc/found/add', { confirm: true, digest: f.digest });
          st.added = (st.added || 0) + (got.added || 0);
          log('welcome.found.add', { added: got.added });
          try { if (BARRY.vacc && BARRY.vacc.loadKnows) await BARRY.vacc.loadKnows(true); }
          catch (e) { /* the marks catch up on their own */ }
          st.did.find = 'done';
          st.found = null;
          await read(false);
        } catch (e) {
          say(line, e.message, 'warn');
          btn.disabled = false;
        } finally {
          st.busy = false;
        }
      }

      function draw() {
        inner.textContent = '';
        rest.textContent = '';
        term.node.hidden = !signedIn();
        if (!signedIn()) {
          inner.appendChild(el('p', { class: 'wl-state', 'data-kind': 'warn',
            text: 'Looking needs the VACC: the cluster is what reads netfiles. Go back a '
                + 'step to sign in, or skip this and do it later from Sessions › VACC.' }));
          inner.appendChild(row([ghost('Back to the VACC', () => go('vacc'))]));
          next.hidden = true;
          return;
        }
        const f = st.found;
        if (!f) {
          inner.appendChild(el('p', { class: 'wl-state', 'data-kind': 'busy',
                                      text: 'Reading what the cluster holds…' }));
          return;
        }
        if (!f.ok) {
          inner.appendChild(el('p', { class: 'wl-state', 'data-kind': 'warn',
            text: f.error || 'Could not read what the cluster holds.' }));
        }
        const roots = f.roots || [];
        const busyKind = (k) => roots.some((r) => r.busy && (k === 'netfiles'
          ? r.kind === 'netfiles' : r.kind !== 'netfiles'));
        const lookedKind = (k) => roots.some((r) => r.age_s != null && (k === 'netfiles'
          ? r.kind === 'netfiles' : r.kind !== 'netfiles'));

        const place = (kind, title, cost) => {
          const mine = roots.filter((r) => (kind === 'netfiles') === (r.kind === 'netfiles'));
          const busy = busyKind(kind);
          const looked = lookedKind(kind);
          const total = mine.reduce((a, r) => a + (r.age_s != null ? (r.n || 0) : 0), 0);
          const card = el('div', { class: 'wl-place', 'data-state': busy ? 'busy'
            : looked ? 'done' : 'wait' }, [
            el('div', { class: 'wl-place-head' }, [
              el('span', { class: 'wl-mark-dot', 'aria-hidden': 'true' }),
              el('strong', { text: title }),
              el('span', { class: 'wl-hint', text: cost }),
            ]),
            el('p', { class: 'wl-hint', text: busy ? 'Looking through it now…'
              : looked ? n(total) + ' recording' + (total === 1 ? '' : 's') + ' seen, looked through '
                         + ago(Math.min.apply(null, mine.filter((r) => r.age_s != null).map((r) => r.age_s)))
                : 'Not looked through on this computer yet.' }),
            el('button', {
              class: 'btn ' + (looked ? 'ghost sm' : 'ghost'), type: 'button',
              text: busy ? (kind === 'netfiles' ? 'Looking on netfiles…' : 'Looking on VACC…')
                : (kind === 'netfiles' ? 'Find everything on netfiles' : 'Find everything on VACC'),
              disabled: busy ? 'disabled' : null,
              onclick: () => read(kind),
            }),
          ]);
          return card;
        };
        inner.appendChild(el('div', { class: 'wl-places' }, [
          place('vacc', 'The cluster’s own space', 'scratch, uploads, temp — seconds'),
          place('netfiles', 'The lab’s netfiles share', 'about two and a half minutes'),
        ]));
        for (const d of (f.denied_roots || [])) {
          inner.appendChild(el('p', { class: 'wl-state', 'data-kind': 'warn',
            text: d + ' is there, and this account (' + (f.netid || '?') + ') cannot read it — '
                + 'ask Shahriar to have it added to the jarvis_writes group.' }));
        }

        const any = roots.some((r) => r.age_s != null);
        if (any || st.added) {
          const byProj = Object.entries(f.new_by_project || {})
            .sort((a, b) => b[1] - a[1]).map(([p, k]) => k + ' ' + p).join(', ');
          rest.appendChild(el('div', { class: 'wl-tally' }, [
            el('div', { class: 'wl-num' }, [el('strong', { text: n(f.n_matched) }),
              el('span', { text: 'already in ' + word })]),
            el('div', { class: 'wl-num', 'data-hot': f.n_new ? '1' : null }, [
              el('strong', { text: n(f.n_new) }),
              el('span', { text: 'new' + (byProj ? ' — ' + byProj : '') })]),
            el('div', { class: 'wl-num' }, [el('strong', { text: n(f.n_refused) }),
              el('span', { text: 'need a person to say which' })]),
            el('div', { class: 'wl-num' }, [el('strong', { text: n(f.n_unidentifiable) }),
              el('span', { text: 'folders that name no mouse and session — left alone' })]),
          ]));
          const line = msgLine();
          if (st.added) {
            say(line, n(st.added) + ' recording' + (st.added === 1 ? '' : 's')
              + ' added. Every tool now offers them, labelled VACC loaded.', 'ok');
          }
          if (f.n_new) {
            const addBtn = primary('Add ' + n(f.n_new) + ' recording' + (f.n_new === 1 ? '' : 's')
                                   + ' found', null);
            addBtn.addEventListener('click', () => add(addBtn, line));
            rest.appendChild(row([addBtn]));
            rest.appendChild(el('p', { class: 'wl-hint', text: 'Each gets a permanent id in the '
              + 'catalogue. Nothing is copied and nothing on the cluster changes; the new records '
              + 'travel to the lab like any others.' }));
          }
          rest.appendChild(line);
        }
        next.hidden = !(any || st.added);
        skip.hidden = !!(any || st.added);
        // One primary at a time: while there is something to add, adding is it.
        next.className = 'btn ' + (f.n_new ? 'ghost' : 'wl-go');
        if (any && !st.did.find) st.did.find = 'done';
        if (!any) st.did.find = st.did.find === 'done' ? 'done' : null;
      }

      if (st.found) draw();
      else { draw(); if (signedIn()) read(false); }
      return box;
    }

    /* ---------------------------------------------------------- done */
    function finished() {
      const who = (BARRY.profile && BARRY.profile.who && BARRY.profile.who()) || '';
      const first = who.split(/\s+/)[0] || '';
      const item = (label, state, yes, no) => el('li', { class: 'wl-sum',
                                                         'data-state': state || 'skipped' }, [
        el('span', { class: 'wl-dot', text: state === 'done' ? '✓' : '–' }),
        el('span', {}, [el('strong', { text: label }),
                        el('span', { class: 'wl-hint', text: '  ' + (state === 'done' ? yes : no) })]),
      ]);
      const v = st.vstatus || {};
      return el('div', { class: 'wl-hello' }, [
        el('h1', { class: 'wl-big', text: first ? 'You’re set, ' + first + '.' : 'You’re set.' }),
        el('ul', { class: 'wl-plan' }, [
          item('You', st.did.you, who, 'not said yet'),
          item('VACC', st.did.vacc, 'connected as ' + (v.netid || '?'),
               'later, from your profile'),
          item('Recordings', st.did.find, st.added ? st.added.toLocaleString() + ' added'
               : 'looked through', 'later, from Sessions › VACC'),
        ]),
        row([primary('Open ' + word, () => close('finished'), { 'data-autofocus': '1' })]),
        el('p', { class: 'wl-hint', text: 'This is on the start screen as “Set up this '
          + 'computer” whenever you want it again.' }),
      ]);
    }

    // `go` for a harness that wants a step without filling in the ones before.
    live = { close, go };
    paint();
    log('welcome.open', { forced: forced(), from: o.from || 'boot' });
    return live;
  }

  /* ------------------------------------------------------------ entries */
  /* Whether this computer still needs it: nobody has said who they are. */
  function needs(prof) {
    if (forced()) return true;
    return !!prof && !prof.set;
  }

  /* From the boot overlay (core.js `BARRY.boot.clear`). True when it has
     taken the overlay -- or is finding out whether to -- and will call
     `after()` when the welcome is over, or `instead()` when it turns out
     not to be wanted; false to let the start menu have it now.
     Synchronous where it can be, so a computer that is set up loses no time
     waiting for an answer it already has. */
  function maybe(box, after, instead) {
    const not = instead || after;
    if (!frameOk()) return false;
    const prof = BARRY.profile && BARRY.profile.get && BARRY.profile.get();
    if (prof && !needs(prof)) return false;
    (async () => {
      let p = prof;
      if (!p) {
        try { p = await BARRY.profile.load(); } catch (e) { p = null; }
      }
      // Set up after all, or an older server with no profile route.
      if (!needs(p)) { not(); return; }
      box.classList.add('boot-menu', 'boot-welcome');
      if (BARRY.ui && BARRY.ui.reducedMotion && BARRY.ui.reducedMotion()) {
        box.classList.add('still');
      }
      build(box, () => after(), { from: 'boot' });
    })().catch((e) => {
      reportClientError('welcome.boot', e.message, e.stack);
      not();
    });
    return true;
  }

  /* On demand: the start menu's "Set up this computer". */
  function open() {
    if (live) return live;
    const shade = el('div', { class: 'wl-overlay boot-welcome' });
    document.body.appendChild(shade);
    return build(shade, () => {
      shade.classList.add('gone');
      setTimeout(() => shade.remove(), 380);
    }, { escape: true, from: 'menu' });
  }

  return { maybe, open, needs, get open_() { return !!live; } };
})();
