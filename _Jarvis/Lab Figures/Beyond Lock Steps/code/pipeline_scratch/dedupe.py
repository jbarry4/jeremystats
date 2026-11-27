"""Duplicate Spike stamps (user, 2026-11-19): neighbours under 10 ms apart are
one event. In each run of them, the stamp with the largest CSD sink stays a
Spike; the others become Garbage, in a new version of the Confluence set.
Nothing moves or is deleted. Dry run unless --apply."""
import json
import os
import sys

import numpy as np

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
sys.path.insert(0, APP)
from backend import eventbank, store as storemod, rootcanal, dspca, braces  # noqa: E402

APPLY = "--apply" in sys.argv
S = os.path.dirname(os.path.abspath(__file__))
logs = os.path.join(APP, "GUI_logs")
STORE = storemod.Store(logs, auto_stage=False)
B = eventbank.EventBank(logs, STORE)
IDS = {"bfa98498290b": "m1", "afa70b62f372": "m13", "41dd94702761": "m2", "edc1a5080093": "m21", "43a2cfedde17": "m22",
       "f4c18a9a8bd4": "m26", "35c325a44d44": "m28", "db66d3c694fd": "m3", "a62d1b78448b": "m33", "eaecc4a5e194": "m34",
       "b60578899091": "m5", "8aad148bd6f6": "m51", "1429bf1f239f": "m59", "cb139fb2ea29": "m6", "d4a4bcb4e47f": "m60",
       "ab69363ee622": "m61", "ece9a84acdea": "m7", "2a8e47760eea": "m8"}
reads = dict(l.strip().split(" ") for l in open(os.path.join(S, "pool_reads.txt")) if l.strip())
GAP = 0.010


def sinks(z):
    """Each event's deepest CSD sink within +-2 ms of its stamp (A/m^3; more negative = bigger sink)."""
    meta = json.loads(str(z["meta"]))
    nums, fs = meta["nums"], float(meta["snip_fs"])
    run = (meta.get("runs") or [{"rows": list(range(len(nums)))}])[0]
    rows = list(run["rows"])
    bad = {str(k) for k in (meta.get("bad") or {})}
    chans = [{"number": nums[k]} for k in rows]
    dp = dspca.Params(probe=meta.get("probe"))
    half = z["snip"].shape[2] // 2
    w = int(round(0.002 * fs))
    out = []
    for x in z["snip"]:
        lfp = rootcanal._ds_filter(np.nan_to_num(x[rows].astype(float)), fs)
        lfp = braces.repair(lfp, chans, {nums[k]: "bad" for k in rows if str(nums[k]) in bad})
        csd = dspca.toothy_csd(lfp, float(meta.get("spacing_um") or 50.0), dp)[1]
        out.append(float(np.min(csd[:, half - w:half + w + 1])))
    return np.array(out)


report, total = [], 0
for eid, lab in IDS.items():
    rec = B.get(eid)
    ev = rec["events"]
    sp = sorted([i for i, e in enumerate(ev) if e.get("label_id") == "spike"], key=lambda i: float(ev[i]["start"]))
    t = np.array([float(ev[i]["start"]) for i in sp])
    runs, cur = [], [0]
    for k in range(1, len(sp)):
        if t[k] - t[k - 1] < GAP:
            cur.append(k)
        else:
            if len(cur) > 1:
                runs.append(cur)
            cur = [k]
    if len(cur) > 1:
        runs.append(cur)
    if not runs:
        continue
    z = np.load(os.path.join(logs, ".cache", "rootcanal", "%s__%s.npz" % (rec["gid"], reads[eid].split(":")[-1])), allow_pickle=True)
    zs = sinks(z)
    zt = z["t"]
    drop = set()
    for r in runs:
        sk = []
        for k in r:
            j = int(np.argmin(np.abs(zt - t[k])))
            assert abs(zt[j] - t[k]) < 1e-4
            sk.append(zs[j])
        keep = r[int(np.argmin(sk))]            # deepest sink; on a tie, the earlier stamp
        for k in r:
            if k != keep:
                drop.add(sp[k])
        report.append({"mouse": lab, "times": [round(float(t[k]), 6) for k in r], "gaps_ms": [round(float((t[b] - t[a]) * 1000), 3) for a, b in zip(r, r[1:])],
                       "sink": [round(float(s), 3) for s in sk], "kept": round(float(t[keep]), 6),
                       "tie": len(set(np.round(sk, 6))) < len(sk)})
    total += len(drop)
    new = []
    for i, e in enumerate(ev):
        e = dict(e)
        if i in drop:
            e["label_id"], e["label"] = "garbage", "Garbage"
        new.append(e)
    print("%-4s runs %2d  -> %2d stamps marked Garbage (spikes %d -> %d)" % (lab, len(runs), len(drop), len(sp), len(sp) - len(drop)))
    if APPLY:
        entry = {k: v for k, v in rec.items() if k not in ("events", "versions", "history", "_sync", "n", "by_label")}
        entry.update(events=new, curated=True, pipeline=(rec.get("source") or {}).get("pipeline") or "The Confluence",
                     added_by="Shahriar Tafti", by_label=None,
                     version_note=("Duplicate stamps marked Garbage (2026-11-19): %d Spike stamp(s) under 10 ms from a neighbouring "
                                   "Spike were the same dentate spike written twice (made by a +-200 ms Braces pass on the Incisor "
                                   "set). In each run the stamp with the deepest CSD sink stays a Spike. No stamp moved." % len(drop)),
                     version_tag="dedupe")
        entry.pop("by_label")
        out = B.add(entry)
        print("     wrote v%s; newest is aligned: %s" % (out.get("version"), bool(out.get("aligned"))))
with open(os.path.join(S, "dedupe_report.json"), "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=1)
print("runs", len(report), "stamps to Garbage", total, "ties", sum(r["tie"] for r in report))
