"""A check page per placed recording (PNG): what was found, where it lands.

    python tools/sextant/figure.py [mice...]  -> GUI_logs/.cache/sextant/figs/

Left: the evidence down the shank (each curve scaled to its own range) with
the detectors' landmarks. Middle: the layers the atlas puts under each
contact for the best pose, beside the landmarks it was matched to. Right: the
coronal atlas section through the probe, the best probe solid and the cloud
faint.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, APP)

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

from backend.sextant import atlas as A  # noqa: E402
from backend.sextant import cohort, evidence  # noqa: E402

LOGS = os.path.join(APP, "GUI_logs")
OUT = os.path.join(LOGS, ".cache", "sextant")

COL = {0: "#ffffff", 30: "#d9d4cc", 31: "#f2efe6", 32: "#cfe3f0", 33: "#c9c2b6", 34: "#c9c2b6",
       35: "#bdb6a9", 36: "#d0c8ba", 37: "#c7d1c2", 38: "#cfc9bd",
       10: "#9ec5e8", 11: "#2f6fb3", 12: "#b9d6f0", 13: "#7fb0dc", 14: "#9ec5e8", 15: "#2f6fb3",
       16: "#b9d6f0", 17: "#7fb0dc", 18: "#a9c9a4", 19: "#3f8a3a", 20: "#c6dfc2", 21: "#c6dfc2",
       22: "#a9c9a4", 23: "#d8c7e6", 24: "#d8c7e6", 25: "#e0e0e0", 26: "#e0e0e0", 27: "#f4f1ea", 28: "#f4f1ea",
       1: "#f6c99a", 2: "#f0a35e", 3: "#f7dcc0", 4: "#c0392b", 5: "#f3e3a2", 6: "#c0392b", 7: "#f7dcc0",
       8: "#f0a35e", 9: "#f6c99a"}
LM_COL = {"sp": "#2f6fb3", "spw_rev": "#2f6fb3", "sr_sink": "#5aa0d8", "slm_src": "#7fb0dc",
          "fissure": "#8e44ad", "ml_a": "#e67e22", "ml_b": "#e67e22", "dg_core": "#c0392b",
          "hil_gam": "#c0392b", "dg_end": "#7f8c8d", "th_top": "#555555"}


def lut():
    c = np.ones((256, 3))
    for k, v in COL.items():
        c[k] = matplotlib.colors.to_rgb(v)
    return ListedColormap(c)


def page(atl, rec, pl, ev):
    fig = plt.figure(figsize=(15, 8.5))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.25, 0.45, 1.6], wspace=0.25)
    ax = fig.add_subplot(gs[0])
    bad = ev["is_bad"]
    y = np.arange(1, 65)

    def nz(v):
        v = np.where(bad, np.nan, np.asarray(v, float))
        lo, hi = np.nanmin(v), np.nanmax(v)
        return (v - lo) / (hi - lo) if hi > lo else v * 0
    curves = [("multiunit", ev["c_mua"], "#555555"),
              ("ripple/theta (still)", np.log(ev["c_ripple"] / ev["c_theta_still"]), "#2f6fb3"),
              ("theta amplitude", np.abs(ev["theta_cx"]), "#8e44ad"),
              ("fast gamma", ev["c_fast_gamma"], "#c0392b")]
    for i, (name, v, c) in enumerate(curves):
        ax.plot(nz(v) + i * 1.15, y, color=c, lw=1.4)
        ax.text(i * 1.15 + 0.5, -1.5, name, ha="center", fontsize=8, color=c)
    xo = len(curves) * 1.15
    for name, key, c in (("sharp wave", "spw", "#2f6fb3"), ("DS (LFP)", "ds_peak", "#e67e22")):
        if key in ev:
            v = np.asarray(ev[key], float)
            m = np.nanmax(np.abs(np.where(bad, np.nan, v)))
            ax.plot(0.5 * v / m + xo + 0.5, y, color=c, lw=1.4)
            ax.axvline(xo + 0.5, color="#dddddd", lw=0.6, zorder=0)
            ax.text(xo + 0.5, -1.5, name, ha="center", fontsize=8, color=c)
            xo += 1.15
    if "ds_peak" in ev:
        cs = evidence.csd(ev["ds_peak"], bad)
        m = np.nanmax(np.abs(cs))
        ax.fill_betweenx(y, xo + 0.5, xo + 0.5 + 0.5 * np.nan_to_num(cs / m), color="#e67e22", alpha=0.5, lw=0)
        ax.text(xo + 0.5, -1.5, "DS current", ha="center", fontsize=8, color="#e67e22")
        xo += 1.15
    for l in pl["landmarks"]:
        c = LM_COL.get(l["key"].replace("ps_", "").replace("bt_", ""), "#999999")
        ax.plot([-0.2, xo], [l["x"] + 1, l["x"] + 1], color=c, lw=0.8, ls="--", alpha=0.8)
        ax.text(xo + 0.05, l["x"] + 1, l["key"], fontsize=7, color=c, va="center")
    ax.set_ylim(65, -3)
    ax.set_xlim(-0.3, xo + 1.0)
    ax.set_xticks([])
    ax.set_ylabel("contact (1 = top)")
    ax.set_title("%s (%s) %s  - what the recording shows" % (rec["mouse"], rec["group"], rec["gid"]), fontsize=10, loc="left")

    ax2 = fig.add_subplot(gs[1])
    lay = pl["best"]["layers"]
    codes = np.array([atl.code.get(k, 0) for k in lay])[:, None]
    ax2.imshow(codes, cmap=lut(), vmin=0, vmax=255, aspect="auto", extent=(0, 1, 64.5, 0.5), interpolation="nearest")
    prev = None
    for k, name in enumerate(lay):
        if name != prev:
            ax2.text(1.05, k + 1, atl.label.get(atl.code.get(name, 0)) or name, fontsize=7, va="top")
            prev = name
    for r in pl["residuals"]:
        if r["atlas"] is not None:
            ax2.plot([0, 1], [r["atlas"] + 1] * 2, color="k", lw=0.6)
            ax2.plot([0.5], [r["found"] + 1], "o", ms=3, color=LM_COL.get(r["key"].replace("ps_", "").replace("bt_", ""), "#999"))
    ax2.set_ylim(64.5, 0.5)
    ax2.set_xticks([])
    ax2.set_yticks([])
    ax2.set_title("atlas layers\n(dot = found, line = atlas)", fontsize=9)

    ax3 = fig.add_subplot(gs[2])
    b = pl["best"]
    c1, c64 = np.array(b["ccf"][0]), np.array(b["ccf"][1])
    mid = (c1 + c64) / 2
    i_ap = int((mid[0] - atl.origin[0]) // atl.um)
    sl = atl.L[i_ap]                                  # DV x ML
    x0, x1 = 5700, 9300
    ax3.imshow(sl, cmap=lut(), vmin=0, vmax=255, extent=(x0, x1, atl.origin[1] + sl.shape[0] * 10, atl.origin[1]),
               interpolation="nearest")
    for cl in pl["cloud"]:
        p, q = np.array(cl[0]), np.array(cl[1])
        ax3.plot([p[2], q[2]], [p[1], q[1]], color="k", alpha=0.08, lw=1)
    ax3.plot([c1[2], c64[2]], [c1[1], c64[1]], color="k", lw=2.2)
    ax3.plot([c1[2]], [c1[1]], "o", color="k", ms=4)
    ax3.set_xlim(5700, 8500)
    ax3.set_ylim(3600, 600)
    ax3.set_aspect("equal")
    r = pl["ranges"]
    ax3.set_title("best: entry AP %.2f ML %.2f (side %s), tilts %.1f / %.1f deg, size %.2f\n"
                  "95%%: AP %.2f..%.2f  ML %.2f..%.2f   chi2 %.1f" % (
                      b["entry"]["ap"], b["entry"]["ml"], rec["hemisphere"], b["tilt_ml"], b["tilt_ap"], b["scale"],
                      r["entry_ap"][0], r["entry_ap"][2], r["entry_ml"][0], r["entry_ml"][2], pl["chi2"]), fontsize=9, loc="left")
    ax3.set_xlabel("CCF ML (um)  [coronal section at the probe's middle]")
    os.makedirs(os.path.join(OUT, "figs"), exist_ok=True)
    p = os.path.join(OUT, "figs", "%s_%s.png" % (rec["mouse"], rec["gid"]))
    fig.savefig(p, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return p


def main(argv):
    atl = A.load()
    for rec in cohort.recordings(LOGS, only=set(argv) or None):
        d = os.path.join(OUT, rec["gid"])
        if not os.path.exists(os.path.join(d, "placement.json")):
            continue
        pl = json.load(open(os.path.join(d, "placement.json"), encoding="utf-8"))
        ev = evidence.load(os.path.join(d, "evidence.npz"))
        print(page(atl, rec, pl, ev))


if __name__ == "__main__":
    main(sys.argv[1:])
