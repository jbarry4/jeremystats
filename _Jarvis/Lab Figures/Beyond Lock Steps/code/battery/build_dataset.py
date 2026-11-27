"""Freezes one event set (v6 = Halo set, v8 = No P-spikes set) of the
Extraction Room into a single file the battery reads: data/ds_<set>.pkl.
Run once by the main session; nothing here talks to Jarvis.

  python build_dataset.py 6
"""
import json
import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = r"C:\Users\Z390\AppData\Local\Temp\claude\4f94f33fe0a28c30\7a6601ed-d746-46d4-b1b0-3073ab9de62e\scratchpad"
V = int(sys.argv[1]) if len(sys.argv) > 1 else 6
ON_PLANE = ("pca", "pca_gmm_line", "pca_gmm_curve")
IED = {"m8": "IED-", "m33": "IED-", "m1": "IED-", "m7": "IED-", "m13": "IED+", "m28": "IED+", "m3": "IED+", "m5": "IED+", "m34": "IED+"}
NOTES = {"m21": "Lab sheet: worried this recording is a bit high, potentially missing the bottom blade portion of DS1s.",
         "m51": "Lab sheet: maybe a miss? Uncertain.", "m13": "Lab sheet: bottom blade is too strong (color scale note)."}


def load(name):
    with open(os.path.join(SRC, name % V), "rb") as f:
        return pickle.load(f)


recs = load("deep_v%d.pkl")
full = load("deep_full_v%d.pkl")
pca2 = load("deep_pca2_v%d.pkl")
opt = load("deep_opt_v%d.pkl")
opt2 = load("deep_opt2_v%d.pkl")
ds3 = load("deep_ds3_v%d.pkl")
fields = json.load(open(os.path.join(HERE, "data", "lab_fields.json")))


def eligible(e, n):
    return min(e["n1"], e["n2"]) >= max(5, 0.05 * n)


out = []
for d in recs:
    F = full[d["gid"]]
    n = d["n"]
    assert list(F["nums_all"]) == list(F["nums_lfp"]), d["lab"]
    na = [int(x) for x in F["nums_all"]]
    a, b = na.index(d["ns"][0]), na.index(d["ns"][-1])
    labels, score, gap = {}, {}, {}
    for m, e in d["splits"].items():
        if "err" in e or e.get("si") is None:
            continue
        labels[m] = {"types": np.asarray(e["types"], np.int8), "si": float(e["si"]), "n1": int(e["n1"]), "n2": int(e["n2"]),
                     "axis": np.asarray(e["x"], np.float32)}
        if not e.get("why") and "score" in e:
            score[m] = np.asarray(e["score"], np.float32)
            gap[m] = abs(int(e["oml"]) - int(e["mml"])) * 50
    for m, e in (pca2.get(d["gid"], {}).get("fits") or {}).items():
        if "err" in e or e.get("si") is None:
            continue
        labels[m] = {"types": np.asarray(e["types"], np.int8), "si": float(e["si"]), "n1": int(e["n1"]), "n2": int(e["n2"]), "axis": None,
                     "bootstrap_stability": e.get("stable")}
    for m, e in (opt.get(d["gid"], {}).get("fits") or {}).items():
        if "err" in e or e.get("si") is None:
            continue
        labels[m] = {"types": np.asarray(e["types"], np.int8), "si": float(e["si"]), "n1": int(e["n1"]), "n2": int(e["n2"]), "axis": None,
                     "heldout_si": e.get("heldout")}
    for m, e in (ds3.get(d["gid"]) or {}).items():
        if not e.get("why") and "score" in e:
            score[m] = np.asarray(e["score"], np.float32)
            gap[m] = abs(int(e["oml"]) - int(e["mml"])) * 50
    for m, e in labels.items():
        e["eligible"] = bool(eligible(e, n))
    conv_keys = [k for k in labels if not k.startswith("opt_")]
    ok = [k for k in conv_keys if labels[k]["eligible"]]
    used = max(ok, key=lambda k: labels[k]["si"]) if ok and n >= 20 else None
    onp = [k for k in ON_PLANE if k in labels]
    onp_ok = [k for k in onp if labels[k]["eligible"]]
    conv = max(onp_ok or onp, key=lambda k: labels[k]["si"]) if onp and n >= 20 else None
    lab_f = fields.get(d["lab"]) or {}
    rec = {"lab": d["lab"], "gid": d["gid"], "label": d["label"], "group": d["g"], "subgroup": IED.get(d["lab"], "CTL"), "ko": float(d["ko"]),
           "n": int(n), "dur_s": float(d["dur"]), "date": d["label"].split()[-1], "session": d["label"].split()[2],
           "contacts": na, "bad": [int(x) for x in F["bad"]], "lab_field": [lab_f.get(str(c), "") for c in na], "band": (int(a), int(b)),
           "hump_cut_row": None if d["hump_cut"] is None else int(a + d["hump_cut"]), "t_ms": np.asarray(F["tt"], np.float32),
           "csd": np.asarray(F["csd_ev"], np.float32), "lfp": np.asarray(F["lfp_ev"], np.float32),
           "times_s": None if d.get("times") is None else np.asarray(d["times"], float),
           "det_peak": None if d.get("peak") is None else np.asarray(d["peak"], float),
           "pc": np.asarray(pca2[d["gid"]]["X"], np.float32) if d["gid"] in pca2 else None,
           "theta_t": np.asarray(d.get("theta_t", []), float), "theta_p": np.asarray(d.get("theta_p", []), float),
           "labels": labels, "ds3_score": score, "ds3_gap_um": gap, "W": (opt2.get(d["gid"]) or {}).get("W") or {},
           "used": used, "conv": conv, "opt": "opt_curve" if "opt_curve" in labels else None,
           "interp": d.get("interp"), "sheet_note": NOTES.get(d["lab"], "")}
    out.append(rec)
    print("%-4s %-4s %-4s ko %5.1f n %4d band %2d-%2d cut %s bad %s | labels %2d ds3 %2d | used %s conv %s" % (
        rec["lab"], rec["group"], rec["subgroup"], rec["ko"], n, a, b, rec["hump_cut_row"], rec["bad"], len(labels), len(score), used, conv), flush=True)
os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
with open(os.path.join(HERE, "data", "ds_v%d.pkl" % V), "wb") as f:
    pickle.dump(out, f, protocol=4)
print("saved", len(out))
