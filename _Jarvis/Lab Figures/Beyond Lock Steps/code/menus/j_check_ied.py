"""Check: the red (IED-class) events against the same mice's DS, paired, for every question-7 measure."""
import os
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jpages as J  # noqa: E402
import menu_data as D  # noqa: E402
import stats_lib as S  # noqa: E402

rc = D.rc()
h = rc[rc.wf == "halo"]


def med(l, k, col):
    return float(h[(h.lab == l) & (h.kind == k)][col].median())


refn = J.ref_reads("notch")
gets = {
    "fast power": lambda l, k: med(l, k, "hf"),
    "amplitude": lambda l, k: med(l, k, "amp"),
    "deepest sink notch": lambda l, k: float(J.fq(l, "notch", "deep", k)) / refn,
    "deepest sink 5-100": lambda l, k: float(J.fq(l, "5-100", "deep", k)) / J.ref_reads("5-100"),
}
for key in J.KEYS4:
    gets["sink %s %s" % key] = lambda l, k, key=key: J.fq(l, "notch", "sink", (k,) + key) / refn
    gets["center %s %s" % key] = lambda l, k, key=key: J.fast_of(l, "notch", k, key, "csd", 0)
    gets["gain %s %s" % key] = lambda l, k, key=key: J.fast_of(l, "notch", k, key, "csd", 1)
for name, g in gets.items():
    ds = [g(l, "DS") for l in J.IEDP]
    bt = [g(l, "TZ") for l in J.IEDP]
    ied = [g(l, "IED") for l in J.IEDP]
    wt = [g(l, "DS") for l in J.CTL]
    p_ied_ds = J.paired_p(ied, ds)
    p_bt_ds = J.paired_p(bt, ds)
    p_ied_wt = S.two([v for v in wt if np.isfinite(v)], [v for v in ied if np.isfinite(v)])["p"]
    p_bt_wt = S.two([v for v in wt if np.isfinite(v)], [v for v in bt if np.isfinite(v)])["p"]
    p_ied_bt = J.paired_p(ied, bt)
    print("%-26s BT/DS %-7.3g IED/DS %-7.3g BT/WT %-7.3g IED/WT %-7.3g IED/BT %-7.3g  IED-DS %s" % (
        name, p_bt_ds, p_ied_ds, p_bt_wt, p_ied_wt, p_ied_bt, np.round(np.array(ied) - np.array(ds), 2)))
