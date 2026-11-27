"""Every pair of Spike stamps under 1 ms apart in the 18 Confluence sets,
drawn from the pools' own Root Canal reads, for a by-eye check. Read only."""
import os
import pickle
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
sys.path.insert(0, APP)
from backend import eventbank, store as storemod  # noqa: E402

S = os.path.dirname(os.path.abspath(__file__))
OUT = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\duplicate_check"
os.makedirs(OUT, exist_ok=True)
logs = os.path.join(APP, "GUI_logs")
B = eventbank.EventBank(logs, storemod.Store(logs, auto_stage=False))
IDS = {"bfa98498290b": "m1", "afa70b62f372": "m13", "41dd94702761": "m2", "edc1a5080093": "m21", "43a2cfedde17": "m22",
       "f4c18a9a8bd4": "m26", "35c325a44d44": "m28", "db66d3c694fd": "m3", "a62d1b78448b": "m33", "eaecc4a5e194": "m34",
       "b60578899091": "m5", "8aad148bd6f6": "m51", "1429bf1f239f": "m59", "cb139fb2ea29": "m6", "d4a4bcb4e47f": "m60",
       "ab69363ee622": "m61", "ece9a84acdea": "m7", "2a8e47760eea": "m8"}
reads = dict(l.strip().split(" ") for l in open(os.path.join(S, "pool_reads.txt")) if l.strip())
halo = {d["lab"]: np.asarray(d["times_s"], float) for d in
        pickle.load(open(r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\data\ds_v6.pkl", "rb"))}

pairs, gaps_all, near_real = [], [], []
for eid, lab in IDS.items():
    rec = B.get(eid)
    t = np.array(sorted(float(e["start"]) for e in rec["events"] if e.get("label_id") == "spike"))
    g = np.diff(t)
    gaps_all.extend(g * 1000)
    rh = reads[eid].split(":")[-1]
    z = np.load(os.path.join(logs, ".cache", "rootcanal", "%s__%s.npz" % (rec["gid"], rh)), allow_pickle=True)
    zt = z["t"]
    for i in np.where(g < 0.001)[0]:
        pairs.append((lab, rec["gid"], t[i], t[i + 1], z, zt))
    for i in np.where((g >= 0.001) & (g < 0.020))[0]:
        near_real.append((lab, rec["gid"], t[i], t[i + 1], z, zt))
print("pairs", len(pairs), "| consecutive gaps 1-30 ms", len(near_real))

FS, HALF = 2000.0, 500
tt = (np.arange(1001) - HALF) / FS * 1000


def snip(z, zt, t):
    j = int(np.argmin(np.abs(zt - t)))
    assert abs(zt[j] - t) < 1e-4, (t, zt[j])
    x = z["snip"][j].astype(float)
    x = x - np.median(x, axis=1, keepdims=True)
    import json as _j
    m = _j.loads(str(z["meta"]))
    for b in (m.get("bad") or {}):
        if int(b) in m["nums"]:
            x[m["nums"].index(int(b))] = np.nan
    return x, j


def in_halo(lab, t):
    h = halo.get(lab)
    return h is not None and np.min(np.abs(h - t)) < 0.0006


def panel(fig, gs, row, item, title_extra=""):
    lab, gid, ta, tb, z, zt = item
    xa, ja = snip(z, zt, ta)
    xb, jb = snip(z, zt, tb)
    ch = int(np.nanargmax(np.nanmax(np.abs(xa[:, HALF - 10:HALF + 10]), axis=1)))
    gap = (tb - ta) * 1000
    ha, hb = in_halo(lab, ta), in_halo(lab, tb)
    # a: the two events on the biggest contact, +-100 ms
    ax = fig.add_subplot(gs[row, 0])
    ax.plot(tt, xa[ch], color="#1f5fbf", lw=1.4, label="stamp A")
    ax.plot(tt + gap, xb[ch], color="#d9480f", lw=0.8, ls="--", label="stamp B")
    ax.axvline(0, color="#1f5fbf", lw=0.5)
    ax.axvline(gap, color="#d9480f", lw=0.5)
    ax.set_xlim(-100, 100)
    ax.set_xlabel("ms from stamp A", fontsize=6)
    ax.set_ylabel("LFP, contact %d (µV)" % (ch + 1), fontsize=6)
    ax.tick_params(labelsize=5.5)
    ax.set_title("%s  %.4f s  ·  gap %.3f ms%s" % (lab, ta, gap, title_extra), fontsize=7, loc="left")
    ax.text(0.99, 0.03, "Halo set holds: %s" % ("both" if ha and hb else "one" if (ha or hb) else "neither"),
            transform=ax.transAxes, ha="right", fontsize=5.5, color="#555")
    if row == 0:
        ax.legend(fontsize=5.5, frameon=False, loc="upper right")
    # b: depth x time for stamp A
    ax = fig.add_subplot(gs[row, 1])
    v = np.nanpercentile(np.abs(xa[:, HALF - 200:HALF + 200]), 99) or 1
    ax.imshow(xa[:, HALF - 200:HALF + 201], aspect="auto", cmap="RdBu_r", vmin=-v, vmax=v,
              extent=[tt[HALF - 200], tt[HALF + 200], xa.shape[0], 1])
    ax.axvline(0, color="#1f5fbf", lw=0.6)
    ax.axvline(gap, color="#d9480f", lw=0.6, ls="--")
    ax.set_xlabel("ms from stamp A", fontsize=6)
    ax.set_ylabel("contact (read order)", fontsize=6)
    ax.tick_params(labelsize=5.5)
    ax.set_title("every contact, stamp A", fontsize=6.5, loc="left")
    # c: difference between the two snippets after lining them up
    ax = fig.add_subplot(gs[row, 2])
    a_, b_ = xa[:, HALF - 100:HALF + 100].ravel(), xb[:, HALF - 100:HALF + 100].ravel()
    ok = np.isfinite(a_) & np.isfinite(b_)
    same = np.corrcoef(a_[ok], b_[ok])[0, 1]
    ax.plot(tt, xa[ch] - xb[ch], color="#444", lw=0.8)
    ax.set_xlim(-100, 100)
    ax.set_xlabel("ms from stamp A", fontsize=6)
    ax.set_ylabel("A − B, same contact (µV)", fontsize=6)
    ax.tick_params(labelsize=5.5)
    ax.set_title("A and B on all contacts, r = %.4f" % same, fontsize=6.5, loc="left")
    return same


rs = []
with PdfPages(os.path.join(OUT, "Duplicate_stamps_check.pdf")) as pdf:
    # page 1: every gap between neighbouring spikes
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    g = np.array(gaps_all)
    bins = np.logspace(-2.5, 4.5, 90)
    axs[0].hist(g, bins=bins, color="#888")
    axs[0].hist(g[g < 1], bins=bins, color="#d9480f")
    axs[0].set_xscale("log")
    axs[0].axvline(1, color="k", lw=0.6, ls="--")
    axs[0].set_xlabel("time from one Spike stamp to the next, same recording (ms, log scale)")
    axs[0].set_ylabel("number of neighbouring pairs")
    axs[0].set_title("All 18 Confluence sets: %d gaps; %d under 1 ms (orange)" % (g.size, (g < 1).sum()), fontsize=9, loc="left")
    axs[1].hist(g[g < 50], bins=np.linspace(0, 50, 101), color="#888")
    axs[1].hist(g[g < 1], bins=np.linspace(0, 50, 101), color="#d9480f")
    axs[1].set_xlabel("same, zoomed to 0-50 ms (linear)")
    axs[1].set_title("Under 1 ms: %d; 1-10 ms: %d; 10-20 ms: %d" % ((g < 1).sum(), ((g >= 1) & (g < 10)).sum(), ((g >= 10) & (g < 20)).sum()), fontsize=9, loc="left")
    fig.text(0.01, 0.01, "Each recording's Confluence set at its newest version (the stamps the pools read). Orange: two Spike stamps "
             "under 1 ms apart. The reads are at 2 kHz, so anything under 0.5 ms is the same sample.", fontsize=7, color="#555")
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    pdf.savefig(fig)
    plt.close(fig)
    # the pairs, five a page
    order = sorted(pairs, key=lambda p: (int(p[0][1:]), p[2]))
    for k in range(0, len(order), 5):
        fig = plt.figure(figsize=(11, 8.5))
        gs = fig.add_gridspec(5, 3, hspace=0.95, wspace=0.28, width_ratios=[1.3, 1, 1])
        for r, it in enumerate(order[k:k + 5]):
            rs.append(panel(fig, gs, r, it, "  ·  pair %d of %d" % (k + r + 1, len(order))))
        fig.suptitle("Spike stamps under 1 ms apart: left, both on the biggest contact (B drawn at its own time); middle, every "
                     "contact; right, A minus B", fontsize=8, x=0.01, ha="left")
        pdf.savefig(fig)
        fig.savefig(os.path.join(OUT, "pairs_%02d.png" % (k // 5 + 1)), dpi=110)
        plt.close(fig)
    # for contrast: the closest neighbours that are NOT under 1 ms
    near = sorted(near_real, key=lambda p: p[3] - p[2])
    for k in range(0, len(near), 5):
        fig = plt.figure(figsize=(11, 8.5))
        gs = fig.add_gridspec(5, 3, hspace=0.95, wspace=0.28, width_ratios=[1.3, 1, 1])
        for r, it in enumerate(near[k:k + 5]):
            panel(fig, gs, r, it, "  ·  1-20 ms, %d of %d" % (k + r + 1, len(near)))
        fig.suptitle("Neighbouring Spike stamps 1 to 20 ms apart, every one: the same event twice, or two events? Same layout as before.", fontsize=8, x=0.01, ha="left")
        pdf.savefig(fig)
        plt.close(fig)
print("r min %.4f median %.4f" % (min(rs), float(np.median(rs))))
print("closest gap above 1 ms: %.2f ms" % (np.array(gaps_all)[np.array(gaps_all) >= 1].min()))
print("by mouse", {m: sum(1 for p in pairs if p[0] == m) for m in sorted({p[0] for p in pairs}, key=lambda s: int(s[1:]))})
print("in halo: both", sum(1 for p in pairs if in_halo(p[0], p[2]) and in_halo(p[0], p[3])),
      "one", sum(1 for p in pairs if in_halo(p[0], p[2]) != in_halo(p[0], p[3])))
