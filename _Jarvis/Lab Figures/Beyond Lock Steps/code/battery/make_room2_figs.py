"""Extraction Room 2.0 -- the journal figures (2026-11-18).

For each target: Figure (a: the three best spike-based models, every held-out
call; b: their five most important parameters, consolidated) and Extended
Data figure (one row per parameter: where it is read on the waveform, how it
looks in a typical mouse of each group, every mouse's value), then a legends
page. Plus Figure 1 (every model's held-out score) and a Methods document.

Everything comes from Jarvis run r006 (260 tasks) on amber bundle v3 (2026-11-20, m21 in).
  python make_room2_figs.py      -> ../room2_figures/
"""
import json
import os
import sys
import textwrap

import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

import dsdata
import house as Hs
import measures as MS
from house import plt, ax_mm, text_mm, INK, MUTE, HAIR, CSD_CMAP, C_CTL, C_IEDN, C_IEDP, C_DS1, C_DS2, C_DS3

sys.path.insert(0, r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app")
from backend import er2run as R          # noqa: E402
from backend.er2 import engine as E      # noqa: E402
from backend.er2 import explain as EX    # noqa: E402

OUT = os.path.abspath(os.path.join(dsdata.HERE, "..", "room2_figures"))
os.makedirs(OUT, exist_ok=True)
RUN = "r006"
C_PTEN = "#C8591A"
PANEL = 8.0           # panel letter size, pt
T5, T6, T7 = 5.0, 6.0, 7.0
TARGETS = [("pten_vs_ctl", "PTEN against control"), ("ko_pct", "Knockout percentage"), ("low_vs_high", "Low against high knockout"),
           ("ied3", "Control, IED− and IED+"), ("iedpos_vs_iedneg", "IED+ against IED−")]
VIEW = {"core": "waveform and depth", "context": "waveform, depth and event context", "filters": "waveform and depth under seven filters",
        "before_after": "waveform, depth and power before and after", "events_all": "every per-event feature", "mouse": "per-mouse tables",
        "everything": "everything, nuisance included", "nuisance": "nuisance only"}
MODEL = {"linear": "Linear (L2)", "lasso": "Lasso (L1)", "forest": "Random forest", "boosting": "Gradient boosting", "mlp": "Small neural net",
         "deepsets": "Deep sets", "attention": "Attention network"}
SCORE = {"binary": "AUC", "multiclass": "macro AUC", "regression": "Spearman ρ"}
FILT = {"none": "no filter", "1_100": "1–100 Hz", "1_300": "1–300 Hz", "5_300": "5–300 Hz", "5_50": "5–50 Hz", "10_40": "10–40 Hz"}
STATW = {"median": "median", "iqr": "interquartile range", "mean": "mean", "sd": "standard deviation", "p10": "10th percentile", "p90": "90th percentile"}
# what each parameter is, in one plain line, and its unit
WHAT = {
    "blade_balance": ("Blade balance: (upper − lower) / (upper + lower) sink at the two main-sink rows, ±3 ms; negative = lower blade larger", ""),
    "sink_upper": ("Sink at the DS peak at the upper blade's main-sink row (−CSD, ±3 ms)", "µA/mm³"),
    "sink_lower": ("Sink at the DS peak at the lower blade's main-sink row (−CSD, ±3 ms)", "µA/mm³"),
    "sink_amp": ("Sink at the DS peak, mean of the two main-sink rows (−CSD, ±3 ms)", "µA/mm³"),
    "sink_area": ("Sink summed over −10 to +10 ms, mean of the two main-sink rows", "µA/mm³ × ms"),
    "sink_width_um": ("Spread in depth of the sink within a blade (weighted SD), mean of the two blades", "µm"),
    "source_amp": ("Source between the blades at the DS peak (mean of the source rows, ±3 ms)", "µA/mm³"),
    "source_over_sink": ("Source between the blades over the sink at the main-sink rows, per event", "ratio"),
    "lat_source_minus_sink": ("Peak time of the source minus peak time of the sink", "ms"),
    "net_between": ("Net CSD between the two blades' sinks (sink rows left out), over the sink", "ratio"),
    "cen_um": ("Centroid of the sink relative to the main-sink row, mean of the two blades (+ = farther from the cell layer)", "µm"),
    "cen_v": ("Centroid of the sink on the within-blade scale v (0 = cell-layer source, 1 = main sink), mean of the two blades", "v"),
    "lfp_max": ("Largest LFP at the DS peak over the analyzed band", "µV"),
    "lfp_fwhm": ("Width in time of the LFP at the source (full width at half maximum)", "ms"),
    "sink_fwhm": ("Duration of the sink at the main-sink rows (full width at half maximum)", "ms"),
}
TYPEW = {"ds1": "DS1", "ds2": "DS2", "ds3": "DS3", "unscored": "too small to score DS3"}


# ------------------------------------------------------------------ data
class Ctx(object):
    def __init__(self):
        self.res = {(r["target"], r["view"], r["model"]): r for r in R.results(RUN) if "score" in r}
        self.data = E.Data(1)
        self.P, self.pn, self.pf, self.pb = self.data.pooled()
        self.labs = self.data.labs
        self.sets = {}
        self.feats = {}

    def recs(self, es):
        if es not in self.sets:
            self.sets[es] = {r.lab: r for r in dsdata.load(es)}
        return self.sets[es]

    def ev_amber(self, item, lab):
        col = item.split("|")[0]
        if col == "share":
            col = "type_" + item.split("|")[1]
        if col not in self.data.efeat:
            return None
        mi = self.labs.index(lab)
        return self.data.X[self.data.bag == mi, self.data.efeat.index(col)]

    def ev(self, es, lab, base):
        key = (es, lab)
        if key not in self.feats:
            self.feats[key] = MS.event_features(self.recs(es)[lab])
        return np.asarray(self.feats[key].get(base, np.full(self.recs(es)[lab].n, np.nan)), float)

    def mouse_value(self, item):
        """Each mouse's value of a parameter as the models read it (pooled
        column; a set network's raw event feature is shown as the median)."""
        name = item if "|" in item else ("share|" + item[5:] if item.startswith("type_") else item + "|median")
        if name in self.pn:
            return self.P[:, self.pn.index(name)], name
        return None, name


def parse(item):
    """(filter set, base measure, statistic) of a parameter's name."""
    base, _, stat = item.partition("|")
    es, band = "v6", None
    if base.startswith("f_"):
        band, _, base = base[2:].partition("__")
        es = "b_" + band
    if base == "share":
        base, stat = "type_" + stat, ""
    return es, band, base, stat


BA_WIN = {"pre_far": "−500 to −200 ms", "pre_near": "−150 to −50 ms", "post_near": "+50 to +150 ms", "post_far": "+200 to +500 ms"}


def ba_parts(base):
    """(after-over-before?, band, window, depth bin) of a before/after parameter."""
    pp = base.startswith("ba_pp_")
    rest = base[6:] if pp else base[7:]
    band, _, rest = rest.partition("_")
    if pp:
        win, _, depth = rest.partition("_")
    else:
        win = next(w for w in BA_WIN if rest.startswith(w))
        depth = rest[len(win) + 1:]
    return pp, band, win, depth


def ba_words(base):
    pp, band, win, depth = ba_parts(base)
    what = "spiking (MUA)" if band == "MUA" else band + " Hz power"
    where = "whole shank" if depth == "shank" else "u %s to %s" % tuple(x.replace("-", "−") for x in depth.replace("u", "").split("_"))
    if pp:
        return "%s after over before (%s), %s" % (what[0].upper() + what[1:], "+200 to +500 against −500 to −200 ms" if win == "far"
                                                   else "+50 to +150 against −150 to −50 ms", where)
    return "%s over random moments, %s, %s" % (what[0].upper() + what[1:], BA_WIN[win], where)


def label_of(item):
    es, band, base, stat = parse(item)
    if base.startswith("ba_"):
        return ba_words(base) + (" (%s over events)" % STATW.get(stat, stat) if stat else "")
    if base.startswith("type_"):
        return "Share of events that are " + TYPEW[base[5:]]
    w = base.replace("_", " ")
    nice = {"blade_balance": "Blade balance", "sink_upper": "Upper-blade sink", "sink_lower": "Lower-blade sink", "sink_amp": "Sink size",
            "sink_area": "Sink area", "sink_width_um": "Sink spread in depth", "source_amp": "Source between the blades",
            "source_over_sink": "Source over sink", "lat_source_minus_sink": "Source-to-sink timing", "net_between": "Net source between blades",
            "cen_um": "Sink centroid (depth)", "cen_v": "Sink centroid (blade scale)", "lfp_max": "Largest LFP", "lfp_fwhm": "LFP duration",
            "sink_fwhm": "Sink duration"}.get(base, w)
    bits = []
    if stat:
        bits.append(STATW.get(stat, stat.replace("_median", " median").upper()) + " over events")
    if band:
        bits.append(FILT[band])
    return nice + (" (" + ", ".join(bits) + ")" if bits else "")


def classes(t, ctx):
    d = ctx.data
    mice, y, task, scheme, cls = E.target(d, t)
    if cls:
        cls = [(c[0].upper() + c[1:]).replace("IED-", "IED−") for c in cls]
    return mice, y, task, cls


def stars(p):
    """The significance sign (raw P, uncorrected)."""
    if p is None or not np.isfinite(p):
        return ""
    return "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "n.s."))


def pword(p):
    return "P = %s" % ("%.3f" % p if p >= 0.001 else "%.1e" % p)


def colors_for(t, cls):
    if t == "pten_vs_ctl":
        return [C_CTL, C_PTEN]
    if t == "ied3":
        return [C_CTL, C_IEDN, C_IEDP]
    if t == "iedpos_vs_iedneg":
        return [C_IEDN, C_IEDP]
    if t == "low_vs_high":
        return ["#F0B27A", "#8E2A0B"]
    return [C_PTEN]


def top_models(ctx, t, n=3):
    mine = [r for (tt, v, m), r in ctx.res.items() if tt == t and v != "nuisance"]
    return sorted(mine, key=lambda r: -r["score"]["main"])[:n]


def top_params(ctx, models, n=5):
    c = EX.consolidate(models, top_n=200)
    out, seen = [], set()
    for d in c["features"]:
        es, band, base, stat = parse(d["item"])
        if base in seen or d["item"] == "(everything else)":
            continue
        seen.add(base)
        out.append(d)
        if len(out) >= n:
            break
    return out


# ------------------------------------------------------------------ drawing helpers
def tidy(ax, size=T5):
    ax.tick_params(labelsize=size, length=2, width=0.5, pad=1.5)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def letter(fig, H, x, y, s):
    text_mm(fig, H, x, y, s, fontsize=PANEL, fontweight="bold", va="top")


def per_mouse_calls(r):
    per = {}
    for c in r["calls"]:
        v = np.atleast_1d(np.array(c["call"], float))
        p = per.setdefault(c["lab"], {"truth": c["truth"], "s": np.zeros(v.size), "n": 0})
        p["s"] += v
        p["n"] += 1
    return {k: (p["truth"], p["s"] / p["n"]) for k, p in per.items()}


def draw_model(fig, H, x, y, w, h, r, t, ctx, base):
    """One model's held-out calls."""
    from scipy import stats as st
    task = r["task"]
    cls = [(c[0].upper() + c[1:]).replace("IED-", "IED−") for c in r["classes"]] if r["classes"] else None
    calls = per_mouse_calls(r)
    cols = colors_for(t, cls)
    ax = ax_mm(fig, H, x, y, w, h)
    tidy(ax)
    rng = np.random.default_rng(4)
    if task == "binary":
        for c in (0, 1):
            v = [m[0] for lab, (tr, m) in calls.items() if tr == c]
            xs = c + rng.uniform(-0.16, 0.16, len(v))
            ax.scatter(xs, v, s=9, color=cols[c], edgecolors="white", linewidths=0.4, zorder=3)
            if v:
                ax.plot([c - 0.28, c + 0.28], [np.median(v)] * 2, color=INK, lw=0.9, zorder=4)
        ax.axhline(0.5, color=HAIR, lw=0.6, ls=(0, (3, 2)), zorder=1)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(cls, fontsize=T5)
        ax.set_xlim(-0.6, 1.6)
        ax.set_ylim(-0.03, 1.03)
        ax.set_ylabel("Held-out score for %s" % cls[1], fontsize=T5)
    elif task == "regression":
        tr = np.array([v[0] for v in calls.values()])
        pr = np.array([v[1][0] for v in calls.values()])
        meta = {m["lab"]: m for m in ctx.data.mice}
        c_ = [Hs.GROUP_COL[meta[l]["subgroup"]] for l in calls]
        lim = [min(tr.min(), pr.min()) - 3, max(tr.max(), pr.max()) + 3]
        ax.plot(lim, lim, color=HAIR, lw=0.6, ls=(0, (3, 2)))
        ax.scatter(tr, pr, s=9, c=c_, edgecolors="white", linewidths=0.4, zorder=3)
        ax.set_xlim(lim)
        ax.set_ylim(lim)
        ax.set_xlabel("True knockout (%)", fontsize=T5)
        ax.set_ylabel("Held-out guess (%)", fontsize=T5)
    else:
        M = np.zeros((3, 3))
        for lab, (tr, m) in calls.items():
            M[int(tr), int(np.argmax(m))] += 1
        ax.imshow(M, cmap="Greys", vmin=0, vmax=max(M.max(), 1))
        for i in range(3):
            for j in range(3):
                ax.text(j, i, "%d" % M[i, j], ha="center", va="center", fontsize=T6, color="white" if M[i, j] > M.max() / 2 else INK)
        ax.set_xticks(range(3))
        ax.set_xticklabels(cls, fontsize=T5)
        ax.set_yticks(range(3))
        ax.set_yticklabels(cls, fontsize=T5)
        ax.set_xlabel("Held-out call", fontsize=T5)
        ax.set_ylabel("True group", fontsize=T5)
        for s in ax.spines.values():
            s.set_visible(False)
    if task == "binary":
        a_ = [m[0] for lab, (tr, m) in calls.items() if tr == 0]
        b_ = [m[0] for lab, (tr, m) in calls.items() if tr == 1]
        p = st.mannwhitneyu(b_, a_, alternative="greater").pvalue if a_ and b_ else np.nan
        test = "one-sided Mann-Whitney on held-out scores"
    elif task == "regression":
        tr = np.array([v[0] for v in calls.values()])
        pr = np.array([v[1][0] for v in calls.values()])
        p = st.spearmanr(tr, pr).pvalue
        test = "Spearman, held-out guess against truth"
    else:
        tr = np.array([v[0] for v in calls.values()]).astype(int)
        pc = np.array([np.argmax(v[1]) for v in calls.values()])
        k_ = int((tr == pc).sum())
        p = float(st.binomtest(k_, tr.size, 1.0 / 3, alternative="greater").pvalue)
        test = "binomial, calls right against 1 in 3"
    r["_p"], r["_test"] = p, test
    text_mm(fig, H, x, y - 7.2, MODEL[r["model"]], fontsize=T6, fontweight="bold")
    text_mm(fig, H, x, y - 4.4, "Inputs: " + VIEW[r["view"]], fontsize=T5, color=MUTE)
    sc = r["score"]["main"]
    text_mm(fig, H, x, y - 1.7, "%s %.2f %s  (bar %.2f; nuisance only %.2f)" % (SCORE[task], sc, stars(p), E.BAR[task], base), fontsize=T5)
    extra = ("%d%% of calls right" % round(100 * r["score"]["accuracy"])) if "accuracy" in r["score"] else ("mean error %.1f%%" % r["score"]["mae"])
    text_mm(fig, H, x, y + h + (9.5 if task == "multiclass" else 7.5), "%s · %s %s" % (extra, pword(p), stars(p)), fontsize=4.6, color=MUTE)
    return ax


def where_panel(fig, H, x, y, w, h, r, base):
    """The mean CSD of one recording with the rows (and time) the parameter reads."""
    import make_leads as ML
    rows, win, kind = ML.place(r, base)
    ax = ax_mm(fig, H, x, y, w, h)
    k = r.landmarks
    lo, hi = max(0, k["rowU"] - 6), min(63, k["rowL"] + 6)
    M = dsdata.fill_bad(r.csd.mean(axis=0).T, r.bad_rows).T[lo:hi + 1]
    v = np.nanpercentile(np.abs(M), 99)
    ax.imshow(M, aspect="auto", cmap=CSD_CMAP, vmin=-v, vmax=v, extent=[r.t_ms[0], r.t_ms[-1], (hi - lo + 0.5) * 50, -25],
              interpolation="bilinear")
    for row, word, col in rows:
        yy = (row - lo) * 50
        ax.plot([-30, 30], [yy, yy], color=col if word else "#7A5195", lw=0.8 if word else 0.35, alpha=0.95 if word else 0.7)
    if win is not None:
        ax.axvspan(win[0], win[1], color="black", alpha=0.10, lw=0)
    else:
        ax.axvspan(-3, 3, color="black", alpha=0.10, lw=0)
    ax.set_xlim(-30, 30)
    ax.set_xticks([-30, 0, 30])
    ax.set_xlabel("Time from DS peak (ms)", fontsize=T5)
    ax.set_ylabel("Depth (µm)", fontsize=T5)
    tidy(ax, 4.6)
    return ax


def ba_panel(fig, H, x, y, w, h, r, base):
    """The parameter's band around the DS, depth by time, in one recording:
    each event's power over random moments (log2), median over events."""
    import make_leads as ML
    pp, band, win, depth = ba_parts(base)
    got = ML.around_maps(r, band, "all")
    ax = ax_mm(fig, H, x, y, w, h)
    if got is None:
        return ax
    u, M, n = got
    o = np.argsort(u)
    show = (u >= -2.0) & (u <= 2.5)
    v = float(np.nanpercentile(np.abs(M[show]), 98)) or 1.0
    ax.pcolormesh(np.arange(-50, 51) * 10.0, u[o], M[o], cmap="RdBu_r", vmin=-v, vmax=v, shading="nearest", rasterized=True)
    ax.text(1.02, 1.0, "±%.1f" % v, transform=ax.transAxes, fontsize=3.8, va="top", color=MUTE)
    for yy in (0, 1):
        ax.axhline(yy, color=INK, lw=0.4, ls=(0, (2, 2)))
    ax.axvline(0, color=INK, lw=0.4)
    wins = {"near": [(-150, -50), (50, 150)], "far": [(-500, -200), (200, 500)]}[win] if pp else [{"pre_far": (-500, -200), "pre_near": (-150, -50),
                                                                                                     "post_near": (50, 150), "post_far": (200, 500)}[win]]
    if depth != "shank":
        a_, b_ = (float(x_) for x_ in depth.replace("u", "").split("_"))
        for w0, w1 in wins:
            ax.add_patch(Rectangle((w0, a_), w1 - w0, b_ - a_, fill=False, ec="#6A3D9A", lw=0.8))
    else:
        for w0, w1 in wins:
            ax.axvspan(w0, w1, color="#6A3D9A", alpha=0.12, lw=0)
    ax.set_ylim(min(u.max(), 2.5), max(u.min(), -2.0))
    ax.set_xlim(-500, 500)
    ax.set_xticks([-500, 0, 500])
    ax.set_xlabel("Time from DS peak (ms)", fontsize=T5)
    ax.set_ylabel("Depth (u)", fontsize=T5)
    tidy(ax, 4.6)
    return ax


def type_panel(fig, H, x, y, w, h, ctx, mice_order, cols_of):
    ax = ax_mm(fig, H, x, y, w, h)
    tidy(ax, 4.6)
    d = ctx.data
    idx = {f: d.efeat.index("type_" + f) for f in ("ds1", "ds2", "ds3", "unscored")}
    for j, lab in enumerate(mice_order):
        mi = d.labs.index(lab)
        X = d.X[d.bag == mi]
        un = X[:, idx["unscored"]] > 0.5
        parts = {"ds1": (X[:, idx["ds1"]] > 0.5) & ~un, "ds2": (X[:, idx["ds2"]] > 0.5) & ~un, "ds3": X[:, idx["ds3"]] > 0.5, "unscored": un}
        b0 = 0.0
        for f, col in (("ds1", C_DS1), ("ds2", C_DS2), ("ds3", C_DS3), ("unscored", "#CFCFCF")):
            s = float(parts[f].mean())
            ax.bar([j], [s], bottom=[b0], color=col, width=0.78, lw=0)
            b0 += s
    ax.set_xticks(range(len(mice_order)))
    ax.set_xticklabels(mice_order, fontsize=3.9, rotation=90)
    for i_, lab in enumerate(mice_order):
        ax.get_xticklabels()[i_].set_color(cols_of(lab))
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Share of events", fontsize=T5)
    return ax


def dist_panel(fig, H, x, y, w, h, ctx, item, examples, unit, short=""):
    """Per-event values of the parameter in one typical mouse of each group."""
    es, band, base, stat = parse(item)
    ax = ax_mm(fig, H, x, y, w, h)
    tidy(ax, 4.6)
    allv = []
    for lab, col, word in examples:
        v = ctx.ev_amber(item, lab)
        if v is None:
            v = ctx.ev(es, lab, base)
        allv.append(v[np.isfinite(v)])
    pool = np.concatenate(allv) if allv else np.array([0.0])
    lo, hi = np.percentile(pool, [1, 99]) if pool.size else (0, 1)
    if hi <= lo:
        hi = lo + 1
    bins = np.linspace(lo, hi, 26)
    for (lab, col, word), v in zip(examples, allv):
        ax.hist(np.clip(v, lo, hi), bins=bins, density=True, histtype="stepfilled", color=col, alpha=0.30, lw=0)
        ax.hist(np.clip(v, lo, hi), bins=bins, density=True, histtype="step", color=col, lw=0.8)
    top = ax.get_ylim()[1]
    for k_, ((lab, col, word), v) in enumerate(zip(examples, allv)):
        if not v.size:
            continue
        # mark the statistic the models read, not always the median
        if stat in ("", "median") or stat.endswith("_median"):
            ax.axvline(np.median(v), color=col, lw=0.9, ls=(0, (2.5, 1.5)))
        elif stat in ("mean", "p10", "p90"):
            ax.axvline({"mean": np.mean(v), "p10": np.percentile(v, 10), "p90": np.percentile(v, 90)}[stat], color=col, lw=0.9, ls=(0, (2.5, 1.5)))
        elif stat == "iqr":
            q1, q3 = np.percentile(v, [25, 75])
            yy = top * (0.95 - 0.08 * k_)
            ax.plot([q1, q3], [yy, yy], color=col, lw=0.8)
            ax.plot([np.median(v)], [yy], marker="o", ms=2.2, color=col)
        elif stat == "sd":
            m_, s_ = np.mean(v), np.std(v)
            yy = top * (0.95 - 0.08 * k_)
            ax.plot([max(lo, m_ - s_), min(hi, m_ + s_)], [yy, yy], color=col, lw=0.8)
            ax.plot([m_], [yy], marker="o", ms=2.2, color=col)
    ax.set_ylim(0, top)
    ax.set_xlabel(short + (" (" + unit + ")" if unit else ""), fontsize=T5)
    ax.set_ylabel("Events (density)", fontsize=T5)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    return ax


def value_panel(fig, H, x, y, w, h, ctx, t, item, unit):
    """Every mouse's value, by group (or against knockout)."""
    vals, name = ctx.mouse_value(item)
    ax = ax_mm(fig, H, x, y, w, h)
    tidy(ax, 4.6)
    d = ctx.data
    mice, yv, task, cls = classes(t, ctx)
    rng = np.random.default_rng(9)
    if vals is None:
        ax.text(0.5, 0.5, "not available", transform=ax.transAxes, ha="center", fontsize=T5)
        return ax, None
    import make_leads as ML
    from scipy import stats as st
    lims = ML.outlier_limits(vals)
    shown = np.clip(vals, lims[0], lims[1])
    out = np.isfinite(vals) & ((vals < lims[2]) | (vals > lims[3]))
    if task == "regression":
        ko = d.ko
        c_ = [Hs.GROUP_COL[m["subgroup"]] for m in d.mice]
        xs = np.where(d.group == "CTL", rng.uniform(-1.5, 1.5, ko.size), ko)
        ok = np.isfinite(vals)
        ax.scatter(xs[ok & ~out], shown[ok & ~out], s=8, c=[c_[i] for i in np.where(ok & ~out)[0]], edgecolors="white", linewidths=0.35, zorder=3)
        for i in np.where(out)[0]:
            ax.scatter([xs[i]], [shown[i]], marker="^" if vals[i] > lims[3] else "v", s=12, color=c_[i], zorder=3)
            ax.text(xs[i] + 0.8, shown[i], ("%s %s" % (d.labs[i], ML.fmt(vals[i]))).replace("-", "−"), fontsize=3.8, va="center", color=MUTE)
        p = st.spearmanr(ko[ok], vals[ok]).pvalue
        ax.text(0.98, 0.98, ("ρ %+.2f %s" % (st.spearmanr(ko[ok], vals[ok]).correlation, stars(p))).replace("-", "−"), transform=ax.transAxes,
                ha="right", va="top", fontsize=4.8)
        ax.set_xlabel("Knockout (%)", fontsize=T5)
        ax.set_xticks([0, 10, 20, 30])
        ax.set_xticklabels(["CTL", "10", "20", "30"])
    else:
        cols = colors_for(t, cls)
        for c in range(len(cls)):
            sel = np.array([i for i in mice[yv == c] if np.isfinite(vals[i])], int)
            xs = c + rng.uniform(-0.15, 0.15, sel.size)
            for xx, i in zip(xs, sel):
                if out[i]:
                    ax.scatter([xx], [shown[i]], marker="^" if vals[i] > lims[3] else "v", s=12, color=cols[c], zorder=3)
                    ax.text(xx + 0.12, shown[i], ("%s %s" % (d.labs[i], ML.fmt(vals[i]))).replace("-", "−"), fontsize=3.8, va="center", color=MUTE)
                else:
                    ax.scatter([xx], [vals[i]], s=8, color=cols[c], edgecolors="white", linewidths=0.35, zorder=3)
            if sel.size:
                med = np.median(vals[sel])
                if lims[0] <= med <= lims[1]:
                    ax.plot([c - 0.27, c + 0.27], [med] * 2, color=INK, lw=0.9, zorder=4)
        ax.set_xticks(range(len(cls)))
        ax.set_xticklabels([c_.replace(" (", "\n(") for c_ in cls], fontsize=4.4)
        ax.set_xlim(-0.6, len(cls) - 0.4)
    es, band, base, stat = parse(item)
    word = "share" if base.startswith("type_") else (STATW.get(stat, "median") if not stat.endswith("_median") else stat[:-7].upper() + " median")
    ax.set_ylabel(("Each mouse's " + word) + ("\n(" + unit + ")" if unit else ""), fontsize=T5)
    span = lims[1] - lims[0]
    if task != "regression":
        # significance between the groups (raw P, uncorrected): Mann-Whitney for two, Kruskal-Wallis for three
        grp = [vals[np.array([i for i in mice[yv == c] if np.isfinite(vals[i])], int)] for c in range(len(cls))]
        if all(g.size >= 2 for g in grp):
            p = st.mannwhitneyu(grp[0], grp[1]).pvalue if len(grp) == 2 else st.kruskal(*grp).pvalue
            ytop = lims[1] + span * 0.05
            ax.plot([0, len(cls) - 1], [ytop, ytop], color=INK, lw=0.5)
            ax.text((len(cls) - 1) / 2.0, ytop + span * 0.01, stars(p), ha="center", va="bottom", fontsize=5.6 if stars(p) != "n.s." else 4.6)
            ax.set_ylim(lims[0] - span * 0.04, lims[1] + span * 0.16)
            return ax, name
    ax.set_ylim(lims[0] - span * 0.04, lims[1] + span * 0.06)
    return ax, name


def typical(ctx, t, item):
    """One typical mouse per group (closest to its group's median of the parameter)."""
    vals, _ = ctx.mouse_value(item)
    mice, yv, task, cls = classes(t, ctx)
    out = []
    if task == "regression":
        groups = [("CTL", ctx.data.group == "CTL", C_CTL, "control"), ("high", (ctx.data.group == "PTEN") & (ctx.data.ko >= 15), C_IEDP, "knockout 15%+")]
        for g, m, col, word in groups:
            idx = np.where(m & np.isfinite(vals))[0]
            if idx.size:
                i = idx[np.argmin(np.abs(vals[idx] - np.median(vals[idx])))]
                out.append((ctx.labs[i], col, word))
        return out
    cols = colors_for(t, cls)
    for c in range(len(cls)):
        idx = np.array([i for i in mice[yv == c] if np.isfinite(vals[i])])
        if idx.size:
            i = idx[np.argmin(np.abs(vals[idx] - np.median(vals[idx])))]
            out.append((ctx.labs[i], cols[c], cls[c].split(" (")[0]))
    return out


# ------------------------------------------------------------------ the figures
def main_figure(pdf, ctx, t, title, fig_no):
    H = 128.0
    fig = Hs.page(H)
    Hs.stamp(fig, "UNCORRECTED")
    models = top_models(ctx, t)
    params = top_params(ctx, models)
    task = models[0]["task"]
    base = max([r["score"]["main"] for (tt, v, m), r in ctx.res.items() if tt == t and v == "nuisance"])
    text_mm(fig, H, 3, 4, "Fig. %d | %s: the three best spike-based models and what carried them" % (fig_no, title), fontsize=T7, fontweight="bold")
    letter(fig, H, 3, 9, "a")
    for k, r in enumerate(models):
        draw_model(fig, H, 16 + k * 58, 19, 40, 36, r, t, ctx, base)
    letter(fig, H, 3, 70, "b")
    text_mm(fig, H, 9, 71.5, "The five parameters that carried these three models most", fontsize=T6, fontweight="bold")
    ax = ax_mm(fig, H, 78, 76, 72, 44)
    tidy(ax)
    pts = [d["points"] for d in params]
    ax.barh(range(len(params)), pts, color="#4C78A8", height=0.62)
    for i, d in enumerate(params):
        ax.text(pts[i] + max(pts) * 0.02, i, "%d of 3 models · %d of 3 methods" % (d["n_models"], d["n_methods"]), fontsize=4.4, va="center",
                color=MUTE)
    ax.set_yticks(range(len(params)))
    ax.set_yticklabels([""] * len(params))
    for i, d in enumerate(params):
        lab = label_of(d["item"])
        for j, ln in enumerate(textwrap.wrap(lab, 44)):
            ax.text(-max(pts) * 0.03, i + (j - (len(textwrap.wrap(lab, 44)) - 1) / 2.0) * 0.32, ln, ha="right", va="center", fontsize=4.8)
    ax.invert_yaxis()
    ax.set_xlim(0, max(pts) * 1.55)
    ax.set_xlabel("Importance (rank points, summed over methods and models, per model)", fontsize=T5)
    pdf.savefig(fig)
    fig.savefig(os.path.join(OUT, "Fig%d_%s.png" % (fig_no, t)), dpi=300)
    plt.close(fig)
    return models, params, base


def extended_figure(pdf, ctx, t, title, fig_no, params):
    H = 236.0
    fig = Hs.page(H)
    Hs.stamp(fig, "UNCORRECTED")
    mice, yv, task, cls = classes(t, ctx)
    text_mm(fig, H, 3, 4, "Extended Data Fig. %d | %s: the five parameters, what they are and how they look" % (fig_no, title), fontsize=T7,
            fontweight="bold")
    heads = ["Where it is read (typical mouse)", "Every event, a typical mouse per group", "Every mouse"]
    for x, s in ((44, heads[0]), (96, heads[1]), (153, heads[2])):
        text_mm(fig, H, x, 11, s, fontsize=T5, color=MUTE, ha="center")
    if task == "regression":
        for j, (g, nm) in enumerate((("CTL", "Control"), ("IED-", "IED−"), ("IED+", "IED+"))):
            fig.add_artist(plt.Circle(((140 + j * 12) / Hs.W, 1 - 14.2 / H), 0.0045, color=Hs.GROUP_COL[g], transform=fig.transFigure))
            text_mm(fig, H, 141.5 + j * 12, 14.2, nm, fontsize=4.4)
    meta = {m["lab"]: m for m in ctx.data.mice}
    cols_of = lambda lab: Hs.GROUP_COL[meta[lab]["subgroup"]]
    for k, d in enumerate(params):
        y0 = 17 + k * 44
        item = d["item"]
        es, band, base, stat = parse(item)
        what, unit = WHAT.get(base, (base.replace("_", " "), ""))
        if base.startswith("ba_"):
            what, unit = ("Each event's %s, log2 (0 = no change); spiking = 300–3000 Hz, rectified" % (
                "power after over before" if base.startswith("ba_pp_") else "power over random moments"), "log2")
        letter(fig, H, 3, y0 - 1, "abcde"[k])
        text_mm(fig, H, 9, y0 + 0.5, label_of(item), fontsize=T6, fontweight="bold")
        for j, ln in enumerate(textwrap.wrap(("" if base.startswith("type_") else what + "."), 52)):
            text_mm(fig, H, 9, y0 + 4.5 + j * 2.6, ln, fontsize=4.4, color=MUTE)
        ex = typical(ctx, t, item)
        if base.startswith("type_"):
            order = [l for l in ctx.labs if meta[l]["subgroup"] == "CTL"] + [l for l in ctx.labs if meta[l]["subgroup"] == "IED-"] + \
                [l for l in ctx.labs if meta[l]["subgroup"] == "IED+"]
            type_panel(fig, H, 70, y0 + 3, 54, 30, ctx, order, cols_of)
            for j, (nm, col) in enumerate((("DS1", C_DS1), ("DS2", C_DS2), ("DS3", C_DS3), ("no DS3 score", "#CFCFCF"))):
                fig.add_artist(Rectangle(((9 + (j % 2) * 26) / Hs.W, 1 - (y0 + 9.2 + (j // 2) * 4) / H), 1.8 / Hs.W, 1.8 / H, color=col,
                                         transform=fig.transFigure))
                text_mm(fig, H, 11.6 + (j % 2) * 26, y0 + 8.3 + (j // 2) * 4, nm, fontsize=4.4)
            text_mm(fig, H, 9, y0 + 18, "Each mouse's events by the winning", fontsize=4.4, color=MUTE)
            text_mm(fig, H, 9, y0 + 20.6, "classifier's call (DS3: relative sink", fontsize=4.4, color=MUTE)
            text_mm(fig, H, 9, y0 + 23.2, "within ±0.5 between the two layers;", fontsize=4.4, color=MUTE)
            text_mm(fig, H, 9, y0 + 25.8, "no score: too small, or no two layers to", fontsize=4.4, color=MUTE)
            text_mm(fig, H, 9, y0 + 28.4, "compare, as in m3).", fontsize=4.4, color=MUTE)
        else:
            rec = ctx.recs(es if not base.startswith("ba_") else "v6").get(ex[-1][0]) if ex else None
            if rec is not None and rec.landmarks is not None:
                if base.startswith("ba_"):
                    ba_panel(fig, H, 24, y0 + 13, 24, 24, rec, base)
                    text_mm(fig, H, 24, y0 + 11.2, "%s (%s), log2 over random" % (rec.lab, ex[-1][2]), fontsize=4.4, color=ex[-1][1])
                else:
                    where_panel(fig, H, 24, y0 + 13, 24, 24, rec, base)
                    text_mm(fig, H, 24, y0 + 11.2, "%s (%s)" % (rec.lab, ex[-1][2]), fontsize=4.4, color=ex[-1][1])
            dist_panel(fig, H, 80, y0 + 3, 36, 26, ctx, item, ex, unit, label_of(item).split(" (")[0])
            for j, (lab, col, word) in enumerate(ex):
                text_mm(fig, H, 80 + j * 13, y0 + 36, "%s %s" % (lab, word.split(" (")[0]), fontsize=4.2, color=col)
        ax, name = value_panel(fig, H, 136, y0 + 3, 34, 28, ctx, t, item, unit)
    pdf.savefig(fig)
    fig.savefig(os.path.join(OUT, "ExtendedDataFig%d_%s.png" % (fig_no, t)), dpi=300)
    plt.close(fig)


def legends_page(pdf, t, title, fig_no, models, params, base, ctx):
    H = 236.0
    fig = Hs.page(H)
    Hs.stamp(fig, "UNCORRECTED")
    task = models[0]["task"]
    mice, yv, _, cls = classes(t, ctx)
    n = len(mice)
    scheme = "one control and one PTEN mouse at a time (all 63 pairs)" if t == "pten_vs_ctl" else "one mouse at a time"
    m_txt = "; ".join("%s on %s, %s %.2f" % (MODEL[r["model"]], VIEW[r["view"]], SCORE[task], r["score"]["main"]) for r in models)
    lg = [("Fig. %d | %s: the three best spike-based models and what carried them." % (fig_no, title),
           "a, The three spike-based models with the highest held-out score among 52 fitted for this target (%s). Every call is made on a mouse the "
           "model never saw: the mice are held out %s, and nothing about a held-out mouse is used to train, choose inputs, scale or fill in values. "
           "%s Dots are mice (n = %d), colored by group; black lines are group medians. Significance signs (raw P, uncorrected for the 260 models or "
           "the choice of these three): one-sided Mann-Whitney test of the held-out scores between the two groups; Spearman correlation of the held-out "
           "guess with the true knockout; binomial test of the share of held-out calls right against 1 in 3 for three groups; * P < 0.05, ** P < 0.01, "
           "*** P < 0.001, n.s. not significant. The bar set beforehand is %s %.2f; the best model "
           "given only nuisance values (where the dentate sat on the probe, the year recorded, the event count and recording length) reaches %.2f. "
           "b, The five parameters that carried these three models most, after consolidating four ways of opening a model on held-out mice "
           "(permutation of the parameter, Shapley values, retraining without its family, attention weights): each method ranks parameters, first "
           "place earns 1 point and last 0, and points are summed over methods and models and divided by the number of models. A parameter that "
           "appears under several statistics or filters is shown once, at its best-ranked form. Text beside each bar: how many of the three "
           "models and of the methods put it in their top ten." % (
               m_txt, scheme,
               {"binary": "Panels show each mouse's held-out score (mean over the tests that held it out; 0.5 dashed).",
                "regression": "Panels show each mouse's held-out guess against its true knockout (identity dashed); controls are at 0 %.",
                "multiclass": "Panels show held-out calls against true group (counts of mice)."}[task], n, SCORE[task], E.BAR[task], base)),
          ("Extended Data Fig. %d | %s: the five parameters, what they are and how they look." % (fig_no, title),
           "One row per parameter of Fig. %d b (a–e). Left, where the parameter is read: the recording's mean current source density (CSD) "
           "around the dentate spike (blue sink, red source) in a typical mouse of the last group, with the rows the parameter reads drawn on it "
           "(blue: the two blades' main-sink rows; red: the source rows; purple: further rows used) and the time window shaded. Middle, the "
           "parameter for every event of one typical mouse per group (the mouse closest to its group's median; dashed line: that mouse's median); "
           "values beyond the 1st and 99th percentiles are drawn at the edge. For the share of DS1, DS2 and DS3 events, the bars show every "
           "mouse's events by the winning classifier's call (DS3: relative sink within ±0.5; gray: no DS3 score, because the two layer sinks are "
           "under the noise floor or, as in m3, DS1's and DS2's sinks sit at the same contact so there are no two layers to compare). Right, each mouse's value "
           "as the models read it (the statistic named in the row title; for a set network, which reads every event, the mouse's median), with "
           "group medians; a mouse beyond three interquartile ranges is drawn at the edge as a triangle with its value. In the middle panels, "
           "dashed lines mark the statistic the models read (median, mean or a percentile); a bar with a dot marks mean ± SD or the middle half "
           "around the median. Significance signs over the right panels (raw P, uncorrected): two-sided Mann-Whitney test between two groups, "
           "Kruskal-Wallis across three, Spearman correlation with knockout for the knockout target." % fig_no),
          ("Reading these figures.",
           "Exploratory. 260 models were fitted over five targets, eight input views and seven model families on 9 to 16 mice (one recording per "
           "mouse; Halo event set, %d events). Scores are held-out, but the best of many models can reach the bar by chance, and with one mouse "
           "held out a model that learned nothing scores below 0.5, so 0.5 is not the chance line; a shuffled-label check and new mice are "
           "the tests these figures call for. No P value here is a finding." % ctx.data.X.shape[0])]
    y = 6
    for head, body in lg:
        text_mm(fig, H, 4, y, head, fontsize=T6, fontweight="bold")
        y += 4
        for ln in textwrap.wrap(body, 150):
            text_mm(fig, H, 4, y, ln, fontsize=T5 + 0.3)
            y += 2.9
        y += 4
    pdf.savefig(fig)
    plt.close(fig)


def overview(pdf, ctx):
    H = 138.0
    fig = Hs.page(H)
    Hs.stamp(fig, "UNCORRECTED")
    text_mm(fig, H, 3, 4, "Fig. 1 | Every model's held-out score, by target, input and model", fontsize=T7, fontweight="bold")
    views, models = list(E.VIEWS), list(E.MODELS)
    VS = {"core": "Waveform + depth", "context": "+ event context", "filters": "+ seven filters", "before_after": "+ before/after power",
          "events_all": "Every event feature", "mouse": "Per-mouse tables", "everything": "Everything", "nuisance": "Nuisance only"}
    MS_ = {"linear": "Linear", "lasso": "Lasso", "forest": "Forest", "boosting": "Boosting", "mlp": "Small net", "deepsets": "Deep sets",
           "attention": "Attention"}
    pos = [(30, 14), (85, 14), (140, 14), (30, 80), (85, 80)]
    for k, (t, title) in enumerate(TARGETS):
        x0, y0 = pos[k]
        M = np.full((len(views), len(models)), np.nan)
        Pm = np.zeros_like(M, bool)
        task = None
        for (tt, v, m), r in ctx.res.items():
            if tt != t:
                continue
            task = r["task"]
            M[views.index(v), models.index(m)] = r["score"]["main"]
            Pm[views.index(v), models.index(m)] = bool(r.get("passes"))
        letter(fig, H, x0 - (27 if x0 == 30 else 4), y0 - 1, "abcde"[k])
        text_mm(fig, H, x0, y0 + 0.5, "%s (%s)" % (title, SCORE[task]), fontsize=T5 + 0.3, fontweight="bold")
        ax = ax_mm(fig, H, x0, y0 + 4, 30, 38)
        lo, hi = (-0.5, 1.0) if task == "regression" else (0.0, 1.0)
        im = ax.imshow(M, cmap="RdBu_r", vmin=lo, vmax=hi, aspect="auto")
        mid = 0.25 if task == "regression" else 0.5
        for i in range(len(views)):
            for j in range(len(models)):
                if np.isfinite(M[i, j]):
                    ax.text(j, i, ("%.2f" % M[i, j]).replace("-", "−"), ha="center", va="center", fontsize=3.4,
                            color="white" if abs(M[i, j] - mid) > 0.33 else INK)
                    if Pm[i, j]:
                        ax.add_patch(Rectangle((j - 0.47, i - 0.47), 0.94, 0.94, fill=False, ec=INK, lw=0.9))
                else:
                    ax.text(j, i, "—", ha="center", va="center", fontsize=3.6, color=MUTE)
        ax.set_xticks(range(len(models)))
        ax.set_xticklabels([MS_[m] for m in models], fontsize=4.0, rotation=55, ha="right", rotation_mode="anchor")
        ax.set_yticks(range(len(views)))
        ax.set_yticklabels([VS[v] for v in views] if x0 == 30 else [""] * len(views), fontsize=4.2)
        ax.tick_params(length=0, pad=1.2)
        for s_ in ax.spines.values():
            s_.set_visible(False)
        cax = ax_mm(fig, H, x0 + 31.2, y0 + 4, 1.3, 38)
        cb = fig.colorbar(im, cax=cax)
        cb.ax.tick_params(labelsize=3.8, length=1.5, width=0.4, pad=1)
        cb.outline.set_linewidth(0.4)
        cb.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: ("%.1f" % v).replace("-", "−")))
    notes = ["Every square is one model (column) on one input view (row),", "scored only on mice it never saw.",
             "Boxed: reached the bar (AUC 0.80; Spearman ρ 0.70 for", "knockout percentage).", "Bottom row: nuisance-only inputs (where the dentate sat",
             "on the probe, year, event count, recording length).", "—: the set networks need events; these views have none.",
             "With one mouse held out, a model that learned nothing", "scores below 0.5, so 0.5 is not the chance line."]
    for i, ln in enumerate(notes):
        text_mm(fig, H, 132, 86 + i * 3.4, ln, fontsize=4.6, color=MUTE)
    pdf.savefig(fig)
    fig.savefig(os.path.join(OUT, "Fig1_overview.png"), dpi=300)
    plt.close(fig)


def main(only=None):
    ctx = Ctx()
    with PdfPages(os.path.join(OUT, "Room2_figures.pdf")) as pdf:
        overview(pdf, ctx)
        for k, (t, title) in enumerate(TARGETS, 2):
            if only and t not in only:
                continue
            models, params, base = main_figure(pdf, ctx, t, title, k)
            extended_figure(pdf, ctx, t, title, k, params)
            legends_page(pdf, t, title, k, models, params, base, ctx)
            print(t, [(r["view"], r["model"], round(r["score"]["main"], 2)) for r in models], [d["item"] for d in params], flush=True)
    print("saved", OUT)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
