"""Print the blank horizontal bands (and, inside a y range, vertical bands) of a figure, in PDF points.

  python gaps.py 39            horizontal bands over the whole figure
  python gaps.py 39 80 240     vertical bands within y 80..240
"""
import os
import sys

import numpy as np
import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
fid = sys.argv[1]
page = pymupdf.open(os.path.join(HERE, "svgpdf", fid + ".pdf"))[0]
pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].astype(int)
bg = a[2, 2]
ink = (np.abs(a - bg).sum(axis=2) > 40)


def bands(mask_1d, minlen=3):
    out, start = [], None
    for i, blank in enumerate(mask_1d):
        if blank and start is None:
            start = i
        if not blank and start is not None:
            if i - start >= minlen:
                out.append((start / 2, i / 2))
            start = None
    if start is not None and len(mask_1d) - start >= minlen:
        out.append((start / 2, len(mask_1d) / 2))
    return out


if len(sys.argv) == 2:
    rows = ~ink.any(axis=1)
    print("H blank bands (pt):", ", ".join("%.0f-%.0f" % b for b in bands(rows)))
else:
    y0, y1 = float(sys.argv[2]), float(sys.argv[3])
    sub = ink[int(y0 * 2):int(y1 * 2)]
    cols = ~sub.any(axis=0)
    print("V blank bands in y %g-%g (pt):" % (y0, y1), ", ".join("%.0f-%.0f" % b for b in bands(cols)))
