"""
ied_ampwidth_gui_v5.py -- 500-1000 Hz power instead of amplitude, with the
FOOOF decomposition that says whether it is an oscillation or just broadband.

The band is FIXED at 500-1000 Hz and there is no slider for it. That is
deliberate: the band is part of what the measurement IS, so a run's numbers
mean nothing without it, and a control that moves it invites two sessions to
report incomparable figures under the same name. Change HF_BAND in
`ied_ds_hf.py` if it ever needs to be something else, and every number that
comes out changes with it, visibly.

HOW YOU PLOT "POWER ABOVE 250 Hz" -- FOUR PANELS, FOUR DIFFERENT QUESTIONS
==========================================================================
"Above-250 Hz power" is one number per event per contact, and one number
cannot be plotted usefully on its own. Each panel here answers a question the
others cannot:

  SPECTROGRAM (time x frequency, dB re baseline)
      WHEN was the high-frequency energy? A fast ripple is locked to the
      discharge; background HF is not. This is the panel that distinguishes
      "this event had an HFO" from "this contact is noisy", and no scalar can.

  ENVELOPE (500-1000 Hz amplitude against time)
      The same thing collapsed to one trace, so it can be averaged over
      events. The class-average envelope under it shows whether the HF is
      consistently locked across events or smeared -- an average that is flat
      means the individual bursts were at different latencies.

  PSD WITH THE FOOOF FIT (log power vs log frequency)
      WHY the number is what it is. Measured spectrum, the fitted aperiodic
      1/f, the full model, and the flattened spectrum with the aperiodic
      removed. The band is shaded. If the flattened trace has a bump in the
      band there is an oscillation; if it is flat there, the band power is
      just broadband energy riding on a raised 1/f.

  DEPTH PROFILE (dB per contact) and the PER-EVENT DISTRIBUTION
      WHERE it is generated, and whether the classes differ.

WHAT FOOOF ADDS, AND WHAT IT DOES NOT
=====================================
FOOOF does NOT measure band power -- an integral under the PSD does that, and
needs no model. What FOOOF adds is the split between

    aperiodic   offset and exponent of the 1/f. A sharp transient is
                broadband: an IED's fast edges raise the whole spectrum with
                no oscillation anywhere. That shows up here.
    periodic    Gaussian peaks above the aperiodic fit. A genuine fast ripple
                is a peak at its own centre frequency. That shows up here.

This matters because the classic HFO false positive is exactly this confusion:
band-pass a sharp transient and the filter rings, producing a convincing
"ripple" that is only the filter's response to a step. Band power cannot tell
the two apart. The `flattened` trace in the PSD panel can.

Fitted over 100-2000 Hz, not 1-2000: one aperiodic component cannot describe
three decades of a neural spectrum, and forcing it makes the fit worse exactly
where it is being read. Per-event spectra from a +-25 ms window are short and
noisy, so the PSD panel defaults to the CLASS AVERAGE, where the fit is worth
trusting; per-event fits are still exported with their R^2 so a bad one is
visible rather than silent.

MEASURED AGAINST EACH EVENT'S OWN BASELINE
==========================================
Absolute uV^2/Hz depends on the contact, so the statistic is dB of the event
window's band power against a baseline window on the same contact of the same
event, taken `baseline -ms` before the stamp. The comparison is then "how far
above its own background did this event go".

THE RAIL BIASES DOWNWARD HERE, NOT UPWARD
=========================================
v4 had to worry that clipping inflates a maximum. Measured, clipping REDUCES
250-500 Hz power (x0.91 at a 1200 uV limit, x0.62 at 800, x0.47 at 500),
because flattening a peak destroys the fast edges that carry the energy. The
IED numbers here are therefore if anything under-estimates -- a safer
direction than v4's, but still a bias, and still on the class that clips most.

RUN
===
  python ied_ampwidth_gui_v5.py           (first run builds an HF cache, ~45 s)
  python ied_ampwidth_gui_v5.py --category curated
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import to_rgba
from matplotlib.widgets import Button, CheckButtons, RadioButtons, Slider, TextBox
from scipy.signal import spectrogram

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from ied_ds import ANAT, BAD_CHANNELS, DS_BANK, NCS_FOLDER, Probe64  # noqa: E402
from ied_ds_hf import (BASELINE_OFFSET_MS, BASELINE_WIN_MS, FIT_RANGE,  # noqa: E402
                       HF_BAND, HF_HALF_MS, HF_LOWPASS, HF_Q, HFMeasure,
                       band_power, build_hf_store, db, fit_fooof, psd)

INK = "#1b2220"
BADC = "#c0392b"
IEDC = "#b8620a"
DSC = "#1f6feb"
WINC = "#0b7a63"
CLASS_C = {"IED": IEDC, "DS": DSC}
PSD_SRC = ("class average", "this event")

PICKS = os.path.join(_HERE, "ied_ds_v5_centres.csv")
OUT_EVENTS = os.path.join(_HERE, "ied_ds_v5_event_stats.csv")
OUT_PROFILE = os.path.join(_HERE, "ied_ds_v5_channel_profile.csv")


class Bench:
    def __init__(self, args):
        self.args = args
        self.band = HF_BAND
        self.win_ms = args.win_ms
        self.view_ms = args.view_ms
        self.search_ms = args.search_ms
        self.base_off = args.baseline_ms
        self.gain = 1.0
        self.kind = "IED"
        self.pos = {"IED": 0, "DS": 0}
        self.psd_src = PSD_SRC[0]
        self.show_fit = True
        self._ver = 0
        self._note = ""
        self._cache = {}

        self.p = Probe64(args.folder, BAD_CHANNELS, args.anat)
        self._build()
        _, self.st = build_hf_store(self.p, category=args.category,
                                    progress=self._progress,
                                    refresh=args.refresh)
        self.hm = HFMeasure(self.st, self.p, self.band, self.win_ms,
                            self.base_off, BASELINE_WIN_MS)
        n = len(self.st)
        self.shift = np.zeros(n, dtype=int)
        self.hand = np.zeros(n, dtype=bool)
        self.centre_all(initial=True)
        self.draw()

    # -------------------------------------------------------------- centres
    def centre_all(self, initial=False):
        keep, old = self.hand.copy(), self.shift.copy()
        self.shift, _ = self.st.centre_all(
            np.zeros(len(self.st), dtype=int), self.search_ms,
            "mean|amp| peak", True)
        if not initial:
            self.shift[keep] = old[keep]
        self._bump()
        if not initial:
            self.draw()

    def _bump(self):
        self._ver += 1
        self._cache = {}
        self.hm.band = self.band
        self.hm.win_ms = self.win_ms
        self.hm.base_offset_ms = self.base_off
        self.hm._env = {}

    def reset_one(self):
        i = self.cur
        self.shift[i], self.hand[i] = 0, False
        self._bump()
        self.draw()

    # ---------------------------------------------------------------- state
    @property
    def order(self):
        return self.st.where(self.kind)

    @property
    def cur(self):
        o = self.order
        return int(o[self.pos[self.kind] % len(o)])

    def stats(self, kind):
        """(hf_db[n,64], hf_abs[n,64], best_contact[n]) cached per settings."""
        key = ("stats", kind, self.band, self.win_ms, self.base_off, self._ver)
        got = self._cache.get(key)
        if got is None:
            idx = self.st.where(kind)
            got = self.hm.measure_all(idx, self.shift[idx])
            self._cache[key] = got
        return got

    def best_db(self, kind):
        """Best contact's dB per event; NaN where nothing was measurable.

        An event whose baseline window fell outside the cache has an all-NaN
        row, and np.nanmax warns and returns NaN for it. NaN is the right
        answer -- it is dropped downstream -- so the row is detected rather
        than the warning suppressed, which would also hide real all-NaN rows.
        """
        D, _, _ = self.stats(kind)
        out = np.full(D.shape[0], np.nan)
        ok = np.isfinite(D).any(axis=1)
        if ok.any():
            out[ok] = np.nanmax(D[ok], axis=1)
        return out

    def avg_psd(self, kind, nperseg=256):
        key = ("psd", kind, self.win_ms, self._ver)
        got = self._cache.get(key)
        if got is None:
            idx = self.st.where(kind)
            acc = None
            for i in idx:
                f, P = self.hm.event_psd(int(i), self.shift[i], nperseg)
                acc = P if acc is None else acc + P
            got = (f, acc / max(len(idx), 1))
            self._cache[key] = got
        return got

    # ---------------------------------------------------------------- build
    def _build(self):
        self.fig = plt.figure(figsize=(19.0, 10.4), facecolor="white")
        self.fig.canvas.manager.set_window_title(
            "IED vs DS -- high-frequency power (v5)")
        self.ax_stack = self.fig.add_axes([0.042, 0.375, 0.160, 0.555])
        self.ax_env = self.fig.add_axes([0.042, 0.280, 0.160, 0.080])
        self.ax_spec = self.fig.add_axes([0.243, 0.375, 0.180, 0.555])
        self.ax_envavg = self.fig.add_axes([0.243, 0.280, 0.180, 0.080])
        self.ax_prof = self.fig.add_axes([0.487, 0.280, 0.105, 0.650])
        self.ax_psd = self.fig.add_axes([0.635, 0.555, 0.160, 0.375])
        self.ax_cmp = self.fig.add_axes([0.635, 0.280, 0.160, 0.205])

        self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        b = lambda l, t, w, h: self.fig.add_axes([l, t, w, h])

        self.r_kind = RadioButtons(b(0.040, 0.145, 0.046, 0.072), ("IED", "DS"))
        self.r_kind.on_clicked(self.on_kind)
        self.fig.text(0.040, 0.223, "class", fontsize=8, color=INK)

        self.b_prev = Button(b(0.094, 0.183, 0.034, 0.033), "< prev")
        self.b_next = Button(b(0.132, 0.183, 0.034, 0.033), "next >")
        self.b_prev.on_clicked(lambda _: self.step(-1))
        self.b_next.on_clicked(lambda _: self.step(+1))
        self.t_jump = TextBox(b(0.104, 0.145, 0.032, 0.033), "id ", initial="")
        self.t_jump.on_submit(self.on_jump)
        self.b_reset = Button(b(0.146, 0.145, 0.030, 0.033), "reset")
        self.b_reset.on_clicked(lambda _: self.reset_one())
        self.b_exp = Button(b(0.180, 0.145, 0.034, 0.033), "export")
        self.b_exp.on_clicked(lambda _: self.export())

        # No band sliders: the band is FIXED at HF_BAND. It is part of what
        # the measurement is, and one that moves while numbers are being read
        # makes two runs incomparable unless both recorded which band they used.
        self.fig.text(0.268, 0.200, "band  %.0f-%.0f Hz  (fixed)" % HF_BAND,
                      fontsize=9, color=INK, fontweight="bold")
        self.s_win = Slider(b(0.268, 0.160, 0.100, 0.018), "window ±ms",
                            5.0, 100.0, valinit=self.win_ms, valfmt="%.0f")
        self.s_base = Slider(b(0.268, 0.125, 0.100, 0.018), "baseline -ms",
                             60.0, 170.0, valinit=self.base_off, valfmt="%.0f")
        self.s_view = Slider(b(0.268, 0.090, 0.100, 0.018), "view ±ms",
                             20.0, 190.0, valinit=self.view_ms, valfmt="%.0f")
        for s, cb in ((self.s_win, self.on_win), (self.s_base, self.on_base),
                      (self.s_view, self.on_view)):
            s.on_changed(cb)

        self.r_psd = RadioButtons(b(0.430, 0.145, 0.080, 0.072), PSD_SRC)
        self.r_psd.on_clicked(self.on_psdsrc)
        self.fig.text(0.430, 0.223, "PSD / FOOOF from", fontsize=8, color=INK)

        self.c_opt = CheckButtons(b(0.530, 0.150, 0.075, 0.062),
                                  ["FOOOF fit", "flattened"], [True, True])
        self.c_opt.on_clicked(self.on_opt)

        self.txt = self.fig.text(0.806, 0.930, "", fontsize=8.2, color=INK,
                                 va="top", family="monospace")
        self.stat_txt = self.fig.text(0.040, 0.048, "", fontsize=8.5,
                                      color=INK, va="top", family="monospace")
        self.show_flat = True

    def _progress(self, i, n, msg):
        self.stat_txt.set_text(
            "building the HF store  [%d/%d]  %s\n"
            "(v5 needs 250-2000 Hz, which the 300 Hz store does not have,\n"
            " so it reads its own cache once: ~45 s)" % (i, n, msg))
        try:
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()
        except Exception:
            pass

    # ------------------------------------------------------------ callbacks
    def on_click(self, ev):
        if ev.inaxes is not self.ax_stack or ev.xdata is None:
            return
        tb = getattr(self.fig.canvas.manager, "toolbar", None)
        if tb is not None and getattr(tb, "mode", ""):
            return
        i = self.cur
        self.shift[i] += int(round(ev.xdata * 1e-3 * self.st.fs))
        self.hand[i] = True
        self._bump()
        self.draw()

    def on_key(self, ev):
        k = ev.key
        if k == "right":
            self.step(+1)
        elif k == "left":
            self.step(-1)
        elif k == "tab":
            self.on_kind("DS" if self.kind == "IED" else "IED")
            self.r_kind.set_active(0 if self.kind == "IED" else 1)
        elif k == "r":
            self.reset_one()
        elif k == "e":
            self.export()

    def on_kind(self, label):
        self.kind = label
        self.draw()

    def step(self, d):
        self.pos[self.kind] = (self.pos[self.kind] + d) % len(self.order)
        self.draw()

    def on_jump(self, text):
        try:
            want = int(str(text).strip())
        except ValueError:
            return
        hit = np.where(self.st.ids[self.order] == want)[0]
        if hit.size:
            self.pos[self.kind] = int(hit[0])
        self.draw()

    @staticmethod
    def _drag(s):
        return bool(getattr(s, "drag_active", False))

    def on_win(self, v):
        self.win_ms = float(v)
        if self._drag(self.s_win):
            return
        self._bump(); self.draw()

    def on_base(self, v):
        self.base_off = float(v)
        if self._drag(self.s_base):
            return
        self._bump(); self.draw()

    def on_view(self, v):
        self.view_ms = min(float(v), self.st.half_ms - 5.0)
        if self._drag(self.s_view):
            return
        self.draw()

    def on_psdsrc(self, label):
        self.psd_src = label
        self.draw()

    def on_opt(self, label):
        st = dict(zip(["FOOOF fit", "flattened"], self.c_opt.get_status()))
        self.show_fit, self.show_flat = st["FOOOF fit"], st["flattened"]
        self.draw()

    # --------------------------------------------------------------- output
    def export(self):
        rows, prof = [], []
        for kind in ("IED", "DS"):
            idx = self.st.where(kind)
            D, A, W = self.stats(kind)
            for j, i in enumerate(idx):
                wc = int(self.p.numbers[W[j]]) if W[j] >= 0 else -1
                f, P = self.hm.event_psd(int(i), self.shift[i], 256)
                r = fit_fooof(f, P[:, W[j]]) if W[j] >= 0 else None
                rows.append({
                    "kind": kind, "id": int(self.st.ids[i]),
                    "t_s": float(self.st.t_s[i]),
                    "centre_s": float(self.st.t_s[i]) + self.shift[i] / self.st.fs,
                    "shift_ms": self.shift[i] / self.st.fs * 1e3,
                    "hand_placed": bool(self.hand[i]),
                    "hf_db_best": float(np.nanmax(D[j])) if np.isfinite(D[j]).any() else np.nan,
                    "hf_abs_best": float(A[j, W[j]]) if W[j] >= 0 else np.nan,
                    "hf_contact_csc": wc,
                    "hf_region": self.p.region.get(wc, ""),
                    "band_lo_hz": self.band[0], "band_hi_hz": self.band[1],
                    "window_ms": self.win_ms, "baseline_offset_ms": self.base_off,
                    "fooof_exponent": r["exponent"] if r else np.nan,
                    "fooof_offset": r["offset"] if r else np.nan,
                    "fooof_r2": r["r2"] if r else np.nan,
                    "fooof_hf_peak_hz": r["hf_peak_cf"] if r else np.nan,
                    "fooof_hf_peak_pw": r["hf_peak_pw"] if r else np.nan,
                    "fit_range_hz": "%g-%g" % FIT_RANGE,
                    "fs_hz": self.st.fs, "lowpass_hz": self.st.lowpass,
                    "n_channels": int(self.p.included.sum()),
                })
                for c, n in enumerate(self.p.numbers):
                    prof.append({"kind": kind, "id": int(self.st.ids[i]),
                                 "csc": int(n),
                                 "region": self.p.region.get(int(n), ""),
                                 "included": bool(self.p.included[c]),
                                 "hf_db": D[j, c], "hf_abs": A[j, c],
                                 "band_lo_hz": self.band[0],
                                 "band_hi_hz": self.band[1]})
        pd.DataFrame(rows).to_csv(OUT_EVENTS, index=False)
        pd.DataFrame(prof).to_csv(OUT_PROFILE, index=False)
        self.draw(note="exported %d events -> %s"
                       % (len(rows), os.path.basename(OUT_EVENTS)))

    # -------------------------------------------------------------- drawing
    def draw(self, note=""):
        self._stack()
        self._envelope()
        self._spectrogram()
        self._env_average()
        self._profile()
        self._psd()
        self._compare()
        self._readout(note)
        self.fig.canvas.draw_idle()

    def _peak_contact(self):
        D, _, W = self.stats(self.kind)
        j = self.pos[self.kind] % len(self.order)
        return int(W[j]) if W[j] >= 0 else 0

    def _stack(self):
        ax = self.ax_stack
        ax.clear()
        i = self.cur
        y = self.st.slice_(i, self.shift[i], self.view_ms)
        t = (np.arange(y.shape[0]) - y.shape[0] // 2) / self.st.fs * 1e3
        per = np.nanpercentile(np.abs(y - np.nanmedian(y, axis=0)), 99.0, axis=0)
        step = max(2.0 * float(np.nanmedian(per)) / self.gain, 1e-6)
        w = self._peak_contact()
        cols, lws = [], []
        for k in range(y.shape[1]):
            if k == w:
                cols.append(to_rgba(WINC, 1.0)); lws.append(1.6)
            elif not self.p.included[k]:
                cols.append(to_rgba(BADC, 0.45)); lws.append(0.7)
            else:
                cols.append(to_rgba(CLASS_C[self.kind], 1.0)); lws.append(0.75)
        ax.add_collection(LineCollection(
            [np.column_stack((t, y[:, k] - k * step)) for k in range(y.shape[1])],
            colors=cols, linewidths=lws, zorder=3))
        ax.axvline(0.0, color="#333333", lw=1.2, zorder=6)
        ax.axvspan(-self.win_ms, self.win_ms,
                   color=CLASS_C[self.kind], alpha=0.09, zorder=0)
        ticks = list(range(0, y.shape[1], 4))
        ax.set_yticks([-k * step for k in ticks])
        ax.set_yticklabels([self.p.label(k) for k in ticks], fontsize=6)
        ax.set_ylim(-(y.shape[1] - 0.2) * step, step)
        ax.set_xlim(-self.view_ms, self.view_ms)
        ax.set_xticklabels([])
        ax.set_title("%s   wideband (to %.0f Hz)\npeak HF contact %s"
                     % (self.st.label(i), self.st.lowpass, self.p.label(w)),
                     fontsize=9)

    def _envelope(self):
        ax = self.ax_env
        ax.clear()
        i, w = self.cur, self._peak_contact()
        env = self.hm.envelope(i)[:, w]
        h = int(round(self.view_ms * 1e-3 * self.st.fs))
        c = self.st.stamp_i + int(self.shift[i])
        lo, hi = c - h, c + h + 1
        y = np.full(2 * h + 1, np.nan)
        a, bq = max(0, lo), min(len(env), hi)
        y[a - lo:bq - lo] = env[a:bq]
        t = (np.arange(len(y)) - h) / self.st.fs * 1e3
        ax.plot(t, y, lw=1.0, color=CLASS_C[self.kind])
        ax.axvline(0.0, color="#333333", lw=1.2)
        ax.axvspan(-self.win_ms, self.win_ms, color=CLASS_C[self.kind],
                   alpha=0.10, lw=0)
        ax.axvspan(-self.base_off - BASELINE_WIN_MS / 2,
                   -self.base_off + BASELINE_WIN_MS / 2,
                   color="#777777", alpha=0.18, lw=0)
        ax.set_xlim(-self.view_ms, self.view_ms)
        ax.set_ylabel("%.0f-%.0f Hz\nenv µV" % self.band, fontsize=6.5)
        ax.set_xlabel("ms from centre   (grey = baseline window)", fontsize=8)
        ax.tick_params(labelsize=7)

    def _spectrogram(self):
        """Time x frequency, in dB against this event's own baseline window."""
        ax = self.ax_spec
        ax.clear()
        i, w = self.cur, self._peak_contact()
        x = self.st.trace(i)[:, w]
        fs = self.st.fs
        nper = 64
        f, tt, S = spectrogram(x, fs=fs, nperseg=nper, noverlap=nper - 8,
                               scaling="density", mode="psd")
        c = self.st.stamp_i + int(self.shift[i])
        t_ms = (tt * fs - c) / fs * 1e3
        # Baseline: the same contact's spectrum in the grey window.
        bm = np.abs(t_ms + self.base_off) <= BASELINE_WIN_MS / 2
        base = np.median(S[:, bm], axis=1) if bm.sum() > 2 else np.median(S, axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            Z = 10 * np.log10(S / base[:, None])
        keep = (f >= 50) & (f <= min(2000.0, fs / 2 - 50))
        m = np.abs(t_ms) <= self.view_ms
        im = ax.pcolormesh(t_ms[m], f[keep], Z[np.ix_(keep, m)],
                           cmap="magma", vmin=-5, vmax=40, shading="nearest")
        ax.axhspan(self.band[0], self.band[1], facecolor="none",
                   edgecolor="#00e5ff", lw=1.4, ls="--")
        ax.axvline(0.0, color="white", lw=1.0, alpha=0.8)
        ax.set_xlim(-self.view_ms, self.view_ms)
        ax.set_ylabel("Hz", fontsize=8.5)
        ax.set_xticklabels([])
        ax.set_title("%s  dB re baseline\n(cyan = the band being integrated)"
                     % self.p.label(w), fontsize=9)
        if not hasattr(self, "_cb"):
            self._cb = self.fig.colorbar(im, ax=ax, pad=0.01, fraction=0.045)
            self._cb.ax.tick_params(labelsize=6.5)
        else:
            self._cb.update_normal(im)

    def _env_average(self):
        ax = self.ax_envavg
        ax.clear()
        h = int(round(self.view_ms * 1e-3 * self.st.fs))
        for kind in ("IED", "DS"):
            idx = self.st.where(kind)
            _, _, W = self.stats(kind)
            A = np.full((len(idx), 2 * h + 1), np.nan)
            for j, i in enumerate(idx):
                w = int(W[j]) if W[j] >= 0 else 0
                env = self.hm.envelope(int(i))[:, w]
                c = self.st.stamp_i + int(self.shift[i])
                lo, hi = c - h, c + h + 1
                a, bq = max(0, lo), min(len(env), hi)
                A[j, a - lo:bq - lo] = env[a:bq]
            t = (np.arange(A.shape[1]) - h) / self.st.fs * 1e3
            mu = np.nanmean(A, axis=0)
            se = np.nanstd(A, axis=0) / max(np.sqrt(len(idx)), 1)
            ax.fill_between(t, mu - se, mu + se, color=CLASS_C[kind],
                            alpha=0.22, lw=0)
            ax.plot(t, mu, lw=1.5, color=CLASS_C[kind], label=kind)
        ax.axvline(0.0, color="#333333", lw=1.2)
        ax.set_xlim(-self.view_ms, self.view_ms)
        ax.set_xlabel("ms from centre   (class-average HF envelope ± SEM)",
                      fontsize=8)
        ax.set_ylabel("µV", fontsize=7)
        ax.tick_params(labelsize=7)
        ax.legend(fontsize=7, framealpha=0.9, loc="upper right")

    def _profile(self):
        ax = self.ax_prof
        ax.clear()
        k = np.arange(len(self.p.numbers))
        inc = self.p.included
        for kind in ("IED", "DS"):
            D, _, _ = self.stats(kind)
            mu = np.full(D.shape[1], np.nan)
            se = np.full(D.shape[1], np.nan)
            with np.errstate(invalid="ignore"):
                mu[inc] = np.nanmean(D[:, inc], axis=0)
                se[inc] = np.nanstd(D[:, inc], axis=0) / max(np.sqrt(D.shape[0]), 1)
            ax.plot(mu, k, "-", lw=1.4, color=CLASS_C[kind],
                    label="%s (n=%d)" % (kind, D.shape[0]))
            ax.fill_betweenx(k, mu - se, mu + se, color=CLASS_C[kind],
                             alpha=0.22, lw=0)
        for c in np.where(~inc)[0]:
            ax.axhline(c, color=BADC, lw=0.8, alpha=0.5)
        ax.axvline(0.0, color="#888888", lw=0.8, ls=":")
        ax.invert_yaxis()
        ax.set_yticks(range(0, len(k), 4))
        ax.set_yticklabels([self.p.label(i) for i in range(0, len(k), 4)],
                           fontsize=6)
        ax.set_xlabel("dB re baseline", fontsize=8.5)
        ax.set_title("%.0f-%.0f Hz per contact\n(mean ± SEM)" % self.band,
                     fontsize=9)
        ax.legend(fontsize=7, loc="lower right", framealpha=0.9)

    def _psd(self):
        ax = self.ax_psd
        ax.clear()
        self._fits = {}
        for kind in ("IED", "DS"):
            if self.psd_src == "this event" and kind != self.kind:
                continue
            if self.psd_src == "this event":
                i = self.cur
                f, P = self.hm.event_psd(i, self.shift[i], 256)
                w = self._peak_contact()
                spec = P[:, w]
                lab = "%s (CSC%d)" % (self.st.label(i), self.p.numbers[w])
            else:
                f, P = self.avg_psd(kind)
                D, _, W = self.stats(kind)
                w = int(np.bincount(W[W >= 0], minlength=P.shape[1]).argmax())
                spec = P[:, w]
                lab = "%s avg (CSC%d)" % (kind, self.p.numbers[w])
            m = (f >= FIT_RANGE[0]) & (f <= FIT_RANGE[1]) & (spec > 0)
            ax.loglog(f[m], spec[m], lw=1.3, color=CLASS_C[kind], label=lab)
            r = fit_fooof(f, spec) if self.show_fit else None
            self._fits[kind] = r
            if r is not None:
                ff = r["freqs"]
                ax.loglog(ff, 10 ** r["ap_fit"], lw=1.1, ls="--",
                          color=CLASS_C[kind], alpha=0.8)
                ax.loglog(ff, 10 ** r["fit"], lw=1.0, ls=":", color="#333333",
                          alpha=0.7)
                if self.show_flat:
                    # The flattened spectrum, scaled onto the same axes: this
                    # is the panel's real payload -- a bump here in the shaded
                    # band is an oscillation, flat here means the band power is
                    # only broadband energy on a raised 1/f.
                    base = np.nanmin(spec[m]) if m.any() else 1.0
                    ax.loglog(ff, base * 10 ** (r["flat"] * 2.0), lw=1.2,
                              color=WINC, alpha=0.85,
                              label="flattened x2" if kind == self.kind else None)
        ax.axvspan(self.band[0], self.band[1], color="#00a0c0", alpha=0.12, lw=0)
        ax.set_xticks([100, 200, 500, 1000, 2000])
        ax.set_xticklabels(["100", "200", "500", "1k", "2k"])
        ax.minorticks_off()
        ax.set_xlabel("Hz", fontsize=8.5)
        ax.set_ylabel("µV²/Hz", fontsize=8.5)
        ax.set_title("spectrum + FOOOF  (%s)\ndashed = aperiodic 1/f fit"
                     % self.psd_src, fontsize=9)
        ax.legend(fontsize=6.5, framealpha=0.9, loc="lower left")
        ax.tick_params(labelsize=7)

    def _compare(self):
        ax = self.ax_cmp
        ax.clear()
        rng = np.random.default_rng(0)
        self._summary = []
        for j, kind in enumerate(("IED", "DS")):
            S = self.best_db(kind)
            S = S[np.isfinite(S)]
            if S.size == 0:
                continue
            bp = ax.boxplot([S], positions=[j], widths=0.44, whis=(5, 95),
                            showfliers=False, patch_artist=True,
                            manage_ticks=False)
            for p_ in bp["boxes"]:
                p_.set(facecolor=CLASS_C[kind], alpha=0.25,
                       edgecolor=CLASS_C[kind], lw=1.3)
            for part in ("whiskers", "caps", "medians"):
                for p_ in bp[part]:
                    p_.set(color=CLASS_C[kind], lw=1.5)
            show = S if S.size <= 120 else rng.choice(S, 120, replace=False)
            ax.plot(j + (rng.random(show.size) - 0.5) * 0.30, show, "o",
                    ms=2.6, color=CLASS_C[kind], alpha=0.45, mec="none")
            self._summary.append((kind, S.size, float(np.median(S)),
                                  float(np.percentile(S, 25)),
                                  float(np.percentile(S, 75)), S))
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["IED", "DS"], fontsize=9)
        ax.set_xlim(-0.6, 1.6)
        ax.axhline(0.0, color="#888888", lw=0.8, ls=":")
        ax.set_ylabel("dB re baseline", fontsize=8.5)
        ax.set_title("best contact, %.0f-%.0f Hz" % self.band, fontsize=9)
        ax.tick_params(labelsize=7)

    def _readout(self, note=""):
        L = ["band   %.0f-%.0f Hz  win ±%.0f ms  base -%.0f ms"
             % (self.band[0], self.band[1], self.win_ms, self.base_off),
             "data   fs %.0f Hz  LP %.0f Hz  %d/%d contacts"
             % (self.st.fs, self.st.lowpass, self.p.included.sum(),
                len(self.p.numbers)),
             ""]
        for (kind, n, med, q1, q3, _) in getattr(self, "_summary", []):
            L.append("%-4s n=%3d med %+6.2f dB  IQR %+.1f..%+.1f"
                     % (kind, n, med, q1, q3))
        sm = getattr(self, "_summary", [])
        if len(sm) == 2:
            a, b = sm[0][5], sm[1][5]
            L.append("")
            try:
                from scipy.stats import mannwhitneyu
                U, pv = mannwhitneyu(a, b, alternative="two-sided")
                d = 2.0 * (U / (len(a) * len(b))) - 1.0
                L.append("Mann-Whitney p=%.3g  delta %+0.3f" % (pv, d))
                L.append("difference %+.2f dB  = x%.1f power"
                         % (sm[0][2] - sm[1][2], 10 ** ((sm[0][2] - sm[1][2]) / 10)))
            except Exception as exc:
                L.append("test unavailable: %s" % exc)
        fits = getattr(self, "_fits", {})
        if fits:
            L.append("")
            L.append("FOOOF, fit %g-%g Hz:" % FIT_RANGE)
            for kind, r in fits.items():
                if r is None:
                    L.append("  %-4s fit failed" % kind)
                    continue
                pk = ("no peak in band" if not np.isfinite(r["hf_peak_cf"])
                      else "peak %.0f Hz pw %.2f" % (r["hf_peak_cf"],
                                                    r["hf_peak_pw"]))
                L.append("  %-4s exp %.2f off %.2f R2 %.3f" 
                         % (kind, r["exponent"], r["offset"], r["r2"]))
                L.append("       %s" % pk)
            L.append("  exp/offset = broadband; peak = oscillation")
        if note or self._note:
            L.append("")
            L.append(note or self._note)
        self.txt.set_text("\n".join(L))

        i = self.cur
        D, _, W = self.stats(self.kind)
        j = self.pos[self.kind] % len(self.order)
        w = int(W[j]) if W[j] >= 0 else -1
        self.stat_txt.set_text(
            "%s   t=%.3f s   centre %+.2f ms   %.0f-%.0f Hz = %+.2f dB on %s"
            % (self.st.label(i), self.st.t_s[i],
               self.shift[i] / self.st.fs * 1e3, self.band[0], self.band[1],
               np.nanmax(D[j]) if np.isfinite(D[j]).any() else np.nan,
               self.p.label(w) if w >= 0 else "--"))


def main():
    ap = argparse.ArgumentParser(description="IED vs DS, high-frequency power")
    ap.add_argument("--folder", default=NCS_FOLDER)
    ap.add_argument("--ds-bank", default=DS_BANK)
    ap.add_argument("--anat", default=ANAT)
    ap.add_argument("--category", default="Solid")
    ap.add_argument("--win-ms", type=float, default=25.0)
    ap.add_argument("--view-ms", type=float, default=100.0)
    ap.add_argument("--search-ms", type=float, default=50.0)
    ap.add_argument("--baseline-ms", type=float, default=BASELINE_OFFSET_MS)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    Bench(args)
    plt.show()


if __name__ == "__main__":
    main()
