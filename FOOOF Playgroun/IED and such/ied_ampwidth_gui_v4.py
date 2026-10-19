"""
ied_ampwidth_gui_v4.py -- the biggest contact, not the average of all of them.

THE CHANGE, AND THE REASON FOR IT
=================================
v3's statistic is the mean of |x - baseline| over all 62 good contacts. On a
probe that spans CA1 to deep DG, most of those contacts are nowhere near the
discharge: an event that is enormous in the hilus and silent in CA1 gets its
hilar amplitude divided by sixty-two, and the quiet contacts dilute the thing
being measured. So v4 takes the largest contact instead.

    v3      mean over 62 contacts of (mean over window of |x - baseline|)
    v4      the LARGEST contact's amplitude, by either reduction below

`K` generalises it: the statistic is the mean of the top K contacts, so K=1 is
the single biggest and K=62 with the "channel mean" reduction reproduces v3
exactly. Sliding K is a direct measurement of how much the quiet contacts were
costing, rather than an argument about it.

THE RAIL, AND WHAT IS DONE ABOUT IT
===================================
This acquisition clips at +-1999.94 uV (Neuralynx `InputRange 2000`, in the
raw .ncs). Within +-50 ms of the stamp, 92% of Solid IEDs and 34% of dentate
spikes have their peak contact railed, so a maximum lands on the clip often.

The clipped value is taken as it stands -- a railed contact reads ~2000 uV and
that is the statistic. `skip railed` is available as a checkbox if you want
the largest UNCLIPPED contact instead, but it is off by default.

What the readout does keep is the censored PERCENTAGE per class, because the
two classes clip at very different rates and that is worth seeing next to the
medians: where both classes pile up near 2000 uV, the comparison is between
two lower bounds, not two amplitudes.

RUN
===
  python ied_ampwidth_gui_v4.py            (rebuilds the cache once, ~90 s,
                                            because v4 needs the rail mask)
  python ied_ampwidth_gui_v4.py --k 5
  python ied_ampwidth_gui_v4.py --mode "channel mean" --k 62   (= v3)

KEYS
====
  left / right  previous / next event      tab   switch class
  f             next flagged centring      x     next censored event
  c / C         centre this / centre all   r / R reset this / reset all
  s / e         save centres / export
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

from ied_ds import (ANAT, BAD_CHANNELS, DS_BANK, NCS_FOLDER,      # noqa: E402
                    Probe64, read_ds_bank, read_ied_events)
from ied_ds_store import DEC_Q, HALF_MS, EventStore               # noqa: E402

INK = "#1b2220"
BADC = "#c0392b"
IEDC = "#b8620a"
DSC = "#1f6feb"
WINC = "#0b7a63"
CLASS_C = {"IED": IEDC, "DS": DSC}
CENTRE_METHODS = ("mean|amp| peak", "max channel")
MODES = ("peak |amp|", "channel mean")

PICKS = os.path.join(_HERE, "ied_ds_v4_centres.csv")
OUT_EVENTS = os.path.join(_HERE, "ied_ds_v4_event_stats.csv")
OUT_PROFILE = os.path.join(_HERE, "ied_ds_v4_channel_profile.csv")


class Bench:
    def __init__(self, args):
        self.args = args
        self.win_ms = args.win_ms
        self.view_ms = args.view_ms
        self.search_ms = args.search_ms
        self.method = CENTRE_METHODS[0]
        self.mode = args.mode
        self.k = int(args.k)
        self.skip_railed = False
        self.baseline = True
        self.gain = 1.0
        self.kind = "IED"
        self.pos = {"IED": 0, "DS": 0}
        self._ver = 0
        self._avg_cache = {}
        self._note = ""

        self.p = Probe64(args.folder, BAD_CHANNELS, args.anat)
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
                self.shift[j], self.hand[j], self.edge[j] = int(r["shift"]), True, False
                got += 1
        self._ver += 1
        self._note = "restored %d hand-placed centres" % got if got else ""

    def centre_all(self, initial=False):
        keep, old = self.hand.copy(), self.shift.copy()
        self.shift, self.edge = self.st.centre_all(
            np.zeros(len(self.st), dtype=int), self.search_ms, self.method,
            self.baseline)
        if not initial:
            self.shift[keep], self.edge[keep] = old[keep], False
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
        self.shift[:], self.edge[:], self.hand[:] = 0, False, False
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

    def _kw(self):
        return dict(baseline=self.baseline, k=self.k, mode=self.mode,
                    exclude_railed=self.skip_railed)

    def stats(self, kind):
        idx = self.st.where(kind)
        return self.st.peak_stats_for(idx, self.shift[idx], self.win_ms,
                                      **self._kw())

    # ---------------------------------------------------------------- build
    def _build(self):
        self.fig = plt.figure(figsize=(19.0, 10.4), facecolor="white")
        self.fig.canvas.manager.set_window_title(
            "IED vs DS -- biggest contact (v4)")
        self.ax_stack = self.fig.add_axes([0.058, 0.355, 0.185, 0.575])
        self.ax_act = self.fig.add_axes([0.058, 0.270, 0.185, 0.070])
        self.ax_avg = self.fig.add_axes([0.268, 0.355, 0.200, 0.575])
        self.ax_avgact = self.fig.add_axes([0.268, 0.270, 0.200, 0.070])
        self.ax_prof = self.fig.add_axes([0.530, 0.270, 0.140, 0.660])
        self.ax_cmp = self.fig.add_axes([0.715, 0.600, 0.120, 0.330])
        self.ax_hist = self.fig.add_axes([0.868, 0.600, 0.120, 0.330])

        self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        b = lambda l, t, w, h: self.fig.add_axes([l, t, w, h])

        self.r_kind = RadioButtons(b(0.040, 0.145, 0.048, 0.075), ("IED", "DS"))
        self.r_kind.on_clicked(self.on_kind)
        self.fig.text(0.040, 0.226, "class", fontsize=8, color=INK)

        self.b_prev = Button(b(0.096, 0.185, 0.035, 0.034), "< prev")
        self.b_next = Button(b(0.135, 0.185, 0.035, 0.034), "next >")
        self.b_prev.on_clicked(lambda _: self.step(-1))
        self.b_next.on_clicked(lambda _: self.step(+1))
        self.b_flag = Button(b(0.174, 0.185, 0.048, 0.034), "next flag")
        self.b_cens = Button(b(0.226, 0.185, 0.050, 0.034), "next censored")
        self.b_flag.on_clicked(lambda _: self.next_flagged())
        self.b_cens.on_clicked(lambda _: self.next_censored())

        self.t_jump = TextBox(b(0.108, 0.145, 0.035, 0.034), "id ", initial="")
        self.t_jump.on_submit(self.on_jump)
        self.b_c1 = Button(b(0.152, 0.145, 0.034, 0.034), "centre")
        self.b_cA = Button(b(0.189, 0.145, 0.024, 0.034), "all")
        self.b_c1.on_clicked(lambda _: self.centre_one())
        self.b_cA.on_clicked(lambda _: self.centre_all())
        self.b_r1 = Button(b(0.218, 0.145, 0.030, 0.034), "reset")
        self.b_save = Button(b(0.251, 0.145, 0.028, 0.034), "save")
        self.b_exp = Button(b(0.282, 0.145, 0.032, 0.034), "export")
        self.b_r1.on_clicked(lambda _: self.reset_one())
        self.b_save.on_clicked(lambda _: self.save())
        self.b_exp.on_clicked(lambda _: self.export())

        self.r_mode = RadioButtons(b(0.330, 0.150, 0.082, 0.068), MODES,
                                   active=MODES.index(self.mode))
        self.r_mode.on_clicked(self.on_mode)
        self.fig.text(0.330, 0.224, "per-contact reduction", fontsize=8, color=INK)

        self.s_k = Slider(b(0.487, 0.196, 0.095, 0.019), "top K", 1, 62,
                          valinit=self.k, valstep=1, valfmt="%d")
        self.s_win = Slider(b(0.487, 0.163, 0.095, 0.019), "window ±ms",
                            2.0, 150.0, valinit=self.win_ms, valfmt="%.0f")
        self.s_search = Slider(b(0.487, 0.130, 0.095, 0.019), "search ±ms",
                               2.0, 150.0, valinit=self.search_ms, valfmt="%.0f")
        self.s_view = Slider(b(0.487, 0.097, 0.095, 0.019), "view ±ms",
                             20.0, 190.0, valinit=self.view_ms, valfmt="%.0f")
        self.s_k.on_changed(self.on_k)
        self.s_win.on_changed(self.on_win)
        self.s_search.on_changed(self.on_search)
        self.s_view.on_changed(self.on_view)

        self.c_opt = CheckButtons(b(0.630, 0.145, 0.082, 0.075),
                                  ["skip railed", "baseline-subtract",
                                   "60 Hz notch"],
                                  [False, True, False])
        self.c_opt.on_clicked(self.on_opt)

        self.txt = self.fig.text(0.728, 0.240, "", fontsize=8.5, color=INK,
                                 va="top", family="monospace")
        self.stat_txt = self.fig.text(0.040, 0.050, "", fontsize=8.5,
                                      color=INK, va="top", family="monospace")

    def _progress(self, i, n, msg):
        self.stat_txt.set_text("building event store  [%d/%d]  %s\n"
                               "(v4 needs the rail mask, so the first run "
                               "re-reads: ~90 s)" % (i, n, msg))
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
        self.hand[i], self.edge[i] = True, False
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
        elif k == "x":
            self.next_censored()
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

    def _walk(self, mask, what):
        o = self.order
        start = self.pos[self.kind] % len(o)
        for j in range(1, len(o) + 1):
            m = (start + j) % len(o)
            if mask[m]:
                self.pos[self.kind] = m
                self.draw(note="%s %s" % (what, self.st.label(int(o[m]))))
                return
        self.draw(note="no %s events in %s" % (what, self.kind))

    def next_flagged(self):
        self._walk(self.edge[self.order], "flagged")

    def next_censored(self):
        _, _, _, R = self.stats(self.kind)
        self._walk(R, "censored")

    def on_jump(self, text):
        try:
            want = int(str(text).strip())
        except ValueError:
            return
        hit = np.where(self.st.ids[self.order] == want)[0]
        if hit.size:
            self.pos[self.kind] = int(hit[0])
            self.draw()
        else:
            self.draw(note="no %s %d" % (self.kind, want))

    def on_mode(self, label):
        self.mode = label
        self.draw()

    @staticmethod
    def _dragging(s):
        return bool(getattr(s, "drag_active", False))

    def on_k(self, v):
        self.k = int(v)
        if self._dragging(self.s_k):
            return
        self.draw()

    def on_win(self, v):
        self.win_ms = float(v)
        if self._dragging(self.s_win):
            return
        self.draw()

    def on_search(self, v):
        self.search_ms = float(v)
        if self._dragging(self.s_search):
            return
        self.centre_all()

    def on_view(self, v):
        self.view_ms = min(float(v), self.st.half_ms - 5.0)
        if self._dragging(self.s_view):
            return
        self.draw()

    def on_opt(self, label):
        st = dict(zip(["skip railed", "baseline-subtract", "60 Hz notch"],
                      self.c_opt.get_status()))
        self.skip_railed = st["skip railed"]
        self.baseline = st["baseline-subtract"]
        want = 60.0 if st["60 Hz notch"] else None
        if want != self.st.notch:
            self.stat_txt.set_text("applying notch ...")
            self.fig.canvas.draw_idle()
            self.st.set_notch(want)
        self.draw()

    # --------------------------------------------------------------- output
    def save(self):
        rows = [{"kind": str(self.st.kinds[j]), "id": int(self.st.ids[j]),
                 "t_s": float(self.st.t_s[j]), "shift": int(self.shift[j]),
                 "shift_ms": self.shift[j] / self.st.fs * 1e3,
                 "hand": bool(self.hand[j]), "at_edge": bool(self.edge[j]),
                 "centring_method": self.method, "search_ms": self.search_ms,
                 "saved_utc": dt.datetime.utcnow().isoformat(timespec="seconds")}
                for j in range(len(self.st))]
        pd.DataFrame(rows).to_csv(PICKS, index=False)
        self.draw(note="saved -> %s" % os.path.basename(PICKS))

    def export(self):
        rows, prof = [], []
        for kind in ("IED", "DS"):
            idx = self.st.where(kind)
            S, P, W, R = self.stats(kind)
            for j, i in enumerate(idx):
                wc = int(self.p.numbers[W[j]]) if W[j] >= 0 else -1
                rows.append({
                    "kind": kind, "id": int(self.st.ids[i]),
                    "t_s": float(self.st.t_s[i]),
                    "centre_s": float(self.st.t_s[i]) + self.shift[i] / self.st.fs,
                    "shift_ms": self.shift[i] / self.st.fs * 1e3,
                    "hand_placed": bool(self.hand[i]),
                    "centre_at_search_edge": bool(self.edge[i]),
                    "stat_uV": S[j], "mode": self.mode, "top_k": self.k,
                    "peak_csc": wc,
                    "peak_region": self.p.region.get(wc, ""),
                    "censored": bool(R[j]),
                    "skip_railed": self.skip_railed,
                    "window_ms": self.win_ms, "search_ms": self.search_ms,
                    "centring_method": self.method,
                    "baseline_subtracted": self.baseline,
                    "lowpass_hz": self.st.lowpass or 0,
                    "notch_hz": self.st.notch or 0, "fs_hz": self.st.fs,
                    "n_channels": int(self.p.included.sum()),
                    "excluded": ",".join(str(x) for x in self.p.bad),
                })
                for c, n in enumerate(self.p.numbers):
                    prof.append({"kind": kind, "id": int(self.st.ids[i]),
                                 "csc": int(n),
                                 "region": self.p.region.get(int(n), ""),
                                 "included": bool(self.p.included[c]),
                                 "value_uV": P[j, c], "mode": self.mode,
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

    def _stackplot(self, ax, y, title, colour, hi=-1, rail=None):
        t = (np.arange(y.shape[0]) - y.shape[0] // 2) / self.st.fs * 1e3
        per = np.nanpercentile(np.abs(y - np.nanmedian(y, axis=0)), 99.0, axis=0)
        step = max(2.0 * float(np.nanmedian(per)) / self.gain, 1e-6)
        cols, lws = [], []
        for k in range(y.shape[1]):
            if k == hi:
                cols.append(to_rgba(WINC, 1.0)); lws.append(1.7)
            elif not self.p.included[k]:
                cols.append(to_rgba(BADC, 0.45)); lws.append(0.7)
            elif rail is not None and rail[k]:
                cols.append(to_rgba(BADC, 0.85)); lws.append(0.9)
            else:
                cols.append(to_rgba(colour, 1.0)); lws.append(0.8)
        segs = [np.column_stack((t, y[:, k] - k * step))
                for k in range(y.shape[1])]
        ax.add_collection(LineCollection(segs, colors=cols, linewidths=lws,
                                         zorder=3))
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
        s, per, usable, w = self.st.peak_stat(i, self.shift[i], self.win_ms,
                                              **self._kw())
        c = self.st.stamp_i + int(self.shift[i])
        h = int(round(self.win_ms * 1e-3 * self.st.fs))
        a, b = max(0, c - h), min(self.st.rail.shape[1], c + h + 1)
        railed = self.st.rail[i, a:b, :].any(axis=0)
        ncens = int((railed & self.p.included).sum())
        tag = "HAND" if self.hand[i] else ("EDGE" if self.edge[i] else "auto")
        self._stackplot(ax, self.st.slice_(i, self.shift[i], self.view_ms),
                        "%s  %+.2f ms  [%s]\npeak %s = %.0f µV%s"
                        % (self.st.label(i), self.shift[i] / self.st.fs * 1e3,
                           tag, self.p.label(w) if w >= 0 else "--", s,
                           "   %d railed" % ncens if ncens else ""),
                        CLASS_C[self.kind], hi=w, rail=railed)
        if ncens:
            ax.title.set_color(BADC)

    def _class_average(self, kind):
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
            cnt += np.isfinite(s[:, :1])
            acc += np.nan_to_num(s)
        out = acc / np.maximum(cnt, 1)
        self._avg_cache = {key: out}
        return out

    def _average(self):
        ax = self.ax_avg
        ax.clear()
        idx = self.order
        _, _, _, R = self.stats(self.kind)
        self._stackplot(ax, self._class_average(self.kind),
                        "%s average of %d   (%d hand, %d censored)"
                        % (self.kind, len(idx), int(self.hand[idx].sum()),
                           int(R.sum())), CLASS_C[self.kind])
        ax.set_yticklabels([])

    def _act_window(self, i):
        act = self.st.activity(i, self.baseline)
        h = int(round(self.view_ms * 1e-3 * self.st.fs))
        c = self.st.stamp_i + int(self.shift[i])
        y = np.full(2 * h + 1, np.nan)
        lo, hi = c - h, c + h + 1
        a, b = max(0, lo), min(len(act), hi)
        y[a - lo:b - lo] = act[a:b]
        return y, h

    def _activity(self):
        ax = self.ax_act
        ax.clear()
        i = self.cur
        y, h = self._act_window(i)
        t = (np.arange(len(y)) - h) / self.st.fs * 1e3
        col = CLASS_C[self.kind]
        ax.plot(t, y, lw=1.0, color=col)
        ax.axvline(0.0, color="#333333", lw=1.2)
        ax.axvspan(-self.win_ms, self.win_ms, color=col, alpha=0.09, lw=0)
        s0 = -self.shift[i] / self.st.fs * 1e3
        ax.axvspan(s0 - self.search_ms, s0 + self.search_ms, facecolor="none",
                   edgecolor=BADC if self.edge[i] else "#555555",
                   ls="--", lw=1.6 if self.edge[i] else 0.9)
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
            A[j], _ = self._act_window(int(i))
        t = (np.arange(A.shape[1]) - h) / self.st.fs * 1e3
        col = CLASS_C[self.kind]
        mu, sd = np.nanmean(A, axis=0), np.nanstd(A, axis=0)
        ax.fill_between(t, mu - sd, mu + sd, color=col, alpha=0.20, lw=0)
        ax.plot(t, mu, lw=1.6, color=col)
        ax.axvline(0.0, color="#333333", lw=1.2)
        ax.axvspan(-self.win_ms, self.win_ms, color=col, alpha=0.09, lw=0)
        ax.set_xlim(-self.view_ms, self.view_ms)
        ax.set_xlabel("ms from centre   (mean ± SD)", fontsize=8.5)
        ax.tick_params(labelsize=7, labelleft=False)

    def _profile(self):
        ax = self.ax_prof
        ax.clear()
        k = np.arange(len(self.p.numbers))
        inc = self.p.included
        self._peakcount = {}
        for kind in ("IED", "DS"):
            _, P, W, _ = self.stats(kind)
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
            cnt = np.bincount(W[W >= 0], minlength=len(k))
            self._peakcount[kind] = cnt
            # Where each class's winning contact actually sits -- the profile
            # is a mean over events, and a mean can peak where no single event
            # did.
            hot = np.where(cnt > 0)[0]
            if hot.size:
                ax.scatter(np.full(hot.size, np.nanmax(mu) * 1.04), hot,
                           s=np.clip(cnt[hot] * 6, 6, 90),
                           color=CLASS_C[kind], alpha=0.45, marker="o",
                           edgecolors="none", zorder=5)
        for c in np.where(~inc)[0]:
            ax.axhline(c, color=BADC, lw=0.8, alpha=0.5)
        ax.invert_yaxis()
        ax.set_yticks(range(0, len(k), 4))
        ax.set_yticklabels([self.p.label(i) for i in range(0, len(k), 4)],
                           fontsize=6)
        ax.set_xlabel("%s (µV)" % self.mode, fontsize=8.5)
        ax.set_title("per contact, ±%.0f ms\n(dots: where the peak was)"
                     % self.win_ms, fontsize=9.5)
        ax.legend(fontsize=7.5, loc="lower right", framealpha=0.9)

    def _compare(self):
        ax = self.ax_cmp
        ax.clear()
        rng = np.random.default_rng(0)
        self._summary = []
        for j, kind in enumerate(("IED", "DS")):
            S, _, _, R = self.stats(kind)
            ok = np.isfinite(S)
            S, R = S[ok], R[ok]
            if S.size == 0:
                continue
            bp = ax.boxplot([S], positions=[j], widths=0.44, whis=(5, 95),
                            showfliers=False, patch_artist=True,
                            manage_ticks=False)
            for p in bp["boxes"]:
                p.set(facecolor=CLASS_C[kind], alpha=0.25,
                      edgecolor=CLASS_C[kind], lw=1.3)
            for part in ("whiskers", "caps", "medians"):
                for p in bp[part]:
                    p.set(color=CLASS_C[kind], lw=1.5)
            # Censored events drawn in the rail colour: a class whose points
            # are mostly red is reporting lower bounds, not amplitudes.
            sel = np.arange(S.size) if S.size <= 120 else rng.choice(
                S.size, 120, replace=False)
            x = j + (rng.random(sel.size) - 0.5) * 0.30
            ax.plot(x[~R[sel]], S[sel][~R[sel]], "o", ms=2.6,
                    color=CLASS_C[kind], alpha=0.45, mec="none", zorder=3)
            ax.plot(x[R[sel]], S[sel][R[sel]], "o", ms=3.0, color=BADC,
                    alpha=0.6, mec="none", zorder=4)
            self._summary.append((kind, S.size, float(np.median(S)),
                                  float(np.percentile(S, 25)),
                                  float(np.percentile(S, 75)), S,
                                  float(R.mean())))
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["IED", "DS"], fontsize=9)
        ax.set_xlim(-0.6, 1.6)
        ax.set_ylabel("%s, top %d (µV)" % (self.mode, self.k), fontsize=8.5)
        ax.set_title("per event, ±%.0f ms\n(red = censored)" % self.win_ms,
                     fontsize=9.5)

    def _hist(self):
        ax = self.ax_hist
        ax.clear()
        sm = getattr(self, "_summary", [])
        if not sm:
            return
        lo = min(float(np.min(s[5])) for s in sm)
        hi = max(float(np.max(s[5])) for s in sm)
        bins = np.linspace(lo, hi, 26)
        for (kind, n, med, q1, q3, S, cens) in sm:
            ax.hist(S, bins=bins, density=True, histtype="stepfilled",
                    color=CLASS_C[kind], alpha=0.28)
            ax.hist(S, bins=bins, density=True, histtype="step",
                    color=CLASS_C[kind], lw=1.5,
                    label="%s n=%d (%.0f%% cens)" % (kind, n, 100 * cens))
            ax.axvline(med, color=CLASS_C[kind], ls="--", lw=1.2)
        ax.set_xlabel("%s (µV)" % self.mode, fontsize=8.5)
        ax.set_ylabel("density", fontsize=8.5)
        ax.set_title("distributions", fontsize=9.5)
        ax.legend(fontsize=7, framealpha=0.9)
        ax.tick_params(labelsize=7)

    def _readout(self, note=""):
        L = ["statistic %s, top K=%d" % (self.mode, self.k),
             "contacts  %d of %d   excluded %s   railed %s"
             % (self.p.included.sum(), len(self.p.numbers),
                ", ".join("CSC%d" % b for b in self.p.bad),
                "skipped" if self.skip_railed else "KEPT"),
             "window    ±%.0f ms   centring %s ±%.0f ms"
             % (self.win_ms, self.method, self.search_ms),
             ""]
        for (kind, n, med, q1, q3, S, cens) in getattr(self, "_summary", []):
            L.append("%-4s n=%3d  median %7.1f  IQR %.0f-%.0f  censored %3.0f%%"
                     % (kind, n, med, q1, q3, 100 * cens))
        sm = getattr(self, "_summary", [])
        if len(sm) == 2:
            a, b = sm[0][5], sm[1][5]
            L.append("")
            try:
                from scipy.stats import mannwhitneyu
                U, pv = mannwhitneyu(a, b, alternative="two-sided")
                delta = 2.0 * (U / (len(a) * len(b))) - 1.0
                L.append("Mann-Whitney U=%.0f  p=%.4g   delta %+0.3f"
                         % (U, pv, delta))
            except Exception as exc:
                L.append("test unavailable: %s" % exc)
            if max(sm[0][6], sm[1][6]) > 0.05:
                L.append("")
                L.append("CENSORED: IED %.0f%% vs DS %.0f%% of events have a"
                         % (100 * sm[0][6], 100 * sm[1][6]))
                L.append("railed contact in-window. These are LOWER BOUNDS,")
                L.append("and the two classes are censored unequally.")
        if note or self._note:
            L.append("")
            L.append(note or self._note)
        self.txt.set_text("\n".join(L))

        i = self.cur
        s, _, _, w = self.st.peak_stat(i, self.shift[i], self.win_ms, **self._kw())
        self.stat_txt.set_text(
            "%s   t=%.3f s   centre %+.2f ms   %s = %.1f uV on %s"
            % (self.st.label(i), self.st.t_s[i],
               self.shift[i] / self.st.fs * 1e3, self.mode, s,
               self.p.label(w) if w >= 0 else "--"))


def main():
    ap = argparse.ArgumentParser(description="IED vs DS, biggest contact")
    ap.add_argument("--folder", default=NCS_FOLDER)
    ap.add_argument("--ds-bank", default=DS_BANK)
    ap.add_argument("--anat", default=ANAT)
    ap.add_argument("--category", default="Solid")
    ap.add_argument("--mode", default=MODES[0], choices=list(MODES))
    ap.add_argument("--k", type=int, default=1, help="average the top K contacts")
    ap.add_argument("--win-ms", type=float, default=25.0)
    ap.add_argument("--view-ms", type=float, default=100.0)
    ap.add_argument("--search-ms", type=float, default=50.0)
    ap.add_argument("--half-ms", type=float, default=HALF_MS)
    ap.add_argument("--lowpass", type=float, default=300.0)
    ap.add_argument("--q", type=int, default=DEC_Q)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    Bench(args)
    plt.show()


if __name__ == "__main__":
    main()
