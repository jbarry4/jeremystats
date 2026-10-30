"""check_final.py -- tab 12, the final stage: its measures against planted
signals, and this machine's final.json against itself.

    python tools/check_final.py

Part 1 makes its own signals and day arrays. Part 2 reads
GUI_logs/.cache/monolith/final when it is there; it writes nothing.
"""
import os
import sys
import zipfile

import numpy as np

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
from backend import monolith as MO                     # noqa: E402

MO.configure(os.path.join(APP, "GUI_logs"))
from backend import evenmore as E, finalstage as FS, joe   # noqa: E402

ok = bad = 0


def check(name, cond, detail=None):
    global ok, bad
    if cond:
        ok += 1
        print("  ok    " + name)
    else:
        bad += 1
        print("  FAIL  " + name + ("   " + repr(detail)[:300] if detail is not None else ""))


print("The measures, on planted signals")
rng = np.random.default_rng(30)
fs = E.FS
t = np.arange(int(20 * fs)) / fs
# power: a 7 Hz sine of amplitude A µV has a band power of A^2/2 µV^2 spread over the band
A = 50.0
x = A * np.sin(2 * np.pi * 7.0 * t) + rng.standard_normal(t.size)
Fx = E._spectra_of([x])[0]
psd = (np.abs(Fx) ** 2).mean(axis=0) * FS._scale()
df_ = E.FREQS[1] - E.FREQS[0]
m = (E.FREQS >= 5) & (E.FREQS <= 12)
check("power: the PSD integrates to a sine's power, A²/2 (%.0f against %.0f µV²)" % (psd[m].sum() * df_, A * A / 2),
      abs(psd[m].sum() * df_ / (A * A / 2) - 1) < 0.05)
check("power in dB is 10·log10 of µV²/Hz", np.allclose(FS._db(np.array([1.0, 10.0, 100.0])), [0, 10, 20]))
# FOOOF: 1/f^2 background with a theta bump
f = E.FREQS
bg = 1e4 / np.maximum(f, 1.0) ** 2
bump = 1e4 / 49.0 * 3.0 * np.exp(-0.5 * ((f - 7.5) / 1.0) ** 2)
got = FS.fooof_fit(f, bg + bump)
check("FOOOF: a 1/f² background gives an exponent of 2 and finds the 7.5 Hz theta peak (%.2f, %.1f Hz)" % (got["exponent"], got["theta_cf"]),
      got and abs(got["exponent"] - 2.0) < 0.2 and abs(got["theta_cf"] - 7.5) < 0.6)
# Granger: b follows a by 10 ms; pooled over three "trials"
from backend import sweep                              # noqa: E402
S = np.zeros((E.GC_NFFT, 2, 2), complex)
n = 0
for k in range(3):
    a = rng.standard_normal(t.size)
    a = np.convolve(a, np.ones(15) / 15, mode="same") + 0.2 * rng.standard_normal(t.size)
    b = np.roll(a, 10) * 0.9 + 0.5 * rng.standard_normal(t.size)
    Ga, Gb = E._gc_spectra_of([a, b])
    S[:, 0, 0] += (np.abs(Ga) ** 2).sum(0)
    S[:, 1, 1] += (np.abs(Gb) ** 2).sum(0)
    S[:, 0, 1] += (Ga * np.conj(Gb)).sum(0)
    S[:, 1, 0] += np.conj((Ga * np.conj(Gb)).sum(0))
    n += Ga.shape[0]
H, sig, _it = sweep.wilson((S / n)[None])
g12, g21 = sweep.granger(H, sig)
mm = (FS.GC_FREQS > 2) & (FS.GC_FREQS < 30)
check("Granger from a pooled matrix: the leader leads (a→b %.3f, b→a %.3f)" % (np.mean(g12[0, mm]), np.mean(g21[0, mm])),
      np.mean(g12[0, mm]) > 3 * np.mean(g21[0, mm]))
# PAC: gamma bursts on theta's peak, and none
th = np.sin(2 * np.pi * 7.0 * t)
coupled =3 * th + (1 + th) * 0.5 * np.sin(2 * np.pi * 45.0 * t) + 0.3 * rng.standard_normal(t.size)
flat = 3 * th + 0.5 * np.sin(2 * np.pi * 45.0 * t) + 0.3 * rng.standard_normal(t.size)


def mi(sig_):
    s_, n_ = E._pac_hist(sig_)
    mean = s_ / n_
    p = mean / mean.sum()
    return (np.log(len(p)) + np.sum(p * np.log(p))) / np.log(len(p))
check("PAC: gamma riding theta's peak gives a modulation index far above none (%.4f against %.4f)" % (mi(coupled), mi(flat)),
      mi(coupled) > 10 * mi(flat))
# the SPSS coding: the last level the reference
import pandas as pd                                     # noqa: E402
rows = [{"rat": r, "day": d, "period": p, "y": float(1 + (d == "Precon4") * 0.5 + (p == "3 cue 2") * 0.2 + rng.normal(0, 0.05))}
        for r in range(8) for d in E.DAYS for p in ("1 baseline", "2 cue 1", "3 cue 2")]
refs, co = FS.spss_coefficients(pd.DataFrame(rows), ["day", "period"], "normal")
check("SPSS's coefficients: Precon4 and cue 2 (the last levels) are the reference, and the intercept is their cell",
      refs == {"day": "Precon4", "period": "3 cue 2"} and abs(co[0]["b"] - 1.7) < 0.05, refs)

print("\nThis machine's tab 12")
O = FS.result()
if not O:
    print("  (not worked out here: skipped)")
else:
    EM = E.result()
    check("power: each region on its own, both bands, Region never a factor",
          all(not any("Region" in t["term"] for t in (x["e1"] or []) + (x["e2"] or [])) for b in O["power"].values() for x in b if x)
          and sorted(O["power"]) == ["gamma", "theta"])
    for b, per in O["power"].items():
        ps = [x["sp"]["p"] for x in per if x and x.get("sp")]
        qs = [x["sp"]["q"] for x in per if x and x.get("sp")]
        from statsmodels.stats.multitest import multipletests
        check("%s power: Session × Period on 2 robust df, its q Benjamini-Hochberg across the five regions" % b,
              np.allclose(qs, multipletests(ps, method="fdr_bh")[1]) and all(x["sp"]["df"] == 2 for x in per if x))
    for m in E.MODES:
        want = {(h["pair"], h["band"]) for h in O["hits"][m]}
        got = {(x["pair"], x["band"]) for x in O["granger"] if x["in"][m]}
        check("Granger runs on exactly tab 11's results with the correction %s (%d)" % ("on" if m == "fdr" else "off", len(want)), want == got)
        regs = {r for p, _b in want for r in (E.STRUCTS[E.PAIRS[p][0]][0], E.STRUCTS[E.PAIRS[p][1]][0])}
        check("coupling runs in exactly their regions (%s)" % ", ".join(sorted(regs)), {x["region"] for x in O["pac"] if x["in"][m]} == regs)
    figs_ok = all(os.path.isfile(FS.figs_dir(f[k][e])) for v in O["figures"].values() for f in v for k in ("files", "files_raw")
                  for e in ("svg", "pdf", "png"))
    check("every figure drawn both sides of the switch", figs_ok)
    fdr_sig = [r["label"] for r in FS.significant(EM, {"power": {b: v for b, v in O["power"].items()}, "fooof": O["fooof"],
                                                       "granger": O["granger"], "pac": O["pac"]}, "fdr")]
    meth = " ".join(p for s in O["methods"] for p in s["paras"])
    check("the methods name every result that passes with the correction on (%d)" % len(fdr_sig), all(lbl in meth for lbl in fdr_sig))
    check("the methods say the reference levels, the clipping rule, the notch and the 20 × 16 × 8 × 2 question",
          "Precon4" in meth and "Period, cue 2" in meth and "16 or more consecutive samples" in meth and "59–61 Hz" in meth
          and "waiting for confirmation from Joe" in meth)
    with zipfile.ZipFile(FS.export_dir("final_files.zip")) as z:
        names = set(z.namelist())
    check("the zip: rows, tests, SPSS's coefficients, R, SPSS, the methods; the side question outside it",
          {"final_long.csv", "final_results.csv", "final_coefficients_spss.csv", "final_gee.R", "final_gee.sps", "final_methods.txt",
           "final_methods.docx"} == names and os.path.isfile(FS.export_dir("final_side_question_not_for_joe.csv")), names)

print("\n%d passed, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
