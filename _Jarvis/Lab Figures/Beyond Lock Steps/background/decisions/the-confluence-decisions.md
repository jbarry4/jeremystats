# the-confluence-decisions

_The Confluence bundle (Incisor + Doppler pooled): the user's 10 answers and the calls made building it, 2026-10-14._

The Confluence was built 2026-10-14 (CHANGELOG 2026.10.14.8). It is a ToolKit bundle under The Dentist and The Storm, with a stream drawn into it. Its steps are Junction (pool them), Panning (sort them), Lock (line them up) and Root Canal (tease them apart).

User's answers:
- Inputs are banked entries, newest version by default, other versions through the version tree.
- Merge rule: time only, on any channel, within a window that can be adjusted. It was 5 ms; the user changed the default to **20 ms** on 2026-10-20, and another session made the change.
- Curation sets created from 2026-10-20 on are keyed per bank entry as a compound kind, `<kind>.e<entry_id>`, for example `ied.e3b3111be3118`. Existing plain `ds`/`ied`/`pooled` sets are unchanged. Compare kinds through curation's `kind_of()`/`entry_of()`, never with `==`.
- A merged event keeps **Incisor's** stamp; Doppler's is kept as `pair_t`. (Since 2026-10-19, Doppler's when chosen — see below.)
- Labels are Spike, Garbage and Flag.
- Colour by origin; an event both detectors found is two-tone.
- Passes: All, Merged, Incisor only, Doppler only.
- **Merge only.** Z undoes a merge; there is no split.
- The stream always flows gently, and holds still under reduced motion.

Calls I made:
- The type and kind id is **`pooled`, not `spike`**. The bank already has `spike` entries (unit spikes), and there is a 300 Hz `spike` filter preset.
- Pairing is one to one, nearest first. Anything labelled Garbage stays out of the pool.
- Panning's merge keeps whichever event carries Incisor's time, so no stamp ever moves. An undo puts the other event back under a new id, because the old id was tombstoned.
- Lock is Eye's panel with a different config (`makeAligner`). Pooled sets are aligned through the `ied` band (`_kind_band`).
- Root Canal on a pooled set **names** each event (`rc_name`) as a new version and removes nothing. The bank now mints a version when only `rc_name` changes.
- Root Canal knows which bundle it was opened from through `toolkit.via()`.
- Origin colours are the tokens `--o-incisor` and `--o-doppler`, which map to `--c3` and `--c4`.

Added 2026-10-19, at the user's request:
- **Merge to Incisor or to Doppler.**
  - Junction has a "Merged events keep" switch.
  - Panning has M (Incisor's time) and D (Doppler's time).
  - The default is still Incisor's.
- **What a Doppler-kept merge stores:** `start` = Doppler's time, `pair_t` = Incisor's time, and the event carries `stamp: 'doppler'`.
  - `stamp` is carried through every path that carries `origin`/`pair_t`: eventbank add, curation create and bank, the from-bank facts, and the Root Canal stamps.
  - Readers must use stampOf(): a `both` event without a stamp is Incisor's.
  - D is refused when neither event carries Doppler's time.
  - Pools dedupe on `keep` too (an old pool with no `keep` counts as Incisor's).
- **The aligned label.** Junction says "✓ aligned" / "not aligned" on every input: the list, each side, the version tree, the pool line, and Many.
  - It comes from the bank's `aligned` stamps: Braces, Eye, Lock.
  - `_cf_aligned` treats a version as aligned when an alignment wrote it, or when it descends on that line from one that did.
  - The pool's params record `ds_aligned`/`ied_aligned`.
- **Panning bulk and list.**
  - Bulk: "Label many…" picks origins × current decision → one label, as one `{labels:{}}` write and one Z.
  - List: "List all…" (key L) is Checkup's list plus origin pills and a "label the N shown" bar.
- The Panning workbench/step page was another session's job that day: Checkup's workbench generalised in toolkit.js.

Not built yet:
- Root Canal's multi-recording "Pooled" view does not take pooled-type sets.
- Panning has no "+ New category".

**Why:** this pins the merge semantics and the type id. Changing either later would silently fork the data.

**How to apply:** keep these semantics when extending The Confluence. Tests: `tools/test_confluence.py`, `tools/test_confluence_routes.py`, `_dev/confluence.html` and `_dev/panmany.html` (merge-to, label many, list, Junction aligned).

Related: `apipost-is-a-const-stub-fetch` (a note not copied here), [bank-identifies-events-by-time](bank-identifies-events-by-time.md).
