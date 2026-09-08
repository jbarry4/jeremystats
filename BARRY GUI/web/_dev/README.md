# Dev harnesses

Self-contained pages that drive the real interface in an iframe and report
what they find. They are served like any other file, so they run against a
live server with no build step and no test framework:

| page | what it checks |
| --- | --- |
| `smoke.html` | 77 assertions across every section — every feature's controls render and respond |
| `pose.html`  | opens one specific UI state and leaves it open, for screenshots |
| `align.html` | measures each channel row's center against its trace's midline, before and after a resize |
| `leak.html`  | counts window listeners across 60 pane rebuilds, to catch teardown regressions |
| `check.html` | the scale control, bookmark placement, analysis provenance, the frequency view and the debug trace |
| `grid.html`  | reads the raster overlay's pixels to prove the grid rules are actually drawn |
| `sb.html`    | measures the Storyboard layout for overflow at several window widths |
| `bank.html`  | the Event Bank: filing, the required provenance, import back onto a recording, and danger-button contrast |
| `strip.html` | the old pane control strip measurements, kept for comparison |
| `strip2.html` | the compacted strip: that it fits, that each menu opens outside the scroller, and that a setting relabels its own button |
| `theme.html` | every theme's tokens, that the categorical ramp is internally distinct, that Horizon leads with pink, and that the favicon repaints |
| `rebuild.html` | Figure rebuild end to end: exports a figure, audits the recipe, walks the steps, then checks the session really was restored |
| `toolkit.html` | ToolKit: all five scopes, both shapes, the refusals, and the CSV's header and filing |
| `arrows.html` | that a line or arrow points where it was dragged in all eight directions, the endpoint grips, and rotation — on screen and through the export |
| `sbdebug.html` | Storyboard deep dive: `el()`'s SVG namespace, every drawing tool, slide reordering, undo/redo by keyboard, and the inspector |
| `spike.html` | the threshold detector, the frequency view control, and how many requests one edit makes |
| `fig.html` | the figure builder's scrolling and preview |
| `arrowprobe.html` | a scratch page for one drawing interaction at a time |
| `tour.html` | presenter zoom (that it anchors on the pointer and clamps at the edges) and the guided tours end to end, including a click-to-continue step |
| `tourshot.html` | poses the tour at a given step for screenshots: `?at=menu` or `?at=<n>` |
| `probe.html` | a scratch page for walking one flow step by step when something is wrong |
| `curmanage.html` | the curation workbench: the bench, the shelf, that putting a set down costs nothing, and that a banked set's labels survive coming back |
| `curpose.html` | poses the curation workbench for screenshots: `?open=<n>` and `?shelf=1` |
| `curprobe.html` | a scratch page for one curation state at a time |
| `minorui.html` | the small interface faults: the Errors badge, the bank list's scroll, probe switching keeping the panel, one panel change reaching all six panes |
| `uiprobe.html` | a scratch page for one interface interaction at a time |
| `newfeat.html` | bookmark colours end to end, and the version chip against CHANGELOG.md |
| `figgrid.html` | the figure builder: that it opens on the panes actually in view, that rows and columns are built with + and ×, that panels arrive by being dragged, and that the rebuild dialog docks out of the way |
| `gridgeo.html` | measures where the grid's + and × controls actually sit, since "on the corner instead of the right side" is a question about boxes |
| `master.html` | one control strip for panes that are views of one recording, and a strip each when they are not |
| `display.html` | unchecked channels removed vs kept faint (checked through the request and the pixels), and marks faded or hidden with the notice that says so |
| `radio.html` | that the radio loads nothing until asked, asks before the first connection, and keeps playing when minimised |
| `marks.html` | that deleting a bookmark redraws the list rather than stacking another dialog, so the close X closes; and that one click is one request |
| `motion.html` | the boot overlay is painted before the scripts finish and cannot outlive them; the Menu button carries its three positions; the rail really reaches 54px and 0px; and skeletons are present during a load and gone after, including a failed one |

Run them by opening, with the server up:

```
http://127.0.0.1:8733/_dev/smoke.html?session=<a CSC folder>
http://127.0.0.1:8733/_dev/align.html?session=<a CSC folder>
http://127.0.0.1:8733/_dev/leak.html?session=<a CSC folder>
http://127.0.0.1:8733/_dev/pose.html?pose=preflight&session=<a CSC folder>
```

`smoke.html` puts its result in the page title as well as the log, so it can
be read from a headless capture:

```
msedge --headless=new --disable-gpu --virtual-time-budget=300000 ^
       --dump-dom "http://127.0.0.1:8733/_dev/smoke.html?session=..."
```

The `session` parameter is optional; without it the checks that need a real
recording are skipped and the rest still run.

`pose.html` accepts `pose=` one of `xplore`, `errors`, `layouts`,
`preflight`, `palette`, `health`.

Two things to know when writing one of these:

- **`.sb-item:last-child` is not the last item.** `drawSlide` appends the
  slide heading after the items, so the last child of `#sbCanvas` is the
  heading. Take the last `.sb-item` from a `querySelectorAll` instead.
- **The strip's controls live behind menus.** A control that used to be on
  `.pane-ctl` is now inside a `.ctl-pop` that only exists while its
  `.ctl-menu` button is open, and each use closes it — so open the menu
  again for each thing you need. `bank.html` has a small `fromMenu()` helper
  worth copying.

These reach into the app through `iframe.contentWindow.eval(...)`, because
`core.js` declares `BARRY` with `const` — a lexical global, which is not a
property of `window`. `eval` runs in the page's own global scope and can see
it.
