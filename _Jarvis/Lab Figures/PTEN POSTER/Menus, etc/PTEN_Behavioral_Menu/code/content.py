# -*- coding: utf-8 -*-
"""The PTEN behavioral menu: one spec per figure page, every number taken from report_v3.md (2026-11-24).

Crop boxes are in the report figure's own PDF points (svgpdf/<id>.pdf; ids are the figure's order in the report
docx: 01 = Figure 1, 03 = Figure 2, 05 = Figure 3, 07 = Figure 4, 09 = 5, 11 = 6, 13 = 8, 15 = 9, 17 = 12, 19 = 13,
21 = 10, 23 = 11, 25 = 7, 27 = 14, 29 = 15, 31 = 16, 33 = 17, 35 = 18, 37 = 19, 39 = 20, 41 = 21, 43 = 22, 45 = 23,
47 = 24, 49 = 25, 65 = S8, 77 = S14).
"""

PAGES = []


def page(**kw):
    PAGES.append(kw)


# ------------------------------------------------------------------------------------------------ 1 learning
page(
    num=1, slug="learning_the_cue_rule", fig="Figure 1", kicker="Learning the cue rule", mode="side",
    question="Can they learn that the cue predicts the reward?",
    results=("Every Lo mouse took longer than every WT mouse to learn the cue rule (21 against 9 sessions), while Hi mice "
             "learned close to the WT rate: fewer KO cells, not more, meant slower learning."),
    legend=("01", (0, 271, 763, 284)), legend_scale=0.68,
    panels={
        "a": dict(src="01", clip=(0, 43, 266, 262),
                  h="Lo mice need 21 sessions to criterion against 9 in WT, with no overlap; Hi mice need 14"),
        "b": dict(src="01", clip=(266, 43, 521, 262),
                  h="Learning does not slow with % KO: the slowest learners have the fewest KO cells"),
        "c": dict(src="01", clip=(521, 43, 763, 262),
                  h="The KO groups miss in opposite directions: Lo learn slowly but keep the place, Hi learn fast but drop it"),
    },
    rows=[[dict(w=0.5, p=["a"]), dict(w=0.5, p=["b"])], [dict(w=0.62, p=["c"])]],
    how=("Sessions to criterion: training sessions until a mouse met the training criterion with the goal marked by a "
         "cue, so it measures a cue–reward association, not a place task. One number per mouse. M6 (WT, 27 "
         "sessions) is left out as an extreme outlier. b: each mouse against its % KO cells in the granule cell layer, WT "
         "at 0%; the curve is a quadratic that describes the shape, not a dose model. c: sessions to criterion against "
         "the latent place preference with the cue present (page 6). Brackets: Mann-Whitney."),
    what=("WT 8.8 ± 0.5 sessions (n 18, range 7–13); Lo 21.2 ± 2.1 (n 5, range 15–28; against WT "
          "P < 0.001, Hedges g 4.3); Hi 14.0 ± 2.8 (n 6, median 11.5, range 8–25; P 0.03); Lo against Hi P 0.08. "
          "Within the KO mice, % KO and sessions run against each other (r −0.52, P 0.10); within either cluster % KO "
          "explains nothing (r 0.14 and 0.04). Slow learning picks out Lo mice (AUC 0.96) but not Hi mice (AUC 0.66)."),
    reading=("Low KO load slows the cue–reward association; high load leaves it mostly intact. The mosaic fraction "
             "works more like a switch between two phenotypes than a dial on severity, and page 6 shows the other half: "
             "what each group does when cue and place disagree."),
    caveats=("Hi mice split: three sit inside the WT range (8, 9, 9 sessions) and three do not (14, 19, 25). Low KO, "
             "heterotopia and IED− status travel together, so these data cannot say which drives slow learning. The "
             "two mice without histology (M27, 8 sessions; M31, 27) decide whether Lo and Hi differ. The inverted U "
             "depends on counting WT as 0% KO."),
)

# ------------------------------------------------------------------------------------------------ 2 task and measures
page(
    num=2, slug="the_task_and_the_session_measures", fig="Figures 2 and 3", kicker="The task and the session measures",
    mode="below",
    question="What does the task look like, and what do the session measures say?",
    results=("With the cue on the goal no KO group is impaired; without it both KO groups earn fewer rewards per entrance "
             "from the trained location on, and at the last rotation Hi mice fall to 5.5 rewards against 15.2 in WT."),
    panels={
        "a": dict(src="03", clip=(0, 48, 452, 360),
                  h="Cue present: all three example mice run to the marked goal and collect rewards at every phase"),
        "b": dict(src="03", clip=(452, 40, 806, 357),
                  h="Cue present: no group is impaired; Lo mice move less but earn more per entrance"),
        "c": dict(src="05", clip=(0, 48, 452, 360),
                  h="Cue removed: the Hi mouse (M34) reaches the goal 44 times at phase 10 but earns 4 rewards"),
        "d": dict(src="05", clip=(452, 40, 806, 357),
                  h="Cue removed: both KO groups earn less per entrance from phase 7, and Hi mice collapse at phase 10"),
    },
    rows=[[dict(w=0.565, p=["a"]), dict(w=0.435, p=["b"])], [dict(w=0.565, p=["c"]), dict(w=0.435, p=["d"])]],
    how=("Every phase has a cued session (a beacon on the goal) and a hidden session about 32 minutes later at the same "
         "goal. Arenas: gray = the whole 30-minute path, colored = the 3 s before each reward, black dots = where rewards "
         "were triggered; solid circle = current goal, dashed = previous goal, dotted = trained goal (zone 1), light gray "
         "= not yet used; room view, the phase 7 goal upper right and later goals anticlockwise. Example mice: M22 (WT), "
         "M33 (Lo, 8.8% KO), M34 (Hi, 28.4% KO, IED+). Plots: mean ± SE across mice; letters mark P < 0.05 at that "
         "phase (L = Lo against WT, H = Hi against WT, × = Lo against Hi); shading = novel goal locations."),
    what=("Cued: no group effect on any measure (closest, goal entrances P 0.05); Hi against WT, nothing in 32 tests. Lo "
          "mice make fewer entrances at phase 9 (63 against 96, P 0.03) and earn more rewards per entrance at phase 10 "
          "(0.48 against 0.34, P 0.02). Hidden: group affects rewards (P 0.003), rewards per entrance (P 0.004) and time "
          "in goal (P 0.03). At phase 7 both KO groups already earn fewer rewards per entrance (Lo 0.21, Hi 0.23, WT 0.34; "
          "P 0.008 and 0.006). At phase 10 Hi mice earn 5.5 rewards against 15.2 (P 0.004), 0.14 per entrance against "
          "0.32 (P 0.006), and move faster in the goal zone (23.2 against 16.6 cm/s, P < 0.001)."),
    reading=("The cued sessions are the control: the same mice on the same days find a marked goal normally, so the "
             "hidden-goal loss is not motor, motivational or visual. The hidden deficit is present before any rotation; "
             "the Hi collapse comes at the last one."),
    caveats=("The example mice illustrate; the group plots carry the inference. Rewards, time in goal and rewards per "
             "entrance all depend on the 1.2 s stop, so they are not independent measures."),
)

# ------------------------------------------------------------------------------------------------ 3 change per phase
page(
    num=3, slug="change_across_the_rotations", fig="Figure 4", kicker="Change across the rotations", mode="side",
    question="Does performance change as the goal moves?",
    results=("Only without the cue: each rotation costs Hi mice 2.9 rewards and adds 2.1 cm/s to their goal-zone speed "
             "while WT stay flat, and with the cue no group declines on any measure."),
    legend=("07", (550, 30, 792, 52)), legend_scale=0.72,
    panels={
        "a": dict(src="07", clip=(14, 62, 396, 209),
                  h="Cue removed: Hi mice lose 2.9 rewards and 0.023 rewards per entrance with each rotation"),
        "b": dict(src="07", clip=(396, 62, 792, 209),
                  h="Cue removed: Lo mice lose goal time; Hi mice speed up in the goal zone by 2.1 cm/s per rotation"),
        "c": dict(src="07", clip=(14, 250, 396, 399),
                  h="Cue present, same mice and days: no group loses rewards; Lo mice gain rewards per entrance"),
        "d": dict(src="07", clip=(396, 250, 792, 399),
                  h="Cue present: goal time and goal-zone speed stay flat in every group"),
    },
    rows=[[dict(w=1.0, p=["a", "b", "c", "d"])]],
    how=("For each mouse, the least-squares slope across phases 7 to 10 (change per phase) of rewards, rewards per "
         "entrance, proportion of time in the goal zone and mean target speed (speed as the mouse enters and moves "
         "through the goal zone). Points are mice; bars are the group mean ± SE; beneath each group, the mean slope "
         "and its one-sample t test against zero. Group differences in slope: Mann-Whitney."),
    what=("Hidden: Hi rewards −2.90 per phase (P 0.003), rewards per entrance −0.023 (P 0.022), target speed "
          "+2.13 cm/s (P 0.005); Lo time in goal −0.0069 (P 0.004); WT flat on every measure (P 0.06 to 0.61). The Hi "
          "target-speed slope differs from WT's (+2.1 against +0.9 cm/s per phase, P 0.007). Cued: the one significant "
          "slope is Lo rewards per entrance, +0.071 per phase (P < 0.001); Hi flat on all four (P 0.06 to 0.55)."),
    reading=("The decline answers the goal moving, not the days passing: fatigue, satiety or drift would show in the cued "
             "sessions, which run on the same days, and they are flat. The Lo cued improvement is their slow acquisition "
             "still finishing."),
    caveats=("One WT mouse (M2) has an extreme target-speed slope (+8.5 cm/s per phase, from very few goal visits); a rank "
             "test is barely affected. The Hi group is flat from phase 8 to 9 (10.5 and 10.5 rewards), so with three novel "
             "locations a late drop cannot be told apart from a steady decline."),
)

# ------------------------------------------------------------------------------------------------ 4 place vs cue
page(
    num=4, slug="cue_against_place", fig="Figure 5", kicker="Cue against place, phase 8 with the cue", mode="side",
    question="When the cue and the remembered place disagree, which one wins?",
    results=("With the cue on the new goal, WT and Lo mice still favor the old place but Hi mice do not (−4.2 points), "
             "and the mice that weigh place most against the cue earn the most rewards at the last hidden rotation."),
    legend=("09", (5, 18, 280, 36)), legend_scale=0.7,
    panels={
        "a": dict(src="09", clip=(0, 59.6, 206, 240),
                  h="Against the cue, Hi mice give the old place half the WT share of runs (18% against 36%)"),
        "b": dict(src="09", clip=(206, 59.6, 380, 240),
                  h="WT and Lo mice prefer the old place to a never-used zone; Hi mice do not"),
        "c": dict(src="09", clip=(380, 59, 547, 240),
                  h="The more a mouse weighs place against cue at phase 8, the more it earns at phase 10 (ρ +0.62)"),
    },
    rows=[[dict(w=0.53, p=["a"]), dict(w=0.47, p=["b"])], [dict(w=0.5, p=["c"])]],
    how=("Visible phase 8: the cue sits on the new goal while the old (trained) goal is only a remembered place. Directed "
         "runs only (launched at least 20 cm from the zone), the first 10 in session order. a: old-place share (filled) = "
         "% of runs to the old place or the cue that went to the old place; open = the same share for a never-used zone "
         "against the cue (zones 3 and 4 averaged), joined by mouse. b: latent place preference = % of runs to the old "
         "place minus % to one never-used zone; stars, one-sample t against 0. c: old-place share against rewards at "
         "hidden phase 10, line through all 30 mice."),
    what=("Old-place share WT 36%, Lo 28%, Hi 18% (Hi against WT P 0.010; Lo against Hi P 0.049); the never-used baseline "
          "does not differ (22, 20, 25%). Latent preference WT +9.2 (P 0.007), Lo +12.0 (P 0.016), Hi −4.2 (P 0.58). "
          "Within the 11 KO mice, more KO goes with a lower old-place share (ρ −0.69, P 0.018). Old-place share "
          "predicts phase 10 rewards: ρ +0.62 (P < 0.001, n 30), within WT +0.46 (P 0.049), with group in the model "
          "P 0.018."),
    reading=("Hi mice are drawn to the cue rather than blind to place: they go to a never-used zone against the cue as "
             "often as WT, but the remembered place does not compete. The balance of place against cue at the first "
             "rotation forecasts the last hidden rotation, within WT as well as across groups."),
    caveats=("Three WT mice (M52, M54, M59) have phase 8 dated before phase 7; leaving them out changes no conclusion. The "
             "latent preference alone, without the cue in the comparison, does not predict phase 10 (ρ +0.25, P 0.19)."),
)

# ------------------------------------------------------------------------------------------------ 5 new vs old place
page(
    num=5, slug="new_place_against_old_place", fig="Figure 6", kicker="New place against old place, phase 8 without the cue",
    mode="side",
    question="With the cue gone, do they still remember the old place?",
    results=("Yes, every group does: without the cue all three groups go to both the new and the old place more than to a "
             "never-used zone, and the Hi mice's pull toward the old place returns to the WT level."),
    legend=("11", (5, 18, 280, 36)), legend_scale=0.7,
    panels={
        "a": dict(src="11", clip=(0, 59.6, 198, 240),
                  h="Every group holds both places: the new and the old place each draw more runs than a never-used zone"),
        "b": dict(src="11", clip=(198, 59.6, 386, 240),
                  h="Removing the cue brings back the Hi mice's pull toward the old place, in 5 of 6 mice"),
        "c": dict(src="11", clip=(386, 58, 547, 240),
                  h="The hidden phase 8 place pull does not forecast phase 10 (ρ −0.17)"),
    },
    rows=[[dict(w=0.53, p=["a"]), dict(w=0.47, p=["b"])], [dict(w=0.5, p=["c"])]],
    how=("Hidden phase 8, about 32 minutes after the cued session. Place pull = of the first 20 directed runs to any zone, "
         "% to a place minus % to one never-used zone (20 because the mice make fewer directed runs without the cue). "
         "a: new place filled, old place open; stars, one-sample t against 0. b: old-place pull over the first 10 runs "
         "with the cue (open) and without (filled), joined by mouse; above each group the paired t and the mice that went "
         "up and down. c: mean place pull against hidden phase 10 rewards."),
    what=("New place minus never-used: WT +8.7 (P 0.049), Lo +22.5 (P 0.015), Hi +13.5 (P 0.039). Old place: WT +10.3 "
          "(P 0.002), Lo +11.5 (P 0.13), Hi +10.4 (P 0.072). No group differs on any measure (all P ≥ 0.12). Old-place "
          "pull with and without the cue: WT +9.2 and +9.7, Lo +12.0 and +10.0, Hi −4.2 and +12.5 (5 of 6 up, "
          "P 0.15). Place pull against phase 10 rewards: ρ −0.17 (P 0.36)."),
    reading=("The place memory is there in Hi mice and a cue suppresses it. With page 6 this is a strategy bias toward the "
             "cue, not a lost spatial memory; it fits the last rotation, where the cue is gone and Hi mice reach the goal "
             "but do not settle."),
    caveats=("With six Hi mice the rise without the cue is a direction, not a significant effect, and one Hi mouse (M3) goes "
             "the other way. The claim is that the Hi pull becomes normal, not that it exceeds WT (Hi against WT P 1.00)."),
)

# ------------------------------------------------------------------------------------------------ 6 time at each zone
page(
    num=6, slug="time_at_each_zone", fig="Figure 7", kicker="Time at each zone, cue removed", mode="below",
    question="Do they favor the current goal over the zones that used to pay?",
    results=("WT favor the current goal at every hidden phase after the first rotation; Lo mice stop favoring any zone "
             "from phase 9 and Hi mice from phase 10, when their time at the goal falls to about half the WT level."),
    legend=("25", (80, 762, 760, 790)), legend_scale=0.62,
    panels={
        "a": dict(src="25", clip=(0, 60, 828, 278),
                  h="WT favor the current goal at every phase; only at the first rotation does the old goal draw as much time"),
        "b": dict(src="25", clip=(0, 280, 828, 500),
                  h="Lo mice stop favoring any zone at phase 9, when their current-goal time halves (1.7% against 3.4%)"),
        "c": dict(src="25", clip=(0, 503, 828, 748),
                  h="Hi mice still favor the goal at phase 9 but not at phase 10 (1.7% against 3.1% of the session)"),
    },
    rows=[[dict(w=1.0, p=["a"])], [dict(w=1.0, p=["b"])], [dict(w=1.0, p=["c"])]],
    how=("Hidden sessions: time in each of the four goal-sized zones, % of the session; zone k was the goal of phase k + 6. "
         "Colored bar with a star: the current goal; dark gray: former goals; light gray: zones not yet used. 'ns': a "
         "zone not significantly below the current goal (paired t). 'Zones differ': Friedman test across the four zones. "
         "'vs WT': current-goal time against WT (Mann-Whitney)."),
    what=("Zones differ in WT at every phase (P < 0.001). Lo: P 0.02 at phases 7 and 8, then 0.39 and 0.11. Hi: P 0.01 at "
          "phases 7 and 9, 0.14 at phase 8 and 0.46 at phase 10. Current-goal time against WT: Lo 1.7% against 3.4% at "
          "phase 9 (P 0.015); Hi 1.7% against 3.1% at phase 10 (P 0.017). In WT at phase 10 the trained zone comes "
          "closest (P 0.06). With the cue every group favors the current "
          "goal at every phase (Friedman P ≤ 0.02)."),
    reading=("Losing the goal is specific to the hidden sessions and comes one rotation earlier in Lo than in Hi mice. In Lo "
             "mice at phase 9 the time moves to the original trained zone; in Hi mice at phase 10 it spreads across the "
             "zones."),
    caveats=("The Lo shift to the trained zone is driven by two of five mice (M8, M10). Zone time is not accuracy: KO mice "
             "spend less time in all four zones, so share and absolute time can disagree."),
)

# ------------------------------------------------------------------------------------------------ 7 getting there
page(
    num=7, slug="getting_to_the_goal", fig="Figure 12 and Supplementary Figure S8", kicker="Getting to the goal",
    mode="side",
    question="Is getting to the goal intact?",
    results=("Yes: Lo and Hi mice aim at the goal, launch toward it and decelerate on approach just like WT, with the cue "
             "and without it, so the deficits lie at and after arrival."),
    panels={
        "a": dict(src="17", clip=(0, 28.7, 253, 209),
                  h="Cue removed, phase 10: all groups trace the same approach, speeding up from the wall and slowing into the zone"),
        "b": dict(src="17", clip=(253, 28.7, 504, 209),
                  h="Cue present: the three approach profiles are almost superimposed"),
        "c": dict(src="65", clip=(0, 49.6, 312, 228),
                  h="With the cue WT aim at the goal from 34 cm away; without it only from 21 cm"),
        "d": dict(src="65", clip=(312, 45.6, 547, 228),
                  h="Every Lo and Hi mouse shifts like WT, reaching further with the cue"),
    },
    rows=[[dict(w=0.5, p=["a"]), dict(w=0.5, p=["b"])], [dict(w=0.56, p=["c"]), dict(w=0.44, p=["d"])]],
    how=("a, b: every directed run into the current goal at phase 10, cut where it entered the zone, speed scaled to that "
         "run's own approach maximum and binned by distance from the goal center (2 cm); line = mean over mice, band = SE; "
         "dashed line at 70% of the maximum (the braking criterion); gray = the goal zone. c, d: goal-directedness = mean "
         "cosine of the angle between the direction of travel and the direction to the goal, over running frames "
         "(> 5 cm/s) off the wall; reach = where it first falls below 0.1 (phases 7–10 pooled); filled = cued, open "
         "= hidden; paired t."),
    what=("Approach shape, Hi against WT, permutation test over the whole profile: cue removed P 0.83 (largest gap 8.3 "
          "points), cue present P 0.22; hidden minus cued P 0.57. Reach with and without the cue: WT 33.8 and 21.4 cm, Lo "
          "30.3 and 20.5, Hi 31.7 and 19.4 (P < 0.001, 0.027, 0.001); further with the cue in 17 of 19 WT, 5 of 5 Lo and 6 "
          "of 6 Hi mice. Neither KO group differs from WT in either condition (all P ≥ 0.27). Launch distance, "
          "straightness and run duration also match WT."),
    reading=("A cued goal is approached by beaconing from across the arena; a hidden goal locally, by reaching the right "
             "region and then turning in. KO mice do both normally. Whishaw, Cassel and Jarrard (1995) took deceleration on "
             "approach as the sign that an animal expects the goal at a place; on the shape of the approach these mice pass."),
    caveats=("Without the cue the profiles are more ragged in every group because there are a quarter as many runs. Each run "
             "is scaled to its own maximum, so the height of a profile reflects how alike the approaches are, not how fast "
             "the mouse runs."),
)

# ------------------------------------------------------------------------------------------------ 8 arrival
page(
    num=8, slug="arriving_at_the_goal", fig="Figure 8", kicker="Arriving at the goal", mode="side",
    question="Do they stop when they reach the hidden goal?",
    results=("No: at the last rotation Hi mice cross the hidden goal at 16.4 cm/s through the 1.2 s that earns a reward, "
             "against 11.5 in WT, while at the trained location and with the cue they slow like WT."),
    panels={
        "a": dict(src="13", clip=(12, 30, 504, 229.5),
                  h="At phase 10, WT and Lo runs end in a knot inside the goal; the Hi mouse's runs carry on through it"),
        "b": dict(src="13", clip=(12, 233, 504, 285),
                  h="One typical run each: WT and Lo slow inside the zone, the Hi run crosses it at full speed"),
        "c": dict(src="13", clip=(0, 305, 504, 511), mask=[(0, 349, 12, 366)],
                  h="Only at the last hidden rotation do Hi mice keep moving through the reward window (P < 0.001)"),
    },
    rows=[[dict(w=1.0, p=["a", "b", "c"])]],
    how=("a: every directed run into the hidden goal at phase 10 for one mouse per group (M22 WT, M10 Lo, M34 Hi), centered "
         "on the goal with the approach from the left, colored by speed; the dot is where the mouse was 1.2 s after "
         "entering (green inside = reward, red outside = miss). b: the run whose slowing ratio is closest to that mouse's "
         "median, a dot every 0.1 s, so dots bunch where the mouse is slow; slowing ratio = speed over the 1.2 s after "
         "entry divided by speed 1.5 to 0.5 s before. c: mean speed around every entry into the current goal, aimed runs "
         "and chance crossings alike, mean ± SE over mice; shading = the 1.2 s reward window; P = Hi against WT on the "
         "mean speed inside it (Mann-Whitney)."),
    what=("Speed through the reward window, Hi against WT: trained location 11.1 against 10.1 cm/s (P 0.18); last hidden "
          "rotation 16.4 against 11.5 (P 0.0005); cued last rotation 11.8 against 10.7 (P 0.18). It holds on aimed runs "
          "(17.3 against 12.4, P 0.001) and on chance crossings (14.9 against 10.6, P 0.003). At hidden phase 10 Hi mice "
          "enter faster (22.1 against 14.7 cm/s, P 0.003), stay half as long (0.51 against 1.11 s, P 0.006) and are "
          "rewarded on 16% of directed runs against 34% (P 0.020) and 45% in Lo."),
    reading=("They reach the place and pass through it. The deficit is as strong on chance crossings as on aimed runs, so it "
             "is not momentum from a fast approach; it is what a failure to recognize the place should look like. This is "
             "where Lo and Hi differ most clearly (entry speed, time in goal and reward per run, P 0.013 to 0.030)."),
    caveats=("The example mice are typical, not proof. Speed in the window, time in goal, rewards per entrance and the "
             "slowing ratio all express one rule (stop for 1.2 s): one result seen from several sides."),
)

# ------------------------------------------------------------------------------------------------ 9 slowing and pausing
page(
    num=9, slug="slowing_and_pausing", fig="Figure 9", kicker="Slowing and pausing across the rotations", mode="below",
    question="Where does stopping fail, and when does it start?",
    results=("Across the hidden rotations WT mice pause slightly more and Hi mice steadily less (59 against 134 s by phase "
             "10), and the lost pauses are out in the arena, not at the goal."),
    legend=("15", (150, 25, 360, 42)), legend_scale=0.75,
    panels={
        "a": dict(src="15", clip=(0, 50, 250, 185), mask=[(0, 50, 13, 66)],
                  h="With each hidden rotation Hi mice slow less on entering the goal, until at phase 10 they barely slow; cued, no difference"),
        "b": dict(src="15", clip=(250, 50, 504, 185),
                  h="Total pausing diverges over hidden rotations, WT up and Hi down (P 0.036); flat with the cue (P 0.88)"),
        "c": dict(src="15", clip=(12, 208, 504, 360),
                  h="Pausing at the goal and around it is the same in every group; the whole loss is in the open interior (P 0.007)"),
    },
    rows=[[dict(w=0.5, p=["a"]), dict(w=0.5, p=["b"])], [dict(w=1.0, p=["c"])]],
    how=("Slowing ratio: mean speed over the 1.2 s after entry divided by the mean over 1.5 to 0.5 s before, on directed "
         "runs (1 = no slowing). Pause: 1.2 to 10 s below 3 cm/s, away from the wall (beyond 0.8 of the arena radius is "
         "excluded, so none of this is wall-hugging). c splits hidden pause time by distance from the current goal: inside "
         "the zone (< 1 zone radius), the ring around it (1 to 2.5 radii), the open interior (> 2.5 radii), with the cued "
         "open interior as the control. Faint points are mice, lines group means ± SE; beneath each panel, the mean "
         "per-mouse slopes and the Mann-Whitney comparing them, Hi against WT; numbers above a phase compare Hi and WT."),
    what=("Slowing ratio, hidden: WT 0.58, 0.70, 0.72, 0.74; Hi 0.61, 0.70, 0.87, 0.91 (phase 10 P 0.009; within Hi +0.11 "
          "per phase, P 0.033). Pause time slopes WT +5.9, Hi −14.4 s per phase (P 0.036); at phase 10 134 against 59 s "
          "(P 0.006): fewer pauses (49.6 against 28.0, P 0.024) and shorter ones (2.71 against 2.03 s, P 0.002). Open "
          "interior: WT 78.5 to 101.8 s, Hi 79.7 to 37.7 s (+7.0 against −12.5 s per phase, P 0.007; phase 10 P 0.003); "
          "inside the goal P 0.69, around it P 0.83; cued open interior P 0.98."),
    reading=("The groups do not differ in how much they stop at the goal; they differ, in opposite directions, in how much "
             "they stop everywhere else. WT stop more often out in the arena as the goal keeps moving, checking candidate "
             "places; Hi mice stop doing it. That is a change in search, and it grows with each rotation (page 13 shows the "
             "lost pauses are at former goals)."),
    caveats=("Three of six Hi mice sit inside the WT range at phase 10 (WT 50 to 283 s), so this is a shifted distribution, "
             "not every mouse. The Hi decline on its own is a trend (−14.4 s per phase, P 0.079, 5 of 6 down); the "
             "contrast with WT and its absence with the cue carry it. The pauses Hi mice still make land as close to the "
             "goal as WT's, which at n 6 cannot rule out a coarser memory."),
)

# ------------------------------------------------------------------------------------------------ 10 braking
page(
    num=10, slug="braking_at_the_goal", fig="Figure 13", kicker="Braking at the goal", mode="side",
    question="Do they brake at the goal the way a mouse that expects it should?",
    results=("Not without the cue: removing it costs Hi mice more than twice WT's braking at the goal (6.8 against 2.8 "
             "events per 10 m), and only 38% of their runs contain a slowdown; at former goals they brake as often as WT."),
    panels={
        "a": dict(src="19", clip=(0, 51.6, 166, 220),
                  h="Removing the cue cuts braking at the goal in every group, most in Hi mice (change P 0.021)"),
        "b": dict(src="19", clip=(166, 51.6, 334, 220),
                  h="Without the cue fewer Hi runs contain any slowdown (38% against 56%)"),
        "c": dict(src="19", clip=(334, 51.6, 504, 220),
                  h="When Hi mice do brake, they start further from the goal (13.7 against 11.5 cm)"),
    },
    rows=[[dict(w=0.5, p=["a"]), dict(w=0.5, p=["b"])], [dict(w=0.5, p=["c"])]],
    how=("Phase 10, each mouse cued (left point) and hidden (right point); P beneath each pair: paired t; above each panel: "
         "Mann-Whitney on the change, Hi against WT. Braking event: a fall from a local speed maximum of at least 12 cm/s to "
         "below half that speed within 1 s, placed where the mouse ended up slow and assigned to the nearest kind of zone "
         "within 2.5 zone radii; counted per 10 m of path off the wall (Hi mice cover about 29% more ground). b: share of "
         "directed runs with any braking. c: distance from the goal center at which a braking run first fell below 70% of "
         "its approach maximum. Diamonds mark IED+ mice."),
    what=("Hidden phase 10, braking rate at the goal: WT 9.15, Lo 7.96, Hi 6.05 per 10 m (Hi against WT P 0.004). Runs with "
          "any braking: 56.2, 51.3, 38.4% (P 0.045). Braking distance: 11.5, 13.2, 13.7 cm (P 0.050). Cued phase 10: rates "
          "11.93, 11.93, 12.81 (P 0.30); distance 10.2 cm in WT and Hi (P 0.98). Phase 7: identical (11.44 against 11.02, "
          "P 0.64). At former goals: 15.2, 15.8, 14.7 per 10 m (P 0.93)."),
    reading=("This is the test Whishaw, Cassel and Jarrard (1995) used; their fimbria-fornix rats passed it, and these Hi mice "
             "fail it, only at the last hidden rotation. They brake further out and over a broader region rather than at a "
             "wrong spot, which reads as uncertainty about where the goal is. At former goals they slow as often as WT: they "
             "have not stopped checking, they have stopped committing."),
    caveats=("The 12 cm/s, half-speed and 70% thresholds were set once and not tested for sensitivity. Braking distance is "
             "measured on the runs that braked, which Hi mice supply fewer of, and P 0.050 sits on the line."),
)

# ------------------------------------------------------------------------------------------------ 11 set to rule out
page(
    num=11, slug="the_set_to_rule_out", fig="Figure 10", kicker="The set to rule out", mode="side",
    question="When the goal has moved, do they search the places that used to pay?",
    results=("WT and Lo mice check the former goals more with every rotation (82 and 88 s by phase 10) while Hi mice barely "
             "do (28 s; +25.3 against +9.6 s per phase, P 0.003), and with the cue the groups behave alike."),
    legend=("21", (130, 28, 340, 37)), legend_scale=0.95,
    panels={
        "a": dict(src="21", clip=(0, 48, 258, 238),
                  h="Goal hidden: as former goals pile up, WT and Lo mice spend more time at them; Hi mice fall behind"),
        "b": dict(src="21", clip=(258, 48, 475, 238),
                  h="Goal cued: Hi mice work through the former goals almost as much as WT (P 0.198)"),
    },
    rows=[[dict(w=1.0, p=["a", "b"])]],
    how=("Each zone was the goal of one phase, so across hidden phases 7 to 10 the former goals number 0, 1, 2, 3. Every pause "
         "(1.2 to 10 s below 3 cm/s, off the wall) is assigned to the nearest kind of zone within 2.5 zone radii: current "
         "goal, former goal, never-used zone, or none. Pause time at former goals per session, hidden (a) and cued (b). "
         "Faint points are mice, lines group means ± SE; beneath each panel, the mean per-mouse slopes and the "
         "Mann-Whitney comparing them, Hi against WT; numbers above a phase are Hi against WT at that phase."),
    what=("Hidden: WT 0, 33, 42, 82 s; Lo 0, 31, 55, 88; Hi 0, 15, 26, 28; slopes +25.3, +28.8, +9.6 s per phase (Hi against "
          "WT P 0.003). Cued: slopes +18.6, +18.6, +15.0 (P 0.198). Controls from the same pauses: never-used zones fall "
          "at the same rate in WT and Hi (−19.0 against −21.2 s per phase, P 0.64); the current goal does not "
          "differ (P 0.93); pausing away from every zone does not differ (P 0.60)."),
    reading=("WT mice treat the history as a list to work through, and the list grows; Hi mice do not add to it. The deficit "
             "is specific to former goals, scales with how many there are, and disappears when a beacon removes the need to "
             "hold the set in mind: the shape of a limit on holding and testing candidate places. It is the strongest "
             "behavioral result in the report."),
    caveats=("Lo mice do not differ from WT at former goals at any phase (P 0.33 to 0.95) or in slope (P 1.00), so Lo "
             "perseveration is not a group feature. Working memory and pattern separation cannot be told apart here."),
)

# ------------------------------------------------------------------------------------------------ 12 pause maps
page(
    num=12, slug="where_they_pause", fig="Figure 11", kicker="Where they pause, cue on and off", mode="side",
    question="What does the search look like in one session, and what does removing the cue do to it?",
    results=("Removing the cue makes WT mice pause more (+30 s) and Hi mice pause less (−34 s; P 0.043); without it the "
             "typical WT and Lo mice work through the former goals while the typical Hi mouse barely stops."),
    legend=("23", (285, 5, 518, 22)), legend_scale=0.75,
    panels={
        "a–f": dict(src="23", clip=(0, 28, 258, 497),
                         h="Typical mice at phase 10: without the cue WT and Lo pause at the current and former goals; the Hi mouse makes 21 short pauses"),
        "g": dict(src="23", clip=(258, 51, 518, 262),
                  h="Cue removed, Hi mice lose their pauses at former goals (P 0.002); at the current goal they match WT"),
        "h": dict(src="23", clip=(258, 306.5, 518, 505),
                  h="Removing the cue raises WT pausing and lowers Hi pausing (P 0.043)"),
    },
    rows=[[dict(w=0.56, p=["a–f"]), dict(w=0.44, p=["g", "h"])]],
    how=("a–f: one session per mouse per condition at phase 10 (cue present left, removed right), for the mouse of each "
         "group closest to its group median on five of the report's measures (M9 WT, M8 Lo, M5 Hi), chosen before drawing. "
         "Gray = the path; each marker a pause, sized by duration: filled black at the current goal, amber ring at a former "
         "goal, pale dot in the open interior; the dashed arc marks the wall band the pause measure excludes. g: pause time "
         "by kind of place, cue removed, every mouse, mean ± SE. h: change in total pause time on removing the cue, per "
         "mouse; P under each group: paired t; bracket: Mann-Whitney on the change."),
    what=("Cue removed: M9 57 pauses and 129 s, M8 52 and 125 s, M5 21 and 37 s (cue present: 50 and 111 s, 34 and 129 s, "
          "40 and 74 s). Pause time Hi against WT: former goals P 0.002, current goal P 0.25, open interior P 0.086. Change "
          "on removing the cue: WT +30 s (P 0.024), Lo P 0.52, Hi −34 s (P 0.29); Hi against WT P 0.043."),
    reading=("The within-animal control holds the account together: nothing about locomotion, motivation or vision changes "
             "between the two sessions, only whether the location has to be held in mind. WT answer that demand by stopping "
             "more; Hi mice stop less. The Hi mouse's goal pauses sit on the rim of the zone rather than inside it."),
    caveats=("The example mice are typical by a stated rule, not proof; g and h carry the inference. The Hi change on its own "
             "is not significant (P 0.29); the difference from WT is."),
)

# ------------------------------------------------------------------------------------------------ 13 running
page(
    num=13, slug="what_they_do_instead", fig="Figure 14", kicker="What they do instead", mode="side",
    question="If Hi mice stop searching, what do they do with the session?",
    results=("They run: without the cue Hi mice speed up where WT and Lo slow down (+1.69 against −1.80 cm/s at phase "
             "10, P 0.001), and they enter the goal as often as WT while collecting a third of the rewards."),
    panels={
        "a": dict(src="27", clip=(0, 43.2, 205, 216),
                  h="WT and Lo run slower without the cue at every phase; Hi mice run faster without it at phase 10"),
        "b": dict(src="27", clip=(205, 43.2, 409, 216),
                  h="Within each mouse, removing the cue slows WT and Lo but speeds Hi mice up at phase 10 (P 0.001)"),
        "c": dict(src="27", clip=(409, 43.2, 605, 216),
                  h="At hidden phase 10 Hi mice enter the goal as often as WT (43 against 49) but earn a third of the rewards"),
    },
    rows=[[dict(w=0.5, p=["a"]), dict(w=0.5, p=["b"])], [dict(w=0.5, p=["c"])]],
    how=("a: mean speed per probe session by phase, cued dashed and hidden solid, mean ± SE. b: hidden minus cued "
         "speed at the same phase within each mouse (below 0 = slower without the cue); faint points are mice. c: goal-zone "
         "entries against rewards at hidden phase 10, one point per mouse; reference lines at one reward per three and per "
         "six entries."),
    what=("Hidden minus cued at phase 10: WT −1.80 cm/s (P < 0.001), Lo −1.13 (P 0.020), Hi +1.69 (Hi against WT "
          "P 0.001). At phase 7 all three slow without the cue (−2.42, −1.30, −1.17). Hidden phase 10: 10.2 "
          "against 7.9 cm/s (P 0.025) and 71% against 66% of the session in the wall band; entries 43 against 49 (P 0.77), "
          "rewards 5.5 against 15.2 (P 0.004)."),
    reading=("Hi mice pass through the right place at the right rate, too fast to collect, because the reward needs 1.2 s "
             "still. Dropping the search of former goals did not clear their path; it removed their only systematic route "
             "to the answer. Three strategies, not three severities: WT check the known places; Lo are deliberate but poorly "
             "aimed; Hi know the goal but abandon the search."),
    caveats=("Running more and pausing less are linked, so this page and page 11 describe one change of mode, not two "
             "separate results."),
)

# ------------------------------------------------------------------------------------------------ 14 after a miss
page(
    num=14, slug="after_a_miss", fig="Figure 15", kicker="After a miss", mode="side",
    question="Do they know where the goal is: do they come back after a miss, and where do they pause?",
    results=("Hi mice know where the goal is: after a miss they come back as often as WT (10.5% against 8.8%) and pause "
             "near it as often; Lo mice rarely come back (2.0%) and pause near the wrong zones."),
    panels={
        "a": dict(src="29", clip=(0, 64, 240, 252),
                  h="After a miss WT and Hi mice return to the current goal more than to other zones; Lo mice less"),
        "b": dict(src="29", clip=(240, 64, 475, 252),
                  h="WT and Hi mice pause most near the current goal; Lo mice near the other zones"),
        "c": dict(src="29", clip=(0, 284, 240, 465),
                  h="At phase 10 Hi mice pause about half as often as WT (28 against 50 per session)"),
        "d": dict(src="29", clip=(240, 284, 475, 465),
                  h="Hi mice leave the goal faster at phases 9 and 10 (23.4 against 19.0 cm/s at phase 10)"),
    },
    rows=[[dict(w=0.5, p=["a"]), dict(w=0.5, p=["b"])], [dict(w=0.5, p=["c"]), dict(w=0.5, p=["d"])]],
    how=("Hidden phases 8–10. Miss: an exit from the current goal (beyond 1.3 zone radii) without a reward; return = "
         "re-entry within 3 s; the control is the same measure after leaving any of the other three zones, which corrects "
         "for how active a mouse is. Pause: 1.2 to 10 s below 3 cm/s, off the wall; near a zone if within 2.5 zone radii. "
         "a, b: each mouse's rate at the current goal (filled) and the mean over the other zones (open); stars: paired t. "
         "c, d: by hidden phase, mean ± SE; † Hi against WT, ‡ Hi against Lo, § Lo against WT "
         "(Mann-Whitney P < 0.05)."),
    what=("Returns within 3 s of a miss: WT 8.8%, Lo 2.0%, Hi 10.5% (Lo against WT P 0.006; Lo against Hi P 0.008); to other "
          "zones 3.9, 4.3, 4.6%. Pauses near the current goal 27, 14, 28% (Lo against WT P 0.001); near each other zone 19, "
          "24, 18%. Within groups, current against other: returns WT P 0.0002, Hi P 0.025, Lo lower (P 0.06); pauses WT "
          "P 0.004, Lo lower (P 0.019), Hi P 0.26. Phase 10: 28 against 50 pauses (P 0.024); exit speed 23.4 against 19.0 "
          "cm/s (P 0.017; also faster at phase 9, P 0.043)."),
    reading=("Two different failures. Lo mice do not know where the goal is once it has moved, but stop normally when they "
             "reach it. Hi mice know roughly where it is and return to it, but do not settle. With the cue Lo mice return to "
             "the goal more than to other zones (9.9% against 2.9%), so their hidden pattern is about remembering the place."),
    caveats=("With a 5 s window the Lo result holds (P 0.024); with 10 s it weakens (P 0.09). Lo mice also return less "
             "often than WT with the cue (9.9% against 16.7%), so part of the gap is their lower activity. The Hi phase 10 "
             "differences rest on several tests near P 0.02."),
)

# ------------------------------------------------------------------------------------------------ 15 phase 10 zones
page(
    num=15, slug="last_rotation_zones", fig="Figure 16", kicker="The last hidden rotation: zones", mode="below",
    question="At phase 10, where do they spend their time, and does it follow % KO?",
    results=("At hidden phase 10 Hi mice visit the current goal as often as WT but stay less than the 1.2 s a reward needs, "
             "and the more KO cells a mouse has, the fewer rewards it earns per entry (r −0.75)."),
    panels={
        "a": dict(src="31", clip=(0, 77, 448, 322),
                  h="WT spend more time at the current goal than at the previous one; Hi mice split their time between them"),
        "b": dict(src="31", clip=(448, 77, 726, 322),
                  h="Hi mice stay 0.76 s per entry, under the 1.2 s a reward needs (WT 1.16 s, P 0.04)"),
        "c": dict(src="31", clip=(726, 77, 1010, 322),
                  h="Hi mice enter the current goal as often as WT (P 0.77)"),
        "d": dict(src="31", clip=(100, 421.8, 502, 668), mask=[(117, 421, 500, 432)],
                  h="Time at the previous goal rises with % KO (ρ +0.62) and doubles in IED+ mice"),
        "e": dict(src="31", clip=(502, 421.8, 910, 668), mask=[(519, 421, 910, 432)],
                  h="Rewards per entry fall with % KO (r −0.75, P 0.01)"),
    },
    legend=("31", (280, 330, 735, 350)), legend_scale=0.62,
    rows=[[dict(w=0.42, p=["a"]), dict(w=0.29, p=["b"]), dict(w=0.29, p=["c"])],
          [dict(w=0.49, p=["d"]), dict(w=0.51, p=["e"])]],
    how=("Hidden phase 10. a: time in each zone, % of the session, each mouse a point (diamonds IED+), group mean ± SE. "
         "b: time per entry into the current goal; line at the 1.2 s stop a reward needs. c: entries into the current goal. "
         "d, e: against % KO cells, line and 95% band through the KO mice only, WT drawn at 0% for reference and not in the "
         "fit (Lo green, Hi red, diamonds IED+)."),
    what=("Current against previous goal: WT current higher (P < 0.001), Hi equal (P 0.50); Hi share at the previous goal "
          "29% against 20% (P 0.06). Per entry WT 1.16 s, Lo 1.07, Hi 0.76 (Hi against WT P 0.04); five of six Hi mice "
          "average under 1 s. Rewards per entry 0.32, 0.31, 0.14 (P 0.006). Previous-goal time against % KO ρ +0.62 "
          "(P 0.04); IED+ against IED− 1.7% against 0.9% (P 0.04). Rewards per entry against % KO r −0.75 "
          "(P 0.01)."),
    reading=("By phase 10 Hi mice no longer favor the new location and do not stop when they are in it: mainly a failure to "
             "update the current goal. Lo mice reach the goal less often but stop normally when they do."),
    caveats=("All IED+ mice are Hi, so % KO and IED status cannot be separated. The KO percentages form two clusters, so a "
             "correlation here restates the Lo against Hi difference rather than showing a graded dose."),
)

# ------------------------------------------------------------------------------------------------ 16 phase 10 performance
page(
    num=16, slug="last_rotation_performance", fig="Figure 17", kicker="The last hidden rotation: performance",
    mode="below",
    question="Does % KO predict performance, and in which phase?",
    results=("Only at the last hidden rotation: there Hi mice move faster in the goal zone (23.2 against 16.6 cm/s) and earn "
             "fewer rewards per entrance (0.14 against 0.32), while Lo mice match WT per entrance; earlier, % KO predicts "
             "nothing."),
    panels={
        "a": dict(src="33", clip=(58, 45, 319, 262), h="Goal-zone speed rises with % KO (ρ +0.75, P 0.007)"),
        "b": dict(src="33", clip=(319, 45, 581, 262), h="Rewards per entrance fall with % KO (ρ −0.75, P 0.008)"),
        "c": dict(src="33", clip=(581, 45, 840, 262), h="Rewards lean the same way (ρ −0.51, P 0.11)"),
        "d": dict(src="33", clip=(13, 325, 231, 557), h="Hi mice earn 0.14 rewards per entrance against 0.32; Lo match WT"),
        "e": dict(src="33", clip=(231, 325, 454, 557), h="Hi mice earn 5.5 rewards against 15.2 in WT"),
        "f": dict(src="33", clip=(454, 325, 673, 557), h="Hi mice cross the goal zone at 23.2 cm/s against 16.6"),
        "g": dict(src="33", clip=(673, 325, 892, 557), h="Hi mice run faster overall; Lo mice slower"),
    },
    rows=[[dict(w=1 / 3.0, p=["a"]), dict(w=1 / 3.0, p=["b"]), dict(w=1 / 3.0, p=["c"])],
          [dict(w=0.25, p=["d"]), dict(w=0.25, p=["e"]), dict(w=0.25, p=["f"]), dict(w=0.25, p=["g"])]],
    how=("Hidden phase 10. a–c: each measure against % KO cells, Spearman across the 11 KO mice with histology; blue band "
         "= WT mean ± SE; line through the KO mice. d–g: the same measures by group, each mouse a point (diamonds IED+), bars mean "
         "± SE; brackets: Mann-Whitney."),
    what=("Against % KO: target speed ρ +0.75 (P 0.007), rewards per entrance −0.75 (P 0.008), mean speed +0.67 "
          "(P 0.02), rewards −0.51 (P 0.11). By group: rewards per entrance WT 0.32, Lo 0.31, Hi 0.14 (Hi against WT "
          "P 0.006); rewards 15.2, 9.6, 5.5 (P 0.004); target speed 16.6, 15.3, 23.2 cm/s (P < 0.001); mean speed 7.9, 5.9, "
          "10.2 (P 0.03). At phases 7 to 9 and in every cued session, no correlation with % KO reaches P 0.05 (nearest "
          "P 0.07)."),
    reading=("% KO tracks behavior only where Lo and Hi part, at the last hidden rotation; in the cued sessions it tracks "
             "nothing. It behaves as a step between the groups rather than a graded dose."),
    caveats=("No mice sit between 9.5% and 20.2% KO, so a correlation cannot show grading within either cluster."),
)

# ------------------------------------------------------------------------------------------------ 17 slopes
page(
    num=17, slug="does_it_scale_with_the_load", fig="Figure 18", kicker="Does it scale with the load?", mode="side",
    question="Gathered together, which measures change with each rotation, and which do not?",
    results=("The groups part only on what grows with the load: time at former goals (P 0.003) and total pausing (P 0.036) "
             "diverge across rotations, while pausing at never-used zones and at the current goal does not (P 0.64, 0.93)."),
    panels={
        "a": dict(src="35", clip=(25, 41, 522, 280),
                  h="Ranked by change per rotation, the two measures that separate Hi from WT are both about pausing at places that used to pay"),
        "b": dict(src="35", clip=(0, 325, 336, 508),
                  h="Every Hi mouse turns fewer directed runs into rewards at each rotation; WT vary widely"),
        "c": dict(src="35", clip=(336, 325, 522, 508),
                  h="The Hi decline needs the hidden goal: cued, their slopes are flat"),
    },
    rows=[[dict(w=1.0, p=["a"])], [dict(w=0.62, p=["b"]), dict(w=0.38, p=["c"])]],
    how=("a: every measure with a slope across hidden phases 7–10: per-mouse least-squares slope, divided by the SD of "
         "the per-mouse slopes for that measure so different units share one axis; points are group means ± SE; P = "
         "Hi against WT on the unscaled slopes (Mann-Whitney). b: share of directed runs to the current goal that end in a "
         "reward, each mouse thin and the group mean thick. c: each mouse's slope of that share across phases 7–10, hidden "
         "circles and cued squares, bars group means."),
    what=("Slopes, Hi against WT: former-goal pause time P 0.003, total pause time P 0.036, slowing ratio P 0.069, rewards "
          "P 0.098, time in goal P 0.198, never-used zones P 0.642, current goal P 0.926. Reward per directed run: all six "
          "Hi mice fall (−5.1 ± 0.6 points per phase, P < 0.001); WT −1.1 ± 2.0 (P 0.58, range "
          "−13.6 to +14.3); Lo +5.5 ± 3.1. Per mouse, Hi against WT P 0.22, against Lo P 0.017; per run, odds "
          "ratio per phase 0.79 against WT (P 0.016) and 0.60 against Lo (P 0.0001). Cued: Hi flat (+3.3 ± 2.2)."),
    reading=("The number of never-used zones falls across the rotations and all groups drop them alike; the current goal is "
             "one place throughout and all groups treat it alike. Only the measure that tracks the growing set separates "
             "them, which a general loss of pausing, motivation or locomotion would not respect. Lo mice sit with WT on "
             "every row: the Hi deficit appears above a threshold of KO load."),
    caveats=("The per-run model uses every run, but with 5 or 6 mice per KO group its clustered errors are approximate; the "
             "per-mouse test is the conservative one."),
)

# ------------------------------------------------------------------------------------------------ 18 theta by layer
page(
    num=18, slug="theta_csd_by_layer", fig="Figure 19 and Supplementary Figure S14", kicker="Theta CSD by layer",
    mode="below",
    question="Where in the dentate gyrus is the theta current changed, and what does CNO do to it?",
    results=("Hi KO mice carry about twice the WT theta current, concentrated in the lower blade's granule cell layer "
             "(GCL2) and middle molecular layer (MML2); CNO brings GCL2 back to WT and removes about half of the MML2 "
             "excess."),
    panels={
        "a": dict(src="37", clip=(0, 24, 590, 315),
                  h="By KO level: Hi mice peak at GCL2 and MML2 at baseline, and CNO pulls that peak down toward WT"),
        "b": dict(src="77", clip=(0, 24, 590, 315),
                  h="By IEDs: the excess is largest in the IED+ mice (GCL2 0.058 and MML2 0.055 against about 0.02)"),
    },
    rows=[[dict(w=1.0, p=["a"])], [dict(w=1.0, p=["b"])]],
    how=("Theta CSD per layer = the mean of the recording's channels labeled with that layer, at baseline and after CNO; "
         "layers run down the probe from CA1 to the lower (infrapyramidal) blade. Mean ± SE across mice; shaded row: "
         "the WT hilus, the reference. Stars: GEE clustered by mouse against the WT hilus (one star P < 0.05; two stars, "
         "also after Holm within the panel). WT 10 (8 after CNO), Lo 6, Hi 7; IED+ 5, KO without IEDs 8. M26 is excluded "
         "from all CSD (a problem after surgery)."),
    what=("4-layer average at baseline: WT 0.019, Lo 0.026, Hi 0.037 (Hi against WT P 0.043); Hi is 2.7 times WT at MML2 "
          "and 2.5 times at GCL2, against 1.3 and 1.2 times at MML1 and GCL1. CNO: Hi −22% (6 of 7 fall, P 0.012; "
          "group × drug P 0.009); WT +12% (P 0.19). Share of the excess CNO removes: GCL2 Hi 62%, IED+ 54%; MML2 47% "
          "and 46%. IED+ MML2 stays above WT after CNO (0.035 against 0.014, P 0.019). Lo mice: GCL2 only (0.035 against "
          "0.019, P 0.031)."),
    reading=("Silencing the DREADD-expressing granule cells returns the current at GCL2, where the KO cell bodies sit, to "
             "WT: that part is driven by their activity. MML2 is where the medial perforant path meets the KO cells' "
             "enlarged, spine-rich dendrites; that structure does not change when firing falls, so part of the synaptic "
             "excess remains."),
    caveats=("Within the KO mice alone no layer tracks % KO (r +0.10 to +0.36); the relation rests on the step from WT to KO. "
             "WT mice also carry the DREADD in about 5% of granule cells. The activity against structure reading is an "
             "interpretation."),
)

# ------------------------------------------------------------------------------------------------ 19 CSD vs KO
page(
    num=19, slug="theta_csd_and_percent_ko", fig="Figure 20", kicker="Theta CSD and % KO", mode="below",
    question="Does the lower-blade theta current scale with % KO, and does CNO remove that link?",
    results=("At baseline the lower-blade theta current rises with % KO (MML2 + GCL2 r +0.57); after CNO it no longer does, "
             "and the more KO cells a mouse has, the more its current falls."),
    legend=("39", (0, 35, 250, 47)), legend_scale=0.8,
    panels={
        "a": dict(src="39", clip=(0, 79, 547, 255),
                  h="MML2 + GCL2 rises with % KO at baseline (r +0.57), loses the link after CNO, and falls most in high-KO mice (r −0.47)"),
        "b": dict(src="39", clip=(0, 266, 547, 443),
                  h="MML2 alone rises with % KO at baseline (r +0.56); after CNO the link weakens (r +0.40, P 0.075)"),
        "c": dict(src="39", clip=(0, 453, 547, 644),
                  h="GCL2 alone rises with % KO at baseline (r +0.47) and falls most with CNO in high-KO mice (r −0.43)"),
    },
    rows=[[dict(w=1.0, p=["a"])], [dict(w=1.0, p=["b"])], [dict(w=1.0, p=["c"])]],
    how=("Each row is one lower-blade measure (MML2 and GCL2 channels pooled, MML2, GCL2); columns: baseline, after CNO, and "
         "the change. Least-squares line through all mice with WT at 0% KO (drawn slightly spread) and its 95% band; dashed "
         "line at 15% KO; red titles, P < 0.05. Blue WT, green Lo, red Hi; diamonds IED+. n 23 at baseline, 21 after CNO. "
         "The 4-layer average, MML1 and GCL1 are in the report's Supplementary Figure S1."),
    what=("MML2 + GCL2: baseline r +0.57 (P 0.005), after CNO +0.29 (P 0.21), change −0.47 (P 0.032). MML2: +0.56 "
          "(P 0.006), +0.40 (P 0.075), −0.40 (P 0.076). GCL2: +0.47 (P 0.024), +0.15 (P 0.51), −0.43 (P 0.049). "
          "The upper blade does not track % KO (MML1 r +0.27, GCL1 +0.20)."),
    reading=("The lower blade, where the KO cells are concentrated, carries the current that grows with KO load, and CNO "
             "removes it in proportion to that load."),
    caveats=("Within the KO mice alone no layer tracks % KO (all P > 0.2), so the slope is mostly the step from WT to KO and "
             "depends on placing WT at 0%."),
)

# ------------------------------------------------------------------------------------------------ 20 ROC
page(
    num=20, slug="theta_csd_marks_the_ied_mice", fig="Figure 21", kicker="Theta CSD as an IED marker", mode="below",
    question="Can the theta current pick out the mice with clear IEDs, and does it still after CNO?",
    results=("At baseline the lower-blade theta current picks out the IED mice almost perfectly (MML2 + GCL2 AUC 0.97); "
             "after CNO it does not (0.78), because CNO cuts the current most in exactly those mice."),
    panels={
        "a": dict(src="41", clip=(0, 59, 518, 238),
                  h="MML2 + GCL2 separates the IED mice at baseline (AUC 0.97) and loses it after CNO (loss 0.20, P 0.026)"),
        "b": dict(src="41", clip=(0, 249, 518, 428),
                  h="MML2 keeps part of its separation after CNO (AUC 0.80)"),
        "c": dict(src="41", clip=(0, 439, 518, 632),
                  h="GCL2 loses its separation after CNO (AUC 0.90 falls to 0.66)"),
    },
    rows=[[dict(w=1.0, p=["a"])], [dict(w=1.0, p=["b"])], [dict(w=1.0, p=["c"])]],
    how=("The 21 mice with CSD at baseline and after CNO: 5 IED mice against 16 others (8 WT, 8 KO without IEDs); WT count as "
         "IED-negative. Left: ROC at baseline (solid) and after CNO (dashed); the loss of AUC by paired bootstrap on the same "
         "mice. Right: each mouse from baseline to CNO by group; dashed line = the best baseline cutoff; black = group "
         "means; above, the CNO drop itself as a predictor."),
    what=("Baseline AUC: MML2 + GCL2 0.97 (P < 0.001; its cutoff catches 5 of 5 IED mice with 2 of 16 false positives), "
          "MML2 0.93, GCL2 0.90, 4-layer average 0.91; MML1 0.71 and GCL1 0.60. After CNO: 0.78, 0.80, 0.66, 0.72. The CNO "
          "drop as a predictor: 0.89, 0.94, 0.81. IED mice average 0.045 against 0.024 in KO mice without IEDs "
          "(P 0.030) and 0.019 in WT."),
    reading=("The excess theta current carries the information in the IED label, and only in the lower-blade layers where KO "
             "is highest. % KO predicts the IED mice about as well (AUC 0.95) but errs on different mice (M7, M29, both Hi "
             "without IEDs and with low current), so the current depends on where the KO cells sit, not only how many."),
    caveats=("Five IED mice. Without M3 the loss of AUC for the 4-layer average falls from 0.19 to 0.11. The MML2 against "
             "GCL2 difference rests on those five mice."),
)

# ------------------------------------------------------------------------------------------------ 21 patch
page(
    num=21, slug="the_dreadd_works", fig="Figure 22", kicker="The DREADD works", mode="below",
    question="Does CNO actually silence the hM4D-expressing Pten KO granule neurons?",
    results=("Yes: at matched current CNO cut firing by three quarters (5.70 to 1.44 spikes per sweep; effect 95% CI "
             "−6.9 to −1.6), two of five neurons stopped firing altogether, and threshold and resting potential "
             "did not change."),
    legend=("43", (120, 456, 470, 472)), legend_scale=0.85,
    panels={
        "a": dict(src="43", clip=(14, 22, 259, 154),
                  h="One neuron at the same injected current: a train of spikes in aCSF, almost none in CNO"),
        "b": dict(src="43", clip=(290, 22, 518, 154), mask=[(290, 20, 303, 42)],
                  h="At every current CNO shifts firing down (−4.3 spikes per sweep)"),
        "c": dict(src="43", clip=(12, 208.5, 124, 455),
                  h="Firing falls in all five neurons (paired P 0.051)"),
        "d": dict(src="43", clip=(124, 208.5, 255, 455),
                  h="Rheobase rises; two neurons pass the highest current tested"),
        "e": dict(src="43", clip=(255, 208.5, 383, 455),
                  h="Spike threshold does not change (P 0.48)"),
        "f": dict(src="43", clip=(383, 208.5, 518, 455),
                  h="Resting potential does not change (P 0.49)"),
    },
    rows=[[dict(w=0.53, p=["a"]), dict(w=0.47, p=["b"])],
          [dict(w=0.25, p=["c"]), dict(w=0.25, p=["d"]), dict(w=0.25, p=["e"]), dict(w=0.25, p=["f"])]],
    how=("Pten flx/flx mice injected with pRubi-hM4D-T2A-Cre, so every KO granule neuron carries the receptor. Whole-cell "
         "recordings, repeated 500 ms current steps before and during 10 µM CNO, five KO neurons, every number "
         "recomputed from the raw recordings. b: spikes per sweep against current above each neuron's own baseline "
         "rheobase; thin lines neurons, thick the mean ± SE where at least three contribute; mixed model over 100 "
         "matched sweep pairs, referred to 4 df. c: matched current, paired t over neurons and a bootstrap interval "
         "resampling neurons. d, e: silenced neurons drawn open and left out of the paired tests."),
    what=("Spikes per sweep 5.70 ± 1.35 to 1.44 ± 0.77 (−75%); paired P 0.051; effect −4.23 spikes per "
          "sweep, 95% CI −6.91 to −1.61. Two neurons were silenced up to 640 and 490 pA, two fell by 97% and 60%, "
          "and N001 fell from 3.45 to 2.45 over 17 minutes. Firing falls with time after CNO in all five (−0.07 to "
          "−0.71 spikes per sweep per minute). Rheobase in the three still firing: 200 to 250, 440 to 440, 740 to 870 "
          "pA. Threshold −44.2 to −43.5 mV; resting −82.9 to −83.4 mV."),
    reading=("The KO neurons already need far more current to fire (rheobase 452 ± 95 pA, three to four times WT "
             "granule neurons), and CNO pushes them further from firing without harming the recordings. This is the "
             "cell-level version of what CNO does to the circuit (pages 20 to 22)."),
    caveats=("Five neurons set the floor: with five, no neuron-level test can go below P 0.063, so the effect and its "
             "interval are the summary to quote (a sweep-level P treats sweeps as independent and is not used). No WT "
             "no-drug time control is in this figure; earlier recordings put rundown at about a third over ten minutes."),
)

# ------------------------------------------------------------------------------------------------ 22 CNO behavior
page(
    num=22, slug="cno_and_behavior", fig="Figure 23", kicker="CNO and behavior", mode="below",
    question="Does silencing the KO cells change behavior?",
    results=("Only with the goal hidden: after CNO, hidden-goal time rises in Pten KO mice (2.2% to 3.0%; Hi 2.4% to 3.7%) "
             "and falls in WT (2.6% to 2.0%), and with the cue CNO changes nothing by genotype."),
    legend=("45", (0, 37, 200, 50)), legend_scale=0.8,
    panels={
        "a": dict(src="45", clip=(0, 81, 551, 253),
                  h="Cue present: goal-zone time does not follow % KO at baseline, after CNO or in the change"),
        "b": dict(src="45", clip=(0, 264, 551, 446),
                  h="Cue removed: after CNO goal-zone time rises with % KO (r +0.56), and so does the change"),
        "c": dict(src="45", clip=(0, 478, 551, 690),
                  h="Hidden goal time falls in WT and rises in Pten KO mice after CNO (group × drug P 0.022)"),
    },
    rows=[[dict(w=1.0, p=["a"])], [dict(w=1.0, p=["b"])], [dict(w=1.0, p=["c"])]],
    how=("Goal-zone time = mean of probe phases 8 and 9, % of the session, cued and hidden separately, at baseline and after "
         "CNO. a, b: against % KO with WT at 0%, least-squares line and 95% band; red titles, P < 0.05; n 30 at baseline "
         "(8 WT tested only at baseline), 22 after CNO (11 WT, 5 Lo, 6 Hi). c: all Pten KO mice pooled against WT: group "
         "means ± SE, each mouse from baseline to CNO (Lo green, Hi red, diamonds IED+), and each mouse's change; "
         "group × drug from a mixed model."),
    what=("Hidden: WT 2.62 to 2.03 (3 of 11 rise), all KO 2.22 to 3.03 (8 of 11), Lo 2.03 to 2.25, Hi 2.39 to 3.67 (4 of 6). "
          "Group × drug: all KO P 0.022, Hi P 0.009, Lo P 0.28; change against WT: all KO P 0.042, Hi P 0.048. Against "
          "% KO: baseline r −0.29 (P 0.12), after CNO +0.56 (P 0.006), change +0.56 (P 0.007). Cued: no group "
          "× drug effect (all P ≥ 0.62) and no relation to % KO."),
    reading=("In WT, CNO silences about 5% of normal granule cells and hidden goal time falls a little. In KO mice, Hi most, "
             "CNO pulls an overdriven dentate network back toward normal and hidden goal time rises. The benefit appears "
             "only where the task makes a hippocampal demand."),
    caveats=("M5 rises most (+4.7 points); without it all KO × drug is P 0.042, Hi × drug P 0.055 and the % KO "
             "link r +0.42 (P 0.059). Cued goal time drifts down after CNO in every group, possibly from repeated testing."),
)

# ------------------------------------------------------------------------------------------------ 23 IEDs
page(
    num=23, slug="interictal_discharges", fig="Figure 24", kicker="Interictal discharges", mode="side",
    question="Where do the IEDs start, and does CNO stop them?",
    results=("The IEDs start in the same two lower-blade layers that carry the theta excess (a GCL2 sink above an MML2 "
             "source), and CNO keeps their laminar structure and does not reduce them."),
    panels={
        "a": dict(src="47", clip=(0, 62, 263, 265),
                  h="Baseline: at initiation the hilus and GCL2 are negative, MML2 and OML2 positive"),
        "b": dict(src="47", clip=(263, 62, 551, 265),
                  h="After CNO the same layers carry the same signs"),
        "c": dict(src="47", clip=(0, 301, 261, 501),
                  h="Initiation and propagation differ by depth"),
        "d": dict(src="47", clip=(261, 301, 551, 501),
                  h="With CNO the layer pattern holds"),
        "e": dict(src="47", clip=(0, 557, 211, 773),
                  h="IED+ mice carry extra theta current at GCL2 and MML2"),
        "f": dict(src="47", clip=(211, 557, 376, 773),
                  h="The IED starts as a GCL2 sink over an MML2 source"),
        "g": dict(src="47", clip=(376, 557, 551, 773),
                  h="Both profiles peak at GCL2 and MML2"),
    },
    rows=[[dict(w=0.46, p=["a"]), dict(w=0.54, p=["b"])], [dict(w=0.46, p=["c"]), dict(w=0.54, p=["d"])],
          [dict(w=0.39, p=["e"]), dict(w=0.305, p=["f"]), dict(w=0.305, p=["g"])]],
    how=("IEDs from the lab's recording pipeline: 5 Pten KO mice (M3, M5, M13, M28, M34), one baseline and one CNO recording "
         "each, 41 and 131 IEDs. a, b: spatially normalized grand-average voltage, 49 depth bins over 8 layers around the "
         "IED peak, one color scale; bars mark initiation (IP, −1 to 0 ms) and propagation (PP, 2 to 15 ms). c, d: "
         "voltage by layer in each window, initiation filled, propagation open. e: baseline theta CSD of IED+ mice minus "
         "WT (5 against 10, ± SE). f: CSD of the averaged IED at initiation (blue sink, red source), approximate "
         "because the depth bins are unevenly spaced. g: both profiles scaled to their own maximum; shading marks GCL2 and "
         "MML2."),
    what=("Initiation, baseline: hilus −537 µV, GCL2 −822, MML2 +263, OML2 +670; in propagation MML2 and "
          "OML2 turn negative and the hilus positive, while GCL2 stays negative throughout. Depth × phase χ² "
          "191 (P < 0.001). After CNO the signs hold; per-mouse drug tests find no layer change (only GCL1 at initiation, "
          "P 0.038). IED rate 0.25 to 0.65 per minute, up in 4 of 5 mice (paired P 0.15). Theta excess about 0.04 a.u. at "
          "GCL2 and MML2, 0.02 or less elsewhere; profiles ρ +0.55 across 8 layers."),
    reading=("One circuit, two outputs: the lower blade, where KO granule cells and their perforant-path synapses are "
             "concentrated, produces both the continuous theta excess and the intermittent IED. CNO normalizes the first "
             "and not the second."),
    caveats=("Five mice; the profile match across eight layers is descriptive (P 0.16). CNO recordings ran 20 to 95 minutes, "
             "but the first 20 minutes give the same rise (0.27 to 0.74 per minute). The time from injection to recording "
             "is not in these files."),
)

# ------------------------------------------------------------------------------------------------ 24 four mice
page(
    num=24, slug="behavior_follows_theta", fig="Figure 25", kicker="Theta or IEDs?", mode="side",
    question="In the mice with both recordings and behavior, does behavior follow the theta current or the IED rate?",
    results=("It follows the theta current: in M3 and M5 IEDs rose 2.7- and 5.4-fold after CNO, yet their theta current fell "
             "by a third to a half and hidden-goal time rose; M28, whose theta fell least, was the only mouse that got worse."),
    panels={
        "a": dict(src="49", clip=(0, 53.5, 180, 221),
                  h="CNO lowers the theta current in every IED+ Hi mouse, M28 least (−13%)"),
        "b": dict(src="49", clip=(180, 53.5, 367, 221),
                  h="CNO raises the IED rate in 4 of 5 mice"),
        "c": dict(src="49", clip=(367, 53.5, 547, 221),
                  h="Hidden-goal time rises in 3 of 4 mice; only M28 falls"),
    },
    rows=[[dict(w=0.5, p=["a"]), dict(w=0.5, p=["b"])], [dict(w=0.5, p=["c"])]],
    how=("The four IED+ Hi mice with recordings and behavior (diamonds; M13, gray, has recordings only), baseline open and "
         "CNO filled. a: theta CSD, 4-layer mean. b: IED rate from the recording pipeline. c: hidden goal-zone time "
         "(phases 8 and 9). Recording and behavior sessions were on different days."),
    what=("M3: IEDs 0.33 to 0.90 per minute (×2.7), theta −53%, goal time 1.9% to 3.6%. M5: 0.06 to 0.32 "
          "(×5.4), −38%, 0.9% to 5.5%. M34: 0.28 to 0.23, −29%, 2.3% to 3.4%. M28: 0.16 to 1.34 (×8.1), "
          "−13% (GCL2 unchanged), 5.0% to 3.4%. M13: 0.42 to 0.45, +1%."),
    reading=("The behavioral benefit of CNO does not depend on fewer IEDs; it goes with the normalized theta current. M29, a "
             "Hi mouse without IEDs, also improves (+1.8 points). A continuous excess at the perforant-path synapse, present "
             "through every moment of encoding and retrieval, is the better candidate route from Pten KO to the memory "
             "deficit than intermittent IEDs."),
    caveats=("Four mice, so this is descriptive. M28 cannot separate the two explanations: its theta fell least and its IEDs "
             "rose most."),
)
