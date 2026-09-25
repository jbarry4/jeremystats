"""
ied_ampwidth_gui_v3.py -- every dentate spike and every IED, centred,
measured and compared as distributions.

WHAT CHANGES AT FULL SCALE
==========================
v2 compares five of each, and five of each is a picture, not a result: with
n=5 the spread between events swamps any difference between classes, so the
honest reading of v2's output was always "suggestive, untested". v3 runs the
same measurement over all 296 curated dentate spikes and every curated IED, at
which point the comparison becomes a distribution against a distribution and
can actually be tested.

Three things follow from the scale, and each one changes the interface:

  YOU CANNOT HAND-PLACE 309 CENTRES. So every event is auto-centred on load,
  by the method v2 introduced -- the peak of the across-channel mean|amp|
  inside the search window. Hand-placing is still there for the ones that need
  it, and the readout separates `auto` from `hand` so an average never quietly
  claims more curation than it had.

  THE OUTLIERS ARE THE WORK. With ten events you look at each. With 309 you
  look at the ones the automatic pass could not resolve, so `next flagged`
  walks only the events whose centring hit the search boundary -- the ones
  whose real peak lies outside the window and which have therefore been
  dragged to its edge.

  A STRIP OF 309 DOTS IS NOT A COMPARISON. The per-event panel is a box and a
  strip, and beside it the two distributions as histograms, with a
  Mann-Whitney U and Cliff's delta underneath. Medians and IQR are reported
  rather than mean and SD because the classes are not symmetric and one of
  them has thirteen members.

THE UNEQUAL N IS REAL AND IT IS NOT A BUG
=========================================
There are 296 curated dentate spikes and 13 curated Solid IEDs in this
session. No amount of statistics makes 13 into a large sample: the DS
distribution is well estimated and the IED one is not, and a p-value computed
across that asymmetry is dominated by the DS side. Switch the IED set with
`--category` (Solid, Sputter, curated, All) to see how much the answer depends
on which IEDs are counted -- that dependence is the finding, not a nuisance.

WHAT IS AND IS NOT THE SAME AS v2
=================================
The statistic, the centring, the 62 good contacts and the exclusion of CSC55
and CSC59 are identical. The data is decimated to 2 kHz -- worth 0.66% on the
statistic and 0.37 ms on the centre, measured, see `ied_ds_store.py` -- which
is what lets 309 events sit in memory at once. Because decimation needs its
anti-alias filter, the 300 Hz lowpass is baked into the cache rather than
being a live toggle; `--lowpass` changes it and rebuilds.

RUN
===
  python ied_ampwidth_gui_v3.py                   (first run reads ~80 s)
  python ied_ampwidth_gui_v3.py --category curated
  python ied_ampwidth_gui_v3.py --refresh         (ignore the cache)

KEYS
====
  left / right  previous / next event in the current class
  tab           switch class (IED <-> DS)
  f             jump to the next flagged (edge-clamped) event
  c / C         centre this event / centre every event
  r / R         reset this centre / reset every centre
  s / e         save centres / export the tables
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

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from ied_ds import BAD_CHANNELS, DS_BANK, NCS_FOLDER, Probe64   # noqa: E402
from ied_ds_store import DEC_Q, HALF_MS, EventStore             # noqa: E402
from ied_ds import read_ds_bank, read_ied_events                # noqa: E402

INK = "#1b2220"
GREY = "#a8b0ad"
BADC = "#c0392b"
IEDC = "#b8620a"
DSC = "#1f6feb"
CLASS_C = {"IED": IEDC, "DS": DSC}
METHODS = ("mean|amp| peak", "max channel")

PICKS = os.path.join(_HERE, "ied_ds_v3_centres.csv")
OUT_EVENTS = os.path.join(_HERE, "ied_ds_v3_event_stats.csv")
OUT_PROFILE = os.path.join(_HERE, "ied_ds_v3_channel_profile.csv")


class Bench:
    def __init__(self, args):
        self.args = args
        self.win_ms = args.win_ms
        self.view_ms = args.view_ms
        self.search_ms = args.search_ms
        self.method = METHODS[0]
        self.baseline = True
        self.gain = 1.0
        self.kind = "IED"
        self.pos = {"IED": 0, "DS": 0}

        self.p = Probe64(args.folder, BAD_CHANNELS, args.anat)
        self._ver = 0              # bumped whenever a centre moves
        self._avg_cache = {}
        self._build()
        self.st = EventStore.build(
            self.p, read_ied_events(category=args.category),
            read_ds_bank(args.ds_bank), half_ms=args.half_ms,
            lowpass=args.lowpass, q=args.q, progress=self._progress,
            refresh=args.refresh)

        n = len(self.st)
        self.shift = np.zeros(n, dtype=int)
        self.edge = np.zeros(n, dtype=bool)
        self.hand = np.zeros(n, dtype=bool)
        self.centre_all(initial=True)
        self._restore()
        self.draw()

    # ------------------------------------------------------------- centres
    def _restore(self):
        """Hand-placed centres from a previous session, and only those.

        The automatic ones are recomputed on load rather than restored: they
        are a function of the current settings, and reloading a shift that was
        computed under a different search window would silently mix two
        centrings in one average. A centre you placed yourself is not
        reproducible from settings, so that one is kept.
        """
        if not os.path.exists(PICKS):
            return
        try:
            t = pd.read_csv(PICKS)
        except Exception:
            return
        idx = {(str(k), int(i)): j
               for j, (k, i) in enumerate(zip(self.st.kinds, self.st.ids))}
        got = 0
        for _, r in t.iterrows():
            if not bool(r.get("hand", False)):
                continue
            j = idx.get((str(r["kind"]), int(r["id"])))
            if j is not None:
                self.shift[j] = int(r["shift"])
                self.hand[j] = True
                self.edge[j] = False
                got += 1
        self._ver += 1
        self._note = "restored %d hand-placed centres" % got if got else ""

    def centre_all(self, initial=False):
        keep = self.hand.copy()
        old = self.shift.copy()
        self.shift, self.edge = self.st.centre_all(
            np.zeros(len(self.st), dtype=int), self.search_ms, self.method,
            self.baseline)
        if not initial:
            # A hand-placed centre is a decision; a batch re-centre must not
            # quietly overwrite it.
            self.shift[keep] = old[keep]
            self.edge[keep] = False
        self._ver += 1
        if not initial:
            self.draw()

    def centre_one(self):
        i = self.cur
        self.shift[i], self.edge[i] = self.st.centre(
            i, self.shift[i], self.search_ms, self.method, self.baseline)
        self.hand[i] = False
        self._ver += 1
        self.draw()

    def reset_one(self):
        i = self.cur
        self.shift[i], self.edge[i], self.hand[i] = 0, False, False
        self._ver += 1
        self.draw()

    def reset_all(self):
        self.shift[:] = 0
        self.edge[:] = False
        self.hand[:] = False
        self._ver += 1
        self.draw()

    # --------------------------------------------------------------- state
    @property
    def order(self):
        return self.st.where(self.kind)

    @property
    def cur(self):
        o = self.order
        return int(o[self.pos[self.kind] % len(o)])

    def stats(self, kind):
        idx = self.st.where(kind)
        return self.st.stats_for(idx, self.shift[idx], self.win_ms,
                                 self.baseline)

    # ---------------------------------------------------------------- build
    def _build(self):
        self.fig = plt.figure(figsize=(19.0, 10.4), facecolor="white")
        self.fig.canvas.manager.set_window_title(
            "IED vs dentate spike -- every curated event")
        # The left stack carries the contact labels, so it needs a gutter the
        # middle one does not.
        self.ax_stack = self.fig.add_axes([0.058, 0.355, 0.185, 0.575])
        self.ax_act = self.fig.add_axes([0.058, 0.270, 0.185, 0.070])
        self.ax_avg = self.fig.add_axes([0.268, 0.355, 0.200, 0.575])
        self.ax_avgact = self.fig.add_axes([0.268, 0.270, 0.200, 0.070])
        self.ax_prof = self.fig.add_axes([0.530, 0.270, 0.140, 0.660])
        self.ax_cmp = self.fig.add_axes([0.715, 0.600, 0.120, 0.330])
        self.ax_hist = self.fig.add_axes([0.868, 0.600, 0.120, 0.330])
        self.ax_cmp.set_facecolor("white")

        self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        b = lambda l, t, w, h: self.fig.add_axes([l, t, w, h])

        self.r_kind = RadioButtons(b(0.040, 0.145, 0.050, 0.075), ("IED", "DS"))
        self.r_kind.on_clicked(self.on_kind)
        self.fig.text(0.040, 0.226, "class", fontsize=8, color=INK)

        self.b_prev = Button(b(0.100, 0.185, 0.037, 0.034), "< prev")
        self.b_next = Button(b(0.141, 0.185, 0.037, 0.034), "next >")
        self.b_prev.on_clicked(lambda _: self.step(-1))
        self.b_next.on_clicked(lambda _: self.step(+1))
        self.b_flag = Button(b(0.182, 0.185, 0.055, 0.034), "next flagged")
        self.b_flag.on_clicked(lambda _: self.next_flagged())

        self.t_jump = TextBox(b(0.112, 0.145, 0.040, 0.034), "id ", initial="")
        self.t_jump.on_submit(self.on_jump)
        self.b_c1 = Button(b(0.162, 0.145, 0.036, 0.034), "centre")
        self.b_cA = Button(b(0.201, 0.145, 0.036, 0.034), "all")
        self.b_c1.on_clicked(lambda _: self.centre_one())
        self.b_cA.on_clicked(lambda _: self.centre_all())

        self.b_r1 = Button(b(0.248, 0.185, 0.032, 0.034), "reset")
        self.b_rA = Button(b(0.283, 0.185, 0.026, 0.034), "all")
        self.b_r1.on_clicked(lambda _: self.reset_one())
        self.b_rA.on_clicked(lambda _: self.reset_all())
        self.b_save = Button(b(0.248, 0.145, 0.030, 0.034), "save")
        self.b_exp = Button(b(0.281, 0.145, 0.036, 0.034), "export")
        self.b_save.on_clicked(lambda _: self.save())
        self.b_exp.on_clicked(lambda _: self.export())

        self.r_meth = RadioButtons(b(0.330, 0.145, 0.088, 0.075), METHODS)
        self.r_meth.on_clicked(self.on_method)
        self.fig.text(0.330, 0.226, "centring method", fontsize=8, color=INK)

        self.s_search = Slider(b(0.487, 0.196, 0.095, 0.019), "search ±ms",
                               2.0, 150.0, valinit=self.search_ms, valfmt="%.0f")
        self.s_win = Slider(b(0.487, 0.163, 0.095, 0.019), "window ±ms",
                            2.0, 150.0, valinit=self.win_ms, valfmt="%.0f")
        self.s_view = Slider(b(0.487, 0.130, 0.095, 0.019), "view ±ms",
                             20.0, 190.0, valinit=self.view_ms, valfmt="%.0f")
        self.s_gain = Slider(b(0.487, 0.097, 0.095, 0.019), "gain",
                             0.2, 6.0, valinit=1.0, valfmt="%.1f")
        self.s_search.on_changed(self.on_search)
        self.s_win.on_changed(self.on_win)
        self.s_view.on_changed(self.on_view)
        self.s_gain.on_changed(self.on_gain)

        self.c_opt = CheckButtons(b(0.630, 0.145, 0.085, 0.075),
                                  ["baseline-subtract", "60 Hz notch"],
                                  [True, False])
        self.c_opt.on_clicked(self.on_opt)

        self.txt = self.fig.text(0.732, 0.232, "", fontsize=8.5, color=INK,
                                 va="top", family="monospace")
        self.stat_txt = self.fig.text(0.040, 0.050, "", fontsize=8.5,
                                      color=INK, va="top", family="monospace")
        self._note = ""

    def _progress(self, i, n, msg):
        self.stat_txt.set_text("building event store  [%d/%d]  %s" % (i, n, msg))
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
        self.edge[i] = False
        self._ver += 1
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
        elif k == "f":
            self.next_flagged()
        elif k == "c":
            self.centre_one()
        elif k == "C":
            self.centre_all()
        elif k == "r":
            self.reset_one()
        elif k == "R":
            self.reset_all()
        elif k == "s":
            self.save()
        elif k == "e":
            self.export()

    def on_kind(self, label):
        self.kind = label
        self.draw()

    def step(self, d):
        self.pos[self.kind] = (self.pos[self.kind] + d) % len(self.order)
        self.draw()

    def next_flagged(self):
        """Walk only the events the automatic pass could not resolve."""
        o = self.order
        start = self.pos[self.kind] % len(o)
        for j in range(1, len(o) + 1):
            k = (start + j) % len(o)
            if self.edge[o[k]]:
                self.pos[self.kind] = k
                self.draw(note="flagged %s" % self.st.label(int(o[k])))
                return
        self.draw(note="no flagged events in %s" % self.kind)

    def on_jump(self, text):
        try:
            want = int(str(text).strip())
        except ValueError:
            return
        o = self.order
        hit = np.where(self.st.ids[o] == want)[0]
        if hit.size:
            self.pos[self.kind] = int(hit[0])
            self.draw()
        else:
            self.draw(note="no %s %d" % (self.kind, want))

    def on_method(self, label):
        self.method = label
        self.centre_all()

    @staticmethod
    def _dragging(slider):
        """True while the handle is still held down.

        A full redraw of this figure is ~0.7 s, most of it matplotlib's fixed
        cost for a 1900x1040 canvas full of widgets rather than anything the
        measurement does -- all 309 events' statistics compute in 16 ms. A
        Slider fires on_changed for every pixel of a drag, so without this the
        callbacks queue up and the handle crawls. Skipping while the drag is
        live and acting on release makes the slider track the mouse and the
        figure update once, when the value is the one that was wanted.
        """
        return bool(getattr(slider, "drag_active", False))

    def on_search(self, v):
        self.search_ms = float(v)
        if self._dragging(self.s_search):
            return
        self.centre_all()

    def on_win(self, v):
        self.win_ms = float(v)
        if self._dragging(self.s_win):
            return
        self.draw()

    def on_view(self, v):
        self.view_ms = min(float(v), self.st.half_ms - 5.0)
        if self._dragging(self.s_view):
            return
        self.draw()

    def on_gain(self, v):
        self.gain = max(float(v), 0.05)
        if self._dragging(self.s_gain):
            return
        self.draw()

    def on_opt(self, label):
        st = dict(zip(["baseline-subtract", "60 Hz notch"],
                      self.c_opt.get_status()))
        self.baseline = st["baseline-subtract"]
        want = 60.0 if st["60 Hz notch"] else None
        if want != self.st.notch:
            self.stat_txt.set_text("applying notch ...")
            self.fig.canvas.draw_idle()
            self.st.set_notch(want)
        self.draw()

    # --------------------------------------------------------------- output
    def save(self):
        rows = []
        for j in range(len(self.st)):
            rows.append({"kind": str(self.st.kinds[j]), "id": int(self.st.ids[j]),
                         "t_s": float(self.st.t_s[j]), "shift": int(self.shift[j]),
                         "shift_ms": self.shift[j] / self.st.fs * 1e3,
                         "hand": bool(self.hand[j]), "at_edge": bool(self.edge[j]),
                         "centring_method": self.method,
                         "search_ms": self.search_ms,
                         "saved_utc": dt.datetime.utcnow().isoformat(
                             timespec="seconds")})
        pd.DataFrame(rows).to_csv(PICKS, index=False)
        self.draw(note="saved -> %s" % os.path.basename(PICKS))

    def export(self):
        rows, prof = [], []
        for kind in ("IED", "DS"):
            idx = self.st.where(kind)
            S, P = self.stats(kind)
            for j, i in enumerate(idx):
                rows.append({
                    "kind": kind, "id": int(self.st.ids[i]),
                    "t_s": float(self.st.t_s[i]),
                    "centre_s": float(self.st.t_s[i]) + self.shift[i] / self.st.fs,
                    "shift_ms": self.shift[i] / self.st.fs * 1e3,
                    "hand_placed": bool(self.hand[i]),
                    "centre_at_search_edge": bool(self.edge[i]),
                    "mean_abs_amp_uV": S[j], "window_ms": self.win_ms,
                    "centring_method": self.method, "search_ms": self.search_ms,
                    "baseline_subtracted": self.baseline,
                    "lowpass_hz": self.st.lowpass or 0,
                    "notch_hz": self.st.notch or 0,
                    "fs_hz": self.st.fs,
                    "n_channels": int(self.p.included.sum()),
                    "excluded": ",".join(str(x) for x in self.p.bad),
                })
                for c, n in enumerate(self.p.numbers):
                    prof.append({"kind": kind, "id": int(self.st.ids[i]),
                                 "csc": int(n),
                                 "region": self.p.region.get(int(n), ""),
                                 "included": bool(self.p.included[c]),
                                 "mean_abs_amp_uV": P[j, c],
                                 "window_ms": self.win_ms})
        pd.DataFrame(rows).to_csv(OUT_EVENTS, index=False)
        pd.DataFrame(prof).to_csv(OUT_PROFILE, index=False)
        self.save()
        self.draw(note="exported %d events -> %s"
                       % (len(rows), os.path.basename(OUT_EVENTS)))

    # -------------------------------------------------------------- drawing
    def draw(self, note=""):
        self._stack()
        self._activity()
        self._average()
        self._avg_activity()
        self._profile()
        self._compare()
        self._hist()
        self._readout(note)
        self.fig.canvas.draw_idle()

    def _stackplot(self, ax, y, title, colour):
        t = (np.arange(y.shape[0]) - y.shape[0] // 2) / self.st.fs * 1e3
        per = np.nanpercentile(np.abs(y - np.nanmedian(y, axis=0)), 99.0, axis=0)
        step = max(2.0 * float(np.nanmedian(per)) / self.gain, 1e-6)
        # One LineCollection rather than 64 Line2D artists. At full scale the
        # two stacks are redrawn on every slider step, and the per-artist
        # overhead -- not the arithmetic, which profiles at ~15 ms for all 309
        # events -- was what made a redraw take most of a second.
        rgba_ok = to_rgba(colour, 1.0)
        rgba_bad = to_rgba(BADC, 0.5)
        segs = [np.column_stack((t, y[:, k] - k * step))
                for k in range(y.shape[1])]
        lc = LineCollection(
            segs,
            colors=[rgba_ok if self.p.included[k] else rgba_bad
                    for k in range(y.shape[1])],
            linewidths=[0.85 if self.p.included[k] else 0.7
                        for k in range(y.shape[1])],
            zorder=3)
        ax.add_collection(lc)
        ax.axvline(0.0, color="#333333", lw=1.2, zorder=6)
        ax.axvspan(-self.win_ms, self.win_ms, color=colour, alpha=0.09, zorder=0)
        ticks = list(range(0, y.shape[1], 4))
        ax.set_yticks([-k * step for k in ticks])
        ax.set_yticklabels([self.p.label(k) for k in ticks], fontsize=6)
        for lab, k in zip(ax.get_yticklabels(), ticks):
            if not self.p.included[k]:
                lab.set_color(BADC)
        ax.set_ylim(-(y.shape[1] - 0.2) * step, step)
        ax.set_xlim(-self.view_ms, self.view_ms)
        ax.set_xticklabels([])
        ax.set_title(title, fontsize=9.5)

    def _stack(self):
        ax = self.ax_stack
        ax.clear()
        i = self.cur
        tag = ("HAND" if self.hand[i] else
               ("AT SEARCH EDGE" if self.edge[i] else "auto"))
        self._stackplot(ax, self.st.slice_(i, self.shift[i], self.view_ms),
                        "%s   %+.2f ms   [%s]"
                        % (self.st.label(i), self.shift[i] / self.st.fs * 1e3,
                           tag), CLASS_C[self.kind])
        if self.edge[i]:
            ax.title.set_color(BADC)

    def _class_average(self, kind):
        """Cached event-triggered average.

        Stacking 296 windows is ~7.6 M floats, and it depends only on the
        centres and the viewed span -- not on the measure window. Rebuilt on
        every redraw it made the window slider take most of a second per step
        at full scale; cached against a version counter that the centres bump,
        it is free.
        """
        key = (kind, self.view_ms, self._ver, self.st.notch)
        hit = self._avg_cache.get(key)
        if hit is not None:
            return hit
        idx = self.st.where(kind)
        h = int(round(self.view_ms * 1e-3 * self.st.fs))
        acc = np.zeros((2 * h + 1, len(self.p.numbers)))
        cnt = np.zeros((2 * h + 1, 1))
        for i in idx:
            s = self.st.slice_(int(i), self.shift[i], self.view_ms)
            ok = np.isfinite(s[:, :1])
            acc += np.nan_to_num(s)
            cnt += ok
        out = acc / np.maximum(cnt, 1)
        self._avg_cache = {key: out}          # one entry: only the current view
        return out

    def _average(self):
        ax = self.ax_avg
        ax.clear()
        idx = self.order
        y = self._class_average(self.kind)
        nh = int(self.hand[idx].sum())
        ne = int(self.edge[idx].sum())
        self._stackplot(ax, y, "%s average of %d   (%d hand, %d flagged)"
                        % (self.kind, len(idx), nh, ne), CLASS_C[self.kind])
        ax.set_yticklabels([])

    def _activity(self):
        ax = self.ax_act
        ax.clear()
        i = self.cur
        act = self.st.activity(i, self.baseline)
        h = int(round(self.view_ms * 1e-3 * self.st.fs))
        c = self.st.stamp_i + int(self.shift[i])
        y = np.full(2 * h + 1, np.nan)
        lo, hi = c - h, c + h + 1
        a, b = max(0, lo), min(len(act), hi)
        y[a - lo:b - lo] = act[a:b]
        t = (np.arange(len(y)) - h) / self.st.fs * 1e3
        col = CLASS_C[self.kind]
        ax.plot(t, y, lw=1.0, color=col)
        ax.axvline(0.0, color="#333333", lw=1.2)
        ax.axvspan(-self.win_ms, self.win_ms, color=col, alpha=0.09, lw=0)
        s0 = -self.shift[i] / self.st.fs * 1e3
        ax.axvspan(s0 - self.search_ms, s0 + self.search_ms, facecolor="none",
                   edgecolor=BADC if self.edge[i] else "#555555",
                   ls="--", lw=1.6 if self.edge[i] else 0.9)
        if self.edge[i]:
            ax.text(0.99, 0.86, "clamped to search edge", transform=ax.transAxes,
                    ha="right", va="top", fontsize=7, color=BADC,
                    fontweight="bold")
        ax.set_xlim(-self.view_ms, self.view_ms)
        ax.set_ylabel("mean|amp|", fontsize=7)
        ax.set_xlabel("ms from centre   (click the stack to move it)",
                      fontsize=8.5)
        ax.tick_params(labelsize=7)

    def _avg_activity(self):
        ax = self.ax_avgact
        ax.clear()
        idx = self.order
        h = int(round(self.view_ms * 1e-3 * self.st.fs))
        A = np.full((len(idx), 2 * h + 1), np.nan)
        for j, i in enumerate(idx):
            act = self.st.activity(int(i), self.baseline)
            c = self.st.stamp_i + int(self.shift[i])
            lo, hi = c - h, c + h + 1
            a, b = max(0, lo), min(len(act), hi)
            A[j, a - lo:b - lo] = act[a:b]
        t = (np.arange(A.shape[1]) - h) / self.st.fs * 1e3
        col = CLASS_C[self.kind]
        mu = np.nanmean(A, axis=0)
        sd = np.nanstd(A, axis=0)
        ax.fill_between(t, mu - sd, mu + sd, color=col, alpha=0.20, lw=0)
        ax.plot(t, mu, lw=1.6, color=col)
        ax.axvline(0.0, color="#333333", lw=1.2)
        ax.axvspan(-self.win_ms, self.win_ms, color=col, alpha=0.09, lw=0)
        ax.set_xlim(-self.view_ms, self.view_ms)
        ax.set_xlabel("ms from centre   (mean ± SD across events)",
                      fontsize=8.5)
        ax.tick_params(labelsize=7, labelleft=False)

    def _profile(self):
        ax = self.ax_prof
        ax.clear()
        k = np.arange(len(self.p.numbers))
        inc = self.p.included
        for kind in ("IED", "DS"):
            _, P = self.stats(kind)
            if P.size == 0:
                continue
            mu = np.full(P.shape[1], np.nan)
            sem = np.full(P.shape[1], np.nan)
            mu[inc] = np.nanmean(P[:, inc], axis=0)
            sem[inc] = np.nanstd(P[:, inc], axis=0) / max(np.sqrt(P.shape[0]), 1)
            ax.plot(mu, k, "-", lw=1.4, color=CLASS_C[kind],
                    label="%s (n=%d)" % (kind, P.shape[0]))
            ax.fill_betweenx(k, mu - sem, mu + sem, color=CLASS_C[kind],
                             alpha=0.22, lw=0)
        for c in np.where(~inc)[0]:
            ax.axhline(c, color=BADC, lw=0.8, alpha=0.5)
        ax.invert_yaxis()
        ax.set_yticks(range(0, len(k), 4))
        ax.set_yticklabels([self.p.label(i) for i in range(0, len(k), 4)],
                           fontsize=6)
        ax.set_xlabel("mean |amp| (µV)", fontsize=8.5)
        ax.set_title("per contact, ±%.0f ms\n(mean ± SEM)"
                     % self.win_ms, fontsize=9.5)
        ax.legend(fontsize=7.5, loc="lower right", framealpha=0.9)

    def _compare(self):
        ax = self.ax_cmp
        ax.clear()
        rng = np.random.default_rng(0)
        self._summary = []
        for j, kind in enumerate(("IED", "DS")):
            S, _ = self.stats(kind)
            S = S[np.isfinite(S)]
            if S.size == 0:
                continue
            bp = ax.boxplot([S], positions=[j], widths=0.44, whis=(5, 95),
                            showfliers=False, patch_artist=True, manage_ticks=False)
            for p in bp["boxes"]:
                p.set(facecolor=CLASS_C[kind], alpha=0.25,
                      edgecolor=CLASS_C[kind], lw=1.3)
            for part in ("whiskers", "caps", "medians"):
                for p in bp[part]:
                    p.set(color=CLASS_C[kind], lw=1.5)
            # Strip, thinned when the class is large: 296 opaque dots is a
            # solid block that hides the shape the box is there to show.
            show = S if S.size <= 120 else rng.choice(S, 120, replace=False)
            ax.plot(j + (rng.random(show.size) - 0.5) * 0.30, show, "o",
                    ms=2.6, color=CLASS_C[kind], alpha=0.45, mec="none", zorder=3)
            self._summary.append(
                (kind, S.size, float(np.median(S)),
                 float(np.percentile(S, 25)), float(np.percentile(S, 75)), S))
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["IED", "DS"], fontsize=9)
        ax.set_xlim(-0.6, 1.6)
        ax.set_ylabel("mean |amp| (µV)", fontsize=8.5)
        ax.set_title("per event, ±%.0f ms" % self.win_ms, fontsize=9.5)

    def _hist(self):
        ax = self.ax_hist
        ax.clear()
        allS = [s[5] for s in getattr(self, "_summary", [])]
        if not allS:
            return
        lo = min(float(np.min(s)) for s in allS)
        hi = max(float(np.max(s)) for s in allS)
        bins = np.linspace(lo, hi, 26)
        for (kind, n, med, q1, q3, S) in self._summary:
            # Density, not counts: 296 against 13 on a count axis shows only
            # that there are more dentate spikes, which is not the question.
            ax.hist(S, bins=bins, density=True, histtype="stepfilled",
                    color=CLASS_C[kind], alpha=0.28)
            ax.hist(S, bins=bins, density=True, histtype="step",
                    color=CLASS_C[kind], lw=1.5, label="%s n=%d" % (kind, n))
            ax.axvline(med, color=CLASS_C[kind], ls="--", lw=1.2)
        ax.set_xlabel("mean |amp| (µV)", fontsize=8.5)
        ax.set_ylabel("density", fontsize=8.5)
        ax.set_title("distributions", fontsize=9.5)
        ax.legend(fontsize=7.5, framealpha=0.9)
        ax.tick_params(labelsize=7)

    def _readout(self, note=""):
        L = ["contacts  %d of %d   excluded %s"
             % (self.p.included.sum(), len(self.p.numbers),
                ", ".join("CSC%d" % b for b in self.p.bad)),
             "window    ±%.0f ms   baseline %s   %s @ %.0f Hz"
             % (self.win_ms, "on" if self.baseline else "off",
                ("LP %.0f" % self.st.lowpass) if self.st.lowpass else "no LP",
                self.st.fs),
             "centring  %s, ±%.0f ms" % (self.method, self.search_ms),
             ""]
        for (kind, n, med, q1, q3, _) in getattr(self, "_summary", []):
            L.append("%-4s n=%3d  median %7.2f  IQR %.0f-%.0f uV"
                     % (kind, n, med, q1, q3))
        if len(getattr(self, "_summary", [])) == 2:
            a, b = self._summary[0][5], self._summary[1][5]
            L.append("")
            try:
                from scipy.stats import mannwhitneyu
                U, pv = mannwhitneyu(a, b, alternative="two-sided")
                # Cliff's delta: P(IED>DS) - P(IED<DS), a plain effect size
                # that does not assume either shape.
                delta = 2.0 * (U / (len(a) * len(b))) - 1.0
                L.append("Mann-Whitney  U=%.0f  p=%.4g" % (U, pv))
                L.append("Cliff's delta %+0.3f  (0 = complete overlap)" % delta)
            except Exception as exc:
                L.append("test unavailable: %s" % exc)
        nh, ne = int(self.hand.sum()), int(self.edge.sum())
        L.append("")
        L.append("centres   %d auto, %d hand" % (len(self.st) - nh, nh))
        if ne:
            L.append("WARNING   %d at the search edge (press f)" % ne)
        if note or self._note:
            L.append(note or self._note)
        self.txt.set_text("\n".join(L))

        i = self.cur
        s, _ = self.st.stat(i, self.shift[i], self.win_ms, self.baseline)
        self.stat_txt.set_text(
            "%s   t=%.3f s   centre %+.2f ms   mean|amp| %.2f uV   [%s]"
            % (self.st.label(i), self.st.t_s[i],
               self.shift[i] / self.st.fs * 1e3, s,
               "hand" if self.hand[i] else ("EDGE" if self.edge[i] else "auto")))


def main():
    ap = argparse.ArgumentParser(description="IED vs DS, every curated event")
    ap.add_argument("--folder", default=NCS_FOLDER)
    ap.add_argument("--ds-bank", default=DS_BANK)
    ap.add_argument("--anat", default=None)
    ap.add_argument("--category", default="Solid",
                    help="which IEDs: Solid | Sputter | curated | All")
    ap.add_argument("--win-ms", type=float, default=25.0)
    ap.add_argument("--view-ms", type=float, default=100.0)
    # +-50 ms, not +-25. At +-25 the automatic pass clamped real dentate
    # spikes to the boundary -- DS2's peak sits at +27.5 ms -- and a clamped
    # centre drags the event to the window edge rather than onto its peak.
    ap.add_argument("--search-ms", type=float, default=50.0)
    ap.add_argument("--half-ms", type=float, default=HALF_MS)
    ap.add_argument("--lowpass", type=float, default=300.0)
    ap.add_argument("--q", type=int, default=DEC_Q, help="decimation factor")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache")
    args = ap.parse_args()
    if args.anat is None:
        from ied_ds import ANAT
        args.anat = ANAT

    Bench(args)
    plt.show()


if __name__ == "__main__":
    main()
