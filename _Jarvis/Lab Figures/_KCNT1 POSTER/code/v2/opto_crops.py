"""Opto panels for poster v2, cut from Dylan's 2024 poster (FinalKcnt1_Dylan 1.pdf) at 400 dpi.
  opto_effects.png      Fig. 7 panels A (Baseline), B (5 Hz, 'A' run), D (7 Hz), F (12 Hz, 'A' run): LFP, spectrogram,
                        one SST unit's spikes; old panel letters and titles left out, new titles drawn on, 2 x 2.
  opto_entrainment.png  Fig. 8 whole (A autocorrelation + spectrum per light frequency, B mean burst power, C mean
                        firing rate); 'Fig. 8' and the A)/B)/C) letters (and Fig. 7's D)/F) at the edge) painted out.
Regions are in display px of a 2212-px-wide view of the 3456-pt-wide poster, as in draft 1's crops.py."""
import os, sys
import fitz
from PIL import Image, ImageDraw, ImageFont
SRC = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\KCNT1 POSTER\Poster Resources\FinalKcnt1_Dylan 1.pdf"
OUT = sys.argv[1]
P = 3456 / 2212.0
DPI = 400
page = fitz.open(SRC)[0]

def cut(box, erase=()):
    x0, y0, x1, y1 = box
    z = DPI / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(z, z), clip=fitz.Rect(x0 * P, y0 * P, x1 * P, y1 * P), alpha=False)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    d = ImageDraw.Draw(im); k = P * z
    for ex0, ey0, ex1, ey1 in erase:
        d.rectangle(((ex0 - x0) * k, (ey0 - y0) * k, (ex1 - x0) * k, (ey1 - y0) * k), fill="white")
    return im

PANELS = [("Baseline", (1121, 487, 1458, 686), [(1108, 489, 1127, 507)]),
          ("5 Hz", (1484, 487, 1826, 686), [(1482, 489, 1500, 507)]),
          ("7 Hz", (1489, 719, 1826, 917), []),
          ("12 Hz", (1489, 953, 1826, 1149), [])]
ims = [(t, cut(b, e)) for t, b, e in PANELS]
W = max(im.width for _t, im in ims)
H = max(im.height for _t, im in ims)
font = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 120)
font2 = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 105)
title_h, gap, foot = 170, 90, 150
sheet = Image.new("RGB", (2 * W + gap, 2 * (H + title_h) + gap + foot), "white")
d = ImageDraw.Draw(sheet)
for i, (t, im) in enumerate(ims):
    r, c = divmod(i, 2)
    x, y = c * (W + gap), r * (H + title_h + gap)
    d.text((x + W / 2, y + title_h / 2), t, font=font, fill="#1d2433", anchor="mm")
    sheet.paste(im, (x + (W - im.width) // 2, y + title_h))
d.text((sheet.width / 2, sheet.height - foot / 2), "Time (s)", font=font2, fill="#1d2433", anchor="mm")
sheet.save(os.path.join(OUT, "opto_effects.png"))
print("opto_effects", sheet.size)

ent = cut((1205, 722, 1483, 1224), [(1211, 727, 1224, 740), (1211, 1116, 1224, 1129), (1352, 1117, 1366, 1130),
                                     (1472, 722, 1483, 740), (1472, 952, 1483, 972)])
ent.save(os.path.join(OUT, "opto_entrainment.png"))
print("opto_entrainment", ent.size)
