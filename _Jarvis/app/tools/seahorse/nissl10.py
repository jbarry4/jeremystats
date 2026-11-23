# -*- coding: utf-8 -*-
"""The real 10 um Allen Nissl (ARA Nissl, CCFv3 2017) over the hippocampal
crop, replacing the 25 um stain upsampled by volume.py.

    python tools/seahorse/nissl10.py           crop + ship
    python tools/seahorse/nissl10.py --ship    ship only (from RAW)

ara_nissl_10.nrrd is 2.2 GB (float32, gzip, AP fastest, ML slowest). It is
streamed and only the hippocampal crop (the same box as hip10_labels.npy) is
kept: RAW/hip10_nissl_true.npy, uint8, 0-255 with 255 at the 99.5th
percentile of tissue.

What the tab loads:
  fine10.shb.gz   the dorsal hippocampus at 10 um, where the probes go:
                  labels (uint8 lamina codes) and the Nissl as one JPEG
                  sheet of coronal tiles (grayscale, a twentieth the size of
                  raw bytes; it is a backdrop, not a measurement).
  hip20.shb.gz    rewritten by volume.ship() from the true stain.
"""
import io
import math
import os
import sys
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import OUT, RAW, log, read_json, write_blob  # noqa: E402
from volume import brain_nissl_hi, mode3, read_nrrd_header  # noqa: E402

# The fine box (CCF um): dorsal hippocampus, AP 5800-8800, DV down to 3700.
FINE = {'ap': (5800, 8800), 'dv': (1320, 3700)}
JPEG_Q = 84


def stream_crop_f32(path, ap0, ap1, dv0, dv1, ml0, ml1):
    h, off = read_nrrd_header(path)
    sizes = [int(x) for x in h['sizes'].split()]
    assert h['encoding'] == 'gzip' and h['type'] == 'float', (h['encoding'], h['type'])
    nap, ndv, nml = sizes
    slab = nap * ndv * 4
    out = np.zeros((ap1 - ap0, dv1 - dv0, ml1 - ml0), np.float32)
    d = zlib.decompressobj(31)
    buf = bytearray()
    k = 0
    with open(path, 'rb') as f:
        f.seek(off)
        while k < ml1:
            chunk = f.read(1 << 23)
            if not chunk:
                break
            buf += d.decompress(chunk)
            while len(buf) >= slab and k < ml1:
                if k >= ml0:
                    a = np.frombuffer(bytes(buf[:slab]), np.float32).reshape(ndv, nap)
                    out[:, :, k - ml0] = a[dv0:dv1, ap0:ap1].T
                del buf[:slab]
                k += 1
                if k % 50 == 0:
                    log('  ML slab', k, '/', ml1)
    return out


def crop():
    meta = read_json(os.path.join(RAW, 'hip10_meta.json'))
    o = [v // 10 for v in meta['origin_um']]
    sh = meta['shape']
    log('cropping 10 um Nissl at', meta['origin_um'], 'shape', sh)
    n = stream_crop_f32(os.path.join(RAW, 'ara_nissl_10.nrrd'),
                        o[0], o[0] + sh[0], o[1], o[1] + sh[1], o[2], o[2] + sh[2])
    annot = np.load(os.path.join(RAW, 'hip10_annot.npy'))
    tissue = annot > 0
    hi = brain_nissl_hi()
    log('Nissl in the crop: p99.5 %.1f; scaled by the brain-wide %.1f' % (float(np.percentile(n[tissue], 99.5)), hi))
    u8 = np.clip((n - 0) / hi * 255, 0, 255).astype(np.uint8)
    np.save(os.path.join(RAW, 'hip10_nissl_true.npy'), u8)
    old = np.load(os.path.join(RAW, 'hip10_nissl.npy'))
    sub = (slice(None, None, 3),) * 3
    r = np.corrcoef(u8[sub][tissue[sub]].astype(float), old[sub][tissue[sub]].astype(float))[0, 1]
    log('agreement with the upsampled 25 um stain: r = %.3f' % r)
    return u8


def jpeg_sheet(vol, q=JPEG_Q):
    """Coronal tiles (AP slices of [DV, ML]) on one grayscale JPEG.
    Returns (bytes, cols, rows)."""
    from PIL import Image
    n, h, w = vol.shape
    cols = int(math.ceil(math.sqrt(n * h / w)))
    cols = max(1, min(n, cols))
    rows = int(math.ceil(n / cols))
    sheet = np.zeros((rows * h, cols * w), np.uint8)
    for i in range(n):
        r, c = divmod(i, cols)
        sheet[r * h:(r + 1) * h, c * w:(c + 1) * w] = vol[i]
    im = Image.fromarray(sheet, 'L')
    b = io.BytesIO()
    im.save(b, 'JPEG', quality=q, optimize=True, progressive=False, subsampling=0)
    return b.getvalue(), cols, rows


def ship():
    meta = read_json(os.path.join(RAW, 'hip10_meta.json'))
    origin = meta['origin_um']
    L = np.load(os.path.join(RAW, 'hip10_labels.npy'))
    N = np.load(os.path.join(RAW, 'hip10_nissl_true.npy'))
    a0 = (FINE['ap'][0] - origin[0]) // 10
    a1 = (FINE['ap'][1] - origin[0]) // 10
    d0 = max(0, (FINE['dv'][0] - origin[1]) // 10)
    d1 = (FINE['dv'][1] - origin[1]) // 10
    Lf = np.ascontiguousarray(mode3(L[a0:a1, d0:d1, :]))
    Nf = np.ascontiguousarray(N[a0:a1, d0:d1, :])
    jpg, cols, rows = jpeg_sheet(Nf)
    log('fine Nissl sheet', Nf.shape, '->', cols, 'x', rows, 'tiles,', len(jpg) // 1024, 'KB')
    from volume import DERIVED, HOW, LAMINA
    lam = [{'code': r[0], 'key': r[1], 'label': r[2], 'group': r[3], 'name': r[4],
            'how': DERIVED[HOW[r[1]]] if r[1] in HOW else ''} for r in LAMINA]
    n = write_blob(os.path.join(OUT, 'fine10.shb.gz'),
                   {'kind': 'fine10', 'um': 10, 'order': 'AP,DV,ML',
                    'origin_um': [origin[0] + a0 * 10, origin[1] + d0 * 10, origin[2]],
                    'shape': list(Lf.shape), 'lamina': lam, 'labels_smoothed': '3x3x3 majority (display)',
                    'nissl_jpeg': {'tile': [int(Nf.shape[1]), int(Nf.shape[2])], 'cols': cols, 'rows': rows,
                                   'slices': int(Nf.shape[0]), 'axis': 'AP', 'quality': JPEG_Q}},
                   [('labels', Lf), ('nissl_jpeg', np.frombuffer(jpg, np.uint8))])
    log('fine10', Lf.shape, n // 1024, 'KB')


if __name__ == '__main__':
    if '--ship' not in sys.argv:
        crop()
    ship()
