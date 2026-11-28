"""The one normalized figure (2026-11-17, replacing round 10's four
averaged pages): DS1 and DS2, the DS3 events taken out, depth normalized,
averaged over recordings. round11/Averaged_DS1_DS2.pdf
  page 1 control, page 2 PTEN (all), page 3 PTEN IED-, page 4 PTEN IED+,
  page 5 the groups laid over each other (cluster permutation test, raw P).
No folded axes, no "separable" labels: every recording is drawn on its own
beside the mean, with its separation index, so the reader decides.
  python make_averaged2.py
"""
import json
import os

import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

import dsdata
import house as Hs
import normcurves as N
from house import plt, ax_mm, text_mm, INK, MUTE, HAIR, RED, C_DS1, C_DS2, FS, FS_S, W

OUT = os.path.join(os.path.dirname(dsdata.HERE), "round11")
os.makedirs(OUT, exist_ok=True)
import sys
from scipy import stats as st
NOCUT = len(sys.argv) > 1 and sys.argv[1] == "nocut"
TAG = "_no_cutoff" if NOCUT else ""
recs = [r for r in dsdata.load("v6") if r.ok]


def clf_of(r):
    """The classifier drawn: the best eligible one (each type 5%+ of events),
    or with nocut the best by index whatever the type sizes."""
    if not NOCUT:
        return r.used
    conv = [c for c in dsdata.CONVENTIONAL if r.has(c)]
    return max(conv, key=lambda c: r.si(c)) if conv else None


TU = {r.lab: N.typed_u(r, clf_of(r), min_n=1 if NOCUT else 5) for r in recs}
U = N.GRID_U
NAMES = {"bite": "Bite line", "pca": "PCA, k-means", "pca_gap": "PCA + gap", "delta": "Delta", "delta_mid": "Delta middle",
         "pca_gmm_line": "PCA mixture, line", "pca_gmm_curve": "PCA mixture, curve"}


def clf_name(m):
    base = m.replace("_top", "").replace("_bottom", "")
    return NAMES.get(base, base) + {"": "", "_top": ", upper", "_bottom": ", lower"}[m[len(base):]]


def stack(rs, c):
    Y = [TU[r.lab][c] for r in rs if TU[r.lab][c] is not None]
    return np.array(Y) if Y else np.zeros((0, U.size))


def mean_band(ax, Y, col, lw=1.6, ls="-", label=None):
    if not len(Y):
        return
    mu = np.nanmean(Y, axis=0)
    k = np.isfinite(Y).sum(axis=0)
    se = np.nanstd(Y, axis=0) / np.sqrt(np.maximum(k, 1))
    bad = k < max(2, 0.6 * Y.shape[0])
    mu[bad] = np.nan
    se[bad] = np.nan
    ax.fill_betweenx(U, mu - se, mu + se, color=col, alpha=0.2, lw=0)
    ax.plot(mu, U, color=col, lw=lw, ls=ls, label=label)


def depth_axis(ax, labels=True, src=None):
    ax.axvline(0, color=HAIR, lw=0.5, zorder=0)
    for y in (0, 1):
        ax.axhline(y, color=HAIR, lw=0.5, zorder=0)
    if src is not None:
        for s in src:
            ax.plot([1.0], [s], marker="<", color=RED, ms=3.0, transform=ax.get_yaxis_transform(), clip_on=False)
    ax.set_ylim(U[-1], U[0])
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["upper blade's\nsink" if labels else "", "lower blade's\nsink" if labels else ""], fontsize=FS_S)


EXPLAIN = ["How it is normalized.  Every recording is put on the same ruler. Depth: 0 is where that recording's average dentate spike (all its events) has its",
           "deepest sink in the upper blade, 1 is the same in the lower blade; everything between and beyond is stretched in proportion, so the blades line up",
           "whatever the probe's track. Size: CSD divided by the depth of that average sink (mean of the two blades), one number per recording, the same for",
           "DS1 and DS2, so their sizes still compare. CSD at the DS peak (±3 ms); left of 0 = sink, right = source. Red ticks: the source on the cell-layer",
           "side of each blade (mean over the recordings). DS1 and DS2: each recording's best eligible classifier, names checked against the anatomy (DS1 = the",
           "type whose sink sits farther from the cell layer), the DS3 events taken out (score within ±0.5, layers looked for past the analyzed band).",
           "Thick line and band: mean ± s.e.m. over recordings. A type with fewer than 5 events on a recording is left out of that recording's panel and the mean."]


def group_page(pdf, rs, title, col, fname):
    ncol = 3
    y_txt = max(22 + ((len(rs) + ncol - 1) // ncol) * 46 + 2, 128)
    H = y_txt + 3.2 * len(EXPLAIN) + 4
    fig = Hs.page(H)
    text_mm(fig, H, 4, 5, title + ("  ·  NO MINIMUM TYPE SIZE" if NOCUT else ""), fontsize=9, fontweight="bold")
    fig.add_artist(plt.Rectangle((4 / W, 1 - 9.2 / H), 175 / W, 0.9 / H, color=col, lw=0, transform=fig.transFigure))
    text_mm(fig, H, 179, 5, "Halo set  ·  %d recordings" % len(rs), fontsize=FS_S, ha="right", color=MUTE)
    ax = ax_mm(fig, H, 22, 20, 46, 98)
    src = [np.nanmean([TU[r.lab]["src_u"][0] for r in rs]), np.nanmean([TU[r.lab]["src_u"][-1] for r in rs])]
    for c, cc in ((2, C_DS2), (1, C_DS1)):
        Y = stack(rs, c)
        for y in Y:
            ax.plot(y, U, color=cc, lw=0.3, alpha=0.35)
        mean_band(ax, Y, cc, label="%s (%d recordings)" % ("DS1" if c == 1 else "DS2", len(Y)))
    depth_axis(ax, True, src)
    ax.set_xlabel("CSD at the DS peak\n(1 = the recording's average sink)", fontsize=FS)
    ax.set_title("DS1 and DS2 without DS3, averaged", fontsize=FS, loc="left", pad=3)
    ax.legend(frameon=False, fontsize=FS_S, loc="lower left", handlelength=1.6)
    xl = ax.get_xlim()
    # every recording
    text_mm(fig, H, 80, 15.5, "Each recording (same axes; separation index of DS1 against DS2 under its classifier, events left after DS3 is taken out)", fontsize=FS_S, color=MUTE)
    for i, r in enumerate(rs):
        cx, cy = 80 + (i % ncol) * 34, 22 + (i // ncol) * 46
        a2 = ax_mm(fig, H, cx + 3, cy + 7, 27, 33)
        t = TU[r.lab]
        for c, cc in ((2, C_DS2), (1, C_DS1)):
            if t[c] is not None:
                a2.plot(t[c], U, color=cc, lw=0.9)
        depth_axis(a2, False, t["src_u"])
        a2.tick_params(labelsize=4.5)
        a2.set_xlim(xl)
        text_mm(fig, H, cx + 3, cy + 1.2, "%s  ·  index %.2f" % (r.lab, r.si(clf_of(r))), fontsize=FS_S, fontweight="bold", color=Hs.col_of(r))
        text_mm(fig, H, cx + 3, cy + 4.2, "%s; DS1 %d, DS2 %d" % (clf_name(clf_of(r)), t["n"][1], t["n"][2]), fontsize=4.6, color=MUTE)
    y = y_txt
    ex_ = EXPLAIN if not NOCUT else EXPLAIN[:4] + [
        "side of each blade (mean over the recordings). NO MINIMUM TYPE SIZE: each recording's classifier is the one with the highest separation index, however few",
        "events its smaller type holds, and every type with at least one event is drawn and averaged. Names checked against the anatomy; DS3 events taken out.",
        "Thick line and band: mean ± s.e.m. over recordings. A type with 1–4 events is a noisy mean: read those recordings' panels with that in mind."]
    for i, s in enumerate(ex_):
        text_mm(fig, H, 4, y + 3.2 * i, s, fontsize=FS_S - 0.2, color=MUTE)
    pdf.savefig(fig)
    fig.savefig(os.path.join(OUT, "Averaged_DS1_DS2%s_%s.png" % (TAG, fname)), dpi=200)
    plt.close(fig)


def sink_pos(prof, src_u, blade):
    """Centroid (on the depth axis u) of a profile's deepest sink lobe on
    the far side of the cell-layer source of one blade."""
    if prof is None:
        return np.nan
    far = (U < src_u[0]) if blade == "upper" else (U > src_u[-1])
    y = np.where(far & np.isfinite(prof), np.maximum(-prof, 0.0), 0.0)
    if y.max() <= 0:
        return np.nan
    return N._lobe_centroid(y, U, int(np.argmax(y)))


def apart(r):
    """How far apart DS1's and DS2's sinks sit, per blade, outward positive
    (DS1 farther from the cell layer), in u units and in um."""
    t = TU[r.lab]
    out = []
    for blade, sg in (("upper", -1), ("lower", 1)):
        d = sg * (sink_pos(t[1], t["src_u"], blade) - sink_pos(t[2], t["src_u"], blade))
        out.append(d)
    out = np.array(out)
    return out, out * r.landmarks["blade_um"]


def apart_page(pdf, groups):
    """The user's question: in the overlay, IED− DS1 sits farther from DS2
    than in control and IED+. Measured per recording."""
    H = 132.0
    fig = Hs.page(H)
    Hs.stamp(fig)
    text_mm(fig, H, 4, 5, "How far apart DS1's and DS2's sinks sit (DS3 removed)%s" % (", no minimum type size" if NOCUT else ""), fontsize=9, fontweight="bold")
    text_mm(fig, H, 4, 10.5, "Per recording and blade: where DS1's sink is (center of its deepest lobe on the far side of the cell layer) minus where DS2's is, on the normalized depth; "
            "positive = DS1 farther out.", fontsize=FS_S, color=MUTE)
    res = {}
    for j, (unit, k) in enumerate((("normalized depth (blade-to-blade = 1)", 0), ("µm", 1))):
        ax = ax_mm(fig, H, 18 + j * 88, 22, 62, 52)
        rng = np.random.default_rng(2)
        xt = []
        for gi, g in enumerate(("CTL", "IED-", "IED+")):
            for bi, blade in enumerate(("upper", "lower")):
                xx = gi * 2.6 + bi
                xt.append((xx, "%s\n%s" % ({"CTL": "control", "IED-": "IED−", "IED+": "IED+"}[g], blade)))
                v = np.array([apart(r)[k][bi] for r in groups[g]])
                lb = [r.lab for r in groups[g]]
                ok = np.isfinite(v)
                xs = xx + rng.uniform(-0.2, 0.2, ok.sum())
                ax.scatter(xs, v[ok], s=16, color=[Hs.col_of(r) for r, o in zip(groups[g], ok) if o], edgecolor="white", linewidth=0.4, zorder=3)
                for x_, y_, l_ in zip(xs, v[ok], [l for l, o in zip(lb, ok) if o]):
                    ax.annotate(l_, (x_, y_), xytext=(3, 0), textcoords="offset points", fontsize=3.8, color=MUTE, va="center")
                if ok.any():
                    ax.plot([xx - 0.3, xx + 0.3], [np.median(v[ok])] * 2, color=INK, lw=1.0)
        ax.axhline(0, color=HAIR, lw=0.6)
        ax.set_xticks([x for x, _ in xt])
        ax.set_xticklabels([l for _, l in xt], fontsize=4.6)
        ax.set_ylabel("DS1 sink minus DS2 sink, outward (%s)" % unit, fontsize=FS_S)
        ax.tick_params(labelsize=4.8)
    # tests on the mean of the two blades, in um
    y = 86
    text_mm(fig, H, 4, y, "Mean of the two blades (µm), raw P (UNCORRECTED); Mann–Whitney, exact", fontsize=FS, fontweight="bold")
    vals = {g: np.array([np.nanmean(apart(r)[1]) for r in groups[g]]) for g in ("CTL", "IED-", "IED+", "PTEN")}
    for i, g in enumerate(("CTL", "IED-", "IED+")):
        v = vals[g][np.isfinite(vals[g])]
        text_mm(fig, H, 6, y + 4.5 + 3.4 * i, ("%s: median %.0f µm (range %.0f to %.0f, n = %d)" % (Hs.GROUP_NAME[g], np.median(v), v.min(), v.max(), v.size)).replace("-", "−"), fontsize=FS_S)
    yy = y + 4.5 + 3.4 * 3 + 1.5
    for i, (a, b) in enumerate((("IED-", "CTL"), ("IED-", "IED+"), ("IED+", "CTL"), ("PTEN", "CTL"))):
        va, vb = vals[a][np.isfinite(vals[a])], vals[b][np.isfinite(vals[b])]
        p = st.mannwhitneyu(va, vb, alternative="two-sided", method="exact").pvalue if va.size and vb.size else np.nan
        res["%s_vs_%s" % (a, b)] = {"p": float(p), "median_a": float(np.median(va)), "median_b": float(np.median(vb))}
        text_mm(fig, H, 6, yy + 3.4 * i, "%s against %s: %.0f against %.0f µm, P = %.3f" % (Hs.GROUP_NAME[a], Hs.GROUP_NAME[b], np.median(va), np.median(vb), p),
                fontsize=FS_S, color=INK if p < 0.05 else MUTE)
    notes = ["DS1 and DS2: each recording's %s, names checked against the anatomy, DS3 events taken out. A type with %s is left out." % (
        "best classifier by index with no minimum type size" if NOCUT else "best eligible classifier (each type 5% of events or more)",
        "no events" if NOCUT else "fewer than 5 events"),
        "µm: the normalized distance times the recording's distance between its two blade sinks. Groups: control m2, m21, m22, m26, m59, m60, m61; IED− m8, m33, m1, m7; IED+ m13, m28, m3, m5, m34."]
    for i, s_ in enumerate(notes):
        text_mm(fig, H, 4, H - 9 + 3.2 * i, s_, fontsize=FS_S - 0.4, color=MUTE)
    pdf.savefig(fig)
    fig.savefig(os.path.join(OUT, "Averaged_DS1_DS2%s_apart.png" % TAG), dpi=200)
    plt.close(fig)
    return res


def comparison_page(pdf, groups):
    H = 142.0
    fig = Hs.page(H)
    text_mm(fig, H, 4, 5, "DS1 and DS2 without DS3: the groups laid over each other", fontsize=9, fontweight="bold")
    Hs.stamp(fig)
    res = {}
    pairs = [("CTL", "PTEN"), ("IED-", "IED+"), ("CTL", "IED+"), ("CTL", "IED-")]
    for j, (c, cc) in enumerate(((1, C_DS1), (2, C_DS2))):
        ax = ax_mm(fig, H, 22 + j * 62, 20, 44, 88)
        for g in ("CTL", "IED-", "IED+"):
            mean_band(ax, stack(groups[g], c), Hs.GROUP_COL[g], lw=1.3, label="%s (n = %d)" % (Hs.GROUP_NAME[g], len(stack(groups[g], c))))
        depth_axis(ax, j == 0)
        ax.set_title("DS1" if c == 1 else "DS2", fontsize=FS + 1, loc="left", pad=3, color=cc, fontweight="bold")
        ax.set_xlabel("CSD at the DS peak\n(1 = the recording's average sink)", fontsize=FS)
        if j == 0:
            ax.legend(frameon=False, fontsize=FS_S, loc="lower left", handlelength=1.6)
        for a, b in pairs:
            A, B = stack(groups[a], c), stack(groups[b], c)
            if len(A) >= 3 and len(B) >= 3:
                _, cl, p = N.cluster_test(A, B, n_perm=4000)
                best = min(cl, key=lambda z: z[3]) if cl else None
                res["DS%d %s vs %s" % (c, a, b)] = {"p": p, "where": None if best is None else [float(U[best[0]]), float(U[best[1]])]}
    x0 = 150
    text_mm(fig, H, x0 - 20, 22, "Do the groups differ anywhere along the depth?", fontsize=FS, fontweight="bold")
    text_mm(fig, H, x0 - 20, 26, "Cluster permutation test, raw P (not corrected)", fontsize=FS_S, color=RED)
    i = 0
    for c in (1, 2):
        for a, b in pairs:
            k = "DS%d %s vs %s" % (c, a, b)
            if k not in res:
                continue
            v = res[k]
            nm = lambda g: {"CTL": "control", "PTEN": "PTEN", "IED-": "IED−", "IED+": "IED+"}[g]
            where = "" if v["where"] is None else (", depth %.2f to %.2f" % tuple(v["where"])).replace("-", "−")
            text_mm(fig, H, x0 - 20, 31 + 3.5 * i, ("DS%d, %s against %s: P = %.3f%s" % (c, nm(a), nm(b), v["p"], where if v["p"] < 0.2 else "")) if v["where"] is not None else
                    "DS%d, %s against %s: no depth where |t| passes 2.1" % (c, nm(a), nm(b)),
                    fontsize=FS_S, color=INK if v["p"] < 0.05 else MUTE)
            i += 1
    notes = ["Groups: control (m2, m21, m22, m26, m59, m60, m61; m6 left out), PTEN IED− (m8, m33, m1, m7), PTEN IED+ (m13, m28, m3, m5, m34), from the lab sheet.",
             "Thick line and band: mean ± s.e.m. over recordings; normalized as on the group pages (depth 0 and 1: where the recording's average sink is deepest in the upper and",
             "lower blade; size: 1 = that average sink). Test: Welch t at every depth, runs over |t| 2.1 summed, the largest run against 4,000 shufflings of the group labels.",
             "PTEN (all) against control is in the list; it is not drawn as its own line. m3 has no DS3 score (its DS1 and DS2 sink at the same contact), so nothing is taken out there."]
    for k_, s in enumerate(notes):
        text_mm(fig, H, 4, 126 + 3.3 * k_, s, fontsize=FS_S - 0.2, color=MUTE)
    pdf.savefig(fig)
    fig.savefig(os.path.join(OUT, "Averaged_DS1_DS2%s_comparison.png" % TAG), dpi=200)
    plt.close(fig)
    return res


if __name__ == "__main__":
    groups = {"CTL": [r for r in recs if r.group == "CTL"], "PTEN": [r for r in recs if r.group == "PTEN"],
              "IED-": [r for r in recs if r.subgroup == "IED-"], "IED+": [r for r in recs if r.subgroup == "IED+"]}
    for g in groups:
        groups[g] = sorted(groups[g], key=lambda r: (r.subgroup != "IED-", r.ko, r.lab))
    with PdfPages(os.path.join(OUT, "Averaged_DS1_DS2%s.pdf" % TAG)) as pdf:
        group_page(pdf, groups["CTL"], "Control: DS1 and DS2 without DS3, depth normalized", Hs.C_CTL, "1_control")
        group_page(pdf, groups["PTEN"], "PTEN knockout, all: DS1 and DS2 without DS3, depth normalized", Hs.GROUP_COL["PTEN"], "2_PTEN_all")
        group_page(pdf, groups["IED-"], "PTEN IED−: DS1 and DS2 without DS3, depth normalized", Hs.C_IEDN, "3_PTEN_IEDneg")
        group_page(pdf, groups["IED+"], "PTEN IED+: DS1 and DS2 without DS3, depth normalized", Hs.C_IEDP, "4_PTEN_IEDpos")
        res = comparison_page(pdf, groups)
        res["apart"] = apart_page(pdf, groups)
    json.dump(res, open(os.path.join(dsdata.HERE, "results", "cluster_tests_ds1_ds2%s.json" % TAG), "w"), indent=1)
    for k, v in res.items():
        print(k, v)
