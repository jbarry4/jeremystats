"""Three figures in the house Nature style (PDF vector + PNG 300 dpi):
1 the atlas, 2 the two families and the hybrids, 3 PTEN against control."""
import os
import pickle
import sys
import warnings

warnings.filterwarnings("ignore")
APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
sys.path.insert(0, APP)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
from scipy import stats as st  # noqa: E402
from backend import joefigs as JG  # noqa: E402
import deep_stats as DS  # noqa: E402
import deep_stats2 as D2  # noqa: E402

plt = JG._plt()
from matplotlib.colors import LinearSegmentedColormap, Normalize  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

UNC = "--uncorrected" in sys.argv
OUT = r"c:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16" + ("\\uncorrected" if UNC else "")
os.makedirs(OUT, exist_ok=True)
recs = pickle.load(open(os.path.join(HERE, "deep_v6.pkl"), "rb"))
full = pickle.load(open(os.path.join(HERE, "deep_full_v6.pkl"), "rb"))
FIN = pickle.load(open(os.path.join(HERE, "deep_final.pkl"), "rb"))
M = {m["lab"]: m for m in FIN[6]["M"]}
W = 183.0
INK, MUTE, HAIR = "#1A1A1A", "#6B6B6B", "#C9C9C9"
C_CTL = "#5A6470"
C_DS1, C_DS2, C_DS3 = "#0072B2", "#D55E00", "#009E73"
KO_CMAP = LinearSegmentedColormap.from_list("ko", ["#F6C99B", "#E2711D", "#8E2A0B"])
KO_NORM = Normalize(0, 30)
CSD_CMAP = LinearSegmentedColormap.from_list("csd", ["#0B3C7A", "#2F79B9", "#A9CCE6", "#FAFAFA", "#F0B49A", "#CC4B37", "#7A0F1C"])
FS, FS_S, FS_L = 6.5, 5.5, 8.0


def col_of(d):
    return C_CTL if d["g"] == "CTL" else KO_CMAP(KO_NORM(d["ko"]))


def ax_mm(fig, H, x, y, w, h, **kw):
    return JG._ax(fig, x, y, w, h, H, W, **kw)


def letter(fig, H, x, y, s):
    JG._letter(fig, x, y, s, H, W)


def bare(ax):
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])


def save(fig, stem):
    if UNC:
        stem += "_UNCORRECTED"
        fig.text(0.995, 0.993, "UNCORRECTED", fontsize=8, fontweight="bold", color="#B5361F", ha="right", va="top")
    for ext, kw in ((".pdf", {}), (".png", {"dpi": 300})):
        fig.savefig(os.path.join(OUT, stem + ext), **kw)
    plt.close(fig)


def window(d, half=18):
    """The recording's mean DS (CSD, LFP) on rows centred between its two
    blade sinks: (csd, lfp, s1, s2) with rows -half..half about the middle."""
    F = full[d["gid"]]
    g = D2.geometry(d, F)
    s1, s2, _ = g
    mid = int(round((s1 + s2) / 2.0))
    rows = np.arange(mid - half, mid + half + 1)
    n_r = F["csd_mean"].shape[0]
    ok = (rows >= 0) & (rows < n_r)
    csd = np.full((rows.size, F["csd_mean"].shape[1]), np.nan)
    csd[ok] = F["csd_mean"][rows[ok]]
    nl = F["nums_lfp"]
    lfp = np.full_like(csd, np.nan)
    for i, r in enumerate(rows):
        if 0 <= r < n_r and F["nums_all"][r] in nl:
            lfp[i] = F["lfp_mean"][nl.index(F["nums_all"][r])]
    return csd, lfp, s1 - mid, s2 - mid


def draw_ds(ax, d, half=18, t_lim=25.0, traces=True, lw=0.3, every=2):
    csd, lfp, a, b = window(d, half)
    tt = full[d["gid"]]["tt"]
    v = np.nanpercentile(np.abs(csd[:, np.abs(tt) <= t_lim]), 99.7)
    ax.set_facecolor("#EDEDED")
    ax.imshow(csd, aspect="auto", cmap=CSD_CMAP, vmin=-v, vmax=v, interpolation="bicubic",
              extent=[tt[0], tt[-1], (half + 0.5) * 50, -(half + 0.5) * 50])
    if traces:
        sc = 110.0 / np.nanmax(np.abs(lfp))
        for i in range(0, lfp.shape[0], every):
            if np.isfinite(lfp[i]).all():
                ax.plot(tt, (i - half) * 50.0 - lfp[i] * sc, color=INK, lw=lw, alpha=0.75, solid_capstyle="round")
    ax.set_xlim(-t_lim, t_lim)
    ax.set_ylim((half + 0.5) * 50, -(half + 0.5) * 50)
    return a * 50.0, b * 50.0


# ───────────────────────── Figure 1: the atlas ─────────────────────────
def figure1():
    H = 116.0
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    ex = next(d for d in recs if d["lab"] == "m60")
    letter(fig, H, 2, 2, "a")
    ax = ax_mm(fig, H, 12, 9, 44, 92)
    ya, yb = draw_ds(ax, ex, half=18, t_lim=40.0, lw=0.4, every=1)
    ax.set_xlabel("Time from dentate spike (ms)", fontsize=FS)
    ax.set_ylabel("Depth from midpoint between blade sinks (µm)", fontsize=FS)
    ax.set_yticks([-800, -400, 0, 400, 800])
    ax.set_xticks([-40, -20, 0, 20, 40])
    for y, s in ((ya, "Sink\nupper blade"), (0.5 * (ya + yb) - 120, "Source\ngranule cell layer"), (yb, "Sink\nlower blade")):
        ax.annotate(s, xy=(41, y), xytext=(47, y), fontsize=FS_S, va="center", ha="left", annotation_clip=False, color=INK,
                    arrowprops=dict(arrowstyle="-", lw=0.4, color=MUTE, shrinkA=0, shrinkB=0))
    ax.set_title("Control mouse m60, mean of %d events" % ex["n"], fontsize=FS, pad=3, loc="left")
    cax = ax_mm(fig, H, 24, 111, 20, 1.6)
    cax.imshow(np.linspace(-1, 1, 200)[None, :], aspect="auto", cmap=CSD_CMAP, extent=[-1, 1, 0, 1])
    bare(cax)
    fig.text((24 - 0.8) / W, 1 - 111.8 / H, "sink", fontsize=FS_S, ha="right", va="center", color=MUTE)
    fig.text((44 + 0.8) / W, 1 - 111.8 / H, "source", fontsize=FS_S, ha="left", va="center", color=MUTE)
    # the gallery
    letter(fig, H, 74, 2, "b")
    order = [[d for d in recs if d["g"] == "CTL"], sorted([d for d in recs if d["g"] == "PTEN"], key=lambda d: d["ko"])]
    x0, pw, ph, gx = 82.0, 9.4, 40.0, 1.5
    for ri, row in enumerate(order):
        y0 = 13.0 + ri * (ph + 13.5)
        fig.text(x0 / W, 1 - (y0 - 8.0) / H, "Control" if ri == 0 else "PTEN knockout, ordered by % of granule cells with knockout",
                 fontsize=FS, va="center", ha="left", color=INK, fontweight="bold")
        for ci, d in enumerate(row):
            a = ax_mm(fig, H, x0 + ci * (pw + gx), y0, pw, ph)
            draw_ds(a, d, half=18, t_lim=20.0, lw=0.22, every=2)
            bare(a)
            a.add_patch(Rectangle((0, 1.012), 1, 0.022, transform=a.transAxes, color=col_of(d), clip_on=False, lw=0))
            a.text(0.5, 1.05, d["lab"] if ri == 0 else "%s  %.0f%%" % (d["lab"], d["ko"]), transform=a.transAxes, ha="center",
                   va="bottom", fontsize=FS_S, color=INK)
            a.text(0.5, -0.03 if not (ri == 1 and ci == 0) else -0.085, "n = %d" % d["n"], transform=a.transAxes, ha="center", va="top", fontsize=FS_S - 0.5, color=MUTE)
            if ri == 1 and ci == 0:
                a.plot([-20, -10], [985, 985], color=INK, lw=0.8, clip_on=False)
                a.text(-8.5, 985, "10 ms", ha="left", va="center", fontsize=FS_S - 0.5, clip_on=False)
                a.plot([-23.5, -23.5], [925, 525], color=INK, lw=0.8, clip_on=False)
                a.text(-25.5, 725, "400 µm", ha="right", va="center", fontsize=FS_S - 0.5, rotation=90, clip_on=False)
    save(fig, "Fig1_dentate_spike_atlas")


# ─────────────────── Figure 2: two families, and the hybrids ───────────────────
def raster(fig, H, x, y, d, title):
    m, e = D2.best_si(d)
    xs = np.asarray(e["x"], float)
    ty = e["types"]
    # DS1 on top, each class in the split's own order
    o = np.lexsort((np.where(np.isfinite(xs), xs, np.nanmax(xs)), ty))
    P = d["prof"][o]
    v = np.percentile(np.abs(P), 99)
    ax = ax_mm(fig, H, x, y, 30, 40)
    dep = (np.arange(P.shape[1]) - (P.shape[1] - 1) / 2.0) * 50.0
    ax.imshow(P.T, aspect="auto", cmap=CSD_CMAP, vmin=-v, vmax=v, interpolation="nearest",
              extent=[0, P.shape[0], dep[-1] + 25, dep[0] - 25])
    n1 = int((ty == 1).sum())
    ax.axvline(n1, color=INK, lw=0.6)
    ax.set_xlabel("Events, sorted by score", fontsize=FS)
    ax.set_ylabel("Depth in the dentate (µm)", fontsize=FS)
    ax.set_xticks([0, P.shape[0]])
    ax.set_title("%s (index %.2f)" % (title, e["si"]), fontsize=FS, loc="left", pad=9)
    for (a, b, c, s) in ((0, n1, C_DS1, "DS1"), (n1, P.shape[0], C_DS2, "DS2")):
        ax.add_patch(Rectangle((a, dep[0] - 25 - 0.045 * (dep[-1] - dep[0] + 50)), b - a, 0.03 * (dep[-1] - dep[0] + 50), color=c,
                               clip_on=False, lw=0))
    ax2 = ax_mm(fig, H, x + 32, y, 11, 40)
    for c, col in ((1, C_DS1), (2, C_DS2)):
        mu = d["prof"][ty == c].mean(axis=0)
        sd = d["prof"][ty == c].std(axis=0) / np.sqrt(max((ty == c).sum(), 1))
        ax2.fill_betweenx(dep, mu - sd, mu + sd, color=col, alpha=0.25, lw=0)
        ax2.plot(mu, dep, color=col, lw=0.9)
    ax2.axvline(0, color=HAIR, lw=0.5, zorder=0)
    ax2.set_ylim(dep[-1] + 25, dep[0] - 25)
    ax2.set_yticks([])
    ax2.spines["left"].set_visible(False)
    ax2.set_xticks([0])
    ax2.set_xticklabels(["0"])
    ax2.set_xlabel("Mean CSD", fontsize=FS)
    ax2.text(0.02, 1.02, "sink", transform=ax2.transAxes, fontsize=FS_S, color=MUTE, ha="left", va="bottom")
    ax2.text(0.98, 1.02, "source", transform=ax2.transAxes, fontsize=FS_S, color=MUTE, ha="right", va="bottom")


def figure2():
    H = 128.0
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    by = {d["lab"]: d for d in recs}
    letter(fig, H, 2, 2, "a")
    raster(fig, H, 13, 12, by["m61"], "DS1 and DS2 separable: control m61")
    letter(fig, H, 66, 2, "b")
    raster(fig, H, 77, 12, by["m60"], "Not separable: control m60")
    # c  how well the best split parts each recording
    letter(fig, H, 130, 2, "c")
    ax = ax_mm(fig, H, 141, 12, 38, 40)
    rows = sorted([d for d in recs if d["n"] >= DS.MIN_N], key=lambda d: D2.best_si(d)[1]["si"])
    for lo, hi, s, c in ((0, 0.2, "not sep.", "#F3F3F3"), (0.2, 0.45, "partial", "#E9E9E9"), (0.45, 1.0, "separable", "#DEDEDE")):
        ax.axvspan(lo, hi, color=c, lw=0, zorder=0)
        ax.text((lo + hi) / 2, len(rows) - 0.25, s, fontsize=FS_S, ha="center", va="bottom", color=MUTE)
    for i, d in enumerate(rows):
        si = D2.best_si(d)[1]["si"]
        ax.plot([0, si], [i, i], color=col_of(d), lw=0.8, solid_capstyle="round")
        ax.scatter([si], [i], s=13, color=col_of(d), edgecolor="white", linewidth=0.4, zorder=3)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([d["lab"] for d in rows], fontsize=FS_S)
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.7, len(rows) + 0.6)
    ax.set_xlabel("DS1–DS2 separation index\n(1 = no overlap between DS1 and DS2)", fontsize=FS)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    # d  the hybrid share against how far apart the two layers were placed
    letter(fig, H, 2, 68, "d")
    ax = ax_mm(fig, H, 13, 80, 42, 36)
    rng = np.random.default_rng(2)
    gx, gy = [], []
    for d in recs:
        if d["n"] < DS.MIN_N:
            continue
        for m, e in d["splits"].items():
            if "err" in e or e.get("why") or min(e["n1"], e["n2"]) < 5:
                continue
            sc = e["score"]
            okk = np.isfinite(sc)
            gx.append(abs(e["oml"] - e["mml"]) * 50.0)
            gy.append(100.0 * (np.abs(sc[okk]) <= 0.5).sum() / d["n"])
    gx, gy = np.array(gx), np.array(gy)
    ax.scatter(gx + rng.uniform(-13, 13, gx.size), gy, s=5, color=C_DS3, alpha=0.45, linewidth=0, zorder=2)
    ux = np.array(sorted(set(gx)))
    med = np.array([np.median(gy[gx == u]) for u in ux])
    keep = np.array([(gx == u).sum() >= 4 for u in ux])
    ax.plot(ux[keep], med[keep], color=INK, lw=0.9, marker="o", ms=2.6, mfc="white", mew=0.7, zorder=3)
    ax.axhline(27, color=MUTE, lw=0.5, ls=(0, (3, 2)))
    ax.text(340, 29, "about 27% in\nTarcsay et al. 2025", fontsize=FS_S, color=MUTE, ha="right", va="bottom", linespacing=1.2)
    ax.set_xlabel("Distance between the outer and middle\nmolecular layer contacts (µm)", fontsize=FS)
    ax.set_ylabel("Events classified as DS3 (%)", fontsize=FS)
    ax.set_ylim(-3, 103)
    ax.set_xlim(0, 350)
    ax.set_xticks([0, 100, 200, 300])
    ax.text(0.98, 0.97, "dot: one recording, one classifier\nline: median", transform=ax.transAxes, fontsize=FS_S, ha="right", va="top",
            color=MUTE)
    # e  DS1 and DS2 sinks on one scale, in the separable recordings
    letter(fig, H, 66, 68, "e")
    use = [d for d in recs if d["n"] >= DS.MIN_N]
    res = sorted([d for d in use if D2.best_si(d)[1]["si"] >= 0.45], key=lambda d: (d["g"] != "CTL", d["ko"]))
    fig.text(77.0 / W, 1 - 71.5 / H, "DS1 and DS2 sink amplitude by depth in the six separable recordings", fontsize=FS, ha="left", va="center")
    info = {d["lab"]: families(d) for d in use}
    for i, d in enumerate(res):
        ax = ax_mm(fig, H, 78 + i * 11.4, 80, 10.0, 36)
        draw_sinks(ax, info[d["lab"]], first=(i == 0))
        ax.set_ylim(525, -525)
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        ax.add_patch(Rectangle((0, 1.012), 1, 0.022, transform=ax.transAxes, color=col_of(d), clip_on=False, lw=0))
        ax.text(0.5, 1.05, d["lab"], transform=ax.transAxes, ha="center", va="bottom", fontsize=FS_S)
        ax.text(0.5, -0.02, "DS1 %.0f%%" % info[d["lab"]]["share"], transform=ax.transAxes, ha="center", va="top", fontsize=FS_S, color=C_DS1)
    fig.text(78.0 / W, 1 - 124.0 / H, "DS1", fontsize=FS_S, color=C_DS1, fontweight="bold", ha="left", va="center")
    fig.text(84.0 / W, 1 - 124.0 / H, "DS2", fontsize=FS_S, color=C_DS2, fontweight="bold", ha="left", va="center")
    fig.text(90.5 / W, 1 - 124.0 / H, "mean sink ± s.e.m., one scale per recording;" + chr(10) + "dashed: noise floor of each mean", fontsize=FS_S,
             color=MUTE, ha="left", va="center", linespacing=1.2)
    # f  does DS1's sink clear its noise floor
    letter(fig, H, 149, 68, "f")
    ax = ax_mm(fig, H, 160, 80, 20, 36)
    rng = np.random.default_rng(5)
    grp = [[d for d in use if D2.best_si(d)[1]["si"] >= 0.45], [d for d in use if D2.best_si(d)[1]["si"] < 0.45]]
    vals = []
    ax.axhline(1, color=MUTE, lw=0.5, ls=(0, (3, 2)), zorder=0)
    for k, g in enumerate(grp):
        v = np.array([max(info[d["lab"]]["clear"]) for d in g])
        vals.append(v)
        ax.scatter(k + rng.uniform(-0.16, 0.16, v.size), v, s=13, c=[col_of(d) for d in g], edgecolor="white", linewidth=0.4, zorder=3)
        ax.plot([k - 0.28, k + 0.28], [np.median(v)] * 2, color=INK, lw=1.0, zorder=4)
    ax.set_yscale("log")
    ax.set_yticks([1, 2, 4, 8])
    ax.set_yticklabels(["1", "2", "4", "8"])
    ax.minorticks_off()
    ax.set_ylim(0.4, 9)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Yes" + chr(10) + "(n = %d)" % len(grp[0]), "No" + chr(10) + "(n = %d)" % len(grp[1])], fontsize=FS_S)
    ax.set_xlabel("DS1 and DS2" + chr(10) + "separable", fontsize=FS)
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylabel("DS1 peak sink / noise floor", fontsize=FS)
    save(fig, "Fig2_DS1_DS2_DS3_classification")
    R = [info[d["lab"]] for d in res]
    return {"resolved": [(d["lab"], d["g"], round(I["share"], 1), [round(x, 2) for x in I["clear"]], I["out"], round(I["amp"], 2)) for d, I in zip(res, R)],
            "clear_res": float(np.median(vals[0])), "clear_not": float(np.median(vals[1]))}


def families(d):
    """DS1 and DS2 under the best classifier, in the analysed band, on one
    absolute scale: the mean sink (max(0, -CSD) of the type's mean) and its
    s.e.m. by depth; each mean's noise floor (the 99th percentile of the
    mean's |CSD| more than 30 ms from the DS); per blade, DS1's peak sink
    over its floor, each type's sink centroid above its floor, and the
    offset (DS1 distal to DS2, um) only where both clear their floors."""
    F = full[d["gid"]]
    e = D2.best_si(d)[1]
    ty = e["types"]
    na = F["nums_all"]
    sel = [na.index(x) for x in d["ns"]]
    ev = F["csd_ev"][:, sel, :].astype(float)
    tt = F["tt"]
    at0 = ev[:, :, np.abs(tt) <= 3.0].mean(axis=2)
    base = np.abs(tt) > 30
    nb = len(sel)
    hc = d["hump_cut"]
    out = {"dep": (np.arange(nb) - (nb - 1) / 2.0) * 50.0, "sink": {}, "se": {}, "floor": {}, "cen": {}, "peak": {},
           "share": 100.0 * float((ty == 1).mean()), "n": {c: int((ty == c).sum()) for c in (1, 2)}}
    for c in (1, 2):
        mu = at0[ty == c].mean(axis=0)
        out["sink"][c] = np.maximum(-mu, 0.0)
        out["se"][c] = at0[ty == c].std(axis=0) / np.sqrt(max((ty == c).sum(), 1))
        out["floor"][c] = float(np.percentile(np.abs(ev[ty == c].mean(axis=0)[:, base]), 99))
        cs, pk = [], []
        for lo, hi in ((0, hc), (hc, nb)):
            sk = out["sink"][c][lo:hi]
            pk.append(float(sk.max()))
            w = np.maximum(sk - out["floor"][c], 0.0)
            cs.append(float((w * out["dep"][lo:hi]).sum() / w.sum()) if w.sum() > 0 else None)
        out["cen"][c], out["peak"][c] = cs, pk
    out["clear"] = [out["peak"][1][b] / max(out["floor"][1], 1e-12) for b in (0, 1)]
    out["out"] = [None if out["cen"][1][b] is None or out["cen"][2][b] is None
                  else round((out["cen"][2][b] - out["cen"][1][b]) * (1 if b == 0 else -1)) for b in (0, 1)]
    out["amp"] = max(out["peak"][1]) / max(out["peak"][2])
    return out


def draw_sinks(ax, I, first=True):
    """Both types' mean sink by depth, one scale, with s.e.m. and floors."""
    top = max(float((I["sink"][c] + I["se"][c]).max()) for c in (1, 2))
    for c, col in ((2, C_DS2), (1, C_DS1)):
        sk, se = I["sink"][c] / top, I["se"][c] / top
        ax.fill_betweenx(I["dep"], np.maximum(sk - se, 0), sk + se, color=col, alpha=0.25, lw=0)
        ax.plot(sk, I["dep"], color=col, lw=0.9)
        ax.axvline(I["floor"][c] / top, color=col, lw=0.6, ls=(0, (2, 2)))
        for y in I["cen"][c]:
            if y is not None:
                ax.plot([1.0, 1.1], [y, y], color=col, lw=1.4, solid_capstyle="butt", clip_on=False)
    ax.set_xlim(0, 1.05)
    ax.set_ylim(I["dep"][-1] + 25, I["dep"][0] - 25)
    ax.set_xticks([0])
    if not first:
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
    else:
        ax.set_ylabel("Depth in the analysed band (µm)", fontsize=FS)


# ───────────────────────── Figure 3: PTEN against control ─────────────────────────
def profile(d, u):
    F = full[d["gid"]]
    s1, s2, _ = D2.geometry(d, F)
    m = F["csd_at0"].mean(axis=0)
    sk = (-m[s1] - m[s2]) / 2.0
    pos = (np.arange(m.size) - s1) / float(s2 - s1)
    return np.interp(u, pos, m / sk, left=np.nan, right=np.nan)


def figure3():
    H = 140.0
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    rows = D2.rename(FIN[6]["rows"])
    n = len(rows)
    yy = np.arange(n)[::-1]
    letter(fig, H, 2, 2, "a")
    for pi, (key, ci, pk, title, xl) in enumerate((("rb", "rb_ci", "p_group", "PTEN against control",
                                                   "Rank-biserial correlation\n(− lower in PTEN, + higher)"),
                                                  ("rho", "rho_ci", "p_dose", "Correlation with % knockout, PTEN only",
                                                   "Spearman ρ"))):
        ax = ax_mm(fig, H, 50 + pi * 46, 11, 40, 58)
        ax.axvline(0, color=HAIR, lw=0.6, zorder=0)
        for i, r in enumerate(rows):
            lead = r["key"] in ("src_net",)
            c = "#B5361F" if lead else INK
            ax.plot(r[ci], [yy[i]] * 2, color=c, lw=0.8, solid_capstyle="round", alpha=0.9)
            ax.scatter([r[key]], [yy[i]], s=15, color=c if r[pk] < 0.05 else "white", edgecolor=c, linewidth=0.7, zorder=3)
        ax.set_xlim(-1.08, 1.08)
        ax.set_ylim(-0.7, n - 0.3)
        ax.set_xticks([-1, -0.5, 0, 0.5, 1])
        ax.set_xlabel(xl, fontsize=FS)
        ax.set_title(title, fontsize=FS, loc="left", pad=4)
        if pi == 0:
            ax.set_yticks(yy)
            ax.set_yticklabels([r["name"] for r in rows], fontsize=FS_S)
            for tl, r in zip(ax.get_yticklabels(), rows):
                if r["key"] == "src_net":
                    tl.set_color("#B5361F")
        else:
            ax.set_yticks([])
        ax.tick_params(axis="y", length=0)
        ax.spines["left"].set_visible(False)
    axl = ax_mm(fig, H, 143, 11, 38, 58)
    bare(axl)
    axl.set_xlim(0, 1)
    axl.set_ylim(0, 1)
    axl.scatter([0.04], [0.93], s=15, color=INK, edgecolor=INK, linewidth=0.7)
    axl.text(0.11, 0.93, "P < 0.05, uncorrected", fontsize=FS_S, va="center")
    axl.scatter([0.04], [0.86], s=15, color="white", edgecolor=INK, linewidth=0.7)
    axl.text(0.11, 0.86, "P ≥ 0.05", fontsize=FS_S, va="center")
    axl.plot([0.0, 0.08], [0.79, 0.79], color=INK, lw=0.8)
    axl.text(0.11, 0.79, "95% bootstrap interval", fontsize=FS_S, va="center")
    qmin = min(min(r["q_group"], r["q_dose"]) for r in rows)
    axl.text(0.0, 0.66, ("One recording per mouse.\nControl n = 8, PTEN n = 9.\n\nRaw P values: no correction\nfor the %d tests shown." % (2 * n)) if UNC else "One recording per mouse.\nControl n = 8, PTEN n = 9.\n\nBenjamini–Hochberg correction\nover these %d tests:\nsmallest q = %.2f." % (2 * n, qmin),
             fontsize=FS_S, va="top", color=MUTE, linespacing=1.35)
    # b  the mean DS between the blades, by group
    letter(fig, H, 2, 84, "b")
    ax = ax_mm(fig, H, 13, 97, 44, 32)
    u = np.linspace(-0.35, 1.35, 171)
    use = [d for d in recs if d["n"] >= DS.MIN_N]
    groups = (("Control", [d for d in use if d["g"] == "CTL"], C_CTL),
              ("PTEN, under 10%", [d for d in use if d["g"] == "PTEN" and d["ko"] < 10], KO_CMAP(0.12)),
              ("PTEN, 15% and over", [d for d in use if d["g"] == "PTEN" and d["ko"] >= 15], KO_CMAP(0.9)))
    ax.axhline(0, color=HAIR, lw=0.5, zorder=0)
    ax.axvspan(0.2, 0.8, color="#F4F4F4", lw=0, zorder=0)
    for name, ds, c in groups:
        P = np.array([profile(d, u) for d in ds])
        mu = np.nanmean(P, axis=0)
        se = np.nanstd(P, axis=0) / np.sqrt(np.isfinite(P).sum(axis=0))
        ax.fill_between(u, mu - se, mu + se, color=c, alpha=0.22, lw=0)
        ax.plot(u, mu, color=c, lw=1.0, label="%s (n = %d)" % (name, len(ds)))
    ax.set_xticks([0, 0.5, 1])
    ax.set_xticklabels(["upper\nblade sink", "granule cell\nlayers, hilus", "lower\nblade sink"], fontsize=FS_S)
    ax.set_ylabel("CSD at the DS peak\n(normalised to mean sink amplitude)", fontsize=FS)
    ax.set_yticks([-1, 0, 1])
    ax.text(0.5, 1.0, "source", transform=ax.transAxes, fontsize=FS_S, color=MUTE, ha="center", va="top")
    ax.legend(fontsize=FS_S, frameon=False, loc="lower left", bbox_to_anchor=(-0.02, 1.0), ncol=1, handlelength=1.2, borderaxespad=0.1,
              labelspacing=0.25)
    # c  the lead, per mouse
    letter(fig, H, 64, 84, "c")
    ax = ax_mm(fig, H, 78, 97, 40, 32)
    rng = np.random.default_rng(4)
    xs = np.array([d["ko"] if d["g"] == "PTEN" else rng.uniform(-1.6, 1.6) for d in use])
    ys = np.array([M[d["lab"]]["src_net"] for d in use])
    ax.axhline(0, color=HAIR, lw=0.5, zorder=0)
    ax.scatter(xs, ys, s=17, c=[col_of(d) for d in use], edgecolor="white", linewidth=0.4, zorder=3)
    ko = np.array([d["ko"] for d in use])
    ra = st.spearmanr(ko, ys)
    pt = np.array([d["g"] == "PTEN" for d in use])
    rp = st.spearmanr(ko[pt], ys[pt])
    ax.set_xlabel("PTEN knockout (% of granule cells)", fontsize=FS)
    ax.set_ylabel("Mean CSD between blade sinks\n(normalised to sink amplitude)", fontsize=FS)
    ax.set_xticks([0, 10, 20, 30])
    ax.set_xticklabels(["Control", "10", "20", "30"])
    ax.text(0.98, 0.98, ("all mice: ρ = %.2f, P = %.3f\nPTEN only: ρ = %.2f, P = %.3f\nuncorrected" % (ra.correlation, ra.pvalue, rp.correlation, rp.pvalue)).replace("-", "−").replace("\nuncorrected", "" if UNC else "\nuncorrected"),
            transform=ax.transAxes, fontsize=FS_S, ha="right", va="top", linespacing=1.3)
    if UNC:
        save(fig, "Fig3_PTEN_against_control")
        return {"rho_all": (ra.correlation, ra.pvalue), "rho_pten": (rp.correlation, rp.pvalue)}
    # d  what the whole search gives by chance
    letter(fig, H, 126, 84, "d")
    ax = ax_mm(fig, H, 136, 97, 43, 32)
    fam = FIN["family"]
    lm = np.log10(fam["mins"])
    ax.hist(lm, bins=np.linspace(-6, -1, 36), color="#BFC5CC", lw=0)
    ob = np.log10(fam["best"][1])
    ax.axvline(ob, color="#B5361F", lw=1.0)
    ax.set_xticks([-5, -4, -3, -2, -1])
    ax.set_xticklabels(["$10^{-5}$", "$10^{-4}$", "$10^{-3}$", "0.01", "0.1"])
    ax.set_xlim(-6, -1)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Minimum P across all %d tests,\n1,000 permutations of group labels" % fam["n_tests"], fontsize=FS)
    ax.text(ob - 0.12, ax.get_ylim()[1] * 0.98, "observed minimum:\nP = %.3f\n\nfamily-wise\nP = %.2f" % (fam["best"][1], fam["fw_p"]),
            fontsize=FS_S, color="#B5361F", ha="right", va="top", linespacing=1.3, bbox=dict(fc="white", ec="none", pad=1.2, alpha=0.9))
    save(fig, "Fig3_PTEN_against_control")
    return {"rho_all": (ra.correlation, ra.pvalue), "rho_pten": (rp.correlation, rp.pvalue)}


if __name__ == "__main__":
    which = [a for a in sys.argv[1:] if not a.startswith("--")] or ["1", "2", "3"]
    if "1" in which:
        figure1()
    if "2" in which:
        print("fig2:", figure2())
    if "3" in which:
        print("fig3:", figure3())
    print("saved to", OUT)
