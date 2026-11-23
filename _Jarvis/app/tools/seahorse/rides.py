# -*- coding: utf-8 -*-
"""Rides: a signal followed along real cells, axon to synapse to dendrite to
soma to axon, through the circuit.

    python tools/seahorse/rides.py --chains     search for touching chains
    python tools/seahorse/rides.py              build web/seahorse/rides.json

Run after cells.py: it reads the placed cells (RAW/cells_built.npz) and
where each one meets the next (RAW/cells_stats.json, 'story').

The whole-brain tracings (MouseLight) share one atlas frame, so where one
cell's axon passes within a few micrometres of another cell's dendrite, in
the layer where that connection is known to synapse, the ride shows a
synapse there. These are cells from different mice, aligned only by
registration (good to roughly 50-100 um), so a "contact" is a close
approach in the shared frame, not a synapse anyone saw; the tab says so.

Timing: each axon step takes (its real path length) / (that fibre's
conduction velocity); each synapse a delay; the numbers and their sources
are in VELOCITY and DELAY and travel with the ride.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import OUT, RAW, log, read_json, write_json  # noqa: E402
from volume import CODE  # noqa: E402

# m/s, with sources (shown in the tab next to the ms clock)
VELOCITY = {
    'pp': (3.3, 'Perforant path volley, rabbit in vivo (Lomo 1971).'),
    'mf': (0.24, 'Mossy fibre, mouse slices (Schmidt-Hieber, Jonas & Bischofberger 2008).'),
    'ca3': (0.3, 'CA3 pyramidal axon, unmyelinated (Meeks & Mennerick 2007).'),
    'ca1': (0.3, 'Pyramidal axon, assumed like CA3 (Meeks & Mennerick 2007).'),
    'mc': (0.25, 'Mossy-cell axon, assumed like mossy fibres (slower in imaging: Ma et al. 2017).'),
    'int': (0.3, 'Interneuron axon, assumed.'),
    'drawn': (3.3, 'Drawn path; perforant-path speed assumed.'),
}
DELAY = {'synapse': (0.8, 'Monosynaptic delay after the perforant-path volley (Lomo 1971).'),
         'dend': (1.5, 'EPSP spread to the soma, a few ms (assumed).'),
         'fire': (1.0, 'Spike start at the axon initial segment, 20-30 um out (Schmidt-Hieber et al. 2008).')}

REFS = {
    'lomo1971': 'Lomo T (1971) Patterns of activation in a monosynaptic cortical pathway: the perforant path input to the dentate area of the hippocampal formation. Exp Brain Res 12:18-45.',
    'schmidthieber2008': 'Schmidt-Hieber C, Jonas P, Bischofberger J (2008) Action potential initiation and propagation in hippocampal mossy fibre axons. J Physiol 586:1849-1857.',
    'meeks2007': 'Meeks JP, Mennerick S (2007) Action potential initiation and propagation in CA3 pyramidal axons. J Neurophysiol 97:3460-3472.',
    'ma2017': 'Ma Y, Bayguinov PO, Jackson MB (2017) Action potential dynamics in fine axons probed with an axonally targeted optical voltage sensor. eNeuro 4:ENEURO.0146-17.2017.',
    'pun2012': 'Pun RYK, Rolle IJ, LaSarge CL, et al. (2012) Excessive activation of mTOR in postnatally generated granule cells is sufficient to cause epilepsy. Neuron 75:1022-1034.',
    'shore2020': 'Shore AN, Colombo S, Tobin WF, et al. (2020) Reduced GABAergic neuron excitability, altered synaptic connectivity, and seizures in a KCNT1 gain-of-function mouse model of childhood epilepsy. Cell Rep 33:108303.',
    'rollenhagen2007': 'Rollenhagen A, Satzler K, Rodriguez EP, Jonas P, Frotscher M, Lubke JHR (2007) Structural determinants of transmission at large hippocampal mossy fiber synapses. J Neurosci 27:10434-10444.',
    'winnubst2019': 'Winnubst J, Bas E, Ferreira TA, et al. (2019) Reconstruction of 1,000 projection neurons reveals new cell types and organization of long-range connectivity in the mouse brain. Cell 179:268-281.',
}

# What each synapse looks like up close (the tab draws the inset from this).
SYNAPSES = {
    'pp_spine': {'title': 'Perforant-path bouton on a granule-cell spine', 'sign': 'exc',
                 'say': 'A small glutamatergic bouton on a dendritic spine, far out on the dendrite. AMPA and NMDA receptors; each synapse is weak, so many must arrive together.',
                 'refs': ['witter2007', 'amaral2007']},
    'mf_giant': {'title': 'Giant mossy-fibre bouton on a thorny excrescence', 'sign': 'exc',
                 'say': 'One of the largest synapses in the brain: a bouton 4-10 um across wrapped around a cluster of spines (a thorny excrescence) on the CA3 cell\'s proximal dendrite, with dozens of release sites. Weak at rest, it facilitates hugely with repeated firing: a conditional detonator.',
                 'refs': ['rollenhagen2007', 'henze2000']},
    'mf_thorn_mc': {'title': 'Mossy-fibre bouton on a mossy-cell thorn', 'sign': 'exc',
                    'say': 'In the hilus the granule-cell axon gives large boutons onto the thorny excrescences of mossy cells, the hilar counterpart of the CA3 contact.',
                    'refs': ['acsady1998', 'scharfman2016']},
    'mc_iml': {'title': 'Mossy-cell bouton in the inner molecular layer', 'sign': 'exc',
               'say': 'Mossy-cell axons end on the proximal dendrites of granule cells in the inner third of the molecular layer, mostly at other levels and on the other side.',
               'refs': ['buckmaster1996', 'scharfman2016']},
    'sc_spine': {'title': 'Schaffer-collateral bouton on a CA1 spine', 'sign': 'exc',
                 'say': 'Small en-passant boutons on CA1 spines in stratum radiatum and oriens: the most studied synapse in neuroscience (LTP).',
                 'refs': ['ishizuka1990']},
    'rc_spine': {'title': 'Recurrent-collateral bouton on a CA3 spine', 'sign': 'exc',
                 'say': 'CA3 cells excite each other in radiatum and oriens: the autoassociative network that can complete a pattern from a fragment.',
                 'refs': ['ishizuka1990']},
    'ta_spine': {'title': 'Temporoammonic bouton on a CA1 tuft spine', 'sign': 'exc',
                 'say': 'EC layer III axons end on the distal tuft of CA1 cells in stratum lacunosum-moleculare.',
                 'refs': ['kitamura2014', 'vanstrien2009']},
    'inh_dend': {'title': 'GABAergic bouton on a distal dendrite', 'sign': 'inh',
                 'say': 'Dendrite-targeting inhibition: GABA-A synapses on the dendritic shaft right where the excitatory input of that layer arrives.',
                 'refs': ['han1993', 'klausberger2008']},
    'inh_peri': {'title': 'Basket-cell terminals around a soma', 'sign': 'inh',
                 'say': 'Perisomatic inhibition: many fast GABA-A boutons from one basket cell on the cell body, timing when the cell can fire.',
                 'refs': ['freund1996', 'hosp2014']},
    'inh_ais': {'title': 'Chandelier cartridge on the axon initial segment', 'sign': 'inh',
                'say': 'Axo-axonic terminals line up along the axon initial segment, where the spike starts.',
                'refs': ['soriano1989', 'freund1996']},
}


def tree_path(xyz, par, node):
    """Node -> root (soma), as a list of indices."""
    out = [node]
    while par[out[-1]] >= 0:
        out.append(int(par[out[-1]]))
    return out


def polyline_len(pts):
    pts = np.asarray(pts)
    return float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum()) if len(pts) > 1 else 0.0


def rnd(pts):
    return [[round(float(v), 1) for v in p] for p in pts]


class Cells:
    def __init__(self):
        z = np.load(os.path.join(RAW, 'cells_built.npz'))
        self.c = {}
        for k in z.files:
            key, f = k.split(':')
            self.c.setdefault(key, {})[f] = z[k]
        self.stats = read_json(os.path.join(RAW, 'cells_stats.json'))

    def soma(self, k):
        c = self.c[k]
        s = np.nonzero(c['typ'] == 1)[0]
        return int(s[0]) if len(s) else 0

    def out_path(self, k, node):
        """soma -> node along the tree."""
        c = self.c[k]
        idx = tree_path(c['xyz'], c['par'], node)[::-1]
        return c['xyz'][idx]

    def in_path(self, k, node):
        """node -> soma along the tree."""
        c = self.c[k]
        return c['xyz'][tree_path(c['xyz'], c['par'], node)]

    def story(self, k):
        return self.stats[k].get('story') or {}

    def nearest_node(self, k, p, types):
        c = self.c[k]
        m = np.nonzero(np.isin(c['typ'], types))[0]
        d = np.linalg.norm(c['xyz'][m] - p, axis=1)
        return int(m[int(np.argmin(d))]), float(d.min())


def route25(a, b, cost_by_acr, default=60.0, outside=5000.0, pad=400.0):
    """A drawn path from a to b (CCF um) through the Allen annotation at
    25 um: cheapest route where each structure costs what cost_by_acr says
    (descendants included)."""
    import nrrd
    from skimage.graph import route_through_array
    from common import by_acronym, ontology
    flat = ontology()
    A = by_acronym(flat)
    a25, _ = nrrd.read(os.path.join(RAW, 'annotation_25.nrrd'))
    lo = np.maximum((np.minimum(a, b) - pad) // 25, 0).astype(int)
    hi = np.minimum((np.maximum(a, b) + pad) // 25 + 1, np.array(a25.shape)).astype(int)
    sub = a25[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]]
    ids = np.unique(sub)
    lut = {}
    for sid in ids:
        sid = int(sid)
        if sid == 0:
            lut[sid] = outside
            continue
        path = flat[sid]['path'] if sid in flat else []
        c = default
        best_depth = -1
        for ac, cost in cost_by_acr.items():
            if ac in A and A[ac]['id'] in path:
                depth = path.index(A[ac]['id'])
                if depth > best_depth:
                    best_depth, c = depth, cost
        lut[sid] = c
    cost = np.vectorize(lambda v: lut[int(v)], otypes=[np.float64])(sub)
    ga = tuple(np.clip((a // 25).astype(int) - lo, 0, np.array(sub.shape) - 1))
    gb = tuple(np.clip((b // 25).astype(int) - lo, 0, np.array(sub.shape) - 1))
    path, _ = route_through_array(cost, ga, gb, fully_connected=True, geometric=True)
    pts = (np.array(path) + lo) * 25.0 + 12.5
    pts[0], pts[-1] = a, b
    for _ in range(4):
        pts[1:-1] = (pts[:-2] + 2 * pts[1:-1] + pts[2:]) / 4
    return pts


PP_COST = {'ENTm5': 3.0, 'ENTm6': 3.0, 'ENTl5': 3.0, 'ENTl6a': 3.0, 'ab': 1.0, 'per': 1.0, 'ENTm4': 6.0,
           'SUB': 4.0, 'ProS': 4.0, 'PRE': 5.0, 'POST': 5.0, 'PAR': 4.0, 'hf': 1.0, 'DG-mo': 2.0,
           'CA1': 8.0, 'CA3': 8.0, 'DG-sg': 30.0, 'DG-po': 30.0, 'ENTm1': 15.0, 'ENTm2': 6.0, 'ENTm3': 4.0,
           'ENTl1': 15.0, 'ENTl2': 6.0, 'ENTl3': 4.0, 'fiber tracts': 12.0}


class Ride:
    def __init__(self, key, label, blurb, kind='ride'):
        self.key, self.label, self.blurb, self.kind = key, label, blurb, kind
        self.steps = []
        self.t = 0.0

    def add(self, kind, title, say, cite=(), lab='', cell=None, path=None, ms=None, fiber=None,
            synapse=None, layer=None, sign='exc', also=None, bridge_um=None, drawn=False, frame=None, conn=None):
        st = {'kind': kind, 'title': title, 'say': say, 'cite': list(cite), 'lab': lab, 'sign': sign}
        if cell:
            st['cell'] = cell
        if path is not None:
            st['path'] = rnd(path)
            st['len_um'] = round(polyline_len(path), 1)
        if fiber:
            v, src = VELOCITY[fiber]
            ms = st['len_um'] / (v * 1000.0)       # um / (um per ms); 1 m/s = 1000 um/ms
            st['fiber'] = fiber
            st['velocity'] = {'m_per_s': v, 'source': src}
        if ms is None:
            ms = DELAY.get(kind, (0.0, ''))[0]
        st['ms'] = [round(self.t, 2), round(ms, 2)]
        self.t += ms
        for k, v in (('synapse', synapse), ('layer', layer), ('also', also), ('bridge_um', bridge_um), ('frame', frame), ('conn', conn)):
            if v is not None:
                st[k] = v
        if drawn:
            st['drawn'] = True
        self.steps.append(st)
        return st

    def out(self):
        return {'key': self.key, 'label': self.label, 'blurb': self.blurb, 'kind': self.kind,
                'total_ms': round(self.t, 2), 'steps': self.steps}


def lam_of(p):
    from cells import Atlas
    if not hasattr(lam_of, 'at'):
        lam_of.at = Atlas()
    at = lam_of.at
    return at.lam_key.get(int(at.lam(np.array([p]))[0]), '') or at.acr(at.allen(np.array([p]))[0])


def build():
    C = Cells()
    rides = []

    # ------------------------------------------------------------------
    # 1. The trisynaptic loop, on four real cells that touch
    # ------------------------------------------------------------------
    R = Ride('trisynaptic', 'Trisynaptic loop', 'Entorhinal cortex to dentate to CA3 to CA1 to subiculum, riding four whole-brain tracings that touch in the atlas.')
    s_gc, s_ca3, s_ca1 = C.story('gc'), C.story('ca3'), C.story('ca1')
    R.add('fire', 'An entorhinal layer II cell fires',
          'MouseLight AA1047, a layer II cell of the lateral entorhinal cortex, traced through the whole brain (Winnubst 2019). Its axon is the lateral perforant path.',
          cite=['winnubst2019', 'witter2007'], cell='fan',
          lab='Layer II of the entorhinal cortex is where dentate spikes start: a lateral volley gives DS1, a medial one DS2.')
    p = C.out_path('fan', s_gc['up_node'])
    R.add('axon', 'Down the perforant path',
          'The axon leaves layer II, runs through the angular bundle, perforates the subiculum and crosses the hippocampal fissure into the dentate molecular layer.',
          cite=['witter2007', 'steward1976'], cell='fan', path=p, fiber='pp', layer=s_gc['layer'], conn='lpp')
    R.add('synapse', 'Synapse on a granule-cell dendrite',
          'The axon passes %.1f um from granule cell AA0573\'s dendrite in %s (shifted %.1f um to touch): a perforant-path spine synapse.' % (s_gc['gap_um'], s_gc['layer'].upper(), np.linalg.norm(s_gc['shift_um'])),
          cite=['lomo1971'], cell='gc', synapse='pp_spine', layer=s_gc['layer'], conn='lpp',
          lab='This molecular-layer synapse is the current sink you see at DS1 (outer third) and DS2 (middle third).')
    R.add('dend', 'Inward to the soma', 'The EPSP spreads from the distal dendrite to the cell body.',
          cell='gc', path=C.in_path('gc', s_gc['node']))
    R.add('fire', 'The granule cell fires',
          'Granule cells fire sparsely; the spike starts 20-30 um out along the axon (Schmidt-Hieber 2008). AA0573 sits in the lower (infrapyramidal) blade.',
          cite=['schmidthieber2008', 'amaral2007'], cell='gc',
          lab='PTEN loss in granule cells makes them hypertrophic, with ectopic somata, hilar basal dendrites and mossy fibres sprouting back into the inner molecular layer, and is enough to cause epilepsy (Pun et al. 2012).')
    p = C.out_path('gc', s_ca3['up_node'])
    R.add('axon', 'The mossy fibre', 'Through the hilus (collaterals here feed mossy cells and interneurons), then along CA3 in stratum lucidum.',
          cite=['henze2000', 'acsady1998'], cell='gc', path=p, fiber='mf', layer=s_ca3['layer'], conn='mf_ca3')
    R.add('synapse', 'Giant bouton on a CA3 thorn',
          'The mossy fibre meets CA3 cell AA0307 (gap %.1f um, closed by %.1f um).' % (s_ca3['gap_um'], np.linalg.norm(s_ca3['shift_um'])),
          cite=['rollenhagen2007'], cell='ca3', synapse='mf_giant', layer=s_ca3['layer'], conn='mf_ca3')
    R.add('dend', 'Inward to the CA3 soma', 'Proximal apical dendrite to the cell body.', cell='ca3', path=C.in_path('ca3', s_ca3['node']))
    R.add('fire', 'The CA3 cell fires', 'CA3 pyramidal cells also excite each other through recurrent collaterals (the CA side loop ride follows one).',
          cite=['ishizuka1990'], cell='ca3')
    p = C.out_path('ca3', s_ca1['up_node'])
    R.add('axon', 'A Schaffer collateral', 'The axon arcs out of CA3 into CA1, where it runs in radiatum and oriens.',
          cite=['ishizuka1990', 'meeks2007'], cell='ca3', path=p, fiber='ca3', layer=s_ca1['layer'], conn='sc')
    R.add('synapse', 'Synapse on a CA1 dendrite',
          'The Schaffer collateral meets CA1 cell AA0306 in %s (gap %.1f um, closed by moving the CA1 cell %.0f um: within registration error).' % (s_ca1['layer'].upper(), s_ca1['gap_um'], np.linalg.norm(s_ca1['shift_um'])),
          cite=['ishizuka1990'], cell='ca1', synapse='sc_spine', layer=s_ca1['layer'], conn='sc')
    R.add('dend', 'Inward to the CA1 soma', 'From the basal dendrite in oriens to the cell body.', cell='ca1', path=C.in_path('ca1', s_ca1['node']))
    R.add('fire', 'The CA1 cell fires', 'CA1 is the main output of the hippocampus proper.', cite=['amaral1991'], cell='ca1')
    # the CA1 axon into the subiculum: the tip in SUB reached by the longest path
    c = C.c['ca1']
    from cells import path_len
    pl = path_len(c['xyz'], c['par'])
    kids = np.zeros(len(c['xyz']), int)
    for q in c['par']:
        if q >= 0:
            kids[q] += 1
    tips = np.nonzero((kids == 0) & (c['typ'] == 2))[0]
    sub_tips = [i for i in tips if lam_of(c['xyz'][i]) in ('sub', 'pros')]
    end = max(sub_tips, key=lambda i: pl[i]) if sub_tips else int(tips[int(np.argmax(pl[tips]))])
    p = C.out_path('ca1', end)
    R.add('axon', 'Out to the subiculum', 'CA1 axons run through the alveus and end in the subiculum; AA0306 puts 21 mm of axon there.',
          cite=['amaral1991'], cell='ca1', path=p, fiber='ca1', layer=lam_of(c['xyz'][end]), conn='ca1_sub')
    R.add('region', 'The loop closes in deep EC', 'The subiculum (and CA1) project to the deep layers of the entorhinal cortex, which send the result back to the neocortex and to layers II and III.',
          cite=['naber2001', 'vanstrien2009'], ms=0.0, also={'regions': ['sub', 'ec5']}, conn='sub_ec5')
    rides.append(R.out())

    # ------------------------------------------------------------------
    # 2. DS1: the lateral perforant path volley
    # ------------------------------------------------------------------
    R = Ride('ds1', 'DS1: lateral volley', 'Many LEC layer II cells fire together; their axons depolarize the outer third of the molecular layer: a sink there.', kind='event')
    R.add('fire', 'LEC layer II fires together', 'Two real LEC cells stand for the population (AA1047, AA1002).',
          cite=['bragin1995', 'winnubst2019'], cell='fan', also={'cells': ['fan_b']},
          lab='DS1: sink in the outer molecular layer, both blades (Bragin et al. 1995).')
    p = C.out_path('fan', s_gc['up_node'])
    # fan_b to its own OML terminal near the granule cell
    nb, db = C.nearest_node('fan_b', C.c['gc']['xyz'][s_gc['node']], [2])
    R.add('axon', 'The volley', 'Along the lateral perforant path, together.', cell='fan', path=p, fiber='pp', conn='lpp',
          also={'paths': {'fan_b': rnd(C.out_path('fan_b', nb))}})
    R.add('sink', 'Sink in OML', 'The outer third of the molecular layer goes negative (a current sink); the return current makes a source closer to the granule cells.',
          cite=['bragin1995', 'penttonen1997'], ms=8.0, also={'sink': ['oml1', 'oml2'], 'source': ['mml1', 'mml2', 'gcl1', 'gcl2']},
          lab='This is the profile your probe records across the dentate: the sink at OML, the source in MML and the granule layer.')
    R.add('burst', 'Hilar interneurons burst', 'Dentate spikes come with bursts of hilar interneurons (Bragin 1995).',
          cite=['bragin1995'], ms=10.0, also={'cells': ['hipp', 'pvbc', 'aac']})
    rides.append(R.out())

    # ------------------------------------------------------------------
    # 3. DS2: the medial perforant path (drawn along the atlas route)
    # ------------------------------------------------------------------
    R = Ride('ds2', 'DS2: medial volley', 'Many MEC layer II stellate cells fire together; their axons depolarize the middle third: a sink there.', kind='event')
    st = C.c['stel']
    s0 = st['xyz'][C.soma('stel')]
    # a granule-cell dendrite point in MML (the chain cell's own)
    gcx = C.c['gc']
    de = np.nonzero(np.isin(gcx['typ'], (3, 4)))[0]
    mml = [i for i in de if lam_of(gcx['xyz'][i]) in ('mml1', 'mml2')]
    tgt_i = mml[len(mml) // 2] if mml else int(de[0])
    tgt = gcx['xyz'][tgt_i]
    mpp = route25(np.array(s0, float), np.array(tgt, float), PP_COST)
    R.add('fire', 'MEC layer II stellate cells fire together',
          'A real stellate cell (slice tracing, Huang 2024) stands for the population. No public registered MEC layer II tracing has an axon, so the medial perforant path below is drawn along its route in the atlas (angular bundle, subiculum, fissure).',
          cite=['klink1997', 'bragin1995'], cell='stel', lab='DS2: sink in the middle molecular layer (Bragin et al. 1995). DS2 is usually the larger dentate spike.')
    R.add('axon', 'The medial perforant path (drawn)', 'Drawn, not traced: the cheapest route through the atlas\'s entorhinal deep layers, angular path, subiculum and fissure to MML.',
          cite=['witter2007', 'steward1976'], path=mpp, fiber='drawn', drawn=True, conn='mpp')
    R.add('sink', 'Sink in MML', 'The middle third goes negative, flanked by sources in the outer third and the granule layer.',
          cite=['bragin1995', 'penttonen1997'], ms=8.0, also={'sink': ['mml1', 'mml2'], 'source': ['oml1', 'oml2', 'gcl1', 'gcl2']})
    R.add('burst', 'Hilar interneurons burst', 'Feed-forward drive reaches basket cells too: granule-cell somata are clamped a few ms later.',
          cite=['bragin1995', 'hosp2014'], ms=10.0, also={'cells': ['hipp', 'pvbc', 'aac']})
    rides.append(R.out())

    # ------------------------------------------------------------------
    # 4. The dentate local circuit
    # ------------------------------------------------------------------
    R = Ride('dentate', 'Dentate local circuit', 'Granule cell to mossy cell to granule cells far away, and the three interneurons that answer.')
    mc = C.story('mc')
    thorn_node = mc['thorn_on'][1]
    R.add('fire', 'The granule cell fires', 'AA0573 again, in the lower blade.', cell='gc', cite=['amaral2007'])
    R.add('axon', 'A hilar collateral', 'On its way to CA3 the mossy fibre branches in the hilus.', cell='gc',
          path=C.out_path('gc', thorn_node), fiber='mf', cite=['acsady1998'], layer='hil', conn='mf_mc')
    R.add('synapse', 'On a mossy cell\'s thorn', 'The drawn mossy cell\'s thick proximal dendrite ends on this collateral.',
          cell='mc', synapse='mf_thorn_mc', layer='hil', cite=['scharfman2016'], conn='mf_mc')
    mc_soma = C.soma('mc')
    mcx = C.c['mc']
    thorn_mc_node, _ = C.nearest_node('mc', np.array(mc['thorn_um']), [3])
    R.add('dend', 'Inward to the mossy cell', 'Thorny excrescences crowd the proximal dendrites.', cell='mc', path=C.in_path('mc', thorn_mc_node))
    R.add('fire', 'The mossy cell fires', 'Mossy cells are far more active than granule cells (Senzai & Buzsaki 2017).',
          cite=['senzai2017', 'scharfman2016'], cell='mc',
          lab='Mossy cells are lost or damaged in many epilepsy models; whether the survivors excite or inhibit granule cells is the "dormant basket cell" debate (Scharfman 2016).')
    reach_node = mc['reaches'][1]
    mc_end, _ = C.nearest_node('mc', np.array(mc['reach_um']), [2])
    R.add('axon', 'To another level', 'The axon runs through the hilus and inner molecular layer, along the hippocampus, to granule cells at other levels (drawn route).',
          cell='mc', path=C.out_path('mc', mc_end), fiber='mc', drawn=True, cite=['buckmaster1996'], conn='mc_gc')
    R.add('synapse', 'On a far granule cell', 'The associational synapse: a granule cell\'s proximal dendrite in the inner molecular layer (MouseLight AA0869).',
          cell='gc_b', synapse='mc_iml', layer='iml', cite=['buckmaster1996'], conn='mc_gc')
    R.add('dend', 'Inward', 'A proximal input, close to the soma.', cell='gc_b', path=C.in_path('gc_b', int(reach_node)))
    R.add('fire', 'A granule cell elsewhere is excited', 'The dentate talks along its own length through mossy cells.', cell='gc_b', cite=['scharfman2016'])
    # feedback inhibition
    hs, ps, as_ = C.story('hipp'), C.story('pvbc'), C.story('aac')
    R.add('fire', 'The HIPP cell answers', 'Mossy-fibre collaterals also drive hilar interneurons; this SST+ HIPP cell (slice tracing, placed by its layers) fires.',
          cite=['acsady1998', 'han1993'], cell='hipp', sign='inh',
          lab='In a Kcnt1 gain-of-function mouse, non-fast-spiking interneurons such as SST+ cells are less excitable (Shore et al. 2020).')
    R.add('axon', 'Out to the distal dendrites', 'HIPP axons fill the outer two-thirds of the molecular layer.', cell='hipp',
          path=C.out_path('hipp', hs['node']), fiber='int', sign='inh', cite=['han1993'], conn='hipp_gc')
    R.add('synapse', 'Inhibition where the perforant path lands', 'On the granule cell\'s distal dendrite.', cell='gc', synapse='inh_dend', sign='inh', cite=['han1993'], conn='hipp_gc')
    R.add('fire', 'The basket cell', 'PV+ basket cell (slice tracing, placed by its layers).', cell='pvbc', sign='inh', cite=['hosp2014'])
    R.add('axon', 'To the soma', 'A dense basket in the granule layer.', cell='pvbc', path=C.out_path('pvbc', ps['node']), fiber='int', sign='inh', conn='pv_gc')
    R.add('synapse', 'Perisomatic inhibition', 'On the granule cell\'s soma.', cell='gc', synapse='inh_peri', sign='inh', cite=['freund1996'], conn='pv_gc')
    R.add('fire', 'The chandelier cell', 'Axo-axonic cell (slice tracing).', cell='aac', sign='inh', cite=['soriano1989'])
    R.add('axon', 'To the axon initial segment', 'Cartridges at the granule-layer / hilus border.', cell='aac', path=C.out_path('aac', as_['node']), fiber='int', sign='inh', conn='aac_gc')
    R.add('synapse', 'The last word', 'On the axon initial segment, where the granule cell\'s spike starts.', cell='gc', synapse='inh_ais', sign='inh', cite=['soriano1989'], conn='aac_gc')
    rides.append(R.out())

    # ------------------------------------------------------------------
    # 5. CA side loops: CA3 recurrents, the temporoammonic path, O-LM
    # ------------------------------------------------------------------
    R = Ride('caside', 'CA side loops', 'CA3 exciting CA3, entorhinal layer III straight onto CA1 tufts, and the O-LM cell that guards them.')
    s3b = C.story('ca3_b')
    R.add('fire', 'A CA3 cell fires', 'AA0307 again.', cell='ca3', cite=['ishizuka1990'])
    R.add('axon', 'A recurrent collateral', 'Back into CA3 radiatum and oriens.', cell='ca3', path=C.out_path('ca3', s3b['up_node']),
          fiber='ca3', layer=s3b['layer'], cite=['ishizuka1990'], conn='rc')
    R.add('synapse', 'On another CA3 cell', 'CA3 cell AA0304 (gap %.1f um).' % s3b['gap_um'], cell='ca3_b', synapse='rc_spine', layer=s3b['layer'], cite=['ishizuka1990'], conn='rc')
    R.add('dend', 'Inward', '', cell='ca3_b', path=C.in_path('ca3_b', s3b['node']))
    R.add('fire', 'The second CA3 cell fires', 'Pattern completion needs just this: cells that fire together, wired together.', cell='ca3_b', cite=['ishizuka1990'])
    # temporoammonic, drawn from EC layer III to the CA1 tuft
    c1 = C.c['ca1']
    de = np.nonzero(np.isin(c1['typ'], (3, 4)))[0]
    slm = [i for i in de if lam_of(c1['xyz'][i]) == 'ca1slm']
    tuft = slm[int(np.argmax([np.linalg.norm(c1['xyz'][i] - c1['xyz'][C.soma('ca1')]) for i in slm]))] if slm else int(de[-1])
    from cells import Atlas
    at = lam_of.at if hasattr(lam_of, 'at') else Atlas()
    e3 = at.voxels_of('ENTm3')
    e3 = e3[np.argmin(np.linalg.norm(e3 - s0, axis=1))]
    ta = route25(np.array(e3, float), np.array(c1['xyz'][tuft], float), PP_COST)
    R.add('fire', 'EC layer III fires', 'No public tracing of an EC layer III axon reaches CA1, so this path is drawn along its route in the atlas.',
          cite=['kitamura2014', 'vanstrien2009'], also={'regions': ['ec3']})
    R.add('axon', 'The temporoammonic path (drawn)', 'Through the angular bundle and subiculum to stratum lacunosum-moleculare.', path=ta, fiber='drawn', drawn=True, cite=['vanstrien2009'], conn='ta')
    R.add('synapse', 'On the CA1 tuft', 'Direct cortical input on the distal tuft of AA0306.', cell='ca1', synapse='ta_spine', layer='ca1slm', cite=['kitamura2014'], conn='ta')
    R.add('dend', 'Down the apical dendrite', 'A long way in: distal tuft inputs are filtered on their way to the soma.', cell='ca1', path=C.in_path('ca1', tuft))
    R.add('fire', 'The CA1 cell fires', '', cell='ca1')
    so = C.story('olm')
    # CA1 axon collateral in oriens onto the O-LM dendrite
    ox = C.c['olm']
    olm_de = np.nonzero(np.isin(ox['typ'], (3, 4)))[0]
    ca1_ax = np.nonzero(c1['typ'] == 2)[0]
    from scipy.spatial import cKDTree
    d, j = cKDTree(ox['xyz'][olm_de]).query(c1['xyz'][ca1_ax])
    k = int(np.argmin(d))
    R.add('axon', 'A local collateral in oriens', 'CA1 axons give collaterals in oriens before leaving.', cell='ca1',
          path=C.out_path('ca1', int(ca1_ax[k])), fiber='ca1', cite=['klausberger2008'], bridge_um=round(float(d[k]), 1), conn='ca1_olm')
    R.add('synapse', 'Onto the O-LM cell', 'The O-LM cell\'s horizontal dendrites in oriens (gap %.0f um, shown as a short hop).' % d[k],
          cell='olm', synapse='sc_spine', layer='ca1so', cite=['klausberger2008'], conn='ca1_olm')
    R.add('dend', 'Inward', '', cell='olm', path=C.in_path('olm', int(olm_de[j[k]])))
    R.add('fire', 'The O-LM cell fires', 'SST+ O-LM cells feed back onto the same tufts the temporoammonic path excites.', cell='olm', sign='inh',
          cite=['klausberger2008'], lab='SST+ interneurons are among the cells a Kcnt1 gain-of-function variant makes less excitable (Shore et al. 2020; 2024).')
    R.add('axon', 'Up to lacunosum-moleculare', 'Across the layers to slm.', cell='olm', path=C.out_path('olm', so['node']), fiber='int', sign='inh', conn='olm_ca1')
    R.add('synapse', 'Inhibition on the tuft', 'CA1 gates its own entorhinal input.', cell='ca1', synapse='inh_dend', sign='inh', layer='ca1slm', cite=['klausberger2008'], conn='olm_ca1')
    rides.append(R.out())

    out = {'velocity': {k: {'m_per_s': v[0], 'source': v[1]} for k, v in VELOCITY.items()},
           'delay': {k: {'ms': v[0], 'source': v[1]} for k, v in DELAY.items()},
           'synapses': SYNAPSES, 'refs': REFS, 'rides': rides,
           'note': 'Cells from different mice, aligned by registration to the Allen CCF (good to about 50-100 um). A synapse here is a close approach in that shared frame; cells were moved by the gap (listed) to close it.'}
    write_json(os.path.join(OUT, 'rides.json'), out)
    for r in rides:
        log(r['key'], len(r['steps']), 'steps', '%.1f ms' % r['total_ms'],
            [(s['kind'], s.get('cell'), s.get('len_um')) for s in r['steps'] if s.get('len_um')])
    log('rides.json', os.path.getsize(os.path.join(OUT, 'rides.json')) // 1024, 'KB')


# ----------------------------------------------------------------------
# the chain search (kept for reference; cells.py records the result)
# ----------------------------------------------------------------------
def chains():
    from survey import load, resample, MID
    from cells import Atlas
    from scipy.spatial import cKDTree
    at = Atlas()
    sv = read_json(os.path.join(RAW, 'survey.json'))
    rows = {n['neuron_name']: n for n in json.load(open(os.path.join(RAW, 'neuromorpho_catalog.json'), encoding='utf-8'))}

    def cell(name):
        xyz, typ, rad, par = load(rows[name])
        soma = xyz[typ == 1].mean(axis=0) if (typ == 1).any() else xyz[0]
        if soma[2] < MID:
            xyz = xyz.copy()
            xyz[:, 2] = 2 * MID - xyz[:, 2]
        pts, ts = resample(xyz, typ, par, step=4.0)
        return pts[ts == 2], pts[np.isin(ts, (3, 4))]

    def gap(a, b, layers):
        ok = np.zeros(256, bool)
        for l in layers:
            ok[CODE[l]] = True
        ax = a[0][ok[at.lam(a[0])]] if len(a[0]) else a[0]
        if not len(ax) or not len(b[1]):
            return None
        d, _ = cKDTree(b[1]).query(ax)
        return float(d.min())

    ml = lambda role: [k for k, v in sv.items() if not k.startswith('_') and v['archive'] == 'MouseLight' and v['role'] == role]
    gcs, ca3s, ca1s = ml('gc'), [k for k in ml('ca3') if sv[k]['axon_um'] > 5000], ml('ca1')
    C = {k: cell(k) for k in set(['AA1002', 'AA1047'] + gcs + ca3s + ca1s)}
    res = []
    for e in ('AA1002', 'AA1047'):
        for g in gcs:
            a = gap(C[e], C[g], ['oml1', 'oml2', 'mml1', 'mml2'])
            for c3 in ca3s:
                b = gap(C[g], C[c3], ['ca3slu', 'ca3sp', 'ca3sr', 'ca3so'])
                for p in ca1s:
                    d = gap(C[c3], C[p], ['ca1sr', 'ca1so'])
                    if None in (a, b, d):
                        continue
                    res.append((max(a, b, d), e, g, c3, p, [round(a, 1), round(b, 1), round(d, 1)]))
    res.sort()
    for r in res[:20]:
        print(r)


if __name__ == '__main__':
    if '--chains' in sys.argv:
        chains()
    else:
        build()
