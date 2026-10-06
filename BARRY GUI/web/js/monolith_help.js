/* ==========================================================================
   monolith_help.js -- what everything on the Monolith page means.

   Every ? on the page opens one of these, beside it: what it is in plain
   words, what to look for, what fools it, a line about the entry on screen,
   and -- for the measures and the statistics -- two synthetic examples, a
   strong effect and no effect, drawn from web/monolith_guide.json. That
   file is made by tools/monolith_guide.py with the Monolith's own engine
   (backend/sweep.py, backend/monolith.py), so the numbers under the
   pictures are what the real analysis says about those signals. The Guide
   page (monolith-guide.html) is every one of these, one after another.
   ========================================================================== */
'use strict';

window.MONO_HELP = (function () {
  const F = () => window.MONO_FIGS;
  let GUIDE = null;
  let loading = null;
  function guide() {
    if (GUIDE) return Promise.resolve(GUIDE);
    if (!loading) {
      loading = fetch('monolith_guide.json', { cache: 'no-cache' })
        .then((r) => (r.ok ? r.json() : null)).then((g) => { GUIDE = g; return g; })
        .catch(() => null);
    }
    return loading;
  }

  /* ---- the words ---------------------------------------------------- */
  const T = {
    verdict: {
      title: 'The counts at the top',
      plain: 'How many entries were tested (every window × frequency × measure × region pair that at least four rats had on both days), how many came out p < .05, and how many would by chance alone.',
      look: 'Compare p < .05 with the chance count. If they are close, most of what passes is noise; what matters is what stands out consistently.',
      traps: 'Every p here is uncorrected: with hundreds of thousands of tests, thousands pass by chance. The Monolith is for finding leads, not for proving them.',
      cite: ['Benjamini & Hochberg (1995). Controlling the false discovery rate. J R Stat Soc B 57:289–300.'],
      demo: 'null',
    },
    layer: {
      title: 'Layer: raw or minus FP',
      plain: 'Two ways of measuring each rat’s change from Precon1 to Precon4. Raw uses the cue pairs alone. Minus FP takes each day’s rest away first — the same measure on the same wires in that day’s no-cue recordings (FP1 and FP2) — so whatever changed for the whole day, and not for the cue windows, falls out. For one entry (one window, band, measure and region pair), minus FP is worked out like this:',
      steps: [
        'Every cue pair of the day gives the entry one number, measured in its window (Cue 1, say: ten seconds). Both pairings count. A cue pair whose wires were clipped in that window gives none, and is left out rather than filled in.',
        'Rest, the same day: the rat was also recorded with no cues, in FP1 and FP2. From those Jarvis cut ten-second epochs — as many as the day had cue pairs of one pairing (eight, say) — spread evenly across FP1 and FP2, at least ten seconds in from each end, and checked for clipping by the same detector as the cue windows. Each epoch gives the entry one number: same band, same measure, same two regions, same wires where they survive.',
        'The first averaging, within the day. Cue: the mean over the day’s cue pairs, with its standard error (their spread ÷ √n). Rest: the mean over the day’s rest epochs, with its standard error. Rest has only the one ten-second window, so the same rest mean stands against every cue window — Baseline, Cue 1, Cue 2, After, and the three transitions.',
        'The subtraction: the day’s value is the cue mean − the rest mean. Its uncertainty adds rather than cancels: SE² = SE²(cue) + SE²(rest). Taking one noisy number from another makes the result noisier, never cleaner.',
        'The rat’s change: (cue − rest) on Precon4 minus (cue − rest) on Precon1, its variance the two days’ SE² added together. Raw is the same with the rest terms left out: cue on Precon4 minus cue on Precon1.',
        'The second averaging, over rats: every rat’s change pooled DerSimonian–Laird — each weighted by 1 ÷ (its own variance + τ², the spread between rats beyond their own noise) — and tested Hartung–Knapp on k − 1 degrees of freedom. It needs at least four rats with both days.',
      ],
      example: 'Say r3’s Cue 1 coherence at 10 Hz averaged 0.42 over its Precon1 cue pairs and 0.38 over its Precon1 rest epochs; on Precon4, 0.49 and 0.43. Raw change: 0.49 − 0.42 = +0.07. Minus FP: (0.49 − 0.43) − (0.42 − 0.38) = 0.06 − 0.04 = +0.02. Five hundredths of the seven were in rest as well: the rat’s whole day moved, and only two hundredths belong to the cue window.',
      look: 'An edge in raw that survives minus FP changed with the cues, relative to rest. One that vanishes changed in rest by about as much — the day changed (an electrode settling, the rat calmer, the recording quieter), not the response to the cues. One that appears only in minus FP is a cue change raw could not see, because rest moved the other way.',
      traps: 'Minus FP is noisier — both days carry rest’s error too — so a real but small cue change can fall below the line there. It assumes the day moves cue and rest by the same amount (additively); a change that scales everything is not removed exactly. Rest is a separate recording from the cue session, minutes apart, so it takes away what changed over the day, not what differs between rest and cues within one session. The transition windows are shorter than the ten-second rest epochs, and measures biased by window length (coherence, PLV) differ by that bias within a day — but the bias is the same on both days, so it cancels from the change.',
      demo: 'minus_fp',
    },
    windows: {
      title: 'Seven windows: 4 states, 3 transitions',
      plain: 'Every presentation is measured seven times. The 4 states are 10 s each: pre-baseline (before cue 1), cue 1, cue 2, post-baseline (after cue 2). The 3 transitions straddle the moments things change: cue 1 starting (onset), cue 1 giving way to cue 2 (switch), cue 2 ending (offset).',
      look: 'A state change says how the brain sat during a part of the pair; a transition change says how it moved at the boundary.',
      traps: 'Transition windows are shorter (6 s for slow bands, 3 s for fast), so their numbers are noisier than state ones.',
    },
    window: {
      title: 'Which window',
      plain: 'Pre-baseline is the 10 s before cue 1; cue 1 and cue 2 are the cues (about 10 s each); post-baseline is the 10 s after cue 2 ends. Onset, switch and offset are −3/+3 s around each boundary for bands up to 12 Hz (a 1 Hz cycle needs that long), and −1/+2 s for faster ones.',
      look: 'Compare the cue windows with pre-baseline in the same rat-day to see what the cue itself did.',
      traps: 'A window that touched clipping drops the clipped wire for that cue pair: shorter windows lose more cue pairs.',
    },
    frequency: {
      title: 'Frequency',
      plain: 'Every whole hertz from 1 to 55, each a band of ±15% around it (never narrower than ±0.5 Hz, never past 55 Hz so it stays clear of 60 Hz mains). Theta, beta and low gamma are the three named bands the earlier work used.',
      look: 'Something real usually shows over several neighbouring frequencies, not one. Use the strip below the circuit to see where in the spectrum things change.',
      traps: 'Below about 3 Hz a 10 s window holds only a few cycles, so slow bands are noisy; one isolated hertz is more likely chance than a band of them.',
      cite: ['Buzsáki & Draguhn (2004). Neuronal oscillations in cortical networks. Science 304:1926–1929.'],
    },
    bands: {
      title: 'Theta, beta, low gamma',
      plain: 'The three named bands (4–12, 13–30, 30–55 Hz), computed exactly as the Precon circuits were, so their state rows reproduce those numbers. Each 1 Hz band is a narrower view inside them.',
      look: 'A named-band result plus agreement in the 1 Hz bands inside it is a stronger lead than either alone.',
      traps: 'A wide band averages over everything in it: a change at 5 Hz and an opposite one at 10 Hz can cancel in theta.',
    },
    measure: {
      title: 'The measures',
      plain: 'Each asks a different question about two regions: do they share a rhythm (coherence), keep a steady phase relationship (PLV, PPC, PLI, wPLI), rise and fall in loudness together (envelope measures), line up at some delay (cross-correlation), or does one predict the other (Granger)?',
      look: 'Lag-blind measures (imaginary coherence, PLI, wPLI, orthogonalised envelopes) cannot be faked by two wires seeing the same source. When those agree with the others, the coupling is between regions.',
      traps: 'Coherence, PLV and plain envelope correlation are inflated by volume conduction and a shared reference.',
      cite: ['Bastos & Schoffelen (2016). A tutorial review of functional connectivity analysis methods and their interpretational pitfalls. Front Syst Neurosci 9:175.'],
    },
    coherence: {
      title: 'Coherence',
      plain: 'How much of the two regions’ activity in this band rises and falls together, in step, across the window. From 0 (unrelated) to 1 (one is a scaled, shifted copy of the other). Welch’s method, averaged over the band.',
      look: 'A higher value on Precon4: the two regions share more of this rhythm.',
      traps: 'Two wires picking up the same source (volume conduction, shared reference) are perfectly coherent at zero lag. Few segments bias it upward.',
      cite: ['Carter (1987). Coherence and time delay estimation. Proc IEEE 75:236–255.'],
      plot: 'coherence',
    },
    icoh: {
      title: 'Imaginary coherence',
      plain: 'Only the part of coherence that needs a time lag: the imaginary part of coherency, averaged over the band. A shared source seen by two wires at once has none.',
      look: 'Non-zero means a lagged, so genuinely between-region, relationship. Its sign says which leads.',
      traps: 'It misses coupling that really is at zero lag, and it is small when the lag is near half a cycle.',
      cite: ['Nolte et al. (2004). Identifying true brain interaction from EEG data using the imaginary part of coherency. Clin Neurophysiol 115:2292–2307.'],
      plot: 'icoh',
    },
    raw_cc: {
      title: 'Raw cross-correlation',
      plain: 'The two band-passed traces slid past each other, up to two cycles either way; the value is r at the lag where they line up best (signed).',
      look: 'A bigger peak on Precon4, and where the peak sits: positive lag means the first region follows the second.',
      traps: 'Two narrow-band signals line up somewhere within two cycles by chance, so the number is large even with no coupling. Only its change between days means anything. Peaks repeat every cycle.',
      cite: ['Bastos & Schoffelen (2016). Front Syst Neurosci 9:175.'],
      plot: 'raw_cc',
    },
    env_cc: {
      title: 'Envelope cross-correlation',
      plain: 'The same as raw cc but on the band’s loudness (its envelope), with its mean removed: do the two regions get loud and quiet together, and at what delay?',
      look: 'A rise means the regions’ loudness co-varies more. The peak’s lag says which tends to swell first.',
      traps: 'Short windows hold few envelope ups and downs, so chance correlations are large. A shared source makes envelopes match too.',
      cite: ['Adhikari et al. (2010). Cross-correlation of instantaneous amplitudes of field potential oscillations. J Neurosci Methods 191:191–200.'],
      plot: 'env_cc',
    },
    env_cc0: {
      title: 'Amplitude correlation at zero lag',
      plain: 'Pearson r between the two regions’ band envelopes at the same moment: no lag search, so no chance of picking the best of many.',
      look: 'Envelopes can be correlated with no phase relationship at all: a different kind of coupling from PLV.',
      traps: 'Volume conduction makes it near 1. A steady rhythm’s envelope barely varies, so its window edges can dominate.',
      cite: ['Bruns et al. (2000). Amplitude envelope correlation detects coupling among incoherent brain signals. NeuroReport 11:1509–1514.'],
      plot: 'env_cc0',
    },
    orth_env: {
      title: 'Orthogonalised envelope correlation',
      plain: 'Envelope correlation after taking out of each signal everything that is in phase with the other (both ways, averaged): what is left cannot come from one source seen twice.',
      look: 'Survives volume conduction: an increase here is loudness shared between regions.',
      traps: 'It removes genuine zero-lag coupling too, so it underestimates; with slowly drifting phases it is noisy.',
      cite: ['Hipp et al. (2012). Large-scale cortical correlation structure of spontaneous oscillatory activity. Nat Neurosci 15:884–890.'],
      plot: 'orth_env',
    },
    plv: {
      title: 'PLV (phase-locking value)',
      plain: 'How constant the phase difference between the regions is across the window: the length of the average of all the phase differences as arrows. 0 = all directions, 1 = always the same.',
      look: 'A higher PLV: the two keep a steadier timing relationship.',
      traps: 'Biased upward with few cycles (PPC fixes that), and fooled by volume conduction (a shared source gives PLV near 1 at zero phase).',
      cite: ['Lachaux et al. (1999). Measuring phase synchrony in brain signals. Hum Brain Mapp 8:194–208.'],
      plot: 'plv',
    },
    ppc: {
      title: 'PPC (pairwise phase consistency)',
      plain: 'PLV without its bias: the window is cut into pieces, and PPC is the average agreement between the phase differences of every pair of pieces. Unrelated signals average 0.',
      look: 'Comparable across windows of different lengths and days with different numbers of cycles.',
      traps: 'With few pieces (slow bands, short windows) it is noisy and can go negative. Still fooled by volume conduction.',
      cite: ['Vinck et al. (2010). The pairwise phase consistency: a bias-free measure of rhythmic neuronal synchronization. NeuroImage 51:112–122.'],
      plot: 'ppc',
    },
    pli: {
      title: 'PLI (phase-lag index)',
      plain: 'How consistently one region is ahead of the other in phase, counting only which side of zero the lag is on: |fraction ahead − fraction behind|.',
      look: 'Immune to zero-lag mixing: a shared source is never consistently ahead.',
      traps: 'Small lags near zero flip side with noise, so real coupling near zero lag is missed.',
      cite: ['Stam, Nolte & Daffertshofer (2007). Phase lag index. Hum Brain Mapp 28:1178–1193.'],
      plot: 'pli',
    },
    wpli: {
      title: 'wPLI (weighted phase-lag index)',
      plain: 'PLI weighted by how far from zero each lag is, so small lags that flip with noise count little.',
      look: 'A rise: one region more consistently leads the other.',
      traps: 'Biased upward with few samples (the debiased version fixes that).',
      cite: ['Vinck et al. (2011). An improved index of phase-synchronization for electrophysiological data. NeuroImage 55:1548–1565.'],
      plot: 'wpli',
    },
    dwpli: {
      title: 'Debiased wPLI',
      plain: 'The squared wPLI corrected for the number of pieces, as PPC corrects PLV: unrelated signals average 0.',
      look: 'The cleanest of the phase measures: lag-blind and unbiased.',
      traps: 'Noisy with few pieces; can be negative by chance.',
      cite: ['Vinck et al. (2011). NeuroImage 55:1548–1565.'],
      plot: 'dwpli',
    },
    gc_ab: {
      title: 'Granger A→B',
      plain: 'How much the first region’s past improves the prediction of the second’s, at these frequencies (spectral Granger causality, in nats). Computed from the spectrum without fitting a model (Wilson’s factorisation).',
      look: 'A rise: more of the second region’s activity in this band is predicted by the first.',
      traps: 'A third region driving both, or one region simply being cleaner (better signal-to-noise), can look like drive. It is never negative, so it is biased upward.',
      cite: ['Dhamala, Rangarajan & Ding (2008). Analyzing information flow in brain networks with nonparametric Granger causality. NeuroImage 41:354–362.', 'Geweke (1982). J Am Stat Assoc 77:304–313.'],
      plot: 'gc',
    },
    gc_ba: {
      title: 'Granger B→A',
      plain: 'The same, the other way: how much the second region’s past predicts the first’s.',
      look: 'Read it beside A→B: drive in one direction only is the clearest picture.',
      traps: 'As for A→B.',
      cite: ['Dhamala, Rangarajan & Ding (2008). NeuroImage 41:354–362.'],
      plot: 'gc',
    },
    gc_net: {
      title: 'Granger net',
      plain: 'A→B minus B→A. Positive: the first region drives the second more than the reverse. On the circuit it is drawn as an arrow the way the net drive grew.',
      look: 'Net direction is more robust than either direction alone: shared biases cancel.',
      traps: 'A difference in signal quality between the two regions can still tip it.',
      cite: ['Dhamala, Rangarajan & Ding (2008). NeuroImage 41:354–362.'],
      plot: 'gc',
    },
    power: {
      title: 'Node power',
      plain: 'Each node is coloured by its region’s own change in power at this frequency (log10 of Welch power density, pooled over rats like everything else). Red: louder on Precon4. Blue: quieter. A ring: the change passes the slider.',
      look: 'Coupling that rises where both regions also got louder may be about loudness, not coordination.',
      traps: 'Power differences between regions change coherence-type measures without any change in coupling.',
      cite: ['Welch (1967). The use of fast Fourier transform for the estimation of power spectra. IEEE Trans Audio Electroacoust 15:70–73.'],
      plot: 'power',
    },
    sig: {
      title: 'The significance slider',
      plain: 'Which edges are drawn: every tested entry, or only those whose p is below .05, .01, .001 or .0001. Stricter to the right. p comes from pooling the rats’ changes (DerSimonian–Laird) and testing the pool with Hartung–Knapp t on k − 1 degrees of freedom.',
      look: 'Edges that stay at the strict end, with every rat the same way, are the strongest leads.',
      traps: 'Uncorrected: even with nothing changing, about 5% pass at .05, 1% at .01 (see the null circuit below).',
      cite: ['DerSimonian & Laird (1986). Control Clin Trials 7:177–188.', 'Hartung & Knapp (2001). Stat Med 20:3875–3889.'],
      demo: 'null',
    },
    arrows: {
      title: 'Granger arrows',
      plain: 'Over any measure, draws the net Granger change (A→B minus B→A) as a dashed arrow wherever it passes the slider, pointing the way the net drive grew.',
      look: 'An edge with an arrow: the two regions changed together, and one of them came to lead.',
      traps: 'See Granger net: common input and unequal signal quality.',
      plot: 'gc',
    },
    circuit: {
      title: 'The circuit',
      plain: 'One node per region, one edge per region pair that passes the slider. Red edge: the measure rose from Precon1 to Precon4; blue: it fell. Thicker: a bigger change. Grey rings: regions no rat had usable (histology or wires).',
      look: 'Click an edge to lift it out and open it into its rats, days and cue pairs.',
      traps: 'A thick edge is a big change, not necessarily a reliable one: check how many rats agree.',
    },
    rank: {
      title: 'Rank overall, or within each window',
      plain: 'Overall: every entry of every window competes in one list, ranked by how many rats changed the same way, then by p. Within each window: the best three of each of the seven windows, ranked the same way, each window on its own.',
      look: 'Overall is what is strongest anywhere. Within each window stops one window with many strong entries (onset, often: the cue starting moves everything) from filling the whole list, so a smaller change at the switch or offset is still seen.',
      traps: 'The windows are not equally long, so their p are not equally easy to reach: a 3 s transition is noisier than a 10 s state. Comparing ranks across windows says which is stronger within its own window, not which is the bigger effect.',
    },
    trail: {
      title: 'Where this value comes from',
      plain: 'The path from the whole Monolith down to one presentation’s signals: the pooled change of a region pair, then each rat’s change, then one rat’s two sessions, then one session’s presentations, then one presentation. Each step says what its numbers are.',
      look: 'Click any earlier step to go back to it. Pooled and rat levels are changes (Precon4 − Precon1); session and presentation levels are values, not changes.',
      traps: 'Raw and minus FP give different numbers at every level: minus FP takes each session’s flower-pot rest off first. The layer is named at each step.',
    },
    points: {
      title: 'Points of interest',
      plain: 'Single entries with p < .05, ranked by how many rats changed the same way, then by p; at most three per region pair, and an entry within 2 Hz of one already listed (same window and measure) is the same finding and is listed under it.',
      look: 'Click one to snap the whole view to it. 8/8 rats is the strongest agreement there can be.',
      traps: 'Uncorrected p: a list this long always has chance entries. A broadband flag means it passes at most frequencies, which oscillatory coupling rarely does.',
      demo: 'agree',
    },
    broadband: {
      title: 'Broadband',
      plain: 'This region pair passes p < .05 at most of the 1 Hz bands in this window and measure.',
      look: 'Real oscillatory coupling usually lives in one or two bands. A change at nearly every frequency more often means something changed in the recording: a different wire or reference, a loose connection, movement.',
      traps: 'It is a flag, not a verdict: open the cue pairs and look at the traces.',
    },
    coverage: {
      title: 'Coverage',
      plain: 'How many of each rat’s cue pairs (and rest epochs) gave a value for this entry. A dash is a cue pair that did not, and its hover says why: a region with no usable wire in that window (every wire clipped or bad), or the measure could not be formed.',
      look: 'A rat whose day rests on two or three cue pairs counts for less in the pool, and should.',
      traps: 'Slow transition windows (6 s) lose more cue pairs to clipping than state windows.',
    },
    spectrum: {
      title: 'Across frequencies',
      plain: 'Bars: how many region pairs pass the slider at each frequency, for this window and measure. Line: the selected pair at every frequency, a filled dot where it passes.',
      look: 'A run of neighbouring frequencies is a band; one lone frequency is more likely chance.',
      traps: 'In transition view, bands left of the dashed line use −3/+3 s windows and those right of it −1/+2 s.',
    },
    trajectory: {
      title: 'Across the four sessions',
      plain: 'The selected line’s value in every Precon session — 1, 2, 3 and 4 — measured exactly as the Monolith measures Precon1 and Precon4. Left: every presentation in order, a panel a session, each rat its own colour and the mean over rats in black. Below: each rat’s session value (the mean over its presentations, less its flower-pot rest in minus FP), and the mean ± SE over rats.',
      look: 'Whether a change from Precon1 to Precon4 builds session by session, appears all at once, or comes and goes; and whether it is in every rat or a few. Within a session: whether it drifts from the first presentation to the last.',
      traps: 'Nothing here is tested, on purpose (the lab’s choice): the Monolith’s p is for Precon4 − Precon1 alone, and Precon2 and Precon3 never enter it. Four sessions of eight rats invite stories; read the shape, not single numbers. Presentations are lined up by their order in the session, not by which cue pair they were.',
    },
    events: {
      title: 'Events first: hippocampal P300-like events',
      plain: 'Large positive deflections in the dorsal hippocampus, found wherever they fall in the cue session rather than in fixed windows. The wire is band-passed (0.5–15 Hz by default) and put on a robust z scale over the session (median, and 1.4826 × the median absolute deviation, away from the rail); an event is a positive peak at or above the threshold (z 4), 150–500 ms wide at half its height, at least 500 ms after the last. Above the ceiling (z 15), or within 250 ms of the rail, it is an artifact and dropped. Each event is then placed against the presentations, and every other region’s wire is averaged around the events and around twice as many random times in the same session.',
      look: 'A rise in the histogram right after a cue, in most rats, that is bigger on Precon4: the events came to follow that cue. A region whose event-locked average beats random times in most rats, while others do not, moved with the hippocampus specifically.',
      traps: 'Something every wire shares — the reference, movement, chewing, a cable knock — makes events that show up in every region at once; the page warns when that is the pattern, and the example traces show it. A 1 Hz low edge takes about 40% off a 300 ms deflection and halves its width (measured), which is why the default is 0.5 Hz. Nothing here is tested across rats: the counts are descriptive.',
      cite: ['Polich (2007). Updating P300: an integrative theory of P3a and P3b. Clin Neurophysiol 118:2128–2148.', 'Halgren et al. (1980). Endogenous potentials generated in the human hippocampal formation and amygdala by infrequent events. Science 210:803–805.'],
    },
    'pac.self': {
      title: 'Phase–amplitude coupling within a region',
      plain: 'The conventional measure: does a slow rhythm’s phase (2–12 Hz) set how loud a faster one (15–50 Hz) is, both read from the same region’s wire? Tort’s modulation index (MI): how far the amplitude across 18 phase bins is from flat. Each session’s comodulogram is the mean over rats of each rat’s mean over its presentations; the change is pooled over rats as everything else on the page.',
      look: 'A patch of neighbouring cells that is already there on Precon1 and grows on Precon4, in most rats. Compare the region with the others at the same cell (the rows below the comodulograms), and open a typical presentation of each session to see the phase-binned amplitude itself.',
      traps: 'Sharp, non-sinusoidal waves and evoked responses produce PAC with no real coupling: look at the presentation’s traces. MI grows with noise in short windows, so the 6 s transitions sit higher than the 10 s states; compare like with like. Empty cells cannot carry their sidebands and are not measured.',
      cite: ['Tort et al. (2010). Measuring phase-amplitude coupling between neuronal oscillations of different frequencies. J Neurophysiol 104:1195–1210.', 'Aru et al. (2015). Untangling cross-frequency coupling in neuroscience. Curr Opin Neurobiol 31:51–61.'],
      plot: 'pac',
    },
    pac: {
      title: 'Phase–amplitude coupling across regions (exploratory)',
      plain: 'Does a slow rhythm’s phase (2–12 Hz) in one region set how loud a faster one (15–50 Hz) is in another? Tort’s modulation index: how far the amplitude across 18 phase bins is from flat. Shown is its change, Precon1 → Precon4, each way. Exploratory: how to read it is still being validated.',
      look: 'A cell that rises across rats: that slow rhythm came to organise that fast one. Check the within-region comodulograms first: cross-region PAC means more when each region’s own coupling is understood.',
      traps: 'Two regions on a shared reference, or picking up the same source, show cross-region PAC with no real interaction. Sharp, non-sinusoidal waves and evoked responses produce PAC with no real coupling. Empty cells cannot carry their sidebands and are not measured.',
      cite: ['Tort et al. (2010). Measuring phase-amplitude coupling between neuronal oscillations of different frequencies. J Neurophysiol 104:1195–1210.', 'Aru et al. (2015). Untangling cross-frequency coupling in neuroscience. Curr Opin Neurobiol 31:51–61.'],
      plot: 'pac',
    },
    'pac.circuit': {
      title: 'The PAC circuit at one cell',
      plain: 'For the chosen phase × amplitude cell: an arrow from the region giving the phase to the region whose amplitude it organises, wherever the change passes the slider. A filled node: its own PAC changed.',
      look: 'Hubs here are regions whose slow rhythm organises fast activity elsewhere.',
      traps: 'As for PAC.',
      plot: 'pac',
    },
    'ghost.pooled': {
      title: 'The pooled edge',
      plain: 'The edge as the circuit draws it: every rat’s change pooled. Below, each rat’s Precon1 and Precon4 values joined by a line.',
      look: 'Lines mostly sloping the same way: the change is shared across rats.',
      traps: 'Lines crossing in both directions with a few steep ones: the mean is carried by a few rats.',
      demo: 'agree',
    },
    'ghost.rats': {
      title: 'One edge per rat',
      plain: 'The pooled edge opened into the rats it averages: each rat’s change (Precon4 − Precon1) with its 95% interval, sized by its weight in the pool, and the pooled change as a diamond across its Hartung–Knapp interval.',
      look: 'Every square on the same side of zero, and the diamond clear of zero.',
      traps: 'One rat far from the rest pulls the mean but not the agreement count.',
      demo: 'outlier',
    },
    'ghost.days': {
      title: 'One rat’s two days',
      plain: 'The rat opened into its two days: one dot per cue pair, the day’s mean and standard error. Minus FP shows the rest epochs beside them.',
      look: 'A clear shift between the days relative to the spread within each.',
      traps: 'A day with few usable cue pairs has a wide error and little weight.',
      demo: 'day',
    },
    'ghost.units': {
      title: 'Every cue pair',
      plain: 'The day opened into its cue pairs (and rest epochs, dashed). Each is one window of real recording. Click one to see its traces and how each number was made.',
      look: 'Whether the day’s value comes from all its cue pairs or a few.',
      traps: 'A dash: not measured, and the hover says why.',
    },
    leaf: {
      title: 'One cue pair, down to its traces',
      plain: 'The recording itself, read from the cluster’s copy: the whole cue pair with its windows marked and the analysed window highlighted; that window raw, band-passed, as envelopes and as phase difference; and every measure’s own picture of it.',
      look: 'The number at the top of each picture is the analysis’s own, recomputed here; “matches” says it equals the stored value.',
      traps: 'One cue pair is one noisy sample: the pooled edge is what counts.',
    },
    averaged: {
      title: 'When we averaged',
      plain: 'One line of the circuit, followed from the recording up, with its own numbers. A wire’s trace is cleaned (mains out, brought down to 1000 Hz), cut to one window, filtered to one band, and measured: one number per cue pair. That is repeated for every cue pair of a day and averaged — the first averaging — giving one number per day (minus FP: less that day’s rest). Precon4 − Precon1 gives one change per rat. Those are averaged over rats — the second averaging, weighted by how sure each rat is — giving one change and one p, and the line is drawn if p passes the slider.',
      look: 'Where the number comes from: a pooled change carried by every rat, or by one; a day’s mean carried by every cue pair, or by a few.',
      traps: 'The traces shown are one cue pair of one rat on one day: a picture of how the number is made, not of the result. The result is step 7.',
    },
    split: {
      title: 'Cue pairs: both, or one half',
      plain: 'Every rat hears two pairings on every Precon day, and in every rat one of them has the Click in it and the other the Noise, one has the High tone and the other the Low tone. So each half of the cue pairs -- the Click pair, the Noise pair, the High-tone pair, the Low-tone pair -- is there in all eight rats, and is pooled exactly as the whole is: each rat’s Precon4 − Precon1 over that half’s cue pairs only, then over rats. The third way to halve them is by what conditioning later did: the pair whose second cue was followed by food, read from each rat’s own Con TTLs, and the other.',
      look: 'A change that is in both halves of a split is about the cue pairs in general; one that is in only one half is about that sound, that tone or that pair’s later meaning. During Precon a rat cannot yet tell the food pair from the other, so a real difference there would be a surprise worth checking.',
      traps: 'A half has half the cue pairs, so its days are noisier and fewer entries pass. Why not split by the exact pairing, Click → Low tone? The cohort is counterbalanced: each exact pairing is heard by only two rats, and two rats cannot be pooled.',
    },
    range: {
      title: 'A frequency range',
      plain: 'Pull the frequency slider’s two knobs apart and the circuit is drawn over every 1 Hz band between them. A line appears where the pair passes the significance slider at any, most (more than half), or every one of those bands; its colour and width are the median change over the range. Clicking it opens the band where it is strongest.',
      look: 'A change that holds across most of a range is a rhythm changing; one that passes at a single band of a wide range is more likely chance.',
      traps: '“Any” band in a range is a lenient rule: with ten bands, a pair passes it far more often than at one band by chance alone. “Most” or “every” is the honest reading of a range.',
    },
    filter: {
      title: 'Filtering the points of interest',
      plain: 'Narrows the list to what you are interested in: one measure or a family of them, one region or one pair, a frequency range (with or without the named bands inside it), state windows or transitions or one window, which way the change went, and whether broadband entries are in. The list is ranked again from every entry, by the same rule as the full list: p < .05, most rats the same way, then p, at most three a region pair.',
      look: 'A lead that keeps coming back however you slice it, and the count of entries that pass with the filter on.',
      traps: 'Narrowing a list does not make what is in it truer: every p is still uncorrected, and a filter chosen after looking at the data is a way of finding what you hoped to find.',
    },
    excluded: {
      title: 'Wires left out',
      plain: 'Each region has two or four wires; a window is computed on the first that is usable. A wire is left out of a window when histology says the probe is not in that region, when it is marked bad for the whole recording, or when the clipping check found it at the rail there. These are read anyway, so you can see what was left out and judge the reason yourself.',
      look: 'A clipped wire should show flat tops or sharp steps where it is marked red. A wire that looks clean but was left out deserves a second look at the clipping check.',
      traps: 'The traces are notched and brought down to 250 Hz for display, which rounds off the very flat tops the check looks for in the raw 32 kHz samples; the red marks come from the raw samples, not from this picture.',
    },
    damage: {
      title: 'What was lost',
      plain: 'Everything the Monolith could have measured and did not, read from what the cluster actually did: the wire each region was read on in each window of each cue pair, or none. A region gives nothing in a window when histology says the probe is not in it, when its wires are marked bad, or when every wire it has was clipped there. A cue pair is kept when every region histology allows was read in every window, partly kept when some were not, and lost when no two regions were read anywhere.',
      look: 'Whether the losses are even across rats and days. A rat that lost far more on one day than the other changes that rat’s Precon4 − Precon1 for a reason that is not the brain.',
      traps: 'Clipping is decided per wire and per window, so a region with two wires survives until both clip. A region kept in every window can still be a poor signal; this counts what was measured, not how well.',
    },
    aliasing: {
      title: 'Aliasing',
      plain: 'Sampling a signal folds anything above half the sampling rate back down to a lower frequency, where it is indistinguishable from real activity. Every recording here is read at its own rate and brought down to 1000 Hz (and 250 Hz for Granger) through anti-aliasing filters; this check measures how much of what was above those limits could have landed in 1–55 Hz.',
      look: 'The worst leakage, in dB: anything below about −60 dB is far beneath the signal. And whether the recordings’ own hardware filters were below half their sampling rate, which no software can fix afterwards.',
      traps: 'Mains harmonics are the usual culprit: 60 Hz multiples above the Nyquist limit fold to exact frequencies (240 Hz to 10 Hz at 250 Hz sampling), so a sharp line at one frequency in every rat is the thing to look for.',
      cite: ['Oppenheim & Schafer (2010). Discrete-Time Signal Processing, 3rd ed., ch. 4.'],
    },
  };

  const SAY_KEY = { coherence: 'coherence', icoh: 'icoh', raw_cc: 'raw_cc', env_cc: 'env_cc', env_cc0: 'env_cc0', orth_env: 'orth_env',
                    plv: 'plv', ppc: 'ppc', pli: 'pli', wpli: 'wpli', dwpli: 'dwpli', gc_ab: 'gc_ab', gc_ba: 'gc_ba', gc_net: 'gc_net' };

  /* ---- the measure's own picture, from sweep.explain output ---------- */
  function measurePlot(kind, ex, o) {
    const G = F();
    o = o || {};
    const w = o.w || 280;
    const b = ex.band || {};
    const bandR = [b.low, b.high];
    const css = G.css;
    if (kind === 'coherence' && ex.spectra) return G.spectrum(ex.spectra.f, [{ y: ex.spectra.coh }], { w, band: bandR, range: [0, 1], ylabel: 'coherence' });
    if (kind === 'icoh' && ex.spectra) return G.spectrum(ex.spectra.f, [{ y: ex.spectra.icoh }], { w, band: bandR, range: [-1, 1], zero: true, ylabel: 'imag. coherency' });
    if ((kind === 'raw_cc' || kind === 'env_cc') && ex.lags) {
      return G.lag(ex.lags.ms, kind === 'raw_cc' ? ex.lags.raw : ex.lags.env, { w, peak: kind === 'raw_cc' ? ex.lags.raw_peak : ex.lags.env_peak });
    }
    if ((kind === 'env_cc0' || kind === 'orth_env') && ex.traces) {
      const tr = ex.traces;
      return G.traces(tr.t, [{ y: tr.env_a, y2: kind === 'env_cc0' ? tr.env_b : tr.orth_b, color: css('--up'), color2: css('--down'),
                                short: 'env', label: kind === 'env_cc0' ? 'A and B envelopes' : 'A, and B orthogonalised to A' }],
                      { w, rowH: 70 });
    }
    if (kind === 'plv' && ex.phase) return G.rose(ex.phase.rose, { w: 150, h: 150, angle: ex.phase.mean_angle, length: ex.phase.plv });
    if ((kind === 'ppc' || kind === 'dwpli') && ex.segments) return G.segs(ex.segments.angle, ex.segments.size, { w: 150, h: 150 });
    if ((kind === 'pli' || kind === 'wpli') && ex.phase) return G.signs(ex.phase, { w: 220 });
    if (kind === 'gc' && ex.granger && ex.granger.f) {
      return G.spectrum(ex.granger.f, [{ y: ex.granger.ab, color: css('--up') }, { y: ex.granger.ba, color: css('--down'), dash: '4 3' }],
                        { w, band: bandR, ylabel: 'GC (nats): A→B solid, B→A dashed' });
    }
    if (kind === 'power' && ex.spectra) {
      return G.spectrum(ex.spectra.f, [{ y: ex.spectra.psd_a, color: css('--up') }, { y: ex.spectra.psd_b, color: css('--down'), dash: '4 3' }],
                        { w, band: bandR, ylabel: 'log10 power: A solid, B dashed' });
    }
    if (kind === 'pac' && ex.pac && ex.pac.ab) return G.pacBars(ex.pac.aa.p, { w: 240, mi: ex.pac.aa.mi });
    return null;
  }
  function plotKind(key) { return (T[key] || {}).plot || null; }
  function valueOf(key, ex) {
    if (!ex) return null;
    if (key === 'power') return ex.power ? ex.power[0] : null;
    if (key === 'pac' || /^pac\./.test(key)) return ex.pac && ex.pac.aa ? ex.pac.aa.mi : null;
    if (key === 'arrows') return ex.values ? ex.values.gc_net : null;
    return ex.values ? ex.values[key] : null;
  }

  /* Strong vs none, for a measure: traces, the measure's picture, its number. */
  function measureDemo(key, g, big) {
    const G = F();
    const mkey = key === 'arrows' ? 'gc_net' : /^pac\./.test(key) ? 'pac' : key;
    const scen = g && g.measures && g.measures[mkey];
    if (!scen) return null;
    const S = g.scenarios[scen];
    const box = document.createElement('div');
    box.className = 'qdemo';
    for (const c of ['strong', 'none']) {
      const ex = S[c];
      const col = document.createElement('div');
      col.className = 'qcase ' + c;
      const h = document.createElement('div');
      h.className = 'qcase-h';
      const v = valueOf(mkey, ex);
      h.textContent = (c === 'strong' ? 'Strong effect' : 'No effect') + (v != null ? ' — ' + G.sig(v) : '');
      col.appendChild(h);
      const say = document.createElement('div');
      say.className = 'qcase-say';
      say.textContent = S.say[c];
      col.appendChild(say);
      const tr = ex.traces;
      if (tr && tr.band_a) {
        col.appendChild(G.traces(tr.t, [{ y: tr.band_a, short: 'A', color: G.css('--up') }, { y: tr.band_b, short: 'B', color: G.css('--down') }],
                                 { w: big ? 420 : 280, rowH: big ? 44 : 34, label: 'band-passed traces' }));
      }
      const pl = measurePlot(plotKind(key) || 'coherence', ex, { w: big ? 420 : 280 });
      if (pl) col.appendChild(pl);
      box.appendChild(col);
    }
    return box;
  }

  function statsDemo(name, g, big) {
    const G = F();
    const st = g && g.stats;
    if (!st || !st[name]) return null;
    const box = document.createElement('div');
    box.className = 'qdemo';
    const w = big ? 420 : 280;
    const cap = (txt) => { const d = document.createElement('div'); d.className = 'qcase-h'; d.textContent = txt; return d; };
    const col = (kids) => { const c = document.createElement('div'); c.className = 'qcase'; kids.forEach((k) => k && c.appendChild(k)); return c; };
    const p = (x) => 'change ' + G.sig(x.est) + ', p ' + (x.p == null ? '—' : G.sig(x.p)) + ', ' + x.same + '/' + x.k + ' rats the same way';
    if (name === 'agree') {
      box.appendChild(col([cap('Every rat the same way — ' + p(st.agree.agree)), G.forest(st.agree.agree.rats, st.agree.agree, { w })]));
      box.appendChild(col([cap('Split 5:3 — ' + p(st.agree.split)), G.forest(st.agree.split.rats, st.agree.split, { w })]));
    } else if (name === 'outlier') {
      box.appendChild(col([cap('One rat far from the rest — ' + p(st.outlier.outlier)), G.forest(st.outlier.outlier.rats, st.outlier.outlier, { w })]));
      box.appendChild(col([cap('Every rat the same way — ' + p(st.agree.agree)), G.forest(st.agree.agree.rats, st.agree.agree, { w })]));
    } else if (name === 'minus_fp') {
      box.appendChild(col([cap('Raw — ' + p(st.minus_fp.raw)), G.forest(st.minus_fp.raw.rats, st.minus_fp.raw, { w })]));
      box.appendChild(col([cap('Minus FP — ' + p(st.minus_fp.minus_fp)), G.forest(st.minus_fp.minus_fp.rats, st.minus_fp.minus_fp, { w })]));
    } else if (name === 'null') {
      box.appendChild(col([cap(st.null.passed.length + ' of ' + st.null.tested + ' pass p < .05 with nothing changed'),
        G.miniCircuit(st.null.regions, st.null.pairs, st.null.passed, { w: big ? 280 : 200, h: big ? 280 : 200 })]));
    } else if (name === 'day') {
      box.appendChild(col([cap('Cue pairs, and rest beside them'), G.dots([
        { name: 'cue pairs', values: st.day.cue, mean: st.day.mean, se: st.day.se },
        { name: 'rest epochs', values: st.day.rest, mean: st.day.rest_mean, se: st.day.rest_se, color: G.css('--arrow') }], { w })]));
    }
    const say = document.createElement('p');
    say.className = 'qsay';
    say.textContent = st[name].say;
    box.appendChild(say);
    return box;
  }

  /* ---- one help block: used by the popover and the Guide ------------ */
  function block(key, opts) {
    opts = opts || {};
    const t = T[key];
    const root = document.createElement('div');
    root.className = 'qblock';
    if (!t) { root.textContent = 'No help written for ' + key + '.'; return root; }
    const add = (cls, label, text) => {
      if (!text) return;
      const p = document.createElement('p');
      p.className = cls;
      if (label) { const b = document.createElement('b'); b.textContent = label + ' '; p.appendChild(b); }
      p.appendChild(document.createTextNode(text));
      root.appendChild(p);
    };
    add('qplain', '', t.plain);
    if ((t.steps || []).length) {
      const ol = document.createElement('ol');
      ol.className = 'qsteps';
      for (const x of t.steps) {
        const li = document.createElement('li');
        li.textContent = x;
        ol.appendChild(li);
      }
      root.appendChild(ol);
    }
    add('qexample', 'For example:', t.example);
    add('qlook', 'What to look for:', t.look);
    add('qtraps', 'What fools it:', t.traps);
    if (opts.here) add('qhere', 'This one:', opts.here);
    const fig = document.createElement('div');
    fig.className = 'qfigs';
    root.appendChild(fig);
    guide().then((g) => {
      if (!g) return;
      const d = t.demo ? statsDemo(t.demo, g, opts.big) : (t.plot ? measureDemo(key, g, opts.big) : null);
      if (d) fig.appendChild(d);
    });
    if ((t.cite || []).length) {
      const c = document.createElement('div');
      c.className = 'qcite';
      c.textContent = (t.cite.length > 1 ? 'Papers: ' : 'Paper: ') + t.cite.join(' · ');
      root.appendChild(c);
    }
    if (!opts.noGuide) {
      const a = document.createElement('a');
      a.href = 'monolith-guide.html#' + encodeURIComponent(key);
      a.target = '_blank';
      a.rel = 'noopener';
      a.className = 'qguide';
      a.textContent = 'Read it in the Guide →';
      root.appendChild(a);
    }
    return root;
  }

  /* ---- the popover ---------------------------------------------------- */
  let pop = null, popFor = null;
  function close() {
    if (pop) pop.remove();
    pop = null;
    popFor = null;
  }
  function open(key, anchor, here) {
    if (popFor === anchor && pop) { close(); return; }
    close();
    const t = T[key] || { title: key };
    pop = document.createElement('div');
    pop.className = 'qpop';
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-label', t.title);
    pop.dataset.key = key;
    const head = document.createElement('div');
    head.className = 'qpop-h';
    const h = document.createElement('b');
    h.textContent = t.title;
    const x = document.createElement('button');
    x.type = 'button';
    x.className = 'qpop-x';
    x.textContent = '✕';
    x.setAttribute('aria-label', 'Close');
    x.addEventListener('click', close);
    head.appendChild(h);
    head.appendChild(x);
    pop.appendChild(head);
    pop.appendChild(block(key, { here }));
    document.body.appendChild(pop);
    popFor = anchor;
    place(anchor);
    setTimeout(() => place(anchor), 60);
  }
  function place(anchor) {
    if (!pop || !anchor || !anchor.isConnected) return;
    const r = anchor.getBoundingClientRect();
    const w = Math.min(640, innerWidth - 24);
    pop.style.width = w + 'px';
    let x = r.right + 10;
    if (x + w > innerWidth - 12) x = Math.max(12, r.left - w - 10);
    if (x < 12) x = 12;
    const h = Math.min(pop.scrollHeight, innerHeight - 24);
    let y = r.top - 8;
    if (y + h > innerHeight - 12) y = Math.max(12, innerHeight - h - 12);
    pop.style.left = x + 'px';
    pop.style.top = y + 'px';
    pop.style.maxHeight = (innerHeight - 24) + 'px';
  }
  document.addEventListener('mousedown', (e) => {
    if (pop && !pop.contains(e.target) && !(popFor && popFor.contains(e.target))) close();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && pop) { close(); e.stopImmediatePropagation(); } }, true);

  /* A ? button. `here()` is asked when it opens, for the line about the
     entry on screen. */
  function q(key, here) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'qmark';
    b.textContent = '?';
    b.dataset.help = key;
    const t = T[key] || {};
    b.setAttribute('aria-label', 'What is ' + (t.title || key) + '?');
    b.title = t.plain ? t.plain.split('. ')[0] + '.' : '';
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      e.preventDefault();
      let line = null;
      try { line = here ? here() : null; } catch (err) { line = null; }
      open(key, b, line);
    });
    return b;
  }

  return { T, q, open, close, block, guide, measurePlot, plotKind, valueOf, get openKey() { return pop ? pop.dataset.key : null; } };
})();
