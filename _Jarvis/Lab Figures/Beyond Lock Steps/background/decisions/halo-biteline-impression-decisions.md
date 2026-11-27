# halo-biteline-impression-decisions

_2026-11-12 round: Halo (capture outside both), the new room round without X-ray, the Bite line split, Compare splits, Impression lock, Blob Analysis — the user's 20 answers._

Asked 2026-11-12, with the user's answers to my 20 questions.

**Halo** (Root Canal, Ambiguous)
- It is an option in the Ambiguous workflow's **Apply border stage**, not in the builder. ("not an initialization option in the making of the workflow")
- Rule: each border's gauge γ measures how far out an event is, in units of that border's own size about its centre (1 = on the border).
  - For an event outside both borders: it is captured by a side when γ ≤ reach AND it is margin× nearer that border than the other.
  - Otherwise, if it is within either halo, it is extended ambiguous.
  - Beyond both halos it is far out.
- Default is Balanced: **reach 2×, margin 1.5×**. Both are sliders.
- The halos are drawn as dotted grown borders in 3D and 2D.
- Apply it to "Ambiguous Dataset (Optimized Parameters/Snap)" **6fa7fef7b7a3 v2**. Save the result as its next version, with notes and full metadata (halo on, reach, margin).
- Its room set takes **DS-only + captured DS**. Nickname: "data rich, less specific".

**The new Extraction Room round**
- Sets:
  - that Halo result;
  - "CTL Baseline (Optimized Paramters/Snap/10% Grace))" bac8eaf5dfa8 v3. It is banked: 4,201 events, 18 recordings. The user's spelling is kept.
- Archive the Verified DS 5% (v1) and 10% (v2) sets. The new cards start **amber** (uncalled); the old calls stay with the archived sets.
- X-ray is skipped. Each card sets its depth band by **dragging on the average CSD**: click to centre, handles, double-click to reset.
- The default band covers the edges of the **2 bottom sinks**.
- The filter stays 5–100 Hz. Add a note that the blob analysis might be worth redoing with other filters.

**Bite line** (the new default DS1/DS2 split)
- It is a sink-overlap normalised cut: Bhattacharyya overlap and the Fiedler order. The line can be dragged along the order, with a cost curve and a sink raster.
- The sink representation is the user's: the negative side of the depth profile in the band, split into bumps at its zero crossings, keeping the **top 2 bumps**. Later on 11-12 these became the RECORDING's two humps, not each event's, because notched humps split; see [camel-hump-is-bookkeeping](camel-hump-is-bookkeeping.md).
- One line, so every event goes to a side.
- **Compare splits** has **all four** methods (Bite line, PCA no gap, PCA + gap, delta). Each is a full panel: its own line, the raster, DS1/DS2 CSDs, the 2-bump profiles, counts, the overlap score and "Use this".
- **Impression** is the locked state. It locks the **whole set at once** into one artifact version, and Blob Analysis opens from it.

**Blob Analysis**
- It is grouped:
  - per recording;
  - CTL/PTEN;
  - separable / not separable;
  - pick-and-choose, averaging any group with more than 2 recordings.
- Top and bottom blobs are the 2 bumps, with the upper one as top.
- All four kinds of numbers are measured:
  - peak, latency and duration (FWHM);
  - rise and decay (10–90%) and sharpness (peak ÷ area);
  - area;
  - depth spread at half peak (µm).
- Each number is measured per event, and the recording is the unit.
- Not separable recordings are one class, "DS, one kind", kept out of the DS1 vs DS2 comparisons.
- The histograms should show "what averages hide": per-event distributions with each recording weighted equally, a shift function (quantile differences), ECDFs, and a spread test.

**Compare across sets** (asked later the same day): a recording can be compared between two room sets side by side, e.g. m13 s2 in the specific 10% set against the rich Halo set.

**Done 11-12:**
- Halo built. Ambiguous Dataset 6fa7fef7b7a3 v3 = Halo 2×/1.5× (from v2). Its DS side was banked as a784d51b11a6 (4,824 events).
- X-ray Many folders for the round:
  - xm-500fa6c3c5 = CTL Baseline Snap 10% (bac8eaf5dfa8 v3);
  - xm-f6c45faefb = the Halo DS side.
  - `xraymany.inside_by_gid` takes ds+halo_ds for ambiguous runs.
  - Reading their recordings takes about 6 min each.
- New code:
  - backend/sinkcut.py (Bite line);
  - backend/blobs.py;
  - room routes in app.py: band, set_archive, impression(s), blobs, blobs/compare, blobs/all;
  - extraction.py "THE NEW ROUND" section (default_band, add_bite, direct_record);
  - artifact kind `extraction_impression`;
  - web/js/extraction_compare.js and extraction_blobs.js (register on `erRoom.ext`, using `erRoom.kit`).
- Direct arrays are cached as `GUI_logs/.cache/extraction/direct__*.npz`. Blob sets are cached as `blobs__<imp>_v<n>.json`.
- The room's v4 is the Halo set, fitted directly. On it, m13 s2 splits 345/8 under the Bite line; in the 10% set the same recording splits 127/160.
- The room's v3 is the 10% set, fitted directly. The old 5% and 10% sets are archived (pref `extraction_set_archive`).
- On the real 10% set, the Bite line's default (a 2% floor) often isolates a tiny side: 13/508, 11/286, 5/101.
  - These cards say "separate". The rest say "one family".
  - Offer the user a 10% floor, which matches X-ray's MIN_SHARE. Don't change it unasked.
- No Impression has been taken. The user locks in by hand.

**How to apply:** build in this order: Halo → room sets → Bite line → Compare → Impression → Blobs. Related: [extraction-room-decisions](extraction-room-decisions.md), [rootcanal-workflow-decisions](rootcanal-workflow-decisions.md), [xray-many-decisions](xray-many-decisions.md).
