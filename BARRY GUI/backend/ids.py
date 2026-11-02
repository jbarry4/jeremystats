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

DEWEY RATs are named nothing like any of that -- the animal is J<n>, and what
follows is a behavioural phase rather than a session number -- so they get
their own rule below. See `dewey_parts`.

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
GROUP_TOKENS = ("PTEN_DKO", "PTENDKO", "PTEN", "CTL", "KCNT1", "WT", "DKO",
                "DEWEY")


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


# --------------------------------------------------------------------------
# DEWEY RATs -- Rats Associating Two Sounds
# --------------------------------------------------------------------------
# Four levels: rat / phase / run / recording, and the spelling is different on
# almost every animal. All of these are real, from E:\\Joe Multisite 2026 data:
#
#   J10\\J10_Precon1\\J10_Precon1_SPC\\2026-08-16_14-35-02
#   J4 \\Precon1    \\J4_Precon1_SPC \\2026-07-22_10-48-48   rat only at the top
#   J3 \\J3 Precon 1\\J3_precon_1_precon\\...                spaces, lowercase
#   J9 \\J9_Con3R   \\J9_Con3_SPC    \\...                   R = a repeat
#   J4 \\Cond1      \\J4_Con1_SPC    \\...                   "Cond" one level,
#                                                            "Con" the next
#
# The animal number is read from the RAT folder rather than the run folder,
# because J4, J5, J6 and J7 leave it out of the folders below.
#
# The session number is banded so the phase is readable straight off it and a
# sixth conditioning day cannot push Test1 onto a number that means something
# else on another animal (J3 has six Cons; everybody else has four):
#
#   Precon 1-4  ->  s1  .. s4
#   Con    1-6  ->  s11 .. s16
#   Test   1-2  ->  s21 .. s22
#
# The run -- FP1, FP2, SPC -- is NOT folded into the session number. Three
# recordings share one session, and they are told apart by their start time
# the same way every other repeat in this lab is. SPC is the run carrying the
# TTL cue pairs (spelled SP in the older HOF data, and "precon" again on J3);
# FP1/FP2 are the grounding recordings.
DEWEY_RAT_RE = re.compile(r"^J(\d{1,3})(?:[_ ]|$)", re.IGNORECASE)

# "Precon 1", "PRECON1", "Cond3", "Con 4", "Test2", "J9_Con3R".
# `precon` is listed first and the word must not be preceded by a letter, so
# the "con" inside "Precon" can never be read as a conditioning day.
DEWEY_PHASE_RE = re.compile(
    r"(?:^|[^A-Za-z])"
    r"(pre[\s_-]*con(?:ditioning)?|con(?:d|ditioning)?|test)"
    r"[\s_-]*(\d{1,2})([A-Za-z])?(?![0-9])",
    re.IGNORECASE)

DEWEY_BANDS = (("precon", 0), ("test", 20), ("con", 10))

# FP2 before FP1 before a bare FP, and SP/SPC/precon all mean the cued run.
DEWEY_RUNS = (
    ("FP2", re.compile(r"(?:^|[^A-Z0-9])FP[\s_-]*2(?![0-9])", re.IGNORECASE)),
    ("FP1", re.compile(r"(?:^|[^A-Z0-9])FP[\s_-]*1(?![0-9])", re.IGNORECASE)),
    ("FP", re.compile(r"(?:^|[^A-Z0-9])FP(?![A-Z0-9])", re.IGNORECASE)),
    ("SPC", re.compile(r"(?:^|[^A-Z0-9])SPC?(?![A-Z0-9])", re.IGNORECASE)),
    ("SPC", re.compile(r"pre[\s_-]*con[\s_-]*$", re.IGNORECASE)),
)


def _dewey_phase(text):
    """('precon'|'con'|'test', n, repeat_letter) from one folder name."""
    if not text:
        return None
    m = DEWEY_PHASE_RE.search(text)
    if not m:
        return None
    word = re.sub(r"[\s_-]", "", m.group(1)).lower()
    for name, _band in DEWEY_BANDS:
        if word.startswith(name):
            return name, int(m.group(2)), (m.group(3) or "").upper() or None
    return None


def _dewey_run(text):
    """FP1 / FP2 / FP / SPC from a run folder name, or None."""
    if not text:
        return None
    for name, rx in DEWEY_RUNS:
        if rx.search(text):
            return name
    return None


def dewey_parts(parts):
    """DEWEY identity from a split path, or None if this is not one.

    Two gates, both required: a J<n> folder AND a recognisable phase. Neither
    alone is enough -- and nothing else in this lab's tree has either, which
    was checked against all 1,892 registry records before this rule was
    written. A rule here that widens by accident re-keys somebody's PTEN
    recording and detaches its curation from it, so it is deliberately narrow
    and `tools/check_ids_dewey.py` asserts that every existing key is
    unchanged.
    """
    window = [p for p in parts[-4:] if p]
    if not window:
        return None

    rat = None
    for comp in window:                       # leftmost wins: the rat folder
        m = DEWEY_RAT_RE.match(comp)
        if m:
            rat = int(m.group(1))
            break
    if rat is None:
        return None

    # The datetime folder names nothing; everything else might.
    named = [p for p in window if not parse_recording_dir(p)]
    if not named:
        return None

    # Ask the phase folder before the run folder, because the repeat marker
    # lives only on the phase folder: J9_Con3R holds J9_Con3_SPC, and reading
    # the run folder first would lose the R.
    order = []
    if len(named) >= 2:
        order.append(named[-2])
    order.append(named[-1])
    order.extend(named[:-2])

    phase = None
    for comp in order:
        phase = _dewey_phase(comp)
        if phase:
            break
    if not phase:
        return None

    name, n, repeat = phase
    band = dict(DEWEY_BANDS)[name]
    return {
        "mouse": rat,
        "session": band + n,
        "phase": {"precon": "Precon", "con": "Con", "test": "Test"}[name],
        "phase_n": n,
        "repeat": repeat,
        "run": _dewey_run(named[-1]),
    }


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

    # DEWEY first, and only when both its gates pass -- the generic rule below
    # finds neither a mouse nor a session in "J10_Precon1_SPC", which is why
    # every one of these recordings filed as Unfiled with a null key, and why
    # opening one minted a fresh gid every time instead of matching the row
    # that was already there.
    dewey = dewey_parts(parts)
    if dewey:
        mouse, session = dewey["mouse"], dewey["session"]
        mouse_src = "dewey:J<n>"
    else:
        mouse, mouse_src = extract_mouse_number(session_folder, mouse_folder)
        session = extract_session_number(session_folder)
        if session is None and mouse_folder:
            session = extract_session_number(mouse_folder)

    start = header_time or rec_time
    group = "DEWEY" if dewey else extract_group(parts)
    prefix = subject_prefix(group)

    confidence = "high"
    if mouse is None or session is None:
        confidence = "low"
    elif mouse_src.endswith(":any"):
        confidence = "medium"

    out = {
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
        "key": make_key(mouse, session, start, prefix),
        "loose_key": make_loose_key(mouse, session, prefix),
        "subject_prefix": prefix,
        "label": make_label(mouse, session, group, start, prefix=prefix,
                            phase=(dewey or {}).get("phase"),
                            phase_n=(dewey or {}).get("phase_n"),
                            run=(dewey or {}).get("run"),
                            repeat=(dewey or {}).get("repeat")),
    }
    if dewey:
        out.update({k: dewey[k] for k in ("phase", "phase_n", "run", "repeat")})
    return out


# --------------------------------------------------------------------------
# What the animal is called
# --------------------------------------------------------------------------
# Every key in this lab has started `m` since there was a lab, because every
# animal was a mouse. DEWEY's are rats, and calling a rat m9 in the one view
# where the animal is named is the kind of small wrongness that gets read out
# loud in a lab meeting.
#
# So the letter is a property of the PROJECT, not of the format string. The
# default stays `m`, which is what keeps every PTEN and KCNT1 key exactly as
# it was -- this is not a rename of anything that already exists.
SUBJECT_PREFIX = {"DEWEY": "r"}
DEFAULT_PREFIX = "m"


def subject_prefix(group):
    """`r` for rats, `m` for everything else."""
    return SUBJECT_PREFIX.get((group or "").strip().upper(), DEFAULT_PREFIX)


def make_key(mouse, session, start, prefix=DEFAULT_PREFIX):
    """Full identity: unique even when a subject/session pair repeats."""
    if mouse is None or session is None:
        return None
    base = "%s%03d_s%03d" % (prefix or DEFAULT_PREFIX, mouse, session)
    if start:
        return base + "_" + start.replace(":", "-").replace("T", "_")
    return base


def make_loose_key(mouse, session, prefix=DEFAULT_PREFIX):
    """Subject + session only -- the key people actually think in."""
    if mouse is None or session is None:
        return None
    return "%s%03d_s%03d" % (prefix or DEFAULT_PREFIX, mouse, session)


def make_label(mouse, session, group, start, prefix=DEFAULT_PREFIX,
               phase=None, phase_n=None, run=None, repeat=None):
    """Short human label: 'PTEN m13 s2 2023-08-01'.

    A DEWEY recording adds what it is called out loud between the session
    number and the date -- 'DEWEY m10 s13 Con3 SPC 2026-08-16' -- because s13
    is a banding nobody says in the room, and three recordings share it.
    """
    bits = []
    if group:
        bits.append(group)
    if mouse is not None:
        bits.append("%s%d" % (prefix or DEFAULT_PREFIX, mouse))
    if session is not None:
        bits.append("s%d" % session)
    if phase and phase_n is not None:
        bits.append("%s%d%s" % (phase, phase_n, repeat or ""))
    if run:
        bits.append(run)
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

        # A DEWEY session holds three recordings -- FP1, SPC, FP2 -- and they
        # share a mouse and a session number by design, because the lab calls
        # the whole day "Precon1". The start time was supposed to tell them
        # apart, and it does not: all three are run the same afternoon, well
        # inside the six-hour window `_near` allows for two mounts of one
        # recording disagreeing about the clock.
        #
        # Without this, a scan matched the SPC folder onto the FP1 record and
        # `upsert_session` appended its path -- three recordings silently
        # becoming one. It had already happened to all 280 of them: 93 rows
        # holding 257 paths, and the 91-minute cued recording filed as a
        # 6-minute grounding one.
        #
        # So the run is part of the identity at this tier. A candidate that
        # does not state one is still allowed through, because everything
        # that is not DEWEY has no run and must keep matching as it always
        # did -- and because mouse+session is not unique ACROSS projects
        # either, which is what `_near` below is for.
        run = identity.get("run")
        if run:
            hits = [c for c in hits
                    if not c.get("run") or c.get("run") == run]
            # Mouse, session AND run still is not an identity here. One
            # session can hold two recordings of the same run -- a flower
            # pot run started in the evening and again the next morning --
            # and those are two recordings, not one seen twice. So among
            # candidates that agree about the run, the clock has to agree
            # too, and `_near`'s six-hour window is far too generous to
            # decide it. See `_same_take`.
            start = identity.get("start")
            if start:
                hits = [c for c in hits if _same_take(c.get("start"), start)]

        start = identity.get("start")
        if start:
            # A loose match has to agree about WHEN.
            #
            # Mouse plus session is not an identity: this lab's numbering
            # restarts per project, so PTEN m1 s1 and KCNT1 m1 s1 have one
            # loose key and are two recordings. Without this, a scan of a
            # drive holding the second one matched the first, and
            # `upsert_session` appended the new path to it -- two recordings
            # silently becoming one. Three real records from 2023 and 2024
            # were taken over by a fixture named m1s1/m1s2/m2s1 that way.
            hits = [c for c in hits if _near(c.get("start"), start)]
        if len(hits) == 1:
            return hits[0], "strong"
        if len(hits) > 1:
            # Same mouse+session recorded more than once within the window:
            # prefer the nearest start time rather than guessing.
            if start:
                hits.sort(key=lambda c: abs(_epoch(c.get("start"))
                                            - _epoch(start)))
                return hits[0], "weak"
            return hits[0], "weak"
    return None, None


# How far apart two start times can be and still be one recording.
#
# Two mounts of the same recording carry the same start to the second. The
# slack is for one side having read it from a Neuralynx header and the other
# from a folder name, which differ by seconds or minutes -- never by days.
LOOSE_WINDOW_S = 6 * 3600


#: How far two clocks may disagree about one recording's start and still be
#: read as the same take. Sixteen seconds is real: a J4 folder is named
#: 10-38-11 and its Neuralynx header says 10-38-27, because the folder is
#: made when the operator clicks and the header is written when acquisition
#: actually begins.
SAME_TAKE_S = 10 * 60

#: How close to a whole number of hours a difference has to be before it is
#: read as a timezone, not a second recording.
TZ_SLACK_S = 120


def _same_take(a, b):
    """Are these two start times the same take, rather than two takes?

    `_near` answers a different question -- "could these be the same
    recording seen from two machines" -- and answers it with six hours of
    slack, because one machine reads the start from a Neuralynx header in
    UTC and another from a folder name in local time.

    That slack is unusable once mouse, session and run have already been
    matched, because a session legitimately holds two recordings of the
    same run: a flower pot run started in the evening and again the next
    morning. Sixteen hours apart is outside the window, but the two takes
    of J4's Precon1 FP1 are sixteen SECONDS apart and inside any window
    worth having.

    So this asks the sharper question. Two takes are the same when either:

      * the clocks are within `SAME_TAKE_S` -- a folder name and a header
        of one recording; or
      * they differ by a whole number of hours, to within `TZ_SLACK_S` --
        which is a timezone and nothing else. A genuine second take shares
        no minutes-and-seconds with the first: the evening and morning
        flower pot runs above are 16 h 10 m 41 s apart, and the ten
        minutes is what gives it away.

    A missing start on either side counts as the same take, for the same
    reason `_near` does: this tier exists for folders that do not say when.
    """
    if not a or not b:
        return True
    ea, eb = _seconds(a), _seconds(b)
    if ea is None or eb is None:
        return True
    gap = abs(ea - eb)
    if gap <= SAME_TAKE_S:
        return True
    off_hour = abs(gap - round(gap / 3600.0) * 3600.0)
    return off_hour <= TZ_SLACK_S


def _near(a, b):
    """Are these two start times the same recording's?

    A missing start on either side cannot be compared, and this tier exists
    for exactly that case -- a folder whose name says mouse and session but
    not when -- so it counts as near. Refusing it would lose the match that
    makes bad channels follow a recording between machines.
    """
    if not a or not b:
        return True
    ea, eb = _seconds(a), _seconds(b)
    if ea is None or eb is None:
        return True
    return abs(ea - eb) <= LOOSE_WINDOW_S


def _seconds(iso):
    """An ISO-ish stamp as seconds, or None when it cannot be read."""
    digits = re.sub(r"\D", "", str(iso or ""))
    if len(digits) < 8:
        return None
    digits = (digits + "000000")[:14]
    try:
        from datetime import datetime
        return datetime(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]),
                        int(digits[8:10]), int(digits[10:12]),
                        int(digits[12:14])).timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def _epoch(iso):
    """Crude ordering value for an ISO-ish timestamp; missing sorts far away."""
    if not iso:
        return float("inf")
    digits = re.sub(r"\D", "", iso)
    try:
        return float(digits[:14])
    except ValueError:
        return float("inf")
