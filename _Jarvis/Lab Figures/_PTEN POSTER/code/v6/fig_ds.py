"""PTEN poster v4: the dentate-spike figures redrawn at print size from the menus' own per-mouse tables
(Jeremy menu, tight layers, 2026-11-27; its follow-up 2026-11-25; the DS story menu 2026-11-23). One dot per mouse,
generous uncorrected tests as in the menus (pstats.py); brackets only where P < 0.05.

  DS_ab      sink size (a) and fast power for a standard sink (b): by IED status, by knockout level and against % KO
  DS_gain    LFP fast (250-500 Hz) gain at the DS in each layer: IED- below control, IED+ above (Jeremy menu Q4 d)
  DS_rates   BT and IED-class events per minute in every mouse (Q6 a), and the ROC for calling the IED+ mice (Q6 b,
             plus the DS story's held-out models)
  DS_cont    the continuum by layer: fast gain of the control mice's DS and of the IED+ mice's DS, BTs and IED-class
             events (Q7 d), now with the comparison the user asked for: IED+ DS against control (WT) DS
Prints every P it draws, and the IED+ DS against WT DS tests for the fast-power centre too (Q7 c), for the notes."""
import os
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
import style as S
import pstats as PS

HERE = os.path.dirname(os.path.abspath(__file__))
MEN = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\PTEN POSTER\Menus, etc"
JT = os.path.join(MEN, "Jeremy_Menu_TightLayers_112726", "tables")
Q1 = pd.read_csv(os.path.join(JT, "q1_q2_per_mouse.csv"))
Q4 = pd.read_csv(os.path.join(JT, "q4_q5_q7_q8_reads_per_mouse.csv"))
CNT = pd.read_csv(os.path.join(MEN, "Jeremy_Menu_Followup_112526", "tables", "counts_per_mouse.csv"))
BTF = pd.read_csv(os.path.join(MEN, "DS_Story_Menu_112326", "tables", "BT_IED_and_fast_power_per_mouse.csv"))
ML = pd.read_csv(os.path.join(MEN, "DS_Story_Menu_112326", "tables", "ML_heldout_calls_per_mouse.csv"))

C_CTL, C_NEG, C_POS = "#8C8C8C", "#E7A3C9", "#A8326E"           # the menus' group colours
C_DS, C_BT, C_IED = "#2F6DB5", "#8E44AD", "#D62728"              # the menus' event classes
GC = {"CTL": C_CTL, "IED-": C_NEG, "IED+": C_POS}
GROUP = dict(zip(Q1.mouse, Q1.group))
KO = dict(zip(Q1.mouse, Q1.knockout_pct))
LABS = list(Q1.mouse)
CTL = [m for m in LABS if GROUP[m] == "CTL"]
NEG = [m for m in LABS if GROUP[m] == "IED-"]
POS = [m for m in LABS if GROUP[m] == "IED+"]
PTEN = NEG + POS
M7 = "m7"
KOG = {m: ("CTL" if GROUP[m] == "CTL" else "low" if KO[m] < 10 else "high") for m in LABS}
LOG = []


def log(s):
    LOG.append(s)
    print(s)


def brackets(ax, pairs, top, step, fs=S.NOTE):
    """pairs: (x0, x1, P); drawn from the shortest span up, only P < 0.05."""
    y = top
    for x0, x1, p in sorted(pairs, key=lambda t: (abs(t[1] - t[0]), t[0])):
        if not (np.isfinite(p) and p < 0.05):
            continue
        ax.plot([x0, x0, x1, x1], [y - step * 0.25, y, y, y - step * 0.25], c=S.INK, lw=1.0, clip_on=False)
        ax.text((x0 + x1) / 2, y - step * 0.05, PS.stars(p), ha="center", va="bottom", fontsize=fs + 1, clip_on=False)
        y += step
    return y


def dots(ax, vals, groups, order, cols, rng, hollow_m7=True, s=70):
    """one dot per mouse in each group, the median as a bar; m7 a diamond."""
    for i, g in enumerate(order):
        ms = [m for m in vals if groups[m] == g and np.isfinite(vals[m])]
        if not ms:
            continue
        v = np.array([vals[m] for m in ms])
        ax.plot([i - 0.26, i + 0.26], [np.median(v)] * 2, c=S.INK, lw=2.0, zorder=3, solid_capstyle="butt")
        for m in ms:
            mk = "D" if m == M7 else "o"
            ax.scatter(i + rng.uniform(-0.12, 0.12), vals[m], s=s * (0.8 if mk == "D" else 1), marker=mk, color=cols[g],
                       edgecolor="white", lw=0.8, zorder=4)
    ax.set_xticks(range(len(order)))
    ax.set_xlim(-0.6, len(order) - 0.4)
    ax.tick_params(axis="x", length=0)


def group_ps(vals, groups, order):
    out = []
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            a = [vals[m] for m in vals if groups[m] == order[i]]
            b = [vals[m] for m in vals if groups[m] == order[j]]
            out.append((i, j, PS.two(a, b)))
    return out


def three_ways(fig, y, h, vals, ylabel, name, ylim, step):
    """IED status | knockout level | % knockout, on one y axis."""
    rng = np.random.RandomState(3)
    x0, w1, w2, w3, gap = 0.95, 3.55, 3.35, 5.6, 0.55
    a1 = S.ax_at(fig, x0, y, w1, h)
    a2 = S.ax_at(fig, x0 + w1 + gap, y, w2, h)
    a3 = S.ax_at(fig, x0 + w1 + w2 + 2 * gap, y, w3, h)
    dots(a1, vals, GROUP, ["CTL", "IED-", "IED+"], GC, rng)
    a1.set_xticklabels(["Control", "IED\u2212", "IED+"])
    kc = {"CTL": C_CTL, "low": "#D9A0BF", "high": "#B5567F"}
    kc = {"CTL": C_CTL, "low": C_NEG, "high": C_POS}
    gcol = {m: (C_CTL if GROUP[m] == "CTL" else C_NEG if GROUP[m] == "IED-" else C_POS) for m in vals}
    # knockout level: dots keep their IED colour, so m7 (high KO, no IEDs) shows where it sits
    for i, g in enumerate(["CTL", "low", "high"]):
        ms = [m for m in vals if KOG[m] == g]
        v = np.array([vals[m] for m in ms])
        a2.plot([i - 0.26, i + 0.26], [np.median(v)] * 2, c=S.INK, lw=2.0, zorder=3, solid_capstyle="butt")
        for m in ms:
            a2.scatter(i + rng.uniform(-0.12, 0.12), vals[m], s=56 if m == M7 else 70, marker="D" if m == M7 else "o",
                       color=gcol[m], edgecolor="white", lw=0.8, zorder=4)
    a2.set_xticks([0, 1, 2]); a2.set_xticklabels(["Control", "Low KO", "High KO"]); a2.set_xlim(-0.6, 2.4)
    a2.tick_params(axis="x", length=0)
    p1 = group_ps(vals, GROUP, ["CTL", "IED-", "IED+"])
    p2 = group_ps(vals, KOG, ["CTL", "low", "high"])
    for a in (a1, a2, a3):
        a.set_ylim(*ylim)
    top = ylim[1] - step * 1.9
    brackets(a1, p1, top, step)
    brackets(a2, p2, top, step)
    # % knockout: controls at 0, PTEN mice with a Theil-Sen line
    for m in vals:
        a3.scatter(KO[m] + (np.random.RandomState(hash(m) % 999).uniform(-0.5, 0.5) if GROUP[m] == "CTL" else 0), vals[m],
                   s=56 if m == M7 else 70, marker="D" if m == M7 else "o", color=gcol[m], edgecolor="white", lw=0.8, zorder=4)
    xs = np.array([KO[m] for m in PTEN]); ys = np.array([vals[m] for m in PTEN])
    from scipy.stats import theilslopes
    sl, ic, _, _ = theilslopes(ys, xs)
    xx = np.linspace(3, 29.5, 60)
    # least-squares line over the PTEN mice with its 95% confidence band (t, n - 2 df); the printed rho are Spearman
    from scipy import stats as _st
    n_ = len(xs); b1_, b0_ = np.polyfit(xs, ys, 1)
    res = ys - (b0_ + b1_ * xs); s_e = np.sqrt(np.sum(res ** 2) / (n_ - 2))
    se = s_e * np.sqrt(1 / n_ + (xx - xs.mean()) ** 2 / np.sum((xs - xs.mean()) ** 2))
    tq = _st.t.ppf(0.975, n_ - 2)
    a3.fill_between(xx, b0_ + b1_ * xx - tq * se, b0_ + b1_ * xx + tq * se, color=C_POS, alpha=0.14, lw=0, zorder=1)
    a3.plot(xx, b0_ + b1_ * xx, c=C_POS, lw=1.8, zorder=2)
    a3.axvline(15, c=S.FAINT, lw=0.9, ls=(0, (2, 2)), zorder=1)
    r_p, p_p = PS.corr(xs, ys)
    r_a, p_a = PS.corr([KO[m] for m in vals], [vals[m] for m in vals])
    a3.text(0.02, 0.98, "PTEN \u03c1 %+.2f, P %s\nall mice \u03c1 %+.2f, P %s" % (r_p, PS.pfmt(p_p), r_a, PS.pfmt(p_a)),
            transform=a3.transAxes, ha="left", va="top", fontsize=S.NOTE, color=S.SOFT, linespacing=1.1)
    a3.set_xlim(-2, 31); a3.set_xticks([0, 10, 20, 30])
    a1.set_ylabel(ylabel)
    for a in (a2, a3):
        a.set_yticklabels([])
    log("%s: IED groups %s; KO groups %s; PTEN rho %+.2f P %.3g; all rho %+.2f P %.3g" % (
        name, [(i, j, round(p, 4)) for i, j, p in p1], [(i, j, round(p, 4)) for i, j, p in p2], r_p, p_p, r_a, p_a))
    return a1, a2, a3


# =========================================================================== DS_ab
W, H = 14.75, 5.95
fig = S.figure(W, H)
sink = dict(zip(Q1.mouse, Q1.sink_control_eq_1))
fp = dict(zip(Q1.mouse, Q1.fast_power_at_standard_sink_dB))
a1, a2, a3 = three_ways(fig, 0.12, 2.15, sink, "DS sink\n(control average = 1)", "sink", (0, 3.25), 0.3)
b1, b2, b3 = three_ways(fig, 2.98, 2.15, fp, "Fast power for a\nstandard sink (dB)", "fast power at standard sink", (5, 27.5), 2.1)
b3.set_xlabel("PTEN knockout (% of granule cells)")
for a in (a1, a2, a3):
    a.set_xticklabels([]) if a is a3 else None
a3.set_xticklabels([])
# key
hs = [Line2D([], [], ls="", marker="o", ms=9, mfc=c, mec="white", label=l) for c, l in ((C_CTL, "Control"), (C_NEG, "PTEN IED\u2212"), (C_POS, "PTEN IED+"))]
hs.append(Line2D([], [], ls="", marker="D", ms=8, mfc=C_NEG, mec="white", label="m7 (24% KO, no IEDs)"))
fig.legend(handles=hs, loc="lower center", bbox_to_anchor=(0.5, 0.0), ncol=4, fontsize=S.NOTE, handletextpad=0.3, columnspacing=1.4)
S.save(fig, os.path.join(HERE, "out", "DS_ab.png"))

# =========================================================================== DS_gain (LFP fast gain by layer and group)
KEYS = [("upper", "MML"), ("upper", "OML"), ("lower", "MML"), ("lower", "OML")]


def q4(signal, measure_start, cls, key):
    d = Q4[(Q4.band == "notch") & (Q4.signal == signal) & (Q4["class"] == cls) & (Q4.blade == key[0]) & (Q4.layer == key[1])
           & Q4.measure.str.startswith(measure_start)]
    return dict(zip(d.mouse, d.value))


GAIN = "fast gain, dB over the moment before (250-500 Hz)"
CENTER = "fast-power center, Hz (added power, 100-500 Hz)"
W, H = 7.3, 2.75
fig = S.figure(W, H)
rng = np.random.RandomState(5)
for i, key in enumerate(KEYS):
    v = q4("lfp", GAIN, "DS", key)
    a = S.ax_at(fig, 0.82 + i * 1.66, 0.42, 1.28, 1.86)
    dots(a, v, GROUP, ["CTL", "IED-", "IED+"], GC, rng, s=46)
    a.set_xticklabels(["Ctl", "IED\u2212", "IED+"], fontsize=S.SMALL + 1)
    ps = group_ps(v, GROUP, ["CTL", "IED-", "IED+"])
    a.set_ylim(0, 22)
    brackets(a, ps, 15.0, 2.6, fs=S.SMALL)
    a.set_yticks([0, 5, 10, 15]) if i == 0 else a.set_yticks([0, 5, 10, 15], [])
    a.set_title("%s %s" % (key[0].capitalize(), key[1]), fontsize=S.NOTE, fontweight="bold", loc="left", pad=2)
    log("LFP fast gain %s: %s" % (key, [(i_, j_, round(p, 5)) for i_, j_, p in ps]))
fig.axes[0].set_ylabel("LFP fast gain (dB)")
S.save(fig, os.path.join(HERE, "out", "DS_gain.png"))

# =========================================================================== DS_rates
W, H = 14.75, 3.1
fig = S.figure(W, H)
a = S.ax_at(fig, 0.82, 0.4, 8.4, 2.2)
order = CTL + NEG + POS
bt = dict(zip(CNT.mouse, CNT.BT_per_min)); ied = dict(zip(CNT.mouse, CNT.IED_per_min))
for i, m in enumerate(order):
    a.bar(i, bt[m], color=C_BT, width=0.72, edgecolor="white", lw=0.6)
    a.bar(i, ied[m], bottom=bt[m], color=C_IED, width=0.72, edgecolor="white", lw=0.6)
hc = max(bt[m] + ied[m] for m in CTL)
a.axhline(hc, c=S.SOFT, lw=0.9, ls=(0, (3, 2)))
a.text(0.0, hc + 0.06, "highest control", fontsize=S.SMALL, color=S.SOFT, va="bottom")
a.set_xticks(range(len(order)))
a.set_xticklabels(["%s\n%s" % (m, "" if GROUP[m] == "CTL" else "%.0f%%" % KO[m]) for m in order], fontsize=S.SMALL)
for tl, m in zip(a.get_xticklabels(), order):
    tl.set_color(S.INK if GROUP[m] == "CTL" else GC[GROUP[m]] if GROUP[m] == "IED+" else "#C0679A")
a.tick_params(axis="x", length=0)
a.set_xlim(-0.6, len(order) - 0.4)
a.set_ylabel("Events per minute")
for x0, x1, lab, col in ((0, 6, "Control", S.INK), (7, 10, "PTEN IED−", "#C0679A"), (11, 15, "PTEN IED+", C_POS)):
    a.plot([x0 - 0.3, x1 + 0.3], [4.05, 4.05], c=col, lw=1.4, clip_on=False)
    a.text((x0 + x1) / 2, 4.12, lab, ha="center", va="bottom", fontsize=S.NOTE, color=col, fontweight="bold")
a.set_ylim(0, 4.0)
a.legend(handles=[Line2D([], [], ls="", marker="s", ms=11, mfc=C_BT, mec="none", label="Borderline transients (BTs)"),
                  Line2D([], [], ls="", marker="s", ms=11, mfc=C_IED, mec="none", label="IED-class events")],
         loc="upper left", bbox_to_anchor=(0.0, 0.93), fontsize=S.NOTE)
log("rates: highest control %.3f/min; IED+ BT+IED %s" % (hc, {m: round(bt[m] + ied[m], 2) for m in POS}))


def roc(score, pos):
    s = np.array([score[m] for m in PTEN]); y = np.array([m in pos for m in PTEN])
    th = np.r_[np.inf, np.sort(np.unique(s))[::-1]]
    tpr = [(s[y] >= t).mean() for t in th]; fpr = [(s[~y] >= t).mean() for t in th]
    auc = np.mean([(sp > sn) + 0.5 * (sp == sn) for sp in s[y] for sn in s[~y]])
    return np.array(fpr), np.array(tpr), auc


r = S.ax_at(fig, 10.0, 0.4, 2.0, 2.0)
r.plot([0, 1], [0, 1], c=S.FAINT, lw=0.9, ls=(0, (3, 2)))
dsfp = dict(zip(BTF.mouse, BTF.DS_fast_power_median_dB))
held = dict(zip(ML.mouse, ML.P_IEDplus_mean))
for score, lab, col, off in ((KO, "% knockout", "#C2571A", 0.0), (dsfp, "DS fast power", C_POS, 0.012), (held, "Held-out models", C_DS, -0.012)):
    f_, t_, auc = roc(score, set(POS))
    r.step(f_ + off, t_ + off, where="post", c=col, lw=2.0, label="%s  %.2f" % (lab, auc))
    log("ROC %s: AUC %.3f (9 PTEN mice)" % (lab, auc))
r.set_xlim(-0.03, 1.03); r.set_ylim(-0.03, 1.05)
r.set_xticks([0, 0.5, 1]); r.set_yticks([0, 0.5, 1])
r.set_xlabel("False positives"); r.set_ylabel("True positives")
r.legend(loc="lower left", bbox_to_anchor=(1.02, 0.0), fontsize=S.NOTE, handlelength=1.0, title="AUC, 9 PTEN mice", title_fontsize=S.NOTE, alignment="left")
S.save(fig, os.path.join(HERE, "out", "DS_rates.png"))

# =========================================================================== DS_cont (continuum by layer, with WT DS vs IED+ DS)
CATS = [("WT", "WT", C_CTL), ("DS", "DS", C_DS), ("BT", "BT", C_BT), ("IED", "IED", C_IED)]
W, H = 7.3, 3.4
fig = S.figure(W, H)
rng = np.random.RandomState(9)
for i, key in enumerate(KEYS):
    wt = q4("csd", GAIN, "DS", key)
    cls = {c: q4("csd", GAIN, c, key) for c in ("DS", "BT", "IED")}
    vals = {"WT": {m: wt[m] for m in CTL}, **{c: {m: cls[c].get(m, np.nan) for m in POS} for c in cls}}
    a = S.ax_at(fig, 0.82 + i * 1.66, 0.3, 1.34, 2.66)
    for j, (c, lab, col) in enumerate(CATS):
        v = np.array([x for x in vals[c].values() if np.isfinite(x)])
        a.plot([j - 0.28, j + 0.28], [np.median(v)] * 2, c=S.INK, lw=1.8, zorder=3, solid_capstyle="butt")
        for m, x in vals[c].items():
            if np.isfinite(x):
                a.scatter(j + rng.uniform(-0.1, 0.1), x, s=34, color=col, edgecolor="white", lw=0.6, zorder=4)
    for m in POS:
        a.plot([1, 2, 3], [vals[c].get(m, np.nan) for c in ("DS", "BT", "IED")], c=C_POS, lw=0.8, alpha=0.45, zorder=2)
    ps = [(0, 1, PS.two(list(vals["WT"].values()), list(vals["DS"].values())))]
    ps += [(0, k, PS.two(list(vals["WT"].values()), list(vals[c].values()))) for k, c in ((2, "BT"), (3, "IED"))]
    ps += [(1, k, PS.paired([vals[c][m] for m in POS], [vals["DS"][m] for m in POS])) for k, c in ((2, "BT"), (3, "IED"))]
    a.set_ylim(-2, 43)
    brackets(a, ps, 21.0, 4.3, fs=S.SMALL)
    a.set_xticks(range(4)); a.set_xticklabels([l for _c, l, _col in CATS], fontsize=S.SMALL, rotation=0)
    for tl, (_c, _l, col) in zip(a.get_xticklabels(), CATS):
        tl.set_color(col if col != C_CTL else S.INK)
    a.tick_params(axis="x", length=0); a.set_xlim(-0.55, 3.55)
    a.set_yticks([0, 10, 20]) if i == 0 else a.set_yticks([0, 10, 20], [])
    a.set_title("%s %s" % (key[0].capitalize(), key[1]), fontsize=S.NOTE, fontweight="bold", loc="left", pad=2)
    log("CSD fast gain %s: WT DS vs IED+ DS P %s; WT vs BT %s; WT vs IED %s; DS->BT paired %s; DS->IED paired %s" % (
        key, *[PS.pfmt(p) for _x, _y, p in ps]))
    wc = q4("csd", CENTER, "DS", key)
    log("   centre %s: WT DS vs IED+ DS P %s (medians %.0f vs %.0f Hz)" % (key, PS.pfmt(PS.two([wc[m] for m in CTL], [wc[m] for m in POS])),
        np.median([wc[m] for m in CTL]), np.median([wc[m] for m in POS])))
fig.axes[0].set_ylabel("Fast gain, 250\u2013500 Hz\n(dB over before)")
S.save(fig, os.path.join(HERE, "out", "DS_cont.png"))
# =========================================================================== DS_windows (follow-up 3 a, the rows the poster uses)
# the user (Rain): "only need the top time ranges (-170 to -130 with the +-25 ms) and the bottom DS sink +-3 ms windows".
# The DS drawn is a schematic of the mean DS shape (the follow-up page draws m13's mean DS; that trace is not in the tables).
from matplotlib.patches import FancyBboxPatch
W, H = 6.4, 2.6
fig = S.figure(W, H)
a = S.ax_at(fig, 0.15, 0.06, 6.1, 1.98)
t = np.linspace(-200, 100, 1200)
ds = -np.exp(-(t / 7.0) ** 2) + 0.12 * np.exp(-((t - 22) / 18.0) ** 2) + 0.1 * np.exp(-((t + 30) / 22.0) ** 2)
a.plot(t, 2.05 + 0.8 * ds, c=C_DS, lw=2.4, solid_capstyle="round", zorder=3)
a.text(-196, 2.22, "Mean dentate spike (schematic)", fontsize=S.SMALL + 0.5, color=C_DS, va="bottom")
a.plot([0, 0], [0.05, 2.45], c=S.INK, lw=0.9, ls=(0, (3, 2)), zorder=2)
a.text(3, 2.45, "DS peak", ha="left", va="top", fontsize=S.SMALL + 0.5, color=S.INK)
GREY_W, RED_W = "#8C939E", "#D9363E"
rows = [(1.15, "Fast power (240–420 Hz)", [(-170, -130, GREY_W, "baseline", "−170 to −130 ms"), (-25, 25, RED_W, "event", "±25 ms")]),
        (0.32, "Sink size", [(-3, 3, RED_W, "", "±3 ms")])]
for y, lab, spans in rows:
    a.text(-196, y + 0.22, lab, fontsize=S.SMALL + 0.5, fontweight="bold", va="bottom")
    a.plot([-200, 100], [y, y], c="#E3E6EA", lw=0.8, zorder=0)
    for x0, x1, col, name, txt in spans:
        a.add_patch(FancyBboxPatch((x0, y - 0.14), x1 - x0, 0.28, boxstyle="round,pad=0,rounding_size=1.2",
                                   mutation_aspect=0.08, fc=col, ec="none", zorder=2))
        lab2 = (name + "  " if name else "") + txt
        a.text(x1 + 5, y, lab2, fontsize=S.SMALL, va="center", color=S.INK)
a.set_xlim(-205, 105); a.set_ylim(0.05, 2.62)
a.set_yticks([]); a.spines["left"].set_visible(False)
a.set_xticks([-200, -150, -100, -50, 0, 50, 100]); a.set_xlabel("Time from the DS peak (ms)")
S.save(fig, os.path.join(HERE, "out", "DS_windows.png"))
open(os.path.join(HERE, "out", "ds_stats.txt"), "w", encoding="utf8").write("\n".join(LOG))
