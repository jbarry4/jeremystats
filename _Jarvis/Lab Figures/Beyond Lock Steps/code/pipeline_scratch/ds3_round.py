"""The user's ask (2026-11-13) on the Halo set (room v6): every recording on
the Bite line at the lowest point of its cost curve, DS3 on, an Impression
of that state, and a fresh round of stats on DS3 -- PTEN against CTL."""
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
from backend import extraction as EX  # noqa: E402

V = 6
c = app.test_client()
room = A._er_rooms()["dentate_spike"]
AID = room["id"]
DO = "--apply" in sys.argv


def get():
    return c.get("/api/extraction/%s?version=%d" % (AID, V)).get_json()


j = get()
folder = j["payload"]["source"]["folder"]
# 1 The Bite line at the lowest point of its cost curve (no floor).
for r in j["payload"]["recordings"]:
    Ar, _a, _b = A._er_split_arrays(r)
    bv = EX.bite_view(Ar)
    sw = bv["sweep"]
    nc = np.array([np.nan if v is None else v for v in sw["ncut"]], float)
    kmin = int(sw["k"][int(np.nanargmin(nc))])
    ch = j["splits"].get(r["gid"])
    cur = (ch or {}).get("method", "bite"), (None if not ch or ch.get("cut") is None else int(np.ceil(ch["cut"] - 1e-9)))
    want_cut = None if kmin == bv["line"]["default_k"] else kmin - 0.5
    now_k = cur[1] if cur[0] == "bite" and cur[1] is not None else (bv["line"]["default_k"] if cur[0] == "bite" else None)
    same = cur[0] == "bite" and now_k is not None and (now_k == kmin or abs(nc[now_k - 1] - np.nanmin(nc)) < 1e-3)
    print("%-8s lowest cost after %3d of %3d (cost %.3f)  now %s%s" % (
        r["session_label"][5:12], kmin, r["n"], np.nanmin(nc), "bite after %s" % now_k if cur[0] == "bite" else cur[0],
        "" if same else "  -> set"), flush=True)
    if DO and not same:
        g = c.post("/api/extraction/split", json={"artifact_id": AID, "version": V, "gid": r["gid"],
                                                  "method": None if want_cut is None else "bite", "cut": want_cut}).get_json()
        print("     set:", g.get("ok"), g.get("error"), g.get("stuck"), flush=True)
if DO:
    g = c.post("/api/extraction/mode", json={"room": "dentate_spike", "folder": folder, "mode": "ds3"}).get_json()
    print("mode:", g.get("mode"), flush=True)
    g = c.post("/api/extraction/impression", json={"artifact_id": AID, "version": V, "note":
        "2026-11-13: every recording on the Bite line at the lowest point of its cost curve; DS3 (hybrid, Tarcsay et al. "
        "2025, relative-sink score within 0.5) laid over; only the events fed into the room."}).get_json()
    print("impression:", json.dumps({k: g.get(k) for k in ("ok", "artifact_id", "version", "n", "uncalled", "error")}), flush=True)
    if g.get("ok"):
        for v in range(1, int(g["version"])):
            try:
                A.ARTIFACTS.set_version_nickname(g["artifact_id"], v, "archived: superseded 11-13")
            except Exception as exc:
                print("   v%d not renamed: %s" % (v, exc))
        A.ARTIFACTS.set_version_nickname(g["artifact_id"], g["version"], "Bite minimum + DS3")

# 2 The numbers, one row a recording.
j = get()
rows = []
for r in j["payload"]["recordings"]:
    mx = r.get("mix") or {}
    d3 = mx.get("ds3") or {}
    cn = r.get("counts") or {}
    mins = (r.get("duration_s") or 0) / 60.0
    n1, n2, n3 = int(cn.get("1", 0)), int(cn.get("2", 0)), int(cn.get("3", 0))
    rows.append({"lab": r["session_label"][5:12].strip(), "g": "CTL" if str(r["group"]).upper() == "CTL" else "PTEN",
                 "ko": r.get("ko_now", r.get("ko_pct")), "n": r["n"], "n1": n1, "n2": n2, "n3": n3, "mins": mins,
                 "share": n3 / float(r["n"]) if not d3.get("why") else np.nan,
                 "rate": n3 / mins if mins and not d3.get("why") else np.nan,
                 "rate_all": r["n"] / mins if mins else np.nan,
                 "near": bool(d3.get("near")), "gap": d3.get("gap"), "why": d3.get("why"),
                 "unsc": (d3.get("unscorable") or {}).get("n")})
print("\nmode", j.get("mode"))
for x in rows:
    print("  %-8s %-4s KO %-5s n %3d = DS1 %3d DS2 %3d DS3 %3d | %4.1f min | DS3 %5.1f%%  %5.2f/min | all %5.2f/min | gap %s%s unsc %s %s" % (
        x["lab"], x["g"], x["ko"], x["n"], x["n1"], x["n2"], x["n3"], x["mins"], 100 * x["share"], x["rate"], x["rate_all"],
        x["gap"], "!" if x["near"] else " ", x["unsc"], "(no OML/MML)" if x["why"] else ""))


def two(name, key, sel=lambda x: True):
    a = np.array([x[key] for x in rows if x["g"] == "CTL" and sel(x) and np.isfinite(x[key])])
    b = np.array([x[key] for x in rows if x["g"] == "PTEN" and sel(x) and np.isfinite(x[key])])
    if min(a.size, b.size) < 3:
        print("  %-46s CTL n %d, PTEN n %d: too few" % (name, a.size, b.size))
        return
    u = st.mannwhitneyu(a, b, alternative="two-sided")
    w = st.ttest_ind(a, b, equal_var=False)
    rng = np.random.default_rng(0)
    allv = np.concatenate([a, b])
    obs = b.mean() - a.mean()
    perm = np.array([(lambda p: p[a.size:].mean() - p[:a.size].mean())(rng.permutation(allv)) for _ in range(20000)])
    pp = float((np.abs(perm) >= abs(obs) - 1e-12).mean())
    print("  %-46s CTL %d: median %.3g mean %.3g | PTEN %d: median %.3g mean %.3g | MWU p %.3f  Welch p %.3f  perm p %.3f" % (
        name, a.size, np.median(a), a.mean(), b.size, np.median(b), b.mean(), u.pvalue, w.pvalue, pp))


print("\nPTEN against CTL (one number a recording):")
ok = lambda x: not x["why"]
far = lambda x: not x["why"] and not x["near"]
two("DS3 rate, a minute -- every card", "rate", ok)
two("DS3 share of events -- every card", "share", ok)
two("DS3 rate -- OML and MML 3+ contacts apart", "rate", far)
two("DS3 share -- OML and MML 3+ contacts apart", "share", far)
two("DS3 rate -- 20+ events only", "rate", lambda x: ok(x) and x["n"] >= 20)
two("all DS rate, a minute (for scale)", "rate_all")
pt = [x for x in rows if x["g"] == "PTEN" and not x["why"] and x["ko"] is not None]
if len(pt) >= 4:
    for key in ("rate", "share"):
        rho = st.spearmanr([x["ko"] for x in pt], [x[key] for x in pt])
        print("  among PTEN, DS3 %s against %%KO: Spearman rho %.2f p %.3f (n %d)" % (key, rho.correlation, rho.pvalue, len(pt)))
tot = {g: (sum(x["n3"] for x in rows if x["g"] == g and not x["why"]), sum(x["n"] for x in rows if x["g"] == g and not x["why"])) for g in ("CTL", "PTEN")}
print("  pooled events (not the unit, for scale): CTL %d of %d (%.0f%%), PTEN %d of %d (%.0f%%)" % (
    tot["CTL"][0], tot["CTL"][1], 100.0 * tot["CTL"][0] / tot["CTL"][1], tot["PTEN"][0], tot["PTEN"][1], 100.0 * tot["PTEN"][0] / tot["PTEN"][1]))
json.dump(rows, open(os.path.join(os.path.dirname(__file__), "ds3_round.json"), "w"), default=str)
