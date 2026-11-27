"""The leads from deep_stats.py, pressed: the granule-layer source against
the blade sinks measured six ways on the whole shank; the best split per
animal on the shared yardstick (SI); the vote across methods; and what the
whole 153-test family gives by chance (max-statistic permutation)."""
import json
import os
import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
import numpy as np  # noqa: E402
from scipy import stats as st  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deep_stats as DS  # noqa: E402

BOTH = ("bite", "pca", "pca_gap", "delta", "delta_mid")
RENAME = {"rate": "Event rate", "lfp_amp": "LFP amplitude", "lfp_ms": "LFP width (FWHM)", "sink_ms": "Sink duration (FWHM)",
          "sink_width": "Sink spatial width (FWHM)", "blade_um": "Distance between blade sinks", "amp_cv": "LFP amplitude CV",
          "iei_cv": "CV of inter-event intervals", "burst": "Inter-event intervals under 1 s", "si_best2": "DS1–DS2 separation index",
          "vote_agree": "Agreement between classifiers", "ds3_share_si": "DS3 share of events",
          "sink_asym": "Sink asymmetry, upper − lower blade", "src_net": "Source/sink ratio, granule layer",
          "lfp_at_src": "LFP ratio, granule layer / blades"}


def rename(rows):
    for r in rows:
        r["name"] = RENAME.get(r["key"], r["name"])
    return rows


def geometry(d, F):
    """The two blade sinks and the source between, on the recording's mean
    DS (CSD, +-3 ms). Rows are whole-shank rows."""
    na = F["nums_all"]
    m = F["csd_at0"].mean(axis=0)
    a, b = na.index(d["ns"][0]), na.index(d["ns"][-1])
    hc = d["hump_cut"]
    if hc is None:
        return None
    cut = a + hc
    s1 = a + int(np.argmin(m[a:cut]))
    s2 = cut + int(np.argmin(m[cut:b + 1]))
    if s2 - s1 < 2:
        return None
    src = s1 + 1 + int(np.argmax(m[s1 + 1:s2]))
    return s1, s2, src


def source_measures(d, F):
    g = geometry(d, F)
    if g is None:
        return {}
    s1, s2, src = g
    ev = F["csd_at0"].astype(float)
    m = ev.mean(axis=0)
    o = {"blade_um": (s2 - s1) * 50.0}
    sk = (-m[s1] - m[s2]) / 2.0
    o["src_peak_mean"] = m[src] / sk
    seg = m[s1:s2 + 1]
    o["src_area_mean"] = np.maximum(seg, 0).sum() / max(np.maximum(-seg, 0).sum(), 1e-12)
    es = np.maximum(ev[:, s1 + 1:s2], 0).max(axis=1)
    ek = (np.maximum(-ev[:, s1], 0) + np.maximum(-ev[:, s2], 0)) / 2.0
    ok = ek > 0
    o["src_peak_event"] = float(np.median(es[ok] / ek[ok]))
    segs = ev[:, s1:s2 + 1]
    o["src_area_event"] = float(np.median(np.maximum(segs, 0).sum(axis=1) / np.maximum(np.maximum(-segs, 0).sum(axis=1), 1e-12)))
    # the source as a share of everything between the blades, sign kept
    o["src_net"] = float(seg[1:-1].mean() / sk)
    # in the LFP: how much of the DS is left at the source contact
    nl = F["nums_lfp"]
    lf = F["lfp_at0"].mean(axis=0)
    try:
        o["lfp_at_src"] = float(lf[nl.index(F["nums_all"][src])] / lf[[nl.index(F["nums_all"][s1]), nl.index(F["nums_all"][s2])]].mean())
    except Exception:  # noqa: BLE001
        pass
    o["sink_asym"] = float((-m[s1] + m[s2]) / (-m[s1] - m[s2]))
    return o


def best_si(d):
    ok = [(m, e) for m, e in d["splits"].items() if "err" not in e and e.get("si") is not None
          and min(e["n1"], e["n2"]) >= max(5, 0.05 * d["n"])]
    if not ok:
        return None, None
    return max(ok, key=lambda p: p[1]["si"])


def split_measures(d):
    o = {}
    mins = d["dur"] / 60.0
    m, e = best_si(d)
    o["best_si_method"] = m
    if e is not None:
        ty = e["types"]
        o.update(si_best2=e["si"], ds1_share_si=float((ty == 1).mean()), ds1_rate_si=float((ty == 1).sum() / mins),
                 ds2_rate_si=float((ty == 2).sum() / mins))
        if not e.get("why"):
            sc = e["score"]
            okk = np.isfinite(sc)
            o["ds3_share_si"] = float((np.abs(sc[okk]) <= 0.5).sum() / d["n"])
            o["oml_mml_si"] = abs(e["oml"] - e["mml"]) * 50.0
    # the vote of the five whole-band methods
    T = np.array([d["splits"][k]["types"] for k in BOTH if "err" not in d["splits"][k]])
    if T.shape[0] >= 4:
        v1 = (T == 1).mean(axis=0)
        o["vote_ambig"] = float(((v1 > 0.2) & (v1 < 0.8)).mean())
        o["vote_ds1"] = float((v1 >= 0.8).mean())
        o["vote_ds1_rate"] = float((v1 >= 0.8).sum() / mins)
        o["vote_ds2_rate"] = float((v1 <= 0.2).sum() / mins)
        o["vote_agree"] = float(np.mean(np.maximum(v1, 1 - v1)))
    for k in BOTH:
        e = d["splits"].get(k, {})
        if "err" not in e:
            o["ds1_share_" + k] = float((e["types"] == 1).mean())
            o["ds1_rate_" + k] = float((e["types"] == 1).sum() / mins)
    return o


def table(V):
    recs = pickle.load(open(os.path.join(HERE, "deep_v%d.pkl" % V), "rb"))
    full = pickle.load(open(os.path.join(HERE, "deep_full_v%d.pkl" % V), "rb"))
    M = []
    for d in recs:
        o = DS.measures(d)
        o.update(source_measures(d, full[d["gid"]]))
        o.update(split_measures(d))
        M.append(o)
    return M


def tests_of(M, keys, perm=None):
    """group / dose / all for each key; `perm` reorders the animals'
    (group, knockout) labels."""
    use = [m for m in M if m["n"] >= DS.MIN_N]
    g = np.array([m["g"] == "PTEN" for m in use])
    ko = np.array([m["ko"] for m in use])
    if perm is not None:
        g, ko = g[perm], ko[perm]
    out = {}
    for key in keys:
        v = np.array([np.nan if m.get(key) is None else float(m.get(key)) for m in use])
        ok = np.isfinite(v)
        a, b = v[ok & ~g], v[ok & g]
        if min(a.size, b.size) < 5:
            continue
        out[("group", key)] = (st.mannwhitneyu(a, b, alternative="two-sided").pvalue, np.median(b) - np.median(a))
        r = st.spearmanr(ko[ok & g], v[ok & g])
        out[("dose", key)] = (r.pvalue, r.correlation)
        r = st.spearmanr(ko[ok], v[ok])
        out[("all", key)] = (r.pvalue, r.correlation)
    return out


if __name__ == "__main__":
    res = {}
    for V in (6, 8):
        M = table(V)
        res[V] = M
        print("\n=== v%d, per animal ===" % V)
        print("  %-5s %-4s %5s %4s | %7s %7s %7s %7s %7s %6s | %-16s %5s %5s %5s | %5s %5s" % (
            "", "", "KO", "n", "pk_mean", "ar_mean", "pk_ev", "ar_ev", "net", "blade", "best SI split", "SI", "DS1%", "DS3%", "ambig", "agree"))
        for m in M:
            f = lambda k, s="%7.2f": (s % m[k]) if m.get(k) is not None and np.isfinite(m.get(k)) else " " * (int(s[1]) - 1) + "-"
            print("  %-5s %-4s %5.1f %4d | %s %s %s %s %s %6s | %-16s %s %s %s | %s %s" % (
                m["lab"], m["g"], m["ko"], m["n"], f("src_peak_mean"), f("src_area_mean"), f("src_peak_event"), f("src_area_event"),
                f("src_net"), f("blade_um", "%6.0f"), m.get("best_si_method"), f("si_best2", "%5.2f"),
                f("ds1_share_si", "%5.2f"), f("ds3_share_si", "%5.2f"), f("vote_ambig", "%5.2f"), f("vote_agree", "%5.2f")))
        keys = ["src_peak_mean", "src_area_mean", "src_peak_event", "src_area_event", "src_net", "lfp_at_src", "blade_um", "sink_asym",
                "si_best2", "ds1_share_si", "ds1_rate_si", "ds2_rate_si", "ds3_share_si", "vote_ambig", "vote_ds1", "vote_ds1_rate",
                "vote_ds2_rate", "vote_agree"] + ["ds1_share_" + k for k in BOTH] + ["ds1_rate_" + k for k in BOTH]
        T = tests_of(M, keys)
        for k, (p, e) in sorted(T.items(), key=lambda kv: kv[1][0])[:26]:
            print("  p %.4f  %-6s %-18s eff %+.2f" % (p, k[0], k[1], e))
    # What the whole family gives by chance: the smallest p of all the tests
    # when the animals' labels are shuffled (v6).
    M = res[6]
    allkeys = sorted({k for m in M for k, v in m.items() if isinstance(v, (int, float)) and k not in ("ko", "n")})
    T = tests_of(M, allkeys)
    obs = sorted(T.items(), key=lambda kv: kv[1][0])
    n_use = sum(1 for m in M if m["n"] >= DS.MIN_N)
    rng = np.random.default_rng(7)
    NP = 600
    mins = np.array([min(v[0] for v in tests_of(M, allkeys, rng.permutation(n_use)).values()) for _ in range(NP)])
    print("\n=== the whole family on v6: %d tests over %d measures ===" % (len(T), len(allkeys)))
    print("  smallest p by chance (shuffled labels): median %.4f, 5th percentile %.4f" % (np.median(mins), np.percentile(mins, 5)))
    for k, (p, e) in obs[:8]:
        print("  %-6s %-18s p %.4f eff %+.2f  family-wise p %.3f" % (k[0], k[1], p, e, float((mins <= p).mean())))
    json.dump({str(V): res[V] for V in res}, open(os.path.join(HERE, "deep_measures2.json"), "w"), default=str)
