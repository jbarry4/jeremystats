"""
check_joe.py -- tab 8 (backend/joe.py) and its standalone script
(tools/joe_standalone.py), end to end, on made-up recordings written as real
Neuralynx files.

Eight rats (the identity sheet's own, so their sounds are real), Precon1 and
Precon4, eight trials a day, six regions on one wire each, FP1 and FP2 beside
every session. Planted:

  * theta: regions 0 and 1 share a 7 Hz rhythm in cue 1, on Precon4 only;
  * gamma: regions 2 and 3 share a 50 Hz rhythm in the first two seconds of
    cue 2, on Precon4 only;
  * FP: regions 4 and 5 share a 7 Hz rhythm in FP on Precon4 only, and never
    in the trials;
  * one clipped stretch: rat 4, Precon1, trial 2, region 0's wire at the
    rail through cue 2;
  * the sounds: nothing.

Each must be found where it was planted and nowhere else; the mixed model's
fixed effects are checked against least squares and the RM-ANOVA against a
hand-made F; the SPSS files are read back; and the standalone script, run on
the same folders, must give the same .csv files.

    python tools/check_joe.py [--keep]
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import joe, nlx, ratidentity                # noqa: E402

N = {"ok": 0, "bad": 0}


def check(name, cond, detail=""):
    N["ok" if cond else "bad"] += 1
    print("  %s  %s%s" % ("ok  " if cond else "FAIL", name, "" if cond else "   [%s]" % (detail,)), flush=True)


FS_RAW = 2000.0
ADBV = 0.000000030517578125
RATS = (3, 4, 6, 7, 8, 9, 10, 11)
DAYS = ("Precon1", "Precon4")
REGIONS = ["Right ACC", "Right OFC", "Right DHC", "Right RSC", "Left ACC", "Left OFC"]
CHAN = {name: [i + 1] for i, name in enumerate(REGIONS)}
TRIAL_EVERY = 45.0
FIRST = 40.0
N_TRIALS = 8
DUR = FIRST + N_TRIALS * TRIAL_EVERY + 30.0
FP_DUR = 200.0
T0_US = 1_000_000_000.0
CODE = {"Click": 124, "Noise": 122, "High": 118, "Low": 110}


def write_ncs(path, x_uv, chan, fs=FS_RAW, t0_us=T0_US):
    head = ("######## Neuralynx Data File Header\n-FileType CSC\n-AcqEntName CSC%d\n"
            "-SamplingFrequency %.4f\n-ADBitVolts %.24f\n-ADMaxValue 32767\n") % (chan, fs, ADBV)
    raw = head.encode("latin-1")
    raw += b"\x00" * (nlx.HEADER_BYTES - len(raw))
    counts = np.clip(np.round(-x_uv / (ADBV * 1e6)), -32767, 32767).astype(np.int16)
    n = nlx.SAMPLES_PER_RECORD
    nrec = counts.size // n
    rec = np.zeros(nrec, dtype=nlx.RECORD_DTYPE)
    rec["timestamp"] = np.round(t0_us + np.arange(nrec) * (n / fs * 1e6)).astype(np.uint64)
    rec["channel"] = chan
    rec["freq"] = int(round(fs))
    rec["nvalid"] = n
    rec["samples"] = counts[:nrec * n].reshape(nrec, n)
    with open(path, "wb") as fh:
        fh.write(raw)
        fh.write(rec.tobytes())


def write_nev(path, events, t0_us=T0_US):
    raw = b"######## Neuralynx Data File Header\n-FileType Event\n"
    raw += b"\x00" * (nlx.HEADER_BYTES - len(raw))
    rec = np.zeros(len(events), dtype=nlx.NEV_DTYPE)
    for i, (t, ttl) in enumerate(events):
        rec["timestamp"][i] = int(round(t0_us + t * 1e6))
        rec["event_id"][i] = 11
        rec["ttl"][i] = ttl
        rec["event_string"][i] = ("TTL Input on AcqSystem1_0 board 0 port 1 value (0x%04X)." % ttl).encode("latin-1")
    with open(path, "wb") as fh:
        fh.write(raw)
        fh.write(rec.tobytes())


def noise(rng, n, fs=FS_RAW):
    """Brown-ish noise, like a field potential, in microvolts."""
    from scipy.signal import lfilter
    w = rng.standard_normal(n)
    return lfilter([1.0], [1.0, -0.95], w) * 6.0


def make_rat_day(root, rat, day, rng):
    """One rat-day's three recordings, and its trials (opener, closer, cue type)."""
    ids = ratidentity.identity(rat)
    order = ["AB", "CD"] * (N_TRIALS // 2)
    trials, events = [], []
    for k, pr in enumerate(order):
        o = FIRST + k * TRIAL_EVERY + 20.0
        c = o + 10.0
        a, b = ids[pr[0]], ids[pr[1]]
        trials.append({"opener_t": round(o, 6), "closer_t": round(c, 6), "offset_t": round(c + 10.0, 6),
                       "cue_type": ratidentity.cue_type_of_pair(rat, pr), "pair": pr})
        events += [(o, CODE[a]), (o + 0.05, 126), (c, CODE[b]), (c + 0.05, 126), (c + 10.0, 126)]
    events.sort()
    n = int(DUR * FS_RAW)
    t = np.arange(n) / FS_RAW
    X = [noise(rng, n) for _r in REGIONS]
    p4 = day == "Precon4"
    for tr in trials:
        o, c = tr["opener_t"], tr["closer_t"]
        if p4:
            k = (t >= o) & (t < c)                      # cue 1: theta, regions 0 and 1
            s = 18.0 * np.sin(2 * np.pi * 7.0 * t[k] + rng.uniform(0, 2 * np.pi))
            X[0][k] += s
            X[1][k] += s
            k = (t >= c) & (t < c + 2.0)                # first 2 s of cue 2: gamma, regions 2 and 3
            s = 6.0 * np.sin(2 * np.pi * 50.0 * t[k] + rng.uniform(0, 2 * np.pi))
            X[2][k] += s
            X[3][k] += s
    if rat == 4 and day == "Precon1":
        tr = trials[1]
        k = (t >= tr["closer_t"] + 1.0) & (t < tr["closer_t"] + 1.4)
        X[0][k] = -32767 * ADBV * 1e6 * 1.001          # at the rail (the reader inverts)
    spc = os.path.join(root, "r%d_%s_SPC" % (rat, day))
    os.makedirs(spc)
    for i, x in enumerate(X):
        write_ncs(os.path.join(spc, "CSC%d.ncs" % (i + 1)), x, i + 1)
    write_nev(os.path.join(spc, "Events.nev"), events)
    fps = []
    for role in ("FP1", "FP2"):
        f = os.path.join(root, "r%d_%s_%s" % (rat, day, role))
        os.makedirs(f)
        nf = int(FP_DUR * FS_RAW)
        tf = np.arange(nf) / FS_RAW
        Y = [noise(rng, nf) for _r in REGIONS]
        if p4:
            s = 18.0 * np.sin(2 * np.pi * 7.0 * tf + 0.3)
            Y[4] += s
            Y[5] += s
        for i, y in enumerate(Y):
            write_ncs(os.path.join(f, "CSC%d.ncs" % (i + 1)), y, i + 1)
        fps.append((role, f))
    units = [{"id": "p%02d" % (i + 1), "pair_id": i + 1, "cue_type": tr["cue_type"],
              "pair": {"pair_id": i + 1, "opener_t": tr["opener_t"], "closer_t": tr["closer_t"], "offset_t": tr["offset_t"]},
              "drop": {}, "manual": {}} for i, tr in enumerate(trials)]
    return {"rat": rat, "day": day, "gid": "fake-r%d-%s" % (rat, day), "bad": [], "blocked": {},
            "units": units, "folders": [{"role": "SPC", "local": spc}] + [{"role": r, "local": p} for r, p in fps]}


def _measure_day(d):
    """In a worker process: one made-up rat-day through the engine."""
    return joe.day_compute(d, REGIONS, CHAN)


def main():
    keep = "--keep" in sys.argv
    root = tempfile.mkdtemp(prefix="check_joe_")
    print("made-up recordings in", root)
    rng = np.random.default_rng(20261009)
    days = []
    t0 = time.time()
    for rat in RATS:
        for day in DAYS:
            days.append(make_rat_day(root, rat, day, rng))
    print("written in %.0f s" % (time.time() - t0))

    print("\nThe engine, one rat-day at a time")
    day_data = {}
    t0 = time.time()
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=max(1, min(4, (os.cpu_count() or 2) - 1))) as ex:
        for d, got in zip(days, ex.map(_measure_day, days)):
            day_data[(d["rat"], d["day"])] = got
    print("measured in %.0f s" % (time.time() - t0))
    a, fp, meta = day_data[(4, "Precon1")]
    wi = joe.WINDOWS.index("cue2")
    check("the clipped wire: region 0 not measured in that trial's cue 2, measured in its cue 1",
          np.isnan(a["power"][wi, 1, 0, 0]) and np.isfinite(a["power"][joe.WINDOWS.index("cue1"), 1, 0, 0]),
          (a["power"][wi, 1, 0, 0], a["power"][joe.WINDOWS.index("cue1"), 1, 0, 0]))
    check("seven windows, every trial, two bands, two methods", a["coh"].shape == (7, N_TRIALS, 2, 2, 15), a["coh"].shape)
    check("FP snippets: as many as the trials, 10 s and 20 s, inside FP1 and FP2 and 10 s from their ends",
          len(meta["fp"]["fp10"]) == N_TRIALS and len(meta["fp"]["fp20"]) == N_TRIALS
          and all(10.0 <= s["t0"] and s["t1"] <= FP_DUR - 10.0 for s in meta["fp"]["fp20"]), meta["fp"]["fp20"][:2])
    check("the FP snippets are the same every time (seeded)",
          joe.fp_random(meta["fp_recordings"], N_TRIALS, 20.0, joe.fp_seed(4, "Precon1", 20.0))
          == [(s["rec"], s["t0"], s["t1"]) for s in meta["fp"]["fp20"]], meta["fp_recordings"])

    # Method (b) against a hand-written mscohere, on one window.
    from scipy.signal import coherence, butter, filtfilt
    rs = np.random.default_rng(5)
    x = rs.standard_normal(10000)
    y = 0.6 * x + rs.standard_normal(10000)
    m = joe.measure([x, y], follow=False)
    bb, aa = butter(1, [59.0, 61.0], btype="bandstop", fs=1000.0)
    xb, yb = filtfilt(bb, aa, x), filtfilt(bb, aa, y)
    from scipy.signal import windows as W
    win = W.hann(1026, sym=True)[1:-1]
    f, C = coherence(xb, yb, fs=1000.0, window=win, noverlap=512, nfft=2048, detrend=False)
    msk = (f >= 5 - 1e-9) & (f <= 12 + 1e-9)
    check("Dickson coherence is mscohere(x, y, hanning(1024), 512, 2048) over theta",
          abs(m["coh"][0, 1, 0] - float(C[msk].mean())) < 1e-9, (m["coh"][0, 1, 0], float(C[msk].mean())))
    msk = (f >= 30 - 1e-9) & (f <= 90 + 1e-9) & ~((f >= 59 - 1e-9) & (f <= 61 + 1e-9))
    check("and over gamma without the notch's own 59–61 Hz bins", abs(m["coh"][1, 1, 0] - float(C[msk].mean())) < 1e-9)

    print("\nThe models")
    out = joe.build(day_data, REGIONS)
    res = {(r["model"], r["band"], r["method"]): r for r in out["results"]}
    def gate(mid, band, method="welch"):
        return (res[(mid, band, method)].get("gate") or {}).get("passed")
    def top(mid, band, method="welch"):
        post = [p for p in res[(mid, band, method)]["post"] if p.get("p") is not None]
        return min(post, key=lambda p: p["p"])["unit"] if post else None
    pr01 = "R ACC – R OFC"
    check("theta, Baseline vs Cue 1: opens its follow-ups, and its strongest pair is the planted one",
          gate("m2", "theta") and top("m2", "theta") == pr01, (res[("m2", "theta", "welch")]["gate"], top("m2", "theta")))
    check("and Cue 1 vs Cue 2 sees it too, the other way", gate("m5", "theta") and top("m5", "theta") == pr01)
    check("theta, Baseline vs Cue 2: nothing there", not gate("m3", "theta"), res[("m3", "theta", "welch")]["gate"])
    check("gamma, the switch (8–10 s vs 10–12 s): opens, the planted pair first",
          gate("m4", "gamma") and top("m4", "gamma") == "R DHC – R RSC", (res[("m4", "gamma", "welch")]["gate"], top("m4", "gamma")))
    check("gamma at the switch, Dickson's way too", gate("m4", "gamma", "dickson") and top("m4", "gamma", "dickson") == "R DHC – R RSC")
    check("trials vs FP (20 s), theta: the FP-only change found there, in its pair",
          gate("m6a", "theta") and top("m6a", "theta") == "L ACC – L OFC", (res[("m6a", "theta", "welch")]["gate"], top("m6a", "theta")))
    fpc = res[("m6a", "theta", "welch")]["cells"]
    check("and it is FP that changed, not the trials (FP's Precon4 − Precon1 larger than the trials')",
          (fpc["Precon4"]["fp"]["mean"] - fpc["Precon1"]["fp"]["mean"]) > (fpc["Precon4"]["trials"]["mean"] - fpc["Precon1"]["trials"]["mean"]))
    sound_open = [k for k in res if k[0] in ("c1", "c2", "c4") and k[1] == "gamma" and gate(*k)]
    check("the sound checks open nothing in gamma, where nothing was planted in a cue window but the switch", not sound_open, sound_open)
    snd_theta = [k for k in res if k[0] in ("c1", "c4") and k[1] == "theta" and gate(*k)]
    check("nor Noise vs Click, nor High vs Low, in theta: each pair of sounds opens the same cue in a rat", not snd_theta, snd_theta)
    check("but A/B/C/D does see the cue-1 change: A and C are cue 1", gate("c3", "theta") and top("c3", "theta") == pr01,
          (res[("c3", "theta", "welch")]["gate"], top("c3", "theta")))
    f2 = res[("m2", "theta", "welch")].get("follow") or {}
    check("the follow-ups run for the pair Holm keeps, with PLI, direction and PAC",
          [p["pair"] for p in f2.get("pairs", [])] == [pr01]
          and all(k in f2["pairs"][0]["measures"] for k in ("pli", "icoh", "gc_ab", "gc_ba", "xlag", "pac_ab", "pac_aa")), f2.get("basis"))
    check("no follow-ups where the gate stays shut", not res[("m3", "theta", "welch")].get("follow"))
    r2 = res[("m2", "theta", "welch")]
    check("the RM-ANOVA beside it: every rat has every cell here except the clipped one's", r2["rm"].get("n_rats") in (7, 8), r2["rm"])

    # The mixed model's fixed effects against least squares (balanced data,
    # so the GLS fixed effects equal OLS's); the RM-ANOVA against a hand F.
    import pandas as pd
    import statsmodels.formula.api as smf
    mdl = joe.MODEL_BY_ID["m2"]
    tab = joe.model_table(day_data, mdl, 0, 0, out["pairs"], days=joe.TESTED)
    keepu = joe.included_units(tab, mdl, out["pairs"])
    df = joe._frame(tab, mdl, keepu, out["pairs"])
    full = df.groupby("rat").size()
    dfb = df[df["rat"].isin(full[full == full.max()].index)]
    ols = smf.ols("value ~ C(day, Sum) * C(level, Sum) * C(unit, Sum) + C(rat)", dfb).fit()
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mix = smf.mixedlm("value ~ C(day, Sum) * C(level, Sum) * C(unit, Sum)", dfb, groups=dfb["rat"]).fit(reml=True)
    common = [k for k in mix.fe_params.index if k in ols.params.index and k != "Intercept"]
    worst = max(abs(mix.fe_params[k] - ols.params[k]) for k in common)
    check("the mixed model's fixed effects equal least squares' on balanced data (%d of them)" % len(common), worst < 1e-6, worst)
    # Hand two-way RM-ANOVA (day x level) on the per-rat means over units.
    g = dfb.groupby(["rat", "day", "level"])["value"].mean().unstack(["day", "level"])
    Y = g.values                                         # rats x 4 cells
    n = Y.shape[0]
    d1 = (Y[:, 2] + Y[:, 3] - Y[:, 0] - Y[:, 1]) / 2.0     # day effect per rat (cols: P1 base, P1 cue1, P4 base, P4 cue1)
    i1 = (Y[:, 3] - Y[:, 2]) - (Y[:, 1] - Y[:, 0])         # day x level contrast per rat
    F_int = n * i1.mean() ** 2 / (i1.var(ddof=1))
    from statsmodels.stats.anova import AnovaRM
    a2 = AnovaRM(dfb.groupby(["rat", "day", "level"], as_index=False)["value"].mean(), "value", "rat", within=["day", "level"]).fit().anova_table
    check("the RM-ANOVA's Day × Phase F is the hand-made one (a paired contrast's t²)",
          abs(float(a2.loc["day:level", "F Value"]) - F_int) < 1e-6 * max(1.0, F_int), (float(a2.loc["day:level", "F Value"]), F_int))

    print("\nThe SPSS files")
    exp = os.path.join(root, "export")
    files = joe.write_exports(out, exp)
    name = "m2_theta_welch"
    head = open(os.path.join(exp, name + ".csv"), encoding="utf-8").readline().strip().split(",")
    sps = open(os.path.join(exp, name + ".sps"), encoding="utf-8").read()
    K = r2["n_units"]
    check("one wide row a rat, a column per Day × level × pair, day first and pair fastest (SPSS's order)",
          head[0] == "rat" and len(head) == 1 + 2 * 2 * K and head[1].startswith("D1_base_") and head[1 + K].startswith("D1_cue1_")
          and head[1 + 2 * K].startswith("D4_base_"), head[:4])
    check("999 for the clipped cell", "999" in open(os.path.join(exp, "m2_theta_welch.csv"), encoding="utf-8").read()
          or "999" in open(os.path.join(exp, "m3_theta_welch.csv"), encoding="utf-8").read())
    check("the .sps declares 999 missing, runs the GLM, restructures and runs MIXED (Satterthwaite)",
          "MISSING VALUES %s TO %s (999)." % (head[1], head[-1]) in sps and "/WSFACTOR=day 2 Polynomial phase 2 Polynomial pair %d Polynomial" % K in sps
          and "VARSTOCASES /MAKE value FROM %s TO %s" % (head[1], head[-1]) in sps and "DFMETHOD(SATTERTHWAITE)" in sps
          and "/RANDOM=INTERCEPT day phase day*phase | SUBJECT(rat) COVTYPE(VC)" in sps)
    check("and every variable it names is a column of its .csv, in order",
          [l.strip().split()[0] for l in sps.split("/VARIABLES=")[1].split(".\n")[0].splitlines()[1:]] == head)
    check("a zip of them all", os.path.isfile(os.path.join(exp, "joe_tab8_spss.zip")) and len(files) == 2 * sum(1 for r in out["results"] if r.get("units")))

    print("\nThe standalone script, on the same recordings")
    inputs = {"schema": joe.SCHEMA, "regions": REGIONS, "channels": CHAN,
              "identity": {str(r): ratidentity.identity(r) for r in RATS},
              "bands": [list(b) for b in joe.BANDS], "skip_hz": list(joe.SKIP_HZ),
              "fp": {"seed": joe.FP_SEED, "lengths": list(joe.FP_LENGTHS), "edge_s": joe.FP_EDGE_S}, "min_rats": joe.MIN_RATS,
              "days": [{"rat": d["rat"], "day": d["day"], "folders": [[f["role"], f["local"]] for f in d["folders"]],
                        "bad": [], "blocked": [], "trials": [{"id": u["id"], "opener_t": u["pair"]["opener_t"],
                                                              "closer_t": u["pair"]["closer_t"], "offset_t": u["pair"]["offset_t"],
                                                              "cue_type": u["cue_type"], "manual": {}} for u in d["units"]]}
                       for d in days]}
    ip = os.path.join(root, "inputs.json")
    json.dump(inputs, open(ip, "w", encoding="utf-8"))
    so = os.path.join(root, "script")
    t0 = time.time()
    p = subprocess.run([sys.executable, os.path.join(HERE, "joe_standalone.py"), "--inputs", ip, "--out", so],
                       capture_output=True, text=True)
    print("ran in %.0f s" % (time.time() - t0))
    check("the script ran", p.returncode == 0, p.stderr[-400:])
    worst, n_cells, bad = 0.0, 0, []
    for f in sorted(x for x in os.listdir(exp) if x.endswith(".csv")):
        A = [l.strip().split(",") for l in open(os.path.join(exp, f), encoding="utf-8")]
        Bp = os.path.join(so, f)
        if not os.path.isfile(Bp):
            bad.append(f + ": missing")
            continue
        B = [l.strip().split(",") for l in open(Bp, encoding="utf-8")]
        if A[0] != B[0]:
            bad.append(f + ": columns")
            continue
        for ra, rb in zip(A[1:], B[1:]):
            for x, y in zip(ra[1:], rb[1:]):
                n_cells += 1
                if (x == "999") != (y == "999"):
                    bad.append(f + ": missing differs")
                    break
                if x != "999":
                    worst = max(worst, abs(float(x) - float(y)))
    check("its .csv files are the engine's, every cell (%d) within 1e-9" % n_cells, not bad and worst < 1e-9, (bad[:4], worst))
    notes = open(os.path.join(so, "notes.txt"), encoding="utf-8").read().strip()
    check("and it found every trial in the TTLs itself, on the same boundaries", notes == "", notes[:200])

    if "--fixture" in sys.argv:
        # The harness's tab 8 fixture: these made-up numbers, as the page reads them.
        fx = sys.argv[sys.argv.index("--fixture") + 1]
        out["exports"] = files
        for r in out["results"]:
            r.pop("table", None)
            r.pop("all_units", None)
        out.update(rats=list(RATS), n_days=len(day_data), notes=["r4 Precon1 p02: a made-up clipped stretch"],
                   histology="made up", at="2026-10-09T12:00:00",
                   agreement={"files": [{"file": f, "ok": True, "cells": 100, "worst": 0.0, "missing_differs": 0}
                                        for f in files if f.endswith(".csv")], "ok": True, "tol": 1e-6,
                              "ran_at": "2026-10-09T12:30:00"})
        joe._write(fx, out)
        print("fixture written to", fx)
    print("\n%d passed, %d failed" % (N["ok"], N["bad"]))
    if not keep:
        shutil.rmtree(root, ignore_errors=True)
    return 0 if N["bad"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
