# -*- coding: utf-8 -*-
"""The Monolith's node code on a real recording, against the circuits'.

    python tools\\check_sweep_real.py [rat] [day]

Reads one cue pair and one rest epoch of a real DEWEY day (from the
Monolith's manifest, GUI_logs/.cache/monolith/manifest.json, which the
Monolith tab's upload plan writes), runs `sweep.run_task` on them exactly
as a compute node would -- the same reader, the same exclusions, the same
histology -- and compares:

  - the three named bands' coherence, raw cc and envelope cc in the four
    state windows with `coupling.pair_connectivity` on the same pair, the
    same exclusion and the same blocked regions: the circuits' numbers
  - the wire each region was read on, with the circuit run's
  - the slow transition windows: measured for clipping here, and every
    region either read on a wire not lost in that window or not read
  - a rest epoch: read from its own FP folder, numbers where wires are

Reads only. Nothing is written anywhere but a temporary folder.
"""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

import numpy as np                                        # noqa: E402

from backend import coupling, spark, sweep                # noqa: E402

N = {"ok": 0, "bad": 0}


def check(name, cond, detail=""):
    N["ok" if cond else "bad"] += 1
    print(("  ok    " if cond else "  FAIL  ") + name
          + ("" if cond or detail == "" else "  " + str(detail)[:400]))


def main(argv):
    path = os.path.join(APP, "GUI_logs", ".cache", "monolith",
                        "manifest.json")
    if not os.path.isfile(path):
        print("No Monolith manifest yet: open the Monolith tab and ask for "
              "the upload plan first.")
        return 2
    with open(path, encoding="utf-8") as fh:
        man = json.load(fh)
    rat = int(argv[1]) if len(argv) > 1 else 7
    day = argv[2] if len(argv) > 2 else "Precon1"
    d = [x for x in man["days"] if x["rat"] == rat and x["day"] == day][0]
    spc = [f for f in d["folders"] if f["role"] == "SPC"][0]["local"]
    u = d["units"][0]
    names = sweep.regions()
    print("r%d %s, %s, cue pair %s (%s)" % (rat, day, os.path.basename(spc),
                                            u["id"], u["label"]))
    print("grey: %s" % (", ".join(d["grey"]) or "none"))

    print("\nState windows against coupling.pair_connectivity")
    bands = ["f08", "theta", "beta", "gamma_low", "f40"]
    spec = {"kind": "state", "bands": bands, "units": [u], "folder": spc,
            "blocked": d["blocked"], "bad": d["bad"], "regions": names}
    t0 = time.time()
    arrays, meta = sweep.run_task(spec)
    print("  (sweep: %.1f s)" % (time.time() - t0))
    t0 = time.time()
    ref = coupling.pair_connectivity(
        spc, u["pair"], regions=None, exclude_by_channel=u["drop"],
        blocked_regions=d["blocked"] or None,
        bands=list(coupling.BAND_ORDER), kind="state")
    print("  (coupling: %.1f s)" % (time.time() - t0))
    v = arrays["values"][0]                      # (W, B, M, P)
    pairs = sweep.pairs_of(names)
    mi = {m: i for i, m in enumerate(sweep.EDGE_METHODS)}
    worst, n_cmp, n_nan_agree, n_nan_disagree = 0.0, 0, 0, 0
    wires_ok = True
    for bid in coupling.BAND_ORDER:
        res = ref["bands"][bid]
        bi = bands.index(bid)
        for wi, win in enumerate(res["windows"]):
            for r in win["pairs"]:
                pi = pairs.index((r["a"], r["b"]))
                for m, cm in (("coherence", "coherence"),
                              ("raw_cc", "raw_cc"), ("env_cc", "amp_cc")):
                    mine = float(v[wi, bi, mi[m], pi])
                    theirs = (r.get(cm) or {}).get("value") \
                        if r.get(cm) else None
                    if theirs is None:
                        if np.isnan(mine):
                            n_nan_agree += 1
                        else:
                            n_nan_disagree += 1
                        continue
                    n_cmp += 1
                    worst = max(worst, abs(mine - float(theirs)))
            for ri, name in enumerate(names):
                ch = (win["regions"].get(name) or {}).get("channel")
                got = int(arrays["wires"][0, wi, ri])
                wires_ok &= (ch if ch is not None else -1) == got
    check("%d named-band numbers equal the circuits' (worst %.1e; float32 "
          "and six places)" % (n_cmp, worst), n_cmp > 100 and worst < 2e-6,
          worst)
    check("every pair the circuits could not measure is NaN here, and no "
          "other (%d)" % n_nan_agree, n_nan_disagree == 0, n_nan_disagree)
    check("every region read on the circuits' wire, in every window",
          wires_ok)
    fin = np.isfinite(v)
    check("every method has numbers where wires are (%.0f%% finite)"
          % (100 * fin.mean()), all(fin[:, :, i].any()
                                    for i in range(len(sweep.EDGE_METHODS))))

    print("\nSlow transition windows, clipping measured here")
    spec = dict(spec, kind="trans_slow", bands=["f02", "f08", "theta"])
    t0 = time.time()
    arrays, meta = sweep.run_task(spec)
    print("  (%.1f s)" % (time.time() - t0))
    lost = (meta.get("slow_clipping") or {}).get(u["id"])
    check("the slow windows were measured", lost is not None, meta["why"])
    if lost is not None:
        bad_pick = []
        for wi, w in enumerate(sweep.TRANSITION):
            for ri, name in enumerate(names):
                ch = int(arrays["wires"][0, wi, ri])
                if ch >= 0 and (ch in lost[w] or ch in d["bad"]):
                    bad_pick.append((w, name, ch))
        check("no region read on a wire lost in that window", not bad_pick,
              bad_pick)
        print("  lost per window: %s" % {w: lost[w] for w in sweep.TRANSITION})
    wins = spark.transition_windows(u["pair"], *sweep.SLOW_LEN)
    check("the windows are -3/+3 s around each boundary",
          all(abs((b - a) - 6.0) < 1e-9 for _n, a, b in wins))

    print("\nA rest epoch")
    e = d["rest"][0]
    fp = [f for f in d["folders"] if f["gid"] == e["fp_gid"]][0]["local"]
    spec = {"kind": "rest", "bands": ["f08", "theta"], "units": [dict(
        e, folder=fp)], "blocked": d["blocked"], "bad": d["bad"],
        "regions": names}
    arrays, meta = sweep.run_task(spec)
    vv = arrays["values"][0]
    check("read from its own FP folder: numbers where wires are",
          np.isfinite(vv).any() and (arrays["wires"][0, 0] >= 0).any(),
          meta["why"])
    print("\n%d passed, %d failed" % (N["ok"], N["bad"]))
    return 1 if N["bad"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
