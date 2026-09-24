# The GUI constitution

How this interface is built, so the next feature looks like it belongs in it.

Most of what follows is not new. The application already does these things —
they were written down in code comments, or in one module and not the next,
which is why an audit found the same control drawn several slightly different
ways under several names. This is the same set of beliefs, in one place, where
somebody can read it *before* writing the next tool rather than after.

Every rule cites the code that proves it. Where a rule exists because
something broke, the counter-example is named — those are the useful half.

> **Status.** All in force. §6 covers the shared compositions that exist
> today (`analysisRun` is still to come and says so); **§6b is the one to read
> before building a new tool, bundle or Xplorefinder mode** — it is about the
> machinery rather than the look, and most of it is there because getting it
> wrong loses somebody's work quietly.

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
them.

**A bundle must remove its members from the flat tool list below it.** This is
the rule with the longest comment in `toolkit.js` and it is worth reading:
a bundle that does not is "a menu that describes one thing twice and makes
the reader work out that it is one thing."

Every step gets a `stepHeader` with its `step` set (§6). The header is where
somebody arriving at step 3 learns there are four.

### An Xplorefinder mode

A mode is entered with a gid and takes the whole interface:

```js
BARRY.yours.enter(gid)   →  true/false
BARRY.yours.exit()
BARRY.yours.active       //  a GETTER. Calling it throws.
BARRY.yours.rebind(sess) //  a reopen replaces the session object
BARRY.yours.state        //  what a pop-out or a deep link needs
```

**One mode at a time, and `enter` is responsible for that.** Both modes take
over the panes, the keyboard and the aid window. Entering one on top of the
other left two toolbars stacked, two sets of key handlers fighting over the
same presses, and an aid window belonging to whichever got there first. So:

```js
if (BARRY.curate && BARRY.curate.active) BARRY.curate.exit();
if (mine) exit();          // re-entering: start clean
```

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
- [ ] `check_classes.py` clean; `ui_baseline.py` diff is only what you meant
- [ ] A `_dev/` harness, listed in `_dev/README.md`
