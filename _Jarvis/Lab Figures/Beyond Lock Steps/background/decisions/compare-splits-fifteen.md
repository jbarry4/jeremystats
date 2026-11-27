# compare-splits-fifteen

_Compare splits since 2026-11-13: 5 methods (delta middle added) × 3 rows (both humps / top only / bottom only) and a low-contacts toggle that is a look only._

The user asked on 2026-11-13:
- add "Delta Middle", which takes the middle of each hump rather than its greatest sink;
- give every method two more rows, one on the top hump alone and one on the bottom hump alone;
- add a toggle that excludes the low contacts.

**What each row means.** These come from the user's words.
- Bite line: one hump's sink only.
- PCA: PCA on that hump's contacts.
- PCA + gap: the gap is replaced by the channel position.
- Delta and Delta Middle: the position, sorted lower to higher.

**My choices.** The user didn't specify these; I chose them and said so.
- A hump's middle is halfway between its edges at **half its depth** (`MID_LEVEL`), so a notch doesn't move it. The alternatives were the zero-crossing edges or the centroid.
- Rows use the Bite line's humps (`hump_cut`).
- Hump rows are also scored on their own hump (`scores.hump`), as well as on the one yardstick.
- Low = more than 2% below the median gain AND more than 5 MADs (`LOW_FRAC`, `LOW_MADS`), using the cubic stencil.
  - A 3% cut missed m28's 44 and 52, and those two were its notches.
  - Contacts next to an already-bad contact are not judged. A stretched stencil reads about 4% low on its own, and that made a false 60/57.
  - Contacts are removed one at a time.
- A left-out contact is REBUILT by the cubic (`rebuild_contacts`), not by the linear bad repair. The linear repair zeroes the CSD there: with it, m28 kept 143 of 143 notches; with the cubic and all five contacts out, 1.
- Result: the Bite line is robust to the low contacts (m22 183/19 → 182/20; m28 11/286 SI 0.85 → 0.86). PCA and delta move more.
- The low toggle is **view-only**: Use this is disabled while it's on, and the server refuses a save made with `low`.

**Code:**
- `extraction.add_humps`, `SPLIT_METHODS` (15), `split_base`/`split_row`, `low_contacts`, `keep_fit`.
- `sinkcut` sink `"one"`, `fit(sink_nums=)` and `view(slim=)`.
- Cached split arrays without `x_delta_mid` are refit once, because the hump PCA needs `feat`.

**Not done (offered):**
- Marking 25 and 49 (plus 62, and 5 on m28) bad for real.
- The 10% Bite floor.

Related: [camel-hump-is-bookkeeping](camel-hump-is-bookkeeping.md), [halo-biteline-impression-decisions](halo-biteline-impression-decisions.md), [room-sets-lineage](room-sets-lineage.md).
