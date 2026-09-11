"""
make_icons.py -- The Jarvis mark, as files the desktop can use.

`web/img/jarvis.svg` is the mark. A browser tab takes the SVG directly, but
Windows wants an `.ico` and macOS wants a `.png` (or an `.icns`), and both
want several sizes in one file so the small ones are not a blurry shrink of
the large one.

Rather than re-draw the mark in PIL -- two implementations of one shape,
which drift the first time somebody edits either -- this renders the real
SVG in the browser that is already used for the harnesses, at each size, and
packs the results. So the tab, the shortcut and the dock cannot disagree.

    python tools/make_icons.py

Writes:
    web/img/jarvis-<n>.png     256, 128, 64, 48, 32, 16
    web/img/jarvis.ico         all of the above, in one file
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
# The one the browser draws. Everything else is resampled from it.
MASTER = 512
SIZES = [256, 128, 64, 48, 32, 16]
SRC = os.path.join(APP, "web", "img", "jarvis.svg")
OUT = os.path.join(APP, "web", "img")


def page_for(svg, size):
    """A page that is nothing but the mark, at exactly `size` pixels.

    No margin, no scrollbars, and a transparent ground: an icon with a white
    square behind it looks like a sticker on every dark dock.
    """
    return (
        "<!doctype html><meta charset='utf-8'>"
        "<style>html,body{margin:0;padding:0;background:transparent;"
        "overflow:hidden}svg{display:block;width:%dpx;height:%dpx}</style>"
        % (size, size)
    ) + svg


def render(svg, size, where):
    """One PNG, rendered by the browser from the real SVG."""
    html = os.path.join(where, "icon_%d.html" % size)
    png = os.path.join(where, "icon_%d.png" % size)
    io.open(html, "w", encoding="utf-8").write(page_for(svg, size))
    res = subprocess.run(
        [EDGE, "--headless=new", "--disable-gpu",
         "--default-background-color=00000000",
         "--force-device-scale-factor=1",
         "--window-size=%d,%d" % (size, size),
         "--virtual-time-budget=4000",
         "--screenshot=" + png, html],
        capture_output=True, timeout=180)
    if not os.path.exists(png):
        sys.stderr.write(res.stderr.decode("utf-8", "replace")[-400:])
        raise SystemExit("the browser produced no PNG at %d px" % size)
    return png


def main():
    if not os.path.exists(SRC):
        raise SystemExit("No mark at %s" % SRC)
    if not os.path.exists(EDGE):
        raise SystemExit("Edge is not where this expects it: " + EDGE)
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("Pillow is needed to pack the .ico: pip install "
                         "pillow")

    svg = io.open(SRC, encoding="utf-8").read().strip()
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="jarvis-icons-")
    frames = []
    try:
        # Rendered once, large, then resampled down.
        #
        # Asking the browser for a 64 px window hangs it -- headless Edge
        # will not go that small and simply never produces the file. So the
        # browser draws the mark once at 512, where it is unambiguously
        # crisp, and Lanczos does the rest. The mark is still rendered from
        # the real SVG exactly once, which is the property that matters.
        master = Image.open(render(svg, MASTER, tmp)).convert("RGBA")
        if master.size != (MASTER, MASTER):
            master = master.resize((MASTER, MASTER), Image.LANCZOS)
        for size in SIZES:
            img = (master if size == MASTER
                   else master.resize((size, size), Image.LANCZOS))
            keep = os.path.join(OUT, "jarvis-%d.png" % size)
            img.save(keep)
            frames.append(img)
            print("  %3d px  %s" % (size, os.path.relpath(keep, APP)))
    finally:
        for n in os.listdir(tmp):
            try:
                os.remove(os.path.join(tmp, n))
            except OSError:
                pass
        os.rmdir(tmp)

    ico = os.path.join(OUT, "jarvis.ico")
    # Largest first, every size embedded: Windows picks per context, and a
    # single-size .ico is what makes a taskbar button look resampled.
    frames[0].save(ico, format="ICO",
                   sizes=[(s, s) for s in SIZES])
    print("  ico     %s  (%d sizes)" % (os.path.relpath(ico, APP),
                                        len(SIZES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
