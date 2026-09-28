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
      built: false,
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
      built: false,
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

  /* The four windows of a pair, named. The same boundaries the backend
     measures clipping in, so what is drawn, what was measured and what is
     decided here cannot drift apart. */
  function windowsOf(p) {
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

  function clipOf(pairId) {
    return ((clip && clip.by_pair) || {})[String(pairId)] || null;
  }

  /* One channel's saturated stretches as they now stand: the measurement,
     or what somebody has made of it.

     `hand` marks a stretch that was dragged or widened. It is what lets a
     widened stretch claim a window the measurement did not, without a
     merely-trimmed one doing the same by accident -- see `lostOf`. */
  function spansOf(pairId, csc) {
    const mine = (spans_[String(pairId)] || {})[String(csc)];
    if (mine) return mine;
    const d = (clipOf(pairId) || {})[String(csc)];
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
  function lostOf(pairId, csc) {
    const d = (clipOf(pairId) || {})[String(csc)];
    if (!d) return [];
    const was = d.windows || [];
    const p = pairById(pairId);
    if (!editedSpans(pairId, csc) || !p) return was.slice();
    const live = spansOf(pairId, csc);
    return windowsOf(p).filter(([name, a, b]) => live.some(
      (s) => s.b > a && s.a < b && (s.hand || was.indexOf(name) >= 0)))
      .map((w) => w[0]);
  }

  /* The same scale as spark.loss_grade, so the word on screen and the word
     in the bank are one word. */
  function gradeOf(n) {
    if (n <= 0) return 'clean';
    if (n === 1) return 'partial event loss';
    if (n >= 4) return 'event lost';
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
  function flaggedOf(pairId) {
    const bad = clipOf(pairId);
    if (!bad) return [];
    return Object.keys(bad).map(Number)
      .filter((c) => lostOf(pairId, c).length > 0)
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
  const WINDOW_SAY = { pre: 'baseline', cue1: 'cue 1', cue2: 'cue 2',
                       post: 'after cue 2' };

  function keptWindows(pairId, csc) {
    return ((kept[String(pairId)] || {})[String(csc)]) || [];
  }

  function droppedWindows(pairId, csc) {
    return ((dropped[String(pairId)] || {})[String(csc)]) || [];
  }

  /* Is this one block going into the analysis? */
  function blockKept(pairId, csc, wname) {
    if (droppedWindows(pairId, csc).indexOf(wname) >= 0) return false;
    if (keptWindows(pairId, csc).indexOf(wname) >= 0) return true;
    return lostOf(pairId, csc).indexOf(wname) < 0;
  }

  function setBlock(pairId, csc, wname, keep) {
    const pid = String(pairId), key = String(csc);
    const wasLost = lostOf(pairId, csc).indexOf(wname) >= 0;
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

  /* Every block of every flagged channel, in one gesture. */
  function setAllBlocks(pairId, csc, keep) {
    for (const w of WINDOWS_4) setBlock(pairId, csc, w, keep);
  }

  /* `excluded` is never written from outside this function. One place
     decides it, so the list the bank is handed cannot disagree with the
     list on screen -- they are the same list read twice.
     
     Keyed by WINDOW now, which is the shape the bank and the analysis both
     take: {"pre": [17, 22], "cue1": [17]}. */
  function recompute(pairId) {
    const pid = String(pairId);
    const out = {};
    for (const c of chansOf(pairId)) {
      for (const w of WINDOWS_4) {
        if (blockKept(pid, c, w)) continue;
        (out[w] = out[w] || []).push(c);
      }
    }
    for (const w of Object.keys(out)) out[w].sort((a, b) => a - b);
    if (Object.keys(out).length) excluded[pid] = out;
    else delete excluded[pid];
  }

  /* Every channel with a row in the measurement, flagged or not -- a block
     nobody flagged is still a block somebody may want to drop. */
  function chansOf(pairId) {
    const bad = clipOf(pairId);
    return bad ? Object.keys(bad).map(Number).sort((a, b) => a - b) : [];
  }

  function recomputeAll() {
    for (const p of (reading && reading.pairs) || []) recompute(p.pair_id);
  }

  /* Keeping or dropping a whole channel, which is every one of its four
     blocks at once. The blocks are the model; this is the shortcut for
     somebody who has decided about the channel rather than about a
     window, and it is what the keyboard and the keep-all button use. */
  function setKept(pairId, csc, keep) {
    setAllBlocks(pairId, csc, keep);
  }

  /* A channel is "kept" when nothing about it is being dropped. */
  function channelKept(pairId, csc) {
    return WINDOWS_4.every((w) => blockKept(pairId, csc, w));
  }

  /* The blocks of this channel that will not go into the analysis. */
  function goneOf(pairId, csc) {
    return WINDOWS_4.filter((w) => !blockKept(pairId, csc, w));
  }

  /* Channels with at least one block going. */
  function droppingOf(pairId) {
    return chansOf(pairId).filter((c) => goneOf(pairId, c).length > 0);
  }

  /* Channels the measurement flagged that are being kept anyway. */
  function overruledOf(pairId) {
    return flaggedOf(pairId).filter((c) => channelKept(pairId, c));
  }

  /* How much of this recording the analysis is about to lose, counted the
     two ways somebody asks about it: how many channel-events go, and how
     many distinct channels are involved at all. */
  function dropTally() {
    const chans = new Set();
    let blocks = 0;
    const pairs = new Set();
    for (const pid in excluded) {
      for (const w in excluded[pid]) {
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
    host.appendChild(el('div', { class: 'arc-spark' }, [
      el('div', { class: 'arc-pick', id: 'arcPick' }),
      el('div', { class: 'arc-read', id: 'arcRead' }),
    ]));
    if (rows === null) {
      const pick = document.getElementById('arcPick');
      BARRY.skeleton.into(pick, 'row', 8);
      loadRows().then(() => {
        if (BARRY.views.toolkit.tool() === 'spark') {
          renderPick(); renderRead();
        }
      }).catch((e) => {
        reportClientError('arc.spark', e.message, e.stack);
        const p = document.getElementById('arcPick');
        if (p) {
          p.innerHTML = '';
          p.appendChild(el('p', { class: 'hint',
                                  text: 'Could not read the registry: '
                                        + e.message }));
        }
      });
      return;
    }
    renderPick();
    renderRead();
  }

  const PHASES = [
    ['Precon', 'Preconditioning'],
    ['Con', 'Conditioning'],
    ['Test', 'Test'],
  ];

  function renderPick() {
    const host = document.getElementById('arcPick');
    if (!host) return;
    host.innerHTML = '';

    host.appendChild(BARRY.ui.field({
      label: 'Which sessions',
      control: el('div', { class: 'seg' }, PHASES.map(([id, name]) =>
        el('button', {
          /* `.seg button.active` is the house rule -- the segmented control
             marks its chosen one `active`, not `on`. */
          class: q.phase === id ? 'active' : '',
          text: name,
          onclick: async () => {
            if (q.phase === id) return;
            q.phase = id; q.gid = null; reading = null; rows = null;
            renderPick();
            await loadRows();
            if (BARRY.views.toolkit.tool() === 'spark') {
              renderPick(); renderRead();
            }
          },
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
    }));

    if (rows === null) { BARRY.skeleton.into(host, 'row', 8); return; }
    if (!rows.length) {
      host.appendChild(el('div', { class: 'empty-state' }, [
        el('p', { text: 'No DEWEY recordings of that kind are in the '
                        + 'registry. Scan the share in Sessions first.' }),
      ]));
      return;
    }

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
    excluded = {}; kept = {}; spans_ = {};
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

  function clipCard(s) {
    if (!s.n_pairs) return null;
    if (!clip) {
      return el('div', { class: 'arc-clipbar' }, [
        el('span', { class: 'hint',
          text: 'Nothing has checked these windows for clipping yet. It '
                + 'reads all ' + (reading.summary.n_channels || '')
                + ' channels across four windows per pair — about ten '
                + 'seconds.' }),
        el('div', { class: 'spacer' }),
        el('button', {
          class: 'btn ghost sm' + (clipBusy ? ' off' : ''),
          disabled: clipBusy ? 'disabled' : null,
          text: clipBusy ? 'Reading…' : 'Check for clipping',
          onclick: doClip,
        }),
      ]);
    }

    const chans = clip.channels || [];
    if (!chans.length) {
      return el('p', { class: 'hint',
        text: 'No channel saturated in any of these windows.' });
    }
    const rows = chans.slice(0, 12).map((c) => el('div', {
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
    return el('div', { class: 'arc-clip' }, [
      el('div', { class: 'section-label',
                  text: 'Clipping · ' + chans.length + ' channel(s)' }),
      /* The rule, stated where the numbers are. A grade nobody can check
         is a grade nobody should act on. */
      el('p', { class: 'hint',
        text: 'A window counts as lost where the amplifier sat within '
              + Math.round((1 - (clip.fraction || 0.995)) * 1000) / 10
              + '% of its rail for ' + (clip.min_run || 16)
              + ' samples or more. One window of the four is a partial '
              + 'loss, two or three is major, all four is the event gone '
              + 'on that channel.' }),
      /* The consequence, beside the measurement rather than three clicks
         away from it. This is the sentence the whole clipping check is
         for, and until it was written here the only place the exclusion
         appeared at all was a chip in the pair table reading "56 clipped"
         -- a count, not a claim about what happens next. */
      dropSay(),
      el('div', { class: 'arc-clip-rows' }, rows),
      chans.length > 12
        ? el('p', { class: 'hint',
                    text: chans.length - 12 + ' more, worst first.' })
        : null,
    ].filter(Boolean));
  }

  /* What the exclusion currently comes to, in one sentence, in the words
     the analysis uses. Shown wherever somebody is about to act on it: in
     the clipping card, and again on the bar they file from. */
  function dropSay() {
    const t = dropTally();
    if (!t.n) {
      return el('p', { class: 'arc-drop-say none',
        text: 'Nothing is excluded: every channel goes into the '
              + 'connectivity analysis on every pair.' });
    }
    return el('div', { class: 'arc-drop-say' }, [
      el('strong', { text: t.chans + ' channel' + (t.chans === 1 ? '' : 's') }),
      el('span', { text: 'will be excluded from the connectivity analysis, '
                         + 'across ' + t.pairs + ' of the '
                         + ((reading.pairs || []).length) + ' cue pairs — '
                         + t.n + ' channel-event' + (t.n === 1 ? '' : 's')
                         + ' in all. A channel is excluded only on the '
                         + 'pairs where it lost a window, not on the '
                         + 'recording as a whole.' }),
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

  async function doClip() {
    if (clipBusy || !q.gid) return;
    clipBusy = true;
    renderRead();
    const asked = q.gid;
    try {
      const got = await apiPost('/api/arc/spark/'
                                + encodeURIComponent(q.gid) + '/clipping', {});
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
    if (!going.length && !overruled.length) {
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
    ].filter(Boolean));
  }

  /* Clean, landed on a particular pair. `null` means the first one, which
     is what the bar button has always done. */
  function openClean(pairId) {
    const list = (reading && reading.pairs) || [];
    const i = pairId == null ? 0
      : list.findIndex((x) => String(x.pair_id) === String(pairId));
    BARRY.arcclean.enter(q.gid, reading, clip, i < 0 ? 0 : i);
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
                                + '/bank', { excluded: excluded });
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
  const cq = { gid: null, pair: 1, method: 'amp_cc', window: 'cue1' };
  let cRows = null;       // recordings, with whether they are banked
  let cPairs = null;      // the banked pairs of the chosen recording
  let cRun = null;        // the last analysis
  let cBusy = false;
  let cSaved = null;

  const METHODS = [
    ['coherence', 'Coherence', 'magnitude-squared, read at 8 Hz'],
    ['raw_cc', 'Raw cross-correlation', 'peak |r| within \u00b1500 ms'],
    ['amp_cc', 'Amplitude cross-correlation',
     'theta envelope, peak |r| within \u00b1500 ms'],
  ];
  const WINDOW_NAMES = {
    pre: 'baseline', cue1: 'cue 1', cue2: 'cue 2', post: 'after cue 2',
  };

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
    renderCPick(); renderCMain();
    try {
      cPairs = await api('/api/arc/coupling/' + encodeURIComponent(gid));
    } catch (e) {
      cPairs = { error: e.message };
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
      cPairBar(),
      p ? cPairNote(p) : null,
      cRunBar(),
      cResult(),
    ].filter(Boolean)));
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
    return el('div', { class: 'head-actions arc-cp-bar' }, [
      el('span', { class: 'hint',
        text: 'Four windows \u00d7 66 region pairs \u00d7 three methods, '
              + 'about five seconds. Mains is notched first \u2014 there is '
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
        disabled: cBusy ? 'disabled' : null,
        text: cBusy ? 'Running\u2026' : (cRun ? 'Run again' : 'Run the analysis'),
        onclick: doCouplingRun,
      }),
    ].filter(Boolean));
  }

  async function doCouplingRun() {
    if (cBusy || !cq.gid) return;
    cBusy = true; cSaved = null; renderCMain();
    const asked = cq.gid + ':' + cq.pair;
    try {
      const got = await apiPost(
        '/api/arc/coupling/' + encodeURIComponent(cq.gid) + '/run',
        { pair_id: cq.pair });
      if (cq.gid + ':' + cq.pair === asked) cRun = got;
    } catch (e) {
      toast('That did not run: ' + e.message, 'err', 8000);
      reportClientError('arc.coupling.run', e.message, e.stack);
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
      return loader('Reading four windows',
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

    return el('div', {}, [
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

  function matrixGrid(win) {
    const order = cRun.region_order || [];
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
    for (const b of order) {
      cells.push(el('div', { class: 'arc-mx-head col',
                             title: b, text: shortRegion(b) }));
    }
    for (const a of order) {
      cells.push(el('div', { class: 'arc-mx-head row',
                             title: a, text: shortRegion(a) }));
      for (const b of order) {
        if (a === b) { cells.push(el('div', { class: 'arc-mx-cell self' }));
                       continue; }
        const s = summaryOf(by[a + '\u0000' + b], cq.method);
        if (!s) {
          cells.push(el('div', { class: 'arc-mx-cell none',
                                 title: a + ' \u00d7 ' + b
                                        + ' \u2014 not computed' }));
          continue;
        }
        const v = Number(s.value);
        cells.push(el('div', {
          class: 'arc-mx-cell',
          style: 'background:' + cellColour(v, diverging),
          title: a + ' \u00d7 ' + b + '\n' + s.what + ': ' + v.toFixed(4)
                 + (s.x != null ? '\nat ' + s.x + ' ' + (s.x_unit || '') : ''),
          text: v.toFixed(2).replace('0.', '.'),
        }));
      }
    }
    return el('div', {
      class: 'arc-mx',
      style: 'grid-template-columns: 58px repeat(' + order.length
             + ', minmax(0, 1fr));',
    }, cells);
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
    steps: () => STEPS.map((s) => Object.assign({}, s)),
    step: stepOf,
    /* ----------------------------------------------------------------
       Clean's way in.

       The mode paints the decisions and this panel banks them, so the two
       have to be reading one set of structures. A mode holding its own
       copy of the exclusion list is a mode whose work reaches the bank
       only by coincidence -- and the coincidence would hold right up
       until somebody left the mode and came back.

       Everything here is by CSC NUMBER, never by row index: the pane's
       row list changes the moment somebody toggles even-only, and an
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
      excluded: exclOf,
      isKept: (pid, csc) => channelKept(pid, csc),
      setKept: (pid, csc, keep) => { setKept(pid, csc, keep); afterDecision(); },
      /* The block, which is the unit a decision is actually made in. */
      blockKept: (pid, csc, w) => blockKept(pid, csc, w),
      setBlock: (pid, csc, w, keep) => {
        setBlock(pid, csc, w, keep); afterDecision();
      },
      gone: goneOf,
      dropping: droppingOf,
      overruled: overruledOf,
      names: () => WINDOWS_4.slice(),
      say: (w) => WINDOW_SAY[w] || w,
      keepAll: (pid) => {
        for (const c of chansOf(pid)) setKept(pid, c, true);
        afterDecision();
      },
      dropAll: (pid) => {
        for (const c of flaggedOf(pid)) setKept(pid, c, false);
        afterDecision();
      },
      tally: dropTally,
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

  async function enter(which, gid, reading, clipping, atPair) {
    /* One mode at a time, and this is the function responsible for it. */
    if (BARRY.curate && BARRY.curate.active) BARRY.curate.exit();
    if (BARRY.strata && BARRY.strata.active) BARRY.strata.exit();
    if (BARRY.cfc && BARRY.cfc.active) BARRY.cfc.exit();
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
    setMode(null);
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
    if (k === 'k' || k === 'K') { decide(pick, true); stop(e); return; }
    if (k === 'x' || k === 'X') { decide(pick, false); stop(e); return; }
    if (k === 'Enter') {
      if (edit) commitEdit(); else if (pick != null) toggle(pick);
      stop(e);
    }
  }

  function stop(e) { e.preventDefault(); e.stopPropagation(); }

  function clipOfPair(id) {
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
    const lost = BARRY.arc.clean.lost(p.pair_id, csc);
    if (!lost.length) {
      toast('CSC' + csc + ' did not lose a window of this pair, so it is '
            + 'already going into the analysis. Nothing to keep.',
            null, 5000);
      return;
    }
    BARRY.arc.clean.setKept(p.pair_id, csc, keep);
    pick = Number(csc);
    BARRY.activity.log('arc.clean.' + (keep ? 'keep' : 'drop'),
                       { pair: p.pair_id, csc: Number(csc),
                         windows: lost.length }, sess);
    render();
  }

  function toggle(csc) {
    const p = now();
    if (!p) return;
    decide(csc, !BARRY.arc.clean.isKept(p.pair_id, csc));
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
    const now_ = BARRY.arc.clean.lost(p.pair_id, csc).length;
    if (now_ === was) return;
    const dropped = now_ > 0 && !BARRY.arc.clean.isKept(p.pair_id, csc);
    toast('CSC' + csc + ' is now ' + BARRY.arc.clean.grade(now_)
          + (dropped ? ' — still excluded from this pair.'
                     : ' — it goes into the analysis.'),
          dropped ? 'warn' : 'ok', 6000);
  }

  function dismissSpan(i) {
    const p = now();
    if (!p || pick == null) return;
    const was = BARRY.arc.clean.lost(p.pair_id, pick).length;
    writeSpans(p, pick, liveSpans(p, pick).filter((_, k) => k !== i));
    BARRY.activity.log('arc.clean.span.drop',
                       { pair: p.pair_id, csc: pick }, sess);
    render();
    sayVerdict(p, pick, was);
  }

  function widenSpan(i) {
    const p = now();
    if (!p || pick == null) return;
    const was = BARRY.arc.clean.lost(p.pair_id, pick).length;
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
    const was = BARRY.arc.clean.lost(p.pair_id, pick).length;
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
    const was = BARRY.arc.clean.lost(p.pair_id, csc).length;
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
   * Read off the pane rather than off the recording: even-only and the
   * channel ticks both change it, and a flagged channel nobody can see is
   * worth saying out loud rather than leaving as a stretch that never
   * appears. Odd channels in particular -- an even-only pane holds none of
   * them, and every stretch on CSC17 would silently have nowhere to go. */
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
                   el('kbd', { text: 'x' }), el('span', { text: 'drop' }));
    }
    keyBits.push(el('kbd', { text: 'esc' }),
                 el('span', { text: edit ? 'call off the drag' : 'leave' }));
    bits.push(el('span', { class: 'arc-bar-keys' }, keyBits));
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
    return el('div', { class: 'arc-clean' }, [
      verdict(p),
      chanList(p),
      spanList(p),
    ].filter(Boolean));
  }

  /* The sentence this mode exists to make unmissable. Widest thing on the
     panel, in the colour of the outcome, and it names the channels rather
     than counting them -- "4 channels" is a number somebody has to go and
     look up, and the whole complaint was that the consequence was never
     stated where they were looking. */
  function verdict(p) {
    const C = BARRY.arc.clean;
    const drop = C.excluded(p.pair_id);
    const keep = C.kept(p.pair_id);
    const all = C.flagged(p.pair_id);
    const bits = [];

    if (drop.length) {
      bits.push(el('strong', { text: drop.length + ' channel'
                                     + (drop.length === 1 ? '' : 's') }));
      bits.push(el('span', { text: 'will be excluded from the connectivity '
                                   + 'analysis for this cue pair:' }));
      bits.push(el('span', { class: 'arc-verdict-who',
                             text: 'CSC ' + drop.join(', ') }));
    } else {
      bits.push(el('strong', { text: 'Nothing is excluded' }));
      bits.push(el('span', { text: 'for this cue pair — every channel goes '
                                   + 'into the connectivity analysis.' }));
    }
    if (keep.length) {
      bits.push(el('span', { class: 'arc-verdict-kept',
        text: keep.length + ' kept against the measurement: CSC '
              + keep.join(', ') }));
    }
    bits.push(el('div', { class: 'spacer' }));
    if (all.length || keep.length) {
      const keeping = !drop.length;
      bits.push(el('button', {
        class: 'btn ghost sm',
        text: keeping ? 'Drop them all again' : 'Keep all ' + all.length,
        title: keeping
          ? 'Put every flagged channel of this pair back to what the '
            + 'measurement says, which is that all of them are dropped.'
          : 'Overrule the measurement on every flagged channel of this '
            + 'pair, so none of them is dropped.',
        onclick: () => {
          if (keeping) C.dropAll(p.pair_id); else C.keepAll(p.pair_id);
          BARRY.activity.log('arc.clean.' + (keeping ? 'dropAll' : 'keepAll'),
                             { pair: p.pair_id, n: all.length }, sess);
          render();
        },
      }));
    }
    return el('div', { class: 'arc-verdict' + (drop.length ? '' : ' none') },
              bits);
  }

  function chanList(p) {
    const C = BARRY.arc.clean;
    const all = chansHere();
    if (!all.length) {
      return el('p', { class: 'hint arc-nothing',
        text: 'No channel went near its rail in any of this pair\u2019s four '
              + 'windows. Nothing to decide here \u2014 \u2192 for the next '
              + 'pair.' });
    }
    const shown = new Set(paneRows());
    const missing = [];
    const names = C.names();

    /* One row per channel, four blocks per row.
     *
     * The blocks ARE the decision. A cue pair is four windows and a
     * channel can be ruined in one and perfectly good in the other three,
     * which on this data is most of the data -- so deciding per channel
     * threw three quarters of a usable wire away with the quarter that
     * was bad. Clicking a block keeps or removes that block and nothing
     * else.
     *
     * Every block is clickable, including the ones the measurement was
     * happy with: "this one looks wrong to me" is a decision somebody is
     * entitled to make, and a block that cannot be clicked cannot record
     * it. */
    const rows = all.map((c) => {
      const lost = C.lost(p.pair_id, c);
      const gone = C.gone(p.pair_id, c);
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
          title: 'CSC' + c + ' \u00b7 ' + C.say(w)
                 + (wasLost ? ' \u2014 the amplifier saturated here'
                            : ' \u2014 nothing wrong measured here')
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
      }, [
        el('button', {
          class: 'arc-ch-name',
          title: gone.length
            ? 'CSC' + c + ': ' + gone.length + ' of four blocks will be '
              + 'removed. Click to keep the whole channel.'
            : 'CSC' + c + ': every block is going into the analysis. '
              + 'Click to remove the whole channel.',
          onclick: () => {
            pick = c;
            C.setKept(p.pair_id, c, gone.length > 0);
            render();
          },
        }, [
          el('strong', { text: 'CSC' + c }),
          el('span', { class: 'arc-ch-g',
                       text: gone.length ? gone.length + ' of 4 removed'
                                         : 'all four kept' }),
        ]),
        el('div', { class: 'arc-blks' }, blocks),
      ]);
    });

    const kids = [
      el('div', { class: 'section-label',
                  text: 'Blocks · ' + all.length + ' channel(s) touched '
                        + 'the rail in this pair' }),
      el('p', { class: 'hint',
        text: 'Each row is one channel and each block is one window of this '
              + 'cue pair. Click a block to keep it or remove it; click the '
              + 'channel name for all four. Anything marked remove is left '
              + 'out of the connectivity analysis.' }),
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
              + ' in the channel list, or turn even-only off, to see the '
              + 'stretches. The decision holds either way.' }));
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
    const wins = windowsOf(p);
    const winOf = (s) => (wins.find(([, a, b]) => s.b > a && s.a < b)
                          || ['outside the windows'])[0];

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

    // The four analysis windows of the pair in view.
    const p = now();
    if (p) {
      const shades = { pre: 0.05, cue1: 0.13, cue2: 0.13, post: 0.05 };
      for (const [name, a, b] of windowsOf(p)) {
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
          const lost = C.lost(p.pair_id, csc);
          const drops = lost.length > 0 && !C.isKept(p.pair_id, csc);
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
          ctx.fillText(drops ? C.grade(lost.length) + ' — will be removed'
                       : lost.length ? C.grade(lost.length) + ' — kept'
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
    /* Toggling even-only reopens the recording and replaces the session
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
        excluded: (kind === 'clean' && p)
          ? BARRY.arc.clean.excluded(p.pair_id) : [],
      };
    },
    /* For web/_dev: the decisions as the panel has them, without reaching
       into a closure or reading them back off the DOM. A harness that
       re-derives what it is checking checks nothing. */
    _pick: (csc) => { pick = csc == null ? null : Number(csc); render(); },
    _decide: (csc, keep) => decide(csc, keep),
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
  enter: (gid, reading, clipping, at) =>
    BARRY.arcmode.enter('clean', gid, reading, clipping, at),
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
