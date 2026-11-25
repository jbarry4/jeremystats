"""Jeremy menu, last step: copy the pages, write the tables and copy the code into Lab Figures/Jeremy_Menu_112426.
Then merge the PDF with miniconda's python: j_merge.py."""
import glob
import json
import os
import pickle
import shutil
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figlib as F  # noqa: E402
import jpages as J  # noqa: E402

DEST = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\Jeremy_Menu_112426"
for sub in ("pages", "tables", "code"):
    os.makedirs(os.path.join(DEST, sub), exist_ok=True)
for f in sorted(glob.glob(os.path.join(HERE, "outj", "*.*"))):
    shutil.copy2(f, os.path.join(DEST, "pages", os.path.basename(f)))

TAB = os.path.join(DEST, "tables")
P, ref = J.B()["per"]["v6"], J.B()["ref"]["v6"]
rows = []
for l in J.LABS:
    d = P[l]
    row = {"mouse": l, "group": F.subgroup(l), "knockout_pct": F.ko(l), "DS_events": d["n"], "DS1_events": d["n1"], "DS2_events": d["n2"],
           "minutes": round(d["dur_min"], 2), "separation_index": d["si"],
           "makes_both": bool(d["si"] is not None and min(d["n1"], d["n2"]) >= max(5, 0.05 * d["n"]) and d["si"] >= 0.45),
           "sink_control_eq_1": d["all"]["sink"] / ref, "slope_10_90_control_eq_1": d["all"]["slope"] / ref,
           "rise_10_90_ms": d["all"]["rise"], "fast_power_at_standard_sink_dB": J.es_fit(l)[0], "fast_power_dB_per_doubling": J.es_fit(l)[1]}
    for k in (1, 2):
        if "ds%d" % k in d:
            row["DS%d_sink_control_eq_1" % k] = d["ds%d" % k]["sink"] / ref
            row["DS%d_rise_ms" % k] = d["ds%d" % k]["rise"]
            row["DS%d_fast_power_at_standard_sink_dB" % k] = J.es_fit(l, J.B()["events_v6"][l]["types"] == k)[0]
    rows.append(row)
pd.DataFrame(rows).to_csv(os.path.join(TAB, "q1_q2_per_mouse.csv"), index=False)

rows = []
for es in J.B()["sets"]:
    Pe, re_ = J.B()["per"][es], J.B()["ref"][es]
    for l in J.LABS:
        for (blade, layer), v in Pe[l]["all"]["layers"].items():
            rows.append({"filter_set": es, "mouse": l, "group": F.subgroup(l), "knockout_pct": F.ko(l), "blade": blade, "layer": layer,
                         "sink_control_eq_1": v / re_})
pd.DataFrame(rows).to_csv(os.path.join(TAB, "q3_q5_layer_sinks_every_filter.csv"), index=False)

Q = J.FQ()
rows = []


def base(l, band, cls, blade="", layer="", signal=""):
    return {"mouse": l, "group": F.subgroup(l), "knockout_pct": F.ko(l), "band": band, "class": cls.replace("TZ", "BT"),
            "blade": blade, "layer": layer, "signal": signal}


for l, m in Q["mice"].items():
    for band, br in m["bands"].items():
        ref_b = J.ref_reads(band)
        rng = J.fast_range(band)
        for cls, v in br["deep"].items():
            rows.append(dict(base(l, band, cls, signal="csd"), measure="deepest sink at the DS peak, control DS = 1", value=v / ref_b))
        for (cls, blade, layer), v in br["sink"].items():
            rows.append(dict(base(l, band, cls, blade, layer, "csd"), measure="layer sink at the DS peak, control DS = 1", value=v / ref_b))
        for (cls, blade, layer, sig), (pkf, cen) in br["whole"].items():
            rows.append(dict(base(l, band, cls, blade, layer, sig), measure="dominant frequency, Hz (peak of the event's own spectrum, "
                             "+-50 ms, 5-300 Hz)", value=pkf))
            rows.append(dict(base(l, band, cls, blade, layer, sig), measure="spectral centroid, Hz (event's own spectrum, 5-300 Hz)",
                             value=cen))
        if rng is not None:
            for (cls, blade, layer, sig), spec in br["fast_spec"].items():
                c_, g_ = J.fast_metrics(spec, rng[0], rng[1], rng[2])
                rows.append(dict(base(l, band, cls, blade, layer, sig), measure="fast-power center, Hz (added power, %d-%d Hz)"
                                 % (rng[0], rng[1]), value=c_))
                rows.append(dict(base(l, band, cls, blade, layer, sig), measure="fast gain, dB over the moment before (%d-%d Hz)"
                                 % (rng[2], rng[1]), value=g_))
pd.DataFrame(rows).to_csv(os.path.join(TAB, "q4_q5_q7_q8_reads_per_mouse.csv"), index=False)
T, cen = J.strict_table()
shp, _n_und, _n_both = J.strict_shape()
T["undecided_wider_than_DS_pct"] = [shp[l]["wide_pct"] for l in T.mouse]
T["undecided_halfwidth_over_DS"] = [shp[l]["hw_ratio"] for l in T.mouse]
T["DS_median_fast_power_dB"] = [shp[l]["ds_hf"] for l in T.mouse]
T.rename(columns={"n": "events", "ds": "DS", "ied": "IED_class", "both": "inside_both", "neither": "outside_both", "und": "undecided",
                  "pct": "undecided_pct", "hi": "undecided_above_DS_fast_power", "lo": "undecided_below_DS_fast_power",
                  "und_hf": "undecided_median_fast_power_dB"}).to_csv(os.path.join(TAB, "every_mouse_undecided_strict_workflow.csv"), index=False)

for f in ("jpages.py", "j1_battery.py", "j2_freq.py", "m10_reads_all.py", "m2_extract.py", "m7_uprof.py", "m3_profiles.py", "figlib.py",
          "menu_data.py", "stats_lib.py", "outlier.py", "pages_a.py", "j_package.py", "j_merge.py", "j_check_ied.py",
          "j_check_und.py", "j_check_und2.py", "jfollow.py"):
    p = os.path.join(HERE, f)
    if os.path.exists(p):
        shutil.copy2(p, os.path.join(DEST, "code", f))
print("packaged to", DEST)
