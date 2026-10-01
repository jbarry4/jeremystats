/* ==========================================================================
   arc.js -- The Arc, the DEWEY RATs pipeline.

   Five steps from a TTL pulse to a difference between two brains:

     1  Spark     find the cue events and pair them
     2  Relay     file the pairs in the Event Bank
     3  Coupling  the three correlations, against the traces
     4  Circuit   a named connectivity matrix, with its metadata
     5  Drift     the difference between two of them

   Named after Dewey's 1896 "The Reflex Arc Concept in Psychology", which
   argued that stimulus and response are one continuous circuit rather than a
   chain -- which is the claim a connectivity matrix is making.

   WHY FOUR OF THE FIVE ARE HERE AND DO NOTHING

   Step one is being built; the rest are not. They are registered, named and
   reachable anyway, each painting a card that says what it will do and what
   has to happen first, because "this step exists and cannot be used, and
   here is why" is a real answer and an absent row is not -- the same
   reasoning the banked-set list already applies to a set it cannot read.

   It also means the wiring is exercised now rather than in five separate
   sittings: the ToolKit entry, the dispatch, the step header and the
   Xplorefinder mode contract are all connected from the start, and those
   are the parts that are easy to half-do.

   Each step takes over the whole result pane; none of them uses the
   bad-channel scope card, which is why `toolkit.js` lists them among the
   tools that own the pane.
   ========================================================================== */
'use strict';

BARRY.arc = (function () {
  /* What each step is, in the order they are done. `needs` is the step
     before it; `phase` is when it lands. A step with no `blurb` has not
     been thought about yet, which has never been true here. */
  const STEPS = [
    {
      id: 'spark',
      name: 'Spark',
      blurb: 'Read the TTL pulses out of a DEWEY recording, pair each cue '
             + 'with the one it opens onto, and file the pairs.',
      will: [],
      needs: 'A DEWEY recording whose files are on this computer.',
      phase: 'Phase 3',
      built: true,
    },
    {
      id: 'coupling',
      name: 'Coupling',
      blurb: 'The three correlations between two regions, at each boundary '
             + 'of a cue pair, against the traces they came from.',
      will: [
        'Cuts the four analysis windows of each banked pair: ten seconds '
        + 'of baseline, cue 1, cue 2, and ten seconds after cue 2 ends.',
        'Computes coherence, raw cross-correlation and amplitude '
        + 'cross-correlation, at the parameters the cluster pipeline used.',
        'Opens as an Xplorefinder mode, because picking two regions is a '
        + 'thing you do while looking at what they are doing.',
      ],
      needs: 'Spark, plus a recording whose probe is set to DEWEY 32.',
      phase: 'Phase 5',
      built: true,
    },
    {
      id: 'circuit',
      name: 'Circuit',
      blurb: 'A connectivity matrix over the twelve regions, saved as a '
             + 'named object that can say where every number in it came '
             + 'from.',
      will: [
        'Builds the matrix over any scope you pick: one recording, one '
        + 'rat’s Precon1, every Precon1 across rats.',
        'Saves it with its recordings, its pairs, its boundary, its method, '
        + 'its filter and which channels were excluded — so two copies '
        + 'can be checked against each other rather than assumed equal.',
        'Names it for you, and lets you rename it without changing what it '
        + 'is.',
      ],
      needs: 'Coupling, which is what computes the numbers in it.',
      phase: 'Phase 6',
      // Built in web/js/circuit.js (BARRY.circuit), which paints the step.
      built: true,
    },
    {
      id: 'drift',
      name: 'Drift',
      blurb: 'The difference between two circuits — within a recording, '
             + 'across recordings, across rats, across phases.',
      will: [
        'Differences two saved circuits region pair by region pair.',
        'Tests each difference between the two distributions rather than '
        + 'subtracting two averages, because the two sides are separate '
        + 'recordings and not matched trials.',
        'Refuses two circuits that are not comparable, and says which of '
        + 'their fields disagrees.',
      ],
      needs: 'Circuit, twice — there is nothing to compare until there '
             + 'are two.',
      phase: 'Phase 7',
      // Built in web/js/drift.js (BARRY.drift), which paints the step.
      built: true,
    },
  ];

  const byId = {};
  STEPS.forEach((s, i) => { byId[s.id] = Object.assign({ n: i + 1 }, s); });

  function stepOf(id) { return byId[id] || null; }

  /* ------------------------------------------------------------------
     The construction card

     An `.empty-state`, because that is what this is: a surface with
     nothing on it yet. The rule for one is that it says what to do next,
     so it says what the step will do, what has to happen before it can,
     and when it is being built -- in that order, because "what is this"
     comes before "why can't I".
     ------------------------------------------------------------------ */
  function soonCard(step) {
    const box = el('div', { class: 'empty-state arc-soon' });

    box.appendChild(el('div', { class: 'arc-soon-tag' }, [
      el('span', { class: 'arc-soon-dot' }),
      el('span', { text: 'Being built · ' + step.phase }),
    ]));

    box.appendChild(el('div', { class: 'section-label',
                                text: 'What it will do' }));
    box.appendChild(el('ul', { class: 'arc-soon-list' },
      step.will.map((line) => el('li', { text: line }))));

    box.appendChild(el('div', { class: 'section-label',
                                text: 'What it needs first' }));
    box.appendChild(el('p', { class: 'hint', text: step.needs }));

    box.appendChild(el('p', { class: 'hint arc-soon-foot',
      text: 'Nothing here is saved, and nothing here reads a recording. '
            + 'The step is listed so the five are visible as one job — '
            + 'it will do the work above when it lands.' }));
    return box;
  }

  /* ------------------------------------------------------------------
     Painting
     ------------------------------------------------------------------ */
  function paint() {
    const host = document.getElementById('tkResult');
    if (!host) return;

    /* Which tool is open, asked of the ToolKit rather than assumed.
       Painting into a pane another tool owns puts this module's words under
       that tool's name, and an error thrown afterwards names variables from
       a panel nobody is looking at. Not knowing is a reason not to draw. */
    const tk = BARRY.views.toolkit;
    if (!tk || typeof tk.tool !== 'function') return;
    const step = stepOf(tk.tool());
    if (!step) return;

    host.innerHTML = '';
    host.appendChild(BARRY.ui.stepHeader({
      title: step.name,
      step: 'step ' + step.n + ' of The Arc',
      blurb: step.blurb,
    }));

    if (!step.built) {
      host.appendChild(soonCard(step));
      return;
    }
    if (step.id === 'spark') { paintSpark(host); return; }
    if (step.id === 'coupling') { paintCoupling(host); return; }
    if (step.id === 'circuit' && BARRY.circuit) {
      BARRY.circuit.paint(host); return;
    }
    if (step.id === 'drift' && BARRY.drift) {
      BARRY.drift.paint(host); return;
    }
    host.appendChild(soonCard(step));
  }

  /* ------------------------------------------------------------------
     Spark

     What is being asked for, held here rather than read off the DOM so a
     redraw cannot lose it.
     ------------------------------------------------------------------ */
  const q = { phase: 'Precon', gid: null };
  let rows = null;        // the recordings that can be read
  let banked = {};        // gid -> what is already filed
  let reading = null;     // the current recording's pairs
  let clip = null;        // the clipping reading, once somebody asks
  let clipBusy = false;
  let busy = false;
  /* ------------------------------------------------------------------
     Batch mode -- many recordings at once.

     Braces already has this surface ("Many sets at once") and this is the
     same one in Spark's prefix: a segmented switch at the top, a bar of
     selection shortcuts with one primary at the end, a dense row per
     thing, and a status column that takes the slack. Somebody who has run
     a batch in Braces has already learnt this one, which is the entire
     reason it is not a second idiom.

       `want`   gid -> true. The ticks, and a ticked row means STILL TO DO
                -- see `unpick`, which is what keeps that sentence true.
       `state`  gid -> {state, msg, found}. The only thing the status
                column and the disclosure read, so a recording that
                finished four minutes ago still says what it found.
       `off`    gid -> why a tick came off by itself. Kept rather than
                only acted on: a tick that vanishes with nothing said is
                worse than one that stays and is wrong, because the second
                can be argued with.
       `open`   gid -> the disclosure is open. Held here and not left to
                the DOM because the end of a run repaints the table, and a
                panel somebody had open would shut itself at the one
                moment they were reading it.
     ------------------------------------------------------------------ */
  const bulk = {
    on: false, want: {}, state: {}, off: {}, open: {},
    clip: true, running: false, stop: false,
  };
  /* Which recordings THIS PAGE has measured clipping on.

     The reading lives in the server's process, keyed by gid, and the bank
     route folds whatever it holds into the entry whether or not this panel
     asked for it. So a batch run with clipping switched off, over a
     recording somebody measured by hand ten minutes ago, would file an
     entry whose events are marked `clipped` and whose `excluded` list is
     empty -- the measurement recorded and then ignored, which is the exact
     fault the whole of `recompute` exists to prevent. Asking for the
     reading again costs nothing when the server still has it (it answers
     `cached`), so a recording on this list is always asked.

     WHAT THIS STILL CANNOT SEE. The list is per page load and the server's
     cache is per process, so a recording measured before this page was
     opened is one the panel has no way to know about: the clipping route
     cannot be asked "do you have this" without paying for the answer when
     it does not. Closing it properly means the recordings route saying
     which gids the server holds a reading for. Until it does, the toggle
     defaults to ON, which is the position with no wrong answer in it. */
  const clipSeen = {};
  /* ------------------------------------------------------------------
     What gets dropped, and who said so

     Three structures rather than one, because they are three different
     claims -- the same distinction `eventbank.py` draws when it keeps
     `clipped` and `excluded` in separate fields on a banked event:

       the measurement  `clip.by_pair`. Which windows saturated. Never
                        edited here; it is what was found.
       the override     `kept`. Flagged channels somebody has looked at on
                        the traces and said are fine after all.
       the stretches    `spans_`. The saturated stretches as somebody has
                        trimmed or widened them in Clean.

     `excluded` is what the other three come to, and it is the only one the
     bank is sent. It used to be filled ONLY when somebody clicked the
     "N clipped" chip in the pair table, which meant the default outcome of
     measuring clipping was that nothing was dropped -- the exact opposite
     of what the measurement says. Now a lost window drops the channel
     unless a person overrules it, and every surface that mentions clipping
     says so in those words.

     All of it lives here rather than in the Clean mode, because leaving a
     mode must not lose decisions: stepping out to look at something else
     and coming back costs nothing.
     ------------------------------------------------------------------ */
  let excluded = {};
  /* Overrules, by pair then channel then window. See `setBlock`. */
  let dropped = {};      // pair id -> [csc]  what the bank is told to drop
  let kept = {};          // pair id -> [csc]  flagged, overruled by hand
  let spans_ = {};        // pair id -> csc -> [{a, b, hand}]

  const PAD_S = 10;       // the analysis pad, matching spark.CLIP_PAD_S

  /* The transition windows' lengths, as this panel will ASK for them: one
     second before each boundary and two after, which is spark.py's
     default. What a reading was actually measured with is on the reading
     (`clip.transition.before_s`), and that is what everything drawn from
     a reading uses -- these are only what the next check will be asked. */
  const tq = { before: 1.0, after: 2.0 };

  /* The windows of a pair, named, of either kind. The same boundaries the
     backend measures clipping in, so what is drawn, what was measured and
     what is decided here cannot drift apart. */
  function windowsOf(p, kind) {
    if (kind === 'transition') {
      const t = (clip && clip.transition) || {};
      const b = t.before_s != null ? t.before_s : tq.before;
      const a = t.after_s != null ? t.after_s : tq.after;
      return [
        ['onset', p.opener_t - b, p.opener_t + a],
        ['switch', p.closer_t - b, p.closer_t + a],
        ['offset', p.offset_t - b, p.offset_t + a],
      ];
    }
    return [
      ['pre', p.opener_t - PAD_S, p.opener_t],
      ['cue1', p.opener_t, p.closer_t],
      ['cue2', p.closer_t, p.offset_t],
      ['post', p.offset_t, p.offset_t + PAD_S],
    ];
  }

  function pairById(pairId) {
    return ((reading && reading.pairs) || []).find(
      (p) => String(p.pair_id) === String(pairId)) || null;
  }

  /* One kind's reading of one pair. The transition half is only there
     when the server measured it; absent is "nobody looked", and every
     caller below reads null as that, never as clean. */
  function clipOf(pairId, kind) {
    if (kind === 'transition') {
      const t = (clip && clip.transition) || null;
      if (!t || !t.measured) return null;
      return (t.by_pair || {})[String(pairId)] || null;
    }
    return ((clip && clip.by_pair) || {})[String(pairId)] || null;
  }

  /* Whether this reading has an answer for a kind at all. */
  function measuredKind(kind) {
    if (!clip) return false;
    if (kind === 'transition') {
      return !!(clip.transition && clip.transition.measured);
    }
    return true;
  }

  /* One channel's saturated stretches as they now stand: the measurement,
     or what somebody has made of it.

     `hand` marks a stretch that was dragged or widened. It is what lets a
     widened stretch claim a window the measurement did not, without a
     merely-trimmed one doing the same by accident -- see `lostOf`. */
  function spansOf(pairId, csc) {
    const mine = (spans_[String(pairId)] || {})[String(csc)];
    if (mine) return mine;
    /* The state reading covers the whole forty seconds and so holds every
       stretch; a channel that only the transition reading has anything to
       say about (a stretch split across two state windows, each too short
       to count) falls back to the stretches that reading found. */
    const d = (clipOf(pairId) || {})[String(csc)]
              || (clipOf(pairId, 'transition') || {})[String(csc)];
    return ((d && d.spans) || []).map(
      (s) => ({ a: s[0], b: s[1], hand: false }));
  }

  const editedSpans = (pairId, csc) =>
    !!(spans_[String(pairId)] || {})[String(csc)];

  /* Copies in, always. `spansOf` hands back the stored array itself once a
     channel has been edited, and a caller that spliced it would have moved
     the stretches without `recompute` ever running -- the drawing would
     change and the exclusion list would not. */
  function setSpans(pairId, csc, list) {
    const pid = String(pairId);
    if (!spans_[pid]) spans_[pid] = {};
    spans_[pid][String(csc)] = list.map(
      (s) => ({ a: s.a, b: s.b, hand: !!s.hand }));
    recompute(pid);
  }

  function resetSpans(pairId, csc) {
    const pid = String(pairId);
    if (spans_[pid]) delete spans_[pid][String(csc)];
    recompute(pid);
  }

  /* Which of the four windows this channel has still lost.
   *
   * Untouched, that is exactly what the backend measured: `windows` holds
   * the windows whose saturation passed the fraction-or-run test, and a
   * three-millisecond graze of the rail is deliberately not on it.
   *
   * Once somebody has edited the stretches the question is theirs, so a
   * window counts as lost while a stretch still overlaps it -- and a
   * stretch somebody WIDENED can claim a window the measurement did not,
   * which is what "the saturation is wider than you found" means. Dismiss
   * every stretch in a window and the window comes back. Without that, a
   * row could sit there in red saying the opposite of what had just been
   * decided about it, which is worse than no row at all.
   */
  function lostOf(pairId, csc, kind) {
    const d = (clipOf(pairId, kind) || {})[String(csc)];
    if (!d) return [];
    const was = d.windows || [];
    const p = pairById(pairId);
    if (!editedSpans(pairId, csc) || !p) return was.slice();
    /* The same rule for both kinds, against that kind's windows: the
       stretches are one set per channel, so dismissing one takes it out of
       every window it overlapped, state and transition alike. */
    const live = spansOf(pairId, csc);
    return windowsOf(p, kind).filter(([name, a, b]) => live.some(
      (s) => s.b > a && s.a < b && (s.hand || was.indexOf(name) >= 0)))
      .map((w) => w[0]);
  }

  /* What the measurement itself said, edits or not -- which is what the
     bank's `clipped` carries, and so what Coupling will leave out. */
  function measuredLost(pairId, csc, kind) {
    const d = (clipOf(pairId, kind) || {})[String(csc)];
    return d ? (d.windows || []).slice() : [];
  }

  /* The same scale as spark.loss_grade, so the word on screen and the word
     in the bank are one word. */
  function gradeOf(n, of) {
    const all = of || 4;
    if (n <= 0) return 'clean';
    if (n === 1 && all > 1) return 'partial event loss';
    if (n >= all) return 'event lost';
    return 'major event loss';
  }

  /* The channels this pair has actually lost something on.
   *
   * NOT `Object.keys(by_pair[pid])`. That dict carries a row for every
   * channel that touched the rail at all, including the ones the backend
   * itself grades clean -- `clip_summary` skips a channel whose `windows`
   * list is empty for exactly this reason. Counting the keys is how the
   * mode bar came to announce "56 channel(s) clipped" on a recording whose
   * clipping card listed nine, and how a channel with three milliseconds
   * against it would have been dropped from the analysis. */
  function flaggedOf(pairId, kind) {
    const bad = clipOf(pairId, kind);
    if (!bad) return [];
    return Object.keys(bad).map(Number)
      .filter((c) => lostOf(pairId, c, kind).length > 0)
      .sort((a, b) => a - b);
  }

  const keptOf = (pairId) => kept[String(pairId)] || [];
  const exclOf = (pairId) => excluded[String(pairId)] || [];

  /* ------------------------------------------------------------------
     A decision is about a BLOCK, not a channel.

     A cue pair is four windows and a channel can be ruined in one of them
     and perfectly good in the other three -- which on this data is most
     of the data. Deciding per channel threw the three good windows away
     with the bad one.

     `kept[pid][csc]` is the list of windows somebody has overruled: the
     measurement said lose it, they said keep it. `dropped[pid][csc]` is
     the other direction, a window nobody flagged that they want gone
     anyway. Everything else follows from the measurement.
     ------------------------------------------------------------------ */
  const WINDOWS_4 = ['pre', 'cue1', 'cue2', 'post'];
  /* The transition windows: a short span around each of a pair's three
     boundaries. They are decided in exactly the same way -- one block per
     channel per window, kept or removed -- and banked under their own
     names in the same per-window dict, so one structure holds both kinds
     and a window name says which kind it is. */
  const WINDOWS_T = ['onset', 'switch', 'offset'];
  const WINDOW_SAY = { pre: 'baseline', cue1: 'cue 1', cue2: 'cue 2',
                       post: 'after cue 2',
                       onset: 'cue 1 onset', switch: 'cue 1 → cue 2',
                       offset: 'cue 2 offset' };
  const KINDS = ['state', 'transition'];
  const KIND_SAY = { state: 'State', transition: 'Transition' };

  const namesOf = (kind) => (kind === 'transition' ? WINDOWS_T : WINDOWS_4);
  const kindOfWindow = (w) => (WINDOWS_T.indexOf(w) >= 0 ? 'transition'
                                                          : 'state');

  function keptWindows(pairId, csc) {
    return ((kept[String(pairId)] || {})[String(csc)]) || [];
  }

  function droppedWindows(pairId, csc) {
    return ((dropped[String(pairId)] || {})[String(csc)]) || [];
  }

  /* Is this one block going into the analysis? The window's own name says
     which reading decides it. */
  function blockKept(pairId, csc, wname) {
    if (droppedWindows(pairId, csc).indexOf(wname) >= 0) return false;
    if (keptWindows(pairId, csc).indexOf(wname) >= 0) return true;
    return lostOf(pairId, csc, kindOfWindow(wname)).indexOf(wname) < 0;
  }

  function setBlock(pairId, csc, wname, keep) {
    const pid = String(pairId), key = String(csc);
    const wasLost = lostOf(pairId, csc, kindOfWindow(wname))
      .indexOf(wname) >= 0;
    const k = kept[pid] = kept[pid] || {};
    const d = dropped[pid] = dropped[pid] || {};
    k[key] = (k[key] || []).filter((w) => w !== wname);
    d[key] = (d[key] || []).filter((w) => w !== wname);
    // Only the overrules are stored. A block that agrees with the
    // measurement is recorded nowhere, so re-measuring cannot leave a
    // stale decision behind it.
    if (keep && wasLost) k[key].push(wname);
    if (!keep && !wasLost) d[key].push(wname);
    if (!k[key].length) delete k[key];
    if (!d[key].length) delete d[key];
    if (!Object.keys(k).length) delete kept[pid];
    if (!Object.keys(d).length) delete dropped[pid];
    recompute(pairId);
  }

  /* Every block of one kind of a channel, in one gesture. */
  function setAllBlocks(pairId, csc, keep, kind) {
    for (const w of namesOf(kind)) setBlock(pairId, csc, w, keep);
  }

  /* `excluded` is never written from outside this function. One place
     decides it, so the list the bank is handed cannot disagree with the
     list on screen -- they are the same list read twice.

     Keyed by WINDOW now, which is the shape the bank and the analysis both
     take: {"pre": [17, 22], "cue1": [17], "onset": [17]}. Both kinds, in
     one dict, because the bank keeps them in one dict. */
  function recompute(pairId) {
    const pid = String(pairId);
    const out = {};
    for (const kind of KINDS) {
      for (const c of chansOf(pairId, kind)) {
        for (const w of namesOf(kind)) {
          if (blockKept(pid, c, w)) continue;
          (out[w] = out[w] || []).push(c);
        }
      }
    }
    for (const w of Object.keys(out)) out[w].sort((a, b) => a - b);
    if (Object.keys(out).length) excluded[pid] = out;
    else delete excluded[pid];
  }

  /* Every channel with a row in one kind's measurement, flagged or not --
     a block nobody flagged is still a block somebody may want to drop. */
  function chansOf(pairId, kind) {
    const bad = clipOf(pairId, kind);
    return bad ? Object.keys(bad).map(Number).sort((a, b) => a - b) : [];
  }

  function recomputeAll() {
    for (const p of (reading && reading.pairs) || []) recompute(p.pair_id);
  }

  /* Keeping or dropping a whole channel, which is every one of its blocks
     of one kind at once. The blocks are the model; this is the shortcut
     for somebody who has decided about the channel rather than about a
     window, and it is what the keyboard and the keep-all button use. It
     is per kind because the two views are decided in turn, and keeping a
     channel's four state blocks says nothing about its boundaries. */
  function setKept(pairId, csc, keep, kind) {
    setAllBlocks(pairId, csc, keep, kind);
  }

  /* A channel is "kept" when nothing of that kind is being dropped. */
  function channelKept(pairId, csc, kind) {
    return namesOf(kind).every((w) => blockKept(pairId, csc, w));
  }

  /* The blocks of this channel, of one kind, that will not go in. */
  function goneOf(pairId, csc, kind) {
    return namesOf(kind).filter((w) => !blockKept(pairId, csc, w));
  }

  /* Channels with at least one block of this kind going. */
  function droppingOf(pairId, kind) {
    return chansOf(pairId, kind).filter(
      (c) => goneOf(pairId, c, kind).length > 0);
  }

  /* Channels the measurement flagged that are being kept anyway. */
  function overruledOf(pairId, kind) {
    return flaggedOf(pairId, kind).filter(
      (c) => channelKept(pairId, c, kind));
  }

  /* How much of this recording the analysis is about to lose, counted the
     two ways somebody asks about it: how many channel-events go, and how
     many distinct channels are involved at all. `kind` narrows it to one
     kind's windows; without it, both. */
  function dropTally(kind) {
    const chans = new Set();
    let blocks = 0;
    const pairs = new Set();
    const only = kind ? namesOf(kind) : null;
    for (const pid in excluded) {
      for (const w in excluded[pid]) {
        if (only && only.indexOf(w) < 0) continue;
        for (const c of excluded[pid][w]) {
          blocks += 1;
          chans.add(c);
          pairs.add(pid);
        }
      }
    }
    // `n` stays the headline number and is now BLOCKS, not channels: a
    // channel losing its baseline and a channel losing all four are not
    // the same loss, and one count that called them both "1" was the
    // reason to go block by block in the first place.
    return { n: blocks, blocks: blocks, chans: chans.size,
             pairs: pairs.size };
  }

  /* The blocks put BACK in against the measurement, keyed by pair then
     window: every block the read found lost (the raw measurement, which is
     what the bank's `clipped` carries) that is going into the analysis
     anyway -- kept by a click, or by dismissing its stretches. Banked as
     `kept`, which Coupling subtracts; without it the green block on screen
     was still left out downstream. Both kinds. */
  function keptFor(pairId) {
    const out = {};
    for (const kind of KINDS) {
      for (const c of chansOf(pairId, kind)) {
        for (const w of measuredLost(pairId, c, kind)) {
          if (blockKept(pairId, c, w)) (out[w] = out[w] || []).push(c);
        }
      }
    }
    for (const w of Object.keys(out)) out[w].sort((a, b) => a - b);
    return out;
  }

  function keptAll() {
    const out = {};
    for (const p of (reading && reading.pairs) || []) {
      const k = keptFor(p.pair_id);
      if (Object.keys(k).length) out[String(p.pair_id)] = k;
    }
    return out;
  }

  /* One kind's slice of a pair's exclusion, keyed by window. */
  function exclKind(pairId, kind) {
    const all = excluded[String(pairId)] || {};
    const out = {};
    for (const w of namesOf(kind)) if (all[w]) out[w] = all[w].slice();
    return out;
  }

  /* Which wire each region will be measured on, window by window, given
     what has been decided so far -- the same one-wire rule Coupling runs
     (`coupling.representative`): the lowest-numbered channel that is
     present, not marked bad, and not left out in that window.

     "Left out" is what COUPLING will leave out: the bank carries `clipped`
     (what the read found), `excluded` (what was removed by hand) and
     `kept` (what was put back against the measurement), and Coupling
     takes (clipped + excluded) - kept -- which is exactly the blocks not
     kept here.

     Per region, per window, one of:
       ok        its lowest wire is used
       rescued   its lowest wire is out here, and a spare takes over
       gone      every wire it has is out here
       hist      the probe is not in the region (or nobody has scored it),
                 so it is not computed at all, whatever its wires do

     `regs` is `/api/arc/spark/<gid>/regions`. */
  function wireGrid(pairId, kind, regs) {
    const bad = new Set(((regs && regs.bad) || (clip && clip.bad) || [])
      .map(Number));
    const present = clip && clip.present
      ? new Set(clip.present.map(Number)) : null;
    const out = [];
    for (const r of ((regs && regs.regions) || [])) {
      const rec = { slot: r.slot, region: r.region, label: r.label || r.region,
                    histology: r.histology, windows: {} };
      for (const w of namesOf(kind)) {
        if (r.usable === false) {
          rec.windows[w] = { state: 'hist', channel: null,
                             why: r.why || (rec.label + ' is ruled out by '
                                            + 'histology.') };
          continue;
        }
        const csc = (r.csc || []).map(Number).sort((a, b) => a - b);
        let base = null, chosen = null;
        const passed = [];
        for (const c of csc) {
          if (present && !present.has(c)) { passed.push([c, 'not present']); continue; }
          if (bad.has(c)) { passed.push([c, 'marked bad']); continue; }
          if (base == null) base = c;
          /* Left out exactly when the block is not kept: the bank carries
             the measurement, the removals AND the blocks kept against the
             measurement, and Coupling takes (clipped + excluded) - kept. */
          const measured = measuredLost(pairId, c, kind).indexOf(w) >= 0;
          if (!blockKept(pairId, c, w)) {
            passed.push([c, measured ? 'clipped here' : 'removed here by hand']);
            continue;
          }
          chosen = c;
          break;
        }
        const say = (list) => list.map(([c, why]) => 'CSC ' + c + ' ' + why)
          .join('; ');
        if (chosen == null) {
          rec.windows[w] = { state: 'gone', channel: null,
            why: rec.label + ' has no usable wire in ' + WINDOW_SAY[w]
                 + (passed.length ? ': ' + say(passed) : '')
                 + '. Nothing is computed for it there.' };
        } else if (base != null && chosen !== base) {
          rec.windows[w] = { state: 'rescued', channel: chosen,
            why: rec.label + ' is rescued in ' + WINDOW_SAY[w] + ': '
                 + say(passed.filter(([c]) => c < chosen))
                 + ', so its spare wire CSC ' + chosen + ' takes over.' };
        } else {
          rec.windows[w] = { state: 'ok', channel: chosen,
            why: rec.label + ' is measured on CSC ' + chosen + ' in '
                 + WINDOW_SAY[w] + '.' };
        }
      }
      out.push(rec);
    }
    return out;
  }

  /* The Spark panel is behind the mode rather than gone -- the ToolKit
     view still holds it -- so a decision made in Clean has to repaint it,
     or stepping back out shows the counts as they were before. Only when
     Spark is the tool on screen: painting into a pane another tool owns is
     the fault `paint()` guards against at the top of this module. */
  function afterDecision() {
    try {
      if (BARRY.views.toolkit && BARRY.views.toolkit.tool
          && BARRY.views.toolkit.tool() === 'spark'
          && document.getElementById('arcRead')) renderRead();
    } catch (e) {
      reportClientError('arc.spark.repaint', e.message, e.stack);
    }
  }

  async function loadRows() {
    const got = await api('/api/arc/spark/recordings?phase='
                          + encodeURIComponent(q.phase));
    rows = got.rows || [];
    banked = got.banked || {};
  }

  function paintSpark(host) {
    host.appendChild(modeCard());
    /* One of the two surfaces, never both. They answer different
       questions -- "what is in this recording" and "get through these
       nine" -- and the one that is not on screen has no host, which is
       what lets `renderSpark` be one call instead of three branches that
       have to agree about which mode is on. */
    if (bulk.on) {
      host.appendChild(el('div', { class: 'arc-batch-host', id: 'arcBatch' }));
    } else {
      host.appendChild(el('div', { class: 'arc-spark' }, [
        el('div', { class: 'arc-pick', id: 'arcPick' }),
        el('div', { class: 'arc-read', id: 'arcRead' }),
      ]));
    }
    if (rows === null) {
      const pick = document.getElementById(bulk.on ? 'arcBatch' : 'arcPick');
      BARRY.skeleton.into(pick, 'row', 8);
      loadRows().then(renderSpark).catch((e) => {
        reportClientError('arc.spark', e.message, e.stack);
        const p = document.getElementById(bulk.on ? 'arcBatch' : 'arcPick');
        if (p) {
          p.innerHTML = '';
          p.appendChild(el('p', { class: 'hint',
                                  text: 'Could not read the registry: '
                                        + e.message }));
        }
      });
      return;
    }
    renderSpark();
  }

  /* Whichever of the two surfaces is on screen. Each of the three returns
     at once when its host is not in the document, so callers never have to
     know which mode is on -- and an async callback landing after somebody
     has switched tools draws nothing rather than into another tool's pane,
     which is the fault `paint()` guards at the top of this module. */
  function renderSpark() {
    if (!BARRY.views.toolkit || BARRY.views.toolkit.tool() !== 'spark') return;
    renderPick(); renderRead(); renderBatch();
  }

  /* One set at a time, or many.

     Two genuinely different jobs rather than two views of one, and the
     same switch Braces puts over the same choice: reading one recording,
     looking at its pulses and deciding what to drop is a thing you do
     while thinking; getting a phase's worth of recordings filed is a thing
     you set off and come back to. It is a switch here rather than a
     separate tool because the scope, the recordings and the exclusion rule
     are the same in both.

     Not disabled while a run is going. The run is a loop over awaits on
     `bulk`, not on the DOM, so stepping over to look at one recording
     while nine are being read costs nothing and loses nothing -- every
     repaint finds its host missing and returns. */
  function modeCard() {
    return el('div', { class: 'card arc-mode' }, [
      el('div', { class: 'seg' }, [
        ['one', 'One recording at a time'],
        ['many', 'Many recordings at once'],
      ].map(([id, label]) => el('button', {
        class: (bulk.on ? 'many' : 'one') === id ? 'active' : '',
        text: label,
        onclick: () => {
          if ((bulk.on ? 'many' : 'one') === id) return;
          bulk.on = id === 'many';
          paint();
        },
      }))),
      el('span', { class: 'hint', text: bulk.on
        ? 'Reads them one after another and files each as it lands. Every '
          + 'window the clipping check grades lost is excluded — anything '
          + 'that wants a judgement is what one at a time is for.'
        : 'Pick a recording, read its pulses, keep or drop what clipped, '
          + 'then file it.' }),
    ]);
  }

  const PHASES = [
    ['Precon', 'Preconditioning'],
    ['Con', 'Conditioning'],
    ['Test', 'Test'],
  ];

  const phaseName = (id) =>
    (PHASES.find((p) => p[0] === id) || [id, id])[1];

  /* The scope control, drawn by both surfaces from one definition.

     A tick in the batch table is about a recording IN THIS SCOPE, and the
     counts above that table read the same `rows` the table does -- §6c's
     rule that whatever narrows a view narrows the numbers above it. Two
     copies of this control would be two places to change the scope and
     one of them would eventually not tell the other. */
  function phaseField() {
    return BARRY.ui.field({
      label: 'Which sessions',
      control: el('div', { class: 'seg' }, PHASES.map(([id, name]) =>
        el('button', {
          /* `.seg button.active` is the house rule -- the segmented control
             marks its chosen one `active`, not `on`. */
          class: q.phase === id ? 'active' : '',
          /* Moving the scope out from under a queue that is being worked
             through would leave the run filing recordings the table no
             longer lists. */
          disabled: bulk.running ? 'disabled' : null,
          text: name,
          onclick: () => pickPhase(id),
        }))),
      /* Said here rather than discovered by clicking through nine animals:
         only preconditioning holds cue PAIRS. The other two are offered
         because looking at their pulses is a reasonable thing to want,
         and because a tool that hides them invites the question. */
      hint: q.phase === 'Precon'
        ? 'The cued run of each preconditioning session — sixteen cue '
          + 'pairs apiece, eight of each pairing.'
        : 'These hold no cue pairs: conditioning pairs one cue with a '
          + 'reinforcer, and test sessions present single cues. The pulses '
          + 'are still worth reading.',
    });
  }

  async function pickPhase(id) {
    if (q.phase === id || bulk.running) return;
    q.phase = id; q.gid = null; reading = null; rows = null;
    renderSpark();
    await loadRows();
    /* Ticks that have left the scope come off with everything else that
       stops meaning anything, through the one function that says why.
       Carrying them would be worse than it sounds: a ticked conditioning
       recording is guaranteed to hold no cue pairs, so it would survive
       the switch only to be unticked again mid-run for a second reason. */
    const live = {};
    for (const r of (rows || [])) live[r.gid] = true;
    let gone = 0;
    for (const gid of Object.keys(bulk.want)) {
      if (live[gid]) continue;
      unpick(gid, 'not one of the ' + phaseName(id).toLowerCase()
                  + ' recordings');
      gone += 1;
    }
    if (gone) {
      toast(gone + ' ticked recording' + (gone === 1 ? '' : 's')
            + ' came off the selection: ' + (gone === 1 ? 'it is' : 'they are')
            + ' not in ' + phaseName(id) + '.', null, 7000);
    }
    renderSpark();
  }

  /* One `.empty-state`, read by both surfaces: same registry, same
     question, same answer, and it says what to do next rather than only
     that there is nothing here. */
  function noRecordings() {
    return el('div', { class: 'empty-state' }, [
      el('p', { text: 'No DEWEY recordings of that kind are in the '
                      + 'registry. Scan the share in Sessions first.' }),
    ]);
  }

  function renderPick() {
    const host = document.getElementById('arcPick');
    if (!host) return;
    host.innerHTML = '';

    host.appendChild(phaseField());

    if (rows === null) { BARRY.skeleton.into(host, 'row', 8); return; }
    if (!rows.length) { host.appendChild(noRecordings()); return; }

    const list = el('div', { class: 'arc-rows' });
    for (const r of rows) {
      const has = banked[r.gid];
      list.appendChild(el('button', {
        class: 'arc-row' + (q.gid === r.gid ? ' on' : '')
               + (r.reachable ? '' : ' off'),
        disabled: r.reachable ? null : 'disabled',
        title: r.reachable ? r.label
          : 'None of this recording’s paths are reachable from this '
            + 'machine, so there is nothing to look at.',
        onclick: () => pickRecording(r.gid),
      }, [
        el('strong', { text: 'J' + r.mouse }),
        el('span', { class: 'arc-row-s',
                     text: (r.phase || '') + (r.phase_n || '') }),
        el('span', { class: 'arc-row-d', text: r.date || '' }),
        has ? el('span', { class: 'flagchip mat',
                           title: has.versions + ' version(s) filed',
                           text: has.n + ' banked' })
            : el('span', { class: 'arc-row-n', text: '—' }),
      ]));
    }
    host.appendChild(list);
  }

  async function pickRecording(gid) {
    q.gid = gid;
    reading = null;
    clip = null;
    /* `dropped` too: it is keyed by pair id like the rest, and a pair id
       restarts at 1 in every recording, so a block removed by hand on the
       last recording would otherwise be removed on this one. */
    excluded = {}; kept = {}; dropped = {}; spans_ = {};
    renderPick();
    renderRead();
    try {
      reading = await api('/api/arc/spark/' + encodeURIComponent(gid));
    } catch (e) {
      reading = { error: e.message };
    }
    if (BARRY.views.toolkit.tool() === 'spark' && q.gid === gid) renderRead();
  }

  function renderRead() {
    const host = document.getElementById('arcRead');
    if (!host) return;
    host.innerHTML = '';

    if (!q.gid) {
      host.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'Pick a recording to read its cue pulses.' }),
      ]));
      return;
    }
    if (!reading) {
      host.appendChild(loader('Reading the pulses',
                              'Events.nev, then the recording’s clock'));
      return;
    }
    if (reading.error) {
      host.appendChild(el('div', { class: 'card' }, [
        el('p', { class: 'hint', text: reading.error }),
      ]));
      return;
    }

    const s = reading.summary || {};
    host.appendChild(el('div', { class: 'card' }, [
      el('div', { class: 'section-label', text: reading.label || '' }),
      chipRow(s),
      lineView(reading),
      clipCard(s),
      pairTable(reading.pairs || []),
      troubles(s, reading.unpaired || []),
      bankBar(s),
    ]));
  }

  /* ------------------------------------------------------------------
     The line view

     Every pulse in the recording on one line, so "where are the events"
     is answered by looking rather than by reading sixteen pairs of
     timestamps. A cue pair is a bar from its opener to the end of cue 2;
     everything else is a tick.

     SVG rather than a canvas: it is a few hundred marks, it has to scale
     with the pane, and each mark wants a title you can hover.
     ------------------------------------------------------------------ */
  const LINE_H = 54;
  const LINE_PAD = 6;

  function lineView(read) {
    const events = read.events || [];
    const pairs = read.pairs || [];
    if (!events.length) return null;

    const last = Math.max(
      events.length ? events[events.length - 1].t : 0,
      pairs.length ? pairs[pairs.length - 1].offset_t : 0) || 1;
    const span = last + 20;
    const W = 1000;                       // viewBox units, scaled by CSS
    const x = (t) => LINE_PAD + (t / span) * (W - LINE_PAD * 2);

    const kids = [];

    // The baseline.
    kids.push(el('line', {
      x1: x(0), x2: x(span), y1: LINE_H - 14, y2: LINE_H - 14,
      class: 'arc-line-axis',
    }));

    /* The pairs first, so the ticks land on top of them. A bar, not two
       ticks: the whole point of a pair is that it is one interval. */
    for (const p of pairs) {
      const bad = clipOf(p.pair_id);
      const excl = exclOf(p.pair_id);
      const n = bad ? Object.keys(bad).length : 0;
      kids.push(el('rect', {
        x: x(p.opener_t), y: 8,
        width: Math.max(1.2, x(p.offset_t) - x(p.opener_t)),
        height: LINE_H - 24,
        class: 'arc-line-pair' + (n || excl.length ? ' bad' : ''),
        onclick: () => showPair(p.pair_id),
      }, [
        el('title', { text: 'Pair ' + p.pair_id + ': ' + p.opener_label
                            + ' → ' + p.closer_label
                            + ' at ' + p.opener_t.toFixed(1) + ' s'
                            + (n ? '\n' + n + ' channel(s) clipped' : '')
                            + (excl.length ? '\n' + excl.length
                               + ' invalidated by hand' : '') }),
      ]));
    }

    /* Every pulse, including the ones that were dropped -- a view of the
       events that showed only the ones that survived would be answering a
       different question than the one somebody verifying them has. */
    for (const e of events) {
      const kind = !e.known ? 'unknown'
        : e.is_mirror ? 'mirror'
        : e.debounced ? 'bounce'
        : (e.label === 'Session') ? 'end'
        : 'cue';
      kids.push(el('line', {
        x1: x(e.t), x2: x(e.t),
        y1: LINE_H - 22, y2: LINE_H - 6,
        class: 'arc-tick ' + kind,
      }, [
        el('title', { text: e.t.toFixed(3) + ' s  ·  ' + e.label
                            + '  (TTL ' + e.ttl + ')'
                            + (e.is_mirror ? '  — mirror, dropped' : '')
                            + (e.debounced ? '  — bounce, dropped' : '')
                            + (!e.known ? '  — not in the vocabulary'
                               : '') }),
      ]));
    }

    const svg = el('svg', {
      class: 'arc-line', viewBox: '0 0 ' + W + ' ' + LINE_H,
      preserveAspectRatio: 'none', 'aria-hidden': 'true',
    }, kids);

    return el('div', { class: 'arc-line-wrap' }, [
      svg,
      el('div', { class: 'arc-line-key' }, [
        keyDot('cue', 'cue'), keyDot('end', 'cue ends'),
        keyDot('mirror', 'mirror'), keyDot('bounce', 'bounce'),
        keyDot('unknown', 'unnamed'),
        el('span', { class: 'spacer' }),
        el('span', { class: 'hint',
                     text: '0–' + Math.round(span) + ' s' }),
      ]),
    ]);
  }

  function keyDot(kind, name) {
    return el('span', { class: 'arc-key-item' }, [
      el('i', { class: 'arc-key-dot ' + kind }),
      el('span', { text: name }),
    ]);
  }

  function showPair(id) {
    const row = document.querySelector('.arc-pair[data-pair="' + id + '"]');
    if (!row) return;
    row.scrollIntoView({ block: 'center' });
    row.classList.add('lit');
    setTimeout(() => row.classList.remove('lit'), 1400);
  }

  function chipRow(s) {
    const chips = [
      ['pairs', s.n_pairs, s.n_pairs ? 'ok' : 'warn'],
      ['TTL pulses', s.n_ttl, ''],
      ['mirrors dropped', s.n_mirror, ''],
      ['bounces dropped', s.n_debounced, ''],
      ['unpaired', s.n_unpaired, s.n_unpaired ? 'warn' : ''],
    ];
    return el('div', { class: 'chip-row' }, chips.map(([name, n, kind]) =>
      el('span', { class: 'flagchip' + (kind ? ' ' + kind : ''),
                   text: n + ' ' + name })));
  }

  /* ------------------------------------------------------------------
     Clipping

     Not run on open. It memory-maps every channel and slices four windows
     out of each pair -- about twelve seconds on a 64-channel recording --
     and the table above is worth reading without it. So it is asked for,
     and the cost is stated before anybody waits for it.
     ------------------------------------------------------------------ */
  const GRADE_CLASS = {
    'partial event loss': 'warn',
    'major event loss': 'warn',
    'event lost': 'bad',
  };

  /* The transition windows' lengths, editable before the check runs.

     Sent as typed and checked on the server, which refuses a length it
     will not measure with a sentence rather than quietly using another --
     a check made at different lengths from the ones on screen is a check
     of windows nobody asked about. */
  function lengthFields() {
    const box = (id, label) => el('label', { class: 'arc-tlen-f' }, [
      el('input', {
        type: 'number', step: '0.1', min: '0.1', max: '5',
        value: String(tq[id]),
        disabled: clipBusy ? 'disabled' : null,
        'aria-label': label,
        onchange: (e) => {
          const v = Number(e.target.value);
          tq[id] = isFinite(v) && e.target.value !== '' ? v : e.target.value;
          renderRead();
        },
      }),
      el('span', { text: label }),
    ]);
    return el('div', { class: 'arc-tlen' }, [
      el('span', { class: 'arc-tlen-k', text: 'Transition windows' }),
      box('before', 's before'),
      box('after', 's after each boundary'),
    ]);
  }

  /* Whether the lengths on screen are the ones the reading was made at. */
  function lengthsChanged() {
    const t = (clip && clip.transition) || {};
    if (!t.measured) return true;
    return Number(tq.before) !== Number(t.before_s)
           || Number(tq.after) !== Number(t.after_s);
  }

  function clipRows(chans) {
    return chans.slice(0, 12).map((c) => el('div', {
      class: 'arc-clip-row',
    }, [
      el('strong', { text: 'CSC' + c.channel }),
      el('span', { class: 'flagchip ' + (GRADE_CLASS[c.grade] || ''),
                   text: c.grade }),
      el('span', { class: 'num',
                   text: c.windows_lost + ' / ' + c.windows_total
                         + ' windows' }),
      el('span', { class: 'num',
                   text: Math.round(c.worst_frac * 100) + '% worst' }),
      el('span', { class: 'hint',
                   text: 'in ' + c.in_events + ' of ' + c.of_events
                         + ' events' }),
    ]));
  }

  /* The grades a step found, counted by channel, worst first. */
  function gradeTally(chans) {
    const by = {};
    for (const c of chans) by[c.grade] = (by[c.grade] || 0) + 1;
    return ['event lost', 'major event loss', 'partial event loss']
      .filter((g) => by[g]).map((g) => [g, by[g]]);
  }

  /* One of the two answers the one read gives. Each is a step somebody
     can see was taken, with its own grades and its own rule, because they
     are two claims -- "this channel lost its baseline" and "this channel
     lost the moment cue 2 began" -- and folding them into one count would
     make neither checkable. */
  function clipStep(kind) {
    const T = kind === 'transition';
    const t = (clip && clip.transition) || {};
    const done = measuredKind(kind);
    const chans = (T ? t.channels : clip.channels) || [];
    const kids = [
      el('div', { class: 'arc-clip-step-h' }, [
        el('span', { class: 'flagchip ' + (done ? 'mat' : 'warn'),
                     text: done ? 'checked' : 'not checked' }),
        el('strong', { text: T ? 'Transition windows checked'
                                : 'State windows checked' }),
        el('span', { class: 'hint', text: T
          ? (done ? t.before_s + ' s before to ' + t.after_s + ' s after '
                    + 'cue 1 starting, cue 2 starting and cue 2 ending'
                  : '')
          : 'baseline, cue 1, cue 2 and after cue 2, ten seconds each' }),
      ]),
    ];
    if (!done) {
      kids.push(el('p', { class: 'hint arc-clip-step-why',
        text: (t.why ? t.why + ' ' : '')
              + 'This reading has no answer for the transition windows, '
              + 'which is not the same as a clean one: nothing has looked '
              + 'at them. Check again to measure them.' }));
      return el('div', { class: 'arc-clip-step ' + kind }, kids);
    }
    const g = gradeTally(chans);
    kids.push(el('div', { class: 'chip-row arc-clip-grades' },
      g.length ? g.map(([grade, n]) => el('span', {
        class: 'flagchip ' + (GRADE_CLASS[grade] || ''),
        text: n + ' channel' + (n === 1 ? '' : 's') + ' · ' + grade }))
        : [el('span', { class: 'flagchip mat',
                        text: 'no channel lost a window' })]));
    /* The rule, stated where the numbers are. A grade nobody can check is
       a grade nobody should act on. */
    kids.push(el('p', { class: 'hint', text: T
      ? 'A transition window counts as lost on a channel that spent '
        + (t.lost_ms || 50) + ' ms or more at its rail inside it — the '
        + 'same 50 ms as the state windows, in time rather than as a '
        + 'fraction, so a three-second window is not held to a stricter '
        + 'standard than a ten-second one. One of the three is a partial '
        + 'loss, two is major, all three is every boundary of the event '
        + 'gone on that channel.'
      : 'A window counts as lost where the amplifier sat within '
        + Math.round((1 - (clip.fraction || 0.995)) * 1000) / 10
        + '% of its rail for ' + (clip.min_run || 16)
        + ' samples or more, for half a percent of the window or one '
        + 'unbroken 50 ms. One window of the four is a partial loss, two '
        + 'or three is major, all four is the event gone on that '
        + 'channel.' }));
    if (T) {
      const um = Object.keys(t.unmeasured || {}).length;
      if (um) {
        kids.push(el('p', { class: 'hint arc-clip-step-why',
          text: um + ' cue pair' + (um === 1 ? ' has' : 's have')
                + ' a transition window that could not be cut to the '
                + 'sample on some channel — a break in the clock or a '
                + 'short record inside it. Those windows were not '
                + 'measured, and Coupling refuses the same windows for '
                + 'the same reason.' }));
      }
    }
    if (chans.length) {
      kids.push(el('div', { class: 'arc-clip-rows' }, clipRows(chans)));
      if (chans.length > 12) {
        kids.push(el('p', { class: 'hint',
                            text: chans.length - 12 + ' more, worst first.' }));
      }
    }
    return el('div', { class: 'arc-clip-step ' + kind }, kids);
  }

  function clipCard(s) {
    if (!s.n_pairs) return null;
    if (!clip) {
      return el('div', { class: 'arc-clipbar' }, [
        el('span', { class: 'hint',
          text: 'Nothing has checked these windows for clipping yet. It '
                + 'reads all ' + (reading.summary.n_channels || '')
                + ' channels once and answers twice: the four state '
                + 'windows of each pair, and the three transition windows '
                + 'around its boundaries — about ten seconds.' }),
        lengthFields(),
        el('div', { class: 'spacer' }),
        el('button', {
          class: 'btn ghost sm' + (clipBusy ? ' off' : ''),
          disabled: clipBusy ? 'disabled' : null,
          text: clipBusy ? 'Reading…' : 'Check for clipping',
          onclick: () => doClip(false),
        }),
      ]);
    }

    const rd = clip.read || {};
    return el('div', { class: 'arc-clip' }, [
      el('div', { class: 'section-label',
                  text: 'Clipping · one read'
                        + (rd.channels ? ' of ' + rd.channels + ' channels'
                                       : '')
                        + ', two answers' }),
      clipStep('state'),
      clipStep('transition'),
      /* The consequence, beside the measurement rather than three clicks
         away from it. This is the sentence the whole clipping check is
         for, and until it was written here the only place the exclusion
         appeared at all was a chip in the pair table reading "56 clipped"
         -- a count, not a claim about what happens next. */
      dropSay(),
      el('div', { class: 'arc-clipbar arc-clip-again' }, [
        lengthFields(),
        el('div', { class: 'spacer' }),
        el('button', {
          class: 'btn ghost sm' + (clipBusy ? ' off' : ''),
          disabled: (clipBusy || !lengthsChanged()) ? 'disabled' : null,
          title: lengthsChanged()
            ? 'Read the channels again and measure the transition windows '
              + 'at the lengths shown. The state windows come back the '
              + 'same.'
            : 'These are the lengths this reading was made at.',
          text: clipBusy ? 'Reading…' : 'Check again at these lengths',
          onclick: () => doClip(true),
        }),
      ]),
    ].filter(Boolean));
  }

  /* What the exclusion currently comes to, in one sentence, in the words
     the analysis uses. Shown wherever somebody is about to act on it: in
     the clipping card, and again on the bar they file from. Both kinds,
     each counted, because both go to the bank. */
  function dropSay() {
    const t = dropTally();
    if (!t.n) {
      return el('p', { class: 'arc-drop-say none',
        text: 'Nothing is excluded: every channel goes into the '
              + 'connectivity analysis on every pair'
              + (measuredKind('transition')
                 ? ', in every state and every transition window.'
                 : '. The transition windows have not been checked.') });
    }
    const ts = dropTally('state'), tt = dropTally('transition');
    return el('div', { class: 'arc-drop-say' }, [
      el('strong', { text: t.chans + ' channel' + (t.chans === 1 ? '' : 's') }),
      el('span', { text: 'will be excluded from the connectivity analysis, '
                         + 'across ' + t.pairs + ' of the '
                         + ((reading.pairs || []).length) + ' cue pairs — '
                         + t.n + ' channel-event' + (t.n === 1 ? '' : 's')
                         + ' in all: ' + ts.n + ' in the state windows and '
                         + (measuredKind('transition')
                            ? tt.n + ' at the transitions'
                            : 'none at the transitions, which have not been '
                              + 'checked')
                         + '. A channel is excluded only in the windows '
                         + 'where it lost something, not on the recording '
                         + 'as a whole.' }),
      el('div', { class: 'spacer' }),
      el('button', {
        class: 'btn ghost sm', text: 'Keep or drop them',
        title: 'Open Clean on the traces, where each flagged channel can '
               + 'be kept against the measurement and each saturated '
               + 'stretch trimmed or widened.',
        onclick: () => openClean(null),
      }),
    ]);
  }

  async function doClip(again) {
    if (clipBusy || !q.gid) return;
    clipBusy = true;
    renderRead();
    const asked = q.gid;
    try {
      const got = await apiPost('/api/arc/spark/'
                                + encodeURIComponent(q.gid) + '/clipping',
                                { before_s: tq.before, after_s: tq.after,
                                  again: !!again });
      /* Noted whether or not this recording is still the one on screen:
         what is being recorded is that the SERVER now holds a reading for
         it, which is true regardless of what the panel moved on to. See
         `clipSeen`. */
      clipSeen[asked] = true;
      if (q.gid === asked) {
        clip = got;
        /* The measurement lands as a decision: every channel that lost a
           window is dropped from that pair unless somebody says otherwise.
           Done here and not at banking time so the count on screen and the
           count in the POST are the same number from the moment it is
           known -- a panel that says "9 dropped" and banks nothing is a
           panel that has lied about the one thing it is for. */
        recomputeAll();
      }
    } catch (e) {
      toast('Could not read the clipping: ' + e.message, 'err', 8000);
      reportClientError('arc.spark.clipping', e.message, e.stack);
    } finally {
      clipBusy = false;
      if (BARRY.views.toolkit.tool() === 'spark') renderRead();
    }
  }

  function pairTable(pairs) {
    if (!pairs.length) {
      return el('p', { class: 'hint',
        text: 'No cue pairs here. Conditioning and test sessions hold '
              + 'none — that is what they are, not a failure to find '
              + 'them.' });
    }
    const head = el('div', { class: 'arc-pair arc-pair-hd' }, [
      el('span', { text: '#' }),
      el('span', { text: 'pairing' }),
      el('span', { text: 'cue 1' }),
      el('span', { text: 'cue 2' }),
      el('span', { text: 'gap' }),
      el('span', { text: 'cue 2 ends' }),
      el('span', { text: 'lost' }),
    ]);
    const body = el('div', { class: 'arc-pairs' },
      pairs.map((p) => el('div', { class: 'arc-pair', 'data-pair': p.pair_id }, [
        el('span', { class: 'arc-pair-i', text: String(p.pair_id) }),
        el('span', { text: p.opener_label + ' → ' + p.closer_label }),
        el('span', { class: 'num', text: p.opener_t.toFixed(3) }),
        el('span', { class: 'num', text: p.closer_t.toFixed(3) }),
        el('span', { class: 'num', text: p.gap_s.toFixed(4) }),
        /* Read off the rig's own end-of-pulse mark where there is one, and
           derived from the gap where there is not. Which of the two it was
           is on the row, because a boundary that was measured and one that
           was assumed are different claims. */
        el('span', { class: 'num' + (p.offset_from === 'mark'
                                     ? '' : ' arc-derived'),
                     title: p.offset_from === 'mark'
                       ? 'From the rig’s end-of-pulse mark'
                       : 'Derived: the closer plus the gap, because no '
                         + 'end mark was found',
                     text: p.offset_t.toFixed(3) }),
        lostCell(p),
      ])));
    return el('div', {}, [head, body]);
  }

  /* What this pair is about to lose, and the way in to changing it.
   *
   * Two numbers, and they are different claims: the channels the
   * measurement says lost a window of this event, and the ones somebody
   * has looked at and kept anyway. Both are buttons, and both open Clean
   * ON THIS PAIR rather than on the first one -- the answer to "is that
   * right?" is only ever on the traces, and a row that names a problem
   * should be the shortest way to it.
   *
   * It used to be the other way round: the chip SET the exclusion when
   * clicked, so a measured loss that nobody clicked reached the bank as a
   * channel in perfect health. */
  function lostCell(p) {
    if (!clip) return el('span', { class: 'hint', text: '—' });
    const going = droppingOf(p.pair_id);
    const overruled = overruledOf(p.pair_id);
    /* The transitions, counted apart: a pair can be clean in its four
       chunks and have lost the moment cue 2 began on a wire, and that is
       its own chip rather than a number folded into the first. */
    const tGoing = droppingOf(p.pair_id, 'transition');
    let tBlocks = 0;
    for (const c of tGoing) tBlocks += goneOf(p.pair_id, c, 'transition').length;
    const tChip = tBlocks ? el('button', {
      class: 'mini flagchip warn arc-lost-t',
      title: tBlocks + ' transition block(s) across ' + tGoing.length
             + ' channel(s) will be excluded for this pair: '
             + tGoing.map((c) => 'CSC' + c + ' ('
                          + goneOf(p.pair_id, c, 'transition')
                            .map((w) => WINDOW_SAY[w]).join(', ') + ')')
               .join('; ') + '. Click to look at them on the traces.',
      text: tBlocks + ' at transitions',
      onclick: () => openClean(p.pair_id, 'transition'),
    }) : null;
    if (!going.length && !overruled.length) {
      if (tChip) return el('span', { class: 'arc-lost' }, [tChip]);
      return el('span', { class: 'flagchip mat', text: 'clean' });
    }
    let blocks = 0;
    for (const c of going) blocks += goneOf(p.pair_id, c).length;
    const whole = going.filter(
      (c) => goneOf(p.pair_id, c).length >= WINDOWS_4.length).length;
    return el('span', { class: 'arc-lost' }, [
      going.length ? el('button', {
        class: 'mini flagchip ' + (whole ? 'bad' : 'warn'),
        title: blocks + ' block(s) across ' + going.length
               + ' channel(s) will be excluded from the connectivity '
               + 'analysis for this pair: '
               + going.map((c) => 'CSC' + c + ' ('
                                  + goneOf(p.pair_id, c).join(', ') + ')')
                   .join('; ')
               + '. Click to look at them on the traces.',
        text: blocks + ' block' + (blocks === 1 ? '' : 's'),
        onclick: () => openClean(p.pair_id),
      }) : null,
      overruled.length ? el('button', {
        class: 'mini arc-keep',
        title: 'Kept against the measurement: CSC '
               + overruled.join(', ')
               + '. Click to look at them on the traces.',
        text: overruled.length + ' kept',
        onclick: () => openClean(p.pair_id),
      }) : null,
      tChip,
    ].filter(Boolean));
  }

  /* Clean, landed on a particular pair. `null` means the first one, which
     is what the bar button has always done. `view` opens it on the state
     or the transition blocks; state when not said. */
  function openClean(pairId, view) {
    const list = (reading && reading.pairs) || [];
    const i = pairId == null ? 0
      : list.findIndex((x) => String(x.pair_id) === String(pairId));
    BARRY.arcclean.enter(q.gid, reading, clip, i < 0 ? 0 : i, view);
  }

  function troubles(s, unpaired) {
    const bits = [];
    if (s.n_unknown) {
      bits.push('TTL codes nobody has named: '
                + (s.unknown_codes || []).join(', ')
                + '. They are counted and ignored.');
    }
    const near = unpaired.filter((u) => u.near_miss);
    if (near.length) {
      bits.push(near.length + ' cue(s) had a partner close to ten seconds '
                + 'away but outside tolerance — worth a look.');
    }
    if (s.gap_mean != null) {
      bits.push('Gaps ran ' + s.gap_min.toFixed(4) + '–'
                + s.gap_max.toFixed(4) + ' s against an expected '
                + s.expected_gap_s + ' s.');
    }
    if (!bits.length) return null;
    return el('p', { class: 'hint', text: bits.join(' ') });
  }

  function bankBar(s) {
    const has = banked[q.gid];
    const bits = [];
    if (has) {
      bits.push(el('span', { class: 'hint',
        text: 'Filed already: ' + has.n + ' pairs, version '
              + (has.version != null ? has.version : '?') + ' of '
              + has.versions + '. Filing again adds a version rather than '
              + 'a second set.' }));
    }
    /* Said again here, because this is the button that writes it. The
       clipping card is where somebody reads the measurement; this is
       where they commit to it, and those are far enough apart on a long
       pane to be two different sittings. */
    if (clip) bits.push(dropSay());
    bits.push(el('div', { class: 'spacer' }));
    /* Two ways to look at the pairs before filing them, and they answer
       different questions -- "are these the right pairs" and "which of
       them is still usable". Secondary to filing, so they sit before it:
       the primary action is last. */
    bits.push(el('button', {
      class: 'btn ghost sm',
      disabled: s.n_pairs ? null : 'disabled',
      text: 'Confirm on the traces',
      title: 'Open the recording with every pulse drawn and the four '
             + 'analysis windows shaded.',
      onclick: () => BARRY.arcconfirm.enter(q.gid, reading),
    }));
    bits.push(el('button', {
      class: 'btn ghost sm',
      disabled: (s.n_pairs && clip) ? null : 'disabled',
      text: 'Clean on the traces',
      title: clip ? 'Open the recording with the saturated stretches marked '
                    + 'on the channels that saturated, and keep or drop '
                    + 'each of them.'
                  : 'Check for clipping first — there is nothing to '
                    + 'mark until something has measured it.',
      onclick: () => openClean(null),
    }));
    bits.push(el('button', {
      class: 'btn' + (busy ? ' off' : ''),
      disabled: (busy || !s.n_pairs) ? 'disabled' : null,
      text: has ? 'File a new version' : 'File these pairs',
      title: s.n_pairs ? '' : 'There are no pairs here to file.',
      onclick: doBank,
    }));
    return el('div', { class: 'head-actions arc-bank' }, bits);
  }

  async function doBank() {
    if (busy || !q.gid) return;
    busy = true;
    renderRead();
    try {
      const res = await apiPost('/api/arc/spark/' + encodeURIComponent(q.gid)
                                + '/bank', { excluded: excluded,
                                             kept: keptAll() });
      /* The exclusion is named in the receipt, not only in the request.
         What was dropped is the part of this that is a judgement, and a
         judgement nobody was told about is one nobody can dispute. */
      const t = dropTally();
      toast('Filed ' + res.n + ' cue pairs'
            + (t.n ? ', excluding ' + t.chans + ' channel(s) across '
                     + t.pairs + ' of them' : ''), 'ok', t.n ? 7000 : 4000);
      BARRY.activity.log('arc.spark.bank', {
        gid: q.gid, n: res.n, excluded: t.n, channels: t.chans,
        pairs: t.pairs,
      });
      await loadRows();
    } catch (e) {
      toast('That did not file: ' + e.message, 'err', 8000);
      reportClientError('arc.spark.bank', e.message, e.stack);
    } finally {
      busy = false;
      if (BARRY.views.toolkit.tool() === 'spark') {
        renderPick(); renderRead();
      }
    }
  }

  /* ==================================================================
     Many recordings at once

     WHY THIS DRIVES THE ROUTES AND LEAVES THE PANEL'S STATE ALONE

     `excluded`, `kept`, `dropped` and `spans_` are keyed by PAIR ID, and
     a pair id restarts at 1 in every recording -- the same trap as a
     mouse-and-session number, which names many different recordings and
     passes every check vacuously. A batch writing into those structures
     would have nine recordings all claiming pair 1, and the last one
     through the loop would decide what the first one had banked.

     So the batch holds nothing of its own about a recording except what
     it found. It calls the three per-recording routes in order, works the
     exclusion out with `exclusionFrom` -- a pure function of the reading
     -- and hands that straight to the bank. Opening a recording by hand
     afterwards finds the interactive panel exactly as it was left.

     It also means the batch and the single-recording panel cannot drift
     apart about what gets dropped: `exclusionFrom` produces the list
     `recompute` produces with no hand overrules, which is what a batch has,
     because nobody is at the traces.
     ================================================================== */

  /* What one recording costs, before it is spent.

     `READ_S` is the Events.nev read, and it is paid TWICE per recording:
     once here, to see what was found and decide whether there is anything
     to file at all, and once inside the bank route, which re-reads the
     recording rather than trusting a client's copy of it. Driving the
     existing per-recording routes one at a time is what buys that. It is
     small beside the clipping and it is honest to count it.

     `CLIP_S` is the clipping scan: every channel, four windows a pair.
     Both are MEASURED on this data rather than guessed -- 0.1 to 0.5 s for
     the .nev read of a DEWEY preconditioning recording, 11.6 s for the
     clipping scan of a 64-channel one -- and rounded up, because a job
     that finishes sooner than it said is a good surprise and the other way
     round is not. */
  const READ_S = 1;
  const CLIP_S = 12;

  function costOf(n) {
    const per = READ_S * 2 + (bulk.clip ? CLIP_S : 0);
    return { n: n, per: per, seconds: n * per };
  }

  function howLong(s) {
    if (s < 90) return 'about ' + Math.round(s) + ' seconds';
    const m = Math.round(s / 60);
    return 'about ' + m + ' minute' + (m === 1 ? '' : 's');
  }

  /* Whether this run will have a clipping reading for a recording.

     The toggle, OR the server already holding one for it. See `clipSeen`:
     the bank route folds whatever the server holds into the entry, so
     asking for it is the only way the exclusion this panel sends can
     agree with the measurement that entry will carry. */
  const wantsClip = (gid) => bulk.clip || !!clipSeen[gid];

  /* Can this row be run at all. Not a judgement about whether it is worth
     running -- that is `skipReason`, and it cannot be answered until the
     recording has been read. */
  const canBatch = (r) => !!r.reachable;

  /* A tick coming off by itself, with the reason kept.

     A ticked row means STILL TO DO, and that sentence is only true if
     something takes the tick off when a recording turns out to have
     nothing to do. The reason goes in `bulk.off` and onto the row, because
     a tick that vanishes with nothing said is worse than one that stays
     and is wrong. */
  function unpick(gid, why) {
    delete bulk.want[gid];
    bulk.off[gid] = why;
  }

  /* Why a ticked recording turns out to have nothing to do. '' when there
     is something.

     Two answers, and they are asked in this order because the first is
     about the recording and the second is about the bank:

       no cue pairs      Conditioning and test sessions hold none. That is
                         what they are, not a failure to find them -- so
                         this is a row coming off the list, not a failure.
       already filed     Filed, and the read came back with the same number
                         of pairs, and this run has no clipping reading to
                         add. A second version identical to the first is
                         not free: version numbers are not unique across
                         machines, and every pointless one makes the
                         lineage harder to read.

     The clipping clause is the honest limit of what can be known from
     here. The bank's summary says how many events an entry holds, not
     whether it was filed with a clipping judgement, so a run that HAS one
     files -- the measurement may be new information and there is no way to
     ask. Somebody who wants the cheap second pass has "Only the N never
     filed" on the bar, which answers it before anything is read. */
  function skipReason(gid, read) {
    const s = (read && read.summary) || {};
    if (!s.n_pairs) {
      return 'no cue pairs — conditioning and test sessions hold none';
    }
    const has = banked[gid];
    if (has && has.n === s.n_pairs && !wantsClip(gid)) {
      return 'already filed, and the same ' + s.n_pairs + ' pairs came '
             + 'back — a new version would say nothing new';
    }
    return '';
  }

  /* The exclusion a batch run files: the measurement, and nothing else.

     A pure function of the two readings. It touches none of the panel's
     decision structures for the reason at the top of this section, and it
     produces exactly what `recompute` produces when nobody has overruled
     anything -- keyed by window, which is the shape the bank and the
     analysis both take, because a channel ruined in the baseline is
     perfectly good in both cues. */
  function exclusionFrom(pairs, clipping, kind) {
    /* `kind` picks which answer of the one read: the state windows (the
       default, and all this ever returned before transitions), or the
       transition windows -- only when they were measured, since a reading
       that did not measure them has nothing to exclude there and saying
       otherwise would invent a decision. `exclusionBoth` is what a batch
       files. */
    const t = (clipping && clipping.transition) || null;
    const by = kind === 'transition'
      ? ((t && t.measured && t.by_pair) || {})
      : ((clipping && clipping.by_pair) || {});
    const out = {};
    for (const p of (pairs || [])) {
      const pid = String(p.pair_id);
      const bad = by[pid];
      if (!bad) continue;
      const per = {};
      for (const csc of Object.keys(bad)) {
        for (const w of ((bad[csc] || {}).windows || [])) {
          (per[w] = per[w] || []).push(Number(csc));
        }
      }
      for (const w of Object.keys(per)) per[w].sort((a, b) => a - b);
      if (Object.keys(per).length) out[pid] = per;
    }
    return out;
  }

  /* Both answers, merged into the one per-window dict the bank takes --
     the window names never collide, so this is a union of keys. */
  function exclusionBoth(pairs, clipping) {
    const out = exclusionFrom(pairs, clipping, 'state');
    const tr = exclusionFrom(pairs, clipping, 'transition');
    for (const pid of Object.keys(tr)) {
      out[pid] = Object.assign(out[pid] || {}, tr[pid]);
    }
    return out;
  }

  function blocksIn(excl, kind) {
    const only = kind ? namesOf(kind) : null;
    let n = 0;
    for (const pid in (excl || {})) {
      for (const w in excl[pid]) {
        if (only && only.indexOf(w) < 0) continue;
        n += excl[pid][w].length;
      }
    }
    return n;
  }

  /* Which cue opened onto which, counted off this recording.

     Never assumed. The pairings are counterbalanced, so which cue opens
     onto which is a fact about THIS recording; a hard-coded answer would
     be right for half the cohort and confidently wrong for the other.

     `summary.by_pair_type` is the module that owns the fact answering it,
     so that is what is read. The tally off the pairs is the fallback for a
     payload from a server that has not been restarted yet -- the same
     falling-back Braces does over `newest`. */
  function pairingsOf(read) {
    const said = ((read || {}).summary || {}).by_pair_type;
    if (said && said.length) {
      return said.map((row) => ({
        what: String(row[0]).replace(' -> ', ' \u2192 '), n: row[1],
      }));
    }
    const by = {};
    for (const p of ((read || {}).pairs || [])) {
      const k = p.opener_label + ' \u2192 ' + p.closer_label;
      by[k] = (by[k] || 0) + 1;
    }
    return Object.keys(by).sort().map((k) => ({ what: k, n: by[k] }));
  }

  /* What one recording turned out to hold, frozen at the moment it
     finished. Kept on `bulk.state` rather than re-derived when the
     disclosure opens, because by then the run is three recordings further
     on and `reading` belongs to somebody else. */
  function foundOf(read, clipping, excl, res) {
    const s = (read && read.summary) || {};
    return {
      label: (read && read.label) || '',
      n_pairs: s.n_pairs || 0,
      n_unpaired: s.n_unpaired || 0,
      pairings: pairingsOf(read),
      gap_min: s.gap_min, gap_max: s.gap_max,
      gap_expect: s.expected_gap_s,
      clipped: clipping ? ((clipping.channels || []).length) : null,
      /* The transition answer of the same read: null when it was not
         measured, which the disclosure says as "not measured" rather than
         as a clean zero. */
      t_clipped: (clipping && clipping.transition
                  && clipping.transition.measured)
        ? ((clipping.transition.channels || []).length) : null,
      t_blocks: excl ? blocksIn(excl, 'transition') : 0,
      blocks: excl ? blocksIn(excl) : 0,
      pairs_hit: excl ? Object.keys(excl).length : 0,
      filed: res ? res.n : null,
      version: res ? ((res.entry || {}).version) : null,
    };
  }

  /* ---------------- the table ---------------- */

  function renderBatch() {
    const host = document.getElementById('arcBatch');
    if (!host) return;
    host.innerHTML = '';

    const card = el('div', { class: 'card arc-batch' });
    card.appendChild(el('div', { class: 'section-label',
                                 text: 'Read many recordings' }));
    card.appendChild(phaseField());

    if (rows === null) {
      card.appendChild(el('div', { class: 'arc-batch-rows' }));
      host.appendChild(card);
      BARRY.skeleton.into(card.querySelector('.arc-batch-rows'), 'row', 8);
      return;
    }
    if (!rows.length) {
      card.appendChild(noRecordings());
      host.appendChild(card);
      return;
    }

    card.appendChild(batchCost());
    card.appendChild(batchBar());
    const said = batchOff();
    if (said) card.appendChild(said);

    const tbl = el('div', { class: 'arc-batch-rows' });
    for (const r of rows) tbl.appendChild(batchRow(r));
    card.appendChild(tbl);
    host.appendChild(card);
  }

  /* Cost, before it is spent -- Panorama's line, in Spark's words.

     The size of the job and the size of a step, both, because the second
     is what makes "stop after this one" mean anything: whoever sets this
     off should know before they do that it goes one recording at a time
     and that what is already filed stays filed. */
  function batchCost() {
    const n = (rows || []).filter((r) => bulk.want[r.gid]).length;
    const c = costOf(n);
    const line = el('div', { class: 'arc-batch-cost' }, [
      el('strong', { text: n ? howLong(c.seconds)
                             : 'Nothing is ticked yet' }),
      el('label', { class: 'toggle' + (bulk.clip ? ' on' : '') }, [
        el('input', {
          type: 'checkbox',
          checked: bulk.clip ? 'checked' : null,
          disabled: bulk.running ? 'disabled' : null,
          /* The head, not the table: the toggle changes what the run
             costs and nothing about how a row looks. */
          onchange: (e) => {
            bulk.clip = !!e.target.checked;
            paintBatchHead();
          },
        }),
        el('span', { text: 'Check for clipping too' }),
      ]),
      el('p', { class: 'hint arc-batch-say', text: n
        ? n + ' recording' + (n === 1 ? '' : 's') + ', one at a time — '
          + 'each reads its Events.nev'
          + (bulk.clip
             ? ', measures clipping across every channel in one read — '
               + 'the four state windows of each pair and its three '
               + 'transition windows, ' + tq.before + ' s before to '
               + tq.after + ' s after each boundary (about twelve '
               + 'seconds) — '
             : ' — ')
          + 'then files the pairs, which reads the file once more. '
          + 'You can stop after any one of them, and what has been filed '
          + 'stays filed.'
        : 'Tick the recordings to read. Nothing is read until you do, and '
          + 'the cost of the run appears here before it starts.' }),
    ]);
    if (!bulk.clip) {
      /* The consequence of the toggle, beside the toggle. Filing without
         measuring is a real choice -- the pairs are the point and the
         clipping can be added in a later version -- but an entry with no
         exclusion is an entry claiming every channel was fine, and that
         claim should not be made by accident. */
      line.appendChild(el('p', { class: 'hint arc-batch-say arc-batch-warn',
        text: 'Without it, each entry is filed claiming every channel is '
              + 'usable on every pair. Recordings this page has already '
              + 'measured are the exception — the reading is still on the '
              + 'server and comes straight back, so theirs is filed.' }));
    }
    return line;
  }

  function batchBar() {
    const list = rows || [];
    const ready = list.filter(canBatch);
    const fresh = ready.filter((r) => !banked[r.gid]);
    const n = list.filter((r) => bulk.want[r.gid]).length;

    const bar = el('div', { class: 'arc-batch-bar' });
    /* Three shortcuts, all ghost. Braces draws the equivalent three
       filled, and §2 is the tie-breaker: one primary per surface, and on
       this surface it is the run. */
    bar.appendChild(el('button', {
      class: 'btn ghost sm', disabled: bulk.running ? 'disabled' : null,
      text: 'Every readable recording',
      title: 'Ticks every recording in this phase whose files are on a '
             + 'drive this machine can reach.',
      onclick: () => {
        for (const r of ready) bulk.want[r.gid] = true;
        renderBatch();
      },
    }));
    bar.appendChild(el('button', {
      class: 'btn ghost sm', disabled: bulk.running ? 'disabled' : null,
      text: 'Clear',
      onclick: () => { bulk.want = {}; renderBatch(); },
    }));
    /* The one somebody wants on a second pass. "Every readable recording"
       ticks one that has been filed as readily as one that has not, so a
       second run over a phase re-reads the lot. */
    bar.appendChild(el('button', {
      class: 'btn ghost sm',
      disabled: (bulk.running || !fresh.length) ? 'disabled' : null,
      text: 'Only the ' + fresh.length + ' never filed',
      title: 'Every readable recording in this phase with no cue pairs in '
             + 'the Event Bank yet.',
      onclick: () => {
        for (const r of fresh) bulk.want[r.gid] = true;
        renderBatch();
      },
    }));
    bar.appendChild(el('span', { class: 'hint arc-batch-count',
                                 text: countSay() }));
    bar.appendChild(el('div', { class: 'spacer' }));
    if (bulk.running) {
      bar.appendChild(el('button', {
        class: 'btn ghost sm', text: 'Stop after this one',
        title: 'The recording being read now is finished and filed. '
               + 'Everything after it stays ticked.',
        disabled: bulk.stop ? 'disabled' : null,
        onclick: () => { bulk.stop = true; renderBatch(); },
      }));
    } else {
      bar.appendChild(el('button', {
        class: 'btn', disabled: n ? null : 'disabled',
        text: 'Read and file ' + n + ' recording' + (n === 1 ? '' : 's'),
        title: n ? '' : 'Tick a recording first.',
        onclick: runBatch,
      }));
    }
    return bar;
  }

  /* The counts over the table, read off the same list the table draws --
     §6c, a count has to describe the list underneath it. */
  function countSay() {
    const list = rows || [];
    const n = list.filter((r) => bulk.want[r.gid]).length;
    const ready = list.filter(canBatch).length;
    const done = list.filter(
      (r) => (bulk.state[r.gid] || {}).state === 'done').length;
    return n + ' of ' + list.length + ' ticked \u00b7 ' + ready
           + ' can be read here' + (done ? ' \u00b7 ' + done + ' filed' : '');
  }

  /* What came off the selection by itself, once, above the table.

     Said here as well as on each row because the rows scroll and this is
     the number somebody needs while the run is going: how much of what
     they ticked turned out to be nothing to do.

     Scoped to the recordings the table is showing, for §6c's reason that a
     count has to describe the list underneath it -- a recording unticked
     for leaving the scope is not in this list, so naming it here would be
     a line about rows nobody can see, under a gid nobody can read. */
  function batchOff() {
    const live = {};
    for (const r of (rows || [])) live[r.gid] = true;
    const gids = Object.keys(bulk.off).filter((g) => live[g]);
    if (!gids.length) return null;
    return el('p', { class: 'hint arc-batch-off',
      text: gids.length + ' tick' + (gids.length === 1 ? '' : 's')
            + ' came off by ' + (gids.length === 1 ? 'itself' : 'themselves')
            + ': ' + gids.map((g) => labelOf(g) + ' — ' + bulk.off[g])
                .join('; ') + '.' });
  }

  function labelOf(gid) {
    const r = (rows || []).find((x) => x.gid === gid);
    if (!r) return gid;
    return 'J' + r.mouse + ' ' + (r.phase || '') + (r.phase_n || '');
  }

  function batchRow(r) {
    const st = bulk.state[r.gid] || {};
    const ok = canBatch(r);
    const has = banked[r.gid];
    return el('div', {
      class: 'arc-batch-row' + (bulk.want[r.gid] ? ' on' : '')
             + (ok ? '' : ' away') + (st.state ? ' ' + st.state : ''),
      // So one row can be rewritten without rebuilding the table.
      'data-gid': r.gid,
    }, [
      el('input', {
        type: 'checkbox',
        disabled: (bulk.running || !ok) ? 'disabled' : null,
        checked: bulk.want[r.gid] ? 'checked' : null,
        title: ok ? r.label
          : 'None of this recording’s paths are reachable from this '
            + 'machine, so there is nothing to read.',
        onchange: (e) => {
          if (e.target.checked) {
            bulk.want[r.gid] = true;
            /* Ticking it again is somebody overruling whatever took the
               tick off, so the reason goes with it rather than sitting
               over the table contradicting the row. */
            delete bulk.off[r.gid];
          } else {
            delete bulk.want[r.gid];
            delete bulk.off[r.gid];
          }
          /* The row and the head, never the table. Thirty-three rows in a
             52vh box scroll, and rebuilding them would send somebody back
             to the top on every third tick -- the same reason
             `paintBatchRow` exists for the run. */
          paintBatchRow(r.gid, true);
          paintBatchHead();
        },
      }),
      el('span', { class: 'nm', text: 'J' + r.mouse }),
      el('span', { class: 'ss', text: (r.phase || '') + (r.phase_n || '') }),
      el('span', { class: 'dt', text: r.date || '' }),
      el('span', { class: 'bk',
                   title: has ? has.versions + ' version(s) filed' : '',
                   text: has ? has.n + ' banked' : '\u2014' }),
      /* What it is doing, or why it cannot be run at all. A row that
         cannot is shown and dimmed rather than hidden: the answer to "why
         is that one not ticked" has to be on the screen. */
      el('span', { class: 'st', text: st.msg
        || (ok ? '' : 'not on a drive this machine can reach') }),
      foundBox(r.gid),
    ].filter(Boolean));
  }

  /* The disclosure: what that one recording turned out to hold.

     Drawn the moment that recording finishes rather than when the queue
     does, which is the whole point of it -- "what pairings did that one
     have" is a question people have while the rest is still being read.
     `bulk.open` is what survives the repaint at the end of the run. */
  function foundBox(gid) {
    const f = (bulk.state[gid] || {}).found;
    if (!f) return null;
    const facts = [
      ['pairs', f.n_pairs + (f.n_unpaired
        ? '  \u00b7  ' + f.n_unpaired + ' cue(s) left unpaired' : '')],
      ['pairings', f.pairings.length
        ? f.pairings.map((p) => p.what + ' \u00d7' + p.n).join('  \u00b7  ')
        : '\u2014'],
      ['gap', f.gap_min != null
        ? f.gap_min.toFixed(4) + '\u2013' + f.gap_max.toFixed(4)
          + ' s against an expected ' + f.gap_expect + ' s'
        : '\u2014'],
      ['clipping', f.clipped == null
        ? 'not measured on this run'
        : f.clipped + ' channel(s) lost a state window'
          + (f.t_clipped == null
             ? '; the transition windows were not measured'
             : '; ' + f.t_clipped + ' lost a transition window')],
      ['excluded', f.clipped == null ? '\u2014'
        : (f.blocks
           ? f.blocks + ' block(s) across ' + f.pairs_hit + ' pair(s)'
             + (f.t_blocks ? ', ' + f.t_blocks + ' of them at transitions'
                           : '')
           : 'nothing — every channel goes into the analysis')],
      ['filed', f.filed == null ? 'nothing was filed'
        : f.filed + ' cue pairs'
          + (f.version != null ? ', version ' + f.version : '')],
    ];
    const kids = [
      el('summary', {}, [
        el('span', { text: 'What it found' }),
        el('span', { class: 'arc-batch-tag',
                     text: f.n_pairs + ' pairs' }),
      ]),
    ];
    const grid = el('div', { class: 'arc-batch-facts' });
    for (const [k, v] of facts) {
      grid.appendChild(el('span', { class: 'arc-batch-fact-k', text: k }));
      grid.appendChild(el('span', { class: 'arc-batch-fact-v', text: v }));
    }
    kids.push(grid);
    return el('details', {
      class: 'arc-batch-found',
      /* The recording's full label, which the row has no column wide
         enough for -- "J3 Precon1" and a date is enough to find it in the
         table and not enough to be sure which folder it came out of. */
      title: f.label || '',
      open: bulk.open[gid] ? 'open' : null,
      ontoggle: (e) => {
        if (e.target.open) bulk.open[gid] = true;
        else delete bulk.open[gid];
      },
    }, kids);
  }

  /* ONE ROW, and nothing else.

     Rebuilding the card on every tick of a run throws away the scroll
     position and shuts every disclosure somebody had open -- which is
     exactly what they are reading while the rest of the queue goes. The
     status text is the only thing that changes mid-recording, so it is
     the only thing written; `whole` is for a recording that has LANDED,
     which has a disclosure now and needs its row built again. Braces
     learnt this the same way, with an Open button that only appeared when
     the whole queue finished. */
  function paintBatchRow(gid, whole) {
    const row = document.querySelector('.arc-batch-row[data-gid="'
                                       + cssEsc(gid) + '"]');
    if (!row || !row.parentNode) return;
    const st = bulk.state[gid] || {};
    if (whole) {
      const r = (rows || []).find((x) => x.gid === gid);
      if (r) { row.parentNode.replaceChild(batchRow(r), row); return; }
    }
    const cell = row.querySelector('.st');
    if (cell) cell.textContent = st.msg || '';
    for (const k of ['queued', 'going', 'done', 'failed', 'skipped']) {
      row.classList.toggle(k, st.state === k);
    }
    row.classList.toggle('on', !!bulk.want[gid]);
  }

  /* Mid-run, only the number moves: the bar itself is holding the Stop
     button somebody may be about to press, and replacing it under a
     pointer is how a click lands on nothing. */
  function paintBatchBar() {
    const n = document.querySelector('.arc-batch-count');
    if (n) n.textContent = countSay();
  }

  /* Everything above the rows, rebuilt where it stands: the cost changes
     with the number ticked, the primary's label counts them, and the line
     about what came off appears and disappears. The rows are left alone,
     which is the whole point. */
  function paintBatchHead() {
    const card = document.querySelector('#arcBatch .arc-batch');
    if (!card) return;
    const cost = card.querySelector('.arc-batch-cost');
    if (cost) card.replaceChild(batchCost(), cost);
    const bar = card.querySelector('.arc-batch-bar');
    if (bar) card.replaceChild(batchBar(), bar);
    const was = card.querySelector('.arc-batch-off');
    const now_ = batchOff();
    if (was && now_) card.replaceChild(now_, was);
    else if (was) card.removeChild(was);
    else if (now_) card.insertBefore(now_,
                                     card.querySelector('.arc-batch-rows'));
  }

  /* Attribute selectors take a quoted value, and a gid is somebody else's
     string, so it is escaped rather than trusted. */
  function cssEsc(v) {
    return (window.CSS && CSS.escape) ? CSS.escape(String(v))
                                      : String(v).replace(/["\\]/g, '\\$&');
  }

  /* ---------------- the run ----------------

     One recording at a time, and sequentially on purpose. Each of these
     reads a .nev and memory-maps every channel file on a network share;
     nine of them at once would be nine readers fighting over one disk and
     a progress table that finished all at once having told nobody
     anything. Sequential also makes "stop" mean something simple: the one
     in hand finishes and nothing else starts. */
  async function runBatch() {
    if (bulk.running) return;
    bulk.off = {};

    /* Ticks that stopped meaning anything before the run even started. A
       share can go away between ticking and running, and forty failures
       in a row is not a report -- it is a thing somebody has to read
       backwards to find the one real fault in. */
    for (const gid of Object.keys(bulk.want)) {
      const r = (rows || []).find((x) => x.gid === gid);
      if (!r) { unpick(gid, 'not in this phase any more'); continue; }
      if (!canBatch(r)) {
        unpick(gid, 'the recording is not on a drive this machine can reach');
      }
    }

    const queue = (rows || []).filter((r) => bulk.want[r.gid]);
    if (!queue.length) {
      renderBatch();
      toast('Nothing is ticked that can be read from this machine.',
            'warn', 6000);
      return;
    }

    bulk.running = true;
    bulk.stop = false;
    for (const r of queue) {
      bulk.state[r.gid] = { state: 'queued', msg: 'waiting' };
    }
    renderBatch();

    let filed = 0, skipped = 0, failed = 0, stopped = 0;

    for (const r of queue) {
      if (bulk.stop) {
        /* Left ticked. It is still to do, which is what a tick means, and
           pressing the button again picks up exactly where this left. */
        bulk.state[r.gid] = { state: '', msg: 'stopped before this one' };
        paintBatchRow(r.gid, true);
        stopped += 1;
        continue;
      }
      try {
        bulk.state[r.gid] = { state: 'going', msg: 'reading Events.nev…' };
        paintBatchRow(r.gid);
        const read = await api('/api/arc/spark/'
                               + encodeURIComponent(r.gid));

        const why = skipReason(r.gid, read);
        if (why) {
          unpick(r.gid, why);
          bulk.state[r.gid] = { state: 'skipped', msg: why,
                                found: foundOf(read, null, null, null) };
          skipped += 1;
          paintBatchRow(r.gid, true);
          paintBatchBar();
          continue;
        }

        let clipping = null;
        if (wantsClip(r.gid)) {
          bulk.state[r.gid] = { state: 'going', msg: 'checking '
            + (read.summary.n_channels || 'every')
            + ' channels for clipping…' };
          paintBatchRow(r.gid);
          /* At the panel's transition lengths: one read answers both
             kinds, so a batch banks both without costing a second pass. */
          clipping = await apiPost('/api/arc/spark/'
            + encodeURIComponent(r.gid) + '/clipping',
            { before_s: tq.before, after_s: tq.after });
          clipSeen[r.gid] = true;
        }

        const excl = exclusionBoth(read.pairs || [], clipping);
        bulk.state[r.gid] = { state: 'going', msg: 'filing the pairs…' };
        paintBatchRow(r.gid);
        const res = await apiPost('/api/arc/spark/'
          + encodeURIComponent(r.gid) + '/bank', { excluded: excl });

        /* Provisional, and replaced by `loadRows` at the end of the run.
           Written now anyway because the count over the table says how
           many are filed, and a number that only becomes true when the
           queue empties is one somebody reads wrong for two minutes. */
        banked[r.gid] = Object.assign({}, banked[r.gid] || {}, {
          id: (res.entry || {}).id || (banked[r.gid] || {}).id,
          n: res.n,
          version: (res.entry || {}).version,
          versions: ((banked[r.gid] || {}).versions || 0) + 1,
        });
        /* Filed is no longer still-to-do. The tick comes off, and the row
           says what happened to it -- so stopping halfway and pressing the
           button again runs the rest and nothing twice. */
        delete bulk.want[r.gid];
        bulk.state[r.gid] = {
          state: 'done',
          msg: 'filed ' + res.n + ' cue pairs'
               + (clipping
                  ? (blocksIn(excl)
                     ? ', ' + blocksIn(excl) + ' blocks excluded'
                     : ', nothing excluded')
                  : ''),
          found: foundOf(read, clipping, clipping ? excl : null, res),
        };
        filed += 1;
        BARRY.activity.log('arc.spark.bank', {
          gid: r.gid, n: res.n, excluded: blocksIn(excl),
          via: 'batch',
        });
      } catch (e) {
        /* Named and kept, and the tick STAYS -- this one is still to do.
           A batch that swallows a failure is a batch somebody has to check
           by hand afterwards anyway. */
        bulk.state[r.gid] = { state: 'failed',
                              msg: e.message || String(e) };
        failed += 1;
        reportClientError('arc.spark.batch', e.message, e.stack);
      }
      paintBatchRow(r.gid, true);
      paintBatchBar();
    }

    bulk.running = false;
    bulk.stop = false;
    try {
      await loadRows();
    } catch (e) {
      // The table is still true about everything except how many versions
      // each entry now has, and a toast about a refresh nobody asked for
      // would be a worse answer than a count one behind.
      reportClientError('arc.spark.batch.rows', e.message, e.stack);
    }
    renderSpark();
    BARRY.activity.log('arc.spark.batch', {
      phase: q.phase, n: queue.length, filed: filed, skipped: skipped,
      failed: failed, stopped: stopped, clipping: bulk.clip,
    });
    toast(filed + ' of ' + queue.length + ' filed'
          + (skipped ? ', ' + skipped + ' had nothing to file and came off '
                     + 'the selection' : '')
          + (stopped ? ', ' + stopped + ' not started' : '')
          + (failed ? ', ' + failed + ' failed' : '') + '.',
          failed ? 'warn' : 'ok', 9000);
  }

  /* ==================================================================
     Coupling -- step two.

     Reads the BANK, never a .nev. By the time a pair is banked somebody
     has looked at it, the clipping has been measured and the channels it
     is not valid on travel with it; re-reading the event file here would
     throw all of that away and correlate a window that had already been
     decided against.

     A recording Spark has not filed is listed anyway, with the reason.
     "Spark found these and nobody filed them" is a thing somebody needs
     to be told, not a row to leave out.
     ================================================================== */
  /* `kind` is state or transition: which windows the overview grid, the
     run, the matrix and the CSV are about. Held across recordings for the
     same reason `cParams` is -- it is a choice about the analysis. */
  const cq = { gid: null, pair: 1, method: 'amp_cc', window: 'cue1',
               kind: 'state' };
  let cRows = null;       // recordings, with whether they are banked
  let cPairs = null;      // the banked pairs of the chosen recording
  let cRun = null;        // the last analysis
  let cBusy = false;
  /* The pre-run overview for the picked recording -- parameters, where
     each probe is, and which wire each region will use -- and the values
     the parameter fields hold. `cParams` outlives a change of recording on
     purpose: the corners are a choice about the analysis, not about the
     rat, and silently resetting them on every pick would make the second
     recording of a batch run at different corners from the first. */
  let cOver = null;
  let cParams = null;
  let cParamErr = null;
  const cOpen = { params: false, probes: true, channels: true };
  let cSaved = null;

  const METHODS = [
    ['coherence', 'Coherence', 'magnitude-squared, read at 8 Hz'],
    ['raw_cc', 'Raw cross-correlation', 'peak |r| within \u00b1500 ms'],
    ['amp_cc', 'Amplitude cross-correlation',
     'theta envelope, peak |r| within \u00b1500 ms'],
  ];
  const WINDOW_NAMES = {
    pre: 'baseline', cue1: 'cue 1', cue2: 'cue 2', post: 'after cue 2',
    onset: 'cue 1 onset', switch: 'cue 1 → cue 2',
    offset: 'cue 2 offset',
  };

  /* The window a matrix opens on for each kind: cue 1 for state, as it
     always has, and the cue 1 -> cue 2 switch for transitions, which is
     the boundary the paradigm is about. */
  const FIRST_WINDOW = { state: 'cue1', transition: 'switch' };

  /* The overview for one recording in one kind. The grid and the length
     fields are per kind; the histology is not, but it comes back in the
     same answer and costs nothing to ask for again. */
  function overviewURL(gid) {
    return '/api/arc/coupling/' + encodeURIComponent(gid) + '/overview'
           + (cq.kind === 'transition' ? '?kind=transition' : '');
  }

  async function setCouplingKind(k) {
    const next = k === 'transition' ? 'transition' : 'state';
    if (next === cq.kind) return;
    cq.kind = next;
    cq.window = FIRST_WINDOW[next];
    cRun = null; cSaved = null; cParamErr = null;
    const gid = cq.gid;
    if (!gid) { renderCMain(); return; }
    cOver = null;
    renderCMain();
    try {
      const got = await api(overviewURL(gid));
      if (cq.gid !== gid || cq.kind !== next) return;
      cOver = got;
    } catch (e) {
      if (cq.gid !== gid || cq.kind !== next) return;
      cOver = { error: e.message };
    }
    if (!cOver.error && !cParams) cParams = Object.assign({}, cOver.defaults || {});
    if (BARRY.views.toolkit.tool() === 'coupling' && cq.gid === gid) {
      renderCMain();
    }
  }

  /* The switch itself: the house segmented control, above everything it
     changes. */
  function cKindSeg() {
    return el('div', { class: 'arc-cp-kind' }, [
      el('div', { class: 'seg' }, [
        ['state', 'State'], ['transition', 'Transition'],
      ].map(([id, label]) => el('button', {
        class: cq.kind === id ? 'active' : '',
        'data-kind': id,
        text: label,
        onclick: () => setCouplingKind(id),
      }))),
      el('span', { class: 'hint', text: cq.kind === 'transition'
        ? 'Three windows around each pair’s boundaries: cue 1 starting, '
          + 'cue 1 giving way to cue 2, and cue 2 ending.'
        : 'Four ten-second windows per pair: baseline, cue 1, cue 2, and '
          + 'after cue 2.' }),
    ]);
  }

  function paintCoupling(host) {
    host.appendChild(el('div', { class: 'arc-spark' }, [
      el('div', { class: 'arc-pick', id: 'cpPick' }),
      el('div', { class: 'arc-read', id: 'cpMain' }),
    ]));
    if (cRows === null) {
      BARRY.skeleton.into(document.getElementById('cpPick'), 'row', 8);
      api('/api/arc/coupling/recordings').then((got) => {
        cRows = got.rows || [];
        if (BARRY.views.toolkit.tool() === 'coupling') {
          renderCPick(); renderCMain();
        }
      }).catch((e) => {
        reportClientError('arc.coupling', e.message, e.stack);
        const p = document.getElementById('cpPick');
        if (p) {
          p.innerHTML = '';
          p.appendChild(el('p', { class: 'hint', text: e.message }));
        }
      });
      return;
    }
    renderCPick();
    renderCMain();
  }

  function renderCPick() {
    const host = document.getElementById('cpPick');
    if (!host) return;
    host.innerHTML = '';
    host.appendChild(el('div', { class: 'section-label',
                                 text: 'Banked recordings' }));
    host.appendChild(el('p', { class: 'hint',
      text: 'Coupling reads the cue pairs Spark filed, so the channels a '
            + 'pair is invalid on come with it. A recording Spark has not '
            + 'filed cannot be analysed yet.' }));

    const list = el('div', { class: 'arc-rows' });
    for (const r of (cRows || [])) {
      list.appendChild(el('button', {
        class: 'arc-row' + (cq.gid === r.gid ? ' on' : '')
               + (r.banked && r.reachable ? '' : ' off'),
        disabled: (r.banked && r.reachable) ? null : 'disabled',
        title: r.banked
          ? (r.reachable ? r.label
             : 'None of this recording\u2019s paths are reachable from this '
               + 'machine.')
          : r.why,
        onclick: () => pickCoupling(r.gid),
      }, [
        el('strong', { text: 'r' + r.mouse }),
        el('span', { class: 'arc-row-s',
                     text: (r.phase || '') + (r.phase_n || '') }),
        el('span', { class: 'arc-row-d', text: r.date || '' }),
        r.banked
          ? el('span', { class: 'flagchip mat', text: r.n_pairs + ' pairs' })
          : el('span', { class: 'arc-row-n', text: 'not filed' }),
      ]));
    }
    host.appendChild(list);
  }

  async function pickCoupling(gid) {
    cq.gid = gid; cq.pair = 1; cPairs = null; cRun = null; cSaved = null;
    cOver = null; cParamErr = null;
    renderCPick(); renderCMain();
    /* Both at once. The overview opens no recording file, so it is cheap,
       but it is a second request and there is no reason to wait for the
       first before asking. Settled rather than awaited together: a Jarvis
       started before the overview route existed answers "restart", and
       that must cost the overview only, not the pair list under it. */
    const base = '/api/arc/coupling/' + encodeURIComponent(gid);
    const asked = cq.kind;
    const [pairs, over] = await Promise.allSettled([
      api(base), api(overviewURL(gid))]);
    if (cq.gid !== gid || cq.kind !== asked) return;
    cPairs = pairs.status === 'fulfilled' ? pairs.value
                                          : { error: pairs.reason.message };
    cOver = over.status === 'fulfilled' ? over.value
                                        : { error: over.reason.message };
    if (!cOver.error && !cParams) {
      cParams = Object.assign({}, cOver.defaults || {});
    }
    if (BARRY.views.toolkit.tool() === 'coupling' && cq.gid === gid) {
      renderCMain();
    }
  }

  function renderCMain() {
    const host = document.getElementById('cpMain');
    if (!host) return;
    host.innerHTML = '';
    if (!cq.gid) {
      host.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'Pick a recording whose cue pairs are filed.' }),
      ]));
      return;
    }
    if (!cPairs) {
      host.appendChild(loader('Reading the bank', 'the filed cue pairs'));
      return;
    }
    if (cPairs.error) {
      host.appendChild(el('div', { class: 'card' }, [
        el('p', { class: 'hint', text: cPairs.error })]));
      return;
    }
    const p = (cPairs.pairs || [])[cq.pair - 1];
    host.appendChild(el('div', { class: 'card' }, [
      el('div', { class: 'section-label', text: cPairs.label || '' }),
      cKindSeg(),
      cOverview(),
      cPairBar(),
      p ? cPairNote(p) : null,
      cRunBar(),
      cResult(),
    ].filter(Boolean)));
  }

  /* ================================================================
     Before running: what will be computed, from what, and why.

     Three parts, each a <details> so a person who has read them once can
     fold them away, each with a one-line summary that stays visible when
     folded -- because the reason this exists is that the answer to "what
     is this matrix made of" should be on screen at the moment the Run
     button is, not in a file afterwards.

       Parameters       the corners, editable, with their limits
       Probe sanity     where each probe really is, with the slides
       Channel sanity   per cue pair, which wire each region will use
     ================================================================ */
  function cOverview() {
    if (!cOver) {
      return el('div', { class: 'arc-ov' }, [
        loader('Reading the histology and the bank',
               'where each probe is, and which wire each region uses')]);
    }
    if (cOver.error) {
      return el('div', { class: 'arc-ov arc-ov-err' }, [
        el('p', { class: 'hint',
          text: 'The overview could not be read, so the parameters, the '
                + 'histology and the wire each region will use are not '
                + 'shown. The analysis still runs at its defaults. '
                + cOver.error }),
      ]);
    }
    return el('div', { class: 'arc-ov' }, [
      ovSection('params', 'Parameters', paramSummary(), paramBody),
      ovSection('probes', 'Probe sanity', probeSummary(), probeBody),
      ovSection('channels', 'Channel sanity', channelSummary(), channelBody),
    ]);
  }

  function ovSection(key, title, summary, body) {
    /* `arc-ov-sec-<key>`, not `arc-ov-<key>`: the parameter GRID inside
       is `.arc-ov-params`, and the section wearing the same class took
       the grid's `display: grid` along with it. */
    const d = el('details', { class: 'arc-ov-sec arc-ov-sec-' + key });
    if (cOpen[key]) d.setAttribute('open', '');
    d.appendChild(el('summary', {}, [
      el('strong', { text: title }),
      el('span', { class: 'arc-ov-sum', text: summary }),
    ]));
    /* Built on first open rather than always. The probe section asks for a
       thumbnail per slide, and a folded section should cost nothing. */
    let built = false;
    const build = () => {
      if (built) return;
      built = true;
      d.appendChild(el('div', { class: 'arc-ov-body' }, [body()]));
    };
    if (cOpen[key]) build();
    d.addEventListener('toggle', () => {
      cOpen[key] = d.open;
      if (d.open) build();
    });
    return d;
  }

  /* ---------------- parameters ---------------- */

  function paramChanged(id) {
    const def = (cOver.defaults || {})[id];
    const now = (cParams || {})[id];
    return String(def) !== String(now);
  }

  function paramSummary() {
    const p = cParams || {};
    const n = (cOver.params || []).filter(
      (x) => !x.fixed && paramChanged(x.id)).length;
    return p.low + '\u2013' + p.high + ' Hz \u00b7 coherence at '
      + p.summary_hz + ' Hz \u00b7 \u00b1' + p.max_lag_ms + ' ms \u00b7 '
      + (p.notch_hz ? p.notch_hz + ' Hz notch' : 'no notch') + ' \u00b7 '
      + (cq.kind === 'transition'
         ? p.before_s + ' s before to ' + p.after_s + ' s after each boundary'
         : p.pad_s + ' s baseline')
      + (n ? '  \u00b7  ' + n + ' changed from the default' : '')
      + (cParamErr ? '  \u00b7  refused' : '');
  }

  function paramBody() {
    const grid = el('div', { class: 'arc-ov-params' });
    for (const spec of (cOver.params || [])) {
      grid.appendChild(paramField(spec));
    }
    const kids = [grid];
    if (cParamErr) {
      /* The server's sentence, where the fields are. A refusal shown only
         as a toast is gone before somebody has found which field it was
         about. */
      kids.unshift(el('p', { class: 'arc-ov-refused', text: cParamErr }));
    }
    kids.push(el('div', { class: 'head-actions' }, [
      el('span', { class: 'hint',
        text: 'Checked on the server when you run, and refused rather than '
              + 'adjusted: a matrix made at different corners from the ones '
              + 'shown here is the thing showing them is for preventing.' }),
      el('div', { class: 'spacer' }),
      el('button', {
        class: 'btn ghost sm', text: 'Back to the defaults',
        disabled: (cOver.params || []).some(
          (x) => !x.fixed && paramChanged(x.id)) ? null : 'disabled',
        onclick: () => {
          cParams = Object.assign({}, cOver.defaults || {});
          cParamErr = null;
          renderCMain();
        },
      }),
    ]));
    return el('div', {}, kids);
  }

  function paramField(spec) {
    const val = (cParams || {})[spec.id];
    let control;
    if (spec.fixed) {
      control = el('div', { class: 'arc-ov-fixed',
                            text: String(val) + (spec.unit ? ' ' + spec.unit
                                                           : '') });
    } else if (spec.choices) {
      control = el('select', {
        onchange: (e) => {
          const v = e.target.value;
          cParams[spec.id] = v === 'off' ? null : Number(v);
          cParamErr = null;
          renderCMain();
        },
      }, spec.choices.map((c) => {
        const o = el('option', { value: c == null ? 'off' : String(c),
                                 text: c == null ? 'off' : c + ' ' + spec.unit });
        if ((c == null && val == null) || Number(c) === Number(val)) {
          o.selected = true;
        }
        return o;
      }));
    } else {
      control = el('div', { class: 'arc-ov-num' }, [
        el('input', {
          type: 'number', value: String(val),
          min: spec.min != null ? String(spec.min) : null,
          max: spec.max != null ? String(spec.max) : null,
          step: spec.step != null ? String(spec.step) : null,
          /* On change, not on input. Repainting on every keystroke would
             rebuild this field under the caret and lose the focus mid-way
             through typing "12.5". */
          onchange: (e) => {
            const v = Number(e.target.value);
            cParams[spec.id] = isFinite(v) ? v : e.target.value;
            cParamErr = null;
            renderCMain();
          },
        }),
        el('span', { class: 'arc-ov-unit', text: spec.unit || '' }),
      ]);
    }
    return BARRY.ui.field({
      label: spec.name + (paramChanged(spec.id) && !spec.fixed
                          ? '  \u00b7  changed' : ''),
      control: control,
      hint: spec.say
        + (spec.min != null && spec.max != null && !spec.fixed
           ? '  ' + spec.min + ' to ' + spec.max + ' ' + spec.unit + '.'
           : ''),
      extra: 'arc-ov-field' + (spec.fixed ? ' fixed' : '')
             + (paramChanged(spec.id) && !spec.fixed ? ' changed' : ''),
    });
  }

  /* ---------------- where each probe is ---------------- */

  const VERDICT_WORD = {
    intended: 'in target', uncertain: 'maybe', relocated: 'elsewhere',
    missed: 'missed', unscored: 'not scored',
  };

  function probeSummary() {
    const s = cOver.probe_summary;
    if (!s) return 'no histology for this rat';
    const by = s.by_verdict || {};
    const n = (k) => (by[k] || []).length;
    if (n('unscored') === s.n) {
      return 'this rat has no row in ' + cOver.histology_file
             + ', so nothing will be computed until it is scored';
    }
    const bits = [s.usable + ' of ' + s.n + ' will be computed'];
    if (n('relocated')) bits.push(n('relocated') + ' not where aimed');
    if (n('uncertain')) bits.push(n('uncertain') + ' scored maybe');
    if (n('missed')) bits.push(n('missed') + ' missed');
    return bits.join(' \u00b7 ');
  }

  function probeBody() {
    const probe = cOver.probe || [];
    const slides = cOver.slides;
    const rows = probe.map((p) => {
      const mine = slides ? (slides[p.slot] || []) : null;
      return el('div', { class: 'arc-pr ' + p.verdict,
                         title: p.why }, [
        el('span', { class: 'arc-pr-v ' + p.verdict,
                     text: VERDICT_WORD[p.verdict] || p.verdict }),
        el('div', { class: 'arc-pr-name' }, [
          el('strong', { text: p.actual }),
          p.actual !== p.intended
            ? el('span', { class: 'arc-pr-aim',
                           text: 'aimed at ' + p.intended })
            : null,
          el('span', { class: 'arc-pr-ch',
                       text: 'CSC ' + p.channels.join(', ') }),
        ].filter(Boolean)),
        el('div', { class: 'arc-pr-slides' },
          mine == null
            ? [el('span', { class: 'hint', text: '\u2014' })]
            : mine.length
              ? mine.map((sl) => thumb(sl, p))
              : [el('span', { class: 'hint',
                              text: 'no slide names this region' })]),
      ]);
    });
    const kids = [el('div', { class: 'arc-pr-list' }, rows)];
    if (slides == null && cOver.slides_why) {
      kids.push(el('p', { class: 'hint', text: cOver.slides_why }));
    }
    kids.push(el('p', { class: 'hint',
      text: 'From ' + cOver.histology_file + '. A probe that is elsewhere '
            + 'is still computed, under the name of the region it is really '
            + 'in; a missed one is not, and neither is a rat nobody has '
            + 'scored. The words under a slide are its own filename\u2019s '
            + 'verdict, which is a second opinion and does not always agree '
            + 'with the workbook \u2014 that is worth looking at when it '
            + 'happens.' }));
    return el('div', {}, kids);
  }

  function slideURL(sl, kind) {
    return '/api/histoimg/file?rat=' + encodeURIComponent('J' + cOver.rat)
           + '&file=' + encodeURIComponent(sl.file) + '&kind=' + kind;
  }

  function slideWords(sl) {
    const w = [].concat(sl.verdicts || [], sl.notes || []);
    if (sl.side_unclear) w.push('side unclear');
    return w.join(' \u00b7 ');
  }

  function thumb(sl, probe) {
    const words = slideWords(sl);
    return el('button', {
      class: 'arc-thumb', title: sl.says || sl.file,
      onclick: () => openSlide(sl, probe),
    }, [
      el('img', { src: slideURL(sl, 'thumb'), alt: sl.file,
                  loading: 'lazy' }),
      words ? el('span', { class: 'arc-thumb-w', text: words }) : null,
    ].filter(Boolean));
  }

  /* One slide, big enough to read, with the two verdicts beside it.

     Wheel to zoom about the pointer, drag to pan, double-click to fit. A
     2400 px section has the tract in a corner of it; a viewer that cannot
     zoom is a viewer that shows you the brain and not the electrode. */
  function openSlide(sl, probe) {
    const stage = el('div', { class: 'arc-slide-stage' });
    const img = el('img', { class: 'arc-slide-img', alt: sl.file,
                            draggable: 'false' });
    const wait = loader('Fetching the slide',
                        'from this machine, or from the cloud');
    stage.appendChild(wait);
    let z = 1, x = 0, y = 0, fitZ = 1;
    const apply = () => {
      img.style.transform = 'translate(' + x + 'px,' + y + 'px) scale('
                            + z + ')';
    };
    const fit = () => {
      const r = stage.getBoundingClientRect();
      if (!img.naturalWidth || !r.width) return;
      fitZ = Math.min(r.width / img.naturalWidth, r.height / img.naturalHeight);
      z = fitZ;
      x = (r.width - img.naturalWidth * z) / 2;
      y = (r.height - img.naturalHeight * z) / 2;
      apply();
    };
    img.onload = () => {
      if (wait.parentNode) wait.remove();
      stage.appendChild(img);
      fit();
    };
    img.onerror = () => {
      if (wait.parentNode) wait.remove();
      stage.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'This slide could not be fetched. It has to be '
                        + 'derived on a machine with the E: drive and '
                        + 'uploaded before other machines can show it.' }),
      ]));
    };
    img.src = slideURL(sl, 'web');

    stage.addEventListener('wheel', (e) => {
      if (!img.naturalWidth) return;
      e.preventDefault();
      const r = stage.getBoundingClientRect();
      const px = e.clientX - r.left, py = e.clientY - r.top;
      const k = Math.exp(-e.deltaY * 0.0015);
      const nz = Math.max(fitZ * 0.5, Math.min(z * k, 8));
      // Zoom about the pointer: the pixel under it stays under it.
      x = px - (px - x) * (nz / z);
      y = py - (py - y) * (nz / z);
      z = nz;
      apply();
    }, { passive: false });
    let drag = null;
    stage.addEventListener('pointerdown', (e) => {
      drag = { sx: e.clientX, sy: e.clientY, x: x, y: y };
      stage.setPointerCapture(e.pointerId);
      stage.classList.add('dragging');
    });
    stage.addEventListener('pointermove', (e) => {
      if (!drag) return;
      x = drag.x + (e.clientX - drag.sx);
      y = drag.y + (e.clientY - drag.sy);
      apply();
    });
    const end = () => { drag = null; stage.classList.remove('dragging'); };
    stage.addEventListener('pointerup', end);
    stage.addEventListener('pointercancel', end);
    stage.addEventListener('dblclick', fit);

    /* The modal has no Escape of its own, so this adds one for as long as
       the stage is on the page -- and takes itself off the moment it is
       not, however the dialog was closed. */
    const onKey = (e) => {
      if (!stage.isConnected) {
        document.removeEventListener('keydown', onKey);
        return;
      }
      if (e.key === 'Escape') { e.preventDefault(); done(); }
    };
    const done = () => {
      document.removeEventListener('keydown', onKey);
      closeModal();
    };
    document.addEventListener('keydown', onKey);

    const words = slideWords(sl);
    const book = probe.verdict === 'relocated'
      ? 'the workbook puts it in ' + probe.actual
      : 'the workbook says ' + (VERDICT_WORD[probe.verdict] || probe.verdict)
        + (probe.raw && probe.verdict !== 'intended'
           ? ' (\u201c' + probe.raw + '\u201d)' : '');
    showModal(el('div', { class: 'arc-slide' }, [
      el('div', { class: 'mh' }, [
        el('h3', { text: 'J' + cOver.rat + ' \u00b7 ' + sl.file }),
        el('div', { class: 'spacer' }),
        el('button', { class: 'close-x', onclick: done,
          html: '<svg viewBox="0 0 20 20"><path d="M5 5l10 10M15 5L5 15"/>'
                + '</svg>' }),
      ]),
      el('div', { class: 'mb' }, [
        el('div', { class: 'arc-slide-meta' }, [
          el('span', { class: 'arc-pr-v ' + probe.verdict,
                       text: VERDICT_WORD[probe.verdict] || probe.verdict }),
          el('span', { text: 'Aimed at ' + probe.intended + '; ' + book
                             + '.' }),
          words ? el('span', { class: 'arc-slide-file',
                               text: 'The filename says: ' + words + '.' })
                : null,
          sl.both_sides
            ? el('span', { class: 'hint',
                           text: 'Not side-specific, so it is shown for both '
                                 + 'hemispheres.' })
            : null,
          sl.side_unclear
            ? el('span', { class: 'hint',
                           text: 'The filename names both sides, so which '
                                 + 'hemisphere this is could not be read off '
                                 + 'it.' })
            : null,
        ].filter(Boolean)),
        stage,
        el('p', { class: 'hint',
                  text: 'Wheel to zoom, drag to move, double-click to fit.' }),
      ]),
      el('div', { class: 'mf' }, [
        el('div', { class: 'spacer' }),
        el('button', { class: 'btn', text: 'Close', onclick: done }),
      ]),
    ]));
  }

  /* ---------------- which wire, per cue pair ---------------- */

  function ovEvent() {
    return (cOver.events || []).find((e) => e.pair_id === cq.pair)
           || (cOver.events || [])[0] || null;
  }

  function channelSummary() {
    if (cOver.refused) {
      return 'the transition windows have never been checked for clipping';
    }
    const ev = ovEvent();
    if (!ev) return 'no cue pairs';
    const b = ev.blocked || {};
    return 'cue pair ' + ev.pair_id + ' of ' + (cOver.events || []).length
      + ' \u00b7 region pairs blocked: '
      + (cOver.windows || []).map((w) => (WINDOW_NAMES[w] || w) + ' '
                                         + (b[w] || 0)).join(', ')
      + ' of 66';
  }

  function channelBody() {
    if (cOver.refused) {
      /* No grid rather than a grid of guesses: with nothing measured at
         the boundaries every wire would look usable. The server's own
         sentence, which says what to do. */
      return el('p', { class: 'arc-ov-refused arc-ov-unmeasured',
                       text: cOver.refused });
    }
    const ev = ovEvent();
    if (!ev) return el('p', { class: 'hint', text: 'No cue pairs are banked.' });
    const n = (cOver.events || []).length;
    const step = (d) => {
      cq.pair = Math.max(1, Math.min(n, ev.pair_id + d));
      cRun = null; cSaved = null;
      renderCMain();
    };
    const wins = cOver.windows || [];
    const head = el('div', { class: 'arc-cs-row head' }, [
      el('span', { class: 'arc-cs-reg', text: 'region' }),
    ].concat(wins.map((w) => el('span', { class: 'arc-cs-w' + (
      w === 'cue1' || w === 'cue2' ? ' cue' : ''), text: WINDOW_NAMES[w] || w }))));
    const rows = (ev.regions || []).map((r) => el('div', {
      class: 'arc-cs-row',
    }, [
      el('span', { class: 'arc-cs-reg ' + (r.histology || ''),
                   title: r.label, text: r.label }),
    ].concat(wins.map((w) => {
      const c = (r.windows || {})[w] || {};
      const kind = c.channel != null ? 'ok'
        : (c.blocked === 'histology' ? 'hist' : 'gone');
      return el('span', {
        class: 'arc-cs-c ' + kind + (w === 'cue1' || w === 'cue2' ? ' cue' : ''),
        title: c.why || '',
        text: c.channel != null ? String(c.channel)
          : (kind === 'hist' ? '\u2014' : '\u2715'),
      });
    }))));
    const foot = el('div', { class: 'arc-cs-row foot' }, [
      el('span', { class: 'arc-cs-reg', text: 'pairs blocked' }),
    ].concat(wins.map((w) => el('span', {
      class: 'arc-cs-w', text: String((ev.blocked || {})[w] || 0) + ' / 66' }))));

    return el('div', {}, [
      el('div', { class: 'arc-cs-nav' }, [
        el('button', { class: 'btn ghost sm', text: '\u25c0',
                       title: 'The previous cue pair',
                       disabled: ev.pair_id <= 1 ? 'disabled' : null,
                       onclick: () => step(-1) }),
        el('span', { class: 'arc-cs-at',
          text: 'Cue pair ' + ev.pair_id + ' of ' + n
                + (ev.label ? ' \u00b7 ' + ev.label : '')
                + (ev.opener_t != null
                   ? ' at ' + Number(ev.opener_t).toFixed(1) + ' s' : '') }),
        el('button', { class: 'btn ghost sm', text: '\u25b6',
                       title: 'The next cue pair',
                       disabled: ev.pair_id >= n ? 'disabled' : null,
                       onclick: () => step(1) }),
      ]),
      el('div', { class: 'arc-cs arc-cs-n' + wins.length },
         [head].concat(rows, [foot])),
      el('p', { class: 'hint',
        text: 'A number is the one wire that region will be measured on in '
              + 'that window: the lowest-numbered channel that is not marked '
              + 'bad and did not clip there. \u2715 is a region with no such '
              + 'wire; \u2014 is one the histology rules out. Hover any '
              + 'cell for the reason. This is worked out from the bank '
              + 'before a file is opened; the matrix below is labelled from '
              + 'what the run actually did.' }),
    ]);
  }

  function cPairBar() {
    const list = cPairs.pairs || [];
    return el('div', { class: 'arc-cp-pairs' }, list.map((p) => el('button', {
      class: 'mini' + (cq.pair === p.pair_id ? ' on' : '')
             + (p.excluded.length ? ' warn' : ''),
      title: p.label + ' at ' + p.opener_t.toFixed(1) + ' s'
             + (p.excluded.length
                ? ' \u2014 not valid on CSC ' + p.excluded.join(', ') : ''),
      text: String(p.pair_id),
      onclick: () => { cq.pair = p.pair_id; cRun = null; cSaved = null;
                       renderCMain(); },
    })));
  }

  /* What this pair cannot be analysed on, said before anything is run
     rather than discovered in a table of Nones afterwards. */
  function cPairNote(p) {
    const bits = [el('strong', { text: p.label }),
                  el('span', { class: 'hint',
                               text: 'cue 1 at ' + p.opener_t.toFixed(2)
                                     + ' s, gap ' + p.gap_s.toFixed(4) + ' s' })];
    if (p.excluded.length) {
      bits.push(el('span', { class: 'flagchip warn',
        title: 'CSC ' + p.excluded.join(', '),
        text: p.excluded.length + ' channel(s) excluded' }));
    } else {
      bits.push(el('span', { class: 'flagchip mat',
                             text: 'every channel usable' }));
    }
    return el('div', { class: 'chip-row arc-cp-note' }, bits);
  }

  function cRunBar() {
    const T = cq.kind === 'transition';
    /* A transition run on an entry whose transitions nobody checked is
       refused by the server; the button says so before it is pressed. */
    const refused = !!(cOver && cOver.refused);
    return el('div', { class: 'head-actions arc-cp-bar' }, [
      el('span', { class: 'hint',
        text: (T ? 'Three transition windows' : 'Four windows')
              + ' × 66 region pairs × three methods, '
              + 'about five seconds. Mains is notched first — there is '
              + 'more power at 60 Hz than at 8 Hz in this data, and the '
              + 'peak-picking would find it.' }),
      el('div', { class: 'spacer' }),
      cRun ? el('button', {
        class: 'btn ghost sm',
        disabled: cBusy ? 'disabled' : null,
        text: cSaved ? 'Saved' : 'Save to Results',
        title: cSaved ? cSaved : 'Write the summary as a CSV under Results.',
        onclick: doCouplingSave,
      }) : null,
      el('button', {
        class: 'btn' + (cBusy ? ' off' : ''),
        disabled: (cBusy || refused) ? 'disabled' : null,
        title: refused ? cOver.refused : '',
        text: cBusy ? 'Running…' : (cRun ? 'Run again' : 'Run the analysis'),
        onclick: doCouplingRun,
      }),
    ].filter(Boolean));
  }

  async function doCouplingRun() {
    if (cBusy || !cq.gid) return;
    cBusy = true; cSaved = null; renderCMain();
    const asked = cq.gid + ':' + cq.pair + ':' + cq.kind;
    const sent = cParams ? Object.assign({}, cParams) : null;
    const body = { pair_id: cq.pair, kind: cq.kind };
    if (sent) body.params = sent;
    try {
      const got = await apiPost(
        '/api/arc/coupling/' + encodeURIComponent(cq.gid) + '/run', body);
      if (cq.gid + ':' + cq.pair + ':' + cq.kind === asked) {
        cRun = got;
        // What it was run at, so a change afterwards can be said out loud.
        cRun.__sent = JSON.stringify(sent);
        cParamErr = null;
        /* The matrix opens on a window this run HAS: a transition run has
           no cue1, and a seg with nothing lit reads as a broken control. */
        const names = (got.windows || []).map((w) => w.window);
        if (names.indexOf(cq.window) < 0) {
          cq.window = names.indexOf(FIRST_WINDOW[cq.kind]) >= 0
            ? FIRST_WINDOW[cq.kind] : (names[0] || cq.window);
        }
      }
    } catch (e) {
      /* A refused parameter is not a fault; it is the server saying which
         field is wrong. It goes where the fields are, and the section
         opens so it is seen. An unchecked transition is not a parameter,
         and the overview already says it where the grid would be. */
      if (/transition windows have never been checked/.test(e.message || '')) {
        // said in the overview; the toast below is enough here
      } else if (/has to be|outside|not a number|not one of|never been checked/
            .test(e.message || '')) {
        cParamErr = e.message;
        cOpen.params = true;
      } else {
        reportClientError('arc.coupling.run', e.message, e.stack);
      }
      toast('That did not run: ' + e.message, 'err', 8000);
    } finally {
      cBusy = false;
      if (BARRY.views.toolkit.tool() === 'coupling') renderCMain();
    }
  }

  async function doCouplingSave() {
    if (!cRun) return;
    try {
      const res = await apiPost(
        '/api/arc/coupling/' + encodeURIComponent(cq.gid) + '/save',
        { result: cRun, entry_id: cRun.entry_id });
      cSaved = res.rel;
      toast('Filed under Results \u00b7 ' + res.rel, 'ok', 6000);
    } catch (e) {
      toast('That did not save: ' + e.message, 'err', 8000);
      reportClientError('arc.coupling.save', e.message, e.stack);
    }
    if (BARRY.views.toolkit.tool() === 'coupling') renderCMain();
  }

  /* ---------------- the matrix ----------------

     Twelve regions, so 66 unordered pairs -- drawn as the lower triangle
     of a 12x12 rather than a list, because what somebody is looking for
     is which CORNER of the brain lit up, and a list of 66 rows hides
     that completely. */
  function cResult() {
    if (cBusy) {
      return loader(cq.kind === 'transition'
                      ? 'Reading three transition windows'
                      : 'Reading four windows',
                    '32 channels, 66 region pairs, three methods');
    }
    if (!cRun) {
      return el('div', { class: 'empty-state' }, [
        el('p', { text: 'Nothing has been computed for this pair yet. '
                        + 'Run the analysis to see the matrix.' }),
      ]);
    }
    const win = (cRun.windows || []).find((w) => w.window === cq.window)
                || (cRun.windows || [])[0];
    if (!win) return el('p', { class: 'hint', text: 'No windows came back.' });
    const stale = cRun.__sent !== undefined
                  && cRun.__sent !== JSON.stringify(cParams || null);

    return el('div', {}, [
      stale ? el('p', { class: 'arc-ov-refused',
        text: 'The parameters have changed since this was run, so the '
              + 'matrix below is at the old ones. Run it again to see the '
              + 'new.' }) : null,
      el('div', { class: 'arc-cp-controls' }, [
        el('div', { class: 'seg' }, (cRun.windows || []).map((w) =>
          el('button', {
            class: cq.window === w.window ? 'active' : '',
            text: WINDOW_NAMES[w.window] || w.window,
            onclick: () => { cq.window = w.window; renderCMain(); },
          }))),
        el('div', { class: 'seg' }, METHODS.map(([id, name, note]) =>
          el('button', {
            class: cq.method === id ? 'active' : '',
            title: note, text: name,
            onclick: () => { cq.method = id; renderCMain(); },
          }))),
      ]),
      matrixGrid(win),
      matrixKey(),
      el('p', { class: 'hint',
        text: win.n_refused
          ? win.n_refused + ' of ' + (win.n_pairs || 0) + ' region pairs '
            + 'could not be computed: every channel in one of the two '
            + 'regions was excluded. They are blank, not zero.'
          : 'All ' + (win.n_pairs || 0) + ' region pairs computed.' }),
    ]);
  }

  function summaryOf(pr, method) {
    const got = (pr || {})[method];
    if (!got) return null;
    /* Two shapes: with curves asked for the summary is nested, without it
       the summary IS the method. Reading only one of them is how an export
       came out with a header and no rows. */
    const s = (got.summary && typeof got.summary === 'object')
      ? got.summary : got;
    return (s && s.value != null) ? s : null;
  }

  /* What the run says about one region -- which wire, what histology
     found -- or nothing, for a run made before runs said. Everything below
     degrades to the plain matrix rather than failing, because such a run
     is still a run and its numbers are still true; it just cannot say which
     wire they came from. */
  function regionInfo(name) {
    const cfg = cRun && cRun.sanity;
    if (!cfg) return null;
    const rec = (cfg.channel_sanity || []).find((r) => r.region === name
                                                    || r.label === name);
    if (!rec) return null;
    const w = (rec.windows || {})[cq.window] || {};
    return {
      label: rec.label || rec.region,
      region: rec.region,
      verdict: rec.histology,
      channel: w.channel,
      blocked: w.channel == null,
      why: w.why,
      /* "A different region" -- the probe is not where the map says it
         is. Flagged on the axis rather than only in the hover, because
         the whole point is that somebody reading the matrix should not
         have to ask. */
      moved: rec.histology === 'relocated',
      unsure: rec.histology === 'uncertain' || rec.histology === 'unscored',
    };
  }

  function headClass(info, kind) {
    let c = 'arc-mx-head ' + kind;
    if (!info) return c;
    if (info.blocked) c += ' blocked';
    if (info.moved) c += ' moved';
    else if (info.unsure) c += ' unsure';
    return c;
  }

  function headTitle(name, info) {
    if (!info) return name;
    const bits = [info.label];
    if (info.label !== info.region) {
      bits.push('The probe was aimed at ' + info.region + '.');
    }
    bits.push(info.channel != null
      ? 'Measured on CSC ' + info.channel + ' in '
        + (WINDOW_NAMES[cq.window] || cq.window) + '.'
      : 'Not measured in ' + (WINDOW_NAMES[cq.window] || cq.window) + '.');
    if (info.why) bits.push(info.why);
    return bits.join('\n');
  }

  function matrixGrid(win) {
    const order = cRun.region_order || [];
    const info = {};
    order.forEach((n) => { info[n] = regionInfo(n); });
    const by = {};
    for (const pr of (win.pairs || [])) {
      by[pr.a + '\u0000' + pr.b] = pr;
      by[pr.b + '\u0000' + pr.a] = pr;
    }
    /* Coherence is 0..1 and the two correlations are -1..1, so they are
       not the same scale and must not share one ramp. */
    const diverging = cq.method !== 'coherence';

    const cells = [];
    cells.push(el('div', { class: 'arc-mx-corner' }));
    order.forEach((b, j) => {
      const el_ = el('div', { class: headClass(info[b], 'col'),
                              title: headTitle(b, info[b]),
                              text: shortRegion(info[b] ? info[b].label : b) });
      el_.dataset.c = String(j);
      cells.push(el_);
    });
    order.forEach((a, i) => {
      const rowHead = el('div', { class: headClass(info[a], 'row'),
                                  title: headTitle(a, info[a]),
                                  text: shortRegion(info[a] ? info[a].label
                                                            : a) });
      rowHead.dataset.r = String(i);
      cells.push(rowHead);
      order.forEach((b, j) => {
        let node;
        if (a === b) {
          node = el('div', { class: 'arc-mx-cell self' });
        } else if ((info[a] && info[a].blocked)
                   || (info[b] && info[b].blocked)) {
          /* Blocked is not "not computed". A blank cell means nobody
             asked; this one means somebody asked and the answer is that
             there is no wire to ask with. Different mark, and the reason
             is on it -- which side is blocked and for what. */
          const why = [(info[a] || {}).blocked ? info[a].why : null,
                       (info[b] || {}).blocked ? info[b].why : null]
            .filter(Boolean);
          node = el('div', {
            class: 'arc-mx-cell blocked',
            title: (info[a] ? info[a].label : a) + ' \u00d7 '
                   + (info[b] ? info[b].label : b) + '\n\n' + why.join('\n\n'),
          });
        } else {
          const s = summaryOf(by[a + '\u0000' + b], cq.method);
          if (!s) {
            node = el('div', { class: 'arc-mx-cell none',
                               title: a + ' \u00d7 ' + b
                                      + ' \u2014 not computed' });
          } else {
            const v = Number(s.value);
            const moved = (info[a] && info[a].moved)
                          || (info[b] && info[b].moved);
            node = el('div', {
              class: 'arc-mx-cell' + (moved ? ' moved' : ''),
              style: 'background-color:' + cellColour(v, diverging),
              title: (info[a] ? info[a].label : a) + ' \u00d7 '
                     + (info[b] ? info[b].label : b) + '\n'
                     + s.what + ': ' + v.toFixed(4)
                     + (s.x != null ? '\nat ' + s.x + ' ' + (s.x_unit || '')
                                    : '')
                     + (moved ? '\n\nOne of these is not the region the '
                              + 'probe was aimed at.' : ''),
              text: v.toFixed(2).replace('0.', '.'),
            });
          }
        }
        node.dataset.r = String(i);
        node.dataset.c = String(j);
        cells.push(node);
      });
    });

    const grid = el('div', {
      class: 'arc-mx',
      style: 'grid-template-columns: 58px repeat(' + order.length
             + ', minmax(0, 1fr));',
    }, cells);
    crosshair(grid);
    return grid;
  }

  /* Follow a cell back to the two names that made it.

     A 12x12 of four-letter abbreviations is unreadable at the point it
     matters: the cell you are looking at is eight rows from its label and
     eleven columns from the other, and counting squares is how people
     misread a matrix. The trail runs LEFT along the row and UP the column
     -- to the two headers and no further -- because those are the only two
     directions that end at a name. Lighting the whole row and column would
     be twice the paint for the same information and would cross the
     diagonal, where the pair does not exist.

     Delegated on the grid rather than bound per cell: 169 nodes, rebuilt
     on every window and method change, and 338 listeners left to be
     collected each time is how a panel gets slow in a way nobody can find
     afterwards. */
  function crosshair(grid) {
    let lit = [];
    const clear = () => { lit.forEach((n) => n.classList.remove('lit',
                                                               'lit-head'));
                          lit = []; };
    const light = (r, c) => {
      clear();
      if (r == null || c == null) return;
      for (const n of grid.children) {
        const nr = n.dataset.r, nc = n.dataset.c;
        if (nr === undefined && nc === undefined) continue;
        const isRowHead = nr !== undefined && nc === undefined;
        const isColHead = nc !== undefined && nr === undefined;
        if (isRowHead) {
          if (Number(nr) === r) { n.classList.add('lit-head'); lit.push(n); }
          continue;
        }
        if (isColHead) {
          if (Number(nc) === c) { n.classList.add('lit-head'); lit.push(n); }
          continue;
        }
        const ri = Number(nr), ci = Number(nc);
        /* Left along this row, up this column. `<=` so the cell under the
           pointer is lit too -- it is the thing being asked about. */
        if ((ri === r && ci <= c) || (ci === c && ri <= r)) {
          n.classList.add('lit');
          lit.push(n);
        }
      }
    };
    grid.addEventListener('mouseover', (e) => {
      const n = e.target.closest('.arc-mx-cell');
      if (!n || !grid.contains(n)) return;
      light(Number(n.dataset.r), Number(n.dataset.c));
    });
    grid.addEventListener('mouseleave', clear);
  }

  /* A legend, because four of the marks above are conventions rather than
     data and a convention nobody is told is a decoration. */
  function matrixKey() {
    const cfg = cRun && cRun.sanity;
    if (!cfg) return null;
    const moved = (cfg.channel_sanity || []).filter(
      (r) => r.histology === 'relocated');
    const unsure = (cfg.channel_sanity || []).filter(
      (r) => r.histology === 'uncertain' || r.histology === 'unscored');
    const out = [];
    if (moved.length) {
      out.push(el('span', { class: 'arc-mx-key moved',
        title: moved.map((r) => r.label).join('\n'),
        text: moved.length + ' region'
              + (moved.length === 1 ? ' is' : 's are')
              + ' not where the probe was aimed' }));
    }
    if (unsure.length) {
      out.push(el('span', { class: 'arc-mx-key unsure',
        title: unsure.map((r) => r.label).join('\n'),
        text: unsure.length + ' scored without confidence' }));
    }
    const blocked = (cfg.blocked || {})[cq.window];
    if (blocked && blocked.n) {
      out.push(el('span', { class: 'arc-mx-key blocked',
        title: (blocked.regions || []).join('\n'),
        text: blocked.n + ' of ' + blocked.of + ' pairs blocked here \u2014 '
              + (blocked.regions || []).join(', ') + ' had no usable wire' }));
    }
    if (!out.length) {
      out.push(el('span', { class: 'arc-mx-key ok',
        text: 'Every region is where the probe was aimed and has a usable '
              + 'wire in this window.' }));
    }
    return el('div', { class: 'arc-mx-keys' }, out);
  }

  function shortRegion(name) {
    const bits = String(name).split(' ');
    return (bits[0] || '').charAt(0) + (bits[1] || name);
  }

  /* Colour from the theme, never a literal. `--accent` for one-sided
     measures and the semantic pair for a signed one, so the ramp means
     the same thing in every theme. */
  function cellColour(v, diverging) {
    if (diverging) {
      const t = Math.max(-1, Math.min(1, v));
      const tok = t >= 0 ? '--err' : '--accent';
      return withAlpha(BARRY.token(tok), Math.min(0.85, Math.abs(t)));
    }
    return withAlpha(BARRY.token('--ok'),
                     Math.min(0.85, Math.max(0, v)));
  }

  function withAlpha(colour, a) {
    const c = String(colour || '').trim();
    const m = /^#([0-9a-f]{6})$/i.exec(c);
    if (!m) return c;
    const n = parseInt(m[1], 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ','
           + (n & 255) + ',' + a.toFixed(3) + ')';
  }

  return {
    paint,
    /* Coupling's matrix pieces, for Circuit (web/js/circuit.js), so the two
       matrices light, colour and abbreviate one way rather than two. */
    shared: { crosshair, cellColour, withAlpha, shortRegion },
    steps: () => STEPS.map((s) => Object.assign({}, s)),
    step: stepOf,
    /* ----------------------------------------------------------------
       Batch mode's way in, for `web/_dev`.

       The two predicates are exported as the functions the panel itself
       calls, not as copies: a harness that re-derives what it is checking
       checks nothing. `skipReason` is the whole of "automatically unselect
       those removed", so it is the one worth driving against a real
       reading of a real recording.
       ---------------------------------------------------------------- */
    batch: {
      get on() { return bulk.on; },
      get running() { return bulk.running; },
      mode: (on) => { bulk.on = !!on; paint(); },
      rows: () => (rows || []).slice(),
      want: () => Object.keys(bulk.want),
      pick: (gid, on) => {
        if (on === false) delete bulk.want[gid];
        else bulk.want[gid] = true;
        renderBatch();
      },
      clear: () => { bulk.want = {}; bulk.off = {}; renderBatch(); },
      clipping: (on) => { bulk.clip = !!on; renderBatch(); },
      state: (gid) => Object.assign({}, bulk.state[gid] || {}),
      off: () => Object.assign({}, bulk.off),
      cost: costOf,
      skipReason: skipReason,
      exclusionFrom: exclusionFrom,
      exclusionBoth: exclusionBoth,
      lengths: () => Object.assign({}, tq),
      stop: () => { bulk.stop = true; renderBatch(); },
      run: runBatch,
    },
    /* ----------------------------------------------------------------
       The matrix's way in, for `web/_dev`.

       Every check below would otherwise need a real analysis behind it --
       four windows of thirty-two channels, three methods, about three
       minutes -- to assert something that is entirely about how the grid
       is drawn. So the run can be handed in. What must NOT be handed in
       is the reading of it: `info` is the function the grid itself calls,
       not a copy, so a harness cannot quietly agree with itself.
       ---------------------------------------------------------------- */
    matrix: {
      /* Draws the result straight into the panel's host, skipping the
         recording picker and the bank read that normally stand in front
         of it -- neither of which the grid depends on. The window and
         method segs inside it still go through `renderCMain`, which DOES
         need those, so a harness changes windows by calling this again
         rather than by clicking them. */
      _show: (run, q) => {
        cRun = run || null;
        cBusy = false;
        if (q) Object.assign(cq, q);
        const host = document.getElementById('cpMain');
        if (!host) return false;
        host.innerHTML = '';
        host.appendChild(cResult());
        return true;
      },
      get run() { return cRun; },
      get query() { return Object.assign({}, cq); },
      info: (name) => regionInfo(name),
    },
    /* The overview's way in. `pick` is the panel's own picker, and `over`
       is exactly what the panel drew from, so a harness compares the page
       against the server's answer rather than against a copy of it. */
    overview: {
      pick: (gid) => pickCoupling(gid),
      get over() { return cOver; },
      get params() { return Object.assign({}, cParams || {}); },
      get pair() { return cq.pair; },
      get error() { return cParamErr; },
      /* State or transition, and the panel's own switch for it. */
      get kind() { return cq.kind; },
      setKind: (k) => setCouplingKind(k),
      run: () => doCouplingRun(),
    },
    /* ----------------------------------------------------------------
       Clean's way in.

       The mode paints the decisions and this panel banks them, so the two
       have to be reading one set of structures. A mode holding its own
       copy of the exclusion list is a mode whose work reaches the bank
       only by coincidence -- and the coincidence would hold right up
       until somebody left the mode and came back.

       Everything here is by CSC NUMBER, never by row index: the pane's
       row list changes the moment a channel file goes missing, and an
       index would then name a different channel with perfect confidence.
       ---------------------------------------------------------------- */
    clean: {
      windows: windowsOf,
      pair: pairById,
      spans: spansOf,
      wasEdited: editedSpans,
      setSpans: (pid, csc, list) => { setSpans(pid, csc, list); afterDecision(); },
      resetSpans: (pid, csc) => { resetSpans(pid, csc); afterDecision(); },
      lost: lostOf,
      grade: gradeOf,
      flagged: flaggedOf,
      kept: keptOf,
      /* What is absent from the analysis for reasons that have nothing to
         do with clipping. Both were being counted as "nothing excluded",
         which reads as a clean bill of health over a recording missing
         half its wires. */
      bad: () => ((clip && clip.bad) || []).slice(),
      /* File from inside Clean, through the panel's own route rather than
         a second copy of it: one place knows what an entry has to carry.
         Returns what was filed so the mode can say so. */
      file: async () => {
        const res = await apiPost(
          '/api/arc/spark/' + encodeURIComponent(q.gid) + '/bank',
          { excluded: excluded, kept: keptAll() });
        const t = dropTally();
        BARRY.activity.log('arc.spark.bank', {
          gid: q.gid, n: res.n, excluded: t.n, channels: t.chans,
          pairs: t.pairs, via: 'clean',
        });
        await loadRows();
        if (BARRY.views.toolkit.tool() === 'spark') {
          renderPick(); renderRead();
        }
        return res;
      },
      present: () => ((clip && clip.present) || []).slice(),
      /* Everything below takes a `kind` -- 'state' or 'transition' -- and
         means 'state' without one, which is all it meant before the
         transition windows existed. The decisions themselves live in one
         structure keyed by window name, and a window name says its kind. */
      blocksGone: (pid, kind) => droppingOf(pid, kind).reduce(
        (n, c) => n + goneOf(pid, c, kind).length, 0),
      /* One kind's exclusion for a pair; `'all'` is what the bank is sent,
         both kinds in one dict. */
      excluded: (pid, kind) => (kind === 'all'
                                ? Object.assign({}, excluded[String(pid)] || {})
                                : exclKind(pid, kind || 'state')),
      isKept: (pid, csc, kind) => channelKept(pid, csc, kind),
      setKept: (pid, csc, keep, kind) => {
        setKept(pid, csc, keep, kind); afterDecision();
      },
      /* The block, which is the unit a decision is actually made in. */
      blockKept: (pid, csc, w) => blockKept(pid, csc, w),
      setBlock: (pid, csc, w, keep) => {
        setBlock(pid, csc, w, keep); afterDecision();
      },
      gone: goneOf,
      dropping: droppingOf,
      overruled: overruledOf,
      chans: chansOf,
      names: (kind) => namesOf(kind).slice(),
      kinds: () => KINDS.slice(),
      kindSay: (kind) => KIND_SAY[kind] || kind,
      measured: measuredKind,
      /* The lengths the transition reading was made at, or null. */
      lengths: () => {
        const t = (clip && clip.transition) || {};
        return t.measured ? { before: t.before_s, after: t.after_s } : null;
      },
      say: (w) => WINDOW_SAY[w] || w,
      keepAll: (pid, kind) => {
        for (const c of chansOf(pid, kind)) setKept(pid, c, true, kind);
        afterDecision();
      },
      dropAll: (pid, kind) => {
        for (const c of flaggedOf(pid, kind)) setKept(pid, c, false, kind);
        afterDecision();
      },
      tally: dropTally,
      wires: wireGrid,
      /* What the bank is sent as `kept`: per pair, per window. */
      keptBlocks: (pid) => (pid == null ? keptAll() : keptFor(pid)),
    },
  };
})();

/* ==========================================================================
   Spark's two Xplorefinder modes.

   The panel can say sixteen pairs were found at 10.0003 s apart. It cannot
   say whether that is true, because the only evidence for it is in the
   traces -- so both of these put the pairs ON the recording and let you
   look.

   They are two modes and not one because they answer different questions
   and want different things on screen:

     Confirm   are these the right pairs? Every pulse is drawn, including
               the mirrors and bounces that were dropped, so what was
               thrown away is as visible as what was kept.

     Clean     which of these is still usable? The four analysis windows
               are drawn per pair, the saturated stretches are highlighted
               on the channels that saturated, and each flagged channel is
               kept or dropped by hand against the measurement.

   Both draw through one hook in `xplore.js`, both take the whole interface,
   and both put the other one out first -- there is one set of panes, one
   keyboard and one aid window, and two modes sharing them is how you get
   two toolbars and two key handlers fighting.

   WHY CLEAN IS A PANEL AND NOT A STATUS LINE

   The first version of this was one strip of text. It said which pair you
   were on, how many channels had clipped, and which keys moved you -- all
   of it true, and none of it a thing you could act on. What it left out is
   the only part that matters downstream: those channels are dropped from
   the connectivity analysis, and the strip never said so.

   So the mode now carries the decision as well as the reading. The
   sentence about what is excluded is the widest thing on it; every flagged
   channel is a button that keeps or drops it, red for going and green for
   staying; and a stretch of saturation that is not really saturation can
   be dismissed, widened, or dragged to the span you actually want out.
   The structures all of that writes into live in `BARRY.arc`, so what the
   bank is handed is the list on screen rather than a copy of it.
   ========================================================================== */
BARRY.arcmode = (function () {
  let kind = null;         // 'confirm' | 'clean' | null
  let sess = null;
  let read = null;         // the Spark reading for this recording
  let clip = null;         // the clipping reading, if there is one
  let at = 0;              // which pair we are looking at
  let panel = null;
  /* Which channel the stretch editor is on, by CSC number. Never a row
     index -- see the note on `BARRY.arc.clean`. */
  let pick = null;
  /* A stretch being dragged into shape, before it is confirmed. Held
     apart from the stored spans so Cancel is a delete and not an undo,
     and so nothing downstream ever sees a half-finished drag. */
  let edit = null;

  function pairs() { return (read && read.pairs) || []; }
  function now() { return pairs()[at] || null; }

  /* One definition of the four windows, in `BARRY.arc`, because the
     exclusion is worked out against the same boundaries this draws. Two
     copies of the pad would drift the day somebody changed one. */
  const windowsOf = (p) => BARRY.arc.clean.windows(p);

  /* Which blocks Clean is showing: the four state windows or the three
     transition windows. One decision model underneath -- a window name
     says its kind -- so switching views loses nothing and "Save and
     return" files both. */
  let view = 'state';
  /* The regions and the histology, for the rescue/ruin grid. Null until
     the small route answers; `{error}` if it could not. */
  let regs = null;

  /* The windows of the view on screen -- what is shaded, what a stretch is
     said to fall in. Confirm always shows the state windows. */
  const windowsView = (p) => BARRY.arc.clean.windows(
    p, kind === 'clean' ? view : 'state');

  async function enter(which, gid, reading, clipping, atPair, atView) {
    /* One mode at a time, and this is the function responsible for it. */
    BARRY.modes.leaveAllBut('arcmode');   // every other mode; see core.js
    if (kind) exit();

    const path = reading && reading.path;
    if (!path) {
      toast('None of this recording’s paths are reachable from this '
            + 'machine, so there is nothing to look at.', 'err', 7000);
      return false;
    }
    kind = which;
    read = reading;
    clip = clipping || null;
    at = Math.max(0, Math.min(pairs().length - 1, atPair || 0));
    pick = null;
    edit = null;
    view = atView === 'transition' ? 'transition' : 'state';
    regs = null;
    if (which === 'clean' && gid) {
      /* Not awaited: the blocks are usable without it, and the grid says
         it is waiting rather than holding the whole mode up. */
      api('/api/arc/spark/' + encodeURIComponent(gid) + '/regions')
        .then((got) => { if (kind === 'clean') { regs = got; render(); } })
        .catch((e) => {
          regs = { error: e.message };
          reportClientError('arc.clean.regions', e.message, e.stack);
          if (kind === 'clean') render();
        });
    }

    setView('xplore');
    sess = await BARRY.views.xplore.open(path);
    if (!sess) { kind = null; return false; }

    setMode('arc' + which, exit);
    /* One pane. These modes are about time, not about geometry: what is
       being checked is where a pulse fell, and six region panes would give
       six copies of the same answer in a sixth of the height. */
    BARRY.views.xplore.setPanes([{ panel: 'traces' }], { col: 0.5, row: 0.5 });
    if (which === 'clean') grab();
    render();
    document.addEventListener('keydown', keys, true);
    BARRY.activity.log('arc.' + which + '.enter',
                       { gid: gid, pairs: pairs().length, at: at }, sess);
    goTo(at);
    return true;
  }

  function exit() {
    document.removeEventListener('keydown', keys, true);
    /* Hand the pointer back. A mode that keeps `grabTime` after it has
       gone owns every press on the pane and the traces stop panning, with
       nothing on screen to say why. */
    if (BARRY.views.xplore.grabTime) BARRY.views.xplore.grabTime(null);
    if (panel && panel.parentNode) panel.parentNode.removeChild(panel);
    panel = null;
    kind = null;
    sess = null;
    read = null;
    clip = null;
    pick = null;
    edit = null;
    view = 'state';
    regs = null;
    setMode(null);
  }

  /* Switching between the state and the transition blocks. The channel
     picked stays picked if it is on the other list too; the stretch being
     dragged does not survive, because it was being drawn against the
     other view's windows. NOT `setView`: that is the app's own global for
     changing views, and this module calls it on the way in. */
  function setBlockView(v) {
    const next = v === 'transition' ? 'transition' : 'state';
    if (next === view) return;
    view = next;
    edit = null;
    if (pick != null && !onList(pick)) pick = null;
    BARRY.activity.log('arc.clean.view', { view: view }, sess);
    render();
  }

  function goTo(i) {
    const list = pairs();
    if (!list.length) return;
    at = Math.max(0, Math.min(list.length - 1, i));
    /* A stretch half-dragged on one pair means nothing on the next one,
       and carrying it across would leave a handle floating over a channel
       nobody was editing. */
    edit = null;
    const w = windowsOf(list[at]);
    /* The whole event plus both pads, with a little room either side --
       the span the clipping was measured over, so what is on screen is
       what was judged. */
    const a = w[0][1], b = w[w.length - 1][2];
    BARRY.views.xplore.setWindow(0, Math.max(0, a - 2), (b - a) + 4);
    if (pick != null && !onList(pick)) pick = null;
    render();
  }

  function keys(e) {
    if (!kind) return;
    const tag = (e.target && e.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) {
      return;
    }
    // Anything modified belongs to the browser or the app, not here.
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key;

    if (k === 'Escape') {
      /* Escape gets out of the smallest thing first. Leaving the whole
         mode to call off a drag would throw away the pair you were in the
         middle of, and "I pressed escape and lost my place" is not a
         trade anybody would have chosen. */
      if (edit) { edit = null; render(); } else exit();
      stop(e); return;
    }
    if (k === 'n' || k === 'ArrowRight') { goTo(at + 1); stop(e); return; }
    if (k === 'p' || k === 'ArrowLeft') { goTo(at - 1); stop(e); return; }
    if (kind !== 'clean') return;

    /* Up and down move between the channels WITHOUT deciding anything,
       which is the one thing clicking cannot do: a click on a channel
       keeps or drops it. Somebody reading down the list to see what is
       there should not have to change it twice to leave it as it was. */
    if (k === 'ArrowDown') { movePick(1); stop(e); return; }
    if (k === 'ArrowUp') { movePick(-1); stop(e); return; }
    if (k === 't' || k === 'T') {
      setBlockView(view === 'state' ? 'transition' : 'state');
      stop(e); return;
    }
    if (k === 'k' || k === 'K') { decide(pick, true); stop(e); return; }
    if (k === 'x' || k === 'X') { decide(pick, false); stop(e); return; }
    if (k === 'Enter') {
      if (edit) commitEdit(); else if (pick != null) toggle(pick);
      stop(e);
    }
  }

  function stop(e) { e.preventDefault(); e.stopPropagation(); }

  /* The reading of the view on screen. The transition half only when it
     was measured -- otherwise there is no list to show, and the panel
     says so rather than showing an empty one that reads as clean. */
  function clipOfPair(id, k) {
    const which = k || (kind === 'clean' ? view : 'state');
    if (which === 'transition') {
      const t = (clip && clip.transition) || null;
      if (!t || !t.measured) return null;
      return (t.by_pair || {})[String(id)] || null;
    }
    return ((clip && clip.by_pair) || {})[String(id)] || null;
  }

  /* Every channel of this pair the clipping reading has anything to say
     about -- the ones that lost a window AND the ones that merely grazed
     the rail. The grazed ones are listed because "CSC 9 touched the rail
     for four milliseconds and is being kept" is an answer, and an absent
     row is not. */
  function chansHere() {
    const p = now();
    const bad = p ? clipOfPair(p.pair_id) : null;
    return bad ? Object.keys(bad).map(Number).sort((a, b) => a - b) : [];
  }

  const onList = (csc) => chansHere().indexOf(Number(csc)) >= 0;

  function movePick(d) {
    const list = chansHere();
    if (!list.length) return;
    const i = pick == null ? (d > 0 ? -1 : 0) : list.indexOf(Number(pick));
    pick = list[Math.max(0, Math.min(list.length - 1, i + d))];
    edit = null;
    render();
  }

  /* Keep or drop one channel for the pair in view.
   *
   * `decide(c, true)` means KEEP: the measurement says this channel lost a
   * window and somebody has looked and disagreed. Everything runs through
   * `BARRY.arc.clean`, so the chip that turns green and the list the bank
   * is handed are one structure read twice. */
  function decide(csc, keep) {
    const p = now();
    if (!p || csc == null) return;
    const lost = BARRY.arc.clean.lost(p.pair_id, csc, view);
    if (!lost.length) {
      toast('CSC' + csc + ' did not lose ' + (view === 'transition'
              ? 'a transition window' : 'a window')
            + ' of this pair, so it is already going into the analysis. '
            + 'Nothing to keep.', null, 5000);
      return;
    }
    BARRY.arc.clean.setKept(p.pair_id, csc, keep, view);
    pick = Number(csc);
    BARRY.activity.log('arc.clean.' + (keep ? 'keep' : 'drop'),
                       { pair: p.pair_id, csc: Number(csc), view: view,
                         windows: lost.length }, sess);
    render();
  }

  function toggle(csc) {
    const p = now();
    if (!p) return;
    decide(csc, !BARRY.arc.clean.isKept(p.pair_id, csc, view));
  }

  /* ==================================================================
     The saturated stretches, and changing your mind about one
     ==================================================================
     A stretch is a claim that the amplifier sat at its rail from a to b.
     Three things can be wrong with it, and there is a verb for each:

       it is not really clipping   dismiss it
       it is wider than that       widen it, or drag it
       there is one it missed      draw a new one

     Dismissing every stretch in a window takes that window out of the
     loss, which is what makes the channel go green on its own rather than
     leaving a red row contradicting the decision that had just been made
     about it. `BARRY.arc.clean.lost` is where that rule lives.
     ================================================================== */

  /* A quarter of its own length each side, and never less than 50 ms --
     enough to be worth a click on a stretch of a few milliseconds, and
     proportionate on one that is already half a window. */
  const GROW = 0.25;
  const GROW_MIN = 0.05;

  /* Copies, and sorted. The editor rewrites the whole list every time
     rather than patching one entry, because the only thing that reads it
     afterwards is the overlap test, and an unsorted list of stretches is
     a list two people will read differently. */
  function writeSpans(p, csc, list) {
    BARRY.arc.clean.setSpans(p.pair_id, csc,
      list.slice().sort((x, y) => x.a - y.a));
  }

  function liveSpans(p, csc) {
    return BARRY.arc.clean.spans(p.pair_id, csc).map(
      (s) => ({ a: s.a, b: s.b, hand: s.hand }));
  }

  /* What a change did to the verdict, said out loud. The channel going
     from red to green is the consequence of dismissing a stretch, and it
     happens three rows away from the button that was pressed. */
  function sayVerdict(p, csc, was) {
    const C = BARRY.arc.clean;
    const now_ = C.lost(p.pair_id, csc, view).length;
    if (now_ === was) return;
    const dropped = now_ > 0 && !C.isKept(p.pair_id, csc, view);
    toast('CSC' + csc + ' is now '
          + C.grade(now_, C.names(view).length)
          + (view === 'transition' ? ' at the transitions' : '')
          + (dropped ? ' — still excluded from this pair.'
                     : ' — it goes into the analysis.'),
          dropped ? 'warn' : 'ok', 6000);
  }

  function dismissSpan(i) {
    const p = now();
    if (!p || pick == null) return;
    const was = BARRY.arc.clean.lost(p.pair_id, pick, view).length;
    writeSpans(p, pick, liveSpans(p, pick).filter((_, k) => k !== i));
    BARRY.activity.log('arc.clean.span.drop',
                       { pair: p.pair_id, csc: pick }, sess);
    render();
    sayVerdict(p, pick, was);
  }

  function widenSpan(i) {
    const p = now();
    if (!p || pick == null) return;
    const was = BARRY.arc.clean.lost(p.pair_id, pick, view).length;
    const list = liveSpans(p, pick);
    const s = list[i];
    if (!s) return;
    const by = Math.max(GROW_MIN, (s.b - s.a) * GROW);
    /* Clamped to the four windows. Outside them nothing was measured and
       nothing is analysed, so a stretch that ran past the pad would be a
       claim about samples this pair never looks at. */
    const w = windowsOf(p);
    list[i] = { a: Math.max(w[0][1], s.a - by),
                b: Math.min(w[w.length - 1][2], s.b + by), hand: true };
    writeSpans(p, pick, list);
    render();
    sayVerdict(p, pick, was);
  }

  function restoreSpans() {
    const p = now();
    if (!p || pick == null) return;
    const was = BARRY.arc.clean.lost(p.pair_id, pick, view).length;
    BARRY.arc.clean.resetSpans(p.pair_id, pick);
    edit = null;
    render();
    sayVerdict(p, pick, was);
  }

  /* Arm a drag. `i` is the stretch it will replace, or -1 for a new one,
     in which case the first press sets both edges at once. */
  function armEdit(i) {
    const p = now();
    if (!p || pick == null) return;
    const s = i >= 0 ? liveSpans(p, pick)[i] : null;
    edit = { csc: pick, i: i, a: s ? s.a : null, b: s ? s.b : null,
             hold: null };
    render();
  }

  function commitEdit() {
    const p = now();
    if (!p || !edit) return;
    if (edit.a == null || !(edit.b > edit.a)) {
      toast('Drag on the traces first — a stretch with no width is not a '
            + 'stretch.', 'warn', 5000);
      return;
    }
    /* Read off the edit, not off `pick`. They are the same channel today,
       and the day they are not is the day a confirmed drag lands on a
       channel nobody was dragging on. */
    const csc = edit.csc;
    const was = BARRY.arc.clean.lost(p.pair_id, csc, view).length;
    const list = liveSpans(p, csc);
    const one = { a: edit.a, b: edit.b, hand: true };
    if (edit.i >= 0 && edit.i < list.length) list[edit.i] = one;
    else list.push(one);
    writeSpans(p, csc, list);
    BARRY.activity.log('arc.clean.span.set', {
      pair: p.pair_id, csc: csc,
      a: Math.round(edit.a * 1e4) / 1e4, b: Math.round(edit.b * 1e4) / 1e4,
    }, sess);
    edit = null;
    render();
    sayVerdict(p, csc, was);
  }

  /* Dragging a stretch into shape.
   *
   * Through xplore's `grabTime` rather than a listener of this module's
   * own: the pane canvas already carries a mousedown that pans, and a
   * second one is two handlers fighting over one press -- which is the
   * fault that hook was added to avoid, and the same reason the channel
   * lines are hit-tested inside the existing handler rather than beside
   * it. `onStart` refuses every press unless a stretch is armed, so
   * panning is untouched the rest of the time. */
  function grab() {
    if (!BARRY.views.xplore.grabTime) return;
    BARRY.views.xplore.grabTime({
      onStart: (t) => {
        if (!edit) return false;
        if (edit.a == null) {
          // A new stretch: both edges start where the press landed and
          // the right-hand one follows the pointer.
          edit.a = t; edit.b = t; edit.hold = 'b';
        } else {
          /* Whichever edge the press is nearer. A drag that always took
             the right-hand edge would leave the left one unreachable
             without starting the stretch over. */
          edit.hold = Math.abs(t - edit.a) <= Math.abs(t - edit.b)
            ? 'a' : 'b';
          edit[edit.hold] = t;
        }
        repaint();
        return true;
      },
      onMove: (t) => {
        if (!edit || !edit.hold) return;
        edit[edit.hold] = t;
        repaint();
      },
      onEnd: (t) => {
        if (!edit || !edit.hold) return;
        edit[edit.hold] = t;
        edit.hold = null;
        if (edit.a > edit.b) {
          const x = edit.a; edit.a = edit.b; edit.b = x;
        }
        // Nothing is decided until Confirm: a drag that has just stopped
        // is a proposal, and the panel now has two numbers to show for it.
        render();
      },
    });
  }

  /* The canvas only. A drag repaints forty times a second and rebuilding
     the panel each time would take the focus off whatever has it. */
  function repaint() {
    if (BARRY.views.xplore.redraw) BARRY.views.xplore.redraw();
  }

  /* Which channels the pane is actually drawing.
   *
   * Read off the pane rather than off the recording: the channel ticks
   * change it, and a flagged channel nobody can see is worth saying out
   * loud rather than leaving as a stretch that never appears. Odd channels
   * in particular -- a pane on the Even preset holds none of them, and
   * every stretch on CSC17 would silently have nowhere to go. */
  function paneRows() {
    try {
      const XF = BARRY.views.xplore.state;
      const pane = (XF.panes || [])[0];
      const w = pane && pane._win;
      return ((w && w.series) || []).map((s) => Number(s.number));
    } catch (e) {
      return [];
    }
  }

  /* ==================================================================
     The panel
     ================================================================== */
  function render() {
    const host = document.getElementById('xfBody');
    if (!host) return;
    if (panel && panel.parentNode) panel.parentNode.removeChild(panel);
    const p = now();

    panel = el('div', { class: 'arc-panel', id: 'arcPanel' }, [
      topBar(p),
      kind === 'clean' ? cleanBody(p) : null,
    ].filter(Boolean));
    host.appendChild(panel);
    // The overlay changed, not the samples. Repaint rather than refetch.
    repaint();
  }

  let saving = false;

  /* File what has been decided, then leave. The banking itself belongs to
     the Spark panel -- one route, one place that knows what an entry has
     to carry -- so this asks it rather than building a second one. */
  async function saveAndBack() {
    if (saving) return;
    saving = true;
    render();
    try {
      const C = BARRY.arc.clean;
      const ts = C.tally('state'), tt = C.tally('transition');
      const res = await C.file();
      toast('Filed ' + res.n + ' cue pairs with their clipping decisions: '
            + ts.n + ' state block' + (ts.n === 1 ? '' : 's') + ' and '
            + (C.measured('transition')
               ? tt.n + ' transition block' + (tt.n === 1 ? '' : 's')
               : 'no transition blocks — the transition windows were not '
                 + 'checked')
            + ' left out.', 'ok', 7000);
      exit();
    } catch (e) {
      toast('That did not file: ' + e.message, 'err', 8000);
      reportClientError('arc.clean.save', e.message, e.stack);
    } finally {
      saving = false;
      if (kind) render();
    }
  }

  function topBar(p) {
    const list = pairs();
    const bits = [
      el('strong', { text: kind === 'clean' ? 'Clean' : 'Confirm' }),
      el('span', { class: 'arc-bar-n',
                   text: list.length ? (at + 1) + ' / ' + list.length
                                     : 'no pairs' }),
      el('button', { class: 'mini', text: '◀', title: 'The pair before  (← or p)',
                     disabled: at > 0 ? null : 'disabled',
                     onclick: () => goTo(at - 1) }),
      el('button', { class: 'mini', text: '▶', title: 'The next pair  (→ or n)',
                     disabled: at < list.length - 1 ? null : 'disabled',
                     onclick: () => goTo(at + 1) }),
    ];

    if (p) {
      bits.push(el('span', { class: 'arc-bar-pair',
        text: p.opener_label + ' → ' + p.closer_label }));
      /* WHY these two, stated on the bar rather than left to be inferred
         from two timestamps. This is the whole question the mode exists to
         answer. */
      bits.push(el('span', { class: 'arc-bar-why',
        text: 'two different cues, ' + p.gap_s.toFixed(4) + ' s apart'
              + (p.offset_from === 'mark'
                 ? ' · cue 2 ends on the rig’s own mark'
                 : ' · cue 2 end derived') }));
    }

    /* State or transition: which blocks are on screen. A segmented switch,
       the house control for an exclusive choice between two modes, and the
       count of what each view is removing rides on its label so the view
       NOT on screen is still accounted for. */
    if (kind === 'clean') {
      const C = BARRY.arc.clean;
      bits.push(el('div', { class: 'seg arc-view-seg' }, C.kinds().map((k) => {
        const n = p ? C.blocksGone(p.pair_id, k) : 0;
        const on = C.measured(k);
        return el('button', {
          class: view === k ? 'active' : '',
          'data-view': k,
          title: (k === 'transition'
                  ? 'The three windows around the boundaries  (t)'
                  : 'The four ten-second windows  (t)')
                 + (on ? '' : ' — not checked for clipping yet'),
          text: C.kindSay(k) + (on ? (n ? ' · ' + n + ' out' : '')
                                   : ' · not checked'),
          onclick: () => setBlockView(k),
        });
      })));
    }

    bits.push(el('div', { class: 'spacer' }));
    /* The keys, spelled as keys.
     *
     * The arrows have been bound since the first version of this mode and
     * were advertised nowhere, so the bar taught n and p to people whose
     * hand was already on the arrow keys -- "why is it n/p? not the arrow
     * keys" is the whole of the report. Both still work; the arrows are
     * named first, because they are the pair that needs no learning. */
    const keyBits = [
      el('kbd', { text: '←' }), el('kbd', { text: '→' }),
      el('span', { text: 'or' }),
      el('kbd', { text: 'n' }), el('kbd', { text: 'p' }),
      el('span', { text: 'step pairs' }),
    ];
    if (kind === 'clean') {
      keyBits.push(el('kbd', { text: '↑' }), el('kbd', { text: '↓' }),
                   el('span', { text: 'pick a channel' }),
                   el('kbd', { text: 'k' }), el('span', { text: 'keep' }),
                   el('kbd', { text: 'x' }), el('span', { text: 'drop' }),
                   el('kbd', { text: 't' }),
                   el('span', { text: 'state / transition' }));
    }
    keyBits.push(el('kbd', { text: 'esc' }),
                 el('span', { text: edit ? 'call off the drag' : 'leave' }));
    bits.push(el('span', { class: 'arc-bar-keys' }, keyBits));

    /* The way out, with the decisions written down.
     *
     * Leaving with Escape keeps them -- they live in `BARRY.arc`, not in
     * this mode, so stepping out and back costs nothing. But "kept in a
     * browser tab" is not saved, and somebody who has just been through
     * sixteen pairs deciding things should not have to find their way to
     * another panel's button to make them durable. So the primary action
     * here files them and goes back, and it is the last thing on the bar
     * because it is the one thing to click. */
    if (kind === 'clean') {
      bits.push(el('button', {
        class: 'btn ghost sm',
        text: 'Back to Spark',
        title: 'Leave without filing. The decisions are kept.',
        onclick: () => exit(),
      }));
      bits.push(el('button', {
        class: 'btn' + (saving ? ' off' : ''),
        disabled: saving ? 'disabled' : null,
        text: saving ? 'Filing…' : 'Save and return to Spark',
        title: 'File these cue pairs with the clipping decisions on them '
               + '— the state blocks and the transition blocks both — '
               + 'and go back to Spark.',
        onclick: saveAndBack,
      }));
    }
    return el('div', { class: 'arc-bar' }, bits);
  }

  function cleanBody(p) {
    if (!p) return null;
    if (!clip) {
      /* An empty state says what to do next. There is no way back to the
         clipping check from inside the mode -- it is a ten-second read of
         every channel and it belongs to the panel -- so it says where. */
      return el('div', { class: 'empty-state arc-nothing' }, [
        el('p', { text: 'Nothing has measured these windows for clipping, '
                        + 'so there is nothing here to keep or drop.' }),
        el('p', { class: 'hint',
                  text: 'Press esc to leave, then “Check for clipping” in '
                        + 'Spark. It reads every channel across four '
                        + 'windows a pair — about ten seconds.' }),
      ]);
    }
    if (view === 'transition' && !BARRY.arc.clean.measured('transition')) {
      /* Absent is not negative. A reading made before the transition
         windows existed has no answer for them, and three rows of green
         blocks would say the boundaries were clean when nobody looked. */
      return el('div', { class: 'arc-clean' }, [
        verdict(p),
        el('div', { class: 'empty-state arc-nothing' }, [
          el('p', { text: 'The transition windows of this recording have not '
                          + 'been checked for clipping, so there are no '
                          + 'transition blocks to keep or drop.' }),
          el('p', { class: 'hint',
                    text: 'Press esc to leave, then “Check again” in Spark: '
                          + 'one read of every channel answers both the '
                          + 'state and the transition windows.' }),
        ]),
      ]);
    }
    return el('div', { class: 'arc-clean' }, [
      verdict(p),
      chanList(p),
      wireBox(p),
      spanList(p),
    ].filter(Boolean));
  }

  /* Which wire each region will be measured on in this pair, in the view
     on screen, given what has been decided -- and where that is only true
     because a spare wire stepped in, or not true at all because the probe
     missed. Laid out like Coupling's channel-sanity grid, because it is
     the same question asked earlier: here while the blocks are still
     being decided, there once they are banked. */
  function wireBox(p) {
    const C = BARRY.arc.clean;
    if (!regs) {
      return el('div', { class: 'arc-wires' }, [
        loader('Reading the montage and the histology',
               'which wire each region uses, and where each probe is')]);
    }
    if (regs.error) {
      return el('p', { class: 'hint arc-wires',
        text: 'Which wire each region uses could not be worked out here: '
              + regs.error + ' The blocks above still decide what is '
              + 'banked.' });
    }
    const names = C.names(view);
    const grid = C.wires(p.pair_id, view, regs);
    let rescued = 0, gone = 0;
    const hist = grid.filter((r) => (r.windows[names[0]] || {}).state
                                    === 'hist').length;
    for (const r of grid) {
      for (const w of names) {
        const s = (r.windows[w] || {}).state;
        if (s === 'rescued') rescued += 1;
        if (s === 'gone') gone += 1;
      }
    }
    const head = el('div', { class: 'arc-cs-row head' }, [
      el('span', { class: 'arc-cs-reg', text: 'region' }),
    ].concat(names.map((w) => el('span', { class: 'arc-cs-w',
                                           text: C.say(w) }))));
    const rows = grid.map((r) => el('div', { class: 'arc-cs-row' }, [
      el('span', { class: 'arc-cs-reg ' + (r.histology || ''),
                   title: r.label, text: r.label }),
    ].concat(names.map((w) => {
      const c = r.windows[w] || {};
      return el('span', {
        class: 'arc-cs-c ' + (c.state || ''),
        'data-w': w, 'data-region': r.region,
        title: c.why || '',
        text: c.channel != null ? String(c.channel)
          : (c.state === 'hist' ? '—' : '✕'),
      });
    }))));
    const bits = [];
    bits.push(rescued
      ? rescued + ' region-window' + (rescued === 1 ? '' : 's')
        + ' rescued by a spare wire'
      : 'no region needs its spare wire');
    if (gone) bits.push(gone + ' with no usable wire');
    if (hist) bits.push(hist + ' ruled out by histology whatever its wires do');
    return el('div', { class: 'arc-wires' }, [
      el('div', { class: 'section-label',
                  text: 'Which wire each region uses · ' + bits.join(' · ') }),
      el('div', { class: 'arc-cs arc-cs-n' + names.length },
         [head].concat(rows)),
      el('p', { class: 'hint',
        text: 'A number is the one wire Coupling will measure that region on '
              + 'in that window — the lowest-numbered one not bad and not '
              + 'left out there. Outlined is a spare that took over because '
              + 'a lower wire is out; ✕ is a region with none left; '
              + '— is a probe the histology rules out, which is not '
              + 'computed whatever its wires do. A block kept here against '
              + 'the measurement is banked as kept, and Coupling uses it. '
              + 'Hover a cell for the reason.' }),
    ]);
  }

  /* The sentence this mode exists to make unmissable. Widest thing on the
     panel, in the colour of the outcome, and it names the channels rather
     than counting them -- "4 channels" is a number somebody has to go and
     look up, and the whole complaint was that the consequence was never
     stated where they were looking.

     About the view on screen, and then -- in the same strip, because the
     save files both -- one line for the view that is NOT on screen. A
     verdict that only spoke for the blocks in view would let somebody
     file a transition exclusion they had never looked at. */
  function verdict(p) {
    const C = BARRY.arc.clean;
    const T = view === 'transition';
    const measured = C.measured(view);
    const going = measured ? C.dropping(p.pair_id, view) : [];
    const blocks = measured ? C.blocksGone(p.pair_id, view) : 0;
    const overruled = measured ? C.overruled(p.pair_id, view) : [];
    const all = measured ? C.flagged(p.pair_id, view) : [];
    const bad = C.bad();
    const bits = [];
    const where = T ? ' at the transitions of this cue pair'
                    : ' for this cue pair';

    if (!measured) {
      bits.push(el('strong', { text: 'Not checked' }));
      bits.push(el('span', {
        text: 'The transition windows of this recording have not been '
              + 'measured, so nothing here is excluded at them — and '
              + 'nothing is known to be clean either.' }));
    } else if (blocks) {
      bits.push(el('strong', { text: blocks + (T ? ' transition' : '')
                                     + ' block'
                                     + (blocks === 1 ? '' : 's') }));
      bits.push(el('span', {
        text: 'across ' + going.length + ' channel'
              + (going.length === 1 ? '' : 's')
              + ' will be excluded from the connectivity analysis' + where
              + ':' }));
      /* Named, and named by window: "CSC17" is not the decision, "CSC17's
         baseline and cue 1" is. The whole complaint this strip answers was
         that the consequence was never stated where somebody was looking,
         and half-stating it is the same fault. */
      bits.push(el('span', { class: 'arc-verdict-who',
        text: going.map((c) => 'CSC' + c + ' ('
                               + C.gone(p.pair_id, c, view).map(C.say)
                                 .join(', ')
                               + ')').join('; ') }));
    } else {
      /* "Nothing is excluded" used to be followed by "every channel goes
         into the connectivity analysis", which is a claim about the
         recording and not about this cue pair -- and it was false whenever
         a channel was marked bad or simply absent. Those are counted
         separately now and said in the same breath, because a clean bill
         of health over a recording missing half its wires is worse than
         no sentence at all. */
      bits.push(el('strong', { text: 'Nothing is excluded' }));
      bits.push(el('span', {
        text: bad.length
          ? (T ? 'at this pair’s transitions by its clipping.'
               : 'by this pair’s clipping.')
          : where.slice(1) + ' — every channel goes into the '
            + 'connectivity analysis.' }));
    }

    /* The other view, in one line. */
    const other = T ? 'state' : 'transition';
    const oBlocks = C.measured(other) ? C.blocksGone(p.pair_id, other) : 0;
    bits.push(el('span', { class: 'arc-verdict-other',
      'data-view': other,
      text: C.measured(other)
        ? (oBlocks
           ? 'and ' + oBlocks + ' ' + (T ? 'state' : 'transition')
             + ' block' + (oBlocks === 1 ? '' : 's') + ' in the '
             + (T ? 'State' : 'Transition') + ' view'
           : 'nothing in the ' + (T ? 'State' : 'Transition') + ' view')
        : 'the transition windows are not checked' }));

    if (bad.length) {
      bits.push(el('span', {
        class: 'arc-verdict-bad',
        title: 'CSC ' + bad.join(', '),
        text: bad.length + ' channel' + (bad.length === 1 ? ' is' : 's are')
              + ' marked bad for the whole recording and '
              + (bad.length === 1 ? 'was' : 'were')
              + ' never measured for clipping.' }));
    }
    if (overruled.length) {
      bits.push(el('span', { class: 'arc-verdict-kept',
        text: overruled.length + ' kept against the measurement: CSC '
              + overruled.join(', ') }));
    }

    bits.push(el('div', { class: 'spacer' }));
    if (all.length) {
      const keeping = !blocks;
      bits.push(el('button', {
        class: 'btn ghost sm',
        text: keeping ? 'Remove them all again' : 'Keep all ' + all.length,
        title: keeping
          ? 'Put every flagged channel of this pair back to what the '
            + 'measurement says, which is that its lost blocks go.'
          : 'Overrule the measurement on every flagged channel of this '
            + 'pair, so none of its ' + (T ? 'transition ' : '')
            + 'blocks is removed.',
        onclick: () => {
          if (keeping) C.dropAll(p.pair_id, view);
          else C.keepAll(p.pair_id, view);
          BARRY.activity.log('arc.clean.' + (keeping ? 'dropAll' : 'keepAll'),
                             { pair: p.pair_id, n: all.length, view: view },
                             sess);
          render();
        },
      }));
    }
    return el('div', { class: 'arc-verdict' + (blocks ? '' : ' none')
                       + (measured ? '' : ' unmeasured') }, bits);
  }

  function chanList(p) {
    const C = BARRY.arc.clean;
    const all = chansHere();
    const names = C.names(view);
    const N = names.length;
    const NW = N === 3 ? 'three' : 'four';
    if (!all.length) {
      return el('p', { class: 'hint arc-nothing',
        text: 'No channel went near its rail in any of this pair’s '
              + NW + (view === 'transition' ? ' transition' : '')
              + ' windows. Nothing to decide here — → for the next '
              + 'pair.' });
    }
    const shown = new Set(paneRows());
    const missing = [];

    /* One row per channel, one block per window of the view on screen.
     *
     * The blocks ARE the decision. A cue pair is four windows and a
     * channel can be ruined in one and perfectly good in the other three,
     * which on this data is most of the data -- so deciding per channel
     * threw three quarters of a usable wire away with the quarter that
     * was bad. Clicking a block keeps or removes that block and nothing
     * else. The transition view is the same model with three blocks, one
     * per boundary.
     *
     * Every block is clickable, including the ones the measurement was
     * happy with: "this one looks wrong to me" is a decision somebody is
     * entitled to make, and a block that cannot be clicked cannot record
     * it. */
    const rows = all.map((c) => {
      const lost = C.lost(p.pair_id, c, view);
      const gone = C.gone(p.pair_id, c, view);
      if (!shown.has(c)) missing.push(c);

      const blocks = names.map((w) => {
        const wasLost = lost.indexOf(w) >= 0;
        const keeping = C.blockKept(p.pair_id, c, w);
        /* Four states, and each says a different thing:
             removed   going out of the analysis
             kept      staying, and the measurement agreed
             overrule  staying, and the measurement did not agree
             clean     staying, nothing was ever wrong with it       */
        const state = !keeping ? 'removed'
          : wasLost ? 'overrule' : 'clean';
        return el('button', {
          class: 'arc-blk ' + state,
          'data-w': w,
          title: 'CSC' + c + ' · ' + C.say(w)
                 + (wasLost ? ' — the amplifier saturated here'
                            : ' — nothing wrong measured here')
                 + '. ' + (keeping ? 'It is going INTO the analysis. Click '
                                     + 'to remove it.'
                                   : 'It will be REMOVED. Click to keep it.'),
          onclick: (e) => {
            e.stopPropagation();
            pick = c;
            C.setBlock(p.pair_id, c, w, !keeping);
            render();
          },
        }, [
          el('span', { class: 'arc-blk-w', text: C.say(w) }),
          el('span', { class: 'arc-blk-s',
                       text: keeping ? 'keep' : 'remove' }),
        ]);
      });

      return el('div', {
        class: 'arc-chrow' + (c === pick ? ' on' : ''),
        'data-csc': String(c),
      }, [
        el('button', {
          class: 'arc-ch-name',
          title: gone.length
            ? 'CSC' + c + ': ' + gone.length + ' of ' + NW + ' blocks will be '
              + 'removed. Click to keep the whole channel.'
            : 'CSC' + c + ': every block is going into the analysis. '
              + 'Click to remove the whole channel.',
          onclick: () => {
            pick = c;
            C.setKept(p.pair_id, c, gone.length > 0, view);
            render();
          },
        }, [
          el('strong', { text: 'CSC' + c }),
          el('span', { class: 'arc-ch-g',
                       text: gone.length ? gone.length + ' of ' + N + ' removed'
                                         : 'all ' + NW + ' kept' }),
        ]),
        el('div', { class: 'arc-blks arc-blks-' + N }, blocks),
      ]);
    });

    const kids = [
      el('div', { class: 'section-label',
                  text: (view === 'transition' ? 'Transition blocks · '
                                                : 'Blocks · ')
                        + all.length + ' channel(s) touched the rail in this '
                        + 'pair' }),
      el('p', { class: 'hint',
        text: 'Each row is one channel and each block is one '
              + (view === 'transition'
                 ? 'transition window of this cue pair — a short span around '
                   + 'cue 1 starting, cue 2 starting, or cue 2 ending'
                 : 'window of this cue pair')
              + '. Click a block to keep it or remove it; click the channel '
              + 'name for all ' + NW + '. Anything marked remove is left out '
              + 'of the connectivity analysis.' }),
      el('div', { class: 'arc-chrows' }, rows),
    ];
    /* A flagged channel the pane is not drawing has no stretch on screen,
       which reads as nothing being wrong with it. Said plainly instead. */
    if (missing.length) {
      kids.push(el('p', { class: 'hint',
        text: 'Not on screen: CSC ' + missing.join(', ')
              + '. This pane is not drawing ' + (missing.length === 1
                ? 'that channel' : 'those channels')
              + ' — tick ' + (missing.length === 1 ? 'it' : 'them')
              + ' in the channel list to see the stretches. The decision '
              + 'holds either way.' }));
    }
    return el('div', { class: 'arc-chan-box' }, kids);
  }

  /* mm:ss.mmm, the same way curation writes a candidate's time. Nobody
     scrubbing a recording thinks in 1483.2 seconds. */
  function clock(t) {
    const m = Math.floor(t / 60);
    const s = t - m * 60;
    return m + ':' + (s < 10 ? '0' : '') + s.toFixed(3);
  }

  function spanList(p) {
    if (pick == null) {
      return el('p', { class: 'hint arc-nothing',
        text: 'Pick a channel to see the saturated stretches on it, and to '
              + 'dismiss, widen or redraw any of them.' });
    }
    const C = BARRY.arc.clean;
    const spans = C.spans(p.pair_id, pick);
    /* Named by the windows of the view on screen: a stretch that sits in
       the baseline in the state view sits in "cue 1 onset", or in no
       transition window at all, in the other. */
    const wins = windowsView(p);
    const winOf = (s) => {
      const hit = wins.find(([, a, b]) => s.b > a && s.a < b);
      return hit ? C.say(hit[0])
                 : (view === 'transition' ? 'outside the transition windows'
                                          : 'outside the windows');
    };

    const rows = spans.map((s, i) => el('div', {
      class: 'arc-span' + (s.hand ? ' hand' : '')
             + (edit && edit.i === i ? ' editing' : ''),
    }, [
      el('span', { class: 'num', text: clock(s.a) + ' → ' + clock(s.b) }),
      el('span', { class: 'arc-span-w', text: winOf(s) }),
      el('span', { class: 'num',
                   text: Math.round((s.b - s.a) * 1000) + ' ms' }),
      s.hand ? el('span', { class: 'flagchip', text: 'by hand' }) : null,
      el('div', { class: 'spacer' }),
      el('button', { class: 'mini', text: 'Not clipping',
                     title: 'Take this stretch off the channel. If it was '
                            + 'the only one in its window, the window '
                            + 'stops counting as lost.',
                     onclick: () => dismissSpan(i) }),
      el('button', { class: 'mini', text: 'Wider',
                     title: 'Grow it by a quarter of its length each side, '
                            + 'within the four windows — for saturation '
                            + 'that runs past what was detected.',
                     onclick: () => widenSpan(i) }),
      el('button', { class: 'mini', text: 'Drag it',
                     title: 'Set this stretch by dragging its edges on the '
                            + 'traces, then confirm.',
                     onclick: () => armEdit(i) }),
    ].filter(Boolean)));

    const acts = [];
    if (edit) {
      acts.push(el('span', { class: 'hint',
        text: edit.a == null
          ? 'Drag across the traces to draw the stretch you want excluded '
            + 'on CSC' + edit.csc + '.'
          : 'Drag either edge on the traces to move it. '
            + clock(edit.a) + ' → ' + clock(edit.b) + '  ·  '
            + Math.round((edit.b - edit.a) * 1000) + ' ms' }));
      acts.push(el('div', { class: 'spacer' }));
      acts.push(el('button', { class: 'btn ghost sm', text: 'Cancel',
        title: 'Leave the stretches as they are  (esc)',
        onclick: () => { edit = null; render(); } }));
      /* The one primary on this panel, and it is only here while there is
         something to confirm. */
      acts.push(el('button', {
        class: 'btn sm', text: 'Use this stretch',
        disabled: (edit.a != null && edit.b > edit.a) ? null : 'disabled',
        title: 'Take this as the stretch to exclude on CSC' + edit.csc
               + '  (enter)',
        onclick: commitEdit,
      }));
    } else {
      if (C.wasEdited(p.pair_id, pick)) {
        acts.push(el('button', { class: 'mini',
          text: 'Put back what was measured',
          title: 'Throw away the edits on CSC' + pick + ' and go back to '
                 + 'the stretches the clipping read found.',
          onclick: restoreSpans }));
      }
      acts.push(el('div', { class: 'spacer' }));
      acts.push(el('button', { class: 'mini', text: 'Draw a stretch',
        title: 'Drag one onto CSC' + pick + ' on the traces — for '
               + 'saturation the read did not find.',
        onclick: () => armEdit(-1) }));
    }

    return el('div', { class: 'arc-spans' }, [
      el('div', { class: 'section-label',
                  text: 'CSC' + pick + ' · ' + spans.length
                        + ' saturated stretch'
                        + (spans.length === 1 ? '' : 'es') }),
      spans.length
        ? el('div', { class: 'arc-span-rows' }, rows)
        : el('p', { class: 'hint',
                    text: 'None left on this channel — every stretch has '
                          + 'been dismissed, so it lost no window and goes '
                          + 'into the analysis.' }),
      el('div', { class: 'arc-span-acts' }, acts),
    ]);
  }

  /* ---------------- drawing on the traces ----------------

     Called from the pane paint loop with the plot's own geometry, the same
     way curation and Braces are. Everything is drawn in TIME and converted
     here, so a zoom or a scroll needs no bookkeeping. */
  function draw(ctx, s, win, padL, plotW, padTop, plotH, P) {
    if (!kind || !read || !s || s.id !== (sess && sess.id)) return;
    const t0 = win.t0, t1 = win.t1;
    if (!(t1 > t0)) return;
    const X = (t) => padL + ((t - t0) / (t1 - t0)) * plotW;

    ctx.save();

    // The analysis windows of the pair in view -- the four state windows,
    // or in Clean's transition view the three boundary windows.
    const p = now();
    if (p) {
      const shades = { pre: 0.05, cue1: 0.13, cue2: 0.13, post: 0.05,
                       onset: 0.13, switch: 0.13, offset: 0.13 };
      for (const [name, a, b] of windowsView(p)) {
        if (b < t0 || a > t1) continue;
        const xa = Math.max(padL, X(a)), xb = Math.min(padL + plotW, X(b));
        if (xb <= xa) continue;
        ctx.fillStyle = BARRY.token('--mode');
        ctx.globalAlpha = shades[name];
        ctx.fillRect(xa, padTop, xb - xa, plotH);
        ctx.globalAlpha = 1;
        // The boundary itself, which is what the analysis cuts on.
        ctx.strokeStyle = BARRY.token('--mode');
        ctx.lineWidth = name === 'pre' ? 1 : 1.5;
        ctx.beginPath();
        ctx.moveTo(xa, padTop); ctx.lineTo(xa, padTop + plotH);
        ctx.stroke();
        if (xb - xa > 34) {
          ctx.fillStyle = BARRY.token('--mode');
          ctx.globalAlpha = 0.85;
          ctx.font = '9px ui-monospace, monospace';
          ctx.fillText(name, xa + 3, padTop + 10);
          ctx.globalAlpha = 1;
        }
      }
    }

    /* Every pulse in view, dropped ones included. Confirm is the mode for
       "is this right", and a drawing that showed only the pulses that
       survived would be showing its own answer back. */
    for (const e of (read.events || [])) {
      if (e.t < t0 || e.t > t1) continue;
      const x = X(e.t);
      const kept = e.known && !e.is_mirror && !e.debounced;
      ctx.strokeStyle = !e.known ? BARRY.token('--warn')
        : kept ? BARRY.token('--ok') : BARRY.token('--text-3');
      ctx.globalAlpha = kept ? 0.9 : 0.35;
      ctx.setLineDash(kept ? [] : [2, 3]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, padTop); ctx.lineTo(x, padTop + plotH);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
    }

    /* Clean: the saturated stretches, on the rows that saturated. Drawn
       per channel rather than across the pane, because "CSC17 was at the
       rail here" and "the recording was bad here" are different claims and
       only the first one is true.

       COLOURED BY WHAT WILL HAPPEN, not by what was measured. Red is a
       channel on its way out of the analysis, green is one somebody has
       kept, and a channel that only grazed the rail is neither -- it was
       never going to be dropped, so painting it either colour would claim
       a decision nobody made. The same three states as the buttons on the
       panel, so the row and its chip cannot disagree. */
    if (kind === 'clean' && p) {
      const C = BARRY.arc.clean;
      const bad = clipOfPair(p.pair_id);
      const series = (win.series || []);
      if (bad && series.length) {
        const rowH = plotH / series.length;
        series.forEach((ser, i) => {
          const csc = Number(ser.number);
          const got = bad[String(csc)] || bad[csc];
          if (!got) return;
          const y = padTop + i * rowH;
          const lost = C.lost(p.pair_id, csc, view);
          const drops = lost.length > 0 && !C.isKept(p.pair_id, csc, view);
          const col = drops ? BARRY.token('--err')
            : lost.length ? BARRY.token('--ok') : BARRY.token('--text-3');

          for (const sp of C.spans(p.pair_id, csc)) {
            if (sp.b < t0 || sp.a > t1) continue;
            const xa = Math.max(padL, X(sp.a));
            const xb = Math.min(padL + plotW, X(sp.b));
            ctx.fillStyle = col;
            ctx.globalAlpha = drops ? 0.3 : lost.length ? 0.2 : 0.12;
            ctx.fillRect(xa, y, Math.max(1, xb - xa), rowH);
            ctx.globalAlpha = 1;
            /* A stretch somebody drew or widened is outlined, so the
               measurement and the judgement are told apart on the canvas
               the same way they are kept apart in the bank. */
            if (sp.hand) {
              ctx.strokeStyle = col;
              ctx.globalAlpha = 0.9;
              ctx.lineWidth = 1;
              ctx.setLineDash([3, 2]);
              ctx.strokeRect(xa + 0.5, y + 0.5,
                             Math.max(1, xb - xa) - 1, rowH - 1);
              ctx.setLineDash([]);
              ctx.globalAlpha = 1;
            }
          }

          // The row's own word, so the channel's fate is readable without
          // going back to the panel for it.
          ctx.fillStyle = col;
          ctx.globalAlpha = 0.9;
          ctx.font = '9px ui-monospace, monospace';
          const of = C.names(view).length;
          const atT = view === 'transition' ? ' at the transitions' : '';
          ctx.fillText(drops ? C.grade(lost.length, of) + atT
                               + ' — will be removed'
                       : lost.length ? C.grade(lost.length, of) + atT
                                       + ' — kept'
                       : 'grazed the rail — kept',
                       padL + 4, y + 9);
          ctx.globalAlpha = 1;

          // The row being edited, framed in the mode's colour.
          if (csc === pick) {
            ctx.strokeStyle = BARRY.token('--mode');
            ctx.globalAlpha = 0.8;
            ctx.lineWidth = 1;
            ctx.strokeRect(padL + 0.5, y + 0.5, plotW - 1, rowH - 1);
            ctx.globalAlpha = 1;
          }
        });
      }

      /* The stretch being dragged, over everything. On its own channel's
         row where the pane is drawing it, and across the whole plot where
         it is not -- a handle you cannot see is a drag you cannot finish,
         and an unticked channel is the commonest way to get there. */
      if (edit && edit.a != null) {
        const i = series.findIndex((ser) => Number(ser.number) === edit.csc);
        const rowH = series.length ? plotH / series.length : plotH;
        const y = i >= 0 ? padTop + i * rowH : padTop;
        const h = i >= 0 ? rowH : plotH;
        const xa = Math.max(padL, X(Math.min(edit.a, edit.b)));
        const xb = Math.min(padL + plotW, X(Math.max(edit.a, edit.b)));
        ctx.fillStyle = BARRY.token('--accent');
        ctx.globalAlpha = 0.25;
        ctx.fillRect(xa, y, Math.max(1, xb - xa), h);
        ctx.globalAlpha = 1;
        ctx.strokeStyle = BARRY.token('--accent');
        ctx.lineWidth = 2;
        for (const x of [xa, xb]) {
          ctx.beginPath();
          ctx.moveTo(Math.round(x) + 0.5, y);
          ctx.lineTo(Math.round(x) + 0.5, y + h);
          ctx.stroke();
          // A knob on each edge, so it reads as something to take hold of.
          ctx.fillStyle = BARRY.token('--accent');
          ctx.fillRect(Math.round(x) - 2.5, y + h / 2 - 5, 5, 10);
        }
      }
    }

    ctx.restore();
  }

  return {
    enter,
    exit,
    draw,
    goTo,
    /* Toggling invert reopens the recording and replaces the session
       object. The panel is repainted with it, because which channels the
       pane draws has just changed and the panel says so out loud. */
    rebind: (s) => { sess = s; if (kind) render(); },
    get active() { return !!kind; },
    get kind() { return kind; },
    get state() {
      if (!kind) return null;
      const p = now();
      return {
        kind, gid: read && read.gid, pair: at,
        channel: pick,
        view: kind === 'clean' ? view : 'state',
        /* Both kinds, keyed by window, which is what the bank is sent. */
        excluded: (kind === 'clean' && p)
          ? BARRY.arc.clean.excluded(p.pair_id, 'all') : [],
      };
    },
    get view() { return view; },
    get regions() { return regs; },
    /* For web/_dev: the decisions as the panel has them, without reaching
       into a closure or reading them back off the DOM. A harness that
       re-derives what it is checking checks nothing. */
    _pick: (csc) => { pick = csc == null ? null : Number(csc); render(); },
    _decide: (csc, keep) => decide(csc, keep),
    _view: (v) => setBlockView(v),
  };
})();

/* The two named doors onto it. Separate objects because a mode is entered
   by name from the ToolKit and from the palette, and `arcmode.enter(
   'clean', ...)` is not something a caller should have to know. */
BARRY.arcconfirm = {
  enter: (gid, reading) => BARRY.arcmode.enter('confirm', gid, reading),
  exit: () => BARRY.arcmode.exit(),
  rebind: (s) => BARRY.arcmode.rebind(s),
  get active() {
    return BARRY.arcmode.active && BARRY.arcmode.kind === 'confirm';
  },
  get state() { return BARRY.arcmode.state; },
};

BARRY.arcclean = {
  /* `at` is which pair to land on. The pair table's "N dropped" chip opens
     the mode on the pair it is about, because a row that names a problem
     and then opens on a different one is a row that has to be followed by
     sixteen presses of the arrow key. */
  enter: (gid, reading, clipping, at, view) =>
    BARRY.arcmode.enter('clean', gid, reading, clipping, at, view),
  exit: () => BARRY.arcmode.exit(),
  rebind: (s) => BARRY.arcmode.rebind(s),
  get active() {
    return BARRY.arcmode.active && BARRY.arcmode.kind === 'clean';
  },
  get state() { return BARRY.arcmode.state; },
};

window.barryArcMode = BARRY.arcmode;

/* --------------------------------------------------------------------------
   Coupling -- the Xplorefinder mode, wired now and closed.

   The five things a mode has to expose are the easiest part of this app to
   half-do: `enter` has to put the other modes out first, `active` has to be
   a getter because calling it throws, `rebind` exists because reopening a
   recording replaces the session object, and `state` is what a pop-out or a
   deep link reads. A stub that answers all five correctly and refuses to
   open proves the wiring is connected, which is worth more now than after
   the mode is written and the failure is tangled up in its own code.

   `enter` returns false rather than throwing, which is the contract: false
   means "did not enter", and a caller that checks it behaves correctly
   today and will behave correctly when this opens for real.
   -------------------------------------------------------------------------- */
BARRY.coupling = (function () {
  const step = BARRY.arc.step('coupling');

  function enter(gid) {
    toast(step.name + ' is not built yet. ' + step.phase + ': '
          + step.needs, 'warn');
    BARRY.activity.log('arc.coupling.refused', { gid: gid || null });
    return false;
  }

  function exit() {
    /* Nothing to undo -- `enter` never took anything. Kept because the way
       out of a mode must exist whether or not the way in did: the Leave
       button binds to this, and a button wired to nothing is how a mode
       becomes one you cannot get out of. */
  }

  return {
    enter,
    exit,
    rebind: function () {},
    draw: function () {},
    get active() { return false; },
    get state() { return null; },
  };
})();

/* `BARRY` is declared with `const`, so it is not a property of `window` and
   a pop-out or an iframe reaching for `BARRY.arc` finds undefined. The
   modules that are opened that way hang themselves here as well; this one
   follows, so a harness driving the app from outside can find it. */
window.barryArc = BARRY.arc;

// One mode at a time, kept by the registry in core.js.
BARRY.modes.register('arcmode', BARRY.arcmode);
