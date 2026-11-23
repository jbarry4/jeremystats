# -*- coding: utf-8 -*-
"""Pull NeuroMorpho.Org metadata for every mouse hippocampal / entorhinal
reconstruction, so exemplar cells are chosen from the full list rather than
from whatever a keyword search happens to match.

    python tools/seahorse/nm_catalog.py            crawl + summarise
    python tools/seahorse/nm_catalog.py --summary  summarise the cached crawl

Writes RAW/neuromorpho_catalog.json.
"""
import collections
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RAW, ensure, get_json, log  # noqa: E402

API = 'https://neuromorpho.org/api/neuron/select?'
REGIONS = ['hippocampus', 'entorhinal cortex']


def crawl():
    rows = {}
    for reg in REGIONS:
        page = 0
        while True:
            q = urllib.parse.urlencode({'q': 'brain_region:"%s"' % reg,
                                        'fq': 'species:mouse',
                                        'size': 500, 'page': page})
            try:
                d = get_json(API + q)
            except Exception as e:
                log('stop', reg, page, e)
                break
            got = d.get('_embedded', {}).get('neuronResources', [])
            for n in got:
                rows[n['neuron_id']] = n
            tp = d.get('page', {}).get('totalPages', 0)
            log(reg, 'page', page + 1, '/', tp, len(rows))
            page += 1
            if page >= tp:
                break
    ensure(RAW)
    with open(os.path.join(RAW, 'neuromorpho_catalog.json'), 'w', encoding='utf-8') as f:
        json.dump(list(rows.values()), f)
    return list(rows.values())


def summary(rows):
    c = collections.Counter()
    for n in rows:
        key = ' / '.join(n.get('brain_region', [])[:3]) + '  ||  ' + ', '.join(n.get('cell_type', []))
        c[key] += 1
    for k, v in c.most_common(400):
        print(v, k)


if __name__ == '__main__':
    p = os.path.join(RAW, 'neuromorpho_catalog.json')
    if '--summary' in sys.argv and os.path.exists(p):
        rows = json.load(open(p, encoding='utf-8'))
    else:
        rows = crawl()
    summary(rows)
