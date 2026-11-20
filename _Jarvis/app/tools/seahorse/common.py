# -*- coding: utf-8 -*-
"""Shared bits for the Seahorse build (tools/seahorse/).

Seahorse is the mouse-brain atlas tab. Everything it shows is built here,
offline, from public sources, into web/seahorse/ -- the app never calls out
to the Allen Institute or NeuroMorpho while you use it.

    RAW   %LOCALAPPDATA%/Jarvis/seahorse_raw   downloads, never committed
    OUT   web/seahorse/                         what the tab loads (committed)

Sources and licences (also written into web/seahorse/manifest.json so the
tab can show them):
  Allen Mouse Brain Common Coordinate Framework v3 (CCFv3, 2017 annotation),
    Wang Q et al. 2020 Cell 181:936-953. Allen Institute terms of use, CC BY 4.0
    style attribution: (c) 2015 Allen Institute for Brain Science.
  Allen Mouse Brain Connectivity Atlas, Oh SW et al. 2014 Nature 508:207-214.
  NeuroMorpho.Org, Ascoli GA et al. 2007 J Neurosci 27:9247-9251; each cell
    keeps its own archive and reference.
"""
import gzip
import io
import json
import os
import struct
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(APP, 'web', 'seahorse')
RAW = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
                   'Jarvis', 'seahorse_raw')

CCF = ('https://download.alleninstitute.org/informatics-archive/'
       'current-release/mouse_ccf')
UA = {'User-Agent': 'jarvis-seahorse-build/1.0'}


def ensure(*parts):
    p = os.path.join(*parts)
    os.makedirs(p, exist_ok=True)
    return p


def get(url, tries=4, timeout=120):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            last = e
        except Exception as e:  # network blips
            last = e
        time.sleep(1.5 * (i + 1))
    raise last


def cached(name, url, sub=''):
    """Download once into RAW; return the local path."""
    d = ensure(RAW, sub) if sub else ensure(RAW)
    p = os.path.join(d, name)
    if not os.path.exists(p) or os.path.getsize(p) == 0:
        data = get(url, timeout=600)
        tmp = p + '.part'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, p)
    return p


def get_json(url):
    return json.loads(get(url).decode('utf-8'))


def write_json(path, obj, compact=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        if compact:
            json.dump(obj, f, separators=(',', ':'), ensure_ascii=False)
        else:
            json.dump(obj, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def write_blob(path, header, arrays):
    """One gzip'd file the browser reads with DecompressionStream:

        'SHB1' | u32 header length | header JSON (utf-8) | pad to 8 |
        array bytes, each padded to 8

    header['arrays'] lists {name, dtype, shape, offset, nbytes}; offsets are
    from the start of the (uncompressed) array section.
    """
    import numpy as np
    meta = []
    off = 0
    chunks = []
    for name, a in arrays:
        a = np.ascontiguousarray(a)
        b = a.tobytes()
        meta.append({'name': name, 'dtype': str(a.dtype), 'shape': list(a.shape),
                     'offset': off, 'nbytes': len(b)})
        pad = (-len(b)) % 8
        chunks.append(b + b'\0' * pad)
        off += len(b) + pad
    header = dict(header)
    header['arrays'] = meta
    hj = json.dumps(header, separators=(',', ':')).encode('utf-8')
    hj += b' ' * ((-(8 + len(hj))) % 8)
    raw = b'SHB1' + struct.pack('<I', len(hj)) + hj + b''.join(chunks)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(gzip.compress(raw, 9))
    os.replace(tmp, path)
    return os.path.getsize(path)


def ontology():
    """Allen structure graph 1 (adult mouse), flattened by id."""
    p = cached('structure_graph_1.json',
               'https://api.brain-map.org/api/v2/structure_graph_download/1.json')
    with open(p, encoding='utf-8') as f:
        root = json.load(f)['msg'][0]
    flat = {}

    def walk(n, path):
        path = path + [n['id']]
        flat[n['id']] = {'id': n['id'], 'acronym': n['acronym'], 'name': n['name'],
                         'parent': n.get('parent_structure_id'),
                         'color': '#' + n['color_hex_triplet'], 'path': path,
                         'children': [c['id'] for c in n.get('children', [])]}
        for c in n.get('children', []):
            walk(c, path)
    walk(root, [])
    return flat


def by_acronym(flat):
    return {v['acronym']: v for v in flat.values()}


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)
