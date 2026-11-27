"""The other way round: a boundary on the PCA plane (PC1, PC2) chosen to
make the DS1-DS2 separation index as high as it can be -- a straight line
at any angle, and a curve (a parabola about that line) -- with each type
holding at least 5% of events. Beside the conventional mixture boundaries
(deep_pca2.py). Because the index is now both target and yardstick, each
is also fitted on a random half of the events and scored on the other half
(5 times). Read only."""
import os
import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import numpy as np  # noqa: E402
from backend.app import app  # noqa: E402
from backend import app as A  # noqa: E402
from backend import extraction as EX  # noqa: E402
from backend import sinkcut  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ANGLES = np.deg2rad(np.arange(0, 180, 6.0))
BENDS = {"opt_line": (0.0,), "opt_curve": (-1.0, -0.5, -0.25, -0.1, 0.0, 0.1, 0.25, 0.5, 1.0)}
MIN_SHARE = 0.05


def si_of(W0, tot, m):
    """The separation index of a two-way split (m: bool), W0 symmetric with
    a zero diagonal -- the same number sinkcut.scores gives."""
    na, nb = int(m.sum()), int((~m).sum())
    if na < 2 or nb < 2:
        return np.nan
    Wm = W0 @ m
    saa = float(m @ Wm)
    sab = float((~m) @ Wm)
    sbb = tot - saa - 2.0 * sab
    w1, w2, btw = saa / (na * (na - 1)), sbb / (nb * (nb - 1)), sab / (na * nb)
    return 1.0 - btw / ((w1 + w2) / 2.0)


def side(Z, th, k, c):
    u = Z[:, 0] * np.cos(th) + Z[:, 1] * np.sin(th)
    v = -Z[:, 0] * np.sin(th) + Z[:, 1] * np.cos(th)
    return (v - k * u * u) > c


def search(Z, W, bends, idx=None):
    """The (angle, bend, offset) with the highest index on events idx."""
    idx = np.arange(Z.shape[0]) if idx is None else idx
    Zs = Z[idx]
    W0 = W[np.ix_(idx, idx)].astype(float).copy()
    np.fill_diagonal(W0, 0.0)
    tot = float(W0.sum())
    lo = max(5, int(np.ceil(MIN_SHARE * idx.size)))
    best = (-np.inf, None)
    for th in ANGLES:
        u = Zs[:, 0] * np.cos(th) + Zs[:, 1] * np.sin(th)
        v = -Zs[:, 0] * np.sin(th) + Zs[:, 1] * np.cos(th)
        for k in bends:
            w = v - k * u * u
            srt = np.sort(w)
            for q in np.unique(np.linspace(lo, idx.size - lo, 40).astype(int)):
                if q <= 0 or q >= idx.size or srt[q - 1] == srt[q]:
                    continue
                c = 0.5 * (srt[q - 1] + srt[q])
                s = si_of(W0, tot, w > c)
                if np.isfinite(s) and s > best[0]:
                    best = (s, (float(th), float(k), float(c)))
    return best


c = app.test_client()
room = A._er_rooms()["dentate_spike"]
j = c.get("/api/extraction/%s?version=6" % room["id"]).get_json()
out = {}
for r in j["payload"]["recordings"]:
    Ar, rule, flip = A._er_split_arrays(r)
    X = np.column_stack([np.asarray(Ar["x_pca"], float), np.asarray(Ar["y_pca"], float)])
    n = X.shape[0]
    d = {"fits": {}}
    if n >= 20 and np.isfinite(X).all() and np.ptp(X[:, 1]) > 0:
        if Ar.get("_bite") is None:
            EX.bite_view(Ar)
        W = np.asarray(Ar["_bite"]["W"], float)
        W = 0.5 * (W + W.T)
        mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-12
        Z = (X - mu) / sd
        lay = A._dspca_layers(r.get("gid")) if rule == "anatomy" else None
        gx = np.linspace(X[:, 0].min(), X[:, 0].max(), 160)
        gy = np.linspace(X[:, 1].min(), X[:, 1].max(), 160)
        GX, GY = np.meshgrid(gx, gy)
        Zg = (np.column_stack([GX.ravel(), GY.ravel()]) - mu) / sd
        for key, bends in BENDS.items():
            s, par = search(Z, W, bends)
            if par is None:
                d["fits"][key] = {"err": "no boundary leaves 5% a side"}
                continue
            lab = side(Z, *par).astype(int)
            types = np.asarray(EX.name_sides(lab, np.asarray(Ar["prof"], float), [int(x) for x in Ar["nums_sel"]], rule, flip, lay), int)
            sc = sinkcut.scores(Ar["_bite"]["W"], types)
            th, k, cc = par
            ug = Zg[:, 0] * np.cos(th) + Zg[:, 1] * np.sin(th)
            vg = -Zg[:, 0] * np.sin(th) + Zg[:, 1] * np.cos(th)
            # held out: fit on half, score the other half
            rng = np.random.default_rng(3)
            ho = []
            for _ in range(5):
                perm = rng.permutation(n)
                a_, b_ = perm[: n // 2], perm[n // 2:]
                s_, p_ = search(Z, W, bends, a_)
                if p_ is None:
                    continue
                mb = side(Z[b_], *p_)
                W0 = W[np.ix_(b_, b_)].copy()
                np.fill_diagonal(W0, 0.0)
                v_ = si_of(W0, float(W0.sum()), mb)
                if np.isfinite(v_):
                    ho.append(v_)
            d["fits"][key] = {"types": types, "si": sc.get("si"), "si_search": s, "n1": int((types == 1).sum()), "n2": int((types == 2).sum()),
                              "angle_deg": float(np.rad2deg(th)), "bend": k, "gx": gx, "gy": gy,
                              "F": (vg - k * ug * ug - cc).reshape(GX.shape).astype(np.float32),
                              "heldout": float(np.mean(ho)) if ho else None, "heldout_n": len(ho)}
    out[r["gid"]] = d
    print(r["session_label"].split()[1], n, {k: ("err" if "err" in v else "SI %.2f (held out %s), %d/%d, angle %.0f bend %.2f" % (
        v["si"], "%.2f" % v["heldout"] if v["heldout"] is not None else "-", v["n1"], v["n2"], v["angle_deg"], v["bend"]))
        for k, v in d["fits"].items()}, flush=True)
with open(os.path.join(HERE, "deep_opt_v6.pkl"), "wb") as f:
    pickle.dump(out, f)
