# X-ray (dspca) — UI work order

*For whoever is working on `web/js/dspca.js`. Temporary; delete when the list
at the bottom is empty.*

A UI consistency pass is running across the GUI in parallel with your work.
It has deliberately not touched `dspca.js`. This is what it would have done,
so you can do it while you are already in the file — and the rules to follow
so the next change does not reopen any of it.

**Read `web/GUI-CONSTITUTION.md` first.** It is short, it is the spec, and
everything below is an instance of it.

---

## Already fixed — thank you

These were real and they are gone:

- `.spinner` — the loading card was rendering an empty `div`. There has never
  been a `.spinner` rule; the only occurrences of the word in `app.css` are
  comments.
- `.input` on the two dropdowns — no such rule, so they fell back to bare
  `select`. **This was the reason step 4's fields looked nothing like step
  3's.**
- `btn small` ×12 — no rule, so they rendered full size beside the 84 that
  wrote `btn sm` and shrank.
- `btn primary` — `.primary` matches nothing; `.btn` is already the filled
  style.

`python tools/check_classes.py` now reports **zero naked elements** across the
whole application, for the first time. Please keep it there.

---

## What is left in this file

### 1. `.dp-lab` is now dead CSS

You moved the field labels to `.section-label`, which is right — it is the
house label, 164 uses across 25 files. But `app.css` still carries:

```css
.dp-lab { font-size: 11px; color: var(--text-3); }
```

Nothing applies it any more. Delete the rule.

### 2. `section-label` + `style: 'margin-top:0'` — three in this file, 32 across twelve

`.section-label { margin: 22px 0 10px }` is wrong whenever it is the first
thing in a card, which is nearly always, so call sites paste an inline style
to undo it. `dspca.js` does it at **[line 619](web/js/dspca.js#L619)**
(`margin:0`), **[912](web/js/dspca.js#L912)** and
**[1387](web/js/dspca.js#L1387)**.

**Do not add more.** A single rule removes all 32:

```css
.card > .section-label:first-child,
.modal .section-label:first-child { margin-top: 0; }
```

If you want to land that, do — it is on my list otherwise, and whoever gets
there first should just say so in the commit.

### 3. `.dp-intro` is a second tool header

Braces (step 3) builds its header as `.card.br-intro` › `.section-label` +
`p.hint` — ALL CAPS, boxed in a card, the step number inside the title text.
X-ray builds `.dp-intro` › `strong` + `.dp-step` pill + `.hint` — mixed case,
unboxed, the step in a separate chip.

Two adjacent steps of the same bundle, two unrelated header primitives. There
are **twelve** bespoke `*-head`/`*-intro` classes across the app, between them
using four alignments, seven gaps, three title elements and three subtitle
classes.

**Leave this one alone for now.** A shared `stepHeader({ title, step, blurb })`
is coming in phase 6b and Braces and X-ray adopt it together — that is the
point of it. Just do not add a third variant in the meantime.

### 4. Adopt `BARRY.ui` for new controls

`web/js/ui.js` landed today. It emits the classes `app.css` already defines —
`_dev/uikit.html` measures every kind and size against the hand-written markup
it replaces, attribute for attribute, so adopting it changes nothing on
screen.

```js
BARRY.ui.button({ kind: 'primary', text: 'Read a batch…', onclick: … })
BARRY.ui.button({ kind: 'ghost', size: 'sm', text: 'Close', onclick: … })
BARRY.ui.searchField({ placeholder: 'Search…', oninput: … })   // debounced
BARRY.ui.actions([cancel, primary])        // right-aligned, primary last
BARRY.ui.modalFoot([openIt], [cancel, primary])
BARRY.ui.seg([['a','One'],['b','Two']], current, onPick)
BARRY.ui.chip('24 / 24')
```

`kind` defaults to `ghost` on purpose: a surface gets one primary, so the
filled button is the one you ask for by name. `size` is `'sm'` or nothing —
`'small'` **throws**, naming the fault, which is the whole reason it is a
function.

No need to convert the existing 22 buttons in a sweep. Use it for anything new
or anything you are already rewriting.

### 5. Sixteen inline styles

Not urgent, and not worth a pass of its own. When one is doing a job a class
should do — spacing, alignment — move it. When it is a computed value
(`width: <n>%` on a progress bar) it is fine where it is.

---

## The rules that matter most here

Full detail in `web/GUI-CONSTITUTION.md`. The ones this file keeps tripping:

**Buttons.** `[navigational] [.spacer] [Cancel · btn ghost] [Primary · btn]`
— **primary last**, right-aligned. One primary per surface. Destructive takes
`.danger` and never the primary slot. `.btn.sm` in headers and toolbars;
`.mini` for an action inside a row.

**Waiting.** `loader(label, sub)` for one wait · `stepLoader(label, steps)`
only when the stages each take *real* time · `BARRY.skeleton.into(...)` for a
list about to fill. **Never a bespoke spinner.** A `stepLoader` whose second
and third dots light for zero milliseconds is a progress bar lying about where
the time goes — if there is one slow stage, use `loader`. Say the size of the
job where you can.

**Sizes and colour.** Use the tokens in `:root` — `--fs-115`, `--r-6`,
`--sp-8`. Never a literal colour: `#154734` *is* `--uvm-green`. Semantic
tokens (`--ok`, `--warn`, `--err`) for meaning; `BARRY.hues()` for things that
only need telling apart.

**Naming.** Pick a prefix that names **one** feature and check nothing else
owns it. `.fb-actions` was declared twice for two unrelated features and the
pipeline's folder bar spent months wearing the feedback panel's spacing.

**Words.** "Search…", not "Filter…"/"Find…". A placeholder says what you can
*type* — *"Type a mouse, session or date…"* — not what the box is.

---

## Before you commit

```
python tools/check_js.py         # all modules parse
python tools/check_classes.py    # must stay at zero naked elements
python tools/ui_baseline.py      # the diff must be only what you meant
python tools/harness_run.py dspca.html
```

**Run these from PowerShell, never bash.** Under bash Edge's `--dump-dom`
writes nothing on this machine, so every harness reports zero checks and the
whole suite reads as a clean sweep.

`ui_baseline.py` is the one worth understanding. It walks every view at three
widths and one short window and records every control's measured shape, every
composition's structure, container gaps, grid column counts and overflow. A
change meant to change nothing must produce an **empty** diff. If it prints
lines you did not intend, stop — that is the tool doing its job.

Two known-noisy things, neither yours: `curversion.html` fails 2 checks at
HEAD (it wants a demo set on the shelf), and the full 159-harness suite takes
about five hours, so run named harnesses rather than the lot.

**One warning.** Some harnesses write and delete Event Bank records and do not
always put them back — a run of `bank.html` and `spikeflow.html` deleted 29
real KCNT1 entries from `GUI_logs/`. Check `git status` after a harness run,
and `git checkout --` anything under `GUI_logs/` that shows as deleted.

---

## Do not touch

Some numbers in `app.css` are load-bearing alignment, not styling, and
`_dev/align.html` asserts sub-pixel agreement against them:

- `.pane-grid { gap: 1px }` — the hairline between the six probe panes
- `.ch-overlay .ch-lane.compact { height:12px; font-size:9px }` — the 9px
  *makes* the 12px lane
- `.ch-overlay .ch-lane.micro`, `.strata-rows.tight`, `.strata-rows.packed`

They are marked in the stylesheet. If you change one, `align.html` is the
check.

---

## Checklist

- [ ] delete the dead `.dp-lab` rule from `app.css`
- [ ] stop adding `style: 'margin-top:0'` next to `.section-label`
- [ ] (optional) land `.card > .section-label:first-child { margin-top: 0 }`
      and drop the three inline ones here
- [ ] use `BARRY.ui.*` for new controls
- [ ] leave `.dp-intro` alone until `stepHeader` lands
- [ ] `check_classes.py` still reports zero naked elements
