# -*- coding: utf-8 -*-
"""What one sync cycle actually downloads, measured at the socket.

`cloud_weight.py` says what a FULL pull would cost. This says what a real
one costs, by counting the bytes of every response an ordinary incremental
pull makes -- which is the number that multiplies by however often the
background loop runs.

The two questions it answers:

  * is an incremental pull actually incremental, or does it keep
    re-downloading the same rows? A pull that re-fetches what this machine
    pushed a moment ago is a treadmill, and it looks exactly like a working
    sync.
  * how much does an EMPTY cycle cost? At a pull every 20 seconds that is
    4,320 cycles a day, so a cycle that downloads nothing but still makes
    seventeen requests is not free.

    python tools/cloud_egress.py            one pull, from the real state
    python tools/cloud_egress.py --twice    two in a row, to see the second

Read-only: it pulls, which is what the app already does. It does not push
and does not write the sync state back, so running it does not move
`last_pull` and cannot make the app re-download anything afterwards.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import cloud, cloudsync  # noqa: E402

LOGS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "GUI_logs")


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f GB" % n


def weigh(c, since, label):
    """Every response an incremental pull would download, weighed.

    Deliberately does NOT construct a `Sync` and does NOT apply anything.
    The question is what leaves the database, and that is decided entirely
    by the requests -- so this makes the same requests and throws the rows
    away. Nothing local changes, and `last_pull` is not touched, so running
    this cannot make the app skip or repeat a cycle.
    """
    q = ("updated_at=gt.%s" % since) if since else ""
    tally, calls, t0 = {}, 0, time.time()
    for table in cloudsync.ORDER:
        rows, offset = [], 0
        while True:
            try:
                page = c.select(table, q, limit=cloud.PAGE, offset=offset)
            except Exception as exc:                     # noqa: BLE001
                tally[table] = (0, 0, 1, str(exc)[:40])
                page = []
                break
            calls += 1
            rows.extend(page)
            if len(page) < cloud.PAGE:
                break
            offset += cloud.PAGE
        if table not in tally:
            tally[table] = (len(json.dumps(rows)), len(rows),
                            max(1, (len(rows) // cloud.PAGE) + 1), None)
    took = time.time() - t0

    total = sum(v[0] for v in tally.values())
    print()
    print("== %s ==" % label)
    print("   since %s" % (since or "(never -- this is a FULL pull)"))
    print("   %d request(s), %.1fs" % (calls, took))
    print()
    print("   %-22s %10s %8s" % ("table", "bytes", "rows"))
    print("   " + "-" * 44)
    for name, (b, rows_n, _reqs, err) in sorted(
            tally.items(), key=lambda kv: -kv[1][0]):
        if err:
            print("   %-22s %10s   %s" % (name, "-", err))
        elif rows_n:
            print("   %-22s %10s %8d" % (name, human(b), rows_n))
    quiet = sum(1 for v in tally.values() if not v[1] and not v[3])
    print("   " + "-" * 44)
    print("   %-22s %10s" % ("total", human(total)))
    print("   %d of %d tables had nothing to send" % (quiet, len(tally)))
    return total, calls


def main():
    cfg = cloud.load_config(LOGS)
    if not cfg.get("key"):
        print("No key on this machine, so nothing can be measured.")
        return 1
    c = cloud.Cloud(LOGS)
    since = c.state().get("last_pull")

    total, calls = weigh(c, since, "one incremental pull, from where the "
                                   "app left off")

    if "--full" in sys.argv:
        weigh(c, None, "for comparison: a FULL pull, which is what a "
                       "machine with no state does")

    per_cycle = total
    per_day = per_cycle * (86400 / 20.0)
    print()
    print("At PULL_EVERY = 20s that is %d cycles a day." % (86400 // 20))
    print("   this cycle        %s" % human(per_cycle))
    print("   a day             %s" % human(per_day))
    print("   a month           %s" % human(per_day * 30))
    print()
    print("Plus the requests themselves: %d per cycle, %s a day, which is"
          % (calls, "{:,}".format(calls * (86400 // 20))))
    print("not free even when every one of them returns an empty list.")
    print()
    print("Free tier egress is 5 GB a month, across every machine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
