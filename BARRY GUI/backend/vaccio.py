"""
vaccio.py -- reading a recording that is on the cluster and not on this disk.

WHAT THIS IS FOR

`vacc.py` answers "can the cluster reach this recording", and the Sessions
view draws the answer as a chip. Until now that was the end of it: a
recording VACC reads perfectly well, on a share this computer does not
mount, had no Open button anywhere. You could see that it existed and you
could run a tool on it. You could not look at it.

This is the Open button. A `vacc:<gid>` path opens in Xplorefinder exactly
the way a drive file does -- same tabs, same panes, same curation, same
bank -- and the samples come off the cluster rather than off a disk.

WHY A GID AND NOT A PATH

`vacc:s6b2088ae883b`, not `vacc:/gpfs2/scratch/...`. Three reasons and they
all matter:

  1. The remote path is derived, not typed. `vacc.resolve_gid` already
     decides it, from the lab-wide path map or from what is staged in
     scratch, and it prefers a share the cluster mounts over a copy in
     scratch that gets purged without notice. One place decides; this is
     not a second.

  2. Everything attached to a recording is keyed on the gid -- the stored
     view state, the bad channels, the curation set, the bank. Opening by
     gid means a recording read off the cluster is the SAME recording as
     the one somebody opened off Y: last week, and not a new one that
     happens to look like it.

  3. A cluster path must never enter the registry as a path. `REG.ensure`
     files every path a recording is opened from, and `/gpfs2/scratch/...`
     filed as if it were a local path would come back out of
     `resolve_path` as `local-only` -- the recording would report that the
     cluster cannot reach it, on the strength of having been read off the
     cluster. So `api_csc_open` skips `ensure` for these and takes the
     identity from the record the gid already names.

WHAT RUNS WHERE

Nothing is copied down. `backend/vaccserve.py` runs on the login node with
the same backend this process has, and answers with the payload the viewer
draws -- the enveloped window, not the 42 MB of records it was computed
from. See that file for the split and why.

The link is one ssh process, kept. A window is a line of JSON down and a
line of JSON back, so scrubbing costs a round trip rather than a handshake,
and the session's header is read once on the cluster instead of once per
window.

AND IT IS REAPED

A login node is shared, and a process somebody left running while they went
to lunch is somebody else's problem. The link closes itself after
`IDLE_S` with nothing asked of it, and reopens on the next question -- one
handshake, once, rather than a process held for the afternoon.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time

from . import vacc

PREFIX = "vacc:"
PROTO = "@@JV1 "

# How long a link may sit idle before it is closed. Ten minutes: long enough
# that stepping away from the keyboard and coming back does not cost a
# handshake, short enough that a forgotten tab does not hold a process on a
# shared login node overnight.
IDLE_S = 600.0

# What one call may take, per op, because they are not one kind of work.
#
# Measured on a 45-minute 64-channel recording at 30 kHz, through the real
# routes: open 1.8 s, a filtered 10 s window 1.3 s, a CSD 0.7 s, the
# amplitude overview 4.6 s. The window budget is generous against those and
# still mean by the standards of an interface -- a viewer that hangs for two
# minutes on a dead link is worse than one that says so.
#
# `band` is the exception and gets ten minutes. It reads the channel right
# through at 250 Hz; `extras._bandgram` puts that at most of a minute for
# 28 minutes of recording on a local disk, so a two-hour one behind a
# network is minutes, and timing it out at ninety seconds would report a
# working cluster as a broken one.
CALL_TIMEOUT = 90.0
OP_TIMEOUT = {"overview": 240.0, "band": 600.0}
START_TIMEOUT = 120.0

_LOGS_DIR = None
_APP_DIR = None
_RESOLVE = None

_LOCK = threading.RLock()
_LINK = None


def configure(logs_dir, app_dir):
    """Where the config is, and which tree gets pushed to the cluster."""
    global _LOGS_DIR, _APP_DIR
    _LOGS_DIR = logs_dir
    _APP_DIR = app_dir


def set_resolver(fn):
    """How a gid becomes a place on the cluster.

    A callback rather than an import, because answering it needs the merged
    registry and the staged inventory, and both of those live in `app.py`.
    Reaching for them from here would put a module that shells out to ssh
    underneath the one that serves requests.

    `fn(gid)` returns `{"remote": str, "state": str, "why": str}` or raises
    with a sentence a person can read.
    """
    global _RESOLVE
    _RESOLVE = fn


# --------------------------------------------------------------------------
# The path scheme
# --------------------------------------------------------------------------
def is_vacc(path):
    return isinstance(path, str) and path.startswith(PREFIX)


def gid_of(path):
    """The recording a `vacc:` path names, or None.

    Whitespace-stripped and length-checked rather than trusted: this arrives
    from a browser, and it is about to be interpolated into a lookup.
    """
    if not is_vacc(path):
        return None
    gid = str(path)[len(PREFIX):].strip().strip("/")
    if not gid or len(gid) > 64 or not gid.replace("_", "").replace("-", "").isalnum():
        return None
    return gid


def resolve(path):
    """Where on the cluster a `vacc:` path is. Raises with a sentence."""
    gid = gid_of(path)
    if not gid:
        raise ValueError("Not a recording id: %r" % (path,))
    if _RESOLVE is None:
        raise RuntimeError("Jarvis has not been told how to look a "
                           "recording up yet.")
    return _RESOLVE(gid)


# --------------------------------------------------------------------------
# The link
# --------------------------------------------------------------------------
class LinkError(RuntimeError):
    """A live read that did not come back. Carries a readable sentence."""


class Link:
    """One kept ssh process running `backend.vaccserve` on the login node."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.proc = None
        self.replies = queue.Queue()
        self.noise = []              # anything on stdout that was not a reply
        self.err = []
        self.started_at = 0.0
        self.last_use = 0.0
        self.n_calls = 0
        self.hello = None
        self._seq = 0

    # ---- lifecycle -------------------------------------------------------
    def start(self):
        """Push the code, open the process, and wait for it to say hello.

        The push first, always. A link to a stale backend is the failure
        mode this whole design is meant to make impossible -- the cluster
        running arithmetic that no longer matches the desk's -- and
        `push_code` skips the upload when the hash already matches, so the
        cost of being sure is one `cat` of a checksum.
        """
        if not vacc.have_ssh():
            raise LinkError("There is no ssh client on this computer, so "
                            "Jarvis cannot read anything off the cluster "
                            "from here.")
        if not self.cfg.get("netid"):
            raise LinkError("No VACC account is set up on this computer. "
                            "Sign in from your profile, under VACC account.")
        if _APP_DIR:
            vacc.push_code(self.cfg, _APP_DIR)

        code = vacc._remote_path(self.cfg.get("workspace") or ".", "code")
        # The preamble goes in the COMMAND, not on stdin.
        #
        # Everything else in this codebase sends its script to `bash -s`,
        # which is right when the script is the whole conversation. Here it
        # is not: `bash -s` reads stdin until EOF, and stdin is the request
        # channel. So the preamble is the remote command and the last thing
        # it does is `exec`, which replaces the shell with the reader and
        # hands it the stdin the shell was never going to give up.
        script = (vacc.activate(self.cfg) + "\n"
                  + "cd %s || exit 9\n" % vacc.q(code)
                  + "exec python -u -m backend.vaccserve\n")

        cmd = ["ssh"] + list(vacc.SSH_OPTS)
        if self.cfg.get("key_path"):
            cmd += ["-i", self.cfg["key_path"], "-o", "IdentitiesOnly=yes"]
        cmd += ["%s@%s" % (self.cfg["netid"], self.cfg["host"]), script]

        try:
            # Binary pipes, and the newline written by hand. `text=True`
            # would put a TextIOWrapper on stdin with Windows newline
            # translation, so every request would arrive on the login node
            # ending `\r` -- and `json.loads` would take it, silently, right
            # up until a path had a trailing carriage return in it. Same
            # lesson `vacc._ssh` carries at length.
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, **vacc._popen_kwargs())
        except OSError as exc:
            raise LinkError("Could not start ssh: %s" % exc)

        self.started_at = self.last_use = time.time()
        threading.Thread(target=self._read_out, daemon=True,
                         name="vaccio-out").start()
        threading.Thread(target=self._read_err, daemon=True,
                         name="vaccio-err").start()

        first = self._await(None, START_TIMEOUT, what="the cluster to answer")
        if not first.get("ready"):
            raise LinkError("The cluster started something that is not the "
                            "reader: %s" % json.dumps(first)[:200])
        self.hello = self.call("hello")
        return self.hello

    def alive(self):
        return bool(self.proc) and self.proc.poll() is None

    def close(self, why=None):
        proc, self.proc = self.proc, None
        if not proc:
            return
        try:
            if proc.poll() is None:
                proc.stdin.write(b'{"op":"bye"}\n')
                proc.stdin.flush()
        except Exception:                                # noqa: BLE001
            pass
        try:
            proc.wait(timeout=3)
        except Exception:                                # noqa: BLE001
            try:
                vacc.sysinfo.kill_tree(proc)
            except Exception:                            # noqa: BLE001
                pass

    # ---- the wire --------------------------------------------------------
    def _read_out(self):
        """Every line the far side writes, sorted into replies and noise.

        A login shell prints. An MOTD, a `module load` notice, a conda
        warning about a deprecated activate -- all of it lands on this pipe
        ahead of the first reply. A reader that assumed the next line was
        its answer would parse the message of the day as JSON exactly once
        per cluster upgrade, which is why every reply is marked and
        everything else is kept as `noise` for the error message rather
        than thrown away.
        """
        proc = self.proc
        try:
            for raw in iter(proc.stdout.readline, b""):
                text = raw.decode("utf-8", "replace").rstrip("\r\n")
                if text.startswith(PROTO):
                    try:
                        self.replies.put(json.loads(text[len(PROTO):]))
                    except ValueError:
                        self.noise.append(text[:400])
                elif text.strip():
                    self.noise = (self.noise + [text[:400]])[-20:]
        except Exception:                                # noqa: BLE001
            pass
        finally:
            # A sentinel, so a caller waiting on a dead process is told
            # rather than left on a timeout it will sit out in full.
            self.replies.put(None)

    def _read_err(self):
        proc = self.proc
        try:
            for raw in iter(proc.stderr.readline, b""):
                text = raw.decode("utf-8", "replace").rstrip("\r\n")
                if text.strip():
                    self.err = (self.err + [text[:400]])[-20:]
        except Exception:                                # noqa: BLE001
            pass

    def _await(self, rid, timeout, what="the cluster"):
        end = time.time() + timeout
        while True:
            left = end - time.time()
            if left <= 0:
                raise LinkError("Waited %ds for %s and it did not answer.%s"
                                % (timeout, what, self._tail()))
            try:
                got = self.replies.get(timeout=min(left, 1.0))
            except queue.Empty:
                if not self.alive():
                    raise LinkError("The link to the cluster closed.%s"
                                    % self._tail())
                continue
            if got is None:
                raise LinkError("The link to the cluster closed.%s"
                                % self._tail())
            # A reply to a call that has already timed out. Dropped, not
            # returned: handing a stale window to whoever asked next is how
            # a viewer shows one recording's data under another's name.
            if rid is not None and got.get("id") not in (rid, None):
                continue
            return got

    def _tail(self):
        """What the far side said, when it said anything.

        Appended to every error. "The link closed" on its own is unactionable;
        "The link closed -- ModuleNotFoundError: numpy" is a morning saved.
        """
        bits = [t for t in (self.err[-3:] + self.noise[-3:]) if t]
        return ("\n\nThe cluster said: " + " / ".join(bits)) if bits else ""

    def call(self, op, timeout=CALL_TIMEOUT, **kw):
        if not self.alive():
            raise LinkError("The link to the cluster is not open.%s"
                            % self._tail())
        self._seq += 1
        rid = self._seq
        req = dict(kw)
        req["op"] = op
        req["id"] = rid
        try:
            self.proc.stdin.write(json.dumps(req).encode("utf-8") + b"\n")
            self.proc.stdin.flush()
        except Exception as exc:                         # noqa: BLE001
            raise LinkError("The link to the cluster broke while asking: "
                            "%s%s" % (exc, self._tail()))
        got = self._await(rid, timeout, what="a %s" % op)
        self.last_use = time.time()
        self.n_calls += 1
        return got


def _cfg():
    return vacc.load_config(_LOGS_DIR)


def link(start=True):
    """The one link, opened if it is not already.

    Serialized on `_LOCK` rather than left to whoever asks first. Two panes
    refreshing at once is the ordinary case, and two of them racing to start
    a process would leave one of the two orphaned on the login node.
    """
    global _LINK
    with _LOCK:
        if _LINK is not None and _LINK.alive():
            return _LINK
        if _LINK is not None:
            _LINK.close()
            _LINK = None
        if not start:
            return None
        fresh = Link(_cfg())
        fresh.start()
        _LINK = fresh
        _reaper_soon()
        return _LINK


def call(op, timeout=None, **kw):
    """One request, with one retry across a link that died while idle.

    The retry is deliberately narrow. A link that has been sitting open for
    an hour can be gone -- the login node reboots, a VPN drops, sshd's
    ClientAlive gives up -- and the first thing anybody notices is a broken
    pipe on a window request. Reopening once and asking again turns that
    into a slow scrub instead of an error. A SECOND failure is reported:
    retrying past that is how a dead cluster becomes a spinner forever.
    """
    timeout = timeout or OP_TIMEOUT.get(op, CALL_TIMEOUT)
    with _LOCK:
        try:
            return link().call(op, timeout=timeout, **kw)
        except LinkError:
            global _LINK
            if _LINK is not None:
                _LINK.close()
                _LINK = None
            return link().call(op, timeout=timeout, **kw)


def close(why=None):
    global _LINK
    with _LOCK:
        if _LINK is not None:
            _LINK.close(why)
            _LINK = None


def status():
    """What the link is, without opening one.

    Read-only and offline, the same discipline `vacc.status` follows: this is
    what decides whether to OFFER a live read, and a probe here would put a
    handshake in front of a chip.
    """
    with _LOCK:
        lk = _LINK
        if lk is None or not lk.alive():
            return {"ok": True, "open": False}
        return {"ok": True, "open": True,
                "since": lk.started_at, "idle_s": time.time() - lk.last_use,
                "calls": lk.n_calls, "remote": lk.hello or {}}


_REAPER = {"on": False}


def _reaper_soon():
    if _REAPER["on"]:
        return
    _REAPER["on"] = True

    def go():
        try:
            while True:
                time.sleep(30.0)
                with _LOCK:
                    lk = _LINK
                    if lk is None:
                        break
                    if not lk.alive():
                        close()
                        break
                    if (time.time() - lk.last_use) > IDLE_S:
                        close("idle")
                        break
        finally:
            _REAPER["on"] = False

    threading.Thread(target=go, daemon=True, name="vaccio-reaper").start()


# --------------------------------------------------------------------------
# The session, in the shape `csc.py` hands around
# --------------------------------------------------------------------------
def open_session(path, even_only=None, invert=True):
    """A `vacc:<gid>` recording, opened on the cluster.

    The returned dict is what `csc.open_session` returns for a folder of
    `.ncs` -- because it IS what `csc.open_session` returned, on the far
    side. Three fields are changed on the way back and every one of them is
    about honesty rather than shape:

      `source`  'vacc', so `get_window` knows to ask the cluster rather
                than to open a file that is not there.
      `path`    the `vacc:` id it was asked for, NOT the cluster path.
                Everything downstream treats `path` as the thing to ask for
                again, and asking for `/gpfs2/...` on this machine opens
                nothing.
      `remote`  where it actually is, and which of the two ways -- read in
                place, or a copy in scratch. Drawn in the interface,
                because "you are looking at a scratch copy" is a sentence
                somebody needs before they trust what they see.
    """
    try:
        where = resolve(path)
    except Exception as exc:                             # noqa: BLE001
        return {"ok": False, "error": str(exc), "path": path}

    remote = where.get("remote")
    if not remote:
        return {"ok": False, "path": path,
                "error": where.get("why") or "The cluster has no copy of it."}

    try:
        got = call("open", path=remote, even_only=even_only, invert=invert)
    except LinkError as exc:
        return {"ok": False, "path": path, "error": str(exc)}
    if not got.get("ok"):
        return got

    got["source"] = "vacc"
    got["remote"] = remote
    got["remote_state"] = where.get("state")
    got["remote_why"] = where.get("why")
    got["gid"] = gid_of(path)
    got["path"] = path
    # `name` came back as the folder's basename on the cluster, which is the
    # recording's own name and is right. Left alone deliberately: renaming it
    # to the gid would replace the one human-readable thing in the tab.
    return got


def _remote_args(session):
    return {"path": session.get("remote"),
            "even_only": session.get("even_only"),
            "invert": session.get("invert", True)}


def get_window(session, t0, t1, **kw):
    """`csc.get_window`, run where the samples are.

    Every keyword is forwarded untouched, so this does not have to be kept
    in step with that signature -- adding an argument there needs no change
    here. `report` is the exception: it is an out-parameter, filled in by
    the callee, and an out-parameter does not survive a wire. The payload
    carries the same information as `sampling`, so it is copied back into
    the caller's dict on arrival and nobody downstream can tell.
    """
    report = kw.pop("report", None)
    args = {k: v for k, v in kw.items() if v is not None}
    args["t0"] = float(t0)
    args["t1"] = float(t1)
    got = call("window", args=args, **_remote_args(session))
    if report is not None and isinstance(got.get("sampling"), dict):
        report.update(got["sampling"])
    return got


def nev(session, nev_path, t_start_us=None):
    """One `.nev` beside a recording on the cluster, read where it is.

    Same `nlx.nev_events` as a drive file, and the times land on the same
    clock -- the first CSC timestamp is read on the cluster too, rather than
    being sent from here, because a .nev resolved against the wrong t0 gives
    events that land plausibly and in the wrong place.
    """
    return call("nev", nev=nev_path, t_start_us=t_start_us,
                **_remote_args(session))


def overview(session, **kw):
    return call("overview", args={k: v for k, v in kw.items() if v is not None},
                **_remote_args(session))


def band_profile(session, **kw):
    return call("band", args={k: v for k, v in kw.items() if v is not None},
                **_remote_args(session))
