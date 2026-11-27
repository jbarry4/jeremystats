# never-truncate-text

_Shahriar's rule for BARRY GUI - never cut text with an ellipsis; shrink the type or reflow the layout instead._

"no `...` never truncate — only shrink the text or move everything around if
you have to."

**Why:** the part that gets cut is usually the part that distinguishes one
thing from another. Four Event Bank entries from one session read
"m33s8jun14 — Denta…", "m33s8jun14 — Garba…" — identical up to the ellipsis,
and the only differing word is the one removed.

**How to apply:** no `text-overflow: ellipsis`, no JS `.slice(n) + '…'` in
any user-facing label. Fix it by giving the text a second line
(`white-space: normal; overflow-wrap: anywhere`), restructuring the row into
two lines, shrinking the font, or widening the column. Verify by measuring
`scrollWidth > clientWidth` in a harness rather than by eye — that is the
DOM saying text is hidden. See [measure-dont-guess](measure-dont-guess.md).
