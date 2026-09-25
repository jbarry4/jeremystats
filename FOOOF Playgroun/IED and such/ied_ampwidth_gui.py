"""
ied_ampwidth_gui.py -- the IED amplitude/half-width workbench: click the
midline, read the numbers, see which ones are real.

WHAT YOU CLICK, AND WHY YOU CLICK IT
====================================
The pipeline anchors every event at the midpoint of its curated on/off pair.
That midpoint is a property of where the detector's threshold happened to be
crossed, not of the discharge -- on these events it lands a few milliseconds
off the sharp deflection, and every window measured from it is off by the same
few milliseconds. Amplitude tolerates that; half-width does not, because the
peak-search window slides off the peak and starts finding the shoulder.

So the midline is yours. Click anywhere on the stack and every channel is
re-measured against that time. `a` snaps it to the largest deflection across
the probe, `r` puts it back on the pipeline's midpoint. What you picked is
saved per event and restored when you come back.

WHAT THE COLOURS MEAN
=====================
On the stack, a channel drawn in GREY RED is on the rail: some sample in the
window is pinned at +-1999.94 uV. Its amplitude is a lower bound and its
half-width is inflated by the flat top, so by default it is excluded from the
"which channel is biggest" search -- otherwise every event in this session
answers "2000 uV, in the hilus", which is the amplifier talking, not the
brain. Untick `skip railed` to see what the unguarded argmax would have said.

The winning channel is drawn in BLUE and redrawn alone in the detail panel,
where you can see the baseline that was subtracted, the half-amplitude level,
and the two crossings the width is measured between. A crossing the search
never found is drawn as a DASHED line at the window edge and the half-width
is printed with a `>` -- that is an unresolved measurement, not a value, and
widening `cross +-ms` is what resolves it.

THE THREE BASELINES ARE A LIVE CONTROL ON PURPOSE
=================================================
Half-width is the width at half of a height, and the height is measured from
a baseline you chose. On these events the three defensible choices disagree
by up to twelvefold on the same trace (Evt010: 37 ms from the local field,
3 ms from the peak's own prominence), because one is measuring the whole slow
deflection and the other the spike riding on top of it. That is not a bug to
be settled by a default -- it is the actual question, so the radio button is
next to the number and every saved row records which was used.

RUN
===
  python ied_ampwidth_gui.py
  python ied_ampwidth_gui.py --category Solid
  python ied_ampwidth_gui.py --evt 40

KEYS
====
  left / right   previous / next event in the current filter
  a              snap midline to the largest deflection on the probe
  r              reset midline to the pipeline's on/off midpoint
  s              save this event's row
  e              export every saved event, per channel, to CSV
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

from ied_ampwidth import (BASELINES, CATEGORIES, DEFAULT_MAT, DEFAULT_ROOT,  # noqa: E402
                          DEFAULT_XLS, RAIL_UV, Recording, best_polarity,
                          load_window, measure_window, read_events, winner)

INK = "#1b2220"
GREY = "#a8b0ad"
RAIL_C = "#c0392b"
WIN_C = "#1f6feb"
MAXC = "#b8620a"
MINC = "#1a7f37"
HALO = "#ffffff"

PICKS = os.path.join(_HERE, "ied_ampwidth_picks.csv")
PERCH = os.path.join(_HERE, "ied_ampwidth_perchannel.csv")


# --------------------------------------------------------------------------
# Saved picks -- restored, never cleared
# --------------------------------------------------------------------------
def load_picks(path=PICKS):
    """Whatever was saved before, keyed by event.

    Read-modify-write, never truncate: the file is somebody's afternoon of
    clicking, and a GUI that starts by blanking it because it wants a clean
    slate has destroyed real work to make its own bookkeeping simpler.
    """
    if not os.path.exists(path):
        return {}
    try:
        tab = pd.read_csv(path)
    except Exception:
        return {}
    return {int(r["evt"]): dict(r) for _, r in tab.iterrows()}


def save_picks(picks, path=PICKS):
    if not picks:
        return
    tab = pd.DataFrame([picks[k] for k in sorted(picks)])
    tab.to_csv(path, index=False)


# --------------------------------------------------------------------------
class Workbench:
    def __init__(self, args):
        self.rec = Recording(args.mat, args.anat)
        self.events = read_events(args.xls, args.root)
        self.args = args

        self.disp_ms = args.display_ms
        self.peak_ms = args.peak_ms
        self.cross_ms = args.cross_ms
        self.baseline = args.baseline
        self.lowpass = args.lowpass
        self.notch = None
        self.skip_railed = True
        self.category = args.category
        self.gain = 1.0

        self.picks = load_picks()
        self.ctx = None
        self.rows = None
        self.anchor = None          # absolute sample of the midline
        self.half = int(round((self.disp_ms + 70.0) * 1e-3 * self.rec.sfx))

        self.order = self._filtered()
        self.pos = 0
        if args.evt is not None:
            hit = np.where(self.order == args.evt)[0]
            if hit.size:
                self.pos = int(hit[0])
            else:
                self.category = "All"
                self.order = self._filtered()
                hit = np.where(self.order == args.evt)[0]
                self.pos = int(hit[0]) if hit.size else 0

        self._build()
        self.load_event()

    # ---------------------------------------------------------------- data
    def _filtered(self):
        ev = self.events
        if self.category == "All":
            sel = ev
        elif self.category == "curated":
            sel = ev[ev["category"] != "uncurated"]
        else:
            # An event filed in two folders belongs to both lists, not to
            # whichever one sorted first.
            sel = ev[ev["filed_in"].fillna("").str.split("|").apply(
                lambda f: self.category in f)]
        got = sel["evt"].values.astype(int)
        return got if got.size else ev["evt"].values.astype(int)

    @property
    def evt(self):
        return int(self.order[self.pos % len(self.order)])

    def row_of(self, evt):
        return self.events[self.events["evt"] == evt].iloc[0]

    def midpoint(self, evt):
        e = self.row_of(evt)
        return int((int(e["on_samp"]) + int(e["off_samp"])) // 2)

    def load_event(self):
        """Read the window for the current event and measure it."""
        evt = self.evt
        saved = self.picks.get(evt)
        if saved and np.isfinite(saved.get("midline_samp", np.nan)):
            self.anchor = int(saved["midline_samp"])
        else:
            self.anchor = self.midpoint(evt)
        self.reload_window()

    def reload_window(self):
        """Re-read + re-filter. Only when the event or the filter changes."""
        self.ctx = load_window(self.rec, self.anchor, self.half,
                               lowpass=self.lowpass, notch=self.notch)
        self.remeasure()

    def remeasure(self):
        ai = int(self.anchor - self.ctx["s0"])
        # The midline can be dragged far enough that the cached window no
        # longer surrounds it with room for the flanks; re-read rather than
        # measure off the edge of the slab.
        if ai < self.half // 2 or ai > self.ctx["raw"].shape[0] - self.half // 2:
            self.ctx = load_window(self.rec, self.anchor, self.half,
                                   lowpass=self.lowpass, notch=self.notch)
            ai = int(self.anchor - self.ctx["s0"])
        self.ctx["anchor_i"] = ai
        self.rows = measure_window(self.ctx, self.rec, ai,
                                   peak_ms=self.peak_ms,
                                   cross_ms=self.cross_ms,
                                   baseline=self.baseline)
        self.win = winner(self.rows, exclude_clipped=self.skip_railed)

    # ---------------------------------------------------------------- build
    def _build(self):
        self.fig = plt.figure(figsize=(17.0, 10.0), facecolor="white")
        self.fig.canvas.manager.set_window_title("IED amplitude / half-width workbench")
        self.ax_stack = self.fig.add_axes([0.055, 0.26, 0.42, 0.68])
        self.ax_det = self.fig.add_axes([0.545, 0.60, 0.43, 0.34])
        self.ax_dep = self.fig.add_axes([0.545, 0.26, 0.43, 0.26])

        self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)

        b = lambda l, t, w, h: self.fig.add_axes([l, t, w, h])

        self.b_prev = Button(b(0.055, 0.175, 0.045, 0.040), "< prev")
        self.b_next = Button(b(0.105, 0.175, 0.045, 0.040), "next >")
        self.b_prev.on_clicked(lambda _: self.step(-1))
        self.b_next.on_clicked(lambda _: self.step(+1))

        self.t_evt = TextBox(b(0.196, 0.175, 0.050, 0.040), "evt ", initial="")
        self.t_evt.on_submit(self.on_evt_box)

        self.b_snap = Button(b(0.262, 0.175, 0.052, 0.040), "snap (a)")
        self.b_reset = Button(b(0.318, 0.175, 0.052, 0.040), "reset (r)")
        self.b_snap.on_clicked(lambda _: self.snap())
        self.b_reset.on_clicked(lambda _: self.reset_mid())

        self.b_save = Button(b(0.380, 0.175, 0.045, 0.040), "save (s)")
        self.b_exp = Button(b(0.430, 0.175, 0.055, 0.040), "export (e)")
        self.b_save.on_clicked(lambda _: self.save_row())
        self.b_exp.on_clicked(lambda _: self.export())

        cats = ("Solid", "Sputter", "Flag", "Garbage", "curated", "All")
        self.r_cat = RadioButtons(b(0.055, 0.025, 0.085, 0.135), cats,
                                  active=cats.index(self.category)
                                  if self.category in cats else 5)
        self.r_cat.on_clicked(self.on_cat)
        self.fig.text(0.055, 0.166, "event set", fontsize=8, color=INK)

        self.r_base = RadioButtons(b(0.158, 0.045, 0.085, 0.100), BASELINES,
                                   active=BASELINES.index(self.baseline))
        self.r_base.on_clicked(self.on_base)
        self.fig.text(0.158, 0.150, "baseline for half-amplitude",
                      fontsize=8, color=INK)

        self.c_opt = CheckButtons(b(0.262, 0.045, 0.105, 0.100),
                                  ["skip railed", "300 Hz lowpass", "60 Hz notch"],
                                  [True, bool(self.lowpass), False])
        self.c_opt.on_clicked(self.on_opt)
        self.fig.text(0.262, 0.150, "measurement", fontsize=8, color=INK)

        self.s_peak = Slider(b(0.442, 0.128, 0.110, 0.020), "peak ±ms",
                             1.0, 40.0, valinit=self.peak_ms, valfmt="%.0f")
        self.s_cross = Slider(b(0.442, 0.095, 0.110, 0.020), "cross ±ms",
                              5.0, 120.0, valinit=self.cross_ms, valfmt="%.0f")
        self.s_disp = Slider(b(0.442, 0.062, 0.110, 0.020), "view ±ms",
                             10.0, 150.0, valinit=self.disp_ms, valfmt="%.0f")
        self.s_gain = Slider(b(0.442, 0.029, 0.110, 0.020), "gain",
                             0.2, 6.0, valinit=self.gain, valfmt="%.1f")
        self.s_peak.on_changed(self.on_peak)
        self.s_cross.on_changed(self.on_cross)
        self.s_disp.on_changed(self.on_disp)
        self.s_gain.on_changed(self.on_gain)

        self.txt = self.fig.text(0.60, 0.160, "", fontsize=9, color=INK,
                                 va="top", family="monospace")

    # ------------------------------------------------------------ callbacks
    def on_click(self, ev):
        if ev.inaxes is not self.ax_stack or ev.xdata is None:
            return
        # Don't move the midline while the pan/zoom tool owns the drag. The
        # toolbar is absent under non-interactive backends, so ask for it
        # rather than assuming it is there.
        tb = getattr(self.fig.canvas.manager, "toolbar", None)
        if tb is not None and getattr(tb, "mode", ""):
            return
        self.anchor = int(round(self.anchor + ev.xdata * 1e-3 * self.rec.sfx))
        self.remeasure()
        self.draw()

    def on_key(self, ev):
        if ev.key == "right":
            self.step(+1)
        elif ev.key == "left":
            self.step(-1)
        elif ev.key == "a":
            self.snap()
        elif ev.key == "r":
            self.reset_mid()
        elif ev.key == "s":
            self.save_row()
        elif ev.key == "e":
            self.export()

    def step(self, d):
        self.stash()
        self.pos = (self.pos + d) % len(self.order)
        self.load_event()
        self.draw()

    def on_evt_box(self, text):
        try:
            n = int(str(text).strip())
        except ValueError:
            return
        hit = np.where(self.order == n)[0]
        if not hit.size:
            self.category = "All"
            self.order = self._filtered()
            hit = np.where(self.order == n)[0]
        if hit.size:
            self.stash()
            self.pos = int(hit[0])
            self.load_event()
            self.draw()

    def on_cat(self, label):
        self.stash()
        self.category = label
        keep = self.evt
        self.order = self._filtered()
        hit = np.where(self.order == keep)[0]
        self.pos = int(hit[0]) if hit.size else 0
        self.load_event()
        self.draw()

    def on_base(self, label):
        self.baseline = label
        self.remeasure()
        self.draw()

    def on_opt(self, label):
        st = dict(zip(["skip railed", "300 Hz lowpass", "60 Hz notch"],
                      self.c_opt.get_status()))
        self.skip_railed = st["skip railed"]
        self.lowpass = 300.0 if st["300 Hz lowpass"] else None
        self.notch = 60.0 if st["60 Hz notch"] else None
        if label == "skip railed":
            self.remeasure()
        else:
            self.reload_window()
        self.draw()

    def on_peak(self, v):
        self.peak_ms = float(v)
        self.remeasure()
        self.draw()

    def on_cross(self, v):
        self.cross_ms = float(v)
        self.remeasure()
        self.draw()

    def on_gain(self, v):
        self.gain = max(float(v), 0.05)
        self.draw()

    def on_disp(self, v):
        self.disp_ms = float(v)
        need = int(round((self.disp_ms + 70.0) * 1e-3 * self.rec.sfx))
        if need > self.half:
            self.half = need
            self.reload_window()
        self.draw()

    def snap(self):
        """Move the midline to the biggest thing on the probe near it.

        Largest |trace - channel median| across every channel inside the
        current peak window. Railed channels are left out when `skip railed`
        is on, for the same reason they are left out of the winner: a plateau
        has no time, so snapping to one puts the midline at an arbitrary point
        along a flat top.
        """
        ctx, ai = self.ctx, self.ctx["anchor_i"]
        pw = int(round(self.peak_ms * 1e-3 * self.rec.sfx))
        lo, hi = max(0, ai - pw), min(ctx["filt"].shape[0], ai + pw + 1)
        seg = ctx["filt"][lo:hi, :]
        use = ~ctx["rail"] if self.skip_railed else np.ones(self.rec.n_ch, bool)
        if not use.any():
            use = np.ones(self.rec.n_ch, bool)
        dev = np.abs(seg[:, use] - np.median(ctx["filt"][:, use], axis=0))
        self.anchor = int(self.ctx["s0"] + lo + np.argmax(dev.max(axis=1)))
        self.remeasure()
        self.draw()

    def reset_mid(self):
        self.anchor = self.midpoint(self.evt)
        self.remeasure()
        self.draw()

    # --------------------------------------------------------------- saving
    def _summary(self):
        evt = self.evt
        e = self.row_of(evt)
        w = self.win
        pol = best_polarity(w) if w else "max"
        out = {
            "evt": evt,
            "category": e["category"],
            "filed_in": e["filed_in"],
            "on_samp": int(e["on_samp"]),
            "off_samp": int(e["off_samp"]),
            "midline_samp": int(self.anchor),
            "midline_shift_ms": (self.anchor - self.midpoint(evt)) / self.rec.sfx * 1e3,
            "sfx": self.rec.sfx,
            "baseline": self.baseline,
            "peak_win_ms": self.peak_ms,
            "cross_win_ms": self.cross_ms,
            "lowpass_hz": self.lowpass or 0,
            "notch_hz": self.notch or 0,
            "skip_railed": self.skip_railed,
            "n_railed_rows": int(sum(r["any_rail"] for r in self.rows)),
            "saved_utc": dt.datetime.utcnow().isoformat(timespec="seconds"),
        }
        if w:
            out.update({"best_row": w["row"], "best_csc": w["csc"],
                        "best_region": w["region"], "best_polarity": pol,
                        "best_railed": w["any_rail"]})
            for p in ("max", "min"):
                m = w[p]
                out["best_%s_amp_uV" % p] = m["amp_uV"] if m else np.nan
                out["best_%s_hw_ms" % p] = m["hw_ms"] if m else np.nan
                out["best_%s_unresolved" % p] = m["unresolved"] if m else True
                out["best_%s_clipped_samples" % p] = m["clipped_samples"] if m else 0
                out["best_%s_status" % p] = m["status"] if m else "no_window"
        return out

    def stash(self):
        """Keep the midline the moment you leave the event, saved or not."""
        if self.rows is None:
            return
        evt = self.evt
        if evt in self.picks or self.anchor != self.midpoint(evt):
            self.picks[evt] = self._summary()

    def save_row(self):
        self.picks[self.evt] = self._summary()
        save_picks(self.picks)
        self.draw(note="saved Evt%03d -> %s" % (self.evt, os.path.basename(PICKS)))

    def export(self):
        """Every saved event, every channel. The per-channel table is the
        scientific product; the summary is the index into it."""
        self.stash()
        save_picks(self.picks)
        out = []
        keep = (self.anchor, self.pos)
        # Export every event that was saved, not just the ones the current
        # filter happens to show. Keying the loop off `self.order` meant that
        # switching to Solid before exporting quietly dropped every Sputter
        # event already measured -- the file looked complete and was short.
        for evt in sorted(self.picks):
            self.anchor = int(self.picks[evt]["midline_samp"])
            self.reload_window()
            e = self.row_of(evt)
            for r in self.rows:
                rec = {"evt": evt, "category": e["category"],
                       "row": r["row"], "csc": r["csc"], "region": r["region"],
                       "railed": r["any_rail"],
                       "midline_samp": self.anchor,
                       "baseline": self.baseline,
                       "peak_win_ms": self.peak_ms, "cross_win_ms": self.cross_ms,
                       "lowpass_hz": self.lowpass or 0, "notch_hz": self.notch or 0}
                for p in ("max", "min"):
                    m = r[p]
                    rec["%s_amp_uV" % p] = m["amp_uV"] if m else np.nan
                    rec["%s_hw_ms" % p] = m["hw_ms"] if m else np.nan
                    rec["%s_peak_ms" % p] = m["peak_ms"] if m else np.nan
                    rec["%s_baseline_uV" % p] = m["baseline_uV"] if m else np.nan
                    rec["%s_unresolved" % p] = m["unresolved"] if m else True
                    rec["%s_clipped_samples" % p] = m["clipped_samples"] if m else 0
                    rec["%s_status" % p] = m["status"] if m else "no_window"
                out.append(rec)
        self.anchor, self.pos = keep
        self.load_event()
        if out:
            pd.DataFrame(out).to_csv(PERCH, index=False)
        self.draw(note="exported %d events x %d ch -> %s"
                       % (len(self.picks), self.rec.n_ch, os.path.basename(PERCH)))

    # -------------------------------------------------------------- drawing
    def draw(self, note=""):
        self._stack()
        self._detail()
        self._depth()
        self._text(note)
        self.fig.canvas.draw_idle()

    def _tms(self, n, ai):
        return (np.arange(n) - ai) / self.rec.sfx * 1e3

    def _stack(self):
        ax = self.ax_stack
        ax.clear()
        ctx, ai = self.ctx, self.ctx["anchor_i"]
        y = ctx["filt"]
        t = self._tms(y.shape[0], ai)
        m = np.abs(t) <= self.disp_ms
        t, y = t[m], y[m, :]

        # Row spacing off the TYPICAL channel, not the loudest one. A global
        # percentile over all 32 rows is set by the railed hilar channels at
        # ~2000 uV, which makes the step so large that every other row draws
        # as a flat line and the stack shows nothing. Taking the median of the
        # per-channel spreads keeps the ordinary rows legible and lets the big
        # ones overlap their neighbours, which is what a stack plot is for.
        per = np.percentile(np.abs(y - np.median(y, axis=0)), 99.0, axis=0)
        step = max(2.0 * float(np.median(per)) / self.gain, 1e-6)
        wrow = self.win["row"] if self.win else -1

        for k in range(y.shape[1]):
            railed = bool(ctx["rail"][k])
            col = WIN_C if k == wrow else (RAIL_C if railed else INK)
            lw = 1.5 if k == wrow else (0.8 if railed else 0.7)
            al = 1.0 if (k == wrow or not railed) else 0.55
            ax.plot(t, y[:, k] - k * step, lw=lw, color=col, alpha=al,
                    zorder=5 if k == wrow else 2)

        ax.axvline(0.0, color=RAIL_C, lw=1.4, zorder=6)
        ax.axvspan(-self.peak_ms, self.peak_ms, color=RAIL_C, alpha=0.07, zorder=0)

        ticks, labs = [], []
        for k in range(0, y.shape[1], 2):
            ticks.append(-k * step)
            labs.append(self.rec.label(k))
        ax.set_yticks(ticks)
        ax.set_yticklabels(labs, fontsize=6.5)
        for lab, k in zip(ax.get_yticklabels(), range(0, y.shape[1], 2)):
            if ctx["rail"][k]:
                lab.set_color(RAIL_C)
            if k == wrow:
                lab.set_color(WIN_C)
        ax.set_ylim(-(y.shape[1] - 0.2) * step, step)
        ax.set_xlim(-self.disp_ms, self.disp_ms)
        ax.set_xlabel("ms from midline   (click anywhere to move it)", fontsize=9)
        e = self.row_of(self.evt)
        dur = (int(e["off_samp"]) - int(e["on_samp"])) / self.rec.sfx * 1e3
        ax.set_title("Evt%03d  [%s]   on/off dur %.1f ms   shift %+.2f ms   "
                     "%d/%d rows railed"
                     % (self.evt, e["filed_in"] or "uncurated", dur,
                        (self.anchor - self.midpoint(self.evt)) / self.rec.sfx * 1e3,
                        int(ctx["rail"].sum()), self.rec.n_ch),
                     fontsize=10)

    def _detail(self):
        ax = self.ax_det
        ax.clear()
        w = self.win
        if w is None:
            ax.text(0.5, 0.5, "no channel measured", ha="center")
            return
        ctx, ai = self.ctx, self.ctx["anchor_i"]
        y = ctx["filt"][:, w["row"]]
        raw = ctx["raw"][:, w["row"]]
        t = self._tms(len(y), ai)
        m = np.abs(t) <= self.disp_ms

        ax.plot(t[m], raw[m], lw=0.6, color=GREY, zorder=1, label="raw")
        ax.plot(t[m], y[m], lw=1.4, color=INK, zorder=3, label="measured")
        ax.axvline(0.0, color=RAIL_C, lw=1.2, zorder=2)

        if np.abs(raw[m]).max() >= RAIL_UV:
            for s in (+1, -1):
                ax.axhline(s * RAIL_UV, color=RAIL_C, ls=":", lw=1.2)
            ax.text(0.99, 0.02, "RAIL", transform=ax.transAxes, ha="right",
                    color=RAIL_C, fontsize=9, fontweight="bold")

        for pol, col in (("max", MAXC), ("min", MINC)):
            mm = w[pol]
            if not mm or mm["status"] != "ok":
                continue
            ax.axhline(mm["baseline_uV"], color=col, ls="--", lw=0.8, alpha=0.6)
            ax.axhline(mm["half_level_uV"], color=col, ls="-", lw=0.9, alpha=0.8)
            ax.plot([mm["peak_ms"]], [mm["signed_peak_uV"]], "o", ms=6,
                    color=col, mec="white", mew=1.0, zorder=6)
            for edge, xms in ((mm["edge_left"], mm["left_ms"]),
                              (mm["edge_right"], mm["right_ms"])):
                ax.axvline(xms, color=col, lw=1.6,
                           ls=":" if edge else "-", alpha=0.9)
            ax.annotate("", xy=(mm["left_ms"], mm["half_level_uV"]),
                        xytext=(mm["right_ms"], mm["half_level_uV"]),
                        arrowprops=dict(arrowstyle="<->", color=col, lw=1.2))

        ax.set_xlim(-self.disp_ms, self.disp_ms)
        ax.set_xlabel("ms from midline", fontsize=9)
        ax.set_ylabel("µV", fontsize=9)
        ax.set_title("%s%s   baseline: %s"
                     % (w["label"], "   [RAILED]" if w["any_rail"] else "",
                        self.baseline), fontsize=10,
                     color=RAIL_C if w["any_rail"] else INK)
        ax.legend(fontsize=7, loc="upper left", framealpha=0.85)

    def _depth(self):
        ax = self.ax_dep
        ax.clear()
        rows = self.rows
        k = np.arange(len(rows))

        def col(pol):
            # A channel with no deflection of this polarity leaves a gap in
            # the profile rather than plotting its negative "amplitude".
            return np.array([
                r[pol]["amp_uV"] if (r[pol] and r[pol]["status"] == "ok")
                else np.nan for r in rows])

        amax, amin = col("max"), col("min")
        rail = np.array([r["any_rail"] for r in rows])

        ax.plot(amax, k, "-o", ms=3, lw=1.1, color=MAXC, label="max (positive)")
        ax.plot(amin, k, "-o", ms=3, lw=1.1, color=MINC, label="min (negative)")
        if rail.any():
            ax.plot(np.where(rail, np.fmax(amax, amin), np.nan), k, "x",
                    ms=8, mew=1.6, color=RAIL_C, label="railed")
        if self.win:
            ax.axhline(self.win["row"], color=WIN_C, lw=1.2, alpha=0.7)

        ax.invert_yaxis()
        ax.set_xlabel("amplitude from baseline (µV)", fontsize=9)
        ax.set_ylabel("probe row", fontsize=9)
        ax.set_yticks(range(0, len(rows), 4))
        ax.set_yticklabels([self.rec.label(i) for i in range(0, len(rows), 4)],
                           fontsize=6.5)
        ax.legend(fontsize=7, loc="lower right", framealpha=0.85)
        ax.set_title("depth profile", fontsize=10)

    def _text(self, note=""):
        w = self.win
        L = []
        if w:
            for pol, name in (("max", "max (positive)"), ("min", "min (negative)")):
                m = w[pol]
                if not m:
                    L.append("%-16s  --" % name)
                    continue
                if m["status"] != "ok":
                    L.append("%-16s no deflection of this sign above baseline"
                             % name)
                    continue
                hw = ("%s%.2f ms" % (">" if m["unresolved"] else " ", m["hw_ms"]))
                L.append("%-16s amp %8.1f uV   HW %-10s peak %+6.2f ms%s"
                         % (name, m["amp_uV"], hw,
                            m["peak_ms"],
                            "   CLIPPED %d" % m["clipped_samples"]
                            if m["clipped_samples"] else ""))
            L.append("")
            L.append("channel  %s%s" % (w["label"],
                                        "   (RAILED - amplitude is a lower bound)"
                                        if w["any_rail"] else ""))
        nr = sum(r["any_rail"] for r in self.rows)
        L.append("railed   %d of %d rows%s"
                 % (nr, len(self.rows),
                    "   (excluded from the winner)" if self.skip_railed and nr else ""))
        L.append("saved    %d events   %s" % (len(self.picks), note))
        self.txt.set_text("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--mat", default=DEFAULT_MAT)
    ap.add_argument("--xls", default=DEFAULT_XLS)
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--anat", default=os.path.join(
        DEFAULT_ROOT, "m13s2_anatomical_detail.csv"))
    ap.add_argument("--category", default="Solid",
                    help="Solid | Sputter | Flag | Garbage | curated | All")
    ap.add_argument("--evt", type=int, default=None)
    ap.add_argument("--display-ms", type=float, default=60.0)
    ap.add_argument("--peak-ms", type=float, default=10.0,
                    help="extremum searched within +-this of the midline")
    ap.add_argument("--cross-ms", type=float, default=50.0,
                    help="half-amplitude crossings hunted within +-this")
    ap.add_argument("--baseline", default="local", choices=list(BASELINES))
    ap.add_argument("--lowpass", type=float, default=300.0)
    args = ap.parse_args()

    wb = Workbench(args)
    wb.draw()
    plt.show()
    wb.stash()
    save_picks(wb.picks)
    wb.rec.close()


if __name__ == "__main__":
    main()
