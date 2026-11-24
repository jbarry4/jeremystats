"""Is v1's Sex a row-shifted copy of some older sheet's Sex column? Test every sheet Chicken Scratch has with row locators."""
import json, os, re, collections
HERE = os.path.dirname(os.path.abspath(__file__))
S = json.load(open(os.path.join(HERE, "sexsrc.json")))
V1 = S["V1"]
F = json.load(open(os.path.join(os.environ["LOCALAPPDATA"], "Jarvis", "chickenscratch", "facts_all.json"), encoding="utf-8"))
sheets = collections.defaultdict(dict)   # (source) -> row -> (mouse, sex)
for f in F.values():
    if f["project"] != "KCNT1" or f["type"] != "sex":
        continue
    m = re.search(r"!([A-Z]+)(\d+)$", f.get("locator") or "")
    if not m or not str(f["raw"]).isdigit():
        continue
    v = str(f["value"]).split("=")[-1].strip().upper().rstrip("?")
    if v not in ("M", "F"):
        continue
    sheets[f["source"]][int(m.group(2))] = (str(int(f["raw"])), v)
for src, rows in sheets.items():
    if len(rows) < 20:
        continue
    by_mouse = {mm: (r, s) for r, (mm, s) in rows.items()}
    res = []
    for k in range(-5, 6):
        ok = n = 0
        for mm, (r, s) in by_mouse.items():
            if mm in V1 and (r + k) in rows:
                n += 1
                ok += rows[r + k][1] == V1[mm]
        if n:
            res.append((ok / n, k, ok, n))
    res.sort(reverse=True)
    print("%-75s rows %3d  best offsets: %s" % (src[-75:], len(rows), ", ".join("%+d:%d/%d" % (k, ok, n) for _, k, ok, n in res[:3])))
