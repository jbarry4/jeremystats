# kcnt1-ds-groups-1125

_KCNT1 awake DS readiness 2026-11-25: genotype is column 'YH' on the DS Data sheet; 8 Locked (WT 3 F, Het 3 M, Hom 2 F); WT is the bottleneck and sex is confounded._

On the "PTEN/KCNT1 Dentate Spike Data" Drive sheet (tab "KCNT1 Recording Sessions"), the KCNT1 genotype is column **YH** (Y796H). SST and PV are the Cre crosses. Sex and Prio. are the columns next to them. The user's screenshots are usually filtered, so download the full sheet with `rclone backend copyid gdrive: (Drive id on the work PC) out.xlsx --drive-export-formats xlsx`.

State on 2026-11-25:
- **Locked (8):** WT 1619, 531, 526 (all F). Het 1609, 1606, 576 (all M). Hom 1603 s2, 306 (both F).
- **Panning done, Lock not done:** 530 (Het F), 1604 s2 (Hom M), 310 s2 (Hom M).
- **Still being curated:**
  - WT 529 s1 and 591 s2, both waiting on RY Review.
  - Hom 588.
  - Het 1616, 577, 524, 520, 521.
- **WT mice that are recorded but marked ⛔ and not uploaded:** 523 (s2, s3) and 525 (s1–s3).
- Every WT candidate is female, so a female-only sensitivity check is the only clean way to handle sex.
- Most of these sessions used the H3 Cheetah config (Cheetah2026-06-01_wheel_H3.cfg).

Advice given:
- Lock the three Panning-done sessions first, which gives WT 3 / Het 4 / Hom 4.
- The primary test is a gene-dose trend (0/1/2 alleles) across all mice. WT vs Hom is the priority pair.
- WT is the bottleneck.

Related: [exploratory-no-correction](exploratory-no-correction.md), `kcnt1-aa-story-menu-1123` (a note not copied here), `chicken-scratch` (a note not copied here).
