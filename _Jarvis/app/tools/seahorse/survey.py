# -*- coding: utf-8 -*-
"""Survey the whole-brain, atlas-registered tracings (MouseLight, Winnubst
2019; SEU-ALLEN / Peng) of hippocampal and entorhinal neurons: where each
soma sits, where its axon and dendrites go, and which pairs come close
enough to be shown as a synapse in the rides.

    python tools/seahorse/survey.py            download what is missing, survey
    python tools/seahorse/survey.py --pairs    only redo the pair search

Cells from different mice share one frame only through registration, which
is good to roughly 50-100 um. So "close" here means: an axon of A passes
within CONTACT_UM of a dendrite of B, in the layer where that connection is
known to synapse. The rides then nudge B by that gap at most (flagged in the
tab as "positioned for the story").

Writes RAW/survey.json.
"""
import json
import os
import sys
import urllib.parse

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RAW, cached, log, read_json, write_json  # noqa: E402
from cells import Atlas, parse_swc, swc_url  # noqa: E402
from volume import CODE  # noqa: E402

MID = 5700.0
CONTACT_UM = 150.0

# The expected layer of each synapse in a ride (lamina keys; Allen acronyms
# where Seahorse has no laminae).
EDGES = {
    'ec_gc':   {'from': ('ec2',), 'to': ('gc',), 'layers': ['oml1', 'oml2', 'mml1', 'mml2']},
    'gc_ca3':  {'from': ('gc',), 'to': ('ca3',), 'layers': ['ca3slu', 'ca3sp', 'ca3sr']},
    'gc_mc':   {'from': ('gc',), 'to': ('mc',), 'layers': ['hil']},
    'mc_gc':   {'from': ('mc',), 'to': ('gc',), 'layers': ['iml1', 'iml2']},
    'ca3_ca1': {'from': ('ca3',), 'to': ('ca1',), 'layers': ['ca1sr', 'ca1so']},
    'ca3_ca3': {'from': ('ca3',), 'to': ('ca3',), 'layers': ['ca3sr', 'ca3so']},
    'ec_ca1':  {'from': ('ec3',), 'to': ('ca1',), 'layers': ['ca1slm']},
}


def candidates():
    rows = json.load(open(os.path.join(RAW, 'neuromorpho_catalog.json'), encoding='utf-8'))
    out = []
    for n in rows:
        reg = ' / '.join(n.get('brain_region') or [])
        dom = n.get('domain') or ''
        if 'Axon' not in dom or 'Dendrites' not in dom:
            continue
        if n['archive'] == 'MouseLight':
            out.append(n)
        elif n['archive'] == 'Peng':
            ct = ', '.join(n.get('cell_type') or [])
            principal = 'principal' in ct or 'Unknown' in ct
            if not principal:
                continue
            if 'entorhinal' in reg and ('layer 2' in reg or 'layer 3' in reg):
                out.append(n)
            elif reg.startswith('hippocampus') and ('dentate' in reg or 'CA3' in reg or 'hilus' in reg):
                out.append(n)
    log('candidates', len(out))
    return out


def axes_for(n):
    # MouseLight Source-Version files are (ML, DV, AP); SEU-ALLEN (Peng) are
    # (AP, DV, ML) -- checked by which order puts somata where the authors say.
    return (2, 1, 0) if n['archive'] == 'MouseLight' else (0, 1, 2)


def load(n):
    p = cached(n['neuron_name'] + '.src.swc', swc_url(n, 'source'), sub='swc')
    xyz, typ, rad, par = parse_swc(p)
    xyz = xyz[:, list(axes_for(n))]
    return xyz, typ, rad, par


def resample(xyz, typ, par, step=5.0):
    """Points every `step` um along every segment, with their arbor type."""
    pts, ts = [], []
    for i in range(len(xyz)):
        p = par[i]
        if p < 0:
            continue
        a, b = xyz[p], xyz[i]
        L = float(np.linalg.norm(b - a))
        k = max(1, int(L / step))
        f = (np.arange(k) + 0.5) / k
        pts.append(a + (b - a) * f[:, None])
        ts.append(np.full(k, typ[i], np.int16))
    if not pts:
        return np.zeros((0, 3)), np.zeros(0, np.int16)
    return np.concatenate(pts), np.concatenate(ts)


def mirror_right(p):
    q = np.array(p, float, copy=True)
    left = q[:, 2] < MID
    q[left, 2] = 2 * MID - q[left, 2]
    return q


def classify(at, soma, dend_lam, axon_lam, soma_lam, soma_allen):
    """A role for the rides, from where the soma and arbors are."""
    sl = soma_lam
    tot_ax = sum(axon_lam.values()) or 1
    tot_de = sum(dend_lam.values()) or 1
    frac = lambda d, keys, tot: sum(v for k, v in d.items() if k in keys) / tot
    ml = ['iml1', 'iml2', 'mml1', 'mml2', 'oml1', 'oml2']
    if sl in ('gcl1', 'gcl2', 'iml1', 'iml2') and frac(dend_lam, ml, tot_de) > 0.4:
        return 'gc'
    if sl == 'hil' and frac(axon_lam, ['iml1', 'iml2'], tot_ax) > 0.15:
        return 'mc'
    if sl in ('ca3sp', 'ca3so', 'ca3slu', 'ca3sr'):
        return 'ca3'
    if sl in ('ca1sp', 'ca1so', 'ca1sr'):
        return 'ca1'
    if sl in ('ca2sp', 'ca2so'):
        return 'ca2'
    if soma_allen.startswith('ENTm2') or soma_allen.startswith('ENTl2'):
        return 'ec2'
    if soma_allen.startswith('ENTm3') or soma_allen.startswith('ENTl3'):
        return 'ec3'
    if soma_allen.startswith('ENT'):
        return 'ec_deep'
    if sl == 'hil':
        return 'hilar'
    return 'other'


def survey():
    at = Atlas()
    cands = candidates()
    out = {}
    for n in cands:
        name = n['neuron_name']
        try:
            xyz, typ, rad, par = load(n)
        except Exception as e:  # noqa: BLE001
            log('skip', name, e)
            continue
        if not len(xyz):
            continue
        soma = xyz[typ == 1].mean(axis=0) if (typ == 1).any() else xyz[0]
        flip = soma[2] < MID
        pts, ts = resample(xyz, typ, par, step=10.0)
        pr = mirror_right(pts)
        sr = mirror_right(soma[None])[0]
        lam = at.lam(pr)
        al = at.allen(pr)
        acc = {'dend': {}, 'axon': {}}
        for arbor, m in (('dend', np.isin(ts, (3, 4))), ('axon', ts == 2)):
            for code, sid in zip(lam[m], al[m]):
                k = at.lam_key.get(int(code), 'none')
                if k == 'none':
                    k = at.acr(sid) or 'outside'
                acc[arbor][k] = acc[arbor].get(k, 0) + 10.0
        sl = at.lam_key.get(int(at.lam(sr[None])[0]), 'none')
        sa = at.acr(at.allen(sr[None])[0])
        role = classify(at, sr, acc['dend'], acc['axon'], sl, sa)
        out[name] = {'archive': n['archive'], 'neuron_id': n['neuron_id'], 'region': n.get('brain_region'),
                     'cell_type': n.get('cell_type'), 'soma_um': [round(float(x), 1) for x in soma],
                     'left': bool(flip), 'soma_lamina': sl, 'soma_allen': sa, 'role': role,
                     'axon_um': round(sum(acc['axon'].values())), 'dend_um': round(sum(acc['dend'].values())),
                     'axon': dict(sorted(acc['axon'].items(), key=lambda kv: -kv[1])[:12]),
                     'dend': dict(sorted(acc['dend'].items(), key=lambda kv: -kv[1])[:8]),
                     'doi': n.get('reference_doi')}
        log(name, n['archive'], role, 'soma', sl, sa, 'axon', list(out[name]['axon'].items())[:3])
    write_json(os.path.join(RAW, 'survey.json'), out, compact=False)
    return out


def pairs(sv):
    """For each ride edge: the closest axon-to-dendrite approaches, in the
    synapse's layer, between every candidate pair (right hemisphere frame)."""
    from scipy.spatial import cKDTree
    at = Atlas()
    rows = {n['neuron_name']: n for n in json.load(open(os.path.join(RAW, 'neuromorpho_catalog.json'), encoding='utf-8'))}
    cache = {}

    def arbor(name, kind):
        if (name, kind) in cache:
            return cache[(name, kind)]
        xyz, typ, rad, par = load(rows[name])
        soma = xyz[typ == 1].mean(axis=0) if (typ == 1).any() else xyz[0]
        if soma[2] < MID:
            xyz = xyz.copy()
            xyz[:, 2] = 2 * MID - xyz[:, 2]
        pts, ts = resample(xyz, typ, par, step=5.0)
        m = (ts == 2) if kind == 'axon' else np.isin(ts, (3, 4))
        cache[(name, kind)] = pts[m]
        return pts[m]

    found = {}
    for ek, e in EDGES.items():
        A = [k for k, v in sv.items() if v['role'] in e['from']]
        B = [k for k, v in sv.items() if v['role'] in e['to']]
        codes = np.zeros(256, bool)
        for l in e['layers']:
            codes[CODE[l]] = True
        res = []
        for a in A:
            ax = arbor(a, 'axon')
            if not len(ax):
                continue
            ok = codes[at.lam(ax)]
            ax = ax[ok]
            if not len(ax):
                continue
            for b in B:
                if a == b:
                    continue
                de = arbor(b, 'dend')
                if not len(de):
                    continue
                d, j = cKDTree(de).query(ax)
                i = int(np.argmin(d))
                res.append({'from': a, 'to': b, 'gap_um': round(float(d[i]), 1),
                            'at_axon': [round(float(x), 1) for x in ax[i]],
                            'at_dend': [round(float(x), 1) for x in de[j[i]]],
                            'n_within_50': int((d < 50).sum())})
        res.sort(key=lambda r: r['gap_um'])
        found[ek] = res[:12]
        log(ek, len(A), 'x', len(B), 'best', [(r['from'], r['to'], r['gap_um']) for r in res[:5]])
    sv['_pairs'] = found
    write_json(os.path.join(RAW, 'survey.json'), sv, compact=False)


if __name__ == '__main__':
    if '--pairs' in sys.argv:
        pairs(read_json(os.path.join(RAW, 'survey.json')))
    else:
        pairs(survey())
