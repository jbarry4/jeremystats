# -*- coding: utf-8 -*-
"""Seahorse meshes.

    python tools/seahorse/meshes.py

Three tiers, each one gzip'd blob the tab loads when it needs it:

  mesh_brain   the whole brain shell and its major divisions (Allen CCFv3
               structure meshes, decimated)                 -- first view
  mesh_hpf     hippocampal formation and its neighbours: DG, CA1-3, SUB,
               ProS, PRE, POST, PAR, ENTl, ENTm, PERI, ECT, POR, FC, IG,
               alveus, fimbria (Allen meshes, both hemispheres)
  mesh_lamina  the right hippocampus at laminar detail: every class made by
               volume.py (OML1 ... OML2, CA1 so/sp/sr/slm, ...), marching
               cubes on the 10 um labels

Vertices are CCF micrometres / 10 as uint16 ([AP, DV, ML], 10 um steps);
the tab turns them into its world frame.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CCF, OUT, RAW, by_acronym, cached, log, ontology, read_json, write_blob  # noqa: E402
from volume import LAMINA  # noqa: E402

BRAIN = ['root', 'Isocortex', 'OLF', 'CTXsp', 'STR', 'PAL', 'TH', 'HY', 'MB', 'P',
         'MY', 'CB', 'HPF']
HPF = ['DG', 'CA1', 'CA2', 'CA3', 'SUB', 'ProS', 'PRE', 'POST', 'PAR', 'ENTl', 'ENTm',
       'PERI', 'ECT', 'VISpor', 'FC', 'IG', 'alv', 'fi', 'DG-mo', 'DG-sg', 'DG-po',
       'HATA', 'APr', 'ENTl2', 'ENTl3', 'ENTm2', 'ENTm3', 'ENTl5', 'ENTm5']
TARGET = {'root': 60000, 'Isocortex': 30000, 'HPF': 20000}


def load_obj(path):
    v = []
    f = []
    with open(path, encoding='latin-1') as fh:
        for line in fh:
            if line.startswith('v '):
                v.append(line.split()[1:4])
            elif line.startswith('f '):
                f.append([int(t.split('/')[0]) - 1 for t in line.split()[1:4]])
    return np.array(v, np.float32), np.array(f, np.int64)


def simplify(v, f, target):
    import fast_simplification
    if len(f) <= target:
        return v, f
    red = 1.0 - target / float(len(f))
    v2, f2 = fast_simplification.simplify(v, f.astype(np.int32), target_reduction=red)
    return v2.astype(np.float32), f2.astype(np.int64)


def pack(v_um, f):
    q = np.clip(np.round(v_um / 10.0), 0, 65535).astype(np.uint16)
    idx = f.astype(np.uint32 if f.max() > 65535 else np.uint16)
    return q, idx.reshape(-1)


def allen_tier(name, acronyms, default_target):
    flat = ontology()
    A = by_acronym(flat)
    arrays, items = [], []
    for ac in acronyms:
        s = A[ac]
        try:
            p = cached('%d.obj' % s['id'],
                       CCF + '/annotation/ccf_2017/structure_meshes/%d.obj' % s['id'],
                       sub='meshes')
        except Exception as e:
            log('no mesh for', ac, e)
            continue
        v, f = load_obj(p)
        v, f = simplify(v, f, TARGET.get(ac, default_target))
        q, idx = pack(v, f)
        arrays += [('p:' + ac, q), ('i:' + ac, idx)]
        items.append({'key': ac, 'id': s['id'], 'name': s['name'], 'color': s['color'],
                      'tris': int(len(f))})
        log(name, ac, len(v), 'verts', len(f), 'tris')
    n = write_blob(os.path.join(OUT, name + '.shb.gz'),
                   {'kind': name, 'unit_um': 10, 'order': 'AP,DV,ML', 'meshes': items}, arrays)
    log(name, n // 1024, 'KB')


def lamina_tier():
    from scipy import ndimage as ndi
    from skimage import measure
    L = np.load(os.path.join(RAW, 'hip10_labels.npy'))
    meta = read_json(os.path.join(RAW, 'hip10_meta.json'))
    org = np.array(meta['origin_um'], np.float32)
    arrays, items = [], []
    for code, key, label, group, nm in LAMINA[1:]:
        m = (L == code)
        if m.sum() < 500:
            continue
        sl = ndi.find_objects(m.astype(np.uint8))[0]
        sl = tuple(slice(max(0, s.start - 3), s.stop + 3) for s in sl)
        sub = ndi.gaussian_filter(m[sl].astype(np.float32), 1.0)
        v, f, _, _ = measure.marching_cubes(sub, 0.5, spacing=(10.0, 10.0, 10.0))
        v += org + np.array([s.start * 10.0 for s in sl], np.float32)
        tgt = 9000 if group in ('DG',) else 7000
        v, f = simplify(v.astype(np.float32), f.astype(np.int64), tgt)
        # marching cubes winds the other way from Allen's meshes
        f = f[:, ::-1]
        q, idx = pack(v, f)
        arrays += [('p:' + key, q), ('i:' + key, idx)]
        items.append({'key': key, 'code': code, 'label': label, 'group': group, 'name': nm,
                      'tris': int(len(f))})
        log('lamina', key, len(f), 'tris')
    n = write_blob(os.path.join(OUT, 'mesh_lamina.shb.gz'),
                   {'kind': 'mesh_lamina', 'unit_um': 10, 'order': 'AP,DV,ML',
                    'hemisphere': 'right', 'meshes': items}, arrays)
    log('mesh_lamina', n // 1024, 'KB')


if __name__ == '__main__':
    which = sys.argv[1:] or ['brain', 'hpf', 'lamina']
    if 'brain' in which:
        allen_tier('mesh_brain', BRAIN, 12000)
    if 'hpf' in which:
        allen_tier('mesh_hpf', HPF, 10000)
    if 'lamina' in which:
        lamina_tier()
