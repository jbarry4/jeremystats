"""
test_warmcache.py -- Prove the warm start cannot show you a stale answer.

The warm cache exists to make "Wake up Jarvis" fast: the three roll-ups that
take five seconds each from cold are answered out of last boot's file while
the real ones are recomputed behind the page. That trade is only acceptable
because of the rules that bound it, so this checks the rules rather than the
speed -- a cache that is fast and occasionally wrong is worse than the wait
it replaced.

One rule per section, in the order they appear in warmcache.py's docstring:

    1. only the launcher opens the window
    2. a name stops being cacheable once its live value exists
    3. the window closes when somebody does something
    4. it closes on its own after the deadline
    5. a code change voids everything written by the old code

Plus the three that are not rules but are how it actually behaves: nothing is
written by a process that was never armed, an unchanged answer is reported as
unchanged, and a build that throws does not take the prime down with it.

    python tools/test_warmcache.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import warmcache  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    print("  %-62s %s" % (name, "ok" if ok else "FAILED"))
    if not ok:
        print("      got  %r" % (got,))
        print("      want %r" % (want,))
        FAILED.append(name)


def fresh(tmp, stamp="v1"):
    return warmcache.WarmCache(tmp, stamp=stamp)


def counter(value):
    """A builder that says how many times it has been called."""
    state = {"n": 0, "value": value}

    def build():
        state["n"] += 1
        return {"ok": True, "value": state["value"], "built": state["n"]}
    build.state = state
    return build


# ==========================================================================
def rule_1_only_the_launcher(tmp):
    print("\n1. Only the launcher opens the window")
    w = fresh(tmp)
    b = counter("first")
    # Never armed: this is the harness suite, or a script.
    body, how = w.serve("thing", b)
    check("an unarmed cache serves live", how, "live")
    check("and it built", b.state["n"], 1)
    check("an unarmed cache writes nothing",
          os.path.exists(os.path.join(tmp, ".cache", "warm", "thing.json")),
          False)
    body, how = w.serve("thing", b)
    check("still live the second time", how, "live")
    check("and it built again -- no memoising behind the app's back",
          b.state["n"], 2)


def rule_2_live_wins(tmp):
    print("\n2. Once the live value exists, the cache never answers again")
    w = fresh(tmp)
    w.arm()
    b = counter("first")
    w.serve("thing", b)                       # no file yet -> builds, writes
    check("first call built it", b.state["n"], 1)

    w2 = fresh(tmp)                           # a new process, same disk
    w2.arm()
    b2 = counter("second")
    body, how = w2.serve("thing", b2)
    check("next boot is served from the cache", how, "cache")
    check("and did not build", b2.state["n"], 0)
    check("what came back is what was written", body["value"], "first")

    body, how = w2.serve("thing", b2, fresh=True)
    check("?fresh=1 goes to the builder", how, "live")
    check("and it built", b2.state["n"], 1)
    body, how = w2.serve("thing", b2)
    check("every call after that is live, window open or not", how, "live")
    check("and built again", b2.state["n"], 2)


def rule_3_a_click_closes_it(tmp):
    print("\n3. A click closes the window")
    w = fresh(tmp)
    w.arm()
    counter_b = counter("x")
    w.serve("thing", counter_b)               # writes the file

    w2 = fresh(tmp)
    w2.arm()
    w2.note_write("/api/activity")
    check("boot chatter leaves it open", w2.armed, True)
    w2.note_write("/api/prefs")
    check("so does the theme write-back", w2.armed, True)
    _body, how = w2.serve("thing", counter("y"))
    check("and the cache still answers", how, "cache")

    w2.note_write("/api/curation/save")
    check("a real write closes it", w2.armed, False)
    b = counter("y")
    _body, how = w2.serve("other", b)
    check("after which nothing is served from cache", how, "live")


def rule_4_the_deadline(tmp):
    print("\n4. It closes on its own")
    w = fresh(tmp)
    w.arm()
    w.serve("thing", counter("x"))

    w2 = fresh(tmp)
    w2.arm(window_s=0.25)
    _body, how = w2.serve("thing", counter("y"))
    check("inside the window, cached", how, "cache")
    time.sleep(0.4)
    check("past it, the window is shut", w2.armed, False)
    _body, how = w2.serve("thing2", counter("y"))
    check("and the cache no longer answers", how, "live")


def rule_5_a_code_change_voids_it(tmp):
    print("\n5. A code change voids what the old code wrote")
    w = fresh(tmp, stamp="2026.09.21.1|abc1234")
    w.arm()
    w.serve("thing", counter("old shape"))

    w2 = fresh(tmp, stamp="2026.09.22.1|def5678")   # somebody pulled
    w2.arm()
    b = counter("new shape")
    body, how = w2.serve("thing", b)
    check("a cache written by other code is ignored", how, "live")
    check("so the new code builds its own", body["value"], "new shape")

    w3 = fresh(tmp, stamp="2026.09.22.1|def5678")
    w3.arm()
    _body, how = w3.serve("thing", counter("z"))
    check("and the next boot on the new code gets it", how, "cache")


def unchanged_is_reported_as_unchanged(tmp):
    print("\nAn answer that has not changed says so")
    w = fresh(tmp)
    w.arm()
    w.serve("thing", counter("same"))          # writes it

    w2 = fresh(tmp)
    w2.arm()
    _body, how = w2.serve("thing", counter("same"))
    check("served from cache", how, "cache")
    # The prime recomputes it and finds the same answer.
    w2._build_live("thing", counter("same"))
    check("the live rebuild is in hand", "thing" in w2.state()["fresh"], True)
    check("and it is reported as NOT changed -- the page does nothing",
          w2.state()["fresh"]["thing"], False)

    w3 = fresh(tmp)
    w3.arm()
    w3.serve("thing", counter("same"))
    w3._build_live("thing", counter("DIFFERENT"))
    check("a real change is reported as changed",
          w3.state()["fresh"]["thing"], True)


def a_timestamp_is_not_a_change(tmp):
    print("\nA field that moves on its own is not a change")
    stamps = {"n": 0}

    def build():
        stamps["n"] += 1
        # Same data every time; a different "when" every time. This is
        # exactly the shape of STORE.index().
        return {"ok": True,
                "index": {"generated": "2026-09-21T08:%02d:00" % stamps["n"],
                          "counts": {"sessions": 687}}}

    w = fresh(tmp)
    w.volatile("thing", ["index.generated"])
    w.arm()
    w.serve("thing", build)                    # writes it

    w2 = fresh(tmp)
    w2.volatile("thing", ["index.generated"])
    w2.arm()
    body, how = w2.serve("thing", build)
    check("served from cache", how, "cache")
    check("and it carries the timestamp it was written with",
          body["index"]["generated"], "2026-09-21T08:01:00")
    w2._build_live("thing", build)
    check("a new timestamp over identical data is NOT a change",
          w2.state()["fresh"]["thing"], False)

    # And the data underneath it still is.
    def moved():
        return {"ok": True,
                "index": {"generated": "2026-09-21T09:00:00",
                          "counts": {"sessions": 688}}}

    w3 = fresh(tmp)
    w3.volatile("thing", ["index.generated"])
    w3.arm()
    w3.serve("thing", build)
    w3._build_live("thing", moved)
    check("but a count that moved underneath it is",
          w3.state()["fresh"]["thing"], True)

    # A directory of its own. `w3` left a body on disk with a different
    # count in it, and a fourth cache pointed at the same directory reads
    # that, rebuilds over it and reports a change -- which is correct
    # behaviour being mistaken for the thing under test.
    print("  (and a path that is not there changes nothing)")
    sub = os.path.join(tmp, "unknown-path")
    os.makedirs(sub)
    w4 = fresh(sub)
    w4.volatile("thing", ["nowhere.at.all", "index.generated"])
    w4.arm()
    w4.serve("thing", build)               # first boot: writes it
    w5 = fresh(sub)                        # second boot: has something to
    w5.volatile("thing", ["nowhere.at.all", "index.generated"])
    w5.arm()
    w5.serve("thing", build)               # compare against
    w5._build_live("thing", build)
    check("an unknown path is ignored rather than raising",
          w5.state()["fresh"]["thing"], False)


def a_list_and_a_tuple_are_the_same_answer(tmp):
    print("\nA tuple read back as a list is not a change")
    # Everything that goes through JSON comes back as a list, and half of
    # what the registry builds is tuples. Compared as objects these differ
    # on every boot; compared as JSON text they do not, which is why the
    # fingerprint is taken on the text.
    w = fresh(tmp)
    w.arm()
    w.serve("thing", lambda: {"ok": True, "values": [("a", 1), ("b", 2)]})

    w2 = fresh(tmp)
    w2.arm()
    body, how = w2.serve("thing", lambda: {"ok": True, "values": []})
    check("served from cache", how, "cache")
    check("and came back as lists", body["values"][0], ["a", 1])
    w2._build_live("thing", lambda: {"ok": True,
                                     "values": [("a", 1), ("b", 2)]})
    check("tuples rebuilt over cached lists are not a change",
          w2.state()["fresh"]["thing"], False)


def two_jarvises_do_not_corrupt_each_other(tmp):
    print("\nTwo Jarvises on one machine write whole files")
    # An ordinary thing -- a second window opened rather than the first one
    # found -- and they share GUI_logs/.cache/warm. Ten threads, two bodies
    # that differ in length, all writing the same name at once: every read
    # in between must come back as one of the two, never as a splice.
    import threading as th
    w = fresh(tmp)
    w.arm()
    big = {"ok": True, "rows": [{"i": i, "pad": "x" * 200} for i in range(400)]}
    small = {"ok": True, "rows": [{"i": i} for i in range(5)]}
    stop = [False]
    torn = []

    def writer(body):
        for _ in range(12):
            w.write("thing", body)

    def reader():
        while not stop[0]:
            got = w.read("thing")
            if got is not None and got not in (big, small):
                torn.append(got)

    threads = [th.Thread(target=writer, args=(big,)) for _ in range(5)]
    threads += [th.Thread(target=writer, args=(small,)) for _ in range(5)]
    rt = th.Thread(target=reader)
    rt.start()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stop[0] = True
    rt.join()

    check("no reader ever saw a spliced body", torn, [])
    check("what is on disk is one of the two", w.read("thing") in (big, small),
          True)
    leftovers = [f for f in os.listdir(os.path.join(tmp, ".cache", "warm"))
                 if f.endswith(".part")]
    check("and no half-written file was left behind", leftovers, [])


def a_broken_build_does_not_stop_the_rest(tmp):
    print("\nOne roll-up that throws does not take the prime with it")
    w = fresh(tmp)
    w.arm()

    def boom():
        raise RuntimeError("the drive went away")

    good = counter("fine")
    w.prime([("bad", boom), ("good", good)], delay=0)
    for _ in range(100):
        if not w.state()["warming"]:
            break
        time.sleep(0.05)
    check("the prime finished", w.state()["warming"], False)
    check("the one after the failure still ran", good.state["n"], 1)
    check("and the window is shut afterwards", w.armed, False)
    check("the failed one is listed, so the page stops waiting for it",
          "bad" in w.state()["fresh"], True)


def a_half_written_file_is_not_trusted(tmp):
    print("\nA damaged cache file reads as no cache file")
    w = fresh(tmp)
    w.arm()
    w.serve("thing", counter("x"))
    path = os.path.join(tmp, ".cache", "warm", "thing.json")
    with open(path, "r+", encoding="utf-8") as fh:
        text = fh.read()
        fh.seek(0)
        fh.truncate()
        fh.write(text[:len(text) // 2])        # cut it in half

    w2 = fresh(tmp)
    w2.arm()
    b = counter("y")
    _body, how = w2.serve("thing", b)
    check("truncated JSON falls through to the builder", how, "live")
    check("which is the behaviour from before this module existed",
          b.state["n"], 1)


def main():
    tmp = tempfile.mkdtemp(prefix="jarvis-warm-test-")
    try:
        for fn in (rule_1_only_the_launcher, rule_2_live_wins,
                   rule_3_a_click_closes_it, rule_4_the_deadline,
                   rule_5_a_code_change_voids_it,
                   unchanged_is_reported_as_unchanged,
                   a_timestamp_is_not_a_change,
                   a_list_and_a_tuple_are_the_same_answer,
                   two_jarvises_do_not_corrupt_each_other,
                   a_broken_build_does_not_stop_the_rest,
                   a_half_written_file_is_not_trusted):
            # A directory each, so one section cannot see another's files.
            sub = os.path.join(tmp, fn.__name__)
            os.makedirs(sub)
            fn(sub)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print("%d FAILED: %s" % (len(FAILED), ", ".join(FAILED)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
