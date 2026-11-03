"""
answers.py -- a tool's full answer, on the lab's shelf on the cluster.

2026-10-30: "anything that has been processed by any device is accessible to
anyone without the need to reprocess the data. Even if it has not been
banked and simply ran." Incisor's and Doppler's summaries already travelled
(toolresults: committed and synced) but the full answer behind each -- every
channel's events, the snippets -- stayed in the .cache of the machine that
ran it, and Root Canal's reads too. Another machine could see that a
recording had been scanned and could not open the scan: "That scan is not on
this machine. Run it again", "This set has not been read at these settings
on this machine yet".

WHERE

The lab's shared space on the VACC (vacc.json `shared`, the folder uploads
already go to and every lab account can write), under `_answers/<tool>/`.
Not Supabase: these are megabytes each -- Root Canal's reads are 1 to 130 MB
-- and the database's allowance is measured in requests and a few GB
(memory: big payloads took it down). Not netfiles: Jarvis never writes
there. The shelf is scratch and can be purged; the machine that ran an
answer keeps its own copy, so a purge costs a re-run at worst and never the
only copy.

HOW

`share_soon` gzips one cache file and sends it, in the background, one at a
time; the file this machine wrote is always the one sent, so a run asked
again under the same key replaces the shelf's copy. `fetch` brings one down
into the place the tool reads its cache from, when the shelf has it. What is
on the shelf is one `ls` per tool, kept for two minutes, so a list of forty
sets costs one question and not forty. Nothing here runs without a signed-in
VACC account, or on the harness server, and nothing here ever raises into a
request: an answer the shelf cannot give is the old answer, "run it again".
"""
from __future__ import annotations

import base64
import gzip
import os
import queue
import threading
import time

from . import vacc

SHELF = "_answers"
LIST_TTL_S = 120.0

_logs = None
_share = False
_lock = threading.Lock()
_listed = {}            # tool -> (at, set(names))
_failed_at = {"t": 0.0}
_q = queue.Queue()
_queued = set()
_worker = None
_sent = {}              # (tool, name) -> size sent, this process


def configure(logs_dir, share=False):
    """`share`: this process is the app, which puts answers up and takes
    them down. Only the app does either -- the tools and checks that import
    it leave the shelf alone, as only the app syncs."""
    global _logs, _share
    _logs = logs_dir
    _share = bool(share)


def start_backfill(stores, delay_s=180.0):
    """Once, a few minutes after start: everything already in these caches
    that the shelf has not got. `stores` is [(tool, folder, suffix)]."""
    if not _share:
        return False

    def run():
        time.sleep(delay_s)
        for tool, folder, suffix in stores:
            try:
                backfill(tool, folder, suffix)
            except Exception:                            # noqa: BLE001
                pass

    threading.Thread(target=run, name="answers-backfill", daemon=True).start()
    return True


def _cfg():
    # Only the app itself reaches the shelf, either way. A check that moves
    # a read aside to test "read elsewhere" must not have it brought back.
    if not _logs or not _share or os.environ.get("BARRY_HARNESS_SERVER"):
        return None
    try:
        cfg = vacc.load_config(_logs)
    except Exception:                                    # noqa: BLE001
        return None
    shared = cfg.get("shared") or {}
    if not cfg.get("configured") or not shared.get("data_path"):
        return None
    return cfg


def _dir(cfg, tool):
    return vacc._remote_path(cfg["shared"]["data_path"], SHELF, tool)


def _down():
    """A failed connection is not asked again for a minute: a laptop away
    from the network must not spend every request on a timeout."""
    return time.time() - _failed_at["t"] < 60.0


def listing(tool, fresh=False):
    """The names on the shelf for one tool, or None when it cannot be asked."""
    with _lock:
        hit = _listed.get(tool)
    if hit and not fresh and time.time() - hit[0] < LIST_TTL_S:
        return hit[1]
    cfg = _cfg()
    if cfg is None or _down():
        return hit[1] if hit else None
    try:
        raw = vacc._ssh(cfg, "d=%s; [ -d \"$d\" ] && ls -1 \"$d\" || true"
                        % vacc.q(_dir(cfg, tool)), timeout=40)
    except Exception:                                    # noqa: BLE001
        _failed_at["t"] = time.time()
        return hit[1] if hit else None
    names = {ln.strip()[:-3] for ln in (raw or "").splitlines()
             if ln.strip().endswith(".gz")}
    with _lock:
        _listed[tool] = (time.time(), names)
    return names


def has(tool, name):
    got = listing(tool)
    return bool(got and name in got)


def fetch(tool, dest):
    """Bring the shelf's copy of `dest`'s file down to `dest`. True when it
    is there afterwards. Never raises."""
    name = os.path.basename(dest)
    if os.path.exists(dest):
        return True
    if not has(tool, name):
        return False
    cfg = _cfg()
    if cfg is None:
        return False
    try:
        path = vacc._remote_path(_dir(cfg, tool), name + ".gz")
        raw = vacc._ssh(cfg, "f=%s; if [ -f \"$f\" ]; then base64 -w0 \"$f\"; "
                        "else echo JARVIS_GONE; fi" % vacc.q(path),
                        timeout=900)
        if (raw or "").strip() == "JARVIS_GONE":
            with _lock:
                hit = _listed.get(tool)
                if hit:
                    hit[1].discard(name)
            return False
        body = gzip.decompress(base64.b64decode(raw.strip()))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".shelf.part"
        with open(tmp, "wb") as fh:
            fh.write(body)
        os.replace(tmp, dest)
        return True
    except Exception:                                    # noqa: BLE001
        _failed_at["t"] = time.time()
        return False


def _send(tool, path):
    cfg = _cfg()
    if cfg is None or not os.path.exists(path):
        return False
    name = os.path.basename(path)
    with open(path, "rb") as fh:
        body = gzip.compress(fh.read(), compresslevel=6)
    d = _dir(cfg, tool)
    final = vacc._remote_path(d, name + ".gz")
    part = vacc._remote_path(d, "." + name + ".gz.part")
    # Ten seconds a megabyte at the worst stream measured, and a minute on
    # top for the handshake (memory: VACC upload speed is per stream).
    vacc._ssh(cfg, "mkdir -p %s && cat > %s && mv -f %s %s"
              % (vacc.q(d), vacc.q(part), vacc.q(part), vacc.q(final)),
              stdin=body, timeout=60 + len(body) // 100000)
    with _lock:
        _sent[(tool, name)] = len(body)
        hit = _listed.get(tool)
        if hit:
            hit[1].add(name)
    return True


def _work():
    while True:
        tool, path = _q.get()
        try:
            if not _down():
                _send(tool, path)
        except Exception:                                # noqa: BLE001
            _failed_at["t"] = time.time()
        finally:
            with _lock:
                _queued.discard((tool, path))
            _q.task_done()


def share_soon(tool, path):
    """Put this cache file on the shelf, in the background. Never raises."""
    global _worker
    if not _share or _cfg() is None:
        return False
    with _lock:
        if (tool, path) in _queued:
            return True
        _queued.add((tool, path))
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, name="answers-shelf",
                                       daemon=True)
            _worker.start()
    _q.put((tool, path))
    return True


def backfill(tool, folder, suffix):
    """Every answer in `folder` that the shelf has not got, queued -- what
    makes the work already done on this machine reachable from the others,
    not only what is done from now on. Returns how many were queued."""
    names = listing(tool, fresh=True)
    if names is None:
        return 0
    n = 0
    try:
        files = sorted(os.listdir(folder))
    except OSError:
        return 0
    for f in files:
        if not f.endswith(suffix) or f.endswith(".part" + suffix) \
                or f in names:
            continue
        share_soon(tool, os.path.join(folder, f))
        n += 1
    return n


def status():
    with _lock:
        return {"queued": len(_queued),
                "sent": len(_sent),
                "sent_bytes": sum(_sent.values()),
                "listed": {t: len(v[1]) for t, v in _listed.items()},
                "down": _down()}
