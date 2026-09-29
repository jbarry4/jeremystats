"""Uploading recordings to Jarvis Data, the lab's shared space on the cluster.

Constitution section 6d. A recording goes to

    <shared root>/Jarvis Data/<project>/<mouse>/<recording>/

keeping the folder names it has here, so the cluster copy is identified by
exactly the rules the local one is (`ids.identify` reads the path) and is
then found by the inventory like any other recording -- by looking, by
identity, with nothing written into the registry.

Three rules, all about not doing damage:

  * A file already there AT THE SAME SIZE is skipped. Re-uploading is cheap
    and resumes where it stopped; nothing is sent twice.
  * A file arrives as `<name>.part` and is renamed only when every byte is
    in, so a connection cut halfway never leaves something that looks whole.
    The listing ignores `.part`, so the next upload sends it again.
  * The local copy is only ever read. It stays the source of truth; scratch
    may be purged.

The far side is behind a small interface -- `sizes(dir)` and `put(...)` --
so the whole of this can be tested against a folder on this machine
(`LocalRemote`) without a cluster. `SshRemote` is the real one: one ssh per
file, the file streamed into it in chunks, never held in memory whole, which
is why this does not go through `vacc._ssh` (that one sends stdin at once).
"""
from __future__ import annotations

import os
import posixpath
import shutil
import subprocess

from . import sysinfo, vacc

CHUNK = 4 * 1024 * 1024


class UploadError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Where a recording goes
# --------------------------------------------------------------------------
def _part(name, what):
    """One folder name, safe to put in a remote path."""
    s = str(name or "").strip().replace("\\", "_").replace("/", "_")
    if not s or s in (".", ".."):
        raise UploadError("This recording has no %s to file it under." % what)
    return s


def destination(cfg, rec, local_dir):
    """`Jarvis Data/<project>/<mouse folder>/.../<recording>` for one recording.

    Every folder from the mouse's down to the recording's is kept, not only
    the last: the session number is often in a folder between them
    (`M1_Pten/M1ptens1oct2/2023-10-02_16-49-04`), and `ids.identify` reads it
    from the path. Mirrored as `<project>/<mouse>/<recording>` alone, that
    copy identified as a different recording -- mouse 1, no session -- and
    would never have been found. So the result is checked: a destination
    that does not identify as the same recording is refused.
    """
    from . import ids
    sh = cfg.get("shared") or vacc._shared_of(cfg)
    if not sh.get("data_path"):
        raise UploadError("No shared space is set up for VACC.")
    ident = ids.identify(local_dir)
    project = rec.get("project") or rec.get("group") or ident.get("project")
    parts = [p for p in os.path.normpath(local_dir).replace("\\", "/").split("/")
             if p and not p.endswith(":")]
    mf = ident.get("mouse_folder")
    chain = parts[parts.index(mf):] if mf in parts else parts[-3:]
    dest = vacc._remote_path(sh["data_path"], _part(project, "project"),
                             *[_part(c, "folder") for c in chain])
    want = ident.get("key") or ident.get("loose_key")
    got = ids.identify(dest)
    if want and (got.get("key") or got.get("loose_key")) != want:
        raise UploadError(
            "Its cluster copy would not be recognised as the same recording "
            "(%s here, %s there), so it would never be found. Not uploaded."
            % (want, got.get("key") or got.get("loose_key") or "nothing"))
    if not want:
        raise UploadError("Its folders do not name a mouse and a session, so "
                          "a cluster copy could not be matched back to it.")
    return dest


def local_files(local_dir):
    """[(relative posix path, size, absolute path)] under a recording."""
    out = []
    for folder, dirs, files in os.walk(local_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if name.startswith(".") or name.endswith(".part"):
                continue
            full = os.path.join(folder, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            rel = os.path.relpath(full, local_dir).replace(os.sep, "/")
            out.append((rel, size, full))
    return out


# --------------------------------------------------------------------------
# The far side
# --------------------------------------------------------------------------
class SshRemote:
    """The cluster, over ssh."""

    def __init__(self, cfg):
        self.cfg = cfg

    def sizes(self, rdir):
        """{relative path: size} of what is already there. {} if nothing."""
        script = ('D=%s\nif [ -d "$D" ]; then cd "$D" && find . -type f '
                  "! -name '*.part' -printf '%%P\\t%%s\\n'; fi\necho end=1\n"
                  % vacc.q(rdir))
        raw = vacc._ssh(self.cfg, "bash -s", stdin=script, timeout=120)
        return _parse_sizes(raw)

    def put(self, full, rdir, rel, on_bytes=None, check=None):
        """Stream one file to `rdir/rel`, arriving as .part then renamed."""
        final = posixpath.join(rdir, rel)
        vacc._remote_path(rdir, *rel.split("/"))           # refuses ..
        tmp = final + ".part"
        remote = ("mkdir -p %s && cat > %s && mv -f %s %s"
                  % (vacc.q(posixpath.dirname(final)), vacc.q(tmp),
                     vacc.q(tmp), vacc.q(final)))
        cmd = vacc.ssh_cmd(self.cfg, remote)
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, **vacc.popen_kwargs())
        try:
            with open(full, "rb") as fh:
                while True:
                    if check:
                        check()
                    block = fh.read(CHUNK)
                    if not block:
                        break
                    proc.stdin.write(block)
                    if on_bytes:
                        on_bytes(len(block))
            proc.stdin.close()
            err = proc.stderr.read().decode("utf-8", "replace")
            code = proc.wait(timeout=600)
        except BaseException:
            sysinfo.kill_tree(proc)
            raise
        if code != 0:
            raise UploadError("The cluster refused %s: %s"
                              % (rel, (err or "no reason given").strip()[:300]))


class LocalRemote:
    """A folder on this machine standing in for the cluster, for tests.
    Remote paths are placed under `base`; the same .part-then-rename."""

    def __init__(self, base):
        self.base = base

    def _p(self, rpath):
        return os.path.join(self.base, rpath.lstrip("/").replace("/", os.sep))

    def sizes(self, rdir):
        root = self._p(rdir)
        out = {}
        for folder, _dirs, files in os.walk(root):
            for name in files:
                if name.endswith(".part"):
                    continue
                full = os.path.join(folder, name)
                out[os.path.relpath(full, root).replace(os.sep, "/")] = \
                    os.path.getsize(full)
        return out

    def put(self, full, rdir, rel, on_bytes=None, check=None):
        vacc._remote_path(rdir, *rel.split("/"))
        final = self._p(posixpath.join(rdir, rel))
        os.makedirs(os.path.dirname(final), exist_ok=True)
        tmp = final + ".part"
        with open(full, "rb") as src, open(tmp, "wb") as dst:
            while True:
                if check:
                    check()
                block = src.read(CHUNK)
                if not block:
                    break
                dst.write(block)
                if on_bytes:
                    on_bytes(len(block))
        shutil.move(tmp, final)


def _parse_sizes(raw):
    out, done = {}, False
    for line in (raw or "").splitlines():
        if line.strip() == "end=1":
            done = True
            continue
        rel, _, size = line.rpartition("\t")
        if rel and size.strip().isdigit():
            out[rel] = int(size)
    if not done:
        raise UploadError("The cluster's listing was cut short.")
    return out


# --------------------------------------------------------------------------
# What would be sent, and sending it
# --------------------------------------------------------------------------
def plan_one(remote, local_dir, rdir):
    """{send: [(rel, size, full)], skip: n, bytes, n_files} for one recording."""
    files = local_files(local_dir)
    there = remote.sizes(rdir)
    send = [f for f in files if there.get(f[0]) != f[1]]
    return {"send": send, "skip": len(files) - len(send),
            "bytes": sum(f[1] for f in send), "n_files": len(files),
            "total_bytes": sum(f[1] for f in files)}


def send(remote, local_dir, rdir, plan=None, on_bytes=None, check=None,
         on_file=None):
    """Upload what `plan` says to send (or plan it now). Returns counts."""
    plan = plan or plan_one(remote, local_dir, rdir)
    sent = 0
    for i, (rel, _size, full) in enumerate(plan["send"]):
        if on_file:
            on_file(i, rel)
        remote.put(full, rdir, rel, on_bytes=on_bytes, check=check)
        sent += 1
    return {"sent": sent, "skipped": plan["skip"], "bytes": plan["bytes"]}
