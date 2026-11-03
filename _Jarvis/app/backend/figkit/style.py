"""
figkit/style.py -- journal profiles: how big, which face, how heavy.

A profile is everything about a figure that a journal decides rather than
the data: the widths it prints at, the face, the point sizes, the weight of a
line, how panels are lettered. Choosing Nature and then choosing "double"
gives 183 mm across in Arial at 5-7 pt, exactly as `joefigs.py` already
draws tab 9; choosing the lab page keeps the look every figure made before
this one had.

Sizes are in points and millimetres because that is how journals state them.
Everything is converted to inches once, in `geometry`, and nowhere else.
"""
from __future__ import annotations

MM = 1.0 / 25.4

#: Letters: "lower" a b c (Nature), "upper" A B C (Cell, J Neurosci).
PROFILES = {
    "nature": {
        "name": "Nature",
        "widths": [("single", "One column", 89.0),
                   ("one_half", "One and a half columns", 120.0),
                   ("double", "Two columns", 183.0)],
        "max_height_mm": 247.0,
        "font": ["Arial", "Helvetica", "Liberation Sans"],
        "pt": {"title": 8.0, "sub": 6.5, "panel": 7.0, "label": 6.5,
               "tick": 6.0, "small": 5.5, "letter": 8.0, "meta": 5.0},
        "line_pt": 0.5, "letters": "lower", "dpi": 600,
        "accent": "#1A1A1A", "header": False,
    },
    "jneurosci": {
        "name": "J Neurosci",
        "widths": [("single", "One column", 85.0),
                   ("one_half", "One and a half columns", 116.0),
                   ("double", "Two columns", 176.0)],
        "max_height_mm": 230.0,
        "font": ["Arial", "Helvetica", "Liberation Sans"],
        "pt": {"title": 9.0, "sub": 7.0, "panel": 8.0, "label": 7.5,
               "tick": 7.0, "small": 6.0, "letter": 10.0, "meta": 5.5},
        "line_pt": 0.6, "letters": "upper", "dpi": 600,
        "accent": "#1A1A1A", "header": False,
    },
    "cell": {
        "name": "Cell",
        "widths": [("single", "One column", 85.0),
                   ("one_half", "One and a half columns", 114.0),
                   ("double", "Two columns", 174.0)],
        "max_height_mm": 225.0,
        "font": ["Arial", "Helvetica", "Liberation Sans"],
        "pt": {"title": 8.0, "sub": 6.5, "panel": 7.0, "label": 7.0,
               "tick": 6.0, "small": 5.5, "letter": 9.0, "meta": 5.0},
        "line_pt": 0.5, "letters": "upper", "dpi": 600,
        "accent": "#1A1A1A", "header": False,
    },
    "poster": {
        "name": "Poster or slide",
        "widths": [("slide", "Slide 16:9", 338.7),
                   ("poster_panel", "Poster panel", 400.0),
                   ("poster_wide", "Poster, wide", 800.0)],
        "max_height_mm": 1000.0,
        "font": ["Arial", "Helvetica", "Liberation Sans"],
        "pt": {"title": 28.0, "sub": 18.0, "panel": 20.0, "label": 18.0,
               "tick": 16.0, "small": 13.0, "letter": 28.0, "meta": 10.0},
        "line_pt": 1.5, "letters": "upper", "dpi": 200,
        "accent": "#154734", "header": True,
    },
    "lab": {
        "name": "Lab page",
        # The page presets every figure before this one was made on
        # (compose.PAGE_PRESETS), kept so nothing that worked stops working.
        "widths": [("letter_landscape", "Letter, landscape", 279.4),
                   ("letter_portrait", "Letter, portrait", 215.9),
                   ("a4_landscape", "A4, landscape", 297.0),
                   ("a4_portrait", "A4, portrait", 210.0),
                   ("slide_16_9", "Slide 16:9", 338.7),
                   ("square", "Square", 228.6),
                   ("figure_1col", "Journal column, 3.5 in", 88.9),
                   ("figure_2col", "Journal two columns, 7.2 in", 182.9)],
        "heights": {"letter_landscape": 215.9, "letter_portrait": 279.4,
                    "a4_landscape": 210.0, "a4_portrait": 297.0,
                    "slide_16_9": 190.5, "square": 228.6,
                    "figure_1col": 76.2, "figure_2col": 114.3},
        "max_height_mm": 600.0,
        "font": ["DejaVu Sans"],
        "pt": {"title": 14.0, "sub": 9.5, "panel": 10.0, "label": 8.5,
               "tick": 7.5, "small": 6.5, "letter": 12.0, "meta": 7.0},
        "line_pt": 0.8, "letters": "upper", "dpi": 300,
        "accent": "#154734", "header": True,
    },
}

DEFAULT = "nature"

INK = "#1A1A1A"
MUTED = "#5f6b66"
GRID = "#d9dfdc"
EVENT = "#c0392b"
FOOT_BG = "#f4f6f5"


def profile(pid):
    return PROFILES.get(pid) or PROFILES[DEFAULT]


def width_mm(pid, wid):
    """The page width this profile prints `wid` at, in mm."""
    p = profile(pid)
    for k, _name, mm in p["widths"]:
        if k == wid:
            return mm
    return p["widths"][-1][2]


def default_height_mm(pid, wid, rows):
    """A height to start from: the lab page's own, or a row-led guess."""
    p = profile(pid)
    if p.get("heights") and wid in p["heights"]:
        return p["heights"][wid]
    w = width_mm(pid, wid)
    per_row = max(38.0, min(70.0, w * 0.34))
    return round(min(p["max_height_mm"], 22.0 + per_row * max(1, rows)), 1)


def letter_for(pid, i):
    """The letter for the i-th panel in reading order."""
    p = profile(pid)
    s = ""
    n = i
    while True:
        s = chr(ord("a") + n % 26) + s
        n = n // 26 - 1
        if n < 0:
            break
    return s.upper() if p["letters"] == "upper" else s


def family(pid):
    """The first face this profile names that matplotlib actually has."""
    try:
        from matplotlib import font_manager
        have = {f.name for f in font_manager.fontManager.ttflist}
    except Exception:                                     # noqa: BLE001
        have = set()
    for f in profile(pid)["font"]:
        if f in have:
            return f
    return "DejaVu Sans"


def rc(pid):
    """matplotlib settings for this profile. Fonts embedded as TrueType in
    PDF and kept as text in SVG, so a journal's production desk can edit a
    word without redrawing the figure."""
    p = profile(pid)
    lw = p["line_pt"]
    return {
        "font.family": family(pid),
        "font.size": p["pt"]["label"],
        "axes.linewidth": lw, "xtick.major.width": lw,
        "ytick.major.width": lw, "xtick.minor.width": lw * 0.7,
        "ytick.minor.width": lw * 0.7, "lines.linewidth": max(lw, 0.6),
        "xtick.major.size": 2.5 if lw < 1 else 5,
        "ytick.major.size": 2.5 if lw < 1 else 5,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "axes.unicode_minus": True,
    }


def describe():
    """Profiles as the builder offers them."""
    out = []
    for pid, p in PROFILES.items():
        out.append({
            "id": pid, "name": p["name"],
            "widths": [{"id": k, "name": n, "mm": mm}
                       for k, n, mm in p["widths"]],
            "max_height_mm": p["max_height_mm"],
            "letters": p["letters"], "dpi": p["dpi"],
            "pt": dict(p["pt"]),
            "heights": dict(p.get("heights") or {}),
        })
    return out
