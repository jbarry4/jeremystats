# -*- coding: utf-8 -*-
"""Check the multi-band Coupling path against the paths it must agree with.

    python tools\\check_bands.py [--cache <circuit_cache_s360e48254222.json>]

Three claims, each on a real cue pair (r7 Precon1, pair 1), and each able
to fail:

  1. REGRESSION. With no `bands`, Coupling gives exactly what it gave before
     band mode existed -- compared value for value against pair results the
     /run route wrote on 2026-09-27, before any band code, at the defaults.
  2. ONE READ, SAME ANSWER. A three-band run's theta equals a theta-only
     run's theta, value for value, and likewise beta and gamma. Reading the
     wires once must not change what any band computes.
  3. WHAT A BAND MEANS. Band-average coherence is the mean of the Welch
     curve over [low, high]; band-mode raw_cc is the correlation of the
     BAND-PASSED signals, so it differs from the unfiltered classic one;
     the three bands give different numbers.

Negative controls: a perturbed reference fails (1), and comparing theta
against beta fails (2) -- so neither comparison can pass by being unable to
see a difference.
"""
import copy
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

GID = "s360e48254222"                                    # r7 Precon1 SPC
PAIR = 1
DEFAULT_CACHE = os.path.join(
    os.environ.get("TEMP", ""), "claude",
    "c--Users-Z390-Desktop-jeremystats",
    "9d4ef501-267d-40a5-ac8e-0b4c4f8457cc", "scratchpad",
    "circuit_cache_%s.json" % GID)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(("ok    " if ok else "FAIL  ") + name
          + ("" if ok or not detail else "   [%s]" % detail))


def values(run):
    """{(window, a, b, method): value} from one classic pair result."""
    out = {}
    for w in run.get("windows") or []:
        for pr in w.get("pairs") or []:
            for m in ("coherence", "raw_cc", "amp_cc"):
                got = pr.get(m)
                if not isinstance(got, dict):
                    continue
                s = got.get("summary") if isinstance(got.get("summary"),
                                                      dict) else got
                if s and s.get("value") is not None:
                    out[(w["window"], pr["a"], pr["b"], m)] = s["value"]
    return out


def diff(a, b):
    keys = set(a) | set(b)
    bad = [k for k in keys if a.get(k) != b.get(k)]
    return len(keys), bad


def main():
    cache = DEFAULT_CACHE
    if "--cache" in sys.argv:
        cache = sys.argv[sys.argv.index("--cache") + 1]

    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    from backend import app as appmod
    from backend import coupling

    entry = appmod._coupling_entry(GID)
    rec = appmod.REG.by_gid(GID)
    sm = appmod.REG.summary(rec)
    here = (sm.get("here") or [None])[0]
    if not (entry and here):
        print("r7 Precon1 is not banked and reachable here; nothing checked.")
        return 1
    ev = (entry.get("events") or [])[PAIR - 1]
    pair = appmod._coupling_pair(ev, PAIR)
    bad = sorted(int(c) for c in (sm.get("bad_channels") or []))
    drop = appmod._coupling_drop(ev, bad)
    _rat, probe = appmod._coupling_probe(sm)
    blocked = appmod._coupling_blocked(probe)
    kw = dict(exclude_by_channel=drop, blocked_regions=blocked)

    # -- 1. regression -----------------------------------------------------
    if os.path.isfile(cache):
        ref = json.load(open(cache, encoding="utf-8"))
        ref_run = next((r for r in ref.get("results") or []
                        if r.get("pair_id") == PAIR), None)
        t = time.time()
        now = appmod.app.test_client().post(
            "/api/arc/coupling/%s/run" % GID,
            json={"pair_id": PAIR}).get_json()
        t_classic = time.time() - t
        n, wrong = diff(values(ref_run), values(now))
        check("1. with no bands, Coupling equals its 2026-09-27 answer "
              "(%d values)" % n, n > 0 and not wrong,
              "%d differ, e.g. %s" % (len(wrong), wrong[:2]))
        bent = copy.deepcopy(ref_run)
        w0 = bent["windows"][1]
        for pr in w0["pairs"]:
            got = pr.get("amp_cc")
            if isinstance(got, dict) and got.get("value") is not None:
                got["value"] = got["value"] + 1e-6
                break
        n2, wrong2 = diff(values(bent), values(now))
        check("   NEGATIVE CONTROL: a reference nudged by 1e-6 in one cell "
              "is told apart", len(wrong2) == 1, "%d differ" % len(wrong2))
    else:
        print("note  no pre-band reference cache at %s; regression skipped"
              % cache)
        t_classic = None

    # -- 2. one read, same answer -----------------------------------------
    t = time.time()
    three = coupling.pair_connectivity(here, pair, bands=list(
        coupling.BAND_ORDER), **kw)
    t_three = time.time() - t
    single = {}
    t_single = 0.0
    for b in coupling.BAND_ORDER:
        t = time.time()
        single[b] = coupling.pair_connectivity(here, pair, bands=[b], **kw)
        t_single += time.time() - t
    for b in coupling.BAND_ORDER:
        n, wrong = diff(values(three["bands"][b]),
                        values(single[b]["bands"][b]))
        check("2. %s from the three-band read equals a %s-only run "
              "(%d values)" % (b, b, n), n > 0 and not wrong,
              "%d differ" % len(wrong))
    n, wrong = diff(values(three["bands"]["theta"]),
                    values(three["bands"]["beta"]))
    check("   NEGATIVE CONTROL: theta compared with beta is told apart",
          len(wrong) > n * 0.5, "%d of %d differ" % (len(wrong), n))

    # -- 3. what a band means ----------------------------------------------
    spec = coupling.band_spec("beta")
    curved = coupling.pair_connectivity(here, pair, bands=["beta"],
                                        curves=True, **kw)["bands"]["beta"]
    w = next(x for x in curved["windows"] if x["window"] == "cue1")
    pr = next(p for p in w["pairs"] if (p.get("coherence") or {}).get("curve"))
    cur = pr["coherence"]["curve"]
    xs, ys = cur.get("x") or [], cur.get("y") or []
    inband = [y for x, y in zip(xs, ys) if spec["low"] <= x <= spec["high"]]
    hand = sum(inband) / len(inband) if inband else None
    got = pr["coherence"]["summary"]["value"]
    check("3. band-average coherence is the mean of the Welch curve over "
          "%g-%g Hz" % (spec["low"], spec["high"]),
          hand is not None and abs(got - hand) < 1e-5,
          "summary %s vs hand %s (%d bins)" % (got, hand, len(inband)))

    classic = values(appmod.app.test_client().post(
        "/api/arc/coupling/%s/run" % GID, json={"pair_id": PAIR}).get_json())
    theta = values(three["bands"]["theta"])
    raw_keys = [k for k in theta if k[3] == "raw_cc" and k in classic]
    moved = [k for k in raw_keys if abs(theta[k] - classic[k]) > 1e-9]
    check("   band-mode raw_cc is the band-passed correlation, not the "
          "unfiltered one", raw_keys and len(moved) > len(raw_keys) * 0.5,
          "%d of %d differ" % (len(moved), len(raw_keys)))
    lag = three["bands"]["gamma_low"]["params"]
    check("   each band carries its own lag window (gamma ±60 ms)",
          abs(float(lag.get("max_lag_s") or 0) - 0.06) < 1e-9,
          lag.get("max_lag_s"))

    print("")
    print("timing, one cue pair: classic %s s; three bands in one read "
          "%.1f s; three separate single-band runs %.1f s"
          % ("%.1f" % t_classic if t_classic else "n/a", t_three, t_single))
    bad_n = sum(1 for _n, ok in RESULTS if not ok)
    print("%d check(s), %d failed" % (len(RESULTS), bad_n))
    return 1 if bad_n else 0


if __name__ == "__main__":
    sys.exit(main())
