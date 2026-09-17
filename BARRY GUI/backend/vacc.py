"""
vacc.py -- the link to the cluster, and nothing that computes.

VACC is the University of Vermont's supercomputer. Jarvis already knows what
every recording is and where every copy of it has ever been opened from; this
is the part that knows those facts in the cluster's terms -- which of them it
can already read, what it has been asked to do, and how that is going.

WHY ssh AND NOT paramiko

`ssh.exe` ships in Windows 10's System32 and on every Mac, it reads the user's
own `~/.ssh/config`, and the keys people already use for the cluster work
through it unchanged. paramiko would be a new dependency whose first job is to
reimplement a key agent that is already running. The cost of the choice is
real and is paid in `_ssh`: Windows OpenSSH has no ControlMaster, so there is
no connection to keep alive and every call is a fresh handshake -- measured at
about 0.4 s against login.vacc.uvm.edu, consistently.

Cheap, then, but not free, and it lands on a login node shared with everybody
else's interactive work. So nothing here asks the cluster two questions when
one will do: every probe and every poll is ONE invocation that brings back
everything wanted. What that discipline is really worth showed up in the
quota, which turned out never to return at all -- see `_QUOTA`.

THERE IS NO SECRET IN THIS FILE

UVM's own documentation says authenticating with a key removes the Duo
requirement, and that is the whole reason this is possible: a GUI cannot
answer a push notification for every status poll. With key authentication the
private key stays in `~/.ssh` and Jarvis never reads it, so
`GUI_logs/.vacc.json` holds a netid, a path, and an account code -- identifying
rather than secret. It is still gitignored, because a netid in a public
repository is somebody's name, and `tools/vacc_setup.py` still refuses to
write it unless git is already ignoring it.

THE CONFIG IS SPLIT BY LIFETIME, NOT BY SECRECY

  vacc.json              tracked. Where the cluster is, which partitions
                         exist, and the path map -- a UNC share and the
                         /netfiles path it appears at are lab-wide facts, and
                         a clone should not have to be told them.

  GUI_logs/.vacc.json    this machine. Which netid, which key, which account.

WHAT HAPPENS WHEN THERE IS NO CLUSTER

Nothing. This module imports with no network, no config and no ssh binary;
`status()` returns `available: False` with a sentence saying why and never
raises. Jarvis works offline and that is not a degraded mode, so nothing here
may be on the path of a request that would otherwise have succeeded.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import time

from . import sysinfo

# How long an answer about the cluster is worth believing. Short enough that a
# queue that emptied shows as empty, long enough that a page rendering the chip
# twice does not pay for two connections.
TTL_S = 30.0

# What one round trip to the login node costs, measured from this machine:
# six consecutive `hostname -s` calls came back in 389, 395, 417, 417, 433 and
# 441 ms. Windows OpenSSH has no ControlMaster so none of it is amortised, but
# four tenths of a second is cheap enough that the batching below is about
# being a good neighbour on a shared login node rather than about latency.
#
# Recorded because the first figure written here was eleven seconds, taken
# from a shell loop whose `date +%s` had one-second resolution and whose own
# `timeout` and subshells dominated the number. That measured the harness, not
# the cluster, and every interval in this feature was set from it.
ROUND_TRIP_S = 0.42

# Every ssh call carries these. They are not tuning.
#
#   BatchMode           without it, a rotated or passphrased key makes ssh
#                       block on a password prompt reading a pipe Flask
#                       handed it, and the thread that called it waits for
#                       ever holding a job that never moves and never fails.
#   ConnectTimeout      a login node that is up but not answering must cost
#                       ten seconds, not the request.
#   ServerAlive*        a dropped connection mid-poll should end the call
#                       rather than hang it.
#   accept-new          trust on first use, and never again: a CHANGED key is
#                       refused. `StrictHostKeyChecking=no` would accept it
#                       silently, which is the one thing host keys exist to
#                       stop.
SSH_OPTS = [
    "-o", "BatchMode=yes",
    "-o", "NumberOfPasswordPrompts=0",
    "-o", "PreferredAuthentications=publickey",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ConnectTimeout=10",
    "-o", "ServerAliveInterval=15",
    "-o", "ServerAliveCountMax=3",
]

DEFAULT_HOST = "login.vacc.uvm.edu"

# A run id is minted here and then interpolated into remote paths, so it is
# checked rather than trusted -- see `_remote_path`.
RID_RE = re.compile(r"^[0-9a-f]{12}$")


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
def config_path(logs_dir):
    """This machine's file. Gitignored: netid, key path, account."""
    return os.path.join(logs_dir, ".vacc.json")


def shared_config_path(logs_dir):
    """The tracked one, beside the app: where the cluster is, and the map."""
    return os.path.join(os.path.dirname(os.path.abspath(logs_dir)),
                        "vacc.json")


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (OSError, ValueError):
        return {}


def load_config(logs_dir):
    """Where the cluster is, and who this machine is on it.

    Environment beats this machine's file, which beats the repo's -- the same
    order as the cloud config, because somebody debugging one should not have
    to learn a second set of rules.
    """
    shared = dict(_read(shared_config_path(logs_dir)))
    mine = _read(config_path(logs_dir))
    cfg = dict(shared)
    cfg.update(mine)

    netid = os.environ.get("Jarvis_VACC_NETID") or cfg.get("netid") or ""
    host = os.environ.get("Jarvis_VACC_HOST") or cfg.get("host") or DEFAULT_HOST
    key_path = cfg.get("key_path") or ""

    # A key path inside the repository is the one arrangement that turns "no
    # secret here" into a lie, so it is reported rather than used.
    key_in_repo = False
    if key_path:
        repo = os.path.dirname(os.path.dirname(os.path.abspath(logs_dir)))
        try:
            key_in_repo = os.path.commonpath(
                [os.path.abspath(key_path), repo]) == repo
        except ValueError:                          # different drives
            key_in_repo = False

    home = "/gpfs1/home/%s/%s/%s" % (netid[0], netid[1], netid) if len(netid) > 1 else ""
    return {
        "host": host,
        "netid": netid,
        "key_path": key_path,
        "key_in_repo": key_in_repo,
        "account": cfg.get("account") or "",
        # Two roots, because they have different lifetimes. The workspace is
        # backed up and holds code, specs and answers; scratch is purged
        # without notice and holds copies of recordings, which is the only
        # thing that can be lost without losing anything.
        "workspace": cfg.get("workspace") or (home + "/jarvis" if home else ""),
        "scratch": cfg.get("scratch")
        or ("/gpfs2/scratch/%s/jarvis" % netid if netid else ""),
        # Where this person's own work already lives on the cluster, which is
        # NOT the same as where Jarvis puts things. Measured on the real
        # account: `/gpfs2/scratch/sakhava1` holds 1.3 TB and 120 recordings
        # that predate any of this, across four projects -- so the cluster is
        # not an empty machine waiting to be filled, it is somewhere the work
        # is already happening. Scanned for recordings; never written to.
        "scratch_root": cfg.get("scratch_root")
        or ("/gpfs2/scratch/%s" % netid if netid else ""),
        "partition": cfg.get("partition") or "general",
        "modules": list(cfg.get("modules") or []),
        "env": cfg.get("env") or "",
        # Lab-wide: [{"unc": "//server/share", "vacc": "/netfiles/share"}].
        "path_map": list(cfg.get("path_map") or []),
        "host_fingerprint": cfg.get("host_fingerprint") or "",
        "enabled": bool(cfg.get("enabled", True)),
        "needs_netid": not netid,
        "configured": bool(netid and host and cfg.get("enabled", True)),
    }


def save_shared_config(logs_dir, **patch):
    """The tracked file: the cluster and the map. Never a netid."""
    patch.pop("netid", None)
    patch.pop("key_path", None)
    p = shared_config_path(logs_dir)
    cur = _read(p)
    cur.update({k: v for k, v in patch.items() if v is not None})
    cur["_note"] = (
        "Where the VACC is and which shares it mounts. Tracked on purpose, "
        "so a clone knows the lab-wide facts. Who you are on it is NOT here: "
        "that lives in GUI_logs/.vacc.json, which git ignores.")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cur, fh, indent=2, sort_keys=True)
    os.replace(tmp, p)
    return cur


def save_config(logs_dir, **patch):
    """This machine's file: netid, key path, account."""
    p = config_path(logs_dir)
    cur = _read(p)
    cur.update({k: v for k, v in patch.items() if v is not None})
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cur, fh, indent=2, sort_keys=True)
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return cur


# --------------------------------------------------------------------------
# The one place a subprocess is spawned
# --------------------------------------------------------------------------
class SSHError(RuntimeError):
    """A call to the cluster that did not come back with an answer."""

    def __init__(self, message, kind="failed", stderr=""):
        super().__init__(message)
        # So a caller can tell "no ssh on this machine" from "the key was
        # refused" from "the login node is busy" without parsing English.
        self.kind = kind
        self.stderr = (stderr or "")[:2000]


def have_ssh():
    return bool(shutil.which("ssh"))


def _popen_kwargs():
    """`sysinfo`'s, plus one flag it has no reason to carry.

    `popen_kwargs()` returns CREATE_NEW_PROCESS_GROUP so a tree can be killed.
    That is enough for `runner.py`, which spawns from a console app where one
    more console changes nothing visible. This spawns from a Flask thread
    every few seconds for as long as a job runs -- six hours at one poll every
    ten seconds is two thousand windows flashing over whatever the person is
    actually doing.
    """
    kw = dict(sysinfo.popen_kwargs() or {})
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if flag:
        kw["creationflags"] = kw.get("creationflags", 0) | flag
    return kw


def _ssh(cfg, remote_command, stdin=None, timeout=45):
    """Run one command on the cluster and return its stdout.

    The ONLY place this module starts a process. Everything else goes through
    it, so the timeout, the kill and the option list are decided once.

    `remote_command` is a string because that is what ssh sends: there is no
    argv on the far side, the login shell parses it. Passing a list to
    `subprocess` protects the LOCAL command line and nothing else, which is
    the mistake this docstring exists to stop somebody making. Build the
    string with `shlex.quote`, or better, send data on `stdin` and keep paths
    out of it altogether.
    """
    if not have_ssh():
        raise SSHError("No ssh on this machine.", "no-ssh")
    if not cfg.get("netid"):
        raise SSHError("No VACC netid set.", "unconfigured")

    cmd = ["ssh"] + list(SSH_OPTS)
    if cfg.get("key_path"):
        cmd += ["-i", cfg["key_path"], "-o", "IdentitiesOnly=yes"]
    cmd += ["%s@%s" % (cfg["netid"], cfg["host"]), remote_command]

    try:
        # BINARY pipes, and the encoding done here by hand.
        #
        # `text=True` wraps stdin in a TextIOWrapper with platform newline
        # translation, so on Windows every "\n" in a script written here
        # arrives on the login node as "\r\n". bash then reads the last line
        # of a one-line script as `fi\r` and reports `syntax error: unexpected
        # end of file`, and -- the version of this that cost the most time --
        # a `$(whoami)` inside a `printf` picks the stray CR up and returns
        # `sakhava1\r`, which produced a malformed answer from a cluster that
        # was replying perfectly. It looked like the login node doing
        # something strange to command substitution. It was this line.
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, **_popen_kwargs())
    except OSError as exc:
        raise SSHError("Could not start ssh: %s" % exc, "no-ssh")

    try:
        payload = stdin.encode("utf-8") if isinstance(stdin, str) else stdin
        out, err = proc.communicate(payload, timeout=timeout)
        out = (out or b"").decode("utf-8", "replace")
        err = (err or b"").decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        # The whole tree, not just ssh: it may have spawned a helper, and a
        # half-killed connection holds the port until it times out anyway.
        sysinfo.kill_tree(proc)
        try:
            proc.communicate(timeout=5)
        except Exception:                            # noqa: BLE001
            pass
        raise SSHError("The cluster did not answer within %ds." % timeout,
                       "timeout")

    if proc.returncode != 0:
        kind = "failed"
        low = (err or "").lower()
        if "permission denied" in low or "publickey" in low:
            kind = "auth"
        elif "host key verification failed" in low:
            kind = "host-key"
        elif ("could not resolve" in low or "connection timed out" in low
              or "connection refused" in low or "network is unreachable" in low):
            kind = "unreachable"
        raise SSHError(_why(kind, err), kind, err)
    return out


def _why(kind, err):
    """What to put in front of a person, rather than what ssh said."""
    if kind == "auth":
        return ("The cluster refused the key. Run `ssh %s` once by hand -- if "
                "that asks for a password, the key is not installed there yet."
                % DEFAULT_HOST)
    if kind == "host-key":
        return ("The cluster's host key has changed. That is either a "
                "reinstall or something worth asking about; Jarvis will not "
                "accept it on its own.")
    if kind == "unreachable":
        return "Could not reach the cluster from here."
    if kind == "timeout":
        # `_ssh` writes its own version of this with the actual number of
        # seconds in it, so this branch is for anybody else who asks. It is
        # here because falling through to "returned an error" would describe
        # a connection that never answered as one that answered badly.
        return "The cluster did not answer in time."
    if kind == "no-ssh":
        return "There is no ssh client on this machine."
    if kind == "unconfigured":
        return "No VACC account is set up on this machine."
    return (err or "").strip().splitlines()[-1] if (err or "").strip() else \
        "The cluster returned an error."


# --------------------------------------------------------------------------
# One probe, one round trip
# --------------------------------------------------------------------------
# Everything the status chip wants, asked once. Written as a shell script
# rather than five calls because on Windows there is no connection to reuse
# and five calls is five handshakes.
#
# `squeue` is asked only about this user; `quota` is best-effort because not
# every cluster answers it the same way and a missing quota must not fail a
# probe that otherwise worked.
_PROBE = r"""
set -u
echo "whoami=$(whoami)"
echo "host=$(hostname -s)"
echo "queued=$(squeue -u "$USER" -h -t PD 2>/dev/null | wc -l)"
echo "running=$(squeue -u "$USER" -h -t R 2>/dev/null | wc -l)"
echo "partitions=$(sinfo -h -o '%P' 2>/dev/null | tr -d ' *' | paste -sd, -)"
echo "home=$HOME"
echo "end=1"
"""

# Asked only when somebody asks, never on the routine probe.
#
# `quota -s` on this login node does not return: measured at 1 ms for whoami,
# 6 ms for squeue and sinfo, and a flat 5003 ms for the quota -- which is the
# `timeout 5` expiring, every single time, for an answer that never arrives.
# It asks GPFS and NFS how full they are and waits for both.
#
# Leaving it in the probe made a 0.4 s round trip into a 5.4 s one and put
# that on a background loop against a shared login node, for a field that is
# usually empty. It is worth having on a button.
_QUOTA = r"""
timeout 20 quota -s 2>/dev/null | tail -n +3 | tr -s ' ' | paste -sd'|' -
"""
# One `key=value` per line, parsed in Python, rather than the shell
# assembling JSON with printf.
#
# The JSON version returned `{"whoami":"sakhava1<CR>", ...` -- unparseable,
# from a cluster that was answering every question correctly. The cause was
# not on the cluster at all: `_ssh` wrapped stdin in a text pipe, Windows
# turned every newline in the script into CRLF, and each stray CR was picked
# up by the `$(...)` on its line. That is fixed at the source now (see the
# Popen call), so this format is no longer load-bearing for it.
#
# It is kept anyway, because the failure taught the general point: a format
# where a stray newline is a line ending rather than a syntax error does not
# care, and this one does not need quoting rules to survive a login script.
#
# `timeout 5` on the quota is not defensiveness either. Measured on
# login.vacc.uvm.edu: `quota -s` never returns -- still nothing after twenty
# seconds, while whoami, hostname, squeue and sinfo each answer at once. It
# asks GPFS and NFS how full they are and waits for both. Unguarded it took
# the whole probe with it, so the chip said "the cluster did not answer"
# about a cluster that was answering fine.


def readable_roots(cfg, timeout=40):
    """Which mapped shares this ACCOUNT can actually open, not just which
    ones the cluster mounts.

    The two are different, and finding out which cost an afternoon.
    `/netfiles/bigdata_jbarry` is mounted exactly where the path map says --
    `ls -d` finds it, the rule is right, and 357 of this lab's recordings
    resolve onto it. It is also `drwxrws--- jbarry4 root`, so the only
    account that can read it is the PI's: every lab member's primary group is
    `pi-jbarry4`, and the share is grouped to `root`, which nobody is in.

    A path map is a lab-wide fact and stays one. Whether the person sitting
    here can read what it points at is a different question with a different
    answer per account, and answering the first while being asked the second
    is how somebody spends a morning debugging a job that was never going to
    be able to open its input.

    One call for every rule, and the answers are per root rather than per
    recording because that is the granularity permissions actually have.
    """
    rules = [r for r in (cfg.get("path_map") or []) if r.get("vacc")]
    if not rules:
        return {}
    lines = []
    for rule in rules:
        p = str(rule["vacc"])
        lines.append(
            'if [ ! -e %s ]; then echo "%s=missing";'
            ' elif [ -r %s ] && [ -x %s ]; then echo "%s=ok";'
            ' else echo "%s=denied"; fi' % (q(p), p, q(p), q(p), p, p))
    raw = _ssh(cfg, "bash -s", stdin="\n".join(lines) + "\n", timeout=timeout)
    out = {}
    for line in (raw or "").splitlines():
        line = line.strip()
        if "=" in line:
            k, _, v = line.rpartition("=")
            if v in ("ok", "denied", "missing"):
                out[k] = v
    return out


_INVENTORY = r"""
find %s -maxdepth 7 -name 'CSC1.ncs' -print0 2>/dev/null | while IFS= read -r -d '' f; do
  d=$(dirname "$f")
  n=$(ls "$d"/CSC*.ncs 2>/dev/null | wc -l)
  sz=$(stat -c %%s "$f" 2>/dev/null)
  printf 'rec\t%%s\t%%s\t%%s\n' "$n" "$sz" "$d"
done
echo "end=1"
"""


def inventory(cfg, root=None, timeout=180):
    """Every recording the cluster already holds, found by looking.

    Not a record of what Jarvis put there -- a listing of what is actually on
    the filesystem right now. Scratch is purged without notice, so anything
    remembered about it is a claim about the past; the only honest answer to
    "is it still there" is to ask, and asking costs one connection.

    A recording is a folder with a `CSC1.ncs` in it, which is the same thing
    `discovery.py` decides locally, so the two agree about what counts.

    The path is printed LAST on each line and the fields are tab-separated,
    because these paths contain spaces -- `KCNT1 Urethane/`, `DEWEY GUI
    Project/`, `IED Project/` are all real -- and a path is the one field
    that can contain the delimiter of a lazier format.
    """
    root = root or cfg.get("scratch_root") or cfg.get("scratch") or ""
    if not root:
        return []
    raw = _ssh(cfg, "bash -s", stdin=_INVENTORY % q(root), timeout=timeout)
    out, done = [], False
    for line in (raw or "").splitlines():
        if line.strip() == "end=1":
            done = True
            continue
        bits = line.split("\t")
        if len(bits) < 4 or bits[0] != "rec":
            continue
        try:
            n_ch = int(bits[1])
        except ValueError:
            n_ch = 0
        try:
            first = int(bits[2])
        except ValueError:
            first = 0
        out.append({"path": bits[3], "n_channels": n_ch,
                    "first_ncs_bytes": first})
    if not done:
        raise SSHError("The listing was cut short.", "garbled", raw)
    return out


_INV = {"at": 0.0, "root": None, "list": []}
INV_TTL_S = 300.0


def inventory_cached(cfg, root=None, force=False):
    """`inventory`, but not on every page load.

    Walking scratch for `CSC1.ncs` takes about ten seconds against 120
    recordings -- cheap once, rude on a shared login node every time somebody
    opens the Sessions view. Five minutes, and a button to ask again.

    The cache is in memory and dies with the process on purpose. It is a
    listing of a filesystem that gets purged without notice; writing it down
    anywhere durable would be recording a claim that expires.
    """
    root = root or cfg.get("scratch_root") or cfg.get("scratch") or ""
    now = time.time()
    if (not force and _INV["list"] and _INV["root"] == root
            and (now - _INV["at"]) < INV_TTL_S):
        return list(_INV["list"])
    got = inventory(cfg, root)
    _INV.update(at=now, root=root, list=got)
    return list(got)


def env_path(cfg):
    """Where the analysis environment lives. On HOME, not scratch.

    It is built once and used by every job, so it belongs on the filesystem
    that is backed up rather than the one that gets purged without notice --
    a conda environment that vanishes mid-week is an afternoon, not a file.
    """
    return cfg.get("env") or _remote_path(cfg.get("workspace") or ".", "env")


def activate(cfg):
    """The shell preamble that puts the right Python on PATH.

    One function, because it is needed by the env check, by the job script,
    and by anything run by hand to debug them -- and three copies of a
    `module load` line is three chances for the thing that ran to not be the
    thing that was tested.
    """
    lines = []
    for mod in (cfg.get("modules") or []):
        lines.append("module load %s" % mod)
    env = env_path(cfg)
    if env:
        lines.append('source activate %s 2>/dev/null || '
                     'conda activate %s 2>/dev/null || true' % (q(env), q(env)))
    return "\n".join(lines)


def push_code(cfg, app_dir, timeout=180):
    """Send the backend to the cluster, so the SAME arithmetic runs there.

    A tar on stdin, not rsync. Windows ships `ssh`, `scp` and `sftp` and does
    NOT ship rsync, and requiring it would undo the whole reason this module
    shells out to OpenSSH instead of taking a dependency.

    Only what the analysis needs: `backend/` and `requirements.txt`. Not
    `GUI_logs`, which is the lab's records and none of the cluster's
    business, and not `web/`, which has nothing to do on a compute node.

    Returns the sha256 of what was sent. The remote keeps it in
    `code.sha256`, so an unchanged tree skips the upload -- a few hundred
    kilobytes is nothing, but a push on every submit is a push that happens
    while somebody is waiting.
    """
    import hashlib
    import io
    import tarfile

    buf = io.BytesIO()
    # Deterministic: same tree in, same bytes out, or the hash never matches
    # twice and the skip never fires. mtimes and uid/gid are what vary.
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for rel in _code_files(app_dir):
            full = os.path.join(app_dir, rel)
            info = tar.gettarinfo(full, arcname=rel.replace(os.sep, "/"))
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with open(full, "rb") as fh:
                tar.addfile(info, fh)
    blob = buf.getvalue()
    digest = hashlib.sha256(blob).hexdigest()

    code = _remote_path(cfg.get("workspace") or ".", "code")
    have = _ssh(cfg, "cat %s/code.sha256 2>/dev/null || true" % q(code),
                timeout=30).strip()
    if have == digest:
        return {"sha256": digest, "uploaded": False, "bytes": len(blob)}

    # Unpacked into a fresh directory and swapped in, so a push that dies
    # halfway cannot leave a half-updated backend for a job to import.
    script = (
        "set -e; mkdir -p %(c)s.new; cd %(c)s.new; tar -xf -; "
        "cd ..; rm -rf %(c)s.old; "
        "if [ -d %(c)s ]; then mv %(c)s %(c)s.old; fi; "
        "mv %(c)s.new %(c)s; rm -rf %(c)s.old; "
        "printf '%%s' %(d)s > %(c)s/code.sha256; echo PUSHED"
        % {"c": q(code), "d": q(digest)}
    )
    mk = "mkdir -p %s" % q(os.path.dirname(code) or ".")
    _ssh(cfg, mk, timeout=30)
    out = _ssh(cfg, "bash -c %s" % q(script), stdin=blob, timeout=timeout)
    if "PUSHED" not in (out or ""):
        raise SSHError("The code did not unpack on the cluster.", "push", out)
    return {"sha256": digest, "uploaded": True, "bytes": len(blob)}


def _code_files(app_dir):
    """Which files go. `backend/*.py`, the runner, and requirements."""
    out = []
    for name in sorted(os.listdir(os.path.join(app_dir, "backend"))):
        if name.endswith(".py"):
            out.append(os.path.join("backend", name))
    for name in ("requirements.txt", "vacc_run.py"):
        if os.path.isfile(os.path.join(app_dir, name)):
            out.append(name)
    return out


def env_check(cfg, timeout=90):
    """Which Python, and which libraries, the compute node would use.

    Asked and recorded rather than assumed. Two answers to the same question
    that disagree are a real result in this lab -- the whole reason
    `provenance()` now carries a version and a commit -- and "the cluster had
    a different scipy" is exactly the kind of thing nobody thinks to check
    until two numbers differ.
    """
    script = activate(cfg) + "\n" + r"""
python - <<'PYEOF' 2>&1 | tail -1
import importlib, json, sys
d = {"python": "%d.%d.%d" % sys.version_info[:3], "exe": sys.executable}
for m in ("numpy", "scipy", "fooof"):
    try:
        d[m] = importlib.import_module(m).__version__
    except Exception:
        d[m] = None
print(json.dumps(d))
PYEOF
"""
    raw = _ssh(cfg, "bash -s", stdin=script, timeout=timeout)
    line = (raw or "").strip().splitlines()[-1] if (raw or "").strip() else ""
    try:
        return json.loads(line)
    except ValueError:
        raise SSHError("Could not read the cluster's Python environment.",
                       "env", raw)


_BROWSE = r"""
D=%s
if [ ! -d "$D" ]; then echo "err=not a directory"; exit 0; fi
echo "at=$D"
for f in "$D"/*; do
  [ -e "$f" ] || continue
  n=$(basename "$f")
  if [ -d "$f" ]; then
    # Is it a recording? One CSC file is the same test discovery.py makes
    # locally, so the two agree about what counts as one.
    if [ -e "$f/CSC1.ncs" ]; then
      echo "rec	$(ls "$f"/CSC*.ncs 2>/dev/null | wc -l)	$n"
    else
      echo "dir	0	$n"
    fi
  fi
done
echo "end=1"
"""


def browse(cfg, path=None, timeout=60):
    """One level of the cluster's filesystem, as folders and recordings.

    Folders only. The point of looking at a cluster from here is to find
    recordings, and a listing that also carried every `.ncs` would be four
    thousand lines to show one folder. A recording is marked as one -- by
    the same test `discovery.py` makes locally, the presence of `CSC1.ncs`
    -- so the tree can stop there rather than descending into sixty-four
    files that are one thing.
    """
    root = path or cfg.get("scratch_root") or cfg.get("scratch") or ""
    if not root:
        return {"at": None, "dirs": [], "recordings": [], "error": "nowhere to look"}
    # Refuse to climb out of what the config points at, the same way
    # `_remote_path` does: this is a path from a browser.
    root = str(root)
    if ".." in root.split("/"):
        raise ValueError("Refusing a path containing '..'")
    raw = _ssh(cfg, "bash -s", stdin=_BROWSE % q(root), timeout=timeout)
    at, dirs, recs, done, err = root, [], [], False, None
    for line in (raw or "").splitlines():
        line = line.rstrip()
        if line.startswith("at="):
            at = line[3:]
            continue
        if line.startswith("err="):
            err = line[4:]
            continue
        if line.strip() == "end=1":
            done = True
            continue
        bits = line.split("\t")
        if len(bits) < 3:
            continue
        name = bits[2]
        if bits[0] == "rec":
            try:
                n_ch = int(bits[1])
            except ValueError:
                n_ch = 0
            recs.append({"name": name, "path": at.rstrip("/") + "/" + name,
                         "n_channels": n_ch})
        elif bits[0] == "dir":
            dirs.append({"name": name, "path": at.rstrip("/") + "/" + name})
    if err:
        return {"at": at, "dirs": [], "recordings": [], "error": err}
    if not done:
        raise SSHError("The listing was cut short.", "garbled", raw)
    dirs.sort(key=lambda d: d["name"].lower())
    recs.sort(key=lambda d: d["name"].lower())
    return {"at": at, "dirs": dirs, "recordings": recs, "error": None}


def quota(cfg, timeout=40):
    """How full the filesystems are. Slow on purpose to ask, so ask rarely.

    Separate from `probe` because it is the one question this cluster does
    not answer quickly -- and a field that is usually empty is not worth
    putting five seconds on a background loop for.
    """
    raw = _ssh(cfg, "bash -s", stdin=_QUOTA, timeout=timeout)
    return (raw or "").strip()


def _parse_probe(raw):
    """`key=value` lines into a dict. Anything else on the line is ignored.

    A login node prints things -- a banner, a module message, somebody's
    `.bashrc` being helpful -- and none of it looks like `key=value`, so
    none of it lands here.
    """
    got = {}
    for line in (raw or "").splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if k.isidentifier():
            got[k] = v.strip()
    return got


def _root_checks(cfg):
    """Shell that tests each mapped share, as `rootN=<path>|<verdict>`.

    Appended to the probe rather than sent on its own, because the rule here
    is one connection per question-asking, not one per question.
    """
    out = []
    for i, rule in enumerate([r for r in (cfg.get("path_map") or [])
                              if r.get("vacc")]):
        p = str(rule["vacc"])
        out.append(
            'if [ ! -e %s ]; then echo "root%d=%s|missing";'
            ' elif [ -r %s ] && [ -x %s ]; then echo "root%d=%s|ok";'
            ' else echo "root%d=%s|denied"; fi'
            % (q(p), i, p, q(p), q(p), i, p, i, p))
    return "\n".join(out)


def probe(cfg, timeout=90):
    """Ask the cluster everything the interface wants, in one connection."""
    # The root checks go BEFORE the `end=1` line, so a connection cut halfway
    # cannot produce an answer that looks complete but has lost them.
    script = _PROBE.replace('echo "end=1"',
                            _root_checks(cfg) + '\necho "end=1"')
    raw = _ssh(cfg, "bash -s", stdin=script, timeout=timeout)
    got = _parse_probe(raw)
    # `end=1` is the last line the script writes, so its presence is how a
    # complete answer is told from one cut short by a dropped connection --
    # which otherwise arrives as a plausible dict with fields missing.
    if not got.pop("end", None):
        raise SSHError("The cluster's answer was cut short.", "garbled", raw)
    got["partitions"] = [p for p in (got.get("partitions") or "").split(",") if p]
    for n in ("queued", "running"):
        try:
            got[n] = int(got.get(n) or 0)
        except (TypeError, ValueError):
            got[n] = None
    # Which mapped shares this ACCOUNT can open, which is not the same
    # question as which ones the cluster mounts -- see `readable_roots`.
    roots = {}
    for k in [k for k in got if k.startswith("root")]:
        path, _, verdict = got.pop(k).partition("|")
        if path:
            roots[path] = verdict or "unknown"
    got["roots"] = roots
    return got


# --------------------------------------------------------------------------
# Status, cached, and never on the path of a request
# --------------------------------------------------------------------------
_STATE = {
    "at": 0.0, "ok": False, "why": "not checked yet", "probe": None,
    "kind": None, "failures": 0, "retry_at": 0.0,
}
_LOCK = threading.Lock()
LOGS_DIR = None


def configure(logs_dir):
    """Called once by app.py, the same way cfc and continuity are."""
    global LOGS_DIR
    LOGS_DIR = logs_dir


def _backoff(n):
    """Wait longer each time it fails, and stop hammering a login node.

    Capped at five minutes: a cluster that has been down for an hour is not
    more likely to be up if we ask every thirty seconds, and a login node is
    shared with everybody else's interactive work.
    """
    return min(300.0, 15.0 * (2 ** max(0, n - 1)))


def refresh(force=False):
    """Ask the cluster how it is. Returns the cached answer if it is fresh.

    Called by a background thread, never by a route -- a badge that renders on
    every page load is the natural and wrong place to spend a ten-second
    connect timeout.
    """
    cfg = load_config(LOGS_DIR) if LOGS_DIR else {"configured": False}
    now = time.time()
    with _LOCK:
        fresh = (now - _STATE["at"]) < TTL_S
        waiting = now < _STATE["retry_at"]
        if not force and (fresh or waiting):
            return dict(_STATE)

    if not cfg.get("configured"):
        with _LOCK:
            _STATE.update(at=now, ok=False, probe=None, kind="unconfigured",
                          why=("No VACC account set up on this machine yet."
                               if cfg.get("needs_netid")
                               else "VACC is switched off here."))
            return dict(_STATE)
    if not have_ssh():
        with _LOCK:
            _STATE.update(at=now, ok=False, probe=None, kind="no-ssh",
                          why="No ssh client on this machine.")
            return dict(_STATE)

    try:
        got = probe(cfg)
    except SSHError as exc:
        with _LOCK:
            _STATE["failures"] += 1
            _STATE.update(at=now, ok=False, probe=None, kind=exc.kind,
                          why=str(exc),
                          retry_at=now + _backoff(_STATE["failures"]))
            return dict(_STATE)
    except Exception as exc:                         # noqa: BLE001
        # A probe must never take down the loop that calls it.
        with _LOCK:
            _STATE["failures"] += 1
            _STATE.update(at=now, ok=False, probe=None, kind="failed",
                          why=str(exc)[:200],
                          retry_at=now + _backoff(_STATE["failures"]))
            return dict(_STATE)

    with _LOCK:
        _STATE.update(at=now, ok=True, probe=got, kind=None, why="",
                      failures=0, retry_at=0.0)
        return dict(_STATE)


def status():
    """What to show. Reads the cache; never connects."""
    cfg = load_config(LOGS_DIR) if LOGS_DIR else {"configured": False,
                                                 "needs_netid": True}
    with _LOCK:
        st = dict(_STATE)
    got = st.get("probe") or {}
    return {
        "ok": True,
        "configured": bool(cfg.get("configured")),
        "needs_netid": bool(cfg.get("needs_netid")),
        "key_in_repo": bool(cfg.get("key_in_repo")),
        "have_ssh": have_ssh(),
        "available": bool(st.get("ok")),
        "why": st.get("why") or "",
        "kind": st.get("kind"),
        "checked_at": st.get("at") or None,
        "host": cfg.get("host"),
        "netid": cfg.get("netid"),
        "partition": cfg.get("partition"),
        "workspace": cfg.get("workspace"),
        "scratch": cfg.get("scratch"),
        "queued": got.get("queued"),
        "running": got.get("running"),
        "partitions": got.get("partitions") or [],
        "quota": got.get("quota") or "",
        "n_rules": len(cfg.get("path_map") or []),
        # Per mapped share: ok | denied | missing. The distinction matters
        # enough to be on the status payload rather than inferred, because
        # "VACC mounts your data" and "you can read it" came apart the first
        # time this was pointed at the real cluster: /netfiles/bigdata_jbarry
        # is there, 357 recordings resolve onto it, and it is mode
        # drwxrws--- owned by jbarry4:root -- so every lab member's account
        # is refused by a share their own primary group was made for.
        "roots": got.get("roots") or {},
        "denied_roots": sorted(k for k, v in (got.get("roots") or {}).items()
                               if v == "denied"),
    }


def loop(stop=None, every=30.0):
    """Keep `status()` worth reading. Started by app.py in a daemon thread.

    The loop itself must not die: a probe that raises takes one iteration
    with it and nothing else, because the alternative is a status chip that
    silently stops updating and reads as "fine" for ever.
    """
    while not (stop and stop.is_set()):
        try:
            refresh()
        except Exception:                            # noqa: BLE001
            pass
        for _ in range(int(max(1.0, every))):
            if stop and stop.is_set():
                return
            time.sleep(1.0)


# --------------------------------------------------------------------------
# Building a remote path without building a remote command
# --------------------------------------------------------------------------
def _remote_path(root, *parts):
    """Join, and refuse anything that could climb out of the root.

    `vacc.json` is tracked, so any clone can edit the path map, and a rule
    that produced `../..` would be a rule that reached any file the account
    can read. Checked here rather than trusted there.
    """
    out = str(root or "").rstrip("/")
    for p in parts:
        p = str(p).strip("/")
        if not p or p == "." or ".." in p.split("/"):
            raise ValueError("Refusing a remote path containing '..': %r" % p)
        out += "/" + p
    return out


def q(text):
    """Quote one value for the remote shell.

    Lab paths contain spaces, ampersands, brackets and apostrophes -- `VACC
    Code/KCNT1 Urethane/` is in this repository -- and every one of them is a
    shell metacharacter on the far side.
    """
    return shlex.quote(str(text))


def new_rid():
    """A name for one run, safe to put in a path and checkable on sight."""
    import uuid
    return uuid.uuid4().hex[:12]


def check_rid(rid):
    if not RID_RE.match(str(rid or "")):
        raise ValueError("Not a run id: %r" % (rid,))
    return str(rid)


# --------------------------------------------------------------------------
# What the cluster can reach
#
# Four states, and the fourth is the one that matters:
#
#   native      the cluster mounts this share already. No transfer, ever.
#   staged      a copy is in scratch. A cache, never the only copy.
#   local-only  it exists, on a disk the cluster cannot see.
#   unknown     nobody has established which. Says nothing.
#
# `unknown` exists because a scanned row often has no gid -- exact ids are
# only minted when headers are read -- and reading a missing field as "no"
# is a mistake this codebase has already made once, in `canOpen`, where it
# hid every recording that was certainly openable. A recording nobody has
# checked is not a recording that needs uploading.
# --------------------------------------------------------------------------
NATIVE = "native"
STAGED = "staged"
LOCAL_ONLY = "local-only"
UNKNOWN = "unknown"

# Drive letter -> UNC, as observed on THIS machine. Filled by `drive_map`.
_DRIVES = {"at": 0.0, "map": {}}
_DRIVES_TTL = 300.0


def _norm(path):
    """One spelling to compare with: forward slashes, no trailing one.

    The registry holds both `Y:\\Jeremy3\\...` and
    `//netfiles03.uvm.edu/bigdata_jbarry/Jeremy3/...` for the same tree,
    because they were written by different machines through different mounts.
    """
    p = str(path or "").replace("\\", "/")
    while p.endswith("/") and len(p) > 1:
        p = p[:-1]
    return p


def drive_map(force=False):
    """Which drive letters on THIS machine are which UNC shares.

    A drive letter is not a portable fact and must never be written into the
    tracked config: `Y:` here and `Y:` on the rig are two different shares,
    and on the machine this was written on `net use` reports nothing at all
    while 2544 recorded paths still begin with `Y:`. So the letter is
    resolved where it means something -- on the machine that has it mounted
    -- and what travels is the UNC it resolved to.

    Windows only; everything else has no such concept and gets {}.
    """
    now = time.time()
    if not force and (now - _DRIVES["at"]) < _DRIVES_TTL:
        return dict(_DRIVES["map"])
    out = {}
    if os.name == "nt":
        try:
            res = subprocess.run(["net", "use"], capture_output=True,
                                 text=True, timeout=10, **_popen_kwargs())
            for line in (res.stdout or "").splitlines():
                m = re.search(r"([A-Za-z]:)\s+(\\\\[^\s]+)", line)
                if m:
                    out[m.group(1).lower()] = _norm(m.group(2))
        except Exception:                            # noqa: BLE001
            pass                                     # no mappings is an answer
    _DRIVES.update(at=now, map=out)
    return dict(out)


def resolve_path(path, cfg, drives=None):
    """One local path, in the cluster's terms.

    Returns `(state, remote_or_None, why)`. A drive letter is expanded to its
    UNC first -- on this machine, if this machine knows it -- and the UNC is
    then matched against the lab-wide rules, which is the only half that is
    portable.
    """
    p = _norm(path)
    if not p:
        return (UNKNOWN, None, "no path")

    if len(p) >= 2 and p[1] == ":":
        unc = (drives if drives is not None else drive_map()).get(p[:2].lower())
        if not unc:
            return (LOCAL_ONLY, None,
                    "%s is not a share this machine has mounted" % p[:2])
        p = unc + p[2:]

    low = p.lower()
    for rule in (cfg.get("path_map") or []):
        pre = _norm(rule.get("unc")).lower()
        if not pre:
            continue
        if low == pre or low.startswith(pre + "/"):
            tail = p[len(pre):].lstrip("/")
            remote = _norm(rule.get("vacc")).rstrip("/")
            return (NATIVE, remote + ("/" + tail if tail else ""),
                    "on %s, which the cluster mounts" % rule.get("unc"))

    if p.startswith("//"):
        return (LOCAL_ONLY, None, "on a share the cluster does not mount")
    return (LOCAL_ONLY, None, "on a local disk")


def resolve_gid(gid, paths, cfg, drives=None, staged=None):
    """A recording, in the cluster's terms. THE entry point.

    Not `resolve_path`, and the difference is the whole design. A recording
    carries every path it has ever been opened from on ANY machine, unioned
    across the lab -- so the machine asking may hold only a drive letter it
    cannot expand while some colleague's shard holds the UNC spelling of the
    very same folder. Asking about the recording rather than about the path
    in front of you is what makes those 2544 `Y:` paths answerable from a
    computer with no `Y:` mounted.

    `staged` is what the cluster said it has, keyed by gid. Checked second:
    a recording the cluster can read in place never needs a copy, and a
    staged copy of one is a cache to be ignored rather than preferred.
    """
    best = (UNKNOWN, None, "no path on record")
    for p in (paths or []):
        state, remote, why = resolve_path(p, cfg, drives)
        if state == NATIVE:
            return {"gid": gid, "state": NATIVE, "remote": remote,
                    "why": why, "via": p}
        if state == LOCAL_ONLY and best[0] == UNKNOWN:
            best = (LOCAL_ONLY, None, why)

    if staged and gid in staged:
        got = staged[gid] or {}
        if got.get("conflict"):
            # More than one folder on the cluster answers to this recording,
            # and nothing here can tell which is meant. Reported rather than
            # resolved: picking one silently is how the wrong data gets
            # analysed under the right name.
            return {"gid": gid, "state": UNKNOWN, "remote": None, "via": None,
                    "why": ("the cluster has %d folders that all claim to be "
                            "this recording, so which one is meant is not "
                            "established: %s"
                            % (len(got["conflict"]),
                               "; ".join(got["conflict"][:3]))),
                    "conflict": got["conflict"]}
        return {"gid": gid, "state": STAGED, "remote": got.get("path"),
                "why": "a copy is in cluster scratch", "via": None,
                "staged_at": got.get("staged_at")}

    return {"gid": gid, "state": best[0], "remote": None, "why": best[2],
            "via": None}


def resolve_many(rows, cfg, staged=None):
    """Every recording at once, with the drive map read once for the lot.

    `rows` is [{"gid": ..., "paths": [...]}]. One `net use` for four thousand
    recordings rather than four thousand, which is the same discipline
    `sessreg.summary` applies to `os.path.isdir`.
    """
    drives = drive_map()
    out = {}
    for row in rows or []:
        gid = row.get("gid")
        if not gid:
            continue
        out[gid] = resolve_gid(gid, row.get("paths") or [], cfg,
                               drives, staged)
    return out


def histogram(resolved):
    """How many of each state. What you read before writing any staging."""
    counts = {NATIVE: 0, STAGED: 0, LOCAL_ONLY: 0, UNKNOWN: 0}
    for got in (resolved or {}).values():
        counts[got.get("state", UNKNOWN)] = counts.get(got.get("state",
                                                               UNKNOWN), 0) + 1
    return counts


# --------------------------------------------------------------------------
# Slurm: asking for the right box, and knowing how the job ended
# --------------------------------------------------------------------------
# What a partition will take. The default walltime on this cluster is THIRTY
# MINUTES if `--time` is omitted, and `sbatch` reports success long before a
# job dies of it -- which makes "forgot --time" the most common way a run
# fails, and the failure arrives 30 minutes later looking like a crash.
PARTITIONS = [
    ("short", 3 * 3600),
    ("general", 48 * 3600),
    ("week", 7 * 24 * 3600),
]

# How much longer than the estimate to ask for. An estimate is a median and a
# walltime is a guillotine, so they are not the same quantity: being wrong by
# 3x costs nothing but queue priority, and being wrong by 1% costs the run.
SAFETY = 3.0
MIN_WALL_S = 600


def slurm_request(seconds, megasamples=1.0, partition=None):
    """What to ask slurm for, from what the estimator already knows.

    The estimate this multiplies is the same one the local run quotes, made
    from rates this machine measured -- so it is an estimate of the wrong
    computer until the cluster has run something, which is exactly why
    SAFETY is 3x and not 1.2x.
    """
    wall = max(MIN_WALL_S, int(float(seconds or 0) * SAFETY))
    if not partition:
        partition = "general"
        for name, cap in PARTITIONS:
            if wall <= cap:
                partition = name
                break
    cap = dict(PARTITIONS).get(partition)
    if cap:
        wall = min(wall, cap - 60)
    # Memory from the data volume, with a floor that covers the interpreter
    # and the imports. Refined by what `sacct` reports as MaxRSS, which is
    # worth more than any formula here.
    mem_gb = max(4, int(float(megasamples or 1.0) * 0.06) + 4)
    return {
        "partition": partition,
        "time": "%02d:%02d:%02d" % (wall // 3600, (wall % 3600) // 60, wall % 60),
        "time_s": wall,
        "mem": "%dG" % mem_gb,
        "cpus": 4,
    }


# How slurm says a job ended, and what that means to a person. The mapping
# matters more than it looks: three of these are NOT failures of the work and
# telling somebody "it failed" when the cluster ran out of time is how they
# go looking for a bug in their analysis.
TERMINAL = {
    "COMPLETED": "done",
    "CANCELLED": "canceled",
    "TIMEOUT": "timeout",
    "OUT_OF_MEMORY": "oom",
    "FAILED": "failed",
    "NODE_FAIL": "node-fail",
    "PREEMPTED": "preempted",
    "BOOT_FAIL": "node-fail",
    "DEADLINE": "timeout",
    "REVOKED": "canceled",
}
ACTIVE = ("PENDING", "RUNNING", "CONFIGURING", "COMPLETING", "SUSPENDED",
          "RESIZING", "REQUEUED")


def read_state(text):
    """The state word out of squeue or sacct, however it was decorated.

    `CANCELLED by 123456` is a real sacct state, and so is `COMPLETED+`.
    """
    s = (text or "").strip().upper()
    s = s.split(" BY ")[0].strip().rstrip("+")
    return s


def outcome_for(state):
    """(kind, sentence) for a finished job. `None` while it is still going."""
    s = read_state(state)
    if not s or s in ACTIVE:
        return None
    kind = TERMINAL.get(s, "failed")
    if kind == "done":
        return ("done", "")
    if kind == "timeout":
        return ("timeout",
                "It needed more time than it was given. Nothing is wrong with "
                "the analysis -- resubmit it with a longer walltime.")
    if kind == "oom":
        return ("oom",
                "It ran out of memory on the node. Resubmit it with more, "
                "which Jarvis will do at twice the request.")
    if kind == "node-fail":
        return ("node-fail",
                "The compute node failed underneath it. That is the "
                "cluster's problem rather than yours; it will be retried "
                "once.")
    if kind == "preempted":
        return ("preempted",
                "A job with a prior claim on that node took it back.")
    if kind == "canceled":
        return ("canceled", "Cancelled.")
    return ("failed", "The job failed on the cluster.")


# A job that is in neither `squeue` nor `sacct` has not necessarily vanished.
# slurmdbd lags behind the controller, so there is a window of seconds where
# a finished job is in neither -- and a poller that calls that "gone" fails
# runs that actually succeeded.
LAG_GRACE_S = 120.0


def _runner(cfg, ssh=None):
    """How this call reaches the cluster.

    One seam, so `poll_states`, `cancel` and a run driver all go through the
    same place and a test can stand in for the login node once rather than
    three times. `_ssh` is looked up when the call is made, not when this is
    built, so replacing the module attribute still works.
    """
    if ssh is not None:
        return ssh
    return lambda cmd, stdin=None, timeout=45: _ssh(cfg, cmd, stdin=stdin,
                                                    timeout=timeout)


def poll_states(cfg, job_ids, timeout=30, ssh=None):
    """`{slurm_id: state}` for a batch of jobs, in ONE connection.

    squeue first because it is authoritative while a job lives, then sacct
    for everything squeue no longer knows about. Both in one invocation --
    there is no connection to reuse on Windows, so two calls is two
    handshakes, every poll, for as long as the job runs.
    """
    ids = [str(int(j)) for j in job_ids if str(j).strip()]
    if not ids:
        return {}
    joined = ",".join(ids)
    script = (
        "squeue -h -j %s -o '%%i %%T' 2>/dev/null; "
        "echo '--'; "
        "sacct -n -X -j %s -o 'JobID,JobIDRaw,State,Elapsed,MaxRSS' -P 2>/dev/null"
        % (q(joined), q(joined))
    )
    # JobIDRaw, and it is not belt and braces.
    #
    # The number `sbatch --parsable` hands back is the RAW id. For anything
    # in a job array sacct PRINTS something else -- measured on this cluster:
    # `sacct -j 999999` answers `999467_3|999999|COMPLETED`, the array-and-
    # task form beside the raw one. Keying on what it prints means a job that
    # finished an hour and forty-nine minutes ago is not found under the id we
    # submitted, `wait` reads that as "in neither squeue nor sacct", and a
    # perfectly good run is failed as vanished once the grace period expires.
    #
    # squeue's `%i` has the same shape for array elements. It is correct for
    # the single jobs submitted today, and it is the first thing to fix when
    # arrays arrive.
    out = _runner(cfg, ssh)("bash -s", stdin=script, timeout=timeout)
    states, seen = {}, set()
    half = 0
    for line in (out or "").splitlines():
        line = line.strip()
        if line == "--":
            half = 1
            continue
        if not line:
            continue
        if half == 0:
            bits = line.split()
            if len(bits) >= 2:
                states[bits[0]] = {"state": read_state(bits[1]), "live": True}
                seen.add(bits[0])
        else:
            bits = line.split("|")
            shown = bits[0].split(".")[0]
            raw_id = (bits[1].split(".")[0] if len(bits) > 1 else "") or shown
            jid = raw_id if raw_id in ids else shown
            if jid in seen:
                continue
            states[jid] = {
                # What sacct calls it, kept for anything that shows a job id
                # to a person -- `999467_3` is what they will see in squeue.
                "job_id": shown,
                "state": read_state(bits[2] if len(bits) > 2 else ""),
                "elapsed": bits[3] if len(bits) > 3 else None,
                "max_rss": bits[4] if len(bits) > 4 else None,
                "live": False,
            }
    return states


def cancel(cfg, slurm_id=None, rid=None, timeout=25, ssh=None):
    """Stop a job. By id if we have one, by name if we do not.

    The name fallback is not belt and braces. There is a window between
    `sbatch` returning and its id being written down, and a cancel arriving
    in that window would otherwise leave a job running on a shared cluster
    with nothing pointing at it. Every job is named after its run id for
    this one reason.
    """
    bits = []
    if slurm_id:
        bits.append("scancel %s 2>/dev/null" % q(str(slurm_id)))
    if rid:
        check_rid(rid)
        bits.append("scancel -u \"$USER\" -n %s 2>/dev/null" % q(rid))
    if not bits:
        return False
    _runner(cfg, ssh)("; ".join(bits) + "; true", timeout=timeout)
    return True
