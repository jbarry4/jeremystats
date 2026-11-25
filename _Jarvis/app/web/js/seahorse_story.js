/* ==========================================================================
   seahorse_story.js -- Seahorse's stories: one recorded event, told click by
   click. The first (and for now only) one is a seizure in KCNT1 mouse 459
   (session 1, 2024-12-06), the seizure of figure A in
   Barry Playground/KCNT1 Spreadsheets/KCNT1 mouse 459/Seizure anatomical spread.

   Two kinds of stop, and every stop says which it is:
     On the probe       recorded in mouse 459: its own currents (each zone's
                        current density against its own quiet baseline), its
                        own multi-unit firing, its own hilar interneuron
     Beyond the probe   our hypothesis: what the circuits we know would do
                        next, drawn on the 3D brain
   plus a model (the healthy dentate spike) and the literature where they
   set the scene. Nothing moves on to the next stop without a click.

   The numbers come from web/seahorse/story_m459.json, built from the raw
   Neuralynx files by tools/seahorse/story_m459.py. This file holds the
   words, the stops and the drawings for the card; seahorse.js plays them.
   ========================================================================== */
'use strict';

BARRY.shStory = (function () {
  /* the papers the story leans on (the atlas's own are in kb.json and rides.json) */
  const REFS = {
    heinemann1992: 'Heinemann U, Beck H, Dreier JP, Ficker E, Stabel J, Zhang CL (1992) The dentate gyrus as a regulated gate for the propagation of epileptiform activity. Epilepsy Res Suppl 7:273-280.',
    krook2015: 'Krook-Magnuson E, Armstrong C, Bui A, Lew S, Oijala M, Soltesz I (2015) In vivo evaluation of the dentate gate theory in epilepsy. J Physiol 593:2379-2388.',
    yuan2017: 'Yuan M, Meyer T, Benkowitz C, et al. (2017) Somatostatin-positive interneurons in the dentate gyrus of mice provide local- and long-range septal synaptic inhibition. eLife 6:e21105.',
    freund1988: 'Freund TF, Antal M (1988) GABA-containing neurons in the septum control inhibitory interneurons in the hippocampus. Nature 336:170-173.',
    pare1992: 'Paré D, deCurtis M, Llinás R (1992) Role of the hippocampal-entorhinal loop in temporal lobe epilepsy: extra- and intracellular study in the isolated guinea pig brain in vitro. J Neurosci 12:1867-1881.',
    lothman1991: 'Lothman EW, Bertram EH, Stringer JL (1991) Functional anatomy of hippocampal seizures. Prog Neurobiol 37:1-82.',
    racine1972: 'Racine RJ (1972) Modification of seizure activity by electrical stimulation. II. Motor seizure. Electroencephalogr Clin Neurophysiol 32:281-294.',
    browning1985: 'Browning RA (1985) Role of the brain-stem reticular formation in tonic-clonic seizures: lesion and pharmacological studies. Fed Proc 44:2425-2431.',
    sloviter1987: 'Sloviter RS (1987) Decreased hippocampal inhibition and a selective loss of interneurons in experimental epilepsy. Science 235:73-76.',
    ziburkus2006: 'Ziburkus J, Cressman JR, Barreto E, Schiff SJ (2006) Interneuron and pyramidal cell interplay during in vitro seizure-like events. J Neurophysiol 95:3948-3954.',
    krook2013: 'Krook-Magnuson E, Armstrong C, Oijala M, Soltesz I (2013) On-demand optogenetic control of spontaneous seizures in temporal lobe epilepsy. Nat Commun 4:1376.',
  };

  /* what kind of claim a stop makes */
  const TAGS = {
    recorded: { label: 'On the probe', sub: 'recorded in mouse 459', cls: 'rec' },
    hypothesis: { label: 'Beyond the probe', sub: 'our hypothesis', cls: 'hyp' },
    model: { label: 'A model', sub: 'not a recording', cls: 'model' },
    literature: { label: 'From the literature', sub: 'and our question', cls: 'lit' },
    next: { label: 'Next', sub: 'an experiment to run', cls: 'next' },
  };

  const ACTS = [
    { key: 'open', label: 'Mouse 459' },
    { key: 'before', label: 'Tripping over its own skis' },
    { key: 'probe', label: 'From the hilus to CA1' },
    { key: 'beyond', label: 'Around the loop, then the brain' },
    { key: 'after', label: 'After' },
    { key: 'leaves', label: 'What it leaves' },
  ];

  /* the probe's zones, top (CA1) to bottom, in the words the figure uses;
     short: the words beside the shank and on the card's rows */
  const ZONE_WORDS = {
    ca1o: ['CA1 oriens and pyramidale', 'CA1 or/pyr'],
    ca1r: ['CA1 radiatum and lacunosum-moleculare', 'CA1 rad/l-m'],
    supd: ['Upper blade, outer dendrites', 'Upper ML, outer'],
    supp: ['Upper blade, inner dendrites', 'Upper ML, inner'],
    supg: ['Upper blade, granule cell layer', 'Upper GCL'],
    hil: ['Hilus', 'Hilus'],
    infg: ['Lower blade, granule cell layer', 'Lower GCL'],
    infp: ['Lower blade, inner dendrites', 'Lower ML, inner'],
    infd: ['Lower blade, outer dendrites', 'Lower ML, outer'],
  };

  /* views: 'probe' (the section through the probe), 'dentate' (closer),
     'hpf' (3D, the hippocampal formation cut at the probe), 'brain-septum',
     'brain' (3D, the whole brain). paint: what the section shows.
     clip: [from, to] s of the recording around the onset, played at speed. */
  const STOPS = [
    { key: 'intro', act: 'open', tag: 'recorded', view: 'probe', map: 'dentate', panels: ['zones'],
      title: 'Where the circuit first fails',
      say: 'One seizure in KCNT1 mouse 459, recorded on a 64-contact probe from CA1 down through the dentate gyrus. Step through what the probe saw, then what we think happened beyond it.',
      lede: 'We are not arguing where in the brain this seizure began. We are asking where, on this probe, the circuit first fails, and how the failure spreads until the whole brain is seizing.',
      more: ['Two kinds of stop. On the probe: recorded in mouse 459, its own currents and its own cells. Beyond the probe: our hypothesis, what the circuits we know would do next. Every stop waits for your click.',
        'The probe\'s contacts are grouped into the zones of the figure. In the section each zone sits where its layers are in the atlas.'] },

    { key: 'gate', act: 'before', tag: 'model', view: 'dentate', map: 'dentate', model: 'ds2', panels: [],
      focus: { conns: ['mpp', 'lpp', 'hipp_gc', 'pv_gc'] },
      title: 'A dentate spike: the gate holds',
      say: 'A volley from the entorhinal cortex lands on the granule cells\' dendrites (red: where current flows in). The hilar interneurons keep the cell layer quiet: the gate holds.',
      lede: 'The dentate gyrus sits between the entorhinal cortex and the rest of the hippocampus, and lets little through: it is a gate.',
      more: ['Somatostatin interneurons in the hilus keep the gate. HIPP cells inhibit the granule cells\' outer dendrites, where the volleys land; HIL cells also send their axons back to the medial septum. The septum times them, and the entorhinal cortex too.',
        'A dentate spike is one volley arriving: a sink in the molecular layer, a brief moment the gate contains. Shown here with Seahorse\'s model of a DS2, from the medial perforant path.'],
      refs: ['heinemann1992', 'krook2015', 'han1993', 'yuan2017', 'freund1988'] },

    { key: 'stumble', act: 'before', tag: 'recorded', view: 'probe', map: 'dentate', clip: [-12, -4], speed: 1, measure: 'absx', panels: ['raster', 'timeline'],
      title: 'Tripping over its own skis',
      say: 'In the 36 s before the seizure, the dentate fired 69 discharges, faster and faster: one every few seconds at first, five or six a second by the end. Each flash is one of them, recorded.',
      lede: 'Dentate spikes and P-spikes are the seizure\'s pattern in a lesser degree. Each is the circuit tripping over its own skis; usually it catches itself.',
      more: ['Each zone lights by how far its current density moved from its own quiet baseline (figure A\'s measure). Here: the last 12 to 4 s before onset, in real time.',
        'Discharges per 4 s, from 40 s before onset: 1, 3, 0, 1, 2, 3, 6, 9, 24, 20 (the dentate\'s summed current density above 15 robust deviations of its quiet baseline).'] },

    { key: 'pushed', act: 'before', tag: 'recorded', view: 'probe', map: 'dentate', clip: [-4, 0.3], speed: 0.5, measure: 'absx', unit: true, panels: ['unit'],
      title: 'Pushed too hard',
      say: 'In the last 3 s a hilar interneuron, on contact 41, fires at about 60 Hz: nearly five times its rate over the half-minute before. Within 3 s of the onset it falls silent.',
      lede: 'We don\'t know which interneuron this is. Its narrow spike (0.85 ms) and its place in the hilus fit the somatostatin cells we suspect: HIPP or HIL.',
      more: ['Its firing in 0.25 s bins: 6 Hz from 10 to 4 s before onset; 66, 59 and 49 Hz in the last three seconds. It dips as the hilus erupts (10 Hz from 0.5 to 1 s), fires again while the upper blade takes over (47 Hz), then stops: 0.5 Hz for the next minute and more.',
        'KCNT1\'s gain of function makes inhibitory interneurons less excitable than they should be. Here the cell is driven hard before it fails.'],
      refs: ['shore2020'] },

    { key: 'stage1', act: 'probe', tag: 'recorded', view: 'probe', map: 'dentate', clip: [-0.3, 1.2], win: [0, 1], speed: 0.2, measure: 'absx', unit: true, figure: 0, panels: ['figure', 'timeline'],
      title: '1 · The hilus lets go',
      say: '0 to 1 s. At 0.6 s a large current erupts in the hilus: the kickoff. The upper blade\'s inner layers, right beside it, move with it.',
      lede: 'This is the kickoff: the sink in the hilus. What follows it is a very large sink in the granule cell layer, as if the cell layer had lost its inhibition.',
      more: ['The figure is stage 1 of figure A: the current source density on every contact (red sink, blue source), the potentials over it, the red bar on the hilus.',
        'In the section, each zone lights by its current density against its own quiet level, played at a fifth of real time.'] },

    { key: 'stage2', act: 'probe', tag: 'recorded', view: 'probe', map: 'dentate', clip: [1.0, 2.6], win: [1.3, 2.3], speed: 0.2, measure: 'absx', unit: true, figure: 1, panels: ['figure', 'timeline'],
      title: '2 · The upper blade fires',
      say: '1.3 to 2.3 s. The upper blade\'s cell layer and inner dendrites take over, with currents up to 100 times their quiet level: the granule cells, disinhibited, fire together.',
      lede: 'The upper blade\'s firing rises with its currents: multi-unit activity in its cell layer reaches 12 times its quiet level at 2.4 s.',
      more: ['Figure A, stage 2: the green bar marks the upper blade.'] },

    { key: 'stage3', act: 'probe', tag: 'recorded', view: 'probe', map: 'dentate', clip: [2.4, 4.2], win: [2.6, 3.6], speed: 0.2, measure: 'absx', figure: 2, panels: ['figure', 'timeline'],
      title: '3 · The lower blade joins',
      say: '2.6 to 3.6 s. The lower blade\'s cell layer and dendrites light up in turn, with the strongest currents on the whole probe.',
      lede: 'The lower blade\'s cell layer reaches 140 times its quiet level, the most anywhere on the probe; its firing follows, to 20 times.',
      more: ['Figure A, stage 3: the bar marks the lower blade.'] },

    { key: 'stage4', act: 'probe', tag: 'recorded', view: 'probe', map: 'dentate', clip: [4.2, 6.0], win: [4.6, 5.6], speed: 0.2, measure: 'absx', figure: 3, panels: ['figure', 'timeline'],
      title: '4 · CA1',
      say: '4.6 to 5.6 s. CA1 joins last. CA3, between the dentate and CA1, is not on the probe; the path runs through it, so it most likely joined in between.',
      lede: 'CA1\'s contacts see the discharge arrive about 4 s after the hilus.',
      more: ['Inferred, not recorded: CA3. Mossy fibers carry the dentate\'s output to CA3, and Schaffer collaterals carry CA3\'s to CA1.',
        'Figure A, stage 4: the bar marks CA1.'] },

    { key: 'loop', act: 'beyond', tag: 'hypothesis', view: 'hpf', map: 'circuit', fx: 'loop',
      focus: { conns: ['mpp', 'lpp', 'mf_ca3', 'sc', 'ca1_sub', 'sub_ec5', 'ca1_ec5', 'ec5_ec2'], regions: ['dg', 'ca3', 'ca1', 'sub', 'ec5', 'mec2', 'lec2'] },
      title: 'Around the loop',
      say: 'CA1 hands the discharge to the subiculum and the deep entorhinal cortex, whose upper layers send it straight back to the dentate. With the gate broken, each lap comes back stronger.',
      lede: 'The hippocampus and the entorhinal cortex form a loop: entorhinal cortex, dentate gyrus, CA3, CA1, subiculum, deep entorhinal cortex, and back up to its superficial layers. Seizures can reverberate around it.',
      more: ['Normally the dentate gate stops a returning volley. In this recording the gate\'s interneuron had gone quiet, so each lap would land on a disinhibited dentate.',
        'The arcs are drawn, not recorded: the probe saw only CA1 and the dentate gyrus.'],
      refs: ['pare1992', 'lothman1991'] },

    { key: 'septum', act: 'beyond', tag: 'hypothesis', view: 'brain-septum', map: 'circuit', fx: 'septum',
      focus: { conns: ['hipp_gc', 'mpp', 'lpp'], regions: ['dg', 'mec2', 'lec2'] },
      title: 'The septum keeps time',
      say: 'The medial septum paces both the hilar interneurons and the entorhinal cortex. If it keeps saying all is well while the hilar brake is broken, cortical volleys land on a disinhibited dentate.',
      lede: 'Septal GABAergic neurons target hippocampal interneurons, and hilar HIL cells send their axons back to the septum: a timing loop between the septum and the hilus.',
      more: ['The input keeps coming whether the dentate is inhibited or not. If the chain in the hilus is broken, the septum\'s rhythm carries the seizure instead of the memory.'],
      refs: ['freund1988', 'yuan2017'] },

    { key: 'global', act: 'beyond', tag: 'hypothesis', view: 'brain', map: 'circuit', fx: 'global',
      focus: { conns: ['ec5_ctx', 'ctx_per', 'per_lec', 'ctx_por', 'por_mec'], regions: ['ctx', 'per', 'por', 'ec5'] },
      title: 'Local, focal, global',
      say: 'From the entorhinal cortex the discharge reaches the neocortex, and through the thalamus it can lock the forebrain together: a local failure becomes a focal seizure, then a global one.',
      lede: 'Seizures that start in a local circuit spread to a focal network, then become global, with feedback loops at every step.',
      more: ['The entorhinal and perirhinal cortex connect the hippocampus with the rest of the cortex; the thalamus ties the cortex to itself. None of this was recorded here.'],
      refs: ['lothman1991'] },

    { key: 'clonic', act: 'beyond', tag: 'hypothesis', view: 'brain', map: 'circuit', fx: 'clonic',
      title: 'Clonic: the motor cortex',
      say: 'When the discharge captures the motor cortex, the body jerks in time with it: forelimb clonus, rearing, falling (Racine stages 3 to 5).',
      lede: 'Forebrain seizures make clonus: rhythmic jerks of the face and forelimbs that follow the cortical discharge.',
      more: ['No video was recorded in this session (its camera file tracked nothing), so we can\'t say what mouse 459 did. This stop is the textbook, not this mouse.'],
      refs: ['racine1972'] },

    { key: 'tonic', act: 'beyond', tag: 'hypothesis', view: 'brain', map: 'circuit', fx: 'tonic',
      title: 'Tonic: the brainstem',
      say: 'Recruit the brainstem and the body stiffens: tonic extension. Forebrain circuits make the clonus; the brainstem makes the tonic phase.',
      lede: 'Brainstem seizure circuits make tonic extension, forebrain circuits make clonus, and a seizure that spreads from the forebrain into the brainstem can show both.',
      more: ['Again the textbook, not this mouse.'],
      refs: ['browning1985'] },

    { key: 'quiet', act: 'after', tag: 'recorded', view: 'probe', map: 'dentate', clip: [16, 46], speed: 2, measure: 'mua', panels: ['offs', 'timeline'],
      title: 'It stops, out of order',
      say: 'Back on the probe, firing stops layer by layer: the hilus first (23.6 s), the upper blade\'s cell layer (27.5 s), CA1 (36.1 s), the lower blade\'s cell layer last (36.8 s).',
      lede: 'When each zone fell quiet: the last time its multi-unit firing held 6 robust deviations above its quiet baseline for 0.3 s.',
      more: ['The section now shows firing, not current: each zone lights by its multi-unit activity against its quiet level, at twice real time.',
        'The lower blade\'s inner dendrites keep firing longest, to 41.1 s.'] },

    { key: 'silence', act: 'after', tag: 'recorded', view: 'probe', map: 'dentate', clip: [44, 60], speed: 1, measure: 'mua', unit: true, panels: ['unit'],
      title: 'Post-ictal silence',
      say: 'Then quiet. The hilar interneuron that fired at 60 Hz now fires at 0.5 Hz, and stays almost silent for more than a minute.',
      lede: 'Over the half-minute before the seizure it fired at 12.6 Hz; from 3 to 80 s after the onset it averages 0.48 Hz.',
      more: ['Why it stops, the recording can\'t say: exhausted, blocked by its own depolarization, or held down by its overactive KCNT1 channels, which open further as sodium builds up inside a hard-firing cell. That is a question we can test.'],
      refs: ['ziburkus2006'] },

    { key: 'damage', act: 'leaves', tag: 'literature', view: 'dentate', probe: false, map: 'dentate', fx: 'damage',
      focus: { conns: ['hipp_gc'], cells: ['hipp'] },
      title: 'Lasting damage',
      say: 'Seizures leave the network changed: hilar somatostatin interneurons are among the first cells to die, and new granule cells wire in wrong. The damage becomes the network\'s.',
      lede: 'Once a network is hyperactive, the damage is done: cells die, others sprout, and the circuit that gated the dentate is no longer there to gate it (the Danzer lab\'s view).',
      more: ['Our question for KCNT1: do these mice keep fewer somatostatin cells in the hilus? Counting them is the test.'],
      refs: ['sloviter1987', 'pun2012'] },

    { key: 'opto', act: 'leaves', tag: 'next', view: 'dentate', probe: false, map: 'dentate', fx: 'opto',
      focus: { conns: ['hipp_gc'], cells: ['hipp'] },
      title: 'Keep them happy',
      say: 'If the hilar interneurons trip over their own skis, help them keep their footing: drive them with light at a rhythm they like to burst at, and a stumble may never become a fall.',
      lede: 'On-demand light has stopped spontaneous seizures in mice with epilepsy.',
      more: ['In CA1, pacing PV interneurons with light has worked in the lab\'s hands; the circuit is so interconnected that steadying one kind of interneuron may steady the others.',
        'Not a cure: a testable framework, and a way to test drugs.'],
      refs: ['krook2013'] },
  ];

  const M459 = {
    key: 'm459', label: 'A seizure, from the hilus out', data: 'story_m459.json',
    blurb: 'KCNT1 mouse 459: where the circuit first fails, how it spreads, what follows',
    figures: ['story/m459_stage1.jpg', 'story/m459_stage2.jpg', 'story/m459_stage3.jpg', 'story/m459_stage4.jpg'],
    // a probe line through the section where the atlas's layers fall in the recorded order
    // (AP -1.80, ML +1.40 mm: every zone, top to bottom, as on the probe)
    probe: { ap: 7200, ml: 7100 },
    stops: STOPS,
  };
  const stories = () => [M459];

  /* ---------------------------------------------------------------- numbers */
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  /* one zone's series at time t (s from onset), linear between samples */
  function at(D, series, t) {
    if (!series) return 0;
    const x = (t - D.t0) * D.fs;
    const i = Math.floor(x);
    if (i < 0) return series[0];
    if (i >= series.length - 1) return series[series.length - 1];
    const f = x - i;
    return series[i] * (1 - f) + series[i + 1] * f;
  }
  /* how lit a zone is, 0..1: current density from 4 to 110 times its quiet
     level, or firing from 1.6 to 18 times, on a log scale (below that, dark:
     the dentate hums at a few times its quiet level all through the run-up) */
  const SCALE = { absx: [4, 110], mua: [1.6, 18] };
  function level(v, measure) {
    const [lo, hi] = SCALE[measure === 'mua' ? 'mua' : 'absx'];
    return v <= lo ? 0 : clamp(Math.log(v / lo) / Math.log(hi / lo), 0, 1);
  }
  function zoneLevels(D, t, measure) {
    const src = measure === 'mua' ? D.mua : D.absx;
    const out = {};
    for (const z of D.zones) out[z.key] = level(at(D, src[z.key], t), measure);
    return out;
  }
  /* the unit's rate at t (Hz, its 0.25 s bins) */
  function unitRate(D, t) {
    const u = D.unit;
    const i = Math.floor((t - u.t0) / u.bin_s);
    return i >= 0 && i < u.hz.length ? u.hz[i] : 0;
  }
  /* Ember: deep red, then orange, then white-gold as a zone heats; made for
     the dark stage, where the hottest thing should be the brightest. */
  const RAMP = [[0, [122, 22, 52]], [0.3, [205, 48, 46]], [0.62, [255, 138, 42]], [0.86, [255, 206, 104]], [1, [255, 244, 206]]];
  function ramp(x) {
    x = clamp(x, 0, 1);
    for (let i = 1; i < RAMP.length; i++) {
      if (x <= RAMP[i][0]) {
        const [a, ca] = RAMP[i - 1], [b, cb] = RAMP[i];
        const f = (x - a) / (b - a);
        return ca.map((v, k) => Math.round(v + (cb[k] - v) * f));
      }
    }
    return RAMP[RAMP.length - 1][1].slice();
  }
  const alphaOf = (lv) => (lv < 0.03 ? 0 : Math.min(0.94, 0.12 + 0.86 * Math.pow(lv, 1.15)));
  const rgba = (c, a) => 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a.toFixed(3) + ')';
  const rampCss = () => 'linear-gradient(90deg,' + RAMP.map(([x, c]) => rgba(c, alphaOf(Math.max(0.06, x))) + ' ' + Math.round(x * 100) + '%').join(',') + ')';

  /* ---------------------------------------------------------------- drawings for the card */
  /* A canvas sized for its box and the screen's pixel ratio; returns the 2D context in CSS pixels. */
  function prep(cv, h) {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.max(120, Math.round(cv.clientWidth || cv.parentNode.clientWidth || 360));
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); cv.style.height = h + 'px'; }
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return { ctx, w, h, dpr };
  }
  const niceStep = (span, n) => { const raw = span / n; const p = Math.pow(10, Math.floor(Math.log10(raw))); const m = raw / p; return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p; };
  const fmtT = (t) => (Math.abs(t) < 1e-9 ? '0' : (t < 0 ? '−' : '') + (Math.abs(t) % 1 ? Math.abs(t).toFixed(1) : String(Math.abs(t)))) + ' s';
  function axis(ctx, x0, x1, y, t0, t1, o) {
    const step = niceStep(t1 - t0, Math.max(2, Math.floor((x1 - x0) / 70)));
    ctx.fillStyle = o.ink3; ctx.font = '10.5px ' + o.font; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (let t = Math.ceil(t0 / step) * step; t <= t1 + 1e-9; t += step) {
      const x = x0 + (t - t0) / (t1 - t0) * (x1 - x0);
      ctx.fillRect(Math.round(x), y, 1, 4);
      ctx.fillText(fmtT(+t.toFixed(3)), x, y + 6);
    }
  }
  /* The zones down the probe against time, each lit by how far it is from
     its quiet self (figure A's bottom panel, as a heat strip). Cached: the
     cursor moves over a picture drawn once. */
  function drawTimeline(cv, D, o) {
    const rows = D.zones.length, rowH = 15, top = 18, lab = 98, h = top + rows * rowH + 30;
    const { ctx, w } = prep(cv, h);
    const key = [o.t0, o.t1, o.measure, w, o.ink].join('|');
    const x0 = lab, x1 = w - 8;
    if (!cv._img || cv._key !== key) {
      const off = document.createElement('canvas');
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      off.width = Math.round(w * dpr); off.height = Math.round(h * dpr);
      const c = off.getContext('2d');
      c.setTransform(dpr, 0, 0, dpr, 0, 0);
      const src = o.measure === 'mua' ? D.mua : D.absx;
      const cols = Math.max(2, Math.round(x1 - x0));
      D.zones.forEach((z, r) => {
        const y = top + r * rowH;
        c.fillStyle = o.ink1; c.fillRect(x0, y + 1, x1 - x0, rowH - 2);
        for (let i = 0; i < cols; i++) {
          const t = o.t0 + (i + 0.5) / cols * (o.t1 - o.t0);
          const lv = level(at(D, src[z.key], t), o.measure);
          const a = alphaOf(lv);
          if (!a) continue;
          c.fillStyle = rgba(ramp(lv), a);
          c.fillRect(x0 + i, y + 1, 1.2, rowH - 2);
        }
        c.fillStyle = o.ink2; c.font = '10.5px ' + o.font; c.textAlign = 'right'; c.textBaseline = 'middle';
        c.fillText(ZONE_WORDS[z.key][1], x0 - 8, y + rowH / 2);
      });
      // the stage's window, as figure A marks it
      if (o.win) {
        const a = x0 + (o.win[0] - o.t0) / (o.t1 - o.t0) * (x1 - x0), b = x0 + (o.win[1] - o.t0) / (o.t1 - o.t0) * (x1 - x0);
        c.strokeStyle = o.ink2; c.lineWidth = 1.2;
        c.beginPath(); c.moveTo(a, top - 4); c.lineTo(a, top - 9); c.lineTo(b, top - 9); c.lineTo(b, top - 4); c.stroke();
        c.fillStyle = o.ink2; c.textAlign = 'center'; c.textBaseline = 'bottom'; c.font = '600 10px ' + o.font;
        c.fillText('stage ' + o.stage, (a + b) / 2, top - 10);
      }
      if (o.t0 < 0 && o.t1 > 0) { const x = x0 + (0 - o.t0) / (o.t1 - o.t0) * (x1 - x0); c.fillStyle = o.ink3; c.fillRect(Math.round(x), top, 1, rows * rowH); }
      axis(c, x0, x1, top + rows * rowH + 2, o.t0, o.t1, o);
      cv._img = off; cv._key = key;
    }
    ctx.drawImage(cv._img, 0, 0, w, h);
    if (o.cursor != null && o.cursor >= o.t0 && o.cursor <= o.t1) {
      const x = x0 + (o.cursor - o.t0) / (o.t1 - o.t0) * (x1 - x0);
      ctx.fillStyle = o.accent; ctx.fillRect(Math.round(x) - 1, top - 2, 2, rows * rowH + 4);
    }
  }
  /* The hilar interneuron's firing, -10 to +90 s, with its earlier rate as a dashed line. */
  function drawUnit(cv, D, o) {
    const h = 132, top = 10, bot = 26, left = 34;
    const { ctx, w } = prep(cv, h);
    const u = D.unit, x0 = left, x1 = w - 8, y0 = h - bot, y1 = top, yMax = 70;
    const t0 = u.t0, t1 = u.t0 + u.hz.length * u.bin_s;
    const X = (t) => x0 + (t - t0) / (t1 - t0) * (x1 - x0), Y = (v) => y0 - Math.min(v, yMax) / yMax * (y0 - y1);
    ctx.fillStyle = o.ink1; ctx.fillRect(x0, y1, x1 - x0, y0 - y1);
    if (o.win) { ctx.fillStyle = o.soft; ctx.fillRect(X(o.win[0]), y1, Math.max(2, X(o.win[1]) - X(o.win[0])), y0 - y1); }
    ctx.fillStyle = o.cellColor;
    const bw = Math.max(1, (x1 - x0) / u.hz.length);
    u.hz.forEach((v, i) => { if (v > 0) { const x = X(t0 + i * u.bin_s); ctx.fillRect(x, Y(v), Math.max(1, bw - 0.4), y0 - Y(v)); } });
    ctx.setLineDash([4, 3]); ctx.strokeStyle = o.ink2; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x0, Y(u.baseline_hz) + 0.5); ctx.lineTo(x1, Y(u.baseline_hz) + 0.5); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = o.ink3; ctx.fillRect(Math.round(X(0)), y1, 1, y0 - y1);
    ctx.font = '10.5px ' + o.font; ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; ctx.fillStyle = o.ink3;
    [0, 30, 60].forEach((v) => ctx.fillText(String(v), x0 - 6, Y(v)));
    ctx.save(); ctx.translate(10, (y0 + y1) / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = 'center'; ctx.fillText('Hz', 0, 0); ctx.restore();
    ctx.textAlign = 'left'; ctx.textBaseline = 'bottom'; ctx.fillStyle = o.ink2;
    ctx.fillText(u.baseline_hz + ' Hz, the half-minute before', X(40), Y(u.baseline_hz) - 3);
    axis(ctx, x0, x1, y0 + 2, t0, t1, o);
    if (o.cursor != null) { ctx.fillStyle = o.accent; ctx.fillRect(Math.round(X(o.cursor)) - 1, y1 - 2, 2, y0 - y1 + 4); }
  }
  /* The discharges before the onset, one tick each, faster and faster. */
  function drawRaster(cv, D, o) {
    const h = 64, left = 8, t0 = -40, t1 = 2;
    const { ctx, w } = prep(cv, h);
    const x0 = left, x1 = w - 8, y0 = 8, y1 = 36;
    const X = (t) => x0 + (t - t0) / (t1 - t0) * (x1 - x0);
    ctx.fillStyle = o.ink1; ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
    if (o.win) { ctx.fillStyle = o.soft; ctx.fillRect(X(o.win[0]), y0, X(o.win[1]) - X(o.win[0]), y1 - y0); }
    for (const t of D.discharges) {
      if (t < t0 || t > t1) continue;
      const seen = o.cursor == null || t <= o.cursor;
      ctx.fillStyle = t < 0 ? (seen ? o.hot : o.ink3) : o.ink3;
      ctx.fillRect(Math.round(X(t)), y0 + 3, 1.6, y1 - y0 - 6);
    }
    ctx.fillStyle = o.ink2; ctx.fillRect(Math.round(X(0)), y0 - 3, 1.4, y1 - y0 + 6);
    axis(ctx, x0, x1, y1 + 3, t0, t1, o);
    if (o.cursor != null && o.cursor >= t0 && o.cursor <= t1) { ctx.fillStyle = o.accent; ctx.fillRect(Math.round(X(o.cursor)) - 1, y0 - 2, 2, y1 - y0 + 4); }
  }
  /* When each zone fell quiet: a bar from the onset to its last strong firing. */
  function drawOffs(cv, D, o) {
    const rows = D.zones.length, rowH = 15, top = 6, lab = 98, h = top + rows * rowH + 28;
    const { ctx, w } = prep(cv, h);
    const x0 = lab, x1 = w - 40, t0 = 0, t1 = 45;
    const X = (t) => x0 + (t - t0) / (t1 - t0) * (x1 - x0);
    D.zones.forEach((z, r) => {
      const y = top + r * rowH;
      ctx.fillStyle = o.ink2; ctx.font = '10.5px ' + o.font; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      ctx.fillText(ZONE_WORDS[z.key][1], x0 - 8, y + rowH / 2);
      ctx.fillStyle = o.ink1; ctx.fillRect(x0, y + 3, x1 - x0, rowH - 6);
      if (z.off_s != null) {
        const lit = o.cursor == null || o.cursor < z.off_s;
        ctx.fillStyle = lit ? rgba(ramp(0.7), 0.9) : o.ink3;
        ctx.fillRect(x0, y + 3, X(z.off_s) - x0, rowH - 6);
        ctx.fillStyle = o.ink2; ctx.textAlign = 'left';
        ctx.fillText(z.off_s.toFixed(1) + ' s', X(z.off_s) + 5, y + rowH / 2);
      }
    });
    axis(ctx, x0, x1, top + rows * rowH + 2, t0, t1, o);
    if (o.cursor != null && o.cursor >= t0 && o.cursor <= t1) { ctx.fillStyle = o.accent; ctx.fillRect(Math.round(X(o.cursor)) - 1, top - 2, 2, rows * rowH + 4); }
  }

  return { REFS, TAGS, ACTS, ZONE_WORDS, SCALE, stories, at, level, zoneLevels, unitRate, ramp, alphaOf, rgba, rampCss,
           drawTimeline, drawUnit, drawRaster, drawOffs };
})();
