/* ==========================================================================
   figrebuild.js -- Rebuilding a figure that already exists.

   A PNG in Results/ is the end of a trail that started somewhere in a 20
   minute recording. "Which seconds was that, and what was filtered out?" is
   the question, and the honest answer is on the run record -- so this reads
   the record, checks every part of it against the disk as it is today, shows
   the plan including the parts that will not work, and then performs it.

   Two deliberate choices:

   Warn first, work second. The whole plan is audited on the server before
   anything is opened, so a missing drive is a sentence in the dialog rather
   than a failure four steps in.

   Show the motions. Each step lights up as it runs and says what it did --
   which folder was opened, which window was set, how many channels came
   back. Not every mouse movement, but every step that changed something,
   because a rebuild you cannot watch is a rebuild you have to take on faith.
   ========================================================================== */
'use strict';

BARRY.figrebuild = (function () {
  // Long enough to read a line, short enough not to be waiting on it. Real
  // work (opening a recording) takes longer than this on its own.
  const BEAT = 260;

  let plan = null;      // the audit from the server
  let running = false;
  let sess = null;      // the session, once opened

  const pause = (ms) => new Promise((r) => setTimeout(r, ms));

  /* ==================================================================
     Entry point
     ================================================================== */
  async function start(runId) {
    if (running) { toast('A rebuild is already running.', null, 3000); return; }
    plan = null;
    sess = null;
    try {
      plan = await api('/api/figure/recipe/' + encodeURIComponent(runId));
    } catch (e) {
      toast('Could not read the recipe: ' + e.message, 'err', 8000);
      return;
    }
    BARRY.activity.log('figure.rebuild.plan', {
      run: runId, verdict: plan.verdict, complete: plan.complete,
      problems: (plan.problems || []).length,
    });
    render();
  }

  /* ==================================================================
     The dialog
     ================================================================== */
  function render() {
    const run = plan.run || {};
    const blocked = plan.verdict === 'missing';
    const label = plan.verdict === 'ok' ? 'Rebuild it'
      : blocked ? 'Rebuild what is possible' : 'Rebuild anyway';

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Rebuild this figure' }),
        el('span', { class: 'sub', text: (run.label || 'figure')
          + (run.provenance ? ' · ' + niceDate(run.provenance.at) : '') }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [
        header(run),
        problemBlock(),
        el('div', { class: 'rb-steps', id: 'rbSteps' },
           (plan.steps || []).map((s, i) => stepRow(s, i))),
        el('div', { class: 'rb-live hidden', id: 'rbLive' }),
      ]),
      el('div', { class: 'mf' }, [
        el('span', { class: 'hint', id: 'rbHint', text: hintFor() }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Close', onclick: closeModal }),
        el('button', {
          class: 'btn' + (blocked ? ' ghost' : ' primary'),
          id: 'rbGo', text: label,
          onclick: () => run_(),
        }),
      ]),
    ]));
  }

  function header(run) {
    const r = plan.recipe || {};
    const out = run.output || {};
    const bits = [
      ['Recording', (r.identity || {}).label || r.session_label || '—'],
      ['Made', run.provenance ? niceDate(run.provenance.at) : '—'],
      ['By', (run.provenance || {}).user || '—'],
      ['Format', (run.format || '').toUpperCase() || '—'],
    ];
    return el('div', { class: 'rb-head' }, [
      el('div', { class: 'rb-facts' }, bits.map(([k, v]) =>
        el('div', { class: 'rb-fact' }, [
          el('span', { class: 'k', text: k }),
          el('span', { class: 'v', text: String(v), title: String(v) }),
        ]))),
      out.rel ? el('button', {
        class: 'btn ghost sm', text: 'Show the original',
        title: out.rel,
        onclick: () => {
          closeModal();
          setView('results');
          if (BARRY.views.results && BARRY.views.results.search) {
            BARRY.views.results.search(baseName(out.rel));
          }
        },
      }) : null,
    ].filter(Boolean));
  }

  function problemBlock() {
    const probs = plan.problems || [];
    if (!probs.length) {
      return el('div', { class: 'rb-verdict ok' }, [
        el('span', { class: 'rb-dot ok' }),
        el('span', { text: 'Everything this figure needs is on this machine. '
                     + 'It can be rebuilt exactly.' }),
      ]);
    }
    return el('div', { class: 'rb-verdict ' + plan.verdict }, [
      el('div', { class: 'rb-verdict-top' }, [
        el('span', { class: 'rb-dot ' + plan.verdict }),
        el('strong', { text: plan.verdict === 'missing'
          ? 'Something it needs is not here'
          : 'It can be rebuilt, with differences' }),
      ]),
      el('ul', { class: 'rb-probs' },
         probs.map((p) => el('li', { text: p }))),
    ]);
  }

  function hintFor() {
    if (plan.verdict === 'ok') return 'Every step below checked out.';
    if (plan.verdict === 'missing') {
      return 'The steps marked in red will be skipped.';
    }
    return 'The steps marked in amber will differ from the original.';
  }

  function stepRow(s, i) {
    return el('div', { class: 'rb-step', id: 'rbStep' + i,
                       'data-state': 'planned' }, [
      el('div', { class: 'rb-mark' }, [
        el('span', { class: 'rb-n', text: String(i + 1) }),
        el('span', { class: 'rb-dot ' + s.status }),
      ]),
      el('div', { class: 'rb-body' }, [
        el('div', { class: 'rb-title' }, [
          el('span', { text: s.title }),
          el('span', { class: 'rb-state', text: '' }),
        ]),
        el('div', { class: 'rb-what', text: String(s.what), title: String(s.what) }),
        s.note ? el('div', { class: 'rb-note ' + s.status, text: s.note }) : null,
        el('div', { class: 'rb-did hidden' }),
      ].filter(Boolean)),
    ]);
  }

  /* ==================================================================
     Performing it
     ================================================================== */
  function mark(i, state, did) {
    const node = $('#rbStep' + i);
    if (!node) return;
    node.dataset.state = state;
    const st = node.querySelector('.rb-state');
    if (st) {
      st.textContent = { running: 'working…', done: 'done',
                         skipped: 'skipped', failed: 'failed' }[state] || '';
    }
    if (did) {
      const d = node.querySelector('.rb-did');
      d.classList.remove('hidden');
      d.textContent = did;
    }
    if (state === 'running') node.scrollIntoView({ block: 'nearest' });
  }

  function say(msg) {
    const live = $('#rbLive');
    if (!live) return;
    live.classList.remove('hidden');
    live.textContent = msg;
  }

  async function run_() {
    if (running) return;
    running = true;
    const go = $('#rbGo');
    if (go) { go.disabled = true; go.textContent = 'Rebuilding…'; }

    const steps = plan.steps || [];
    const r = plan.recipe || {};
    let ok = true;

    BARRY.activity.log('figure.rebuild.start', {
      run: (plan.run || {}).id, verdict: plan.verdict,
    });

    // The last step opens the builder, which replaces this dialog. Running it
    // automatically would erase the account of what just happened at the
    // moment it became worth reading, so it waits for a click.
    const handoff = steps.length - 1;

    try {
      for (let i = 0; i < handoff; i++) {
        const s = steps[i];
        if (s.status === 'missing') {
          mark(i, 'skipped', s.note || 'Not available on this machine.');
          ok = false;
          await pause(BEAT / 2);
          continue;
        }
        mark(i, 'running');
        say(s.title + '…');
        await pause(BEAT);
        let did = null;
        try {
          did = await perform(s, r);
        } catch (e) {
          mark(i, 'failed', e.message);
          say('Stopped at "' + s.title + '": ' + e.message);
          BARRY.activity.log('figure.rebuild.failed',
                             { step: s.id, error: e.message });
          running = false;
          if (go) { go.disabled = false; go.textContent = 'Try again'; }
          return;
        }
        mark(i, 'done', did);
        await pause(BEAT / 2);
      }
    } finally {
      running = false;
    }

    say(ok ? 'The recording is back the way the figure left it. '
             + 'Open the builder to draw it again.'
           : 'Restored as far as this machine allows — the skipped steps are '
             + 'marked above.');
    BARRY.activity.log('figure.rebuild.done',
                       { run: (plan.run || {}).id, exact: ok });

    // The node is replaced rather than relabeled: el() binds handlers with
    // addEventListener, so the old "Rebuild" click would still be attached
    // alongside the new one.
    if (go) {
      go.replaceWith(el('button', {
        class: 'btn primary', id: 'rbGo',
        text: 'Open the figure builder →',
        onclick: () => finish(handoff),
      }));
    }
    const hint = $('#rbHint');
    if (hint) {
      hint.textContent = ok
        ? 'Restored exactly. Everything above is now on screen in '
          + 'Xplorefinder.'
        : 'Restored with the differences noted above.';
    }
  }

  /* The handoff. Marked done before the builder replaces this dialog, so the
     step is recorded even though nobody gets to see the tick. */
  async function finish(i) {
    const s = (plan.steps || [])[i];
    if (!s) return;
    mark(i, 'running');
    try {
      const did = await perform(s, plan.recipe || {});
      mark(i, 'done', did);
    } catch (e) {
      mark(i, 'failed', e.message);
      say('Could not open the builder: ' + e.message);
      BARRY.activity.log('figure.rebuild.failed',
                         { step: s.id, error: e.message });
    }
  }

  /* Each step, for real. Returns a line saying what it actually did, which is
     the part worth watching -- "32 channels, 30000 Hz" is evidence; "done" is
     not. */
  async function perform(s, r) {
    switch (s.id) {
      case 'locate':
        return s.moved ? 'Using ' + s.path + ' instead of the original.'
                       : 'Found at ' + s.path;

      case 'open': {
        setView('xplore');
        const locate = (plan.steps || []).find((x) => x.id === 'locate') || {};
        sess = await BARRY.views.xplore.open(locate.path, {
          evenOnly: s.even_only !== false,
          invert: s.invert !== false,
        });
        if (!sess) throw new Error('The recording would not open.');
        return 'Opened ' + (sess.identity.label || sess.info.name) + ' — '
             + sess.info.channels.length + ' channels at '
             + sess.info.fs + ' Hz.';
      }

      case 'window': {
        need();
        const dur = sess.info.duration_s || 0;
        const t0 = Math.max(0, Math.min(s.t0, Math.max(0, dur - 0.05)));
        const t1 = dur ? Math.min(s.t1, dur) : s.t1;
        sess.t0 = t0;
        sess.span = Math.max(0.05, t1 - t0);
        const clipped = Math.abs(t1 - s.t1) > 0.01;
        return 'Window set to ' + clock(t0) + '–' + clock(t0 + sess.span)
             + (clipped ? ' (clipped to the end of the recording).' : '.');
      }

      case 'filters': {
        need();
        sess.hp = s.highpass || 0;
        sess.lp = s.lowpass || 0;
        sess.notch = s.notch || 0;
        if (s.gain) sess.gain = s.gain;
        return 'Filters set: ' + String(s.what) + '.';
      }

      case 'channels': {
        need();
        const all = sess.info.channels;
        if (Array.isArray(s.channels) && s.channels.length) {
          const keep = s.channels.filter((i) => i >= 0 && i < all.length);
          sess.sel = new Set(keep);
          const lost = s.channels.length - keep.length;
          var line = keep.length + ' of ' + all.length + ' channels selected'
            + (lost ? ', ' + lost + ' no longer present' : '');
        } else {
          sess.sel = new Set(all.map((c) => c.index));
          line = 'no selection was recorded, so all ' + all.length
               + ' channels are on';
        }
        const bad = (s.bad_channels || []).map(Number);
        if (bad.length) {
          sess.bad = new Set(bad);
          line += '; CSC ' + bad.join(', ') + ' marked bad';
        }
        return line.charAt(0).toUpperCase() + line.slice(1) + '.';
      }

      case 'events': {
        need();
        const evs = (plan.recipe || {}).events || [];
        sess.events = evs;
        sess.eventsMeta = { source: 'figure rebuild',
                            name: (plan.run || {}).label || 'figure',
                            n: evs.length };
        BARRY.views.xplore.refreshAll();
        return evs.length + ' mark' + (evs.length === 1 ? '' : 's')
             + ' put back on the trace.';
      }

      case 'panels': {
        need();
        const XF = BARRY.views.xplore.state;
        const panels = s.panels || [];
        // The pane grid shows what the figure showed, so the rebuild is
        // visible in Xplorefinder itself and not only in the builder.
        const want = Math.max(1, Math.min(4, panels.length));
        XF.nPanes = want;
        XF.panes = panels.slice(0, want).map((p) => ({
          sessionId: sess.id,
          panel: p.panel || 'traces',
          cmap: p.cmap || (plan.recipe || {}).cmap || 'jet',
          channel: p.channel,
          fmin: p.fmin, fmax: p.fmax,
        }));
        BARRY.views.xplore.onShow();
        await pause(BEAT);
        return panels.map((p) => p.title || p.panel).join(', ')
             + ' laid out ' + ((plan.recipe || {}).rows || 1) + '×'
             + ((plan.recipe || {}).cols || 1) + '.';
      }

      case 'builder': {
        need();
        // reopen() calls showModal, which replaces this dialog's contents --
        // so there is nothing to close first.
        await BARRY.figure.reopen(BARRY.views.xplore.state, sess,
                                  plan.recipe, plan);
        return 'Builder open.';
      }

      default:
        return null;
    }
  }

  function need() {
    if (!sess) throw new Error('The recording is not open, so this step '
                               + 'cannot run.');
  }

  /* ==================================================================
     small helpers
     ================================================================== */
  function clock(t) {
    const m = Math.floor(t / 60);
    const s = t - m * 60;
    return m + ':' + (s < 10 ? '0' : '') + s.toFixed(2);
  }

  function niceDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString();
  }

  /* A button for anywhere a figure result is listed. */
  function button(run, extraClass) {
    if (!run || run.kind !== 'figure') return null;
    return el('button', {
      class: 'btn ghost sm' + (extraClass ? ' ' + extraClass : ''),
      text: 'Rebuild…',
      title: 'Check what this figure needs, then walk through remaking it',
      onclick: (e) => { e.stopPropagation(); start(run.id); },
    });
  }

  return { start, button };
})();
