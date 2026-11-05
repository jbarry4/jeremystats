# -*- coding: utf-8 -*-
"""The Lab Operations Schedule's Apps Script from the command line (clasp).

The project lives in Colony Management/Apps Script (clasp clone of the sheet's
bound script, signed in as barrylabuvm@gmail.com; the token is clasp's own,
in ~/.clasprc.json). This wraps clasp so the two ways to lose work cannot
happen quietly:

  * push overwrites the whole remote project. If someone edited in the
    browser since the last pull, push refuses and says which files.
  * the hand-pasted copies (Colony Management/VOS_Import.gs and SoftMouse
    Exports/SoftMouse_Import.gs) are mirrors now: pull writes them.

    python tools/appscript.py status          what push would change
    python tools/appscript.py pull            remote -> here (+ mirrors)
    python tools/appscript.py push            here -> remote (refuses on drift)
    python tools/appscript.py deploy "why"    push, then a new version of the
                                              web app, same /exec URL
    python tools/appscript.py versions        the project's versions
    python tools/appscript.py read SHEET [N]  first N rows of a sheet tab, as
                                              the link-readable export has them
"""
import csv
import difflib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from backend.paths import REPO_ROOT  # noqa: E402

COLONY = os.path.join(REPO_ROOT, "Colony Management")
PROJECT = os.path.join(COLONY, "Apps Script")
SHEET_ID = "1SDXG1GpRhkjq2aKri3n06nOuR8TGio9QuQsyN656ERo"
# The web app Jarvis posts to (VOS and SoftMouse). Redeploying it keeps the URL.
WEBAPP = "AKfycbyBAdW8j7j-eavAcSu_9GkA1u2wJHZc2j6gzNCoVP5qe5S2Bns5KwoLPyV5JXsVsNkvzA"
MIRRORS = {"VOS_Import.js": os.path.join(COLONY, "VOS_Import.gs"),
           "SoftMouse_Import.js": os.path.join(COLONY, "SoftMouse Exports",
                                               "SoftMouse_Import.gs")}
# What the remote looked like at the last pull: the base push compares against.
BASE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                    "Jarvis", "appscript", "last_pull")
SCRIPT_EXT = (".js", ".gs", ".html", ".json")


def clasp(*args, cwd=PROJECT, check=True):
    exe = shutil.which("clasp")
    if not exe:
        sys.exit("clasp is not installed: npm install -g @google/clasp, then clasp login")
    p = subprocess.run([exe, *args], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and p.returncode:
        sys.exit("clasp %s failed:\n%s%s" % (" ".join(args), p.stdout, p.stderr))
    return p.stdout


def _files(folder):
    out = {}
    for name in os.listdir(folder):
        if name.endswith(SCRIPT_EXT) and name != ".clasp.json":
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                out[name] = fh.read().replace("\r\n", "\n")
    return out


def _remote():
    """The remote project as it is now, pulled into a throwaway folder."""
    tmp = tempfile.mkdtemp()
    shutil.copy(os.path.join(PROJECT, ".clasp.json"), tmp)
    clasp("pull", cwd=tmp)
    got = _files(tmp)
    shutil.rmtree(tmp, ignore_errors=True)
    return got


def _diff_names(a, b):
    return sorted(n for n in set(a) | set(b) if a.get(n) != b.get(n))


def _save_base(files):
    shutil.rmtree(BASE, ignore_errors=True)
    os.makedirs(BASE)
    for n, t in files.items():
        with open(os.path.join(BASE, n), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(t)


def _mirror():
    """Copies into the hand-pasted files, in their own line endings, and only
    when the text differs: clasp writes LF, the repo's copies are CRLF."""
    for name, dest in MIRRORS.items():
        src = os.path.join(PROJECT, name)
        if not os.path.isfile(src):
            continue
        with open(src, "rb") as fh:
            text = fh.read().replace(b"\r\n", b"\n")
        old = b""
        if os.path.isfile(dest):
            with open(dest, "rb") as fh:
                old = fh.read()
        if old.replace(b"\r\n", b"\n") == text:
            continue
        if b"\r\n" in old or not old:
            text = text.replace(b"\n", b"\r\n")
        with open(dest, "wb") as fh:
            fh.write(text)


def pull():
    clasp("pull")
    _save_base(_files(PROJECT))
    _mirror()
    print("pulled %d files; mirrors updated" % len(_files(PROJECT)))


def status(show=True):
    remote, local = _remote(), _files(PROJECT)
    names = _diff_names(remote, local)
    if show:
        print("push would change: " + (", ".join(names) or "nothing"))
        for n in names:
            sys.stdout.writelines(difflib.unified_diff(
                remote.get(n, "").splitlines(True), local.get(n, "").splitlines(True),
                "remote/" + n, "local/" + n, n=1))
    return remote, local, names


def push():
    if not os.path.isdir(BASE):
        sys.exit("no record of the last pull on this machine: run pull first")
    remote, local, names = status(show=False)
    drift = _diff_names(_files(BASE), remote)
    if drift:
        sys.exit("someone changed %s in the browser since the last pull; nothing was "
                 "pushed. Run pull (it overwrites local edits to those files, so copy "
                 "them aside first), merge, then push." % ", ".join(drift))
    if not names:
        print("nothing to push")
        return False
    clasp("push", "--force")
    _save_base(local)
    _mirror()
    print("pushed: " + ", ".join(names))
    return True


def deploy(why):
    push()
    print(clasp("deploy", "-i", WEBAPP, "-d", why).strip())


def read(sheet, n=20):
    tmp = os.path.join(tempfile.mkdtemp(), "sheet.csv")
    # headers=1: without it gviz guesses, and folds many rows into the header.
    url = ("https://docs.google.com/spreadsheets/d/%s/gviz/tq?tqx=out:csv&headers=1&sheet=%s"
           % (SHEET_ID, urllib.parse.quote(sheet)))
    urllib.request.urlretrieve(url, tmp)
    with open(tmp, encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    w = csv.writer(sys.stdout)
    for r in rows[:n]:
        w.writerow(r)
    print("(%d of %d rows)" % (min(n, len(rows)), len(rows)), file=sys.stderr)


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        sys.exit(__doc__)
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "pull":
        pull()
    elif cmd == "status":
        status()
    elif cmd == "push":
        push()
    elif cmd == "deploy":
        if not rest:
            sys.exit('say why: deploy "what changed"')
        deploy(rest[0])
    elif cmd == "versions":
        print(clasp("list-versions").strip())
    elif cmd == "read":
        read(rest[0], int(rest[1]) if len(rest) > 1 else 20)
    else:
        sys.exit("unknown command %r\n%s" % (cmd, __doc__))


if __name__ == "__main__":
    main()
