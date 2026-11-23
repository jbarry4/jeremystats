# -*- coding: utf-8 -*-
"""derived.py -- answers worked out from a recording, kept on disk.

WHY

Opening a recording in Xplorefinder asks for its overview strip: 900 short
reads spread across the whole file. Measured 2026-10-21 on the lab desktop,
10.6 s, and every restart of Jarvis paid it again, because the only copy of
the answer lived in the process's memory. The band strip behind it reads the
whole channel at 250 Hz -- "most of a minute" for a long recording -- with
the same forgetfulness.

These answers never change while the file they came from does not. So they
are written down here, keyed on the file itself: its path, its size and its
modification time. A changed file is a different key, so a kept answer can
never describe data that is no longer there -- it is simply not found, and
the answer is worked out again.

WHERE

GUI_logs/.cache/derived/<kind>/<hash>.json (or .npz), beside the warm cache
and for the same reasons: per machine, derived, regenerable, gitignored, and
never synced -- another computer's copy of a recording is a different file.

LIMITS

At most CAP_BYTES on disk, oldest-used first. "Used" is the file's mtime,
touched on every read, because Windows does not keep access times by
default. Every failure -- a full disk, OneDrive holding a file open, a
corrupt entry -- is "not kept": a read returns None, a write gives up
quietly. Nothing here can fail a request.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time

CAP_BYTES = 1024 * 1024 * 1024
PRUNE_EVERY = 50              # writes between size checks

_ROOT = [None]
_LOCK = threading.Lock()
_WRITES = [0]
_STATS = {"hit": 0, "miss": 0, "put": 0, "pruned": 0, "errors": 0}


def configure(logs_dir):
    _ROOT[0] = os.path.join(logs_dir, ".cache", "derived")


def file_ident(path):
    """(size, mtime_ns) of a file, or None when it cannot be read."""
    try:
        st = os.stat(path)
        return [int(st.st_size), int(st.st_mtime_ns)]
    except (OSError, TypeError, ValueError):
        return None


def _path(kind, parts, ext):
    if not _ROOT[0]:
        return None
    blob = json.dumps(parts, sort_keys=True, default=str)
    h = hashlib.sha1(blob.encode("utf-8")).hexdigest()[:24]
    return os.path.join(_ROOT[0], kind, h + ext)


def _touch(p):
    try:
        os.utime(p, None)
    except OSError:
        pass


def _write(p, data):
    """Temp file and rename, retried: OneDrive and antivirus hold files open
    for a moment, and a half-written entry must never be readable."""
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
    except OSError:
        return False
    tmp = "%s.%d.%d.tmp" % (p, os.getpid(), threading.get_ident())
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
        for attempt in range(4):
            try:
                os.replace(tmp, p)
                return True
            except PermissionError:
                time.sleep(0.05 * (attempt + 1))
        return False
    except OSError:
        return False
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def get_json(kind, parts):
    p = _path(kind, parts, ".json")
    if not p:
        return None
    try:
        with open(p, "rb") as fh:
            out = json.loads(fh.read().decode("utf-8"))
    except FileNotFoundError:
        _STATS["miss"] += 1
        return None
    except (OSError, ValueError):
        _STATS["errors"] += 1
        return None
    _touch(p)
    _STATS["hit"] += 1
    return out


def put_json(kind, parts, obj):
    p = _path(kind, parts, ".json")
    if not p:
        return False
    try:
        data = json.dumps(obj, separators=(",", ":"), default=str).encode("utf-8")
    except (TypeError, ValueError):
        return False
    ok = _write(p, data)
    if ok:
        _after_put()
    return ok


def get_arrays(kind, parts):
    """A dict of numpy arrays (and a `meta` dict), or None."""
    p = _path(kind, parts, ".npz")
    if not p:
        return None
    try:
        import numpy as np
        with np.load(p, allow_pickle=False) as z:
            out = {k: z[k] for k in z.files}
    except FileNotFoundError:
        _STATS["miss"] += 1
        return None
    except Exception:                                    # noqa: BLE001
        _STATS["errors"] += 1
        return None
    if "__meta__" in out:
        try:
            out["meta"] = json.loads(bytes(out.pop("__meta__")).decode("utf-8"))
        except (ValueError, TypeError):
            out["meta"] = {}
    _touch(p)
    _STATS["hit"] += 1
    return out


def put_arrays(kind, parts, arrays, meta=None):
    p = _path(kind, parts, ".npz")
    if not p:
        return False
    try:
        import io
        import numpy as np
        buf = io.BytesIO()
        extra = {}
        if meta is not None:
            extra["__meta__"] = np.frombuffer(
                json.dumps(meta, default=str).encode("utf-8"), dtype=np.uint8)
        np.savez(buf, **arrays, **extra)
        ok = _write(p, buf.getvalue())
    except Exception:                                    # noqa: BLE001
        return False
    if ok:
        _after_put()
    return ok


def _after_put():
    _STATS["put"] += 1
    with _LOCK:
        _WRITES[0] += 1
        due = _WRITES[0] % PRUNE_EVERY == 1
    if due:
        threading.Thread(target=prune, daemon=True).start()


def prune(cap=CAP_BYTES):
    """Remove the least recently used entries until under `cap`."""
    root = _ROOT[0]
    if not root or not os.path.isdir(root):
        return 0
    rows = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            p = os.path.join(dirpath, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if name.endswith(".tmp") and time.time() - st.st_mtime > 3600:
                try:
                    os.remove(p)
                except OSError:
                    pass
                continue
            rows.append((st.st_mtime, st.st_size, p))
    total = sum(r[1] for r in rows)
    removed = 0
    for _m, size, p in sorted(rows):
        if total <= cap:
            break
        try:
            os.remove(p)
            total -= size
            removed += 1
        except OSError:
            continue
    _STATS["pruned"] += removed
    return removed


def stats():
    out = dict(_STATS)
    out["root"] = _ROOT[0]
    return out
