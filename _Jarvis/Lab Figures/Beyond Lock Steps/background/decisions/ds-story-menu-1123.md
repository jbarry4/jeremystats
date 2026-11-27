# ds-story-menu-1123

_2026-11-23 DS story menu (Lab Figures/DS_Story_Menu_112326): the user's answers (BT name, three groupings, generous stats, staged dose/place/synchrony frame, DS-registered depth, common CSD scale), round-3 revisions, and the main findings._

The user is writing the DS part of the lab's somatic-mosaicism narrative (moving away from PTEN/mTOR toward pure electrophysiology). On 2026-11-23 I archived everything in `_Jarvis\Lab Figures` into `Lab Figures\Archive\<date>_<name>` (intact, index README) and built `Lab Figures\DS_Story_Menu_112326` (11-page PDF, pages/, tables/, code/; scripts also in the session scratchpad `menu/`).

**First set of answers (8 data, 4 narrative):**
- Archive by date, folders intact.
- Halo is the main set; Strict is the check.
- Three groupings, always: IED groups (control / IED- / IED+), KO groups (control / low <10% / high >=15%), and % knockout. m7 stays IED-, drawn as a diamond.
- Stats: uncorrected, "the most applicable and generous": smallest P of the applicable tests. I dropped Brunner-Munzel under 10 per group (invalid there).
- Selection: story first.
- DS vs IED analysis in the same sessions: yes.
- What separates PTEN pathology from WT is an open question (the borders used amplitude, fast power and half-width).
- Framework: staged **dose, then place, then synchrony**. DS1/DS2 is one menu item, with no behavior claim.
- Deliverable: "a middle phase between data overflow and a polished poster". Figures with narrative bits around them, not a separate narrative doc. A menu of stories the data support.

**Second round (same evening):**
- The in-between class (Root Canal Twilight Zone) is named **borderline transients (BTs)**. Briefly called pDS that afternoon; the user dropped it.
  - The name should not be DS-specific.
  - The idea, in the user's own analogy: "not quite normal, not quite pathological; a few are fine, many mean something is going on".
- Story 5a: static 3D of amplitude x half-width x fast power, with the border hulls, plus the three 2D projections.
- The hand-sorted-IEDs-by-class panel and claim were dropped ("ignore the hand sorted ones").
- Final form: the polished menu only (no poster panels this round).

**Third round (late evening, after review):** the figure rules are in [story-menu-figure-rules](story-menu-figure-rules.md). What changed in this menu:
- No lab layer labels anywhere (the labels were imported from `EEGData_FeederSheet_PTEN_with_DKO.xlsx` on 2026-09-08). Depth: u = 0 at each recording's upper DS sink peak, 1 at the lower; regions from DS landmarks (median over 16): top edge -0.19, upper cell-layer source 0.43, lower 0.68, bottom edge 1.17 (`uprof.pkl`, `m7_uprof.py`).
- Story 3 CSD on one common scale (control average deepest sink = -1). Story 7 depth on y with mirrored blades.
- Story 1b tests m7 as an outlier; Story 8 rebuilt around per-mouse held-out calls.

**Findings (exploratory):**
- Fast power at the DS (Root Canal 240-420 Hz) goes in two directions: every IED+ mouse above every control (P 1.9e-5); every IED- mouse below every control (P 0.003); m7 lowest of all.
- m7 is an outlier for its knockout level (Grubbs among high-KO P 0.001; off the PTEN line P 0.004), not for its IED status (Grubbs among IED- P 0.13). Without m7: high KO vs control P 0.051 to 1.9e-5; PTEN rho +0.57 to +0.81 (P 0.001).
- On the common CSD scale, IED- dentate spikes carry about half the control current (upper sink peak P 0.012, lower P 0.036). The IED+ lower sink is 1.3x control but varies widely (P 0.27); the per-event blade balance holds (P 0.002).
- BTs: 0.56-1.89 per minute in IED+ mice vs at most 0.075 elsewhere. They have an IED's half-width and fast power but a DS's depth footprint.
- Pooled over the five IED+ mice: DS are 1.4-2.0x chance from 0.5 to 60 s around IEDs (P <= 0.003); BTs 1.1-1.4x within 5-60 s (P 0.005-0.04). m28 has no BT within 1 s, but 29 within 20 s.
- DS1 sits farther out than DS2 in 14/15 (upper) and 13/15 (lower) recordings. The gap is smaller in IED+ than IED- (P 0.035).
- Held-out IED models (r006, 14 at the bar) get 8 of 9 PTEN mice right. The miss is m3 (0.07), whose fast power is above every control. They call m7 IED- (0.05). Knockout models call m7 low (0.00) and m1 high (0.95). Fast power was never an ML input.

**Why:** these are the user's framing choices for the poster and next paper.
**How to apply:** reuse the groupings, stats rule, BT name, DS-registered depth, common CSD scale and page style for later rounds. Related: [exploratory-no-correction](exploratory-no-correction.md), [ds-pten-halo-and-strict-sets](ds-pten-halo-and-strict-sets.md), [pten-probe-is-h3-20um](pten-probe-is-h3-20um.md), [never-say-a-spike](never-say-a-spike.md), `stratascope-evidence-vs-lab-labels` (a note not copied here).
