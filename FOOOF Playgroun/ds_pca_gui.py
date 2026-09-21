"""
ds_pca_gui.py -- the DS1/DS2 workbench: drag the window, click the dots.

WHAT YOU DRAG, AND WHY THERE ARE TWO OF THEM
============================================
Toothy's features are ONE SAMPLE. `ds_classification_gui.get_csd` builds
`lfp_interp[channels][:, idx]` -- a [contacts x events] array where each
column is a single instant -- so an event is described by its depth profile
at exactly one millisecond, and the only choice anybody makes is which
contacts. That is the whole feature set.

This opens up both axes. The rectangle on the CSD raster selects

  DEPTH   which contacts the CSD runs over   (Toothy's one choice)
  TIME    how many samples around the stamp go in  (Toothy: always one)

and the features become that whole block, flattened. Pull the box down to a
single column and you are running Toothy exactly; widen it and each event is
described by a shape in depth AND time, which is what tells a biphasic event
from a monophasic one of the same amplitude -- something a single sample
cannot see however well the stamp is aligned.

WHAT IS DRAWN IS NOT WHAT IS MEASURED, AND THAT IS DELIBERATE
=============================================================
The raster you drag on is the 5-100 Hz, mains-out CSD, because that is what
makes a dentate spike LOOK like one: broadband, the event is buried under the
slow field and you would be choosing a depth band by eye from a picture with
no event in it.

The FEATURES stay broadband, because that is what Toothy does -- its
`bp_dict['raw']` is the plain downsampled trace and the DS band is used only
to find peak times. The `60 Hz notch` box switches the features between
Toothy's choice and ours. So: the picture is filtered, the measurement is
whatever the checkbox says, and the two are never silently swapped.

One more asymmetry worth knowing. The raster shows the CSD of the whole
shank; the features are the CSD computed WITHIN the selected contacts, so
the top and bottom rows of the box get Vaknin-extended at the box edge
rather than reading their real neighbours. That is Toothy's behaviour and it
is why the outermost row or two of a narrow box is not to be trusted.

CLICKING A DOT
==============
Click any point in the PCA scatter and the left two panels stop showing the
event-triggered average and show THAT event: its voltage traces, its own CSD
raster. This is the check that matters before believing a cluster -- a class
whose members all look like the class average is a type; a class whose
members look like nothing in particular is a line drawn through a cloud.
"Show average" puts it back.

WHAT IS CHEAP AND WHAT IS NOT
=============================
Reading is minutes and happens once, cached to a .npz beside the bank. The
CSD is a tridiagonal matrix multiply and the PCA is two components over a few
dozen points, so everything the controls touch is milliseconds -- which is
why the box is live rather than behind a "recompute" button.

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
from matplotlib.widgets import Button, CheckButtons, RectangleSelector, Slider
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

CACHE_VERSION = 2          # bumped when the cached arrays change shape

# Assigned in a fixed order and never cycled: class 3 is always this orange,
# whether or not class 4 exists, so adding a cluster cannot repaint the ones
# already on screen.
CLASS_COLORS = ["#1a7f37", "#7b3fa0", "#b8620a", "#1f6feb", "#a3155f"]
GREY = "#8c9994"
INK = "#1b2220"


class Opts:
    """A plain attribute bag, so ds_pca's functions can be called unchanged."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


# --------------------------------------------------------------------------
# The expensive half, done once
# --------------------------------------------------------------------------
def cache_path(args):
    """One cache per (recording, bank, read settings).

    Keyed on what was READ, not on what the controls change -- the whole
    point is that dragging the box never invalidates it.
    """
    key = "|".join(str(x) for x in (
        CACHE_VERSION, os.path.abspath(args.folder), os.path.abspath(args.bank),
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
        return dict(rows=list(z["rows"]),
                    sur={k: z["sur_" + k] for k in ("raw", "notch", "band")},
                    nums=[int(n) for n in z["nums"]],
                    bad=dict(z["bad"].item()),
                    session_label=str(z["session_label"]),
                    mains_uv=float(z["mains_uv"]),
                    wideband_uv=float(z["wideband_uv"]))

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
        sur_raw=data["raw"]["sur"], sur_notch=data["notch"]["sur"],
        sur_band=data["band"]["sur"],
        nums=np.array(nums), bad=np.array(bad, dtype=object),
        session_label=label, mains_uv=data["mains_uv"],
        wideband_uv=data["wideband_uv"])
    print("cached to " + os.path.basename(path))
    return dict(rows=rows,
                sur={k: data[k]["sur"] for k in ("raw", "notch", "band")},
                nums=nums, bad=bad, session_label=label,
                mains_uv=data["mains_uv"], wideband_uv=data["wideband_uv"])


# --------------------------------------------------------------------------
# The cheap half, done on every drag
# --------------------------------------------------------------------------
def stack_csd(sur, args):
    """CSD of every event at once, as [nEvents x nCh x nSamp].

    One matrix multiply rather than one per event: the CSD is independent
    column by column, so every event's window can be laid side by side,
    differenced in a single call and folded back. With sixty events that is
    the difference between a drag that stutters and one that does not.
    """
    n_ev, n_ch, n_t = sur.shape
    flat = sur.transpose(1, 0, 2).reshape(n_ch, n_ev * n_t)
    csd = toothy_csd(flat, args.spacing, args)[1]        # filtered
    return csd.reshape(n_ch, n_ev, n_t).transpose(1, 0, 2)


def normalize_block(block):
    """pyfx.Normalize per EVENT, over the whole selected block.

    Toothy normalizes each event's single column across depth. With a time
    window there is more than one column, and the honest generalization is
    one min and one max for the whole patch -- normalizing each column
    separately would erase exactly the thing a time window was opened to
    see, which is how the profile changes from millisecond to millisecond.
    """
    out = np.asarray(block, dtype=np.float64).copy()
    for i in range(out.shape[0]):
        lo, hi = np.nanmin(out[i]), np.nanmax(out[i])
        out[i] = np.zeros_like(out[i]) if hi == lo else (out[i] - lo) / (hi - lo)
    return out


def recompute(state):
    """Screen, CSD, features, PCA, K-means -- for the current selection."""
    a = state["args"]
    sur = state["sur"]["notch" if state["notch"] else "raw"]
    sur_band = state["sur"]["band"]
    chans = state["chans"]

    bad = dict(state["bad0"])
    if state["screen"]:
        for _ in range(5):
            cbad, _b = ds_pca.csd_screen(sur, chans, a, a.csd_bad_x, known=bad)
            cbad = {k: v for k, v in cbad.items() if k not in bad}
            if not cbad:
                break
            bad = {**bad, **cbad}
            sur = np.array([braces.repair(s, chans, bad) for s in sur])
            sur_band = np.array([braces.repair(s, chans, bad)
                                 for s in sur_band])

    # The picture: whole-shank CSD of the band-limited trace.
    disp = stack_csd(sur_band, a)

    # The measurement: CSD computed WITHIN the chosen contacts, Toothy-style.
    sel, t0, t1 = state["sel"], state["t0"], state["t1"]
    feat_csd = stack_csd(sur[:, sel, :], a)[:, :, t0:t1]
    norm = normalize_block(feat_csd)
    X = norm.reshape(norm.shape[0], -1)

    pca = PCA(n_components=2)
    fit = pca.fit_transform(X)
    k = int(state["nclasses"])
    km = KMeans(n_clusters=k, n_init="auto", random_state=a.seed).fit(fit)

    # EVERY PICTURE COMES OFF THE SAME SIGNAL, and it is not the features.
    #
    # The class-average profile and the class-average rasters are both the
    # 5-100 Hz, mains-out CSD over the selected block. They used to disagree
    # -- the rasters band-limited, the profile broadband -- which meant the
    # "sink CSC30" in the profile legend was not necessarily the sink you
    # could see in the heatmap beside it. Two different answers to the same
    # question, a few centimetres apart.
    #
    # The features stay broadband, because that is Toothy's method and the
    # method is the thing being ported. So: the measurement is broadband,
    # everything drawn is band-limited, and the split is on purpose.
    prof = disp[:, sel, t0:t1].mean(axis=2)      # [nEvents x span]

    # Classes renumbered by sink depth, which generalizes Toothy's DS1/DS2
    # rule to any number: DS1 is the shallowest sink. Scored on `prof`, so
    # the naming agrees with what is on screen -- Toothy scores it on its
    # broadband features instead, and on this rig the two can disagree
    # because the mains moves the argmin. A label is a naming convention;
    # one you can check against the picture is the better convention.
    order = sorted(range(k), key=lambda c: (
        int(np.argmin(np.nanmean(prof[km.labels_ == c], axis=0)))
        if (km.labels_ == c).any() else 10 ** 6))
    remap = {c: i + 1 for i, c in enumerate(order)}
    types = np.array([remap[x] for x in km.labels_])

    return dict(disp=disp, feat=feat_csd, norm=norm, fit=fit, pca=pca,
                types=types, k=k, bad=bad, prof=prof,
                nums_sel=[state["nums"][i] for i in sel],
                n_features=X.shape[1])


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------
def draw(state, res):
    a = state["args"]
    nums, types = state["nums"], res["types"]
    tw = state["tw"]
    groups = [(c, np.where(types == c)[0]) for c in range(1, res["k"] + 1)]
    colors = {c: CLASS_COLORS[(c - 1) % len(CLASS_COLORS)] for c, _ in groups}
    pick = state["picked"]
    sel, t0, t1 = state["sel"], state["t0"], state["t1"]
    lo_n, hi_n = nums[sel[0]], nums[sel[-1]]

    for key in ("volt", "pca", "profile", "csd1", "csd2"):
        state["axes"][key].clear()

    # --- 1. voltage traces --------------------------------------------
    # Stacked per contact, the way an ephys trace is read. Band-limited to
    # match the raster beside it: on the broadband trace the slow field
    # dwarfs the spike and nothing about the depth is legible.
    ax = state["axes"]["volt"]
    vb = state["sur"]["band"]
    wave = vb[pick] if pick is not None else vb.mean(axis=0)
    # Gain in CONTACT UNITS: the biggest deflection on the shank spans this
    # many contacts. Traces overlapping is how a stacked ephys raster is
    # supposed to look -- the first version scaled the peak to under half a
    # contact and every channel drew as a flat line.
    gain = state["gain"]
    scale = float(np.percentile(np.abs(wave), 99.5)) or 1.0
    for i, n in enumerate(nums):
        inside = sel[0] <= i <= sel[-1]
        ax.plot(tw, -wave[i] * gain / scale + n,
                color=INK if inside else GREY, lw=.85 if inside else .5,
                alpha=1.0 if inside else .40, zorder=3 if inside else 2)
    ax.axvspan(tw[t0], tw[max(t0, t1 - 1)], color="#1f6feb", alpha=.12, lw=0)
    ax.axvline(0, color="#b03030", ls="--", lw=1.0, alpha=.8)
    ax.set_ylim(nums[-1] + gain + 1, nums[0] - gain - 1)
    ax.set_xlim(tw[0], tw[-1])
    ax.set_xlabel("ms from the refined stamp", fontsize=9)
    ax.set_ylabel("CSC number", fontsize=9)
    ax.set_title("voltage  %g–%g Hz, %s"
                 % (a.band[0], a.band[1],
                    "event #%d" % state["rows"][pick]["n"] if pick is not None
                    else "mean of %d" % len(state["rows"])),
                 fontsize=10)
    ax.tick_params(labelsize=8)

    # --- 2. the CSD raster, which is what you drag on ------------------
    # Its axes are never cleared: a RectangleSelector lives on the axes and
    # clearing them kills it. Only the image data changes.
    mat = res["disp"][pick] if pick is not None else res["disp"].mean(axis=0)
    lim = float(np.percentile(np.abs(mat), 99.5)) or 1.0
    state["raster_im"].set_data(mat)
    state["raster_im"].set_clim(-lim, lim)
    state["axes"]["csd"].set_title(
        "CSD  %g–%g Hz, 60 Hz out   —   drag a box: depth × time"
        % (a.band[0], a.band[1]), fontsize=10)

    # --- 3. PCA scatter, pickable -------------------------------------
    ax = state["axes"]["pca"]
    state["pick_artists"] = []
    for c, rr in groups:
        if rr.size == 0:
            continue
        art = ax.scatter(res["fit"][rr, 0], res["fit"][rr, 1], s=34,
                         c=colors[c], lw=.6, edgecolors="white",
                         label="DS%d  n=%d" % (c, rr.size), picker=6,
                         zorder=3)
        art._event_rows = rr
        state["pick_artists"].append(art)
    if pick is not None:
        ax.scatter([res["fit"][pick, 0]], [res["fit"][pick, 1]], s=190,
                   facecolors="none", edgecolors=INK, lw=1.8, zorder=4)
    ax.set_xlabel("PC1 (%.0f%%)" % (100 * res["pca"].explained_variance_ratio_[0]),
                  fontsize=9)
    ax.set_ylabel("PC2 (%.0f%%)" % (100 * res["pca"].explained_variance_ratio_[1]),
                  fontsize=9)
    ax.set_title("PCA of %d features — click a dot" % res["n_features"],
                 fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=.15, lw=.6)
    ax.tick_params(labelsize=8)

    # --- 4. class-average depth profile -------------------------------
    # The panel that says whether the box is in the right place. Two curves
    # differing in SHAPE -- sinks at different depths -- are two kinds of
    # event. Two of the same shape at different heights are one kind, loud
    # and quiet, which is a badly placed box sorting events by amplitude.
    ax = state["axes"]["profile"]
    ns = res["nums_sel"]
    for c, rr in groups:
        if rr.size == 0:
            continue
        mu = np.nanmean(res["prof"][rr], axis=0)
        sem = np.nanstd(res["prof"][rr], axis=0) / np.sqrt(rr.size)
        ax.fill_betweenx(ns, mu - sem, mu + sem, color=colors[c], alpha=.20,
                         lw=0)
        ax.plot(mu, ns, color=colors[c], lw=1.9,
                label="DS%d  sink CSC%s"
                      % (c, sink_channel(res["prof"].T, ns, rr)))
    ax.axvline(0, color="#444444", lw=.9, ls="--")
    ax.set_ylim(max(ns) + .5, min(ns) - .5)
    ax.set_xlabel(r"mean CSD over the window ($\mu V/mm^2$)", fontsize=9)
    ax.set_ylabel("CSC number", fontsize=9)
    ax.set_title("class-average depth profile ± SEM", fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=.15, lw=.6)
    ax.tick_params(labelsize=8)

    # --- 5 & 6. mean CSD per class, over the whole surround -----------
    mats = []
    for c, rr in groups[:2]:
        mats.append(None if rr.size == 0
                    else res["disp"][rr].mean(axis=0)[sel, :])
    lim2 = max([np.abs(m).max() for m in mats if m is not None] or [1.0])
    for j, (key, (c, rr)) in enumerate(zip(("csd1", "csd2"), groups[:2])):
        ax = state["axes"][key]
        if mats[j] is None:
            ax.text(.5, .5, "no DS%d events" % c, ha="center", va="center",
                    transform=ax.transAxes, color=GREY, fontsize=9)
            continue
        ax.imshow(mats[j], aspect="auto", origin="upper", cmap="jet",
                  vmin=-lim2, vmax=lim2,
                  extent=[tw[0], tw[-1], hi_n + .5, lo_n - .5])
        ax.axvspan(tw[t0], tw[max(t0, t1 - 1)], color="white", alpha=.0, lw=0)
        for x in (tw[t0], tw[max(t0, t1 - 1)]):
            ax.axvline(x, color="white", lw=1.2, alpha=.9)
        ax.set_xlabel("ms", fontsize=9)
        if j == 0:
            ax.set_ylabel("CSC number", fontsize=9)
        ax.set_title("mean CSD, DS%d (n=%d)" % (c, rr.size), fontsize=10,
                     color=colors[c])
        ax.tick_params(labelsize=8)

    repaired = sorted(set(res["bad"]) - set(state["bad0"]))
    state["fig"].suptitle(
        "%s   ·   %d events   ·   depth CSC%d–%d (%d)   ·   time %+.0f to "
        "%+.0f ms (%d sample%s)   ·   %d classes   ·   features %s   ·   %s"
        % (state["session_label"], types.size, lo_n, hi_n, len(sel),
           tw[t0], tw[max(t0, t1 - 1)], t1 - t0, "" if t1 - t0 == 1 else "s",
           res["k"], "60 Hz notched" if state["notch"] else "no notch (Toothy)",
           ("screen: CSC" + ",".join(str(n) for n in repaired))
           if repaired else "screen: nothing flagged"),
        fontsize=10.5, y=.988)
    state["fig"].canvas.draw_idle()


# --------------------------------------------------------------------------
def build(state):
    fig = plt.figure(figsize=(16.2, 9.6))
    state["fig"] = fig
    gs = gridspec.GridSpec(2, 3, figure=fig, hspace=.34, wspace=.26,
                           left=.055, right=.985, top=.905, bottom=.155)
    state["axes"] = {
        "volt": fig.add_subplot(gs[0, 0]),
        "csd": fig.add_subplot(gs[0, 1]),
        "pca": fig.add_subplot(gs[0, 2]),
        "profile": fig.add_subplot(gs[1, 0]),
        "csd1": fig.add_subplot(gs[1, 1]),
        "csd2": fig.add_subplot(gs[1, 2]),
    }

    nums, tw = state["nums"], state["tw"]
    ax = state["axes"]["csd"]
    state["raster_im"] = ax.imshow(
        np.zeros((len(nums), tw.size)), aspect="auto", origin="upper",
        cmap="jet", extent=[tw[0], tw[-1], nums[-1] + .5, nums[0] - .5])
    ax.axvline(0, color="white", ls="--", lw=1.0, alpha=.8)
    ax.set_xlabel("ms from the refined stamp", fontsize=9)
    ax.set_ylabel("CSC number", fontsize=9)
    ax.tick_params(labelsize=8)

    def on_select(eclick, erelease):
        """A dragged box -> a contact range and a sample range."""
        xs = sorted([eclick.xdata, erelease.xdata])
        ys = sorted([eclick.ydata, erelease.ydata])
        if None in xs or None in ys:
            return
        i0 = int(np.argmin(np.abs(tw - xs[0])))
        i1 = int(np.argmin(np.abs(tw - xs[1])))
        state["t0"], state["t1"] = i0, max(i0 + 1, i1 + 1)
        c0 = int(np.clip(round(ys[0]) - nums[0], 0, len(nums) - 1))
        c1 = int(np.clip(round(ys[1]) - nums[0], 0, len(nums) - 1))
        if c1 - c0 < 2:                      # a CSD needs three contacts
            c1 = min(len(nums) - 1, c0 + 2)
        state["sel"] = list(range(c0, c1 + 1))
        refresh()

    state["selector"] = RectangleSelector(
        ax, on_select, useblit=False, button=[1], interactive=True,
        minspanx=0, minspany=0, spancoords="data",
        props=dict(facecolor="none", edgecolor="white", lw=1.6, alpha=.9))

    # --- controls -----------------------------------------------------
    ax_k = fig.add_axes([.10, .055, .22, .022])
    s_k = Slider(ax_k, "classes", 2, 5, valinit=state["nclasses"], valstep=1)
    s_k.label.set_fontsize(9)
    s_k.valtext.set_fontsize(9)

    ax_chk = fig.add_axes([.40, .022, .13, .085])
    ax_chk.set_frame_on(False)
    chk = CheckButtons(ax_chk, ["60 Hz notch", "CSD screen"],
                       [state["notch"], state["screen"]])
    for t in chk.labels:
        t.set_fontsize(9)

    b_auto = Button(fig.add_axes([.565, .058, .085, .040]), "auto box")
    b_one = Button(fig.add_axes([.565, .014, .085, .040]), "1 sample")
    b_mean = Button(fig.add_axes([.665, .058, .085, .040]), "show average")
    b_save = Button(fig.add_axes([.665, .014, .085, .040]), "save fig + csv")
    for b in (b_auto, b_one, b_mean, b_save):
        b.label.set_fontsize(8.5)

    note = fig.text(.775, .058,
                    "mains %.0f µV rms of %.0f µV (%.0f%%)"
                    % (state["mains_uv"], state["wideband_uv"],
                       100 * state["mains_uv"] / max(state["wideband_uv"], 1e-9)),
                    fontsize=8.5, color=GREY, va="center")
    hint = fig.text(.775, .022,
                    "drag on the CSD raster to move the box", fontsize=8.5,
                    color=GREY, va="center")
    state["note"] = note

    def sync_box():
        """Put the selector's own rectangle where the state says it is."""
        sel, t0, t1 = state["sel"], state["t0"], state["t1"]
        try:
            state["selector"].extents = (tw[t0], tw[max(t0, t1 - 1)],
                                         nums[sel[0]] - .5, nums[sel[-1]] + .5)
        except Exception:
            pass                       # an older matplotlib; the box is cosmetic

    def refresh(_=None):
        state["nclasses"] = int(s_k.val)
        state["res"] = recompute(state)
        draw(state, state["res"])
        sync_box()

    def toggled(label):
        if label == "60 Hz notch":
            state["notch"] = not state["notch"]
        else:
            state["screen"] = not state["screen"]
        refresh()

    def auto_box(_):
        a = state["args"]
        sur = state["sur"]["notch" if state["notch"] else "raw"]
        sel = ds_pca.depth_band(sur, a, state["chans"], state["res"]["bad"])
        state["sel"] = sel
        state["t0"], state["t1"] = state["centre_i"], state["centre_i"] + 1
        refresh()

    def one_sample(_):
        state["t0"], state["t1"] = state["centre_i"], state["centre_i"] + 1
        refresh()

    def show_mean(_):
        state["picked"] = None
        draw(state, state["res"])
        sync_box()

    def on_pick(event):
        art = event.artist
        rows = getattr(art, "_event_rows", None)
        if rows is None or not len(event.ind):
            return
        state["picked"] = int(rows[event.ind[0]])
        draw(state, state["res"])
        sync_box()

    def save(_):
        res, sel = state["res"], state["sel"]
        tag = "CSC%d-%d_t%+d%+dms_%dcl_%s%s" % (
            state["nums"][sel[0]], state["nums"][sel[-1]],
            round(tw[state["t0"]]), round(tw[max(state["t0"], state["t1"] - 1)]),
            res["k"], "notch" if state["notch"] else "raw",
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

    s_k.on_changed(refresh)
    chk.on_clicked(toggled)
    b_auto.on_clicked(auto_box)
    b_one.on_clicked(one_sample)
    b_mean.on_clicked(show_mean)
    b_save.on_clicked(save)
    fig.canvas.mpl_connect("pick_event", on_pick)
    state["_widgets"] = (s_k, chk, b_auto, b_one, b_mean, b_save)
    state["refresh"] = refresh
    refresh()
    _ = hint
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
                    metavar=("LO", "HI"),
                    help="the band the raster and the refinement use")
    ap.add_argument("--window-ms", type=float, default=WINDOW_MS)
    ap.add_argument("--surround-ms", type=float, default=SURROUND_MS,
                    help="how far either side of the stamp is available to "
                         "the time box; widening it means re-reading")
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
    ap.add_argument("--csd-span", type=int, default=braces.DEPTH_BAND)
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

    got = load_everything(args)
    nums = got["nums"]
    n_t = got["sur"]["raw"].shape[2]
    a = Opts(**vars(args))

    # `chans` is only ever used to look up channel numbers, which is all
    # braces.repair and the screen ask of it.
    chans = [{"number": int(n)} for n in nums]
    state = {
        "args": a, "rows": got["rows"], "nums": nums, "chans": chans,
        "bad0": got["bad"], "sur": got["sur"],
        "session_label": got["session_label"], "mains_uv": got["mains_uv"],
        "wideband_uv": got["wideband_uv"],
        "notch": True, "screen": True, "nclasses": 2, "picked": None,
        "gain": 4.0,
        "tw": np.linspace(-args.surround_ms, args.surround_ms, n_t),
        "centre_i": n_t // 2,
    }
    # Open on Toothy's own feature window -- one sample at the stamp -- over
    # the depth band the data suggests, so the first thing on screen is the
    # faithful answer and every widening of it is a visible departure.
    state["t0"], state["t1"] = state["centre_i"], state["centre_i"] + 1
    state["sel"] = ds_pca.depth_band(got["sur"]["notch"], a, chans, got["bad"])

    fig = build(state)
    print("opening box: CSC%d-%d, 1 sample at the stamp  (drag to change)"
          % (nums[state["sel"][0]], nums[state["sel"][-1]]))
    if args.save:
        out = args.save if os.path.isabs(args.save) else \
            os.path.join(_HERE, args.save)
        fig.savefig(out, dpi=150)
        print("wrote " + out)
    else:
        plt.show()


if __name__ == "__main__":
    main()
