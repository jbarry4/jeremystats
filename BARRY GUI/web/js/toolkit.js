/* ==========================================================================
   toolkit.js -- The jobs that are about the whole pile, not one recording.

   Everywhere else you are looking at a single session. These are the
   questions that span it: which channels have we thrown away, across this
   mouse, over this month, in this project.

   The first tool is the bad-channel export. It is deliberately more than a
   download button: you pick the scope, you see the rows and the counts before
   committing to anything, and the file that comes out carries a header saying
   what it was a list of and when it was taken -- because a CSV called
   "export.csv" in a downloads folder is not a record.
   ========================================================================== */
'use strict';

BARRY.views.toolkit = (function () {
  let scopes = null;      // what there is to choose from
  let preview = null;     // the last previewed rows
  let busy = false;

  // What is being asked for. Held here rather than read off the DOM so a
  // re-render cannot lose a half-filled form.
  const q = {
    tool: 'bad',
    scope: 'all',
    key: '', mouse: '', group: '',
    from: '', to: '',
    form: 'long',
    clean: false,
    via: null,          // the bundle the open tool was opened from
  };

  /* ==================================================================
     Loading
     ================================================================== */
  async function onShow() {
    render();
    if (!scopes) await loadScopes();
    refresh();
    // Who is in what, and keep it current while this view is open.
    startPresence();
  }

  async function loadScopes() {
    try {
      scopes = await api('/api/toolkit/scopes');
      // Fill in every scope's default up front, so the fields are never
      // empty by the time one of them is shown -- including the date range,
      // which otherwise opens as two blank boxes that look broken.
      const was = q.scope;
      for (const sc of ['session', 'mouse', 'group', 'range']) {
        q.scope = sc;
        seedScope();
      }
      q.scope = was;
    } catch (e) {
      toast('Could not read the session list: ' + e.message, 'err', 8000);
      scopes = { sessions: [], mice: [], groups: [] };
    }
    render();
  }

  /* A scope arrives with its first option already chosen. Otherwise picking
     "One mouse" asks the server about mouse (nothing), which it rightly
     refuses -- so the panel answered a deliberate click with an error. */
  function seedScope() {
    const s = scopes || {};
    if (q.scope === 'session' && !q.key && (s.sessions || []).length) {
      // Prefer one that actually has something marked: an empty session is a
      // confusing thing to land on in a bad-channel report.
      const withBad = (s.sessions || []).find((x) => x.n_bad > 0);
      q.key = (withBad || s.sessions[0]).key;
    }
    if (q.scope === 'mouse' && !q.mouse && (s.mice || []).length) {
      q.mouse = String(s.mice[0]);
    }
    if (q.scope === 'group' && !q.group && (s.groups || []).length) {
      q.group = s.groups[0];
    }
    if (q.scope === 'range') {
      if (!q.from && s.first_day) q.from = s.first_day;
      if (!q.to && s.last_day) q.to = s.last_day;
    }
  }

  function args() {
    const p = new URLSearchParams({ scope: q.scope, form: q.form });
    if (q.scope === 'session') p.set('key', q.key);
    if (q.scope === 'mouse') p.set('mouse', q.mouse);
    if (q.scope === 'group') p.set('group', q.group);
    if (q.scope === 'range') {
      if (q.from) p.set('from', q.from);
      if (q.to) p.set('to', q.to);
    }
    if (q.clean) p.set('clean', '1');
    return p.toString();
  }

  /* The registry, kept rather than re-read.

     It takes eight seconds on this lab's data and both the Curation and
     StrataScope tools want it, so switching between them paid for it again
     every time -- and a slow read in flight is what lets a stale answer land
     on top of the tool you just opened. Held for a minute: a recording
     appearing mid-session is not what this pane is for, and `forget()` is
     there for when something really has changed. */
  let regCache = { at: 0, data: null, inflight: null };
  const REG_FRESH_MS = 60000;

  async function registry(force) {
    const now = Date.now();
    if (!force && regCache.data && now - regCache.at < REG_FRESH_MS) {
      return regCache.data;
    }
    if (regCache.inflight) return regCache.inflight;
    regCache.inflight = (async () => {
      try {
        const got = await api('/api/registry');
        regCache = { at: Date.now(), data: got, inflight: null };
        return got;
      } catch (e) {
        regCache.inflight = null;
        throw e;
      }
    })();
    return regCache.inflight;
  }

  const refresh = debounce(async function refresh_() {
    /* Checkup, Spotter and Panning are one workbench (`WB`, below): the
       same bench and shelf, each showing its own kind of set. */
    if (WB[q.tool]) { await loadCuration(); return; }
    if (q.tool === 'strata') { await loadStrata(); return; }
    if (q.tool === 'incisor') { await loadIncisor(); return; }
    if (q.tool === 'braces') { BARRY.braces.paint(); return; }
    if (q.tool === 'doppler') { await loadDoppler(); return; }
    if (q.tool === 'eye') { BARRY.eye.paint(); return; }
    /* The Confluence. Junction and Lock paint from banked entries; Panning
       is a mode, and its step page is the way in, like Spotter's. None of
       them reads the bad-channel table below. */
    /* Only when the pane is not already theirs: `render` has painted them a
       moment before this debounced call lands, and a second paint rebuilt
       the panel under the pointer -- the "it keeps reloading" Doppler had. */
    if (q.tool === 'junction') {
      const h = $('#tkResult');
      if (!(h && h.dataset.tool === q.tool)) renderResult();
      return;
    }
    if (q.tool === 'lock') { BARRY.lock.paint(); return; }
    if (q.tool === 'rootcanal') { BARRY.rootcanal.paint(); return; }
    if (q.tool === 'dspca') { BARRY.dspca.paint(); return; }
    if (q.tool === 'cfc') { await loadCFC(); return; }
    if (q.tool === 'panorama') { await loadPanorama(); return; }
    if (q.tool === 'horizon') { await loadHorizon(); return; }
    /* The Arc paints from what it is given; nothing it shows comes
       from the bad-channel query below. */
    if (ARC.some(function (st) { return st[0] === q.tool; })) {
      BARRY.arc.paint(); return;
    }
    /* Kilosort has nothing to do with bad channels.

       It used to fall through to the query below, which fetched the whole
       bad-channel table nobody had asked for and dimmed the pane to 0.55
       while it ran. renderResult then returned early for Kilosort, before
       the line that puts the opacity back -- so the pane stayed at 55% for
       good. That is the "everything is greyed out". */
    if (q.tool === 'kilosort') { renderResult(); return; }
    if (q.tool === 'snapshots') { renderResult(); return; }
    if (busy) return;
    busy = true;
    /* Which tool asked. A debounced request can land after you have clicked
       something else, and rendering its answer then replaces the pane you
       just opened -- which is the "it snaps back to another tool". */
    const asked = q.tool;
    const host = $('#tkResult');
    // Dimmed while re-querying, but only when there is already something to
    // dim; the first read shows the loader instead of a grey rectangle.
    if (host && preview) host.style.opacity = '0.55';
    else if (host) tkLoading('Bad channels',
                             ['reading every recording that has marks']);
    try {
      preview = await api('/api/toolkit/bad-channels?' + args());
      preview.error = null;
    } catch (e) {
      preview = { error: e.message, rows: [], columns: [], summary: {} };
    } finally {
      busy = false;
      if (asked !== q.tool) {
        // Superseded. Undim, and leave the current tool alone.
        if (host) host.style.opacity = '1';
      } else {
        renderResult();
      }
    }
  }, 220);

  /* ==================================================================
     The page
     ================================================================== */
  function render() {
    const host = $('#tkBody');
    if (!host) return;
    host.innerHTML = '';
    host.appendChild(el('div', { class: 'tk-layout' }, [
      el('div', { class: 'tk-tools' }, [
        el('div', { class: 'section-label',
                    text: 'Bundles' }),
        ...bundleCards(),
        el('div', { class: 'section-label', text: 'Tools' }),
        toolButton('bad', 'Bad channels',
                   'Export which channels were marked bad, by session, mouse, '
                   + 'project or date range.'),
        /* Every tool below may name itself freely: `toolButton` drops the
           ones a bundle above already lists, so a tool moving into a bundle
           is one edit to BUNDLES and nothing here. Braid and Panorama were
           the last two hand-kept entries and are now steps of The Lookout;
           they still appear here in source and correctly do not render. */
        toolButton('strata', 'StrataScope',
                   'Say which anatomical layer each channel is in, in steps: '
                   + 'Theta Walk, CA1, the hilus, then the molecular layer in '
                   + 'thirds (Method A) checked by ICA gamma (Method B) — '
                   + 'from evidence Jarvis measures, never from dentate '
                   + 'spikes.'),
        toolButton('cfc', 'Braid',
                   'Band-resolved theta power and phase-amplitude coupling, '
                   + 'against the live recording. Looks only — nothing '
                   + 'in it is saved.'),
        toolButton('panorama', 'Panorama',
                   'The whole recording at once: the spectrogram end to '
                   + 'end, which frequency was dominant and how often, '
                   + 'and the power spectrum over the range you ask '
                   + 'for. Saves into Results.'),
        toolButton('kilosort', 'Kilosort',
                   'Check this machine can sort, run a sort against a '
                   + 'recording, then open it in Phy.'),
        toolButton('snapshots', 'Import sorted snapshots',
                   'Read a folder of dentate-spike images that were sorted '
                   + 'by dragging them into Dentate Spike / Garbage / Flag '
                   + 'folders, and turn it back into curation.'),
        el('p', { class: 'hint tk-soon',
          text: 'More tools will land here as they earn their place. This is '
              + 'the section for anything that spans many recordings at '
              + 'once.' }),
      ]),
      el('div', { class: 'tk-main', id: 'tkMain' },
         /* Which tools own the whole pane. The scope card below is the
            bad-channel query's, and means nothing to the others -- the
            snapshot importer was showing it and asking which recordings to
            scope a folder read to. */
         (q.tool === 'curate' || q.tool === 'strata' || q.tool === 'cfc'
          || q.tool === 'kilosort' || q.tool === 'snapshots'
          // Incisor picks its own recording and scans every channel, so the
          // bad-channel scope card above would be describing something else.
          || q.tool === 'incisor'
          // Braces picks a banked set, which carries its own recording.
          || q.tool === 'braces'
          // Root Canal and X-ray pick a banked set too, and own the pane.
          || q.tool === 'rootcanal'
          || q.tool === 'dspca'
          // Panorama picks its own recording and its own channel, so
          // the bad-channel scope card above would be describing
          // something else.
          || q.tool === 'panorama'
          // Horizon picks its own recording and reads every good channel of
          // it, so the bad-channel scope card above would be asking a
          // question it has already answered for itself.
          || q.tool === 'horizon'
          // Every step of The Arc picks its own recordings -- by project,
          // by rat, by phase -- so the bad-channel scope card would be
          // answering a question none of them asked.
          || ARC.some(([id]) => id === q.tool)
          // Every step of The Storm picks its own recording or its own
          // banked set, so the bad-channel scope card would be describing
          // something else -- and Doppler has a channel editor of its own
          // that writes to the same record.
          || STORM.some(([id]) => id === q.tool)
          // The Confluence pools banked entries and walks pooled sets; the
          // scope card would be about a question none of its steps asks.
          || CONFLUENCE.some(([id]) => id === q.tool))
           ? [flatHead(), el('div', { class: 'tk-result', id: 'tkResult' }),
              nextHost(), feedHost()].filter(Boolean)
           : [flatHead(), scopeCard(),
              el('div', { class: 'tk-result', id: 'tkResult' }), nextHost(),
              feedHost()].filter(Boolean)),
    ]));
    renderResult();
    paintNext();
  }

  /* EVERY STEP ENDS WITH THE NEXT ONE (2026-10-20): header, picker, run
     bar, settings, result, Bank -- then "Next: <Step> — <what it does> →",
     in the same place on every bundle step, below whatever the tool drew
     (ui.handoff). Its own host, so a tool repainting its page cannot take
     it away. A tool whose next step needs something carried -- a run onto
     Spotter's bench -- says how with `setHandoff`. */
  const handoffs = {};
  function nextHost() { return el('div', { class: 'tk-next', id: 'tkNext' }); }
  /* The header the flat tools without one of their own were missing
     (2026-10-20): every tool page opens on its name and what it is for,
     as every bundle step does (ui.stepHeader). Above the tool's host, so
     the tool repainting cannot take it away. */
  const FLAT_HEADS = {
    bad: ['Bad channels', 'Which channels were marked bad: by session, mouse, '
          + 'project or date range, as a table you can download.'],
    kilosort: ['Kilosort', 'Check this machine can sort, sort a recording, '
               + 'then open the sort in Phy.'],
    snapshots: ['Import sorted snapshots', 'A folder of dentate-spike '
                + 'images sorted by dragging them into folders, read back '
                + 'into curation.'],
  };
  function flatHead() {
    const h = FLAT_HEADS[q.tool];
    if (!h) return null;
    return el('div', { class: 'tk-head' }, [
      BARRY.ui.stepHeader({ title: h[0], blurb: h[1] }),
    ]);
  }
  /* The activity feed under the Next, in a host of its own: in the tool's
     host it sat between the tool and its next step, and a tool repainting
     its page took it with it. */
  function feedHost() { return el('div', { class: 'tk-feed', id: 'tkFeed' }); }
  function paintNext() {
    const host = document.getElementById('tkNext');
    if (!host) return;
    host.innerHTML = '';
    const h = BARRY.ui.handoff && BARRY.ui.handoff(q.tool, handoffs[q.tool]);
    if (h) host.appendChild(h);
  }
  function setHandoff(toolId, opts) {
    handoffs[toolId] = opts || null;
    if (q.tool === toolId) paintNext();
  }

  /* ---------- bundles ----------

     A bundle is three tools that are one job done in three sittings, and
     the flat list above could not say so. Grouping them is the small half;
     the half worth having is that each step reads its own state, so the
     rail says where you are rather than what exists.

     The order is a real dependency. Checkup has nothing to show until
     Incisor has banked candidates, and Braces has nothing to move until
     Checkup has said which stamps are spikes -- which is why these are
     numbered and the other tools are not. */
  const DENTIST = [
    ['incisor', 'Incisor', 'find them'],
    ['curate', 'Checkup', 'clean them'],
    ['braces', 'Braces', 'line them up'],
    /* Between Braces and X-ray because it needs the first and serves the
       second: it measures at the stamp, so the stamps have to be lined up,
       and X-ray should split dentate spikes, not dentate spikes with the
       interictal discharges Incisor let through still in them. */
    ['rootcanal', 'Root Canal', 'take the IEDs out'],
    ['dspca', 'X-ray', 'tell them apart'],
  ];

  /* The Arc -- the DEWEY RATs pipeline, named after Dewey's 1896 paper
     arguing that stimulus and response are one continuous circuit rather
     than a chain, which is the claim a connectivity matrix makes.

     Four of the five are not built yet and say so rather than being left
     out: see `stepOff` below for why an absent step would read worse than a
     disabled one. The fifth element of a step is the sentence explaining
     what it is waiting for -- present means "not yet", absent means
     "ready". */
  /* Four steps, not five. Finding the pairs and filing them were drawn up
     as separate steps and are one act: a pair that has been found and not
     banked is a number on a screen, and every step after this reads the
     bank. Splitting them would have meant a tool whose only output was
     another tool's input. */
  const ARC = [
    ['spark', 'Spark', 'find and file them', null],
    ['coupling', 'Coupling', 'correlate them', null],
    ['circuit', 'Circuit', 'map them', null],
    ['drift', 'Drift', 'tell them apart', null],
  ];

  /* The Storm -- interictal discharges, from the cluster to a set
     somebody has confirmed.

     Named for what it is: radar sweeps the whole recording and says where
     the cells are, a spotter drives out and confirms by eye what radar saw,
     and the eye of the storm is its centre. That is detect, curate, align,
     and it is also the split between the cluster and this computer --
     Doppler is the only one of the three that runs anywhere else.

     The order is a real dependency, the same way The Dentist's is. Spotter
     has nothing to show until Doppler has banked candidates, and Eye has
     nothing to move until Spotter has said which of them are discharges. */
  const STORM = [
    ['doppler', 'Doppler', 'find them'],
    ['spotter', 'Spotter', 'confirm them'],
    ['eye', 'Eye', 'line them up'],
  ];

  /* The Confluence -- where The Dentist and The Storm meet.

     Named for the place two rivers become one. Incisor's dentate spikes and
     Doppler's discharges are two detectors' answers about one recording,
     and some of what each finds is the other's; Junction pools them,
     Panning sorts the pool (spike, or not -- prospectors pan a river for
     what is worth keeping), Lock lines it up (a canal lock is what levels
     boats), and Root Canal teases it apart in its three axes, each event
     coloured by its DS / IED call.

     Root Canal is a step of The Dentist too. A tool in two bundles is one
     tool: the step you came in by is remembered (`q.via`), so its chip and
     the lit card say which bundle you are working in. */
  const CONFLUENCE = [
    ['junction', 'Junction', 'pool them'],
    ['panning', 'Panning', 'sort them'],
    ['lock', 'Lock', 'line them up'],
    ['rootcanal', 'Root Canal', 'tease them apart'],
  ];

  /* The Lookout -- the frequency tools, widest view first.

     Named for the place you stand to see a long way. The order is a real
     dependency, the way The Dentist's is, and it inverts what the ToolKit
     used to ask of somebody: Panorama needs a channel named before it can
     say anything, and until now nothing answered that except somebody's
     memory of which CSC was in the cell layer last time. Horizon answers
     it, so it goes first -- find where the rhythm lives, then what it is
     doing there, then how it couples.

     Braid keeps its name rather than lending it to the bundle. Every other
     bundle here is named for its theme and none for one of its own steps,
     because a heading repeating a row underneath it is the same "menu that
     describes one thing twice" the flat list was fixed to stop being. */
  const LOOKOUT = [
    ['horizon', 'Horizon', 'every channel, by depth'],
    ['panorama', 'Panorama', 'one channel, end to end'],
    ['cfc', 'Braid', 'how the bands couple'],
  ];

  /* Every bundle in the ToolKit, in the order they are offered.

     This used to be one array and one hard-coded card, which was right
     while there was one bundle. `icon` is the tool whose glyph stands for
     the whole bundle. */
  /* The Dentist and The Storm sit together, with The Confluence under them,
     because a stream runs from both into it (`bundleCards`). */
  const BUNDLES = [
    { id: 'dentist', name: 'The Dentist', icon: 'incisor', steps: DENTIST },
    { id: 'storm', name: 'The Storm', icon: 'doppler', steps: STORM },
    { id: 'confluence', name: 'The Confluence', icon: 'junction',
      steps: CONFLUENCE },
    { id: 'arc', name: 'The Arc', icon: 'circuit', steps: ARC },
    { id: 'lookout', name: 'The Lookout', icon: 'horizon', steps: LOOKOUT },
  ];

  /* Every tool that belongs to a bundle, so nothing has to list them twice
     to keep them out of the flat list below. */
  const BUNDLED = BUNDLES.reduce(
    (acc, b) => acc.concat(b.steps.map(([id]) => id)), []);

  /* The bundle a tool is being worked in: the one it was opened from when
     it is in more than one, else the first that holds it. */
  function bundleOf(toolId) {
    const holds = (b) => b.steps.some(([id]) => id === toolId);
    if (q.via) {
      const via = BUNDLES.find((b) => b.id === q.via);
      if (via && holds(via)) return via;
    }
    return BUNDLES.find(holds) || null;
  }

  /* "step 2 of The Lookout", worked out rather than typed.

     GUI-CONSTITUTION.md 6b asks for this by name, and says why: every tool
     used to write its own chip, so when Root Canal was inserted between
     Braces and X-ray somebody had to edit X-ray's header by hand from 4 to
     5. It was done that time. Reading the position out of BUNDLES means
     inserting a step renumbers every header after it, and a tool that is
     not in a bundle gets null and draws no chip at all. */
  function stepOf(toolId) {
    const b = bundleOf(toolId);
    if (!b) return null;
    const i = b.steps.findIndex(([id]) => id === toolId);
    return 'step ' + (i + 1) + ' of ' + b.name;
  }

  /* Which bundles are folded away.

     Remembered, because which parts of a menu you care about is a standing
     preference and not a thing to re-state every morning -- the same reason
     the rail remembers its width. Stored as the FOLDED ids rather than the
     open ones, so a bundle added later arrives open and is seen, instead of
     arriving folded and never being found.

     Three bundles of three and four steps is eleven rows before the flat
     list starts, and somebody working in one of them has no use for the
     other seven. */
  const FOLD_KEY = 'barry.tkFolded';
  let folded = (() => {
    try { return new Set(JSON.parse(localStorage.getItem(FOLD_KEY) || '[]')); }
    catch (e) { return new Set(); }     // private mode
  })();

  function setFolded(id, off) {
    if (off) folded.add(id); else folded.delete(id);
    try { localStorage.setItem(FOLD_KEY, JSON.stringify([...folded])); }
    catch (e) { /* private mode: it just will not be remembered */ }
  }

  /* Fold or unfold, easing the steps rather than snapping them (constitution
     §5, "a bundle", rule 5).

     The rail is re-rendered on every change, so there is no element that
     persists across the fold for a CSS transition to run on. The steps are
     animated either side of the render instead: shrunk away before a fold,
     grown in after an unfold. The 9px the open bundle puts between head and
     steps goes with them, as a margin, so it does not jump, and the caret
     turns with them (it is a new caret after each render too, so CSS could
     not turn it). Under prefers-reduced-motion it is the plain render it
     always was. */
  const FOLD_MS = 220;
  let folding = null;           // the bundle mid-fold; a second click waits
  function foldBundle(id, off) {
    if (folding) return;
    const calm = window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const boxOf = () =>
      document.querySelector('.tk-bundle[data-bundle="' + id + '"]');
    const opts = { duration: FOLD_MS,
                   easing: 'cubic-bezier(.22, .61, .36, 1)' };  // --ease-out
    const turn = (b, from, to) => {
      const c = b && b.querySelector('.tk-bundle-hd .caret');
      if (c && c.animate) {
        c.animate([{ transform: 'rotate(' + from + 'deg)' },
                   { transform: 'rotate(' + to + 'deg)' }], opts);
      }
    };
    const was = boxOf();
    const steps = was && was.querySelector('.tk-steps');
    if (off) {
      if (calm || !steps || !steps.animate) {
        setFolded(id, true); render(); return;
      }
      folding = id;
      steps.style.overflow = 'hidden';
      turn(was, 90, 0);
      const a = steps.animate([
        { height: steps.offsetHeight + 'px', opacity: 1, marginTop: '0px' },
        { height: '0px', opacity: 0, marginTop: '-9px' },
      ], Object.assign({ fill: 'forwards' }, opts));
      settle(a, () => { setFolded(id, true); render(); });
      return;
    }
    setFolded(id, false);
    render();
    const now = boxOf();
    const grown = now && now.querySelector('.tk-steps');
    if (calm || !grown || !grown.animate) return;
    folding = id;
    grown.style.overflow = 'hidden';
    turn(now, 0, 90);
    const a = grown.animate([
      { height: '0px', opacity: 0, marginTop: '-9px' },
      { height: grown.offsetHeight + 'px', opacity: 1, marginTop: '0px' },
    ], opts);
    settle(a, () => { grown.style.overflow = ''; });
  }

  /* An animation's end, whichever comes first: the animation saying so, or
     the time it should have taken. A background tab throttles animations
     and a headless one may never tick them, and a fold that waits on an
     event that never comes leaves the rail refusing every click after. */
  function settle(anim, then) {
    let done = false;
    const end = () => {
      if (done) return;
      done = true; folding = null;
      try { anim.finish(); } catch (e) { /* already over */ }
      then();
    };
    anim.onfinish = anim.oncancel = end;
    setTimeout(end, FOLD_MS + 80);
  }

  /* The cards, with The Dentist, The Storm and The Confluence in a group of
     their own so the stream can be drawn beside them. Everything else is a
     card as it always was. */
  function bundleCards() {
    const out = [];
    const flow = el('div', { class: 'tk-flow' });
    for (const b of BUNDLES) {
      if (FLOW_IN.indexOf(b.id) >= 0 || b.id === FLOW_OUT) {
        flow.appendChild(bundleCard(b));
        if (b.id === FLOW_OUT) {
          flow.insertBefore(riverSvg(), flow.firstChild);
          out.push(flow);
          // Once the group is in the page and has heights to measure. On a
          // timer as well as a frame: a frame never comes in a background
          // tab, and the stream would be missing until something resized.
          requestAnimationFrame(() => drawRiver(flow));
          setTimeout(() => drawRiver(flow), 0);
        }
      } else {
        out.push(bundleCard(b));
      }
    }
    return out;
  }

  /* ---------- the stream ----------

     Asked for in so many words: "a stream connecting them and leading to a
     separate bundle". Two strands in the gutter to the left of the cards,
     one leaving The Dentist and one leaving The Storm, in the two origin
     colours Panning and Root Canal use for Incisor's and Doppler's events
     -- so the colours are learnt here once -- joining, and running into The
     Confluence as a pair: two-tone, the way a merged event is drawn.

     Always flowing, gently: dashes travel along the strands. The rail is
     rebuilt on every tool switch, so the animation is offset by the clock
     rather than restarted -- a stream that jumps back to the start each
     time you click is not a stream. Still under prefers-reduced-motion. */
  const FLOW_IN = ['dentist', 'storm'];
  const FLOW_OUT = 'confluence';
  const RIVER_W = 16;
  const RIVER_MS = 2400;              // one dash period; see app.css

  function riverSvg() {
    return el('svg', { class: 'tk-river', 'aria-hidden': 'true',
                       focusable: 'false' });
  }

  function drawRiver(flow) {
    const svg = flow && flow.querySelector('.tk-river');
    if (!svg || !flow.isConnected) {
      // The rail was rebuilt; this group is gone, and so is its watcher.
      if (flow && flow._riverObs) { flow._riverObs.disconnect(); }
      return;
    }
    const top = flow.getBoundingClientRect().top;
    const cardY = (id, f) => {
      const c = flow.querySelector('.tk-bundle[data-bundle="' + id + '"] '
                                   + '.tk-bundle-hd');
      if (!c) return null;
      const r = c.getBoundingClientRect();
      return r.top - top + r.height * (f == null ? 0.5 : f);
    };
    const yD = cardY('dentist'), yS = cardY('storm');
    const yC = cardY(FLOW_OUT);
    if (yD == null || yS == null || yC == null) return;
    const h = Math.ceil(flow.getBoundingClientRect().height);
    svg.setAttribute('viewBox', '0 0 ' + RIVER_W + ' ' + h);
    svg.setAttribute('width', RIVER_W);
    svg.setAttribute('height', h);
    /* As a style too: a rule elsewhere sizes svgs in the rail, and an svg
       wider than its viewBox centres the drawing -- which put the stream
       through the middle of the cards instead of in the gutter. */
    svg.style.width = RIVER_W + 'px';
    svg.style.height = h + 'px';
    svg.setAttribute('preserveAspectRatio', 'xMinYMin meet');
    /* Each strand leaves its card's head at the gutter's right edge, turns
       down, and the two run side by side once they meet, a few pixels
       apart, until they turn into The Confluence's head. */
    const xIn = RIVER_W, xA = 5, xB = 10;
    const strand = (y0, x, yEnd, xEnd) =>
      'M' + xIn + ' ' + y0.toFixed(1)
      + ' C' + (x + 3) + ' ' + y0.toFixed(1) + ' ' + x + ' '
      + (y0 + 4).toFixed(1) + ' ' + x + ' ' + (y0 + 9).toFixed(1)
      + ' L' + x + ' ' + (yEnd - 9).toFixed(1)
      + ' C' + x + ' ' + (yEnd - 3).toFixed(1) + ' ' + (xEnd - 4) + ' '
      + yEnd.toFixed(1) + ' ' + xEnd + ' ' + yEnd.toFixed(1);
    const dPath = strand(yD, xA, yC - 2, xIn);
    const sPath = strand(yS, xB, yC + 2, xIn);
    // The clock, so the dashes carry on from where they were.
    const lag = -(Date.now() % RIVER_MS) + 'ms';
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    svg.appendChild(svgFragment(
      '<path class="tk-river-bed i" d="' + dPath + '"/>'
      + '<path class="tk-river-bed d" d="' + sPath + '"/>'
      + '<path class="tk-river-i" style="animation-delay:' + lag + '" d="'
      + dPath + '"/>'
      + '<path class="tk-river-d" style="animation-delay:' + lag + '" d="'
      + sPath + '"/>'));
    // A fold changes the heights under it; the stream follows.
    if (!flow._riverObs && window.ResizeObserver) {
      flow._riverObs = new ResizeObserver(() => drawRiver(flow));
      flow._riverObs.observe(flow);
    }
  }

  function bundleCard(bundle) {
    const steps = bundle.steps;
    const here = steps.find(([id]) => id === q.tool)
      && bundleOf(q.tool) === bundle
      ? steps.find(([id]) => id === q.tool) : null;
    const on = !!here;
    const open = !folded.has(bundle.id);
    const box = el('div', {
      class: 'tk-bundle' + (on ? ' on' : '') + (open ? ' open' : ''),
      'data-bundle': bundle.id,
    });
    /* The head is the control, so it is a button -- it was a div, and a div
       you have to click is one nothing can tab to and nothing can announce.

       A folded bundle that holds the tool you are in says WHICH step that is
       instead of how many there are. Folding is then safe: the accent border
       says the tool you are in is in here, and the head says where in here,
       so putting the list away never costs you your place. */
    box.appendChild(el('button', {
      class: 'tk-bundle-hd',
      'aria-expanded': open ? 'true' : 'false',
      title: open ? 'Fold ' + bundle.name + ' away'
                  : 'Show the ' + steps.length + ' steps of ' + bundle.name,
      onclick: () => foldBundle(bundle.id, open),
    }, [
      el('span', { class: 'caret',
                   html: '<svg viewBox="0 0 20 20"><path d="m8 5 5 5-5 5"/></svg>' }),
      toolIcon(bundle.icon),
      el('strong', { text: bundle.name }),
      el('span', { class: 'tk-bundle-c',
                   text: (!open && here) ? here[1]
                                         : steps.length + ' tools' }),
    ]));
    if (!open) return box;
    box.appendChild(el('div', { class: 'tk-steps' },
      steps.map(([id, name, does, soon], i) => {
        /* A step that is not built yet is SHOWN and disabled, with the
           reason on it -- the same call the banked-set list makes for a set
           that cannot be read here. Leaving it out instead would say the
           step does not exist, and somebody arriving at Coupling needs to
           know both that it is the third of five and that the two before it
           come first. */
        return el('button', {
          class: 'tk-step' + (q.tool === id ? ' now' : '')
                 + (soon ? ' off' : ''),
          // Its colour (app.css --tool-*), the one its outputs' chips wear.
          'data-tool': id,
          title: soon ? (name + ' — ' + does + '. ' + soon)
                      : (name + ' — ' + does),
          disabled: soon ? 'disabled' : null,
          onclick: soon ? null : (() => pickTool(id, bundle.id)),
        }, [
          /* Its own mark in its own colour, on a rail down the bundle
             (2026-10-21: "get rid of the numbering"). The order is the
             rail's; `data-n` keeps it for anything that has to count. */
          el('span', { class: 'tk-step-i', 'data-n': String(i + 1),
                       'aria-hidden': 'true' }, [toolIcon(id)].filter(Boolean)),
          /* `strong`, like the flat tool buttons use, because the name of a
             tool is the same thing in both shapes. Several checks find a
             tool by reading the `strong` inside whatever was clicked, and
             having one shape spell it `span` made those look straight past
             the two tools that now live only here. Weight is set in CSS, so
             nothing moves. */
          el('strong', { class: 'tk-step-n', text: name }),
          el('span', { class: 'tk-step-s', text: does }),
          // The mark belongs on the step, now that the step is the only
          // place this tool appears.
          vaccMark(id),
        ].filter(Boolean));
      })));
    return box;
  }

  /* One per tool, drawing the thing the tool is about rather than a generic
     gear -- what makes a row findable at a glance is a shape that is about
     it. Stroke on `currentColor` at 16px, so they take the button's state
     and need no second set for the dark theme. */
  const TOOL_ICONS = {
    // Channel rows, one of them struck out.
    bad: 'M2 4h12M2 8h5M2 12h12M9.5 6.5l4 3M13.5 6.5l-4 3',
    // A dentate spike, and a tick for the decision made about it.
    curate: 'M1 11.5h2.5l2-6.5 2 6.5H10M11.5 10.5l1.5 1.5L15.5 8',
    // Layers, with the probe going down through them.
    strata: 'M2 4.5h12M2 8h12M2 11.5h12M11 2.5v11',
    // A tooth. Dentate means toothed, and an incisor is the sharp one.
    incisor: 'M4.2 3c1.7-1.3 5.9-1.3 7.6 0 1.1.9 1.1 2.6.7 4.1l-1.3 5.2c-.3 '
             + '1-1.4 1-1.7 0L8.6 8.6c-.2-.7-1-.7-1.2 0l-.9 3.7c-.3 1-1.4 1-'
             + '1.7 0L3.5 7.1C3.1 5.6 3.1 3.9 4.2 3z',
    // A tooth with its roots showing: the canal is what is cleaned out.
    rootcanal: 'M4.2 2.6c1.7-1.3 5.9-1.3 7.6 0 1.1.9 1.1 2.6.7 4.1l-1.3 5.2c-.3 '
               + '1-1.4 1-1.7 0L8.6 8.2c-.2-.7-1-.7-1.2 0l-.9 3.7c-.3 1-1.4 1-'
               + '1.7 0L3.5 6.7C3.1 5.2 3.1 3.5 4.2 2.6zM6.2 4.8v2.6M9.8 4.8v2.6',
    // Two clouds of points with the line that tells them apart.
    dspca: 'M3 4.5h.01M5.2 3h.01M4.6 6.6h.01M2.6 7.6h.01M11.4 9h.01'
           + 'M13 11.6h.01M10.6 12.4h.01M12.8 8.4h.01M1.8 13.5L14.2 2.5',
    // A tooth with a wire across it, which is what braces are.
    braces: 'M4.2 2.6c1.7-1.3 5.9-1.3 7.6 0 1.1.9 1.1 2.6.7 4.1l-1.3 5.2c-.3 '
            + '1-1.4 1-1.7 0L8.6 8.2c-.2-.7-1-.7-1.2 0l-.9 3.7c-.3 1-1.4 1-'
            + '1.7 0L3.5 6.7C3.1 5.2 3.1 3.5 4.2 2.6zM1.5 6.2h13',
    // A radar sweep: an arc of coverage with the beam through it.
    doppler: 'M8 14a6 6 0 0 1 0-12M8 14a6 6 0 0 0 0-12M2 8h12M8 8l4.5-4.5',
    // An eye, for the centre of the storm.
    spotter: 'M1 8s2.6-4.2 7-4.2S15 8 15 8s-2.6 4.2-7 4.2S1 8 1 8z'
             + 'M8 6.2A1.8 1.8 0 1 0 8 9.8a1.8 1.8 0 0 0 0-3.6z',
    /* The Confluence. Two streams becoming one; a pan with the gold left
       in it; a lock's two gates and the level between them. */
    junction: 'M2 2.5c0 4 3 5 6 6.5M14 2.5c0 4-3 5-6 6.5M8 9v4.5',
    panning: 'M1.5 8.5h13c0 2.8-2.9 4.5-6.5 4.5S1.5 11.3 1.5 8.5z'
             + 'M5.5 10.6h.01M8.6 10.9h.01M10.6 10.2h.01M4 6.5l2-3 2 3',
    lock: 'M3.5 2.5v11M12.5 2.5v11M3.5 9.5h9M6 6.5h4M1.5 13.5h13',
    // A target: the thing lined up on.
    eye: 'M8 1.6v2.2M8 12.2v2.2M1.6 8h2.2M12.2 8h2.2'
         + 'M8 3.6a4.4 4.4 0 1 0 0 8.8 4.4 4.4 0 0 0 0-8.8z'
         + 'M8 6.9a1.1 1.1 0 1 0 0 2.2 1.1 1.1 0 0 0 0-2.2z',
    // Two waves braided through one another.
    cfc: 'M1 5.5c3 0 3 5 6 5s3-5 6-5M1 10.5c3 0 3-5 6-5s3 5 6 5',
    // A grid of cells, which is what the map is: depth down, time across.
    horizon: 'M1.5 4h13v8h-13zM1.5 6.7h13M1.5 9.3h13M6 4v8M10.5 4v8',
    // A wide frame with a horizon in it.
    panorama: 'M1.5 3.5h13v9h-13zM2.5 10.5l3-3 2.5 2.5 3-3.5 2.5 3',
    // Units sorted into ordered bars.
    kilosort: 'M2.5 13.5V9M6.5 13.5V5.5M10.5 13.5V7.5M14.5 13.5V3',
    // A stack of frames.
    snapshots: 'M5 2.5h9v9M2.5 5.5h9v9h-9zM5 11l2-2 1.5 1.5L11 8',

    /* The Arc. Each one draws the thing the step is about: a spark jumping
       a gap, a relay passing it on, two waves running together, a ring of
       wired nodes, and two rings that no longer agree. */
    // A gap with a spark across it.
    spark: 'M3 8h3M10 8h3M6.8 4.5L9 7.2l-1.8 1.1L9.4 11',
    // A coil and the contact it closes.
    relay: 'M2 10.5h2l1-4 1.5 4 1.5-4 1.5 4 1-4h2M2.5 13.5h11',
    // Two waves, in step.
    coupling: 'M1.5 6c2 0 2-3 4-3s2 3 4 3 2-3 4-3M1.5 12c2 0 2-3 4-3s2 3 4 '
              + '3 2-3 4-3',
    // Nodes on a ring, wired across it.
    circuit: 'M8 1.8a6.2 6.2 0 1 0 0 12.4 6.2 6.2 0 1 0 0-12.4M8 2.2L3.2 '
             + '11M8 2.2l4.8 8.8M3.2 5.6h9.6',
    // One ring against another that has moved.
    drift: 'M6 2.5a5 5 0 1 0 0 10 5 5 0 1 0 0-10M10.5 4.2a5 5 0 1 1 0 9.6',
  };

  function toolIcon(id) {
    const d = TOOL_ICONS[id];
    if (!d) return null;
    return el('svg', { class: 'tk-ico', viewBox: '0 0 16 16',
                       'aria-hidden': 'true',
                       html: '<path d="' + d + '" />' });
  }

  /* Switching tools. One function, because the bundle's steps and the flat
     list are two doors onto the same thing and a second copy of this drifts
     -- the Kilosort host reset below was already missed once. */
  function pickTool(id, via) {
    q.tool = id;
    /* Which bundle it was opened from, for a tool in more than one. A door
       that names no bundle keeps the one already in use when it holds this
       tool -- Panning's "Tease them apart" opens Root Canal inside The
       Confluence by passing it -- and otherwise falls back to the first. */
    if (via) q.via = via;
    else if (q.via && !BUNDLES.some((b) => b.id === q.via
        && b.steps.some(([s]) => s === id))) q.via = null;
    // The Kilosort pane owns its own host; let it rebuild.
    const host = document.getElementById('tkResult');
    if (host) delete host.dataset.ks;
    render();
    refresh();
  }

  function toolButton(id, name, blurb) {
    /* A tool that belongs to a bundle is not also a row in the flat list.

       GUI-CONSTITUTION.md 6b states this as the rule with the longest
       comment in this file behind it -- "a menu that describes one thing
       twice and makes the reader work out that it is one thing" -- and says
       BUNDLED does it for you. It did not: the omissions were hand-written
       below, which is why they came with a paragraph explaining that
       Incisor and Checkup were deliberately missing. Now the rule is the
       code, so adding a bundle is one edit and cannot half-land. */
    if (BUNDLED.indexOf(id) >= 0) return null;
    return el('button', {
      class: 'tk-tool' + (q.tool === id ? ' on' : ''),
      'data-tool': id,
      onclick: () => pickTool(id),
    }, [
      el('div', { class: 'tk-tool-head' }, [
        toolIcon(id),
        el('strong', { text: name }),
        vaccMark(id),
      ].filter(Boolean)),
      el('span', { text: blurb }),
    ]);
  }

  /* A VACC mark on the tools that can run there.

     Only while the mode is on and the server says there is a cluster: the
     mark is how somebody finds out the tool has somewhere else to run, and
     a mark on a machine you have no account on would be an advertisement
     rather than an affordance.

     Listed rather than assumed, because a tool that cannot be offloaded and
     is marked as though it can is worse than one with no mark at all. */
  /* Circuit joined 2026-09-28, once real `tool=circuit` jobs had landed from
     the cluster (a single run and an array). Drift has a VACC branch but no
     cluster run has come back yet, so it is not listed. */
  /* Braces and Eye joined 2026-10-09: a set whose recording is only on the
     cluster is aligned there by the same `braces.align` (vacc_run.py). */
  /* StrataScope joined 2026-10-14: a recording only on the cluster is read
     there by the same `stratasteps.scan` (vacc_run.py), and the read comes
     home. */
  /* Lock joined 2026-10-14 with The Confluence: it is Eye's engine on a
     pooled set, so it goes to the cluster for the same reason Eye does.
     Junction does not -- it reads no recording, only banked times -- and
     Panning only looks, through the link, the way Spotter does. */
  const VACC_TOOLS = ['incisor', 'doppler', 'circuit', 'braces', 'eye',
                      'strata', 'lock'];

  /* What each tool can do with a recording that is VACC loaded and not on
     this computer -- the input to `BARRY.vacc.reach` (vacc.js says what the
     three words mean). Declared, never guessed, for the reason VACC_TOOLS
     is: a tool that claims a recording it then cannot read is worse than
     one that says plainly it needs the files here.

       'cluster'  runs there with no copy here: Incisor and Doppler (the
                  node resolves the channels and measures the gaps), Braces
                  and Eye (the stamps go up with the job). Circuit runs on
                  the cluster too, but still reads the cue folder on this
                  computer first, so it is 'here' until that moves.
       'link'     views it through the live link: Checkup, Spotter and
                  StrataScope take over Xplorefinder, which reads windows and
                  every panel off the cluster. StrataScope's steps also read
                  the recording on the cluster and bring the read home.
       'here'     everything else, until somebody checks that every read it
                  makes goes through the link or the cluster. Panorama's VACC
                  run is in the constitution's table and not built yet. */
  const READS = {
    incisor: 'cluster', doppler: 'cluster', braces: 'cluster', eye: 'cluster',
    lock: 'cluster',
    curate: 'link', spotter: 'link', panning: 'link', strata: 'link',
    xplore: 'link',
  };
  function readsOf(id) { return READS[id] || 'here'; }

  /* What the VACC mark on a tool means, said on the mark (asked for
     2026-10-09): why this tool is VACC enabled, what is processed on the
     cluster, and what using it would be like without. Per tool, because the
     three answers are different for each -- Doppler cannot run anywhere
     else at all, Braces only goes there for a recording this computer does
     not have, and Checkup never runs anything there, it only reads. One
     table, so the mark on a bundle step and on the flat list say the same
     thing. */
  const VACC_INFO = {
    incisor: {
      why: 'Finding dentate spikes means reading every channel of a whole '
         + 'recording at full rate, which ties this computer up for minutes '
         + 'per recording — and is only possible here when this computer '
         + 'has the files.',
      what: 'On the cluster, where the recording already is (the lab’s '
          + 'netfiles share, or an uploaded copy): every channel is read, '
          + 'filtered and decimated, spikes are detected on each, the gaps '
          + 'are measured and the hilus is picked. Only the per-channel '
          + 'summary and the events come back; you choose the hilus range '
          + 'and bank here.',
      without: 'Only recordings on this computer, one at a time, with this '
             + 'computer busy for each scan. Recordings that live only on '
             + 'netfiles could not be scanned from here at all.',
    },
    doppler: {
      why: 'Finding interictal discharges takes the line-length transform '
         + 'of every kept channel of a whole recording at its native rate, '
         + 'twice — far more memory than a desk computer has. It has no run '
         + 'here.',
      what: 'On the cluster: every kept channel is read twice (the threshold '
          + 'is a percentile over all of them), discharges are found, and '
          + 'which channels each one reached is worked out. The events, '
          + 'their participation and a sample of waveforms come back.',
      without: 'Doppler could not run at all. With VACC, a recording this '
             + 'computer has no copy of runs just as well — its channel list '
             + 'comes over the link and the rest is done there.',
    },
    strata: {
      why: 'StrataScope\u2019s steps start by reading every channel of the '
         + 'whole recording once. For a recording only on the cluster that '
         + 'read cannot happen here.',
      what: 'Only when this computer has no copy: a compute node reads the '
          + 'recording by the same rule as here (the first 64 channels, bad '
          + 'ones skipped) and the read — the per-second numbers and a 1250 '
          + 'Hz copy, a few hundred MB — comes home. The steps, the '
          + 'evidence, ICA and the phase map then run on this computer.',
      without: 'Only recordings on this computer could be labelled with the '
             + 'steps; one only on the cluster could be looked at but not '
             + 'read.',
    },
    braces: {
      why: 'Lining stamps up reads the signal around every curated spike on '
         + 'many channels at full rate. For a recording this computer has, '
         + 'that happens here; for one only on the cluster, it cannot.',
      what: 'Only when this computer has no copy: the stamps, the contacts '
          + 'and the settings go up with a job, and the cluster screens the '
          + 'probe, finds the depth, reads the window round each stamp and '
          + 'proposes where each one goes — by the same rule as here. The '
          + 'proposal comes back to review and bank.',
      without: 'Only sets whose recording is on this computer could be '
             + 'aligned; the rest would be listed with the reason.',
    },
    eye: {
      why: 'Eye is Braces’ engine pointed at interictal discharges, run '
         + 'three times (CSD, voltage, slope) so the measures can be '
         + 'compared — three full reads of the windows round every stamp.',
      what: 'Only when this computer has no copy: each of the three runs is '
          + 'a job on the cluster, reading the windows there; the three '
          + 'proposals come back side by side.',
      without: 'Only sets whose recording is on this computer could be '
             + 'lined up.',
    },
    lock: {
      why: 'Lock is Eye pointed at a pooled set -- Incisor’s and Doppler’s '
         + 'events together -- so it reads the windows round every stamp, '
         + 'three times over, as Eye does.',
      what: 'Only when this computer has no copy: each of the three runs is '
          + 'a job on the cluster, reading the windows there; the three '
          + 'proposals come back side by side.',
      without: 'Only pooled sets whose recording is on this computer could '
             + 'be lined up.',
    },
    panning: {
      why: 'Panning sorts a pooled set on the traces. For a recording only '
         + 'on the cluster, there is nothing here to draw them from.',
      what: 'Nothing is run. Each window — traces, CSD, voltage and '
          + 'spectrogram — is read and drawn on the cluster over a live '
          + 'link. Decisions and merges are saved here.',
      without: 'Only recordings on this computer could be sorted.',
    },
    circuit: {
      why: 'A circuit computes every coupling measure on every cue pair of '
         + 'a recording; a cohort of them is hours.',
      what: 'On the cluster: each cue pair’s coupling is computed by the '
          + 'same code, many at once; the pairs come back and the circuit is '
          + 'built and filed here.',
      without: 'One recording’s circuit is about a minute here, so a single '
             + 'one is fine; a batch over a cohort would tie this computer '
             + 'up for the whole run.',
    },
    curate: {
      why: 'Checkup shows each candidate on the traces. For a recording '
         + 'only on the cluster, there is nothing here to draw them from.',
      what: 'Nothing is run. Each window you step to — the traces and the '
          + 'CSD beside them — is read and drawn on the cluster over a live '
          + 'link, and only the picture comes back. About a second a window; '
          + 'the first takes longer while the link opens. Your decisions '
          + 'are saved here as always.',
      without: 'Only recordings on this computer could be checked.',
    },
    spotter: {
      why: 'Spotter confirms Doppler’s discharges on the traces, with the '
         + 'channels each one reached lit. For a recording only on the '
         + 'cluster, there is nothing here to draw them from.',
      what: 'Nothing is run. Each window — traces, CSD, voltage and '
          + 'spectrogram — is read and drawn on the cluster over a live '
          + 'link; the participation comes from Doppler’s run, fetched once '
          + 'if this computer has not seen it. Decisions are saved here.',
      without: 'Only recordings on this computer could be confirmed, and a '
             + 'Doppler run made from another computer would light the peak '
             + 'channel alone.',
    },
  };

  /* The words on the mark, for a harness and for any surface that wants to
     say the same thing (one table, §6c). */
  function vaccWords(id) {
    const info = VACC_INFO[id];
    if (!info) return null;
    return 'Why it is VACC enabled: ' + info.why
      + '\n\nWhat is processed on the cluster: ' + info.what
      + '\n\nWithout VACC: ' + info.without;
  }

  function vaccMark(id) {
    if (VACC_TOOLS.indexOf(id) < 0 && !VACC_INFO[id]) return null;
    if (!(BARRY.state.vacc && BARRY.vacc
          && (BARRY.vacc.last || {}).configured)) return null;
    const up = !!(BARRY.vacc.last || {}).available;
    const words = vaccWords(id) || 'This one can run on the cluster.';
    const state = up ? ''
      : '\n\nRight now: ' + ((BARRY.vacc.last || {}).why
                             || 'the cluster is not reachable.');
    return el('span', {
      class: 'tk-vacc' + (up ? ' up' : ''),
      text: 'VACC',
      title: words + state,
      'aria-label': 'VACC enabled. ' + words.replace(/\n\n/g, ' ') + state,
    });
  }

  /* ---------- picking the scope ---------- */
  function scopeCard() {
    const box = el('div', { class: 'card tk-scope' });
    box.appendChild(el('div', { class: 'section-label',
                                text: 'Which recordings' }));

    const total = (scopes && scopes.total) || 0;
    const choices = [
      ['all', 'Everything', total + ' recorded session'
        + (total === 1 ? '' : 's')],
      ['session', 'One session', 'pick it below'],
      ['mouse', 'One mouse', 'every session for that animal'],
      ['group', 'One project', 'every session in it'],
      ['range', 'A date range', 'by recording date'],
    ];
    box.appendChild(el('div', { class: 'tk-pills' }, choices.map(([id, name, sub]) =>
      el('button', {
        class: 'pill' + (q.scope === id ? ' active' : ''),
        title: sub,
        onclick: () => { q.scope = id; seedScope(); render(); refresh(); },
      }, [
        el('span', { text: name }),
        el('span', { class: 'tk-pill-sub', text: sub }),
      ]))));

    // Only the fields the chosen scope actually uses, so there is never a
    // date range sitting greyed out next to a session picker.
    const fields = el('div', { class: 'tk-fields' });
    if (q.scope === 'session') fields.appendChild(sessionPicker());
    if (q.scope === 'mouse') fields.appendChild(listPicker(
      'Mouse', (scopes && scopes.mice) || [], q.mouse,
      (v) => { q.mouse = v; refresh(); }, (m) => 'm' + m));
    if (q.scope === 'group') fields.appendChild(listPicker(
      'Project', (scopes && scopes.groups) || [], q.group,
      (v) => { q.group = v; refresh(); }));
    if (q.scope === 'range') {
      fields.appendChild(field('From', el('input', {
        type: 'date', value: q.from,
        min: (scopes || {}).first_day || null,
        max: (scopes || {}).last_day || null,
        onchange: (e) => { q.from = e.target.value; refresh(); },
      })));
      fields.appendChild(field('To', el('input', {
        type: 'date', value: q.to,
        min: (scopes || {}).first_day || null,
        max: (scopes || {}).last_day || null,
        onchange: (e) => { q.to = e.target.value; refresh(); },
      })));
      if (scopes && scopes.first_day) {
        fields.appendChild(el('p', { class: 'hint',
          text: 'Recordings on disk run ' + scopes.first_day + ' to '
              + scopes.last_day + '.' }));
      }
    }
    if (fields.childNodes.length) box.appendChild(fields);

    box.appendChild(el('div', { class: 'section-label', text: 'Shape' }));
    box.appendChild(el('div', { class: 'tk-pills flat' }, [
      el('button', {
        class: 'pill' + (q.form === 'long' ? ' active' : ''),
        title: 'One row per bad channel. Filters and pivots cleanly.',
        onclick: () => { q.form = 'long'; render(); refresh(); },
      }, [el('span', { text: 'One row per channel' })]),
      el('button', {
        class: 'pill' + (q.form === 'wide' ? ' active' : ''),
        title: 'One row per session, channels listed in a cell. Easier to read.',
        onclick: () => { q.form = 'wide'; render(); refresh(); },
      }, [el('span', { text: 'One row per session' })]),
    ]));
    box.appendChild(el('label', { class: 'toggle' + (q.clean ? ' on' : '') }, [
      el('input', {
        type: 'checkbox', checked: q.clean ? 'checked' : null,
        onchange: (e) => { q.clean = e.target.checked; refresh(); },
      }),
      el('span', { text: 'Include sessions with nothing marked' }),
    ]));
    box.appendChild(el('p', { class: 'hint',
      text: 'A zero row is the only way to tell a session that was checked '
          + 'and found clean from one nobody has looked at.' }));
    return box;
  }

  function sessionPicker() {
    const list = (scopes && scopes.sessions) || [];
    if (!list.length) {
      return el('p', { class: 'hint',
        text: 'No session has anything recorded against it yet.' });
    }

    /* The registry, for what the scope list cannot know: the date, the
       project, and whether the recording is on a drive this machine can
       reach. Joined on the session key. A scope row the registry has never
       seen still appears -- it is a real session with real marks against
       it -- and its dot stays dark, which is the truth: nothing here can
       open it. */
    const reg = registryRowsInternal();
    const byKey = new Map();
    for (const r of reg) if (r.key) byKey.set(r.key, r);
    const known = reg.length > 0;

    const rows = list.map((s) => {
      const r = byKey.get(s.key) || {};
      return {
        // pickSession identifies a row by `gid`; here the identity IS the
        // session key, which is what the scope filter is keyed on.
        gid: s.key,
        key: s.key,
        // The bad count in the label answers the question before it is
        // asked, and it is searchable along with everything else.
        label: (s.label || s.key)
               + (s.n_bad ? '   (' + s.n_bad + ' bad)' : ''),
        project: r.project, cohort: r.cohort,
        mouse: r.mouse, session: r.session, date: r.date,
        // Unknown to the registry is not reachable. Where there is no
        // registry at all, nothing is claimed either way rather than
        // every dot going dark on a cold cache.
        reachable: known ? !!r.reachable : true,
      };
    });

    return field('Session', BARRY.pickSession({
      rows,
      value: q.key,
      placeholder: 'Which session? Type a mouse, a date, a project\u2026',
      onpick: (r) => { q.key = r.gid; refresh(); },
    }));
  }

  /* The registry rows as this module holds them. The exported
     `registryRows` is the same thing; this is here so the picker above
     does not have to reach out through `BARRY.views` to read its own
     module's cache. */
  function registryRowsInternal() {
    return (((regCache.data) || {}).tree || [])
      .flatMap((p) => (p.mice || []).flatMap((m) => m.sessions || []));
  }

  function listPicker(label, values, current, onchange, fmt) {
    if (!values.length) {
      return el('p', { class: 'hint',
        text: 'No ' + label.toLowerCase() + ' has been recorded yet. Open a '
            + 'recording in Xplorefinder first.' });
    }
    return field(label, el('select', {
      onchange: (e) => onchange(e.target.value),
    }, values.map((v) => el('option', {
      value: String(v),
      selected: String(current) === String(v) ? 'selected' : null,
      text: fmt ? fmt(v) : String(v),
    }))));
  }

  function field(label, control) {
    return el('div', { class: 'field' }, [
      el('label', { text: label }), control,
    ]);
  }

  /* ---------- the rows, and what they add up to ---------- */
  /* ==================================================================
     Event curation

     A detector says where something might be; curation says what it actually
     was. Keeping those apart is the whole design: candidates arrive
     unspecified and stay that way until somebody looks at them.
     ================================================================== */
  let cur = null;
  /* Set by curation whenever a decision is made or a set is opened or put
     down. The tool reloads on its next showing instead of repainting a
     picture of how things were when it was last looked at. */
  let curStale = false;

  /* Show what it is waiting on while it waits.

     Two requests, and the registry is the slow one -- over a second on a
     network share. The pane used to say "Reading..." for both of them and
     look identical whether it was about to finish or had stalled. */
  function tkLoading(label, steps) {
    const host = $('#tkResult');
    if (!host) return null;
    host.style.opacity = '1';
    host.innerHTML = '';
    const l = stepLoader(label, steps);
    host.appendChild(el('div', { class: 'tk-loading' }, [l]));
    return l;
  }

  /* The load in flight, so several callers share one. The registry takes
     seconds on a network share -- nineteen of them in one report -- and
     without this, entering the tool, a stale flag and a refresh each
     started their own, and every copy was slower for the company. */
  let curLoading = null;

  function loadCuration() {
    if (curLoading) return curLoading;
    /* The stepped loader whenever this is actually fetching, not only on
       the very first visit. Coming back from curation the data IS being
       re-read -- that is the point of the stale flag -- and showing the old
       cards motionless for five seconds while it happens looked like the
       view had simply stopped. */
    const w = WB[q.tool];
    const l = (w && (!cur || curStale || (w.startable && !curStart[w.kind])))
      ? (w.startable ? doorLoading(w)
                     : tkLoading(w.title, ['reading the curation sets',
                                           'reading the recording registry']))
      : null;
    curLoading = (async () => {
      try {
        const got = await api('/api/curation');
        if (l) l.step('reading the recording registry');
        got.registry = await registry();
        /* And, for Spotter and Panning, the banked runs no set has been
           started from -- the list that used to be missing entirely. */
        if (w && w.startable) {
          if (l) l.step('reading the banked runs');
          try {
            const st = await api('/api/curation/startable?kind='
                                 + encodeURIComponent(w.kind));
            curStart[w.kind] = st.entries || [];
          } catch (e) { curStart[w.kind] = []; }
        }
        /* And what the cluster can read, which the cards' open buttons ask
           (`openReach`). Cached for minutes and usually already here. */
        if (BARRY.vacc && BARRY.vacc.loadKnows) {
          try { await BARRY.vacc.loadKnows(); } catch (e) { /* the drive answer stands */ }
        }
        cur = got;
        curStale = false;
      } catch (e) {
        cur = { error: e.message, sets: [], kinds: [] };
      } finally {
        curLoading = null;
      }
      /* Only if this is still the tool on screen. A four-second answer
         that lands after you have clicked StrataScope must not paint
         Curation over it -- the same guard the bad-channel loader has
         carried all along. */
      if (WB[q.tool]) renderCuration();
      return cur;
    })();
    return curLoading;
  }

  /* How the shelf is being looked at -- the shelf only, because the bench
     is not a query result and has no order to choose. Held here rather than
     read off the DOM so a re-render cannot lose a half-typed search. */
  /* The shelf is open by default (2026-10-20): it is the one way in -- every
     set put down AND every banked dataset with no set yet, searchable. */
  const curQ = { text: '', sort: 'recent', show: 'all', shelf: true,
                 fresh: true };

  /* ONE WORKBENCH, THREE DOORS (2026-10-19).

     Spotter's step page was a plain list -- "a lame list", and rightly: no
     search, no archive, no idea who was working on what, no way to put a set
     down, and none of the Doppler runs nobody had started on. Checkup's
     workbench already did all of that for every kind of set, so Spotter and
     Panning ARE it now, each showing its own kind: the bench (whose, since
     when, who is in it right now, how far through, whether it is banked;
     carry on, put it down, version, bank, export, receipt, archive), the
     shelf (search, sort, unfinished / flagged / done / archived), and one
     thing Checkup did not need -- the banked runs no set has been started
     from, to start one.

     Each door shows ITS OWN kind (2026-10-20): Checkup's dentate spikes,
     Spotter's discharges, Panning's pools. Checkup used to show every kind,
     so Junction's pools and Doppler's runs sat on its bench among the
     dentate spikes ("appeared together under Checkup; separate them").
     Harness leftovers are hidden from the doors, and counted.

     A set's kind names its bank entry ("ied.e3b31..."; `BARRY.ui.kindBase`
     for the door), and a set is entered with its own kind. Starting from a
     banked run goes through the add-a-set dialog (`newSetDialog`) and ends
     on the bench, never straight in the mode. */
  const WB = {
    curate: {
      tool: 'curate', title: 'Checkup', kinds: ['ds'], kind: 'ds',
      noun: 'dentate spikes', from: 'Incisor banks them.',
      enter: (st) => BARRY.curate.enter(st.gid, st.kind),
      startable: { kind: 'ds', noun: 'dentate spikes' },
    },
    spotter: {
      tool: 'spotter', title: 'Spotter', kinds: ['ied'], kind: 'ied',
      noun: 'discharges', from: 'Doppler banks them.',
      hideTests: true,
      blurb: 'Confirm what the radar found, one discharge at a time: solid, '
           + 'sputter, or neither.',
      enter: (st) => BARRY.spotter.enter(st.gid, null, { kind: st.kind }),
      startable: {
        kind: 'ied', noun: 'discharges', otherLabel: 'imported',
        mine: { label: 'From Doppler', chip: 'Doppler',
                test: (p) => /^Doppler/.test(p) },
        enter: (gid, id) => newSetDialog({ door: 'spotter',
                                           preset: { gid, entry: id } }),
      },
    },
    panning: {
      tool: 'panning', title: 'Panning', kinds: ['pooled'], kind: 'pooled',
      noun: 'events', from: 'Junction pools them.',
      hideTests: true,
      blurb: 'Sort a pool one event at a time: spike, garbage or flag. Every '
           + 'event shows which detector found it, and two that are one '
           + 'event can be merged.',
      enter: (st) => BARRY.panning.enter(st.gid, null, { kind: st.kind }),
      startable: {
        kind: 'pooled', noun: 'events', otherLabel: 'other',
        mine: { label: 'From Junction', chip: 'Junction',
                test: (p) => /^The Confluence/.test(p) },
        enter: (gid, id) => newSetDialog({ door: 'panning',
                                           preset: { gid, entry: id } }),
      },
    },
  };
  const wb = () => WB[q.tool] || WB.curate;
  /* The banked runs no set has been started from, per kind. */
  const curStart = {};

  /* The sets this door shows. */
  function wbSets() {
    const w = wb();
    return ((cur && cur.sets) || []).filter((st) =>
      (!w.kinds || w.kinds.indexOf(BARRY.ui.kindBase(st.kind)) >= 0)
      && !(w.hideTests && st.test));
  }

  /* Opening a set through the door it was picked up from. */
  function wbEnter(st) {
    const w = wb();
    // Each door opens its own kind; a set of another kind opens in its own
    // door's mode (a pool in Panning, a run in Spotter), never in Checkup.
    const base = BARRY.ui.kindBase(st.kind);
    const own = Object.keys(WB).map((k) => WB[k])
      .find((x) => x.kinds && x.kinds.indexOf(base) >= 0);
    return (w.kinds && w.kinds.indexOf(base) < 0 ? (own || WB.curate) : w)
      .enter(st);
  }

  /* Which half of Checkup is showing: the sets, or AI Beta (aibeta.js).
     A preference, so it survives a reload; read and written in try/catch
     because a browser set to block site data throws on the accessor. */
  const CUR_PANE_KEY = 'barry.checkupPane';
  function curPane() {
    try {
      return localStorage.getItem(CUR_PANE_KEY) === 'ai' && BARRY.aibeta
        ? 'ai' : 'sets';
    } catch (e) { return 'sets'; }
  }
  function curPaneSwitch() {
    if (!BARRY.aibeta) return null;
    return BARRY.ui.seg([
      ['sets', 'Sets', 'The curation sets: what is open on the bench, and '
                     + 'the shelf.'],
      ['ai', 'AI Beta', 'A sandbox: a model trained on finished sets and '
                      + 'tested on mice it never saw. It changes nothing.'],
    ], curPane(), (v) => {
      try { localStorage.setItem(CUR_PANE_KEY, v); } catch (e) { /* kept for this view only */ }
      renderCuration();
    }, { extra: 'cur-pane' });
  }

  const CUR_SORTS = [
    ['recent', 'Recently touched'],
    ['left', 'Most left to do'],
    ['flag', 'Most flagged'],
    ['name', 'Name'],
    ['mouse', 'Mouse and session'],
    ['size', 'Biggest'],
  ];

  /* "opened 2 hours ago", which is the fact, rather than a timestamp that
     has to be subtracted from today's date in your head.

     Date.parse is lenient about `-0400` but not required to accept it --
     the server writes strftime's %z, which has no colon -- so the offset is
     normalised first rather than left to the engine's goodwill. */
  function curWhen(iso) {
    if (!iso) return null;
    const fixed = String(iso).replace(/([+-]\d{2})(\d{2})$/, '$1:$2');
    const t = Date.parse(fixed);
    if (!isFinite(t)) return null;
    const mins = Math.round((Date.now() - t) / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + (mins === 1 ? ' minute ago' : ' minutes ago');
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return hrs + (hrs === 1 ? ' hour ago' : ' hours ago');
    const days = Math.round(hrs / 24);
    if (days < 14) return days + (days === 1 ? ' day ago' : ' days ago');
    return new Date(t).toLocaleDateString(undefined,
      { month: 'short', day: 'numeric' });
  }

  const curOpen = () => wbSets().filter((s) => s.open && !s.archived);

  /* The sets on the shelf that match what is being asked for. Everything
     not on the bench, which includes the finished ones -- being done is not
     a reason to be hidden, only a reason not to be in the way. */
  function curationRows(arch) {
    const all = wbSets();
    const q = curQ.text.trim().toLowerCase();
    const words = q ? q.split(/\s+/) : [];
    const by = (st) => (st.progress || {}).by_label || {};

    let rows = all.filter((st) => {
      if (st.open) return false;
      /* Archived sets sink (2026-10-20): never among the shelf's own rows,
         and listed apart, under the toggle at the bottom (`arch`), where
         only the search narrows them -- the pills are about live work. */
      if (!!st.archived !== !!arch) return false;
      const pr = st.progress || {};
      const pill = arch ? 'all' : curQ.show;
      if (pill === 'left' && !(pr.left > 0)) return false;
      if (pill === 'flagged' && !(by(st).flag > 0)) return false;
      if (pill === 'done' && !(pr.left === 0 && pr.total > 0)) return false;
      if (pill === 'demo' && !String(st.gid || '').startsWith('demo-')) {
        return false;
      }
      /* Archiving still means what it meant -- "I am done thinking about
         this at all" -- a stronger statement than closing it; the drawer
         at the bottom of the shelf is where those sets are found again. */
      if (!words.length) return true;
      return BARRY.ui.searchMatch(
        [st.name, st.kind_name, st.kind, st.gid, st.assignee,
         st.session && st.session.label, st.session && st.session.project],
        q, { mouse: st.session && st.session.mouse,
             session: st.session && st.session.session });
    });

    const num = (v) => (isFinite(v) ? Number(v) : -1);
    /* A stamp as a number, for the sorts. "-0400" without its colon is
     written by some of the stores and `Date.parse` will not take it. */
  const momentOf = (t) => {
    const raw = String(t || '').trim();
    if (!raw) return 0;
    const ms = Date.parse(raw.replace(' ', 'T')
                             .replace(/([+-]\d{2})(\d{2})$/, '$1:$2'));
    return isFinite(ms) ? ms : 0;
  };
  const cmp = {
      left: (a, b) => ((b.progress || {}).left || 0)
                    - ((a.progress || {}).left || 0),
      flag: (a, b) => (by(b).flag || 0) - (by(a).flag || 0),
      name: (a, b) => BARRY.ui.natCompare(a.name, b.name),
      size: (a, b) => ((b.progress || {}).total || 0)
                    - ((a.progress || {}).total || 0),
      /* Newest first, by time. These stamps are not all in one offset --
         a set opened here carries this machine's, one that came down from
         the shared table is UTC -- so comparing them as text sorted a set
         opened at 20:41 local below one from 00:37 UTC that is four
         minutes older. */
      recent: (a, b) => momentOf(b.opened_at || (b.updated || {}).at)
                      - momentOf(a.opened_at || (a.updated || {}).at),
      mouse: (a, b) => {
        const sa = a.session || {}, sb = b.session || {};
        return (num(sa.mouse) - num(sb.mouse))
            || (num(sa.session) - num(sb.session))
            || BARRY.ui.natCompare(a.name, b.name);
      },
    }[curQ.sort] || (() => 0);
    return rows.slice().sort(cmp);
  }

  function renderCuration() {
    const host = $('#tkResult');
    if (!host) return;
    /* Belt as well as braces. This is called from the presence poll, from
       every set action and from the loader, and any of those can happen
       after the tool has changed -- one place that refuses is worth more
       than a guard at each call site, because the next call site will not
       have one. */
    if (!WB[q.tool]) return;
    const w = wb();
    host.style.opacity = '1';
    host.innerHTML = '';
    /* AI Beta needs none of the sets, so it does not wait for them. */
    if (w.tool === 'curate' && curPane() === 'ai') {
      host.appendChild(el('div', { class: 'tk-head' }, [
        BARRY.ui.stepHeader({
          title: 'Checkup',
          step: BARRY.ui.stepOf('curate'),
          blurb: 'AI Beta. A model trained on the sets people have '
               + 'finished, and tested on mice it never saw. A sandbox: '
               + 'nothing here changes a set.',
        }),
        el('div', { class: 'spacer' }),
        curPaneSwitch(),
      ]));
      BARRY.aibeta.paint(host);
      return;
    }
    if (!cur || (w.startable && !curStart[w.kind])) {
      if (w.startable) { doorLoading(w); return; }
      host.appendChild(el('div', { class: 'tk-loading' }, [
        stepLoader(w.title, ['reading the curation sets',
                             'reading the recording registry'])]));
      return;
    }
    if (w.tool !== 'curate') { renderDoor(host, w); return; }

    const sets = cur.sets || [];
    const open = curOpen();

    host.appendChild(el('div', { class: 'tk-head' }, [
      /* Step 2 of The Dentist, and titled with the name on the step button
         you clicked to get here -- it said "Event curation" while the button
         said "Checkup". The number is read from the bundle (stepOf). */
      BARRY.ui.stepHeader({
        title: 'Checkup',
        step: BARRY.ui.stepOf('curate'),
        blurb: 'Event curation. ' + (open.length
          ? 'What you have open. It stays here until you close it.'
          : 'Start a set from a banked entry, or pick one up below. It '
            + 'stays here until you close it.'),
      }),
      el('div', { class: 'spacer' }),
      curPaneSwitch(),
      open.length > 1 ? el('button', {
        class: 'btn ghost sm', text: 'Clear the bench',
        title: 'Close every set on the bench. Nothing is archived, deleted '
             + 'or unbanked.',
        onclick: closeAllSets,
      }) : null,
      /* Not "Import candidates". Candidates live in the Event Bank, with
         the detector that found them and their version history; curation
         reads a version out of it. Importing them here made Event curation
         a second door into the same store, and implied a recording could
         have more than one set of a kind -- it cannot, so a second import
         merged into the first, added nothing and threw away the name. */
      /* Not a novelty. It is the only view of the decisions as a set
         rather than one at a time, which makes it the only place a
         detector producing mostly obvious garbage would show up. */
      /* Tooth Fairy over several sets at once (toothfairy.js). It asks
         which, and writes nothing until its summary is accepted. */
      BARRY.toothFairy ? el('button', {
        class: 'btn ghost sm tf-btn', id: 'tfBatchOpen',
        title: 'Let Tooth Fairy sweep several dentate spike sets in turn -- '
             + 'the ones on the bench, or any you choose -- and keep the '
             + 'calls for the sets you want.',
        onclick: () => BARRY.toothFairy.openBatch({
          onDone: () => { curStale = true; loadCuration(); },
        }),
      }, [BARRY.toothFairy.icon(), 'Tooth Fairy batch\u2026']) : null,
      el('button', {
        class: 'btn ghost sm', text: 'Hall of garbage',
        title: 'The candidates nobody had to think about — rejected fast, '
             + 'never flagged, never revisited. Useful for showing a new '
             + 'curator what garbage looks like.',
        onclick: showGarbageHall,
      }),

    ].filter(Boolean)));

    if (!sets.length) {
      host.appendChild(el('div', { class: 'hint tk-empty',
        text: 'Nothing to curate yet. Bank something from Incisor, and it '
            + 'is offered under "Pick up a set": pick it up, choose which '
            + 'version to work from, and it lands on the bench.' }));
    }

    /* ---- the bench ---- */
    const bench = el('div', { class: 'cur-sets cur-bench', id: 'curBench' });
    if (open.length) {
      for (const st of open) bench.appendChild(curCard(st));
    } else {
      bench.appendChild(el('div', { class: 'cur-bench-empty' }, [
        el('p', { text: 'Nothing open.' }),
        el('p', { class: 'hint',
          text: 'Pick one up below and it stays on the bench until you put '
              + 'it down. Closing a set neither saves nor loses anything '
              + '— every decision was written the moment you made it.' }),
      ]));
    }
    host.appendChild(bench);

    /* ---- the shelf, folded away until wanted ---- */
    const nShelf = sets.filter((s) => !s.open && !s.archived).length;
    const shelf = el('div', { class: 'cur-shelf', id: 'curShelf' });
    host.appendChild(el('div', { class: 'cur-shelf-head' }, [
      el('button', {
        class: 'cur-shelf-toggle' + (curQ.shelf ? ' on' : ''),
        text: (curQ.shelf ? '▾  ' : '▸  ')
            + (open.length ? 'Pick up another set' : 'Pick up a set')
            + '  ·  ' + nShelf + ' put down  ·  ' + freshOf(w).length
            + ' not started',
        onclick: () => { curQ.shelf = !curQ.shelf; renderCuration(); },
      }),
    ]));
    if (curQ.shelf) host.appendChild(shelf);
    if (curQ.shelf) paintShelf();
  }

  /* A door's page while it reads: its header straight away, then what it
     is waiting on, step by step -- "Spotter needs a clear loading" (asked
     2026-10-19). The registry is the slow read, seconds on a share. */
  function doorLoading(w) {
    const host = $('#tkResult');
    if (!host) return null;
    host.style.opacity = '1';
    host.innerHTML = '';
    host.appendChild(el('div', { class: 'tk-head' }, [
      BARRY.ui.stepHeader({ title: w.title, step: BARRY.ui.stepOf(w.tool),
                            blurb: w.blurb }),
    ]));
    const l = stepLoader('Reading ' + w.title + '\u2019s sets',
                         ['reading the curation sets',
                          'reading the recording registry',
                          'reading the banked runs']);
    host.appendChild(el('div', { class: 'tk-loading' }, [l]));
    return l;
  }

  /* Spotter's and Panning's page: Checkup's bench and shelf for its own
     kind of set, then the banked runs no set has been started from. */
  function renderDoor(host, w) {
    const sets = wbSets();
    const open = curOpen();
    const fresh = curStart[w.kind] || [];
    const tests = ((cur && cur.sets) || []).filter(
      (st) => w.kinds.indexOf(BARRY.ui.kindBase(st.kind)) >= 0 && st.test).length
      + fresh.filter((e) => e.test).length;
    host.appendChild(el('div', { class: 'tk-head' }, [
      BARRY.ui.stepHeader({
        title: w.title, step: BARRY.ui.stepOf(w.tool), blurb: w.blurb,
      }),
      el('div', { class: 'spacer' }),
      open.length > 1 ? el('button', {
        class: 'btn ghost sm', text: 'Clear the bench',
        title: 'Close every ' + w.title + ' set on the bench. Nothing is '
             + 'archived, deleted or unbanked.',
        onclick: closeAllSets,
      }) : null,

    ].filter(Boolean)));

    /* ---- the bench ---- */
    const bench = el('div', { class: 'cur-sets cur-bench', id: 'curBench' });
    if (open.length) {
      for (const st of open) bench.appendChild(curCard(st));
    } else {
      bench.appendChild(el('div', { class: 'cur-bench-empty' }, [
        el('p', { text: 'Nothing open.' }),
        el('p', { class: 'hint',
          text: (sets.length ? 'Pick one up from the shelf below, or start '
                             : 'Start ')
              + 'one from a banked run. It stays on the bench until you put '
              + 'it down, and every decision is written the moment it is '
              + 'made.' }),
      ]));
    }
    host.appendChild(bench);

    /* ---- the shelf ---- */
    const nShelf = sets.filter((s) => !s.open && !s.archived).length;
    /* ONE WAY IN (2026-10-20): "make Pick up a set the only way to load
       things in". The shelf holds every set put down AND every banked run
       with no set yet, searchable together, each with Archive on its row. */
    host.appendChild(el('div', { class: 'cur-shelf-head' }, [
      el('button', {
        class: 'cur-shelf-toggle' + (curQ.shelf ? ' on' : ''),
        text: (curQ.shelf ? '\u25be  ' : '\u25b8  ')
            + (open.length ? 'Pick up another set' : 'Pick up a set')
            + '  \u00b7  ' + nShelf + ' put down  \u00b7  '
            + freshOf(w).length + ' not started',
        onclick: () => { curQ.shelf = !curQ.shelf; renderCuration(); },
      }),
    ]));
    if (curQ.shelf) {
      host.appendChild(el('div', { class: 'cur-shelf', id: 'curShelf' }));
      paintShelf();
    }
    if (tests) {
      host.appendChild(el('p', { class: 'hint quiet',
        text: tests + ' set' + (tests === 1 ? '' : 's') + ' and run'
            + (tests === 1 ? '' : 's') + ' left behind by test harnesses '
            + (tests === 1 ? 'is' : 'are') + ' not shown.' }));
    }
  }

  /* One set on the bench. Two verbs on the face of it -- carry on, or put
     it down -- and everything administrative folded behind "More", because
     a row that offers you Delete reads as a record in a table rather than
     as work in progress. */
  /* ---------- who is in what, right now ----------

     Kept separate from the curation sets themselves because it is a
     different kind of fact: a set is a record and is still true tomorrow,
     presence is a claim about this minute. A stale "nobody is here" is
     worse than showing nothing -- it looks authoritative, and somebody acts
     on it -- but the claim itself only changes when somebody beats, once a
     minute (curate.js PRESENCE_BEAT), so asking every ten seconds bought
     nothing the server knew.

     Cost (constitution §11, rule 5): one request per poll at most, and the
     server answers several askers from one read (presence.READ_TTL_S) --
     ~120 an hour with ToolKit in front, none when hidden or elsewhere. */
  const PRESENCE_POLL = 30000;
  let presence = { sessions: [], machine: null, ttl_s: 150 };
  let presenceTimer = null;

  async function loadPresence(andRender) {
    try {
      const res = await api('/api/presence');
      if (!res || !res.ok) return;
      const before = presenceSig(presence.sessions);
      presence = res;
      /* Only redraw when it actually changed, and only when the tool it is
         about is the one on screen. This runs every ten seconds for as long
         as the ToolKit is open, so without the second condition it repaints
         Curation over StrataScope, or over Kilosort, on its own -- a jump to
         another module with nothing you did to explain it. */
      if (andRender && WB[q.tool]
          && presenceSig(res.sessions) !== before) {
        renderCuration();
      }
    } catch (e) { /* presence is a courtesy, never an interruption */ }
  }

  /* What a presence answer says, less how old each row is. `age_s` differs
     on every read, so comparing whole answers redrew Curation every poll --
     and each redraw remounted the tool feed, which fired a full read of its
     own. Whether somebody is active, and where they are, is the news. */
  function presenceSig(list) {
    return JSON.stringify((list || []).map((r) => {
      const o = Object.assign({}, r);
      delete o.age_s;
      return o;
    }));
  }

  function startPresence() {
    if (presenceTimer) return;
    loadPresence(true);
    presenceTimer = setInterval(() => {
      // Only while the curation view is the one being looked at. Polling for
      // a panel nobody can see is just traffic.
      if (BARRY.state.view !== 'toolkit') return;
      // Nor while the window is behind another one, nor after ten minutes
      // with nobody at it (BARRY.idle). The answer is a fresh read every
      // time somebody comes back, so nothing is missed by not asking.
      if (BARRY.idle ? BARRY.idle.away() : document.hidden) return;
      loadPresence(true);
    }, PRESENCE_POLL);
  }

  if (BARRY.idle) {
    BARRY.idle.onWake(() => {
      if (presenceTimer && BARRY.state.view === 'toolkit') loadPresence(true);
    });
  }

  /* Stop asking.

     There was no way to: startPresence had no counterpart anywhere in this
     file, so the timer it starts ran for the life of the page. The view
     check inside it kept the fetches down while you were elsewhere, but the
     timer itself never stopped, and the moment ToolKit was shown again it
     resumed -- including in a background tab. Called from onHide below. */
  function stopPresence() {
    if (!presenceTimer) return;
    clearInterval(presenceTimer);
    presenceTimer = null;
  }

  /* Everyone active in a set, this machine included -- the card wants to
     show "you, on the rig" as much as anybody else. */
  function inSet(st) {
    return (presence.sessions || []).filter(
      (s) => s.active && s.gid === st.gid && (s.kind || 'ds') === st.kind);
  }

  /* Somebody who is not us. This is what gates opening. */
  function heldBy(st) {
    return inSet(st).filter((s) => !s.is_me)[0] || null;
  }

  function howLong(sec) {
    if (sec == null) return '';
    if (sec < 60) return 'just now';
    const m = Math.round(sec / 60);
    if (m < 60) return m + ' min ago';
    return Math.round(m / 60) + ' h ago';
  }

  /* The live line. Present only when somebody is in the set, so a quiet
     shelf stays quiet. */
  function presenceLine(st) {
    const here = inSet(st);
    if (!here.length) return null;
    return el('div', { class: 'cur-live' }, here.map((s) => {
      const n = (s.n_decided != null && s.n_total)
        ? s.n_decided + '/' + s.n_total : null;
      const bits = [];
      if (n) bits.push(n + ' decided');
      if (s.n_this_visit) bits.push('+' + s.n_this_visit + ' this sitting');
      if (s.at_index != null) bits.push('at #' + (s.at_index + 1));
      return el('span', {
        class: 'cur-live-who' + (s.is_me ? ' me' : ''),
        title: (s.person || 'Somebody') + ' on ' + (s.device || s.machine)
             + '\nlast heard from ' + howLong(s.age_s)
             + (s.is_me ? '\nThis is this machine.' : ''),
      }, [
        el('span', { class: 'cur-live-dot' }),
        el('b', { text: s.is_me ? 'You' : (s.person || s.device || 'Somebody') }),
        el('span', { text: ' on ' + (s.device || s.machine) }),
        bits.length ? el('span', { class: 'cur-live-n',
                                   text: '  ·  ' + bits.join('  ·  ') }) : null,
      ].filter(Boolean));
    }));
  }

  /* Opening a set somebody else is actively in.

     Advisory, and the override is right there. The ask was to stop two
     people curating the same file *accidentally* -- an accident is prevented
     by being told, and a hard block would also stop the deliberate case,
     which is legitimate and common: somebody left a set open on a rig and
     went home. A lock that gets in the way of the honest case is a lock
     people learn to route around.

     Taking it marks their session rather than deleting it, so their window
     finds out and says so, instead of carrying on writing decisions into a
     set it no longer holds. */
  async function enterSet(st) {
    const held = heldBy(st);
    if (!held) { wbEnter(st); return; }

    const who = held.person || held.device || 'Somebody';
    const got = (held.n_decided != null && held.n_total)
      ? held.n_decided + ' of ' + held.n_total + ' decided'
      : 'in progress';
    const ok = await BARRY.confirm(
      who + ' is curating this set right now',
      who + ' has it open on ' + (held.device || held.machine)
      + ', last heard from ' + howLong(held.age_s) + ' — ' + got
      + (held.n_this_visit ? ', ' + held.n_this_visit + ' this sitting' : '')
      + '.\n\nIf you both work on it you will both be deciding the same '
      + 'candidates, and the merge will have to pick a winner. Nothing is '
      + 'lost either way, but one of you will have wasted the afternoon.'
      + '\n\nOpening it anyway tells their window that you have taken it, '
      + 'so they find out rather than carrying on.',
      'Take it anyway');
    if (!ok) return;

    try {
      await apiPost('/api/presence/take',
                    { gid: st.gid, kind: st.kind, machine: held.machine });
    } catch (e) { /* saying so is best effort; opening it is not */ }
    wbEnter(st);
    loadPresence(true);
  }

  /* ==================================================================
     The hall of garbage
     ==================================================================
     The candidates nobody had to think about: rejected, decided in under a
     couple of seconds, never flagged, never revisited. Which makes it a
     teaching set -- the fastest way to explain what garbage looks like is
     forty examples that nobody hesitated over -- and a sanity check on the
     detector, since a detector producing this much obvious garbage is
     saying something about its threshold.

     The honest part is the caveat. Most of the decisions in this store were
     backfilled with one shared timestamp, so their gaps are not durations
     at all, and those are excluded and counted rather than quietly averaged
     in. A hall of fame built on made-up numbers would be worse than none.
     ================================================================== */
  let hall = null;

  async function showGarbageHall() {
    showModal(el('div', { class: 'gh-wrap' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Hall of garbage' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'hint', text: 'Reading every decision…' }),
      ]),
    ]));
    try {
      hall = await api('/api/curation/garbage-hall?limit=60');
    } catch (e) {
      hall = { failed: e.message };
    }
    drawHall();
  }

  function drawHall() {
    if (!hall) return;
    const rows = hall.hall || [];
    const body = el('div', { class: 'mb' });

    if (hall.failed) {
      body.appendChild(el('div', { class: 'hint',
        text: 'Could not read the decisions: ' + hall.failed }));
    } else {
      body.appendChild(el('p', { class: 'sub',
        text: 'Rejected in under ' + hall.quick_s + ' seconds, never '
            + 'flagged, never revisited. Sorted by how fast the call was.' }));

      /* Said before the list, not after it. If most of the store cannot be
         timed then the list is a sample of a corner of it, and somebody
         reading "5 qualify" out of nine thousand decisions deserves to know
         why before they conclude the detector is fine. */
      if (hall.unusable) {
        body.appendChild(el('div', { class: 'ecx-warn' }, [
          el('strong', { text: hall.unusable.toLocaleString()
                             + ' decisions could not be timed. ' }),
          el('span', { text: hall.why || 'They share one timestamp, so the '
            + 'gap between them is not how long anybody took. They are left '
            + 'out rather than guessed at.' }),
        ]));
      }

      if (!rows.length) {
        body.appendChild(el('div', { class: 'hint',
          text: 'Nothing qualifies yet. It fills up as people curate — '
              + 'every fast rejection lands here.' }));
      } else {
        const list = el('div', { class: 'gh-list' });
        rows.forEach((r, i) => {
          list.appendChild(el('div', { class: 'gh-row' }, [
            el('span', { class: 'gh-rank', text: '#' + (i + 1) }),
            el('span', { class: 'gh-took', text: r.took_s + 's' }),
            el('span', { class: 'gh-sess', text: r.session || r.gid }),
            el('span', { class: 'gh-at', text: fmtClock(r.start) }),
            el('span', { class: 'gh-by', text: r.by || '' }),
            /* Straight to the candidate, because "show me" is the next
               thought after "that was quick". */
            el('button', {
              class: 'linkish gh-go', text: 'look',
              title: 'Open that recording at that moment',
              onclick: () => { closeModal(); goToCandidate(r); },
            }),
          ]));
        });
        body.appendChild(list);
        body.appendChild(el('div', { class: 'hint gh-foot',
          text: rows.length >= hall.n
            ? (hall.n === 1 ? 'One qualifies.'
                            : 'All ' + hall.n + ' that qualify are shown.')
            : hall.n + ' qualify altogether; the fastest ' + rows.length
              + ' are shown.' }));
      }
    }

    showModal(el('div', { class: 'gh-wrap' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Hall of garbage' }),
        el('span', { class: 'sub',
          text: 'The candidates nobody had to think about' }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x',
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>',
          onclick: closeModal }),
      ]),
      body,
    ]), { replace: true });
  }

  function fmtClock(sec) {
    if (!isFinite(sec)) return '';
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m + ':' + (s < 10 ? '0' : '') + s.toFixed(1);
  }

  /* Open the recording it came from and put the window on it. Not curation
     mode -- looking at an example is not deciding it, and entering curation
     would take the set off whoever has it and reset their pass. */
  async function goToCandidate(r) {
    const sets = (cur && cur.sets) || [];
    const st = sets.find((x) => x.gid === r.gid && x.kind === r.kind);
    const label = (st && st.session && st.session.label) || r.session || r.gid;
    let info = st;
    if (!info) {
      try {
        info = await api('/api/curation/' + encodeURIComponent(r.gid) + '/'
                         + encodeURIComponent(r.kind));
      } catch (e) { info = null; }
    }
    const row = Object.assign({ gid: r.gid }, (info && info.session) || {});
    const got = BARRY.vacc.reachFor(row, 'xplore');
    if (!got.path) {
      toast((got.why || 'That recording is not reachable from this machine.')
            + ' (' + label + ')', 'warn', 8000);
      return;
    }
    setView('xplore');
    const sess = await BARRY.views.xplore.open(got.path);
    if (!sess) return;
    /* A second either side, the same window curation uses -- enough to tell
       a deflection from an artifact on one wire, which is the whole point of
       looking at it. */
    BARRY.views.xplore.setWindow(0, Math.max(0, r.start - 0.5), 1.0);
  }

  /* WHETHER A SET'S RECORDING CAN BE OPENED HERE (2026-10-13).

     The same answer the tool gives when it opens it -- `BARRY.vacc.reachFor`,
     this computer first and the cluster second -- so the button and the
     open cannot disagree. The cards used to ask `session.reachable`, which
     is "on a drive this computer mounts" and nothing else: Isabella's
     machine had no copy of PTEN_DKO m44 s1, the cluster reads it in place on
     netfiles, Checkup would have opened it through the link, and "Look
     again…" was greyed out with no way in. Returns { ok, where, why }:
     `why` is the reach's own sentence when it cannot, so a greyed button
     says the real reason (no VACC account here, no read access, nowhere at
     all) rather than only "not on a drive". */
  function openReach(gid, session, tool) {
    const row = Object.assign({ gid: gid }, session || {});
    const got = (BARRY.vacc && BARRY.vacc.reachFor)
      ? BARRY.vacc.reachFor(row, tool)
      : { path: (row.here || [])[0] || null,
          where: (row.here || [])[0] ? 'here' : null,
          why: 'This recording is not on a drive this machine can reach.' };
    return { ok: !!got.path, where: got.where, why: got.why
             || 'This recording is not on a drive this machine can reach.' };
  }

  function curCard(st) {
    const pr = st.progress || {};
    const done = pr.left === 0 && pr.total > 0;
    const rr = openReach(st.gid, st.session, wb().tool);
    const reach = rr.ok;
    const who = st.assignee || null;
    const when = curWhen(st.opened_at);
    const key = st.gid + '/' + st.kind;

    const more = el('div', { class: 'cur-set-more',
                             hidden: curMore[key] ? null : 'hidden' }, [
      el('button', {
        class: 'btn ghost sm', text: 'Bank the results…',
        disabled: pr.specified ? null : 'disabled',
        title: pr.specified
          ? 'Publish the decided ones to the Event Bank as a new version. '
            + 'Not a save — the decisions are already saved.'
          : 'Nothing has been decided yet',
        onclick: () => bankSet(st),
      }),
      el('button', {
        class: 'btn ghost sm', text: 'Export CSV',
        onclick: () => window.open(
          '/api/curation/' + encodeURIComponent(st.gid) + '/'
          + encodeURIComponent(st.kind) + '/export', '_blank'),
      }),
      /* What the last sitting on it came to. Available whether or not the
         set is open, because the question "how long did that take" arrives
         after you have already left. */
      el('button', {
        class: 'btn ghost sm', text: 'Receipt',
        disabled: (pr.specified) ? null : 'disabled',
        title: pr.specified
          ? 'What the last sitting on this set came to, and how fast'
          : 'Nothing has been decided yet',
        onclick: () => BARRY.curate.receipt(st.gid, st.kind),
      }),
      el('button', {
        class: 'btn ghost sm', text: st.archived ? 'Unarchive' : 'Archive',
        title: st.archived
          ? 'Put it back on the shelf'
          : 'Files the set away: off the shelf as well as off the bench. '
            + 'Nothing is deleted — every candidate and every decision '
            + 'stays exactly as it is, and it can still be opened, curated '
            + 'and banked.',
        onclick: () => archiveSet(st, !st.archived),
      }),
      /* No Delete. It erased every machine's shard of the set -- the one
         irreversible thing in this view, sitting at the same weight as
         Export CSV. Archiving is what "get this out of my way" means, and
         it destroys nothing. */
    ]);

    /* Whose it is and when it was last picked up. Without a name on it,
       forty sets are forty identical rows and there is no way to tell
       "mine, this morning" from "somebody's, in June".

       `presenceLine` goes above the progress bar, because it is about right
       now and the bar is about the set. */
    const card = BARRY.ui.workbenchCard({
      done: done,
      extra: st.archived ? 'archived' : null,
      title: st.name,
      gid: st.gid,
      kind: st.kind,
      chips: [
        el('span', { class: 'hk-chip', text: st.kind_name }),
        el('span', { class: 'cur-set-sess',
                     text: (st.session || {}).label || st.gid }),
        // Which dataset it is (2026-10-20): a set belongs to one bank
        // entry, and two on one recording are told apart by it.
        entryChip(st),
        // Whether the work on it is in the Event Bank (setpicker.js).
        BARRY.setPicker ? BARRY.setPicker.bankChip(st) : null,
      ].filter(Boolean),
      count: pr.specified + ' / ' + pr.total
             + (done ? '  ✓' : '  ·  ' + pr.left + ' left'),
      owner: { name: who, onAssign: () => assignSet(st) },
      // The id the push files it under (cloudsync.rows_curation).
      sync: { kind: 'curation', id: st.gid + '__' + st.kind },
      when: when ? 'opened ' + when
                   + (st.opened_by && st.opened_by !== who
                       ? ' by ' + st.opened_by : '') : null,
      extras: [presenceLine(st)].filter(Boolean),
      progress: pr.percent || 0,
      tally: (st.labels || []).map((l) => el('span', {
        class: 'cur-tally', style: '--cat:' + l.color,
        text: l.name + '  ' + ((pr.by_label || {})[l.id] || 0),
      })),
      actions: [
        el('button', {
          class: 'btn sm', text: pr.left ? 'Carry on…' : 'Look again…',
          disabled: reach ? null : 'disabled',
          title: !reach ? rr.why
            : rr.where === 'vacc'
              ? 'Open the recording off the cluster and step through the '
                + 'candidates. It is not on this computer, so each window is '
                + 'a round trip, about a second.'
              : 'Open the recording and step through the candidates',
          onclick: () => enterSet(st),
        }),
        el('button', {
          class: 'btn ghost sm', text: 'Close',
          title: 'Off the bench. Nothing to save first — every decision '
               + 'was written as you made it, and it is all still here.',
          onclick: () => openSet(st, false),
        }),
        /* Only where there is a choice. A set with one banked version, or
           none, has nothing to switch between, and a button that answers
           every press with "there is nothing to do" teaches people not to
           press buttons. 1 of the 45 sets here has no banked history at
           all. */
        BARRY.vers.askable(st.history) ? el('button', {
          class: 'btn ghost sm', text: 'Version\u2026',
          title: 'Which banked pass this one is carrying on from. Switching '
               + 'puts the current version down and picks another up \u2014 '
               + 'the decisions on the set become that version\u2019s.',
          onclick: () => switchSetVersion(st),
        }) : null,
        el('div', { style: 'flex:1' }),
        el('button', {
          class: 'btn ghost sm', text: curMore[key] ? 'Less' : 'More…',
          onclick: () => {
            curMore[key] = !curMore[key];
            renderCuration();
          },
        }),
      ],
    });
    /* The administrative half, folded away, sits below everything the card
       is about -- so it is appended rather than being a slot every other
       bench card would have to know about. */
    if (more) card.appendChild(more);
    return card;
  }

  /* Which cards have their administrative half showing. Outside the render
     so opening it survives the next repaint. */
  const curMore = {};

  /* The dataset a set stands for: its detector and the bank entry's id,
     with the entry's name in the title. Older sets say the entry they were
     started from, when they know it. */
  function entryChip(st) {
    const src = st.source || {};
    const id = st.entry || src.bank_entry;
    if (!id) return null;
    const v = src.version !== undefined && src.version !== null
      ? ' · from ' + BARRY.ui.versionLabel(src.version) : '';
    const pr = BARRY.ui.producerOf(src.pipeline, BARRY.ui.kindBase(st.kind));
    return BARRY.ui.chip(((pr && pr.label) || 'bank entry') + v, {
      flag: true, extra: 'cur-entry producer',
      title: 'This set belongs to bank entry ' + id
           + (src.entry_name ? ' (\u201c' + src.entry_name + '\u201d)' : '')
           + (st.entry ? '. Its versions are that entry\u2019s, and nothing '
                         + 'else writes to it.'
                       : '. An older set: one per recording and kind.'),
    });
  }

  /* The shelf: a picker, and the only place the list is a list. This is
     where searching and sorting belong -- you are looking something up. */
  function paintShelf() {
    const shelf = document.getElementById('curShelf');
    if (!shelf) return;
    shelf.innerHTML = '';
    const sets = wbSets();
    const down = sets.filter((s) => !s.open && !s.archived);
    const nLeft = down.filter((s) => ((s.progress || {}).left || 0) > 0).length;
    const nFlag = down.filter(
      (s) => (((s.progress || {}).by_label) || {}).flag > 0).length;
    const nDone = down.filter((s) => {
      const p = s.progress || {};
      return p.left === 0 && p.total > 0;
    }).length;
    const nDemo = down.filter(
      (s) => String(s.gid || '').startsWith('demo-')).length;
    // The archived ones are the drawer at the bottom of the list now.
    if (curQ.show === 'archived') curQ.show = 'all';

    const search = el('input', {
      type: 'text', class: 'cur-search', value: curQ.text,
      placeholder: 'Search a name, a mouse, a session, a person…',
      oninput: (e) => { curQ.text = e.target.value; paintShelfList(); },
    });
    const chip = (id, label, n) => el('button', {
      class: 'pill' + (curQ.show === id ? ' active' : ''),
      disabled: (n === 0 && id !== 'all') ? 'disabled' : null,
      text: label + ' (' + n + ')',
      onclick: () => { curQ.show = id; paintShelf(); },
    });

    shelf.appendChild(el('div', { class: 'cur-filter' }, [
      search,
      el('select', {
        title: 'Order',
        onchange: (e) => { curQ.sort = e.target.value; paintShelfList(); },
      }, CUR_SORTS.map(([v, t]) => el('option', {
        value: v, text: t, selected: curQ.sort === v ? 'selected' : null }))),
    ]));
    shelf.appendChild(el('div', { class: 'res-toolbar cur-chips' }, [
      chip('all', 'All', down.length),
      chip('left', 'Unfinished', nLeft),
      chip('flagged', 'Has flagged', nFlag),
      chip('done', 'Done', nDone),
      nDemo ? chip('demo', 'Demo', nDemo) : null,
      el('div', { class: 'spacer', style: 'flex:1' }),
      el('span', { class: 'hint', id: 'curCount' }),
    ].filter(Boolean)));
    /* Named columns. A bare "416 ✓", a dash and "15 minutes ago"
       are three facts nobody can identify without being told which
       is which. */
    /* One grid for the header and every row (2026-10-20). Each row used to
       be a grid of its own, so its last column sized to its own chip and
       buttons and every column before it moved row to row -- the numbers
       and names zig-zagged down the shelf, and a wide row ran off the
       right edge. Rows are subgrids of this one now: a column is as wide as
       its widest cell, for every row at once. */
    shelf.appendChild(el('div', { class: 'cur-shelf-grid' }, [
      el('div', { class: 'cur-shelf-cols' }, [
        el('span', { class: 'csr-name', text: 'Set' }),
        el('span', { class: 'csr-sess', text: 'Recording' }),
        el('span', { class: 'csr-n', text: 'Decided' }),
        el('span', { class: 'csr-who', text: 'Whose' }),
        el('span', { class: 'csr-when', text: 'Last touched' }),
        el('span', {}),
      ]),
      el('div', { class: 'cur-shelf-list', id: 'curShelfList' }),
    ]));
    paintShelfList();
  }

  /* Only the list, so typing in the search box does not rebuild the box
     being typed into and lose the caret. */
  function paintShelfList() {
    const list = document.getElementById('curShelfList');
    if (!list) return;
    list.innerHTML = '';
    const rows = curationRows();
    const total = wbSets().filter((s) => !s.open && !s.archived).length;
    const count = document.getElementById('curCount');
    if (count) {
      count.textContent = rows.length === total
        ? rows.length + (rows.length === 1 ? ' set' : ' sets')
        : rows.length + ' of ' + total;
    }
    if (!rows.length) {
      list.appendChild(el('div', { class: 'hint',
        text: 'Nothing matches that. Clear the search, or pick All.' }));
    }
    for (const st of rows) list.appendChild(shelfRow(st));
    /* And what is banked with no set yet: picking one up asks which version
       to work from and puts it on the bench (2026-10-20). */
    const fresh = freshRows(false);
    if (fresh.length) {
      list.appendChild(el('div', { class: 'cur-shelf-sub',
        text: 'Banked, not started \u2014 ' + fresh.length }));
      for (const e of fresh) list.appendChild(freshRow(e));
    }
    const gone = curationRows(true).map((st) => ({ st }))
      .concat(freshRows(true).map((e) => ({ e })));
    const tail = BARRY.ui.archivedTail({
      key: 'shelf-' + wb().tool, items: gone,
      noun: ['one', 'ones'],
      render: (xs) => xs.map((x) => (x.st ? shelfRow(x.st) : freshRow(x.e))),
      onToggle: () => paintShelfList(),
    });
    if (tail) list.appendChild(tail);
  }

  /* The banked datasets of this door's kind that no set stands for. */
  function freshOf(w, all) {
    return ((curStart[w.kind] || []).filter((e) => !e.test
                                            && (all || !e.archived)));
  }

  function freshRows(arch) {
    const q = curQ.text.trim();
    // The pills are about sets in progress; with one on, only sets show.
    if (!arch && curQ.show !== 'all') return [];
    return BARRY.ui.natSort(freshOf(wb(), true).filter((e) => !!e.archived === !!arch
      && BARRY.ui.searchMatch([e.name, e.session_label, e.project, e.by,
                               e.pipeline, e.gid], q,
                              { mouse: e.mouse, session: e.session })),
      (e) => [e.session_label || e.gid, e.name || '']);
  }

  function freshRow(e) {
    const w = wb();
    const when = curWhen(e.at);
    return el('div', {
      class: 'cur-shelf-row fresh' + (e.archived ? ' is-archived' : ''),
    }, [
      el('span', { class: 'csr-name', text: e.name || 'unnamed' }),
      el('span', { class: 'csr-sess', text: e.session_label || e.gid }),
      el('span', { class: 'csr-n', text: (e.n || 0).toLocaleString()
                                       + ' to decide' }),
      el('span', { class: 'csr-who' + (e.by ? '' : ' none'),
                   text: e.by || '\u2014' }),
      el('span', { class: 'csr-when', text: when || '' }),
      el('div', { class: 'csr-acts' }, [
        el('div', { class: 'csr-chips' }, [
          BARRY.ui.producerChip(e.pipeline, w.kind),
          BARRY.ui.chip('not started', { flag: true }),
        ].filter(Boolean)),
        e.archived ? el('span', { class: 'csr-slot' }) : el('button', {
          class: 'btn ghost sm', text: 'Pick it up',
          title: 'Choose which version to work from, and put it on the bench '
               + 'as a set of its own',
          onclick: () => newSetDialog({ door: w.tool,
                                        preset: { gid: e.gid, entry: e.id },
                                        quick: true }),
        }),
        el('button', {
          class: 'btn ghost sm', text: e.archived ? 'Unarchive' : 'Archive',
          title: e.archived
            ? 'Offer it again'
            : 'File it away: kept in the Event Bank, not offered here. '
              + 'Nothing is deleted.',
          onclick: () => archiveEntry(e, !e.archived),
        }),
        // No arrow: there is no set to open yet. The slot keeps the columns.
        el('span', { class: 'csr-slot' }),
      ]),
    ]);
  }

  async function archiveEntry(e, on) {
    try {
      await apiPost('/api/bank/' + encodeURIComponent(e.id) + '/archive',
                    { archived: !!on });
      e.archived = !!on;
      toast(on ? 'Archived \u201c' + (e.name || e.id) + '\u201d. It is kept '
                 + 'in the Event Bank, and listed at the bottom here.'
               : 'Back on the list.', 'ok', 5000);
      paintShelfList();
    } catch (err) { toast(err.message, 'err', 8000); }
  }

  function shelfRow(st) {
    {
      const pr = st.progress || {};
      const done = pr.left === 0 && pr.total > 0;
      const rr = openReach(st.gid, st.session, wb().tool);
      const reach = rr.ok;
      const when = curWhen(st.opened_at) || curWhen((st.updated || {}).at);
      return el('div', {
        class: 'cur-shelf-row' + (done ? ' done' : '')
               + (st.archived ? ' is-archived' : ''),
      }, [
        el('span', { class: 'csr-name', text: st.name }),
        el('span', { class: 'csr-sess',
                     text: (st.session || {}).label || st.gid }),
        el('span', { class: 'csr-n',
          text: done ? pr.total + ' ✓'
                     : pr.specified + ' / ' + pr.total }),
        el('span', { class: 'csr-who' + (st.assignee ? '' : ' none'),
                     text: st.assignee || '—' }),
        // And whether it has reached the shared database, beside when it
        // was last touched -- the shelf is where most sets are.
        el('span', { class: 'csr-when' }, [
          when || '',
          BARRY.syncState
            ? BARRY.syncState.mark('curation', st.gid + '__' + st.kind) : null,
        ].filter(Boolean)),
        el('div', { class: 'csr-acts' }, [
        // Whether its work is in the bank, as on the bench cards. The chips
        // are one cell; each button is a cell of its own (app.css).
        el('div', { class: 'csr-chips' }, [
          BARRY.setPicker ? BARRY.setPicker.bankChip(st) : null,
        ].filter(Boolean)),
        el('button', {
          class: 'btn ghost sm', text: 'Pick it up',
          title: 'Put it on the bench. Opening the recording is the '
               + 'next step, not this one — a set you cannot curate '
               + 'right now can still be claimed, named and exported.',
          onclick: () => pickUpSet(st),
        }),
        el('button', {
          class: 'btn ghost sm', text: st.archived ? 'Unarchive' : 'Archive',
          title: st.archived ? 'Put it back on the shelf'
            : 'File it away. Nothing is deleted -- every candidate and '
              + 'decision stays, and it is listed at the bottom here.',
          onclick: () => archiveSet(st, !st.archived),
        }),
        el('button', {
          class: 'btn ghost sm icon-only',
          text: '\u2192', title: !reach ? rr.why
            : 'Pick it up and go straight to the recording'
              + (rr.where === 'vacc' ? ', read off the cluster' : ''),
          disabled: reach ? null : 'disabled',
          /* Through the same pick-up as the button beside it: going
             straight to the recording is still picking it up, so it asks
             the same two questions -- un-archive this, and which version
             are you carrying on from -- rather than skipping both. */
          onclick: () => pickUpSet(st, true),
        }),
        ].filter(Boolean)),
      ]);
    }
  }

  /* ADD A SET (2026-10-20): recording, then dataset, then version, then
     onto the bench -- the same three questions in all three doors, each
     door offering its own kind (Checkup's dentate spikes, Spotter's
     discharges, Panning's pools). "For everything including Panning, when
     adding something, have it chosen by recording, and then which dataset
     to be offered as a choice with all the versions."

     It never opens the mode. The set lands on the bench, where its card
     says what it is and how far through, and Xplorefinder opens from the
     card when wanted ("not directly opening into Xplorefinder").

     A set belongs to one bank entry, so nothing is replaced: two runs on
     one recording are two sets, and a dataset that already has a set offers
     to pick that one up instead.

       door     'curate' | 'spotter' | 'panning' (default: the one showing)
       preset   { gid, entry } -- start on a recording, and a dataset
       quick    put it straight on the bench when there is nothing to
                choose: one version a set can be built from, and no set yet */
  async function newSetDialog(o) {
    const opt = o || {};
    const w = WB[opt.door] || wb();
    const base = w.kind || 'ds';
    const noun = w.noun || 'events';
    /* Wait for the registry rather than reading whatever is cached: it is a
       seconds-long fetch on a share, and reading it early gave an empty
       list -- reported as "no recordings are registered" to somebody with a
       recording open. */
    if (!(cur && cur.registry)) {
      toast('Reading the recording registry\u2026', null, 2500);
      await loadCuration();
    }
    const reg = ((cur || {}).registry || {}).tree || [];
    const rows = BARRY.ui.natSort(
      reg.flatMap((p) => p.mice.flatMap((m) => m.sessions)),
      (r) => r.label || r.gid);
    if (!rows.length) {
      toast((cur && cur.registry)
        ? 'The recording registry is empty \u2014 no recording has been '
          + 'opened on this machine yet. Open one in Xplorefinder and it '
          + 'will be registered.'
        : 'Could not read the recording registry'
          + ((cur || {}).error ? ': ' + cur.error : '.')
          + ' Nothing can be picked until it answers.', 'err', 9000);
      return false;
    }

    // Which recordings have a dataset of this kind banked -- not counting
    // what a test harness left behind, which is offered nowhere.
    const harness = (e) => /harness/i.test([((e.added || {}).by || ''),
      e.name || '', e.pipeline || ((e.source || {}).pipeline || '')].join(' '));
    const has = new Set();
    try {
      const b = await api('/api/bank');
      for (const e of (b.entries || [])) {
        if (e.gid && e.type === base && !harness(e)) has.add(e.gid);
      }
    } catch (e) { /* every recording is offered; the next step says */ }

    const pre = opt.preset || {};
    let gid = pre.gid
      || (rows.find((r) => r.reachable && has.has(r.gid))
          || rows.find((r) => has.has(r.gid)) || {}).gid || null;
    let wantEntry = pre.entry || null;
    let info = null;            // what is banked for the chosen recording
    let entry = null;
    let ver = null;

    const body = el('div', { class: 'mb ncs' });
    const okBtn = el('button', { class: 'btn', text: 'Put on the bench',
                                 disabled: 'disabled' });

    const ents = () => BARRY.ui.natSort(
      ((info && info.entries) || []).filter((e) => e.kind === base && !e.test),
      (e) => [e.name || '', e.at || '']);
    const nTests = () => ((info && info.entries) || [])
      .filter((e) => e.kind === base && e.test).length;
    // The set that stands for a dataset: its own, or an older one started
    // from it.
    const setOf = (e) => (((info && info.existing) || []).find((x) =>
      BARRY.ui.kindBase(x.kind) === base
      && (BARRY.ui.kindEntry(x.kind) === e.id
          || (!BARRY.ui.kindEntry(x.kind)
              && (x.source || {}).bank_entry === e.id)))) || null;
    const firstUsable = (e) => ((e && e.versions) || [])
      .find((v) => v.usable && !v.archived)
      || ((e && e.versions) || []).find((v) => v.usable) || null;

    const recPick = BARRY.ui.pickRecording({
      rows,
      value: gid,
      usable: (r) => (has.has(r.gid) ? true
        : 'Nothing for ' + w.title + ' is banked against this recording '
          + 'yet. ' + (w.from || '')),
      emptyText: 'Nothing for ' + w.title + ' is banked against any '
               + 'recording yet. ' + (w.from || ''),
      onpick: (r) => {
        gid = r.gid; entry = null; ver = null; wantEntry = null; load();
      },
    });

    const load = async () => {
      info = null;
      paint();
      if (!gid) { info = { entries: [], existing: [] }; paint(); return; }
      try {
        info = await api('/api/curation/for-recording/'
                         + encodeURIComponent(gid));
      } catch (e) {
        info = { entries: [], existing: [], error: e.message };
      }
      const es = ents();
      const live = es.filter((e) => !e.archived);
      entry = es.find((e) => e.id === wantEntry)
        || (live.length === 1 ? live[0] : null);
      ver = entry ? firstUsable(entry) : null;
      // Quick: nothing to choose -- its set is there already, or there is
      // one version a set can be built from -- so straight to the bench.
      if (opt.quick && !shown && entry && (setOf(entry)
          || (entry.versions || []).filter((v) => v.usable).length === 1)) {
        await go();
        return;
      }
      paint();
    };

    const paint = () => {
      body.innerHTML = '';
      body.appendChild(recPick);
      if (!gid) { okBtn.disabled = 'disabled'; return; }
      if (!info) {
        body.appendChild(el('p', { class: 'hint',
          text: 'Reading what is banked for it\u2026' }));
        okBtn.disabled = 'disabled';
        return;
      }
      if (info.error) {
        body.appendChild(el('p', { class: 'confirm-sub warn',
                                   text: info.error }));
        okBtn.disabled = 'disabled';
        return;
      }
      const es = ents();
      if (!es.length) {
        body.appendChild(el('p', { class: 'confirm-msg',
          text: 'Nothing for ' + w.title + ' is banked against this '
              + 'recording, so there is nothing to work from. '
              + (w.from || '') }));
        okBtn.disabled = 'disabled';
        return;
      }

      body.appendChild(el('div', { class: 'section-label', text: 'Dataset' }));
      const list = el('div', { class: 'bm-list' });
      const rowOf = (e) => {
        const st = setOf(e);
        const pr = (st && st.progress) || {};
        const nv = (e.versions || []).length;
        return el('label', {
          class: 'bm-row' + (entry && entry.id === e.id ? ' on' : '')
                 + (e.archived ? ' is-archived' : ''),
        }, [
          el('input', { type: 'radio', name: 'ncsEntry',
            checked: entry && entry.id === e.id ? 'checked' : null,
            onchange: () => {
              entry = e; wantEntry = e.id; ver = firstUsable(e); paint();
            } }),
          el('span', { class: 'mk-name', text: e.name || 'unnamed' }),
          BARRY.ui.producerChip(e.source, e.kind),
          el('span', { class: 'person-what',
                       text: (e.n || 0).toLocaleString() + ' ' + noun
                           + '  \u00b7  ' + nv + ' version'
                           + (nv === 1 ? '' : 's')
                           + (e.by ? '  \u00b7  ' + e.by : '') }),
          st ? BARRY.ui.chip((st.open ? 'on the bench' : 'has its set')
                             + ' \u00b7 ' + (pr.specified || 0) + ' of '
                             + (pr.total || 0) + ' decided',
                             { flag: true, kind: 'ok' }) : null,
        ].filter(Boolean));
      };
      const [live, gone] = BARRY.ui.splitArchived(es, (e) => e.archived);
      for (const e of live) list.appendChild(rowOf(e));
      const tail = BARRY.ui.archivedTail({
        key: 'ncs-' + base, items: gone, noun: ['dataset', 'datasets'],
        render: (xs) => xs.map(rowOf), onToggle: () => paint(),
        forceOpen: !!(entry && entry.archived),
      });
      if (tail) list.appendChild(tail);
      body.appendChild(list);
      if (nTests()) {
        body.appendChild(el('p', { class: 'hint quiet',
          text: nTests() + ' left behind by test harnesses '
              + (nTests() === 1 ? 'is' : 'are') + ' not shown.' }));
      }

      if (!entry) {
        okBtn.textContent = 'Put on the bench';
        okBtn.disabled = 'disabled';
        return;
      }
      const st = setOf(entry);
      if (st) {
        const pr = st.progress || {};
        body.appendChild(el('p', { class: 'confirm-msg',
          text: 'This dataset already has its set, \u201c'
              + (st.name || entry.name || '') + '\u201d \u2014 '
              + (pr.specified || 0) + ' of ' + (pr.total || 0) + ' decided'
              + (st.assignee ? ', ' + st.assignee + '\u2019s' : '')
              + '. ' + (st.open ? 'It is on the bench.'
                                : 'Picking it up puts it on the bench.')
              + ' Nothing is replaced. To work from another version, use '
              + 'Version on its card.' }));
        okBtn.textContent = st.open ? 'Show it on the bench' : 'Pick it up';
        okBtn.disabled = null;
        return;
      }

      body.appendChild(el('div', { class: 'section-label', text: 'Version' }));
      const names = entry.label_names || {};
      const nameOf = (k) => names[k] || (k === 'unspecified' ? 'undecided' : k);
      /* Every version, chosen by id: the stored number repeats when two
         machines both mint the next one, so `ver.v === v.v` lit two rows
         and sent an ambiguous number. */
      body.appendChild(el('div', { class: 'ncs-vers' }, [BARRY.ui.versionTree({
        producer: entry.source, producerType: entry.kind,
        versions: entry.versions || [],
        idOf: (v) => (v.id != null ? v.id : 'v' + v.v),
        value: ver ? (ver.id != null ? ver.id : 'v' + ver.v) : undefined,
        disabled: (v) => (v.usable ? null : 'no snapshot kept \u2014 a set '
                                          + 'cannot be built from it'),
        state: (v) => [v.imported ? 'the detector' : null,
                       v.archived ? 'archived' : null].filter(Boolean),
        notes: (v) => Object.keys(v.by_label || {})
          .sort((a, b) => v.by_label[b] - v.by_label[a])
          .map((k) => nameOf(k) + ' ' + v.by_label[k]).join('  \u00b7  ')
          || ((v.n || 0) + ' ' + noun),
        onpick: (v) => { ver = v; paint(); },
      })]));

      if (ver) {
        const decided = Object.keys(ver.by_label || {})
          .filter((k) => k !== 'unspecified')
          .reduce((n, k) => n + ver.by_label[k], 0);
        body.appendChild(el('p', { class: 'confirm-msg',
          text: 'The set will hold ' + (ver.n || 0) + ' ' + noun
              + (decided ? ', ' + decided + ' of them already decided as of '
                           + BARRY.ui.versionLabel(ver) + '.'
                         : ', none decided \u2014 a fresh pass.')
              + ' It goes on the bench; open it from there.' }));
        if (ver.note) {
          body.appendChild(el('p', { class: 'hint', text: '\u201c'
                                     + ver.note + '\u201d' }));
        }
      }
      okBtn.textContent = 'Put on the bench';
      okBtn.disabled = ver ? null : 'disabled';
    };

    let shown = false;
    let went = false;
    const go = async () => {
      if (!entry) return;
      went = true;
      const st = setOf(entry);
      okBtn.disabled = 'disabled';
      try {
        let kind;
        if (st) {
          kind = st.kind;
        } else {
          if (!ver) { okBtn.disabled = null; return; }
          const res = await apiPost('/api/curation/from-bank', {
            gid, kind: base, entry: entry.id,
            // By id where there is one (the route resolves a ref).
            version: ver.id != null ? ver.id : ver.v,
            open: true,
          });
          kind = res.kind;
          const pr = res.progress || {};
          toast('On the bench: \u201c' + ((res.set || {}).name || entry.name)
                + '\u201d from ' + BARRY.ui.versionLabel(ver) + ' \u2014 '
                + (pr.total || 0) + ' ' + noun + ', ' + (pr.left || 0)
                + ' to decide. Open it from its card when you want to look.',
                'ok', 8000);
        }
        if (shown) closeModal();
        await benchShow(w, gid, kind, !!st);
      } catch (e) {
        // Made by somebody else a moment ago: that set is this dataset's.
        const d = e && e.data;
        if (d && d.exists && d.kind) {
          if (shown) closeModal();
          await benchShow(w, gid, d.kind, true);
          return;
        }
        went = false;
        toast(e.message, 'err', 9000);
        okBtn.disabled = null;
      }
    };
    okBtn.onclick = go;

    const showIt = (sub) => {
      shown = true;
      showModal(el('div', { class: 'ncs-modal' }, [
        el('div', { class: 'mh' }, [
          el('h3', { text: 'Add a set to ' + w.title }),
          el('span', { class: 'sub', text: sub }),
          el('div', { class: 'spacer' }),
          el('button', { class: 'close-x', onclick: closeModal,
            title: 'Close',
            html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
        ]),
        body,
        BARRY.ui.modalFoot(null, [
          el('button', { class: 'btn ghost', text: 'Cancel',
                         onclick: closeModal }),
          okBtn,
        ]),
      ]));
    };
    if (!opt.quick) showIt('recording, dataset, version \u2014 onto the bench');
    await load();
    // Quick, but there was a choice to make after all: ask.
    if (opt.quick && !shown && !went) {
      showIt('which version to work from');
      paint();
    }
    return true;
  }

  /* A set onto the bench of its door, the door on screen, and the card
     lit so it is found. */
  async function benchShow(w, gid, kind, pickUp) {
    curStale = true;
    delete curStart[w.kind];
    if (q.tool !== w.tool) pickTool(w.tool, (bundleOf(w.tool) || {}).id);
    await loadCuration();
    const st = ((cur && cur.sets) || []).find(
      (x) => x.gid === gid && x.kind === kind);
    if (st && pickUp && !st.open) await openSet(st, true);
    else renderCuration();
    const card = Array.from(document.querySelectorAll('#curBench .cur-set'))
      .find((n) => n.dataset.gid === gid && n.dataset.kind === kind);
    if (card) {
      try { card.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
      catch (e) { /* an old engine scrolls without the options */ }
      if (BARRY.motion && BARRY.motion.land) BARRY.motion.land(card);
    }
    return st || null;
  }

  /* ---- the workbench verbs ---- */
  /* `based` is which banked version this pass is being picked up FROM.
     It is the stored integer, not the lineage name: the cloud table's
     `version` column is an integer and the sync casts to int, so the number
     is the identity and "1.1" is worked out from it. Null leaves the server
     to default to the newest, which is what happened before this was
     askable. */
  async function openSet(st, on, unarchive, based) {
    /* Archiving is a decision, so un-doing it is one too. Picking up an
       archived set used to un-archive it silently -- "archived it and could
       still just open it" was the report. */
    if (on && st.archived && !unarchive) {
      const ok = await BARRY.confirm(
        'Un-archive "' + (st.name || st.gid) + '"?',
        'It is archived, which is how a set is filed away. Putting it on '
        + 'the bench means taking it back out \u2014 a set cannot be both '
        + 'archived and in use, or it shows up in neither list.',
        'Un-archive and pick it up');
      if (!ok) return false;
      return openSet(st, true, true, based);
    }

    /* On screen first. The round trip is seconds on a network share, and
       the answer is already known locally -- the decision was made by the
       click. Rolled back and said out loud if the write fails. */
    const was = { open: st.open, archived: st.archived,
                  opened_at: st.opened_at, closed_at: st.closed_at,
                  assignee: st.assignee };
    st.open = !!on;
    if (on) {
      st.opened_at = new Date().toISOString();
      st.archived = false;
      if (!st.assignee && BARRY.profile && BARRY.profile.who()) {
        st.assignee = BARRY.profile.who();
      }
    } else {
      st.closed_at = new Date().toISOString();
    }
    renderCuration();
    const pr = st.progress || {};
    if (on) {
      toast('On the bench' + (st.assignee ? ', assigned to '
            + st.assignee : '') + '. It stays there until you put it '
            + 'down.', 'ok', 4500);
    } else {
      toast('Put down. ' + (pr.specified || 0) + ' decision(s) are saved '
            + 'and it is on the shelf whenever you want it back.',
            'ok', 5000);
    }

    try {
      const res = await apiPost(
        '/api/curation/' + encodeURIComponent(st.gid) + '/'
        + encodeURIComponent(st.kind) + '/open',
        { open: !!on, unarchive: !!unarchive,
          based_on: (based === null || based === undefined)
            ? undefined : based });
      // The server's answer is the truth; the guess above only had to be
      // fast. They agree in every ordinary case.
      /* The summary does not carry `history`, and losing it would empty the
         version button on the card that was just picked up. */
      if (res.set) {
        const keep = st.history;
        Object.assign(st, res.set);
        if (keep && !st.history) st.history = keep;
        renderCuration();
      }
    } catch (e) {
      Object.assign(st, was);
      renderCuration();
      toast('That did not save: ' + (e && e.message || e), 'err', 8000);
      return false;
    }
    return true;
  }

  /* ==================================================================
     Which version a sitting works from
     ==================================================================
     A curation set is one row per recording per kind, but the bank behind
     it keeps every pass anybody ever banked -- seven of them on entry
     7d5fa32206b4. Picking the set up used to say nothing about which of
     those the sitting was carrying on from, so banking always landed on top
     of whatever was newest. That is right until somebody goes back to an
     earlier pass on purpose, and then it silently buries the work that came
     after it.

     So both doors ask. Picking up records where the next bank lands, and
     puts that version's decisions on the bench if it is not the one the set
     already reflects. Switching while it is on the bench always does both:
     the current version goes down, the chosen one comes up.
     ================================================================== */

  /* Put that version's decisions onto the set. Restore is the one route
     that does it, and it records what the set is now based on as well --
     so the next bank lands as a pass on that version rather than on top of
     whatever happened to be newest. */
  async function restoreVersion(st, pick) {
    let res;
    try {
      res = await apiPost('/api/curation/' + encodeURIComponent(st.gid) + '/'
                          + encodeURIComponent(st.kind) + '/restore',
                          { entry: pick.entry,
                            // By id: the number repeats (the route resolves a ref).
                            version: (pick.row && pick.row.id != null) ? pick.row.id : pick.v });
    } catch (e) {
      toast('Could not work from v' + pick.name + ': '
            + (e && e.message || e), 'err', 9000);
      return null;
    }
    toast('Working from v' + pick.name + '. '
          + (res.changed ? res.changed + ' decision(s) changed to match it'
                         : 'Nothing on the set had to change')
          + (res.missing
              ? ', ' + res.missing + ' of its candidate(s) are not in this '
                + 'set any more' : '')
          + '. ' + (pick.branches
              ? 'Banking from here starts a new line at v' + pick.next + '.'
              : 'Banking from here writes v' + pick.next + '.'),
          'ok', 9000);
    BARRY.activity.log('curation.version',
                       { gid: st.gid, kind: st.kind, entry: pick.entry,
                         version: pick.v, label: pick.name,
                         changed: res.changed });
    return res;
  }

  /* Off the shelf and onto the bench, having said which pass it carries on
     from. `andEnter` is the arrow beside it: same question, then straight
     into the recording. */
  async function pickUpSet(st, andEnter) {
    let pick = null;
    if (BARRY.vers.askable(st.history)) {
      pick = await BARRY.pickVersion(st.history, {
        title: 'Which version to work from',
        sub: (st.name || st.gid) + '  \u00b7  '
           + ((st.session || {}).label || st.gid),
        lead: 'Picking it up says which banked pass this sitting carries on '
            + 'from. That is what decides where the next bank lands \u2014 '
            + 'on the end of a line, or as a new line off an older pass.',
        labels: st.labels || [],
        mode: 'pickup',
        verb: 'Pick it up from', okLabel: 'Pick it up',
      });
      if (!pick) return false;      // asked, and called off
    }
    // The version by its id: numbers repeat when two machines both mint
    // the next one, and the bank refuses to guess (2026-10-20).
    const got = await openSet(st, true, false, pick
      ? ((pick.row && pick.row.id != null) ? pick.row.id : pick.v) : null);
    if (!got) return false;
    /* Before entering, not after: the panel reads the set when it opens, and
       restoring underneath it would leave the decisions on screen belonging
       to the version that was just put down. */
    if (pick && pick.restores) {
      await restoreVersion(st, pick);
      await loadCuration();
    }
    if (andEnter) wbEnter(st);
    return true;
  }

  /* Switching while it is on the bench. Destructive to what is there, so it
     says so with the count before it happens, and the button is the danger
     one. If the panel is actually open on this set it does it, because it
     has to redraw the candidates and the marks afterwards. */
  async function switchSetVersion(st) {
    const live = BARRY.curate && BARRY.curate.active && BARRY.curate.state;
    if (live && live.gid === st.gid && live.kind === st.kind) {
      await BARRY.curate.switchVersion();
      await loadCuration();
      return;
    }
    if (!BARRY.vers.askable(st.history)) {
      toast('There is only one banked version of this set, so there is '
            + 'nothing to switch between.', null, 6000);
      return;
    }
    const pick = await BARRY.pickVersion(st.history, {
      title: 'Switch to another version',
      sub: (st.name || st.gid) + '  \u00b7  '
         + ((st.session || {}).label || st.gid),
      lead: 'Switching puts the current version down and picks the chosen '
          + 'one up. The decisions on the set become that version\u2019s, '
          + 'and everything decided after it is written onto that line. '
          + 'Nothing is deleted \u2014 every version stays in the bank.',
      labels: st.labels || [],
      mode: 'switch',
      danger: true, verb: 'Switch to', okLabel: 'Switch',
    });
    if (!pick) return;
    const res = await restoreVersion(st, pick);
    if (res) await loadCuration();
  }

  async function closeAllSets() {
    const open = curOpen();
    const ok = await BARRY.confirm(
      'Clear the bench?',
      'This puts down ' + open.length + ' set(s). Nothing is archived, '
      + 'deleted or unbanked, and no decision is lost — they were all '
      + 'written as they were made. Each one goes back on the shelf.',
      'Put down ' + open.length + ' set(s)');
    if (!ok) return;
    /* Spotter's and Panning's own sets only: the server's close-all puts
       down every set of every kind, Checkup's included. */
    if (wb().kinds) {
      let n = 0;
      for (const st of open) {
        try {
          await apiPost('/api/curation/' + encodeURIComponent(st.gid) + '/'
                        + encodeURIComponent(st.kind) + '/open', { open: false });
          n += 1;
        } catch (e) { toast(e.message, 'err', 8000); }
      }
      toast('Bench cleared \u2014 ' + n + ' set(s) put down.', 'ok', 5000);
      await loadCuration();
      return;
    }
    try {
      const res = await apiPost('/api/curation/close-all', {});
      toast('Bench cleared — ' + res.n + ' set(s) put down.', 'ok', 5000);
      await loadCuration();
    } catch (e) { toast(e.message, 'err', 8000); }
  }

  /* Who has worked on this repo, cached for the session. Compiled by the
     server from the profiles, the decisions and the bank, so it is exactly
     the set of names already stamped on the data. */
  let roster = null;

  async function people(force) {
    if (roster && !force) return roster;
    try {
      roster = await api('/api/people');
    } catch (e) {
      roster = { people: [], not_people: [], me: null };
    }
    return roster;
  }

  /* Pick an owner from the people already here, rather than retyping a
     name. A free-text box is how one person becomes three -- "Rain",
     "rain" and "Rain " are three owners to any list that groups by name. */
  async function assignSet(st) {
    const r = await people();
    let chosen = st.assignee || null;
    const list = el('div', { class: 'bm-list tall person-list' });
    const fresh = el('input', {
      type: 'text', class: 'cur-search',
      placeholder: 'Somebody not listed yet\u2014 type a name',
    });

    const paint = () => {
      list.innerHTML = '';
      /* Archived people are not offered. Except the one who already has
         this set: hiding a current owner would leave a set assigned to a
         name that is nowhere on screen, and no way to hand it on. */
      const rows = (r.people || []).filter(
        (x) => !x.archived || x.name === st.assignee);
      const away = (r.people || []).filter(
        (x) => x.archived && x.name !== st.assignee).length;
      if (!rows.length) {
        list.appendChild(el('div', { class: 'hint',
          text: 'Nobody is on the roster yet. Jarvis builds it from the '
              + 'names already stamped on decisions and bank entries, so '
              + 'it fills in as work happens \u2014 or type one below.' }));
      }
      /* Nobody is a real answer, and the only way to hand a set back. */
      list.appendChild(el('label', {
        class: 'bm-row' + (chosen === null ? ' on' : ''),
      }, [
        el('input', { type: 'radio', name: 'whose',
          checked: chosen === null ? 'checked' : null,
          onchange: () => { chosen = null; paint(); } }),
        el('span', { class: 'mk-name', text: 'Nobody' }),
        el('span', { class: 'flagchip', text: 'unassigned' }),
      ]));
      for (const p of rows) {
        const what = Object.keys(p.counts || {})
          .map((k) => p.counts[k] + ' ' + k).join('  \u00b7  ');
        list.appendChild(el('label', {
          class: 'bm-row' + (chosen === p.name ? ' on' : ''),
        }, [
          el('input', { type: 'radio', name: 'whose',
            checked: chosen === p.name ? 'checked' : null,
            onchange: () => { chosen = p.name; paint(); } }),
          el('span', { class: 'mk-name', text: p.name }),
          what ? el('span', { class: 'person-what', text: what }) : null,
          p.me ? el('span', { class: 'flagchip good', text: 'you' }) : null,
          p.archived
            ? el('span', { class: 'flagchip', text: 'archived' }) : null,
        ].filter(Boolean)));
      }
      /* Said, not silently dropped. A picker that is quietly shorter than
         the roster is a picker somebody will scroll looking for a name. */
      if (away) {
        list.appendChild(el('div', { class: 'hint',
          text: away + ' archived ' + (away === 1 ? 'person is' : 'people are')
              + ' not listed. They are still on every record they are on — '
              + 'un-archive them in Profile to offer them work again.' }));
      }
    };
    paint();

    /* Optimistic, and the modal closes first on purpose here -- picking a
       name from a list is a decision, and the list has served its purpose the
       moment you make it.

       What was wrong was what happened next: nothing, for a round trip, with
       the card still showing the previous owner. Whoever you picked goes on
       the card immediately now, and only an actual failure takes it off. */
    const save = async (who) => {
      const was = st.assignee;
      st.assignee = who || null;
      closeModal();
      renderCuration();
      toast(who ? 'Assigned to ' + who + '.' : 'Handed back \u2014 nobody '
            + 'has this one now.', 'ok', 4000);
      try {
        const res = await apiPost(
          '/api/curation/' + encodeURIComponent(st.gid) + '/'
          + encodeURIComponent(st.kind) + '/assign', { who: who });
        if (res.set) { Object.assign(st, res.set); renderCuration(); }
      } catch (e) {
        st.assignee = was;
        renderCuration();
        toast('That did not save: ' + e.message, 'err', 8000);
      }
    };

    showModal(el('div', {}, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'Who is working on this?' }),
        el('span', { class: 'sub', text: st.name || st.gid }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: closeModal,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/></svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        list,
        el('div', { class: 'section-label', text: 'Or add somebody' }),
        el('div', { class: 'person-add' }, [
          fresh,
          el('button', {
            class: 'btn ghost sm', text: 'Add and assign',
            onclick: async () => {
              const name = (fresh.value || '').trim();
              if (!name) { toast('Type a name first.', 'err', 3000); return; }
              try {
                roster = await apiPost('/api/people/add', { name: name });
              } catch (e) { toast(e.message, 'err', 8000); return; }
              save(name);
            },
          }),
        ]),
        (r.not_people || []).length
          ? el('p', { class: 'hint',
              text: 'Not offered, because they are a record of where a '
                  + 'decision came from rather than somebody who can be '
                  + 'asked about it: '
                  + r.not_people.map((p) => p.name).join(', ') + '.' })
          : null,
      ].filter(Boolean)),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn ghost', text: 'Cancel',
                       onclick: closeModal }),
        el('button', { class: 'btn', text: 'Assign',
                       onclick: () => save(chosen) }),
      ]),
    ]));
  }

  /* The comment here used to say "change the list now rather than after a
     round trip" and sat directly underneath the await, so it did neither: the
     card stayed put for the whole request and was then followed by a reload
     of every curation set and the entire recording registry -- the second of
     which is over a second on a network share -- to carry one boolean.

     Now it means it. The card moves on the click, the write follows, and a
     failure puts it back and says so rather than leaving the list claiming
     something that did not happen. Same shape as openSet just below. */
  async function archiveSet(st, on) {
    const was = st.archived;
    st.archived = on;
    // The whole panel, not just the list: the filter chips carry counts, and
    // archiving changes what those counts are counting.
    renderCuration();
    toast(on ? 'Archived. It is still there \u2014 the Archived filter '
               + 'brings it back.'
             : 'Back in the list.', 'ok', 5000);
    try {
      const res = await apiPost(
        '/api/curation/' + encodeURIComponent(st.gid) + '/'
        + encodeURIComponent(st.kind) + '/archive', { archived: on });
      // Reconcile with what the server actually stored, in case it knows
      // something this copy did not -- but no reload: one field changed.
      if (res && res.set) { Object.assign(st, res.set); renderCuration(); }
    } catch (e) {
      st.archived = was;
      renderCuration();
      toast('That did not save: ' + e.message, 'err', 8000);
    }
  }


  /* Browse the bank and pick something, rather than being handed
     entries[0].

     Opens filtered to the kind being curated and searched for the recording
     picked above -- both clearable, because "show me what else is in here"
     is a reasonable thing to want and the old flow made it impossible.
     Resolves to the full entry, or null if cancelled. */


  /* Through Checkup's own banking, which is the shared bank dialog
     (constitution §6e) with the mix and the history on it -- the same path
     Spotter takes. This asked "Who is banking these?" in a prompt every
     time, then banked without showing what it was about to write or which
     version it would become. */
  async function bankSet(st) {
    if (!(BARRY.curate && BARRY.curate.bankAt)) return;
    const pr = st.progress || {};
    await BARRY.curate.bankAt({
      gid: st.gid, kind: st.kind, name: st.name,
      labels: st.labels || [],
      progress: { by_label: pr.by_label || {}, left: pr.left || 0 },
    });
  }


  /* ==================================================================
     StrataScope
     ================================================================== */
  let strata = null;

  async function loadStrata() {
    const l = (q.tool === 'strata' && !strata)
      ? tkLoading('StrataScope', ['reading the layer sheets',
                                  'reading the recording registry'])
      : null;
    try {
      strata = await api('/api/layers');
      if (l) l.step('reading the recording registry');
      strata.registry = await registry();
      // What the cluster can read, for the open buttons (`openReach`).
      if (BARRY.vacc && BARRY.vacc.loadKnows) {
        try { await BARRY.vacc.loadKnows(); } catch (e) { /* the drive answer stands */ }
      }
    } catch (e) {
      strata = { error: e.message, sheets: [], regions: [] };
    }
    // See `loadCuration`: an eight-second registry read that lands after the
    // tool has changed must not paint over what is there now.
    if (q.tool !== 'strata') return;
    renderStrata();
  }

  /* How the shelf is being looked at. Held here, not read off the DOM, so a
     re-render cannot lose a half-typed search. */
  const strataQ = { text: '', show: 'all', shelf: false };

  const STRATA_SHOWS = [
    ['all', 'All'],
    ['left', 'Unfinished'],
    ['done', 'Finished'],
    ['mine', 'Mine'],
    ['archived', 'Archived'],
  ];

  const strataSheets = () => (strata && strata.sheets) || [];
  const strataOpen = () => strataSheets()
    .filter((sh) => sh.open && !sh.archived);

  /* The sheets on the shelf that match what is being asked for. Everything
     not on the bench, the finished ones included -- being done is a reason
     not to be in the way, not a reason to be hidden. */
  function strataShelf() {
    const me = (BARRY.profile && BARRY.profile.who && BARRY.profile.who())
      || '';
    const q = strataQ.text.trim().toLowerCase();
    const words = q ? q.split(/\s+/) : [];
    return strataSheets().filter((sh) => {
      if (sh.open && !sh.archived) return false;
      const pr = sh.progress || {};
      if (strataQ.show === 'left' && !(pr.left > 0)) return false;
      if (strataQ.show === 'done' && !(pr.left === 0 && pr.total > 0)) {
        return false;
      }
      if (strataQ.show === 'mine'
          && (sh.assignee || '').toLowerCase() !== me.toLowerCase()) {
        return false;
      }
      /* Archived sheets are out of the way unless asked for. Archiving still
         means "I am done thinking about this at all", which is a stronger
         statement than putting it down. */
      if (strataQ.show === 'archived') {
        if (!sh.archived) return false;
      } else if (sh.archived) {
        return false;
      }
      if (!words.length) return true;
      const hay = [sh.name, sh.session_label, sh.gid, sh.assignee]
        .filter(Boolean).join(' ').toLowerCase();
      return words.every((w) => hay.indexOf(w) >= 0);
    });
  }

  async function strataAct(gid, what, body) {
    try {
      const got = await apiPost('/api/layers/' + encodeURIComponent(gid)
                                + '/' + what, body || {});
      if (got && got.sheet) {
        const at = strataSheets().findIndex((x) => x.gid === gid);
        if (at >= 0) Object.assign(strata.sheets[at], got.sheet);
      }
      renderStrata();
      return got;
    } catch (e) {
      toast(e.message, 'err', 6000);
      return null;
    }
  }

  const pickUpSheet = (sh, andOpen) => strataAct(sh.gid, 'open', { on: true })
    .then((got) => { if (got && andOpen) BARRY.strata.enter(sh.gid); });
  const putDownSheet = (sh) => strataAct(sh.gid, 'open', { on: false });

  async function archiveSheet(sh) {
    if (!sh.archived) {
      const ok = await BARRY.confirm(
        'File away the layer sheet for ' + (sh.session_label || sh.gid) + '?',
        'It comes off the bench and off the shelf, so it stops being offered. '
        + 'Nothing is lost: the labels, the version history and the snapshots '
        + 'all stay, and it can be taken back out at any time.',
        'File it away');
      if (!ok) return;
    }
    strataAct(sh.gid, 'archive', { on: !sh.archived });
  }

  async function unarchiveAndPickUp(sh) {
    const ok = await BARRY.confirm(
      'Take ' + (sh.session_label || sh.gid) + ' back out?',
      'It is archived. Picking it up puts it back on the bench and takes it '
      + 'out of the archive.',
      'Take it out and pick it up');
    if (!ok) return;
    strataAct(sh.gid, 'open', { on: true, unarchive: true });
  }

  /* The name, edited where it is shown.

     There is no text-prompt helper in this codebase and one field does not
     justify inventing a dialog for it, so the title becomes an input and
     goes back to being a title. Empty means "call it after the
     recording". */
  function nameCell(sh) {
    const shown = sh.name || sh.session_label || sh.gid;
    const strong = el('strong', {
      class: 'sheet-name', text: shown, tabindex: '0',
      title: 'Click to name this work set. A sheet is about a recording, but '
           + 'the work is not always "the recording" — it can be the '
           + 'second pass after the probe map was fixed.',
      onclick: (e) => edit(e.currentTarget),
      onkeydown: (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          edit(e.currentTarget);
        }
      },
    });

    function edit(node) {
      const box = el('input', {
        class: 'inp sm sheet-name-edit', value: sh.name || '',
        placeholder: sh.session_label || sh.gid,
      });
      let done = false;
      const finish = (save) => {
        if (done) return;
        done = true;
        const want = box.value.trim();
        if (save && want !== (sh.name || '')) {
          strataAct(sh.gid, 'rename', { name: want });
        } else {
          renderStrata();
        }
      };
      box.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); finish(true); }
        if (e.key === 'Escape') { e.preventDefault(); finish(false); }
      });
      box.addEventListener('blur', () => finish(true));
      node.replaceWith(box);
      box.focus();
      box.select();
    }

    return strong;
  }
  /* There is no delete here.

     There was, and it took a confirmation dialog three paragraphs long to
     explain everything it would not destroy -- which is the tell. The
     labelling IS the data; a work set is a statement about who is working
     on what. So the verbs are Close (off the bench) and File away (off the
     shelf as well), and neither touches a label, a version or a snapshot.

     `/api/layers/<gid>/delete` still exists, because an import that landed
     a sheet on the wrong recording has to be undoable. It is not something
     a card offers you in passing. */

  async function closeAllSheets() {
    const n = strataOpen().length;
    const ok = await BARRY.confirm(
      'Clear the bench?',
      'Closes all ' + n + ' open work set' + (n === 1 ? '' : 's') + '. '
      + 'Nothing is archived, deleted or unlabelled — every label was '
      + 'written as it was made. Each one goes back on the shelf.',
      'Close them all');
    if (!ok) return;
    try {
      await apiPost('/api/layers/close-all', {});
      strata = null;
      loadStrata();
    } catch (e) { toast(e.message, 'err', 6000); }
  }

  /* One sheet, as a card. The same shape as a curation set, because it is
     the same kind of thing: a pile of decisions about one recording that
     somebody is or is not working on. */
  /* How far StrataScope's steps have got on a sheet, in one chip: signed
     off, or which of 0-3 are accepted. Nothing for a sheet labelled by hand
     only -- most of the shelf -- so the chip means something when it is
     there. */
  function stepsChip(sh) {
    const st = (sh.strata || {});
    if ((st.signed || {}).at) {
      return el('span', { class: 'hk-chip', text: 'signed off',
                          title: 'Signed off by ' + (st.signed.by || '?')
                               + ' (v' + st.signed.v + ')' });
    }
    const steps = st.steps || {};
    const done = ['0', '1', '2', '3'].filter(
      (k) => (steps[k] || {}).status === 'done');
    if (!done.length) return null;
    return el('span', { class: 'hk-chip', text: 'steps ' + done.join(' ')
                        + ' done',
                        title: 'StrataScope steps accepted: '
                             + done.join(', ') });
  }

  function sheetCard(sh, onBench) {
    const pr = sh.progress || {};
    const done = pr.left === 0 && pr.total > 0;
    // StrataScope opens it the same way Checkup does: here, or the link.
    const rr = openReach(sh.gid, sh.session, 'strata');
    const reach = rr.ok;
    const when = curWhen(onBench ? sh.opened_at : (sh.updated || {}).at);

    const acts = [
      el('button', {
        class: 'btn sm',
        text: pr.left ? 'Continue…' : 'Review…',
        disabled: reach ? null : 'disabled',
        title: !reach ? rr.why
          : 'Open it in StrataScope'
            + (rr.where === 'vacc' ? ', read off the cluster' : ''),
        onclick: () => BARRY.strata.enter(sh.gid),
      }),
    ];
    if (onBench) {
      acts.push(el('button', {
        class: 'btn ghost sm', text: 'Close',
        title: 'Closes the work set: it comes off the bench and goes back '
             + 'on the shelf. It changes no labels, no versions and no '
             + 'snapshots \u2014 every label was written the moment you '
             + 'made it.',
        onclick: () => putDownSheet(sh),
      }));
    } else if (sh.archived) {
      acts.push(el('button', {
        class: 'btn ghost sm', text: 'Take it out…',
        title: 'Un-archive it and put it on the bench',
        onclick: () => unarchiveAndPickUp(sh),
      }));
    } else {
      acts.push(el('button', {
        class: 'btn ghost sm', text: 'Pick it up',
        title: 'Puts it on the bench. Opening the recording is separate — '
             + 'this is just saying you are working on it.',
        onclick: () => pickUpSheet(sh, false),
      }));
      acts.push(el('button', {
        class: 'btn ghost sm', text: 'Pick up and open',
        disabled: reach ? null : 'disabled',
        title: reach ? null : rr.why,
        onclick: () => pickUpSheet(sh, true),
      }));
    }
    acts.push(el('button', {
      class: 'btn ghost sm', text: 'Export CSV',
      onclick: () => window.open('/api/layers/'
        + encodeURIComponent(sh.gid) + '/export', '_blank'),
    }));
    acts.push(el('button', {
      class: 'btn ghost sm', text: sh.archived ? 'Unarchive' : 'File away',
      title: sh.archived
        ? 'Put it back on the shelf'
        : 'Off the shelf as well as off the bench. Nothing is lost.',
      onclick: () => archiveSheet(sh),
    }));

    /* The same card Checkup builds. The owner is text rather than a button
       here because a sheet cannot be handed to somebody -- there is no
       assign path for one -- but it is stated either way, including when
       nobody has it, which is the thing a bench is for saying. */
    return BARRY.ui.workbenchCard({
      gid: sh.gid,
      done: done,
      extra: onBench ? 'on-bench' : null,
      title: nameCell(sh),
      chips: [
        el('span', { class: 'hk-chip', text: 'layers' }),
        stepsChip(sh),
        sh.name && sh.session_label
          ? el('span', { class: 'cur-set-sess', text: sh.session_label }) : null,
        sh.archived ? el('span', { class: 'hk-chip', text: 'archived' }) : null,
      ].filter(Boolean),
      count: (pr.labelled || 0) + ' / ' + (pr.total || 0) + ' channels',
      owner: { name: sh.assignee || null },
      sync: { kind: 'layers', id: sh.gid },
      when: when ? (onBench ? 'picked up ' : 'last touched ') + when
                   + (sh.opened_by && onBench ? ' by ' + sh.opened_by : '')
                 : null,
      progress: pr.percent || 0,
      tally: (sh.regions || []).filter(
        (r) => (pr.by_region || {})[r.id]).map((r) => el('span', {
          class: 'cur-tally', style: '--cat:' + r.color,
          text: r.name + '  ' + pr.by_region[r.id],
        })),
      actions: acts,
    });
  }

  /* ==================================================================
     Braid

     The one tool here that decides nothing. It opens a recording in
     XploreFinder with the band-resolved power panel up, and puts a
     comodulogram of whatever window you are looking at one keystroke away.

     No bench and no sets, so this pane is a chooser and nothing else --
     there is no state to come back to, because looking does not leave any.
     ================================================================== */
  let cfcReg = null;

  /* Incisor needs the registry and nothing else -- it does its own
     estimating once a recording is chosen. The rows come from the same
     sixty-second cache every other tool uses, because reading the registry
     takes eight seconds on this lab's data. */
  /* Doppler warms the same registry cache Incisor does before painting:
     its recording picker reads it, and a picker that is empty for the first
     six seconds reads as "there are no recordings". */
  async function loadDoppler() {
    const host = document.getElementById('tkResult');
    if (host) host.style.opacity = '1';
    try {
      await registry();
    } catch (e) { /* the panel says so itself */ }
    // The tool may have changed while the registry was being read; painting
    // then would put Doppler's panel over whatever was opened instead.
    if (q.tool !== 'doppler') return;
    BARRY.doppler.paint();
  }

  /* Spotter is a mode, not a panel. This is the way in: pick a recording
     that has a banked set of IEDs on it, and enter.

     It draws the sets rather than a recording picker, because "which of the
     three runs on this recording" is the question -- the recording alone
     does not say which list you mean. */
  async function loadIncisor() {
    const host = document.getElementById('tkResult');
    if (host) host.style.opacity = '1';
    try {
      await registry();
    } catch (e) { /* the panel says so itself */ }
    if (q.tool !== 'incisor') return;
    BARRY.incisor.paint();
  }

  /* Panorama needs the registry for its recording picker and nothing
     else -- it estimates its own cost once a recording is chosen. Same
     sixty-second cache as every other tool. */
  async function loadPanorama() {
    const host = document.getElementById('tkResult');
    if (host) host.style.opacity = '1';
    try {
      await registry();
    } catch (e) { /* the panel says so itself */ }
    if (q.tool !== 'panorama') return;
    BARRY.panorama.paint();
  }

  /* Horizon needs the registry for its recording picker and nothing else,
     the same way Panorama does -- it reads a recording rather than a bank. */
  async function loadHorizon() {
    const host = document.getElementById('tkResult');
    if (host) host.style.opacity = '1';
    try {
      await registry();
    } catch (e) { /* the panel says so itself */ }
    if (q.tool !== 'horizon') return;
    BARRY.horizon.paint();
  }

  async function loadCFC() {
    renderCFC();
    cfcReg = await registry();
    renderCFC();
  }

  let cfcGid = null;

  function renderCFC() {
    const host = $('#tkResult');
    if (!host) return;
    if (q.tool !== 'cfc') return;      // see renderCuration
    host.style.opacity = '1';
    host.innerHTML = '';
    if (!cfcReg) {
      host.appendChild(el('div', { class: 'tk-loading' }, [
        stepLoader('Braid', ['reading the recording registry'])]));
      return;
    }

    const rows = ((cfcReg || {}).tree || [])
      .flatMap((p) => (p.mice || []).flatMap((m) => m.sessions || []));
    if (!cfcGid) cfcGid = (rows.find((r) => r.reachable) || rows[0] || {}).gid;
    const pick = BARRY.pickSession({
      rows, value: cfcGid,
      placeholder: 'Which recording? Type a mouse, session or date…',
      onpick: (r) => { cfcGid = r.gid; },
    });

    host.appendChild(el('div', { class: 'tk-head' }, [
      // A step of The Lookout; the number is read from the bundle.
      BARRY.ui.stepHeader({
        title: 'Braid',
        step: BARRY.ui.stepOf('cfc'),
        blurb: 'Theta, resolved into the bands it is actually made of, and '
             + 'phase-amplitude coupling for a window you choose.',
      }),
    ]));

    const card = el('div', { class: 'card' });
    card.appendChild(el('div', { class: 'section-label',
                                 text: 'Open a recording' }));
    card.appendChild(pick);
    card.appendChild(el('div', { class: 'tk-actions' }, [
      el('button', {
        class: 'btn', text: 'Open in Braid',
        onclick: () => { if (cfcGid) BARRY.cfc.enter(cfcGid); },
      }),
      el('span', { class: 'hint',
        text: 'Opens in XploreFinder with a second window for the panels.' }),
    ]));
    host.appendChild(card);

    /* What it does, said once, here. The two panels it opens are not
       obvious from their names and the second one is the whole reason the
       mode exists. */
    const what = el('div', { class: 'card' });
    what.appendChild(el('div', { class: 'section-label',
                                 text: 'What it gives you' }));
    what.appendChild(el('dl', { class: 'tk-what' }, [
      el('dt', { text: 'Theta power, band by band' }),
      el('dd', { text: 'Not one 4–12 Hz filter. Seventeen narrow bands '
                     + 'in 0.5 Hz steps, each one the mean squared envelope '
                     + 'of its own analytic signal — the same '
                     + 'definition ThetaPower.m uses in the CFC pipeline. A '
                     + 'rhythm that moves from 7 Hz to 9 Hz during a session '
                     + 'is visible as a thing that moved, which a single '
                     + 'wide filter cannot show you.' }),
      el('dt', { text: 'A comodulogram, when you ask for one' }),
      el('dd', { text: 'Phase-amplitude coupling across a grid of band '
                     + 'pairs, for the window on screen. Seconds without a '
                     + 'null, half a minute with one, so it opens its own '
                     + 'window and tells you the cost before it starts.' }),
      el('dt', { text: 'Nothing written down' }),
      el('dd', { text: 'No set is claimed, no decision is recorded, nothing '
                     + 'goes on anybody’s bench. Leave whenever you '
                     + 'like; there is nothing to put down.' }),
    ]));
    host.appendChild(what);
  }

  function renderStrata() {
    const host = $('#tkResult');
    if (!host) return;
    if (q.tool !== 'strata') return;   // see renderCuration
    host.style.opacity = '1';
    host.innerHTML = '';
    if (!strata) {
      host.appendChild(el('div', { class: 'tk-loading' }, [
        stepLoader('StrataScope', ['reading the layer sheets',
                                   'reading the recording registry'])]));
      return;
    }

    const rows = ((strata.registry || {}).tree || [])
      .flatMap((p) => (p.mice || []).flatMap((m) => m.sessions || []));
    // Same search field as the curation importer, for the same reason.
    let strataGid = (rows.find((r) => r.reachable) || rows[0] || {}).gid;
    const pick = BARRY.pickSession({
      rows, value: strataGid,
      placeholder: 'Which recording? Type a mouse, session or date…',
      onpick: (r) => { strataGid = r.gid; },
    });
    pick.id = 'strataPick';

    const open = strataOpen();

    host.appendChild(el('div', { class: 'tk-head' }, [
      el('div', {}, [
        el('h2', { text: 'StrataScope' }),
        el('p', { class: 'sub',
          text: open.length
            ? 'What you have open. It stays here until you put it down.'
            : 'Which anatomical layer each channel is sitting in. Pick a '
              + 'recording up below, or start a new sheet on the right — '
              + 'it stays on the bench until you put it down.' }),
      ]),
      el('div', { class: 'spacer' }),
      open.length > 1 ? el('button', {
        class: 'btn ghost sm', text: 'Clear the bench',
        title: 'Closes every open work set. Nothing is archived, deleted or '
             + 'unlabelled.',
        onclick: closeAllSheets,
      }) : null,
      pick,
      el('button', {
        class: 'btn', text: 'Open…',
        disabled: rows.length ? null : 'disabled',
        title: 'Opens the recording in StrataScope, making a sheet if there '
             + 'is not one yet',
        onclick: () => {
          if (!strataGid) { toast('Pick a recording first.', 'err'); return; }
          BARRY.strata.enter(strataGid);
        },
      }),
    ].filter(Boolean)));

    /* ---- the bench ---- */
    const bench = el('div', { class: 'cur-sets cur-bench', id: 'strataBench' });
    if (open.length) {
      for (const sh of open) bench.appendChild(sheetCard(sh, true));
    } else {
      bench.appendChild(el('div', { class: 'cur-bench-empty' }, [
        el('p', { text: 'Nothing open.' }),
        el('p', { class: 'hint',
          text: strataSheets().length
            ? 'Pick one up below and it stays on the bench until you put it '
              + 'down. Putting a sheet down neither saves nor loses '
              + 'anything — every label was written the moment you made it.'
            : 'No layer sheets yet. Pick a recording above and open it — a '
              + 'sheet is made the first time.' }),
      ]));
    }
    host.appendChild(bench);

    /* ---- the shelf, folded away until wanted ---- */
    const nShelf = strataSheets().filter((sh) => !sh.open && !sh.archived)
      .length;
    const nArch = strataSheets().filter((sh) => sh.archived).length;
    if (strataSheets().length) {
      host.appendChild(el('div', { class: 'cur-shelf-head' }, [
        el('button', {
          class: 'cur-shelf-toggle' + (strataQ.shelf ? ' on' : ''),
          text: (strataQ.shelf ? '▾  ' : '▸  ')
              + (open.length ? 'Pick up another sheet' : 'Pick up a sheet')
              + '  ·  ' + nShelf + ' put down'
              + (nArch ? '  ·  ' + nArch + ' archived' : ''),
          onclick: () => { strataQ.shelf = !strataQ.shelf; renderStrata(); },
        }),
      ]));
    }

    if (strataQ.shelf) {
      const shelf = el('div', { class: 'cur-shelf', id: 'strataShelf' });
      shelf.appendChild(el('div', { class: 'cur-filter' }, [
        el('input', {
          class: 'inp sm', id: 'strataSearch', type: 'search',
          placeholder: 'Search the sheets…', value: strataQ.text,
          oninput: (e) => {
            strataQ.text = e.target.value;
            const box = $('#strataShelfList');
            if (box) fillStrataShelf(box);
          },
        }),
        el('select', {
          title: 'Which of them',
          onchange: (e) => { strataQ.show = e.target.value; renderStrata(); },
        }, STRATA_SHOWS.map(([v, t]) => el('option', {
          value: v, text: t,
          selected: strataQ.show === v ? 'selected' : null }))),
      ]));
      const list = el('div', { class: 'cur-sets', id: 'strataShelfList' });
      fillStrataShelf(list);
      shelf.appendChild(list);
      host.appendChild(shelf);
    }

    host.appendChild(el('div', { class: 'section-label', text: 'The layers' }));
    host.appendChild(el('div', { class: 'strata-legend' },
      (strata.regions || []).map((r) => el('span', {
        class: 'cur-tally', style: '--cat:' + r.color,
        title: r.note || '', text: r.name,
      }))));
  }

  /* The shelf list on its own, so typing in the search box repaints the rows
     and not the box the cursor is in. */
  function fillStrataShelf(box) {
    box.innerHTML = '';
    const rows = strataShelf();
    if (!rows.length) {
      box.appendChild(el('div', { class: 'hint tk-empty',
        text: strataQ.text
          ? 'Nothing matches “' + strataQ.text + '”.'
          : 'Nothing here under that filter.' }));
      return;
    }
    for (const sh of rows) box.appendChild(sheetCard(sh, false));
  }

  /* ==================================================================
     Importing a folder of sorted snapshots
     ==================================================================
     Thousands of dentate spikes were sorted before Jarvis existed, by
     dragging one PNG per candidate into a folder named after the decision.
     That work is real and nobody is redoing it, so this reads it back.

     Scan first, always. The images carry an event number but not a time, so
     the decisions are matched to banked candidates by position -- which is
     only safe when the counts agree exactly. The scan is where you see
     whether they do, per recording, before anything is written.
     ================================================================== */
  let snapRoot = '';
  let snapScan = null;
  let snapBusy = false;

  const VERDICT_NOTE = {
    ready: 'will import',
    empty: 'no snapshots in it',
    unparsed: 'cannot tell which recording',
    'no-bank': 'nothing banked to get times from',
    'count-mismatch': 'counts disagree',
    gappy: 'numbering has gaps',
    'no-gid': 'the banked entry has no recording id',
    unreadable: 'could not read the folder',
  };

  function renderSnapshots() {
    const host = $('#tkResult');
    if (!host) return;
    host.innerHTML = '';

    host.appendChild(el('div', { class: 'section-label',
                                 style: 'margin-top:0',
                                 text: 'The folder to read' }));
    const pathIn = el('input', {
      type: 'text', value: snapRoot, style: 'flex:1;min-width:0',
      placeholder: 'E:\\PTEN_DS_Curation\\Visualized_spikes_...',
      oninput: (e) => { snapRoot = e.target.value; },
    });
    host.appendChild(el('div', { class: 'row', style: 'gap:8px' }, [
      pathIn,
      el('button', { class: 'btn ghost sm', text: 'Browse\u2026',
        onclick: async () => {
          const d = await pickPath('folder', snapRoot);
          if (d) { snapRoot = d; renderSnapshots(); }
        } }),
      el('button', {
        class: 'btn', text: snapBusy ? 'Scanning\u2026' : 'Scan',
        disabled: snapBusy ? 'disabled' : null,
        onclick: async () => {
          if (!snapRoot.trim()) { toast('Point it at a folder first.', 'err'); return; }
          snapBusy = true; renderSnapshots();
          try {
            snapScan = await apiPost('/api/dsimport/scan', { root: snapRoot });
          } catch (e) {
            snapScan = null;
            toast(e.message, 'err', 9000);
          } finally { snapBusy = false; renderSnapshots(); }
        } }),
    ]));

    host.appendChild(el('p', { class: 'hint',
      text: 'Each recording is a folder of numbered snapshots with '
          + 'Dentate Spike / Garbage / Flag / Flag for Deep Review inside '
          + 'it. Scanning writes nothing \u2014 it reports what would '
          + 'happen, per recording, so you can check it before it does.' }));

    if (!snapScan) return;

    const sum = snapScan.summary || {};
    const ready = (snapScan.rows || []).filter((r) => r.verdict === 'ready');
    host.appendChild(el('div', { class: 'rb-verdict '
      + (ready.length ? 'ok' : 'missing') }, [
      el('div', { class: 'rb-verdict-top' }, [
        el('strong', { text: ready.length + ' of ' + (sum.folders || 0)
                           + ' folders ready to import' }),
      ]),
      el('p', { text: [
        sum.events_spike ? sum.events_spike + ' dentate spikes' : null,
        sum.events_garbage ? sum.events_garbage + ' garbage' : null,
        sum.events_flag ? sum.events_flag + ' flagged' : null,
        sum.events_review ? sum.events_review + ' for deep review' : null,
        sum.events_undecided ? sum.events_undecided + ' still undecided' : null,
      ].filter(Boolean).join('  \u00b7  ') }),
      sum.conflicts ? el('p', { class: 'warn-line',
        text: sum.conflicts + ' snapshot(s) were filed under two different '
            + 'decisions. Those come in flagged, with a note saying which '
            + 'two, so they get looked at rather than guessed.' }) : null,
    ]));

    const table = el('table', { class: 'tk-table' });
    table.appendChild(el('thead', {}, [el('tr', {}, [
      el('th', { text: 'Folder' }), el('th', { text: 'Recording' }),
      el('th', { text: 'Events' }), el('th', { text: 'How they were sorted' }),
      el('th', { text: '' }),
    ])]));
    const body = el('tbody');
    for (const r of (snapScan.rows || [])) {
      const t = r.tally || {};
      const bits = [['spike', 'spikes'], ['garbage', 'garbage'],
                    ['flag', 'flagged'], ['review', 'deep review'],
                    ['undecided', 'undecided']]
        .filter(([k]) => t[k]).map(([k, name]) => t[k] + ' ' + name);
      body.appendChild(el('tr', { class: r.verdict === 'ready' ? '' : 'dim' }, [
        el('td', { text: r.folder }),
        el('td', { text: r.session_label || '\u2014',
                   title: r.gid || '' }),
        el('td', { text: String(r.n_images == null ? '' : r.n_images) }),
        el('td', { text: bits.join(', ')
                       + (r.conflicts && r.conflicts.length
                          ? '   (' + r.conflicts.length + ' conflicting)' : '') }),
        el('td', {}, [el('span', {
          class: 'flagchip' + (r.verdict === 'ready' ? ' good' : ' bad'),
          text: VERDICT_NOTE[r.verdict] || r.verdict,
          title: r.reason || '',
        })]),
      ]));
    }
    table.appendChild(body);
    host.appendChild(el('div', { class: 'tk-table-wrap' }, [table]));

    if (!ready.length) return;
    host.appendChild(el('div', { class: 'row', style: 'gap:8px;margin-top:10px' }, [
      el('p', { class: 'hint', style: 'flex:1',
        text: 'Importing replaces any curation set those recordings already '
            + 'have, because this is the record of a sort that already '
            + 'happened rather than something to merge into a half-finished '
            + 'one.' }),
      el('button', {
        class: 'btn', text: 'Import ' + ready.length + ' recording(s)',
        disabled: snapBusy ? 'disabled' : null,
        onclick: async () => {
          snapBusy = true; renderSnapshots();
          try {
            const res = await apiPost('/api/dsimport/apply',
                                      { token: snapScan.token });
            const nEv = (res.imported || [])
              .reduce((a, x) => a + (x.n || 0), 0);
            toast('Imported ' + (res.imported || []).length + ' recording(s), '
                  + nEv + ' candidates. Open Event curation to review the '
                  + 'flagged ones.', 'ok', 9000);
            BARRY.activity.log('dsimport.apply',
                               { folders: (res.imported || []).length, n: nEv });
            await loadCuration();
          } catch (e) {
            toast(e.message, 'err', 10000);
          } finally { snapBusy = false; renderSnapshots(); }
        } }),
    ]));
  }

  /* The panel, and then the feed.

     Each tool's branch below returns early, so there is nowhere after them
     to hang anything. Wrapping is what makes the feed automatic: a toolkit
     added later renders in a branch of the same function, and gets its
     activity list without anybody remembering to ask for one. */
  function renderResult() {
    renderToolPanel();
    mountFeed();
  }

  /* One feed, for the tool on screen. Torn down and remounted rather than
     left running: a poller for a tool nobody is looking at is a request
     every nine seconds for as long as the window is open. */
  let feedWatch = null;

  function mountFeed() {
    if (!BARRY.toolfeed) return;
    if (feedSoon) { clearTimeout(feedSoon); feedSoon = null; }
    BARRY.toolfeed.stop();
    const host = $('#tkResult');
    if (!host || !q.tool) return;
    watchPanel(host);
    tryFeed(host, q.tool);
  }
  const feedInto = (host) => document.getElementById('tkFeed') || host;

  /* Mount when there is a panel to mount under.

     Skipped while a spinner is up -- a feed above a loading panel jumps
     when the panel lands -- and skipped when one is already there, which is
     what stops the watcher below reacting to its own mount. */
  function tryFeed(host, tool) {
    if (!host || !tool || !BARRY.toolfeed) return;
    if (host.querySelector('.tk-loading')) return;
    const into = feedInto(host);
    if (into.querySelector('.tf')) return;
    BARRY.toolfeed.mount(into, tool);
  }

  /* Half the tools fetch before they draw, so the panel arrives after the
     mount would have run and repaints over it. Watching the host covers
     sync tools, async tools and anything added later without each of them
     having to remember. */
  /* Coalesced, because a panel does not rebuild once.

     A tool that redraws its whole host -- emptying it and appending a fresh
     tree -- fires this several times for one repaint, and every firing that
     lands while `.tf` is absent mounts a feed, which is a fetch. Measured on
     Braces during a read: fifteen requests for /api/toolfeed/braces in
     thirty seconds, because the panel was rebuilding four times a second
     and taking the feed with it each time.

     The tool that rebuilt too eagerly has been fixed as well; this is the
     side of it that keeps the next tool from doing the same thing. One
     frame is enough for a rebuild to finish appending. */
  let feedSoon = null;

  function watchPanel(host) {
    if (feedWatch) { feedWatch.disconnect(); feedWatch = null; }
    if (typeof MutationObserver !== 'function') return;
    feedWatch = new MutationObserver(() => {
      if (!q.tool) return;
      if (feedSoon) return;
      feedSoon = setTimeout(() => {
        feedSoon = null;
        if (!q.tool) return;
        const now = $('#tkResult');
        if (now) tryFeed(now, q.tool);
      }, 60);
    });
    feedWatch.observe(host, { childList: true });
  }

  function renderToolPanel() {
    /* Undim first, whatever branch this takes. Every early return below used
       to skip the line that reset it. */
    const box = document.getElementById('tkResult');
    if (box) box.style.opacity = '1';
    if (q.tool === 'kilosort') {
      const host = document.getElementById('tkResult');
      if (host && !host.dataset.ks) {
        host.dataset.ks = '1';
        BARRY.kilosort.load(host);
      }
      return;
    }
    if (WB[q.tool]) {
      // Reload rather than repaint when something has changed since this
      // was last read -- which is the whole of "why do I have to refresh".
      const w = WB[q.tool];
      if (!cur || curStale || (w.startable && !curStart[w.kind])) loadCuration();
      else renderCuration();
      return;
    }
    if (q.tool === 'strata') { renderStrata(); return; }
    if (q.tool === 'incisor') { BARRY.incisor.paint(); return; }
    if (q.tool === 'braces') { BARRY.braces.paint(); return; }
    if (q.tool === 'doppler') { BARRY.doppler.paint(); return; }
    if (q.tool === 'eye') { BARRY.eye.paint(); return; }
    if (q.tool === 'junction') { BARRY.junction.paint(); return; }
    if (q.tool === 'lock') { BARRY.lock.paint(); return; }
    if (q.tool === 'rootcanal') { BARRY.rootcanal.paint(); return; }
    if (q.tool === 'dspca') { BARRY.dspca.paint(); return; }
    if (q.tool === 'cfc') { renderCFC(); return; }
    if (q.tool === 'panorama') { BARRY.panorama.paint(); return; }
    if (q.tool === 'horizon') { BARRY.horizon.paint(); return; }
    if (q.tool === 'snapshots') { renderSnapshots(); return; }
    if (ARC.some(function (st) { return st[0] === q.tool; })) {
      BARRY.arc.paint(); return;
    }
    const host = $('#tkResult');
    if (!host) return;
    host.style.opacity = '1';
    host.innerHTML = '';

    if (!preview) {
      host.appendChild(el('div', { class: 'tk-loading' }, [
        stepLoader('Bad channels',
                   ['reading every recording that has marks'])]));
      return;
    }
    if (preview.error) {
      host.appendChild(el('div', { class: 'rb-verdict missing' }, [
        el('div', { class: 'rb-verdict-top' }, [
          el('span', { class: 'rb-dot missing' }),
          el('strong', { text: 'That scope does not work' }),
        ]),
        el('p', { style: 'margin:0;font-size:12px', text: preview.error }),
      ]));
      return;
    }

    const sm = preview.summary || {};
    host.appendChild(el('div', { class: 'tk-head' }, [
      el('div', {}, [
        el('h2', { text: 'Bad channels' }),
        el('p', { class: 'sub', text: preview.scope_label || '' }),
      ]),
      el('div', { class: 'spacer' }),
      el('button', {
        class: 'btn', text: 'Download CSV',
        disabled: preview.rows.length ? null : 'disabled',
        title: preview.rows.length
          ? 'Also filed under Results/ToolKit'
          : 'Nothing to export in this scope',
        onclick: download,
      }),
    ]));

    host.appendChild(el('div', { class: 'stat-row' }, [
      chip(sm.sessions + ' session' + (sm.sessions === 1 ? '' : 's'), 'good'),
      chip(sm.with_bad + ' with something marked',
           sm.with_bad ? 'warn' : null),
      chip(sm.clean + ' with nothing marked'),
      chip(sm.bad_total + ' bad channel'
           + (sm.bad_total === 1 ? '' : 's') + ' in total'),
      chip(sm.distinct_channels + ' distinct channel number'
           + (sm.distinct_channels === 1 ? '' : 's')),
      sm.first_day ? chip(sm.first_day + ' → ' + sm.last_day) : null,
    ].filter(Boolean)));

    // A channel that goes bad in several sessions is usually a wire, not a
    // recording -- which is a different problem, so it gets said out loud.
    const rep = sm.repeat_offenders || [];
    if (rep.length) {
      host.appendChild(el('div', { class: 'tk-repeat' }, [
        el('strong', { text: 'Bad more than once: ' }),
        el('span', { text: rep.map((r) => 'CSC ' + r.channel
                     + ' (' + r.sessions + ')').join(',  ') }),
        el('p', { class: 'hint', style: 'margin:4px 0 0',
          text: 'A channel that keeps coming up is worth checking at the '
              + 'headstage rather than in the analysis.' }),
      ]));
    }

    if (!preview.rows.length) {
      host.appendChild(el('div', { class: 'hint tk-empty',
        text: 'No bad channels are marked in ' + (preview.scope_label || 'this scope')
            + '. Mark them on the channel list in Xplorefinder and they will '
            + 'appear here.' }));
      return;
    }

    host.appendChild(table(preview.columns, preview.rows));
  }

  function chip(text, kind) {
    return el('span', { class: 'stat-chip' + (kind ? ' ' + kind : ''), text });
  }

  function table(cols, rows) {
    // Wide tables scroll inside their own box; the page must not.
    const wrap = el('div', { class: 'tk-tablewrap' });
    const t = el('table', { class: 'res-table tk-table' });
    t.appendChild(el('thead', {}, [el('tr', {}, cols.map((c) =>
      el('th', { text: c.replace(/_/g, ' ') })))]));
    const body = el('tbody');
    // A cap on what is drawn, not on what is exported: 4000 rows of DOM is
    // slow to build and nobody reads past the first screen anyway.
    const CAP = 500;
    for (const r of rows.slice(0, CAP)) {
      body.appendChild(el('tr', {}, cols.map((c) => el('td', {
        text: r[c] === null || r[c] === undefined ? '' : String(r[c]),
        title: c === 'path' ? String(r[c] || '') : null,
        class: c === 'channel' || c === 'bad_channels' ? 'tk-ch' : null,
      }))));
    }
    t.appendChild(body);
    wrap.appendChild(t);
    if (rows.length > CAP) {
      wrap.appendChild(el('p', { class: 'hint',
        text: 'Showing the first ' + CAP + ' of ' + rows.length
            + ' rows. The download has all of them.' }));
    }
    return wrap;
  }

  /* ---------- the download ---------- */
  async function download() {
    const url = '/api/toolkit/bad-channels/export?' + args();
    try {
      const res = await fetch(url);
      if (!res.ok) {
        let msg = 'HTTP ' + res.status;
        try { msg = (await res.json()).error || msg; } catch (e) { /* text */ }
        toast(msg, 'err', 8000);
        return;
      }
      const blob = await res.blob();
      const name = (res.headers.get('Content-Disposition') || '')
        .replace(/.*filename="?([^"]+)"?.*/, '$1') || 'bad-channels.csv';
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);

      const rel = res.headers.get('X-Barry-Output');
      toast((res.headers.get('X-Barry-Rows') || '?') + ' rows downloaded'
            + (rel ? ' — also filed at Results/' + rel : ''), 'ok', 7000);
      BARRY.activity.log('toolkit.bad_channels.export', {
        scope: q.scope, form: q.form, rows: res.headers.get('X-Barry-Rows'),
        run: res.headers.get('X-Barry-Run-Id'),
      });
      BARRY.refreshSync();
    } catch (e) {
      toast('Export failed: ' + e.message, 'err', 8000);
    }
  }

  /* Nothing to wire up any more.

     The header used to carry a Refresh button. Every tool in here reloads
     what it needs when it is opened, and each one that can go stale has its
     own control saying what it would actually re-fetch -- so a general
     "Refresh" in the corner was a button whose effect nobody could predict
     and which was mostly pressed out of doubt. Kept as a function because
     the view loop calls `init` on every view. */
  function init() {}

  return {
    init,
    /* The cached registry rows, flattened, for a tool that wants its own
       session picker. Through here rather than each tool fetching, so one
       sixty-second cache serves them all. */
    registryRows: registryRowsInternal,
    /* And the read that fills it, for a tool that needs the rows rather than
       merely preferring them.

       `registryRows` is a getter over a cache nothing here is obliged to
       have filled: Curation, StrataScope and Braid each warm it on their way
       in, but a tool opened before any of those reads an empty list and
       cannot tell that apart from a registry with nothing in it. Braces read
       it that way for its bad-channel column and its reachability, and so
       said "none bad" against forty-six recordings that have channels marked
       and "can be read here" about every one of them. A tool that needs the
       answer awaits this first; the cache is shared, so warming it twice
       costs one request. */
    loadRegistry: registry,
    tool: () => q.tool, onShow, refresh,
    /* How a tool's "Next" carries on (see paintNext). */
    setHandoff,
    /* A banked run onto its door's bench, and the door on screen: what
       "Next: Spotter" from Doppler and "Pan them" from Junction do. Quick
       when there is nothing to choose (one version, no set yet); otherwise
       the add-a-set dialog opens on that dataset. Never the mode itself. */
    benchFrom: (door, gid, entryId) => newSetDialog({
      door, preset: { gid, entry: entryId }, quick: true }),
    newSet: (door) => newSetDialog({ door }),
    /* Open a tool by name, for anything outside this view that knows which
       one it wants -- the command palette, and a deep link. The same
       function the bundle steps and the flat buttons call, rather than a
       second copy: two doors onto one thing is already the rule here, and
       the third would be the one that drifts. Unknown ids are refused
       rather than set, because `q.tool` naming a tool that does not exist
       renders an empty pane with no way back. */
    pick: (id, via) => {
      /* Every bundle step, plus every flat tool -- which is every id with
         an icon. Not the icon map alone: X-ray has no icon of its own and
         would have been refused by a guard that only asked that. */
      if (BUNDLED.indexOf(id) < 0 && !TOOL_ICONS[id]) return false;
      pickTool(id, via);
      return true;
    },
    /* The bundle the open tool is being worked in (see `bundleOf`). */
    via: () => (bundleOf(q.tool) || {}).id || null,
    /* Which tools are steps of a bundle, and of which. `_dev/arc.html`
       checks the bundle renders its steps and keeps them out of the flat
       list; nothing else should need this. */
    // Which tools claim they can run on the cluster. Exported so
    // `_dev/storm.html` can assert the claim is true of exactly the ones
    // that can -- a tool marked as offloadable that is not is worse than
    // one with no mark at all.
    _vaccTools: () => VACC_TOOLS.slice(),
    readsOf,
    vaccWords,
    /* The step chip, for any tool that is in a bundle. See `stepOf`. */
    stepOf,
    bundles: () => BUNDLES.map((b) => ({
      id: b.id, name: b.name,
      steps: b.steps.map(([id, name, does, soon]) =>
        ({ id, name, does, soon: soon || null })),
    })),
    /* Leaving ToolKit stops what ToolKit started.

       Two timers ran on regardless: the presence beat above, and whatever
       tool feed was mounted -- toolfeed.stop() was only ever reached by
       mounting a different one, so navigating away left a 3-second poll
       running for the rest of the session. onShow starts both again. */
    onHide() {
      stopPresence();
      if (BARRY.toolfeed) BARRY.toolfeed.stop();
    },
    /* Redraw the chrome without re-fetching anything. VACC Mode adds a mark
       to the tool row, and turning it on has to show up in the panel it is
       talking about rather than at the next navigation. */
    render,
    /* For web/_dev/presence.html, which drives the real workbench rather
       than a copy: it needs to hand in a known set of sessions and ask what
       the bench makes of them. */
    _presence: (got) => { if (got) presence = got; renderCuration(); },
    _heldBy: (st) => heldBy(st),
    _loadPresence: (andRender) => loadPresence(andRender),
    /* Curation calls this when it changes something. Cheap on purpose: it
       marks the cache stale rather than refetching, because the tool is not
       on screen while somebody is curating and a fetch per keystroke is
       exactly the kind of thing that made the queue back up. */
    curationChanged: () => { curStale = true; },
    /* Drop what each pane has cached, so the loading path can be exercised
       on a second visit. Only web/_dev/tkload.html uses this. */
    debugForget: () => { preview = null; cur = null; strata = null; },
  };
})();
