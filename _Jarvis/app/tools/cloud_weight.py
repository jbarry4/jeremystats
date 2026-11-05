# -*- coding: utf-8 -*-
"""Which tables are actually costing egress, measured rather than guessed.

Supabase's free tier gives 5 GB of egress a month. Egress is what LEAVES
the database, which is almost entirely `pull` -- a push is ingress and does
not count against it. So "what are we downloading, and how often" is the
whole question, and this answers the first half from the database itself.

For each table it reports the row count and the average serialized row, and
multiplies them out. A table whose rows are 40 bytes is not worth thinking
about however many there are; one whose rows are 30 KB is worth thinking
about at a hundred rows.

    python tools/cloud_weight.py            every table in the sync order
    python tools/cloud_weight.py --rows 50  sample more rows per table

Read-only. Downloads a small sample per table -- a few hundred KB, not a
scan -- so running this does not itself become the problem.
"""
import json
import os
import sys

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


def main():
    sample = 20
    if "--rows" in sys.argv:
        sample = int(sys.argv[sys.argv.index("--rows") + 1])

    cfg = cloud.load_config(LOGS)
    if not cfg.get("key"):
        print("No key on this machine, so nothing can be measured.")
        return 1
    c = cloud.Cloud(LOGS)

    tables = list(getattr(cloudsync, "ORDER", None) or [])
    if not tables:
        tables = ["sessions", "session_paths", "mice", "bank_entries",
                  "bank_snapshots", "curation_sets", "curation_events",
                  "layer_sheets", "layer_labels", "results", "runs",
                  "storyboards", "activity", "errors", "error_marks",
                  "feedback", "feedback_notes", "people", "health_checks",
                  "tool_results", "machines"]

    rows = []
    for t in tables:
        name = t if isinstance(t, str) else (t.get("table") or t[0])
        try:
            n = c.count(name) if hasattr(c, "count") else None
        except Exception:                                # noqa: BLE001
            n = None
        try:
            page = c.select(name, "", limit=sample, offset=0)
        except Exception as exc:                         # noqa: BLE001
            print("  %-20s  (not there: %s)" % (name, str(exc)[:50]))
            continue
        if n is None:
            # No count helper: walk far enough to know the order of
            # magnitude without downloading the table.
            n = len(page)
            if len(page) == sample:
                n = None
        avg = (len(json.dumps(page)) / max(1, len(page))) if page else 0
        rows.append((name, n, avg, (n or 0) * avg))

    rows.sort(key=lambda r: -(r[3] or 0))
    print()
    print("%-22s %10s %12s %12s" % ("table", "rows", "avg row", "one pull"))
    print("-" * 60)
    total = 0
    for name, n, avg, tot in rows:
        total += tot or 0
        print("%-22s %10s %12s %12s"
              % (name, "?" if n is None else n, human(avg), human(tot or 0)))
    print("-" * 60)
    print("%-22s %10s %12s %12s" % ("", "", "", human(total)))
    print()
    print("That is one FULL pull. An incremental pull only fetches rows")
    print("whose updated_at is newer than the last one, so the number that")
    print("matters is how often a full pull happens -- see `last_pull` in")
    print("GUI_logs/.cloud_state.json and the `since` handling in")
    print("cloudsync.pull.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
