"""Quality check, round 5: one page a recording, laid out as three rows
that read the same way -- the classifier used, the conventional boundary
on the PCA plane, and the boundary optimized for the separation index --
each with the PCA plane, every event, the DS1 and DS2 means and the sink
amplitudes, in the same columns."""
import os
import pickle
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import deep_figs as G  # noqa: E402
from deep_figs import D2, plt, recs, full, W, INK, MUTE, HAIR, C_DS1, C_DS2, C_DS3, CSD_CMAP, FS, FS_S  # noqa: E402
COLS = {1: C_DS1, 2: C_DS2, 3: C_DS3}
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

OUT = r"c:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\round10\quality_check"
sys.path.insert(0, r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery")
import dsdata  # noqa: E402
import normcurves as NC  # noqa: E402
RECS = {r_.lab: r_ for r_ in dsdata.load("v6")}
GROUPS = {"CTL": [r_ for r_ in RECS.values() if r_.ok and r_.group == "CTL"], "PTEN": [r_ for r_ in RECS.values() if r_.ok and r_.group == "PTEN"]}
SEP = [r_ for r_ in RECS.values() if r_.ok and r_.separable()]
os.makedirs(OUT, exist_ok=True)
H = 386.0
RED, PURPLE = "#B5361F", "#6A3D9A"
NAMES = {"bite": "Bite line", "pca": "PCA, k-means", "pca_gap": "PCA + gap", "delta": "Delta", "delta_mid": "Delta middle",
         "pca_gmm_line": "PCA, mixture (line)", "pca_gmm_curve": "PCA, mixture (curve)",
         "opt_line": "PCA, index-optimized (line)", "opt_curve": "PCA, index-optimized (curve)"}
ROWS = {"": "both sinks", "_top": "upper sink", "_bottom": "lower sink"}
ON_PLANE = ("pca", "pca_gmm_line", "pca_gmm_curve")
PCA2 = pickle.load(open(os.path.join(HERE, "deep_pca2_v6.pkl"), "rb"))
OPT = pickle.load(open(os.path.join(HERE, "deep_opt_v6.pkl"), "rb"))
OPT2 = pickle.load(open(os.path.join(HERE, "deep_opt2_v6.pkl"), "rb"))
DS3 = pickle.load(open(os.path.join(HERE, "deep_ds3_v6.pkl"), "rb"))
DS3_CUT = 0.5


def si_sub(d, t3):
    """The whole-band separation index of DS1 against DS2 among the events
    that are still DS1 or DS2 in `t3`."""
    Wd = (OPT2.get(d["gid"]) or {}).get("W") or {}
    if "both" not in Wd:
        return None
    keep = np.where((t3 == 1) | (t3 == 2))[0]
    W0 = Wd["both"][np.ix_(keep, keep)].astype(float).copy()
    np.fill_diagonal(W0, 0.0)
    m = t3[keep] == 1
    na, nb = int(m.sum()), int((~m).sum())
    if na < 2 or nb < 2:
        return None
    Wm = W0 @ m
    saa, sab = float(m @ Wm), float((~m) @ Wm)
    sbb = float(W0.sum()) - saa - 2.0 * sab
    return 1.0 - (sab / (na * nb)) / ((saa / (na * (na - 1)) + sbb / (nb * (nb - 1))) / 2.0)


def ds3_info(d, key, ty, si0):
    """DS3 under one classification: which events score within +-0.5 on
    the relative sink (Tarcsay et al. 2025), and how well DS1 and DS2
    separate without them. `final` is None when a type is left with under
    5 events."""
    src = (DS3.get(d["gid"]) or {}).get(key)
    if src is None:
        e_ = d["splits"].get(key) or {}
        src = e_ if ("score" in e_ or e_.get("why")) and e_.get("why") != "not scored for DS3" else None
    n = ty.size
    if src is None or src.get("why") or "score" not in src:
        return {"ok": False, "mask": np.zeros(n, bool), "t3": ty.copy(), "final": si0, "n1": int((ty == 1).sum()), "n2": int((ty == 2).sum())}
    sc = np.asarray(src["score"], float)
    mask = np.isfinite(sc) & (np.abs(sc) <= DS3_CUT)
    t3 = np.where(mask, 3, ty)
    n1, n2 = int((t3 == 1).sum()), int((t3 == 2).sum())
    return {"ok": True, "mask": mask, "t3": t3, "unsc": int((~np.isfinite(sc)).sum()), "gap": abs(src["oml"] - src["mml"]) * 50,
            "n1": n1, "n2": n2, "final": si_sub(d, t3) if min(n1, n2) >= 5 else None}


def blade_si(d, ty):
    """The separation index of classification `ty` in each blade (that
    blade's own sink overlap): (upper, lower), or None."""
    Wd = (OPT2.get(d["gid"]) or {}).get("W") or {}
    if "top" not in Wd or "bottom" not in Wd:
        return None
    out = []
    for k in ("top", "bottom"):
        W0 = Wd[k].astype(float).copy()
        np.fill_diagonal(W0, 0.0)
        m = ty == 1
        na, nb = int(m.sum()), int((~m).sum())
        if na < 2 or nb < 2:
            return None
        Wm = W0 @ m
        saa, sab = float(m @ Wm), float((~m) @ Wm)
        sbb = float(W0.sum()) - saa - 2.0 * sab
        out.append(1.0 - (sab / (na * nb)) / ((saa / (na * (na - 1)) + sbb / (nb * (nb - 1))) / 2.0))
    return out
for d_ in recs:
    for k_, v_ in (PCA2.get(d_["gid"], {}).get("fits") or {}).items():
        if "err" not in v_ and v_.get("si") is not None:
            d_["splits"][k_] = dict(v_, x=PCA2[d_["gid"]]["X"][:, 0], why="not scored for DS3")


def word(si):
    return "separable" if si >= 0.45 else ("partial" if si >= 0.2 else "not separable")


def full_name(m):
    base = m.replace("_top", "").replace("_bottom", "")
    return NAMES[base] + ("" if base.startswith("pca_gmm") or base.startswith("opt_") else ", " + ROWS[m[len(base):]])


def eligible(e, n):
    return min(e["n1"], e["n2"]) >= max(5, 0.05 * n)


MARGIN, MARGIN_MOST = 5, 12


def extent(d, ty):
    """The whole-shank rows to draw: the analyzed band and 5 contacts a
    side, widened (to 12) while either type's mean sink is still above its
    noise floor at that end. Bad contacts are skipped over, never an end."""
    F = full[d["gid"]]
    na = F["nums_all"]
    a, b = na.index(d["ns"][0]), na.index(d["ns"][-1])
    tt = F["tt"]
    at0 = F["csd_ev"][:, :, np.abs(tt) <= 3.0].mean(axis=2).astype(float)
    base = np.abs(tt) > 30
    sink, floor = {}, {}
    for c in (1, 2):
        sink[c] = np.maximum(-at0[ty == c].mean(axis=0), 0.0)
        floor[c] = float(np.percentile(np.abs(F["csd_ev"][ty == c][:, a:b + 1, :].astype(float).mean(axis=0)[:, base]), 99))
    n_r = at0.shape[1]
    lo, hi = max(0, a - MARGIN), min(n_r - 1, b + MARGIN)
    while lo > max(0, a - MARGIN_MOST) and any(sink[c][lo] > floor[c] for c in (1, 2)):
        lo -= 1
    while hi < min(n_r - 1, b + MARGIN_MOST) and any(sink[c][hi] > floor[c] for c in (1, 2)):
        hi += 1
    return lo, hi


def sinks_of(d, ty, ext, classes=(1, 2)):
    """DS1 and DS2 under any classification `ty`, over the rows `ext`
    (extent): the mean CSD and sink (max(0, -CSD) of the mean) with s.e.m.
    by depth, each mean's noise floor (99th percentile of the mean's |CSD|
    more than 30 ms from the DS, in the analyzed band), and per blade DS1's
    peak sink over its floor, each type's sink centroid above its floor
    and the offset (DS1 distal to DS2) where both clear their floors."""
    F = full[d["gid"]]
    na = F["nums_all"]
    a, b = na.index(d["ns"][0]), na.index(d["ns"][-1])
    lo, hi = ext
    rows = np.arange(lo, hi + 1)
    bad = np.array([na[r] in F["bad"] and not (a <= r <= b) for r in rows])
    ev = F["csd_ev"][:, lo:hi + 1, :].astype(float)
    tt = F["tt"]
    at0 = ev[:, :, np.abs(tt) <= 3.0].mean(axis=2)
    at0[:, bad] = np.nan
    base = np.abs(tt) > 30
    mid = (a + b) / 2.0
    cut = a + d["hump_cut"] - lo
    out = {"dep": (rows - mid) * 50.0, "band": ((a - mid) * 50.0 - 25, (b - mid) * 50.0 + 25), "at0": at0, "inband": (rows >= a) & (rows <= b),
           "sink": {}, "se": {}, "floor": {}, "cen": {}, "peak": {}, "mu": {}, "mse": {}}
    classes = tuple(c for c in classes if (ty == c).any())
    out["classes"] = classes
    for c in classes:
        k = max(int((ty == c).sum()), 1)
        mu = at0[ty == c].mean(axis=0)
        out["mu"][c], out["mse"][c] = mu, at0[ty == c].std(axis=0) / np.sqrt(k)
        out["sink"][c], out["se"][c] = np.maximum(-mu, 0.0), out["mse"][c]
        out["floor"][c] = float(np.percentile(np.abs(ev[ty == c][:, a - lo:b - lo + 1, :].mean(axis=0)[:, base]), 99))
        cs, pk, pd_ = [], [], []
        for l_, h_ in ((0, cut), (cut, rows.size)):
            sk = np.nan_to_num(out["sink"][c][l_:h_])
            pk.append(float(sk.max()))
            pd_.append(float(out["dep"][l_:h_][int(np.argmax(sk))]))
            w = np.maximum(sk - out["floor"][c], 0.0)
            cs.append(float((w * out["dep"][l_:h_]).sum() / w.sum()) if w.sum() > 0 else None)
        out["cen"][c], out["peak"][c] = cs, pk
        out.setdefault("pkdep", {})[c] = pd_
    if 1 in classes and 2 in classes:
        out["clear"] = [out["peak"][1][b_] / max(out["floor"][1], 1e-12) for b_ in (0, 1)]
        out["out"] = [None if out["cen"][1][b_] is None or out["cen"][2][b_] is None
                      else round((out["cen"][2][b_] - out["cen"][1][b_]) * (1 if b_ == 0 else -1)) for b_ in (0, 1)]
    return out


def top_of(I):
    return max([float(np.nanmax(I["sink"][c] + I["se"][c])) for c in I["classes"]] or [0.0])


def draw_sinks(ax, I, top=None):
    top = top or top_of(I) or 1.0
    for c in sorted(I["classes"], reverse=True):
        col = COLS[c]
        sk, se = I["sink"][c] / top, I["se"][c] / top
        ax.fill_betweenx(I["dep"], np.maximum(sk - se, 0), sk + se, color=col, alpha=0.25, lw=0)
        ax.plot(sk, I["dep"], color=col, lw=0.9)
        ax.axvline(I["floor"][c] / top, color=col, lw=0.6, ls=(0, (2, 2)))
        x0 = 1.16 if c == 1 else 1.0
        for b_, y in enumerate(I["cen"][c]):
            if y is not None:
                ax.plot([x0, x0 + 0.12], [y, y], color=col, lw=1.4, solid_capstyle="butt", clip_on=False)
            else:
                ax.plot([x0, x0 + 0.12], [I["pkdep"][c][b_]] * 2, color=col, lw=1.4, alpha=0.3, solid_capstyle="butt", clip_on=False)
    ax.set_xlim(0, 1.05)
    ax.set_xticks([0])
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)


def band_lines(ax, I, word=False):
    for y in I["band"]:
        ax.axhline(y, color=INK, lw=0.5, ls=(0, (4, 2)), alpha=0.7)
    if word:
        ax.text(1.0, I["band"][0], "band ", transform=ax.get_yaxis_transform(), fontsize=FS_S - 0.5, ha="right", va="bottom", color=INK)


def sink_words(I):
    bits = []
    for b, nm in ((0, "upper blade"), (1, "lower blade")):
        if I["cen"][2][b] is None:
            bits.append("%s: DS2 sink under its noise floor" % nm)
        elif I["out"][b] is None:
            bits.append("%s: DS1 sink %.1f× its noise floor, under it" % (nm, I["clear"][b]))
        else:
            bits.append("%s: DS1 sink %.1f× its noise floor, centroid %d µm %s to DS2's" % (
                nm, I["clear"][b], abs(I["out"][b]), "distal" if I["out"][b] >= 0 else "proximal"))
    return "Sinks.  " + ";   ".join(bits) + "."


def row(fig, y0, d, num, title, sub, colr, ty, order_x, plane, heads, ext, badge=None, D3=None, extra=None):
    """One classification, in six columns. y0: the top of the row (mm)."""
    ax_mm = lambda x, y, w, h: G.ax_mm(fig, H, x, y, w, h)
    fig.add_artist(Rectangle((4 / W, 1 - (y0 + 5.4) / H), 1.2 / W, 5.4 / H, color=colr, lw=0, transform=fig.transFigure))
    fig.text(7 / W, 1 - (y0 + 1.6) / H, "%d   %s" % (num, title), fontsize=7.5, fontweight="bold", ha="left", va="center", color=colr)
    if badge:
        fig.text(179 / W, 1 - (y0 + 1.6) / H, badge, fontsize=6.5, fontweight="bold", ha="right", va="center", color="white",
                 bbox=dict(boxstyle="round,pad=0.35", fc="#1B7F4B", ec="none"))
        fig.add_artist(Rectangle((2.2 / W, 1 - (y0 + 66.0) / H), 0.8 / W, 66.0 / H, color="#1B7F4B", lw=0, transform=fig.transFigure))
    bs = blade_si(d, ty)
    if bs is not None:
        sub = sub.replace(".   DS1 ", " (upper blade %.2f, lower blade %.2f, mean %.2f).   DS1 " % (bs[0], bs[1], (bs[0] + bs[1]) / 2.0), 1)
    fig.text(7 / W, 1 - (y0 + 4.6) / H, sub, fontsize=FS_S, ha="left", va="center", color=INK)
    I = sinks_of(d, ty, ext)
    fig.text(7 / W, 1 - (y0 + 7.4) / H, sink_words(I), fontsize=FS_S, ha="left", va="center", color=MUTE)
    n = ty.size
    if not D3["ok"]:
        w3 = ("DS3.  Cannot be scored under this classification: DS1's and DS2's mean sinks peak at the same contact, so outer and middle "
              "cannot be told apart. That is not 'no DS3': the events are one type here.")
    else:
        k3 = int(D3["mask"].sum())
        w3 = "DS3.  %d events (%.0f%%) score within ±0.5 (layer contacts %d µm apart); %d unscorable events keep their type.   Without DS3: %s; DS1 %d, DS2 %d." % (
            k3, 100.0 * k3 / n, D3["gap"], D3["unsc"],
            "a type is left with under 5 events, no index" if D3["final"] is None else "separation index %.2f" % D3["final"], D3["n1"], D3["n2"])
    fig.text(7 / W, 1 - (y0 + 10.2) / H, w3, fontsize=FS_S, ha="left", va="center", color=C_DS3)
    if extra:
        fig.text(7 / W, 1 - (y0 + 13.0) / H, extra, fontsize=FS_S, ha="left", va="center", color=colr)
    top, hh = y0 + 23.5, 34.0
    X = PCA2[d["gid"]]["X"]
    t3 = D3["t3"]
    # 1 the PCA plane
    ax = ax_mm(10, top, 28, hh)
    ax.scatter(X[:, 0], X[:, 1], s=2.0, c=np.where(ty == 1, C_DS1, C_DS2), linewidth=0, alpha=0.8, rasterized=True)
    ax.set_xlim(X[:, 0].min(), X[:, 0].max())
    ax.set_ylim(X[:, 1].min(), X[:, 1].max())
    plane(ax, X)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel("PC1", fontsize=FS)
    ax.set_ylabel("PC2", fontsize=FS)
    # 2 every event: DS1, DS3, DS2
    rank = np.where(t3 == 1, 0, np.where(t3 == 3, 1, 2))
    o = np.lexsort((np.where(np.isfinite(order_x), order_x, np.nanmax(order_x)), rank))
    P = I["at0"][o]
    v = np.percentile(np.abs(I["at0"][:, I["inband"]]), 99)
    dep = I["dep"]
    ax = ax_mm(51, top, 38, hh)
    ax.set_facecolor("#DADADA")
    ax.imshow(np.ma.masked_invalid(P.T), aspect="auto", cmap=CSD_CMAP, vmin=-v, vmax=v, interpolation="nearest", extent=[0, P.shape[0], dep[-1] + 25, dep[0] - 25])
    n1, n3 = int((t3 == 1).sum()), int((t3 == 3).sum())
    for x_ in (n1, n1 + n3):
        if 0 < x_ < n:
            ax.axvline(x_, color=INK, lw=0.6)
    band_lines(ax, I, True)
    span = dep[-1] - dep[0] + 50
    for a, b, c in ((0, n1, C_DS1), (n1, n1 + n3, C_DS3), (n1 + n3, n, C_DS2)):
        if b > a:
            ax.add_patch(Rectangle((a, dep[0] - 25 - 0.045 * span), b - a, 0.03 * span, color=c, clip_on=False, lw=0))
    ax.set_xticks([0, n])
    ax.set_ylabel("Depth from band center (µm)", fontsize=FS)
    ax.set_xlabel("Events: DS1, DS3, DS2", fontsize=FS_S)
    # 3 the means
    ax = ax_mm(93, top, 17, hh)
    for c in (2, 1):
        ax.fill_betweenx(dep, I["mu"][c] - I["mse"][c], I["mu"][c] + I["mse"][c], color=COLS[c], alpha=0.25, lw=0)
        ax.plot(I["mu"][c], dep, color=COLS[c], lw=0.9)
    ax.axvline(0, color=HAIR, lw=0.5, zorder=0)
    band_lines(ax, I)
    ax.set_ylim(dep[-1] + 25, dep[0] - 25)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xticks([0])
    ax.set_xlabel("sink − 0 + source", fontsize=FS_S - 0.5)
    # 4-6 the sinks: as classified, DS3 alone, DS1 and DS2 without DS3
    I3 = sinks_of(d, t3, ext, (3,)) if D3["mask"].any() else None
    In = sinks_of(d, t3, ext, (1, 2)) if D3["mask"].any() else None
    tp = max([top_of(I)] + [top_of(k) for k in (I3, In) if k is not None]) or 1.0
    for x_, Ik, lab, none in ((114, I, "DS1 and DS2", None), (137, I3, "DS3", "no event scores as DS3" if D3["ok"] else "DS3 cannot be scored"),
                              (160, In, "DS1, DS2 without DS3", "same as the first" if D3["ok"] else "DS3 cannot be scored")):
        ax = ax_mm(x_, top, 15, hh)
        if Ik is None:
            ax.text(0.5, 0.5, chr(10).join(none.rsplit(" ", 2)[0:1] + [" ".join(none.rsplit(" ", 2)[1:])]), transform=ax.transAxes, ha="center", va="center", fontsize=FS_S, color=MUTE)
            ax.set_xticks([])
            ax.set_yticks([])
            ax.spines["left"].set_visible(False)
        else:
            draw_sinks(ax, Ik, tp)
            band_lines(ax, I)
        ax.set_ylim(dep[-1] + 25, dep[0] - 25)
        ax.set_xlabel(lab, fontsize=FS_S - 0.5, color=C_DS3 if lab == "DS3" else INK)
    if heads:
        for x, s_ in ((10, "PCA plane"), (51, "CSD at the DS peak, every event"), (93, "Mean CSD"), (114, "Mean sink ± s.e.m., one scale across the three")):
            fig.text(x / W, 1 - (top - 5.8) / H, s_, fontsize=FS, ha="left", va="center", color=INK)
        for x, s_, c in ((93, "DS1", C_DS1), (99.5, "DS2", C_DS2), (106, "DS3", C_DS3)):
            fig.text(x / W, 1 - (top - 2.3) / H, s_, fontsize=FS_S, fontweight="bold", color=c, ha="left", va="center")
    return I


def contour(ax, ft, key, col, lw, ls):
    if ft and key in ft:
        ax.contour(ft["gx"], ft["gy"], ft[key], levels=[0.5 if key == "P" else 0.0], colors=[col], linewidths=lw, linestyles=[ls])


def align(to, ty):
    """`to` with the names of `ty` (so the colors compare), and which
    events still differ."""
    if np.mean(to != ty) > 0.5:
        to = 3 - to
    return to, to != ty


def page(d):
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    ax_mm = lambda x, y, w, h: G.ax_mm(fig, H, x, y, w, h)
    head = "%s    %s%s    %d events    %.0f min" % (d["lab"], "Control" if d["g"] == "CTL" else "PTEN knockout",
                                                     "" if d["g"] == "CTL" else " %.1f%%" % d["ko"], d["n"], d["dur"] / 60.0)
    fig.text(4 / W, 1 - 5 / H, head, fontsize=9, fontweight="bold", ha="left", va="center", color=INK)
    fig.add_artist(Rectangle((4 / W, 1 - 9.2 / H), 175 / W, 0.9 / H, color=G.col_of(d), lw=0, transform=fig.transFigure))
    # a  the mean DS
    G.letter(fig, H, 2, 12, "a")
    ax = ax_mm(13, 19, 34, 48)
    G.draw_ds(ax, d, half=18, t_lim=40.0, lw=0.3, every=1)
    ax.set_xlabel("Time from DS peak (ms)", fontsize=FS)
    ax.set_ylabel("Depth from midpoint between" + chr(10) + "blade sinks (µm)", fontsize=FS)
    ax.set_title("Mean DS: CSD and LFP", fontsize=FS, loc="left", pad=3)
    if d["n"] < 20:
        fig.text(60 / W, 1 - 30 / H, "Too few events to classify.", fontsize=FS, ha="left", va="center", color=MUTE)
        return fig
    m, e = D2.best_si(d)
    ty = e["types"]
    Q, O = PCA2[d["gid"]], (OPT.get(d["gid"], {}).get("fits") or {})
    ext = extent(d, ty)
    # each row's classification, its DS3, and DS1 against DS2 without DS3
    cand_ = [(k, d["splits"][k]) for k in ON_PLANE if k in d["splits"] and "err" not in d["splits"][k] and d["splits"][k].get("si") is not None]
    ok_ = [c for c in cand_ if eligible(c[1], d["n"])]
    k2_, e2_ = max(ok_ or cand_, key=lambda c: c[1]["si"])
    oc_ = O.get("opt_curve") or {}
    D3s = {1: ds3_info(d, m, ty, e["si"]), 2: ds3_info(d, k2_, align(e2_["types"], ty)[0], e2_["si"] if eligible(e2_, d["n"]) else None)}
    if "types" in oc_:
        D3s[3] = ds3_info(d, "opt_curve", align(oc_["types"], ty)[0], oc_["si"])
    before = {1: e["si"], 2: e2_["si"] if eligible(e2_, d["n"]) else None, 3: oc_.get("si")}
    fin = {k: v["final"] for k, v in D3s.items()}
    live = [v for v in fin.values() if v is not None]
    win = [k for k, v in fin.items() if v is not None and v >= max(live) - 0.005] if live else []
    badge = lambda k: None if k not in win else ("FINAL OPTIMIZED SEPARATION" if len(win) == 1 else "FINAL OPTIMIZED SEPARATION (TIE: ROWS %s)" % (", ".join(str(x) for x in win[:-1]) + " AND %d" % win[-1]))
    f2 = lambda v: "none" if v is None else "%.2f" % v
    bits = ["row %d: %s to %s" % (k, f2(before[k]), f2(fin.get(k))) for k in (1, 2, 3)]
    fig.text(179 / W, 1 - 12.6 / H, "Separation index, as classified, then without DS3:     " + "     ".join(bits).replace(" to ", ", then "), fontsize=FS_S, ha="right", va="center", color=INK)
    # b  every classifier's index
    G.letter(fig, H, 56, 12, "b")
    ax = ax_mm(98, 19, 52, 48)
    for lo, hi, c in ((0, 0.2, "#F3F3F3"), (0.2, 0.45, "#E9E9E9"), (0.45, 1.0, "#DEDEDE")):
        ax.axvspan(lo, hi, color=c, lw=0, zorder=0)
    bases = list(NAMES)
    for i, b in enumerate(bases):
        for k, (suf, mk) in enumerate((("", "o"), ("_top", "^"), ("_bottom", "v"))):
            if suf and (b.startswith("pca_gmm") or b.startswith("opt_")):
                continue
            ee = d["splits"].get(b + suf, {}) if not b.startswith("opt_") else O.get(b, {"err": 1})
            if "err" in ee or ee.get("si") is None:
                continue
            opt = b.startswith("opt_")
            best = (b + suf) == m
            ax.scatter([ee["si"]], [i + (k - 1) * 0.24], s=30 if opt else (22 if best else 12), marker="*" if opt else mk,
                       color=PURPLE if opt else (INK if eligible(ee, d["n"]) else "white"),
                       edgecolor=PURPLE if opt else (RED if best else INK), linewidth=0.3 if opt else (1.0 if best else 0.5), zorder=3)
    ax.set_yticks(range(len(bases)))
    ax.set_yticklabels([NAMES[b] for b in bases], fontsize=FS_S)
    ax.set_ylim(len(bases) - 0.5, -0.5)
    ax.set_xlim(-0.02, 1)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("DS1–DS2 separation index", fontsize=FS)
    ax.set_title("Every classifier tried", fontsize=FS, loc="left", pad=3)
    for i, t in enumerate(("●  both sinks", "▲  upper sink", "▼  lower sink", "", "red ring: used (row 1)",
                           "open: a type under", "5% of events,", "not eligible", "", "purple star: optimized", "for the index (row 3)")):
        fig.text(154 / W, 1 - (22 + 3.3 * i) / H, t, fontsize=FS_S, ha="left", va="center", color=PURPLE if "purple" in t or "row 3" in t else MUTE)
    # row 1  the classifier used
    def plane1(ax, X):
        if m in ON_PLANE:
            if m == "pca":
                ax.axvline(Q["km_cut"], color=RED, lw=1.3)
            else:
                contour(ax, Q["fits"].get(m), "P", RED, 1.3, "-")
        else:
            ax.text(0.03, 0.97, "boundary not on this plane", transform=ax.transAxes, fontsize=FS_S, color=MUTE, ha="left", va="top")
    y = 76.0
    row(fig, y, d, 1, "Classifier used: %s" % full_name(m),
        "Separation index %.2f, %s.   DS1 %d events (%.0f%%), DS2 %d." % (e["si"], word(e["si"]), e["n1"], 100.0 * e["n1"] / d["n"], e["n2"]),
        RED, ty, np.asarray(e["x"], float), plane1, True, ext, badge(1), D3s[1])
    # row 2  conventional, on the PCA plane
    cand = [(k, d["splits"][k]) for k in ON_PLANE if k in d["splits"] and "err" not in d["splits"][k] and d["splits"][k].get("si") is not None]
    ok = [c for c in cand if eligible(c[1], d["n"])]
    k2, e2 = max(ok or cand, key=lambda c: c[1]["si"])
    t2, diff2 = align(e2["types"], ty)

    def plane2(ax, X):
        ax.axvline(Q["km_cut"], color=INK, lw=1.3 if k2 == "pca" else 0.6, ls=(0, (3, 2)))
        for key, ls in (("pca_gmm_line", "-"), ("pca_gmm_curve", (0, (1, 1.2)))):
            contour(ax, Q["fits"].get(key), "P", INK, 1.3 if k2 == key else 0.6, ls)
    st = (Q["fits"].get(k2) or {}).get("stable")
    y += 68.0
    row(fig, y, d, 2, "Conventional, on the PCA plane: %s%s" % (NAMES[k2], "  (this is the classifier used)" if k2 == m else ""),
        "Separation index %.2f, %s.   DS1 %d (%.0f%%), DS2 %d.%s%s   %d events (%.0f%%) differ from row 1." % (
            e2["si"], word(e2["si"]), int((t2 == 1).sum()), 100.0 * (t2 == 1).mean(), int((t2 == 2).sum()),
            "" if eligible(e2, d["n"]) else "   Not eligible: a type under 5%.",
            "" if st is None else "   %.0f%% of events keep their type on bootstrap refits." % (100 * st), int(diff2.sum()), 100.0 * diff2.mean()),
        INK, t2, Q["X"][:, 0], plane2, False, ext, badge(2), D3s[2])
    # row 3  optimized for the index
    oc = O.get("opt_curve") or {}
    y += 68.0
    if "types" in oc:
        t3, diff3 = align(oc["types"], ty)

        def plane3(ax, X):
            ax.scatter(X[diff3, 0], X[diff3, 1], s=8, facecolor="none", edgecolor=INK, linewidth=0.35, rasterized=True)
            contour(ax, O.get("opt_line"), "F", PURPLE, 0.7, "-")
            contour(ax, oc, "F", PURPLE, 1.3, (0, (1, 1.2)))
        extra4 = None
        f4 = (OPT2.get(d["gid"]) or {}).get("fit")
        if f4 is not None:
            same4 = max(np.mean(f4["types"] == oc["types"]), np.mean(f4["types"] != oc["types"]))
            extra4 = "Maximizing the mean of the upper-blade and lower-blade indices instead gives %s (mean %.2f, %.2f held out)." % (
                "the same boundary" if same4 > 0.999 else "nearly the same boundary, %.0f%% of events keeping their type" % (100 * same4), f4["mean"],
                f4["heldout"] if f4["heldout"] is not None else float("nan"))
        row(fig, y, d, 3, "Optimized for the separation index, on the PCA plane: curve",
            "Separation index %.2f (%s on held-out events), %s.   DS1 %d (%.0f%%), DS2 %d.   %d events (%.0f%%) differ from row 1 (ringed)." % (
                oc["si"], "%.2f" % oc["heldout"] if oc.get("heldout") is not None else "not measured", word(oc["si"]),
                int((t3 == 1).sum()), 100.0 * (t3 == 1).mean(), int((t3 == 2).sum()), int(diff3.sum()), 100.0 * diff3.mean()),
            PURPLE, t3, Q["X"][:, 0], plane3, False, ext, badge(3), D3s[3], extra4)
    else:
        fig.text(7 / W, 1 - (y + 4) / H, "3   Optimized for the separation index: no boundary leaves 5% of events in each type.", fontsize=7.5,
                 fontweight="bold", color=PURPLE, ha="left", va="center")
    row4(fig, 76.0 + 3 * 68.0, d)
    notes = [
        "Row 4.  Depth normalized by this recording's own landmarks (blue ticks: the two main sinks; red ticks: the source next to each). Gray band: mean ± s.e.m. of the recording's group; "
        "dashed: mean of the six separable recordings.",
        "Each row is one way of classifying the same events, drawn the same way. Colors: DS1 blue, DS2 orange, named as in row 1.",
        "Depth.  Dashed lines: the limits of the analyzed band (the contacts the classifiers saw). The range is widened 5 contacts past each "
        "limit, and further while a sink is still above its noise floor there; gray: a bad contact outside the band.",
        "PCA plane.  Row 1: the boundary used, in red, when it lies on this plane.  Row 2: dashed, k-means cut on PC1; solid, two-Gaussian mixture "
        "with a straight boundary; dotted, mixture with a curved boundary; thick, the one drawn in this row.",
        "    Row 3: boundaries chosen to maximize the separation index with each type 5% of events or more; thin solid, line; thick dotted, curve "
        "(drawn in this row). Held out: fitted on a random half of the events, scored on the other half (mean of 5).",
        "Sink amplitude.  Mean sink of each type on one scale. Dashed: the noise floor of each mean (99th percentile of the mean's |CSD| more "
        "than 30 ms from the DS peak, in the band).",
        "    Ticks at the right: sink centroid above the floor, over the widened range (DS2 inner column, DS1 outer). A faint tick: that sink is under its noise floor; the tick marks its peak.",
        "DS3.  An event whose relative sink, (outer − middle) / (outer + middle), is within ±0.5 (Tarcsay et al. 2025); the outer and middle "
        "molecular layer contacts are where DS1's and DS2's mean sinks peak in this row's classification.",
        "    Sink panels: DS1 and DS2 as classified; DS3 alone; DS1 and DS2 with the DS3 events taken out. One scale across the three.",
        "Green label and bar, FINAL OPTIMIZED SEPARATION: the row whose DS1 and DS2 have the highest separation index once DS3 is taken out "
        "(each type keeping 5 events or more).",
        "    Where DS3 is not measurable the row keeps its index as classified."]
    for i_, t_ in enumerate(notes):
        fig.text(4 / W, 1 - (352.0 + 3.3 * i_) / H, t_, fontsize=FS_S - 0.6, ha="left", va="center", color=MUTE)
    return fig


def row4(fig, y0, d):
    """This recording on the normalized axes, against its group."""
    r = RECS[d["lab"]]
    ax_mm = lambda x, y, w, h: G.ax_mm(fig, H, x, y, w, h)
    k = r.landmarks
    c = NC.curves(r)
    grp = GROUPS[r.group]
    fig.add_artist(Rectangle((4 / W, 1 - (y0 + 5.4) / H), 1.2 / W, 5.4 / H, color=G.col_of(d), lw=0, transform=fig.transFigure))
    fig.text(7 / W, 1 - (y0 + 1.6) / H, "4   Depth normalized: this recording against %s" % ("the controls" if r.group == "CTL" else "the PTEN recordings"),
             fontsize=7.5, fontweight="bold", ha="left", va="center", color=INK)
    fig.text(7 / W, 1 - (y0 + 4.6) / H, "Landmarks.  Main sinks %.0f µm apart; source to main sink %.0f µm (upper blade), %.0f µm (lower); %s." % (
        k["blade_um"], k["gcl_to_sink_upper_um"], k["gcl_to_sink_lower_um"],
        "one source between the blades" if k["source_gap_um"] < 60 else "two sources %.0f µm apart" % k["source_gap_um"]), fontsize=FS_S, ha="left", va="center")
    ty = c["typed"]
    if ty is not None and "ratio" in ty:
        fig.text(7 / W, 1 - (y0 + 7.4) / H, "DS1 against DS2 (%s).  DS1's sink sits at %.2f× (upper) and %.2f× (lower) DS2's distance from the source; its size is %.2f× and %.2f× DS2's." % (
            "separable" if r.separable() else "not separable, names arbitrary", ty["ratio"][0], ty["ratio"][1], ty["amp"][0], ty["amp"][1]),
            fontsize=FS_S, ha="left", va="center", color=MUTE)
    bits = []
    for blade in ("upper", "lower"):
        L = NC.literature_ds3(r, blade)
        bits.append("%s blade: the two quarters' sinks peak at the same contact, so the layers cannot be placed" % blade if L is None else
                    "%s blade: outer and middle contacts %d µm apart; DS1 %.0f%%, DS2 %.0f%%, DS3 %.0f%%, unscored %.0f%%" % (
                        blade, L["gap_um"], 100 * L["share"][1], 100 * L["share"][2], 100 * L["share"][3], 100 * L["share"][0]))
    fig.text(7 / W, 1 - (y0 + 10.2) / H, "DS3 by the paper's own procedure (Tarcsay et al. 2025: layers from the two extreme quarters of PC1).  " + bits[0] + ";",
             fontsize=FS_S, ha="left", va="center", color=C_DS3)
    fig.text(7 / W, 1 - (y0 + 13.0) / H, "    " + bits[1] + ".", fontsize=FS_S, ha="left", va="center", color=C_DS3)
    top, hh = y0 + 23.5, 34.0
    # 1 the landmarks on the raw depth axis
    ax = ax_mm(12, top, 26, hh)
    rows = np.arange(64)
    dep = r.depth_um(rows)
    ax.plot(r.mean_csd_peak, dep, color=INK, lw=0.9)
    ax.axvline(0, color=HAIR, lw=0.5, zorder=0)
    for key, col in (("U", C_DS1), ("L", C_DS1), ("GU", RED), ("GL", RED)):
        ax.plot([0.9, 1.0], [r.depth_um(k[key])] * 2, color=col, lw=1.6, transform=ax.get_yaxis_transform(), clip_on=False, solid_capstyle="butt")
    a_, b_ = r.band
    for y in (r.depth_um(a_) - 25, r.depth_um(b_) + 25):
        ax.axhline(y, color=INK, lw=0.5, ls=(0, (4, 2)), alpha=0.7)
    lo, hi = r.depth_um(max(0, a_ - 6)), r.depth_um(min(63, b_ + 6))
    ax.set_ylim(hi, lo)
    ax.set_xticks([0])
    ax.set_ylabel("Depth from band center (µm)", fontsize=FS)
    ax.set_xlabel("Mean CSD at the peak", fontsize=FS_S)
    # 2 blade to blade
    ax = ax_mm(50, top, 24, hh)
    Y = np.array([NC.curves(x)["prof_u"] for x in grp])
    mu, se = np.nanmean(Y, axis=0), np.nanstd(Y, axis=0) / np.sqrt(np.isfinite(Y).sum(axis=0).clip(1))
    ax.fill_betweenx(NC.GRID_U, mu - se, mu + se, color="#BDBDBD", lw=0, alpha=0.8)
    ax.plot(c["prof_u"], NC.GRID_U, color=G.col_of(d), lw=1.1)
    ax.axvline(0, color=HAIR, lw=0.5, zorder=0)
    ax.set_ylim(NC.GRID_U[-1], NC.GRID_U[0])
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["upper" + chr(10) + "sink", "lower" + chr(10) + "sink"], fontsize=FS_S - 0.5)
    ax.set_xticks([-1, 0, 1])
    ax.set_xlabel("CSD (1 = main sinks)", fontsize=FS_S)
    # 3 folded, all events
    ax = ax_mm(93, top, 38, hh)
    Y = np.array([NC.curves(x)["fold"] for x in grp])
    mu, se = np.nanmean(Y, axis=0), np.nanstd(Y, axis=0) / np.sqrt(np.isfinite(Y).sum(axis=0).clip(1))
    ax.fill_between(NC.GRID_V, mu - se, mu + se, color="#BDBDBD", lw=0, alpha=0.8)
    ax.plot(NC.GRID_V, c["fold"], color=G.col_of(d), lw=1.1)
    for x_ in (0, 1):
        ax.axvline(x_, color=HAIR, lw=0.5, zorder=0)
    ax.axhline(0, color=HAIR, lw=0.5, zorder=0)
    ax.set_xlim(-0.5, 2.6)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["source", "main sink", "2x out"], fontsize=FS_S)
    ax.set_ylabel("CSD (−1 = main sink)", fontsize=FS_S)
    ax.set_xlabel("All events, blades folded", fontsize=FS_S)
    # 4 folded, DS1 and DS2
    ax = ax_mm(143, top, 36, hh)
    for c_, col in ((2, C_DS2), (1, C_DS1)):
        Y = np.array([NC.curves(x)["typed"]["fold"][c_] for x in SEP])
        ax.plot(NC.GRID_V, np.nanmean(Y, axis=0), color=col, lw=0.7, ls=(0, (3, 2)), alpha=0.8)
        if ty is not None and c_ in ty["fold"]:
            ax.plot(NC.GRID_V, ty["fold"][c_], color=col, lw=1.1)
    for x_ in (0, 1):
        ax.axvline(x_, color=HAIR, lw=0.5, zorder=0)
    ax.axhline(0, color=HAIR, lw=0.5, zorder=0)
    ax.set_xlim(-0.5, 2.6)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["source", "main sink", "2x out"], fontsize=FS_S)
    ax.set_ylabel("CSD (−1 = DS2's sink)", fontsize=FS_S)
    ax.set_xlabel("DS1 and DS2, blades folded", fontsize=FS_S)
    for x, s_ in ((12, "Landmarks"), (50, "Blade to blade"), (93, "Within a blade"), (143, "Within a blade, by type")):
        fig.text(x / W, 1 - (top - 3.5) / H, s_, fontsize=FS, ha="left", va="center", color=INK)


order = [d for d in recs if d["g"] == "CTL"] + sorted([d for d in recs if d["g"] == "PTEN"], key=lambda d: d["ko"])
only = [a for a in sys.argv[1:]]
with PdfPages(os.path.join(OUT, "DS1_DS2_classification_all_recordings.pdf" if not only else "_test.pdf")) as pdf:
    for i, d in enumerate(order):
        if only and d["lab"] not in only:
            continue
        fig = page(d)
        pdf.savefig(fig)
        fig.savefig(os.path.join(OUT, "%02d_%s_%s.png" % (i + 1, d["lab"], "control" if d["g"] == "CTL" else "PTEN")), dpi=220)
        plt.close(fig)
        print(d["lab"], flush=True)
print("saved to", OUT)
