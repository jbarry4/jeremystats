# Dev harnesses

Self-contained pages that drive the real interface in an iframe and report
what they find. They are served like any other file, so they run against a
live server with no build step and no test framework:

| page | what it checks |
| --- | --- |
| `dspca.html` | X-ray end to end on the demo recording: the read, the box, the three methods and that all of them are computed every fit, the sink gap's arithmetic, banking's pictures, and the under-the-hood panel checked against the arithmetic it claims to show |
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
| `results.html` | the catalogue: that the by-product lane stays out of it through all three doors, that results know which animal they are about, and that grouping puts every result in a room rather than quietly dropping the ones it has no heading for |
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
| `presence.html` | who is curating what: that a beat carries the counters, that a second machine is seen and reported back, that the workbench treats the set as held, that taking it marks their session rather than deleting it, and that a failed presence read never breaks the bench. Writes to the live table and clears up after itself |
| `people.html` | that a name carried by the data is refused and a hand-added one goes; and that the removability rule does not use the count that includes the hand-add itself, which would refuse everything |
| `strata.html` | that selecting a channel writes nothing, that a layer button names everything selected, that the number keys do the same, and that the overlay reaches image panels at every strength |
| `strataxis.html` | that the layer overlay paints only where a lane is a channel -- the traces and a raster that names its rows, and NOT a single-channel spectrogram, a scalogram or the band-power map, whose y axis is frequency and which therefore report no rows -- and that a page carrying only `sess.strata`, with the labelling mode shut, gets the bands |
| `sessfilter.html` | that the layer and reachability filters divide the list rather than emptying it — the two layer halves must account for every card, which catches a filter matching on the wrong field |
| `banklayers.html` | that the bank's two kinds stay separate while living in one view, that a sheet shows its runs and history, that a version's CSV comes from that version's snapshot rather than the sheet as it stands, and that snapshotting adds one |
| `errctx.html` | that an error's context window holds only actions actually inside it (compared as moments, not strings — mixed timezones is what broke it), that an empty window answers ok rather than failing, and that a device being online is independent of its having anything to say |
| `history.html` | that the shared scope really spans more than one machine, that the kind filter matches a family of actions rather than one verb, that the per-person counts add up, and that the answer never claims to be showing everyone when it is not |
| `panorama.html` | Panorama end to end: that the tool owns the pane, that the cost and the step size are stated before anything runs, that the waiting screen shows both stages and builds the spectrogram up while you wait, and that all three steps end up on screen together. Forces a real run rather than taking the cached one, or there is nothing to watch |
| `pnbulk.html` | Panorama over a set: that a set can be built from the registry with a layer rule, that the tree shows every recording and what each is doing, that the bar never goes backwards, that a finished row draws its histogram and opens its spectrogram from the cache rather than from the record, and that re-running a finished set does nothing. Then converges: that the histograms pool, that the curve and both strip plots are drawn, that each recording integrates to 1, and that switching the weighting re-pools without starting another run. Writes a real set and deletes it again - unless something failed, in which case it leaves it behind on purpose |
| `pnshow.html` | that the four controls which change only how a finished run is SHOWN - log/linear bins, the bin count, the colormap, log power - leave the result on screen and start no job, while a control that changes the measurement still clears it. Written after log/linear was reported as making the Holistic view disappear. Also checks every control offers an explanation and that it opens and closes |
| `pngeo.html` | measures Panorama's boxes at two widths -- that the axes overlay sits exactly on the spectrogram it labels, that no canvas is zero-height, and that the two-column step 1 stacks rather than scrolling sideways. Names the offending element when something sticks out, which is how the colormap dropdown was caught being ninety-one pixels wider than the pane |
| `pnpose.html` | poses Panorama with a finished run, for screenshots: `?t1=<seconds>`, `?wait=0` for the form alone |
| `pnprobe.html` | a scratch page for one question at a time: currently, which ToolKit tools overflow at which widths |
| `incisorsel.html` | what Incisor reads and what changing it moves: that the landmarks are listed theta, ripple, hilus; that step 2 names the probe configuration and states the bad-channel position either way; that marking one bad really drops it from the plan and throws the standing scan away; and that the traces window opens on a CSD, even channels, five seconds. READS the recording's bad channels and puts them back through a `finally` — the first version established its starting point by clearing them, which read as twenty-six passing checks and had deleted a real one |
| `incisorplots.html` | the three channel plots: that each canvas has ink on it, that the tallest bar in the count plot stands over the channel that actually has the most events (read off the PIXELS, with the title, the axis furniture and the chosen-channel band excluded -- each of those read as a bar once), that clicking any plot picks the channel under the pointer, and that “Most spikes” is the argmax over the counts. Nothing is held across an action that repaints: `paint()` rebuilds the panel, and a canvas kept from before is a detached node whose rect is all zeros |
| `incisorshot.html` | poses Incisor with a finished scan for screenshots: `?n=<channels>` (default 5, from the middle of the probe, where a hilus is), `?path=<folder>` |
| `vacccircuit.html` | the wiring: that the layer that follows the pointer moves by `transform` and NOT by `left`/`top` (which would relayout and repaint everything under it at pointer rate, in an app whose main view redraws canvases every pan frame), that nothing in it animates at rest, that the click ripple removes itself, and that the surge delays each halo by its own distance from the button rather than firing them together. Waits on the transform CHANGING rather than on a clock -- rAF does not run on the harness's wall clock, and a fixed sleep read the old value and reported a bug that was not there |
| `vaccmorph.html` | the power-up, and the three ways a flourish goes wrong: that it OUTLIVES itself (a fixed full-screen element left behind is invisible and sits over the app for the session), that it animates something expensive (only `opacity` and `transform` are composited -- anything else repaints the canvases behind it every frame, and this reads the keyframes out of the stylesheet rather than sampling one mid-flight), and that it fires when nobody asked (`applyVacc` also runs at boot, on the cross-window sync and on the prefs reconcile, so the toggle plays it and nothing else does). Also that turning the mode OFF plays nothing, and that two in a row leave one |
| `vaccsignin.html` | getting onto the cluster without knowing what SSH is: that a machine with a key the cluster already accepts signs in with NO password (being asked for one by software that does not need it is how people learn to type passwords into things that should not have them); that an account with no working key says "a password is needed once" as a fact rather than as a failure; that signing out forgets the ACCOUNT and not the key, so the next person signs in free; and that a malformed netid never reaches the network. The password half needs a real UVM password and lives in `tools/test_vaccsignin.py` |
| `vacccat.html` | the cluster gets the catalogue too: that "Everything VACC knows" draws the same project/mouse/session tree as "Everything Jarvis knows" from ONE renderer, that it is narrowed rather than emptied, that every row it shows is a recording the cluster actually said yes to (`unknown` is excluded as firmly as `local-only` -- nobody having asked is not a yes), that the directory walk is still there beside it, and that going back leaves the full catalogue full. The last one is the regression to watch: the scope is module state, so leaving it set makes the view that promises everything quietly keep the cluster filter |
| `probedual.html` | two probes in two places at once: that the dual template splits exactly where `sessreg.banks_for` splits (CSC 1-64 hippocampus, 65-128 M2, no overlap), that each column is evenly spaced so a CSD down it is arithmetic over neighbours, that a 128-channel recording READS as a dual implant without that being written down as a decision, that assigning one labels the channel banks from it, and that the picker is built from the server so a new template appears in it. Puts the recording back exactly as it found it, source and all |
| `projchan.html` | the two filters that are not yes-or-no: project as a SET (adding a second project must widen, which is what separates it from a radio) and channels as a comparison. The assertion that matters is that the three comparisons do NOT add up to the total -- 164 recordings have no channel count, and a missing number landing in "fewer than 64" would mean absence was being read as zero. Scoped to `#hkBody`: an earlier version counted `.sess-card` and found 587 of them in housekeeping mode, because they sit in the DOM inside a `hidden` pad the whole time |
| `scanlive.html` | the running scan says what it is finding -- see the row above for the rest |
| `projflag.html` | the filing flag, and mostly its restraint: that a path naming a project other than the one the recording is filed under raises a chip and moves nothing; that the two PTEN recordings with "urethane" in the filename — where the word is the anaesthetic, not the project — are flagged **and still PTEN**; that anything filed by hand is silent, because setting it is the answer; and that flagged plus the rest is the whole catalogue, so the filter divides instead of emptying. Completeness is computed from the raw paths rather than from the flag, so an implementation that quietly skipped the awkward pair fails |

| `uikit.html` | that adopting the shared controls in `js/ui.js` changes nothing on screen: every kind and size of `ui.button`, the chips and the search field are built in the live page and measured against the hand-written markup they replace, attribute for attribute. If any pair differed, migrating a call site would be a visual change smuggled inside a refactor. Also checks the guards — that `size: 'small'` is refused rather than quietly rendering full size, which is the fault that put eleven buttons out of step with the other eighty-four |
| `sessload.html` | what the Sessions wait actually says: that a loader appears *while* the registry is being read rather than after, that it names the size of the job once there is a previous run to take it from and refuses to invent a number when there is not, that the skeleton stays underneath it (the loader says what is happening, the bones say what is coming), and that both clear on every exit including the failing one. Catches the loader in flight, and says so rather than passing when the answer arrived too early to see anything. Puts the remembered size back afterwards |
| `uiaudit.html` | one interface, or several: walks every view and reads the *computed* style of every control, then groups each family by measured shape — font size, padding, radius, border. A family with one shape is one control; a family with nine is nine controls wearing one name. Also checks the claims that came out of that: that a size modifier has a rule behind it (`.btn.small` does not), that every search field is one shape, and that search boxes open with one verb |

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

Three things to know when writing one of these:

- **A waiting loop needs far more iterations than the wall clock suggests.** The runner drives Edge with `--virtual-time-budget`, which
  fast-forwards timers - so a poll of `untilN(fn, 900, 100)` is not 90
  seconds, it is 900 iterations that can all fire before the server has
  finished forty seconds of real work. A harness that passes when opened
  by hand and fails in the sweep, on a check that waits for something
  slow, is almost always this. `panorama.html` did exactly that, twice.
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
