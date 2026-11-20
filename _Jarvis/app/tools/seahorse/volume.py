# -*- coding: utf-8 -*-
"""Seahorse volumes: whole-brain labels for slicing, and the hippocampal
laminae at 10 um.

    python tools/seahorse/volume.py

CCFv3 (2017) annotates the dentate's three layers (DG-mo, DG-po, DG-sg) but
NOT the strata of CA1-3 and not the thirds of the molecular layer, so those
are derived here and every derived class says how it was made (LAMINA below;
the tab shows it, and crosscheck.py tests it against the Allen Nissl volume):

  CA stratum pyramidale  Nissl-dense sheet inside each CA field: CA voxels
                         whose Nissl (25 um, Allen ARA Nissl, upsampled) is
                         in the top fraction for that field, largest pieces
                         kept.
  so vs the rest         a CA voxel is in stratum oriens when it sits on the
                         alveus side of its nearest pyramidal voxel (closer
                         to the alveus than that voxel is).
  CA3 lucidum            CA3, apical side, within 70 um of stratum pyramidale.
  radiatum vs l-m        proportional depth from the pyramidal layer to the
                         fissure (DG-mo): outer third = lacunosum-moleculare.
  DG upper/lower blade   upper (suprapyramidal, "1") = granule cells closer
                         to CA1/CA2 than their nearest hilar voxel; lower
                         (infrapyramidal, "2") the rest; molecular layer
                         takes the blade of its nearest granule voxel.
  IML / MML / OML        thirds of depth from the granule layer to the outer
                         edge of DG-mo.

Index order everywhere: [AP, DV, ML], AP increasing posterior, DV
increasing ventral, ML increasing to the right; CCF micrometres.
"""
import os
import sys
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import OUT, RAW, by_acronym, log, ontology, write_blob, write_json  # noqa: E402

MID_ML_UM = 5700.0          # CCF midline (456 * 25 / 2)

# The derived hippocampal classes. Code -> (key, label, group, how).
LAMINA = [
    (0, 'none', '', '', ''),
    (1, 'oml1', 'OML1', 'DG', 'outer molecular layer, upper (suprapyramidal) blade'),
    (2, 'mml1', 'MML1', 'DG', 'middle molecular layer, upper blade'),
    (3, 'iml1', 'IML1', 'DG', 'inner molecular layer, upper blade'),
    (4, 'gcl1', 'GCL1', 'DG', 'granule cell layer, upper blade'),
    (5, 'hil',  'HIL',  'DG', 'hilus (polymorph layer)'),
    (6, 'gcl2', 'GCL2', 'DG', 'granule cell layer, lower (infrapyramidal) blade'),
    (7, 'iml2', 'IML2', 'DG', 'inner molecular layer, lower blade'),
    (8, 'mml2', 'MML2', 'DG', 'middle molecular layer, lower blade'),
    (9, 'oml2', 'OML2', 'DG', 'outer molecular layer, lower blade'),
    (10, 'ca1so', 'CA1 so', 'CA1', 'stratum oriens'),
    (11, 'ca1sp', 'CA1 sp', 'CA1', 'stratum pyramidale'),
    (12, 'ca1sr', 'CA1 sr', 'CA1', 'stratum radiatum'),
    (13, 'ca1slm', 'CA1 slm', 'CA1', 'stratum lacunosum-moleculare'),
    (14, 'ca2so', 'CA2 so', 'CA2', 'stratum oriens'),
    (15, 'ca2sp', 'CA2 sp', 'CA2', 'stratum pyramidale'),
    (16, 'ca2sr', 'CA2 sr', 'CA2', 'stratum radiatum'),
    (17, 'ca2slm', 'CA2 slm', 'CA2', 'stratum lacunosum-moleculare'),
    (18, 'ca3so', 'CA3 so', 'CA3', 'stratum oriens'),
    (19, 'ca3sp', 'CA3 sp', 'CA3', 'stratum pyramidale'),
    (20, 'ca3slu', 'CA3 slu', 'CA3', 'stratum lucidum'),
    (21, 'ca3sr', 'CA3 sr', 'CA3', 'stratum radiatum'),
    (22, 'ca3slm', 'CA3 slm', 'CA3', 'stratum lacunosum-moleculare'),
    (23, 'sub', 'SUB', 'SUB', 'subiculum'),
    (24, 'pros', 'ProS', 'SUB', 'prosubiculum'),
    (25, 'fc', 'FC', 'HIP', 'fasciola cinerea'),
    (26, 'ig', 'IG', 'HIP', 'induseum griseum'),
    (27, 'alv', 'alv', 'tract', 'alveus'),
    (28, 'fi', 'fi', 'tract', 'fimbria'),
]
DERIVED = {  # how each class was obtained -- shown in the tab
    'annotated': 'Allen CCFv3 2017 annotation, as is',
    'nissl': 'derived: Nissl-dense sheet inside the Allen CA field',
    'side': 'derived: side of stratum pyramidale (alveus side = oriens)',
    'prop': 'derived: proportional depth (thirds) inside an Allen structure',
    'blade': 'derived: blade from which side of the hilus faces CA1/CA2',
}
HOW = {'hil': 'annotated', 'gcl1': 'blade', 'gcl2': 'blade',
       'oml1': 'prop', 'mml1': 'prop', 'iml1': 'prop',
       'oml2': 'prop', 'mml2': 'prop', 'iml2': 'prop',
       'ca1so': 'side', 'ca1sp': 'nissl', 'ca1sr': 'prop', 'ca1slm': 'prop',
       'ca2so': 'side', 'ca2sp': 'nissl', 'ca2sr': 'prop', 'ca2slm': 'prop',
       'ca3so': 'side', 'ca3sp': 'nissl', 'ca3slu': 'side', 'ca3sr': 'prop', 'ca3slm': 'prop',
       'sub': 'annotated', 'pros': 'annotated', 'fc': 'annotated', 'ig': 'annotated',
       'alv': 'annotated', 'fi': 'annotated'}
CODE = {row[1]: row[0] for row in LAMINA}


def read_nrrd_header(path):
    with open(path, 'rb') as f:
        head = b''
        while b'\n\n' not in head:
            chunk = f.read(4096)
            if not chunk:
                break
            head += chunk
    end = head.index(b'\n\n') + 2
    h = {}
    for line in head[:end].decode('latin-1').splitlines():
        if ':' in line and not line.startswith('#'):
            k, v = line.split(':', 1)
            h[k.strip()] = v.strip()
    return h, end


def stream_crop_10(path, ap0, ap1, dv0, dv1, ml0, ml1):
    """annotation_10.nrrd, cropped while decompressing: the file is AP
    fastest, ML slowest, so whole ML slabs stream past and only the crop of
    each is kept. Returns uint32 [AP, DV, ML]."""
    h, off = read_nrrd_header(path)
    sizes = [int(x) for x in h['sizes'].split()]
    assert h['encoding'] == 'gzip', h['encoding']
    nap, ndv, nml = sizes
    slab = nap * ndv * 4
    out = np.zeros((ap1 - ap0, dv1 - dv0, ml1 - ml0), np.uint32)
    d = zlib.decompressobj(31)
    buf = bytearray()
    k = 0
    with open(path, 'rb') as f:
        f.seek(off)
        while k < ml1:
            chunk = f.read(1 << 22)
            if not chunk:
                break
            buf += d.decompress(chunk)
            while len(buf) >= slab and k < ml1:
                if k >= ml0:
                    a = np.frombuffer(bytes(buf[:slab]), np.uint32).reshape(ndv, nap)
                    out[:, :, k - ml0] = a[dv0:dv1, ap0:ap1].T
                del buf[:slab]
                k += 1
    log('streamed 10 um crop', out.shape, 'sizes', sizes)
    return out


def descendants(flat, sid):
    out = [sid]
    for c in flat[sid]['children']:
        out += descendants(flat, c)
    return out


def main():
    import nrrd
    from scipy import ndimage as ndi

    flat = ontology()
    A = by_acronym(flat)
    a25, _ = nrrd.read(os.path.join(RAW, 'annotation_25.nrrd'))
    a25 = np.ascontiguousarray(a25)            # [AP, DV, ML] at 25 um
    log('annotation 25', a25.shape)

    # ---------- whole brain at 50 um, for slicing ----------
    a50 = a25[::2, ::2, ::2]
    ids = np.unique(a50)
    idx = {int(v): i for i, v in enumerate(ids)}
    lut = np.zeros(int(ids.max()) + 1, np.uint16)
    for v, i in idx.items():
        lut[v] = i
    lab50 = lut[a50]
    structs = []
    for v in ids:
        v = int(v)
        if v == 0:
            structs.append({'id': 0, 'acronym': '', 'name': 'outside', 'color': '#000000', 'path': []})
        else:
            s = flat[v]
            structs.append({'id': v, 'acronym': s['acronym'], 'name': s['name'],
                            'color': s['color'], 'path': s['path']})
    tmpl, _ = nrrd.read(os.path.join(RAW, 'ara_nissl_25.nrrd'))
    tmpl = np.ascontiguousarray(tmpl).astype(np.float32)
    hi = np.percentile(tmpl[a25 > 0], 99.5)
    n50 = tmpl.reshape(264, 2, 160, 2, 228, 2).mean(axis=(1, 3, 5))
    n50 = np.clip(n50 / hi * 255, 0, 255).astype(np.uint8)
    n = write_blob(os.path.join(OUT, 'brain50.shb.gz'),
                   {'kind': 'brain50', 'um': 50, 'origin_um': [0, 0, 0],
                    'order': 'AP,DV,ML', 'structures': structs},
                   [('labels', lab50), ('nissl', n50)])
    log('brain50', lab50.shape, len(structs), 'structures', n // 1024, 'KB')

    # ---------- the hippocampal crop at 10 um (right hemisphere) ----------
    hip_ids = set()
    for ac in ('HIP', 'SUB', 'ProS'):
        hip_ids.update(descendants(flat, A[ac]['id']))
    m = np.isin(a25, list(hip_ids))
    m[:, :, :228] = False
    ap, dv, ml = np.nonzero(m)
    pad = 2
    b25 = [(ap.min() - pad, ap.max() + pad + 1), (dv.min() - pad, dv.max() + pad + 1),
           (max(228, ml.min() - pad), ml.max() + pad + 1)]
    b10 = [(int(lo * 2.5), int(hi_ * 2.5)) for lo, hi_ in b25]
    log('HIP bbox 25', b25, '-> 10', b10)
    a10 = stream_crop_10(os.path.join(RAW, 'annotation_10.nrrd'),
                         b10[0][0], b10[0][1], b10[1][0], b10[1][1], b10[2][0], b10[2][1])
    # sanity: the 10 um crop must agree with the 25 um volume where they overlap
    sub = a10[::5, ::5, ::5]
    pts = np.argwhere(sub > 0)[::97]
    agree = 0
    for p in pts:
        um = (np.array([b10[0][0], b10[1][0], b10[2][0]]) + p * 5) * 10 + 5
        q = np.minimum((um / 25).astype(int), np.array(a25.shape) - 1)
        agree += int(a25[tuple(q)] == sub[tuple(p)])
    log('10 vs 25 agreement %.1f%%' % (100.0 * agree / max(1, len(pts))))

    def ids_of(*acs):
        s = set()
        for ac in acs:
            s.update(descendants(flat, A[ac]['id']))
        return list(s)
    isin = lambda *acs: np.isin(a10, ids_of(*acs))

    mo, po, sg = isin('DG-mo'), isin('DG-po'), isin('DG-sg')
    ca1, ca2, ca3 = isin('CA1'), isin('CA2'), isin('CA3')
    alv = isin('alv')
    sh = a10.shape
    L = np.zeros(sh, np.uint8)
    for ac, key in (('SUB', 'sub'), ('ProS', 'pros'), ('FC', 'fc'), ('IG', 'ig'),
                    ('alv', 'alv'), ('fi', 'fi')):
        L[isin(ac)] = CODE[key]
    L[po] = CODE['hil']

    # Nissl at 10 um over the crop (25 um upsampled, linear)
    nb = tmpl[b25[0][0]:b25[0][1], b25[1][0]:b25[1][1], b25[2][0]:b25[2][1]]
    n10 = ndi.zoom(nb, 2.5, order=1)
    n10 = n10[:sh[0], :sh[1], :sh[2]]
    if n10.shape != sh:
        n10 = np.pad(n10, [(0, sh[i] - n10.shape[i]) for i in range(3)], mode='edge')

    edt = lambda mask, **kw: ndi.distance_transform_edt(~mask, sampling=10.0, **kw)
    d_alv = edt(alv)
    d_mo = edt(mo)

    sp_frac = {'CA1': 0.16, 'CA2': 0.22, 'CA3': 0.20}
    for name, fld in (('CA1', ca1), ('CA2', ca2), ('CA3', ca3)):
        k = name.lower()
        vals = n10[fld]
        thr = np.quantile(vals, 1 - sp_frac[name])
        sp = fld & (n10 >= thr)
        sp = ndi.binary_opening(sp, iterations=1)
        lab, nlab = ndi.label(sp)
        if nlab:
            sizes = ndi.sum(sp, lab, range(1, nlab + 1))
            keep = np.zeros(nlab + 1, bool)
            keep[1:] = sizes >= max(200, 0.02 * sizes.max())
            sp = keep[lab]
        dsp, ind = ndi.distance_transform_edt(~sp, sampling=10.0, return_indices=True)
        near_alv = d_alv[ind[0], ind[1], ind[2]]
        so = fld & ~sp & (d_alv < near_alv)
        rest = fld & ~sp & ~so
        t = dsp / np.maximum(dsp + d_mo, 1e-3)
        slm = rest & (t > 0.67)
        if name == 'CA3':
            slu = rest & ~slm & (dsp <= 70.0)
            L[slu] = CODE['ca3slu']
            rest = rest & ~slu
        L[so] = CODE[k + 'so']
        L[sp] = CODE[k + 'sp']
        L[rest & ~slm] = CODE[k + 'sr']
        L[slm] = CODE[k + 'slm']
        log(name, 'sp vox', int(sp.sum()), 'so', int(so.sum()), 'slm', int(slm.sum()))

    # ---------- DG: blades and thirds ----------
    d_ca12 = edt(ca1 | ca2)
    _, hind = ndi.distance_transform_edt(~po, sampling=10.0, return_indices=True)
    upper_g = sg & (d_ca12 < d_ca12[hind[0], hind[1], hind[2]])
    lower_g = sg & ~upper_g
    L[upper_g] = CODE['gcl1']
    L[lower_g] = CODE['gcl2']
    d_g, gind = ndi.distance_transform_edt(~sg, sampling=10.0, return_indices=True)
    blade_up = upper_g[gind[0], gind[1], gind[2]]
    d_out = edt(~(mo | sg))
    t = d_g / np.maximum(d_g + d_out, 1e-3)
    for up, sfx in ((True, '1'), (False, '2')):
        mm = mo & (blade_up == up)
        L[mm & (t < 1 / 3)] = CODE['iml' + sfx]
        L[mm & (t >= 1 / 3) & (t < 2 / 3)] = CODE['mml' + sfx]
        L[mm & (t >= 2 / 3)] = CODE['oml' + sfx]
    counts = {row[1]: int((L == row[0]).sum()) for row in LAMINA[1:]}
    log('lamina counts', counts)

    origin = [b10[0][0] * 10, b10[1][0] * 10, b10[2][0] * 10]
    np.save(os.path.join(RAW, 'hip10_labels.npy'), L)
    np.save(os.path.join(RAW, 'hip10_annot.npy'), a10)
    write_json(os.path.join(RAW, 'hip10_meta.json'), {'origin_um': origin, 'um': 10,
                                                      'shape': list(sh)})
    nis = np.clip(n10 / hi * 255, 0, 255).astype(np.uint8)
    np.save(os.path.join(RAW, 'hip10_nissl.npy'), nis)

    ship()


def ship():
    """Write what the tab loads, from the arrays main() saved in RAW.

    Labels are cheap (the whole 10 um crop is ~1 MB gzip'd); Nissl is noise
    to a compressor, so it travels at 20 um and 32 levels -- it is the
    backdrop, not a measurement. The browser multiplies it back by 8."""
    import nrrd
    from common import read_json
    flat = ontology()
    a25, _ = nrrd.read(os.path.join(RAW, 'annotation_25.nrrd'))
    a25 = np.ascontiguousarray(a25)
    a50 = a25[::2, ::2, ::2]
    ids = np.unique(a50)
    lut = np.zeros(int(ids.max()) + 1, np.uint16)
    structs = []
    for i, v in enumerate(ids):
        v = int(v)
        lut[v] = i
        if v == 0:
            structs.append({'id': 0, 'acronym': '', 'name': 'outside', 'color': '#000000', 'path': []})
        else:
            s = flat[v]
            structs.append({'id': v, 'acronym': s['acronym'], 'name': s['name'],
                            'color': s['color'], 'path': s['path']})
    nis25, _ = nrrd.read(os.path.join(RAW, 'ara_nissl_25.nrrd'))
    nis25 = np.ascontiguousarray(nis25).astype(np.float32)
    hi = np.percentile(nis25[a25 > 0], 99.5)
    n50 = nis25.reshape(264, 2, 160, 2, 228, 2).mean(axis=(1, 3, 5))
    n50 = (np.clip(n50 / hi * 255, 0, 255).astype(np.uint8) >> 3)
    n = write_blob(os.path.join(OUT, 'brain50.shb.gz'),
                   {'kind': 'brain50', 'um': 50, 'origin_um': [0, 0, 0],
                    'order': 'AP,DV,ML', 'nissl_scale': 8, 'structures': structs},
                   [('labels', lut[a50]), ('nissl', n50)])
    log('brain50', len(structs), 'structures', n // 1024, 'KB')

    L = np.load(os.path.join(RAW, 'hip10_labels.npy'))
    nis = np.load(os.path.join(RAW, 'hip10_nissl.npy'))
    meta = read_json(os.path.join(RAW, 'hip10_meta.json'))
    origin = meta['origin_um']
    lam = [{'code': r[0], 'key': r[1], 'label': r[2], 'group': r[3], 'name': r[4],
            'how': DERIVED[HOW[r[1]]] if r[1] in HOW else ''} for r in LAMINA]
    n = write_blob(os.path.join(OUT, 'hip20.shb.gz'),
                   {'kind': 'hip20', 'um': 20, 'origin_um': origin, 'order': 'AP,DV,ML',
                    'nissl_scale': 8, 'lamina': lam},
                   [('labels', L[::2, ::2, ::2]), ('nissl', nis[::2, ::2, ::2] >> 3)])
    log('hip20', L[::2, ::2, ::2].shape, n // 1024, 'KB')
    # 10 um labels over the dorsal hippocampus, where the probes go:
    # CCF AP 6000-8400 um, DV <= 3200 um. Its Nissl comes from hip20.
    sh = L.shape
    ap_lo = max(0, (6000 - origin[0]) // 10)
    ap_hi = min(sh[0], (8400 - origin[0]) // 10)
    dv_hi = min(sh[1], (3200 - origin[1]) // 10)
    Ld = L[ap_lo:ap_hi, :dv_hi, :]
    n = write_blob(os.path.join(OUT, 'hip10d.shb.gz'),
                   {'kind': 'hip10d', 'um': 10,
                    'origin_um': [origin[0] + ap_lo * 10, origin[1], origin[2]],
                    'order': 'AP,DV,ML', 'lamina': lam},
                   [('labels', Ld)])
    log('hip10d', Ld.shape, n // 1024, 'KB')


if __name__ == '__main__':
    if '--ship' in sys.argv:
        ship()
    else:
        main()
