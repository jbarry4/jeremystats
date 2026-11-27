"""Assemble report_v3.md from report_v2.md: new figure architecture, new order, new numbering."""
import re

L = open('/home/claude/work/report_v2.md').read().split('\n')
blk = lambda a, b: '\n'.join(L[a - 1:b])            # 1-indexed, inclusive

# ---------------------------------------------------------------- figure set
FIG = {
    1:  ('figsv3/fig01_learning.svg', '6.9in'),
    2:  ('figsv3/fig02_visible.svg', '6.9in'),
    3:  ('figsv3/fig03_hidden.svg', '6.9in'),
    4:  ('figsv3/fig04_change_per_phase.svg', '6.9in'),
    5:  ('figsv/p8__fig30_phase8_visible.svg', '6.5in'),
    6:  ('figsv/p8__fig31_phase8_hidden.svg', '6.5in'),
    7:  ('figsv/gzbars12__fig_bars_hidden.svg', '6.5in'),
    8:  ('figsv3/fig16a_arrival_runs.svg', '6.3in'),
    9:  ('figsv3/fig16b_arrival_phase.svg', '6.5in'),
    10: ('figsv3/fig17_former_goals.svg', '5.6in'),
    11: ('figsv3/nf2_pausemaps.svg', '6.3in'),
    12: ('figsv3/nf4_arrival.svg', '6.5in'),
    13: ('figsv/sm__fig_speed_mode.svg', '6.5in'),
    14: ('figsv/miss__ap6_aftermiss.svg', '6.3in'),
    15: ('figsv3/fig09_phase10_zones.svg', '6.9in'),
    16: ('figsv3/fig10_phase10_perf.svg', '6.9in'),
    17: ('figsv3/fig11_slopes.svg', '6.2in'),
    18: ('figsv/csd3__fig28_layer_profile_lohi.svg', '6.4in'),
    19: ('figsv3/fig12b_csd_regression.svg', '6.0in'),
    20: ('figsv3/fig12c_roc.svg', '6.0in'),
    21: ('figsv/patch__fig36_cno_patch.svg', '6.3in'),
    22: ('figsv3/fig13_cno_behaviour.svg', '6.2in'),
    23: ('figsv3/fig15_ied.svg', '6.2in'),
    24: ('figsv/ied__fig35_dissociation.svg', '6.5in'),
    'S1': ('figsv/csd3__figS1_csd_regression_supp.svg', '6.4in'),
    'S2': ('figsv/csd3__figS2_roc_supp.svg', '6.4in'),
    'S3': ('figsv/ied__figS3_ied_csd.svg', '5.2in'),
    'S4': ('figsv/ied__figS4_ied_timing.svg', '6.5in'),
    'S5': ('figsv/ap__ap1_paths.svg', '6in'),
    'S6': ('figsv/ap__ap2_metrics.svg', '6in'),
    'S7': ('figsv/ap__ap3_launch_phase.svg', '6in'),
    'S8': ('figsv/ap__fig32_heading_profile.svg', '6.5in'),
    'S9': ('figsv/ex__exB_dwell_hidden.svg', '6.5in'),
    'S10': ('figsv/ex__exC_speed_hidden.svg', '6.5in'),
    'S11': ('figsv/gzfigs__fig11_zone_roles.svg', '6.5in'),
    'S12': ('figsv/gzbarsH__fig_bars_hidden_mwu.svg', '6.5in'),
    'S13': ('figsv/figs__fig5_heatmap.svg', '6.3in'),
    'S14': ('figsv/csd3__fig29_layer_profile_ied.svg', '6.4in'),
}
# old figure number in v2 -> new label
MAP = {1: '1', 2: '1', 3: '5', 4: '6', 5: '2', 6: '3', 7: 'S5', 8: 'S6', 9: 'S7', 10: 'S8',
       11: '3', 12: 'S9', 13: 'S10', 14: '2', 15: '8', 16: '8', 17: '10', 18: 'S11', 19: '7',
       20: 'S12', 21: '15', 22: '15', 23: '17', 24: '4', 25: '17', 26: 'S13', 27: '16', 28: '16',
       29: '13', 30: '14', 31: '19', 32: '18', 33: 'S14', 34: '21', 35: '22', 36: '22', 37: '20',
       38: '23', 39: '23', 40: '24'}


def renumber(t):
    """Rewrite references to v2 figure numbers. Captions are rewritten separately."""
    def one(m):
        n = int(m.group(2))
        return '%s %s%s' % (m.group(1), MAP.get(n, str(n)), m.group(3) or '')
    t = re.sub(r'\b(Figure)s? (\d+)([ab])?\b', one, t)
    t = re.sub(r'\b(Figures) (\d+) and (\d+)\b',
               lambda m: 'Figures %s and %s' % (MAP.get(int(m.group(2))), MAP.get(int(m.group(3)))), t)
    return t


def strip_figs(t):
    """Remove v2 image lines and their captions; the new blocks are placed explicitly."""
    out = []; skip = False
    for ln in t.split('\n'):
        if ln.startswith('!['):
            skip = True; continue
        if skip and ln.strip().startswith('*Figure'):
            skip = False; continue
        if skip and not ln.strip():
            continue
        skip = False
        out.append(ln)
    return '\n'.join(out)


CAP = {}


def fig(n, caption):
    p, w = FIG[n]
    CAP[n] = caption
    lab = n if isinstance(n, str) else str(n)
    pre = 'Supplementary Figure ' if lab.startswith('S') else 'Figure '
    return '![](%s){width=%s}\n\n*%s%s. %s*\n' % (p, w, pre, lab, caption)


def sec(a, b):
    return renumber(strip_figs(blk(a, b)))


P = []
A = P.append


def orig(svg):
    """The caption v2 gave this figure, with its 'Figure N.' prefix removed and refs renumbered."""
    for i, ln in enumerate(L):
        if ln.startswith('![](figsv/' + svg):
            for j in range(i + 1, i + 4):
                if L[j].strip().startswith('*Figure'):
                    c = L[j].strip().strip('*')
                    return renumber(re.sub(r'^Figure \d+\.\s*', '', c))
    raise KeyError(svg)

# ================================================================= assemble
A('''---
title: "Pten KO mosaicism and spatial accuracy: a behavioural interrogation"
subtitle: "Version 3"
date: "November 24, 2026"
---
''')

A('''# Summary

Mosaic Pten deletion does not produce one deficit that worsens with dose. It produces two
different phenotypes, and the axis separating them is reliance on the cue against reliance on the
place. Low load gives a mouse that is slow to take up the cue rule but knows where things are.
High load gives a mouse that takes the rule up readily and then cannot function without it.

| | Pten KO Lo (< 15% KO, n = 5) | Pten KO Hi (≥ 15% KO, n = 6) |
|---|---|---|
| Learning the cue→reward rule | Acquires it, least readily of the three — 21.2 vs 8.8 sessions (p < 0.001, no overlap with WT) | Acquires it more readily than Lo — 14.0 sessions (p = 0.03 vs WT), median 11.5, inside the WT range |
| Place preference with a cue present | Intact — +12.0 points (p = 0.016) | Absent — −4.2 points (p = 0.58) |
| Speed through the reward window | Like WT | **16.4 vs 11.5 cm/s at hidden phase 10 (p < 0.001)**; unchanged at phase 7 and when cued |
| Decelerating at the hidden goal | Like WT | Braking on 38% of runs against 56% (p = 0.045); the change on removing the cue is twice WT's (p = 0.021) |
| Dwelling at the hidden goal | Pauses the most of any group | 59 s against 134 s per session (p = 0.006) |
| Searching the places that used to pay | Scales with the set, like WT | Does not — group × phase p = 0.003, and p = 0.198 when cued |
| Change across the four rotations | Goal time falls (p = 0.004) | Rewards −2.9 per phase (p = 0.003), target speed +2.1 cm/s (p = 0.005); cued slopes flat |
| What they do instead | Search hard, aim badly | Run — they speed up when the marker is removed (p = 0.001) |

**What is new in this version.** Three things changed the account rather than adding to it.

1. **Speed through the reward window, on every entry.** Locking the speed profile to the moment of
   entry and including chance crossings as well as directed runs gives the largest arrival effect
   in the report: at hidden phase 10 the Hi mice are moving at 16.4 cm/s through the 1.2 s window
   that earns a pellet, against 11.5 in WT (p = 0.0005). The same comparison at the trained
   location and in the cued session gives p = 0.18. This is "running through the goal", measured.
2. **The shape of the approach is normal.** With each run scaled to its own approach maximum, the
   speed profile against distance from the goal does not differ between groups: a permutation test
   across the whole profile with max-statistic correction gives p = 0.53, and the within-animal
   hidden-minus-cued version p = 0.83. The deficit is not in getting there or in aiming; it is at
   and after arrival.
3. **The cued sessions are flat.** Every slope that falls across the four hidden rotations is flat
   when the goal is marked, in the same mice (Figure 4). The decline is a response to the rotation,
   not drift across days.

**The within-animal control.** Every claim above survives the comparison that matters most: the
same mouse, the same phase, the same arena, with and without the marker. Hi mice pause less when
the cue is removed while WT mice pause more (change p = 0.043), their braking at the goal falls
twice as far (p = 0.021), and they speed up where WT mice slow down (p = 0.001).

**Dose.** Percent KO does not order the groups. The slowest learners have the fewest KO cells, and
there are no mice between 9.5% and 20.2%, so the Lo/Hi split carries what percent KO carries.
''')

A('# Part I — The behavioural interrogation\n')
A(sec(37, 56))                                              # 1. Cohort
A(sec(57, 124))                                             # 2. Criterion
A(fig(1, 'Learning the cue rule. **a** Sessions to criterion, each point one mouse, group '
        'mean ± SE; M6 (WT, 27 sessions) excluded; brackets are Mann-Whitney tests. **b** Sessions '
        'to criterion against percent KO: the slowest learners have the fewest KO cells. The '
        'quadratic describes that shape and is not a dose model — the mice fall in two clusters '
        'with a gap between them. IED+ and heterotopia mice are labelled. **c** The two measures '
        'that separate the groups, against each other: sessions to criterion and the latent place '
        'preference with the cue present (Figure 5b). Diamonds mark IED+ mice.'))

A('''## 3. The task, and the measures that missed it

Before any of the fine-grained analysis, this is what the task looks like and what the session
measures say about it. The three example mice are the same throughout: M22 (WT), M33 (Pten KO Lo,
8.8% KO) and M34 (Pten KO Hi, 28.4% KO, IED+). With the marker present all three run to the goal
at every phase and collect rewards (Figure 2). With it removed the picture changes, and the four
session measures change with it (Figure 3) — but, as the rest of Part I shows, what they change by
understates what is happening at the goal.
''')
A(fig(2, 'Visible goal sessions. Left: the three example mice, phase by phase; grey is the full '
        '30-minute path, coloured the 3 s before each reward, black dots where the reward was '
        'triggered; circles mark the current goal (solid), the previous goal (dashed), the trained '
        'goal (dotted) and zones not yet used (light grey). Arenas are drawn in the room view, so '
        'the phase 7 goal sits in the upper right quadrant and the later goals follow '
        'anti-clockwise. Right: the four session measures by phase, mean ± SE across mice; letters '
        'mark uncorrected p < 0.05 at that phase (L = Lo vs WT, H = Hi vs WT, × = Lo vs Hi).'))
A(sec(209, 244))                                            # visible probe text
A(fig(3, 'Hidden goal sessions. Same conventions as Figure 2.'))
A(sec(245, 283))                                            # hidden probe text
A(sec(392, 466))                                            # example-mice walkthrough
A('''## 4. Does performance change across the rotations?

Each mouse gets a slope: the least-squares change per phase across the four hidden probes. The
cued sessions give the control, because a mouse that is simply getting worse over days should
decline there too.
''')
A(fig(4, 'Change per phase across the four rotations. Each point is one mouse\'s least-squares '
        'slope across phases 7 to 10; the bar is the group mean ± SE; beneath each group is the '
        'mean slope and its test against zero. Top row: goal hidden. Bottom row: goal cued, the '
        'control.'))
A('''The hidden slopes are where the groups part. Hi mice lose 2.9 rewards per phase (p = 0.003),
lose 0.023 rewards per entrance per phase (p = 0.022) and gain 2.13 cm/s of target speed per phase
(p = 0.005). Lo mice lose goal-zone time (−0.0069 per phase, p = 0.004) without losing rewards.
WT mice are flat on every measure (p = 0.06 to 0.61).

In the cued sessions nothing declines. The only significant cued slope in the set runs the other
way: Lo mice improve their rewards per entrance by +0.071 per phase (p < 0.001), which is the slow
acquisition of Section 2 still finishing. Hi mice are flat when cued on all four measures
(p = 0.06 to 0.55).

So the decline is a response to the goal moving, not a drift across days, and it is not fatigue or
satiety: the same mice on the same days earn rewards normally when the goal is marked.
''')
A(sec(702, 733))                                            # the two slope tables
A('''## 5. What controls where they go: the cue or the place?
''')
A(sec(125, 156).replace('## 3. What controls where they go: the cue or the place?', '').lstrip('\n'))
A(fig(5, orig('p8__fig30_phase8_visible.svg')))
A(sec(157, 176))
A(fig(6, orig('p8__fig31_phase8_hidden.svg')))
A(sec(177, 208))

A('''## 6. Is getting to the goal intact?
''')
A(sec(284, 391).replace('## 4. Is getting to the goal intact?', '').lstrip('\n'))
A('''The figures behind this section — every wall-to-goal run for one mouse per group, the visible
against hidden comparison of each measure, launch distance by phase and the heading profile — are
Supplementary Figures S5 to S8. Nothing in them separates the groups once the cue is removed in
the way the arrival measures do, which is the point: the navigation is intact.

## 7. Do they recognise arrival?
''')
A(sec(467, 491).replace('## 5. Do they recognise arrival?', '').lstrip('\n'))
A(fig(8, 'Arriving at the goal: what the runs look like. **a** Every directed run into the hidden '
        'goal at phase 10 for one mouse per group, in goal-centred coordinates, rotated so the '
        'approach comes from the left and coloured by speed; the dot marks where the mouse was '
        '1.2 s after entering — inside the zone (green) is a reward, outside (red) is a miss. '
        '**b** One run per mouse, the run whose slowing ratio is closest to that mouse\'s median; '
        'a dot every 0.1 s, so the dots bunch where the mouse is slow. All three panels share one '
        'axis range, so the goal circles are the same size and the runs are drawn to the same '
        'scale. **c** Mean speed around every entry into the current goal — directed runs and '
        'chance crossings alike — at the trained location, the last rotation and the cued last '
        'rotation; mean ± SE across mice; the shaded band is the 1.2 s the mouse must stay in the '
        'zone to earn the reward. The p value compares the mean speed inside that window, Hi vs '
        'WT (Mann-Whitney).'))
A('''Panel c is the clearest statement of the deficit in the report. At the trained location the
three groups are indistinguishable through the reward window (Hi 11.1 cm/s, WT 10.1, p = 0.18).
At the last rotation the Hi mice are moving at **16.4 cm/s against 11.5 in WT (p = 0.0005)** —
they reach the goal and pass through it. Put the marker back, at the same phase in the same mice,
and the difference goes (11.8 against 10.7, p = 0.18).

This is the measure to lead with: it uses every entry rather than the subset the mouse aimed at,
so it cannot be explained by a difference in which runs qualify as directed.
''')
A(fig(9, 'Slowing and pausing across the rotations. **a** Slowing ratio (mean speed over the '
        '1.2 s after entry divided by the mean over the 1.5 to 0.5 s before it, on directed runs; '
        '1 means no slowing) and total pause time per session, hidden and cued. **b** Pause time '
        'split by where the pause happened — inside the goal zone, in the ring around it, and in '
        'the open interior beyond 2.5 zone radii — with the cued open interior as the control. '
        'Pauses at the wall (beyond 0.8 of the arena radius) are excluded by the pause definition '
        'throughout. Faint points are mice, lines are group means ± SE. Beneath each panel are the '
        'mean per-mouse slopes across phases 7 to 10 and the Mann-Whitney comparing those slopes '
        'between Hi and WT; numbers above a phase are Hi vs WT at that phase.'))
A(sec(492, 529))
A('''### The shape of the approach is normal

Whishaw, Cassel and Jarrard (1995, *J Neurosci* 15:5779) treat deceleration on approach as the
sign that an animal expects the goal at a place. Applying that test here needs care, because there
are two different questions in it: *does the approach have the right shape*, and *does the animal
stop when it arrives*.

The shape is normal. Scaling every directed run to its own approach maximum and plotting speed
against distance from the goal, the groups are indistinguishable: a permutation test across the
whole profile with max-statistic correction gives p = 0.53, and the within-animal hidden-minus-cued
profile gives p = 0.83. Hi mice decelerate on approach like everyone else.

What differs is whether a run contains a slowdown at all, and what happens at the goal.
''')
A(fig(12, 'Braking on approach, cue present and cue removed, at phase 10. **a** Braking events at '
         'the current goal per 10 m of off-wall path — a braking event is a fall from a local '
         'speed maximum of at least 12 cm/s to below half that speed within 1 s, placed where the '
         'mouse ended up slow and assigned to the nearest kind of zone within 2.5 zone radii; '
         'rates are per metre travelled because Hi mice cover about 29% more ground. **b** The '
         'proportion of directed runs that contain any braking. **c** The distance from the goal '
         'at which a braking run first fell below 70% of its approach maximum, over the runs that '
         'braked. Each pair of points is one mouse, cue present on the left; p beneath each pair '
         'is the paired t-test; above each panel is the Mann-Whitney on the change between Hi and '
         'WT. Diamonds mark IED+ mice.'))
A('''Cued, the three groups brake alike: 88.0% of WT runs and 81.2% of Hi runs contain a slowdown
(p = 0.59), beginning 10.2 cm out in both (p = 0.98). Hidden, 56.2% of WT runs and 38.4% of Hi runs
contain one (p = 0.045), and when Hi mice do brake they start later, 13.7 cm from the goal centre
against 11.5 (p = 0.050). The within-animal change is the stronger test: removing the cue costs WT
mice 2.8 braking events per 10 m and Hi mice 6.8 (p = 0.021).

**Where this logic has to stop.** Braking at *former* goals is identical in all three groups
(15.2, 15.8 and 14.7 events per 10 m, p = 0.93). Hi mice do pass through the old places and do slow
at them. The deficit is not a failure to generate candidates or to check them; it is a failure to
turn a check into a stay.
''')

A('''## 8. When the goal has moved, do they search the places that used to pay?
''')
A(sec(530, 557).replace('## 6. When the goal has moved, do they search the places that used to pay?', '').lstrip('\n'))
A(fig(10, 'The set to rule out. Pause time at former goals per session, by phase, with the goal '
         'hidden (left) and cued (right). The number of former goals in play grows 0, 1, 2, 3 '
         'across the four phases. Faint points are mice, lines are group means ± SE; beneath each '
         'panel are the mean per-mouse slopes and the Mann-Whitney comparing those slopes between '
         'Hi and WT; numbers above a phase are Hi vs WT at that phase. Pauses at the wall are '
         'excluded by the pause definition throughout.'))
A('''This is the strongest behavioural result in the report. With the goal hidden, WT mice spend
0, 33, 42 and 82 s at former goals as the set grows, Lo mice 0, 31, 55 and 88, and Hi mice 0, 15,
26 and 28; the per-mouse slopes are +25.3, +28.8 and +9.6 s per phase, and the group × phase
comparison is p = 0.003. With the goal cued the same mice behave alike (slopes +18.6, +18.6 and
+15.0, p = 0.198), so this is not a general difference in how much they pause.

What it says is that a WT mouse treats the history as a list to work through, and that the list
gets longer as the experiment goes on. The Hi mouse does not add to the list.
''')
A(fig(11, 'Where they look, with the cue on and off. **a–f** One session per mouse per condition '
         'at phase 10, cue present (left) and cue removed (right), for the three mice closest to '
         'their group medians across five of the measures in this report (M9 WT, M8 Lo, M5 Hi). '
         'Grey is the whole path; each marker is a pause, drawn where it happened and sized by how '
         'long it lasted: filled black at the current goal, an open amber ring at one of the three '
         'former goals, a pale dot in the open interior. The inner dashed arc is the wall annulus, '
         'which the pause measure excludes. **g** Pause time by the kind of place, cue removed, '
         'every mouse; bars are mean ± SE with each mouse as a point. **h** The change in total '
         'pause time on removing the cue, per mouse, with the group mean ± SE; p beneath each '
         'group is the paired t-test, and the bracket is the Mann-Whitney on the change.'))
A('''The maps are the group result in one session each. The WT and Lo mice work the history — a
cluster at the current goal and a second at the phase 7 and 8 goals — while the Hi mouse gives 21
pauses and 37 s against 57 and 52 pauses, 129 and 125 s, with its goal pauses on the rim of the
zone rather than inside it.

Panel h is the control stated plainly: removing the cue makes WT mice pause **more**, because the
goal now has to be remembered (+30 s, p = 0.024), and makes Hi mice pause less (−34 s); the change
differs between the groups at p = 0.043.
''')
A(sec(558, 581))
A(fig(7, orig('gzbars12__fig_bars_hidden.svg')))
A(sec(582, 683))
A('''## 9. What they do instead, and what a found-it measure cannot show
''')
A(sec(825, 832).replace('## 8. What this task can show that a found-it-or-didn’t measure cannot', '').lstrip('\n'))
A(fig(13, orig('sm__fig_speed_mode.svg')))
A(sec(833, 858))
A(fig(14, orig('miss__ap6_aftermiss.svg')))
A(sec(859, 927))
A('''## 10. Does the deficit scale with the load?
''')
A(sec(684, 701).replace('## 7. Does the deficit scale with the load?', '').lstrip('\n'))
A(fig(15, 'Hidden phase 10, zone measures. **A** Time in each zone, each mouse a small point '
         '(diamonds: IED+) and the group mean ± SE; time per entry into the current goal, with the '
         'dashed line at the 1.2 s stop needed for a reward; entries into the current goal. '
         '**B** The same measures against percent KO, with the best-fit line and 95% confidence '
         'band through the Pten KO mice; WT shown at 0% for reference and not included in the fit; '
         'Spearman p above each panel.'))
A(sec(734, 762))
A(fig(16, 'Hidden phase 10, performance measures. **A** Each measure against percent KO; the blue '
         'band is the WT mean ± SE and the dashed line a linear fit through the Pten KO mice. '
         '**B** The same measures by group. The Hi KO mice deviate from WT; the Lo KO mice match '
         'WT on rewards per entrance and target speed but move more slowly and earn fewer rewards. '
         'Diamonds: IED+ mice.'))
A(sec(795, 824))
A(fig(17, 'Slopes across the hidden rotations. **A** Every measure with a slope across the four '
         'hidden rotations: per-mouse least-squares slope, standardised by the SD of the per-mouse '
         'slopes for that measure so that measures in different units sit on one axis; points are '
         'group means ± SE; p values are Hi versus WT on the unstandardised slopes '
         '(Mann-Whitney). **B** Share of directed runs to the current goal that end in a reward '
         'across the hidden probes: each mouse (thin) and the group mean (thick), and each '
         'mouse\'s slope across phases 7 to 10 in hidden (circles) and visible (squares) sessions.'))
A(sec(763, 794))

# ---------------------------------------------------------------- Part II
A('# Part II — The circuit\n')
A(sec(930, 997).replace('## 9. Theta CSD by layer', '## 11. Theta CSD by layer').lstrip('\n'))
A(fig(18, orig('csd3__fig28_layer_profile_lohi.svg')))
A(sec(998, 1100))
A(fig(19, 'Theta CSD against percent KO for the three lower-blade measures: MML2 + GCL2, MML2 and '
         'GCL2. Columns: baseline, after CNO, and the change. Blue: WT (plotted at 0%, slightly '
         'spread); green: Lo KO; red: Hi KO; diamonds: IED+. Dashed line: 15% KO. The 4-layer '
         'average, and the same plots for MML1 and GCL1, are Supplementary Figure S1.'))
A(fig(20, 'Theta CSD as a predictor of clear IEDs, for the same three measures. Left: ROC curves '
         'at baseline (solid) and after CNO (dashed), with the loss of AUC. Right: each mouse\'s '
         'CSD at baseline and after CNO, by WT, KO without IEDs and KO with IEDs; dashed line: the '
         'best baseline cutoff; black: group means; above the panel, the CNO drop itself as a '
         'predictor. MML1 and GCL1 are Supplementary Figure S2.'))
A(sec(1101, 1104).replace('## 10. The DREADD works', '## 12. The DREADD works').lstrip('\n'))
A(fig(21, orig('patch__fig36_cno_patch.svg')))
A(sec(1105, 1119))
A(sec(1120, 1121).replace('## 11. Silencing the KO cells', '## 13. Silencing the KO cells').lstrip('\n'))
A(fig(22, 'CNO and behaviour. **A** Goal-zone time (phases 8–9 mean) against percent KO, visible '
         'sessions (top) and hidden sessions (bottom), at baseline, after CNO and the change; '
         'conventions as in Figure 19; M36 is included here. **B** Hidden goal-zone time for all '
         'Pten KO mice pooled against WT: group means ± SE at baseline and after CNO, each mouse '
         '(KO coloured by Lo and Hi; diamonds: IED+), and each mouse\'s change with CNO.'))
A(sec(1122, 1187))
A(sec(1188, 1199).replace('## 12. Interictal discharges', '## 14. Interictal discharges').lstrip('\n'))
A(fig(23, 'Interictal discharges. **A** Grand-average IED voltage at baseline and after CNO, on '
         'the same colour scale (5 mice; 41 and 131 IEDs); bars above each raster mark the '
         'initiation (IP, −1 to 0 ms) and propagation (PP, 2 to 15 ms) windows; beneath, voltage '
         'by layer in each window on the same axis, initiation filled and propagation open. '
         '**B** Theta excess and IED initiation by layer: baseline theta CSD of IED+ mice minus WT '
         '(IED+ 5, WT 10); the CSD of the averaged IED in the initiation window (blue sink, red '
         'source); and both profiles scaled to their own maximum, with shading marking GCL2 and '
         'MML2.'))
A(sec(1200, 1226))
A(fig(24, orig('ied__fig35_dissociation.svg')))
A(sec(1227, 1249))

# ---------------------------------------------------------------- Part III
A(sec(1250, 1367).replace('## 13. Interpretation', '## 15. Interpretation')
                 .replace('## 14. Caveats and open questions', '## 16. Caveats and open questions'))

A('''## 17. Figure list

| | |
|---|---|
| 1 | Learning the cue rule: criterion, percent KO, and the two phenotypes |
| 2 | Visible goal sessions: the example mice and the session measures |
| 3 | Hidden goal sessions: the example mice and the session measures |
| 4 | Change per phase across the four rotations, hidden and cued |
| 5 | Visible phase 8: place against cue |
| 6 | Hidden phase 8: new place against old place |
| 7 | Time in each zone in hidden sessions, by phase and group |
| 8 | Arriving at the goal: what the runs look like |
| 9 | Slowing and pausing across the rotations |
| 10 | The set to rule out: pause time at former goals |
| 11 | Where they look, with the cue on and off |
| 12 | Braking on approach |
| 13 | What they do instead: running |
| 14 | Pauses and returns after a miss |
| 15 | Hidden phase 10: zone measures |
| 16 | Hidden phase 10: performance measures |
| 17 | Slopes across the hidden rotations |
| 18 | Theta CSD by layer |
| 19 | Theta CSD against percent KO |
| 20 | Theta CSD as a predictor of IEDs |
| 21 | CNO silences hM4D-expressing Pten KO granule neurons |
| 22 | CNO and behaviour |
| 23 | Interictal discharges |
| 24 | The four IED+ Hi mice with recordings and behaviour |

## 18. Supplementary figures
''')
for k, cap in [('S1', 'Theta CSD on percent KO for the 4-layer average, MML1 and GCL1.'),
               ('S2', 'ROC for MML1 and GCL1.'),
               ('S3', 'IED CSD, supplementary.'),
               ('S4', 'IED timing, supplementary.'),
               ('S5', orig('ap__ap1_paths.svg')),
               ('S6', orig('ap__ap2_metrics.svg')),
               ('S7', orig('ap__ap3_launch_phase.svg')),
               ('S8', orig('ap__fig32_heading_profile.svg')),
               ('S9', orig('ex__exB_dwell_hidden.svg')),
               ('S10', orig('ex__exC_speed_hidden.svg')),
               ('S11', orig('gzfigs__fig11_zone_roles.svg')),
               ('S12', orig('gzbarsH__fig_bars_hidden_mwu.svg')),
               ('S13', orig('figs__fig5_heatmap.svg')),
               ('S14', orig('csd3__fig29_layer_profile_ied.svg'))]:
    A(fig(k, cap))

out = '\n'.join(P)
out = out.replace('Phase 35 hidden session', 'Hidden phase 10')
out = out.replace('Phase 35', 'Hidden phase 10')
out = re.sub(r'\n{4,}', '\n\n\n', out)
open('/home/claude/work/report_v3.md', 'w').write(out)
print('wrote report_v3.md', len(out.split('\n')), 'lines')
