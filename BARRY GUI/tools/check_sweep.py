# -*- coding: utf-8 -*-
"""Checks for backend/sweep.py -- the Monolith's engine.

    python tools\\check_sweep.py

On made-up signals whose answers are known:
  - the band table: 55 one-hertz bands, +/-15% (never under +/-0.5 Hz),
    none past 55 Hz; theta, beta and low gamma as coupling defines them;
    slow is <= 12 Hz and theta, fast the rest
  - the named bands give the circuits' own numbers: coherence, raw cc and
    envelope cc equal coupling.band_metrics on the same signals
  - raw cc in a 1 Hz band equals coupling's own cross-correlation run on
    the same band-passed traces (so the lag convention is the same)
  - zero-lag mixing (volume conduction): coherence and envelope r high;
    imaginary coherence, PLI, wPLI, debiased wPLI and the orthogonalised
    envelope r near zero
  - a quarter-cycle lag: PLI and wPLI near 1, imaginary coherence high
  - independent noise: PPC and debiased wPLI average zero; PLV does not
    (it is the biased one)
  - Granger: Wilson's factor rebuilds the spectrum; on a VAR whose answer
    is known in closed form, the estimate matches it in one direction and
    is near zero in the other; through window_measures, a -> b beats b -> a
  - power: a 20 Hz rhythm is loudest in the 20 Hz band
  - PAC: theta phase driving gamma amplitude is found at that cell, in the
    right direction between two regions, and not where it is absent
  - a missing region, and a flat one, leave their pairs NaN and no others
  - explain(), behind the page's pictures: each curve rebuilds its number
    -- the coherence and Granger spectra averaged over the band, the
    phase-difference rose's mean vector, the lead/lag shares, the lag
    curves' peaks and zero, the segments' PPC and debiased wPLI, the power
    spectrum's band mean, the PAC bars' MI against pac_window -- and the
    same curve read over the wrong band does not
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

import numpy as np                                        # noqa: E402

from backend import coupling, sweep as SW                 # noqa: E402

N = {"ok": 0, "bad": 0}
FS = 1000.0
MI = {m: i for i, m in enumerate(SW.EDGE_METHODS)}
BI = {b: i for i, b in enumerate(SW.BAND_IDS)}


def check(name, cond, detail=""):
    N["ok" if cond else "bad"] += 1
    print(("  ok    " if cond else "  FAIL  ") + name
          + ("" if cond or detail == "" else "  " + str(detail)[:300]))


def noise(rng, n, scale=1.0):
    """Pinkish noise: white plus a little integrated."""
    return (rng.standard_normal(n) + 0.05 * np.cumsum(rng.standard_normal(n))
            ) * scale


def bands_table():
    print("\nThe bands")
    B = SW.BANDS
    bins = [b for b in B if not b["named"]]
    check("55 one-hertz bands and 3 named", len(bins) == 55
          and [b["id"] for b in B if b["named"]] == list(coupling.BAND_ORDER))
    f1 = SW.BAND_BY_ID["f01"]
    check("1 Hz is 0.5-1.5 Hz", (f1["low"], f1["high"]) == (0.5, 1.5), f1)
    f20 = SW.BAND_BY_ID["f20"]
    check("20 Hz is 17-23 Hz (+/-15%)", (f20["low"], f20["high"]) == (17.0, 23.0),
          f20)
    f55 = SW.BAND_BY_ID["f55"]
    check("55 Hz is cut at 55 (46.75-55), never across the notch",
          (f55["low"], f55["high"]) == (46.75, 55.0), f55)
    check("no band reaches past 55 Hz", max(b["high"] for b in B) == 55.0)
    check("no band narrower than +/-0.5 Hz",
          min((b["high"] - b["low"]) / 2 for b in bins) >= 0.5 - 1e-9)
    for bid in coupling.BAND_ORDER:
        b, c = SW.BAND_BY_ID[bid], coupling.BANDS[bid]
        check("%s is coupling's own band and lag" % bid,
              (b["low"], b["high"], b["lag_s"] * 1000.0)
              == (c["low"], c["high"], c["max_lag_ms"]))
    slow = SW.bands_for("trans_slow")
    fast = SW.bands_for("trans_fast")
    check("slow transition bands are 1-12 Hz and theta",
          slow == ["f%02d" % f for f in range(1, 13)] + ["theta"], slow)
    check("fast transition bands are 13-55 Hz, beta and low gamma",
          fast == ["f%02d" % f for f in range(13, 56)] + ["beta", "gamma_low"])
    check("lag bound is two cycles of each bin",
          SW.BAND_BY_ID["f10"]["lag_s"] == 0.2
          and SW.BAND_BY_ID["f01"]["lag_s"] == 2.0)
    check("Welch segments: 2 s for 1-3 Hz, 1.5 s for 4 Hz, 1 s from 5 Hz",
          [SW.welch_len_s(SW.BAND_BY_ID["f%02d" % f]) for f in (1, 3, 4, 5, 30)]
          == [2.0, 2.0, 1.5, 1.0, 1.0]
          and SW.welch_len_s(SW.BAND_BY_ID["theta"]) == 1.0)
    cells = SW.PAC_CELLS
    check("PAC: 11 phase x 8 amplitude cells", len(cells) == 88)
    bad = [c for c in cells if c[3] is not None and
           (c[3][0] < c[2][1] + SW.PAC_GAP_HZ or c[3][1] - c[3][0] < 2 * c[0]
            or c[3][1] > 55.0)]
    check("PAC: every measured cell carries its sidebands, sits above its "
          "phase band and stays under 55 Hz", not bad, bad[:3])


def named_equal_coupling():
    print("\nNamed bands are the circuits' numbers")
    rng = np.random.default_rng(7)
    n = 10020
    t = np.arange(n) / FS
    worst = {"coherence": 0.0, "raw_cc": 0.0, "env_cc": 0.0}
    for trial in range(3):
        common = np.sin(2 * np.pi * 7 * t + trial) * 2
        sigs = [(noise(rng, n) + common * (0.3 + 0.2 * r)) * 80 for r in range(4)]
        v, _pw, _n = SW.window_measures(sigs, list(coupling.BAND_ORDER))
        pairs = SW.pairs_of(list(range(4)))
        for pi, (a, b) in enumerate(pairs):
            for bi, bid in enumerate(coupling.BAND_ORDER):
                bm = coupling.band_metrics(sigs[a], sigs[b],
                                           coupling.band_spec(bid))
                for m, cm in (("coherence", "coherence"), ("raw_cc", "raw_cc"),
                              ("env_cc", "amp_cc")):
                    d = abs(v[bi, MI[m], pi] - bm[cm]["summary"]["value"])
                    worst[m] = max(worst[m], d)
    for m, d in worst.items():
        # band_metrics rounds to six places.
        check("%s equals coupling.band_metrics (worst %.1e)" % (m, d),
              d <= 6e-7, d)


def bin_raw_cc_equals_coupling():
    print("\nRaw cc in a 1 Hz band, against coupling's own cross-correlation")
    rng = np.random.default_rng(11)
    n = 10020
    a = noise(rng, n, 50)
    b = np.roll(a, 23) * 0.7 + noise(rng, n, 30)
    worst = 0.0
    for bid in ("f03", "f10", "f40"):
        band = SW.BAND_BY_ID[bid]
        v, _pw, _n = SW.window_measures([a, b], [bid])
        na = coupling.notch(a, FS)[0]
        nb = coupling.notch(b, FS)[0]
        ya = np.real(SW.analytic(na, FS, band["low"], band["high"]))
        yb = np.real(SW.analytic(nb, FS, band["low"], band["high"]))
        lags, r = coupling._xcorr_coeff(ya, yb, FS, band["lag_s"])
        val, _lag = coupling._peak(lags, r)
        worst = max(worst, abs(v[0, MI["raw_cc"], 0] - val))
        ea = np.abs(SW.analytic(na, FS, band["low"], band["high"]))
        eb = np.abs(SW.analytic(nb, FS, band["low"], band["high"]))
        lags, r = coupling._xcorr_coeff(ea - ea.mean(), eb - eb.mean(), FS,
                                        band["lag_s"])
        val2, _ = coupling._peak(lags, r)
        worst = max(worst, abs(v[0, MI["env_cc"], 0] - val2))
    check("raw cc and envelope cc equal coupling._xcorr_coeff's peak "
          "(worst %.1e)" % worst, worst < 1e-9, worst)


def phase_methods():
    print("\nPhase methods on known relationships")
    rng = np.random.default_rng(3)
    n = 10020
    # Zero-lag mixing: b is a plus a little of its own noise.
    vals = []
    for _ in range(6):
        a = noise(rng, n, 50)
        b = a + noise(rng, n, 15)
        v, _p, _n = SW.window_measures([a, b], ["f10"])
        vals.append(v[0, :, 0])
    v = np.mean(vals, axis=0)
    check("volume conduction: coherence high (%.2f)" % v[MI["coherence"]],
          v[MI["coherence"]] > 0.8)
    check("volume conduction: envelope r at zero lag high (%.2f)"
          % v[MI["env_cc0"]], v[MI["env_cc0"]] > 0.8)
    check("volume conduction: imaginary coherence near 0 (%.3f)"
          % v[MI["icoh"]], v[MI["icoh"]] < 0.05)
    check("volume conduction: wPLI low (%.2f), debiased wPLI near 0 (%.3f)"
          % (v[MI["wpli"]], v[MI["dwpli"]]),
          v[MI["wpli"]] < 0.3 and abs(v[MI["dwpli"]]) < 0.1)
    check("volume conduction: orthogonalised envelope r near 0 (%.2f)"
          % v[MI["orth_env"]], abs(v[MI["orth_env"]]) < 0.15)
    check("volume conduction: PLV high (%.2f) -- it cannot tell"
          % v[MI["plv"]], v[MI["plv"]] > 0.8)

    # A quarter cycle of lag at 10 Hz: 25 ms.
    vals = []
    for _ in range(6):
        a = noise(rng, n, 50)
        b = np.roll(a, 25) + noise(rng, n, 15)
        v, _p, _n = SW.window_measures([a, b], ["f10"])
        vals.append(v[0, :, 0])
    v = np.mean(vals, axis=0)
    check("quarter-cycle lag: PLI (%.2f) and wPLI (%.2f) near 1"
          % (v[MI["pli"]], v[MI["wpli"]]),
          v[MI["pli"]] > 0.8 and v[MI["wpli"]] > 0.9)
    check("quarter-cycle lag: imaginary coherence high (%.2f)" % v[MI["icoh"]],
          v[MI["icoh"]] > 0.5)
    check("quarter-cycle lag: debiased wPLI high (%.2f)" % v[MI["dwpli"]],
          v[MI["dwpli"]] > 0.8)

    # Independent: the unbiased ones average zero, PLV does not.
    se = lambda x: np.std(x, ddof=1) / math.sqrt(len(x))  # noqa: E731
    for bid in ("f06", "f20"):
        ppc, dw, plv = [], [], []
        for _ in range(80):
            a = noise(rng, n, 50)
            b = noise(rng, n, 50)
            v, _p, _n = SW.window_measures([a, b], [bid])
            ppc.append(v[0, MI["ppc"], 0])
            dw.append(v[0, MI["dwpli"], 0])
            plv.append(v[0, MI["plv"], 0])
        check("independent, %s: PPC averages 0 (%.4f +/- %.4f)"
              % (bid, np.mean(ppc), se(ppc)),
              abs(np.mean(ppc)) < 3 * se(ppc) + 2e-3)
        check("independent, %s: debiased wPLI averages 0 (%.4f +/- %.4f)"
              % (bid, np.mean(dw), se(dw)),
              abs(np.mean(dw)) < 3 * se(dw) + 2e-3)
        check("independent, %s: PLV does not (%.3f) -- the bias PPC removes"
              % (bid, np.mean(plv)), np.mean(plv) > 0.03)


def var_series(rng, T, a_to_b=0.5):
    x = np.zeros((2, T))
    e = rng.standard_normal((2, T))
    for t in range(2, T):
        x[0, t] = 0.55 * x[0, t - 1] - 0.7 * x[0, t - 2] + e[0, t]
        x[1, t] = (0.56 * x[1, t - 1] - 0.75 * x[1, t - 2]
                   + a_to_b * x[0, t - 1] + e[1, t])
    return x


def granger_known():
    print("\nGranger")
    rng = np.random.default_rng(5)
    fs = 250.0
    x = var_series(rng, int(fs * 300))
    nseg = 500
    win = SW._hann(nseg)
    segs = SW._segments(x, nseg, nseg // 2)
    segs = segs - segs.mean(axis=2, keepdims=True)
    F = np.fft.fft(segs * win, n=2 * nseg, axis=2)
    S = np.empty((1, 2 * nseg, 2, 2), complex)
    S[..., 0, 0] = np.mean(np.abs(F[0]) ** 2, axis=0)
    S[..., 1, 1] = np.mean(np.abs(F[1]) ** 2, axis=0)
    S[..., 0, 1] = np.mean(F[0] * np.conj(F[1]), axis=0)
    S[..., 1, 0] = np.conj(S[..., 0, 1])
    H, sig, it = SW.wilson(S)
    Sf = SW._mm(SW._mm(H, sig[:, None].astype(complex)), SW._ct(H))
    rel = np.abs(Sf - S).max() / np.abs(S).max()
    check("Wilson converges (%d iterations) and rebuilds the spectrum "
          "(%.1e)" % (it, rel), it < SW.WILSON_MAX and rel < 1e-3, (it, rel))
    g12, g21 = SW.granger(H, sig)
    f = np.fft.fftfreq(2 * nseg, 1 / fs)
    A1 = np.array([[0.55, 0], [0.5, 0.56]])
    A2 = np.array([[-0.7, 0], [0, -0.75]])
    errs, rev = [], []
    for fr in (5, 10, 20, 30, 40):
        i = int(round(fr * 2 * nseg / fs))
        z = np.exp(-2j * np.pi * f[i] / fs)
        Hf = np.linalg.inv(np.eye(2) - A1 * z - A2 * z * z)
        Sg = Hf @ Hf.conj().T
        true12 = math.log(Sg[1, 1].real / abs(Hf[1, 1]) ** 2)
        errs.append(abs(g12[0, i] - true12))
        rev.append(abs(g21[0, i]))
    check("a -> b matches the closed form (worst %.3f nats)" % max(errs),
          max(errs) < 0.06, errs)
    check("b -> a is near zero (worst %.3f nats)" % max(rev), max(rev) < 0.03,
          rev)

    # Through the whole window path: a drives b at 1000 Hz, 10 ms late.
    n = 10020
    gab, gba = [], []
    for _ in range(4):
        a = noise(rng, n, 40)
        b = 0.8 * np.roll(a, 10) + noise(rng, n, 40)
        v, _p, _n = SW.window_measures([a, b], ["f10", "f30", "theta"])
        gab.append(v[:, MI["gc_ab"], 0])
        gba.append(v[:, MI["gc_ba"], 0])
    gab, gba = np.mean(gab, axis=0), np.mean(gba, axis=0)
    check("window path: a -> b beats b -> a in every band (%s vs %s)"
          % (np.round(gab, 3), np.round(gba, 3)),
          np.all(gab > gba + 0.05) and np.all(gba < 0.05))


def power_and_gaps():
    print("\nPower, and what is not measured")
    rng = np.random.default_rng(9)
    n = 10020
    t = np.arange(n) / FS
    a = noise(rng, n, 20) + 200 * np.sin(2 * np.pi * 20 * t)
    b = noise(rng, n, 20)
    flat = np.full(n, 5.0)
    v, pw, _n = SW.window_measures([a, b, None, flat],
                                   ["f10", "f20", "f30"])
    check("power: the 20 Hz rhythm is loudest at 20 Hz (%s)"
          % np.round(pw[:, 0], 2),
          pw[1, 0] > pw[0, 0] + 1 and pw[1, 0] > pw[2, 0] + 1)
    check("power: a missing and a flat region have none",
          np.all(np.isnan(pw[:, 2])) and np.all(np.isnan(pw[:, 3])))
    pairs = SW.pairs_of(list(range(4)))
    gone = [i for i, (x, y) in enumerate(pairs) if {x, y} & {2, 3}]
    kept = [i for i in range(len(pairs)) if i not in gone]
    check("every pair with a missing or flat region is NaN in every method",
          np.all(np.isnan(v[:, :, gone])))
    check("the pair with neither is measured in every method",
          np.all(np.isfinite(v[:, :, kept])), v[:, :, kept])


def pac_known():
    print("\nPhase-amplitude coupling")
    rng = np.random.default_rng(13)
    n = 10020
    t = np.arange(n) / FS
    theta = np.sin(2 * np.pi * 6 * t)
    gamma = np.sin(2 * np.pi * 40 * t)
    a = 60 * theta + 15 * (1 + 0.9 * theta) * gamma + noise(rng, n, 8)
    # Region 1's gamma follows region 0's theta; its own theta is noise.
    b = 15 * (1 + 0.9 * theta) * gamma + noise(rng, n, 8)
    c = 60 * np.sin(2 * np.pi * 6 * t + 1.0) + 15 * gamma + noise(rng, n, 8)
    out = SW.pac_window([a, b, c])
    R = 3
    cells = SW.PAC_CELLS
    want = [i for i, cc in enumerate(cells) if cc[0] == 6 and cc[1] == 40][0]
    self_a = out[:, 0 * R + 0]
    top = cells[int(np.nanargmax(self_a))]
    # Neighbouring phase bands overlap (6 Hz sits in both 5.1-6.9 and
    # 5.95-8.05), so the peak may sit one bin over; the far bins may not.
    far = [i for i, cc in enumerate(cells) if cc[1] == 40 and cc[0] in (2, 3, 11, 12)
           and cc[3] is not None]
    check("self PAC in region 0 peaks at 40 Hz amplitude, 6 +/- 1 Hz phase "
          "(%s), and the 6 Hz cell is within 80%% of it"
          % (top[:2],), top[1] == 40 and abs(top[0] - 6) <= 1
          and self_a[want] >= 0.8 * np.nanmax(self_a), (top[:2], self_a[want]))
    check("far phase bins carry far less (%.4f vs %.4f)"
          % (np.nanmax(self_a[far]), self_a[want]),
          np.nanmax(self_a[far]) < 0.25 * self_a[want])
    check("0 -> 1 (0's phase, 1's amplitude) is found (%.4f) and 1 -> 0 is "
          "not (%.4f)" % (out[want, 0 * R + 1], out[want, 1 * R + 0]),
          out[want, 0 * R + 1] > 10 * out[want, 1 * R + 0])
    check("an unmodulated region has none (%.4f vs %.4f)"
          % (out[want, 2 * R + 2], self_a[want]),
          out[want, 2 * R + 2] < 0.1 * self_a[want])
    unmeasured = [i for i, cc in enumerate(cells) if cc[3] is None]
    check("cells that cannot carry their sidebands are not measured",
          np.all(np.isnan(out[unmeasured])) and len(unmeasured) > 0)


def explain_agrees():
    """The pictures on the page are drawn from explain(): if a curve could
    not rebuild the number beside it, the picture would be decoration."""
    print("\nexplain(): every curve rebuilds its number")
    rng = np.random.default_rng(21)
    n = 10000
    t = np.arange(n) / FS
    s = np.sin(2 * np.pi * 8 * t + 0.3 * np.cumsum(rng.standard_normal(n)) / 40)
    a = 50 * s + noise(rng, n, 20)
    b = 40 * np.roll(s, 12) + noise(rng, n, 20)
    cell = [i for i, cc in enumerate(SW.PAC_CELLS) if cc[0] == 6 and cc[1] == 40][0]
    worst = {}

    def near(key, x, y, tol):
        d = abs(float(x) - float(y))
        worst[key] = max(worst.get(key, 0.0), d)
        return d <= tol

    oks = {k: True for k in ("same", "coherence", "icoh", "gc", "plv", "pli",
                             "wpli", "raw_cc", "env_cc", "env_cc0", "orth",
                             "ppc", "dwpli", "power", "pac")}
    for band in ("f08", "theta", "f30", "beta"):
        ex = SW.explain(a, b, band, cell=cell)
        v = ex["values"]
        vm, pw, _n = SW.window_measures([a, b], [band])
        oks["same"] &= all(
            (v[m] is None and np.isnan(vm[0, i, 0])) or near("same", v[m], vm[0, i, 0], 1e-12)
            for i, m in enumerate(SW.EDGE_METHODS)) and near("same", v["gc_net"], v["gc_ab"] - v["gc_ba"], 1e-12)
        lo, hi = ex["band"]["low"], ex["band"]["high"]
        f = np.array(ex["spectra"]["f"])
        sel = (f >= lo) & (f <= hi)
        oks["coherence"] &= near("coherence", np.nanmean(np.array(ex["spectra"]["coh"])[sel]), v["coherence"], 2e-4)
        oks["icoh"] &= near("icoh", abs(np.nanmean(np.array(ex["spectra"]["icoh"])[sel])), v["icoh"], 2e-4)
        gf = np.array(ex["granger"]["f"])
        gs = (gf >= lo) & (gf <= hi)
        oks["gc"] &= near("gc", np.nanmean(np.array(ex["granger"]["ab"])[gs]), v["gc_ab"], 1e-3) and \
            near("gc", np.nanmean(np.array(ex["granger"]["ba"])[gs]), v["gc_ba"], 1e-3)
        ph = ex["phase"]
        oks["plv"] &= near("plv", ph["plv"], v["plv"], 1e-12)
        oks["pli"] &= near("pli", abs(ph["lead_frac"] - ph["lag_frac"]), v["pli"], 1e-9)
        oks["wpli"] &= near("wpli", abs(ph["w_lead"] - ph["w_lag"]), v["wpli"], 1e-9)
        L = ex["lags"]
        oks["raw_cc"] &= near("raw_cc", L["raw_peak"][1], v["raw_cc"], 1e-9)
        oks["env_cc"] &= near("env_cc", L["env_peak"][1], v["env_cc"], 1e-9)
        z = int(np.argmin(np.abs(np.array(L["ms"]))))
        oks["env_cc0"] &= L["ms"][z] == 0 and near("env_cc0", L["env"][z], v["env_cc0"], 2e-4)
        oks["orth"] &= near("orth", (ex["orth"]["r_a"] + ex["orth"]["r_b"]) / 2.0, v["orth_env"], 1e-9)
        sg = ex["segments"]
        u = np.exp(1j * np.array(sg["angle"]))
        K = u.size
        ppc = (abs(u.sum()) ** 2 - K) / (K * (K - 1.0))
        oks["ppc"] &= near("ppc", ppc, v["ppc"], 2e-3)
        im = np.array(sg["imag"])
        dw = (im.sum() ** 2 - (im ** 2).sum()) / (np.abs(im).sum() ** 2 - (im ** 2).sum())
        oks["dwpli"] &= near("dwpli", dw, v["dwpli"], 2e-3)
        psa = np.log10(np.mean(10 ** np.array(ex["spectra"]["psd_a"])[sel]))
        psb = np.log10(np.mean(10 ** np.array(ex["spectra"]["psd_b"])[sel]))
        oks["power"] &= near("power", psa, ex["power"][0], 1e-3) and near("power", psb, ex["power"][1], 1e-3) \
            and near("power", ex["power"][0], pw[0, 0], 1e-12)
        if band == "f08":
            pac = SW.pac_window([a, b])[cell]
            P = ex["pac"]
            oks["pac"] = all(near("pac", P[k]["mi"], pac[j], 1e-9) for k, j in
                             (("aa", 0), ("ab", 1), ("ba", 2), ("bb", 3))) and \
                all(abs(sum(P[k]["p"]) - 1) < 1e-3 for k in ("aa", "ab", "ba", "bb"))
            # CONTROL: the same curve read a band too high misses.
            off = (f >= lo + 4) & (f <= hi + 4)
            miss = abs(np.nanmean(np.array(ex["spectra"]["coh"])[off]) - v["coherence"])
    check("its numbers are window_measures' own (gc_net = A→B − B→A)", oks["same"])
    for k, say in (("coherence", "coherence: the spectrum's band mean"),
                   ("icoh", "imaginary coherence: |the band mean|"),
                   ("gc", "Granger: each direction's band mean"),
                   ("plv", "PLV: the rose's mean vector"),
                   ("pli", "PLI: |lead share − lag share|"),
                   ("wpli", "wPLI: the same, weighted"),
                   ("raw_cc", "raw cc: the lag curve's peak"),
                   ("env_cc", "envelope cc: its curve's peak"),
                   ("env_cc0", "amplitude r at zero lag: the envelope curve at 0 ms"),
                   ("orth", "orthogonalised r: the mean of both ways"),
                   ("ppc", "PPC: from the segments shown"),
                   ("dwpli", "debiased wPLI: from the segments shown"),
                   ("power", "power: log of the spectrum's band mean"),
                   ("pac", "PAC: the bars' MI is pac_window's, each way")):
        check(say + " (worst %.1e)" % worst.get(k, 0.0), oks[k])
    check("CONTROL: the coherence curve read 4 Hz too high misses (%.3f)" % miss,
          miss > 0.1)


def main():
    explain_agrees()
    bands_table()
    named_equal_coupling()
    bin_raw_cc_equals_coupling()
    phase_methods()
    granger_known()
    power_and_gaps()
    pac_known()
    print("\n%d passed, %d failed" % (N["ok"], N["bad"]))
    return 1 if N["bad"] else 0


if __name__ == "__main__":
    sys.exit(main())
