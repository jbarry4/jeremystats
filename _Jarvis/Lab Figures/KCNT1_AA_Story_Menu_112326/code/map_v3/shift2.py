"""In v1 row order: is the Sex column shifted relative to the true sex (SoftMouse, else Archive)?
Also: was v1's Sex column sorted on its own (e.g. all F then all M within blocks)?"""
import openpyxl, os, re, json
HERE = os.path.dirname(os.path.abspath(__file__))
S = json.load(open(os.path.join(HERE, "sexsrc.json")))
wb = openpyxl.load_workbook(os.path.join(HERE, "labops_1623.xlsx"), data_only=True)


def mid(v):
    s = str(v or "").strip().replace(".0", "")
    m = re.match(r"^(\d+)", s)
    return str(int(m.group(1))) if m else None


def sexn(v):
    s = str(v or "").strip().upper().rstrip("?")
    return s if s in ("M", "F") else None


for tabname in ["KCNT1 Active (Archived)", "KCNT1 Active 2.0"]:
    ws = wb[tabname]
    h = [c.value for c in ws[1]]
    rows = [(mid(r[0]), sexn(r[h.index("Sex")]), r[h.index("DOB")]) for r in ws.iter_rows(min_row=2, values_only=True)]
    truth = lambda m: S["SM"].get(m) or S["VOS"].get(m) or S["ARC"].get(m)
    print("==", tabname, len(rows))
    best = []
    for k in range(-6, 7):
        ok = n = 0
        for i, (m, s, d) in enumerate(rows):
            j = i + k
            if 0 <= j < len(rows) and s and truth(rows[j][0]):
                n += 1
                ok += (s == truth(rows[j][0]))
        best.append((ok / max(n, 1), k, ok, n))
    for b in sorted(best, reverse=True)[:4]:
        print("   offset %+d matches %d/%d (%.2f)" % (b[1], b[2], b[3], b[0]))
    # print the run of rows with truth vs sheet, to see blocks
    line = []
    for i, (m, s, d) in enumerate(rows):
        t = truth(m)
        mark = "." if (s and t and s == t) else ("X" if (s and t) else "?")
        line.append(mark)
    print("   row-by-row (. ok, X flipped, ? unknown):")
    seq = "".join(line)
    for i in range(0, len(seq), 60):
        print("   %4d %s" % (i + 2, seq[i:i + 60]))
    if tabname == "KCNT1 Active (Archived)":
        print("   first rows:")
        for i, (m, s, d) in enumerate(rows[:200]):
            t = truth(m)
            print("     row", i + 2, m, "sheet", s, "true", t, "X" if s and t and s != t else "", str(d)[:10])
