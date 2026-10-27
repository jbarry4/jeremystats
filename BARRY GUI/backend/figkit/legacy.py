"""
figkit/legacy.py -- a figure made by the old builder, as a figkit layout.

The old builder kept one layout for the whole page -- the window, the
filters, the channels and the marks at the top, and panels that inherited
them -- and drew on the lab's page presets. A figkit panel carries its own
settings, so each panel here gets the page's settings folded into its
`params`, the profile is the lab page, and the width is the page preset it
was drawn on. Nothing is invented: a key the old record never wrote down is
left out, and the panel says so in its lineage the way any panel would.

    from_recipe(recipe, run=None) -> layout
"""
from __future__ import annotations

from . import style

#: What the old layout held at the top and every panel inherited.
PAGE_KEYS = ("t0", "t1", "highpass", "lowpass", "notch", "channels",
             "bad_channels", "spacing_um", "gain", "cmap")
#: What an old panel could carry of its own.
PANEL_KEYS = ("cmap", "channels", "clim", "ylim", "tf_channels", "tf_mode",
              "fmin", "fmax", "fview_min", "fview_max", "stft_mode", "probe",
              "probe_view", "probe_columns", "channel", "smooth", "normalize")


def from_recipe(recipe, run=None):
    recipe = recipe or {}
    run = run or {}
    sessions = recipe.get("sessions") or {}
    primary = sessions.get("default") or (list(sessions.values())[0]
                                          if sessions else {})
    ident = recipe.get("identity") or run.get("session") or {}
    page = recipe.get("page") or "letter_landscape"
    lab = style.PROFILES["lab"]
    if page not in dict((k, 1) for k, _n, _mm in lab["widths"]):
        page = "letter_landscape"

    base = {k: recipe[k] for k in PAGE_KEYS
            if recipe.get(k) is not None}
    events = recipe.get("events") or []
    if events:
        base["events"] = events
        base["events_source"] = "the original figure"

    panels = []
    for i, p in enumerate(recipe.get("panels") or []):
        params = dict(base)
        for k in PANEL_KEYS:
            if p.get(k) is not None:
                params[k] = p[k]
        panels.append({
            "uid": "p%d" % (i + 1), "tool": "xplore",
            "plot": p.get("panel") or "traces",
            "row": int(p.get("row") or 0), "col": int(p.get("col") or 0),
            "rowspan": int(p.get("rowspan") or 1),
            "colspan": int(p.get("colspan") or 1),
            "title": p.get("title") or "",
            "params": params,
        })
    rows = max([p["row"] + p["rowspan"] for p in panels] or [1])
    cols = max([p["col"] + p["colspan"] for p in panels] or [1])
    meta = recipe.get("metadata") or {}
    notes = (meta.get("notes") or "").strip()
    return {
        "schema": "fig/2", "profile": "lab", "width": page,
        "height_mm": lab["heights"].get(page),
        "rows": max(rows, int(recipe.get("rows") or 1)),
        "cols": max(cols, int(recipe.get("cols") or 1)),
        "title": recipe.get("title") or run.get("label") or "Figure",
        "subtitle": recipe.get("subtitle") or "",
        "recording": {
            "gid": ident.get("gid"),
            "label": ident.get("label") or recipe.get("session_label"),
            "path": primary.get("path") or meta.get("source_path"),
            "invert": bool(primary.get("invert", True)),
            "identity": ident or None,
        },
        "panels": panels,
        "footer": {"notes": notes} if notes else {},
        "legacy": {"run": run.get("id"), "schema": recipe.get("schema")},
    }
