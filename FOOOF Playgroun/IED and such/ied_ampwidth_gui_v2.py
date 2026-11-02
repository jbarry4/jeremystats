"""
ied_ampwidth_gui_v2.py -- IEDs against dentate spikes: centre each one, then
compare what the whole probe did.

WHAT v2 IS FOR, AS AGAINST v1
=============================
v1 answers "how big and how wide is the peak on the best channel of this
IED". That is a question about one contact. v2 answers a different one:

    averaged over an adjustable window, and over every good contact, how much
    did the probe move -- and does that differ between an IED and a dentate
    spike?

So the measurement here is one number per event,

    mean over included channels, mean over the window, of |x(t) - baseline|

and the products are a class average and a comparison, not a peak table.

64 CONTACTS, NOT 32, AND WHY THAT IS THE WHOLE REASON THIS READS .ncs
=====================================================================
The bad channels for this session are CSC55 and CSC59. The .mat that v1 and
the IED pipeline read keeps only the EVEN CSCs, so neither bad channel is in
it and excluding them there removes nothing while reporting that it did. v2
reads the raw .ncs folder, gets all 64 contacts, and drops 55 and 59 for
real -- 62 remain, and the panel says so. `ied_ds.py` has the detail, along
with the bit-equality check that lets IED stamps (.mat samples) and DS stamps
(.ncs seconds) be put on one timeline.

CENTRING
========
Both stamp systems mark an event, neither marks its centre: the IED stamp is
the midpoint of a threshold crossing and the DS stamp is the curator's click.
An average of events centred on different parts of their waveforms is a
smeared version of none of them, so the centre is yours -- click the stack,
and the class average and both comparison panels update. Centres are saved
per event and restored.

There are two automatic methods, and they answer different questions:

  mean|amp| peak   (default) the time, inside the search window, at which the
                   ACROSS-CHANNEL average of |x - baseline| is largest. This
                   is the peak of the very quantity the comparison measures,
                   so the event is centred on the moment the whole probe was
                   most active, and a narrow measure window then sits on the
                   maximum of what it is about to average.
  max channel      the time of the single largest deflection on any one good
                   contact. Winner-take-all: on a multiphasic IED this can
                   land on whichever phase happens to be biggest on whichever
                   contact happens to be loudest, and that need not be the
                   same feature from one event to the next.

Both search around the ORIGINAL STAMP, never around the current centre, so
pressing the button twice cannot walk the centre down the trace and the
result does not depend on your click history.

The strip under each stack is the trace being maximised -- the across-channel
mean|amp| against time, with the search window shaded and the chosen centre
marked. A centring you cannot see is a centring you cannot check: if that
trace has two peaks of similar height, the method picked one of them and the
event deserves a hand-placed centre.

The averages are over whatever centres are currently set, which means a
half-centred set produces a half-smeared average. That is visible rather than
hidden: the class-average panel says how many of its events you have centred
by hand.

RUN
===
  python ied_ampwidth_gui_v2.py
  python ied_ampwidth_gui_v2.py -n 8
  python ied_ampwidth_gui_v2.py --ied 10,15,16,20,26 --ds 1,2,3,4,5

KEYS
====
  left / right  previous / next event within the current class
  tab           switch class (IED <-> DS)
  c             centre this event by the selected method
  C             centre every event in both classes
  r             reset the centre to the original stamp
  s / e         save centres / export the comparison tables
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.widgets import Button, CheckButtons, RadioButtons, Slider, TextBox

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from ied_ds import (BAD_CHANNELS, DS_BANK, NCS_FOLDER, Probe64,  # noqa: E402
                    mean_abs_amp, prep, read_ds_bank, read_ied_events)

INK = "#1b2220"
GREY = "#a8b0ad"
BADC = "#c0392b"
IEDC = "#b8620a"
DSC = "#1f6feb"
CLASS_C = {"IED": IEDC, "DS": DSC}

CACHE_MS = 300.0        # cached either side of each stamp; re-centring is free

# The two automatic centring methods. Order matters: the first is the default.
METHODS = ("mean|amp| peak", "max channel")
PICKS = os.path.join(_HERE, "ied_ds_centres.csv")
OUT_EVENTS = os.path.join(_HERE, "ied_ds_event_stats.csv")
OUT_PROFILE = os.path.join(_HERE, "ied_ds_channel_profile.csv")


class Ev:
    """One event, its cached window, and the centre you chose for it."""

    def __init__(self, kind, eid, t_s):
        self.kind, self.id, self.t_s = kind, int(eid), float(t_s)
        self.raw = None
        self.filt = None
        self.stamp_i = 0        # index of the original stamp in the cache
        self.shift = 0          # samples the user moved the centre
        self.placed = False     # centred by hand?
        self.at_edge = False    # auto-centring hit the search boundary

    @property
    def centre_i(self):
        return self.stamp_i + self.shift


class Bench:
    def __init__(self, args):
        self.p = Probe64(args.folder, BAD_CHANNELS, args.anat)
        self.args = args
        self.win_ms = args.win_ms
        self.view_ms = args.view_ms
        self.search_ms = args.search_ms
        self.method = METHODS[0]
        self.lowpass = args.lowpass
        self.notch = None
        self.baseline = True
        self.gain = 1.0
        self.kind = "IED"
        self.pos = {"IED": 0, "DS": 0}

        ied = read_ied_events(category=args.category)
        ds = read_ds_bank(args.ds_bank)
        self.sets = {
            "IED": self._pick(ied, args.ied, args.n),
            "DS": self._pick(ds, args.ds, args.n),
        }
        self.centres = self._load_centres()
        self._build()
        self._preload()
        self.draw()

    # ------------------------------------------------------------- events
    def _pick(self, tab, want, n):
        if want:
            ids = [int(x) for x in str(want).replace(" ", "").split(",") if x]
            tab = tab[tab["id"].isin(ids)]
            tab = tab.set_index("id").loc[[i for i in ids if i in set(tab["id"])]]
            tab = tab.reset_index()
        else:
            tab = tab.head(n)
        kind = str(tab["kind"].iloc[0]) if len(tab) else "?"
        return [Ev(kind, r["id"], r["t_s"]) for _, r in tab.iterrows()]

    def _load_centres(self):
        if not os.path.exists(PICKS):
            return {}
        try:
            t = pd.read_csv(PICKS)
        except Exception:
            return {}
        return {(str(r["kind"]), int(r["id"])): int(r["shift"])
                for _, r in t.iterrows()}

    def _save_centres(self):
        rows = []
        for kind, evs in self.sets.items():
            for e in evs:
                rows.append({"kind": kind, "id": e.id, "t_s": e.t_s,
                             "shift": e.shift,
                             "shift_ms": e.shift / self.p.fs * 1e3,
                             "placed": e.placed,
                             "centring_method": self.method,
                             "search_ms": self.search_ms,
                             "at_edge": e.at_edge,
                             "saved_utc": dt.datetime.utcnow().isoformat(
                                 timespec="seconds")})
        pd.DataFrame(rows).to_csv(PICKS, index=False)

    def _preload(self):
        half = CACHE_MS * 1e-3
        todo = [e for evs in self.sets.values() for e in evs]
        for i, e in enumerate(todo):
            self._status("reading %d/%d  %s%d ..." % (i + 1, len(todo), e.kind, e.id))
            seg, t0 = self.p.read(e.t_s - half, e.t_s + half)
            e.raw = seg
            e.stamp_i = int(round((e.t_s - t0) * self.p.fs))
            e.shift = int(self.centres.get((e.kind, e.id), 0))
            e.placed = (e.kind, e.id) in self.centres
            e.filt = prep(seg, self.p.fs, self.lowpass, self.notch)
        self._status("")

    def _refilter(self):
        for evs in self.sets.values():
            for e in evs:
                e.filt = prep(e.raw, self.p.fs, self.lowpass, self.notch)

    @property
    def evs(self):
        return self.sets[self.kind]

    @property
    def cur(self):
        return self.evs[self.pos[self.kind] % len(self.evs)]

    # ------------------------------------------------------- measurements
    def slice_(self, e, half_ms):
        h = int(round(half_ms * 1e-3 * self.p.fs))
        c = e.centre_i
        n = e.filt.shape[0]
        lo, hi = c - h, c + h + 1
        if lo < 0 or hi > n:                     # pad rather than silently crop
            out = np.full((2 * h + 1, e.filt.shape[1]), np.nan)
            a, b = max(0, lo), min(n, hi)
            out[a - lo:b - lo, :] = e.filt[a:b, :]
            return out
        return e.filt[lo:hi, :]

    def stat(self, e):
        return mean_abs_amp(e.filt, e.centre_i, self.p.fs, self.win_ms,
                            self.p.included, self.baseline)

    def class_stats(self, kind):
        """(scalars[n], profiles[n, 64]) for one class, at current centres."""
        S, P = [], []
        for e in self.sets[kind]:
            s, per = self.stat(e)
            S.append(s)
            P.append(per)
        return np.array(S), np.vstack(P) if P else np.zeros((0, 64))

    def class_average(self, kind):
        """Event-triggered average stack, at the centres currently set."""
        segs = [self.slice_(e, self.view_ms) for e in self.sets[kind]]
        if not segs:
            return None
        n = min(s.shape[0] for s in segs)
        return np.nanmean(np.dstack([s[:n] for s in segs]), axis=2)

    # -------------------------------------------------------------- build
    def _build(self):
        self.fig = plt.figure(figsize=(18.0, 10.2), facecolor="white")
        self.fig.canvas.manager.set_window_title(
            "IED vs dentate spike -- centre, average, compare")
        self.ax_stack = self.fig.add_axes([0.045, 0.355, 0.235, 0.575])
        self.ax_act = self.fig.add_axes([0.045, 0.270, 0.235, 0.070])
        self.ax_avg = self.fig.add_axes([0.315, 0.355, 0.235, 0.575])
        self.ax_avgact = self.fig.add_axes([0.315, 0.270, 0.235, 0.070])
        self.ax_prof = self.fig.add_axes([0.605, 0.27, 0.165, 0.66])
        self.ax_cmp = self.fig.add_axes([0.825, 0.51, 0.155, 0.42])
        self.ax_tab = self.fig.add_axes([0.825, 0.27, 0.155, 0.17])
        self.ax_tab.axis("off")

        self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        b = lambda l, t, w, h: self.fig.add_axes([l, t, w, h])

        self.r_kind = RadioButtons(b(0.045, 0.145, 0.055, 0.075), ("IED", "DS"))
        self.r_kind.on_clicked(self.on_kind)
        self.fig.text(0.045, 0.226, "class", fontsize=8, color=INK)

        self.b_prev = Button(b(0.112, 0.183, 0.040, 0.036), "< prev")
        self.b_next = Button(b(0.156, 0.183, 0.040, 0.036), "next >")
        self.b_prev.on_clicked(lambda _: self.step(-1))
        self.b_next.on_clicked(lambda _: self.step(+1))
        self.b_centre = Button(b(0.112, 0.143, 0.040, 0.036), "centre")
        self.b_reset = Button(b(0.156, 0.143, 0.040, 0.036), "reset")
        self.b_centre.on_clicked(lambda _: self.centre())
        self.b_reset.on_clicked(lambda _: self.reset_centre())

        self.b_centreall = Button(b(0.206, 0.183, 0.062, 0.036), "centre all")
        self.b_centreall.on_clicked(lambda _: self.centre_all())
        self.b_save = Button(b(0.206, 0.143, 0.030, 0.036), "save")
        self.b_exp = Button(b(0.238, 0.143, 0.030, 0.036), "export")
        self.b_save.on_clicked(lambda _: self.save())
        self.b_exp.on_clicked(lambda _: self.export())

        self.r_meth = RadioButtons(b(0.282, 0.143, 0.090, 0.076), METHODS)
        self.r_meth.on_clicked(self.on_method)
        self.fig.text(0.282, 0.224, "centring method", fontsize=8, color=INK)

        # Sliders start right of the method box with room for their own
        # left-hand labels, and end well left of the checkboxes -- a Slider
        # draws its value to the RIGHT of its axes, so the box that follows it
        # has to clear the axes AND that text.
        self.s_search = Slider(b(0.445, 0.196, 0.100, 0.019),
                               "search ±ms", 2.0, 150.0,
                               valinit=self.search_ms, valfmt="%.0f")
        self.s_win = Slider(b(0.445, 0.163, 0.100, 0.019), "window ±ms",
                            2.0, 150.0, valinit=self.win_ms, valfmt="%.0f")
        self.s_view = Slider(b(0.445, 0.130, 0.100, 0.019), "view ±ms",
                             20.0, 200.0, valinit=self.view_ms, valfmt="%.0f")
        self.s_gain = Slider(b(0.445, 0.097, 0.100, 0.019), "gain",
                             0.2, 6.0, valinit=1.0, valfmt="%.1f")
        self.s_search.on_changed(self.on_search)
        self.s_win.on_changed(self.on_win)
        self.s_view.on_changed(self.on_view)
        self.s_gain.on_changed(self.on_gain)

        self.c_opt = CheckButtons(b(0.592, 0.120, 0.093, 0.100),
                                  ["baseline-subtract", "300 Hz lowpass",
                                   "60 Hz notch"],
                                  [True, bool(self.lowpass), False])
        self.c_opt.on_clicked(self.on_opt)

        self.txt = self.fig.text(0.700, 0.225, "", fontsize=8.5, color=INK,
                                 va="top", family="monospace")
        self.stat_txt = self.fig.text(0.045, 0.055, "", fontsize=8.5,
                                      color=INK, va="top", family="monospace")

    def _status(self, msg):
        if not hasattr(self, "txt"):
            return
        self.txt.set_text(msg)
        try:
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()
        except Exception:
            pass

    # ---------------------------------------------------------- callbacks
    def on_click(self, ev):
        if ev.inaxes is not self.ax_stack or ev.xdata is None:
            return
        tb = getattr(self.fig.canvas.manager, "toolbar", None)
        if tb is not None and getattr(tb, "mode", ""):
            return
        e = self.cur
        e.shift += int(round(ev.xdata * 1e-3 * self.p.fs))
        e.placed = True
        e.at_edge = False          # a centre you placed is not clamped
        self.draw()

    def on_key(self, ev):
        if ev.key == "right":
            self.step(+1)
        elif ev.key == "left":
            self.step(-1)
        elif ev.key == "tab":
            self.on_kind("DS" if self.kind == "IED" else "IED")
            self.r_kind.set_active(0 if self.kind == "IED" else 1)
        elif ev.key == "c":
            self.centre()
        elif ev.key == "C":
            self.centre_all()
        elif ev.key == "r":
            self.reset_centre()
        elif ev.key == "s":
            self.save()
        elif ev.key == "e":
            self.export()

    def on_kind(self, label):
        self.kind = label
        self.draw()

    def step(self, d):
        self.pos[self.kind] = (self.pos[self.kind] + d) % len(self.evs)
        self.draw()

    def on_method(self, label):
        self.method = label
        self.draw()

    def on_search(self, v):
        self.search_ms = float(v)
        self.draw()

    def on_win(self, v):
        self.win_ms = float(v)
        self.draw()

    def on_view(self, v):
        self.view_ms = min(float(v), CACHE_MS - 120.0)
        self.draw()

    def on_gain(self, v):
        self.gain = max(float(v), 0.05)
        self.draw()

    def on_opt(self, label):
        st = dict(zip(["baseline-subtract", "300 Hz lowpass", "60 Hz notch"],
                      self.c_opt.get_status()))
        self.baseline = st["baseline-subtract"]
        new_lp = 300.0 if st["300 Hz lowpass"] else None
        new_nt = 60.0 if st["60 Hz notch"] else None
        if (new_lp, new_nt) != (self.lowpass, self.notch):
            self.lowpass, self.notch = new_lp, new_nt
            self._status("re-filtering ...")
            self._refilter()
        self.draw()

    def activity(self, e):
        """Across-channel mean |x - baseline|, against time.

        One number per sample: how much the whole probe was moving at that
        instant. It is the same quantity the comparison averages over a
        window, so centring on its peak and then measuring around that centre
        are the same measurement asked at two scales -- which is why this, and
        not the loudest single contact, is the default.
        """
        y = e.filt[:, self.p.included]
        base = np.median(y, axis=0) if self.baseline else 0.0
        return np.mean(np.abs(y - base), axis=1)

    def _centre_one(self, e):
        """Place `e`'s centre by the selected method.

        Searched around e.stamp_i -- the ORIGINAL stamp -- not around the
        centre currently set. Searching from the current centre makes the
        button non-idempotent: each press re-searches from where the last
        press landed, so the centre walks along the trace and where it ends up
        depends on how many times it was clicked.
        """
        h = int(round(self.search_ms * 1e-3 * self.p.fs))
        n = e.filt.shape[0]
        lo, hi = max(0, e.stamp_i - h), min(n, e.stamp_i + h + 1)
        if hi - lo < 2:
            return
        if self.method == "mean|amp| peak":
            pick = lo + int(np.argmax(self.activity(e)[lo:hi]))
        else:
            seg = e.filt[lo:hi, :][:, self.p.included]
            dev = np.abs(seg - np.median(e.filt[:, self.p.included], axis=0))
            pick = lo + int(np.argmax(dev.max(axis=1)))
        # An argmax that lands ON the boundary is not a maximum that was
        # found -- it is the search running out of room, and the real peak is
        # somewhere outside. Left unflagged it reads as a centre like any
        # other, and it silently moves the event to the window edge, which is
        # worse than not centring it at all. Widening `search +-ms` resolves
        # it; the flag says which events need that.
        e.at_edge = bool(pick <= lo or pick >= hi - 1)
        e.shift = pick - e.stamp_i
        e.placed = True

    def centre(self):
        self._centre_one(self.cur)
        self.draw()

    def centre_all(self):
        for evs in self.sets.values():
            for e in evs:
                self._centre_one(e)
        self.draw()

    def reset_centre(self):
        self.cur.shift = 0
        self.cur.placed = False
        self.cur.at_edge = False
        self.draw()

    # ------------------------------------------------------------- output
    def save(self):
        self._save_centres()
        self.draw(note="centres saved -> %s" % os.path.basename(PICKS))

    def export(self):
        self._save_centres()
        rows, prof = [], []
        for kind in ("IED", "DS"):
            for e in self.sets[kind]:
                s, per = self.stat(e)
                rows.append({
                    "kind": kind, "id": e.id, "t_s": e.t_s,
                    "centre_s": e.t_s + e.shift / self.p.fs,
                    "shift_ms": e.shift / self.p.fs * 1e3, "placed": e.placed,
                    "centring_method": self.method,
                    "search_ms": self.search_ms,
                    "centre_at_search_edge": e.at_edge,
                    "mean_abs_amp_uV": s, "window_ms": self.win_ms,
                    "baseline_subtracted": self.baseline,
                    "lowpass_hz": self.lowpass or 0, "notch_hz": self.notch or 0,
                    "n_channels": int(self.p.included.sum()),
                    "excluded": ",".join(str(b) for b in self.p.bad),
                })
                for i, n in enumerate(self.p.numbers):
                    prof.append({"kind": kind, "id": e.id, "csc": int(n),
                                 "region": self.p.region.get(int(n), ""),
                                 "included": bool(self.p.included[i]),
                                 "mean_abs_amp_uV": per[i],
                                 "window_ms": self.win_ms})
        pd.DataFrame(rows).to_csv(OUT_EVENTS, index=False)
        pd.DataFrame(prof).to_csv(OUT_PROFILE, index=False)
        self.draw(note="exported -> %s + %s" % (os.path.basename(OUT_EVENTS),
                                                os.path.basename(OUT_PROFILE)))

    # ------------------------------------------------------------ drawing
    def draw(self, note=""):
        self._stack()
        self._activity_strip()
        self._average()
        self._avg_activity_strip()
        self._profile()
        self._compare()
        self._readout(note)
        self.fig.canvas.draw_idle()

    def _act_slice(self, e):
        """This event's activity trace over the viewed span, centred."""
        act = self.activity(e)
        h = int(round(self.view_ms * 1e-3 * self.p.fs))
        c, n = e.centre_i, len(act)
        lo, hi = c - h, c + h + 1
        out = np.full(2 * h + 1, np.nan)
        a, b = max(0, lo), min(n, hi)
        out[a - lo:b - lo] = act[a:b]
        return out

    def _activity_strip(self):
        """The trace the centring maximises, so the choice can be checked."""
        ax = self.ax_act
        ax.clear()
        e = self.cur
        y = self._act_slice(e)
        t = (np.arange(len(y)) - len(y) // 2) / self.p.fs * 1e3
        col = CLASS_C[e.kind]
        ax.plot(t, y, lw=1.0, color=col)
        ax.axvline(0.0, color="#333333", lw=1.2)
        ax.axvspan(-self.win_ms, self.win_ms, color=col, alpha=0.09, lw=0)
        # The search window, drawn where it actually sat: around the STAMP,
        # which is -shift from the centre the plot is drawn on.
        s0 = -e.shift / self.p.fs * 1e3
        ax.axvspan(s0 - self.search_ms, s0 + self.search_ms, facecolor="none",
                   edgecolor=BADC if e.at_edge else "#555555",
                   ls="--", lw=1.6 if e.at_edge else 0.9)
        if e.at_edge:
            ax.text(0.99, 0.88, "centre clamped to search edge",
                    transform=ax.transAxes, ha="right", va="top",
                    fontsize=7.5, color=BADC, fontweight="bold")
        ax.set_xlim(-self.view_ms, self.view_ms)
        ax.set_ylabel("mean|amp|", fontsize=7)
        ax.set_xlabel("ms from centre   (click the stack above to move it)",
                      fontsize=8.5)
        ax.tick_params(labelsize=7)

    def _avg_activity_strip(self):
        ax = self.ax_avgact
        ax.clear()
        segs = [self._act_slice(e) for e in self.evs]
        if not segs:
            return
        A = np.vstack(segs)
        t = (np.arange(A.shape[1]) - A.shape[1] // 2) / self.p.fs * 1e3
        col = CLASS_C[self.kind]
        for row in A:
            ax.plot(t, row, lw=0.6, color=col, alpha=0.35)
        ax.plot(t, np.nanmean(A, axis=0), lw=1.6, color=col)
        ax.axvline(0.0, color="#333333", lw=1.2)
        ax.axvspan(-self.win_ms, self.win_ms, color=col, alpha=0.09, lw=0)
        ax.set_xlim(-self.view_ms, self.view_ms)
        ax.set_xlabel("ms from centre", fontsize=8.5)
        ax.tick_params(labelsize=7, labelleft=False)

    def _stackplot(self, ax, y, title, colour):
        t = (np.arange(y.shape[0]) - y.shape[0] // 2) / self.p.fs * 1e3
        per = np.nanpercentile(np.abs(y - np.nanmedian(y, axis=0)), 99.0, axis=0)
        step = max(2.0 * float(np.nanmedian(per)) / self.gain, 1e-6)
        for k in range(y.shape[1]):
            good = self.p.included[k]
            ax.plot(t, y[:, k] - k * step, lw=0.9 if good else 0.7,
                    color=colour if good else BADC,
                    alpha=1.0 if good else 0.5, zorder=3 if good else 2)
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
        ax.set_title(title, fontsize=9.5)
        return step

    def _stack(self):
        ax = self.ax_stack
        ax.clear()
        e = self.cur
        y = self.slice_(e, self.view_ms)
        self._stackplot(ax, y, "%s %d   centre %+.2f ms%s"
                        % (e.kind, e.id, e.shift / self.p.fs * 1e3,
                           "  AT SEARCH EDGE" if e.at_edge else
                           ("" if e.placed else "   (stamp, not centred)")),
                        CLASS_C[e.kind])
        ax.set_xticklabels([])          # the strip below carries the axis

    def _average(self):
        ax = self.ax_avg
        ax.clear()
        y = self.class_average(self.kind)
        if y is None:
            return
        placed = sum(e.placed for e in self.evs)
        self._stackplot(ax, y, "%s average of %d   (%d centred)"
                        % (self.kind, len(self.evs), placed), CLASS_C[self.kind])
        ax.set_xticklabels([])
        ax.set_yticklabels([])

    def _profile(self):
        ax = self.ax_prof
        ax.clear()
        k = np.arange(len(self.p.numbers))
        for kind in ("IED", "DS"):
            _, P = self.class_stats(kind)
            if P.size == 0:
                continue
            # Averaged only over the included columns. The excluded contacts
            # are all-NaN, and handing an all-NaN column to nanmean is both a
            # warning and a way to end up with a 0.0 where there is no data.
            inc = self.p.included
            mu = np.full(P.shape[1], np.nan)
            sem = np.full(P.shape[1], np.nan)
            mu[inc] = np.nanmean(P[:, inc], axis=0)
            sem[inc] = np.nanstd(P[:, inc], axis=0) / max(np.sqrt(P.shape[0]), 1)
            ax.plot(mu, k, "-", lw=1.4, color=CLASS_C[kind], label=kind)
            ax.fill_betweenx(k, mu - sem, mu + sem, color=CLASS_C[kind],
                             alpha=0.20, lw=0)
        for i, n in enumerate(self.p.numbers):
            if not self.p.included[i]:
                ax.axhline(i, color=BADC, lw=0.8, alpha=0.5)
        ax.invert_yaxis()
        ax.set_yticks(range(0, len(k), 4))
        ax.set_yticklabels([self.p.label(i) for i in range(0, len(k), 4)],
                           fontsize=6)
        ax.set_xlabel("mean |amp| (µV)", fontsize=8.5)
        ax.set_title("per-contact, ±%.0f ms" % self.win_ms, fontsize=9.5)
        ax.legend(fontsize=7.5, loc="lower right", framealpha=0.9)

    def _compare(self):
        ax = self.ax_cmp
        ax.clear()
        rng = np.random.default_rng(0)
        summary = []
        for j, kind in enumerate(("IED", "DS")):
            S, _ = self.class_stats(kind)
            S = S[np.isfinite(S)]
            if S.size == 0:
                continue
            x = j + (rng.random(S.size) - 0.5) * 0.22
            ax.plot(x, S, "o", ms=6, color=CLASS_C[kind], alpha=0.85,
                    mec="white", mew=0.8, zorder=3)
            mu, sd = float(np.mean(S)), float(np.std(S, ddof=1)) if S.size > 1 else 0.0
            ax.hlines(mu, j - 0.28, j + 0.28, color=CLASS_C[kind], lw=2.4, zorder=4)
            ax.vlines(j, mu - sd, mu + sd, color=CLASS_C[kind], lw=1.2, zorder=2)
            summary.append((kind, S.size, mu, sd))
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["IED", "DS"], fontsize=9)
        ax.set_xlim(-0.55, 1.55)
        ax.set_ylabel("mean |amp| (µV)", fontsize=8.5)
        ax.set_title("per event, ±%.0f ms, %d contacts"
                     % (self.win_ms, int(self.p.included.sum())), fontsize=9.5)
        self._summary = summary

    def _readout(self, note=""):
        L = ["contacts  %d of %d   excluded %s"
             % (self.p.included.sum(), len(self.p.numbers),
                ", ".join("CSC%d" % b for b in self.p.bad)),
             "window    ±%.0f ms    baseline %s    lowpass %s"
             % (self.win_ms, "on" if self.baseline else "off",
                ("%.0f Hz" % self.lowpass) if self.lowpass else "off"),
             "centring  %s, ±%.0f ms (%.0f ms span)"
             % (self.method, self.search_ms, 2 * self.search_ms),
             ""]
        for kind, n, mu, sd in getattr(self, "_summary", []):
            L.append("%-4s n=%d   mean|amp| %8.2f +- %.2f uV" % (kind, n, mu, sd))
        if len(getattr(self, "_summary", [])) == 2:
            (_, _, a, _), (_, _, b, _) = self._summary
            if b:
                L.append("")
                L.append("IED / DS  = %.2fx" % (a / b))
        nplaced = sum(e.placed for evs in self.sets.values() for e in evs)
        nedge = sum(e.at_edge for evs in self.sets.values() for e in evs)
        ntot = sum(len(v) for v in self.sets.values())
        L.append("")
        L.append("centred   %d of %d events" % (nplaced, ntot))
        if nedge:
            L.append("WARNING   %d at the search edge -- widen it" % nedge)
        if note:
            L.append(note)
        self.txt.set_text("\n".join(L))

        e = self.cur
        s, _ = self.stat(e)
        self.stat_txt.set_text(
            "%s %d   t=%.3f s   centre %+.2f ms   mean|amp| %.2f uV"
            % (e.kind, e.id, e.t_s, e.shift / self.p.fs * 1e3, s))


def main():
    ap = argparse.ArgumentParser(description="IED vs dentate spike workbench")
    ap.add_argument("--folder", default=NCS_FOLDER)
    ap.add_argument("--ds-bank", default=DS_BANK)
    ap.add_argument("--anat", default=None)
    ap.add_argument("--category", default="Solid", help="which IEDs to draw on")
    ap.add_argument("-n", type=int, default=5, help="events per class")
    ap.add_argument("--ied", default="", help="explicit IED ids, comma separated")
    ap.add_argument("--ds", default="", help="explicit DS ids, comma separated")
    # +-50 ms: at +-25 the centring clamped real dentate spikes to the search
    # boundary (DS2's peak is at +27.5 ms), which moves the event to the edge
    # instead of onto its peak. v3 uses the same default for the same reason.
    ap.add_argument("--search-ms", type=float, default=50.0,
                    help="centring searched +-this around the stamp")
    ap.add_argument("--win-ms", type=float, default=25.0)
    ap.add_argument("--view-ms", type=float, default=100.0)
    ap.add_argument("--lowpass", type=float, default=300.0)
    args = ap.parse_args()
    if args.anat is None:
        from ied_ds import ANAT
        args.anat = ANAT

    bench = Bench(args)
    plt.show()
    bench._save_centres()


if __name__ == "__main__":
    main()
