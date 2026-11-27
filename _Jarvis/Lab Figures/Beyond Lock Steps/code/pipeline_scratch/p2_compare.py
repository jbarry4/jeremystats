"""Phase 2 check: each workflow's new run against its previous run, per mouse.
m1's events are paired through Lock's own moves (old time -> new time). Read only."""
import collections
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import eventbank, store as storemod, bracesset as brsetmod  # noqa: E402
from backend import artifacts as _a  # noqa: E402,F401

logs = os.path.join(APP, "GUI_logs")
STORE = storemod.Store(logs, auto_stage=False)
from backend import app as A  # noqa: E402
AR = A.ARTIFACTS

lock = brsetmod.BracesSets(logs, STORE).get("br1f1b0830ec")
B = A.BANK
v1, _ = B.events_at(B.get("bfa98498290b"), lock["from_version"])
moves, *_ = brsetmod.resolve(lock)
newt = {round(float(v1[i]["start"]), 4): round(float(t), 4) for i, t in moves.items()}
M1 = "s45bae70722f2"


def classes(aid, v):
    run = (AR.payload(aid, v) or {}).get("run") or {}
    cols = run["cols"]
    gids = cols["gids"]
    out = {}
    for cls, g, t in zip(cols["cls"], cols["g"], cols["t"]):
        if g is None or t is None:
            continue
        out[(gids[int(g)], round(float(t), 4))] = cls
    return out


for aid, old_v, new_v, name in (("4a29af93e601", 2, 3, "10% DS workflow (behind v7/v8)"),
                                ("6fa7fef7b7a3", 3, 4, "Halo Ambiguous (v6, the Halo set)"),
                                ("a7eee6a6ca9f", 2, 3, "No P-spikes Ambiguous (v8)")):
    a, b = classes(aid, old_v), classes(aid, new_v)
    others_same = {k: v for k, v in a.items() if k[0] != M1} == {k: v for k, v in b.items() if k[0] != M1}
    # m1, paired through Lock's moves
    am = {k[1]: v for k, v in a.items() if k[0] == M1}
    bm = {k[1]: v for k, v in b.items() if k[0] == M1}
    pairs = collections.Counter()
    unmatched = 0
    for t, c in am.items():
        t2 = newt.get(t, t)
        if t2 in bm:
            pairs[(c, bm[t2])] += 1
        else:
            unmatched += 1
    print("\n%s  v%d -> v%d" % (name, old_v, new_v))
    print("  other 17 recordings identical:", others_same)
    print("  m1 before:", dict(collections.Counter(am.values())))
    print("  m1 after: ", dict(collections.Counter(bm.values())))
    print("  m1 changed class:", {"%s -> %s" % k: n for k, n in pairs.items() if k[0] != k[1]}, "| unpaired", unmatched)
