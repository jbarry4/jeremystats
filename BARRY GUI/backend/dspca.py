"""
dspca.py -- telling DS1 from DS2, without a window.

Step four of The Dentist. Incisor found them, Checkup said which ones are
real, Braces put every stamp on its own peak, and this says which KIND each
one is.

WHAT A FEATURE IS, AND WHY THERE ARE TWO AXES
=============================================
Toothy describes an event by its depth profile at exactly one millisecond --
`lfp_interp[channels][:, idx]`, a column -- so the only choice anybody makes
is which contacts. That is the whole feature set.

Here the selection has two axes:

    DEPTH   which contacts the CSD runs over   (Toothy's one choice)
    TIME    how many samples around the stamp  (Toothy: always one)

and the features are that whole block, flattened. Pull the box down to a
single column and this is Toothy exactly; widen it and each event is a shape
in depth AND time, which is what tells a biphasic event from a monophasic one
of the same amplitude -- something a single sample cannot see however well
the stamp is aligned.

WHAT IS MEASURED IS NOT WHAT IS DRAWN, AND THAT IS DELIBERATE
=============================================================
The raster a person drags on is the 5-100 Hz, mains-out CSD, because that is
what makes a dentate spike LOOK like one: broadband, the event is buried under
the slow field and the depth band would be chosen by eye from a picture with
no event in it.

The FEATURES stay broadband, because that is what Toothy does -- its
`bp_dict['raw']` is the plain downsampled trace and the DS band is used only
to find peak times. `Params.notch` switches the features between Toothy's
choice and ours. So: the picture is filtered, the measurement is whatever the
caller asked for, and the two are never silently swapped.

ONE MORE ASYMMETRY WORTH KNOWING. The raster shows the CSD of the whole shank;
the features are the CSD computed WITHIN the selected contacts, so the top and
bottom rows of the box get Vaknin-extended at the box edge rather than reading
their real neighbours. That is Toothy's behaviour and it is why the outermost
row or two of a narrow box is not to be trusted.

REFINEMENT IS OFF BY DEFAULT HERE, AND THAT IS THE DIFFERENCE FROM THE DRAFT
===========================================================================
The standalone version refines every stamp onto the nearest CSD peak, because
its input was a bank CSV that may never have been aligned. In the bundle,
Braces has already done exactly that and done it better -- an optimal matching
over a whole run of stamps and peaks, not nearest-wins one at a time. Refining
an `aligned` version again would move stamps a second time under a weaker
rule, so `refine` defaults to "off" and the caller turns it on knowingly.

WHAT IS EXPENSIVE AND WHAT IS NOT
=================================
`read` is minutes and happens once per (recording, read settings); the caller
caches it. `fit` is a tridiagonal matrix multiply and two components over a
few dozen points -- milliseconds, which is why the box can be live rather than
behind a "recompute" button.

NOTHING HERE DRAWS. No matplotlib, at any depth. The standalone `ds_pca.py`
and `dentate_spike_aligner.py` both import pyplot at module scope and both
call `sys.exit` on bad input, so neither may be imported by the server; the
functions below are copies, and `tools/check_dspca.py` is what keeps the two
honest about being the same arithmetic.
"""
from __future__ import annotations

import json
import os

import numpy as np

from . import braces, csc, incisor, probes

try:
    from scipy.signal import convolve, find_peaks
    from scipy.signal.windows import gaussian
    HAVE_SCIPY = True
except Exception:                                        # noqa: BLE001
    convolve = find_peaks = gaussian = None
    HAVE_SCIPY = False

# Guarded, and the guard is not decoration.
#
# `app.py` imports every backend module at boot, so an unguarded
# `from sklearn...` on a machine that has not run Setup since scikit-learn
# joined requirements.txt would take the whole application down -- not this
# panel, the whole thing -- with an ImportError nobody would connect to a
# dentate spike. Missing sklearn has to be a sentence in one tool, not a
# server that will not start.
try:
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    HAVE_SKLEARN = True
except Exception:                                        # noqa: BLE001
    KMeans = PCA = None
    HAVE_SKLEARN = False

NO_SKLEARN = (
    "This step needs scikit-learn, which is not installed on this machine. "
    "Run Setup Windows.bat (or Setup Mac.command) again, or "
    "`pip install scikit-learn`.")


class DsPcaError(Exception):
    """Something a person can fix, said in a sentence."""


# --------------------------------------------------------------------------
# The numbers
# --------------------------------------------------------------------------
# Toothy's own defaults, from qparam.get_original_defaults(). Named in one
# block so a change in Toothy is a diff here rather than a hunt.
T_LFP_FS = 1000.0            # 'lfp_fs'
T_DS_FREQ = (5.0, 100.0)     # 'ds_freq'   -- the detection/refinement band
T_F_ORDER = 3                # 'f_order'   -- spatial filter length
T_F_SIGMA = 1.0              # 'f_sigma'
T_VAKNIN = True              # 'vaknin_el'
T_COND = 0.3                 # 'cond'      -- S/m
T_NCLUSTERS = 2              # 'nclusters'

WINDOW_MS = 100.0            # how far a stamp may move, if it may move
SURROUND_MS = 50.0           # half-width of the window kept around each stamp
PAD_S = 0.5                  # filter margin, read then trimmed

# The DS1..DSn colours, assigned in a fixed order and never cycled: class 3 is
# always this orange whether or not class 4 exists, so adding a cluster cannot
# repaint the ones already on screen. The first two are the `ds1` and `ds2`
# label colours in curation.KINDS, and they have to stay in step.
CLASS_COLORS = ["#1a7f37", "#7b3fa0", "#b8620a", "#1f6feb", "#a3155f"]

RULES = ("tort", "sink", "sources", "anatomy")

MAX_CLASSES = 5


class Params:
    """One question, as an attribute bag.

    Deliberately attribute-shaped and deliberately using the same field names
    as the standalone script's argparse namespace, so every function lifted
    out of `ds_pca.py` reads `p.cond` and `p.spacing` exactly as it read
    `args.cond` and `args.spacing`. That is what lets `tools/check_dspca.py`
    compare the two implementations by running them side by side rather than
    by reading them side by side.

    The fields split into two groups and the split is the whole caching
    story: `READ_KEYS` change what comes off the disk, everything else only
    changes what is done with it afterwards.
    """

    # What was READ. A change to any of these invalidates the .npz; a change
    # to anything else must not, because the box being live is the point.
    READ_KEYS = ("lfp_fs", "band", "window_ms", "surround_ms", "pad",
                 "refine", "spacing", "probe", "line", "line_q", "invert",
                 "channels", "bad")

    # What was ASKED of it. These name the answer, not the read.
    FIT_KEYS = ("notch", "screen", "csd_bad_x", "csd_span", "nclasses",
                "rule", "flip", "seed", "sel_lo", "sel_hi", "t_lo_ms",
                "t_hi_ms", "cond", "f_order", "f_sigma", "no_vaknin",
                "h_power", "features", "dead",
                # Which of the three methods, and the two numbers the two
                # that use the sink gap are shaped by.
                "method", "min_sep", "gap_weight", "delta_cut",
                "manual_bad")

    def __init__(self, **kw):
        # -- the read ---------------------------------------------------
        self.lfp_fs = float(kw.get("lfp_fs") or T_LFP_FS)
        band = kw.get("band") or T_DS_FREQ
        self.band = (float(band[0]), float(band[1]))
        self.window_ms = float(kw.get("window_ms") or WINDOW_MS)
        self.surround_ms = float(kw.get("surround_ms") or SURROUND_MS)
        self.pad = float(kw.get("pad") if kw.get("pad") is not None else PAD_S)
        # "off" is the default, not "nearest". See the module docstring.
        self.refine = kw.get("refine") or "off"
        # Which template this recording's probe is. NOT guessed from the
        # channel count: `probes.suggest(64)` answers "h3", because 64
        # contacts is an H3 and an H10-D alike and only a person knows which
        # was in the animal. The caller reads it off the session record and
        # refuses when nobody has said -- see `probes.state_of`.
        self.probe = kw.get("probe") or None
        # None means "ask the probe", which is the only right answer -- see
        # `spacing_for`. A number here is an override and is recorded as one.
        self.spacing = kw.get("spacing")
        self.line = float(kw.get("line") if kw.get("line") is not None
                          else braces.LINE_HZ)
        self.line_q = float(kw.get("line_q") or braces.LINE_Q)
        self.invert = bool(kw.get("invert", True))
        self.channels = kw.get("channels") or ""
        # Which contacts a person has marked bad on this recording.
        #
        # In the READ key because the stored windows are repaired ones: a bad
        # row is replaced by the interpolation of its neighbours before it is
        # kept, so marking a new wire bad genuinely changes the arrays. Left
        # out of the key, the next read would quietly hand back the old
        # repair and the panel would show a correction that had not been
        # applied. The automatic screens are NOT in here -- they are a
        # function of the data, so they cannot change without it.
        self.bad = sorted(int(n) for n in (kw.get("bad") or []))

        # -- the CSD ----------------------------------------------------
        self.cond = float(kw.get("cond") or T_COND)
        # How the patch becomes a feature vector. A question ASKED of the
        # read, never a property of it: switching it must not invalidate
        # the .npz, which is the whole reason the box is draggable.
        feats = str(kw.get("features") or "minmax")
        self.features = feats if feats in FEATURES else "minmax"
        self.dead = float(kw.get("dead") if kw.get("dead") is not None
                          else DEAD_FRAC)
        # DELTA IS THE DEFAULT, deliberately. The thing being clustered is
        # then the thing somebody meant to cluster on, and the boundary is
        # a threshold that can be read off an axis and quoted. The two PCA
        # methods are computed beside it every time, so the choice is
        # always visible rather than assumed -- see `fit`.
        # CONTACTS TAKEN OUT BY HAND, on top of the ones the recording
        # is already marked with.
        #
        # A FIT parameter and not a read one: taking a wire out changes
        # the answer and must not invalidate the minutes of reading. It
        # does NOT change the refinement either -- those stamps were
        # timed during the read against the read-time bad list -- which
        # is a real limitation and a small one: one dead wire among
        # sixty-four moves a mean over depth by almost nothing.
        #
        # And they are REPAIRED, not dropped. A CSD is a second
        # difference over depth and needs an even grid; a contact taken
        # out of the middle leaves the rest unevenly spaced.
        mb = kw.get("manual_bad")
        if isinstance(mb, dict):
            self.manual_bad = {int(k2): (v or "by hand")
                               for k2, v in mb.items()}
        elif mb:
            self.manual_bad = {int(n): "by hand" for n in mb}
        else:
            self.manual_bad = {}

        # A THRESHOLD PLACED BY HAND, for the one method whose axis has
        # units. See `fit`. A list, because k classes need k-1 of them.
        cut = kw.get("delta_cut")
        if cut in (None, "", []):
            self.delta_cut = None
        else:
            try:
                self.delta_cut = sorted(float(c) for c in cut)
            except (TypeError, ValueError):
                self.delta_cut = None
        meth = str(kw.get("method") or "delta")
        self.method = meth if meth in METHODS else "delta"
        self.min_sep = max(1, int(kw.get("min_sep") or MIN_SINK_SEP))
        gw = kw.get("gap_weight")
        self.gap_weight = float(GAP_WEIGHT if gw is None else max(0.0, gw))
        self.f_order = int(kw.get("f_order") or T_F_ORDER)
        self.f_sigma = float(kw.get("f_sigma") or T_F_SIGMA)
        self.no_vaknin = bool(kw.get("no_vaknin", not T_VAKNIN))
        self.h_power = int(kw.get("h_power") or 1)

        # -- the question -----------------------------------------------
        self.notch = bool(kw.get("notch", True))
        self.screen = bool(kw.get("screen", False))
        self.csd_bad_x = float(kw.get("csd_bad_x") or 4.0)
        self.csd_span = int(kw.get("csd_span") or braces.DEPTH_BAND)
        self.nclasses = int(kw.get("nclasses") or T_NCLUSTERS)
        self.rule = kw.get("rule") or "tort"
        self.flip = bool(kw.get("flip", False))
        self.seed = int(kw.get("seed") or 0)

        # The box, in the units a person and a URL both understand: contact
        # NUMBERS and milliseconds. Sample indices and row indices are
        # derived at fit time, because they depend on what was read and a
        # saved run has to survive a re-read at a different rate.
        self.sel_lo = kw.get("sel_lo")
        self.sel_hi = kw.get("sel_hi")
        self.t_lo_ms = kw.get("t_lo_ms")
        self.t_hi_ms = kw.get("t_hi_ms")

        if self.rule not in RULES:
            raise DsPcaError(
                "%r is not one of the DS1/DS2 rules (%s)."
                % (self.rule, ", ".join(RULES)))
        if not 2 <= self.nclasses <= MAX_CLASSES:
            raise DsPcaError(
                "Between 2 and %d classes, not %d."
                % (MAX_CLASSES, self.nclasses))

    def read_params(self):
        """Just the fields that decide what comes off the disk."""
        return {k: getattr(self, k) for k in self.READ_KEYS}

    def fit_params(self):
        return {k: getattr(self, k) for k in self.FIT_KEYS}

    def spec(self):
        """The filter spec `braces` and `incisor` both speak."""
        return {"band": self.band, "line_hz": self.line,
                "line_q": self.line_q, "lfp_fs": self.lfp_fs,
                "spacing_um": self.spacing, "csd_smooth": True}

    def as_dict(self):
        out = dict(self.read_params())
        out.update(self.fit_params())
        return out


def spacing_for(probe_id):
    """Contact pitch in microns, from the probe rather than from a constant.

    This matters more than it looks. The CSD divides by h squared, so the
    difference between the H10-D's 30 um within-column pitch and the linear
    arrays' 50 um is a factor of 2.8 on every number the panel shows --
    silently, with nothing on screen that looks wrong.

    The standalone script defaulted to `probes.CONTACT_PITCH_UM`, which is
    the H10-D's within-column pitch, because it was only ever pointed at one
    probe. Read from the template here, the same way `probes.listing` reads
    it, so there is one answer to what the pitch is.
    """
    probe = probes.get(probe_id) or {}
    return float(probe.get("pitch_um", probes.CONTACT_PITCH_UM))


def geometry(probe_id, channels):
    """The runs of contacts a CSD may legally be taken down.

    A CSD is a second spatial derivative across DEPTH, so it is only defined
    over contacts that are neighbours on the probe. Two templates in this lab
    break that if you read them down the channel order:

      h10d   two shanks of three interleaved columns, so CSC 1, 2, 3 are
             three different columns and consecutive numbers are not
             neighbours at all.
      dual   two separate implants, so the derivative at channel 64 subtracts
             motor cortex from hippocampus.

    Either way the number that comes out is not a large current sink, it is
    nonsense, and nothing about it looks wrong -- which is why this returns
    the columns rather than warning about them.

    Returns (runs, probe) where `runs` is a list of {label, rows, numbers}
    with `rows` as indices into `channels`. A single linear array comes back
    as one run covering everything, which is the common case and needs no
    special handling downstream.
    """
    probe = probes.get(probe_id)
    cols = probes.columns_for(probe_id, channels) if probe else None
    if not cols:
        return ([{"id": "line", "label": "the whole shank",
                  "rows": list(range(len(channels))),
                  "numbers": [int(c["number"]) for c in channels]}],
                probe)
    runs = []
    for col in cols:
        rows = list(col.get("indices") or [])
        if len(rows) < 3:
            continue
        runs.append({"id": col.get("id"), "label": col.get("label") or col.get("id"),
                     "rows": rows,
                     "numbers": [int(channels[i]["number"]) for i in rows]})
    if not runs:
        raise DsPcaError(
            "None of this recording's %s columns has three contacts present, "
            "so there is nowhere a CSD can be taken."
            % (probe or {}).get("name", "probe"))
    return runs, probe


def run_for_box(runs, sel):
    """Which column a chosen box lies in, or None if it straddles two.

    Straddling is the failure this exists to catch. It is not an edge case on
    an H10-D: contacts 26 to 41 is a perfectly reasonable-looking box and it
    spans all six columns.
    """
    want = set(sel or [])
    if not want:
        return None
    for run in runs:
        if want <= set(run["rows"]):
            return run
    return None


# --------------------------------------------------------------------------
# Toothy's CSD, without quantities, probeinterface or Qt
# --------------------------------------------------------------------------
def standard_csd(lfp, h_m, sigma=T_COND, vaknin=T_VAKNIN, h_power=1):
    """icsd.StandardCSD.get_csd, for [nCh x nCol] in volts.

    The Vaknin trick is what keeps the output the same height as the input:
    a second difference over n points gives n-2, so the endpoint contacts are
    duplicated first and the two extra rows are dropped afterwards. The top
    and bottom contacts therefore get a CSD computed as though the field were
    flat just past the end of the probe, which is an assumption and not a
    measurement -- it is Toothy's assumption, so it is kept.
    """
    x = np.asarray(lfp, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if vaknin:
        ext = np.empty((x.shape[0] + 2, x.shape[1]), dtype=np.float64)
        ext[0] = x[0]
        ext[1:-1] = x
        ext[-1] = x[-1]
    else:
        ext = x
    n = ext.shape[0]

    f_inv = -np.eye(n)
    for j in range(1, n - 1):
        f_inv[j, j - 1:j + 2] = np.array([1.0, -2.0, 1.0])
    f_inv = f_inv * -sigma / (h_m ** h_power)

    csd = f_inv.dot(ext)
    return csd[1:-1] if vaknin else csd


def filter_csd(csd, f_order=T_F_ORDER, f_sigma=T_F_SIGMA):
    """icsd.CSD.filter_csd, 'convolve' branch, gaussian window.

    Note the 'same' convolution: it zero-pads, so the first and last contacts
    are pulled toward zero by the part of the kernel hanging off the end of
    the probe. Real, reproduced, and a reason not to read anything into the
    two outermost rows.
    """
    if not HAVE_SCIPY:
        raise DsPcaError("This step needs scipy, which is not installed.")
    num = gaussian(int(f_order), float(f_sigma))
    num = num / num.sum()
    out = np.array(csd, dtype=np.float64, copy=True)
    for i in range(out.shape[1]):
        out[:, i] = convolve(out[:, i], num, "same")
    return out


def normalize_columns(x):
    """pyfx.Normalize down each column -- one event, min-max to [0, 1].

    Per EVENT and not per contact, which is what makes the features a shape
    rather than a size: a big dentate spike and a small one with the same
    laminar profile land on top of each other in the PCA. It also makes the
    whole thing invariant to the units of the input, which is why Toothy's
    "assume mV" does not matter here.
    """
    out = np.array(x, dtype=np.float64, copy=True)
    for i in range(out.shape[1]):
        col = out[:, i]
        lo, hi = np.nanmin(col), np.nanmax(col)
        out[:, i] = np.zeros(col.size) if hi == lo else (col - lo) / (hi - lo)
    return out


def toothy_csd(lfp_uv, pitch_um, p):
    """(raw, filtered, normalized) CSD for [nCh x nCol] of microvolts.

    Toothy reads its LFP as millivolts and rescales to volts; ours is
    microvolts, so the conversion differs by a thousand. It changes the
    magnitude of `raw` and `filt` and nothing else -- `norm` is invariant,
    and `norm` is the only one the PCA sees.
    """
    volts = np.asarray(lfp_uv, dtype=np.float64) * 1e-6
    h_m = float(pitch_um) * 1e-6
    raw = standard_csd(volts, h_m, sigma=p.cond, vaknin=not p.no_vaknin,
                       h_power=p.h_power)
    filt = filter_csd(raw, p.f_order, p.f_sigma)
    return raw, filt, normalize_columns(filt)


def stack_csd(sur, p, pitch_um):
    """CSD of every event at once, as [nEvents x nCh x nSamp].

    One matrix multiply rather than one per event: the CSD is independent
    column by column, so every event's window can be laid side by side,
    differenced in a single call and folded back. With sixty events that is
    the difference between a drag that stutters and one that does not.
    """
    n_ev, n_ch, n_t = sur.shape
    flat = sur.transpose(1, 0, 2).reshape(n_ch, n_ev * n_t)
    csd = toothy_csd(flat, pitch_um, p)[1]               # filtered
    return csd.reshape(n_ch, n_ev, n_t).transpose(1, 0, 2)


FEATURES = ("minmax", "sign", "sign_dead")
DEAD_FRAC = 0.15             # 'dead', as a fraction of the patch's own peak

FEATURE_NAMES = {
    "minmax": "min-max (Toothy)",
    "sign": "sign ±1",
    "sign_dead": "sign + deadband",
}


MIN_SINK_SEP = 5        # contacts; two sinks closer than this are one sink
GAP_WEIGHT = 1.0       # how hard the gap column is allowed to pull

METHODS = ("pca", "pca_gap", "delta")
METHOD_NAMES = {
    "pca": "PCA, no gap",
    "pca_gap": "PCA + gap",
    "delta": "delta only, no PCA",
}


def two_sinks(mu, min_sep=MIN_SINK_SEP):
    """The two LARGEST sinks of one depth profile, shallower first.

    Largest by how far the CSD actually dips, not by prominence.
    Prominence asks how far a dip stands above its own surroundings, which
    can rank a small notch on a flat stretch above a deep trough on a
    slope; "largest" is the plainer question and the one that was asked
    for.

    A MINIMUM SEPARATION, because two dips three contacts apart are the
    same sink seen twice through a spatial filter, not two laminar sinks.
    A 3-point Gaussian taper across depth plus a second difference will
    routinely split one trough into a pair, and without this floor the
    gap measures the width of that artefact rather than the distance
    between the molecular layers. Contacts are 30 um, so the default of 5
    is 150 um -- comfortably under the OML-to-MML spacing and comfortably
    over anything the smoothing can manufacture.

    Recomputed from the profile it is handed, every time. The pair is what
    the gap feature measures AND what the panels draw, from this one
    function, so the marks on screen cannot drift from the number in the
    feature vector.
    """
    mu = np.asarray(mu, dtype=np.float64)
    sep = MIN_SINK_SEP if min_sep is None else max(1, int(min_sep))
    try:
        from scipy.signal import find_peaks
        idx, _props = find_peaks(-mu)
    except Exception:                                    # noqa: BLE001
        idx = np.array([], dtype=int)
    if idx.size == 0:
        r = int(np.argmin(mu))
        return r, r
    order = [int(r) for r in idx[np.argsort(mu[idx])]]   # deepest first
    first = order[0]
    second = next((r for r in order[1:] if abs(r - first) >= sep), None)
    if second is None:
        return first, first          # only one real sink in this profile
    return (min(first, second), max(first, second))


def sink_gap(block, min_sep=MIN_SINK_SEP):
    """How far apart each event's two sinks are, on a 0-to-1 scale.

        0  the two sinks are neighbouring contacts
        1  they are at opposite ends of the selected band

    which is `(gap - 1) / (span - 2)`, clipped. Put that way it is pure
    geometry: two events with the same laminar spacing give the same
    number whatever the band width, wherever the probe sits, and however
    big the event was.

    WHAT IS AND IS NOT AMPLITUDE-FREE. The VALUE carries no amplitude --
    it is two row indices and nothing else, so a loud event and a quiet
    one with the same geometry are identical here. The CHOICE of which two
    sinks to measure does rank candidates by depth, but that ranking never
    reaches the output.

    On a 0-1 scale it also sits in the same range as the min-max profile
    features, so it is one column among many rather than the column that
    decides everything. In raw contacts it did decide everything: its
    spread was five times a min-max column's, and switching it on took
    PC1's correlation with loudness from 0.52 to 0.75.

    An event with fewer than two detectable sinks gets 0. Returns the
    scale, the raw contact gap and the two rows, because the panels draw
    all three.
    """
    prof = np.asarray(block, dtype=np.float64).mean(axis=2)   # [nEv x span]
    span = prof.shape[1]
    out = np.zeros((prof.shape[0], 1), dtype=np.float64)
    gaps, rows = [], []
    for i, mu in enumerate(prof):
        r1, r2 = two_sinks(mu, min_sep)
        gap = abs(r2 - r1)
        rows.append((int(r1), int(r2)))
        gaps.append(int(gap))
        if gap >= 1:
            out[i, 0] = min(max((gap - 1.0) / max(span - 2.0, 1.0), 0.0), 1.0)
    return out, gaps, rows


def normalize_block(block, mode="minmax", dead=DEAD_FRAC):
    """Turn each event's CSD patch into the vector the PCA sees.

    `minmax` is Toothy: pyfx.Normalize per EVENT over the whole selected
    block. Toothy normalizes each event's single column across depth. With
    a time window there is more than one column, and the honest
    generalization is one min and one max for the whole patch --
    normalizing each column separately would erase exactly the thing a time
    window was opened to see, which is how the profile changes from
    millisecond to millisecond.

    WHY THE OTHER TWO EXIST. Min-max removes SCALE exactly: a*x and x land
    on the same point, so in principle a loud and a quiet event with the
    same shape are the same feature vector. In practice it does not hold,
    because the scale is set by two samples -- the single min and the
    single max. A quiet event riding the same background noise normalizes
    to a NOISIER shape, and that is an amplitude effect that survives the
    normalization. Measured on M2ctls3jan23: under min-max the two K-means
    classes differ in amplitude by 3.07x, and PC1 correlates 0.52 with log
    amplitude. The clusters were substantially loud-versus-quiet.

    `sign` throws the magnitudes away completely and keeps only source
    (+1) or sink (-1) per contact, which is the laminar pattern and nothing
    else. On the same recording that drops the class amplitude ratio to
    1.12x -- the loudness split is gone.

    `sign_dead` is sign with a null band, because pure sign gives a contact
    two hundred microns from the dipole, where the CSD is essentially zero,
    exactly as much vote as the contact at the sink. Everything within
    `dead` of the patch's own peak becomes 0 rather than a coin flip.

    Read the result with the amplitude question in mind: if the classes
    stop separating once the magnitudes go, they were separating on
    magnitude.
    """
    out = np.asarray(block, dtype=np.float64).copy()
    for i in range(out.shape[0]):
        x = out[i]
        if mode == "sign":
            out[i] = np.sign(x)
        elif mode == "sign_dead":
            thr = dead * np.nanmax(np.abs(x))
            out[i] = np.where(x > thr, 1.0, np.where(x < -thr, -1.0, 0.0))
        else:
            lo, hi = np.nanmin(x), np.nanmax(x)
            out[i] = np.zeros_like(x) if hi == lo else (x - lo) / (hi - lo)
    return out


# --------------------------------------------------------------------------
# The expensive half
# --------------------------------------------------------------------------
def _read_span(session, channels, t0, t1, p, report=None):
    """One stretch on every channel: broadband, broadband-notched, DS-band.

    All three come out of ONE read. The refinement needs the band-limited
    CSD, the features need the broadband sample at whatever time it lands on,
    and the notch is a checkbox somebody flips while watching -- reading the
    file again for any of that would make the cheapest control the slowest.
    Three copies of a window is a few megabytes; a second pass over the .ncs
    is minutes.
    """
    wide, wide_n, band, anchor, fs_out = [], [], [], None, None
    raw_rms, line_rms = [], []
    spec = p.spec()
    for ch in channels:
        raw, got_t0, ch_fs = csc._read_channel_window(session, ch, t0, t1)
        if raw.size < 8:
            return None
        q = incisor.decimation_for(ch_fs, p.lfp_fs)
        dec = incisor._decimate(raw, q) if q > 1 else np.asarray(raw, float)
        if dec.size < 16:
            return None
        if anchor is None:
            anchor, fs_out = got_t0, ch_fs / q
        # Measured whether or not it is applied. Toothy never notches, so the
        # default leaves the mains in the features -- but "how much mains is
        # in the features" is the number that decides whether that matters,
        # and it is not knowable from a run that silently kept it.
        clean = braces._notch(dec, fs_out, spec)
        raw_rms.append(float(np.std(dec)))
        line_rms.append(float(np.std(dec - clean)))
        # THE REFINEMENT IS ALWAYS NOTCHED, whatever the features do.
        #
        # 60 Hz sits INSIDE the 5-100 Hz band the refinement measures in, and
        # it survives a CSD -- it is common-mode, but a second difference of
        # a common-mode line is not zero on a real probe. What an alignment
        # produces is a TIME, and a mains ripple in the trace it picks peaks
        # off is a systematic error in that time. Measured on M1ptens8oct4,
        # notching first tightens the refinement's IQR from 3.6 ms to 1.8 ms.
        # Toothy's "no notch" is a statement about its FEATURES; it is not a
        # reason to time events badly.
        band.append(incisor._filtered(clean, fs_out, p.band))
        wide.append(dec)
        wide_n.append(clean)
    if not wide:
        return None
    keep = min(min(w.size for w in wide), min(b.size for b in band))
    if report is not None:
        report.setdefault("raw_rms", []).extend(raw_rms)
        report.setdefault("line_rms", []).extend(line_rms)
    return (np.vstack([w[:keep] for w in wide]),
            np.vstack([w[:keep] for w in wide_n]),
            np.vstack([b[:keep] for b in band]), anchor, fs_out)


def pick_peak(trace, t_ms, mode="nearest", frac=0.25):
    """Which maximum of mean|CSD| the stamp should move to.

    "argmax" is the whole window's largest. It is winner-take-all: a stamp
    whose own event is real but whose neighbour 60 ms away is bigger gets
    moved onto the neighbour, and the event that was curated is abandoned.

    "nearest" takes the local maximum CLOSEST TO THE STAMP among those with
    real prominence. That is what a refinement means: the curated time is an
    assertion about WHICH event, and the measurement only gets to correct
    WHEN. It is also what Braces does, for the same reason.

    The prominence floor is a quarter of the window's range, which keeps the
    pick off the ripples in the baseline without needing a noise model.
    """
    if mode == "argmax":
        return int(np.argmax(trace))
    span = float(np.nanmax(trace) - np.nanmin(trace))
    pk, _ = find_peaks(trace, prominence=max(span * frac, 1e-12))
    if pk.size == 0:
        return int(np.argmax(trace))
    return int(pk[int(np.argmin(np.abs(t_ms[pk])))])


def read(session, channels, stamps, p, bad=None, job=None, stop=None):
    """Every event's window, read once, in three filterings.

    READ IN MERGED SPANS, NOT ONE WINDOW PER STAMP. `braces.spans` is what
    makes this minutes rather than an hour: a dentate spike set is a thousand
    stamps scattered through an hour of recording, and the stretches that can
    possibly matter are the hundred and fifty milliseconds around each one --
    about seven per cent of the file. Stamps in a burst share one read, which
    also gives the filter a longer run to settle in, for free.

    Returns a dict:
        rows          per event: n, stamp_s, refined_s, offset_ms, idx,
                      peak_uv_mm2, label, by
        sur           {"raw"|"notch"|"band": [nEvents x nCh x nSamp]}
        nums          the contact numbers, in probe order
        bad           what the amplitude screen found, {number: why}
        mains_uv      median per-contact 60 Hz rms
        wideband_uv   median per-contact broadband rms
        fs            the rate the windows are at
        spacing_um    the pitch the CSD will be taken at
    """
    if not stamps:
        raise DsPcaError("That set has no events to classify.")
    if p.spacing is None:
        p.spacing = spacing_for(p.probe)

    bad = dict(bad or {})
    reach_ms = p.window_ms + p.surround_ms
    runs = braces.spans([float(e["t"]) for e in stamps],
                        window_ms=reach_ms, pad_s=p.pad)
    if job:
        job.begin("ds pca read", of=len(runs), unit="windows")

    half = p.window_ms / 1000.0
    sur_s = p.surround_ms / 1000.0
    keys = ("raw", "notch", "band")
    out_rows, surrounds = [], {k: [] for k in keys}
    report, fs_out, missed = {}, None, []

    # Every stamp keeps its position in the set, so the rows that come back
    # line up with the bank's own order however the spans were merged.
    by_time = sorted(enumerate(stamps), key=lambda kv: float(kv[1]["t"]))
    at = 0

    for k, (a, b) in enumerate(runs):
        # STOPPING AND COUNTING ARE TWO DIFFERENT JOBS.
        #
        # A batch owns the progress bar -- it counts recordings, and the
        # read inside it counts windows -- so the read cannot be handed
        # the batch's job without rescaling the bar out from under it.
        # It was therefore handed nothing at all, and nothing at all is
        # also nothing to ask "have I been cancelled". Pressing Stop did
        # nothing until the recording in flight had finished, which on a
        # long one is minutes and reads as a button that does not work.
        #
        # `stop` is that question on its own, with no progress attached.
        if stop:
            stop()
        if job:
            job.check()
            job.tick("ds pca read", k)
        mine = []
        while at < len(by_time) and float(by_time[at][1]["t"]) <= b - p.pad:
            mine.append(by_time[at])
            at += 1
        if not mine:
            continue
        got = _read_span(session, channels, a, b, p, report)
        if not got:
            missed.extend(i for i, _e in mine)
            continue
        wide, wide_n, band, anchor, fs = got
        fs_out = fs
        wide = braces.repair(wide, channels, bad)
        wide_n = braces.repair(wide_n, channels, bad)
        band = braces.repair(band, channels, bad)

        # The refinement measurement: BARRY's derivative, not Toothy's. This
        # is the same signed CSD Braces aligns on, so a stamp that has been
        # through step three is already sitting on the peak this would find.
        cs = braces.csd_of(band, p.spec())
        tt_all = anchor + np.arange(cs.shape[1]) / fs

        n_sur = int(round(sur_s * fs))
        for idx, e in mine:
            t = float(e["t"])
            tt = tt_all - t
            inside = np.abs(tt) <= half + 0.5 / fs
            if inside.sum() < 8:
                missed.append(idx)
                continue
            trace = np.abs(cs[:, inside]).mean(axis=0)
            t_ms = tt[inside] * 1000.0
            if p.refine == "off":
                # The stamp is the answer. Still measure the trace at it, so
                # `peak_uv_mm2` means the same thing either way and a run
                # with refinement off is not a run with a column missing.
                j = int(np.argmin(np.abs(t_ms)))
            else:
                j = pick_peak(trace, t_ms, p.refine)
            off_ms = float(t_ms[j])
            t_ref = t + off_ms / 1000.0

            i_ref = int(round((t_ref - anchor) * fs))
            if i_ref - n_sur < 0 or i_ref + n_sur + 1 > wide.shape[1]:
                missed.append(idx)
                continue
            for key, w in (("raw", wide), ("notch", wide_n), ("band", band)):
                surrounds[key].append(
                    w[:, i_ref - n_sur:i_ref + n_sur + 1].copy())
            out_rows.append({
                "i": idx, "n": idx + 1, "stamp_s": t, "refined_s": t_ref,
                "offset_ms": off_ms,
                "idx": int(round(t_ref * p.lfp_fs)),
                "peak_uv_mm2": float(trace[j]),
                "label": e.get("label") or "",
                "by": e.get("by") or "",
            })

    if not out_rows:
        raise DsPcaError(
            "None of those %d stamp(s) could be read -- every window was "
            "past the end of the recording, inside a gap, or too short to "
            "measure." % len(stamps))

    # Back into the set's own order. The spans were merged and walked in time
    # order, which is the same order for a bank entry (`add` sorts by start)
    # -- but that is a property of the caller, not of this function, and a
    # classification silently permuted against its stamps is the kind of
    # wrong that looks right.
    order = np.argsort([r["i"] for r in out_rows])
    out_rows = [out_rows[i] for i in order]
    sur = {k: np.array([surrounds[k][i] for i in order]) for k in keys}

    raw_rms = report.get("raw_rms") or [0.0]
    line_rms = report.get("line_rms") or [0.0]
    runs, _probe = geometry(p.probe, channels)
    return {
        "rows": out_rows,
        "sur": sur,
        "nums": [int(c["number"]) for c in channels],
        "bad": bad,
        "missed": sorted(set(missed)),
        "mains_uv": float(np.median(line_rms)),
        "wideband_uv": float(np.median(raw_rms)),
        "fs": float(fs_out or p.lfp_fs),
        "probe": p.probe,
        "spacing_um": float(p.spacing),
        "surround_ms": float(p.surround_ms),
        # Carried with the arrays rather than recomputed at fit time: the
        # columns are a fact about what was read, and a fit that disagreed
        # with its own read about where a column ends would be the one bug
        # this whole check exists to prevent.
        "runs": [{"id": r["id"], "label": r["label"], "rows": r["rows"],
                  "numbers": r["numbers"]} for r in runs],
    }


# --------------------------------------------------------------------------
# Screening, and where the box goes when nobody has drawn one
# --------------------------------------------------------------------------
def csd_screen(surrounds, channels, p, ratio=4.0, known=(), half=4,
               excess_frac=0.5):
    """Contacts a CSD cannot be run over, judged on the CSD and not the LFP.

    THIS EXISTS BECAUSE THE FIRST VERSION OF THIS ANALYSIS CLASSIFIED ONE BAD
    WIRE. An amplitude screen (`braces.screen`) asks whether a contact is
    dead or railing, and on M1ptens2oct2 it passes CSC47-53 -- their RMS is
    within half a decibel of the median. But a second spatial difference does
    not care about a contact's amplitude, it cares about how far that contact
    sits from the line through its neighbours, and by that measure those
    contacts are three to four times worse than the rest of the shank.

    What that did: every feature vector is min-max normalized per event, so
    one contact with a large offset becomes the minimum or the maximum of
    EVERY column. PC1 then separates events by the sign of that one contact,
    K-means cuts the result in half, and two beautifully separated clusters
    come out that have nothing to do with dentate spikes -- the class-mean
    CSD is a stripe just as strong 50 ms away from the event as at it. A
    clean-looking answer to the wrong question.

    The screen is on the BASELINE CSD: how big each contact's CSD is at the
    edges of the event window, where by construction there is no spike.

    AGAINST ITS NEIGHBOURS, NOT AGAINST THE PROBE. The rule used to be "more
    than 4x the median baseline CSD of the whole shank". That works on
    M1ptens2oct2. On M2ctls3jan23 it destroys the data: that recording has
    genuinely large signals over CSC25-42, so the whole-probe median is set
    by the quiet half and the screen interpolated away the dentate spike
    itself -- the event was the anomaly.

    What separates the two cases is not how big the baseline is, it is
    whether the contact carries an EVENT. A bad wire is loud all the time; a
    real hilar contact is quiet between events and large at them. So the gate
    on every rule below is the event-triggered excess. A contact carrying
    real event-locked signal is never screened out however loud it is, which
    is what stops the screen deleting the thing it was pointed at.

    `known` contacts are left out of every median, so that a bad block cannot
    raise the bar that would have caught it.
    """
    filt = toothy_csd(surrounds.mean(axis=0), p.spacing, p)[1]
    t = np.linspace(-p.surround_ms, p.surround_ms, filt.shape[1])
    i0 = int(np.argmin(np.abs(t)))
    edge = np.abs(t) > p.surround_ms * 0.7
    base = np.abs(filt[:, edge]).mean(axis=1)
    excess = np.clip(np.abs(filt[:, i0]) - base, 0.0, None)
    skip = {int(n) for n in known}
    n = len(channels)
    live = [base[j] for j in range(n)
            if base[j] > 0 and int(channels[j]["number"]) not in skip]
    world = float(np.median(live)) if len(live) >= 4 else 0.0

    out = {}
    for i, c in enumerate(channels):
        if base[i] <= 0 or int(c["number"]) in skip:
            continue
        if excess[i] >= excess_frac * base[i]:
            continue                 # it carries an event; leave it alone
        near = [base[j] for j in range(max(0, i - half), min(n, i + half + 1))
                if j != i and base[j] > 0
                and int(channels[j]["number"]) not in skip]
        local = float(np.median(near)) if len(near) >= 3 else 0.0
        why = None
        if world > 0 and base[i] > ratio * world:
            why = "%.1fx the probe median" % (base[i] / world)
        elif local > 0 and base[i] > ratio * local:
            why = "%.1fx its neighbours" % (base[i] / local)
        if why:
            out[int(c["number"])] = (
                "baseline CSD %.3g, %s, and almost nothing at the stamp -- "
                "a second difference amplifies it" % (base[i], why))
    return out, base


def depth_band(surrounds, p, channels=None, bad=None, runs=None):
    """Which contacts the CSD runs over, when nobody has drawn the box.

    Toothy has a person select this window on screen, and the choice is not
    cosmetic: the features ARE these contacts, so a window centred on the
    wrong depth is a PCA of the wrong thing.

    Scored on the EVENT-TRIGGERED TEMPLATE against its own baseline, and that
    is the whole point. The first version of this scored contacts by mean
    |CSD| over the window, which is a question about magnitude -- and on
    M1ptens2oct2 the largest magnitude is CSC47-51, a run of noisy contacts
    whose CSD is just as large 40 ms away from the event as at it. It chose
    CSC30-53, put the "sink" on a bad wire, and the clustering that came out
    of it was about ongoing noise.

    Averaging over events kills whatever is not time-locked; subtracting the
    window's own edges kills whatever is large but constant. What is left is
    how much each contact MOVES when the dentate spike happens, which is the
    thing worth building features from.
    """
    filt = toothy_csd(surrounds.mean(axis=0), p.spacing, p)[1]
    t = np.linspace(-p.surround_ms, p.surround_ms, filt.shape[1])
    i0 = int(np.argmin(np.abs(t)))
    edge = np.abs(t) > p.surround_ms * 0.7
    score = np.abs(filt[:, i0]) - np.abs(filt[:, edge]).mean(axis=1)
    score = np.clip(score, 0.0, None)
    # A repaired contact is the average of its neighbours, so it scores like
    # them and carries nothing of its own. Left in, a run of them pulls the
    # window onto the part of the shank with the least real information in
    # it; scored at zero, the window has to earn its place on live contacts.
    if channels is not None and bad:
        for i, c in enumerate(channels):
            if int(c["number"]) in bad:
                score[i] = 0.0

    # Searched WITHIN a column, not across the channel list. A contiguous run
    # of rows is only contiguous on the probe when the probe is a line; on an
    # H10-D the best-scoring sixteen consecutive rows span every column, and
    # the opening view would be a CSD of nothing. Each column is scored on
    # its own and the best window over any of them wins.
    best, span_want = None, max(3, int(p.csd_span))
    for run in (runs or [{"rows": list(range(filt.shape[0]))}]):
        rows = [i for i in run["rows"] if i < filt.shape[0]]
        if len(rows) < 3:
            continue
        span = min(span_want, len(rows))
        sub = np.array([score[i] for i in rows], dtype=np.float64)
        tot = np.convolve(sub, np.ones(span), "valid")
        at = int(np.argmax(tot))
        if best is None or float(tot[at]) > best[0]:
            best = (float(tot[at]), rows[at:at + span])
    if best is None:
        raise DsPcaError(
            "No column on this probe has three usable contacts, so there is "
            "nowhere to put the depth window.")
    return best[1]


# --------------------------------------------------------------------------
# Which class is DS1
# --------------------------------------------------------------------------
def source_peaks(mu, want=2):
    """The most prominent SOURCE peaks of one class's mean depth profile.

    Returns [(row, value, prominence), ...], most prominent first, at most
    `want` of them.

    WHY SOURCES RATHER THAN THE SINK. Toothy orders DS1/DS2 by `argmin` of
    the profile -- the deepest negative. That is one number off a curve that
    on a wide band has three or four excursions, and it answers the wrong
    question when two of them are close in size: the deepest dip is not
    necessarily the dip that belongs to the event.

    A dentate spike's sink is bracketed by sources, and a source peak is the
    better landmark for two reasons. It is a peak, so PROMINENCE is defined
    for it -- how far it stands above the surrounding profile, which measures
    how much of a feature it really is rather than just how large the number
    got. And ranking by prominence rather than by height means a broad
    shallow shoulder loses to a sharp local peak, which is what the eye does
    when it picks a landmark off the same curve.
    """
    mu = np.asarray(mu, dtype=np.float64)
    if mu.size < 3:
        return []
    idx, props = find_peaks(mu, prominence=0.0)
    if idx.size == 0:
        return []
    proms = props["prominences"]
    # Sources are positive CSD. If nothing is positive the profile has no
    # source in this window at all, and every local maximum is a shoulder on
    # the way out of a sink -- worth ranking anyway rather than returning
    # nothing, so the caller still gets a landmark.
    pos = mu[idx] > 0
    if pos.any():
        idx, proms = idx[pos], proms[pos]
    order = np.argsort(proms)[::-1][:int(want)]
    return [(int(idx[i]), float(mu[idx[i]]), float(proms[i])) for i in order]


def tort_main_sink(mu):
    """tortlab's landmark: the main sink BEFORE the main source.

    `dentatespike.classification.CSDbC`, in the tortlab reference:

        mainsink[ci] = np.argmin(meancsd[:np.argmax(meancsd)])

    Find the largest SOURCE on the profile, then take the deepest sink from
    the contacts ABOVE it only. That one restriction is the whole idea, and
    it is better than either of the other two rules here.

    Toothy's plain `argmin` asks "where is the deepest dip anywhere on the
    shank", which on a probe crossing both blades of the dentate finds
    whichever blade happened to be louder -- a fact about electrode
    placement, not about the event. Anchoring the sink to its own source
    picks the dipole out of the profile first and then measures inside it, so
    the answer is a property of the current, not of the window.

    Returns (row, why) -- `why` names the source it anchored to, so the
    summary can show the pair rather than one number.
    """
    mu = np.asarray(mu, dtype=np.float64)
    if mu.size < 2:
        return 0, None
    src = int(np.argmax(mu))
    if src < 1:
        return int(np.argmin(mu)), None     # no contact above the source
    return int(np.argmin(mu[:src])), src


def class_marker(mu, rule="tort"):
    """The depth that stands for a class when DS1/DS2 are ordered.

    `tort`    -- the main sink above the main source (tortlab CSDbC).
    `sink`    -- Toothy's rule, the most negative point anywhere.
    `sources` -- the most prominent source peak.
    `anatomy` -- handled by the caller, which has the layer labels; it falls
                 back to `tort` here so this function is still total.

    Returns (row, extra) where `extra` is whatever the rule looked at, so a
    caller can show its working instead of asserting a verdict.
    """
    mu = np.asarray(mu, dtype=np.float64)
    if rule == "sink":
        return int(np.argmin(mu)), []
    if rule == "sources":
        peaks = source_peaks(mu, want=2)
        if not peaks:
            return int(np.argmin(mu)), []   # no peak at all; fall back
        return peaks[0][0], peaks
    row, src = tort_main_sink(mu)
    return row, src


def tort_order(profiles):
    """tortlab's class ordering, collision fallback included.

    `np.argsort(mainsink)` puts the shallower main sink first -- DS1. And if
    every class lands on the SAME contact, CSDbC redoes the whole thing on
    the upside-down profile, because a probe inserted the other way round
    makes "before the main source" point the wrong way. Reproduced, because
    on a probe crossing both blades it is not a rare case.

    Returns (rows, flipped).
    """
    rows = [tort_main_sink(mu)[0] for mu in profiles]
    if len(rows) > 1 and len(set(rows)) == 1:
        n = len(profiles[0])
        rows = [n - 1 - tort_main_sink(mu[::-1])[0] for mu in profiles]
        return rows, True
    return rows, False


def sink_channel(filt_csd, nums, rows):
    """Which contact the mean CSD of these events dips at."""
    if len(rows) == 0:
        return None
    return int(nums[int(np.argmin(np.nanmean(filt_csd[:, rows], axis=1)))])


def anatomy_rows(nums, layers, want=("hil", "dg_gcl1", "dg_gcl2")):
    """The row indices of the contacts labelled as the hilus and its blades.

    The three other rules all ask "which class is shallower", which is a
    question about the probe rather than about the brain: it gives the right
    answer only when the shank went in the usual way up. Where somebody has
    actually said which contact is the hilus -- StrataScope writes exactly
    that, per recording -- the question can be asked properly, and the answer
    survives a probe inserted the other way round.

    `layers` is {contact number: region id}, as `layers.Layers.get` stores.
    Returns the row indices, in the order `nums` is in, or [] when this
    recording has no labels.
    """
    if not layers:
        return []
    keep = set(want)
    return [i for i, n in enumerate(nums)
            if str(layers.get(str(n), layers.get(int(n), ""))) in keep]


# --------------------------------------------------------------------------
# The cheap half
# --------------------------------------------------------------------------
def rows_for_box(nums, p, runs=None):
    """The box, from contact numbers to row indices into what was read.

    Held as numbers rather than indices because a run is saved and reopened,
    and an index into a channel list is only meaningful against the list it
    was taken from -- a recording read with `even_only` on, or a probe column
    selected, and row 12 is a different wire.
    """
    if p.sel_lo is None or p.sel_hi is None:
        return None
    lo, hi = int(p.sel_lo), int(p.sel_hi)
    if lo > hi:
        lo, hi = hi, lo
    rows = [i for i, n in enumerate(nums) if lo <= int(n) <= hi]
    if len(rows) >= 3:
        return rows

    # A CSD is a second derivative across depth; three contacts is the floor.
    # Widened rather than refused, because a drag that lands on two contacts
    # is a person asking for the thinnest box there is -- but widened ALONG
    # THE COLUMN the box started in, since the next row in the channel list
    # is not the next contact down the shank on every probe.
    here = rows[0] if rows else 0
    for run in (runs or [{"rows": list(range(len(nums)))}]):
        seq = list(run["rows"])
        if here not in seq or len(seq) < 3:
            continue
        at = seq.index(here)
        at = max(0, min(at, len(seq) - 3))
        return seq[at:at + 3]
    return list(range(0, min(3, len(nums))))


def samples_for_box(n_t, p):
    """The time half of the box, from milliseconds to sample indices."""
    tw = np.linspace(-p.surround_ms, p.surround_ms, n_t)
    centre = n_t // 2
    if p.t_lo_ms is None or p.t_hi_ms is None:
        return centre, centre + 1, tw          # Toothy: one sample, at the stamp
    lo = int(np.argmin(np.abs(tw - float(p.t_lo_ms))))
    hi = int(np.argmin(np.abs(tw - float(p.t_hi_ms))))
    if lo > hi:
        lo, hi = hi, lo
    return lo, max(lo + 1, hi + 1), tw


def fit(got, p, layers=None):
    """Screen, CSD, features, PCA, K-means, and the DS1/DS2 call.

    Everything here is milliseconds. `got` is what `read` returned, which is
    the thing that took minutes; nothing below touches the disk, which is why
    the box can be dragged live.
    """
    if not HAVE_SKLEARN:
        raise DsPcaError(NO_SKLEARN)
    if p.spacing is None:
        p.spacing = float(got.get("spacing_um") or probes.CONTACT_PITCH_UM)
    p.surround_ms = float(got.get("surround_ms") or p.surround_ms)

    nums = [int(n) for n in got["nums"]]
    chans = [{"number": n} for n in nums]
    sur = got["sur"]["notch" if p.notch else "raw"]
    sur_band = got["sur"]["band"]

    # Two screens and whatever a person marked, all repaired the same way.
    #
    # Marking a contact bad does NOT change the refinement: those stamps were
    # timed during the read, against the read-time bad list. One dead wire
    # among sixty-four moves a mean over depth by almost nothing, so this is
    # a real limitation rather than a serious one -- and with `refine` off,
    # which is the default in the bundle, it does not arise at all.
    bad = dict(got.get("bad") or {})
    manual = dict(getattr(p, "manual_bad", None) or {})
    bad.update(manual)
    if manual:
        sur = np.array([braces.repair(s, chans, bad) for s in sur])
        sur_band = np.array([braces.repair(s, chans, bad) for s in sur_band])
    if p.screen:
        for _ in range(5):
            cbad, _b = csd_screen(sur, chans, p, p.csd_bad_x, known=bad)
            cbad = {k: v for k, v in cbad.items() if k not in bad}
            if not cbad:
                break
            bad.update(cbad)
            sur = np.array([braces.repair(s, chans, bad) for s in sur])
            sur_band = np.array([braces.repair(s, chans, bad)
                                 for s in sur_band])

    # The picture: the whole shank's CSD of the band-limited trace.
    disp = stack_csd(sur_band, p, p.spacing)

    # WHERE A CSD MAY BE TAKEN, before one is taken.
    #
    # On a single linear array this is the whole shank and the check is free.
    # On an H10-D it is one of six interleaved columns, and a box spanning
    # CSC26-41 -- which looks entirely reasonable and is what the standalone
    # version opens with -- crosses all six. Refused rather than warned
    # about: the resulting profile has a sink in it, the sink has a contact
    # number, and nothing on screen would say it was arithmetic between
    # contacts 200 um apart in the other direction.
    # Reused from the read where the probe has not changed, re-derived where
    # it has. Somebody correcting an H10-D that was read as a linear array is
    # exactly the person who needs this check, and making them wait for a
    # re-read to get it would mean the wrong answer stays on screen for the
    # minutes it takes -- while the correction they just made says it is
    # wrong.
    want = p.probe if p.probe is not None else got.get("probe")
    runs = ([dict(r, rows=[int(i) for i in r["rows"]])
             for r in (got.get("runs") or [])]
            if want == got.get("probe") else [])
    if not runs:
        runs, _probe = geometry(want, chans)

    sel = rows_for_box(nums, p, runs)
    if sel is None:
        sel = depth_band(sur, p, chans, bad, runs=runs)
    run = run_for_box(runs, sel)
    if run is None:
        raise DsPcaError(
            "CSC%d-%d crosses more than one of this probe's columns, and a "
            "CSD across columns subtracts contacts that are not neighbours. "
            "Choose a box inside one of: %s."
            % (min(nums[i] for i in sel), max(nums[i] for i in sel),
               "; ".join("%s (CSC%d-%d)"
                         % (r["label"], min(r["numbers"]), max(r["numbers"]))
                         for r in runs)))
    t0, t1, tw = samples_for_box(sur.shape[2], p)

    # The measurement: CSD computed WITHIN the chosen contacts, Toothy-style.
    feat_csd = stack_csd(sur[:, sel, :], p, p.spacing)[:, :, t0:t1]

    # THE GAP IS MEASURED ON THE 5-100 Hz, MAINS-OUT SIGNAL.
    #
    # Not on `feat_csd`, which is broadband because that is Toothy's
    # method for the FEATURE VECTOR and the method is the thing being
    # ported. The gap is not part of that vector's heritage: it is a
    # question about GEOMETRY -- which two contacts the sinks sit on --
    # and the answer to it is found by peak-picking a depth profile.
    #
    # 60 Hz sits INSIDE the 5-100 Hz band and it survives a CSD: it is
    # common-mode, but a second difference of a common-mode line is not
    # zero on a real probe. A mains ripple across depth adds local
    # minima, and `find_peaks` cannot tell one of those from a laminar
    # sink -- so on the broadband signal the "two main sinks" could be
    # two crests of the mains. This is the same reason the refinement is
    # always notched whatever the features do; see `_read_span`.
    #
    # `sur["band"]` is built from the NOTCHED trace and then filtered to
    # the DS band, so it is both at once.
    gap_csd = stack_csd(sur_band[:, sel, :], p, p.spacing)[:, :, t0:t1]
    norm = normalize_block(feat_csd, p.features, p.dead)
    X_pca = norm.reshape(norm.shape[0], -1)

    k = int(p.nclasses)
    if k > X_pca.shape[0]:
        raise DsPcaError(
            "%d classes out of %d event(s) is more clusters than points."
            % (k, X_pca.shape[0]))

    # The sink gap, once. Both methods that use it use this.
    gap_col, gap_contacts, gap_rows = sink_gap(gap_csd, p.min_sep)
    X_gap = np.hstack([X_pca, gap_col * float(p.gap_weight)])

    # ALL THREE, EVERY FIT.
    #
    # A PCA over a few dozen columns and a few hundred events is
    # milliseconds, so there is nothing saved by computing only the one
    # that happens to be chosen -- and having all three is the only way to
    # show what the extra column did, or whether the gap was carrying the
    # split at all. The third has no PCA in it: one number per event, and
    # k-means partitions that line directly, so the boundary is a
    # threshold that can be read off the axis and quoted.
    def _pca_fit(Xv):
        pv = PCA(n_components=2)
        return pv, pv.fit_transform(Xv)

    runs = {}
    pca_off, coords_off = _pca_fit(X_pca)
    runs["pca"] = {"pca": pca_off, "coords": coords_off, "X": X_pca,
                   "labels": KMeans(n_clusters=k, n_init="auto",
                                    random_state=p.seed)
                   .fit(coords_off).labels_,
                   "kind": "pca"}
    pca_on, coords_on = _pca_fit(X_gap)
    runs["pca_gap"] = {"pca": pca_on, "coords": coords_on, "X": X_gap,
                       "labels": KMeans(n_clusters=k, n_init="auto",
                                        random_state=p.seed)
                       .fit(coords_on).labels_,
                       "kind": "pca"}
    kd = KMeans(n_clusters=k, n_init="auto", random_state=p.seed).fit(gap_col)
    km_centres = sorted(float(c) for c in kd.cluster_centers_[:, 0])
    if p.delta_cut:
        # A HAND-PLACED THRESHOLD BEATS A FITTED ONE when you can see the
        # distribution. k-means minimises within-cluster variance, which
        # on a lopsided one-dimensional spread puts the boundary where
        # the arithmetic wants it rather than where the gap in the data
        # is. Here the axis has units and the events are on screen along
        # it, so a person can simply say where the line goes -- and the
        # counts, the profiles and the DS1/DS2 call all recompute from
        # that exactly as they would from k-means.
        cuts = list(p.delta_cut)
        labels = np.digitize(gap_col[:, 0], cuts)
        centres = None
    else:
        labels = kd.labels_
        centres = km_centres
        cuts = [(km_centres[i] + km_centres[i + 1]) / 2.0
                for i in range(len(km_centres) - 1)]
    runs["delta"] = {
        "pca": None, "coords": gap_col, "X": gap_col,
        "labels": labels, "kind": "delta",
        "centres": centres,
        # Where k-means WOULD have put them, kept even when a hand has
        # overridden it: "you moved it from 0.31 to 0.44" is the useful
        # sentence, and it needs both numbers.
        "km_centres": km_centres,
        "bounds": cuts,
        "manual": bool(p.delta_cut),
    }

    use = runs[p.method]
    pca, coords, X = use["pca"], use["coords"], use["X"]

    class _Km(object):
        pass
    km = _Km()
    km.labels_ = use["labels"]
    km.cluster_centers_ = (kd.cluster_centers_ if p.method == "delta"
                           else np.asarray(
                               [coords[use["labels"] == c].mean(axis=0)
                                if (use["labels"] == c).any()
                                else np.zeros(coords.shape[1])
                                for c in range(k)]))

    # EVERY PICTURE COMES OFF THE SAME SIGNAL, and it is not the features.
    #
    # The class-average profile and the class-average rasters are both the
    # band-limited, mains-out CSD over the selected block. They used to
    # disagree -- the rasters band-limited, the profile broadband -- which
    # meant the "sink CSC30" in the profile legend was not necessarily the
    # sink visible in the heatmap beside it. Two different answers to the
    # same question, a few centimetres apart.
    #
    # The features stay broadband, because that is Toothy's method and the
    # method is the thing being ported. So: the measurement is broadband,
    # everything drawn is band-limited, and the split is on purpose.
    prof = disp[:, sel, t0:t1].mean(axis=2)      # [nEvents x span]
    ns = [nums[i] for i in sel]

    # The same profile down the WHOLE shank, for drawing and nothing else.
    #
    # The measurement stays on the selected band and has to: every ordering
    # rule is scored on `prof`, and widening what is measured would change
    # the answer rather than the picture. But a picture cropped to the band
    # cannot show whether the band is in the right place, which is the one
    # question somebody brings to it -- so the panel draws all of it and
    # shades what is outside. Same `t0:t1`, so the two are the same
    # quantity over a different set of contacts.
    prof_all = disp[:, :, t0:t1].mean(axis=2)

    # Classes renumbered by their landmark depth, which generalizes Toothy's
    # DS1/DS2 rule to any number: DS1 is the shallowest. Scored on `prof`, so
    # the naming agrees with what is on screen -- Toothy scores it on its
    # broadband features instead, and on this rig the two can disagree
    # because the mains moves the argmin. A label is a naming convention; one
    # you can check against the picture is the better convention.
    mus = {c: np.nanmean(prof[km.labels_ == c], axis=0)
           for c in range(k) if (km.labels_ == c).any()}
    live = sorted(mus)
    upside = False
    if p.rule == "tort":
        rows_, upside = tort_order([mus[c] for c in live])
        marker = dict(zip(live, rows_))
    elif p.rule == "anatomy":
        marker = _anatomy_marker(mus, ns, layers)
    else:
        marker = {c: class_marker(mu, p.rule)[0] for c, mu in mus.items()}
    order = sorted(range(k), key=lambda c: marker.get(c, 10 ** 6))
    if p.flip:
        order = order[::-1]          # DS1 <-> DSk, by hand
    remap = {c: i + 1 for i, c in enumerate(order)}
    types = np.array([remap[x] for x in km.labels_])

    decide = _working(types, prof, ns, marker, km.labels_, k, p, layers)

    # AND THE SAME NUMBERING FOR ALL THREE.
    #
    # Run through the identical rule, so "DS1" means the shallower class
    # in each of them and the three can be put side by side. Numbering
    # them by whatever k-means happened to return would make the
    # comparison meaningless in exactly the way it exists to avoid.
    variants = {}
    for name, r in runs.items():
        lab = np.asarray(r["labels"])
        mus_v = {c: np.nanmean(prof[lab == c], axis=0)
                 for c in range(k) if (lab == c).any()}
        live_v = sorted(mus_v)
        if p.rule == "tort":
            rows_v, _up = tort_order([mus_v[c] for c in live_v])
            mark_v = dict(zip(live_v, rows_v))
        elif p.rule == "anatomy":
            mark_v = _anatomy_marker(mus_v, ns, layers)
        else:
            mark_v = {c: class_marker(mu, p.rule)[0]
                      for c, mu in mus_v.items()}
        ord_v = sorted(range(k), key=lambda c: mark_v.get(c, 10 ** 6))
        if p.flip:
            ord_v = ord_v[::-1]
        remap_v = {c: i + 1 for i, c in enumerate(ord_v)}
        types_v = np.array([remap_v[x] for x in lab])
        variants[name] = {
            "method": name,
            "name": METHOD_NAMES.get(name, name),
            "kind": r["kind"],
            "n_features": int(np.asarray(r["X"]).shape[1]),
            "types": types_v,
            "decide": _working(types_v, prof, ns, mark_v, lab, k, p, layers),
            "coords": np.asarray(r["coords"]),
            "explained": ([float(v) for v in r["pca"]
                           .explained_variance_ratio_]
                          if r["pca"] is not None else []),
            "centres": r.get("centres"),
            "km_centres": r.get("km_centres"),
            "bounds": r.get("bounds"),
            "manual": bool(r.get("manual")),
            "active": name == p.method,
        }

    return {
        "disp": disp, "feat": feat_csd, "norm": norm,
        # What the gap was measured on, so the marks drawn for it come
        # off the same array the number did.
        "gap_csd": gap_csd,
        "gap_signal": "5-%g Hz, 60 Hz notched" % p.band[1],
        "coords": coords, "pca": pca, "types": types, "k": k,
        # For `under_hood`: where k-means put its centres, and how its
        # labels were renumbered into DS1..DSk. Both are thrown away by
        # every other caller, and both are needed to show the step rather
        # than assert it.
        "km_centres": km.cluster_centers_,
        "km_to_type": dict(remap),
        # The three, all numbered by the same rule, so they compare.
        "variants": variants,
        "method": p.method,
        "method_name": METHOD_NAMES.get(p.method, p.method),
        # The gap itself, which two of the three are built on and the
        # panels draw: the 0-1 scale, the raw contact distance, and the
        # two rows it was measured between.
        "gap": [float(v) for v in gap_col[:, 0]],
        "gap_contacts": [int(v) for v in gap_contacts],
        "gap_rows": [[int(a), int(b)] for a, b in gap_rows],
        "min_sep": int(p.min_sep),
        "gap_weight": float(p.gap_weight),
        # Which contacts were taken out by hand, on top of whatever the
        # recording is marked with. `bad` above is all of them together.
        "manual_bad": sorted(int(n) for n in manual),
        "bad": bad, "prof": prof, "decide": decide,
        "sel": sel, "nums_sel": ns, "t0": t0, "t1": t1, "tw": tw,
        "prof_all": prof_all, "nums_all": nums,
        "n_features": int(X.shape[1]),
        "tort_upside": upside,
        # Empty under `delta`, which has no components to explain
        # anything with: one number per event is the whole feature
        # space, and there is nothing to rotate.
        "explained": ([float(v) for v in pca.explained_variance_ratio_]
                      if pca is not None else []),
        "spacing_um": float(p.spacing),
    }


def _anatomy_marker(mus, ns, layers):
    """Order the classes by where their sink sits relative to the hilus.

    The class whose main sink is nearest the labelled hilus is the deeper
    one; everything above it is shallower. Expressed as a sortable number so
    it drops into the same `marker` slot the other three rules fill -- the
    distance in contacts from the hilus, signed, so "above" sorts first.

    Falls back to `tort` for any class this cannot place, and the caller is
    told which happened through `decide[...]["rule"]`.
    """
    rows = anatomy_rows(ns, layers)
    if not rows:
        return {c: tort_main_sink(mu)[0] for c, mu in mus.items()}
    centre = float(np.mean(rows))
    out = {}
    for c, mu in mus.items():
        row = tort_main_sink(mu)[0]
        # Ranked on the signed distance, not the absolute one: two classes
        # either side of the hilus are a real and common arrangement, and
        # |distance| would call them the same depth.
        out[c] = row - centre
    return out


def _working(types, prof, ns, marker, labels, k, p, layers):
    """What the rule actually looked at, kept so the panel can show it.

    A rule stated in a legend reads as a fact about anatomy, which it is not:
    it is one argmin off a curve that often has three or four excursions. The
    local minima are counted here so the panel can say when the single number
    is thin.
    """
    out = []
    for c in range(1, k + 1):
        rr = np.where(types == c)[0]
        if rr.size == 0:
            out.append({"c": c, "n": 0})
            continue
        mu = np.nanmean(prof[rr], axis=0)
        j, peaks = class_marker(mu, "tort" if p.rule == "anatomy" else p.rule)
        if p.rule in ("tort", "anatomy"):
            got = marker.get(int(labels[rr[0]]))
            if got is not None and p.rule == "tort":
                j = int(got)
        lows = [i for i in range(1, len(mu) - 1)
                if mu[i] < mu[i - 1] and mu[i] < mu[i + 1] and mu[i] < 0]
        j = int(np.clip(j, 0, len(ns) - 1))
        out.append({
            "c": c, "n": int(rr.size), "row": j, "csc": int(ns[j]),
            "value": float(mu[j]), "rule": p.rule,
            "peaks": (int(peaks) if isinstance(peaks, int) else
                      [[int(ns[r]), float(v), float(pr)]
                       for r, v, pr in (peaks or [])]),
            "sink": int(ns[int(np.argmin(mu))]),
            "lows": [int(ns[i]) for i in lows],
            "mu": [float(v) for v in mu],
        })
    return out


# --------------------------------------------------------------------------
# Keeping a read
# --------------------------------------------------------------------------
# Which parts of a read are arrays. Everything else goes into the same file
# as ONE JSON STRING.
#
# Not as object arrays. `np.savez(..., rows=np.array(rows, dtype=object))`
# pickles them, and a pickle carries the writing NumPy's private module
# paths -- the standalone version's caches were written under NumPy 2 and
# cannot be opened in this tree at all, which raises
# `No module named 'numpy._core'` under 1.24. A cache only one machine can
# read is not a cache, and this one is meant to be shared.
ARRAYS = ("raw", "notch", "band")

_META_KEYS = ("rows", "nums", "bad", "missed", "mains_uv", "wideband_uv",
              "fs", "probe", "spacing_um", "surround_ms", "runs")


def save_read(path, got):
    """File one read. Written beside and moved, so a crash leaves no half."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    meta = {k: got.get(k) for k in _META_KEYS}
    tmp = path + ".part.npz"
    np.savez_compressed(
        tmp, meta=np.array(json.dumps(meta, default=str)),
        **{"sur_" + k: np.asarray(got["sur"][k], dtype=np.float32)
           for k in ARRAYS})
    os.replace(tmp, path)
    return path


def load_read(path):
    """The dict `read` returned, back off the disk."""
    if not os.path.exists(path):
        raise DsPcaError(
            "That read is not on this machine any more. It is a cache, so "
            "nothing is lost -- read the set again.")
    with np.load(path, allow_pickle=False) as z:
        meta = json.loads(str(z["meta"]))
        got = dict(meta)
        got["sur"] = {k: np.asarray(z["sur_" + k], dtype=np.float64)
                      for k in ARRAYS}
    got["bad"] = {int(k): v for k, v in (meta.get("bad") or {}).items()}
    return got


def profiles(res):
    """Each class's mean depth profile and its standard error, for drawing.

    Computed from `res["prof"]` -- the very numbers every ordering rule was
    scored on -- rather than from anything recomputed, so the curve on screen
    and the contact named in the decision panel cannot come from two
    different answers to the same question.
    """
    types = np.asarray(res["types"])
    sel_ns = [int(n) for n in res["nums_sel"]]
    # Drawn down the whole shank, with the band that was MEASURED named
    # separately so the panel can shade the rest rather than crop to it.
    prof = res.get("prof_all")
    ns = [int(n) for n in res.get("nums_all") or []]
    if prof is None or not ns:
        prof, ns = res["prof"], sel_ns
    band = [min(sel_ns), max(sel_ns)] if sel_ns else None
    out = []
    for c in range(1, int(res["k"]) + 1):
        rr = np.where(types == c)[0]
        if rr.size == 0:
            out.append({"c": c, "n": 0, "contacts": ns, "mean": [], "sem": [],
                        "band": band})
            continue
        mu = np.nanmean(prof[rr], axis=0)
        sem = np.nanstd(prof[rr], axis=0) / np.sqrt(rr.size)
        # THE TWO SINKS THIS CLASS'S GAP WAS MEASURED BETWEEN.
        #
        # From `feat` and not from the curve beside it, which is the
        # display CSD: the mark on screen has to be the pair the NUMBER
        # came from, or the panel shows one thing and the feature vector
        # holds another. Reported as contact numbers, so it can be drawn
        # on a full-shank axis without anyone re-deriving the mapping.
        sinks = None
        try:
            # The same array the gap number came off, not `feat`:
            # `feat` is broadband because that is Toothy's feature
            # method, and the gap is measured on the band-limited,
            # mains-out CSD. A mark drawn from the other one would be a
            # different pair of sinks.
            feat = np.asarray(res.get("gap_csd"))
            if not feat.size:
                feat = np.asarray(res.get("feat"))
            if feat.size and sel_ns:
                mu_feat = feat[rr].mean(axis=0).mean(axis=1)
                r1, r2 = two_sinks(mu_feat,
                                   res.get("min_sep") or MIN_SINK_SEP)
                gap = abs(r2 - r1)
                span = len(sel_ns)
                sinks = {
                    "rows": [int(r1), int(r2)],
                    "csc": [int(sel_ns[r1]), int(sel_ns[r2])],
                    "contacts": int(gap),
                    "value": (0.0 if gap < 1 else
                              min(max((gap - 1.0) / max(span - 2.0, 1.0),
                                      0.0), 1.0)),
                }
        except Exception:                                # noqa: BLE001
            sinks = None
        out.append({"c": c, "n": int(rr.size), "contacts": ns,
                    "mean": [float(v) for v in mu],
                    "sem": [float(v) for v in sem],
                    "band": band, "sinks": sinks})
    return out


# --------------------------------------------------------------------------
# The pictures
# --------------------------------------------------------------------------
# Drawn through callbacks rather than by importing `analysis` here, for two
# reasons. `analysis` imports matplotlib, and the whole claim of this module
# is that it does not -- the fidelity check imports it beside a matplotlib
# program and relies on neither pulling the other's backend in. And the
# encoder is the app's, not this tool's: passing it in is what guarantees the
# rasters here are the same picture, from the same colormap and the same
# robust percentile, as the CSD panel in Xplorefinder.
def pictures(got, what, index=None, cmap="jet", gain=None, fit_params=None,
             encode=None, clim_of=None, layers=None):
    """One of the four things this panel draws.

    Everything is the band-limited, mains-out CSD -- the picture, not the
    measurement. See the module docstring: the features stay broadband
    because that is Toothy's method, and the two are never swapped quietly.
    """
    p = fit_params or Params()
    if p.spacing is None:
        p.spacing = float(got.get("spacing_um") or probes.CONTACT_PITCH_UM)
    sur_ms = float(got.get("surround_ms") or SURROUND_MS)
    nums = [int(n) for n in got["nums"]]
    n_t = got["sur"]["band"].shape[2]
    tw = np.linspace(-sur_ms, sur_ms, n_t)
    extent = [float(tw[0]), float(tw[-1])]

    if what == "traces":
        return _picture_traces(got, p, index, tw, nums, gain)

    disp = stack_csd(got["sur"]["band"], p, p.spacing)

    if what in ("shank", "event"):
        if what == "event":
            i = int(index or 0)
            if not 0 <= i < disp.shape[0]:
                raise DsPcaError("There is no event %d in this read." % i)
            mat = disp[i]
            title = "spike %d" % (i + 1)
        else:
            mat = disp.mean(axis=0)
            title = "mean of %d" % disp.shape[0]
        clim = clim_of(mat)

        # THE DEPTH PROFILE OF WHAT THIS RASTER IS SHOWING.
        #
        # A raster is a field and the eye is bad at reading a trough out
        # of one: "where is the sink" is a question about a curve, and
        # the curve is not drawn anywhere. This is that curve, over the
        # SAME time window the features come from -- averaging the whole
        # surround instead would smear a 20 ms event into 100 ms of
        # baseline and flatten the thing being looked for.
        #
        # Whole shank, because that is what the raster spans. The
        # LANDMARKS on it are a different matter: the two sinks are the
        # pair the gap number was measured from, and that is measured
        # inside the selected band on the band-limited, mains-out CSD.
        # So the line is the picture's own signal and the marks are the
        # measurement's, which is the same split the box already has and
        # is stated rather than hidden.
        line = None
        try:
            res_ = fit(got, p, layers=layers)
            t0_, t1_ = res_["t0"], res_["t1"]
            prof_all = mat[:, t0_:t1_].mean(axis=1)
            sel_ns = [int(n) for n in res_["nums_sel"]]
            gsrc = np.asarray(res_.get("gap_csd"))
            if what == "event" and gsrc.size:
                mu_band = gsrc[i].mean(axis=1)
            elif gsrc.size:
                mu_band = gsrc.mean(axis=0).mean(axis=1)
            else:
                mu_band = None
            peaks, sinks = [], None
            if mu_band is not None and sel_ns:
                try:
                    from scipy.signal import find_peaks
                    idx, _pr = find_peaks(-np.asarray(mu_band))
                except Exception:                        # noqa: BLE001
                    idx = []
                peaks = [int(sel_ns[int(r)]) for r in idx
                         if 0 <= int(r) < len(sel_ns)]
                r1, r2 = two_sinks(mu_band, p.min_sep)
                gap = abs(r2 - r1)
                span = len(sel_ns)
                sinks = {
                    "csc": [int(sel_ns[r1]), int(sel_ns[r2])],
                    "contacts": int(gap),
                    "value": (0.0 if gap < 1 else
                              min(max((gap - 1.0) / max(span - 2.0, 1.0),
                                      0.0), 1.0)),
                }
            line = {
                "values": [float(v) for v in prof_all],
                "contacts": nums,
                "window_ms": [float(tw[t0_]),
                              float(tw[max(t0_, t1_ - 1)])],
                "peaks": peaks,
                "sinks": sinks,
                "band": [min(sel_ns), max(sel_ns)] if sel_ns else None,
                "signal": res_.get("gap_signal"),
            }
        except Exception:                                # noqa: BLE001
            line = None

        return {"ok": True, "what": what, "title": title,
                "image": encode(mat, cmap, clim),
                "extent": extent, "clim": [float(clim[0]), float(clim[1])],
                "contacts": nums, "lo": nums[0], "hi": nums[-1],
                "line": line,
                "layers": layers or {}}

    if what == "features":
        return _picture_features(got, p, cmap, encode, layers)

    if what != "classes":
        raise DsPcaError("%r is not something this panel draws." % what)

    res = fit(got, p, layers=layers)
    sel, types = res["sel"], np.asarray(res["types"])
    ns = [nums[i] for i in sel]
    t0, t1 = res["t0"], res["t1"]

    # THE WHOLE SHANK, not the selected band.
    #
    # These used to be cropped to the contacts the features come from, which
    # made the picture agree with the measurement and useless for the
    # question people actually ask it: is the band in the right place? A
    # panel that only ever shows the inside of the box cannot answer that.
    # So the class mean is drawn down the whole probe and the box is ruled
    # on it, with everything outside dimmed -- the measurement is unchanged
    # and is what `res["sel"]` still names.
    mats, out = [], []
    for c in range(1, int(res["k"]) + 1):
        rr = np.where(types == c)[0]
        mats.append(None if rr.size == 0 else disp[rr].mean(axis=0))
    live = [m for m in mats if m is not None]
    shared_hi = max([float(np.abs(m).max()) for m in live] or [1.0])

    # A COLOUR SCALE PER CLASS, and each panel says what its own is.
    #
    # This was one scale across all of them, deliberately: two heatmaps
    # side by side with independent scales say nothing about which event
    # is larger, and "DS2 is the big one" is a claim people make off
    # exactly this picture. But a shared scale has the opposite cost, and
    # it is the one that bites in practice -- a class with a quarter of
    # the amplitude is drawn as a wash of green, and the SHAPE, which is
    # the whole question the panel exists to answer, is not visible at
    # all.
    #
    # So: each class is scaled to itself, and each panel carries its own
    # peak. The comparison is still available and is now a number to read
    # rather than a colour to eyeball, which is the more honest way round
    # -- the pictures never supported that comparison as well as they
    # appeared to, because the classes rarely share a peak contact.
    for c, mat in enumerate(mats, start=1):
        rr = np.where(types == c)[0]
        hi = shared_hi if mat is None else float(np.abs(mat).max()) or 1.0
        clim = (-hi, hi)
        out.append({
            "c": c, "n": int(rr.size),
            "image": None if mat is None else encode(mat, cmap, clim),
            "extent": extent,
            # Its own scale, and the one it would have shared, so the panel
            # can say how this class compares without redrawing anything.
            "clim": [float(clim[0]), float(clim[1])],
            "peak": float(hi),
            "peak_of_all": float(shared_hi),
            # The picture spans every contact; `band` is the part of it the
            # features were taken from, so the panel can shade the rest.
            "lo": int(min(nums)), "hi": int(max(nums)),
            "band": [int(min(ns)), int(max(ns))] if ns else None,
            # Where the feature box sits inside the picture, so the panel can
            # rule it rather than describing it in a caption.
            "box_ms": [float(tw[t0]), float(tw[max(t0, t1 - 1)])],
        })
    clim = (-shared_hi, shared_hi)
    return {"ok": True, "what": "classes", "classes": out,
            "scaled": "per-class",
            "clim": [float(clim[0]), float(clim[1])],
            "contacts": nums, "band_contacts": ns, "colors": CLASS_COLORS,
            "layers": layers or {}}


def under_hood(got, p, index=None, layers=None, n_scree=8):
    """Every number between one event's CSD patch and the class it was put
    in, in the order they are computed.

    WHY THIS EXISTS. Everything else in this panel is a picture of an
    answer. A picture cannot be checked: "DS1 is the shallower one" and
    "this event is DS2" are claims, and the only way to test a claim is to
    follow the arithmetic that produced it. This returns that arithmetic
    for one event -- the raw patch, what the normalisation did to it, the
    component weights it was multiplied by, the score that came out, and
    the distance to each cluster centre that decided the rest.

    THE THINGS IT MAKES VISIBLE, which are not obvious from the pictures:

      * The PCA sees a FLATTENED patch. Feature 37 is not a depth or a
        time, it is (contact 5, sample 2), and the `axis` list here is
        what turns one back into the other.
      * `mean` is subtracted before projecting. A loading is a weight on a
        DEVIATION from the average event, not on the value.
      * K-MEANS RUNS ON THE TWO PCA COORDINATES, not on the features. Every
        component past the second is computed and then thrown away before
        anything is clustered, and `scree` is how much was in them. On a
        set where PC3 carries as much as PC2 that is worth knowing, and
        nothing on screen says it anywhere else.
      * The class NUMBER comes last, from the depth of a landmark, and is
        not what k-means returned. `km_label` and `type` are both here so
        the renumbering can be seen rather than assumed.
    """
    res = fit(got, p, layers=layers)
    X = np.asarray(res["norm"]).reshape(np.asarray(res["norm"]).shape[0], -1)
    n_ev, n_f = X.shape
    sel, nums = res["sel"], [int(n) for n in got["nums"]]
    ns = [int(n) for n in res["nums_sel"]]
    t0, t1 = res["t0"], res["t1"]
    tw = res["tw"]
    n_t = max(1, t1 - t0)

    i = 0 if index is None else int(index)
    if not 0 <= i < n_ev:
        raise DsPcaError("There is no event %d in this read." % i)

    pca = res["pca"]
    coords = np.asarray(res["coords"])
    x = X[i]
    # `delta` has no components and no mean to subtract: the feature space
    # IS the one number, so the arithmetic below is about that number
    # instead of about a rotation. Zeros rather than a branch everywhere,
    # so the shape of the answer does not change with the method.
    if pca is None:
        comps = np.zeros((0, X.shape[1]))
        mean = np.zeros(X.shape[1])
    else:
        comps = np.asarray(pca.components_)        # [2 x n_features]
        mean = np.asarray(pca.mean_)
    dev = x - mean

    # The score, recomputed HERE from the parts rather than read off the
    # transform. If the two disagree the panel is lying about the
    # arithmetic, and a check is cheap.
    recomputed = [float(np.dot(dev, comps[c])) for c in range(comps.shape[0])]

    # What was thrown away. `fit` asks for two components because two is
    # what the scatter draws; this asks for more, on the same matrix, only
    # to say how much is in the ones nobody clusters on.
    scree = []
    try:
        n_more = int(min(n_scree, n_ev, n_f))
        if pca is not None and n_more >= 1:
            more = PCA(n_components=n_more).fit(X)
            scree = [float(v) for v in more.explained_variance_ratio_]
    except Exception:                                    # noqa: BLE001
        scree = ([float(v) for v in pca.explained_variance_ratio_]
                 if pca is not None else [])

    # The cluster step, in the plane it actually happens in.
    km_centres = np.asarray(res.get("km_centres"))
    dists, km_label = [], None
    if km_centres.size:
        d = [float(np.linalg.norm(coords[i] - c)) for c in km_centres]
        dists = d
        km_label = int(np.argmin(d))
    order = res.get("km_to_type") or {}

    # index -> (contact, sample), which is the whole of "trace it back".
    axis = [{"f": int(f), "csc": int(ns[f // n_t]),
             "row": int(f // n_t), "col": int(f % n_t),
             "t_ms": float(tw[t0 + (f % n_t)])}
            for f in range(n_f)]

    # The features that actually moved this event's score, largest first.
    def top_for(c):
        # `delta` has no components, so there are no terms to rank: the
        # feature vector is one number and the "contribution" of that
        # number is the whole of it. An empty list says that plainly
        # rather than inventing a breakdown of a sum with one term.
        if c >= comps.shape[0]:
            return []
        contrib = dev * comps[c]
        idx = np.argsort(-np.abs(contrib))[:12]
        return [{"f": int(j), "csc": axis[j]["csc"],
                 "t_ms": axis[j]["t_ms"],
                 "x": float(x[j]), "mean": float(mean[j]),
                 "dev": float(dev[j]), "w": float(comps[c][j]),
                 "contrib": float(contrib[j])}
                for j in idx]

    raw = np.asarray(res["feat"])[i]               # [contacts x samples]
    nrm = np.asarray(res["norm"])[i]
    return {
        "ok": True,
        "event": i,
        "n_events": int(n_ev),
        "n_features": int(n_f),
        "shape": {"contacts": len(ns), "samples": int(n_t)},
        "contacts": ns,
        "times_ms": [float(tw[t0 + j]) for j in range(n_t)],
        "features_mode": p.features,
        "features_mode_name": FEATURE_NAMES.get(p.features, p.features),
        "dead": float(p.dead),
        # The three states of one event's patch, same shape, same order.
        "raw": [[float(v) for v in row] for row in raw],
        "norm": [[float(v) for v in row] for row in nrm],
        "mean_vec": [float(v) for v in mean],
        "axis": axis,
        "components": [[float(v) for v in comps[c]]
                       for c in range(comps.shape[0])],
        # Empty under `delta`, which has no components to explain
        # anything with: one number per event is the whole feature
        # space, and there is nothing to rotate.
        "explained": ([float(v) for v in pca.explained_variance_ratio_]
                      if pca is not None else []),
        "scree": scree,
        "score": [float(v) for v in coords[i]],
        "score_recomputed": recomputed,
        "top": {"pc1": top_for(0), "pc2": top_for(1)},
        "km": {
            "on": "the two PCA coordinates",
            "centres": [[float(v) for v in c] for c in km_centres]
                       if km_centres.size else [],
            "distances": dists,
            "label": km_label,
            "to_type": {str(a): int(b) for a, b in (order or {}).items()},
        },
        "method": res.get("method"),
        "method_name": res.get("method_name"),
        # The sink gap for THIS event: the two rows it was measured
        # between, the raw contact distance, and the 0-1 scale that
        # distance becomes. Under `delta` this one number is the entire
        # feature vector; under `pca_gap` it is the last column; under
        # `pca` it is computed and not used, which is worth being able to
        # see rather than having to infer.
        "gap": {
            "value": float((res.get("gap") or [0])[i]),
            "contacts": int((res.get("gap_contacts") or [0])[i]),
            "rows": [int(v) for v in (res.get("gap_rows") or [[0, 0]])[i]],
            "csc": [int(ns[v]) for v in (res.get("gap_rows")
                                         or [[0, 0]])[i]],
            "min_sep": int(res.get("min_sep") or MIN_SINK_SEP),
            "weight": float(res.get("gap_weight") or 1.0),
            "span": len(ns),
            "used": res.get("method") in ("pca_gap", "delta"),
        },
        # Where k-means drew its line, for the one method where that is a
        # number on an axis rather than a plane.
        "bounds": ((res.get("variants") or {}).get("delta") or {}).get(
            "bounds") or [],
        # What the other two methods called this same event. The whole
        # reason all three are computed.
        "agree": {name: int(np.asarray(v["types"])[i])
                  for name, v in (res.get("variants") or {}).items()},
        "type": int(np.asarray(res["types"])[i]),
        "k": int(res["k"]),
        "rule": p.rule,
        "flip": bool(p.flip),
        "decide": res.get("decide") or [],
        "colors": CLASS_COLORS,
    }


def _picture_features(got, p, cmap, encode, layers):
    """The feature matrix itself: one column per event, sorted by class.

    NOT DECORATION. This is the panel a bad contact shows up on, as a solid
    stripe running the whole width of the sheet -- which is how the first
    version of this analysis was caught classifying one wire rather than
    one kind of event. Everything else here shows an average, and an
    average is exactly where a single bad column hides.

    It is also the only picture that shows the thing the PCA actually sees.
    The rasters are the band-limited, mains-out CSD because that is what is
    legible; the features are what `normalize_block` returned. Sorted by
    class and ruled between them, so "these two groups look different" is
    something you can check rather than take on trust.
    """
    res = fit(got, p, layers=layers)
    types = np.asarray(res["types"])
    norm = np.asarray(res["norm"])
    X = norm.reshape(norm.shape[0], -1)

    groups, order, at = [], [], 0
    for c in range(1, int(res["k"]) + 1):
        rr = np.where(types == c)[0]
        order.append(rr)
        groups.append({"c": int(c), "n": int(rr.size),
                       "x0": int(at), "x1": int(at + rr.size)})
        at += int(rr.size)
    live = [r for r in order if r.size]
    idx = np.concatenate(live) if live else np.arange(X.shape[0])
    mat = X[idx].T                       # feature (depth x time) down, event across

    # The scale the mode is on, not a robust percentile of it. min-max is 0
    # to 1 by construction and sign is -1 to +1; a percentile would make the
    # same pattern a different colour on two recordings, which is the one
    # thing a panel for comparing patterns must not do.
    clim = (0.0, 1.0) if p.features == "minmax" else (-1.0, 1.0)
    return {"ok": True, "what": "features",
            "image": encode(mat, cmap, clim),
            "clim": [clim[0], clim[1]],
            "n_events": int(mat.shape[1]), "n_features": int(mat.shape[0]),
            "n_contacts": int(len(res["sel"])),
            "n_samples": int(res["t1"] - res["t0"]),
            "groups": groups, "colors": CLASS_COLORS,
            "mode": p.features,
            "mode_name": FEATURE_NAMES.get(p.features, p.features)}


def _picture_traces(got, p, index, tw, nums, gain):
    """The stacked voltage panel, as vectors rather than as an image.

    Vectors because that is what a trace view is: the browser draws sixty-
    four polylines and they stay crisp at any pane size, which is what
    Xplorefinder's own traces pane does. Band-limited to match the raster
    beside it -- on the broadband trace the slow field dwarfs the spike and
    nothing about the depth is legible.
    """
    vb = got["sur"]["band"]
    if index is None:
        wave = vb.mean(axis=0)
        title = "mean of %d" % vb.shape[0]
    else:
        i = int(index)
        if not 0 <= i < vb.shape[0]:
            raise DsPcaError("There is no event %d in this read." % i)
        wave = vb[i]
        title = "spike %d" % (i + 1)
    # The gain is in CONTACT UNITS: the biggest deflection on the shank spans
    # this many contacts. Traces overlapping is how a stacked ephys raster is
    # meant to look -- the standalone version's first draft scaled the peak
    # to under half a contact and every channel drew as a flat line.
    g = float(gain or 4.0)
    scale = float(np.percentile(np.abs(wave), 99.5)) or 1.0
    return {
        "ok": True, "what": "traces", "title": title,
        "t_ms": [float(v) for v in tw],
        "gain": g,
        "contacts": nums,
        # Already in contact units, so the browser draws `num - value` and
        # needs to know nothing about microvolts.
        "rows": [[float(v) for v in (-wave[i] * g / scale)]
                 for i in range(wave.shape[0])],
        "uv_per_contact": float(scale / g),
    }
