# -*- coding: utf-8 -*-
"""Each DEWEY rat's counterbalanced cue identities: A, B, C, D.

Every rat hears two pairs in preconditioning, A -> B and C -> D, and which
physical sound sits in which seat is counterbalanced across rats. Click is
A in J3 and J8, B in J9 and J11, C in J6 and J7, D in J4 and J10. So the
main comparisons are made by seat, which averages the sounds out, and the
physical sound is kept only for checking (the lab, 2026-10-06).

The seats come from the lab's sheet, `RAT Identity for multisite 2026 -
Sheet1.csv`, and from nothing else: in particular not from the Con
sessions, because the analysis stays inside Precon1-4 ("don't go past
Precon4", the user). The sheet happens to agree with the recordings in all
eight rats -- each rat's two recorded pairings are exactly its A -> B and
C -> D -- and `check()` proves that against the bank's cue types.

As `histo.py` does with the histology workbook, the sheet is carried here
as literals (a module the whole app imports does no file I/O at import
time), and `tools/check_ratidentity.py` re-reads the real file and asserts
they agree cell for cell.
"""
from __future__ import annotations

SHEET_FILE = "RAT Identity for multisite 2026 - Sheet1.csv"
SEATS = ("A", "B", "C", "D")

#: rat -> {seat: the sheet's word, verbatim}.
IDENTITY = {
    3: {"A": "Click", "B": "Low", "C": "Noise", "D": "High"},
    4: {"A": "High", "B": "Noise", "C": "Low", "D": "Click"},
    6: {"A": "Noise", "B": "High", "C": "Click", "D": "Low"},
    7: {"A": "Noise", "B": "Low", "C": "Click", "D": "High"},
    8: {"A": "Click", "B": "High", "C": "Noise", "D": "Low"},
    9: {"A": "High", "B": "Click", "C": "Low", "D": "Noise"},
    10: {"A": "Low", "B": "Noise", "C": "High", "D": "Click"},
    11: {"A": "Low", "B": "Click", "C": "High", "D": "Noise"},
}

#: The sheet's words, as the rig names the sounds (circuit.CUES keys).
_KEY = {"Click": "Click", "Noise": "Noise", "High": "HighTone",
        "Low": "LowTone"}
#: And as a person reads them.
SOUND_SAY = {"Click": "Click", "Noise": "Noise", "High": "High tone",
             "Low": "Low tone"}

PAIRS = ("AB", "CD")
PAIR_SAY = {"AB": "AB (A → B)", "CD": "CD (C → D)"}


class IdentityError(Exception):
    pass


def known(rat):
    try:
        return int(rat) in IDENTITY
    except (TypeError, ValueError):
        return False


def identity(rat):
    """{A: "Click", B: "Low", ...} for one rat, or None if it is not on the
    sheet."""
    got = IDENTITY.get(int(rat)) if known(rat) else None
    return dict(got) if got else None


def cue_type_of_pair(rat, pair):
    """The rig's cue type for one of a rat's pairs: "Click_LowTone" for
    J3's AB."""
    ids = identity(rat)
    if not ids or pair not in PAIRS:
        return None
    a, b = pair[0], pair[1]
    return _KEY[ids[a]] + "_" + _KEY[ids[b]]


def pair_of(rat, cue_type):
    """"AB" or "CD" for a presentation of this cue type in this rat, or
    None when the cue type is neither of its pairs."""
    for p in PAIRS:
        if cue_type_of_pair(rat, p) == cue_type:
            return p
    return None


def seats_of(rat, cue_type):
    """(first seat, second seat) heard in a presentation: ("A", "B") or
    ("C", "D"), or None."""
    p = pair_of(rat, cue_type)
    return (p[0], p[1]) if p else None


def seat(rat, cue_type, window):
    """What was heard in one window of one presentation: {"seats": [...],
    "sounds": [...]} -- Cue 1 is the pair's first seat, Cue 2 its second,
    the pair window both, and the windows around them none."""
    s = seats_of(rat, cue_type)
    ids = identity(rat)
    if not s or not ids:
        return {"seats": [], "sounds": []}
    heard = {"cue1": [s[0]], "cue2": [s[1]], "pair": [s[0], s[1]],
             "onset": [s[0]], "switch": [s[0], s[1]],
             "offset": [s[1]]}.get(window, [])
    return {"seats": heard, "sounds": [SOUND_SAY[ids[x]] for x in heard]}


def label(rat, cue_type):
    """"AB: Click → Low tone" for a presentation, the seat first."""
    p = pair_of(rat, cue_type)
    ids = identity(rat)
    if not p or not ids:
        return None
    return "%s: %s → %s" % (p, SOUND_SAY[ids[p[0]]], SOUND_SAY[ids[p[1]]])


def seat_say(rat, cue_type):
    """"AB · A → B (Click → Low tone)": a presentation by its seats, the
    sounds after them -- the name every view leads with."""
    p = pair_of(rat, cue_type)
    ids = identity(rat)
    if not p or not ids:
        return None
    return "%s · %s → %s (%s → %s)" % (p, p[0], p[1], SOUND_SAY[ids[p[0]]],
                                      SOUND_SAY[ids[p[1]]])


def check(rat, cue_types):
    """Every cue type the bank holds for this rat is one of its two pairs on
    the sheet, and both pairs are there. Raises IdentityError, naming what
    disagrees, when not -- a presentation with the wrong seat would be
    pooled into the wrong side of every comparison, silently."""
    ids = identity(rat)
    if not ids:
        raise IdentityError("J%s is not on %s." % (rat, SHEET_FILE))
    want = {cue_type_of_pair(rat, p) for p in PAIRS}
    have = set(c for c in cue_types if c)
    stray = sorted(have - want)
    if stray:
        raise IdentityError(
            "J%s's recordings hold %s, which is neither its AB (%s) nor its "
            "CD (%s) on %s." % (rat, ", ".join(stray),
                                cue_type_of_pair(rat, "AB"),
                                cue_type_of_pair(rat, "CD"), SHEET_FILE))
    return {"rat": int(rat), "AB": cue_type_of_pair(rat, "AB"),
            "CD": cue_type_of_pair(rat, "CD"),
            "missing": sorted(want - have)}
