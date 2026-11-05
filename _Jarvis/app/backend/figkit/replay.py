"""
figkit/replay.py -- the walk-through's plan: what it will take to put a
figure's panels back on screen, checked before anything is done.

The walk-through is kept (asked 2026-10-22) and fixed. The old one drove the
UI step by step and then waited a fixed 2.2 s and hoped nothing had moved;
late writes kept undoing it. Now each tool replays its own panels, and the
page then READS BACK what is actually on screen and compares it, field by
field, with the figure's record. This module is the half that can be done
without a screen: is the recording here, does it still have those channels,
is the window inside it, can this version draw that plot. Every step comes
back ok / warn / missing, so a missing drive is a sentence before the work
rather than a failure in the middle of it.

    plan(layout, ctx, known) -> {"steps": [...], "problems": [...],
                                 "verdict": "ok" | "warn" | "missing"}
"""
from __future__ import annotations

import os

from . import FigError, adapter
from . import layout as L

#: Tools whose panels the page knows how to put back on screen
#: (web/js/figreplay.js registers the performers).
WALKABLE = {"xplore", "rootcanal"}
#: Tools whose panels read the recording itself, so the walk-through
#: has to find and open its folder first.
READS_RECORDING = {"xplore"}


def _step(sid, title, what, status="ok", note=None, **extra):
    s = {"id": sid, "title": title, "what": what, "status": status}
    if note:
        s["note"] = note
    s.update(extra)
    return s


def _worst(statuses):
    for level in ("missing", "warn"):
        if level in statuses:
            return level
    return "ok"


def _reachable(path):
    from .. import demo
    if not path:
        return False
    if demo.is_demo(path) or str(path).startswith("vacc:"):
        return True
    return os.path.isdir(path) or os.path.isfile(path)


def plan(layout, ctx, known=None):
    from .. import rebuild
    rec = dict(layout.get("recording") or {})
    steps, problems = [], []
    panels = L.reading_order(layout.get("panels") or [])
    # Only a panel that reads the recording itself needs its folder: a Root
    # Canal panel is of a banked set and its numbers, wherever the
    # recording is.
    needs_folder = any(p.get("tool") in READS_RECORDING for p in panels)

    # ---- 1. the recording -------------------------------------------------
    sess = None
    path = rec.get("path") or ""
    if needs_folder:
        if not path:
            steps.append(_step("locate", "Find the recording",
                               "no path recorded", "missing",
                               "The figure does not say where its "
                               "recording was, so there is nothing to "
                               "open."))
            problems.append("The figure does not name its recording's "
                            "folder.")
        elif _reachable(path):
            steps.append(_step("locate", "Find the recording", path, "ok",
                               path=path))
        else:
            alt, how = rebuild._find_moved(rec.get("identity") or {}, known)
            if alt:
                steps.append(_step(
                    "locate", "Find the recording", alt, "warn",
                    "The original folder is gone. The same recording "
                    "(matched on mouse, session and start time, %s) was "
                    "later opened from here, so this is used instead." % how,
                    path=alt, original=path, moved=True))
                problems.append("The recording has moved since the figure "
                                "was made.")
                path = alt
            else:
                steps.append(_step(
                    "locate", "Find the recording", path, "missing",
                    "That folder is not on this machine. It may be on a "
                    "drive that is not plugged in.", path=path))
                problems.append("The recording's folder is not here: "
                                + path)

        if steps[-1]["status"] != "missing":
            try:
                sess = ctx.session(path, rec.get("invert", True))
            except Exception:                             # noqa: BLE001
                sess = None
            if sess:
                n = len(sess.get("channels") or [])
                steps.append(_step(
                    "open", "Open it", "%d channels at %g Hz, %.1f s long"
                    % (n, float(sess.get("fs") or 0),
                       float(sess.get("duration_s") or 0)),
                    "ok", path=path, invert=rec.get("invert", True)))
            else:
                steps.append(_step("open", "Open it", path, "missing",
                                   "The recording would not open here."))
                problems.append("The recording would not open.")

    # ---- 2. each panel ------------------------------------------------------
    letters = L.letters(layout)
    for p in panels:
        letter = letters.get(p.get("uid")) or "?"
        tool = p.get("tool")
        try:
            ad = adapter(tool)
            pl = ad.plot(p.get("plot"))
        except FigError as exc:
            steps.append(_step("panel", "Panel %s" % letter, str(exc),
                               "missing", uid=p.get("uid"), tool=tool))
            problems.append("Panel %s: %s" % (letter, exc))
            continue
        name = (pl or {}).get("name") or p.get("plot")
        title = "Panel %s: %s" % (letter, name)
        if tool not in WALKABLE:
            steps.append(_step(
                "panel", title, "%s, %s" % (ad.name, name), "missing",
                "Putting %s panels back on screen is not built yet. The "
                "figure itself can still be opened and drawn." % ad.name,
                uid=p.get("uid"), tool=tool))
            problems.append("Panel %s cannot be walked through yet." % letter)
            continue
        if tool in READS_RECORDING:
            checks = _checks(ad, p, sess) if sess else []
            status = _worst([c["status"] for c in checks]) if checks else (
                "ok" if sess else "missing")
            for c in checks:
                if c["status"] != "ok":
                    problems.append("Panel %s: %s" % (letter, c["say"]))
            steps.append(_step(
                "panel", title,
                ", ".join(c["what"] for c in checks if c.get("what"))
                or "%s, %s" % (ad.name, name),
                status, "; ".join(c["say"] for c in checks
                                  if c["status"] != "ok") or None,
                uid=p.get("uid"), tool=tool))
            continue
        # Any other tool: can this machine get the panel's numbers? The
        # same question the figure asks when it draws, asked now.
        try:
            prep = ad.prepare(p, ctx)
            lin = ad.lineage(p, prep, ctx) or {}
            steps.append(_step("panel", title, ", ".join(
                (lin.get("phrases") or [])[:4]) or "%s, %s" % (ad.name, name),
                "ok", uid=p.get("uid"), tool=tool))
        except Exception as exc:                          # noqa: BLE001
            steps.append(_step("panel", title, "%s, %s" % (ad.name, name),
                               "missing", str(exc), uid=p.get("uid"),
                               tool=tool))
            problems.append("Panel %s: %s" % (letter, exc))

    # ---- 3. read it back ----------------------------------------------------
    steps.append(_step(
        "readback", "Read back what is on screen",
        "every panel's settings, compared with the figure's record", "ok"))
    steps.append(_step(
        "compare", "Draw it again beside the original",
        "the original and the redraw side by side, with what moved", "ok"))
    return {"steps": steps, "problems": problems,
            "verdict": _worst([s["status"] for s in steps])}


def _checks(ad, p, sess):
    """What can be checked about an Xplorefinder panel without a screen."""
    q = p.get("params") or {}
    out = []
    dur = float(sess.get("duration_s") or 0)
    t0, t1 = q.get("t0"), q.get("t1")
    if t0 is not None and t1 is not None:
        what = "%.3f-%.3f s" % (float(t0), float(t1))
        if dur and float(t1) > dur + 0.5:
            out.append({"status": "warn", "what": what,
                        "say": "the window runs past the end of the "
                               "recording, which is %.1f s long" % dur})
        else:
            out.append({"status": "ok", "what": what, "say": ""})
    chans = sess.get("channels") or []
    want = q.get("channels") or []
    gone = [i for i in want if not 0 <= int(i) < len(chans)]
    if gone:
        out.append({"status": "warn", "what": "%d channels" % len(want),
                    "say": "%d of its channels are past the end of this "
                           "recording's list" % len(gone)})
    elif want:
        out.append({"status": "ok", "what": "%d channels" % len(want),
                    "say": ""})
    numbers = {int(c["number"]) for c in chans}
    bad = [int(b) for b in (q.get("bad_channels") or [])]
    lost = sorted(set(bad) - numbers)
    if lost:
        out.append({"status": "warn", "what": "",
                    "say": "CSC %s was marked bad on the figure and is not in "
                           "this recording" % ", ".join(map(str, lost))})
    return out


def page_png(layout, ctx, dpi=110):
    """The whole page as one PNG, for the side-by-side."""
    from . import render
    blob, problems, _P = render.render_page(layout, ctx, "png", dpi=dpi)
    return blob, problems

