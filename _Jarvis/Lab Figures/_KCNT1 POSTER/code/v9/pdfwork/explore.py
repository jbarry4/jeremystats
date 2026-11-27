import sys, collections, fitz
import os
SRC = os.environ.get("PDF", r"C:SERSINFODESKTOPJEREMYSTATS_JARVISab figureskcnt1 posterposter resourcesfinalkcnt1_dylan 1.pdf")
P = 3456 / 2212.0
page = fitz.open(SRC)[0]
x0, y0, x1, y1 = [float(v) for v in sys.argv[1:5]]
R = fitz.Rect(x0 * P, y0 * P, x1 * P, y1 * P)
print("rect pt", R)
dr = [d for d in page.get_drawings() if fitz.Rect(d["rect"]).intersects(R)]
g = collections.Counter()
ex = {}
for d in dr:
    key = (d["type"], tuple(round(c, 3) for c in d["color"]) if d.get("color") else None, tuple(round(c, 3) for c in d["fill"]) if d.get("fill") else None, round(d.get("width") or 0, 2))
    g[key] += 1
    ex.setdefault(key, d)
for k, n in g.most_common(40):
    d = ex[k]
    print(n, k, "items", len(d["items"]), "rect", [round(v, 1) for v in d["rect"]], [it[0] for it in d["items"][:6]])
print("--- images")
for img in page.get_image_info(xrefs=True):
    b = fitz.Rect(img["bbox"])
    if b.intersects(R):
        print(img["xref"], img["width"], img["height"], [round(v, 1) for v in b])
print("--- text")
for b in page.get_text("dict", clip=R)["blocks"]:
    for l in b.get("lines", []):
        for s in l["spans"]:
            print(repr(s["text"]), [round(v, 1) for v in s["bbox"]], round(s["size"], 1))
