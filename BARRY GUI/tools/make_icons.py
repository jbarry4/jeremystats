"""
make_icons.py -- The Jarvis mark, as files the desktop can use.

The mark is drawn by one function, `markSvg` in `web/js/jarvis.js`, which
also draws the rail badge, the tab icon and the reveal. This writes the
static copies of it that need to exist as files -- `web/img/jarvis.svg` for
pages and the first paint, `web/img/workbench.svg` for the same while the
name is hidden -- and then the raster icons: Windows wants an `.ico`, macOS
a `.png`, and both want several sizes in one file so the small ones are not
a blurry shrink of the large one.

Rather than re-draw the mark in Python -- two implementations of one shape,
which drift the first time somebody edits either -- this asks the browser
that already runs the harnesses to call `markSvg` and to render what it
returns. So the tab, the rail, the shortcut and the dock cannot disagree.

    python tools/make_icons.py

Writes:
    web/img/jarvis.svg         the mark, UVM green and gold
    web/img/workbench.svg      the plain tile shown while the name is hidden
    web/img/jarvis-<n>.png     256, 128, 64, 48, 32, 16
    web/img/jarvis.ico         all of the above, in one file

Run it from PowerShell or cmd, not Git Bash: under Bash, Edge writes nothing
for --dump-dom on this machine.
"""
from __future__ import annotations

import base64
import io
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
# The one the browser draws. Everything else is resampled from it.
MASTER = 512
SIZES = [256, 128, 64, 48, 32, 16]
# At and below this the mark is drawn in its small cut -- heavier strokes,
# no dial and no glow -- because the large one turns to mud at 16 px.
SMALL = 32
JS = os.path.join(APP, "web", "js", "jarvis.js")
OUT = os.path.join(APP, "web", "img")
SRC = os.path.join(OUT, "jarvis.svg")
DORMANT = os.path.join(OUT, "workbench.svg")


def _uri(path):
    return "file:///" + path.replace("\\", "/")


def marks_from_js(where):
    """Ask jarvis.js for the two static marks.

    Base64 in an attribute on the way out, so what comes back is exactly the
    string `markSvg` returned and not the browser's re-serialisation of it.
    Dumped to a file rather than a pipe: a piped --dump-dom comes back empty
    on this machine.
    """
    page = os.path.join(where, "marks.html")
    dump = os.path.join(where, "marks.txt")
    io.open(page, "w", encoding="utf-8").write(
        "<!doctype html><meta charset='utf-8'><body>"
        "<script src='%s'></script>"
        "<script>"
        "const J = window.JarvisName;"
        "const enc = (s) => btoa(unescape(encodeURIComponent(s)));"
        "document.body.setAttribute('data-mark', enc(J.markSvg(J.UVM, 'full', {file: true})));"
        "document.body.setAttribute('data-dormant', enc(J.markSvg(J.UVM, 'tiny', {dormant: true})));"
        "</script></body>" % _uri(JS))
    with open(dump, "wb") as fh:
        subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu",
             "--user-data-dir=" + os.path.join(where, "profile"),
             "--allow-file-access-from-files",
             "--virtual-time-budget=3000", "--dump-dom", _uri(page)],
            stdout=fh, stderr=subprocess.DEVNULL, timeout=180)
    dom = io.open(dump, encoding="utf-8", errors="replace").read()
    out = {}
    for key in ("mark", "dormant"):
        m = re.search(r'data-%s="([A-Za-z0-9+/=]+)"' % key, dom)
        if not m:
            raise SystemExit("jarvis.js gave no %s -- is this PowerShell or "
                             "cmd rather than Git Bash?" % key)
        out[key] = base64.b64decode(m.group(1)).decode("utf-8")
    return out


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


def render(svg, size, where, name):
    """One PNG, rendered by the browser from the real SVG."""
    html = os.path.join(where, "icon_%s.html" % name)
    png = os.path.join(where, "icon_%s.png" % name)
    io.open(html, "w", encoding="utf-8").write(page_for(svg, size))
    res = subprocess.run(
        [EDGE, "--headless=new", "--disable-gpu",
         "--user-data-dir=" + os.path.join(where, "profile"),
         "--default-background-color=00000000",
         "--force-device-scale-factor=1",
         "--window-size=%d,%d" % (size, size),
         "--virtual-time-budget=4000",
         "--screenshot=" + png, html],
        capture_output=True, timeout=180)
    if not os.path.exists(png):
        sys.stderr.write(res.stderr.decode("utf-8", "replace")[-400:])
        raise SystemExit("the browser produced no PNG for %s" % name)
    return png


def main():
    if not os.path.exists(JS):
        raise SystemExit("No mark at %s" % JS)
    if not os.path.exists(EDGE):
        raise SystemExit("Edge is not where this expects it: " + EDGE)
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("Pillow is needed to pack the .ico: pip install "
                         "pillow")

    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="jarvis-icons-")
    frames = []
    try:
        marks = marks_from_js(tmp)
        for path, text in ((SRC, marks["mark"]), (DORMANT, marks["dormant"])):
            io.open(path, "w", encoding="utf-8", newline="\n").write(text + "\n")
            print("  svg     %s" % os.path.relpath(path, APP))

        # Rendered twice, large, then resampled down: once as drawn, once in
        # the small cut (the file's own `svg.small` rules).
        #
        # Asking the browser for a 64 px window hangs it -- headless Edge
        # will not go that small and simply never produces the file. So the
        # browser draws each cut once at 512, where it is unambiguously
        # crisp, and Lanczos does the rest.
        svg = marks["mark"]
        small = svg.replace("<svg ", '<svg class="small" ', 1)
        masters = {}
        for name, text in (("full", svg), ("small", small)):
            img = Image.open(render(text, MASTER, tmp, name)).convert("RGBA")
            if img.size != (MASTER, MASTER):
                img = img.resize((MASTER, MASTER), Image.LANCZOS)
            masters[name] = img
        for size in SIZES:
            master = masters["small" if size <= SMALL else "full"]
            img = master.resize((size, size), Image.LANCZOS)
            keep = os.path.join(OUT, "jarvis-%d.png" % size)
            img.save(keep)
            frames.append(img)
            print("  %3d px  %s" % (size, os.path.relpath(keep, APP)))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    ico = os.path.join(OUT, "jarvis.ico")
    # Every size embedded, each from its own cut: Windows picks per context,
    # and a single-size .ico is what makes a taskbar button look resampled.
    # `append_images` is what keeps the small cut for the small sizes --
    # without it Pillow resamples all of them from the first frame.
    frames[0].save(ico, format="ICO", sizes=[(s, s) for s in SIZES],
                   append_images=frames[1:])
    print("  ico     %s  (%d sizes)" % (os.path.relpath(ico, APP),
                                        len(SIZES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
