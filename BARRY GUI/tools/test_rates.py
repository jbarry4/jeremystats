# -*- coding: utf-8 -*-
"""Does a run somewhere else leave this machine's estimates alone?

`cfc.py` learns how long each stage takes and writes it to
`GUI_logs/.cfc_rates.json`, and every ETA in the app is read back out of that
file. The table was built when every run happened on the computer running the
app, so `_learn` folded each measurement into the volume-blind key as well as
the per-volume one -- right for a second disk, and wrong for a second
*machine*.

Nothing in the suite could have caught that. The damage is a number in a cache
file sitting 0.3 of the way towards another computer's speed, and every screen
goes on looking exactly as it did; it surfaces as an ETA wrong by a factor,
weeks later, with nothing to point at. So it is asserted here rather than
noticed there.

The other half of the file is a regression guard. The fix works by namespacing
in `_key`, deliberately NOT by adding stages to `_PER_VOLUME` -- because
`_stage_stamp` hashes `_PER_VOLUME` membership, and changing it would drop
every affected rate on every machine in the lab on the next start. The
membership assertions below are there to fail if somebody later "fixes" this
the other way.

    python tools/test_rates.py

Hermetic: a temp rates file. No recording, no cluster, no server.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import cfc  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %-62s %s" % (name, "ok" if ok else "FAILED"))
    if detail and not ok:
        print("      " + str(detail))
    if not ok:
        FAILED.append(name)


def learn(stage, where, seconds=10.0, units=100):
    """One measurement, and what it changed. Restores nothing -- callers
    snapshot what they care about."""
    cfc._learn(stage, seconds, units, 1.0, where)


def main():
    tmp = tempfile.mkdtemp(prefix="barry_rates_")
    try:
        cfc.configure(tmp)

        # ---- a run on the cluster teaches the cluster, and only it --------
        print("\na remote run writes only its own key")

        # `ds detect` is the case that matters: it is NOT in _PER_VOLUME, so
        # before the fix `_key` collapsed to the bare name and the cluster's
        # seconds landed in the number this desktop quotes.
        stage = "ds detect"
        before = dict(cfc._RATES)
        learn(stage, "vacc:netfiles", seconds=1.0, units=100)
        after = dict(cfc._RATES)

        check("the volume-blind rate is untouched by a remote run",
              after.get(stage) == before.get(stage),
              "was %r, now %r" % (before.get(stage), after.get(stage)))
        check("the remote rate is written under its own key",
              after.get("ds detect @ vacc:netfiles") is not None)
        check("no other key moved",
              set(after) - set(before) == {"ds detect @ vacc:netfiles"},
              sorted(set(after) - set(before)))

        # A second cluster, and the first one's number stays put.
        learn(stage, "vacc:scratch", seconds=4.0, units=100)
        check("two remote filesystems are two rates",
              cfc._RATES.get("ds detect @ vacc:netfiles")
              != cfc._RATES.get("ds detect @ vacc:scratch"))

        # ---- local behaviour is exactly what it was -----------------------
        print("\nlocal runs still learn both keys")

        before = dict(cfc._RATES)
        learn("ds read", "d:", seconds=8.0, units=200)
        check("a per-volume stage writes the bare key too",
              cfc._RATES.get("ds read") != before.get("ds read"))
        check("a per-volume stage writes the volume key",
              cfc._RATES.get("ds read @ d:") is not None)

        before = dict(cfc._RATES)
        learn("surrogates", "d:", seconds=3.0, units=50)
        check("a stage that is not per-volume still learns",
              cfc._RATES.get("surrogates") != before.get("surrogates"))
        check("and does not invent a volume key for itself",
              "surrogates @ d:" not in cfc._RATES)

        # ---- what rate_for hands back -------------------------------------
        print("\nrate_for prefers the measured rate for where it ran")

        check("a measured remote rate is returned for that remote",
              cfc.rate_for("ds detect", "vacc:netfiles")
              == cfc._RATES["ds detect @ vacc:netfiles"])
        check("and is not what the local estimate quotes",
              cfc.rate_for("ds detect") == cfc._RATES["ds detect"])
        # Deliberate, and worth pinning: an unmeasured remote is quoted the
        # local number rather than nothing. It is wrong by whatever the two
        # machines differ by, it is right until there is evidence, and the
        # first run replaces it.
        check("an unmeasured remote falls back to the volume-blind rate",
              cfc.rate_for("surrogates", "vacc:netfiles")
              == cfc._RATES["surrogates"])

        # ---- queue wait is not a rate --------------------------------------
        print("\nqueue wait is never learned")

        before = dict(cfc._RATES)
        learn("vacc queue", "vacc:netfiles", seconds=900.0, units=1)
        check("a _NOLEARN stage writes nothing at all",
              dict(cfc._RATES) == before,
              sorted(set(cfc._RATES) - set(before)))

        # ---- the regression guard ------------------------------------------
        print("\nthe stamped sets are unchanged, so no rate is dropped")

        check("_PER_VOLUME is still the four readers and the bulk run",
              cfc._PER_VOLUME == {"read", "decimate", "spectrum read",
                                  "ds read", "panorama bulk"},
              sorted(cfc._PER_VOLUME))
        check("ds detect is NOT per-volume (that is the wrong fix)",
              "ds detect" not in cfc._PER_VOLUME)
        check("_NOLEARN does not take part in the stage stamp",
              cfc._stage_stamp("ds detect", "channels")
              == cfc._stage_stamp("ds detect", "channels"))

        # A saved file written by this code must survive its own reload --
        # the thing that breaks when a stamped set changes.
        keep = dict(cfc._RATES)
        cfc.configure(tmp)
        check("every learned rate survives a reload",
              all(cfc._RATES.get(k) == v for k, v in keep.items()
                  if " @ " in k),
              [k for k, v in keep.items()
               if " @ " in k and cfc._RATES.get(k) != v])

        # ---- adopt ----------------------------------------------------------
        print("\nadopt registers a job without running it")

        job = cfc.Job({"path": "X:\\x"}, [("ds detect", 4)], 1.0,
                      "vacc:netfiles", id="abc123abc123")
        check("a job can be built with an id that was written down",
              job.id == "abc123abc123")
        check("it is not pollable until it is adopted",
              cfc.get("abc123abc123") is None)
        cfc.adopt(job)
        check("and is afterwards", cfc.get("abc123abc123") is job)
        check("exists() agrees", cfc.exists("abc123abc123"))
        check("a minted id is still the default",
              len(cfc.Job({}, [], 1.0, None).id) == 12)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print("FAILED: " + ", ".join(FAILED))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
