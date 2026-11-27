"""NBH'25 Fig. 2B ('H3 Laminar recording', a control mouse) back to numbers: the 64 LFP traces (vector paths), the printed
1 s and 500 uV bars, and the layer labels (SP, SR, SLM, OML, MML, GCL, HILUS) at their printed depths."""
import os, json, numpy as np, fitz
SRC = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\_KCNT1 POSTER\Poster Resources\FinalNBH'25 1.pdf"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nbh_laminar.npz")
page = fitz.open(SRC)[0]
P = page.rect.width / 2212.0
R = fitz.Rect(338 * P, 514 * P, 848 * P, 742 * P)
paths = [d for d in page.get_drawings() if fitz.Rect(d["rect"]).intersects(R) and d["type"] == "s"]
long_ = [d for d in paths if len(d["items"]) > 1000]
short = [d for d in paths if len(d["items"]) <= 1000]
print(len(long_), "traces;", len(short), "short paths:", [(len(d["items"]), [round(v, 1) for v in d["rect"]]) for d in short][:12])
tr = []
for d in long_:
    its = [it for it in d["items"] if it[0] == "l"]
    Pp = np.array([(it[1].x, it[1].y) for it in its] + [(its[-1][2].x, its[-1][2].y)])
    tr.append(Pp)
tr.sort(key=lambda p: np.median(p[:, 1]))
base = np.array([np.median(p[:, 1]) for p in tr])
print("trace baselines pt: first %s ... last %s; spacing median %.2f" % (np.round(base[:3], 1), np.round(base[-3:], 1), np.median(np.diff(base))))
# scale bars: render the area near the printed '1 sec' and '500 uV' and find the dark runs
z = 1200 / 72
def strip(rect):
    pix = page.get_pixmap(matrix=fitz.Matrix(z, z), clip=fitz.Rect(*rect), alpha=False)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).astype(int).sum(2)
A = strip((1225, 844, 1310, 860))
r = np.argmax((A < 300).sum(1)); cols = np.flatnonzero(A[r] < 300)
sec_pt = (cols.max() - cols.min()) / z
print("1 sec bar: y %.2f, x %.2f-%.2f -> %.2f pt" % (844 + r / z, 1225 + cols.min() / z, 1225 + cols.max() / z, sec_pt))
A = strip((1295, 845, 1310, 905))
c = np.argmax((A < 300).sum(0)); rows = np.flatnonzero(A[:, c] < 300)
uv_pt = (rows.max() - rows.min()) / z
print("500 uV bar: x %.2f, y %.2f-%.2f -> %.2f pt" % (1295 + c / z, 845 + rows.min() / z, 845 + rows.max() / z, uv_pt))
lay = {}
for b in page.get_text("dict", clip=R)["blocks"]:
    for l in b.get("lines", []):
        for s in l["spans"]:
            t = s["text"].strip()
            if t in ("SP", "SR", "SLM", "OML", "MML", "GCL", "HILUS"):
                lay[t] = (s["bbox"][1] + s["bbox"][3]) / 2
print("layers (pt):", {k: round(v, 1) for k, v in lay.items()})
x0 = min(p[:, 0].min() for p in tr)
np.savez_compressed(OUT, n=len(tr), **{"x%d" % i: ((p[:, 0] - x0) / sec_pt).astype(np.float32) for i, p in enumerate(tr)},
                    **{"y%d" % i: (-(p[:, 1] - np.median(p[:, 1])) / uv_pt * 500).astype(np.float32) for i, p in enumerate(tr)},
                    base=base, layers=json.dumps(lay), sec_pt=sec_pt, uv_pt=uv_pt)
print("wrote", OUT, "duration %.2f s" % (max(p[:, 0].max() for p in tr) - x0) / sec_pt if False else "")
print("duration s:", (max(p[:, 0].max() for p in tr) - x0) / sec_pt)
