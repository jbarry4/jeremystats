"""
check_joe.py -- tab 8 (backend/joe.py) and its standalone script
(tools/joe_standalone.py), end to end, on made-up recordings written as real
Neuralynx files.

Eight rats (the identity sheet's own, so their sounds are real), Precon1 and
Precon4, eight trials a day, six regions on one wire each, FP1 and FP2 beside
every session. Planted:

  * theta: regions 0 and 1 share 5-12 Hz activity in cue 1, on Precon4 only;
  * gamma: regions 2 and 3 share 32-88 Hz activity in the first two seconds
    of cue 2, on Precon4 only;
  * FP: regions 4 and 5 share 5-12 Hz activity in FP on Precon4 only, and
    never in the trials;
  * one clipped stretch: rat 4, Precon1, trial 2, region 0's wire at the
    rail through cue 2;
  * the sounds: nothing.

Each must be found where it was planted and nowhere else; the mixed model
is checked against the repeated-measures ANOVA on complete made-up data (the
tab runs no RM-ANOVA itself: on the real data it would keep 3 of 8 rats); the
SPSS package is read back, and its recreate files must give the tab's F
exactly; and the standalone script, run on the same folders, must give the
same values.

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
sys.stdout.reconfigure(encoding="utf-8")
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
# One FP recording whose clock breaks 6 s in for 0.6 s, as J3 Precon1's FP2
# does: every snippet after it must still be found and measured (Spark once
# looked for them by arithmetic and threw them all away).
CLOCK_BREAK = ((6, "Precon1", "FP2"), 6.0, 0.6)


def write_ncs(path, x_uv, chan, fs=FS_RAW, t0_us=T0_US, gap=None):
    head = ("######## Neuralynx Data File Header\n-FileType CSC\n-AcqEntName CSC%d\n"
            "-SamplingFrequency %.4f\n-ADBitVolts %.24f\n-ADMaxValue 32767\n") % (chan, fs, ADBV)
    raw = head.encode("latin-1")
    raw += b"\x00" * (nlx.HEADER_BYTES - len(raw))
    counts = np.clip(np.round(-x_uv / (ADBV * 1e6)), -32767, 32767).astype(np.int16)
    n = nlx.SAMPLES_PER_RECORD
    nrec = counts.size // n
    rec = np.zeros(nrec, dtype=nlx.RECORD_DTYPE)
    ts = t0_us + np.arange(nrec) * (n / fs * 1e6)
    if gap:                                              # (at s, for s): the clock jumps, as J3 Precon1's FP2 does
        ts[ts >= t0_us + gap[0] * 1e6] += gap[1] * 1e6
    rec["timestamp"] = np.round(ts).astype(np.uint64)
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


def shared(rng, n, lo, hi, sd, fs=FS_RAW):
    """Band-limited noise for two regions to share: coupling across the whole
    band, as a band's mean coherence would see it (a pure tone would touch
    two or three of its bins)."""
    from scipy.signal import butter, sosfiltfilt
    sos = butter(4, [lo / (fs / 2), hi / (fs / 2)], btype="bandpass", output="sos")
    x = sosfiltfilt(sos, rng.standard_normal(n + 2000))[1000:1000 + n]
    return x / (x.std() or 1.0) * sd


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
            s = shared(rng, int(k.sum()), 5.0, 12.0, 10.0)
            X[0][k] += s
            X[1][k] += s
            k = (t >= c) & (t < c + 2.0)                # first 2 s of cue 2: gamma, regions 2 and 3
            s = shared(rng, int(k.sum()), 32.0, 88.0, 12.0)
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
            s = shared(rng, nf, 5.0, 12.0, 10.0)
            Y[4] += s
            Y[5] += s
        gap = CLOCK_BREAK[1:] if (rat, day, role) == CLOCK_BREAK[0] else None
        for i, y in enumerate(Y):
            write_ncs(os.path.join(f, "CSC%d.ncs" % (i + 1)), y, i + 1, gap=gap)
        fps.append((role, f))
    units = [{"id": "p%02d" % (i + 1), "pair_id": i + 1, "cue_type": tr["cue_type"],
              "pair": {"pair_id": i + 1, "opener_t": tr["opener_t"], "closer_t": tr["closer_t"], "offset_t": tr["offset_t"]},
              "drop": {}, "manual": {}} for i, tr in enumerate(trials)]
    return {"rat": rat, "day": day, "gid": "fake-r%d-%s" % (rat, day), "bad": [], "blocked": {},
            "units": units, "folders": [{"role": "SPC", "local": spc}] + [{"role": r, "local": p} for r, p in fps]}


def _measure_day(d):
    """In a worker process: one made-up rat-day through the engine."""
    return joe.day_compute(d, REGIONS, CHAN)


def _fp_part(args):
    d, step = args
    return joe.fp_pool_part(d, REGIONS, CHAN, step=step)


def main():
    import pickle
    keep = "--keep" in sys.argv
    # --root <dir>: the made-up recordings and the engine's measurement of
    # them kept there, and reused if they are already there (for working on
    # the models without measuring again). Otherwise a fresh temporary one.
    given = sys.argv[sys.argv.index("--root") + 1] if "--root" in sys.argv else None
    root = given or tempfile.mkdtemp(prefix="check_joe_")
    cache = os.path.join(root, "measured.pkl")
    reuse = bool(given) and os.path.isfile(cache)
    print("made-up recordings in", root, "(reused)" if reuse else "")
    if reuse:
        with open(cache, "rb") as fh:
            days, day_data = pickle.load(fh)
    else:
        os.makedirs(root, exist_ok=True)
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
        if given:
            with open(cache, "wb") as fh:
                pickle.dump((days, day_data), fh)
    keep = keep or bool(given)
    a, fp, meta = day_data[(4, "Precon1")]
    wi = joe.WINDOWS.index("cue2")
    check("the clipped wire: region 0 not measured in that trial's cue 2, measured in its cue 1",
          np.isnan(a["power"][wi, 1, 0, 0]) and np.isfinite(a["power"][joe.WINDOWS.index("cue1"), 1, 0, 0]),
          (a["power"][wi, 1, 0, 0], a["power"][joe.WINDOWS.index("cue1"), 1, 0, 0]))
    check("seven windows, every trial, two bands, two methods", a["coh"].shape == (7, N_TRIALS, 2, 2, 15), a["coh"].shape)
    check("FP snippets: as many as the trials, 10 s and 20 s, inside FP1 and FP2 and 10 s from their ends",
          len(meta["fp"]["fp10"]) == N_TRIALS and len(meta["fp"]["fp20"]) == N_TRIALS
          and all(10.0 <= s["t0"] and s["t1"] <= FP_DUR - 10.0 for s in meta["fp"]["fp20"]), meta["fp"]["fp20"][:2])
    a6, fp6, meta6 = day_data[CLOCK_BREAK[0][:2]]
    after = [i for i, s in enumerate(meta6["fp"]["fp20"]) if s["rec"] == CLOCK_BREAK[0][2]]
    check("an FP recording whose clock breaks: every snippet after the break measured (%d of them), none lost" % len(after),
          after and not [n for n in meta6["notes"] if "snippet" in n]
          and all(np.isfinite(fp6["fp20"]["coh"][0, i]).all() for i in after),
          [n for n in meta6["notes"] if "snippet" in n][:2])
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
    f, Cxy = coherence(xb, yb, fs=1000.0, window=win, noverlap=512, nfft=2048, detrend=False)
    msk = (f >= 5 - 1e-9) & (f <= 12 + 1e-9)
    check("Dickson coherence is mscohere(x, y, hanning(1024), 512, 2048) over theta",
          abs(m["coh"][0, 1, 0] - float(Cxy[msk].mean())) < 1e-9, (m["coh"][0, 1, 0], float(Cxy[msk].mean())))
    msk = (f >= 30 - 1e-9) & (f <= 90 + 1e-9) & ~((f >= 59 - 1e-9) & (f <= 61 + 1e-9))
    check("and over gamma without the notch's own 59–61 Hz bins", abs(m["coh"][1, 1, 0] - float(Cxy[msk].mean())) < 1e-9)

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
    f2 = res[("m2", "theta", "dickson")].get("follow") or {}
    check("the follow-ups run for the pair Holm keeps, with PLI, direction and PAC",
          [p["pair"] for p in f2.get("pairs", [])] == [pr01]
          and all(k in f2["pairs"][0]["measures"] for k in joe.FOLLOW_KEYS), f2.get("basis"))
    check("no follow-ups where the gate stays shut, and none on Welch's results (the tab shows Dickson)",
          not res[("m3", "theta", "dickson")].get("follow") and not any(r.get("follow") for r in out["results"] if r["method"] == "welch"))
    r2 = res[("m2", "theta", "welch")]
    check("no RM-ANOVA run; the rats it could have kept (those with every cell) said instead",
          not any("rm" in r for r in out["results"]) and set(r2["complete_rats"]) <= set(r2["rats"]) and len(r2["complete_rats"]) in (7, 8),
          (r2.get("complete_rats"), r2.get("rats")))

    # The mixed model against the RM-ANOVA: on complete data, with a real
    # rat variance in every stratum, the two are the same test.
    import pandas as pd
    import warnings
    from statsmodels.stats.anova import AnovaRM
    for L in (2, 4):
        rg = np.random.default_rng(40 + L)
        levels = ["l%d" % i for i in range(L)]
        rows = []
        for r in range(8):
            eff = {k: rg.normal(0, 0.5, sh) for k, sh in (("d", 2), ("l", L), ("u", 6), ("dl", (2, L)), ("du", (2, 6)), ("lu", (L, 6)))}
            for di, d in enumerate(joe.TESTED):
                for li, lv in enumerate(levels):
                    for k in range(6):
                        v = (eff["d"][di] + eff["l"][li] + eff["u"][k] + eff["dl"][di, li] + eff["du"][di, k]
                             + eff["lu"][li, k] + rg.normal(0, 0.3) + (0.6 if (di == 1 and li == 1 and k == 2) else 0.0))
                        rows.append((r, d, lv, "u%d" % k, v))
        dfm = pd.DataFrame(rows, columns=["rat", "day", "level", "unit", "value"])
        mx = joe.fit_mixed(dfm, "Phase", "pair")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            at = AnovaRM(dfm, "value", "rat", within=["day", "level", "unit"]).fit().anova_table
        nm = {"day": "Day", "level": "Phase", "unit": "Pair", "day:level": "Day × Phase", "day:unit": "Day × Pair",
              "level:unit": "Phase × Pair", "day:level:unit": "Day × Phase × Pair"}
        off = {v: abs(mx["terms"][v]["F"] - float(at.loc[k, "F Value"])) / max(1.0, float(at.loc[k, "F Value"]))
               for k, v in nm.items()} if mx.get("ok") else {"fit": mx}
        check("the mixed model's seven F equal the RM-ANOVA's on complete data (%d levels), df too" % L,
              mx.get("ok") and max(off.values()) < 1e-3
              and all(mx["terms"][v]["df2"] == int(at.loc[k, "Den DF"]) for k, v in nm.items()), off)
        part = joe.fit_mixed(dfm[~((dfm["rat"] == 2) & (dfm["unit"] == "u5"))], "Phase", "pair")
        check("and a rat missing one pair keeps its others there (%d levels)" % L,
              part.get("ok") and part["n_rats"] == 8 and part["n_obs"] == 8 * 6 - 1, (part.get("n_rats"), part.get("n_obs")))
    # The check anyone can do by hand, on a positive result: each rat's mean
    # difference over its pairs, a one-sample t, against the engine's.
    from scipy.stats import ttest_1samp
    rq = res[("m2", "theta", "dickson")]
    mdl = joe.MODEL_BY_ID["m2"]
    tab = joe.model_table(day_data, mdl, 0, joe.METHODS.index("dickson"), out["pairs"], days=joe.TESTED)
    keepu = joe.included_units(tab, mdl, out["pairs"])
    per = {}
    for r in tab:
        d = [(tab[r]["Precon4"]["cue1"][u] - tab[r]["Precon4"]["base"][u]) - (tab[r]["Precon1"]["cue1"][u] - tab[r]["Precon1"]["base"][u]) for u in keepu]
        d = [x for x in d if np.isfinite(x)]
        if d:
            per[r] = float(np.mean(d))
    th = ttest_1samp(list(per.values()), 0.0)
    check("the by-hand check: each rat's mean difference, a one-sample t, is the engine's",
          rq.get("quick") and abs(rq["quick"]["t"] - float(th.statistic)) < 1e-9 and rq["quick"]["df"] == len(per) - 1,
          (rq.get("quick"), float(th.statistic)))

    print("\nThe SPSS package")
    import io
    import zipfile
    exp = os.path.join(root, "export")
    got = joe.write_exports(out, exp)
    zp = os.path.join(exp, "joe_tab8_spss.zip")
    Z = zipfile.ZipFile(zp)
    names = Z.namelist()
    R = "joe_tab8_spss/"
    check("one zip: a README, a results summary and four folders, the main comparisons, the checks, the recreate files and the follow-ups",
          R + "README.txt" in names and R + "Results summary.csv" in names
          and all(any(n.startswith(R + d + "/") for n in names) for d in (joe.MAIN_DIR, joe.CHECK_DIR, joe.REDO_DIR, joe.FOLLOW_DIR))
          and got["downloads"] == ["joe_tab8_spss.zip", "joe_tab8_README.txt", "joe_tab8_results.csv"]
          and all(os.path.isfile(os.path.join(exp, f)) for f in got["downloads"]), names[:3])
    mains = [n for n in names if n.startswith(R + joe.MAIN_DIR + "/") or n.startswith(R + joe.CHECK_DIR + "/")]
    check("each comparison named by its number and name, in both bands, as a .csv and a .sps; no Welch file, no m1, m2",
          len(mains) == 2 * 2 * len(joe.MODELS) and R + joe.MAIN_DIR + "/02 Baseline 10 s to cue 1 - theta.csv" in names
          and R + joe.CHECK_DIR + "/11 A-B-C-D - gamma.sps" in names
          and not any("welch" in n.lower() or "/m1" in n or "_m2" in n for n in names), [n for n in mains][:3])
    csv2 = Z.read(R + joe.MAIN_DIR + "/02 Baseline 10 s to cue 1 - theta.csv").decode("utf-8").splitlines()
    head2 = csv2[0].split(",")
    allu = rq["all_units"]
    n_vals = sum(1 for rr, perr in rq["table"].items() for d in joe.TESTED for lv, _l in mdl[4] for u in rq["units"]
                 if perr[d][lv][allu.index(u)] is not None)
    check("its .csv long: one row per rat, day (1 or 4), window and pair that has a value, nothing written in for a missing one",
          head2 == ["rat", "day", "phase", "pair", "coherence", "day_name", "phase_name", "pair_name"] and len(csv2) - 1 == n_vals
          and {r.split(",")[1] for r in csv2[1:]} == {"1", "4"} and "999" not in [r.split(",")[4] for r in csv2[1:]], (head2, len(csv2) - 1, n_vals))
    sps2 = Z.read(R + joe.MAIN_DIR + "/02 Baseline 10 s to cue 1 - theta.sps").decode("utf-8-sig")
    var2 = sps2.split("/VARIABLES=")[1].split(".\r\n")[0].split()
    t2 = rq["mixed"]["terms"]["Day × Phase"]
    check("its .sps: a CD line to change, the .csv read with every column in order, the full mixed model (Satterthwaite), no GLM, tab 8's F in its header",
          "CD '" in sps2 and "/FILE='02 Baseline 10 s to cue 1 - theta.csv'" in sps2 and var2[0::2] == head2
          and "MIXED coherence BY day phase pair" in sps2 and "/RANDOM=INTERCEPT day phase pair day*phase day*pair phase*pair | SUBJECT(rat) COVTYPE(VC)" in sps2
          and "DFMETHOD(SATTERTHWAITE)" in sps2 and "GLM " not in sps2 and ("F(1, %d) = %.2f" % (t2["df2"], t2["F"])) in sps2, var2[:6])
    pos = [x for x in got["positive"] if x["model"] == "m2" and x["band"] == "theta"]
    check("every result that changed has its recreate files (and nothing else does)",
          bool(pos) and all(R + f in names for x in got["positive"] for f in x["files"])
          and len([n for n in names if n.startswith(R + joe.REDO_DIR + "/")]) == 2 * len(got["positive"])
          and all(res[(x["model"], x["band"], "dickson" if joe.MODEL_BY_ID[x["model"]][5] == "pair" else "welch")]["gate"]["passed"] for x in got["positive"]),
          [(x["model"], x["band"]) for x in got["positive"]][:6])
    rc = pd.read_csv(io.BytesIO(Z.read(R + pos[0]["files"][0])))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = joe._mlm("difference ~ C(pair, Sum)", rc, rc["rat"])
    w = fit.wald_test_terms(skip_single=False, scalar=True).summary_frame()
    t3 = rq["mixed"]["terms"]["Day × Phase × Pair"]
    fi, fp_ = float(w.loc["Intercept", "chi2"]), float(w.loc["C(pair, Sum)", "chi2"]) / int(w.loc["C(pair, Sum)", "df constraint"])
    check("the recreate file, fitted as its .sps fits it (difference by pair, the rat random), gives tab 8's two F exactly",
          abs(fi - t2["F"]) < 1e-4 * max(1.0, t2["F"]) and abs(fp_ - t3["F"]) < 1e-4 * max(1.0, t3["F"]), (fi, t2["F"], fp_, t3["F"]))
    redo = Z.read(R + pos[0]["files"][1]).decode("utf-8-sig")
    check("its .sps: the exact test (MIXED difference BY pair, the rat random) and the by-hand t-test, with tab 8's numbers to expect",
          "MIXED difference BY pair" in redo and "/RANDOM=INTERCEPT | SUBJECT(rat) COVTYPE(VC)" in redo and "T-TEST /TESTVAL=0 /VARIABLES=difference." in redo
          and ("tab 8: F = %.2f" % t2["F"]) in redo and ("t(%d) = %.2f" % (rq["quick"]["df"], rq["quick"]["t"])) in redo)
    # The follow-ups: every line of the .sps's split t-test is the tab's.
    fo = [x for x in got["positive"] if x.get("follow_files")]
    fx_ = fo[0]
    frows = pd.read_csv(io.BytesIO(Z.read(R + fx_["files"][0].replace(joe.REDO_DIR, joe.FOLLOW_DIR).replace("per rat and pair", "follow-ups"))))
    fres = res[(fx_["model"], fx_["band"], "dickson")]
    worst_t, n_t = 0.0, 0
    for (pi, ki), g in frows.groupby(["pair", "measure"]):
        meas = fres["follow"]["pairs"][pi - 1]["measures"][joe.FOLLOW_KEYS[ki - 1]]
        if meas.get("t") is None:
            continue
        tt = ttest_1samp(g["difference"].to_numpy(), 0.0)
        worst_t = max(worst_t, abs(float(tt.statistic) - meas["t"]), abs(float(tt.pvalue) - meas["p"]))
        n_t += 1
    fsps = Z.read(R + fx_["follow_files"][1]).decode("utf-8-sig")
    check("the follow-ups for SPSS: a row per rat, pair and measure, and each pair and measure's t-test is the tab's to rounding (%d of them)" % n_t,
          n_t == sum(1 for pr in fres["follow"]["pairs"] for k in joe.FOLLOW_KEYS if pr["measures"][k].get("t") is not None) and worst_t < 1e-6
          and "SPLIT FILE LAYERED BY pair_name measure_name." in fsps and "T-TEST /TESTVAL=0 /VARIABLES=difference." in fsps, (n_t, worst_t))
    readme = Z.read(R + "README.txt").decode("utf-8")
    check("the README: the comparisons by number, why there is no repeated-measures ANOVA, how to run one, how to recreate each result",
          all(h in readme for h in ("THE COMPARISONS", "WHY THERE IS NO REPEATED-MEASURES ANOVA", "HOW TO RUN ONE", "HOW TO RECREATE THE POSITIVE RESULTS", "THE FOLLOW-UPS"))
          and " 2  Baseline (10 s) to cue 1" in readme and "WELCH" in readme)
    summ = Z.read(R + "Results summary.csv").decode("utf-8").splitlines()
    check("the results summary: a row a comparison and band, its words, its numbers and whether Welch agrees",
          len(summ) - 1 == 2 * len(joe.MODELS) and "Welch agrees" in summ[0] and summ[1].startswith("1,Baseline (20 s) to both cues,main,theta,"), summ[:2])

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
    cmp_dir = os.path.join(exp, "compare")
    for f in sorted(x for x in os.listdir(cmp_dir) if x.endswith(".csv")):
        A = [l.strip().split(",") for l in open(os.path.join(cmp_dir, f), encoding="utf-8")]
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

    print("\nThe figures (tab 9)")
    from backend import monolith as MO, joefigs
    MO.configure(os.path.join(root, "logs"))
    R9 = dict(out, at="made up")
    # The FP comparison's pools: fake trials in each tested rat-day's FP1
    # and FP2 (every 30 s here, to keep the check quick; tab 9 uses 10 s).
    from concurrent.futures import ProcessPoolExecutor
    tested = [d for d in days if d["day"] in joe.TESTED]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=max(1, min(6, (os.cpu_count() or 2) - 1))) as ex:
        parts = list(ex.map(_fp_part, [(d, 30.0) for d in tested]))
    for d, part in zip(tested, parts):
        joe.fp_pool_save(joe.fp_pool_path(d["rat"], d["day"]), d, REGIONS, CHAN, [part], step=30.0)
    print("FP pools made in %.0f s" % (time.time() - t0))
    figs = joefigs.build(R=R9, days=day_data, inputs=inputs)
    shown = [r for r in out["results"] if r["model"] in joefigs.WINDOWS and r["method"] == "dickson" and r["gate"].get("passed")]
    conn = [f for f in figs["figures"] if f["kind"] == "connectome"]
    check("a connectome for every result that changed (%d), nine graphs each, as SVG, PDF and 600 dpi PNG" % len(shown),
          len(conn) == len(shown) and all(len(f["stats"]["graphs"]) == 9 for f in conn)
          and all(os.path.isfile(joefigs.figs_dir(f["files"][x])) for f in figs["figures"] for x in ("svg", "pdf", "png")),
          (len(conn), len(shown)))
    # Its edges are the rats' mean changes, from tab 8's own per-rat table.
    c0 = conn[0]
    r0 = next(r for r in shown if r["model"] == c0["model"] and r["band"] == c0["band"])
    lv = [x for x, _l in joe.MODEL_BY_ID[r0["model"]][4]]
    worst = 0.0
    for d in ("Precon1", "Precon4"):
        for k, u in enumerate(c0["stats"]["pairs"]):
            ui = r0["all_units"].index(u)
            ch = [per[d][lv[1]][ui] - per[d][lv[0]][ui] for per in r0["table"].values()
                  if per[d][lv[1]][ui] is not None and per[d][lv[0]][ui] is not None]
            e = c0["stats"]["edges"][d][k]
            worst = max(worst, abs(float(np.mean(ch)) - e) if ch and e is not None else 0.0)
    check("its edges are the rats' mean changes from tab 8's own per-rat values", worst < 1e-9, worst)
    alt = lambda f, k: next(a for a in f.get("alts") or [] if a["null"] == k)      # noqa: E731
    nets = [g for f in conn for g in alt(f, "trials")["stats"]["graphs"] if g["kind"] == "net"]
    check("the within-session shuffles of the sums are centred on nothing",
          all(abs(g["null"]["mean"]) < 0.1 * g["null"]["sd"] for g in nets), [(round(g["null"]["mean"], 4), round(g["null"]["sd"], 4)) for g in nets][:4])
    cm2 = next((f for f in conn if f["model"] == "m2" and f["band"] == "theta"), None)
    g2 = cm2 and next(g for g in alt(cm2, "trials")["stats"]["graphs"] if g["row"] == "delta" and g["kind"] == "pos")
    check("the planted theta change in cue 1 stands out of its shuffles (Precon4 − Precon1, increases)",
          bool(g2) and g2["p"] < 0.05 and g2["stars"], g2 and (g2["p"], g2["rank"]))

    # The main test (2026-10-22): the rats' signs flipped every way, the rat
    # the unit as in the mixed model behind tab 8's light; the trials'
    # shuffle is the alternative, a toggle away.
    n_r = len(c0["stats"]["rats"])
    check("the rings' main test is the rats' sign flips, all 2^%d = %d of them; the trials' shuffle the alternative, in its own files"
          % (n_r, 2 ** n_r),
          all(f["null"] == "rats" and f["stats"]["rat_exact"] and f["stats"]["n_signs"] == 2 ** n_r
              and all(g["null_kind"] == "rats" and g["n"] == 2 ** n_r for g in f["stats"]["graphs"])
              and alt(f, "trials")["null"] == "trials" and len(alt(f, "trials")["stats"]["graphs"]) == 9
              and all(g["null_kind"] == "trials" and g["n"] == joefigs.N_PERM + 1 for g in alt(f, "trials")["stats"]["graphs"])
              and alt(f, "trials")["files"]["svg"] != f["files"]["svg"]
              and all(os.path.isfile(joefigs.figs_dir(alt(f, "trials")["files"][x])) for x in ("svg", "pdf", "png"))
              and "ratflip" in f["methods"] and "permutation" in alt(f, "trials")["methods"] for f in conn), [f["null"] for f in conn])
    # Every one by hand, from tab 8's own per-rat table: each rat's change,
    # its sign flipped all 2^n ways, the rats' mean per pair, the ring's sum.
    import itertools
    lv0 = [x for x, _l in joe.MODEL_BY_ID[r0["model"]][4]]
    ui0 = [r0["all_units"].index(u) for u in c0["stats"]["pairs"]]
    def per_rat_change(per, d):
        return [np.nan if per[d][lv0[1]][i] is None or per[d][lv0[0]][i] is None else per[d][lv0[1]][i] - per[d][lv0[0]][i] for i in ui0]
    X = {"Precon1": [], "Precon4": []}
    for rat in c0["stats"]["rats"]:
        per = r0["table"].get(str(rat)) or r0["table"].get(rat)
        for d in X:
            X[d].append(per_rat_change(per, d) if per else [np.nan] * len(ui0))
    X = {d: np.array(v, float) for d, v in X.items()}
    X["delta"] = X["Precon4"] - X["Precon1"]
    signs = np.array(list(itertools.product((1.0, -1.0), repeat=n_r)))
    worst = 0.0
    for g in c0["stats"]["graphs"]:
        with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
            __import__("warnings").simplefilter("ignore", RuntimeWarning)
            m = np.nanmean(signs[:, :, None] * X[g["row"]][None], axis=1)
        m = np.where(np.isfinite(m), m, 0.0)
        tot = {"pos": np.clip(m, 0, None).sum(1), "neg": np.clip(m, None, 0).sum(1), "net": m.sum(1)}[g["kind"]]
        o = tot[0]
        k = {"up": (tot >= o - 1e-12).sum(), "down": (tot <= o + 1e-12).sum(), "two": (np.abs(tot) >= abs(o) - 1e-12).sum()}[g["side"]]
        worst = max(worst, abs(k / len(tot) - g["p"]), abs(o - g["stat"]))
    check("its P, every one of the nine, is the share of all 2^%d sign patterns of tab 8's own per-rat changes at least as extreme" % n_r,
          worst < 1e-9, worst)
    rg = [g for f in conn for g in f["stats"]["graphs"]]
    check("P in steps of 1/%d: never under 1/%d one-sided nor 2/%d for both (flipping every rat is the mirror image)" % ((2 ** n_r,) * 3),
          all(abs(g["p"] * 2 ** n_r - round(g["p"] * 2 ** n_r)) < 1e-9 for g in rg)
          and all(g["p"] >= (2 if g["side"] == "two" else 1) / 2 ** n_r - 1e-12 for g in rg), min(g["p"] for g in rg))
    gr2 = cm2 and next(g for g in cm2["stats"]["graphs"] if g["row"] == "delta" and g["kind"] == "pos")
    check("the planted theta change stands out of the rats' flips too (Precon4 − Precon1, increases)",
          bool(gr2) and gr2["p"] < 0.05 and gr2["stars"], gr2 and (gr2["p"], gr2["rank"]))
    lg0, la0 = c0["legend"]["body"], alt(c0, "trials")["legend"]["body"]
    check("each test's legend says its own: the rats' with 1/%d one-sided and 2/%d for both; the trials' its %s shuffles"
          % (2 ** n_r, 2 ** n_r, format(joefigs.N_PERM, ",")),
          ("smallest possible is 1/%d for the increases or the decreases and 2/%d for both" % (2 ** n_r, 2 ** n_r)) in lg0
          and "sign patterns" in lg0 and "shuffles" in la0 and format(joefigs.N_PERM, ",") in la0 and "sign patterns" not in la0,
          (lg0[:120], la0[:120]))
    fol = [f for f in figs["figures"] if f["kind"] == "follow"]
    worst = 0.0
    for f in fol:
        res9 = next(r for r in out["results"] if r["model"] == f["model"] and r["band"] == f["band"] and r["method"] == "dickson")
        pr = next(x for x in res9["follow"]["pairs"] if x["pair"] == f["pair"])
        for k in f["keys"]:
            worst = max(worst, abs(f["stats"]["nulls"][k]["obs"] - pr["measures"][k]["delta"]))
    check("a figure per follow-up that changed (%d), its shuffles' real value the tab's own change" % len(fol), bool(fol) and worst < 1e-9, worst)
    pacf = [f for f in fol if any(k.startswith("pac_") for k in f["keys"])]
    check("PAC: the roses and the comodulogram read from the recordings, through tab 8's wires (made-up recordings here)",
          figs["recordings_read"] and (not pacf or all(f["pac_profiles"] and not f["pac_missing"] for f in pacf)), [f["id"] for f in pacf])
    svg0 = open(joefigs.figs_dir(c0["files"]["svg"]), encoding="utf-8").read(4000)
    import re as _re
    wpt = float(_re.search(r'width="([0-9.]+)pt"', svg0).group(1))
    check("Nature's format: 183 mm wide, Arial, text kept as text", abs(wpt - 183 / 25.4 * 72) < 0.5 and "Arial" in open(joefigs.figs_dir(c0["files"]["svg"]), encoding="utf-8").read(),
          wpt)
    check("PAC: every trial's MI read for the roses is tab 8's own (%s trials and windows)" % (figs["pac_check"] or {}).get("compared"),
          bool(figs["pac_check"]) and figs["pac_check"]["ok"] and figs["recordings_where"] == "here", figs["pac_check"])

    print("\nThe FP comparison (tab 9's third test)")
    pools = joe.fp_pools()
    pa, pm = pools[(tested[0]["rat"], tested[0]["day"])]
    ons = joe.fp_onsets(tested[0], 30.0)
    w7 = joe.fake_windows(ons[0][2])
    check("the pool: a fake cue every 30 s of FP1 and FP2, a trial's seven windows round it, every measure, every tested rat-day",
          len(pools) == len(tested) and pa["coh"].shape[:2] == (7, len(ons)) and len(pm["onsets"]) == len(ons)
          and [w[0] for w in w7] == list(joe.WINDOWS) and w7[0][1] == ons[0][2] - 20 and w7[4][2] == ons[0][2] + 20
          and all(k in pa for k in ("coh", "pac") + joe.FOLLOW)
          and np.isfinite(pa["coh"][joe.WINDOWS.index("pair"), :, 0, 1, :]).mean() > 0.9,
          (len(pools), pa["coh"].shape, len(ons)))
    # By hand: one FP null, drawn the same way, from the same seed.
    res_c0 = next(r for r in shown if r["model"] == c0["model"] and r["band"] == c0["band"])
    bi, mi = [x for x, _l, _h in joe.BANDS].index(res_c0["band"]), joe.METHODS.index("dickson")
    keep0 = [R9["pairs"].index(u) for u in res_c0["units"]]
    wa, wb = joefigs.WINDOWS[c0["model"]]
    get = lambda pool, w: pool["coh"][joe.WINDOWS.index(w), :, bi, mi, :][:, keep0]     # noqa: E731
    rats9 = sorted({r for r, d in day_data if d in joe.TESTED})
    fpr = joefigs.fp_per_rat(pools, day_data, rats9, get, wa, wb, seed=11, n=7)
    rng = np.random.default_rng(11)
    worst = 0.0
    for day in joe.TESTED:
        for ri, r in enumerate(rats9):
            a_, _m = pools[(r, day)]
            bs, cs = get(a_, wa).astype(np.float32), get(a_, wb).astype(np.float32)
            real = day_data[(r, day)][0]
            oka, okb = np.isfinite(get(real, wa)), np.isfinite(get(real, wb))
            T = oka.shape[0]
            idx = rng.integers(0, bs.shape[0], size=(7, T))
            flip = rng.random((7, T)) < 0.5
            for k in range(7):
                sec = np.array([np.where(okb[t], bs[i] if fl else cs[i], np.nan) for t, (i, fl) in enumerate(zip(idx[k], flip[k]))])
                fst = np.array([np.where(oka[t], cs[i] if fl else bs[i], np.nan) for t, (i, fl) in enumerate(zip(idx[k], flip[k]))])
                want_ = np.nanmean(sec, axis=0) - np.nanmean(fst, axis=0)
                worst = max(worst, float(np.nanmax(np.abs(want_ - fpr[day][ri, k]))))
    check("one FP null set by hand: each session as many fake trials as it had real ones, drawn with replacement, each in random order, losing the windows its real trial lost",
          worst < 1e-6, worst)
    fps = [alt(f, "fp") for f in conn]
    check("on every ring as a third test, with its own figure files and legend",
          all(len(a["stats"]["graphs"]) == 9 and all(g["null_kind"] == "fp" and g["n"] == joefigs.N_PERM + 1 for g in a["stats"]["graphs"])
              and all(os.path.isfile(joefigs.figs_dir(a["files"][x])) for x in ("svg", "pdf", "png")) and "fpnull" in a["methods"]
              and "FP1 and FP2" in a["legend"]["body"] for a in fps) and figs["fp"]["read"] and figs["fp"]["rat_days"] == len(tested),
          figs["fp"])
    fnet = [g for a in fps for g in a["stats"]["graphs"] if g["kind"] == "net"]
    check("FP's sets of a ring's change sit round nothing (no cues, no change)",
          all(abs(g["null"]["mean"]) < 0.25 * g["null"]["sd"] for g in fnet if g["row"] == "delta"),
          [(round(g["null"]["mean"], 4), round(g["null"]["sd"], 4)) for g in fnet if g["row"] == "delta"][:4])
    gf2 = cm2 and next(g for g in alt(cm2, "fp")["stats"]["graphs"] if g["row"] == "delta" and g["kind"] == "pos")
    check("the planted theta change in cue 1 stands out of FP too", bool(gf2) and gf2["p"] < 0.05, gf2 and (gf2["p"], gf2["rank"]))
    worst = 0.0
    for f in fol:
        for k in f["keys"]:
            worst = max(worst, abs(f["stats"]["nulls_fp"][k]["obs"] - f["stats"]["nulls"][k]["obs"]))
    check("every follow-up has FP beside its shuffles, from the same observed change, in its legend and its methods",
          all(set(f["stats"]["nulls_fp"]) == set(f["keys"]) and "fpnull" in f["methods"] and "FP1 and FP2" in f["legend"]["body"]
              for f in fol) and worst < 1e-12, worst)

    print("\nOn the VACC (its entry point, run here on these recordings)")
    import copy
    import shlex
    items9 = joefigs.follow_items(R9)
    # The manifest names each folder's copy on the cluster; here the "copy"
    # is the folder itself, so the cluster's entry point can run on it.
    sizes = lambda f: {n: os.path.getsize(os.path.join(f, n)) for n in os.listdir(f)}          # noqa: E731
    man_days = [{"folders": [{"local": f["local"], "remote": {"scratch": f["local"]}, "files": sizes(f["local"])}
                             for f in d["folders"]]} for d in days]
    real_manifest = MO.manifest
    MO.manifest = lambda: {"days": man_days}
    try:
        spec = joefigs.pac_spec(R9, day_data, inputs, items9)
    finally:
        MO.manifest = real_manifest
    tested = sorted((d["rat"], d["day"]) for d in days if d["day"] in joe.TESTED)
    check("the spec: every tested rat-day's copy, its trials and wires, and its .ncs/.nev sizes; only the PAC follow-ups",
          sorted((d["rat"], d["day"]) for d in spec["days"]) == tested and not spec["missing"]
          and all(spec["sizes"][d["folders"][0][1]] and all(n.endswith((".ncs", ".nev")) for n in spec["sizes"][d["folders"][0][1]])
                  for d in spec["inputs"]["days"])
          and all(k.startswith("pac_") for it in spec["items"] for k in it["keys"]) and spec["items"],
          (len(spec["days"]), spec["missing"][:2]))
    sp, so9 = os.path.join(root, "pac_spec.json"), os.path.join(root, "pac_result.json")
    json.dump(spec, open(sp, "w", encoding="utf-8"))
    p9 = subprocess.run([sys.executable, "-m", "backend.joefigs", "pac", sp, so9], cwd=APP, capture_output=True, text=True)
    got9 = json.load(open(so9, encoding="utf-8")) if p9.returncode == 0 else {}
    here9, _n9 = joefigs.pac_profiles(R9, day_data, inputs, items9)
    worst = max((abs(np.asarray(here9[k]["per_rat"][r][d][w]["profile"]) - np.asarray(v["per_rat"][r][d][w]["profile"])).max()
                 for k, v in (got9.get("profiles") or {}).items() for r in v["per_rat"] for d in v["per_rat"][r]
                 for w in v["per_rat"][r][d]), default=None)
    check("the cluster's entry point (python -m backend.joefigs pac): the same profiles as reading here, every rat-day read",
          p9.returncode == 0 and sorted(got9["profiles"]) == sorted(here9) and worst is not None and worst < 1e-12
          and len(got9["rat_days"]) == len(tested) and not got9["notes"] and got9["key"] == spec["key"],
          (p9.stderr[-300:], worst))
    bad = copy.deepcopy(spec)
    f0 = bad["inputs"]["days"][0]["folders"][0][1]
    n0 = sorted(x for x in bad["sizes"][f0] if x.endswith(".ncs"))[0]
    bad["sizes"][f0][n0] += 1
    json.dump(bad, open(sp, "w", encoding="utf-8"))
    p9b = subprocess.run([sys.executable, "-m", "backend.joefigs", "pac", sp, so9], cwd=APP, capture_output=True, text=True)
    gb = json.load(open(so9, encoding="utf-8")) if p9b.returncode == 0 else {}
    d0 = bad["inputs"]["days"][0]
    check("a copy whose size is not the recording tab 8 read: that rat-day is said and left out, the others read",
          p9b.returncode == 0 and len(gb["rat_days"]) == len(tested) - 1 and "r%d %s" % (d0["rat"], d0["day"]) not in gb["rat_days"]
          and any(n.startswith("r%d %s: the cluster's copy is not the recording tab 8 read (%s" % (d0["rat"], d0["day"], n0)) for n in gb["notes"]),
          gb.get("notes", [])[:2])
    # Drawn where the recordings are not: the VACC's reading of this very tab 8 is used, and one of another is not.
    gone = dict(inputs, days=[dict(d, folders=[[r, f + "_not_here"] for r, f in d["folders"]]) for d in inputs["days"]])
    joe._write(joe.joe_dir(joefigs.PAC_VACC), dict(got9, at="2026-10-22T11:38:10", slurm_id="5979834",
                                                   where="/users/s/a/sakhava1/jarvis/joefigs/made-up"))
    figs2 = joefigs.build(R=R9, days=day_data, inputs=gone)
    pac2 = [f for f in figs2["figures"] if any(k.startswith("pac_") for k in f.get("keys") or [])]
    check("drawn without the recordings: the VACC's reading of this tab 8, every PAC figure with its roses, every trial tab 8's own",
          figs2["recordings_where"] == "vacc" and figs2["pac_check"]["ok"] and figs2["vacc_run"]["slurm_id"] == "5979834"
          and pac2 and all(f["pac_profiles"] and not f["pac_missing"] for f in pac2), (figs2["recordings_where"], figs2["pac_check"]))
    joe._write(joe.joe_dir(joefigs.PAC_VACC), dict(got9, key="0" * 16))
    figs3 = joefigs.build(R=R9, days=day_data, inputs=gone)
    check("a reading made from another tab 8 is not used: no roses, and the figures say so",
          not figs3["recordings_read"] and all(f["pac_missing"] for f in figs3["figures"] if any(k.startswith("pac_") for k in f.get("keys") or [])),
          figs3["recordings_where"])
    os.remove(joe.joe_dir(joefigs.PAC_VACC))

    # The size check: what find answers, parsed; the folders go as data on stdin, never on the command line.
    from backend import vacc as V
    seen = {}
    def fake_ssh(cfg, cmd, stdin=None, timeout=45):
        seen.update(cmd=cmd, stdin=stdin)
        return "10\t/gpfs/x/J3 Precon 1/a b/CSC1.ncs\n5\t/gpfs/x/J3 Precon 1/a b/Events.nev\n8\t/gpfs/x/J3 Precon 1/a b/CSC2.ncs\n"
    real_ssh = V._ssh
    V._ssh = fake_ssh
    try:
        sb = joe.vacc_sizes({}, {"/gpfs/x/J3 Precon 1/a b": {"CSC1.ncs": 10, "Events.nev": 5, "CSC2.ncs": 7, "CSC3.ncs": 4}})
    finally:
        V._ssh = real_ssh
    check("the copies' sizes from one find: a file of another size and a missing one said; the folder sent only as data",
          sb == ["/gpfs/x/J3 Precon 1/a b/CSC2.ncs is 8 bytes, not 7 bytes", "/gpfs/x/J3 Precon 1/a b/CSC3.ncs is missing, not 4 bytes"]
          and seen["cmd"] == "bash -s" and "J3 Precon 1" in seen["stdin"], sb)

    # Tab 8's script on the VACC: the job stood in for by a run here, the rest as it is.
    so_here = joe.joe_dir("script")
    jd = joe.joe_dir()
    os.makedirs(jd, exist_ok=True)
    json.dump(inputs, open(joe.joe_dir("joe_inputs.json"), "w", encoding="utf-8"))
    shutil.copytree(cmp_dir, joe.joe_dir("export", "compare"), dirs_exist_ok=True)
    runs = {}
    def fake_job(files, command, cpus=4, mem="8G", wall="01:00:00", progress=None, check=None, kind="joe"):
        ws = tempfile.mkdtemp(dir=root, prefix="vacc_ws_")
        for name, data in files.items():
            with open(os.path.join(ws, name), "wb") as fh:
                fh.write(data)
        argv = shlex.split(command)
        argv = argv[1:] if argv[0] == "exec" else argv
        argv[0] = sys.executable
        pj = subprocess.run(argv, cwd=ws, capture_output=True, text=True)
        open(os.path.join(ws, "job_1.out"), "w", encoding="utf-8").write(pj.stdout + pj.stderr)
        runs.update(files=files, command=command, cpus=cpus, mem=mem, kind=kind, rc=pj.returncode)
        if pj.returncode:
            raise joe.JoeError("the job failed: " + pj.stderr[-300:], 502)
        return {}, ws, "1"
    class Wk:
        def note(self, **kw):
            pass
        def check(self):
            pass
    stand = {k: getattr(joe, k) for k in ("vacc_copies", "vacc_config", "vacc_sizes", "vacc_job", "vacc_tree", "vacc_text")}
    copies = lambda: {joe._norm(f["local"]): (f["local"], sizes(f["local"])) for d in days for f in d["folders"]}     # noqa: E731
    joe.vacc_copies = copies
    joe.vacc_config = lambda: {}
    joe.vacc_sizes = lambda cfg, want: []
    joe.vacc_job = fake_job
    joe.vacc_tree = lambda cfg, ws, name, dest, timeout=600: shutil.copytree(os.path.join(ws, name), dest, dirs_exist_ok=True)
    joe.vacc_text = lambda cfg, ws, name, timeout=120: open(os.path.join(ws, name), encoding="utf-8").read()
    try:
        ag = joe.script_vacc_work(Wk())
        sent = json.loads(runs["files"]["joe_inputs.json"])
        check("tab 8's script on the VACC: sent with its inputs (every tested folder its copy), run as one job, compared as a run here is",
              ag["ok"] and ag["where"] == "vacc" and ag["slurm_id"] == "1" and runs["kind"] == "joescript"
              and "--jobs %d" % runs["cpus"] in runs["command"] and "joe_standalone.py" in runs["files"]
              and sorted((d["rat"], d["day"]) for d in sent["days"]) == tested
              and all(len(d["folders"]) == 3 for d in sent["days"]), (ag.get("where"), runs.get("command")))
        before = sorted(os.listdir(so_here))
        joe.vacc_copies = lambda: {}
        try:
            joe.script_vacc_work(Wk())
            r1 = None
        except joe.JoeError as exc:
            r1 = str(exc)
        joe.vacc_copies = copies
        joe.vacc_sizes = lambda cfg, want: ["/gpfs/x/a/CSC1.ncs is 1 bytes, not 2 bytes"]
        try:
            joe.script_vacc_work(Wk())
            r2 = None
        except joe.JoeError as exc:
            r2 = str(exc)
        check("refused, and the last comparison kept, when a folder has no copy there or a copy differs from what tab 8 read",
              r1 and "no copy on the VACC" in r1 and r2 and "differ from the recordings tab 8 read" in r2
              and sorted(os.listdir(so_here)) == before, (r1, r2))
    finally:
        for k, v in stand.items():
            setattr(joe, k, v)

    # vacc_job against a stand-in cluster: only a Stop (or a submit gone
    # wrong) cancels; a login node that does not answer is waited out, and
    # past the limit let go of without cancelling (the review of 10-22).
    from backend import vaccrun as VR
    calls = []
    was = {"ssh": V._ssh, "poll": V.poll_states, "cancel": V.cancel, "cfg": joe.vacc_config, "poll_s": joe.VACC_POLL_S,
            "sleep": VR.SLEEP, "clock": VR.CLOCK, "grace": V.LAG_GRACE_S}
    def run_job(polls, submit_ok=True, stop_at=None, ws="/users/x/jarvis"):
        calls.clear()
        seq = list(polls)
        def ssh(cfg, cmd, stdin=None, timeout=45):
            calls.append(("ssh", cmd.split(" ")[0]))
            if "sbatch" in cmd:
                if not submit_ok:
                    raise V.SSHError("The cluster did not answer within 300s.", "timeout")
                return "4242\n"
            return ""
        def poll(cfg, ids, timeout=30, ssh=None):
            calls.append(("poll",))
            x = seq.pop(0) if seq else {"state": "COMPLETED"}
            if isinstance(x, Exception):
                raise x
            return {"4242": x} if x else {}
        def cancel(cfg, slurm_id=None, rid=None, timeout=25, ssh=None):
            calls.append(("cancel", slurm_id, bool(rid)))
        n_check = [0]
        def chk():
            n_check[0] += 1
            if stop_at and n_check[0] >= stop_at:
                raise RuntimeError("Stopped.")
        V._ssh, V.poll_states, V.cancel = ssh, poll, cancel
        joe.vacc_config = lambda: {"workspace": ws, "partition": "general", "modules": []}
        joe.VACC_POLL_S = 0
        VR.SLEEP = lambda s_: None
        try:
            return joe.vacc_job({"a.txt": b"x"}, "exec true", kind="checkjob", check=chk), None
        except Exception as exc:                         # noqa: BLE001
            return None, exc
    fail = V.SSHError("The cluster did not answer within 30s.", "timeout")
    try:
        gj, err = run_job([fail, fail, {"state": "RUNNING"}, {"state": "COMPLETED"}])
        r1 = (err is None and gj[2] == "4242" and not any(c[0] == "cancel" for c in calls) and not joe.vacc_runs().get("checkjob"))
        gj, err = run_job([{"state": "RUNNING"}, {"state": "RUNNING"}], stop_at=3)
        r2 = (err is not None and ("cancel", "4242", True) in calls and not joe.vacc_runs().get("checkjob"))
        gj, err = run_job([], submit_ok=False)
        r3 = (err is not None and any(c[0] == "cancel" and c[2] for c in calls) and not joe.vacc_runs().get("checkjob"))
        t_ = [0.0]
        VR.CLOCK = lambda: t_.__setitem__(0, t_[0] + 400.0) or t_[0]
        gj, err = run_job([fail] * 50)
        r4 = (isinstance(err, joe.JoeError) and "nothing was cancelled" in str(err) and "4242" in str(err)
              and not any(c[0] == "cancel" for c in calls) and joe.vacc_runs().get("checkjob", {}).get("slurm_id") == "4242")
        VR.CLOCK = was["clock"]
        gj, err = run_job([{"state": "RUNNING"}])
        r5 = err is None and ("cancel", "4242", True) in calls[:3]       # the one left behind, cancelled first
        V.LAG_GRACE_S = 0.0
        gj, err = run_job([{}] * 500)
        r6 = err is None and gj[2] == "4242" and sum(c[0] == "poll" for c in calls) < 100
        V.LAG_GRACE_S = was["grace"]
        gj, err = run_job([], ws="/users/x/my jarvis")
        r7 = isinstance(err, joe.JoeError) and "not a plain absolute path" in str(err) and not any(c[0] == "ssh" for c in calls)
    finally:
        V._ssh, V.poll_states, V.cancel, joe.vacc_config = was["ssh"], was["poll"], was["cancel"], was["cfg"]
        joe.VACC_POLL_S, VR.SLEEP, VR.CLOCK, V.LAG_GRACE_S = was["poll_s"], was["sleep"], was["clock"], was["grace"]
        joe.vacc_runs(drop=["checkjob"])
    check("a VACC job waits out a login node that does not answer, and finishes without cancelling anything", r1, calls)
    check("a Stop cancels it (by its id and its name), and nothing is left on the record", r2)
    check("a submit whose answer was lost cancels by the job's name", r3)
    check("past half an hour of no answer it lets go, says the job and where, and cancels nothing; the record keeps it", r4)
    check("the next job of that kind cancels the one left behind first", r5)
    check("a job in neither squeue nor sacct past the grace is taken as finished (its answer then decides)", r6)
    check("a workspace with a space (sbatch would cut it) is refused before anything is sent", r7)

    if "--figs-fixture" in sys.argv:
        # The page's fixture: the figures as drawn from the VACC's reading.
        joe._write(sys.argv[sys.argv.index("--figs-fixture") + 1], figs2)
        print("tab 9 fixture written")

    if "--fixture" in sys.argv:
        # The harness's tab 8 fixture: these made-up numbers, as the page reads them.
        fx = sys.argv[sys.argv.index("--fixture") + 1]
        out["exports"] = got["downloads"]
        out["spss"] = got
        for r in out["results"]:
            r.pop("table", None)
            r.pop("all_units", None)
        out.update(rats=list(RATS), n_days=len(day_data), notes=["r4 Precon1 p02: a made-up clipped stretch"],
                   histology="made up", at="2026-10-09T12:00:00",
                   agreement={"files": [{"file": f, "ok": True, "cells": 100, "worst": 0.0, "missing_differs": 0}
                                        for f in sorted(os.listdir(cmp_dir))], "ok": True, "tol": 1e-6,
                              "ran_at": "2026-10-09T12:30:00", "where": "vacc", "slurm_id": "5979928"})
        joe._write(fx, out)
        print("fixture written to", fx)
    print("\n%d passed, %d failed" % (N["ok"], N["bad"]))
    if not keep:
        shutil.rmtree(root, ignore_errors=True)
    return 0 if N["bad"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
