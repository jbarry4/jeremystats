"""KCNT1 preliminary, step K1: Root Canal pools, borders and the Halo and Strict sets, through the running Jarvis
(http://127.0.0.1:8733). The reads were made on the VACC by Root Canal's own batch (where: vacc).

  python k1_rootcanal.py pools      fit and save the WT pool and the all-genotype pool
  python k1_rootcanal.py borders    DS borders (Snap, 5% and 10% grace) around the WT pool, applied to the all pool
  python k1_rootcanal.py sets       the Halo set (5% DS + PTEN P-spike border + halo 2 / 1.5) and the Strict set
  python k1_rootcanal.py report     counts per mouse and genotype

Ids are kept in k1_ids.json beside this file.
"""
import json
import os
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8733"
HERE = os.path.dirname(os.path.abspath(__file__))
IDS = os.path.join(HERE, "k1_ids.json")

# entry id -> (label, genotype, Root Canal read made on the VACC 2026-11-27)
MICE = {
    "ac407abaa569": ("m1619", "WT", "64b4d692a7b8"),
    "22749a284641": ("m526", "WT", "4c2d452a245b"),
    "aa1d581d5f7e": ("m1609", "Het", "bee0870818f4"),
    "ef5031882809": ("m576", "Het", "b00f4dc80779"),
    "9a12a5c1afaa": ("m1603", "Hom", "a1ec92e8a2a4"),
    "a1eb8aa0f5d1": ("m306", "Hom", "2ce99d200901"),
}
# The PTEN pools' "Optimized parameters" (pool 3561fc988afd), copied exactly: the reused P-spike border only means
# something if KCNT1 events are measured the way its events were.
MEMBER_PARAMS = {"band_hi": 420.0, "band_lo": 240.0, "centres": None, "cluster_calls": {}, "cluster_names": {},
                 "complete_only": False, "cross_ms": 75.0, "drawn": [], "filt": "custom", "flank_ms": [30.0, 60.0],
                 "flips": [], "hi_hz": 150.0, "k": 2, "lo_hz": 10.0, "mains_out": True, "margin": None, "n_init": 10,
                 "order": 3, "retry": [], "seed": 0, "win_ms": 33.0}
MEASURE = {"band_hi": 420.0, "band_lo": 240.0, "cross_ms": 75.0, "filt": "custom", "hi_hz": 150.0, "lo_hz": 10.0,
           "mains_out": True, "order": 3, "win_ms": 33.0}
PSPIKE = {"artifact_id": "4e5ce690d4b1", "version": 2}   # PTEN's P-spike (IED) border, reused unchanged (user, 11-27)
TAG = "KCNT1 prelim (2 WT, 2 Het, 2 Hom)"


def call(path, body=None, timeout=3600):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def ids():
    return json.load(open(IDS)) if os.path.exists(IDS) else {}


def save_ids(d):
    json.dump(d, open(IDS, "w"), indent=1)


def pool_body(entries):
    return {"members": [{"key": "u:%s:%s" % (e, MICE[e][2]), "params": dict(MEMBER_PARAMS)} for e in entries],
            "mouse_types": {}, "focus": None, "measure": dict(MEASURE), "k": 2, "complete_only": False,
            "cluster_calls": {}, "cluster_names": {}, "margin": None, "border": None, "drawn": [], "all_ds": None}


def counts_by_mouse(run):
    out = {}
    for row in run.get("by_mouse") or []:
        out[row.get("label")] = {k: v for k, v in row.items() if k not in ("key", "label", "mouse_type")}
    return out


step = sys.argv[1]
D = ids()
if step == "pools":
    wt = [e for e in MICE if MICE[e][1] == "WT"]
    for key, ents, nick in (("pool_wt", wt, "KCNT1 prelim WT Baseline (Optimized parameters)"),
                            ("pool_all", list(MICE), "KCNT1 prelim WT, Het and Hom Baseline (Optimized parameters)")):
        b = pool_body(ents)
        got = call("/api/rootcanal/pool/fit", b)
        if not got.get("ok"):
            print(key, "FIT FAILED", got.get("error"))
            sys.exit(1)
        print(key, "fit:", got.get("counts"), "n", got.get("n"))
        b.update(nickname=nick, note="%s. Reads made on the VACC (Root Canal batch), measured with the PTEN pools' "
                                     "Optimized parameters." % TAG)
        if D.get(key):
            b["artifact_id"] = D[key]
        s = call("/api/rootcanal/pool/save", b)
        art = {"id": s.get("artifact_id"), "version": s.get("version")}
        print("   saved:", s.get("ok"), s.get("error"), art.get("id"), "v", art.get("version"))
        if s.get("ok"):
            D[key] = art.get("id")
            save_ids(D)
elif step == "borders":
    for key, grace, nick in (("ds5", 0.05, "KCNT1 prelim WT DS border (Optimized parameters/Snap/5% grace)"),
                             ("ds10", 0.10, "KCNT1 prelim WT DS border (Optimized parameters/Snap/10% grace)")):
        body = {"kind": "ds", "nickname": nick, "grace": grace, "shape": "hull",
                "source": {"artifact_id": D["pool_wt"], "type": "pool"},
                "target": {"artifact_id": D["pool_all"]}, "folder": ["KCNT1 prelim"]}
        if D.get(key):
            body["artifact_id"] = D[key]
        s = call("/api/rootcanal/workflow/save", body)
        print(key, "saved", s.get("ok"), s.get("error"), s.get("artifact_id"), "v", s.get("version"))
        if not s.get("ok"):
            sys.exit(1)
        D[key] = s["artifact_id"]
        save_ids(D)
        r = call("/api/rootcanal/workflow/%s/run" % D[key], {"bank": False})
        if not r.get("ok"):
            print("   RUN FAILED", r.get("error"))
            sys.exit(1)
        run = r["run"]
        print("   run v%s counts %s kept %s" % (r["version"], run.get("counts"), run.get("kept")))
        for lab, c in counts_by_mouse(run).items():
            print("     ", lab, c)
elif step == "sets":
    for key, ds, halo, nick in (
            ("halo", "ds5", True, "KCNT1 prelim Ambiguous Halo set (Optimized Parameters/Snap; PTEN P-spike border)"),
            ("strict", "ds10", False, "KCNT1 prelim Ambiguous Strict set (Optimized Parameters/Snap/10% Grace; "
                                      "PTEN P-spike border)")):
        body = {"kind": "ambiguous", "nickname": nick, "folder": ["KCNT1 prelim"],
                "uses": {"ds": {"artifact_id": D[ds]}, "pspike": dict(PSPIKE)},
                "target": {"artifact_id": D["pool_all"]}}
        if D.get(key):
            body["artifact_id"] = D[key]
        s = call("/api/rootcanal/workflow/save", body)
        print(key, "saved", s.get("ok"), s.get("error"), s.get("artifact_id"), "v", s.get("version"))
        if not s.get("ok"):
            sys.exit(1)
        D[key] = s["artifact_id"]
        save_ids(D)
        r = call("/api/rootcanal/workflow/%s/run" % D[key], {})
        if not r.get("ok"):
            print("   RUN FAILED", r.get("error"))
            sys.exit(1)
        print("   run v%s counts %s kept %s" % (r["version"], r["run"].get("counts"), r["run"].get("kept")))
        D[key + "_run_v"] = r["version"]
        if halo:
            h = call("/api/rootcanal/workflow/%s/halo" % D[key], {"version": r["version"], "reach": 2, "margin": 1.5})
            print("   halo:", h.get("ok"), h.get("error"), "v", h.get("version"),
                  (h.get("run") or {}).get("counts"))
            if h.get("ok"):
                D[key + "_run_v"] = h.get("version")
        save_ids(D)
elif step == "report":
    for key in ("halo", "strict"):
        d = call("/api/rootcanal/workflow/%s" % D[key])
        a, p = d["artifact"], d["payload"]
        run = p.get("run") or {}
        print("==", key, a.get("nickname"), "v", a.get("version"), run.get("counts"))
        for lab, c in counts_by_mouse(run).items():
            print("   ", lab, c)
