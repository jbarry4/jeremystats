"""The DS3 score (Tarcsay et al. 2025 relative sink, backend/dsmix.relsink)
of every event under the classifications the quality check draws that the
room does not already hold: the two mixtures and the two optimized
boundaries on the PCA plane. Read only."""
import os
import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
APP = os.environ.get("JAPP", "/gpfs2/scratch/sakhava1/kcnt1_prelim/app")
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import numpy as np  # noqa: E402
from backend.app import app  # noqa: E402
from backend import app as A  # noqa: E402
from backend import dsmix  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PCA2 = pickle.load(open(os.path.join(HERE, "deep_pca2_v7.pkl"), "rb"))
OPT = pickle.load(open(os.path.join(HERE, "deep_opt_v7.pkl"), "rb"))
c = app.test_client()
room = A._er_rooms()[os.environ.get("KROOM", "dentate_spike_kcnt1")]
j = c.get("/api/extraction/%s?version=7" % room["id"]).get_json()
out = {}
for r in j["payload"]["recordings"]:
    Ar, rule, flip = A._er_split_arrays(r)
    d = {}
    src = dict((PCA2.get(r["gid"], {}).get("fits") or {}))
    src.update((OPT.get(r["gid"], {}).get("fits") or {}))
    for key, ft in src.items():
        if "types" not in ft:
            continue
        rs = dsmix.relsink(Ar, np.asarray(ft["types"], int))
        d[key] = {"why": rs.get("why")} if rs.get("why") else {"why": None, "score": np.asarray(rs["score"], float), "oml": rs["oml"],
                                                               "mml": rs["mml"], "floor": rs["floor"]}
    out[r["gid"]] = d
    print(r["session_label"].split()[1], {k: ("no layers" if v["why"] else "DS3 %d, unscorable %d, OML-MML %d um" % (
        int((np.abs(v["score"]) <= 0.5).sum()), int((~np.isfinite(v["score"])).sum()), abs(v["oml"] - v["mml"]) * 50)) for k, v in d.items()}, flush=True)
with open(os.path.join(HERE, "deep_ds3_v7.pkl"), "wb") as f:
    pickle.dump(out, f)
