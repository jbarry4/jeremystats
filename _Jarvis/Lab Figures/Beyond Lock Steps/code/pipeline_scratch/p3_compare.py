"""Dedupe check: each workflow's new run against its previous one, per mouse.
Events are matched by (recording, time). Read only."""
import collections
import json
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402

AR = A.ARTIFACTS
S = os.path.dirname(os.path.abspath(__file__))
dropped = collections.defaultdict(set)   # mouse -> times marked Garbage
for r in json.load(open(os.path.join(S, "dedupe_report.json"))):
    for t in r["times"]:
        if abs(t - r["kept"]) > 1e-6:
            dropped[r["mouse"]].add(round(t, 4))

lab = {}
for e in A.BANK.list() if hasattr(A.BANK, "list") else []:
    pass


def mouse_of(gid):
    if gid not in lab:
        lab[gid] = gid
        for e in A.BANK.entries() if hasattr(A.BANK, "entries") else []:
            pass
    return lab[gid]


def classes(aid, v):
    run = (AR.payload(aid, v) or {}).get("run") or {}
    cols = run["cols"]
    gids = cols["gids"]
    out = {}
    for cls, g, t in zip(cols["cls"], cols["g"], cols["t"]):
        if g is None or t is None:
            continue
        out[(gids[int(g)], round(float(t), 4))] = cls
    return out


GID = {}
for eid, m in {"bfa98498290b": "m1", "afa70b62f372": "m13", "41dd94702761": "m2", "edc1a5080093": "m21", "43a2cfedde17": "m22",
               "f4c18a9a8bd4": "m26", "35c325a44d44": "m28", "db66d3c694fd": "m3", "a62d1b78448b": "m33", "eaecc4a5e194": "m34",
               "b60578899091": "m5", "8aad148bd6f6": "m51", "1429bf1f239f": "m59", "cb139fb2ea29": "m6", "d4a4bcb4e47f": "m60",
               "ab69363ee622": "m61", "ece9a84acdea": "m7", "2a8e47760eea": "m8"}.items():
    GID[A.BANK.get(eid)["gid"]] = m

out = {}
for aid, ov, nv, name in (("178daabb125c", 3, 4, "5% DS border (CTL)"), ("4a29af93e601", 3, 4, "10% DS border"),
                          ("6fa7fef7b7a3", 4, 5, "Halo Ambiguous (v6)"), ("a7eee6a6ca9f", 3, 4, "No P-spikes Ambiguous (v8)")):
    a, b = classes(aid, ov), classes(aid, nv)
    print("\n== %s  v%d -> v%d   events %d -> %d" % (name, ov, nv, len(a), len(b)))
    rows = []
    for g in sorted(set(k[0] for k in a) | set(k[0] for k in b), key=lambda g: int(GID.get(g, "m999")[1:])):
        m = GID.get(g, g)
        ka = {k[1]: c for k, c in a.items() if k[0] == g}
        kb = {k[1]: c for k, c in b.items() if k[0] == g}
        gone = set(ka) - set(kb)
        new = set(kb) - set(ka)
        gone_dup = sum(1 for t in gone if t in dropped.get(m, ()))
        flips = collections.Counter("%s->%s" % (ka[t], kb[t]) for t in set(ka) & set(kb) if ka[t] != kb[t])
        ca, cb = collections.Counter(ka.values()), collections.Counter(kb.values())
        if gone or new or flips:
            print("  %-4s %s -> %s | removed %d (duplicates %d) | new %d | changed class %s" % (
                m, dict(ca), dict(cb), len(gone), gone_dup, len(new), dict(flips)))
        rows.append({"mouse": m, "before": dict(ca), "after": dict(cb), "removed": len(gone), "removed_dup": gone_dup,
                     "new": len(new), "flips": dict(flips)})
    same = [r["mouse"] for r in rows if not (r["removed"] or r["new"] or r["flips"])]
    print("  unchanged:", same)
    tot = collections.Counter()
    for r in rows:
        for k, v in r["flips"].items():
            tot[k] += v
    print("  totals: removed %d (dup %d), new %d, class changes %s" % (sum(r["removed"] for r in rows),
          sum(r["removed_dup"] for r in rows), sum(r["new"] for r in rows), dict(tot)))
    out[aid] = rows
json.dump(out, open(os.path.join(S, "p3_compare.json"), "w"), indent=1)
