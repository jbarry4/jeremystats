"""
figkit -- every tool's plots, as panels a figure can hold.

The figure builder used to know seven panels, all of them Xplorefinder's, and
nothing any ToolKit tool drew could go into a figure. Here, a tool says what
it can draw and how, and the builder asks it -- the same shape as
`recipe.register`, which is where a tool already says what can be done about
its own runs.

A PANEL is a spec, plain JSON, and nothing else:

    {uid, tool, plot, gid, row, col, rowspan, colspan, title,
     params: {...the tool's own settings, as they were on screen...},
     axes:   {x: {words, unit, range, crop}, y: {...}, c: {...}},
     link:   {x, y, c},                       # share scales, default true
     labels: {anatomy, scalebar, stats}}

An ADAPTER turns a spec into a picture, in two halves so that panels can
agree on a shared scale before any of them is drawn:

    prepare(spec, ctx)  -> the numbers, and their extent ("lim") in the
                           plot's own units. Reads; never draws.
    draw(fig, rect, spec, prep, ctx, st)
                        -> {"main": ax, "axes": [...], "cbar": cax}
                           draws into a rectangle it is given, and nowhere
                           else.

and says, beside that, what a reader needs:

    plots()             what it can draw, each with its axes as
                        {quantity, unit, words} (figkit.units)
    lineage(spec, prep, ctx)
                        where these numbers came from, as short phrases and
                        as fields
    numbers(spec, prep) the plotted numbers, kept with each version

Nothing pools here. A figure is one recording, and a plot a tool pooled
across recordings is refused at the door (`plot["pooled"]`).
"""
from __future__ import annotations

_ADAPTERS = {}

#: Every tool that has an adapter, by module. Imported on first use rather
#: than at start-up: an adapter reaches into its tool, and the tool's heavy
#: imports should be paid by the first figure, not by every boot.
ADAPTER_MODULES = ("xplore",)
_LOADED = False


def _load():
    global _LOADED
    if _LOADED:
        return
    import importlib
    for name in ADAPTER_MODULES:
        importlib.import_module("%s.%s" % (__name__, name))
    _LOADED = True


class FigError(Exception):
    """A sentence for the person, not a traceback."""

    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


class Adapter:
    """The base every tool's adapter extends. Defaults are the honest
    answer for a tool that has not said: nothing to show, nothing known."""

    tool = ""
    name = ""

    def plots(self):
        return []

    def plot(self, pid):
        for p in self.plots():
            if p["id"] == pid:
                return p
        return None

    def prepare(self, spec, ctx):
        raise FigError("%s cannot draw %s yet." % (self.name or self.tool,
                                                    spec.get("plot")))

    def draw(self, fig, rect, spec, prep, ctx, st):
        raise FigError("%s cannot draw %s yet." % (self.name or self.tool,
                                                    spec.get("plot")))

    def lineage(self, spec, prep, ctx):
        return {"phrases": [], "fields": {}}

    def numbers(self, spec, prep):
        return {}

    def scalebar(self, ax, spec, prep, st):
        """Draw scale bars in place of the axes. Only plots that set
        `scalebar: True` are ever asked."""
        return False

    def anatomy(self, spec, prep, ctx):
        """[(y0, y1, name)] in the plot's y units, or []."""
        return []

    def stats(self, spec, prep):
        """[{x, y, text}] marks the tool itself computed, or []."""
        return []

    def describe(self):
        return {"tool": self.tool, "name": self.name,
                "plots": [dict(p) for p in self.plots()]}


def register(adapter):
    if not isinstance(adapter, Adapter) or not adapter.tool:
        raise TypeError("figkit.register takes an Adapter with a tool id")
    _ADAPTERS[adapter.tool] = adapter
    return adapter


def adapter(tool):
    _load()
    got = _ADAPTERS.get(tool)
    if not got:
        raise FigError("Figures from %s are not built yet." % (tool or "that"
                                                                " tool"))
    return got


def adapters():
    _load()
    return [_ADAPTERS[k] for k in sorted(_ADAPTERS)]


def plot_of(spec):
    """(adapter, plot description) for a panel spec, refusing what cannot
    be a panel."""
    ad = adapter(spec.get("tool"))
    pl = ad.plot(spec.get("plot"))
    if not pl:
        raise FigError("%s has no plot called %s." % (ad.name,
                                                      spec.get("plot")))
    if pl.get("pooled"):
        raise FigError(
            "%s pools several recordings, and a figure is one recording. "
            "Make it in %s instead." % (pl.get("name") or pl["id"], ad.name))
    return ad, pl


def catalog():
    from . import layout, style, units
    return {
        "adapters": [a.describe() for a in adapters()],
        "units": units.describe(),
        "profiles": style.describe(),
        "presets": [{"id": p["id"], "name": p["name"], "rows": p["rows"],
                     "cols": p["cols"], "cells": [list(c) for c in p["cells"]]}
                    for p in layout.PRESETS],
        "default_profile": style.DEFAULT,
    }
