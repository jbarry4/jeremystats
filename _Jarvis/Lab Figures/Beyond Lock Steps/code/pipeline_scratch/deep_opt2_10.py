"""A curve on the PCA plane (PC1, PC2) chosen to maximize the AVERAGE of
the upper-blade and lower-blade separation index (each blade's own sink
overlap), each type holding 5% of events or more. Also saves the three
overlap matrices (both sinks, upper, lower) so any classification can be
scored per blade. Held out: fitted on a random half, scored on the other
half (5 times). Read only."""
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

HERE = os.path.dirname(os.path.abspath(__file__))
ANGLES = np.deg2rad(np.arange(0, 180, 6.0))
BENDS = (-1.0, -0.5, -0.25, -0.1, 0.0, 0.1, 0.25, 0.5, 1.0)
MIN_SHARE = 0.05


def prep(W, idx):
    W0 = W[np.ix_(idx, idx)].astype(float).copy()
    np.fill_diagonal(W0, 0.0)
    return W0, float(W0.sum())


def si_of(W0, tot, m):
    na, nb = int(m.sum()), int((~m).sum())
    if na < 2 or nb < 2:
        return np.nan
    Wm = W0 @ m
    saa = float(m @ Wm)
    sab = float((~m) @ Wm)
    sbb = tot - saa - 2.0 * sab
    w1, w2, btw = saa / (na * (na - 1)), sbb / (nb * (nb - 1)), sab / (na * nb)
    den = (w1 + w2) / 2.0
    return 1.0 - btw / den if den > 0 else np.nan


def side(Z, th, k, c):
    u = Z[:, 0] * np.cos(th) + Z[:, 1] * np.sin(th)
    v = -Z[:, 0] * np.sin(th) + Z[:, 1] * np.cos(th)
    return (v - k * u * u) > c


def search(Z, Ws, idx=None):
    idx = np.arange(Z.shape[0]) if idx is None else idx
    Zs = Z[idx]
    P = [prep(W, idx) for W in Ws]
    lo = max(5, int(np.ceil(MIN_SHARE * idx.size)))
    best = (-np.inf, None)
    for th in ANGLES:
        u = Zs[:, 0] * np.cos(th) + Zs[:, 1] * np.sin(th)
        v = -Zs[:, 0] * np.sin(th) + Zs[:, 1] * np.cos(th)
        for k in BENDS:
            w = v - k * u * u
            srt = np.sort(w)
            for q in np.unique(np.linspace(lo, idx.size - lo, 40).astype(int)):
                if q <= 0 or q >= idx.size or srt[q - 1] == srt[q]:
                    continue
                c = 0.5 * (srt[q - 1] + srt[q])
                m = w > c
                s = float(np.mean([si_of(W0, tot, m) for W0, tot in P]))
                if np.isfinite(s) and s > best[0]:
                    best = (s, (float(th), float(k), float(c)))
    return best


c = app.test_client()
room = A._er_rooms()["dentate_spike"]
j = c.get("/api/extraction/%s?version=10" % room["id"]).get_json()
out = {}
for r in j["payload"]["recordings"]:
    Ar, rule, flip = A._er_split_arrays(r)
    X = np.column_stack([np.asarray(Ar["x_pca"], float), np.asarray(Ar["y_pca"], float)])
    n = X.shape[0]
    d = {}
    if n >= 20 and np.isfinite(X).all() and np.ptp(X[:, 1]) > 0:
        if Ar.get("_bite") is None:
            EX.bite_view(Ar)
        Ws = {"both": np.asarray(Ar["_bite"]["W"], float)}
        for sd_ in ("top", "bottom"):
            try:
                if Ar.get("_bite_" + sd_) is None:
                    EX.hump_bite_view(Ar, sd_)
                Ws[sd_] = np.asarray(Ar["_bite_" + sd_]["W"], float)
            except Exception as exc:  # noqa: BLE001
                d["why_" + sd_] = str(exc)
        Ws = {k: 0.5 * (v + v.T) for k, v in Ws.items()}
        d["W"] = {k: v.astype(np.float32) for k, v in Ws.items()}
        if "top" in Ws and "bottom" in Ws:
            mu, sdv = X.mean(axis=0), X.std(axis=0) + 1e-12
            Z = (X - mu) / sdv
            blades = [Ws["top"], Ws["bottom"]]
            s, par = search(Z, blades)
            if par is not None:
                lay = A._dspca_layers(r.get("gid")) if rule == "anatomy" else None
                lab = side(Z, *par).astype(int)
                types = np.asarray(EX.name_sides(lab, np.asarray(Ar["prof"], float), [int(x) for x in Ar["nums_sel"]], rule, flip, lay), int)
                th, k, cc = par
                gx = np.linspace(X[:, 0].min(), X[:, 0].max(), 160)
                gy = np.linspace(X[:, 1].min(), X[:, 1].max(), 160)
                GX, GY = np.meshgrid(gx, gy)
                Zg = (np.column_stack([GX.ravel(), GY.ravel()]) - mu) / sdv
                ug = Zg[:, 0] * np.cos(th) + Zg[:, 1] * np.sin(th)
                vg = -Zg[:, 0] * np.sin(th) + Zg[:, 1] * np.cos(th)
                rng = np.random.default_rng(3)
                ho = []
                for _ in range(5):
                    perm = rng.permutation(n)
                    a_, b_ = perm[: n // 2], perm[n // 2:]
                    s_, p_ = search(Z, blades, a_)
                    if p_ is None:
                        continue
                    mb = side(Z[b_], *p_)
                    v_ = float(np.mean([si_of(*prep(W, b_), mb) for W in blades]))
                    if np.isfinite(v_):
                        ho.append(v_)
                d["fit"] = {"types": types, "mean": s, "n1": int((types == 1).sum()), "n2": int((types == 2).sum()),
                            "angle_deg": float(np.rad2deg(th)), "bend": k, "gx": gx, "gy": gy,
                            "F": (vg - k * ug * ug - cc).reshape(GX.shape).astype(np.float32),
                            "heldout": float(np.mean(ho)) if ho else None}
    out[r["gid"]] = d
    f = d.get("fit")
    print(r["session_label"].split()[1], n, "no fit (%s)" % (d.get("why_top") or d.get("why_bottom") or "too few") if not f else
          "blade mean %.2f (held out %s), %d/%d" % (f["mean"], "%.2f" % f["heldout"] if f["heldout"] is not None else "-", f["n1"], f["n2"]), flush=True)
with open(os.path.join(HERE, "deep_opt2_v10.pkl"), "wb") as fh:
    pickle.dump(out, fh)
