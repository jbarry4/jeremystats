"""
vacc_run.py -- what actually runs on a compute node.

    python vacc_run.py <workspace>/runs/<rid>/spec.json

THE WHOLE POINT IS THAT THIS IS NOT A PORT

It imports `backend.incisor` and `backend.panorama` and calls the same
`run()` the desktop calls. No arithmetic is reimplemented here, and that is
not laziness -- `incisor.py` exists because Toothy's detection was worth
writing down once, with each step citing the line it came from, and a second
copy on the cluster would be a second thing to keep in step with it. Two
implementations of one measurement is how a lab ends up with two answers and
no way to tell which is right.

So this file is plumbing: read a spec, open the recording, call run(), write
the answer down. Everything it does that the desktop does not do is about
being on the far side of a wire.

PROGRESS IS A SHIM, NOT A JOB

`cfc.Job` is what `run()` expects to report progress to, and the real one
lives in a Flask process on somebody's desk. `JobShim` is the same three
methods -- begin, tick, check -- printing a line each instead. The poller on
the other end translates those back. Stage names are asserted against the
manifest the spec carries, because `Job.begin` on an unknown stage returns
silently: a typo here is a job that runs perfectly and shows no progress at
all, and nothing anywhere says why.

THE ANSWER IS WRITTEN ATOMICALLY, AND IT IS THE NUMBERS

`result.json.part` then `os.replace`. A job killed by scancel or a walltime
half way through writing must not leave a file the fetcher will happily read
as an answer.

What crosses the wire is the answer -- about thirty kilobytes -- and not the
picture. A spectrogram is megabytes and regenerable from the numbers in
milliseconds, so it stays here. `toolresults.py` makes the same split for the
same reason, and this is that reason arriving over a network.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def emit(obj):
    """One JSON object per line on stdout, flushed.

    Slurm buffers a job's stdout into a file; without the flush the progress
    of a two-hour run arrives in one lump when it finishes, which is the same
    as having none.
    """
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


class JobShim:
    """`cfc.Job`'s three methods, as far as a compute node needs them."""

    def __init__(self, stages):
        # The vocabulary the other end declared. Anything outside it is a
        # mistake worth stopping for rather than a line nobody reads.
        self.stages = set(stages or [])
        self._at = None
        self._t0 = time.time()

    def _check_name(self, name):
        if self.stages and name not in self.stages:
            raise KeyError(
                "stage %r was not declared for this run; the poller would "
                "drop it silently and the run would show no progress" % name)

    def begin(self, name, of=None, unit=None):
        self._check_name(name)
        self._at = name
        emit({"k": "begin", "stage": name, "of": of, "unit": unit,
              "t": round(time.time() - self._t0, 2)})

    def tick(self, name, done):
        self._check_name(name)
        emit({"k": "tick", "stage": name, "done": int(done),
              "t": round(time.time() - self._t0, 2)})

    def check(self):
        """Cancellation is scancel here, not a flag.

        There is nothing cooperative to check: the other end cancels by
        killing this process. Present because `run()` calls it.
        """
        return False

    # Panorama hands previews to a real Job. They are pictures, so they do
    # not travel; accepting and dropping them is the honest no-op.
    def set_preview(self, *a, **k):
        return None

    def members_init(self, *a, **k):
        return None

    def member(self, *a, **k):
        return None


def main(argv):
    if len(argv) < 2:
        emit({"k": "fatal", "error": "usage: vacc_run.py <spec.json>"})
        return 2
    spec_path = argv[1]
    with open(spec_path, "r", encoding="utf-8") as fh:
        bundle = json.load(fh)

    rid = bundle.get("rid")
    tool = bundle.get("tool")
    spec = bundle.get("spec") or {}
    out_dir = os.path.dirname(os.path.abspath(spec_path))
    job = JobShim(bundle.get("stages"))

    emit({"k": "start", "rid": rid, "tool": tool, "pid": os.getpid(),
          "host": os.uname().nodename if hasattr(os, "uname") else "?"})

    try:
        from backend import csc
        result = run_tool(tool, spec, bundle, job, csc)
    except Exception as exc:                             # noqa: BLE001
        emit({"k": "fatal", "error": "%s: %s" % (type(exc).__name__, exc),
              "traceback": traceback.format_exc(limit=12)})
        return 1

    tmp = os.path.join(out_dir, "result.json.part")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(result, fh)
    os.replace(tmp, os.path.join(out_dir, "result.json"))
    emit({"k": "done", "rid": rid,
          "bytes": os.path.getsize(os.path.join(out_dir, "result.json"))})
    return 0


def run_tool(tool, spec, bundle, job, csc):
    """Open the recording and call the tool's own `run`."""
    path = spec.get("path")
    if not path or not os.path.isdir(path):
        raise IOError("the recording is not readable here: %r" % (path,))

    session = csc.open_session(path, even_only=bool(spec.get("even_only")),
                               invert=bool(spec.get("invert", True)))

    if tool == "incisor":
        from backend import incisor
        # The continuity report travels WITH the spec rather than being
        # recomputed. It is in the cache key, and a segmentation that came
        # out even slightly differently here would give the answer a
        # different name -- a permanent cache miss that nothing reports.
        report = bundle.get("report")
        if report is None:
            from backend import continuity
            report = continuity.check(path)
        return incisor.run(session, spec, report, job)

    if tool == "panorama":
        from backend import panorama
        return panorama.run(session, spec, job)

    raise ValueError("no such tool: %r" % (tool,))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
