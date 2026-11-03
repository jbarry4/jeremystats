"""
figkit/render.py -- a layout of panel specs, drawn.

Three things come out of one set of rules, so they cannot disagree:

    render_frame(layout, ctx)       the page without its panels: title,
                                    footer, and where every panel goes. The
                                    preview lays its tiles over this.
    render_tile(layout, uid, ctx)   one panel, at its own box's size, with
                                    the boxes of everything clickable on it.
    render_page(layout, ctx, fmt)   the whole figure in one matplotlib pass,
                                    for the file.

A tile is the export's panel, cut out: same box (layout.geometry), same
shared scales (resolve), same footer height. That is what lets a word be
changed and one panel redrawn instead of the page.

Matplotlib is used through `matplotlib.figure.Figure` with its own Agg
canvas, never through pyplot's figure list. Requests are served on threads,
and pyplot's "current figure" is one global that two of them would share.
"""
from __future__ import annotations

import hashlib
import io
import json
import threading
from collections import OrderedDict
from datetime import datetime

import numpy as np

from . import FigError, plot_of
from . import layout as L
from . import style, units

# Plots that read one channel axis do not share it with each other -- two
# panels' channel rows are two different lists, and lining them up by row
# number would put CSC 4 of one beside CSC 9 of the other.
NOLINK = {"channel", "index", "count"}

_PREP = OrderedDict()
_PREP_LOCK = threading.Lock()
PREP_MAX = 48


def digest(obj):
    raw = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------
# style for one render
# --------------------------------------------------------------------------
class St:
    """The profile's numbers, the way a draw function wants them."""

    def __init__(self, layout):
        self.pid = layout.get("profile") or style.DEFAULT
        self.prof = style.profile(self.pid)
        self.sizes = dict(self.prof["pt"])
        # compose.py's draw helpers ask for this: thin labels by the axes'
        # own height, so a tile and the page thin them alike.
        self.axes_based = True
        self.line = float(self.prof["line_pt"])
        self.ink = style.INK
        self.muted = style.MUTED
        self.grid = style.GRID
        self.event = style.EVENT
        self.accent = self.prof.get("accent") or style.INK
        self.font = style.family(self.pid)

    # compose.py's _Scale names, so its draw helpers can be handed this.
    @property
    def title_pt(self):
        return self.sizes["title"]

    @property
    def sub_pt(self):
        return self.sizes["sub"]

    @property
    def panel_title_pt(self):
        return self.sizes["panel"]

    @property
    def label_pt(self):
        return self.sizes["label"]

    @property
    def tick_pt(self):
        return self.sizes["tick"]

    @property
    def chan_pt(self):
        return self.sizes["small"]

    @property
    def small_pt(self):
        return self.sizes["small"]

    @property
    def meta_pt(self):
        return self.sizes["meta"]

    @property
    def k(self):
        return 1.0

    @staticmethod
    def pt(points):
        """Points to inches, as compose._Scale.pt."""
        return points / 72.0


def _figure(w_in, h_in, dpi, pid):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    with matplotlib.rc_context(style.rc(pid)):
        fig = Figure(figsize=(w_in, h_in), dpi=dpi)
    FigureCanvasAgg(fig)
    fig.patch.set_facecolor("white")
    return fig


# --------------------------------------------------------------------------
# prepare: every panel's numbers, before anything is drawn
# --------------------------------------------------------------------------
def check_layout(layout):
    """One recording, panels that exist, uids that are unique."""
    rec = layout.get("recording") or {}
    gid = rec.get("gid")
    panels = layout.get("panels") or []
    if not panels:
        raise FigError("There is nothing in this figure yet.")
    seen = set()
    for i, p in enumerate(panels):
        if not p.get("uid"):
            p["uid"] = "p%d" % (i + 1)
        if p["uid"] in seen:
            p["uid"] = "%s_%d" % (p["uid"], i + 1)
        seen.add(p["uid"])
        pg = p.get("gid")
        if gid and pg and pg != gid:
            raise FigError(
                "Panel %d is from a different recording. A figure is one "
                "recording; make a second figure for the other one."
                % (i + 1))
        plot_of(p)
    return layout


def _prepare(spec, layout, ctx):
    ad, pl = plot_of(spec)
    rec = layout.get("recording") or {}
    key = digest({"tool": spec.get("tool"), "plot": spec.get("plot"),
                  "params": spec.get("params") or {},
                  "gid": rec.get("gid"), "path": rec.get("path"),
                  "invert": rec.get("invert"),
                  "c": (spec.get("_resolved") or {}).get("c")})
    with _PREP_LOCK:
        got = _PREP.get(key)
        if got is not None:
            _PREP.move_to_end(key)
            return ad, pl, got
    prep = ad.prepare(spec, ctx)
    with _PREP_LOCK:
        _PREP[key] = prep
        while len(_PREP) > PREP_MAX:
            _PREP.popitem(last=False)
    return ad, pl, prep


def _with_axes(pl, prep):
    """The plot's axes as this panel actually has them.

    Mostly what the adapter declared. A spectrogram of several channels
    stacked has channels down its side rather than frequency, and a band
    power panel in linear units is not in dB, so a prepared panel may say
    so (`prep["axes"]`) and that wins for this panel alone.
    """
    if isinstance(prep, dict) and prep.get("ytick_chars"):
        # The labels' real length, which the box's left pad is cut to.
        pl = dict(pl, ytick_chars=max(float(pl.get("ytick_chars") or 0),
                                      float(prep["ytick_chars"])))
    over = (prep or {}).get("axes") if isinstance(prep, dict) else None
    if not over:
        return pl
    axes = dict(pl.get("axes") or {})
    for k, v in over.items():
        if v is None:
            axes.pop(k, None)
        else:
            axes[k] = dict(axes.get(k) or {}, **v)
    return dict(pl, axes=axes)


def prepare_all(layout, ctx):
    """{uid: {"ad", "pl", "prep", "error"}} -- a panel that fails says why
    and the rest are drawn anyway."""
    out = {}
    for p in layout.get("panels") or []:
        try:
            ad, pl, prep = _prepare(p, layout, ctx)
            out[p["uid"]] = {"ad": ad, "pl": _with_axes(pl, prep),
                             "prep": prep, "error": None}
        except FigError as exc:
            out[p["uid"]] = {"ad": None, "pl": None, "prep": None,
                             "error": str(exc)}
        except Exception as exc:                          # noqa: BLE001
            out[p["uid"]] = {"ad": None, "pl": None, "prep": None,
                             "error": "%s: %s" % (type(exc).__name__, exc)}
    return out


# --------------------------------------------------------------------------
# shared scales
# --------------------------------------------------------------------------
def _axis_decl(pl, axis):
    return ((pl or {}).get("axes") or {}).get(axis)


def _range_in_base(spec, pl, axis):
    """The person's From/To for an axis, converted back to the plot's own
    units, or None."""
    ax = ((spec.get("axes") or {}).get(axis)) or {}
    rng = ax.get("range")
    decl = _axis_decl(pl, axis)
    if not decl or not rng or len(rng) != 2:
        return None
    try:
        lo, hi = float(rng[0]), float(rng[1])
    except (TypeError, ValueError):
        return None
    if not (np.isfinite(lo) and np.isfinite(hi)) or lo == hi:
        return None
    q = decl.get("quantity")
    shown = units.pick(q, decl.get("unit"), ax.get("unit"))
    f = units.factor(q, decl.get("unit"), shown) if q in units.QUANTITIES \
        else 1.0
    return [min(lo, hi) / f, max(lo, hi) / f]


def resolve(layout, prepared):
    """Each panel's limits on each axis, after linking and the person's
    ranges: {uid: {"x": [lo, hi] | None, "y": ..., "c": ...}}.

    A group is every linked panel whose axis carries the same quantity -- and
    for colour, the same plot as well, since a CSD and a voltage raster are
    both "a colour" and are not one scale. A group shares the union of its
    members' extents. A panel's own range beats the group, and "cut" keeps
    it inside the data while "extend" takes it as given.
    """
    groups = {}
    for p in layout.get("panels") or []:
        got = prepared.get(p["uid"]) or {}
        pl, prep = got.get("pl"), got.get("prep")
        if not pl or prep is None:
            continue
        lim = (prep or {}).get("lim") or {}
        link = p.get("link") or {}
        for axis in ("x", "y", "c"):
            decl = _axis_decl(pl, axis)
            if not decl or not lim.get(axis) or link.get(axis) is False:
                continue
            q = decl.get("quantity")
            if q in NOLINK:
                continue
            gk = (axis, q, pl["id"] if axis == "c" else "")
            lo, hi = lim[axis]
            g = groups.setdefault(gk, [lo, hi])
            g[0], g[1] = min(g[0], lo), max(g[1], hi)

    out = {}
    for p in layout.get("panels") or []:
        got = prepared.get(p["uid"]) or {}
        pl, prep = got.get("pl"), got.get("prep")
        res = {"x": None, "y": None, "c": None}
        if pl and prep is not None:
            lim = (prep or {}).get("lim") or {}
            link = p.get("link") or {}
            for axis in ("x", "y", "c"):
                decl = _axis_decl(pl, axis)
                if not decl:
                    continue
                q = decl.get("quantity")
                gk = (axis, q, pl["id"] if axis == "c" else "")
                base = lim.get(axis)
                if link.get(axis) is not False and gk in groups \
                        and q not in NOLINK:
                    base = list(groups[gk])
                want = _range_in_base(p, pl, axis)
                crop = (((p.get("axes") or {}).get(axis)) or {}).get("crop") \
                    or "cut"
                if want:
                    if crop == "cut" and base and axis != "c":
                        lo = max(want[0], min(base))
                        hi = min(want[1], max(base))
                        want = [lo, hi] if hi > lo else want
                    res[axis] = want
                else:
                    res[axis] = list(base) if base else None
        out[p["uid"]] = res
    return out


# --------------------------------------------------------------------------
# the footer: always there, never cut
# --------------------------------------------------------------------------
def _pack(parts, cap):
    from .. import compose
    return compose._pack(parts, cap)


def footer_parts(layout, prepared, ctx, letters):
    """The footer's phrases, in the order a reader needs them: which
    recording, then each panel's lineage, then who made it with what."""
    rec = layout.get("recording") or {}
    head = []
    if rec.get("label"):
        head.append(str(rec["label"]))
    if rec.get("gid"):
        head.append("gid " + str(rec["gid"]))
    for k in ("probe", "fs_text", "duration_text"):
        if rec.get(k):
            head.append(str(rec[k]))
    if rec.get("path"):
        head.append(str(rec["path"]))

    per = []
    for p in L.reading_order(layout.get("panels") or []):
        got = prepared.get(p["uid"]) or {}
        ad, pl, prep = got.get("ad"), got.get("pl"), got.get("prep")
        bits = [letters.get(p["uid"], "?")]
        if ad and pl:
            bits.append("%s, %s" % (ad.name, pl.get("name") or pl["id"]))
            try:
                lin = ad.lineage(p, prep, ctx) or {}
            except Exception as exc:                      # noqa: BLE001
                lin = {"phrases": ["lineage unavailable: %s" % exc]}
            bits.extend(lin.get("phrases") or [])
        else:
            bits.append("failed: %s" % (got.get("error") or "unknown"))
        per.append(bits)

    prov = getattr(ctx, "prov", None) or {}
    who = []
    ver = prov.get("app_version")
    if ver:
        who.append("Jarvis %s%s" % (ver, (" (%s)" % str(prov["commit"])[:8])
                                    if prov.get("commit") else ""))
    if prov.get("user"):
        who.append("made by %s" % prov["user"])
    if prov.get("machine"):
        who.append(str(prov["machine"]))
    who.append((layout.get("made_at") or
                datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")))
    if layout.get("id"):
        who.append("figure %s%s" % (layout["id"],
                                    (" v%s" % layout["v"]) if layout.get("v")
                                    else " (draft)"))
    notes = ((layout.get("footer") or {}).get("notes") or "").strip()
    if notes:
        who.append(notes)
    return head, per, who


def footer_plan(layout, prepared, ctx, letters, width_in, st):
    """The footer's lines, their size, and how tall the band is.

    Shrinks the type a little before adding lines, then lets the lines grow.
    Nothing is dropped and nothing is cut: a figure that cannot say where its
    numbers came from in four lines says it in six.
    """
    head, per, who = footer_parts(layout, prepared, ctx, letters)
    pt = st.sizes["meta"]
    floor = max(4.0, pt * 0.8)
    lines = []

    def cap_at(size):
        return max(28, int((width_in - 0.16) / ((size / 72.0) * 0.56)))

    for _ in range(4):
        cap = cap_at(pt)
        lines = _pack(head, cap)
        for bits in per:
            lines.extend(_pack(["%s  %s" % (bits[0], bits[1])] + bits[2:],
                               cap))
        lines.extend(_pack(who, cap))
        if len(lines) <= 2 + len(per):
            break
        pt = max(floor, pt * 0.9)
    height = (pt / 72.0) * 1.2 * (len(lines) + 0.6) + 0.05
    return {"lines": lines, "pt": pt, "height_in": height}


def _draw_footer(fig, plan, origin, page_h, st):
    """The band, then the lines from its top down. `origin` is where the
    page's bottom-left sits in this figure, in inches."""
    from matplotlib.patches import Rectangle
    fw, fh = fig.get_size_inches()
    ox, oy = origin
    band = plan["height_in"]
    fig.add_artist(Rectangle(((0 - ox) / fw, (0 - oy) / fh), 1.0 + ox / fw,
                             band / fh, transform=fig.transFigure,
                             facecolor=style.FOOT_BG, edgecolor="none",
                             zorder=0))
    step = (plan["pt"] / 72.0) * 1.2
    y = band - step * 0.75
    for i, line in enumerate(plan["lines"]):
        fig.text((0.08 - ox) / fw, (y - oy) / fh, line, fontsize=plan["pt"],
                 color=st.ink if i == 0 else st.muted, va="center",
                 ha="left", family=st.font)
        y -= step


def _draw_header(fig, layout, geo, origin, st):
    fw, fh = fig.get_size_inches()
    ox, oy = origin
    x0, y0, x1, y1 = geo["header"]
    y = y1
    t = (layout.get("title") or "").strip()
    s = (layout.get("subtitle") or "").strip()
    color = st.accent if st.prof.get("header") else st.ink
    if t:
        fig.text((x0 - ox) / fw, (y - oy) / fh, t, fontsize=st.sizes["title"],
                 weight="bold", color=color, va="top", ha="left",
                 family=st.font, gid="fig:title")
        y -= st.sizes["title"] * 1.5 / 72.0
    if s:
        fig.text((x0 - ox) / fw, (y - oy) / fh, s, fontsize=st.sizes["sub"],
                 color=st.muted, va="top", ha="left", family=st.font,
                 gid="fig:subtitle")


# --------------------------------------------------------------------------
# one panel
# --------------------------------------------------------------------------
def _frac(rect, origin, fig):
    fw, fh = fig.get_size_inches()
    x0, y0, x1, y1 = rect
    ox, oy = origin
    return [(x0 - ox) / fw, (y0 - oy) / fh, (x1 - x0) / fw, (y1 - y0) / fh]


def _formatter(f):
    from matplotlib.ticker import FuncFormatter

    def fmt(v, _pos):
        x = v * f
        if abs(x) >= 1e4 or (0 < abs(x) < 1e-3):
            return "%.3g" % x
        s = ("%.4f" % x).rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s.replace("-", "−")
    return FuncFormatter(fmt)


def _apply_axis(ax, which, spec, pl, lims, st):
    """Words, unit and range for one axis of the main axes."""
    decl = _axis_decl(pl, which)
    if not decl:
        return None
    mine = ((spec.get("axes") or {}).get(which)) or {}
    q = decl.get("quantity")
    shown = units.pick(q, decl.get("unit"), mine.get("unit"))
    text = units.axis_text(mine.get("words") or decl.get("words"), q, shown)
    axis = ax.xaxis if which == "x" else ax.yaxis
    if q in units.QUANTITIES and decl.get("unit") is not None \
            and not decl.get("own_ticks"):
        f = units.factor(q, decl.get("unit"), shown)
        if f != 1.0:
            axis.set_major_formatter(_formatter(f))
    if lims and not decl.get("own_limits"):
        (ax.set_xlim if which == "x" else ax.set_ylim)(*lims)
    if decl.get("label", True):
        (ax.set_xlabel if which == "x" else ax.set_ylabel)(
            text, fontsize=st.sizes["label"], color=st.ink, family=st.font)
    return text


def _apply_cbar(cax, spec, pl, st):
    decl = _axis_decl(pl, "c")
    if cax is None or not decl:
        return None
    mine = ((spec.get("axes") or {}).get("c")) or {}
    q = decl.get("quantity")
    shown = units.pick(q, decl.get("unit"), mine.get("unit"))
    if q in units.QUANTITIES:
        f = units.factor(q, decl.get("unit"), shown)
        if f != 1.0:
            cax.yaxis.set_major_formatter(_formatter(f))
    words = (mine.get("words") or "").strip()
    text = units.axis_text(words, q, shown) if words else (shown or
                                                           decl.get("words"))
    cax.set_title(text, fontsize=st.sizes["small"], color=st.muted, pad=2,
                  family=st.font)
    cax.tick_params(labelsize=st.sizes["small"], colors=st.muted,
                    width=st.line * 0.8, length=2)
    for s in cax.spines.values():
        s.set_linewidth(st.line * 0.8)
        s.set_edgecolor(st.grid)
    return text


def _style_axes(ax, st):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_linewidth(st.line)
        ax.spines[side].set_color(st.ink)
    ax.tick_params(labelsize=st.sizes["tick"], colors=st.ink, width=st.line)


def _draw_one(fig, origin, g, spec, entry, ctx, st, res, letter):
    """Draw a panel into its box. Returns the artists the person can click,
    by name, for the hit boxes."""
    arts = {}
    fw, fh = fig.get_size_inches()
    ox, oy = origin
    ad, pl, prep = entry.get("ad"), entry.get("pl"), entry.get("prep")
    title = (spec.get("title") or "").strip()

    if letter and spec.get("labels", {}).get("letter", True) is not False:
        lx, ly = g["letter_at"]
        arts["letter"] = fig.text(
            (lx - ox) / fw, (ly - oy) / fh, letter, fontsize=st.sizes["letter"],
            weight="bold", color=st.ink, va="top", ha="left", family=st.font)
    if title:
        tx, ty = g["title_at"]
        # Beside the letter rather than over it.
        lead = (st.sizes["letter"] * 0.9 / 72.0) if letter else 0.0
        arts["title"] = fig.text(
            (max(tx, g["box"][0] + lead) - ox) / fw, (ty - oy) / fh, title,
            fontsize=st.sizes["panel"], weight="bold", color=st.ink, va="top",
            ha="left", family=st.font)

    if entry.get("error") or not ad:
        ax = fig.add_axes(_frac(g["box"], origin, fig))
        ax.set_axis_off()
        ax.text(0.5, 0.5, "This panel could not be drawn.\n\n"
                + _wrap(entry.get("error") or "", 48),
                ha="center", va="center", fontsize=st.sizes["small"],
                color=st.event, transform=ax.transAxes, family=st.font)
        arts["plot"] = ax
        return arts

    spec_eff = dict(spec)
    spec_eff["_resolved"] = res
    before = list(fig.axes)
    try:
        got = ad.draw(fig, _frac(g["axes"], origin, fig), spec_eff, prep,
                      ctx, st) or {}
    except Exception as exc:                              # noqa: BLE001
        # One panel failing to draw is that panel's problem, said on it;
        # the rest of the figure is still drawn.
        for a in [a for a in fig.axes if a not in before]:
            a.remove()
        entry["error"] = (str(exc) if isinstance(exc, FigError)
                          else "%s: %s" % (type(exc).__name__, exc))
        ax = fig.add_axes(_frac(g["box"], origin, fig))
        ax.set_axis_off()
        ax.text(0.5, 0.5, "This panel could not be drawn.\n\n"
                + _wrap(entry["error"], 48), ha="center", va="center",
                fontsize=st.sizes["small"], color=st.event,
                transform=ax.transAxes, family=st.font)
        arts["plot"] = ax
        return arts
    main = got.get("main")
    new_axes = [a for a in fig.axes if a not in before]
    if main is None and new_axes:
        main = new_axes[0]
    arts["plot"] = main
    if main is None:
        return arts

    styled = got.get("axes")
    for a in ([main] if styled is None else styled):
        if a is not got.get("cbar"):
            _style_axes(a, st)
    arts["x"] = _apply_axis(main, "x", spec, pl, res.get("x"), st) and main
    arts["y"] = _apply_axis(main, "y", spec, pl, res.get("y"), st) and main
    for a in (got.get("axes") or []):
        if a is not main and a is not got.get("cbar"):
            # The other columns of a probe panel follow the main one's
            # units and range; only the main one is labelled.
            _apply_axis(a, "x", spec, dict(pl, axes=dict(
                pl.get("axes") or {}, x=dict(_axis_decl(pl, "x") or {},
                                             label=False))),
                        res.get("x"), st)
    if got.get("cbar") is not None:
        _apply_cbar(got["cbar"], spec, pl, st)
        arts["c"] = got["cbar"]

    labels = spec.get("labels") or {}
    if labels.get("scalebar") and pl.get("scalebar"):
        if ad.scalebar(main, spec_eff, prep, st):
            arts["x"] = arts["y"] = None
    if labels.get("anatomy") and pl.get("anatomy"):
        _draw_anatomy(main, ad.anatomy(spec_eff, prep, ctx) or [], st)
    if labels.get("stats") and pl.get("stats"):
        for m in ad.stats(spec_eff, prep) or []:
            main.text(m["x"], m["y"], m["text"], ha="center", va="bottom",
                      fontsize=st.sizes["label"], color=st.ink, family=st.font,
                      zorder=8)
    return arts


def _draw_anatomy(ax, bands, st):
    """Region names down the right edge of the data, with a thin rule where
    one region gives way to the next."""
    from matplotlib.transforms import blended_transform_factory
    tr = blended_transform_factory(ax.transAxes, ax.transData)
    for i, (y0, y1, name) in enumerate(bands):
        if i:
            ax.axhline(y0, color=st.muted, linewidth=st.line * 0.6,
                       linestyle=(0, (2, 2)), zorder=6)
        ax.text(1.01, (y0 + y1) / 2.0, name, transform=tr, ha="left",
                va="center", fontsize=st.sizes["small"], color=st.muted,
                family=st.font, clip_on=False)


def _wrap(text, width):
    import textwrap
    return "\n".join(textwrap.wrap(str(text), width))


def _hits(fig, arts, dpi):
    """Every clickable thing's box, as fractions of the figure from its top
    left -- the browser's way round."""
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    W, H = fig.canvas.get_width_height()
    out = {}
    for name, art in arts.items():
        if art is None:
            continue
        try:
            if name in ("x", "y"):
                axis = art.xaxis if name == "x" else art.yaxis
                bb = axis.get_tightbbox(rend)
            elif hasattr(art, "get_tightbbox") and name in ("plot", "c"):
                bb = art.get_window_extent(rend)
            else:
                bb = art.get_window_extent(rend)
        except Exception:                                 # noqa: BLE001
            continue
        if bb is None or bb.width <= 0 or bb.height <= 0:
            continue
        out[name] = [round(bb.x0 / W, 4), round(1 - bb.y1 / H, 4),
                     round(bb.x1 / W, 4), round(1 - bb.y0 / H, 4)]
    return out


def _png(fig, dpi):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor="white")
    return buf.getvalue()


def _plots_by_uid(layout, prepared):
    return {p["uid"]: (prepared.get(p["uid"]) or {}).get("pl")
            for p in layout.get("panels") or []}


def plan(layout, ctx):
    """Everything a render needs worked out first: prepared panels, shared
    scales, letters, footer, geometry."""
    check_layout(layout)
    st = St(layout)
    prepared = prepare_all(layout, ctx)
    res = resolve(layout, prepared)
    # Colour shared by a group is a re-render for image panels, so the
    # resolved range is handed back to prepare before drawing.
    for p in layout.get("panels") or []:
        entry = prepared.get(p["uid"]) or {}
        if entry.get("ad") and (res.get(p["uid"]) or {}).get("c"):
            want = res[p["uid"]]["c"]
            have = (entry.get("prep") or {}).get("clim_used")
            if not _same(have, want) and getattr(entry["ad"], "recolour",
                                                 False):
                spec = dict(p, _resolved={"c": want})
                try:
                    ad, pl, prep = _prepare(spec, layout, ctx)
                    entry["prep"] = prep
                    entry["pl"] = _with_axes(pl, prep)
                except Exception as exc:                  # noqa: BLE001
                    entry["error"] = str(exc)
    letters = L.letters(layout)
    w, h = L.page_size(layout)
    foot = footer_plan(layout, prepared, ctx, letters, w, st)
    geo = L.geometry(layout, foot["height_in"],
                     _plots_by_uid(layout, prepared))
    return {"st": st, "prepared": prepared, "res": res, "letters": letters,
            "foot": foot, "geo": geo}


def _same(a, b, tol=1e-6):
    if not a or not b or len(a) != 2 or len(b) != 2:
        return False
    span = max(abs(float(b[1]) - float(b[0])), 1e-12)
    return all(abs(float(x) - float(y)) <= tol * span + 1e-12
               for x, y in zip(a, b))


def render_frame(layout, ctx, dpi=110):
    """The page without its panels, and where they go."""
    P = plan(layout, ctx)
    w, h = P["geo"]["page"]
    fig = _figure(w, h, dpi, P["st"].pid)
    _draw_header(fig, layout, P["geo"], (0, 0), P["st"])
    _draw_footer(fig, P["foot"], (0, 0), h, P["st"])
    arts = {}
    for t in fig.texts:
        if t.get_gid() == "fig:title":
            arts["fig_title"] = t
        elif t.get_gid() == "fig:subtitle":
            arts["fig_subtitle"] = t
    hits = _hits(fig, arts, dpi)
    png = _png(fig, dpi)
    boxes, sigs, about = {}, {}, {}
    page_keys = {k: layout.get(k) for k in ("profile", "width", "height_mm",
                                             "rows", "cols", "gap_mm")}
    for g in P["geo"]["panels"]:
        x0, y0, x1, y1 = g["box"]
        uid = g["uid"]
        boxes[uid] = [x0 / w, 1 - y1 / h, x1 / w, 1 - y0 / h]
        spec = next(p for p in layout["panels"] if p["uid"] == uid)
        entry = P["prepared"].get(uid) or {}
        # Everything a tile's picture depends on. The same sig is the same
        # picture, so the page asks again only for tiles whose sig moved.
        sigs[uid] = digest({"spec": {k: v for k, v in spec.items()
                                     if not str(k).startswith("_")},
                            "res": P["res"].get(uid), "box": g["box"],
                            "axes": g["axes"],
                            "letter": P["letters"].get(uid),
                            "page": page_keys, "err": entry.get("error")})
        about[uid] = _about(spec, entry, ctx)
    return {"image": png, "page_in": [w, h], "boxes": boxes, "hits": hits,
            "sigs": sigs, "about": about,
            "letters": P["letters"], "footer": P["foot"]["lines"],
            "problems": _problems(P)}


def _about(spec, entry, ctx):
    """One panel in plain words, for the builder's side column: what it is,
    and the lineage phrases the footer prints for it."""
    ad, pl = entry.get("ad"), entry.get("pl")
    if not ad or not pl:
        return {"error": entry.get("error")}
    try:
        lin = ad.lineage(spec, entry.get("prep"), ctx) or {}
    except Exception as exc:                              # noqa: BLE001
        lin = {"phrases": ["lineage unavailable: %s" % exc]}
    from . import units as U
    axes = {}
    for k, decl in (pl.get("axes") or {}).items():
        q = decl.get("quantity")
        axes[k] = {"quantity": q, "unit": U.norm_unit(decl.get("unit")),
                   "words": decl.get("words"),
                   "units": U.choices(q, decl.get("unit")),
                   "convertible": q in U.QUANTITIES,
                   "linkable": q not in NOLINK,
                   "lim": ((entry.get("prep") or {}).get("lim") or {}).get(k)}
    return {"tool": ad.tool, "tool_name": ad.name, "plot": pl["id"],
            "plot_name": pl.get("name"), "axes": axes,
            "scalebar": bool(pl.get("scalebar")),
            "anatomy": bool(pl.get("anatomy")),
            "stats": bool(pl.get("stats")),
            "phrases": lin.get("phrases") or [],
            "fields": lin.get("fields") or {}}


def render_tile(layout, uid, ctx, dpi=110):
    """One panel, alone, at its own box."""
    P = plan(layout, ctx)
    g = next((x for x in P["geo"]["panels"] if x["uid"] == uid), None)
    spec = next((p for p in layout["panels"] if p["uid"] == uid), None)
    if not g or not spec:
        raise FigError("No panel %s in this figure." % uid)
    x0, y0, x1, y1 = g["box"]
    fig = _figure(x1 - x0, y1 - y0, dpi, P["st"].pid)
    import matplotlib
    with matplotlib.rc_context(style.rc(P["st"].pid)):
        arts = _draw_one(fig, (x0, y0), g, spec, P["prepared"][uid], ctx,
                         P["st"], P["res"].get(uid) or {},
                         P["letters"].get(uid))
        hits = _hits(fig, arts, dpi)
        png = _png(fig, dpi)
    entry = P["prepared"][uid]
    return {"image": png, "hits": hits, "uid": uid,
            "error": entry.get("error"),
            "resolved": P["res"].get(uid),
            "letter": P["letters"].get(uid)}


def render_page(layout, ctx, fmt="png", dpi=None):
    """The whole figure, one pass, for the file. Returns the bytes, the
    problems, every panel's plotted numbers and every panel's lineage."""
    from .. import compose
    fmt = (fmt or "png").lower()
    if fmt not in compose.MIME:
        raise FigError("A figure is saved as png, svg or pdf, not %s." % fmt)
    P = plan(layout, ctx)
    st = P["st"]
    dpi = int(dpi or st.prof["dpi"])
    w, h = P["geo"]["page"]
    import matplotlib
    with matplotlib.rc_context(style.rc(st.pid)):
        fig = _figure(w, h, dpi, st.pid)
        _draw_header(fig, layout, P["geo"], (0, 0), st)
        for g in P["geo"]["panels"]:
            spec = next(p for p in layout["panels"] if p["uid"] == g["uid"])
            _draw_one(fig, (0, 0), g, spec, P["prepared"][g["uid"]], ctx, st,
                      P["res"].get(g["uid"]) or {}, P["letters"].get(g["uid"]))
        _draw_footer(fig, P["foot"], (0, 0), h, st)
        buf = io.BytesIO()
        kw = {"format": fmt, "facecolor": "white",
              "metadata": _file_meta(layout, fmt, ctx)}
        if fmt == "png":
            kw["dpi"] = dpi
        fig.savefig(buf, **kw)
    return buf.getvalue(), _problems(P), P


def numbers(layout, P):
    """{"<uid>.<name>": array} -- what every panel plotted, for the
    version's data file."""
    out = {}
    for p in layout.get("panels") or []:
        entry = P["prepared"].get(p["uid"]) or {}
        if not entry.get("ad"):
            continue
        try:
            got = entry["ad"].numbers(p, entry["prep"]) or {}
        except Exception:                                 # noqa: BLE001
            got = {}
        for k, v in got.items():
            try:
                arr = np.asarray(v)
                if arr.dtype.kind == "f":
                    arr = arr.astype(np.float32)
                out["%s.%s" % (p["uid"], k)] = arr
            except Exception:                             # noqa: BLE001
                continue
    return out


def lineage(layout, P, ctx):
    out = {}
    for p in layout.get("panels") or []:
        entry = P["prepared"].get(p["uid"]) or {}
        if not entry.get("ad"):
            out[p["uid"]] = {"error": entry.get("error")}
            continue
        try:
            out[p["uid"]] = entry["ad"].lineage(p, entry["prep"], ctx) or {}
        except Exception as exc:                          # noqa: BLE001
            out[p["uid"]] = {"error": str(exc)}
    return out


def _file_meta(layout, fmt, ctx):
    """What the file says about itself, where the format has a place."""
    rec = layout.get("recording") or {}
    title = layout.get("title") or "figure"
    prov = getattr(ctx, "prov", None) or {}
    desc = "Jarvis figure %s%s of %s" % (
        layout.get("id") or "", (" v%s" % layout["v"]) if layout.get("v")
        else "", rec.get("label") or rec.get("gid") or "a recording")
    if fmt == "png":
        return {"Title": title, "Description": desc,
                "Author": prov.get("user") or "",
                "Software": "Jarvis %s" % (prov.get("app_version") or "")}
    if fmt == "pdf":
        return {"Title": title, "Subject": desc,
                "Author": prov.get("user") or "",
                "Creator": "Jarvis %s" % (prov.get("app_version") or "")}
    if fmt == "svg":
        return {"Title": title, "Description": desc,
                "Creator": "Jarvis %s" % (prov.get("app_version") or "")}
    return None


def _problems(P):
    out = []
    for uid, e in P["prepared"].items():
        if e.get("error"):
            out.append("Panel %s: %s" % (P["letters"].get(uid, uid),
                                         e["error"]))
    return out
