"""Methods figure for KCNT1 poster v2: one dentate spike and one spike (IED) from the same KCNT1 recording, each as
voltage, CSD and spectrograms -- the Jarvis 'Rain figure' recipe with the theta panel left out.

Raw data: all 64 CSCs read on a VACC compute node straight from netfiles with Jarvis's own reader (backend/nlx.py,
times in seconds from the first record's timestamp, invert=True), 30 kHz -> 2.5 kHz (resample_poly 1/12).
Depth: StrataScope layers where the recording has them signed off; otherwise even channel numbers plus the
recording's own mean dentate spike (where its upper- and lower-blade sinks and the source between them sit).

usage: python methods_fig.py WINDOWS.npz RECORDING_LABEL DS_TIME SPIKE_TIME OUT.png [layers|ds_landmarks]
"""
import json
import sys

import numpy as np
from scipy.signal import butter, fftconvolve, filtfilt, iirnotch, sosfiltfilt

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

FS = 2500.0
EVEN = list(range(2, 65, 2))
H_MM = 0.04                    # H3: 20 um pitch, so even contacts are 40 um apart
BAD = [59]
LAYERS = {
    "m1606": [("SO", 1, 2), ("SP", 3, 7), ("SR", 8, 13), ("SLM", 14, 18), ("OML", 19, 24), ("MML", 25, 28),
              ("GCL", 29, 34), ("HIL", 35, 44), ("GCL", 45, 51), ("MML", 52, 57), ("OML", 58, 61), ("THAL", 62, 64)],
}
SPEC_COLORS = ["#4d4d4d", "#1b9e77", "#d95f02", "#7570b3"]
SPEC_CMAP = LinearSegmentedColormap.from_list(
    "spec", ["#0b0c3d", "#2c3fa0", "#2f8fbf", "#7fcf9a", "#f4e04d", "#f29c38", "#c0392b"])


def notch(X):
    b, a = iirnotch(60.0, 30.0, FS)
    return filtfilt(b, a, X, axis=-1)


def band(X, lo, hi):
    return sosfiltfilt(butter(3, [lo, hi], btype="band", fs=FS, output="sos"), X, axis=-1)


def evens(X):
    V = X[[c - 1 for c in EVEN]].copy()
    for c in BAD:
        if c % 2 == 0:
            i = EVEN.index(c)
            V[i] = V[[j for j in (i - 1, i + 1) if 0 <= j < 32]].mean(axis=0)
    return V


def csd(V):
    P = np.vstack([V[:1], V, V[-1:]])
    return -(P[2:] - 2 * P[1:-1] + P[:-2]) / H_MM ** 2 / 1000.0


def morlet_power(x, freqs):
    out = np.empty((len(freqs), len(x)))
    ncyc = np.interp(np.log(freqs), np.log([freqs[0], freqs[-1]]), [3.0, 10.0])
    for k, (f, nc) in enumerate(zip(freqs, ncyc)):
        st = nc / (2 * np.pi * f)
        tt = np.arange(-4 * st, 4 * st, 1 / FS)
        w = np.exp(2j * np.pi * f * tt) * np.exp(-tt ** 2 / (2 * st ** 2))
        w /= np.abs(w).sum()
        out[k] = np.abs(fftconvolve(x, w, mode="same")) ** 2
    return out


def ds_landmarks(X, kind, tt):
    """Upper-blade sink, source between, lower-blade sink: channels from the mean CSD of the recording's DS windows."""
    idx = np.flatnonzero(np.char.find(kind.astype(str), "ds") >= 0)
    C = np.mean([csd(evens(band(notch(X[i]), 5.0, 100.0))) for i in idx], axis=0)
    w = (tt >= -10) & (tt <= 25)
    col = C[:, w][:, np.argmin(C[:, w].min(axis=0))]
    s1 = int(np.argmin(col))
    rest = [i for i in range(32) if abs(i - s1) >= 6]
    s2 = rest[int(np.argmin(col[rest]))]
    up, lo = sorted((s1, s2))
    src = up + int(np.argmax(col[up:lo + 1]))
    return dict(upper_sink=EVEN[up], source=EVEN[src], lower_sink=EVEN[lo], n_ds=int(len(idx)))


def main(npz, rec, t_ds, t_sp, out_png, depth="layers", sp_npz=None, sp_label=None):
    z = np.load(npz)
    X = z["X"].astype(np.float64)
    t, kind = z["t"], z["kind"]
    tt = (np.arange(X.shape[-1]) / FS - float(z["half"])) * 1000.0
    w = (tt >= -150) & (tt <= 150)
    tm = tt[w]
    freqs = np.geomspace(2.0, 800.0, 80)
    marks = ds_landmarks(X, kind, tt) if depth == "ds_landmarks" else None
    spec = ([10, marks["upper_sink"], marks["source"], marks["lower_sink"]] if marks else [10, 30, 40, 56])
    spec = [c if c != 59 else 58 for c in spec]
    base_idx = np.flatnonzero(kind == "base")
    base = {c: np.median(np.concatenate([morlet_power(notch(X[i, c - 1]), freqs)[:, 500:-500] for i in base_idx], axis=1), axis=1)
            for c in spec}
    plt.rcParams.update({"font.family": "Arial", "font.size": 13, "axes.linewidth": 1.0, "xtick.major.width": 1.0,
                         "ytick.major.width": 1.0, "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42})
    FW, FH = 13.8, 5.1
    fig = plt.figure(figsize=(FW, FH))

    def ax_in(x, y, w_, h_):
        return fig.add_axes([x / FW, 1 - (y + h_) / FH, w_ / FW, h_ / FH])

    SRC = {True: (X, t, base, marks)}
    if sp_npz:
        z2 = np.load(sp_npz); X2 = z2["X"].astype(np.float64); k2 = z2["kind"]
        b2 = {c: np.median(np.concatenate([morlet_power(notch(X2[i, c - 1]), freqs)[:, 500:-500] for i in np.flatnonzero(k2 == "base")], axis=1), axis=1)
              for c in spec}
        SRC[False] = (X2, z2["t"], b2, None if sp_label else marks)
    else:
        SRC[False] = SRC[True]
    rows = []
    for k_, (label, tv, is_ds) in enumerate((("Dentate spike", t_ds, True), ("Spike (IED)", t_sp, False))):
        Xs, ts_, base_s, marks_s = SRC[is_ds]
        i = int(np.flatnonzero(np.abs(ts_ - tv) < 0.002)[0])
        Xn = notch(Xs[i])
        if is_ds:
            V = evens(band(Xn, 5.0, 100.0))
        else:
            V = evens(Xn)
            V = V - np.median(V[:, (tt >= -150) & (tt < -60)], axis=1, keepdims=True)
        V = V[:, w]
        C = csd(V)
        x0 = 0.12 + k_ * 6.85
        y0, h = 0.62, 3.85
        fig.text((x0 + 0.06) / FW, 1 - 0.30 / FH, label, fontsize=17, fontweight="bold", va="center", ha="left")
        fig.text((x0 + 0.06 + (1.85 if is_ds else 1.55)) / FW, 1 - 0.30 / FH,
                 ("(5–100 Hz)" if is_ds else "(unfiltered)") + ("  " + (sp_label if not is_ds else rec) if sp_npz and sp_label else ""), fontsize=12.5, va="center", ha="left", color="#5a6273")
        # voltage
        ax = ax_in(x0 + 0.95, y0, 1.2, h)
        g = np.percentile(np.abs(V), 99.5)
        for r in range(32):
            ax.plot(tm, r - 1.5 * V[r] / g, color="k", lw=0.6)
        ax.set_xlim(tm[0], tm[-1])
        ax.set_ylim(32.3, -1.5)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])
        for c, col in zip(spec, SPEC_COLORS):
            ax.plot(tm[0] - 7, EVEN.index(c), marker=">", ms=7, color=col, clip_on=False, mec="none")
        sb = 1000.0 if is_ds else 2000.0
        ax.plot([tm[-1] + 8] * 2, [31, 31 - 1.5 * sb / g], color="k", lw=1.6, clip_on=False)
        ax.text(tm[-1] + 14, 31 - 0.75 * sb / g, "%g mV" % (sb / 1000), rotation=90, va="center", ha="left", fontsize=11.5)
        ax.plot([tm[-1] - 50, tm[-1]], [32.6, 32.6], color="k", lw=1.6, clip_on=False)
        ax.text(tm[-1] - 25, 33.0, "50 ms", ha="center", va="top", fontsize=11.5)
        ax.set_title("Voltage", fontsize=13, pad=3)
        if rec in LAYERS and depth == "layers":
            for nm, a, b in LAYERS[rec]:
                ev = [r for r, c in enumerate(EVEN) if a <= c <= b]
                if not ev:
                    continue
                ya, yb = ev[0] - 0.45, ev[-1] + 0.45
                ax.plot([tm[0] - 30] * 2, [ya, yb], color="#5a6273", lw=1.2, clip_on=False)
                ax.text(tm[0] - 36, (ya + yb) / 2, nm, ha="right", va="center", fontsize=9.5, color="#1d2433")
        else:
            for c in (2, 64):
                ax.text(tm[0] - 22, EVEN.index(c), "Ch %d" % c, ha="right", va="center", fontsize=10, color="#1d2433")
            if marks_s:
                for key, txt in (("upper_sink", "upper sink"), ("source", "source"), ("lower_sink", "lower sink")):
                    ax.text(tm[0] - 22, EVEN.index(marks[key]), "%s\nCh %d" % (txt, marks[key]), ha="right", va="center",
                            fontsize=9.5, color="#1f6f8b", fontweight="bold", linespacing=0.95)
        # CSD
        ax = ax_in(x0 + 2.45, y0, 1.45, h)
        cl = np.percentile(np.abs(C), 99.5)
        im = ax.imshow(C, aspect="auto", cmap="jet", vmin=-cl, vmax=cl, interpolation="bilinear",
                       extent=[tm[0], tm[-1], 31.5, -0.5])
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.set_xticks([-100, 0, 100])
        ax.set_xlabel("Time (ms)", labelpad=2)
        ax.set_title("CSD", fontsize=13, pad=3)
        cax = ax_in(x0 + 3.96, y0 + 0.6, 0.08, h - 1.2)
        cb = fig.colorbar(im, cax=cax, ticks=[-cl, 0, cl])
        cb.ax.set_yticklabels(["sink", "0", "source"], fontsize=10.5)
        cb.outline.set_linewidth(0.6)
        cb.ax.tick_params(length=2)
        # spectrograms
        sh = (h - 3 * 0.12) / 4
        for j, (c, col) in enumerate(zip(spec, SPEC_COLORS)):
            ax = ax_in(x0 + 4.95, y0 + j * (sh + 0.12), 1.3, sh)
            P = morlet_power(Xn[c - 1], freqs)[:, w]
            S = 10 * np.log10(P / base_s[c][:, None])
            ax.pcolormesh(tm, freqs, S, cmap=SPEC_CMAP, vmin=-6, vmax=(18 if is_ds else 30), shading="gouraud", rasterized=True)
            ax.set_yscale("log")
            ax.set_ylim(2, 800)
            ax.set_yticks([10, 100])
            ax.set_yticklabels(["10", "100"], fontsize=10.5)
            ax.tick_params(axis="y", which="minor", length=0)
            ax.text(1.03, 0.5, "Ch %d" % c, transform=ax.transAxes, ha="left", va="center", fontsize=10.5, color=col,
                    fontweight="bold")
            if j < 3:
                ax.set_xticks([])
                ax.spines["bottom"].set_visible(False)
            else:
                ax.set_xticks([-100, 0, 100])
                ax.set_xlabel("Time (ms)", labelpad=2)
            if j == 0:
                ax.set_title("Spectrogram (Hz)", fontsize=13, pad=3)
        rows.append(dict(panel=label, t_s=float(tv), window_index=i, csd_color_limit_mV_mm2=float(cl),
                         trace_gain_uV=float(g), filter="5-100 Hz + 60 Hz notch" if is_ds else "60 Hz notch only, baseline -150..-60 ms removed",
                         spectrogram_db_max=18 if is_ds else 30))
    fig.savefig(out_png, dpi=300)
    meta = dict(recording=rec, npz=npz, events=rows, spectrogram_channels=spec, depth=depth, ds_landmarks=marks,
                layers=LAYERS.get(rec) if depth == "layers" else None, csd="-d2V/dz2 over even contacts, 40 um apart, ends duplicated (Vaknin 1988); bad CSC59 replaced by neighbours where even",
                spectrogram="complex Morlet, 3 cycles at 2 Hz rising to 10 at 800 Hz; dB relative to the median power per frequency over 20 random 2-s windows of the same recording")
    json.dump(meta, open(out_png.rsplit(".", 1)[0] + ".json", "w"), indent=1)
    print("saved", out_png, json.dumps(rows))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), sys.argv[5], sys.argv[6] if len(sys.argv) > 6 else "layers",
         sys.argv[7] if len(sys.argv) > 7 else None, sys.argv[8] if len(sys.argv) > 8 else None)
