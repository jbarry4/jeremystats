"""Build Sextant's layer volume: web/seahorse/sextant10.shb.gz

    python tools/sextant/build_atlas.py

The Seahorse laminae (tools/seahorse/volume.py: Allen CCFv3 2017 with CA
strata and molecular-layer thirds derived, 10 um, right hemisphere) inside a
box big enough for any probe Sextant will consider, with every voxel outside
the hippocampus given the coarse Allen region it sits in -- a probe that
starts in cortex or ends in thalamus has to be told so.

Box (CCF um): AP 5800-9400, DV 0-4400, ML 5700-9300 (midline to 3.6 mm
lateral). Codes 0-28 are the laminae (volume.LAMINA); 30+ are the coarse
regions below. Left-hemisphere probes are mirrored onto it (the CCF is
symmetric).
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(APP, 'tools', 'seahorse'))

from common import OUT, RAW, by_acronym, log, ontology, write_blob  # noqa: E402
from volume import LAMINA, descendants, stream_crop_10  # noqa: E402

BOX = {'ap': (5800, 9400), 'dv': (0, 4400), 'ml': (5700, 9300)}

# Coarse regions outside the hippocampus proper, in the order they are
# assigned (later wins, so specific beats general).
COARSE = [
    (38, 'brain', 'brain', 'other brain', ('grey', 'fiber tracts', 'VS')),
    (36, 'cnu', 'CNU', 'cerebral nuclei (striatum, pallidum)', ('CNU',)),
    (35, 'mb', 'MB', 'midbrain', ('MB',)),
    (34, 'hy', 'HY', 'hypothalamus', ('HY',)),
    (33, 'th', 'TH', 'thalamus', ('TH',)),
    (37, 'hpf', 'HPF', 'other hippocampal formation (entorhinal, subicular complex)', ('HPF',)),
    (30, 'ctx', 'CTX', 'neocortex', ('Isocortex', 'OLF', 'CTXsp')),
    (31, 'wm', 'WM', 'white matter (corpus callosum, cingulum, capsules)', ('fiber tracts',)),
    (32, 'vent', 'VENT', 'ventricle or choroid plexus', ('VS',)),
]


def main():
    flat = ontology()
    A = by_acronym(flat)
    vox = {k: (v[0] // 10, v[1] // 10) for k, v in BOX.items()}
    log('box voxels', vox)
    a10 = stream_crop_10(os.path.join(RAW, 'annotation_10.nrrd'),
                         vox['ap'][0], vox['ap'][1], vox['dv'][0], vox['dv'][1],
                         vox['ml'][0], vox['ml'][1])
    L = np.zeros(a10.shape, np.uint8)
    inbrain = a10 > 0
    for code, key, label, name, acs in COARSE:
        ids = set()
        for ac in acs:
            if ac in A:
                ids.update(descendants(flat, A[ac]['id']))
        m = np.isin(a10, list(ids))
        L[m] = code
        log('coarse', key, int(m.sum()))
    L[inbrain & (L == 0)] = 38

    # the laminae, from the Seahorse build's unsmoothed 10 um derivation
    H = np.load(os.path.join(RAW, 'hip10_labels.npy'), mmap_mode='r')
    import json
    meta = json.load(open(os.path.join(RAW, 'hip10_meta.json')))
    ho = np.array(meta['origin_um']) // 10
    bo = np.array([vox['ap'][0], vox['dv'][0], vox['ml'][0]])
    bs = np.array(L.shape)
    lo = np.maximum(ho, bo)
    hi = np.minimum(ho + np.array(H.shape), bo + bs)
    hs = tuple(slice(lo[i] - ho[i], hi[i] - ho[i]) for i in range(3))
    bsl = tuple(slice(lo[i] - bo[i], hi[i] - bo[i]) for i in range(3))
    sub = np.asarray(H[hs])
    tgt = L[bsl]
    tgt[sub > 0] = sub[sub > 0]
    L[bsl] = tgt
    log('laminae placed', int((L > 0).sum()), 'of', L.size)

    classes = [{'code': c, 'key': k, 'label': lab, 'group': g, 'name': n}
               for c, k, lab, g, n in LAMINA]
    classes += [{'code': c, 'key': k, 'label': lab, 'group': 'coarse', 'name': n}
                for c, k, lab, n, _ in COARSE]
    classes.append({'code': 0, 'key': 'out', 'label': 'outside',
                    'group': 'coarse', 'name': 'outside the brain'})
    u, c = np.unique(L, return_counts=True)
    log('codes', dict(zip(u.tolist(), c.tolist())))
    n = write_blob(os.path.join(OUT, 'sextant10.shb.gz'),
                   {'kind': 'sextant10', 'um': 10, 'order': 'AP,DV,ML',
                    'origin_um': [BOX['ap'][0], BOX['dv'][0], BOX['ml'][0]],
                    'shape': list(L.shape), 'classes': classes,
                    'side': 'right hemisphere; mirror ML about 5700 for the left',
                    'source': 'Allen CCFv3 2017 annotation (10 um) + Seahorse derived laminae'},
                   [('labels', L)])
    log('wrote sextant10.shb.gz', n, 'bytes')


if __name__ == '__main__':
    main()
