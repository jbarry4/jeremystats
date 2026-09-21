"""
ds_pca_gui.py -- the DS1/DS2 workbench: slide the depth band, watch it move.

WHY THIS EXISTS
===============
The one judgement `ds_pca.py` cannot make for you is WHICH CONTACTS the CSD
runs over. Toothy has a person draw that box on screen and it is not a
detail: the features ARE those contacts, so the window decides the answer.
The command-line version picks a band from the event-triggered CSD and prints
it, which is a guess you have to accept or override blind.

Here you drag it. Everything downstream -- the CSD, the PCA, the clustering,
the class-average profiles -- recomputes as the slider moves, because the
expensive part happened once before the window opened.

WHAT IS CHEAP AND WHAT IS NOT
=============================
Reading the recording is minutes: sixty-odd windows on sixty-four contacts,
decimated and filtered. That happens ONCE, at startup, and is cached to a
.npz beside the bank -- the second run opens instantly.

Everything the controls touch is milliseconds: the CSD is a tridiagonal
matrix times a [contacts x events] array, the PCA is two components over a
few dozen points. So the sliders are live rather than a "recompute" button.

The cache holds the plain AND the mains-notched copy of every window, which
is why the notch is a checkbox and not a restart.

THE CONTROLS
============
  band centre / width   which contacts the CSD runs over. This is the knob
                        that matters. Watch the class-average profiles: a
                        window centred on the hilar dipole gives two curves
                        that differ in SHAPE; one centred off it gives two
                        curves that differ only in size, which is the PCA
                        sorting events by amplitude and calling it a type.
  classes               how many clusters K-means is asked for. Two is
                        Toothy's default and the DS1/DS2 question; more is
                        worth a look when the scatter is plainly not two
                        blobs.
  60 Hz notch           on is ours, off is Toothy's.
  CSD screen            interpolate over contacts whose baseline CSD towers
                        over the probe median. Off is faithful to Toothy,
                        which has no such screen -- and on this rig that
                        lets five bad contacts decide the classification.
  save                  writes the figure and the table for the CURRENT
                        settings, named by the band, so a sweep leaves a
                        trail rather than one overwritten file.

NAMING. With two classes the shallower sink is DS1, which is Toothy's rule.
With more, classes are numbered by sink depth the same way: DS1 shallowest.
The sink contact of each class is in the legend, so if the anatomy says the
numbering is upside down you can see it rather than infer it.

Run:
  python ds_pca_gui.py
  python ds_pca_gui.py --folder "D:/PTEN/.../2023-10-05_14-09-57" --bank event-bank-M1ptens8oct4-v4.csv
  python ds_pca_gui.py --refresh          (ignore the cache and re-read)
"""

import argparse
import csv as csvmod
import hashlib
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import gridspec
from matplotlib.widgets import Button, CheckButtons, Slider
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import ds_pca                                                    # noqa: E402
from ds_pca import (T_COND, T_DS_FREQ, T_F_ORDER, T_F_SIGMA, T_LFP_FS,
                    SURROUND_MS, WINDOW_MS, PAD_S, braces, csc, probes,
                    toothy_csd, sink_channel)                    # noqa: E402
from dentate_spike_aligner import (BANK, FOLDER, LINE_Q,         # noqa: E402
                                   parse_channels, read_bank)

# Assigned in a fixed order and never cycled: class 3 is always this orange,
# whether or not class 4 exists, so adding a cluster cannot repaint the ones
# already on screen.
CLASS_COLORS = ["#1a7f37", "#7b3fa0", "#b8620a", "#1f6feb", "#a3155f"]
GREY = "#8c9994"


class Opts:
    """A plain attribute bag, so ds_pca's functions can be called unchanged."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


# --------------------------------------------------------------------------
# The expensive half, done once
# --------------------------------------------------------------------------
def cache_path(args):
    """One cache per (recording, bank, read settings).

    Keyed on the things that change what was READ, not on the things the
    sliders change -- the whole point is that the sliders never invalidate it.
    """
    key = "|".join(str(x) for x in (
        os.path.abspath(args.folder), os.path.abspath(args.bank),
        args.label, args.n_events, args.lfp_fs, args.band, args.window_ms,
        args.surround_ms, args.refine, args.spacing, args.pad,
        args.no_invert, args.channels))
    stem = os.path.splitext(os.path.basename(args.bank))[0]
    return os.path.join(_HERE, "%s_cache_%s.npz"
                        % (stem, hashlib.sha1(key.encode()).hexdigest()[:10]))


def load_everything(args):
    """Stamps, refinement and windows -- from the cache if it is there."""
    path = cache_path(args)
    if os.path.exists(path) and not args.refresh:
        z = np.load(path, allow_pickle=True)
        print("cache: " + os.path.basename(path))
        return (list(z["rows"]), z["col_raw"], z["col_notch"],
                z["sur_raw"], z["sur_notch"], list(z["nums"]),
                dict(z["bad"].item()), str(z["session_label"]),
                float(z["mains_uv"]), float(z["wideband_uv"]))

    kept = read_bank(args.bank, label=args.label)
    if not kept:
        sys.exit("no %s events in %s" % (args.label or "any", args.bank))
    events = kept if args.n_events == 0 else kept[:max(1, args.n_events)]
    label = events[0]["session"] or os.path.basename(args.folder)
    print("%s: %d event(s)" % (os.path.basename(args.bank), len(events)))

    session = csc.open_session(args.folder, invert=not args.no_invert)
    if not session.get("ok"):
        sys.exit(session.get("error") or "could not open " + args.folder)
    chans = parse_channels(args.channels, session["channels"])
    print("%s  fs=%g Hz  CSC%d-%d"
          % (session["name"], session["fs"], chans[0]["number"],
             chans[-1]["number"]))

    spec = {"band": args.band, "line_hz": 60.0, "line_q": LINE_Q,
            "lfp_fs": args.lfp_fs}
    bad = braces.screen(session, chans, spec, [e["t"] for e in events])
    for num in sorted(bad):
        print("  interpolated over CSC%-3d %s" % (num, bad[num]))

    rows, data, _fs = ds_pca.refine_and_read(session, chans, events, args, bad)
    nums = [int(c["number"]) for c in chans]
    np.savez_compressed(
        path, rows=np.array(rows, dtype=object),
        col_raw=data["raw"]["col"], col_notch=data["notch"]["col"],
        sur_raw=data["raw"]["sur"], sur_notch=data["notch"]["sur"],
        nums=np.array(nums), bad=np.array(bad, dtype=object),
        session_label=label, mains_uv=data["mains_uv"],
        wideband_uv=data["wideband_uv"])
    print("cached to " + os.path.basename(path))
    return (rows, data["raw"]["col"], data["notch"]["col"],
            data["raw"]["sur"], data["notch"]["sur"], nums, bad, label,
            data["mains_uv"], data["wideband_uv"])


# --------------------------------------------------------------------------
# The cheap half, done on every slider move
# --------------------------------------------------------------------------
def recompute(state):
    """CSD -> PCA -> K-means -> class order, for the current settings."""
    a = state["args"]
    col = state["col_notch"] if state["notch"] else state["col_raw"]
    sur = state["sur_notch"] if state["notch"] else state["sur_raw"]
    nums_all, chans = state["nums"], state["chans"]

    bad = dict(state["bad0"])
    if state["screen"]:
        for _ in range(5):
            cbad, _b = ds_pca.csd_screen(sur, chans, a, a.csd_bad_x, known=bad)
            cbad = {k: v for k, v in cbad.items() if k not in bad}
            if not cbad:
                break
            bad = {**bad, **cbad}
            col = braces.repair(col, chans, bad)
            sur = np.array([braces.repair(s, chans, bad) for s in sur])

    lo = max(0, min(state["centre"] - state["span"] // 2,
                    len(nums_all) - state["span"]))
    sel = list(range(lo, lo + state["span"]))
    nums = [nums_all[i] for i in sel]

    _raw, filt, norm = toothy_csd(col[sel, :], a.spacing, a)
    pca = PCA(n_components=2)
    fit = pca.fit_transform(norm.T)
    k = int(state["nclasses"])
    km = KMeans(n_clusters=k, n_init="auto", random_state=a.seed).fit(fit)

    # Classes renumbered by sink depth, which generalizes Toothy's DS1/DS2
    # rule to any number of them: DS1 is the shallowest sink. Without this the
    # labels are whatever order K-means happened to seed in, and they change
    # from one slider move to the next for no reason anybody can see.
    order = sorted(range(k), key=lambda c: (
        int(np.argmin(np.nanmean(filt[:, km.labels_ == c], axis=1)))
        if (km.labels_ == c).any() else 10 ** 6))
    remap = {c: i + 1 for i, c in enumerate(order)}
    types = np.array([remap[x] for x in km.labels_])

    return dict(sel=sel, nums=nums, filt=filt, norm=norm, fit=fit, pca=pca,
                types=types, sur=sur[:, sel, :], bad=bad, k=k)


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------
def draw(state, res):
    a = state["args"]
    nums, types, filt = res["nums"], res["types"], res["filt"]
    sur, fit, pca = res["sur"], res["fit"], res["pca"]
    tw = np.linspace(-a.surround_ms, a.surround_ms, sur.shape[2])
    groups = [(c, np.where(types == c)[0]) for c in range(1, res["k"] + 1)]
    colors = {c: CLASS_COLORS[(c - 1) % len(CLASS_COLORS)]
              for c, _ in groups}

    for ax in state["axes"].values():
        ax.clear()

    # --- PCA scatter --------------------------------------------------
    ax = state["axes"]["pca"]
    for c, rr in groups:
        if rr.size:
            ax.scatter(fit[rr, 0], fit[rr, 1], s=30, c=colors[c], lw=.6,
                       edgecolors="white", label="DS%d  n=%d" % (c, rr.size))
    ax.set_xlabel("PC1 (%.0f%%)" % (100 * pca.explained_variance_ratio_[0]),
                  fontsize=9)
    ax.set_ylabel("PC2 (%.0f%%)" % (100 * pca.explained_variance_ratio_[1]),
                  fontsize=9)
    ax.set_title("PCA of the normalized CSD", fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=.15, lw=.6)
    ax.tick_params(labelsize=8)

    # --- the average profile comparison -------------------------------
    # The panel to read when deciding whether the band is right. Two classes
    # that differ in SHAPE -- a sink at different depths -- are two kinds of
    # event. Two curves of the same shape and different height are one kind
    # of event, loud and quiet, which is what a badly placed window gives.
    ax = state["axes"]["profile"]
    for c, rr in groups:
        if rr.size == 0:
            continue
        mu = np.nanmean(filt[:, rr], axis=1)
        sem = np.nanstd(filt[:, rr], axis=1) / np.sqrt(rr.size)
        ax.fill_betweenx(nums, mu - sem, mu + sem, color=colors[c],
                         alpha=.20, lw=0)
        ax.plot(mu, nums, color=colors[c], lw=1.9,
                label="DS%d  sink CSC%s" % (c, sink_channel(filt, nums, rr)))
    ax.axvline(0, color="#444444", lw=.9, ls="--")
    ax.invert_yaxis()
    ax.set_xlabel(r"mean CSD at the stamp ($\mu V/mm^2$)", fontsize=9)
    ax.set_ylabel("CSC number", fontsize=9)
    ax.set_title("class-average depth profile  ± SEM", fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=.15, lw=.6)
    ax.tick_params(labelsize=8)

    # --- mean waveform at each class's sink ---------------------------
    ax = state["axes"]["wave"]
    for c, rr in groups:
        if rr.size == 0:
            continue
        ch = sink_channel(filt, nums, rr)
        w = sur[rr][:, list(nums).index(ch), :]
        mu = w.mean(axis=0)
        sem = w.std(axis=0) / np.sqrt(rr.size)
        ax.fill_between(tw, mu - sem, mu + sem, color=colors[c], alpha=.18,
                        lw=0)
        ax.plot(tw, mu, color=colors[c], lw=1.7, label="DS%d at CSC%d" % (c, ch))
    ax.axvline(0, color="#111111", ls="--", lw=1.0)
    ax.set_xlabel("ms from the refined stamp", fontsize=9)
    ax.set_ylabel("LFP (µV)", fontsize=9)
    ax.set_title("mean waveform at each class's sink", fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=.15, lw=.6)
    ax.tick_params(labelsize=8)

    # --- mean CSD heatmaps, first two classes -------------------------
    mats = []
    for c, rr in groups[:2]:
        mats.append(None if rr.size == 0
                    else toothy_csd(sur[rr].mean(axis=0), a.spacing, a)[1])
    lim = max([np.abs(m).max() for m in mats if m is not None] or [1.0])
    for j, (key, (c, rr)) in enumerate(zip(("csd1", "csd2"), groups[:2])):
        ax = state["axes"][key]
        if mats[j] is None:
            ax.text(.5, .5, "no DS%d events" % c, ha="center", va="center",
                    transform=ax.transAxes, color=GREY, fontsize=9)
            continue
        ax.imshow(mats[j], aspect="auto", origin="upper", cmap="jet",
                  vmin=-lim, vmax=lim,
                  extent=[tw[0], tw[-1], nums[-1] + .5, nums[0] - .5])
        ax.axvline(0, color="white", ls="--", lw=1.0)
        ax.set_xlabel("ms", fontsize=9)
        if j == 0:
            ax.set_ylabel("CSC number", fontsize=9)
        ax.set_title("mean CSD, DS%d (n=%d)" % (c, rr.size), fontsize=10,
                     color=colors[c])
        ax.tick_params(labelsize=8)

    # --- the feature matrix -------------------------------------------
    ax = state["axes"]["feat"]
    order = np.concatenate([rr for _c, rr in groups if rr.size] or
                           [np.arange(types.size)]).astype(int)
    ax.imshow(res["norm"][:, order], aspect="auto", origin="upper",
              cmap="jet", vmin=0, vmax=1,
              extent=[0, order.size, nums[-1] + .5, nums[0] - .5])
    at = 0
    for _c, rr in groups[:-1]:
        at += rr.size
        if 0 < at < order.size:
            ax.axvline(at, color="white", lw=1.4)
    ax.set_xlabel("event, sorted by class", fontsize=9)
    ax.set_title("normalized CSD — the features", fontsize=10)
    ax.tick_params(labelsize=8, labelleft=False)

    repaired = sorted(set(res["bad"]) - set(state["bad0"]))
    state["fig"].suptitle(
        "%s   ·   %d events   ·   CSD over CSC%d–%d   ·   %d classes   ·   "
        "%s   ·   %s"
        % (state["session_label"], types.size, nums[0], nums[-1], res["k"],
           "60 Hz notched" if state["notch"] else "no notch (Toothy)",
           ("CSD screen: CSC" + ",".join(str(n) for n in repaired))
           if repaired else "CSD screen: nothing flagged"),
        fontsize=11.5, y=.985)
    state["fig"].canvas.draw_idle()


# --------------------------------------------------------------------------
def build(state):
    fig = plt.figure(figsize=(15.5, 9.4))
    state["fig"] = fig
    gs = gridspec.GridSpec(2, 3, figure=fig, hspace=.36, wspace=.26,
                           left=.06, right=.985, top=.90, bottom=.20)
    state["axes"] = {
        "pca": fig.add_subplot(gs[0, 0]),
        "profile": fig.add_subplot(gs[0, 1]),
        "wave": fig.add_subplot(gs[0, 2]),
        "csd1": fig.add_subplot(gs[1, 0]),
        "csd2": fig.add_subplot(gs[1, 1]),
        "feat": fig.add_subplot(gs[1, 2]),
    }

    n_ch = len(state["nums"])
    lo, hi = state["nums"][0], state["nums"][-1]

    # Left-inset far enough for the labels: a Slider writes its name OUTSIDE
    # its own axes, so an axes starting at .08 puts the text off the sheet.
    ax_c = fig.add_axes([.155, .105, .33, .022])
    ax_s = fig.add_axes([.155, .065, .33, .022])
    ax_k = fig.add_axes([.155, .025, .33, .022])
    s_centre = Slider(ax_c, "band centre (CSC)", lo, hi,
                      valinit=state["nums"][state["centre"]], valstep=1)
    s_span = Slider(ax_s, "band width (contacts)", 4, min(40, n_ch),
                    valinit=state["span"], valstep=1)
    s_k = Slider(ax_k, "classes", 2, 5, valinit=state["nclasses"], valstep=1)
    for s in (s_centre, s_span, s_k):
        s.label.set_fontsize(9)
        s.valtext.set_fontsize(9)

    ax_chk = fig.add_axes([.56, .025, .13, .105])
    ax_chk.set_frame_on(False)
    chk = CheckButtons(ax_chk, ["60 Hz notch", "CSD screen"],
                       [state["notch"], state["screen"]])
    for t in chk.labels:
        t.set_fontsize(9)

    ax_btn = fig.add_axes([.72, .055, .10, .045])
    btn = Button(ax_btn, "save figure + csv")
    btn.label.set_fontsize(9)

    note = fig.text(.84, .078,
                    "mains %.0f µV rms of %.0f µV (%.0f%%)"
                    % (state["mains_uv"], state["wideband_uv"],
                       100 * state["mains_uv"] / max(state["wideband_uv"], 1e-9)),
                    fontsize=8.5, color=GREY, va="center")
    state["note"] = note

    def refresh(_=None):
        state["centre"] = int(np.clip(int(s_centre.val) - lo, 0, n_ch - 1))
        state["span"] = int(s_span.val)
        state["nclasses"] = int(s_k.val)
        state["res"] = recompute(state)
        draw(state, state["res"])

    def toggled(label):
        if label == "60 Hz notch":
            state["notch"] = not state["notch"]
        else:
            state["screen"] = not state["screen"]
        refresh()

    def save(_):
        res = state["res"]
        tag = "CSC%d-%d_%dcl_%s%s" % (
            res["nums"][0], res["nums"][-1], res["k"],
            "notch" if state["notch"] else "raw",
            "_screen" if state["screen"] else "")
        png = os.path.join(_HERE, "ds_pca_%s.png" % tag)
        csvp = os.path.join(_HERE, "ds_pca_%s.csv" % tag)
        state["fig"].savefig(png, dpi=150)
        cols = ["n", "stamp_s", "refined_s", "offset_ms", "idx",
                "peak_uv_mm2", "pc1", "pc2", "type", "by"]
        with open(csvp, "w", newline="", encoding="utf-8") as fh:
            w = csvmod.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r, p, ty in zip(state["rows"], res["fit"], res["types"]):
                w.writerow({**r, "pc1": float(p[0]), "pc2": float(p[1]),
                            "type": int(ty)})
        note.set_text("wrote ds_pca_%s.{png,csv}" % tag)
        note.set_color("#1a7f37")
        state["fig"].canvas.draw_idle()

    s_centre.on_changed(refresh)
    s_span.on_changed(refresh)
    s_k.on_changed(refresh)
    chk.on_clicked(toggled)
    btn.on_clicked(save)
    state["_widgets"] = (s_centre, s_span, s_k, chk, btn)   # keep them alive
    refresh()
    return fig


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", default=FOLDER)
    ap.add_argument("--bank", default=BANK)
    ap.add_argument("--label", default="spike")
    ap.add_argument("-n", "--n-events", type=int, default=0)
    ap.add_argument("--refine", default="nearest",
                    choices=("nearest", "argmax"))
    ap.add_argument("--band", type=float, nargs=2, default=list(T_DS_FREQ),
                    metavar=("LO", "HI"))
    ap.add_argument("--window-ms", type=float, default=WINDOW_MS)
    ap.add_argument("--surround-ms", type=float, default=SURROUND_MS)
    ap.add_argument("--channels", default="")
    ap.add_argument("--spacing", type=float, default=probes.CONTACT_PITCH_UM)
    ap.add_argument("--lfp-fs", type=float, default=T_LFP_FS)
    ap.add_argument("--pad", type=float, default=PAD_S)
    ap.add_argument("--no-invert", action="store_true")
    ap.add_argument("--cond", type=float, default=T_COND)
    ap.add_argument("--f-order", type=int, default=T_F_ORDER)
    ap.add_argument("--f-sigma", type=float, default=T_F_SIGMA)
    ap.add_argument("--no-vaknin", action="store_true")
    ap.add_argument("--h-power", type=int, default=1, choices=(1, 2))
    ap.add_argument("--csd-bad-x", type=float, default=4.0)
    ap.add_argument("--csd-span", type=int, default=braces.DEPTH_BAND,
                    help="the band width the sliders start at")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--refresh", action="store_true",
                    help="ignore the cache and read the recording again")
    ap.add_argument("--save", default=None,
                    help="write the opening view here and exit, no window")
    args = ap.parse_args()
    args.band = (float(args.band[0]), float(args.band[1]))
    args.line = 0.0                       # the checkbox owns this, not argv
    args.bank = args.bank if os.path.isabs(args.bank) else \
        os.path.join(_HERE, args.bank)
    if not os.path.exists(args.bank):
        sys.exit("no such bank: " + args.bank)

    (rows, col_raw, col_notch, sur_raw, sur_notch, nums, bad, label,
     mains_uv, wideband_uv) = load_everything(args)

    # `chans` here is only ever used to look up channel numbers, which is all
    # braces.repair and the screen need of it.
    chans = [{"number": int(n)} for n in nums]
    a = Opts(**vars(args))
    state = {
        "args": a, "rows": rows, "nums": nums, "chans": chans, "bad0": bad,
        "col_raw": col_raw, "col_notch": col_notch,
        "sur_raw": sur_raw, "sur_notch": sur_notch,
        "session_label": label, "mains_uv": mains_uv,
        "wideband_uv": wideband_uv,
        "notch": True, "screen": True, "nclasses": 2,
        "span": int(args.csd_span), "centre": len(nums) // 2,
    }

    # Open on the band the data suggests rather than the middle of the shank,
    # so the first thing on screen is a real answer to argue with.
    probe_args = Opts(**{**vars(args), "csd_span": int(args.csd_span)})
    sel0 = ds_pca.depth_band(sur_notch, probe_args, chans, bad)
    state["centre"] = int(np.mean(sel0))

    fig = build(state)
    print("opening band: CSC%d-%d   (drag to move it)"
          % (state["res"]["nums"][0], state["res"]["nums"][-1]))
    if args.save:
        out = args.save if os.path.isabs(args.save) else \
            os.path.join(_HERE, args.save)
        fig.savefig(out, dpi=150)
        print("wrote " + out)
    else:
        plt.show()


if __name__ == "__main__":
    main()
