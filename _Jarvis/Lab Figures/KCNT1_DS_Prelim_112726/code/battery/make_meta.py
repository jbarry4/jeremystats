"""data/meta.json for the KCNT1 battery: one row per recording, the fields the harness, analyze and the menus read.
Run after build_dataset.py has frozen the Halo (v6) and Strict (v8) slots.

Genotype, sex and recording facts are from the lab's "KCNT1 Recording Sessions" sheet as summarized on 2026-11-25
(background/decisions/kcnt1-ds-groups-1125.md): WT 1619, 526 female; Het 1609, 576 male; Hom 1603, 306 female.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dsdata  # noqa: E402

SEX = {"m1619": "F", "m526": "F", "m1609": "M", "m576": "M", "m1603": "F", "m306": "F"}
ORDER = ["m1619", "m526", "m1609", "m576", "m1603", "m306"]
n8 = {}
if os.path.isfile(os.path.join(HERE, "data", "ds_v8.pkl")):
    n8 = {r.lab: int(r.n) for r in dsdata.load("v8")}
rows = []
for r in sorted(dsdata.load("v6"), key=lambda r: ORDER.index(r.lab)):
    k = r.landmarks or {}
    blade = None
    if k.get("U") is not None and k.get("L") is not None:
        blade = float(abs(k["L"] - k["U"]) * dsdata.SPACING_UM)
    rows.append({"lab": r.lab, "gid": r.gid, "label": r.label, "group": r.group, "subgroup": r.subgroup, "ko": float(r.ko),
                 "dose": float(r.ko), "sex": SEX.get(r.lab), "n_v6": int(r.n), "n_v8": n8.get(r.lab), "dur_min": float(r.dur_min),
                 "year": int(r.year), "n_bad": len(r.bad), "band_contacts": int(r.band[1] - r.band[0] + 1), "blade_um": blade,
                 "ok": bool(r.ok)})
    print(rows[-1])
json.dump(rows, open(os.path.join(HERE, "data", "meta.json"), "w"), indent=1)
print("saved", len(rows))
