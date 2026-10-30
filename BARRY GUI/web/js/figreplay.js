/* ==========================================================================
   figreplay.js -- The walk-through: put a figure back on screen, and prove it.

   A figure in Results is the end of a trail that began somewhere in a long
   recording. The walk-through follows the trail back: it opens the
   recording, sets each panel's tool up the way the panel was grabbed, and
   then READS BACK what is actually on screen and compares it with the
   figure's record, field by field. It ends with the original and a fresh
   drawing of what is on screen side by side, and says in plain words what
   moved. Keeping the redraw as the figure's next version is a choice, never
   automatic -- a figure is frozen once it is exported.

   The old walk-through (figrebuild.js, retired 2026-10-22) set each thing
   and then waited a fixed 2.2 s and checked again, because late writes --
   an event import in flight, the recording reopening -- kept undoing it. It
   was patched three times for that and could still report success over a
   screen that did not match. Reading back what the screen shows after the
   tool says it has finished drawing is what makes a late write a reported
   difference instead of a silent one.

   Each tool registers how its panels are put back:

     BARRY.figreplay.register(tool, {
       open(layout)             the recording, opened; returns a line
       setup(panel, layout)     the tool showing this panel; returns a line
       ready(panel)             resolves when the tool has finished drawing
       readback(panel, layout)  the panel's params as the screen has them
       arrange(panels, layout)  optional: the whole figure on screen at the end
     })

   Xplorefinder's is below.
   ========================================================================== */
'use strict';

BARRY.figreplay = (function () {
  const performers = {};
  let plan = null;
  let running = false;
  let redraw = null;          // the layout as read back
  let moved = [];             // what differs, in words

  const pause = (ms) => new Promise((r) => setTimeout(r, ms));

  function register(tool, def) { performers[tool] = def; }

  /* ==================================================================
     Entry points
     ================================================================== */
  async function start(fid, v) {
    if (running) { toast('A walk-through is already running.', null, 3000); return; }
    plan = null; redraw = null; moved = [];
    try {
      plan = await api('/api/figures/' + encodeURIComponent(fid) + '/v/' + v + '/plan');
    } catch (e) {
      toast('Could not read what this figure needs: ' + e.message, 'err', 8000);
      return;
    }
    plan.fid = fid;
    plan.v = v;
    BARRY.activity.log('figure.walk.plan', { figure: fid, v, verdict: plan.verdict });
    render();
  }

  /* From a file in Results: which figure version it is, then the plan. */
  async function startRun(runId) {
    let got;
    try {
      got = await api('/api/figures/for-run/' + encodeURIComponent(runId));
    } catch (e) {
      toast(e.message, null, 8000);
      return;
    }
    return start(got.figure_id, got.v || 1);
  }

  /* ==================================================================
     The dialog
     ================================================================== */
  function render() {
    const ver = plan.version || {};
    const lay = ver.layout || {};
    const blocked = plan.verdict === 'missing';
    showModal(el('div', { class: 'fr' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Walk through this figure' }),
        el('span', { class: 'sub', text: (lay.title || 'figure') + ' · v'
          + plan.v + (ver.at ? ' · ' + niceDate(ver.at) : '') }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', type: 'button', title: 'Close',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: close }),
      ]),
      el('div', { class: 'mb' }, [
        el('p', { class: 'hint', text: 'Each step puts part of the figure back '
          + 'on screen and says what it did. At the end, what is on screen is '
          + 'read back and drawn beside the original.' }),
        verdictBlock(),
        el('div', { class: 'rb-steps', id: 'frSteps' },
           (plan.steps || []).map((s, i) => stepRow(s, i))),
        el('div', { class: 'rb-live hidden', id: 'frLive' }),
        el('div', { class: 'fr-compare hidden', id: 'frCompare' }),
      ]),
      el('div', { class: 'mf' }, [
        el('span', { class: 'hint', id: 'frHint', text: hintFor() }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost sm hidden', id: 'frGrow', type: 'button',
          text: 'Bring it back to the middle', onclick: () => dock(false) }),
        el('button', { class: 'btn ghost', type: 'button', text: 'Close',
                       onclick: close }),
        el('button', { class: 'btn' + (blocked ? ' ghost' : ' primary'),
          id: 'frGo', type: 'button',
          text: blocked ? 'Walk through what is possible'
            : plan.verdict === 'warn' ? 'Walk through it anyway' : 'Walk through it',
          onclick: go }),
      ]),
    ]));
  }

  function close() { dock(false); closeModal(); }

  function verdictBlock() {
    const probs = plan.problems || [];
    if (!probs.length) {
      return el('div', { class: 'rb-verdict ok' }, [
        el('span', { class: 'rb-dot ok' }),
        el('span', { text: 'Everything this figure needs is on this machine.' }),
      ]);
    }
    return el('div', { class: 'rb-verdict ' + plan.verdict }, [
      el('div', { class: 'rb-verdict-top' }, [
        el('span', { class: 'rb-dot ' + plan.verdict }),
        el('strong', { text: plan.verdict === 'missing'
          ? 'Something it needs is not here'
          : 'It can be walked through, with differences' }),
      ]),
      el('ul', { class: 'rb-probs' }, probs.map((p) => el('li', { text: p }))),
    ]);
  }

  function hintFor() {
    if (plan.verdict === 'ok') return 'Every step below checked out.';
    if (plan.verdict === 'missing') return 'The steps marked in red will be skipped.';
    return 'The steps marked in amber will differ from the original.';
  }

  function stepRow(s, i) {
    return el('div', { class: 'rb-step', id: 'frStep' + i, 'data-state': 'planned' }, [
      el('div', { class: 'rb-mark' }, [
        el('span', { class: 'rb-n', text: String(i + 1) }),
        el('span', { class: 'rb-dot ' + s.status }),
      ]),
      el('div', { class: 'rb-body' }, [
        el('div', { class: 'rb-title' }, [
          el('span', { text: s.title }),
          el('span', { class: 'rb-state', text: '' }),
        ]),
        el('div', { class: 'rb-what', text: String(s.what || '') }),
        s.note ? el('div', { class: 'rb-note ' + s.status, text: s.note }) : null,
        el('div', { class: 'rb-did hidden' }),
      ].filter(Boolean)),
    ]);
  }

  function mark(i, state, did) {
    const node = $('#frStep' + i);
    if (!node) return;
    node.dataset.state = state;
    const st = node.querySelector('.rb-state');
    if (st) {
      st.textContent = { running: 'working…', done: 'done', skipped: 'skipped',
                         failed: 'failed' }[state] || '';
    }
    if (did) {
      const d = node.querySelector('.rb-did');
      d.classList.remove('hidden');
      d.textContent = did;
    }
    if (state === 'running') node.scrollIntoView({ block: 'nearest' });
  }

  function say(msg) {
    const live = $('#frLive');
    if (!live) return;
    live.classList.remove('hidden');
    live.textContent = msg;
  }

  /* Out of the way while it works: the point is to watch the screen. */
  function dock(on) {
    const shell = document.getElementById('bigModal');
    if (shell) shell.classList.toggle('docked', !!on);
    const box = document.getElementById('bigModalBox');
    if (box) box.classList.toggle('docked', !!on);
    const g = $('#frGrow');
    if (g) g.classList.toggle('hidden', !on);
    window.dispatchEvent(new Event('resize'));
  }

  /* ==================================================================
     Performing it
     ================================================================== */
  async function go() {
    if (running) return;
    running = true;
    const btn = $('#frGo');
    if (btn) { btn.disabled = true; btn.textContent = 'Walking through…'; }
    dock(true);
    const steps = plan.steps || [];
    const lay = JSON.parse(JSON.stringify((plan.version || {}).layout || {}));
    const back = JSON.parse(JSON.stringify(lay));
    const byUid = (uid) => lay.panels.find((p) => p.uid === uid);
    moved = [];
    // A figure with nothing that reads the recording itself (Root Canal's
    // panels are of a banked set) has no open step; each panel opens its tool.
    let opened = !steps.some((s) => s.id === 'open');
    BARRY.activity.log('figure.walk.start', { figure: plan.fid, v: plan.v });
    try {
      for (let i = 0; i < steps.length; i++) {
        const s = steps[i];
        if (s.status === 'missing') {
          mark(i, 'skipped', s.note || 'Not available on this machine.');
          await pause(120);
          continue;
        }
        mark(i, 'running');
        say(s.title + '…');
        try {
          let did = null;
          if (s.id === 'locate') {
            if (s.moved) lay.recording.path = s.path;
            did = s.moved ? 'Using ' + s.path + ' instead of the original.'
                          : 'Found at ' + s.path + '.';
          } else if (s.id === 'open') {
            const perf = performers[firstTool(lay)];
            did = perf ? await perf.open(lay) : 'Nothing to open it with.';
            opened = true;
          } else if (s.id === 'panel') {
            const p = byUid(s.uid);
            const perf = performers[s.tool];
            if (!p || !perf || !opened) {
              mark(i, 'skipped', 'Nothing to put this panel on.');
              continue;
            }
            const set = await perf.setup(p, lay);
            const settled = await perf.ready(p, lay);
            const got = await perf.readback(p, lay);
            const bp = back.panels.find((x) => x.uid === p.uid);
            if (got && bp) bp.params = got;
            const diff = !got ? ['nothing could be read back']
              : (perf.differences ? perf.differences(p.params || {}, got)
                                  : differences(p.params || {}, got));
            diff.forEach((d) => moved.push(letterOf(p) + ': ' + d));
            did = (set || 'Set up.') + (settled ? '' : ' (It was still drawing when '
              + 'it was read back.)') + (diff.length ? ' Differs: ' + diff.join('; ') + '.'
                                         : ' Reads back exactly as recorded.');
          } else if (s.id === 'readback') {
            const perfs = Array.from(new Set(lay.panels.map((p) => p.tool)))
              .map((t) => performers[t]).filter(Boolean);
            for (const perf of perfs) {
              if (perf.arrange) await perf.arrange(lay.panels.filter((p) => performers[p.tool] === perf), lay);
            }
            did = moved.length ? moved.length + ' difference'
              + (moved.length === 1 ? '' : 's') + ' from the record.'
              : 'Every panel reads back as the figure recorded it.';
          } else if (s.id === 'compare') {
            await compare(back);
            did = 'Drawn beside the original.';
          }
          mark(i, 'done', did);
        } catch (e) {
          mark(i, 'failed', e.message);
          say('Stopped at "' + s.title + '": ' + e.message);
          BARRY.activity.log('figure.walk.failed', { figure: plan.fid, step: s.id,
                                                    error: e.message });
          if (btn) { btn.disabled = false; btn.textContent = 'Try again'; }
          return;
        }
        await pause(120);
      }
    } finally {
      running = false;
    }
    redraw = back;
    dock(false);
    say(moved.length ? 'On screen, with the differences listed. Keep it as a '
                       + 'new version only if that is what you want.'
                     : 'On screen exactly as the figure recorded it.');
    BARRY.activity.log('figure.walk.done', { figure: plan.fid, v: plan.v,
                                            moved: moved.length });
    const hint = $('#frHint');
    if (hint) hint.textContent = moved.length
      ? 'v' + plan.v + ' is unchanged. The redraw is kept only if you keep it.'
      : 'v' + plan.v + ' and the screen agree.';
    if (btn) {
      btn.replaceWith(el('button', {
        class: 'btn primary', id: 'frGo', type: 'button',
        text: 'Keep the redraw as the next version',
        title: 'Export what is on screen as this figure’s next version. '
          + 'v' + plan.v + ' stays as it is.',
        onclick: keep,
      }));
    }
  }

  function firstTool(lay) {
    return ((lay.panels || [])[0] || {}).tool || 'xplore';
  }

  function letterOf(p) {
    const order = plan.version.layout.panels.slice().sort((a, b) =>
      (a.row - b.row) || (a.col - b.col));
    const i = order.findIndex((x) => x.uid === p.uid);
    const lower = (plan.version.layout.profile || 'nature') === 'nature';
    const s = String.fromCharCode(97 + Math.max(0, i));
    return 'panel ' + (lower ? s : s.toUpperCase());
  }

  /* The original beside a fresh drawing of what is on screen. */
  async function compare(lay) {
    const host = $('#frCompare');
    if (!host) return;
    host.classList.remove('hidden');
    host.innerHTML = '';
    const orig = '/api/figures/' + encodeURIComponent(plan.fid) + '/v/' + plan.v
      + '/file/png';
    let now = null;
    try {
      now = (await apiPost('/api/figkit/page', { layout: lay, dpi: 110 })).image;
    } catch (e) {
      now = null;
      host.appendChild(el('p', { class: 'hint warn-line',
        text: 'The redraw failed: ' + e.message }));
    }
    host.appendChild(el('div', { class: 'fr-pair' }, [
      el('figure', {}, [el('img', { src: orig, alt: 'the original' }),
                        el('figcaption', { text: 'v' + plan.v + ', as exported' })]),
      el('figure', {}, [now ? el('img', { src: now, alt: 'the redraw' })
                            : el('div', { class: 'fr-none', text: 'no redraw' }),
                        el('figcaption', { text: 'What is on screen now' })]),
    ]));
    host.appendChild(moved.length
      ? el('div', { class: 'rb-verdict warn' }, [
          el('strong', { text: 'What moved' }),
          el('ul', { class: 'rb-probs' }, moved.map((m) => el('li', { text: m }))),
        ])
      : el('div', { class: 'rb-verdict ok' }, [
          el('span', { class: 'rb-dot ok' }),
          el('span', { text: 'Nothing moved: the screen matches the record.' }),
        ]));
  }

  async function keep() {
    if (!redraw) return;
    const btn = $('#frGo');
    if (btn) { btn.disabled = true; btn.textContent = 'Keeping it…'; }
    try {
      const res = await apiPost('/api/figkit/export', {
        layout: Object.assign({}, redraw, { id: plan.fid }),
        figure_id: plan.fid, from_v: plan.v, source: 'walk-through',
        note: 'Walked through from v' + plan.v
          + (moved.length ? '; ' + moved.length + ' difference(s)' : ''),
      });
      toast('Kept as v' + res.version.v + '. v' + plan.v + ' is unchanged.', 'ok', 6000);
      if (btn) btn.textContent = 'Kept as v' + res.version.v;
      if (BARRY.refreshSync) BARRY.refreshSync();
    } catch (e) {
      toast('Could not keep it: ' + e.message, 'err', 8000);
      if (btn) { btn.disabled = false; btn.textContent = 'Keep the redraw as the next version'; }
    }
  }

  /* ==================================================================
     What moved, in plain words
     ================================================================== */
  const near = (a, b) => Math.abs((+a || 0) - (+b || 0)) < 0.005;
  const sameSet = (a, b) => {
    const x = (a || []).map(Number).sort((m, n) => m - n).join(',');
    const y = (b || []).map(Number).sort((m, n) => m - n).join(',');
    return x === y;
  };
  function differences(want, got) {
    const out = [];
    const sec = (v) => (v == null ? '?' : (+v).toFixed(3));
    if (!near(want.t0, got.t0) || !near(want.t1, got.t1)) {
      out.push('the window is ' + sec(got.t0) + '–' + sec(got.t1) + ' s, not '
               + sec(want.t0) + '–' + sec(want.t1) + ' s');
    }
    for (const [k, name] of [['highpass', 'high-pass'], ['lowpass', 'low-pass'],
                             ['notch', 'notch']]) {
      if (!near(want[k], got[k])) {
        out.push('the ' + name + ' is ' + (+got[k] || 0) + ' Hz, not ' + (+want[k] || 0) + ' Hz');
      }
    }
    if (want.channels && !sameSet(want.channels, got.channels)) {
      out.push((got.channels || []).length + ' channels are drawn, not '
               + want.channels.length);
    }
    if (!sameSet(want.bad_channels, got.bad_channels)) {
      out.push('the bad channels are ' + ((got.bad_channels || []).join(', ') || 'none')
               + ', not ' + ((want.bad_channels || []).join(', ') || 'none'));
    }
    if (want.tf_channels && !sameSet(want.tf_channels, got.tf_channels)) {
      out.push('the map is of different channels');
    }
    if (want.tf_mode && got.tf_mode && want.tf_mode !== got.tf_mode) {
      out.push('the channels are ' + got.tf_mode + 'ed, not ' + want.tf_mode + 'ed');
    }
    if (want.fmin != null && (!near(want.fmin, got.fmin) || !near(want.fmax, got.fmax))) {
      out.push('the band is ' + got.fmin + '–' + got.fmax + ' Hz, not '
               + want.fmin + '–' + want.fmax + ' Hz');
    }
    if (want.cmap && got.cmap && want.cmap !== got.cmap) {
      out.push('the colours are ' + got.cmap + ', not ' + want.cmap);
    }
    if ((want.gain || 1) !== (got.gain || 1)) {
      out.push('the gain is ×' + (got.gain || 1) + ', not ×' + (want.gain || 1));
    }
    const ne = (want.events || []).length, ng = (got.events || []).length;
    if (ne !== ng) out.push(ng + ' marks are on the trace, not ' + ne);
    return out;
  }

  /* ==================================================================
     Xplorefinder: open, set up one panel, wait, read back
     ================================================================== */
  const XV = () => BARRY.views.xplore;
  const XS = () => XV().state;

  function liveSession(lay) {
    const XF = XS();
    const path = (lay.recording || {}).path;
    return Object.values(XF.sessions || {}).find((s) => s.path === path) || null;
  }

  function paneFor(p) {
    const q = p.params || {};
    const pane = { panel: p.plot || 'traces', cmap: q.cmap || 'jet' };
    if (q.clim) pane.climBy = { [pane.panel]: q.clim };
    if (q.ylim != null) pane.ylim = q.ylim;
    if (q.tf_channels) pane.tfChannels = q.tf_channels.slice();
    if (q.tf_mode) pane.tfMode = q.tf_mode;
    if (q.channel != null) pane.channel = q.channel;
    if (q.fmin != null) pane.fmin = q.fmin;
    if (q.fmax != null) pane.fmax = q.fmax;
    return pane;
  }

  function applySession(sess, p) {
    const q = p.params || {};
    if (q.t0 != null && q.t1 != null) {
      sess.t0 = +q.t0;
      sess.span = Math.max(0.05, q.t1 - q.t0);
    }
    if (!(p.plot === 'theta')) {
      sess.hp = q.highpass || 0; sess.lp = q.lowpass || 0; sess.notch = q.notch || 0;
    }
    if (Array.isArray(q.channels) && q.channels.length) sess.sel = new Set(q.channels.map(Number));
    if (Array.isArray(q.bad_channels)) sess.bad = new Set(q.bad_channels.map(Number));
    sess.gain = q.gain || 1;
    if ((p.plot === 'spectrogram' || p.plot === 'scalogram') && q.fmin != null) {
      sess.fdefault = Object.assign({}, sess.fdefault, {
        fmin: q.fmin, fmax: q.fmax, fviewMin: q.fview_min, fviewMax: q.fview_max });
    }
    sess.events = (q.events || []).map((e) => Object.assign({}, e));
    sess.eventsMeta = { source: 'figure walk-through',
                        name: q.events_source || 'the figure', n: sess.events.length };
  }

  register('xplore', {
    async open(lay) {
      setView('xplore');
      let sess = liveSession(lay);
      if (!sess) {
        sess = await XV().open(lay.recording.path,
                               { invert: lay.recording.invert !== false });
      }
      if (!sess) throw new Error('The recording would not open.');
      return 'Opened ' + ((sess.identity || {}).label || (sess.info || {}).name)
        + ' — ' + ((sess.info || {}).channels || []).length + ' channels.';
    },
    async setup(p, lay) {
      const sess = liveSession(lay);
      if (!sess) throw new Error('The recording is not open any more.');
      XS().active = sess.id;
      applySession(sess, p);
      XV().setPanes([Object.assign({ sessionId: sess.id }, paneFor(p))]);
      return 'Xplorefinder shows ' + (p.plot || 'traces') + ', '
        + (+p.params.t0).toFixed(3) + '–' + (+p.params.t1).toFixed(3) + ' s.';
    },
    /* Finished drawing: nothing loading, and two reads of the pane a
       moment apart that agree. Not a fixed wait -- a late write shows up
       as the second read disagreeing, and is waited out or reported. */
    async ready() {
      let last = null;
      for (let i = 0; i < 80; i++) {
        await pause(150);
        const pane = (XS().panes || [])[0];
        const loading = pane && pane._loading && !pane._loading.classList.contains('hidden');
        const now = JSON.stringify(BARRY.figure.paramsOf ? BARRY.figure.paramsOf(0) : null);
        if (!loading && now === last && i > 2) return true;
        last = now;
      }
      return false;
    },
    async readback() {
      return BARRY.figure.paramsOf ? BARRY.figure.paramsOf(0) : null;
    },
    /* The whole figure on screen at the end, in the first panel's seconds. */
    async arrange(panels, lay) {
      const sess = liveSession(lay);
      if (!sess || !panels.length) return;
      applySession(sess, panels[0]);
      XV().setPanes(panels.slice(0, 12).map((p) => Object.assign(
        { sessionId: sess.id }, paneFor(p))));
    },
  });

  /* ==================================================================
     helpers
     ================================================================== */
  function niceDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString();
  }

  return { register, start, startRun, dock, sameSet, near };
})();

/* The name the rest of the app has called it by since 2026-09. Results, the
   run log and the command palette all ask for `BARRY.figrebuild.start(runId)`
   with a run id; it now finds the figure version that run is and walks it. */
BARRY.figrebuild = {
  start: (runId) => BARRY.figreplay.startRun(runId),
  dock: (on) => BARRY.figreplay.dock(on),
  button: (run, extraClass) => {
    if (!run || run.kind !== 'figure') return null;
    return el('button', {
      class: 'btn ghost sm' + (extraClass ? ' ' + extraClass : ''),
      text: 'Walk through…', type: 'button',
      title: 'Check what this figure needs, then put it back on screen and '
           + 'compare',
      onclick: (e) => { e.stopPropagation(); BARRY.figreplay.startRun(run.id); },
    });
  },
};
