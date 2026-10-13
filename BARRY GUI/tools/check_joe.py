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
    f2 = res[("m2", "theta", "welch")].get("follow") or {}
    check("the follow-ups run for the pair Holm keeps, with PLI, direction and PAC",
          [p["pair"] for p in f2.get("pairs", [])] == [pr01]
          and all(k in f2["pairs"][0]["measures"] for k in ("pli", "icoh", "gc_ab", "gc_ba", "xlag", "pac_ab", "pac_aa")), f2.get("basis"))
    check("no follow-ups where the gate stays shut", not res[("m3", "theta", "welch")].get("follow"))
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
    check("one zip: a README, a results summary and three folders, the main comparisons, the checks and the recreate files",
          R + "README.txt" in names and R + "Results summary.csv" in names
          and all(any(n.startswith(R + d + "/") for n in names) for d in (joe.MAIN_DIR, joe.CHECK_DIR, joe.REDO_DIR))
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
    readme = Z.read(R + "README.txt").decode("utf-8")
    check("the README: the comparisons by number, why there is no repeated-measures ANOVA, how to run one, how to recreate each result",
          all(h in readme for h in ("THE COMPARISONS", "WHY THERE IS NO REPEATED-MEASURES ANOVA", "HOW TO RUN ONE", "HOW TO RECREATE THE POSITIVE RESULTS"))
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
                              "ran_at": "2026-10-09T12:30:00"})
        joe._write(fx, out)
        print("fixture written to", fx)
    print("\n%d passed, %d failed" % (N["ok"], N["bad"]))
    if not keep:
        shutil.rmtree(root, ignore_errors=True)
    return 0 if N["bad"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
