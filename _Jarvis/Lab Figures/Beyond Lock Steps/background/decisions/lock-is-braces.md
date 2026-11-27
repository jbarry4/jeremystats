# lock-is-braces

_Lock (Confluence step 3) is Braces built twice via makeBraces(cfg) since 2026-10-22; Panning-only input; origin groups (Incisor only/Merged/Doppler only) choose what moves, the rest held; DS band default; pickers are tiles, never radios_

Decided by the user (Shahriar, with Rain's feedback) 2026-10-22 to 10-26:

- **Lock copies Braces.** It is a "carbon copy" of Braces (One, Many, Alignments, review), not Eye's panel. braces.js is `makeBraces(cfg)`; `BARRY.braces` and `BARRY.lock` are its instances, and both are registered in `BARRY.modes`.
- **Eye too (2026-10-30).** The user asked: "update the Eye gui to match the flow and steps of braces". `BARRY.eye` is a third makeBraces instance, with mode `eye`, type `ied`, no band choice (the server uses the IED band for ied) and CSD/Voltage/Slope. eye.js `makeAligner` is no longer constructed. Braces' `setTypes` is now `ds` only.
- **Held is a warning, not a wall (2026-10-30).** The user said: "two spikes side by side, and I am not allowed to garbage this one?" `lockedSay(n, what, go)` offers "Garbage/Move it anyway". The decide call carries `override` and the server keeps it on the call (`bracesset.decide`).
- **The review centres on `r.was`**, not the proposal (2026-10-30), so a ±window span shows the whole search window.
- **A first alignment that moves nothing is still a version** (`unmoved_first`). Otherwise Root Canal waits for ever ("accepted as vnull"). Autobank on leave skips it; the last call or Bank it writes it.
- **Input is Panning's results only.** Unsorted pools aren't offered, and Junction versions are greyed in the tree.
- **Origin groups decide what moves (2026-10-26).** The three groups are Incisor only (`incisor`), Merged (`both`) and Doppler only (`doppler`).
  - Lock lines up the ticked groups and holds the rest. Held stamps never move or relabel, and each fills the one peak it occupies (nearest within the merge window, 20 ms).
  - The groups replaced the Braces lock switch. "Braces ✓ N" stays as a clearly labelled hint.
  - Default: all three ticked. After that, use the set's last run (`request.hold`), else the last setting Lock ran with (pref `lock_hold`).
  - Many has its own I/M/D switches on each row.
  - Rain's reason: this sidesteps not knowing whether Braces was run.
- **Fill rule (2026-10-23).** Free stamps take the largest peak left in their ±200 ms window. One pushed off a held peak, with ≥2 peaks left, is flagged `locked_peak`.
- **Band.** Lock aligns through the DS band (5–100 Hz + notch) by default; the IED band is an option (`band_kind`). The review's traces have DS / IED / Both.
- **Braces detection broke because the version mark didn't sync.** cloudsync's slim versions dropped `aligned` and `tag`. They sync now, and `eventbank._fold_aligned` recognises older versions by the "Aligned to the mean magnitude over" note.
- **Autobank runs once.** Checkup, Spotter and Panning bank by themselves only when every event is first decided (`auto: true`, enforced on the server, with a set mark `autobanked`). They never bank on Leave.
- "Incisor outputs / Doppler outputs" are the user's internal terms. Never rename UI labels to them.
- Set pickers: no radio-button lists. Use recording, then a set menu of cards, then the version button.

**How to apply:** a change to one aligner's panel lands in braces.js for both. Words that differ go in `cfg.words`. Related: `ui-v2-decisions` (a note not copied here), [the-confluence-decisions](the-confluence-decisions.md).
