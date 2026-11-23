"""Rain's figure: representative theta CSDs (CTL / PTEN / DKO), a control
dentate spike and a PTEN interictal spike (IED), each as voltage, CSD and
spectrogram. Writes Rain_Figure.pdf (+ a PNG preview) beside this file.

    python make_rain_figure.py

Reads the raw Neuralynx CSC files through Jarvis's reader (backend/nlx.py),
so times are Jarvis's clock: seconds from the first record's timestamp.
Polarity is Jarvis's (invert=True: positive up, as the lab views it).
Raw reads are cached in %TEMP%/rain_figure_cache.
"""
import hashlib
import os
import sys
import tempfile

import numpy as np
from scipy.signal import butter, filtfilt, fftconvolve, iirnotch, resample_poly, sosfiltfilt

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))
from backend import nlx  # noqa: E402

CACHE = os.path.join(tempfile.gettempdir(), "rain_figure_cache")
os.makedirs(CACHE, exist_ok=True)
FS = 2500.0                 # 30 kHz -> 2.5 kHz (zero-phase polyphase FIR)
PAD = 4.0                   # s read either side of what is shown (filter edges, spectrogram baseline)
EVEN = list(range(2, 65, 2))
H_MM = 0.1                  # even contacts are 100 um apart

# ----------------------------------------------------------------- the data
THETA = [
    ("CTL", r"D:\PTEN\CTL\M6_PtenMissCTL\M6s4sept13\2023-09-13_17-24-49", (618.0, 624.0), [34, 38, 39, 47, 59]),
    ("PTEN", r"\\netfiles03.uvm.edu\bigdata_jbarry\ProcessedPtenData\M13_pten\HF4s1aug1\2023-08-01_11-37-10", (825.0, 831.0), [59]),
    ("DKO", r"D:\PTEN\PTEN_DKO\PTENDKOM41\M41s1nov26\2024-11-26_11-55-25", (970.0, 976.0), [59]),
]
DS = dict(folder=r"D:\PTEN\CTL\PTENDKOM59\m59s4jul7\2025-07-07_12-52-42", t=2024.8641, bad=[59],
          half=0.150, spec=[10, 34, 46, 54], db_max=18)
IED = dict(folder=r"D:\PTEN\PTEN\M34_ptenblind\m34s5jun10\2024-06-10_14-45-34", t=1197.3657, bad=[8, 41, 59],
           half=0.150, spec=[6, 28, 42, 56], db_max=30)


def read(folder, t0, t1):
    """All 64 CSCs over [t0, t1) s at 2.5 kHz, uV; returns (X 64 x n, time of X[:, 0])."""
    key = hashlib.sha1(("%s|%.6f|%.6f" % (folder, t0, t1)).encode()).hexdigest()[:16]
    f = os.path.join(CACHE, key + ".npz")
    if os.path.exists(f):
        z = np.load(f)
        return z["X"].astype(np.float64), float(z["t0"])
    files = dict(nlx.list_csc_files(folder))
    rows, a0s = [], []
    for ch in range(1, 65):
        x, a0, fs = nlx.read_ncs_range(files[ch], t0, t1, invert=True)
        assert abs(fs - 30000.0) < 1
        rows.append(x)
        a0s.append(a0)
    assert max(a0s) - min(a0s) < 1e-3
    n = min(len(r) for r in rows)
    X = resample_poly(np.stack([r[:n] for r in rows]).astype(np.float64), 1, 12, axis=1)
    np.savez(f, X=X.astype(np.float32), t0=a0s[0])
    return X, float(a0s[0])


def notch(X):
    b, a = iirnotch(60.0, 30.0, FS)
    return filtfilt(b, a, X, axis=1)


def band(X, lo, hi):
    return sosfiltfilt(butter(3, [lo, hi], btype="band", fs=FS, output="sos"), X, axis=1)


def evens(X, bad):
    """The 32 even contacts (CSC2 top ... CSC64 bottom); a bad even contact is
    replaced by the mean of its even neighbors."""
    V = X[[c - 1 for c in EVEN]].copy()
    for c in bad:
        if c % 2 == 0:
            i = EVEN.index(c)
            nb = [j for j in (i - 1, i + 1) if 0 <= j < len(EVEN) and EVEN[j] not in bad]
            V[i] = V[nb].mean(axis=0)
    return V


def csd(V):
    """-d2V/dz2 over the even contacts (100 um), ends duplicated (Vaknin et al.
    1988) so every contact has a value; uV in, mV/mm2 out. Sink < 0."""
    P = np.vstack([V[:1], V, V[-1:]])
    return -(P[2:] - 2 * P[1:-1] + P[:-2]) / H_MM ** 2 / 1000.0


def morlet_db(x, freqs, show):
    """Morlet wavelet power (3 cycles at 1 Hz rising log-linearly to 10 at 800
    Hz), in dB relative to each frequency's median over the whole read
    (+-4 s); returns power over the `show` samples only."""
    out = np.empty((len(freqs), show.sum()))
    ncyc = np.interp(np.log(freqs), np.log([freqs[0], freqs[-1]]), [3.0, 10.0])
    for k, (f, nc) in enumerate(zip(freqs, ncyc)):
        st = nc / (2 * np.pi * f)
        tt = np.arange(-4 * st, 4 * st, 1 / FS)
        w = np.exp(2j * np.pi * f * tt) * np.exp(-tt ** 2 / (2 * st ** 2))
        w /= np.abs(w).sum()
        p = np.abs(fftconvolve(x, w, mode="same")) ** 2
        out[k] = 10 * np.log10(p[show] / np.median(p))
    return out


# ------------------------------------------------------------------- style
plt.rcParams.update({
    "font.family": "Arial", "font.size": 6.5, "axes.linewidth": 0.5, "xtick.major.width": 0.5,
    "ytick.major.width": 0.5, "xtick.major.size": 2, "ytick.major.size": 2, "pdf.fonttype": 42,
    "ps.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False, "savefig.dpi": 600,
})
W_MM, H_FIG = 180.0, 200.0
CSD_CMAP = "RdBu_r"         # sink blue, source red
SPEC_CMAP = LinearSegmentedColormap.from_list(
    "spec", ["#0b0c3d", "#2c3fa0", "#2f8fbf", "#7fcf9a", "#f4e04d", "#f29c38", "#c0392b"])
SPEC_COLORS = ["#4d4d4d", "#1b9e77", "#d95f02", "#7570b3"]


def ax_mm(fig, x, y, w, h):
    return fig.add_axes([x / W_MM, 1 - (y + h) / H_FIG, w / W_MM, h / H_FIG])


def letter(fig, x, y, s):
    fig.text(x / W_MM, 1 - y / H_FIG, s, fontsize=9, fontweight="bold", va="top", ha="left")


def bare(ax):
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])


CHAN_TICKS = True           # even channel numbers on the theta and CSD depth axes (both versions)
OUT_STEM = "Rain_Figure"


def chan_ticks(ax):
    """Even channel numbers on the depth axis (rows are CSC2 ... CSC64)."""
    show = [2, 16, 32, 48, 64]
    ax.set_yticks([EVEN.index(c) for c in show])
    ax.set_yticklabels([str(c) for c in show], fontsize=5.5)
    ax.tick_params(axis="y", length=1.5, pad=1)
    ax.set_ylabel("Channel", labelpad=1, fontsize=6)


def vbar(ax, x, y0, length, label, side="left"):
    ax.plot([x, x], [y0, y0 + length], color="k", lw=0.8, clip_on=False, solid_capstyle="butt")
    ax.text(x + (-1 if side == "left" else 1) * 0.012 * np.diff(ax.get_xlim())[0], y0 + length / 2, label,
            rotation=90, ha="right" if side == "left" else "left", va="center", fontsize=6)


def cbar(fig, im, x, y, w, h, label, ticks=None):
    cax = ax_mm(fig, x, y, w, h)
    cb = fig.colorbar(im, cax=cax, ticks=ticks)
    cb.outline.set_linewidth(0.4)
    cb.ax.tick_params(width=0.4, length=1.5, labelsize=5.5)
    cb.set_label(label, fontsize=6, labelpad=2)
    return cb


def export_panels(fig, groups, pad_in=0.04):
    """Each panel on its own: the full figure cropped to that panel's artists
    (axes with their ticks, labels, scale bars and colorbar), as PDF and a
    600 dpi PNG, in "<OUT_STEM> panels/"."""
    from matplotlib.transforms import Bbox
    out = os.path.join(HERE, "Individual panels", OUT_STEM)
    os.makedirs(out, exist_ok=True)
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    crops = []
    for name, arts in groups:               # every crop measured before anything is hidden
        boxes = [a.get_tightbbox(r) if hasattr(a, "get_tightbbox") else a.get_window_extent(r) for a in arts]
        bb = Bbox.union([b for b in boxes if b is not None]).transformed(fig.dpi_scale_trans.inverted())
        crops.append((name, arts, Bbox.from_extents(bb.x0 - pad_in, bb.y0 - pad_in, bb.x1 + pad_in, bb.y1 + pad_in)))
    for name, arts, bb in crops:
        for t in fig.texts:                 # panel letters and other rows' headers stay out of the crop
            t.set_visible(any(t is a for a in arts))
        for ext, kw in ((".pdf", {}), (".png", {"dpi": 600})):
            fig.savefig(os.path.join(out, name + ext), bbox_inches=bb, **kw)
    for t in fig.texts:
        t.set_visible(True)
    print("panels:", out, len(groups))


# ------------------------------------------------------------- the figure
def main():
    fig = plt.figure(figsize=(W_MM / 25.4, H_FIG / 25.4))
    notes = []
    groups = []                 # (file name, artists) for the one-panel exports

    # a: theta CSDs ---------------------------------------------------------
    TH = []
    for name, folder, (s0, s1), bad in THETA:
        X, t0 = read(folder, s0 - PAD, s1 + PAD)
        V = evens(band(notch(X), 4.0, 12.0), bad)
        C = csd(V)
        t = t0 + np.arange(X.shape[1]) / FS
        w = (t >= s0) & (t < s1)
        TH.append((name, t[w] - s0, V[:, w], C[:, w]))
    clim = np.percentile(np.abs(np.concatenate([c.ravel() for *_x, c in TH])), 99.0)
    vs = np.percentile(np.abs(np.concatenate([v.ravel() for _n, _t, v, _c in TH])), 99.0)
    y_a, h_a = 8.0, 50.0
    xs = [14.0, 64.0, 114.0]
    for (name, tt, V, C), x in zip(TH, xs):
        ax = ax_mm(fig, x, y_a, 46.0, h_a)
        im = ax.imshow(C, aspect="auto", cmap=CSD_CMAP, vmin=-clim, vmax=clim, interpolation="bilinear",
                       extent=[tt[0], tt[-1], len(EVEN) - 0.5, -0.5])
        for i in range(len(EVEN)):
            ax.plot(tt, i - 0.9 * V[i] / vs, color="k", lw=0.25)
        ax.set_xlim(0, 6)
        ax.set_ylim(len(EVEN) - 0.5, -1.0)
        ax.set_title(name, fontsize=7.5, fontweight="bold", pad=3)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.set_xticks(range(7))
        ax.set_xlabel("Time (s)", labelpad=1)
        groups.append(("a_Theta_%s" % name, [ax]))
        if x == xs[0]:
            if CHAN_TICKS:
                chan_ticks(ax)
    th_ticks = [v for v in MaxNLocator(5, symmetric=True, integer=True).tick_values(-clim, clim) if abs(v) <= clim]
    cb = cbar(fig, im, 164.0, y_a + 8, 1.6, h_a - 16, "CSD (mV/mm\u00b2)", ticks=th_ticks)
    t1 = fig.text(164.8 / W_MM, 1 - (y_a + 6.8) / H_FIG, "source", fontsize=5.5, ha="center", va="bottom",
                  color="#b2182b")
    t2 = fig.text(164.8 / W_MM, 1 - (y_a + h_a - 7.2) / H_FIG, "sink", fontsize=5.5, ha="center", va="top",
                  color="#2166ac")
    groups.append(("a_Theta_colorbar", [cb.ax, t1, t2]))
    groups.append(("a_Theta_all", [g for _n, gs in groups for g in gs]))
    letter(fig, 2, 3, "a")
    notes.append("a  theta 4-12 Hz CSD, shared color scale +-%.3g mV/mm2 (99th percentile of |CSD| over the three windows); "
                 "trace scale: %.0f uV = 0.9 contact spacing" % (clim, vs))

    # b, c: events -----------------------------------------------------------
    freqs = np.geomspace(1.0, 800.0, 90)
    rows = [("b", "Control dentate spike", DS, "ds", 78.0), ("c", "PTEN interictal epileptiform discharge (IED)", IED, "ied", 144.0)]
    spec_all = []
    for lt, title, E, kind, y0 in rows:
        X, t0 = read(E["folder"], E["t"] - PAD, E["t"] + PAD)
        Xn = notch(X)
        t = t0 + np.arange(X.shape[1]) / FS - E["t"]
        w = (t >= -E["half"]) & (t <= E["half"])
        tm = t[w] * 1000.0
        if kind == "ds":
            V = evens(band(Xn, 5.0, 100.0), E["bad"])[:, w]
            filt_txt = "5\u2013100 Hz, 60 Hz notch"
        else:
            V = evens(Xn, E["bad"])[:, w]
            V = V - np.median(V[:, tm < -60], axis=1, keepdims=True)
            filt_txt = "unfiltered, 60 Hz notch"
        C = csd(V)
        h = 46.0
        letter(fig, 2, y0 - 7.5, lt)
        head = fig.text(8 / W_MM, 1 - (y0 - 7.3) / H_FIG, "%s  (%s)" % (title, filt_txt), fontsize=6.5, va="top")

        # voltage
        ax = ax_mm(fig, 14, y0, 38, h)
        gain = np.percentile(np.abs(V), 99.5)
        for i in range(len(EVEN)):
            ax.plot(tm, i - 1.6 * V[i] / gain, color="k", lw=0.35)
        ax.set_xlim(tm[0], tm[-1])
        ax.set_ylim(len(EVEN) + 0.5, -2.0)
        bare(ax)
        for c, col in zip(E["spec"], SPEC_COLORS):
            ax.plot(tm[0] - 6, EVEN.index(c), marker=">", ms=3, color=col, clip_on=False, mec="none")
        sb = 1000.0 if kind == "ds" else 2000.0
        x_sb = tm[-1] + 8
        ax.plot([x_sb, x_sb], [len(EVEN) - 1, len(EVEN) - 1 - 1.6 * sb / gain], color="k", lw=0.8, clip_on=False)
        ax.text(x_sb + 3, len(EVEN) - 1 - 0.8 * sb / gain, "%g mV" % (sb / 1000), rotation=90, va="center",
                ha="left", fontsize=6)
        ax.plot([tm[-1] - 50, tm[-1]], [len(EVEN) + 0.3] * 2, color="k", lw=0.8, clip_on=False)
        ax.text(tm[-1] - 25, len(EVEN) + 0.8, "50 ms", ha="center", va="top", fontsize=6)
        ax.set_title("Voltage", fontsize=6.5, pad=2)
        groups.append(("%s_%s_Voltage" % (lt, kind.upper()), [ax]))

        # CSD
        ax = ax_mm(fig, 64, y0, 38, h)
        cl = np.percentile(np.abs(C), 99.5)
        im = ax.imshow(C, aspect="auto", cmap=CSD_CMAP, vmin=-cl, vmax=cl, interpolation="bilinear",
                       extent=[tm[0], tm[-1], len(EVEN) - 0.5, -0.5])
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        if CHAN_TICKS:
            chan_ticks(ax)
        ax.set_xticks([-150, -100, -50, 0, 50, 100, 150])
        ax.set_xlabel("Time (ms)", labelpad=1)
        ax.set_title("CSD", fontsize=6.5, pad=2)
        cb_ticks = [v for v in MaxNLocator(5, symmetric=True).tick_values(-cl, cl) if abs(v) <= cl]
        cb = cbar(fig, im, 103.5, y0 + 6, 1.6, h - 12, "CSD (mV/mm\u00b2)", ticks=cb_ticks)
        groups.append(("%s_%s_CSD" % (lt, kind.upper()), [ax, cb.ax]))

        # spectrogram: 4 contacts stacked, top to bottom in depth order
        raw = evens(Xn, E["bad"])
        sh = (h - 3 * 1.2) / 4
        S = [morlet_db(raw[EVEN.index(c)], freqs, w) for c in E["spec"]]
        spec_all.append(S)
        spec_axes = []
        for j, (c, col) in enumerate(zip(E["spec"], SPEC_COLORS)):
            ax = ax_mm(fig, 126, y0 + j * (sh + 1.2), 33, sh)
            spec_axes.append(ax)
            im = ax.pcolormesh(tm, freqs, S[j], cmap=SPEC_CMAP, vmin=-6, vmax=E["db_max"], shading="gouraud",
                               rasterized=True)
            ax.set_yscale("log")
            ax.set_ylim(1, 800)
            ax.set_yticks([1, 10, 100])
            ax.set_yticklabels(["1", "10", "100"], fontsize=5.5)
            ax.tick_params(axis="y", which="minor", length=0)
            ax.text(1.03, 0.5, "Ch %d" % c, transform=ax.transAxes, ha="left", va="center", fontsize=5.5,
                    color=col, fontweight="bold")
            if j < 3:
                ax.set_xticks([])
                ax.spines["bottom"].set_visible(False)
            else:
                ax.set_xticks([-150, -100, -50, 0, 50, 100, 150])
                ax.set_xticklabels(["−150", "", "", "0", "", "", "150"])
                ax.set_xlabel("Time (ms)", labelpad=1)
            if j == 0:
                ax.set_title("Spectrogram (1–800 Hz)", fontsize=6.5, pad=2)
        ft = fig.text(118.5 / W_MM, 1 - (y0 + h / 2) / H_FIG, "Frequency (Hz)", rotation=90, ha="center",
                      va="center", fontsize=6.5)
        cb = cbar(fig, im, 168.5, y0 + 6, 1.6, h - 12, "Relative power (dB)",
                  ticks=list(range(-6, E["db_max"] + 1, 6)))
        groups.append(("%s_%s_Spectrogram" % (lt, kind.upper()), spec_axes + [ft, cb.ax]))
        groups.append(("%s_%s_all" % (lt, kind.upper()), [g for n, gs in groups if n.startswith(lt + "_")
                                                          for g in gs] + [head]))
        notes.append("%s  %s: window %+.0f to %+.0f ms; CSD color limit +-%.3g mV/mm2 (99.5th percentile); "
                     "voltage scale bar %g mV" % (lt, title, -E["half"] * 1e3, E["half"] * 1e3, cl, sb / 1000))

    out = os.path.join(HERE, OUT_STEM + ".pdf")
    fig.savefig(out)
    fig.savefig(os.path.join(HERE, OUT_STEM + "_preview.png"), dpi=300)
    export_panels(fig, groups)
    plt.close(fig)
    for n in notes:
        print(n)
    for S, E in zip(spec_all, (DS, IED)):
        print("spectrogram dB range", [round(float(np.percentile(s, 1)), 1) for s in S],
              [round(float(np.percentile(s, 99.5)), 1) for s in S])
    print("wrote", out)


if __name__ == "__main__":
    main()
