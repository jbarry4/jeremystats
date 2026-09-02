"""
rebuild.py -- Reproducing a figure that was already exported.

A figure in Results/ is evidence. Six months later the question is always the
same: which recording, which seconds of it, which channels, filtered how? The
run record answers that, but only if the answer was written down at export
time and can still be checked against the disk today.

Two halves live here:

  pack_recipe()  is called on the way out, when a figure is exported. It keeps
                 the complete layout -- not a summary of it -- because a
                 summary is exactly what cannot be rebuilt from. The only
                 things trimmed are the ones that are large and derived.

  audit()        is called on the way back in. It reads a recipe and checks it
                 against the machine as it is now: does the folder still
                 exist, are the channels still there, is the window inside the
                 recording, are the panel types and colormaps still known. It
                 returns the steps a rebuild would take, each already marked
                 ok / warn / missing, so the warning comes before the work
                 rather than in the middle of it.

Nothing here rebuilds anything. The steps are performed by the client, which
is where the session cache, the open panes and the figure builder already
live; this module only says what the steps are and which of them will hurt.
"""
from __future__ import annotations

import os

from . import csc, ids

SCHEMA = 1

# Events are the one part of a layout that can be unbounded. A figure with
# more marks on it than this is not a figure anyone is reading, and the count
# is kept either way so the rebuild can say what it dropped.
MAX_EVENTS = 4000

# The keys that actually determine what the figure looks like. Anything not in
# here is either derived (rows, from the panels) or cosmetic in a way that does
# not survive a rebuild anyway.
LAYOUT_KEYS = (
    "title", "subtitle", "page", "width_in", "height_in", "dpi",
    "rows", "cols", "t0", "t1", "highpass", "lowpass", "notch", "cmap",
    "spacing_um", "channels", "bad_channels", "gain", "show_metadata",
    "identity", "session_label", "metadata", "panels",
)


def pack_recipe(layout, sessions):
    """Everything needed to draw this figure again, and nothing else."""
    recipe = {"schema": SCHEMA}
    for k in LAYOUT_KEYS:
        if k in layout:
            recipe[k] = layout[k]

    events = layout.get("events") or []
    recipe["event_count"] = len(events)
    recipe["events"] = events[:MAX_EVENTS]
    recipe["events_truncated"] = len(events) > MAX_EVENTS

    # How each session was opened matters as much as which one it was:
    # even_only and invert change the channel list and the sign of every trace.
    recipe["sessions"] = {
        sid: {"path": spec.get("path", ""),
              "even_only": bool(spec.get("even_only", True)),
              "invert": bool(spec.get("invert", True))}
        for sid, spec in (sessions or {}).items()
    }
    return recipe


def from_legacy(run):
    """Build the best recipe available from a record written before recipes.

    Marked incomplete, because it is: the channel selection, the gain, the
    events and the per-panel frequency ranges were never written down, so a
    rebuild from one of these is a reconstruction and should say so.
    """
    pr = run.get("parameters") or {}
    sess = run.get("session") or {}
    return {
        "schema": 0,
        "title": run.get("label") or "figure",
        "subtitle": "",
        "page": pr.get("page") or "letter_landscape",
        "rows": pr.get("rows") or 1,
        "cols": pr.get("cols") or 1,
        "t0": pr.get("t0"), "t1": pr.get("t1"),
        "highpass": pr.get("highpass") or 0,
        "lowpass": pr.get("lowpass") or 0,
        "notch": pr.get("notch") or 0,
        "cmap": pr.get("cmap") or "jet",
        "bad_channels": pr.get("bad_channels") or [],
        "channels": None,          # never recorded
        "gain": None,              # never recorded
        "identity": sess,
        "session_label": sess.get("label"),
        "show_metadata": True,
        "metadata": {"source_path": sess.get("path", "")},
        "panels": [dict(p, session_id="default")
                   for p in (run.get("panels") or [])],
        "events": [], "event_count": 0, "events_truncated": False,
        "sessions": {"default": {"path": sess.get("path", ""),
                                 "even_only": True, "invert": True}},
    }


def recipe_for(run):
    """The recipe on a run record, or the best reconstruction of one."""
    rec = run.get("recipe")
    if isinstance(rec, dict) and rec.get("panels") is not None:
        return rec, True
    return from_legacy(run), False


# ----------------------------------------------------------------------------
# The audit
# ----------------------------------------------------------------------------

def _step(sid, title, what, status="ok", note=None, **extra):
    s = {"id": sid, "title": title, "what": what, "status": status}
    if note:
        s["note"] = note
    s.update(extra)
    return s


def _worst(*statuses):
    for level in ("missing", "warn", "ok"):
        if level in statuses:
            return level
    return "ok"


def audit(recipe, complete, panel_ids, colormap_ids, page_ids, known=None):
    """Check a recipe against this machine. Returns (steps, problems)."""
    steps, problems = [], []

    if not complete:
        problems.append(
            "This figure was exported before full recipes were recorded. The "
            "recording, the time window and the filters are known; the "
            "channel selection, the gain and any event marks are not, and "
            "will come from the session defaults instead.")

    # ---- 1. the recording itself -------------------------------------------
    sessions = recipe.get("sessions") or {}
    primary = (sessions.get("default")
               or (list(sessions.values())[0] if sessions else {}))
    path = primary.get("path") or ""
    ident = recipe.get("identity") or {}

    if not path:
        steps.append(_step(
            "locate", "Locate the recording",
            "no path was recorded", "missing",
            "There is no path on this record, so there is nothing to reopen."))
        problems.append("The record does not name a recording folder.")
    elif os.path.isdir(path) or os.path.isfile(path):
        steps.append(_step("locate", "Locate the recording", path, "ok",
                           None, path=path))
    else:
        alt, how = _find_moved(ident, known)
        if alt:
            steps.append(_step(
                "locate", "Locate the recording", alt, "warn",
                "The original path is gone. This recording was later opened "
                "from here, and matches on mouse, session and start time "
                "(%s match), so this path will be used instead." % how,
                path=alt, original=path, moved=True, match=how))
            problems.append(
                "The recording has moved since the figure was made.")
        else:
            steps.append(_step(
                "locate", "Locate the recording", path, "missing",
                "This folder is not on this machine. It may be on a drive "
                "that is not mounted. Nothing else can be checked until it "
                "is reachable.",
                path=path))
            problems.append("The recording folder does not exist: " + path)

    reachable = steps[-1]["status"] != "missing"
    use_path = steps[-1].get("path") or path

    # ---- 2. open it and compare the inventory ------------------------------
    duration = None
    if reachable:
        sess, err = _peek(use_path, primary)
        if err:
            steps.append(_step(
                "open", "Read the channel inventory", use_path, "missing",
                err))
            problems.append("The recording could not be opened: " + err)
            reachable = False
        else:
            duration = sess.get("duration_s")
            chans = sess.get("channels") or []
            numbers = [c["number"] for c in chans]
            note, status = None, "ok"

            # A layout's `channels` are positions in this list, and its
            # `bad_channels` are CSC numbers -- they are not interchangeable,
            # and checking one against the other is how a rebuild would come
            # back with the wrong traces.
            want = recipe.get("channels")
            if want:
                gone = sorted(i for i in want if not 0 <= i < len(chans))
                if gone:
                    status = "warn"
                    note = ("The figure used %d channels but this recording "
                            "only has %d, so %d of them (position %s) cannot "
                            "be restored."
                            % (len(want), len(chans), len(gone), _brief(gone)))
                    problems.append(
                        "%d channel position(s) used by the figure are past "
                        "the end of this recording's channel list."
                        % len(gone))
            bad = recipe.get("bad_channels") or []
            lost_bad = sorted(set(int(b) for b in bad) - set(numbers))
            if lost_bad:
                status = _worst(status, "warn")
                extra = ("CSC %s was marked bad on the figure but is not in "
                         "this recording." % _brief(lost_bad))
                note = (note + " " + extra) if note else extra
                # A step that warns without a line in `problems` produces a
                # verdict the dialog cannot explain.
                problems.append(
                    "%d channel(s) marked bad on the figure are not in this "
                    "recording: CSC %s." % (len(lost_bad), _brief(lost_bad)))

            steps.append(_step(
                "open", "Read the channel inventory",
                "%d channels at %s Hz, %s"
                % (len(chans), _num(sess.get("fs")), _dur(duration)),
                status, note,
                even_only=primary.get("even_only", True),
                invert=primary.get("invert", True),
                channels_present=len(chans)))

    # ---- 3. the window -----------------------------------------------------
    t0, t1 = recipe.get("t0"), recipe.get("t1")
    if t0 is None or t1 is None:
        steps.append(_step(
            "window", "Restore the time window", "not recorded", "warn",
            "The window was not written down. The rebuild will open at the "
            "start of the recording."))
        problems.append("The time window was not recorded.")
    else:
        span = t1 - t0
        what = "%s to %s  (%s)" % (_clock(t0), _clock(t1), _dur(span))
        status, note = "ok", None
        if duration is not None and t1 > duration + 0.5:
            status = "warn"
            note = ("The figure ends at %s but this recording is only %s "
                    "long. The window will be clipped."
                    % (_clock(t1), _dur(duration)))
            problems.append(
                "The recorded window runs past the end of the file.")
        steps.append(_step("window", "Restore the time window", what, status,
                           note, t0=t0, t1=t1))

    # ---- 4. filters --------------------------------------------------------
    steps.append(_step(
        "filters", "Restore the filters and gain",
        _filters(recipe), "ok" if complete else "warn",
        None if complete else ("The gain was not recorded; the session "
                               "default will be used."),
        highpass=recipe.get("highpass") or 0,
        lowpass=recipe.get("lowpass") or 0,
        notch=recipe.get("notch") or 0,
        gain=recipe.get("gain")))

    # ---- 5. channel selection ---------------------------------------------
    want = recipe.get("channels")
    bad = recipe.get("bad_channels") or []
    if want:
        steps.append(_step(
            "channels", "Restore the channel selection",
            "%d selected%s" % (len(want),
                               ", %d marked bad" % len(bad) if bad else ""),
            "ok", None, channels=want, bad_channels=bad))
    else:
        steps.append(_step(
            "channels", "Restore the channel selection",
            "not recorded", "warn",
            "Which channels were on screen was not written down. Every "
            "channel will be selected, which may not be what the figure "
            "showed.",
            channels=None, bad_channels=bad))

    # ---- 6. events ---------------------------------------------------------
    n_ev = recipe.get("event_count") or 0
    if n_ev:
        note, status = None, "ok"
        if recipe.get("events_truncated"):
            status = "warn"
            note = ("The figure had %d marks; only the first %d were kept on "
                    "the record." % (n_ev, MAX_EVENTS))
            problems.append(
                "Not all of the figure's event marks were recorded.")
        steps.append(_step("events", "Put the event marks back",
                           "%d mark%s" % (n_ev, "" if n_ev == 1 else "s"),
                           status, note, event_count=n_ev))

    # ---- 7. the panels -----------------------------------------------------
    panels = recipe.get("panels") or []
    unknown = sorted({p.get("panel") for p in panels}
                     - set(panel_ids) - {None})
    cmaps = {p.get("cmap") for p in panels if p.get("cmap")}
    cmaps.add(recipe.get("cmap"))
    lost_cmaps = sorted(cmaps - set(colormap_ids) - {None})
    page = recipe.get("page")
    note, status, bits = None, "ok", []
    if unknown:
        status = "missing"
        bits.append("%s is not a panel this version can draw"
                    % ", ".join(unknown))
        problems.append("Unknown panel type(s): " + ", ".join(unknown))
    if lost_cmaps:
        status = _worst(status, "warn")
        bits.append("the colormap %s is gone, so jet will be used instead"
                    % ", ".join(lost_cmaps))
        problems.append("Colormap(s) no longer available: "
                        + ", ".join(lost_cmaps))
    if page and page not in page_ids:
        status = _worst(status, "warn")
        bits.append("the page preset %s is gone, so letter landscape will be "
                    "used" % page)
    if bits:
        note = "; ".join(bits).capitalize() + "."
    steps.append(_step(
        "panels", "Rebuild the panel grid",
        "%d panel%s on a %s x %s grid"
        % (len(panels), "" if len(panels) == 1 else "s",
           recipe.get("rows") or 1, recipe.get("cols") or 1),
        status, note, panels=panels))

    # ---- 8. hand over ------------------------------------------------------
    steps.append(_step("builder", "Open the figure builder",
                       "with everything above already filled in", "ok"))

    return steps, problems


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

def _peek(path, spec):
    """Open a session far enough to read its inventory, without loading data."""
    try:
        sess = csc.open_session(
            path,
            even_only=bool(spec.get("even_only", True)),
            invert=bool(spec.get("invert", True)))
    except Exception as exc:                       # noqa: BLE001 -- reported
        return None, str(exc)
    if not sess.get("ok"):
        return None, sess.get("error") or "unknown error"
    return sess, None


def _find_moved(identity, known):
    """Look for the same recording somewhere else.

    `known` is the stored session records. Each one accumulates every path the
    recording has ever been opened from, which is exactly the history needed
    when a drive letter changes or data is copied to a new machine. Matching
    goes through ids.match so a moved folder is recognized by mouse, session
    and start time rather than by its name.
    """
    if not identity or not known:
        return None, None
    try:
        rec, how = ids.match(identity, known)
    except Exception:                              # noqa: BLE001 -- best effort
        return None, None
    if not rec:
        return None, None
    # Newest path first: the most recent place it was opened from is the most
    # likely place it still is.
    for p in reversed(rec.get("paths") or []):
        if p and os.path.isdir(p):
            return p, how
    return None, None


def _filters(recipe):
    hp = recipe.get("highpass") or 0
    lp = recipe.get("lowpass") or 0
    notch = recipe.get("notch") or 0
    gain = recipe.get("gain")
    if lp:
        band = "%s-%s Hz" % (_num(hp) if hp else "DC", _num(lp))
    elif hp:
        band = "above %s Hz" % _num(hp)
    else:
        band = "unfiltered"
    bits = [band]
    if notch:
        bits.append("%s Hz notch" % _num(notch))
    if gain:
        bits.append("gain %sx" % _num(gain))
    return " · ".join(bits)


def _brief(nums, cap=8):
    nums = list(nums)
    if len(nums) <= cap:
        return ", ".join(str(n) for n in nums)
    return "%s and %d more" % (", ".join(str(n) for n in nums[:cap]),
                               len(nums) - cap)


def _num(v):
    if v is None:
        return "?"
    return "%g" % float(v)


def _dur(sec):
    if sec is None:
        return "unknown length"
    sec = float(sec)
    if sec < 90:
        return "%.2f s" % sec
    return "%d:%04.1f" % (int(sec // 60), sec % 60)


def _clock(t):
    if t is None:
        return "?"
    t = float(t)
    return "%d:%05.2f" % (int(t // 60), t % 60)
