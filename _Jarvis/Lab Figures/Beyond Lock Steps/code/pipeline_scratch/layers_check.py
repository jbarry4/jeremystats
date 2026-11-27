"""Which of the DS recordings carry real layer labels (not placeholders) in Jarvis's layer store?"""
import glob
import json
import os
from collections import Counter

L = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\app\GUI_logs\layers"
GIDS = {
    "m2": "s79ba9ba163c4", "m6": "s9eb56573e0b4", "m21": "s37c7c8edfe10", "m22": "s0a9e96cf1739",
    "m26": "s016e132432c8", "m59": "sd42a6992b76c", "m60": "s8d7f397b9708", "m61": "s43b16cd74bcb",
    "m8": "sba57286bdee3", "m33": "s6cdd64d005c4", "m1": "s45bae70722f2", "m13": "s38b9e61c5684",
    "m28": "s4a67210fc7ac", "m7": "s500a5aec223e", "m3": "sd0d0bded958b", "m5": "sc74c98b2495d",
    "m34": "s14510e30e1bd",
}
for lab, g in GIDS.items():
    files = glob.glob(os.path.join(L, g + "@*.json"))
    merged = {}
    strata = set()
    vers = 0
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        lab_map = d.get("labels") or {}
        # labels may be {ch: region} or {ch: {"v":..., "at":...}}
        for ch, v in lab_map.items():
            if isinstance(v, dict):
                v = v.get("v") or v.get("region") or v.get("value")
            merged[ch] = v
        for k in d:
            if k.startswith("strata") or k in ("bands", "steps"):
                strata.add(k)
        vers += len(d.get("versions") or [])
    c = Counter(merged.values())
    order = ["ca1_slm", "dg_oml1", "dg_mml1", "dg_iml1", "dg_gcl1", "hil", "dg_gcl2", "dg_iml2", "dg_mml2", "dg_oml2"]
    real = {k: c[k] for k in order if c.get(k)}
    ph = {k: c[k] for k in ("ca1_sr", "dg", "dg2") if c.get(k)}
    print("%-4s files %d  versions %d  real %s  placeholders %s  keys %s" % (lab, len(files), vers, real, ph, sorted(strata)))
