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
import json
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import gridspec, patheffects
from matplotlib.widgets import (Button, CheckButtons, RectangleSelector,
                                Slider, TextBox)
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
GUIDE = "#101010"          # depth guides: neutral, so no class owns them
MAX_GUIDES = 10

# A white stroke under every guide. They are drawn over a jet colormap that
# runs from dark blue to dark red, and no single ink reads over all of it.
_HALO = [patheffects.withStroke(linewidth=2.8, foreground="white")]


# --------------------------------------------------------------------------
# Depth guides -- laminar boundaries, named
# --------------------------------------------------------------------------
def guides_path(args):
    """Guides live beside the bank, not in the cache.

    The cache is keyed on read settings and is thrown away whenever those
    change; where the hilus is does not change because somebody widened a
    filter. Anatomy outlives a parameter sweep, so it gets its own file.
    """
    stem = os.path.splitext(os.path.basename(args.bank))[0]
    return os.path.join(_HERE, "%s_guides.json" % stem)


def load_guides(args):
    try:
        with open(guides_path(args), encoding="utf-8") as fh:
            got = json.load(fh)
        return [{"csc": int(g["csc"]), "label": str(g.get("label", ""))}
                for g in got][:MAX_GUIDES]
    except Exception:
        return []


def save_guides(state):
    try:
        with open(guides_path(state["args"]), "w", encoding="utf-8") as fh:
            json.dump(state["guides"], fh, indent=1)
    except Exception as err:
        print("could not save guides: %s" % err)


def draw_guides(state, ax, labels=True, side="left"):
    """One guide set, on any panel whose y axis is the contact number.

    Drawn on the individual-spike raster and on the class averages alike --
    a laminar boundary is a fact about the probe, not about which view is
    open, so it does not come and go with the toggle.
    """
    # Clipped, both the line and its label. A guide at CSC49 is a fact about
    # the probe whatever the box is set to, but a panel showing CSC26-36 has
    # no business growing to reach it -- and an unclipped label writes itself
    # over whatever sits below the axes, which on this figure is the
    # controls.
    arts = state.setdefault("guide_artists", [])
    for g in state.setdefault("guides", []):
        arts.append(ax.axhline(g["csc"], color=GUIDE, lw=1.1,
                               ls=(0, (6, 3)), alpha=.95, zorder=8,
                               clip_on=True, path_effects=_HALO))
        if labels and g["label"]:
            x = .012 if side == "left" else .988
            arts.append(ax.text(
                x, g["csc"] - .4, g["label"],
                transform=ax.get_yaxis_transform(),
                ha="left" if side == "left" else "right", va="bottom",
                fontsize=8, color=GUIDE, zorder=9, clip_on=True,
                path_effects=_HALO))


def forget_guide_artists(state):
    """Drop last draw's guides.

    The CSD raster's axes are never cleared -- a RectangleSelector lives on
    them -- so its guides have to be taken off by hand or they pile up one
    layer per redraw. The cleared panels have already destroyed theirs,
    which is why the removal is allowed to fail.
    """
    for art in state.get("guide_artists", []):
        try:
            art.remove()
        except Exception:
            pass
    state["guide_artists"] = []


def flip_path(args):
    """Whether DS1/DS2 were swapped by hand -- a per-session decision."""
    stem = os.path.splitext(os.path.basename(args.bank))[0]
    return os.path.join(_HERE, "%s_flip.json" % stem)


def load_flip(args):
    try:
        with open(flip_path(args), encoding="utf-8") as fh:
            return bool(json.load(fh).get("flip"))
    except Exception:
        return False


def save_flip(state):
    try:
        with open(flip_path(state["args"]), "w", encoding="utf-8") as fh:
            json.dump({"flip": bool(state.get("flip"))}, fh)
    except Exception as err:
        print("could not save the flip: %s" % err)


def bad_path(args):
    """Manually-marked bad contacts, beside the bank like the guides.

    Which wire is dead is a fact about the probe and the session, and it
    outlives every parameter sweep, so it is not kept in the cache.
    """
    stem = os.path.splitext(os.path.basename(args.bank))[0]
    return os.path.join(_HERE, "%s_bad.json" % stem)


def load_bad(args):
    try:
        with open(bad_path(args), encoding="utf-8") as fh:
            return {int(k): str(v) for k, v in json.load(fh).items()}
    except Exception:
        return {}


def save_bad(state):
    try:
        with open(bad_path(state["args"]), "w", encoding="utf-8") as fh:
            json.dump({str(k): v for k, v in state["manual_bad"].items()},
                      fh, indent=1)
    except Exception as err:
        print("could not save bad channels: %s" % err)


def toggle_bad(state, nums_text):
    """'59' or '59 61' -- mark contacts bad, or unmark ones already marked."""
    said = []
    for tok in str(nums_text).replace(",", " ").split():
        try:
            num = int(round(float(tok)))
        except ValueError:
            said.append("%r is not a contact number" % tok)
            continue
        if num not in state["nums"]:
            said.append("CSC%d is not in this recording" % num)
            continue
        if num in state["manual_bad"]:
            del state["manual_bad"][num]
            said.append("CSC%d back in" % num)
        else:
            state["manual_bad"][num] = "marked bad by hand"
            said.append("CSC%d out" % num)
    return ", ".join(said) or "type a contact number, e.g. 59"


def parse_guide(text, default_label=""):
    """'30 hilus' -> (30, 'hilus').  '30' -> (30, default).  else None."""
    parts = str(text).strip().split(None, 1)
    if not parts:
        return None
    try:
        csc = int(round(float(parts[0])))
    except ValueError:
        return None
    return csc, (parts[1].strip() if len(parts) > 1 else default_label)


def toggle_guide(state, csc, label="", tol=0.6):
    """Add a guide, or remove the one already at that depth.

    Same gesture both ways, because the alternative is a delete mode and a
    mode you can forget you are in is worse than one you cannot.
    """
    for g in list(state["guides"]):
        if abs(g["csc"] - csc) <= tol:
            state["guides"].remove(g)
            return "removed the guide at CSC%d" % g["csc"]
    if len(state["guides"]) >= MAX_GUIDES:
        return "%d guides is the limit — clear one first" % MAX_GUIDES
    state["guides"].append({"csc": int(csc), "label": label})
    state["guides"].sort(key=lambda g: g["csc"])
    return "guide at CSC%d%s" % (csc, (" — " + label) if label else "")


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

    # Three sources, all repaired the same way: the amplitude screen that ran
    # at read time, whatever was marked by hand, and the CSD screen below.
    #
    # Marking by hand does NOT change the refinement -- those stamps were
    # timed during the read, against the read-time bad list. One dead wire
    # among sixty-four moves a mean over depth by almost nothing, so this is
    # a real limitation rather than a serious one; `--bad 59` at the command
    # line puts it in before the read if it ever matters.
    bad = {**state["bad0"], **state["manual_bad"]}
    if state["manual_bad"]:
        sur = np.array([braces.repair(s, chans, bad) for s in sur])
        sur_band = np.array([braces.repair(s, chans, bad) for s in sur_band])
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
    if state.get("flip"):
        order = order[::-1]          # DS1 <-> DSk, by hand
    remap = {c: i + 1 for i, c in enumerate(order)}
    types = np.array([remap[x] for x in km.labels_])

    # WHAT THE RULE ACTUALLY LOOKED AT, kept so the summary panel can show
    # its working rather than asserting a verdict. `argmin` is one number off
    # a curve that often has three or four excursions -- the local minima are
    # counted here so the panel can say when the single number is thin.
    ns = [state["nums"][i] for i in sel]
    decide = []
    for c in range(1, k + 1):
        rr = np.where(types == c)[0]
        if rr.size == 0:
            decide.append(dict(c=c, n=0))
            continue
        mu = np.nanmean(prof[rr], axis=0)
        j = int(np.argmin(mu))
        lows = [i for i in range(1, len(mu) - 1)
                if mu[i] < mu[i - 1] and mu[i] < mu[i + 1] and mu[i] < 0]
        decide.append(dict(c=c, n=int(rr.size), row=j, csc=ns[j],
                           value=float(mu[j]),
                           lows=[ns[i] for i in lows], mu=mu))

    return dict(disp=disp, feat=feat_csd, norm=norm, fit=fit, pca=pca,
                types=types, k=k, bad=bad, prof=prof, decide=decide,
                nums_sel=ns, n_features=X.shape[1])


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

    forget_guide_artists(state)
    for key in ("volt", "pca", "profile", "csd1", "csd2", "why"):
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
    draw_guides(state, ax)
    ax.set_ylim(nums[-1] + gain + 1, nums[0] - gain - 1)
    ax.set_xlim(tw[0], tw[-1])
    ax.set_xlabel("ms from the refined stamp", fontsize=9)
    ax.set_ylabel("CSC number", fontsize=9)
    if pick is None:
        what = "mean of %d" % len(state["rows"])
    else:
        r = state["rows"][pick]
        what = ("spike #%d  ·  %.3f s  ·  DS%d"
                % (r["n"], r["refined_s"], types[pick]))
    ax.set_title("voltage  %g–%g Hz, 60 Hz out  —  %s"
                 % (a.band[0], a.band[1], what), fontsize=10)
    ax.tick_params(labelsize=8)
    if state.get("where") is not None:
        if pick is None:
            state["where"].set_text("showing the average")
            state["where"].set_color(GREY)
        else:
            state["where"].set_text("spike %d of %d   (DS%d)"
                                    % (pick + 1, len(state["rows"]),
                                       types[pick]))
            state["where"].set_color(colors.get(int(types[pick]), INK))

    # --- 2. the CSD raster, which is what you drag on ------------------
    # Its axes are never cleared: a RectangleSelector lives on the axes and
    # clearing them kills it. Only the image data changes.
    mat = res["disp"][pick] if pick is not None else res["disp"].mean(axis=0)
    lim = float(np.percentile(np.abs(mat), 99.5)) or 1.0
    state["raster_im"].set_data(mat)
    state["raster_im"].set_clim(-lim, lim)
    draw_guides(state, state["axes"]["csd"], side="right")
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
        # The point the rule actually used, marked. Without it the legend
        # asserts a sink and the curve beside it has three.
        j = int(np.argmin(mu))
        ax.plot([mu[j]], [ns[j]], "o", ms=8, color=colors[c], mec="white",
                mew=1.4, zorder=6)
    ax.axvline(0, color="#444444", lw=.9, ls="--")
    draw_guides(state, ax)
    ax.set_ylim(max(ns) + .5, min(ns) - .5)
    ax.set_xlabel(r"mean CSD over the window ($\mu V/mm^2$)", fontsize=9)
    ax.set_ylabel("CSC number", fontsize=9)
    ax.set_title("class-average depth profile ± SEM  (%g–%g Hz, 60 Hz out)"
                 % (a.band[0], a.band[1]), fontsize=10)
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
        draw_guides(state, ax, labels=(j == 0))
        # After the guides, not before: axhline expands the data limits, so
        # a guide outside the box would otherwise stretch these panels past
        # the contacts they are showing.
        ax.set_ylim(hi_n + .5, lo_n - .5)
        ax.set_xlim(tw[0], tw[-1])
        ax.set_xlabel("ms", fontsize=9)
        if j == 0:
            ax.set_ylabel("CSC number", fontsize=9)
        ax.set_title("mean CSD, DS%d (n=%d)  %g–%g Hz, 60 Hz out"
                     % (c, rr.size, a.band[0], a.band[1]), fontsize=10,
                     color=colors[c])
        ax.tick_params(labelsize=8)

    # --- the feature matrix, events sorted by class --------------------
    # Not decoration: this is the panel a bad contact shows up on as a solid
    # stripe running the width of the sheet, which is how the first version
    # of this analysis was caught classifying one wire.
    ax = state["axes"]["feat"]
    order = np.concatenate([rr for _c, rr in groups if rr.size]
                           or [np.arange(types.size)]).astype(int)
    ax.imshow(res["norm"].reshape(res["norm"].shape[0], -1).T[:, order],
              aspect="auto", origin="upper", cmap="jet", vmin=0, vmax=1)
    at = 0
    for _c, rr in groups[:-1]:
        at += rr.size
        if 0 < at < order.size:
            ax.axvline(at, color="white", lw=1.4)
    ax.set_xlabel("event, sorted by class", fontsize=9)
    ax.set_ylabel("feature (depth × time)", fontsize=9)
    ax.set_title("normalized CSD — the features", fontsize=10)
    ax.tick_params(labelsize=8)

    # --- 7. how the labels were decided -------------------------------
    # A panel whose whole job is to show its working. The rule is one argmin
    # per class and a comparison of two row numbers; stated in a legend it
    # reads as a fact about anatomy, which it is not.
    ax = state["axes"]["why"]
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    lines = [("HOW DS1/DS2 WAS DECIDED", INK, 9.5, "bold"),
             ("mean CSD profile per class over the", GREY, 8.0, "normal"),
             ("selected block; the sink is where it", GREY, 8.0, "normal"),
             ("is most negative.", GREY, 8.0, "normal"),
             ("", GREY, 3, "normal")]
    for d in res["decide"]:
        if not d.get("n"):
            lines.append(("DS%d   no events" % d["c"], GREY, 8.4, "normal"))
            continue
        lines.append(("DS%d  n=%-3d sink CSC%-3d row %-2d %+.2f"
                      % (d["c"], d["n"], d["csc"], d["row"], d["value"]),
                      colors.get(d["c"], INK), 8.4, "normal"))
    rows_ = [d["row"] for d in res["decide"] if d.get("n")]
    lines.append(("", GREY, 3, "normal"))
    if len(rows_) >= 2:
        lines.append(("rule: DS1 = smallest sink row", INK, 8.4, "normal"))
        lines.append(("      " + "  <  ".join(str(r) for r in rows_),
                      INK, 8.4, "normal"))
    lines.append(("flipped by hand: %s"
                  % ("YES" if state.get("flip") else "no"),
                  "#a4531c" if state.get("flip") else GREY, 8.4, "normal"))
    multi = [d for d in res["decide"] if len(d.get("lows", [])) > 1]
    if multi:
        lines.append(("", GREY, 3, "normal"))
        lines.append(("CAREFUL — more than one sink", "#a4531c", 8.4, "bold"))
        for d in multi:
            lines.append(("  DS%d dips at CSC%s"
                          % (d["c"], ",".join(str(x) for x in d["lows"])),
                          "#a4531c", 8.0, "normal"))
        lines.append(("  argmin takes the DEEPEST dip,", GREY, 7.8, "normal"))
        lines.append(("  not the shallowest one. Narrow", GREY, 7.8, "normal"))
        lines.append(("  the box, or use flip DS1/DS2.", GREY, 7.8, "normal"))
    y = .99
    for txt, col, size, weight in lines:
        if txt:
            ax.text(.0, y, txt, transform=ax.transAxes, va="top", ha="left",
                    fontsize=size, color=col, fontweight=weight)
        y -= (size + 5.0) / 235.0

    # Every repaired contact, named, and which of the three found it. The
    # amplitude screen's finding used to go unreported, so a dead wire was
    # being interpolated with nothing on screen to say so.
    def _lst(src):
        return ",".join("CSC%d" % n for n in sorted(src)) or "none"

    auto_csd = sorted(set(res["bad"]) - set(state["bad0"])
                      - set(state["manual_bad"]))
    state["fig"].suptitle(
        "%s   ·   %d events   ·   depth CSC%d–%d (%d)   ·   time %+.0f to "
        "%+.0f ms (%d sample%s)   ·   %d classes   ·   features %s"
        % (state["session_label"], types.size, lo_n, hi_n, len(sel),
           tw[t0], tw[max(t0, t1 - 1)], t1 - t0, "" if t1 - t0 == 1 else "s",
           res["k"], "60 Hz notched" if state["notch"] else "no notch (Toothy)"),
        fontsize=10.5, y=.988)
    state["fig"].texts[0].set_text(state["fig"].texts[0].get_text())
    state["repaired_note"].set_text(
        "repaired — amplitude: %s   ·   CSD: %s   ·   by hand: %s"
        % (_lst(state["bad0"]), _lst(auto_csd), _lst(state["manual_bad"])))
    state["fig"].canvas.draw_idle()


# --------------------------------------------------------------------------
def build(state):
    fig = plt.figure(figsize=(17.6, 9.6))
    state["fig"] = fig
    # Four columns, the last one narrower: it carries the decision panel,
    # which is text and needs less width than a raster.
    gs = gridspec.GridSpec(2, 4, figure=fig, hspace=.34, wspace=.27,
                           width_ratios=[1, 1, 1, .72],
                           left=.048, right=.988, top=.905, bottom=.155)
    state["axes"] = {
        "volt": fig.add_subplot(gs[0, 0]),
        "csd": fig.add_subplot(gs[0, 1]),
        "pca": fig.add_subplot(gs[0, 2]),
        "why": fig.add_subplot(gs[0, 3]),
        "profile": fig.add_subplot(gs[1, 0]),
        "csd1": fig.add_subplot(gs[1, 1]),
        "csd2": fig.add_subplot(gs[1, 2]),
        "feat": fig.add_subplot(gs[1, 3]),
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
    s_k = Slider(fig.add_axes([.072, .076, .155, .020]), "classes", 2, 5,
                 valinit=state["nclasses"], valstep=1)
    s_k.label.set_fontsize(9)
    s_k.valtext.set_fontsize(9)

    note = fig.text(.040, .046,
                    "mains %.0f µV rms of %.0f µV (%.0f%%)"
                    % (state["mains_uv"], state["wideband_uv"],
                       100 * state["mains_uv"] / max(state["wideband_uv"], 1e-9)),
                    fontsize=8.5, color=GREY, va="center")
    fig.text(.040, .020,
             "drag = box  ·  right-click a depth panel = guide  ·  "
             "← → = step spikes  ·  Esc = average",
             fontsize=8.5, color=GREY, va="center")
    state["note"] = note

    ax_chk = fig.add_axes([.275, .012, .12, .088])
    ax_chk.set_frame_on(False)
    chk = CheckButtons(ax_chk, ["60 Hz notch", "CSD screen"],
                       [state["notch"], state["screen"]])
    # The CSD screen is OFF by default. It is a heuristic for finding wires
    # that misbehave, and on these probes it finds contacts that are simply
    # carrying signal -- CSC59 is the only bad one, and the amplitude screen
    # already has it. Left as a checkbox because the heuristic is still worth
    # a look when a new probe misbehaves, but nothing is repaired on its say
    # so unless somebody asks.
    for t in chk.labels:
        t.set_fontsize(9)

    b_auto = Button(fig.add_axes([.392, .058, .078, .040]), "auto box")
    b_one = Button(fig.add_axes([.392, .012, .078, .040]), "1 sample")
    b_prev = Button(fig.add_axes([.478, .058, .078, .040]), "◀ prev")
    b_next = Button(fig.add_axes([.478, .012, .078, .040]), "next ▶")
    b_mean = Button(fig.add_axes([.564, .058, .078, .040]), "show average")
    b_save = Button(fig.add_axes([.564, .012, .078, .040]), "save fig + csv")
    b_clear = Button(fig.add_axes([.650, .058, .078, .040]), "clear guides")
    b_unbad = Button(fig.add_axes([.650, .012, .078, .040]), "clear bad")
    b_flip = Button(fig.add_axes([.736, .058, .078, .040]), "flip DS1/DS2")
    for b in (b_auto, b_one, b_prev, b_next, b_mean, b_save, b_clear, b_unbad,
              b_flip):
        b.label.set_fontsize(8.5)

    tb = TextBox(fig.add_axes([.855, .058, .068, .038]), "guide ",
                 initial="", textalignment="left")
    tb_bad = TextBox(fig.add_axes([.855, .012, .068, .038]), "bad ",
                     initial="", textalignment="left")
    for t in (tb, tb_bad):
        t.label.set_fontsize(8.5)
        t.text_disp.set_fontsize(8.5)

    state["where"] = fig.text(.736, .030, "", fontsize=8.5, va="center",
                              color=INK)
    state["guide_note"] = fig.text(
        .932, .020, "", fontsize=8.5, va="center", color=GREY)
    state["repaired_note"] = fig.text(
        .5, .958, "", fontsize=8.5, va="center", ha="center", color=GREY)

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

    def step(delta):
        """Walk the spikes in time order, wrapping at both ends.

        Deliberately independent of the box: stepping through events while
        dragging is the whole point -- you widen the time window, walk a
        dozen spikes to see whether the extra samples are carrying anything,
        and widen again. Nothing is recomputed, only redrawn, so it is
        instant however many events there are.
        """
        n = len(state["rows"])
        cur = state["picked"]
        state["picked"] = 0 if cur is None else int((cur + delta) % n)
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

    def on_key(event):
        # Nothing here may fire while the guide box has the keyboard, or
        # typing "next" in a label would step four spikes.
        if (getattr(tb, "capturekeystrokes", False)
                or getattr(tb_bad, "capturekeystrokes", False)):
            return
        if event.key in ("right", "n"):
            step(+1)
        elif event.key in ("left", "p"):
            step(-1)
        elif event.key in ("escape", "0"):
            show_mean(None)

    def say(msg):
        state["guide_note"].set_text(msg)
        state["guide_note"].set_color(GREY if "limit" not in msg else "#a4531c")
        state["fig"].canvas.draw_idle()

    def redraw_guides():
        save_guides(state)
        draw(state, state["res"])
        sync_box()

    def on_submit(text):
        """'30 hilus' in the box, Enter -- position first, then the name."""
        got = parse_guide(text)
        if got is None:
            say("type a contact then a name, e.g. 30 hilus")
            return
        say(toggle_guide(state, got[0], got[1]))
        tb.set_val("")
        redraw_guides()

    def on_click(event):
        """Right-click on any depth panel: add a guide there, or take it off."""
        if event.button != 3 or event.inaxes is None or event.ydata is None:
            return
        depth_axes = [state["axes"][k]
                      for k in ("volt", "csd", "profile", "csd1", "csd2")]
        if event.inaxes not in depth_axes:
            return
        label = parse_guide("0 " + tb.text)
        say(toggle_guide(state, int(round(event.ydata)),
                         label[1] if label else tb.text.strip()))
        redraw_guides()

    def clear_guides(_):
        state["guides"] = []
        say("guides cleared")
        redraw_guides()

    def on_bad(text):
        """Mark contacts bad by hand, or put ones already marked back in."""
        say(toggle_bad(state, text))
        tb_bad.set_val("")
        save_bad(state)
        refresh()

    def flip_types(_):
        """Swap DS1 and DS2 -- the last word on the labels is anatomy's."""
        state["flip"] = not state.get("flip")
        save_flip(state)
        say("DS1/DS2 flipped by hand" if state["flip"]
            else "DS1/DS2 back to the computed order")
        refresh()

    def clear_bad(_):
        state["manual_bad"] = {}
        save_bad(state)
        say("hand-marked contacts cleared (the automatic screens still run)")
        refresh()

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
            if state["guides"]:
                fh.write("# guides: %s\n" % "; ".join(
                    "CSC%d %s" % (g["csc"], g["label"] or "-")
                    for g in state["guides"]))
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
    b_prev.on_clicked(lambda _: step(-1))
    b_next.on_clicked(lambda _: step(+1))
    b_mean.on_clicked(show_mean)
    b_save.on_clicked(save)
    b_clear.on_clicked(clear_guides)
    b_unbad.on_clicked(clear_bad)
    b_flip.on_clicked(flip_types)
    tb.on_submit(on_submit)
    tb_bad.on_submit(on_bad)
    fig.canvas.mpl_connect("pick_event", on_pick)
    fig.canvas.mpl_connect("key_press_event", on_key)
    fig.canvas.mpl_connect("button_press_event", on_click)
    state["step"] = step
    # Exposed so the headless probe can drive the paths a render cannot reach.
    state["on_key"] = on_key
    state["on_click"] = on_click
    state["on_submit"] = on_submit
    state["clear_guides"] = clear_guides
    state["on_bad"] = on_bad
    state["clear_bad"] = clear_bad
    state["flip_types"] = flip_types
    state["_widgets"] = (s_k, chk, b_auto, b_one, b_prev, b_next, b_mean,
                         b_save, b_clear, tb, b_unbad, tb_bad, b_flip)
    state["refresh"] = refresh
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
        "notch": True, "screen": False, "nclasses": 2, "picked": None,
        "gain": 4.0, "guides": load_guides(args), "guide_artists": [],
        "manual_bad": load_bad(args), "flip": load_flip(args),
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
