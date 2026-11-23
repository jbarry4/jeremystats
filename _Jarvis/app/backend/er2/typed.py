"""DS-type questions for Extraction Room 2.0 (asked 2026-11-20).

Two things, added beside the original grid (which is unchanged and can be run
again as before):

1. THE SAME GROUP MODELS, ONE DS TYPE AT A TIME. A view written "core@ds1"
   is the view "core" seeing only that mouse's DS1 events (DS3 already taken
   out of DS1 and DS2, as in the battery). Subsets:
     ds1, ds2, ds3        the events of that type
     twin1, twin2, twin3  the same NUMBER of events as that type, drawn at
                          random from all of the mouse's events (a fixed draw):
                          the yardstick. A type only "carries" a difference
                          if it beats its own twin, so fewer events cannot
                          pass for less information.
   A mouse with fewer than 5 events in the subset sits that target out.
   A view written "contrast:core" gives the pooled models one row per mouse
   of DS1 minus DS2 (each feature's median over DS1 events minus over DS2
   events), plus the DS1 / DS2 count ratio: does the RELATION between the
   types differ by group. Mice need 5 events of each type.

2. TELLING DS1 FROM DS2 (target "ds1_vs_ds2"). One call per EVENT, DS1 (1)
   against DS2 (0), DS3 left out; every recording with types ("give it
   everything"); tested on mice the model never saw (leave one mouse out).
   Score: the AUC within each held-out mouse, averaged over mice with 5 or
   more of each type (the pooled AUC over all held-out events is kept too).
   The types were named by the winning classifier from the depth profile of
   the CSD, so the views that include that profile are expected to score
   near 1 (a check that the machinery works); the question is what is left
   without it:
     everything     every event feature
     shape          waveform / depth measures + the six filter copies
     raw_wave       the raw CSD and LFP on the blade-to-blade axis
     no_shape       everything except the shape of the DS: context, before /
                    after power, the raw spectrogram
     context        interval before / after, time in recording, peak, theta
     before_after   power before / after the DS (measures)
     spectrogram    the raw spectrogram (7 bands x depth x +-500 ms)
"""
import time

import numpy as np
from scipy import stats as st

TYPE12_VIEWS = ("everything", "shape", "raw_wave", "no_shape", "context", "before_after", "spectrogram")
TYPE12_MODELS = ("linear", "lasso", "forest", "boosting", "mlp")
SUBSETS = ("ds1", "ds2", "ds3")
TWINS = ("twin1", "twin2", "twin3")
GROUP_VIEWS = ("core", "context", "filters", "before_after", "events_all", "everything", "raw")
CONTRAST_VIEWS = ("core", "context", "filters", "before_after", "events_all", "raw")
MIN_EV = 5
K_EVENT = 400


def parse_view(view):
    """'core@ds1' -> ('core', 'ds1', False); 'contrast:core' -> ('core', None, True)."""
    if view.startswith("contrast:"):
        return view.split(":", 1)[1], None, True
    if "@" in view:
        b, s = view.split("@", 1)
        return b, s, False
    return view, None, False


def _type_masks(data):
    return {k: data.X[:, data.efeat.index("type_" + k)] > 0.5 for k in ("ds1", "ds2", "ds3")}


def restrict(data, subset, seed=0):
    """A copy of the bundle holding only the subset's events; data.keep marks
    the mice with MIN_EV or more of them."""
    tm = _type_masks(data)
    if subset in tm:
        ev = tm[subset]
    elif subset in TWINS:
        want = tm["ds" + subset[-1]]
        rng = np.random.default_rng(1234 + seed)
        ev = np.zeros(data.bag.size, bool)
        for m in range(len(data.mice)):
            idx = np.where(data.bag == m)[0]
            n = int(want[idx].sum())
            if n:
                ev[rng.choice(idx, min(n, idx.size), replace=False)] = True
    else:
        raise ValueError("unknown subset %s" % subset)
    d = _copy(data)
    d.X, d.bag = data.X[ev], data.bag[ev]
    d.keep = np.array([(d.bag == m).sum() >= MIN_EV for m in range(len(data.mice))])
    d.subset = subset
    d._pooled = None
    return d


def contrast(data):
    """A copy whose pooled table is DS1 minus DS2 per mouse."""
    tm = _type_masks(data)
    nm = len(data.mice)
    n1 = np.array([(tm["ds1"] & (data.bag == m)).sum() for m in range(nm)])
    n2 = np.array([(tm["ds2"] & (data.bag == m)).sum() for m in range(nm)])
    keep = (n1 >= MIN_EV) & (n2 >= MIN_EV)
    cols, names, fams, base = [], [], [], []
    for j, f in enumerate(data.efeat):
        if f.startswith("type_"):
            continue
        x = data.X[:, j]
        v = np.full(nm, np.nan)
        for m in np.where(keep)[0]:
            a = x[tm["ds1"] & (data.bag == m)]
            b = x[tm["ds2"] & (data.bag == m)]
            a, b = a[np.isfinite(a)], b[np.isfinite(b)]
            if a.size >= MIN_EV and b.size >= MIN_EV:
                v[m] = np.median(a) - np.median(b)
        cols.append(v)
        names.append("%s|ds1-ds2" % f)
        fams.append(data.efam[j])
        base.append(j)
    j0 = data.efeat.index("type_ds1")
    cols.append(np.where(keep, np.log2(np.maximum(n1, 1) / np.maximum(n2, 1)), np.nan))
    names.append("count|log2 ds1/ds2")
    fams.append("ds type")
    base.append(j0)
    d = _copy(data)
    d._pooled = (np.column_stack(cols), names, fams, np.array(base))
    d.keep = keep
    d.subset = "contrast"
    return d


def _copy(data):
    d = object.__new__(type(data))
    d.__dict__.update(data.__dict__)
    return d


# ------------------------------------------------------------------ DS1 against DS2, per event
def type12_cols(data, view):
    fam = np.array(data.efam).astype(str)
    shape = (fam == "waveform/depth") | np.char.startswith(fam, "filter")
    rawwave = (fam == "raw CSD") | (fam == "raw LFP")
    spec = fam == "raw spectrogram"
    ctx = fam == "context"
    ba = np.char.startswith(fam, "before/after")
    m = {"everything": np.ones(fam.size, bool), "shape": shape, "raw_wave": rawwave, "no_shape": ctx | ba | spec,
         "context": ctx, "before_after": ba, "spectrogram": spec}[view]
    m &= fam != "ds type"                      # the label itself is never an input
    return np.where(m)[0]


def _event_model(model, seed):
    from sklearn import ensemble, linear_model, neural_network
    return {"linear": lambda: linear_model.LogisticRegression(C=0.05, max_iter=5000, class_weight="balanced"),
            "lasso": lambda: linear_model.LogisticRegression(C=0.05, penalty="l1", solver="saga", max_iter=5000, class_weight="balanced"),
            "forest": lambda: ensemble.RandomForestClassifier(400, min_samples_leaf=5, max_features="sqrt", class_weight="balanced_subsample",
                                                              random_state=seed, n_jobs=1),
            "boosting": lambda: ensemble.HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                                                        l2_regularization=1.0, class_weight="balanced", random_state=seed),
            "mlp": lambda: neural_network.MLPClassifier(hidden_layer_sizes=(64, 32), alpha=1e-2, early_stopping=True, max_iter=500,
                                                        random_state=seed)}[model]()


class EventFit(object):
    """One fold: fill, scale and screen on the training events only."""

    def __init__(self, X, y, model, seed):
        med = np.nanmedian(X, axis=0)
        self.med = np.where(np.isfinite(med), med, 0.0)
        Xf = np.where(np.isfinite(X), X, self.med)
        self.mu, sd = Xf.mean(axis=0), Xf.std(axis=0)
        self.sd = np.where(sd > 1e-12, sd, 1.0)
        Z = np.clip((Xf - self.mu) / self.sd, -6, 6)
        ok = sd > 1e-12
        r = np.zeros(X.shape[1])
        if ok.any():
            R = np.apply_along_axis(st.rankdata, 0, Z[:, ok])
            ry = st.rankdata(y)
            R -= R.mean(axis=0)
            ry -= ry.mean()
            den = np.sqrt((R ** 2).sum(axis=0) * (ry ** 2).sum())
            r[ok] = np.abs(np.where(den > 0, (R * ry[:, None]).sum(axis=0) / np.where(den > 0, den, 1), 0.0))
        self.sel = np.argsort(-r)[:min(K_EVENT, int(ok.sum()))]
        self.est = _event_model(model, seed).fit(Z[:, self.sel], y)

    def z(self, X):
        Xf = np.where(np.isfinite(X), X, self.med)
        return np.clip((Xf - self.mu) / self.sd, -6, 6)[:, self.sel]

    def proba(self, X):
        return self.est.predict_proba(self.z(X))[:, 1]


def _auc(y, p):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p)) if 0 < y.sum() < y.size else np.nan


def type12_cv(data, view, model, seed=0, cols=None):
    tm = _type_masks(data)
    ev = tm["ds1"] | tm["ds2"]
    cols = type12_cols(data, view) if cols is None else cols
    X, y, bag = data.X[ev][:, cols], tm["ds1"][ev].astype(int), data.bag[ev]
    mice = [m for m in np.unique(bag) if 0 < y[bag == m].sum() < (bag == m).sum()]
    pred = np.full(y.size, np.nan)
    fits = {}
    for f, m in enumerate(mice):
        tr, te = bag != m, bag == m
        fit = EventFit(X[tr], y[tr], model, seed + f)
        pred[te] = fit.proba(X[te])
        fits[m] = fit
    return {"X": X, "y": y, "bag": bag, "mice": mice, "pred": pred, "fits": fits, "cols": cols}


def type12_score(res, pred=None):
    p = res["pred"] if pred is None else pred
    y, bag = res["y"], res["bag"]
    per = {}
    for m in res["mice"]:
        s = bag == m
        if y[s].sum() >= MIN_EV and (1 - y[s]).sum() >= MIN_EV:
            per[int(m)] = _auc(y[s], p[s])
    vals = [v for v in per.values() if np.isfinite(v)]
    ok = np.isfinite(p)
    return {"main": float(np.mean(vals)) if vals else np.nan, "auc_pooled": _auc(y[ok], p[ok]), "per_mouse": per,
            "n_mice_scored": len(vals), "n_events": int(ok.sum())}


def run_type12(spec, Data, log=print):
    t0 = time.time()
    data = Data(spec.get("amber_version"), spec.get("amber_root"))
    view, model = spec["view"], spec["model"]
    res = type12_cv(data, view, model, seed=int(spec.get("seed", 0)))
    sc = type12_score(res)
    names = [data.efeat[c] for c in res["cols"]]
    fams = [data.efam[c] for c in res["cols"]]
    out = {"target": "ds1_vs_ds2", "view": view, "model": model, "amber_version": data.man["version"], "task": "binary", "scheme": "loo_events",
           "score": sc, "passes": bool(np.isfinite(sc["main"]) and sc["main"] >= 0.80), "bar": 0.80, "n_folds": len(res["mice"]),
           "per_mouse": [{"lab": data.labs[m], "auc": v, "n_ds1": int(res["y"][res["bag"] == m].sum()),
                          "n_ds2": int((1 - res["y"][res["bag"] == m]).sum())} for m, v in sc["per_mouse"].items()],
           "n_columns": len(names)}
    log("ds1_vs_ds2 %s %s: mean within-mouse AUC %.3f (pooled %.3f) over %d mice" % (view, model, sc["main"], sc["auc_pooled"], sc["n_mice_scored"]))
    if spec.get("explain", True) and np.isfinite(sc["main"]):
        out["explain"] = explain_type12(data, res, sc["main"], names, fams, model, drop=bool(spec.get("drop", True)), log=log)
    out["seconds"] = round(time.time() - t0, 1)
    return out


def explain_type12(data, res, base, names, fams, model, drop=True, log=print):
    """What tells DS1 from DS2: permutation (families, then features) on the
    held-out events, retraining without each family, and for the strongest
    features which way they lean (DS1 against DS2, within each mouse)."""
    rng = np.random.default_rng(7)
    X, bag = res["X"], res["bag"]
    famset = sorted(set(fams))
    fam_cols = {f: np.array([i for i, x in enumerate(fams) if x == f]) for f in famset}

    def permuted(cols, reps=3):
        drops = []
        for _ in range(reps):
            p = np.full(res["y"].size, np.nan)
            for m, fit in res["fits"].items():
                te = np.where(bag == m)[0]
                Xt = X[te].copy()
                donor = rng.integers(0, X.shape[0], size=te.size)
                Xt[:, cols] = X[donor][:, cols]              # values of random events of any mouse
                p[te] = fit.proba(Xt)
            drops.append(base - type12_score(res, p)["main"])
        return float(np.mean(drops))
    out = {"base": base}
    out["perm_family"] = sorted(({"item": f, "drop": permuted(c)} for f, c in fam_cols.items()), key=lambda d: -d["drop"])
    cnt = {}
    for fit in res["fits"].values():
        for c in fit.sel[:40]:
            cnt[c] = cnt.get(c, 0) + 1
    cand = sorted(cnt, key=lambda c: -cnt[c])[:40]
    pf = [{"item": names[c], "family": fams[c], "drop": permuted(np.array([c]), reps=2)} for c in cand]
    out["perm_feature"] = sorted(pf, key=lambda d: -d["drop"])
    # which way: per mouse, median over DS1 minus over DS2 (in SD units of that mouse), for the top features
    lean = []
    for d in out["perm_feature"][:20]:
        c = names.index(d["item"])
        diffs = []
        for m in res["mice"]:
            s = bag == m
            a, b = X[s & (res["y"] == 1), c], X[s & (res["y"] == 0), c]
            a, b = a[np.isfinite(a)], b[np.isfinite(b)]
            sd = np.nanstd(X[s, c])
            if a.size >= MIN_EV and b.size >= MIN_EV and sd > 0:
                diffs.append((np.median(a) - np.median(b)) / sd)
        if diffs:
            lean.append({"item": d["item"], "family": d["family"], "ds1_minus_ds2_sd": float(np.median(diffs)),
                         "share_mice_ds1_higher": float(np.mean(np.array(diffs) > 0)), "n_mice": len(diffs)})
    out["lean"] = lean
    log("   top family %s (%.3f), top feature %s" % (out["perm_family"][0]["item"], out["perm_family"][0]["drop"],
                                                     out["perm_feature"][0]["item"] if pf else "-"))
    if drop and len(famset) > 1:
        dl = []
        for f in famset:
            keep = np.array([i for i, x in enumerate(fams) if x != f])
            r2 = type12_cv(data, None, model, cols=res["cols"][keep])
            dl.append({"item": f, "drop": float(base - type12_score(r2)["main"])})
        out["drop_family"] = sorted(dl, key=lambda d: -d["drop"])
    return out


# ------------------------------------------------------------------ grids
def grid_types(targets, models, subsets=SUBSETS, views=GROUP_VIEWS, setnets=("deepsets", "attention")):
    return [{"target": t, "view": "%s@%s" % (v, s), "model": m} for t in targets for s in subsets for v in views for m in models]


def grid_contrast(targets, models, views=CONTRAST_VIEWS, setnets=("deepsets", "attention")):
    return [{"target": t, "view": "contrast:%s" % v, "model": m} for t in targets for v in views for m in models if m not in setnets]


def grid_type12(views=TYPE12_VIEWS, models=TYPE12_MODELS):
    return [{"target": "ds1_vs_ds2", "view": v, "model": m} for v in views for m in models]
