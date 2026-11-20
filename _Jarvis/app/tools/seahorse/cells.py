# -*- coding: utf-8 -*-
"""Seahorse cells: real NeuroMorpho.Org reconstructions, placed in the atlas.

    python tools/seahorse/cells.py

Two kinds of tracing:

  'ccf'    already registered to CCFv3 by the people who traced it
           (MouseLight, Winnubst 2019; SEU-ALLEN, Peng 2021). Put in as
           they are -- the soma's own atlas label, and where the axon goes,
           are evidence, and crosscheck.py treats them that way.
  'slice'  traced in a slice in its own frame. Placed by rule: soma into
           the layer the paper puts it in, rotated so the arbor named in
           ALIGN points to the layer named there. Where its branches land
           is then a consequence of that placement, not evidence, and the
           tab says so.

One cell type has no public tracing at all (the mossy cell, mouse or rat,
as of 2026-11): it is drawn from its published description and marked
'drawn' everywhere it appears.

Writes web/seahorse/cells.shb.gz and RAW/cells_stats.json.
"""
import json
import math
import os
import sys
import urllib.parse

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import OUT, RAW, by_acronym, cached, get_json, log, ontology, read_json, write_blob, write_json  # noqa: E402
from volume import CODE, LAMINA  # noqa: E402

MID = 5700.0

# key, neuron_name, kind, extra
#   ccf   extra = axis order of the file: MouseLight writes (ML, DV, AP),
#         SEU-ALLEN (Peng) writes (AP, DV, ML) -- found by asking which order
#         puts each soma in the region its authors named (2026-11-20).
#   slice extra = FIT: soma layers, and the layers each arbor belongs in
#         (the paper's description). The placement searches soma positions
#         in those layers and rotations for the best fit.
EXEMPLARS = [
    ('gc',   'AA0091', 'ccf', (2, 1, 0)),
    ('sgc',  'Anstoetz_Toolbox-SL1', 'slice', {'soma': ['iml1'], 'dend': ['mml1', 'oml1'], 'axon': ['hil', 'ca3slu', 'ca3sp']}),
    ('mc',   None, 'drawn', None),
    ('hipp', 'HIPP1', 'slice', {'soma': ['hil'], 'dend': ['hil'], 'axon': ['oml1', 'oml2', 'mml1', 'mml2']}),
    ('pvbc', 'class-BC1', 'slice', {'soma': ['gcl1'], 'dend': ['iml1', 'mml1', 'oml1', 'hil', 'gcl1'], 'axon': ['gcl1']}),
    ('aac',  '082113-1COMAACscale', 'slice', {'soma': ['gcl1'], 'dend': ['iml1', 'mml1', 'oml1', 'hil'], 'axon': ['gcl1', 'hil']}),
    ('stel', 'Huang2024SCHor1', 'slice', {'soma': ['ENTm2'], 'dend': ['ENTm1', 'ENTm2'], 'axon': []}),
    ('fan',  '182712_10001_32777_7520', 'ccf', (0, 1, 2)),
    ('ca3',  'AA0999', 'ccf', (2, 1, 0)),
    ('ca1',  'AA0959', 'ccf', (2, 1, 0)),
    ('olm',  'cell-pair-02-12-10-A_file2', 'slice', {'soma': ['ca1so'], 'dend': ['ca1so', 'alv'], 'axon': ['ca1slm']}),
]
# The coronal plane the hippocampal slice cells go in (CCF um): through the
# dorsal dentate, near where the lab's probes sit.
ANCHOR_AP = 7300.0
ANCHOR = {'hil': (ANCHOR_AP, 2250.0, 7150.0)}


def meta(name):
    return get_json('https://neuromorpho.org/api/neuron/name/' + urllib.parse.quote(name))


def swc_url(m, version):
    arch = m['archive'].lower().replace(' ', '%20')
    nm = urllib.parse.quote(m['neuron_name'])
    if version == 'cng':
        return 'https://neuromorpho.org/dableFiles/%s/CNG%%20version/%s.CNG.swc' % (arch, nm)
    return 'https://neuromorpho.org/dableFiles/%s/Source-Version/%s.swc' % (arch, nm)


def parse_swc(path):
    rows = []
    with open(path, encoding='latin-1') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            p = line.split()
            if len(p) < 7:
                continue
            rows.append((int(float(p[0])), int(float(p[1])), float(p[2]), float(p[3]),
                         float(p[4]), float(p[5]), int(float(p[6]))))
    ids = {r[0]: i for i, r in enumerate(rows)}
    xyz = np.array([[r[2], r[3], r[4]] for r in rows], np.float64)
    typ = np.array([r[1] for r in rows], np.int16)
    rad = np.array([r[5] for r in rows], np.float32)
    par = np.array([ids.get(r[6], -1) for r in rows], np.int64)
    return xyz, typ, rad, par


def simplify(xyz, typ, rad, par, step=8.0):
    """Keep somata, branch points and tips; along unbranched runs keep a
    point every `step` um. Returns the reduced arrays with remapped parents."""
    n = len(xyz)
    kids = np.zeros(n, np.int32)
    for p in par:
        if p >= 0:
            kids[p] += 1
    keep = np.zeros(n, bool)
    keep[(par < 0) | (kids != 1) | (typ == 1)] = True
    run = np.zeros(n)
    for i in range(n):  # SWC parents precede children
        p = par[i]
        if p < 0:
            continue
        if typ[i] != typ[p]:
            keep[i] = True
        run[i] = (0.0 if keep[p] else run[p]) + float(np.linalg.norm(xyz[i] - xyz[p]))
        if run[i] >= step:
            keep[i] = True
    new = -np.ones(n, np.int64)
    new[keep] = np.arange(keep.sum())
    npar = -np.ones(keep.sum(), np.int64)
    for i in np.nonzero(keep)[0]:
        p = par[i]
        while p >= 0 and not keep[p]:
            p = par[p]
        npar[new[i]] = new[p] if p >= 0 else -1
    return xyz[keep], typ[keep], rad[keep], npar


def rot_to(a, b):
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3) if c > 0 else -np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / (np.linalg.norm(v) ** 2))


class Atlas:
    """Label lookups in CCF um: laminae at 10 um (right hippocampus), Allen
    at 25 um everywhere."""

    def __init__(self):
        import nrrd
        self.L = np.load(os.path.join(RAW, 'hip10_labels.npy'))
        self.org = np.array(read_json(os.path.join(RAW, 'hip10_meta.json'))['origin_um'], float)
        self.a25, _ = nrrd.read(os.path.join(RAW, 'annotation_25.nrrd'))
        self.flat = ontology()
        self.A = by_acronym(self.flat)
        self.lam_key = {r[0]: r[1] for r in LAMINA}

    def lam(self, um):
        i = np.floor((np.asarray(um) - self.org) / 10.0).astype(int)
        ok = np.all((i >= 0) & (i < np.array(self.L.shape)), axis=-1)
        out = np.zeros(len(i), np.uint8)
        out[ok] = self.L[i[ok, 0], i[ok, 1], i[ok, 2]]
        return out

    def allen(self, um):
        i = np.floor(np.asarray(um) / 25.0).astype(int)
        ok = np.all((i >= 0) & (i < np.array(self.a25.shape)), axis=-1)
        out = np.zeros(len(i), np.int64)
        out[ok] = self.a25[i[ok, 0], i[ok, 1], i[ok, 2]]
        return out

    def acr(self, sid):
        return self.flat[int(sid)]['acronym'] if int(sid) in self.flat else ''

    def under(self, sid, ac):
        sid = int(sid)
        return sid in self.flat and self.A[ac]['id'] in self.flat[sid]['path']

    def voxels_of(self, key):
        """CCF um centres of every voxel of a lamina key or an Allen acronym."""
        if key in CODE:
            idx = np.argwhere(self.L == CODE[key])
            return self.org + idx * 10.0 + 5.0
        ids = [k for k, v in self.flat.items() if self.A[key]['id'] in v['path']]
        idx = np.argwhere(np.isin(self.a25, ids))
        idx = idx[idx[:, 2] >= 228]  # right hemisphere
        return idx * 25.0 + 12.5

    def nearest(self, key, p, plane_ap=None):
        pts = self.voxels_of(key)
        if plane_ap is not None:
            near = np.abs(pts[:, 0] - plane_ap) < 15
            if near.any():
                pts = pts[near]
        d = np.linalg.norm(pts - p, axis=1)
        return pts[int(np.argmin(d))]


def random_rotations(n, rng):
    q = rng.normal(size=(n, 4))
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    w, x, y, z = q.T
    return np.stack([
        np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
        np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
        np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], 1)


def fit_place(xyz, typ, par, at, fit):
    """Search soma positions (in the soma layer, on one coronal plane) and
    rotations for the placement whose arbors fall most in their layers.
    Score = mean over arbors of the fraction of length in the right layers,
    plus a little for lying flat in the coronal plane (as in a slice)."""
    rng = np.random.default_rng(11)
    soma = xyz[typ == 1].mean(axis=0) if (typ == 1).any() else xyz[0]
    local = xyz - soma
    child = np.nonzero(par >= 0)[0]
    mid = (local[child] + local[par[child]]) / 2
    seg = np.linalg.norm(local[child] - local[par[child]], axis=1)
    t = typ[child]
    arbors = []
    for arbor, sel in (('dend', np.isin(t, (3, 4))), ('axon', t == 2)):
        if not fit.get(arbor) or not sel.any():
            continue
        idx = np.nonzero(sel)[0]
        if len(idx) > 1200:
            idx = rng.choice(idx, 1200, replace=False)
        arbors.append((arbor, mid[idx], seg[idx] / seg[idx].sum(), fit[arbor]))

    def member(keys):
        lam = np.zeros(256, bool)
        ids = set()
        for k in keys:
            if k in CODE:
                lam[CODE[k]] = True
            else:
                ids.update(kk for kk, v in at.flat.items() if at.A[k]['id'] in v['path'])
        return lam, np.array(sorted(ids), np.int64)

    tests = [member(keys) for (_, _, _, keys) in arbors]
    somas = np.concatenate([at.voxels_of(k) for k in fit['soma']])
    hip = all(k in CODE for k in fit['soma'])
    plane = ANCHOR_AP if hip else float(np.median(somas[:, 0]))
    somas = somas[np.abs(somas[:, 0] - plane) < 13]
    if hip:   # keep to the dorsal part of the section
        somas = somas[somas[:, 1] < 2600]
    if len(somas) > 60:
        somas = somas[rng.choice(len(somas), 60, replace=False)]
    rots = random_rotations(300, rng)
    spread = np.abs(local).mean() + 1e-6
    sub = local[:: max(1, len(local) // 300)]
    best = (-1.0, None, None)
    for R in rots:
        flat_ap = 1.0 - min(1.0, float(np.abs((sub @ R.T)[:, 0]).mean()) / spread)
        rot_pts = [pts @ R.T for (_, pts, _, _) in arbors]
        for s in somas:
            sc = 0.0
            for (arbor, pts, w, keys), (lam_ok, ids), rp in zip(arbors, tests, rot_pts):
                q = rp + s
                ok = lam_ok[at.lam(q)]
                if len(ids):
                    ok = ok | np.isin(at.allen(q), ids)
                sc += float((w * ok).sum())
            sc = sc / max(1, len(arbors)) + 0.1 * flat_ap
            if sc > best[0]:
                best = (sc, s, R)
    sc, s, R = best
    log('   fit score %.2f at' % sc, np.round(s), 'plane', plane)
    return local @ R.T + s, round(sc, 3)


def drawn_mossy(at):
    """A mossy cell drawn from its description (Amaral 1978; Scharfman &
    Myers 2013; Scharfman 2016): soma in the hilus, 3-4 thick primary
    dendrites that stay mostly in the hilus with a few crossing the granule
    layer into the molecular layer, thorny excrescences proximally; axon
    collaterals in the hilus and a main axon to the inner molecular layer
    (both blades; most of it leaves for other levels and the other side)."""
    rng = np.random.default_rng(7)
    s = at.nearest('hil', np.array(ANCHOR['hil']), plane_ap=ANCHOR_AP)
    hil = at.voxels_of('hil')
    hil = hil[np.abs(hil[:, 0] - ANCHOR_AP) < 200]
    iml = np.concatenate([at.voxels_of('iml1'), at.voxels_of('iml2')])
    iml = iml[np.abs(iml[:, 0] - ANCHOR_AP) < 250]
    xyz, typ, par = [s], [1], [-1]

    def grow(start_i, goal, t, step=6.0, wobble=0.25):
        cur = np.array(xyz[start_i])
        last = start_i
        n = int(np.linalg.norm(goal - cur) / step)
        d0 = (goal - cur) / max(1, np.linalg.norm(goal - cur))
        for _ in range(max(2, n)):
            d = (goal - cur)
            d = d / max(1e-6, np.linalg.norm(d)) + rng.normal(0, wobble, 3)
            d /= np.linalg.norm(d)
            cur = cur + d * step
            xyz.append(cur.copy())
            typ.append(t)
            par.append(last)
            last = len(xyz) - 1
        return last

    # dendrites: mostly to far points of the hilus, two reaching the ML
    for k in range(4):
        g = hil[rng.integers(len(hil))]
        tip = grow(0, g, 3)
        mid = (tip + 1) // 2 + 1
        for _ in range(2):
            grow(mid, hil[rng.integers(len(hil))], 3, step=5.0)
    for k in range(2):
        ml = at.nearest('mml1' if k == 0 else 'mml2', s, plane_ap=ANCHOR_AP)
        grow(0, ml, 3)
    # axon: hilar collaterals then to the IML of both blades
    a0 = grow(0, s + np.array([60.0, 40.0, 0.0]), 2, step=8.0)
    for _ in range(4):
        grow(a0, hil[rng.integers(len(hil))], 2, step=8.0, wobble=0.35)
    for _ in range(6):
        g = iml[rng.integers(len(iml))]
        b = grow(a0, g, 2, step=10.0)
        # run along the IML for a while
        for _ in range(2):
            g2 = iml[np.argsort(np.linalg.norm(iml - g, axis=1))[rng.integers(40, 400)]]
            grow(b, g2, 2, step=10.0, wobble=0.15)
    xyz = np.array(xyz)
    return xyz, np.array(typ, np.int16), np.full(len(xyz), 1.0, np.float32), np.array(par, np.int64)


def stats(at, xyz, typ, par, kind):
    """Length of dendrite and axon in each lamina / Allen region."""
    out = {'dend': {}, 'axon': {}}
    if len(xyz) < 2:
        return out
    child = np.nonzero(par >= 0)[0]
    a = xyz[child]
    b = xyz[par[child]]
    mid = (a + b) / 2
    seg = np.linalg.norm(a - b, axis=1)
    t = typ[child]
    lam = at.lam(mid)
    al = at.allen(mid)
    for arbor, m in (('dend', np.isin(t, (3, 4))), ('axon', t == 2)):
        acc = {}
        for i in np.nonzero(m)[0]:
            k = at.lam_key.get(int(lam[i]), 'none')
            if k == 'none':
                k = at.acr(al[i]) or 'outside'
                # group Allen leaves by their layer-free parent for readability
            acc[k] = acc.get(k, 0.0) + float(seg[i])
        out[arbor] = {k: round(v, 1) for k, v in sorted(acc.items(), key=lambda kv: -kv[1])}
    return out


def main():
    at = Atlas()
    arrays, cells, allstats = [], [], {}
    for key, name, kind, extra in EXEMPLARS:
        m = None
        if kind == 'drawn':
            xyz, typ, rad, par = drawn_mossy(at)
            src = {'kind': 'drawn', 'note': 'No public mouse or rat mossy-cell tracing on NeuroMorpho.Org (checked 2026-11-20). Drawn from Amaral 1978, Scharfman & Myers 2013, Scharfman 2016.'}
        else:
            m = meta(name)
            ver = 'source' if kind == 'ccf' else 'cng'
            p = cached(name + ('.src.swc' if ver == 'source' else '.cng.swc'), swc_url(m, ver), sub='swc')
            xyz, typ, rad, par = parse_swc(p)
            fitscore = None
            if kind == 'ccf':
                xyz = xyz[:, list(extra)]
                s0 = xyz[typ == 1].mean(axis=0) if (typ == 1).any() else xyz[0]
                if s0[2] < MID:     # mirror the cell into the right hemisphere
                    xyz[:, 2] = 2 * MID - xyz[:, 2]
            xyz, typ, rad, par = simplify(xyz, typ, rad, par, step=8.0 if kind == 'slice' else 20.0)
            if kind == 'slice':
                xyz, fitscore = fit_place(xyz, typ, par, at, extra)
            src = {'kind': kind, 'neuron_name': m['neuron_name'], 'neuron_id': m['neuron_id'],
                   'archive': m['archive'], 'species': m['species'], 'strain': m.get('strain'),
                   'brain_region': m.get('brain_region'), 'cell_type': m.get('cell_type'),
                   'domain': m.get('domain'), 'integrity': m.get('physical_Integrity'),
                   'condition': m.get('experiment_condition'), 'protocol': m.get('protocol'),
                   'doi': m.get('reference_doi'), 'pmid': m.get('reference_pmid'),
                   'url': 'https://neuromorpho.org/neuron_info.jsp?neuron_name=' + urllib.parse.quote(m['neuron_name'])}
            if kind == 'slice':
                src['fit'] = {'score': fitscore, 'layers': extra}
            if kind == 'ccf':
                src['axes'] = ['AP', 'DV', 'ML'] if list(extra) == [0, 1, 2] else ['ML', 'DV', 'AP']
        soma = xyz[typ == 1].mean(axis=0) if (typ == 1).any() else xyz[0]
        st = stats(at, xyz, typ, par, kind)
        sl = at.lam(soma[None])[0]
        sa = at.allen(soma[None])[0]
        st['soma_lamina'] = at.lam_key.get(int(sl), 'none')
        st['soma_allen'] = at.acr(sa)
        st['soma_um'] = [round(float(x), 1) for x in soma]
        allstats[key] = {'source': src, 'stats': st}
        arrays += [('p:' + key, xyz.astype(np.float32)), ('t:' + key, typ.astype(np.uint8)),
                   ('r:' + key, np.clip(rad, 0.1, 30).astype(np.float32)),
                   ('a:' + key, par.astype(np.int32))]
        cells.append({'key': key, 'n': int(len(xyz)), 'soma_um': st['soma_um'],
                      'soma_lamina': st['soma_lamina'], 'soma_allen': st['soma_allen'],
                      'source': src})
        log(key, kind, len(xyz), 'pts; soma in', st['soma_lamina'], '/', st['soma_allen'],
            '| axon top', list(st['axon'].items())[:4], '| dend top', list(st['dend'].items())[:4])
    n = write_blob(os.path.join(OUT, 'cells.shb.gz'), {'kind': 'cells', 'unit': 'um',
                   'order': 'AP,DV,ML', 'cells': cells}, arrays)
    write_json(os.path.join(RAW, 'cells_stats.json'), allstats, compact=False)
    log('cells', n // 1024, 'KB')


if __name__ == '__main__':
    main()
