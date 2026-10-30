"""The end-of-day error report: one computer's faults for one day, each with
what that computer was doing either side of it (2026-10-21).

"Create an end of day error log from each computer. Get the error and the
logs from sometime before and after them and put them in as an informative
file. I'll feed that to you daily."

So it is written for whoever patches the code the next morning, not for the
person at the bench: which build was running, every distinct fault once with
how often and when, its full traceback, the context it was raised with, and
the activity log around its first and latest occurrences on one clock, the
error marked in its place. Test faults (harness pages, the test client) are
counted and left out.

Written to GUI_logs/error_reports/<day>@<machine shard>.txt -- one file per
computer per day, so two computers never write one file -- and rewritten
while the day's errors keep changing (`due`). app.py writes today's after
six in the evening and yesterday's on the first tick of a new day, and the
Errors view writes one on request.

Pure functions over lists, so tools/test_dayreport.py can feed it records.
"""
import datetime
import json
import os

BEFORE_S = 300          # five minutes of what led up to it
AFTER_S = 120           # two of what followed
MAX_BEFORE = 30         # nearest lines either side, so a busy minute of
MAX_AFTER = 15          #   scrolling does not bury the error
MAX_OCCURRENCES = 3     # contexts printed per fault: first, latest, one between
EVENING_HOUR = 18       # when today's report is first written


def _instant(stamp):
    if not stamp:
        return None
    s = str(stamp).strip().replace("Z", "+00:00")
    try:
        d = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.astimezone()
    return d


def _t(stamp):
    d = _instant(stamp)
    return d.timestamp() if d is not None else 0.0


def _clock(stamp):
    d = _instant(stamp)
    return d.astimezone().strftime("%H:%M:%S") if d is not None else "??:??:??"


def _first_line(msg):
    return str(msg or "").strip().split("\n")[0]


def _compact(obj):
    try:
        return json.dumps(obj, default=str, ensure_ascii=False,
                          separators=(",", ":"), sort_keys=True)
    except Exception:                                    # noqa: BLE001
        return str(obj)


def group(errors, signature):
    """Distinct faults, newest last-seen first: [(sig, [records oldest first])]."""
    groups = {}
    for r in errors:
        groups.setdefault(signature(r), []).append(r)
    out = []
    for sig, rows in groups.items():
        rows.sort(key=lambda r: _t(r.get("at")))
        out.append((sig, rows))
    out.sort(key=lambda kv: _t(kv[1][-1].get("at")), reverse=True)
    return out


def _picks(rows):
    """Which occurrences get their context printed: the first, the latest
    and the middle one -- the first is usually the cause, the latest says
    whether it is still happening."""
    if len(rows) <= MAX_OCCURRENCES:
        return list(rows)
    return [rows[0], rows[len(rows) // 2], rows[-1]]


def _around(acts, when):
    before = [a for a in acts if when - BEFORE_S <= a["_t"] <= when]
    after = [a for a in acts if when < a["_t"] <= when + AFTER_S]
    return before[-MAX_BEFORE:], after[:MAX_AFTER], len(before), len(after)


def _act_line(a, when):
    bits = [a.get("action") or "?"]
    if a.get("view"):
        bits.append("[" + str(a["view"]) + "]")
    sess = a.get("session") or {}
    key = sess.get("key") or sess.get("gid") or sess.get("name")
    if key:
        bits.append("rec=" + str(key))
    det = a.get("detail")
    if det:
        bits.append(_compact(det))
    return "    %s  %+7.1fs  %s" % (_clock(a.get("at")), a["_t"] - when,
                                   "  ".join(bits))


def build(day, errors, activity, signature, machine, user=None, build_id=None,
          tests_left_out=0, resolved=None, generated=None):
    """The report's text.

      day             'YYYY-MM-DD'
      errors          this computer's error records for that day (no tests)
      activity        this computer's activity records, that day and the
                      edges of the days either side
      signature       extras.signature: what makes two records one fault
      machine         the name to head it with
      resolved        {signature: {at, by}} triage marks, said per fault
    """
    acts = []
    for a in activity or []:
        a = dict(a)
        a["_t"] = _t(a.get("at"))
        acts.append(a)
    acts.sort(key=lambda a: a["_t"])
    groups = group(errors or [], signature)
    resolved = resolved or {}

    L = []
    L.append("Jarvis end-of-day error report")
    L.append("=" * 74)
    L.append("day         %s" % day)
    L.append("computer    %s" % machine)
    if user:
        L.append("person      %s" % user)
    if build_id:
        L.append("build       %s" % build_id)
    L.append("written     %s" % (generated or datetime.datetime.now()
                                 .astimezone().isoformat(timespec="seconds")))
    L.append("faults      %d error(s), %d distinct" % (len(errors or []),
                                                       len(groups)))
    if tests_left_out:
        L.append("left out    %d test fault(s) (harness pages, the test "
                 "client)" % tests_left_out)
    L.append("activity    %d action(s) logged on this computer that day"
             % sum(1 for a in acts if str(a.get("at") or "")[:10] == day))
    L.append("")
    if not groups:
        L.append("No errors on this computer today.")
        return "\n".join(L) + "\n"

    L.append("Each fault below is printed once: how often, when, the message, "
             "the context")
    L.append("it was raised with, its traceback, then what this computer was "
             "doing in the")
    L.append("%d minutes before and %d after its first and latest occurrences "
             "(>>> marks it)." % (BEFORE_S // 60, AFTER_S // 60))
    L.append("")
    L.append("Summary")
    L.append("-" * 74)
    for i, (sig, rows) in enumerate(groups, 1):
        L.append("%3d. x%-4d %s-%s  %s: %s" % (
            i, len(rows), _clock(rows[0].get("at")), _clock(rows[-1].get("at")),
            rows[-1].get("where") or "?", _first_line(rows[-1].get("message"))))

    for i, (sig, rows) in enumerate(groups, 1):
        last = rows[-1]
        L.append("")
        L.append("=" * 74)
        L.append("%d/%d  %s  x%d" % (i, len(groups), last.get("where") or "?",
                                     len(rows)))
        L.append("=" * 74)
        L.append("first       %s" % (rows[0].get("at") or "?"))
        L.append("latest      %s" % (last.get("at") or "?"))
        users = sorted({str(r.get("user")) for r in rows if r.get("user")})
        if users:
            L.append("who         %s" % ", ".join(users))
        mark = resolved.get(sig) or {}
        if mark:
            L.append("triage      marked resolved %s%s" % (
                mark.get("at") or "", (" by " + mark["by"]) if mark.get("by")
                else ""))
        L.append("signature   %s" % sig)
        L.append("")
        L.append("message")
        for line in str(last.get("message") or "").strip().split("\n"):
            L.append("    " + line)
        # The latest occurrence that carried them: a repeat often arrives
        # with the message alone.
        ctx = next((r.get("context") for r in reversed(rows)
                    if isinstance(r.get("context"), dict) and r["context"]),
                   None)
        if isinstance(ctx, dict) and ctx:
            L.append("")
            L.append("context")
            for k in sorted(ctx):
                L.append("    %-18s %s" % (k, _compact(ctx[k])
                                           if not isinstance(ctx[k], str)
                                           else ctx[k]))
        tb = next((r.get("detail") or r.get("stack") for r in reversed(rows)
                   if r.get("detail") or r.get("stack")), None)
        if tb:
            L.append("")
            L.append("traceback")
            text = tb if isinstance(tb, str) else _compact(tb)
            for line in text.strip().split("\n"):
                L.append("    " + line)
        for r in _picks(rows):
            when = _t(r.get("at"))
            before, after, nb, na = _around(acts, when)
            L.append("")
            L.append("--- around %s ---" % (r.get("at") or "?"))
            if not before and not after:
                L.append("    (nothing in this computer's activity log within "
                         "%d minutes before or %d after)"
                         % (BEFORE_S // 60, AFTER_S // 60))
                continue
            if nb > len(before):
                L.append("    (%d earlier action(s) in the window not shown; "
                         "the nearest %d are)" % (nb - len(before), len(before)))
            for a in before:
                L.append(_act_line(a, when))
            L.append("    %s  %+7.1fs  >>> %s: %s" % (
                _clock(r.get("at")), 0.0, r.get("where") or "?",
                _first_line(r.get("message"))))
            for a in after:
                L.append(_act_line(a, when))
            if na > len(after):
                L.append("    (%d later action(s) in the window not shown)"
                         % (na - len(after)))
    return "\n".join(L) + "\n"


def path_for(reports_dir, day, shard):
    return os.path.join(reports_dir, "%s@%s.txt" % (day, shard))


def stamp_of(errors):
    """What the day's errors were when a report was written: a report is
    due again only when this changes."""
    return "%d|%s" % (len(errors or []),
                      max([str(r.get("at") or "") for r in errors or []] or [""]))


def due(day, today, now_hour, have_stamp, want_stamp):
    """Whether to (re)write the report for `day` now. Today's after the
    evening hour; an earlier day's whenever it is out of date (the computer
    was off at six, or more went wrong after). Never a day still to come."""
    if day > today:
        return False
    if day == today and now_hour < EVENING_HOUR:
        return False
    return have_stamp != want_stamp
