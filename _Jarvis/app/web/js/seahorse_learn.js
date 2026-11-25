/* ==========================================================================
   seahorse_learn.js -- tours, quiz cards and search for the Seahorse tab
   (BARRY.shLearn).

   Tours are lists of beats; each beat is a title, one or two sentences and
   a few actions the tab knows how to do (['mode', '3d'], ['ride', key],
   ['event', 'ds2'], ['select', sel] ...). The tab runs them in the step bar,
   with Back / Next like a ride.

   Quiz cards come from the atlas itself (layers, cells, connections, DS
   sinks) and are scheduled per person with the SM-2 rule Anki uses
   (Again / Hard / Good / Easy).

   Search knows every cell, layer, region, connection, ride, event and tour
   by its name and a few synonyms.
   ========================================================================== */
'use strict';

BARRY.shLearn = (function () {
  const DG_ML = ['oml1', 'mml1', 'iml1', 'oml2', 'mml2', 'iml2'];

  /* ---------------------------------------------------------------- tours */
  function tours(kb, ctx) {
    const cells = kb.cells.map((c) => ({
      title: c.label,
      say: c.about,
      do: [['mode', '3d'], ['level', c.region === 'mec2' || c.region === 'lec2' ? 'hpf' : 'hpf'], ['cell', c.key]],
    }));
    return [
      {
        key: 'ds', label: 'What is a DS?', blurb: 'DS1 and DS2: where their sinks sit, and why your probe can tell them apart.',
        beats: [
          { title: 'The molecular layer, in thirds', say: 'Granule-cell dendrites fill the molecular layer. Seahorse splits it into thirds by depth: inner (IML), middle (MML) and outer (OML), in both blades.',
            do: [['mode', 'slice'], ['slice', { plane: 'coronal', pos: ctx.probeAp, zoom: 'dg' }], ['layers', DG_ML]] },
          { title: 'Two inputs, two thirds', say: 'Lateral entorhinal axons (the lateral perforant path) end in the outer third; medial entorhinal axons (the medial perforant path) end in the middle third.',
            do: [['schem', 'dentate'], ['select', { type: 'conn', key: 'lpp' }]] },
          { title: 'DS1: the lateral volley', say: 'When many LEC layer II cells fire together, the outer third goes negative: a current sink at OML. That is DS1.',
            do: [['event', 'ds1']] },
          { title: 'DS2: the medial volley', say: 'The same thing one third deeper: a sink at MML. DS2 is usually the larger one.',
            do: [['event', 'ds2']] },
          { title: 'On your probe', say: 'A linear probe through the dentate crosses both thirds. The contact where the sink sits tells DS1 from DS2; in the hilus both dentate spikes are large and positive.',
            do: [['probe', 'show'], ['event', 'ds2'], ['select', { type: 'probe' }]] },
          { title: 'Ride a DS1 volley', say: 'Two real LEC cells fire together and their axons light the outer molecular layer.',
            do: [['mode', '3d'], ['ride', 'ds1']] },
        ],
      },
      {
        key: 'tri', label: 'Trisynaptic loop', blurb: 'Entorhinal cortex to dentate to CA3 to CA1 and out, on four real cells that touch.',
        beats: [
          { title: 'Four cells from four mice', say: 'MouseLight traced these neurons through whole brains and registered them to the Allen atlas. In that shared frame, each axon passes within micrometres of the next cell\'s dendrite.',
            do: [['mode', '3d'], ['level', 'hpf'], ['focus', ['fan', 'gc', 'ca3', 'ca1']]] },
          { title: 'Ride it', say: 'Each step waits for you: Next step (or the right arrow, or Space) moves the signal on. Drag to look around, F to follow again.', do: [['ride', 'trisynaptic']] },
        ],
      },
      {
        key: 'probe', label: "Where's our probe", blurb: 'The 64 contacts, which layers they cross, and what each one records.',
        beats: null,   // built from the probe's own runs when the tour starts
      },
      { key: 'cells', label: 'Meet the cells', blurb: 'One stop for each cell type.', beats: cells },
    ];
  }

  /* What each layer contributes to a recording, for the probe tour. */
  const RECORDS = {
    ca1so: 'Basal dendrites of CA1 pyramidal cells; Schaffer and CA2 inputs; O-LM somata. Positive during sharp waves.',
    ca1sp: 'CA1 cell bodies: their spikes, and the 140-200 Hz ripple during sharp-wave ripples.',
    ca1sr: 'Schaffer collaterals on the apical dendrites: the sharp-wave sink.',
    ca1slm: 'Entorhinal (temporoammonic) input on the tufts; theta is largest near here and the fissure.',
    oml1: 'Lateral perforant path: the DS1 sink (upper blade).', mml1: 'Medial perforant path: the DS2 sink (upper blade).',
    iml1: 'Mossy-cell (associational) input on proximal granule-cell dendrites.', gcl1: 'Granule-cell bodies: their spikes, and a source during dentate spikes.',
    hil: 'Mossy cells and hilar interneurons; dentate spikes are large and positive here.',
    gcl2: 'Granule-cell bodies of the lower blade.', iml2: 'Mossy-cell input, lower blade.', mml2: 'DS2 sink, lower blade.', oml2: 'DS1 sink, lower blade.',
    ca3sp: 'CA3 cell bodies.', ca3slu: 'Mossy fibres and their giant boutons.', ca3sr: 'CA3 recurrent collaterals.', ca3so: 'CA3 basal dendrites.',
    alv: 'The alveus: pyramidal-cell axons leaving.', fi: 'The fimbria.',
  };
  function probeBeats(runs, kb) {
    return runs.filter((r) => r.key || r.name).map((r) => ({
      title: (r.from === r.to ? 'Contact ' + r.from : 'Contacts ' + r.from + '-' + r.to) + ': ' + r.name,
      say: RECORDS[r.key] || (r.full ? r.full + '.' : 'Outside the hippocampus.'),
      do: [['probeRun', r]],
    })).reverse();
  }

  /* ---------------------------------------------------------------- quiz */
  function shuffle(a, seed) {
    const out = a.slice();
    let s = seed || 1;
    for (let i = out.length - 1; i > 0; i--) {
      s = (s * 9301 + 49297) % 233280;
      const j = Math.floor(s / 233280 * (i + 1));
      [out[i], out[j]] = [out[j], out[i]];
    }
    return out;
  }
  const hash = (s) => { let h = 7; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 1000003; return h; };
  function options(answer, pool, id) {
    const others = shuffle(pool.filter((x) => x !== answer), hash(id)).slice(0, 3);
    return shuffle([answer].concat(others), hash(id + 'o'));
  }
  function cards(kb) {
    const L = (k) => (kb.lamina.find((l) => l.key === k) || { label: k }).label;
    const lamKeys = ['oml1', 'mml1', 'iml1', 'gcl1', 'hil', 'ca1so', 'ca1sp', 'ca1sr', 'ca1slm', 'ca3sp', 'ca3slu', 'ca3sr'];
    const lamPool = lamKeys.map(L);
    const out = [];
    for (const k of lamKeys) {
      const id = 'lam-' + k;
      out.push({ id, kind: 'layer', prompt: 'Which layer is lit on the section?', answer: L(k), options: options(L(k), lamPool, id),
                 show: ['layer', k], explain: (kb.lamina.find((l) => l.key === k) || {}).name || '' });
    }
    for (const c of kb.connections) {
      if (!c.layer || !c.layer.length || c.hidden) continue;
      const ans = c.layer.map(L).join(' + ');
      const pool = [...new Set(kb.connections.filter((x) => x.layer && x.layer.length).map((x) => x.layer.map(L).join(' + ')))];
      if (pool.length < 4) continue;
      const id = 'conn-' + c.key;
      out.push({ id, kind: 'connection', prompt: 'Where does the ' + c.label + ' end?', answer: ans, options: options(ans, pool, id),
                 show: ['conn', c.key], explain: c.about || '' });
    }
    const cellPool = kb.cells.map((c) => c.label);
    for (const c of kb.cells) {
      if (c.markers && !/no unique/.test(c.markers)) {
        const id = 'marker-' + c.key;
        out.push({ id, kind: 'cell', prompt: 'Which cell is ' + c.markers.split(',')[0].trim() + '?', answer: c.label,
                   options: options(c.label, cellPool, id), show: ['cell', c.key], explain: c.about });
      }
      const id2 = 'name-' + c.key;
      out.push({ id: id2, kind: 'cell', prompt: 'Name the lit cell.', answer: c.label, options: options(c.label, cellPool, id2),
                 show: ['spot', c.key], explain: c.about });
      const id3 = 'soma-' + c.key;
      const somaPool = [...new Set(kb.cells.map((x) => x.soma))];
      out.push({ id: id3, kind: 'cell', prompt: 'Where does the ' + c.label.toLowerCase() + '\'s soma sit?', answer: c.soma,
                 options: options(c.soma, somaPool, id3), show: ['cell', c.key], explain: 'Dendrites: ' + c.dend + '.' });
    }
    for (const d of kb.ds) {
      const ans = d.sink.map(L).join(' + ');
      const id = 'ds-' + d.key;
      out.push({ id, kind: 'ds', prompt: 'Where is the current sink of ' + d.label + '?', answer: ans,
                 options: options(ans, ['OML1 + OML2', 'MML1 + MML2', 'IML1 + IML2', 'GCL1 + GCL2', 'HIL'].map((s) => s.replace(/(\w+)/g, (m) => m)), id),
                 show: ['event', d.key], explain: d.say });
    }
    return out;
  }
  /* SM-2, as Anki uses it. grade: 0 again, 3 hard, 4 good, 5 easy. */
  function schedule(st, grade, now) {
    st = Object.assign({ ivl: 0, ease: 2.5, reps: 0, lapses: 0 }, st || {});
    now = now || Date.now();
    if (grade < 3) {
      st.reps = 0; st.lapses += 1; st.ivl = 0;
      st.ease = Math.max(1.3, st.ease - 0.2);
      st.due = new Date(now + 10 * 60 * 1000).toISOString();
    } else {
      if (st.reps === 0) st.ivl = grade === 5 ? 3 : 1;
      else if (st.reps === 1) st.ivl = grade === 3 ? 2 : grade === 5 ? 7 : 4;
      else st.ivl = Math.round(st.ivl * (grade === 3 ? 1.2 : grade === 5 ? st.ease * 1.3 : st.ease));
      st.reps += 1;
      st.ease = Math.max(1.3, st.ease + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02)));
      st.due = new Date(now + st.ivl * 86400000).toISOString();
    }
    st.last = new Date(now).toISOString();
    return st;
  }
  function queue(all, states, newPerDay) {
    const now = Date.now();
    const due = all.filter((c) => states[c.id] && states[c.id].due && Date.parse(states[c.id].due) <= now);
    const fresh = all.filter((c) => !states[c.id]).slice(0, newPerDay == null ? 10 : newPerDay);
    return { due, fresh, next: due.concat(fresh) };
  }

  /* -------------------------------------------------------------- search */
  const SYN = {
    gc: 'granule dentate principal prox1 calbindin', sgc: 'semilunar half-moon', mc: 'mossy hilar thorny excrescence',
    hipp: 'somatostatin sst hilar perforant interneuron npy', pvbc: 'parvalbumin pv basket fast-spiking perisomatic',
    aac: 'chandelier axo-axonic ais cartridge', stel: 'stellate grid medial entorhinal mec reelin',
    fan: 'fan lateral entorhinal lec object', ca3: 'ca3 pyramidal recurrent pattern completion', ca1: 'ca1 pyramidal place cell output',
    olm: 'oriens lacunosum o-lm somatostatin chrna2',
    oml1: 'outer molecular lateral perforant ds1', mml1: 'middle molecular medial perforant ds2', iml1: 'inner molecular associational commissural',
    gcl1: 'granule cell layer', hil: 'hilus polymorph', ca3slu: 'lucidum mossy fibre bouton', ca1slm: 'lacunosum moleculare tuft temporoammonic',
    ca1sr: 'radiatum schaffer sharp wave', ca1sp: 'pyramidale ripple', ca1so: 'oriens basal',
    lpp: 'lateral perforant path ds1', mpp: 'medial perforant path ds2', mf_ca3: 'mossy fibre giant bouton detonator',
    sc: 'schaffer collateral ltp', ta: 'temporoammonic direct', rc: 'recurrent autoassociative',
    ds1: 'dentate spike lateral', ds2: 'dentate spike medial', swr: 'sharp wave ripple replay', theta: 'theta gamma rhythm',
    pspike: 'p-spike interictal epileptiform spike seizure',
  };
  function index(kb, extra) {
    const E = [];
    const add = (label, sub, kind, target, terms) => E.push({ label, sub, kind, target, terms: (label + ' ' + (sub || '') + ' ' + (terms || '')).toLowerCase() });
    kb.cells.forEach((c) => add(c.label, (c.markers || '') + ' cell', 'cell', { type: 'cell', key: c.key }, c.short + ' ' + (SYN[c.key] || '')));
    kb.lamina.forEach((l) => add(l.label, l.name, 'layer', { type: 'lamina', key: l.key }, SYN[l.key] || ''));
    kb.regions.forEach((r) => add(r.label, r.sub, 'region', { type: 'region', key: r.key }, (r.allen || []).join(' ')));
    kb.connections.filter((c) => !c.hidden).forEach((c) => add(c.label, 'connection', 'conn', { type: 'conn', key: c.key }, SYN[c.key] || ''));
    (extra.rides || []).forEach((r) => add(r.label, 'ride', 'ride', { ride: r.key }, r.blurb + ' ' + (SYN[r.key] || '')));
    Object.entries(extra.events || {}).forEach(([k, e]) => add(e.label, 'play the model', 'event', { event: k }, SYN[k] || ''));
    (extra.tours || []).forEach((t) => add(t.label, 'tour', 'tour', { tour: t.key }, t.blurb));
    (extra.stories || []).forEach((s) => add(s.label, 'a recorded seizure, click by click', 'story', { story: s.key }, s.blurb + ' seizure ictal postictal tonic clonic kcnt1 459 spread'));
    (extra.views || []).forEach((v) => add(v.name, 'saved view' + (v.by ? ' by ' + v.by : ''), 'view', { view: v.id }, ''));
    return E;
  }
  function search(E, q) {
    q = (q || '').trim().toLowerCase();
    if (!q) return [];
    const words = q.split(/\s+/);
    const scored = [];
    for (const e of E) {
      let s = 0;
      const lab = e.label.toLowerCase();
      if (lab === q) s += 100;
      else if (lab.startsWith(q)) s += 60;
      else if (lab.includes(q)) s += 40;
      let all = true;
      for (const w of words) { if (e.terms.includes(w)) s += 10; else all = false; }
      if (!all && s < 40) continue;
      scored.push([s - lab.length * 0.05, e]);
    }
    scored.sort((a, b) => b[0] - a[0]);
    return scored.slice(0, 9).map((x) => x[1]);
  }

  return { tours, probeBeats, RECORDS, cards, schedule, queue, index, search };
})();
