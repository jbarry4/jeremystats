# -*- coding: utf-8 -*-
"""Seahorse cells: real NeuroMorpho.Org reconstructions, placed in the atlas.

    python tools/seahorse/cells.py

Three kinds of cell:

  'ccf'    whole-brain tracings already registered to CCFv3 by the people
           who traced them (MouseLight, Winnubst 2019). Put in as they are
           -- the soma's own atlas label, and where the axon goes, are
           evidence, and crosscheck.py treats them that way.
  'slice'  traced in a slice in its own frame. Placed by rule: soma into
           the layer the paper puts it in, rotated so each arbor falls in
           the layers named for it, beside the chain cell it talks to.
           Where its branches land is a consequence of that placement, not
           evidence, and the tab says so.
  'drawn'  the mossy cell. There is no public mouse or rat mossy-cell
           tracing (NeuroMorpho, checked 2026-11-20; the survey of every
           registered hilar cell found none with a mossy-cell axon), so it
           is drawn from its published description, its axon routed through
           the hilus and inner molecular layer of the atlas.

The instances are chosen so the rides can run along them: tools/seahorse/
survey.py found MouseLight cells that touch where they are (LEC AA1047 ->
granule cell AA0573 0.8 um -> CA3 AA0307 2.3 um -> CA1 AA0306 42 um). A
cell that "meets" an upstream axon is shifted by the remaining gap so the
synapse closes exactly ("positioned for the story", never more than
MAX_NUDGE_UM -- registration between brains is good to about 50-100 um);
the shift is recorded and the tab can switch back to true positions.

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
MAX_NUDGE_UM = 120.0

ML = ['iml1', 'mml1', 'oml1', 'iml2', 'mml2', 'oml2']
ML_OUTER = ['mml1', 'oml1', 'mml2', 'oml2']
GCL = ['gcl1', 'gcl2']

# key, type (kb cell), source, placement. Order matters: a cell is placed
# after the cells it meets or reaches.
INSTANCES = [
    # the trisynaptic chain, as traced (MouseLight)
    dict(key='fan', type='fan', name='AA1047', kind='ccf', step=10.0),
    dict(key='gc', type='gc', name='AA0573', kind='ccf', step=6.0,
         meets=('fan', ['oml1', 'oml2', 'mml1', 'mml2'])),
    dict(key='ca3', type='ca3', name='AA0307', kind='ccf', step=10.0,
         meets=('gc', ['ca3slu', 'ca3sp', 'ca3sr', 'ca3so'])),
    # (AA0621 is closer, 10.8 um, but its dendrites lie in the corpus
    # callosum, not CA1: 8% in CA1 strata. AA0306: 94%.)
    dict(key='ca1', type='ca1', name='AA0306', kind='ccf', step=10.0,
         meets=('ca3', ['ca1sr', 'ca1so'])),
    # partners: a CA3 cell on AA0307's recurrent axon, a second LEC cell for
    # the DS1 volley, and a granule cell at another level for the mossy cell
    dict(key='ca3_b', type='ca3', name='AA0304', kind='ccf', step=10.0,
         meets=('ca3', ['ca3sr', 'ca3so'])),
    dict(key='fan_b', type='fan', name='AA1002', kind='ccf', step=20.0),
    dict(key='gc_b', type='gc', name='AA0869', kind='ccf', step=6.0),
    # local cells, placed by their layers beside the chain's granule cell
    dict(key='mc', type='mc', kind='drawn', near='gc', reach='gc_b'),
    dict(key='hipp', type='hipp', name='HIPP1', kind='slice', near=('gc', 320),
         fit={'soma': ['hil'], 'dend': ['hil'], 'axon': ML_OUTER},
         reaches=('gc', 'dend', ML_OUTER)),
    dict(key='pvbc', type='pvbc', name='class-BC1', kind='slice', near=('gc', 220),
         fit={'soma': GCL, 'dend': ML + ['hil'] + GCL, 'axon': GCL},
         reaches=('gc', 'soma', None)),
    dict(key='aac', type='aac', name='082113-1COMAACscale', kind='slice', near=('gc', 220),
         fit={'soma': GCL, 'dend': ML + ['hil'], 'axon': GCL + ['hil']},
         reaches=('gc', 'ais', None)),
    dict(key='sgc', type='sgc', name='Anstoetz_Toolbox-SL1', kind='slice', near=('gc', 320),
         fit={'soma': ['iml1', 'iml2'], 'dend': ML_OUTER, 'axon': ['hil', 'ca3slu', 'ca3sp']}),
    dict(key='olm', type='olm', name='cell-pair-02-12-10-A_file2', kind='slice', near=('ca1', 320),
         fit={'soma': ['ca1so'], 'dend': ['ca1so', 'alv'], 'axon': ['ca1slm']},
         reaches=('ca1', 'dend', ['ca1slm'])),
    dict(key='stel', type='stel', name='Huang2024SCHor1', kind='slice',
         fit={'soma': ['ENTm2'], 'dend': ['ENTm1', 'ENTm2'], 'axon': []}),
]


def catalog_row(name):
    p = os.path.join(RAW, 'neuromorpho_catalog.json')
    if not hasattr(catalog_row, 'rows'):
        catalog_row.rows = {n['neuron_name']: n for n in json.load(open(p, encoding='utf-8'))}
    r = catalog_row.rows.get(name)
    return r if r else get_json('https://neuromorpho.org/api/neuron/name/' + urllib.parse.quote(name))


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


def path_len(xyz, par):
    """Path length from the root to every node."""
    out = np.zeros(len(xyz))
    for i in range(len(xyz)):
        p = par[i]
        if p >= 0:
            out[i] = out[p] + float(np.linalg.norm(xyz[i] - xyz[p]))
    return out


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
        self._vox = {}

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

    def ids_under(self, ac):
        return [k for k, v in self.flat.items() if self.A[ac]['id'] in v['path']]

    def voxels_of(self, key):
        """CCF um centres of every voxel of a lamina key or an Allen acronym."""
        if key in self._vox:
            return self._vox[key]
        if key in CODE:
            idx = np.argwhere(self.L == CODE[key])
            out = self.org + idx * 10.0 + 5.0
        else:
            idx = np.argwhere(np.isin(self.a25, self.ids_under(key)))
            idx = idx[idx[:, 2] >= 228]  # right hemisphere
            out = idx * 25.0 + 12.5
        self._vox[key] = out
        return out

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


def fit_place(xyz, typ, par, at, fit, plane=None, near=None, top=1):
    """Search soma positions (in the soma layer, on one coronal plane, near
    a point if given) and rotations for the placement whose arbors fall most
    in their layers. Score = mean over arbors of the fraction of length in
    the right layers, plus a little for lying flat in the coronal plane (as
    in a slice)."""
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
                ids.update(at.ids_under(k))
        return lam, np.array(sorted(ids), np.int64)

    tests = [member(keys) for (_, _, _, keys) in arbors]
    somas = np.concatenate([at.voxels_of(k) for k in fit['soma']])
    hip = all(k in CODE for k in fit['soma'])
    if plane is None:
        plane = float(near[0][0]) if near is not None else float(np.median(somas[:, 0]))
    somas = somas[np.abs(somas[:, 0] - plane) < 13]
    if near is not None:
        somas = somas[np.linalg.norm(somas - near[0], axis=1) < near[1]]
    if len(somas) > 60:
        somas = somas[rng.choice(len(somas), 60, replace=False)]
    rots = random_rotations(300, rng)
    spread = np.abs(local).mean() + 1e-6
    sub = local[:: max(1, len(local) // 300)]
    best = (-1.0, None, None)
    pool = []
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
            pool.append((sc, s, R))
            if sc > best[0]:
                best = (sc, s, R)
    sc, s, R = best
    log('   fit score %.2f at' % sc, np.round(s), 'plane', round(plane))
    if top > 1:
        pool.sort(key=lambda x: -x[0])
        return [(local @ R2.T + s2, round(sc2, 3)) for sc2, s2, R2 in pool[:top]]
    return local @ R.T + s, round(sc, 3)


def route(at, a, b, cost_of, pad=250.0, res=20.0):
    """A path from a to b (CCF um) through cheap tissue: minimum-cost route
    on a res-um grid of the hippocampal crop (skimage MCP, 26-connected).
    cost_of(lamina codes) -> cost per voxel."""
    from skimage.graph import route_through_array
    lo = np.minimum(a, b) - pad
    hi = np.maximum(a, b) + pad
    k = max(1, int(res / 10))
    i0 = np.clip(((lo - at.org) / 10).astype(int), 0, np.array(at.L.shape) - 1)
    i1 = np.clip(((hi - at.org) / 10).astype(int) + 1, 1, np.array(at.L.shape))
    sub = at.L[i0[0]:i1[0]:k, i0[1]:i1[1]:k, i0[2]:i1[2]:k]
    cost = cost_of(sub).astype(np.float64)
    ga = np.clip(((a - at.org) / 10).astype(int) - i0, 0, None) // k
    gb = np.clip(((b - at.org) / 10).astype(int) - i0, 0, None) // k
    ga = np.minimum(ga, np.array(sub.shape) - 1)
    gb = np.minimum(gb, np.array(sub.shape) - 1)
    path, _ = route_through_array(cost, tuple(ga), tuple(gb), fully_connected=True, geometric=True)
    pts = at.org + (np.array(path) * k + i0) * 10.0 + 5.0 * k
    pts[0], pts[-1] = a, b
    # smooth, keeping the ends
    if len(pts) > 4:
        sm = pts.copy()
        for _ in range(3):
            sm[1:-1] = (sm[:-2] + sm[1:-1] * 2 + sm[2:]) / 4
        pts = sm
    return pts


def grow(xyz, typ, par, start_i, goal, t, rng, step=6.0, wobble=0.25, exact=False):
    cur = np.array(xyz[start_i])
    last = start_i
    n = int(np.linalg.norm(goal - cur) / step)
    for k in range(max(2, n)):
        d = (goal - cur)
        d = d / max(1e-6, np.linalg.norm(d)) + rng.normal(0, wobble, 3)
        d /= np.linalg.norm(d)
        cur = cur + d * step
        if exact and k == max(2, n) - 1:
            cur = np.array(goal, float)
        xyz.append(cur.copy())
        typ.append(t)
        par.append(last)
        last = len(xyz) - 1
    return last


def follow(xyz, typ, par, start_i, pts, t):
    """Append a polyline (already routed) as a branch from start_i."""
    last = start_i
    for p in pts:
        xyz.append(np.array(p, float))
        typ.append(t)
        par.append(last)
        last = len(xyz) - 1
    return last


def drawn_mossy(at, gc, gc_b):
    """A mossy cell drawn from its description (Amaral 1978; Buckmaster
    1996; Scharfman & Myers 2013; Scharfman 2016): soma in the hilus beside
    the granule cell's hilar mossy-fiber collateral, a thick proximal
    dendrite that ends on that collateral (thorny excrescences take the
    mossy-fiber boutons), more dendrites spread in the hilus and two
    crossing the granule layer; axon collaterals in the hilus and a main
    axon through the hilus and inner molecular layer to another level,
    where it ends on a granule cell's proximal dendrite (the associational
    path). Routed through the atlas layers it really uses."""
    rng = np.random.default_rng(7)
    gx, gt, gp = gc['xyz'], gc['typ'], gc['par']
    hil_code = CODE['hil']
    ax_i = np.nonzero(gt == 2)[0]
    in_hil = ax_i[at.lam(gx[ax_i]) == hil_code]
    if not len(in_hil):
        raise RuntimeError('granule cell has no hilar axon')
    # the thorn: a hilar collateral node in the middle of the hilar run
    cen = gx[in_hil].mean(axis=0)
    thorn_i = in_hil[int(np.argmin(np.linalg.norm(gx[in_hil] - cen, axis=1)))]
    thorn = gx[thorn_i]
    hil = at.voxels_of('hil')
    plane = hil[np.abs(hil[:, 0] - thorn[0]) < 40]
    d = np.linalg.norm(plane - thorn, axis=1)
    gcl = np.concatenate([at.voxels_of('gcl1'), at.voxels_of('gcl2')])
    gcl = gcl[np.abs(gcl[:, 0] - thorn[0]) < 60]
    from scipy.spatial import cKDTree
    dg = cKDTree(gcl).query(plane)[0]
    ok = (d > 55) & (d < 110)
    s = plane[ok][int(np.argmax(dg[ok]))] if ok.any() else plane[int(np.argmin(np.abs(d - 80)))]
    xyz, typ, par = [s], [1], [-1]
    # the thorny dendrite onto the mossy-fiber collateral, exactly
    grow(xyz, typ, par, 0, thorn, 3, rng, step=5.0, wobble=0.12, exact=True)
    near_h = plane[(d > 40) & (d < 320)]
    for _ in range(4):
        tip = grow(xyz, typ, par, 0, near_h[rng.integers(len(near_h))], 3, rng)
        mid = (tip + len(xyz)) // 2
        grow(xyz, typ, par, max(1, tip - 6), near_h[rng.integers(len(near_h))], 3, rng, step=5.0)
    for k in ('mml1', 'mml2'):
        grow(xyz, typ, par, 0, at.nearest(k, s, plane_ap=s[0]), 3, rng)
    # axon: hilar collaterals, then the main axon routed to gc_b's IML dendrite
    a0 = grow(xyz, typ, par, 0, s + np.array([0.0, 0.0, 30.0]), 2, rng, step=8.0)
    for _ in range(4):
        grow(xyz, typ, par, a0, near_h[rng.integers(len(near_h))], 2, rng, step=8.0, wobble=0.35)
    bx, bt = gc_b['xyz'], gc_b['typ']
    de_i = np.nonzero(np.isin(bt, (3, 4)))[0]
    iml = de_i[np.isin(at.lam(bx[de_i]), [CODE['iml1'], CODE['iml2']])]
    if not len(iml):
        raise RuntimeError('target granule cell has no IML dendrite')
    target_i = iml[int(np.argmin(np.linalg.norm(bx[iml] - s, axis=1)))]
    target = bx[target_i]
    lut = np.full(256, 400.0)
    for k2, c in (('hil', 1.0), ('iml1', 1.0), ('iml2', 1.0), ('gcl1', 4.0), ('gcl2', 4.0), ('mml1', 30.0), ('mml2', 30.0)):
        lut[CODE[k2]] = c
    path = route(at, np.array(xyz[a0]), target, lambda sub: lut[sub])
    end = follow(xyz, typ, par, a0, path[1:], 2)
    # a few branches running along the IML near the target and at home
    iml_vox = np.concatenate([at.voxels_of('iml1'), at.voxels_of('iml2')])
    for anchor, n_br in ((target, 3), (s, 3)):
        loc = iml_vox[np.linalg.norm(iml_vox - anchor, axis=1) < 380]
        if not len(loc):
            continue
        base = end if anchor is target else a0
        for _ in range(n_br):
            g = loc[rng.integers(len(loc))]
            p2 = route(at, np.array(xyz[base]), g, lambda sub: lut[sub], pad=120)
            follow(xyz, typ, par, base, p2[1:], 2)
    xyz = np.array(xyz)
    info = {'thorn_on': ('gc', int(thorn_i)), 'thorn_um': [round(float(x), 1) for x in thorn],
            'reaches': ('gc_b', int(target_i)), 'reach_um': [round(float(x), 1) for x in target],
            'axon_end': int(end)}
    return xyz, np.array(typ, np.int16), np.full(len(xyz), 1.0, np.float32), np.array(par, np.int64), info


def stats(at, xyz, typ, par):
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
            acc[k] = acc.get(k, 0.0) + float(seg[i])
        out[arbor] = {k: round(v, 1) for k, v in sorted(acc.items(), key=lambda kv: -kv[1])}
    return out


def closest(at, A, B_xyz, B_mask, layers=None):
    """Closest approach of A's axon nodes (in `layers`, if given) to B's
    nodes under B_mask. Returns (gap, a_index, b_index)."""
    from scipy.spatial import cKDTree
    ai = np.nonzero(A['typ'] == 2)[0]
    if layers:
        ok = np.zeros(256, bool)
        for l in layers:
            ok[CODE[l]] = True
        ai = ai[ok[at.lam(A['xyz'][ai])]]
    bi = np.nonzero(B_mask)[0]
    if not len(ai) or not len(bi):
        return None
    d, j = cKDTree(B_xyz[bi]).query(A['xyz'][ai])
    k = int(np.argmin(d))
    return float(d[k]), int(ai[k]), int(bi[j[k]])


def ais_node(C):
    """The granule cell's axon node nearest 25 um from the soma along the
    axon -- where spikes start (Schmidt-Hieber et al. 2008: 20-30 um)."""
    pl = path_len(C['xyz'], C['par'])
    ax = np.nonzero(C['typ'] == 2)[0]
    return int(ax[int(np.argmin(np.abs(pl[ax] - 25.0)))])


def main():
    at = Atlas()
    built = {}
    arrays, cells, allstats = [], [], {}
    for spec in INSTANCES:
        key = spec['key']
        kind = spec['kind']
        story = None
        src = {'kind': kind}
        if kind == 'drawn':
            xyz, typ, rad, par, info = drawn_mossy(at, built[spec['near']], built[spec['reach']])
            src.update({'note': 'No public mouse or rat mossy-cell tracing (NeuroMorpho.Org, and every registered hilar cell surveyed, 2026-11-20). Drawn from Amaral 1978, Buckmaster 1996, Scharfman & Myers 2013 and Scharfman 2016; its axon is routed through the hilus and inner molecular layer of the atlas.'})
            story = {'drawn': True, 'thorn_on': info['thorn_on'], 'reaches': info['reaches'],
                     'thorn_um': info['thorn_um'], 'reach_um': info['reach_um']}
        else:
            m = catalog_row(spec['name'])
            ver = 'source' if kind == 'ccf' else 'cng'
            p = cached(spec['name'] + ('.src.swc' if ver == 'source' else '.cng.swc'), swc_url(m, ver), sub='swc')
            xyz, typ, rad, par = parse_swc(p)
            fitscore = None
            mirrored = False
            if kind == 'ccf':
                xyz = xyz[:, [2, 1, 0]]          # MouseLight: (ML, DV, AP) -> (AP, DV, ML)
                s0 = xyz[typ == 1].mean(axis=0) if (typ == 1).any() else xyz[0]
                if s0[2] < MID:                  # mirror into the right hemisphere
                    xyz[:, 2] = 2 * MID - xyz[:, 2]
                    mirrored = True
            xyz, typ, rad, par = simplify(xyz, typ, rad, par, step=spec.get('step', 8.0 if kind == 'slice' else 20.0))
            if kind == 'slice':
                near = None
                if spec.get('near'):
                    tgt = built[spec['near'][0]]
                    near = (np.array(tgt['soma']), spec['near'][1])
                if spec.get('reaches'):
                    # among the near-best layer fits, the one already closest to its target
                    cands = fit_place(xyz, typ, par, at, spec['fit'], near=near, top=400)
                    best_sc = cands[0][1]
                    tk, what, layers = spec['reaches']
                    T = built[tk]
                    if what == 'dend':
                        tmask = np.isin(T['typ'], (3, 4))
                    elif what == 'soma':
                        tmask = T['typ'] == 1
                    else:
                        tmask = np.zeros(len(T['xyz']), bool)
                        tmask[ais_node(T)] = True
                    scored = []
                    for cx, csc in cands:
                        if csc < best_sc - 0.06:
                            continue
                        c = closest(at, {'xyz': cx, 'typ': typ}, T['xyz'], tmask, layers if what == 'dend' else None)
                        scored.append((c[0] if c else 1e9, -csc, cx, csc))
                    scored.sort(key=lambda x: (x[0], x[1]))
                    xyz, fitscore = scored[0][2], scored[0][3]
                    log('   chose fit %.2f (best %.2f) with gap %.1f um' % (fitscore, best_sc, scored[0][0]))
                else:
                    xyz, fitscore = fit_place(xyz, typ, par, at, spec['fit'], near=near)
            src.update({'neuron_name': m['neuron_name'], 'neuron_id': m['neuron_id'],
                        'archive': m['archive'], 'species': m['species'], 'strain': m.get('strain'),
                        'brain_region': m.get('brain_region'), 'cell_type': m.get('cell_type'),
                        'domain': m.get('domain'), 'integrity': m.get('physical_Integrity'),
                        'condition': m.get('experiment_condition'), 'protocol': m.get('protocol'),
                        'doi': m.get('reference_doi'), 'pmid': m.get('reference_pmid'),
                        'url': 'https://neuromorpho.org/neuron_info.jsp?neuron_name=' + urllib.parse.quote(m['neuron_name'])})
            if kind == 'slice':
                src['fit'] = {'score': fitscore, 'layers': spec['fit']}
            if kind == 'ccf':
                src['axes'] = ['ML', 'DV', 'AP']
                src['mirrored'] = mirrored
            # the story: close the synapse onto an upstream axon
            if spec.get('meets'):
                up, layers = spec['meets']
                U = built[up]
                c = closest(at, U, xyz, np.isin(typ, (3, 4)), layers)
                if c:
                    g, ai, bi = c
                    shift = U['xyz'][ai] - xyz[bi]
                    if g <= MAX_NUDGE_UM:
                        xyz = xyz + shift
                    story = {'meets': up, 'gap_um': round(g, 1), 'shift_um': [round(float(x), 2) for x in shift],
                             'moved': g <= MAX_NUDGE_UM, 'up_node': ai, 'node': bi,
                             'at_um': [round(float(x), 1) for x in U['xyz'][ai]],
                             'layer': at.lam_key.get(int(at.lam(U['xyz'][ai][None])[0]), '')}
                    log('   meets', up, 'gap %.1f um at' % g, story['layer'], '-> shifted' if story['moved'] else '-> left (too far)')
            if spec.get('reaches'):
                tk, what, layers = spec['reaches']
                T = built[tk]
                me = {'xyz': xyz, 'typ': typ}
                if what == 'dend':
                    c = closest(at, me, T['xyz'], np.isin(T['typ'], (3, 4)), layers)
                    if c:
                        g, ai, bi = c
                        goal = T['xyz'][bi]
                elif what == 'soma':
                    si = int(np.nonzero(T['typ'] == 1)[0][0]) if (T['typ'] == 1).any() else 0
                    m2 = np.zeros(len(T['xyz']), bool)
                    m2[si] = True
                    c = closest(at, me, T['xyz'], m2, None)
                    if c:
                        g, ai, bi = c
                        v = xyz[ai] - T['xyz'][bi]
                        goal = T['xyz'][bi] + v / max(1e-6, np.linalg.norm(v)) * 6.0   # on the soma's surface
                else:   # ais
                    bi = ais_node(T)
                    m2 = np.zeros(len(T['xyz']), bool)
                    m2[bi] = True
                    c = closest(at, me, T['xyz'], m2, None)
                    if c:
                        g, ai, bi = c
                        goal = T['xyz'][bi]
                if c:
                    shift = goal - xyz[ai]
                    moved = float(np.linalg.norm(shift)) <= MAX_NUDGE_UM * 2.5
                    if moved:
                        xyz = xyz + shift
                    story = {'reaches': tk, 'what': what, 'gap_um': round(float(np.linalg.norm(shift)), 1),
                             'shift_um': [round(float(x), 2) for x in shift], 'moved': moved,
                             'node': ai, 'target_node': bi, 'at_um': [round(float(x), 1) for x in goal]}
                    log('   reaches', tk, what, 'gap %.1f um' % story['gap_um'])
        soma = xyz[typ == 1].mean(axis=0) if (typ == 1).any() else xyz[0]
        st = stats(at, xyz, typ, par)
        sl = at.lam(soma[None])[0]
        sa = at.allen(soma[None])[0]
        st['soma_lamina'] = at.lam_key.get(int(sl), 'none')
        st['soma_allen'] = at.acr(sa)
        st['soma_um'] = [round(float(x), 1) for x in soma]
        built[key] = {'xyz': xyz, 'typ': typ, 'par': par, 'soma': soma}
        allstats[key] = {'type': spec['type'], 'source': src, 'stats': st, 'story': story}
        arrays += [('p:' + key, xyz.astype(np.float32)), ('t:' + key, typ.astype(np.uint8)),
                   ('r:' + key, np.clip(rad, 0.1, 30).astype(np.float32)),
                   ('a:' + key, par.astype(np.int32))]
        cells.append({'key': key, 'type': spec['type'], 'n': int(len(xyz)), 'soma_um': st['soma_um'],
                      'soma_lamina': st['soma_lamina'], 'soma_allen': st['soma_allen'],
                      'source': src, 'story': story,
                      'axon_mm': round(sum(st['axon'].values()) / 1000, 2),
                      'dend_mm': round(sum(st['dend'].values()) / 1000, 2)})
        log(key, kind, len(xyz), 'pts; soma in', st['soma_lamina'], '/', st['soma_allen'],
            '| axon top', list(st['axon'].items())[:4], '| dend top', list(st['dend'].items())[:3])
    n = write_blob(os.path.join(OUT, 'cells.shb.gz'), {'kind': 'cells', 'unit': 'um',
                   'order': 'AP,DV,ML', 'cells': cells}, arrays)
    write_json(os.path.join(RAW, 'cells_stats.json'), allstats, compact=False)
    np.savez_compressed(os.path.join(RAW, 'cells_built.npz'),
                        **{k + ':' + f: v[f] for k, v in built.items() for f in ('xyz', 'typ', 'par')})
    log('cells', n // 1024, 'KB')


if __name__ == '__main__':
    main()
