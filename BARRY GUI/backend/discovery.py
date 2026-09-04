"""
discovery.py -- Walk a data root and find every recording session in it.

Point this at something like D:\\PTEN\\PTEN or a UVM netfiles share and it
returns a browsable tree grouped by cohort -> mouse -> session, with each
recording's identity, channel count and duration already resolved.

Two things make this usable on a network share:

  * Depth-limited and pruned. Once a folder is recognized as a recording it is
    never descended into -- a session with 64 CSC files is a leaf, not a
    directory to keep walking.
  * Cheap per session. Duration comes from the file size of one .ncs divided by
    the record size; nothing is read beyond a single 16 KB header.

Results are cached per root and returned incrementally so a slow share does not
freeze the UI.
"""
from __future__ import annotations

import os
import threading
import time

from . import ids, nlx

MAX_DEPTH = 6
MAX_SESSIONS = 4000

# Folders that never contain recordings; skipping them saves a lot of time on a
# share with analysis output mixed in.
SKIP_NAMES = {
    "pipeline output", "__pycache__", ".git", "$recycle.bin",
    "system volume information", ".ds_store", "node_modules",
    "figures", "figs", "analysis", "spss", ".trash", ".spotlight-v100",
}

_JOBS = {}
_LOCK = threading.Lock()


def _is_hidden(name):
    return name.startswith(".") or name.startswith("$")


def classify_folder(path, names=None):
    """Decide whether `path` is a recording, and describe what is in it."""
    if names is None:
        try:
            names = os.listdir(path)
        except OSError:
            return None

    ncs, mats, videos, nvts, events = [], [], [], [], []
    for n in names:
        low = n.lower()
        if low.endswith(".ncs") and low.startswith("csc"):
            ncs.append(n)
        elif low.endswith(".mat"):
            mats.append(n)
        elif low.endswith((".mpg", ".mpeg", ".avi", ".mp4", ".mkv", ".mov", ".wmv", ".m4v")):
            videos.append(n)
        elif low.endswith(".nvt"):
            nvts.append(n)
        elif low.endswith((".xlsx", ".xls")) or (low.endswith(".csv") and "ds_df" in low):
            events.append(n)

    if not ncs and not mats:
        return None

    return {"ncs": ncs, "mats": mats, "videos": videos, "nvts": nvts,
            "events": events}


# --------------------------------------------------------------------------
# Is this folder actually a recording?
# --------------------------------------------------------------------------
# Scanning the lab drives turned up seven folders of 64 files each, every one
# of them exactly 16384 bytes: a Neuralynx header and no data. Aborted
# acquisitions, registered as ordinary recordings, indistinguishable in the
# tree from a real session.
#
# The rig writes channels in banks of 32, so a count that is not a multiple of
# 32 means files are missing or something else is in the folder. Neither check
# deletes or hides anything -- a folder that fails is reported with the reason
# and kept out of the registry until somebody overrides it.
CHANNEL_BANK = 32
TINY_BYTES = 1_000_000


def assess(path, contents):
    """What is wrong with this folder, if anything.

    Returns a verdict and reasons in words. `ok` is not the same as `empty`:
    an empty folder is a real recording that failed, and saying so is more
    useful than pretending it is fine or pretending it is not there.
    """
    ncs = contents.get("ncs") or []
    loadable = nlx.list_csc_files(path, even_only=False)
    parts = nlx.csc_parts(path)

    n_named = len(ncs)
    n_loadable = len(loadable)
    unreadable = sorted(set(ncs) - {os.path.basename(p) for _n, p in loadable})
    split = {n: len(v) for n, v in parts.items() if len(v) > 1}

    empty, tiny, sizes = [], [], []
    for _num, p in loadable:
        recs = nlx.data_records(p)
        try:
            size = os.path.getsize(p)
        except OSError:
            size = 0
        sizes.append(size)
        if recs <= 0:
            empty.append(os.path.basename(p))
        elif size < TINY_BYTES:
            tiny.append(os.path.basename(p))

    reasons, verdict = [], "ok"
    if not n_loadable and contents.get("mats"):
        verdict = "ok"                    # a converted session; nothing to check
    elif not n_loadable:
        verdict = "reject"
        reasons.append("no CSC file here has a name the loader can read")
    elif empty and len(empty) == n_loadable:
        verdict = "empty"
        reasons.append(
            "every one of the %d channels is header-only -- %d bytes and no "
            "data records. The acquisition was started and never wrote "
            "anything." % (n_loadable, nlx.HEADER_BYTES))
    else:
        if empty:
            verdict = "suspect"
            reasons.append("%d of %d channels contain no data at all (%s%s)"
                           % (len(empty), n_loadable, ", ".join(empty[:4]),
                              "..." if len(empty) > 4 else ""))
        if tiny:
            verdict = "suspect"
            reasons.append(
                "%d channel(s) are under 1 MB, which is a few seconds at "
                "30 kHz (%s%s)" % (len(tiny), ", ".join(tiny[:4]),
                                   "..." if len(tiny) > 4 else ""))
        if n_loadable % CHANNEL_BANK:
            verdict = "suspect"
            reasons.append(
                "%d channels is not a multiple of %d -- the rig records in "
                "banks of %d, so files are probably missing"
                % (n_loadable, CHANNEL_BANK, CHANNEL_BANK))
        if unreadable:
            verdict = "suspect"
            reasons.append(
                "%d file(s) look like CSC data but are not named so the "
                "loader can read them (%s%s)"
                % (len(unreadable), ", ".join(unreadable[:3]),
                   "..." if len(unreadable) > 3 else ""))
    if split:
        reasons.append(
            "%d channel(s) are split across more than one file, which "
            "Cheetah does when acquisition restarts -- only the first part "
            "is loaded" % len(split))

    return {
        "verdict": verdict,
        "usable": verdict in ("ok", "suspect"),
        "reasons": reasons,
        "n_named": n_named,
        "n_loadable": n_loadable,
        "n_empty": len(empty),
        "n_tiny": len(tiny),
        "unreadable": unreadable[:12],
        "split": split,
        "bank_ok": (n_loadable % CHANNEL_BANK == 0) if n_loadable else None,
        "median_bytes": (sorted(sizes)[len(sizes) // 2] if sizes else 0),
    }


def describe_session(path, contents, read_header=True):
    """Build the full session record: identity + quick technical summary."""
    header_time, fs, n_ch, duration, adbv = None, None, 0, 0.0, None

    if contents["ncs"]:
        first = os.path.join(path, sorted(contents["ncs"])[0])
        n_ch = len(contents["ncs"])
        try:
            if read_header:
                hdr = nlx.read_header(first)
                header_time = nlx.header_start_time(hdr)
                fs = nlx._header_float(hdr, "SamplingFrequency")
                adbv = nlx._header_float(hdr, "ADBitVolts")
            size = os.path.getsize(first)
            n_rec = max(0, (size - nlx.HEADER_BYTES) // nlx.RECORD_DTYPE.itemsize)
            if fs:
                duration = n_rec * nlx.SAMPLES_PER_RECORD / fs
        except OSError:
            pass
    elif contents["mats"]:
        n_ch = 0

    identity = ids.identify(path, header_time=header_time)
    quality = assess(path, contents)
    return {
        "path": path,
        # Whether this folder is a recording worth registering, and why not.
        "quality": quality,
        "name": os.path.basename(path.rstrip("\\/")) or path,
        "identity": identity,
        "n_ncs": len(contents["ncs"]),
        "n_mat": len(contents["mats"]),
        "mats": sorted(contents["mats"])[:12],
        "videos": sorted(contents["videos"]),
        "nvts": sorted(contents["nvts"]),
        "event_files": sorted(contents["events"])[:12],
        "channels": n_ch,
        "fs": fs,
        "adbitvolts": adbv,
        "duration_s": duration,
        "has_video": bool(contents["videos"]),
        "has_tracking": bool(contents["nvts"]),
        "converted": bool(contents["mats"]),
    }


def scan(root, max_depth=MAX_DEPTH, progress=None, should_stop=None,
         read_headers=True):
    """Walk `root` and return every recording found beneath it."""
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise NotADirectoryError("Not a folder: " + root)

    sessions = []
    scanned = [0]

    def walk(path, depth):
        if len(sessions) >= MAX_SESSIONS:
            return
        if should_stop and should_stop():
            return
        if depth > max_depth:
            return
        try:
            names = os.listdir(path)
        except (OSError, PermissionError):
            return

        scanned[0] += 1
        if progress and scanned[0] % 25 == 0:
            progress(scanned[0], len(sessions), path)

        contents = classify_folder(path, names)
        if contents:
            try:
                sessions.append(describe_session(path, contents, read_headers))
            except Exception:
                pass
            return                       # a recording is a leaf -- stop here

        for n in names:
            if _is_hidden(n) or n.lower() in SKIP_NAMES:
                continue
            sub = os.path.join(path, n)
            if os.path.isdir(sub):
                walk(sub, depth + 1)

    walk(root, 0)
    sessions.sort(key=_sort_key)
    return sessions


def _sort_key(s):
    ident = s["identity"]
    return (
        (ident.get("group") or "~"),
        ident.get("mouse") if ident.get("mouse") is not None else 9999,
        ident.get("session") if ident.get("session") is not None else 9999,
        ident.get("start") or "",
    )


def group_sessions(sessions):
    """Nest a flat session list into cohort -> mouse -> sessions for the UI."""
    tree = {}
    for s in sessions:
        ident = s["identity"]
        g = ident.get("group") or "Ungrouped"
        mouse = ident.get("mouse")
        mkey = ("m%d" % mouse) if mouse is not None else (ident.get("mouse_folder") or "unknown")
        tree.setdefault(g, {})
        tree[g].setdefault(mkey, {
            "mouse": mouse,
            "label": mkey,
            "folder": ident.get("mouse_folder"),
            "sessions": [],
        })
        tree[g][mkey]["sessions"].append(s)

    out = []
    for g in sorted(tree.keys()):
        mice = []
        for mkey in sorted(tree[g].keys(),
                           key=lambda k: (tree[g][k]["mouse"] is None,
                                          tree[g][k]["mouse"] or 0, k)):
            m = tree[g][mkey]
            m["sessions"].sort(key=lambda s: (
                s["identity"].get("session") or 9999, s["identity"].get("start") or ""))
            m["n"] = len(m["sessions"])
            mice.append(m)
        out.append({"group": g, "mice": mice,
                    "n": sum(m["n"] for m in mice)})
    return out


# --------------------------------------------------------------------------
# Background scanning (a netfiles share can take a while)
# --------------------------------------------------------------------------
class ScanJob:
    def __init__(self, root, max_depth, read_headers):
        self.id = "scan_" + os.urandom(5).hex()
        self.root = root
        self.max_depth = max_depth
        self.read_headers = read_headers
        self.status = "running"
        self.started = time.time()
        self.ended = None
        self.scanned = 0
        self.found = 0
        self.current = ""
        self.error = None
        self.sessions = []
        self._stop = False

    def stop(self):
        self._stop = True

    def snapshot(self, include_sessions=False):
        data = {
            "id": self.id, "root": self.root, "status": self.status,
            "scanned": self.scanned, "found": self.found,
            "current": self.current, "error": self.error,
            "elapsed": round((self.ended or time.time()) - self.started, 1),
        }
        if include_sessions and self.status == "done":
            data["sessions"] = self.sessions
            data["tree"] = group_sessions(self.sessions)
        return data


def start_scan(root, max_depth=MAX_DEPTH, read_headers=True):
    job = ScanJob(root, max_depth, read_headers)

    def progress(scanned, found, current):
        job.scanned = scanned
        job.found = found
        job.current = current

    def run():
        try:
            job.sessions = scan(root, max_depth, progress,
                                lambda: job._stop, read_headers)
            job.found = len(job.sessions)
            job.status = "canceled" if job._stop else "done"
        except Exception as exc:
            job.status = "failed"
            job.error = "%s: %s" % (type(exc).__name__, exc)
        finally:
            job.ended = time.time()

    with _LOCK:
        _JOBS[job.id] = job
        for old in [j for j in _JOBS.values()
                    if j.status != "running" and (j.ended or 0) < time.time() - 3600]:
            _JOBS.pop(old.id, None)
    threading.Thread(target=run, daemon=True).start()
    return job


def get_scan(job_id):
    with _LOCK:
        return _JOBS.get(job_id)
