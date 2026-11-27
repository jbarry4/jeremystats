"""Two more classifiers on the PCA plane (PC1, PC2), for the quality check:
a two-Gaussian mixture with a shared covariance (a straight boundary at
any angle) and with its own covariance per type (a curved boundary). Ten
starts each; scored on the same separation index as the other fifteen;
stability = the share of events that keep their type when the mixture is
refitted on 40 bootstrap resamples. Read only."""
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
from sklearn.mixture import GaussianMixture  # noqa: E402
from backend.app import app  # noqa: E402
from backend import app as A  # noqa: E402
from backend import extraction as EX  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
c = app.test_client()
room = A._er_rooms()["dentate_spike"]
j = c.get("/api/extraction/%s?version=6" % room["id"]).get_json()
out = {}
for r in j["payload"]["recordings"]:
    Ar, rule, flip = A._er_split_arrays(r)
    X = np.column_stack([np.asarray(Ar["x_pca"], float), np.asarray(Ar["y_pca"], float)])
    n = X.shape[0]
    d = {"X": X, "km_types": np.asarray(Ar["types_pca"], int), "km_cut": EX.default_cut(Ar, "pca"), "fits": {}}
    ok = np.isfinite(X).all(axis=1)
    if n >= 20 and ok.all() and np.ptp(X[:, 1]) > 0:
        lay = A._dspca_layers(r.get("gid")) if rule == "anatomy" else None
        mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-12
        Z = (X - mu) / sd
        for key, cov in (("pca_gmm_line", "tied"), ("pca_gmm_curve", "full")):
            try:
                g = GaussianMixture(2, covariance_type=cov, n_init=10, random_state=0, reg_covar=1e-4).fit(Z)
                lab = g.predict(Z)
                if lab.min() == lab.max():
                    raise ValueError("one type only")
                types = np.asarray(EX.name_sides(lab, np.asarray(Ar["prof"], float), [int(x) for x in Ar["nums_sel"]], rule, flip, lay), int)
                sc = A._er_overlap_scores(Ar, types, "pca") or {}
                rng = np.random.default_rng(1)
                keep = []
                for _ in range(40):
                    i = rng.integers(0, n, n)
                    try:
                        gb = GaussianMixture(2, covariance_type=cov, n_init=3, random_state=0, reg_covar=1e-4).fit(Z[i])
                        lb = gb.predict(Z)
                        keep.append(max(np.mean(lb == lab), np.mean(lb != lab)))
                    except Exception:  # noqa: BLE001
                        pass
                # the boundary, on a grid in the plane's own units
                gx = np.linspace(X[:, 0].min(), X[:, 0].max(), 160)
                gy = np.linspace(X[:, 1].min(), X[:, 1].max(), 160)
                GX, GY = np.meshgrid(gx, gy)
                P = g.predict_proba((np.column_stack([GX.ravel(), GY.ravel()]) - mu) / sd)[:, 0].reshape(GX.shape)
                d["fits"][key] = {"types": types, "si": sc.get("si"), "n1": int((types == 1).sum()), "n2": int((types == 2).sum()),
                                  "stable": float(np.mean(keep)) if keep else None, "gx": gx, "gy": gy, "P": P.astype(np.float32),
                                  "post": g.predict_proba(Z).max(axis=1)}
            except Exception as exc:  # noqa: BLE001
                d["fits"][key] = {"err": str(exc)}
    out[r["gid"]] = d
    print(r["session_label"].split()[1], n, {k: ("err " + v["err"] if "err" in v else "SI %.2f, %d/%d, stable %.2f" % (
        v["si"] if v["si"] is not None else float("nan"), v["n1"], v["n2"], v["stable"] or float("nan"))) for k, v in d["fits"].items()}, flush=True)
with open(os.path.join(HERE, "deep_pca2_v6.pkl"), "wb") as f:
    pickle.dump(out, f)
