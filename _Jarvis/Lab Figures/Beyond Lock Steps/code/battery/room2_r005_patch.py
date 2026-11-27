"""Point the Room 2 write-up and figures at run r005 (2026-11-19: amber v2,
duplicate stamps removed, m1 on Lock, m21 without a winner so 15 mice).
  python room2_r005_patch.py"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
R = [
    ("make_room2.py", [
        ('PDFs from the VACC run r003 (with r004 filling in tasks r003 has not answered).',
         'PDFs from the VACC run r005 (2026-11-19, amber v2; r003 and r004 were run 4 data).'),
        ('RUNS = ["r003", "r004"]', 'RUNS = ["r005"]'),
        ('("The frozen inputs (amber bundle v1)", "Every event of the Halo set (4,613 events in 16 recordings, one per mouse; m6 and m51 not included) with each "',
         '("The frozen inputs (amber bundle v2)", "Every event of the Halo set (4,455 events in 15 recordings, one per mouse; m6 and m51 not included, and m21, '
         'whose winning classifier no longer keeps 5 events of each type once its duplicate stamps are gone) with each "'),
        ('"Targets", "PTEN against control (16 mice); % knockout as a number, controls at 0 (16); low (under 10%) against high (15% or more) knockout "\n     "(PTEN only, 9 mice); control / IED− / IED+ (16); IED+ against IED− (PTEN only, 9).',
         '"Targets", "PTEN against control (15 mice); % knockout as a number, controls at 0 (15); low (under 10%) against high (15% or more) knockout "\n     "(PTEN only, 9 mice); control / IED− / IED+ (15); IED+ against IED− (PTEN only, 9).'),
        ('leaves one control and one PTEN mouse out at a time (all 63 pairs)', 'leaves one control and one PTEN mouse out at a time (all 54 pairs)'),
        ('"Where it ran", "Jarvis\'s new Extraction Room tab \'Room 2.0 · models\', on the VACC (one slurm array, 260 tasks, run r003; r004 re-ran the four "\n     "slowest without the drop-one-family step; all 260 r003 tasks finished, so r004 is not used).',
         '"Where it ran", "Jarvis\'s Extraction Room tab \'Room 2.0 · models\', on the VACC (one slurm array, 260 tasks, run r005, all answered; "\n     "the same settings as run r003 on the earlier data).'),
        ('with 9 to 16 mice a held-out "\n     "score is 9 to 16 calls.', 'with 9 to 15 mice a held-out "\n     "score is 9 to 15 calls.'),
        ('"pten_vs_ctl": "The nuisance-only baseline (above all the year recorded) does as well as the best spike-based model: controls and PTEN mice "\n                           "were mostly recorded in different years, so this target cannot be told apart from when the mice were recorded.",',
         '"pten_vs_ctl": "One model reached the bar (before/after power, forest, 0.82); the nuisance-only baseline gets 0.72. Controls and PTEN mice "\n                           "were mostly recorded in different years, so this target is still hard to tell apart from when the mice were recorded.",'),
        ('"ko_pct": "Rank correlation over 16 mice, 7 of them controls at 0 %:', '"ko_pct": "Rank correlation over 15 mice, 6 of them controls at 0 %:'),
        ('three classes over 16 mice.', 'three classes over 15 mice.'),
        ('"low_vs_high": "Nine PTEN mice (3 low, 6 high, ko 10–15% left out); no model reached the bar."',
         '"low_vs_high": "Nine PTEN mice (3 low, 6 high): two models reached the bar (event context, set networks, 0.83 = 15 of 18 pairs), '
         'and neither did in run r003."'),
    ]),
    ("make_room2_figs.py", [
        ('Everything comes from Jarvis run r003 (260 tasks) on amber bundle v1.', 'Everything comes from Jarvis run r005 (260 tasks) on amber bundle v2 (2026-11-19).'),
        ('RUN = "r003"', 'RUN = "r005"'),
        ('on 9 to 16 mice (one recording per "', 'on 9 to 15 mice (one recording per "'),
    ]),
]
for fn, subs in R:
    p = os.path.join(HERE, fn)
    s = open(p, encoding="utf-8").read()
    for a, b in subs:
        if a not in s:
            print("NOT FOUND in", fn, ":", a[:80])
            continue
        s = s.replace(a, b)
    open(p, "w", encoding="utf-8").write(s)
    print("patched", fn)
