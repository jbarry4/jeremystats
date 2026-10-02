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
    const take = (got) => {
      knows = got.knows || {};
      BARRY.vacc.counts = got.counts || {};
      BARRY.vacc.drives = got.drives || {};
    };
    /* Last time's answer first, from this browser (web/js/stash.js), so the
       VACC marks on the Sessions cards and the Everything VACC Knows view
       are there while the live answer comes -- only when there is nothing
       yet, and never waited on. `knowsAt` stays 0, so the live answer is
       still asked for and replaces it. */
    let liveDone = false;
    const live = api('/api/vacc/knows').finally(() => { liveDone = true; });
    if (!knows) {
      const was = await BARRY.stash.get('vacc-knows');
      if (was && was.value && !liveDone && !knows) take(was.value);
    }
    try {
      const got = await live;
      take(got);
      knowsAt = Date.now();
      BARRY.stash.put('vacc-knows', got);
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

  /* ---- what the two affirmative states MEAN ----------------------------
     One table, because four surfaces say it and they were saying it four
     times: the card in Sessions, the row detail in Housekeeping, the tab in
     Xplorefinder, and the toast when one opens. Four copies of "green means
     it reads it in place, amber means a scratch copy that gets purged" is
     four chances for one of them to be reworded and the others not, and the
     one that drifts is the one somebody reads before trusting a trace.

     `short` is for anywhere with a name competing for the room -- an
     Xplorefinder tab is 230px. `word` is the full one, for a card that has
     a row to itself. */
  const STATES = {
    native: {
      word: 'VACC', short: 'VACC',
      note: 'read in place, on a share VACC mounts',
      why: (remote) =>
        'The cluster reads this one where it already is'
        + (remote ? ' — ' + remote : '')
        + '\n\nNothing to upload: it is on a share VACC mounts.',
    },
    /* `staged` is the internal name and stays so; what a person reads is
       "uploaded" (constitution §6d). "Staged" said Jarvis had put it there,
       and it had not -- this is a copy found on the cluster, in scratch or
       in a folder a scan was pointed at. */
    staged: {
      word: 'Uploaded to VACC', short: 'VACC',
      note: 'a copy uploaded to the cluster',
      why: (remote) =>
        'A copy of this recording is on the cluster'
        + (remote ? ' — ' + remote : '') + '.\n\n'
        + 'Scratch is not storage — VACC may clear it without notice, so '
        + 'this is a working copy and never the only one. If it goes, '
        + 'upload it again.',
    },
  };

  /* The words for one state, or null. Null for `local-only`, for `unknown`
     and for a recording nobody has established an answer for, because none
     of those three is a thing to say on a card -- see `of`. */
  function words(state) {
    return STATES[state] || null;
  }

  /* THE cluster mark. Every view draws this one, never its own.

     `from` is for a surface that already has the answer and must not ask a
     second source for it: an Xplorefinder session opened off the cluster
     carries `remote_state` from the open itself, and looking the same
     recording up in `knows` could disagree with the read actually
     happening. */
  function mark(sess, opts) {
    opts = opts || {};
    const got = opts.from || of(sess);
    const w = words(got && got.state);
    if (!w) return null;
    return el('span', {
      class: 'flagchip vacc ' + got.state,
      text: opts.compact ? w.short : w.word,
      title: w.why(got.remote),
    });
  }

  /* ---- opening one, off the cluster ------------------------------------- */
  /* Whether a recording can be READ off the cluster.

     Not the same question as `of()`, and the difference is what decides
     whether an Open button exists. `of()` answers four ways and two of them
     are affirmative: `native` is a share VACC mounts, `staged` is a copy in
     its scratch, and both can be opened. `local-only` and `unknown` cannot,
     and neither can a recording nobody has established an answer for -- for
     which `of()` returns null rather than a no, for the reason its own
     comment gives at length. */
  function canRead(sess) {
    const got = of(sess);
    // `words` is the same table the chip draws from, so a state that can be
    // read and a state that gets a mark can never come apart.
    return !!words(got && got.state);
  }

  /* The id a cluster read is opened by.

     A gid, not a path. `vaccio.py` carries the three reasons; the one that
     matters here is that everything attached to a recording -- its view
     state, its bad channels, its curation set, its bank -- is keyed on the
     gid, so a recording read off the cluster has to BE the recording
     somebody opened off Y: last week rather than one that looks like it. */
  function pathFor(sess) {
    const gid = sess && (sess.gid || (sess.identity && sess.identity.gid));
    return gid ? ('vacc:' + gid) : null;
  }

  /* Open it in Xplorefinder, reading off the cluster.

     The same call every other Open in this interface makes. What is
     different is the path, and that is the whole point: a recording on a
     share this computer does not mount opens into the same tabs, the same
     panes and the same curation as one on a drive.

     ONE WAIT, SO ONE `loader`

     Measured: about two seconds to open the recording, and up to five more
     on top when the link has to be started first. There are no named stages
     worth drawing -- `stepLoader` with a dot that lights for zero
     milliseconds is a progress bar lying about where the time goes -- so it
     is `loader`, and it says the size of the job.

     `host` is where it is drawn: the surface the click happened on. Given
     rather than assumed, because the caller is the only thing that knows
     which box it owns.

     AND THE VIEW DOES NOT MOVE UNTIL IT IS OPEN

     Xplorefinder used to be shown first and then filled. Which meant the
     wait happened on a view that had nothing on it yet, so the loader would
     have had to be drawn somewhere the person had just been sent rather
     than where they clicked -- and if the cluster refused, they had been
     moved to an empty viewer to be told so. */
  async function open(sess, opts) {
    const path = pathFor(sess);
    if (!path) {
      toast('This recording has no permanent id yet, so there is nothing to '
            + 'ask the cluster for. Scan the folder it is in first.',
            'err', 8000);
      return null;
    }
    const got = of(sess) || {};
    const host = (opts || {}).host || null;
    const put = host ? Array.from(host.childNodes) : null;
    if (host) {
      host.innerHTML = '';
      host.appendChild(loader(
        'Opening it off the cluster',
        'The link opens, then the recording\u2019s header is read where it '
        + 'is — a few seconds. After that each window is one round trip.'));
    }
    try {
      const opened = await BARRY.views.xplore.open(path);
      if (opened) {
        setView('xplore');
        BARRY.activity.log('vacc.open', { gid: path.slice(5),
                                          state: got.state,
                                          remote: got.remote || null });
      }
      return opened;
    } catch (e) {
      /* A refusal from the cluster is not this: `xplore.open` toasts that
         one itself and hands back null. This is the other kind -- something
         threw where nothing was expected to -- and a catch that only put it
         on the console would be a fault nobody hears about. */
      reportClientError('vacc.open', e.message, e.stack);
      toast('Could not open it off the cluster: ' + e.message, 'err', 9000);
      return null;
    } finally {
      /* Put the surface back whatever happened. A refusal leaves somebody
         looking at the panel they clicked on, with the reason in a toast
         and the button still there to try again. */
      if (host) {
        host.innerHTML = '';
        put.forEach((node) => host.appendChild(node));
      }
    }
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
      BARRY.ui.button({
        kind: 'ghost', text: scanning ? 'Scanning…' : 'Scan this folder',
        disabled: scanning,
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
      /* Nothing is written into the registry: the folder is remembered
         and the recordings under it are known to be on VACC by identity
         (constitution §6d, "a cluster path never enters the registry"). */
      line(d.dry ? 'would be known to be on VACC' : 'now known to be on VACC',
           d.added || []),
      line('already known to be on VACC', d.already || []),
      line('not a recording Jarvis knows — left alone', d.unmatched || []),
      line('too ambiguous to match — refused', d.ambiguous || [], 'warn-line'),
    ].filter(Boolean);
    bits.forEach((b) => box.appendChild(b));

    if (d.dry && n) {
      box.appendChild(el('div', { class: 'tk-actions' }, [
        BARRY.ui.button({
          kind: 'primary', text: 'Look here for recordings on VACC',
          disabled: scanning,
          onclick: () => scan(d.root, false),
        }),
        el('span', { class: 'hint quiet',
          text: 'Jarvis remembers this folder and looks in it as it looks '
              + 'in scratch. Nothing is written into the registry.' }),
      ]));
    } else if (d.dry && !n) {
      box.appendChild(el('p', { class: 'hint quiet',
        text: 'Nothing new — every recording under here that Jarvis knows '
            + 'is already known to be on VACC.' }));
    }
    return box;
  }

  async function scan(path, dry) {
    scanning = true;
    reopen();
    try {
      lastScan = await apiPost('/api/vacc/scan', { path, dry: !!dry });
      if (!dry) {
        toast((lastScan.added || []).length + ' recording(s) now known to be '
              + 'on VACC.', 'ok');
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
    const go = BARRY.ui.button({
      kind: 'primary', id: 'vaccSignGo',
      text: st.configured ? 'Sign in again' : 'Sign in',
      onclick: () => doSignIn(),
    });
    /* Cancel, then the primary. This dialog had them the other way round --
       Sign in on the left, Cancel to the right of it -- which is the reverse
       of every other dialog in the application, and the one place somebody
       reaches for Cancel without reading. */
    b.appendChild(BARRY.ui.actions([
      BARRY.ui.button({ kind: 'ghost', text: 'Cancel', onclick: closeModal }),
      go,
    ], { extra: 'vacc-actions' }));
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
              BARRY.ui.button({ kind: 'primary', text: 'Sign in to VACC…',
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

        sharedBox(d),
        uploadsBox(),
        jobsBox(d),

        el('h4', { text: 'Look around it' }),
        el('p', { class: 'hint',
          text: 'The cluster’s own filesystem. Scanning a folder makes '
              + 'Jarvis look in it, as it looks in scratch, for recordings '
              + 'it already knows. Nothing is written into the registry and '
              + 'no recording is invented: a permanent id is not something '
              + 'a directory walk should be allowed to mint.' }),
        browseBox(),

        el('h4', { text: 'What it can already read' }),
        el('p', { class: 'hint',
          text: 'Worked out from the paths every machine has recorded for a '
              + 'recording, against the shares the cluster mounts. A '
              + 'recording nobody has opened yet says nothing rather than '
              + 'saying no.' }),
        el('div', { class: 'vacc-grid' }, [
          row('Reads in place', c['native']),
          row('Uploaded to VACC', c['staged']),
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

  /* The lab's shared space (constitution §6d): one account owns it and
     everybody else reaches it with their own netid. When this account is
     refused, say what was refused, where to look at it, and who to ask --
     never a bare "permission denied". */
  function sharedBox(d) {
    const sh = d.shared || {};
    if (!sh.root || !d.available) return null;
    const words = {
      ok: 'Open to this account',
      denied: 'Refused to this account',
      missing: 'Not there',
    };
    const dataWords = {
      ok: 'writable — uploads can go here',
      creatable: 'not made yet — the first upload creates it',
      nowrite: 'readable, not writable — an upload would be refused',
      missing: 'not there, and this account cannot create it',
    };
    return el('div', { class: 'vacc-shared' }, [
      el('h4', { text: 'The lab’s shared space' }),
      el('div', { class: 'vacc-grid' }, [
        el('div', { class: 'vacc-row' }, [
          el('span', { class: 'vacc-k', text: sh.root }),
          el('span', { class: 'vacc-v', text: words[sh.state] || 'not checked yet' }),
        ]),
        el('div', { class: 'vacc-row' }, [
          el('span', { class: 'vacc-k', text: sh.data || 'Jarvis Data' }),
          el('span', { class: 'vacc-v',
                       text: dataWords[sh.data_state] || 'not checked yet' }),
        ]),
      ]),
      sh.why ? el('p', { class: 'warn-line', text: sh.why }) : null,
      sh.ondemand ? el('a', {
        class: 'linkish', href: sh.ondemand, target: '_blank',
        rel: 'noopener', text: 'Open it in OnDemand',
      }) : null,
    ].filter(Boolean));
  }

  /* The account's jobs, from `squeue --me` on the routine probe, each
     marked by whether Jarvis on this machine is following it: a run record
     here is what lets a restart pick it up and file its answer. */
  function jobsBox(d) {
    if (!d.available) return null;
    const jobs = d.jobs || [];
    const whose = (j) => (j.followed
      ? 'Jarvis here' + (j.tool ? ' · ' + j.tool : '')
      : j.jarvis ? 'Jarvis, not followed here' : 'not Jarvis');
    const kids = [el('h4', { text: 'Jobs on this account' })];
    if (!jobs.length) {
      kids.push(el('p', { class: 'hint', text: 'Nothing queued or running.' }));
    } else {
      kids.push(el('table', { class: 'tbl vacc-jobs' }, [
        el('thead', {}, [el('tr', {}, ['Job', 'Name', 'State', 'Time', 'Why',
                                       'Followed by'].map((h) => el('th', { text: h })))]),
        el('tbody', {}, jobs.map((j) => el('tr', {
          class: j.followed ? 'on' : '',
        }, [
          el('td', { text: j.id }),
          el('td', { text: j.name }),
          el('td', { text: j.state }),
          el('td', { text: j.elapsed }),
          el('td', { text: j.reason }),
          el('td', { text: whose(j) }),
        ]))),
      ]));
    }
    if ((d.waiting || []).length) {
      kids.push(el('p', { class: 'hint', text:
        'Jarvis here is waiting on ' + d.waiting.length + ' run(s) the cluster '
        + 'no longer lists — finished and being fetched, or lost: '
        + d.waiting.map((w) => (w.tool || 'run') + ' ' + (w.id || w.rid))
          .join(', ') + '.' }));
    }
    if (d.resumed) {
      kids.push(el('p', { class: 'hint', text:
        'Picked up ' + d.resumed + ' batch(es) a previous run of Jarvis left '
        + 'on the cluster.' }));
    }
    const fails = d.failures || [];
    if (fails.length) {
      kids.push(el('p', { class: 'warn-line', text:
        fails.length + ' job(s) ended badly in the last day: '
        + fails.slice(0, 8).map((f) => f.id + ' ' + f.state.toLowerCase())
          .join(', ') + (fails.length > 8 ? ', and more.' : '.') }));
    }
    return el('div', { class: 'vacc-health' }, kids);
  }

  /* ---- uploading to Jarvis Data (constitution §6d) ---------------------

     Two steps, always: the plan -- what would be sent, where, and what is
     already there -- and then the upload, which the server refuses without
     `confirm`. The upload writes to the lab's shared space, so it happens
     only after somebody has seen the plan and pressed the button that says
     how much will be sent. */
  const uploads = new Map();          // job id -> the latest snapshot
  let upTimer = null;
  /* Who wants to know when that changes.

     A set rather than a single callback: the modal and the Sessions pad can
     both be showing uploads, and whichever was wired second must not
     silently replace the first. Each returns its own remover so a view that
     is torn down stops being called -- `leak.html` counts listeners across
     rebuilds for exactly this reason. */
  const upWatchers = new Set();

  function onUploads(fn) {
    if (typeof fn !== 'function') return () => {};
    upWatchers.add(fn);
    return () => upWatchers.delete(fn);
  }

  function uploadsChanged() {
    /* The modal first, if it is open, because it is the one that was
       already claiming to show this. */
    reopen();
    for (const fn of upWatchers) {
      try { fn(); } catch (e) { /* a watcher must not stop the others */ }
    }
  }

  const bytes = (n) => (typeof fmtBytes === 'function' ? fmtBytes(n || 0)
                                                       : (n || 0) + ' B');

  /* Where it goes is asked every time, Scratch first (2026-10-01): the
     lab's shared Jarvis Data, or Temp, the lab's gpfs3tmp space, which
     is purged on a schedule and has its own quota. Each choice is
     planned on its own, because what is already there differs between
     them, and the button says what the chosen one would send. */
  const DEST_SAY = {
    scratch: 'The lab’s shared space, Jarvis Data. Processing space: VACC may clear it, and this is never the only copy.',
    temp: 'The lab’s temporary space (gpfs3tmp), purged on a schedule. The lab’s quota there is about 1 TB.',
  };

  async function upload(gids) {
    const want = (gids || []).filter(Boolean);
    if (!want.length) {
      toast('None of those is a registered recording.', 'warn');
      return null;
    }
    const plans = {};
    let dest = 'scratch';
    try {
      toast('Working out what would be sent…', null, 2500);
      plans[dest] = await apiPost('/api/vacc/upload/plan', { gids: want, dest });
    } catch (e) {
      toast(e.message, 'err', 9000);
      return null;
    }
    const dests = plans[dest].dests && plans[dest].dests.length ? plans[dest].dests
      : [{ id: 'scratch', label: 'Scratch', root: plans[dest].dest_root }];
    const box = el('div', { class: 'vacc-up' });
    let asking = false;
    const okBtn = () => {
      const mb = box.closest('.mb');
      const mf = mb && mb.nextElementSibling;
      return mf ? mf.lastElementChild : null;
    };
    const draw = () => {
      const plan = plans[dest];
      box.innerHTML = '';
      box.appendChild(el('div', { class: 'vacc-up-where' }, [
        el('span', { class: 'vacc-k', text: 'Upload to' }),
        el('div', { class: 'seg', role: 'radiogroup' }, dests.map((d) => el('button', {
          class: d.id === dest ? 'active' : '', 'data-dest': d.id, role: 'radio',
          'aria-checked': d.id === dest ? 'true' : 'false', text: d.label || d.id,
          disabled: asking ? 'disabled' : null,
          onclick: () => choose(d.id) }))),
      ]));
      const d = dests.find((x) => x.id === dest) || {};
      box.appendChild(el('p', { class: 'hint', text: (d.say || DEST_SAY[dest] || '') }));
      if (asking || !plan) {
        box.appendChild(el('p', { class: 'hint', text: 'Working out what ' + (d.label || dest)
          + ' already holds…' }));
      } else {
        const ready = (plan.items || []).filter((i) => !i.why);
        box.appendChild(el('p', { text: 'To ' + (plan.dest_root || d.root || 'Jarvis Data') + ', as '
            + 'project / mouse / recording. A file already there at the same '
            + 'size is skipped, so uploading again sends only what is missing. '
            + 'The copy here is only read.' }));
        if ((plan.shared || {}).why && dest === 'scratch') {
          box.appendChild(el('p', { class: 'warn-line', text: plan.shared.why }));
        }
        /* The lab's quota there, asked of the cluster with the plan: a
           place that is full is said before anything is sent, not found
           out file by file as "Broken pipe". */
        const room = plan.room || {};
        if (room.say) {
          box.appendChild(el('p', { class: room.fits === false ? 'warn-line vacc-up-room' : 'hint vacc-up-room',
            text: room.say }));
        }
        box.appendChild(el('ul', { class: 'fix-steps' }, ready.map((i) => el('li', { text:
          i.label + ' — ' + (i.n_send
            ? i.n_send + ' file(s), ' + bytes(i.bytes)
              + (i.n_skip ? ', ' + i.n_skip + ' already there' : '')
            : 'everything already there') }))
          .concat((plan.blocked || []).map((i) => el('li', {
            class: 'vacc-up-no', text: i.label + ' — ' + i.why })))));
        if (!plan.files) {
          box.appendChild(el('p', { class: 'hint', text: 'Nothing to send to '
            + (d.label || dest) + ': everything is already there.' }));
        }
      }
      const b = okBtn();
      if (b) {
        const n = plan && !asking ? plan.files : 0;
        const full = !!(plan && !asking && (plan.room || {}).fits === false);
        b.disabled = n && !full ? null : 'disabled';
        b.textContent = full ? 'Not enough room in ' + (d.label || dest)
          : n ? 'Upload ' + bytes(plan.bytes) + ' to ' + (d.label || dest)
          : 'Nothing to upload';
      }
    };
    const choose = async (id) => {
      if (id === dest || asking) return;
      dest = id;
      if (!plans[id]) {
        asking = true;
        draw();
        try {
          plans[id] = await apiPost('/api/vacc/upload/plan', { gids: want, dest: id });
        } catch (e) {
          asking = false;
          toast(e.message, 'err', 9000);
          dest = 'scratch';
          draw();
          return;
        }
        asking = false;
      }
      draw();
    };
    draw();
    let started = null;
    const first = plans[dest];
    const asked = BARRY.confirm('Upload to VACC', box,
      first.files ? 'Upload ' + bytes(first.bytes) + ' to Scratch' : 'Nothing to upload',
      false, async () => {
        const plan = plans[dest];
        if (!plan || !plan.files) throw new Error('Nothing to send there.');
        if ((plan.room || {}).fits === false) throw new Error(plan.room.say);
        started = await apiPost('/api/vacc/upload', {
          gids: (plan.items || []).filter((i) => !i.why && i.n_send).map((i) => i.gid),
          dest, confirm: true });
      });
    draw();               // the dialog is up now: the button can be reached
    const ok = await asked;
    if (!ok || !started || !started.job) return null;
    track(started.job);
    /* Names the place it is actually showing, which is the pad somebody
       is already looking at -- they picked the recordings there. It used
       to say "the VACC panel", which opens from the command palette and
       nowhere else. */
    toast('Uploading ' + started.n + ' recording(s) to VACC ('
          + ((dests.find((x) => x.id === dest) || {}).label || dest) + '). Progress is '
          + 'under Everything VACC knows.', 'ok', 7000);
    return started.job.id;
  }

  function track(snap) {
    uploads.set(snap.id, snap);
    if (!upTimer) upTimer = setInterval(pollUploads, 3000);
    uploadsChanged();
  }

  async function pollUploads() {
    if (document.hidden) return;              // nobody can see it (§10)
    for (const [id, was] of uploads) {
      if (was.status !== 'running') continue;
      try {
        const got = await api('/api/cfc/job/' + encodeURIComponent(id));
        const snap = got.job || got;
        uploads.set(id, snap);
        if (snap.status !== 'running') {
          const failed = (snap.members || []).filter((m) => m.status === 'failed');
          toast(snap.status === 'done' && !failed.length
                  ? 'Uploaded to VACC. The cluster will find the copies the '
                    + 'next time it looks.'
                  : 'The upload ' + (snap.status === 'done'
                      ? 'finished with ' + failed.length + ' failed'
                      : snap.status) + (snap.error ? ': ' + snap.error : '.'),
                snap.status === 'done' && !failed.length ? 'ok' : 'err', 9000);
          knows = null;
        }
      } catch (e) { /* the next tick asks again */ }
    }
    /* Said once per tick, not once per job: three recordings finishing in
       the same three seconds is one redraw, not three. */
    uploadsChanged();
    if (![...uploads.values()].some((s) => s.status === 'running')) {
      clearInterval(upTimer);
      upTimer = null;
    }
  }

  function uploadsBox() {
    if (!uploads.size) return null;
    const rows = [];
    for (const snap of uploads.values()) {
      for (const m of (snap.members || [])) {
        rows.push(el('div', { class: 'vacc-row' }, [
          el('span', { class: 'vacc-k', text: m.label || m.id }),
          el('span', { class: 'vacc-v', text: m.status === 'failed'
            ? 'failed: ' + (m.error || '')
            : m.status === 'done' ? (m.step || 'done')
            : (m.of ? 'file ' + Math.min((m.done || 0) + 1, m.of) + ' of ' + m.of
                      + (m.step ? ' · ' + m.step : '')
                    : (m.step || m.status || 'waiting')) }),
        ]));
      }
    }
    return el('div', { class: 'vacc-uploads' }, [
      el('h4', { text: 'Uploads' }),
      el('div', { class: 'vacc-grid' }, rows),
    ]);
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

  return { init, status, showVacc, loadKnows, of, canRead, words, mark,
           uploadsBox, onUploads,
           get nUploads() { return uploads.size; },

           upload, _uploads: uploads,
           /* Hand in a job snapshot as if a poll had returned it.
              `track` is internal -- it also starts the timer -- and the
              upload harness needs to drive the display without a cluster
              and without three seconds between frames. Same path the real
              poll takes, so what is tested is what runs. */
           feed: (snap) => { uploads.set(snap.id, snap); uploadsChanged(); },
           open, pathFor, watch,
           offerSignIn, showSignIn, signOut,
           get last() { return last; },
           counts: {}, drives: {} };
})();
