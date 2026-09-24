# -*- coding: utf-8 -*-
"""The half of banking that a browser harness should not exercise.

Banking writes a version to the Event Bank. A harness that did it on every
run would mint a version per run on the demo entry forever, and a history
that grows by one every time anybody runs the suite is not a history. So
`_dev/dspca.html` checks the half it can -- that the panels really do come
off the canvases as PNGs -- and this checks the half underneath it:

  * `_png_bytes` accepts what the browser sends and refuses everything
    else, because it decides what becomes a file in Results/;
  * the result record is keyed on the QUESTION, so asking the same thing
    twice writes one record and changing any setting that changes a number
    writes a different one;
  * every setting that changes a number is in that key, which is what
    "reconstruct from the events bank or the results bank" rests on.

    python tools/check_dspca_filing.py

Reads only. Writes nothing, starts no server, touches no data.
"""
import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

from backend import dspca, toolresults            # noqa: E402

OK, BAD = [], []


def ck(name, good, why=""):
    (OK if good else BAD).append(name)
    print(("  ok   " if good else "  FAIL ") + name
          + (("\n       " + str(why)) if (why and not good) else ""))


# A real one-pixel PNG, so "is this a PNG" is answered against a PNG.
PNG1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mP8z8BQDw"
    "AEhQGAhKmMIQAAAABJRU5ErkJggg==")


def main():
    print("THE PICTURE GATE")
    print("-" * 66)
    from backend import app as appmod
    png = appmod._png_bytes(
        "data:image/png;base64," + base64.b64encode(PNG1).decode())
    ck("a PNG data URI from the browser is accepted", png == PNG1)
    ck("something that is not base64 is refused",
       appmod._png_bytes("data:image/png;base64,not base64!!") is None)
    ck("a JPEG data URI is refused, whatever it is called",
       appmod._png_bytes("data:image/jpeg;base64,"
                         + base64.b64encode(PNG1).decode()) is None)
    ck("base64 of something that is not a PNG is refused",
       appmod._png_bytes("data:image/png;base64,"
                         + base64.b64encode(b"not a png at all").decode())
       is None)
    ck("empty is refused", appmod._png_bytes("") is None
       and appmod._png_bytes(None) is None)
    ck("a bare string with no header is refused",
       appmod._png_bytes(base64.b64encode(PNG1).decode()) is None)

    print("")
    print("THE RESULT IS KEYED ON THE QUESTION")
    print("-" * 66)
    keys = tuple(dspca.Params.READ_KEYS) + tuple(dspca.Params.FIT_KEYS)
    base = dspca.Params().as_dict()
    h0 = toolresults.params_hash(base, keys)
    ck("the same question hashes the same way twice",
       h0 == toolresults.params_hash(dict(base), keys))

    # EVERY setting that changes a number has to be in the key, or two
    # different answers are filed as one and the second is lost.
    changed = {
        "method": "pca", "min_sep": 9, "gap_weight": 25.0,
        "features": "sign", "rule": "sink", "nclasses": 3,
        "notch": False, "flip": True, "sel_lo": 7, "sel_hi": 19,
        "t_lo_ms": -2.0, "t_hi_ms": 2.0, "dead": 0.3,
    }
    for key, val in changed.items():
        alt = dict(base)
        alt[key] = val
        ck("changing %s writes a different record" % key,
           toolresults.params_hash(alt, keys) != h0,
           "%r -> %r hashed the same" % (base.get(key), val))

    # And the three methods are three questions, not one asked three ways.
    hs = {}
    for m in dspca.METHODS:
        hs[m] = toolresults.params_hash(dict(base, method=m), keys)
    ck("each method is its own record",
       len(set(hs.values())) == len(dspca.METHODS), hs)

    print("")
    print("THE DEFAULT IS THE ONE THAT WAS ASKED FOR")
    print("-" * 66)
    ck("a fresh question opens on delta", dspca.Params().method == "delta")
    ck("with the sink separation at 5 contacts, which is 150 um",
       dspca.Params().min_sep == 5)
    ck("and the gap column at 1, one column among many",
       dspca.Params().gap_weight == 1.0)

    print("")
    print("  %d ok, %d fail" % (len(OK), len(BAD)))
    return 1 if BAD else 0


if __name__ == "__main__":
    raise SystemExit(main())
