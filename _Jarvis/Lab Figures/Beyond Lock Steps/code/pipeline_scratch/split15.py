"""The fifteen splits and the low-contacts look on real cards, through the
app's own routes, in-process. argv: room version, then session labels
(substrings); none = every card."""
import json
import os
import sys
import time

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import warnings  # noqa: E402
warnings.filterwarnings("ignore")
from backend.app import app  # noqa: E402
from backend import app as A  # noqa: E402

V = int(sys.argv[1])
WANT = sys.argv[2:]
c = app.test_client()
room = A._er_rooms()["dentate_spike"]
pay = A.ARTIFACTS.payload(room["id"], V)
OUT = {}
for rec in pay["recordings"]:
    lab = rec["session_label"]
    if WANT and not any(w in lab for w in WANT):
        continue
    row = {}
    for low in (False, True):
        t0 = time.time()
        r = c.get("/api/extraction/%s/split?version=%d&gid=%s%s" % (room["id"], V, rec["gid"], "&low=1" if low else ""))
        j = r.get_json() or {}
        dt = time.time() - t0
        if r.status_code != 200:
            print(lab, "low" if low else "", "FAILED", r.status_code, j.get("error"), flush=True)
            continue
        line = {"secs": round(dt, 1), "humps": j.get("humps"), "low": j.get("low") and {
            k: j["low"].get(k) for k in ("contacts", "bad", "left_out")}}
        for m, M in j["methods"].items():
            pre = (j.get("pre") or {}).get(m) or {}
            sc = pre.get("scores") or {}
            line[m] = {"n1": (pre.get("counts") or {}).get("1"), "n2": (pre.get("counts") or {}).get("2"),
                       "si": sc.get("si"), "hump_si": (sc.get("hump") or {}).get("si"),
                       "why": M.get("why"), "cut": M.get("cut"),
                       "nan": sum(1 for x in M.get("x") or [] if x is None)}
        for h, bv in (j.get("bite_rows") or {}).items():
            line["bite_rows_" + h] = {"error": bv.get("error"), "k": (bv.get("line") or {}).get("k"),
                                      "order_n": len(bv.get("order") or [])}
        row["low" if low else "plain"] = line
        print("%-24s %s %5.1fs humps %s %s" % (lab[:24], "LOW  " if low else "plain", dt, j.get("humps"),
                                               ("left out %s" % (j.get("low") or {}).get("contacts")) if low else ""),
              flush=True)
        for m in ("bite", "pca", "pca_gap", "delta", "delta_mid", "bite_top", "pca_top", "pca_gap_top", "delta_top",
                  "delta_mid_top", "bite_bottom", "pca_bottom", "pca_gap_bottom", "delta_bottom", "delta_mid_bottom"):
            x = line.get(m) or {}
            print("     %-17s %4s/%-4s SI %-7s hump SI %-7s nan %-3s %s" % (
                m, x.get("n1"), x.get("n2"), x.get("si"), x.get("hump_si"), x.get("nan"),
                ("WHY " + str(x.get("why"))) if x.get("why") else ""), flush=True)
    OUT[lab] = row
with open(os.path.join(os.path.dirname(__file__), "split15_v%d.json" % V), "w") as fh:
    json.dump(OUT, fh, indent=1)
