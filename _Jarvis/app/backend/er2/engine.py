"""Targets, input views, models and mouse-level testing for Extraction Room 2.0.

TARGETS (one model per target; asked 2026-11-18):
  pten_vs_ctl       PTEN (1) against control (0); all 16 mice
  ko_pct            % knockout, controls at 0 (regression); all 16 mice
  low_vs_high       PTEN under 10% (0) against 15% or more (1); PTEN only
  ied3              control / IED- / IED+ (three classes); all 16 mice
  iedpos_vs_iedneg  IED+ (1) against IED- (0); PTEN only

TESTING: PTEN against control leaves one control AND one PTEN mouse out at a
time (every such pair, 7 x 9 = 63); every other target leaves one mouse out.
Nothing about a held-out mouse -- not its events, not its pooled numbers --
is used in training, feature choice, scaling or filling in missing values.

VIEWS (what a model sees):
  core          waveform / depth measures + the frozen DS type
  context       core + interval before / after, time in recording, detector peak, theta
  filters       core + the same measures under the six other filters
  before_after  core + power before / after the DS
  events_all    every per-event feature
  mouse         the per-mouse tables (battery, before/after per mouse); no events
  everything    every per-event feature + the per-mouse tables + nuisance
  nuisance      placement geometry, year, event count, length only (a baseline:
                anything that only matches this is not about the dentate spikes)

MODELS:
  pooled (each mouse's events summarized as distributions, then one row a mouse):
    linear (L2), lasso (L1), forest, boosting, mlp
  set networks over the events themselves (nets.py): deepsets, attention

SCORES (on held-out calls only): binary AUC (for the pair scheme: the share of
held-out control/PTEN pairs ordered right) and accuracy; knockout: rank
correlation of predicted with true % and mean absolute error; three classes:
accuracy and macro AUC. The bar asked for: AUC 0.80 (binary, three classes) or
rank correlation 0.70 (knockout).
"""
import json
import time
import warnings

import numpy as np
from scipy import stats as st

from . import amber as AMB
from .nets import SetNet

warnings.filterwarnings("ignore")
TARGETS = ("pten_vs_ctl", "ko_pct", "low_vs_high", "ied3", "iedpos_vs_iedneg")
# KCNT1's targets (2026-11-27). Not in TARGETS, which is what a run asks by
# default: a KCNT1 run names them (`targets` in /api/er2/run).
KCNT1_TARGETS = ("dose", "wt_vs_hom", "wt_vs_mut", "geno3")
VIEWS = ("core", "context", "filters", "before_after", "events_all", "mouse", "everything", "nuisance")
POOLED = ("linear", "lasso", "forest", "boosting", "mlp")
SETNETS = ("deepsets", "attention")
MODELS = POOLED + SETNETS
BAR = {"binary": 0.80, "multiclass": 0.80, "regression": 0.70}
STATS = ("median", "iqr", "mean", "sd", "p10", "p90")
K_LINEAR, K_TREES = 100, 400


# ------------------------------------------------------------------ data
class Data(object):
    """The frozen bundle, with its pooled per-mouse table made once."""

    def __init__(self, version=None, root=None):
        man, A = AMB.load(version) if root is None else AMB.load(version, root)
        self.man = man
        self.X = A["X"].astype(np.float64)
        self.bag = A["ev_mouse"].astype(int)
        self.XM = A["XM"].astype(np.float64)
        self.mice = man["mice"]
        self.labs = [m["lab"] for m in self.mice]
        self.efeat = man["event_features"]
        self.efam = man["event_families"]
        self.mfeat = man["mouse_features"]
        self.mfam = man["mouse_families"]
        self.group = np.array([m["group"] for m in self.mice])
        self.sub = np.array([m["subgroup"] for m in self.mice])
        # Controls (PTEN) and WT (KCNT1, whose `ko` is the gene dose) are at 0.
        self.ko = np.array([m["ko"] if m["group"] not in ("CTL", "WT") else 0.0 for m in self.mice], float)
        self._pooled = None

    def event_cols(self, view):
        fam = np.array(self.efam)
        base = (fam == "waveform/depth") | (fam == "ds type")
        if view == "core":
            m = base
        elif view == "context":
            m = base | (fam == "context")
        elif view == "filters":
            m = base | np.char.startswith(fam.astype(str), "filter")
        elif view == "before_after":
            m = base | np.char.startswith(fam.astype(str), "before/after")
        elif view in ("events_all", "everything"):
            m = np.ones(fam.size, bool)
        elif view == "raw":
            # the raw event only (2026-11-20): CSD, LFP, spectrogram, + the frozen type
            m = np.isin(fam, ["raw CSD", "raw LFP", "raw spectrogram", "ds type"])
        else:
            m = np.zeros(fam.size, bool)
        return np.where(m)[0]

    def mouse_cols(self, view):
        fam = np.array(self.mfam)
        if view == "mouse":
            return np.where(fam != "nuisance")[0]
        if view == "everything":
            return np.arange(fam.size)
        if view == "nuisance":
            return np.where(fam == "nuisance")[0]
        return np.array([], int)

    def pooled(self):
        """Every event feature summarized per mouse: (matrix mice x columns, names, families, base event column)."""
        if self._pooled is not None:
            return self._pooled
        # Vectorized over features (2026-11-20, for the raw-event bundles with
        # thousands of columns); the same numbers, in the same column order, as
        # the loop it replaced: each statistic over a mouse's finite values,
        # NaN with fewer than 5.
        nm, F = len(self.mice), len(self.efeat)
        types = {k: self.X[:, self.efeat.index("type_" + k)] > 0.5 for k in ("ds1", "ds2", "ds3")}
        is_type = np.array([f.startswith("type_") for f in self.efeat])
        S = {s: np.full((nm, F), np.nan) for s in STATS}
        T = {k: np.full((nm, F), np.nan) for k in types}
        share = np.full((nm, F), np.nan)
        for i in range(nm):
            sel = self.bag == i
            xi = self.X[sel]
            if xi.shape[0] == 0:
                continue
            share[i] = np.nanmean(xi, axis=0)
            n = np.isfinite(xi).sum(axis=0)
            okc = n >= 5
            if okc.any():
                xo = xi[:, okc]
                q10, q25, q50, q75, q90 = np.nanpercentile(xo, [10, 25, 50, 75, 90], axis=0)
                S["median"][i, okc], S["iqr"][i, okc], S["p10"][i, okc], S["p90"][i, okc] = q50, q75 - q25, q10, q90
                S["mean"][i, okc] = np.nanmean(xo, axis=0)
                S["sd"][i, okc] = np.nanstd(xo, axis=0)
            for k, tm in types.items():
                xt = self.X[sel & tm]
                if xt.shape[0] < 5:
                    continue
                nt = np.isfinite(xt).sum(axis=0) >= 5
                if nt.any():
                    T[k][i, nt] = np.nanmedian(xt[:, nt], axis=0)
        cols, names, fams, base = [], [], [], []
        for j, f in enumerate(self.efeat):
            if is_type[j]:
                cols.append(share[:, j])
                names.append("share|" + f[5:])
                fams.append("ds type")
                base.append(j)
                continue
            for s in STATS:
                cols.append(S[s][:, j])
                names.append("%s|%s" % (f, s))
                fams.append(self.efam[j])
                base.append(j)
            for k in types:
                cols.append(T[k][:, j])
                names.append("%s|%s_median" % (f, k))
                fams.append(self.efam[j])
                base.append(j)
        self._pooled = (np.column_stack(cols), names, fams, np.array(base))
        return self._pooled

    def mouse_matrix(self, view):
        """(mice x columns, names, families) of a view for the pooled models."""
        P, pn, pf, pb = self.pooled()
        ec = set(self.event_cols(view).tolist())
        keep = np.array([b in ec for b in pb])
        mc = self.mouse_cols(view)
        M = np.column_stack([P[:, keep], self.XM[:, mc]]) if mc.size else P[:, keep]
        names = [n for n, k in zip(pn, keep) if k] + [self.mfeat[i] for i in mc]
        fams = [f for f, k in zip(pf, keep) if k] + [self.mfam[i] for i in mc]
        return M, names, fams


def target(data, name):
    """(mice used, y, task kind, cv scheme, class names).

    A bundle cut down to one DS type (typed.restrict / typed.contrast) marks
    in data.keep the mice with enough events; the others sit the target out."""
    m_, y_, task_, scheme_, cls_ = _target(data, name)
    keep = getattr(data, "keep", None)
    if keep is not None:
        ok = keep[m_]
        m_, y_ = m_[ok], y_[ok]
    return m_, y_, task_, scheme_, cls_


def _target(data, name):
    g, s, ko = data.group, data.sub, data.ko
    allm = np.arange(len(data.mice))
    if name == "pten_vs_ctl":
        return allm, (g == "PTEN").astype(float), "binary", "pairs", ["control", "PTEN"]
    if name == "ko_pct":
        return allm, ko, "regression", "loo", None
    if name == "low_vs_high":
        m = allm[(g == "PTEN") & ((ko < 10) | (ko >= 15))]
        return m, (ko[m] >= 15).astype(float), "binary", "loo", ["low (<10%)", "high (15%+)"]
    if name == "ied3":
        return allm, np.array([{"CTL": 0, "IED-": 1, "IED+": 2}[x] for x in s], float), "multiclass", "loo", ["control", "IED-", "IED+"]
    if name == "iedpos_vs_iedneg":
        m = allm[g == "PTEN"]
        return m, (s[m] == "IED+").astype(float), "binary", "loo", ["IED-", "IED+"]
    # KCNT1 (2026-11-27, the preliminary run): group is the genotype and `ko`
    # the gene dose (mutant alleles: WT 0, Het 1, Hom 2), as the KCNT1 battery
    # writes them. Same testing as PTEN: a two-group target leaves one mouse of
    # each group out, everything else one mouse.
    if name == "dose":
        return allm, ko.astype(float), "regression", "loo", None
    if name == "wt_vs_hom":
        m = allm[(g == "WT") | (g == "Hom")]
        return m, (g[m] == "Hom").astype(float), "binary", "pairs", ["WT", "Hom"]
    if name == "wt_vs_mut":
        m = allm[np.isin(g, ["WT", "Het", "Hom"])]
        return m, (g[m] != "WT").astype(float), "binary", "pairs", ["WT", "Het or Hom"]
    if name == "geno3":
        m = allm[np.isin(g, ["WT", "Het", "Hom"])]
        return m, np.array([{"WT": 0, "Het": 1, "Hom": 2}[x] for x in g[m]], float), "multiclass", "loo", ["WT", "Het", "Hom"]
    raise ValueError("unknown target %s" % name)


def folds(y, scheme):
    """Lists of held-out positions (into the target's mice)."""
    n = y.size
    if scheme == "pairs":
        a, b = np.where(y == 0)[0], np.where(y == 1)[0]
        return [[i, j] for i in a for j in b]
    return [[i] for i in range(n)]


# ------------------------------------------------------------------ prep
def _prep_fit(M, y, k, task):
    """Fill, scale and choose columns on the training mice only."""
    med = np.nanmedian(M, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    X = np.where(np.isfinite(M), M, med)
    sd = X.std(axis=0)
    ok = sd > 1e-12
    mu = X.mean(axis=0)
    Z = np.zeros_like(X)
    Z[:, ok] = (X[:, ok] - mu[ok]) / sd[ok]
    # univariate screen: rank correlation with the target (|rho|), among usable columns
    yy = y if task != "multiclass" else y
    r = np.zeros(X.shape[1])
    if ok.any():
        R = np.apply_along_axis(st.rankdata, 0, X[:, ok])
        ry = st.rankdata(yy)
        R = R - R.mean(axis=0)
        ry = ry - ry.mean()
        den = np.sqrt((R ** 2).sum(axis=0) * (ry ** 2).sum())
        rr = np.where(den > 0, (R * ry[:, None]).sum(axis=0) / np.where(den > 0, den, 1), 0.0)
        if task == "multiclass":
            # largest |rho| of the one-vs-rest indicators
            rr = np.zeros(ok.sum())
            for c in np.unique(y):
                yc = st.rankdata(y == c) - st.rankdata(y == c).mean()
                d = np.sqrt((R ** 2).sum(axis=0) * (yc ** 2).sum())
                rr = np.maximum(rr, np.abs(np.where(d > 0, (R * yc[:, None]).sum(axis=0) / np.where(d > 0, d, 1), 0.0)))
        r[ok] = np.abs(rr)
    sel = np.argsort(-r)[:min(k, int(ok.sum()))]
    return {"med": med, "mu": mu, "sd": np.where(ok, sd, 1.0), "sel": sel}


def _prep_apply(P, M):
    X = np.where(np.isfinite(M), M, P["med"])
    return ((X - P["mu"]) / P["sd"])[:, P["sel"]]


def _make(model, task, n_class, seed):
    from sklearn import ensemble, linear_model, neural_network
    if task == "regression":
        return {"linear": lambda: linear_model.Ridge(alpha=10.0),
                "lasso": lambda: linear_model.Lasso(alpha=0.5, max_iter=20000),
                "forest": lambda: ensemble.RandomForestRegressor(500, min_samples_leaf=2, random_state=seed, n_jobs=1),
                "boosting": lambda: ensemble.GradientBoostingRegressor(n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=seed),
                "mlp": lambda: neural_network.MLPRegressor(hidden_layer_sizes=(16,), alpha=1.0, max_iter=3000, random_state=seed)}[model]()
    return {"linear": lambda: linear_model.LogisticRegression(C=0.1, max_iter=5000),
            "lasso": lambda: linear_model.LogisticRegression(C=0.5, penalty="l1", solver="saga", max_iter=20000),
            "forest": lambda: ensemble.RandomForestClassifier(500, min_samples_leaf=2, random_state=seed, n_jobs=1),
            "boosting": lambda: ensemble.GradientBoostingClassifier(n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=seed),
            "mlp": lambda: neural_network.MLPClassifier(hidden_layer_sizes=(16,), alpha=1.0, max_iter=3000, random_state=seed)}[model]()


def _score_of(est, Z, task, n_class):
    if task == "regression":
        return est.predict(Z)
    pr = est.predict_proba(Z)
    if task == "binary":
        return pr[:, 1] if pr.shape[1] > 1 else np.zeros(Z.shape[0])
    out = np.zeros((Z.shape[0], n_class))
    out[:, est.classes_.astype(int)] = pr
    return out


# ------------------------------------------------------------------ one fit
class Fitted(object):
    """One fold's model, able to predict held-out mice (also with columns permuted)."""

    def __init__(self, data, view, model, task, n_class, train, y_train, seed=0, drop_family=None):
        self.data, self.view, self.model, self.task, self.n_class = data, view, model, task, n_class
        self.drop_family = drop_family
        if model in POOLED:
            M, self.names, self.fams = data.mouse_matrix(view)
            if drop_family:
                keep = np.array([f != drop_family for f in self.fams])
                self.cols = np.where(keep)[0]
            else:
                self.cols = np.arange(M.shape[1])
            self.M = M[:, self.cols]
            k = K_TREES if model in ("forest", "boosting") else K_LINEAR
            self.prep = _prep_fit(self.M[train], y_train, k, task)
            self.est = _make(model, task, n_class, seed)
            Zt = _prep_apply(self.prep, self.M[train])
            yt = y_train if task != "multiclass" else y_train.astype(int)
            if task != "regression" and np.unique(yt).size < 2:
                raise ValueError("one class in training")
            self.est.fit(Zt, yt)
        else:
            cols = data.event_cols(view)
            if drop_family:
                cols = np.array([c for c in cols if data.efam[c] != drop_family], int)
            self.ecols = cols
            ev = np.isin(data.bag, train)
            Xe = data.X[ev][:, cols]
            med = np.nanmedian(Xe, axis=0)
            self.emed = np.where(np.isfinite(med), med, 0.0)
            Xe = np.where(np.isfinite(Xe), Xe, self.emed)
            self.emu, sd = Xe.mean(axis=0), Xe.std(axis=0)
            self.esd = np.where(sd > 1e-12, sd, 1.0)
            Ze = np.clip((Xe - self.emu) / self.esd, -6, 6)
            yb = {int(m): float(v) for m, v in zip(train, y_train)}
            if task == "regression":
                self.ysc = max(np.std(y_train), 1e-6)
                self.ymu = float(np.mean(y_train))
                yb = {m: (v - self.ymu) / self.ysc for m, v in yb.items()}
            self.est = SetNet(len(cols), kind="mean" if model == "deepsets" else "attention", task=task,
                              n_out=n_class, seed=seed).fit(Ze, data.bag[ev], yb)

    def _events(self, mice, perm_cols=None, rng=None, fill_cols=None):
        ev = np.where(np.isin(self.data.bag, mice))[0]
        Xe = self.data.X[ev][:, self.ecols].copy()
        if fill_cols is not None and len(fill_cols):
            Xe[:, fill_cols] = self.emed[fill_cols]
        if perm_cols is not None:
            # replace the columns with values drawn from every event of every mouse
            pool = self.data.X[:, self.ecols][:, perm_cols]
            take = rng.integers(0, pool.shape[0], size=ev.size)
            Xe[:, perm_cols] = pool[take]
        Xe = np.where(np.isfinite(Xe), Xe, self.emed)
        return np.clip((Xe - self.emu) / self.esd, -6, 6), self.data.bag[ev]

    def predict(self, mice, perm_cols=None, rng=None, M_override=None, fill_cols=None):
        """Scores of the given mice (target order); perm_cols: columns (in this
        model's own column order) replaced by random other mice's / events' values."""
        mice = np.asarray(mice)
        if self.model in POOLED:
            M = (self.M if M_override is None else M_override)[mice].copy()
            if perm_cols is not None:
                donors = rng.integers(0, self.M.shape[0], size=(mice.size,))
                M[:, perm_cols] = self.M[donors][:, perm_cols]
            return _score_of(self.est, _prep_apply(self.prep, M), self.task, self.n_class)
        Ze, bg = self._events(mice, perm_cols, rng, fill_cols)
        ids, out = self.est.predict(Ze, bg)
        order = [int(np.where(ids == m)[0][0]) for m in mice]
        out = out[order]
        if self.task == "regression":
            out = out * self.ysc + self.ymu
        return out

    def weights(self, mice):
        if self.model != "attention":
            return None
        Ze, bg = self._events(np.asarray(mice))
        return self.est.weights(Ze, bg), bg

    def feature_names(self):
        if self.model in POOLED:
            return [self.names[c] for c in self.cols], [self.fams[c] for c in self.cols]
        return [self.data.efeat[c] for c in self.ecols], [self.data.efam[c] for c in self.ecols]


# ------------------------------------------------------------------ scores
def score(task, y, pred, fold_list, scheme):
    """Held-out score from the out-of-fold calls: pred[f] = calls of fold f's mice."""
    if task == "regression":
        p = np.array([pred[f][0] for f in range(len(fold_list))])
        t = np.array([y[fold_list[f][0]] for f in range(len(fold_list))])
        rho = st.spearmanr(p, t).correlation if np.ptp(p) > 0 else 0.0
        return {"rho": float(rho), "mae": float(np.mean(np.abs(p - t))), "main": float(rho)}
    if task == "binary":
        if scheme == "pairs":
            right, acc = [], []
            for f, (i, j) in enumerate(fold_list):
                si, sj = pred[f][0], pred[f][1]            # i control, j PTEN
                right.append(1.0 if sj > si else (0.5 if sj == si else 0.0))
                acc += [float(si < 0.5), float(sj >= 0.5)]
            return {"auc": float(np.mean(right)), "accuracy": float(np.mean(acc)), "main": float(np.mean(right))}
        p = np.array([pred[f][0] for f in range(len(fold_list))])
        t = np.array([y[fold_list[f][0]] for f in range(len(fold_list))])
        from sklearn.metrics import roc_auc_score
        auc = roc_auc_score(t, p) if np.unique(t).size > 1 else np.nan
        return {"auc": float(auc), "accuracy": float(np.mean((p >= 0.5) == (t == 1))), "main": float(auc)}
    P = np.array([pred[f][0] for f in range(len(fold_list))])
    t = np.array([y[fold_list[f][0]] for f in range(len(fold_list))]).astype(int)
    from sklearn.metrics import roc_auc_score
    aucs = [roc_auc_score(t == c, P[:, c]) for c in range(P.shape[1]) if 0 < (t == c).sum() < t.size]
    return {"accuracy": float(np.mean(P.argmax(axis=1) == t)), "auc": float(np.mean(aucs)), "main": float(np.mean(aucs))}


def run_cv(data, target_name, view, model, seed=0, y_override=None, drop_family=None, keep_models=False):
    mice, y, task, scheme, classes = target(data, target_name)
    if y_override is not None:
        y = y_override
    n_class = 3 if task == "multiclass" else 1
    F = folds(y, scheme)
    pred, fitted = [], []
    for f, held in enumerate(F):
        train = np.array([i for i in range(y.size) if i not in held])
        fm = Fitted(data, view, model, task, n_class, mice[train], y[train], seed=seed + f, drop_family=drop_family)
        pred.append(fm.predict(mice[np.array(held)]))
        if keep_models:
            fitted.append(fm)
    sc = score(task, y, pred, F, scheme)
    return {"mice": mice, "y": y, "task": task, "scheme": scheme, "classes": classes, "folds": F, "pred": pred,
            "score": sc, "fitted": fitted}


def passes(task, sc):
    return bool(np.isfinite(sc["main"]) and sc["main"] >= BAR[task])


def run_task(spec, log=print):
    """One leaderboard entry: target x view x model, with its explanation.
    spec: {target, view, model, amber_version, seed, n_shuffle, explain, out}."""
    from . import explain as EX
    from . import typed as TY
    t0 = time.time()
    if spec["target"] == "ds1_vs_ds2":
        return TY.run_type12(spec, Data, log=log)
    data = Data(spec.get("amber_version"), spec.get("amber_root"))
    tgt, full_view, model = spec["target"], spec["view"], spec["model"]
    view, subset, is_contrast = TY.parse_view(full_view)
    if model in SETNETS and (view in ("mouse", "nuisance") or is_contrast):
        return {"skipped": "the set networks read events; this view has none"}
    if is_contrast:
        data = TY.contrast(data)
    elif subset:
        data = TY.restrict(data, subset, seed=int(spec.get("seed", 0)))
    res = run_cv(data, tgt, view, model, seed=int(spec.get("seed", 0)), keep_models=True)
    out = {"target": tgt, "view": full_view, "model": model, "amber_version": data.man["version"], "task": res["task"], "scheme": res["scheme"],
           "score": res["score"], "passes": passes(res["task"], res["score"]), "bar": BAR[res["task"]], "n_folds": len(res["folds"]),
           "calls": [], "classes": res["classes"], "n_mice": int(len(res["mice"]))}
    for f, held in enumerate(res["folds"]):
        for k, i in enumerate(held):
            p = res["pred"][f][k]
            out["calls"].append({"fold": f, "lab": data.labs[res["mice"][i]], "truth": float(res["y"][i]),
                                 "call": p.tolist() if hasattr(p, "tolist") else float(p)})
    log("%s %s %s: %s" % (tgt, full_view, model, json.dumps({k: round(v, 3) for k, v in res["score"].items()})))
    ns = int(spec.get("n_shuffle", 0))
    if ns:
        rng = np.random.default_rng(1000 + int(spec.get("seed", 0)))
        null = []
        for _ in range(ns):
            yp = rng.permutation(res["y"])
            try:
                null.append(run_cv(data, tgt, view, model, y_override=yp)["score"]["main"])
            except ValueError:
                continue
        null = np.array([v for v in null if np.isfinite(v)])
        out["chance"] = {"n": int(null.size), "p": float((1 + (null >= res["score"]["main"]).sum()) / (1 + null.size)) if null.size else None,
                         "median": float(np.median(null)) if null.size else None}
    if spec.get("explain", True):
        out["explain"] = EX.explain(data, res, tgt, view, model, log=log, drop=bool(spec.get("drop", True)))
    out["seconds"] = round(time.time() - t0, 1)
    return out


def grid(targets=TARGETS, views=VIEWS, models=MODELS):
    return [{"target": t, "view": v, "model": m} for t in targets for v in views for m in models
            if not (m in SETNETS and v in ("mouse", "nuisance"))]
