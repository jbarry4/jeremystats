"""
test_times.py -- Two timestamps are compared as times, not as text.

The same fault turned up in eleven places in one day -- six comparisons and
five orderings: a stamp compared with `>` or `<` against another stamp, which
is only right while both carry the same offset. In this application they do not. Anything that came down from
Supabase is UTC; anything written here carries this machine's offset. So

    2026-09-10T00:37:00+00:00      (UTC)
    2026-09-09T20:41:00-04:00      (Vermont, four minutes LATER)

sort the wrong way round as text, and whatever the comparison decided --
which push to send, whose curation label wins, whether an error is resolved,
whose feedback state is current -- came out backwards.

This covers the comparison, the sort key, and the feedback merges that use
them, driven against a scratch directory. It writes nothing outside a temp folder.

    python tools/test_times.py
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import extras, feedback  # noqa: E402

FAILED = []

# The same afternoon, written two ways. Vermont is UTC-4.
LOCAL_LATE = "2026-09-09T20:41:00-04:00"     # 00:41 UTC -- the later one
UTC_EARLY = "2026-09-10T00:37:00+00:00"      # 20:37 local -- four min before


def check(name, got, want):
    ok = got == want
    print("  %-58s %s" % (name, "ok" if ok else "FAILED"))
    if not ok:
        print("      got  %r" % (got,))
        print("      want %r" % (want,))
        FAILED.append(name)


def the_comparison():
    """`marked_after(a, b)` -- is a at or before b?"""
    print("the comparison")
    # The case measured on this machine: an error in UTC, a mark made three
    # minutes later in local time. As text the error sorts later and the
    # error stayed red however many times somebody resolved it.
    check("a local mark after a UTC error resolves it",
          extras.marked_after("2026-09-10T00:37:57+00:00",
                              "2026-09-09T20:40:45-04:00"), True)
    check("a mark from before the error does not",
          extras.marked_after("2026-09-10T00:37:57+00:00",
                              "2026-09-09T20:30:00-04:00"), False)
    check("one offset on both sides, which always worked",
          extras.marked_after("2026-09-09T20:37:57-04:00",
                              "2026-09-09T20:40:45-04:00"), True)
    # Stamps are not written uniformly either: the feedback store writes
    # "-0400" with no colon, which `fromisoformat` will not take raw.
    check("an offset written without its colon",
          extras.marked_after("2026-09-09T18:03:57-0400",
                              "2026-09-09T18:04:00-0400"), True)
    check("no offset at all is this machine's clock",
          extras.marked_after("2026-09-09 20:37:57",
                              "2026-09-09T20:40:45-04:00"), True)
    check("nothing to compare against is not after",
          extras.marked_after("2026-09-09T20:37:57-04:00", None), False)
    check("nothing to compare is after anything",
          extras.marked_after(None, "2026-09-09T20:40:45-04:00"), True)


def the_sort_key():
    """`moment_key(stamp)` -- a stamp as a number the sorts can use."""
    print("the sort key")
    # The lists that use this hold both offsets at once, so "newest first"
    # has to put the local 20:41 above the UTC 00:37 that is four minutes
    # older -- as text it went below it.
    check("local 20:41 sorts after UTC 00:37, which is older",
          extras.moment_key(LOCAL_LATE) > extras.moment_key(UTC_EARLY), True)
    check("the two are four minutes apart",
          round((extras.moment_key(LOCAL_LATE)
                 - extras.moment_key(UTC_EARLY)) / 60), 4)
    check("unreadable sorts as the epoch, where \"\" sorted",
          extras.moment_key("not a time"), 0.0)
    check("missing sorts as the epoch", extras.moment_key(None), 0.0)


def _write(fb, rid, shard, **fields):
    rec = {"id": rid, "kind": "bug", "title": "t", "detail": "",
           "state": "open", "at": "2026-09-09T09:00:00-04:00", "by": "me",
           "machine": shard, "shard": shard, "notes": []}
    rec.update(fields)
    os.makedirs(fb.dir, exist_ok=True)
    with io.open(os.path.join(fb.dir, "%s@%s.json" % (rid, shard)), "w",
                 encoding="utf-8", newline=chr(10)) as fh:
        json.dump(rec, fh, indent=1)


def _state(fb, rid):
    for r in fb.all():
        if r.get("id") == rid:
            return r.get("state")
    return None


def the_feedback_merge(root):
    """Whose state is current, and which copy of a report is the original."""
    print("the feedback merge")

    def fresh():
        shutil.rmtree(os.path.join(root, "feedback"), ignore_errors=True)
        return feedback.Feedback(root)

    # A report acknowledged here at 20:41 must not be reopened by a row from
    # the shared table stamped four minutes earlier.
    fb = fresh()
    _write(fb, "r1", fb.machine, state="done", state_at=LOCAL_LATE)
    fb.absorb({"id": "r1", "state": "open", "state_at": UTC_EARLY,
               "state_by": "them", "created_at": "2026-09-09T09:00:00-04:00"})
    check("an older UTC row does not undo a newer local mark",
          _state(fb, "r1"), "done")

    # And a genuinely newer one still lands, or the fix would just be a
    # different way of being wrong.
    fb = fresh()
    _write(fb, "r2", fb.machine, state="open",
           state_at="2026-09-09T18:00:00-04:00")
    fb.absorb({"id": "r2", "state": "done", "state_at": UTC_EARLY,
               "state_by": "them", "created_at": "2026-09-09T09:00:00-04:00"})
    check("a newer UTC row is taken", _state(fb, "r2"), "done")

    # Two machines holding one report: the earlier copy is the original.
    fb = fresh()
    _write(fb, "r3", "alpha", at=LOCAL_LATE, title="the later copy")
    _write(fb, "r3", "beta", at=UTC_EARLY, title="the earlier copy")
    got = [r for r in fb.all() if r.get("id") == "r3"]
    check("one report, not two", len(got), 1)
    check("the earlier copy is the original",
          (got[0].get("title") if got else None), "the earlier copy")


def main():
    the_comparison()
    print()
    the_sort_key()
    print()
    root = tempfile.mkdtemp(prefix="barry-times-")
    try:
        the_feedback_merge(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if FAILED:
        print("%d check(s) FAILED: %s" % (len(FAILED), ", ".join(FAILED)))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
