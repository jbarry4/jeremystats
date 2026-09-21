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
}


def get(probe_id):
    return PROBES.get(str(probe_id or "h3").lower())


#: How many channels each template expects, so a recording can be offered
#: the ones that could actually be true of it. `None` means any number --
#: an H3 is a line of contacts however many there are.
EXPECTS_CHANNELS = {"h3": None, "h10d": 64, "dual": 2 * DUAL_SIZE}


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
         "expects_channels": EXPECTS_CHANNELS.get(p["id"])}
        for p in (PROBES["h3"], PROBES["h10d"], PROBES["dual"])
    ]


#: A short name for the chip. The full names say what the probe IS and are
#: right in a picker; a chip has room for what it is CALLED.
SHORT = {"h3": "H3", "h10d": "H10", "dual": "HIP/M2"}


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
