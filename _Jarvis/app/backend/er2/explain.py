"""Opening a model (Extraction Room 2.0): which inputs carry its calls.

Four ways, all on held-out mice only (a mouse is explained by the fold
models that never saw it):

  permutation   replace one input (a family of inputs, or one feature) in the
                held-out mice with values from random other mice (pooled
                models) or random other events (set networks), redo the calls,
                and see how far the held-out score falls; 5 repeats
  shapley       Shapley values (Strumbelj & Kononenko sampling): how much each
                family -- and each of the 20 strongest features -- pushed each
                held-out mouse's call, with absent inputs set to the training
                mice's typical value
  drop family   retrain the whole test with one family left out; how far the
                score falls
  attention     (attention network) which events of a held-out mouse got the
                most weight, and which event features go with that weight

consolidate() turns many models' explanations into the MOST IMPORTANT list:
every method ranks its items, each rank becomes points (1 for first, falling
to 0 for last), and points are added over methods and models; an item is
listed with how many methods and models put it in their top ten.
"""
import numpy as np
from scipy import stats as st

N_REPEAT = 5
N_PERM_SHAP = 16
TOP_FEATURES = 60


def _score(engine, res, pred):
    return engine.score(res["task"], res["y"], pred, res["folds"], res["scheme"])["main"]


def _first_fold(res):
    """For each held-out mouse (position), the first fold that holds it out: (fold, slot)."""
    out = {}
    for f, held in enumerate(res["folds"]):
        for k, i in enumerate(held):
            out.setdefault(i, (f, k))
    return out


def explain(data, res, tgt, view, model, log=print, drop=True):
    from . import engine as E
    fitted = res["fitted"]
    base = res["score"]["main"]
    names, fams = fitted[0].feature_names()
    rng = np.random.default_rng(7)
    out = {"base": base}
    if not np.isfinite(base):
        return out
    famset = sorted(set(fams))
    fam_cols = {fm: np.array([i for i, x in enumerate(fams) if x == fm]) for fm in famset}

    def permuted(cols):
        drops = []
        for _ in range(N_REPEAT):
            pred = [fm.predict(res["mice"][np.array(h)], perm_cols=cols, rng=rng) for fm, h in zip(fitted, res["folds"])]
            drops.append(base - _score(E, res, pred))
        return float(np.mean(drops)), float(np.std(drops))

    # ---- permutation: families, then features
    out["perm_family"] = sorted(({"item": fm, "drop": permuted(c)[0]} for fm, c in fam_cols.items()), key=lambda d: -d["drop"])
    if model in E.POOLED:
        cnt = {}
        for fm in fitted:
            for c in fm.prep["sel"][:30]:
                cnt[c] = cnt.get(c, 0) + 1
        cand = sorted(cnt, key=lambda c: -cnt[c])[:TOP_FEATURES]
    else:
        top_fams = [d["item"] for d in out["perm_family"][:3]]
        cand = [i for fm in top_fams for i in fam_cols[fm]][:TOP_FEATURES * 2]
    pf = []
    for c in cand:
        m, s = permuted(np.array([c]))
        pf.append({"item": names[c], "family": fams[c], "drop": m, "sd": s})
    out["perm_feature"] = sorted(pf, key=lambda d: -d["drop"])
    log("   permutation: top family %s (%.3f), top feature %s (%.3f)" % (
        out["perm_family"][0]["item"], out["perm_family"][0]["drop"], out["perm_feature"][0]["item"] if pf else "-",
        out["perm_feature"][0]["drop"] if pf else 0))

    # ---- Shapley: families and the 20 strongest features (+ the rest as one player)
    first = _first_fold(res)
    task = res["task"]

    def call(fm, i, absent_cols):
        mouse = res["mice"][i]
        if model in E.POOLED:
            M = fm.M.copy()
            if absent_cols.size:
                M[mouse, absent_cols] = fm.prep["med"][absent_cols]
            v = fm.predict(np.array([mouse]), M_override=M)[0]
        else:
            v = fm.predict(np.array([mouse]), fill_cols=absent_cols)[0]
        if task == "multiclass":
            v = v[int(res["y"][i])]                 # the true class's probability
        return float(v)

    def shapley(players):
        allc = np.concatenate([p for p in players.values()]) if players else np.array([], int)
        keys = list(players)
        phi = {k: [] for k in keys}
        per_mouse = []
        for i, (f, _k) in sorted(first.items()):
            fm = fitted[f]
            acc = {k: 0.0 for k in keys}
            for _ in range(N_PERM_SHAP):
                order = rng.permutation(len(keys))
                present = []
                prev = call(fm, i, allc)
                for o in order:
                    present.append(keys[o])
                    absent = np.concatenate([players[k] for k in keys if k not in present] or [np.array([], int)])
                    cur = call(fm, i, absent.astype(int))
                    acc[keys[o]] += cur - prev
                    prev = cur
            sign = 1.0 if (task != "binary" or res["y"][i] == 1) else -1.0
            row = {k: acc[k] / N_PERM_SHAP for k in keys}
            per_mouse.append({"lab": data.labs[res["mice"][i]], "truth": float(res["y"][i]), "phi": row})
            for k in keys:
                phi[k].append(abs(row[k]))
        return sorted(({"item": k, "mean_abs": float(np.mean(v))} for k, v in phi.items()), key=lambda d: -d["mean_abs"]), per_mouse

    out["shap_family"], out["shap_family_by_mouse"] = shapley({fm: c for fm, c in fam_cols.items()})
    top = [names.index(d["item"]) for d in out["perm_feature"][:20]]
    rest = np.array([c for c in range(len(names)) if c not in top], int)
    players = {names[c]: np.array([c]) for c in top}
    if rest.size:
        players["(everything else)"] = rest
    out["shap_feature"], out["shap_feature_by_mouse"] = shapley(players)
    log("   shapley: top family %s, top feature %s" % (out["shap_family"][0]["item"], out["shap_feature"][0]["item"]))

    # ---- drop one family (retrain)
    if drop and len(famset) > 1:
        dl = []
        for fm in famset:
            try:
                r2 = E.run_cv(data, tgt, view, model, drop_family=fm)
                dl.append({"item": fm, "drop": float(base - r2["score"]["main"])})
            except ValueError:
                continue
        out["drop_family"] = sorted(dl, key=lambda d: -d["drop"])
        if dl:
            log("   drop one family: largest fall %s (%.3f)" % (out["drop_family"][0]["item"], out["drop_family"][0]["drop"]))

    # ---- attention weights
    if model == "attention":
        rho_acc, tops = {}, []
        for i, (f, _k) in sorted(first.items()):
            fm = fitted[f]
            mouse = res["mice"][i]
            w, _bg = fm.weights(np.array([mouse]))
            ev = np.where(data.bag == mouse)[0]
            X = data.X[ev][:, fm.ecols]
            for j in range(X.shape[1]):
                x = X[:, j]
                ok = np.isfinite(x)
                if ok.sum() >= 10 and np.ptp(x[ok]) > 0:
                    rho_acc.setdefault(j, []).append(st.spearmanr(w[ok], x[ok]).correlation)
            o = np.argsort(-w)[:5]
            tops.append({"lab": data.labs[mouse], "events": [int(e) for e in ev[o]], "weights": [float(x) for x in w[o]],
                         "flat_weight": 1.0 / max(ev.size, 1)})
        att = [{"item": names[j], "family": fams[j], "mean_rho": float(np.nanmean(v)), "n_mice": len(v)} for j, v in rho_acc.items()]
        out["attention_feature"] = sorted(att, key=lambda d: -abs(d["mean_rho"]))[:TOP_FEATURES]
        out["attention_top_events"] = tops
    return out


def _points(lst, key="item"):
    n = len(lst)
    return {d[key]: 1.0 - (r / float(max(n - 1, 1))) for r, d in enumerate(lst)} if n else {}


def base_measure(name):
    """'sink_amp|median' -> 'sink_amp'; 'f_none__sink_pre|iqr' -> 'f_none__sink_pre'; mouse features unchanged."""
    return name.split("|")[0] if "|" in name and not name.startswith(("battery", "waveform", "laminar", "timing", "structure", "around", "nuisance")) else name


def consolidate(results, top_n=40):
    """The MOST IMPORTANT list, over the explained leaderboard entries given."""
    fam_pts, feat_pts, meas_pts = {}, {}, {}
    fam_hits, feat_hits = {}, {}
    used = []
    for r in results:
        ex = r.get("explain") or {}
        tag = "%s / %s / %s" % (r["target"], r["view"], r["model"])
        used.append(tag)
        for meth in ("perm_family", "shap_family", "drop_family"):
            lst = ex.get(meth) or []
            for k, p in _points(lst).items():
                fam_pts[k] = fam_pts.get(k, 0.0) + p
            for d in lst[:3]:
                fam_hits.setdefault(d["item"], set()).add((meth, tag))
        for meth in ("perm_feature", "shap_feature", "attention_feature"):
            lst = [d for d in (ex.get(meth) or []) if d["item"] != "(everything else)"]
            for k, p in _points(lst).items():
                feat_pts[k] = feat_pts.get(k, 0.0) + p
                b = base_measure(k)
                meas_pts[b] = meas_pts.get(b, 0.0) + p
            for d in lst[:10]:
                feat_hits.setdefault(d["item"], set()).add((meth, tag))
    n = max(len(used), 1)

    def table(pts, hits):
        rows = []
        for k, p in sorted(pts.items(), key=lambda kv: -kv[1])[:top_n]:
            h = hits.get(k, set())
            rows.append({"item": k, "points": round(p / n, 3), "n_methods": len({m for m, _ in h}), "n_models": len({t for _, t in h})})
        return rows
    return {"models": used, "families": table(fam_pts, fam_hits), "features": table(feat_pts, feat_hits),
            "measures": [{"item": k, "points": round(p / n, 3)} for k, p in sorted(meas_pts.items(), key=lambda kv: -kv[1])[:top_n]]}
