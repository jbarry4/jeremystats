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


def _with_depths(col):
    """Attach the depth of each contact, top-down at the contact pitch."""
    top = col["y_top_um"]
    return [top - CONTACT_PITCH_UM * i for i in range(len(col["csc"]))]


PROBES = {
    "h3": {
        "id": "h3",
        "name": "H3 (single linear array)",
        "note": "One column of contacts, so channel order is depth order and "
                "a CSD runs straight down it. This is what BARRY has always "
                "assumed.",
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
}


def get(probe_id):
    return PROBES.get(str(probe_id or "h3").lower())


def listing():
    """Everything the client needs to offer the choice and lay out the panes."""
    return [
        {"id": p["id"], "name": p["name"], "note": p["note"],
         "columns": p["columns"], "pitch_um": CONTACT_PITCH_UM}
        for p in (PROBES["h3"], PROBES["h10d"])
    ]


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
