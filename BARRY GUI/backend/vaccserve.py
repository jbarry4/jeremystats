"""
vaccserve.py -- the cluster half of reading a recording live.

    cd <workspace>/code && python -u -m backend.vaccserve

THE WHOLE POINT IS THAT THIS IS NOT A PORT

Same argument `vacc_run.py` makes, arriving at a different place. That file
runs an analysis on a compute node; this one answers a viewer on somebody's
desk. Both import `backend.csc` and call the function the desktop calls, and
neither reimplements a single line of arithmetic. A second envelope, a second
filter chain or a second seek-by-timestamp would be a second thing to keep in
step with `csc.py`, and two implementations of one measurement is how a lab
ends up with two answers and no way to tell which is right.

So the ops below are a lookup table of functions that already exist. What is
new here is only the wire.

WHY A PROCESS RATHER THAN A COMMAND PER READ

`vacc.py::_ssh` starts a connection per call, which is right for everything
it does: a status poll, a directory listing, a scan. A viewer is different.
Scrubbing a trace asks for a window several times a second, and a fresh ssh
handshake per window is a second of latency on every one of them -- so this
is started once, kept on stdin/stdout, and asked repeatedly.

It also means the opened session is cached HERE. The header read, the
channel scheme and the record-count arithmetic happen once per recording
rather than once per window, which is the difference between a scrub that
tracks the pointer and one that does not.

WHAT CROSSES THE WIRE IS THE ANSWER, NOT THE DATA

Measured on `M2ctls3jan23`, 64 channels at 30 kHz: ten seconds of it is
39 MB of raw records, and the same window enveloped to the 1400 columns the
viewer actually draws is 2.9 MB. The envelope is what the browser was going
to be sent either way. So `csc.get_window` runs on this side, complete with
its filters, and what goes back is the payload the viewer draws -- 1.3 s for
that window through the real route, against 1.8 s to open the recording.

This is the same split `toolresults.py` makes and for the same reason: send
the numbers somebody reads, not the array they were computed from.

THE MARKER

Every reply is one line, prefixed `@@JV1 `. Nothing else on stdout is a
reply. `module load` and `conda activate` both print on occasion, an MOTD
lands on the first line of a login shell, and a reader that assumed "the
next line is my answer" would parse the message of the day as JSON exactly
once per cluster upgrade.
"""
from __future__ import annotations

import json
import os
import sys
import traceback

# Same shape as vacc_run.py: the pushed tree has `backend/` in it, and the
# process is started from the directory above it.
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

PROTO = "@@JV1 "

# Opened sessions, keyed by what distinguishes them. Unbounded on purpose:
# one entry is a channel list and a few floats, a viewer holds a dozen
# recordings open at the very most, and this process is short-lived -- it is
# reaped the moment the desk stops asking.
_SESSIONS = {}


def emit(obj):
    """One reply, marked and flushed.

    Flushed because stdout to a pipe is block-buffered, and a reply that sits
    in a 4 KB buffer until the next one fills it is a viewer that waits for a
    window it has already been sent.
    """
    sys.stdout.write(PROTO + json.dumps(obj) + "\n")
    sys.stdout.flush()


def _session(req):
    """The recording this request is about, opened once and kept.

    `even_only` is passed through as None when the caller did not say, which
    is what makes `nlx.channel_scheme` decide -- see `csc.open_session`. The
    key carries it either way so that forcing it opens a second entry rather
    than quietly reusing the first.
    """
    from backend import csc

    path = req.get("path") or ""
    even = req.get("even_only")
    even = None if even is None else bool(even)
    invert = bool(req.get("invert", True))
    key = "%s|%s|%s" % (path, even, invert)
    if key not in _SESSIONS:
        sess = csc.open_session(path, even_only=even, invert=invert)
        if not sess.get("ok"):
            return None, sess
        _SESSIONS[key] = sess
    return _SESSIONS[key], None


def op_hello(req):
    """What this Python is, so a disagreement is visible rather than found.

    The same question `vacc.env_check` asks, answered by the process that
    will actually do the reading rather than by a separate one -- which is
    the point. `env_check` proves an environment exists; this proves the
    environment the viewer is talking to.
    """
    import numpy

    try:
        import scipy
        scipy_v = scipy.__version__
    except Exception:                                    # noqa: BLE001
        scipy_v = None
    return {
        "ok": True,
        "python": "%d.%d.%d" % sys.version_info[:3],
        "exe": sys.executable,
        "numpy": numpy.__version__,
        "scipy": scipy_v,
        "cwd": os.getcwd(),
        "pid": os.getpid(),
    }


def op_open(req):
    """The channel inventory and timing, read from the cluster's copy.

    `file` is left on each channel deliberately. It is a path on THIS
    filesystem and means nothing on the desk -- but `app.py` already strips
    it before anything reaches a browser, and keeping it means a session
    that came back from here is the same shape as one opened locally.
    """
    sess, err = _session(req)
    if err:
        return err
    out = dict(sess)
    out["nev"] = _nev(sess.get("path"))
    return out


def _nev(folder):
    """Cheetah's own event files beside the recording, named and sized.

    Listed rather than read. Whether the desk can do anything with one is
    its own question -- what this answers is "there are three of them and
    they are this big", which is the difference between an empty list
    meaning "none" and an empty list meaning "nobody looked".
    """
    out = []
    try:
        for name in sorted(os.listdir(folder or "")):
            if name.lower().endswith(".nev"):
                full = os.path.join(folder, name)
                try:
                    out.append({"name": name, "path": full,
                                "bytes": os.path.getsize(full)})
                except OSError:
                    continue
    except OSError:
        pass
    return out


def op_window(req):
    from backend import csc

    sess, err = _session(req)
    if err:
        return err
    args = dict(req.get("args") or {})
    t0 = float(args.pop("t0", 0.0))
    t1 = float(args.pop("t1", 10.0))
    return csc.get_window(sess, t0, t1, **args)


def op_overview(req):
    from backend import extras

    sess, err = _session(req)
    if err:
        return err
    return extras.overview(sess, **(req.get("args") or {}))


def op_band(req):
    from backend import extras

    sess, err = _session(req)
    if err:
        return err
    return extras.band_profile(sess, **(req.get("args") or {}))


def op_nev(req):
    """One .nev beside the recording, on the recording's own clock.

    The same `nlx.nev_events` the desk calls, and the same resolution against
    the first CSC timestamp -- which is why the recording is opened here too
    rather than the timestamp being sent from the desk. A .nev read against
    the wrong t0 is a set of events that land plausibly and in the wrong
    place, which is the worst kind of wrong this file could produce.

    The file must sit inside the recording's own folder. It arrives from a
    browser and is about to be opened under somebody's netid on a shared
    cluster; nothing here needs to read outside the folder it was asked
    about, so nothing here may.
    """
    import numpy as np

    from backend import nlx

    sess, err = _session(req)
    if err:
        return err
    folder = os.path.abspath(sess.get("path") or "")
    nev = os.path.abspath(req.get("nev") or "")
    if os.path.dirname(nev) != folder:
        return {"ok": False,
                "error": "That event file is not in this recording's folder."}
    if not os.path.isfile(nev):
        return {"ok": False, "error": "Not found: " + nev}

    t_start = req.get("t_start_us")
    if t_start is None:
        try:
            first = (sess.get("channels") or [{}])[0].get("file")
            with open(first, "rb") as fh:
                fh.seek(nlx.HEADER_BYTES)
                rec = np.fromfile(fh, dtype=nlx.RECORD_DTYPE, count=1)
            t_start = float(rec["timestamp"][0]) if rec.size else None
        except Exception:                                # noqa: BLE001
            t_start = None

    evs, meta = nlx.nev_events(nev, t_start_us=t_start)
    return {"ok": True, "events": evs, "path": nev, "n": meta.get("n", 0),
            "relative_to": meta.get("relative_to"),
            "labels": meta.get("labels", [])}


# An allowlist, not a dispatch on whatever name arrived.
#
# The desk is trusted -- it is the same person's machine over their own SSH
# key -- but "trusted" is not a reason to let a string from a browser pick
# which function runs on a shared cluster under somebody's netid. Four names
# that map to four functions, and anything else is an error with the name in
# it rather than an AttributeError.
OPS = {
    "hello": op_hello,
    "open": op_open,
    "window": op_window,
    "overview": op_overview,
    "band": op_band,
    "nev": op_nev,
}


def main():
    emit({"ok": True, "ready": True, "proto": 1})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        rid = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            name = req.get("op")
            if name == "bye":
                emit({"id": rid, "ok": True, "bye": True})
                return
            fn = OPS.get(name)
            if fn is None:
                emit({"id": rid, "ok": False,
                      "error": "No such op: %r" % (name,)})
                continue
            got = fn(req)
            if isinstance(got, dict):
                got = dict(got)
                got["id"] = rid
            emit(got)
        except ModuleNotFoundError as exc:
            # The one failure that is about the cluster rather than about the
            # request, and it reads as nonsense unless it is named: the
            # analysis environment here is built from `requirements.txt` and
            # can be older than the desk's. Answered with the package and the
            # fix rather than with an import traceback, because the person
            # reading it is looking at a trace window, not a terminal.
            emit({"id": rid, "ok": False,
                  "error": ("The cluster's analysis environment does not have "
                            "%s. Everything else still works; rebuild it with "
                            "`pip install -r requirements.txt` into %s."
                            % (getattr(exc, "name", None) or str(exc),
                               sys.prefix)),
                  "missing": getattr(exc, "name", None)})
        except Exception as exc:                         # noqa: BLE001
            # Never die on one bad request. A viewer that asked for a window
            # past the end of a file must get an error and keep its link,
            # not lose the connection and pay for a new one.
            emit({"id": rid, "ok": False, "error": "%s: %s"
                  % (type(exc).__name__, exc),
                  "trace": traceback.format_exc()[-2000:]})


if __name__ == "__main__":
    main()
