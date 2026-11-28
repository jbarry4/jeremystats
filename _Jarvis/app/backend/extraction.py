# -*- coding: utf-8 -*-
"""extraction.py -- The Extraction Room, the sixth and last step of The
Dentist (asked 2026-11-10).

"Create the 6th and last step of The Dentist, The Extraction Room: a
different tab open, like the Monolith. The first tab is the Dentate Spike:
the CSD view and the depth profiles, toggleable between the mean sink and
the mean source -- for the mean sink keep the delta. And the %KO for each
PTEN mouse as a chip next to it, 0% for the controls."

WHAT IS EXTRACTED. The X-ray bundles of one X-ray Many folder, the newest
version of each, taken OUT of Jarvis into a room of their own: every number
the room shows is copied into one artifact version (kind `extraction`,
one per room), so the room keeps showing exactly what was extracted however
the bundles move on afterwards. Extracting again is the room's next
version. Nothing here writes to a bundle, a read or the Event Bank.

PER RECORDING, PER CLASS (DS1, DS2):
  csd       the class's mean CSD over the whole shank and the read's
            surround (5-100 Hz, 60 Hz notched: the picture X-ray draws),
            contacts x time;
  profile   the class's depth profile at the box's time -- the bundle's
            own mean and SEM, the curve X-ray's sinks were measured on;
  sink      its strongest sink in the box (the bundle's) and the DELTA:
            the distance between its two largest sinks, per event, as
            X-ray's delta method measures it -- mean and SEM, in contacts
            and um;
  source    its strongest source in the box: the profile's maximum there,
            with its SEM.
And the recording's %KO, from the lab's sheet (a shared preference, so it is
corrected once for everybody), 0 for a control.

Everything numeric is worked out by `extract_one` from the bundle and its
read; app.py does the loading and the saving.
"""
from __future__ import annotations

import numpy as np

KIND = "extraction"
SCHEMA = "extraction.ds/1"
# A second room for KCNT1 (2026-11-27, the preliminary run): its sets are kept
# apart from PTEN's, so a new version of one project's room never mixes in the
# other's recordings.
ROOMS = (("dentate_spike", "Dentate Spike"),
         ("dentate_spike_kcnt1", "Dentate Spike KCNT1"))
KO_KEY = "extraction_ko"

# The %KO of each PTEN mouse, "JB % hits" on the lab's sheet (sent
# 2026-11-10). Keyed as Jarvis keys a mouse; a control is 0 by rule, not
# by entry. Seeded into the shared preference on the room's first visit.
KO_SHEET = {
    "PTEN|m7": 24.12, "PTEN|m8": 3.89, "PTEN|m1": 5.18, "PTEN|m10": 9.51,
    "PTEN|m11": 13.50, "PTEN|m33": 4.41, "PTEN|m34": 28.43,
    "PTEN|m13": 18.87, "PTEN|m3": 24.57, "PTEN|m5": 27.64,
    "PTEN|m28": 20.19,
}
# Its other column, kept beside it: which of them have IEDs.
IED_SHEET = {
    "PTEN|m7": False, "PTEN|m8": False, "PTEN|m1": False, "PTEN|m10": False,
    "PTEN|m11": False, "PTEN|m33": False, "PTEN|m34": True,
    "PTEN|m13": True, "PTEN|m3": True, "PTEN|m5": True, "PTEN|m28": True,
}


def _sig(v, n=4):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    if v == 0:
        return 0.0
    return float("%.*g" % (n, v))


def _sem(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 2:
        return None
    return float(np.std(x) / np.sqrt(x.size))


def ko_of(mouse_key, group, ko):
    """(pct, said): a control is 0; a PTEN mouse is its sheet's number, or
    None when the sheet has none for it."""
    if str(group or "").upper() == "CTL":
        return 0.0, "control"
    v = (ko or {}).get(mouse_key)
    if v is None:
        return None, "not on the sheet"
    try:
        return float(v), "sheet"
    except (TypeError, ValueError):
        return None, "not a number on the sheet"


def source_of(profile, box):
    """The class's strongest source inside the box: the profile's maximum
    there, its contact and its SEM. None when the box is unknown."""
    cs = [int(c) for c in profile.get("contacts") or []]
    mu = np.asarray(profile.get("mean") or [], dtype=float)
    se = np.asarray(profile.get("sem") or [np.nan] * len(mu), dtype=float)
    lo, hi = (box or {}).get("sel_lo"), (box or {}).get("sel_hi")
    if not cs or mu.size != len(cs):
        return None
    idx = [j for j, c in enumerate(cs)
           if lo is None or hi is None or lo <= c <= hi]
    idx = [j for j in idx if np.isfinite(mu[j])]
    if not idx:
        return None
    j = max(idx, key=lambda r: mu[r])
    return {"csc": cs[j], "value": _sig(mu[j]),
            "sem": _sig(se[j]) if se.size > j else None}


def extract_one(bundle, subject, res, got, ko):
    """One recording's part of the room, from its bundle's payload and a
    fit of its read made with the bundle's own settings and box (`res`).

    The refit is how the class of each of the read's events is known --
    the bundle keeps the types in its own event order, which is the fit's
    -- and it is checked against the bundle's counts: a refit that does not
    give the same classes is refused, not shown."""
    types = np.asarray(res.get("types"), dtype=int)
    counts = {str(k): int(v) for k, v in (bundle.get("counts") or {}).items()}
    mine = {str(c): int((types == c).sum()) for c in sorted(set(types.tolist()))}
    if counts and mine != counts:
        raise ValueError("refitting its read gave %s, the bundle says %s"
                         % (mine, counts))
    disp = np.asarray(res["disp"], dtype=float)          # ev x ch x t
    nums = [int(n) for n in res.get("nums_all") or got.get("nums") or []]
    sur_ms = float(got.get("surround_ms") or 50.0)
    n_t = disp.shape[2]
    t_ms = np.linspace(-sur_ms, sur_ms, n_t)
    spacing = float(res.get("spacing_um") or got.get("spacing_um") or 0) or None
    gap_c = np.asarray(res.get("gap_contacts") or [], dtype=float)
    box = bundle.get("box") or {}
    profiles = {int(p.get("c")): p for p in bundle.get("profiles") or []}
    sinks = {int(s.get("cls")): s for s in bundle.get("sinks") or []}
    classes = []
    for c in sorted(set(types.tolist())):
        rr = np.where(types == c)[0]
        mat = np.nanmean(disp[rr], axis=0) if rr.size else None
        prof = profiles.get(c) or {}
        g = gap_c[rr] if gap_c.size == types.size else np.array([])
        sk = sinks.get(c) or {}
        classes.append({
            "c": int(c), "name": "DS%d" % c, "n": int(rr.size),
            "csd": ([[_sig(v, 3) for v in row] for row in mat]
                    if mat is not None else None),
            "profile": {"contacts": prof.get("contacts"),
                        "mean": prof.get("mean"), "sem": prof.get("sem"),
                        "band": prof.get("band")},
            "sink": {"csc": sk.get("csc"), "value": sk.get("value"),
                     "sem": sk.get("sem"), "unit": sk.get("unit")},
            "delta": {
                "contacts": _sig(np.mean(g)) if g.size else None,
                "sem": _sig(_sem(g)) if g.size else None,
                "um": (_sig(np.mean(g) * spacing)
                       if g.size and spacing else None),
                "um_sem": (_sig(_sem(g) * spacing)
                           if g.size and spacing and _sem(g) is not None
                           else None),
                "n": int(g.size)},
            "source": source_of(prof, box),
        })
    ko_pct, ko_said = ko_of(subject.get("mouse_key"), subject.get("group"), ko)
    return {
        "gid": subject.get("gid"), "entry_id": subject.get("entry_id"),
        "session_label": subject.get("session_label"),
        "mouse_key": subject.get("mouse_key"), "group": subject.get("group"),
        "ko_pct": ko_pct, "ko_said": ko_said,
        "ied": IED_SHEET.get(subject.get("mouse_key")),
        "n": int(types.size), "counts": counts,
        "separation": {k: (bundle.get("separation") or {}).get(k)
                       for k in ("verdict", "dbic", "min_share", "n", "words")},
        "box": {k: box.get(k) for k in ("sel_lo", "sel_hi", "t_lo_ms",
                                        "t_hi_ms", "auto")},
        "contacts": nums, "t_ms": [_sig(v, 5) for v in t_ms],
        "spacing_um": spacing, "unit": (classes[0]["sink"].get("unit")
                                        if classes else None),
        "bad": bundle.get("bad") or [],
        "classes": classes,
    }


# --------------------------------------------------------------------------
# THE SPLIT, BY HAND (2026-11-11: "include this sort of K-cluster plot below
# each depth profile as a collapsible ... allow us to move where the line is
# drawn for DS1 and DS2 and see the depth profile and CSDs update"; "have
# these 3 options pre-rendered for us to flip through ... change one at a
# time, or change all mice to the PCA").
#
# X-ray's fit makes all three splits every time (dspca.fit's `variants`):
# PCA with no gap, PCA with the sink gap as a column, and the sink gap alone.
# Each event's place in each, and its class there, is kept with the
# per-event CSD and profiles (`split_arrays`, cached on this machine), so a
# method or a cut is a mean over rows -- milliseconds -- and never a refit.
# A cut is a line across the plot's x axis (the gap, or PC1): the two sides
# are named DS1 and DS2 by X-ray's own rule, as each of its three is.
# --------------------------------------------------------------------------
SPLIT_KEY = "extraction_split"
# THE BITE LINE (2026-11-12) is first and the default of the new round:
# backend/sinkcut.py. Its line is drawn along the events in their overlap
# order, so its "x" is each event's place in that order.
#
# DELTA MIDDLE AND THE HUMP ROWS (2026-11-13: "Add a Delta Middle ... where
# instead of finding the greatest sink it just takes the middle of the hump.
# And for all the total 5 methods... add 2 rows where one basically just
# does it on the top hump, and one on the bottom hump"). Each of the five
# again on the recording's top hump alone and its bottom hump alone (the
# humps sinkcut.hump_cut parts): the Bite line on that hump's sink; PCA on
# that hump's contacts; PCA + gap with the hump's strongest contact in place
# of the gap ("PCA + gap would get channel position instead"); delta and
# delta middle as where that hump's sink is strongest, or its middle, sorted
# shallow to deep. See add_humps.
BASE_METHODS = ("bite", "pca", "pca_gap", "delta", "delta_mid")
HUMP_SIDES = ("top", "bottom")
SPLIT_METHODS = BASE_METHODS + tuple("%s_%s" % (m, h) for h in HUMP_SIDES
                                     for m in BASE_METHODS)
_WORDS_BOTH = {"bite": "Bite line", "pca": "PCA, no gap", "pca_gap": "PCA + gap",
               "delta": "delta only, no PCA", "delta_mid": "delta middle, no PCA"}
_WORDS_HUMP = {"bite": "Bite line", "pca": "PCA", "pca_gap": "PCA + position",
               "delta": "delta, by position", "delta_mid": "delta middle, by position"}
SPLIT_WORDS = dict(_WORDS_BOTH, **{"%s_%s" % (m, h): "%s · %s hump only"
                                   % (_WORDS_HUMP[m], h)
                                   for h in HUMP_SIDES for m in BASE_METHODS})
# Where a hump's middle is: halfway between its edges at this share of its
# deepest point (half: a notch inside the hump does not move the edges).
MID_LEVEL = 0.5
ONE_HUMP = ("The average CSD has one sink hump in this band, so there is no "
            "top and bottom hump to take apart.")


def split_base(m):
    """The method a split is a row of: "pca_gap_top" -> "pca_gap"."""
    for h in HUMP_SIDES:
        if str(m).endswith("_" + h):
            return str(m)[:-len(h) - 1]
    return str(m)


def split_row(m):
    """Which row a split is: "both", "top" or "bottom"."""
    for h in HUMP_SIDES:
        if str(m).endswith("_" + h):
            return h
    return "both"


def split_arrays(res):
    """What a recording's split can be redrawn from without fitting again:
    the per-event CSD, profiles and sink gaps, and each method's place and
    class for every event."""
    v = res.get("variants") or {}
    prof = np.asarray(res["prof"], dtype=np.float32)
    pa = res.get("prof_all")
    out = {"disp": np.asarray(res["disp"], dtype=np.float32), "prof": prof,
           "prof_all": np.asarray(pa if pa is not None else prof, dtype=np.float32),
           "gap_contacts": np.asarray(res.get("gap_contacts") or [], dtype=np.float32),
           "nums_sel": np.asarray(res.get("nums_sel") or [], dtype=int),
           "nums_all": np.asarray(res.get("nums_all") or res.get("nums_sel") or [],
                                  dtype=int)}
    if res.get("feat") is not None:
        # The PCA's own features (2026-11-13), for a PCA on one hump's
        # contacts: events x box contacts x the box's time samples.
        out["feat"] = np.asarray(res["feat"], dtype=np.float32)
    for m in ("pca", "pca_gap", "delta"):
        vm = v.get(m) or {}
        co = np.asarray(vm.get("coords") if vm.get("coords") is not None else [],
                        dtype=np.float32)
        if co.ndim == 1:
            co = co.reshape(-1, 1)
        out["types_" + m] = np.asarray(vm.get("types"), dtype=np.int16)
        out["x_" + m] = co[:, 0] if co.size else np.zeros(0, np.float32)
        out["y_" + m] = (co[:, 1] if co.size and co.shape[1] > 1
                         else np.zeros(co.shape[0] if co.size else 0, np.float32))
        out["bounds_" + m] = np.asarray(vm.get("bounds") or [], dtype=float)
    return out


def default_cut(A, method):
    """Where the line starts: k-means' own boundary for the gap, and for a
    PCA the point halfway between the two classes along PC1."""
    b = A.get("bounds_" + method)
    if b is not None and len(b) and split_base(method) != "pca" and split_base(
            method) != "pca_gap":
        return float(b[0])
    x, t = np.asarray(A["x_" + method], dtype=float), A["types_" + method]
    ok = np.isfinite(x)
    ms = [float(np.mean(x[ok & (t == c)])) for c in (1, 2) if np.any(ok & (t == c))]
    return float(np.mean(ms)) if len(ms) == 2 else (float(ms[0]) if ms else 0.0)


def name_sides(lab, prof, ns, rule="tort", flip=False, layers=None):
    """The two sides of a cut, numbered DS1 and DS2 exactly as dspca.fit
    numbers each of its three (its `variants` loop)."""
    from . import dspca
    mus = {c: np.nanmean(prof[lab == c], axis=0) for c in (0, 1) if np.any(lab == c)}
    live = sorted(mus)
    if rule == "tort":
        rows_, _up = dspca.tort_order([mus[c] for c in live])
        mark = dict(zip(live, rows_))
    elif rule == "anatomy" and layers is not None:
        mark = dspca._anatomy_marker(mus, ns, layers)
    else:
        mark = {c: dspca.class_marker(mu, rule if rule != "anatomy" else "sink")[0]
                for c, mu in mus.items()}
    order = sorted((0, 1), key=lambda c: mark.get(c, 10 ** 6))
    if flip:
        order = order[::-1]
    remap = {c: i + 1 for i, c in enumerate(order)}
    return np.array([remap[int(x)] for x in lab], dtype=int)


def split_types(A, method, cut=None, rule="tort", flip=False, layers=None):
    """Each event's class under a method, and a cut when one is given."""
    if method not in SPLIT_METHODS:
        raise ValueError("A split is one of %s; not %r."
                         % (", ".join(SPLIT_METHODS), method))
    if np.asarray(A.get("types_" + method, [])).size == 0:
        raise ValueError(str(A.get("why_" + method) or
                             "That split is not worked out for this recording."))
    if cut is None:
        return np.asarray(A["types_" + method], dtype=int)
    # An event with no place on the axis (no sink in that hump) is on the
    # right, as the Bite line puts an event with no sink.
    x = np.asarray(A["x_" + method], dtype=float)
    lab = np.where(np.isfinite(x), x > float(cut), True).astype(int)
    if lab.min() == lab.max():
        raise ValueError("That cut leaves every event on one side.")
    return name_sides(lab, np.asarray(A["prof"], dtype=float),
                      [int(n) for n in A["nums_sel"]], rule, flip, layers)


def split_classes(A, types, box, spacing=None, unit=None):
    """A recording's classes under any split, in the shape extract_one gives
    them: each class's mean CSD down the shank, its depth profile (mean and
    SEM), its sink (the class mean's minimum in the box, as xraymany.sinks
    finds it), its delta and its source. With X-ray's own split, the same
    numbers the room was extracted with."""
    types = np.asarray(types, dtype=int)
    disp = np.asarray(A["disp"], dtype=float)
    prof = np.asarray(A["prof"], dtype=float)
    pall = np.asarray(A["prof_all"], dtype=float)
    ns = [int(n) for n in A["nums_sel"]]
    na = [int(n) for n in A["nums_all"]] or ns
    gap = np.asarray(A["gap_contacts"], dtype=float)
    band = [min(ns), max(ns)] if ns else None
    out = []
    for c in sorted(set(types.tolist())):
        rr = np.where(types == c)[0]
        mat = np.nanmean(disp[rr], axis=0)
        mu_all = np.nanmean(pall[rr], axis=0)
        sem_all = np.nanstd(pall[rr], axis=0) / np.sqrt(rr.size)
        profile = {"contacts": na, "mean": [_sig(v) for v in mu_all],
                   "sem": [_sig(v) for v in sem_all], "band": band}
        mu = np.nanmean(prof[rr], axis=0)
        j = int(np.nanargmin(mu)) if ns else None
        sink = ({"csc": int(ns[j]), "value": _sig(mu[j]),
                 "sem": _sig(float(np.nanstd(prof[rr, j]) / np.sqrt(rr.size))),
                 "unit": unit} if j is not None else {"unit": unit})
        g = gap[rr] if gap.size == types.size else np.array([])
        out.append({
            "c": int(c), "name": "DS%d" % c, "n": int(rr.size),
            "csd": [[_sig(v, 3) for v in row] for row in mat],
            "profile": profile, "sink": sink,
            "delta": {"contacts": _sig(np.mean(g)) if g.size else None,
                      "sem": _sig(_sem(g)) if g.size else None,
                      "um": _sig(np.mean(g) * spacing) if g.size and spacing else None,
                      "um_sem": (_sig(_sem(g) * spacing)
                                 if g.size and spacing and _sem(g) is not None else None),
                      "n": int(g.size)},
            "source": source_of(profile, box or {}),
        })
    return out


_AXIS = {"bite": "events in Bite line order", "pca": "PC1", "pca_gap": "PC1",
         "delta": "sink gap (0 to 1)",
         "delta_mid": "contacts between the two humps’ middles"}
_AXIS_HUMP = {"delta": "where the %s hump’s sink is strongest (contact)",
              "delta_mid": "the %s hump’s middle (contact)"}


def split_view(A, choice=None):
    """The fifteen splits for the page (five methods, each on both humps
    and on each hump alone): each event's place and class in each, and
    where its line starts. A split that cannot be made here has no events
    and says why. `choice`: {method, cut} in use."""
    out = {"n": int(np.asarray(A["types_delta"]).size), "methods": {},
           "humps": humps_of(A)}
    for m in SPLIT_METHODS:
        b, row = split_base(m), split_row(m)
        if "x_" + m not in A or np.asarray(A["types_" + m]).size == 0:
            out["methods"][m] = {"name": SPLIT_WORDS[m], "base": b, "row": row,
                                 "x": [], "y": [], "types": [],
                                 "why": str(A.get("why_" + m) or
                                            "Not worked out for this recording.")}
            continue
        x = np.asarray(A["x_" + m], dtype=float)
        y = np.asarray(A["y_" + m], dtype=float)
        axis = (_AXIS_HUMP[b] % row if row != "both" and b in _AXIS_HUMP
                else _AXIS[b])
        out["methods"][m] = {
            "name": SPLIT_WORDS[m], "base": b, "row": row,
            "x": [_sig(v, 4) for v in x], "y": [_sig(v, 4) for v in y],
            "types": [int(v) for v in A["types_" + m]],
            "cut": _sig(default_cut(A, m), 5),
            "axis": axis,
            "yaxis": (None if b in ("delta", "delta_mid") else
                      "where its sink sits (contact)" if b == "bite" else "PC2")}
    return out


def humps_of(A):
    """The recording's two humps as contact spans, {top: [first, last],
    bottom: [...], at: the bottom one's first contact}, or None (one hump)."""
    at = A.get("hump_at")
    ns = [int(n) for n in A["nums_sel"]]
    try:
        c = int(at) if at is not None else -1
    except (TypeError, ValueError):
        c = -1
    if c <= 0 or c >= len(ns):
        return None
    return {"top": [ns[0], ns[c - 1]], "bottom": [ns[c], ns[-1]], "at": ns[c]}


def hump_marks(neg, a, b, level=MID_LEVEL):
    """Each event's strongest row and middle row inside rows a..b-1 (one
    hump) of its sink profile `neg` (events x rows, the sink as >= 0): the
    deepest point, and halfway between the hump's edges at `level` of it,
    each edge put between rows where the sink crosses that level. NaN for
    an event with no sink in the hump."""
    seg = np.asarray(neg, dtype=float)[:, a:b]
    n, w = seg.shape
    peak, mid = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(n):
        r = seg[i]
        pv = float(r.max()) if w else 0.0
        if not pv > 0:
            continue
        peak[i] = a + int(np.argmax(r))
        half = level * pv
        on = np.flatnonzero(r >= half)
        lo, hi = int(on[0]), int(on[-1])
        left = (lo - (r[lo] - half) / (r[lo] - r[lo - 1])
                if lo > 0 and r[lo] > r[lo - 1] else float(lo))
        right = (hi + (r[hi] - half) / (r[hi] - r[hi + 1])
                 if hi < w - 1 and r[hi] > r[hi + 1] else float(hi))
        mid[i] = a + (left + right) / 2.0
    return peak, mid


def _line_1d(x, seed=0):
    """Two classes on one number per event, as delta makes them: k-means'
    two centres and the line halfway between. An event with no number goes
    to the right. Returns (0/1 labels, the line)."""
    from . import dspca
    x = np.asarray(x, dtype=float)
    ok = np.isfinite(x)
    if np.unique(x[ok]).size < 2:
        raise ValueError("Every event sits at the same place, so there is "
                         "nothing to split.")
    km = dspca.KMeans(n_clusters=2, n_init="auto", random_state=int(seed)).fit(
        x[ok].reshape(-1, 1))
    c = sorted(float(v) for v in km.cluster_centers_[:, 0])
    cut = (c[0] + c[1]) / 2.0
    return np.where(ok, x > cut, True).astype(int), cut


def _pca_2(X, seed=0):
    """PC1/PC2 of X and k-means' two classes on them, as X-ray's PCA."""
    from . import dspca
    coords = dspca.PCA(n_components=2).fit_transform(np.asarray(X, dtype=float))
    lab = dspca.KMeans(n_clusters=2, n_init="auto",
                       random_state=int(seed)).fit(coords).labels_
    return coords, np.asarray(lab, dtype=int)


def add_humps(A, rule="tort", flip=False, layers=None):
    """Delta middle, and all five methods on each hump alone (2026-11-13),
    into the arrays in their own shape (x_, y_, types_, bounds_ per split;
    why_ where one cannot be made). The humps are the Bite line's: the two
    biggest of the recording's mean stamp profile, parted at the source
    between them (sinkcut.hump_cut), so every row means the same contacts.

      delta_mid         contacts between the two humps' middles
      bite_<h>          the Bite line on that hump's sink alone
      pca_<h>           X-ray's PCA (its own features and scaling) on that
                        hump's contacts
      pca_gap_<h>       the same with that hump's strongest contact (0 at
                        its top edge, 1 at its bottom) where the gap was
      delta_<h>         where that hump's sink is strongest, a contact
      delta_mid_<h>     that hump's middle, a contact
    The 1-D ones are cut by k-means' line, as delta is."""
    from . import dspca, sinkcut
    prof_s, ns = sinkcut.stamp_profiles(A)
    neg = np.maximum(0.0, -prof_s)
    n, D = neg.shape
    cut = sinkcut.hump_cut(prof_s.mean(axis=0)) if n else None
    A["hump_at"] = np.array(-1 if cut is None else int(cut))
    seed = int(np.asarray(A.get("seed", 0)))
    prof = np.asarray(A["prof"], dtype=float)
    feat = A.get("feat")
    mode = str(A.get("features", "minmax"))
    dead = float(np.asarray(A.get("dead", 0.1)))
    gw = float(np.asarray(A.get("gap_weight", 1.0)))

    def name(lab):
        return name_sides(np.asarray(lab, dtype=int), prof, ns, rule, flip, layers)

    def put(m, x, y, lab, bounds):
        A["x_" + m] = np.asarray(x, dtype=np.float32)
        A["y_" + m] = np.asarray(y, dtype=np.float32)
        A["types_" + m] = np.asarray(name(lab), dtype=np.int16)
        A["bounds_" + m] = np.asarray(bounds, dtype=float)
        A.pop("why_" + m, None)

    def fail(m, why):
        A["x_" + m] = np.zeros(0, np.float32)
        A["y_" + m] = np.zeros(0, np.float32)
        A["types_" + m] = np.zeros(0, np.int16)
        A["bounds_" + m] = np.zeros(0, float)
        A["why_" + m] = np.array(str(why))

    def at_contact(rows):
        rows = np.asarray(rows, dtype=float)
        return np.where(np.isfinite(rows),
                        np.interp(np.nan_to_num(rows), np.arange(D), ns), np.nan)

    hump_methods = ["%s_%s" % (m, h) for h in HUMP_SIDES for m in BASE_METHODS]
    if cut is None:
        for m in ["delta_mid"] + hump_methods:
            fail(m, ONE_HUMP)
        return A
    spans = {"top": (0, cut), "bottom": (cut, D)}
    marks = {h: hump_marks(neg, a, b) for h, (a, b) in spans.items()}
    zero = np.zeros(n)
    try:
        lab, c = _line_1d(marks["bottom"][1] - marks["top"][1], seed)
        put("delta_mid", marks["bottom"][1] - marks["top"][1], zero, lab, [c])
    except Exception as exc:                             # noqa: BLE001
        fail("delta_mid", exc)
    for h, (a, b) in spans.items():
        if b - a < 2:
            for m in BASE_METHODS:
                fail("%s_%s" % (m, h), "The %s hump is one contact wide." % h)
            continue
        peak, mid = marks[h]
        try:
            add_bite(A, rule, flip, layers, sink="one", sink_nums=ns[a:b],
                     key="bite_" + h)
        except Exception as exc:                         # noqa: BLE001
            fail("bite_" + h, exc)
        for m, rows in (("delta_" + h, peak), ("delta_mid_" + h, mid)):
            try:
                x = at_contact(rows)
                lab, c = _line_1d(x, seed)
                put(m, x, zero, lab, [c])
            except Exception as exc:                     # noqa: BLE001
                fail(m, exc)
        if feat is None or np.asarray(feat).ndim != 3:
            for m in ("pca_" + h, "pca_gap_" + h):
                fail(m, "Its PCA features were not kept with this read; "
                        "open it again to fit them.")
            continue
        try:
            X = dspca.normalize_block(np.asarray(feat, dtype=float)[:, a:b, :],
                                      mode, dead).reshape(n, -1)
            coords, lab = _pca_2(X, seed)
            put("pca_" + h, coords[:, 0], coords[:, 1], lab, [])
            pos = (peak - a) / float(max(b - a - 1, 1))
            pos = np.where(np.isfinite(pos), pos, 0.5)
            coords, lab = _pca_2(np.hstack([X, pos[:, None] * gw]), seed)
            put("pca_gap_" + h, coords[:, 0], coords[:, 1], lab, [])
        except Exception as exc:                         # noqa: BLE001
            fail("pca_" + h, exc)
            fail("pca_gap_" + h, exc)
    return A


def keep_fit(A, p):
    """The fit's own settings the hump rows need, kept with the arrays."""
    A["features"] = np.array(str(getattr(p, "features", "minmax")))
    A["dead"] = np.array(float(getattr(p, "dead", 0.1) or 0.0))
    A["gap_weight"] = np.array(float(getattr(p, "gap_weight", 1.0)))
    A["seed"] = np.array(int(getattr(p, "seed", 0) or 0))
    return A


def hump_bite_view(A, side, cut=None):
    """The Bite line on one hump alone, slim (sinkcut.view slim): its order,
    cost and sides, drawn on the whole box's raster by the page."""
    from . import sinkcut
    key = "bite_" + side
    F = A.get("_" + key)
    if F is None:
        if np.asarray(A.get("types_" + key, [])).size == 0:
            raise ValueError(str(A.get("why_" + key) or "Not worked out."))
        hm = humps_of(A)
        if not hm:
            raise ValueError(ONE_HUMP)
        lo, hi = hm[side]
        ns = [int(n) for n in A["nums_sel"]]
        add_bite(A, str(A.get("rule", "tort")), bool(A.get("flip", False)),
                 sink="one", sink_nums=[c for c in ns if lo <= c <= hi], key=key)
        F = A["_" + key]
    k = None if cut is None else int(np.ceil(float(cut)))
    return sinkcut.view(F, k=k, slim=True)


# --------------------------------------------------------------------------
# LOW CONTACTS (2026-11-13: "Have a toggle option to exclude the Low
# contacts; just to see how it changes everything"). A contact whose signal
# reads low against its neighbours' -- a gain the wire lost -- is found the
# way it was found on 2026-11-12: each contact's voltage against a cubic
# through the two good contacts either side, in the baseline (|t| > 30 ms,
# no event), as the slope over every sample. The lowest under LOW_FRAC below
# the recording's median gain is taken out and the rest measured again
# without it (a low contact makes its neighbours read high and the ones two
# away read a little low), until none is. A contact left out is made again
# from its neighbours before the CSD -- by the cubic (rebuild_contacts), not
# the straight line a bad contact gets, which would put a notch there itself.
# --------------------------------------------------------------------------
# Low: more than 2% under the median gain AND more than 5 of the
# recording's own MADs (a clean recording's contacts sit within 0.2-0.5% of
# it). 3% missed m28 s2's 44 and 52 (2.2%, 2.7% low) -- and those two were
# its notches: taken out with 25 and 49, its notched events went from 150
# to 1; without them, none.
LOW_FRAC = 0.02
LOW_MADS = 5.0
LOW_MOST = 8


def _lagrange_at(xs, x0):
    """Weights of the polynomial through points xs, evaluated at x0."""
    xs = [float(v) for v in xs]
    w = []
    for i, xi in enumerate(xs):
        p = 1.0
        for j, xj in enumerate(xs):
            if j != i:
                p *= (x0 - xj) / (xi - xj)
        w.append(p)
    return w


def contact_gains(sur, nums, skip=(), surround_ms=50.0, base_ms=30.0):
    """{contact: gain} -- each contact's baseline voltage against the cubic
    through the two contacts either side, (-V[c-2] + 4V[c-1] + 4V[c+1] -
    V[c+2]) / 6. Only where all four are kept (none in `skip`): a stencil
    stretched over a left-out contact predicts more noisily, and a noisier
    prediction pulls the slope down -- the contacts beside a bad one read
    a few per cent low for that alone. `sur` is events x contacts x
    samples, the contacts in shank order."""
    sur = np.asarray(sur, dtype=float)
    _E, C, T = sur.shape
    t = np.linspace(-surround_ms, surround_ms, T)
    base = np.abs(t) > base_ms
    skip = {int(s) for s in skip}
    out = {}
    for c in range(2, C - 2):
        nb = [c - 2, c - 1, c + 1, c + 2]
        if any(int(nums[k]) in skip for k in nb + [c]):
            continue
        w = _lagrange_at(nb, c)
        pred = sum(wk * sur[:, k][:, base] for wk, k in zip(w, nb)).ravel()
        y = sur[:, c][:, base].ravel()
        x = pred - pred.mean()
        d = float((x * x).sum())
        if d > 0:
            out[int(nums[c])] = float((x * (y - y.mean())).sum() / d)
    return out


def rebuild_contacts(got, contacts):
    """A copy of a read with `contacts` made again from their neighbours:
    the cubic through the two nearest good contacts either side, at each
    contact's own depth. For one contact with four good neighbours that is
    (-V[c-2] + 4V[c-1] + 4V[c+1] - V[c+2]) / 6; for a run of them -- 38 and
    39 together, say -- it is the one cubic through 36, 37, 40 and 41,
    read off at 38 and at 39. A contact already marked bad is not used as a
    neighbour, and may be rebuilt itself. NOT the straight line a bad
    contact gets (braces.repair): that makes the second difference -- the
    CSD -- zero at the contact, a notch of its own. On 2026-11-12 the cubic
    took m28 s2's notched events from 150 to 1; filling in straight left 143
    of 143. Where two good contacts are not found on a side, a straight
    line between the nearest good ones. The read itself (shared, cached) is
    not touched."""
    nums = [int(n) for n in got.get("nums") or []]
    want = [int(c) for c in contacts if int(c) in nums]
    bad = {int(k) for k in (got.get("bad") or {})} | set(want)
    out = dict(got)
    out["sur"] = {}
    for key, X in (got.get("sur") or {}).items():
        X = np.array(X, dtype=float, copy=True)
        for c in sorted(want):
            i = nums.index(c)
            below = [k for k in range(i - 1, -1, -1) if nums[k] not in bad][:2]
            above = [k for k in range(i + 1, len(nums)) if nums[k] not in bad][:2]
            if len(below) == 2 and len(above) == 2:
                pts = [below[1], below[0], above[0], above[1]]
                w = _lagrange_at(pts, i)
                X[:, i] = sum(wk * X[:, p] for wk, p in zip(w, pts))
            elif below and above:
                lo, hi = below[0], above[0]
                f = (i - lo) / float(hi - lo)
                X[:, i] = (1 - f) * X[:, lo] + f * X[:, hi]
            elif below or above:
                X[:, i] = X[:, (below or above)[0]]
        out["sur"][key] = X
    return out


# A TIME WINDOW (2026-11-13: "on the time scale add a 2 konbs that limits
# how which DS spikes are included based on the time they appeared"). Only
# the events between two times of the recording are taken: every split,
# class and number is then worked out from those. The recording's, like its
# interpolated contacts: kept per room and recording, used in every set.
TWIN_KEY = "extraction_twin"
TWIN_MIN = 8             # a window keeping fewer events than this is refused


def clean_twin(t0, t1):
    """[t0, t1] in seconds, in order, or a ValueError."""
    try:
        a, b = float(t0), float(t1)
    except (TypeError, ValueError):
        raise ValueError("A time window is two times, in seconds.")
    a, b = min(a, b), max(a, b)
    if not (b - a >= 1.0) or a < 0:
        raise ValueError("A time window is at least a second long.")
    return [round(a, 2), round(b, 2)]


def subset_read(got, twin):
    """A copy of a read with only the events stamped inside `twin`
    ([t0, t1] s). The read itself (shared, cached) is not touched."""
    t0, t1 = twin
    rows = got.get("rows") or []
    keep = np.array([t0 <= float(r.get("stamp_s") or 0.0) <= t1 for r in rows], dtype=bool)
    if int(keep.sum()) < TWIN_MIN:
        raise ValueError("Only %d event%s between %.1f and %.1f min: a window keeps "
                         "at least %d." % (int(keep.sum()), "" if keep.sum() == 1 else "s",
                                           t0 / 60.0, t1 / 60.0, TWIN_MIN))
    out = dict(got)
    out["rows"] = [r for r, k in zip(rows, keep) if k]
    out["sur"] = {k: np.asarray(v)[keep] for k, v in (got.get("sur") or {}).items()}
    return out


# CONTACTS INTERPOLATED BY HAND (2026-11-13, m6 s4's 38 and 39: "we cant
# just remove them because that messes with the profile of the CSD ... if
# there's a way to interpolate two channels like that that would be the best
# method"). A recording's bad wires are the recording's, not a set's: kept
# per room and recording, `room|gid`, and used in every set of the room.
INTERP_KEY = "extraction_interp"
INTERP_MOST = 6


def interp_key(room, gid):
    return "%s|%s" % (room or "dentate_spike", gid)


def clean_interp(contacts, nums, bad=()):
    """The contacts to interpolate, checked: on this shank, at most
    INTERP_MOST, and each with two good contacts above it and two below
    (the others asked for and the ones marked bad do not count)."""
    try:
        want = sorted({int(round(float(c))) for c in contacts or []})
    except (TypeError, ValueError):
        raise ValueError("Contacts are numbers, like 38, 39.")
    ns = [int(n) for n in nums]
    off = [c for c in want if c not in ns]
    if off:
        raise ValueError("Contact%s %s %s not on this shank (%d-%d)." % (
            "" if len(off) == 1 else "s", ", ".join(map(str, off)),
            "is" if len(off) == 1 else "are", min(ns), max(ns)))
    if len(want) > INTERP_MOST:
        raise ValueError("At most %d contacts are interpolated on one recording; "
                         "past that the cubic is guessing." % INTERP_MOST)
    skip = set(want) | {int(b) for b in bad}
    keep = [i for i, n in enumerate(ns) if n not in skip]
    for c in want:
        i = ns.index(c)
        if sum(k < i for k in keep) < 2 or sum(k > i for k in keep) < 2:
            raise ValueError("Contact %d needs two good contacts above it and two "
                             "below to be interpolated." % c)
    return want


# THE TIMELINE (2026-11-13: "At the top of the separation have a line
# showing when all the DS spikes happened. And then a theta power level in
# middle of the region we highlighted on the same time course"). Theta is
# Incisor's (and Toothy's) 6-10 Hz; its power is the squared Hilbert
# envelope, averaged in bins of THETA_BIN_S seconds; a bin with no signal
# (a hole in the recording) is None.
THETA_BIN_S = 4.0
THETA_FS = 250.0                 # the channel is read decimated to about this


def theta_course(x, fs, band=None, bin_s=THETA_BIN_S):
    """(bin starts in s, power per bin) of one channel `x` (NaN in holes)
    sampled at `fs`, in the theta band (incisor.THETA_BAND by default)."""
    from scipy import signal as sig
    from . import incisor
    lo, hi = band or incisor.THETA_BAND
    x = np.asarray(x, dtype=np.float64)
    good = np.isfinite(x)
    if not good.any():
        return np.zeros(0), np.zeros(0)
    y = np.where(good, x - np.nanmean(x), 0.0)
    sos = sig.butter(3, [lo / (fs / 2.0), hi / (fs / 2.0)], btype="band", output="sos")
    env = np.abs(sig.hilbert(sig.sosfiltfilt(sos, y))) ** 2
    env[~good] = np.nan
    per = max(1, int(round(bin_s * fs)))
    nb = int(np.ceil(x.size / float(per)))
    pad = np.full(nb * per, np.nan)
    pad[:x.size] = env
    blk = pad.reshape(nb, per)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # an all-hole bin
        m = np.nanmean(blk, axis=1)
    cnt = np.isfinite(blk).sum(axis=1)
    pw = np.where(cnt > per // 2, m, np.nan)
    return np.arange(nb) * (per / float(fs)), pw


def low_contacts(got, frac=LOW_FRAC, most=LOW_MOST):
    """The contacts of one read whose gain is under the recording's median
    by more than `frac`, found one at a time (see above). Returns (low,
    first): low is [{c, off}] in the order taken out (off: a fraction, the
    gain when it was found against the median), first the first pass's
    gains {contact: off} for saying where every contact stood."""
    nums = [int(n) for n in got.get("nums") or []]
    sur = np.asarray(got["sur"]["band"], dtype=float)
    sur_ms = float(got.get("surround_ms") or 50.0)
    known = {int(b) for b in (got.get("bad") or {})}
    low, first = [], None
    for _ in range(int(most)):
        g = contact_gains(sur, nums, known | {x["c"] for x in low}, sur_ms)
        if not g:
            break
        med = float(np.median(list(g.values())))
        off = {c: v - med for c, v in g.items()}
        if first is None:
            first = off
        mad = float(np.median(np.abs(list(off.values()))))
        c, o = min(off.items(), key=lambda kv: kv[1])
        if o >= -max(float(frac), LOW_MADS * mad):
            break
        low.append({"c": int(c), "off": float(o)})
    return low, first or {}


def room_name(room):
    return dict(ROOMS).get(room, room)


# --------------------------------------------------------------------------
# Which is DS1, said by hand (2026-11-10: "let me toggle the label, because
# the math can be a bit off")
# --------------------------------------------------------------------------
FLIP_KEY = "extraction_flip"


def flip_key(room, gid):
    """The key a call had before calls were kept per set (2026-11-11)."""
    return "%s|%s" % (room, gid)


def call_key(room, folder, gid):
    """A call on one recording in one set -- the X-ray Many folder it was
    extracted from -- for the swaps and the separable calls alike."""
    return "%s|%s|%s" % (room, folder, gid)


def classes_shown(rec, flipped):
    """The recording's classes as they are to be called: with its labels
    swapped by hand, X-ray's DS1 is shown and counted as DS2 and the other
    way round. Copies; the extracted numbers are never changed."""
    out = []
    for c in rec.get("classes") or []:
        d = dict(c)
        k = int(c.get("c") or 0)
        d["shown"] = (3 - k) if flipped and k in (1, 2) else k
        if rec.get("no_ds1"):
            d["shown"] = 2               # called "no DS1": all DS2, swapped or not
        d["name"] = {3: "DS3", 4: "unsure"}.get(d["shown"], "DS%d" % d["shown"])
        out.append(d)
    return sorted(out, key=lambda d: d["shown"])


# --------------------------------------------------------------------------
# Does it differ? (2026-11-10: "a chart / stat to see, after toggling, if
# there is a significant result: PTEN vs CTL, and CTL, Low KO, High KO")
# --------------------------------------------------------------------------
# One number per recording (each recording is one mouse here), so the test
# is across mice, never across events: a mouse with 700 events must not
# outvote one with 60.
MIN_N = 5          # a class with fewer events has no sink worth comparing
KO_SPLIT = 10.0    # % KO: below is Low, at or above is High (adjustable)

METRICS = (
    ("ds1_sink", "DS1 sink strength", "csd",
     "How deep DS1's strongest sink in the box goes (the size of its mean CSD there)."),
    ("ds2_sink", "DS2 sink strength", "csd",
     "How deep DS2's strongest sink in the box goes."),
    ("sink_ratio", "DS2 / DS1 sink", "ratio",
     "DS2's sink strength over DS1's: above 1, DS2's sink is the deeper."),
    ("ds1_delta", "DS1 delta", "um",
     "How far apart DS1's two largest sinks are, the mean over its events."),
    ("ds2_delta", "DS2 delta", "um",
     "How far apart DS2's two largest sinks are, the mean over its events."),
    ("ds1_source", "DS1 source", "csd",
     "How high DS1's strongest source in the box goes."),
    ("ds2_source", "DS2 source", "csd",
     "How high DS2's strongest source in the box goes."),
    ("ds1_share", "Share that are DS1", "share",
     "Of the recording's dentate spikes, the share called DS1."),
    ("ds3_share", "Share that are DS3 (hybrid)", "share",
     "With DS3 on: of the recording's dentate spikes, the share whose OML and "
     "MML sinks are balanced (Tarcsay et al. 2025). Empty otherwise."),
)


def metrics_of(rec, flipped, min_n=MIN_N):
    """{metric: value or None} for one recording, with its labels as shown.
    A class with fewer than `min_n` events gives None for its own numbers
    (and the ratio), not a number from three spikes."""
    cs = {d["shown"]: d for d in classes_shown(rec, flipped)}
    a, b = cs.get(1) or {}, cs.get(2) or {}
    ok_a, ok_b = (a.get("n") or 0) >= min_n, (b.get("n") or 0) >= min_n

    def strength(d):
        v = (d.get("sink") or {}).get("value")
        return None if v is None else -float(v)

    def delta(d):
        x = d.get("delta") or {}
        return x.get("um") if x.get("um") is not None else None

    out = {
        "ds1_sink": strength(a) if ok_a else None,
        "ds2_sink": strength(b) if ok_b else None,
        "ds1_delta": delta(a) if ok_a else None,
        "ds2_delta": delta(b) if ok_b else None,
        "ds1_source": (a.get("source") or {}).get("value") if ok_a else None,
        "ds2_source": (b.get("source") or {}).get("value") if ok_b else None,
    }
    s1, s2 = out["ds1_sink"], out["ds2_sink"]
    out["sink_ratio"] = (s2 / s1) if (s1 and s2 is not None and s1 > 0) else None
    n1, n2 = a.get("n") or 0, b.get("n") or 0
    out["ds1_share"] = (n1 / float(n1 + n2)) if (n1 + n2) else None
    mx = rec.get("mix") or {}
    n3 = (cs.get(3) or {}).get("n") or 0
    out["ds3_share"] = ((n3 / float(n1 + n2 + n3)) if (
        mx.get("mode") == "ds3" and not (mx.get("ds3") or {}).get("why")
        and (n1 + n2 + n3)) else None)
    return out


def ko_group(rec, ko_now, split=KO_SPLIT):
    if str(rec.get("group") or "").upper() == "CTL":
        return "CTL"
    if ko_now is None:
        return None
    return "Low KO" if float(ko_now) < float(split) else "High KO"


def _summ(x):
    x = np.asarray([v for v in x if v is not None and np.isfinite(v)], float)
    if not x.size:
        return {"n": 0, "mean": None, "sem": None, "median": None}
    return {"n": int(x.size), "mean": _sig(np.mean(x)),
            "sem": _sig(np.std(x, ddof=1) / np.sqrt(x.size)) if x.size > 1 else None,
            "median": _sig(np.median(x))}


def _p(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(v) else float("%.4g" % v)


def _holm(ps):
    """Holm's step-down adjustment, in the order given."""
    idx = [i for i, p in enumerate(ps) if p is not None]
    out = list(ps)
    order = sorted(idx, key=lambda i: ps[i])
    run = 0.0
    m = len(order)
    for r, i in enumerate(order):
        run = max(run, min(1.0, (m - r) * ps[i]))
        out[i] = _p(run)
    return out


def two_groups(a, b):
    """CTL vs PTEN: Welch's t, Mann-Whitney U, Hedges' g. Each needs two in
    each group and some spread; short of that, None, and said."""
    from scipy import stats as st
    a = [v for v in a if v is not None and np.isfinite(v)]
    b = [v for v in b if v is not None and np.isfinite(v)]
    out = {"welch_p": None, "mwu_p": None, "g": None,
           "why": None if len(a) >= 2 and len(b) >= 2 else
           "fewer than two recordings in a group"}
    if out["why"]:
        return out
    try:
        out["welch_p"] = _p(st.ttest_ind(b, a, equal_var=False).pvalue)
    except Exception:                                    # noqa: BLE001
        pass
    try:
        out["mwu_p"] = _p(st.mannwhitneyu(b, a, alternative="two-sided").pvalue)
    except Exception:                                    # noqa: BLE001
        pass
    na, nb = len(a), len(b)
    sp = np.sqrt(((na - 1) * np.var(a, ddof=1) + (nb - 1) * np.var(b, ddof=1))
                 / max(na + nb - 2, 1))
    if sp > 0:
        d = (np.mean(b) - np.mean(a)) / sp
        out["g"] = _sig(d * (1 - 3.0 / (4 * (na + nb) - 9)))
    return out


def three_groups(groups):
    """CTL, Low KO, High KO: one-way ANOVA and Kruskal-Wallis across all
    three, every pair by Mann-Whitney (Holm-adjusted over the three pairs),
    and Spearman's rho against %KO itself (controls at 0)."""
    from scipy import stats as st
    names = ("CTL", "Low KO", "High KO")
    xs = [[v for v in groups.get(n) or [] if v is not None and np.isfinite(v)]
          for n in names]
    out = {"anova_p": None, "kw_p": None, "pairs": [],
           "why": None if all(len(x) >= 2 for x in xs) else
           "fewer than two recordings in a group"}
    if not out["why"]:
        try:
            out["anova_p"] = _p(st.f_oneway(*xs).pvalue)
        except Exception:                                # noqa: BLE001
            pass
        try:
            out["kw_p"] = _p(st.kruskal(*xs).pvalue)
        except Exception:                                # noqa: BLE001
            pass
    pairs, raw = [], []
    for i, j in ((0, 1), (0, 2), (1, 2)):
        p = None
        if len(xs[i]) >= 2 and len(xs[j]) >= 2:
            try:
                p = _p(st.mannwhitneyu(xs[j], xs[i],
                                       alternative="two-sided").pvalue)
            except Exception:                            # noqa: BLE001
                p = None
        pairs.append({"a": names[i], "b": names[j], "mwu_p": p})
        raw.append(p)
    for pr, ph in zip(pairs, _holm(raw)):
        pr["holm_p"] = ph
    out["pairs"] = pairs
    return out


def spearman(points):
    from scipy import stats as st
    pts = [(k, v) for k, v in points if k is not None and v is not None
           and np.isfinite(v)]
    if len(pts) < 4:
        return {"rho": None, "p": None, "n": len(pts)}
    r = st.spearmanr([k for k, _ in pts], [v for _, v in pts])
    return {"rho": _sig(r.correlation if hasattr(r, "correlation") else r[0], 3),
            "p": _p(r.pvalue if hasattr(r, "pvalue") else r[1]),
            "n": len(pts)}


# --------------------------------------------------------------------------
# THE USUAL TESTS (2026-11-11: "our stats are a bit too strict? use
# something more common and forgiving for a low sample size"). The way most
# papers -- and Prism -- do it: one test per question, picked by whether the
# residuals look normal (Shapiro-Wilk). Two groups: Welch's t, or
# Mann-Whitney. Three: one-way ANOVA with Tukey's pairs, or Kruskal-Wallis
# with Dunn's (Holm). A rate: Boschloo's exact test, never less powerful than
# Fisher's. Nothing corrected across measures. The strict set (both tests
# must agree, Fisher, the false discovery rate) stays beside it.
# --------------------------------------------------------------------------
NORMAL_P = 0.05    # Shapiro-Wilk under this: the residuals are not normal


def _clean(x):
    return [float(v) for v in x if v is not None and np.isfinite(v)]


def normal_resid(groups):
    """Shapiro-Wilk p of the residuals -- each value less its own group's
    mean -- pooled over the groups. None with fewer than three, or none
    spread."""
    from scipy import stats as st
    res = []
    for g in groups:
        if len(g) >= 2:
            m = float(np.mean(g))
            res += [v - m for v in g]
    if len(res) < 3 or float(np.ptp(res)) == 0.0:
        return None
    try:
        return _p(st.shapiro(res).pvalue)
    except Exception:                                    # noqa: BLE001
        return None


def usual_two(a, b, strict):
    """CTL (`a`) vs PTEN (`b`), the usual way: Welch's t when the residuals
    look normal, Mann-Whitney when they do not. `strict` is two_groups'
    answer for the same numbers, so the p is the same one shown there."""
    a, b = _clean(a), _clean(b)
    if len(a) < 2 or len(b) < 2:
        return {"test": None, "p": None, "normal_p": None,
                "why": "fewer than two recordings in a group"}
    norm = normal_resid([a, b])
    if norm is None or norm >= NORMAL_P:
        return {"test": "welch", "p": strict.get("welch_p"), "normal_p": norm}
    return {"test": "mwu", "p": strict.get("mwu_p"), "normal_p": norm}


def dunn(xs):
    """Dunn's test for every pair of `xs` (three groups): each pair's mean
    ranks, from the ranks of all of them together, tie-corrected; raw p."""
    from scipy import stats as st
    allv = [v for x in xs for v in x]
    N = len(allv)
    if N < 3:
        return [None, None, None]
    r = st.rankdata(allv)
    _u, cnt = np.unique(allv, return_counts=True)
    s2 = N * (N + 1) / 12.0 - float(np.sum(cnt ** 3 - cnt)) / (12.0 * (N - 1))
    mr, pos = [], 0
    for x in xs:
        mr.append(float(np.mean(r[pos:pos + len(x)])) if x else None)
        pos += len(x)
    out = []
    for i, j in ((0, 1), (0, 2), (1, 2)):
        if mr[i] is None or mr[j] is None or s2 <= 0:
            out.append(None)
            continue
        z = (mr[j] - mr[i]) / np.sqrt(s2 * (1.0 / len(xs[i]) + 1.0 / len(xs[j])))
        out.append(_p(2 * st.norm.sf(abs(z))))
    return out


def jonckheere(xs):
    """Jonckheere-Terpstra test for a trend in order across the groups `xs`
    (CTL, Low KO, High KO): (p, z), two-sided, by the normal approximation
    with ties (Hollander and Wolfe). z > 0 rises along the order."""
    from scipy import stats as st
    xs = [list(x) for x in xs]
    ns = [len(x) for x in xs]
    N = sum(ns)
    if N < 4 or sum(1 for n in ns if n) < 2:
        return None, None
    J = 0.0
    for i in range(len(xs)):
        for j in range(i + 1, len(xs)):
            for a in xs[i]:
                for b in xs[j]:
                    J += 1.0 if b > a else 0.5 if b == a else 0.0
    _u, t = np.unique([v for x in xs for v in x], return_counts=True)
    t = t.astype(float)
    n = np.asarray(ns, float)
    E = (N * N - float(np.sum(n * n))) / 4.0
    V = ((N * (N - 1) * (2 * N + 5) - float(np.sum(n * (n - 1) * (2 * n + 5)))
          - float(np.sum(t * (t - 1) * (2 * t + 5)))) / 72.0
         + float(np.sum(n * (n - 1) * (n - 2))) * float(np.sum(t * (t - 1) * (t - 2)))
         / (36.0 * N * (N - 1) * (N - 2))
         + float(np.sum(n * (n - 1))) * float(np.sum(t * (t - 1))) / (8.0 * N * (N - 1)))
    if V <= 0:
        return None, None
    z = (J - E) / np.sqrt(V)
    return _p(2 * st.norm.sf(abs(z))), _sig(z, 3)


def dose(points):
    """DOES IT GET WORSE WITH MORE KNOCKOUT? (2026-11-11: "there's something
    wacky with the stats... we want to show that it gets worse with PTEN
    KO".) Spearman against %KO with the controls at 0% is mostly a test of
    controls against PTEN: every control sits at one end, so any PTEN
    difference reads as a trend. The dose is asked among the PTEN mice
    alone, with a Theil-Sen line to draw. `points` [(ko, value)], PTEN only."""
    from scipy import stats as st
    pts = [(float(k), float(v)) for k, v in points
           if k is not None and v is not None and np.isfinite(v)]
    out = dict(spearman(pts), fit=None)
    if len(pts) >= 3 and len({k for k, _ in pts}) >= 2:
        try:
            ts = st.theilslopes([v for _, v in pts], [k for k, _ in pts])
            out["fit"] = {"slope": _sig(ts[0]), "intercept": _sig(ts[1]),
                          "ko": [min(k for k, _ in pts), max(k for k, _ in pts)]}
        except Exception:                                # noqa: BLE001
            pass
    return out


def usual_three(groups, strict):
    """CTL / Low KO / High KO, the usual way: one-way ANOVA and Tukey's
    pairs when the residuals look normal; Kruskal-Wallis and Dunn's pairs
    (Holm) when they do not."""
    from scipy import stats as st
    names = ("CTL", "Low KO", "High KO")
    xs = [_clean(groups.get(n) or []) for n in names]
    out = {"test": None, "p": None, "normal_p": None, "post": None, "pairs": []}
    if not all(len(x) >= 2 for x in xs):
        out["why"] = "fewer than two recordings in a group"
        return out
    norm = normal_resid(xs)
    out["normal_p"] = norm
    # In order, CTL -> Low KO -> High KO: whether it worsens with the dose.
    out["jt_p"], out["jt_z"] = jonckheere(xs)
    ps = [None, None, None]
    if norm is None or norm >= NORMAL_P:
        out.update(test="anova", p=strict.get("anova_p"), post="tukey")
        try:
            tk = st.tukey_hsd(*xs).pvalue
            ps = [_p(tk[i][j]) for i, j in ((0, 1), (0, 2), (1, 2))]
        except Exception:                                # noqa: BLE001
            pass
    else:
        out.update(test="kw", p=strict.get("kw_p"), post="dunn")
        ps = _holm(dunn(xs))
    out["pairs"] = [{"a": names[i], "b": names[j], "p": p}
                    for (i, j), p in zip(((0, 1), (0, 2), (1, 2)), ps)]
    return out


def _boschloo(y1, n1, y2, n2):
    """Boschloo's exact test of two rates, y1 / n1 against y2 / n2 (each
    column of scipy's table is one group's binomial)."""
    from scipy import stats as st
    if not n1 or not n2:
        return None
    if (y1 + y2) in (0, n1 + n2):
        return 1.0
    try:
        return _p(st.boschloo_exact([[y1, y2], [n1 - y1, n2 - y2]],
                                    alternative="two-sided").pvalue)
    except Exception:                                    # noqa: BLE001
        return None


def usual(ctl, pten, by, strict_two, strict_three):
    """A measure's usual tests, beside its strict ones."""
    return {"two": usual_two(ctl, pten, strict_two),
            "three": usual_three(by, strict_three)}


# --------------------------------------------------------------------------
# Separable or not, said by hand (2026-11-10: "I meant: let me swap
# separable / not separable" -- the two-vs-one test and the 10% rule are a
# rule, and the person looking at the two CSDs is the judge)
# --------------------------------------------------------------------------
SEP_KEY = "extraction_sep"


# NO DS1 (2026-11-13: "add an option to say no DS1"): a third call. The
# recording's dentate spikes are all DS2 -- there is no DS1 in it -- so every
# event is one class, DS2: DS2's numbers are taken from all of them, DS1's
# are none, and the share that are DS1 is 0. In the separation rate it is
# one kind, not separable.
SEP_CALLS = ("yes", "no", "no_ds1")


def sep_shown(rec, override):
    """(verdict, by_hand): the person's call when there is one ('yes',
    'no' or 'no_ds1'), else X-ray's."""
    if override in SEP_CALLS:
        return override, True
    return (rec.get("separation") or {}).get("verdict"), False


def sep_binary(verdict):
    """Separable (True), not (False), or not counted (None): 'weak' counts
    as not separable, and so does 'no_ds1' (one kind, all DS2); 'too few'
    is left out of the test, not guessed."""
    if verdict == "yes":
        return True
    if verdict in ("no", "weak", "no_ds1"):
        return False
    return None


def _fisher2(a, b, c, d):
    from scipy import stats as st
    try:
        return _p(st.fisher_exact([[a, b], [c, d]]).pvalue)
    except Exception:                                    # noqa: BLE001
        try:
            return _p(st.fisher_exact([[a, b], [c, d]])[1])
        except Exception:                                # noqa: BLE001
            return None


def _freeman_halton(yes, n):
    """Exact test of a 2 x k table (k groups, separable or not) with its
    margins fixed: the sum of the probabilities of every table no more
    likely than the one seen. Small enough here to enumerate."""
    from math import comb
    k = len(n)
    R1, N = sum(yes), sum(n)
    if not N or R1 in (0, N):
        return 1.0 if N else None
    denom = comb(N, R1)

    def prob(xs):
        out = 1
        for x, m in zip(xs, n):
            out *= comb(m, x)
        return out / denom

    seen = prob(yes)
    total = 0.0

    def walk(i, left, xs):
        nonlocal total
        if i == k - 1:
            if 0 <= left <= n[i]:
                q = prob(xs + [left])
                if q <= seen * (1 + 1e-9):
                    total += q
            return
        for x in range(0, min(n[i], left) + 1):
            walk(i + 1, left - x, xs + [x])
    walk(0, R1, [])
    return _p(min(1.0, total))


def wilson(k, n, z=1.959964):
    """The Wilson 95% interval of a rate k / n, as [lo, hi]."""
    if not n:
        return None
    p = k / float(n)
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [_sig(max(0.0, c - h)), _sig(min(1.0, c + h))]


def cochran_armitage(yes, n, scores=(0, 1, 2)):
    """(p, z): the Cochran-Armitage test for a trend in a rate across
    ordered groups -- here CTL, Low KO, High KO, scored 0, 1, 2."""
    N, R = float(sum(n)), float(sum(yes))
    if N < 2 or R in (0, N):
        return None, None
    pbar = R / N
    t = sum(s * (y - m * pbar) for s, y, m in zip(scores, yes, n))
    v = pbar * (1 - pbar) * (sum(m * s * s for s, m in zip(scores, n))
                             - sum(m * s for s, m in zip(scores, n)) ** 2 / N)
    if v <= 0:
        return None, None
    z = t / np.sqrt(v)
    from scipy import stats as st
    return _p(2 * st.norm.sf(abs(z))), _sig(z, 3)


def logit_ko(ko, yes):
    """Logistic regression of separable on %KO: the odds ratio per 10% KO
    and its likelihood-ratio p. None when it cannot be fitted (every one
    the same, or perfectly split)."""
    x = np.asarray(ko, float)
    y = np.asarray(yes, float)
    if x.size < 4 or y.min() == y.max():
        return {"or10": None, "p": None, "n": int(x.size)}
    from scipy import optimize, stats as st

    def nll(b):
        eta = b[0] + b[1] * x / 10.0
        return float(np.sum(np.logaddexp(0, eta) - y * eta))
    try:
        fit = optimize.minimize(nll, [0.0, 0.0], method="BFGS")
        p0 = y.mean()
        null = -float(np.sum(y * np.log(p0) + (1 - y) * np.log(1 - p0)))
        lr = 2 * (null - fit.fun)
        b1 = float(fit.x[1])
        if not np.isfinite(b1) or abs(b1) > 20:
            return {"or10": None, "p": _p(st.chi2.sf(max(lr, 0), 1)),
                    "n": int(x.size), "why": "the two are split almost perfectly"}
        return {"or10": _sig(np.exp(b1), 3), "p": _p(st.chi2.sf(max(lr, 0), 1)),
                "n": int(x.size)}
    except Exception:                                    # noqa: BLE001
        return {"or10": None, "p": None, "n": int(x.size)}


def separability(rows):
    """How many are separable, by group, and whether that differs: CTL vs
    PTEN by Fisher's exact test; CTL / Low KO / High KO by the exact
    Freeman-Halton test and each pair by Fisher (Holm); and the %KO of the
    separable against the not separable (Mann-Whitney)."""
    from scipy import stats as st
    counted = [x for x in rows if x["sep"] is not None]

    def tally(pred):
        mine = [x for x in counted if pred(x)]
        return {"n": len(mine), "yes": sum(1 for x in mine if x["sep"]),
                "labels_yes": [x["label"] for x in mine if x["sep"]],
                "labels_no": [x["label"] for x in mine if not x["sep"]]}
    is_ctl = lambda x: str(x["group"]).upper() == "CTL"          # noqa: E731
    two = {"CTL": tally(is_ctl), "PTEN": tally(lambda x: not is_ctl(x))}
    a, b = two["PTEN"]["yes"], two["PTEN"]["n"] - two["PTEN"]["yes"]
    c, d = two["CTL"]["yes"], two["CTL"]["n"] - two["CTL"]["yes"]
    two["fisher_p"] = _fisher2(a, b, c, d) if two["PTEN"]["n"] and two["CTL"]["n"] else None
    two["boschloo_p"] = _boschloo(a, a + b, c, c + d)
    names = ("CTL", "Low KO", "High KO")
    three = {nm: tally(lambda x, nm=nm: x["ko_group"] == nm) for nm in names}
    ns = [three[nm]["n"] for nm in names]
    ys = [three[nm]["yes"] for nm in names]
    three["exact_p"] = _freeman_halton(ys, ns) if all(ns) else None
    pairs, raw = [], []
    for i, j in ((0, 1), (0, 2), (1, 2)):
        A, B = three[names[i]], three[names[j]]
        p = (_fisher2(A["yes"], A["n"] - A["yes"], B["yes"], B["n"] - B["yes"])
             if A["n"] and B["n"] else None)
        pairs.append({"a": names[i], "b": names[j], "fisher_p": p,
                      "boschloo_p": _boschloo(B["yes"], B["n"], A["yes"], A["n"])})
        raw.append(p)
    for pr, ph in zip(pairs, _holm(raw)):
        pr["holm_p"] = ph
    for pr, ph in zip(pairs, _holm([pr["boschloo_p"] for pr in pairs])):
        pr["boschloo_holm_p"] = ph
    three["pairs"] = pairs
    kos = [(0.0 if is_ctl(x) else x["ko"], x["sep"]) for x in counted
           if is_ctl(x) or x["ko"] is not None]
    ky = [k for k, s in kos if s]
    kn = [k for k, s in kos if not s]
    ko = {"yes": _summ(ky), "no": _summ(kn), "mwu_p": None}
    if len(ky) >= 2 and len(kn) >= 2:
        try:
            ko["mwu_p"] = _p(st.mannwhitneyu(ky, kn, alternative="two-sided").pvalue)
        except Exception:                                # noqa: BLE001
            pass
    # THE SEPARATION RATE, with its uncertainty (2026-11-10: "have a stats
    # test for separation rate"): each group's rate with a Wilson 95%
    # interval, and whether the rate falls (or rises) in order CTL -> Low
    # KO -> High KO (Cochran-Armitage), and with %KO itself (logistic).
    for t in list(two.values()) + [three[nm] for nm in names]:
        if isinstance(t, dict) and "n" in t:
            t["rate"] = _sig(t["yes"] / t["n"]) if t["n"] else None
            t["ci"] = wilson(t["yes"], t["n"])
    three["trend_p"], three["trend_z"] = cochran_armitage(ys, ns)
    ko["logit"] = logit_ko([k for k, _s in kos], [bool(s) for _k, s in kos])
    # The dose: among the PTEN mice alone (2026-11-11), the controls left out.
    pk = [(x["ko"], x["sep"]) for x in counted if not is_ctl(x) and x["ko"] is not None]
    ko["logit_pten"] = logit_ko([k for k, _s in pk], [bool(s) for _k, s in pk])
    return {"two": two, "three": three, "ko": ko,
            "not_counted": [x["label"] for x in rows if x["sep"] is None],
            "by_hand": [x["label"] for x in rows if x["sep_by_hand"]],
            "values": [{"gid": x["gid"], "label": x["label"], "group": x["group"],
                        "ko": x["ko"], "ko_group": x["ko_group"], "sep": x["sep"],
                        "verdict": x["verdict"], "by_hand": x["sep_by_hand"]}
                       for x in rows]}


def stats(recs, flips, ko_now, split=KO_SPLIT, min_n=MIN_N, skip=(),
          seps=None, only_sep=False):
    """Every metric, every comparison. `flips` is {gid: bool}; `ko_now`
    {gid: % or None}; `skip` the gids a person has left out; `seps`
    {gid: 'yes' | 'no'} the calls made by hand. `only_sep` takes the
    measures from the recordings called separable only (the separability
    test itself always counts them all)."""
    seps = seps or {}
    rows = []
    for r in recs:
        if r.get("gid") in skip:
            continue
        g = r.get("gid")
        ko = ko_now.get(g)
        verdict, by_hand = sep_shown(r, seps.get(g))
        rows.append({"gid": g, "label": r.get("session_label"),
                     "group": r.get("group"), "ko": ko,
                     "ko_group": ko_group(r, ko, split),
                     "flipped": bool(flips.get(g)),
                     "verdict": verdict, "sep": sep_binary(verdict),
                     "sep_by_hand": by_hand,
                     "m": metrics_of(r, bool(flips.get(g)), min_n)})
    sepb = separability(rows)
    if only_sep:
        rows = [x for x in rows if x["sep"]]
    out = []
    for key, name, unit, words in METRICS:
        vals = [{"gid": x["gid"], "label": x["label"], "group": x["group"],
                 "ko": x["ko"], "ko_group": x["ko_group"],
                 "value": _sig(x["m"].get(key))} for x in rows]
        ctl = [v["value"] for v in vals if str(v["group"]).upper() == "CTL"]
        pten = [v["value"] for v in vals if str(v["group"]).upper() != "CTL"]
        by = {n: [v["value"] for v in vals if v["ko_group"] == n]
              for n in ("CTL", "Low KO", "High KO")}
        two_s, three_s = two_groups(ctl, pten), three_groups(by)
        out.append({
            "key": key, "name": name, "unit": unit, "words": words,
            "values": vals,
            "two": dict(two_s, ctl=_summ(ctl), pten=_summ(pten)),
            "three": dict(three_s,
                          **{n: _summ(by[n]) for n in by}),
            "usual": usual(ctl, pten, by, two_s, three_s),
            "spearman": spearman([(0.0 if str(v["group"]).upper() == "CTL"
                                   else v["ko"], v["value"]) for v in vals]),
            "dose": dose([(v["ko"], v["value"]) for v in vals
                          if str(v["group"]).upper() != "CTL"]),
        })
    return {"metrics": out, "split": float(split), "min_n": int(min_n),
            "n": len(rows),
            "groups": {"CTL": sum(1 for x in rows if x["ko_group"] == "CTL"),
                       "Low KO": sum(1 for x in rows if x["ko_group"] == "Low KO"),
                       "High KO": sum(1 for x in rows if x["ko_group"] == "High KO"),
                       "PTEN": sum(1 for x in rows
                                   if str(x["group"]).upper() != "CTL"),
                       "no KO": [x["label"] for x in rows
                                 if x["ko_group"] is None
                                 and str(x["group"]).upper() != "CTL"]},
            "skipped": sorted(skip),
            "separability": sepb, "only_sep": bool(only_sep)}


# --------------------------------------------------------------------------
# Round II (2026-11-10: "try to find something straightforward that is
# significant"): a wide, plain look. Simple per-recording measures, each
# compared the three ways, and the false discovery rate held across all of
# them (Benjamini-Hochberg) -- so a hit is not just the luckiest of many.
# --------------------------------------------------------------------------
ROUND2 = (
    ("events_min", "Events per minute", "/min",
     "Every event Panning kept, per minute of recording."),
    ("ds_min", "Verified DS per minute", "/min",
     "Events inside the DS border, per minute."),
    ("pspike_min", "P-spikes per minute", "/min",
     "Events the one pool calls P-spike, per minute."),
    ("pspike_share", "Share that are P-spikes", "share",
     "Of the recording's events, the share the one pool calls P-spike."),
    ("ds_like", "Share that look like control DS", "share",
     "Of the recording's events, the share inside a DS border drawn from the "
     "controls -- for a control, from the OTHER controls, so its own events "
     "never drew the border they are judged by."),
    ("ds_amp", "Verified DS amplitude", "uV",
     "The mean max amplitude of the recording's verified DS."),
    ("ds_hf", "Verified DS HF power", "dB",
     "The mean 500-1000 Hz power of the recording's verified DS."),
    ("ds_hw", "Verified DS half-width", "ms",
     "The mean half-width of the recording's verified DS."),
    ("all_hf", "HF power of every event", "dB",
     "The mean 500-1000 Hz power of every event Panning kept."),
    ("ds1_min", "DS1 per minute", "/min",
     "X-ray's DS1 (as called now), per minute."),
    ("ds2_min", "DS2 per minute", "/min",
     "X-ray's DS2 (as called now), per minute."),
)


def bh(ps):
    """Benjamini-Hochberg q-values, in the order given (None kept None)."""
    idx = [i for i, p in enumerate(ps) if p is not None]
    m = len(idx)
    out = [None] * len(ps)
    order = sorted(idx, key=lambda i: ps[i], reverse=True)
    run = 1.0
    for r, i in enumerate(order):
        rank = m - r
        run = min(run, ps[i] * m / rank)
        out[i] = _p(min(1.0, run))
    return out


def round2(rows, split=KO_SPLIT):
    """`rows`: [{gid, label, group, ko, m: {measure: value}}]. Every measure
    the three ways, and BH across the measures within each way."""
    for x in rows:
        x["ko_group"] = ko_group(x, x.get("ko"), split)
    out = []
    for key, name, unit, words in ROUND2:
        vals = [{"gid": x["gid"], "label": x["label"], "group": x["group"],
                 "ko": x["ko"], "ko_group": x["ko_group"],
                 "value": _sig((x.get("m") or {}).get(key))} for x in rows]
        ctl = [v["value"] for v in vals if str(v["group"]).upper() == "CTL"]
        pten = [v["value"] for v in vals if str(v["group"]).upper() != "CTL"]
        by = {n: [v["value"] for v in vals if v["ko_group"] == n]
              for n in ("CTL", "Low KO", "High KO")}
        two_s, three_s = two_groups(ctl, pten), three_groups(by)
        out.append({
            "key": key, "name": name, "unit": unit, "words": words,
            "values": vals,
            "two": dict(two_s, ctl=_summ(ctl), pten=_summ(pten)),
            "three": dict(three_s, **{n: _summ(by[n]) for n in by}),
            "usual": usual(ctl, pten, by, two_s, three_s),
            "spearman": spearman([(0.0 if str(v["group"]).upper() == "CTL"
                                   else v["ko"], v["value"]) for v in vals]),
            "dose": dose([(v["ko"], v["value"]) for v in vals
                          if str(v["group"]).upper() != "CTL"]),
        })
    # The false discovery rate, held across the measures, for each way of
    # comparing: its rank test (Mann-Whitney / Kruskal-Wallis / Spearman).
    for way, get in (("two", lambda m: m["two"].get("mwu_p")),
                     ("three", lambda m: m["three"].get("kw_p")),
                     ("ko", lambda m: m["dose"].get("p"))):
        qs = bh([get(m) for m in out])
        for m, q in zip(out, qs):
            m.setdefault("q", {})[way] = q
    # The same rate for the usual tests: shown beside each, not a gate.
    for way, get in (("two", lambda m: m["usual"]["two"].get("p")),
                     ("three", lambda m: m["usual"]["three"].get("p")),
                     ("ko", lambda m: m["dose"].get("p"))):
        qs = bh([get(m) for m in out])
        for m, q in zip(out, qs):
            m.setdefault("q_usual", {})[way] = q
    return {"metrics": out, "split": float(split), "n": len(rows),
            "groups": {"CTL": sum(1 for x in rows if x["ko_group"] == "CTL"),
                       "Low KO": sum(1 for x in rows if x["ko_group"] == "Low KO"),
                       "High KO": sum(1 for x in rows if x["ko_group"] == "High KO"),
                       "PTEN": sum(1 for x in rows
                                   if str(x["group"]).upper() != "CTL")}}


# ==========================================================================
# THE NEW ROUND (2026-11-12): no X-ray. "Since we are skipping x-ray add an
# option for defining the range of depth profile with a simple click and
# drag." A set is still an X-ray Many folder (its workflow run's kept
# events, read once per recording), but the room fits each recording
# itself, in a band the room draws -- by default over "the edges of the 2
# bottom sinks" -- and splits it by the Bite line unless told otherwise.
# The band, the split and the separable call are shared preferences over
# the extracted version; the Impression locks them all in.
# ==========================================================================
BAND_KEY = "extraction_band"
SET_ARCHIVE_KEY = "extraction_set_archive"
BAND_MIN_FRAC = 0.15     # a sink smaller than this share of the largest is not one
BAND_PAD = 1             # contacts past each outer edge, so the edge is in
HALF_MS_BAND = 3.0


def _stamp_rows(n_t, surround_ms=50.0, half_ms=HALF_MS_BAND):
    """The time samples within half_ms of the stamp."""
    t = np.linspace(-surround_ms, surround_ms, n_t)
    return np.where(np.abs(t) <= half_ms + 1e-9)[0]


def mean_profile(disp, surround_ms=50.0):
    """Every event's CSD averaged, at the stamp (+-3 ms), down the shank."""
    disp = np.asarray(disp, dtype=float)
    rows = _stamp_rows(disp.shape[2], surround_ms)
    return np.nanmean(disp[:, :, rows], axis=(0, 2))


def default_band(disp, nums_all, surround_ms=50.0, min_frac=BAND_MIN_FRAC,
                 pad=BAND_PAD):
    """Where the band starts (2026-11-12: "it should cover the edges of the
    2 bottom sinks generally"): the mean CSD at the stamp, its sinks found
    as the Bite line finds an event's (each stretch below zero, ended by a
    zero crossing), those under `min_frac` of the largest dropped as noise,
    and of the rest the two deepest -- from the top edge of the upper one
    to the bottom edge of the lower one, a contact past each. Time: the
    stamp. One sink only: that sink and 4 contacts either side."""
    from . import sinkcut
    na = [int(n) for n in nums_all]
    neg = np.clip(-mean_profile(disp, surround_ms), 0, None)
    bb = sinkcut.bumps(np.nan_to_num(neg))
    big = max((b[2] for b in bb), default=0.0)
    keep = sorted([b for b in bb if big > 0 and b[2] >= min_frac * big],
                  key=lambda b: b[0])
    if not keep:
        return {"sel_lo": na[0], "sel_hi": na[-1], "t_lo_ms": 0.0,
                "t_hi_ms": 0.0, "auto": True,
                "why": "no sink in the average: the whole shank"}
    two = keep[-2:]
    if len(two) == 1:
        lo, hi = two[0][0] - 4, two[0][1] - 1 + 4
        why = "one sink in the average: it and 4 contacts either side"
    else:
        lo, hi = two[0][0] - pad, two[-1][1] - 1 + pad
        why = ("the two bottom sinks of the average, %d-%d and %d-%d, edge "
               "to edge" % (na[two[0][0]], na[two[0][1] - 1],
                            na[two[1][0]], na[two[1][1] - 1]))
    lo, hi = max(0, lo), min(len(na) - 1, hi)
    return {"sel_lo": na[lo], "sel_hi": na[hi], "t_lo_ms": 0.0,
            "t_hi_ms": 0.0, "auto": True, "why": why}


def clean_band(b, nums_all):
    """A band as the room keeps it: contact numbers inside the shank, low
    above high, at least 4 contacts; a time sample or span. None when it
    is not one."""
    if not isinstance(b, dict):
        return None
    na = [int(n) for n in nums_all]
    try:
        lo, hi = int(round(float(b["sel_lo"]))), int(round(float(b["sel_hi"])))
    except (KeyError, TypeError, ValueError):
        return None
    lo, hi = min(lo, hi), max(lo, hi)
    lo, hi = max(lo, min(na)), min(hi, max(na))
    if hi - lo < 3:
        return None
    try:
        t0 = float(b.get("t_lo_ms") or 0.0)
        t1 = float(b.get("t_hi_ms") if b.get("t_hi_ms") is not None else t0)
    except (TypeError, ValueError):
        t0 = t1 = 0.0
    t0, t1 = sorted((max(-50.0, min(50.0, t0)), max(-50.0, min(50.0, t1))))
    return {"sel_lo": lo, "sel_hi": hi, "t_lo_ms": round(t0, 2),
            "t_hi_ms": round(t1, 2), "auto": bool(b.get("auto"))}


def add_bite(A, rule="tort", flip=False, layers=None, sink=None, key="bite",
             **kw):
    """The Bite line on a recording's split arrays, in their own shape:
    x_bite is each event's place in the overlap order (0 = far left),
    y_bite where its sink sits (contact), types_bite the default line's
    classes and bounds_bite that line (between places k-1 and k). The fit
    itself is kept as A['_bite'] for `bite_view`, and what its sink was
    (sinkcut.SINKS) as A['bite_sink']: a line placed by hand is a place in
    THIS order, and means nothing in an order made from another sink.
    `key` "bite_top" / "bite_bottom" (with sink="one" and sink_nums): the
    same on one hump alone, kept under its own names."""
    from . import sinkcut
    sink = str(sink or sinkcut.SINK_DEFAULT)
    F = sinkcut.fit(A, rule=rule, flip=flip, layers=layers, sink=sink, **kw)
    if key == "bite":
        A["bite_sink"] = np.array(sink)
    n = int(np.asarray(F["coord"]).size)
    pos = np.full(n, np.nan)
    live = np.asarray(F["live"], dtype=int)
    pos[live] = np.arange(live.size, dtype=float)
    # An event with no sink at all sits past the right end.
    pos[~np.isfinite(pos)] = float(live.size)
    # Where its sink sits: the sink's centre of mass down its contacts. (Up
    # to 2026-11-13 this read the window's centre -- a TIME sample -- as a
    # contact, so y_bite was empty and the delta plot spread its dots
    # instead of drawing them at their sink's depth.)
    sn = [int(c) for c in F.get("sink_nums") or A["nums_sel"]]
    dd = np.asarray(F["info"]["depth"], dtype=float)
    has = dd.sum(axis=1) > 0
    rows = sinkcut.centroid(dd)
    y = np.where(has, np.interp(rows, np.arange(len(sn)), sn), np.nan)
    A["x_" + key] = pos.astype(np.float32)
    A["y_" + key] = y.astype(np.float32)
    A["types_" + key] = np.asarray(F["types"], dtype=np.int16)
    A["bounds_" + key] = np.asarray([F["k"] - 0.5], dtype=float)
    A.pop("why_" + key, None)
    A["_" + key] = F
    return A


def bite_sink(A):
    """The sink a set of arrays' Bite line was made with: arrays saved
    before it was kept were made with each event's own bumps."""
    s = A.get("bite_sink")
    return str(s) if s is not None and str(s) else "bumps"


def bite_view(A, cut=None):
    """What the Compare panel draws for the Bite line (sinkcut.view): the
    raster in order, the overlap matrix, the cost along the line, and the
    classes at `cut` (a place in the order) or the default line."""
    from . import sinkcut
    F = A.get("_bite")
    if F is None:
        # Arrays from the disk keep the Bite line's classes, not its working:
        # fitted again here, once, when its picture is asked for -- with the
        # sink they were made with (before 2026-11-12's humps: "bumps").
        add_bite(A, str(A.get("rule", "tort")), bool(A.get("flip", False)),
                 sink=bite_sink(A))
        F = A["_bite"]
    k = None if cut is None else int(np.ceil(float(cut)))
    return sinkcut.view(F, k=k)


def csd_all(disp, digits=3):
    """Every event's CSD averaged down the whole shank: the tile the band
    is drawn on."""
    mat = np.nanmean(np.asarray(disp, dtype=float), axis=0)
    return [[_sig(v, digits) for v in row] for row in mat]


def direct_record(subject, res, got, A, types, band, ko, sep=None,
                  read=None, fit_params=None):
    """One recording's part of a new-round room: what extract_one gives,
    from the room's own fit in the room's band rather than an X-ray
    bundle. Its classes are `types` (the Bite line's, by default)."""
    disp = np.asarray(res["disp"], dtype=float)
    nums = [int(n) for n in res.get("nums_all") or got.get("nums") or []]
    sur_ms = float(got.get("surround_ms") or 50.0)
    t_ms = np.linspace(-sur_ms, sur_ms, disp.shape[2])
    spacing = float(res.get("spacing_um") or got.get("spacing_um") or 0) or None
    unit = res.get("unit") or res.get("csd_unit")
    classes = split_classes(A, types, band, spacing, unit)
    counts = {str(c["c"]): int(c["n"]) for c in classes}
    ko_pct, ko_said = ko_of(subject.get("mouse_key"), subject.get("group"), ko)
    return {
        "gid": subject.get("gid"), "entry_id": subject.get("entry_id"),
        "session_label": subject.get("session_label"),
        "mouse_key": subject.get("mouse_key"), "group": subject.get("group"),
        "ko_pct": ko_pct, "ko_said": ko_said,
        "ied": IED_SHEET.get(subject.get("mouse_key")),
        "n": int(np.asarray(types).size), "counts": counts,
        "separation": {k: (sep or {}).get(k)
                       for k in ("verdict", "dbic", "min_share", "n", "words")},
        "box": dict(band), "band": dict(band), "direct": True,
        "read": read, "fit_params": fit_params or {},
        "contacts": nums, "t_ms": [_sig(v, 5) for v in t_ms],
        "spacing_um": spacing, "unit": unit,
        "bad": [int(b) for b in (got.get("bad") or {})],
        "csd_all": csd_all(disp),
        "classes": classes,
    }
