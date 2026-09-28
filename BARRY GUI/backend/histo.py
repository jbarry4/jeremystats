# -*- coding: utf-8 -*-
"""Where each DEWEY probe actually ended up, read off the histology.

A connectivity matrix is a claim about regions, and every row of it is only
as good as the sentence "channels 5 to 8 were in left perirhinal cortex".
For eight of the nine rats that sentence is wrong somewhere: three of J4's
twelve probes are in subiculum, both of J9's hippocampal probes are in
parietal association cortex, and J3 has four probes that simply missed.
Correlating those and labelling the result "Left PER x Right POR" is not a
weaker result, it is a differently-labelled one, and nothing downstream can
tell.

So the histology is a first-class input here rather than a note in a
notebook. `Joes multi site histo results.xlsx` scores all twelve probes in
eight rats, and this module is that workbook made enforceable.

Why the table is literal rather than read from the file
-------------------------------------------------------
Same rule `probes.py` already follows and for the same reason: a module the
whole app imports must not do file I/O at import time, and a workbook on a
desk is not a deployable. The literals below are the contract;
`tools/check_histo.py` re-reads the real workbook and asserts they still
agree, which makes the spreadsheet enforceable without making it a
dependency.

The cells are transcribed RAW -- "y", "n", "maybe", "subiculum", "L
entorhinal (need second opinion)" -- exactly as typed, including the
capital L and the parenthetical. The check compares those strings, so it
catches a re-transcription that quietly tidied something up. Interpretation
happens below, in one place, where it can be read and argued with.

The vocabulary
--------------
Five outcomes, and they are not a severity scale -- they are five different
claims:

  intended   "y".     The probe is where the map says. Nothing to say.
  uncertain  "maybe". Probably right; scored without confidence.
  relocated  a named region. The probe works and records real signal,
             from somewhere else. This is the interesting one.
  missed     "n".     Not in the target, and nothing named. There is no
             label that could honestly go on this channel group.
  unscored   the rat is not in the workbook at all (J5). Different from
             "n": nobody has looked, which is not the same as looking and
             finding nothing. Excluded all the same, until it is scored.

What happens to each is decided in `usable()` and stated on the record, not
buried in a caller.
"""

# --------------------------------------------------------------------------
# The workbook, transcribed.

SHEET_FILE = "Joes multi site histo results.xlsx"

# In the workbook's own column order, and in its own spelling. `dHC` and
# `Prh` here; `electrode_map.xlsx` writes the same two regions `L-DHPC` and
# `L-PrH`, and `probes.py` carries that spelling as `sheet_label`. Neither
# is wrong and both are in use, so the binding below is by normalised key
# rather than by string equality -- see `_norm`.
SHEET_COLUMNS = ("L-OFC", "R-OFC", "L-ACC", "R-ACC", "L-dHC", "R-dHC",
                 "L-RSC", "R-RSC", "L-Prh", "R-Prh", "L-Por", "R-Por")

# rat number -> {sheet column: the cell, verbatim}
#
# J5 is deliberately absent: the workbook has a blank row where it would
# be. It has histology IMAGES on E:, so it was photographed and not scored,
# and inventing a row for it here would turn "nobody looked" into "nothing
# found". J1 and J2 are the two rats the VACC pipeline ran on and are not
# in this cohort at all.
HISTO_RAW = {
    3: {"L-OFC": "y", "R-OFC": "y", "L-ACC": "y", "R-ACC": "y",
        "L-dHC": "y", "R-dHC": "y", "L-RSC": "n", "R-RSC": "n",
        "L-Prh": "n", "R-Prh": "lateral entorhinal",
        "L-Por": "n", "R-Por": "n"},
    4: {"L-OFC": "y", "R-OFC": "y", "L-ACC": "y", "R-ACC": "y",
        "L-dHC": "y", "R-dHC": "y", "L-RSC": "y", "R-RSC": "y",
        "L-Prh": "subiculum", "R-Prh": "subiculum",
        "L-Por": "subiculum", "R-Por": "fmj"},
    6: {"L-OFC": "y", "R-OFC": "y", "L-ACC": "y", "R-ACC": "y",
        "L-dHC": "y", "R-dHC": "white matter tracts",
        "L-RSC": "y", "R-RSC": "y",
        "L-Prh": "y", "R-Prh": "entorhinal",
        "L-Por": "subiculum", "R-Por": "subiculum"},
    7: {"L-OFC": "y", "R-OFC": "y", "L-ACC": "y", "R-ACC": "y",
        "L-dHC": "y", "R-dHC": "y", "L-RSC": "y", "R-RSC": "y",
        "L-Prh": "L entorhinal (need second opinion)", "R-Prh": "y",
        "L-Por": "subiculum", "R-Por": "n"},
    8: {"L-OFC": "y", "R-OFC": "y", "L-ACC": "y", "R-ACC": "y",
        "L-dHC": "maybe", "R-dHC": "maybe",
        "L-RSC": "y", "R-RSC": "n",
        "L-Prh": "ventral dhc ca1", "R-Prh": "ventral dhc ca1",
        "L-Por": "n", "R-Por": "n"},
    9: {"L-OFC": "y", "R-OFC": "y", "L-ACC": "y", "R-ACC": "y",
        "L-dHC": "Parietal association ctx",
        "R-dHC": "Parietal association ctx",
        "L-RSC": "y", "R-RSC": "y",
        "L-Prh": "n", "R-Prh": "y", "L-Por": "n", "R-Por": "n"},
    10: {"L-OFC": "maybe", "R-OFC": "maybe", "L-ACC": "y", "R-ACC": "y",
         "L-dHC": "Parietal association ctx", "R-dHC": "white matter tracts",
         "L-RSC": "y", "R-RSC": "y",
         "L-Prh": "subiculum", "R-Prh": "subiculum",
         "L-Por": "subiculum", "R-Por": "subiculum"},
    11: {"L-OFC": "y", "R-OFC": "y", "L-ACC": "y", "R-ACC": "y",
         "L-dHC": "maybe", "R-dHC": "y", "L-RSC": "y", "R-RSC": "y",
         "L-Prh": "y", "R-Prh": "ventral dhc ca1",
         "L-Por": "n", "R-Por": "n"},
}

# --------------------------------------------------------------------------
# What the free-text cells name.
#
# Keyed by the cell lowercased and squeezed, so a stray capital or double
# space does not open a hole. Anything NOT in here is reported as an
# unrecognised relocation rather than guessed at or dropped -- a region
# nobody anticipated has to be visible, because the alternative is a matrix
# row silently labelled with the region the probe was aiming at.

OTHER_REGIONS = {
    "subiculum": {
        "id": "SUB", "name": "Subiculum", "abbr": "SUB", "grey": True},
    "entorhinal": {
        "id": "ENT", "name": "Entorhinal cortex", "abbr": "ENT",
        "grey": True},
    "lateral entorhinal": {
        "id": "LENT", "name": "Lateral entorhinal cortex", "abbr": "LENT",
        "grey": True},
    "l entorhinal (need second opinion)": {
        "id": "ENT", "name": "Entorhinal cortex", "abbr": "ENT",
        "grey": True,
        # Scored AND doubted in the same cell. Both facts are kept: the
        # region is entorhinal and the confidence is low, so this reads as
        # relocated and uncertain at once rather than as one or the other.
        "uncertain": True, "side": "Left"},
    "ventral dhc ca1": {
        "id": "VCA1", "name": "Ventral hippocampus CA1", "abbr": "vCA1",
        "grey": True},
    "parietal association ctx": {
        "id": "PTA", "name": "Parietal association cortex", "abbr": "PtA",
        "grey": True},
    # Not grey matter. Kept and labelled rather than excluded, which is the
    # call that was made deliberately: a probe in a fibre tract still
    # records, and what it records is a real thing that should be looked at
    # under its own name and not averaged into a cortical row. `grey` is
    # False so a caller that wants only cell-body regions has one field to
    # filter on instead of a list of special cases.
    "white matter tracts": {
        "id": "WM", "name": "White matter tracts", "abbr": "WM",
        "grey": False},
    "fmj": {
        "id": "FMJ", "name": "Forceps major of the corpus callosum",
        "abbr": "fmj", "grey": False},
}

INTENDED = "intended"
UNCERTAIN = "uncertain"
RELOCATED = "relocated"
MISSED = "missed"
UNSCORED = "unscored"

VERDICT_SAY = {
    INTENDED: "where the map says",
    UNCERTAIN: "probably right, scored without confidence",
    RELOCATED: "somewhere else, and named",
    MISSED: "not in the target, nothing named",
    UNSCORED: "not scored -- nobody has looked",
}

# Which outcomes contribute a row to a matrix.
#
# `missed` does not: there is no label that could honestly go on it.
#
# Nor does `unscored`, decided 2026-09-25. It was kept at first, on the
# argument that "nobody looked" is not evidence the probe is wrong -- and
# that is true, but it is not evidence the probe is RIGHT either, and every
# other rat has shown that a third of these probes are somewhere else. A
# matrix row for a region nobody has checked is a claim about that region,
# so J5 stays out until its row is in the workbook. Adding the row is the
# whole fix: nothing else needs to change.
#
# This set is the only place that judgement lives, on purpose.
USABLE = frozenset((INTENDED, UNCERTAIN, RELOCATED))


def _norm(label):
    """A region label reduced to something two spellings can agree on.

    Three files name these regions and no two agree: the histology
    workbook writes `L-dHC` and `L-Prh`, `electrode_map.xlsx` writes
    `L-DHPC` and `L-PrH`, and `probes.py` carries `Left DHC` / `Left PER`.
    Matching on the raw string means one capital letter detaches a rat's
    whole hippocampus from its score, silently, and the matrix still draws.
    """
    s = "".join(ch for ch in str(label or "").lower() if ch.isalnum())
    for was, now in (("dhpc", "dhc"), ("hcp", "dhc"), ("hpc", "dhc"),
                     ("prh", "per")):
        # Hemisphere prefix survives: `ldhpc` -> `ldhc`, `rprh` -> `rper`.
        s = s.replace(was, now)
    return s


_BY_NORM = {_norm(c): c for c in SHEET_COLUMNS}


def sheet_column(label):
    """The workbook column a region label belongs to, or None."""
    return _BY_NORM.get(_norm(label))


def _squeeze(text):
    return " ".join(str(text or "").split()).strip().lower()


def read_cell(raw):
    """One cell, interpreted. Never raises; an unknown cell says so."""
    say = _squeeze(raw)
    if not say:
        return {"verdict": UNSCORED, "raw": raw, "other": None,
                "recognised": True}
    if say in ("y", "yes"):
        return {"verdict": INTENDED, "raw": raw, "other": None,
                "recognised": True}
    if say in ("n", "no"):
        return {"verdict": MISSED, "raw": raw, "other": None,
                "recognised": True}
    if say == "maybe":
        return {"verdict": UNCERTAIN, "raw": raw, "other": None,
                "recognised": True}
    got = OTHER_REGIONS.get(say)
    if got:
        return {"verdict": RELOCATED, "raw": raw, "other": got,
                "recognised": True}
    # A region nobody has written down yet. Relocated, so it is not thrown
    # away, but flagged as unrecognised so it cannot quietly become a
    # matrix row labelled with the region the probe was aiming at.
    return {"verdict": RELOCATED, "raw": raw, "recognised": False,
            "other": {"id": "OTHER", "name": str(raw).strip(),
                      "abbr": str(raw).strip()[:6], "grey": None}}


def scored(rat):
    """True when this rat has a row in the workbook at all."""
    try:
        return int(rat) in HISTO_RAW
    except (TypeError, ValueError):
        return False


def probe_sanity(rat, regions):
    """One record per probe: where it was aimed, where it is, and whether
    anything may be computed from it.

    `regions` is `probes.regions_for(...)` output -- the twelve DEWEY
    groups with their channels. Returned in the same order, one record
    each, so a caller can zip them without matching on names.

    The matrix keeps twelve slots and relabels them; it does not grow a row
    per discovered region. That is not a shortcut, it is forced: J4 has
    THREE probes in subiculum and J10 has four, so "one row per true
    region" would put two left-hemisphere subiculum groups on one row with
    nothing to tell them apart. The slot stays the identity -- it is the
    channel group, which is a real, distinct thing -- and `label` carries
    the truth: "Left subiculum (aimed at Left PER)".
    """
    row = HISTO_RAW.get(int(rat)) if scored(rat) else None
    out = []
    for r in (regions or []):
        intended = r.get("region") or r.get("id")
        col = sheet_column(r.get("sheet_label") or intended)
        cell = read_cell(row.get(col) if (row and col) else None)
        out.append(_record(r, intended, col, cell, scored(rat)))
    return out


def _record(r, intended, col, cell, have_row):
    verdict = cell["verdict"]
    hemi = r.get("hemisphere") or ""
    other = cell.get("other")

    # A relocation inherits the probe's hemisphere unless the cell named
    # one itself -- J7's "L entorhinal" says Left out loud, and the column
    # it sits in is the left one, so the two agree; if they ever did not,
    # the cell wins, because somebody wrote it while looking at the slide.
    side = (other or {}).get("side") or hemi
    if verdict == RELOCATED:
        # "Left subiculum", not "Left Subiculum". The stored name is
        # capitalised because it stands alone in the picker; prefixing a
        # hemisphere makes it mid-sentence, and every one of these reads
        # correctly lowered -- "Right forceps major of the corpus
        # callosum", "Left parietal association cortex". Acronyms are
        # safe because none of them START with one.
        lower = (other["name"][:1].lower() + other["name"][1:]
                 if other.get("name") else "")
        name = ((side + " " + lower) if side else other["name"])
        actual_id = ((side[0].upper() + "_" + other["id"]) if side
                     else other["id"])
        label = name + " (aimed at " + intended + ")"
    elif verdict == UNSCORED:
        name, actual_id = intended, r.get("id")
        label = intended + (" (not scored)" if not have_row
                            else " (no score in this row)")
    else:
        name, actual_id = intended, r.get("id")
        label = intended

    uncertain = (verdict == UNCERTAIN) or bool((other or {}).get("uncertain"))

    return {
        "slot": r.get("id"),
        "channels": list(r.get("csc") or r.get("channels") or []),
        "intended": intended,
        "sheet_column": col,
        "verdict": verdict,
        "raw": cell.get("raw"),
        "recognised": cell.get("recognised", True),
        "actual_id": actual_id,
        "actual": name,
        "label": label,
        "abbr": (other or {}).get("abbr") or r.get("abbr"),
        "grey": True if other is None else other.get("grey"),
        "uncertain": uncertain,
        "usable": verdict in USABLE,
        "why": _why(verdict, intended, name, cell, uncertain),
    }


def _why(verdict, intended, name, cell, uncertain):
    """The sentence a hover shows. Written here so every surface that
    explains a blocked-out cell explains it the same way."""
    if verdict == INTENDED:
        return ("Histology puts this probe in " + intended
                + ", which is where it was aimed.")
    if verdict == UNCERTAIN:
        return ("Histology scored " + intended + " as “maybe”. "
                "Probably right, but it was written down without "
                "confidence, so anything computed from it carries that.")
    if verdict == MISSED:
        return ("Histology says this probe is not in " + intended
                + ", and does not say where it is instead. There is no "
                "region label that could honestly go on these channels, "
                "so nothing is computed from them.")
    if verdict == UNSCORED:
        return ("This rat has no row in the histology workbook, so nobody "
                "has checked where the probe is. That is not the same as a "
                "probe known to have missed, but it is not evidence that it "
                "hit either, so nothing is computed from it until the rat "
                "is scored. Add its row to " + SHEET_FILE + " to include it.")
    bits = ["Histology puts this probe in " + name + ", not " + intended
            + ". The signal is real; the label is not the one on the map, "
            "and it is drawn under its own name."]
    if not cell.get("recognised"):
        bits.append("The workbook wrote “" + str(cell.get("raw"))
                    + "”, which is not a region this app knows. It is "
                    "shown as written and should be added to "
                    "OTHER_REGIONS in backend/histo.py.")
    if uncertain:
        bits.append("The same cell asks for a second opinion, so the "
                    "relocation itself is not settled.")
    return "  ".join(bits)


def summary(records):
    """A one-line count for a card header, and the lists behind it."""
    by = {}
    for rec in records or []:
        by.setdefault(rec["verdict"], []).append(rec["intended"])
    return {
        "n": len(records or []),
        "usable": sum(1 for r in (records or []) if r["usable"]),
        "by_verdict": {k: sorted(v) for k, v in by.items()},
        "unrecognised": sorted(r["raw"] for r in (records or [])
                               if not r.get("recognised")),
    }


# --------------------------------------------------------------------------
# Which slide photographs belong to which probe
# --------------------------------------------------------------------------
#
# The photographs are named by hand ("J4_Missed_Prh_L", "J6_OFC_ACC",
# "J11_R_Dhc_L_Maybe") and `histoimg.parse_name` reads the region and side
# out of each. This joins them to the probes, and takes the file index as
# an argument so this module still never opens a file.
#
# A slide with no side applies to both hemispheres, and so does one whose
# side cannot be told (J11_R_Dhc_L names both): shown against both probes,
# and marked, rather than guessed onto one. A slide naming two regions
# ("J6_OFC_ACC") belongs to both.

_IMG_REGION_TO_ABBR = {"acc": "ACC", "ofc": "OFC", "rsc": "RSC",
                       "por": "POR", "prh": "PER", "hpc": "DHC"}


def slides_for(records, files):
    """{slot: [slide, ...]} for one rat's probes.

    `records` is `probe_sanity(...)` output; `files` is one rat's entry
    from `histoimg.index()["rats"]` -- its `files` list.
    """
    out = {r.get("slot"): [] for r in (records or [])}
    # One slide photographed twice is one slide. J11_L_OFC_ACC exists as a
    # .jpg and a .tif of the same section; showing both puts the same
    # picture beside a probe twice and reads as two pieces of evidence.
    # The .tif wins -- it is the original the .jpg was exported from.
    seen = {}
    for f in (files or []):
        stem = ((f.get("parsed") or {}).get("stem") or f.get("file") or "")
        prev = seen.get(stem.lower())
        if prev is None or str(f.get("file", "")).lower().endswith(".tif"):
            seen[stem.lower()] = f
    for f in seen.values():
        p = f.get("parsed") or {}
        abbrs = {_IMG_REGION_TO_ABBR.get(i) for i in (p.get("region_ids")
                                                      or [])}
        abbrs.discard(None)
        side = p.get("side")
        unsure_side = bool(p.get("side_ambiguous"))
        for r in (records or []):
            if r.get("abbr_intended", None) is not None:
                ab = r["abbr_intended"]
            else:
                ab = _intended_abbr(r)
            if ab not in abbrs:
                continue
            hemi = (r.get("intended") or "").split(" ")[0].lower()
            if side and not unsure_side and side != hemi:
                continue
            out[r.get("slot")].append({
                "file": f.get("file"),
                "says": f.get("says"),
                "verdicts": [v.get("raw") for v in (p.get("verdicts") or [])],
                "notes": list(p.get("notes") or []),
                "side": side,
                "side_unclear": unsure_side,
                "both_sides": side is None and not unsure_side,
                "other_regions": sorted(abbrs - {ab}),
                "derived": bool(f.get("derived")),
                "pixels": f.get("pixels"),
            })
    return out


def _intended_abbr(rec):
    """The region the probe was AIMED at, as an abbreviation -- the slides
    are named after the target, not after where the probe ended up."""
    name = rec.get("intended") or ""
    return name.split(" ")[-1].upper() if name else None
