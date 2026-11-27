"""One number a recording for every measure; PTEN against CTL, the knockout
dose, the ordered trend; BH over the lot; the same on the No P-spikes set."""
import json
import os
import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
import numpy as np  # noqa: E402
from scipy import stats as st  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MIN_N = 20


def med(v):
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    return float(np.median(v)) if v.size else np.nan


def best_split(d, crit="mix"):
    """The split that parts this animal's events best: the lowest mix-up
    (two-Gaussian, on the split's own axis) among splits leaving 5+ events
    a side. Blind to group."""
    ok = [(m, e) for m, e in d["splits"].items() if "err" not in e and min(e["n1"], e["n2"]) >= 5
          and e.get(crit) is not None and np.isfinite(e.get(crit))]
    if not ok:
        return None, None
    m, e = (min if crit == "mix" else max)(ok, key=lambda p: p[1][crit])
    return m, e


def measures(d):
    o = {"lab": d["lab"], "g": d["g"], "ko": d["ko"], "n": d["n"]}
    mins = d["dur"] / 60.0
    o["rate"] = d["n"] / mins
    for k in ("lfp_amp", "lfp_ms", "sink_peak", "sink_total", "source_peak", "sink_width", "sink_spread", "sink_ms", "blade_gap"):
        if d.get(k) is not None:
            o[k] = med(d[k])
    o["amp_cv"] = float(np.std(d["lfp_amp"]) / np.mean(d["lfp_amp"])) if d["n"] >= MIN_N else np.nan
    o["sink_per_lfp"] = o["sink_peak"] / o["lfp_amp"]
    o["src_per_sink"] = o["source_peak"] / o["sink_peak"]
    if d.get("top_peak") is not None:
        o["blade_balance"] = med((d["top_peak"] - d["bot_peak"]) / (d["top_peak"] + d["bot_peak"] + 1e-12))
        o["blade_gap_mean"] = d["blade_gap_mean"]
        o["both_blades"] = float(np.mean((d["top_peak"] > 0.25 * d["sink_peak"]) & (d["bot_peak"] > 0.25 * d["sink_peak"])))
    t = d.get("times")
    if t is not None and t.size >= MIN_N:
        iei = np.diff(np.sort(t))
        iei = iei[iei > 0]
        o["iei_cv"] = float(np.std(iei) / np.mean(iei))
        o["burst"] = float(np.mean(iei < 1.0))
        o["iei_med"] = float(np.median(iei))
        nb = int(d["dur"] // 30)
        if nb >= 10:
            cnt = np.histogram(t, bins=np.arange(nb + 1) * 30.0)[0]
            o["fano30"] = float(cnt.var() / max(cnt.mean(), 1e-9))
        tp, tt_ = d.get("theta_p"), d.get("theta_t")
        if tp is not None and len(tp) > 20:
            rank = st.rankdata(tp) / len(tp)
            idx = np.clip(np.searchsorted(tt_, t) - 1, 0, len(tp) - 1)
            o["theta_pct"] = float(np.mean(rank[idx]))
            cnt = np.zeros(len(tp))
            np.add.at(cnt, idx, 1)
            o["theta_rho"] = float(st.spearmanr(tp, cnt).correlation)
            o["theta_cv"] = float(np.std(tp) / np.mean(tp))
    # separation
    e = d["splits"].get("bite", {})
    o["si_bite"], o["mix_bite"] = e.get("si"), e.get("mix")
    ms = [v.get("mix") for v in d["splits"].values() if "err" not in v and v.get("mix") is not None and min(v["n1"], v["n2"]) >= 5]
    sis = [v.get("si") for v in d["splits"].values() if "err" not in v and v.get("si") is not None and min(v["n1"], v["n2"]) >= 5]
    o["mix_median"] = med(ms) if ms else np.nan
    o["si_median"] = med(sis) if sis else np.nan
    o["n_clean"] = float(sum(1 for v in ms if v <= 0.10))
    bm, be = best_split(d)
    o["best"] = bm
    if be is not None and d["n"] >= MIN_N:
        o["mix_best"], o["si_best"] = be["mix"], be["si"]
        ty = be["types"]
        o["ds1_share"] = float((ty == 1).mean())
        o["ds1_rate"], o["ds2_rate"] = float((ty == 1).sum() / mins), float((ty == 2).sum() / mins)
        for k in ("lfp_amp", "sink_peak", "sink_width", "sink_ms", "lfp_ms"):
            a, b = med(d[k][ty == 1]), med(d[k][ty == 2])
            o["ds1_" + k], o["ds2_" + k] = a, b
            o["ratio12_" + k] = a / b if b else np.nan
        if not be.get("why"):
            sc = be["score"]
            okk = np.isfinite(sc)
            o["oml_mml_um"] = abs(be["oml"] - be["mml"]) * 50.0
            if okk.sum() >= 10:
                o["ds3_share_best"] = float((np.abs(sc[okk]) <= 0.5).sum() / d["n"])
                o["ds3_rate_best"] = float((np.abs(sc[okk]) <= 0.5).sum() / mins)
                o["abs_score"] = float(np.median(np.abs(sc[okk])))
                o["unscorable"] = float((~okk).mean())
                s = sc[okk]
                g1 = st.skew(s)
                g2 = st.kurtosis(s)
                nn = s.size
                o["bimodality"] = float((g1 ** 2 + 1) / (g2 + 3 * (nn - 1) ** 2 / ((nn - 2) * (nn - 3))))
    return o


def run(V, show=True):
    recs = pickle.load(open(os.path.join(HERE, "deep_v%d.pkl" % V), "rb"))
    M = [measures(d) for d in recs]
    keys = sorted({k for m in M for k, v in m.items() if k not in ("lab", "g", "ko", "n", "best")})
    tests = []
    for key in keys:
        rows = [m for m in M if m.get(key) is not None and np.isfinite(m.get(key)) and m["n"] >= MIN_N]
        a = np.array([m[key] for m in rows if m["g"] == "CTL"])
        b = np.array([m[key] for m in rows if m["g"] == "PTEN"])
        if min(a.size, b.size) < 5:
            continue
        p = st.mannwhitneyu(a, b, alternative="two-sided").pvalue
        auc = st.mannwhitneyu(b, a).statistic / (a.size * b.size)
        tests.append(("group", key, p, auc, "CTL %.3g  PTEN %.3g  (n %d, %d)" % (np.median(a), np.median(b), a.size, b.size)))
        pt = [m for m in rows if m["g"] == "PTEN"]
        rho = st.spearmanr([m["ko"] for m in pt], [m[key] for m in pt])
        tests.append(("dose", key, rho.pvalue, rho.correlation, "rho %.2f (n %d)" % (rho.correlation, len(pt))))
        ra = st.spearmanr([m["ko"] for m in rows], [m[key] for m in rows])
        tests.append(("all", key, ra.pvalue, ra.correlation, "rho %.2f (n %d, CTL at 0)" % (ra.correlation, len(rows))))
    ps = np.array([t[2] for t in tests])
    order = np.argsort(ps)
    q = np.empty(len(ps))
    prev = 1.0
    for rank, i in enumerate(order[::-1]):
        prev = min(prev, ps[i] * len(ps) / (len(ps) - rank))
        q[i] = prev
    if show:
        print("\n=== room v%d: %d tests over %d measures ===" % (V, len(tests), len(keys)))
        for i in order[:28]:
            print("  p %.4f q %.3f  %-6s %-22s eff %+.2f  %s" % (ps[i], q[i], tests[i][0], tests[i][1], tests[i][3], tests[i][4]))
        print("  best split per animal:", ", ".join("%s:%s" % (m["lab"], m["best"]) for m in M))
    return M, {(t[0], t[1]): (t[2], t[3], float(q[i])) for i, t in enumerate(tests)}


if __name__ == "__main__":
    M6, T6 = run(6)
    M8, T8 = run(8)
    print("\n=== holds on both sets (p < 0.05 on each, same sign) ===")
    for k, (p, e, q) in sorted(T6.items(), key=lambda kv: kv[1][0]):
        if k in T8 and p < 0.05 and T8[k][0] < 0.05 and np.sign(e) == np.sign(T8[k][1]):
            print("  %-6s %-22s v6 p %.4f q %.3f eff %+.2f | v8 p %.4f q %.3f eff %+.2f" % (k[0], k[1], p, q, e, T8[k][0], T8[k][2], T8[k][1]))
    json.dump({"v6": M6, "v8": M8}, open(os.path.join(HERE, "deep_measures.json"), "w"), default=str)
