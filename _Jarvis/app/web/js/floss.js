/* floss.js -- Floss, the bug fixer anyone can ask (backend/floss.py).

   The rail's Floss chip, and "Ask Floss" on a fault in Errors, open one
   dialog. It walks a machine through what Floss needs the first time
   (Claude Code installed, the lab PIN typed once), then: say what went
   wrong, watch it look, read what it found, and choose. "Use it here"
   applies the fix to this machine's code; "Leave it for review" keeps it
   for the main Claude session to integrate. Either way the ticket is in
   GUI_logs/floss/ and travels with the next commit (docs/floss.md).

   Everything here talks to the local server only: polling while Floss
   works costs no cloud requests. */
BARRY.floss = (function () {
  // His name, wherever the page says it (2026-11-06). Code, routes and files
  // still say floss.
  const NAME = 'Hater of AI';
  let st = null;          // the last /api/floss/status
  let root = null;        // the dialog's node, while it is open
  let showing = null;     // a ticket id, when one is open in the dialog
  let ticket = null;      // that ticket, whole (with its patch)
  let after = null;       // what a use/undo said needs doing next
  let draft = '';
  let context = null;     // {error, view} handed in by whoever opened it
  let pin = '';
  let poll = null;

  const STATUS = {
    working: ['Working', ''],
    ready: ['Fix ready', 'good'],
    held: ['Kept for review', 'warn'],
    nothing: ['No change', ''],
    failed: ['Could not finish', 'warn'],
    stopped: ['Stopped', ''],
    applied: ['In use here', 'good'],
    undone: ['Taken out', ''],
    dismissed: ['Left for review', ''],
  };

  const isOpen = () => !!(root && root.isConnected);

  async function refresh() {
    // Not background: somebody opened the dialog and is waiting on it.
    st = await api('/api/floss/status');
    if (st.run && st.run.running && !showing && st.run.id) showing = st.run.id;
    return st;
  }

  function schedule() {
    clearTimeout(poll);
    const busy = st && st.run && st.run.running;
    if (!isOpen() || !busy) return;
    poll = setTimeout(async () => {
      if (!isOpen()) return;
      const was = st.run.id;
      try { await refresh(); } catch (e) { /* the feed says why */ }
      if (was && !(st.run && st.run.running) && showing === was) await loadTicket(was);
      draw();
    }, 1200);
  }

  async function loadTicket(id) {
    try {
      ticket = (await api('/api/floss/ticket?id=' + encodeURIComponent(id))).ticket;
    } catch (e) { ticket = null; toast(e.message, 'err'); }
  }

  async function post(path, body, okWords) {
    try {
      const res = await apiPost('/api/floss/' + path, body || {});
      st = res;
      if (okWords) toast(okWords, 'ok');
      return res;
    } catch (e) {
      toast(e.message, 'err');
      return null;
    }
  }

  /* ---------- the pieces ---------- */

  function chip(status) {
    const s = STATUS[status] || [status, ''];
    return el('span', { class: 'stat-chip' + (s[1] ? ' ' + s[1] : ''), text: s[0] });
  }

  function engineCard() {
    const installing = st.engine.installing;
    return el('div', { class: 'floss-card' }, [
      el('p', { text: NAME + ' runs on Claude Code, which this machine does not have yet. '
        + 'Installing it takes about a minute and needs the internet. It is done once.' }),
      BARRY.ui.button({ kind: 'primary', size: 'sm',
        text: installing ? 'Installing' : 'Install Claude Code',
        disabled: installing,
        onclick: async () => {
          await post('install');
          draw();
          const wait = setInterval(async () => {
            try { await refresh(); } catch (e) { /* keep waiting */ }
            if (!st.engine.installing) {
              clearInterval(wait);
              if (st.engine.path) toast('Claude Code is installed', 'ok');
              else toast('Claude Code did not install. The Output dock says why.', 'err');
              if (isOpen()) draw();
            }
          }, 2000);
        } }),
    ]);
  }

  function lockCard() {
    const input = el('input', { type: 'password', class: 'floss-pin', placeholder: 'Lab PIN',
      autocomplete: 'off', value: pin,
      oninput: (e) => { pin = e.target.value; } });
    const go = async () => {
      if (!pin.trim()) return;
      const res = await post('unlock', { pin: pin.trim() }, NAME + ' is unlocked on this machine');
      if (res) { pin = ''; draw(); }
    };
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
    setTimeout(() => input.focus(), 30);
    return el('div', { class: 'floss-card' }, [
      el('p', { text: NAME + ' is locked on this machine. Type the lab PIN once to unlock it '
        + '(hint: ' + st.key.hint + '). It uses the lab’s Claude account, never yours.' }),
      el('div', { class: 'coll-row' }, [input,
        BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'Unlock', onclick: go })]),
    ]);
  }

  function askCard() {
    const box = el('textarea', { class: 'floss-ask', rows: 5,
      placeholder: 'What went wrong? What did you click, what did you expect, '
        + 'and what happened instead?' });
    box.value = draft;
    box.addEventListener('input', () => { draft = box.value; });
    setTimeout(() => box.focus(), 30);
    const err = context && context.error;
    const send = async () => {
      if (draft.trim().length < 8) { toast('Say a little more about what went wrong', 'err'); return; }
      const body = { ask: draft, context: { view: (BARRY.state && BARRY.state.view) || null,
                                            error: err || null } };
      const res = await post('ask', body);
      if (!res) return;
      draft = '';
      context = null;
      showing = res.id;
      ticket = null;
      draw();
    };
    return el('div', { class: 'floss-card' }, [
      err ? el('div', { class: 'floss-err' }, [
        el('b', { text: 'About this error: ' }),
        el('span', { text: (err.where ? err.where + ': ' : '') + (err.message || '') }),
      ]) : null,
      box,
      el('p', { class: 'hint', text: NAME + ' also reads this machine’s recent errors. He fixes '
        + 'small things (up to ' + st.limits.files + ' files and ' + st.limits.lines
        + ' lines) in his own copy of the code; you decide whether to use the fix.' }),
      el('div', { class: 'coll-row' }, [el('div', { class: 'spacer' }),
        BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'Ask ' + NAME, onclick: send })]),
    ]);
  }

  function runCard() {
    const r = st.run;
    const secs = Math.max(0, Math.round(Date.now() / 1000 - (r.started || 0)));
    const steps = (r.steps || []).slice(-14);
    return el('div', { class: 'floss-card' }, [
      el('div', { class: 'coll-row' }, [
        el('b', { text: NAME + ' is looking into it' }),
        el('span', { class: 'hint', text: fmtDur(secs) }),
        el('div', { class: 'spacer' }),
        BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Stop',
          onclick: () => post('stop', {}, 'Stopped') }),
      ]),
      el('ol', { class: 'floss-steps' },
        steps.length ? steps.map((s) => el('li', { text: s.text }))
                     : [el('li', { text: 'starting' })]),
    ]);
  }

  function field(label, text) {
    if (!text) return null;
    return el('div', { class: 'floss-field' }, [el('b', { text: label }), el('span', { text })]);
  }

  function ticketCard() {
    const t = ticket;
    if (!t) return loader('Opening the ticket');
    const rep = t.report || {};
    const files = (t.files || []).map((f) => f.path + ' (+' + f.added + ' −' + f.removed + ')');
    const kids = [
      el('div', { class: 'coll-row' }, [chip(t.status),
        el('span', { class: 'hint', text: BARRY.when(t.at, 'minute') + (t.who ? ', ' + t.who : '') })]),
      el('blockquote', { class: 'floss-quote', text: t.ask }),
    ];
    if (t.status === 'failed') kids.push(el('p', { class: 'floss-bad', text: NAME + ' could not finish: ' + (t.error || 'no reason given') }));
    if (rep.words) kids.push(el('p', { class: 'floss-words', text: rep.words }));
    kids.push(field('Cause', rep.cause), field('Fix', rep.fix),
              field('Confidence', rep.confidence), field('Checked', rep.tested));
    if (files.length) kids.push(field('Changes', files.join(', ')));
    if ((t.held_because || []).length) {
      kids.push(el('div', { class: 'floss-held' }, [
        el('b', { text: 'Too big to use here, so it is kept for review:' }),
        el('ul', {}, t.held_because.map((w) => el('li', { text: w }))),
      ]));
    }
    if ((rep.needs || []).length) {
      kids.push(el('div', { class: 'floss-needs' }, [
        el('b', { text: 'Left for review' }),
        el('ul', {}, rep.needs.map((w) => el('li', { text: w }))),
      ]));
    }
    if (t.patch) {
      kids.push(el('details', {}, [el('summary', { text: 'The change, line by line' }),
                                   el('pre', { class: 'floss-diff', text: t.patch })]));
    }
    if (after && (after.restart || after.reload)) {
      const row = el('div', { class: 'floss-after' }, [
        el('span', { text: after.restart
          ? 'The fix is in the server’s code, so it takes effect after a restart.'
          : 'The fix is in the page’s code, so it takes effect after a reload.' })]);
      if (after.restart && BARRY.solid && BARRY.solid.restartControl) row.appendChild(BARRY.solid.restartControl());
      else row.appendChild(BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'Reload',
        onclick: () => location.reload() }));
      kids.push(row);
    }
    if (t.mother) kids.push(field('Reviewed', [t.mother.status, t.mother.note].filter(Boolean).join(': ')));
    return el('div', { class: 'floss-card' }, kids);
  }

  function historyCard() {
    const rows = (st.tickets || []).filter((t) => t.id !== showing).slice(0, 12);
    if (!rows.length) return null;
    return el('div', { class: 'floss-history' }, [
      el('b', { text: 'Asked on this machine' }),
      el('div', {}, rows.map((t) => el('button', { class: 'floss-row', type: 'button',
        onclick: async () => { showing = t.id; after = null; ticket = null; draw(); await loadTicket(t.id); draw(); } }, [
        chip(t.status),
        el('span', { class: 'floss-row-ask', text: t.ask }),
        el('span', { class: 'hint', text: BARRY.when(t.at, 'minute') }),
      ]))),
    ]);
  }

  /* ---------- the pop-up ----------

     A little panel beside the rail chip that opened it, not a modal: the
     app stays usable while he works, and it never covers the corner toasts.
     Closed by its x, Esc, or the chip again. */

  function foot() {
    const left = [], right = [];
    const t = ticket;
    const running = st && st.run && st.run.running && st.run.id === showing;
    if (showing && !running) {
      left.push(BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Ask something else',
        onclick: () => { showing = null; ticket = null; after = null; draw(); } }));
    }
    if (t && !running && t.status === 'ready') {
      right.push(BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Leave it for review',
        onclick: async () => { if (await post('dismiss', { id: t.id }, 'Kept for review')) { await loadTicket(t.id); draw(); } } }));
      right.push(BARRY.ui.button({ kind: 'primary', size: 'sm', text: 'Use it here',
        onclick: async () => {
          const res = await post('use', { id: t.id }, 'The fix is in use on this machine');
          if (res) { after = res.after; await loadTicket(t.id); draw(); }
        } }));
    } else if (t && t.status === 'applied') {
      right.push(BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Take it out',
        onclick: async () => {
          const res = await post('undo', { id: t.id }, 'The fix was taken out');
          if (res) { after = res.after; await loadTicket(t.id); draw(); }
        } }));
    }
    if (!left.length && !right.length) return null;
    return el('div', { class: 'hoa-foot' }, left.concat([el('div', { class: 'spacer' })], right));
  }

  function body() {
    if (!st) return [loader('Asking ' + NAME + ' how he is')];
    if (!st.engine.path) return [engineCard()];
    if (!st.key.here) return [lockCard()];
    const running = st.run.running && st.run.id;
    if (showing) return [running && st.run.id === showing ? runCard() : ticketCard(), historyCard()];
    if (running) return [runCard()];
    return [askCard(), historyCard()];
  }

  /* Beside the rail, its foot level with the chip's, and never off screen. */
  function place() {
    const rail = document.getElementById('rail');
    const r = rail ? rail.getBoundingClientRect() : { right: 0 };
    const b = btn ? btn.getBoundingClientRect() : null;
    const gap = 12;
    const bottom = b && b.height ? Math.max(gap, window.innerHeight - b.bottom) : gap + 40;
    root.style.left = Math.max(gap, Math.round(r.right + gap)) + 'px';
    root.style.bottom = Math.round(bottom) + 'px';
    root.style.maxHeight = Math.max(240, window.innerHeight - bottom - gap) + 'px';
  }

  function close() {
    clearTimeout(poll);
    if (root) root.remove();
    root = null;
    if (btn) btn.classList.remove('on');
  }

  function draw() {
    if (!isOpen()) {
      root = el('div', { class: 'hoa-pop', role: 'dialog', 'aria-label': NAME });
      document.body.appendChild(root);
      if (btn) btn.classList.add('on');
    }
    root.replaceChildren(
      el('div', { class: 'hoa-head' }, [
        el('b', { text: NAME }),
        el('span', { class: 'hint', text: 'fixes small bugs, leaves the rest for review' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', title: 'Close', onclick: close,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'hoa-body' }, body().filter(Boolean)),
      foot() || '');
    place();
    schedule();
  }

  /* `o.error`: an error record to ask about (Errors view). */
  async function open(o) {
    context = o && o.error ? { error: o.error } : null;
    if (context) { showing = null; ticket = null; }
    after = null;
    draw();
    try { await refresh(); } catch (e) { toast(e.message, 'err'); close(); return; }
    if (showing && !ticket && !(st.run.running && st.run.id === showing)) await loadTicket(showing);
    if (isOpen()) draw();
  }

  // Wired as it loads: the chip is already in the page above this script.
  const btn = document.getElementById('flossBtn');
  if (btn) btn.addEventListener('click', () => (isOpen() && !context ? close() : open()));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isOpen() && !isTyping(e)) close();
  });
  window.addEventListener('resize', () => { if (isOpen()) place(); });

  return { open };
})();
