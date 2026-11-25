const fs = require('fs');
const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, LevelFormat, Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType } = require('docx');

const FONT = 'Arial';
// text with inline **bold** and _italic_ markup
function runs(s) {
  const out = []; const re = /(\*\*[^*]+\*\*)/g; let last = 0, m;
  while ((m = re.exec(s)) !== null) {
    if (m.index > last) out.push(new TextRun({ text: s.slice(last, m.index), font: FONT, size: 21 }));
    const t = m[0];
    if (t.startsWith('**')) out.push(new TextRun({ text: t.slice(2, -2), bold: true, font: FONT, size: 21 }));
    else out.push(new TextRun({ text: t.slice(1, -1), italics: true, font: FONT, size: 21 }));
    last = m.index + t.length;
  }
  if (last < s.length) out.push(new TextRun({ text: s.slice(last), font: FONT, size: 21 }));
  return out;
}
const P = (s) => new Paragraph({ children: runs(s), spacing: { after: 120, line: 276 } });
const B = (s, lvl = 0) => new Paragraph({ children: runs(s), numbering: { reference: 'bullets', level: lvl }, spacing: { after: 60, line: 264 } });
const H1 = (s) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: s })] });
const H2 = (s) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: s })] });
const NOTE = (s) => new Paragraph({ children: [new TextRun({ text: s, italics: true, font: FONT, size: 19, color: '52514E' })], spacing: { after: 120 } });

const border = { style: BorderStyle.SINGLE, size: 4, color: 'BFBFBF' };
function table(rows, widths) {
  const total = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths,
    rows: rows.map((r, i) => new TableRow({
      tableHeader: i === 0,
      children: r.map((c, j) => new TableCell({
        width: { size: widths[j], type: WidthType.DXA },
        borders: { top: border, bottom: border, left: border, right: border },
        shading: i === 0 ? { fill: 'E9E8E3', type: ShadingType.CLEAR, color: 'auto' } : undefined,
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        children: [new Paragraph({ children: [new TextRun({ text: c, bold: i === 0, font: FONT, size: 19 })] })]
      }))
    }))
  });
}

const today = new Date().toISOString().slice(0, 10);
const C = [];
C.push(new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun({ text: 'Analysis methods: Pten KO mosaicism and spatial accuracy' })] }));
C.push(NOTE(`Prepared ${today} from the analysis code (ClaudeAnalsysisCode) and the report. Covers data processing and statistics for every analysis in the report. Animal procedures, viral labelling, histology (percent KO counts), electrophysiological recording, CNO dosing and the training protocol are described elsewhere; places where a detail from those methods is needed are marked [in brackets].`));

// ---------------------------------------------------------------- 1
C.push(H1('1. Mice, groups and labels'));
C.push(P('Mice were Pten knockout (KO) mosaic mice and wild-type (WT) controls. Pten KO mice were divided by the percentage of dentate granule cells in the granule cell layer that were Pten KO (% KO; KO cells outside the layer were not counted): **Pten KO Lo**, below 15% KO (observed 3.9–9.5%), and **Pten KO Hi**, 15% or more (observed 18.9–28.4%). The 15% boundary follows LaSarge et al. (2021). WT mice were assigned 0% KO where % KO is used as a continuous variable. Pten;Raptor double KO mice were not included in any analysis.'));
C.push(table([
  ['Group', 'Behaviour (probe) analyses', 'Theta CSD analyses'],
  ['WT', '19 mice (18 for sessions to criterion)', '10 at baseline, 8 after CNO (M26 excluded)'],
  ['Pten KO Lo', '5 (M1, M8, M10, M30, M33)', '6 (adds M11)'],
  ['Pten KO Hi', '6 (M3, M5, M7, M28, M29, M34)', '7 (adds M13)'],
  ['KO, no histology', '2 (M27, M31); pooled KO numbers only', 'not recorded'],
], [2200, 3700, 3460]));
C.push(new Paragraph({ text: '', spacing: { after: 60 } }));
C.push(B('**IED status.** Mice were labelled IED+ (clear interictal epileptiform discharges: M3, M5, M13, M28, M34) or IED− (no obvious IEDs) from the depth recordings [IED detection method]. The labels are qualitative; IED− means no obvious IEDs, not normal activity. WT mice were treated as IED-negative.'));
C.push(B('**Heterotopia.** Granule cell heterotopia was noted in M8, M10, M27, M29 and M30 [histological criterion].'));
C.push(B('**Exclusions.** M6 (WT) was excluded from sessions to criterion only, as an extreme outlier (27 sessions against 7–13 for every other WT mouse); it was kept in all probe analyses. M26 (WT) was excluded from the theta CSD analyses because of a problem after implantation surgery [details]; it was kept in the behavioural analyses, which were run before implantation.'));
C.push(B('**Percent KO sources.** Behavioural analyses used the project % KO list. The CSD and CNO analyses used the values in Data4Claude.xlsx, with M29 = 22.00% and M30 = 5.97% from the project list. The two sources differ only for M33 (8.82% vs 4.41%), which is Lo either way.'));

// ---------------------------------------------------------------- 2
C.push(H1('2. Spatial accuracy task and probe sessions'));
C.push(P('Mice were tested in an active place preference (spatial accuracy) task adapted from the place preference task of Bureš and colleagues as developed by J. Kubie: a reward is delivered only when the mouse enters a small, unmarked goal zone and stays in it. Position was tracked at 30 frames/s with Bio-Signal Tracker (version 2.36) [camera, arena, reward delivery]. Tracker parameters were the same in all 256 probe sessions analysed: arena 0.82 m in diameter as entered in the tracker; goal zone 15% of the arena diameter (20% in 2 sessions); entrance latency 1200 ms (the time the mouse must remain in the zone before a reward), reward pulse 500 ms, inter-reward interval 5000 ms and outside refractory period 3000 ms. Sessions lasted 30 min (one session 26 min).'));
C.push(P('**Training and criterion.** Mice were trained to criterion [criterion definition]; sessions to criterion is the number of training sessions needed.'));
C.push(P('**Probe sessions.** After training, mice received probe sessions at four goal locations: phase 7 at the trained location and phases 8, 9 and 10 at successive novel locations. Each phase had a visible-goal session (cued) and a hidden-goal session. The four goal locations are fixed positions in the arena (zones 1–4), so at each phase one zone is the current goal, earlier ones are previous goals and the rest have not yet been used. Session dates and times were read from the header of each tracking file (listed in the data workbook).'));

// ---------------------------------------------------------------- 3
C.push(H1('3. Probe-session measures'));
C.push(P('Eight measures per session were taken from the PlaceAccuracy output (AllProbeSessions.sav):'));
[['NumRewards', 'rewards earned.'], ['PGoalTime', 'fraction of the session spent in the goal zone.'], ['NumEntrances', 'entrances into the goal zone.'],
 ['ReRatio', 'rewards per entrance.'], ['PTimeCenter', 'fraction of time in the centre of the arena.'], ['PTimeAnnulus', 'fraction of time in the outer annulus (the wall zone, 35 pixels wide).'],
 ['MeanSpeed', 'mean running speed over the session (cm/s).'], ['MeanTargSpeed (target speed)', 'running speed in the goal zone: the speed as the mouse enters and moves through the zone (about the first 0.4–0.5 s after entry), not speed on the way to it.']]
  .forEach(([k, v]) => C.push(B(`**${k}:** ${v}`)));
C.push(P('Values are mean ± SE across mice unless stated.'));

// ---------------------------------------------------------------- 4
C.push(H1('4. Sessions to criterion'));
C.push(B('**Group comparisons.** Lo vs WT, Hi vs WT, Lo vs Hi and all Pten KO vs WT: two-sided Mann-Whitney U tests, with Welch t-tests and exact permutation tests of the difference in means (all relabellings when there are 100,000 or fewer, otherwise random relabellings) shown alongside. Effect size: Hedges g. A quasi-Poisson GLM (Pearson chi-square scale) was fitted as a count-model check.'));
C.push(B('**ROC.** Sessions to criterion as a classifier of each subtype against all other mice, WT included (Lo, Hi, any Pten KO, IED+, IED−, heterotopia). AUC is the Mann-Whitney probability that a mouse of the subtype needs more sessions (ties count one half); 95% CI from 5000 bootstrap resamples within each class; p from the Mann-Whitney test; the cutoff maximises sensitivity + specificity.'));
C.push(B('**Percent KO.** Pearson and Spearman correlations among Pten KO mice, within each cluster, and linear and quadratic least-squares fits across all mice with WT at 0% KO; the slope was checked by leaving out one mouse at a time.'));

// ---------------------------------------------------------------- 5
C.push(H1('5. Probe sessions: group comparisons'));
C.push(P('For each measure, condition (visible, hidden) and phase, Lo vs WT, Hi vs WT and Lo vs Hi were compared with two-sided Mann-Whitney U tests on the session values. p-values are uncorrected unless stated; where a corrected value (q) is given it is the Benjamini-Hochberg false discovery rate across the 64 measure × condition × phase tests of that comparison. Pooled Pten KO (including M27 and M31) and IED+ vs IED− comparisons used the same test.'));

// ---------------------------------------------------------------- 6
C.push(H1('6. Phase effects'));
C.push(B('**Trained vs novel.** Within each group, phase 7 against the mean of phases 8–10: paired t-test, exact sign-flip permutation test and Friedman test across the four phases. The change (novel − trained) was compared between groups with Mann-Whitney U tests.'));
C.push(B('**Slopes.** For each mouse, the least-squares slope of the measure across phases 7–10 (and 8–10, novel only); slopes were tested against zero (one-sample t-test) and compared between groups (Mann-Whitney U).'));
C.push(B('**Group × phase.** Linear mixed models with a random intercept per mouse (statsmodels mixedlm, maximum likelihood): group and group × phase effects tested by likelihood-ratio tests against the reduced models.'));

// ---------------------------------------------------------------- 7
C.push(H1('7. Percent KO and probe outcome'));
C.push(P('Among Pten KO mice with histology, each probe measure at each phase and condition was correlated with % KO (Spearman ρ, with Pearson r alongside). q is the Benjamini-Hochberg false discovery rate across the 64 tests. Phase 10 hidden values were also plotted against % KO with a least-squares line and its 95% confidence band fitted to the Pten KO mice only (WT shown at 0% for reference).'));

// ---------------------------------------------------------------- 8
C.push(H1('8. Time in each goal zone'));
C.push(P('Time in each of the four candidate goal zones per probe session came from AllProbes_ByGZLocation.sav. At each phase, zones were classed by role: current goal, previous goal(s) (the most recent previous goal and the mean of all previous goals), the trained (phase 7) goal, and zones not yet used as a goal. Shares were computed as the time in a zone divided by the total time in the four zones.'));
C.push(B('Within each group and phase: Friedman test across the four zones; paired t-test of the current goal against each other zone.'));
C.push(B('Between groups: Mann-Whitney U on current-goal time; current vs original (trained) goal within group (paired t-test and Wilcoxon signed-rank where shown).'));
C.push(B('Zone entries: entries, time per entry and rewards per entry for the current and previous goals.'));

// ---------------------------------------------------------------- 9
C.push(H1('9. Path analyses from the raw tracking files'));
C.push(P('All path analyses re-implement the lab\'s MATLAB code (TargetTrajectories.m, JB2 June 2025) in Python; every departure from the MATLAB code is marked in the code (## DEVIATION FROM MATLAB) and summarised in the package README.'));
C.push(H2('9.1 Reading and validating the tracking files'));
C.push(P('Each Bio-Signal Tracker .dat file was parsed for its header (%Name.0 ( values ) lines) and the frame, time stamp, x, y and state columns. State codes: 0 outside the goal, 1 entrance latency (in the zone, reward pending), 2 reward, 3 inter-reward latency. A reward is a 1 → 2 transition and an entrance a 0 → 1 transition. Goal centre and radius were taken from the header (ReinforcedSector), as in the MATLAB code. Rewards, entrances and goal time reproduced the PlaceAccuracy output exactly for all 256 probe sessions (32 mice, phases 7–10, visible and hidden).'));
C.push(H2('9.2 Position, speed and the arena wall'));
C.push(B('Positions were converted to cm with the scale used in the MATLAB code (75 cm across the 255-pixel field, 0.294 cm per pixel). Lost frames (x = 0) were set to missing.'));
C.push(B('**Speed for the PlaceAccuracy-matched measures:** displacement over 15 frames (0.5 s) divided by elapsed time, shifted 12 frames earlier, which reproduces MeanSpeed within 0.4 cm/s and MeanTargSpeed within 1.2 cm/s (the MATLAB Speed_MtxEZ function was not available).'));
C.push(B('**Speed for the approach analyses:** gaps up to 15 frames interpolated, a 5-frame centred running mean, and velocity from the gradient of the smoothed position.'));
C.push(B('**Arena wall.** Because the camera view shifted slightly between recording days, the arena edge was fitted per session: for each of 90 angular bins the 99th percentile of radius was taken as an edge point and a circle fitted by least squares (three iterations). "At the wall" is radius > 0.8 of the fitted radius (the outer 20%).'));
C.push(H2('9.3 Approach to the goal (Figures 20–22)'));
C.push(P('Every entry into the current goal zone was analysed (17,588 entries). The same zone is used in the visible and hidden session of a phase, so visible vs hidden is compared at the same location.'));
C.push(B('**Launch distance:** working back from the entry, the last run during which the mouse moved at more than 5 cm/s with its heading within 45° of the goal, allowing up to 0.5 s (15 frames) off course and searching up to 20 s back; launch distance is the distance from the goal (cm) at which that run began. A **directed run** is one with launch distance of at least 20 cm.'));
C.push(B('**Wall-to-goal run:** the path from the last frame at the wall to the entry, kept when the mouse did not pass through the zone on the way and the run lasted 3 frames to 20 s; straightness = straight-line distance ÷ path length; duration in s.'));
C.push(B('**Path per reward:** total distance run in the session ÷ rewards.'));
C.push(B('**Per mouse:** launch distance and run duration are medians over all entries of phases 7–10; straightness is the mean over runs; path per reward is the median over the four sessions.'));
C.push(B('**Tests:** visible vs hidden within group, paired t-test; between groups, Mann-Whitney U.'));
C.push(H2('9.4 Heading toward the goal by distance (Figure 32)'));
C.push(P('This analysis uses every running frame rather than one launch distance per entry, to show where along the way a mouse starts to orient to the goal. Position, smoothing, speed and the arena fit are as in 9.2–9.3, and the goal location is the same in the visible and hidden session of each phase.'));
C.push(B('**Frames:** running (> 5 cm/s), outside the goal zone (tracker state 0), and not in the 2 s after leaving the goal zone, so movement away from the goal after a visit is not counted. Frames at the wall (radius > 0.8 of the fitted arena radius) are analysed separately, because along the wall the heading is set by the wall; the main results use frames off the wall, and all frames are reported as a check.'));
C.push(B('**Heading error:** the angle between the velocity vector and the vector from the mouse to the goal centre (0° = straight at the goal). **Goal-directedness** = mean cosine of the heading error: 1 = straight at the goal, 0 = heading unrelated to the goal.'));
C.push(B('**Profile:** per mouse and condition, frames from phases 7–10 were pooled into 2.5 cm bins of distance from the goal centre (bins with fewer than 30 frames dropped), and goal-directedness was computed per bin.'));
C.push(B('**Reach:** the distance at which goal-directedness first falls below 0.1, moving outward from the goal (linear interpolation between bins). Because the 0.1 line is arbitrary, the frame-weighted mean goal-directedness from 10 to 40 cm, which needs no threshold, is reported alongside. Reach was also computed for each phase separately.'));
C.push(B('**Launch-distance distribution:** from the per-entry launch distances of 9.3, the % of each mouse\'s goal entries launched from at least each distance (0–55 cm), averaged across mice; tested at 20, 30 and 40 cm.'));
C.push(B('**Tests:** visible vs hidden within group by paired t-test (for WT also per distance bin and per phase); groups compared with Mann-Whitney U.'));
C.push(H2('9.5 Arrival at the goal (Figure 23)'));
C.push(P('Zone visits were defined geometrically for all four zones: a visit starts when the mouse enters the zone circle and ends when it is more than 1.3 zone radii from the centre (hysteresis, so jitter at the edge does not create new visits). For each visit to the current goal: launch distance (as above), entry speed (mean speed over the first 0.5 s inside), dwell (time until the mouse is again beyond 1.3 radii) and whether a reward was earned. Per mouse, phase and condition: % of entries reached by a directed run, median entry speed, median dwell and % of directed runs rewarded. Groups were compared at each phase with Mann-Whitney U tests.'));
C.push(H2('9.5b Slowing at the goal and total pausing (Figure 37)'));
C.push(P('Two things that Figure 23 pools were separated here. First, the speed profile around each entry was recomputed for entries reached by a directed run (launch \u2265 20 cm) and for the rest, to check whether the Hi deficit is specific to runs the mouse aimed; it is not, and the two are reported separately in the workbook.'));
C.push(B('**Slowing ratio:** for each session, the mean speed over the 1.2 s after entering the goal divided by the mean speed over the 1.5 s to 0.5 s before it, on directed runs only; 1 means the mouse did not slow. Speed is the centred 15-frame (0.5 s) displacement speed used for the arrival profiles, so that time zero lines up with the entry. Because the ratio is formed within each run it controls for approach speed, which does not differ between Hi and WT at any phase or condition (p = 0.14 to 0.40).'));
C.push(B('**Pausing:** pauses are those of 9.7. For each probe session the total pause time, the number of pauses and the mean pause duration were taken over the whole session and the whole arena, not only the goal zone. Distances from a pause to each of the four zones are in zone radii, so a pause inside the zone is under 1. The proportion measures (the share of near-goal pauses falling inside the zone, the share of pause time spent there, the median distance of a near-goal pause) are reported alongside the absolute ones because they answer a different question: the proportions describe where the pauses land, the absolute amounts describe how much the mouse pauses at all. Only the absolute amounts differ between groups.'));
C.push(B('**Where the pause happened:** pause time was also split by the distance from the pause to the current goal, in zone radii: inside the zone (under 1), the ring around it (1 to 2.5) and the open interior (beyond 2.5). The wall is not a fourth compartment because the pause definition already excludes it \u2014 a pause is 1.2 to 10 s below 3 cm/s and pauses beyond 0.8 of the fitted arena radius are dropped, so none of these measures contain thigmotaxis or resting against the wall.'));
C.push(B('**Phase effects:** per mouse, the slope of each measure across hidden phases 7\u201310 was fitted by least squares and the slopes compared between groups with a two-sided Mann-Whitney, which is the group \u00d7 phase test reported in Figure 37. The same test on the cued sessions is the control.'));
C.push(B('**Example runs (Figure 37a, b):** every directed run into the hidden goal at phase 10, plotted in goal-centred coordinates and rotated so that the launch point lies to the left of the goal, with the path coloured by speed. The marker on each run is the mouse\u2019s position 1.2 s after entry, the moment the reward is due. For panel b the run shown is the one whose slowing ratio is closest to that mouse\u2019s median, so it is typical rather than selected; points are drawn every 0.1 s.'));

C.push(H2('9.5c What the mice search: pause time by kind of place (Figure 38)'));
C.push(P('Zone k was the goal of phase k + 6, so at each hidden phase the four zones divide into the current goal, the goals of earlier phases, and the zones not yet used; the number of former goals is 0, 1, 2 and 3 at phases 7, 8, 9 and 10. Each pause was assigned to the nearest kind of zone within 2.5 zone radii, testing the current goal first, then the former goals, then the never-used zones; pauses near none of them were counted separately. Pause time was then summed per probe session within each kind of place, per-mouse slopes across phases 7 to 10 fitted by least squares, and the slopes compared between groups with a two-sided Mann-Whitney, as in 9.5b. Both conditions are analysed: the hidden sessions, where the set of candidate places has to be held in mind, and the cued sessions, where a beacon marks the current goal. As everywhere in this package, pauses at the wall are excluded by the pause definition.'));
C.push(B('**Location specification, stated explicitly because the measures differ:** the arrival profile of 9.5 is triggered on entries into the current goal and describes only its neighbourhood. The pause-placement measures of 9.5b are conditional proportions and describe where pauses land given that the mouse paused near the goal, not how much it paused. Total pause time is not location-specified at all beyond the exclusion of the wall. The compartment split is specified by distance from the current goal without regard to zone identity. This section is specified by zone identity. A proportion read as an amount, or distance-from-goal read as place identity, gives different and incompatible answers from the same pauses.'));

C.push(H2('9.5d Braking: deceleration on approach (Section 5)'));
C.push(P('Whishaw, Cassel and Jarrard (1995, J Neurosci 15:5779) treat deceleration on approach as the sign that an animal expects to find the goal at a place; their fimbria-fornix rats decelerated at the same distance from the vanished platform as controls. Two measures apply that logic here, both from the centred 15-frame displacement speed used for the arrival profiles.'));
C.push(B('**Braking rate by place.** Along the whole path, off the wall (radius \u2264 0.8 of the fitted arena radius), a braking event is a fall from a local speed maximum of at least 12 cm/s to below half that speed within 1 s. The event is placed where the mouse ended up slow, and assigned to the nearest kind of zone within 2.5 zone radii \u2014 current goal, former goal, or not yet used \u2014 and otherwise counted as elsewhere. Rates are expressed per metre of off-wall path travelled, because Hi mice cover about 29 per cent more ground in a hidden session and a raw count would reward that.'));
C.push(B('**Braking distance.** On each directed run to the current goal (launch \u2265 20 cm), the distance from the goal at which speed first falls below 70 per cent of that run\u2019s approach maximum, taken after the maximum. Runs with no such fall before the mouse reaches the goal are recorded as not braking rather than dropped, so the proportion of runs with any braking is reported beside the distance and the censoring is explicit.'));
C.push(B('**Thresholds.** The 12 cm/s peak, the halving criterion, the 1 s window and the 70 per cent run criterion are choices, not standards. They were set once, before the group comparisons were run, and not adjusted afterwards; the sensitivity of the result to them has not been tested and is noted as a caveat in the report.'));

C.push(H2('9.5e Example mice in the standalone summary'));
C.push(P('The standalone summary (\u201cTwo phenotypes, three mice\u201d) follows one animal per group. Each is the mouse closest to its group median across five measures \u2014 sessions to criterion, pause time at former goals at hidden phase 10, total pause time at hidden phase 10, hidden-minus-cued speed, and braking rate at the current goal \u2014 scored as the summed absolute deviation from the group median in units of that measure\u2019s median absolute deviation. The rule was fixed before the figures were drawn. It selects M9 (WT), M8 (Pten KO Lo) and M5 (Pten KO Hi).'));
C.push(B('**Arena orientation.** The tracker stores y running down the image, so plotting it into a y-up axis mirrors the arena. Arena figures are drawn in the room view (y negated), in which the phase 7 goal falls in the upper right quadrant (39 to 46 degrees in every mouse) and the goals of phases 8, 9 and 10 follow anti-clockwise, the lab convention. No rotation is applied: the zone layout is the same in every mouse. The example-path and dwell-map figures already used an inverted y axis and were unaffected; the goal-centred approach figures were mirrored in handedness and are corrected here.'));
C.push(B('**Speed through the reward window, all entries.** For each mouse, phase and condition the speed profile is averaged over every entry into the current goal, directed runs and chance crossings alike, weighted by the number of entries, from 3 s before entry to 3 s after. The reported statistic is the mean speed over the 1.2 s window that earns a reward, compared between groups by two-sided Mann-Whitney over per-mouse values.'));
C.push(B('**Distance-locked approach profiles.** For the summary\u2019s arrival figure, speed on each directed run is expressed as a percentage of that run\u2019s own approach maximum and interpolated onto a common grid of distance from the goal (6 to 60 cm in 2 cm steps; runs end at the zone edge). A mouse\u2019s value in a bin is the mean over its runs, computed only where at least three runs contribute; group means are across mice.'));

C.push(H2('9.6 Reward per directed run across rotations (Figure 24)'));
C.push(B('**Per mouse:** least-squares slope of % directed runs rewarded across hidden phases 7–10; tested against zero (one-sample t-test) and between groups (Mann-Whitney U).'));
C.push(B('**Per run:** logistic generalised estimating equations (statsmodels GEE, binomial family, exchangeable working correlation, clustered by mouse) with reward (yes/no) as outcome and group × phase as predictors; the group × phase odds ratio is the change in the odds of a reward per rotation relative to the reference group.'));
C.push(H2('9.7 After a miss: returns and pauses (Figure 25)'));
C.push(B('**Returns:** for each exit from a zone (first frame beyond 1.3 radii), the time until the mouse is inside the same zone again (searched up to 10 s). A miss is an unrewarded exit from the current goal. The outcome is the % of misses followed by a return within 3 s, with returns to the other zones as a control.'));
C.push(B('**Pauses:** speed ≤ 3 cm/s for at least 35 frames (about 1.2 s; the minimum window of the MATLAB pause filter) and no longer than 300 frames (10 s), excluding pauses at the wall. A pause is "near" a zone when within 2.5 zone radii of its centre.'));
C.push(B('Measures are per mouse over hidden phases 8–10 (and phase 10 alone for pause counts and the median exit speed); groups were compared with Mann-Whitney U tests.'));
C.push(H2('9.8 First goal rotation: place vs cue and new place vs old place (Figures 30–31)'));
C.push(P('Phase 8 is the first rotation of the goal. In the visible probe the cue sits on the new goal (zone 2) while the old goal (zone 1, the phase 7 location) is a remembered place, so old vs new is a place vs cue conflict. In the hidden probe, run about 32 min later (M7: one day later), there is no cue, so old vs new is a conflict between the new and the old place. Zones 3 and 4 had never been a goal or been rewarded; runs to them give each mouse\'s no-memory baseline.'));
C.push(B('**Visits and runs:** every visit to each of the four zones was kept with its entry time (same visit rule and launch distance as in 9.3 and 9.5). Only directed runs (launch ≥ 20 cm) were counted, taken in the order the mouse made them. Visit counts, launch distances and rewards match the zone-visit table of 9.5 exactly.'));
C.push(B('**Old-place share (visible):** of the first 10 directed runs to either the old place or the cue (new goal), the % to the old place. Baseline: the same share for each never-used zone against the cue (first 10 never-used vs cue runs), averaged over zones 3 and 4; compared with the old-place share by paired t-test.'));
C.push(B('**Place pull (latent place preference):** of the first N directed runs to any zone, the % to a place minus the % to one never-used zone (the never-used % halved, as there are two such zones). N = 10 for the visible probe; N = 20 for the hidden probe, where mice make fewer directed runs (WT median 54 vs 94 per session). Hidden: pull of the new place, of the old place, and of both (mean of new and old minus never-used). Tested against 0 by one-sample t-test.'));
C.push(B('**Cue present vs gone:** old-place pull over the first 10 directed runs in the visible and the hidden probe, compared within mouse by paired t-test; the change (hidden − visible) compared between groups by Mann-Whitney U.'));
C.push(B('**Links:** Spearman correlation of each phase 8 measure with rewards at hidden phase 10 (all mice, WT only, KO only) and a rank regression with group in the model (rank(y) ~ rank(x) + group, ordinary least squares); within KO, Spearman correlation with % KO.'));
C.push(B('**Between groups:** two-sided Mann-Whitney U (Lo vs WT, Hi vs WT, pooled KO vs WT, Lo vs Hi). Robustness: repeated without M52, M54 and M59, whose phase 8 sessions are dated before phase 7.'));
C.push(H2('9.9 Example mice (Figures 16–19)'));
C.push(P('One mouse per group (M22 WT, M33 Lo, M34 Hi) was chosen to show each group\'s pattern. Paths were drawn per session with rewards marked; dwell and speed maps used 32 × 32 bins of 8 pixels, as in the MATLAB code, smoothed with a Gaussian filter (σ = 1 bin), with rarely visited bins left blank in the speed maps.'));

// ---------------------------------------------------------------- 10
C.push(H1('10. Theta current source density (CSD)'));
C.push(P('Theta-band CSD was computed per recording channel from laminar silicon-probe recordings in the dentate gyrus at baseline and after CNO [recording, theta filtering (4–12 Hz), CSD calculation and channel spacing as in the methods of the companion manuscript]. Each channel was assigned to a layer (CA1 SP, CA1 SLM, DG OML1, MML1, GCL1, hilus, GCL2, MML2, OML2; 1 = suprapyramidal blade, 2 = infrapyramidal blade). The analyses used the channel-level file CSD_sansM2.sav.'));
C.push(B('**Per-layer CSD:** the mean of all channels with that layer label in the session.'));
C.push(B('**Combined measures:** the 4-layer average pools all channels in MML1, MML2, GCL1 and GCL2; MML2 + GCL2 pools the channels of those two layers.'));
C.push(B('**Sessions:** one baseline and one CNO session per mouse; for M59, which had two baseline sessions, session s4 was used. M47 and M51 (WT) had no CNO session. One M33 CNO channel row with a blank mouse ID was assigned from its session ID.'));
C.push(B('**DREADD control:** WT mice also expressed the inhibitory DREADD, in about 5% of granule cells, so CNO in WT mice silences a small set of normal granule cells.'));

// ---------------------------------------------------------------- 11
C.push(H1('11. Goal-zone time before and after CNO'));
C.push(P('Goal-zone time (PGoalTime) was taken from probe sessions run at baseline and after CNO (AllProbeSessions_CNO.sav) and averaged over phases 8 and 9, separately for visible and hidden sessions, as a percentage of the session [CNO dose, route and timing]. Baseline values match the probe sessions above exactly. M2 had two visible CNO sessions at phase 9; both were averaged. Baseline regressions include the 8 WT mice tested only at baseline.'));

// ---------------------------------------------------------------- 12
C.push(H1('12. Statistics for CSD and CNO (Figures 9, 10, 26; Supplementary Figure S1)'));
C.push(B('**Between groups:** two-sided Mann-Whitney U (Lo vs WT, Hi vs WT, Lo vs Hi, all Pten KO vs WT, IED vs KO without IEDs, IED vs WT).'));
C.push(B('**Baseline vs CNO within group:** paired t-test.'));
C.push(B('**Group × drug:** linear mixed model y ~ group × drug with a random intercept per mouse (statsmodels mixedlm, REML); the p-value reported is that of the group × drug term, with WT (or Lo) as reference.'));
C.push(B('**Regression on % KO:** least squares with WT at 0% KO (Pearson r, slope, 95% confidence band of the fitted line), for baseline, after CNO and the change; also within Pten KO mice only (Spearman ρ alongside).'));
C.push(B('**Layers:** every analysis was run for the 4-layer average, MML2 + GCL2, MML2, GCL2, MML1 and GCL1; MML1 and GCL1 are shown in Supplementary Figures S1 and S2.'));
C.push(B('**Sensitivity:** the Hi × drug interaction for CSD recomputed leaving out each Hi mouse; the behavioural results recomputed without M5.'));

// ---------------------------------------------------------------- 13
C.push(H1('13. ROC: theta CSD as a predictor of clear IEDs (Figure 27, Supplementary Figure S2)'));
C.push(P('IED status (IED+ vs all other mice, WT counted as IED-negative) was predicted from each CSD measure in the 21 mice with CSD at baseline and after CNO (5 IED vs 16 others), and in Pten KO mice only (5 vs 8).'));
C.push(B('**AUC:** the probability that an IED mouse has the higher value, ties counted one half (equivalent to the Mann-Whitney U statistic divided by the product of the group sizes); p from the Mann-Whitney test.'));
C.push(B('**95% CI:** 5000 bootstrap resamples within each class (percentile interval).'));
C.push(B('**Best cutoff:** the value maximising sensitivity + specificity − 1 (Youden index), classifying values at or above the cutoff as IED.'));
C.push(B('**Loss of AUC with CNO:** AUC at baseline minus AUC after CNO on the same mice, with a 95% CI and two-sided p from a paired bootstrap (5000 resamples of mice within class). Robustness: recomputed leaving out each mouse.'));
C.push(B('**CNO drop as a predictor:** baseline − CNO used as the predictor in the same way.'));
C.push(B('**Percent KO** was used as a predictor on the same mice for comparison.'));
C.push(B('**Comparing measures:** the difference in AUC (and in correlation with % KO) between MML2 + GCL2 and the 4-layer average, with a paired bootstrap over mice (5000 resamples).'));

// ---------------------------------------------------------------- 14
C.push(H1('14. Layer profile of theta CSD (Figures 28–29)'));
C.push(P('Per-layer CSD per mouse was compared across groups in two groupings: WT / Pten KO Lo / Pten KO Hi, and WT / KO without IEDs / KO with IEDs.'));
C.push(B('**GEE against the WT hilus:** generalised estimating equations (statsmodels GEE, Gaussian family, exchangeable working correlation, clustered by mouse) with one coefficient per group × layer cell and the WT hilus as the reference cell, fitted separately for baseline, after CNO and the change (CNO − baseline). Each cell\'s p-value tests its difference from the WT hilus; Holm correction was applied across the cells of each panel.'));
C.push(B('**GCL2 and MML2:** each KO group against WT in the same layer (Mann-Whitney U) at baseline and after CNO, and baseline vs CNO within group (paired t-test). The share of the baseline excess removed by CNO = 1 − (group − WT after CNO) / (group − WT at baseline), from group means.'));

// ---------------------------------------------------------------- 15
C.push(H1('15. IEDs: laminar structure, rate with CNO, and the link to theta and behaviour (Figures 33–35, Supplementary Figures S3–S4)'));
C.push(P('IEDs were detected and reviewed by the lab\'s recording pipeline (automated detection with expert review of each event; only events rated solid were kept) in 5 Pten KO mice (M3, M5, M13, M28, M34), each with one baseline and one CNO recording (41 and 131 solid IEDs). The analyses here use the pipeline\'s outputs: the spatially normalised grand-average voltage per condition, the per-session counts, recording lengths and onset times, and the pipeline\'s per-depth statistics, which are reported as given.'));
C.push(B('**Grand-average voltage:** 49 depth bins (CA1 SLM 5, OML1 4, MML1 5, GCL1 5, hilus 13, GCL2 7, MML2 5, OML2 5, superficial to deep) by 1201 samples (−20 to +20 ms at 30 kHz around the IED peak); mean of the 5 sessions in each condition. Each bin was baseline-corrected to its mean from −20 to −10 ms. Layer values are the mean over the layer\'s bins and the window: initiation (IP) −1 to 0 ms, propagation (PP) 2 to 15 ms.'));
C.push(B('**CSD (supplementary):** minus the second difference across depth bins of the voltage after 3-point [1 2 1]/4 smoothing (a.u.). The bins are not evenly spaced in tissue, so this approximates the pipeline\'s channel CSD; it is used for illustration (Supplementary Figure S3) and for the initiation profile of Figure 34B.'));
C.push(B('**Pipeline statistics (as given):** initiation vs propagation per depth by a linear mixed model on the paired per-IED difference with a random intercept for mouse; CNO vs baseline per depth at the mouse level (paired t, n = 5); Benjamini-Hochberg correction across the 8 depths within each panel.'));
C.push(B('**Theta excess vs IED profile:** baseline theta CSD of IED+ mice minus WT for each layer (section 14), with SE = √(SE₁² + SE₂²), compared with the IED initiation CSD by Spearman correlation across the 8 layers (descriptive).'));
C.push(B('**IED rate:** solid IEDs per minute of recording; also over the first 20 minutes of every session, so that recordings of different length (20–95 min) compare. Baseline vs CNO by paired t-test and Wilcoxon signed-rank across the 5 mice. Intervals between successive IEDs within each recording, pooled across mice.'));
C.push(B('**Link to theta and behaviour:** for the four mice with recordings and behaviour, the change with CNO in theta CSD (4-layer mean, MML2 + GCL2, GCL2; section 10) and in hidden goal-zone time (section 11) is set beside the change in IED rate. With n = 4 this is descriptive; the recording and behaviour sessions were on different days.'));

// ---------------------------------------------------------------- 16
C.push(H1('16. Whole-cell validation of CNO silencing (Figure 21)'));
C.push(P('The patch-clamp recordings were made in the lab; this version of the figure shows the five Pten KO neurons only, and every value in it is computed here from the raw AxoGraph recordings. Pten^flx/flx^ mice carrying the Ai14 tdTomato reporter were injected in the dentate gyrus with the retrovirus pRubi-HM4D-T2A-Cre, which expresses the inhibitory DREADD hM4D(Gi) and Cre from one open reading frame separated by a T2A peptide, so that every Cre-expressing neuron also expresses the receptor; tdTomato-positive neurons are Pten KO neurons expressing hM4D.'));
C.push(B('**Protocol.** Current-clamp series of 20 depolarising steps of 500 ms beginning 21 ms into the sweep, incremented by 10 pA per sweep from a first step chosen per neuron to bracket rheobase, repeated at about 5 min intervals; sampled at 80 kHz with a 10 kHz Bessel filter. After one or two baseline series, 10 \u00b5M CNO was added to the bath and the identical series repeated. The comparison series is the one nearest 10 min after CNO, which at this spacing is the second post-CNO series. The first step amplitude and the 10 pA increment are read from each file\u2019s own stored pulse table, so the injected current of every sweep is known.'));
C.push(B('**Spike detection.** Peaks above \u221210 mV preceded within 2 ms by dV/dt greater than 100 mV/ms; threshold is the first sample of the spike\u2019s own contiguous rising phase at which dV/dt reaches 20 mV/ms; a spike is accepted when its peak exceeds threshold by at least 20 mV. Per series: spikes per sweep, rheobase (the lowest current evoking a spike), spike threshold (the mean threshold of the first spike of every sweep that fired) and resting potential (the mean over the 5\u201318 ms preceding the step). Spikes per sweep are compared at matched injected current: the currents shared by the baseline and comparison series.'));
C.push(B('**Identifying the neurons.** The raw files carry only a date and a cell number. Each neuron in the published figure was identified by computing all four measures for every series of every cell and matching the four-vector against the published per-cell values; the five Pten KO neurons match on all four measures, and the results text independently names the non-responder (N001) as the cell this matching assigns to it. The assignment is in inputs/patch/patch_cell_identities.csv.'));
C.push(B('**Statistics.** Baseline and CNO are compared over the five neurons by two-tailed paired t test, as in the original (panels c–f). The effect on firing is also given as a 95% confidence interval from 4000 bootstrap resamples of the five neurons, which is the summary the text relies on. Because the paired test uses five summary values in place of the 100 matched pairs of sweeps behind them, the firing-rate comparison is additionally fitted as a linear mixed model of spikes per sweep on condition and injected current with a random intercept and slope per neuron (maximum likelihood), reported in panel b. Its Wald p treats sweeps as the replication unit, so it is referred to the 4 degrees of freedom that five neurons provide; the uncorrected Wald p (0.002) lies below the floor of the exact within-neuron sign-flip permutation test (2/32 = 0.063 with five neurons, 0.125 here), which is the signature of sweep-level pseudo-replication, and is not reported. Neurons silenced at every current tested have no rheobase or threshold and are excluded from those two paired tests, as in the original, but contribute to spikes per sweep and resting potential.'));
C.push(B('**Correction to the earlier metadata.** The per-cell table used in earlier versions was recovered from the vector coordinates of the lab\u2019s summary figure. Within each measure its values are correct and reproduce the published means and SEMs, but the rows are not aligned across measures: each panel\u2019s points were matched to cell labels independently, so a row could pair one neuron\u2019s spike count with another\u2019s threshold. Group statistics computed within a measure are unaffected. The table built from the raw recordings supersedes it.'));
C.push(B('**Not included here.** The uninfected wild-type no-drug time control and the Pten;Raptor dKO group are not shown in this version. Their raw recordings for the control group were not available, so rundown over the comparison interval is not controlled within this figure.'));

C.push(H1('17. Software, figures and reproducibility'));
C.push(P('All analyses were run in Python 3 with numpy, pandas, scipy, statsmodels, pyreadstat and matplotlib. The code package (ClaudeAnalsysisCode) contains every script with its inputs, a README giving the order to run them and the figure each produces, and notes wherever the Python code departs from the lab\'s MATLAB code. The package reproduces every number and figure in the report from a clean copy. Figures were exported as vector PDF and SVG (Inter font embedded or converted to outlines) and as 600-dpi PNG. Per-mouse data and the statistical tables for every analysis are in the accompanying workbook (Pten_KO_data_by_analysis.xlsx).'));
C.push(P('**Reference.** LaSarge CL, et al. (2021). Progress in Neurobiology 200:101974.'));

const doc = new Document({
  creator: 'Claude', title: 'Analysis methods: Pten KO mosaicism and spatial accuracy',
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: 'Title', name: 'Title', basedOn: 'Normal', run: { font: FONT, size: 34, bold: true }, paragraph: { spacing: { before: 0, after: 160 }, keepNext: true } },
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: FONT, size: 26, bold: true, color: '1F3864' }, paragraph: { spacing: { before: 280, after: 120 }, keepNext: true, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: FONT, size: 22, bold: true, color: '1F3864' }, paragraph: { spacing: { before: 200, after: 80 }, keepNext: true, outlineLevel: 1 } },
    ]
  },
  numbering: { config: [{ reference: 'bullets', levels: [
    { level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } },
    { level: 1, format: LevelFormat.BULLET, text: '–', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 1000, hanging: 270 } } } }] }] },
  sections: [{ properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1260, bottom: 1260, left: 1440, right: 1440 } } }, children: C }]
});
Packer.toBuffer(doc).then(b => { fs.writeFileSync(process.argv[2], b); console.log('written', process.argv[2]); });
