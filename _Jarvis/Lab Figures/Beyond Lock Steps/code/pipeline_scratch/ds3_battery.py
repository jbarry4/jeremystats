"""A wide battery on the Halo set (room v6) as it stands: every per-recording
measure, PTEN against CTL, the knockout dose among PTEN, the ordered trend
CTL < low KO < high KO -- all corrected together (BH) -- and the checks
against the literature. One number a recording; nothing saved."""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import numpy as np  # noqa: E402
from scipy import stats as st  # noqa: E402
from backend.app import app  # noqa: E402
from backend import app as A  # noqa: E402
from backend import dsmix, sinkcut  # noqa: E402
from backend import extraction as EX  # noqa: E402

V = 6
c = app.test_client()
room = A._er_rooms()["dentate_spike"]
j = c.get("/api/extraction/%s?version=%d" % (room["id"], V)).get_json()
mode = j["mode"]
recs = []
for r in j["payload"]["recordings"]:
    method, cut = A._er_rec_split(r)
    Ar, types, L = A._er_layers(r, method, cut, mode)
    rs = dsmix.relsink(Ar, types)
    mins = (r.get("duration_s") or 0) / 60.0
    d = {"lab": r["session_label"][5:12].strip().split()[0], "g": "CTL" if str(r["group"]).upper() == "CTL" else "PTEN",
         "ko": float(r.get("ko_now", r.get("ko_pct")) or 0.0), "n": int(len(types)), "mins": mins,
         "types": [int(t) for t in types], "why": rs.get("why")}
    bv = EX.bite_view(Ar)
    d["si"] = bv["scores"]["si"]
    d["mix"] = ((L["mix"] or {}).get("plain") or {}).get("est")
    prof, ns = sinkcut.stamp_profiles(Ar)
    d["times"] = [float(x.get("stamp_s")) for x in A._dspca_load(r["gid"], r["read"])["rows"]]
    if not rs.get("why"):
        d.update(score=[None if not np.isfinite(v) else float(v) for v in rs["score"]], sink=[float(v) for v in rs["sink"]],
                 lag=[None if not np.isfinite(v) else float(v) for v in rs["lag_ms"]], oml=rs["oml"], mml=rs["mml"],
                 gap=abs(rs["oml"] - rs["mml"]), floor=rs["floor"])
        o, m = ns.index(rs["oml"]), ns.index(rs["mml"])
        d["prof_o"] = [float(v) for v in np.maximum(0, -prof[:, o])]
        d["prof_m"] = [float(v) for v in np.maximum(0, -prof[:, m])]
    recs.append(d)
json.dump(recs, open(os.path.join(os.path.dirname(__file__), "ds3_events.json"), "w"))


def measures(d, cutv=0.5):
    out = {"all_rate": d["n"] / d["mins"], "si": d["si"], "mix": d["mix"]}
    t = np.array(d["types"])
    if d["why"]:
        return out
    sc = np.array([np.nan if v is None else v for v in d["score"]])
    okk = np.isfinite(sc)
    is3 = okk & (np.abs(sc) <= cutv)
    n3 = int(is3.sum())
    n1, n2 = int(((t == 1) & ~is3).sum()), int(((t == 2) & ~is3).sum())
    out.update(ds3_rate=n3 / d["mins"], ds3_share=n3 / d["n"], ds1_rate=n1 / d["mins"], ds2_rate=n2 / d["mins"],
               ds1_share=n1 / d["n"], unsc_share=float((~okk).mean()),
               score_median=float(np.nanmedian(sc)) if okk.any() else np.nan,
               score_iqr=float(np.subtract(*np.nanpercentile(sc, [75, 25]))) if okk.sum() > 3 else np.nan,
               abs_score=float(np.nanmedian(np.abs(sc))) if okk.any() else np.nan,
               n3=n3)
    sk = np.array(d["sink"])
    if n3 >= 5 and (okk & ~is3).sum() >= 5:
        out["ds3_sink_ratio"] = float(np.median(sk[is3]) / np.median(sk[okk & ~is3]))
    lg = np.array([np.nan if v is None else v for v in d["lag"]])
    if np.isfinite(lg[is3]).sum() >= 5:
        out["ds3_lag_abs"] = float(np.nanmedian(np.abs(lg[is3])))
    return out


M = [dict(measures(d), lab=d["lab"], g=d["g"], ko=d["ko"], n=d["n"], gap=d.get("gap")) for d in recs]
KEYS = ["ds3_rate", "ds3_share", "ds1_rate", "ds2_rate", "ds1_share", "all_rate", "score_median", "abs_score", "score_iqr",
        "unsc_share", "si", "mix"]
tests = []


def col(key, sel):
    return np.array([m[key] for m in M if sel(m) and m.get(key) is not None and np.isfinite(m.get(key))], float)


for key in KEYS:
    a, b = col(key, lambda m: m["g"] == "CTL"), col(key, lambda m: m["g"] == "PTEN")
    if min(a.size, b.size) >= 4:
        p = st.mannwhitneyu(a, b, alternative="two-sided").pvalue
        tests.append(("PTEN vs CTL", key, "CTL %.3g, PTEN %.3g (medians; n %d, %d)" % (np.median(a), np.median(b), a.size, b.size), p))
    pt = [m for m in M if m["g"] == "PTEN" and m.get(key) is not None and np.isfinite(m.get(key))]
    if len(pt) >= 6:
        rho = st.spearmanr([m["ko"] for m in pt], [m[key] for m in pt])
        tests.append(("PTEN, vs %KO", key, "rho %.2f (n %d)" % (rho.correlation, len(pt)), rho.pvalue))
    # The ordered trend CTL < low KO (<10%) < high KO: Jonckheere, by permutation.
    grp = [0 if m["g"] == "CTL" else (1 if m["ko"] < 10 else 2) for m in M if m.get(key) is not None and np.isfinite(m.get(key))]
    val = [m[key] for m in M if m.get(key) is not None and np.isfinite(m.get(key))]
    grp, val = np.array(grp), np.array(val)

    def jt(g_):
        s = 0.0
        for x in (0, 1):
            for y in range(x + 1, 3):
                A_, B_ = val[g_ == x], val[g_ == y]
                s += (A_[:, None] < B_[None, :]).sum() + 0.5 * (A_[:, None] == B_[None, :]).sum()
        return s
    if all((grp == x).sum() >= 3 for x in (0, 1, 2)):
        obs = jt(grp)
        rng = np.random.default_rng(1)
        pm = np.array([jt(rng.permutation(grp)) for _ in range(5000)])
        mu = pm.mean()
        p = float((np.abs(pm - mu) >= abs(obs - mu) - 1e-9).mean())
        tests.append(("CTL<low<high KO", key, "medians %.3g / %.3g / %.3g" % tuple(np.median(val[grp == x]) for x in (0, 1, 2)), p))

ps = np.array([t[3] for t in tests])
order = np.argsort(ps)
q = np.empty(len(ps))
prev = 1.0
for rank, i in enumerate(order[::-1]):
    k = len(ps) - rank
    prev = min(prev, ps[i] * len(ps) / k)
    q[i] = prev
print("mode", mode, "| %d tests in the family" % len(tests))
for i in order[:14]:
    print("  p %.4f q %.3f  %-16s %-13s %s" % (ps[i], q[i], tests[i][0], tests[i][1], tests[i][2]))
print("  ... the rest: p from %.2f up" % ps[order[14]] if len(order) > 14 else "")

# The dose lead, across DS3 cuts, and as counts with exposure.
print("\nAmong PTEN, DS3 share against %KO, by the cut on |score|:")
for cv in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
    pt = [(d["ko"], measures(d, cv)) for d in recs if d["g"] == "PTEN" and not d["why"]]
    rho = st.spearmanr([k for k, _ in pt], [m["ds3_share"] for _, m in pt])
    a = [measures(d, cv)["ds3_share"] for d in recs if d["g"] == "CTL" and not d["why"]]
    b = [m["ds3_share"] for _, m in pt]
    print("  cut %.1f: rho %.2f p %.4f | DS3 counts %s | PTEN vs CTL p %.2f" % (
        cv, rho.correlation, rho.pvalue, [m["n3"] for _, m in pt], st.mannwhitneyu(a, b).pvalue))
try:
    import statsmodels.api as sm
    pt = [d for d in recs if d["g"] == "PTEN" and not d["why"]]
    y = np.array([measures(d)["n3"] for d in pt])
    X = sm.add_constant(np.array([d["ko"] for d in pt]))
    for nm, off in (("per minute", np.log([d["mins"] for d in pt])), ("per event", np.log([d["n"] for d in pt]))):
        mdl = sm.GLM(y, X, family=sm.families.NegativeBinomial(alpha=1.0), offset=off).fit()
        print("  negative binomial, DS3 count %s ~ %%KO: x%.2f per 1%% KO, p %.4f" % (nm, np.exp(mdl.params[1]), mdl.pvalues[1]))
    al = [d for d in recs if not d["why"]]
    y = np.array([measures(d)["n3"] for d in al])
    X = sm.add_constant(np.array([1.0 if d["g"] == "PTEN" else 0.0 for d in al]))
    mdl = sm.GLM(y, X, family=sm.families.NegativeBinomial(alpha=1.0), offset=np.log([d["mins"] for d in al])).fit()
    print("  negative binomial, DS3 per minute ~ PTEN: x%.2f, p %.3f" % (np.exp(mdl.params[1]), mdl.pvalues[1]))
except Exception as exc:
    print("  (no count model: %s)" % exc)

# Against the literature.
print("\nAgainst the literature (Tarcsay et al. 2025: DS1 0.09, DS2 0.18, DS3 0.10 Hz; DS3 sinks weaker):")
r1, r2, r3 = col("ds1_rate", lambda m: True) / 60, col("ds2_rate", lambda m: True) / 60, col("ds3_rate", lambda m: True) / 60
print("  here, mean rates (Hz): DS1 %.3f, DS2 %.3f, DS3 %.3f; medians %.3f / %.3f / %.3f" % (
    r1.mean(), r2.mean(), r3.mean(), np.median(r1), np.median(r2), np.median(r3)))
print("  DS2 rate above DS1 rate in %d of %d recordings (Wilcoxon p %.3f)" % ((r2 > r1).sum(), r1.size, st.wilcoxon(r2, r1).pvalue))
sr = col("ds3_sink_ratio", lambda m: True)
if sr.size >= 3:
    print("  DS3 sink / DS1-DS2 sink: median %.2f over %d recordings with 5+ DS3 (below 1 in %d); Wilcoxon vs 1 p %.3f" % (
        np.median(sr), sr.size, (sr < 1).sum(), st.wilcoxon(sr - 1).pvalue if sr.size >= 6 else float("nan")))
sh = col("ds3_share", lambda m: True)
print("  DS3 share: median %.1f%%, mean %.1f%% (Tarcsay's rates imply about 27%%)" % (100 * np.median(sh), 100 * sh.mean()))
si = col("si", lambda m: True)
print("  one family by the Bite line (SI under 0.2): %d of %d recordings; 'separate' (0.5+): %d" % ((si < 0.2).sum(), si.size, (si >= 0.5).sum()))
json.dump({"measures": M, "tests": [(t[0], t[1], t[2], float(t[3]), float(q[i])) for i, t in enumerate(tests)]},
          open(os.path.join(os.path.dirname(__file__), "ds3_battery.json"), "w"), default=str)
