import os, sys
import numpy as np
import pymupdf
HERE = os.path.dirname(os.path.abspath(__file__))
fid, x0, x1, y0, y1 = sys.argv[1], *map(float, sys.argv[2:6])
page = pymupdf.open(os.path.join(HERE, "svgpdf", fid + ".pdf"))[0]
pix = page.get_pixmap(matrix=pymupdf.Matrix(4, 4), clip=pymupdf.Rect(x0, y0, x1, y1))
a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].astype(int)
bg = np.array([252, 252, 251])
ink = (np.abs(a - bg).sum(axis=2) > 40).any(axis=1)
out, start = [], None
for i, v in enumerate(ink):
    if not v and start is None:
        start = i
    if v and start is not None:
        out.append("%.1f-%.1f" % (y0 + start / 4, y0 + i / 4)); start = None
if start is not None:
    out.append("%.1f-%.1f" % (y0 + start / 4, y1))
print(fid, "blank rows:", ", ".join(out))
