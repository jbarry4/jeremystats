"""Does the Halo set (room v9) hold any P-spike? Read only.
1. The classes of the room's events in their workflow run (Halo Ambiguous 6fa7fef7b7a3 v5).
2. The P-spike border's own run: any room event that run calls inside the P-spike border.
3. The hand-curated P-spike sets: any room event within 20 ms of a stamp labeled P-spike."""
import collections
import os
import sys

import numpy as np

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402

AR = A.ARTIFACTS
room = A._er_rooms()["dentate_spike"]
pay = AR.payload(room["id"], 9)
src = pay["source"]["workflow"]
print("room v9 from", src)
run = AR.payload(src["artifact_id"], src["version"])["run"]
cols = run["cols"]
gids = cols["gids"]
cls_at = {}
for c, g, t in zip(cols["cls"], cols["g"], cols["t"]):
    if g is not None and t is not None:
        cls_at[(gids[int(g)], round(float(t), 4))] = c
print("run kind:", run.get("kind"), "| classes in the whole run:", dict(collections.Counter(cls_at.values())))

# the room's own events: the read each card was made from
lab = {}
room_t = {}
from backend import xraymany  # noqa: E402
kept = xraymany.inside_by_gid(run)
for r in pay["recordings"]:
    room_t[r["gid"]] = np.asarray(kept.get(r["gid"], []), float)
    lab[r["gid"]] = r["session_label"].split()[1]
    assert room_t[r["gid"]].size == r["n"], r["session_label"]
n = sum(v.size for v in room_t.values())
print("room events:", n)

# 1. class of each room event in the run
cc = collections.Counter()
for g, ts in room_t.items():
    keys = np.array([k[1] for k in cls_at if k[0] == g])
    cl = [cls_at[(g, k)] for k in keys]
    for t in ts:
        j = int(np.argmin(np.abs(keys - t)))
        cc[cl[j] if abs(keys[j] - t) < 0.005 else "not in run"] += 1
print("1. room events by run class:", dict(cc))

# 2. the P-spike border workflow's own run (the version the Halo run used)
d = A.ARTIFACTS.payload(src["artifact_id"], src["version"])
uses = (d.get("definition") or {}).get("uses") or {}
print("   Halo run used:", uses)
ps = uses.get("pspike") or {}
if ps.get("artifact_id"):
    prun = AR.payload(ps["artifact_id"], ps["version"])["run"]
    pc = prun["cols"]
    inside = collections.defaultdict(list)
    for c, g, t in zip(pc["cls"], pc["g"], pc["t"]):
        if c == "inside" and g is not None and t is not None:
            inside[pc["gids"][int(g)]].append(float(t))
    hit = 0
    for g, ts in room_t.items():
        pt = np.asarray(inside.get(g, []), float)
        if pt.size:
            hit += int((np.min(np.abs(ts[:, None] - pt[None, :]), axis=1) < 0.005).sum())
    print("2. room events inside the P-spike border (%s v%s): %d" % (ps["artifact_id"], ps["version"], hit))

# 3. hand-labeled P-spikes in the bank, same recordings (every entry, every label that says P-spike)
labels = collections.Counter()
for rec in A.BANK.all():
    g = rec.get("gid")
    if g not in room_t:
        continue
    for e in rec.get("events") or []:
        labels[(e.get("label_id"), e.get("label"))] += 1
print("   labels in those recordings' bank entries:", dict(labels))
PS = {"ied", "pspike", "p-spike", "p_spike"}
by = collections.defaultdict(lambda: [0, 0, set()])
for rec in A.BANK.all():
    g = rec.get("gid")
    if g not in room_t:
        continue
    pt = np.array([float(e["start"]) for e in rec.get("events") or [] if str(e.get("label_id") or "").lower() in PS], float)
    if not pt.size:
        continue
    d = np.min(np.abs(room_t[g][:, None] - pt[None, :]), axis=1)
    b = by[lab[g]]
    b[0] += int((d < 0.020).sum()); b[1] = max(b[1], pt.size); b[2].add(rec["id"])
for k, (h, n, ids) in sorted(by.items()):
    print("3. %-4s room events within 20 ms of a P-spike stamp: %d (P-spike stamps in the largest entry: %d; entries %d)" % (k, h, n, len(ids)))
