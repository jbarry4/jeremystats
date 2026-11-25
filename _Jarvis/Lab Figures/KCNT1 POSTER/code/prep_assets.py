"""Collect the poster's images into one folder, capped at MAXPX on the long side (>= ~280 dpi at their placed
size), and write sizes.json ({name: [w, h]}) for the builder.

usage: python -I prep_assets.py SRC_ASSET_DIR PTEN_MEDIA_DIR OUT_DIR
"""
import json
import os
import shutil
import sys

import fitz
from PIL import Image

src, media, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
MAXPX = 4200

# the seizure figure, re-cut from the PDF the user named, with its own title line removed
SEIZ = (r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\KCNT1 POSTER\Poster Resources"
        r"\KCNT1_m459_A_origin_v6_overlay.pdf")
page = fitz.open(SEIZ)[0]
pix = page.get_pixmap(matrix=fitz.Matrix(3.5, 3.5), clip=fitz.Rect(56, 88, 1720, 1296), alpha=False)
pix.save(os.path.join(src, "m459_v6_overlay_notitle.png"))

FILES = {
    "logo_ecdl": os.path.join(media, "image1.png"),
    "logo_ngp": os.path.join(media, "image2.png"),
    "logo_uvm": os.path.join(media, "image3.png"),
    "elife_fig4_C": os.path.join(src, "elife_fig4_C.png"),
    "hilar_circuit": os.path.join(src, "nbh_fig1_D_hilar.png"),
    "headfixed": os.path.join(src, "nbh_fig2_A.png"),
    "laminar": os.path.join(src, "nbh_fig2_B.png"),
    "csd_primer": os.path.join(src, "nbh_fig2_CD.png"),
    "arena": os.path.join(src, "nbh_fig6_A.png"),
    "histology": os.path.join(src, "dyl_fig6_C.png"),
    "ied_hilus": os.path.join(src, "nbh_fig4_AD.png"),
    "ied_two_ds": os.path.join(src, "nbh_fig4_EF.png"),
    "urethane": os.path.join(src, "urethane_ied_rate.png"),
    "seizure": os.path.join(src, "m459_v6_overlay_notitle.png"),
    "opto_csd": os.path.join(src, "dyl_fig9.png"),
    "opto_autocorr": os.path.join(src, "nbh_fig7.png"),
    "behavior": os.path.join(src, "behavior", "KCNT1_AA_poster_figure_v2_with_outliers.png"),
}
sizes = {}
for name, p in FILES.items():
    im = Image.open(p)
    keep_alpha = name.startswith("logo")
    im = im.convert("RGBA" if keep_alpha else "RGB")
    if max(im.size) > MAXPX:
        k = MAXPX / max(im.size)
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    dst = os.path.join(out, name + ".png")
    im.save(dst, optimize=True)
    sizes[name] = [im.width, im.height]
    print("%-14s %5d x %5d  %6.1f KB" % (name, im.width, im.height, os.path.getsize(dst) / 1024))
json.dump(sizes, open(os.path.join(out, "sizes.json"), "w"), indent=1)
# the urethane, behavior and seizure sources and their scripts travel with the poster
print("sizes.json written")
