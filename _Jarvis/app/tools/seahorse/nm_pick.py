# -*- coding: utf-8 -*-
"""Rank NeuroMorpho candidates for each Seahorse cell type.

Mouse first (Seahorse is a mouse atlas). A type with no mouse tracing on
NeuroMorpho falls back to rat, and the cell carries that fact on screen.

    python tools/seahorse/nm_pick.py           print the top candidates
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RAW, get_json, log  # noqa: E402

API = 'https://neuromorpho.org/api/neuron/select?'

# key -> (species, q, [fq...], must-have words in region+type)
SPECS = {
    'gc':    ('mouse', 'cell_type:granule', ['brain_region:"dentate gyrus"'], ['granule']),
    'sgc':   ('mouse', 'cell_type:"semilunar granule"', [], ['semilunar']),
    'mc':    ('rat',   'cell_type:mossy', [], ['mossy']),
    'hipp':  ('mouse', 'cell_type:HIPP', [], ['hipp']),
    'pvbc':  ('mouse', 'cell_type:basket', ['brain_region:"dentate gyrus"'], ['basket']),
    'aac':   ('rat',   'cell_type:"axo-axonic"', [], ['axo']),
    'aac_m': ('mouse', 'cell_type:Chandelier', ['brain_region:hippocampus'], ['chandelier']),
    'stel':  ('mouse', 'cell_type:stellate', ['brain_region:"entorhinal cortex"'], ['stellate']),
    'fan':   ('mouse', 'brain_region:"layer 2"', ['brain_region:lateral', 'brain_region:"entorhinal cortex"', 'cell_type:"principal cell"'], []),
    'fan_r': ('rat',   'cell_type:fan', [], ['fan']),
    'ca3':   ('mouse', 'cell_type:pyramidal', ['brain_region:CA3'], ['pyramidal']),
    'ca1':   ('mouse', 'cell_type:pyramidal', ['brain_region:CA1'], ['pyramidal']),
    'olm':   ('mouse', 'cell_type:"oriens-lacunosum moleculare"', [], ['oriens']),
}


def search(species, q, fqs):
    out = []
    page = 0
    while page < 6:
        params = [('q', q), ('fq', 'species:' + species)] + [('fq', f) for f in fqs]
        params += [('size', 500), ('page', page)]
        try:
            d = get_json(API + urllib.parse.urlencode(params))
        except Exception as e:
            return out
        out += d.get('_embedded', {}).get('neuronResources', [])
        if page + 1 >= d.get('page', {}).get('totalPages', 0):
            break
        page += 1
    return out


def score(n):
    s = 0
    dom = (n.get('domain') or '')
    integ = (n.get('physical_Integrity') or '')
    cond = ' '.join(n.get('experiment_condition') or [])
    if 'Axon' in dom: s += 3
    if 'Dendrites' in dom: s += 3
    if 'Soma' in dom: s += 1
    if 'Complete' in integ and 'Dendrites' in integ: s += 3
    if 'Axon' in integ and 'Complete' in integ: s += 2
    if 'Control' in cond: s += 3
    if n.get('protocol') == 'in vivo': s += 1
    if n.get('age_classification') in ('adult', 'young adult'): s += 2
    if '3D' in (n.get('attributes') or ''): s += 1
    try:
        vol = float(n.get('volume') or 0)
        s += min(2, vol / 5000.0)
    except Exception:
        pass
    return s


def main():
    picks = {}
    for key, (sp, q, fqs, words) in SPECS.items():
        rows = search(sp, q, fqs)
        if words:
            rows = [n for n in rows if all(w in (' '.join(n.get('cell_type', []) + n.get('brain_region', []))).lower() for w in words)]
        rows.sort(key=score, reverse=True)
        log(key, sp, len(rows))
        for n in rows[:6]:
            print('   %5.1f %-28s %-14s %s | %s | %s | %s | %s' % (
                score(n), n['neuron_name'], n['archive'], '/'.join(n['brain_region'][:4]),
                ','.join(n['cell_type'][:4]), n.get('domain'), n.get('physical_Integrity'),
                ','.join(n.get('experiment_condition') or [])))
        picks[key] = rows[:12]
    with open(os.path.join(RAW, 'nm_candidates.json'), 'w', encoding='utf-8') as f:
        json.dump(picks, f)


if __name__ == '__main__':
    main()
