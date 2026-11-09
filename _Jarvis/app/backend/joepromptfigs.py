"""Tab 14, Joe Prompt: the figures (Nature format, Early and Late), each
request's PDF and CSV, and joeprompt.json (Shahriar, 2026-11-06).

    build(progress)   every request (joepromptrun), drawn and written into
                      joeprompt/Aim 2 follow-up/, plus joeprompt.json
"""
import csv
import io
import json
import os
import re
import time

import numpy as np

from . import evenmore as E
from . import finalstage as FS
from . import joeprompt as JP
from . import joepromptrun as R

W1, W2 = 89.0, 183.0                     # Nature's single and double column, mm
MM = 1 / 25.4
OKABE = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442", "#000000")
EARLY, LATE = "#56B4E9", "#0072B2"
GREY = "#8C8C8C"


def _plt():
    from . import joefigs
    return joefigs._plt()


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")


def _save(fig, stem):
    """PDF (vector, to use) and PNG (300 dpi, the page's preview)."""
    pdf = JP.out_dir(stem + ".pdf")
    png = JP.out_dir(stem + ".png")
    for path, kw in ((pdf, {}), (png, {"dpi": 300})):
        tmp = path + ".part" + os.path.splitext(path)[1]
        fig.savefig(tmp, **kw)
        os.replace(tmp, path)
    _plt().close(fig)
    return {"pdf": os.path.basename(pdf), "png": os.path.basename(png)}


def _fig(w_mm, h_mm):
    plt = _plt()
    return plt.figure(figsize=(w_mm * MM, h_mm * MM))


def forest(ax, labels, rows, log=True, ref=None, xlabel="", legend=True):
    """Rows of [(est, lo, hi, significant)] per series, one row of the axes
    per label; series side by side."""
    plt = _plt()
    k = len(rows)
    ref = (1.0 if log else 0.0) if ref is None else ref
    ax.axvline(ref, color=GREY, lw=0.5, zorder=0)
    for si, (name, col, vals) in enumerate(rows):
        off = (si - (k - 1) / 2) * (0.7 / max(k, 1))
        for i, v in enumerate(vals):
            if not v or v[0] is None or not np.isfinite(v[0]):
                continue
            e, lo, hi, s = v
            y = i + off
            ax.plot([lo, hi], [y, y], color=col, lw=0.8, solid_capstyle="round")
            ax.plot([e], [y], marker="o", ms=3.2, color=col, mfc=col if s else "white", mew=0.8, ls="none",
                    label=name if i == 0 or (legend and i == next(j for j, z in enumerate(vals) if z and z[0] is not None)) else None)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_ylim(len(labels) - 0.5, -0.5)
    if log:
        ax.set_xscale("log")
        from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter
        lo_, hi_ = ax.get_xlim()
        ticks = [t for t in (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100) if lo_ <= t <= hi_]
        ax.xaxis.set_major_locator(FixedLocator(ticks))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: ("%g" % v)))
        ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel(xlabel)
    if legend and k > 1:
        h, l_ = ax.get_legend_handles_labels()
        seen = {}
        for hh, ll in zip(h, l_):
            seen.setdefault(ll, hh)
        # below the axis, never over the data
        ax.legend(list(seen.values()), list(seen.keys()), frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2),
                  ncol=min(k, 4), handlelength=1.0, columnspacing=1.2)
    plt.setp(ax.get_yticklabels(), fontsize=5.5)


def _v(g, sigkey="q"):
    if not g or g.get("est") is None:
        return None
    s = g.get(sigkey) if g.get(sigkey) is not None else g.get("p")
    return (g["est"], g.get("lo"), g.get("hi"), s is not None and s < 0.05)


def letters(fig, skip_narrow=0.06):
    """Bold lowercase panel letters (a, b, ...) at the top-left of each
    panel's drawn extent, tick labels included, as the publication figures
    have them; nothing for a one-panel figure. Narrow axes (a colour bar)
    and insets are skipped."""
    axes = [ax for ax in fig.axes if ax.get_position().width >= skip_narrow and ax.get_label() != "<colorbar>"]
    if len(axes) < 2:
        return
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    W, H = fig.bbox.width, fig.bbox.height
    # reading order: panels side by side (overlapping in height) left to right, then the next row down
    rows = sorted(axes, key=lambda ax: (-round((ax.get_position().y0 + ax.get_position().y1) * 1.5), ax.get_position().x0))
    for i, ax in enumerate(rows):
        bb = ax.get_tightbbox(rend)
        x = max(0.004, bb.x0 / W - 0.012)
        y = min(0.99, bb.y1 / H + 0.012)                       # above the panel's title, never on it
        fig.text(x, y, "abcdefghij"[i], fontsize=8, fontweight="bold", va="bottom", ha="left")


PAIRS = list(E.PAIR_SAY)


# --------------------------------------------------------------------------
# The figures
# --------------------------------------------------------------------------
def fig_a1(Rq, X):
    D = Rq["data"]
    fig = _fig(W2, 88)
    gs = fig.add_gridspec(1, 2, left=0.1, right=0.98, top=0.86, bottom=0.26, wspace=0.12)
    for bi, band in enumerate(R.BANDS):
        ax = fig.add_subplot(gs[0, bi])
        by = {x["pair"]: x for x in D[band] if "error" not in x}
        series = [("|Sxy|²", OKABE[0], "lxy"), ("Sxx", OKABE[1], "lxx"), ("Syy", OKABE[2], "lyy"), ("Coherence", "#000000", "coh")]
        forest(ax, PAIRS if bi == 0 else [""] * len(PAIRS), [(n, c, [_v((by.get(p) or {}).get(k)) for p in range(len(PAIRS))]) for n, c, k in series],
               log=True, xlabel="Late/Early (log scale)", legend=bi == 1)
        ax.set_title(band.capitalize(), loc="left", fontsize=6.5)
    letters(fig)
    return _save(fig, "A1_fig1_coherence_decomposition_NoJ3J4")


def fig_a3(Rq, X):
    D = Rq["data"]
    fig = _fig(W2, 70)
    gs = fig.add_gridspec(1, 4, left=0.07, right=0.98, top=0.84, bottom=0.18, wspace=0.55)
    for bi, band in enumerate(R.BANDS):
        nd = D[band]["node"].get("gee") or {}
        if "nodes" not in nd:
            continue
        ax = fig.add_subplot(gs[0, 2 * bi])
        forest(ax, [z["region"] for z in nd["nodes"]], [("Region", OKABE[0], [(z["ratio"], z["lo"], z["hi"], z["lo"] > 1 or z["hi"] < 1) for z in nd["nodes"]])],
               log=True, xlabel="Region's Late/Early", legend=False)
        ax.set_title("%s: node model" % band.capitalize(), loc="left", fontsize=6.5)
        ax2 = fig.add_subplot(gs[0, 2 * bi + 1])
        res = nd["resid"]
        ax2.barh(range(len(res)), [z["resid"] for z in res], color=OKABE[1], height=0.6)
        ax2.axvline(0, color=GREY, lw=0.5)
        ax2.set_yticks(range(len(res)))
        ax2.set_yticklabels([z["pair"] for z in res], fontsize=5)
        ax2.set_ylim(len(res) - 0.5, -0.5)
        ax2.set_xlabel("Pair beyond its regions (log)")
        ax2.set_title("Full vs node: p = %s" % ("%.3f" % nd["p"]).lstrip("0"), loc="left", fontsize=6)
    letters(fig)
    return _save(fig, "A3_fig1_node_model_NoJ3J4")


def fig_a4(Rq, X):
    D = Rq["data"]["bands"]
    fig = _fig(W2, 86)
    gs = fig.add_gridspec(1, 2, left=0.1, right=0.98, top=0.86, bottom=0.26, wspace=0.12)
    for bi, band in enumerate(R.BANDS):
        ax = fig.add_subplot(gs[0, bi])
        by = {x["pair"]: x for x in D[band] if "error" not in x}
        forest(ax, PAIRS if bi == 0 else [""] * len(PAIRS),
               [("Pooled", OKABE[0], [_v((by.get(p) or {}).get("po")) for p in range(len(PAIRS))]),
                ("Mean of trials", OKABE[1], [_v((by.get(p) or {}).get("tm")) for p in range(len(PAIRS))])],
               log=True, xlabel="Late/Early (log scale)", legend=bi == 1)
        ax.set_title(band.capitalize(), loc="left", fontsize=6.5)
    letters(fig)
    return _save(fig, "A4_fig1_pooled_vs_trial_mean_NoJ3J4")


def fig_a5(Rq, X):
    D = Rq["data"]["coh"]
    fig = _fig(W2, 82)
    gs = fig.add_gridspec(1, 3, left=0.1, right=0.92, top=0.86, bottom=0.17, wspace=0.12, width_ratios=[14, 30, 1.2])
    from matplotlib.colors import TwoSlopeNorm
    norm = TwoSlopeNorm(vmin=-2.0, vcenter=0.0, vmax=2.0)
    im = None
    for bi, band in enumerate(R.BANDS):
        ax = fig.add_subplot(gs[0, bi])
        hz = [f for f, _m in E.bins_of(band)]
        M = np.full((len(PAIRS), len(hz)), np.nan)
        S = np.zeros_like(M, dtype=bool)
        for x in D[band]:
            for fi, b in enumerate(x["bins"]):
                if b["s"].get("est"):
                    M[x["pair"], fi] = np.log2(b["s"]["est"])
                    S[x["pair"], fi] = R.sig(b["s"], "q")
        im = ax.imshow(M, aspect="auto", cmap="RdBu_r", norm=norm, interpolation="nearest")
        yy, xx = np.nonzero(S)
        ax.plot(xx, yy, marker="s", ms=2.2, mfc="none", mec="#000000", mew=0.5, ls="none")
        step = 2 if band == "theta" else 5
        ax.set_xticks(range(0, len(hz), step))
        ax.set_xticklabels(["%g" % round(hz[i], 1) for i in range(0, len(hz), step)])
        ax.set_yticks(range(len(PAIRS)))
        ax.set_yticklabels(PAIRS if bi == 0 else [])
        ax.set_xlabel("Hz")
        ax.set_title(band.capitalize(), loc="left", fontsize=6.5)
    cax = fig.add_subplot(gs[0, 2])
    cb = fig.colorbar(im, cax=cax)
    cb.set_ticks([-2, -1, 0, 1, 2])
    cb.set_ticklabels(["×¼", "×½", "×1", "×2", "×4"])
    cb.set_label("Late/Early")
    letters(fig)
    return _save(fig, "A5_fig1_per_bin_coherence_NoJ3J4")


def fig_c1(Rq, X):
    D = Rq["data"]
    fig = _fig(W2, 88)
    gs = fig.add_gridspec(1, 2, left=0.1, right=0.98, top=0.86, bottom=0.26, wspace=0.12)
    cols = {"base10": GREY, "cue1": OKABE[0], "cue2": OKABE[1]}
    for bi, band in enumerate(R.BANDS):
        ax = fig.add_subplot(gs[0, bi])
        by = {x["pair"]: x for x in D[band]}
        forest(ax, PAIRS if bi == 0 else [""] * len(PAIRS),
               [(E.PERIOD_SAY[w], cols[w], [_v((by.get(p) or {}).get("by_period", {}).get(w)) for p in range(len(PAIRS))]) for w in E.PERIODS],
               log=True, xlabel="Late/Early (log scale)", legend=bi == 1)
        ax.set_title(band.capitalize(), loc="left", fontsize=6.5)
    letters(fig)
    return _save(fig, "C1_fig1_coherence_by_period_NoJ3J4")


def fig_b8(Rq, X):
    D = Rq["data"]["coh"]
    fig = _fig(W2, 88)
    gs = fig.add_gridspec(1, 2, left=0.1, right=0.98, top=0.86, bottom=0.26, wspace=0.12)
    for bi, band in enumerate(R.BANDS):
        ax = fig.add_subplot(gs[0, bi])
        by = {x["pair"]: x for x in D[band]}
        forest(ax, PAIRS if bi == 0 else [""] * len(PAIRS),
               [("Ipsilateral", OKABE[0], [_v((by.get(p) or {}).get("ipsi")) for p in range(len(PAIRS))]),
                ("Contralateral", OKABE[1], [_v((by.get(p) or {}).get("contra")) for p in range(len(PAIRS))])],
               log=True, xlabel="Late/Early (log scale)", legend=bi == 1)
        ax.set_title(band.capitalize(), loc="left", fontsize=6.5)
    letters(fig)
    return _save(fig, "B8_fig1_ipsilateral_vs_contralateral_NoJ3J4")


def fig_b10(Rq, X):
    D = Rq["data"]
    fig = _fig(W1, 80)
    ax = fig.add_axes([0.24, 0.26, 0.72, 0.6])
    forest(ax, PAIRS, [("Low gamma", OKABE[0], [_v(g) for g in D["low"]["coh"]]), ("High gamma", OKABE[1], [_v(g) for g in D["high"]["coh"]])],
           log=True, xlabel="Late/Early (log scale)")
    letters(fig)
    return _save(fig, "B10_fig1_low_vs_high_gamma_NoJ3J4")


def fig_b9(Rq, X):
    D = Rq["data"]["coh"]
    fig = _fig(W2, 92)
    gs = fig.add_gridspec(1, 2, left=0.1, right=0.98, top=0.86, bottom=0.26, wspace=0.12)
    cols = (GREY, OKABE[0], OKABE[4], OKABE[1])
    for bi, band in enumerate(R.BANDS):
        ax = fig.add_subplot(gs[0, bi])
        series = []
        for wi, (_k, _s, _e, say) in enumerate(JP.SHORT):
            by = {g["pair"]: g for g in D if g["band"] == band and g["window"] == say}
            series.append((say, cols[wi], [_v(by.get(p)) for p in range(len(PAIRS))]))
        forest(ax, PAIRS if bi == 0 else [""] * len(PAIRS), series, log=True, xlabel="Late/Early (log scale)", legend=bi == 1)
        ax.set_title(band.capitalize(), loc="left", fontsize=6.5)
    letters(fig)
    return _save(fig, "B9_fig1_two_second_windows_NoJ3J4")


def fig_c2(Rq, X):
    D = Rq["data"]
    fig = _fig(W2, 72)
    gs = fig.add_gridspec(1, 2, left=0.14, right=0.98, top=0.82, bottom=0.3, wspace=0.5)
    labs = ["%s (%s)" % (E.PAIR_SAY[x["pair"]], x["band"]) for x in D]
    ax = fig.add_subplot(gs[0, 0])
    forest(ax, labs, [("Forwards", OKABE[0], [_v(x["dir"], "p") for x in D]), ("Time-reversed", OKABE[1], [_v(x["rdir"], "p") for x in D])],
           log=True, xlabel="First → second over second → first")
    ax.set_title("Direction, forwards and reversed", loc="left", fontsize=6.5)
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.barh(range(len(D)), [100 * x["share"] for x in D], color=OKABE[2], height=0.6)
    ax2.axvline(0, color=GREY, lw=0.5)
    ax2.set_yticks(range(len(D)))
    ax2.set_yticklabels(labs, fontsize=5)
    ax2.set_ylim(len(D) - 0.5, -0.5)
    ax2.set_xlabel("Zero-lag share of the band's interdependence (%)\n(frequency domain; below 0 = none)")
    ax2.set_title("Zero-lag share", loc="left", fontsize=6.5)
    letters(fig)
    return _save(fig, "C2_fig1_direction_and_zero_lag_NoJ3J4")


def fig_c4(Rq, X):
    D = Rq["data"]
    fig = _fig(W2, 88)
    gs = fig.add_gridspec(1, 2, left=0.1, right=0.98, top=0.86, bottom=0.26, wspace=0.12)
    for bi, band in enumerate(R.BANDS):
        ax = fig.add_subplot(gs[0, bi])
        forest(ax, PAIRS if bi == 0 else [""] * len(PAIRS), [("Session × Pairing", OKABE[3], [_v(g) for g in D[band]])], log=False,
               xlabel="Δ similarity, paired − unpaired (Fisher z)", legend=False)
        ax.set_title(band.capitalize(), loc="left", fontsize=6.5)
    letters(fig)
    return _save(fig, "C4_fig1_paired_vs_unpaired_NoJ3J4")


def fig_b1(Rq, X):
    D = Rq["data"]
    fig = _fig(W2, 70)
    gs = fig.add_gridspec(1, 4, left=0.07, right=0.98, top=0.82, bottom=0.2, wspace=0.35)
    regs = [FS.REGION_SAY[r] for r in FS.REGIONS]
    for i, (key, say, unit) in enumerate(FS.FOOOF_PARAMS):
        ax = fig.add_subplot(gs[0, i])
        forest(ax, regs if i == 0 else [""] * len(regs), [(say, OKABE[i], [_v(x["session"]) for x in D[key]])], log=False,
               xlabel="Late − Early" + (" (%s)" % unit if unit else ""), legend=False)
        ax.set_title(say, loc="left", fontsize=6)
    letters(fig)
    return _save(fig, "B1_fig1_fooof_estimates_NoJ3J4")


def fig_b2(Rq, X):
    D = Rq["data"]["session"]
    fig = _fig(W1, 70)
    ax = fig.add_axes([0.2, 0.3, 0.75, 0.54])
    regs = [FS.REGION_SAY[r] for r in FS.REGIONS]
    forest(ax, regs, [(band.capitalize(), OKABE[i], [_v(next(s for s in D if s["band"] == band and s["region"] == r)) for r in FS.REGIONS])
                      for i, band in enumerate(R.BANDS)], log=False, xlabel="Late − Early (dB)")
    letters(fig)
    return _save(fig, "B2_fig1_power_by_region_NoJ3J4")


def fig_b11(Rq, X):
    """How the data were cleaned. a, what artifact removal left of each
    rat's sessions (region-windows: kept their first wire, used the next,
    omitted), with the share of 1-s pieces omitted beside each bar; b, the
    steps every wire went through, the two that remove artifacts marked."""
    from matplotlib.patches import FancyBboxPatch, Circle
    rows = {(x["rat"], x["day"]): x for x in Rq["data"]}
    rats = sorted({r for r, _d in rows})
    fig = _fig(W2, 96)
    ax = fig.add_axes([0.1, 0.12, 0.33, 0.72])
    cols = (("First wire kept", "#0072B2"), ("Next wire used", "#E69F00"), ("Omitted (no wire left)", "#D55E00"))
    y, ylab, grp, pos = [], [], [], 0.0
    shares, lost = [], []
    for r in rats:
        first = pos
        for d in E.DAYS:
            x = rows.get((r, d))
            if not x:
                continue
            n = max(1, x["windows"])
            shares.append((100.0 * (x["windows"] - x["replaced"] - x["omitted"]) / n, 100.0 * x["replaced"] / n, 100.0 * x["omitted"] / n))
            lost.append(100.0 * x["segments_lost"] / max(1, x["segments"]))
            y.append(pos)
            ylab.append(R.DAY_SAY(d))
            pos += 1.0
        grp.append(("J%d" % r, (first + pos - 1) / 2))
        pos += 0.55
    left = np.zeros(len(y))
    for k, (name, col) in enumerate(cols):
        v = np.array([s_[k] for s_ in shares])
        ax.barh(y, v, left=left, height=0.8, color=col, edgecolor="white", linewidth=0.5, label=name)
        left += v
    for yy, l_ in zip(y, lost):
        ax.text(103, yy, "%d%%" % round(l_), va="center", ha="left", fontsize=5.5, color="#333333")
    ax.text(103, -1.1, "Pieces\nomitted", va="bottom", ha="left", fontsize=5.5, color="#333333")
    ax.set_xlim(0, 100)
    ax.set_ylim(pos - 0.55 + 0.1, -0.7)
    ax.set_yticks(y)
    ax.set_yticklabels(ylab, fontsize=5.5)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Region-windows (%)")
    for name, gy in grp:
        ax.text(-0.17, gy, name, transform=ax.get_yaxis_transform(), va="center", ha="right", fontsize=6, fontweight="bold")
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(-0.02, 1.0), ncol=3, fontsize=5.5, handlelength=1.0, columnspacing=1.0,
              handletextpad=0.4)
    # b: the steps
    ax2 = fig.add_axes([0.58, 0.04, 0.4, 0.84])
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.axis("off")
    steps = (("Recorded at 32 kHz; converted to µV", False),
             ("Down-sampled to 1 kHz (zero-phase anti-alias filter)", False),
             ("Inspected by hand: a wire with an artifact\nis excluded from that 10-s window", True),
             ("Saturation rule: within 0.5% of the limit for\n≥ 16 samples, over ≥ 0.5% of the window or 50 ms", True),
             ("Each region and side keeps its lowest-numbered\nwire left; none left: omitted from that window", True),
             ("59–61 Hz removed (2nd-order Butterworth band-stop)", False),
             ("1.024-s Hann pieces, half overlapping, pooled\nover every trial of a session", False))
    n = len(steps)
    gap = 1.0 / n
    hb = gap * 0.74
    for i, (txt, art) in enumerate(steps):
        yc = 1 - (i + 0.5) * gap
        ax2.add_patch(FancyBboxPatch((0.1, yc - hb / 2), 0.88, hb, boxstyle="round,pad=0,rounding_size=0.02",
                                     fc="#FBE9DF" if art else "#F2F2F2", ec="#D55E00" if art else "#BBBBBB", lw=0.6))
        ax2.add_patch(Circle((0.045, yc), 0.032, fc="#333333", ec="none", transform=ax2.transData))
        ax2.text(0.045, yc, str(i + 1), ha="center", va="center", fontsize=5.5, color="white", fontweight="bold")
        ax2.text(0.13, yc, txt, ha="left", va="center", fontsize=5.5, color="#111111", linespacing=1.25)
        if i < n - 1:
            ax2.annotate("", xy=(0.54, yc - gap + hb / 2 + 0.003), xytext=(0.54, yc - hb / 2 - 0.003),
                         arrowprops=dict(arrowstyle="-|>", lw=0.5, color="#777777", mutation_scale=5, shrinkA=0, shrinkB=0))
    ax2.text(0.1, 1.035, "Artifact removal (shaded orange): steps 3–5", fontsize=5.5, color="#D55E00", ha="left", va="bottom")
    letters(fig)
    return _save(fig, "B11_fig1_how_the_data_were_cleaned_NoJ3J4")


# --------------------------------------------------------------------------
# Volume conduction, in plain English (2026-11-06: "write in english bro"):
# four figures that each make one point, and the words under each
# --------------------------------------------------------------------------
BLUE, ORANGE, GREEN, LIGHT = "#0072B2", "#D55E00", "#009E73", "#56B4E9"
FS_T, FS_L, FS_S = 6.5, 6.0, 5.5          # title, label, small: the house sizes (joefigs._plt)


def _tidy(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=FS_S)


def fig_vc_idea(Rq, X):
    """1. What the two kinds of shared signal look like."""
    fig = _fig(W2, 52)
    t = np.linspace(0, 1, 600)
    for i, (title, lag, col, note) in enumerate((
            ("One signal on both wires (volume conduction)", 0.0, ORANGE,
             "Peaks line up: zero delay"),
            ("One region driving the other (communication)", 0.06, BLUE,
             "Region 2 follows a few ms later: a delay"))):
        ax = fig.add_axes([0.04 + i * 0.5, 0.06, 0.42, 0.78])
        a = np.sin(2 * np.pi * 5 * t)
        b = np.sin(2 * np.pi * 5 * (t - lag))
        ax.plot(t, a + 1.4, color="#333333", lw=1.1)
        ax.plot(t, b - 1.4, color=col, lw=1.1)
        for k in range(5):
            pk = 0.05 + k * 0.2
            ax.axvline(pk, color="#BBBBBB", lw=0.5, ls=":", zorder=0)
            if lag:
                ax.annotate("", xy=(pk + lag, -0.25), xytext=(pk, -0.25), arrowprops=dict(arrowstyle="->", lw=0.7, color=col))
        ax.text(-0.02, 1.4, "Region 1", ha="right", va="center", fontsize=FS_S)
        ax.text(-0.02, -1.4, "Region 2", ha="right", va="center", fontsize=FS_S)
        ax.set_xlim(-0.16, 1.0)
        ax.set_ylim(-3.7, 2.7)
        ax.axis("off")
        ax.set_title(title, loc="left", fontsize=FS_T)
        ax.text(0.42, -3.6, note, ha="center", va="bottom", fontsize=FS_L, color=col)
    letters(fig)
    return _save(fig, "A2_fig1_what_volume_conduction_looks_like")


def _phase_shares(X):
    out = {}
    for band in R.BANDS:
        m = R._bins(*R.BAND_LIM[band])
        kept, bad = [], []
        for (r, d), (a, _m) in X.em_all.items():
            for p in range(len(PAIRS)):
                ph = R._phase(a, "pair", p, m)
                if r in JP.DROP and (r == 3 or d == "Precon1"):
                    bad += ph
                elif r not in JP.DROP:
                    kept += ph
        out[band] = {"kept": R.near_zero(kept), "bad": R.near_zero(bad), "n_kept": len(kept), "n_bad": len(bad)}
    return out


def fig_vc_timing(Rq, X):
    """2. How often two wires' signals line up at zero delay."""
    S = Rq.setdefault("vc", {})["timing"] = _phase_shares(X)
    fig = _fig(W1 + 20, 74)
    ax = fig.add_axes([0.16, 0.14, 0.8, 0.8])
    _tidy(ax)
    x = np.arange(len(R.BANDS))
    w = 0.36
    kept = [100 * S[b]["kept"] for b in R.BANDS]
    bad = [100 * S[b]["bad"] for b in R.BANDS]
    b1 = ax.bar(x - w / 2, kept, w, color=BLUE, label="Rats analysed (J6–J11)")
    b2 = ax.bar(x + w / 2, bad, w, color=ORANGE, label="Recordings left out (J3, J4 Early)")
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.5, "%d%%" % round(b.get_height()), ha="center", fontsize=FS_S)
    ax.axhline(100 * 20 / 180, color="#666666", lw=0.6, ls="--")
    ax.text(len(R.BANDS) - 0.45, 100 * 20 / 180 + 1.5, "Random timing: 11%", ha="right", fontsize=FS_S, color="#444444")
    ax.set_xticks(x)
    ax.set_xticklabels(["Theta (5–12 Hz)", "Gamma (30–90 Hz)"], fontsize=FS_L)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Wire pairs in step at zero delay (%)", fontsize=FS_L)
    ax.legend(frameon=False, fontsize=FS_S, loc="upper left", handlelength=1.0)
    return _save(fig, "A2_fig2_how_often_signals_line_up")


def fig_vc_changes(Rq, X):
    """3. The six coherence changes, and whether the lag-only measure moved too."""
    D = Rq["data"]
    rows = []
    for band in R.BANDS:
        for x in D[band]:
            if "error" not in x and R.sig(x["coh"], "q"):
                rows.append((band, x))
    fig = _fig(W2, 30 + 11 * len(rows))
    H = 30 + 11 * len(rows)
    top, bot = 1 - 14 / H, 13 / H
    axc = fig.add_axes([0.18, bot, 0.3, top - bot])
    axw = fig.add_axes([0.54, bot, 0.3, top - bot])
    labels = []
    for i, (band, x) in enumerate(rows):
        c, w = x["coh"], x["wpli"]
        rob = (w.get("robust") or {}).get("robust") and ((w["est"] < 0) == (c["est"] < 1))
        axc.plot([c["lo"], c["hi"]], [i, i], color="#333333", lw=1.0)
        axc.plot([c["est"]], [i], "o", ms=5, color="#333333")
        wc = GREEN if rob else ("#999999" if not R.sig(w) else ORANGE)
        axw.plot([w["lo"], w["hi"]], [i, i], color=wc, lw=1.0)
        axw.plot([w["est"]], [i], "o", ms=5, color=wc, mfc=wc if R.sig(w) else "white", mew=1.0)
        labels.append("%s (%s)" % (E.PAIR_SAY[x["pair"]], band))
        verdict = "Backed up" if rob else ("Same way, not reliable" if R.sig(w) and ((w["est"] < 0) == (c["est"] < 1)) else "No lagged change")
        axw.text(1.04, i, verdict, transform=axw.get_yaxis_transform(), va="center", fontsize=FS_S, color=wc if wc != "#999999" else "#555555")
    for ax in (axc, axw):
        _tidy(ax)
        ax.set_ylim(len(rows) - 0.5, -0.6)
        ax.set_yticks(range(len(rows)))
    axc.set_yticklabels(labels, fontsize=FS_L)
    axw.set_yticklabels([])
    axc.axvline(1, color="#888888", lw=0.6)
    axw.axvline(0, color="#888888", lw=0.6)
    axc.set_xscale("log")
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter
    axc.xaxis.set_major_locator(FixedLocator([0.1, 0.2, 0.5, 1, 2, 5]))
    axc.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: "×%g" % v))
    axc.xaxis.set_minor_formatter(NullFormatter())
    axc.set_xlabel("Coherence, Late vs Early\n(×0.5 = halved, ×2 = doubled)", fontsize=FS_S)
    axw.set_xlabel("Lag-only coupling (wPLI), Late − Early\n(below 0 = went down, above 0 = went up)", fontsize=FS_S)
    axc.set_title("What coherence says", loc="left", fontsize=FS_T)
    axw.set_title("What the lag-only measure says", loc="left", fontsize=FS_T)
    letters(fig)
    return _save(fig, "A2_fig3_did_the_lagged_part_change_NoJ3J4")


def fig_vc_every(Rq, X):
    """4. Every recording: total coupling against its lagged part."""
    from . import conduction
    lag = conduction.lag_table(X.em_all)
    fig = _fig(W1 + 20, 92)
    ax = fig.add_axes([0.17, 0.15, 0.79, 0.8])
    _tidy(ax)
    for x in lag:
        bad = x["rat"] in JP.DROP and (x["rat"] == 3 or x["day"] == "Precon1")
        if bad:
            ax.plot(x["coh"], x["icoh"], "s", ms=6, color=ORANGE)
            ax.annotate("J%d %s" % (x["rat"], R.DAY_SAY(x["day"])), (x["coh"], x["icoh"]), xytext=(5, -2), textcoords="offset points", fontsize=FS_S, color=ORANGE)
        else:
            ax.plot(x["coh"], x["icoh"], "o", ms=5, color=BLUE, alpha=0.85)
    ax.set_xlim(0, max(x["coh"] for x in lag) * 1.18)
    ax.set_ylim(0, max(x["icoh"] for x in lag) * 1.3)
    ax.set_xlabel("Total coupling at gamma (coherence)", fontsize=FS_L)
    ax.set_ylabel("Lagged part only\n(imaginary coherence)", fontsize=FS_L)
    from matplotlib.lines import Line2D
    ax.legend([Line2D([], [], marker="o", color=BLUE, ls="none", ms=5), Line2D([], [], marker="s", color=ORANGE, ls="none", ms=6)],
              ["Rats analysed: each recording (J6–J11, Early and Late)", "Left out: one signal on every wire"], frameon=False, fontsize=FS_S, loc="upper left")
    letters(fig)
    return _save(fig, "A2_fig4_why_J3_and_J4_were_left_out")


def vc_story(recs, X):
    """The words of the Volume conduction part: what it is, why it matters,
    each check with its figure, how to read it and what it shows, a row per
    coherence change and the bottom line. Every number from the run."""
    A2r, B8r, C2r = recs["A2"], recs["B8"], recs["C2"]
    T = A2r.get("vc", {}).get("timing") or _phase_shares(X)
    from . import conduction
    lagt = conduction.lag_table(X.em_all)
    j3l = next((x["coh"] for x in lagt if x["rat"] == 3 and x["day"] == "Precon4"), None)
    typ = float(np.median([x["coh"] for x in lagt if x["rat"] not in JP.DROP])) if lagt else None
    figs = {f["id"]: f["id"] for f in A2r["figures"]}           # the page finds each by its id among A2's figures
    ch = []
    for band in R.BANDS:
        for x in A2r["data"][band]:
            if "error" not in x and R.sig(x["coh"], "q"):
                ch.append((band, x))
    b8 = {(b, x["pair"]): x for b in R.BANDS for x in B8r["data"]["coh"][b]}
    pct = lambda v: "%d%%" % round(100 * v)   # noqa: E731
    word = lambda e: ("fell by %d%%" % round(100 * (1 - e))) if e < 1 else ("about doubled" if 1.8 <= e <= 2.3 else "rose by %d%%" % round(100 * (e - 1)))   # noqa: E731
    rows, nconf, nhemi = [], 0, 0
    for band, x in ch:
        c, w = x["coh"], x["wpli"]
        same = (w["est"] < 0) == (c["est"] < 1)
        rob = bool((w.get("robust") or {}).get("robust")) and same
        con = (b8.get((band, x["pair"])) or {}).get("contra") or {}
        hemi = R.sig(con, "q") and ((con["est"] < 1) == (c["est"] < 1))
        nconf += rob
        nhemi += hemi
        lagged = ("Yes: it %s too, reliably" % ("fell" if w["est"] < 0 else "rose")) if rob else \
            ("Same direction, but not reliable (fails without J%d)" % w["robust"]["worst_rat"]) if R.sig(w) and same and w.get("robust") else \
            "No clear change"
        rows.append(["%s (%s)" % (E.PAIR_SAY[x["pair"]], band), "%s (×%s)" % (word(c["est"]), R.num(c["est"])), lagged,
                     "Yes" if hemi else "No", "Backed up" if rob else ("Partly backed up" if hemi or (R.sig(w) and same) else "Not backed up")])
    share = {(x["pair"], x["band"]): x["share"] for x in C2r.get("data") or []}
    big = sorted(((E.PAIR_SAY[p], b, s) for (p, b), s in share.items()), key=lambda z: -z[2])[:2]
    conf = [r_[0].replace(" (", " ").rstrip(")") for r_ in rows if r_[4] == "Backed up"]
    return {
        "title": "Volume conduction, in plain English",
        "what": [
            "The brain conducts electricity. A strong signal in one place spreads through the tissue and reaches electrodes some distance "
            "away instantly. A reference wire does the same: whatever it picks up appears on every electrode. Either way, two electrodes can "
            "look \"coupled\" only because they are recording the same signal, not because the two regions are talking. That is volume conduction.",
            "Coherence, the main measure here, can't tell the difference. It rises whenever two signals keep a steady timing relationship, and "
            "\"at exactly the same moment\" is a steady relationship. So we need checks that can tell them apart.",
            "The checks all use timing. A signal spreading through tissue arrives everywhere at the same instant (zero delay). A signal "
            "travelling between regions takes a few milliseconds, so one region's rhythm runs slightly ahead of the other's (a delay)."],
        "checks": [
            {"title": "1. The idea", "fig": figs.get("A2_fig1"),
             "read": "Top line in each panel: region 1's rhythm. Bottom line: region 2's. The dotted lines mark region 1's peaks.",
             "shows": "On the left the peaks line up exactly: that is what one signal picked up by two wires looks like. On the right region 2's "
                      "peaks come a little later: that is what real communication looks like. Coherence counts both. The \"lag-only\" "
                      "measures (wPLI and imaginary coherence) ignore the left kind and count only the right kind."},
            {"title": "2. The recordings with the problem were left out", "fig": figs.get("A2_fig4"),
             "read": "Each dot is one recording (one rat on one day). Further right means more total coupling between regions; higher up "
                     "means more of it has a delay (the part volume conduction cannot make).",
             "shows": "Three recordings (orange squares: J3 on both days, J4 Early) sit far to the right: much more total coupling than "
                      "any rat analysed, between every region and even across hemispheres, without a matching rise in the delayed part. J3 "
                      "Late has %s times the coupling of a typical recording but a delayed part like theirs. That is one signal on every "
                      "wire, most likely the reference. These recordings were left out of everything in this tab. The six rats analysed "
                      "(blue) sit together at low coupling." % ("%.0f" % (j3l / typ) if j3l and typ else "many")},
            {"title": "3. In the rats analysed, most coupling has a delay", "fig": figs.get("A2_fig2"),
             "read": "For every pair of wires, we measured whether the two signals line up at zero delay. The bars show the share that do. "
                     "The dashed line is what you would get if the timing were random.",
             "shows": "In the six rats analysed, %s of wire pairs line up at zero delay in theta and %s in gamma: more than random (11%%), "
                      "so some zero-delay signal is there, but most coupling has a delay. In the recordings that were left out, %s did in gamma."
                      % (pct(T["theta"]["kept"]), pct(T["gamma"]["kept"]), pct(T["gamma"]["bad"]))},
            {"title": "4. Did the lag-only measure change along with coherence?", "fig": figs.get("A2_fig3"),
             "read": "One row per coherence change found (Early vs Late). Left: how much coherence changed (×0.5 means it halved). Right: how "
                     "the lag-only measure (wPLI) changed; 0 means no change. On the right, a hollow grey dot means no change; a filled "
                     "orange dot moved the same way as coherence (p < .05) but did not hold up (not after correcting for the ten pairs, or "
                     "not without one rat); a filled green dot holds after correction, without any one rat, and in the mixed model.",
             "shows": "%s of the %d coherence changes %s backed up by the lag-only measure (%s). For the others the lag-only measure does "
                      "not change reliably, so we cannot show those changes are in the delayed part of the signal."
                      % ({1: "One", 2: "Two", 3: "Three"}.get(nconf, str(nconf)), len(rows), "is" if nconf == 1 else "are", ", ".join(conf) or "none")}],
        "table": {"title": "Each coherence change, checked", "head": ["Pair (band)", "Coherence, Early to Late", "Did the lag-only measure change too?",
                                                                      "Does it hold between the two hemispheres alone?", "Overall"],
                  "rows": rows, "bold": [r_[4] == "Backed up" for r_ in rows],
                  "note": "Between the two hemispheres alone: only wire pairs that cross the midline (left–right), where volume conduction is "
                          "weakest because it fades with distance (request B8)."},
        "bottom": [
            "What we can say: the recordings with a shared-signal problem were found and left out, and in the six rats analysed most coupling "
            "has a delay, which volume conduction cannot produce.",
            "What we can't say yet: only %s of the %d coherence changes (%s) is backed up by the lag-only measure. %d hold between the two "
            "hemispheres alone, which makes local volume conduction less likely for them. For the rest, part of the change could sit in the "
            "zero-delay part of the signal." % (nconf, len(rows), ", ".join(conf) or "none", nhemi),
            "Two cautions. With six rats the lag-only measures are noisy, so \"not backed up\" is not the same as \"caused by volume "
            "conduction\". And genuine brain synchrony at zero delay also exists; the lag-only measures throw it away too.",
            "Related: in the Granger analysis, the zero-delay share of the coupling is largest for %s." % " and ".join("%s %s (%s)" % (p, b, pct(s)) for p, b, s in big),
            "Not tested: J8, J9 and J10 were recorded against a different reference on the two days. Both references sat in the cerebellum, "
            "so it was treated as no change."]}


FIGS = {"A1": [fig_a1], "A2": [fig_vc_idea, fig_vc_timing, fig_vc_changes, fig_vc_every], "A3": [fig_a3], "A4": [fig_a4], "A5": [fig_a5], "C1": [fig_c1],
        "B1": [fig_b1], "B2": [fig_b2], "B8": [fig_b8], "B9": [fig_b9], "B10": [fig_b10], "B11": [fig_b11], "C2": [fig_c2], "C4": [fig_c4]}
CAPTIONS = {
    "A1_fig1": "Coherence decomposed into its cross-spectrum and the two regions' power. Each pair's Late/Early ratio (95% CI) of |Sxy|², Sxx, "
               "Syy and coherence, J6–J11, cue pair; filled where q < .05 (BH across the 10 pairs within a term).",
    "A2_fig1": "What volume conduction looks like. a, one signal picked up by two wires: the peaks line up at zero delay. b, one region driving another: the second region's peaks come a few milliseconds later. Coherence counts both; the lag-only measures (wPLI, imaginary coherence) count only b.",
    "A2_fig2": "The share of wire pairs whose two signals line up at zero delay (within 10° of 0° or 180° in the pooled cross-spectrum), in the six rats analysed and in the three recordings left out for one signal on every wire. Dashed line: what random timing would give (11%).",
    "A2_fig3": "Each coherence change found between Early and Late (left, Late/Early ratio with 95% CI) beside the change in debiased wPLI, which ignores zero-delay signal (right, Late − Early with 95% CI). Right: hollow grey, p ≥ .05; filled orange, p < .05 but not robust (q ≥ .05 across the 10 pairs, or fails leaving out one rat); filled green, q < .05, holds leaving out each rat and in the mixed model.",
    "A2_fig4": "Every recording's gamma coherence on the 10-s baseline (total coupling) against its imaginary part (the delayed part). The three recordings left out combine very high coherence with little delayed coupling: one signal on every wire.",
    "A3_fig1": "The node model: each region's Late/Early ratio when a pair's change is the sum of its two regions', and each pair's residual "
               "beyond that. The p above each residual panel tests the full Session × Pair model against the node model (5 df, GEE).",
    "A4_fig1": "Pooled coherence against the mean of each trial's own coherence, Late/Early (95% CI); filled where q < .05.",
    "A5_fig1": "Late/Early coherence in every frequency bin and pair (log2 scale); outlined bins have q < .05 across the band's bins.",
    "C1_fig1": "Late/Early coherence in the baseline, cue 1 and cue 2 windows (95% CI); filled where q < .05 across the 10 pairs within a period.",
    "B1_fig1": "Late − Early in each FOOOF parameter and region, averaged over periods (95% CI); filled where q < .05 across the 5 regions.",
    "B2_fig1": "Late − Early band power in each region (dB, 95% CI), averaged over periods; filled where q < .05 across the 10 models.",
    "B8_fig1": "Late/Early coherence from ipsilateral and contralateral wire pairs separately, wire pairs valid in both sessions only (95% CI); "
               "filled where q < .05.",
    "B9_fig1": "Late/Early coherence in 2-s windows (exploratory): the last 2 s of baseline, the first and last 2 s of cue 1 and the first 2 s "
               "of cue 2 (95% CI); filled where q < .05 across the 10 pairs.",
    "B10_fig1": "Late/Early gamma coherence in low (30–56 Hz) and high (64–90 Hz) gamma (95% CI); filled where q < .05.",
    "B11_fig1": "a, The share of region-windows (one region and hemisphere in one 10-s window of one trial) that kept their first wire, used "
                "the next one, or were omitted after artifact removal, per rat and session. b, The processing steps.",
    "C2_fig1": "Left, Granger causality first → second over second → first, sessions pooled, forwards and on time-reversed signals (95% CI). "
               "Right, the zero-lag share of total interdependence in the band.",
    "C4_fig1": "Session × Pairing in the similarity (Fisher z) of the coherence spectra of cue 1 and cue 2: paired against unpaired; 95% CI.",
}


# --------------------------------------------------------------------------
# The PDF and CSV of each request
# --------------------------------------------------------------------------
CSS = """
* { font-family: sans-serif; font-size: 9pt; line-height: 1.32; color: #111; }
h1 { font-size: 13pt; margin: 0 0 2pt 0; }
h2 { font-size: 10.5pt; margin: 12pt 0 3pt 0; }
p { margin: 0 0 4pt 0; }
.src { color: #555; font-size: 8.5pt; }
li { margin: 0 0 3pt 0; }
table { border-collapse: collapse; margin: 4pt 0 2pt 0; }
th { font-weight: bold; text-align: left; border-bottom: 0.8px solid #000; padding: 1.5pt 6pt 1.5pt 0; font-size: 7.5pt; }
td { border-bottom: 0.4px solid #bbb; padding: 1.5pt 6pt 1.5pt 0; font-size: 7.5pt; }
tr.s td { font-weight: bold; }
.foot { color: #444; font-size: 7.5pt; }
"""


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def html(r):
    out = ["<h1>%s. %s</h1>" % (_esc(r["id"]), _esc(r["name"])),
           '<p class="src">Aim 2 follow-up · %s · %s · %s · status: %s · run %s</p>' % (_esc(r["priority"]), _esc(r["rats"]), _esc(r["n"]),
                                                                                      _esc(r["status"]), _esc(r.get("date", "")))]
    out.append("<p><b>Decides.</b> %s</p>" % _esc(r["decides"]))
    if r.get("ran"):
        out.append("<p><b>What was run.</b> %s</p>" % _esc(r["ran"]))
    if r.get("source"):
        out.append('<p class="src">From: %s</p>' % _esc(r["source"]))
    if r["summary"]:
        out.append("<h2>Summary</h2><ul>%s</ul>" % "".join("<li>%s</li>" % _esc(s) for s in r["summary"]))
    if r["robust"]:
        out.append("<h2>Robustness</h2><ul>%s</ul>" % "".join("<li>%s</li>" % _esc(s) for s in r["robust"]))
    if r["reading"]:
        out.append("<h2>Reading (from the run sheet)</h2>%s" % "".join("<p>%s</p>" % _esc(s) for s in r["reading"]))
    if r["notes"]:
        out.append("<h2>Notes</h2><ul>%s</ul>" % "".join("<li>%s</li>" % _esc(s) for s in r["notes"]))
    if r.get("methods"):
        out.append("<h2>Methods text</h2>%s" % "".join("<p>%s</p>" % _esc(s) for s in r["methods"]))
    for t in r["tables"]:
        out.append("<h2>%s</h2>" % _esc(t["title"]))
        out.append("<table><tr>%s</tr>%s</table>" % ("".join("<th>%s</th>" % _esc(h) for h in t["head"]),
                                                     "".join("<tr%s>%s</tr>" % (' class="s"' if b else "", "".join("<td>%s</td>" % _esc(c) for c in row))
                                                             for row, b in zip(t["rows"], t["bold"]))))
        if t.get("note"):
            out.append('<p class="foot">%s</p>' % _esc(t["note"]))
    out.append('<p class="foot">Conventions: GEE with the rat as the cluster (exchangeable); Gamma with a log link for coherence and Granger, '
               "normal for dB power, FOOOF parameters, phase measures and log terms; robust (Mancl–DeRouen) errors for tests of 1–2 df, "
               "model-based above; Benjamini–Hochberg with its family named; significant = q &lt; .05, nominal = p &lt; .05 with q ≥ .05, "
               "robust = also holds leaving out each rat and in an LMM with a random intercept for rat. Early = Precon 1, Late = Precon 4.</p>")
    return "".join(out)


def write_pdf(r, path, figs):
    import fitz
    story = fitz.Story(html=html(r), user_css=CSS)
    buf = io.BytesIO()
    w = fitz.DocumentWriter(buf)
    page = fitz.paper_rect("letter-l")
    where = page + (40, 36, -40, -36)
    more = 1
    while more:
        dev = w.begin_page(page)
        more, _ = story.place(where)
        story.draw(dev)
        w.end_page()
    w.close()
    d = fitz.open("pdf", buf.getvalue())
    for f in figs:
        fp_ = JP.out_dir(f["pdf"])
        if os.path.isfile(fp_):
            src = fitz.open(fp_)
            d.insert_pdf(src)
            src.close()
    d.set_metadata({"title": "%s. %s" % (r["id"], r["name"]), "author": "Jarvis (tab 14, Joe Prompt)", "subject": "Aim 2 follow-up"})
    d.subset_fonts()
    d.save(path + ".tmp", garbage=4, deflate=True)
    d.close()
    os.replace(path + ".tmp", path)


def write_csv(r, path):
    rows = r["csv"]
    if not rows:
        return False
    keys = []
    for x in rows:
        for k in x:
            if k not in keys:
                keys.append(k)
    with open(path + ".tmp", "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=keys)
        wr.writeheader()
        for x in rows:
            wr.writerow({k: ("" if v is None else v) for k, v in x.items()})
    os.replace(path + ".tmp", path)
    return True


def _clean(x):
    """JSON-safe: numbers as floats or None, no numpy, no frames."""
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items() if not str(k).startswith("_")}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return float(x) if np.isfinite(x) else None
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.ndarray):
        return _clean(x.tolist())
    return x


def build(progress=None):
    say = progress or (lambda s: None)
    os.makedirs(JP.out_dir(), exist_ok=True)
    X = R.Ctx(say)
    date = time.strftime("%Y-%m-%d")
    recs = {}
    for rid in R.ORDER:
        say("running %s" % rid)
        fn = R.RUN[rid]
        try:
            r = fn(X, say) if rid == "A5" else fn(X)
        except Exception as exc:                             # noqa: BLE001
            r = R.rec(rid, status="Failed", summary=["Failed: %s: %s" % (type(exc).__name__, exc)])
        r["date"] = date
        recs[rid] = r
    for rid, r in recs.items():
        figs = []
        for fn in FIGS.get(rid, []):
            say("drawing %s" % fn.__name__)
            try:
                f = fn(r, X)
            except Exception as exc:                         # noqa: BLE001
                r["notes"].append("A figure could not be drawn (%s: %s)." % (type(exc).__name__, exc))
                continue
            key = "_".join(f["pdf"].split("_")[:2])
            f["caption"] = CAPTIONS.get(key, "")
            f["id"] = key
            figs.append(f)
        r["figures"] = figs
        stem = "%s_%s_%s" % (rid, slug(r["name"]), JP.TAG)
        pdf = JP.out_dir(stem + ".pdf")
        say("writing %s" % os.path.basename(pdf))
        write_pdf(r, pdf, figs)
        r["files"] = {"pdf": os.path.basename(pdf)}
        if write_csv(r, JP.out_dir(stem + ".csv")):
            r["files"]["csv"] = stem + ".csv"
        r["line"] = R.line(rid, r, X)
    story = vc_story(recs, X)
    C = None
    try:
        with open(os.path.join(os.path.dirname(JP._root()), "joepub", "conduction.json"), encoding="utf-8") as fh:
            C = json.load(fh)
    except OSError:
        pass
    out = {"ok": True, "schema": JP.SCHEMA, "made": time.strftime("%Y-%m-%dT%H:%M:%S"), "rats": JP.RATS_SAY, "tag": JP.TAG,
           "title": "Aim 2 follow-up: Joe's final round",
           "say": "Every request of Joe's run sheet (Aim 2 Jarvis Run Sheet, Nov 6, 2026), on J6–J11 (PER n = 5), Early (Precon 1) against "
                  "Late (Precon 4). Each request has its PDF (tables, then figures) and a CSV of the per-rat values behind its tests.",
           "parts": [{"key": k, "say": s} for k, s in JP.PARTS], "statuses": list(JP.STATUS), "priorities": ["P1", "P2", "P3"],
           "order": list(R.ORDER), "confirmations": R.confirmations(X), "vc_story": story, "conduction": C if C and C.get("ok") else None,
           "requests": [_clean({k: v for k, v in recs[rid].items() if k not in ("data", "csv")}) for rid in [x[0] for x in JP.REQUESTS]]}
    tmp = JP._root("joeprompt.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(_clean(out), fh, ensure_ascii=False)
    os.replace(tmp, JP._root("joeprompt.json"))
    return out


def result():
    p = JP._root("joeprompt.json")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


if __name__ == "__main__":
    import sys
    from . import monolith as MO
    MO.configure(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "GUI_logs"))
    t0 = time.time()
    o = build(lambda s: print(s, flush=True))
    print("built %d requests in %.0f s" % (len(o["requests"]), time.time() - t0))
    for r in o["requests"]:
        print(r["id"], r["status"], r.get("files"), len(r.get("figures") or []))
