"""Render a figure PDF with a coordinate grid (in PDF points) so crop boxes can be read off.

  python grid.py 01 [zoom]
writes grid/<id>.png
"""
import os
import sys

import pymupdf
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
fid = sys.argv[1]
zoom = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
doc = pymupdf.open(os.path.join(HERE, "svgpdf", fid + ".pdf"))
page = doc[0]
pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
d = ImageDraw.Draw(img, "RGBA")
font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 11)
W, H = page.rect.width, page.rect.height
step = 25
x = 0
while x <= W:
    major = x % 50 == 0
    d.line([(x * zoom, 0), (x * zoom, img.height)], fill=(255, 0, 255, 110 if major else 45), width=1)
    if major:
        d.text((x * zoom + 2, 2), str(int(x)), fill=(200, 0, 200, 255), font=font)
    x += step
y = 0
while y <= H:
    major = y % 50 == 0
    d.line([(0, y * zoom), (img.width, y * zoom)], fill=(0, 160, 255, 110 if major else 45), width=1)
    if major:
        d.text((2, y * zoom + 2), str(int(y)), fill=(0, 120, 220, 255), font=font)
    y += step
os.makedirs(os.path.join(HERE, "grid"), exist_ok=True)
img.save(os.path.join(HERE, "grid", fid + ".png"))
print(fid, "%.0f x %.0f pt" % (W, H))
