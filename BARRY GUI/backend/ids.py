"""
ids.py -- Stable session identity across machines, drives and folder renames.

A recording's path is not a usable identity: the same session lives at
D:\\PTEN\\... on one machine and \\\\netfiles03\\bigdata_jbarry\\... on another.
What IS stable is the mouse and session number, which appear in every naming
convention the lab uses -- though never the same way twice:

    PTEN\\M13_pten\\HF4s2aug1\\2023-08-01_12-11-26          -> mouse 13, session 2
    PTEN\\M11_Pten\\HF2_s10jul25\\2023-07-25_14-40-32       -> mouse 11, session 10
    CTL\\m21_ptenblind\\m21s2jul29\\2024-07-29_13-05-17     -> mouse 21, session 2
    PTEN_DKO\\PTENKDOM48\\m48s6cno90feb4\\2025-02-04_12-48-12 -> mouse 48, session 6
    KCNT1\\KCNT1_m0591\\KCNT1_m0591_s04_081026\\2026-08-10_16-14-48 -> mouse 591, session 4

Mouse and session alone are NOT unique -- M5s2bnov16 and M5s2cnov16 are both
mouse 5 session 2, and m53s7mar4-2025 holds two different recordings. So the
full identity carries a third component: the recording start time, taken from
the Neuralynx header when available (which survives any rename) and otherwise
from the YYYY-MM-DD_HH-MM-SS folder name.

Matching is therefore tiered:
    exact   mouse + session + recording start
    strong  mouse + session (unique among candidates)
    weak    mouse + session (ambiguous -- caller disambiguates)
"""
from __future__ import annotations

import re

# The Neuralynx recording folder: 2023-08-01_12-11-26
REC_DIR_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[_ ](\d{2})-(\d{2})-(\d{2})$")

# Session number: "s4", "S1", "s04", "s10". Must not swallow a following digit
# run ("cno90" after s6 stays out; "sept13" is not a session because the s is
# followed by a letter).
SESSION_RE = re.compile(r"[sS](\d{1,3})(?!\d)")

# Mouse token forms, most specific first.
MOUSE_WITH_SESSION_RE = re.compile(r"[mM](\d{1,5})[_\-]?[sS]\d")   # m10s4, m0591_s04
MOUSE_LEADING_RE = re.compile(r"^[^0-9]{0,12}?[mM](\d{1,5})")      # M1ptens2, KCNT1_m0591
MOUSE_ANY_RE = re.compile(r"[mM](\d{1,5})")                        # PTENDKOM41

# Cohort/genotype hints seen in the tree.
GROUP_TOKENS = ("PTEN_DKO", "PTENDKO", "PTEN", "CTL", "KCNT1", "WT", "DKO")


def _norm_parts(path):
    """Split a path into components, tolerating either separator."""
    return [p for p in re.split(r"[\\/]+", str(path).strip()) if p not in ("", ".")]


def parse_recording_dir(name):
    """Return an ISO-ish timestamp if `name` is a Neuralynx recording folder."""
    m = REC_DIR_RE.match(name.strip())
    if not m:
        return None
    y, mo, d, h, mi, s = m.groups()
    return "%s-%s-%sT%s:%s:%s" % (y, mo, d, h, mi, s)


def extract_session_number(text):
    """First plausible session number in a folder name."""
    if not text:
        return None
    # Skip an "s" that is part of the mouse token itself (m10s4 -> the s4 IS
    # the session, so search the whole string but prefer a match after 'm<n>').
    m = MOUSE_WITH_SESSION_RE.search(text)
    if m:
        tail = text[m.end() - 2:]        # re-include the s<digit>
        hit = SESSION_RE.search(tail)
        if hit:
            return int(hit.group(1))
    hit = SESSION_RE.search(text)
    return int(hit.group(1)) if hit else None


def extract_mouse_number(session_folder, mouse_folder):
    """Mouse number, preferring the most explicit evidence available.

    Returns (number, source) so callers can judge confidence.
    """
    for text, src in ((session_folder, "session_folder"),
                      (mouse_folder, "mouse_folder")):
        if not text:
            continue
        m = MOUSE_WITH_SESSION_RE.search(text)
        if m:
            return int(m.group(1)), src + ":m<n>s<n>"

    if session_folder:
        m = MOUSE_LEADING_RE.match(session_folder)
        if m:
            return int(m.group(1)), "session_folder:leading"

    if mouse_folder:
        m = MOUSE_LEADING_RE.match(mouse_folder)
        if m:
            return int(m.group(1)), "mouse_folder:leading"
        m = MOUSE_ANY_RE.search(mouse_folder)
        if m:
            return int(m.group(1)), "mouse_folder:any"

    if session_folder:
        m = MOUSE_ANY_RE.search(session_folder)
        if m:
            return int(m.group(1)), "session_folder:any"

    return None, "none"


def extract_group(parts):
    """Cohort label (PTEN / CTL / PTEN_DKO / KCNT1) from anywhere in the path."""
    upper = [p.upper() for p in parts]
    for token in GROUP_TOKENS:
        for i, p in enumerate(upper):
            if p == token or p.startswith(token + "_") or p == token.replace("_", ""):
                return parts[i]
    # Fall back to a token appearing inside a folder name.
    for token in GROUP_TOKENS:
        for i, p in enumerate(upper):
            if token in p:
                return token
    return None


def identify(path, header_time=None):
    """Build the identity record for a recording folder.

    `path`        the recording directory (the one holding CSC*.ncs)
    `header_time` optional ISO timestamp read from the Neuralynx header, which
                  is preferred over the folder name because it survives renames.
    """
    path = str(path)
    parts = _norm_parts(path)
    leaf = parts[-1] if parts else ""

    rec_time = parse_recording_dir(leaf)
    if rec_time:
        session_folder = parts[-2] if len(parts) >= 2 else ""
        mouse_folder = parts[-3] if len(parts) >= 3 else ""
    else:
        # Some sessions are not nested under a datetime folder.
        session_folder = leaf
        mouse_folder = parts[-2] if len(parts) >= 2 else ""

    mouse, mouse_src = extract_mouse_number(session_folder, mouse_folder)
    session = extract_session_number(session_folder)
    if session is None and mouse_folder:
        session = extract_session_number(mouse_folder)

    start = header_time or rec_time
    group = extract_group(parts)

    confidence = "high"
    if mouse is None or session is None:
        confidence = "low"
    elif mouse_src.endswith(":any"):
        confidence = "medium"

    return {
        "path": path,
        "mouse": mouse,
        "session": session,
        "start": start,
        "group": group,
        "mouse_folder": mouse_folder,
        "session_folder": session_folder,
        "rec_folder": leaf if rec_time else None,
        "mouse_source": mouse_src,
        "time_source": "header" if header_time else ("folder" if rec_time else "none"),
        "confidence": confidence,
        "key": make_key(mouse, session, start),
        "loose_key": make_loose_key(mouse, session),
        "label": make_label(mouse, session, group, start),
    }


def make_key(mouse, session, start):
    """Full identity: unique even when a mouse/session pair repeats."""
    if mouse is None or session is None:
        return None
    base = "m%03d_s%03d" % (mouse, session)
    if start:
        return base + "_" + start.replace(":", "-").replace("T", "_")
    return base


def make_loose_key(mouse, session):
    """Mouse + session only -- the key people actually think in."""
    if mouse is None or session is None:
        return None
    return "m%03d_s%03d" % (mouse, session)


def make_label(mouse, session, group, start):
    """Short human label: 'PTEN m13 s2 · 2023-08-01'."""
    bits = []
    if group:
        bits.append(group)
    if mouse is not None:
        bits.append("m%d" % mouse)
    if session is not None:
        bits.append("s%d" % session)
    if start:
        bits.append(start.split("T")[0])
    return " ".join(bits) if bits else "unidentified"


def match(identity, candidates):
    """Find `identity` among stored `candidates` (dicts with key/loose_key).

    Returns (record, how) where `how` is 'exact', 'strong', 'weak' or None.
    This is what makes bad-channel marks follow a session across machines.
    """
    if not identity:
        return None, None

    key = identity.get("key")
    if key:
        for c in candidates:
            if c.get("key") == key:
                return c, "exact"

    loose = identity.get("loose_key")
    if loose:
        hits = [c for c in candidates if c.get("loose_key") == loose]
        if len(hits) == 1:
            return hits[0], "strong"
        if len(hits) > 1:
            # Same mouse+session recorded more than once: prefer the nearest
            # start time rather than guessing.
            start = identity.get("start")
            if start:
                hits.sort(key=lambda c: abs(_epoch(c.get("start")) - _epoch(start)))
                return hits[0], "weak"
            return hits[0], "weak"
    return None, None


def _epoch(iso):
    """Crude ordering value for an ISO-ish timestamp; missing sorts far away."""
    if not iso:
        return float("inf")
    digits = re.sub(r"\D", "", iso)
    try:
        return float(digits[:14])
    except ValueError:
        return float("inf")
