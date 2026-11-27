"""Quality check: the DS1/DS2 classification of every recording, one page
each (a PNG per recording and one PDF with a page per recording)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import deep_figs as G  # noqa: E402
from deep_figs import D2, DS, plt, recs, full, W, INK, MUTE, HAIR, C_DS1, C_DS2, CSD_CMAP, FS, FS_S  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from scipy.interpolate import PchipInterpolator  # noqa: E402

OUT = r"c:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\quality_check_round4"
os.makedirs(OUT, exist_ok=True)
H = 195.0
NAMES = {"bite": "Bite line", "pca": "PCA, k-means", "pca_gap": "PCA + gap", "delta": "Delta", "delta_mid": "Delta middle",
         "pca_gmm_line": "PCA, mixture (line)", "pca_gmm_curve": "PCA, mixture (curve)",
         "opt_line": "PCA, index-optimised (line)", "opt_curve": "PCA, index-optimised (curve)"}
import pickle  # noqa: E402
PCA2 = pickle.load(open(os.path.join(HERE, "deep_pca2_v6.pkl"), "rb"))
OPT = pickle.load(open(os.path.join(HERE, "deep_opt_v6.pkl"), "rb"))
for d_ in recs:
    for k_, v_ in (PCA2.get(d_["gid"], {}).get("fits") or {}).items():
        if "err" not in v_ and v_.get("si") is not None:
            d_["splits"][k_] = dict(v_, x=PCA2[d_["gid"]]["X"][:, 0], why="not scored for DS3")
ROWS = {"": "both sinks", "_top": "upper sink", "_bottom": "lower sink"}


def word(si):
    return "separable" if si >= 0.45 else ("partial" if si >= 0.2 else "not separable")


def page(d):
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    ax_mm = lambda x, y, w, h: G.ax_mm(fig, H, x, y, w, h)
    m, e = D2.best_si(d) if d["n"] >= 10 else (None, None)
    head = "%s    %s%s    %d events    %.0f min" % (d["lab"], "Control" if d["g"] == "CTL" else "PTEN knockout",
                                                     "" if d["g"] == "CTL" else " %.1f%%" % d["ko"], d["n"], d["dur"] / 60.0)
    fig.text(4 / W, 1 - 5 / H, head, fontsize=9, fontweight="bold", ha="left", va="center", color=INK)
    fig.add_artist(Rectangle((4 / W, 1 - 9.2 / H), 175 / W, 0.9 / H, color=G.col_of(d), lw=0, transform=fig.transFigure))
    if e is None:
        fig.text(4 / W, 1 - 14 / H, "Too few events to classify.", fontsize=FS, ha="left", va="center", color=MUTE)
    else:
        base = m.replace("_top", "").replace("_bottom", "")
        row = ROWS[m[len(base):]]
        fig.text(4 / W, 1 - 14 / H, "Best classifier: %s, %s.   Separation index %.2f: %s.   DS1 %d events (%.0f%%), DS2 %d events." % (
            NAMES[base], row, e["si"], word(e["si"]), e["n1"], 100.0 * e["n1"] / d["n"], e["n2"]), fontsize=FS, ha="left", va="center")
    # a  mean DS
    G.letter(fig, H, 2, 19, "a")
    ax = ax_mm(13, 27, 34, 76)
    G.draw_ds(ax, d, half=18, t_lim=40.0, lw=0.3, every=1)
    ax.set_xlabel("Time from DS peak (ms)", fontsize=FS)
    ax.set_ylabel("Depth from midpoint between blade sinks (µm)", fontsize=FS)
    ax.set_title("Mean DS: CSD and LFP", fontsize=FS, loc="left", pad=3)
    if e is None:
        return fig
    ty = e["types"]
    xs = np.asarray(e["x"], float)
    # b  every event, sorted
    G.letter(fig, H, 54, 19, "b")
    o = np.lexsort((np.where(np.isfinite(xs), xs, np.nanmax(xs)), ty))
    P = d["prof"][o]
    v = np.percentile(np.abs(P), 99)
    dep = (np.arange(P.shape[1]) - (P.shape[1] - 1) / 2.0) * 50.0
    ax = ax_mm(65, 27, 52, 76)
    ax.imshow(P.T, aspect="auto", cmap=CSD_CMAP, vmin=-v, vmax=v, interpolation="nearest", extent=[0, P.shape[0], dep[-1] + 25, dep[0] - 25])
    n1 = int((ty == 1).sum())
    ax.axvline(n1, color=INK, lw=0.6)
    span = dep[-1] - dep[0] + 50
    for a, b, c in ((0, n1, C_DS1), (n1, P.shape[0], C_DS2)):
        ax.add_patch(Rectangle((a, dep[0] - 25 - 0.03 * span), b - a, 0.02 * span, color=c, clip_on=False, lw=0))
    ax.set_xticks([0, P.shape[0]])
    ax.set_xlabel("Events, sorted by classifier score", fontsize=FS)
    ax.set_ylabel("Depth in the analysed band (µm)", fontsize=FS)
    ax.set_title("CSD at the DS peak, every event", fontsize=FS, loc="left", pad=8)
    # c  class means
    G.letter(fig, H, 122, 19, "c")
    ax = ax_mm(127, 27, 22, 76)
    for c, col in ((1, C_DS1), (2, C_DS2)):
        mu = d["prof"][ty == c].mean(axis=0)
        se = d["prof"][ty == c].std(axis=0) / np.sqrt(max((ty == c).sum(), 1))
        ax.fill_betweenx(dep, mu - se, mu + se, color=col, alpha=0.25, lw=0)
        ax.plot(mu, dep, color=col, lw=0.9)
    ax.axvline(0, color=HAIR, lw=0.5, zorder=0)
    ax.set_ylim(dep[-1] + 25, dep[0] - 25)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xticks([0])
    ax.set_xlabel("Mean CSD ± s.e.m.\\n(sink − , source +)".replace("\\n", chr(10)), fontsize=FS)
    ax.set_title("DS1 and DS2 means", fontsize=FS, loc="left", pad=8)
    ax.text(0.02, 0.995, "DS1", transform=ax.transAxes, color=C_DS1, fontsize=FS_S, fontweight="bold", va="top")
    ax.text(0.98, 0.995, "DS2", transform=ax.transAxes, color=C_DS2, fontsize=FS_S, fontweight="bold", va="top", ha="right")
    # d  both types' sinks on one scale
    G.letter(fig, H, 153, 19, "d")
    I = G.families(d)
    ax = ax_mm(156, 27, 19, 76)
    G.draw_sinks(ax, I, first=False)
    ax.set_title("Sink amplitude", fontsize=FS, loc="left", pad=8)
    lines = []
    for b, nm in ((0, "upper"), (1, "lower")):
        if I["cen"][2][b] is None:
            lines.append("%s: DS2 sink under its" % nm + chr(10) + "noise floor (no centroid)")
        elif I["out"][b] is None:
            lines.append("%s: DS1 sink %.1f× its floor" % (nm, I["clear"][b]) + chr(10) + "(under it: no centroid)")
        else:
            lines.append("%s: DS1 sink %.1f× floor," % (nm, I["clear"][b]) + chr(10) + "centroid %d µm %s to DS2" % (abs(I["out"][b]), "distal" if I["out"][b] >= 0 else "proximal"))
    ax.set_xlabel(chr(10).join(lines), fontsize=FS_S - 0.3)
    # e  the classifier's axis
    G.letter(fig, H, 2, 118, "e")
    ax = ax_mm(12, 126, 27, 32)
    ok = np.isfinite(xs)
    bins = np.linspace(np.nanmin(xs), np.nanmax(xs), 46) if np.nanmax(xs) > np.nanmin(xs) else 10
    ax.hist([xs[ok & (ty == 1)], xs[ok & (ty == 2)]], bins=bins, stacked=True, color=[C_DS1, C_DS2], lw=0)
    ax.set_xlabel("Score: %s," % NAMES[base] + chr(10) + row, fontsize=FS)
    ax.set_ylabel("Events", fontsize=FS)
    ax.set_title("Classifier scores", fontsize=FS, loc="left", pad=3)
    if (~ok).any():
        ax.text(0.99, 0.97, "%d events without a score" % int((~ok).sum()), transform=ax.transAxes, fontsize=FS_S, ha="right", va="top", color=MUTE)
    # f  all fifteen classifiers
    G.letter(fig, H, 43, 118, "f")
    ax = ax_mm(79, 126, 27, 32)
    for lo, hi, c in ((0, 0.2, "#F3F3F3"), (0.2, 0.45, "#E9E9E9"), (0.45, 1.0, "#DEDEDE")):
        ax.axvspan(lo, hi, color=c, lw=0, zorder=0)
    bases = list(NAMES)
    for i, b in enumerate(bases):
        for k, (suf, mk) in enumerate((("", "o"), ("_top", "^"), ("_bottom", "v"))):
            if suf and (b.startswith("pca_gmm") or b.startswith("opt_")):
                continue
            ee = d["splits"].get(b + suf, {}) if not b.startswith("opt_") else (OPT.get(d["gid"], {}).get("fits") or {}).get(b, {"err": 1})
            if b.startswith("opt_"):
                mk = "*"
            if "err" in ee or ee.get("si") is None:
                continue
            valid = min(ee["n1"], ee["n2"]) >= max(5, 0.05 * d["n"])
            best = (b + suf) == m
            ax.scatter([ee["si"]], [i + (k - 1) * 0.24], s=22 if best else 12, marker=mk, color=INK if valid else "white",
                       edgecolor="#B5361F" if best else INK, linewidth=1.0 if best else 0.5, zorder=3)
    ax.set_yticks(range(len(bases)))
    ax.set_yticklabels([NAMES[b] for b in bases], fontsize=FS_S)
    ax.set_ylim(len(bases) - 0.5, -0.5)
    ax.set_xlim(-0.02, 1)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Separation index", fontsize=FS)
    ax.set_xticks([0, 0.5, 1])
    ax.set_title("17 classifiers + 2 optimised", fontsize=FS, loc="left", pad=3)
    # g  the PCA plane
    G.letter(fig, H, 109, 118, "g")
    ax = ax_mm(115, 126, 29, 32)
    Q = PCA2.get(d["gid"])
    X = Q["X"]
    ax.scatter(X[:, 0], X[:, 1], s=2.2, c=np.where(ty == 1, C_DS1, C_DS2), linewidth=0, alpha=0.8, rasterized=True)
    used = m in ("pca", "pca_gmm_line", "pca_gmm_curve")
    ax.axvline(Q["km_cut"], color="#B5361F" if m == "pca" else MUTE, lw=1.4 if m == "pca" else 0.7, ls=(0, (3, 2)))
    for key, ls in (("pca_gmm_line", "-"), ("pca_gmm_curve", (0, (1, 1.2)))):
        ft = Q["fits"].get(key) or {}
        if "err" not in ft and ft.get("P") is not None:
            ax.contour(ft["gx"], ft["gy"], ft["P"], levels=[0.5], colors=["#B5361F" if m == key else INK], linewidths=1.4 if m == key else 0.8, linestyles=[ls])
    ax.set_xlabel("PC1", fontsize=FS)
    ax.set_ylabel("PC2", fontsize=FS)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Conventional", fontsize=FS, loc="left", pad=9)
    if used:
        why = "USED: the red boundary"
    elif m.startswith("pca"):
        why = "NOT USED: other axes"
    else:
        why = "NOT USED: %s was" % NAMES[base]
    ax.text(0.0, 1.015, why, transform=ax.transAxes, fontsize=FS_S, fontweight="bold", ha="left", va="bottom",
            color="#B5361F" if used else MUTE)
    st_ = ["%s %.0f%%" % (nm, 100 * Q["fits"][k]["stable"]) for k, nm in (("pca_gmm_line", "line"), ("pca_gmm_curve", "curve"))
           if k in Q["fits"] and "err" not in Q["fits"][k] and Q["fits"][k].get("stable") is not None]
    notes = [
        "d: mean sink ± s.e.m. of each type on one scale, at the depths of c. Dashed lines: the noise floor of each mean (99th percentile of the "
        "mean's |CSD| more than 30 ms from the DS peak).",
        "    Ticks at the right: sink centroid above the floor, where the sink clears it.",
        "f: ●  both sinks   ▲  upper sink   ▼  lower sink. Red ring: the best classifier. Open marker: one type holds under 5% of events, so the "
        "classifier is not eligible.",
        "g: PC1 and PC2 of the events, coloured by the best classifier. Dashed: k-means cut on PC1. Solid: two-Gaussian mixture, straight "
        "boundary. Dotted: mixture, curved boundary. Red and thick: the boundary used.",
        "h: the same plane, coloured by the curve chosen to maximise the separation index (each type 5% of events or more). Solid: optimised "
        "line. Dotted: optimised curve. Black rings: events whose type differs from g.",
        "    Stars in f: the two optimised boundaries; they are shown for comparison and are not eligible as the best classifier. Held out: fitted "
        "on a random half of the events, scored on the other half (mean of 5).",
        ("    Events keeping their type when the mixture is refitted on 40 bootstrap resamples: " + ", ".join(st_) + "." if st_ else "")]
    # h  the other way round: boundaries chosen for the index
    G.letter(fig, H, 147, 118, "h")
    ax = ax_mm(152, 126, 28, 32)
    O = (OPT.get(d["gid"], {}).get("fits") or {})
    oc = O.get("opt_curve") or {}
    PURPLE = "#6A3D9A"
    if "types" in oc:
        to = oc["types"]
        if np.mean(to != ty) > 0.5:
            to = 3 - to     # the same names as g, so the colours compare
        ax.scatter(X[:, 0], X[:, 1], s=2.2, c=np.where(to == 1, C_DS1, C_DS2), linewidth=0, alpha=0.8, rasterized=True)
        diff = to != ty
        ax.scatter(X[diff, 0], X[diff, 1], s=7, facecolor="none", edgecolor=INK, linewidth=0.35, rasterized=True)
        for key, ls in (("opt_line", "-"), ("opt_curve", (0, (1, 1.2)))):
            ft = O.get(key) or {}
            if "F" in ft:
                ax.contour(ft["gx"], ft["gy"], ft["F"], levels=[0.0], colors=[PURPLE], linewidths=1.1, linestyles=[ls])
        ax.set_xlim(X[:, 0].min(), X[:, 0].max())
        ax.set_ylim(X[:, 1].min(), X[:, 1].max())
        ho = "held out %.2f" % oc["heldout"] if oc.get("heldout") is not None else "not held out"
        ax.text(0.0, 1.015, "index %.2f to %.2f (%s)" % (e["si"], oc["si"], ho), transform=ax.transAxes, fontsize=FS_S - 0.3,
                fontweight="bold", ha="left", va="bottom", color=PURPLE)
        ax.set_xlabel("PC1" + chr(10) + "%d events (%.0f%%) change type" % (int(diff.sum()), 100.0 * diff.mean()), fontsize=FS_S)
    else:
        ax.text(0.5, 0.5, "no boundary leaves" + chr(10) + "5% of events a side", transform=ax.transAxes, ha="center", va="center",
                fontsize=FS_S, color=MUTE)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Optimised for the index", fontsize=FS, loc="left", pad=9)
    for i_, t_ in enumerate(notes):
        fig.text(4 / W, 1 - (171.0 + 3.4 * i_) / H, t_, fontsize=FS_S - 0.5, ha="left", va="center", color=MUTE)
    return fig


order = [d for d in recs if d["g"] == "CTL"] + sorted([d for d in recs if d["g"] == "PTEN"], key=lambda d: d["ko"])
with PdfPages(os.path.join(OUT, "DS1_DS2_classification_all_recordings.pdf")) as pdf:
    for i, d in enumerate(order):
        fig = page(d)
        pdf.savefig(fig)
        fig.savefig(os.path.join(OUT, "%02d_%s_%s.png" % (i + 1, d["lab"], "control" if d["g"] == "CTL" else "PTEN")), dpi=250)
        plt.close(fig)
        print(d["lab"], flush=True)
print("saved to", OUT)
