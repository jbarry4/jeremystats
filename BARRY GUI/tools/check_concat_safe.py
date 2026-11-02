# -*- coding: utf-8 -*-
"""Is an Incisor set protected from the correction it must never receive?

Incisor's times already account for acquisition gaps -- they are stamped from
the .ncs record clock. Applying the concatenation correction to them would
shift them AGAIN, by the full cumulative gap, and the result would look
entirely plausible. So three things have to hold, and none of them is
something to take on trust:

  1. `retime.offer` must refuse, with a reason, for an Incisor set on a
     recording that genuinely has gaps.
  2. `healthlog.summary` must not call that recording "unpatched", because
     that is the label the session list filters on and the thing that
     invites somebody to go and patch it.
  3. Toothy's own output must still be offered the correction, because it
     genuinely needs it -- a guard that refuses everything is not a guard.

Run: python tools/check_concat_safe.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import continuity, healthlog, retime          # noqa: E402

FAILED = []


def ck(name, ok, detail=""):
    print("  %-5s %s%s" % ("ok" if ok else "FAIL", name,
                           "" if ok else "   [%s]" % detail))
    if not ok:
        FAILED.append(name)


GAPPY = r"D:\PTEN\PTEN\M8_Pten\M8s9feb8\2024-02-09_16-43-46"


def entry(pipeline, stamped=None, n=100):
    """A bank entry as `BANK.add` would have written it."""
    e = {"id": "test-" + pipeline[:8], "gid": "g-test", "n": n,
         "name": "test set", "type": "ds",
         "source": {"pipeline": pipeline},
         "events": [{"start": 1.0 + i} for i in range(n)]}
    if stamped:
        e["time_basis"] = stamped
    return e


def main():
    rep = continuity.check(GAPPY)
    if not rep.get("ok"):
        print("could not segment %s" % GAPPY)
        raise SystemExit(1)
    print("recording: %d segments, %.3f s lost -- this one genuinely needs "
          "the correction" % (rep["n_segments"], rep["seconds_lost"]))
    print()

    print("What clock each pipeline is believed to be on")
    for pipe, want in (("ETS dentate-spike export", retime.CONCAT),
                       ("Incisor (dentate spike)", retime.TRUE),
                       ("Jarvis curation (ds)", retime.TRUE),
                       ("something nobody has written down", None)):
        got = retime.basis_of(entry(pipe))
        ck("%-34s -> %s" % (pipe[:34], got["basis"] or "unknown"),
           got["basis"] == want, "got %s" % got["basis"])
    print()

    print("Who is offered the correction")
    off_toothy = retime.offer(rep, entry("ETS dentate-spike export"))
    ck("Toothy's output IS offered it", bool(off_toothy.get("offer")),
       off_toothy.get("reason"))

    off_inc = retime.offer(rep, entry("Incisor (dentate spike)"))
    ck("an Incisor set is NOT offered it", not off_inc.get("offer"),
       "it was offered")
    ck("  and the refusal says why",
       bool(off_inc.get("reason")), "no reason given")
    if off_inc.get("reason"):
        print("       %s" % off_inc["reason"][:150])

    off_unknown = retime.offer(rep, entry("some other detector"))
    ck("an unrecognised pipeline is NOT offered it",
       not off_unknown.get("offer"), "it was offered")
    print()

    print("What the session list says about a recording holding each")
    # `summary` reads a bank; a stand-in with just `all()` is enough.
    class FakeBank(object):
        def __init__(self, entries):
            self._e = entries

        def all(self):
            return self._e

    log = _log_for(rep)
    for pipe, label in (("ETS dentate-spike export", "Toothy output"),
                        ("Incisor (dentate spike)", "an Incisor set")):
        e = entry(pipe)
        e["gid"] = log["gid"]
        rows = log["log"].summary(FakeBank([e]))
        row = rows.get(log["gid"]) or {}
        print("    %-18s concat_issue=%s patched=%s unpatched=%s"
              % (label, row.get("concat_issue"), row.get("patched"),
                 row.get("unpatched")))
        if pipe.startswith("Incisor"):
            ck("an Incisor set does not leave the recording 'unpatched'",
               not row.get("unpatched"),
               "the session list would show it as needing the correction")
            ck("  and it counts as dealt with", bool(row.get("patched")),
               "patched=%s" % row.get("patched"))
        else:
            ck("Toothy output DOES leave it 'unpatched'",
               bool(row.get("unpatched")), "not flagged")

    print()
    print("Mixtures -- the case most likely to be got wrong")
    # "The DS is safe, either because it was corrected or because it was
    # generated in house" -- so a recording holding one of each is safe, and
    # one holding an uncorrected Toothy set is not, however much in-house
    # work sits beside it.
    corrected = entry("ETS dentate-spike export",
                      stamped={"kind": retime.TRUE})
    corrected["gid"] = log["gid"]
    inhouse = entry("Incisor (dentate spike)")
    inhouse["gid"] = log["gid"]
    raw_toothy = entry("ETS dentate-spike export")
    raw_toothy["gid"] = log["gid"]

    for label, sets, want_patched, want_safe in (
            ("all in house", [inhouse], True, True),
            ("corrected only", [corrected], True, False),
            ("one of each", [inhouse, corrected], True, False),
            ("in house + uncorrected", [inhouse, raw_toothy], False, False)):
        rows = log["log"].summary(FakeBank(list(sets)))
        row = rows.get(log["gid"]) or {}
        print("    %-24s patched=%-5s all_concat_safe=%-5s unpatched=%s"
              % (label, row.get("patched"), row.get("all_concat_safe"),
                 row.get("unpatched")))
        ck("%s: patched is %s" % (label, want_patched),
           bool(row.get("patched")) == want_patched,
           "got %s" % row.get("patched"))
        ck("  and concat-safe is %s" % want_safe,
           bool(row.get("all_concat_safe")) == want_safe,
           "got %s" % row.get("all_concat_safe"))
    ck("an uncorrected Toothy set still flags the recording",
       bool((log["log"].summary(FakeBank([inhouse, raw_toothy]))
             .get(log["gid"]) or {}).get("unpatched")),
       "it was not flagged")

    print()
    print("A recording with NO gaps: nothing should be adjusted at all")
    # The correction is not something Incisor applies -- it is an error it
    # never introduces. On a gapless recording that has to be visible as
    # literally no shift: sample i sits at i/rate from the first record,
    # and the segment map has nothing to say about it.
    clean = _gapless()
    if clean is None:
        print("    no gapless recording reachable; skipped")
    else:
        crep, cpath = clean
        print("    %s -- %d segment, %.3f s lost"
              % (os.path.basename(cpath), crep["n_segments"],
                 crep["seconds_lost"]))
        ck("it has no gaps to correct for", crep["n_segments"] == 1,
           "%d segments" % crep["n_segments"])
        fs = crep["map_fs"]
        worst = 0.0
        for i in (0, 1000, 1000000, int(crep["total_samples"]) - 1):
            got = continuity.sample_to_true(crep, i)
            if got is None:
                continue
            worst = max(worst, abs(got - i / fs))
        ck("sample index over the rate IS the time, with no offset",
           worst < 1e-6, "worst %.3g s" % worst)
        # And the correction machinery agrees there is nothing to do.
        off = retime.offer(crep, entry("ETS dentate-spike export"))
        ck("even Toothy output is not offered a correction here",
           not off.get("offer"), "it was offered one")
        if off.get("reason"):
            print("       %s" % off["reason"][:120])

    print()
    if FAILED:
        print("%d check(s) FAILED:" % len(FAILED))
        for f in FAILED:
            print("   %s" % f)
        raise SystemExit(1)
    print("all good -- in-house output is concat-safe and says so")


def _gapless():
    """A reachable recording that segments into one piece."""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:8791/api/registry", timeout=300) as fh:
            reg = json.loads(fh.read())
    except Exception:                                     # noqa: BLE001
        return None
    for p in reg.get("tree", []):
        for m in p.get("mice", []):
            for s in m.get("sessions", []):
                path = (s.get("here") or [None])[0]
                if not path:
                    continue
                try:
                    r = continuity.check(path)
                except Exception:                         # noqa: BLE001
                    continue
                if r.get("ok") and r.get("n_segments") == 1:
                    return r, path
    return None


def _log_for(rep):
    """A health log holding one check for this recording."""
    import tempfile
    root = tempfile.mkdtemp(prefix="concatsafe-")

    class FakeStore(object):
        def provenance(self):
            return {"user": "checker", "machine": "test"}

        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return lambda *a, **k: None

    log = healthlog.HealthLog(root, FakeStore())
    gid = "g-test"
    log.record(gid, rep.get("folder"), rep, label="test")
    return {"log": log, "gid": gid}


main()
