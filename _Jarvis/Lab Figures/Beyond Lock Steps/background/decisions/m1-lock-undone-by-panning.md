# m1-lock-undone-by-panning

_Audit 2026-11-19: every battery/ER2 event comes from the newest Lock version of its Confluence entry, except PTEN m1 s2, whose Lock (v2) was undone 6 min later by Panning's bank-on-leave (v3 = v1)._

The user asked on 2026-11-19 whether the Root Canal workflows, and everything built on them, use the latest Lock results. Audit scripts: scratchpad `aud1.py`–`aud4.py`. The scratchpad does not persist.

**The chain.** Battery sets v6 and v8 come from room folders, then workflows `6fa7fef7b7a3` v3 and `a7eee6a6ca9f` v2, then pools `07cdcb084c86` v2 and `3561fc988afd` v2.
- Every pool member is the recording's Confluence entry (type `pooled`, Junction → Panning → Lock), at its newest version. None is an Incisor-only `ds` entry.
- Battery times match the pool stamps within 0.5 ms, which is the read snapping to the 1 kHz sample.
- The P-spike border's 5 Eye sets are pinned at their newest version.

**The exception: m1 s2, an IED− mouse.**
- Entry `bfa98498290b`. Lock v2 (2026-10-23 13:28) moved 87 stamps.
- At 13:34 "Banked on leaving Panning" wrote v3, and v3's stamps equal v1's: the alignment is undone.
- So 80 of m1's 188 v6 events sit more than 1 ms from Lock's position, 29 of them more than 20 ms.
- The bank-on-leave was stopped on 10-26 (see [lock-is-braces](lock-is-braces.md)).
- This had not been fixed as of 11-19. A fix means re-banking Lock's v2 as the newest version, then re-running the pools, workflows, room, battery and ER2. That is the user's call.

**Secondary finding.** 86 pairs of good stamps sit under 1 ms apart in these pooled entries. They are already present in Panning's v1, so Lock did not make them. 38 such pairs are in v6.

**Root Canal opened in The Dentist** shows only Incisor `ds` sets. The Confluence's Lock sets appear only when Root Canal is opened from The Confluence (`inConfluence()`).

Related: [the-confluence-decisions](the-confluence-decisions.md), [room-sets-lineage](room-sets-lineage.md).

**Phase 1 done 2026-11-19.**
- I replayed Lock pass `br1f1b0830ec`, using its own index moves, onto v3 with `BANK.align`. That wrote v4 `br-a0701425f4`, whose spikes are identical to v2's. The script is scratchpad `fix_m1.py`.
- The write was made outside the app's process. The running Jarvis picked it up with no restart, because the bank re-reads a shard when its mtime changes.
- `align()` did not bump `rec['version']`; that is fixed in eventbank.py.
- Still to do: re-read m1 and resave pools `3561fc988afd` and `105b40acbbb0`. Then rerun the workflows, the room, the battery and ER2.
- The workflows show no 'stale' flag until the pool is resaved, because they pin pool v2.

**Phase 2 done 2026-11-19**, through the running app's HTTP API with no restart (scratchpad `p2.py` and `p2_compare.py`).
- m1's read of the Lock stamps was already cached: `d029ea158841`.
- Both pools were refit and checked: the refit of v2 reproduced the saved pool exactly. They were then saved as v3: `3561fc988afd` and `105b40acbbb0`.
- The workflows were rerun with refresh and left unbanked:
  - `4a29af93e601` → v3;
  - Halo `6fa7fef7b7a3` → v4;
  - No P-spikes `a7eee6a6ca9f` → v3.
- In every run, the other 17 recordings came out identical.
- m1 under the 10% DS border: 158 inside / 33 outside before, 157 / 34 after. In the Halo set: 188 before, 188 after. In No P-spikes: 157 before, 156 after.
- A workflow run's `diff` is keyed by time, so m1's moved stamps show as absent/present pairs. To compare runs, pair the events through Lock's moves.

**Archived 2026-11-19, at the user's request:** everything in Root Canal outside the current chain (scratchpad `p2_archive.py`, using shared prefs merged per id).
- 19 workflows and 13 borders were archived. Two bank entries went with their workflows, as the UI does it: `ad9b1441cdaa` and `c42d07d8260d`.
- Still on show:
  - pools `3561fc988afd` v3, `105b40acbbb0` v3 and `07cdcb084c86` v2;
  - workflows `a7eee6a6ca9f` v3, `6fa7fef7b7a3` v4, `4a29af93e601` v3, `178daabb125c` v3 and `4e5ce690d4b1` v2;
  - their 3 borders.
- The Meta workflows have no archive feature, so they were left as they are.

**Duplicate stamps fixed 2026-11-19.** The user looked at the pairs (PDF `DS_PTEN_figures_2026-11-16/duplicate_check`).
- The rule: Spike neighbors under 10 ms apart are one event. Neighbors 10–20 ms apart are two real events (the user said they "are fine").
- In each pair, the stamp with the largest CSD sink (±2 ms) stays a Spike, and the other becomes Garbage. On a tie (the same sample), the earlier stamp stays.
- This gave 103 Garbage across 14 sets, all of them pairs (no triples). Each fix is a new version with version_tag "dedupe" (scratchpad `dedupe.py`).
- Source: a ±200 ms Braces pass on the Incisor sets put two stamps on one peak. Braces' exact-time clash check misses stamps a hair apart.
- A forced `/api/rootcanal/read` was needed: an unforced read says "cached" through a covering superset read, but the pool refuses that.
