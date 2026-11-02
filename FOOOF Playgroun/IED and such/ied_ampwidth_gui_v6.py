"""
ied_ampwidth_gui_v6.py -- largest amplitude and its half-width, per event,
and the PCA that asks whether those two separate IEDs from dentate spikes.

WHAT IT DOES
============
Per event, after centring: find the largest good contact, then measure that
contact's amplitude and its half-width at half-amplitude. Two numbers per
event. Then PCA them, colour by class, and ask whether the classes sit in
different parts of the cloud.

The half-width comes from `ied_ampwidth.measure_peak` -- v1's code, unchanged
-- so the level is taken from a real baseline rather than from zero, and a
crossing the search never found is flagged `unresolved` rather than
interpolated at the window edge and reported as a number.

CLICK A POINT
=============
Click any dot in the scatter or the PCA and the left panels jump to that
event: its stack with the winning contact in green, and that contact drawn
alone with its baseline, its half-amplitude level and the two crossings the
width is measured between. A cluster is only worth believing once you have
looked at the events at its edges, and an outlier in the scatter is usually a
measurement to check rather than a discovery.

WHAT PCA CAN AND CANNOT TELL YOU HERE
=====================================
With two features PCA is a ROTATION. PC1 and PC2 hold exactly the information
in the amplitude/half-width scatter, on turned axes, and no separation can
appear in one that is absent from the other. Both are drawn side by side so
that is visible rather than taken on trust.

More importantly, PCA is unsupervised: it finds the directions of greatest
VARIANCE, which are not the directions that separate the classes, and it never
sees the labels. So an LDA axis -- which does see them -- is reported next to
it. On this data the gap is large and instructive: with all features enabled
PC1 reaches AUC 0.36 while LDA reaches 0.78, which means the biggest source of
variance in these events is not what distinguishes an IED from a dentate
spike.

AUC, NOT ACCURACY
=================
13 IEDs against 296 dentate spikes. A classifier that answers "DS" every time
is 96% accurate, so accuracy is meaningless here; every separability number in
this panel is a rank AUC, which is the probability that a randomly chosen IED
scores above a randomly chosen DS. 0.5 is chance in either direction, and a
feature at 0.32 separates exactly as well as one at 0.68 -- it just points the
other way.

RUN
===
  python ied_ampwidth_gui_v6.py
  python ied_ampwidth_gui_v6.py --baseline prominence
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import to_rgba
from matplotlib.widgets import Button, CheckButtons, RadioButtons, Slider, TextBox

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from ied_ampwidth import BASELINES                                # noqa: E402
from ied_ds import ANAT, BAD_CHANNELS, DS_BANK, NCS_FOLDER, Probe64  # noqa: E402
from ied_ds_features import (ALL_FEATURES, CORE, EXTRA, HF_FEATURE,  # noqa: E402
                             all_features, attach_hf, auc, build_store,
                             event_features, run_pca)

INK = "#1b2220"
BADC = "#c0392b"
IEDC = "#b8620a"
DSC = "#1f6feb"
WINC = "#0b7a63"
CLASS_C = {"IED": IEDC, "DS": DSC}
MAXC = "#b8620a"
MINC = "#1a7f37"

OUT = os.path.join(_HERE, "ied_ds_v6_features.csv")


class Bench:
    def __init__(self, args):
        self.args = args
        self.win_ms = args.win_ms
        self.cross_ms = args.cross_ms
        self.view_ms = args.view_ms
        self.baseline = args.baseline
        self.search_ms = args.search_ms
        self.kind = "IED"
        self.sel = 0                      # row in self.tab
        self.feats = list(CORE)
        self.hf_loaded = False
        self._note = ""

        self.p = Probe64(args.folder, BAD_CHANNELS, args.anat)
        self._build()
        _, self.st = build_store(self.p, category=args.category,
                                 progress=self._progress, refresh=args.refresh)
        self.shift, _ = self.st.centre_all(
            np.zeros(len(self.st), dtype=int), self.search_ms,
            "mean|amp| peak", True)
        self.recompute()
        self.draw()

    # ------------------------------------------------------------- features
    def recompute(self):
        self.tab, self.dropped = all_features(
            self.st, self.p, self.shift, win_ms=self.win_ms,
            cross_ms=self.cross_ms, baseline=self.baseline)
        if self.hf_loaded and getattr(self, "_hfcol", None):
            self.tab[HF_FEATURE] = [
                self._hfcol.get((k, i), np.nan)
                for k, i in zip(self.tab["kind"], self.tab["id"])]
        self.fit()

    def fit(self):
        use = [f for f in self.feats if f in self.tab.columns]
        self.missing = [f for f in self.feats if f not in self.tab.columns]
        self.used = use
        self.pca = run_pca(self.tab, use) if len(use) >= 2 else None

    def _load_hf(self):
        if self.hf_loaded:
            return
        self._progress(0, 1, "loading v5's 500-1000 Hz store ...")
        t = attach_hf(self.tab, self.p, category=self.args.category,
                      win_ms=self.win_ms, progress=self._progress)
        self._hfcol = {(k, i): v for k, i, v in
                       zip(t["kind"], t["id"], t[HF_FEATURE])}
        self.hf_loaded = True
        self._progress(1, 1, "")

    # ---------------------------------------------------------------- state
    @property
    def row(self):
        if not len(self.tab):
            return None
        return self.tab.iloc[self.sel % len(self.tab)]

    # ---------------------------------------------------------------- build
    def _build(self):
        self.fig = plt.figure(figsize=(18.5, 10.2), facecolor="white")
        self.fig.canvas.manager.set_window_title(
            "IED vs DS -- amplitude, half-width, PCA (v6)")
        self.ax_stack = self.fig.add_axes([0.048, 0.315, 0.150, 0.615])
        self.ax_det = self.fig.add_axes([0.235, 0.315, 0.195, 0.615])
        self.ax_scat = self.fig.add_axes([0.480, 0.560, 0.200, 0.370])
        self.ax_pca = self.fig.add_axes([0.480, 0.085, 0.200, 0.370])
        self.ax_load = self.fig.add_axes([0.725, 0.560, 0.180, 0.370])

        self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        b = lambda l, t, w, h: self.fig.add_axes([l, t, w, h])

        self.b_prev = Button(b(0.048, 0.235, 0.034, 0.032), "< prev")
        self.b_next = Button(b(0.086, 0.235, 0.034, 0.032), "next >")
        self.b_prev.on_clicked(lambda _: self.step(-1))
        self.b_next.on_clicked(lambda _: self.step(+1))
        self.b_cls = Button(b(0.124, 0.235, 0.048, 0.032), "next IED")
        self.b_cls.on_clicked(lambda _: self.next_class())
        self.b_exp = Button(b(0.176, 0.235, 0.034, 0.032), "export")
        self.b_exp.on_clicked(lambda _: self.export())

        self.r_base = RadioButtons(b(0.048, 0.090, 0.075, 0.105), BASELINES,
                                   active=BASELINES.index(self.baseline))
        self.r_base.on_clicked(self.on_base)
        self.fig.text(0.048, 0.200, "half-width baseline", fontsize=8, color=INK)

        self.s_win = Slider(b(0.190, 0.165, 0.095, 0.018), "peak ±ms",
                            2.0, 60.0, valinit=self.win_ms, valfmt="%.0f")
        self.s_cross = Slider(b(0.190, 0.132, 0.095, 0.018), "cross ±ms",
                              5.0, 120.0, valinit=self.cross_ms, valfmt="%.0f")
        self.s_view = Slider(b(0.190, 0.099, 0.095, 0.018), "view ±ms",
                             20.0, 190.0, valinit=self.view_ms, valfmt="%.0f")
        self.s_win.on_changed(self.on_win)
        self.s_cross.on_changed(self.on_cross)
        self.s_view.on_changed(self.on_view)

        names = list(ALL_FEATURES) + [HF_FEATURE]
        self.c_feat = CheckButtons(
            b(0.315, 0.070, 0.105, 0.150), names,
            [f in self.feats for f in names])
        self.c_feat.on_clicked(self.on_feat)
        self.fig.text(0.315, 0.225, "features in the PCA", fontsize=8, color=INK)

        self.txt = self.fig.text(0.725, 0.500, "", fontsize=8.5, color=INK,
                                 va="top", family="monospace")
        self.stat_txt = self.fig.text(0.048, 0.035, "", fontsize=8.5,
                                      color=INK, va="top", family="monospace")

    def _progress(self, i, n, msg):
        self.stat_txt.set_text("[%d/%d] %s" % (i, n, msg))
        try:
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()
        except Exception:
            pass

    # ------------------------------------------------------------ callbacks
    def on_click(self, ev):
        if ev.xdata is None or ev.inaxes not in (self.ax_scat, self.ax_pca):
            return
        tb = getattr(self.fig.canvas.manager, "toolbar", None)
        if tb is not None and getattr(tb, "mode", ""):
            return
        if ev.inaxes is self.ax_scat:
            X = self.tab[self.feats[0]].to_numpy(dtype=float)
            Y = self.tab[self.feats[1]].to_numpy(dtype=float) \
                if len(self.feats) > 1 else np.zeros(len(self.tab))
            rows = np.arange(len(self.tab))
        else:
            if self.pca is None:
                return
            X = self.pca["scores"][:, 0]
            Y = (self.pca["scores"][:, 1] if self.pca["scores"].shape[1] > 1
                 else np.zeros(len(X)))
            rows = np.where(self.pca["keep"])[0]
        # Nearest in AXES units, not data units: the two axes have different
        # scales and ranges, so a plain Euclidean distance in data units picks
        # whatever is nearest along the bigger-numbered axis.
        ax = ev.inaxes
        (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
        sx, sy = (x1 - x0) or 1.0, (y1 - y0) or 1.0
        d = ((X - ev.xdata) / sx) ** 2 + ((Y - ev.ydata) / sy) ** 2
        if not np.isfinite(d).any():
            return
        self.sel = int(rows[int(np.nanargmin(d))])
        self.draw()

    def on_key(self, ev):
        if ev.key == "right":
            self.step(+1)
        elif ev.key == "left":
            self.step(-1)
        elif ev.key == "tab":
            self.next_class()
        elif ev.key == "e":
            self.export()

    def step(self, d):
        self.sel = (self.sel + d) % max(len(self.tab), 1)
        self.draw()

    def next_class(self):
        """Jump to the next event of the OTHER class -- 13 IEDs among 309."""
        want = "DS" if str(self.row["kind"]) == "IED" else "IED"
        k = self.tab["kind"].to_numpy()
        for j in range(1, len(k) + 1):
            m = (self.sel + j) % len(k)
            if k[m] == want:
                self.sel = m
                break
        self.b_cls.label.set_text("next %s" % ("IED" if want == "DS" else "DS"))
        self.draw()

    def on_base(self, label):
        self.baseline = label
        self.recompute()
        self.draw()

    @staticmethod
    def _drag(s):
        return bool(getattr(s, "drag_active", False))

    def on_win(self, v):
        self.win_ms = float(v)
        if self._drag(self.s_win):
            return
        self.recompute(); self.draw()

    def on_cross(self, v):
        self.cross_ms = float(v)
        if self._drag(self.s_cross):
            return
        self.recompute(); self.draw()

    def on_view(self, v):
        self.view_ms = min(float(v), self.st.half_ms - 5.0)
        if self._drag(self.s_view):
            return
        self.draw()

    def on_feat(self, label):
        names = list(ALL_FEATURES) + [HF_FEATURE]
        chosen = [f for f, on in zip(names, self.c_feat.get_status()) if on]
        if label == HF_FEATURE and HF_FEATURE in chosen:
            self._load_hf()
            self.recompute()
        self.feats = chosen if len(chosen) >= 2 else list(CORE)
        self.fit()
        self.draw()

    def export(self):
        out = self.tab.copy()
        if self.pca is not None:
            sc = np.full((len(out), self.pca["scores"].shape[1]), np.nan)
            sc[self.pca["keep"]] = self.pca["scores"]
            for k in range(sc.shape[1]):
                out["PC%d" % (k + 1)] = sc[:, k]
            if self.pca["lda"] is not None:
                ld = np.full(len(out), np.nan)
                ld[self.pca["keep"]] = self.pca["lda"]
                out["LDA"] = ld
        out["baseline"] = self.baseline
        out["peak_win_ms"] = self.win_ms
        out["cross_win_ms"] = self.cross_ms
        out["pca_features"] = "|".join(self.feats)
        out.to_csv(OUT, index=False)
        self.draw(note="exported %d rows -> %s" % (len(out), os.path.basename(OUT)))

    # -------------------------------------------------------------- drawing
    def draw(self, note=""):
        self._stack()
        self._detail()
        self._scatter()
        self._pca()
        self._loadings()
        self._readout(note)
        self.fig.canvas.draw_idle()

    def _stack(self):
        ax = self.ax_stack
        ax.clear()
        r = self.row
        if r is None:
            return
        i, w = int(r["idx"]), int(r["contact_row"])
        y = self.st.slice_(i, self.shift[i], self.view_ms)
        t = (np.arange(y.shape[0]) - y.shape[0] // 2) / self.st.fs * 1e3
        per = np.nanpercentile(np.abs(y - np.nanmedian(y, axis=0)), 99.0, axis=0)
        step = max(2.0 * float(np.nanmedian(per)), 1e-6)
        cols, lws = [], []
        for k in range(y.shape[1]):
            if k == w:
                cols.append(to_rgba(WINC, 1.0)); lws.append(1.7)
            elif not self.p.included[k]:
                cols.append(to_rgba(BADC, 0.45)); lws.append(0.7)
            else:
                cols.append(to_rgba(CLASS_C[str(r["kind"])], 1.0)); lws.append(0.75)
        ax.add_collection(LineCollection(
            [np.column_stack((t, y[:, k] - k * step)) for k in range(y.shape[1])],
            colors=cols, linewidths=lws, zorder=3))
        ax.axvline(0.0, color="#333333", lw=1.2, zorder=6)
        ax.axvspan(-self.win_ms, self.win_ms, color=CLASS_C[str(r["kind"])],
                   alpha=0.09, zorder=0)
        ticks = list(range(0, y.shape[1], 4))
        ax.set_yticks([-k * step for k in ticks])
        ax.set_yticklabels([self.p.label(k) for k in ticks], fontsize=6)
        ax.set_ylim(-(y.shape[1] - 0.2) * step, step)
        ax.set_xlim(-self.view_ms, self.view_ms)
        ax.set_xlabel("ms from centre", fontsize=8.5)
        ax.set_title("%s %d   largest: %s" % (r["kind"], r["id"],
                                              self.p.label(w)), fontsize=9.5)

    def _detail(self):
        """The winning contact alone, with the half-width actually drawn."""
        ax = self.ax_det
        ax.clear()
        r = self.row
        if r is None:
            return
        i, w = int(r["idx"]), int(r["contact_row"])
        y = self.st.trace(i)[:, w]
        anchor = self.st.stamp_i + int(self.shift[i])
        t = (np.arange(len(y)) - anchor) / self.st.fs * 1e3
        m = np.abs(t) <= self.view_ms
        col = CLASS_C[str(r["kind"])]
        ax.plot(t[m], y[m], lw=1.4, color=INK, zorder=3)
        ax.axvline(0.0, color="#333333", lw=1.2)
        ax.axvspan(-self.win_ms, self.win_ms, color=col, alpha=0.09, lw=0)

        from ied_ampwidth import measure_peak
        pol = "max" if float(r["polarity"]) > 0 else "min"
        mm = measure_peak(y, anchor, self.st.fs, pol, self.win_ms,
                          self.cross_ms, self.baseline, raw=None)
        pc = MAXC if pol == "max" else MINC
        if mm and mm.get("status") == "ok":
            ax.axhline(mm["baseline_uV"], color=pc, ls="--", lw=0.9, alpha=0.7)
            ax.axhline(mm["half_level_uV"], color=pc, ls="-", lw=1.0, alpha=0.9)
            for edge, xms in ((mm["edge_left"], mm["left_ms"]),
                              (mm["edge_right"], mm["right_ms"])):
                ax.axvline(xms, color=pc, lw=1.7, ls=":" if edge else "-")
            ax.annotate("", xy=(mm["left_ms"], mm["half_level_uV"]),
                        xytext=(mm["right_ms"], mm["half_level_uV"]),
                        arrowprops=dict(arrowstyle="<->", color=pc, lw=1.3))
            ax.plot([mm["peak_ms"]], [mm["signed_peak_uV"]], "o", ms=6,
                    color=pc, mec="white", mew=1.0, zorder=6)
        if bool(r["railed"]):
            for s in (+1, -1):
                ax.axhline(s * 1999.94, color=BADC, ls=":", lw=1.1)
            ax.text(0.99, 0.02, "RAILED", transform=ax.transAxes, ha="right",
                    color=BADC, fontsize=8.5, fontweight="bold")
        ax.set_xlim(-self.view_ms, self.view_ms)
        ax.set_xlabel("ms from centre", fontsize=8.5)
        ax.set_ylabel("µV", fontsize=8.5)
        ax.set_title("amp %.0f µV   HW %.2f ms%s   (%s baseline)"
                     % (r["amp_uV"], r["hw_ms"],
                        "  UNRESOLVED" if bool(r["unresolved"]) else "",
                        self.baseline), fontsize=9.5,
                     color=BADC if bool(r["unresolved"]) else INK)

    def _pts(self, ax, X, Y, rows, xlab, ylab, title):
        r = self.row
        for kind in ("DS", "IED"):
            m = (self.tab["kind"].to_numpy()[rows] == kind)
            ax.plot(X[m], Y[m], "o", ms=3.4 if kind == "IED" else 2.6,
                    color=CLASS_C[kind], alpha=0.75 if kind == "IED" else 0.40,
                    mec="none", zorder=4 if kind == "IED" else 3,
                    label="%s n=%d" % (kind, int(m.sum())))
        if r is not None:
            hit = np.where(rows == self.sel)[0]
            if hit.size:
                ax.plot(X[hit[0]], Y[hit[0]], "o", ms=11, mfc="none",
                        mec=WINC, mew=2.0, zorder=6)
        ax.set_xlabel(xlab, fontsize=8.5)
        ax.set_ylabel(ylab, fontsize=8.5)
        ax.set_title(title, fontsize=9.5)
        ax.legend(fontsize=7, framealpha=0.9, loc="best")
        ax.tick_params(labelsize=7)

    def _scatter(self):
        ax = self.ax_scat
        ax.clear()
        f0, f1 = self.feats[0], self.feats[1] if len(self.feats) > 1 else self.feats[0]
        rows = np.arange(len(self.tab))
        X = self.tab[f0].to_numpy(dtype=float)
        Y = self.tab[f1].to_numpy(dtype=float)
        self._pts(ax, X, Y, rows, f0, f1,
                  "the two features   (click a dot)")

    def _pca(self):
        ax = self.ax_pca
        ax.clear()
        if self.pca is None:
            ax.text(0.5, 0.5, "pick at least two features", ha="center")
            return
        S = self.pca["scores"]
        rows = np.where(self.pca["keep"])[0]
        Y = S[:, 1] if S.shape[1] > 1 else np.zeros(S.shape[0])
        ev = self.pca["explained"]
        self._pts(ax, S[:, 0], Y, rows,
                  "PC1 (%.0f%% var)" % (100 * ev[0]),
                  "PC2 (%.0f%% var)" % (100 * ev[1]) if len(ev) > 1 else "",
                  "PCA of %d features   (click a dot)" % len(self.feats))

    def _loadings(self):
        ax = self.ax_load
        ax.clear()
        if self.pca is None:
            return
        L = self.pca["loadings"]
        feats = self.pca["features"]
        n = min(2, L.shape[0])
        yy = np.arange(len(feats))
        wid = 0.38
        for k in range(n):
            ax.barh(yy + (k - (n - 1) / 2.0) * wid, L[k], height=wid,
                    label="PC%d" % (k + 1),
                    color=["#4c6ef5", "#f08c00"][k], alpha=0.85)
        if self.pca["lda_coef"] is not None:
            c = self.pca["lda_coef"]
            c = c / (np.abs(c).max() or 1.0)
            ax.plot(c, yy, "D", ms=5, color=WINC, label="LDA (scaled)",
                    zorder=5)
        ax.axvline(0, color="#888888", lw=0.8)
        ax.set_yticks(yy)
        ax.set_yticklabels(feats, fontsize=7.5)
        ax.invert_yaxis()
        ax.set_xlabel("loading", fontsize=8.5)
        ax.set_title("what each component is made of", fontsize=9.5)
        ax.legend(fontsize=7, framealpha=0.9, loc="lower right")
        ax.tick_params(labelsize=7)

    def _readout(self, note=""):
        L = ["events   %d  (IED %d, DS %d)%s"
             % (len(self.tab), int((self.tab["kind"] == "IED").sum()),
                int((self.tab["kind"] == "DS").sum()),
                "  %d dropped" % self.dropped if self.dropped else ""),
             "measured half-width baseline=%s  peak ±%.0f  cross ±%.0f ms"
             % (self.baseline, self.win_ms, self.cross_ms),
             "unresolved %d   railed %d"
             % (int(self.tab["unresolved"].sum()), int(self.tab["railed"].sum())),
             ""]
        L.append("AUC per feature  (0.5 = chance, either direction)")
        is_ied = (self.tab["kind"] == "IED").to_numpy()
        for f in getattr(self, "used", self.feats):
            a = auc(self.tab[f].to_numpy(dtype=float), is_ied)
            L.append("  %-10s %.3f%s" % (f, a, "   <-- " if abs(a - 0.5) > 0.2 else ""))
        for f in getattr(self, "missing", []):
            L.append("  %-10s not loaded -- NOT in the PCA" % f)
        if self.pca is not None:
            L.append("")
            L.append("PCA  explained %s"
                     % " ".join("%.2f" % v for v in self.pca["explained"][:4]))
            L.append("  AUC  %s"
                     % "  ".join("PC%d %.3f" % (k + 1, v)
                                 for k, v in enumerate(self.pca["auc_pc"][:3])))
            L.append("  LDA  AUC %.3f  (sees the labels; PCA does not)"
                     % self.pca["lda_auc"])
            best = max((abs(v - 0.5), f) for f, v in
                       self.pca["auc_feature"].items())
            L.append("")
            L.append("best single feature: %s (%.3f)"
                     % (best[1], self.pca["auc_feature"][best[1]]))
        if note or self._note:
            L.append("")
            L.append(note or self._note)
        self.txt.set_text("\n".join(L))

        r = self.row
        if r is not None:
            self.stat_txt.set_text(
                "%s %d  t=%.3f s  %s  amp %.0f uV  HW %.2f ms  %s"
                % (r["kind"], r["id"], r["t_s"],
                   self.p.label(int(r["contact_row"])), r["amp_uV"],
                   r["hw_ms"], "RAILED" if bool(r["railed"]) else ""))


def main():
    ap = argparse.ArgumentParser(
        description="amplitude + half-width + PCA, IED vs DS")
    ap.add_argument("--folder", default=NCS_FOLDER)
    ap.add_argument("--ds-bank", default=DS_BANK)
    ap.add_argument("--anat", default=ANAT)
    ap.add_argument("--category", default="Solid")
    ap.add_argument("--baseline", default="local", choices=list(BASELINES))
    ap.add_argument("--win-ms", type=float, default=25.0)
    ap.add_argument("--cross-ms", type=float, default=50.0)
    ap.add_argument("--view-ms", type=float, default=100.0)
    ap.add_argument("--search-ms", type=float, default=50.0)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    Bench(args)
    plt.show()


if __name__ == "__main__":
    main()
