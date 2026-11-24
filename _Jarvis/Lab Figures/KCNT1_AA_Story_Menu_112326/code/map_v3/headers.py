"""Read every .dat header in the AA folder -> headers.json"""
import os, re, json, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Z390\Desktop\jeremystats\KCNT1 Active Avoidance\active_avoidance_data"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), sys.argv[2] if len(sys.argv) > 2 else "headers.json")
rows = []
for folder in sorted(os.listdir(ROOT)):
    fp = os.path.join(ROOT, folder)
    if not os.path.isdir(fp):
        continue
    for fn in sorted(os.listdir(fp)):
        if not fn.lower().endswith(".dat"):
            continue
        p = os.path.join(fp, fn)
        size = os.path.getsize(p)
        with open(p, "r", encoding="latin-1") as f:
            text = f.read()
        head, _, body = text.partition("%%END_HEADER")
        def g(key):
            m = re.search(r"%" + re.escape(key) + r"\.0 \( (.*?) \)", head)
            return m.group(1).strip() if m else None
        lines = [l for l in body.splitlines() if l.strip() and not l.lstrip().startswith("%")]
        last_ts = None
        shocks = 0
        if lines:
            try:
                last_ts = int(lines[-1].split()[1])
            except (IndexError, ValueError):
                pass
        rows.append(dict(folder=folder, file=fn, size=size, date=g("Date"), time=g("Time"),
                         elapsed_ms=g("ElapsedTime_ms"), path_m=g("ElapsedPath_m"),
                         paradigm=g("Paradigm"), frame=g("Frame"), shock=g("ShockParameters"),
                         sector=g("ReinforcedSector"), n_samples=len(lines), last_ts=last_ts,
                         mtime=os.path.getmtime(p)))
json.dump(rows, open(OUT, "w"), indent=1)
print(len(rows))
