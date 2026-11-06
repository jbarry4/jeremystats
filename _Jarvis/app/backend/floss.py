"""
floss.py -- Floss, the bug fixer anyone in the lab can ask.

Somebody hits a bug, opens Floss, says what went wrong. Floss (Claude Code,
run headless on the lab's own Claude account) looks for the cause in a
private copy of the code and makes the smallest fix it can. The person
reads what it found and decides: use it on this machine now, or leave it
for review. Either way the ticket goes into GUI_logs/floss/, which travels
by git, and the main Claude Code session ("the mother AI") reviews it,
integrates it properly and settles any conflict. docs/floss.md is the
contract between the two.

WHAT KEEPS IT SMALL

  * Its own copy. Each ask copies backend/, web/ and tools/ -- as they are
    on this machine, uncommitted work included, because that is the code
    that misbehaved -- into %LOCALAPPDATA%\\Jarvis\\floss\\wt\\<id>, makes
    that a throwaway git repo, and runs there. The live tree, the real
    repo's index, branches and config are never touched by the run.
  * Few tools. Claude Code in --restricted mode with Read, Glob, Grep, Edit
    and a Bash that may only run py_compile, node --check and git diff /
    status. No Write (so no new files), no web, no agents, no MCP.
  * A hard limit after the run, not just a request before it: at most
    MAX_FILES files and MAX_LINES changed lines, existing files only, under
    backend/ web/ tools/, never the FENCED ones. A change past that is HELD
    -- kept for the mother AI, never offered to apply here.
  * Its own Claude Code home (CLAUDE_CONFIG_DIR), so the run never reads
    this machine's personal settings, memory or sign-in, and an environment
    scrubbed of every other ANTHROPIC_ / CLAUDE variable.

THE KEY is the lab account's, sealed in the cloud with the lab PIN and kept
here once somebody types it (floss_key.py). The engine is Claude Code: found
on PATH, in ~/.local/bin, or inside the VS Code extension, and installed
with one click from the dialog when none is found.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime

from . import feed
from . import floss_key as keymod
from .paths import APP_REL, LOGS_DIR, REPO_ROOT

WIN = sys.platform == "win32"
_NO_WINDOW = 0x08000000 if WIN else 0          # CREATE_NO_WINDOW: no console flashes up
TICKETS = os.path.join(LOGS_DIR, "floss")
WT_ROOT = os.path.join(keymod.STATE, "wt")
HOME = os.path.join(keymod.STATE, "home")
RUNLOGS = os.path.join(keymod.STATE, "runs")

NAME = "Hater of AI"              # what the page and the feed call him
MODEL = os.environ.get("JARVIS_FLOSS_MODEL") or "sonnet"
MAX_TURNS = 40
TIMEOUT_S = 15 * 60
BUDGET_USD = "2"                   # per run, API keys only (a plan has its own limits)

COPY_DIRS = ("backend", "web", "tools")
COPY_TOP = ("CHANGELOG.md", "README.md", "requirements.txt", "start.py", "setup.py")
COPY_MAX_BYTES = 2 * 1024 * 1024
EDIT_DIRS = ("backend/", "web/", "tools/")
EDIT_EXTS = (".py", ".js", ".css", ".html")
# Floss itself, its key, the sync, sign-ins, where things live, and the
# launchers: a "small fix" there can cost the lab its data or its access.
FENCED = (
    "backend/floss.py", "backend/floss_key.py", "web/js/floss.js",
    "tools/floss_setup.py", "tools/floss_inbox.py",
    "backend/cloud.py", "backend/cloudsync.py", "backend/shards.py",
    "backend/softmouse_login.py", "backend/paths.py", "backend/launchers.py",
)
MAX_FILES = 3
MAX_LINES = 60

RUN = {"running": False, "id": None, "what": None, "steps": [], "started": None,
       "proc": None, "stopped": False, "error": None}
_LOCK = threading.Lock()
HOOKS = {"who": None, "machine": None, "shard": None, "build": None, "errors": None}

RULES = """\
You are "Hater of AI", a small bug-fixing helper inside Jarvis, a neuroscience lab's
app (a Flask backend in _Jarvis/app/backend, a vanilla-JS front end in
_Jarvis/app/web, scripts in _Jarvis/app/tools). Your working directory is a
private copy of that code as it is on the machine where the bug happened.
Nothing you change touches the running app: a lab member decides afterwards
whether to use your change, and a senior engineer (Claude Code on the lab's
main machine, "the mother AI") reviews and integrates everything you leave.

Your job: find the cause of ONE reported bug and fix it with the smallest
change that works.

Hard limits. A change past them is not offered to the lab member; it is
held for the mother AI:
- at most 3 files and 60 changed lines in total;
- edit only existing .py .js .css .html files under _Jarvis/app/backend,
  _Jarvis/app/web or _Jarvis/app/tools. No new files, no deleted files;
- no new features, refactors, renames, new dependencies or formatting
  sweeps; nothing about cloud sync, shards, keys, sign-ins or file
  locations; no changes to data or to GUI_logs.
If the honest fix is bigger than that, or the ask is really a feature
request, make NO edit and say what is needed under "needs". A wrong fix is
worse than none: if you cannot find the cause with confidence, say so.

Read before you edit. Match the surrounding code's naming, idiom and comment
density. Words the app shows follow the house rules: plain words, and never
cut text short with an ellipsis. Check every edit: `python -m py_compile
FILE` for Python, `node --check FILE` for JavaScript, then `git diff`. You
cannot run the app or its tests.

Finish with two or three plain sentences for the person who asked (a lab
member, not a programmer), then one fenced json block exactly like this:
```json
{"summary": "one sentence", "cause": "what was wrong", "fix": "what you changed, or empty", "confidence": "high|medium|low", "tested": "what you checked", "needs": ["anything left for the mother AI: a bigger fix, a follow-up, a doubt"]}
```
"""


# --- small things ---------------------------------------------------------------

def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _hook(name, default=None):
    fn = HOOKS.get(name)
    if not fn:
        return default
    try:
        return fn()
    except Exception:                                    # noqa: BLE001
        return default


def _say(text, tid=None, level="info", done=False):
    feed.say(NAME + ": " + text, lane="jarvis", kind="floss", level=level,
             key="floss-" + (tid or "engine"), done=done)


def _git(args, cwd, check=True, inp=None):
    r = subprocess.run(["git", "-c", "core.longpaths=true"] + list(args), cwd=cwd,
                       input=inp, capture_output=True,
                       creationflags=_NO_WINDOW)
    if check and r.returncode:
        raise RuntimeError("git %s: %s" % (args[0], (r.stderr or r.stdout).decode("utf-8", "replace").strip()))
    return r.stdout.decode("utf-8", "replace")


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "wb") as fh:
        fh.write((json.dumps(obj, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    os.replace(tmp, path)


def _rmtree(path):
    def onerror(fn, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            fn(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=onerror)


# --- the engine (Claude Code) ------------------------------------------------------

_VERSION = {}


def _ver_key(path):
    m = re.search(r"claude-code-(\d+)\.(\d+)\.(\d+)", path)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def engine():
    """The Claude Code executable this machine can run, or None."""
    exe = "claude.exe" if WIN else "claude"
    home = os.path.expanduser("~")
    cands = [os.environ.get("JARVIS_CLAUDE"), shutil.which("claude"),
             os.path.join(home, ".local", "bin", exe)]
    ext = sorted(glob.glob(os.path.join(home, ".vscode", "extensions", "anthropic.claude-code-*")),
                 key=_ver_key, reverse=True)
    cands += [os.path.join(d, "resources", "native-binary", exe) for d in ext]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def engine_version(path):
    if not path:
        return None
    try:
        sig = (path, os.path.getmtime(path))
    except OSError:
        return None
    if sig not in _VERSION:
        try:
            r = subprocess.run([path, "--version"], capture_output=True, timeout=30,
                               creationflags=_NO_WINDOW)
            _VERSION[sig] = r.stdout.decode("utf-8", "replace").strip().split(" ")[0] or None
        except (OSError, subprocess.SubprocessError):
            _VERSION[sig] = None
    return _VERSION[sig]


def _install():
    _say("installing Claude Code on this machine (about a minute)", "engine")
    if WIN:
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
               "irm https://claude.ai/install.ps1 | iex"]
    else:
        cmd = ["bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"]
    r = subprocess.run(cmd, capture_output=True, timeout=600, creationflags=_NO_WINDOW)
    if not engine():
        said = (r.stderr or r.stdout).decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError("the installer finished but Claude Code was not found"
                           + (": " + said[-1] if said else ""))
    _say("Claude Code is installed", "engine", done=True)


# --- tickets -----------------------------------------------------------------------

def _shard():
    return _hook("shard", "") or "here"


def _path_of(tid, shard=None):
    return os.path.join(TICKETS, "%s@%s.json" % (tid, shard or _shard()))


def load(tid):
    with open(_path_of(tid), encoding="utf-8") as fh:
        return json.load(fh)


def save(t):
    t["updated"] = _now_iso()
    _write_json(_path_of(t["id"], t.get("shard")), t)


def tickets(limit=30):
    """This machine's tickets, newest first, without their patches."""
    out = []
    for p in sorted(glob.glob(os.path.join(TICKETS, "*@%s.json" % _shard())), reverse=True)[:limit]:
        try:
            with open(p, encoding="utf-8") as fh:
                t = json.load(fh)
        except (OSError, ValueError):
            continue
        out.append({k: t.get(k) for k in ("id", "at", "who", "ask", "status", "report",
                                          "files", "lines", "held_because", "mother")})
    return out


# --- one ask -------------------------------------------------------------------------

def _step(tid, text):
    with _LOCK:
        RUN["steps"].append({"at": time.time(), "text": text})
        del RUN["steps"][:-60]
    _say(text, tid)


def _prepare(tid):
    """Copy the code as it is on this machine into a throwaway repo."""
    root = os.path.join(WT_ROOT, tid)
    os.makedirs(root)
    rels = _git(["ls-files", "-z", "-co", "--exclude-standard", "--"]
                + ["%s/%s" % (APP_REL, d) for d in COPY_DIRS], REPO_ROOT).split("\0")
    rels += ["%s/%s" % (APP_REL, f) for f in COPY_TOP]
    n = 0
    for rel in rels:
        if not rel or "__pycache__" in rel:
            continue
        src = os.path.join(REPO_ROOT, rel)
        try:
            if os.path.getsize(src) > COPY_MAX_BYTES:
                continue
        except OSError:
            continue
        dst = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        n += 1
    _git(["init", "-q"], root)
    # His own syntax checks leave bytecode behind; it is not a change he made.
    with open(os.path.join(root, ".git", "info", "exclude"), "a", encoding="utf-8") as fh:
        fh.write("\n__pycache__/\n*.pyc\n")
    for args in (["config", "core.autocrlf", "false"],
                 ["config", "user.name", "Floss"], ["config", "user.email", "floss@jarvis.local"],
                 ["add", "-A"], ["commit", "-q", "-m", "as it was on this machine"]):
        _git(args, root)
    dirty = [ln[3:] for ln in _git(["status", "--porcelain", "--"]
                                   + ["%s/%s" % (APP_REL, d) for d in COPY_DIRS],
                                   REPO_ROOT, check=False).splitlines() if ln.strip()]
    head = _git(["rev-parse", "HEAD"], REPO_ROOT, check=False).strip()
    return root, n, head, dirty


def _brief(t):
    c = t.get("context") or {}
    L = ["A lab member asked for help:", "", t["ask"].strip(), "",
         "On machine %s, Jarvis %s, commit %s." % (t.get("machine"), t.get("build"),
                                                  (t.get("head") or "")[:10])]
    if c.get("view"):
        L.append("They were in the %s view." % c["view"])
    if t.get("dirty"):
        L.append("This machine had uncommitted changes in: " + ", ".join(t["dirty"][:20])
                 + ". Your copy includes them.")
    e = c.get("error")
    if e:
        L += ["", "The error they pointed at:",
              "  where:   %s" % e.get("where"), "  when:    %s" % e.get("at"),
              "  message: %s" % e.get("message")]
        if e.get("context"):
            L.append("  context: %s" % json.dumps(e["context"], ensure_ascii=False)[:600])
        if e.get("detail"):
            L += ["  traceback:", str(e["detail"])[-4000:]]
    recent = c.get("recent") or []
    if recent:
        L += ["", "Other recent errors on this machine (newest first):"]
        L += ["  %s  %s  %s" % (r.get("at"), r.get("where"), str(r.get("message"))[:200])
              for r in recent[:8]]
    L += ["", "Code paths in your copy start with %s/." % APP_REL]
    return "\n".join(L)


def _show_path(p, root):
    p = str(p or "")
    if p.lower().startswith(root.lower()):
        p = p[len(root):].lstrip("\\/")
    p = p.replace("\\", "/")
    pre = APP_REL + "/"
    return p[len(pre):] if p.startswith(pre) else p


def _narrate(tid, root, ev):
    """One stream-json event -> a step in plain words, when it is worth one."""
    if ev.get("type") != "assistant":
        return
    for b in (ev.get("message") or {}).get("content") or []:
        if b.get("type") == "tool_use":
            i, n = b.get("input") or {}, b.get("name")
            if n == "Read":
                _step(tid, "reading " + _show_path(i.get("file_path"), root))
            elif n == "Edit":
                _step(tid, "editing " + _show_path(i.get("file_path"), root))
            elif n == "Grep":
                _step(tid, "searching the code for “%s”" % str(i.get("pattern"))[:80])
            elif n == "Glob":
                _step(tid, "looking for files like " + str(i.get("pattern"))[:80])
            elif n == "Bash":
                _step(tid, "checking: " + _show_path(str(i.get("command"))[:120], root))
        elif b.get("type") == "text" and (b.get("text") or "").strip():
            first = b["text"].strip().splitlines()[0]
            if not first.startswith("```") and not first.startswith("{"):
                _step(tid, first[:240])


def _report_of(text):
    """The json block Floss ends with, and the words before it."""
    text = text or ""
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    rep = {}
    if blocks:
        try:
            rep = json.loads(blocks[-1])
        except ValueError:
            rep = {}
    words = re.split(r"```json", text)[0].strip()
    rep = {k: rep.get(k) for k in ("summary", "cause", "fix", "confidence", "tested", "needs")}
    rep["needs"] = [str(n) for n in (rep.get("needs") or []) if str(n).strip()]
    rep["words"] = words[-3000:]
    return rep


def _judge(root):
    """The change Floss made, and whether it is small enough to offer."""
    patch = _git(["diff", "--no-color", "--no-ext-diff"], root)
    files, why, total = [], [], 0
    for ln in _git(["diff", "--numstat"], root).splitlines():
        a, r, path = ln.split("\t", 2)
        a, r = (int(a) if a.isdigit() else 0), (int(r) if r.isdigit() else 0)
        short = path[len(APP_REL) + 1:] if path.startswith(APP_REL + "/") else path
        files.append({"path": short, "added": a, "removed": r})
        total += a + r
        if not short.startswith(EDIT_DIRS) or path == short:
            why.append("%s is outside backend/, web/ and tools/" % short)
        elif short in FENCED:
            why.append("%s is fenced: the mother AI changes it, not %s" % (short, NAME))
        elif not short.endswith(EDIT_EXTS):
            why.append("%s is not code %s may edit" % (short, NAME))
    for ln in _git(["status", "--porcelain"], root).splitlines():
        if ln.startswith("??") or ln[:2].strip() in ("A", "D"):
            why.append("%s was %s" % (ln[3:], "deleted" if "D" in ln[:2] else "added"))
    if len(files) > MAX_FILES:
        why.append("%d files changed; the limit is %d" % (len(files), MAX_FILES))
    if total > MAX_LINES:
        why.append("%d lines changed; the limit is %d" % (total, MAX_LINES))
    return patch, files, total, why


def _env(key):
    env = {k: v for k, v in os.environ.items()
           if not (k.upper().startswith("ANTHROPIC_") or k.upper().startswith("CLAUDE"))}
    env.update(CLAUDE_CONFIG_DIR=HOME, DISABLE_AUTOUPDATER="1",
               CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1", PYTHONDONTWRITEBYTECODE="1")
    env["CLAUDE_CODE_OAUTH_TOKEN" if keymod.kind_of(key) == "oauth" else "ANTHROPIC_API_KEY"] = key
    return env


def _command(exe, key, rules_file):
    cmd = [exe, "-p", "--output-format", "stream-json", "--verbose",
           "--model", MODEL, "--max-turns", str(MAX_TURNS),
           "--restricted", "--tools", "Read,Glob,Grep,Edit,Bash",
           "--allowedTools", "Read", "Glob", "Grep", "Edit",
           "Bash(python -m py_compile:*)", "Bash(py -3 -m py_compile:*)",
           "Bash(python3 -m py_compile:*)", "Bash(node --check:*)",
           "Bash(git diff:*)", "Bash(git status:*)",
           "--permission-mode", "dontAsk", "--strict-mcp-config",
           "--no-session-persistence", "--append-system-prompt-file", rules_file]
    if keymod.kind_of(key) == "api":
        cmd += ["--max-budget-usd", BUDGET_USD]
    return cmd


def _kill(proc):
    if not proc or proc.poll() is not None:
        return
    try:
        if WIN:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, creationflags=_NO_WINDOW)
        else:
            os.killpg(proc.pid, 9)
    except OSError:
        proc.kill()


def _run(t, key, exe):
    tid, root = t["id"], None
    try:
        _step(tid, "copying the code as it is on this machine")
        root, n, t["head"], t["dirty"] = _prepare(tid)
        save(t)
        os.makedirs(RUNLOGS, exist_ok=True)
        os.makedirs(HOME, exist_ok=True)
        rules = os.path.join(RUNLOGS, tid + ".rules.md")
        with open(rules, "w", encoding="utf-8") as fh:
            fh.write(RULES)
        _step(tid, "looking into it (%d files in its copy)" % n)
        log = open(os.path.join(RUNLOGS, tid + ".jsonl"), "wb")
        err = open(os.path.join(RUNLOGS, tid + ".stderr.txt"), "wb")
        try:
            proc = subprocess.Popen(_command(exe, key, rules), cwd=root, env=_env(key),
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err,
                                    creationflags=_NO_WINDOW, start_new_session=not WIN)
            RUN["proc"] = proc
            proc.stdin.write(_brief(t).encode("utf-8"))
            proc.stdin.close()
            timer = threading.Timer(TIMEOUT_S, _kill, [proc])
            timer.daemon = True
            timer.start()
            result = {}
            for raw in proc.stdout:
                log.write(raw)
                try:
                    ev = json.loads(raw)
                except ValueError:
                    continue
                if ev.get("type") == "result":
                    result = ev
                else:
                    _narrate(tid, root, ev)
            proc.wait()
            timer.cancel()
        finally:
            log.close()
            err.close()
        t["run"] = {"model": MODEL, "key": keymod.kind_of(key), "engine": engine_version(exe),
                    "turns": result.get("num_turns"), "cost_usd": result.get("total_cost_usd"),
                    "seconds": round((result.get("duration_ms") or 0) / 1000.0, 1) or None,
                    "end": result.get("subtype"), "exit": proc.returncode}
        if RUN["stopped"]:
            t["status"] = "stopped"
            return
        if not result or result.get("is_error"):
            with open(os.path.join(RUNLOGS, tid + ".stderr.txt"), encoding="utf-8",
                      errors="replace") as fh:
                said = fh.read().strip().splitlines()
            msg = (result.get("result") if result else None) or (said[-1] if said else
                                                                   "Claude Code stopped without an answer")
            if proc.returncode and not result and time.time() - RUN["started"] >= TIMEOUT_S - 1:
                msg = "it ran out of time (%d min)" % (TIMEOUT_S // 60)
            t.update(status="failed", error=str(msg)[:1000])
            return
        t["report"] = _report_of(result.get("result"))
        patch, files, total, why = _judge(root)
        t.update(patch=patch, files=files, lines=total, held_because=why)
        if not patch.strip():
            t["status"] = "nothing"
        elif why:
            t["status"] = "held"
        else:
            t["status"] = "ready"
    except Exception as e:                               # noqa: BLE001
        t.update(status="failed", error=str(e)[:1000])
    finally:
        save(t)
        if root:
            _rmtree(root)
        words = {"ready": "has a fix ready to look at", "held": "found something too big "
                 "to apply here; it is kept for review", "nothing": "made no change",
                 "stopped": "was stopped", "failed": "could not finish: %s" % t.get("error")}
        _say(words.get(t["status"], t["status"]), tid,
             level="err" if t["status"] == "failed" else "info", done=True)
        with _LOCK:
            RUN.update(running=False, proc=None, what=None)


def ask(text, context=None):
    text = (text or "").strip()
    if len(text) < 8:
        raise ValueError("say a little more about what went wrong")
    exe = engine()
    if not exe:
        raise RuntimeError("Claude Code is not on this machine yet; install it first")
    key = keymod.here()
    if not key:
        raise RuntimeError(NAME + " is locked on this machine; type the lab PIN first")
    with _LOCK:
        if RUN["running"]:
            raise RuntimeError(NAME + " is already working on something here")
        tid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        RUN.update(running=True, id=tid, what="ask", steps=[], started=time.time(),
                   stopped=False, error=None)
    ctx = dict(context or {})
    errs = _hook("errors", []) or []
    ctx["recent"] = [{k: e.get(k) for k in ("at", "where", "message")} for e in errs[:8]]
    t = {"id": tid, "shard": _shard(), "machine": _hook("machine"), "who": _hook("who"),
         "at": _now_iso(), "build": _hook("build"), "ask": text, "context": ctx,
         "status": "working", "report": None, "patch": "", "files": [], "lines": 0,
         "held_because": [], "applied": None, "undone": None, "mother": None}
    try:
        save(t)
        threading.Thread(target=_run, args=(t, key, exe), daemon=True,
                         name="jarvis-floss-" + tid).start()
    except Exception:
        with _LOCK:
            RUN.update(running=False, what=None)
        raise
    return tid


def stop():
    with _LOCK:
        if not RUN["running"]:
            return False
        RUN["stopped"] = True
        proc = RUN["proc"]
    _kill(proc)
    return True


# --- using a fix here ---------------------------------------------------------------

def _apply(t, reverse=False):
    fd, tmp = tempfile.mkstemp(suffix=".diff")
    with os.fdopen(fd, "wb") as fh:
        fh.write(t["patch"].encode("utf-8"))
    try:
        base = ["apply", "--whitespace=nowarn"] + (["-R"] if reverse else [])
        try:
            _git(base + ["--check", tmp], REPO_ROOT)
        except RuntimeError as e:
            raise RuntimeError(("the code here has changed since " + NAME + " looked, so his fix "
                                "no longer fits; it stays for review (%s)" if not reverse else
                                "the files have changed since the fix went in, so it cannot "
                                "be taken out by itself (%s)") % str(e)[:300])
        _git(base + [tmp], REPO_ROOT)
    finally:
        os.remove(tmp)


def _after(t):
    paths = [f["path"] for f in t.get("files") or []]
    return {"restart": any(p.startswith("backend/") for p in paths),
            "reload": any(p.startswith("web/") for p in paths)}


def use(tid, by=None):
    t = load(tid)
    if t.get("status") != "ready":
        raise RuntimeError("only a fix that is ready can be used here (this one is %s)"
                           % t.get("status"))
    _apply(t)
    t.update(status="applied", applied={"at": _now_iso(), "by": by})
    save(t)
    _say("its fix is in use on this machine", tid, done=True)
    return _after(t)


def undo(tid, by=None):
    t = load(tid)
    if t.get("status") != "applied":
        raise RuntimeError("that fix is not in use here")
    _apply(t, reverse=True)
    t.update(status="undone", undone={"at": _now_iso(), "by": by})
    save(t)
    _say("its fix was taken out again", tid, done=True)
    return _after(t)


def dismiss(tid, by=None):
    t = load(tid)
    if t.get("status") in ("working", "applied"):
        raise RuntimeError("that one cannot be put away while it is %s" % t["status"])
    t.update(dismissed={"at": _now_iso(), "by": by, "was": t.get("status")}, status="dismissed")
    save(t)


# --- the page -------------------------------------------------------------------------

def status():
    exe = engine()
    key = keymod.here()
    with _LOCK:
        run = {"running": RUN["running"], "id": RUN["id"], "steps": list(RUN["steps"]),
               "started": RUN["started"]}
    return {"ok": True,
            "engine": {"path": exe, "version": engine_version(exe) if exe else None,
                       "installing": RUN.get("what") == "install"},
            "key": {"here": bool(key), "kind": keymod.kind_of(key), "hint": keymod.HINT},
            "limits": {"files": MAX_FILES, "lines": MAX_LINES, "model": MODEL},
            "run": run, "tickets": tickets()}


def install(app, fail, who=None, machine=None, shard=None, build=None, errors=None):
    from flask import jsonify, request
    HOOKS.update(who=who, machine=machine, shard=shard, build=build, errors=errors)
    os.makedirs(TICKETS, exist_ok=True)
    # A run the server died in the middle of says so, rather than "working"
    # for ever, and its copy is cleared out. Only once it is older than any
    # run can last: a harness server on this machine shares these folders,
    # and must not end the real server's run.
    stale = time.time() - TIMEOUT_S - 120
    for p in glob.glob(os.path.join(TICKETS, "*@%s.json" % _shard())):
        try:
            if os.path.getmtime(p) > stale:
                continue
            with open(p, encoding="utf-8") as fh:
                t = json.load(fh)
            if t.get("status") == "working":
                t.update(status="failed", error="Jarvis stopped while " + NAME + " was working")
                save(t)
        except (OSError, ValueError):
            pass
    if os.path.isdir(WT_ROOT):
        for d in os.listdir(WT_ROOT):
            try:
                if os.path.getmtime(os.path.join(WT_ROOT, d)) < stale:
                    _rmtree(os.path.join(WT_ROOT, d))
            except OSError:
                pass

    def body():
        return request.get_json(silent=True) or {}

    @app.route("/api/floss/status")
    def api_floss_status():
        return jsonify(status())

    @app.route("/api/floss/ticket")
    def api_floss_ticket():
        try:
            return jsonify({"ok": True, "ticket": load(request.args.get("id") or "")})
        except (OSError, ValueError):
            return jsonify({"ok": False, "error": "no such ticket on this machine"}), 404

    @app.route("/api/floss/unlock", methods=["POST"])
    def api_floss_unlock():
        pin = str(body().get("pin") or "").strip()
        if not pin:
            return jsonify({"ok": False, "error": "type the PIN"}), 400
        try:
            keymod.unlock(pin)
        except keymod.WrongPin as e:
            return jsonify({"ok": False, "error": str(e), "hint": keymod.HINT}), 403
        except Exception as e:                           # noqa: BLE001
            return jsonify({"ok": False, "error": str(e)}), 400
        _say("unlocked on this machine", "engine", done=True)
        return jsonify(status())

    @app.route("/api/floss/install", methods=["POST"])
    def api_floss_install():
        with _LOCK:
            if RUN["running"]:
                return jsonify({"ok": False, "error": NAME + " is busy"}), 409
            RUN.update(running=True, what="install", id=None, steps=[], started=time.time())

        def go():
            try:
                _install()
            except Exception as e:                       # noqa: BLE001
                _say("could not install Claude Code: %s" % e, "engine", level="err", done=True)
            finally:
                with _LOCK:
                    RUN.update(running=False, what=None)
        threading.Thread(target=go, daemon=True, name="jarvis-floss-install").start()
        return jsonify(status())

    @app.route("/api/floss/ask", methods=["POST"])
    def api_floss_ask():
        b = body()
        try:
            tid = ask(b.get("ask"), b.get("context"))
        except Exception as e:                           # noqa: BLE001
            return jsonify({"ok": False, "error": str(e)}), 400
        return jsonify(dict(status(), id=tid))

    @app.route("/api/floss/stop", methods=["POST"])
    def api_floss_stop():
        stop()
        return jsonify(status())

    def act(fn):
        b = body()
        try:
            got = fn(str(b.get("id") or ""), by=_hook("who"))
        except FileNotFoundError:
            return jsonify({"ok": False, "error": "no such ticket on this machine"}), 404
        except Exception as e:                           # noqa: BLE001
            return jsonify({"ok": False, "error": str(e)}), 400
        return jsonify(dict(status(), after=got))

    @app.route("/api/floss/use", methods=["POST"])
    def api_floss_use():
        return act(use)

    @app.route("/api/floss/undo", methods=["POST"])
    def api_floss_undo():
        return act(undo)

    @app.route("/api/floss/dismiss", methods=["POST"])
    def api_floss_dismiss():
        return act(dismiss)
