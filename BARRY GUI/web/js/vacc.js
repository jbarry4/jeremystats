/* ==========================================================================
   vacc.js -- the cluster, as far as the interface is concerned.

   Two separate things live here and they must not be confused, because
   confusing them is a bug with somebody's job on the end of it:

     BARRY.state.vacc      what the interface LOOKS like. A display
                           preference. See applyVacc in core.js.

     status().configured   what the cluster can DO. Whether there is an
                           account, whether ssh answers, what is queued.

   The switch may add affordances; it may never take one away. Turn the glow
   off because your eyes hurt and the Cancel button for a job still running
   on a shared cluster has to still be there.

   Nothing here polls on a timer by default. A permanent poller for a machine
   nobody is using is exactly what toolfeed's stop() discipline exists to
   prevent, so the status is read once at boot and then only while somebody
   is looking at it.
   ========================================================================== */
BARRY.vacc = (function () {
  let last = null;                 // the last /api/vacc/status payload
  let knows = null;                // gid -> {state, remote, why}
  let knowsAt = 0;
  let timer = null;

  const KNOWS_TTL = 60000;

  /* ---- status ---------------------------------------------------------- */
  async function status(force) {
    try {
      last = force ? await api('/api/vacc/check', { method: 'POST' })
                   : await api('/api/vacc/status');
    } catch (e) {
      // A cluster that cannot be asked is not an error on screen. It is a
      // cluster that cannot be asked.
      last = { ok: true, configured: false, available: false,
               why: 'Jarvis could not reach its own backend.' };
    }
    paintChip();
    return last;
  }

  function paintChip() {
    const btn = $('#vaccToggle');
    if (!btn) return;
    const d = last || {};
    // Visible when there is a cluster to talk to -- or when somebody already
    // turned the mode on, because a control that vanishes from under a
    // person is worse than one that is merely useless.
    btn.hidden = !(d.configured || BARRY.state.vacc);
    btn.classList.toggle('on', !!BARRY.state.vacc);
    btn.classList.toggle('vacc-live', !!d.available);
    const bits = [];
    if (!d.configured) bits.push('no account set up here');
    else if (!d.available) bits.push(d.why || 'not reachable');
    else {
      bits.push(d.host || 'VACC');
      if (d.running != null) bits.push(d.running + ' running');
      if (d.queued) bits.push(d.queued + ' queued');
    }
    btn.title = 'VACC Mode — ' + bits.join(' · ');
  }

  /* ---- what the cluster can reach -------------------------------------- */
  async function loadKnows(force) {
    if (!force && knows && (Date.now() - knowsAt) < KNOWS_TTL) return knows;
    try {
      const got = await api('/api/vacc/knows');
      knows = got.knows || {};
      knowsAt = Date.now();
      BARRY.vacc.counts = got.counts || {};
      BARRY.vacc.drives = got.drives || {};
    } catch (e) {
      knows = knows || {};
    }
    return knows;
  }

  /* What the cluster makes of one recording.

     Returns null -- not 'local-only' -- for anything nobody has established,
     and the difference is the whole point. A scanned row often has no gid at
     all, because exact ids are only minted when headers are read; treating a
     missing answer as "cannot reach it" is how you tell somebody to upload
     four hundred recordings that are already on the share. `canOpen` in
     sessions.js carries a comment about the same mistake. */
  function of(sess) {
    if (!knows || !sess) return null;
    const gid = sess.gid || (sess.identity && sess.identity.gid);
    if (!gid) return null;
    return knows[gid] || null;
  }

  /* ---- looking around the cluster --------------------------------------- */
  let here = null;           // the listing of wherever we are
  let scanning = false;
  let lastScan = null;       // what the last dry run said it would do
  /* In flight. `browseBox` draws, sees no listing, asks `go` to fetch one,
     and `go` clears the listing and redraws before awaiting anything -- so
     the draw re-entered the fetch, which redrew, without bound. It took the
     whole interface down with "Maximum call stack size exceeded". A draw
     must never be able to start work that draws again. */
  let loading = false;

  async function go(path) {
    if (loading) return;
    loading = true;
    here = null;
    reopen();
    try {
      here = await api('/api/vacc/browse' + (path ? ('?path='
             + encodeURIComponent(path)) : ''));
    } catch (e) {
      here = { error: e.message, dirs: [], recordings: [] };
    } finally {
      loading = false;
    }
    lastScan = null;
    reopen();
  }

  /* The panel is a modal built in one go, so changing what is in it means
     building it again. Cheap, and it keeps the browse state in one place
     rather than threading DOM nodes through every handler.

     `replace` rather than close-then-open: `showModal` keeps a stack so a
     dialog can sit over a panel and give it back afterwards, and closing to
     redraw would pop whatever was underneath. Rebuilt in place, and only
     while the panel is actually open -- a browse that finished after
     somebody shut the window must not reopen it. */
  function reopen() {
    const shell = document.getElementById('bigModal');
    if (!shell || shell.classList.contains('hidden')) return;
    showVacc();
  }

  function crumbs(at) {
    const root = (last || {}).scratch_root
      || ((here || {}).root) || '';
    const out = [];
    const parts = String(at || '').split('/').filter(Boolean);
    let acc = '';
    out.push(el('button', { class: 'vacc-crumb', text: '/',
                            onclick: () => go('/') }));
    for (const p of parts) {
      acc += '/' + p;
      const target = acc;
      out.push(el('button', { class: 'vacc-crumb', text: p,
                              onclick: () => go(target) }));
    }
    return el('div', { class: 'vacc-crumbs' }, out);
  }

  function browseBox() {
    const box = el('div', { class: 'vacc-browse' });
    if (!here) {
      box.appendChild(el('p', { class: 'hint quiet', text: 'Looking…' }));
      if (!loading) go(null);
      return box;
    }
    if (here.error) {
      box.appendChild(el('p', { class: 'warn-line', text: here.error }));
      return box;
    }
    box.appendChild(crumbs(here.at));

    const list = el('div', { class: 'vacc-ls' });
    const up = String(here.at || '').replace(/\/[^/]+$/, '') || '/';
    if (here.at && here.at !== '/') {
      list.appendChild(el('button', { class: 'vacc-ls-row up', text: '..',
                                      onclick: () => go(up) }));
    }
    for (const d of (here.dirs || [])) {
      list.appendChild(el('button', { class: 'vacc-ls-row dir', text: d.name,
                                      onclick: () => go(d.path) }));
    }
    for (const r of (here.recordings || [])) {
      list.appendChild(el('div', { class: 'vacc-ls-row rec' }, [
        el('span', { text: r.name }),
        el('span', { class: 'vr-n', text: r.n_channels + ' ch' }),
      ]));
    }
    if (!(here.dirs || []).length && !(here.recordings || []).length) {
      list.appendChild(el('p', { class: 'hint quiet', text: 'Nothing here.' }));
    }
    box.appendChild(list);

    box.appendChild(el('div', { class: 'tk-actions' }, [
      el('button', {
        class: 'btn ghost', text: scanning ? 'Scanning…' : 'Scan this folder',
        disabled: scanning ? 'disabled' : null,
        onclick: () => scan(here.at, true),
      }),
      el('span', { class: 'hint quiet',
        text: 'Walks everything under it and says what it would do first.' }),
    ]));

    if (lastScan) box.appendChild(scanReport(lastScan));
    return box;
  }

  function scanReport(d) {
    const box = el('div', { class: 'vacc-scan' });
    const n = (d.added || []).length;
    box.appendChild(el('div', { class: 'hint',
      text: d.n_found + ' recording(s) under it. '
          + (d.dry ? 'Nothing has been written yet.' : 'Done.') }));
    const line = (label, rows, cls) => rows.length
      ? el('details', { class: cls || '' }, [
          el('summary', { text: rows.length + ' ' + label }),
          el('div', {}, rows.slice(0, 40).map((r) => el('div', {
            class: 'hint quiet',
            text: (r.label ? r.label + ' — ' : '')
                + (r.path || '').replace(d.root + '/', '')
                + (r.why ? '  (' + r.why + ')' : '') }))),
        ])
      : null;
    const bits = [
      line(d.dry ? 'would gain a cluster path' : 'gained a cluster path',
           d.added || []),
      line('already had it', d.already || []),
      line('not a recording Jarvis knows — left alone', d.unmatched || []),
      line('too ambiguous to match — refused', d.ambiguous || [], 'warn-line'),
    ].filter(Boolean);
    bits.forEach((b) => box.appendChild(b));

    if (d.dry && n) {
      box.appendChild(el('div', { class: 'tk-actions' }, [
        el('button', {
          class: 'btn', text: 'Add ' + n + ' path(s) to the registry',
          disabled: scanning ? 'disabled' : null,
          onclick: () => scan(d.root, false),
        }),
        el('span', { class: 'hint quiet',
          text: 'Paths only. Nothing new is created.' }),
      ]));
    } else if (d.dry && !n) {
      box.appendChild(el('p', { class: 'hint quiet',
        text: 'Nothing to add — every recording under here that Jarvis knows '
            + 'already carries its cluster path.' }));
    }
    return box;
  }

  async function scan(path, dry) {
    scanning = true;
    reopen();
    try {
      lastScan = await apiPost('/api/vacc/scan', { path, dry: !!dry });
      if (!dry) {
        toast((lastScan.added || []).length + ' cluster path(s) added.', 'ok');
        knows = null;            // reachability just changed
      }
    } catch (e) {
      toast(e.message, 'err', 9000);
    } finally {
      scanning = false;
      reopen();
    }
  }

  /* ---- the panel -------------------------------------------------------- */
  /* ==================================================================
     Getting onto the cluster the first time
     ==================================================================
     A netid is all anybody should have to know. The account is
     `<netid>@login.vacc.uvm.edu`, and the home and scratch directories are
     derived from it -- so this asks for the netid, asks for a password
     once, and never asks for a password again.

     Once, because what it does with the password is install an SSH key.
     After that the key logs in, which is also what removes the Duo prompt
     from every subsequent connection -- and that matters more than
     convenience: the status chip polls, and a second factor every ten
     seconds for six hours is not a thing anybody would leave on.

     The password is typed here, sent over localhost, held in the
     environment of exactly one ssh process, and dropped when it exits. It
     is not stored, not logged, and not kept in this module after the
     request returns -- which is why the field is cleared in a `finally`
     rather than on success. */
  let signState = null;
  let signBusy = false;

  /* Asked once, when somebody first says they want the cluster.

     Not a nag. A person who signed out deliberately and is toggling the
     mode for the look gets asked the first time and then left alone for
     the rest of the session -- `asked` is per page load, so restarting
     Jarvis offers again, which is right on a shared rig where the next
     person at the keyboard is a different person. */
  let asked = false;

  async function offerSignIn() {
    if (asked) return;
    let st = last;
    if (!st) { try { st = await status(); } catch (e) { st = null; } }
    if (st && st.configured) return;      // somebody is already signed in
    asked = true;
    /* Profile, not a sign-in box of its own.

       "Which VACC account is this computer" is the same question as "who
       does this computer credit work to", and both belong in the same
       place -- so the first time somebody turns the mode on they land on
       the page that already answers the first question, with the second
       one on it, rather than meeting a modal about SSH keys with no
       context around it.

       Falls back to the sign-in panel where there is no profile module,
       which is every pop-out window: those carry `BARRY` but not every
       view, and a pop-out that could not offer sign-in at all would be
       worse than one that offers it plainly. */
    if (BARRY.profile && BARRY.profile.open) {
      BARRY.profile.open();
      toast('Sign in to VACC to run anything on it — it is on your '
            + 'profile, under VACC account.', null, 9000);
      return;
    }
    showSignIn();
  }

  async function signOut() {
    const who = (last || {}).netid || 'this machine';
    try {
      const res = await apiPost('/api/vacc/signout', {});
      toast('Signed out of ' + (res.was || who) + '. The key is left where '
            + 'it is, so signing back in — as anyone — asks for no '
            + 'password.', 'ok', 8000);
      signState = null;
      await status(true);
      /* Offer again straight away: signing out is almost always the first
         half of signing in as somebody else. */
      asked = false;
      showSignIn();
      BARRY.activity.log('vacc.signout', { was: res.was });
    } catch (e) { toast(e.message, 'err', 8000); }
  }

  async function showSignIn() {
    signState = null;
    showModal(signInBody());
    try {
      signState = await api('/api/vacc/signin/state');
    } catch (e) {
      signState = { error: e.message };
    }
    repaintSignIn();
  }

  /* Redrawn in place, never closed and reopened.

     `showModal` keeps a stack so a dialog can sit over the VACC panel and
     hand it back afterwards -- so closing to redraw would pop whatever was
     underneath, and somebody who opened this from the panel would find the
     panel gone. `{replace: true}` is the option that exists for exactly
     this, and `reopen()` above uses it for the same reason.

     Only while it is actually open: a state read that finishes after
     somebody shut the window must not reopen it. */
  function repaintSignIn() {
    const shell = document.getElementById('bigModal');
    if (!shell || shell.classList.contains('hidden')) return;
    showModal(signInBody(), { replace: true });
  }

  function signInBody() {
    const st = signState || {};
    const box = el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Sign in to VACC' }),
        el('span', { class: 'sub', text: st.host || 'login.vacc.uvm.edu' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
    ]);
    const b = el('div', { class: 'mb' });
    box.appendChild(b);

    if (!signState) {
      b.appendChild(el('p', { class: 'hint quiet',
                              text: 'Looking at this machine…' }));
      return box;
    }
    if (st.error) {
      b.appendChild(el('p', { class: 'warn-line', text: st.error }));
      return box;
    }
    if (!st.have_ssh) {
      /* Nothing else on this panel can work, so nothing else is shown.
         The same rule `runner.MATLAB_EXE` follows: a capability that is
         missing is said once, plainly, instead of being discovered by
         every button failing differently. */
      b.appendChild(el('p', { class: 'warn-line',
        text: 'There is no ssh client on this computer, so Jarvis cannot '
            + 'reach the cluster from here at all. On Windows it comes with '
            + '"OpenSSH Client" under Settings › Optional features.' }));
      return box;
    }

    if (st.configured) {
      b.appendChild(el('p', { class: 'vacc-state up',
        text: 'This machine is already signed in as ' + st.netid + '.' }));
    }

    b.appendChild(el('p', { class: 'hint', style: 'max-width:70ch',
      text: 'Your NetID is the part of your UVM email in front of the @. '
          + 'Everything else — which machine to connect to, where your '
          + 'home and scratch directories are — follows from it.' }));

    const netid = el('input', {
      type: 'text', id: 'vaccNetid', spellcheck: 'false',
      autocomplete: 'username', placeholder: 'netid',
      value: st.netid || '',
    });
    b.appendChild(el('label', { class: 'vacc-field' }, [
      el('span', { text: 'NetID' }), netid,
    ]));

    /* No key picker.

       There used to be a dropdown offering the keys already on this
       machine, which asked a question nobody in this lab can answer: the
       undergraduates who rotate through the rig do not know what an
       `id_ed25519` is, and the right answer was always "whichever one
       works". So the server tries them, and the only question left is the
       one everybody can answer -- which account. */
    const pw = el('input', {
      type: 'password', id: 'vaccPassword',
      autocomplete: 'current-password', placeholder: 'UVM password',
    });
    b.appendChild(el('div', { id: 'vaccPwWrap' }, [
      el('label', { class: 'vacc-field' }, [
        el('span', { text: 'Password' }), pw,
      ]),
      el('p', { class: 'hint', style: 'max-width:70ch',
        text: 'Only needed the first time this computer connects to your '
            + 'account. Jarvis tries the keys it already has first, and '
            + 'asks for this only when none of them work.' }),
      el('p', { class: 'hint', style: 'max-width:70ch',
        text: 'It is used once, to install an SSH key, and then dropped — '
            + 'not written to disk, not kept, and not sent anywhere except '
            + 'to the cluster you are signing in to. After that the key '
            + 'signs in and you are never asked again.' }),
    ]));

    const msg = el('p', { class: 'hint quiet', id: 'vaccSignMsg' });
    const go = el('button', {
      class: 'btn', id: 'vaccSignGo',
      text: st.configured ? 'Sign in again' : 'Sign in',
      onclick: () => doSignIn(),
    });
    b.appendChild(el('div', { class: 'vacc-actions' }, [
      go,
      el('button', { class: 'btn ghost', text: 'Cancel',
                     onclick: closeModal }),
    ]));
    b.appendChild(msg);

    netid.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') pw.focus();
    });
    pw.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') doSignIn();
    });
    setTimeout(() => (st.netid ? pw : netid).focus(), 40);
    return box;
  }

  async function doSignIn() {
    if (signBusy) return;
    const netidEl = document.getElementById('vaccNetid');
    const pwEl = document.getElementById('vaccPassword');
    const msg = document.getElementById('vaccSignMsg');
    const go = document.getElementById('vaccSignGo');
    const netid = (netidEl && netidEl.value || '').trim();
    const password = (pwEl && pwEl.value) || '';

    if (!netid) {
      if (msg) { msg.className = 'warn-line'; msg.textContent =
        'A NetID is needed — it is the part of your UVM email before '
        + 'the @.'; }
      return;
    }
    /* No password is NOT an error. It is the ordinary case on a machine
       where somebody has already set the cluster up: the server tries the
       keys it has and only comes back asking if none of them work. */

    signBusy = true;
    if (go) { go.disabled = true; go.textContent = 'Signing in…'; }
    if (msg) {
      msg.className = 'hint quiet';
      msg.textContent = password
        ? 'Installing a key on the cluster…'
        : 'Trying the keys this computer already has…';
    }
    try {
      const res = await apiPost('/api/vacc/signin', { netid, password });
      toast(res.already_installed && !res.made_key
        ? 'Signed in as ' + res.netid + '. That key was already on the '
          + 'cluster.'
        : 'Signed in as ' + res.netid + '. A key is installed, so this will '
          + 'not ask again.', 'ok', 8000);
      closeModal();
      await status(true);
      BARRY.activity.log('vacc.signin', { netid: res.netid,
                                          made_key: !!res.made_key });
    } catch (e) {
      if (msg) {
        msg.className = 'warn-line';
        msg.textContent = e.message;
      }
      /* "No key works yet" is the server asking for the password, not a
         failure to report and walk away from. Put the cursor where the
         answer goes. */
      if (/password is needed once/i.test(e.message || '') && pwEl) {
        pwEl.focus();
      }
    } finally {
      /* Cleared here rather than on success, because a failed attempt is
         exactly when a password is most likely to be left sitting in a
         field on somebody's screen. */
      if (pwEl) pwEl.value = '';
      signBusy = false;
      if (go) { go.disabled = false; go.textContent = 'Sign in'; }
    }
  }

  function showVacc() {
    const d = last || {};
    const c = BARRY.vacc.counts || {};
    const row = (k, v) => el('div', { class: 'vacc-row' }, [
      el('span', { class: 'vacc-k', text: k }),
      el('span', { class: 'vacc-v', text: v == null ? '—' : String(v) }),
    ]);

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'VACC' }),
        el('span', { class: 'sub', text: d.host || '' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
                       html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
                       onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { class: 'vacc-state ' + (d.available ? 'up' : 'down'),
                  text: d.available
                    ? 'Connected as ' + (d.netid || '?')
                    : (d.why || 'Not connected.') }),

        /* Who is signed in, and how to stop being them.

           On a shared rig this is the line people actually need: four
           undergraduates take turns and the one thing that is never
           obvious is whose account the last job went to. */
        !d.configured
          ? el('div', {}, [
              el('p', { class: 'hint',
                text: 'Nobody is signed in to VACC on this computer.' }),
              el('button', { class: 'btn', text: 'Sign in to VACC…',
                             onclick: () => showSignIn() }),
            ])
          : el('div', { class: 'vacc-who' }, [
              el('span', { class: 'hint',
                text: 'Signed in as ' + (d.netid || '?') + '.' }),
              el('button', {
                class: 'btn ghost sm', text: 'Switch account…',
                title: 'Sign in as somebody else. The key on this machine is '
                     + 'reused, so it asks for a password only if that '
                     + 'account has never been set up from here.',
                onclick: () => showSignIn(),
              }),
              el('button', {
                class: 'btn ghost sm', text: 'Sign out',
                title: 'Forget this account on this computer. The key is '
                     + 'left alone, here and on the cluster — signing '
                     + 'back in asks for no password.',
                onclick: () => signOut(),
              }),
            ]),

        d.key_in_repo ? el('p', { class: 'warn-line',
          text: 'The SSH key is inside this repository. Move it to ~/.ssh — '
              + 'anything in here can be committed by accident.' }) : null,

        /* The share being mounted and the account being allowed to read it
           are two different facts, and they came apart the first time this
           was pointed at the real cluster. Saying "VACC can read 357 of your
           recordings" while every one of them is refused would send somebody
           to debug a job that was never going to open its input. */
        (d.denied_roots || []).length ? el('p', { class: 'warn-line',
          text: 'VACC mounts ' + d.denied_roots.join(', ') + ', and this '
              + 'account cannot read it. That is a permission on the share '
              + 'rather than anything here — ask vacchelp@uvm.edu to grant '
              + 'your PI group read and execute on it. Until then nothing '
              + 'on that share can be run on the cluster.' }) : null,

        el('div', { class: 'vacc-grid' }, [
          row('Queued', d.queued),
          row('Running', d.running),
          row('Partition', d.partition),
          row('Workspace', d.workspace),
          row('Scratch', d.scratch),
          row('Quota', d.quota || null),
        ]),

        el('h4', { text: 'Look around it' }),
        el('p', { class: 'hint',
          text: 'The cluster’s own filesystem. Scanning a folder tells '
              + 'recordings Jarvis already knows that they also live there '
              + '— it adds a path, and never invents a recording: a '
              + 'permanent id is not something a directory walk should be '
              + 'allowed to mint.' }),
        browseBox(),

        el('h4', { text: 'What it can already read' }),
        el('p', { class: 'hint',
          text: 'Worked out from the paths every machine has recorded for a '
              + 'recording, against the shares the cluster mounts. A '
              + 'recording nobody has opened yet says nothing rather than '
              + 'saying no.' }),
        el('div', { class: 'vacc-grid' }, [
          row('Reads in place', c['native']),
          row('Copied to scratch', c['staged']),
          row('Not reachable from it', c['local-only']),
          row('Not established', c['unknown']),
        ]),

        el('div', { class: 'mf' }, [
          el('button', { class: 'btn ghost', text: 'Check now',
                         onclick: async (e) => {
                           e.target.disabled = true;
                           await status(true);
                           await loadKnows(true);
                           closeModal();
                           showVacc();
                         } }),
        ]),
      ]),
    ]), { replace: true });
  }

  /* ---- boot ------------------------------------------------------------- */
  async function init() {
    await status();
    /* The reachability answer is local arithmetic and cheap -- 0.05 s for
       687 recordings -- but the registry read underneath it is four to
       eight seconds the first time a process asks, and this runs before
       anybody has clicked anything. The server hands back last boot's
       answer for it; this is what happens if the real one turns out to
       differ.

       Nothing here moves anything. The rail chip's tooltip is rewritten and
       the Sessions rows get their VACC marks redrawn, and only if that view
       is the one on screen -- a list somebody is not looking at is re-read
       the next time they open it, which costs nothing and cannot scroll
       under them. */
    if (BARRY.warm) {
      BARRY.warm.onFresh('vacc_knows', async () => {
        await loadKnows(true);
        const v = BARRY.views[BARRY.state.view];
        if (BARRY.state.view === 'sessions' && v && v.repaintQuietly) {
          v.repaintQuietly();
        }
      });
    }
    loadKnows();
  }

  function watch(on) {
    // Only while a panel or tool that shows it is open.
    if (on && !timer) timer = setInterval(() => status(), 15000);
    if (!on && timer) { clearInterval(timer); timer = null; }
  }

  return { init, status, showVacc, loadKnows, of, watch,
           offerSignIn, showSignIn, signOut,
           get last() { return last; },
           counts: {}, drives: {} };
})();
