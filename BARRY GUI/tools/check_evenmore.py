"""check_evenmore.py -- tab 11, Narrowing down (even more): its arithmetic
against independent code, and its saved result against itself.

    python tools/check_evenmore.py

Part 1 needs nothing: made-up signals and rows. Part 2 reads this
machine's evenmore.json (GUI_logs/.cache/monolith/evenmore) when there is
one; it computes nothing new and writes nothing.
"""
import csv
import io
import json
import os
import sys
import zipfile

import numpy as np

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
from backend import monolith as MO                     # noqa: E402

MO.configure(os.path.join(APP, "GUI_logs"))
from backend import coupling, joe, evenmore as E       # noqa: E402

ok = bad = 0


def check(name, cond, detail=None):
    global ok, bad
    if cond:
        ok += 1
        print("  ok    " + name)
    else:
        bad += 1
        print("  FAIL  " + name + ("   " + repr(detail)[:300] if detail is not None else ""))


print("The arithmetic")
rng = np.random.default_rng(11)
fs = E.FS
t = np.arange(int(20 * fs)) / fs
common = np.sin(2 * np.pi * 7.0 * t)
trials = []
for k in range(3):
    ph = rng.uniform(0, 2 * np.pi)
    a = common + 0.8 * rng.standard_normal(t.size)
    b = np.sin(2 * np.pi * 7.0 * t + ph) + 0.8 * rng.standard_normal(t.size)          # a lag that wanders trial to trial
    trials.append((a, b))
# one trial: the pooled spectra are scipy's coherence with mscohere's settings
from scipy.signal import coherence as sc_coh, csd, welch    # noqa: E402
a, b = trials[0]
Fa, Fb = E._spectra_of([a, b])
mine = np.abs((Fa * np.conj(Fb)).sum(0)) ** 2 / ((np.abs(Fa) ** 2).sum(0) * (np.abs(Fb) ** 2).sum(0))
win = coupling.matlab_hanning(E.SEG)
_f, ref = sc_coh(joe.dickson_notch(a), joe.dickson_notch(b), fs=fs, window=win, nperseg=E.SEG, noverlap=E.STEP, nfft=E.NFFT, detrend=False)
check("one trial: pooled coherence is scipy's (mscohere's hanning(1024), 512, 2048)", np.allclose(mine, ref[:E.NF], atol=1e-10),
      float(np.max(np.abs(mine - ref[:E.NF]))))
# several trials: every segment of every trial in one cross-spectrum
num = np.zeros(E.NF, complex)
da = np.zeros(E.NF)
db = np.zeros(E.NF)
per = []
for a, b in trials:
    xa, xb = joe.dickson_notch(a), joe.dickson_notch(b)
    _f, pab = csd(xa, xb, fs=fs, window=win, nperseg=E.SEG, noverlap=E.STEP, nfft=E.NFFT, detrend=False)
    _f, paa = welch(xa, fs=fs, window=win, nperseg=E.SEG, noverlap=E.STEP, nfft=E.NFFT, detrend=False)
    _f, pbb = welch(xb, fs=fs, window=win, nperseg=E.SEG, noverlap=E.STEP, nfft=E.NFFT, detrend=False)
    num += pab[:E.NF]
    da += paa[:E.NF]
    db += pbb[:E.NF]
    per.append(np.abs(pab[:E.NF]) ** 2 / (paa[:E.NF] * pbb[:E.NF]))
ref_pool = np.abs(num) ** 2 / (da * db)
sab = sum((x * np.conj(y)).sum(0) for x, y in (E._spectra_of([a, b]) for a, b in trials))
saa = sum((np.abs(x) ** 2).sum(0) for x, _y in (E._spectra_of([a, b]) for a, b in trials))
sbb = sum((np.abs(y) ** 2).sum(0) for _x, y in (E._spectra_of([a, b]) for a, b in trials))
pooled = np.abs(sab) ** 2 / (saa * sbb)
check("three trials: pooled is the coherence of the summed cross- and auto-spectra", np.allclose(pooled, ref_pool, rtol=1e-9))
m7 = np.argmin(np.abs(E.FREQS - 7.0))
check("a lag that wanders between trials: pooled below the mean of trials at 7 Hz (%.2f < %.2f)" % (pooled[m7], np.mean([p[m7] for p in per])),
      pooled[m7] < np.mean([p[m7] for p in per]))
# the bins
gb = E.bins_of("gamma")
check("gamma: 2 Hz bins from 30 to 90 Hz, none holding 59-61 Hz",
      len(gb) == 30 and not any(m[(E.FREQS > 59.0) & (E.FREQS < 61.0)].any() for _f, m in gb) and gb[0][0] == 31.0)
tb = E.bins_of("theta")
check("theta: the FFT's own 0.49 Hz bins, 5 to 12 Hz (%d)" % len(tb),
      all(5.0 <= f <= 12.0 for f, _m in tb) and np.allclose(np.diff([f for f, _m in tb]), fs / E.NFFT))
# the wire pairs: each region pair's four, never homotopic
wp = E.wire_pairs()
check("forty wire pairs, four a region pair, no region paired with itself", len(wp) == 40
      and all(a.split(" ", 1)[1] != b.split(" ", 1)[1] for _p, _c, a, b in wp))
check("the plan's ten pairs, in its order", list(E.PAIR_SAY) == ["RSC–dHC", "RSC–ACC", "RSC–OFC", "RSC–PER", "dHC–ACC", "dHC–OFC",
                                                               "dHC–PER", "ACC–OFC", "ACC–PER", "OFC–PER"])
day = {"sab": np.ones((3, 10, 4, E.NF), complex), "saa": np.ones((3, 10, 4, E.NF)), "sbb": np.ones((3, 10, 4, E.NF)),
       "nseg": np.ones((3, 10, 4), np.int32)}
day["sab"][0, 0, 0] *= np.sqrt(0.5)                    # coherence 0.5 on one wire pair, 1 on another, two never valid
day["nseg"][0, 0, 2:] = 0
check("a region pair is the mean of its valid wire pairs, each counting the same",
      np.allclose(E.rat_spectrum(day, "pair")[0], 0.75))
# Benjamini-Hochberg against statsmodels
from statsmodels.stats.multitest import multipletests  # noqa: E402
ps = [0.001, 0.2, 0.03, None, 0.04, 0.5]
got = E.bh(ps)
ref = multipletests([p for p in ps if p is not None], method="fdr_bh")[1]
check("FDR is Benjamini-Hochberg (statsmodels' fdr_bh), None passed through",
      got[3] is None and np.allclose([g for g in got if g is not None], ref))
# the GEE: a one-df test is the robust bias-reduced Wald, a planted change found
import pandas as pd                                    # noqa: E402
rows = []
for r in range(8):
    u = rng.normal(0, 0.3)
    for d in E.DAYS:
        for p in range(3):
            eff = 0.5 if (d == "Precon4" and p == 0) else 0.0
            rows.append({"rat": r, "day": d, "pair": "p%02d" % p, "y": float(np.exp(-2 + u + eff + rng.normal(0, 0.1)))})
df = pd.DataFrame(rows)
res = E.gee(df[df["pair"] == "p00"], "y ~ C(day, Treatment('Precon1'))")
rt = E.ratio(res, "Precon4")
w = res.wald_test("C(day, Treatment('Precon1'))[T.Precon4] = 0", scalar=True)
check("a one-df test is statsmodels' own Wald on the bias-reduced errors", abs(rt["chi2"] - float(w.statistic)) < 1e-6 * max(1, rt["chi2"]),
      (rt["chi2"], float(w.statistic)))
check("a planted 1.65-fold rise is found (×%.2f, p = %.2g)" % (rt["ratio"], rt["p"]), 1.4 < rt["ratio"] < 1.9 and rt["p"] < 0.01)
res0 = E.gee(df[df["pair"] == "p01"], "y ~ C(day, Treatment('Precon1'))")
check("an unchanged pair is not (p = %.2f)" % E.ratio(res0, "Precon4")["p"], E.ratio(res0, "Precon4")["p"] > 0.01)
ts = E.terms(E.gee(df, "y ~ C(day, Sum) * C(pair, Sum)"))
check("terms of up to %d df are on the robust errors, more on the model's own" % E.ROBUST_MAX_DF,
      all((t["errors"] == E.ROBUST) == (t["df"] <= E.ROBUST_MAX_DF) for t in ts) and [t["term"] for t in ts] == ["Session", "Pair", "Session × Pair"])

print("\nThis machine's tab 11")
O = E.result()
if not O:
    print("  (not worked out here: skipped)")
else:
    B = {b["band"]: b for b in O["bands"]}
    check("theta and gamma, each with all three phases", sorted(B) == ["gamma", "theta"]
          and all(B[b][ph]["figures"] for b in B for ph in ("phase1", "phase2", "phase3")))
    files_ok = all(os.path.isfile(E.figs_dir(f["files"][k])) for b in B.values() for ph in ("phase1", "phase2", "phase3")
                   for f in b[ph]["figures"] for k in ("svg", "pdf", "png", "xlsx", "pzfx"))
    raw_ok = all(os.path.isfile(E.figs_dir(f["files_raw"][k])) and f["files_raw"][k] != f["files"][k] for b in B.values()
                 for ph in ("phase1", "phase2", "phase3") for f in b[ph]["figures"] for k in ("svg", "pdf", "png"))
    check("every figure as SVG, PDF, PNG and its Prism files, and drawn again for the other side of the switch", files_ok and raw_ok)
    for b in B.values():
        n_pairs = sum(1 for x in b["phase1"]["pairs"] if x)
        figs = b["phase1"]["figures"]
        check("%s: one figure a pair (%d), then all ten" % (b["band"], n_pairs),
              [f["kind"] for f in figs] == ["pair"] * n_pairs + ["pooled"])
        qs = [x["a2"]["q"] for x in b["phase1"]["pairs"] if x and x["a2"]]
        ps = [x["a2"]["p"] for x in b["phase1"]["pairs"] if x and x["a2"]]
        check("%s: each pair's q is Benjamini-Hochberg of the ten p" % b["band"], np.allclose(qs, multipletests(ps, method="fdr_bh")[1]))
        check("%s: a figure passes with the correction on exactly when its q < 0.05, off when its p < 0.05" % b["band"],
              all(f["passes"]["fdr"] == (b["phase1"]["pairs"][f["pair"]]["a2"]["q"] < 0.05)
                  and f["passes"]["raw"] == (b["phase1"]["pairs"][f["pair"]]["a2"]["p"] < 0.05) for f in figs if f["kind"] == "pair"))
        sp = [x["sp"]["p"] for x in b["phase3"]["pairs"] if x and x.get("sp")]
        sq = [x["sp"]["q"] for x in b["phase3"]["pairs"] if x and x.get("sp")]
        check("%s: baseline, cue 1, cue 2: Session × Period on 2 robust df in every pair, its q Benjamini-Hochberg of the ten" % b["band"],
              len(sp) == sum(1 for x in b["phase3"]["pairs"] if x) and np.allclose(sq, multipletests(sp, method="fdr_bh")[1])
              and all(x["sp"]["df"] == 2 and x["sp"]["errors"] == E.ROBUST for x in b["phase3"]["pairs"] if x))
    with open(E.export_dir("evenmore_long.csv"), encoding="utf-8") as fh:
        long_rows = list(csv.DictReader(fh))
    for b in B.values():
        n_a1 = sum(1 for r in long_rows if r["model"] == "A1" and r["band"] == b["band"])
        want = sum(2 * len(x["rats"]) for x in b["phase1"]["pairs"] if x)
        check("%s: the long file has every A1 row the GEE saw (%d)" % (b["band"], want), n_a1 == want, n_a1)
    with zipfile.ZipFile(E.export_dir("evenmore_gee.zip")) as z:
        names = set(z.namelist())
    check("the zip: rows, tests, R, SPSS, read-me", names == {"evenmore_long.csv", "evenmore_results.csv", "evenmore_gee.R",
                                                              "evenmore_gee.sps", "evenmore_README.txt"}, names)
    sps = open(E.export_dir("evenmore_gee.sps"), encoding="utf-8").read()
    check("the SPSS syntax fits a Gamma, log-link GEE with the rat as subject, every model in both bands",
          sps.count("DISTRIBUTION=GAMMA LINK=LOG") == 8 and sps.count("SUBJECT=rat") == 8 and "CORRTYPE=EXCHANGEABLE" in sps)
    rb = O.get("robust") or []
    check("every result passing uncorrected has its robustness: eight leave-one-out fits and a mixed model (%d)" % len(rb),
          bool(rb) and all(len(r["loo"]) == len(r["loo"]) >= 4 and (r["lmm"].get("p") is not None or r["lmm"].get("error")) for r in rb)
          and all(r["passes"]["raw"] for r in rb))
    fl = O.get("flag") or {}
    check("the flag has its numbers: pooled and mean of trials, both bands and days",
          all(fl.get(b, {}).get(d, {}).get(k) is not None for b in ("theta", "gamma") for d in E.DAYS for k in ("pooled", "trialmean")))

print("\n%d passed, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
