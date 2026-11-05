# -*- coding: utf-8 -*-
"""membudget.py -- one memory budget for every cache in the server.

WHY

Measured 2026-10-21 on the lab desktop: a few minutes after start, with one
recording opened, the server held 1.3 GB of private memory. About fifteen
modules keep a cache of their own -- rendered panels (`prewarm`, up to
320 MB by itself), trace windows, overview strips, band profiles, Horizon's
and Panorama's arrays, video clips, storyboard images -- and each one
bounds itself by its own count, in its own units, without knowing about the
others. Sixteen caches that are each "reasonable" add up to a laptop that
swaps.

So there is one budget, in bytes, for all of them together, and one
least-recently-used policy across them: whatever nobody has looked at for
longest goes first, whichever cache it is in.

HOW A CACHE TAKES PART

    membudget.register("overview", items=fn, drop=fn)

`items()` returns `[(key, nbytes, last_used), ...]` for what the cache holds
right now; `drop(key)` removes one entry. After a cache adds something it
calls `membudget.settle()`, which evicts across every registered cache until
the total is under the budget. A cache that cannot say how big an entry is
should estimate: a wrong guess costs a little accuracy, not correctness --
a dropped entry is simply recomputed next time.

THE BUDGET

About 6 % of the machine's memory, at least 256 MB and at most 1 GB: 1 GB on
the 16 GB laptop the lab plans for (2026-10-21). Jarvis Light halves it,
because a computer that needs Light is one that needs the memory back.

`report()` is what `/api/debug/memory` shows: the process's own resident and
private bytes, the budget, and every cache's entries and bytes.
"""
from __future__ import annotations

import os
import sys
import threading
import time

MB = 1024 * 1024
FLOOR = 256 * MB
CEILING = 1024 * MB
SHARE = 0.0625

_LOCK = threading.RLock()
_CACHES = {}             # name -> {"items": fn, "drop": fn}
_LIGHT = [False]
_STATS = {"evicted": 0, "evicted_bytes": 0, "settles": 0}


# --------------------------------------------------------------------------
# The machine and the process
# --------------------------------------------------------------------------
def total_ram():
    """Physical memory in bytes, or None when the platform will not say."""
    if sys.platform.startswith("win"):
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return int(st.ullTotalPhys)
        except Exception:                                # noqa: BLE001
            return None
        return None
    try:
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except (ValueError, OSError, AttributeError):
        return None


def process_memory():
    """{"rss": bytes, "private": bytes or None} for this process."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD),
                            ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t),
                            ("PrivateUsage", ctypes.c_size_t)]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            k32 = ctypes.windll.kernel32
            # Typed, or the pseudo-handle (-1) goes through as a 32-bit int
            # and the call quietly fails on a 64-bit Python.
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            fn = getattr(k32, "K32GetProcessMemoryInfo", None) \
                or ctypes.windll.psapi.GetProcessMemoryInfo
            fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            fn.restype = wintypes.BOOL
            ok = fn(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
            if ok:
                return {"rss": int(pmc.WorkingSetSize),
                        "private": int(pmc.PrivateUsage)}
        except Exception:                                # noqa: BLE001
            pass
        return {"rss": None, "private": None}
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports kilobytes, macOS bytes.
        rss = peak if sys.platform == "darwin" else peak * 1024
        return {"rss": int(rss), "private": None}
    except Exception:                                    # noqa: BLE001
        return {"rss": None, "private": None}


# --------------------------------------------------------------------------
# The budget
# --------------------------------------------------------------------------
_SOURCE = [None, 0.0, False]   # fn, when last asked, its answer


def set_light(on):
    """Jarvis Light on this machine: the budget halves."""
    _LIGHT[0] = bool(on)


def light_from(fn):
    """Where to read whether Light is on (app.py: this machine's own prefs
    shard). Asked at most every 30 s."""
    _SOURCE[0] = fn
    _SOURCE[1] = 0.0


def light():
    fn = _SOURCE[0]
    if fn is not None and time.time() - _SOURCE[1] > 30:
        _SOURCE[1] = time.time()
        try:
            _SOURCE[2] = bool(fn())
        except Exception:                                # noqa: BLE001
            _SOURCE[2] = False
    return _LIGHT[0] or (fn is not None and _SOURCE[2])


def budget():
    ram = total_ram() or 16 * 1024 * MB
    full = int(min(CEILING, max(FLOOR, ram * SHARE)))
    return full // 2 if light() else full


# --------------------------------------------------------------------------
# The caches
# --------------------------------------------------------------------------
def sizeof(obj, _depth=0):
    """Roughly how many bytes `obj` holds: numpy arrays by their buffers,
    strings and bytes by their length, containers by what is in them.
    Rough on purpose -- it decides what to drop first, not what to bill."""
    if _depth > 6 or obj is None:
        return 0
    nb = getattr(obj, "nbytes", None)
    if isinstance(nb, int):
        # Only bytes that are actually in memory. An h5py dataset reports
        # the size of what is on DISK, and a memmap's pages belong to its
        # file: counting either would make a ten-gigabyte recording look
        # like ten gigabytes of cache, and the budget would throw out the
        # one handle keeping it cheap to read.
        mod = type(obj).__module__ or ""
        if mod.startswith("h5py") or type(obj).__name__ == "memmap":
            return 64
        return nb
    if isinstance(obj, (bytes, bytearray, str)):
        return len(obj)
    if isinstance(obj, dict):
        return sum(64 + sizeof(k, _depth + 1) + sizeof(v, _depth + 1)
                   for k, v in obj.items())
    if isinstance(obj, (list, tuple, set, frozenset)):
        return 56 + sum(8 + sizeof(v, _depth + 1) for v in obj)
    try:
        return sys.getsizeof(obj)
    except TypeError:
        return 64


def watch_dict(name, cache, order=None, lock=None):
    """Take part in the budget with a module's plain dict cache, unchanged.

    Most of the server's caches are a dict, a list of keys in the order they
    went in, and a lock (panorama, spectrum, cfc, doppler, incisor, Horizon).
    This reads them as they are: an entry's size is measured once, the first
    time it is seen, and its age is when it was first seen -- the order they
    go in, across all of them. Dropping one removes it from the dict and the
    list under the module's own lock."""
    seen = {}

    def items():
        now = time.time()
        keys = list(cache.keys())
        live = set(keys)
        for k in list(seen):
            if k not in live:
                del seen[k]
        out = []
        for k in keys:
            if k not in seen:
                try:
                    seen[k] = (sizeof(cache.get(k)), now)
                except Exception:                        # noqa: BLE001
                    seen[k] = (0, now)
            n, at = seen[k]
            out.append((k, n, at))
        return out

    def drop(key):
        ctx = lock if lock is not None else threading.Lock()
        with ctx:
            cache.pop(key, None)
            if order is not None:
                try:
                    order.remove(key)
                except ValueError:
                    pass
        seen.pop(key, None)

    register(name, items, drop)


_LAST_SETTLE = [0.0]


def settle_soon(min_gap=2.0):
    """`settle`, at most once every `min_gap` seconds -- for the request
    hook, so a burst of answers costs one pass, not one each."""
    now = time.time()
    if now - _LAST_SETTLE[0] < min_gap:
        return 0
    _LAST_SETTLE[0] = now
    return settle()


def register(name, items, drop):
    """Take part in the budget. Registering a name twice replaces it, so a
    module reloaded in a test does not leave its old functions behind."""
    with _LOCK:
        _CACHES[name] = {"items": items, "drop": drop}


def _entries():
    rows = []
    for name, c in list(_CACHES.items()):
        try:
            for key, nbytes, used in c["items"]() or ():
                rows.append((float(used or 0), name, key, int(nbytes or 0)))
        except Exception:                                # noqa: BLE001
            continue
    return rows


def used():
    return sum(r[3] for r in _entries())


def settle():
    """Evict, oldest first and across every cache, until under budget.

    Returns the bytes freed. Cheap when nothing needs to go: one pass over
    what the caches hold, which is hundreds of entries, not millions."""
    with _LOCK:
        _STATS["settles"] += 1
        rows = _entries()
        total = sum(r[3] for r in rows)
        limit = budget()
        if total <= limit:
            return 0
        freed = 0
        for used_at, name, key, nbytes in sorted(rows):
            if total - freed <= limit:
                break
            try:
                _CACHES[name]["drop"](key)
            except Exception:                            # noqa: BLE001
                continue
            freed += nbytes
            _STATS["evicted"] += 1
            _STATS["evicted_bytes"] += nbytes
        return freed


def report():
    """For /api/debug/memory."""
    per = {}
    for used_at, name, key, nbytes in _entries():
        p = per.setdefault(name, {"entries": 0, "bytes": 0, "oldest": None})
        p["entries"] += 1
        p["bytes"] += nbytes
        if used_at and (p["oldest"] is None or used_at < p["oldest"]):
            p["oldest"] = used_at
    for name in _CACHES:
        per.setdefault(name, {"entries": 0, "bytes": 0, "oldest": None})
    now = time.time()
    for p in per.values():
        p["mb"] = round(p["bytes"] / MB, 1)
        p["oldest_s"] = round(now - p["oldest"]) if p["oldest"] else None
        del p["oldest"]
    proc = process_memory()
    heavy = [m for m in ("numpy", "scipy", "scipy.signal", "scipy.stats",
                         "sklearn", "matplotlib", "fooof", "h5py", "pandas")
             if m in sys.modules]
    return {
        "process": {k: (round(v / MB, 1) if v else None)
                    for k, v in proc.items()},
        "ram_mb": round((total_ram() or 0) / MB),
        "budget_mb": round(budget() / MB),
        "light": light(),
        "caches_mb": round(sum(p["bytes"] for p in per.values()) / MB, 1),
        "caches": dict(sorted(per.items(), key=lambda kv: -kv[1]["bytes"])),
        "imported": heavy,
        "stats": dict(_STATS),
    }
