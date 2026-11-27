"""Figure E (poster v6): the seizure starts in the hilus, recruits both blades and CA1; the hilar interneuron fires hard, then
falls silent. Data: data/seizure.npz (seizure_data.py, from the raw). The stage drawings are the real section the probe went
down (section.py: Jarvis Seahorse's 10 um laminae at AP -1.90 mm). Drawn at its print size, 15.0 x 10.9 in."""
import os, json
import numpy as np
from matplotlib.patches import FancyArrowPatch, Rectangle, ConnectionPatch
import style as S
import section as X

HERE = os.path.dirname(os.path.abspath(__file__))
D = np.load(os.path.join(HERE, "data", "seizure.npz"), allow_pickle=True)
W, H = 15.0, 10.9
R = S.REGION
GROUPS = [("CA1", 2, 27), ("Supra blade", 28, 39), ("Hilus", 40, 49), ("Infra blade", 50, 59)]
PH = [("1", "Hilus", ["Hilus"], "firing"),                     # the unit, as its histogram says: 18 and 66 spikes/s in
      ("2", "+ Supra blade", ["Hilus", "Supra blade"], "firing"),   # stages 1 and 2, none in stage 3, masked in 4 (and
      # 0.4 spikes/s once the seizure is over, 44-80 s)
      ("3", "+ Infra blade", ["Hilus", "Supra blade", "Infra blade"], "silent"),
      ("4", "+ CA1", ["Hilus", "Supra blade", "Infra blade", "CA1"], "silent")]
NEW = ["Hilus", "Supra blade", "Infra blade", "CA1"]
stages = D["stages"]
vmax, gap = float(D["vmax"]), float(D["gap"])
unit = json.loads(str(D["unit"]))

fig = S.figure(W, H)
X0, PW, GAPX = 1.22, 2.98, 0.22
xs = [X0 + k * (PW + GAPX) for k in range(4)]
Y_SCH, H_SCH = 0.42, 1.72
Y_CSD, H_CSD = 2.42, 3.72
TR_CH = list(range(4, 60, 4))
sc = 4.0 / gap                                   # the 99th percentile of the traces spans four contacts (figure A)
csd_axes = []

for k, (num, name, act, un) in enumerate(PH):
    col = R[NEW[k]]
    S.text_at(fig, xs[k] + 0.16, 0.2, num, fontsize=S.TITLE - 1, fontweight="bold", color="white", ha="center", va="center",
              bbox=dict(boxstyle="circle,pad=0.28", fc=col, ec="none"))
    S.text_at(fig, xs[k] + 0.42, 0.2, name, fontsize=S.TITLE, fontweight="bold", color=col, va="center")
    sa = S.ax_at(fig, xs[k] + 0.15, Y_SCH, PW - 0.30, H_SCH)
    X.draw(sa, act, NEW[k], un, labels=(k == 0))
    if k < 3:
        y = 1 - (Y_SCH + H_SCH * 0.5) / H
        fig.patches.append(FancyArrowPatch(((xs[k] + PW - 0.13) / W, y), ((xs[k + 1] + 0.13) / W, y), transform=fig.transFigure,
                                           arrowstyle="-|>", mutation_scale=16, lw=1.6, color=S.SOFT))
    # CSD snapshot with the potentials over it
    a = S.ax_at(fig, xs[k], Y_CSD, PW, H_CSD)
    csd_axes.append(a)
    r0, r1 = stages[k]
    C = np.asarray(D["snaps"][k], dtype=float)
    a.imshow(C[1:59], aspect="auto", cmap=S.CSD_CMAP, vmin=-vmax, vmax=vmax, extent=[r0, r1, 59.5, 1.5], interpolation="bilinear")
    tt = np.asarray(D["t_stage"][k], dtype=float)
    Tr = np.asarray(D["traces"][k], dtype=float)
    for c in TR_CH:
        a.plot(tt, c - np.clip(Tr[c - 1], -1.3 * gap, 1.3 * gap) * sc, c=S.INK, lw=0.65, alpha=0.72)
    a.set_xlim(r0, r1); a.set_ylim(59.5, 1.5)
    for _, lo, hi in GROUPS[:-1]:
        a.axhline(hi + 0.5, c=S.INK, lw=0.8, ls=(0, (3, 3)), alpha=0.45)
    S.bare(a)
    for s in a.spines.values():
        s.set_visible(True); s.set_color(S.FAINT); s.set_linewidth(0.8)
    # the region that just joined: a bar on the panel's right
    g = [g_ for g_ in GROUPS if g_[0] == NEW[k]][0]
    a.plot([1.018, 1.018], [g[1] - 0.5, g[2] + 0.5], c=col, lw=5, transform=a.get_yaxis_transform(), clip_on=False, solid_capstyle="butt")
    a.text(0.5, -0.035, "%g–%g s" % (r0, r1), transform=a.transAxes, ha="center", va="top", fontsize=S.TICK, color=S.SOFT)
    if k == 0:
        for nm, lo, hi in GROUPS:
            a.text(-0.04, (lo + hi) / 2, nm.replace(" ", "\n"), transform=a.get_yaxis_transform(), ha="right", va="center",
                   fontsize=S.LABEL - 0.5, fontweight="bold", color=R[nm], linespacing=0.95)
    if k == 3:
        # scale bars: 250 ms and 2 mV
        yb = 61.4
        a.plot([r1 - 0.25, r1], [yb, yb], c=S.INK, lw=2.2, clip_on=False, solid_capstyle="butt")
        a.text(r1 - 0.125, yb + 0.6, "250 ms", ha="center", va="top", fontsize=S.NOTE, color=S.INK)
        v = 2000.0
        xb = r1 + 0.075
        a.plot([xb, xb], [58.5, 58.5 - v * sc], c=S.INK, lw=2.2, clip_on=False, solid_capstyle="butt")
        a.text(xb + 0.025, 58.5 - v * sc / 2, "2 mV", ha="left", va="center", fontsize=S.NOTE, color=S.INK, rotation=90)
    if k == 0:
        im_for_cb = a.images[0]

# colorbar: sink and source
cax = S.ax_at(fig, 14.08, Y_CSD + 0.55, 0.17, 2.1)
cb = fig.colorbar(im_for_cb, cax=cax)
cb.set_ticks([-vmax * 0.85, vmax * 0.85]); cb.set_ticklabels(["sink", "source"])
cb.ax.tick_params(labelsize=S.NOTE, length=0, pad=3)
cb.outline.set_visible(False)
S.text_at(fig, 14.165, Y_CSD + 0.18, "CSD", fontsize=S.NOTE, fontweight="bold", color=S.INK, ha="center")

# ---------------------------------------------------------------- the interneuron and each zone, on one clock
T0, T1 = -4.5, 6.5
XL, XW = X0, xs[3] + PW - X0
Y_U, H_U = 6.95, 1.25
Y_Z, H_Z = 8.55, 1.72
au = S.ax_at(fig, XL, Y_U, XW, H_U)
az = S.ax_at(fig, XL, Y_Z, XW, H_Z, sharex=au)
sp = D["spikes"]
edges = np.arange(T0, T1 + 1e-9, 0.25)
hz = np.histogram(sp, edges)[0] / 0.25
base_hz = float(unit["rate"])
pre3 = float(np.mean(hz[(edges[:-1] >= -3) & (edges[:-1] < 0)]))
MASK = 3.7
show = edges[:-1] < MASK
au.bar(edges[:-1][show], hz[show], width=0.25, align="edge", color=S.SST_FILL, ec="white", lw=0.4, zorder=3)
au.axhline(base_hz, c=S.SOFT, lw=1.1, ls=(0, (4, 3)), zorder=4)
au.text(2.58, base_hz + 2.0, "baseline %.1f Hz" % base_hz, fontsize=S.NOTE, color=S.SOFT, va="bottom", zorder=5)
au.add_patch(Rectangle((MASK, 0), T1 - MASK, 1, transform=au.get_xaxis_transform(), fc="none", ec="#C9CFD6", hatch="////", lw=0, zorder=1))
au.text(T1 - 0.1, 0.93, "single spikes masked\nby the discharges", transform=au.get_xaxis_transform(), ha="right", va="top",
        fontsize=S.NOTE, color=S.SOFT, bbox=dict(fc="white", ec="none", pad=1.5), zorder=5)
au.set_ylim(0, 100); au.set_yticks([0, 40, 80]); au.set_ylabel("Spikes/s")
au.tick_params(labelbottom=False)
S.text_at(fig, XL, Y_U - 0.36, "Hilar interneuron (CSC 41)", fontsize=S.LABEL, fontweight="bold", color=S.SST)
rate = lambda a, b: float(np.sum((sp >= a) & (sp < b)) / (b - a))          # noqa: E731
END = 43.83                                      # the seizure's last discharge (story_m459: the mask runs 3.7 to 43.83 s)
burst, none, post = rate(1.3, 2.3), int(np.sum((sp >= 2.6) & (sp < MASK))), rate(END, 80.0)
S.text_at(fig, XL + 2.62, Y_U - 0.34, "%.0f spikes/s in the 3 s before onset (%.1f× baseline) and %.0f at 1.3–2.3 s; then silent: %s spikes "
          "from 2.6 to 3.7 s, %.1f/s after the seizure" % (pre3, pre3 / base_hz, burst, "no" if none == 0 else str(none), post),
          fontsize=S.NOTE + 0.5, color=S.SOFT)
# its spike, averaged over the baseline
wa = S.ax_at(fig, 13.98, Y_U + 0.12, 0.92, 0.9)
wm, wsd = D["wf_mean"], D["wf_sd"]
tw = (np.arange(len(wm)) - 18) / 30.0
wa.fill_between(tw, wm - wsd, wm + wsd, color=X.tint(S.SST_FILL, 0.35), lw=0)
wa.plot(tw, wm, c=S.SST, lw=1.5)
S.bare(wa)
yb0 = wm.min() - 30
wa.plot([0.55, 1.05], [yb0, yb0], c=S.INK, lw=1.6, solid_capstyle="butt")
wa.plot([1.05, 1.05], [yb0, yb0 + 100], c=S.INK, lw=1.6, solid_capstyle="butt")
wa.text(0.26, yb0 - 12, "0.5 ms · 100 µV", ha="center", va="top", fontsize=S.SMALL, color=S.INK)
wa.set_xlim(tw[0], 1.12)
S.text_at(fig, 14.45, Y_U - 0.15, "its spike", fontsize=S.NOTE, color=S.SOFT, ha="center")

zt, zn, Z = D["zt"], list(D["zone_names"]), D["zone"]
m = (zt >= T0) & (zt <= T1)
for nm in ("CA1", "Infra blade", "Supra blade", "Hilus"):
    az.plot(zt[m], Z[zn.index(nm)][m], c=R[nm], lw=2.3, zorder=4 if nm == "Hilus" else 3)
az.set_yscale("log"); az.set_ylim(0.9, 220)
az.set_yticks([1, 10, 100]); az.set_yticklabels(["1×", "10×", "100×"])
az.minorticks_off()
az.set_ylabel("|CSD| vs own\nbaseline")
az.set_xlim(T0, T1)
az.set_xticks([-4, -2, 0, 2, 4, 6])
az.set_xlabel("Time from hilar onset (s)")
LBL = {"Hilus": (0.72, 118, "center"), "Supra blade": (2.05, 118, "center"), "Infra blade": (2.6, 2.3, "center"), "CA1": (4.05, 2.0, "center")}
for k, (a0, a1) in enumerate(stages):
    for ax_ in (au, az):
        ax_.axvspan(a0, a1, color="#EEF1F4", lw=0, zorder=0)
    az.text((a0 + a1) / 2, 1.09, PH[k][0], transform=az.get_xaxis_transform(), ha="center", va="center", fontsize=S.NOTE,
            fontweight="bold", color="white", bbox=dict(boxstyle="circle,pad=0.25", fc=R[NEW[k]], ec="none"), zorder=7, clip_on=False)
for nm, (x, y, ha) in LBL.items():
    az.text(x, y, nm, color=R[nm], fontsize=S.LABEL - 0.5, fontweight="bold", ha=ha, va="center",
            bbox=dict(fc="white", ec="none", alpha=0.85, pad=0.8), zorder=6)
for ax_ in (au, az):
    ax_.axvline(0, c=S.INK, lw=1.0, alpha=0.55, zorder=2)

S.save(fig, os.path.join(HERE, "out", "E_seizure.png"))
print("E: base %.1f Hz, -3..0 s %.1f Hz (%.1fx); unit %s" % (base_hz, pre3, pre3 / base_hz, unit))
