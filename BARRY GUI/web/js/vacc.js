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

  async function go(path) {
    here = null;
    reopen();
    try {
      here = await api('/api/vacc/browse' + (path ? ('?path='
             + encodeURIComponent(path)) : ''));
    } catch (e) {
      here = { error: e.message, dirs: [], recordings: [] };
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
      go(null);
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

        !d.configured ? el('p', { class: 'hint',
          text: 'Nobody has set up a VACC account on this computer. Jarvis '
              + 'needs a NetID and an SSH key that already works — run '
              + '"ssh <netid>@login.vacc.uvm.edu" in a terminal once; if it '
              + 'asks for a password, the key is not installed there yet.' }) : null,

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
    // The reachability answer is local arithmetic and cheap, so it is worth
    // having before anything asks for it. It is also useful with the cluster
    // down, which is why it does not wait on the status above succeeding.
    loadKnows();
  }

  function watch(on) {
    // Only while a panel or tool that shows it is open.
    if (on && !timer) timer = setInterval(() => status(), 15000);
    if (!on && timer) { clearInterval(timer); timer = null; }
  }

  return { init, status, showVacc, loadKnows, of, watch,
           get last() { return last; },
           counts: {}, drives: {} };
})();
