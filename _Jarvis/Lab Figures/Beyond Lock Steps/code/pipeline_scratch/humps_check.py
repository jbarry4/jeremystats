"""The humps on real arrays: the Bite line's split and SI under humps vs
bumps, the view's new fields, and the blobs."""
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402
from backend import extraction as EX  # noqa: E402
from backend import blobs as B  # noqa: E402
import numpy as np  # noqa: E402

room = A._er_rooms().get("dentate_spike")
pay = A.ARTIFACTS.payload(room["id"], 4)
for lab in ("m6 s4", "m22 s3", "m26 s2", "m13 s2", "m60 s1"):
    rec = next(r for r in pay["recordings"] if lab in r["session_label"])
    Ar, rule, flip = A._er_split_arrays(dict(rec))
    print(lab, "record sink", A._er_rec_sink(rec), "arrays sink", EX.bite_sink(Ar))
    for sink in ("bumps", "humps"):
        A2 = {k: v for k, v in Ar.items() if not k.startswith("_")}
        EX.add_bite(A2, rule, flip, sink=sink)
        v = EX.bite_view(A2)
        bm = v["bumps"]
        print("   %-6s split %s/%s SI %s verdict %s | hump_at %s camel %s short %s peaks[0] %s" % (
            sink, v["scores"]["n1"], v["scores"]["n2"], v["scores"]["si"], v["verdict"]["word"],
            bm.get("hump_at"), bm.get("camel"), bm.get("short"), bm["peaks"][0]))
    summ, ev = B.recording(Ar, 50.0, classes=np.asarray(Ar["types_bite"]))
    print("   blobs: sink %s kinds %s camel %s; top fwhm median %s bottom %s" % (
        summ["sink"], summ["kinds"], summ["camel"],
        summ["cls"]["all"]["top"]["stats"]["fwhm_ms"]["median"],
        summ["cls"]["all"]["bottom"]["stats"]["fwhm_ms"]["median"]))
    summ_b, _ = B.recording(Ar, 50.0, classes=np.asarray(Ar["types_bite"]), sink="bumps")
    print("   blobs (bumps): kinds %s third_big %s; top fwhm %s bottom %s" % (
        summ_b["kinds"], summ_b["third_big"], summ_b["cls"]["all"]["top"]["stats"]["fwhm_ms"]["median"],
        summ_b["cls"]["all"]["bottom"]["stats"]["fwhm_ms"]["median"]))
