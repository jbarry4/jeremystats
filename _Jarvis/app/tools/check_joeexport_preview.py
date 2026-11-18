# -*- coding: utf-8 -*-
"""Tab 10's list survives a figure PNG that is being drawn again.

2026-11-04, Bluebarry: GET /api/arc/monolith/joeexport/file/... failed six
times with "cannot identify image file ...joepub\\all\\fig_P2_2.png" (and
five other PNGs), each one whole a moment later. joefigs._save writes the
PNG in place, and joeexport._preview read it mid-write: one unreadable PNG
failed the whole manifest.

Nothing written under GUI_logs: the preview cache is a temp folder.

    python tools/check_joeexport_preview.py
"""
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from PIL import Image  # noqa: E402

from backend import joeexport as J  # noqa: E402

ok = bad = 0


def check(name, cond, got=None):
    global ok, bad
    if cond:
        ok += 1
        print("  ok    %s" % name)
    else:
        bad += 1
        print("  FAIL  %s\n        got %r" % (name, got))


def call(png):
    try:
        return J._preview(add, png, "fig_P2_2.png"), None
    except Exception as exc:                              # noqa: BLE001
        return None, exc


root = tempfile.mkdtemp(prefix="joe_preview_")
J.cache_dir = lambda *parts: os.path.join(root, "cache", *parts)
os.makedirs(os.path.join(root, "cache"))
add = lambda path, **kw: {"name": os.path.basename(path)}  # noqa: E731
try:
    png = os.path.join(root, "fig_P2_2.png")
    out = J.cache_dir("fig_P2_2_preview.webp")

    with open(png, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")          # a write just begun
    got, exc = call(png)
    check("a PNG mid-write, no preview yet: no failure", exc is None, exc)
    check("... and no preview listed", got is None, got)

    Image.new("RGB", (1600, 900), (40, 90, 160)).save(png)
    got, exc = call(png)
    check("the whole PNG makes its preview", exc is None and got == "fig_P2_2_preview.webp", (got, exc))
    before = os.path.getmtime(out)

    time.sleep(0.05)
    with open(png, "r+b") as fh:                  # drawn again: cut short
        fh.truncate(200)
    os.utime(png, (time.time() + 5, time.time() + 5))
    got, exc = call(png)
    check("a PNG mid-redraw: no failure", exc is None, exc)
    check("... and the last preview still listed", got == "fig_P2_2_preview.webp", got)
    check("... left as it was", os.path.getmtime(out) == before)

    Image.new("RGB", (1600, 900), (200, 60, 40)).save(png)
    os.utime(png, (time.time() + 10, time.time() + 10))
    got, exc = call(png)
    check("once whole again it is made again",
          exc is None and os.path.getmtime(out) > before
          and Image.open(out).convert("RGB").getpixel((10, 10))[0] > 150, (got, exc))
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\n%d ok, %d failed" % (ok, bad))
sys.exit(1 if bad else 0)
