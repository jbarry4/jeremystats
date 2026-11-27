"""Panel B and C of Dylan's Fig. 8: each run's value is the centre of the round join (or cap) the PDF drew at that run's
category; B is checked against the peak amplitudes the PDF prints, so C (the firing rates, not printed) can be trusted."""
import json, re, numpy as np, fitz
SRC = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\_KCNT1 POSTER\Poster Resources\FinalKcnt1_Dylan 1.pdf"
OUT = r"C:\Users\info\AppData\Local\Temp\claude\8edeb4480295094a\6cbfc353-8a69-4b03-b8c7-ec6377a03c30\scratchpad\poster\v5\data\opto_fig8.json"
page = fitz.open(SRC)[0]
TX = [(s["text"].strip(), fitz.Rect(s["bbox"])) for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]]
num = re.compile(r"^-?\d+(\.\d+)?$")

def circle(p):
    x, y = p[:, 0], p[:, 1]
    A = np.c_[2 * x, 2 * y, np.ones(len(x))]
    c = np.linalg.lstsq(A, x ** 2 + y ** 2, rcond=None)[0]
    return c[0], c[1], np.sqrt(c[2] + c[0] ** 2 + c[1] ** 2)

def values(R):
    ds = [d for d in page.get_drawings() if fitz.Rect(d["rect"]).intersects(R) and fitz.Rect(d["rect"]).width > 50 and d.get("fill") == (0.0, 0.0, 0.0)]
    d = max(ds, key=lambda d: len(d["items"]))
    V = np.array([(it[1].x, it[1].y) for it in d["items"] if it[0] == "l"])
    yl = [(float(t), (r.y0 + r.y1) / 2) for t, r in TX if num.match(t) and R.x0 - 15 < r.x0 and r.x1 < R.x0 + 9 and R.y0 - 4 < (r.y0 + r.y1) / 2 < R.y1 + 4]
    a, b = np.polyfit([y for _, y in yl], [v for v, _ in yl], 1)
    # every round join and cap is a run of closely spaced vertices on a circle of the line's half-width; its centre is a vertex
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
        if merged and abs(c[0] - merged[-1][0][0]) < 1.0:
            merged[-1].append(c)
        else:
            merged.append([c])
    out = [(float(np.mean([c[0] for c in m])), float(a * np.mean([c[1] for c in m]) + b)) for m in merged]
    return out

B = fitz.Rect(1940.6, 1755.1, 2110.6, 1880.4)
C = fitz.Rect(2140.0, 1754.5, 2309.2, 1879.9)
printed = [0.713, 7253.91, 7081.07, 1390.97, 4048.85, 1170.87, 291.53]
vb = values(B)
print("B (check):", [(round(v[0], 1), round(v[1], 1), p) for v, p in zip(vb, printed)], len(vb))
vc = values(C)
print("C rates:", [(round(v[0], 1), round(v[1], 2)) for v in vc], len(vc))
d = json.load(open(OUT))
d["rate_hz"] = [round(float(v[1]), 2) for v in vc]
d["power_check"] = [round(float(v[1]), 1) for v in vb]
json.dump(d, open(OUT, "w"), indent=1)
print("updated", OUT)
