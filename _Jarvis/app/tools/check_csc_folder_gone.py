# -*- coding: utf-8 -*-
"""A recording whose folder is renamed while it is open says so in plain
words, and the next read opens the path afresh.

2026-11-04, Strawbarry: Rain renamed `KCNT1_529_s1apr17` to
`KCNT1_m529_s1_apr17` on Y: with it open. /api/csc/window answered from the
opening `_SESSIONS` still held, and failed with a bare "[WinError 3] The
system cannot find the path specified". Every later read of that path
would have gone to the same cached opening and failed the same way.

No server and nothing written under GUI_logs: a one-channel recording is
made in a temp folder, the real route is asked through Flask's test client,
and the error log is stood in for in memory.

    python tools/check_csc_folder_gone.py
"""
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
# Before the import: no day-report loop or warm-up threads for a check.
os.environ.setdefault("BARRY_HARNESS_SERVER", "1")

from backend import app as A  # noqa: E402
from backend import nlx  # noqa: E402

ok = bad = 0


def check(name, cond, got=None):
    global ok, bad
    if cond:
        ok += 1
        print("  ok    %s" % name)
    else:
        bad += 1
        print("  FAIL  %s\n        got %r" % (name, got))


def make_recording(folder, n_rec=200, fs=30000.0):
    os.makedirs(folder)
    head = ("######## Neuralynx Data File Header\r\n"
            "-SamplingFrequency %s\r\n-ADBitVolts 0.000000030500\r\n"
            "-TimeCreated 2026/04/17 12:55:27\r\n" % fs).encode("ascii")
    head = head.ljust(nlx.HEADER_BYTES, b"\0")
    recs = np.zeros(n_rec, dtype=nlx.RECORD_DTYPE)
    step = 1e6 * nlx.SAMPLES_PER_RECORD / fs
    recs["timestamp"] = (np.arange(n_rec) * step).astype("<u8")
    recs["freq"] = int(fs)
    recs["nvalid"] = nlx.SAMPLES_PER_RECORD
    recs["samples"] = (np.random.RandomState(0).randn(n_rec, nlx.SAMPLES_PER_RECORD) * 200).astype("<i2")
    with open(os.path.join(folder, "CSC1.ncs"), "wb") as fh:
        fh.write(head)
        fh.write(recs.tobytes())


logged = []
A.STORE.record_error = lambda where, message, detail=None, context=None, *a, **k: (
    logged.append((where, message)) or {"id": "check"})
A._gid_for_path = lambda path: "scheck"

root = tempfile.mkdtemp(prefix="csc_gone_")
try:
    old = os.path.join(root, "KCNT1_529_s1apr17")
    new = os.path.join(root, "KCNT1_m529_s1_apr17")
    make_recording(old)
    client = A.app.test_client()
    body = {"path": old, "t0": 0, "t1": 1, "px": 400}

    r = client.post("/api/csc/window", json=body)
    check("the window reads while the folder is there", r.status_code == 200, (r.status_code, r.get_json()))
    key = "%s|%s" % (os.path.abspath(old), True)
    check("the opening is kept", key in A._SESSIONS)

    os.rename(old, new)
    r = client.post("/api/csc/window", json=body)
    got = r.get_json() or {}
    check("after the rename it is refused", r.status_code == 400, r.status_code)
    check("in plain words", "no longer at" in (got.get("error") or ""), got.get("error"))
    check("with no WinError in it", "WinError" not in (got.get("error") or ""), got.get("error"))
    check("the stale opening is let go", key not in A._SESSIONS, list(A._SESSIONS))

    r = client.post("/api/csc/window", json=body)
    got = r.get_json() or {}
    check("the next read opens it afresh: Path not found",
          r.status_code == 400 and "Path not found" in (got.get("error") or ""), (r.status_code, got))

    r = client.post("/api/csc/window", json=dict(body, path=new))
    check("it reads from where it is now", r.status_code == 200, (r.status_code, r.get_json()))
finally:
    A._SESSIONS.clear()
    shutil.rmtree(root, ignore_errors=True)

print("\n%d ok, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
