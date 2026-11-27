# Sextant: what the literature says about placing a probe in the hippocampus

Written 2026-11-27 for Sextant (Seahorse > Place a probe). It covers four things:

- how others locate electrodes;
- which signals mark which hippocampal layer;
- how the hippocampus's shape changes with position;
- what PTEN loss does to the dentate.

Each detector and model choice in `backend/sextant/` points back to a section here.

## 1. How others place probes

- **Histology first, physiology to finish.** The International Brain Laboratory reconstructs each probe track from histology in the Allen Common Coordinate Framework (CCF). It then slides and stretches the electrodes along that track until physiological features line up with the atlas regions: firing rate, neuron yield, and LFP power in set bands. Their alignment GUI fits a depth scaling between pairs of reference lines (IBL 2024; IBL alignment GUI documentation). Histology alone usually gives the track but not the tip, which is why physiology is needed at all.
- **Physiology alone.** Region identity can be decoded from spike trains, and it transfers across animals and labs (Tolossa et al. 2024). Neuron-level embeddings classify brain regions on the IBL Brain-wide Map (NEMO, ICLR 2025). Neither places a probe within the layers of one structure. Sextant asks that finer, layer-level question, which those decoders do not answer.
- **The hippocampal tradition.** Layers are read from physiology:
  - the ripple-amplitude peak and the sharp-wave reversal mark CA1's pyramidal layer (used to anchor depth by Lubenov & Siapas 2009, among many);
  - the dentate spike's depth profile marks the dentate's layers (Senzai & Buzsáki 2017 placed granule and mossy cells by the DS2 profile).

  Sextant automates this reading and adds the atlas.
- **Coordinates.**
  - The CCF has no official bregma. It was built from fixed brains outside the skull, about 30% smaller in volume than in the cranium (Allen Institute; Wang et al. 2020).
  - Sextant uses the IBL's bregma: the average of five experimenters picking it on the atlas, CCF ML 5739, AP 5400, DV 332 µm, with no scaling.
  - A community estimate puts the CCF about 94% stretched in depth.
  - Sextant fits a size factor along the shank, which absorbs fixed-tissue shrinkage and tissue compressed during insertion.
- **Insertion.** Cortex can dimple by hundreds of micrometers before a probe breaks through, so the depth the drive reads is not the depth reached. Dimpling depends on probe shape, insertion speed and dura (Obaid et al. 2020; Fiáth et al. 2019; reviews therein). That is one reason Sextant reads depth from the recording, not from the drive.

## 2. What marks each layer

| Layer (landmark) | Signal | Sources |
|---|---|---|
| CA1 stratum pyramidale (`sp`) | Ripple-band power highest against theta during stillness; multiunit firing peaks; ripple power during ripples peaks | Buzsáki 2015; Ylinen et al. 1995; Toothy's ripple rule (StrataScope) |
| sp / radiatum border (`spw_rev`) | The sharp wave changes sign | Ylinen et al. 1995; Lubenov & Siapas 2009 |
| Stratum radiatum (`sr_sink`) | The sharp wave's current sink, where CA3's Schaffer collaterals land; in 81% of ripples the dominant sink is in radiatum | Ylinen et al. 1995; Castelli et al. 2025 |
| Lacunosum-moleculare (`slm_src`) | The sharp wave's return current (source). Some ripples sink here instead, a distinct subtype | Castelli et al. 2025 |
| Hippocampal fissure (`fissure`) | Theta amplitude's first maximum below the cell layer. Theta's phase shifts gradually by about 180° from oriens to the fissure | Winson 1974; Buzsáki 2002; Kamondi et al. 1998 |
| Dentate molecular layers (`ml_a`, `ml_b`) | Dentate spikes sink current in the outer third (DS1: lateral entorhinal input) and the middle third (DS2: medial entorhinal input), in both blades | Bragin et al. 1995; Dvorak et al. 2021; Santiago et al. 2024; Farrell et al. 2024; Tarcsay et al. 2025 |
| Granule cells and hilus (`dg_core`) | The dentate spike's return current; the largest positive DS potential is in the hilus | Bragin et al. 1995 |
| Dentate gamma (shown, not fitted) | Gamma is largest in the hilus (Bragin et al. 1995 gamma). By pathway: slow gamma (30–50 Hz) is LEC to OML, mid (about 63 Hz) commissural to IML, fast (100–150 Hz) MEC to MML | Bragin et al. 1995; Fernández-Ruiz et al. 2021 |
| CA1 gamma by layer (context) | Slow gamma in radiatum (CA3 input), mid in lacunosum-moleculare (EC3 input), fast near the pyramidal layer (local) | Lasztóczi & Klausberger 2014, 2016; Schomburg et al. 2014 |
| Below the dentate (`th_top`) | Units fire again in the thalamus under the dorsal hippocampus | Allen CCFv3 anatomy |
| P-spikes and BTs (`ps_*`, `bt_*`) | Interictal spikes in epileptic dentate look like dentate spikes in current but are more spatially spread out, and are led by the dentate | Boublil & Ewell 2024 (abstract); Lisgaras & Scharfman 2023; Flynn et al. 2015 |

**Caveats that shaped the detectors:**
- **Raw ripple-band power peaks in the dentate in these mice**, from dentate-spike energy (found in StrataScope work, 2026-10-09). So CA1 is found from ripples against theta, above the dentate. It is never found from the raw maximum.
- **In PTEN dentates theta and multiunit firing can peak deep in the hilus.** So the dentate is found first, from the two largest dentate-spike sinks, and CA1's cell layer is looked for only above it.
- **The dentate spike's lower blade can carry four times the current of the upper in high-knockout mice.** So a weaker second blade counts when a strong granule-cell return current lies between the two.
- **Theta's maximum lands near the fissure, give or take a few contacts.** That's why it carries the widest uncertainty of the CA1 landmarks (3 contacts).

## 3. Pathway-specific generators (Method B)

- Hippocampal LFP is a sum of a few pathway-specific generators, each with a fixed layer pattern. Independent component analysis recovers about six of them, matching known synaptic territories (Makarov et al. 2010; Makarova et al. 2011; Benito et al. 2014; reviewed by Herreras 2016). Theta has three generators (López-Madrona et al. 2020).
- Turning a layered current into voltage at the contacts uses the standard laminar volume conductor: a disk of finite radius (Pettersen et al. 2006, the iCSD forward model).
- Fitting the LFP itself proved too forgiving: the LFP is smooth, and pathway strengths of opposite sign can put a sink anywhere. Sextant therefore fits the current source density, with synaptic sinks held positive. Method A and Method B then agree (m2: both put the entry at AP −2.33, ML 1.15).

## 4. The hippocampus changes with position

Measured on the atlas, not taken from a paper: Allen CCFv3 at 10 µm with Seahorse's derived strata and molecular-layer thirds.

- **At the craniotomy** (AP −2.2, ML 1.4 mm), a vertical probe crosses, in µm:

  | Layer | CA1 so | CA1 sp | radiatum | lacunosum-moleculare | upper blade (OML, MML, IML) | GCL | hilus | lower GCL | lower blade (IML, MML, OML) |
  |---|---|---|---|---|---|---|---|---|---|
  | Thickness | 90 | 80 | 370 | 100 | 70, 70, 60 | 100 | 50 | 70 | 60, 70, 70 |

  Then thalamus. About 1.2 mm in all, close to the H3's 1.26 mm.
- **0.4 mm medial**, the probe meets the dentate's crest. There is no hilus, and the two molecular-layer crossings come within about 200 µm of each other (m2 looks like this).
- **Lateral or anterior**, CA3 enters the hilus.
- **Posterior and medial**, the subiculum replaces CA1.
- **Medially**, a thick band of white matter puts CA1 about 1.6 mm deep, against about 1.3 mm at ML 1.4.
- So how far apart the landmarks sit on the shank carries the position: cell layer to fissure, fissure to the first sink, sink to sink. A tilt stretches every layer by 1/cos of the angle.
- **AP is the hardest to pin down.** The dorsal hippocampus changes slowly from front to back, so one shank's spacings fit a run of AP positions. Expect AP to be the widest range in every placement. The planted-probe check measures how wide.

## 5. PTEN and the dentate

- Deleting Pten from adult-born granule cells makes them:
  - hypertrophic, with bigger somata and excess dendrite and axon growth;
  - prone to ectopic migration into the hilus;
  - prone to hilar basal dendrites and mossy-fiber sprouting;
  - and it causes epilepsy (Pun et al. 2012; LaSarge et al. 2015, 2016; Santos et al. 2017; reviewed by LaSarge et al. 2021).
- The share of knockout granule cells can run from under 1% to over 30%, with effects on their normal neighbors (LaSarge et al. 2019).
- No paper found here measures dentate layer thickness in this model. So Sextant does not assume an enlargement. It fits how much the dentate stretches in each PTEN mouse, compares that with what the controls show (the user's choice: "learn normal from controls"), and reports the mice outside the controls' range.

## 6. What would make it better

- **Ground truth:**
  - a DiI-painted probe and a Nissl section for even a few mice would turn the planted-probe check into a real one;
  - the probe's actual entry point (photographed craniotomy, or drive readings) would tighten AP.
- **A second shank**, or the next session's probe moved a known distance, would pin AP, which one shank cannot.
- **The atlas's CA strata and molecular-layer thirds are derived**, not annotated. Their boundaries carry about one voxel (10 µm) of uncertainty, and the thirds are a convention.

## References

- Benito N, Fernández-Ruiz A, Makarov VA, Makarova J, Korovaichuk A, Herreras O (2014) Spatial modules of coherent activity in pathway-specific LFPs in the hippocampus reflect topology and different modes of presynaptic synchronization. Cereb Cortex 24:1738-1752.
- Boublil B, Ewell L (2024) Dissecting synaptic contributions to interictal spikes in vivo. AES abstract. https://aesnet.org/abstractslisting/dissecting-synaptic-contributions-to-interictal-spikes-in-vivo
- Bragin A, Jandó G, Nádasdy Z, van Landeghem M, Buzsáki G (1995) Dentate EEG spikes and associated interneuronal population bursts in the hippocampal hilar region of the rat. J Neurophysiol 73:1691-1705.
- Bragin A, Jandó G, Nádasdy Z, Hetke J, Wise K, Buzsáki G (1995) Gamma (40-100 Hz) oscillation in the hippocampus of the behaving rat. J Neurosci 15:47-60. https://pmc.ncbi.nlm.nih.gov/articles/PMC6578273
- Buzsáki G (2002) Theta oscillations in the hippocampus. Neuron 33:325-340.
- Buzsáki G (2015) Hippocampal sharp wave-ripple: a cognitive biomarker for episodic memory and planning. Hippocampus 25:1073-1188.
- Castelli M, et al. (2025) Neuron (ripple current-sink subtypes in mouse CA1). https://www.mrcbndu.ox.ac.uk/sites/default/files/Castelli2025Neuron.pdf
- Dvorak D, Chung A, Park EH, Fenton AA (2021) Dentate spikes and external control of hippocampal function. Cell Rep 36:109497.
- Farrell JS, et al. (2024) In vivo dentate spike types. https://www.nature.com/articles/s41586-024-07192-8
- Fernández-Ruiz A, Oliva A, Soula M, Rocha-Almeida F, Nagy GA, Martin-Vazquez G, Buzsáki G (2021) Gamma rhythm communication between entorhinal cortex and dentate gyrus neuronal assemblies. Science 372:eabf3119. https://pmc.ncbi.nlm.nih.gov/articles/PMC8285088
- Flynn SP, et al. (2015) Status epilepticus induced spontaneous dentate gyrus spikes: in vivo current source density analysis. PLoS One. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4492740/
- Herreras O (2016) Local field potentials: myths and misunderstandings. Front Neural Circuits 10:101.
- International Brain Laboratory, Banga K, et al. (2024) Reproducibility of in vivo electrophysiological measurements in mice. eLife 13:RP100840. https://elifesciences.org/articles/100840
- International Brain Laboratory, ephys alignment GUI. https://int-brain-lab.github.io/ibl-alignment-gui/getting_started.html ; atlas conventions (bregma, scaling): https://int-brain-lab.github.io/iblenv/_autosummary/iblatlas.html
- Kamondi A, Acsády L, Wang XJ, Buzsáki G (1998) Theta oscillations in somata and dendrites of hippocampal pyramidal cells in vivo. Hippocampus 8:244-261.
- LaSarge CL, Santos VR, Danzer SC (2015) PTEN deletion from adult-generated dentate granule cells disrupts granule cell mossy fiber axon structure. Neurobiol Dis 75:142-150. https://pmc.ncbi.nlm.nih.gov/articles/PMC4351143
- LaSarge CL, Pun RYK, Muntifering MB, Danzer SC (2016) Disrupted hippocampal network physiology following PTEN deletion from newborn dentate granule cells. Neurobiol Dis 96:105-114. https://pmc.ncbi.nlm.nih.gov/articles/PMC5102799
- LaSarge CL, et al. (2019) Pten-deleted granule cells and their neighbors (knockout fraction under 1% to over 30%). https://pmc.ncbi.nlm.nih.gov/articles/PMC6744293
- LaSarge CL, et al. (2021) Review: Pten and dentate granule cells. https://pmc.ncbi.nlm.nih.gov/articles/PMC8026598
- Lasztóczi B, Klausberger T (2014) Layer-specific GABAergic control of distinct gamma oscillations in the CA1 hippocampus. Neuron 81:1126-1139.
- Lasztóczi B, Klausberger T (2016) Hippocampal place cells couple to three different gamma oscillations during place field traversal. Neuron 91:34-40.
- Lisgaras CP, Scharfman HE (2023) Interictal spikes in Alzheimer's model mice. Neurobiol Dis. https://doaj.org/article/1fa6bd3e39044a8fa130e3ef345f0d6a
- López-Madrona VJ, et al. (2020) Different theta frameworks coexist in the rat hippocampus and are coordinated during memory-guided and novelty tasks. eLife 9:e57313.
- Lubenov EV, Siapas AG (2009) Hippocampal theta oscillations are travelling waves. Nature 459:534-539.
- Makarov VA, Makarova J, Herreras O (2010) Disentanglement of local field potential sources by independent component analysis. J Comput Neurosci 29:445-457.
- Makarova J, et al. (2011) Can pathway-specific LFPs be faithfully obtained in compact neuronal structures? Front Syst Neurosci 5:77. https://pmc.ncbi.nlm.nih.gov/articles/PMC3171694
- Pettersen KH, Devor A, Ulbert I, Dale AM, Einevoll GT (2006) Current-source density estimation based on inversion of electrostatic forward solution. J Neurosci Methods 154:116-133.
- Pun RYK, et al. (2012) Excessive activation of mTOR in postnatally generated granule cells is sufficient to cause epilepsy. Neuron 75:1022-1034. https://pmc.ncbi.nlm.nih.gov/articles/PMC3474536
- Santiago RMM, et al. (2024) Waveform-based classification of dentate spikes. Sci Rep 14:2989. https://www.nature.com/articles/s41598-024-53075-3
- Santos VR, et al. (2017) PTEN deletion increases hippocampal granule cell excitability... Neurobiol Dis. https://doaj.org/article/74ce67b9679e498481eae3c323676666
- Schomburg EW, Fernández-Ruiz A, Mizuseki K, et al. (2014) Theta phase segregation of input-specific gamma patterns in entorhinal-hippocampal networks. Neuron 84:470-485.
- Senzai Y, Buzsáki G (2017) Physiological properties and behavioral correlates of hippocampal granule cells and mossy cells. Neuron 93:691-704. https://pmc.ncbi.nlm.nih.gov/articles/PMC5293146
- Tarcsay G, et al. (2025) Dentate spikes comprise a continuum of relative input strength from the lateral and medial entorhinal cortex. bioRxiv. https://www.biorxiv.org/content/10.1101/2025.10.27.684857.full.pdf
- Tolossa GB, Schneider AM, Dyer EL, Hengen KB (2024) Neurons throughout the brain embed robust signatures of their anatomical location into spike trains. eLife 13:RP101506. https://elifesciences.org/articles/101506
- Wang Q, Ding SL, Li Y, et al. (2020) The Allen Mouse Brain Common Coordinate Framework: a 3D reference atlas. Cell 181:936-953.
- Winson J (1974) Patterns of hippocampal theta rhythm in the freely moving rat. Electroencephalogr Clin Neurophysiol 36:291-301.
- Ylinen A, Bragin A, Nádasdy Z, et al. (1995) Sharp wave-associated high-frequency oscillation (200 Hz) in the intact hippocampus. J Neurosci 15:30-46.
- Yu H, Lyu H, Xu EY, et al. (2025) NEMO: multimodal neuron embeddings for cell type and brain region classification. ICLR. https://proceedings.iclr.cc/paper_files/paper/2025/file/bfb0920bdcfa44b7411824f43ac8c02a-Paper-Conference.pdf
- Obaid A, et al. (2020) and Fiáth R, et al. (2019) on insertion dimpling and speed: see https://pmc.ncbi.nlm.nih.gov/articles/PMC7261651 and https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8323825/
