"""Page engine for the PTEN behavioral menu: letter pages composed in PyMuPDF.

Each figure page: kicker, the question, "Results show", lettered panels (vector crops of the report's own figures,
their vague panel titles cut away) under headings that state the finding, then How it was measured / What it shows /
Reading / Caveats either in a right-hand column ("side") or in two columns under the panels ("below").
"""
import html
import os
import re

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, "svgpdf")
PAGE_W, PAGE_H = 612.0, 792.0
ML, MR, MT, MB = 40.0, 40.0, 34.0, 38.0
ARCH = pymupdf.Archive(r"C:\Windows\Fonts")
BASE_CSS = """
@font-face {font-family: A; src: url(arial.ttf);}
@font-face {font-family: A; src: url(arialbd.ttf); font-weight: bold;}
@font-face {font-family: A; src: url(ariali.ttf); font-style: italic;}
@font-face {font-family: A; src: url(arialbi.ttf); font-weight: bold; font-style: italic;}
* {font-family: A;}
p, div {margin: 0; padding: 0;}
"""
INK = "#161b26"
BODY = "#2c313c"
MUTED = "#5b6170"
ACCENT = "#b23a78"
KICKER = "PTEN BEHAVIOR MENU"
FOOTER = ("PTEN behavior menu \u00b7 the Pten KO mosaicism behavior report (version 3, 2026-11-24) recast \u00b7 "
          "exploratory: one number per mouse, P values uncorrected \u00b7 2026-11-27")

_scratch = pymupdf.open()
_scratch_page = _scratch.new_page(width=PAGE_W, height=4000)
_src = {}


NB = " "
_RULES = [
    (re.compile(r"\b(P|r|n|AUC|g)\s(?=[−+<>=≥≤\d(])"), r"\1" + NB),
    (re.compile(r"(ρ|χ²)\s(?=[−+\d])"), r"\1" + NB),
    (re.compile(r"(\d)\s(?=(cm/s|cm|s|m|pA|mV|min|minutes|sessions|points|a\.u\.)\b)"), r"\1" + NB),
    (re.compile(r"(\d)\s(?=%)"), r"\1" + NB),
    (re.compile(r"\s(?=±)"), NB),
    (re.compile(r"(?<=±)\s"), NB),
]


def nb(s):
    """Keep statistics and units with their numbers, and the last two words of a text together (no widows)."""
    for rx, rep in _RULES:
        s = rx.sub(rep, s)
    i = s.rfind(" ")
    if i > 0 and len(s) - i < 18:
        s = s[:i] + NB + s[i + 1:]
    return s


def esc(s):
    return html.escape(nb(s), quote=False)


def src(fid):
    if fid not in _src:
        _src[fid] = pymupdf.open(os.path.join(SVG, fid + ".pdf"))
    return _src[fid]


def measure(markup, width, css=""):
    """Height of an HTML snippet laid out at this width, without scaling."""
    rect = pymupdf.Rect(0, 0, width, 3900)
    pg = _scratch.new_page(width=PAGE_W, height=4000)
    spare, scale = pg.insert_htmlbox(rect, markup, css=BASE_CSS + css, archive=ARCH, scale_low=1)
    _scratch.delete_page(-1)
    if spare < 0:
        raise RuntimeError("text too long to measure")
    return 3900 - spare


def draw(page, x, y, width, markup, css=""):
    h = measure(markup, width, css)
    rect = pymupdf.Rect(x, y, x + width, y + h + 2)
    spare, scale = page.insert_htmlbox(rect, markup, css=BASE_CSS + css, archive=ARCH, scale_low=1)
    if spare < 0 or scale < 1:
        raise RuntimeError("text did not fit: %r" % markup[:80])
    return h


# --------------------------------------------------------------------------------------------- pieces
def header(page, num, kicker, question, results):
    y = MT
    w = PAGE_W - ML - MR
    k = '<div style="font-size:8.5pt;font-weight:bold;color:%s">%s \u00b7 %s \u00b7 %s</div>' % (
        ACCENT, KICKER, num, esc(kicker.upper()))
    y += draw(page, ML, y, w, k) + 4
    q = '<div style="font-size:10pt;font-style:italic;color:%s">The question: \u201c%s\u201d</div>' % (MUTED, esc(question))
    y += draw(page, ML, y, w, q) + 5
    r = '<div style="font-size:13.2pt;font-weight:bold;color:%s;line-height:1.2">Results show: %s</div>' % (INK, esc(results))
    y += draw(page, ML, y, w, r) + 10
    return y


def footer(page, number):
    css = "div {font-size:6.5pt;color:#8a8f99;}"
    draw(page, ML, PAGE_H - MB + 12, PAGE_W - ML - MR - 30, '<div>%s</div>' % esc(FOOTER), css)
    draw(page, PAGE_W - MR - 24, PAGE_H - MB + 12, 24, '<div style="text-align:right">%d</div>' % number, css)


BLOCKS = (("How it was measured", "how"), ("What it shows", "what"), ("Reading", "reading"), ("Caveats", "caveats"))


def blocks_html(spec, keys, size=7.6):
    parts = []
    for title, key in BLOCKS:
        if key not in keys or not spec.get(key):
            continue
        parts.append('<p style="font-size:9pt;font-weight:bold;color:%s;margin-bottom:2pt">%s</p>' % (INK, title))
        parts.append('<p style="font-size:%.1fpt;color:%s;line-height:1.3;margin-bottom:8pt">%s</p>' % (size, BODY, esc(spec[key])))
    return "".join(parts)


def heading_html(text):
    return '<div style="font-size:8.6pt;font-weight:bold;color:%s;line-height:1.2">%s</div>' % (INK, esc(text))


def letter_html(letter):
    return '<div style="font-size:9.5pt;font-weight:bold;color:%s">%s</div>' % (INK, esc(letter))


# --------------------------------------------------------------------------------------------- panels
def lwid(letter):
    return 12.0 if len(letter) == 1 else 26.0


def plan_rows(spec, x0, width, k):
    """Positions of every panel at shrink k: list of (row height, [(letter, x, col width), ...])."""
    out = []
    for row in spec["rows"]:
        total = sum(c["w"] for c in row) * width * k
        x = x0 + (width - total) / 2.0
        cols = []
        row_h = 0.0
        for c in row:
            cw = c["w"] * width * k
            inner = cw - (10 if c is not row[-1] else 0)
            hsum = 0.0
            items = []
            for letter in c["p"]:
                p = spec["panels"][letter]
                cx0, cy0, cx1, cy1 = p["clip"]
                img_h = inner * (cy1 - cy0) / (cx1 - cx0)
                head_h = measure(heading_html(p["h"]), inner - lwid(letter)) if p.get("h") else 0.0
                items.append((letter, head_h, img_h))
                hsum += head_h + (3 if head_h else 0) + img_h + 10
            cols.append((x, inner, items))
            row_h = max(row_h, hsum)
            x += cw
        out.append((row_h, cols))
    return out


def legend_size(spec, width, k):
    if not spec.get("legend"):
        return 0.0, 0.0
    fid, clip = spec["legend"]
    cw, ch = clip[2] - clip[0], clip[3] - clip[1]
    s = min(spec.get("legend_scale", 0.72), width / cw)
    return cw * s, ch * s


def draw_legend(page, spec, y):
    """The figure's own key, across the full page width; returns the height used."""
    lw, lh = legend_size(spec, PAGE_W - ML - MR, 1.0)
    if not lh:
        return 0.0
    fid, clip = spec["legend"]
    page.show_pdf_page(pymupdf.Rect(ML, y, ML + lw, y + lh), src(fid), 0, clip=pymupdf.Rect(clip))
    return lh + 8


def layout_panels(page, spec, x0, y0, width, avail):
    k = spec.get("scale", 1.0)
    for _ in range(8):
        rows = plan_rows(spec, x0, width, k)
        need = sum(r[0] for r in rows)
        if need <= avail + 0.5:
            break
        k *= max(0.5, avail / need) * 0.995
    y = y0
    for row_h, cols in rows:
        for x, inner, items in cols:
            yy = y
            for letter, head_h, img_h in items:
                p = spec["panels"][letter]
                if head_h:
                    draw(page, x, yy, lwid(letter), letter_html(letter))
                    draw(page, x + lwid(letter), yy + 0.5, inner - lwid(letter), heading_html(p["h"]))
                    yy += head_h + 3
                page.show_pdf_page(pymupdf.Rect(x, yy, x + inner, yy + img_h), src(p["src"]), 0,
                                   clip=pymupdf.Rect(p["clip"]))
                # cover leftovers of the figure's own panel letters or titles with its background color
                cx0, cy0, cx1, cy1 = p["clip"]
                f = inner / (cx1 - cx0)
                for mx0, my0, mx1, my1 in p.get("mask", ()):
                    r = pymupdf.Rect(x + (mx0 - cx0) * f, yy + (my0 - cy0) * f, x + (mx1 - cx0) * f, yy + (my1 - cy0) * f)
                    page.draw_rect(r & pymupdf.Rect(x, yy, x + inner, yy + img_h), color=None,
                                   fill=(252 / 255.0, 252 / 255.0, 251 / 255.0), width=0)
                yy += img_h + 10
        y += row_h
    return y, k


def figure_page(doc, spec, number):
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    top = header(page, spec["num"], spec["kicker"], spec["question"], spec["results"])
    top += draw_legend(page, spec, top)
    bottom = PAGE_H - MB - 4
    keys = [k for _, k in BLOCKS]
    if spec["mode"] == "side":
        tx, tw = 424.0, PAGE_W - MR - 424.0
        size = 7.6
        while True:
            th = measure(blocks_html(spec, keys, size), tw)
            if th <= bottom - top or size < 6.6:
                break
            size -= 0.2
        draw(page, tx, top, tw, blocks_html(spec, keys, size))
        _, k = layout_panels(page, spec, ML, top, 410.0 - ML, bottom - top)
    else:
        gap = 18.0
        size = 7.6
        best = None
        for ncol in (2, 3):
            cw = (PAGE_W - ML - MR - gap * (ncol - 1)) / ncol
            splits = [(1,), (2,), (3,)] if ncol == 2 else [(1, 2), (1, 3), (2, 3)]
            for sp in splits:
                cuts = [0] + list(sp) + [4]
                groups = [keys[cuts[i]:cuts[i + 1]] for i in range(ncol)]
                h = max(measure(blocks_html(spec, g, size), cw) for g in groups)
                if best is None or h < best[0] - 0.5:
                    best = (h, cw, groups)
        th, cw, groups = best
        ty = bottom - th
        for i, g in enumerate(groups):
            draw(page, ML + i * (cw + gap), ty, cw, blocks_html(spec, g, size))
        page.draw_line(pymupdf.Point(ML, ty - 9), pymupdf.Point(PAGE_W - MR, ty - 9), color=(0.85, 0.86, 0.88), width=0.6)
        _, k = layout_panels(page, spec, ML, top, PAGE_W - ML - MR, ty - 16 - top)
    footer(page, number)
    return page, k
