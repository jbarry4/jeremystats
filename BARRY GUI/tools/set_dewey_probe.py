"""set_dewey_probe.py -- put every DEWEY recording on the DEWEY 32 montage.

Setting a probe is a person saying what went into the animal, which is why
the app makes you say it one recording at a time and `probes.suggest` refuses
to guess. Saying it 242 times through a picker is not a better answer than
saying it once here, so this is the once -- and it records the same
`probe_source: "manual"` the picker does, because it is the same claim made
by the same person.

WHAT IT WILL NOT DO

J3 is a 64-channel recording and everybody else is 32. It is the same
montage: the acquisition wrote 64 CSC files and 33-64 are dead, confirmed
2026-09-24. `--include-64` says so, and the recordings it covers get a note
recording why the count disagrees with the template, so the next person to
notice does not have to work it out again.

Without that flag a recording whose channel count does not match the template
is counted, named and left alone -- because a channel count that disagrees is
normally the sign of something worth looking at rather than something to
override.

It also leaves alone anything that already has a probe set, because that is
somebody's answer and this is a bulk default.

    python tools\\set_dewey_probe.py           # say what would happen
    python tools\\set_dewey_probe.py --apply   # do it
"""
from __future__ import annotations

import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

from backend import probes, sessreg, store as storemod  # noqa: E402

PROBE = "dewey32"


def main():
    apply = "--apply" in sys.argv
    include64 = "--include-64" in sys.argv

    STORE = storemod.Store(os.path.join(APP, "GUI_logs"), auto_stage=False)
    REG = sessreg.Registry(STORE)

    rows = [r for r in REG.all() if (r.get("project") or "") == "DEWEY"]
    if not rows:
        print("No DEWEY records. Nothing to do.")
        return 0

    want_n = probes.EXPECTS_CHANNELS.get(PROBE)
    todo, already, wrong_n, no_count = [], [], [], []
    for r in rows:
        if r.get("probe"):
            already.append(r)
            continue
        n = r.get("n_channels")
        if not n:
            no_count.append(r)
        elif int(n) != int(want_n) and not include64:
            wrong_n.append(r)
        else:
            todo.append(r)

    print("DEWEY records      : %d" % len(rows))
    print("already have a probe: %d" % len(already))
    print("no channel count   : %d" % len(no_count))
    print("not %d channels     : %d" % (want_n, len(wrong_n)))
    print("to set to %-9s: %d" % (PROBE, len(todo)))

    if wrong_n:
        by = Counter((r.get("mouse"), r.get("n_channels")) for r in wrong_n)
        print("\nLeft alone -- a different channel count:")
        for (m, n), c in sorted(by.items(), key=lambda kv: str(kv[0])):
            print("   m%-4s %s channels   %d recording(s)" % (m, n, c))
        print("   The DEWEY 32 template describes a 32-channel headstage. "
              "Use --include-64 only if you know these are the same montage.")
    if no_count:
        print("\nLeft alone -- nothing has read a header for them: %d"
              % len(no_count))

    if not apply:
        print("\nDry run. Nothing was written. Re-run with --apply to act.")
        return 0
    if not todo:
        print("\nNothing to do.")
        return 0

    print("\napplying...")
    done = 0
    for r in todo:
        patch = {"probe": PROBE, "probe_source": "manual"}
        n = r.get("n_channels")
        if n and int(n) != int(want_n):
            # Why the count disagrees, written down on the record rather
            # than left for somebody to rediscover. A 64-channel recording
            # carrying a 32-channel montage is exactly the shape of thing
            # that reads as a mistake six months later.
            note = ("Acquisition wrote %d CSC files; 33-%d are dead. The "
                    "montage is the same 32-channel DEWEY map."
                    % (int(n), int(n)))
            if note not in (r.get("note") or ""):
                patch["note"] = ((r.get("note") or "") + " " + note).strip()
        REG._patch(r, patch)
        done += 1
        if done % 50 == 0:
            print("  ... %d of %d" % (done, len(todo)))

    STORE.record_activity([{
        "action": "registry.probe",
        "detail": {"probe": PROBE, "n": done, "via": "set_dewey_probe"},
    }])
    print("\nDone. %d recording(s) set to %s." % (done, PROBE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
