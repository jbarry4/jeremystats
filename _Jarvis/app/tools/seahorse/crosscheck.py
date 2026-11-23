# -*- coding: utf-8 -*-
"""Seahorse auto cross-check: test what the schematic claims against data.

    python tools/seahorse/crosscheck.py      -> web/seahorse/checks.json

Three kinds of test, each with a verdict the tab shows beside the claim:

  Allen connectivity   for a region-level connection A -> B: every Allen
                       Mouse Connectivity experiment whose primary injection
                       is in A; projection density in B (both hemispheres)
                       against the same experiments' density in cerebellum
                       (a structure none of these project to). supported if
                       the median is >= 0.002 and >= 5x the control.
  tracings             for a cell-level connection: the share of the
                       exemplar's axon (or dendrite) length in the layers the
                       claim names. 'evidence' when the tracing was registered
                       to CCF by its authors; 'placement' when the cell was
                       traced in a slice and placed here by fit -- then it only
                       says the placement is sane.
  laminae vs Nissl     each derived layer's mean Nissl density: granule and
                       pyramidal layers must be denser than their neighbors.

Plus findings: things the checks turned up about the sources themselves.
"""
import datetime
import os
import sys
import urllib.parse

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import OUT, RAW, by_acronym, get_json, log, ontology, read_json, write_json  # noqa: E402
from volume import CODE  # noqa: E402

API = 'https://api.brain-map.org/api/v2/data/query.json?criteria='
CONTROL = 'CB'


def experiments(sid, flat):
    """Experiments whose primary injection is in sid (or under it). The
    service's primary_structure_only filter fails server-side for some
    structures (SUB, CA2 on 2026-11-20); then ask without it and keep the
    experiments whose primary structure is sid or a descendant."""
    import time
    base = API + 'service::mouse_connectivity_injection_structure[injection_structures$eq%d]' % sid
    for attempt in range(3):
        d = get_json(base + '[primary_structure_only$eqtrue]')
        if d.get('success') and isinstance(d.get('msg'), list):
            return d['msg']
        time.sleep(1.0 + attempt)
    for attempt in range(3):
        d = get_json(base)
        if d.get('success') and isinstance(d.get('msg'), list):
            keep = [e for e in d['msg'] if e.get('structure-id') in flat
                    and sid in flat[e['structure-id']]['path']]
            return keep
        time.sleep(1.0 + attempt)
    return []


def unionize(exp_ids, sids):
    rows = []
    for i in range(0, len(exp_ids), 40):
        chunk = exp_ids[i:i + 40]
        q = ('model::ProjectionStructureUnionize,rma::criteria,'
             '[section_data_set_id$in%s][structure_id$in%s][is_injection$eqfalse][hemisphere_id$eq3],'
             'rma::options[num_rows$eqall]' % (','.join(map(str, chunk)), ','.join(map(str, sids))))
        d = get_json(API + urllib.parse.quote(q, safe='[]$:,()='))
        rows += d.get('msg', [])
    return rows


def allen_check(A, src, tgt, cache, flat):
    s, t, c = A[src]['id'], A[tgt]['id'], A[CONTROL]['id']
    if src not in cache:
        cache[src] = experiments(s, flat)
    exps = cache[src]
    if not exps:
        return {'status': 'untested', 'evidence': 'allen', 'detail': 'No Allen experiment has its primary injection in %s.' % src}
    ids = [e['id'] for e in exps]
    rows = unionize(ids, [t, c])
    dens = {}
    for r in rows:
        dens.setdefault(r['section_data_set_id'], {})[r['structure_id']] = r['projection_density']
    tv = np.array([dens.get(i, {}).get(t, 0.0) for i in ids])
    cv = np.array([dens.get(i, {}).get(c, 0.0) for i in ids])
    med, ctl = float(np.median(tv)), float(np.median(cv))
    n_hit = int((tv >= 0.002).sum())
    ok = med >= 0.002 and med >= 5 * max(ctl, 1e-5)
    weak = not ok and n_hit >= max(1, len(ids) // 4)
    lines = sorted(({'id': i, 'line': e.get('transgenic-line') or 'wild type', 'density': round(float(v), 4)}
                    for i, e, v in zip(ids, exps, tv)), key=lambda x: -x['density'])
    return {'status': 'supported' if ok else ('weak' if weak else 'not seen'), 'evidence': 'allen',
            'detail': '%d Allen experiments injected in %s; median projection density in %s %.4f '
                      '(cerebellum control %.4f); %d of %d at or above 0.002.' % (
                          len(ids), src, tgt, med, ctl, n_hit, len(ids)),
            'median': round(med, 5), 'control': round(ctl, 5), 'n': len(ids), 'top': lines[:5]}


def frac(stats, arbor, keys, flat, A):
    d = stats.get(arbor) or {}
    tot = sum(d.values())
    if tot <= 0:
        return None, 0.0
    allen_ids = [A[k]['id'] for k in keys if k in A and k not in CODE]
    hit = 0.0
    for k, v in d.items():
        if k in keys:
            hit += v
        elif k in A and any(a in flat[A[k]['id']]['path'] for a in allen_ids):
            hit += v
    return hit / tot, tot


EXPECT_SOMA = {'gc': ['gcl1', 'gcl2'], 'ca3': ['ca3sp'], 'ca1': ['ca1sp'], 'fan': ['ENTl2'],
               'sgc': ['iml1', 'iml2', 'mml1'], 'hipp': ['hil'], 'pvbc': ['gcl1', 'gcl2', 'hil'],
               'aac': ['gcl1', 'gcl2', 'hil'], 'olm': ['ca1so'], 'stel': ['ENTm2'], 'mc': ['hil']}


def main():
    flat = ontology()
    A = by_acronym(flat)
    kb = read_json(os.path.join(OUT, 'kb.json'))
    cs = read_json(os.path.join(RAW, 'cells_stats.json'))
    out = {'ran': datetime.date.today().isoformat(), 'connections': {}, 'cells': {}, 'lamina': [],
           'findings': [], 'method': __doc__.strip()}
    cache = {}
    for c in kb['connections']:
        chk = c.get('check')
        if not chk:
            out['connections'][c['key']] = {'status': 'cited', 'evidence': 'literature',
                                            'detail': 'Cited, not tested: no public dataset here can test this one.'}
            continue
        if 'allen' in chk:
            try:
                r = allen_check(A, chk['allen'][0], chk['allen'][1], cache, flat)
            except Exception as e:
                r = {'status': 'error', 'evidence': 'allen', 'detail': 'Allen API: %s' % e}
            out['connections'][c['key']] = r
            log(c['key'], r['status'], r['detail'])
        elif 'cell' in chk:
            ent = cs.get(chk['cell'])
            kind = ent['source']['kind']
            f, tot = frac(ent['stats'], chk['arbor'], chk['in'], flat, A)
            if f is None:
                r = {'status': 'untested', 'evidence': kind, 'detail': 'The exemplar has no traced %s.' % chk['arbor']}
            else:
                good = f >= chk['min']
                name = ent['source'].get('neuron_name', 'drawn cell')
                how = {'ccf': 'evidence: %s was registered to CCFv3 by its authors' % name,
                       'slice': 'placement only: %s was traced in a slice and placed here by fit' % name,
                       'drawn': 'drawn: no tracing exists'}[kind]
                r = {'status': ('supported' if kind == 'ccf' else 'consistent') if good else 'not seen',
                     'evidence': kind, 'fraction': round(f, 3),
                     'detail': '%.0f%% of %.1f mm of %s in %s (needs %.0f%%); %s.' % (
                         100 * f, tot / 1000.0, chk['arbor'], ', '.join(chk['in']), 100 * chk['min'], how)}
            out['connections'][c['key']] = r
            log(c['key'], r['status'], r['detail'])

    # cells: does each soma sit where the cell type lives?
    for key, ent in cs.items():
        st, src = ent['stats'], ent['source']
        where = st['soma_lamina'] if st['soma_lamina'] != 'none' else st['soma_allen']
        ok = where in EXPECT_SOMA.get(key, [])
        res = {'soma': where, 'soma_ok': ok, 'kind': src['kind'], 'notes': []}
        if src['kind'] == 'ccf':
            res['notes'].append('Soma lands in %s (CCF %s um), %s.' % (
                where, ', '.join('%.0f' % x for x in st['soma_um']),
                'as expected' if ok else 'NOT where this type lives'))
        if key == 'fan':
            f, tot = frac(st, 'dend', ['ENTl1'], flat, A)
            res['notes'].append('Dendrites in layer I: %.0f%% of %.1f mm. Fan cells send their dendrites up into layer I; '
                                'this one keeps them in %s, so its identity as a fan cell is unconfirmed '
                                '(NeuroMorpho lists it only as a LEC layer II principal cell).' % (
                                    100 * (f or 0), tot / 1000, ', '.join(list(st['dend'])[:2])) if (f or 0) < 0.1 else
                                'Dendrites reach layer I (%.0f%%), as fan cells do.' % (100 * f))
            res['identity'] = 'unconfirmed' if (f or 0) < 0.1 else 'consistent'
        if key == 'mc':
            res['identity'] = 'drawn'
        if src.get('fit'):
            res['notes'].append('Placed by fit (score %.2f of 1.1): soma in %s.' % (src['fit']['score'], where))
        out['cells'][key] = res

    # laminae vs Nissl
    L = np.load(os.path.join(RAW, 'hip10_labels.npy'))
    N = np.load(os.path.join(RAW, 'hip10_nissl.npy'))
    mean = {k: float(N[L == v].mean()) for k, v in CODE.items() if v and (L == v).any()}
    for dense, thin in (('gcl1', ['iml1', 'hil', 'mml1']), ('gcl2', ['iml2', 'hil', 'mml2']),
                        ('ca1sp', ['ca1so', 'ca1sr']), ('ca3sp', ['ca3so', 'ca3slu', 'ca3sr']),
                        ('ca2sp', ['ca2so', 'ca2sr'])):
        r = min(mean[dense] / max(1e-3, mean[t]) for t in thin)
        out['lamina'].append({'layer': dense, 'vs': thin, 'ratio': round(r, 2), 'ok': r > 1.15,
                              'detail': 'Mean Nissl in %s is %.2fx the densest of %s.' % (dense, r, ', '.join(thin))})
        log('lamina', dense, round(r, 2))
    out['nissl_means'] = {k: round(v, 1) for k, v in mean.items()}

    out['findings'] = [
        {'about': 'gc', 'text': 'NeuroMorpho lists MouseLight AA0998 as a dentate granule cell, but its axon is 108 mm long and stays in the molecular layer; real MouseLight granule cells have 3-5 mm axons through the hilus into CA3. AA0998 is not used; AA0091 is.'},
        {'about': 'ccf', 'text': 'MouseLight source files are (ML, DV, AP); SEU-ALLEN (Peng) files are (AP, DV, ML). Found by checking which order puts each soma in the region its authors named.'},
        {'about': 'ca1', 'text': 'MouseLight AA0960, listed as CA1, has its soma in CA3 by the CCFv3 annotation (near the border); AA0959 (soma in CA1 sp) is used instead.'},
        {'about': 'mc', 'text': 'No mouse or rat mossy-cell tracing is on NeuroMorpho.Org (searched 2026-11-20); the mossy cell is drawn from published descriptions.'},
        {'about': 'ca', 'text': 'CCFv3 does not annotate CA strata or the thirds of the molecular layer; Seahorse derives them (see each layer), and the Nissl test above is how they are checked.'},
    ]
    write_json(os.path.join(OUT, 'checks.json'), out, compact=False)
    log('checks.json written')


if __name__ == '__main__':
    main()
