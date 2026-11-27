# rootcanal-workflow-decisions

_Root Canal "Workflow" tab (asked 2026-11-05) — three separate workflows (verified DS / verified P-spikes / ambiguous), Define → Apply → Extract, and the user's 10 answers._

The user wants a **Workflow** tab in Root Canal: each workflow is Define border → Apply border → Extract, with a 3D view of each stage. Workflows are built, archived and versioned. Results go to the Bank, are easy to rebuild, open in Root Canal, and trace every event back to its recording, time and waveforms.

The three workflows:
1. **Verified DS.** 5%-grace border around DS from pool "PTEN CTL Baseline Full Incisor"; applied to "PTEN ALL PTEN Baseline Full Incisor"; extract the DS inside the border.
2. **Verified P-spikes.** 5%-grace border around the Bank's "IED spikes (hand-sorted)" import sets (all hand-sorted, per the user); applied to the same target; extract the P-spikes inside the border.
3. **Ambiguous.** Both borders on the same target; **view only for now**, and let the user choose what to do with them. Not auto-banked.

Answers (2026-11-05):
- Grace = the existing one-class envelope ("border around DS", rcborder): 5% of the events. Don't call it "training".
- Inside both borders = ambiguous.
- Bank: **one entry for the whole pool** per output (not per recording). Each recording's own DS set version tree gets a **side branch** saying its events went into that Root Canal entry.
- Pinned input versions; flag out of date and offer "Run again". Never rerun by itself.
- **Three separate workflows**; W3 picks W1's and W2's borders.
- Synced like pools (artifacts). Archive hides it everywhere and archives its bank entries (nothing deleted).
- Trace-back: all four — waveform + CSD, Open in Xplorefinder, history (Incisor run → Braces version → pool/border/workflow version), and the three numbers vs each cut-off.

**Built 2026-11-05 (changelog 2026.11.05.5).**
- backend/rcworkflow.py plus the /api/rootcanal/workflow* routes in app.py (after the border routes); web/js/rcworkflow.js (the third view in Root Canal's view bar); harness web/_dev/rcworkflow.html (57 checks, fixtures).
- Each run saves its border as an ordinary rootcanal_border ("DS border · <name>") and banks with pipeline "Root Canal workflow".
- The P-spike prepare step (retime → Eye align + commit → Root Canal read) has never been run for real. 2 sets need retiming: m5 s7 and m34 s8, the latter up to 121 ms.
- Harness flake fixed: draw on a timer as well as rAF, because the runner's virtual time withholds frames.

**2026-11-06:**
- A fourth kind, **Pooled PCA** (kind 'pca'): pools made one pool (re-clustered with fit_pool), then a PCA of amp/HF/hw. The dots are coloured by the one-pool call, by each pool's own call, or by the verified borders. It is view-only; the 3D view sits beside the 2D PCA; Xplorefinder follows every dot clicked.
- Ambiguous is **purple** (--call-amb / --call-amb-2), never the amber --warn ("that ugly brown").
- **"Panning output"** means each recording's panned **pooled** entry (Incisor+Doppler, type 'pooled'), at its newest version. Pool candidates now include type 'pooled'.
- The v2 dataset lives in the folder "PTEN Panning Complete v2 (Version Bug Fixed)". It has three pools: CTL Baseline v2, PTEN Baseline v2, and CTL & PTEN Baseline v2. Everything else in Root Canal was archived (prefs keys rootcanal_pool_archive and rootcanal_single_archive, plus folder archived:true). The four workflows were rerun on v2 without banking.
- The grace bug: on a small group the even quantile trim left nothing out (39 P-spikes, 5% → 0 outside). Fixed with rcborder.box_for, which peels the most outlying events until floor(grace × n) are outside.

**The P-spike sets (2026-11-12):**
- Every P-spike workflow draws its border around 39 stamps from 5 sets: m3 s2, m5 s2, m13 s2, m28 s2 and m34 s5. These are exactly the PTEN sessions in the Baseline v2 pools.
- The other sessions of those mice (s7, s8, s17) are not in the pools, were never aligned, and are unticked.
- Prepare all aligned the 5 sets in Eye on 2026-11-05: CSD, ±100 ms, committed with no person looking. m3 s2's #6 (822.505 s, outlier) and #10 (1869.870 s, edge) stayed at their hand-sorted times.
- The user wanted a manual check "to be safe". On 11-12 I sent the 5 to Eye as proposals from the aligned tip: br3be0b157fd, br73e928c3aa, br10db0e4387, br6a7da8a84b and br89f1236118. Their acceptance will make the next version on the trunk.
- A P-spike workflow's Run picks up each set's newest aligned version by itself (`refresh_sets`).

**Why:** the science pipeline (CTL DS envelope → hand-sorted P-spike envelope → classify PTEN).
**How to apply:** build on rcborder / rootcanalpool / artifacts. Pool-wide bank entries are a new shape: the Bank was per recording until now. Related: [ied-is-p-spike](ied-is-p-spike.md), `histology-v2` (a note not copied here).
