"""
storyboard.py -- Render a storyboard deck to PDF or PNG.

A deck is a list of slides; a slide is a list of items placed on a 16:9 canvas
in fractional coordinates (0-1), so the same deck renders correctly at any
output size. Item kinds:

    result     an image or PDF page from the Results catalog
    image      an uploaded image, as a data URI
    text       a text box, with size/weight/color/alignment
    shape      rectangle, ellipse, line or arrow
    ink        freehand strokes, as fractional polylines
    highlight  a translucent rectangle over whatever is beneath

Notes attached to a slide are rendered under it, so a printed deck carries the
commentary with the figure rather than losing it.

Everything is drawn with matplotlib. PDF comes out as one page per slide with
real vectors for text and shapes; embedded images stay images.
"""
from __future__ import annotations

import base64
import io
import os
import re
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Ellipse, FancyArrow, Rectangle
from matplotlib.transforms import Affine2D

UVM_GREEN = "#154734"
UVM_GOLD = "#FFB81C"
INK = "#12211b"
MUTED = "#5f7168"
PAPER = "#ffffff"

SLIDE_W, SLIDE_H = 13.333, 7.5          # 16:9 at 96 dpi-ish, in inches
NOTES_H = 1.9                           # extra page height when notes are shown


class DeckError(Exception):
    pass


def _color_of(item, fallback):
    """Decks saved before the spelling was made consistent used "colour"."""
    return item.get("color") or item.get("colour") or fallback


def render_deck(deck, results, fmt="pdf", dpi=200):
    """Render every slide. Returns (bytes, mimetype, filename)."""
    fmt = (fmt or "pdf").lower()
    slides = deck.get("slides") or []
    if not slides:
        raise DeckError("This deck has no slides.")

    title = deck.get("title") or "storyboard"
    safe = re.sub(r"[^\w \-.]+", "_", title).strip() or "storyboard"

    if fmt == "pdf":
        buf = io.BytesIO()
        with PdfPages(buf) as pdf:
            for i, slide in enumerate(slides):
                fig = _render_slide(slide, deck, results, i, len(slides))
                pdf.savefig(fig, facecolor=PAPER)
                plt.close(fig)
        return buf.getvalue(), "application/pdf", safe + ".pdf"

    if fmt == "png":
        # A single tall sheet: one slide per row, so it can be pasted anywhere.
        buf = io.BytesIO()
        fig = _render_contact_sheet(slides, deck, results)
        fig.savefig(buf, format="png", dpi=dpi, facecolor=PAPER,
                    bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue(), "image/png", safe + ".png"

    raise DeckError("Unsupported deck format '%s'. Use pdf or png." % fmt)


# --------------------------------------------------------------------------
def _render_slide(slide, deck, results, index, total):
    notes = (slide.get("notes") or "").strip()
    show_notes = bool(notes) and slide.get("show_notes", True)
    h = SLIDE_H + (NOTES_H if show_notes else 0.0)

    fig = plt.figure(figsize=(SLIDE_W, h), dpi=110)
    fig.patch.set_facecolor(PAPER)

    # The slide canvas occupies the top; notes sit beneath it.
    top = 1.0 - 0.0
    canvas_frac = SLIDE_H / h
    ax = fig.add_axes([0, top - canvas_frac, 1, canvas_frac])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_axis_off()
    ax.set_facecolor(slide.get("background") or PAPER)
    if slide.get("background"):
        ax.add_patch(Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                               facecolor=slide["background"], zorder=0))

    heading = (slide.get("title") or "").strip()
    if heading:
        ax.text(0.035, 0.955, heading, fontsize=20, weight="bold",
                color=UVM_GREEN, va="top", ha="left", zorder=5)

    for item in (slide.get("items") or []):
        try:
            _draw_item(ax, item, results)
        except Exception as exc:
            _draw_item_error(ax, item, str(exc))

    if show_notes:
        nax = fig.add_axes([0, 0, 1, NOTES_H / h])
        nax.set_axis_off()
        nax.add_patch(Rectangle((0, 0), 1, 1, transform=nax.transAxes,
                                facecolor="#f4f7f5", edgecolor="none"))
        nax.add_patch(Rectangle((0, 0.97), 1, 0.03, transform=nax.transAxes,
                                facecolor=UVM_GOLD, edgecolor="none"))
        wrapped = "\n".join(textwrap.wrap(notes, 165)[:8])
        nax.text(0.035, 0.80, "Notes", fontsize=9, weight="bold", color=UVM_GREEN,
                 va="top", ha="left")
        nax.text(0.035, 0.62, wrapped, fontsize=9.5, color=INK,
                 va="top", ha="left", linespacing=1.5)

    # Footer: deck title and slide number, so a printed page stands alone.
    fig.text(0.035, 0.012 if not show_notes else 0.012,
             (deck.get("title") or ""), fontsize=7.5, color=MUTED,
             va="bottom", ha="left")
    fig.text(0.965, 0.012, "%d / %d" % (index + 1, total), fontsize=7.5,
             color=MUTED, va="bottom", ha="right")
    return fig


def _render_contact_sheet(slides, deck, results):
    n = len(slides)
    fig = plt.figure(figsize=(SLIDE_W, SLIDE_H * n), dpi=100)
    fig.patch.set_facecolor(PAPER)
    for i, slide in enumerate(slides):
        ax = fig.add_axes([0, 1 - (i + 1) / n, 1, 1 / n])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_axis_off()
        heading = (slide.get("title") or "").strip()
        if heading:
            ax.text(0.035, 0.95, heading, fontsize=15, weight="bold",
                    color=UVM_GREEN, va="top", ha="left")
        for item in (slide.get("items") or []):
            try:
                _draw_item(ax, item, results)
            except Exception as exc:
                _draw_item_error(ax, item, str(exc))
        ax.add_patch(Rectangle((0, 0), 1, 1, transform=ax.transAxes, fill=False,
                               edgecolor="#dde7e2", linewidth=0.8))
    return fig


# --------------------------------------------------------------------------
def _box(item):
    """Item geometry in axes fractions, with y measured from the bottom."""
    x = float(item.get("x", 0.1))
    y = float(item.get("y", 0.1))
    w = float(item.get("w", 0.4))
    h = float(item.get("h", 0.3))
    # The editor works top-down (like every layout tool); matplotlib is
    # bottom-up, so flip once here rather than everywhere below.
    return x, 1.0 - y - h, w, h


def _ends(item):
    """A line or arrow's two endpoints, as fractions of its own box.

    The editor stores them because a bounding box has no direction: without
    them every line came out running bottom-left to top-right no matter which
    way it was drawn. Items saved before that default to the old diagonal so
    old decks render the way they were saved.
    """
    a = item.get("a") or [0.0, 1.0]
    b = item.get("b") or [1.0, 0.0]
    return (float(a[0]), float(a[1]), float(b[0]), float(b[1]))


def _rotation(ax, item):
    """The transform for an item's `rot`, or None if it is not rotated.

    Rotation happens about the item's own center, in the top-down coordinates
    the editor uses -- so the sign is flipped, matplotlib measuring angles
    counter-clockwise from a bottom-up origin.
    """
    rot = float(item.get("rot") or 0.0)
    if not rot:
        return None
    x, y, w, h = _box(item)
    return (Affine2D().rotate_deg_around(x + w / 2.0, y + h / 2.0, -rot)
            + ax.transData)


def _spin(ax, item, *artists):
    """Apply the item's rotation to whatever was just drawn."""
    tr = _rotation(ax, item)
    if tr is None:
        return
    for art in artists:
        if art is not None:
            art.set_transform(tr)


def _draw_item(ax, item, results):
    kind = item.get("type")
    if kind == "result":
        _draw_result(ax, item, results)
    elif kind == "image":
        _draw_data_image(ax, item)
    elif kind == "text":
        _draw_text(ax, item)
    elif kind in ("shape", "highlight"):
        _draw_shape(ax, item)
    elif kind == "ink":
        _draw_ink(ax, item)


def _draw_result(ax, item, results):
    # resolve(), not get(): a deck built on another machine carries ids that
    # were derived from that machine's absolute paths, and the file it means
    # is sitting right here under the same name.
    rec = None
    if results:
        rec = (results.resolve(item) if hasattr(results, "resolve")
               else results.get(item.get("result_id", "")))
    if not rec:
        raise DeckError("result no longer in the catalog")
    img = _load_image(rec["path"])
    x, y, w, h = _box(item)
    # Preserve aspect: a squashed figure is worse than a smaller one.
    ih, iw = img.shape[0], img.shape[1]
    if iw and ih:
        target = w / h
        native = iw / ih
        if native > target:
            new_h = w / native
            y += (h - new_h) / 2
            h = new_h
        else:
            new_w = h * native
            x += (w - new_w) / 2
            w = new_w
    im = ax.imshow(img, extent=(x, x + w, y, y + h), aspect="auto",
                   zorder=int(item.get("z", 1)))
    # A rotated image needs its clip box rotated with it, or matplotlib keeps
    # clipping to the upright rectangle and shears off the corners.
    _spin(ax, item, im)
    if item.get("rot"):
        im.set_clip_on(False)
    cap = (item.get("caption") or "").strip()
    if cap:
        art = ax.text(x + w / 2, y - 0.012, cap, fontsize=8.5, color=MUTED,
                      ha="center", va="top", zorder=6)
        rot = float(item.get("rot") or 0.0)
        if rot:
            art.set_rotation(-rot)
            art.set_rotation_mode("anchor")
            _spin(ax, item, art)


def _draw_data_image(ax, item):
    src = item.get("src") or ""
    if not src.startswith("data:"):
        raise DeckError("image is not embedded")
    raw = base64.b64decode(src.split(",", 1)[1])
    from matplotlib.image import imread
    img = imread(io.BytesIO(raw), format="png")
    x, y, w, h = _box(item)
    im = ax.imshow(img, extent=(x, x + w, y, y + h), aspect="auto",
                   zorder=int(item.get("z", 1)))
    _spin(ax, item, im)
    if item.get("rot"):
        im.set_clip_on(False)


def _draw_text(ax, item):
    x, y, w, h = _box(item)
    align = item.get("align") or "left"
    tx = x if align == "left" else (x + w / 2 if align == "center" else x + w)
    size = float(item.get("size", 14))
    # Wrap to the box width, worked out in real units: the box is w * SLIDE_W
    # inches wide, and a character averages about 0.55 em, so
    #   chars = box_inches / (0.55 * size/72)
    # Guessing at a ratio instead is how "recording" ended up broken mid-word.
    char_in = 0.55 * max(6.0, size) / 72.0
    chars = max(6, int((w * SLIDE_W) / char_in))
    raw = item.get("text") or ""
    # Honour the author's own line breaks, wrapping each paragraph separately.
    lines = []
    for para in raw.split("\n"):
        lines.extend(textwrap.wrap(para, chars) or [""])
    body = "\n".join(lines)
    art = ax.text(tx, y + h, body, fontsize=size,
                  color=_color_of(item, INK),
                  weight="bold" if item.get("bold") else "normal",
                  style="italic" if item.get("italic") else "normal",
                  ha=align, va="top", linespacing=1.4,
                  zorder=int(item.get("z", 4)))
    # Text rotates about the box center like everything else, so a rotated
    # caption stays where it was put rather than swinging off its anchor.
    rot = float(item.get("rot") or 0.0)
    if rot:
        art.set_rotation(-rot)
        art.set_rotation_mode("anchor")
        _spin(ax, item, art)


def _draw_shape(ax, item):
    x, y, w, h = _box(item)
    shape = item.get("shape") or ("rect" if item.get("type") == "shape" else "rect")
    color = _color_of(item, UVM_GOLD)
    alpha = float(item.get("alpha", 0.3 if item.get("type") == "highlight" else 1.0))
    lw = float(item.get("width", 2))
    filled = bool(item.get("filled", item.get("type") == "highlight"))
    z = int(item.get("z", 3))

    if shape == "ellipse":
        patch = Ellipse((x + w / 2, y + h / 2), w, h,
                        facecolor=color if filled else "none",
                        edgecolor="none" if filled else color,
                        alpha=alpha, linewidth=lw, zorder=z)
        ax.add_patch(patch)
        _spin(ax, item, patch)
    elif shape in ("line", "arrow"):
        ax_, ay_, bx_, by_ = _ends(item)
        # The endpoints are top-down fractions of the box; _box already
        # flipped the box itself, so the y fractions flip with it.
        x0, y0 = x + ax_ * w, y + h - ay_ * h
        x1, y1 = x + bx_ * w, y + h - by_ * h
        if shape == "line":
            (art,) = ax.plot([x0, x1], [y0, y1], color=color, linewidth=lw,
                             alpha=alpha, zorder=z, solid_capstyle="round")
            _spin(ax, item, art)
        else:
            dx, dy = x1 - x0, y1 - y0
            # A zero-length arrow makes FancyArrow raise; a dot is the honest
            # rendering of one.
            if abs(dx) < 1e-6 and abs(dy) < 1e-6:
                (art,) = ax.plot([x0], [y0], marker="o", color=color,
                                 markersize=lw * 2, alpha=alpha, zorder=z)
                _spin(ax, item, art)
            else:
                head_len = min(0.024, (dx ** 2 + dy ** 2) ** 0.5 * 0.42)
                patch = FancyArrow(
                    x0, y0, dx, dy, width=0.0009 * lw,
                    head_width=0.016 * max(1, lw / 2),
                    head_length=head_len, color=color, alpha=alpha,
                    length_includes_head=True, zorder=z)
                ax.add_patch(patch)
                _spin(ax, item, patch)
    else:
        patch = Rectangle((x, y), w, h,
                          facecolor=color if filled else "none",
                          edgecolor="none" if filled else color,
                          alpha=alpha, linewidth=lw, zorder=z)
        ax.add_patch(patch)
        _spin(ax, item, patch)


def _draw_ink(ax, item):
    color = _color_of(item, "#c0392b")
    lw = float(item.get("width", 2))
    for stroke in (item.get("strokes") or []):
        if len(stroke) < 2:
            continue
        xs = [float(p[0]) for p in stroke]
        ys = [1.0 - float(p[1]) for p in stroke]
        (art,) = ax.plot(
            xs, ys, color=color, linewidth=lw,
            alpha=float(item.get("alpha", 1)),
            solid_capstyle="round", solid_joinstyle="round",
            zorder=int(item.get("z", 5)))
        _spin(ax, item, art)


def _draw_item_error(ax, item, msg):
    x, y, w, h = _box(item)
    ax.add_patch(Rectangle((x, y), w, h, facecolor="#fdf3f2",
                           edgecolor="#c0392b", linewidth=1,
                           linestyle="--", zorder=8))
    ax.text(x + w / 2, y + h / 2, "missing\n" + msg[:60], fontsize=8,
            color="#c0392b", ha="center", va="center", zorder=9)


_IMG_CACHE = {}


def _load_image(path):
    """Load an image or the first page of a PDF, cached by path+mtime."""
    key = (path, os.path.getmtime(path))
    if key in _IMG_CACHE:
        return _IMG_CACHE[key]

    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        img = _pdf_first_page(path)
    else:
        from matplotlib.image import imread
        img = imread(path)

    if len(_IMG_CACHE) > 24:
        _IMG_CACHE.clear()
    _IMG_CACHE[key] = img
    return img


def _pdf_first_page(path):
    """Rasterise a PDF's first page, if a renderer is available."""
    try:
        import fitz                                   # PyMuPDF, if installed
        doc = fitz.open(path)
        pix = doc[0].get_pixmap(dpi=150)
        import numpy as np
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n)
        return arr[:, :, :3] / 255.0
    except Exception:
        pass
    raise DeckError(
        "PDF pages need PyMuPDF to appear on a slide (pip install pymupdf). "
        "Export that figure as PNG instead, or add it as a link.")
