"""The averaged documents: the dentate spike normalized across recordings.
  round10/Averaged_CTL.pdf          control
  round10/Averaged_PTEN.pdf         PTEN: all, IED-, IED+
  round10/Averaged_comparison.pdf   groups laid over each other, with a
                                    cluster permutation test of each curve
  python make_averaged.py
"""
import json
import os

import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

import dsdata
import house as Hs
import normcurves as N
from house import plt, ax_mm, text_mm, letter, INK, MUTE, HAIR, C_DS1, C_DS2, CSD_CMAP, FS, FS_S, W

OUT = os.path.join(os.path.dirname(dsdata.HERE), "round10")
os.makedirs(OUT, exist_ok=True)
recs = [r for r in dsdata.load("v6") if r.ok]
NAMES = {"bite": "Bite line", "pca": "PCA, k-means", "pca_gap": "PCA + gap", "delta": "Delta", "delta_mid": "Delta middle",
         "pca_gmm_line": "PCA, mixture (line)", "pca_gmm_curve": "PCA, mixture (curve)"}


def clf_name(m):
    base = m.replace("_top", "").replace("_bottom", "")
    suf = m[len(base):]
    return NAMES.get(base, base) + {"": "", "_top": ", upper sink", "_bottom": ", lower sink"}[suf]


def band(ax, x, Y, col, vertical=False, lw=1.1, label=None):
    mu = np.nanmean(Y, axis=0)
    k = np.isfinite(Y).sum(axis=0)
    se = np.nanstd(Y, axis=0) / np.sqrt(np.maximum(k, 1))
    mu[k < max(2, 0.6 * Y.shape[0])] = np.nan
    if vertical:
        ax.fill_betweenx(x, mu - se, mu + se, color=col, alpha=0.22, lw=0)
        ax.plot(mu, x, color=col, lw=lw, label=label)
    else:
        ax.fill_between(x, mu - se, mu + se, color=col, alpha=0.22, lw=0)
        ax.plot(x, mu, color=col, lw=lw, label=label)
    return mu


def thin(ax, x, Y, rs, vertical=False):
    for y, r in zip(Y, rs):
        if vertical:
            ax.plot(y, x, color=Hs.col_of(r), lw=0.35, alpha=0.75)
        else:
            ax.plot(x, y, color=Hs.col_of(r), lw=0.35, alpha=0.75)


def group_page(rs, title, col, sub=""):
    H = 209.0
    fig = Hs.page(H)
    text_mm(fig, H, 4, 5, title, fontsize=9, fontweight="bold")
    fig.add_artist(plt.Rectangle((4 / W, 1 - 9.2 / H), 175 / W, 0.9 / H, color=col, lw=0, transform=fig.transFigure))
    if sub:
        text_mm(fig, H, 179, 5, sub, fontsize=FS_S, ha="right", color=MUTE)
    C = [N.curves(r) for r in rs]
    sep = [r for r in rs if r.separable()]
    # a  who is in it
    letter(fig, H, 2, 12, "a")
    text_mm(fig, H, 8, 14.5, "Recordings", fontsize=FS)
    text_mm(fig, H, 8, 19, "mouse   knockout   events   best classifier, index", fontsize=FS_S, color=MUTE)
    for i, r in enumerate(rs):
        text_mm(fig, H, 8, 23 + 3.5 * i, "%-4s" % r.lab, fontsize=FS_S, color=Hs.col_of(r), fontweight="bold")
        text_mm(fig, H, 17, 23 + 3.5 * i, ("%.0f%%" % r.ko) if r.group == "PTEN" else "control", fontsize=FS_S)
        text_mm(fig, H, 28, 23 + 3.5 * i, "%d" % r.n, fontsize=FS_S)
        text_mm(fig, H, 36, 23 + 3.5 * i, "%s, %.2f%s" % (clf_name(r.used), r.si(r.used), "  separable" if r.separable() else ""), fontsize=FS_S,
                color=INK if r.separable() else MUTE)
    text_mm(fig, H, 8, 23 + 3.5 * len(rs) + 2, "Each recording counts once, whatever its number of events.", fontsize=FS_S, color=MUTE)
    # b  the mean DS in normalized depth
    letter(fig, H, 84, 12, "b")
    img = np.nanmean(np.array([c["img_u"] for c in C]), axis=0)
    ax = ax_mm(fig, H, 96, 19, 34, 56)
    t = rs[0].t_ms
    vmax = np.nanpercentile(np.abs(img), 99.5)
    ax.imshow(img, aspect="auto", cmap=CSD_CMAP, vmin=-vmax, vmax=vmax, interpolation="bicubic", extent=[t[0], t[-1], N.GRID_U[-1], N.GRID_U[0]])
    ax.set_xlim(-30, 30)
    ax.set_yticks([0, 0.5, 1])
    ax.set_yticklabels(["upper\nblade sink", "between", "lower\nblade sink"], fontsize=FS_S)
    ax.set_xlabel("Time from DS peak (ms)", fontsize=FS)
    ax.set_title("Mean CSD, depth normalized", fontsize=FS, loc="left", pad=3)
    # c, d  depth profiles at the peak
    letter(fig, H, 134, 12, "c")
    ax = ax_mm(fig, H, 138, 19, 18, 56)
    Y = np.array([c["prof_u"] for c in C])
    thin(ax, N.GRID_U, Y, rs, True)
    band(ax, N.GRID_U, Y, INK, True)
    ax.axvline(0, color=HAIR, lw=0.5, zorder=0)
    ax.set_ylim(N.GRID_U[-1], N.GRID_U[0])
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xticks([-1, 0, 1])
    ax.set_xlabel("CSD at the peak\n(1 = main sinks)", fontsize=FS_S)
    ax.set_title("CSD", fontsize=FS, loc="left", pad=3)
    letter(fig, H, 158, 12, "d")
    ax = ax_mm(fig, H, 162, 19, 17, 56)
    Y = np.array([c["lfp_u"] for c in C])
    thin(ax, N.GRID_U, Y, rs, True)
    band(ax, N.GRID_U, Y, INK, True)
    ax.axvline(0, color=HAIR, lw=0.5, zorder=0)
    ax.set_ylim(N.GRID_U[-1], N.GRID_U[0])
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xticks([0, 1])
    ax.set_xlabel("LFP at the peak\n(1 = its largest)", fontsize=FS_S)
    ax.set_title("LFP", fontsize=FS, loc="left", pad=3)
    # e  folded, all events
    letter(fig, H, 2, 88, "e")
    ax = ax_mm(fig, H, 14, 96, 48, 40)
    Y = np.array([c["fold"] for c in C])
    thin(ax, N.GRID_V, Y, rs)
    band(ax, N.GRID_V, Y, INK)
    fold_axes(ax)
    ax.set_ylabel("CSD at the peak\n(−1 = the blade's main sink)", fontsize=FS)
    ax.set_title("All events, both blades folded onto one axis", fontsize=FS, loc="left", pad=3)
    # f  folded, DS1 and DS2 where they are separable
    letter(fig, H, 68, 88, "f")
    ax = ax_mm(fig, H, 78, 96, 48, 40)
    if sep:
        for c_, colr in ((2, C_DS2), (1, C_DS1)):
            Y = np.array([N.curves(r)["typed"]["fold"][c_] for r in sep])
            for y in Y:
                ax.plot(N.GRID_V, y, color=colr, lw=0.35, alpha=0.6)
            band(ax, N.GRID_V, Y, colr, label="DS%d" % c_)
        ax.legend(frameon=False, fontsize=FS_S, loc="lower right", handlelength=1.2)
    else:
        ax.text(0.5, 0.5, "no recording with\nseparable DS1 and DS2", transform=ax.transAxes, ha="center", va="center", fontsize=FS_S, color=MUTE)
    fold_axes(ax)
    ax.set_title("DS1 and DS2, separable recordings (n = %d)" % len(sep), fontsize=FS, loc="left", pad=3)
    ax.set_ylabel("CSD (−1 = DS2's main sink)", fontsize=FS)
    # g  where DS1's sink sits and how large it is
    letter(fig, H, 132, 88, "g")
    ax = ax_mm(fig, H, 144, 96, 35, 40)
    for r in rs:
        ty = N.curves(r)["typed"]
        if ty is None or "ratio" not in ty:
            continue
        x, y = np.nanmean(ty["ratio"]), np.nanmean(ty["amp"])
        if r.separable():
            ax.scatter([x], [y], s=16, color=Hs.col_of(r), edgecolor="white", linewidth=0.4, zorder=3)
            ax.annotate(r.lab, (x, y), xytext=(2.5, 2.5), textcoords="offset points", fontsize=FS_S - 0.5)
        else:
            ax.scatter([x], [y], s=12, facecolor="white", edgecolor=Hs.col_of(r), linewidth=0.7, zorder=2)
    ax.axvline(1, color=HAIR, lw=0.5, zorder=0)
    ax.axhline(1, color=HAIR, lw=0.5, zorder=0)
    ax.set_xlabel("DS1 sink position / DS2 sink position\n(distance from the source; 1 = same place)", fontsize=FS_S)
    ax.set_ylabel("DS1 sink size / DS2 sink size", fontsize=FS)
    ax.set_title("DS1 against DS2", fontsize=FS, loc="left", pad=3)
    ax.text(0.98, 0.97, "filled: separable\nopen: not separable", transform=ax.transAxes, fontsize=FS_S - 0.5, ha="right", va="top", color=MUTE)
    # h-k  time courses
    t = rs[0].t_ms
    for j, (key, ttl, yl) in enumerate((("tc_sink", "CSD at the main sinks", "−1 = sink at the peak"), ("tc_source", "CSD at the source", "1 = main sinks"),
                                        ("tc_lfp", "LFP at the source", "1 = its largest"))):
        letter(fig, H, 2 + j * 45, 148, "hij"[j])
        ax = ax_mm(fig, H, 13 + j * 45, 156, 33, 30)
        Y = np.array([c[key] for c in C])
        thin(ax, t, Y, rs)
        band(ax, t, Y, INK)
        ax.axhline(0, color=HAIR, lw=0.5, zorder=0)
        ax.set_xlim(-40, 40)
        ax.set_xlabel("Time from DS peak (ms)", fontsize=FS_S)
        ax.set_ylabel(yl, fontsize=FS_S)
        ax.set_title(ttl, fontsize=FS, loc="left", pad=3)
    letter(fig, H, 137, 148, "k")
    ax = ax_mm(fig, H, 148, 156, 31, 30)
    if sep:
        for c_, colr in ((2, C_DS2), (1, C_DS1)):
            Y = np.array([N.curves(r)["typed"]["tc"][c_] for r in sep])
            for y in Y:
                ax.plot(t, y, color=colr, lw=0.35, alpha=0.6)
            band(ax, t, Y, colr)
    ax.axhline(0, color=HAIR, lw=0.5, zorder=0)
    ax.set_xlim(-40, 40)
    ax.set_xlabel("Time from DS peak (ms)", fontsize=FS_S)
    ax.set_title("DS1, DS2 at the main sinks", fontsize=FS, loc="left", pad=3)
    notes = ["Depth is normalized by each recording's own landmarks, found on the mean of all its events: the main sink of the upper blade, the main sink of the lower blade, and the source between them.",
             "b-d: blade to blade, 0 at the upper main sink, 1 at the lower. e-f: within a blade, 0 at the source, 1 at the main sink, above 1 farther out; the two blades are folded and averaged.",
             "Size: CSD is divided by the recording's own main sinks, so 1 is the same in every mouse. Thin lines: one recording each (color: control slate, PTEN light to dark with % knockout).",
             "Thick line and band: mean ± s.e.m. over recordings. DS1 and DS2 come from each recording's best eligible classifier; separable = separation index 0.45 or more."]
    for i, s in enumerate(notes):
        text_mm(fig, H, 4, 197.5 + 3.0 * i, s, fontsize=FS_S - 0.6, color=MUTE)
    return fig


def fold_axes(ax):
    ax.axhline(0, color=HAIR, lw=0.5, zorder=0)
    for x in (0, 1):
        ax.axvline(x, color=HAIR, lw=0.5, zorder=0)
    ax.set_xlim(-0.5, 2.6)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["source", "main sink", "2x as far out"], fontsize=FS_S)
    ax.set_xlabel("Position in the blade, from the source outward", fontsize=FS)


def compare_page(A, B, na, nb, ca, cb, results):
    H = 150.0
    fig = Hs.page(H)
    text_mm(fig, H, 4, 5, "%s (n = %d) against %s (n = %d)" % (na, len(A), nb, len(B)), fontsize=9, fontweight="bold")
    fig.add_artist(plt.Rectangle((4 / W, 1 - 9.2 / H), 87 / W, 0.9 / H, color=ca, lw=0, transform=fig.transFigure))
    fig.add_artist(plt.Rectangle((92 / W, 1 - 9.2 / H), 87 / W, 0.9 / H, color=cb, lw=0, transform=fig.transFigure))
    t = A[0].t_ms
    specs = [("prof_u", N.GRID_U, "CSD at the peak, blade to blade", "upper sink = 0, lower sink = 1", (-0.6, 1.6)),
             ("fold", N.GRID_V, "CSD at the peak, blades folded", "source = 0, main sink = 1", (-0.5, 2.6)),
             ("lfp_u", N.GRID_U, "LFP at the peak, blade to blade", "upper sink = 0, lower sink = 1", (-0.6, 1.6)),
             ("tc_sink", t, "CSD at the main sinks in time", "ms from DS peak", (-40, 40)),
             ("tc_source", t, "CSD at the source in time", "ms from DS peak", (-40, 40)),
             ("tc_lfp", t, "LFP at the source in time", "ms from DS peak", (-40, 40))]
    for j, (key, x, ttl, xl, xlim) in enumerate(specs):
        col_, row_ = j % 3, j // 3
        letter(fig, H, 2 + col_ * 60, 14 + row_ * 62, "abcdef"[j])
        ax = ax_mm(fig, H, 14 + col_ * 60, 22 + row_ * 62, 44, 38)
        Ya = np.array([N.curves(r)[key] for r in A])
        Yb = np.array([N.curves(r)[key] for r in B])
        band(ax, x, Ya, ca, label=na)
        band(ax, x, Yb, cb, label=nb)
        ax.axhline(0, color=HAIR, lw=0.5, zorder=0)
        sel = (x >= xlim[0]) & (x <= xlim[1])
        tt, cl, pmin = N.cluster_test(Ya[:, sel], Yb[:, sel], n_perm=3000)
        xs = x[sel]
        yl = ax.get_ylim()
        for i0, i1, mass, p in cl:
            ax.axvspan(xs[i0], xs[i1], color="#F2D9A6" if p >= 0.05 else "#E9A23B", alpha=0.45, lw=0, zorder=0)
        ax.set_ylim(yl)
        ax.set_xlim(*xlim)
        ax.set_xlabel(xl, fontsize=FS_S)
        ax.set_title(ttl, fontsize=FS, loc="left", pad=3)
        best = min(cl, key=lambda c: c[3]) if cl else None
        ax.text(0.98, 0.04, "no point differs" if best is None else "largest cluster %.2f to %.2f: P = %.3f" % (xs[best[0]], xs[best[1]], best[3]),
                transform=ax.transAxes, fontsize=FS_S - 0.3, ha="right", va="bottom", color=INK if (best and best[3] < 0.05) else MUTE)
        if j == 0:
            ax.legend(frameon=False, fontsize=FS_S, loc="upper right", handlelength=1.2)
        results.append({"groups": "%s vs %s" % (nb, na), "curve": key, "what": ttl, "n_a": len(A), "n_b": len(B),
                        "clusters": [{"from": float(xs[a_]), "to": float(xs[b_]), "mass": m_, "p": p_} for a_, b_, m_, p_ in cl], "p_min": float(pmin)})
    notes = ["Mean ± s.e.m. over recordings of each group's normalized curves. Shaded: runs of points where the groups differ (Welch t beyond ±2.1).",
             "P: cluster permutation test (the largest run's summed |t| against 3,000 shuffles of the group labels); it answers 'do the curves differ anywhere', once per curve.",
             "Darker shading: cluster P under 0.05. These P values are not corrected across the six curves or across pages."]
    for i, s in enumerate(notes):
        text_mm(fig, H, 4, 140 + 3.0 * i, s, fontsize=FS_S - 0.6, color=MUTE)
    return fig


if __name__ == "__main__":
    ctl = [r for r in recs if r.group == "CTL"]
    pten = sorted([r for r in recs if r.group == "PTEN"], key=lambda r: r.ko)
    iedn, iedp = [r for r in pten if r.subgroup == "IED-"], [r for r in pten if r.subgroup == "IED+"]
    with PdfPages(os.path.join(OUT, "Averaged_CTL.pdf")) as pdf:
        fig = group_page(ctl, "Control: the averaged dentate spike (n = %d recordings)" % len(ctl), Hs.C_CTL, "m51 (5 events) left out")
        pdf.savefig(fig)
        fig.savefig(os.path.join(OUT, "Averaged_CTL.png"), dpi=200)
        plt.close(fig)
    with PdfPages(os.path.join(OUT, "Averaged_PTEN.pdf")) as pdf:
        for rs, ttl, col, tag in ((pten, "PTEN knockout: the averaged dentate spike (n = %d recordings)" % len(pten), Hs.GROUP_COL["PTEN"], "all"),
                                  (iedn, "PTEN IED−: the averaged dentate spike (n = %d recordings)" % len(iedn), Hs.C_IEDN, "IEDneg"),
                                  (iedp, "PTEN IED+: the averaged dentate spike (n = %d recordings)" % len(iedp), Hs.C_IEDP, "IEDpos")):
            fig = group_page(rs, ttl, col, "IED+ mice are also the high-knockout mice (only m7 is IED− with a high knockout)" if tag != "all" else "")
            pdf.savefig(fig)
            fig.savefig(os.path.join(OUT, "Averaged_PTEN_%s.png" % tag), dpi=200)
            plt.close(fig)
    res = []
    hi = [r for r in pten if r.ko >= 15]
    with PdfPages(os.path.join(OUT, "Averaged_comparison.pdf")) as pdf:
        for k, (A, B, na, nb, ca, cb) in enumerate(((ctl, pten, "Control", "PTEN", Hs.C_CTL, Hs.GROUP_COL["PTEN"]),
                                                    (iedn, iedp, "PTEN IED−", "PTEN IED+", Hs.C_IEDN, Hs.C_IEDP),
                                                    (ctl, iedp, "Control", "PTEN IED+", Hs.C_CTL, Hs.C_IEDP),
                                                    (ctl, iedn, "Control", "PTEN IED−", Hs.C_CTL, Hs.C_IEDN),
                                                    (ctl, hi, "Control", "PTEN, 15%+ knockout", Hs.C_CTL, Hs.KO_CMAP(0.85)))):
            fig = compare_page(A, B, na, nb, ca, cb, res)
            pdf.savefig(fig)
            fig.savefig(os.path.join(OUT, "Averaged_comparison_%d.png" % (k + 1)), dpi=200)
            plt.close(fig)
    json.dump(res, open(os.path.join(dsdata.HERE, "results", "cluster_tests.json"), "w"), indent=1)
    for r_ in sorted(res, key=lambda r_: r_["p_min"])[:8]:
        print(("%.3f  %-28s %s" % (r_["p_min"], r_["groups"], r_["what"])).encode("ascii", "replace").decode())
    print("saved to", OUT)
