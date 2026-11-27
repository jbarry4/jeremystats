"""Figures B, C and D (poster v5; v7 adds the lab's cells, cells.py, between B's and C's layer names and their CSD), the
'Where discharges start' card.
B and C are redrawn from the numbers in the NBH'25 poster's Fig. 4 (data/nbh_fig4*.npz, from nbh_extract*.py); D is computed
from the urethane session table (as draft 1's urethane_plot.py did). CSD everywhere: sinks blue, sources red (the NBH figure's
own sign: its dentate-spike CSDs put the sink at the OML in blue)."""
import os, json
import numpy as np
import pandas as pd
from scipy import stats as st
from matplotlib.patches import Rectangle
import style as S
import icons as I
import cells as Ce

HERE = os.path.dirname(os.path.abspath(__file__))
R = S.REGION
CTX = "#7A8592"


def badge(ax, x, y, s, color=S.INK, size=S.NOTE, transform=None):
    kw = dict(transform=transform) if transform is not None else {}
    ax.text(x, y, s, ha="center", va="center", fontsize=size, fontweight="bold", color="white", zorder=9, clip_on=False,
            bbox=dict(boxstyle="circle,pad=0.22", fc=color, ec="none"), **kw)


def csd_bar(fig, x, y, w, h, im, vmax, label=True):
    cax = S.ax_at(fig, x, y, w, h)
    cb = fig.colorbar(im, cax=cax)
    cb.set_ticks([-vmax * 0.85, vmax * 0.85]); cb.set_ticklabels(["sink", "source"])
    cb.ax.tick_params(labelsize=S.NOTE, length=0, pad=2)
    cb.outline.set_visible(False)
    return cb


# ================================================================== B: one IED, from the hilus
A = np.load(os.path.join(HERE, "data", "nbh_fig4.npz"), allow_pickle=True)
t_sp = float(A["A_spike_t"])
ext = A["A_extent"]                                       # t0, t1, CSC bottom, CSC top
LAY = json.loads(str(A["A_layers"]))
fig = S.figure(15.0, 4.85)
Y0, H = 0.42, 3.9                                  # v8: 0.6 in taller
VB = 0.15
# --- the CSD with the LFP over it (v7: the lab's cells between the layer names and the CSD, on its depth axis)
ax = S.ax_at(fig, 1.62, Y0, 3.95, H)
ms = lambda t: (np.asarray(t) - t_sp) * 1000
im = ax.imshow(A["A_csd"], aspect="auto", cmap=S.CSD_CMAP, vmin=-VB, vmax=VB, extent=[ms(ext[0]), ms(ext[1]), ext[2], ext[3]],
               interpolation="bilinear")
MVCH = 3.77 / 2                                          # channels per mV, as drawn in the source (2 mV = 3.77 contacts)
for k, colr in ((0, CTX), (1, R["CA1"]), (2, R["Hilus"])):
    t = ms(A["A_tr%d_t" % k]); v = A["A_tr%d_mv" % k]; c0 = float(A["A_tr%d_ch" % k])
    ax.plot(t, c0 - v * MVCH, c=S.INK, lw=0.8, zorder=3)
ax.set_xlim(-145, 150); ax.set_ylim(62.4, 2.6)
S.bare(ax)
for s_ in ax.spines.values():
    s_.set_visible(True); s_.set_color(S.FAINT); s_.set_linewidth(0.8)
names = [("Ctx", "Cortex", CTX), ("Pyr", "CA1 pyr", R["CA1"]), ("SLM", "SLM", S.SOFT), ("OML", "OML", S.SOFT), ("DGC", "GCL", S.GC),
         ("Hil", "Hilus", R["Hilus"])]
for key, lab, colr in names:
    ax.text(-0.165, LAY[key], lab, transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=S.NOTE + 0.5,
            color=colr, fontweight="bold" if key in ("Pyr", "Hil") else "normal")
ia = I.icon_axes(fig, 1.0, Y0, 0.6, H, (62.4, 2.6))
xi = 0.5 * ia.get_xlim()[1]
FISB = (LAY["SLM"] + LAY["OML"]) / 2
Ce.group(ia, "pyr", xi, LAY["Pyr"], FISB - 0.4)
Ce.group(ia, "gc_up", xi, LAY["DGC"], FISB + 0.6)
hs = ia.get_xlim()[1] * 0.9 / 13.4
Ce.sst(ia, Ce.frame((xi, LAY["Hil"]), (0, -hs), (hs, 0)), spine_lw=0.35)
# spike marker, pre-spike window, scale bars
ax.annotate("", xy=(0, 62.4), xytext=(0, 66.2), arrowprops=dict(arrowstyle="-|>", color=S.INK, lw=1.4, mutation_scale=12),
            annotation_clip=False)
ax.text(0, 67.0, "IED", ha="center", va="top", fontsize=S.NOTE, fontweight="bold", color=S.INK)
ax.plot([95, 145], [64.2, 64.2], c=S.INK, lw=1.8, clip_on=False, solid_capstyle="butt")
ax.text(120, 64.6, "50 ms", ha="center", va="top", fontsize=S.NOTE, color=S.INK)
ax.plot([153, 153], [60.5, 60.5 - 2 * MVCH], c=S.INK, lw=1.8, clip_on=False, solid_capstyle="butt")
ax.text(157, 60.5 - MVCH, "2 mV", ha="left", va="center", fontsize=S.NOTE, color=S.INK, rotation=90)
csd_bar(fig, 5.86, Y0 + 0.23 * H, 0.13, 0.55 * H, im, VB)
S.title(fig, 0.3, 0.0, "CSD and LFP through the IED", size=S.LABEL)
# --- the probe's track (histology, same depth axis)
pa = S.ax_at(fig, 6.72, Y0, 1.02, H)
pa.imshow(A["B_img"], cmap="gray", aspect="auto", extent=[0, 1, 66.8, 1.51], vmin=10, vmax=235, interpolation="bilinear")
pa.set_xlim(0, 1); pa.set_ylim(62.4, 2.6); S.bare(pa)
pa.plot([0.31, 0.31], [2.6, 62.4], c="white", lw=1.3, alpha=0.9)
pa.plot([1.1, 1.1], [62.4, 62.4 - 25], c=S.INK, lw=1.8, solid_capstyle="butt", clip_on=False)
pa.text(1.18, 62.4 - 12.5, "500 µm", rotation=90, ha="left", va="center", fontsize=S.NOTE, color=S.INK)
S.title(fig, 6.72, 0.0, "Probe track", size=S.LABEL)
# --- pre-spike spectra
for j, (nm, colr, lab) in enumerate((("pyr", R["CA1"], "CA1 pyr"), ("hil", R["Hilus"], "Hilus"))):
    sa = S.ax_at(fig, 8.92, Y0 + j * (H / 2 + 0.17), 1.7, H / 2 - 0.17)
    f, y = A["C_%s_f" % nm], A["C_%s_y" % nm]
    sa.plot(f, y / 1000, c=colr, lw=1.8)
    sa.set_xlim(0, 120); sa.set_ylim(0, None)
    sa.set_xticks([0, 40, 80, 120])
    if j == 0:
        sa.tick_params(labelbottom=False)
    else:
        sa.set_xlabel("Hz", labelpad=1)
    sa.text(0.96, 0.92, lab, transform=sa.transAxes, ha="right", va="top", fontsize=S.NOTE + 0.5, fontweight="bold", color=colr)
    if nm == "hil":
        sa.annotate("", xy=(17, 0.6), xytext=(46, 0.6), arrowprops=dict(arrowstyle="-", color=S.INK, lw=1.2))
        sa.text(31.5, 0.64, "β–γ", ha="center", va="bottom", fontsize=S.NOTE + 1, color=S.INK, fontweight="bold")
        sa.set_ylim(0, 1.12)
S.text_at(fig, 8.36, Y0 + H / 2, "Power (×1000)", rotation=90, ha="center", va="center", fontsize=S.NOTE + 0.5, color=S.INK)
S.title(fig, 8.36, 0.0, "LFP before the IED", size=S.LABEL)
# --- 300-6000 Hz traces
ua = S.ax_at(fig, 11.32, Y0, 3.6, H)
nmz = json.loads(str(A["D_names"]))
GAP = 420
for k, nm in enumerate(nmz):
    colr = CTX if nm == "Ctx" else (R["CA1"] if nm == "CA1" else R["Hilus"])
    t = ms(A["D_tr%d_t" % k]); v = A["D_tr%d_uv" % k]
    keep = t <= 98                                       # v8: the traces stop short of the scale bar, so its label is clear
    ua.plot(t[keep], v[keep] - k * GAP, c=colr, lw=0.55)
ua.set_xlim(-170, 120); ua.set_ylim(-(len(nmz) - 0.45) * GAP, 0.62 * GAP); S.bare(ua)
for nm, k0, k1, colr in (("Ctx", 0, 0, CTX), ("CA1", 1, 1, R["CA1"]), ("Hilus", 2, len(nmz) - 1, R["Hilus"])):
    yc = -(k0 + k1) / 2 * GAP
    ua.text(-0.02, yc, nm, transform=ua.get_yaxis_transform(), ha="right", va="center", fontsize=S.NOTE + 0.5, color=colr,
            fontweight="bold")
    if k1 > k0:
        ua.plot([-0.008, -0.008], [-k1 * GAP - 150, -k0 * GAP + 150], transform=ua.get_yaxis_transform(), c=colr, lw=2.5,
                clip_on=False, solid_capstyle="butt")
ua.axvline(0, c=S.FAINT, lw=0.9, zorder=0)
ua.plot([-110, -4], [0.45 * GAP, 0.45 * GAP], c=S.INK, lw=1.6, solid_capstyle="butt")
ua.text(-57, 0.52 * GAP, "pre-spike", ha="center", va="bottom", fontsize=S.NOTE, color=S.INK)
y_sb = -(len(nmz) - 0.45) * GAP - 60
ua.plot([70, 120], [y_sb, y_sb], c=S.INK, lw=1.8, solid_capstyle="butt", clip_on=False)
ua.text(95, y_sb - 45, "50 ms", ha="center", va="top", fontsize=S.NOTE, color=S.INK)
ua.plot([120, 120], [y_sb, y_sb + 400], c=S.INK, lw=1.8, solid_capstyle="butt", clip_on=False)
ua.text(116, y_sb + 200, "400 µV", ha="right", va="center", fontsize=S.NOTE, color=S.INK, rotation=90)
ua.annotate("", xy=(0, -(len(nmz) - 0.45) * GAP), xytext=(0, -(len(nmz) + 0.05) * GAP),
            arrowprops=dict(arrowstyle="-|>", color=S.INK, lw=1.4, mutation_scale=12), annotation_clip=False)
ua.text(0, -(len(nmz) + 0.12) * GAP, "IED", ha="center", va="top", fontsize=S.NOTE, fontweight="bold", color=S.INK)
S.title(fig, 10.75, 0.0, "Units (300–6000 Hz) before the IED", size=S.LABEL)
S.save(fig, os.path.join(HERE, "out", "B_ied.png"))
print("B written")

# ================================================================== C: a discharge in two steps, and a KCNT1 dentate spike
E = np.load(os.path.join(HERE, "data", "nbh_fig4ef.npz"), allow_pickle=True)
arrE = json.loads(str(E["E_arrows"])); arrF = json.loads(str(E["F_arrows"]))
layE = json.loads(str(E["E_layers"]))
fig = S.figure(10.0, 4.75)                     # v8: the CSD panels 0.4 in taller
P1, P2 = "#9AA3AE", S.INK                               # phase 1 (light), phase 2 (ink)
VC = 0.2
halves = [("E", 0.0, arrE["blue"], "A two-step discharge"), ("F", 4.72, arrF["black"], "A KCNT1 dentate spike")]
for key, x0, t_ref, ttl in halves:
    S.title(fig, x0 + 0.72, 0.0, ttl, size=S.LABEL)
    # LFP
    la = S.ax_at(fig, x0 + 0.72, 0.36, 3.7, 1.08)
    t = (E[key + "i_t"] - t_ref) * 1000
    m = (t > -200) & (t < 300)
    la.fill_between(t[m], E[key + "i_lo_mv"][m], E[key + "i_hi_mv"][m], color=S.INK, lw=0.4, edgecolor=S.INK)
    la.set_xlim(-200, 300); la.set_ylim(-2.0, 2.0); S.bare(la)
    if key == "E":
        for nm, colr, num in (("red", P1, "1"), ("blue", P2, "2")):
            tt = (arrE[nm] - t_ref) * 1000
            yy = -1.35 if num == "1" else 1.92
            badge(la, tt + (-24 if num == "1" else 12), yy, num, colr)
        la.plot([-200, -200], [-1.95, 0.05], c=S.INK, lw=1.8, solid_capstyle="butt", clip_on=False)
        la.text(-210, -0.95, "2 mV", ha="right", va="center", fontsize=S.NOTE, color=S.INK, rotation=90)
    else:
        badge(la, 13, 1.75, "DS", P2, size=S.SMALL)
    la.plot([-200, -100], [-1.95, -1.95], c=S.INK, lw=1.8, solid_capstyle="butt", clip_on=False)
    la.text(-150, -2.0, "100 ms", ha="center", va="top", fontsize=S.NOTE, color=S.INK)
    # CSD zoom
    hp = E[key + "_heat_pt"]
    tz = (E[key + "_t"] - t_ref) * 1000
    ca = S.ax_at(fig, x0 + 1.12, 1.82, 2.08, 2.45)
    im = ca.imshow(E[key + "_csd"], aspect="auto", cmap=S.CSD_CMAP, vmin=-VC, vmax=VC, extent=[tz[0], tz[1], hp[3], hp[2]],
                   interpolation="bilinear")
    ov_t = (E[key + "_ov_t"] - t_ref) * 1000
    ca.plot(ov_t, E[key + "_ov_y"], c=S.INK, lw=0.9)
    ca.set_xlim(tz[0], tz[1]); ca.set_ylim(hp[3], hp[2])
    ca.set_yticks([]); ca.spines["left"].set_visible(False)
    ca.set_xticks([-15, 0, 15]); ca.set_xlabel("ms", labelpad=1)
    if key == "E":
        for nm, colr, num in (("red", P1, "1"), ("blue", P2, "2")):
            tt = (arrE[nm] - t_ref) * 1000
            ca.axvline(tt, c=colr, lw=1.3, ls=(0, (3, 2)) if num == "1" else "-")
            badge(ca, tt + (-1.6 if num == "1" else 1.6), hp[2] - 6.5, num, colr)
        for lab, yv in layE.items():
            colr = R["Hilus"] if lab == "Hilus" else (S.GC if lab == "GCL" else S.SOFT)
            ca.text(-0.235, yv, lab, transform=ca.get_yaxis_transform(), ha="right", va="center", fontsize=S.NOTE + 0.5,
                    color=colr, fontweight="bold" if lab in ("Hilus", "GCL") else "normal")
        # the lab's cells: the upper blade's granule cells from the GCL out through MML and OML, a hilar SST cell
        ic = I.icon_axes(fig, x0 + 0.66, 1.82, 0.44, 2.45, (hp[3], hp[2]))
        xi = 0.5 * ic.get_xlim()[1]
        Ce.group(ic, "gc_up", xi, layE["GCL"], layE["OML"] - 13.0, width=0.9 * ic.get_xlim()[1])
        hs = ic.get_xlim()[1] * 0.95 / 13.4
        Ce.sst(ic, Ce.frame((xi, layE["Hilus"]), (0, -hs), (hs, 0)), spine_lw=0.35)
    else:
        ca.axvline(0, c=P2, lw=1.3)
        badge(ca, 0, hp[2] - 6.5, "DS", P2, size=S.SMALL)
    # depth profiles
    pa = S.ax_at(fig, x0 + 3.3, 1.82, 1.08, 2.45)
    y = E[key + "_prof_y"]
    pa.axvline(0, c=S.FAINT, lw=0.9)
    if key == "E":
        pa.plot(E["E_prof_red"], y, c=P1, lw=1.6, ls=(0, (3, 1.6)))
        pa.plot(E["E_prof_blue"], y, c=P2, lw=1.6)
        pa.text(0.0, 1.04, "phase 1", transform=pa.transAxes, color="#7A8592", fontsize=S.NOTE, fontweight="bold", ha="left", va="bottom")
        pa.text(0.0, 1.13, "phase 2", transform=pa.transAxes, color=P2, fontsize=S.NOTE, fontweight="bold", ha="left", va="bottom")
    else:
        pa.plot(E["E_prof_blue"], y, c="#C9CED6", lw=1.6)
        pa.plot(E["F_prof_black"], y, c=P2, lw=1.6)
        pa.text(0.0, 1.04, "discharge, phase 2", transform=pa.transAxes, color="#9AA3AE", fontsize=S.NOTE, fontweight="bold", ha="left", va="bottom")
        pa.text(0.0, 1.13, "DS", transform=pa.transAxes, color=P2, fontsize=S.NOTE, fontweight="bold", ha="left", va="bottom")
    pa.set_ylim(hp[3], hp[2]); pa.set_xlim(-0.15, 0.22)
    pa.set_yticks([]); pa.spines["left"].set_visible(False)
    pa.set_xticks([-0.1, 0, 0.1, 0.2]); pa.set_xticklabels(["", "0", "", "0.2"])
    pa.set_xlabel("CSD", labelpad=1)
csd_bar(fig, 9.27, 2.4, 0.12, 1.45, im, VC)
S.save(fig, os.path.join(HERE, "out", "C_ds.png"))
print("C written; phase times", arrE, arrF)

# ================================================================== D: urethane IEDs per minute
CSV = r"C:\Users\info\Desktop\JeremyStats\Barry Playground\KCNT1 Spreadsheets\GitHub__jeremystats__KCNT1_urethane_sessions.csv"
SET = {"WT": [(5, 2), (6, 4), (10, 2), (11, 6), (13, 3)], "Het": [(19, 4), (22, 2), (22, 3)],
       "Hom": [(2, 2), (4, 2), (7, 3), (8, 3), (9, 3), (12, 4), (14, 2), (15, 6)]}
d = pd.read_csv(CSV)
rows = []
for g, keys in SET.items():
    for m_, s_ in keys:
        r = d[(d.m == m_) & (d.s == s_)].iloc[0]
        rows.append(dict(geno=g, mouse=m_, solid=int(r["Solid IEDs"]), minutes=float(r["Duration (s)"]) / 60))
M = pd.DataFrame(rows).groupby(["geno", "mouse"]).agg(solid=("solid", "sum"), minutes=("minutes", "sum")).reset_index()
M["rate"] = M.solid / M.minutes
wt, het, hom = (M[M.geno == g].rate.values for g in ("WT", "Het", "Hom"))
p = st.mannwhitneyu(hom, wt, alternative="two-sided", method="exact").pvalue
fig = S.figure(4.6, 3.45)
ax = S.ax_at(fig, 0.78, 0.42, 3.65, 2.45)
rs = np.random.RandomState(3)
for i, (g, v) in enumerate((("WT", wt), ("Het", het), ("Hom", hom))):
    x = i + (rs.rand(v.size) - 0.5) * 0.3
    ax.scatter(x, v, s=62, color=S.GENO[g], edgecolors="white", linewidths=1.0, zorder=3)
    ax.plot([i - 0.27, i + 0.27], [np.median(v)] * 2, color=S.INK, lw=2.2, zorder=4, solid_capstyle="butt")
ax.set_xticks([0, 1, 2]); ax.set_xticklabels(["WT\n%d" % wt.size, "Het\n%d" % het.size, "Hom\n%d" % hom.size])
for tl, g in zip(ax.get_xticklabels(), ("WT", "Het", "Hom")):
    tl.set_color(S.GENO[g]); tl.set_fontweight("bold")
ax.tick_params(axis="x", length=0)
ax.set_ylabel("IEDs per minute")
top = M.rate.max()
ax.set_xlim(-0.55, 2.55); ax.set_ylim(-0.1, top * 1.3)
yb = top * 1.12
ax.plot([0, 0, 2, 2], [yb - top * 0.04, yb, yb, yb - top * 0.04], color=S.INK, lw=1.3)
ax.text(1, yb + top * 0.02, "**  P = %.3f" % p, ha="center", va="bottom", fontsize=S.NOTE + 0.5)
S.save(fig, os.path.join(HERE, "out", "D_urethane.png"))
print("D: medians WT %.2f Het %.2f Hom %.2f; Hom vs WT exact Mann-Whitney P = %.4f; n %d/%d/%d" % (
    np.median(wt), np.median(het), np.median(hom), p, wt.size, het.size, hom.size))
