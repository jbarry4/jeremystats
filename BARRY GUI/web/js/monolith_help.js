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
      plain: 'How many stat tests were run (every window × frequency × measure × region pair that at least four rats had on both days), how many came out p < .05, and how many would by chance alone.',
      look: 'Compare p < .05 with the chance count. If they are close, most of what passes is noise; what matters is what stands out consistently.',
      traps: 'Every p here is uncorrected: with hundreds of thousands of tests, thousands pass by chance. The Monolith is for finding things to follow up, not for proving them.',
      cite: ['Benjamini & Hochberg (1995). Controlling the false discovery rate. J R Stat Soc B 57:289–300.'],
      demo: 'null',
    },
    layer: {
      title: 'Raw or Minus FP',
      exampleFirst: true,
      example: 'Rat r3, Cue 1, coherence at 10 Hz. On Precon1 its trials averaged 0.42 and its FP recordings that day 0.38. On Precon4: 0.49 and 0.43. Raw is the change in the trials: 0.49 − 0.42 = +0.07. But FP went up too, by 0.05, so most of that was the whole day moving, not the cues. Minus FP takes each day’s FP off first: (0.49 − 0.43) − (0.42 − 0.38) = 0.06 − 0.04 = +0.02. Only +0.02 belongs to the cues.',
      worked: { day: ['Precon1', 'Precon4'], cue: [0.42, 0.49], rest: [0.38, 0.43] },
      plain: 'Raw is how much the cue windows changed from Precon1 to Precon4. Minus FP is the same change after taking away whatever changed with no cues at all: the same measure, on the same wires, in that day’s FP recordings (FP1 and FP2). If the whole day moved — an electrode settling, a calmer rat — Minus FP removes it, and what is left changed with the cues.',
      steps: [
        'Cue: every trial gives one number for the window; the day’s cue value is their mean. A window with clipped wires is left out, not filled in.',
        'FP: the same measure on 10 s epochs of that day’s FP1 and FP2, as many as the day had trials of one pair; the day’s FP value is their mean.',
        'Each day: trials − FP. Each rat: that on Precon4 minus that on Precon1.',
        'Over rats: the rats’ changes are pooled and tested as everything else on the page (at least four rats).',
      ],
      note: 'The price: FP has noise of its own, and taking it off adds that noise, so Minus FP is a little noisier than Raw.',
      look: 'An edge in raw that survives minus FP changed with the cues, relative to FP. One that vanishes changed in FP by about as much — the day changed (an electrode settling, the rat calmer, the recording quieter), not the response to the cues. One that appears only in minus FP is a cue change raw could not see, because FP moved the other way.',
      traps: 'Minus FP is noisier — both days carry FP’s error too — so a real but small cue change can fall below the line there. It assumes the day moves cue and FP by the same amount (additively); a change that scales everything is not removed exactly. FP1 and FP2 are separate recordings from the cue session, minutes apart, so it takes away what changed over the day, not what differs between FP and cues within one session. The transition windows are shorter than the ten-second FP epochs, and measures biased by window length (coherence, PLV) differ by that bias within a day — but the bias is the same on both days, so it cancels from the change.',
      demo: 'minus_fp',
    },
    windows: {
      title: 'The windows: 4 states, the whole pair, 3 transitions, and the contrast',
      plain: 'Every trial is measured in each window. The 4 states are 10 s each: pre-baseline (before cue 1), cue 1, cue 2, post-baseline (after cue 2). The whole pair is cue 1 onset to cue 2 offset, 20 s — usable on a wire only where both cues were clean. The 3 transitions straddle the moments things change: cue 1 starting (onset), cue 1 giving way to cue 2 (switch), cue 2 ending (offset). Cue 2 − Cue 1 is not a window but the agreed comparison: within each trial, the second cue against the first.',
      look: 'A state change says how the brain sat during a part of the pair; a transition change says how it moved at the boundary.',
      traps: 'Transition windows are shorter (6 s for slow bands, 3 s for fast), so their numbers are noisier than state ones.',
    },
    window: {
      title: 'Which window',
      plain: 'Pre-baseline is the 10 s before cue 1; cue 1 and cue 2 are the cues (about 10 s each); post-baseline is the 10 s after cue 2 ends. Onset, switch and offset are −3/+3 s around each boundary for bands up to 12 Hz (a 1 Hz cycle needs that long), and −1/+2 s for faster ones.',
      look: 'Compare the cue windows with pre-baseline in the same rat-day to see what the cue itself did.',
      traps: 'A window that touched clipping drops the clipped wire for that trial: shorter windows lose more trials.',
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
      look: 'A named-band result plus agreement in the 1 Hz bands inside it is a stronger result than either alone.',
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
      plain: 'A is the region named first on the line and B the second: on “R ACC – L OFC”, A is R ACC. Granger A→B asks whether knowing A’s recent past helps predict what B does next, beyond what B’s own past already predicts, at these frequencies. 0: A’s past adds nothing. It is spectral Granger causality in nats, worked out from the spectrum without fitting a model (Wilson’s factorisation).',
      look: 'A rise from Precon1 to Precon4: A’s activity in this band came to carry more of what B does next. Read it beside B→A (the next measure): the two are measured separately.',
      traps: 'A third region driving both, or one region simply being cleaner (better signal-to-noise), can look like drive. It is never negative, so it is biased upward.',
      cite: ['Dhamala, Rangarajan & Ding (2008). Analyzing information flow in brain networks with nonparametric Granger causality. NeuroImage 41:354–362.', 'Geweke (1982). J Am Stat Assoc 77:304–313.'],
      plot: 'gc',
    },
    gc_ba: {
      title: 'Granger B→A',
      plain: 'The same, the other way round: whether B’s past helps predict A. A→B and B→A can both be large at once: the two regions predict each other (a loop, or something feeding both).',
      look: 'Read the two side by side. A→B up, B→A flat: A came to lead B. Both up: they exchange more, either way. One up and the other down: the lead moved from one to the other.',
      traps: 'As for A→B.',
      cite: ['Dhamala, Rangarajan & Ding (2008). NeuroImage 41:354–362.'],
      plot: 'gc',
    },
    gc_net: {
      title: 'Granger net',
      plain: 'A→B minus B→A: which of the two leads, and by how much. Positive: A predicts B more than B predicts A. The Monolith shows its change, Precon4 − Precon1. A positive change means the balance tipped towards A leading: A’s lead grew, or B’s lead shrank. On the circuit it is an arrow pointing the way the balance tipped.',
      look: 'Net direction is more robust than either direction alone: biases both share cancel. To tell “A came to lead” from “B stopped leading”, open Granger A→B and B→A for the same pair.',
      traps: 'A difference in signal quality between the two regions can still tip it.',
      cite: ['Dhamala, Rangarajan & Ding (2008). NeuroImage 41:354–362.'],
      plot: 'gc',
    },
    power: {
      title: 'Node power',
      plain: 'Each node is coloured by its region’s own change in power at this frequency: how much stronger or weaker that region’s signal got in this band, from Precon1 to Precon4, on its own, whatever the other regions did. Red: louder on Precon4. Blue: quieter. The deeper the colour, the bigger the change, against the biggest in view. A ring: the change passes the slider.',
      powsteps: [
        'One trial, one region: the region’s wire in the window (10 s for a state window, −3/+3 s or −1/+2 s around a boundary, 20 s for the whole pair), with the mains hum notched out.',
        'Welch’s method: the window cut into 1-second pieces (1.5 or 2 s for the narrowest low bands), each overlapping the next by half and tapered at its ends; each piece’s frequencies found (a Fourier transform) and their squared sizes averaged over the pieces. That is the power at each frequency.',
        'The band: that power averaged over the band’s frequencies (9 Hz, say: 7.65–10.35 Hz), then its log10, so that a change reads the same for a quiet region as for a loud one.',
        'Each rat-day: the mean over its trials (in Minus FP, less the same from its FP epochs). Each rat: Precon4 − Precon1. Then pooled over rats and tested, as every edge is.',
        'Reading the number: it is a change in log10 power. +0.30 is twice the power (10^0.30 = 2), +0.10 about a quarter more, −0.30 half. The node’s hover gives the factor (×).',
      ],
      look: 'Coupling that rises where both regions also got louder may be about loudness, not coordination.',
      traps: 'Power differences between regions change coherence-type measures without any change in coupling.',
      cite: ['Welch (1967). The use of fast Fourier transform for the estimation of power spectra. IEEE Trans Audio Electroacoust 15:70–73.'],
      plot: 'power',
    },
    sig: {
      title: 'The significance slider',
      plain: 'Which edges are drawn: every stat test run, or only those whose p is below .05, .01, .001 or .0001. Stricter to the right. p comes from pooling the rats’ changes (DerSimonian–Laird) and testing the pool with Hartung–Knapp t on k − 1 degrees of freedom.',
      look: 'Edges that stay at the strict end, with every rat the same way, are the strongest results.',
      traps: 'Uncorrected: even with nothing changing, about 5% pass at .05, 1% at .01 (see the null circuit below).',
      cite: ['DerSimonian & Laird (1986). Control Clin Trials 7:177–188.', 'Hartung & Knapp (2001). Stat Med 20:3875–3889.'],
      demo: 'null',
    },
    arrows: {
      title: 'Granger arrows',
      plain: 'An arrow on an edge is Granger net’s change for that region pair, at this frequency and window, wherever it passes the slider. It points from the region whose lead grew towards the region it leads: an arrow R ACC → L OFC means R ACC→L OFC minus L OFC→R ACC rose from Precon1 to Precon4. Wider: a bigger change. Dashed: drawn over another measure (the toggle); solid: Granger net is the measure in view.',
      look: 'An edge with an arrow over coherence: the two regions came to move together, and the balance of who leads tipped the arrow’s way. The arrow does not say which half moved: choose Granger A→B and then B→A in Measure to see whether the leader’s drive grew or the other’s faded.',
      traps: 'Granger is prediction, not a wire between them: an input that reaches one region before the other, or one region’s cleaner signal, makes an arrow too. Its p is uncorrected, as everywhere on the page.',
      plot: 'gc',
    },
    circuit: {
      title: 'The circuit',
      plain: 'One node per region, one edge per region pair that passes the slider. Red edge: the measure rose from Precon1 to Precon4; blue: it fell. Thicker: a bigger change. Grey rings: regions no rat had usable (histology or wires).',
      look: 'Click an edge to lift it out and open it into its rats, days and trials.',
      traps: 'A thick edge is a big change, not necessarily a reliable one: check how many rats agree.',
    },
    rank: {
      title: 'Rank overall, or within each window',
      plain: 'Overall: every stat test of every window competes in one list, ranked by how many rats changed the same way, then by p. Within each window: the best three of each of the seven windows, ranked the same way, each window on its own.',
      look: 'Overall is what is strongest anywhere. Within each window stops one window with many strong stat tests (onset, often: the cue starting moves everything) from filling the whole list, so a smaller change at the switch or offset is still seen.',
      traps: 'The windows are not equally long, so their p are not equally easy to reach: a 3 s transition is noisier than a 10 s state. Comparing ranks across windows says which is stronger within its own window, not which is the bigger effect.',
    },
    trail: {
      title: 'Where this value comes from',
      plain: 'The path from the whole Monolith down to one trial’s signals: the pooled change of a region pair, then each rat’s change, then one rat’s two sessions, then one session’s trials, then one trial. Each step says what its numbers are.',
      look: 'Click any earlier step to go back to it. Pooled and rat levels are changes (Precon4 − Precon1); session and trial levels are values, not changes.',
      traps: 'Raw and minus FP give different numbers at every level: minus FP takes each session’s FP1/FP2 off first. Raw or Minus FP is named at each step.',
    },
    points: {
      title: 'Top results',
      plain: 'Single stat tests with p < .05, ranked by how many rats changed the same way, then by p; at most three per region pair, and a stat test within 2 Hz of one already listed (same window and measure) is the same finding and is listed under it.',
      look: 'Click one to snap the whole view to it. 8/8 rats is the strongest agreement there can be.',
      traps: 'Uncorrected p: a list this long always has chance stat tests. A broadband flag means it passes at most frequencies, which oscillatory coupling rarely does.',
      demo: 'agree',
    },
    broadband: {
      title: 'Broadband',
      plain: 'This region pair passes p < .05 at most of the 1 Hz bands in this window and measure.',
      look: 'Real oscillatory coupling usually lives in one or two bands. A change at nearly every frequency more often means something changed in the recording: a different wire or reference, a loose connection, movement.',
      traps: 'It is a flag, not a verdict: open the trials and look at the traces.',
    },
    coverage: {
      title: 'Coverage',
      plain: 'How many of each rat’s trials (and FP epochs) gave a value for this stat test. A dash is a trial that did not, and its hover says why: a region with no usable wire in that window (every wire clipped or bad), or the measure could not be formed.',
      look: 'A rat whose day rests on two or three trials counts for less in the pool, and should.',
      traps: 'Slow transition windows (6 s) lose more trials to clipping than state windows.',
    },
    spectrum: {
      title: 'Across frequencies',
      plain: 'Bars: how many region pairs pass the slider at each frequency, for this window and measure. Line: the selected pair at every frequency, a filled dot where it passes.',
      look: 'A run of neighbouring frequencies is a band; one lone frequency is more likely chance.',
      traps: 'In transition view, bands left of the dashed line use −3/+3 s windows and those right of it −1/+2 s.',
    },
    trajectory: {
      title: 'Across the four sessions',
      plain: 'The selected line’s value in every Precon session — 1, 2, 3 and 4 — measured exactly as the Monolith measures Precon1 and Precon4. Left: every trial in order, a panel a session, each rat its own colour and the mean over rats in black. Below: each rat’s session value (the mean over its trials, less its FP1/FP2 in minus FP), and the mean ± SE over rats.',
      look: 'Whether a change from Precon1 to Precon4 builds session by session, appears all at once, or comes and goes; and whether it is in every rat or a few. Within a session: whether it drifts from the first trial to the last.',
      traps: 'Nothing here is tested, on purpose (the lab’s choice): the Monolith’s p is for Precon4 − Precon1 alone, and Precon2 and Precon3 never enter it. Four sessions of eight rats invite stories; read the shape, not single numbers. Trials are lined up by their order in the session, not by which pair (AB or CD) they were.',
    },
    progress: {
      title: 'Monolith Progress',
      plain: 'The button on the Monolith’s circuit. The Monolith compares Precon4 with Precon1; Progress shows every Precon session — 1, 2, 3 and 4 — measured exactly as those two are: for every edge at once as circuits, and for any line you choose as a panel with the sessions along the bottom. Each session can be read as its own value (the mean over rats of each rat’s session value) or as its change from Precon1 (each rat’s session less its own Precon1, then the mean over rats), or both.',
      look: 'Whether a change builds session by session, arrives at once, or comes and goes; whether every rat carries it or a few; and whether lines you suspect belong together move together.',
      traps: 'Nothing here is tested, on purpose (the lab’s choice): the only p is the Monolith’s own, Precon4 − Precon1, uncorrected. Four sessions of eight rats invite stories; read the shape, not single numbers. Precon2 and Precon3 come from one VACC run (Drift → Monolith), and until it has run they are marked “not run yet”.',
    },
    'progress.circuits': {
      title: 'Every edge, session by session',
      plain: 'One circuit a session, for the window, frequency, measure, Raw or Minus FP, and cue pairs chosen above the circuits. In “each session’s value”, a thicker, darker line is a higher value, on one scale for all four sessions, and a larger node has more power. In “change from Precon1”, red is higher than on Precon1 and blue lower, the width how much, again on one scale. “Both” shows the two readings together; “one at a time” shows one session and turns it into the next, and Play runs Precon1 to Precon4.',
      look: 'Lines that thicken steadily from one session to the next. Switch between the two readings: a line that is strong in every session but changes little is a different finding from one that is weak but grows.',
      traps: 'One scale for every session means a session with one very strong line can make the rest look thin. The value circuits show where coupling is high, which is mostly anatomy and wiring; the change circuits are the ones that bear on learning. “Only the lines whose Precon4 − Precon1 passes” uses the Monolith’s slider and its uncorrected p.',
    },
    'progress.series': {
      title: 'Following a line across the sessions',
      plain: 'Each panel is one line: an edge (two regions, a measure, a frequency, a window, Raw or Minus FP, the cue pairs) or one region’s power. Along the bottom, the four Precon sessions; up the side, the line’s own units, so panels with different measures are never forced onto one scale. Black: the mean over rats ± its standard error; thin coloured lines: each rat. Drag an edge or a node from a circuit into the box, click one, or build one with the form. Click a session’s point for that session’s rats, a rat for its trials, and a trial for its traces.',
      look: 'Several tests stacked: whether coherence and envelope correlation of the same pair rise together, or whether the change shows in one window and not the next. The rats: whether the mean is carried by most of them or by one.',
      traps: 'The mean ± SE is descriptive. A session where a rat is missing moves the mean for that reason alone: hover a point for how many rats it rests on. CSV and SVG take every panel away as numbers and as a picture.',
    },
    physical: {
      title: 'Physical cue against balanced cue',
      plain: 'The Monolith names cues A, B, C and D, from the lab’s identity sheet, and the sheet spreads the four sounds over A/B/C/D so that no sound is the same letter in every rat. Section 6 asks whether the sounds themselves left a mark anyway. It can, because of how the sheet is laid out: every rat opens both its pairs with the same kind of sound (J3, J6, J7 and J8 with Click or Noise; J4, J9, J10 and J11 with a tone), and every ordered pair of sounds is heard by exactly two rats. So each rat’s own Precon4 − Precon1 change can be sorted by sound instead of by A/B/C/D and tested the same way: tone-first rats against noise-first rats; within the noise-first rats, the pair Click opens against the pair Noise opens; within the tone-first rats, the high tone’s pair against the low tone’s; and Cue 2 − Cue 1, which is tone − noise for half the rats and noise − tone for the other half, turned round to read tone − noise for all eight.',
      look: 'At the top, whether the comparisons by sound pass p < .05 any more often than chance and than a shuffle of the same rats. Below, whether each top result of the Monolith goes the same way in the tone-first and the noise-first rats, and is the same in both within half its own size.',
      traps: 'An absence of evidence is not evidence of absence: with four rats a group, only a large effect of the sound could be seen. That is why the top results also carry an equivalence test, which can say “the same within ±½” only when the two groups’ intervals are narrow enough. Every p is uncorrected, as everywhere on the page. Tone-first against noise-first is also rat against rat: any way the two groups of four differ besides the sound (cage, surgery date) falls into it too.',
    },
    'physical.how': {
      title: 'How sorting by sound works, in pictures',
      plain: 'Every rat heard the same four sounds, but the identity sheet puts them at a different A/B/C/D for each rat. The first picture is that sheet: a row per rat, its AB pair and its CD pair, each sound coloured by kind. Read down the first sound of each pair (A and C): for four rats it is Click or Noise (blue), for the other four a tone (red). That splits the rats in two by sound, while the Monolith pools all eight by A/B/C/D.',
      steps: [
        'If the sound itself drove a change, the two groups would disagree: the change would sit in one group and not the other (second picture, made up). The Monolith, pooling all eight by A/B/C/D, would then report a change that is really about the sound.',
        'If the sound did not matter, the two groups agree, and each looks like the Monolith’s pooled answer (third picture, made up).',
        'The tab measures which of the two the real data look like, for every stat test, and compares that with every other way of splitting the same rats.',
      ],
      draw: 'physical',
    },
    'physical.verdict': {
      title: 'Across the whole Monolith, by A/B/C/D and by sound',
      plain: 'One row a comparison: how many stat tests were tested, how many passed p < .05, how many chance alone would give (5%), and that as a ratio. The rows by A/B/C/D are the Monolith as it stands; the rows by sound are the same rats’ changes sorted by sound. The bars draw the ratio: the solid line is chance, and the dashed line is the rate made-up data with no change at all gave. Then the yardstick that fits these data: every other way of sorting the same rats — all 35 ways of splitting eight rats into two fours, all 128 sign-flip shuffles of the eight rats’ Cue 2 − Cue 1, all 8 of four rats’ AB − CD — and where the sound’s own sorting ranks among them.',
      look: 'Comparisons by sound that rank among the ordinary sortings (“at chance”), while the Monolith by A/B/C/D passes more than chance. The histograms show the whole spread of the shuffles, with the sound’s sorting marked on it.',
      traps: 'The stat tests are not independent — neighbouring frequencies, measures and windows move together — so a count can stray well away from 5% by luck, and the shuffles are the fair test, not the 5%. With only 8 shuffles of four rats, a rank among them says little on its own.',
    },
    narrow: {
      title: 'Narrowing down',
      plain: 'Every p on the Monolith page is uncorrected, by the lab’s choice: one test per stat test, and hundreds of thousands of stat tests, so thousands pass p < .05 by chance alone. This tab says how those p were made, whether the Monolith holds more than chance at all, what each correction for the number of tests would keep, and tests that assume less than the t-test: exact shuffles of the eight rats, the sign test, runs of neighbouring frequencies and replication in both pairs.',
      look: 'Whether the whole Monolith beats its shuffles; then which top results survive a correction, a frequency run, and both pairs. Those are the ones to report as findings; the rest are worth following up.',
      traps: 'A correction answers “how sure”, not “how big”. With eight rats, exact tests cannot go below 1 in 128, so corrections over the whole Monolith keep almost nothing exact: narrow the question first.',
    },
    'narrow.how': {
      title: 'How every p was made',
      plain: 'Each rat’s own change, Precon4 − Precon1, is pooled over rats by DerSimonian–Laird (each rat weighted by 1 ÷ (its own uncertainty + the spread between rats)), and tested by Hartung–Knapp: t = the pooled change ÷ its standard error, on rats − 1 degrees of freedom, two-sided. The card works one through with the first top result’s own numbers.',
      look: 'How many rats a stat test rests on (k): with fewer, the same change gives a larger p.',
      traps: 'The t-test assumes each rat’s change is roughly normal, which eight rats cannot show; its smallest p come from the tails of the t distribution, not from the data.',
    },
    'narrow.global': {
      title: 'Is there anything at all?',
      plain: 'If nothing changed, each rat’s change could as well have had the other sign. Flipping the eight rats’ signs every possible way (128) and pooling each exactly as the Monolith does gives the counts of p < .05 that chance alone gives, with every correlation between stat tests kept. Where the real count falls among them is the honest test of the Monolith as a whole.',
      look: 'A real count beyond nearly every shuffle: the Monolith holds more than chance, even if no single stat test can be trusted alone.',
      traps: 'With 128 shuffles the smallest possible rank is 1 of 128 (p = .0078). The test says “something”, not where.',
    },
    'narrow.correct': {
      title: 'What correcting does',
      plain: 'Bonferroni: p must be below .05 ÷ the number of tests; the chance of even one false finding stays under 5%. Holm: the same promise, stepping up from the smallest p, so a little less strict. Benjamini–Hochberg: keep the largest set in which at most 5% are expected to be false (the false discovery rate). Benjamini–Yekutieli: the same, safe under any correlation, so stricter. Permutation max-t (Westfall–Young): a stat test survives if its |t| beats the largest |t| anywhere in the Monolith in 95% of the shuffles, which uses the data’s own correlations. Frequency clusters (Maris & Oostenveld): runs of neighbouring 1 Hz bands passing together, weighed by their summed |t| against the heaviest run anywhere in each shuffle. The exact permutation and sign tests are not corrections: they test each stat test without assuming normality.',
      look: 'What survives BH (worth following) and what survives max-t or a frequency run (worth claiming).',
      traps: 'Bonferroni and Holm treat every test as independent, which they are not, so they are stricter than they need be; max-t and clusters are not. A correction cannot rescue a question asked after seeing the data.',
      cite: ['Benjamini & Hochberg (1995). J R Stat Soc B 57:289–300.', 'Benjamini & Yekutieli (2001). Ann Stat 29:1165–1188.', 'Westfall & Young (1993). Resampling-based multiple testing. Wiley.', 'Maris & Oostenveld (2007). J Neurosci Methods 164:177–190.'],
    },
    'narrow.families': {
      title: 'Ways to narrow it down',
      plain: 'Three ways to ask less of chance. Ask fewer questions: a smaller family of tests, chosen before looking, lowers every correction’s bar. Ask more of each finding: it should hold at neighbouring frequencies, in both of a rat’s pairs (separate trials), and in Raw and Minus FP. Read runs of frequencies rather than single bands.',
      look: 'Top results that pass each step of the funnel; the replication count against its shuffles.',
      traps: 'A family chosen after seeing the results is not a smaller family. The two pairs share their rats, so replication across them guards against chance in the trials, not in the choice of rats.',
    },
    'narrow.leads': {
      title: 'Every test, on each top result',
      plain: 'For each top result: its t-test p (the page’s), the exact permutation p (its 128 shuffles), the exact sign test (how many rats went that way), Benjamini–Hochberg q, Holm p, the permutation max-t p, the run of frequencies it sits in and that run’s p, its p in AB and in CD, and in the other of Raw and Minus FP. “Survives” lists what it passes.',
      look: 'Top results that survive several different tests: they do not hang on one test’s assumptions.',
      traps: 'An exact p of .0078 is the strongest eight rats can give; it is not weak, and not corrected.',
    },
    'narrow.circuit': {
      title: 'What survives, as a circuit',
      plain: 'Any window, frequency, measure, Raw or Minus FP: the region pairs that survive the method chosen, drawn as on the Monolith (red up, blue down, thicker bigger). The count under it says how many passed uncorrected.',
      look: 'How much of the uncorrected circuit each method keeps.',
      traps: 'Frequency runs keep a band because its neighbours passed with it; read the run, not the band.',
    },
    'physical.sound': {
      title: 'Each sound on its own',
      plain: 'The most direct test of the sounds. For every rat and each of the four sounds, the Precon4 − Precon1 change of the measure in the cue window while that sound played. The identity sheet puts each sound at a different one of A/B/C/D in different rats (J3’s Noise is its C, so its CD pair’s Cue 1; J4’s Noise is its B, so its AB pair’s Cue 2), so the same sound is gathered from whichever window it was in. Every rat heard all four, so two sounds are compared within each rat: Noise’s change less Click’s, rat by rat, pooled over all eight. And all four at once: a repeated-measures ANOVA asks whether the four changes differ more than the rats’ own scatter.',
      look: 'Pairs of sounds, and the four together, at chance: the rats’ changes did not depend on which sound was playing. Each sound’s own change (the first four rows) is the Monolith’s kind of result, kept for reference.',
      traps: 'Uncorrected. Two sounds in the same pair (A and B) come from the same trials, and that covariance is not taken off, so those tests are a little conservative. The cue windows only: nothing else holds one sound.',
    },
    'physical.leads': {
      title: 'The top results, in each group of four',
      plain: 'The Monolith’s 50 top results (or Cue 2 − Cue 1’s), each with its change pooled over the tone-first rats and over the noise-first rats, as the Monolith pools all eight. Same way in both: both groups changed the way all eight did. Difference: the tone-first change less the noise-first (Welch’s t, uncorrected). Equivalent within ±½: the 90% interval of that difference lies inside ± half the top result’s own change (two one-sided tests at α = .05) — the two groups are the same within that margin.',
      look: 'Top results that go the same way in both groups and are equivalent within ±½: they are about the cue’s place in the pair, not about the sound. A top result carried by one group alone is worth a second look before it is read as learning.',
      traps: '“Not equivalent” does not mean “different”: with four rats a group the interval is often too wide to say either, so beside each verdict is the narrowest margin the top result is equivalent within (the far end of its interval, as a multiple of its own change). The top results were chosen for most rats going the same way, so “same way in both” is close to certain when all eight agree; it rules out only a top result carried by one group. A top result that some rat lacks cannot be split four against four: it is described, not tested.',
    },
    'physical.circuit': {
      title: 'Any comparison as a circuit',
      plain: 'Pick one of the comparisons by sound (or AB against CD, by A/B/C/D) and any window, frequency, measure, and Raw or Minus FP: every region pair, drawn where its difference passes the slider. Red: higher in the first named (the tone-first rats; the Click-first or High-first pair; tone in tone − noise), blue: lower.',
      look: 'An empty or scattered circuit at p < .05, with about as many lines as chance gives (the count under it), is what “no effect of the sound” looks like.',
      traps: 'Uncorrected: at p < .05 about one region pair in twenty passes by chance alone, in every circuit.',
    },
    events: {
      title: 'Events first: hippocampal P300-like events',
      plain: 'Large positive deflections in the dorsal hippocampus, found wherever they fall in the cue session rather than in fixed windows. The wire is band-passed (0.5–15 Hz by default) and put on a robust z scale over the session (median, and 1.4826 × the median absolute deviation, away from the rail); an event is a positive peak at or above the threshold (z 4), 150–500 ms wide at half its height, at least 500 ms after the last. Above the ceiling (z 15), or within 250 ms of the rail, it is an artifact and dropped. Each event is then placed against the trials, and every other region’s wire is averaged around the events and around twice as many random times in the same session.',
      look: 'A rise in the histogram right after a cue, in most rats, that is bigger on Precon4: the events came to follow that cue. A region whose event-locked average beats random times in most rats, while others do not, moved with the hippocampus specifically.',
      traps: 'Something every wire shares — the reference, movement, chewing, a cable knock — makes events that show up in every region at once; the page warns when that is the pattern, and the example traces show it. A 1 Hz low edge takes about 40% off a 300 ms deflection and halves its width (measured), which is why the default is 0.5 Hz. Nothing here is tested across rats: the counts are descriptive.',
      cite: ['Polich (2007). Updating P300: an integrative theory of P3a and P3b. Clin Neurophysiol 118:2128–2148.', 'Halgren et al. (1980). Endogenous potentials generated in the human hippocampal formation and amygdala by infrequent events. Science 210:803–805.'],
    },
    'pac.self': {
      title: 'Phase–amplitude coupling within a region',
      plain: 'The conventional measure: does a slow rhythm’s phase (2–12 Hz) set how loud a faster one (15–50 Hz) is, both read from the same region’s wire? Tort’s modulation index (MI): how far the amplitude across 18 phase bins is from flat. Each session’s comodulogram is the mean over rats of each rat’s mean over its trials; the change is pooled over rats as everything else on the page.',
      look: 'A patch of neighbouring cells that is already there on Precon1 and grows on Precon4, in most rats. Compare the region with the others at the same cell (the rows below the comodulograms), and open a typical trial of each session to see the phase-binned amplitude itself.',
      traps: 'Sharp, non-sinusoidal waves and evoked responses produce PAC with no real coupling: look at the trial’s traces. MI grows with noise in short windows, so the 6 s transitions sit higher than the 10 s states; compare like with like. Empty cells cannot carry their sidebands and are not measured.',
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
      plain: 'The rat opened into its two days: one dot per trial, the day’s mean and standard error. Minus FP shows the FP epochs beside them.',
      look: 'A clear shift between the days relative to the spread within each.',
      traps: 'A day with few usable trials has a wide error and little weight.',
      demo: 'day',
    },
    'ghost.units': {
      title: 'Every trial',
      plain: 'The day opened into its trials (and FP epochs, dashed). Each is one window of real recording. Click one to see its traces and how each number was made.',
      look: 'Whether the day’s value comes from all its trials or a few.',
      traps: 'A dash: not measured, and the hover says why.',
    },
    leaf: {
      title: 'One trial, down to its traces',
      plain: 'The recording itself, read from the cluster’s copy: the whole trial with its windows marked and the analysed window highlighted; that window raw, band-passed, as envelopes and as phase difference; and every measure’s own picture of it.',
      look: 'The number at the top of each picture is the analysis’s own, recomputed here; “matches” says it equals the stored value.',
      traps: 'One trial is one noisy sample: the pooled edge is what counts.',
    },
    averaged: {
      title: 'When we averaged',
      plain: 'One line of the circuit, followed from the recording up, with its own numbers. A wire’s trace is cleaned (mains out, brought down to 1000 Hz), cut to one window, filtered to one band, and measured: one number per trial. That is repeated for every trial of a day and averaged — the first averaging — giving one number per day (minus FP: less that day’s FP). Precon4 − Precon1 gives one change per rat. Those are averaged over rats — the second averaging, weighted by how sure each rat is — giving one change and one p, and the line is drawn if p passes the slider.',
      look: 'Where the number comes from: a pooled change carried by every rat, or by one; a day’s mean carried by every trial, or by a few.',
      traps: 'The traces shown are one trial of one rat on one day: a picture of how the number is made, not of the result. The result is step 7.',
    },
    split: {
      title: 'Cue pairs: AB and CD, pooled or apart',
      plain: 'Every rat hears two pairs on every Precon day: A → B and C → D. Which physical sound is which of A/B/C/D is counterbalanced across rats (Click is A in J3 and J8, B in J9 and J11, C in J6 and J7, D in J4 and J10), and A/B/C/D come from the lab’s identity sheet, RAT Identity for multisite 2026 — nothing is read from the conditioning sessions. Pooled, AB and CD together; or each pair on its own, every rat’s Precon4 − Precon1 over that pair’s trials only, then pooled over rats exactly as the whole is.',
      look: 'A change in both AB and CD is about the cue pairs in general; one in only one of them is about that pair. During Precon a rat has no reason to treat its two pairs differently, so a real difference would be a surprise worth checking.',
      traps: 'One pair has half the trials, so its sessions are noisier and fewer stat tests pass. Because A/B/C/D average the sounds out, a result here is about A/B/C/D, not sounds: the Physical cue sanity check under a lifted edge shows whether one sound carries it.',
    },
    contrast: {
      title: 'Cue 2 − Cue 1: the second cue against the first',
      plain: 'The agreed comparison, with a tab of its own. Its three circuits, left to right: Cue 2 − Cue 1 within Precon1, within Precon4 (both descriptive: the mean over rats of each rat’s mean over its trials), and the change from one to the other, which is the one tested. Precon2 and Precon3 sit underneath, between them. Within each trial, the measure in the Cue 2 window minus the same measure in its own Cue 1 window — B − A in AB, D − C in CD. Each session’s value is the mean of those differences over its trials; each rat’s change is Precon4 − Precon1 of it; and the changes are pooled over rats as everywhere else (DerSimonian–Laird, Hartung–Knapp, at least four rats). Pooled is A + C as the first cue against B + D as the second; split, AB or CD alone.',
      look: 'A rise means the second cue came to differ from the first more by Precon4 than on Precon1 — the pair being taken in as two different things, or the second cue being anticipated, in that measure.',
      traps: 'Raw only: the FP that Minus FP takes away is the same for both cue windows, so it cancels exactly — Minus FP shows the same numbers here. It is a difference of two windows of the same trial, so anything that changes both alike (an electrode settling) cancels too, which is the point. Its p, like every p here, is uncorrected.',
    },
    physcheck: {
      title: 'Physical cue sanity check',
      plain: 'The comparisons are made by A/B/C/D, which the counterbalancing makes blind to the sounds. This turns it round, for the edge you lifted: each rat’s change in its AB and in its CD, labelled with the sound heard in this window (Cue 1: A or C; Cue 2: B or D), then the same changes grouped by A/B/C/D and by sound.',
      look: 'If the spread between sounds is much larger than between A, B, C and D, the change follows a sound (say, the Click wherever it sat) rather than its place in the pair — read it as a sound effect, or a recording quirk, before reading it as learning.',
      traps: 'Each sound sits in only two rats per letter (A, B, C or D), so a sound’s mean rests on about four values: it is a sanity check, not a test. In windows with no cue sound (pre- and post-baseline) only A/B/C/D can be compared.',
    },
    range: {
      title: 'A frequency range',
      plain: 'Pull the frequency slider’s two knobs apart and the circuit is drawn over every 1 Hz band between them. A line appears where the pair passes the significance slider at any, most (more than half), or every one of those bands; its colour and width are the median change over the range. Clicking it opens the band where it is strongest.',
      look: 'A change that holds across most of a range is a rhythm changing; one that passes at a single band of a wide range is more likely chance.',
      traps: '“Any” band in a range is a lenient rule: with ten bands, a pair passes it far more often than at one band by chance alone. “Most” or “every” is the honest reading of a range.',
    },
    filter: {
      title: 'Filtering the top results',
      plain: 'Narrows the list to what you are interested in: one measure or a family of them, one region or one pair, a frequency range (with or without the named bands inside it), state windows or transitions or one window, which way the change went, and whether broadband stat tests are in. The list is ranked again from every stat test, by the same rule as the full list: p < .05, most rats the same way, then p, at most three a region pair.',
      look: 'A result that keeps coming back however you slice it, and the count of stat tests that pass with the filter on.',
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
      plain: 'Everything the Monolith could have measured and did not, read from what the cluster actually did: the wire each region was read on in each window of each trial, or none. A region gives nothing in a window when histology says the probe is not in it, when its wires are marked bad, or when every wire it has was clipped there. A trial is kept when every region histology allows was read in every window, partly kept when some were not, and lost when no two regions were read anywhere.',
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

  /* Section 6 in pictures: the identity sheet, a rat a row, each sound
     coloured by kind (from the Monolith's own summary, when there is one),
     and two made-up outcomes on one scale -- the sound mattering, and not. */
  function physDemo(big) {
    const G = F();
    const box = document.createElement('div');
    box.className = 'qdemo';
    const cap = (txt) => { const d = document.createElement('div'); d.className = 'qcase-h'; d.textContent = txt; return d; };
    const col = (kids) => { const c = document.createElement('div'); c.className = 'qcase'; kids.forEach((k) => k && c.appendChild(k)); return c; };
    const I = (window.MONO && window.MONO.data && window.MONO.data.S && window.MONO.data.S.identity) || null;
    const seats = I && I.seats;
    const noisy = (x) => x === 'Click' || x === 'Noise';
    if (seats && Object.keys(seats).length) {
      const rats = Object.keys(seats).map(Number).sort((a, b) => a - b);
      const kind = (r) => (noisy(seats[r].A) && noisy(seats[r].C) ? 'noise' : !noisy(seats[r].A) && !noisy(seats[r].C) ? 'tone' : null);
      const order = rats.filter((r) => kind(r) === 'noise').concat(rats.filter((r) => kind(r) === 'tone'), rats.filter((r) => !kind(r)));
      const VW = 350, rh = 20, top = 26, gap = 8;
      const VH = top + order.length * rh + gap + 6;
      const s = G.sv('svg', { viewBox: '0 0 ' + VW + ' ' + VH, width: '100%', style: 'max-width:' + (big ? 460 : 420) + 'px', class: 'mfig physseatfig', role: 'img',
                              'aria-label': 'The identity sheet: each rat’s sounds at A, B, C and D' });
      const blue = G.css('--down'), red = G.css('--up');
      s.appendChild(G.sv('text', { x: 4, y: 14, 'font-size': 10, fill: G.css('--ink-3') }, 'Rat'));
      s.appendChild(G.sv('text', { x: 93, y: 14, 'text-anchor': 'middle', 'font-size': 10, fill: G.css('--ink-3') }, 'AB: A → B'));
      s.appendChild(G.sv('text', { x: 221, y: 14, 'text-anchor': 'middle', 'font-size': 10, fill: G.css('--ink-3') }, 'CD: C → D'));
      let y = top;
      order.forEach((r, i) => {
        if (i && kind(r) !== kind(order[i - 1])) y += gap;
        const k = kind(r);
        s.appendChild(G.sv('text', { x: 4, y: y + 11, 'font-size': 10.5, fill: G.css('--ink-2') }, 'J' + r));
        [['A', 38], ['B', 98], ['C', 166], ['D', 226]].forEach(([seat, x]) => {
          const snd = seats[r][seat];
          const c = noisy(snd) ? blue : red;
          s.appendChild(G.sv('rect', { x, y: y + 1, width: 50, height: 14, rx: 3, fill: c, 'fill-opacity': seat === 'A' || seat === 'C' ? 0.28 : 0.12,
                                       stroke: c, 'stroke-width': seat === 'A' || seat === 'C' ? 1.4 : 0.8, 'data-seat': seat }));
          s.appendChild(G.sv('text', { x: x + 25, y: y + 11.5, 'text-anchor': 'middle', 'font-size': 9.5, fill: G.css('--ink') }, snd));
        });
        s.appendChild(G.sv('text', { x: 93, y: y + 11.5, 'text-anchor': 'middle', 'font-size': 9.5, fill: G.css('--ink-3') }, '→'));
        s.appendChild(G.sv('text', { x: 221, y: y + 11.5, 'text-anchor': 'middle', 'font-size': 9.5, fill: G.css('--ink-3') }, '→'));
        if (!i || k !== kind(order[i - 1])) {
          s.appendChild(G.sv('text', { x: 286, y: y + 11, 'font-size': 10, 'font-weight': 600, fill: k === 'noise' ? blue : k === 'tone' ? red : G.css('--ink-3') },
                             k === 'noise' ? 'noise-first' : k === 'tone' ? 'tone-first' : 'mixed'));
        }
        y += rh;
      });
      box.appendChild(col([cap('The identity sheet: blue Click or Noise, red a tone; the first sound of each pair outlined'), s]));
    }
    // Two made-up outcomes, on one scale: a dot a rat, its change.
    const yr = [-0.04, 0.2];
    const grp = (name, vals, color) => ({ name, values: vals, mean: vals.reduce((a, b) => a + b, 0) / vals.length,
      se: Math.sqrt(vals.reduce((a, v, _i, all) => a + (v - all.reduce((p, q) => p + q, 0) / all.length) ** 2, 0) / (vals.length - 1) / vals.length), color });
    const w = big ? 300 : 230;
    box.appendChild(col([cap('If the sound mattered (made up): the change is in one group only'),
      G.dots([grp('tone-first', [0.13, 0.16, 0.11, 0.15], G.css('--up')), grp('noise-first', [0.02, -0.01, 0.03, 0.0], G.css('--down'))],
             { w, h: 150, yr, label: 'If the sound mattered: made-up changes by group' })]));
    box.appendChild(col([cap('If it did not (made up): the two groups agree'),
      G.dots([grp('tone-first', [0.07, 0.10, 0.06, 0.09], G.css('--up')), grp('noise-first', [0.08, 0.06, 0.10, 0.07], G.css('--down'))],
             { w, h: 150, yr, label: 'If the sound did not matter: made-up changes by group' })]));
    const p = document.createElement('p');
    p.className = 'qsay';
    p.textContent = 'A dot is one rat’s Precon4 − Precon1 change; the bar is the group’s mean ± SE, on one scale in both. '
      + 'The two lower pictures are made up, to show what each outcome looks like; the tab’s cards hold the real numbers.';
    box.appendChild(p);
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
      box.appendChild(col([cap('Trials, and FP beside them'), G.dots([
        { name: 'trials', values: st.day.cue, mean: st.day.mean, se: st.day.se },
        { name: 'FP epochs', values: st.day.rest, mean: st.day.rest_mean, se: st.day.rest_se, color: G.css('--arrow') }], { w })]));
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
    if (t.exampleFirst) add('qexample', 'For example:', t.example);
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
    if (!t.exampleFirst) add('qexample', 'For example:', t.example);
    add('qplain', '', t.note);
    add('qlook', 'What to look for:', t.look);
    add('qtraps', 'What fools it:', t.traps);
    if (opts.here) add('qhere', 'This one:', opts.here);
    const fig = document.createElement('div');
    fig.className = 'qfigs';
    root.appendChild(fig);
    guide().then((g) => {
      if (!g) return;
      const d = t.draw === 'physical' ? physDemo(opts.big) : t.demo ? statsDemo(t.demo, g, opts.big)
        : (t.plot ? measureDemo(key, g, opts.big) : null);
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
