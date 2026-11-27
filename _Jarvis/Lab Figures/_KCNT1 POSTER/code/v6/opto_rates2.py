"""Fig. 8 B/C values with the y axis calibrated on the plot's own gridlines; joints too gentle to carry a round-join arc are
read as the midpoint of their outer and inner outline corners. B is checked against the amplitudes the PDF prints."""
import json, re, numpy as np, fitz
SRC = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\_KCNT1 POSTER\Poster Resources\FinalKcnt1_Dylan 1.pdf"
OUT = r"C:\Users\info\AppData\Local\Temp\claude\8edeb4480295094a\6cbfc353-8a69-4b03-b8c7-ec6377a03c30\scratchpad\poster\v5\data\opto_fig8.json"
page = fitz.open(SRC)[0]
TX = [(s["text"].strip(), fitz.Rect(s["bbox"])) for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]]
num = re.compile(r"^-?\d+(\.\d+)?$")

def circle(p):
    x, y = p[:, 0], p[:, 1]
    c = np.linalg.lstsq(np.c_[2 * x, 2 * y, np.ones(len(x))], x ** 2 + y ** 2, rcond=None)[0]
    return c[0], c[1], np.sqrt(c[2] + c[0] ** 2 + c[1] ** 2)

def values(R, n=7):
    DS = [d for d in page.get_drawings() if fitz.Rect(d["rect"]).intersects(R)]
    d = max([d for d in DS if d.get("fill") == (0.0, 0.0, 0.0) and fitz.Rect(d["rect"]).width > 50], key=lambda d: len(d["items"]))
    V = np.array([(it[1].x, it[1].y) for it in d["items"] if it[0] == "l"])
    grid = sorted([(fitz.Rect(g["rect"]).y0 + fitz.Rect(g["rect"]).y1) / 2 for g in DS if g.get("fill") and abs(g["fill"][0] - 0.8796) < 0.01 and fitz.Rect(g["rect"]).width > 100])
    labs = [(float(t), (r.y0 + r.y1) / 2) for t, r in TX if num.match(t) and R.x0 - 15 < r.x0 and r.x1 < R.x0 + 9 and R.y0 - 4 < (r.y0 + r.y1) / 2 < R.y1 + 4]
    pairs = [(g, min(labs, key=lambda l: abs(l[1] - g))[0]) for g in grid]
    a, b = np.polyfit([g for g, _ in pairs], [v for _, v in pairs], 1)
    runs, cur = [], [0]
    for i in range(1, len(V)):
        if np.hypot(*(V[i] - V[i - 1])) < 0.35:
            cur.append(i)
        else:
            runs.append(cur); cur = [i]
    runs.append(cur)
    cents = []
    for r_ in runs:
        if len(r_) >= 4:
            cx_, cy_, rad = circle(V[r_])
            if 0.7 < rad < 1.4:
                cents.append((cx_, cy_))
    cents.sort()
    merged = []
    for c in cents:
        if merged and abs(c[0] - merged[-1][-1][0]) < 1.0:
            merged[-1].append(c)
        else:
            merged.append([c])
    xs = [np.mean([c[0] for c in m]) for m in merged]
    ys = [np.mean([c[1] for c in m]) for m in merged]
    step = (xs[-1] - xs[0]) / (n - 1)
    out = []
    for k in range(n):
        x = xs[0] + k * step
        j = int(np.argmin(np.abs(np.array(xs) - x)))
        if abs(xs[j] - x) < 1.5:
            out.append((xs[j], a * ys[j] + b, "arc"))
        else:
            near = V[np.abs(V[:, 0] - x) < 1.6]
            out.append((x, a * (near[:, 1].min() + near[:, 1].max()) / 2 + b, "corners"))
    return out, pairs

B = fitz.Rect(1940.6, 1755.1, 2110.6, 1880.4)
C = fitz.Rect(2140.0, 1754.5, 2309.2, 1879.9)
printed = [0.713, 7253.91, 7081.07, 1390.97, 4048.85, 1170.87, 291.53]
vb, pb = values(B)
print("B gridlines", [(round(g, 1), v) for g, v in pb])
print("B (check):", [(round(v[1], 1), p, v[2]) for v, p in zip(vb, printed)])
vc, pc = values(C)
print("C gridlines", [(round(g, 1), v) for g, v in pc])
print("C rates:", [(round(v[1], 2), v[2]) for v in vc])
d = json.load(open(OUT))
d["rate_hz"] = [round(float(v[1]), 2) for v in vc]
d["power_check"] = [round(float(v[1]), 1) for v in vb]
d["power_printed"] = printed
json.dump(d, open(OUT, "w"), indent=1)
print("updated", OUT)
