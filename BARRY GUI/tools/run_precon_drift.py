# -*- coding: utf-8 -*-
"""run_precon_drift.py -- DEWEY Precon1 -> Precon4, driven through Jarvis.

WHAT IT DOES
------------
The first real analysis through The Arc (plan: okay-time-for-a-fluffy-crescent;
contract: docs/the-arc-contracts.md section 7). Eight rats -- r3, r4, r6, r7,
r8, r9, r10, r11 (r5 has no Precon4 and no histology) -- two days each,
Precon1 and Precon4, the SPC run. Three stages, in order:

  spark     the transition check, and a re-bank of the 16 recordings: one read
            of every channel answers both the state and the transition
            clipping; the entry's existing decisions are carried (there are
            none by hand today: `excluded` equals `clipped`); a new bank
            version is minted and the old one kept.
  circuits  16 recordings x 2 pairings x {state, transition}, each run once
            for all three bands (theta, beta, low gamma: one read of the
            wires), each carrying `cue_role` + `role_source` from
            backend/cueroles.py; plus the rest circuits, 16 days x 3 bands.
  drifts    matched by rat, Hartung-Knapp, BH per band across windows and
            methods: per band x kind x role the raw Precon1 -> Precon4
            change, the cue - baseline contrast (state, transition), the
            food - no-food sanity check (state, transition), and the rest
            change.

ONE WRITER
----------
Everything goes through the user's RUNNING Jarvis over HTTP (discovered from
port 8733 upward, and checked to be serving THIS tree's GUI_logs), never
through a second process writing the bank or the artifact store. Each
artifact is in their Results the moment it is filed.

COST FIRST, RESUMABLE
---------------------
The cost is stated before anything runs, from the routes' own plans. A
recording whose bank entry is already transition-measured at 1.0 s / 2.0 s is
not re-banked; a circuit the plan says is current at these settings is not
re-run (and one that is re-run with every pair cached computes nothing and
CONFIRMS its version); a drift already filed from the same circuit versions is
not re-run. Every artifact id and version made is written to
docs/dewey-precon-drift.runlog.json as it lands.

    python tools\\run_precon_drift.py --dry-run          plan and cost only
    python tools\\run_precon_drift.py                     the whole thing
    python tools\\run_precon_drift.py --step circuits     one stage
    python tools\\run_precon_drift.py --base http://127.0.0.1:8733

Run it from PowerShell -- or from the Drift panel's "Precon1 -> Precon4"
tab, which starts this same script (backend/preconrun.py) with --yes and
--plan-json / --progress / --stop-file so it can state the cost, draw where
the run is, and stop it between items. Exit codes: 0 done, 1 some items did
not complete, 2 refused before anything ran, 3 stopped as asked, 5
stopped by an error (recorded as `crashed`; not carried on by itself), 4
interrupted -- Jarvis stopped answering or restarted (see JarvisGone); the
next Jarvis started by start.py carries it on by itself.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

LOGS = os.path.join(APP, "GUI_logs")
DOCS = os.path.join(APP, "docs")
RUNLOG_PATH = os.path.join(DOCS, "dewey-precon-drift.runlog.json")
RUNLOG_SCHEMA = "arc.precon-drift.runlog/1"

# --------------------------------------------------------------------------
# The design -- every decision in the plan's table, and nothing else
# --------------------------------------------------------------------------
PROJECT = "DEWEY"
RATS = (3, 4, 6, 7, 8, 9, 10, 11)
EXCLUDED_RATS = {5: "no Precon4 recording, and no histology row"}
DAYS = (1, 4)                        # Precon1 -> Precon4
DAY_LABEL = {1: "Precon1", 4: "Precon4"}
BAND_ORDER = ("theta", "beta", "gamma_low")        # contract 7.1
BAND_SAY = {"theta": "theta", "beta": "beta", "gamma_low": "low gamma"}
CUE_KINDS = ("state", "transition")
REST = "rest"
REST_CUE_TYPE = "none"                              # contract 7.3
ROLES = ("food", "no_food")
ROLE_SAY = {"food": "food pair", "no_food": "no-food pair"}
BEFORE_S, AFTER_S = 1.0, 2.0                        # transition windows
STATE_WINDOWS = ("pre", "cue1", "cue2", "post")
TRANSITION_WINDOWS = ("onset", "switch", "offset")
ALL_WINDOWS = STATE_WINDOWS + TRANSITION_WINDOWS
DRIFT_FIELDS = {"design": "matched", "test": "hk", "bh_scope": "artifact"}
STAGES = ("spark", "circuits", "drifts")

#: Seconds, used ONLY where no route has said: a transition plan refused
#: because the transition check has not run yet, a rest plan from a server
#: that cannot plan rest. Each is said as an estimate where it is used.
SPARK_S_PER_RECORDING = 25.0     # one read of 64 channels, both answers
PAIR_S = 7.5                     # one cue pair, all three bands (plan)
REST_EPOCH_S = 2.5               # one 10 s epoch, all three bands
DRIFT_S = 3.0                    # one drift, pooled and tested

POLL_S = 2.0
SAY_EVERY_S = 20.0


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(
        timespec="seconds")


def say(msg=""):
    print(msg, flush=True)


def say_s(s):
    if s is None:
        return "unknown"
    s = float(s)
    if s < 90:
        return "%d s" % max(1, int(round(s)))
    if s < 5400:
        return "%d min" % int(round(s / 60.0))
    return "%.1f h" % (s / 3600.0)


class Refused(Exception):
    """The run cannot go on, with a sentence for a person."""


class JarvisGone(Exception):
    """The Jarvis this run drives has stopped answering, or has restarted.
    Not an ApiError or a Refused on purpose: the per-item and per-stage
    handlers catch those and move on, and moving on without Jarvis would
    record every remaining item as failed. This ends the run instead (exit
    4, "interrupted"), and the next Jarvis to start carries it on
    (backend/preconrun.py) -- nothing filed is lost, and the item in flight
    is redone from its per-pair cache."""


#: How long Jarvis may be unreachable before the run gives it up. Long enough
#: for a busy moment; short enough that a Jarvis restarted by hand finds the
#: old run gone and starts its own.
GONE_S = 120.0
GONE_POLL_S = 5.0


# ==========================================================================
# HTTP
# ==========================================================================
class ApiError(Exception):
    def __init__(self, code, msg, body=None):
        super().__init__(msg)
        self.code = code
        self.body = body or {}


def _timed_out(exc):
    return isinstance(exc, (socket.timeout, TimeoutError)) or isinstance(
        getattr(exc, "reason", None), (socket.timeout, TimeoutError))


class Api(object):
    """JSON over HTTP to one Jarvis. No proxies: this is 127.0.0.1.

    `boot` is the `started_at` of the Jarvis this run drives. With it set, a
    request that cannot reach Jarvis is not simply a failed item: the run
    asks /api/health what happened. The same Jarvis, answering -- the one
    request is asked again. A different boot, or nothing for GONE_S --
    JarvisGone, and the run ends as interrupted."""

    def __init__(self, base, timeout=300.0, dry=False, boot=None):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.dry = dry
        self.boot = boot
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}))
        self.n = 0

    def health(self):
        """The `started_at` of whatever answers at base, or None."""
        req = urllib.request.Request(self.base + "/api/health",
                                     headers={"Accept": "application/json"})
        try:
            with self.opener.open(req, timeout=10.0) as r:
                got = json.loads(r.read().decode("utf-8", "replace")) or {}
            return str(got.get("started_at") or "")
        except urllib.error.HTTPError:
            return self.boot                  # it answered; that is enough
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def same_boot(self):
        """Raise JarvisGone unless the Jarvis at base is the one this run
        began with -- waiting up to GONE_S while nothing answers."""
        if self.boot is None:
            return
        t0 = time.time()
        said = False
        while True:
            b = self.health()
            if b is not None:
                if b != self.boot:
                    raise JarvisGone(
                        "Jarvis restarted (this run began with the Jarvis "
                        "started %s; the one answering now started %s). "
                        "This run stops so the new Jarvis can carry it on."
                        % (self.boot, b or "at an unknown time"))
                return
            if time.time() - t0 >= GONE_S:
                raise JarvisGone(
                    "Jarvis at %s has not answered for %s. This run stops; "
                    "the next Jarvis to start carries it on."
                    % (self.base, say_s(GONE_S)))
            if not said:
                say("      (Jarvis is not answering; waiting up to %s for it)"
                    % say_s(GONE_S))
                said = True
            time.sleep(GONE_POLL_S)

    def call(self, method, path, body=None, timeout=None, write=False):
        if write and self.dry:
            raise Refused("dry run: refusing to send %s %s" % (method, path))
        url = self.base + path
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method=method)
        for attempt in (1, 2, 3):
            self.n += 1
            try:
                with self.opener.open(req,
                                      timeout=timeout or self.timeout) as r:
                    raw = r.read()
                    code = r.status
                break
            except urllib.error.HTTPError as exc:
                raw = exc.read()
                code = exc.code
                break
            except (urllib.error.URLError, socket.timeout, OSError) as exc:
                if self.boot is None:
                    raise ApiError(0, "%s %s: %s" % (method, path, exc))
                # Jarvis gone or restarted: JarvisGone, out of every
                # handler. Still here: it was this one request.
                self.same_boot()
                if _timed_out(exc) or attempt == 3:
                    raise ApiError(0, "%s %s: %s" % (method, path, exc))
                say("      (%s %s was dropped by the same Jarvis; asking "
                    "again)" % (method, path))
        try:
            got = json.loads(raw.decode("utf-8", "replace")) if raw else {}
        except ValueError:
            got = {"ok": False, "error": raw[:300].decode("utf-8", "replace")}
        if code >= 400 or (isinstance(got, dict) and got.get("ok") is False):
            raise ApiError(code, (got or {}).get("error")
                           or "HTTP %d on %s" % (code, path), got)
        return got

    def get(self, path, **kw):
        return self.call("GET", path, **kw)

    def post(self, path, body=None, write=True, **kw):
        """`write=False` for the read-only POSTs (plans, checks)."""
        return self.call("POST", path, body or {}, write=write, **kw)


def q(s):
    return urllib.parse.quote(str(s), safe="")


def discover(base=None, first=8733, span=40):
    """The Jarvis serving THIS tree: /api/health answers and its `logs` is
    our GUI_logs. A server for another clone is not ours to write to."""
    want = os.path.normcase(os.path.normpath(LOGS))
    tried = []
    bases = [base] if base else ["http://127.0.0.1:%d" % p
                                 for p in range(first, first + span)]
    for b in bases:
        api = Api(b, timeout=6.0)
        try:
            h = api.get("/api/health")
        except ApiError as exc:
            if base:
                raise Refused("No Jarvis answers at %s (%s)." % (b, exc))
            continue
        logs = os.path.normcase(os.path.normpath(str(h.get("logs") or "")))
        if logs != want:
            tried.append("%s serves %s" % (b, h.get("logs")))
            continue
        return b, h
    raise Refused("No running Jarvis serves %s (%s). Start Jarvis, or say "
                  "--base." % (LOGS, "; ".join(tried) or
                               "nothing answered on %d-%d"
                               % (first, first + span - 1)))


def wait_job(api, job_id, label, timeout_s=6 * 3600):
    """Poll /api/cfc/job/<id> until it ends; return /api/cfc/result."""
    t0 = time.time()
    last = 0.0
    while True:
        try:
            snap = api.get("/api/cfc/job/%s" % q(job_id))["job"]
        except ApiError as exc:
            if exc.code == 404:
                api.same_boot()     # a job this Jarvis never had: restarted
            raise
        st = snap.get("status")
        if st != "running":
            break
        if time.time() - last >= SAY_EVERY_S:
            last = time.time()
            mem = snap.get("members") or []
            done = sum(1 for m in mem if m.get("status") in
                       ("done", "cached"))
            say("      ... %s: %s, %s elapsed%s" % (
                label, snap.get("stage") or "running",
                say_s(snap.get("elapsed")),
                (", %d of %d pairs" % (done, len(mem))) if mem else ""))
        if time.time() - t0 > timeout_s:
            raise Refused("%s has run for %s; stopped waiting (job %s is "
                          "still running in Jarvis)." % (
                              label, say_s(time.time() - t0), job_id))
        time.sleep(POLL_S)
    if st != "done":
        raise ApiError(409, "%s %s: %s" % (label, st, snap.get("error")
                                           or "no reason given"), snap)
    return api.get("/api/cfc/result/%s" % q(job_id))["result"], snap


# ==========================================================================
# The run log
# ==========================================================================
class RunLog(object):
    """docs/dewey-precon-drift.runlog.json -- written after every artifact,
    atomically and flushed to the disk, so an interrupted run -- a process
    killed, a computer switched off -- leaves a true record of what landed.

    The one before each write is kept as `<path>.bak`. A file that cannot be
    read (a power cut on a disk that lied about flushing) is set aside, not
    deleted, and the .bak read instead. If neither reads, the run starts a
    fresh log: nothing is lost by that but the log itself, because the
    circuits stage records every circuit it finds current and the drifts
    stage re-files each drift from them (the same answer confirms, it does
    not add a version)."""

    def __init__(self, path, dry=False):
        self.path = path
        self.dry = dry
        self.data = None
        self.recovered = None
        for src in (path, path + ".bak"):
            if not os.path.exists(src):
                continue
            try:
                with open(src, "r", encoding="utf-8") as fh:
                    got = json.load(fh)
                if not isinstance(got, dict):
                    raise ValueError("not an object")
            except (OSError, ValueError) as exc:
                aside = "%s.unreadable-%s" % (src, time.strftime(
                    "%Y%m%d-%H%M%S"))
                if not dry:
                    try:
                        os.replace(src, aside)
                    except OSError:
                        pass
                self.recovered = ("%s could not be read (%s); set aside as "
                                  "%s" % (os.path.basename(src), exc,
                                          os.path.basename(aside)))
                continue
            self.data = got
            if src != path:
                self.recovered = (self.recovered or "") + (
                    "; read the copy before it (%s)" % os.path.basename(src))
            break
        if not self.data:
            self.data = {"schema": RUNLOG_SCHEMA, "created": now(),
                         "spark": {}, "circuits": {}, "drifts": {},
                         "events": []}
        for k in ("spark", "circuits", "drifts"):
            self.data.setdefault(k, {})
        self.data.setdefault("events", [])
        if self.recovered:
            say("  note: the run log " + self.recovered.lstrip("; "))
            self.data["events"].append({"at": now(), "stage": "run",
                                        "msg": "run log " + self.recovered})

    def __getitem__(self, k):
        return self.data[k]

    def event(self, stage, msg):
        self.data["events"].append({"at": now(), "stage": stage,
                                    "msg": msg})
        self.save()

    def save(self):
        if self.dry:
            return
        self.data["updated"] = now()
        if os.path.exists(self.path):
            try:
                shutil.copyfile(self.path, self.path + ".bak")
            except OSError:
                pass
        write_json(self.path, self.data)


def write_json(path, data):
    """Atomically and to the disk: a sibling written and fsync'd, then
    renamed over the target. Without the fsync the rename can reach the
    disk before the bytes do, and a power cut brings the file back empty
    (backend/shards.py `_write_json` says the same)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    replace_patiently(tmp, path)


#: How long a rename waits for a reader to let go of the target.
REPLACE_WAIT_S = 3.0


def replace_patiently(tmp, path):
    """os.replace, waiting for a reader. On Windows a file another process
    has open cannot be replaced ("Access is denied"), and Jarvis reads
    progress.json and the run log every two seconds while the Drift panel
    watches: the 2026-09-30 run died of exactly that, in the drifts stage.
    A reader holds the file for a millisecond, so this retries for up to
    REPLACE_WAIT_S and only then gives up."""
    t0 = time.time()
    while True:
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if time.time() - t0 >= REPLACE_WAIT_S:
                raise
            time.sleep(0.05)


# ==========================================================================
# Where a run is, and asking it to stop -- for the Drift panel
# ==========================================================================
class Progress(object):
    """--progress PATH: which stage, which item, and how many of each stage
    are done, already current, or failed. Rewritten at every item for the
    Drift panel to draw (backend/preconrun.py); the run log stays the record.
    Without a path it is a no-op.

    An item is opened by `item()` and settled by the next `item()` or by
    `settle()`: failed if the stage's failure count grew while it was open,
    otherwise whatever `outcome()` said (default done)."""

    def __init__(self, path=None):
        self.path = path
        self.open = None
        self.data = {"schema": "arc.precon-drift.progress/1",
                     "started": now(), "pid": os.getpid(), "stage": None,
                     "item": None, "stages": {}, "stopped": None,
                     "finished": None}

    def stage(self, name, of):
        self.settle()
        self.data["stage"] = name
        self.data["item"] = None
        self.data["stages"][name] = {"of": of, "done": 0, "already": 0,
                                     "failed": 0, "started": now(),
                                     "ended": None}
        self.save()

    def item(self, n, tag, nfail=0):
        self.settle(nfail)
        self.open = {"nfail": nfail, "outcome": "done"}
        self.data["item"] = {"n": n, "tag": tag, "at": now()}
        self.save()

    def outcome(self, what):
        if self.open is not None:
            self.open["outcome"] = what

    def settle(self, nfail=None, force=None):
        if self.open is None:
            return
        s = self.data["stages"].get(self.data["stage"])
        what = force or ("failed" if nfail is not None and
                         nfail > self.open["nfail"] else self.open["outcome"])
        self.open = None
        if s is not None:
            s[what] = s.get(what, 0) + 1
        self.save()

    def end_stage(self, nfail=None):
        self.settle(nfail)
        s = self.data["stages"].get(self.data["stage"])
        if s is not None:
            s["ended"] = now()
        self.data["item"] = None
        self.save()

    def save(self):
        """Never fatal: this file is for the panel to draw, and a run that
        died because the panel was looking at it has happened once."""
        if self.path:
            self.data["updated"] = now()
            try:
                write_json(self.path, self.data)
            except OSError as exc:
                if not getattr(self, "_said", False):
                    say("      (could not update %s: %s; the run goes on)"
                        % (os.path.basename(self.path), exc))
                    self._said = True


PROG = Progress(None)
STOP_FILE = None


def stop_asked(stage, tag, log):
    """--stop-file PATH exists: stop before the next item, so nothing is left
    half-filed. The item in flight has finished and been recorded."""
    if not (STOP_FILE and os.path.exists(STOP_FILE)):
        return False
    say("  stopped, as asked, before %s" % tag)
    log.event(stage, "stopped, as asked, before %s" % tag)
    PROG.data["stopped"] = now()
    PROG.save()
    return True


# ==========================================================================
# Keys and names
# ==========================================================================
def circuit_key(gid, cue_type, kind, band):
    return "%s|%s|%s|%s" % (gid, cue_type, kind, band)


def drift_key(band, kind, role, contrast):
    return "%s|%s|%s|%s" % (band, kind, role or "-", contrast or "raw")


def drift_nickname(band, kind, role, contrast):
    head = "Precon1\u21924 \u00b7 %s \u00b7 " % BAND_SAY[band]
    if kind == REST:
        return head + "rest (FP1+FP2)"
    if contrast == "roles":
        return head + "%s \u00b7 food \u2212 no-food (sanity)" % kind
    nick = head + "%s \u00b7 %s" % (kind, ROLE_SAY[role])
    if contrast == "baseline":
        nick += " \u00b7 cue \u2212 baseline"
    return nick


def drift_plan():
    """Every drift this analysis files, in the order it files them."""
    out = []
    for band in BAND_ORDER:
        for kind in CUE_KINDS:
            for role in ROLES:
                out.append((band, kind, role, None))
                out.append((band, kind, role, "baseline"))
            out.append((band, kind, None, "roles"))
        out.append((band, REST, None, None))
    return out


# ==========================================================================
# What is there: recordings, roles, bank entries
# ==========================================================================
def select_recordings(api, rats=RATS):
    """The 16 recordings: one banked Precon1 and Precon4 SPC per rat."""
    rows = api.get("/api/arc/circuit/recordings", timeout=600)["rows"]
    got, problems = {}, []
    for r in rows:
        if r.get("mouse") not in rats or r.get("phase") != "Precon":
            continue
        if r.get("phase_n") not in DAYS or (r.get("run") or "SPC") != "SPC":
            continue
        if not r.get("banked"):
            continue
        key = (r["mouse"], r["phase_n"])
        if key in got:
            problems.append("r%d %s has two banked SPC recordings (%s, %s)"
                            % (key[0], DAY_LABEL[key[1]], got[key]["gid"],
                               r["gid"]))
            continue
        got[key] = r
    for rat in rats:
        for day in DAYS:
            if (rat, day) not in got:
                problems.append("r%d %s: no banked SPC recording"
                                % (rat, DAY_LABEL[day]))
    if problems:
        raise Refused("The recordings are not the 16 the plan names: "
                      + "; ".join(problems) + ".")
    return got


def read_roles(recs, rats=RATS):
    """cueroles.role_table per rat, checked against the pairings banked."""
    from backend import cueroles
    records = cueroles.load_records()
    out = {}
    for rat in rats:
        banked = []
        for day in DAYS:
            for t in recs[(rat, day)].get("cue_types") or []:
                if t["cue_type"] not in banked:
                    banked.append(t["cue_type"])
        try:
            tab = cueroles.role_table(rat, records, pairings=banked)
        except cueroles.CueRoleError as exc:
            raise Refused("r%d: %s" % (rat, exc))
        if sorted(tab["roles"].values()) != ["food", "no_food"]:
            raise Refused("r%d's banked pairings are %s -- not one food and "
                          "one no-food pair." % (rat, tab["roles"]))
        for day in DAYS:
            have = [t["cue_type"] for t in recs[(rat, day)].get("cue_types")
                    or []]
            if sorted(have) != sorted(tab["roles"]):
                raise Refused("r%d %s holds %s, not the rat's two pairings "
                              "%s." % (rat, DAY_LABEL[day], have,
                                       sorted(tab["roles"])))
        tab["role_source"] = cueroles.role_source(tab)
        out[rat] = tab
    return out


def bank_entry(api, entry_id):
    return api.get("/api/bank/%s" % q(entry_id))["entry"]


def transition_done(entry):
    p = ((entry or {}).get("source") or {}).get("parameters") or {}
    return (p.get("transition_measured") is True
            and _same(p.get("transition_before_s"), BEFORE_S)
            and _same(p.get("transition_after_s"), AFTER_S))


def _same(a, b):
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return False


# ==========================================================================
# Stage 1: Spark -- the transition check and the re-bank
# ==========================================================================
def _as_windows(x):
    """An exclusion in either bank shape -> {window: set(csc)}. A flat list
    is "every window", which is what it has always meant."""
    if isinstance(x, dict):
        return {str(w): {int(c) for c in (v or [])} for w, v in x.items()}
    if x:
        return {w: {int(c) for c in x} for w in ALL_WINDOWS}
    return {}


def hand_decisions(ev):
    """What a person decided on this banked event, apart from the
    measurement: channels excluded that the measurement did not clip, and
    blocks kept against it."""
    clipped = _as_windows(ev.get("clipped"))
    excluded = _as_windows(ev.get("excluded"))
    added = {}
    for w, chans in excluded.items():
        extra = chans - clipped.get(w, set())
        if extra:
            added[w] = sorted(extra)
    kept = ev.get("kept") or None
    return added, kept


def measured_exclusion(pairs, clipping):
    """`exclusionBoth` of web/js/arc.js, in Python: the state answer and
    (only when measured) the transition answer, per pair, per window."""
    out = {}
    t = (clipping or {}).get("transition") or {}
    for by in ((clipping or {}).get("by_pair") or {},
               (t.get("by_pair") or {}) if t.get("measured") else {}):
        for p in pairs:
            pid = str(p["pair_id"])
            bad = by.get(pid)
            if not bad:
                continue
            per = out.setdefault(pid, {})
            for csc, d in bad.items():
                for w in (d or {}).get("windows") or []:
                    per.setdefault(w, set()).add(int(csc))
    return {pid: {w: sorted(c) for w, c in per.items()}
            for pid, per in out.items() if per}


def _blocks(excl, windows):
    return sum(len(v) for per in excl.values() for w, v in per.items()
               if w in windows)


def spark_plan(api, recs):
    """Per recording: done, todo, or blocked with the reason."""
    banked = api.get("/api/arc/spark/recordings", timeout=600)["banked"]
    out = []
    for (rat, day), r in sorted(recs.items()):
        gid = r["gid"]
        reads = (r.get("bank") or {}).get("entry")
        entry = bank_entry(api, reads) if reads else None
        into = (banked.get(gid) or {}).get("id")
        row = {"gid": gid, "rat": rat, "day": day, "label": r.get("label"),
               "entry": reads, "version": (entry or {}).get("version"),
               "reachable": bool(r.get("reachable"))}
        if entry and transition_done(entry):
            row["state"] = "done"
            row["why"] = ("already transition-measured at %.1f s / %.1f s "
                          "(bank v%s)" % (BEFORE_S, AFTER_S,
                                          entry.get("version")))
        elif not r.get("reachable"):
            row["state"] = "blocked"
            row["why"] = "not reachable from this machine"
        elif into and reads and into != reads:
            # Two Spark entries for one recording. The bank route would add
            # the new version to one, Circuit reads the other: the transition
            # circuits would then be refused as unmeasured.
            row["state"] = "blocked"
            row["why"] = ("two Spark entries for one recording: Spark would "
                          "re-bank into %s (v%s) but Circuit reads %s (v%s). "
                          "Resolve the duplicate first."
                          % (into, (banked.get(gid) or {}).get("version"),
                             reads, (entry or {}).get("version")))
        else:
            row["state"] = "todo"
            added = sum(1 for ev in (entry or {}).get("events") or []
                        if any(hand_decisions(ev)))
            row["hand"] = added
        out.append(row)
    return out


def _spark_one(api, row, log, tag):
    """One recording's transition check and re-bank. Refusals are said
    and recorded here; a route that errors raises ApiError, which the
    stage turns into this recording's failure and goes on."""
    gid = row["gid"]
    t0 = time.time()
    old = bank_entry(api, row["entry"])
    read = api.get("/api/arc/spark/%s" % q(gid), timeout=600)
    pairs = read.get("pairs") or []
    # Match old events to the new reading by time: the bank identifies
    # an event by when it is, not by its position.
    by_t = {round(float(ev.get("start")), 3): ev
            for ev in old.get("events") or []}
    hand, kept, carried = {}, {}, 0
    unmatched = []
    for p in pairs:
        ev = by_t.get(round(float(p["opener_t"]), 3))
        if ev is None:
            unmatched.append(p["pair_id"])
            continue
        add, keep = hand_decisions(ev)
        if add:
            hand[str(p["pair_id"])] = add
            carried += 1
        if keep:
            kept[str(p["pair_id"])] = keep
            carried += 1
    n_hand_old = sum(1 for ev in old.get("events") or []
                     if any(hand_decisions(ev)))
    # The reading must BE the banked cue pairs. A different count, or pairs
    # at other times, is a different recording read under this gid (the
    # registry once handed Spark an FP folder) -- never re-banked over it.
    n_old = len(old.get("events") or [])
    if unmatched or len(pairs) != n_old:
        why = ("the reading is not the banked cue pairs (%d read, %d banked"
               "%s) -- nothing was re-banked" % (
                   len(pairs), n_old,
                   ", %d at other times" % len(unmatched) if unmatched
                   else ""))
        PROG.outcome("failed")
        say("  ! %s: %s" % (tag, why))
        log["spark"][gid] = {"status": "failed", "why": why,
                             "path": read.get("path")}
        log.event("spark", "%s: %s" % (tag, why))
        return
    if unmatched and n_hand_old:
        why = ("the reading's cue pairs no longer match the banked ones "
               "(pairs %s) and the entry holds %d hand decision(s) that "
               "could not be carried" % (unmatched, n_hand_old))
        PROG.outcome("failed")
        say("  ! %s: %s" % (tag, why))
        log["spark"][gid] = {"status": "blocked", "why": why}
        log.event("spark", "%s: %s" % (tag, why))
        return
    clip = api.post("/api/arc/spark/%s/clipping" % q(gid),
                    {"before_s": BEFORE_S, "after_s": AFTER_S},
                    write=False, timeout=1800)
    if not (clip.get("transition") or {}).get("measured"):
        why = ("the transition windows could not be measured (%s)"
               % ((clip.get("transition") or {}).get("why")
                  or "no reason given"))
        PROG.outcome("failed")
        say("  ! %s: %s" % (tag, why))
        log["spark"][gid] = {"status": "failed", "why": why}
        log.event("spark", "%s: %s" % (tag, why))
        return
    excl = measured_exclusion(pairs, clip)
    for pid, per in hand.items():
        mine = excl.setdefault(pid, {})
        for w, chans in per.items():
            mine[w] = sorted(set(mine.get(w) or []) | set(chans))
    body = {"excluded": excl}
    if kept:
        body["kept"] = kept
    if old.get("name"):
        body["name"] = old["name"]
    made = api.post("/api/arc/spark/%s/bank" % q(gid), body,
                    timeout=600)
    ent = made.get("entry") or {}
    rec = {"status": "banked", "entry": ent.get("id"),
           "version_before": old.get("version"),
           "version_after": ent.get("version"),
           "n_pairs": made.get("n"),
           "blocks_state": _blocks(excl, STATE_WINDOWS),
           "blocks_transition": _blocks(excl, TRANSITION_WINDOWS),
           "hand_decisions_carried": carried,
           "unmatched_pairs": unmatched,
           "read_seconds": (clip.get("read") or {}).get("seconds"),
           "seconds": round(time.time() - t0, 1), "at": now()}
    if ent.get("id") != row["entry"]:
        rec["status"] = "split"
        rec["why"] = ("banked into %s, but Circuit reads %s"
                      % (ent.get("id"), row["entry"]))
        PROG.outcome("failed")
        log.event("spark", "%s: %s" % (tag, rec["why"]))
    # What the bank kept, read back: the events AND the entry's word that
    # the transition windows were measured, which is what Circuit reads.
    # On 2026-09-30 the bank kept the first but not the second and all 80
    # circuits were refused -- found only after seven minutes of measuring.
    back = bank_entry(api, ent.get("id") or row["entry"]) or {}
    if not transition_done(back):
        rec["status"] = "not_kept"
        rec["why"] = ("banked, but the entry does not say its transition "
                      "windows were measured (transition_measured=%r)"
                      % (((back.get("source") or {}).get("parameters")
                          or {}).get("transition_measured"),))
        log["spark"][gid] = rec
        log.event("spark", "%s: %s" % (tag, rec["why"]))
        raise Refused("%s: %s. Stopping the Spark stage: every recording "
                      "would go the same way." % (tag, rec["why"]))
    log["spark"][gid] = rec
    log.save()
    say("  + %s: bank v%s -> v%s, %d pairs, %d state + %d transition "
        "blocks excluded, %d hand decision(s) carried, %s" % (
            tag, rec["version_before"], rec["version_after"],
            rec["n_pairs"] or 0, rec["blocks_state"],
            rec["blocks_transition"], carried, say_s(rec["seconds"])))


def run_spark(api, plan, log, only=None):
    say("")
    say("STAGE 1 -- Spark: transition check and re-bank")
    rows = [r for r in plan if not only or r["gid"] in only]
    PROG.stage("spark", len(rows))
    for n, row in enumerate(rows, start=1):
        gid = row["gid"]
        tag = "r%d %s (%s)" % (row["rat"], DAY_LABEL[row["day"]], gid)
        if stop_asked("spark", tag, log):
            break
        api.same_boot()     # a Jarvis restarted between items ends the run
        PROG.item(n, tag)
        if row["state"] == "done":
            PROG.outcome("already")
            say("  = %s: %s" % (tag, row["why"]))
            log["spark"].setdefault(gid, {"status": "done", "why": row["why"],
                                          "entry": row["entry"],
                                          "version_after": row["version"]})
            log.save()
            continue
        if row["state"] == "blocked":
            PROG.outcome("failed")
            say("  ! %s: %s" % (tag, row["why"]))
            log["spark"][gid] = {"status": "blocked", "why": row["why"]}
            log.event("spark", "%s: %s" % (tag, row["why"]))
            continue
        try:
            _spark_one(api, row, log, tag)
        except ApiError as exc:
            # This recording, not the stage: the others are unaffected.
            PROG.outcome("failed")
            why = str(exc)
            say("  ! %s: %s" % (tag, why))
            log["spark"][gid] = {"status": "failed", "why": why}
            log.event("spark", "%s: %s" % (tag, why))
    PROG.end_stage()
    # What Circuit now reads, which is the only check that matters.
    rows = {r["gid"]: r for r in api.get("/api/arc/circuit/recordings",
                                         timeout=600)["rows"]}
    bad = []
    for row in plan:
        if only and row["gid"] not in only:
            continue
        r = rows.get(row["gid"]) or {}
        if not r.get("transition_measured"):
            bad.append("r%d %s" % (row["rat"], DAY_LABEL[row["day"]]))
    if bad:
        log.event("spark", "Circuit still reads no transition measurement "
                  "for: " + ", ".join(bad))
        say("  ! Circuit still reads no transition measurement for: "
            + ", ".join(bad))
    return bad


# ==========================================================================
# Stage 2: circuits
# ==========================================================================
def circuit_items(recs, roles, kinds=CUE_KINDS + (REST,), rats=RATS,
                  gids=None, role_only=None):
    """One item per RUN (every band in one run): (gid, cue_type, kind)."""
    out = []
    for kind in kinds:
        for rat in rats:
            for day in DAYS:
                r = recs[(rat, day)]
                if gids and r["gid"] not in gids:
                    continue
                if kind == REST:
                    out.append({"gid": r["gid"], "rat": rat, "day": day,
                                "label": r.get("label"),
                                "cue_type": REST_CUE_TYPE, "kind": REST,
                                "cue_role": None, "n_pairs": None})
                    continue
                for t in r.get("cue_types") or []:
                    role = roles[rat]["roles"][t["cue_type"]]
                    if role_only and role != role_only:
                        continue
                    out.append({"gid": r["gid"], "rat": rat, "day": day,
                                "label": r.get("label"),
                                "cue_type": t["cue_type"], "kind": kind,
                                "cue_role": role,
                                "n_pairs": t.get("n_pairs")})
    return out


def run_body(item, roles, bands, nickname=None):
    body = {"cue_type": item["cue_type"], "kind": item["kind"],
            "params": {}, "where": "local", "bands": list(bands)}
    if item["cue_role"]:
        body["cue_role"] = item["cue_role"]
        body["role_source"] = roles[item["rat"]]["role_source"]
    if nickname:
        body["nickname"] = nickname
    return body


def _plan_artifacts(plan):
    """The plan's artifact(s), whatever shape a banded plan answers in:
    `artifact` (one), `artifacts` (a list or a {band: ...} dict)."""
    arts = plan.get("artifacts")
    if isinstance(arts, dict):
        return [dict(v or {}, band=v.get("band") if isinstance(v, dict)
                     and v.get("band") else b) for b, v in arts.items()]
    if isinstance(arts, list):
        return [a or {} for a in arts]
    one = plan.get("artifact")
    return [one] if one else []


def plan_circuit(api, item, roles, bands):
    """The route's own plan for one run; an estimate (said) when refused."""
    body = run_body(item, roles, bands)
    body.pop("where")
    try:
        got = api.post("/api/arc/circuit/%s/plan" % q(item["gid"]), body,
                       write=False, timeout=600)
    except ApiError as exc:
        return {"refused": True, "why": str(exc), "code": exc.code}
    arts = _plan_artifacts(got)
    current = (len(arts) >= len(bands)
               and all(a and a.get("current") for a in arts))
    return {"refused": False, "n_pairs": got.get("n_pairs"),
            "n_cached": got.get("n_cached"),
            "local_s": (got.get("cost") or {}).get("local_s"),
            "sentence": (got.get("cost") or {}).get("sentence"),
            "current": current, "artifacts": arts,
            "bank": got.get("bank"), "run_params": got.get("run_params")}


def list_circuits(api, gid):
    return api.get("/api/artifacts?kind=circuit&gid=%s" % q(gid),
                   timeout=300)["artifacts"]


def _band_of(subj):
    return subj.get("band") or ((subj.get("params") or {}).get("band"))


def filed_for(arts, item, band):
    """The live circuit artifact for (gid, cue type, kind, band)."""
    hits = []
    for a in arts:
        s = a.get("subject") or {}
        if s.get("gid") != item["gid"]:
            continue
        if (s.get("window_kind") or s.get("kind")) != item["kind"]:
            continue
        if item["kind"] != REST and s.get("cue_type") != item["cue_type"]:
            continue
        if _band_of(s) != band:
            continue
        hits.append(a)
    hits.sort(key=lambda a: ((a.get("added") or {}).get("at") or "",
                             a.get("id") or ""))
    return hits[0] if hits else None


def run_circuits(api, items, roles, bands, log, recs, allow_unmeasured=False):
    say("")
    say("STAGE 2 -- circuits (%d runs, %d bands each)"
        % (len(items), len(bands)))
    tm = {r["gid"]: bool(r.get("transition_measured"))
          for r in api.get("/api/arc/circuit/recordings", timeout=600)["rows"]}
    before_ids = {}
    failures = []
    PROG.stage("circuits", len(items))
    for n, item in enumerate(items, start=1):
        gid = item["gid"]
        tag = "[%d/%d] r%d %s %s %s" % (
            n, len(items), item["rat"], DAY_LABEL[item["day"]], item["kind"],
            item["cue_type"] if item["kind"] != REST else "(FP1+FP2)")
        if item["cue_role"]:
            tag += " (%s)" % ROLE_SAY[item["cue_role"]]
        if stop_asked("circuits", tag, log):
            break
        api.same_boot()     # a Jarvis restarted between items ends the run
        PROG.item(n, tag, len(failures))
        # Order: circuits are made against the re-banked entry, never the
        # one Spark is about to replace -- or their inputs are stale on
        # arrival.
        if not tm.get(gid) and not allow_unmeasured:
            why = ("the Spark stage has not re-banked this recording "
                   "(Circuit reads no transition measurement)")
            say("  ! %s: %s" % (tag, why))
            failures.append((tag, why))
            continue
        if gid not in before_ids:
            before_ids[gid] = {a["id"] for a in list_circuits(api, gid)}
        pl = plan_circuit(api, item, roles, bands)
        if pl.get("refused"):
            say("  ! %s: the plan refused: %s" % (tag, pl["why"]))
            failures.append((tag, pl["why"]))
            log.event("circuits", "%s: plan refused: %s" % (tag, pl["why"]))
            continue
        t0 = time.time()
        if pl["current"]:
            PROG.outcome("already")
            say("  = %s: already current at these settings" % tag)
            result, new_any = None, False
        else:
            say("  > %s: %s" % (tag, pl.get("sentence") or ""))
            try:
                started = api.post("/api/arc/circuit/%s/run" % q(gid),
                                   run_body(item, roles, bands), timeout=600)
                result, _snap = wait_job(api, started["job"], tag)
            except (ApiError, Refused) as exc:
                say("  ! %s: %s" % (tag, exc))
                failures.append((tag, str(exc)))
                log.event("circuits", "%s: %s" % (tag, exc))
                continue
            new_any = None
        arts = list_circuits(api, gid)
        for band in bands:
            a = filed_for(arts, item, band)
            key = circuit_key(gid, item["cue_type"], item["kind"], band)
            if not a:
                why = ("no %s circuit was filed for band %s" % (item["kind"],
                                                               band))
                say("  ! %s: %s" % (tag, why))
                failures.append((tag, why))
                log.event("circuits", "%s: %s" % (tag, why))
                continue
            cur = a.get("current") or {}
            subj = a.get("subject") or {}
            rec = {"gid": gid, "rat": item["rat"], "day": item["day"],
                   "day_label": DAY_LABEL[item["day"]],
                   "cue_type": item["cue_type"], "kind": item["kind"],
                   "band": band, "cue_role": item["cue_role"],
                   "artifact_id": a["id"], "version": a.get("version"),
                   "version_id": cur.get("id"), "digest": cur.get("digest"),
                   "name": a.get("name"), "nickname": a.get("nickname"),
                   "created_by_this_run": a["id"] not in before_ids[gid],
                   "confirmed": len(cur.get("confirmed") or []),
                   "n_summary": cur.get("n_summary"),
                   "inputs": cur.get("inputs"), "at": now()}
            if item["cue_role"] and subj.get("cue_role") != item["cue_role"]:
                why = ("the filed circuit %s does not carry cue_role %r "
                       "(subject says %r): the circuit route did not take "
                       "the role" % (a["id"], item["cue_role"],
                                     subj.get("cue_role")))
                say("  ! %s: %s" % (tag, why))
                rec["problem"] = why
                failures.append((tag, why))
                log.event("circuits", "%s: %s" % (tag, why))
            log["circuits"][key] = rec
        log.save()
        say("    filed %s in %s" % (", ".join(
            "%s %s v%s" % (b, (log["circuits"].get(circuit_key(
                gid, item["cue_type"], item["kind"], b)) or {}).get(
                    "artifact_id"), (log["circuits"].get(circuit_key(
                        gid, item["cue_type"], item["kind"], b)) or {}).get(
                            "version")) for b in bands), say_s(
                                time.time() - t0)))
    PROG.end_stage(len(failures))
    return failures


# ==========================================================================
# Stage 3: drifts
# ==========================================================================
def _ref(c):
    return {"id": c["artifact_id"], "version_id": c["version_id"]}


def _find(log, recs, rat, day, kind, band, role, roles):
    gid = recs[(rat, day)]["gid"]
    if kind == REST:
        ct = REST_CUE_TYPE
    else:
        ct = next(t for t, r in roles[rat]["roles"].items() if r == role)
    return log["circuits"].get(circuit_key(gid, ct, kind, band))


def drift_body(log, recs, roles, band, kind, role, contrast, rats=RATS):
    """The drift route body, or (None, [missing]) when circuits are absent."""
    left, right, missing = [], [], []
    base_l, base_r = [], []
    use_roles = ROLES if contrast == "roles" else (role,)
    for rat in rats:
        for rl in use_roles:
            for day, side, base in ((DAYS[0], left, base_l),
                                    (DAYS[1], right, base_r)):
                c = _find(log, recs, rat, day, kind, band, rl, roles)
                if not c or c.get("problem"):
                    missing.append("r%d %s %s %s%s" % (
                        rat, DAY_LABEL[day], kind, band,
                        (" " + rl) if rl else ""))
                    continue
                ref = _ref(c)
                if contrast == "baseline" and kind == "transition":
                    # The pre window of the SAME recording, pairing and band
                    # STATE circuit, pinned as an extra input (7.4).
                    s = _find(log, recs, rat, day, "state", band, rl, roles)
                    if not s:
                        missing.append("r%d %s state %s %s (baseline)"
                                       % (rat, DAY_LABEL[day], band, rl))
                        continue
                    ref = dict(ref, baseline=_ref(s))
                    base.append(dict(_ref(s), role="baseline",
                                     **{"for": c["artifact_id"]}))
                side.append(ref)
    if missing:
        return None, missing
    body = dict(DRIFT_FIELDS, left=left, right=right,
                labels={"left": DAY_LABEL[DAYS[0]],
                        "right": DAY_LABEL[DAYS[1]]},
                contrast=contrast, where="local",
                nickname=drift_nickname(band, kind, role, contrast))
    if base_l or base_r:
        body["baseline"] = {"left": base_l, "right": base_r}
    return body, []


def _inputs_of(body):
    ids = []
    for side in ("left", "right"):
        for r in body.get(side) or []:
            ids.append(r["version_id"])
            if r.get("baseline"):
                ids.append(r["baseline"]["version_id"])
    return sorted(ids)


def run_drifts(api, log, recs, roles, bands, kinds, rats=RATS):
    todo = [d for d in drift_plan() if d[0] in bands and d[1] in kinds]
    say("")
    say("STAGE 3 -- drifts (%d)" % len(todo))
    failures = []
    made_ids = {}
    for key0, rec0 in log["drifts"].items():
        if rec0.get("artifact_id"):
            made_ids.setdefault(rec0["artifact_id"], key0)
    PROG.stage("drifts", len(todo))
    for n, (band, kind, role, contrast) in enumerate(todo, start=1):
        key = drift_key(band, kind, role, contrast)
        nick = drift_nickname(band, kind, role, contrast)
        tag = "[%d/%d] %s" % (n, len(todo), nick)
        if stop_asked("drifts", tag, log):
            break
        api.same_boot()     # a Jarvis restarted between items ends the run
        PROG.item(n, tag, len(failures))
        body, missing = drift_body(log, recs, roles, band, kind, role,
                                   contrast, rats)
        if body is None:
            why = "circuits missing: " + ", ".join(missing[:6]) + (
                " and %d more" % (len(missing) - 6) if len(missing) > 6
                else "")
            say("  ! %s: %s" % (tag, why))
            failures.append((tag, why))
            continue
        was = log["drifts"].get(key)
        if was and was.get("artifact_id") and was.get("inputs") == \
                _inputs_of(body):
            PROG.outcome("already")
            say("  = %s: already filed from these circuit versions (%s v%s)"
                % (tag, was["artifact_id"], was.get("version")))
            continue
        try:
            chk = api.post("/api/arc/drift/check", body, write=False,
                           timeout=600)
        except ApiError as exc:
            say("  ! %s: the check refused: %s" % (tag, exc))
            failures.append((tag, str(exc)))
            log.event("drifts", "%s: check refused: %s" % (tag, exc))
            continue
        if not chk.get("compatible"):
            why = "not comparable: " + " ".join(chk.get("reasons") or [])
            say("  ! %s: %s" % (tag, why))
            failures.append((tag, why))
            log.event("drifts", "%s: %s" % (tag, why))
            continue
        t0 = time.time()
        try:
            started = api.post("/api/arc/drift/run", body, timeout=600)
            res, _snap = wait_job(api, started["job"], tag)
        except (ApiError, Refused) as exc:
            say("  ! %s: %s" % (tag, exc))
            failures.append((tag, str(exc)))
            log.event("drifts", "%s: %s" % (tag, exc))
            continue
        aid = res.get("artifact_id")
        other = made_ids.get(aid)
        if other and other != key:
            why = ("the drift route filed this as a version of %s (%s): the "
                   "drift subject does not tell the two apart" % (
                       aid, other))
            say("  ! %s: %s" % (tag, why))
            failures.append((tag, why))
            log.event("drifts", "%s: %s" % (tag, why))
        made_ids[aid] = key
        pay = res.get("payload") or {}
        log["drifts"][key] = {
            "band": band, "kind": kind, "role": role,
            "contrast": contrast or None, "nickname": nick,
            "artifact_id": aid, "version": res.get("version"),
            "version_id": res.get("version_id"),
            "digest": res.get("digest"), "name": res.get("name"),
            "new_version": res.get("new_version"),
            "design": pay.get("design"), "test": pay.get("test"),
            "bh_scope": pay.get("bh_scope"),
            "pooled_by": pay.get("pooled_by"),
            "inputs": _inputs_of(body), "at": now(),
            "seconds": round(time.time() - t0, 1)}
        log.save()
        say("  + %s: %s v%s%s (%s)" % (
            tag, aid, res.get("version"),
            "" if res.get("new_version") else " (confirmed)",
            say_s(time.time() - t0)))
    PROG.end_stage(len(failures))
    return failures


# ==========================================================================
# The plan and its cost -- said before anything runs
# ==========================================================================
def cost_plan(api, recs, roles, spark_rows, items, bands, kinds, stages):
    """{spark_s, circuit_s, drift_s, lines} from the routes' own plans."""
    lines = []
    sp_todo = [r for r in spark_rows if r["state"] == "todo"]
    sp_done = [r for r in spark_rows if r["state"] == "done"]
    sp_block = [r for r in spark_rows if r["state"] == "blocked"]
    rebank = {r["gid"] for r in sp_todo}
    spark_s = len(sp_todo) * SPARK_S_PER_RECORDING if "spark" in stages \
        else 0.0
    if "spark" in stages:
        lines.append("Spark: %d recording(s) to check and re-bank (about %s, "
                     "estimated at %s each), %d already done, %d blocked." % (
                         len(sp_todo), say_s(spark_s),
                         say_s(SPARK_S_PER_RECORDING), len(sp_done),
                         len(sp_block)))
        for r in sp_block:
            lines.append("  blocked: r%d %s (%s): %s" % (
                r["rat"], DAY_LABEL[r["day"]], r["gid"], r["why"]))
        hands = sum(r.get("hand") or 0 for r in sp_todo)
        lines.append("  hand decisions on the entries to re-bank: %d "
                     "event(s) (carried if any)" % hands)

    circuit_s = 0.0
    n_runs = n_current = n_est = 0
    pairs_todo = 0
    by_kind = {}
    plans = []
    if "circuits" in stages:
        state_pairs = {}
        for it in items:
            pl = plan_circuit(api, it, roles, bands)
            fresh = it["gid"] in rebank
            if not pl.get("refused"):
                n_pairs = pl.get("n_pairs") or 0
                n_cached = 0 if fresh else (pl.get("n_cached") or 0)
                todo = n_pairs - n_cached
                if pl["current"] and not fresh:
                    secs = 0.0
                    n_current += 1
                elif fresh or pl.get("local_s") is None:
                    per = (REST_EPOCH_S if it["kind"] == REST else PAIR_S)
                    secs = todo * per
                    n_est += 1
                else:
                    secs = float(pl["local_s"])
                if it["kind"] == "state":
                    state_pairs[(it["gid"], it["cue_type"])] = n_pairs
                how = "planned"
            else:
                # Refused: a transition plan before the Spark stage, or a
                # server that cannot plan this kind yet. Estimated, and said.
                if it["kind"] == REST:
                    n_pairs = max([t.get("n_pairs") or 0 for t in
                                   recs[(it["rat"], it["day"])].get(
                                       "cue_types") or []] or [0])
                    per = REST_EPOCH_S
                else:
                    n_pairs = (state_pairs.get((it["gid"], it["cue_type"]))
                               or it.get("n_pairs") or 0)
                    per = PAIR_S
                todo = n_pairs
                secs = todo * per
                n_est += 1
                how = "estimated (%s)" % pl["why"][:140]
            n_runs += 1
            pairs_todo += todo
            circuit_s += secs
            k = by_kind.setdefault(it["kind"], {"runs": 0, "units": 0,
                                                "s": 0.0, "current": 0})
            k["runs"] += 1
            k["units"] += todo
            k["s"] += secs
            k["current"] += 1 if (not pl.get("refused") and pl["current"]
                                  and not fresh) else 0
            plans.append(dict(it, plan=how, units_todo=todo, seconds=secs))
        lines.append("Circuits: %d run(s) x %d band(s) = %d circuit "
                     "artifact(s); about %s here, one after another." % (
                         n_runs, len(bands), n_runs * len(bands),
                         say_s(circuit_s)))
        for kind, k in by_kind.items():
            lines.append("  %-10s %3d run(s), %4d %s to compute, about %s%s"
                         % (kind, k["runs"], k["units"],
                            "epochs" if kind == REST else "cue pairs",
                            say_s(k["s"]),
                            (", %d already current" % k["current"])
                            if k["current"] else ""))
        if n_est:
            lines.append("  %d of the %d runs are ESTIMATED (%s s per cue "
                         "pair, %s s per rest epoch, all three bands in one "
                         "read): %s" % (
                             n_est, n_runs, PAIR_S, REST_EPOCH_S,
                             "their recordings are re-banked first, so no "
                             "cached pair survives" if rebank else
                             "the route could not plan them yet"))
    drifts = [d for d in drift_plan() if d[0] in bands and d[1] in kinds]
    drift_s = len(drifts) * DRIFT_S if "drifts" in stages else 0.0
    if "drifts" in stages:
        lines.append("Drifts: %d (matched by rat, Hartung-Knapp, BH per band "
                     "across windows and methods); about %s." % (
                         len(drifts), say_s(drift_s)))
    total = spark_s + circuit_s + drift_s
    lines.append("Total: about %s." % say_s(total))
    return {"spark_s": spark_s, "circuit_s": circuit_s, "drift_s": drift_s,
            "total_s": total, "lines": lines, "items": plans,
            "drifts": drifts, "pairs_todo": pairs_todo}


def plan_record(base, health, recs, roles, spark_rows, cost, bands, stages,
                n_requests, dry):
    """--plan-json: the plan and its cost as data, for the Drift panel to
    state before it offers to run. The same numbers `THE COST` prints."""
    return {
        "schema": "arc.precon-drift.plan/1", "at": now(), "dry_run": dry,
        "server": {"base": base, "started_at": health.get("started_at"),
                   "code_changed": health.get("code_changed") or []},
        "question": "How does inter-regional coupling change from Precon1 "
                    "to Precon4 in DEWEY rats r3, r4, r6-r11?",
        "rats": list(RATS), "days": [DAY_LABEL[d] for d in DAYS],
        "excluded": {"r%d" % k: v for k, v in EXCLUDED_RATS.items()},
        "bands": [{"id": b, "say": BAND_SAY[b]} for b in bands],
        "stages": list(stages), "requests": n_requests,
        "transition": {"before_s": BEFORE_S, "after_s": AFTER_S},
        "drift": DRIFT_FIELDS,
        "cost": {k: cost[k] for k in ("spark_s", "circuit_s", "drift_s",
                                      "total_s", "lines", "pairs_todo")},
        "recordings": [{"rat": rat, "day": DAY_LABEL[day], "gid": r["gid"],
                        "label": r.get("label")}
                       for (rat, day), r in sorted(recs.items())],
        "roles": [{"rat": rat, "food_cue": roles[rat]["food_cue"],
                   "food_pair": roles[rat]["food_pair"],
                   "no_food_pairs": roles[rat]["no_food_pairs"],
                   "followed": roles[rat]["source"].get("followed"),
                   "presented": roles[rat]["source"].get("presented")}
                  for rat in RATS],
        "spark": [{"rat": r["rat"], "day": DAY_LABEL[r["day"]],
                   "gid": r["gid"], "state": r["state"], "why": r.get("why"),
                   "hand": r.get("hand")} for r in spark_rows],
        "circuits": [{"rat": it["rat"], "day": DAY_LABEL[it["day"]],
                      "gid": it["gid"], "kind": it["kind"],
                      "cue_type": it["cue_type"], "cue_role": it["cue_role"],
                      "units_todo": it["units_todo"],
                      "seconds": it["seconds"], "plan": it["plan"]}
                     for it in cost["items"]],
        "n_circuit_artifacts": len(cost["items"]) * len(bands),
        "drifts": [{"key": drift_key(*d), "band": d[0], "kind": d[1],
                    "role": d[2], "contrast": d[3],
                    "nickname": drift_nickname(*d)} for d in cost["drifts"]],
    }


# ==========================================================================
# Erasing what a TEST made (never the real run's)
# ==========================================================================
def erase_made(api, log):
    """Delete, through the artifact delete route, every artifact this
    runlog says it CREATED -- drifts first, because a cited circuit cannot
    be deleted. An artifact that existed before (a new version was added to
    it) is never touched."""
    gone, kept = [], []
    for key, d in list(log["drifts"].items()):
        if d.get("artifact_id") and d.get("created_by_this_run", True):
            try:
                api.post("/api/artifacts/%s/delete" % q(d["artifact_id"]))
                gone.append(d["artifact_id"])
            except ApiError as exc:
                kept.append((d["artifact_id"], str(exc)))
    for key, c in list(log["circuits"].items()):
        if not c.get("artifact_id"):
            continue
        if not c.get("created_by_this_run"):
            kept.append((c["artifact_id"], "existed before this run; not "
                         "deleted"))
            continue
        try:
            api.post("/api/artifacts/%s/delete" % q(c["artifact_id"]))
            gone.append(c["artifact_id"])
        except ApiError as exc:
            kept.append((c["artifact_id"], str(exc)))
    return gone, kept


# ==========================================================================
def run_stages(api, log, stages, spark_rows, items, roles, bands, recs,
               kinds, gids=None, allow_unmeasured=False):
    """The three stages, in order, and how they ended:
    (failures, stopped, interrupted).

    A stage that errors part-way (a route refused, a request failed) is a
    failure of that stage, said and recorded; the next stage still runs and
    refuses, item by item, whatever depended on it. Jarvis going away is
    not that: JarvisGone ends the run as INTERRUPTED -- the item in flight is
    not counted, the run log says where it got to, and the run that carries
    it on redoes that item from its per-pair cache."""
    failures = []
    stopped = False
    interrupted = None
    try:
        for stage in STAGES:
            if stage not in stages:
                continue
            if stop_asked(stage, "the %s stage" % stage, log):
                stopped = True
                break
            try:
                if stage == "spark":
                    bad = run_spark(api, spark_rows, log, only=gids)
                    failures += [("spark", b) for b in bad]
                elif stage == "circuits":
                    failures += run_circuits(
                        api, items, roles, bands, log, recs,
                        allow_unmeasured=allow_unmeasured)
                else:
                    failures += run_drifts(api, log, recs, roles, bands,
                                           kinds)
            except (ApiError, Refused) as exc:
                PROG.settle(force="failed")
                PROG.end_stage()
                say("  ! the %s stage stopped: %s" % (stage, exc))
                log.event(stage, "the stage stopped: %s" % exc)
                failures.append((stage, "the stage stopped: %s" % exc))
            if PROG.data.get("stopped"):
                stopped = True
                break
    except JarvisGone as exc:
        interrupted = {"at": now(), "why": str(exc),
                       "stage": PROG.data.get("stage"),
                       "item": PROG.data.get("item")}
        PROG.open = None
        say("")
        say("INTERRUPTED: %s" % exc)
        log.event("run", "interrupted: %s" % exc)
    log.data["finished"] = None if interrupted else now()
    log.data["interrupted"] = interrupted
    log.data["failures"] = [list(f) for f in failures]
    log.data["stopped"] = now() if stopped else None
    log.save()
    PROG.data["finished"] = None if interrupted else now()
    PROG.data["interrupted"] = interrupted
    PROG.data["failures"] = [list(f) for f in failures]
    PROG.save()
    return failures, stopped, interrupted


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="DEWEY Precon1 -> Precon4 through Jarvis (cost first).")
    ap.add_argument("--base", default=None,
                    help="Jarvis URL (default: discover from 8733 upward)")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan and cost only; writes nothing anywhere")
    ap.add_argument("--step", choices=STAGES + ("all",), default="all",
                    help="run one stage only")
    ap.add_argument("--runlog", default=RUNLOG_PATH)
    ap.add_argument("--yes", action="store_true",
                    help="do not pause 15 s after stating the cost")
    # Narrowing, for a test on a slice. The real run uses none of these.
    ap.add_argument("--gids", default=None, help="comma-separated gids")
    ap.add_argument("--bands", default=None, help="comma-separated band ids")
    ap.add_argument("--kinds", default=None,
                    help="comma-separated: state,transition,rest")
    ap.add_argument("--role", default=None, choices=ROLES,
                    help="only circuits of this role")
    ap.add_argument("--allow-unmeasured", action="store_true",
                    help="TEST ONLY: make circuits before the Spark stage")
    ap.add_argument("--plan-json", default=None,
                    help="write the plan and its cost here as JSON, once it "
                         "is known and before anything runs (the Drift "
                         "panel reads it)")
    ap.add_argument("--progress", default=None,
                    help="keep where the run is in this JSON file")
    ap.add_argument("--stop-file", default=None,
                    help="stop before the next item once this file exists")
    ap.add_argument("--resumed", default=None,
                    help="this run carries on one that was interrupted; "
                         "the reason goes in the run log")
    ap.add_argument("--erase-made", action="store_true",
                    help="TEST ONLY: delete what the runlog says it created")
    args = ap.parse_args(argv)
    global PROG, STOP_FILE
    PROG = Progress(None if args.dry_run else args.progress)
    STOP_FILE = args.stop_file

    stages = STAGES if args.step == "all" else (args.step,)
    bands = tuple(args.bands.split(",")) if args.bands else BAND_ORDER
    for b in bands:
        if b not in BAND_ORDER:
            say("%r is not a band (%s)." % (b, ", ".join(BAND_ORDER)))
            return 2
    kinds = tuple(args.kinds.split(",")) if args.kinds else \
        CUE_KINDS + (REST,)
    gids = set(args.gids.split(",")) if args.gids else None

    try:
        base, health = discover(args.base)
    except Refused as exc:
        say(str(exc))
        return 2
    api = Api(base, dry=args.dry_run, boot=str(health.get("started_at") or ""))
    log = RunLog(args.runlog, dry=args.dry_run)
    say("Jarvis at %s (started %s; logs %s)" % (
        base, health.get("started_at"), health.get("logs")))
    if health.get("code_changed"):
        say("  note: Jarvis reports these files changed since it started: "
            "%s -- it is running the OLD code for them."
            % ", ".join(health["code_changed"]))

    if args.resumed and not args.dry_run:
        say("Carrying on: %s" % args.resumed)
        log.event("run", "carrying on: %s" % args.resumed)
        PROG.data["resumed"] = args.resumed
    if args.erase_made:
        gone, kept = erase_made(api, log)
        say("erased %d artifact(s): %s" % (len(gone), ", ".join(gone)))
        for aid, why in kept:
            say("  kept %s: %s" % (aid, why))
        log.data["erased"] = {"at": now(), "ids": gone,
                              "kept": [list(k) for k in kept]}
        log.save()
        return 0 if not [k for k in kept if "existed" not in k[1]] else 1

    try:
        t0 = time.time()
        recs = select_recordings(api)
        say("Recordings: %d (r%s x %s), read in %s" % (
            len(recs), ", r".join(str(r) for r in RATS),
            " and ".join(DAY_LABEL[d] for d in DAYS),
            say_s(time.time() - t0)))
        say("  r5 left out: %s." % EXCLUDED_RATS[5])
        roles = read_roles(recs)
        say("Cue roles (backend/cueroles.py, from each rat's Con SPC TTLs):")
        for rat in RATS:
            t = roles[rat]
            s = t["source"]
            say("  r%-3d food cue %-9s food pair %-18s no-food %-18s "
                "(followed %s)" % (
                    rat, t["food_cue"], t["food_pair"],
                    ",".join(t["no_food_pairs"]),
                    ", ".join("%s %d/%d" % (c, s["followed"].get(c, 0),
                                            s["presented"].get(c, 0))
                              for c in s["presented"])))
        spark_rows = spark_plan(api, recs)
        if gids:
            spark_rows = [r for r in spark_rows if r["gid"] in gids]
        items = circuit_items(recs, roles,
                              kinds=tuple(k for k in kinds
                                          if k in CUE_KINDS + (REST,)),
                              gids=gids, role_only=args.role)
        cost = cost_plan(api, recs, roles, spark_rows, items, bands, kinds,
                         stages)
    except JarvisGone as exc:
        say("INTERRUPTED while planning: %s" % exc)
        log.event("run", "interrupted while planning: %s" % exc)
        return 4
    except (Refused, ApiError) as exc:
        say("REFUSED: %s" % exc)
        return 2

    say("")
    say("THE COST, before anything runs:")
    for line in cost["lines"]:
        say("  " + line)
    say("  (%d requests to plan this)" % api.n)

    log.data.update({
        "question": "How does inter-regional coupling change from Precon1 "
                    "to Precon4 in DEWEY rats r3, r4, r6-r11?",
        "plan": "C:/Users/Z390/.claude/plans/okay-time-for-a-fluffy-"
                "crescent.md",
        "contract": "docs/the-arc-contracts.md section 7",
        "server": {"base": base, "started_at": health.get("started_at"),
                   "code_changed": health.get("code_changed")},
        "design": {"rats": list(RATS), "excluded": {
            "r%d" % k: v for k, v in EXCLUDED_RATS.items()},
            "days": [DAY_LABEL[d] for d in DAYS], "bands": list(bands),
            "kinds": list(kinds), "transition_before_s": BEFORE_S,
            "transition_after_s": AFTER_S, "drift": DRIFT_FIELDS},
        "recordings": {r["gid"]: {"rat": rat, "day": DAY_LABEL[day],
                                  "label": r.get("label"),
                                  "cue_types": r.get("cue_types"),
                                  "bank": r.get("bank")}
                       for (rat, day), r in sorted(recs.items())},
        "roles": {str(rat): {k: roles[rat][k] for k in (
            "food_cue", "roles", "food_pair", "no_food_pairs",
            "no_food_cues", "source")} for rat in RATS},
        "cost": {k: cost[k] for k in ("spark_s", "circuit_s", "drift_s",
                                      "total_s", "lines")},
    })
    if args.plan_json:
        write_json(args.plan_json, plan_record(
            base, health, recs, roles, spark_rows, cost, bands, stages,
            api.n, args.dry_run))

    if args.dry_run:
        say("")
        say("DRY RUN: the plan, item by item.")
        for r in spark_rows:
            say("  spark    r%-3d %-8s %s  %-8s %s" % (
                r["rat"], DAY_LABEL[r["day"]], r["gid"], r["state"],
                r.get("why") or ("%d hand-decided event(s) to carry"
                                 % (r.get("hand") or 0))))
        for it in cost["items"]:
            say("  circuit  r%-3d %-8s %-10s %-15s %-8s %3d to compute, "
                "%-6s %s" % (
                    it["rat"], DAY_LABEL[it["day"]], it["kind"],
                    it["cue_type"], it["cue_role"] or "-", it["units_todo"],
                    say_s(it["seconds"]), it["plan"]))
        for band, kind, role, contrast in cost["drifts"]:
            say("  drift    %s" % drift_nickname(band, kind, role, contrast))
        say("")
        say("Nothing was written (%d requests, all reads)." % api.n)
        return 0

    if not args.yes:
        say("")
        say("Starting in 15 s -- Ctrl-C to stop. Nothing has been written.")
        time.sleep(15)
    log.save()
    PROG.save()

    try:
        failures, stopped, interrupted = run_stages(
            api, log, stages, spark_rows=spark_rows, items=items,
            roles=roles, bands=bands, recs=recs, kinds=kinds, gids=gids,
            allow_unmeasured=args.allow_unmeasured)
    except Exception as exc:                             # noqa: BLE001
        # Something nobody planned for. Said in full, recorded where the
        # panel and the run log can show it, and exit 5 -- which is not
        # carried on by itself: the same error would come back.
        import traceback
        say(traceback.format_exc())
        crashed = {"at": now(), "error": "%s: %s" % (type(exc).__name__,
                                                     exc),
                   "stage": PROG.data.get("stage"),
                   "item": PROG.data.get("item")}
        PROG.open = None
        PROG.data["crashed"] = crashed
        PROG.save()
        try:
            log.data["crashed"] = crashed
            log.event("run", "stopped by an error: %s" % crashed["error"])
        except OSError:
            pass
        say("STOPPED BY AN ERROR: %s" % crashed["error"])
        return 5
    say("")
    if interrupted:
        say("Everything filed so far is in the run log (%s). The next Jarvis "
            "to start carries this on by itself." % args.runlog)
        return 4
    if stopped:
        say("Stopped, as asked. Everything filed so far is in the run log "
            "(%s); running again picks up where this left off." % args.runlog)
        return 3
    if failures:
        say("%d item(s) did not complete -- see %s:" % (len(failures),
                                                        args.runlog))
        for tag, why in failures[:40]:
            say("  %s: %s" % (tag, why))
        return 1
    say("Done. Run log: %s" % args.runlog)
    return 0


if __name__ == "__main__":
    sys.exit(main())
