"""dev helper: render a source region with a point grid (every 5 pt, labelled every 10) to read tick positions."""
import sys, fitz
from PIL import Image, ImageDraw
pdf, x0, y0, x1, y1 = sys.argv[1], *map(float, sys.argv[2:6]); out = sys.argv[6]; z = float(sys.argv[7]) if len(sys.argv) > 7 else 6
pg = fitz.open(pdf)[0]
pix = pg.get_pixmap(clip=fitz.Rect(x0, y0, x1, y1), matrix=fitz.Matrix(z, z), alpha=False)
im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
d = ImageDraw.Draw(im)
import math
for gx in range(int(math.ceil(x0 / 5) * 5), int(x1) + 1, 5):
    X = (gx - x0) * z
    d.line([(X, 0), (X, im.height)], fill=(0, 200, 255) if gx % 10 else (255, 0, 200), width=1)
    if gx % 10 == 0:
        d.text((X + 2, 2), str(gx), fill=(255, 0, 200))
for gy in range(int(math.ceil(y0 / 5) * 5), int(y1) + 1, 5):
    Y = (gy - y0) * z
    d.line([(0, Y), (im.width, Y)], fill=(0, 200, 255) if gy % 10 else (255, 0, 200), width=1)
    if gy % 10 == 0:
        d.text((2, Y + 2), str(gy), fill=(255, 0, 200))
im.save(out)
print(im.size)
