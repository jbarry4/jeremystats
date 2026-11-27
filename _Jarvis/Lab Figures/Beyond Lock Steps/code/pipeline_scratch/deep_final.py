"""The numbers the figures draw: sixteen measures chosen for what they mean
(not for their p), effect sizes with bootstrap intervals, one global test
(can a recording's group be told from its dentate spikes, leaving that
animal out), the chance level of the whole search, and what n a real test
of the best lead would need."""
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
import deep_stats2 as D2  # noqa: E402

PANEL = [("rate", "Event rate"), ("lfp_amp", "LFP amplitude"), ("lfp_ms", "LFP half-width"), ("sink_ms", "Sink duration"),
         ("sink_width", "Sink width (depth)"), ("blade_um", "Blade-to-blade distance"), ("amp_cv", "Amplitude variability"),
         ("iei_cv", "Irregularity (CV of intervals)"), ("burst", "Events within 1 s of another"),
         ("si_best2", "Separation of best split"), ("vote_agree", "Agreement across splits"),
         ("ds3_share_si", "Hybrid (DS3) share"), ("sink_asym", "Upper vs lower blade sink"), ("src_net", "Granule-layer source / sinks"),
         ("lfp_at_src", "LFP at source / at sinks")]


def boot(fn, n, B=4000, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(B):
        v = fn(rng)
        if v is not None and np.isfinite(v):
            out.append(v)
    return np.percentile(out, [2.5, 97.5])


def main():
    out = {}
    for V in (6, 8):
        M = D2.table(V)
        use = [m for m in M if m["n"] >= DS.MIN_N]
        g = np.array([m["g"] == "PTEN" for m in use])
        ko = np.array([m["ko"] for m in use])
        rows = []
        for key, name in PANEL:
            v = np.array([np.nan if m.get(key) is None else float(m[key]) for m in use])
            ok = np.isfinite(v)
            a, b = v[ok & ~g], v[ok & g]
            U = st.mannwhitneyu(b, a, alternative="two-sided")
            rb = 2 * U.statistic / (a.size * b.size) - 1

            def f_rb(rng):
                aa, bb = rng.choice(a, a.size), rng.choice(b, b.size)
                return 2 * st.mannwhitneyu(bb, aa).statistic / (a.size * b.size) - 1
            kk, vv = ko[ok & g], v[ok & g]
            rho = st.spearmanr(kk, vv)

            def f_rho(rng):
                i = rng.integers(0, kk.size, kk.size)
                if np.unique(kk[i]).size < 3 or np.unique(vv[i]).size < 3:
                    return None
                return st.spearmanr(kk[i], vv[i]).correlation
            ra = st.spearmanr(ko[ok], v[ok])
            rows.append({"key": key, "name": name, "rb": rb, "rb_ci": boot(f_rb, 0), "p_group": U.pvalue, "na": int(a.size), "nb": int(b.size),
                         "rho": rho.correlation, "rho_ci": boot(f_rho, 0, 3000), "p_dose": rho.pvalue,
                         "rho_all": ra.correlation, "p_all": ra.pvalue})
        ps = np.array([r["p_group"] for r in rows] + [r["p_dose"] for r in rows])
        order = np.argsort(ps)
        q = np.empty(ps.size)
        prev = 1.0
        for rank, i in enumerate(order[::-1]):
            prev = min(prev, ps[i] * ps.size / (ps.size - rank))
            q[i] = prev
        for i, r in enumerate(rows):
            r["q_group"], r["q_dose"] = float(q[i]), float(q[len(rows) + i])
        print("\n=== v%d: 16 measures (BH over the 32 group and dose tests) ===" % V)
        for r in rows:
            print("  %-32s group r %+.2f [%+.2f, %+.2f] p %.3f q %.2f | dose rho %+.2f [%+.2f, %+.2f] p %.3f q %.2f | all rho %+.2f p %.3f" % (
                r["name"], r["rb"], r["rb_ci"][0], r["rb_ci"][1], r["p_group"], r["q_group"], r["rho"], r["rho_ci"][0], r["rho_ci"][1],
                r["p_dose"], r["q_dose"], r["rho_all"], r["p_all"]))
        # One global test: tell the group from the sixteen, leaving each animal out.
        from sklearn.linear_model import LogisticRegression, Ridge
        X = np.array([[np.nan if m.get(k) is None else float(m[k]) for k, _ in PANEL] for m in use])

        def loo(y, model):
            pred = np.zeros(len(y))
            for i in range(len(y)):
                tr = np.arange(len(y)) != i
                mu = np.nanmedian(X[tr], axis=0)
                Xt = np.where(np.isfinite(X), X, mu)
                sd = Xt[tr].std(axis=0) + 1e-9
                Z = (Xt - Xt[tr].mean(axis=0)) / sd
                mdl = model().fit(Z[tr], y[tr])
                pred[i] = mdl.predict_proba(Z[i:i + 1])[0, 1] if hasattr(mdl, "predict_proba") else mdl.predict(Z[i:i + 1])[0]
            return pred

        def auc(y, p):
            return st.mannwhitneyu(p[y == 1], p[y == 0]).statistic / ((y == 1).sum() * (y == 0).sum())
        y = g.astype(int)
        mk = lambda: LogisticRegression(C=0.3, max_iter=2000)
        a_obs = auc(y, loo(y, mk))
        rng = np.random.default_rng(11)
        a_null = np.array([(lambda yy: auc(yy, loo(yy, mk)))(rng.permutation(y)) for _ in range(500)])
        mr = lambda: Ridge(alpha=5.0)
        pk = loo(ko, mr)
        r_obs = st.spearmanr(ko, pk).correlation
        r_null = np.array([(lambda kk_: st.spearmanr(kk_, loo(kk_, mr)).correlation)(rng.permutation(ko)) for _ in range(500)])
        print("  group from the 16, each animal left out: AUC %.2f, permutation p %.3f" % (a_obs, float((a_null >= a_obs).mean())))
        print("  knockout from the 16, each animal left out: rho %.2f, permutation p %.3f" % (r_obs, float((r_null >= r_obs).mean())))
        out[V] = {"M": M, "rows": rows, "auc": a_obs, "auc_null": a_null, "kofit": r_obs, "kofit_null": r_null, "ko_pred": pk,
                  "labs": [m["lab"] for m in use], "g": g, "ko": ko}
    # The search's chance level (v6, every measure looked at).
    M = out[6]["M"]
    allkeys = sorted({k for m in M for k, v in m.items() if isinstance(v, (int, float)) and k not in ("ko", "n")})
    T = D2.tests_of(M, allkeys)
    n_use = sum(1 for m in M if m["n"] >= DS.MIN_N)
    rng = np.random.default_rng(7)
    mins = np.array([min(v[0] for v in D2.tests_of(M, allkeys, rng.permutation(n_use)).values()) for _ in range(1000)])
    best = min(T.items(), key=lambda kv: kv[1][0])
    out["family"] = {"n_tests": len(T), "n_measures": len(allkeys), "mins": mins, "best": (best[0], best[1][0]),
                     "fw_p": float((mins <= best[1][0]).mean()), "ps": np.array(sorted(v[0] for v in T.values()))}
    print("\nfamily: %d tests, best %s p %.4f, family-wise p %.3f" % (len(T), best[0], best[1][0], out["family"]["fw_p"]))
    # What a real test of the source lead would need (group contrast, v6).
    use = [m for m in M if m["n"] >= DS.MIN_N]
    a = np.array([m["src_net"] for m in use if m["g"] == "CTL"])
    b = np.array([m["src_net"] for m in use if m["g"] == "PTEN"])
    hi = np.array([m["src_net"] for m in use if m["g"] == "PTEN" and m["ko"] >= 15])
    for nm, bb in (("all PTEN", b), ("PTEN 15%+ knockout", hi)):
        dd = (a.mean() - bb.mean()) / np.sqrt((a.var(ddof=1) + bb.var(ddof=1)) / 2)
        rng = np.random.default_rng(3)
        need = None
        for n in range(4, 61):
            hits = 0
            for _ in range(1500):
                x, y_ = rng.normal(0, 1, n), rng.normal(-dd, 1, n)
                hits += st.mannwhitneyu(x, y_).pvalue < 0.05
            if hits / 1500 >= 0.8:
                need = n
                break
        print("  source/sinks, CTL vs %s: d %.2f (n %d vs %d), Mann-Whitney p %.3f; 80%% power at alpha 0.05 needs %s a group" % (
            nm, dd, a.size, bb.size, st.mannwhitneyu(a, bb).pvalue, need))
        out.setdefault("power", {})[nm] = {"d": float(dd), "need": need, "p": float(st.mannwhitneyu(a, bb).pvalue)}
    with open(os.path.join(HERE, "deep_final.pkl"), "wb") as f:
        pickle.dump(out, f)


if __name__ == "__main__":
    main()
