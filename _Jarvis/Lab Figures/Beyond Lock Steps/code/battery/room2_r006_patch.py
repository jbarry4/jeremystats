"""Point the Room 2 write-up and figures at run r006 (2026-11-20: amber v3,
the Halo set with m21 back in, 16 mice). Applied after room2_r005_patch.py.
  python room2_r006_patch.py"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
R = [
    ("make_room2.py", [
        ('PDFs from the VACC run r005 (2026-11-19, amber v2; r003 and r004 were run 4 data).',
         'PDFs from the VACC run r006 (2026-11-20, amber v3: the Halo set with m21 in; r005 left m21 out, r003 and r004 were run 4 data).'),
        ('RUNS = ["r005"]', 'RUNS = ["r006"]'),
        ('("The frozen inputs (amber bundle v2)", "Every event of the Halo set (4,455 events in 15 recordings, one per mouse; m6 and m51 not included, and m21, '
         'whose winning classifier no longer keeps 5 events of each type once its duplicate stamps are gone) with each "',
         '("The frozen inputs (amber bundle v3)", "Every event of the Halo set (4,525 events in 16 recordings, one per mouse; m6 and m51 not included). m21 '
         'has no winning classifier once its duplicate stamps are gone (none keeps 5 events of each type), so its events carry no DS type. Each other "'),
        ('"Targets", "PTEN against control (15 mice); % knockout as a number, controls at 0 (15); low (under 10%) against high (15% or more) knockout "\n     "(PTEN only, 9 mice); control / IED− / IED+ (15); IED+ against IED− (PTEN only, 9).',
         '"Targets", "PTEN against control (16 mice); % knockout as a number, controls at 0 (16); low (under 10%) against high (15% or more) knockout "\n     "(PTEN only, 9 mice); control / IED− / IED+ (16); IED+ against IED− (PTEN only, 9).'),
        ('(all 54 pairs)', '(all 63 pairs)'),
        ('run r005, all answered; "\n     "the same settings as run r003 on the earlier data).',
         'run r006, all answered; "\n     "the same settings as run r003 on the earlier data and r005 without m21).'),
        ('with 9 to 15 mice a held-out "\n     "score is 9 to 15 calls.', 'with 9 to 16 mice a held-out "\n     "score is 9 to 16 calls.'),
        ('"pten_vs_ctl": "One model reached the bar (before/after power, forest, 0.82); the nuisance-only baseline gets 0.72. Controls and PTEN mice "\n                           "were mostly recorded in different years, so this target is still hard to tell apart from when the mice were recorded.",',
         '"pten_vs_ctl": "The nuisance-only baseline (above all the year recorded) gets 0.82, as high as the best spike-based model (0.83): controls and "\n                           "PTEN mice were mostly recorded in different years, so this target cannot be told apart from when the mice were recorded.",'),
        ('"ko_pct": "Rank correlation over 15 mice, 6 of them controls at 0 %:', '"ko_pct": "Rank correlation over 16 mice, 7 of them controls at 0 %:'),
        ('three classes over 15 mice.', 'three classes over 16 mice.'),
        ('"low_vs_high": "Nine PTEN mice (3 low, 6 high): two models reached the bar (event context, set networks, 0.83 = 15 of 18 pairs), '
         'and neither did in run r003."',
         '"low_vs_high": "Nine PTEN mice (3 low, 6 high): two models reached the bar (event context, set networks, 0.83 = 15 of 18 pairs); '
         'none did in run r003, on the data before the duplicate stamps came out."'),
    ]),
    ("make_room2_figs.py", [
        ('Everything comes from Jarvis run r005 (260 tasks) on amber bundle v2 (2026-11-19).',
         'Everything comes from Jarvis run r006 (260 tasks) on amber bundle v3 (2026-11-20, m21 in).'),
        ('RUN = "r005"', 'RUN = "r006"'),
        ('on 9 to 15 mice (one recording per "', 'on 9 to 16 mice (one recording per "'),
    ]),
]
for fn, subs in R:
    p = os.path.join(HERE, fn)
    s = open(p, encoding="utf-8").read()
    for a, b in subs:
        if a not in s:
            print("NOT FOUND in", fn, ":", a[:90])
            continue
        s = s.replace(a, b)
    open(p, "w", encoding="utf-8").write(s)
    print("patched", fn)
