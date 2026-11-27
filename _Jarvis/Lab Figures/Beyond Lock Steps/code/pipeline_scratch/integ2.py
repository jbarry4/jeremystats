"""Data integrity, step 2: event by event. The pools' members and their
groups, the borders' definitions, every room event's class under each run,
and each read's stamps against the run's kept stamps. Read only."""
import collections
import json
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import numpy as np  # noqa: E402
from backend import app as A  # noqa: E402
from backend import rcworkflow, xraymany  # noqa: E402

out = {}
AR = A.ARTIFACTS

# Every pool, its versions, and the groups of its members.
pools = []
for r in AR.list(kind="rootcanal_pool"):
    pools.append((r.get("id"), r.get("nickname") or r.get("name"), r.get("version"), r.get("archived")))
out["pools"] = pools

def pool_members(aid, v):
    pay = AR.payload(aid, v) or {}
    mem = pay.get("members") or []
    gids = [m.get("gid") for m in mem]
    groups = A._xm_groups(gids)
    ev = rcworkflow.pool_events(pay)
    per = collections.Counter(e["gid"] for e in ev)
    return [{"label": m.get("session_label"), "gid": m.get("gid"), "group": groups.get(m.get("gid")),
             "mouse_type": m.get("mouse_type"), "n": per.get(m.get("gid"), 0),
             "entry": m.get("entry_id"), "entry_v": m.get("version") or m.get("entry_version")}
            for m in mem], pay

for aid, v in (("07cdcb084c86", 2), ("3561fc988afd", 2)):
    mem, pay = pool_members(aid, v)
    rec = AR.get(aid) or {}
    out["pool_" + aid] = {"name": rec.get("nickname"), "newest": rec.get("version"), "pinned": v,
                          "params": {k: pay.get(k) for k in ("params", "settings", "read") if k in pay},
                          "members": mem}

# The workflows the two sets come from, and the borders the Halo used.
def wf(aid, v=None):
    rec = AR.get(aid) or {}
    pay = AR.payload(aid, v) or {}
    return rec, pay
for aid in ("178daabb125c", "4e5ce690d4b1", "bac8eaf5dfa8", "6fa7fef7b7a3"):
    rec, pay = wf(aid)
    run = pay.get("run") or {}
    out["wf_" + aid] = {"nickname": rec.get("nickname"), "version": rec.get("version"),
                        "definition": pay.get("definition"), "counts": run.get("counts"),
                        "grace": run.get("grace"), "at": run.get("at")}

# Event-level cross-tab: the 10% set's run against the Halo run, same target.
_r10, p10 = wf("bac8eaf5dfa8", 3)
_rh, ph = wf("6fa7fef7b7a3", 3)
def classes(run):
    cols = run["cols"]
    gids = cols["gids"]
    d = {}
    for cls, g, t in zip(cols["cls"], cols["g"], cols["t"]):
        if g is None or t is None:
            continue
        d[(gids[int(g)], round(float(t), 6))] = cls
    return d
c10 = classes(p10["run"])
ch = classes(ph["run"])
out["n_events"] = {"10pct_run": len(c10), "halo_run": len(ch), "same_keys": len(set(c10) & set(ch))}
tab = collections.Counter((c10.get(k), ch.get(k)) for k in set(c10) | set(ch))
out["crosstab_10pct_x_halo"] = {"%s | %s" % k: v for k, v in sorted(tab.items(), key=lambda x: -x[1])}

# Each room set: the read's stamps against the run's kept stamps.
groups_all = A._xm_groups(sorted({k[0] for k in c10}))
room = A._er_rooms()["dentate_spike"]
for v, run, cmap in ((5, p10["run"], c10), (6, ph["run"], ch)):
    pay = AR.payload(room["id"], v)
    keep = xraymany.inside_by_gid(run)
    rows = []
    bycls = collections.Counter()
    for rec in pay["recordings"]:
        gid = rec["gid"]
        got = A._dspca_load(gid, rec["read"])
        st = np.asarray([r.get("stamp_s") for r in got.get("rows") or []], dtype=float)
        want = np.asarray(keep.get(gid) or [], dtype=float)
        same_n = st.size == want.size
        maxd = float(np.max(np.abs(np.sort(st) - np.sort(want)))) if same_n and st.size else None
        dup = int(st.size - np.unique(np.round(st, 6)).size)
        for t in st:
            bycls[cmap.get((gid, round(float(t), 6)), "NOT IN RUN")] += 1
        rows.append({"label": rec["session_label"], "group_card": rec.get("group"), "group_now": groups_all.get(gid),
                     "n_card": rec["n"], "n_read": int(st.size), "n_run": int(want.size),
                     "max_dt_s": maxd, "dups": dup, "missed": len(got.get("missed") or []), "bad": sorted(int(b) for b in (got.get("bad") or {}))})
    out["room_v%d" % v] = {"rows": rows, "classes_of_its_events": dict(bycls)}

with open(os.path.join(os.path.dirname(__file__), "integ2.json"), "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1, default=str)
print("ok")
