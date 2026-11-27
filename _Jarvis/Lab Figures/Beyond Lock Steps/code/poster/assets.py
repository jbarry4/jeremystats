"""Image assets for the poster, cut from the Jan-26 poster's pictures (python assets.py).
  p7_timeline.png   the P7 injection -> electrophysiology schematic, without the Pten;Raptor genotype line
  traces_wt_ko.png  the Wildtype and Pten KO current-clamp traces with the original 20 mV / 200 ms scale bar moved beside them
  theta_A.png       theta CSD rasters with the PTEN/RAPTOR raster (old Aiii) cut out; old Aiv relabeled Aiii
  icon_*.png        emoji icons for the biomarker steps
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "img")

# ---- P7 timeline: crop, then white out the "Pten flx/flx / Raptor flx/flx" line
src = Image.open(os.path.join(IMG, "Picture_21.png")).convert("RGB")
p7 = src.crop((1035, 40, 1767, 505)).copy()
ImageDraw.Draw(p7).rectangle((1115 - 1035, 84 - 40, 1360 - 1035, 113 - 40), fill=(255, 255, 255))
p7.save(os.path.join(IMG, "p7_timeline.png"))

# ---- traces: Wildtype + Pten KO, teal removed, the original scale bar's black pixels carried over
x0, y0, x1, y1 = 1040, 530, 1485, 1025
tr = np.array(src.crop((x0, y0, x1, y1))).astype(int)
r, g, b = tr[..., 0], tr[..., 1], tr[..., 2]
teal = (g > r + 8) & (b > r + 8)
tr[teal] = 255
tr[:110, 395:] = 255                                        # what is left of the "Pten;Raptor" title
bar = np.array(src.crop((1525, 925, 1712, 1022))).astype(int)
dark = (bar.max(axis=2) < 120) & ~((bar[..., 1] > bar[..., 0] + 25) & (bar[..., 2] > bar[..., 0] + 25))
gap = 6
canvas = np.full((tr.shape[0], tr.shape[1] + gap + bar.shape[1], 3), 255, dtype=int)
canvas[:, :tr.shape[1]] = tr
oy, ox = 925 - y0, tr.shape[1] + gap
region = canvas[oy:oy + bar.shape[0], ox:ox + bar.shape[1]]
region[dark] = bar[dark]
Image.fromarray(canvas.astype(np.uint8)).save(os.path.join(IMG, "traces_wt_ko.png"))

# ---- theta rasters: cut the old Aiii panel (columns 2449-3398), keep the colorbar, move its label, relabel Aiv
A = np.array(Image.open(os.path.join(IMG, "Picture_40.png")).convert("RGBA"))
CUT0, CUT1 = 2449, 3399
label = A[68:104, 3352:CUT1].copy()
A[0:66, 3600:3740, 3] = 0                                   # erase "Aiv" (bbox 3626-3724 x 9-56)
new = np.concatenate([A[:, :CUT0], A[:, CUT1:]], axis=1)
new[1232:1300, 2425:CUT0, 3] = 0                          # the "9" left over from the cut raster's first time label
lx = 3352 - (CUT1 - CUT0)
patch = new[68:104, lx:lx + label.shape[1]]
m = label[..., 3] > 0
patch[m] = label[m]
im = Image.fromarray(new)
f = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 67)
d = ImageDraw.Draw(im)
bx = d.textbbox((0, 0), "Aiii", font=f)
d.text((3626 - (CUT1 - CUT0) - bx[0], 9 - bx[1]), "Aiii", font=f, fill=(0, 0, 0, 255))
im.save(os.path.join(IMG, "theta_A.png"))

# ---- emoji icons
ef = ImageFont.truetype(r"C:\Windows\Fonts\seguiemj.ttf", 109)
for name, ch in (("detect", "\U0001F50D"), ("curate", "\u2705"), ("align", "\U0001F4CF"), ("classify", "\U0001F5C2"),
                 ("vacc", "\U0001F5A5")):
    ic = Image.new("RGBA", (150, 150), (255, 255, 255, 0))
    ImageDraw.Draw(ic).text((75, 75), ch, font=ef, embedded_color=True, anchor="mm")
    ic = ic.crop(ic.getbbox())
    ic.save(os.path.join(IMG, "icon_%s.png" % name))
print("assets written to", IMG)
