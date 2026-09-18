"""
thumbs.py -- small pictures of big pictures.

The Results grid used the original file as its own thumbnail. A figure off the
builder is about a megabyte and a half, so a page of thirty was some forty-five
megabytes over the wire to draw thirty things the size of a postage stamp, and
the browser decoded every one of them at full resolution to scale it down.

A thumbnail is 20-40 KB. The arithmetic is the whole justification.

CACHE, NOT RECORD

These live under GUI_logs/.cache, which git ignores, because they are derived
and deterministic: delete the folder and the next page view rebuilds what it
needs. Nothing should ever point at one as though it were a result.

KEYED ON CONTENT, NOT ON PATH

The name is a hash of the file's bytes-length and mtime along with its path,
so re-exporting a figure to the same name makes a different thumbnail rather
than serving the previous one for ever. Filing a result into a folder changes
its path and costs one regeneration, which is cheaper than any of the ways of
being clever about it.

WHEN THERE IS NO PILLOW

Pillow arrives with matplotlib, so it is there in practice. If it ever is not,
`thumb_for` returns None and the caller serves the original -- slower, and
correct, which is the right way round for a picture nobody can otherwise see.
"""
from __future__ import annotations

import hashlib
import os

# The long edge, in pixels. Twice the ~150px the grid draws, so the card still
# looks right on a high-density screen and nothing more is paid for it.
MAX_EDGE = 320

# Anything bigger than this is not worth the read: a thumbnail of it would
# cost more to make than to skip, and the grid shows a placeholder instead.
MAX_SOURCE_BYTES = 80 * 1024 * 1024


def _key(path, st):
    raw = "%s|%d|%d" % (os.path.abspath(path).lower().replace("\\", "/"),
                        st.st_size, int(st.st_mtime))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def thumb_for(path, cache_dir, max_edge=MAX_EDGE):
    """Path to a thumbnail of `path`, making it if need be. None if it cannot.

    Never raises: a grid that fails to draw because one figure is a truncated
    PNG is worse than a grid with one placeholder in it.
    """
    try:
        st = os.stat(path)
    except OSError:
        return None
    if not st.st_size or st.st_size > MAX_SOURCE_BYTES:
        return None

    out = os.path.join(cache_dir, "%s.jpg" % _key(path, st))
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out

    try:
        from PIL import Image
    except Exception:                                    # noqa: BLE001
        return None

    try:
        os.makedirs(cache_dir, exist_ok=True)
        with Image.open(path) as im:
            im.draft("RGB", (max_edge * 2, max_edge * 2))
            im = im.convert("RGB")
            im.thumbnail((max_edge, max_edge), Image.LANCZOS)
            # To a temp name first: two browser tabs asking for the same new
            # thumbnail at once otherwise means one of them reads a file the
            # other is halfway through writing.
            tmp = "%s.%d.tmp" % (out, os.getpid())
            im.save(tmp, "JPEG", quality=82, optimize=True)
        os.replace(tmp, out)
        return out
    except Exception:                                    # noqa: BLE001
        try:
            os.remove(tmp)
        except Exception:                                # noqa: BLE001
            pass
        return None


def sweep(cache_dir, keep_bytes=200 * 1024 * 1024):
    """Drop the least recently used thumbnails if the folder gets large.

    Called from housekeeping rather than on every request: a cache that
    tidies itself on the hot path is a cache that stalls somebody's page
    load to do it.
    """
    try:
        files = []
        with os.scandir(cache_dir) as it:
            for e in it:
                if not e.name.endswith(".jpg"):
                    continue
                try:
                    s = e.stat()
                except OSError:
                    continue
                files.append((s.st_atime, s.st_size, e.path))
    except OSError:
        return 0
    total = sum(f[1] for f in files)
    if total <= keep_bytes:
        return 0
    files.sort()                                   # oldest access first
    freed = 0
    for _at, size, path in files:
        if total - freed <= keep_bytes:
            break
        try:
            os.remove(path)
            freed += size
        except OSError:
            pass
    return freed
