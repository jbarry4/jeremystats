# The GUI constitution

How this interface is built, so the next feature looks like it belongs in it.

Most of what follows is not new. The application already does these things —
they were written down in code comments, or in one module and not the next,
which is why an audit found the same control drawn several slightly different
ways under several names. This is the same set of beliefs, in one place, where
somebody can read it *before* writing the next tool rather than after.

Every rule cites the code that proves it. Where a rule exists because
something broke, the counter-example is named — those are the useful half.

> **Status.** Sections 1–5 and 7–9 describe the application as it is and are
> in force now. Section 6 describes shared compositions that are still being
> built; until it is filled in, follow section 1 and copy the nearest
> well-behaved neighbour.

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

*Being built. `stepHeader`, `field`, `workbenchCard` and `analysisRun` will
live in `web/js/ui.js`; this section will say what each contains and in what
order, with Braces-vs-X-ray and Checkup-vs-StrataScope as the worked
before/after. Until then, follow §1 and copy the nearest well-behaved
neighbour.*

---

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
