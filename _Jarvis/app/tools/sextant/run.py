"""Place recordings end to end and write Seahorse's files.

    python tools/sextant/run.py m2 m60          # these mice
    python tools/sextant/run.py --ctl           # the 8 controls
    python tools/sextant/run.py --pten          # the 9 PTEN mice
    python tools/sextant/run.py --all --jobs 3  # everything, 3 at a time
    python tools/sextant/run.py --normal --jobs 3   # controls with the dentate
                                                    # free to stretch: normal's range

PTEN mice are placed with the dentate free to stretch below the fissure (the
user, 2026-11-27: "learn normal from controls"); controls are placed with one
size factor, and fitted once more with the stretch free only to learn how
far a normal dentate strays from the atlas (normal.json).

For each: evidence (if not cached) -> detectors -> both methods -> the
report, written to web/seahorse/sextant/<gid>.json, and the index of every
placed recording to web/seahorse/sextant/index.json.
"""
import json
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, APP)

LOGS = os.path.join(APP, "GUI_logs")
CACHE = os.path.join(LOGS, ".cache", "sextant")
WEB = os.path.join(APP, "web", "seahorse", "sextant")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def one(mouse, normal=False):
    import numpy as np
    from backend import stratasteps as st
    from backend.sextant import atlas as A
    from backend.sextant import cohort, detectors, evidence, report, solve
    st.configure(LOGS)
    rec = cohort.recordings(LOGS, only={mouse})[0]
    t0 = time.time()
    p = os.path.join(CACHE, rec["gid"], "evidence.npz")
    if not os.path.exists(p):
        ev = evidence.gather(LOGS, rec, log=log)
        ev["mouse"] = rec["mouse"]
        evidence.save(p, ev)
    ev = evidence.load(p)
    lms, notes = detectors.detect(ev)
    bad = np.asarray(ev["is_bad"], bool) | detectors.noisy(ev)
    atl = A.load()
    stretch = normal or rec["group"] != "CTL"
    out = solve.place(atl, ev, lms, bad, log=lambda *a: log(mouse, *a), stretch=stretch)
    rep = report.build(atl, rec, ev, lms, notes, out, bad)
    if normal:
        st = rep["answer"].get("stretch") or {}
        r = rep["answer"]["ranges"]["k"]
        p = os.path.join(CACHE, rec["gid"], "normal.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"gid": rec["gid"], "mouse": rec["mouse"], "k": st.get("k"), "range": r,
                       "hinge": st.get("hinge")}, f)
        return "%-4s normal-range fit: dentate stretch k %.2f [%.2f, %.2f]" % (rec["mouse"], st.get("k") or 1.0, r["lo"], r["hi"])
    os.makedirs(WEB, exist_ok=True)
    tmp = os.path.join(WEB, rec["gid"] + ".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rep, f, separators=(",", ":"), default=float)
    os.replace(tmp, os.path.join(WEB, rec["gid"] + ".json"))
    a = rep["answer"]
    return ("%-4s %-4s %s  entry AP %.2f ML %.2f  tilts %.1f/%.1f  size %.2f  depth c1 %d c64 %d  "
            "[%s/%s/%s/%s]  %.0f s" % (
                rec["mouse"], rec["group"], rec["hemisphere"], a["entry"]["ap"], a["entry"]["ml"],
                a["tilt_ml"], a["tilt_ap"], a["scale"], a["depth_um"]["contact1"], a["depth_um"]["contact64"],
                a["words"]["ap"], a["words"]["ml"], a["words"]["depth"], a["words"]["tilt"], time.time() - t0))


def write_normal():
    """normal.json: each control's dentate stretch, fitted free, and the
    range they span -- what a PTEN mouse's stretch is read against."""
    from backend.sextant import cohort
    rows = []
    for m, g, gid in cohort.COHORT:
        p = os.path.join(CACHE, gid, "normal.json")
        if g == "CTL" and os.path.exists(p):
            rows.append(json.load(open(p, encoding="utf-8")))
    if not rows:
        return None
    ks = sorted(r["k"] for r in rows if r.get("k") is not None)
    import statistics as stx
    out = {"controls": rows, "k_lo": ks[0], "k_hi": ks[-1], "k_mean": round(stx.mean(ks), 3),
           "k_sd": round(stx.pstdev(ks), 3) if len(ks) > 1 else None}
    with open(os.path.join(WEB, "normal.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    # every PTEN placement says where its stretch falls
    for name in os.listdir(WEB):
        if not name.startswith("s") or not name.endswith(".json"):
            continue
        fp = os.path.join(WEB, name)
        d = json.load(open(fp, encoding="utf-8"))
        st = d["answer"].get("stretch")
        if d.get("group") == "CTL" or not st:
            continue
        k = st["k"]
        st["normal"] = {"lo": out["k_lo"], "hi": out["k_hi"], "mean": out["k_mean"], "sd": out["k_sd"]}
        st["outside"] = bool(k < out["k_lo"] or k > out["k_hi"])
        with open(fp + ".tmp", "w", encoding="utf-8") as f:
            json.dump(d, f, separators=(",", ":"))
        os.replace(fp + ".tmp", fp)
    return out


def write_index():
    items = []
    for name in sorted(os.listdir(WEB)) if os.path.isdir(WEB) else []:
        if not name.endswith(".json") or name == "index.json":
            continue
        try:
            d = json.load(open(os.path.join(WEB, name), encoding="utf-8"))
        except (OSError, ValueError):
            continue
        a = d["answer"]
        items.append({"gid": d["gid"], "mouse": d["mouse"], "group": d["group"], "side": d["side"],
                      "ko": d.get("ko"), "pspikes": d.get("pspikes"), "line": a["line"],
                      "entry": a["entry"], "words": a["words"], "tilt_ml": a["tilt_ml"],
                      "tilt_ap": a["tilt_ap"]})
    order = {"CTL": 0, "PTEN": 1}
    items.sort(key=lambda x: (order.get(x["group"], 2), int(x["mouse"][1:])))
    with open(os.path.join(WEB, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"schema": 1, "made": time.strftime("%Y-%m-%d %H:%M"), "recordings": items}, f, indent=1)


def main(argv):
    from backend.sextant import cohort
    jobs = 1
    if "--jobs" in argv:
        jobs = int(argv[argv.index("--jobs") + 1])
    mice = [a for a in argv if a.startswith("m") and a[1:].isdigit()]
    if "--ctl" in argv or "--all" in argv:
        mice += [m for m, g, _ in cohort.COHORT if g == "CTL"]
    if "--pten" in argv or "--all" in argv:
        mice += [m for m, g, _ in cohort.COHORT if g == "PTEN"]
    normal = "--normal" in argv
    if normal and not mice:
        mice = [m for m, g, _ in cohort.COHORT if g == "CTL"]
    if jobs <= 1:
        for m in mice:
            try:
                log(one(m, normal))
            except Exception:
                log(m, "FAILED")
                traceback.print_exc()
    else:
        with ProcessPoolExecutor(jobs) as ex:
            futs = {ex.submit(one, m, normal): m for m in mice}
            for f, m in futs.items():
                try:
                    log(f.result())
                except Exception:
                    log(m, "FAILED")
                    traceback.print_exc()
    if normal or "--pten" in argv or "--all" in argv or "--write-normal" in argv:
        w = write_normal()
        if w:
            log("normal range of the dentate stretch: %.2f to %.2f (mean %.2f)" % (w["k_lo"], w["k_hi"], w["k_mean"]))
    if not normal:
        write_index()
        log("index written")


if __name__ == "__main__":
    main(sys.argv[1:])
