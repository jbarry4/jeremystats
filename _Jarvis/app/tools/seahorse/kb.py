# -*- coding: utf-8 -*-
"""Seahorse knowledge base: the regions, cells, connections and pathways the
tab draws, each with its sources and the claim crosscheck.py tests.

    python tools/seahorse/kb.py         -> web/seahorse/kb.json

Every connection carries a `check`:
  {'allen': [src, tgt]}        Allen Mouse Connectivity: do injections in src
                               label axons in tgt?
  {'cell': key, 'arbor': ..., 'in': [...], 'min': f}
                               does that exemplar's arbor put at least f of
                               its length in those layers? Only evidence for
                               CCF-registered tracings; for slice tracings it
                               checks the placement, and says so.
  None                         nothing public to test it against; the tab
                               says "cited, not tested".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import OUT, write_json  # noqa: E402
from volume import DERIVED, HOW, LAMINA  # noqa: E402

REFS = {
    'amaral2007': 'Amaral DG, Scharfman HE, Lavenex P (2007) The dentate gyrus: fundamental neuroanatomical organization (dentate gyrus for dummies). Prog Brain Res 163:3-22.',
    'witter2007': 'Witter MP (2007) The perforant path: projections from the entorhinal cortex to the dentate gyrus. Prog Brain Res 163:43-61.',
    'vanstrien2009': 'van Strien NM, Cappaert NLM, Witter MP (2009) The anatomy of memory: an interactive overview of the parahippocampal-hippocampal network. Nat Rev Neurosci 10:272-282.',
    'amaralwitter1989': 'Amaral DG, Witter MP (1989) The three-dimensional organization of the hippocampal formation: a review of anatomical data. Neuroscience 31:571-591.',
    'freund1996': 'Freund TF, Buzsaki G (1996) Interneurons of the hippocampus. Hippocampus 6:347-470.',
    'klausberger2008': 'Klausberger T, Somogyi P (2008) Neuronal diversity and temporal dynamics: the unity of hippocampal circuit operations. Science 321:53-57.',
    'scharfman2016': 'Scharfman HE (2016) The enigmatic mossy cell of the dentate gyrus. Nat Rev Neurosci 17:562-575.',
    'scharfmanmyers2013': 'Scharfman HE, Myers CE (2013) Hilar mossy cells of the dentate gyrus: a historical perspective. Front Neural Circuits 6:106.',
    'amaral1978': 'Amaral DG (1978) A Golgi study of cell types in the hilar region of the hippocampus in the rat. J Comp Neurol 182:851-914.',
    'buckmaster1996': 'Buckmaster PS, Wenzel HJ, Kunkel DD, Schwartzkroin PA (1996) Axon arbors and synaptic connections of hippocampal mossy cells in the rat in vivo. J Comp Neurol 366:271-292.',
    'han1993': 'Han ZS, Buhl EH, Lorinczi Z, Somogyi P (1993) A high degree of spatial selectivity in the axonal and dendritic domains of physiologically identified local-circuit neurons in the dentate gyrus of the rat hippocampus. Eur J Neurosci 5:395-410.',
    'hosp2014': 'Hosp JA, Struber M, Yanagawa Y, Obata K, Vida I, Jonas P, Bartos M (2014) Morpho-physiological criteria divide dentate gyrus interneurons into classes. Hippocampus 24:189-203.',
    'williams2007': 'Williams PA, Larimer P, Gao Y, Strowbridge BW (2007) Semilunar granule cells: glutamatergic neurons in the rat dentate gyrus with axon collaterals in the inner molecular layer. J Neurosci 27:13756-13761.',
    'acsady1998': 'Acsady L, Kamondi A, Sik A, Freund T, Buzsaki G (1998) GABAergic cells are the major postsynaptic targets of mossy fibers in the rat hippocampus. J Neurosci 18:3386-3403.',
    'henze2000': 'Henze DA, Urban NN, Barrionuevo G (2000) The multifarious hippocampal mossy fiber pathway: a review. Neuroscience 98:407-427.',
    'soriano1989': 'Soriano E, Frotscher M (1989) A GABAergic axo-axonic cell in the fascia dentata controls the main excitatory hippocampal pathway. Brain Res 503:170-174.',
    'ishizuka1990': 'Ishizuka N, Weber J, Amaral DG (1990) Organization of intrahippocampal projections originating from CA3 pyramidal cells in the rat. J Comp Neurol 295:580-623.',
    'steward1976': 'Steward O (1976) Topographic organization of the projections from the entorhinal area to the hippocampal formation of the rat. J Comp Neurol 167:285-314.',
    'hjorth1972': 'Hjorth-Simonsen A, Jeune B (1972) Origin and termination of the hippocampal perforant path in the rat studied by silver impregnation. J Comp Neurol 144:215-232.',
    'tamamaki1993': 'Tamamaki N, Nojyo Y (1993) Projection of the entorhinal layer II neurons in the rat as revealed by intracellular pressure-injection of neurobiotin. Hippocampus 3:471-480.',
    'klink1997': 'Klink R, Alonso A (1997) Morphological characteristics of layer II projection neurons in the rat medial entorhinal cortex. Hippocampus 7:571-583.',
    'leitner2016': 'Leitner FC, Melzer S, Lutcke H, Pinna R, Seeburg PH, Helmchen F, Monyer H (2016) Spatially segregated feedforward and feedback neurons support differential odor processing in the lateral entorhinal cortex. Nat Neurosci 19:935-944.',
    'kitamura2014': 'Kitamura T, Pignatelli M, Suh J, Kohara K, Yoshiki A, Abe K, Tonegawa S (2014) Island cells control temporal association memory. Science 343:896-901.',
    'chevaleyre2010': 'Chevaleyre V, Siegelbaum SA (2010) Strong CA2 pyramidal neuron synapses define a powerful disynaptic cortico-hippocampal loop. Neuron 66:560-572.',
    'kohara2014': 'Kohara K, Pignatelli M, Rivest AJ, et al. (2014) Cell type-specific genetic and optogenetic tools reveal hippocampal CA2 circuits. Nat Neurosci 17:269-279.',
    'amaral1991': 'Amaral DG, Dolorfo C, Alvarez-Royo P (1991) Organization of CA1 projections to the subiculum: a PHA-L analysis in the rat. Hippocampus 1:415-435.',
    'naber2001': 'Naber PA, Lopes da Silva FH, Witter MP (2001) Reciprocal connections between the entorhinal cortex and hippocampal fields CA1 and the subiculum are in register with the projections from CA1 to the subiculum. Hippocampus 11:99-104.',
    'burwell2000': 'Burwell RD (2000) The parahippocampal region: corticocortical connectivity. Ann N Y Acad Sci 911:25-42.',
    'bragin1995': 'Bragin A, Jando G, Nadasdy Z, van Landeghem M, Buzsaki G (1995) Dentate EEG spikes and associated interneuronal population bursts in the hippocampal hilar region of the rat. J Neurophysiol 73:1691-1705.',
    'penttonen1997': 'Penttonen M, Kamondi A, Sik A, Acsady L, Buzsaki G (1997) Feed-forward and feed-back activation of the dentate gyrus in vivo during dentate spikes and sharp wave bursts. Hippocampus 7:437-450.',
    'dvorak2021': 'Dvorak D, Chung A, Park EH, Fenton AA (2021) Dentate spikes and external control of hippocampal function. Cell Rep 36:109497.',
    'senzai2017': 'Senzai Y, Buzsaki G (2017) Physiological properties and behavioral correlates of hippocampal granule cells and mossy cells. Neuron 93:691-704.',
    'wang2020': 'Wang Q, Ding SL, Li Y, et al. (2020) The Allen Mouse Brain Common Coordinate Framework: a 3D reference atlas. Cell 181:936-953.',
    'oh2014': 'Oh SW, Harris JA, Ng L, et al. (2014) A mesoscale connectome of the mouse brain. Nature 508:207-214.',
    'winnubst2019': 'Winnubst J, Bas E, Ferreira TA, et al. (2019) Reconstruction of 1,000 projection neurons reveals new cell types and organization of long-range connectivity in the mouse brain. Cell 179:268-281.',
    'peng2021': 'Peng H, Xie P, Liu L, et al. (2021) Morphological diversity of single neurons in molecularly defined cell types. Nature 598:174-181.',
    'ascoli2007': 'Ascoli GA, Donohue DE, Halavi M (2007) NeuroMorpho.Org: a central resource for neuronal morphologies. J Neurosci 27:9247-9251.',
    'wheeler2015': 'Wheeler DW, White CM, Rees CL, Komendantov AO, Hamilton DJ, Ascoli GA (2015) Hippocampome.org: a knowledge base of neuron types in the rodent hippocampus. eLife 4:e09960.',
    'buzsaki2002': 'Buzsaki G (2002) Theta oscillations in the hippocampus. Neuron 33:325-340.',
    'buzsaki2015': 'Buzsaki G (2015) Hippocampal sharp wave-ripple: a cognitive biomarker for episodic memory and planning. Hippocampus 25:1073-1188.',
    'ylinen1995': 'Ylinen A, Bragin A, Nadasdy Z, Jando G, Szabo I, Sik A, Buzsaki G (1995) Sharp wave-associated high-frequency oscillation (200 Hz) in the intact hippocampus: network and intracellular mechanisms. J Neurosci 15:30-46.',
    'wongtraub1983': 'Wong RKS, Traub RD (1983) Synchronized burst discharge in disinhibited hippocampal slice. I. Initiation in CA2-CA3 region. J Neurophysiol 49:442-458.',
    'nicholson1975': 'Nicholson C, Freeman JA (1975) Theory of current source-density analysis and determination of conductivity tensor for anuran cerebellum. J Neurophysiol 38:356-368.',
    'kempermann1997': 'Kempermann G, Kuhn HG, Gage FH (1997) Genetic influence on neurogenesis in the dentate gyrus of adult mice. Proc Natl Acad Sci USA 94:10409-10414.',
    'goodsmith2017': 'GoodSmith D, Chen X, Wang C, et al. (2017) Spatial representations of granule cells and mossy cells of the dentate gyrus. Neuron 93:677-690.',
    'danielson2017': 'Danielson NB, Turi GF, Ladow M, et al. (2017) In vivo imaging of dentate gyrus mossy cells in behaving mice. Neuron 93:552-559.',
    'larimer2010': 'Larimer P, Strowbridge BW (2010) Representing information in cell assemblies: persistent activity mediated by semilunar granule cells. Nat Neurosci 13:213-222.',
    'alonsollinas1989': 'Alonso A, Llinas RR (1989) Subthreshold Na+-dependent theta-like rhythmicity in stellate cells of entorhinal cortex layer II. Nature 342:175-177.',
    'hafting2005': 'Hafting T, Fyhn M, Molden S, Moser MB, Moser EI (2005) Microstructure of a spatial map in the entorhinal cortex. Nature 436:801-806.',
    'tsao2018': 'Tsao A, Sugar J, Lu L, et al. (2018) Integrating time from experience in the lateral entorhinal cortex. Nature 561:57-62.',
    'okeefe1993': 'O\'Keefe J, Recce ML (1993) Phase relationship between hippocampal place units and the EEG theta rhythm. Hippocampus 3:317-330.',
    'klausberger2003': 'Klausberger T, Magill PJ, Marton LF, et al. (2003) Brain-state- and cell-type-specific firing of hippocampal interneurons in vivo. Nature 421:844-848.',
    'bartos2007': 'Bartos M, Vida I, Jonas P (2007) Synaptic mechanisms of synchronized gamma oscillations in inhibitory interneuron networks. Nat Rev Neurosci 8:45-56.',
    'pun2012': 'Pun RYK, Rolle IJ, LaSarge CL, et al. (2012) Excessive activation of mTOR in postnatally generated granule cells is sufficient to cause epilepsy. Neuron 75:1022-1034.',
    'shore2020': 'Shore AN, Colombo S, Tobin WF, et al. (2020) Reduced GABAergic neuron excitability, altered synaptic connectivity, and seizures in a KCNT1 gain-of-function mouse model of childhood epilepsy. Cell Rep 33:108303.',
    'lomo1971': 'Lomo T (1971) Patterns of activation in a monosynaptic cortical pathway: the perforant path input to the dentate area of the hippocampal formation. Exp Brain Res 12:18-45.',
    'schmidthieber2008': 'Schmidt-Hieber C, Jonas P, Bischofberger J (2008) Action potential initiation and propagation in hippocampal mossy fibre axons. J Physiol 586:1849-1857.',
    'meeks2007': 'Meeks JP, Mennerick S (2007) Action potential initiation and propagation in CA3 pyramidal axons. J Neurophysiol 97:3460-3472.',
    'rollenhagen2007': 'Rollenhagen A, Satzler K, Rodriguez EP, Jonas P, Frotscher M, Lubke JHR (2007) Structural determinants of transmission at large hippocampal mossy fiber synapses. J Neurosci 27:10434-10444.',
}

# ----- regions (the boxes of the circuit schematic) -----
# pos: x, y on a 1000 x 640 canvas.  allen: what to light in 3D / slices.
REGIONS = [
    {'key': 'ctx', 'label': 'Neocortex', 'sub': 'association areas', 'allen': ['Isocortex'], 'pos': [500, 40], 'w': 820},
    {'key': 'per', 'label': 'Perirhinal', 'sub': 'PERI (+ ECT) to LEC', 'allen': ['PERI', 'ECT'], 'pos': [165, 140]},
    {'key': 'por', 'label': 'Postrhinal', 'sub': 'POR (VISpor) to MEC', 'allen': ['VISpor'], 'pos': [375, 140]},
    {'key': 'lec2', 'label': 'LEC layer II', 'sub': 'fan cells', 'allen': ['ENTl2'], 'pos': [120, 255], 'cells': ['fan']},
    {'key': 'mec2', 'label': 'MEC layer II', 'sub': 'stellate cells', 'allen': ['ENTm2'], 'pos': [120, 330], 'cells': ['stel']},
    {'key': 'ec3', 'label': 'EC layer III', 'sub': 'pyramidal cells', 'allen': ['ENTl3', 'ENTm3'], 'pos': [120, 405]},
    {'key': 'ec5', 'label': 'EC layers V-VI', 'sub': 'deep', 'allen': ['ENTl5', 'ENTm5'], 'pos': [120, 520]},
    {'key': 'dg', 'label': 'Dentate gyrus', 'sub': 'GC, MC, HIPP, PV+ BC, AAC', 'allen': ['DG'], 'pos': [395, 300],
     'cells': ['gc', 'sgc', 'mc', 'hipp', 'pvbc', 'aac']},
    {'key': 'ca3', 'label': 'CA3', 'sub': 'pyramidal cells', 'allen': ['CA3'], 'pos': [610, 300], 'cells': ['ca3']},
    {'key': 'ca2', 'label': 'CA2', 'sub': 'pyramidal cells', 'allen': ['CA2'], 'pos': [800, 230]},
    {'key': 'ca1', 'label': 'CA1', 'sub': 'pyramidal cells, O-LM', 'allen': ['CA1'], 'pos': [850, 400], 'cells': ['ca1', 'olm']},
    {'key': 'sub', 'label': 'Subiculum', 'sub': 'SUB + ProS', 'allen': ['SUB', 'ProS'], 'pos': [620, 520]},
    {'key': 'prepar', 'label': 'Pre- & parasubiculum', 'sub': 'PRE, POST, PAR', 'allen': ['PRE', 'POST', 'PAR'], 'pos': [420, 600]},
    {'key': 'subc', 'label': 'Subcortical targets', 'sub': 'via fimbria-fornix', 'allen': ['fi'], 'pos': [850, 600]},
]

# ----- cells -----
CELLS = [
    {'key': 'gc', 'label': 'Granule cell', 'short': 'GC', 'color': '#2a9d8f', 'region': 'dg', 'sign': 'exc',
     'soma': 'GCL', 'dend': 'molecular layer (IML, MML, OML), cone-shaped, spiny',
     'axon': 'mossy fiber: collaterals in the hilus, then stratum lucidum of CA3 with giant boutons',
     'markers': 'Prox1, Calbindin', 'about': 'The principal cell of the dentate. Very sparse firing; reads the perforant path on its spines and passes a sparse code to CA3 through some of the largest synapses in the brain.',
     'refs': ['amaral2007', 'henze2000', 'acsady1998']},
    {'key': 'sgc', 'label': 'Semilunar granule cell', 'short': 'SGC', 'color': '#7fd1c7', 'region': 'dg', 'sign': 'exc',
     'soma': 'inner molecular layer', 'dend': 'wide, half-moon fan through the molecular layer',
     'axon': 'like a GC: hilus and CA3, plus IML collaterals', 'markers': '(excitatory; no unique marker)',
     'about': 'A granule-cell relative with its soma out in the inner molecular layer and a broad dendritic fan. Persistent firing after perforant-path input; drives hilar cells.',
     'refs': ['williams2007']},
    {'key': 'mc', 'label': 'Mossy cell', 'short': 'MC', 'color': '#6ab04c', 'region': 'dg', 'sign': 'exc',
     'soma': 'hilus', 'dend': 'thick, mostly in the hilus, covered proximally in thorny excrescences (where mossy-fiber boutons land)',
     'axon': 'to the inner molecular layer, mostly at other septotemporal levels and the other side (associational/commissural)',
     'markers': 'GluR2/3, calretinin (ventral, in mouse)',
     'about': 'The excitatory cell of the hilus. Takes mossy-fiber input on its thorns and feeds it back to granule cells (and interneurons) far along the hippocampus, landing on the proximal dendrites in the IML.',
     'refs': ['scharfman2016', 'scharfmanmyers2013', 'buckmaster1996', 'amaral1978', 'senzai2017']},
    {'key': 'hipp', 'label': 'HIPP cell', 'short': 'HIPP', 'color': '#8e6bbf', 'region': 'dg', 'sign': 'inh',
     'soma': 'hilus', 'dend': 'in the hilus, spiny', 'axon': 'outer two-thirds of the molecular layer, where the perforant path lands',
     'markers': 'SST+ (somatostatin), NPY',
     'about': 'Hilar Perforant-Path-associated interneuron. Inhibits granule-cell distal dendrites right where the entorhinal input arrives: feedback inhibition of the perforant-path synapse.',
     'refs': ['han1993', 'freund1996', 'hosp2014']},
    {'key': 'pvbc', 'label': 'PV+ basket cell', 'short': 'PV+ BC', 'color': '#e9a23b', 'region': 'dg', 'sign': 'inh',
     'soma': 'granule cell layer / hilus border', 'dend': 'up through the molecular layer and down into the hilus',
     'axon': 'basket of terminals around granule-cell somata in the GCL', 'markers': 'PV+ (parvalbumin), fast-spiking',
     'about': 'Perisomatic inhibition: wraps granule-cell bodies in terminals. Fed forward by the perforant path and back by granule cells; sets the timing of granule-cell output.',
     'refs': ['freund1996', 'hosp2014', 'acsady1998']},
    {'key': 'aac', 'label': 'Axo-axonic cell', 'short': 'AAC', 'color': '#e76f51', 'region': 'dg', 'sign': 'inh',
     'soma': 'granule cell layer / hilus border', 'dend': 'through the molecular layer',
     'axon': 'cartridges on granule-cell axon initial segments at the GCL-hilus border', 'markers': 'PV+ (most)',
     'about': 'Chandelier cell. Its terminals line up on the axon initial segments of granule cells: the last word on whether a granule cell fires.',
     'refs': ['soriano1989', 'freund1996']},
    {'key': 'stel', 'label': 'MEC stellate cell', 'short': 'ECII M', 'color': '#3d7dd8', 'region': 'mec2', 'sign': 'exc',
     'soma': 'MEC layer II', 'dend': 'several primary dendrites spreading in layers I-II',
     'axon': 'medial perforant path: middle molecular layer of the DG, and CA3 slm', 'markers': 'Reelin',
     'about': 'Grid-cell territory. Layer II stellate cells of the medial entorhinal cortex give the medial perforant path, which lands on the middle third of the dentate molecular layer.',
     'refs': ['klink1997', 'tamamaki1993', 'witter2007']},
    {'key': 'fan', 'label': 'LEC fan cell', 'short': 'ECII L', 'color': '#d16ba5', 'region': 'lec2', 'sign': 'exc',
     'soma': 'LEC layer II (IIa)', 'dend': 'fan of dendrites up into layer I, little basal tree',
     'axon': 'lateral perforant path: outer molecular layer of the DG, and CA3 slm', 'markers': 'Reelin',
     'about': 'The object/context side of the entorhinal cortex. Layer IIa fan cells of the lateral entorhinal cortex give the lateral perforant path, which lands on the outer third of the molecular layer.',
     'refs': ['leitner2016', 'witter2007', 'tamamaki1993']},
    {'key': 'ca3', 'label': 'CA3 pyramidal cell', 'short': 'CA3 PC', 'color': '#b8323c', 'region': 'ca3', 'sign': 'exc',
     'soma': 'CA3 stratum pyramidale', 'dend': 'basal in oriens, apical through lucidum (mossy-fiber thorns), radiatum and lacunosum-moleculare',
     'axon': 'recurrent collaterals in CA3, Schaffer collaterals to CA1 radiatum/oriens, commissural to the other side; some back to the hilus',
     'markers': '', 'about': 'The recurrent network. Takes mossy fibers proximally, its own collaterals in the middle, and entorhinal input distally; sends Schaffer collaterals to CA1.',
     'refs': ['ishizuka1990', 'amaralwitter1989']},
    {'key': 'ca1', 'label': 'CA1 pyramidal cell', 'short': 'CA1 PC', 'color': '#c2185b', 'region': 'ca1', 'sign': 'exc',
     'soma': 'CA1 stratum pyramidale', 'dend': 'basal in oriens, apical through radiatum (Schaffer input) to a tuft in lacunosum-moleculare (EC layer III input)',
     'axon': 'through the alveus to the subiculum and deep entorhinal cortex', 'markers': '',
     'about': 'The main output of the hippocampus proper. Compares CA3 input in radiatum with direct entorhinal input in lacunosum-moleculare.',
     'refs': ['amaral1991', 'naber2001', 'klausberger2008']},
    {'key': 'olm', 'label': 'O-LM cell', 'short': 'O-LM', 'color': '#5c6bc0', 'region': 'ca1', 'sign': 'inh',
     'soma': 'CA1 stratum oriens', 'dend': 'horizontal in oriens', 'axon': 'up across the layers to lacunosum-moleculare',
     'markers': 'SST+ (somatostatin), Chrna2',
     'about': 'Oriens-lacunosum moleculare cell. Driven by CA1 pyramidal cells, inhibits their distal tufts where the entorhinal input lands: the CA1 counterpart of the HIPP cell.',
     'refs': ['klausberger2008', 'freund1996']},
]

PHYS = {'gc': [('Sparse: in a given place most granule cells are silent; active ones fire at low rates.', ['senzai2017', 'goodsmith2017']), ('The spike starts in the axon 20-30 um from the soma and runs down the mossy fibre at about 0.24 m/s.', ['schmidthieber2008'])], 'sgc': [('Fire persistently for seconds after a perforant-path input, unlike granule cells.', ['larimer2010'])], 'mc': [('Much more active than granule cells, with several place fields each.', ['senzai2017', 'goodsmith2017', 'danielson2017'])], 'hipp': [('A regular-spiking (non-fast-spiking) SST+ cell that inhibits the distal dendrites.', ['hosp2014'])], 'pvbc': [('Fast-spiking: hundreds of spikes a second without slowing; paces gamma and times granule-cell output.', ['bartos2007', 'hosp2014'])], 'aac': [('Fast-spiking PV+ cell whose synapses sit on the axon initial segment.', ['freund1996'])], 'stel': [('Many are grid cells; theta-frequency membrane oscillations in vitro.', ['hafting2005', 'alonsollinas1989'])], 'fan': [('Lateral entorhinal cells signal objects, odors and elapsed time.', ['leitner2016', 'tsao2018'])], 'ca3': [('Burst-firing place cells; CA3 population bursts start sharp-wave ripples.', ['buzsaki2015'])], 'ca1': [('Place cells that shift their spikes earlier in each theta cycle as an animal crosses the field (phase precession).', ['okeefe1993']), ('Fire together during sharp-wave ripples, replaying recent paths.', ['buzsaki2015'])], 'olm': [('Fire at the trough of CA1 theta and fall silent during ripples.', ['klausberger2003'])]}
LAB = {'gc': ('PTEN loss in granule cells makes them hypertrophic, with ectopic somata, hilar basal dendrites and mossy fibres sprouting into the inner molecular layer, and is enough to cause epilepsy.', ['pun2012']), 'hipp': ('A Kcnt1 gain-of-function variant makes non-fast-spiking GABAergic neurons less excitable (cortex).', ['shore2020']), 'olm': ('SST+ cells are among the non-fast-spiking interneurons a Kcnt1 gain-of-function variant makes less excitable.', ['shore2020']), 'fan': ('A synchronous LEC layer II volley onto the outer molecular layer is DS1.', ['bragin1995']), 'stel': ('A synchronous MEC layer II volley onto the middle molecular layer is DS2.', ['bragin1995'])}
LINE = {'gc': "The dentate's principal cell: sparse firing, giant mossy-fibre synapses onto CA3.", 'sgc': 'A granule-cell relative with its soma out in the inner molecular layer.', 'mc': "The hilus's excitatory cell: takes mossy fibres, feeds granule cells far away.", 'hipp': 'SST+ interneuron of the hilus; inhibits where the perforant path lands.', 'pvbc': 'PV+ basket cell: perisomatic inhibition of granule cells.', 'aac': 'Chandelier cell: inhibition on the axon initial segment.', 'stel': 'MEC layer II stellate cell: the medial perforant path (DS2).', 'fan': 'LEC layer II cell: the lateral perforant path (DS1).', 'ca3': 'CA3 pyramidal cell: mossy-fibre input, recurrent network, Schaffer output.', 'ca1': 'CA1 pyramidal cell: the main output of the hippocampus proper.', 'olm': 'SST+ O-LM interneuron: inhibits CA1 tufts in lacunosum-moleculare.'}
for _c in CELLS:
    _c['phys'] = [{'text': t, 'refs': r} for t, r in PHYS.get(_c['key'], [])]
    if _c['key'] in LAB:
        _c['lab'] = {'text': LAB[_c['key']][0], 'refs': LAB[_c['key']][1]}
    _c['line'] = LINE.get(_c['key'], '')

LAYERS_DG = ['oml1', 'mml1', 'iml1', 'gcl1', 'hil', 'gcl2', 'iml2', 'mml2', 'oml2']

# ----- connections -----
# kind: 'region' (box to box) or 'cell'. dash: drawn dashed in the schematic.
CONNECTIONS = [
    # cortex to parahippocampal
    {'key': 'ctx_per', 'from': 'ctx', 'to': 'per', 'kind': 'region', 'sign': 'exc', 'label': 'unimodal + polymodal input',
     'refs': ['burwell2000'], 'check': {'allen': ['TEa', 'PERI']}},
    {'key': 'ctx_por', 'from': 'ctx', 'to': 'por', 'kind': 'region', 'sign': 'exc', 'label': 'visuospatial input',
     'refs': ['burwell2000'], 'check': {'allen': ['VISp', 'VISpor']}},
    {'key': 'per_lec', 'from': 'per', 'to': 'lec2', 'kind': 'region', 'sign': 'exc', 'label': 'perirhinal to LEC',
     'refs': ['burwell2000', 'vanstrien2009'], 'check': {'allen': ['PERI', 'ENTl']}},
    {'key': 'por_mec', 'from': 'por', 'to': 'mec2', 'kind': 'region', 'sign': 'exc', 'label': 'postrhinal to MEC',
     'refs': ['burwell2000', 'vanstrien2009'], 'check': {'allen': ['VISpor', 'ENTm']}},
    # perforant path
    {'key': 'lpp', 'from': 'fan', 'to': 'gc', 'kind': 'cell', 'regions': ['lec2', 'dg'], 'sign': 'exc',
     'label': 'lateral perforant path', 'layer': ['oml1', 'oml2'],
     'about': 'LEC layer II to the outer third of the molecular layer, on granule-cell distal dendrites. The current sink of DS1.',
     'refs': ['hjorth1972', 'steward1976', 'witter2007', 'bragin1995'], 'check': {'allen': ['ENTl', 'DG-mo']}},
    {'key': 'mpp', 'from': 'stel', 'to': 'gc', 'kind': 'cell', 'regions': ['mec2', 'dg'], 'sign': 'exc',
     'label': 'medial perforant path', 'layer': ['mml1', 'mml2'],
     'about': 'MEC layer II to the middle third of the molecular layer. The current sink of DS2.',
     'refs': ['hjorth1972', 'steward1976', 'witter2007', 'bragin1995'], 'check': {'allen': ['ENTm', 'DG-mo']}},
    {'key': 'pp_ca3', 'from': 'mec2', 'to': 'ca3', 'kind': 'region', 'sign': 'exc', 'label': 'EC II to CA3 slm',
     'layer': ['ca3slm'], 'refs': ['witter2007', 'vanstrien2009'], 'check': {'allen': ['ENTm', 'CA3']}},
    {'key': 'pp_ca2', 'from': 'mec2', 'to': 'ca2', 'kind': 'region', 'sign': 'exc', 'label': 'EC II to CA2',
     'layer': ['ca2slm'], 'refs': ['chevaleyre2010', 'kohara2014'], 'check': {'allen': ['ENTm', 'CA2']}},
    {'key': 'ta', 'from': 'ec3', 'to': 'ca1', 'kind': 'region', 'sign': 'exc', 'label': 'temporoammonic (EC III to CA1)',
     'layer': ['ca1slm'], 'dash': True, 'refs': ['kitamura2014', 'naber2001', 'vanstrien2009'], 'check': {'allen': ['ENTl', 'CA1']}},
    {'key': 'ec3_sub', 'from': 'ec3', 'to': 'sub', 'kind': 'region', 'sign': 'exc', 'label': 'EC III to subiculum',
     'dash': True, 'refs': ['naber2001'], 'check': {'allen': ['ENTm', 'SUB']}},
    # feed-forward inhibition in DG
    {'key': 'pp_pv', 'from': 'stel', 'to': 'pvbc', 'kind': 'cell', 'regions': ['mec2', 'dg'], 'sign': 'exc',
     'label': 'feed-forward drive to basket cells', 'layer': ['mml1', 'oml1'], 'refs': ['freund1996', 'hosp2014'], 'check': None},
    # dentate microcircuit
    {'key': 'mf_ca3', 'from': 'gc', 'to': 'ca3', 'kind': 'cell', 'regions': ['dg', 'ca3'], 'sign': 'exc',
     'label': 'mossy fibers', 'layer': ['ca3slu'],
     'about': 'Granule-cell axons to CA3 stratum lucidum: giant, detonator-like boutons on the thorns of CA3 pyramidal cells.',
     'refs': ['henze2000', 'acsady1998', 'amaral2007'],
     'check': {'cell': 'gc', 'arbor': 'axon', 'in': ['ca3so', 'ca3sp', 'ca3slu', 'ca3sr', 'CA3'], 'min': 0.25}},
    {'key': 'mf_mc', 'from': 'gc', 'to': 'mc', 'kind': 'cell', 'regions': ['dg'], 'sign': 'exc',
     'label': 'mossy-fiber collaterals', 'layer': ['hil'],
     'about': 'On the way to CA3, mossy fibers branch in the hilus and land on mossy-cell thorny excrescences.',
     'refs': ['acsady1998', 'scharfman2016'], 'check': {'cell': 'gc', 'arbor': 'axon', 'in': ['hil'], 'min': 0.10}},
    {'key': 'mf_int', 'from': 'gc', 'to': 'hipp', 'kind': 'cell', 'regions': ['dg'], 'sign': 'exc',
     'label': 'mossy fibers to hilar interneurons', 'layer': ['hil'],
     'about': 'Most mossy-fiber synapses are on interneurons (small en-passant boutons and filopodia), not on mossy cells or CA3.',
     'refs': ['acsady1998'], 'check': None},
    {'key': 'gc_pv', 'from': 'gc', 'to': 'pvbc', 'kind': 'cell', 'regions': ['dg'], 'sign': 'exc',
     'label': 'feedback drive to basket cells', 'layer': ['hil'], 'refs': ['acsady1998'], 'check': None},
    {'key': 'mc_gc', 'from': 'mc', 'to': 'gc', 'kind': 'cell', 'regions': ['dg'], 'sign': 'exc',
     'label': 'associational/commissural', 'layer': ['iml1', 'iml2'],
     'about': 'Mossy-cell axons to the inner molecular layer: granule-cell proximal dendrites, mostly at other levels and on the other side.',
     'refs': ['buckmaster1996', 'scharfman2016', 'amaral2007'], 'check': None},
    {'key': 'mc_int', 'from': 'mc', 'to': 'pvbc', 'kind': 'cell', 'regions': ['dg'], 'sign': 'exc',
     'label': 'mossy cells to interneurons', 'layer': ['hil', 'iml1'], 'refs': ['scharfman2016'], 'check': None},
    {'key': 'hipp_gc', 'from': 'hipp', 'to': 'gc', 'kind': 'cell', 'regions': ['dg'], 'sign': 'inh',
     'label': 'HIPP to distal dendrites', 'layer': ['oml1', 'mml1', 'oml2', 'mml2'],
     'about': 'SST+ HIPP axons inhibit granule-cell distal dendrites in the outer two-thirds, in register with the perforant path.',
     'refs': ['han1993', 'freund1996'],
     'check': {'cell': 'hipp', 'arbor': 'axon', 'in': ['oml1', 'mml1', 'oml2', 'mml2'], 'min': 0.30}},
    {'key': 'pv_gc', 'from': 'pvbc', 'to': 'gc', 'kind': 'cell', 'regions': ['dg'], 'sign': 'inh',
     'label': 'perisomatic inhibition', 'layer': ['gcl1', 'gcl2'],
     'refs': ['freund1996', 'hosp2014'], 'check': {'cell': 'pvbc', 'arbor': 'axon', 'in': ['gcl1', 'gcl2'], 'min': 0.5}},
    {'key': 'aac_gc', 'from': 'aac', 'to': 'gc', 'kind': 'cell', 'regions': ['dg'], 'sign': 'inh',
     'label': 'axon initial segments', 'layer': ['gcl1', 'hil'],
     'refs': ['soriano1989'], 'check': {'cell': 'aac', 'arbor': 'axon', 'in': ['gcl1', 'gcl2', 'hil'], 'min': 0.5}},
    {'key': 'sgc_hil', 'from': 'sgc', 'to': 'mc', 'kind': 'cell', 'regions': ['dg'], 'sign': 'exc',
     'label': 'semilunar granule cells to hilar cells', 'layer': ['hil'],
     'refs': ['williams2007'], 'check': {'cell': 'sgc', 'arbor': 'axon', 'in': ['hil', 'ca3slu', 'ca3sp'], 'min': 0.2}},
    # CA3, CA2, CA1
    {'key': 'rc', 'from': 'ca3', 'to': 'ca3', 'kind': 'cell', 'regions': ['ca3'], 'sign': 'exc',
     'label': 'recurrent collaterals', 'layer': ['ca3sr', 'ca3so'], 'refs': ['ishizuka1990'],
     'check': {'cell': 'ca3', 'arbor': 'axon', 'in': ['ca3so', 'ca3sr', 'ca3sp', 'ca3slu', 'CA3'], 'min': 0.05}},
    {'key': 'sc', 'from': 'ca3', 'to': 'ca1', 'kind': 'cell', 'regions': ['ca3', 'ca1'], 'sign': 'exc',
     'label': 'Schaffer collaterals', 'layer': ['ca1sr', 'ca1so'], 'refs': ['ishizuka1990', 'amaralwitter1989'],
     'check': {'cell': 'ca3', 'arbor': 'axon', 'in': ['ca1so', 'ca1sr', 'ca1sp', 'ca1slm', 'CA1'], 'min': 0.3}},
    {'key': 'sc_allen', 'from': 'ca3', 'to': 'ca1', 'kind': 'region', 'sign': 'exc', 'label': 'CA3 to CA1 (population)',
     'refs': ['ishizuka1990'], 'check': {'allen': ['CA3', 'CA1']}, 'hidden': True},
    {'key': 'back', 'from': 'ca3', 'to': 'mc', 'kind': 'cell', 'regions': ['ca3', 'dg'], 'sign': 'exc',
     'label': 'CA3 back-projection to the hilus', 'layer': ['hil'], 'dash': True,
     'refs': ['ishizuka1990', 'scharfman2016'], 'check': None},
    {'key': 'ca2_ca1', 'from': 'ca2', 'to': 'ca1', 'kind': 'region', 'sign': 'exc', 'label': 'CA2 to CA1 oriens',
     'layer': ['ca1so'], 'refs': ['chevaleyre2010', 'kohara2014'], 'check': {'allen': ['CA2', 'CA1']}},
    {'key': 'ca1_olm', 'from': 'ca1', 'to': 'olm', 'kind': 'cell', 'regions': ['ca1'], 'sign': 'exc',
     'label': 'feedback to O-LM', 'layer': ['ca1so'], 'refs': ['klausberger2008'],
     'check': {'cell': 'ca1', 'arbor': 'axon', 'in': ['ca1so', 'alv'], 'min': 0.1}},
    {'key': 'olm_ca1', 'from': 'olm', 'to': 'ca1', 'kind': 'cell', 'regions': ['ca1'], 'sign': 'inh',
     'label': 'O-LM to distal tufts', 'layer': ['ca1slm'], 'refs': ['klausberger2008', 'freund1996'],
     'check': {'cell': 'olm', 'arbor': 'axon', 'in': ['ca1slm'], 'min': 0.4}},
    # output
    {'key': 'ca1_sub', 'from': 'ca1', 'to': 'sub', 'kind': 'region', 'sign': 'exc', 'label': 'CA1 to subiculum',
     'refs': ['amaral1991'], 'check': {'allen': ['CA1', 'SUB']}},
    {'key': 'ca1_ec5', 'from': 'ca1', 'to': 'ec5', 'kind': 'region', 'sign': 'exc', 'label': 'CA1 to deep EC',
     'refs': ['naber2001', 'vanstrien2009'], 'check': {'allen': ['CA1', 'ENTl']}},
    {'key': 'sub_ec5', 'from': 'sub', 'to': 'ec5', 'kind': 'region', 'sign': 'exc', 'label': 'loop closes in deep EC',
     'refs': ['naber2001', 'vanstrien2009'], 'check': {'allen': ['SUB', 'ENTm']}},
    {'key': 'sub_pre', 'from': 'sub', 'to': 'prepar', 'kind': 'region', 'sign': 'exc', 'label': 'to pre- and parasubiculum',
     'refs': ['vanstrien2009'], 'check': {'allen': ['SUB', 'PRE']}},
    {'key': 'sub_subc', 'from': 'sub', 'to': 'subc', 'kind': 'region', 'sign': 'exc', 'label': 'fimbria-fornix',
     'refs': ['vanstrien2009'], 'check': {'allen': ['SUB', 'MBO']}},
    {'key': 'pre_mec', 'from': 'prepar', 'to': 'ec3', 'kind': 'region', 'sign': 'exc', 'label': 'presubiculum to MEC III',
     'refs': ['vanstrien2009'], 'check': {'allen': ['PRE', 'ENTm']}},
    {'key': 'ec5_ec2', 'from': 'ec5', 'to': 'ec3', 'kind': 'region', 'sign': 'exc', 'label': 'deep to superficial EC',
     'dash': True, 'refs': ['vanstrien2009'], 'check': None},
    {'key': 'ec5_ctx', 'from': 'ec5', 'to': 'ctx', 'kind': 'region', 'sign': 'exc', 'label': 'back to neocortex',
     'refs': ['vanstrien2009'], 'check': {'allen': ['ENTl', 'PERI']}},
]

# ----- pathways (the tracer) -----
# Each hop names a connection (or a cell / region to light) and says what
# happens there, in plain words.
PATHWAYS = [
    {'key': 'trisynaptic', 'label': 'Trisynaptic loop', 'blurb': 'The classic route from entorhinal cortex through all three hippocampal stages and back out.',
     'hops': [
         {'at': 'stel', 'say': 'MEC layer II stellate cells fire.'},
         {'via': 'mpp', 'say': 'The medial perforant path crosses the hippocampal fissure and lands on the middle third of the dentate molecular layer.'},
         {'at': 'gc', 'say': 'A few granule cells reach threshold: the dentate is a sparse, pattern-separating gate.'},
         {'via': 'mf_ca3', 'say': 'Mossy fibers run through the hilus into CA3 stratum lucidum: one giant bouton can fire a CA3 cell.'},
         {'at': 'ca3', 'say': 'CA3 pyramidal cells; their recurrent collaterals let the network complete a pattern.'},
         {'via': 'sc', 'say': 'Schaffer collaterals arc through CA1 stratum radiatum and oriens.'},
         {'at': 'ca1', 'say': 'CA1 pyramidal cells compare it with direct entorhinal input on their tufts.'},
         {'via': 'ca1_sub', 'say': 'CA1 axons leave through the alveus to the subiculum ...'},
         {'via': 'sub_ec5', 'say': '... and the loop closes in deep layers of the entorhinal cortex.'},
         {'via': 'ec5_ctx', 'say': 'Deep EC sends the result back to the neocortex.'}]},
    {'key': 'lpp', 'label': 'Lateral perforant path', 'blurb': 'LEC fan cells to the outer molecular layer. Its population volley is DS1.',
     'hops': [
         {'via': 'per_lec', 'say': 'Perirhinal cortex (objects, odors) drives the lateral entorhinal cortex.'},
         {'at': 'fan', 'say': 'Layer IIa fan cells of LEC fire.'},
         {'via': 'lpp', 'say': 'Their axons land on the outer third of the molecular layer, on the farthest reach of granule-cell dendrites.'},
         {'at': 'gc', 'say': 'Granule cells and the interneurons whose dendrites reach OML are depolarized there.'},
         {'via': 'hipp_gc', 'say': 'HIPP cells inhibit the very same stretch of dendrite.'}]},
    {'key': 'mpp', 'label': 'Medial perforant path', 'blurb': 'MEC stellate cells to the middle molecular layer. Its population volley is DS2.',
     'hops': [
         {'via': 'por_mec', 'say': 'Postrhinal cortex (space, scenes) drives the medial entorhinal cortex.'},
         {'at': 'stel', 'say': 'Layer II stellate (grid) cells of MEC fire.'},
         {'via': 'mpp', 'say': 'Their axons land on the middle third of the molecular layer.'},
         {'via': 'pp_pv', 'say': 'The same fibers excite basket cells: feed-forward inhibition.'},
         {'via': 'pv_gc', 'say': 'Basket cells clamp granule-cell somata a few milliseconds later.'}]},
    {'key': 'ta', 'label': 'Temporoammonic path', 'blurb': 'EC layer III straight to CA1, skipping the dentate and CA3.',
     'hops': [
         {'at': 'ec3', 'say': 'EC layer III pyramidal cells.'},
         {'via': 'ta', 'say': 'Axons run to CA1 stratum lacunosum-moleculare, on the distal tufts.'},
         {'at': 'ca1', 'say': 'CA1 pyramidal cells get the direct cortical view next to the CA3 view in radiatum.'},
         {'via': 'olm_ca1', 'say': 'O-LM cells inhibit the same tufts: CA1 can gate its own entorhinal input.'}]},
    {'key': 'mossyloop', 'label': 'Mossy-cell loop', 'blurb': 'Granule cells excite mossy cells, which excite granule cells far away.',
     'hops': [
         {'at': 'gc', 'say': 'Granule cells fire.'},
         {'via': 'mf_mc', 'say': 'Mossy-fiber collaterals in the hilus hit mossy-cell thorny excrescences.'},
         {'at': 'mc', 'say': 'Mossy cells fire (they are much more active than granule cells).'},
         {'via': 'mc_gc', 'say': 'Their axons end in the inner molecular layer, mostly at other levels and on the other side.'},
         {'via': 'mc_int', 'say': 'They also excite interneurons: net effect on granule cells can be inhibition.'}]},
    {'key': 'inhib', 'label': 'Dentate inhibition', 'blurb': 'Three interneurons, three places on a granule cell.',
     'hops': [
         {'via': 'hipp_gc', 'say': 'HIPP: distal dendrites, with the perforant path.'},
         {'via': 'pv_gc', 'say': 'PV+ basket cells: the soma.'},
         {'via': 'aac_gc', 'say': 'Axo-axonic cells: the axon initial segment, the last word.'}]},
    {'key': 'ca2loop', 'label': 'CA2 loop', 'blurb': 'A disynaptic route from EC layer II through CA2 to CA1.',
     'hops': [
         {'via': 'pp_ca2', 'say': 'EC layer II axons excite CA2 pyramidal cells strongly.'},
         {'at': 'ca2', 'say': 'CA2: social memory.'},
         {'via': 'ca2_ca1', 'say': 'CA2 axons end in CA1 stratum oriens (and radiatum).'}]},
    {'key': 'backproj', 'label': 'Back-projection', 'blurb': 'CA3 talks back to the dentate.',
     'hops': [
         {'at': 'ca3', 'say': 'CA3 pyramidal cells, especially CA3c near the hilus.'},
         {'via': 'back', 'say': 'Collaterals return to the hilus and contact mossy cells and interneurons.'},
         {'via': 'mc_gc', 'say': 'Mossy cells pass it to granule-cell proximal dendrites.'}]},
    {'key': 'output', 'label': 'Hippocampal output', 'blurb': 'Where the hippocampus sends its answer.',
     'hops': [
         {'at': 'ca1', 'say': 'CA1 pyramidal cells.'},
         {'via': 'ca1_sub', 'say': 'To the subiculum.'},
         {'via': 'sub_pre', 'say': 'To the pre- and parasubiculum.'},
         {'via': 'sub_subc', 'say': 'Through the fimbria-fornix to the mammillary bodies, septum and nucleus accumbens.'},
         {'via': 'sub_ec5', 'say': 'And back to deep entorhinal cortex.'}]},
]

# ----- dentate spikes (the "play" mode) -----
# Sinks/sources as Bragin et al. 1995 describe them (rat, laminar CSD);
# the lab's own laminar profile (slide "Ci", m13s2) has the same shape.
DS = [
    {'key': 'ds1', 'label': 'DS1', 'from': 'fan', 'path': 'lpp', 'sink': ['oml1', 'oml2'],
     'source': ['mml1', 'mml2', 'gcl1', 'gcl2'],
     'say': 'LEC layer II fires together. The lateral perforant path depolarizes the outer third of the molecular layer in both blades: a current sink in OML, with the return current (source) nearer the granule cells. Hilar interneurons burst.',
     'refs': ['bragin1995', 'penttonen1997', 'dvorak2021']},
    {'key': 'ds2', 'label': 'DS2', 'from': 'stel', 'path': 'mpp', 'sink': ['mml1', 'mml2'],
     'source': ['oml1', 'oml2', 'gcl1', 'gcl2'],
     'say': 'MEC layer II fires together. The medial perforant path depolarizes the middle third: a current sink in MML, flanked by sources. DS2 is usually the larger of the two. Hilar interneurons burst.',
     'refs': ['bragin1995', 'penttonen1997', 'dvorak2021']},
]

# lamina colors for slices and 3D (the shared code: molecular-layer thirds in
# teal-blues, granule layer dark teal, hilus green, CA strata in reds)
LAMINA_COLORS = {
    'oml1': '#1f6f78', 'mml1': '#2b8a8a', 'iml1': '#56b3a9', 'gcl1': '#9ad8cf', 'hil': '#59b24a',
    'gcl2': '#9ad8cf', 'iml2': '#56b3a9', 'mml2': '#2b8a8a', 'oml2': '#1f6f78',
    'ca1so': '#f4a9b8', 'ca1sp': '#e05578', 'ca1sr': '#7d1631', 'ca1slm': '#a52a77',
    'ca2so': '#f6c0a8', 'ca2sp': '#e07a55', 'ca2sr': '#8a3a1c', 'ca2slm': '#a3517a',
    'ca3so': '#f3b3c6', 'ca3sp': '#cc3d5a', 'ca3slu': '#e88aa0', 'ca3sr': '#6e1a2c', 'ca3slm': '#963068',
    'sub': '#c9a45c', 'pros': '#b8934d', 'fc': '#9bb6c9', 'ig': '#9bb6c9', 'alv': '#d9d4c7', 'fi': '#cfc8b6',
}

# The probe (the slice view can show it; no recordings attached yet):
# H3-style linear probe, 64 contacts 20 um apart (memory: PTEN probe is H3).
PROBE = {'label': 'Linear probe', 'contacts': 64, 'pitch_um': 20, 'width_um': 70, 'first_um': 40,
         'default': {'ap': -1.9, 'ml': 1.4, 'depth': 2.3, 'ang_ml': 0, 'ang_ap': 0},
         'note': 'Placement only; no recording is attached.'}


LAM_LINE = {'oml': 'Lateral perforant path (LEC II) ends here; the DS1 sink.', 'mml': 'Medial perforant path (MEC II) ends here; the DS2 sink.', 'iml': 'Mossy-cell (associational/commissural) input on proximal dendrites.', 'gcl': 'Granule-cell bodies, packed; basket and chandelier cells at its edge.', 'hil': 'Mossy cells and hilar interneurons; mossy-fibre collaterals.', 'so': 'Basal dendrites; O-LM somata; Schaffer and CA2 inputs.', 'sp': 'Pyramidal cell bodies; perisomatic inhibition; ripples.', 'sr': 'Apical dendrites: Schaffer (CA1) or recurrent (CA3) input; the sharp-wave sink in CA1.', 'slm': 'Distal tufts: entorhinal input; theta is largest near here.', 'slu': 'Mossy fibres and their giant boutons on CA3 thorny excrescences.', 'sub': "The subiculum: the hippocampus's main output.", 'pros': 'The prosubiculum, between CA1 and the subiculum.', 'alv': 'The alveus: pyramidal-cell axons leaving.', 'fi': 'The fimbria: output to the fornix.', 'fc': 'Fasciola cinerea.', 'ig': 'Induseum griseum.'}
REG_LINE = {'DG': 'Dentate gyrus: the input stage, where the perforant path lands and dentate spikes happen.', 'CA3': 'CA3: the recurrent network; mossy fibres in, Schaffer collaterals out.', 'CA2': 'CA2: a small field with strong entorhinal input; social memory.', 'CA1': 'CA1: compares CA3 and entorhinal input; the main output of the hippocampus proper.', 'SUB': 'Subiculum: the output of the hippocampal formation.', 'ProS': 'Prosubiculum.', 'ENTl': 'Lateral entorhinal cortex: objects, odors, time; the lateral perforant path (DS1).', 'ENTm': 'Medial entorhinal cortex: grid cells; the medial perforant path (DS2).', 'PRE': 'Presubiculum: head-direction cells.', 'POST': 'Postsubiculum: head-direction cells.', 'PAR': 'Parasubiculum.', 'PERI': 'Perirhinal cortex: objects; drives the lateral entorhinal cortex.', 'ECT': 'Ectorhinal cortex.', 'VISpor': 'Postrhinal cortex (VISpor): scenes and space; drives the medial entorhinal cortex.', 'HPF': 'Hippocampal formation.'}
CROWD = {'note': "One dot per cell. Granule cells: the stereological count for C57BL/6 (Kempermann et al. 1997) spread through this atlas's granule layer. Other densities are assumed from soma size and packing.", 'kinds': [{'key': 'gc', 'layers': ['gcl1', 'gcl2'], 'total': 239000, 'soma_um': 10, 'refs': ['kempermann1997']}, {'key': 'ca1', 'layers': ['ca1sp'], 'per_um3': 0.0003333333333333333, 'soma_um': 14, 'assumed': True}, {'key': 'ca3', 'layers': ['ca3sp', 'ca2sp'], 'per_um3': 0.0002, 'soma_um': 18, 'assumed': True}, {'key': 'mc', 'layers': ['hil'], 'per_um3': 2.5e-05, 'soma_um': 20, 'assumed': True}, {'key': 'hipp', 'layers': ['hil'], 'per_um3': 2.5e-05, 'soma_um': 13, 'assumed': True}, {'key': 'pvbc', 'layers': ['iml1', 'iml2', 'mml1', 'mml2', 'oml1', 'oml2', 'ca1so', 'ca1sr', 'ca1slm', 'ca3so', 'ca3sr', 'ca3slm'], 'per_um3': 6.666666666666667e-06, 'soma_um': 12, 'assumed': True}]}


def lam_line(key):
    for suf in ('slu', 'slm', 'so', 'sp', 'sr'):
        if key.startswith('ca') and key.endswith(suf):
            return LAM_LINE[suf]
    for pre in ('oml', 'mml', 'iml', 'gcl'):
        if key.startswith(pre):
            return LAM_LINE[pre]
    return LAM_LINE.get(key, '')


def main():
    write_json(os.path.join(OUT, 'kb.json'), {
        'refs': REFS, 'regions': REGIONS, 'cells': CELLS, 'connections': CONNECTIONS,
        'pathways': PATHWAYS, 'ds': DS, 'lamina_colors': LAMINA_COLORS, 'probe': PROBE,
        'dg_layers': LAYERS_DG, 'region_lines': REG_LINE, 'crowd': CROWD,
        'lamina': [{'code': r[0], 'key': r[1], 'label': r[2], 'group': r[3], 'name': r[4], 'line': lam_line(r[1]),
                    'how': DERIVED[HOW[r[1]]] if r[1] in HOW else ''} for r in LAMINA[1:]],
    }, compact=False)
    print('kb.json:', len(REGIONS), 'regions', len(CELLS), 'cells', len(CONNECTIONS),
          'connections', len(PATHWAYS), 'pathways')


if __name__ == '__main__':
    main()
