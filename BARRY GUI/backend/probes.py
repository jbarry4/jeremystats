"""
probes.py -- which physical column each CSC channel sits in.

Why this exists
---------------
A CSD assumes its inputs are a line of contacts at a known spacing. On an H3
that is exactly what the channel order is, so running CSD straight down the
CSC numbers is right. On an ASSY-77 H10-D it is not: the probe has two shanks
of three columns each, and consecutive CSC numbers step *across* columns
rather than down one. Channels 1, 2 and 3 are three different columns at the
same depth. A CSD over that order is not a bad CSD, it is arithmetic over
neighbours that are not neighbours.

So the H10 is described here as six independent linear arrays -- one per
column -- and everything that needs a line of contacts asks for one column at
a time.

Where the numbers come from
---------------------------
Probes/probe_config_H10D_journey.png, panel b, which lays out all six Cheetah
display windows with the pin -> AD channel -> CSC -> Kilosort channel chain
for every contact. The geometry behind it is probeinterface's
cambridgeneurotech/ASSY-77-H10, and the AD channels are from
H10_D_open_Cheetah2026-07-21_16-59-03.cfg.

The pattern is regular once you see it: within a shank the three columns
interleave, so each column takes every third CSC. The two centre columns also
carry the tip contact, which is why they have twelve sites and the outer
columns have ten.

  W1  back shank   centre  x =  18.5 um   CSC 1,4,..,31 + 32   y 330..0
  W3  back shank   left    x =   0.0 um   CSC 2,5,..,29        y 315..45
  W4  back shank   right   x =  37.0 um   CSC 3,6,..,30        y 315..45
  W2  front shank  centre  x = 168.5 um   CSC 33,36,..,63 + 64 y 330..0
  W6  front shank  left    x = 150.0 um   CSC 34,37,..,61      y 315..45
  W5  front shank  right   x = 187.0 um   CSC 35,38,..,62      y 315..45

Contacts are 30 um apart within a column. Slot 21 (y = 15 um) carries no
contact on either shank, so each tip sits 30 um below its neighbour rather
than 15 -- noted on the figure, and the reason the centre columns run to
y = 0 while the outer ones stop at 45.
"""
from __future__ import annotations

CONTACT_PITCH_UM = 30.0


def _column(first, n, with_tip=None):
    """Every third CSC from `first`, optionally plus the tip contact."""
    out = [first + 3 * k for k in range(n)]
    if with_tip is not None:
        out.append(with_tip)
    return out


# CSC numbers, ordered from the top of the shank down to the tip -- the same
# order the figure lists them in, and the order a CSD wants.
H10D_COLUMNS = [
    {"id": "W1", "shank": "back", "column": "centre", "x_um": 18.5,
     "csc": _column(1, 11, with_tip=32), "y_top_um": 330.0},
    {"id": "W3", "shank": "back", "column": "left", "x_um": 0.0,
     "csc": _column(2, 10), "y_top_um": 315.0},
    {"id": "W4", "shank": "back", "column": "right", "x_um": 37.0,
     "csc": _column(3, 10), "y_top_um": 315.0},
    {"id": "W2", "shank": "front", "column": "centre", "x_um": 168.5,
     "csc": _column(33, 11, with_tip=64), "y_top_um": 330.0},
    {"id": "W6", "shank": "front", "column": "left", "x_um": 150.0,
     "csc": _column(34, 10), "y_top_um": 315.0},
    {"id": "W5", "shank": "front", "column": "right", "x_um": 187.0,
     "csc": _column(35, 10), "y_top_um": 315.0},
]


def _with_depths(col, pitch=None):
    """Attach the depth of each contact, top-down at the contact pitch."""
    top = col["y_top_um"]
    p = CONTACT_PITCH_UM if pitch is None else float(pitch)
    return [top - p * i for i in range(len(col["csc"]))]


# --------------------------------------------------------------------------
# Two probes in two places at once
# --------------------------------------------------------------------------
# The KCNT1 recordings are 128 channels because there are two probes in the
# animal, not one probe with twice as many contacts: a linear array in
# hippocampus on CSC 1-64 and a second one in M2 on CSC 65-128.
#
# That distinction is the whole reason this entry exists. Each array is an
# ordinary line of contacts, so a CSD down either one is right -- but a CSD
# down the CHANNEL ORDER crosses from hippocampus to cortex at channel 64
# and computes a second spatial derivative between two contacts that are
# millimetres and one brain region apart. The number it produces is not a
# large current sink; it is nonsense, and nothing about it looks wrong.
#
# So this is the same shape of answer as the H10-D -- independent columns,
# one pane each -- arrived at for a different reason. There it was contacts
# interleaved within one shank; here it is two separate implants.
#
# The split is the same 64/64 that `sessreg.banks_for` writes down, and it
# has to stay that way: the banks are where a person records which region is
# which, and a probe template that disagreed with them would put the M2 label
# on the hippocampal trace.
DUAL_PITCH_UM = 50.0          # the app's default array spacing, not the H10's
DUAL_SIZE = 64


def _linear(first, n, pitch):
    """One straight line of `n` contacts starting at CSC `first`."""
    return {"csc": [first + k for k in range(n)],
            "y_top_um": pitch * (n - 1)}


DUAL_COLUMNS = [
    dict(_linear(1, DUAL_SIZE, DUAL_PITCH_UM),
         id="HPC", shank="hippocampus", column="linear", x_um=0.0,
         region="Hippocampus"),
    dict(_linear(DUAL_SIZE + 1, DUAL_SIZE, DUAL_PITCH_UM),
         id="M2", shank="M2", column="linear", x_um=1000.0,
         region="M2"),
]


# --------------------------------------------------------------------------
# A montage that is not a line at all
# --------------------------------------------------------------------------
# The DEWEY RATs headstage carries 32 channels into twelve bilateral targets,
# two to four wires each. Nothing about it is a shank: channels 1-4 are four
# wires in one structure, and channel 4 and channel 5 are in two different
# structures on opposite sides of the brain.
#
# So `columns` is None, and it means something different here than it does on
# the H3. On an H3 it means "the whole selection is one line, run the CSD
# down it". Here it means there is no line to run one down at all, and
# `regions` is what the recording is actually organised by. Anything wanting
# a spatial derivative off these channels is asking the wrong question; what
# the connectivity work asks for instead is "which channels are in POR", and
# that is `regions_for`.
#
# WHERE THE NUMBERS COME FROM
#
# `electrode_map.xlsx`, sheet "Channel Map", beside this repo's root. It is
# transcribed rather than read, the same way the H10-D's geometry is, so this
# module stays free of file I/O -- and `tools/check_electrode_map.py` reads
# the workbook and asserts the two still agree, so the transcription cannot
# drift without something saying so.
#
# TWO THINGS THE WORKBOOK DISAGREES WITH THE OLDER PIPELINE ABOUT
#
# The HOF connectivity code (`0 GUI Foundation/lib/regions.ts` on the VACC)
# maps left OFC to 23-24 and left ACC to 21-22. The workbook has them the
# other way round. It also calls 31-32 "R-HCP / Hippocampus" where the older
# map says "Right DHC / Dorsal Hippocampus", and spells perirhinal "PrH"
# where the older map says "PER".
#
# The workbook wins, confirmed 2026-09-24: it describes the headstage these
# recordings were made on, and the older map describes the 64-channel pilot
# rig. The left OFC/ACC pair carries a `was` note recording what the old map
# said, because this is not a tidy-up -- a connectivity figure made from the
# J1/J2 pilot has those two regions swapped relative to anything made here,
# and somebody laying the two side by side has to know that.
#
# The display names are normalised to the twelve the connectivity work
# already uses -- "Left PER", "Right DHC" -- so one region vocabulary, one
# colour key and one network order serve the whole pipeline. The workbook's
# own spelling is kept beside each as `sheet_label`.
DEWEY_SIZE = 32

DEWEY_REGIONS = [
    {"id": "L_POR", "region": "Left POR", "abbr": "POR", "hemisphere": "Left",
     "name": "Postrhinal cortex", "csc": [1, 2, 3, 4], "sheet_label": "L-Por"},
    {"id": "L_PER", "region": "Left PER", "abbr": "PER", "hemisphere": "Left",
     "name": "Perirhinal cortex", "csc": [5, 6, 7, 8], "sheet_label": "L-PrH"},
    {"id": "R_PER", "region": "Right PER", "abbr": "PER", "hemisphere": "Right",
     "name": "Perirhinal cortex", "csc": [9, 10, 11, 12], "sheet_label": "R-PrH"},
    {"id": "R_POR", "region": "Right POR", "abbr": "POR", "hemisphere": "Right",
     "name": "Postrhinal cortex", "csc": [13, 14, 15, 16], "sheet_label": "R-Por"},
    {"id": "R_OFC", "region": "Right OFC", "abbr": "OFC", "hemisphere": "Right",
     "name": "Orbitofrontal cortex", "csc": [17, 18], "sheet_label": "R-OFC"},
    {"id": "R_ACC", "region": "Right ACC", "abbr": "ACC", "hemisphere": "Right",
     "name": "Anterior cingulate cortex", "csc": [19, 20], "sheet_label": "R-ACC"},
    {"id": "L_OFC", "region": "Left OFC", "abbr": "OFC", "hemisphere": "Left",
     "name": "Orbitofrontal cortex", "csc": [21, 22], "sheet_label": "L-OFC",
     "was": "The older 64-channel HOF map had left ACC on 21-22. Confirmed "
            "2026-09-24: the workbook is right and the old map is not, so a "
            "figure made from the J1/J2 pilot has these two swapped relative "
            "to anything made here."},
    {"id": "L_ACC", "region": "Left ACC", "abbr": "ACC", "hemisphere": "Left",
     "name": "Anterior cingulate cortex", "csc": [23, 24], "sheet_label": "L-ACC",
     "was": "The older 64-channel HOF map had left OFC on 23-24. Confirmed "
            "2026-09-24: the workbook is right and the old map is not, so a "
            "figure made from the J1/J2 pilot has these two swapped relative "
            "to anything made here."},
    {"id": "L_DHC", "region": "Left DHC", "abbr": "DHC", "hemisphere": "Left",
     "name": "Dorsal hippocampus", "csc": [25, 26], "sheet_label": "L-DHPC"},
    {"id": "L_RSC", "region": "Left RSC", "abbr": "RSC", "hemisphere": "Left",
     "name": "Retrosplenial cortex", "csc": [27, 28], "sheet_label": "L-RSC"},
    {"id": "R_RSC", "region": "Right RSC", "abbr": "RSC", "hemisphere": "Right",
     "name": "Retrosplenial cortex", "csc": [29, 30], "sheet_label": "R-RSC"},
    {"id": "R_DHC", "region": "Right DHC", "abbr": "DHC", "hemisphere": "Right",
     "name": "Dorsal hippocampus", "csc": [31, 32], "sheet_label": "R-HCP",
     "sheet_name": "Hippocampus",
     "was": "The workbook says plain 'Hippocampus' here and 'Dorsal "
            "hippocampus' for the left side on 25-26. Read as the same "
            "target on both sides, which is what a bilateral implant means; "
            "the asymmetry is the workbook's, not a typo introduced here."},
]

#: Hue is the region, tone is the hemisphere. These are the only literal
#: colours in the app that are not theme tokens, and they are literal for the
#: same reason an anatomical atlas is: POR is this blue in the figures on the
#: cluster, in the published key, and here, or the three cannot be read
#: against one another. Transcribed from `15 Connectivity Matrix/scripts/
#: network_lib.py` and `1 Key/brain_region_key.png`.
DEWEY_REGION_COLORS = {
    "Left POR": "#8EB8EC", "Right POR": "#1D5FAF",
    "Left PER": "#8AF0CB", "Right PER": "#18B47C",
    "Left OFC": "#F6A484", "Right OFC": "#BE400E",
    "Left ACC": "#EE8CB1", "Right ACC": "#B11B53",
    "Left DHC": "#7AFF7A", "Right DHC": "#00CC00",
    "Left RSC": "#FFD47A", "Right RSC": "#CC8B00",
}

#: Where each region sits on the ring in a connectivity diagram: ACC at the
#: top, then mirrored down each side. Same order as the cluster's figures, so
#: a matrix drawn here can be laid beside one drawn there.
DEWEY_NETWORK_ORDER = [
    "Right ACC", "Right OFC", "Right DHC", "Right RSC", "Right PER", "Right POR",
    "Left POR", "Left PER", "Left RSC", "Left DHC", "Left OFC", "Left ACC",
]


PROBES = {
    "h3": {
        "id": "h3",
        "name": "H3 (single linear array)",
        "note": "One column of contacts, so channel order is depth order and "
                "a CSD runs straight down it. This is what Jarvis has always "
                "assumed.",
        # 50 um, which is what every CSD in the app already defaults to
        # (`spacing_um`). The listing used to report 30 for all three
        # templates -- the H10-D's within-column pitch -- which was right
        # for exactly one of them. Nothing read it, so nothing was wrong;
        # it would have been the moment anything did.
        "pitch_um": 50.0,
        "columns": None,          # no grouping: the whole selection is a line
    },
    "h10d": {
        "id": "h10d",
        "name": "ASSY-77 H10-D (2 shanks x 3 columns)",
        "note": "Two shanks of three interleaved columns. Consecutive CSC "
                "numbers are different columns, so a CSD has to be run one "
                "column at a time -- six of them -- rather than down the "
                "channel order.",
        "columns": [
            dict(c, depths_um=_with_depths(c), n=len(c["csc"]),
                 label="%s %s %s" % (c["id"], c["shank"], c["column"]))
            for c in H10D_COLUMNS
        ],
    },
    "dual": {
        "id": "dual",
        "name": "Dual array (hippocampus + M2)",
        "note": "Two separate linear probes: CSC 1-64 in hippocampus, CSC "
                "65-128 in M2. Each is a line of contacts, so a CSD down "
                "either one is right -- but a CSD down the channel order "
                "steps across the gap at channel 64 and subtracts cortex "
                "from hippocampus. Two panes, one per implant.",
        "pitch_um": DUAL_PITCH_UM,
        "columns": [
            dict(c, depths_um=_with_depths(c, DUAL_PITCH_UM),
                 n=len(c["csc"]),
                 label="%s (CSC %d-%d)" % (c["region"], c["csc"][0],
                                           c["csc"][-1]))
            for c in DUAL_COLUMNS
        ],
    },
    "dewey32": {
        "id": "dewey32",
        "name": "DEWEY 32 (12 bilateral targets)",
        "note": "Twelve regions on one 32-channel headstage, two to four "
                "wires each. Not an array: channels 4 and 5 sit in "
                "different structures on opposite sides of the brain, so "
                "there is no line here for a CSD to run down. Panes group "
                "by region instead.",
        "columns": None,
        "regions": [
            dict(r, n=len(r["csc"]),
                 color=DEWEY_REGION_COLORS[r["region"]],
                 label="%s (CSC %s)" % (
                     r["region"],
                     "%d-%d" % (r["csc"][0], r["csc"][-1])
                     if len(r["csc"]) > 1 else str(r["csc"][0])))
            for r in DEWEY_REGIONS
        ],
        "network_order": list(DEWEY_NETWORK_ORDER),
    },
}


def get(probe_id):
    return PROBES.get(str(probe_id or "h3").lower())


#: How many channels each template expects, so a recording can be offered
#: the ones that could actually be true of it. `None` means any number --
#: an H3 is a line of contacts however many there are.
EXPECTS_CHANNELS = {"h3": None, "h10d": 64, "dual": 2 * DUAL_SIZE,
                    "dewey32": DEWEY_SIZE}


def listing():
    """Everything the client needs to offer the choice and lay out the panes."""
    return [
        {"id": p["id"], "name": p["name"], "note": p["note"],
         "columns": p["columns"],
         # Per probe now, because they differ: 30 um within an H10-D
         # column, 50 um on the linear arrays. It used to say 30 for all
         # three, which was right for exactly one of them.
         "pitch_um": p.get("pitch_um", CONTACT_PITCH_UM),
         "n_columns": len(p["columns"] or []) or 1,
         # Regions, for a montage that is grouped by anatomy rather than by
         # depth. Absent on the arrays, and that absence is the difference:
         # a template with regions has no line to run a CSD down.
         "regions": p.get("regions"),
         "network_order": p.get("network_order"),
         # How the template splits its channels, whichever way it does it.
         # A region montage has no columns and still has twelve groups, and
         # a picker that read only `columns` offered it as though it had
         # one -- the same blind spot that made choosing it fail with
         # "that probe has no column map to lay out".
         "n_groups": len(p.get("columns") or p.get("regions") or []) or 1,
         "group_kind": "regions" if p.get("regions") else "columns",
         "expects_channels": EXPECTS_CHANNELS.get(p["id"])}
        for p in (PROBES["h3"], PROBES["h10d"], PROBES["dual"],
                  PROBES["dewey32"])
    ]


#: A short name for the chip. The full names say what the probe IS and are
#: right in a picker; a chip has room for what it is CALLED.
SHORT = {"h3": "H3", "h10d": "H10", "dual": "HIP/M2", "dewey32": "DEWEY"}


def state_of(rec):
    """Three answers about a recording's probe, and they are not degrees.

    `confirmed`  somebody said so. Every view can rely on it.
    `detected`   the channel count supports a guess and nobody has agreed.
                 The guess is USED -- a dual implant drawn as one array is
                 worse than one drawn as two and marked unconfirmed -- but
                 it is never presented as a fact.
    `unknown`    no count, or a count that supports nothing. Draws as a
                 question rather than as a default, because "H3" and "we do
                 not know" are different things and only one of them is
                 safe to run a CSD on.

    The distinction is the point. 71 recordings here read as dual implants
    on their channel count alone, and filing that as a decision would make
    71 guesses indistinguishable from 71 answers -- with no way to find the
    guesses again afterwards.
    """
    rec = rec or {}
    said = rec.get("probe")
    if said and get(said):
        return {
            "state": "confirmed",
            "probe": str(said).lower(),
            "short": SHORT.get(str(said).lower(), str(said).upper()),
            "why": "Set by hand.",
        }
    guess = suggest(rec.get("n_channels"))
    n = rec.get("n_channels")
    if guess and guess != "h3":
        return {
            "state": "detected",
            "probe": guess,
            "short": SHORT.get(guess, guess.upper()),
            "why": "%s channels, which in this lab is two 64-contact "
                   "implants. Nobody has confirmed it." % n,
        }
    if not n:
        return {
            "state": "unknown", "probe": None, "short": "?",
            "why": "Nobody has read a header for this recording, so there "
                   "is no channel count to reason from.",
        }
    if int(n) == DEWEY_SIZE:
        # Named because it is the count every DEWEY recording has, and a
        # person reading "consistent with other things" would have no way to
        # know one of those things is now a template they can pick. Still
        # `unknown`: 32 channels is equally consistent with one linear array,
        # and only somebody who was there knows which went in.
        return {
            "state": "unknown", "probe": None, "short": "?",
            "why": "32 channels. That is the DEWEY 32 montage's count, and "
                   "also a perfectly ordinary linear array, so it is left "
                   "for a person.",
        }
    return {
        "state": "unknown", "probe": None, "short": "?",
        "why": "%s channels. That is consistent with a single linear array "
               "and with other things, so it is left for a person." % n,
    }


def suggest(n_channels):
    """The template a recording with this many channels probably wants.

    A suggestion and never an assignment: two 64-channel probes in two
    regions and one 128-contact array in one region are the same number, and
    only a person knows which was in the animal. What this does is stop the
    list defaulting to the answer that is wrong for every KCNT1 recording in
    the lab.
    """
    try:
        n = int(n_channels or 0)
    except (TypeError, ValueError):
        return "h3"
    if n == 2 * DUAL_SIZE:
        return "dual"
    return "h3"


def regions_for(probe_id, channels, bad=()):
    """Split `channels` (session channel dicts) into this probe's regions.

    The region-shaped twin of `columns_for`, and it returns the same kind of
    answer: a list of the template's groups with `indices` into `channels`.
    Templates that are arrays have no regions and get None, which is the
    honest answer rather than one group called "all".

    `bad` is CSC NUMBERS to leave out -- numbers, never row indices, because
    an index moves the moment somebody toggles even-only. Excluded channels
    are reported as well as dropped: a region down to its last wire is still
    usable and a region down to none is not, and the caller can only tell
    those apart if it is told.
    """
    probe = get(probe_id)
    if not probe or not probe.get("regions"):
        return None
    bad = {int(b) for b in (bad or [])}
    by_number = {}
    for i, ch in enumerate(channels or []):
        num = ch.get("number") if isinstance(ch, dict) else None
        if num is not None:
            by_number.setdefault(int(num), i)
    out = []
    for reg in probe["regions"]:
        idx, csc, missing, excluded = [], [], [], []
        for num in reg["csc"]:
            num = int(num)
            if num in bad:
                excluded.append(num)
                continue
            i = by_number.get(num)
            if i is None:
                missing.append(num)
                continue
            idx.append(i)
            csc.append(num)
        out.append(dict(reg, indices=idx, csc_present=csc,
                        missing=missing, excluded=excluded,
                        usable=bool(idx)))
    return out


def columns_for(probe_id, channels):
    """Split `channels` (session channel dicts) into this probe's columns.

    Returns a list of {..column meta.., "indices": [...]}, where indices are
    positions into `channels` -- which is what every panel request wants.
    Channels the probe does not mention are dropped: a recording with a
    different montage should show nothing in a column rather than something
    wrong.
    """
    probe = get(probe_id)
    if not probe or not probe.get("columns"):
        return None
    by_number = {}
    for i, ch in enumerate(channels or []):
        num = ch.get("number") if isinstance(ch, dict) else None
        if num is not None:
            by_number.setdefault(int(num), i)
    out = []
    for col in probe["columns"]:
        idx, csc, depths = [], [], []
        for num, depth in zip(col["csc"], col["depths_um"]):
            i = by_number.get(int(num))
            if i is None:
                continue
            idx.append(i)
            csc.append(int(num))
            depths.append(depth)
        out.append(dict(col, indices=idx, csc_present=csc,
                        depths_present=depths, missing=len(col["csc"]) - len(idx)))
    return out
