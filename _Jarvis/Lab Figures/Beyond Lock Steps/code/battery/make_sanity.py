"""SANITY CHECK of the DS1 / DS2 names and of DS3, one document per group:
  round11/Sanity_check_CTL.pdf, round11/Sanity_check_PTEN.pdf
Asked 2026-11-17: why do m2, m60, m13, m3, m5 and m34 have more DS1 than
DS2, and is DS3 doing what it is supposed to?
For every recording, under the classifier the other pages use (the best
eligible one by separation index):
  a  each type's mean CSD down the probe, past the analyzed band, with the
     two contacts DS3 is scored on
  b  how many events are DS1, DS2, DS3 (the classifier alone; DS3 as Jarvis
     scored it; DS3 scored again with the layers looked for past the band)
  c  every event's sink at the outer contact against its sink at the middle
     contact: the DS3 rule is the green wedge, the noise floor the gray corner
  d  the DS3 score of every event, DS1 and DS2 stacked
  python make_sanity.py
"""
import os
import textwrap

import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

import dsdata
import house as Hs
from house import plt, ax_mm, text_mm, letter, INK, MUTE, HAIR, C_DS1, C_DS2, C_DS3, FS, FS_S, W

OUT = os.path.join(os.path.dirname(dsdata.HERE), "round11")
os.makedirs(OUT, exist_ok=True)
RECS = [r for r in dsdata.load("v6") if r.n >= dsdata.MIN_EVENTS]
NAMES = {"bite": "Bite line", "pca": "PCA, k-means", "pca_gap": "PCA + gap", "delta": "Delta", "delta_mid": "Delta middle",
         "pca_gmm_line": "PCA, mixture (line)", "pca_gmm_curve": "PCA, mixture (curve)", "opt_line": "PCA, optimized line",
         "opt_curve": "PCA, optimized curve"}
ASKED = {"m2", "m60", "m13", "m3", "m5", "m34"}


def clf_name(m):
    base = m.replace("_top", "").replace("_bottom", "")
    suf = m[len(base):]
    return NAMES.get(base, base) + {"": "", "_top": ", upper sink", "_bottom": ", lower sink"}[suf]


def tort_flipped(r, t):
    """Did Jarvis's naming rule (dspca.tort_order) fall back to the lower
    blade for this split? It does when both types' sinks above the main
    source land on the same contact."""
    a, b = r.band
    rows = []
    for c in (1, 2):
        mu = r.csd_peak[t == c][:, a:b + 1].mean(axis=0)
        src = int(np.argmax(mu))
        rows.append(int(np.argmin(mu[:src])) if src >= 1 else int(np.argmin(mu)))
    return rows[0] == rows[1]


def half_width_um(p, row):
    s = -np.asarray(p, float)
    if s[row] <= 0:
        return np.nan
    h = s[row] / 2
    lo = hi = row
    while lo - 1 >= 0 and s[lo - 1] > h:
        lo -= 1
    while hi + 1 < s.size and s[hi + 1] > h:
        hi += 1
    return (hi - lo + 1) * dsdata.SPACING_UM


def inside(f):
    """The outer and middle contacts sit inside one sink and most events score DS3."""
    w = f["w"]
    return "score" in w and np.isfinite(f.get("width_um", np.nan)) and w["gap_um"] < f["width_um"] and f["x3"].mean() > 0.4


def facts(r):
    """Everything one block shows, as numbers."""
    c = r.used
    t = r.types(c)
    jt = np.asarray(r.labels[c].get("types_jarvis", t), int)
    w = r.ds3w.get(c) or {}
    f = {"clf": c, "si": r.si(c), "t": t, "n1": int((t == 1).sum()), "n2": int((t == 2).sum()), "naming": r.naming[c],
         "jarvis_n1": int((jt == 1).sum()), "renamed": "types_jarvis" in r.labels[c], "w": w}
    f["flipped"] = tort_flipped(r, jt)
    for key, which in (("j", "jarvis"), ("x", "widened")):
        m3 = r.ds3(c, which=which)
        f[key + "3"] = m3
        f[key + "_counts"] = None if m3 is None else (int(((t == 1) & ~m3).sum()), int(((t == 2) & ~m3).sum()), int(m3.sum()))
    cat = r.ds3_category(c)
    f["cat"] = cat
    if "score" in w:
        f["ds1_scored"] = int(np.isfinite(w["score"][t == 1]).sum())
        f["ds2_scored"] = int(np.isfinite(w["score"][t == 2]).sum())
        p = dsdata.fill_bad(r.csd_peak.mean(axis=0), r.bad_rows)
        f["width_um"] = half_width_um(p, w["middle"])
        f["outside"] = [x for x in (w["outer"], w["middle"]) if not (r.band[0] <= x <= r.band[1])]
    # where each type's sink is, per blade
    mu = {k: dsdata.fill_bad(r.csd_peak[t == k].mean(axis=0), r.bad_rows) for k in (1, 2)}
    f["mu"] = mu
    f["se"] = {k: dsdata.fill_bad(r.csd_peak[t == k].std(axis=0) / np.sqrt(max(1, (t == k).sum())), r.bad_rows) for k in (1, 2)}
    f["sink_rows"] = {k: [r.sink_distance_um(mu[k], b)[1] for b in ("upper", "lower")] for k in (1, 2)}
    f["ds1_outside_band"] = [b for b, x in zip(("upper", "lower"), f["sink_rows"][1]) if x is not None and not (r.band[0] <= x <= r.band[1])]
    return f


def rel(x):
    if not np.isfinite(x):
        return "nowhere (no sink there)"
    if abs(x) < 25:
        return "at the same place"
    return "%.0f µm %s" % (abs(x), "farther from the cell layer" if x > 0 else "nearer the cell layer")


def explain(r, f):
    """The block's plain-words reading, one sentence a point."""
    out = []
    nv = f["naming"]
    d = nv["diff"]
    if f["renamed"]:
        out.append("Names: Jarvis had these the other way round. %s Renamed here so DS1 is the type whose sink sits farther from the cell layer "
                   "(%.0f µm farther in the upper blade, %.0f µm in the lower)." % (
                       "Its rule found both types' sinks on the same contact in the upper blade, fell back to the lower blade, and there calls the type nearer the cell layer DS1, which is the inner one."
                       if f["flipped"] else "Its rule asks which type's sink is higher on the probe, which here picked the inner one.", -d[0], -d[1]))
    elif nv["verdict"] == "same place":
        out.append("Names: the two types' sinks sit on the same contacts in both blades (within 25 µm), so the classifier did not split them by where the sink is. "
                   "Which one is called DS1 is arbitrary, and DS3 cannot be scored.")
    elif nv["verdict"] == "blades disagree":
        out.append("Names: one blade puts DS1 farther out, the other nearer in (%+.0f and %+.0f µm); the name is uncertain and left as Jarvis gave it." % (d[0], d[1]))
    else:
        out.append("Names: follow the anatomy. Compared with DS2's sink, DS1's sits %s in the upper blade and %s in the lower blade." % (rel(d[0]), rel(d[1])))
    if f["n1"] > f["n2"] and nv["verdict"] in ("ok", "swapped"):
        out.append("More DS1 than DS2 (%d against %d): the classifier split off a small group whose sink sits nearer the cell layer than the rest. "
                   "Most events keep the recording's usual sink position and, being the farther out of the two, are named DS1. So DS1 here is most of the events, "
                   "not a small outer-layer type." % (f["n1"], f["n2"]))
    elif f["n1"] > f["n2"]:
        out.append("More DS1 than DS2 (%d against %d) only because the name is arbitrary here." % (f["n1"], f["n2"]))
    w = f["w"]
    if "score" not in w:
        out.append("DS3: cannot be scored (%s). That is not 'no DS3'; the score needs two different contacts." % w.get("why", ""))
        return out
    pct = 100.0 * f["x3"].mean()
    if inside(f):
        out.append("DS3: the outer and middle contacts are %.0f µm apart, inside one sink that is %.0f µm wide at half its depth, so most events have sink at both "
                   "and score as DS3 (%.0f%%). The rule is followed, but here it cannot tell a sink at both layers from one sink wider than the gap." % (w["gap_um"], f["width_um"], pct))
    else:
        out.append("DS3: the outer and middle contacts are %.0f µm apart, at least as far apart as the sink is wide (%.0f µm at half depth), so the score can tell them apart: DS3 %.0f%%." % (
            w["gap_um"], f.get("width_um", np.nan), pct))
    if f["ds1_scored"] < 0.5 * f["n1"]:
        out.append("Only %d of %d DS1 events can be scored at all: the rest have outer + middle sink under the noise floor, so the score never calls them DS1 or DS3. "
                   "DS3 here can only come out of DS2." % (f["ds1_scored"], f["n1"]))
    if f["ds1_outside_band"]:
        out.append("DS1's sink lies outside the analyzed band in the %s blade: the classifiers saw only its edge." % " and ".join(f["ds1_outside_band"]))
    if f["j_counts"] != f["x_counts"]:
        out.append("Looking for the layers past the band moved the contacts (Jarvis: %s µm apart); DS3 went from %d to %d events." % (
            r.ds3_gap_um_jarvis.get(f["clf"]), f["j_counts"][2] if f["j_counts"] else 0, f["x_counts"][2]))
    return out


def block(fig, H, y0, r, f):
    parts = [r.lab, Hs.GROUP_NAME[r.subgroup]] + ([] if r.group == "CTL" else ["%.1f%% knockout" % r.ko]) + [
        "%d events" % r.n, "classifier: %s" % clf_name(f["clf"]), "separation index %.2f" % f["si"]]
    text_mm(fig, H, 4, y0 + 2, "  ·  ".join(parts), fontsize=7.5, fontweight="bold")
    if r.lab in ASKED:
        text_mm(fig, H, 179, y0 + 2, "asked about", fontsize=FS_S, color=Hs.RED, ha="right", fontweight="bold")
    yA = y0 + 11
    hA = 44
    for x, ttl in ((2, "a  Each type's mean CSD down the probe"), (58, "b  Events of each type"), (100, "c  Each event at the two DS3 contacts"),
                   (142, "d  DS3 score of each event")):
        text_mm(fig, H, x, yA - 4.5, ttl, fontsize=FS_S + 0.3, fontweight="bold")
    # a  mean CSD down the probe
    ax = ax_mm(fig, H, 14, yA, 30, hA)
    a, b = r.band
    lo, hi = max(0, a - 8), min(63, b + 8)
    rows = np.arange(lo, hi + 1)
    dep = (rows - lo) * dsdata.SPACING_UM
    ax.axhspan((a - lo) * 50 - 25, (b - lo) * 50 + 25, color="#F1F1F1", lw=0, zorder=0)
    ax.axvline(0, color=HAIR, lw=0.5, zorder=0)
    for k, col in ((2, C_DS2), (1, C_DS1)):
        m, s = f["mu"][k][rows], f["se"][k][rows]
        ax.fill_betweenx(dep, m - s, m + s, color=col, alpha=0.2, lw=0)
        ax.plot(m, dep, color=col, lw=1.0)
    x_all = np.concatenate([f["mu"][k][rows] for k in (1, 2)])
    span = max(abs(x_all.min()), abs(x_all.max())) * 1.15
    ax.set_xlim(-span, span)
    ax.set_ylim(dep[-1] + 25, -25)
    kl = r.landmarks
    for g in sorted({kl["rowGU"], kl["rowGL"]}):
        ax.plot([span], [(g - lo) * 50], marker="<", color=Hs.RED, ms=3.2, clip_on=False)
        ax.text(span * 1.12, (g - lo) * 50, "cell layer\nsource", fontsize=4.2, color=Hs.RED, ha="left", va="center", linespacing=0.9)
    w = f["w"]
    if "score" in w:
        o_y, m_y = (w["outer"] - lo) * 50, (w["middle"] - lo) * 50
        dy = 0 if abs(o_y - m_y) > 90 else 45
        for yv, nm, sg in ((o_y, "outer", -1 if o_y < m_y else 1), (m_y, "middle", 1 if o_y < m_y else -1)):
            ax.plot([span], [yv], marker="<", color=C_DS3, ms=3.4, clip_on=False)
            ax.text(span * 1.12, yv + sg * dy, nm, fontsize=4.6, color=C_DS3, ha="left", va="center")
    ax.set_ylabel("Depth below contact %d (µm)" % (lo + 1), fontsize=FS_S)
    ax.set_xlabel("CSD at the DS peak (±3 ms)\nleft = sink, right = source", fontsize=FS_S - 0.3)
    ax.tick_params(labelsize=4.8)
    ax.text(span * 0.95, dep[-1] + 20, "gray: analyzed band", fontsize=4.4, color=MUTE, ha="right", va="bottom", bbox=dict(fc="white", ec="none", pad=0.4))
    # b  counts
    ax = ax_mm(fig, H, 60, yA + 3, 30, hA - 16)
    bars = [("Classifier", (f["n1"], f["n2"], 0))]
    if f["j_counts"] is not None:
        bars.append(("DS3 as in Jarvis", f["j_counts"]))
    if f["x_counts"] is not None:
        bars.append(("DS3, layers past band", f["x_counts"]))
    for i, (lab, (n1, n2, n3)) in enumerate(bars):
        left = 0
        for v, col in ((n1, C_DS1), (n3, C_DS3), (n2, C_DS2)):
            ax.barh([i], [v], left=left, color=col, height=0.62, lw=0)
            if v >= 0.07 * r.n:
                ax.text(left + v / 2, i, "%d" % v, fontsize=4.6, color="white", ha="center", va="center", fontweight="bold")
            left += v
        ax.text(0, i - 0.43, lab, fontsize=4.8, color=INK, ha="left", va="bottom")
        small = ["%s %d" % (nm, v) for nm, v in (("DS1", n1), ("DS3", n3), ("DS2", n2)) if 0 < v < 0.07 * r.n]
        if small:
            ax.text(r.n * 1.02, i, ", ".join(small), fontsize=4.4, color=MUTE, ha="left", va="center")
    ax.set_ylim(max(len(bars), 2) - 0.4, -0.75)
    ax.set_xlim(0, r.n)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Events", fontsize=FS_S)
    ax.tick_params(labelsize=4.8)
    if f["x_counts"] is None:
        ax.text(0, 0.62, "DS3 cannot be scored", fontsize=4.8, color=MUTE, va="center")
    ax.text(0, -1.25, "DS1", fontsize=5, color=C_DS1, fontweight="bold", va="center")
    ax.text(r.n * 0.2, -1.25, "DS3", fontsize=5, color=C_DS3, fontweight="bold", va="center")
    ax.text(r.n * 0.4, -1.25, "DS2", fontsize=5, color=C_DS2, fontweight="bold", va="center")
    # c  outer against middle
    ax = ax_mm(fig, H, 106, yA, 30, 30)
    if "score" in w:
        so = np.maximum(-r.csd_peak[:, w["outer"]], 0)
        sm = np.maximum(-r.csd_peak[:, w["middle"]], 0)
        top = float(np.percentile(np.concatenate([so, sm]), 99)) * 1.08 or 1.0
        xx = np.linspace(0, top, 50)
        ax.fill_between(xx, xx / 3.0, np.minimum(3.0 * xx, top), color=C_DS3, alpha=0.13, lw=0)
        fl = w["floor"]
        ax.fill_between([0, min(fl, top)], [min(fl, top), 0], 0, color="#DADADA", lw=0)
        t = f["t"]
        for k, col in ((2, C_DS2), (1, C_DS1)):
            ax.scatter(so[t == k], sm[t == k], s=2.2, color=col, lw=0, alpha=0.75)
        ax.set_xlim(0, top)
        ax.set_ylim(0, top)
        ax.set_aspect("equal", adjustable="box")
        ax.text(top * 0.97, top * 0.03, "sink mostly\nat outer", fontsize=4.4, color=MUTE, ha="right", va="bottom")
        ax.text(top * 0.03, top * 0.97, "sink mostly\nat middle", fontsize=4.4, color=MUTE, ha="left", va="top")
        ax.text(top * 0.62, top * 0.66, "DS3", fontsize=5, color=C_DS3, ha="center", va="center", fontweight="bold", rotation=45)
        ax.set_xlabel("Sink at the outer contact (%d)" % (w["outer"] + 1), fontsize=FS_S)
        ax.set_ylabel("Sink at the middle contact (%d)" % (w["middle"] + 1), fontsize=FS_S)
        ax.tick_params(labelsize=4.6)
    else:
        Hs.bare(ax)
        ax.text(0.5, 0.5, "DS3 cannot be scored:\nDS1's and DS2's mean sinks\nare deepest at the same contact", transform=ax.transAxes, fontsize=FS_S, ha="center", va="center", color=MUTE)
    # d  score histogram
    ax = ax_mm(fig, H, 150, yA, 29, 28)
    if "score" in w:
        s = w["score"]
        t = f["t"]
        bins = np.linspace(-1, 1, 21)
        h1 = np.histogram(s[(t == 1) & np.isfinite(s)], bins)[0]
        h2 = np.histogram(s[(t == 2) & np.isfinite(s)], bins)[0]
        cen = 0.5 * (bins[1:] + bins[:-1])
        ax.bar(cen, h2, width=0.095, color=C_DS2, lw=0)
        ax.bar(cen, h1, width=0.095, bottom=h2, color=C_DS1, lw=0)
        ax.axvspan(-0.5, 0.5, color=C_DS3, alpha=0.1, lw=0, zorder=0)
        ax.set_xlim(-1.05, 1.05)
        ax.set_xticks([-1, -0.5, 0, 0.5, 1])
        ax.set_xticklabels(["−1\nmiddle", "−0.5", "0", "0.5", "1\nouter"])
        ax.set_xlabel("DS3 score (outer − middle) / (outer + middle)", fontsize=FS_S - 0.3)
        ax.set_ylabel("Events", fontsize=FS_S)
        ax.tick_params(labelsize=4.6)
        nun1, nun2 = f["n1"] - f["ds1_scored"], f["n2"] - f["ds2_scored"]
        ax.text(1.0, 1.04, "unscored: DS1 %d, DS2 %d" % (nun1, nun2), transform=ax.transAxes, fontsize=4.6, ha="right", va="bottom", color=MUTE)
    else:
        Hs.bare(ax)
    # words
    yy = yA + hA + 11
    for s in explain(r, f):
        for ln in textwrap.wrap(s, 178):
            text_mm(fig, H, 4, yy, ln, fontsize=FS_S, color=INK)
            yy += 3.0
        yy += 0.6
    return yy


def RED_IF(r):
    return INK


def summary_page(pdf, group, rs, F):
    H = 150.0
    fig = Hs.page(H)
    text_mm(fig, H, 4, 5, "SANITY CHECK  ·  %s  ·  DS1 / DS2 names and DS3" % Hs.GROUP_NAME[group], fontsize=10, fontweight="bold")
    text_mm(fig, H, 4, 10.5, "Halo set. Each recording under its best eligible classifier (the one the other pages use). m6 is left out (confounding factors during the experiment); "
            "m51 has 5 events.", fontsize=FS_S, color=MUTE)
    cols = [("Recording", 4), ("Events", 22), ("Classifier", 34), ("Index", 72), ("DS1", 82), ("DS2", 91), ("Names", 100), ("DS3 Jarvis", 121),
            ("DS3 past band", 136), ("Contacts apart", 153), ("Sink width", 168)]
    y = 20
    for nm, x in cols:
        text_mm(fig, H, x, y, nm, fontsize=FS_S, fontweight="bold")
    fig.add_artist(plt.Line2D([4 / W, 179 / W], [1 - (y + 2) / H] * 2, color=INK, lw=0.5, transform=fig.transFigure))
    y += 5.5
    for r in rs:
        f = F[r.lab]
        nv = f["naming"]["verdict"]
        vals = [r.lab + ("  %s" % r.subgroup.replace("-", "−") if group == "PTEN" else ""), "%d" % r.n, clf_name(f["clf"]), "%.2f" % f["si"], "%d" % f["n1"], "%d" % f["n2"],
                {"ok": "follow anatomy", "swapped": "were swapped", "same place": "arbitrary", "blades disagree": "uncertain"}.get(nv, nv),
                "—" if f["j3"] is None else "%.0f%%" % (100 * f["j3"].mean()), "—" if f["x3"] is None else "%.0f%%" % (100 * f["x3"].mean()),
                "—" if "score" not in f["w"] else "%.0f µm" % f["w"]["gap_um"], "—" if "score" not in f["w"] else "%.0f µm" % f["width_um"]]
        for (nm, x), v in zip(cols, vals):
            colr = INK
            if nm == "DS1" and f["n1"] > f["n2"]:
                colr = Hs.RED
            if nm == "Names" and nv != "ok":
                colr = Hs.RED
            if nm == "Contacts apart" and inside(f):
                colr = Hs.RED
            text_mm(fig, H, x, y, v, fontsize=FS_S, color=colr, fontweight="bold" if (nm == "Recording" and r.lab in ASKED) else "normal")
        y += 4.2
    y += 3
    notes = ["Red: more DS1 than DS2; names that were swapped or cannot be decided; outer and middle contacts closer together than the sink is wide while most events score DS3. Bold recordings: the ones asked about.",
             "Index: separation index of DS1 against DS2 (1 = their sinks do not overlap). DS1, DS2: counts under the classifier, before DS3 is taken out.",
             "Names: DS1 should be the type whose sink sits farther from the cell layer. Checked in both blades on each type's mean CSD; 'were swapped' = Jarvis named them the other way round and they are renamed on every page from now on.",
             "DS3 (Tarcsay et al. 2025): score = (sink at the outer contact − sink at the middle contact) / (their sum), at the DS peak (±3 ms); between −0.5 and 0.5 = DS3. The outer and middle contacts are where",
             "DS1's and DS2's mean sinks are deepest. 'Jarvis': those contacts looked for inside the analyzed band only. 'Past band': looked for 5 contacts past it too, on the cell layer's far side (used from now on).",
             "Contacts apart: how far apart the outer and middle contacts are. Sink width: how wide the recording's average sink is at half its depth, at the middle contact. When the two contacts sit inside one",
             "sink, nearly every event has sink at both and scores as DS3."]
    for s in textwrap.wrap(" ".join(notes), 190):
        text_mm(fig, H, 4, y, s, fontsize=FS_S - 0.3, color=MUTE)
        y += 3.1
    y += 3
    text_mm(fig, H, 4, y, "What the check found", fontsize=FS, fontweight="bold")
    y += 4.5
    for s in findings(rs, F):
        for i, ln in enumerate(textwrap.wrap(s, 180)):
            text_mm(fig, H, 4 if i == 0 else 6.5, y, ("•  " if i == 0 else "") + ln, fontsize=FS_S)
            y += 3.1
        y += 0.8
    pdf.savefig(fig)
    fig.savefig(os.path.join(OUT, "Sanity_check_%s_summary.png" % group), dpi=200)
    plt.close(fig)


def findings(rs, F):
    out = []
    more = [r.lab for r in rs if F[r.lab]["n1"] > F[r.lab]["n2"]]
    inner = [r.lab for r in rs if F[r.lab]["n1"] > F[r.lab]["n2"] and F[r.lab]["naming"]["verdict"] in ("ok", "swapped")]
    if more:
        out.append("More DS1 than DS2 in %s. In %s the classifier split off a small group whose sink sits nearer the cell layer than the rest; most events keep the "
                   "recording's usual sink position and are named DS1 because they are the farther out of the two. Here DS1 is not the small outer-layer type of the "
                   "literature, and the split's separation index is low." % (", ".join(more), ", ".join(inner) or "none"))
    sw = [r.lab for r in rs if F[r.lab]["renamed"]]
    if sw:
        out.append("Names swapped by Jarvis in %s: its rule (tortlab's 'shallower sink first') falls back to the lower blade when both types share the upper-blade contact, "
                   "and in the lower blade the shallower sink is the inner one. Renamed by anatomy on every page from now on." % ", ".join(sw))
    same = [r.lab for r in rs if F[r.lab]["naming"]["verdict"] == "same place"]
    if same:
        out.append("In %s the two types' sinks sit at the same place: the names are arbitrary there and DS3 cannot be scored." % ", ".join(same))
    close = [r.lab for r in rs if inside(F[r.lab])]
    if close:
        out.append("DS3 follows its rule but cannot do its job in %s: the outer and middle contacts sit inside one sink (closer together than the sink is wide), so most events "
                   "score as DS3 (%s)." % (", ".join(close), ", ".join("%s %.0f%%" % (x, 100 * F[x]["x3"].mean()) for x in close)))
    unsc = [r.lab for r in rs if "score" in F[r.lab]["w"] and F[r.lab]["ds1_scored"] < 0.5 * F[r.lab]["n1"]]
    if unsc:
        out.append("Where DS1 is a small group with its sink well out (%s), most of its events cannot be scored: their sink at the two contacts is under the noise floor. "
                   "There the score never calls an event DS1, and DS3 can only come out of DS2." % ", ".join(unsc))
    out.append("So in no recording does the DS3 score behave as in the paper (all three types in proportions near 1 : 2 : 1). The paper's probes had contacts 20–25 µm apart; "
               "this probe has 50 µm, and its CSD sinks are 150–400 µm wide.")
    return out


def main():
    for group in ("CTL", "PTEN"):
        rs = [r for r in RECS if r.group == group and r.ok]
        if group == "PTEN":
            rs = sorted(rs, key=lambda r: (r.subgroup != "IED-", r.ko))
        F = {r.lab: facts(r) for r in rs}
        with PdfPages(os.path.join(OUT, "Sanity_check_%s.pdf" % group)) as pdf:
            summary_page(pdf, group, rs, F)
            per = 3
            for i in range(0, len(rs), per):
                H = 276.0
                fig = Hs.page(H)
                text_mm(fig, H, 4, 4, "SANITY CHECK  ·  %s" % Hs.GROUP_NAME[group], fontsize=FS, color=MUTE)
                y = 9
                for r in rs[i:i + per]:
                    y = block(fig, H, y, r, F[r.lab]) + 5
                    fig.add_artist(plt.Line2D([4 / W, 179 / W], [1 - (y - 3) / H] * 2, color=HAIR, lw=0.4, transform=fig.transFigure))
                pdf.savefig(fig)
                fig.savefig(os.path.join(OUT, "Sanity_check_%s_p%d.png" % (group, i // per + 1)), dpi=170)
                plt.close(fig)
        print(group, "saved", len(rs))


if __name__ == "__main__":
    main()
