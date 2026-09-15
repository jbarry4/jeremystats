# -*- coding: utf-8 -*-
"""Is what Incisor returns always JSON?

A scan came back HTTP 200 with a body the browser could not parse. That is
the signature of `NaN` or `Infinity`: Python's `json.dumps` writes those
tokens, they are not valid JSON, and the request looks like a success right
up until the parse.

It did not reproduce on M8s9feb8 -- 64 channels, 4.5 MB, clean -- so this
goes looking. Two things are checked for every recording it can reach:

  * the answer survives a STRICT parse, the kind a browser does, with
    `NaN` and `Infinity` rejected rather than accepted as constants;
  * and nothing in it is a non-finite float before serialisation, which
    catches the same fault one step earlier and says which field it was in.

Synthetic cases go first, because they can make the conditions that a
recording only sometimes has: a flat channel with no events at all, a
channel that is entirely NaN, one with a single enormous artifact, and one
whose peaks sit hard against the ends of the trace.

Run: python tools/check_incisor_payload.py [limit]
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import incisor as P                          # noqa: E402

FAILED = []


def ck(name, ok, detail=""):
    print("  %-5s %s%s" % ("ok" if ok else "FAIL", name,
                           "" if ok else "   [%s]" % detail))
    if not ok:
        FAILED.append(name)


def nonfinite(obj, path=""):
    """Every non-finite float in a structure, with where it was."""
    out = []
    if isinstance(obj, float):
        if not math.isfinite(obj):
            out.append((path or "<root>", obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out += nonfinite(v, "%s.%s" % (path, k))
    elif isinstance(obj, (list, tuple)):
        # The first few are enough to name the field.
        for i, v in enumerate(obj[:200]):
            out += nonfinite(v, "%s[%d]" % (path, i))
    return out


def strict(obj):
    """Parse the way a browser does: NaN and Infinity are not constants."""
    raw = json.dumps(obj)

    def boom(c):
        raise ValueError("%r is not JSON" % c)

    json.loads(raw, parse_constant=boom)
    return len(raw)


def check(label, out):
    bad = nonfinite(out)
    ck("%s: nothing non-finite in the answer" % label, not bad,
       "; ".join("%s=%r" % (p, v) for p, v in bad[:4]))
    try:
        n = strict(out)
        ck("%s: it survives a strict parse" % label, True)
        return n
    except ValueError as exc:
        ck("%s: it survives a strict parse" % label, False, str(exc))
        return 0


# --------------------------------------------------------------------------
# The awkward channels, made on purpose
# --------------------------------------------------------------------------
def synthetic_channels():
    fs = 1000.0
    n = 60000
    rng = np.random.default_rng(7)
    t = np.arange(n) / fs
    cases = {}
    cases["flat"] = np.zeros(n)
    cases["noise only"] = rng.normal(0, 40, n)
    cases["all NaN"] = np.full(n, np.nan)
    cases["some NaN"] = np.where(np.arange(n) % 5000 == 0, np.nan,
                                 rng.normal(0, 40, n))
    one = rng.normal(0, 40, n)
    one[30000] = 5e5                      # a single enormous artifact
    cases["one huge artifact"] = one
    edge = rng.normal(0, 30, n)
    for i in (2, 5, n - 6, n - 3):        # peaks hard against the ends
        edge[i] += 4000
    cases["peaks at the ends"] = edge
    square = np.zeros(n)
    square[10000:10400] = 3000.0          # a flat-topped event
    cases["flat-topped event"] = square
    return fs, cases


def main():
    print("Awkward channels, made on purpose")
    fs, cases = synthetic_channels()
    for label, trace in cases.items():
        try:
            f = P._filtered(trace, fs, P.DS_BAND)
            thr = P.threshold_for(f, P.DS_HEIGHT_SD, P.DS_ABS_THR_UV)
            got = P._detect(f, fs, thr["thr_uv"], {}) \
                if math.isfinite(thr["thr_uv"]) else None
        except Exception as exc:                          # noqa: BLE001
            ck("%s: the detector does not raise" % label, False,
               "%s: %s" % (type(exc).__name__, exc))
            continue
        ck("%s: the detector does not raise" % label, True)
        if got is None:
            print("        (no threshold -- the trace is not all numbers, "
                  "which is reported rather than detected on)")
            continue
        payload = {
            "thr": P._finite(thr["thr_uv"]), "sd": P._finite(thr["sd_uv"]),
            "events": [{"amp": P._finite(got["amp"][k], 4),
                        "asym": P._finite(got["asym"][k], 3),
                        "half_width_ms": P._finite(got["half_width_ms"][k], 4)}
                       for k in range(got["idx"].size)],
        }
        check("  " + label, payload)
        n_null = sum(1 for e in payload["events"] if e["asym"] is None)
        if n_null:
            print("        %d of %d events have no asymmetry -- the peak sits "
                  "on its own half-height edge" % (n_null,
                                                   len(payload["events"])))

    print()
    print("Real recordings, end to end through `run`")
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    import urllib.request
    from backend import app as appmod, continuity
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:8791/api/registry", timeout=300) as fh:
            reg = json.loads(fh.read())
    except Exception as exc:                              # noqa: BLE001
        print("  no registry (%s); synthetic only" % exc)
        reg = {}

    seen = 0
    for p in reg.get("tree", []):
        for m in p.get("mice", []):
            for s in m.get("sessions", []):
                path = (s.get("here") or [None])[0]
                if not path or seen >= limit:
                    continue
                try:
                    rep = continuity.check(path)
                    if not rep.get("ok"):
                        continue
                    sess, err = appmod._session_for(path, False, True)
                    if err:
                        continue
                    chans = [c["index"] for c in sess["channels"]][::8]
                    out = P.run(sess, {"path": path, "channels": chans,
                                       "invert": True}, rep)
                except Exception as exc:                  # noqa: BLE001
                    ck("%s: the scan does not raise" % (s.get("label") or "")[:24],
                       False, "%s: %s" % (type(exc).__name__, exc))
                    seen += 1
                    continue
                size = check((s.get("label") or path)[:24], out)
                errs = [c for c in out["channels"] if c.get("error")]
                print("        %d channels, %d events, %.1f MB%s"
                      % (len(out["channels"]), out["n"], size / 1e6,
                         (", %d channel(s) reported bad" % len(errs))
                         if errs else ""))
                for c in errs[:2]:
                    print("          %s: %s" % (c["label"], c["error"]))
                seen += 1

    print()
    if FAILED:
        print("%d check(s) FAILED:" % len(FAILED))
        for f in FAILED:
            print("   %s" % f)
        raise SystemExit(1)
    print("all good -- every answer is JSON a browser can parse")


main()
