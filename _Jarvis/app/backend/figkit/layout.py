"""
figkit/layout.py -- where every panel sits, in inches, worked out once.

The preview is drawn panel by panel, so that changing one word redraws one
panel rather than the page. That only works if a panel's box is the same
whether it is drawn alone as a tile or with every other panel in the export.
So nothing here measures drawn text, and nothing calls `tight_layout`: a box
comes from the grid, the profile's point sizes and the spec, and from nothing
that depends on what happened to be drawn beside it.

    PRESETS             the grid shapes the builder starts from
    apply_preset(layout, preset_id)
    page_size(layout)   (width_in, height_in)
    geometry(layout, footer_in)
                        {page, header, footer, panels: [{box, axes, letter,
                         title}]} -- every rectangle in inches from the
                         bottom-left corner of the page
    reading_order(panels)
"""
from __future__ import annotations

from . import style

PT = 1.0 / 72.0

#: Shapes to start from. `cells` are (row, col, rowspan, colspan) in the
#: order panels are dropped into them.
PRESETS = [
    {"id": "1", "name": "One", "rows": 1, "cols": 1,
     "cells": [(0, 0, 1, 1)]},
    {"id": "1x2", "name": "Two across", "rows": 1, "cols": 2,
     "cells": [(0, 0, 1, 1), (0, 1, 1, 1)]},
    {"id": "2x1", "name": "Two stacked", "rows": 2, "cols": 1,
     "cells": [(0, 0, 1, 1), (1, 0, 1, 1)]},
    {"id": "1x3", "name": "Three across", "rows": 1, "cols": 3,
     "cells": [(0, 0, 1, 1), (0, 1, 1, 1), (0, 2, 1, 1)]},
    {"id": "2x2", "name": "Two by two", "rows": 2, "cols": 2,
     "cells": [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 1), (1, 1, 1, 1)]},
    {"id": "big_left", "name": "One big, two beside it", "rows": 2,
     "cols": 2, "cells": [(0, 0, 2, 1), (0, 1, 1, 1), (1, 1, 1, 1)]},
    {"id": "big_top", "name": "One wide on top, two under it", "rows": 2,
     "cols": 2, "cells": [(0, 0, 1, 2), (1, 0, 1, 1), (1, 1, 1, 1)]},
    {"id": "big_bottom", "name": "Two on top, one wide under them",
     "rows": 2, "cols": 2,
     "cells": [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 2)]},
    {"id": "3x2", "name": "Three by two", "rows": 2, "cols": 3,
     "cells": [(r, c, 1, 1) for r in range(2) for c in range(3)]},
    {"id": "2x3", "name": "Two by three", "rows": 3, "cols": 2,
     "cells": [(r, c, 1, 1) for r in range(3) for c in range(2)]},
]

MAX_ROWS = 6
MAX_COLS = 4


def preset(pid):
    for p in PRESETS:
        if p["id"] == pid:
            return p
    return None


def apply_preset(layout, pid):
    """Re-slot the panels into a preset's cells, in reading order.

    Panels beyond the preset's cells go in new rows underneath rather than
    being dropped: a shape is a starting point, and losing a panel to one is
    the kind of thing that would make somebody stop using shapes.
    """
    got = preset(pid)
    if not got:
        raise ValueError("No grid shape called %r" % pid)
    panels = reading_order(layout.get("panels") or [])
    rows, cols = got["rows"], got["cols"]
    cells = list(got["cells"])
    extra_row = rows
    for i, p in enumerate(panels):
        if i < len(cells):
            r, c, rs, cs = cells[i]
        else:
            j = i - len(cells)
            r, c, rs, cs = extra_row + j // cols, j % cols, 1, 1
        p.update(row=r, col=c, rowspan=rs, colspan=cs)
        rows = max(rows, r + rs)
    layout["rows"] = min(MAX_ROWS, rows)
    layout["cols"] = min(MAX_COLS, cols)
    layout["panels"] = panels
    layout["preset"] = pid
    return layout


def reading_order(panels):
    """Top to bottom, left to right -- the order panels are lettered in."""
    return sorted(panels, key=lambda p: (int(p.get("row") or 0),
                                         int(p.get("col") or 0)))


def letters(layout):
    """{panel uid: letter}, in reading order."""
    pid = layout.get("profile") or style.DEFAULT
    out = {}
    for i, p in enumerate(reading_order(layout.get("panels") or [])):
        out[p.get("uid")] = style.letter_for(pid, i)
    return out


def page_size(layout):
    """(width_in, height_in) for this layout's profile and width."""
    pid = layout.get("profile") or style.DEFAULT
    wid = layout.get("width")
    w_mm = style.width_mm(pid, wid)
    h_mm = layout.get("height_mm")
    try:
        h_mm = float(h_mm)
    except (TypeError, ValueError):
        h_mm = None
    if not h_mm:
        h_mm = style.default_height_mm(pid, wid, int(layout.get("rows") or 1))
    h_mm = max(30.0, min(float(style.profile(pid)["max_height_mm"]), h_mm))
    return w_mm * style.MM, h_mm * style.MM


def _pads(spec, plot, prof):
    """The room inside a panel's box for what is drawn around its axes.

    From point sizes and from what the panel says it carries -- whether it
    has a colour bar, how long its tick labels can get -- never from text
    that has been drawn. `plot` is the adapter's description of the plot.
    """
    pt = prof["pt"]
    plot = plot or {}
    axes = plot.get("axes") or {}
    labels = spec.get("labels") or {}
    tick_chars = float(plot.get("ytick_chars") or 5)
    anatomy = bool(labels.get("anatomy") and plot.get("anatomy"))
    has_title = bool((spec.get("title") or "").strip())
    scalebar = bool(labels.get("scalebar") and plot.get("scalebar"))

    top = (pt["panel"] * 1.7 if has_title else pt["letter"] * 0.9) * PT
    left = (pt["tick"] * tick_chars * 0.58 + pt["label"] * 1.9 + 3) * PT
    bottom = (pt["tick"] * 1.7 + pt["label"] * 1.9 + 2) * PT
    right = 3 * PT
    if anatomy:
        # Region names sit to the right of the data ("DG GCL1" is the
        # longest the layer sheets use).
        right += (pt["small"] * 8 * 0.58 + 4) * PT
    if axes.get("c") and spec.get("colorbar", True):
        right += (6 + pt["small"] * 4.2 + 4) * PT
    if scalebar:
        # No axes to label, but the bars and their words sit under and
        # beside the data.
        left = (pt["small"] * 1.2 + pt["letter"] * 0.6 + 6) * PT
        bottom = (pt["small"] * 2.6 + 4) * PT
    return {"top": top, "left": left, "bottom": bottom, "right": right}


def header_in(layout):
    prof = style.profile(layout.get("profile"))
    h = 0.0
    if (layout.get("title") or "").strip():
        h += prof["pt"]["title"] * 1.5 * PT
    if (layout.get("subtitle") or "").strip():
        h += prof["pt"]["sub"] * 1.5 * PT
    return h + (0.06 if h else 0.03)


def geometry(layout, footer_in, plots=None):
    """Every rectangle on the page, in inches from its bottom-left corner.

    `footer_in` is the footer band's height, which the caller has already
    worked out from the footer's own lines (render.footer_plan). `plots`
    maps a panel uid to its adapter's plot description, for the pads.
    """
    plots = plots or {}
    prof = style.profile(layout.get("profile"))
    w, h = page_size(layout)
    rows = max(1, min(MAX_ROWS, int(layout.get("rows") or 1)))
    cols = max(1, min(MAX_COLS, int(layout.get("cols") or 1)))
    margin = 2.0 * style.MM
    gap_x = float(layout.get("gap_mm", 4.0)) * style.MM
    gap_y = float(layout.get("gap_mm", 4.0)) * style.MM

    head = header_in(layout)
    top = h - margin - head
    bottom = footer_in + margin
    left, right = margin, w - margin
    if top - bottom < 0.4:
        raise ValueError(
            "The page is too short for its title and footer. Make it "
            "taller, or use fewer rows.")
    cw = (right - left - gap_x * (cols - 1)) / cols
    ch = (top - bottom - gap_y * (rows - 1)) / rows

    out = []
    for p in layout.get("panels") or []:
        r = max(0, min(rows - 1, int(p.get("row") or 0)))
        c = max(0, min(cols - 1, int(p.get("col") or 0)))
        rs = max(1, min(rows - r, int(p.get("rowspan") or 1)))
        cs = max(1, min(cols - c, int(p.get("colspan") or 1)))
        x0 = left + c * (cw + gap_x)
        x1 = x0 + cs * cw + (cs - 1) * gap_x
        y1 = top - r * (ch + gap_y)
        y0 = y1 - rs * ch - (rs - 1) * gap_y
        pad = _pads(p, plots.get(p.get("uid")), prof)
        ax = [x0 + pad["left"], y0 + pad["bottom"],
              x1 - pad["right"], y1 - pad["top"]]
        if ax[2] - ax[0] < 0.25 or ax[3] - ax[1] < 0.2:
            # Too small to hold anything; keep the box honest and let the
            # renderer say so on the panel rather than drawing inside out.
            ax = [x0, y0, x1, y1]
            tiny = True
        else:
            tiny = False
        out.append({
            "uid": p.get("uid"),
            "box": [x0, y0, x1, y1],
            "axes": ax,
            "tiny": tiny,
            "letter_at": [x0, y1],
            "title_at": [ax[0], y1 - prof["pt"]["panel"] * 0.35 * PT],
        })
    return {
        "page": [w, h],
        "header": [left, h - margin - head, right, h - margin],
        "footer": [0.0, 0.0, w, footer_in],
        "panels": out,
        "rows": rows, "cols": cols,
    }
