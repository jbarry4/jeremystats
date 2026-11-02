# -*- coding: utf-8 -*-
"""Does backend/dspca.py compute what the standalone workbench computes?

THE PORT IS THE POINT, SO THE PORT IS WHAT IS CHECKED.

`FOOOF Playgroun/ds_pca_gui.py` is the version the DS1/DS2 method was
developed in, and it is a matplotlib program: it imports pyplot at module
scope, keeps its state in a dict the widgets write into, and calls sys.exit
on bad input. None of that can live in a Flask backend, so `backend/dspca.py`
is a copy of the arithmetic with the window taken off.

A copy is a second implementation, and this codebase's rule is one
implementation per question. The rule is kept here by running both on the
same numbers and refusing to let them disagree -- so the copy stays
answerable to the original for as long as the original exists, and the day
somebody changes one of them this says so.

WHAT IT RUNS ON
---------------
The `.npz` caches the standalone version already wrote beside its event
banks. That is deliberate: it needs no recording mounted, runs in seconds,
and compares the two halves on exactly the arrays the method was developed
against rather than on something synthetic.

Only the plain float arrays are read. The caches' `rows` and `bad` entries
are pickled object arrays written under NumPy 2, and this tree currently runs
NumPy 1.24, which cannot unpickle them. Neither half needs them.

Run:  python tools/check_dspca.py
      python tools/check_dspca.py --cache <some other .npz>
"""
import argparse
import glob
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
REPO = os.path.dirname(APP)
DRAFT = os.path.join(REPO, "FOOOF Playgroun")

sys.path.insert(0, APP)

from backend import dspca                                  # noqa: E402

FAIL = []
CHECKS = [0]


def ok(what, cond, detail=""):
    CHECKS[0] += 1
    print(("  ok   " if cond else "  FAIL ") + what
          + (("   " + detail) if detail and not cond else ""))
    if not cond:
        FAIL.append(what)


def load_draft():
    """The standalone module, with the window disabled before pyplot loads."""
    import matplotlib
    matplotlib.use("Agg")
    sys.path.insert(0, DRAFT)
    sys.argv = ["ds_pca_gui.py"]          # it parses argv when main() runs
    import ds_pca_gui
    return ds_pca_gui


def caches():
    out = []
    for path in sorted(glob.glob(os.path.join(DRAFT, "*_cache_*.npz"))):
        z = np.load(path, allow_pickle=True)
        if "sur_band" not in z:
            # A version-1 cache, written before the band-limited picture was
            # kept. Nothing to compare: a fit needs all three filterings.
            continue
        out.append((path, z))
    return out


def arrays_of(z):
    """What `dspca.read` would have returned, out of a draft-written cache."""
    return {
        "rows": [],
        "sur": {k: np.asarray(z["sur_" + k], dtype=np.float64)
                for k in ("raw", "notch", "band")},
        "nums": [int(n) for n in z["nums"]],
        "bad": {},
        "missed": [],
        "mains_uv": float(z["mains_uv"]),
        "wideband_uv": float(z["wideband_uv"]),
        "fs": 1000.0,
        # None is `probes.get`'s own default, which is the H3: one line of
        # contacts, no columns. That is the geometry the standalone version
        # assumes, so it is the geometry the comparison has to use.
        "probe": None,
        "spacing_um": 30.0,
        "surround_ms": 50.0,
        "runs": [],
    }


def draft_state(G, z, sel, t0, t1, k, rule, notch, screen, flip):
    """The dict `ds_pca_gui.recompute` reads, built the way its own test does."""
    nums = [int(n) for n in z["nums"]]
    n_t = z["sur_raw"].shape[2]
    a = G.Opts(folder="", bank="", label="spike", n_events=0,
               refine="nearest", band=(5.0, 100.0), window_ms=100.0,
               surround_ms=50.0, channels="", spacing=30.0, lfp_fs=1000.0,
               pad=0.5, no_invert=False, cond=0.3, f_order=3, f_sigma=1.0,
               no_vaknin=False, h_power=1, csd_bad_x=4.0, csd_span=16,
               seed=0, refresh=False, line=0.0, save=None)
    return {
        "args": a, "rows": [], "nums": nums,
        "chans": [{"number": n} for n in nums],
        "bad0": {},
        "sur": {kk: np.asarray(z["sur_" + kk], dtype=np.float64)
                for kk in ("raw", "notch", "band")},
        "session_label": str(z["session_label"]),
        "mains_uv": float(z["mains_uv"]),
        "wideband_uv": float(z["wideband_uv"]),
        "notch": notch, "screen": screen, "nclasses": k, "picked": None,
        "gain": 4.0, "guides": [], "guide_artists": [], "manual_bad": {},
        "flip": flip, "rule": rule,
        "tw": np.linspace(-a.surround_ms, a.surround_ms, n_t),
        "centre_i": n_t // 2,
        "sel": sel, "t0": t0, "t1": t1,
    }


def compare(name, mine, theirs, sel):
    """Every number the two produce for one question."""
    ok(name + ": same feature count",
       int(mine["n_features"]) == int(theirs["n_features"]),
       "%s vs %s" % (mine["n_features"], theirs["n_features"]))
    ok(name + ": same depth rows", list(mine["sel"]) == list(sel))

    a, b = np.asarray(mine["coords"]), np.asarray(theirs["fit"])
    ok(name + ": PCA coordinates identical",
       a.shape == b.shape and np.allclose(a, b, rtol=0, atol=1e-9),
       "max |d| = %.3g" % (np.abs(a - b).max() if a.shape == b.shape else -1))

    ta, tb = np.asarray(mine["types"]), np.asarray(theirs["types"])
    ok(name + ": same DS1/DS2 call on every event",
       ta.shape == tb.shape and bool((ta == tb).all()),
       "%d of %d differ" % (int((ta != tb).sum()) if ta.shape == tb.shape
                            else -1, ta.size))

    ok(name + ": same class-average profiles",
       np.allclose(mine["prof"], theirs["prof"], rtol=0, atol=1e-9))

    da, db = mine["decide"], theirs["decide"]
    same = len(da) == len(db)
    if same:
        for x, y in zip(da, db):
            if int(x.get("n", 0)) != int(y.get("n", 0)):
                same = False
                break
            if not x.get("n"):
                continue
            if (int(x["row"]) != int(y["row"])
                    or int(x["csc"]) != int(y["csc"])
                    or sorted(x["lows"]) != sorted(int(v) for v in y["lows"])
                    or not np.isclose(x["value"], y["value"], rtol=0,
                                      atol=1e-9)):
                same = False
                break
    ok(name + ": the decision panel says the same thing", same,
       "%r vs %r" % ([d.get("csc") for d in da], [d.get("csc") for d in db]))


def anatomy(z):
    """The one rule that is not in the standalone version, so has no twin.

    `tort`, `sink` and `sources` are checked against the workbench above,
    which is the right check for a port. `anatomy` is new here and there is
    nothing to compare it with, so it is checked against what it claims:
    that it orders classes by where their sink sits relative to the labelled
    hilus, and that it falls back rather than failing when a recording has
    no labels.

    The layers are synthesised. StrataScope writes {contact: region} per
    recording and the demo ds-tutorial has none, so a fixture is the only way
    to reach this path at all.
    """
    print("\nthe anatomy rule")
    nums = [int(n) for n in z["nums"]]
    n_t = int(z["sur_raw"].shape[2])
    centre = n_t // 2
    tw = np.linspace(-50.0, 50.0, n_t)

    # A hilus in the middle of the box, with a granule layer either side --
    # the arrangement a shank crossing both blades actually sees.
    hil = set(range(30, 34))
    layers = {}
    for n in nums:
        if n in hil:
            layers[str(n)] = "hil"
        elif 26 <= n < 30:
            layers[str(n)] = "dg_gcl1"
        elif 34 <= n < 38:
            layers[str(n)] = "dg_gcl2"
        else:
            layers[str(n)] = "ca1_so"

    rows = dspca.anatomy_rows([n for n in nums if 26 <= n <= 41], layers)
    ok("anatomy: it finds the labelled hilus and blades",
       len(rows) == len(hil) + 8, "%d rows" % len(rows))
    ok("anatomy: a recording with no labels yields nothing to measure against",
       dspca.anatomy_rows(nums, {}) == [])

    def run(rule, lay):
        p = dspca.Params(spacing=30.0, csd_span=16, nclasses=2, rule=rule,
                         notch=True, screen=False, flip=False, seed=0,
                         sel_lo=26, sel_hi=41,
                         t_lo_ms=float(tw[centre]), t_hi_ms=float(tw[centre]))
        return dspca.fit(arrays_of(z), p, layers=lay)

    with_l = run("anatomy", layers)
    without = run("anatomy", {})
    tort = run("tort", {})
    ok("anatomy: it labels every event", with_l["types"].size == len(with_l["types"])
       and all(t >= 1 for t in with_l["types"]))
    ok("anatomy: with no layers it falls back to tort rather than failing",
       bool((without["types"] == tort["types"]).all()),
       "%d of %d differ" % (int((without["types"] != tort["types"]).sum()),
                            without["types"].size))
    ok("anatomy: the classes are ordered by depth relative to the hilus",
       _ordered_by_hilus(with_l, layers),
       str([(d["c"], d.get("csc")) for d in with_l["decide"] if d.get("n")]))
    ok("anatomy: it says which rule it used",
       all(d.get("rule") == "anatomy" for d in with_l["decide"] if d.get("n")))


def _ordered_by_hilus(res, layers):
    """DS1 above DS2, measured from the labelled hilus rather than from row 0.

    The whole point of the rule: `tort`, `sink` and `sources` all really ask
    "which class is nearer the top of the box", which is a question about the
    probe. This asks which is nearer the hilus, which survives a shank
    inserted the other way up.
    """
    ns = [int(n) for n in res["nums_sel"]]
    here = [i for i, n in enumerate(ns)
            if str(layers.get(str(n), "")) in ("hil", "dg_gcl1", "dg_gcl2")]
    if not here:
        return False
    centre = float(np.mean(here))
    got = [d["row"] - centre for d in res["decide"] if d.get("n")]
    return got == sorted(got)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", default=None)
    args = ap.parse_args()

    if not dspca.HAVE_SKLEARN:
        sys.exit("scikit-learn is not installed here, so there is nothing to "
                 "check. pip install scikit-learn")

    G = load_draft()
    found = caches()
    if args.cache:
        found = [(args.cache, np.load(args.cache, allow_pickle=True))]
    if not found:
        sys.exit("No .npz caches with a band-limited picture in %s. Run the "
                 "standalone workbench once to write one." % DRAFT)

    for path, z in found:
        nums = [int(n) for n in z["nums"]]
        n_t = int(z["sur_raw"].shape[2])
        centre = n_t // 2
        tw = np.linspace(-50.0, 50.0, n_t)
        print("\n%s   %d events x %d contacts x %d samples"
              % (os.path.basename(path), z["sur_raw"].shape[0], len(nums),
                 n_t))

        # Toothy's own box -- one sample at the stamp -- and two widenings,
        # because the time axis is what this version added and a port that
        # only agreed at width one would agree about nothing new.
        boxes = [
            ("1 sample", list(range(25, 41)), centre, centre + 1),
            ("9 samples", list(range(25, 41)), centre - 4, centre + 5),
            ("narrow, 5 samples", list(range(29, 36)), centre - 2, centre + 3),
        ]
        for label, sel, t0, t1 in boxes:
            for rule in ("tort", "sink", "sources"):
                for k in (2, 3):
                    name = "%s / %s / k=%d" % (label, rule, k)
                    p = dspca.Params(
                        spacing=30.0, csd_span=16, nclasses=k, rule=rule,
                        notch=True, screen=False, flip=False, seed=0,
                        sel_lo=nums[sel[0]], sel_hi=nums[sel[-1]],
                        t_lo_ms=float(tw[t0]), t_hi_ms=float(tw[t1 - 1]))
                    mine = dspca.fit(arrays_of(z), p)
                    theirs = G.recompute(
                        draft_state(G, z, sel, t0, t1, k, rule, True, False,
                                    False))
                    compare(name, mine, theirs, sel)

        # The notch switch and the hand flip, at Toothy's box only: both are
        # one-line branches and running them across every box buys nothing.
        sel = list(range(25, 41))
        for notch in (True, False):
            for flip in (False, True):
                p = dspca.Params(
                    spacing=30.0, csd_span=16, nclasses=2, rule="tort",
                    notch=notch, screen=False, flip=flip, seed=0,
                    sel_lo=nums[25], sel_hi=nums[40],
                    t_lo_ms=float(tw[centre]), t_hi_ms=float(tw[centre]))
                mine = dspca.fit(arrays_of(z), p)
                theirs = G.recompute(
                    draft_state(G, z, sel, centre, centre + 1, 2, "tort",
                                notch, False, flip))
                compare("notch=%s flip=%s" % (notch, flip), mine, theirs, sel)

        # The CSD screen, which is the loop that repairs and re-screens.
        p = dspca.Params(spacing=30.0, csd_span=16, nclasses=2, rule="tort",
                         notch=True, screen=True, flip=False, seed=0,
                         sel_lo=nums[25], sel_hi=nums[40],
                         t_lo_ms=float(tw[centre]), t_hi_ms=float(tw[centre]))
        mine = dspca.fit(arrays_of(z), p)
        theirs = G.recompute(
            draft_state(G, z, sel, centre, centre + 1, 2, "tort", True, True,
                        False))
        compare("CSD screen on", mine, theirs, sel)
        ok("CSD screen on: flagged the same contacts",
           sorted(mine["bad"]) == sorted(theirs["bad"]),
           "%s vs %s" % (sorted(mine["bad"]), sorted(theirs["bad"])))

    anatomy(found[0][1])

    print("\n%d checks, %d failed" % (CHECKS[0], len(FAIL)))
    for f in FAIL:
        print("  - " + f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
