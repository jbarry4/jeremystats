/* ==========================================================================
   tourmodules.js -- What the tours actually say.

   Separate from tour.js on purpose: the engine knows how to point at things,
   this file knows what is worth pointing at. Adding a module means adding
   one object here and nothing else.

   A step is:
     { id, title, body, note,
       target,      CSS selector, or a function returning an element
       view,        switch to this section first
       before,      async setup to run before the step is shown
       wait,        selector or predicate to wait for after `before`
       required,    false = carry on even if `wait` never comes true
       action,      'click' = the step advances when the target is clicked
       doText,      what to say on a click step
       placement,   preferred side for the box
       pad }        extra room around the highlight

   Tone: say what the thing is for, not what it is called. "Which channels
   came out of the average" beats "the Channels control". Someone reading
   these has not yet learned the vocabulary the labels use.
   ========================================================================== */
'use strict';

(function () {
  const T = BARRY.tour;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /* A recording to demonstrate on: whichever one BARRY already knows about.
     Falls back to null, and the steps that need one are marked skippable, so
     the tour still runs on a fresh machine with nothing scanned. */
  let cachedPath;

  async function anyRecording() {
    if (cachedPath !== undefined) return cachedPath;
    cachedPath = null;
    try {
      const d = await api('/api/sessions');
      for (const rec of (d.sessions || [])) {
        const ps = rec.paths || [];
        if (ps.length) { cachedPath = ps[ps.length - 1]; break; }
      }
    } catch (e) { /* nothing stored yet -- the tour still runs */ }
    return cachedPath;
  }

  /* Open one in Xplorefinder if nothing is open yet, and hand back the
     session. Tours should never close what someone already had open. */
  async function ensureOpen() {
    const XF = BARRY.views.xplore.state;
    if (XF.active && XF.sessions[XF.active]) return XF.sessions[XF.active];
    const path = await anyRecording();
    if (!path) return null;
    return BARRY.views.xplore.open(path);
  }

  const hasPane = () => !!document.querySelector('.pane-canvas-host canvas');

  /* The strip's menu buttons are the target of several steps. */
  const stripMenu = (name) => () =>
    Array.from(document.querySelectorAll('.pane-ctl .ctl-menu'))
      .find((b) => b.textContent.startsWith(name)) || null;

  const railItem = (view) => '.nav-item[data-view="' + view + '"]';

  /* ======================================================================
     1. Getting started
     ====================================================================== */
  T.register({
    id: 'start',
    name: 'Getting started',
    blurb: 'The shape of the place: how to get around, and where your work '
         + 'goes.',
    steps: [
      {
        title: 'This is BARRY',
        body: 'A workbench for the lab’s recordings. It reads Neuralynx '
            + 'files straight off the drive, runs the pipeline, draws the '
            + 'figures, and writes down what it did so you can find your way '
            + 'back to it later.',
        note: 'Four minutes. Escape leaves at any point and nothing is lost.',
      },
      {
        title: 'Everything lives in the rail',
        body: 'Eleven sections, and the number on each one is the key that '
            + 'gets you there. ToolKit is T, because there are only ten '
            + 'digits.',
        target: '#rail .nav-group',
        placement: 'right',
      },
      {
        title: 'Or forget the rail entirely',
        body: 'Ctrl+K opens the command palette. It jumps to a section, opens '
            + 'a recording, runs any of the 420 scripts in the repo, or '
            + 'starts a deck. Type roughly what you mean — "cscconv" '
            + 'finds CSCconverter_LLready_pure.m.',
        target: '#rail .nav-group',
        placement: 'right',
        note: 'Press ? at any time for the full list of keys.',
      },
      {
        title: 'Start with a recording',
        body: 'Xplorefinder is where you look at data. Click it — or '
            + 'press 3.',
        target: railItem('xplore'),
        action: 'click',
        placement: 'right',
        doText: 'Click Xplorefinder.',
      },
      {
        title: 'Opening one',
        body: 'Drop a session folder here, or pick one BARRY has seen before. '
            + 'A folder of CSC*.ncs files is all it needs.',
        view: 'xplore',
        before: async () => { await ensureOpen(); },
        wait: hasPane,
        required: false,
        target: () => document.querySelector('.pane-canvas-host')
                   || document.querySelector('#xfDrop'),
        placement: 'top',
        note: 'BARRY has opened one for you, so the rest of the tour has '
            + 'something real to point at.',
      },
      {
        title: 'What you touch most',
        body: 'The start of the window, how wide it is, and the buttons that '
            + 'move and zoom it. Everything here changes what you are looking '
            + 'at, not what the data is.',
        view: 'xplore',
        wait: hasPane,
        required: false,
        target: '.pane-ctl',
        placement: 'bottom',
      },
      {
        title: 'And what you set once',
        body: 'The rest of the controls sit behind buttons that carry their '
            + 'own current value — so the strip still tells you the '
            + 'filter is 1–70 Hz without spending a strip’s worth '
            + 'of width saying so. Click one to open it.',
        view: 'xplore',
        wait: () => !!stripMenu('Filter')(),
        required: false,
        target: stripMenu('Filter'),
        action: 'click',
        placement: 'bottom',
        doText: 'Click Filter to see what is behind it.',
      },
      {
        title: 'Your work is written down',
        body: 'Every figure, every run, every filter change goes into '
            + 'GUI_logs as plain JSON — one file per record, so two '
            + 'people can work at once and git merges it without a fight. '
            + 'History is where you read it back.',
        target: railItem('history'),
        placement: 'right',
      },
      {
        title: 'Every recording gets a permanent name',
        body: 'The first time BARRY meets a recording it mints a global id '
            + 'for it and never changes it. Bad channels, layer labels and '
            + 'curated events hang off that id, so they follow the recording '
            + 'rather than the folder it happens to be sitting in \u2014 and '
            + 'they are the same on everybody\u2019s machine.',
        target: railItem('sessions'),
        placement: 'right',
        note: 'Sessions \u203a Everything BARRY knows is the list, with the '
            + 'id and every path each recording has been seen at.',
      },
      {
        title: 'And your output has one home',
        body: 'Everything BARRY saves lands in the Results folder inside the '
            + 'repo, cataloged automatically. Nothing is filed by hand, and '
            + 'nothing ends up in a downloads folder where nobody else can '
            + 'find it.',
        target: railItem('results'),
        placement: 'right',
      },
      {
        title: 'That is the shape of it',
        body: 'The other tours go deeper: reading a recording, finding '
            + 'events, making a figure that can be rebuilt, and telling the '
            + 'story with it.',
        note: 'The guide button at the bottom of the rail brings this menu '
            + 'back whenever you want it.',
        target: '#tourBtn',
        placement: 'right',
      },
    ],
  });

  /* ======================================================================
     2. Reading a recording
     ====================================================================== */
  T.register({
    id: 'reading',
    name: 'Reading a recording',
    blurb: 'Panels, filters, channels, and what the scale is actually '
         + 'telling you.',
    steps: [
      {
        title: 'One recording, several ways of looking at it',
        body: 'A pane can show stacked traces, a voltage raster, the current '
            + 'source density, the theta band, a spectrogram or a scalogram '
            + '— and video or the position track alongside them.',
        view: 'xplore',
        before: async () => { await ensureOpen(); },
        wait: hasPane,
        required: false,
        target: () => document.querySelector('.pane-head') || '.pane',
        placement: 'bottom',
      },
      {
        title: 'The window is shared, not the panel',
        body: 'View state lives on the recording, so two panes onto the same '
            + 'session — traces above, CSD below — move together '
            + 'for free. Link time extends that across different recordings, '
            + 'for baseline against CNO.',
        view: 'xplore',
        wait: hasPane,
        required: false,
        target: '.pane-ctl',
        placement: 'bottom',
      },
      {
        title: 'Filters, and what they cost',
        body: 'High-pass, low-pass and notch. BARRY filters by subtraction '
            + '— the high-pass is the signal minus its own baseline '
            + '— which is why it can redraw 32 channels of 30 kHz data '
            + 'as fast as you can drag.',
        view: 'xplore',
        wait: () => !!stripMenu('Filter')(),
        required: false,
        target: stripMenu('Filter'),
        placement: 'bottom',
        note: 'The button says the current band, so a figure never quietly '
            + 'comes out unfiltered.',
      },
      {
        title: 'Bad channels follow the recording',
        body: 'Mark one bad on the channel list and it stays marked — '
            + 'across sessions, across machines, and across a git pull, '
            + 'because BARRY matches recordings by mouse, session and header '
            + 'start time rather than by folder name.',
        view: 'xplore',
        wait: '.pane-chans',
        required: false,
        target: '.pane-chans',
        placement: 'right',
      },
      {
        title: 'The scale is a claim',
        body: 'By default each window is scaled to itself, which is useful '
            + 'for looking and misleading for comparing. Pin it and the '
            + 'number stops moving, so two windows can be held against each '
            + 'other honestly.',
        view: 'xplore',
        wait: '.scale-ctl',
        required: false,
        target: '.scale-ctl',
        placement: 'bottom',
      },
      {
        title: 'A spectrogram, and two different frequency ranges',
        body: 'f min and f max set the band the transform is computed over '
            + '— change them and the numbers change. The Show Hz range '
            + 'crops what is drawn out of what was already computed: the '
            + 'same analysis, a closer look. Worth keeping straight.',
        view: 'xplore',
        before: async () => {
          const XF = BARRY.views.xplore.state;
          if (XF.panes[0]) {
            XF.panes[0].panel = 'spectrogram';
            BARRY.views.xplore.onShow();
          }
          await sleep(600);
        },
        wait: () => !!stripMenu('Panel')(),
        required: false,
        target: stripMenu('Panel'),
        action: 'click',
        placement: 'bottom',
        doText: 'Open Panel — both ranges are in there.',
      },
      {
        title: 'The panes are yours to arrange',
        body: 'Drag the divider between them to give one more room; '
            + 'double-click it to even them up again. The button on a pane '
            + 'header fills the workspace with it, and the next one along '
            + 'goes properly full screen \u2014 the whole monitor, nothing '
            + 'else on it.',
        view: 'xplore',
        wait: hasPane,
        required: false,
        target: () => document.querySelector('.pane-head') || '.pane',
        placement: 'bottom',
        note: 'Shift-click the pop-out button to open a pane in its own '
            + 'window, already full screen.',
      },
      {
        title: 'And the frame can get out of the way',
        body: 'View lets you put away the channel list, the control strip, '
            + 'the pane headers and the tab bar \u2014 individually or all '
            + 'at once. Every pixel goes to the data. Nothing is lost; tick '
            + 'it back on in the same place.',
        view: 'xplore',
        wait: '#xfView',
        required: false,
        target: '#xfView',
        action: 'click',
        placement: 'bottom',
        doText: 'Open View and see what can be put away.',
      },
      {
        title: 'What the analysis actually ran on',
        body: 'Every computed panel states it in the corner: the window, the '
            + 'channel count, the filters, how many channels were excluded '
            + 'as bad, whether the trace was inverted. The analysis runs on '
            + 'what you can see, and says so.',
        view: 'xplore',
        wait: '.panel-input',
        required: false,
        target: '.panel-input',
        placement: 'right',
      },
    ],
  });

  /* ======================================================================
     3. Events and spikes
     ====================================================================== */
  T.register({
    id: 'events',
    name: 'Finding events',
    blurb: 'Marks on a trace: importing them, detecting them, and filing '
         + 'them where the next person will find them.',
    steps: [
      {
        title: 'Marks belong to a recording',
        body: 'Bookmarks you place, events imported from a file, spikes a '
            + 'detector found — all of them hang off the recording and '
            + 'come back when you reopen it.',
        view: 'xplore',
        before: async () => { await ensureOpen(); },
        wait: () => !!stripMenu('Marks')(),
        required: false,
        target: stripMenu('Marks'),
        placement: 'bottom',
      },
      {
        title: 'Bringing events in',
        body: 'Import asks where from: the Event Bank, or a file on this '
            + 'machine — .nev, .mat, a CSV, an Excel sheet. Either way '
            + 'you get a review step before anything lands on the trace.',
        view: 'xplore',
        wait: () => !!stripMenu('More')(),
        required: false,
        target: stripMenu('More'),
        action: 'click',
        placement: 'bottom',
        doText: 'Open More — Import and Export are in there.',
      },
      {
        title: 'Detecting them instead',
        body: 'The threshold detector works on what is on screen, in plain '
            + 'microvolts or in multiples of the noise floor. You get a draft '
            + 'to look at before it becomes a set — nothing is committed '
            + 'by accident.',
        view: 'xplore',
        wait: () => !!stripMenu('More')(),
        required: false,
        target: stripMenu('More'),
        placement: 'bottom',
        note: 'The detector is under More, beside the event actions.',
      },
      {
        title: 'And detected spikes become events',
        body: 'Committing a detector run puts its marks on the trace as '
            + 'events in their own class \u2014 so they can be named, '
            + 'colored, hidden, stepped through and exported like anything '
            + 'else. A set of ticks you cannot work with is not much use.',
        view: 'xplore',
        wait: () => !!stripMenu('More')(),
        required: false,
        target: stripMenu('More'),
        placement: 'bottom',
      },
      {
        title: 'The Event Bank',
        body: 'Where events go to be found again: filed by project, mouse, '
            + 'session and kind. Click it.',
        target: railItem('eventbank'),
        action: 'click',
        placement: 'right',
        doText: 'Click Event Bank.',
      },
      {
        title: 'Adding to it costs something, on purpose',
        body: 'Filing an entry requires who added it, when, and what pipeline '
            + 'produced it. A set of event times with no provenance is a '
            + 'number nobody can defend six months later, so BARRY refuses '
            + 'to store one.',
        view: 'eventbank',
        wait: '#bankBody',
        required: false,
        target: '#bankBody',
        placement: 'top',
      },
      {
        title: 'And it comes back out onto a recording',
        body: 'Anything banked for a recording can be loaded straight onto '
            + 'it, matched by mouse, session and start time — so events '
            + 'someone else detected land on your trace at the right '
            + 'timestamps.',
        view: 'eventbank',
        wait: '#bankBody',
        required: false,
        target: '#bankBody',
        placement: 'top',
      },
    ],
  });

  /* ======================================================================
     4. Figures
     ====================================================================== */
  T.register({
    id: 'figures',
    name: 'Making a figure',
    blurb: 'Build it, see it before you commit, and be able to rebuild it '
         + 'in a year.',
    steps: [
      {
        title: 'A figure is a grid of panels',
        body: 'The builder opens showing what you were just looking at. Set '
            + 'the page size, drop panels into cells, retitle them, pick '
            + 'colormaps.',
        view: 'xplore',
        before: async () => { await ensureOpen(); },
        wait: () => !!stripMenu('More')(),
        required: false,
        target: stripMenu('More'),
        placement: 'bottom',
        note: 'The builder is under More, or on any pane’s Figure '
            + 'button.',
      },
      {
        title: 'The preview is not an approximation',
        body: 'It comes from the same matplotlib code that does the export, '
            + 'so what you see is what lands in the file. PDF and SVG come '
            + 'out as true vectors.',
        view: 'xplore',
        wait: () => !!stripMenu('More')(),
        required: false,
        target: stripMenu('More'),
        placement: 'bottom',
      },
      {
        title: 'Every export writes down how to redo it',
        body: 'Not a summary — the whole layout: the recording, the '
            + 'window, the filters, which channels were on, which were '
            + 'marked bad, the gain, the event marks, and how the file was '
            + 'read. A summary is exactly what you cannot rebuild from.',
        target: railItem('results'),
        action: 'click',
        placement: 'right',
        doText: 'Click Results — the figures live there.',
      },
      {
        title: 'So a figure can be rebuilt',
        body: 'Rebuild on any figure checks what it needs against this '
            + 'machine before touching anything — is the drive mounted, '
            + 'are those channels still there, does the window fit the '
            + 'recording — then walks through it, saying what it did at '
            + 'each step, and hands you the builder with everything restored.',
        view: 'results',
        wait: '#resultsBody',
        required: false,
        target: '#resultsBody',
        placement: 'top',
        note: 'If the recording has moved, it will find it again by mouse, '
            + 'session and start time and tell you it did.',
      },
    ],
  });

  /* ======================================================================
     5. Storyboard
     ====================================================================== */
  T.register({
    id: 'deck',
    name: 'Telling the story',
    blurb: 'Turn figures into a deck you can draw on and present from.',
    steps: [
      {
        title: 'A deck built out of your own results',
        body: 'Drag figures into a sequence, draw on them, add text, and '
            + 'write the notes underneath. Click Storyboard.',
        target: railItem('storyboard'),
        action: 'click',
        placement: 'right',
        doText: 'Click Storyboard.',
      },
      {
        title: 'The drawing tools stay selected',
        body: 'Pick the arrow once and draw three arrows. Escape goes back to '
            + 'Select. A line or arrow points whichever way you drew it, and '
            + 'you grab it by its ends rather than by the corners of a box it '
            + 'happens to fit in.',
        view: 'storyboard',
        wait: '.sb-tools',
        required: false,
        target: '.sb-tools',
        placement: 'bottom',
        note: 'Shift while dragging an end snaps the angle to 15°. '
            + 'Everything else has a rotate grip above it.',
      },
      {
        title: 'Ctrl+Z, sixty deep',
        body: 'Every edit is undoable, including moving a slide in the rail. '
            + 'Ctrl+Shift+Z redoes.',
        view: 'storyboard',
        wait: '#sbUndo',
        required: false,
        target: '#sbUndo',
        placement: 'bottom',
      },
      {
        title: 'Presenting it',
        body: 'F5 goes full screen with the speaker notes below and the same '
            + 'geometry the PDF uses. Scroll to zoom into a figure mid-'
            + 'sentence, drag to move around it, 0 for the whole slide again '
            + '— so you can point at one channel without having made a '
            + 'second zoomed slide in advance.',
        view: 'storyboard',
        wait: '.sb-tools',
        required: false,
        target: () => document.querySelector('#sbBar') || '.sb-tools',
        placement: 'bottom',
      },
    ],
  });

  /* ======================================================================
     6. Keeping track
     ====================================================================== */
  T.register({
    id: 'records',
    name: 'Keeping track',
    blurb: 'History, the debug trace, and the tools that span every '
         + 'recording at once.',
    steps: [
      {
        title: 'Everything that happened',
        body: 'Every run, every figure, every filter change, with who did it '
            + 'and on which machine. The timeline groups it by day and kind, '
            + 'and clicking a day filters to it.',
        target: railItem('history'),
        action: 'click',
        placement: 'right',
        doText: 'Click History.',
      },
      {
        title: 'When something goes wrong',
        body: 'Errors keeps them, grouped by signature so twenty instances of '
            + 'one problem read as one problem. The history is not cleared '
            + '— a bug you fixed last month is still there to compare '
            + 'against.',
        target: railItem('errors'),
        placement: 'right',
      },
      {
        title: 'And when nothing obviously goes wrong',
        body: 'The debug trace records every request the interface makes, '
            + 'newest first. If something looks off with no error to show '
            + 'for it, that trace is the thing to hand over — it says '
            + 'exactly what was asked for and what came back.',
        target: railItem('errors'),
        placement: 'right',
      },
      {
        title: 'Everything BARRY has ever met',
        body: 'The other half of Sessions. Every recording, filed by project '
            + 'and mouse, each with its permanent id and every path it has '
            + 'been opened from on any machine \u2014 including the ones '
            + 'this computer cannot reach, which is information rather than '
            + 'a fault.',
        target: railItem('sessions'),
        action: 'click',
        placement: 'right',
        doText: 'Click Sessions.',
      },
      {
        title: 'And it is yours to organise',
        body: 'Projects are guessed from the path and can be overruled by '
            + 'hand. Two records that turned out to be one recording can be '
            + 'merged; one that turned out to be two can be split. Nothing '
            + 'is deleted \u2014 a merged record stays as a pointer, so '
            + 'anything still referring to its id can follow it.',
        view: 'sessions',
        wait: '#sessModeSeg',
        required: false,
        target: '#sessModeSeg',
        placement: 'bottom',
      },
      {
        title: 'Questions about the whole pile',
        body: 'ToolKit is for the things that span recordings rather than '
            + 'sitting inside one. Press T, or click it.',
        target: railItem('toolkit'),
        action: 'click',
        placement: 'right',
        doText: 'Click ToolKit.',
      },
      {
        title: 'Which channels did we throw away, and when',
        body: 'Export the bad channels for one session, one mouse, one '
            + 'project, a date range, or everything — with who marked '
            + 'them and when. It also points out the channel numbers that '
            + 'came up in more than one session, because a recurring number '
            + 'is usually a wire rather than a recording.',
        view: 'toolkit',
        wait: '.tk-scope',
        required: false,
        target: '.tk-scope',
        placement: 'right',
      },
      {
        title: 'And it all syncs by being plain files',
        body: 'GUI_logs is one JSON file per record, so a git pull brings you '
            + 'everyone else’s bad channels, presets, decks and figures '
            + 'without a merge conflict. The sync chip tells you where you '
            + 'stand.',
        target: '#syncBtn',
        placement: 'right',
      },
    ],
  });

  /* ======================================================================
     7. Curating candidates
     ====================================================================== */
  T.register({
    id: 'curation',
    name: 'Curating candidates',
    blurb: 'Going through detected events one at a time and saying what each '
         + 'one actually is.',
    steps: [
      {
        title: 'A detector guesses. You decide.',
        body: 'A line-length detector says where something might be. Whether '
            + 'it was a dentate spike, or whether a discharge was solid or a '
            + 'sputter, is a judgement someone has to make while looking at '
            + 'the recording. BARRY keeps those two things apart on purpose.',
        note: 'Candidates arrive unspecified and stay that way until somebody '
            + 'looks. Unspecified is not a category \u2014 it is the absence '
            + 'of one, which is why the count of what is left is meaningful.',
      },
      {
        title: 'It lives in ToolKit',
        body: 'Press T, or click it.',
        target: railItem('toolkit'),
        action: 'click',
        placement: 'right',
        doText: 'Click ToolKit.',
      },
      {
        title: 'Event curation',
        body: 'One tool for both jobs. Dentate spikes and IEDs are the same '
            + 'shape of work \u2014 jump to a candidate, look, press a key, '
            + 'move on \u2014 so they share an engine and differ only in '
            + 'what the categories are called.',
        view: 'toolkit',
        wait: '.tk-tool',
        required: false,
        target: () => Array.from(document.querySelectorAll('.tk-tool'))
          .find((b) => /Event curation/.test(b.textContent)) || null,
        action: 'click',
        placement: 'right',
        doText: 'Open Event curation.',
      },
      {
        title: 'Import the candidates',
        body: 'From the Event Bank, or from a CSV or .mat of times. Whichever '
            + 'way they come in, none of them arrives with a decision '
            + 'attached.',
        view: 'toolkit',
        wait: '.tk-head button',
        required: false,
        target: () => Array.from(document.querySelectorAll('.tk-head button'))
          .find((b) => /Import candidates/.test(b.textContent)) || null,
        placement: 'left',
      },
      {
        title: 'Then it is a key per candidate',
        body: 'Curating opens the recording at the first undecided one, with '
            + 'the traces large and a spectrogram, CSD and voltage raster '
            + 'beside them. One key per category. It moves on by itself. '
            + 'Six hundred candidates at two seconds each is twenty minutes.',
        note: 'u undoes \u2014 back a decision and back a candidate, because '
            + 'that is what undo means once you have already moved on. n and '
            + 'p move without deciding. Every keystroke is saved as you go.',
        view: 'toolkit',
        wait: '.tk-result',
        required: false,
        target: '.tk-result',
        placement: 'top',
      },
      {
        title: 'And the answers go somewhere useful',
        body: 'Banking a curated set writes one Event Bank entry per '
            + 'category \u2014 solid separately from sputter \u2014 '
            + 'because separating them was the point. The CSV keeps the '
            + 'unspecified ones too, so the denominator survives.',
        target: railItem('eventbank'),
        placement: 'right',
      },
    ],
  });

  /* ======================================================================
     8. StrataScope
     ====================================================================== */
  T.register({
    id: 'strata',
    name: 'StrataScope',
    blurb: 'Labelling which anatomical layer each channel is in, against the '
         + 'live rasters.',
    steps: [
      {
        title: 'Which layer is each channel in?',
        body: 'The standalone version worked on four exported PNGs, and made '
            + 'you crop each one down to the heatmap so that 64 evenly '
            + 'spaced rows would land on the right channels.',
        note: 'The crop was the whole problem: per image, redone on every '
            + 're-export, and when it was slightly off every label was off '
            + 'with nothing on screen to say so.',
      },
      {
        title: 'BARRY draws the panels, so it knows the rows',
        body: 'There is nothing to crop and nothing to drift. And because it '
            + 'is not a snapshot, you can change the window, the filters or '
            + 'the scale while you decide \u2014 which is exactly what you '
            + 'want when a boundary is ambiguous.',
        target: railItem('toolkit'),
        action: 'click',
        placement: 'right',
        doText: 'Click ToolKit.',
      },
      {
        title: 'Pick a recording and open it',
        body: 'It sets up the voltage raster, the CSD, the theta band and the '
            + 'traces \u2014 the same four views the old tool made you '
            + 'export by hand \u2014 and puts a labelling rail beside them, '
            + 'one row per channel, sitting on that channel\u2019s lane.',
        view: 'toolkit',
        wait: '.tk-tool',
        required: false,
        target: () => Array.from(document.querySelectorAll('.tk-tool'))
          .find((b) => /StrataScope/.test(b.textContent)) || null,
        action: 'click',
        placement: 'right',
        doText: 'Open StrataScope.',
      },
      {
        title: 'Paint, do not click sixty-four dropdowns',
        body: 'Pick a layer as a brush \u2014 the number keys pick the first '
            + 'nine \u2014 then click or drag down the rail. Fill down gives '
            + 'every unlabelled channel the label of the one above it, which '
            + 'is right most of the way down a shank.',
        view: 'toolkit',
        wait: '.tk-result',
        required: false,
        target: '.tk-result',
        placement: 'top',
        note: 'Labels are stored against CSC numbers, not row indices, so '
            + 'toggling even-only cannot shift them.',
      },
      {
        title: 'And it follows the recording, not the folder',
        body: 'The sheet hangs off the recording\u2019s permanent id, so a '
            + 'shank labelled on the rig is the same shank on the laptop '
            + 'after a pull.',
        target: railItem('sessions'),
        placement: 'right',
      },
    ],
  });
})();
