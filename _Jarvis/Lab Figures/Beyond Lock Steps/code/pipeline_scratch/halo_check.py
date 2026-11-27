"""Check the Halo's gauges against the run's own classes, on a real run."""
import json
import sys
import urllib.request

sys.path.insert(0, r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app")
from backend import rcworkflow  # noqa: E402

aid, ver = sys.argv[1], sys.argv[2]
got = json.load(urllib.request.urlopen(
    "http://127.0.0.1:8733/api/rootcanal/workflow/%s?version=%s" % (aid, ver),
    timeout=120))
run = got["payload"]["run"]
b = run["borders"]
col = run["cols"]
ga, gb, cen = rcworkflow.halo_gauges(col, b["ds"]["border"], b["ds"]["grace"],
                                     b["pspike"]["border"], b["pspike"]["grace"])
bad = 0
for c, a, p in zip(col["cls"], ga, gb):
    if a is None or p is None:
        continue
    ina, inp = a <= 1 + 1e-6, p <= 1 + 1e-6
    want = "both" if ina and inp else "ds" if ina else "pspike" if inp else "neither"
    if want != c:
        bad += 1
print("events", len(col["cls"]), "class/gauge disagreements", bad)
print("centres", cen)
print("plain", rcworkflow.counts(col["cls"]))
for h in ({"reach": 2, "margin": 1.5}, {"reach": 2.5, "margin": 1.25},
          {"reach": 1.5, "margin": 2}):
    print(h, rcworkflow.counts(rcworkflow.halo_classes(col["cls"], ga, gb, h)))
