"""
extras.py -- the second round of section features.

Everything here is additive: session health checks, a full-recording overview
strip for the viewer's minimap, error grouping, repo grep, a scratch runner
and housekeeping. Kept out of app.py so that file stays a routing table.
"""
from __future__ import annotations

import csv
import io
import os
import re
import shutil
import threading
import time

import numpy as np

from . import csc, ids, nlx


# ==========================================================================
# Session health
# ==========================================================================
# Each check is (level, name, message) with level 'ok' | 'warn' | 'bad'.
def session_health(path, deep=False):
    """Validate a recording folder the way a person would before analysis."""
    out = {"path": path, "checks": [], "level": "ok"}
    if not os.path.isdir(path):
        if os.path.isfile(path):
            out["checks"].append(_c("warn", "single file",
                                    "This is one file, not a session folder."))
            return _grade(out)
        out["checks"].append(_c("bad", "missing", "Folder does not exist."))
        return _grade(out)

    try:
        names = os.listdir(path)
    except OSError as exc:
        out["checks"].append(_c("bad", "unreadable", str(exc)))
        return _grade(out)

    ncs = sorted(n for n in names if n.lower().endswith(".ncs"))
    mats = [n for n in names if n.lower().endswith(".mat")]
    nvts = [n for n in names if n.lower().endswith(".nvt")]
    vids = [n for n in names if os.path.splitext(n)[1].lower()
            in (".mpg", ".mp4", ".avi", ".mpeg", ".mov")]
    nevs = [n for n in names if n.lower().endswith(".nev")]

    # ---- channel inventory ----
    if not ncs:
        out["checks"].append(_c(
            "bad" if not mats else "warn", "no CSC files",
            "No CSC*.ncs here." + (" Converted .mat only." if mats else "")))
    else:
        nums = [n for n in (_csc_num(x) for x in ncs) if n]
        nums.sort()
        out["channels"] = len(ncs)
        out["checks"].append(_c("ok", "channels",
                                "%d CSC file(s), CSC%d-CSC%d"
                                % (len(ncs), min(nums or [0]), max(nums or [0]))))
        # Neuralynx numbers channels contiguously, so a hole means a lost file.
        # An even-only or odd-only rig is normal though, not a gap.
        if nums:
            gaps = [n for n in range(min(nums), max(nums) + 1) if n not in nums]
            evens = [n for n in nums if n % 2 == 0]
            odds = [n for n in nums if n % 2]
            if gaps and evens and odds:
                out["checks"].append(_c(
                    "warn", "channel gaps",
                    "Missing CSC number(s): " + _brief(gaps)))

    # ---- sizes: a truncated file is the classic mid-recording crash ----
    sizes = {}
    for n in ncs:
        try:
            sizes[n] = os.path.getsize(os.path.join(path, n))
        except OSError:
            sizes[n] = 0
    if sizes:
        vals = sorted(sizes.values())
        med = vals[len(vals) // 2]
        short = [n for n, s in sizes.items() if med and s < med * 0.98]
        empty = [n for n, s in sizes.items() if s <= nlx.HEADER_BYTES]
        if empty:
            out["checks"].append(_c("bad", "empty files",
                                    "%d file(s) hold only a header: %s"
                                    % (len(empty), _brief(sorted(empty)[:6]))))
        elif short:
            out["checks"].append(_c(
                "warn", "uneven lengths",
                "%d file(s) shorter than the rest -- the recording may have "
                "been cut: %s" % (len(short), _brief(sorted(short)[:6]))))
        else:
            out["checks"].append(_c("ok", "file sizes",
                                    "All channels the same length."))
        # A byte count that is not a whole number of records means a partial
        # write at the tail.
        ragged = [n for n, s in sizes.items()
                  if s > nlx.HEADER_BYTES
                  and (s - nlx.HEADER_BYTES) % nlx.RECORD_DTYPE.itemsize]
        if ragged:
            out["checks"].append(_c(
                "warn", "partial record",
                "%d file(s) end mid-record: %s"
                % (len(ragged), _brief(sorted(ragged)[:6]))))

    # ---- header: sample-rate agreement and duration ----
    if ncs:
        first = os.path.join(path, ncs[0])
        try:
            hdr = nlx.read_header(first)
            fs = nlx._header_float(hdr, "SamplingFrequency")
            out["fs"] = fs
            out["start_time"] = nlx.header_start_time(hdr)
            size = os.path.getsize(first)
            n_rec = max(0, (size - nlx.HEADER_BYTES) // nlx.RECORD_DTYPE.itemsize)
            dur = n_rec * nlx.SAMPLES_PER_RECORD / fs if fs else 0.0
            out["duration_s"] = dur
            if not fs:
                out["checks"].append(_c("warn", "sample rate",
                                        "Header has no SamplingFrequency."))
            elif dur < 30:
                out["checks"].append(_c("warn", "very short",
                                        "Only %s of data." % _dur(dur)))
            else:
                out["checks"].append(_c("ok", "duration",
                                        "%s at %g Hz" % (_dur(dur), fs)))

            # Comparing every header is slow over the network, so sample.
            probe = ncs[::max(1, len(ncs) // 8)][:8]
            rates = set()
            for n in probe:
                try:
                    h = nlx.read_header(os.path.join(path, n))
                    r = nlx._header_float(h, "SamplingFrequency")
                    if r:
                        rates.add(round(r, 3))
                except OSError:
                    pass
            if len(rates) > 1:
                out["checks"].append(_c(
                    "bad", "mixed sample rates",
                    "Channels disagree: " + ", ".join("%g" % r for r in
                                                      sorted(rates))))
        except Exception as exc:
            out["checks"].append(_c("warn", "header",
                                    "Could not read the header: %s" % exc))

    # ---- companions ----
    out["checks"].append(_c(
        "ok" if vids else "warn", "video",
        ", ".join(vids[:3]) if vids
        else "No video file -- the video pane will be empty."))
    out["checks"].append(_c(
        "ok" if nvts else "warn", "tracking",
        ", ".join(nvts[:3]) if nvts else "No .nvt -- no position tracking."))
    out["checks"].append(_c(
        "ok" if nevs else "warn", "events",
        ", ".join(nevs[:3]) if nevs else "No Events.nev -- TTL marks unavailable."))

    # ---- identity ----
    ident = ids.identify(path, header_time=out.get("start_time"))
    out["identity"] = ident
    conf = ident.get("confidence")
    out["checks"].append(_c(
        "ok" if conf == "exact" else ("warn" if conf else "bad"),
        "identity",
        "%s (%s)" % (ident.get("label") or "unnamed", conf or "unrecognized")))

    # ---- deep: look for flat or railed channels ----
    if deep and ncs:
        try:
            out["checks"].extend(_deep_signal_checks(path, ncs))
        except Exception as exc:
            out["checks"].append(_c("warn", "signal probe", str(exc)))

    return _grade(out)


def _deep_signal_checks(folder, ncs):
    """Read a short slice from every channel and flag dead / railed ones."""
    checks, flat, rail, noisy = [], [], [], []
    for name in ncs:
        p = os.path.join(folder, name)
        try:
            data, _t0, _fs = nlx.read_ncs_range(p, 1.0, 6.0, invert=False)
        except Exception:
            continue
        if data.size < 100:
            continue
        label = "CSC%s" % (_csc_num(name) or "?")
        sd = float(np.std(data))
        if sd < 1.0:
            flat.append(label)
        elif sd > 4000.0:
            noisy.append(label)
        # ADC saturation: many samples pinned at the extreme.
        peak = float(np.max(np.abs(data)))
        if peak and float(np.mean(np.abs(data) > peak * 0.999)) > 0.01:
            rail.append(label)

    if flat:
        checks.append(_c("warn", "flat channels",
                         "Near-zero variance: " + _brief(flat)))
    if rail:
        checks.append(_c("warn", "clipping",
                         "Pinned at the ADC limit: " + _brief(rail)))
    if noisy:
        checks.append(_c("warn", "very noisy", "SD above 4 mV: " + _brief(noisy)))
    if not (flat or rail or noisy):
        checks.append(_c("ok", "signal probe",
                         "All channels have plausible amplitude."))
    return checks


def _csc_num(name):
    """Channel number out of a CSC filename, or None if it is not one."""
    m = nlx._CSC_NAME_RE.match(os.path.basename(name))
    return int(m.group(1)) if m else None


def _c(level, name, message):
    return {"level": level, "name": name, "message": message}


def _grade(out):
    levels = [c["level"] for c in out["checks"]]
    out["level"] = ("bad" if "bad" in levels
                    else ("warn" if "warn" in levels else "ok"))
    out["n_warn"] = levels.count("warn")
    out["n_bad"] = levels.count("bad")
    return out


def _brief(items, limit=8):
    items = [str(i) for i in items]
    if len(items) <= limit:
        return ", ".join(items)
    return ", ".join(items[:limit]) + " (+%d more)" % (len(items) - limit)


def _dur(s):
    s = float(s or 0)
    if s < 60:
        return "%.1f s" % s
    if s < 3600:
        return "%d m %02d s" % (s // 60, s % 60)
    return "%d h %02d m" % (s // 3600, (s % 3600) // 60)


# ==========================================================================
# Python import preflight
# ==========================================================================
# A repo script's own imports are the only honest statement of what it needs,
# and registry already parses them. Map the handful of names that differ from
# their pip package, skip anything shipped with Python, and skip siblings in
# the repo itself.
_PKG_ALIASES = {
    "cv2": "opencv-python", "skimage": "scikit-image",
    "sklearn": "scikit-learn", "yaml": "PyYAML", "PIL": "Pillow",
    "mpl_toolkits": "matplotlib", "matplotlib": "matplotlib",
}


def missing_python_packages(items, repo_root):
    """Which third-party imports of these scripts are not importable here."""
    import importlib.util
    import sys as _sys

    wanted = set()
    for it in items or []:
        for name in (it.get("imports") or []):
            top = str(name).split(".")[0]
            if top and not top.startswith("_"):
                wanted.add(top)

    local = _repo_module_names(repo_root)
    missing = []
    for name in sorted(wanted):
        if name in _sys.builtin_module_names or name in local:
            continue
        try:
            if importlib.util.find_spec(name) is not None:
                continue
        except (ImportError, ValueError, ModuleNotFoundError):
            pass
        missing.append(_PKG_ALIASES.get(name, name))
    return sorted(set(missing))


_LOCAL_MODULES = {}


def _repo_module_names(repo_root):
    """Top-level names a repo script could be importing from its own folder."""
    hit = _LOCAL_MODULES.get(repo_root)
    if hit is not None:
        return hit
    names = set()
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")]
        for n in filenames:
            if n.endswith(".py"):
                names.add(n[:-3])
        for d in dirnames:
            if os.path.isfile(os.path.join(dirpath, d, "__init__.py")):
                names.add(d)
    _LOCAL_MODULES[repo_root] = names
    return names


# ==========================================================================
# Recording overview -- the viewer's minimap
# ==========================================================================
_OVERVIEW_CACHE = {}
OVERVIEW_BINS = 900


def overview(session, channel=None, bins=OVERVIEW_BINS):
    """A whole-recording amplitude strip, so the window has a context bar.

    Reads one channel at a coarse stride: a two-hour recording is summarized
    from a few megabytes, because .ncs records are seekable by index.
    """
    chans = session.get("channels") or []
    if not chans:
        return {"ok": False, "error": "No channels."}
    idx = channel if channel is not None else len(chans) // 2
    idx = max(0, min(int(idx), len(chans) - 1))
    ch = chans[idx]

    # "v2" because the shape of the response changed: a cache entry written
    # before mabs existed would come back without it.
    key = (session.get("path"), ch.get("number"), int(bins), "v2")
    hit = _OVERVIEW_CACHE.get(key)
    if hit:
        return hit

    dur = float(session.get("duration_s") or 0)
    if dur <= 0:
        return {"ok": False, "error": "Unknown duration."}
    bins = int(max(60, min(bins, 2000)))
    step = dur / bins

    lo = np.zeros(bins, dtype=np.float32)
    hi = np.zeros(bins, dtype=np.float32)
    amp = np.zeros(bins, dtype=np.float32)
    # Mean |amplitude| per bin. RMS is dominated by the loudest few samples
    # in a bin, so a single spike lifts the whole bin; the mean of the
    # absolute value tracks how big the signal typically is, which is what
    # you want from a strip you are using to find the busy stretches.
    mabs = np.zeros(bins, dtype=np.float32)

    # A bin can be minutes long, so read a short probe from the head of each
    # rather than the whole span -- keeps the strip quick on network storage.
    probe = min(step, 0.35)
    for i in range(bins):
        t0 = i * step
        try:
            seg, _t, _fs = csc._read_channel_window(session, ch, t0, t0 + probe)
        except Exception:
            continue
        if seg.size == 0:
            continue
        lo[i] = float(np.min(seg))
        hi[i] = float(np.max(seg))
        amp[i] = float(np.sqrt(np.mean(np.square(seg, dtype=np.float64))))
        mabs[i] = float(np.mean(np.abs(seg, dtype=np.float64)))

    res = {
        "ok": True, "bins": bins, "duration_s": dur,
        "channel": {"index": idx, "number": ch.get("number"),
                    "label": ch.get("label")},
        "lo": [round(float(v), 1) for v in lo],
        "hi": [round(float(v), 1) for v in hi],
        "rms": [round(float(v), 1) for v in amp],
        "mabs": [round(float(v), 1) for v in mabs],
        "probe_s": probe,
    }
    if len(_OVERVIEW_CACHE) > 24:
        _OVERVIEW_CACHE.clear()
    _OVERVIEW_CACHE[key] = res
    return res


# ==========================================================================
# Error grouping
# ==========================================================================
_NOISE = [
    (re.compile(r"0x[0-9a-fA-F]{4,}"), "0xADDR"),
    (re.compile(r"\d{4}-\d{2}-\d{2}[ T_]\d{2}[-:]\d{2}[-:]\d{2}"), "<time>"),
    (re.compile(r"[A-Za-z]:[\\/][^\s'\"]+"), "<path>"),
    (re.compile(r"[\\/]{2}[^\s'\"]+"), "<path>"),
    (re.compile(r"\d+"), "N"),
]


def signature(rec):
    """Collapse an error to a stable key so repeats can be counted."""
    msg = str(rec.get("message") or "")
    for pat, sub in _NOISE:
        msg = pat.sub(sub, msg)
    return "%s|%s|%s" % (rec.get("where") or "", rec.get("type") or "",
                         msg.strip()[:180])


def group_errors(records):
    """Fold a flat error list into groups: unresolved first, then newest."""
    groups = {}
    for rec in records:
        sig = signature(rec)
        g = groups.get(sig)
        if not g:
            g = groups[sig] = {
                "signature": sig, "count": 0, "first": None, "last": None,
                "where": rec.get("where"), "message": rec.get("message"),
                "type": rec.get("type"), "records": [], "resolved": True,
                "machines": [],
            }
        g["count"] += 1
        ts = rec.get("at") or rec.get("time") or ""
        if not g["first"] or ts < g["first"]:
            g["first"] = ts
        if not g["last"] or ts > g["last"]:
            g["last"] = ts
            g["message"] = rec.get("message")
        if len(g["records"]) < 25:
            g["records"].append(rec)
        if not rec.get("resolved"):
            g["resolved"] = False
        host = rec.get("machine") or (rec.get("context") or {}).get("host")
        if host and host not in g["machines"]:
            g["machines"].append(host)

    out = list(groups.values())
    out.sort(key=lambda g: (bool(g["resolved"]), _desc(g["last"])))
    return out


def _desc(ts):
    """Sort key that puts the newest timestamp first in an ascending sort."""
    return tuple(-ord(c) for c in (ts or ""))


# ==========================================================================
# Repo grep
# ==========================================================================
SEARCH_EXT = (".py", ".m", ".ipynb", ".txt", ".md", ".json", ".csv",
              ".prb", ".yaml", ".yml", ".cfg", ".sh", ".bat")
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".vs", ".idea",
             "GUI_logs", "Output", ".ipynb_checkpoints"}


def repo_grep(root, pattern, regex=False, case=False, limit=400,
              exts=None, max_bytes=4_000_000, budget_s=25.0):
    """Grep the repo in-process, so it behaves identically on macOS."""
    if not pattern:
        return {"ok": False, "error": "Nothing to search for."}
    flags = 0 if case else re.IGNORECASE
    try:
        rx = re.compile(pattern if regex else re.escape(pattern), flags)
    except re.error as exc:
        return {"ok": False, "error": "Bad pattern: %s" % exc}

    wanted = tuple(exts) if exts else SEARCH_EXT
    hits, files_scanned, truncated = [], 0, False
    t_start = time.time()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if not name.lower().endswith(wanted):
                continue
            full = os.path.join(dirpath, name)
            try:
                if os.path.getsize(full) > max_bytes:
                    continue
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    files_scanned += 1
                    for i, line in enumerate(fh, 1):
                        if rx.search(line):
                            hits.append({
                                "rel": _rel(full, root), "path": full,
                                "line": i, "text": line.rstrip("\n\r")[:400],
                            })
                            if len(hits) >= limit:
                                truncated = True
                                break
            except OSError:
                continue
            if truncated or time.time() - t_start > budget_s:
                truncated = True
                break
        if truncated:
            break

    return {"ok": True, "hits": hits, "files": files_scanned,
            "truncated": truncated, "seconds": round(time.time() - t_start, 2)}


# ==========================================================================
# Housekeeping
# ==========================================================================
JUNK_DIRS = ("__pycache__", ".ipynb_checkpoints", ".pytest_cache")
JUNK_EXTS = (".pyc", ".pyo")
JUNK_NAMES = (".DS_Store", "Thumbs.db")


def housekeeping_scan(repo_root, outputs_dir, logs_dir, big_mb=25):
    """Find reclaimable clutter and the largest files, without deleting."""
    junk, big, empty = [], [], []
    total_junk = 0

    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for d in list(dirnames):
            if d in JUNK_DIRS:
                full = os.path.join(dirpath, d)
                size = _dir_size(full)
                junk.append({"path": full, "kind": "dir", "bytes": size,
                             "rel": _rel(full, repo_root)})
                total_junk += size
                dirnames.remove(d)     # do not descend into what we will delete
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            if name.endswith(JUNK_EXTS) or name in JUNK_NAMES:
                junk.append({"path": full, "kind": "file", "bytes": size,
                             "rel": _rel(full, repo_root)})
                total_junk += size
            elif size >= big_mb * 1024 * 1024:
                big.append({"path": full, "bytes": size,
                            "rel": _rel(full, repo_root)})

    # A zero-byte figure is the signature of an export that died mid-write.
    if os.path.isdir(outputs_dir):
        for dirpath, _dirs, filenames in os.walk(outputs_dir):
            for name in filenames:
                full = os.path.join(dirpath, name)
                try:
                    if os.path.getsize(full) == 0:
                        empty.append({"path": full, "bytes": 0,
                                      "rel": _rel(full, repo_root)})
                except OSError:
                    pass

    big.sort(key=lambda x: -x["bytes"])
    junk.sort(key=lambda x: -x["bytes"])
    return {
        "ok": True,
        "junk": junk[:400], "junk_bytes": total_junk, "junk_count": len(junk),
        "big": big[:60], "empty": empty[:60],
        "outputs_bytes": _dir_size(outputs_dir) if os.path.isdir(outputs_dir) else 0,
        "logs_bytes": _dir_size(logs_dir) if os.path.isdir(logs_dir) else 0,
        "free_bytes": _free_bytes(repo_root),
    }


def housekeeping_clean(paths, repo_root):
    """Delete only paths inside the repo that actually look like clutter.

    Deliberately paranoid: the alternative is a GUI button that can eat data.
    """
    removed, failed, freed = [], [], 0
    root = os.path.abspath(repo_root)
    for p in paths or []:
        full = os.path.abspath(p)
        if not full.startswith(root):
            failed.append({"path": p, "error": "Outside the repo."})
            continue
        name = os.path.basename(full)
        is_junk = (name in JUNK_DIRS or name in JUNK_NAMES
                   or name.endswith(JUNK_EXTS))
        try:
            is_empty = os.path.isfile(full) and os.path.getsize(full) == 0
        except OSError:
            is_empty = False
        if not (is_junk or is_empty):
            failed.append({"path": p,
                           "error": "Refusing: not recognized clutter."})
            continue
        try:
            size = _dir_size(full) if os.path.isdir(full) else os.path.getsize(full)
            if os.path.isdir(full):
                shutil.rmtree(full)
            else:
                os.remove(full)
            removed.append(full)
            freed += size
        except OSError as exc:
            failed.append({"path": p, "error": str(exc)})
    return {"ok": True, "removed": removed, "failed": failed, "freed": freed}


def _dir_size(path):
    total = 0
    for dirpath, _dirs, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total


def _rel(path, root):
    try:
        return os.path.relpath(path, root).replace("\\", "/")
    except ValueError:
        return path


def _free_bytes(path):
    try:
        return shutil.disk_usage(path).free
    except Exception:
        return 0


# ==========================================================================
# Scratch runner
# ==========================================================================
SCRATCH_PREAMBLE = (
    "# BARRY scratch. The repo and BARRY's own readers are importable, and\n"
    "# these names are already bound for you.\n"
    "import os, sys, glob, json, math\n"
    "import numpy as np\n"
)


def scratch_source(body, repo_root, app_dir):
    """Wrap a snippet so the repo and BARRY's backend are both importable."""
    header = ("import sys\n"
              "sys.path.insert(0, %r)\n"
              "sys.path.insert(0, %r)\n"
              "%s\n"
              "# ---------------- your code ----------------\n"
              % (repo_root, app_dir, SCRATCH_PREAMBLE))
    return header + (body or "")


# ==========================================================================
# CSV -- behind every "export this table" button
# ==========================================================================
def to_csv(rows, columns=None):
    """Render a list of dicts as CSV text with a stable column order."""
    rows = list(rows or [])
    if columns is None:
        columns = []
        for r in rows:
            for k in r:
                if k not in columns:
                    columns.append(k)
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore",
                       lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: _flat(r.get(k)) for k in columns})
    return buf.getvalue()


def _flat(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v)
    if isinstance(v, dict):
        return "; ".join("%s=%s" % (k, x) for k, x in v.items())
    return v


# ==========================================================================
# Request trace -- a rolling record of what the server was asked to do
# ==========================================================================
# This exists for the bug that leaves nothing behind: a panel that comes back
# blank, a click that does nothing, a number that is quietly wrong. None of
# those raise, so none of them reach the error log -- but the sequence of
# requests around them says exactly what happened.
class Trace:
    """A bounded, thread-safe ring of recent requests."""

    def __init__(self, limit=600):
        self.limit = limit
        self._items = []
        self._lock = threading.Lock()
        self.seq = 0

    def add(self, rec):
        with self._lock:
            self.seq += 1
            rec["n"] = self.seq
            self._items.append(rec)
            if len(self._items) > self.limit:
                del self._items[:len(self._items) - self.limit]

    def recent(self, limit=300, path=None, failed_only=False):
        with self._lock:
            items = list(self._items)
        if path:
            items = [x for x in items if path in x.get("path", "")]
        if failed_only:
            items = [x for x in items if x.get("status", 200) >= 400]
        return items[-limit:]

    def clear(self):
        with self._lock:
            self._items = []
            self.seq = 0


TRACE = Trace()

# Polled constantly and of no diagnostic value; recording them would push
# everything else out of the ring within seconds.
TRACE_SKIP = ("/api/link", "/api/job/", "/api/activity", "/api/debug",
              "/api/results/file", "/api/outputs/file", "/api/video/clip",
              "/api/video/frame")


def trace_worthy(path):
    return path.startswith("/api/") and not path.startswith(TRACE_SKIP)
