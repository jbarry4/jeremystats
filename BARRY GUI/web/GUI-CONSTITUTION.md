# The GUI constitution

How this interface is built, so the next feature looks like it belongs in it.

Most of what follows is not new. The application already does these things —
they were written down in code comments, or in one module and not the next,
which is why an audit found the same control drawn several slightly different
ways under several names. This is the same set of beliefs, in one place, where
somebody can read it *before* writing the next tool rather than after.

Every rule cites the code that proves it. Where a rule exists because
something broke, the counter-example is named — those are the useful half.

> **Status.** All in force as rules. §6 covers the shared compositions that
> exist today; **§6b is the one to read before building a new tool, bundle or
> Xplorefinder mode**; **§6d** (running — here or on VACC, one or many) and
> **§6e** (choosing a recording, versions, banking) are the workflow every
> tool shares. Where a section names a shared component that is still being
> built, it says so in italics and names the tool to copy until it lands.

---

## 1. Layout — where things go

### The shell

Three regions, and nothing else is top-level:

| region | token | notes |
|---|---|---|
| the rail | `--rail` | three states — `full`, `icons`, `away` (`RAIL_STATES`, [core.js](js/core.js)) |
| the view column | — | one view visible at a time |
| the log dock | `--log-h` | collapsible, shared by every view |

### Inside a view

```
<section class="view">
  <header class="view-head">      title + .sub, then .head-actions
  <div class="pad">               the scrolling body
    <div class="card">            content lives in cards
      <div class="section-label"> a section inside a card opens with one
```

`.view-head` wraps rather than overflows — the Storyboard header carries a
title field and five buttons, which used to run clean off the right edge on a
narrow window with Save unreachable.

### The rail is full

Eleven views, eleven shortcuts: `1`–`9`, `T`, `0`. There is no twelfth slot,
and adding one is not the way to ship a feature. **A new feature is a ToolKit
tool** — see §5.

---

## 2. Buttons

### Placement

Actions are **right-aligned**: `justify-content: flex-end` on both
`.head-actions` and `.modal-actions`.

The order in a modal footer, and the reference implementation is
[eventbank.js:469](js/eventbank.js):

```
[ navigational ]  [ .spacer ]  [ Cancel · btn ghost ]  [ Primary · btn ]
```

**The primary is last.** In a view header the same order holds without the
spacer: secondary actions first, the one primary at the end. Checkup and
StrataScope both already do this.

### One primary per surface

If two things look equally like the thing to click, neither is. Destructive
actions take `.danger` and never occupy the primary slot.

### Which control

| use | when |
|---|---|
| `.btn` | the one primary action on the surface |
| `.btn.ghost` | a secondary action at full size |
| `.btn.sm` / `.btn.ghost.sm` | in a header, a toolbar, or a dense row |
| `.mini` | an action *inside* a list row |
| `.pill` | a filter — one of a set, toggling what is shown |
| `.seg` | an exclusive choice between two or three modes |
| `.toggle` | a checkbox that needs a label beside it |
| `.chip-btn` | a status that is also a button (the rail's cluster chip) |
| `.close-x` | dismissing a panel or a modal |

There is **no `.btn.small`** and **no `.primary`**. Both are spellings people
reached for that no rule has ever matched: `.btn.small` left eleven buttons
full-size beside the eighty-four that used `.btn.sm` and shrank, and
`.primary` does nothing at all because `.btn` is already the filled style. The
pair `btn ghost` / `btn primary` reads as symmetric and is not.

---

## 3. Size and space

Geometry and type are tokenised in `:root`, beside the colour tokens. **Use a
token.** If the value you want is not there, you almost certainly want one
that is.

| scale | tokens |
|---|---|
| type | `--fs-9` `--fs-95` `--fs-10` `--fs-105` `--fs-11` `--fs-115` `--fs-12` `--fs-125` `--fs-13` `--fs-135`, then `--fs-15` `--fs-17` `--fs-20` |
| corners | `--r-2` `--r-3` `--r-4` `--r-5` `--r-6` `--radius-sm` (7px) `--r-8` `--radius` (10px) `--r-pill` (999px) |
| space | `--sp-2` `--sp-4` `--sp-6` `--sp-8` `--sp-10` `--sp-12` `--sp-16` `--sp-20` `--sp-24` |

Tokens are named for their **value**, not a role: `--fs-115` is 11.5px and
nothing else. That is deliberate. Naming them semantically would have meant
deciding what each size *means* while also moving 700 declarations, which is
how a refactor becomes a redesign nobody asked for.

**The half steps are real.** 9.5, 10.5, 11.5 and 12.5 carry 298 declarations —
41% of the type in the application. They are not drift and they are not being
rounded away.

**Space is even numbers only.** The odd gaps in the file are drift, not
decisions; a scale that admits both 5 and 6 is not a scale.

### Geometry that is a measurement, not a style

Some numbers are load-bearing alignment and `_dev/align.html` asserts
sub-pixel agreement against them. **Do not tidy these:**

- `.pane-grid { gap: 1px }` — the hairline between the six probe panes
- `.ch-overlay .ch-lane.compact { height:12px; font-size:9px }` — the 9px
  *makes* the 12px lane
- `.ch-overlay .ch-lane.micro`, `.strata-rows.tight`, `.strata-rows.packed`
- the `max-width` transitions on `.nav-item span` — animation machinery

They are marked in `app.css`. If you change one, `align.html` is the check.

---

## 4. Theme

Ten themes, from UVM Dark through Phosphor to the three Jirai variants
(`THEMES`, [core.js](js/core.js)).

### Never write a literal colour

Every colour comes from a token. 57 literals remain outside the theme blocks
and the worst of them duplicate tokens that already exist — `#154734` *is*
`--uvm-green`, `#ffb81c` and `#E5A823` are the gold. A literal is a surface
that will be wrong in nine themes out of ten.

- **Semantic tokens mean something**: `--ok` `--warn` `--err` `--accent`, and
  their `-soft` grounds. Use them for meaning, not for looks.
- **`BARRY.hues()`** is for things that only need telling *apart* — session
  tabs, chart bands. It comes from the theme's own `--c1`…`--c5`, so it is
  pink in Horizon and gold in UVM Dark, and it is guaranteed internally
  distinct in a way the semantic tokens are not.
- **Reading a token from script**: `BARRY.token('--accent')`. Anything that
  caches one must repaint on a theme change — see `repaintThemedSurfaces()`.

### Motion

Every animated surface needs a `prefers-reduced-motion` block. There are
twelve, and the house pattern is to **name the component and stop its
animation**, not a blanket `* { animation: none }` — reduced motion should
keep the contrast and lose the movement, not flatten the page.

### Fire mode

Opt-in **per surface**. The six that opt in are enumerated in `app.css` under
*"the six surfaces that opt in"*. A new surface joins that list deliberately
or not at all; the mode is not a filter over everything.

---

## 5. Waiting, empty, and wrong

### Waiting

| use | when |
|---|---|
| `loader(label, sub)` | one wait, no distinct stages |
| `stepLoader(label, steps)` | a wait with **named stages that each take real time** |
| `BARRY.skeleton.into(host, kind, n)` | a list that is about to fill — it shows the *shape* of what is coming |

Use a skeleton and a loader together where both apply: the bones say what is
coming, the loader says what is happening. Sessions does this — the registry
read is about six seconds, and the wait states the size of the job.

**Never a bespoke spinner.** X-ray renders `<div class="spinner">` and there
is no such rule, so its loading card shows an empty div.

**Do not name stages that do not take time.** A `stepLoader` whose second and
third dots light for zero milliseconds is a progress bar lying about where the
time goes. If there is one slow stage, use `loader`.

Say the size of the job where you can, and say when something is taking longer
than it should. Both are more useful than a spinner.

### Empty

`.empty-state` — and it says **what to do next**, not merely that there is
nothing here.

### Wrong

- `toast(msg, 'ok' | 'warn' | 'err')` — three kinds, no fourth.
- Client errors go through `reportClientError(where, message, detail)` so the
  Errors view sees them. A `catch` that only does `console.log` is a fault
  nobody will hear about.

---

## 6. Compositions

A control can measure identically to its neighbour and still look like it
belongs to a different application, because what differs is one level up.
These are the shapes that answer that, in `web/js/ui.js`.

### `stepHeader({ title, step, blurb })`

Every tool's header. Mixed-case title, an optional step chip, then the blurb.

```
┌──────────────────────────────────────────────────────────┐
│ X-ray  (step 4 of The Dentist)  Which kind of dentate…   │
└──────────────────────────────────────────────────────────┘
   strong        .step-n              p.hint
```

**The worked example.** Braces and X-ray are adjacent steps of one bundle and
had nothing in common:

| | Braces (before) | X-ray (before) |
|---|---|---|
| header | `.card.br-intro` › `.section-label` + `p.hint` | `.dp-intro` › `strong` + `.dp-step` + `.hint` |
| title | ALL CAPS, boxed in a card | mixed case, unboxed |
| step | text, inside the title | a chip of its own |

Across the app there were thirteen bespoke tool headers using **four
alignments, seven gaps, three title elements and three subtitle classes**.

X-ray's shape won, because it was already closest to the two headers that
*were* shared — `.tk-head` and `.view-head` are both a mixed-case title with a
subtitle beside it, and neither is boxed. The step is a chip because a title
should say what the tool is; "step 4 of The Dentist" is a different fact
about it.

Do not add a fourteenth. If a tool needs something the header cannot express,
change `stepHeader` so every tool gets it.

### `field({ label, control, hint, inline })`

One labelled control. `.section-label` above, the control, the hint under it.
`inline: true` puts the label beside a control too short to deserve a line.

Six primitives did this: `.section-label`, `.field label`, `.dp-lab`,
`.ctl > label`, `.mini-field`, `.vacc-field` — and `.wiz-grid .field label`
un-uppercasing some of them. `.section-label` won on merit and on usage.

### `workbenchCard({ title, chips, count, owner, when, progress, tally, actions })`

A thing you have open, on a bench, until you put it down. Checkup and
StrataScope both build one.

**The owner is always stated, including when there is not one.** "Nobody has
this" is what a bench exists to say. StrataScope used to omit it entirely
when unassigned, so an unclaimed sheet looked identical to one whose owner you
simply had not read.

**What is deliberately not unified.** A curation set can be handed to
somebody; a sheet cannot — there is no assign path for one. So a set's owner
is a `button.cur-who` and a sheet's is `span.cur-who.static`: same words, same
place, no hover, no pointer. A control that looks pressable and is not would
be a worse lie than the inconsistency it replaced.

That is the general rule when two surfaces differ: **unify the shape, keep the
difference that is about what the thing can do.**

### Still to come

`analysisRun`. Comod, Incisor, Panorama and Spectrum share three dead
`.comod-*` classes, which is its own evidence they were copy-pasted from one
another. Until it lands, follow §1 and copy the nearest well-behaved
neighbour.

---

## 6b. Building a tool, a bundle, or an Xplorefinder mode

Sections 1–6 are about how a control looks. This one is about the machinery a
new tool has to join, and the parts of it that are easy to get wrong in ways
nothing catches until somebody's decisions are gone.

### The three shapes a new thing can take

| shape | example | what it is |
|---|---|---|
| **a tool** | Panorama, Kilosort | a panel in ToolKit. Owns the result area, reads a recording, may write to Results |
| **a bundle** | The Dentist | an ordered set of tools that are steps of one job |
| **an Xplorefinder mode** | Checkup, StrataScope | takes over the panes, the keyboard and the aid window to work *on* a recording |

Start with a tool. A bundle is what you make once several tools turn out to
be steps of one job, and a mode is only justified when the work needs the
traces on screen.

### A tool

```js
toolButton('panorama', 'Panorama', 'The whole recording at once: …')
```

- Register it in ToolKit, **not the rail** (§1 — eleven slots, all taken).
- The blurb says what the tool *does*, not what it is called.
- Dispatch a `q.tool === 'yours'` branch to your paint function.
- If it can run on the cluster, add its id to `VACC_TOOLS` — and only then.
  A tool marked as offloadable that is not is worse than no mark.

### A bundle

```js
const DENTIST = [
  ['incisor', 'Incisor', 'find them'],
  ['curate',  'Checkup', 'clean them'],
  ['braces',  'Braces',  'line them up'],
  ['dspca',   'X-ray',   'tell them apart'],
];
```

Each step is `[id, name, what it does in three words]`, in the order you do
them. Register the bundle in `BUNDLES` with an `id`, a `name` and the `icon`
of the tool whose glyph stands for the whole thing.

**A bundle must remove its members from the flat tool list below it.** This is
the rule with the longest comment in `toolkit.js` and it is worth reading:
a bundle that does not is "a menu that describes one thing twice and makes
the reader work out that it is one thing." `BUNDLED` does this for you, so
the only thing a new bundle has to do is be in `BUNDLES`.

Every step gets a `stepHeader` with its `step` set (§6). The header is where
somebody arriving at step 3 learns there are four.

**The step number is derived, never typed.** Each tool used to write its own
"step 4 of The Dentist". When Root Canal was inserted between Braces and
X-ray, X-ray's header had to be edited by hand from 4 to 5 — it was, this
time. Use `stepOf(toolId)`, which reads the position out of `BUNDLES`, so
inserting a step renumbers every header after it. *(Being built; The Arc
already derives its own.)* Incisor and Checkup have no `stepHeader` at all
and are being brought in.

**A step that is not built yet is shown and disabled, with the reason on it.**
Leaving it out says the step does not exist. Somebody arriving at Coupling
needs to know both that it is the third of four and that the two before it
come first.

#### Bundles fold

A bundle is a heading with a list under it, and **every bundle folds**. Three
bundles of three and four steps is eleven rows before the flat list even
starts, and somebody working in one of them has no use for the other seven.

`bundleCard` already does this; a new bundle gets it by being in `BUNDLES`.
What matters is the four rules it follows, because they are what make folding
safe rather than merely possible:

1. **The head is a `button`.** It was a `div`, which nothing can tab to and
   nothing can announce. Full width, left-aligned, `aria-expanded` — the
   target is the whole row, not the chevron.
2. **Open by default; only folds are remembered.** Stored as the *folded*
   ids in `barry.tkFolded`, so a bundle added later arrives open and is seen
   rather than arriving folded and never being found.
3. **Folding never costs you your place.** A folded bundle holding the tool
   you are in keeps its accent border, and its head names *that step* in
   place of the count. "Where am I" stays answered by a menu you have tidied.
4. **The fold is a preference, so it persists.** Same reason the rail
   remembers its width. A fold you have to redo every morning is not a
   preference.
5. **It animates, and says so to reduced motion.** The steps ease their
   height and opacity closed rather than vanishing, because a list that
   snaps shut reads as something having broken. Under
   `prefers-reduced-motion` it snaps (§4). *(Being built.)*

The same shape applies to anything else that is a heading over a list — the
Explorer's tree sections and the Errors view's groups already work this way,
with the same `.caret` and the same `.open` class on the parent. Copy that,
not a new one.

### An Xplorefinder mode

A mode is entered with a gid and takes the whole interface:

```js
BARRY.yours.enter(gid)   →  true/false
BARRY.yours.exit()
BARRY.yours.active       //  a GETTER. Calling it throws.
BARRY.yours.rebind(sess) //  a reopen replaces the session object
BARRY.yours.state        //  what a pop-out or a deep link needs
```

**One mode at a time — and no mode is responsible for that on its own.**
Every mode takes over the panes, the keyboard and the aid window. Entering one
on top of another leaves two toolbars stacked, two sets of key handlers
fighting over the same presses, and an aid window belonging to whichever got
there first.

This section used to say each mode should exit the others itself, and show
Checkup being exited by name. That held while there were two modes. There are
five now — Checkup, StrataScope, Spotter, Braid and The Arc — and a check
found that **none of them exits all the others**:

| entering | exits |
|---|---|
| Checkup | StrataScope only |
| StrataScope | Checkup only |
| Spotter | Checkup, StrataScope |
| Braid | Checkup, StrataScope |

So entering Checkup with Spotter open leaves both live. Five modes that each
list the other four is twenty pairs kept in step by hand, and the sixth mode
breaks them all again. The rule is therefore a registry, not a habit:

```js
BARRY.modes.register('yours', BARRY.yours);   // once, at load
BARRY.modes.enter('yours', gid);              // exits whatever is active first
```

*`BARRY.modes` is being built (round 2, see the plan). Until it lands, a new
mode must exit every mode listed above, and the table is the list.*

**Resolve the recording, do not assume a path.** Registry rows carry `here`,
a list of paths reachable from *this* machine — not `path`. Ask for `here[0]`
and say so plainly when it is empty:

> None of this recording's paths are reachable from this machine, so there is
> nothing to look at.

**`rebind` exists because reopening a recording replaces the session object.**
A mode holding the old one keeps painting into a detached tree.

### Bad channels

Read `README.md § Session identity` before touching these.

- **Stored by CSC channel number, never by row index.** An index shifts the
  moment somebody toggles even-only.
- Identity is **mouse + session + the recording start time from the Neuralynx
  header** — not the path, which differs per machine. Matching is tiered:
  exact, then strong (mouse+session, unambiguous), then weak (nearest start).
- Mouse + session alone is **not unique**. `M5s2bnov16` and `M5s2cnov16` are
  both mouse 5 session 2.
- In a CSD panel a bad channel is **interpolated from its neighbours, not
  blanked** — a second spatial derivative would lose three rows to one bad
  channel.

**A harness that touches bad channels must put them back.** The first version
of `incisorsel.html` established a known starting point by clearing them. It
reported twenty-six passing checks and had deleted a real one. Read them,
work, restore in a `finally`.

### Banking

An entry is evidence, and evidence that cannot say where it came from is not
evidence. The bank refuses one that cannot state **who**, **when** and **what
produced it** — script, detector or file. There is no default and no guess.

- Times are **seconds from the start of that recording**, so they only mean
  anything against it.
- Match on the **registry gid**. Matching banked data by an identity string
  returns zero, silently.
- **Version numbers are not unique.** Two machines curating the same entry
  both mint the next number, and the union keeps both — a real entry is
  numbered `0,1,2,3,4,3,4`. The per-version **`id`** is the identity. Asking
  by an ambiguous number is refused rather than answered, "because there is no
  defensible way to pick and a wrong answer here reads events that somebody
  else decided."
- A snapshot's digest is canonicalised — times to the microsecond, labels as
  text — so `315.275` and `315.27500000000003` are one snapshot, not two. That
  digest is what makes "both copies agree" a check instead of an assumption.

**If your tool moves an event in time, it must carry `from_t`.** Time was the
only identity a banked event had. Without the time it used to have, a moved
stamp arrives as one event vanishing and an unrelated one appearing — a
history reading "1198 lost, 1198 gained" about a pass in which nothing was
decided differently at all.

### Sets, benches and shelves

A set is work somebody has open. The view is a **workbench, not a table**:

- The **bench** holds what is open; the **shelf** holds everything else.
- Putting a set down costs nothing and saves nothing, because every decision
  was written the moment it was made. Say so in the button's title.
- A set carries an **owner**, and the card states it even when there is not
  one (§6).
- Use `ui.workbenchCard`. Do not build a third one.

**Storage: no two machines ever write the same file.** Every editable record
is split by machine — `sessions/m1s2@z390-4f1a.json` — so git sees unrelated
files and a conflict is impossible rather than rare. The merge happens on
read, in code, because only code knows that two `paths` lists should be
unioned while two `note` strings should not. **Never write another machine's
shard.**

### Presence

If two people could be in the same set, use presence — and understand what it
is not.

- It lives **only in Supabase**. No local shard, nothing in `GUI_logs`,
  because a presence row that survives a restart is a lie.
- It **expires rather than unlocks** (TTL 150s against a shorter client beat).
  A lock somebody has to give back strands the set when a machine crashes, and
  the one thing worse than two people in a set is nobody able to get into it.
- The holding is **advisory**. The point is to stop two people colliding
  *accidentally*; a hard block would also stop the deliberate case, which is
  legitimate and common — somebody left a set open on a rig and went home.
- If the cloud is unreachable the answer is "nobody is reported present",
  which is exactly the truth available.

### Cost, before it is spent

Supabase egress is counted in **requests, not bytes**. Ask once per entry and
hold it; do not ask per render. State the cost and the step size before
anything long runs — Panorama does this and it is the pattern to copy.

### Before you call it done

- [ ] A ToolKit entry, and removed from the flat list if it is in a bundle
- [ ] `enter` / `exit` / `active` / `rebind` / `state` if it is a mode
- [ ] `onHide` if it starts a poll or a beat
- [ ] Bad channels by CSC number; restored by any harness that touches them
- [ ] Banked entries state who, when and what produced them
- [ ] `from_t` on anything that moves an event
- [ ] Writes only this machine's shard
- [ ] A `_dev/` harness, listed in `_dev/README.md`

## 6c. Two views of one thing

Three views in Sessions show the same recordings: **Scan a drive**,
**Everything Jarvis knows** and **Everything VACC knows**. They are not three
lists. They are one catalogue asked three questions — what has this computer
met, what has the lab met, what can the cluster read — and the cluster view
answers its question in *both* of the other two's shapes.

That only stays true if nobody writes a second copy of anything. This section
is what "nobody" means in practice.

### One renderer per shape, chosen by scope

| the thing | the one renderer | drawn by |
|---|---|---|
| a recording as a **card** | `sessionCard` — sessions.js | Scan a drive · VACC ▸ Recordings |
| a recording as a **row** | `sessionRow` — housekeeping.js | Everything Jarvis knows · VACC ▸ Catalogue |
| the project → mouse **tree** | `housekeeping.catalogue(scope)` | both catalogues |
| the **probe** chip | `BARRY.hk.probeChip` | card, row, drive scan |
| the **cluster** mark | `BARRY.vacc.mark` | card, Xplorefinder tab |

So a change to a session card lands in the drive view and the cluster view at
once, because there is one function. **A card change does not land on a tree
row, and must not be made to.** A card carries a duration, a sample rate and
four quality buttons; a row carries attachment counts in a dense line. They
are different shapes answering different questions, and forcing one to follow
the other is how a view ends up with furniture nobody asked for.

What crosses between them is the **vocabulary** — the chips — never the
layout.

### Getting one renderer into two places

Two techniques, both in the tree already. Prefer the first.

**Parameterise the host.** `housekeeping.catalogue(scope)` keeps a `SCOPES`
table of `{ host, detail }` ids and draws into whichever it is handed. This is
the default answer and needs no comment beyond the table.

**Move the nodes.** `parkList()` / `listInto()` in sessions.js move the one
`#sessFilters` and the one `#sessTree` between pads, because that markup is
fixed in `index.html` and `.pad` is `flex: 1` — two visible pads split the
height, so the list cannot simply be shown in both. Moving a node keeps its
listeners, so the search box being typed into is the one wired at boot, with
the one `query` behind it.

Only when the markup cannot be parameterised, and then:

- Park the nodes **before** anything clears the pad they are in.
  `innerHTML = ''` on a host holding them does not move them, it destroys
  them, and the symptom is a view that silently has no list.
- Anything that positions itself relative to them must reposition on every
  render, not only when it is built — the pick bar was inserted once and
  stayed behind in the pad the cards had left.

### One module owns the fact; each surface owns the consequence

`native` and `staged` mean something, and four surfaces say so: the card in
Sessions, the detail panel in Housekeeping, the tab in Xplorefinder, and the
toast when a recording opens. Each of them wrote its own sentence, and the
predicate behind them — `state === 'native' || state === 'staged'` — was
written out five times in three files.

The split that fixes it:

- **The fact** lives in the module that owns the subject. `BARRY.vacc.words`
  is a table of what each state *is*; `BARRY.vacc.mark` is the chip; and
  `canRead` is defined as *"there are words for it"*, so the set that opens
  and the set that gets a mark cannot come apart.
- **The consequence** belongs to the surface, because it is about the thing
  that surface is offering. "Opening it from here reads the same files the
  rig wrote" is the detail panel's sentence and belongs nowhere else.

Restating the fact is the fault. Adding a consequence is not.

The same rule made `probeChip` shared: three places drew it, and three copies
of "is this confirmed" would have ended up disagreeing about what green
means.

### Absent is not negative, in every view at once

The cluster has four states and only two are affirmative. `BARRY.vacc.of`
returns **null** for a recording nobody has established an answer for — which
is most of a fresh scan, because exact ids are minted when headers are read.
Every view has to read that the same way: **no mark, no Open, and no
refusal either.** A view that reads a missing answer as "the cluster cannot
reach this" is claiming something nobody checked.

This has been got wrong twice in this codebase — `canOpen` in sessions.js,
where a missing field read as "not on this machine" hid every recording that
was certainly openable, and the first VACC chips. Both have comments; read
them before writing a fifth reader of a four-state field.

### A count has to describe the list underneath it

Whatever narrows a view narrows the numbers above it. The cohort pills
counted the whole catalogue whatever the mode was, so the cluster view
offered **"PTEN (381)" above a list of 109** — and the fix has to be one
predicate, not two that agree today: `modeAllows` is read by the filter and
by the counts, for the same reason `inLocal` was extracted after the view
said "188 of 185".

Zero is an answer. A cohort with nothing in this view reads `(0)` and is
dimmed, not dropped — a pill that vanishes when you change mode is one you
cannot change back with.

### Adding a fourth view

1. It is a **question about the same catalogue**, so it is a mode on the
   existing switch — not a rail slot (§1) and not a new list.
2. Write the narrowing as one predicate and give it to the list *and* the
   counts.
3. Draw the existing card, the existing row and the existing chips. If you
   need a new chip, put it in the module that owns what it means and let the
   other views draw it too.
4. Say in the line above the list which of the questions it is answering, and
   leave out the clauses that are about a different one.
5. An empty view says what fills it (§5) — for the cluster view that is
   "scan a folder under Directories", not "nothing matches those filters",
   which sends somebody looking for a filter that does not exist.

---

## 6d. Running a tool — here or on the cluster, one or many

Every tool does the same job in the same order: **pick what to run on, set
the parameters, run it, get the result back, keep it.** Until now each tool
drew that differently — Braces and X-ray with a *One set at a time | Many
sets at once* switch, Incisor with tabs that made "VACC" mean "many at once",
Doppler with two ghost buttons and no primary. This section is the one shape.

*The shared pieces named here (`runBar`, the VACC health panel, upload) are
being built in round 2. Until they land, Braces is the reference for
everything local and this section is the spec.*

### Four modes, on two independent axes

| | one | many |
|---|---|---|
| **this computer** | local run | local batch |
| **VACC** | VACC run | VACC batch |

*Where it runs* and *how many* are separate questions and never fused into
one control. A tool **declares** which of the four it supports, and the
interface offers only those:

```js
modes: { local: ['one', 'many'], vacc: ['one', 'many'] }   // Incisor
modes: { vacc: ['one', 'many'] }                           // Doppler
modes: { vacc: ['one'] }                                   // Drift
```

Which a tool gets is decided by the work, not by what is easy to build:

- **Simple and quick** → local run only (Spotter, Kilosort, StrataScope).
- **Repetitive** → local run and local batch (Checkup, Braces, Root Canal,
  X-ray, Eye).
- **Heavy and done often** → VACC run and VACC batch, and no local mode at
  all where running it here would only teach people to wait (Doppler,
  Circuit).
- **Heavy and done once** → VACC run only (Drift).

| tool | here · one | here · many | VACC · one | VACC · many |
|---|---|---|---|---|
| Incisor | ✓ | ✓ | ✓ | ✓ |
| Checkup, Braces, Root Canal, X-ray, Eye | ✓ | ✓ | | |
| Doppler, Circuit | | | ✓ | ✓ |
| Panorama | ✓ | | ✓ | |
| Spotter, Kilosort, StrataScope | ✓ | | | |
| Drift | | | ✓ | |

A tool that gains a mode changes its declaration, not its layout.

### The run bar

One component, `BARRY.ui.runBar`, at the top of the tool under its
`stepHeader`:

```
 Where    [ This computer | VACC ]        (hidden if only one)
 How many [ One | Many ]                  (hidden if only one)
```

- An axis with a single option is **hidden**, not shown disabled. A choice
  that cannot be made is not a choice.
- VACC is offered only while VACC Mode is on and an account is signed in —
  and never as the *only* way to reach a tool that can also run here.
- The **primary action is last and names what it will do**: *Run on this
  recording*, *Read 12 sets*, *Submit 40 to VACC*. Never "Go", never "Run
  the batch" as a ghost button (§2).
- **Say the cost before it is spent**: how long, how many, on which
  partition. Panorama already does this and it is the pattern.

### Parameters

- In the tool's own panel, below the run bar, as `ui.field`s — never in a
  popover somebody has to find.
- Every parameter has a **default that is stated**, and the result records
  the parameters it was made with, verbatim. A result whose parameters are
  lost cannot be defended.
- One set of parameters applies to a whole batch. A batch that silently used
  different settings per recording is not a batch.

### Waiting

§5 applies, plus:

- **Local run** — `loader` or `stepLoader` in the result area.
- **Batch** — one row per recording with its own state (*queued · reading ·
  done · failed · skipped*), a bar that never goes backwards, and a **Stop**
  that stops. A batch skips what is already done and says so; re-running a
  finished batch does nothing.
- **VACC** — the job's own state (*uploading · submitting · queued ·
  running · fetching · done*), with the Slurm job id visible. Queued is not
  an error and is never drawn like one.

### Results

- A run leaves a **result**; a batch leaves **one proposal per recording**.
  **Nothing is banked by a batch.** Each proposal is reviewed and banked
  through the bank dialog (§6e) — the review is the point of the tool, and a
  batch that skipped it would bank work nobody looked at.
- A result is cached per tool and per recording (`GUI_logs/<tool>/results`)
  and **re-opens instead of re-running**. Say when a shown result is cached,
  and offer to re-run.
- A VACC result is pulled back and stamped `computed_on: {kind: 'vacc',
  netid, slurm_id}`, so a result says where it was made.

### VACC

**One account runs the lab's jobs.** Others sign in with their own netid to
reach the shared space.

- **Data lives in `Jarvis Data`**, under `/gpfs2/scratch/sakhava1`, mirrored
  as `<project>/<mouse>/<recording>/`. It is **processing space**: critical
  data is kept elsewhere, and scratch may be purged. The local copy is never
  touched and stays the source of truth.
- **Uploading** is part of *Scan a drive*: select recordings, *Upload to
  VACC*. A file already there at the same size is skipped, so re-uploading
  is cheap and resumes where it stopped. An uploaded recording is runnable at
  once.
- **Say "uploaded", not "staged".** "Staged" implied Jarvis had copied
  something when it had not.
- **A cluster path never enters the registry.** A recording on the cluster is
  known by its identity, the same way it is on a second machine.
- **Access is checked, and a refusal is specific.** When the shared space
  cannot be read, say *what* was refused, link the folder in OnDemand
  (`ondemand.vacc.uvm.edu`), and say **ask Shahriar to add you**. Never a
  bare "permission denied".
- **Jobs outlive the window.** A background check runs `squeue --me`,
  reattaches to every job this account owns — including ones started before
  Jarvis last restarted — and pulls back whatever finished. The VACC health
  panel shows queued, running, recent failures and access.

---

## 6e. Choosing, keeping and naming

### Choosing a recording

Braces is the reference (`braces.js`), and `ui.pickRecording` is its rules
made shared. *(Being built; until then, copy Braces.)*

- The label is **Recording**. Not "1. Which recording", not "Session".
- One placeholder: *Which recording? Type a mouse, session or date…*
- **Usable first, everything on request.** List the recordings this tool can
  do something with; a *show all recordings* toggle lists the rest. Picking a
  recording and being told "nothing here" reads as the tool being broken, not
  as the recording being the wrong one.
- **Open on something workable** — whatever is already chosen, else the first
  usable one. Never on nothing.
- **Changing the recording resets everything downstream** — the entry, the
  channels, the version. A panel still describing the last recording's set is
  describing something no longer on offer.
- A second choice under it (*Which banked entry*) is a list, not a select,
  and an entry that cannot be used is **shown and disabled with the reason**,
  not left out.

The same rows feed the batch picker, so *one* and *many* choose from the same
list.

### Versions: the model

`backend/versions.py` is the rule, and it is a good one.

- **Picking up a version starts a new one from it.** The tip continues the
  line: v3 → **v4**. Anything with work after it branches: v1, with v2 and
  v3 after it → **v1.1**. Applied again it keeps working: v1.1 → v1.2, and
  v1.1 once v1.2 exists → v1.1.1.
- Going back is not a mistake to prevent; destroying what came after is.
  v1.1 is *visibly a second line*, with v2 and v3 untouched beside it.
- **v0 is always the detector's list** — the thing curation is done *to*.
- `"1.10"` sorts after `"1.9"`. Compare through `versions.key`, never as text.
- The stored `v` is a plain integer (the sync key); the **name** — `v4.1` —
  is *derived* from lineage (`from_v` / `from_id`). Never store a name, never
  display `v` in place of it.
- The **id is the identity**, not the number. Two machines both mint the next
  number, so numbers repeat.

**Render every version through one `versionLabel(v)`.** About thirty places
build `'v' + (name || v)` by hand, which is how one version comes to read as
two different numbers in two panels.

**What the data showed, and how it is repaired.** Of 948 stored versions,
155 had no id, and 42 numbers were duplicated in a way no id could resolve —
each one pass recorded twice, the same person in the same minute, one copy
from before ids existed. They sit in several machines' files, and a machine
may only write its own. So the repair is **on read, never a rewrite**: a twin
collapses into its id-bearing copy **only when the snapshots match exactly**
(`snap_sha`), and an id-less version gets an id every machine derives the
same way. No file changes, so nothing can be lost. *(Being built, with a
check that proves every event survives.)*

### Versions: choosing one

**One control for every version choice: `ui.versionTree`.** The data is a
tree, and six different controls showed it as a list — Braces' select,
X-ray's *Read from*, Checkup's *Pick it up from*, the Event Bank's chips and
rows, Root Canal's radios, Eye's own formatter — which is why a branch name
like v4.1 looked arbitrary. *(Being built.)*

Vertical lanes, like a git graph: the trunk down the left, each branch in a
lane to its right, one row per version.

```
  o  v6    Rain     2d   1,204   newest
  |
  o  v5    Rain     3d   1,198
  |  o  v3.2  Jeremy   1d   1,187
  |  |
  |  o  v3.1  Jeremy   5d   1,190
  | /
  o  v3    Rain    12d   1,211   aligned
  |
  o  v0    Incisor  import  1,306
```

Every row: **name, who, when, count, state** (*newest · aligned · archived ·
not on this machine*). A version that cannot be read here is shown and
disabled, with the reason — never dropped from the tree.

### Banking: one dialog, every time

There are two acts, and they are different on purpose:

| | a new **entry** | a new **version** |
|---|---|---|
| from | Incisor, Doppler — a detector's output | Checkup, Braces, Root Canal, X-ray — work done *to* an entry |
| asks for | a **name**, pre-filled from `bankName.suggest`, never empty | a **note** — the entry already has a name, shown read-only |
| states | where it will be filed | **continues v5 → v6**, or **branches from v3 → v3.1** |

Both go through **one** `ui.bankDialog`, in the same place, every time.
*(Being built.)* Until now it was a dialog in Incisor, an inline card in
Doppler, a note-only dialog in Root Canal, and a one-off "Who is banking
these?" prompt in Checkup.

- **Who** comes from the profile. Never ask it in a prompt.
- **Nothing banks silently.** Banking is the one act that is evidence, so it
  always shows what is about to be written and where.
- A batch banks nothing (§6d). Its proposals come through this dialog one at
  a time.

## 7. Breaking a rule

Contextual overrides are allowed. The difference between a good one and a bad
one is whether the next person can tell why it is there.

**A good one** — `.tk-pills .pill` overrides the standard pill's padding,
and says so:

> *Each pill carries a name and a subtitle, so it stacks rather than sitting
> on one baseline like the plain pills elsewhere.*

The audit flagged it, the comment answered it, and it stayed. `.ctl-seg .mini`
(radius 0, because the minis are joined into one group) is the same kind.

**A bad one** — `.fb-actions`, declared twice for two unrelated features. The
pipeline's folder bar and the feedback panel both claimed the `fb-` prefix
with different spacing; the later rule won, so the folder bar had been quietly
wearing the feedback panel's 10px gap instead of its own 6px. Nothing failed.
It simply was not what it said.

**So:**

1. Scope an override to a parent (`.tk-pills .pill`), never redefine the base.
2. Say why, in a comment, on the rule.
3. Pick a prefix that names **one** feature, and check nothing else owns it.
4. If two features want the same name, one of them is not a feature name —
   `.fb-stats` turned out to be "a row of stat chips" used by seven modules,
   and is now `.chip-row`.

---

## 8. Lexicon

Half of what reads as inconsistency is wording. One verb per gesture, one noun
per object.

| say | not | for |
|---|---|---|
| **Search…** | Filter…, Find in…, Jump to… | the box above a list. One verb, whatever the list |
| **close** | put down | finishing with something on a bench |
| **set** | sheet | a unit of curation work |
| **Clear the bench** | Close all | closing everything open at once |
| **recording** | session, file | one `.ncs` folder — *session* is the number in its name |
| **banked** | saved, stored | written to the Event Bank |
| **this computer** | local, here | the machine in front of you — 25 strings say it this way and none says "local" |
| **the cluster** | remote, the server | the VACC as a place work runs |
| **VACC** | the cluster | where it is the proper noun — *VACC account*, *VACC mounts*, a path |
| **uploaded** | staged | a recording Jarvis has copied to `Jarvis Data`. "Staged" implied a copy that had never been made |
| **Recording** | Session, 1. Which recording | the label over the recording picker, in every tool |
| **v4.1** | 4.1, version 4.1, v7 | a version, always by its derived name through `versionLabel` — never the stored integer |

Placeholders describe what you can type, not what the box is:
*"Type a mouse, session or date…"*, not *"Search sessions"*.

Button labels are the verb of the thing they do — **Read a batch**, **File
away**, **Line them up** — not OK, Submit or Go.

---

## 9. How this is enforced

Rules that can be checked by a machine are, so this document is enforced
rather than merely published.

| check | what it catches |
|---|---|
| `python tools/check_classes.py` | a class the markup applies that no rule matches — and it separates the ones something *selects* on, since removing those is a behaviour change |
| `python tools/ui_baseline.py` | every control's measured shape, every composition's structure, container gaps, grid column counts and overflow, at three widths and one short window. A change that was meant to change nothing must produce an empty diff |
| `python tools/harness_run.py` | the ~60 behaviour harnesses in `_dev/` |
| `_dev/vaccopen.html` | that the cluster's meaning is single-sourced (§6c): that `words` and `canRead` cannot come apart, and that every mark drawn on screen is a word the module actually keeps — a view that built its own chip fails here |
| `_dev/vacccat.html` | that two views of one list are one list (§6c): one `#sessTree` and one `#sessFilters`, not two, and that leaving a view hands them back rather than destroying them |
| `_dev/uiaudit.html` | the same measurements live, plus the claims that need two classes on a real element — which is how `.btn.small` is caught, since `small` resolves on its own and the pair matches nothing |

Run all of them from **PowerShell**, never bash: under bash Edge's
`--dump-dom` writes nothing on this machine, so every harness reports zero
checks and the whole suite reads as a clean sweep.

### When you add a feature

- [ ] It is a ToolKit tool, not a rail slot (§1)
- [ ] One primary action, last, right-aligned (§2)
- [ ] Sizes and spacing from the tokens (§3)
- [ ] No literal colours; a `prefers-reduced-motion` block if it animates (§4)
- [ ] `loader` / `stepLoader` / skeleton, never a bespoke spinner (§5)
- [ ] An `.empty-state` that says what to do next (§5)
- [ ] Errors through `reportClientError` (§5)
- [ ] A Ctrl+K palette entry; a deep-link param if it has shareable state
- [ ] `onHide` if it starts a poll or a heartbeat
- [ ] If two views show it, **one** renderer and **one** predicate (§6c) —
      and the counts above the list read the same predicate as the list
- [ ] A fact about the subject lives in the subject's module; only the
      consequence for this surface is written here (§6c)
- [ ] `check_classes.py` clean; `ui_baseline.py` diff is only what you meant
- [ ] A `_dev/` harness, listed in `_dev/README.md`

---

## 10. Speed — starting, switching, opening

The data is fast; README § Speed is how. This section is about everything
around it — start-up, switching views, opening a tool — which is what people
mean when they call the app lethargic, and which nothing had measured until
`tools/perf_baseline.py`.

There is no lite mode. Every rule below makes the app faster on every
machine, so it is fine on a laptop over a VPN and better on a lab computer.

### Measure it, in real time

```
python tools/perf_baseline.py            compare against the stored run
python tools/perf_baseline.py --save     store this run as the baseline
```

It drives `_dev/perf.html` on the **wall clock**. The harness runner cannot do
this: it uses `--virtual-time-budget`, which fast-forwards timers, so any
duration taken under it is invented. Open `_dev/perf.html` by hand on a laptop
and the table on screen is the result.

Before speeding anything up, measure it; after, measure it again. **A change
that does not move its number is not kept.** A number counts as worse only
when it is both 30% and 100 ms worse — timings are noisy in a way shapes are
not.

### Start-up: import what you use, when you use it

Measured on the lab machine, about **3 of the 3.6 seconds** before the server
serves are Python importing tools nobody has opened:

| module | cost | for |
|---|---|---|
| `backend.analysis` | 1.3 s | panel rendering |
| `backend.cfc` | 1.1 s | Braid |
| `backend.dspca` | 0.6 s — sklearn alone 0.5 s | X-ray |
| `backend.compose` | 0.3 s | figure export |

On a laptop, where antivirus scans every compiled library the first time it
loads, that is several times worse.

- **A heavy dependency is imported inside the route or function that needs
  it**, never at the top of `app.py` or of a module `app.py` imports. numpy is
  cheap; scipy, matplotlib, sklearn, pandas and h5py are not.
- Guard it the way `dspca.py` guards sklearn: a machine that lacks it loses
  that one tool, not the whole server.

*(Being moved; `app.py` is shared with other in-flight work.)*

### Nothing at boot that is not on screen

1.3 MB of JSON arrives before the first screen settles — `/api/notes` alone
is 443 kB and `/api/sync/status` 405 kB, and neither is needed to draw it.

- Boot asks for what the first screen shows. Everything else is fetched when
  the view that needs it opens.
- A list endpoint sends what the list draws. The full record comes when a row
  is opened.

### Reachability is a cached fact

Every registry read used to call `isdir` on all 1,846 known paths one after
another, then `getmtime` on the reachable ones again — two network round trips
per netfiles path, every read.

- **One `os.stat` answers both questions**, cached for 30 s
  (`sessreg.is_here`). A drive plugged in shows up within the TTL.
- **Ask in parallel**, never one path after another.
- **A drive or share that is not there is asked once**, not once per path it
  holds — with one real path tried before a share is called dead, so a share
  that will not list its top cannot hide its recordings.

Measured: every read after the first went from ~0.5 s to ~0.11 s on the lab
LAN. The cost removed is round trips, so over a VPN the gain is larger still.

**Unmapped drive letters are not the problem**, and it is worth knowing why:
Windows fails them instantly. The cost was per-path latency on a share that
*was* there.

### A view pays for itself, and only itself

A view's time is often spent on requests that belong to a different view —
ToolKit's bad-channels poll turning up while the Event Bank is open, `/api/
devices` (1 s) during Pipeline, `/api/toolfeed/bad` during Results.

- **Every poller stops when its view is hidden** — that is what a view's
  `onHide` is for (§6b checklist) — and when the window is in the
  background (`document.hidden`).
- **A cloud round trip is never on the path to drawing a view.** Presence,
  devices and sync fill in after the view is up; the view does not wait for
  them.

### One request per question

Results and Misc make **61–66 requests per visit**, one per thumbnail.

- A list that needs *n* small things asks for them in one request, or asks
  only for the ones scrolled into view.
- Long lists draw the rows that are visible, not all of them. Sessions spends
  about 230 ms repainting 400+ cards it could not show at once anyway.
- A change repaints the row that changed, not the whole view.

### What is still to be measured

Two suspects cannot be tested on the lab machine, and are written here so
they are not forgotten:

- **GPU effects.** Six `backdrop-filter` and four `blur()` rules, and eleven
  infinite animations, are near-free on a lab GPU and paid on every repaint on
  a laptop's integrated one. Headless Edge draws without a GPU, so only a run
  of `_dev/perf.html` on a real laptop can say. Until then: **no new
  `backdrop-filter`**, and an infinite animation pauses when it is off screen.
- **The VPN.** Every number above was taken on the lab LAN. The laptop run on
  and off the VPN sets the budgets; they are not guessed.

### When you add something

- [ ] Heavy imports inside the function that uses them
- [ ] Nothing fetched at boot that the first screen does not draw
- [ ] Pollers stop in `onHide` and in a background window
- [ ] No cloud call on the path to drawing the view
- [ ] One request per question; long lists draw what is visible
- [ ] No new `backdrop-filter`
- [ ] `perf_baseline.py` before and after, and the number moved
