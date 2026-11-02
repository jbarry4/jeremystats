# -*- coding: utf-8 -*-
"""Check backend/derived.py, the on-disk cache of answers worked out from a
recording, and backend/streamjson.py, the streamed-answer framing.

    python tools/check_derived_cache.py

Runs in a temporary folder; touches nothing under GUI_logs.
"""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

import numpy as np  # noqa: E402

from backend import derived, streamjson  # noqa: E402

fails = 0


def check(what, ok, note=""):
    global fails
    if not ok:
        fails += 1
    print(("ok    " if ok else "FAIL  ") + what + (("   [%s]" % note) if note and not ok else ""))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        derived.configure(tmp)
        data = os.path.join(tmp, "CSC1.ncs")
        with open(data, "wb") as fh:
            fh.write(b"x" * 1000)
        ident = derived.file_ident(data)
        check("a file has an identity", isinstance(ident, list) and ident[0] == 1000, ident)
        key = {"file": data, "ident": ident, "ch": 1, "bins": 900}

        check("nothing kept to start with", derived.get_json("overview", key) is None)
        derived.put_json("overview", key, {"ok": True, "lo": [1, 2, 3]})
        got = derived.get_json("overview", key)
        check("kept and read back", got == {"ok": True, "lo": [1, 2, 3]}, got)

        # The file changes: a different identity, so the old answer is not found.
        time.sleep(0.02)
        with open(data, "ab") as fh:
            fh.write(b"y")
        key2 = dict(key, ident=derived.file_ident(data))
        check("a changed file is a different key", key2["ident"] != key["ident"])
        check("so the old answer is not handed back",
              derived.get_json("overview", key2) is None)

        # Arrays, with a meta dict.
        f = np.linspace(0, 100, 201)
        g = np.random.default_rng(1).random((201, 700))
        derived.put_arrays("bandgram", key, {"freqs": f, "grid": g},
                           {"step_s": 0.5, "gaps": [1, 2]})
        got = derived.get_arrays("bandgram", key)
        check("arrays come back exactly", got is not None
              and np.array_equal(got["freqs"], f) and np.array_equal(got["grid"], g))
        check("with their meta", got and got.get("meta", {}).get("gaps") == [1, 2],
              got and got.get("meta"))

        # A corrupt entry is "not kept", never an error.
        p = derived._path("overview", key, ".json")
        with open(p, "wb") as fh:
            fh.write(b"{not json")
        check("a corrupt entry reads as nothing", derived.get_json("overview", key) is None)

        # The cap: oldest-used first.
        for i in range(10):
            derived.put_json("big", {"i": i}, {"pad": "z" * 20000})
            ep = derived._path("big", {"i": i}, ".json")
            os.utime(ep, (time.time() - 1000 + i, time.time() - 1000 + i))
        derived.get_json("big", {"i": 0})            # used now: newest
        derived.prune(cap=5 * 20100)
        left = [i for i in range(10) if os.path.exists(derived._path("big", {"i": i}, ".json"))]
        check("the cap removes the least recently used", 0 in left and len(left) <= 6,
              left)

        # Unconfigured: everything is a quiet no.
        derived._ROOT[0] = None
        check("unconfigured reads nothing", derived.get_json("overview", key) is None)
        check("and writes nothing", derived.put_json("overview", key, {"a": 1}) is False)

    # streamjson: the framing.
    lines = list(streamjson.lines({"what": "t"}, iter([1, 2, 3]),
                                  tail=lambda: {"sum": 6}))
    objs = [json.loads(x) for x in lines]
    check("a head line first", objs[0] == {"head": {"what": "t"}}, objs[0])
    check("one line per item", [o.get("item") for o in objs[1:4]] == [1, 2, 3])
    check("a done line last, with the tail", objs[-1] == {"done": True, "n": 3, "sum": 6},
          objs[-1])
    check("every line ends in a newline", all(x.endswith("\n") for x in lines))

    def boom():
        yield 1
        raise ValueError("drive went away")
    objs = [json.loads(x) for x in streamjson.lines({}, boom())]
    check("a failure part-way keeps what got through", objs[1] == {"item": 1})
    check("and says what went wrong", objs[-1].get("error") == "drive went away"
          and objs[-1].get("n") == 1, objs[-1])

    print("\n%d failed" % fails if fails else "\nall passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
