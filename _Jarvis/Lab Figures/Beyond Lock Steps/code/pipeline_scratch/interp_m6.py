"""m6 s4: 38 and 39 interpolated (the user's call, 2026-11-13), through the
app's own route; the card before and after; and the "no DS1" call and the
length checked in memory (the call faked, nothing written)."""
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
from backend.app import app  # noqa: E402
from backend import app as A  # noqa: E402
from backend import extraction as EX  # noqa: E402

c = app.test_client()
room = A._er_rooms()["dentate_spike"]
AID = room["id"]


def card(v, lab):
    j = c.get("/api/extraction/%s?version=%d" % (AID, v)).get_json()
    return next(r for r in j["payload"]["recordings"] if lab in r["session_label"])


def say(name, r):
    b = r.get("bite") or {}
    A_, _r, _f = A._er_split_arrays(r)
    bv = EX.bite_view(A_)
    print("  %-8s interp %-8s counts %s  Bite SI %s (%s)  notched %s of %s  length %s s  split %s" % (
        name, r.get("interp"), r.get("counts"), (b.get("scores") or {}).get("si"), (b.get("verdict") or {}).get("word"),
        bv["bumps"]["camel"], bv["n"], r.get("duration_s"), (r.get("split") or {}).get("method")), flush=True)


for v in (8, 6):
    print("v%d m6 s4 before:" % v)
    say("before", card(v, "m6 s4"))
r0 = card(8, "m6 s4")
j = c.post("/api/extraction/interp", json={"artifact_id": AID, "version": 8, "gid": r0["gid"],
                                           "contacts": [38, 39]}).get_json()
print("interp route:", j.get("ok"), j.get("error"), "interps:", json.dumps(j.get("interps")), flush=True)
for v in (8, 6):
    print("v%d m6 s4 after:" % v)
    say("after", card(v, "m6 s4"))

# Refused, with words: a contact off the shank, and one without two good each side.
for bad in ([70], [63], [1, 2]):
    jj = c.post("/api/extraction/interp", json={"artifact_id": AID, "version": 8, "gid": r0["gid"],
                                                "contacts": bad}).get_json()
    print("  refuse %s -> %s" % (bad, jj.get("error")), flush=True)
# ...and the refusals did not change what is kept.
print("  still kept:", json.dumps(A._er_interps("dentate_spike")), flush=True)

# "No DS1", in memory: _er_seps faked for one recording, nothing written.
real = A._er_seps
lab = "m28 s2"
rr = card(8, lab)
A._er_seps = lambda room_, folder_: dict(real(room_, folder_), **{rr["gid"]: {"verdict": "no_ds1"}})
try:
    pay = A.ARTIFACTS.payload(AID, 8)
    A._er_apply_splits(pay, A._er_splits(pay.get("room"), A._er_pay_folder(pay)))
    r = next(x for x in pay["recordings"] if x["gid"] == rr["gid"])
    print("no DS1 on %s: no_ds1 %s counts %s classes %s" % (lab, r.get("no_ds1"), r.get("counts"),
                                                          [(k["c"], k["n"]) for k in r["classes"]]), flush=True)
    m = EX.metrics_of(r, True)          # swapped by hand or not, it is DS2
    print("  metrics (as if swapped):", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()}, flush=True)
    print("  sep_binary:", EX.sep_binary("no_ds1"), " sep_shown:", EX.sep_shown(r, "no_ds1"), flush=True)
    rows = A._er_impression_rows(A.ARTIFACTS.payload(AID, 8))
    row = next(x for x in rows if x["gid"] == rr["gid"])
    print("  impression row: call %s counts %s" % (row["call"], row.get("counts")), flush=True)
    labs, cls = A._blob_labels([{"call": "no_ds1", "group": "PTEN"}, {"call": "yes", "group": "CTL"}], "sep", [], "2")
    labs1, _c = A._blob_labels([{"call": "no_ds1", "group": "PTEN"}], "sep", [], "1")
    print("  blob labels, DS2:", labs, " DS1:", labs1, flush=True)
finally:
    A._er_seps = real

# The timeline.
tl = c.get("/api/extraction/%s/timeline?version=8&gid=%s" % (AID, r0["gid"])).get_json()
print("timeline: ok %s, %d events, %.0f s, theta contact %s, %d bins" % (
    tl.get("ok"), len(tl.get("events") or []), tl.get("duration_s") or 0,
    (tl.get("theta") or {}).get("contact"), len((tl.get("theta") or {}).get("power") or [])), flush=True)
durs = [r.get("duration_s") for r in c.get("/api/extraction/%s?version=8" % AID).get_json()["payload"]["recordings"]]
print("lengths on v8's cards: %d of %d, %s" % (sum(1 for d in durs if d), len(durs),
                                                [round(d / 60, 1) if d else None for d in durs]), flush=True)
