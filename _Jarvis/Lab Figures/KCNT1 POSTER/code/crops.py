"""Cut poster panels out of the old posters and the papers at print resolution.

Regions are given in 'display pixels' of the 2212-px-wide previews (old posters, 3456 pt wide) or of the
1687-px-wide previews (paper pages, 612 pt wide), whichever the region was read from; converted to points here.
usage: python -I crops.py OUTDIR [names...]   (no names = all); writes NAME.png and a preview sheet _sheet.png
"""
import os
import sys

import fitz
from PIL import Image, ImageDraw

R = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\KCNT1 POSTER\Poster Resources"
NBH = os.path.join(R, "FinalNBH'25 1.pdf")
DYL = os.path.join(R, "FinalKcnt1_Dylan 1.pdf")
ELF = os.path.join(R, "elife-92915.pdf")
CR = os.path.join(R, "nihms-1642113.pdf")
P = 3456 / 2212.0            # old posters: display px -> pt
E = 612 / 1687.0             # paper pages: display px -> pt

# name: (pdf, page, (x0, y0, x1, y1) in display px, scale, dpi)
REG = {
    "nbh_fig1_B":        (NBH, 1, (338, 207, 533, 492), P, 450),
    "nbh_fig1_D_hilar":  (NBH, 1, (538, 382, 690, 492), P, 450),
    "nbh_fig2_A":        (NBH, 1, (4, 514, 324, 742), P, 400),
    "nbh_fig2_B":        (NBH, 1, (338, 514, 848, 742), P, 400),
    "nbh_fig2_CD":       (NBH, 1, (8, 742, 850, 1058), P, 400),
    "nbh_fig4_AD":       (NBH, 1, (8, 1100, 277, 1541), P, 450),
    "nbh_fig4_EF":       (NBH, 1, (284, 1102, 806, 1357), P, 450),
    "nbh_fig6_A":        (NBH, 1, (1201, 109, 1450, 313), P, 400),
    "nbh_fig7":          (NBH, 1, (1243, 606, 1818, 1080), P, 400),
    "nbh_fig8":          (NBH, 1, (1846, 606, 2200, 1302), P, 400),
    "dyl_fig9":          (DYL, 1, (1628, 1155, 2147, 1462), P, 400),
    "dyl_fig8_BC":       (DYL, 1, (1210, 1121, 1482, 1222), P, 450),
    "dyl_fig6_C":        (DYL, 1, (1878, 112, 2188, 419), P, 300),
    "elife_fig4_C":      (ELF, 9, (528, 1192, 1347, 1808), E, 600),
}
# old figure and panel labels painted white inside a crop (same display-px space as REG); the poster
# letters its own panels, so the old A)/B)/Ei) letters would clash
ERASE = {
    "nbh_fig1_D_hilar": [(538, 382, 554, 398)],
    "nbh_fig2_A": [(4, 514, 22, 531)],
    "nbh_fig2_B": [(338, 514, 360, 531)],
    "nbh_fig2_CD": [(8, 742, 18, 761), (332, 742, 352, 760), (589, 742, 611, 760)],
    "nbh_fig4_AD": [(12, 1106, 27, 1122), (171, 1106, 186, 1122), (12, 1346, 26, 1361), (104, 1346, 119, 1361)],
    "nbh_fig4_EF": [(308, 1104, 327, 1122), (555, 1104, 573, 1122), (310, 1206, 331, 1222), (557, 1206, 577, 1222)],
    "nbh_fig7": [(1243, 606, 1300, 623)],
    "nbh_fig8": [(1846, 606, 1890, 621), (1846, 634, 1862, 650), (1851, 859, 1867, 874), (1848, 1093, 1865, 1108)],
    "dyl_fig9": [(1636, 1160, 1676, 1183), (2012, 1155, 2042, 1161)],
    "dyl_fig8_BC": [(1210, 1121, 1224, 1129), (1352, 1121, 1366, 1130)],
    "elife_fig4_C": [(526, 1192, 568, 1230), (933, 1192, 978, 1230)],
}


def cut(name, out):
    pdf, pno, (x0, y0, x1, y1), s, dpi = REG[name]
    doc = fitz.open(pdf)
    page = doc[pno - 1]
    rect = fitz.Rect(x0 * s, y0 * s, x1 * s, y1 * s) & page.rect
    z = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(z, z), clip=rect, alpha=False)
    dst = os.path.join(out, name + ".png")
    pix.save(dst)
    if name in ERASE:
        im = Image.open(dst).convert("RGB")
        d = ImageDraw.Draw(im)
        k = s * z                               # display px -> crop px
        for ex0, ey0, ex1, ey1 in ERASE[name]:
            d.rectangle(((ex0 - x0) * k, (ey0 - y0) * k, (ex1 - x0) * k, (ey1 - y0) * k), fill="white")
        im.save(dst)
    return dst, pix.width, pix.height, rect


if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    names = sys.argv[2:] or list(REG)
    thumbs = []
    for n in names:
        dst, w, h, rect = cut(n, out)
        print("%-18s %5d x %5d px  (%.2f x %.2f in at source)  rect=%s" % (n, w, h, rect.width / 72, rect.height / 72,
                                                                        tuple(round(v) for v in rect)))
        im = Image.open(dst).convert("RGB")
        im.thumbnail((700, 700))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, 8 * len(n) + 8, 16), fill="black")
        d.text((4, 3), n, fill="white")
        thumbs.append(im)
    cols = 3
    cw = max(t.width for t in thumbs) + 8
    rows = (len(thumbs) + cols - 1) // cols
    rh = [max(t.height for t in thumbs[r * cols:(r + 1) * cols]) + 8 for r in range(rows)]
    sheet = Image.new("RGB", (cols * cw, sum(rh)), "gray")
    y = 0
    for r in range(rows):
        for c, t in enumerate(thumbs[r * cols:(r + 1) * cols]):
            sheet.paste(t, (c * cw, y))
        y += rh[r]
    sheet.save(os.path.join(out, "_sheet.png"))
    print("sheet", sheet.size)
