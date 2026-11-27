# room-sets-lineage

_What each Extraction Room set is built from (workflow → pools → X-ray Many folder → room version), checked event by event 2026-11-13; why the "CTL Baseline" set holds PTEN._

On 2026-11-13 the user asked for a data integrity check. They thought the "CTL Baseline … 10% Grace" set should hold no PTEN.

**Why it held PTEN.** In a DS workflow's name, "CTL Baseline" names where the BORDER is drawn, not which events are kept.
- The border is drawn around the CTL Baseline v2 (Optimized parameters) pool `07cdcb084c86`: 9 CTL recordings.
- It is applied to the CTL & PTEN Baseline v2 pool `3561fc988afd`: 18 recordings.
- So PTEN events inside the CTL border are kept. That is the design.

**The sets as of 11-13** (room artifact `980b57eab496`):
- **v6, the Halo set.** Folder `xm-f6c45faefb`; source Ambiguous `6fa7fef7b7a3` v3.
  - It holds 4,824 events: 4,467 inside the DS border only, plus 357 captured by the DS halo. Nothing else is in it.
  - Its borders are the **5%** Snaps: DS `178daabb125c` v3 and P-spike `4e5ce690d4b1` v2. They are not the 10% border.
- **v7, PTEN and CTL Baseline.** It replaced v5.
  - Workflow `4a29af93e601` ("PTEN and CTL Baseline (Optimized Paramters/Snap/10% Grace[Extraction Room]))"); the user's spelling is kept. It was run unbanked.
  - Folder `xm-12427c99f8`.
  - Its events are identical to `bac8eaf5dfa8` v3: 4,201 events, 1,965 CTL and 2,236 PTEN.
  - The old folder `xm-500fa6c3c5` is archived in the room. Shahriar's two hand bands were copied to the new folder.
  - 24 of its events sit inside the P-spike border too. A DS workflow never consults the P-spike border.
- **v8, No P-spikes (the user asked, 11-13). It replaced v7, which is archived.**
  - Name: "PTEN and CTL Baseline (Optimized Paramters/Snap/10% Grace[Extraction Room; No P-spikes]))".
  - It is Ambiguous workflow `a7eee6a6ca9f` v2, no halo. It uses DS `4a29af93e601` v2 (10%) and P-spike `4e5ce690d4b1` v2 (5%), with target `3561fc988afd`.
  - Its DS side (class "ds") is 4,177 events: v7 less the 24 events classed "both" (22 PTEN, 2 CTL).
  - Folder `xm-1d6cfcdd3d`. Seven recordings were re-read; the bands were carried over.
  - Every card's verdict is unchanged.
- **The "strict" recipe:** an Ambiguous run with no halo, keeping only its DS side. A plain DS workflow is not strict.
- Every card's read stamps equal the run's kept stamps exactly: no duplicates, nothing missed.

**How to apply:**
- Rerun the integrity check with `scratchpad/integ1.py` and `integ2.py`. The scratchpad does not persist, so rebuild the check this way:
  - `_xm_folder` members;
  - each read's `rows[].stamp_s`;
  - a cross-tab of the run `cols`.
- Calls and bands are keyed per folder (`room|folder|gid`). Replacing a set means copying them over.

Related: [halo-biteline-impression-decisions](halo-biteline-impression-decisions.md), [xray-many-decisions](xray-many-decisions.md), [rootcanal-workflow-decisions](rootcanal-workflow-decisions.md).
