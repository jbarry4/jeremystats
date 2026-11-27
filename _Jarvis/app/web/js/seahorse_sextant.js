/* ==========================================================================
   seahorse_sextant.js -- Sextant: where was the probe?

   A sailor fixes a ship's position from angles to stars whose places are
   known. Sextant fixes a recording probe's position from layers whose places
   are known: every signal the recording carries that belongs to one layer
   says where along the shank that layer was crossed, and the atlas says where
   those layers lie in a real brain. The straight probe that makes the two
   agree is the answer; the probes that nearly do are the cloud around it.

   The placements are computed offline (backend/sextant/, run by
   tools/sextant/run.py) into web/seahorse/sextant/<gid>.json. This file holds
   the words, the references and the card's drawings; seahorse.js plays the
   stops. Nothing here reads a layer label: the lab's labels are never
   evidence and never a check (the user, 2026-11-27).
   ========================================================================== */
'use strict';

BARRY.shSextant = (function () {
  const REFS = {
    winson1974: 'Winson J (1974) Patterns of hippocampal theta rhythm in the freely moving rat. Electroencephalogr Clin Neurophysiol 36:291-301.',
    buzsaki2002: 'Buzsáki G (2002) Theta oscillations in the hippocampus. Neuron 33:325-340.',
    buzsaki2015: 'Buzsáki G (2015) Hippocampal sharp wave-ripple: a cognitive biomarker for episodic memory and planning. Hippocampus 25:1073-1188.',
    ylinen1995: 'Ylinen A, Bragin A, Nádasdy Z, Jandó G, Szabó I, Sik A, Buzsáki G (1995) Sharp wave-associated high-frequency oscillation (200 Hz) in the intact hippocampus: network and intracellular mechanisms. J Neurosci 15:30-46.',
    castelli2025: 'Castelli M, et al. (2025) Ripples with current sinks in stratum lacunosum-moleculare form a distinct subtype in mouse CA1. Neuron (in press).',
    bragin1995: 'Bragin A, Jandó G, Nádasdy Z, van Landeghem M, Buzsáki G (1995) Dentate EEG spikes and associated interneuronal population bursts in the hippocampal hilar region of the rat. J Neurophysiol 73:1691-1705.',
    bragin1995g: 'Bragin A, Jandó G, Nádasdy Z, Hetke J, Wise K, Buzsáki G (1995) Gamma (40-100 Hz) oscillation in the hippocampus of the behaving rat. J Neurosci 15:47-60.',
    dvorak2021: 'Dvorak D, Chung A, Park EH, Fenton AA (2021) Dentate spikes and external control of hippocampal function. Cell Rep 36:109497.',
    senzai2017: 'Senzai Y, Buzsáki G (2017) Physiological properties and behavioral correlates of hippocampal granule cells and mossy cells. Neuron 93:691-704.',
    fernandezruiz2021: 'Fernández-Ruiz A, Oliva A, Soula M, Rocha-Almeida F, Nagy GA, Martin-Vazquez G, Buzsáki G (2021) Gamma rhythm communication between entorhinal cortex and dentate gyrus neuronal assemblies. Science 372:eabf3119.',
    santiago2024: 'Santiago RMM, et al. (2024) Waveform-based classification of dentate spikes. Sci Rep 14:2989.',
    pettersen2006: 'Pettersen KH, Devor A, Ulbert I, Dale AM, Einevoll GT (2006) Current-source density estimation based on inversion of electrostatic forward solution: effects of finite extent of neuronal activity and conductivity discontinuities. J Neurosci Methods 154:116-133.',
    benito2014: 'Benito N, Fernández-Ruiz A, Makarov VA, Makarova J, Korovaichuk A, Herreras O (2014) Spatial modules of coherent activity in pathway-specific LFPs in the hippocampus reflect topology and different modes of presynaptic synchronization. Cereb Cortex 24:1738-1752.',
    lubenov2009: 'Lubenov EV, Siapas AG (2009) Hippocampal theta oscillations are travelling waves. Nature 459:534-539.',
    wang2020: 'Wang Q, Ding SL, Li Y, et al. (2020) The Allen Mouse Brain Common Coordinate Framework: a 3D reference atlas. Cell 181:936-953.',
    ibl2024: 'International Brain Laboratory, Banga K, et al. (2024) Reproducibility of in vivo electrophysiological measurements in mice. eLife 13:RP100840.',
    tolossa2024: 'Tolossa GB, Schneider AM, Dyer EL, Hengen KB (2024) Neurons throughout the brain embed robust signatures of their anatomical location into spike trains. eLife 13:RP101506.',
    pun2012: 'Pun RYK, Rolle IJ, LaSarge CL, Hosford BE, Rosen JM, Uhl JD, Schmeltzer SN, Faulkner C, Bronson SL, Murphy BL, Richards DA, Holland KD, Danzer SC (2012) Excessive activation of mTOR in postnatally generated granule cells is sufficient to cause epilepsy. Neuron 75:1022-1034.',
    lasarge2016: 'LaSarge CL, Pun RYK, Muntifering MB, Danzer SC (2016) Disrupted hippocampal network physiology following PTEN deletion from newborn dentate granule cells. Neurobiol Dis 96:105-114.',
  };

  /* each family of evidence: its name on the stop, and where it comes from */
  const FAMILY = {
    prior: { refs: ['wang2020', 'ibl2024'] },
    ca1: { refs: ['buzsaki2015', 'ylinen1995'] },
    spw: { refs: ['ylinen1995', 'buzsaki2015', 'castelli2025'] },
    theta: { refs: ['winson1974', 'buzsaki2002', 'lubenov2009'] },
    ds: { refs: ['bragin1995', 'dvorak2021', 'senzai2017'] },
    path: { refs: ['pun2012', 'lasarge2016', 'bragin1995'] },
    below: { refs: ['wang2020'] },
    both: { refs: ['pettersen2006', 'benito2014', 'ibl2024'] },
  };

  const LM_WORDS = {
    sp: 'CA1’s cell layer', spw_rev: 'the sharp wave’s reversal', sp_above: 'CA1’s cell layer (above the top)',
    sr_sink: 'stratum radiatum', slm_src: 'lacunosum-moleculare', fissure: 'the fissure',
    ml_a: 'the upper molecular layer', ml_b: 'the lower molecular layer', dg_core: 'the granule cells',
    dg_end: 'the dentate’s lower edge', th_top: 'the thalamus', hil_gam: 'dentate gamma',
    ps_ml_a: 'P-spikes, upper sink', ps_ml_b: 'P-spikes, lower sink', ps_dg_core: 'P-spikes, return',
    bt_ml_a: 'BTs, upper sink', bt_ml_b: 'BTs, lower sink', bt_dg_core: 'BTs, return',
  };

  /* the evidence curves each stop draws in the card (keys of D.evidence.curves) */
  const CURVES = {
    prior: [],
    ca1: [['ripple_theta', 'ripples ÷ theta'], ['mua', 'multiunit'], ['ripple_events', 'ripple power in ripples']],
    spw: [['spw', 'sharp wave'], ['spw_csd', 'its current', 'csd']],
    theta: [['theta', 'theta amplitude'], ['theta_phase', 'theta phase', 'phase']],
    ds: [['ds', 'dentate spike'], ['ds_csd', 'its current', 'csd']],
    path: [['ps_csd', 'P-spike current', 'csd'], ['bt_csd', 'BT current', 'csd']],
    below: [['mua', 'multiunit'], ['theta', 'theta amplitude']],
    both: [['ripple_theta', 'ripples ÷ theta'], ['theta', 'theta'], ['ds_csd', 'DS current', 'csd'], ['spw_csd', 'sharp wave', 'csd']],
  };
  CURVES.brain = CURVES.both;
  const LM_OF = {
    ca1: ['sp', 'spw_rev', 'sp_above'], spw: ['sr_sink', 'slm_src'], theta: ['fissure'],
    ds: ['ml_a', 'ml_b', 'dg_core', 'dg_end', 'hil_gam'], path: ['ps_ml_a', 'ps_ml_b', 'ps_dg_core', 'bt_ml_a', 'bt_ml_b', 'bt_dg_core'],
    below: ['th_top'],
  };

  const n1 = (x) => (Math.round(x * 10) / 10).toFixed(1);
  const contactOf = (lm) => n1(lm.x + 1);
  const mm = (v, d) => (v < 0 ? '−' : '') + Math.abs(v).toFixed(d == null ? 2 : d);
  const ap = (v) => 'AP ' + mm(v);
  const ml = (v, side) => 'ML ' + (side === 'L' ? '−' : side === 'R' ? '+' : '±') + Math.abs(v).toFixed(2);

  /* how far apart the cloud's probes are around the stop's best (median, um):
     the "spread" the dock reports as the cloud narrows */
  function spread(stop) {
    const b = stop.best, mid = (l) => [(l[0][0] + l[1][0]) / 2, (l[0][1] + l[1][1]) / 2, (l[0][2] + l[1][2]) / 2];
    const m0 = mid(b);
    const d = stop.cloud.map((l) => { const m = mid(l); return Math.hypot(m[0] - m0[0], m[1] - m0[1], m[2] - m0[2]); }).sort((a, b2) => a - b2);
    return d.length ? d[Math.floor(d.length / 2)] : 0;
  }

  /* the words for a stop, from what was found in this recording */
  function say(D, stop, prev) {
    const L = (k) => D.landmarks.find((l) => l.key === k);
    const at = (k) => { const l = L(k); return l ? 'contact ' + contactOf(l) : null; };
    const um = (a, b) => { const x = L(a), y = L(b); return x && y ? Math.round(Math.abs(y.x - x.x) * 20) : null; };
    const s = [];
    if (stop.id === 'prior') {
      s.push('Before the recording says anything, the probe could be anywhere under your craniotomy (AP −2.2, ML ±1.4 mm from bregma, "but it can vary a lot"). Every faint line is a probe the craniotomy allows.');
    } else if (stop.id === 'ca1') {
      if (L('sp')) s.push('Ripples stand highest against theta, and units fire most, at ' + at('sp') + ': CA1’s cell layer.');
      else if (L('sp_above')) s.push('Ripples only grow toward the top of the shank: CA1’s cell layer is above the first contact, so the probe starts in stratum radiatum.');
      if (L('spw_rev')) s.push('The sharp wave flips sign at ' + at('spw_rev') + ', where the cell layer meets radiatum.');
      s.push('Probes that would put CA1’s cell layer anywhere else fall away.');
    } else if (stop.id === 'spw') {
      if (L('sr_sink')) s.push('Each sharp wave sinks current at ' + at('sr_sink') + ': stratum radiatum, where CA3’s axons land.');
      if (L('slm_src')) s.push('Its return current comes back at ' + at('slm_src') + ': lacunosum-moleculare.');
    } else if (stop.id === 'theta') {
      if (L('fissure')) s.push('Theta is largest at ' + at('fissure') + ': the hippocampal fissure, where the entorhinal input to CA1 and the dentate meet.');
    } else if (stop.id === 'ds') {
      const n = D.evidence.counts.ds;
      if (L('ml_a') && L('ml_b')) s.push(n + ' dentate spikes sink current at ' + at('ml_a') + ' and ' + at('ml_b') + ': the molecular layers of the two blades, ' + um('ml_a', 'ml_b') + ' µm apart along the shank. How far apart they are says where in the dentate the probe went: wide near the middle of the blades, narrow near the crest.');
      else if (L('ml_a')) s.push(n + ' dentate spikes sink current at ' + at('ml_a') + ' only: the probe crossed one blade’s molecular layer.');
      if (L('dg_end')) s.push('Their current ends at ' + at('dg_end') + ': the dentate’s lower edge.');
    } else if (stop.id === 'path') {
      const c = D.evidence.counts;
      const bits = [];
      if (L('ps_ml_a')) bits.push(c.ps + ' P-spikes sink at ' + at('ps_ml_a') + (L('ps_ml_b') ? ' and ' + at('ps_ml_b') : ''));
      if (L('bt_ml_a')) bits.push(c.bt + ' borderline transients at ' + at('bt_ml_a') + (L('bt_ml_b') ? ' and ' + at('bt_ml_b') : ''));
      s.push(bits.join('; ') + ': the same molecular layers, a second and third witness.');
    } else if (stop.id === 'below') {
      if (L('th_top')) s.push('Below ' + at('th_top') + ' units fire again, more than in the dentate: the thalamus under the hippocampus.');
    } else if (stop.id === 'both') {
      const A = D.methods.A, B = D.methods.B;
      const gap = Math.round(1000 * Math.hypot(A.entry.ap - B.entry.ap, Math.abs(A.entry.ml) - Math.abs(B.entry.ml)));
      s.push('Method A (the landmarks against the atlas) and Method B (simulating each pathway’s current from the atlas layers and matching all of it) are added together. Alone, they put the entry ' + gap + ' µm apart.');
    }
    if (prev && stop.id !== 'prior') {
      const a = spread(prev), b = spread(stop);
      if (a > 0 && b > 0) s.push(b < a * 0.92 ? 'The cloud tightened from ' + Math.round(a) + ' to ' + Math.round(b) + ' µm.' : b > a * 1.08 ? 'The cloud widened, ' + Math.round(a) + ' to ' + Math.round(b) + ' µm: this evidence pulls a different way.' : 'The cloud held at about ' + Math.round(b) + ' µm.');
    }
    return s.join(' ');
  }

  /* a lane's title in its lane: 11 px, down to 9 px, then on two lines */
  function fitTitle(g, text, x, w, font) {
    for (const px of [11, 10, 9]) {
      g.font = px + 'px ' + font;
      if (g.measureText(text).width <= w) { g.fillText(text, x, 14); return; }
    }
    const words = text.split(' ');
    let a = words.slice(0, Math.ceil(words.length / 2)).join(' '), b = words.slice(Math.ceil(words.length / 2)).join(' ');
    g.font = '9px ' + font;
    g.fillText(a, x, 8);
    g.fillText(b, x, 18);
    g.font = '11px ' + font;
  }

  /* ---------- the card's evidence panel ----------
     Depth runs down (contact 1 at the top, 64 at the bottom). Each curve is
     drawn in its own lane, scaled to its own range; a current (CSD) is drawn
     as a filled trace, sinks to the left. The found landmarks cross every
     lane; the strip on the right is the atlas layer under each contact for
     the stop's best probe. */
  function drawEvidence(cv, D, stop, o) {
    const dpr = window.devicePixelRatio || 1;
    const W = cv.clientWidth || 320, H = Math.round(Math.max(260, Math.min(420, W * 1.05)));
    cv.style.height = H + 'px';
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    g.font = '11px ' + o.font;
    const curves = (CURVES[stop.id] || []).filter(([k]) => D.evidence.curves[k]);
    const stripW = 54, top = 24, bot = 10, left = 28;
    const plotW = W - left - stripW - 18;
    const laneW = curves.length ? plotW / curves.length : plotW;
    const y = (c) => top + (c / 63) * (H - top - bot);       // c: 0-based contact
    // contact ticks
    g.fillStyle = o.ink3;
    g.textAlign = 'right';
    [1, 16, 32, 48, 64].forEach((c) => g.fillText(String(c), left - 6, y(c - 1) + 4));
    g.save(); g.translate(9, top + (H - top - bot) / 2); g.rotate(-Math.PI / 2); g.textAlign = 'center'; g.fillText('contact', 0, 0); g.restore();
    curves.forEach(([k, name, kind], i) => {
      const x0 = left + i * laneW + 6, w = laneW - 12;
      const v = D.evidence.curves[k];
      g.fillStyle = o.soft;
      g.fillRect(x0 - 3, top, w + 6, H - top - bot);
      g.fillStyle = o.ink2;
      g.textAlign = 'center';
      fitTitle(g, name, x0 + w / 2, w + 6, o.font);
      if (kind === 'csd') {
        const xm = x0 + w / 2;
        g.strokeStyle = o.ink1; g.beginPath(); g.moveTo(xm, top); g.lineTo(xm, H - bot); g.stroke();
        for (let c = 0; c < 64; c++) {
          if (v[c] == null) continue;
          const a = v[c];
          g.fillStyle = a < 0 ? o.sink : o.source;
          const yy = y(c) - (H - top - bot) / 126;
          g.fillRect(a < 0 ? xm + a * w / 2 : xm, yy, Math.abs(a) * w / 2, (H - top - bot) / 63 + 0.5);
        }
      } else {
        let lo = Infinity, hi = -Infinity;
        v.forEach((a) => { if (a != null) { lo = Math.min(lo, a); hi = Math.max(hi, a); } });
        const sx = (a) => x0 + (hi > lo ? (a - lo) / (hi - lo) : 0.5) * w;
        g.strokeStyle = o.line; g.lineWidth = 1.6; g.beginPath();
        let pen = false;
        for (let c = 0; c < 64; c++) {
          if (v[c] == null) { pen = false; continue; }
          if (!pen) { g.moveTo(sx(v[c]), y(c)); pen = true; } else g.lineTo(sx(v[c]), y(c));
        }
        g.stroke();
      }
    });
    // landmarks found so far (this stop's own stand out)
    const mine = new Set(LM_OF[stop.id] || []);
    const shown = new Set(o.seen || []);
    D.landmarks.forEach((l) => {
      if (!shown.has(l.key) && !mine.has(l.key)) return;
      const yy = y(l.x);
      const on = mine.has(l.key);
      g.strokeStyle = on ? o.accent : o.ink3;
      g.lineWidth = on ? 1.6 : 1;
      g.setLineDash(l.side ? [2, 3] : on ? [] : [4, 3]);
      g.beginPath(); g.moveTo(left, yy); g.lineTo(left + plotW + 6, yy); g.stroke();
      g.setLineDash([]);
    });
    // the atlas strip for this stop's best probe
    const sx0 = W - stripW - 4;
    const lay = stop.layers || [];
    for (let c = 0; c < 64; c++) {
      g.fillStyle = o.layerColor(lay[c]) || o.soft;
      g.fillRect(sx0, y(c) - (H - top - bot) / 126, 16, (H - top - bot) / 63 + 0.5);
    }
    g.fillStyle = o.ink2;
    g.textAlign = 'left';
    g.fillText('atlas', sx0, 14);
    let prevK = null, lastY = -99;
    for (let c = 0; c < 64; c++) {
      const k = lay[c];
      if (k === prevK) continue;
      prevK = k;
      const yy = Math.max(y(c) + 4, lastY + 11);
      if (yy > H - 2) break;
      g.fillStyle = o.ink3;
      g.fillText(o.layerShort(k), sx0 + 20, yy);
      lastY = yy;
    }
  }

  return { REFS, FAMILY, LM_WORDS, CURVES, LM_OF, say, spread, drawEvidence, ap, ml, mm };
})();
