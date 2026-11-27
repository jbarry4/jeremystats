# ds-pten-halo-and-strict-sets

_2026-11-20: the two DS/PTEN event sets are "Halo" and "Strict" (never "No P-spikes"); room v9/v10 after dedupe; m21 stays in the ML with no DS type._

The user named the two event sets (2026-11-19): **Halo** and **Strict**. "No P-spikes" was confusing because both sets remove P-spikes.
- **Halo** = workflow 6fa7fef7b7a3 (5% CTL DS border 178daabb125c + halo, minus the P-spike border 4e5ce690d4b1). Extraction Room "Dentate Spike" **v9**. Battery slot `v6`.
- **Strict** = workflow a7eee6a6ca9f (10% grace border 4a29af93e601, no halo, minus the P-spike border). Room **v10**. Battery slot `v8`.

After the 11-19 dedupe (103 duplicate stamps marked Garbage) m21 has 70 events and no winning classifier. The user said to include it anyway ("I don't see any reason not to include m21"). `backend/er2/amber.py` now keeps recordings with no winner; their events carry no DS type. ML runs: r006 (Halo, 16 mice), r007 (Strict, 16 mice).

Lab copies of the results go to `_Jarvis\Lab Figures\<name>_MMDDYY` (e.g. DS_PTEN_112026). That folder is tracked in the public repo.

**2026-11-21 (PROJECT EVOLVE phase 3):** both sets were re-made from Root Canal bundles (Halo bundle `a9cf6f2c30c2`, Strict `5469cb7ad2ae`): room **v11** (Halo, folder `xm-b2d963ef1c`) equals v9 and **v12** (Strict, `xm-7d6c8cfb0b`) equals v10, recording for recording; v9/v10's folders are archived. Battery slots and ER2 runs still name the old versions; the events are the same.

**Why:** the set names and the m21 call are the user's; reports must use them.
**How to apply:** say Halo/Strict in every report. Do not drop recordings for lacking a winner. See [ds-pten-m6-excluded-and-figure-rules](ds-pten-m6-excluded-and-figure-rules.md), [extraction-room-2-decisions](extraction-room-2-decisions.md), [m1-lock-undone-by-panning](m1-lock-undone-by-panning.md).
