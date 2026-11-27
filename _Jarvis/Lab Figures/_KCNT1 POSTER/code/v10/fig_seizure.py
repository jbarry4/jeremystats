"""Figure E (poster v7): the seizure starts in the hilus, recruits both blades and CA1; the hilar interneuron fires hard,
then falls silent. Data: data/seizure.npz (seizure_data.py, from the raw). The stage drawings are the real section the probe
went down (section.py: Jarvis Seahorse's 10 um laminae at AP -1.90 mm), drawn as smooth vector shapes.

v7 lines the four stages up with the clock below them: the seizure's own time axis (0 to 5.75 s) runs at the width of one
stage panel per second, so each stage's CSD panel sits exactly over its second on the interneuron's histogram and on the
zones' |CSD| (the 1 s between stages 3 and 4 is the real gap). The 3 s before onset get their own, narrower panel on the
left (its own clock, marked by the break). The region names beside the CSD are the lab's cells (cells.py), each with its
region's colour bar: CA1 pyramidal cells, the upper blade's granule cells, a hilar SST cell, the lower blade's granule cells.

v8 (the user's comments on v7): smoother borders on the sections (section.py), the probe drawn as a probe (a shank with its
64 contacts) instead of an arrow, no arrows between the stages, the CSD scale, the scale bars and the unit's spike in a
column of their own on the right (no white box over the histogram), and a PV basket cell among the upper blade's granule
cells beside the hilar SST cell."""
import os, json
import numpy as np
from matplotlib.patches import FancyArrowPatch, Rectangle
import style as S
import section as X
import icons as I
import cells as Ce

HERE = os.path.dirname(os.path.abspath(__file__))
D = np.load(os.path.join(HERE, "data", "seizure.npz"), allow_pickle=True)
W, H = 15.0, 11.59
R = S.REGION
GROUPS = [("CA1", 2, 27), ("Supra blade", 28, 39), ("Hilus", 40, 49), ("Infra blade", 50, 59)]
PH = [("1", "Hilus", ["Hilus"], "firing"),                     # the unit, as its histogram says: 18 and 66 spikes/s in
      ("2", "+ Supra blade", ["Hilus", "Supra blade"], "firing"),   # stages 1 and 2, none in stage 3, masked in 4 (and
      ("3", "+ Infra blade", ["Hilus", "Supra blade", "Infra blade"], "silent"),   # 0.4 spikes/s once it is over)
      ("4", "+ CA1", ["Hilus", "Supra blade", "Infra blade", "CA1"], "silent")]
NEW = ["Hilus", "Supra blade", "Infra blade", "CA1"]
stages = D["stages"]
vmax, gap = float(D["vmax"]), float(D["gap"])
unit = json.loads(str(D["unit"]))

# ------------------------------------------------------------------ one clock for everything below the drawings
XL = 1.06                                         # the before-onset panel's left edge (y labels to its left)
PRE0, PRE1 = XL, 2.2                              # -3..0 s
SEZ0, T_A, T_B = 2.36, -0.05, 5.75                # the seizure panel: t from T_A at SEZ0
SC = 2.0                                          # inches per second on the seizure clock = one CSD panel's width
RC = 14.12                                        # v8: the right-hand column (CSD scale, scale bars, the unit's spike)
xt = lambda t: SEZ0 + (t - T_A) * SC              # noqa: E731
SEZ1 = xt(T_B)
xs = [xt(a) for a, _b in stages]                  # each stage's CSD panel, exactly over its second
PW = SC * 1.0

fig = S.figure(W, H)
Y_SCH, H_SCH = 0.42, 1.62
Y_CSD, H_CSD = 2.36, 4.5
TR_CH = list(range(4, 60, 4))
sc = 4.0 / gap                                    # the 99th percentile of the traces spans four contacts
SECW = 2.45                                       # a section drawing's width, centred over its panel

for k, (num, name, act, un) in enumerate(PH):
    col = R[NEW[k]]
    cxk = xs[k] + PW / 2
    nm_t = S.text_at(fig, cxk, 0.2, name, fontsize=S.TITLE, fontweight="bold", color=col, va="center")
    wn = nm_t.get_window_extent(fig.canvas.get_renderer()).width / fig.dpi
    x_start = cxk - (0.32 + 0.1 + wn) / 2                     # badge and name centred over the panel together
    nm_t.set_x((x_start + 0.42) / W)
    S.text_at(fig, x_start + 0.16, 0.2, num, fontsize=S.TITLE - 1, fontweight="bold", color="white", ha="center", va="center",
              bbox=dict(boxstyle="circle,pad=0.28", fc=col, ec="none"))
    sa = S.ax_at(fig, cxk - SECW / 2, Y_SCH, SECW, H_SCH)
    X.draw(sa, act, NEW[k], un, labels=(k == 0))
    # CSD snapshot with the potentials over it
    a = S.ax_at(fig, xs[k], Y_CSD, PW, H_CSD)
    r0, r1 = stages[k]
    C = np.asarray(D["snaps"][k], dtype=float)
    a.imshow(C[1:59], aspect="auto", cmap=S.CSD_CMAP, vmin=-vmax, vmax=vmax, extent=[r0, r1, 59.5, 1.5], interpolation="bilinear")
    tt = np.asarray(D["t_stage"][k], dtype=float)
    Tr = np.asarray(D["traces"][k], dtype=float)
    for c in TR_CH:
        a.plot(tt, c - np.clip(Tr[c - 1], -1.3 * gap, 1.3 * gap) * sc, c=S.INK, lw=0.6, alpha=0.72)
    a.set_xlim(r0, r1); a.set_ylim(59.5, 1.5)
    for _, lo, hi in GROUPS[:-1]:
        a.axhline(hi + 0.5, c=S.INK, lw=0.8, ls=(0, (3, 3)), alpha=0.45)
    S.bare(a)
    for s in a.spines.values():
        s.set_visible(True); s.set_color(S.FAINT); s.set_linewidth(0.8)
    g = [g_ for g_ in GROUPS if g_[0] == NEW[k]][0]              # the region that just joined: a bar on the panel's right
    a.plot([1.022, 1.022], [g[1] - 0.5, g[2] + 0.5], c=col, lw=4.5, transform=a.get_yaxis_transform(), clip_on=False,
           solid_capstyle="butt")
    a.text(0.5, -0.012, "%g–%g s" % (r0, r1), transform=a.transAxes, ha="center", va="top", fontsize=S.TICK, color=S.SOFT)
    if k == 0:
        im_for_cb = a.images[0]

# the cells beside the first panel, one per region, on the panels' depth axis (CSC 2-59)
ia = I.icon_axes(fig, 1.28, Y_CSD, 1.03, H_CSD, (59.5, 1.5))
wd = ia.get_xlim()[1]
xi = 0.5 * wd
v_, c_, bb_, soma_, end_ = Ce._src("pyr")
Ce.group(ia, "pyr", xi, 7.0, 27.2, xscale=min(1.15, 0.96 * wd / ((bb_[2] - bb_[0]) * 20.2 / abs(end_ - soma_))))
# v9 (the user: "PV interneurons are also around the bottom cell layers ... more anatomically accurate"; Seahorse's
# knowledge base and 3D model): both blades the same size; a PV basket cell at EACH granule layer's hilar border, its
# dendrites out through its blade's molecular layer and into the hilus, its axon around the granule cells' bodies; the
# hilar SST (HIPP) cell between them, its axon up to the outer third of both blades' molecular layers
k_ = Ce.blade_k(38.0, 28.5)
up = Ce.blade(ia, "gc_up", xi, 38.0, -1, k_)
dn = Ce.blade(ia, "gc_down", xi, 50.0, +1, k_)
hs = wd * 0.8 / 13.4
s0 = (xi - 0.02 * wd, 44.2)
Ce.sst(ia, Ce.frame(s0, (0, -hs * 0.95), (hs, 0)), spine_lw=0.45, z=6.5)
Ce.sst_axon(ia, s0[0], s0[1], up, (xi - 0.46 * wd, xi + 0.46 * wd), lw=0.65, seed=3)
Ce.sst_axon(ia, s0[0], s0[1], dn, (xi + 0.46 * wd, xi - 0.46 * wd), lw=0.65, seed=5)
Ce.pv_basket(ia, up, xi + 0.25 * wd, z=7)
Ce.pv_basket(ia, dn, xi - 0.25 * wd, z=7, mirror=True)
bx = I.icon_axes(fig, 1.13, Y_CSD, 0.08, H_CSD, (59.5, 1.5))
for nm, lo, hi in GROUPS:
    bx.plot([0.5 * bx.get_xlim()[1]] * 2, [lo - 0.2, hi + 0.2], c=R[nm], lw=4.0, solid_capstyle="butt")

# the CSD scale and the scale bars: a column of their own on the right (v8)
gx0 = xs[2] + PW
cax = S.ax_at(fig, RC + 0.02, Y_CSD + 0.42, 0.15, 1.9)
cb = fig.colorbar(im_for_cb, cax=cax)
cb.set_ticks([-vmax * 0.85, vmax * 0.85]); cb.set_ticklabels(["sink", "source"])
cb.ax.tick_params(labelsize=S.NOTE, length=0, pad=3)
cb.outline.set_visible(False)
S.text_at(fig, RC + 0.095, Y_CSD + 0.08, "CSD", fontsize=S.NOTE, fontweight="bold", color=S.INK, ha="center")
mv = 2000.0 * sc * (H_CSD / 58.0)                 # 2 mV in inches on the panels
YB_ = Y_CSD + H_CSD                                # the bars sit on the panels' bottom line: 2 mV up, 250 ms across
sb = S.ax_at(fig, RC + 0.02, YB_ - mv, 0.25 * SC, mv); sb.set_xlim(0, 0.25); sb.set_ylim(0, mv); sb.axis("off")
sb.plot([0, 0.25], [0, 0], c=S.INK, lw=2.2, solid_capstyle="butt", clip_on=False)
sb.plot([0, 0], [0, mv], c=S.INK, lw=2.2, solid_capstyle="butt", clip_on=False)
S.text_at(fig, RC + 0.02 + 0.125 * SC, YB_ + 0.05, "250 ms", fontsize=S.NOTE, color=S.INK, ha="center")
S.text_at(fig, RC + 0.09, YB_ - mv / 2, "2 mV", fontsize=S.NOTE, color=S.INK, ha="left", va="center")
S.text_at(fig, gx0 + (xs[3] - gx0) / 2, Y_CSD + H_CSD + 0.06, "(1 s later)", fontsize=S.TICK, color=S.SOFT, ha="center")

# ---------------------------------------------------------------- the interneuron and each zone, on the same clock
Y_U, H_U = Y_CSD + H_CSD + 0.93, 1.12
Y_Z, H_Z = Y_U + H_U + 0.35, 1.62
T_PRE = -3.0
aup = S.ax_at(fig, PRE0, Y_U, PRE1 - PRE0, H_U)
aus = S.ax_at(fig, SEZ0, Y_U, SEZ1 - SEZ0, H_U)
azp = S.ax_at(fig, PRE0, Y_Z, PRE1 - PRE0, H_Z, sharey=None)
azs = S.ax_at(fig, SEZ0, Y_Z, SEZ1 - SEZ0, H_Z)
sp = D["spikes"]
edges = np.arange(-4.5, 6.5 + 1e-9, 0.25)
hz = np.histogram(sp, edges)[0] / 0.25
base_hz = float(unit["rate"])
pre3 = float(np.mean(hz[(edges[:-1] >= -3) & (edges[:-1] < 0)]))
MASK = 3.7
for au_, lo_, hi_ in ((aup, T_PRE, 0.0), (aus, T_A, T_B)):
    show = (edges[:-1] < MASK) & (edges[:-1] >= lo_ - 1e-9) & (edges[:-1] < hi_)
    au_.bar(edges[:-1][show], hz[show], width=0.25, align="edge", color=S.SST_FILL, ec="white", lw=0.4, zorder=3)
    au_.axhline(base_hz, c=S.SOFT, lw=1.1, ls=(0, (4, 3)), zorder=4)
    au_.set_ylim(0, 100); au_.set_xlim(lo_, hi_)
    au_.tick_params(labelbottom=False)
aus.add_patch(Rectangle((MASK, 0), T_B - MASK, 1, transform=aus.get_xaxis_transform(), fc="none", ec="#C9CFD6", hatch="////", lw=0,
                        zorder=1))
aus.text(MASK + 0.12, 0.93, "single spikes masked\nby the discharges", transform=aus.get_xaxis_transform(), ha="left", va="top",
         fontsize=S.NOTE, color=S.SOFT, bbox=dict(fc="white", ec="none", pad=1.5), zorder=5)
aus.text(2.62, base_hz + 2.0, "baseline %.1f Hz" % base_hz, fontsize=S.NOTE, color=S.SOFT, va="bottom", zorder=5)
aup.set_yticks([0, 40, 80]); aup.set_ylabel("Spikes/s")
aus.set_yticks([]); aus.spines["left"].set_visible(False)
rate = lambda a, b: float(np.sum((sp >= a) & (sp < b)) / (b - a))          # noqa: E731
END = 43.83                                      # the seizure's last discharge (story_m459: the mask runs 3.7 to 43.83 s)
burst, none, post = rate(1.3, 2.3), int(np.sum((sp >= 2.6) & (sp < MASK))), rate(END, 80.0)
ttl = S.text_at(fig, PRE0, Y_U - 0.5, "Hilar interneuron (CSC 41)", fontsize=S.LABEL, fontweight="bold", color=S.SST)
wt = ttl.get_window_extent(fig.canvas.get_renderer()).width / fig.dpi
S.text_at(fig, PRE0 + wt + 0.2, Y_U - 0.475, "%.0f spikes/s in the 3 s before onset (%.1f× baseline) and %.0f at 1.3–2.3 s; then silent: %s "
          "spikes from 2.6 to 3.7 s, %.1f/s after the seizure" % (pre3, pre3 / base_hz, burst, "no" if none == 0 else str(none), post),
          fontsize=S.NOTE + 0.5, color=S.SOFT)
# its spike, averaged over the baseline, in the right-hand column (v8: no white box over the plot)
wa = S.ax_at(fig, RC + 0.02, Y_U + 0.3, 0.78, 0.56)
wm, wsd = D["wf_mean"], D["wf_sd"]
tw = (np.arange(len(wm)) - 18) / 30.0
wa.fill_between(tw, wm - wsd, wm + wsd, color=X.tint(S.SST_FILL, 0.35), lw=0)
wa.plot(tw, wm, c=S.SST, lw=1.5)
S.bare(wa)
yb0 = wm.min() - 30
wa.plot([0.55, 1.05], [yb0, yb0], c=S.INK, lw=1.5, solid_capstyle="butt")
wa.plot([1.05, 1.05], [yb0, yb0 + 100], c=S.INK, lw=1.5, solid_capstyle="butt")
wa.set_xlim(tw[0], 1.12)
S.text_at(fig, RC + 0.41, Y_U + 0.22, "its spike", fontsize=S.NOTE, color=S.SST, ha="center", va="bottom", fontweight="bold")
S.text_at(fig, RC + 0.41, Y_U + 0.9, "0.5 ms\n100 µV", fontsize=S.SMALL, color=S.INK, ha="center", linespacing=0.95)

zt, zn, Z = D["zt"], list(D["zone_names"]), D["zone"]
# v9 (the user: "highlight like oh hilus activity goes up... and it gives up... and the supra blade kicks in... and then the
# infra blade, and then CA1 joins"): every zone drawn as before but lighter, and the moment each one takes over drawn bold,
# glowing, and named, with its stage's number. The moments are read off the zones' own |CSD| (seizure.npz): the hilus
# climbs from 15x to 59x by 0.7 s and is back to 7x by 1.4 s; the upper blade goes from 12x to 48x between 1.8 and 2.2 s;
# the lower blade from 6x to 49x between 2.9 and 3.2 s; CA1 from 13x to 43x between 4.8 and 5.3 s.
STORY = [("Hilus", 0.30, 0.86), ("Supra blade", 1.72, 2.30), ("Infra blade", 2.80, 3.30), ("CA1", 4.72, 5.40)]
FALL = ("Hilus", 0.80, 1.44)
for az_, lo_, hi_ in ((azp, T_PRE, 0.0), (azs, T_A, T_B)):
    m = (zt >= lo_) & (zt <= hi_)
    for nm in ("CA1", "Infra blade", "Supra blade", "Hilus"):
        az_.plot(zt[m], Z[zn.index(nm)][m], c=R[nm], lw=1.35, alpha=0.6, zorder=4 if nm == "Hilus" else 3,
                 solid_joinstyle="round")
    az_.set_yscale("log"); az_.set_ylim(0.9, 220)
    az_.minorticks_off()                       # (v10: back inside this loop; v9 left the pre-onset panel's limits to chance)
    az_.set_xlim(lo_, hi_)
# v10 (the user: "polish the highlights ... a lil janky"): each highlight swells out of its line and back into it (its width
# and its glow taper over the first and last quarter), instead of starting and stopping as a blob; the hilus's fall is
# the same, lighter
from matplotlib.patches import Polygon as _Poly  # noqa: E402


def swell(ax_, x, y, color, w0, w1, alpha=1.0, z=5.5, frac=0.3):
    """the line from x, y redrawn as one filled shape whose width (pt) runs from w0 at its ends to w1 in its middle, the
    change easing over the first and last `frac` of it: no caps, no overlaps, so a translucent glow has no seams."""
    T = ax_.transData
    D = T.transform(np.column_stack([x, y]))
    d = np.gradient(D, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-12
    n = np.column_stack([-d[:, 1], d[:, 0]])
    t = np.linspace(0, 1, len(D))
    env = np.sin(np.clip(np.minimum(t, 1 - t) / frac, 0, 1) * np.pi / 2) ** 2
    hw = (w0 + (w1 - w0) * env) / 2 * fig.dpi / 72.0
    poly = np.vstack([D + n * hw[:, None], (D - n * hw[:, None])[::-1]])
    ax_.add_patch(_Poly(T.inverted().transform(poly), closed=True, fc=color, ec="none", alpha=alpha, zorder=z))


def lighter(hexc, f):
    h = hexc.lstrip("#")
    return "#%02X%02X%02X" % tuple(int(round(int(h[i:i + 2], 16) + (255 - int(h[i:i + 2], 16)) * f)) for i in (0, 2, 4))


for nm, a, b in STORY + [FALL]:
    m = (zt >= a) & (zt <= b)
    y = Z[zn.index(nm)][m]
    bold = (nm, a, b) != FALL
    swell(azs, zt[m], y, R[nm], 0.0, 11.0 if bold else 7.0, alpha=0.14 if bold else 0.1, z=5)          # the glow
    swell(azs, zt[m], y, R[nm] if bold else lighter(R[nm], 0.25), 1.35, 3.4 if bold else 2.4, z=5.5)
azp.set_yticks([1, 10, 100]); azp.set_yticklabels(["1×", "10×", "100×"])
azp.set_ylabel("|CSD| ÷ own\nquiet baseline")
azs.set_yticks([]); azs.spines["left"].set_visible(False)
azp.set_xticks([-3, -2, -1, 0]); azp.set_xticklabels(["−3", "−2", "−1", "0"])
azs.set_xticks([0, 1, 2, 3, 4, 5])
S.text_at(fig, (SEZ0 + SEZ1) / 2, Y_Z + H_Z + 0.4, "Time from hilar onset (s)", fontsize=S.LABEL, ha="center")
S.text_at(fig, (PRE0 + PRE1) / 2, Y_Z + H_Z + 0.4, "before onset", fontsize=S.NOTE + 0.5, color=S.SOFT, ha="center")
# the break between the two clocks
for ax_ in (aup, azp):
    ax_.spines["right"].set_visible(False)
for yb, hb in ((Y_U, H_U), (Y_Z, H_Z)):
    for xb in (PRE1 + 0.03, SEZ0 - 0.07):
        S.text_at(fig, xb, yb + hb + 0.02, "/", fontsize=S.LABEL, color=S.SOFT, ha="center", va="center")
for k, (a0, a1) in enumerate(stages):
    for ax_ in (aus, azs):
        ax_.axvspan(a0, a1, color="#EEF1F4", lw=0, zorder=0)
    aus.text((a0 + a1) / 2, 1.1, PH[k][0], transform=aus.get_xaxis_transform(), ha="center", va="center", fontsize=S.NOTE,
             fontweight="bold", color="white", bbox=dict(boxstyle="circle,pad=0.25", fc=R[NEW[k]], ec="none"), zorder=7, clip_on=False)
# the story's words, each with its stage's number, beside the moment it names
rend = fig.canvas.get_renderer()
SAY = [("1", "Hilus", "Hilus rises first", 0.55, 150), ("2", "Supra blade", "Supra blade kicks in", 1.98, 150),
       ("3", "Infra blade", "Infra blade joins", 3.1, 2.25), ("4", "CA1", "CA1 joins last", 5.08, 2.25)]
for num, nm, txt, x, y in SAY:
    t_ = azs.text(x + 0.09, y, txt, color=R[nm], fontsize=S.LABEL - 0.5, fontweight="bold", ha="center", va="center",
                  zorder=6)                                # v10: no white box over the stage bands (no line runs here)
    bb = t_.get_window_extent(rend).transformed(azs.transData.inverted())
    azs.text(bb.x0 - 0.1, y, num, color="white", fontsize=S.NOTE - 1, fontweight="bold", ha="center", va="center", zorder=7,
             bbox=dict(boxstyle="circle,pad=0.22", fc=R[nm], ec="none"))
azs.text(1.13, 30, "…and falls back", color=R["Hilus"], fontsize=S.NOTE, fontweight="bold", ha="left", va="center", zorder=6)
for ax_ in (aus, azs):
    ax_.axvline(0, c=S.INK, lw=1.0, alpha=0.55, zorder=2)

S.save(fig, os.path.join(HERE, "out", "E_seizure.png"))
print("E: base %.1f Hz, -3..0 s %.1f Hz (%.1fx); unit %s; stage panels at x = %s in" %
      (base_hz, pre3, pre3 / base_hz, unit, ", ".join("%.2f" % x for x in xs)))
