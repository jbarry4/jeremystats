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
    ]));
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
