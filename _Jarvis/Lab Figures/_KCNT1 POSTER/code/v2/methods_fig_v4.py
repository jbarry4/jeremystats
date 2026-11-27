"""Methods figure, v4: a normal dentate spike beside a big IED from the same KCNT1 recording, drawn on SHARED scales
so the size difference is the message ("lil old normal DS, BIG BAD IED").

  voltage      32 even contacts, ONE trace gain for both (set by the dentate spike), so the IED swings far past its row
  CSD          ONE color scale for both (the dentate spike's 99.5th percentile |CSD|), so the IED saturates
  spectrogram  Jarvis's Spectrogram pane (backend/analysis.py _stft_legacy = xf_spectrogram.m): Hamming frames a tenth
               of the window, overlapped by 1/1.02 of themselves, 30*log10|S|, jet; 8 contacts stacked (CSC1, 9 ... 57)
               as in the Jarvis pane; ONE color scale for both events
Raw data and reader as before (VACC, Jarvis nlx.py, invert=True, 2.5 kHz).
usage: python methods_fig_v4.py DS.npz DS_T SPIKE.npz SPIKE_T OUT.png"""
import json, sys
import numpy as np
from scipy.signal import butter, filtfilt, iirnotch, sosfiltfilt
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FS = 2500.0
EVEN = list(range(2, 65, 2))
SPEC_CH = [1, 9, 17, 25, 33, 41, 49, 57]
H_MM = 0.04
HALF = 0.15                      # s shown either side of the event
MARKS = dict(upper_sink=34, source=40, lower_sink=56)   # from m1609's mean dentate spike (methods_fig.py)


def notch(X):
    b, a = iirnotch(60.0, 30.0, FS)
    return filtfilt(b, a, X, axis=-1)


def band(X, lo, hi):
    return sosfiltfilt(butter(3, [lo, hi], btype="band", fs=FS, output="sos"), X, axis=-1)


def csd(V):
    P = np.vstack([V[:1], V, V[-1:]])
    return -(P[2:] - 2 * P[1:-1] + P[:-2]) / H_MM ** 2 / 1000.0


def xf_spec(y, fmax=1000.0):
    """_stft_legacy: frames n/10 long, overlap 1/1.02 of a frame, Hamming, |S| -> 30*log10."""
    n = y.size
    ns = int(round(n / 10))
    nover = int(round(ns / 1.02))
    hop = max(1, ns - nover)
    starts = np.arange(0, n - ns + 1, hop)
    win = np.hamming(ns)
    F = np.fft.rfft(np.stack([y[s:s + ns] for s in starts]) * win, axis=1)
    f = np.fft.rfftfreq(ns, 1 / FS)
    keep = (f > 0) & (f <= fmax)
    return 30 * np.log10(np.abs(F[:, keep]).T + 1e-9), f[keep], (starts + ns / 2) / FS


def load(npz, tv):
    z = np.load(npz)
    i = int(np.flatnonzero(np.abs(z["t"] - tv) < 0.002)[0])
    return z["X"][i].astype(np.float64), float(z["half"]), z


def baseline(z, c):
    """Median power per frequency of this contact over the recording's random 1-s baseline windows (same STFT)."""
    half = float(z["half"]); n = z["X"].shape[-1]; tt = np.arange(n) / FS - half; sw = (tt >= -0.5) & (tt <= 0.5)
    cols = [xf_spec(notch(z["X"][i, c - 1].astype(np.float64))[sw])[0] for i in np.flatnonzero(z["kind"] == "base")]
    return np.median(np.concatenate(cols, axis=1), axis=1)


def main(ds_npz, t_ds, sp_npz, t_sp, out):
    ev = []
    for label, npz, tv, is_ds in (("Dentate spike", ds_npz, t_ds, True), ("IED", sp_npz, t_sp, False)):
        X, half, z = load(npz, tv)
        Xn = notch(X)
        tt = np.arange(X.shape[-1]) / FS - half
        w = (tt >= -HALF) & (tt <= HALF)
        V = Xn[[c - 1 for c in EVEN]]
        if is_ds:
            V = band(V, 5.0, 100.0)
        else:
            V = sosfiltfilt(butter(3, 1.0, btype="high", fs=FS, output="sos"), V, axis=-1)      # >1 Hz, as Jarvis's pane
            V = V - np.median(V[:, (tt >= -0.15) & (tt < -0.06)], axis=1, keepdims=True)
        V = V[:, w]
        sw = (tt >= -0.5) & (tt <= 0.5)                         # Jarvis pane: 1 s read, frames a tenth of it
        S = []
        for c in SPEC_CH:
            s, f, ts = xf_spec(Xn[c - 1][sw])
            s = s - baseline(z, c)[:, None]          # dB over this contact's own baseline, frequency by frequency
            ts = ts - 0.5
            S.append((s, f, ts))               # the whole 1 s, as the Jarvis pane shows it
        ev.append(dict(label=label, t=tv, V=V, C=csd(V), S=S, tm=tt[w] * 1000, is_ds=is_ds))
    gain = np.percentile(np.abs(ev[0]["V"]), 99.5)               # set by the dentate spike
    clim = np.percentile(np.abs(ev[0]["C"]), 99.5)
    allS = np.concatenate([s.ravel() for e in ev for s, _f, _t in e["S"]])
    slo, shi = (-6.0, max(12.0, float(np.percentile(allS, 99.9))))

    plt.rcParams.update({"font.family": "Arial", "font.size": 13, "axes.linewidth": 1.0, "axes.spines.top": False,
                         "axes.spines.right": False, "pdf.fonttype": 42})
    FW, FH = 13.8, 5.1
    fig = plt.figure(figsize=(FW, FH))

    def ax_in(x, y, w_, h_):
        return fig.add_axes([x / FW, 1 - (y + h_) / FH, w_ / FW, h_ / FH])

    y0, h = 0.62, 3.85
    for k, e in enumerate(ev):
        x0 = 0.12 + k * 6.85
        tm = e["tm"]
        fig.text((x0 + 0.06) / FW, 1 - 0.30 / FH, e["label"], fontsize=19 if not e["is_ds"] else 17, fontweight="bold",
                 va="center", ha="left", color="#b2182b" if not e["is_ds"] else "#1d2433")
        fig.text((x0 + 0.06 + (1.85 if e["is_ds"] else 0.75)) / FW, 1 - 0.30 / FH,
                 "(5–100 Hz)" if e["is_ds"] else ">1 Hz", fontsize=12.5, va="center", color="#5a6273")
        ax = ax_in(x0 + 0.95, y0, 1.25, h)
        for r in range(32):
            ax.plot(tm, r - 1.4 * e["V"][r] / gain, color="k", lw=0.6, clip_on=False)
        ax.set_xlim(tm[0], tm[-1])
        ax.set_ylim(32.3, -1.5)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])
        if k == 0:
            for c in (2, 64):
                ax.text(tm[0] - 25, EVEN.index(c), "Ch %d" % c, ha="right", va="center", fontsize=10)
            for key, txt in (("upper_sink", "upper sink"), ("source", "source"), ("lower_sink", "lower sink")):
                ax.text(tm[0] - 25, EVEN.index(MARKS[key]), "%s\nCh %d" % (txt, MARKS[key]), ha="right", va="center",
                        fontsize=9.5, color="#1f6f8b", fontweight="bold", linespacing=0.95)
        sb = 1000.0
        ax.plot([tm[-1] + 10] * 2, [31, 31 - 1.4 * sb / gain], color="k", lw=1.6, clip_on=False)
        ax.text(tm[-1] + 18, 31 - 0.7 * sb / gain, "1 mV", rotation=90, va="center", ha="left", fontsize=11.5)
        ax.plot([tm[-1] - 50, tm[-1]], [32.8, 32.8], color="k", lw=1.6, clip_on=False)
        ax.text(tm[-1] - 25, 33.2, "50 ms", ha="center", va="top", fontsize=11.5)
        ax.set_title("Voltage", fontsize=13, pad=3)
        ax = ax_in(x0 + 2.45, y0, 1.45, h)
        im = ax.imshow(e["C"], aspect="auto", cmap="jet", vmin=-clim, vmax=clim, interpolation="bilinear",
                       extent=[tm[0], tm[-1], 31.5, -0.5])
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.set_xticks([-100, 0, 100])
        ax.set_xlabel("Time (ms)", labelpad=2)
        ax.set_title("CSD", fontsize=13, pad=3)
        if k == 1:
            cax = ax_in(x0 + 3.95, y0 + 0.6, 0.07, h - 1.2)
            cb = fig.colorbar(im, cax=cax, ticks=[-clim, 0, clim])
            cb.ax.set_yticklabels(["sink", "0", "source"], fontsize=10.5)
            cb.outline.set_linewidth(0.6)
        sh = (h - 7 * 0.05) / 8
        for j, (c, (s, f, ts)) in enumerate(zip(SPEC_CH, e["S"])):
            ax = ax_in(x0 + 5.0, y0 + j * (sh + 0.05), 1.2, sh)
            im2 = ax.pcolormesh(ts * 1000, f, s, cmap="jet", vmin=slo, vmax=shi, shading="gouraud", rasterized=True)
            ax.set_ylim(0, 600)
            ax.axvline(0, color="w", lw=0.6, ls=(0, (2, 2)), alpha=0.7)
            ax.set_yticks([])
            ax.set_xlim(-500, 500)
            ax.text(-0.04, 0.5, "Ch %d" % c, transform=ax.transAxes, ha="right", va="center", fontsize=9.5)
            if j < 7:
                ax.set_xticks([])
                ax.spines["bottom"].set_visible(False)
            else:
                ax.set_xticks([-400, 0, 400])
                ax.set_xlabel("Time (ms)", labelpad=2)
            if j == 0:
                ax.set_title("Spectrogram, 0–600 Hz", fontsize=13, pad=3)
        if k == 1:
            cax = ax_in(x0 + 6.27, y0 + 0.6, 0.07, h - 1.2)
            cb = fig.colorbar(im2, cax=cax, ticks=[slo, shi])
            cb.ax.set_yticklabels(["−6", "+%d" % round(shi)], fontsize=10.5)
            cb.set_label("dB over baseline", fontsize=10.5, labelpad=-4)
            cb.outline.set_linewidth(0.6)
    fig.savefig(out, dpi=300)
    json.dump(dict(ds_t=t_ds, ied_t=t_sp, trace_gain_uV=float(gain), csd_clim_mV_mm2=float(clim), spec_db_range=[float(slo), float(shi)],
                   ied_peak_uV=float(np.abs(ev[1]["V"]).max()), ds_peak_uV=float(np.abs(ev[0]["V"]).max()),
                   ied_csd_peak=float(np.abs(ev[1]["C"]).max()), ds_csd_peak=float(np.abs(ev[0]["C"]).max())),
              open(out.rsplit(".", 1)[0] + ".json", "w"), indent=1)
    print("saved", out)


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]), sys.argv[3], float(sys.argv[4]), sys.argv[5])
