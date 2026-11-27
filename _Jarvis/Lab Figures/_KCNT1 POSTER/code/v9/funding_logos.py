"""The funders' logos (the PTEN poster v3's funding card: PTEN Research and NIH, its media image22/image23), redrawn for the
KCNT1 poster's green: one-colour white versions for the dark-green funding strip (PTEN Research's orange accent becomes UVM
gold; NIH's grey box turns white with the letters knocked out to the green behind, its usual one-colour form).
usage: python funding_logos.py PTEN.png NIH.png OUTDIR"""
import os, sys
import numpy as np
from PIL import Image

pten, nih, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
GOLD = np.array([255, 212, 22])

a = np.asarray(Image.open(pten).convert("RGBA")).astype(float)
rgb, al = a[..., :3], a[..., 3]
accent = (rgb[..., 0] > rgb[..., 2] + 60)
o = np.zeros_like(a)
o[..., :3] = 255
o[accent, :3] = GOLD
o[..., 3] = al
Image.fromarray(o.astype(np.uint8)).save(os.path.join(out, "logo_pten_white.png"))

b = np.asarray(Image.open(nih).convert("RGBA")).astype(float)
rgb, al = b[..., :3], b[..., 3]
L = rgb.mean(2)
sat = rgb.max(2) - rgb.min(2)
white = np.clip((L - 120) / (232 - 120), 0, 1) * (sat < 40)          # the box's white letters: knocked out
o = np.zeros_like(b)
o[..., :3] = 255
o[..., 3] = al * (1 - white)
Image.fromarray(o.astype(np.uint8)).save(os.path.join(out, "logo_nih_white.png"))
print("logos written to", out)
