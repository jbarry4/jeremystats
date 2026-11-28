KCNT1 dentate spike menu, PRELIMINARY (2026-11-27)
The PTEN pipeline (Beyond Lock Steps/PIPELINE_PTEN.md) run end to end on 2 WT, 2 Het and 2 Hom KCNT1 (Y796H) mice, and
Jeremy's eight questions asked again with gene dose (WT 0, Het 1, Hom 2) in place of % knockout. A pipeline test and a
first look: with two mice per genotype no result here is a finding.

KCNT1_DS_Prelim_Menu_112726.pdf   the eleven pages in one file
pages/                            each page as PDF and PNG
tables/per_mouse_values_and_tests.csv   every measure per mouse, with the dose test, Hom against WT and the female check
tables/root_canal_classes_per_mouse.csv DS / BT / IED-class / outside counts per mouse, Halo and Strict workflows
code/                             everything that made it (see below)

Mice (one baseline recording each; pooled Lock entry at its newest committed version)
  WT   m1619 s1 (ac407abaa569, F)   m526 s1 (22749a284641, F)
  Het  m1609 s1 (aa1d581d5f7e, M)   m576 s1 (ef5031882809, M)
  Hom  m1603 s2 (9a12a5c1afaa, F)   m306 s1 (a1eb8aa0f5d1, F)
  All six recorded with a single line of 64 contacts (checked on the raw signal on the VACC). m531 s1 was left out: its
  Lock set holds 10 events.

What is in Jarvis now (all named "KCNT1 prelim")
  Root Canal pools       fdfa5c615419 (WT), 39840b662391 (all six); PTEN's Optimized parameters
  DS borders (Snap)      da17cac45862 (5% grace), 7fe4bbb98833 (10%), drawn around the WT events
  Halo set               3b70472fd070 v3 (5% DS border + PTEN P-spike border 4e5ce690d4b1 v2 + halo 2 / 1.5)
  Strict set             702bfb1e0a44 v2 (10% DS border + the same P-spike border, no halo)
  Root Canal bundles     116280c65da3 (Halo), c92a2704eea5 (Strict)
  X-ray Many folders     xm-cea705419b (Halo), xm-4aec612316 (Strict); reads made on the VACC, filed here
  Extraction Room        new room "Dentate Spike KCNT1" (953d3a5a81a7): v1 Halo, v2 Strict; default depth bands
  Code changes           backend/extraction.py and web/js/extraction.js (the second room); backend/er2/engine.py
                         (KCNT1 targets dose, wt_vs_hom, wt_vs_mut, geno3, and gene dose read for WT/Het/Hom). Jarvis
                         was restarted on this laptop; other machines need the code before they show the new room.

Where the heavy files are
  VACC /gpfs2/scratch/sakhava1/kcnt1_prelim: app/ (a Jarvis copy used in-process on compute nodes), rec/ (read-only
  copies of the six recordings; scratch, purge-eligible), deep/ (the deep-round pickles), battery/ (the KCNT1 battery:
  data/ds_v6.pkl Halo, ds_v8.pkl Strict, ds_b_*.pkl filter sets, meta.json), menus/ (2 kHz reads, j1/j2 outputs,
  kresults.pkl), logs/. Nothing was written to netfiles.

code/
  k1_rootcanal.py      pools, borders, Halo and Strict sets through the running Jarvis (ids in k1_ids.json)
  make_copies.py       copies Beyond Lock Steps/code with the work PC's paths replaced by settings (JAPP, KBAT, KROOM, KV)
  vacc/                vaccpatch.py (Jarvis in-process with recordings opened from the VACC copies), krun.py, and the
                       sbatch files in the order they ran: stage, k2 (X-ray reads), k3_freeze, k4one / k4 (2 kHz
                       reads, filter reads, menu data), k5_battery (before / after reads, measures, analyze)
  battery/             the PTEN battery adapted: KCNT1 groups and dose (build_dataset), 20 um per contact and no
                       exclusions (dsdata; plus a fix for two source peaks in one lobe), KCNT1 contrasts (harness,
                       analyze), make_meta.py
  deep/                the PTEN deep-round scripts, pointed at the KCNT1 room
  menus/               the PTEN menu scripts pointed at the KCNT1 mice; tight_layers.py falls back on PTEN's DS1-to-DS2
                       distance (no KCNT1 mouse separates); kcompute.py (numbers and tests) and kpages.py (the pages)

Known problems (read before trusting anything)
  - CSC 43 runs 10 to 17% below its neighbors in all six recordings (CSC 44 about 10% above), which draws a narrow false
    sink and source pair at rows 40 to 43, where four mice's upper blade sits. It is not marked bad. Every upper-blade
    result should wait until it is marked bad and the pipeline is run again (the steps above make that a re-run).
  - No mouse separates DS1 from DS2 (separation index 0.03 to 0.44); in m526 and m306 the anatomical naming puts 95% of
    events in DS2.
  - Sex is confounded with genotype (Het male; WT and Hom female). The IED border is PTEN's.
  - Not done: the duplicate-stamp dry run, hand-set depth bands, an IED grouping, and the machine-learning runs.
