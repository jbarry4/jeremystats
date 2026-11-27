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

   The numbers come from web/seahorse/story_m459.json, and the card's
   picture of the probe (figure A's CSD with the potentials over it, the
   same at every stop) from web/seahorse/story_m459_probe.shb.gz, both built
   from the raw Neuralynx files by tools/seahorse/story_m459.py. This file
   holds the words, the stops and the drawings for the card; seahorse.js
   plays them.
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
     clip: [from, to] s of the recording around the onset, played at speed.
     pic: what the card's picture of the probe shows at this stop. Every
     stop has one, so the card looks the same from stop to stop:
       win     the window, s from the onset (a stop with a clip shows its clip)
       zones   the zones it is about: a bar beside them, their names lit
       marks   [from, to, label] brackets over the picture (figure A's stages)
       offs    a tick where each zone fell quiet (the zones' off_s)
       note    one line under it: what to look at */
  const DG_ZONES = ['supd', 'supp', 'supg', 'hil', 'infg', 'infp', 'infd'];
  const STAGE_MARKS = [[0, 1, '1'], [1.3, 2.3, '2'], [2.6, 3.6, '3'], [4.6, 5.6, '4']];
  const STOPS = [
    { key: 'intro', act: 'open', tag: 'recorded', view: 'probe', map: 'dentate',
      pic: { win: [-1, 7], marks: STAGE_MARKS, note: 'The seizure\'s first seconds as the probe saw them, figure A\'s four stages numbered. Blue is a sink (current flowing into the cells), red a source.' },
      title: 'Where the circuit first fails',
      say: 'One seizure in KCNT1 mouse 459, recorded on a 64-contact probe from CA1 down through the dentate gyrus. Step through what the probe saw, then what we think happened beyond it.',
      lede: 'We are not arguing where in the brain this seizure began. We are asking where, on this probe, the circuit first fails, and how the failure spreads until the whole brain is seizing.',
      more: ['Two kinds of stop. On the probe: recorded in mouse 459, its own currents and its own cells. Beyond the probe: our hypothesis, what the circuits we know would do next. Every stop waits for your click.',
        'The probe\'s contacts are grouped into the zones of the figure. In the section each zone sits where its layers are in the atlas.'] },

    { key: 'gate', act: 'before', tag: 'model', view: 'dentate', map: 'dentate', model: 'ds2',
      pic: { win: [-12, -4], zones: DG_ZONES, note: 'The model is on the stage. Here, for comparison, is the recording it stands for: the run-up, where each stripe across the dentate is one discharge (ticked above).' },
      focus: { conns: ['mpp', 'lpp', 'hipp_gc', 'pv_gc'] },
      title: 'A dentate spike: the gate holds',
      say: 'A volley from the entorhinal cortex lands on the granule cells\' dendrites (blue: where current flows in). The hilar interneurons keep the cell layer quiet: the gate holds.',
      lede: 'The dentate gyrus sits between the entorhinal cortex and the rest of the hippocampus, and lets little through: it is a gate.',
      more: ['Somatostatin interneurons in the hilus keep the gate. HIPP cells inhibit the granule cells\' outer dendrites, where the volleys land; HIL cells also send their axons back to the medial septum. The septum times them, and the entorhinal cortex too.',
        'A dentate spike is one volley arriving: a sink in the molecular layer, a brief moment the gate contains. Shown here with Seahorse\'s model of a DS2, from the medial perforant path.'],
      refs: ['heinemann1992', 'krook2015', 'han1993', 'yuan2017', 'freund1988'] },

    { key: 'stumble', act: 'before', tag: 'recorded', view: 'probe', map: 'dentate', clip: [-12, -4], speed: 1, measure: 'absx',
      pic: { zones: DG_ZONES, note: 'Each stripe across the dentate is one discharge (ticked above): 33 in these 8 s, closer and closer together.' },
      title: 'Tripping over its own skis',
      say: 'In the 36 s before the seizure, the dentate fired 69 discharges, faster and faster: one every few seconds at first, five or six a second by the end. Each flash is one of them, recorded.',
      lede: 'Dentate spikes and P-spikes are the seizure\'s pattern in a lesser degree. Each is the circuit tripping over its own skis; usually it catches itself.',
      more: ['In the section, each zone lights by how far its current density moved from its own quiet baseline (figure A\'s measure). Here: the last 12 to 4 s before onset, in real time.',
        'Discharges per 4 s, from 40 s before onset: 1, 3, 0, 1, 2, 3, 6, 9, 24, 20 (the dentate\'s summed current density above 15 robust deviations of its quiet baseline).'] },

    { key: 'pushed', act: 'before', tag: 'recorded', view: 'probe', map: 'dentate', clip: [-4, 0.3], speed: 0.5, measure: 'absx', unit: true,
      pic: { zones: ['hil'], note: 'The interneuron\'s spikes are the ticks under the picture: closer and closer together until the onset.' },
      title: 'Pushed too hard',
      say: 'In the last 3 s a hilar interneuron, on contact 41, fires at about 60 Hz: nearly five times its rate over the half-minute before. Within 3 s of the onset it falls silent.',
      lede: 'We don\'t know which interneuron this is. Its narrow spike (0.85 ms) and its place in the hilus fit the somatostatin cells we suspect: HIPP or HIL.',
      more: ['Its firing in 0.25 s bins: 6 Hz from 10 to 4 s before onset; 66, 58 and 49 Hz in the last three seconds. It dips as the hilus erupts (10 Hz from 0.5 to 1 s), fires again while the upper blade takes over (50 Hz from 1 to 2 s), then stops: 0.4 Hz for the next minute and more.',
        'KCNT1\'s gain of function makes inhibitory interneurons less excitable than they should be. Here the cell is driven hard before it fails.'],
      refs: ['shore2020'] },

    { key: 'stage1', act: 'probe', tag: 'recorded', view: 'probe', map: 'dentate', clip: [-0.3, 1.2], win: [0, 1], speed: 0.2, measure: 'absx', unit: true,
      pic: { zones: ['hil', 'supp'], marks: [STAGE_MARKS[0]], note: 'The hilus (barred) erupts at 0.6 s, the upper blade\'s inner dendrites beside it.' },
      title: '1 · The hilus lets go',
      say: '0 to 1 s. At 0.6 s a large current erupts in the hilus: the kickoff. The upper blade\'s inner layers, right beside it, move with it.',
      lede: 'This is the kickoff: the sink in the hilus. What follows it is a very large sink in the granule cell layer, as if the cell layer had lost its inhibition.',
      more: ['The picture is figure A\'s, drawn over the whole stop: the current source density on every contact (blue sink, red source) with the potentials over it. Its stage 1 is the bracketed second.',
        'In the section, each zone lights by its current density against its own quiet level, played at a fifth of real time.'] },

    { key: 'stage2', act: 'probe', tag: 'recorded', view: 'probe', map: 'dentate', clip: [1.0, 2.6], win: [1.3, 2.3], speed: 0.2, measure: 'absx', unit: true,
      pic: { zones: ['supg', 'supp'], marks: [STAGE_MARKS[1]], note: 'The upper blade\'s cell layer and inner dendrites (barred) take over.' },
      title: '2 · The upper blade fires',
      say: '1.3 to 2.3 s. The upper blade\'s cell layer and inner dendrites take over, with currents up to 100 times their quiet level: the granule cells, disinhibited, fire together.',
      lede: 'The upper blade\'s firing rises with its currents: multi-unit activity in its cell layer reaches 12 times its quiet level at 2.4 s.',
      more: ['Figure A\'s stage 2 is the bracketed second.'] },

    { key: 'stage3', act: 'probe', tag: 'recorded', view: 'probe', map: 'dentate', clip: [2.4, 4.2], win: [2.6, 3.6], speed: 0.2, measure: 'absx',
      pic: { zones: ['infg', 'infp', 'infd'], marks: [STAGE_MARKS[2]], note: 'The lower blade (barred) lights up, with the strongest currents on the probe.' },
      title: '3 · The lower blade joins',
      say: '2.6 to 3.6 s. The lower blade\'s cell layer and dendrites light up in turn, with the strongest currents on the whole probe.',
      lede: 'The lower blade\'s cell layer reaches 140 times its quiet level, the most anywhere on the probe; its firing follows, to 20 times.',
      more: ['Figure A\'s stage 3 is the bracketed second.'] },

    { key: 'stage4', act: 'probe', tag: 'recorded', view: 'probe', map: 'dentate', clip: [4.2, 6.0], win: [4.6, 5.6], speed: 0.2, measure: 'absx',
      pic: { zones: ['ca1o', 'ca1r'], marks: [STAGE_MARKS[3]], note: 'CA1 (barred), at the top of the probe, joins last.' },
      title: '4 · CA1',
      say: '4.6 to 5.6 s. CA1 joins last. CA3, between the dentate and CA1, is not on the probe; the path runs through it, so it most likely joined in between.',
      lede: 'CA1\'s contacts see the discharge arrive about 4 s after the hilus.',
      more: ['Inferred, not recorded: CA3. Mossy fibers carry the dentate\'s output to CA3, and Schaffer collaterals carry CA3\'s to CA1.',
        'Figure A\'s stage 4 is the bracketed second.'] },

    { key: 'loop', act: 'beyond', tag: 'hypothesis', view: 'hpf', map: 'circuit', fx: 'loop',
      pic: { win: [4, 16], note: 'Meanwhile on the probe (4 to 16 s): every zone discharging, again and again. Beyond the probe, nothing was recorded.' },
      focus: { conns: ['mpp', 'lpp', 'mf_ca3', 'sc', 'ca1_sub', 'sub_ec5', 'ca1_ec5', 'ec5_ec2'], regions: ['dg', 'ca3', 'ca1', 'sub', 'ec5', 'mec2', 'lec2'] },
      title: 'Around the loop',
      say: 'CA1 hands the discharge to the subiculum and the deep entorhinal cortex, whose upper layers send it straight back to the dentate. With the gate broken, each lap comes back stronger.',
      lede: 'The hippocampus and the entorhinal cortex form a loop: entorhinal cortex, dentate gyrus, CA3, CA1, subiculum, deep entorhinal cortex, and back up to its superficial layers. Seizures can reverberate around it.',
      more: ['Normally the dentate gate stops a returning volley. In this recording the gate\'s interneuron had gone quiet, so each lap would land on a disinhibited dentate.',
        'The arcs are drawn, not recorded: the probe saw only CA1 and the dentate gyrus.'],
      refs: ['pare1992', 'lothman1991'] },

    { key: 'septum', act: 'beyond', tag: 'hypothesis', view: 'brain-septum', map: 'circuit', fx: 'septum',
      pic: { win: [4, 16], note: 'Meanwhile on the probe (4 to 16 s): every zone discharging, again and again. Beyond the probe, nothing was recorded.' },
      focus: { conns: ['hipp_gc', 'mpp', 'lpp'], regions: ['dg', 'mec2', 'lec2'] },
      title: 'The septum keeps time',
      say: 'The medial septum paces both the hilar interneurons and the entorhinal cortex. If it keeps saying all is well while the hilar brake is broken, cortical volleys land on a disinhibited dentate.',
      lede: 'Septal GABAergic neurons target hippocampal interneurons, and hilar HIL cells send their axons back to the septum: a timing loop between the septum and the hilus.',
      more: ['The input keeps coming whether the dentate is inhibited or not. If the chain in the hilus is broken, the septum\'s rhythm carries the seizure instead of the memory.'],
      refs: ['freund1988', 'yuan2017'] },

    { key: 'global', act: 'beyond', tag: 'hypothesis', view: 'brain', map: 'circuit', fx: 'global',
      pic: { win: [4, 16], note: 'Meanwhile on the probe (4 to 16 s): every zone discharging, again and again. Beyond the probe, nothing was recorded.' },
      focus: { conns: ['ec5_ctx', 'ctx_per', 'per_lec', 'ctx_por', 'por_mec'], regions: ['ctx', 'per', 'por', 'ec5'] },
      title: 'Local, focal, global',
      say: 'From the entorhinal cortex the discharge reaches the neocortex, and through the thalamus it can lock the forebrain together: a local failure becomes a focal seizure, then a global one.',
      lede: 'Seizures that start in a local circuit spread to a focal network, then become global, with feedback loops at every step.',
      more: ['The entorhinal and perirhinal cortex connect the hippocampus with the rest of the cortex; the thalamus ties the cortex to itself. None of this was recorded here.'],
      refs: ['lothman1991'] },

    { key: 'clonic', act: 'beyond', tag: 'hypothesis', view: 'brain', map: 'circuit', fx: 'clonic',
      pic: { win: [4, 16], note: 'Meanwhile on the probe (4 to 16 s): every zone discharging, again and again. Beyond the probe, nothing was recorded.' },
      title: 'Clonic: the motor cortex',
      say: 'When the discharge captures the motor cortex, the body jerks in time with it: forelimb clonus, rearing, falling (Racine stages 3 to 5).',
      lede: 'Forebrain seizures make clonus: rhythmic jerks of the face and forelimbs that follow the cortical discharge.',
      more: ['No video was recorded in this session (its camera file tracked nothing), so we can\'t say what mouse 459 did. This stop is the textbook, not this mouse.'],
      refs: ['racine1972'] },

    { key: 'tonic', act: 'beyond', tag: 'hypothesis', view: 'brain', map: 'circuit', fx: 'tonic',
      pic: { win: [4, 16], note: 'Meanwhile on the probe (4 to 16 s): every zone discharging, again and again. Beyond the probe, nothing was recorded.' },
      title: 'Tonic: the brainstem',
      say: 'Recruit the brainstem and the body stiffens: tonic extension. Forebrain circuits make the clonus; the brainstem makes the tonic phase.',
      lede: 'Brainstem seizure circuits make tonic extension, forebrain circuits make clonus, and a seizure that spreads from the forebrain into the brainstem can show both.',
      more: ['Again the textbook, not this mouse.'],
      refs: ['browning1985'] },

    { key: 'quiet', act: 'after', tag: 'recorded', view: 'probe', map: 'dentate', clip: [16, 46], speed: 2, measure: 'mua',
      pic: { offs: true, note: 'Each zone\'s tick is where its firing stopped: the hilus first, the lower blade\'s cell layer last.' },
      title: 'It stops, out of order',
      say: 'Back on the probe, firing stops layer by layer: the hilus first (23.6 s), the upper blade\'s cell layer (27.5 s), CA1 (36.1 s), the lower blade\'s cell layer last (36.8 s).',
      lede: 'When each zone fell quiet: the last time its multi-unit firing held 6 robust deviations above its quiet baseline for 0.3 s.',
      more: ['The section now shows firing, not current: each zone lights by its multi-unit activity against its quiet level, at twice real time.',
        'The lower blade\'s inner dendrites keep firing longest, to 41.0 s.'] },

    { key: 'silence', act: 'after', tag: 'recorded', view: 'probe', map: 'dentate', clip: [44, 60], speed: 1, measure: 'mua', unit: true,
      pic: { zones: ['hil'], note: 'After the seizure: the interneuron\'s ticks, under the picture, are all but gone.' },
      title: 'Post-ictal silence',
      say: 'Then quiet. The hilar interneuron that fired at 60 Hz now fires at 0.4 Hz, and stays almost silent for more than a minute.',
      lede: 'Over the half-minute before the seizure it fired at 12.4 Hz; from 3 to 80 s after the onset it averages 0.42 Hz.',
      more: ['Why it stops, the recording can\'t say: exhausted, blocked by its own depolarization, or held down by its overactive KCNT1 channels, which open further as sodium builds up inside a hard-firing cell. That is a question we can test.'],
      refs: ['ziburkus2006'] },

    { key: 'damage', act: 'leaves', tag: 'literature', view: 'dentate', probe: false, map: 'dentate', fx: 'damage',
      pic: { win: [44, 60], note: 'The probe\'s last view, 44 to 60 s: after the seizure, the hilus and its interneuron quiet.' },
      focus: { conns: ['hipp_gc'], cells: ['hipp'] },
      title: 'Lasting damage',
      say: 'Seizures leave the network changed: hilar somatostatin interneurons are among the first cells to die, and new granule cells wire in wrong. The damage becomes the network\'s.',
      lede: 'Once a network is hyperactive, the damage is done: cells die, others sprout, and the circuit that gated the dentate is no longer there to gate it (the Danzer lab\'s view).',
      more: ['Our question for KCNT1: do these mice keep fewer somatostatin cells in the hilus? Counting them is the test.'],
      refs: ['sloviter1987', 'pun2012'] },

    { key: 'opto', act: 'leaves', tag: 'next', view: 'dentate', probe: false, map: 'dentate', fx: 'opto',
      pic: { win: [44, 60], note: 'The probe\'s last view, 44 to 60 s: after the seizure, the hilus and its interneuron quiet.' },
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
    // the probe's picture (figure A's CSD and traces, -12 to +60 s), drawn in the card at every stop
    blob: 'story_m459_probe.shb.gz',
    blurb: 'KCNT1 mouse 459: where the circuit first fails, how it spreads, what follows',
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
  /* ---------------------------------------------------------------- the probe, drawn
     The card's picture, the same at every stop: figure A's current source
     density on CSC 2-59 (blue sink, red source, at figure A's colour limit),
     the 1-300 Hz potentials of every fourth contact drawn over it, the hilar
     interneuron's spikes under it, and the whole recording in a strip below
     with this stop's window boxed. It is drawn once per stop; while a clip
     plays, only a cursor and a veil over what is still to come move
     (seahorse.js), which costs the page next to nothing.

     B is story_m459_probe.shb.gz unpacked: header {t0, csd: {fs, csc, vmax},
     lfp: {fs, csc, gap_uv}, unit: {csc, masked}}, arrays {csd: Int16 rows x n,
     lfp: Int16 traces x n, spikes: Float32 s from the onset}. */

  /* what a stop shows: its window, live while its clip plays, and what it highlights */
  function picOf(st) {
    const p = st.pic || {};
    return { win: p.win || st.clip || [-1, 7], live: !!st.clip, zones: p.zones || [], marks: p.marks || [], offs: !!p.offs, note: p.note || '' };
  }

  // matplotlib's RdBu turned round, the KCNT1 poster's map (v8; figure A had it the other way):
  // the deepest sink dark blue, the strongest source dark red, as in Jarvis
  const RDBU = ['#053061', '#2166ac', '#4393c3', '#92c5de', '#d1e5f0', '#f7f7f7', '#fddbc7', '#f4a582', '#d6604d', '#b2182b', '#67001f'];
  // the same two hues on a dark ground (a dark theme): quiet is the ground, and a current
  // grows brighter and more saturated with its size, still blue or still red at its strongest
  const RDBU_NIGHT = ['#7cc8ff', '#43a0f0', '#2479cc', '#164f8c', '#0d2645', null, '#4a0f1d', '#93192b', '#cf2f33', '#f2503a', '#ff7a45'];
  const hexRgb3 = (h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
  /* 513 colours from -1 (a sink at figure A's limit) to +1 (a source at it) */
  function csdLut(dark, zero) {
    const stops = (dark ? RDBU_NIGHT : RDBU).map((c) => (c ? hexRgb3(c) : zero));
    const lut = new Uint8ClampedArray(513 * 3);
    for (let i = 0; i <= 512; i++) {
      const x = i / 512 * (stops.length - 1), k = Math.min(stops.length - 2, Math.floor(x)), f = x - k;
      for (let c = 0; c < 3; c++) lut[i * 3 + c] = Math.round(stops[k][c] + (stops[k + 1][c] - stops[k][c]) * f);
    }
    return lut;
  }
  const lutCss = (lut, n) => 'linear-gradient(90deg,' + Array.from({ length: n }, (_, j) => {
    const k = Math.round(j / (n - 1) * 512) * 3;
    return 'rgb(' + lut[k] + ',' + lut[k + 1] + ',' + lut[k + 2] + ')';
  }).join(',') + ')';

  /* The CSD of [t0, t1] as an image one pixel per column and one row per
     contact. A column wider than a sample keeps its strongest sample (sign
     and all), so a discharge never falls between two columns. */
  function csdImage(B, t0, t1, cols, lut) {
    const H = B.header.csd, A = B.arrays.csd, rows = H.csc.length, n = A.length / rows, fs = H.fs, T0 = B.header.t0, vmax = H.vmax;
    const img = new ImageData(cols, rows), px = img.data;
    const spc = (t1 - t0) * fs / cols;
    for (let c = 0; c < cols; c++) {
      const ta = (t0 - T0) * fs + c * spc, tb = ta + spc, mid = (ta + tb) / 2;
      if (mid < 0 || mid > n - 1) continue;
      for (let r = 0; r < rows; r++) {
        const base = r * n;
        let v;
        if (spc <= 1.5) {
          const i = Math.min(n - 2, Math.floor(mid)), f = mid - i;
          v = A[base + i] * (1 - f) + A[base + i + 1] * f;
        } else {
          const ia = Math.max(0, Math.floor(ta)), ib = Math.min(n - 1, Math.ceil(tb));
          v = 0;
          for (let i = ia; i <= ib; i++) { const s = A[base + i]; if ((s < 0 ? -s : s) > (v < 0 ? -v : v)) v = s; }
        }
        const k = Math.max(0, Math.min(512, Math.round((v / vmax + 1) * 256))) * 3, o = (r * cols + c) * 4;
        px[o] = lut[k]; px[o + 1] = lut[k + 1]; px[o + 2] = lut[k + 2]; px[o + 3] = 255;
      }
    }
    const cv = document.createElement('canvas');
    cv.width = cols; cv.height = rows;
    cv.getContext('2d').putImageData(img, 0, 0);
    return cv;
  }

  /* where everything sits, in CSS pixels, for a canvas w wide */
  const PL = { lab: 98, right: 44, top: 24, rowH: 4, gapU: 5, unitH: 14, axis: 18, gapO: 8, overH: 26, overAxis: 21 };
  function probeLayout(w, B) {
    const rows = B.header.csd.csc.length;
    const x0 = PL.lab, x1 = Math.max(x0 + 80, w - PL.right);
    const y0 = PL.top, y1 = y0 + rows * PL.rowH;
    const u0 = y1 + PL.gapU, u1 = u0 + PL.unitH;
    const a0 = u1 + 2;
    const o0 = a0 + PL.axis + PL.gapO, o1 = o0 + PL.overH;
    return { w, h: o1 + PL.overAxis, x0, x1, y0, y1, u0, u1, a0, o0, o1 };
  }
  /* a zone's rows on the picture (its contacts that have a CSD row) */
  function zoneSpan(B, L, z) {
    const csc = B.header.csd.csc, c0 = csc[0], c1 = csc[csc.length - 1];
    const a = Math.max(c0, z.csc[0]), b = Math.min(c1, z.csc[1]);
    return b < a ? null : [L.y0 + (a - c0) * PL.rowH, L.y0 + (b - c0 + 1) * PL.rowH];
  }
  /* the contact under a point of the picture */
  function cscAt(B, L, y) {
    const csc = B.header.csd.csc;
    const r = Math.floor((y - L.y0) / PL.rowH);
    return r >= 0 && r < csc.length ? csc[r] : null;
  }

  /* The traces of [t0, t1]: a line through every sample when they fit, the
     envelope of each pixel column when they do not (a 30 s window). Figure A
     drew one second across a page; squeezed into a card, seconds of them
     would hide the CSD under them, so the longer the window the fewer and
     fainter they are (every eighth contact below 60 px a second). */
  function drawTraces(ctx, B, L, t0, t1, rgb, dpr) {
    const H = B.header.lfp, A = B.arrays.lfp, nt = H.csc.length, n = A.length / nt, fs = H.fs, T0 = B.header.t0;
    const c0 = B.header.csd.csc[0];
    const k = 4 * PL.rowH / H.gap_uv, lim = 1.3 * H.gap_uv;     // figure A: the gap spans four contacts; clipped at 1.3 gaps
    const i0 = Math.max(0, Math.floor((t0 - T0) * fs)), i1 = Math.min(n - 1, Math.ceil((t1 - T0) * fs));
    const pw = L.x1 - L.x0, cols = Math.max(1, Math.round(pw * dpr)), per = (i1 - i0) / cols;
    const pxs = pw / (t1 - t0), sparse = pxs < 60;
    const alpha = Math.max(0.2, Math.min(0.45, 0.2 + 0.25 * (pxs - 10) / 100));
    ctx.save();
    ctx.beginPath(); ctx.rect(L.x0, L.y0 - 4, pw, L.y1 - L.y0 + 8); ctx.clip();
    ctx.strokeStyle = 'rgba(' + rgb.join(',') + ',' + alpha.toFixed(2) + ')';
    ctx.lineWidth = per > 2 ? 0.6 : 0.85; ctx.lineJoin = 'round';
    for (let j = sparse ? 1 : 0; j < nt; j += sparse ? 2 : 1) {
      const yb = L.y0 + (H.csc[j] - c0 + 0.5) * PL.rowH, base = j * n;
      const Y = (v) => yb - (v > lim ? lim : v < -lim ? -lim : v) * k;
      ctx.beginPath();
      if (per <= 2) {
        const sx = pw / ((t1 - t0) * fs), xa = L.x0 + ((T0 + i0 / fs) - t0) / (t1 - t0) * pw;
        ctx.moveTo(xa, Y(A[base + i0]));
        for (let i = i0 + 1; i <= i1; i++) ctx.lineTo(xa + (i - i0) * sx, Y(A[base + i]));
      } else {
        for (let c = 0; c < cols; c++) {
          const a = i0 + Math.floor(c * per), b = Math.min(i1, i0 + Math.floor((c + 1) * per));
          let lo = 32767, hi = -32768;
          for (let i = a; i <= b; i++) { const v = A[base + i]; if (v < lo) lo = v; if (v > hi) hi = v; }
          const x = L.x0 + (c + 0.5) / dpr;
          if (c === 0) ctx.moveTo(x, Y(hi)); else ctx.lineTo(x, Y(hi));
          ctx.lineTo(x, Y(lo));
        }
      }
      ctx.stroke();
    }
    ctx.restore();
  }

  /* The whole recording, -12 to +60 s, as one strip: cached per size and theme. */
  function overviewImage(B, L, lut, dpr, key) {
    if (B._ov && B._ov.key === key) return B._ov.cv;
    const cols = Math.max(2, Math.round((L.x1 - L.x0) * dpr));
    const cv = csdImage(B, B.header.t0, B.header.t1, cols, lut);
    B._ov = { key, cv };
    return cv;
  }

  /* Draw the picture for one stop. o: {win, zones, marks, offs, dark, c: colours, font, zoneColor(key)}.
     Returns where things are, for the cursor, the veil and the pointer. */
  function drawProbe(cv, D, B, o) {
    const w = Math.max(260, Math.round(cv.parentNode.clientWidth || 420));
    const L = probeLayout(w, B);
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(L.h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(L.h * dpr); }
    cv.style.width = w + 'px'; cv.style.height = L.h + 'px';
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, L.h);
    const c = o.c, f = o.font, zone = new Set(o.zones || []);
    const [t0, t1] = o.win, pw = L.x1 - L.x0;
    const X = (t) => L.x0 + (t - t0) / (t1 - t0) * pw;
    const T0 = B.header.t0, T1 = B.header.t1, XO = (t) => L.x0 + (t - T0) / (T1 - T0) * pw;
    const lutKey = (o.dark ? 'd' : 'l') + c.zero.join(',');
    if (!B._lut || B._lut.key !== lutKey) B._lut = { key: lutKey, lut: csdLut(o.dark, c.zero) };
    const lut = B._lut.lut;

    // the current source density, smoothed between contacts as figure A was
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(csdImage(B, t0, t1, Math.max(2, Math.round(pw * dpr)), lut), L.x0, L.y0, pw, L.y1 - L.y0);
    // the zones' borders, faint (figure A's dashed lines)
    ctx.save();
    ctx.setLineDash([3, 3]); ctx.strokeStyle = c.line; ctx.lineWidth = 1;
    D.zones.forEach((z, i) => {
      if (!i) return;
      const s = zoneSpan(B, L, z);
      if (s) { ctx.beginPath(); ctx.moveTo(L.x0, Math.round(s[0]) + 0.5); ctx.lineTo(L.x1, Math.round(s[0]) + 0.5); ctx.stroke(); }
    });
    ctx.restore();
    // the onset
    if (t0 < 0 && t1 > 0) { ctx.fillStyle = c.onset; ctx.fillRect(Math.round(X(0)), L.y0, 1, L.u1 - L.y0); }
    // the potentials over it
    drawTraces(ctx, B, L, t0, t1, c.trace, dpr);
    // where each zone fell quiet (its firing, measured from the multi-unit activity): a tick on
    // its rows, and the time beside the picture
    if (o.offs) {
      const outs = [];
      D.zones.forEach((z) => {
        const s = zoneSpan(B, L, z);
        if (!s || z.off_s == null || z.off_s < t0 || z.off_s > t1) return;
        const x = Math.round(X(z.off_s));
        ctx.fillStyle = c.halo; ctx.fillRect(x - 2, s[0], 5, s[1] - s[0]);
        ctx.fillStyle = o.zoneColor(z.key); ctx.fillRect(x - 1, s[0] + 0.5, 3, s[1] - s[0] - 1);
        outs.push({ y: (s[0] + s[1]) / 2, text: z.off_s.toFixed(1) + ' s', col: o.zoneColor(z.key) });
      });
      for (let i = 1; i < outs.length; i++) outs[i].y = Math.max(outs[i].y, outs[i - 1].y + 10.5);
      ctx.font = '600 9.5px ' + f; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
      outs.forEach((r) => { ctx.fillStyle = r.col; ctx.fillRect(L.x1 + 4, r.y - 3, 3, 6); ctx.fillStyle = c.text2; ctx.fillText(r.text, L.x1 + 10, r.y); });
    }
    // the plot's frame
    ctx.strokeStyle = c.frame; ctx.lineWidth = 1; ctx.strokeRect(L.x0 - 0.5, L.y0 - 0.5, pw + 1, L.y1 - L.y0 + 1);

    // the discharges, a tick each above the picture
    ctx.fillStyle = c.tick;
    for (const t of D.discharges) if (t >= t0 && t <= t1) ctx.fillRect(Math.round(X(t)), L.y0 - 5, 1, 3);
    // figure A's stages, bracketed
    ctx.font = '600 10px ' + f; ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
    for (const [a, b, lab] of o.marks || []) {
      if (b < t0 || a > t1) continue;
      const xa = Math.max(L.x0, X(a)), xb = Math.min(L.x1, X(b)), y = L.y0 - 9;
      ctx.strokeStyle = c.text2; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(xa + 0.5, y + 4); ctx.lineTo(xa + 0.5, y); ctx.lineTo(xb - 0.5, y); ctx.lineTo(xb - 0.5, y + 4); ctx.stroke();
      ctx.fillStyle = c.text2;
      ctx.fillText((o.marks.length > 1 ? '' : 'stage ') + lab, (xa + xb) / 2, y - 3);
    }

    // the zones: a colour key and a name each, top to bottom, none overlapping
    const named = D.zones.map((z) => { const s = zoneSpan(B, L, z); return s ? { z, s, y: (s[0] + s[1]) / 2 } : null; }).filter(Boolean);
    const ys = named.map((r) => r.y), gap = 11.5;
    for (let i = 1; i < ys.length; i++) ys[i] = Math.max(ys[i], ys[i - 1] + gap);
    const over = ys.length ? ys[ys.length - 1] - (L.y1 - 3) : 0;
    if (over > 0) for (let i = ys.length - 1; i >= 0; i--) { ys[i] -= over; if (i && ys[i - 1] > ys[i] - gap) ys[i - 1] = ys[i] - gap; }
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    named.forEach((r, i) => {
      const lit = zone.has(r.z.key), col = o.zoneColor(r.z.key);
      ctx.fillStyle = col; ctx.globalAlpha = lit || !zone.size ? 1 : 0.55;
      ctx.fillRect(L.x0 - 6, r.s[0] + 0.5, 3, r.s[1] - r.s[0] - 1);
      ctx.globalAlpha = 1;
      if (Math.abs(ys[i] - r.y) > 1.5) {
        ctx.strokeStyle = c.line; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(L.x0 - 10, ys[i]); ctx.lineTo(L.x0 - 7, r.y); ctx.stroke();
      }
      ctx.font = (lit ? '650 ' : '500 ') + '10.5px ' + f;
      ctx.fillStyle = lit ? c.text : c.text3;
      ctx.fillText(ZONE_WORDS[r.z.key][1], L.x0 - 11, ys[i]);
    });
    // and the zones this stop is about, barred beside the picture (figure A's bars)
    named.forEach((r) => {
      if (!zone.has(r.z.key)) return;
      ctx.fillStyle = o.zoneColor(r.z.key);
      ctx.fillRect(L.x1 + 4, r.s[0] + 0.5, 5, r.s[1] - r.s[0] - 1);
    });
    // the traces' scale (figure A's 2 mV), under the picture's right end, out of the way of the bars
    const bar = 2000 * 4 * PL.rowH / B.header.lfp.gap_uv;
    ctx.fillStyle = c.text2; ctx.fillRect(L.x1 + 16, L.a0 + 1, 2, bar);
    ctx.font = '500 9.5px ' + f; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.fillText('2 mV', L.x1 + 21, L.a0 + 1 + bar / 2);

    // the hilar interneuron, its spikes a tick each
    ctx.fillStyle = c.band; ctx.fillRect(L.x0, L.u0, pw, L.u1 - L.u0);
    const ms = B.header.unit.masked;
    if (ms && ms[1] > t0 && ms[0] < t1) {
      const xa = Math.max(L.x0, X(ms[0])), xb = Math.min(L.x1, X(ms[1]));
      ctx.save(); ctx.beginPath(); ctx.rect(xa, L.u0, xb - xa, L.u1 - L.u0); ctx.clip();
      ctx.strokeStyle = c.hatch; ctx.lineWidth = 1;
      ctx.beginPath();
      for (let x = xa - 20; x < xb + 20; x += 5) { ctx.moveTo(x, L.u1); ctx.lineTo(x + (L.u1 - L.u0), L.u0); }
      ctx.stroke();
      if (xb - xa > 150) {
        const tx = 'single spikes hidden by the discharges', cx = (xa + xb) / 2, cy = (L.u0 + L.u1) / 2 + 0.5;
        ctx.font = '500 9.5px ' + f; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        const tw = ctx.measureText(tx).width + 10;
        ctx.fillStyle = c.label; ctx.fillRect(cx - tw / 2, L.u0 + 1, tw, L.u1 - L.u0 - 2);
        ctx.fillStyle = c.text3; ctx.fillText(tx, cx, cy);
      }
      ctx.restore();
    }
    ctx.fillStyle = c.cell;
    const S = B.arrays.spikes;
    for (let i = 0; i < S.length; i++) { const t = S[i]; if (t >= t0 && t <= t1) ctx.fillRect(Math.round(X(t)), L.u0 + 2, 1.3, L.u1 - L.u0 - 4); }
    ctx.font = '500 10px ' + f; ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; ctx.fillStyle = o.unitLit ? c.text : c.text3;
    ctx.fillText('Interneuron, ch ' + B.header.unit.csc, L.x0 - 11, (L.u0 + L.u1) / 2);
    // time
    axis(ctx, L.x0, L.x1, L.a0, t0, t1, { ink3: c.text3, font: f });

    // the whole recording, this stop's window boxed
    ctx.drawImage(overviewImage(B, L, lut, dpr, [w, dpr, lutKey].join('|')), L.x0, L.o0, pw, L.o1 - L.o0);
    const ba = XO(Math.max(T0, t0)), bb = XO(Math.min(T1, t1));
    ctx.fillStyle = c.dim;
    ctx.fillRect(L.x0, L.o0, ba - L.x0, L.o1 - L.o0);
    ctx.fillRect(bb, L.o0, L.x1 - bb, L.o1 - L.o0);
    ctx.fillStyle = c.onset; ctx.fillRect(Math.round(XO(0)), L.o0, 1, L.o1 - L.o0);
    ctx.strokeStyle = c.accent; ctx.lineWidth = 1.5;
    ctx.strokeRect(ba - 0.75, L.o0 - 1.5, Math.max(2, bb - ba) + 1.5, L.o1 - L.o0 + 3);
    ctx.font = '500 10px ' + f; ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; ctx.fillStyle = c.text3;
    ctx.fillText('The whole seizure', L.x0 - 11, (L.o0 + L.o1) / 2);
    axis(ctx, L.x0, L.x1, L.o1 + 2, T0, T1, { ink3: c.text3, font: f });
    return Object.assign(L, { t0, t1, T0, T1, dpr });
  }

  return { REFS, TAGS, ACTS, ZONE_WORDS, SCALE, stories, at, level, zoneLevels, unitRate, ramp, alphaOf, rgba, rampCss,
           picOf, drawProbe, cscAt, zoneSpan, lutCss, csdLut, PL };
})();
