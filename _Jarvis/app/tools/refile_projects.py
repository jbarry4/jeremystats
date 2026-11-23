# -*- coding: utf-8 -*-
"""Re-file recordings whose project no longer matches their own paths.

`guess_project` learned two things it did not know before: that
`KCNT1 Urethane` is a separate body of work from `KCNT1`, and that the gap in
a project name is spelled with a space on the cluster and a path separator on
this lab's drive. Records written before that were filed by the old rule and
stay filed that way -- `_durable_patch` only sets a project on a record that
has none, which is right, because a later scan must never overwrite a
decision.

So the correction is a deliberate pass, here, rather than a side effect of
opening something.

WHY THIS ASKS THE RESOLVER AND NOT THE WORD "URETHANE"

The obvious rule -- if the path says urethane, it is KCNT1 Urethane -- is
wrong on this lab's data, and wrong in the direction that loses information:

    Y:\\ProcessedPtenData\\PTEN_CSDsEtc\\CTL\\rejects\\M15_s3_baseline_urethane
    Y:\\ProcessedPtenData\\PTEN_CSDsEtc\\CTL\\rejects\\M15_s8_CNO_urethane

Those are PTEN recordings. "Urethane" there names the anaesthetic, not the
project, and re-filing them would move two recordings out of the project they
belong to. `guess_project` already reads them correctly because `PTEN` is a
path segment and `KCNT1 Urethane` is not.

THREE THINGS IT WILL NOT DO

  * Never file anything as Unfiled. Five records resolve that way -- all
    harness fixtures under `Z:\\harness\\split-me` -- and turning a project
    into no project is a loss, not a correction.
  * Never touch a project somebody set by hand (`project_source` manual).
  * Never touch a record with no paths to reason from.

    python tools/refile_projects.py           what it would change
    python tools/refile_projects.py --apply   change it

Reads and writes GUI_logs only. No cluster, no network.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import sessreg, store as storemod  # noqa: E402

LOGS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "GUI_logs")


def plan(reg):
    """(gid, was, now, source, path) for every record worth correcting."""
    out = []
    for rec in (reg.all() or []):
        paths = [p for p in (rec.get("paths") or []) if isinstance(p, str)]
        if not paths:
            continue
        if (rec.get("project_source") or "") == "manual":
            continue
        want = sessreg.guess_project(rec, paths)
        have = rec.get("project")
        if want == have or want == sessreg.UNFILED or not want:
            continue
        out.append((rec.get("gid"), have, want,
                    rec.get("project_source"), paths[0]))
    return out


def main():
    apply = "--apply" in sys.argv
    store = storemod.Store(LOGS, auto_stage=False)
    reg = sessreg.Registry(store)

    rows = plan(reg)
    if not rows:
        print("Every recording's project already agrees with its paths.")
        return 0

    by = {}
    for _gid, was, now, _src, _p in rows:
        by[(was, now)] = by.get((was, now), 0) + 1

    print("\n%d recording(s) to re-file\n" % len(rows))
    for (was, now), n in sorted(by.items(), key=lambda kv: -kv[1]):
        print("  %-10s -> %-16s %d" % (was, now, n))

    print("\nfirst few:")
    for gid, was, now, src, path in rows[:8]:
        print("  %s  %-8s -> %-16s %s" % (gid, was, now, path[:58]))

    if not apply:
        print("\nNothing written. Re-run with --apply to change them.")
        return 0

    done = 0
    for gid, _was, now, _src, _path in rows:
        rec = reg.by_gid(gid)
        if not rec:
            continue
        try:
            reg._patch(rec, {"project": now, "project_source": "guessed"})
            done += 1
        except Exception as exc:                         # noqa: BLE001
            print("  FAILED %s: %s" % (gid, exc))
    print("\nRe-filed %d of %d." % (done, len(rows)))
    try:
        store.record_activity([{
            "action": "registry.refile",
            "detail": {"n": done, "by": {"%s->%s" % k: v
                                         for k, v in by.items()}},
        }])
    except Exception:                                    # noqa: BLE001
        pass
    return 0 if done == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
