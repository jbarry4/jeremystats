"""
toolkit.py -- Small jobs that span many sessions at once.

Everywhere else in the GUI you are looking at one recording. These are the
questions that are about the whole pile: which channels did we mark bad across
this mouse, over this month, in this project. The answers already exist in
GUI_logs -- one JSON file per session, written whenever a channel was marked
-- so nothing here reads data off disk. It reads the record of what was
decided, which is faster and, more to the point, is the thing being asked
about.

First job: exporting bad channels.

A bad channel matters twice. It matters now, because it has to come out of the
average. And it matters later, because the next person has to know it came
out. A list of them, scoped and dated and attributed, is the difference
between "channel 18 was noisy" as a memory and as a record.
"""
from __future__ import annotations

import re

# The scopes a caller may ask for. Named rather than inferred, because
# "everything" and "this one session" should not be a formatting accident.
SCOPES = ("session", "mouse", "group", "range", "all")


class ToolkitError(Exception):
    pass


# ----------------------------------------------------------------------------
# Choosing the sessions
# ----------------------------------------------------------------------------

def _day(value):
    """The YYYY-MM-DD part of an ISO-ish timestamp, or None."""
    if not value:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(value))
    return m.group(0) if m else None


def select(sessions, scope="all", key=None, mouse=None, group=None,
           date_from=None, date_to=None):
    """Narrow the stored session records to the ones asked for.

    Dates are compared as YYYY-MM-DD strings. That is not a shortcut: ISO
    dates sort correctly as text, and going through datetime would mean
    picking a timezone for a recording whose header has none.
    """
    if scope not in SCOPES:
        raise ToolkitError(
            "Unknown scope %r. Use one of: %s" % (scope, ", ".join(SCOPES)))

    if scope == "session":
        if not key:
            raise ToolkitError("A session scope needs a session key.")
        picked = [s for s in sessions if s.get("key") == key]
        if not picked:
            raise ToolkitError("No stored session with the key %r." % key)
        return picked

    if scope == "mouse":
        if mouse in (None, ""):
            raise ToolkitError("A mouse scope needs a mouse number.")
        try:
            want = int(mouse)
        except (TypeError, ValueError):
            raise ToolkitError("%r is not a mouse number." % mouse)
        return [s for s in sessions if s.get("mouse") == want]

    if scope == "group":
        if not group:
            raise ToolkitError("A project scope needs a project name.")
        want = str(group).strip().lower()
        return [s for s in sessions
                if (s.get("group") or "").strip().lower() == want]

    if scope == "range":
        lo, hi = _day(date_from), _day(date_to)
        if not lo and not hi:
            raise ToolkitError(
                "A date range needs a start date, an end date, or both.")
        if lo and hi and hi < lo:
            raise ToolkitError(
                "The range ends (%s) before it starts (%s)." % (hi, lo))
        out = []
        for s in sessions:
            day = _day(s.get("start"))
            if not day:
                continue          # no header time: it cannot be in any range
            if lo and day < lo:
                continue
            if hi and day > hi:
                continue
            out.append(s)
        return out

    return list(sessions)


def scope_label(scope, key=None, mouse=None, group=None,
                date_from=None, date_to=None):
    """A phrase naming what was exported, for the file and the header row."""
    if scope == "session":
        return "session " + str(key)
    if scope == "mouse":
        return "mouse " + str(mouse)
    if scope == "group":
        return "project " + str(group)
    if scope == "range":
        lo, hi = _day(date_from), _day(date_to)
        if lo and hi:
            return "%s to %s" % (lo, hi)
        return ("from " + lo) if lo else ("up to " + hi)
    return "every recorded session"


# ----------------------------------------------------------------------------
# Building the rows
# ----------------------------------------------------------------------------

# One row per bad channel. Long form is the one that survives contact with
# other tools -- a spreadsheet can pivot it, a script can filter it, and it
# does not need a parser for a comma-inside-a-cell list.
LONG_COLUMNS = (
    "project", "mouse", "session", "date", "label", "channel",
    "n_bad", "n_channels", "marked_by", "marked_at", "note", "path", "key",
)

# One row per session, for reading rather than processing.
WIDE_COLUMNS = (
    "project", "mouse", "session", "date", "label", "bad_channels",
    "n_bad", "n_channels", "marked_by", "marked_at", "note", "path", "key",
)


def _common(rec):
    upd = rec.get("updated") or rec.get("created") or {}
    bad = sorted(int(b) for b in (rec.get("bad_channels") or []))
    vs = rec.get("view_state") or {}
    # The channel count is not stored on the record; the saved selection is
    # the closest honest stand-in, and is left blank rather than guessed when
    # there is none.
    n_ch = len(vs.get("channels") or []) or ""
    return {
        "project": rec.get("group") or "",
        "mouse": rec.get("mouse") if rec.get("mouse") is not None else "",
        "session": rec.get("session") if rec.get("session") is not None else "",
        "date": _day(rec.get("start")) or "",
        "label": rec.get("label") or "",
        "n_bad": len(bad),
        "n_channels": n_ch,
        "marked_by": upd.get("user") or "",
        "marked_at": upd.get("at") or "",
        "note": (rec.get("note") or "").replace("\n", " ").strip(),
        "path": (rec.get("paths") or [""])[-1],
        "key": rec.get("key") or "",
    }, bad


def _sort_key(row):
    # Mouse then session then date, with blanks last rather than first: a
    # record missing its mouse number should not head the report.
    return (row["mouse"] == "", row["mouse"] or 0,
            row["session"] == "", row["session"] or 0,
            row["date"] or "9999-99-99")


def rows(sessions, form="long", include_clean=False):
    """Bad-channel rows for the given session records.

    `include_clean` keeps sessions with nothing marked. It is off by default
    because the usual question is "which channels are bad", but it matters for
    the other question -- "which sessions has nobody checked yet" -- and a
    zero row is the only way to tell a clean session from a missing one.
    """
    out = []
    for rec in sessions:
        base, bad = _common(rec)
        if not bad and not include_clean:
            continue
        if form == "wide":
            out.append(dict(base, bad_channels=" ".join(str(b) for b in bad)))
        elif not bad:
            out.append(dict(base, channel=""))
        else:
            for ch in bad:
                out.append(dict(base, channel=ch))
    out.sort(key=_sort_key)
    return out


def summarize(sessions):
    """Counts worth showing before anyone downloads anything."""
    marked, clean, bad_total = 0, 0, 0
    channels = {}
    days = []
    for rec in sessions:
        bad = [int(b) for b in (rec.get("bad_channels") or [])]
        if bad:
            marked += 1
            bad_total += len(bad)
            for b in bad:
                channels[b] = channels.get(b, 0) + 1
        else:
            clean += 1
        day = _day(rec.get("start"))
        if day:
            days.append(day)
    # The channels that go bad repeatedly are the interesting ones -- a
    # recurring number is usually a wire, not a recording.
    repeat = sorted(((n, c) for c, n in channels.items() if n > 1),
                    reverse=True)
    return {
        "sessions": len(sessions),
        "with_bad": marked,
        "clean": clean,
        "bad_total": bad_total,
        "distinct_channels": len(channels),
        "repeat_offenders": [{"channel": c, "sessions": n}
                             for n, c in repeat[:12]],
        "first_day": min(days) if days else None,
        "last_day": max(days) if days else None,
    }


def columns(form):
    return list(WIDE_COLUMNS if form == "wide" else LONG_COLUMNS)


def filename(form="long", scope="all", key=None, mouse=None, group=None,
             date_from=None, date_to=None):
    """A file name that says what is in it without being opened.

    The scope arguments are named rather than collected in **kw: they travel
    as one dict everywhere else, and **kw meant a caller splatting that dict
    passed `scope` both positionally and by keyword.
    """
    bits = ["bad-channels"]
    if scope == "session":
        bits.append(str(key or "session"))
    elif scope == "mouse":
        bits.append("m%s" % mouse)
    elif scope == "group":
        bits.append(str(group or "project"))
    elif scope == "range":
        lo, hi = _day(date_from), _day(date_to)
        bits.append("%s_to_%s" % (lo or "start", hi or "end"))
    else:
        bits.append("all")
    if form == "wide":
        bits.append("by-session")
    safe = "_".join(re.sub(r"[^A-Za-z0-9._-]+", "-", b).strip("-")
                    for b in bits if b)
    return safe
